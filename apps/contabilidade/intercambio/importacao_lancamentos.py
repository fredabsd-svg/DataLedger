"""Importação de lançamentos com área de conferência (DL-077, fatia 3, frente A).

QUATRO OPERAÇÕES, E A SEPARAÇÃO É PROPOSITAL.

1. `receber` LÊ, CONFERE e GRAVA a importação em conferência (`ImportacaoLancamentos`, com
   `LancamentoImportado` por lançamento). NADA entra no Diário.
2. `reconferir` refaz a conferência com o cadastro atual (de-para, competências, contas, Diário).
   É o que o contador roda depois de mudar um de-para ou reabrir uma competência.
3. `definir_de_para` e `aceitar_avisos` são as decisões do contador, gravadas na trilha.
4. `efetivar` é a ÚNICA operação que grava no Diário. Reconfere, decide pela política (hoje só
   tudo ou nada; a efetivação parcial está suspensa, BL-676), e chama `criar_lancamento` um a um,
   numa transação. Uma falha no meio desfaz tudo. A chave de idempotência é
   `importacao:<SHA-256>:<número de origem>`: o SHA-256 faz com que o mesmo número em outro arquivo
   NÃO colida, e o prefixo é reservado
   (`criar_lancamento` recusa `importacao:` sem o parâmetro `permitir_prefixo_da_importacao`).

REGRAS DE CONFERÊNCIA (por lançamento; erro nunca efetiva, aviso só efetiva se aceito):
- débitos = créditos; ao menos um débito e um crédito; valor > 0 com no máximo 2 casas e menor
  que 10^16 (o campo do Diário, `max_digits=18`);
- no máximo 200 partidas por lançamento (`LIMITE_PARTIDAS_POR_LANCAMENTO`), como `criar_lancamento`;
- data válida na faixa do RC-77 (`validar_data_de_lancamento`);
- competência da data ABERTA. Competência inexistente é aberta: é o que `criar_lancamento`
  faz (`obter_ou_criar_competencia`). Encerrada ou entregue é erro;
- conta: pelo código exato do plano da empresa (formatos ECD, próprio e Excel); senão pelo
  de-para (`DeParaConta`). No sistema de referência o código é o REDUZIDO, que o DataLedger não
  tem: só o de-para resolve. Sem resolução é erro que nomeia o código de origem. Conta precisa
  ser da empresa, analítica (`aceita_lancamento`) e ativa;
- histórico: as partidas com o mesmo texto geram esse texto; textos diferentes são
  concatenados com ' | ' e geram AVISO. Mais de 300 caracteres é erro: nunca se trunca. Caractere
  nulo é erro;
- número repetido e número acima de 100 caracteres: erro;
- JÁ NO DIÁRIO: lançamento com a mesma data, histórico e partidas de um lançamento efetivado
  desta empresa gera AVISO (campo `duplicidade`), que exige aceite. Compara só com o Diário, nunca
  dentro do mesmo arquivo, e com duas consultas para o arquivo inteiro;
- CNPJ/CPF declarado no arquivo diferente da empresa: recusa do arquivo INTEIRO, com mensagem
  sem os números.

O QUE `criar_lancamento` RECUSA e a conferência replica (lista completa, DL-077 A4): livro-caixa
(empresa recusada inteira), menos de 2 partidas, mais de 200 partidas, data fora da faixa, histórico
com caractere nulo, valor não positivo, mais de 2 casas decimais, débitos diferentes de créditos,
total zero, conta de outra empresa, conta sintética, competência não aberta. A conferência recusa
também o que o Diário não comporta (valor de 10^16 ou mais) e a conta inativa, que
`criar_lancamento` aceita. Chave com prefixo `importacao:` é reservada ao próprio serviço.

ERROS DO ARQUIVO (A1, R1 e R2 da reconferência). Todo erro do arquivo, de lançamento ou não,
recusa a efetivação. Um erro que o leitor não consegue atribuir a um lançamento (número ilegível,
registro desconhecido dentro de um lote) deixa o lançamento vizinho incompleto, e a política não
tem como saber qual é. Nada é efetivado com erro.

POLÍTICAS DE EFETIVAÇÃO. Só `tudo_ou_nada`: qualquer erro, qualquer aviso não aceito, ou erro do
arquivo recusa a efetivação inteira. A política `so_validos` (efetivar só os prontos) está SUSPENSA
(BL-676): falhou duas vezes em gravar lançamento incompleto no Diário, que é imutável. Quem a pede
recebe `ImportacaoNaoEfetivada` com a mensagem nomeada.

AVISO DO ARQUIVO SEM EMPRESA (A11). Arquivo que não declara a empresa (ECD sem 0000, formato
próprio, Excel) recebe o aviso "o arquivo não declara a empresa". Ele exige o aceite do contador
(`aceitar_avisos(..., aceitar_arquivo=True)`) antes de efetivar, nas duas políticas.

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
    Ocorrencia,
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
    ItemLancamento,
    LancamentoContabil,
    LancamentoImportado,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import (
    LancamentoInvalido,
    _travar_empresa_para_operacao_de_zeramento,
    criar_lancamento,
    validar_data_de_lancamento,
)
from apps.contabilidade.validators import LIMITE_PARTIDAS_POR_LANCAMENTO
from apps.empresas.services import EmpresaEmModoLivroCaixa, recusar_se_livro_caixa

FORMATO_REFERENCIA = FormatoImportacaoLancamentos.REFERENCIA

# Leitores de LANÇAMENTOS. Cada um recebe os bytes e devolve `ResultadoLeitura` com
# `lancamentos`. O leitor do plano (`formatos.LEITORES`) é outra coisa, e não entra aqui.
LEITORES_DE_LANCAMENTOS = {
    FormatoImportacaoLancamentos.ECD: ecd_lancamentos_leitura.ler,
    FormatoImportacaoLancamentos.PROPRIO: proprio_lancamentos_leitura.ler,
    FormatoImportacaoLancamentos.EXCEL: excel_lancamentos.ler,
    FormatoImportacaoLancamentos.REFERENCIA: referencia_lancamentos_leitura.ler,
}

# Formatos de TEXTO: o byte nulo nunca é conteúdo deles (A2). No Excel (um .xlsx, que é zip) o
# byte nulo é normal, e a planilha é conferida pelo próprio leitor.
FORMATOS_DE_TEXTO = (
    FormatoImportacaoLancamentos.ECD,
    FormatoImportacaoLancamentos.PROPRIO,
    FormatoImportacaoLancamentos.REFERENCIA,
)

# Limite de lançamentos por arquivo. MEDIDO (2026-10-08, PostgreSQL, dados sintéticos, plano do
# cenário de exportação): efetivar custa ~10,7 ms por lançamento, em ~18 consultas, e cresce de
# forma linear: 1.000 = 10,9 s; 2.000 = 21,5 s; 5.000 = 54,4 s; 20.000 = 214 s. Receber 20.000
# leva 38 s. O gunicorn do Dockerfile corta a requisição em 30 s (sem --workers). Por isso o teto
# é 2.000: a efetivação nele cabe em ~25 s. Acima disso a recusa é nomeada, nunca truncada.
LIMITE_DE_LANCAMENTOS_POR_ARQUIVO = 2_000

# A3: teto de PARTIDAS por arquivo, além do teto de lançamentos. Efetivar custa por partida
# (`criar_lancamento` grava cada uma). MEDIDO em 2026-10-08, mesma máquina, consultas contadas por
# `execute_wrapper`: 2.000 x 2 = 17,2 s e 1.000 x 4 = 9,4 s; antes da correção, 20,3 s e 11,4 s.
# 500 x 200 (100.000 partidas) passou de 82 s na auditoria e morreu no gunicorn aos 30 s. O teto de
# 4.000 mantém qualquer arquivo aceito abaixo do corte do servidor.
LIMITE_DE_PARTIDAS_POR_ARQUIVO = 4_000

# A8: o que se GUARDA e se mostra das ocorrências do arquivo. A contagem total fica à parte.
LIMITE_DE_OCORRENCIAS_GUARDADAS = 500

# A9: o campo `valor` do Diário tem `max_digits=18` e 2 casas: o maior é 9.999.999.999.999.999,99.
# Um valor de 10^16 ou mais não cabe e vira erro de conferência, nunca um 500 na gravação.
LIMITE_MAGNITUDE_VALOR = Decimal(10) ** 16

# Campos de erro que são do ARQUIVO INTEIRO (A1). `0000*` = o leitor não conseguiu conferir a
# empresa; `codificacao`, `cabecalho`, `estrutura`, `linha` e `REG` = a leitura parou ou ficou com
# a estrutura quebrada. Um lançamento lido em arquivo assim pode estar incompleto (uma partida
# perdida pode deixar o lançamento equilibrado por acaso), então NENHUMA política grava com eles.
# Todo erro bloqueia a efetivação (R1 e R2 da reconferência). Esta lista separa, na tela e nos
# totais, o erro do ARQUIVO INTEIRO do erro de um lançamento.
CAMPOS_DE_ERRO_DO_ARQUIVO = frozenset(
    {"0000", "0000.2", "0000.6", "codificacao", "cabecalho", "estrutura", "linha", "REG"}
)

# A11: aviso de arquivo sem declaração da empresa, que exige aceite antes de efetivar.
CAMPO_DA_EMPRESA = "empresa"
MENSAGEM_EMPRESA_NAO_DECLARADA = (
    "o arquivo não declara a empresa: confirme que ele é desta empresa."
)

TAMANHO_MAXIMO_HISTORICO = LancamentoContabil._meta.get_field("historico").max_length
TAMANHO_MAXIMO_NUMERO = 100  # a chave `importacao:<64>:<número>` cabe em 255 com folga
PREFIXO_DA_CHAVE = "importacao"
SEPARADOR_DE_HISTORICO = " | "
CENTAVO = Decimal("0.01")

TUDO_OU_NADA = "tudo_ou_nada"
# SUSPENSA (BL-676). A constante fica só para a recusa nomeada: nenhuma gravação usa esta política.
SO_VALIDOS = "so_validos"
POLITICAS_DE_EFETIVACAO = (TUDO_OU_NADA,)
MENSAGEM_SO_VALIDOS_SUSPENSA = (
    "a efetivação parcial ('só os válidos') está suspensa: corrija ou descarte os lançamentos com "
    "erro e efetive tudo — BL-676"
)

MENSAGEM_ARQUIVO_BLOQUEADO = (
    "o arquivo tem erro que impede a efetivação, ou o aviso de empresa "
    "não foi aceito. Nada foi gravado. Corrija o arquivo ou aceite o aviso."
)
MENSAGEM_LANCAMENTO_BLOQUEADO = (
    "a importação tem erro, ou aviso não aceito: nada foi gravado. Corrija o arquivo ou o de-para "
    "e reconfira, ou descarte a importação."
)

_NAO_ALFANUMERICO = re.compile(r"[^0-9A-Z]")
_PADRAO_EXTENSAO = re.compile(r"\.[a-z0-9]{1,10}")


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
    """Erro ou aviso sem aceite, ou erro do arquivo inteiro: nada gravado. Ver `ocorrencias`."""

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


def _recusar_livro_caixa(empresa):
    """Empresa em livro-caixa não recebe lançamento (a recusa de `criar_lancamento`, DL-038)."""
    try:
        recusar_se_livro_caixa(empresa)
    except EmpresaEmModoLivroCaixa as exc:
        raise ImportacaoRecusada(exc.mensagem) from exc


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


def _escapar_controle(texto):
    """Caractere de controle vira `\\uXXXX` na mensagem (A2).

    A mensagem ecoa valor lido do arquivo. Sem isto, um byte de controle chegava ao JSON da
    conferência e à tela como caractere cru.
    """
    return "".join(
        f"\\u{ord(caractere):04x}" if ord(caractere) < 32 else caractere for caractere in texto
    )


def _ocorrencia(linha, campo, nivel, mensagem, origem):
    return {
        "linha": linha,
        "campo": campo,
        "nivel": nivel,
        "mensagem": _escapar_controle(mensagem),
        "origem": origem,
    }


def _ocorrencia_de_leitura(ocorrencia):
    return _ocorrencia(
        ocorrencia.linha, ocorrencia.campo, ocorrencia.nivel, ocorrencia.mensagem, "leitura"
    )


def _cabe_no_campo(valor):
    """Valor que o Diário comporta: abaixo de 10^16 em módulo (A9)."""
    return abs(valor) < LIMITE_MAGNITUDE_VALOR


def erro_do_arquivo_inteiro(ocorrencia):
    """Erro que bloqueia as duas políticas (A1): linha 0 (arquivo inteiro) ou campo estrutural."""
    return ocorrencia["nivel"] == NIVEL_ERRO and (
        ocorrencia["linha"] == 0 or ocorrencia["campo"] in CAMPOS_DE_ERRO_DO_ARQUIVO
    )


def _extensao_do_arquivo(nome_arquivo):
    """Só a extensão (`.txt`). O nome pode trazer CNPJ ou nome de cliente: a trilha não o guarda."""
    extensao = os.path.splitext(nome_arquivo or "")[1].lower()
    return extensao if _PADRAO_EXTENSAO.fullmatch(extensao) else ""


def _nome_guardado(nome_arquivo):
    """Só o nome, sem caminho e sem caractere de controle, em até 255 caracteres (A2)."""
    base = os.path.basename(nome_arquivo or "")
    return "".join(caractere for caractere in base if ord(caractere) >= 32)[:255]


@dataclass
class _Contexto:
    """O cadastro que a conferência consulta: contas, de-para, competências e o Diário."""

    empresa: object
    formato: str
    contas: dict
    depara: dict
    competencias: dict
    diario: dict

    @classmethod
    def carregar(cls, empresa, formato, datas=()):
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
            diario=_diario_da_empresa(empresa, set(datas)),
        )

    def resolver_conta(self, codigo_origem):
        """(conta, 'codigo' | 'depara') ou (None, None). Código exato do plano vence o de-para."""
        if codigo_origem in self.contas:
            return self.contas[codigo_origem], "codigo"
        conta = self.depara.get(codigo_origem)
        if conta is not None:
            return conta, "depara"
        return None, None


def _assinatura_das_partidas(partidas):
    """Partidas como multiconjunto comparável: (conta, lado, valor com 2 casas)."""
    return tuple(
        sorted(
            (conta_id, lado, str(Decimal(valor).quantize(CENTAVO)))
            for conta_id, lado, valor in partidas
        )
    )


def _diario_da_empresa(empresa, datas):
    """{(data, histórico): {assinatura: número do lançamento}} do Diário da empresa nessas datas.

    Duas consultas para o arquivo inteiro, qualquer que seja o número de lançamentos (A5): não há
    consulta por lançamento. Só lançamento já efetivado (LancamentoContabil) entra; o arquivo que
    está sendo conferido nunca é comparado com ele mesmo.
    """
    if not datas:
        return {}
    partidas = defaultdict(list)
    itens = ItemLancamento.objects.filter(
        lancamento__empresa=empresa, lancamento__data__in=datas
    ).values_list("lancamento_id", "conta_id", "tipo", "valor")
    for lancamento_id, conta_id, tipo, valor in itens:
        partidas[lancamento_id].append((conta_id, tipo, valor))
    diario = defaultdict(dict)
    cabecalhos = LancamentoContabil.objects.filter(empresa=empresa, data__in=datas).values_list(
        "pk", "data", "historico"
    )
    for pk, data, historico in cabecalhos:
        assinatura = _assinatura_das_partidas(partidas.get(pk, ()))
        diario[(data, historico)].setdefault(assinatura, pk)
    return dict(diario)


def _conferir_lancamento(contexto, *, numero, data, partidas, linha, historico_do_lancamento=""):
    """Confere um lançamento contra o cadastro e o Diário. Não grava.

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

    # `criar_lancamento` recusa menos de 2 e mais de 200 partidas (RC-79): a conferência recusa
    # antes, para o contador ver o erro na lista e não na efetivação.
    if len(partidas) < 2:
        erro("partidas", "um lançamento precisa de ao menos duas partidas.")
    elif len(partidas) > LIMITE_PARTIDAS_POR_LANCAMENTO:
        erro(
            "partidas",
            f"um lançamento aceita no máximo {LIMITE_PARTIDAS_POR_LANCAMENTO} partidas; o arquivo "
            f"traz {len(partidas)}. Divida o lançamento no arquivo: nenhuma partida foi gravada.",
        )
    lados = {p["lado"] for p in partidas}
    if LADO_DEBITO not in lados or LADO_CREDITO not in lados:
        erro("partidas", "o lançamento precisa de ao menos um débito e um crédito.")

    resolvidas = []
    soma = {LADO_DEBITO: Decimal("0.00"), LADO_CREDITO: Decimal("0.00")}
    for partida in partidas:
        valor = partida["valor"]
        if valor <= 0:
            erro("valor", f"valor {valor} não é positivo.", partida["linha"])
        elif not _cabe_no_campo(valor):
            # A9: o Diário não comporta o valor. Erro de conferência, nunca truncagem nem 500.
            erro(
                "valor",
                f"valor {valor} não cabe no Diário (o máximo é 9.999.999.999.999.999,99). "
                "Nada foi truncado: corrija o valor no arquivo.",
                partida["linha"],
            )
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
            if conta.empresa_id != contexto.empresa.pk:
                # Defesa: o cadastro carregado já é o da empresa; `criar_lancamento` recusa igual.
                erro("conta", "a conta não pertence a esta empresa.", partida["linha"])
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
    if soma[LADO_DEBITO] <= 0:
        erro("valores", "o lançamento precisa ter valor maior que zero.")

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
    if "\x00" in montado:
        erro(
            "historico",
            "histórico com caractere nulo (código 0): o Diário não grava esse caractere.",
        )
    if len(montado) > TAMANHO_MAXIMO_HISTORICO:
        erro(
            "historico",
            f"histórico com {len(montado)} caracteres; o máximo é {TAMANHO_MAXIMO_HISTORICO}. Nada "
            "foi truncado: encurte o texto no arquivo.",
        )

    # A5: o mesmo lançamento já no Diário desta empresa. Só se o lançamento está limpo: com erro
    # ele não vai para o Diário de qualquer forma, e o aviso só confundiria a conferência.
    if not any(o["nivel"] == NIVEL_ERRO for o in ocorrencias):
        assinatura = _assinatura_das_partidas(
            (p["conta_id"], p["lado"], p["valor"]) for p in resolvidas
        )
        existente = contexto.diario.get((data, montado), {}).get(assinatura)
        if existente is not None:
            aviso(
                "duplicidade",
                f"já existe lançamento igual no Diário desta empresa (lançamento {existente}): "
                "mesma data, histórico e partidas. Aceite só se for outro lançamento legítimo.",
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


def _prioridade_na_guarda(ocorrencia):
    """Ordem de guarda: erro do arquivo inteiro, outro erro, depois os avisos (A8)."""
    if erro_do_arquivo_inteiro(ocorrencia):
        return 0
    if ocorrencia["nivel"] == NIVEL_ERRO:
        return 1
    return 2


def _guardar_ocorrencias_do_arquivo(importacao, do_arquivo):
    """Totais sobre a lista INTEIRA; a guardada tem no máximo `LIMITE_DE_OCORRENCIAS_GUARDADAS`.

    Os totais decidem a efetivação, e nunca a lista cortada. O aviso de empresa não declarada vira
    `exige_aceite_do_arquivo`, que também não depende do corte.
    """
    importacao.quantidade_ocorrencias_do_arquivo = len(do_arquivo)
    importacao.quantidade_erros_do_arquivo = sum(1 for o in do_arquivo if o["nivel"] == NIVEL_ERRO)
    importacao.quantidade_erros_do_arquivo_inteiro = sum(
        1 for o in do_arquivo if erro_do_arquivo_inteiro(o)
    )
    importacao.exige_aceite_do_arquivo = any(
        o["campo"] == CAMPO_DA_EMPRESA and o["nivel"] == NIVEL_AVISO for o in do_arquivo
    )
    guardadas = sorted(do_arquivo, key=lambda o: (_prioridade_na_guarda(o), o["linha"], o["campo"]))
    importacao.ocorrencias_do_arquivo = guardadas[:LIMITE_DE_OCORRENCIAS_GUARDADAS]


def _gravar_lancamentos(importacao, resultado):
    """Grava as linhas da importação já conferidas, e as ocorrências do arquivo."""
    contexto = _Contexto.carregar(
        importacao.empresa, importacao.formato, {lanc.data for lanc in resultado.lancamentos}
    )
    dono = _dono_das_linhas(resultado)

    do_arquivo = []
    de_lancamento = defaultdict(list)
    for ocorrencia in resultado.ocorrencias:
        numero = dono.get(ocorrencia.linha) if ocorrencia.linha else None
        if numero is None:
            do_arquivo.append(_ocorrencia_de_leitura(ocorrencia))
        else:
            de_lancamento[numero].append(_ocorrencia_de_leitura(ocorrencia))
    _guardar_ocorrencias_do_arquivo(importacao, do_arquivo)
    importacao.save(
        update_fields=[
            "ocorrencias_do_arquivo",
            "quantidade_ocorrencias_do_arquivo",
            "quantidade_erros_do_arquivo",
            "quantidade_erros_do_arquivo_inteiro",
            "exige_aceite_do_arquivo",
        ]
    )

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
    """Contagens e somas LIDAS. Partida que o Diário não comporta não entra na soma (já é erro)."""
    linhas = list(importacao.lancamentos.all())
    debitos = Decimal("0.00")
    creditos = Decimal("0.00")
    for linha in linhas:
        for partida in linha.partidas:
            valor = Decimal(partida["valor"])
            if not _cabe_no_campo(valor):
                continue
            if partida["lado"] == LADO_DEBITO:
                debitos += valor
            else:
                creditos += valor
    if not (_cabe_no_campo(debitos) and _cabe_no_campo(creditos)):
        # A9: a SOMA do arquivo também tem de caber no resumo. Recusa nomeada, sem gravar nada.
        raise ImportacaoRecusada(
            "a soma dos débitos ou dos créditos do arquivo passa de 9.999.999.999.999.999,99, "
            "que o resumo não comporta. Nada foi gravado: divida o arquivo por período."
        )
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
    """Só contagens, formato, SHA-256, extensão e somas LIDAS. Nunca o nome, o texto ou o CNPJ."""
    return {
        "formato": importacao.formato,
        "sha256": importacao.sha256,
        "extensao": _extensao_do_arquivo(importacao.nome_arquivo),
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

    Levanta `ImportacaoRecusada` (400) para formato sem leitura, empresa em livro-caixa, byte nulo
    em arquivo de texto, arquivo com CNPJ de outra empresa, arquivo acima de 2.000 lançamentos ou
    de 4.000 partidas, e soma que o resumo não comporta; `ImportacaoJaExiste` (409) se o mesmo
    arquivo já está em conferência ou efetivado; `ArquivoGrandeDemais` (413) acima do limite de
    tamanho ou linhas.
    """
    _validar_formato(formato)
    _recusar_livro_caixa(empresa)
    _conferir_limites(conteudo)
    # A2: o byte nulo não é conteúdo de texto. Recusa nomeada, antes de qualquer leitura: sem isto
    # o PostgreSQL recusa o JSON da conferência com um 500 cru.
    if formato in FORMATOS_DE_TEXTO and b"\x00" in conteudo:
        raise ImportacaoRecusada(
            "o arquivo tem byte nulo (código 0), que não existe em arquivo de texto. Nada foi "
            "gravado: confira se o arquivo não está corrompido e se é mesmo do formato escolhido."
        )
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
    partidas = sum(len(lanc.partidas) for lanc in resultado.lancamentos)
    if partidas > LIMITE_DE_PARTIDAS_POR_ARQUIVO:
        raise ImportacaoRecusada(
            f"o arquivo tem {partidas} partidas; o limite por arquivo é "
            f"{LIMITE_DE_PARTIDAS_POR_ARQUIVO}. Divida o arquivo por período."
        )
    if documento is None:
        # A11: o arquivo não declara a empresa. Aviso de arquivo inteiro (linha 0) que exige aceite.
        resultado.ocorrencias.append(
            Ocorrencia(0, CAMPO_DA_EMPRESA, NIVEL_AVISO, MENSAGEM_EMPRESA_NAO_DECLARADA)
        )

    try:
        with transaction.atomic():
            importacao = ImportacaoLancamentos.objects.create(
                empresa=empresa,
                formato=formato,
                nome_arquivo=_nome_guardado(nome_arquivo),
                sha256=sha256,
                criado_por=usuario,
            )
            _gravar_lancamentos(importacao, resultado)
            _recalcular_contagens(importacao)
            # R2 (reconferência): os registros que a leitura ignorou (contados) vão para a trilha,
            # como o plano faz. A importação não tem campo para eles, e criar um exigiria migração.
            _trilha(
                "lancamentos.importacao.recebida",
                importacao,
                usuario,
                request,
                dict(
                    _resumo_para_trilha(importacao),
                    registros_ignorados=dict(resultado.registros_ignorados),
                ),
            )
    except IntegrityError as exc:
        # Duas requisições com o mesmo arquivo: a que perdeu a corrida da restrição única recusa.
        viva = _viva_com_o_mesmo_arquivo(empresa, sha256)
        if viva is None:
            raise
        raise _recusar_duplicado(viva) from exc
    # Atributo EM MEMÓRIA, não gravado: a resposta do envio (API e tela) mostra os registros
    # ignorados, como a prévia do plano. Depois do envio, quem os quer lê a trilha.
    importacao.registros_ignorados_da_leitura = dict(resultado.registros_ignorados)
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

    Troca só as ocorrências da conferência; as da leitura ficam. Uma linha só é regravada se a
    conferência mudou o que está guardado (A3): a reconferência de uma importação sem mudança
    não custa um UPDATE por lançamento.
    """
    linhas = list(importacao.lancamentos.select_for_update().order_by("linha", "id"))
    contexto = _Contexto.carregar(
        importacao.empresa, importacao.formato, {linha.data for linha in linhas}
    )
    for linha in linhas:
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
        aceito = linha.aceito_com_aviso
        if _assinatura_dos_avisos(ocorrencias) != avisos_antes:
            aceito = False
        tem_erro, tem_aviso = _resumo_das_ocorrencias(ocorrencias)
        novo = (montado, resolvidas, ocorrencias, tem_erro, tem_aviso, aceito)
        atual = (
            linha.historico,
            linha.partidas,
            linha.ocorrencias,
            linha.tem_erro,
            linha.tem_aviso,
            linha.aceito_com_aviso,
        )
        if novo == atual:
            continue
        linha.historico = montado
        linha.partidas = resolvidas
        linha.ocorrencias = ocorrencias
        linha.tem_erro = tem_erro
        linha.tem_aviso = tem_aviso
        linha.aceito_com_aviso = aceito
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

    Use depois de mudar de-para, reabrir uma competência ou entrar um lançamento igual no Diário.
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


def aceitar_avisos(importacao, numeros, *, aceitar_arquivo=False, usuario=None, request=None):
    """Registra o aceite dos avisos dos lançamentos (pelo número) e/ou do arquivo.

    `aceitar_arquivo=True` aceita o aviso "o arquivo não declara a empresa" (A11). Sem nenhum dos
    dois, a operação é recusada. Devolve a quantidade de lançamentos aceitos.
    """
    numeros = [str(numero).strip() for numero in numeros if str(numero).strip()]
    # R3: número com byte nulo não é consultado (o banco recusaria com 500). Nada é aceito.
    if any("\x00" in numero for numero in numeros):
        raise ImportacaoRecusada(
            "número de lançamento com caractere nulo (código 0). Nada foi aceito."
        )
    if not numeros and not aceitar_arquivo:
        raise ImportacaoRecusada(
            "informe ao menos um lançamento, ou o aceite do aviso do arquivo, para aceitar."
        )
    with transaction.atomic():
        atual = _bloquear_em_conferencia(importacao)
        if numeros:
            linhas = {
                linha.numero_origem: linha
                for linha in atual.lancamentos.select_for_update().filter(numero_origem__in=numeros)
            }
            ausentes = [numero for numero in numeros if numero not in linhas]
            if ausentes:
                raise ImportacaoRecusada(
                    f"lançamento(s) {', '.join(ausentes)} não estão nesta importação. "
                    "Nada foi aceito."
                )
            sem_aviso = [numero for numero in numeros if not linhas[numero].tem_aviso]
            if sem_aviso:
                raise ImportacaoRecusada(
                    f"lançamento(s) {', '.join(sem_aviso)} não têm avisos a aceitar. "
                    "Nada foi aceito."
                )
            for numero in numeros:
                linha = linhas[numero]
                linha.aceito_com_aviso = True
                linha.save(update_fields=["aceito_com_aviso"])
        if aceitar_arquivo:
            if not atual.exige_aceite_do_arquivo:
                raise ImportacaoRecusada(
                    "este arquivo não tem aviso de empresa para aceitar. Nada foi aceito."
                )
            atual.aceite_do_arquivo = True
            atual.save(update_fields=["aceite_do_arquivo"])
        _trilha(
            "lancamentos.avisos_aceitos",
            atual,
            usuario,
            request,
            {
                "quantidade": len(numeros),
                "arquivo": bool(aceitar_arquivo),
                "formato": atual.formato,
                "sha256": atual.sha256,
            },
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
    # R3: o PostgreSQL não grava byte nulo em texto. Sem esta recusa, o motivo dava 500.
    if "\x00" in motivo:
        raise ImportacaoRecusada(
            "o motivo do descarte tem caractere nulo (código 0), que o banco não grava. "
            "Nada foi descartado."
        )
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


def _erros_que_bloqueiam(importacao):
    """Todo erro do ARQUIVO (linha sem dono de lançamento): bloqueia a efetivação (R1 e R2).

    Decidido pela lista guardada, que basta: a guarda põe os erros do arquivo na frente dos avisos
    (`_prioridade_na_guarda`); havendo erro, a lista cortada tem pelo menos um.
    """
    return [
        dict(o, numero=None) for o in importacao.ocorrencias_do_arquivo if o["nivel"] == NIVEL_ERRO
    ]


def _aceite_do_arquivo_pendente(importacao):
    return importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo


def _bloqueio_do_aceite_do_arquivo():
    return {
        "linha": 0,
        "campo": CAMPO_DA_EMPRESA,
        "nivel": NIVEL_AVISO,
        "mensagem": MENSAGEM_EMPRESA_NAO_DECLARADA,
        "origem": "conferencia",
        "numero": None,
    }


def efetivar(importacao, *, politica=TUDO_OU_NADA, usuario=None, request=None):
    """Grava no Diário os lançamentos conferidos, em tudo ou nada, numa transação.

    Reconfere antes, sob a trava da empresa (a mesma da aplicação do plano). Cada lançamento
    passa por `criar_lancamento`, com `chave_idempotencia = importacao:<SHA-256>:<número>`.
    Qualquer exceção no meio desfaz tudo: nenhum lançamento fica sem a importação e vice-versa.
    Recusa com `ImportacaoNaoEfetivada` (nada gravado) quando há erro do arquivo ou de lançamento,
    aviso sem aceite, aviso de empresa sem aceite, ou nenhum lançamento para efetivar. A política
    `so_validos` é recusada com mensagem própria: está suspensa (BL-676).

    Grava na importação a soma dos lançamentos EFETIVADOS (A7), separada da soma lida do arquivo.
    """
    if politica == SO_VALIDOS:
        # BL-676: a efetivação parcial falhou duas vezes em gravar lançamento incompleto num Diário
        # imutável. Enquanto estiver suspensa, a recusa vem antes de qualquer leitura ou trava.
        raise ImportacaoNaoEfetivada(MENSAGEM_SO_VALIDOS_SUSPENSA)
    if politica not in POLITICAS_DE_EFETIVACAO:
        raise ImportacaoRecusada(
            f"política '{politica}' desconhecida. Use: {', '.join(POLITICAS_DE_EFETIVACAO)}."
        )
    with transaction.atomic():
        _travar_empresa_para_operacao_de_zeramento(importacao.empresa)
        atual = _bloquear_em_conferencia(importacao)
        _recusar_livro_caixa(atual.empresa)
        _reconferir_linhas(atual)
        _recalcular_contagens(atual)
        linhas = list(atual.lancamentos.select_for_update().order_by("linha", "id"))
        # Ordem das recusas (fixa, e testada): erro do arquivo; arquivo sem lançamento; aviso de
        # empresa sem aceite; erro ou aviso de lançamento. Erro do arquivo vem antes do zero: um
        # arquivo com erro não é lido como "vazio".
        erros_do_arquivo = _erros_que_bloqueiam(atual)
        bloqueios_de_lancamento = []
        for linha in linhas:
            if linha.tem_erro or (linha.tem_aviso and not linha.aceito_com_aviso):
                bloqueios_de_lancamento += [
                    dict(o, numero=linha.numero_origem) for o in linha.ocorrencias
                ]
        if erros_do_arquivo:
            raise ImportacaoNaoEfetivada(
                MENSAGEM_ARQUIVO_BLOQUEADO, erros_do_arquivo + bloqueios_de_lancamento
            )
        if not linhas:
            # Zero para efetivar não é efetivação: sem esta recusa a importação iria a EFETIVADA
            # com zero lançamentos, e a tela mostraria um "sucesso" vazio.
            raise ImportacaoNaoEfetivada(
                "não há lançamento para efetivar: o arquivo não tem lançamento. Nada foi gravado.",
                [],
            )
        if _aceite_do_arquivo_pendente(atual):
            raise ImportacaoNaoEfetivada(
                MENSAGEM_ARQUIVO_BLOQUEADO,
                [_bloqueio_do_aceite_do_arquivo()] + bloqueios_de_lancamento,
            )
        if bloqueios_de_lancamento:
            raise ImportacaoNaoEfetivada(MENSAGEM_LANCAMENTO_BLOQUEADO, bloqueios_de_lancamento)
        # Tudo ou nada: nenhum lançamento fica de fora. `nao_efetivados` continua na forma do
        # resultado (contrato da API), sempre vazia enquanto a efetivação parcial estiver suspensa.
        a_efetivar = linhas
        nao_efetivados = []

        contas = {conta.pk: conta for conta in Conta.objects.filter(empresa=atual.empresa)}
        criados = reaproveitados = 0
        soma_debitos = Decimal("0.00")
        soma_creditos = Decimal("0.00")
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
            for item in itens:
                if item["tipo"] == TipoPartida.DEBITO:
                    soma_debitos += item["valor"]
                else:
                    soma_creditos += item["valor"]
            # DL-089 (BL-72): a origem `importacao` e o documento (o lote, pelo id da
            # importação) são gravados aqui, no único caminho que passa o prefixo
            # reservado. A API e a tela não informam nenhum dos dois.
            lancamento = criar_lancamento(
                empresa=atual.empresa,
                data=linha.data,
                historico=linha.historico,
                itens=itens,
                criado_por=usuario,
                chave_idempotencia=f"{PREFIXO_DA_CHAVE}:{atual.sha256}:{linha.numero_origem}",
                permitir_prefixo_da_importacao=True,
                origem=OrigemLancamento.IMPORTACAO,
                documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, atual.pk),
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
        atual.soma_debitos_efetivados = soma_debitos
        atual.soma_creditos_efetivados = soma_creditos
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
                quantidade_efetivados=len(a_efetivar),
                soma_debitos_efetivados=str(soma_debitos),
                soma_creditos_efetivados=str(soma_creditos),
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
