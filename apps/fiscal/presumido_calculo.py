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
    caso I   ExcAnual = 0          : todo E' = 0; dedução = soma das diferenças
    caso II  0 < ExcAnual < S      : E' = E_t x ExcAnual / S (resíduo no último E > 0);
                                     dedução = soma das diferenças
    caso III ExcAnual >= S         : mantém E (E_4 = ExcAnual - S; a sobra já produz esse valor)

Medida judicial (DL-079, item 0): a diferença de um trimestre só entra na dedução se a parcela
da LC 224 desse trimestre FOI recolhida. Com medida ativa cobrindo o tributo no trimestre, a
parcela ficou suspensa ou depositada; devolvê-la no 4º seria contá-la duas vezes. O limite (E,
sobra, caso) NÃO muda com a medida: só a dedução exclui o trimestre.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
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
    fora do acréscimo). `parcela_lc224`: a diferença entre os dois. `ajuste_quarto`: o total que
    o 4º trimestre deduz quando o caso é I ou II (só nele; zero nos demais).

    `diferenca_recalculo`: com − recalculado com o E' do fechamento (None fora do fechamento).
    É a parcela deste trimestre que o 4º pode devolver, SALVO se `suspensa_por_medida`: nesse caso
    a parcela não foi recolhida e fica fora da dedução (DL-079, item 0).
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
    diferenca_recalculo: Decimal | None = None
    suspensa_por_medida: bool = False


@dataclass(frozen=True)
class ApuracaoAnual:
    """Resultado do ano para um tributo. `fechamento` é None sem trimestre do acréscimo."""

    tributo: str
    ano: int
    primeiro_trimestre: int | None
    linhas: tuple[LinhaTributoTrimestre, ...]
    fechamento: Fechamento | None
    deducao_quarto_trimestre: Decimal


def apurar_ano(
    tributo: str,
    ano: int,
    periodos: list[PeriodoTrimestre],
    suspensos: frozenset[int] = frozenset(),
) -> ApuracaoAnual:
    """Calcula os quatro trimestres de um tributo (pode receber trimestres futuros zerados).

    `suspensos` são os trimestres com medida judicial ativa cobrindo o tributo (DL-079, item 0).
    Eles NÃO mudam o limite nem o caso; saem só da dedução do 4º trimestre, porque a parcela
    deles não foi recolhida.

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
            ajustado = None
            diferenca = None
            if t in excedentes_depois:
                ajustado = excedentes_depois[t]
                com_depois = calcular_imposto(tributo, periodo, ajustado)
                diferenca = com.total - com_depois.total
            suspensa = t in suspensos
            # Parcela suspensa ou depositada não foi recolhida: devolvê-la no 4º seria contá-la
            # duas vezes (DL-079, item 0). Por isso só a diferença de trimestre recolhido soma.
            if diferenca is not None and not suspensa:
                deducao += diferenca
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
                    diferenca_recalculo=diferenca,
                    suspensa_por_medida=suspensa,
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
        replace(linha, ajuste_quarto=deducao_do_quarto) if linha.trimestre == 4 else linha
        for linha in linhas
    ]
    return ApuracaoAnual(
        tributo=tributo,
        ano=ano,
        primeiro_trimestre=t0,
        linhas=tuple(linhas),
        fechamento=fechamento,
        deducao_quarto_trimestre=deducao_do_quarto,
    )


# ---------------------------------------------------------------------------
# Calendário: último dia útil, Páscoa e dias sem expediente bancário (DL-084, item 1)
# ---------------------------------------------------------------------------


def pascoa(ano: int) -> date:
    """Domingo de Páscoa, pelo algoritmo de Gauss/Meeus (calendário gregoriano).

    Base de TODOS os dias sem expediente bancário móveis (Sexta-feira Santa, Carnaval e Corpus
    Christi): um erro aqui muda o vencimento de março ou de maio. Por isso o teste compara anos com
    Páscoa em março e em abril com datas escritas à mão.
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


