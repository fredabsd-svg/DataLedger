"""Exportação de lançamentos e saldos (DL-077, fatia 2).

Uma função de entrada, `exportar_lancamentos`, que faz, nesta ordem:

1. valida os parâmetros (formato, intervalo de até um ano, saldo só com mês inteiro e só
   na ECD, omissão só no sistema de referência);
2. lê os lançamentos do intervalo DA EMPRESA, com as partidas, em uma consulta;
3. recusa o que não fecha no leiaute (conta não analítica ou com subordinadas, na ECD);
4. para a ECD com `incluir_saldos`, lê os saldos mês a mês pelo BALANCETE existente
   (`apurar_balancete`), que é a única regra de saldo do produto, e não recalcula saldo;
5. confere que os saldos conciliam com os lançamentos (débitos e créditos);
6. escreve no formato pedido e monta o relatório de conferência, com o SHA-256 do arquivo.

Esta função não grava nada no banco. Quem chama (API e tela) é quem registra a trilha
`lancamentos.exportados`, e só depois que o arquivo foi entregue.

REGRAS DA FATIA 2 (plano DL-077, consulta do contador-senior de 08/10/2026):
- Intervalo obrigatório, com data inicial não posterior à final, e no máximo um ano
  (366 dias corridos, contando os dois dias do intervalo). Acima disso, recusa nomeada.
- Lançamento de estorno sai como lançamento normal, com o próprio histórico.
- Lançamento de zeramento (DL-043) sai marcado: na ECD, IND_LCTO = E. Identificado pelo
  prefixo `zeramento:<empresa>:` da chave de idempotência, o mesmo que `services.py` usa.
- Ordem de saída: data, depois o número do lançamento.
- Isolamento: toda consulta é filtrada pela empresa. Nenhum lançamento nem conta de outra
  empresa entra no arquivo, nem no mapa de códigos reduzidos, nem nos saldos.
"""

import calendar
import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from django.utils import timezone

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_ERRO,
    IntercambioRecusado,
    Ocorrencia,
)
from apps.contabilidade.intercambio.formatos import (
    ecd_lancamentos,
    proprio_lancamentos,
    referencia_lancamentos,
)
from apps.contabilidade.intercambio.formatos.ecd import FORMATO as FORMATO_ECD
from apps.contabilidade.intercambio.formatos.proprio import FORMATO as FORMATO_PROPRIO
from apps.contabilidade.intercambio.formatos.referencia import FORMATO as FORMATO_REFERENCIA
from apps.contabilidade.intercambio.lancamentos_canonico import (
    LancamentoParaExportar,
    PartidaParaExportar,
    PeriodoDeSaldo,
    SaldoDaConta,
)
from apps.contabilidade.intercambio.plano import ParametroInvalido, _digitos_do_documento
from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    HierarquiaInconsistente,
    _prefixo_chave_zeramento_da_empresa,
    apurar_balancete,
)

FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS = (FORMATO_ECD, FORMATO_PROPRIO, FORMATO_REFERENCIA)

# Um ano por arquivo, em dias corridos e contando os dois extremos do intervalo: cobre um
# ano bissexto inteiro (366 dias), e nenhum intervalo que passe de um ano.
DIAS_MAXIMOS_POR_ARQUIVO = 366

# Casas decimais do valor do registro 6100 no leiaute do sistema de referência. O manual
# NÃO declara (tabela da p. 1450 com tipo e casas em branco; ver `referencia_lancamentos`).
# Enquanto isso não for confirmado, a exportação de lançamento nesse leiaute é recusada.
CASAS_DECIMAIS_DO_VALOR_6100 = None

# Avisos que vão junto de cada arquivo, em ASCII (cabem em cabeçalho HTTP). Não são
# opcionais: a tela os mostra sempre, e a API os devolve no cabeçalho.
AVISOS_DE_EXPORTACAO_DE_LANCAMENTOS = {
    FORMATO_ECD: (
        "Este arquivo nao e a ECD: nao tem registro 0000, bloco J, termos, assinatura nem "
        "validacao do programa da Receita. E so o trecho de lancamentos e saldos.",
    ),
    FORMATO_PROPRIO: (),
    FORMATO_REFERENCIA: (
        "Leiaute do sistema de referencia: codigo reduzido sequencial pela ordem do codigo; "
        "muda quando o plano muda. Nao e a ECD.",
    ),
}


