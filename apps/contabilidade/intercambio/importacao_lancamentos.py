"""Importação de lançamentos com área de conferência (DL-077, fatia 3, frente A).

QUATRO OPERAÇÕES, E A SEPARAÇÃO É PROPOSITAL.

1. `receber` LÊ, CONFERE e GRAVA a importação em conferência (`ImportacaoLancamentos`, com
   `LancamentoImportado` por lançamento). NADA entra no Diário.
2. `reconferir` refaz a conferência com o cadastro atual (de-para, competências, contas).
   É o que o contador roda depois de mudar um de-para ou reabrir uma competência.
3. `definir_de_para` e `aceitar_avisos` são as decisões do contador, gravadas na trilha.
4. `efetivar` é a ÚNICA operação que grava no Diário. Reconfere, decide pela política
   (tudo ou nada, ou só os válidos), e chama `criar_lancamento` um a um, numa transação. Uma
   falha no meio desfaz tudo. A chave de idempotência é `importacao:<SHA-256>:<número de origem>`:
   o SHA-256 faz com que o mesmo número em outro arquivo NÃO colida, e o prefixo é reservado
   (`criar_lancamento` recusa `importacao:` sem o parâmetro `permitir_prefixo_da_importacao`).

REGRAS DE CONFERÊNCIA (por lançamento; erro nunca efetiva, aviso só efetiva se aceito):
- débitos = créditos; ao menos um débito e um crédito; valor > 0 com no máximo 2 casas;
- data válida na faixa do RC-77 (`validar_data_de_lancamento`);
- competência da data ABERTA. Competência inexistente é aberta: é o que `criar_lancamento`
  faz (`obter_ou_criar_competencia`). Encerrada ou entregue é erro;
- conta: pelo código exato do plano da empresa (formatos ECD, próprio e Excel); senão pelo
  de-para (`DeParaConta`). No sistema de referência o código é o REDUZIDO, que o DataLedger
  não tem: só o de-para resolve. Sem resolução é erro que nomeia o código de origem. Conta
  precisa ser analítica (`aceita_lancamento`) e ativa;
- histórico: as partidas com o mesmo texto geram esse texto; textos diferentes são
  concatenados com ' | ' e geram AVISO. Mais de 300 caracteres é erro: nunca se trunca;
- número repetido e número acima de 100 caracteres: erro;
- CNPJ/CPF declarado no arquivo diferente da empresa: recusa do arquivo INTEIRO, com
  mensagem sem os números.

POLÍTICAS DE EFETIVAÇÃO. `tudo_ou_nada` (padrão): qualquer erro, qualquer aviso não aceito, ou
erro do arquivo recusa a efetivação inteira. `so_validos`: efetiva os lançamentos sem erro e
com avisos aceitos; os demais ficam no relatório da importação.

AVISOS DO ARQUIVO (sem lançamento, como a codificação UTF-8) não bloqueiam: não há o que
aceitar por lançamento. Avisos de lançamento exigem aceite (`aceitar_avisos`).

PERMISSÃO. Este módulo não conhece papel: quem chama (a API) verifica o papel no servidor
(`PodeEscriturar` para receber, conferir, de-para, aceitar avisos, efetivar e descartar;
`PodeLerContabilidade` para ler). Ver `apps/contabilidade/views.py`.
"""

import hashlib
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_AVISO,
    NIVEL_ERRO,
    IntercambioRecusado,
)
from apps.contabilidade.intercambio.formatos import (
    ecd_lancamentos_leitura,
    excel_lancamentos,
    proprio_lancamentos_leitura,
    referencia_lancamentos_leitura,
)
from apps.contabilidade.intercambio.leitura import (
    MAXIMO_DE_LINHAS,
    TAMANHO_MAXIMO_ARQUIVO_BYTES,
    ArquivoGrandeDemais,
)
from apps.contabilidade.models import (
    Competencia,
    Conta,
    DeParaConta,
    EstadoCompetencia,
    EstadoImportacaoLancamentos,
    FormatoImportacaoLancamentos,
    ImportacaoLancamentos,
    LancamentoContabil,
    LancamentoImportado,
    TipoPartida,
)
from apps.contabilidade.services import (
    LancamentoInvalido,
    _travar_empresa_para_operacao_de_zeramento,
    criar_lancamento,
    validar_data_de_lancamento,
)

FORMATO_REFERENCIA = FormatoImportacaoLancamentos.REFERENCIA