def dias_sem_expediente_bancario(ano: int) -> dict[date, str]:
    """Data → nome dos dias sem expediente bancário nacional do ano (Páscoa e tabela do módulo).

    Não são úteis para o vencimento (DL-084, item 1): ver `ultimo_dia_util`. A fonte de cada um está
    em `presumido_tabelas.DIAS_SEM_EXPEDIENTE_BANCARIO`.
    """
    domingo = pascoa(ano)
    return {
        domingo + timedelta(days=deslocamento): nome
        for deslocamento, nome, _fonte in tab.DIAS_SEM_EXPEDIENTE_BANCARIO
    }


def feriado_nacional_fixo(dia: date) -> bool:
    """Feriado nacional fixo por lei, vigente na data (Leis 662/1949, 6.802/1980 e 14.759/2023).

    20/11 vale desde 2024 (Lei 14.759/2023, publicada em 22/12/2023; consulta PE-83.9).
    """
    for mes, dia_do_mes, _nome, _fundamento in tab.FERIADOS_NACIONAIS_FIXOS:
        if (dia.month, dia.day) == (mes, dia_do_mes):
            if mes == 11 and dia_do_mes == 20 and dia.year < tab.ANO_FERIADO_20_NOVEMBRO:
                return False
            return True
    return False


def _dia_civil_util(dia: date) -> bool:
    """Sem fim de semana e sem feriado nacional fixo: é o que o vencimento antes do DL-084 usava."""
    return dia.weekday() < 5 and not feriado_nacional_fixo(dia)


def _ultimo_dia_util_civil(ano: int, mes: int) -> date:
    proximo = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    dia = proximo - timedelta(days=1)
    while not _dia_civil_util(dia):
        dia -= timedelta(days=1)
    return dia


def ultimo_dia_util(ano: int, mes: int) -> tuple[date, bool]:
    """Último dia útil do mês e se ele ANTECIPOU por dia sem expediente bancário (DL-084, item 1).

    Recua sábado, domingo, feriado nacional fixo e os dias sem expediente bancário nacional (Sexta-
    feira Santa, segunda e terça de Carnaval, Corpus Christi). O bool é True só quando algum desses
    dias bancários foi pulado: a data antecipou. Feriado local NÃO entra aqui; ele só avisa
    (`avisos_de_feriado_local`), porque a data normativa não muda por feriado local.
    """
    proximo = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    dia = proximo - timedelta(days=1)
    antecipado = False
    while not _dia_civil_util(dia) or dia in dias_sem_expediente_bancario(dia.year):
        if _dia_civil_util(dia):
            antecipado = True
        dia -= timedelta(days=1)
    return dia, antecipado


# ---------------------------------------------------------------------------
# Quotas (Lei 9.430, art. 5º; HI-105)
# ---------------------------------------------------------------------------
# Lei 9.430, art. 5º, § 1º: o imposto pode ser pago em até três quotas mensais, iguais e sucessivas,
# vencíveis no último dia útil dos três meses seguintes ao trimestre. Art. 5º, § 2º: nenhuma quota
# pode ser inferior a R$ 1.000,00, e imposto inferior a R$ 2.000,00 é pago em quota única. Daí
# dois planos: 2 quotas a partir de R$ 2.000,00 e 3 quotas a partir de R$ 3.000,00 (cada uma de
# R$ 1.000,00). Texto lido no Planalto em 09/10/2026. Sem juros na 1ª quota, 1% na 2ª e Selic
# acumulada mais 1% na 3ª (§ 3º); a taxa não é embutida no valor.
QUOTA_MINIMA = Decimal("1000.00")
IMPOSTO_MINIMO_PARCELAVEL = Decimal("2000.00")
JUROS_QUOTA_1 = "sem juros"
JUROS_QUOTA_2 = "1%"
SEM_IMPOSTO_A_RECOLHER = "Sem imposto a recolher neste trimestre."


def _mes_seguinte(ano: int, mes: int, deslocamento: int) -> tuple[int, int]:
    indice = (ano * 12 + (mes - 1)) + deslocamento
    return indice // 12, indice % 12 + 1