class ExportacaoRecusada(IntercambioRecusado):
    """Recusa nomeada desta exportação. A API e a tela traduzem para 400."""


@dataclass(frozen=True)
class LancamentoOmitido:
    """Lançamento que ficou fora do arquivo por não ser representável no formato pedido."""

    numero: int
    data: date
    historico: str
    quantidade_debitos: int
    quantidade_creditos: int


@dataclass(frozen=True)
class ContaUsada:
    """Conta com partida no arquivo. `codigo_reduzido` só existe no sistema de referência."""

    codigo: str
    nome: str
    codigo_reduzido: int | None


@dataclass(frozen=True)
class RelatorioDeConferencia:
    """O que o contador confere antes de usar o arquivo, e o que a trilha guarda.

    `soma_debitos` e `soma_creditos` são dos lançamentos QUE ESTÃO no arquivo. Os omitidos
    ficam à parte, em `omitidos`, com os próprios totais de partida no lançamento.
    """

    formato: str
    inicio: date
    fim: date
    incluir_saldos: bool
    quantidade_lancamentos: int
    quantidade_partidas: int
    quantidade_zeramentos: int
    quantidade_estornos: int
    soma_debitos: Decimal
    soma_creditos: Decimal
    contas_usadas: tuple[ContaUsada, ...]
    quantidade_meses: int
    omitidos: tuple[LancamentoOmitido, ...]
    sha256: str
    nome_do_arquivo: str
    autor: str
    gerado_em: datetime
    avisos: tuple[str, ...]

    @property
    def quantidade_omitidos(self) -> int:
        return len(self.omitidos)

    def para_trilha(self) -> dict:
        """O que a trilha `lancamentos.exportados` guarda: contagens, intervalo e SHA-256.

        Não guarda o nome do arquivo (traz o documento da empresa) nem o conteúdo.
        """
        return {
            "formato": self.formato,
            "inicio": self.inicio.isoformat(),
            "fim": self.fim.isoformat(),
            "incluir_saldos": self.incluir_saldos,
            "quantidade_lancamentos": self.quantidade_lancamentos,
            "quantidade_partidas": self.quantidade_partidas,
            "quantidade_zeramentos": self.quantidade_zeramentos,
            "quantidade_estornos": self.quantidade_estornos,
            "soma_debitos": str(self.soma_debitos),
            "soma_creditos": str(self.soma_creditos),
            "quantidade_omitidos": self.quantidade_omitidos,
            "quantidade_meses": self.quantidade_meses,
            "sha256": self.sha256,
            "avisos": list(self.avisos),
        }


@dataclass(frozen=True)
class ArquivoDeLancamentos:
    """Saída de `exportar_lancamentos`: o conteúdo em bytes e o relatório de conferência."""

    conteudo: bytes
    relatorio: RelatorioDeConferencia

    @property
    def sha256(self) -> str:
        return self.relatorio.sha256


# -----------------------------------------------------------------------------
# Parâmetros
# -----------------------------------------------------------------------------


def _mes_completo(inicio, fim):
    """True se `inicio` é dia 1 e `fim` é o último dia do mês (I150, p. 133)."""
    return inicio.day == 1 and fim.day == calendar.monthrange(fim.year, fim.month)[1]


def _meses(inicio, fim):
    """(primeiro dia, último dia) de cada mês entre `inicio` e `fim`, em ordem."""
    ano, mes = inicio.year, inicio.month
    while (ano, mes) <= (fim.year, fim.month):
        ultimo = calendar.monthrange(ano, mes)[1]
        yield date(ano, mes, 1), date(ano, mes, ultimo)
        mes += 1
        if mes == 13:
            mes, ano = 1, ano + 1