# Leitores de LANÇAMENTOS. Cada um recebe os bytes e devolve `ResultadoLeitura` com
# `lancamentos`. O leitor do plano (`formatos.LEITORES`) é outra coisa, e não entra aqui.
LEITORES_DE_LANCAMENTOS = {
    FormatoImportacaoLancamentos.ECD: ecd_lancamentos_leitura.ler,
    FormatoImportacaoLancamentos.PROPRIO: proprio_lancamentos_leitura.ler,
    FormatoImportacaoLancamentos.EXCEL: excel_lancamentos.ler,
    FormatoImportacaoLancamentos.REFERENCIA: referencia_lancamentos_leitura.ler,
}

# Limite de lançamentos por arquivo. MEDIDO (2026-10-08, PostgreSQL, dados sintéticos, plano do
# cenário de exportação): efetivar custa ~10,7 ms por lançamento, em ~18 consultas, e cresce de
# forma linear: 1.000 = 10,9 s; 2.000 = 21,5 s; 5.000 = 54,4 s; 20.000 = 214 s. Receber 20.000
# leva 38 s. O gunicorn do Dockerfile corta a requisição em 30 s (sem --workers). Por isso o teto
# é 2.000: a efetivação nele cabe em ~25 s. Acima disso a recusa é nomeada, nunca truncada.
LIMITE_DE_LANCAMENTOS_POR_ARQUIVO = 2_000

TAMANHO_MAXIMO_HISTORICO = LancamentoContabil._meta.get_field("historico").max_length
TAMANHO_MAXIMO_NUMERO = 100  # a chave `importacao:<64>:<número>` cabe em 255 com folga
PREFIXO_DA_CHAVE = "importacao"
SEPARADOR_DE_HISTORICO = " | "
CENTAVO = Decimal("0.01")

TUDO_OU_NADA = "tudo_ou_nada"
SO_VALIDOS = "so_validos"
POLITICAS_DE_EFETIVACAO = (TUDO_OU_NADA, SO_VALIDOS)

_NAO_ALFANUMERICO = re.compile(r"[^0-9A-Z]")


class ImportacaoRecusada(IntercambioRecusado):
    """Recusa nomeada: a operação não segue. Nada foi gravado. A API responde 400."""


class ImportacaoJaExiste(ImportacaoRecusada):
    """O mesmo arquivo já está em conferência ou efetivado nesta empresa (409)."""

    def __init__(self, mensagem, importacao_id):
        super().__init__(mensagem)
        self.importacao_id = importacao_id


class ImportacaoEmEstadoInvalido(ImportacaoRecusada):
    """A importação já foi efetivada ou descartada: a operação não cabe mais (409)."""


class ImportacaoNaoEfetivada(ImportacaoRecusada):
    """`tudo_ou_nada` com erro ou aviso não aceito. `ocorrencias` diz linha, campo e lançamento."""

    def __init__(self, mensagem, ocorrencias=()):
        super().__init__(mensagem, ocorrencias)


@dataclass
class ResultadoDaEfetivacao:
    importacao: ImportacaoLancamentos
    criados: int
    reaproveitados: int
    nao_efetivados: list = field(default_factory=list)


def _validar_formato(formato):
    if formato == FORMATO_REFERENCIA or formato in LEITORES_DE_LANCAMENTOS:
        return
    raise ImportacaoRecusada(
        f"formato '{formato}' não suportado para importar lançamentos. Use: "
        f"{', '.join(sorted(LEITORES_DE_LANCAMENTOS))}."
    )


def _conferir_limites(conteudo):
    """Tamanho e linhas, antes de qualquer leitura (mesmos limites do plano de contas)."""
    if len(conteudo) > TAMANHO_MAXIMO_ARQUIVO_BYTES:
        raise ArquivoGrandeDemais(
            f"arquivo com {len(conteudo)} bytes; o limite é "
            f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
        )
    linhas = conteudo.count(b"\n") + 1
    if linhas > MAXIMO_DE_LINHAS:
        raise ArquivoGrandeDemais(
            f"arquivo com cerca de {linhas} linhas; o limite é {MAXIMO_DE_LINHAS}."
        )


def _documento_da_empresa(empresa):
    """CNPJ (ou CPF) canônico da empresa: só dígitos e letras maiúsculas (RC-46)."""
    return _NAO_ALFANUMERICO.sub("", (empresa.cnpj or empresa.cpf or "").upper())


