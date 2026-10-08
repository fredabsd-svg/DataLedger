"""RBT12 do Simples Nacional por mercado — DL-074, frente A (domínio).

NÍVEL 1 (AGENTS.md §3.1): o RBT12 decide a faixa do DAS. Contrato em
docs/planos/DL-074-receita-e-rbt12-do-simples.md (itens 5 e 6; critérios 2 a 5,
8, 9 e 11). Base e hipóteses: consulta RBT12 ao contador-senior (08/10/2026),
HI-64 a HI-67 e HI-70 em docs/projeto/requisitos.md. Não é transmissão: é
pré-apuração para o contador conferir contra o PGDAS-D.

Regra do art. 22 da Res. CGSN 140 (texto lido, consulta item 2 e item 1):

- § 1º (regra geral): RBT12 = receita total dos 12 meses ANTERIORES ao PA.
  Meses anteriores à abertura contam como zero e não exigem confirmação.
- § 2º (primeiro mês de atividade): RBT12 = receita do PRÓPRIO mês × 12.
- § 3º (2º ao 12º mês de atividade, abertura no ano da opção): RBT12 = média das
  receitas dos meses de atividade ANTERIORES ao PA × 12. Mês sem receita
  entra como zero no número de meses.
- § 4º (2º ao 12º mês de atividade, abertura no ano imediatamente anterior ao
  da opção): mesma conta do § 3º; § 1º a partir do 13º mês.

"Mês de atividade" 1 é o mês da abertura no CNPJ. Fração de mês conta como mês
inteiro. O "ano da opção" é o ano do período do Simples vigente no PA
(`HistoricoRegimeTributario`). Sem período, a apuração recusa.

A proporcional vale enquanto o PA for até o 12º mês de atividade, mesmo que o PA
caia no ano seguinte ao da opção (HI-76, achado A1 da auditoria rodada 1: a
regra dos 12 primeiros meses atravessa a virada do ano). O rótulo § 3º ou § 4º
depende só do ano da abertura em relação ao da opção.

Só com TODOS os meses exigidos confirmados (critério 5) o RBT12 é apurado. Caso
contrário, o resultado é "não apurável" e lista os meses. A lista vem de
`apps.fiscal.receita.situacao_do_mes`, a fonte única da confirmação.

Sem arredondamento: a divisão do § 3º/§ 4º pode dar dízima, e o resultado fica
com precisão de 60 dígitos significativos, sem `quantize`. Nenhum valor é
truncado a centavos aqui. A conferência com o PGDAS-D é do contador.

Limites: são DADO com fonte e vigência (`LIMITES`, HI-70). Cada entrada traz
valor, dispositivo, fonte, início e fim. Todas terminam em 31/12/2026. Valores de
2027 não entram. A apuração de 2027 em diante é RECUSADA com mensagem nomeada,
porque depende da Res. CGSN 190/2026, que não foi lida.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, localcontext

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import receita as recibo
from apps.fiscal.models import MercadoReceita

# Mercados que têm RBT12, limite e sublimite próprios (HI-67).
MERCADOS = (MercadoReceita.INTERNO, MercadoReceita.EXTERNO)

# Último ano com limites cadastrados e primeiro sem (HI-70).
ANO_ULTIMO_COM_LIMITES = 2026
ANO_RECUSADO = 2027

# Precisão da divisão do § 3º/§ 4º. Não é arredondamento de centavos: é o
# número de dígitos significativos guardados antes de qualquer tratamento.
_PRECISAO_DA_MEDIA = 60
_LIMITE_DE_EXCESSO = Decimal("0.20")


class ApuracaoRecusada(Exception):
    """Recusa nomeada: a apuração não pode ser feita, e a mensagem diz por quê."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


# ---------------------------------------------------------------------------
# Limites como DADO, com vigência e fonte (HI-70)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LimiteVigente:
    chave: str
    valor: Decimal
    # True: o valor é por MÊS e vale só no ano de início (valor × meses, fração = mês).
    por_mes_no_ano_de_inicio: bool
    dispositivo: str
    fonte: str
    inicio: date
    fim: date