def _validar_parametros(*, formato, data_inicial, data_final, incluir_saldos, omitir):
    if formato not in FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS:
        raise ParametroInvalido(
            f"formato '{formato}' não existe para a exportação de lançamentos. Use: "
            f"{', '.join(FORMATOS_DE_EXPORTACAO_DE_LANCAMENTOS)}."
        )
    if not isinstance(data_inicial, date) or not isinstance(data_final, date):
        raise ParametroInvalido("o intervalo é obrigatório: informe a data inicial e a final.")
    if data_inicial > data_final:
        raise ParametroInvalido("a data inicial é posterior à data final.")
    dias = (data_final - data_inicial).days + 1
    if dias > DIAS_MAXIMOS_POR_ARQUIVO:
        raise ParametroInvalido(
            f"o intervalo tem {dias} dias; o máximo por arquivo é "
            f"{DIAS_MAXIMOS_POR_ARQUIVO} (um ano). Divida a exportação em períodos menores."
        )
    if incluir_saldos and formato != FORMATO_ECD:
        raise ParametroInvalido("os saldos (I150/I155) existem só no leiaute da ECD.")
    if incluir_saldos and not _mes_completo(data_inicial, data_final):
        raise ParametroInvalido(
            "os saldos são por mês inteiro (I150, REGRA_DT_INI_INICIO_MES e "
            "REGRA_DT_FIN_FIM_MES, p. 133): o intervalo deve começar no dia 1 e terminar "
            "no último dia de um mês."
        )
    if omitir and formato != FORMATO_REFERENCIA:
        raise ParametroInvalido(
            "omitir os não representáveis só existe no leiaute do sistema de referência."
        )


def _nome_do_arquivo(empresa, formato, inicio, fim, incluir_saldos):
    """`lancamentos-<documento>-<aaaammdd>-<aaaammdd>-<sufixo>.txt`, sem ECD nem SPED.

    O arquivo no leiaute da ECD não é a ECD, e o nome diz o que ele contém (I200, e I150
    e I155 se houver saldos), sem dizer que é a escrituração.
    """
    documento = re.sub(r"[^0-9A-Za-z]", "", empresa.cnpj or empresa.cpf or "") or "sem-documento"
    if formato == FORMATO_ECD:
        sufixo = "registros-I200-I150-I155" if incluir_saldos else "registros-I200"
    elif formato == FORMATO_PROPRIO:
        sufixo = "formato-dataledger"
    else:
        sufixo = "leiaute-com-separador"
    return f"lancamentos-{documento}-{inicio:%Y%m%d}-{fim:%Y%m%d}-{sufixo}.txt"


def _autor(usuario):
    if usuario is None or not getattr(usuario, "is_authenticated", False):
        return "sistema"
    return usuario.get_full_name().strip() or usuario.get_username()


# -----------------------------------------------------------------------------
# Dados
# -----------------------------------------------------------------------------


def _carregar_lancamentos(empresa, inicio, fim, contas_por_id):
    """Lançamentos da empresa no intervalo, em ordem de data e número, com as partidas.

    Duas consultas no total (cabeçalhos e itens), sem N+1. O filtro de empresa vale nas
    duas, e toda conta é conferida contra o plano da empresa.
    """
    prefixo_zeramento = _prefixo_chave_zeramento_da_empresa(empresa.id)
    cabecalhos = list(
        LancamentoContabil.objects.filter(
            empresa=empresa, data__gte=inicio, data__lte=fim
        ).order_by("data", "pk")
    )
    itens = ItemLancamento.objects.filter(
        lancamento__empresa=empresa,
        lancamento__data__gte=inicio,
        lancamento__data__lte=fim,
    ).order_by("lancamento_id", "pk")
    partidas = defaultdict(list)
    for item in itens:
        conta = contas_por_id.get(item.conta_id)
        if conta is None:
            raise ExportacaoRecusada(
                f"o lançamento {item.lancamento_id} usa uma conta que não é do plano desta "
                "empresa. A exportação foi recusada; corrija o cadastro antes."
            )
        lado = LADO_DEBITO if item.tipo == TipoPartida.DEBITO else LADO_CREDITO
        partidas[item.lancamento_id].append(
            PartidaParaExportar(codigo_conta=conta.codigo, lado=lado, valor=item.valor)
        )

    lancamentos = []
    for cabecalho in cabecalhos:
        lancamento = LancamentoParaExportar(
            numero=cabecalho.pk,
            data=cabecalho.data,
            historico=cabecalho.historico,
            zeramento=(cabecalho.chave_idempotencia or "").startswith(prefixo_zeramento),
            estorno=cabecalho.estorno_de_id is not None,
            partidas=tuple(partidas[cabecalho.pk]),
        )
        # Um lançamento efetivado é balanceado no banco (gatilho da migração 0013). Esta
        # conferência só dispara se o dado foi alterado por fora do ORM.
        if lancamento.total_debito != lancamento.total_credito:
            raise ExportacaoRecusada(
                f"o lançamento {cabecalho.pk} não está equilibrado no banco (débitos "
                f"{lancamento.total_debito} e créditos {lancamento.total_credito}). A "
                "exportação foi recusada; é dado inconsistente."
            )
        lancamentos.append(lancamento)
    return lancamentos