def _ocorrencia(linha, campo, nivel, mensagem, origem):
    return {"linha": linha, "campo": campo, "nivel": nivel, "mensagem": mensagem, "origem": origem}


def _ocorrencia_de_leitura(ocorrencia):
    return _ocorrencia(
        ocorrencia.linha, ocorrencia.campo, ocorrencia.nivel, ocorrencia.mensagem, "leitura"
    )


@dataclass
class _Contexto:
    """O cadastro que a conferência consulta: contas, de-para e competências da empresa."""

    empresa: object
    formato: str
    contas: dict
    depara: dict
    competencias: dict

    @classmethod
    def carregar(cls, empresa, formato):
        # Sistema de referência: o código do arquivo é REDUZIDO, e o DataLedger não tem reduzido.
        # Um código exato do plano nunca pode ser lido como a conta de mesmo número.
        if formato == FORMATO_REFERENCIA:
            contas = {}
        else:
            contas = {conta.codigo: conta for conta in Conta.objects.filter(empresa=empresa)}
        depara = {
            d.codigo_origem: d.conta
            for d in DeParaConta.objects.filter(empresa=empresa, formato=formato).select_related(
                "conta"
            )
        }
        competencias = {
            (ano, mes): estado
            for ano, mes, estado in Competencia.objects.filter(empresa=empresa).values_list(
                "ano", "mes", "estado"
            )
        }
        return cls(
            empresa=empresa,
            formato=formato,
            contas=contas,
            depara=depara,
            competencias=competencias,
        )

    def resolver_conta(self, codigo_origem):
        """(conta, 'codigo' | 'depara') ou (None, None). Código exato do plano vence o de-para."""
        if codigo_origem in self.contas:
            return self.contas[codigo_origem], "codigo"
        conta = self.depara.get(codigo_origem)
        if conta is not None:
            return conta, "depara"
        return None, None


def _conferir_lancamento(contexto, *, numero, data, partidas, linha, historico_do_lancamento=""):
    """Confere um lançamento contra o cadastro. Não grava.

    `partidas` são dicts com `linha`, `codigo_origem`, `lado`, `valor` (Decimal) e `historico`.
    Devolve (histórico montado, partidas com a conta resolvida, ocorrências da conferência).
    """
    ocorrencias = []

    def erro(campo, mensagem, linha_=None):
        ocorrencias.append(_ocorrencia(linha_ or linha, campo, NIVEL_ERRO, mensagem, "conferencia"))

    def aviso(campo, mensagem):
        ocorrencias.append(_ocorrencia(linha, campo, NIVEL_AVISO, mensagem, "conferencia"))

    if not numero or len(numero) > TAMANHO_MAXIMO_NUMERO:
        erro("numero", f"número de origem com mais de {TAMANHO_MAXIMO_NUMERO} caracteres ou vazio.")

    try:
        validar_data_de_lancamento(data)
    except LancamentoInvalido as exc:
        erro("data", str(exc))

    # Mesma regra de `criar_lancamento`: competência que não existe é aberta (ela é criada).
    estado = contexto.competencias.get((data.year, data.month))
    if estado is not None and estado != EstadoCompetencia.ABERTA:
        nome = EstadoCompetencia(estado).label.lower()
        erro(
            "data",
            f"a competência {data.month:02d}/{data.year} está {nome}: o lançamento não entra nela. "
            "Reabra a competência e confira de novo, ou corrija a data no arquivo.",
        )

    if len(partidas) < 2:
        erro("partidas", "um lançamento precisa de ao menos duas partidas.")
    lados = {p["lado"] for p in partidas}
    if LADO_DEBITO not in lados or LADO_CREDITO not in lados:
        erro("partidas", "o lançamento precisa de ao menos um débito e um crédito.")

    resolvidas = []
    soma = {LADO_DEBITO: Decimal("0.00"), LADO_CREDITO: Decimal("0.00")}
    for partida in partidas:
        valor = partida["valor"]
        if valor <= 0:
            erro("valor", f"valor {valor} não é positivo.", partida["linha"])
        elif valor != valor.quantize(CENTAVO):
            erro(
                "valor",
                f"valor {valor} tem mais de 2 casas decimais: não há arredondamento.",
                partida["linha"],
            )
        else:
            soma[partida["lado"]] += valor

        conta, origem = contexto.resolver_conta(partida["codigo_origem"])
        if conta is None:
            erro(
                "conta",
                f"conta de origem '{partida['codigo_origem']}' não existe no plano "
                "e não tem de-para "
                f"para o formato {contexto.formato}. Defina o de-para deste código e reconfira.",
                partida["linha"],
            )
        else:
            if not conta.aceita_lancamento:
                erro(
                    "conta",
                    f"conta {conta.codigo} é sintética: não recebe lançamento direto.",
                    partida["linha"],
                )
            if not conta.ativo:
                erro("conta", f"conta {conta.codigo} está inativa.", partida["linha"])
        resolvidas.append(
            {
                "linha": partida["linha"],
                "codigo_origem": partida["codigo_origem"],
                "conta_id": conta.pk if conta is not None else None,
                "conta_codigo": conta.codigo if conta is not None else None,
                "origem_da_conta": origem,
                "lado": partida["lado"],
                "valor": str(valor),
                "historico": partida["historico"],
            }
        )

    if soma[LADO_DEBITO] != soma[LADO_CREDITO]:
        erro(
            "valores",
            f"débitos ({soma[LADO_DEBITO]}) diferem dos créditos "
            f"({soma[LADO_CREDITO]}): o lançamento "
            "não fecha.",
        )

    textos = []
    for partida in partidas:
        texto = partida["historico"]
        if texto and texto.strip() and texto not in textos:
            textos.append(texto)
    if not textos and historico_do_lancamento and historico_do_lancamento.strip():
        textos = [historico_do_lancamento]
    if not textos:
        erro("historico", "histórico vazio.")
    montado = SEPARADOR_DE_HISTORICO.join(textos)
    if len(textos) > 1:
        aviso(
            "historico",
            f"as partidas trazem {len(textos)} históricos diferentes: o lançamento usa todos, "
            f"separados por '{SEPARADOR_DE_HISTORICO.strip()}'.",
        )
    if len(montado) > TAMANHO_MAXIMO_HISTORICO:
        erro(
            "historico",
            f"histórico com {len(montado)} caracteres; o máximo é {TAMANHO_MAXIMO_HISTORICO}. Nada "
            "foi truncado: encurte o texto no arquivo.",
        )

    return montado, resolvidas, ocorrencias