_FONTE_RES_140 = (
    "Res. CGSN 140/2018 consolidada com anotações até a Res. 190/2026 (PDF íntegro, "
    "lido na consulta de 08/10/2026). Início de 2018 não conferido: LC 155/2016, art. 11."
)

LIMITES: tuple[LimiteVigente, ...] = (
    LimiteVigente(
        chave="limite_anual",
        valor=Decimal("4800000.00"),
        por_mes_no_ano_de_inicio=False,
        dispositivo="LC 123, art. 3º, II; Res. CGSN 140, art. 2º, I, 'b' e § 1º",
        fonte=_FONTE_RES_140,
        inicio=date(2018, 1, 1),
        fim=date(2026, 12, 31),
    ),
    LimiteVigente(
        chave="limite_proporcional_mes",
        valor=Decimal("400000.00"),
        por_mes_no_ano_de_inicio=True,
        dispositivo="Res. CGSN 140, art. 3º; LC 123, art. 3º, § 2º",
        fonte=_FONTE_RES_140,
        inicio=date(2018, 1, 1),
        fim=date(2026, 12, 31),
    ),
    LimiteVigente(
        chave="sublimite_anual",
        valor=Decimal("3600000.00"),
        por_mes_no_ano_de_inicio=False,
        dispositivo=(
            "Res. CGSN 140, art. 9º, § 1º; LC 123, arts. 13-A e 19, § 4º; "
            "Portaria CGSN 54/2025, art. 2º"
        ),
        fonte=(
            "Portaria CGSN 54/2025 (DOU 19/11/2025, cópia). Vale para todas as UFs e o DF em 2026 "
            "(HI-70). A UF não é modelada; o sublimite de 1,8 mi não é usado (nenhuma UF optou)."
        ),
        inicio=date(2026, 1, 1),
        fim=date(2026, 12, 31),
    ),
    LimiteVigente(
        chave="sublimite_proporcional_mes",
        valor=Decimal("300000.00"),
        por_mes_no_ano_de_inicio=True,
        dispositivo="Res. CGSN 140, art. 12, § 2º; LC 123, art. 3º, § 11",
        fonte=_FONTE_RES_140,
        inicio=date(2018, 1, 1),
        fim=date(2026, 12, 31),
    ),
)


def limite_vigente(chave: str, referencia: date) -> LimiteVigente | None:
    """O limite `chave` com vigência cobrindo `referencia`, ou None (sem cadastro)."""
    for limite in LIMITES:
        if limite.chave == chave and limite.inicio <= referencia <= limite.fim:
            return limite
    return None


# ---------------------------------------------------------------------------
# Resultado
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Aviso:
    """Aviso com o dispositivo que o motiva. `mercado` é None quando vale para a empresa."""

    codigo: str
    mensagem: str
    dispositivo: str
    mercado: str | None = None


@dataclass(frozen=True)
class MesDaJanela:
    ano: int
    mes: int
    na_atividade: bool
    situacao: str
    interno: Decimal
    externo: Decimal

    def receita(self, mercado: str) -> Decimal:
        return self.interno if mercado == MercadoReceita.INTERNO else self.externo


@dataclass(frozen=True)
class RbtPorMercado:
    mercado: str
    # None quando não apurável (há mês exigido sem confirmação).
    apurado: Decimal | None
    soma: Decimal
    # Número de meses que entraram na conta (divisor do § 3º/§ 4º; 1 no § 2º; 12 no § 1º).
    divisor: int | None
    acumulado_no_ano: Decimal | None
    teto_limite: Decimal | None
    teto_sublimite: Decimal | None

    @property
    def apuravel(self) -> bool:
        return self.apurado is not None