@dataclass(frozen=True)
class Parcela:
    """Uma quota (ou o imposto em quota única) com a data de vencimento e os avisos da data.

    `aviso_calendario` NÃO é mais preenchido (DL-084, item 1): o aviso "calendário a conferir" saiu
    com a HI-105 substituída. O campo fica só porque a tela da frente B o lê; sempre é falso.
    `antecipada_de` é a data civil (sábado, domingo e feriado fixo) quando o vencimento recuou por
    dia sem expediente bancário nacional; None quando não recuou. `avisos_locais` vêm do feriado
    local da praça (DL-084, item 2): não mudam a data, só avisam.
    """

    numero: int
    valor: Decimal
    vencimento: date
    aviso_calendario: bool
    juros: str
    antecipada_de: date | None = None
    avisos_locais: tuple[str, ...] = ()


@dataclass(frozen=True)
class OpcoesDeQuota:
    """Quota única, e os planos de 2 e de 3 quotas quando a regra os permite.

    Cada plano tem a sua recusa nomeada (`motivo_sem_...`). Quando o plano existe, a lista de
    parcelas vem preenchida e o motivo fica None.
    """

    devido: Decimal
    quota_unica: tuple[Parcela, ...]
    duas_quotas: tuple[Parcela, ...] | None
    motivo_sem_duas_quotas: str | None
    tres_quotas: tuple[Parcela, ...] | None
    motivo_sem_tres_quotas: str | None


def _valores_das_quotas(devido: Decimal, quantidade: int) -> tuple[Decimal, ...]:
    """Quotas iguais em centavos (metade para cima na primeira); a última leva o resíduo."""
    primeira = centavos(devido / quantidade)
    return (primeira,) * (quantidade - 1) + (devido - primeira * (quantidade - 1),)


def _parcelas(ano: int, trimestre: int, valores: tuple[Decimal, ...]) -> tuple[Parcela, ...]:
    """Parcelas com vencimento no último dia útil de cada mês após o trimestre, juros em texto.

    `antecipada_de` guarda a data civil quando o vencimento recuou por dia sem expediente bancário
    (DL-084, item 1). A data que o contador paga é `vencimento`; a outra só explica o recuo.
    """
    mes_fim = trimestre * 3
    parcelas = []
    for numero, valor in enumerate(valores, start=1):
        ano_venc, mes_venc = _mes_seguinte(ano, mes_fim, numero)
        vencimento, antecipado = ultimo_dia_util(ano_venc, mes_venc)
        civil = _ultimo_dia_util_civil(ano_venc, mes_venc)
        if numero == 1:
            juros = JUROS_QUOTA_1
        elif numero == 2:
            juros = JUROS_QUOTA_2
        else:
            _, mes_selic = _mes_seguinte(ano, mes_fim, 2)
            juros = f"Selic acumulada de {tab.MESES[mes_selic - 1]} + 1% — taxa não embutida"
        parcelas.append(
            Parcela(
                numero=numero,
                valor=valor,
                vencimento=vencimento,
                aviso_calendario=False,
                juros=juros,
                antecipada_de=civil if antecipado else None,
            )
        )
    return tuple(parcelas)


# ---------------------------------------------------------------------------
# Feriados locais: só AVISO, nunca muda a data (DL-084, item 2; HI-137)
# ---------------------------------------------------------------------------

AVISO_LOCAL_SEM_FONTE_BANCARIA = "feriado local: confirmar expediente bancário na praça"
AVISO_LOCAL_BANCARIO = "feriado bancário em {praca} (Febraban)"
AVISO_LOCAL_ANTECIPAR = "antecipar: sem expediente bancário na praça"


@dataclass(frozen=True)
class ExcecaoFeriadoDado:
    """Um ano em que o feriado foi movido por decreto (ex.: 05/10/2026 observado em 09/10/2026)."""

    ano: int
    data_observada: date
    fonte_bancaria: str