def _dono_das_linhas(resultado):
    """Linha de origem -> número do lançamento, das linhas que pertencem a um lançamento."""
    dono = {}
    for lancamento in resultado.lancamentos:
        dono[lancamento.linha] = lancamento.numero
        for partida in lancamento.partidas:
            dono[partida.linha] = lancamento.numero
    return dono


def _partidas_da_leitura(lancamento):
    return [
        {
            "linha": partida.linha,
            "codigo_origem": partida.codigo_conta,
            "lado": partida.lado,
            "valor": partida.valor,
            "historico": partida.historico,
        }
        for partida in lancamento.partidas
    ]


def _resumo_das_ocorrencias(ocorrencias):
    return (
        any(o["nivel"] == NIVEL_ERRO for o in ocorrencias),
        any(o["nivel"] == NIVEL_AVISO for o in ocorrencias),
    )


def _gravar_lancamentos(importacao, resultado):
    """Grava as linhas da importação já conferidas, e as ocorrências do arquivo."""
    contexto = _Contexto.carregar(importacao.empresa, importacao.formato)
    dono = _dono_das_linhas(resultado)

    do_arquivo = []
    de_lancamento = defaultdict(list)
    for ocorrencia in resultado.ocorrencias:
        numero = dono.get(ocorrencia.linha) if ocorrencia.linha else None
        if numero is None:
            do_arquivo.append(_ocorrencia_de_leitura(ocorrencia))
        else:
            de_lancamento[numero].append(_ocorrencia_de_leitura(ocorrencia))
    importacao.ocorrencias_do_arquivo = do_arquivo
    importacao.save(update_fields=["ocorrencias_do_arquivo"])

    for lancamento in resultado.lancamentos:
        montado, resolvidas, conferencia = _conferir_lancamento(
            contexto,
            numero=lancamento.numero,
            data=lancamento.data,
            partidas=_partidas_da_leitura(lancamento),
            linha=lancamento.linha,
            historico_do_lancamento=lancamento.historico,
        )
        ocorrencias = de_lancamento.get(lancamento.numero, []) + conferencia
        tem_erro, tem_aviso = _resumo_das_ocorrencias(ocorrencias)
        LancamentoImportado.objects.create(
            importacao=importacao,
            numero_origem=lancamento.numero,
            linha=lancamento.linha,
            data=lancamento.data,
            historico=montado,
            partidas=resolvidas,
            ocorrencias=ocorrencias,
            tem_erro=tem_erro,
            tem_aviso=tem_aviso,
        )