@dataclass(frozen=True)
class Rbt12:
    ano: int
    mes: int
    data_abertura: date
    ano_opcao: int
    regra: str
    janela: tuple[MesDaJanela, ...]
    pendentes_da_janela: tuple[tuple[int, int, str], ...]
    pendentes_do_ano: tuple[tuple[int, int, str], ...]
    por_mercado: dict[str, RbtPorMercado]
    modo_limite: str
    avisos: tuple[Aviso, ...] = field(default_factory=tuple)

    @property
    def apuravel(self) -> bool:
        return not self.pendentes_da_janela

    def de(self, mercado: str) -> RbtPorMercado:
        return self.por_mercado[mercado]


# ---------------------------------------------------------------------------
# Auxiliares de calendário
# ---------------------------------------------------------------------------


def _indice(ano: int, mes: int) -> int:
    return ano * 12 + (mes - 1)


def _do_indice(indice: int) -> tuple[int, int]:
    return indice // 12, indice % 12 + 1


def _ultimo_dia(ano: int, mes: int) -> date:
    proximo = _do_indice(_indice(ano, mes) + 1)
    return date.fromordinal(date(proximo[0], proximo[1], 1).toordinal() - 1)


def periodos_do_simples(empresa: Empresa) -> list:
    """Todos os períodos do Simples da empresa, do mais recente ao mais antigo.

    Lê uma vez para o lote do FS12 do ano (A9 da auditoria DL-075): `_escolher_periodo`
    aplica a mesma regra de `_periodo_do_simples`, em memória, sem consultar por mês.
    """
    return list(
        HistoricoRegimeTributario.objects.filter(
            empresa=empresa, regime=RegimeTributario.SIMPLES_NACIONAL
        ).order_by("-vigencia_inicio", "-id")
    )


def _escolher_periodo(periodos: list, primeiro: date, ultimo: date):
    """Mesma escolha de `_periodo_do_simples`, sobre a lista lida por `periodos_do_simples`.

    Primeiro o período em aberto que começa até o fim do mês; se não houver, o período
    fechado que toca o mês. Os dois critérios são os da consulta ao banco, na mesma ordem.
    """
    for periodo in periodos:
        if periodo.vigencia_fim is None and periodo.vigencia_inicio <= ultimo:
            return periodo
    for periodo in periodos:
        if (
            periodo.vigencia_fim is not None
            and periodo.vigencia_inicio <= ultimo
            and periodo.vigencia_fim >= primeiro
        ):
            return periodo
    return None


def _periodo_do_simples(empresa: Empresa, ano: int, mes: int, periodos: list | None = None):
    """Período do Simples que toca algum dia do PA, ou None.

    Vale qualquer dia do mês, porque o PGDAS-D apura o mês inteiro. O ano da opção
    é o `vigencia_inicio` deste período. Com `periodos` (de `periodos_do_simples`), a
    escolha é feita em memória, sem consulta.
    """
    primeiro, ultimo = date(ano, mes, 1), _ultimo_dia(ano, mes)
    if periodos is not None:
        return _escolher_periodo(periodos, primeiro, ultimo)
    return (
        HistoricoRegimeTributario.objects.filter(
            empresa=empresa,
            regime=RegimeTributario.SIMPLES_NACIONAL,
            vigencia_inicio__lte=ultimo,
        )
        .filter(vigencia_fim__isnull=True)
        .order_by("-vigencia_inicio", "-id")
        .first()
        or HistoricoRegimeTributario.objects.filter(
            empresa=empresa,
            regime=RegimeTributario.SIMPLES_NACIONAL,
            vigencia_inicio__lte=ultimo,
            vigencia_fim__gte=primeiro,
        )
        .order_by("-vigencia_inicio", "-id")
        .first()
    )