def _conferir_contas_da_ecd(lancamentos, contas, contas_por_codigo):
    """A ECD só aceita lançamento em conta analítica sem subordinadas (p. 151 e p. 120).

    Conta com lançamento e com filha, ou conta sintética com lançamento, não fecha no leiaute
    (REGRA_CONTA_PARA_LANCAMENTO, p. 151; REGRA_CONTA_NIVEL_SUPERIOR_NAO_SINTETICA, p. 120).
    Recusa, sem tentar corrigir.
    """
    filhas_de = {conta.conta_pai_id for conta in contas if conta.conta_pai_id is not None}
    usadas = {p.codigo_conta for lancamento in lancamentos for p in lancamento.partidas}
    ocorrencias = []
    for codigo in sorted(usadas):
        conta = contas_por_codigo[codigo]
        if not conta.aceita_lancamento:
            ocorrencias.append(
                Ocorrencia(
                    0,
                    "COD_CTA",
                    NIVEL_ERRO,
                    f"conta {codigo} é sintética no cadastro e tem lançamento. O leiaute "
                    "exige lançamento em conta analítica (REGRA_CONTA_PARA_LANCAMENTO, p. 151).",
                )
            )
        if conta.pk in filhas_de:
            ocorrencias.append(
                Ocorrencia(
                    0,
                    "COD_CTA",
                    NIVEL_ERRO,
                    f"conta {codigo} tem lançamento e subordinadas. No leiaute, a conta com "
                    "lançamento é analítica e não tem subordinadas (p. 120).",
                )
            )
    if ocorrencias:
        raise ExportacaoRecusada(
            "A exportação não cabe no leiaute da ECD: "
            + "; ".join(f"{o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )


def _saldos_mensais(empresa, inicio, fim, contas_por_codigo):
    """Um `PeriodoDeSaldo` por mês, lido do balancete (`apurar_balancete`), sem recalcular.

    O balancete devolve saldo assinado pela natureza cadastrada da conta. Aqui o saldo
    volta a ser débito menos crédito (D − C): `saldo = sinal × valor`, com sinal +1 para
    conta devedora e −1 para credora. Assim o indicador D/C da ECD sai sem depender da
    natureza.

    Só entram as contas analíticas (sem subordinadas) com saldo ou movimento no mês.
    Conta com subordinadas e lançamento próprio, e conta sintética com saldo, não têm
    lugar no I155: são recusadas com o nome da conta, em vez de sumir do arquivo.
    """
    periodos = []
    ocorrencias = []
    for mes_inicio, mes_fim in _meses(inicio, fim):
        try:
            balancete = apurar_balancete(empresa=empresa, inicio=mes_inicio, fim=mes_fim)
        except HierarquiaInconsistente as exc:
            raise ExportacaoRecusada(
                f"a hierarquia de contas impede o balancete de {mes_inicio:%m/%Y}: {exc}"
            ) from exc
        saldos = []
        for linha in balancete["contas"]:
            codigo = linha["conta"]
            conta = contas_por_codigo[codigo]
            sinal = 1 if linha["natureza"] == NaturezaConta.DEVEDORA else -1
            saldo_inicial = sinal * linha["saldo_anterior"]
            saldo_final = sinal * linha["saldo_final"]
            debitos = linha["debitos"]
            creditos = linha["creditos"]
            if not linha["analitica"]:
                if linha["debitos_proprios"] != 0 or linha["creditos_proprios"] != 0:
                    ocorrencias.append(
                        Ocorrencia(
                            0,
                            "COD_CTA",
                            NIVEL_ERRO,
                            f"em {mes_inicio:%m/%Y}, a conta {codigo} tem lançamento próprio "
                            "e subordinadas. O I155 só representa conta analítica sem filhas "
                            "(p. 134).",
                        )
                    )
                continue
            tem_valor = any(v != 0 for v in (saldo_inicial, debitos, creditos, saldo_final))
            if tem_valor and not conta.aceita_lancamento:
                ocorrencias.append(
                    Ocorrencia(
                        0,
                        "COD_CTA",
                        NIVEL_ERRO,
                        f"em {mes_inicio:%m/%Y}, a conta {codigo} é sintética e tem saldo ou "
                        "movimento. O I155 só representa conta analítica (p. 134).",
                    )
                )
                continue
            if not tem_valor:
                continue
            if saldo_final != saldo_inicial + debitos - creditos:
                # Dado inconsistente no balancete: o I155 não pode ser escrito com ele.
                raise ExportacaoRecusada(
                    f"em {mes_inicio:%m/%Y}, o saldo final da conta {codigo} não é o inicial "
                    "mais débitos menos créditos. A exportação foi recusada."
                )
            saldos.append(
                SaldoDaConta(
                    codigo_conta=codigo,
                    saldo_inicial=saldo_inicial,
                    debitos=debitos,
                    creditos=creditos,
                    saldo_final=saldo_final,
                )
            )
        periodos.append(
            PeriodoDeSaldo(
                inicio=mes_inicio,
                fim=mes_fim,
                contas=tuple(sorted(saldos, key=lambda s: s.codigo_conta)),
            )
        )
    if ocorrencias:
        raise ExportacaoRecusada(
            "Os saldos não cabem no leiaute da ECD: "
            + "; ".join(f"{o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )
    return periodos


def _conciliar_saldos_com_lancamentos(periodos, lancamentos):
    """Os débitos e os créditos dos saldos mensais têm de ser os dos lançamentos do arquivo.

    O balancete e os lançamentos saem da mesma base, então um desencontro aqui é dado
    inconsistente, e a exportação para antes de gravar o arquivo.
    """
    debitos_saldos = sum((c.debitos for p in periodos for c in p.contas), Decimal("0"))
    creditos_saldos = sum((c.creditos for p in periodos for c in p.contas), Decimal("0"))
    debitos_lancamentos = sum((lanc.total_debito for lanc in lancamentos), Decimal("0"))
    creditos_lancamentos = sum((lanc.total_credito for lanc in lancamentos), Decimal("0"))
    if debitos_saldos != debitos_lancamentos or creditos_saldos != creditos_lancamentos:
        raise ExportacaoRecusada(
            "Os saldos mensais não conciliam com os lançamentos do período: débitos "
            f"{debitos_saldos} nos saldos e {debitos_lancamentos} nos lançamentos; créditos "
            f"{creditos_saldos} e {creditos_lancamentos}. Nada foi gerado."
        )


# -----------------------------------------------------------------------------
# Entrada pública
# -----------------------------------------------------------------------------


def exportar_lancamentos(
    *,
    empresa,
    formato,
    data_inicial,
    data_final,
    incluir_saldos=False,
    omitir_nao_representaveis=False,
    usuario=None,
    agora=None,
):
    """Gera o arquivo de lançamentos (e saldos) da `empresa` no `formato`, com relatório.

    Parâmetros:
    - `formato`: `ecd` (I200/I250, e I150/I155 com `incluir_saldos`), `proprio` ou
      `referencia`.
    - `data_inicial` e `data_final`: intervalo obrigatório, de até 366 dias, inclusive.
    - `incluir_saldos`: só na ECD, e só com meses inteiros (dia 1 até o último dia).
    - `omitir_nao_representaveis`: só no sistema de referência. Sem ele, qualquer lançamento
      com mais de um débito e mais de um crédito recusa a exportação inteira.
    - `usuario` e `agora`: autor e instante do relatório. `agora=None` usa o relógio.

    Levanta `IntercambioRecusado` (com subclasses `ParametroInvalido` e
    `ExportacaoRecusada`) com a mensagem para o contador. Nada é gravado no banco.
    """
    _validar_parametros(
        formato=formato,
        data_inicial=data_inicial,
        data_final=data_final,
        incluir_saldos=incluir_saldos,
        omitir=omitir_nao_representaveis,
    )

    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    contas_por_id = {conta.pk: conta for conta in contas}
    contas_por_codigo = {conta.codigo: conta for conta in contas}
    lancamentos = _carregar_lancamentos(empresa, data_inicial, data_final, contas_por_id)

    if formato == FORMATO_ECD:
        _conferir_contas_da_ecd(lancamentos, contas, contas_por_codigo)
    periodos = []
    if incluir_saldos:
        periodos = _saldos_mensais(empresa, data_inicial, data_final, contas_por_codigo)
        _conciliar_saldos_com_lancamentos(periodos, lancamentos)

    omitidos = ()
    reduzidos = {}
    if formato == FORMATO_ECD:
        conteudo = ecd_lancamentos.escrever(lancamentos, periodos, incluir_saldos=incluir_saldos)
    elif formato == FORMATO_PROPRIO:
        conteudo = proprio_lancamentos.escrever(lancamentos)
    else:
        reduzidos = referencia_lancamentos.codigos_reduzidos(contas_por_codigo.keys())
        conteudo, omitidos = referencia_lancamentos.escrever(
            lancamentos,
            documento=_digitos_do_documento(empresa),
            codigos_reduzidos=reduzidos,
            casas_decimais_do_valor=CASAS_DECIMAIS_DO_VALOR_6100,
            omitir_nao_representaveis=omitir_nao_representaveis,
        )

    numeros_omitidos = {lancamento.numero for lancamento in omitidos}
    no_arquivo = [lanc for lanc in lancamentos if lanc.numero not in numeros_omitidos]
    usadas = sorted({p.codigo_conta for lanc in no_arquivo for p in lanc.partidas})
    relatorio = RelatorioDeConferencia(
        formato=formato,
        inicio=data_inicial,
        fim=data_final,
        incluir_saldos=incluir_saldos,
        quantidade_lancamentos=len(no_arquivo),
        quantidade_partidas=sum(len(lanc.partidas) for lanc in no_arquivo),
        quantidade_zeramentos=sum(1 for lanc in no_arquivo if lanc.zeramento),
        quantidade_estornos=sum(1 for lanc in no_arquivo if lanc.estorno),
        soma_debitos=sum((lanc.total_debito for lanc in no_arquivo), Decimal("0")),
        soma_creditos=sum((lanc.total_credito for lanc in no_arquivo), Decimal("0")),
        contas_usadas=tuple(
            ContaUsada(
                codigo=codigo,
                nome=contas_por_codigo[codigo].nome,
                codigo_reduzido=reduzidos.get(codigo),
            )
            for codigo in usadas
        ),
        quantidade_meses=len(periodos),
        omitidos=tuple(
            LancamentoOmitido(
                numero=lanc.numero,
                data=lanc.data,
                historico=lanc.historico,
                quantidade_debitos=sum(1 for p in lanc.partidas if p.lado == LADO_DEBITO),
                quantidade_creditos=sum(1 for p in lanc.partidas if p.lado == LADO_CREDITO),
            )
            for lanc in omitidos
        ),
        sha256=hashlib.sha256(conteudo).hexdigest(),
        nome_do_arquivo=_nome_do_arquivo(
            empresa, formato, data_inicial, data_final, incluir_saldos
        ),
        autor=_autor(usuario),
        gerado_em=agora or timezone.now(),
        avisos=AVISOS_DE_EXPORTACAO_DE_LANCAMENTOS[formato],
    )
    return ArquivoDeLancamentos(conteudo=conteudo, relatorio=relatorio)