def _recalcular_contagens(importacao):
    linhas = list(importacao.lancamentos.all())
    debitos = Decimal("0.00")
    creditos = Decimal("0.00")
    for linha in linhas:
        for partida in linha.partidas:
            if partida["lado"] == LADO_DEBITO:
                debitos += Decimal(partida["valor"])
            else:
                creditos += Decimal(partida["valor"])
    importacao.quantidade_lancamentos = len(linhas)
    importacao.quantidade_com_erro = sum(1 for linha in linhas if linha.tem_erro)
    importacao.quantidade_com_aviso = sum(1 for linha in linhas if linha.tem_aviso)
    importacao.soma_debitos = debitos
    importacao.soma_creditos = creditos
    importacao.save(
        update_fields=[
            "quantidade_lancamentos",
            "quantidade_com_erro",
            "quantidade_com_aviso",
            "soma_debitos",
            "soma_creditos",
        ]
    )


def _trilha(acao, importacao, usuario, request, detalhes):
    registrar(
        acao=acao,
        objeto=importacao,
        escritorio=importacao.empresa.escritorio,
        usuario=usuario,
        request=request,
        detalhes=detalhes,
    )


def _resumo_para_trilha(importacao):
    """Só contagens, formato, arquivo e política. Nunca o texto dos lançamentos."""
    return {
        "formato": importacao.formato,
        "sha256": importacao.sha256,
        "nome_arquivo": importacao.nome_arquivo,
        "lancamentos": importacao.quantidade_lancamentos,
        "com_erro": importacao.quantidade_com_erro,
        "com_aviso": importacao.quantidade_com_aviso,
        "soma_debitos": str(importacao.soma_debitos),
        "soma_creditos": str(importacao.soma_creditos),
    }


def _viva_com_o_mesmo_arquivo(empresa, sha256):
    return (
        ImportacaoLancamentos.objects.filter(empresa=empresa, sha256=sha256)
        .exclude(estado=EstadoImportacaoLancamentos.DESCARTADA)
        .first()
    )


def _recusar_duplicado(viva):
    return ImportacaoJaExiste(
        f"este arquivo já foi recebido nesta empresa (importação {viva.pk}, "
        f"{EstadoImportacaoLancamentos(viva.estado).label.lower()} em "
        f"{viva.criado_em:%d/%m/%Y %H:%M}). Não é preciso enviá-lo de novo: confira a importação "
        "existente, ou descarte-a para receber o arquivo outra vez.",
        viva.pk,
    )


def receber(*, empresa, formato, conteudo, nome_arquivo="", usuario=None, request=None):
    """Lê e confere o arquivo e grava a importação EM CONFERÊNCIA. Nada entra no Diário.

    Levanta `ImportacaoRecusada` (400) para formato sem leitura, arquivo com CNPJ de outra empresa
    e arquivo acima de 2.000 lançamentos; `ImportacaoJaExiste` (409) se o mesmo arquivo já está
    em conferência ou efetivado; `ArquivoGrandeDemais` (413) acima do limite de tamanho ou linhas.
    """
    _validar_formato(formato)
    _conferir_limites(conteudo)
    sha256 = hashlib.sha256(conteudo).hexdigest()
    viva = _viva_com_o_mesmo_arquivo(empresa, sha256)
    if viva is not None:
        raise _recusar_duplicado(viva)

    resultado = LEITORES_DE_LANCAMENTOS[formato](conteudo)
    documento = resultado.documento_declarado
    if documento is not None and documento != _documento_da_empresa(empresa):
        # Mensagem sem os números: o contador não precisa que o sistema repita o CNPJ de outro.
        raise ImportacaoRecusada(
            "o arquivo declara CNPJ/CPF diferente do da empresa escolhida. Nada foi gravado: "
            "confira se o arquivo é desta empresa."
        )
    if len(resultado.lancamentos) > LIMITE_DE_LANCAMENTOS_POR_ARQUIVO:
        raise ImportacaoRecusada(
            f"o arquivo tem {len(resultado.lancamentos)} lançamentos; o limite por arquivo é "
            f"{LIMITE_DE_LANCAMENTOS_POR_ARQUIVO}. Divida o arquivo por período."
        )

    try:
        with transaction.atomic():
            importacao = ImportacaoLancamentos.objects.create(
                empresa=empresa,
                formato=formato,
                nome_arquivo=os.path.basename(nome_arquivo or "")[:255],
                sha256=sha256,
                criado_por=usuario,
            )
            _gravar_lancamentos(importacao, resultado)
            _recalcular_contagens(importacao)
            _trilha(
                "lancamentos.importacao.recebida",
                importacao,
                usuario,
                request,
                _resumo_para_trilha(importacao),
            )
    except IntegrityError as exc:
        # Duas requisições com o mesmo arquivo: a que perdeu a corrida da restrição única recusa.
        viva = _viva_com_o_mesmo_arquivo(empresa, sha256)
        if viva is None:
            raise
        raise _recusar_duplicado(viva) from exc
    return importacao