@dataclass(frozen=True)
class FeriadoLocalDado:
    """Um feriado local (estadual ou municipal) já lido do banco, sem consulta própria.

    `fonte_bancaria` vazia = a lista da Febraban não confirma o fechamento na praça: o aviso fica
    o mais fraco ("confirmar expediente"). Com fonte, o aviso diz que a praça fecha.
    """

    descricao: str
    mes: int
    dia: int
    vigencia_inicio: date
    vigencia_fim: date | None
    fonte_bancaria: str
    excecoes: tuple[ExcecaoFeriadoDado, ...] = ()


def chave_municipio(nome: str) -> str:
    """Nome de município sem acento, em maiúsculas e com espaços simples: a chave de comparação.

    É a forma gravada em `FeriadoLocal.municipio`, para que "Palmas", "PALMAS" e "palmas" casem.
    """
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.upper().split())


def avisos_de_feriado_local(
    dia: date, feriados: tuple[FeriadoLocalDado, ...], praca: str
) -> tuple[str, ...]:
    """Avisos que um feriado local põe numa data de vencimento. Nunca mudam a data.

    A data observada vale no ano: se houver exceção desse ano (decreto que moveu o feriado), o
    aviso vai para a data observada, e a data normativa NÃO avisa, porque nesse ano ela não é
    feriado. Sem exceção, a data normativa é a própria data do feriado.
    """
    avisos: list[str] = []
    for feriado in feriados:
        if dia < feriado.vigencia_inicio:
            continue
        if feriado.vigencia_fim is not None and dia > feriado.vigencia_fim:
            continue
        excecao = next((e for e in feriado.excecoes if e.ano == dia.year), None)
        if excecao is not None:
            if excecao.data_observada != dia:
                continue
            fonte = excecao.fonte_bancaria
        else:
            if (feriado.mes, feriado.dia) != (dia.month, dia.day):
                continue
            fonte = feriado.fonte_bancaria
        if fonte:
            avisos.append(AVISO_LOCAL_BANCARIO.format(praca=praca))
            avisos.append(AVISO_LOCAL_ANTECIPAR)
        else:
            avisos.append(AVISO_LOCAL_SEM_FONTE_BANCARIA)
    return tuple(avisos)


def opcoes_de_quota(devido: Decimal, ano: int, trimestre: int) -> OpcoesDeQuota:
    """Opções de pagamento de um imposto de um trimestre (Lei 9.430, art. 5º, §§ 1º a 3º).

    Imposto abaixo de R$ 2.000,00: só quota única. Acima disso, cada plano (2 ou 3 quotas) existe
    se a menor quota ficar em pelo menos R$ 1.000,00. O plano de 3 quotas, portanto, só existe a
    partir de R$ 3.000,00. A quota única sempre existe quando há imposto.
    """
    if devido <= 0:
        return OpcoesDeQuota(devido, (), None, SEM_IMPOSTO_A_RECOLHER, None, SEM_IMPOSTO_A_RECOLHER)
    unica = _parcelas(ano, trimestre, (devido,))
    if devido < IMPOSTO_MINIMO_PARCELAVEL:
        motivo = "Imposto abaixo de R$ 2.000,00: só quota única."
        return OpcoesDeQuota(devido, unica, None, motivo, None, motivo)

    motivo_quota_pequena = "Alguma quota ficaria abaixo de R$ 1.000,00"
    duas = _valores_das_quotas(devido, 2)
    tres = _valores_das_quotas(devido, 3)
    duas_ok = min(duas) >= QUOTA_MINIMA
    tres_ok = min(tres) >= QUOTA_MINIMA
    return OpcoesDeQuota(
        devido,
        unica,
        _parcelas(ano, trimestre, duas) if duas_ok else None,
        None if duas_ok else f"{motivo_quota_pequena}: só quota única.",
        _parcelas(ano, trimestre, tres) if tres_ok else None,
        (
            None
            if tres_ok
            else f"{motivo_quota_pequena}: o plano de 3 quotas exige imposto de pelo menos "
            "R$ 3.000,00."
        ),
    )


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
