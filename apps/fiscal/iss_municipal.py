"""ISS por município, começando por Palmas — DL-076, frente A (itens 2 a 7 do plano).

Contrato: docs/planos/DL-076-iss-por-municipio-palmas.md (critérios 1 a 10) e a consulta
docs/projeto/consultas/2026-10-08-contador-senior-iss-palmas.md. Hipóteses HI-82 a HI-86.

Decisões que o código não explica sozinho:

- CONFERÊNCIA, NUNCA GUIA. O produto soma o `vISSQN` das notas para o contador emitir a
  guia no portal do município. Não gera guia, não transmite e não recalcula o imposto para
  substituir o da nota (em Palmas a guia sai das notas, RCTM art. 214).
- O total é a SOMA do `vISSQN` das notas escrituradas como "ISS devido pelo prestador"
  no município do estabelecimento, na competência (`data_competencia`, o `dCompet`,
  nunca a emissão). Retidas, de outro município, exportação, imunes e fora da lista não
  entram (HI-82, HI-85, HI-86).
- A CONFERÊNCIA usa a base `vBC` da nota (declarado aqui no código; é a base que o XML
  já traz com o desconto e as deduções aplicados, conforme a fórmula do XSD). Esperado =
  vBC × alíquota cadastrada ÷ 100, sem arredondamento intermediário. Diferença acima de
  R$ 0,01 é PENDÊNCIA com os dois valores, e não bloqueia o total. A diferença de base
  (vServ − vDescIncond − deduções ≠ vBC) é só AVISO (`divergencia_de_base`).
- ALÍQUOTA VIGENTE é a que cobre o mês INTEIRO. Alíquota que muda no meio do mês não
  tem um valor único para a competência, e vira bloqueio nomeado.
- Bloqueio = a apuração não sai. A lista de bloqueios é COMPLETA (como o pré-DAS), para
  o contador ver tudo de uma vez.
- Campo ausente nunca vira zero: a nota sem `vISSQN`, `vBC`, `cTribNac`, `cLocIncid` ou
  `tpRetISSQN` é bloqueio com o nome do campo.
- Nota escriturada como ISS devido, mas cancelada depois de escriturada, bloqueia: o
  contador estorna a escrituração (com trilha) antes de a apuração sair. Nota
  escriturada como devido mas retida no XML (tpRetISSQN 2 ou 3) também bloqueia, porque
  a retenção muda quem recolhe o imposto.
- Não há tabela de alíquotas de Palmas: a alíquota é dado do escritório (HI-82), e a
  regra do município (vencimento, dia não útil, fonte) é global (HI-83).

Concorrência: cada cadastro que escreve trava a linha do ESCRITÓRIO (alíquota) ou da
EMPRESA (regime) com `select_for_update` antes de checar a sobreposição; a checagem é
primeira defesa, e a trava de `_gravar_*` traduz a corrida que escapa dela em 409. A
apuração é leitura: não grava e não trava.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Context, Decimal, InvalidOperation, localcontext

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa
from apps.fiscal.escrituracao import (
    SITUACAO_A_ESCRITURAR,
    SITUACAO_RASCUNHO,
    notas_a_escriturar,
)
from apps.fiscal.iss_nota import ausentes_que_alertam, campos_iss_do_documento, divergencia_de_base
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    NaturezaOperacao,
    RegimeIss,
    RegimeIssEmpresa,
    RegraIssMunicipio,
)
from apps.fiscal.rbt12 import _periodo_do_simples
from apps.fiscal.receita import travar_empresa
from apps.fiscal.services import documentos_do_escritorio, situacao_do_documento
from apps.tenancy.models import Escritorio

# ---------------------------------------------------------------------------
# Fontes e constantes. Cada texto diz de onde vem a regra; quem lê o aviso ou o bloqueio
# vê o dispositivo junto. A consulta de 08/10/2026 é a origem de tudo que é "norma".
# ---------------------------------------------------------------------------

DISP_SIMPLES = (
    "DL-075 (pré-DAS: ISS do Simples sai no DAS); LC 123/2006, art. 18, § 4º-A (ISS, citado "
    "no pré-DAS como DISP_SITUACAO_ISS)"
)
DISP_REGIME = "HI-84; DL 406/1968, art. 9º, §§ 1º e 3º; LC 285/2013, arts. 52, 58 e 59 (cópia)"
DISP_REGRA = (
    "HI-83; Decreto 1.667/2018 (RCTM de Palmas), art. 86 §§ 1º e 3º e Anexo I "
    "(cópia de legisweb, consultada em 08/10/2026)"
)
DISP_BASE_TOTAL = "HI-82; Decreto 1.667/2018 (RCTM), arts. 138 e 214 (cópia legisweb)"
DISP_CONFERENCIA = (
    "HI-82; LC 116/2003, art. 8º, II, e art. 8º-A (2% a 5%); tolerância de R$ 0,01 (DL-076, item 5)"
)
DISP_FAIXA = (
    "LC 116/2003, art. 8º, II (máximo 5%); art. 8º-A (mínimo 2%) e § 1º (exceção: "
    "subitens 7.02, 7.05 e 16.01)"
)
DISP_CANCELADA = "DL-072, critério 5 (nota cancelada depois de escriturada); estorno com trilha"
DISP_RETIDO = "HI-86; LC 116/2003, art. 6º; RCTM arts. 141 a 148 (cópia legisweb)"
DISP_MULTA = "LC 285/2013, art. 142, I–III e § 1º (cópia legisweb; consulta de 08/10/2026, item 9)"
DISP_ART_3 = "LC 116/2003, art. 3º, caput, incisos I a XXV, e §§ 1º e 2º (texto do Planalto)"
DISP_ESCRITURACAO = (
    "HI-89 (auditoria DL-076, A2); DL-072: só a escrituração efetivada entra no total"
)
DISP_NATUREZA = "HI-85; LC 116/2003, art. 3º (incidência no município do estabelecimento)"

# Código do aviso de notas prestadas da competência ainda não escrituradas (HI-89). A tela
# destaca este aviso e leva à escrituração; a API o devolve em `avisos`.
CODIGO_NOTAS_NAO_ESCRITURADAS = "notas_nao_escrituradas"

# Alíquota mínima, com a exceção do § 1º do art. 8º-A: estes subitens podem sair abaixo de
# 2% sem nulidade, por isso entram com aviso e não são recusados.
SUBITENS_EXCECAO_DO_MINIMO = frozenset({"07.02", "07.05", "16.01"})

# Tolerância da conferência (DL-076, item 5). Não há regra oficial de arredondamento para
# a conferência; por isso a comparação é exata, sem arredondar o valor calculado.
TOLERANCIA = Decimal("0.01")
_QUATRO_CASAS = Decimal("0.0001")
_CONTEXTO_EXATO = Context(prec=60)

_ANO_MINIMO, _ANO_MAXIMO = 1970, 2999
_EXERCICIO_MINIMO, _EXERCICIO_MAXIMO = 2000, 2999
# Vigência de alíquota: datas fora de 2000 a 2100 são erro de digitação (A9 da auditoria DL-076).
# O sistema não tem data de vigência nesses extremos; o limite é só para recusar o absurdo.
_VIGENCIA_ALIQUOTA_MINIMA, _VIGENCIA_ALIQUOTA_MAXIMA = date(2000, 1, 1), date(2100, 12, 31)

_PADRAO_MUNICIPIO = re.compile(r"[0-9]{7}")
_PADRAO_SUBITEM = re.compile(r"(0[1-9]|[12][0-9]|3[0-9]|40)\.(0[1-9]|[1-9][0-9])")

# Restrições de banco que um cadastro pode violar com dado já validado: o savepoint as
# traduz para erro de entrada (400), e não para 500.
_RESTRICOES_DE_ENTRADA_ALIQUOTA = frozenset(
    {
        "aliquota_iss_codigo_ibge",
        "aliquota_iss_subitem_valido",
        "aliquota_iss_percentual_ate_5",
        "aliquota_iss_fonte_preenchida",
        "aliquota_iss_fim_depois_do_inicio",
        "aliquota_iss_piso_2_salvo_excecao",
    }
)
_RESTRICOES_DE_ENTRADA_REGIME = frozenset(
    {"regime_iss_exercicio_valido", "regime_iss_regime_valido", "regime_iss_codigo_ibge"}
)
_RESTRICOES_DE_ENTRADA_REGRA = frozenset(
    {
        "regra_iss_codigo_ibge",
        "regra_iss_dias_entre_1_e_28",
        "regra_iss_fim_depois_do_inicio",
        "regra_iss_fonte_preenchida",
    }
)

# Subitens das exceções do art. 3º da LC 116 (texto do Planalto, consultado em 08/10/2026).
# Cada inciso aponta para o SUBITEM que o texto nomeia. Um inciso que nomeia ITEM (XVIII
# "subitens do item 12, exceto o 12.13"; XIX "item 16"; XXII "item 20") vai na tabela de
# item. PARA REVISÃO DO CONTADOR (DL-076): (1) o inciso XII não cita subitem no texto atual
# (o texto anterior, na mesma página, cita o 7.16), e foi mapeado para 7.16; (2) o inciso I
# (serviço do exterior, art. 1º, § 1º) não tem subitem, por isso não entra nesta tabela, e o
# aviso de incidência pode sair em caso de importação de serviço.
EXCECOES_ART_3_POR_SUBITEM = {
    "03.04": "§ 1º",
    "03.05": "II",
    "07.02": "III",
    "07.19": "III",
    "14.14": "III",
    "07.04": "IV",
    "07.05": "V",
    "07.09": "VI",
    "07.10": "VII",
    "07.11": "VIII",
    "07.12": "IX",
    "07.16": "XII",
    "07.17": "XIII",
    "07.18": "XIV",
    "11.01": "XV",
    "11.02": "XVI",
    "11.04": "XVII",
    "17.05": "XX",
    "17.10": "XXI",
    "22.01": "§ 2º",
    "04.22": "XXIII",
    "04.23": "XXIII",
    "05.09": "XXIII",
    "15.01": "XXIV",
    "15.09": "XXV",
}
EXCECOES_ART_3_POR_ITEM = {"12": "XVIII", "16": "XIX", "20": "XXII"}
SUBITEM_FORA_DA_EXCECAO_DO_ITEM_12 = "12.13"


def excecao_do_art_3(subitem: str) -> str | None:
    """Inciso (ou parágrafo) do art. 3º da LC 116 que traz o subitem como exceção, ou None.

    None quer dizer que o subitem não está nas exceções: o ISS é devido no estabelecimento
    prestador. O aviso de incidência em outro município usa esta função.
    """
    if subitem in EXCECOES_ART_3_POR_SUBITEM:
        return EXCECOES_ART_3_POR_SUBITEM[subitem]
    item = subitem.split(".")[0]
    if item in EXCECOES_ART_3_POR_ITEM:
        if item == "12" and subitem == SUBITEM_FORA_DA_EXCECAO_DO_ITEM_12:
            return None
        return EXCECOES_ART_3_POR_ITEM[item]
    return None


# ---------------------------------------------------------------------------
# Resultados e erros
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BloqueioIss:
    """Motivo que impede a apuração. `mensagem` nomeia o que falta; `dispositivo`, a fonte."""

    codigo: str
    mensagem: str
    dispositivo: str


@dataclass(frozen=True)
class AvisoIss:
    codigo: str
    mensagem: str
    dispositivo: str


@dataclass(frozen=True)
class PassoIss:
    """Um passo da memória de cálculo. `valor` é texto; os números exatos ficam nos campos."""

    ordem: int
    descricao: str
    valor: str
    dispositivo: str


class IssErro(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaIss(IssErro):
    """Entrada fora da regra, recusada antes de gravar. API: 400."""


class IssConflito(IssErro):
    """Conflito com o estado atual (vigência sobreposta, regime já cadastrado). API: 409."""


class IssRecusado(Exception):
    """Apuração não calculada. `bloqueios` lista TODOS os motivos encontrados.

    `notas` vem preenchido só no regime fixo: são as notas da competência para conferência
    (HI-84), com a marca das que trazem ISS destacado ou retido.
    """

    def __init__(self, bloqueios, notas=()):
        self.bloqueios = tuple(bloqueios)
        self.notas = tuple(notas)
        super().__init__("; ".join(b.mensagem for b in self.bloqueios))


@dataclass(frozen=True)
class NotaApurada:
    identificador: str
    numero: str
    data_competencia: date
    c_loc_incid: str
    subitem: str
    v_bc: Decimal
    v_iss_qn: Decimal
    aliquota_cadastrada: Decimal
    esperado: Decimal
    diferenca: Decimal
    conferida: bool
    avisos: tuple[str, ...] = ()
    # Lidos uma vez, na apuração, para a tela não reler o XML da nota (A6 da auditoria DL-076).
    p_aliq_aplic: Decimal | None = None
    tomador_documento: str = ""
    tomador_nome: str = ""


@dataclass(frozen=True)
class ApuracaoIss:
    empresa_id: int
    ano: int
    mes: int
    municipio_ibge: str
    nome_municipio: str
    regime: str
    total: Decimal
    notas: tuple[NotaApurada, ...]
    avisos: tuple[AvisoIss, ...]
    vencimento_proprio: date
    vencimento_retido: date
    regra_dia_nao_util: str
    memoria: tuple[PassoIss, ...]
    aviso_multa: str | None = None

    @property
    def pendencias(self) -> tuple[NotaApurada, ...]:
        return tuple(nota for nota in self.notas if not nota.conferida)


@dataclass(frozen=True)
class NotaDeRelatorio:
    """Uma nota no relatório de retido sofrido ou de outros municípios. Campo ausente = None."""

    identificador: str
    numero: str
    data_competencia: date
    cancelada: bool
    tomador_documento: str
    tomador_nome: str
    c_loc_incid: str | None
    subitem: str | None
    v_bc: Decimal | None
    p_aliq_aplic: Decimal | None
    v_iss_qn: Decimal | None
    tp_ret_issqn: str | None
    ausentes: tuple[str, ...] = ()


@dataclass(frozen=True)
class GrupoMunicipal:
    """Total de um município de incidência. `incompletas` lista as notas sem o valor
    (campo ausente), que NÃO entram no total como zero."""

    municipio_ibge: str | None
    total: Decimal
    incompletas: tuple[str, ...]
    vencimento_retido: date | None = None
    aviso: str | None = None


@dataclass(frozen=True)
class RelatorioRetidoSofrido:
    ano: int
    mes: int
    notas: tuple[NotaDeRelatorio, ...]
    grupos: tuple[GrupoMunicipal, ...]
    avisos: tuple[AvisoIss, ...]


@dataclass(frozen=True)
class RelatorioOutrosMunicipios:
    ano: int
    mes: int
    notas: tuple[NotaDeRelatorio, ...]
    grupos: tuple[GrupoMunicipal, ...]
    avisos: tuple[AvisoIss, ...]


# ---------------------------------------------------------------------------
# Datas e competência
# ---------------------------------------------------------------------------


def _validar_competencia(ano, mes) -> None:
    if isinstance(ano, bool) or not isinstance(ano, int) or not _ANO_MINIMO <= ano <= _ANO_MAXIMO:
        raise EntradaInvalidaIss(f"Ano inválido: {ano!r}.")
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise EntradaInvalidaIss(f"Mês inválido: {mes!r}.")


def _primeiro_e_ultimo(ano: int, mes: int) -> tuple[date, date]:
    return date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])


def _mes_seguinte(ano: int, mes: int) -> tuple[int, int]:
    return (ano + 1, 1) if mes == 12 else (ano, mes + 1)


def _rotulo(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


def _data_br(valor: date) -> str:
    return valor.strftime("%d/%m/%Y")


_DIA_DE_FIM_DE_SEMANA = {5: "sábado", 6: "domingo"}


def data_nominal_br(valor: date | None) -> str:
    """Data NOMINAL do vencimento em dd/mm/aaaa, com o dia da semana quando cai em sábado ou
    domingo (HI-90, item 4; auditoria A7). Não calcula feriado nem afirma outra data: o dia útil
    seguinte é texto da regra (HI-83), mostrado ao lado."""
    if valor is None:
        return ""
    texto = _data_br(valor)
    dia = _DIA_DE_FIM_DE_SEMANA.get(valor.weekday())
    return f"{texto} ({dia})" if dia else texto


def _cobre_o_mes(inicio: date, fim: date | None, primeiro: date, ultimo: date) -> bool:
    return inicio <= primeiro and (fim is None or fim >= ultimo)


def _toca_o_mes(inicio: date, fim: date | None, primeiro: date, ultimo: date) -> bool:
    return inicio <= ultimo and (fim is None or fim >= primeiro)


# ---------------------------------------------------------------------------
# Consultas (sempre filtradas por escritório e por empresa)
# ---------------------------------------------------------------------------


def _escrituracoes_da_competencia(empresa: Empresa, ano: int, mes: int) -> list:
    """Escriturações EFETIVADAS da empresa cuja competência (`data_competencia`, dCompet
    copiado no ato de efetivar) cai no mês. A emissão nunca define o mês.

    O filtro por escritório é ADICIONAL ao da empresa (AGENTS.md §11): a empresa já é de um
    escritório, e a nota é do escritório do documento. Os dois precisam bater.
    """
    primeiro, ultimo = _primeiro_e_ultimo(ano, mes)
    return list(
        EscrituracaoFiscal.objects.filter(
            empresa=empresa,
            estado=EstadoEscrituracao.EFETIVADA,
            data_competencia__gte=primeiro,
            data_competencia__lte=ultimo,
            vinculo__documento__escritorio=empresa.escritorio,
        )
        .select_related("vinculo__documento")
        .order_by("vinculo__documento__dh_emissao", "id")
    )


def _canceladas(empresa: Empresa, ano: int, mes: int) -> dict[int, bool]:
    """Situação de cancelamento de cada documento, na mesma consulta (sem N+1)."""
    return {
        documento.pk: bool(documento.cancelada)
        for documento in documentos_do_escritorio(
            empresa.escritorio, empresa=empresa, competencia=(ano, mes)
        )
    }


def _cancelada(documento, anotadas: dict[int, bool]) -> bool:
    if documento.pk in anotadas:
        return anotadas[documento.pk]
    return situacao_do_documento(documento) == "cancelada"


def _regra_do_mes(municipio: str, ano: int, mes: int) -> tuple[RegraIssMunicipio | None, str]:
    """(regra, situação). Situação: "vigente", "ausente", "fora_de_vigencia" ou "sobrepostas".

    Regra global (sem escritório): a mesma para todo escritório. A regra precisa cobrir o
    mês inteiro; a sobreposição é recusada no cadastro, então "sobrepostas" é só defesa.
    """
    primeiro, ultimo = _primeiro_e_ultimo(ano, mes)
    existentes = RegraIssMunicipio.objects.filter(municipio_ibge=municipio)
    if not existentes.exists():
        return None, "ausente"
    cobrindo = [
        regra
        for regra in existentes.order_by("inicio_vigencia", "id")
        if _cobre_o_mes(regra.inicio_vigencia, regra.fim_vigencia, primeiro, ultimo)
    ]
    if len(cobrindo) == 1:
        return cobrindo[0], "vigente"
    if not cobrindo:
        return None, "fora_de_vigencia"
    return None, "sobrepostas"


def _aliquotas_do_municipio(
    escritorio: Escritorio, municipio: str
) -> dict[str, list[AliquotaIssMunicipal]]:
    """Alíquotas do ESCRITÓRIO no município, por subitem. Uma consulta para a apuração inteira
    (A6 da auditoria DL-076): antes havia uma por nota. O filtro por escritório fica aqui, e
    nenhuma alíquota de outro escritório entra no dicionário (AGENTS.md §11)."""
    por_subitem: dict[str, list[AliquotaIssMunicipal]] = {}
    consulta = AliquotaIssMunicipal.objects.filter(
        escritorio=escritorio, municipio_ibge=municipio
    ).order_by("subitem", "inicio_vigencia", "id")
    for aliquota in consulta:
        por_subitem.setdefault(aliquota.subitem, []).append(aliquota)
    return por_subitem


def _cobertura_do_mes(
    aliquotas: list[AliquotaIssMunicipal], ano: int, mes: int
) -> tuple[list[AliquotaIssMunicipal], bool]:
    """(alíquotas que cobrem o mês INTEIRO, há alguma que toca só parte do mês).

    A parte do mês serve só para a mensagem: uma alíquota que muda no dia 15 não tem valor
    único para a competência, e a apuração recusa com o motivo, em vez de escolher uma.
    """
    primeiro, ultimo = _primeiro_e_ultimo(ano, mes)
    cobrindo = [
        aliquota
        for aliquota in aliquotas
        if _cobre_o_mes(aliquota.inicio_vigencia, aliquota.fim_vigencia, primeiro, ultimo)
    ]
    parcial = any(
        _toca_o_mes(a.inicio_vigencia, a.fim_vigencia, primeiro, ultimo)
        and not _cobre_o_mes(a.inicio_vigencia, a.fim_vigencia, primeiro, ultimo)
        for a in aliquotas
    )
    return cobrindo, parcial


def _notas_nao_escrituradas(empresa: Empresa, ano: int, mes: int) -> list:
    """Notas PRESTADAS da empresa na competência que ainda não estão efetivadas: a escriturar
    ou em rascunho (HI-89). Canceladas ficam de fora: o cancelamento já é tratado à parte."""
    return [
        nota
        for nota in notas_a_escriturar(empresa, ano, mes)
        if nota.situacao in (SITUACAO_A_ESCRITURAR, SITUACAO_RASCUNHO)
    ]


def _regime_do_exercicio(empresa: Empresa, ano: int) -> RegimeIssEmpresa | None:
    return RegimeIssEmpresa.objects.filter(empresa=empresa, exercicio=ano).first()


# ---------------------------------------------------------------------------
# Apuração do ISS próprio (DL-076, item 5)
# ---------------------------------------------------------------------------

_CAMPOS_DA_APURACAO = (
    ("v_iss_qn", "vISSQN"),
    ("v_bc", "vBC"),
    ("c_trib_nac", "cTribNac"),
    ("c_loc_incid", "cLocIncid"),
    ("tp_ret_issqn", "tpRetISSQN"),
)


def _faltantes_da_apuracao(campos) -> list[str]:
    """Rótulos dos campos que a apuração precisa e que faltam ou vieram ilegíveis."""
    return [rotulo for atributo, rotulo in _CAMPOS_DA_APURACAO if getattr(campos, atributo) is None]


def _numero(documento) -> str:
    return documento.numero or documento.identificador


def _bloqueio_nota(documento, detalhe: str) -> BloqueioIss:
    return BloqueioIss(
        "nota_sem_campo_de_iss",
        f"Nota {_numero(documento)} ({documento.identificador}): {detalhe}. Não se presume "
        "zero para campo ausente (DL-076, item 1).",
        DISP_BASE_TOTAL,
    )


def _notas_do_regime_fixo(empresa: Empresa, ano: int, mes: int) -> tuple[NotaDeRelatorio, ...]:
    """Notas da competência para conferência no regime fixo (HI-84), com o ISS destacado
    ou retido sinalizado. Não entram em total nenhum: é só a lista do contador."""
    anotadas = _canceladas(empresa, ano, mes)
    return tuple(
        _nota_de_relatorio(esc, anotadas)
        for esc in _escrituracoes_da_competencia(empresa, ano, mes)
    )


def _aviso_natureza_incompativel(documento, anotadas, municipio) -> AvisoIss | None:
    """Aviso A3 (auditoria DL-076): nota escriturada como "ISS devido a outro município" cujo
    `cLocIncid` é o município do estabelecimento. É o espelho da incidência em outro município
    (que já avisa quando a natureza é "devido"). A nota cancelada não avisa: fica fora dos
    relatórios de qualquer forma. Sem município do estabelecimento não há com o que comparar."""
    if municipio is None or _cancelada(documento, anotadas):
        return None
    c_loc_incid = campos_iss_do_documento(documento).c_loc_incid
    if c_loc_incid is None or c_loc_incid != municipio:
        return None
    return AvisoIss(
        "natureza_incompativel_com_incidencia",
        f"Nota {_numero(documento)} está escriturada como ISS devido a outro município, mas o "
        f"local de incidência (cLocIncid {c_loc_incid}) é o município do estabelecimento "
        f"({municipio}). Confira a natureza escriturada e o cLocIncid da nota.",
        DISP_NATUREZA,
    )


def apuracao_iss_proprio(
    empresa: Empresa, ano: int, mes: int, *, hoje: date | None = None
) -> ApuracaoIss:
    """Apuração do ISS próprio do mês, ou `IssRecusado` com TODOS os bloqueios.

    `hoje` existe para o teste de multa e juros (aviso de atraso); em produção é o dia de
    Brasília. Não grava nada: é cálculo sob demanda, a partir das escriturações atuais.
    """
    _validar_competencia(ano, mes)
    hoje = hoje or timezone.localdate()
    rotulo = _rotulo(ano, mes)
    bloqueios: list[BloqueioIss] = []
    notas_fixo: tuple[NotaDeRelatorio, ...] = ()

    # 1. Simples Nacional no mês: o ISS sai no DAS (DL-075). Não há apuração própria aqui.
    no_simples = _periodo_do_simples(empresa, ano, mes) is not None
    if no_simples:
        bloqueios.append(
            BloqueioIss(
                "empresa_no_simples",
                f"A empresa está no Simples Nacional em {rotulo}: o ISS dela sai no pré-DAS "
                "(DL-075), não nesta apuração.",
                DISP_SIMPLES,
            )
        )

    # 2. Regime do ISS no exercício (HI-84). Sem regime, o produto não presume nada.
    regime = _regime_do_exercicio(empresa, ano)
    if regime is None:
        bloqueios.append(
            BloqueioIss(
                "regime_iss_ausente",
                f"Não há regime do ISS cadastrado para {ano}. Cadastre o regime (alíquota, fixo "
                "de autônomo ou fixo de sociedade de profissionais) e o município do "
                "estabelecimento.",
                DISP_REGIME,
            )
        )
    elif regime.regime != RegimeIss.ALIQUOTA:
        notas_fixo = _notas_do_regime_fixo(empresa, ano, mes)
        destacadas = [
            n.numero
            for n in notas_fixo
            if (n.v_iss_qn is not None and n.v_iss_qn > 0) or n.tp_ret_issqn in ("2", "3")
        ]
        complemento = (
            f" Com ISS destacado ou retido no XML: {', '.join(destacadas)} (HI-84)."
            if destacadas
            else ""
        )
        bloqueios.append(
            BloqueioIss(
                "regime_fixo",
                f"Regime fixo ({regime.get_regime_display()}) em {ano}: não há apuração por "
                f"alíquota. São {len(notas_fixo)} nota(s) escrituradas em {rotulo} para "
                f"conferência.{complemento}",
                DISP_REGIME,
            )
        )

    municipio = regime.municipio_ibge if regime is not None else ""
    apura_por_nota = regime is not None and regime.regime == RegimeIss.ALIQUOTA and not no_simples

    regra: RegraIssMunicipio | None = None
    if apura_por_nota:
        regra, situacao = _regra_do_mes(municipio, ano, mes)
        if situacao == "ausente":
            bloqueios.append(
                BloqueioIss(
                    "regra_municipio_ausente",
                    f"Não há regra do ISS cadastrada para o município {municipio}. Sem o "
                    "vencimento e a regra do dia não útil, a apuração não sai.",
                    DISP_REGRA,
                )
            )
        elif situacao == "fora_de_vigencia":
            bloqueios.append(
                BloqueioIss(
                    "regra_municipio_fora_de_vigencia",
                    f"A regra cadastrada para o município {municipio} não cobre {rotulo} inteiro.",
                    DISP_REGRA,
                )
            )
        elif situacao == "sobrepostas":
            bloqueios.append(
                BloqueioIss(
                    "regra_municipio_sobreposta",
                    f"Há mais de uma regra do município {municipio} vigente em {rotulo}.",
                    DISP_REGRA,
                )
            )

    incluidas: list[NotaApurada] = []
    avisos: list[AvisoIss] = []
    sem_aliquota: dict[str, list[str]] = {}
    sem_aliquota_parcial: set[str] = set()
    aliquota_sobreposta: set[str] = set()
    total = Decimal("0.00")

    if apura_por_nota:
        escrituracoes = _escrituracoes_da_competencia(empresa, ano, mes)
        anotadas = _canceladas(empresa, ano, mes)
        # Uma consulta de alíquotas para o município inteiro (A6), indexada por subitem.
        por_subitem = _aliquotas_do_municipio(empresa.escritorio, municipio)
        for esc in escrituracoes:
            # Retido, exportação, imune e fora da lista seguem outro caminho e não somam aqui
            # (HI-82, HI-86). Outro município não soma, mas pode estar com a natureza errada (A3).
            if esc.natureza == NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO:
                aviso = _aviso_natureza_incompativel(esc.vinculo.documento, anotadas, municipio)
                if aviso is not None:
                    avisos.append(aviso)
                continue
            # Só o ISS devido pelo prestador entra (HI-82).
            if esc.natureza != NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR:
                continue
            documento = esc.vinculo.documento
            campos = campos_iss_do_documento(documento)
            faltantes = _faltantes_da_apuracao(campos)
            if campos.erro_leitura or faltantes:
                detalhe = (
                    f"XML ilegível ({campos.erro_leitura})"
                    if campos.erro_leitura
                    else f"campo(s) ausente(s) ou ilegível(is): {', '.join(faltantes)}"
                )
                bloqueios.append(_bloqueio_nota(documento, detalhe))
                continue
            if _cancelada(documento, anotadas):
                bloqueios.append(
                    BloqueioIss(
                        "nota_cancelada_escriturada",
                        f"Nota {_numero(documento)} foi cancelada depois de escriturada como ISS "
                        "devido. Estorne a escrituração (com motivo) antes de apurar.",
                        DISP_CANCELADA,
                    )
                )
                continue
            if campos.tp_ret_issqn in ("2", "3"):
                bloqueios.append(
                    BloqueioIss(
                        "nota_retida_com_natureza_devida",
                        f"Nota {_numero(documento)} está escriturada como ISS devido pelo "
                        f"prestador, mas o XML traz retenção (tpRetISSQN {campos.tp_ret_issqn}). "
                        "Corrija a natureza: a apuração não soma a nota nos dois lados.",
                        DISP_RETIDO,
                    )
                )
                continue
            if campos.c_loc_incid != municipio:
                avisos.append(
                    AvisoIss(
                        "incidencia_em_outro_municipio",
                        f"Nota {_numero(documento)} está escriturada como ISS devido pelo "
                        "prestador, "
                        f"mas o local de incidência (cLocIncid {campos.c_loc_incid}) não é o "
                        f"município do estabelecimento ({municipio}). Fora do total: confira a "
                        "natureza.",
                        DISP_BASE_TOTAL,
                    )
                )
                continue

            cobrindo, parcial = _cobertura_do_mes(por_subitem.get(campos.subitem, []), ano, mes)
            if len(cobrindo) > 1:
                # Não deveria existir: o cadastro recusa a sobreposição. Se existir, não se escolhe.
                aliquota_sobreposta.add(campos.subitem)
                continue
            if not cobrindo:
                sem_aliquota.setdefault(campos.subitem, []).append(_numero(documento))
                if parcial:
                    sem_aliquota_parcial.add(campos.subitem)
                continue
            aliquota = cobrindo[0]

            # Esperado = vBC × alíquota cadastrada ÷ 100, em precisão exata (sem arredondar
            # no meio). `vBC` é a base de conferência declarada no código (DL-076, item 5).
            with localcontext(_CONTEXTO_EXATO):
                esperado = campos.v_bc * aliquota.percentual / Decimal("100")
                diferenca = campos.v_iss_qn - esperado
            conferida = abs(diferenca) <= TOLERANCIA
            aviso_base = divergencia_de_base(campos)
            incluidas.append(
                NotaApurada(
                    identificador=documento.identificador,
                    numero=_numero(documento),
                    data_competencia=esc.data_competencia,
                    c_loc_incid=campos.c_loc_incid,
                    subitem=campos.subitem,
                    v_bc=campos.v_bc,
                    v_iss_qn=campos.v_iss_qn,
                    aliquota_cadastrada=aliquota.percentual,
                    esperado=esperado,
                    diferenca=diferenca,
                    conferida=conferida,
                    avisos=(aviso_base,) if aviso_base else (),
                    p_aliq_aplic=campos.p_aliq_aplic,
                    tomador_documento=documento.tomador_documento,
                    tomador_nome=documento.tomador_nome,
                )
            )
            total += campos.v_iss_qn

        # HI-89 (A2): notas prestadas da competência ainda não escrituradas ficam fora do total.
        # Aviso forte, não bloqueio: a guia sai das notas no portal, e esta conta é conferência.
        pendentes = _notas_nao_escrituradas(empresa, ano, mes)
        if pendentes:
            numeros = ", ".join(_numero(nota.documento) for nota in pendentes)
            avisos.append(
                AvisoIss(
                    CODIGO_NOTAS_NAO_ESCRITURADAS,
                    f"{len(pendentes)} nota(s) prestada(s) na competência ainda não "
                    f"escriturada(s) ou em rascunho, fora deste total: {numeros}. A apuração "
                    "soma só as notas efetivadas: escriture ou efetive essas notas e confira "
                    "antes de guiar.",
                    DISP_ESCRITURACAO,
                )
            )

    if aliquota_sobreposta:
        bloqueios.append(
            BloqueioIss(
                "aliquota_sobreposta",
                f"Há mais de uma alíquota vigente em {rotulo} para o(s) subitem(ns): "
                f"{', '.join(sorted(aliquota_sobreposta))}. Encerre a vigência de uma delas.",
                DISP_CONFERENCIA,
            )
        )
    if sem_aliquota:
        listas = "; ".join(
            f"{subitem} (notas {', '.join(numeros)})"
            for subitem, numeros in sorted(sem_aliquota.items())
        )
        parcial_txt = (
            " Há alíquota cadastrada que cobre só parte do mês; a competência precisa de uma "
            "alíquota que cubra o mês inteiro."
            if sem_aliquota_parcial
            else ""
        )
        bloqueios.append(
            BloqueioIss(
                "subitem_sem_aliquota_vigente",
                f"Sem alíquota cadastrada que cubra {rotulo} inteiro para o(s) subitem(ns): "
                f"{listas}.{parcial_txt} Cadastre a alíquota do município (HI-82).",
                DISP_CONFERENCIA,
            )
        )

    if bloqueios:
        raise IssRecusado(bloqueios, notas_fixo)

    # Vencimentos nominais: dia do mês SEGUINTE à competência (Decreto 1.667/2018, Anexo I).
    # Dia não útil passa para o primeiro dia útil seguinte, e o produto não calcula feriado:
    # a regra vai como texto. `regra` existe aqui porque, sem ela, houve bloqueio acima.
    ano_venc, mes_venc = _mes_seguinte(ano, mes)
    vencimento_proprio = date(ano_venc, mes_venc, regra.dia_vencimento_proprio)
    vencimento_retido = date(ano_venc, mes_venc, regra.dia_vencimento_retido)

    aviso_multa = None
    if hoje > vencimento_proprio:
        aviso_multa = (
            f"Vencimento {_data_br(vencimento_proprio)} já passou. Em atraso, incidem atualização "
            "monetária, multa de mora de 0,33% ao dia até o 30º dia e 10% depois, e juros de "
            "1% ao mês ou fração (LC 285/2013, art. 142). O valor não é calculado aqui; confira "
            "na guia."
        )

    memoria = (
        PassoIss(
            1,
            f"Competência {rotulo}; regime do ISS '{regime.get_regime_display()}' em {ano}; "
            f"município do estabelecimento {municipio}",
            municipio,
            DISP_REGIME,
        ),
        PassoIss(
            2,
            "Vencimento do ISS próprio (dia do mês seguinte) e do retido",
            f"próprio dia {regra.dia_vencimento_proprio}: {data_nominal_br(vencimento_proprio)}; "
            f"retido dia {regra.dia_vencimento_retido}: {data_nominal_br(vencimento_retido)}; "
            "datas nominais",
            DISP_REGRA,
        ),
        PassoIss(
            3,
            "Notas escrituradas como ISS devido pelo prestador, incidentes no município, "
            "na competência",
            str(len(incluidas)),
            DISP_BASE_TOTAL,
        ),
        PassoIss(
            4,
            "Total a recolher = soma do vISSQN das notas incluídas (não se recalcula)",
            str(total),
            DISP_BASE_TOTAL,
        ),
        PassoIss(
            5,
            "Conferência por nota: esperado = vBC × alíquota cadastrada ÷ 100; diferença acima "
            "de R$ 0,01 vira pendência, com os dois valores",
            f"{sum(1 for n in incluidas if not n.conferida)} pendência(s)",
            DISP_CONFERENCIA,
        ),
    )

    return ApuracaoIss(
        empresa_id=empresa.pk,
        ano=ano,
        mes=mes,
        municipio_ibge=municipio,
        nome_municipio=regra.nome,
        regime=regime.regime,
        total=total,
        notas=tuple(incluidas),
        avisos=tuple(avisos),
        vencimento_proprio=vencimento_proprio,
        vencimento_retido=vencimento_retido,
        regra_dia_nao_util=regra.regra_dia_nao_util,
        memoria=memoria,
        aviso_multa=aviso_multa,
    )


# ---------------------------------------------------------------------------
# Relatórios (DL-076, itens 6 e 7)
# ---------------------------------------------------------------------------


def _nota_de_relatorio(esc, anotadas: dict[int, bool]) -> NotaDeRelatorio:
    documento = esc.vinculo.documento
    campos = campos_iss_do_documento(documento)
    # Só ausente que o produto exige alerta: campo opcional do XSD ausente é normal (A11).
    ausentes = ausentes_que_alertam(campos) + tuple(campos.invalidos)
    if campos.erro_leitura:
        ausentes = (f"XML ilegível: {campos.erro_leitura}",)
    return NotaDeRelatorio(
        identificador=documento.identificador,
        numero=_numero(documento),
        data_competencia=esc.data_competencia,
        cancelada=_cancelada(documento, anotadas),
        tomador_documento=documento.tomador_documento,
        tomador_nome=documento.tomador_nome,
        c_loc_incid=campos.c_loc_incid,
        subitem=campos.subitem,
        v_bc=campos.v_bc,
        p_aliq_aplic=campos.p_aliq_aplic,
        v_iss_qn=campos.v_iss_qn,
        tp_ret_issqn=campos.tp_ret_issqn,
        ausentes=ausentes,
    )


def _grupos(
    notas: list[NotaDeRelatorio], municipio_de: Callable[[str | None], dict]
) -> tuple[GrupoMunicipal, ...]:
    """Totais por município de incidência. Nota sem valor vai para `incompletas`, nunca zero."""
    por_municipio: dict[str | None, list[NotaDeRelatorio]] = {}
    for nota in notas:
        por_municipio.setdefault(nota.c_loc_incid, []).append(nota)
    grupos = []
    for municipio in sorted(por_municipio, key=lambda m: (m is None, m or "")):
        linhas = por_municipio[municipio]
        validas = [n for n in linhas if n.v_iss_qn is not None]
        total = sum((n.v_iss_qn for n in validas), Decimal("0.00"))
        incompletas = tuple(n.numero for n in linhas if n.v_iss_qn is None)
        grupos.append(
            GrupoMunicipal(
                municipio_ibge=municipio,
                total=total,
                incompletas=incompletas,
                **municipio_de(municipio),
            )
        )
    return tuple(grupos)


def relatorio_iss_retido_sofrido(empresa: Empresa, ano: int, mes: int) -> RelatorioRetidoSofrido:
    """ISS retido sofrido (HI-86), para empresa de QUALQUER regime.

    Notas da competência escrituradas como "ISS retido" e com tpRetISSQN 2 ou 3. O total
    por município é a soma do valor retido. O retido não entra no ISS a recolher do
    prestador. O vencimento do retido (dia 15, em Palmas) é informativo: quem recolhe é o
    tomador, no município de incidência.
    """
    _validar_competencia(ano, mes)
    anotadas = _canceladas(empresa, ano, mes)
    avisos: list[AvisoIss] = []
    notas: list[NotaDeRelatorio] = []
    for esc in _escrituracoes_da_competencia(empresa, ano, mes):
        if esc.natureza != NaturezaOperacao.PRESTADO_ISS_RETIDO:
            continue
        nota = _nota_de_relatorio(esc, anotadas)
        if nota.cancelada:
            avisos.append(
                AvisoIss(
                    "cancelada_escriturada",
                    f"Nota {nota.numero} foi cancelada depois de escriturada: fora do total.",
                    DISP_CANCELADA,
                )
            )
            continue
        if nota.tp_ret_issqn not in ("2", "3"):
            avisos.append(
                AvisoIss(
                    "retencao_nao_confirmada",
                    f"Nota {nota.numero} está escriturada como retida, mas o XML traz "
                    f"tpRetISSQN {nota.tp_ret_issqn or 'ausente'}: fora deste relatório. Confira.",
                    DISP_RETIDO,
                )
            )
            continue
        notas.append(nota)

    def _vencimento(municipio: str | None) -> dict:
        if municipio is None:
            avisos.append(
                AvisoIss(
                    "sem_municipio_de_incidencia",
                    "Há nota retida sem cLocIncid: o vencimento do retido não é calculado.",
                    DISP_REGRA,
                )
            )
            return {"aviso": "sem cLocIncid"}
        regra, situacao = _regra_do_mes(municipio, ano, mes)
        if regra is None:
            if situacao == "ausente":
                texto = (
                    f"Regra do município {municipio} não cadastrada: vencimento do retido "
                    "não calculado."
                )
            else:
                texto = (
                    f"Regra do município {municipio} não cobre {_rotulo(ano, mes)}: "
                    "vencimento não calculado."
                )
            avisos.append(AvisoIss("regra_municipio_indisponivel", texto, DISP_REGRA))
            return {"aviso": texto}
        ano_venc, mes_venc = _mes_seguinte(ano, mes)
        return {"vencimento_retido": date(ano_venc, mes_venc, regra.dia_vencimento_retido)}

    return RelatorioRetidoSofrido(
        ano=ano,
        mes=mes,
        notas=tuple(notas),
        grupos=_grupos(notas, _vencimento),
        avisos=tuple(avisos),
    )


def relatorio_iss_outros_municipios(
    empresa: Empresa, ano: int, mes: int
) -> RelatorioOutrosMunicipios:
    """ISS devido a outro município (HI-85): por município de incidência, com os valores da
    própria nota, sem cálculo. Avisos de alíquota fora de 2% a 5% e de incidência possivelmente
    errada (subitem fora das exceções do art. 3º, com local diferente do estabelecimento).
    """
    _validar_competencia(ano, mes)
    anotadas = _canceladas(empresa, ano, mes)
    regime = _regime_do_exercicio(empresa, ano)
    municipio_prestador = regime.municipio_ibge if regime is not None else None
    avisos: list[AvisoIss] = []
    if municipio_prestador is None:
        avisos.append(
            AvisoIss(
                "estabelecimento_sem_municipio",
                f"Não há município do estabelecimento para {ano}: o aviso de incidência "
                "não é calculado.",
                DISP_ART_3,
            )
        )
    notas: list[NotaDeRelatorio] = []
    for esc in _escrituracoes_da_competencia(empresa, ano, mes):
        if esc.natureza != NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO:
            continue
        nota = _nota_de_relatorio(esc, anotadas)
        notas.append(nota)
        if nota.cancelada:
            continue
        aviso_natureza = _aviso_natureza_incompativel(
            esc.vinculo.documento, anotadas, municipio_prestador
        )
        if aviso_natureza is not None:
            avisos.append(aviso_natureza)
        p = nota.p_aliq_aplic
        if p is not None and not (Decimal("2") <= p <= Decimal("5")):
            avisos.append(
                AvisoIss(
                    "aliquota_fora_de_2_a_5",
                    f"Nota {nota.numero}: alíquota aplicada {p}% fora de 2% a 5%.",
                    DISP_FAIXA,
                )
            )
        if nota.subitem is not None and excecao_do_art_3(nota.subitem) is None:
            if municipio_prestador is not None and nota.c_loc_incid != municipio_prestador:
                avisos.append(
                    AvisoIss(
                        "incidencia_possivelmente_errada",
                        f"Nota {nota.numero}: subitem {nota.subitem} não está nas exceções "
                        "do art. 3º da LC 116, e o local de incidência "
                        f"({nota.c_loc_incid}) não é o "
                        f"município do estabelecimento ({municipio_prestador}). Confira a "
                        "natureza e o cLocIncid.",
                        DISP_ART_3,
                    )
                )

    ativas = [n for n in notas if not n.cancelada]
    return RelatorioOutrosMunicipios(
        ano=ano,
        mes=mes,
        notas=tuple(notas),
        grupos=_grupos(ativas, lambda _m: {}),
        avisos=tuple(avisos),
    )


# ---------------------------------------------------------------------------
# Cadastros: alíquota por escritório (HI-82)
# ---------------------------------------------------------------------------

_CAMPOS_ALIQUOTA = (
    "municipio_ibge",
    "subitem",
    "percentual",
    "fonte",
    "inicio_vigencia",
    "fim_vigencia",
)


def _municipio(valor) -> str:
    if not isinstance(valor, str) or not _PADRAO_MUNICIPIO.fullmatch(valor.strip()):
        raise EntradaInvalidaIss("O código IBGE do município tem 7 dígitos numéricos.")
    return valor.strip()


def _subitem(valor) -> str:
    texto = valor.strip() if isinstance(valor, str) else ""
    if not _PADRAO_SUBITEM.fullmatch(texto):
        raise EntradaInvalidaIss(
            "O subitem tem o formato II.SS da lista da LC 116, com item de 01 a 40 "
            "(ex.: 17.01, 07.02)."
        )
    return texto


def _percentual(valor) -> Decimal:
    """Percentual em pontos (5 = 5%), com até 4 casas. Nunca float (AGENTS.md §10)."""
    if isinstance(valor, bool) or isinstance(valor, float) or valor is None:
        raise EntradaInvalidaIss(
            "Informe a alíquota em percentual (número decimal, sem ponto flutuante)."
        )
    try:
        numero = valor if isinstance(valor, Decimal) else Decimal(str(valor).strip())
    except (InvalidOperation, ValueError) as exc:
        raise EntradaInvalidaIss("A alíquota precisa ser um número decimal.") from exc
    if not numero.is_finite():
        raise EntradaInvalidaIss("A alíquota precisa ser um número decimal finito.")
    if numero.as_tuple().exponent < -4:
        raise EntradaInvalidaIss("A alíquota tem no máximo 4 casas decimais.")
    if numero <= 0:
        raise EntradaInvalidaIss("A alíquota precisa ser maior que zero.")
    return numero.quantize(_QUATRO_CASAS)


def _faixa_da_aliquota(subitem: str, percentual: Decimal) -> AvisoIss | None:
    """Recusa fora de 2% a 5% (LC 116, art. 8º, II, e art. 8º-A). Devolve o aviso da exceção."""
    if percentual > Decimal("5"):
        raise EntradaInvalidaIss(
            f"Alíquota de {percentual}% acima do máximo de 5% (LC 116/2003, art. 8º, II)."
        )
    if percentual < Decimal("2"):
        if subitem in SUBITENS_EXCECAO_DO_MINIMO:
            return AvisoIss(
                "aliquota_abaixo_do_minimo_excecao",
                f"Alíquota de {percentual}% abaixo do mínimo de 2%. O subitem {subitem} está na "
                "exceção do § 1º do art. 8º-A da LC 116: entra, com este aviso.",
                DISP_FAIXA,
            )
        raise EntradaInvalidaIss(
            f"Alíquota de {percentual}% abaixo do mínimo de 2% (LC 116/2003, art. 8º-A). A exceção "
            "vale só para os subitens 7.02, 7.05 e 16.01."
        )
    return None


def _validar_aliquota(
    dados: dict, atual: AliquotaIssMunicipal | None
) -> tuple[dict, AvisoIss | None]:
    """Valores válidos da alíquota. `atual` preenche o que não veio (PATCH)."""
    base = {
        "municipio_ibge": atual.municipio_ibge if atual else None,
        "subitem": atual.subitem if atual else None,
        "percentual": atual.percentual if atual else None,
        "fonte": atual.fonte if atual else "",
        "inicio_vigencia": atual.inicio_vigencia if atual else None,
        "fim_vigencia": atual.fim_vigencia if atual else None,
    }
    base.update({chave: valor for chave, valor in dados.items() if chave in _CAMPOS_ALIQUOTA})

    municipio = _municipio(base["municipio_ibge"])
    subitem = _subitem(base["subitem"])
    percentual = _percentual(base["percentual"])
    aviso = _faixa_da_aliquota(subitem, percentual)

    fonte = base["fonte"].strip() if isinstance(base["fonte"], str) else ""
    if not fonte:
        raise EntradaInvalidaIss("Informe a fonte da alíquota (dispositivo, documento e data).")
    if len(fonte) > 1000:
        raise EntradaInvalidaIss("A fonte tem no máximo 1000 caracteres.")

    inicio, fim = base["inicio_vigencia"], base["fim_vigencia"]
    if not isinstance(inicio, date):
        raise EntradaInvalidaIss("Informe o início da vigência (AAAA-MM-DD).")
    if fim is not None and not isinstance(fim, date):
        raise EntradaInvalidaIss("O fim da vigência tem de ser uma data (AAAA-MM-DD).")
    # Limite sensato para a data de vigência (A9): o erro de digitação (ano 0001, 9999) não
    # vira alíquota. Não é regra legal: é só a faixa em que a alíquota pode ter sido cadastrada.
    for nome, data in (("início", inicio), ("fim", fim)):
        if data is not None and not _VIGENCIA_ALIQUOTA_MINIMA <= data <= _VIGENCIA_ALIQUOTA_MAXIMA:
            raise EntradaInvalidaIss(
                f"A data de {nome} da vigência tem de estar entre 2000 e 2100."
            )
    if fim is not None and fim < inicio:
        raise EntradaInvalidaIss("O fim da vigência é anterior ao início.")

    return (
        {
            "municipio_ibge": municipio,
            "subitem": subitem,
            "percentual": percentual,
            "fonte": fonte,
            "inicio_vigencia": inicio,
            "fim_vigencia": fim,
        },
        aviso,
    )


def _checar_sobreposicao_aliquota(escritorio: Escritorio, valores: dict, excluir_pk=None) -> None:
    """Recusa vigência que se cruza com outra alíquota do mesmo município e subitem, no escritório.

    A checagem é feita com o escritório travado (quem chama trava antes): sem a trava, duas
    inclusões simultâneas passariam juntas pela checagem.
    """
    consulta = AliquotaIssMunicipal.objects.filter(
        escritorio=escritorio,
        municipio_ibge=valores["municipio_ibge"],
        subitem=valores["subitem"],
    )
    if excluir_pk is not None:
        consulta = consulta.exclude(pk=excluir_pk)
    consulta = consulta.filter(
        Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=valores["inicio_vigencia"])
    )
    if valores["fim_vigencia"] is not None:
        consulta = consulta.filter(inicio_vigencia__lte=valores["fim_vigencia"])
    if consulta.exists():
        raise IssConflito(
            "Já há alíquota deste município e subitem com vigência sobreposta. Encerre a "
            "vigência anterior (informando o fim) antes de cadastrar a nova."
        )


def _snapshot_aliquota(aliquota: AliquotaIssMunicipal) -> dict:
    return {
        "municipio_ibge": aliquota.municipio_ibge,
        "subitem": aliquota.subitem,
        "percentual": str(aliquota.percentual),
        "fonte": aliquota.fonte,
        "inicio_vigencia": aliquota.inicio_vigencia.isoformat(),
        "fim_vigencia": aliquota.fim_vigencia.isoformat() if aliquota.fim_vigencia else None,
    }


def _gravar_aliquota(objeto: AliquotaIssMunicipal) -> None:
    """save() com savepoint. Violação de restrição de entrada vira 400; conflito, 409."""
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        nome = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if nome in _RESTRICOES_DE_ENTRADA_ALIQUOTA:
            raise EntradaInvalidaIss("Dados da alíquota fora da regra.") from exc
        raise


@transaction.atomic
def cadastrar_aliquota(
    escritorio: Escritorio, dados: dict, usuario, request=None
) -> tuple[AliquotaIssMunicipal, tuple[AvisoIss, ...]]:
    """Cadastra alíquota do escritório. Devolve (alíquota, avisos). Recusa 2% a 5% fora da
    exceção, sobreposição e dado fora da regra; grava a trilha na mesma transação."""
    valores, aviso = _validar_aliquota(dados, None)
    travado = Escritorio.objects.select_for_update().get(pk=escritorio.pk)
    _checar_sobreposicao_aliquota(travado, valores)
    objeto = AliquotaIssMunicipal(escritorio=travado, criada_por=usuario, **valores)
    _gravar_aliquota(objeto)
    registrar(
        acao="aliquota_iss.criada",
        usuario=usuario,
        escritorio=travado,
        objeto=objeto,
        request=request,
        detalhes={"depois": _snapshot_aliquota(objeto)},
    )
    return objeto, ((aviso,) if aviso else ())


@transaction.atomic
def alterar_aliquota(
    aliquota: AliquotaIssMunicipal, dados: dict, usuario, request=None
) -> tuple[AliquotaIssMunicipal, tuple[AvisoIss, ...]]:
    """Altera a alíquota (inclusive o fim da vigência, que a encerra). Trilha com antes e
    depois. Não há exclusão: encerrar a vigência é o caminho, para não perder o histórico."""
    travado = Escritorio.objects.select_for_update().get(pk=aliquota.escritorio_id)
    atual = AliquotaIssMunicipal.objects.select_for_update(of=("self",)).get(
        pk=aliquota.pk, escritorio=travado
    )
    antes = _snapshot_aliquota(atual)
    valores, aviso = _validar_aliquota(dados, atual)
    _checar_sobreposicao_aliquota(travado, valores, excluir_pk=atual.pk)
    for nome, valor in valores.items():
        setattr(atual, nome, valor)
    atual.alterada_por = usuario
    _gravar_aliquota(atual)
    registrar(
        acao="aliquota_iss.alterada",
        usuario=usuario,
        escritorio=travado,
        objeto=atual,
        request=request,
        detalhes={"antes": antes, "depois": _snapshot_aliquota(atual)},
    )
    return atual, ((aviso,) if aviso else ())


# ---------------------------------------------------------------------------
# Cadastros: regra do município (HI-83), global
# ---------------------------------------------------------------------------

_CAMPOS_REGRA = (
    "municipio_ibge",
    "nome",
    "dia_vencimento_proprio",
    "dia_vencimento_retido",
    "regra_dia_nao_util",
    "fonte",
    "inicio_vigencia",
    "fim_vigencia",
)


def _dia(valor, nome: str) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int) or not 1 <= valor <= 28:
        raise EntradaInvalidaIss(f"{nome}: dia de 1 a 28.")
    return valor


def _validar_regra(dados: dict) -> dict:
    """Valores de uma regra do município. Sem `atual`: a regra só é cadastrada, nunca parcial."""
    # `fim_vigencia` é opcional: vigência em aberto é o caso normal de Palmas.
    obrigatorios = [nome for nome in _CAMPOS_REGRA if nome != "fim_vigencia"]
    faltam = [nome for nome in obrigatorios if dados.get(nome) in (None, "")]
    if faltam:
        raise EntradaInvalidaIss(f"Campos obrigatórios da regra: {', '.join(faltam)}.")
    inicio, fim = dados["inicio_vigencia"], dados.get("fim_vigencia")
    if not isinstance(inicio, date) or (fim is not None and not isinstance(fim, date)):
        raise EntradaInvalidaIss("As vigências são datas (AAAA-MM-DD).")
    if fim is not None and fim < inicio:
        raise EntradaInvalidaIss("O fim da vigência é anterior ao início.")
    return {
        "municipio_ibge": _municipio(dados["municipio_ibge"]),
        "nome": str(dados["nome"]).strip()[:120],
        "dia_vencimento_proprio": _dia(dados["dia_vencimento_proprio"], "dia do ISS próprio"),
        "dia_vencimento_retido": _dia(dados["dia_vencimento_retido"], "dia do ISS retido"),
        "regra_dia_nao_util": str(dados["regra_dia_nao_util"]).strip(),
        "fonte": str(dados["fonte"]).strip(),
        "inicio_vigencia": inicio,
        "fim_vigencia": fim,
    }


def _snapshot_regra(regra: RegraIssMunicipio) -> dict:
    return {
        "municipio_ibge": regra.municipio_ibge,
        "nome": regra.nome,
        "dia_vencimento_proprio": regra.dia_vencimento_proprio,
        "dia_vencimento_retido": regra.dia_vencimento_retido,
        "inicio_vigencia": regra.inicio_vigencia.isoformat(),
        "fim_vigencia": regra.fim_vigencia.isoformat() if regra.fim_vigencia else None,
    }


def _gravar_regra(objeto: RegraIssMunicipio) -> None:
    """save() com savepoint. Vigência repetida vira 409; dado fora da regra, 400."""
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        nome = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if nome == "regra_iss_unica_por_inicio":
            raise IssConflito("Já há regra deste município com este início de vigência.") from exc
        if nome in _RESTRICOES_DE_ENTRADA_REGRA:
            raise EntradaInvalidaIss("Dados da regra fora da regra.") from exc
        raise


@transaction.atomic
def cadastrar_regra_municipio(dados: dict, usuario, request=None) -> RegraIssMunicipio:
    """Cadastra a regra de um município, recusando vigência sobreposta à de outra regra do
    mesmo município. É o único caminho de escrita, sem rota de API: a regra é dado legal,
    e o cadastro dela não é tarefa de cliente. A trava é o `select_for_update` das regras do
    mesmo município, que tem a mesma função da trava de escritório dos cadastros de alíquota.
    """
    valores = _validar_regra(dados)
    list(
        RegraIssMunicipio.objects.select_for_update()
        .filter(municipio_ibge=valores["municipio_ibge"])
        .values_list("pk", flat=True)
    )
    consulta = RegraIssMunicipio.objects.filter(municipio_ibge=valores["municipio_ibge"]).filter(
        Q(fim_vigencia__isnull=True) | Q(fim_vigencia__gte=valores["inicio_vigencia"])
    )
    if valores["fim_vigencia"] is not None:
        consulta = consulta.filter(inicio_vigencia__lte=valores["fim_vigencia"])
    if consulta.exists():
        raise IssConflito(
            f"Já há regra do município {valores['municipio_ibge']} com vigência sobreposta."
        )
    objeto = RegraIssMunicipio(criada_por=usuario, **valores)
    _gravar_regra(objeto)
    registrar(
        acao="regra_iss_municipio.criada",
        usuario=usuario,
        escritorio=None,
        objeto=objeto,
        request=request,
        detalhes={"depois": _snapshot_regra(objeto)},
    )
    return objeto


# ---------------------------------------------------------------------------
# Cadastros: regime do ISS por empresa e exercício (HI-84)
# ---------------------------------------------------------------------------

_CAMPOS_REGIME = ("exercicio", "regime", "municipio_ibge")


def _validar_regime(dados: dict, atual: RegimeIssEmpresa | None) -> dict:
    base = {
        "exercicio": atual.exercicio if atual else None,
        "regime": atual.regime if atual else None,
        "municipio_ibge": atual.municipio_ibge if atual else None,
    }
    base.update({chave: valor for chave, valor in dados.items() if chave in _CAMPOS_REGIME})
    exercicio = base["exercicio"]
    if (
        isinstance(exercicio, bool)
        or not isinstance(exercicio, int)
        or not (_EXERCICIO_MINIMO <= exercicio <= _EXERCICIO_MAXIMO)
    ):
        raise EntradaInvalidaIss(
            f"Exercício inválido: {exercicio!r} (de {_EXERCICIO_MINIMO} a {_EXERCICIO_MAXIMO})."
        )
    if base["regime"] not in RegimeIss.values:
        raise EntradaInvalidaIss(
            "Regime do ISS fora do catálogo: alíquota, fixo de autônomo ou fixo de sociedade "
            "de profissionais."
        )
    return {
        "exercicio": exercicio,
        "regime": base["regime"],
        "municipio_ibge": _municipio(base["municipio_ibge"]),
    }


def _snapshot_regime(regime: RegimeIssEmpresa) -> dict:
    return {
        "exercicio": regime.exercicio,
        "regime": regime.regime,
        "municipio_ibge": regime.municipio_ibge,
    }


def _gravar_regime(objeto: RegimeIssEmpresa) -> None:
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        nome = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
        if nome == "regime_iss_unico_por_empresa_exercicio":
            raise IssConflito(
                "Já há regime do ISS cadastrado para esta empresa neste exercício. Altere o "
                "regime existente."
            ) from exc
        if nome in _RESTRICOES_DE_ENTRADA_REGIME:
            raise EntradaInvalidaIss("Dados do regime fora da regra.") from exc
        raise


@transaction.atomic
def cadastrar_regime(empresa: Empresa, dados: dict, usuario, request=None) -> RegimeIssEmpresa:
    valores = _validar_regime(dados, None)
    travada = travar_empresa(empresa)
    objeto = RegimeIssEmpresa(empresa=travada, criado_por=usuario, **valores)
    _gravar_regime(objeto)
    registrar(
        acao="regime_iss.criado",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=objeto,
        request=request,
        detalhes={"empresa_id": travada.pk, "depois": _snapshot_regime(objeto)},
    )
    return objeto


@transaction.atomic
def alterar_regime(
    regime: RegimeIssEmpresa, dados: dict, usuario, request=None
) -> RegimeIssEmpresa:
    travada = travar_empresa(regime.empresa)
    atual = RegimeIssEmpresa.objects.select_for_update(of=("self",)).get(
        pk=regime.pk, empresa=travada
    )
    antes = _snapshot_regime(atual)
    valores = _validar_regime(dados, atual)
    for nome, valor in valores.items():
        setattr(atual, nome, valor)
    atual.alterado_por = usuario
    _gravar_regime(atual)
    registrar(
        acao="regime_iss.alterado",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={"empresa_id": travada.pk, "antes": antes, "depois": _snapshot_regime(atual)},
    )
    return atual