def _bloquear_em_conferencia(importacao):
    """Relê a importação com trava de linha e recusa se ela já saiu da conferência."""
    atual = ImportacaoLancamentos.objects.select_for_update().get(pk=importacao.pk)
    if atual.estado != EstadoImportacaoLancamentos.EM_CONFERENCIA:
        raise ImportacaoEmEstadoInvalido(
            f"a importação {atual.pk} já está "
            f"{EstadoImportacaoLancamentos(atual.estado).label.lower()}: "
            "nada foi alterado."
        )
    return atual


def _reconferir_linhas(importacao):
    """Refaz a conferência de cada linha com o cadastro de agora.

    Troca só as ocorrências da conferência; as da leitura ficam.
    """
    contexto = _Contexto.carregar(importacao.empresa, importacao.formato)
    for linha in importacao.lancamentos.select_for_update().order_by("linha", "id"):
        partidas = [
            {
                "linha": p["linha"],
                "codigo_origem": p["codigo_origem"],
                "lado": p["lado"],
                "valor": Decimal(p["valor"]),
                "historico": p["historico"],
            }
            for p in linha.partidas
        ]
        avisos_antes = _assinatura_dos_avisos(linha.ocorrencias)
        montado, resolvidas, conferencia = _conferir_lancamento(
            contexto,
            numero=linha.numero_origem,
            data=linha.data,
            partidas=partidas,
            linha=linha.linha,
        )
        mantidas = [o for o in linha.ocorrencias if o.get("origem") == "leitura"]
        ocorrencias = mantidas + conferencia
        # Aceite é da mudança concreta: se o conjunto de avisos mudou, o aceite antigo não vale.
        if _assinatura_dos_avisos(ocorrencias) != avisos_antes:
            linha.aceito_com_aviso = False
        linha.historico = montado
        linha.partidas = resolvidas
        linha.ocorrencias = ocorrencias
        linha.tem_erro, linha.tem_aviso = _resumo_das_ocorrencias(ocorrencias)
        linha.save(
            update_fields=[
                "historico",
                "partidas",
                "ocorrencias",
                "tem_erro",
                "tem_aviso",
                "aceito_com_aviso",
            ]
        )


def _assinatura_dos_avisos(ocorrencias):
    return sorted(
        (o["linha"], o["campo"], o["mensagem"]) for o in ocorrencias if o["nivel"] == NIVEL_AVISO
    )


def reconferir(importacao, *, usuario=None, request=None):
    """Refaz a conferência com o cadastro atual.

    Use depois de mudar de-para ou reabrir uma competência.
    """
    with transaction.atomic():
        _travar_empresa_para_operacao_de_zeramento(importacao.empresa)
        atual = _bloquear_em_conferencia(importacao)
        _reconferir_linhas(atual)
        _recalcular_contagens(atual)
        _trilha(
            "lancamentos.importacao.reconferida",
            atual,
            usuario,
            request,
            _resumo_para_trilha(atual),
        )
    return atual