def _mm_aaaa(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


# ---------------------------------------------------------------------------
# Cálculo
# ---------------------------------------------------------------------------


class _Mes:
    """Receita e situação de um mês, lidas uma vez por apuração."""

    def __init__(self, empresa: Empresa, ano: int, mes: int):
        self.ano, self.mes = ano, mes
        self.composicao = recibo.composicao_do_mes(empresa, ano, mes)
        confirmacao = recibo.confirmacao_do_mes(empresa, ano, mes)
        self.situacao = recibo.situacao_de(confirmacao, self.composicao)

    def receita(self, mercado: str) -> Decimal:
        return self.composicao.total(mercado)


def _regra_e_janela(ano: int, mes: int, abertura: date, ano_opcao: int):
    """(regra, lista de (ano, mês) da janela, em ordem). Ver a docstring do módulo."""
    indice_pa = _indice(ano, mes)
    indice_abertura = _indice(abertura.year, abertura.month)
    n = indice_pa - indice_abertura + 1  # mês de atividade do PA; 1 = mês da abertura

    # HI-76: a proporcional depende só de o PA estar até o 12º mês de atividade, e não
    # do ano do PA ser o ano da opção. A abertura pode ser do ano da opção (§ 3º) ou do
    # ano anterior a ela (§ 4º). Abertura posterior ao ano da opção (dado inconsistente)
    # cai na regra geral, como antes.
    if n <= 12 and abertura.year in (ano_opcao, ano_opcao - 1):
        if n == 1:
            return "§ 2º", [indice_pa]
        regra = "§ 3º" if abertura.year == ano_opcao else "§ 4º"
        return regra, list(range(indice_abertura, indice_pa))
    return "§ 1º", list(range(indice_pa - 12, indice_pa))


def _limites_do_ano(abertura: date, ano: int, mes: int):
    """(modo, teto do limite, teto do sublimite, dispositivos) de cada mercado.

    No ano da abertura o teto é proporcional: valor por mês × meses de atividade
    no ano, com fração de mês contada como mês inteiro (Res. CGSN 140, art. 3º).
    Nos anos seguintes é o valor cheio. Sem cadastro para o período → teto None.
    """
    referencia = date(ano, mes, 1)
    proporcional = abertura.year == ano
    meses = 12 - abertura.month + 1 if proporcional else None

    def teto(chave_cheia: str, chave_mes: str):
        if proporcional:
            por_mes = limite_vigente(chave_mes, referencia)
            return None if por_mes is None else por_mes.valor * meses
        cheio = limite_vigente(chave_cheia, referencia)
        return None if cheio is None else cheio.valor

    modo = f"proporcional ({meses} meses)" if proporcional else "cheio"
    return (
        modo,
        teto("limite_anual", "limite_proporcional_mes"),
        teto("sublimite_anual", "sublimite_proporcional_mes"),
    )


def _excesso(acumulado: Decimal, teto: Decimal) -> tuple[Decimal, bool]:
    """(fração do excesso sobre o teto, e se é "até 20%").

    Excesso até 20% quer dizer acumulado ≤ 1,20 × teto.
    """
    with localcontext() as contexto:
        contexto.prec = _PRECISAO_DA_MEDIA
        fracao = (acumulado - teto) / teto
    return fracao, fracao <= _LIMITE_DE_EXCESSO


def _avisos_de_excesso(mercado: str, acumulado: Decimal, teto_limite, teto_sublimite):
    """Avisos de excesso do sublimite e do limite, por mercado, com a faixa de 20%.

    Excesso "até 20%" = acumulado ≤ 1,20 × teto. Cada aviso cita SÓ os dispositivos da
    sua faixa. Faixa do LIMITE: art. 81, II, 'a' e 'b' (numerado 1 acima de 20%, 2 até
    20%). Faixa do SUBLIMITE: Res. CGSN 140, art. 12, §§ 1º e 4º, dito expressamente na
    HI-70 de docs/projeto/requisitos.md (hipótese, a confirmar com o contador-senior).
    """
    avisos = []
    if teto_sublimite is not None and acumulado > teto_sublimite:
        fracao, ate_20 = _excesso(acumulado, teto_sublimite)
        faixa = "até 20%" if ate_20 else "acima de 20%"
        avisos.append(
            Aviso(
                codigo="sublimite_excedido_ate_20" if ate_20 else "sublimite_excedido_acima_20",
                mercado=mercado,
                mensagem=(
                    f"Receita acumulada no ano ({acumulado}) passou do sublimite de "
                    f"{teto_sublimite} no mercado {mercado}, excesso {faixa} "
                    f"({fracao:.4%} do sublimite). Efeito sobre ICMS/ISS no DAS: "
                    "a conferir na etapa do pré-DAS (HI-70)."
                ),
                dispositivo=(
                    "LC 123, art. 3º, §§ 11 e 13; Res. CGSN 140, art. 12, §§ 1º, 3º, 4º e 6º; "
                    "art. 20, §§ 1º e 1º-A. Faixa de 20% do sublimite: Res. CGSN 140, art. 12, "
                    "§§ 1º e 4º (HI-70, hipótese a confirmar)"
                ),
            )
        )
    if teto_limite is not None and acumulado > teto_limite:
        fracao, ate_20 = _excesso(acumulado, teto_limite)
        if ate_20:
            efeito = (
                "excesso de até 20%: exclusão a partir do ano seguinte, com comunicação "
                "até o último dia útil de janeiro"
            )
            dispositivo = (
                "LC 123, art. 3º, § 9º-A; Res. CGSN 140, art. 2º, § 3º, II; art. 3º, § 2º, II; "
                "art. 81, II, 'a', 2 e 'b', 2"
            )
            codigo = "limite_excedido_ate_20"
        else:
            efeito = (
                "excesso acima de 20%: efeitos no mês seguinte ao excesso (ano em curso) "
                "ou retroativos ao início (ano de início), com comunicação até o último dia "
                "útil do mês seguinte"
            )
            dispositivo = (
                "LC 123, art. 3º, §§ 9º e 10; Res. CGSN 140, art. 2º, § 3º, I; art. 3º, § 2º, I; "
                "art. 81, II, 'a', 1 e 'b', 1"
            )
            codigo = "limite_excedido_acima_20"
        avisos.append(
            Aviso(
                codigo=codigo,
                mercado=mercado,
                mensagem=(
                    f"Receita acumulada no ano ({acumulado}) passou do limite de {teto_limite} "
                    f"no mercado {mercado} ({fracao:.4%}). {efeito[0].upper()}{efeito[1:]}."
                ),
                dispositivo=dispositivo,
            )
        )
    return avisos


def _avisos_de_receita_antes_da_abertura(
    empresa: Empresa, ano: int, mes: int, abertura: date
) -> list[Aviso]:
    """Aviso por mês e mercado com receita confirmada ANTES da abertura (A7, a).

    Varre os meses que a apuração consulta e que são anteriores à abertura: os 12 que
    antecedem o PA e o ano corrente. Essa receita não entra no RBT12 (o mês anterior à
    abertura conta como zero), e o aviso diz isso, em vez de descartá-la em silêncio.
    Só lê meses antes da abertura: para empresa antiga a varredura é vazia.
    """
    indice_abertura = _indice(abertura.year, abertura.month)
    inicio = min(_indice(ano, mes) - 12, _indice(ano, 1))
    avisos: list[Aviso] = []
    for indice in range(inicio, indice_abertura):
        ano_do_mes, mes_do_mes = _do_indice(indice)
        composicao = recibo.composicao_do_mes(empresa, ano_do_mes, mes_do_mes)
        for mercado in MERCADOS:
            if composicao.total(mercado) > 0:
                avisos.append(
                    Aviso(
                        codigo="receita_antes_da_abertura",
                        mercado=mercado,
                        mensagem=(
                            f"receita de {_mm_aaaa(ano_do_mes, mes_do_mes)} anterior à abertura "
                            f"no CNPJ ({abertura.strftime('%d/%m/%Y')}) não entra no RBT12 — "
                            "confira a data de abertura."
                        ),
                        dispositivo=(
                            "Res. CGSN 140, art. 2º, V (início de atividade = abertura no CNPJ) "
                            "e art. 22, §§ 1º a 4º"
                        ),
                    )
                )
    return avisos


def _contexto_da_apuracao(empresa: Empresa, ano: int, mes: int, periodos: list | None = None):
    """(data de abertura, período do Simples) do PA, ou recusa nomeada.

    Recusa com `ApuracaoRecusada`: ano 2027 ou depois, sem data de abertura, PA
    anterior à abertura, sem período do Simples no PA, ou período do Simples que
    começa antes da abertura (R4). Compartilhado por `rbt12()` e
    `janela_da_apuracao()` (DL-075: o FS12 do fator r usa a mesma janela).
    """
    recibo.validar_competencia(ano, mes)
    if ano >= ANO_RECUSADO:
        raise ApuracaoRecusada(
            f"A apuração do RBT12 a partir de {ANO_RECUSADO} depende das regras da Res. CGSN "
            "190/2026, que não foram incorporadas: os limites desses anos não estão "
            "cadastrados (HI-70)."
        )
    abertura = empresa.data_abertura_cnpj
    if abertura is None:
        raise ApuracaoRecusada(
            "Informe a data de abertura no CNPJ da empresa: sem ela o RBT12 não é apurado "
            "(Res. CGSN 140, art. 2º, V; HI-65)."
        )
    # A competência antes da abertura é recusada antes de procurar o período: isso não
    # depende do regime, e um período do Simples que alcance um mês anterior à abertura
    # já seria dado inconsistente (ver a checagem do início do período, abaixo).
    if (ano, mes) < (abertura.year, abertura.month):
        raise ApuracaoRecusada(
            f"A competência {_mm_aaaa(ano, mes)} é anterior à abertura no CNPJ "
            f"({abertura.strftime('%d/%m/%Y')})."
        )
    periodo = _periodo_do_simples(empresa, ano, mes, periodos)
    if periodo is None:
        raise ApuracaoRecusada(
            f"Não há período do Simples Nacional que alcance {_mm_aaaa(ano, mes)}: o RBT12 "
            "do Simples não se aplica a este mês."
        )
    # R4 (reconferência da DL-074): a recusa é por DATA, não por ano. A opção produz efeitos
    # a partir da inscrição no CNPJ (Res. CGSN 140/2018, art. 6º, §§ 1º e 5º, V, e art. 2º, V),
    # então um início anterior à abertura é dado inconsistente. Sem a recusa, o ano da opção
    # cairia em § 1º e a apuração sairia calada e para menos. Corrige-se o cadastro; não se
    # adivinha o dado aqui. Início igual à abertura (qualquer dia) é aceito.
    if periodo.vigencia_inicio < abertura:
        raise ApuracaoRecusada(
            "Dado inconsistente: o período do Simples Nacional começa em "
            f"{periodo.vigencia_inicio.strftime('%d/%m/%Y')}, antes da abertura no CNPJ "
            f"({abertura.strftime('%d/%m/%Y')}). A opção produz efeitos a partir da inscrição "
            "no CNPJ (Res. CGSN 140/2018, art. 6º, §§ 1º e 5º, V, e art. 2º, V). Corrija a data "
            "de abertura ou o início do regime no cadastro da empresa antes de apurar o RBT12."
        )
    return abertura, periodo


@dataclass(frozen=True)
class JanelaDaApuracao:
    """Regra do art. 22 e meses que ela soma, para o PA. Mesma regra do RBT12.

    `meses` vem em ordem e pode trazer meses ANTES da abertura: são zero e não
    exigem confirmação (o mesmo tratamento de `rbt12()`).
    """

    regra: str
    meses: tuple[tuple[int, int], ...]
    abertura: date
    ano_opcao: int


def janela_da_apuracao(
    empresa: Empresa, ano: int, mes: int, periodos: list | None = None
) -> JanelaDaApuracao:
    """Regra e janela de meses do PA, exposta para o FS12 do fator r (DL-075).

    Não lê receita nem confirmação: só calendário e período do Simples. Recusa
    como `rbt12()` (`ApuracaoRecusada`). `periodos` (de `periodos_do_simples`) evita a
    consulta de período quando a janela é calculada para vários meses (A9).
    """
    abertura, periodo = _contexto_da_apuracao(empresa, ano, mes, periodos)
    ano_opcao = periodo.vigencia_inicio.year
    regra, indices = _regra_e_janela(ano, mes, abertura, ano_opcao)
    return JanelaDaApuracao(
        regra=regra,
        meses=tuple(_do_indice(indice) for indice in indices),
        abertura=abertura,
        ano_opcao=ano_opcao,
    )


def rbt12(empresa: Empresa, ano: int, mes: int) -> Rbt12:
    """RBT12 do PA `ano/mes` por mercado, com a regra usada, a janela e os avisos.

    Recusa com `ApuracaoRecusada` (mensagem nomeada) quando não há como apurar:
    ano 2027 ou depois, sem data de abertura, PA anterior à abertura, sem período do
    Simples no PA, ou período do Simples que começa antes da abertura (dado
    inconsistente, R4). Mês da janela sem confirmação NÃO é recusa: o resultado
    fica "não apurável" e lista os meses.
    """
    abertura, periodo = _contexto_da_apuracao(empresa, ano, mes)

    ano_opcao = periodo.vigencia_inicio.year
    regra, indices_janela = _regra_e_janela(ano, mes, abertura, ano_opcao)
    indice_abertura = _indice(abertura.year, abertura.month)

    # Cada mês lido uma vez. A janela pode ter meses ANTES da abertura: são zero e
    # não exigem confirmação (não há receita a confirmar).
    cache: dict[int, _Mes] = {}

    def mes_lido(indice: int) -> _Mes:
        if indice not in cache:
            cache[indice] = _Mes(empresa, *_do_indice(indice))
        return cache[indice]

    janela = []
    for indice in indices_janela:
        na_atividade = indice >= indice_abertura
        lido = mes_lido(indice) if na_atividade else None
        janela.append(
            MesDaJanela(
                ano=_do_indice(indice)[0],
                mes=_do_indice(indice)[1],
                na_atividade=na_atividade,
                situacao=lido.situacao if lido else "fora_da_atividade",
                interno=lido.receita(MercadoReceita.INTERNO) if lido else Decimal("0.00"),
                externo=lido.receita(MercadoReceita.EXTERNO) if lido else Decimal("0.00"),
            )
        )

    pendentes_da_janela = tuple(
        (m.ano, m.mes, m.situacao)
        for m in janela
        if m.na_atividade and m.situacao != recibo.SITUACAO_CONFIRMADO
    )

    # Avisos de limite: receita acumulada de janeiro ao PA, com o PA incluído.
    indices_do_ano = [
        _indice(ano, m) for m in range(1, mes + 1) if _indice(ano, m) >= indice_abertura
    ]
    pendentes_do_ano = tuple(
        (lido.ano, lido.mes, lido.situacao)
        for lido in (mes_lido(i) for i in indices_do_ano)
        if lido.situacao != recibo.SITUACAO_CONFIRMADO
    )

    modo_limite, teto_limite, teto_sublimite = _limites_do_ano(abertura, ano, mes)
    # Limite anual CHEIO (art. 2º, § 1º): o aviso do § 5º compara com ele o RBT12 (inciso I) e a
    # receita acumulada no ano (inciso II). O teto proporcional do ano de início é outro aviso.
    limite_cheio = limite_vigente("limite_anual", date(ano, mes, 1))
    teto_cheio = None if limite_cheio is None else limite_cheio.valor

    avisos: list[Aviso] = _avisos_de_receita_antes_da_abertura(empresa, ano, mes, abertura)
    if recibo.opcao_caixa_do_ano(empresa, ano):
        avisos.append(
            Aviso(
                codigo="regime_caixa_em_ano",
                mensagem=(
                    f"Empresa optante pelo regime de caixa em {ano}: o RBT12 e os limites seguem a "
                    "competência. O pré-DAS fica bloqueado, porque a base mensal é a receita "
                    "recebida e o sistema não tem contas a receber."
                ),
                dispositivo=(
                    "Res. CGSN 140, arts. 16 e 19, parágrafo único; SC Cosit 102/2026; HI-66"
                ),
            )
        )
    if teto_limite is None or teto_sublimite is None:
        avisos.append(
            Aviso(
                codigo="limites_nao_cadastrados",
                mensagem=(
                    f"Não há limite ou sublimite cadastrado para {_mm_aaaa(ano, mes)}: os avisos "
                    "de limite não foram calculados (HI-70)."
                ),
                dispositivo="LC 123, art. 3º; Res. CGSN 140, arts. 2º, 3º, 9º e 12 (HI-70)",
            )
        )

    por_mercado: dict[str, RbtPorMercado] = {}
    for mercado in MERCADOS:
        soma = sum((m.receita(mercado) for m in janela if m.na_atividade), Decimal("0.00"))
        meses_na_conta = [m for m in janela if m.na_atividade]
        divisor = len(meses_na_conta)

        # § 1º: soma dos 12 meses (zeros antes da abertura já estão na soma). Demais: média
        # dos meses de atividade da janela × 12. O divisor é o número de meses da média.
        apurado = None
        if not pendentes_da_janela:
            if regra == "§ 1º":
                apurado = soma
                divisor = 12
            else:
                with localcontext() as contexto:
                    contexto.prec = _PRECISAO_DA_MEDIA
                    apurado = soma * 12 / Decimal(divisor)
        acumulado = None
        if not pendentes_do_ano:
            acumulado = sum((mes_lido(i).receita(mercado) for i in indices_do_ano), Decimal("0.00"))
            # § 5º do art. 22 (Res. CGSN 140/2018), com o LIMITE CHEIO de R$ 4,8 mi nos dois
            # incisos, por mercado (art. 2º, § 1º). Inciso I: o RBT12, inclusive o proporcional,
            # passa do limite cheio ("superior": igual a 4,8 mi não avisa). Inciso II: a receita
            # acumulada no ano em curso está no limite cheio ("<="), e NÃO no teto proporcional
            # do ano de início (art. 3º). O teto proporcional gera o aviso de limite excedido,
            # à parte, e os dois podem disparar juntos. Consulta ao contador-senior, 08/10/2026.
            if (
                apurado is not None
                and teto_cheio is not None
                and apurado > teto_cheio
                and acumulado <= teto_cheio
            ):
                avisos.append(
                    Aviso(
                        codigo="rbt12_acima_do_limite_ano_dentro",
                        mercado=mercado,
                        mensagem=(
                            f"RBT12 do mercado {mercado} ({apurado}) acima do limite anual de "
                            f"{teto_cheio} (inciso I), e receita acumulada no ano ({acumulado}) "
                            f"dentro do limite de {teto_cheio} (inciso II): aplicam-se as "
                            "alíquotas da última faixa (6ª), sem exclusão. A alíquota fica para "
                            "a etapa seguinte."
                        ),
                        dispositivo=("Res. CGSN 140/2018, art. 22, § 5º, I e II, e art. 2º, § 1º"),
                    )
                )
            avisos.extend(_avisos_de_excesso(mercado, acumulado, teto_limite, teto_sublimite))

        por_mercado[mercado] = RbtPorMercado(
            mercado=mercado,
            apurado=apurado,
            soma=soma,
            divisor=divisor if apurado is not None else None,
            acumulado_no_ano=acumulado,
            teto_limite=teto_limite,
            teto_sublimite=teto_sublimite,
        )

    if pendentes_do_ano:
        avisos.append(
            Aviso(
                codigo="limites_nao_apurados",
                mensagem=(
                    "Os avisos de limite não foram calculados: a receita de janeiro a "
                    f"{_mm_aaaa(ano, mes)} não está toda confirmada."
                ),
                dispositivo=(
                    "LC 123, art. 3º, § 9º; Res. CGSN 140, art. 2º, § 3º (consulta, item 7)"
                ),
            )
        )

    return Rbt12(
        ano=ano,
        mes=mes,
        data_abertura=abertura,
        ano_opcao=ano_opcao,
        regra=regra,
        janela=tuple(janela),
        pendentes_da_janela=pendentes_da_janela,
        pendentes_do_ano=pendentes_do_ano,
        por_mercado=por_mercado,
        modo_limite=modo_limite,
        avisos=tuple(avisos),
    )
