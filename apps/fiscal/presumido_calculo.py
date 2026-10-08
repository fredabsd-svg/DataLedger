"""Cálculo puro do Lucro Presumido, IRPJ e CSLL, com o acréscimo da LC 224 — DL-079, frente A.

NÍVEL 1: é o imposto que o cliente paga. Este módulo NÃO toca banco nem relógio: recebe os
valores já lidos e devolve a memória de cálculo. Quem lê os dados é `apps.fiscal.presumido`.

Fórmula (consulta de 08/10/2026, item 4; HI-100):

    R_t      receita presumida do trimestre (sem as receitas integrais do art. 25, II)
    L_t      1.250.000,00 + sobra do trimestre anterior (sobra antes do início do acréscimo = 0)
    E_t      max(0; R_t - L_t)                      excedente do trimestre
    sobra_t  max(0; L_t - R_t)
    E_t,i    E_t x R_t,i / R_t                      rateio por atividade; resíduo na última
    base     soma por atividade de (R_t,i - E_t,i) x p + E_t,i x p x 1,10, mais as integrais

Arredondamento: cada LINHA (normal e acrescida, por atividade) e cada parcela do imposto
(principal e adicional) é arredondada a centavos com ROUND_HALF_UP, separadamente. Isso é o que
faz o exemplo da consulta bater ao centavo (IRPJ T2 = 50.557,89 + 27.705,26 = 78.263,15).
Escolha de produto, sem norma sobre o arredondamento (HI-100).

No 4º trimestre (último do ano em atividade), com N trimestres sujeitos ao acréscimo:

    ExcAnual = max(0; sum(R_t) - 1.250.000,00 x N)     S = sum(E_t) dos trimestres anteriores
    caso I   ExcAnual = 0          : todo E' = 0; dedução = soma das diferenças dos anteriores
    caso II  0 < ExcAnual < S      : E' = E_t x ExcAnual / S (resíduo no último E > 0);
                                     dedução = soma das diferenças
    caso III ExcAnual >= S         : mantém E (E_4 = ExcAnual - S; a sobra já produz esse valor)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from apps.fiscal import presumido_tabelas as tab

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")
CASO_I = "I"
CASO_II = "II"
CASO_III = "III"


def centavos(valor: Decimal) -> Decimal:
    """Arredondamento único do domínio: a centavos, metade para cima (HI-100)."""
    return valor.quantize(CENTAVO, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Entradas e linhas de cálculo
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PeriodoTrimestre:
    """Os dados de um trimestre que o cálculo precisa, já lidos do banco.

    `receitas` é (atividade, R_t,i) em ordem ESTÁVEL: a última atividade recebe o resíduo do
    rateio. `meses` são os meses em atividade no trimestre (3 em regra; menos no trimestre de
    abertura da empresa, HI-107 e Lei 9.249, art. 3º, § 1º). `em_atividade` é falso antes da
    abertura: esse trimestre fica fora de N e da recursão do limite.
    """

    trimestre: int
    receitas: tuple[tuple[str, Decimal], ...]
    integrais: Decimal
    meses: int
    em_atividade: bool = True

    @property
    def receita_presumida(self) -> Decimal:
        return sum((valor for _, valor in self.receitas), ZERO)


@dataclass(frozen=True)
class LinhaAtividade:
    """Uma atividade num trimestre, num tributo. É a linha que o contador confere à mão."""

    atividade: str
    receita: Decimal
    excedente: Decimal
    aliquota: Decimal
    aliquota_acrescida: Decimal
    base_normal: Decimal
    base_acrescida: Decimal


@dataclass(frozen=True)
class Imposto:
    """Um tributo num trimestre, para um conjunto de excedentes. Tudo em centavos."""

    tributo: str
    linhas: tuple[LinhaAtividade, ...]
    base_presumida: Decimal
    receitas_integrais: Decimal
    base: Decimal
    meses: int
    principal: Decimal
    adicional: Decimal

    @property
    def total(self) -> Decimal:
        return self.principal + self.adicional


def ratear_excedente(excedente: Decimal, receitas) -> dict[str, Decimal]:
    """E_t,i = E_t x R_t,i / R_t, com o resíduo de centavos na última atividade (HI-100).

    Sem receita, não há o que ratear: todos os E_t,i são zero.
    """
    total = sum((valor for _, valor in receitas), ZERO)
    partes: dict[str, Decimal] = {atividade: ZERO for atividade, _ in receitas}
    if excedente == 0 or total == 0 or not receitas:
        return partes
    ate_o_penultimo = ZERO
    for atividade, valor in receitas[:-1]:
        parte = centavos(excedente * valor / total)
        partes[atividade] = parte
        ate_o_penultimo += parte
    partes[receitas[-1][0]] = excedente - ate_o_penultimo
    return partes


def calcular_imposto(tributo: str, periodo: PeriodoTrimestre, excedente: Decimal) -> Imposto:
    """Imposto de um trimestre para o excedente dado (use ZERO para a coluna "sem LC 224").

    IRPJ: principal 15% e adicional 10% sobre o que passar de 20.000,00 x meses (Lei 9.249, art.
    3º). CSLL: 9% sobre a base, sem adicional (Lei 7.689, art. 3º). Os dois são arredondados
    separadamente. O acréscimo multiplica a alíquota por 1,10 (LC 224, art. 4º, § 4º, VII).
    """
    excedentes = ratear_excedente(excedente, periodo.receitas)
    linhas = []
    for atividade, receita in periodo.receitas:
        definicao = tab.ATIVIDADES_POR_CODIGO[atividade]
        aliquota = definicao.irpj if tributo == tab.IRPJ else definicao.csll
        aliquota_acrescida = aliquota * tab.FATOR_ACRESCIMO_LC224
        parte_excedente = excedentes[atividade]
        linhas.append(
            LinhaAtividade(
                atividade=atividade,
                receita=receita,
                excedente=parte_excedente,
                aliquota=aliquota,
                aliquota_acrescida=aliquota_acrescida,
                base_normal=centavos((receita - parte_excedente) * aliquota),
                base_acrescida=centavos(parte_excedente * aliquota_acrescida),
            )
        )
    base_presumida = sum((linha_.base_normal + linha_.base_acrescida for linha_ in linhas), ZERO)
    base = base_presumida + periodo.integrais
    if tributo == tab.IRPJ:
        principal = centavos(base * tab.ALIQUOTA_IRPJ)
        excesso = max(ZERO, base - tab.LIMITE_ADICIONAL_POR_MES * periodo.meses)
        adicional = centavos(excesso * tab.ALIQUOTA_ADICIONAL_IRPJ)
    elif tributo == tab.CSLL:
        principal = centavos(base * tab.ALIQUOTA_CSLL)
        adicional = ZERO
    else:
        raise ValueError(f"tributo fora do cálculo do presumido: {tributo!r}")
    return Imposto(
        tributo=tributo,
        linhas=tuple(linhas),
        base_presumida=base_presumida,
        receitas_integrais=periodo.integrais,
        base=base,
        meses=periodo.meses,
        principal=principal,
        adicional=adicional,
    )


# ---------------------------------------------------------------------------
# Limite de R$ 1.250.000,00 por trimestre, com sobra (IN 2.305, art. 15, § 4º)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaLimite:
    trimestre: int
    receita: Decimal
    limite: Decimal
    excedente: Decimal
    sobra: Decimal


def primeiro_trimestre_do_acrescimo(tributo: str, ano: int) -> int | None:
    """Primeiro trimestre do ano sujeito ao acréscimo, pela data de início (LC 224, art. 14).

    IRPJ em 01/01/2026 → 1. CSLL em 01/04/2026 → 2. Fora do ano de início, é o 1º trimestre.
    Antes do ano de início, não há acréscimo: devolve None.
    """
    inicio = tab.INICIO_ACRESCIMO[tributo]
    if ano < inicio.year:
        return None
    if ano > inicio.year:
        return 1
    return (inicio.month - 1) // 3 + 1


def limites(receitas: list[tuple[int, Decimal]]) -> list[LinhaLimite]:
    """Recursão do limite. `receitas` são só os trimestres SUJEITOS ao acréscimo, em ordem.

    L_t = 1.250.000,00 + sobra do anterior. O primeiro trimestre do acréscimo começa sem sobra.
    """
    linhas = []
    sobra_anterior = ZERO
    for trimestre, receita in receitas:
        limite = tab.LIMITE_TRIMESTRAL_LC224 + sobra_anterior
        excedente = max(ZERO, receita - limite)
        sobra = max(ZERO, limite - receita)
        linhas.append(
            LinhaLimite(
                trimestre=trimestre,
                receita=receita,
                limite=limite,
                excedente=excedente,
                sobra=sobra,
            )
        )
        sobra_anterior = sobra
    return linhas


@dataclass(frozen=True)
class Fechamento:
    """Fechamento do ano no 4º trimestre: N, o excedente anual e o caso (I, II ou III)."""

    n: int
    receita_no_acrescimo: Decimal
    limite_anual: Decimal
    excedente_anual_bruto: Decimal
    excedente_anual: Decimal
    s: Decimal
    caso: str


def fechar_ano(linhas: list[LinhaLimite]) -> Fechamento:
    """Caso I, II ou III do § 5º (IN 2.305, art. 15). `linhas` são os trimestres do acréscimo."""
    n = len(linhas)
    receita_total = sum((linha_.receita for linha_ in linhas), ZERO)
    limite_anual = tab.LIMITE_TRIMESTRAL_LC224 * n
    bruto = receita_total - limite_anual
    excedente_anual = max(ZERO, bruto)
    s = sum((linha_.excedente for linha_ in linhas[:-1]), ZERO)
    if excedente_anual == 0:
        caso = CASO_I
    elif excedente_anual < s:
        caso = CASO_II
    else:
        caso = CASO_III
    return Fechamento(
        n=n,
        receita_no_acrescimo=receita_total,
        limite_anual=limite_anual,
        excedente_anual_bruto=bruto,
        excedente_anual=excedente_anual,
        s=s,
        caso=caso,
    )


def excedentes_ajustados(linhas: list[LinhaLimite], fechamento: Fechamento) -> dict[int, Decimal]:
    """E' de cada trimestre do acréscimo depois do fechamento (só muda nos casos I e II).

    Caso II: E' = E_t x ExcAnual / S, com centavos ROUND_HALF_UP e o resíduo no último E_t > 0,
    de modo que a soma dos E' seja exatamente ExcAnual. O último trimestre fica com E' = 0.
    """
    ajustados = {linha_.trimestre: linha_.excedente for linha_ in linhas}
    ultimo = linhas[-1].trimestre
    if fechamento.caso == CASO_III:
        return ajustados
    if fechamento.caso == CASO_I:
        return {t: ZERO for t in ajustados}
    anteriores = linhas[:-1]
    rateio = {}
    for linha_ in anteriores:
        rateio[linha_.trimestre] = centavos(
            linha_.excedente * fechamento.excedente_anual / fechamento.s
        )
    com_excedente = [linha_.trimestre for linha_ in anteriores if linha_.excedente > 0]
    residuo = fechamento.excedente_anual - sum(rateio.values(), ZERO)
    if com_excedente:
        rateio[com_excedente[-1]] += residuo
    rateio[ultimo] = ZERO
    return rateio


@dataclass(frozen=True)
class LinhaTributoTrimestre:
    """Os três números que o contador confere, por tributo e trimestre (HI-100 e item 10).

    `sem_lc224`: o imposto sem o acréscimo. `com_lc224`: com o acréscimo do trimestre (None
    fora do acréscimo). `parcela_lc224`: a diferença entre os dois. `ajuste_quarto`: a
    diferença que o 4º trimestre deduz quando o caso é I ou II (só nele; zero nos demais).
    """

    trimestre: int
    em_atividade: bool
    em_acrescimo: bool
    receita_presumida: Decimal
    limite: Decimal | None
    sobra: Decimal | None
    excedente: Decimal
    sem_lc224: Imposto | None
    com_lc224: Imposto | None
    parcela_lc224: Decimal | None
    excedente_ajustado: Decimal | None
    ajuste_quarto: Decimal


@dataclass(frozen=True)
class ApuracaoAnual:
    """Resultado do ano para um tributo. `fechamento` é None sem trimestre do acréscimo."""

    tributo: str
    ano: int
    primeiro_trimestre: int | None
    linhas: tuple[LinhaTributoTrimestre, ...]
    fechamento: Fechamento | None
    deducao_quarto_trimestre: Decimal


def apurar_ano(tributo: str, ano: int, periodos: list[PeriodoTrimestre]) -> ApuracaoAnual:
    """Calcula os quatro trimestres de um tributo (pode receber trimestres futuros zerados).

    Os trimestres 1 a 3 não dependem dos seguintes: o limite é recursivo para a frente. A
    dedução e o caso só existem no 4º trimestre, e é por isso que `fechamento` é None antes dele.
    """
    por_trimestre = {p.trimestre: p for p in periodos}
    if sorted(por_trimestre) != [1, 2, 3, 4]:
        raise ValueError("apurar_ano exige exatamente os quatro trimestres do ano")
    t0 = primeiro_trimestre_do_acrescimo(tributo, ano)
    sujeitos = [
        p
        for p in (por_trimestre[t] for t in (1, 2, 3, 4))
        if p.em_atividade and t0 is not None and p.trimestre >= t0
    ]
    linhas_limite = limites([(p.trimestre, p.receita_presumida) for p in sujeitos])
    fechamento = None
    excedentes_depois = {}
    if sujeitos and sujeitos[-1].trimestre == 4:
        fechamento = fechar_ano(linhas_limite)
        excedentes_depois = excedentes_ajustados(linhas_limite, fechamento)
    excedente_original = {linha_.trimestre: linha_.excedente for linha_ in linhas_limite}
    sobra_por_t = {linha_.trimestre: linha_.sobra for linha_ in linhas_limite}

    linhas = []
    deducao = ZERO
    for periodo in (por_trimestre[t] for t in (1, 2, 3, 4)):
        t = periodo.trimestre
        sem = calcular_imposto(tributo, periodo, ZERO)
        if t in excedente_original:
            com = calcular_imposto(tributo, periodo, excedente_original[t])
            parcela = com.total - sem.total
            ajuste = ZERO
            ajustado = None
            if t in excedentes_depois:
                ajustado = excedentes_depois[t]
                com_depois = calcular_imposto(tributo, periodo, ajustado)
                ajuste = com.total - com_depois.total
            deducao += ajuste
            linhas.append(
                LinhaTributoTrimestre(
                    trimestre=t,
                    em_atividade=periodo.em_atividade,
                    em_acrescimo=True,
                    receita_presumida=periodo.receita_presumida,
                    limite=next(linha_.limite for linha_ in linhas_limite if linha_.trimestre == t),
                    sobra=sobra_por_t[t],
                    excedente=excedente_original[t],
                    sem_lc224=sem,
                    com_lc224=com,
                    parcela_lc224=parcela,
                    excedente_ajustado=ajustado,
                    ajuste_quarto=ZERO,
                )
            )
        else:
            linhas.append(
                LinhaTributoTrimestre(
                    trimestre=t,
                    em_atividade=periodo.em_atividade,
                    em_acrescimo=False,
                    receita_presumida=periodo.receita_presumida,
                    limite=None,
                    sobra=None,
                    excedente=ZERO,
                    sem_lc224=sem,
                    com_lc224=None,
                    parcela_lc224=None,
                    excedente_ajustado=None,
                    ajuste_quarto=ZERO,
                )
            )
    # A dedução vai para a linha do 4º trimestre, e só existe quando o caso é I ou II.
    deducao_do_quarto = deducao if fechamento is not None and fechamento.caso != CASO_III else ZERO
    linhas = [
        _com_ajuste(linha, deducao_do_quarto) if linha.trimestre == 4 else linha for linha in linhas
    ]
    return ApuracaoAnual(
        tributo=tributo,
        ano=ano,
        primeiro_trimestre=t0,
        linhas=tuple(linhas),
        fechamento=fechamento,
        deducao_quarto_trimestre=deducao_do_quarto,
    )


def _com_ajuste(linha: LinhaTributoTrimestre, ajuste: Decimal) -> LinhaTributoTrimestre:
    return LinhaTributoTrimestre(
        trimestre=linha.trimestre,
        em_atividade=linha.em_atividade,
        em_acrescimo=linha.em_acrescimo,
        receita_presumida=linha.receita_presumida,
        limite=linha.limite,
        sobra=linha.sobra,
        excedente=linha.excedente,
        sem_lc224=linha.sem_lc224,
        com_lc224=linha.com_lc224,
        parcela_lc224=linha.parcela_lc224,
        excedente_ajustado=linha.excedente_ajustado,
        ajuste_quarto=ajuste,
    )


# ---------------------------------------------------------------------------
# Calendário: último dia útil, Páscoa e Carnaval (HI-105)
# ---------------------------------------------------------------------------


def pascoa(ano: int) -> date:
    """Domingo de Páscoa, pelo algoritmo de Gauss/Meeus (calendário gregoriano).

    Usado só para AVISAR: a Sexta-feira Santa e a terça de Carnaval não são feriado nacional por
    lei, então não mudam o vencimento; quando a data cai nelas, a tela pede conferência.
    """
    a = ano % 19
    b = ano // 100
    c = ano % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    linha_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * linha_) // 451
    mes = (h + linha_ - 7 * m + 114) // 31
    dia = ((h + linha_ - 7 * m + 114) % 31) + 1
    return date(ano, mes, dia)


def datas_a_conferir(ano: int) -> frozenset[date]:
    """Sexta-feira Santa (Páscoa − 2) e terça de Carnaval (Páscoa − 47) do ano."""
    domingo = pascoa(ano)
    return frozenset({domingo - timedelta(days=2), domingo - timedelta(days=47)})


def feriado_nacional_fixo(dia: date) -> bool:
    """Feriado nacional fixo por lei, vigente na data (Leis 662/1949, 6.802/1980 e 14.759/2023)."""
    for mes, dia_do_mes, _nome, _fundamento in tab.FERIADOS_NACIONAIS_FIXOS:
        if (dia.month, dia.day) == (mes, dia_do_mes):
            if mes == 11 and dia_do_mes == 20 and dia.year < tab.ANO_FERIADO_20_NOVEMBRO:
                return False
            return True
    return False


def ultimo_dia_util(ano: int, mes: int) -> tuple[date, bool]:
    """Último dia útil do mês e se ele pede conferência de calendário.

    Recua sábado, domingo e feriado nacional fixo. Sexta-feira Santa e terça de Carnaval NÃO
    recuam: o vencimento fica nelas e a data sai com o aviso "calendário a conferir".
    """
    proximo = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    dia = proximo - timedelta(days=1)
    while dia.weekday() >= 5 or feriado_nacional_fixo(dia):
        dia -= timedelta(days=1)
    return dia, dia in datas_a_conferir(dia.year)


# ---------------------------------------------------------------------------
# Quotas (Lei 9.430, art. 5º; HI-105)
# ---------------------------------------------------------------------------

QUOTA_MINIMA = Decimal("1000.00")
IMPOSTO_MINIMO_PARA_TRES_QUOTAS = Decimal("2000.00")
JUROS_QUOTA_1 = "sem juros"
JUROS_QUOTA_2 = "1%"


def _mes_seguinte(ano: int, mes: int, deslocamento: int) -> tuple[int, int]:
    indice = (ano * 12 + (mes - 1)) + deslocamento
    return indice // 12, indice % 12 + 1


@dataclass(frozen=True)
class Parcela:
    numero: int
    valor: Decimal
    vencimento: date
    aviso_calendario: bool
    juros: str


@dataclass(frozen=True)
class OpcoesDeQuota:
    """Quota única, e o plano de 3 quotas quando a regra o permite.

    `motivo_sem_tres_quotas` é a recusa nomeada do plano. Quando o plano existe, `tres_quotas`
    traz as três parcelas e `motivo_sem_tres_quotas` fica None.
    """

    devido: Decimal
    quota_unica: tuple[Parcela, ...]
    tres_quotas: tuple[Parcela, ...] | None
    motivo_sem_tres_quotas: str | None


def opcoes_de_quota(devido: Decimal, ano: int, trimestre: int) -> OpcoesDeQuota:
    """Opções de pagamento de um imposto de um trimestre (Lei 9.430, art. 5º).

    A 1ª quota vence no último dia útil do 1º mês seguinte ao trimestre, sem juros. A 2ª tem 1%.
    A 3ª tem a Selic acumulada a partir do 2º mês seguinte, mais 1% no mês do pagamento; a taxa
    não é embutida. O plano de 3 quotas exige imposto de R$ 2.000,00 e quotas de R$ 1.000,00.
    """
    mes_fim = trimestre * 3
    unica_dia, unica_aviso = ultimo_dia_util(*_mes_seguinte(ano, mes_fim, 1))
    if devido <= 0:
        return OpcoesDeQuota(devido, (), None, "Sem imposto a recolher neste trimestre.")
    unica = (Parcela(1, devido, unica_dia, unica_aviso, JUROS_QUOTA_1),)

    if devido < IMPOSTO_MINIMO_PARA_TRES_QUOTAS:
        return OpcoesDeQuota(
            devido,
            unica,
            None,
            "Imposto abaixo de R$ 2.000,00: só quota única.",
        )
    primeira = centavos(devido / 3)
    segunda = primeira
    terceira = devido - primeira - segunda
    if min(primeira, segunda, terceira) < QUOTA_MINIMA:
        return OpcoesDeQuota(
            devido,
            unica,
            None,
            "Alguma quota ficaria abaixo de R$ 1.000,00: só quota única.",
        )
    parcelas = []
    for numero, valor, deslocamento in (
        (1, primeira, 1),
        (2, segunda, 2),
        (3, terceira, 3),
    ):
        vencimento, aviso = ultimo_dia_util(*_mes_seguinte(ano, mes_fim, deslocamento))
        if numero == 1:
            juros = JUROS_QUOTA_1
        elif numero == 2:
            juros = JUROS_QUOTA_2
        else:
            _, mes_selic = _mes_seguinte(ano, mes_fim, 2)
            juros = f"Selic acumulada de {tab.MESES[mes_selic - 1]} + 1% — taxa não embutida"
        parcelas.append(Parcela(numero, valor, vencimento, aviso, juros))
    return OpcoesDeQuota(devido, unica, tuple(parcelas), None)


def cobre_o_trimestre(
    inicio: tuple[int, int],
    fim: tuple[int, int] | None,
    ano: int,
    trimestre: int,
) -> bool:
    """A medida judicial cobre (ano, trimestre)? `fim` None é prazo indeterminado (item 10).

    Compara pares (ano, trimestre), que ordenam bem sem conversão de data.
    """
    alvo = (ano, trimestre)
    if alvo < inicio:
        return False
    return fim is None or alvo <= fim