def definir_de_para(*, empresa, formato, codigo_origem, conta, usuario=None, request=None):
    """Grava (ou troca) o de-para de um código de origem. Reutilizável em todas as importações."""
    if formato not in LEITORES_DE_LANCAMENTOS:
        raise ImportacaoRecusada(f"formato '{formato}' não tem de-para de lançamentos.")
    codigo = (codigo_origem or "").strip()
    if not codigo or len(codigo) > 100 or "\x00" in codigo:
        raise ImportacaoRecusada(
            "código de origem obrigatório, até 100 caracteres, sem caractere nulo."
        )
    if conta.empresa_id != empresa.pk:
        # A API responde 404 antes de chegar aqui; esta é a defesa do serviço. Vem antes das
        # outras checagens para não dizer nada sobre a conta de outra empresa.
        raise ImportacaoRecusada("a conta não pertence a esta empresa.")
    # O de-para aponta para conta que RECEBE lançamento. Sintética não recebe (regra de
    # `_conferir_lancamento`) e inativa não é usada: gravar um de-para assim só daria erro na
    # próxima conferência, longe de quem o escolheu. A tela já oferece só as analíticas ativas.
    if not conta.aceita_lancamento:
        raise ImportacaoRecusada(
            f"a conta {conta.codigo} é sintética: o de-para aponta só para conta analítica, "
            "que recebe lançamento."
        )
    if not conta.ativo:
        raise ImportacaoRecusada(
            f"a conta {conta.codigo} está inativa: o de-para aponta só para conta ativa."
        )
    with transaction.atomic():
        depara, criado = DeParaConta.objects.update_or_create(
            empresa=empresa,
            formato=formato,
            codigo_origem=codigo,
            defaults={"conta": conta, "criado_por": usuario},
        )
        registrar(
            acao="lancamentos.depara_definido",
            objeto=empresa,
            escritorio=empresa.escritorio,
            usuario=usuario,
            request=request,
            detalhes={
                "formato": formato,
                "codigo_origem": codigo,
                "conta": conta.codigo,
                "criado": criado,
            },
        )
    return depara


def aceitar_avisos(importacao, numeros, *, usuario=None, request=None):
    """Registra que o contador viu e aceitou os avisos dos lançamentos informados (pelo número)."""
    numeros = [str(numero).strip() for numero in numeros if str(numero).strip()]
    if not numeros:
        raise ImportacaoRecusada("informe ao menos um lançamento para aceitar os avisos.")
    with transaction.atomic():
        atual = _bloquear_em_conferencia(importacao)
        linhas = {
            linha.numero_origem: linha
            for linha in atual.lancamentos.select_for_update().filter(numero_origem__in=numeros)
        }
        ausentes = [numero for numero in numeros if numero not in linhas]
        if ausentes:
            raise ImportacaoRecusada(
                f"lançamento(s) {', '.join(ausentes)} não estão nesta importação. Nada foi aceito."
            )
        sem_aviso = [numero for numero in numeros if not linhas[numero].tem_aviso]
        if sem_aviso:
            raise ImportacaoRecusada(
                f"lançamento(s) {', '.join(sem_aviso)} não têm avisos a aceitar. Nada foi aceito."
            )
        for numero in numeros:
            linha = linhas[numero]
            linha.aceito_com_aviso = True
            linha.save(update_fields=["aceito_com_aviso"])
        _trilha(
            "lancamentos.avisos_aceitos",
            atual,
            usuario,
            request,
            {"quantidade": len(numeros), "formato": atual.formato, "sha256": atual.sha256},
        )
    return len(numeros)


def descartar(importacao, *, motivo, usuario=None, request=None):
    """Descarta a importação em conferência, com motivo.

    O arquivo pode ser recebido de novo depois.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ImportacaoRecusada("o motivo do descarte é obrigatório.")
    if len(motivo) > 500:
        raise ImportacaoRecusada("o motivo do descarte tem mais de 500 caracteres.")
    with transaction.atomic():
        atual = _bloquear_em_conferencia(importacao)
        atual.estado = EstadoImportacaoLancamentos.DESCARTADA
        atual.descartada_por = usuario
        atual.descartada_em = timezone.now()
        atual.motivo_do_descarte = motivo
        atual.save()
        _trilha(
            "lancamentos.importacao.descartada", atual, usuario, request, _resumo_para_trilha(atual)
        )
    return atual


def efetivar(importacao, *, politica=TUDO_OU_NADA, usuario=None, request=None):
    """Grava no Diário os lançamentos conferidos, pela política escolhida, numa transação.

    Reconfere antes, sob a trava da empresa (a mesma da aplicação do plano). Cada lançamento
    passa por `criar_lancamento`, com `chave_idempotencia = importacao:<SHA-256>:<número>`.
    Qualquer exceção no meio desfaz tudo: nenhum lançamento fica sem a importação e vice-versa.
    Recusa com `ImportacaoNaoEfetivada` (nada gravado) quando há erro ou aviso não aceito, na
    política tudo ou nada, e quando não há nenhum lançamento para efetivar (arquivo sem lançamento,
    ou, em só os válidos, nenhum pronto).
    """
    if politica not in POLITICAS_DE_EFETIVACAO:
        raise ImportacaoRecusada(
            f"política '{politica}' desconhecida. Use: {', '.join(POLITICAS_DE_EFETIVACAO)}."
        )
    with transaction.atomic():
        _travar_empresa_para_operacao_de_zeramento(importacao.empresa)
        atual = _bloquear_em_conferencia(importacao)
        _reconferir_linhas(atual)
        _recalcular_contagens(atual)
        linhas = list(atual.lancamentos.select_for_update().order_by("linha", "id"))
        erros_do_arquivo = [o for o in atual.ocorrencias_do_arquivo if o["nivel"] == NIVEL_ERRO]

        if politica == TUDO_OU_NADA:
            bloqueios = [dict(o, numero=None) for o in erros_do_arquivo]
            for linha in linhas:
                if linha.tem_erro or (linha.tem_aviso and not linha.aceito_com_aviso):
                    bloqueios += [dict(o, numero=linha.numero_origem) for o in linha.ocorrencias]
            if bloqueios:
                raise ImportacaoNaoEfetivada(
                    "a importação tem erro, ou aviso não aceito: nada foi gravado. "
                    "Corrija o arquivo "
                    "ou o de-para, ou escolha efetivar só os válidos.",
                    bloqueios,
                )
            a_efetivar = linhas
            nao_efetivados = []
        else:
            a_efetivar = [
                linha
                for linha in linhas
                if not linha.tem_erro and (not linha.tem_aviso or linha.aceito_com_aviso)
            ]
            ids = {linha.pk for linha in a_efetivar}
            nao_efetivados = [linha for linha in linhas if linha.pk not in ids]
        if not a_efetivar:
            # Zero para efetivar não é efetivação. Sem esta recusa a importação iria a EFETIVADA
            # com zero lançamentos, e a tela mostraria um "sucesso" vazio. Em tudo_ou_nada o zero
            # só chega aqui com arquivo sem lançamento (erro e aviso já recusaram acima); em
            # so_validos, com nenhum lançamento pronto.
            motivo = (
                "o arquivo não tem lançamento"
                if not linhas
                else "nenhum está pronto (sem erro e com avisos aceitos)"
            )
            raise ImportacaoNaoEfetivada(
                f"não há lançamento para efetivar: {motivo}. Nada foi gravado.",
                [
                    dict(o, numero=linha.numero_origem)
                    for linha in linhas
                    for o in linha.ocorrencias
                ],
            )

        contas = {conta.pk: conta for conta in Conta.objects.filter(empresa=atual.empresa)}
        criados = reaproveitados = 0
        for linha in a_efetivar:
            itens = [
                {
                    "conta": contas[partida["conta_id"]],
                    "tipo": TipoPartida.DEBITO
                    if partida["lado"] == LADO_DEBITO
                    else TipoPartida.CREDITO,
                    "valor": Decimal(partida["valor"]),
                }
                for partida in linha.partidas
            ]
            lancamento = criar_lancamento(
                empresa=atual.empresa,
                data=linha.data,
                historico=linha.historico,
                itens=itens,
                criado_por=usuario,
                chave_idempotencia=f"{PREFIXO_DA_CHAVE}:{atual.sha256}:{linha.numero_origem}",
                permitir_prefixo_da_importacao=True,
            )
            if lancamento.criado_agora:
                criados += 1
            else:
                reaproveitados += 1
            linha.lancamento = lancamento
            linha.save(update_fields=["lancamento"])

        atual.estado = EstadoImportacaoLancamentos.EFETIVADA
        atual.politica_de_efetivacao = politica
        atual.efetivada_por = usuario
        atual.efetivada_em = timezone.now()
        atual.quantidade_efetivados = len(a_efetivar)
        atual.quantidade_nao_efetivados = len(nao_efetivados)
        atual.save()
        _trilha(
            "lancamentos.importacao.efetivada",
            atual,
            usuario,
            request,
            dict(
                _resumo_para_trilha(atual),
                politica=politica,
                criados=criados,
                reaproveitados=reaproveitados,
                nao_efetivados=len(nao_efetivados),
            ),
        )
    return ResultadoDaEfetivacao(
        importacao=atual,
        criados=criados,
        reaproveitados=reaproveitados,
        nao_efetivados=[linha.numero_origem for linha in nao_efetivados],
    )


def listar_importacoes(empresa):
    """Importações da empresa, da mais nova para a mais antiga. Só a empresa pedida."""
    return ImportacaoLancamentos.objects.filter(empresa=empresa).order_by("-criado_em", "-id")
