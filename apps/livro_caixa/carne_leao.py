"""Apuração mensal e anual do carnê-leão (DL-046, fatia 2 — RC-131/RC-132/
RC-133/RC-134, HI-32 a HI-37).

⚠️ **RC-133 foi CORRIGIDA em 2026-09-27** (ordem do arquiteto-senior): a
redução da Lei 15.270/2025 usa o RENDIMENTO BRUTO (antes de qualquer
dedução), NUNCA a base de cálculo — a versão original deste módulo usava a
base, o que não reproduzia os exemplos oficiais da Receita Federal (ver
`_reducao_bruta`, abaixo, e docs/planos/DL-046-livro-caixa-e-carne-leao.md,
"Correção da RC-133").

Motor de cálculo PURO (funções privadas `_pipeline`/`_imposto_pela_tabela`/
`_reducao_bruta`/`_agregados_do_mes`) separado da camada ORM
(`apurar_carne_leao_mensal`/`apurar_carne_leao_anual`), no mesmo espírito de
`apps.contabilidade.services` (DE-034 item 2): regra de cálculo testável sem
banco, agregação testável com banco.

⚠️ **Nunca grava resultado.** A apuração é sempre recalculada a partir dos
LANÇAMENTOS de origem (RC-130, critério 3 do plano): corrigir um lançamento
de um mês passado (por estorno, já que lançamento efetivado é imutável) muda
o resultado desta função na PRÓXIMA chamada, sem nenhuma tabela de resultado
para reconciliar ou invalidar — o "banco de dados" da apuração é
`LancamentoCaixa` mais as quatro tabelas normativas, nunca um cache.

⚠️ **Encadeamento dentro do ANO-CALENDÁRIO, nunca entre anos.** O excesso de
deduções do livro-caixa (art. 69, RIR/2018, §1º) e o saldo de crédito do
imposto pago no exterior (Perguntas e Respostas IRPF 2026, pergunta 267,
"Atenção") são, os dois, POR LEI, limitados a dezembro do mesmo
ano-calendário — a apuração de qualquer mês recomeça de janeiro do MESMO
ano, nunca lê dezembro do ano anterior. O saldo "abaixo de R$ 10,00" (RIR/
2018, art. 938, §§ 4º e 5º; Lei 9.430/1996, art. 68) não tem, nas fontes
consultadas, uma regra que o reinicie por ano-calendário (HI-37) — mas esta implementação, ao só
olhar o ano pedido, também o reinicia em janeiro; é uma LIMITAÇÃO DECLARADA
desta fatia (ver o plano DL-046, "Não testado"), não uma regra confirmada.

⚠️ **Nenhum número normativo aparece como literal Python neste arquivo**
(critério 5 do plano): tabela progressiva, redução da Lei 15.270/2025 e
valor por dependente vêm SEMPRE de `apps.livro_caixa.models.
VigenciaTabelaProgressivaCarneLeao`/`VigenciaReducaoCarneLeao`/
`VigenciaDependenteCarneLeao`, gravadas por migração de dados. A ausência de
uma vigência aplicável levanta `TabelaCarneLeaoNaoConfigurada` — nunca um
valor-padrão do código.

HI-36 (requisitos.md) — arredondamento: nenhuma das fontes lidas (RIR/2018,
Lei 9.250/1995, Lei 15.270/2025, Perguntas e Respostas IRPF 2026) fixa a
política de arredondamento de cada etapa intermediária do carnê-leão (só do
resultado final, implicitamente, por ser sempre expresso em reais e
centavos). Escolha CONSERVADORA declarada: `PoliticaArredondamento.
MEIO_PARA_CIMA` (ROUND_HALF_UP), aplicada a CADA valor monetário que se
torna uma LINHA da memória de cálculo (nunca truncando, que reduziria o
imposto devido em relação ao valor exato — o lado de MAIOR risco de
conformidade tributária) — nunca um cálculo intermediário sem escala
definida entre etapas.
"""

import calendar
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, models, transaction

from apps.auditoria.services import registrar
from apps.core.dinheiro import PoliticaArredondamento, quantizar
from apps.core.restricoes import mensagens_de, restricao_como_400
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.models import (
    DependentesCarneLeaoCliente,
    FaixaTabelaProgressivaCarneLeao,
    LancamentoCaixa,
    NaturezaCaixa,
    VigenciaDependenteCarneLeao,
    VigenciaReducaoCarneLeao,
    VigenciaTabelaProgressivaCarneLeao,
)
from apps.livro_caixa.validators import (
    CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO,
    rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal,
)

# HI-36 — ver o docstring do módulo.
_POLITICA = PoliticaArredondamento.MEIO_PARA_CIMA
_ZERO = Decimal("0.00")
_LIMITE_DARF = Decimal("10.00")


def _q(valor):
    return quantizar(valor, casas=2, politica=_POLITICA)


class TabelaCarneLeaoNaoConfigurada(Exception):
    """Levantada quando não há, no BANCO, uma vigência de tabela
    progressiva, redução (Lei 15.270/2025) ou valor por dependente
    aplicável ao mês pedido. NUNCA cai para um valor padrão do código —
    ver o critério 5 do plano DL-046, fatia 2, e o docstring do módulo."""


class DependentesCarneLeaoInvalido(Exception):
    """Erro de domínio ao registrar a quantidade de dependentes de um
    cliente — mesmo papel de `LancamentoCaixaInvalido` (services.py)."""


# ---------------------------------------------------------------------------
# Motor de cálculo PURO — sem ORM, só `Decimal`. Testável isoladamente com
# casos calculados à mão (critério 1 do plano).


def _faixa_da_base(base, faixas):
    """`faixas` já ordenadas por `ordem` (alíquota crescente). Devolve a
    primeira cuja `limite_superior` (ou ausência dele, na última faixa)
    cobre `base` — as faixas da tabela oficial são CONTÍGUAS, sem lacuna
    entre uma e a próxima (RC-131), então a primeira que cobre é a única
    que cobre."""
    for faixa in faixas:
        if faixa.limite_superior is None or base <= faixa.limite_superior:
            return faixa
    raise TabelaCarneLeaoNaoConfigurada(
        f"A tabela progressiva não tem faixa que cubra a base de cálculo {base} "
        "— faltam faixas com limite superior aberto (última faixa)."
    )


def _imposto_pela_tabela(base, faixas):
    faixa = _faixa_da_base(base, faixas)
    bruto = base * faixa.aliquota - faixa.parcela_a_deduzir
    return _q(max(_ZERO, bruto))


def _reducao_bruta(rendimento_bruto, reducao_cfg):
    """Lei nº 9.250/1995, art. 3º-A (incluído pela Lei 15.270/2025) — Anexo
    X da IN RFB nº 1.500/2014 (na redação da IN RFB nº 2.299/2025): a
    redução usa o RENDIMENTO TRIBUTÁVEL BRUTO sujeito ao ajuste mensal
    (ANTES de qualquer dedução, inclusive livro-caixa), NUNCA a base de
    cálculo — RC-133 (requisitos.md).

    ⚠️ **Correção de 2026-09-27**, a partir de exemplo oficial da Receita
    Federal ("Exemplos de Aplicação da Lei 15.270/2025",
    gov.br/receitafederal — Exemplo 5): "Neste exemplo, o salário
    (rendimento tributável sujeito à incidência mensal) é superior ao
    valor de R$ 7.350,00, logo, não é permitida a redução (...). Importante
    observar que se utiliza nessa tabela de redução o valor do SALÁRIO (R$
    7.607,20), e NÃO o da BASE DE CÁLCULO (R$ 7.000,00)." A versão anterior
    desta função usava a base (após deduções) — ERRADO, contrariado pelo
    próprio exemplo oficial da Receita; a IN RFB nº 2.299/2025 confirma a
    mesma distinção (Anexo X — "Rendimentos Tributáveis Sujeitos ao
    Ajuste Mensal" — é conceito DIFERENTE do Anexo II — base de cálculo).
    Para o carnê-leão (fora do contexto de folha), "rendimento tributável"
    é o total de rendimentos SUJEITOS ao carnê-leão do mês (RC-132), antes
    de qualquer dedução — decisão do arquiteto-senior, 2026-09-27.

    Redução fixa até `limite_faixa_plena` (imposto zero); decrescente
    linearmente até `limite_superior`; nenhuma redução depois (§2º) —
    todos os TRÊS limites comparados contra o BRUTO, nunca a base.
    """
    if rendimento_bruto <= 0:
        return _ZERO
    if rendimento_bruto <= reducao_cfg.limite_faixa_plena:
        valor = reducao_cfg.reducao_maxima
    elif rendimento_bruto <= reducao_cfg.limite_superior:
        valor = reducao_cfg.constante_formula - (reducao_cfg.coeficiente * rendimento_bruto)
    else:
        valor = _ZERO
    return _q(max(_ZERO, valor))


def _pipeline(base_bruta, rendimento_bruto, faixas, reducao_cfg):
    """Base → imposto pela tabela → redução (limitada ao imposto, §1º) →
    imposto após redução. `base_bruta` pode ser negativa (rendimento menor
    que as deduções); a base de cálculo real nunca é negativa.

    `rendimento_bruto` (RC-133) é o rendimento ANTES de qualquer dedução —
    o MESMO valor para as duas formas de dedução (reais ou desconto
    simplificado) no mesmo mês, porque a redução nunca olha a dedução
    escolhida. Só `base_bruta` muda entre as duas chamadas que comparam
    as formas (`_apurar_um_mes`)."""
    base = max(_ZERO, _q(base_bruta))
    imposto_tabela = _imposto_pela_tabela(base, faixas)
    reducao_disponivel = _reducao_bruta(rendimento_bruto, reducao_cfg)
    # §1º do art. 3º-A: a redução fica LIMITADA ao imposto apurado pela
    # tabela — nunca produz imposto negativo nem "crédito" de redução.
    reducao_aplicada = min(reducao_disponivel, imposto_tabela)
    imposto_apos_reducao = _q(imposto_tabela - reducao_aplicada)
    return {
        "base": base,
        "imposto_tabela": imposto_tabela,
        "reducao_disponivel": reducao_disponivel,
        "reducao_aplicada": reducao_aplicada,
        "imposto_apos_reducao": imposto_apos_reducao,
    }


def _limite_compensacao_exterior(
    rendimento_total, rendimento_exterior, deducao_escolhida, faixas, reducao_cfg
):
    """Perguntas e Respostas IRPF 2026, pergunta 267 ("Atenção"): o limite
    de compensação do imposto pago no exterior é "a diferença entre o
    imposto calculado COM a inclusão dos rendimentos de fontes no exterior
    e o imposto calculado SEM a inclusão desses rendimentos" — a MESMA
    forma de dedução (real ou desconto simplificado) já escolhida para o
    mês, variando só o rendimento (RC-134). O rendimento BRUTO da redução
    (RC-133) também varia entre as duas chamadas — excluir o rendimento do
    exterior muda tanto a base quanto o bruto que a redução compara contra
    os limiares de R$ 5.000,00/R$ 7.350,00."""
    if rendimento_exterior <= 0:
        return _ZERO
    imposto_com = _pipeline(
        rendimento_total - deducao_escolhida, rendimento_total, faixas, reducao_cfg
    )["imposto_apos_reducao"]
    rendimento_sem_exterior = rendimento_total - rendimento_exterior
    imposto_sem = _pipeline(
        rendimento_sem_exterior - deducao_escolhida,
        rendimento_sem_exterior,
        faixas,
        reducao_cfg,
    )["imposto_apos_reducao"]
    return _q(max(_ZERO, imposto_com - imposto_sem))


def _agregados_do_mes(lancamentos):
    """Soma os lançamentos de UM mês por categoria relevante ao carnê-leão.
    Estorno contribui com sinal INVERTIDO do original, do MESMO lado (mesma
    convenção de `apps.livro_caixa.services.apurar_livro_caixa`, D3) — nunca
    como um lançamento novo do lado oposto."""
    rendimento_total_sujeito = _ZERO
    rendimento_trabalho_nao_assalariado = _ZERO
    rendimento_exterior_sujeito = _ZERO
    despesa_p10 = _ZERO
    previdencia_oficial = _ZERO
    pensao_paga = _ZERO
    imposto_pago_exterior = _ZERO

    for lancamento in lancamentos:
        sinal = Decimal(-1) if lancamento.estorno_de_id is not None else Decimal(1)
        contribuicao = sinal * lancamento.valor
        codigo = lancamento.conta.codigo_carne_leao

        if lancamento.conta.natureza == NaturezaCaixa.RECEITA:
            # RC-132: só rendimento SUJEITO ao carnê-leão integra a base —
            # rendimento de PJ (fora do modelo notarial) é tributado por
            # retenção na fonte, fora do escopo desta fatia; pensão
            # alimentícia recebida é imune (STF).
            if not rendimento_carne_leao_e_sujeito_ao_recolhimento_mensal(
                codigo, recebido_de=lancamento.recebido_de
            ):
                continue
            rendimento_total_sujeito += contribuicao
            if codigo == CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO:
                rendimento_trabalho_nao_assalariado += contribuicao
            if lancamento.recebido_de == "EX":
                rendimento_exterior_sujeito += contribuicao
        else:  # DESPESA
            if codigo.startswith("P10"):
                despesa_p10 += contribuicao
            elif codigo == "P20.01.00001":  # RC-131(e): previdência oficial
                previdencia_oficial += contribuicao
            elif codigo == "P20.01.00002":  # RC-131(e): pensão alimentícia paga
                pensao_paga += contribuicao
            elif codigo == "P20.01.00003":  # RC-131(e): imposto pago no exterior
                imposto_pago_exterior += contribuicao

    return {
        "rendimento_total_sujeito": rendimento_total_sujeito,
        "rendimento_trabalho_nao_assalariado": rendimento_trabalho_nao_assalariado,
        "rendimento_exterior_sujeito": rendimento_exterior_sujeito,
        "despesa_p10": despesa_p10,
        "previdencia_oficial": previdencia_oficial,
        "pensao_paga": pensao_paga,
        "imposto_pago_exterior": imposto_pago_exterior,
    }


def _apurar_um_mes(
    *,
    ano,
    mes,
    agregados,
    quantidade_dependentes,
    valor_por_dependente,
    faixas,
    reducao_cfg,
    excesso_livro_caixa_anterior,
    saldo_credito_exterior_anterior,
    saldo_pendente_abaixo_de_dez_anterior,
):
    rendimento_total = agregados["rendimento_total_sujeito"]
    rendimento_trabalho = agregados["rendimento_trabalho_nao_assalariado"]

    # Livro-caixa (art. 68/69, RIR/2018): limitado à receita do trabalho
    # não assalariado do MÊS, com o excesso levado aos meses seguintes até
    # dezembro — nunca ao ano seguinte (§1º, imposto em `_apurar_ano_
    # calendario`, que zera o carregamento em dezembro).
    disponivel_livro_caixa = max(_ZERO, agregados["despesa_p10"] + excesso_livro_caixa_anterior)
    limite_receita_trabalho = max(_ZERO, rendimento_trabalho)
    deducao_livro_caixa = min(disponivel_livro_caixa, limite_receita_trabalho)
    excesso_livro_caixa_novo = _q(disponivel_livro_caixa - deducao_livro_caixa)
    if mes == 12:
        excesso_livro_caixa_novo = _ZERO

    dependentes_valor = _q(Decimal(quantidade_dependentes) * valor_por_dependente)

    deducoes_reais_total = _q(
        agregados["previdencia_oficial"]
        + agregados["pensao_paga"]
        + dependentes_valor
        + deducao_livro_caixa
    )

    # Q267 (P&R IRPF 2026): desconto simplificado = 25% do limite da FAIXA
    # DE ALÍQUOTA ZERO da tabela vigente — nunca um número solto (a
    # primeira faixa, ordenada por `ordem`, é sempre a de alíquota 0%).
    faixa_zero = faixas[0]
    if faixa_zero.aliquota != 0:
        raise TabelaCarneLeaoNaoConfigurada(
            "A primeira faixa da tabela progressiva vigente não tem alíquota "
            "zero — dado normativo incoerente (verifique a migração de dados)."
        )
    desconto_simplificado = _q(faixa_zero.limite_superior * Decimal("0.25"))

    # RC-133: a redução usa o rendimento BRUTO (antes de qualquer dedução)
    # — o MESMO valor (`rendimento_total`) nas duas chamadas abaixo, seja
    # qual for a forma de dedução. Só a BASE (primeiro argumento) muda.
    pipeline_real = _pipeline(
        rendimento_total - deducoes_reais_total, rendimento_total, faixas, reducao_cfg
    )
    pipeline_simplificado = _pipeline(
        rendimento_total - desconto_simplificado, rendimento_total, faixas, reducao_cfg
    )

    # HI-33: aplica a forma mais benéfica — decisão pelo IMPOSTO FINAL (após
    # a redução da Lei 15.270/2025), não só pela base ou pelo imposto da
    # tabela isoladamente. Empate (raríssimo, mas possível na fronteira):
    # fica com as deduções REAIS, por serem a regra geral (art. 68) e o
    # desconto simplificado ser a ALTERNATIVA (Q267: "alternativamente...").
    if pipeline_simplificado["imposto_apos_reducao"] < pipeline_real["imposto_apos_reducao"]:
        forma_escolhida = "simplificado"
        pipeline_escolhido = pipeline_simplificado
        deducao_escolhida_valor = desconto_simplificado
    else:
        forma_escolhida = "real"
        pipeline_escolhido = pipeline_real
        deducao_escolhida_valor = deducoes_reais_total

    limite_exterior = _limite_compensacao_exterior(
        rendimento_total,
        agregados["rendimento_exterior_sujeito"],
        deducao_escolhida_valor,
        faixas,
        reducao_cfg,
    )
    credito_exterior_disponivel = _q(
        agregados["imposto_pago_exterior"] + saldo_credito_exterior_anterior
    )
    compensacao_exterior = max(
        _ZERO,
        min(
            credito_exterior_disponivel, limite_exterior, pipeline_escolhido["imposto_apos_reducao"]
        ),
    )
    saldo_credito_exterior_novo = _q(credito_exterior_disponivel - compensacao_exterior)
    if mes == 12:
        saldo_credito_exterior_novo = _ZERO

    imposto_devido_no_mes = _q(pipeline_escolhido["imposto_apos_reducao"] - compensacao_exterior)

    # RIR/2018, art. 938, §§ 4º e 5º (Lei 9.430/1996, art. 68): DARF de
    # imposto sobre a renda abaixo de R$ 10,00 é vedado e o valor soma aos
    # períodos seguintes do mesmo código; repetido para o carnê-leão na
    # página "Carnê-leão — pagar" da Receita (RC-131(d)). Virada do ano: HI-37.
    total_a_considerar = _q(imposto_devido_no_mes + saldo_pendente_abaixo_de_dez_anterior)
    if total_a_considerar < _LIMITE_DARF:
        valor_a_pagar = _ZERO
        saldo_pendente_novo = total_a_considerar
    else:
        valor_a_pagar = total_a_considerar
        saldo_pendente_novo = _ZERO

    return {
        "ano": ano,
        "mes": mes,
        "rendimento_total_sujeito": _q(rendimento_total),
        "rendimento_trabalho_nao_assalariado": _q(rendimento_trabalho),
        "previdencia_oficial": _q(agregados["previdencia_oficial"]),
        "pensao_alimenticia_paga": _q(agregados["pensao_paga"]),
        "dependentes_quantidade": quantidade_dependentes,
        "dependentes_valor": dependentes_valor,
        "despesa_livro_caixa_do_mes": _q(agregados["despesa_p10"]),
        "excesso_livro_caixa_anterior": _q(excesso_livro_caixa_anterior),
        "deducao_livro_caixa_aplicada": _q(deducao_livro_caixa),
        "excesso_livro_caixa_novo": excesso_livro_caixa_novo,
        "deducoes_reais_total": deducoes_reais_total,
        "desconto_simplificado": desconto_simplificado,
        "forma_escolhida": forma_escolhida,
        "memoria_deducoes_reais": pipeline_real,
        "memoria_desconto_simplificado": pipeline_simplificado,
        "base_de_calculo": pipeline_escolhido["base"],
        "imposto_pela_tabela": pipeline_escolhido["imposto_tabela"],
        "reducao_lei_15270_2025": pipeline_escolhido["reducao_aplicada"],
        "imposto_apos_reducao": pipeline_escolhido["imposto_apos_reducao"],
        "imposto_pago_exterior_do_mes": _q(agregados["imposto_pago_exterior"]),
        "limite_compensacao_exterior": limite_exterior,
        "compensacao_exterior_aplicada": compensacao_exterior,
        "saldo_credito_exterior_novo": saldo_credito_exterior_novo,
        "imposto_devido_no_mes": imposto_devido_no_mes,
        "saldo_pendente_abaixo_de_dez_anterior": _q(saldo_pendente_abaixo_de_dez_anterior),
        "valor_a_pagar": valor_a_pagar,
        "saldo_pendente_abaixo_de_dez_novo": saldo_pendente_novo,
        "codigo_darf": "0190",
    }


# ---------------------------------------------------------------------------
# Camada ORM — agregação dos lançamentos e das vigências normativas,
# número de consultas CONSTANTE em relação ao número de meses/lançamentos:
# UMA consulta de lançamentos, UMA de dependentes, TRÊS de vigências
# normativas (uma por tabela) — nunca uma consulta por mês.


def _maior_vigencia_nao_posterior(vigencias_desc, referencia):
    """`vigencias_desc`: lista já ordenada por `vigencia_inicio` DESCENDENTE
    (em memória — DE-089). Devolve a primeira cujo início não é posterior a
    `referencia`, ou `None`."""
    for vigencia in vigencias_desc:
        if vigencia.vigencia_inicio <= referencia:
            return vigencia
    return None


def _lancamentos_por_mes(empresa, ano, mes_final):
    ultimo_dia = calendar.monthrange(ano, mes_final)[1]
    lancamentos = (
        LancamentoCaixa.objects.filter(
            empresa=empresa, data__gte=date(ano, 1, 1), data__lte=date(ano, mes_final, ultimo_dia)
        )
        .select_related("conta")
        .order_by("data", "id")
    )
    por_mes = defaultdict(list)
    for lancamento in lancamentos:
        por_mes[lancamento.data.month].append(lancamento)
    return por_mes


def _dependentes_por_mes(empresa, ano, mes_final):
    registros = list(
        DependentesCarneLeaoCliente.objects.filter(empresa=empresa).order_by("-competencia_inicio")
    )
    resultado = {}
    for mes in range(1, mes_final + 1):
        referencia = date(ano, mes, 1)
        aplicavel = next((r for r in registros if r.competencia_inicio <= referencia), None)
        resultado[mes] = aplicavel.quantidade if aplicavel is not None else 0
    return resultado


def _apurar_ano_calendario(*, empresa, ano, mes_final):
    """Recalcula, do zero, janeiro a `mes_final` do `ano` pedido —
    NUNCA lê nem grava resultado (RC-130). Assume que quem CHAMA já
    verificou autorização/isolamento (mesmo limite declarado de
    `apps.contabilidade.services.apurar_balancete`/`apurar_livro_caixa`) —
    as views deste app aplicam essa verificação via
    `EmpresaEscopadaLivroCaixaMixin`/`PodeLerLivroCaixa`.
    """
    ultimo_dia_do_mes_final = calendar.monthrange(ano, mes_final)[1]
    referencia_final = date(ano, mes_final, ultimo_dia_do_mes_final)

    vigencias_tabela = list(
        VigenciaTabelaProgressivaCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final)
        .order_by("-vigencia_inicio")
        .prefetch_related(
            models.Prefetch(
                "faixas", queryset=FaixaTabelaProgressivaCarneLeao.objects.order_by("ordem")
            )
        )
    )
    vigencias_reducao = list(
        VigenciaReducaoCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final).order_by(
            "-vigencia_inicio"
        )
    )
    vigencias_dependente = list(
        VigenciaDependenteCarneLeao.objects.filter(vigencia_inicio__lte=referencia_final).order_by(
            "-vigencia_inicio"
        )
    )

    lancamentos_por_mes = _lancamentos_por_mes(empresa, ano, mes_final)
    dependentes_por_mes = _dependentes_por_mes(empresa, ano, mes_final)

    excesso_livro_caixa = _ZERO
    saldo_credito_exterior = _ZERO
    saldo_pendente = _ZERO
    meses = []
    for mes in range(1, mes_final + 1):
        referencia = date(ano, mes, 1)
        vig_tabela = _maior_vigencia_nao_posterior(vigencias_tabela, referencia)
        vig_reducao = _maior_vigencia_nao_posterior(vigencias_reducao, referencia)
        vig_dependente = _maior_vigencia_nao_posterior(vigencias_dependente, referencia)
        if vig_tabela is None or not list(vig_tabela.faixas.all()):
            raise TabelaCarneLeaoNaoConfigurada(
                f"Não há tabela progressiva do carnê-leão vigente para {mes:02d}/{ano}."
            )
        if vig_reducao is None:
            raise TabelaCarneLeaoNaoConfigurada(
                f"Não há redução do carnê-leão (Lei 15.270/2025) vigente para {mes:02d}/{ano}."
            )
        if vig_dependente is None:
            raise TabelaCarneLeaoNaoConfigurada(
                f"Não há valor por dependente do carnê-leão vigente para {mes:02d}/{ano}."
            )

        resultado_mes = _apurar_um_mes(
            ano=ano,
            mes=mes,
            agregados=_agregados_do_mes(lancamentos_por_mes.get(mes, [])),
            quantidade_dependentes=dependentes_por_mes.get(mes, 0),
            valor_por_dependente=vig_dependente.valor_por_dependente,
            faixas=list(vig_tabela.faixas.all()),
            reducao_cfg=vig_reducao,
            excesso_livro_caixa_anterior=excesso_livro_caixa,
            saldo_credito_exterior_anterior=saldo_credito_exterior,
            saldo_pendente_abaixo_de_dez_anterior=saldo_pendente,
        )
        resultado_mes["tabela_vigencia_inicio"] = vig_tabela.vigencia_inicio
        resultado_mes["reducao_vigencia_inicio"] = vig_reducao.vigencia_inicio
        resultado_mes["dependente_vigencia_inicio"] = vig_dependente.vigencia_inicio
        meses.append(resultado_mes)

        excesso_livro_caixa = resultado_mes["excesso_livro_caixa_novo"]
        saldo_credito_exterior = resultado_mes["saldo_credito_exterior_novo"]
        saldo_pendente = resultado_mes["saldo_pendente_abaixo_de_dez_novo"]

    return {"empresa_id": empresa.id, "ano": ano, "meses": meses}


def _sob_snapshot(func, **kwargs):
    """DE-067/A5 (auditoria DL-045): leitura sob `REPEATABLE READ`, mesmo
    desenho de `apurar_balanco_patrimonial`/`_apurar_coluna_dre`
    (apps.contabilidade.services) — degrada (sem a garantia extra) quando já
    dentro de uma transação aberta, em vez de quebrar a página."""
    ja_estava_em_transacao = connection.in_atomic_block
    with transaction.atomic():
        if not ja_estava_em_transacao:
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return func(**kwargs)


def apurar_carne_leao_mensal(*, empresa, ano, mes):
    """Demonstrativo do carnê-leão de UM mês, com a memória de cálculo
    completa e o encadeamento (excesso de livro-caixa, crédito do exterior,
    saldo abaixo de R$ 10,00) recalculado desde janeiro do MESMO
    ano-calendário (RC-130)."""
    resultado = _sob_snapshot(_apurar_ano_calendario, empresa=empresa, ano=ano, mes_final=mes)
    return resultado["meses"][-1]


def apurar_carne_leao_anual(*, empresa, ano):
    """Demonstrativo anual: os 12 meses do ano-calendário, cada um com a
    mesma estrutura de `apurar_carne_leao_mensal`."""
    return _sob_snapshot(_apurar_ano_calendario, empresa=empresa, ano=ano, mes_final=12)


def registrar_dependentes_carne_leao(
    *, empresa, quantidade, competencia_inicio, criado_por=None, request=None
):
    """Registra a quantidade de dependentes vigente a partir de
    `competencia_inicio` (HI-35). Mesmo padrão de `criar_conta_livro_caixa`:
    trava a linha da EMPRESA antes de validar o modo de escrituração (N6,
    DL-046 rodada 1) para fechar a mesma corrida já corrigida naquela
    fatia."""
    with (
        transaction.atomic(),
        restricao_como_400(mensagens_de("dependentes_carne_leao_competencia_unica_por_empresa")),
    ):
        empresa_travada = Empresa.objects.select_for_update().get(pk=empresa.pk)
        try:
            recusar_se_nao_livro_caixa(empresa_travada)
        except EmpresaNaoEmModoLivroCaixa as exc:
            raise DependentesCarneLeaoInvalido(exc.mensagem) from exc

        registro = DependentesCarneLeaoCliente(
            empresa=empresa_travada,
            quantidade=quantidade,
            competencia_inicio=competencia_inicio,
            criado_por=criado_por,
        )
        try:
            registro.full_clean()
        except DjangoValidationError as exc:
            raise DependentesCarneLeaoInvalido("; ".join(exc.messages)) from exc
        # A `UniqueConstraint` residual (corrida entre duas requisições que
        # ainda não veem a linha uma da outra) é traduzida pelo
        # `restricao_como_400` do `with`, acima — mesmo padrão de
        # `registrar_regime_tributario` (apps.empresas.services).
        registro.save()
        registrar(
            acao="dependentes_carne_leao.registrado",
            usuario=criado_por,
            escritorio=empresa.escritorio,
            objeto=registro,
            request=request,
            detalhes={
                "empresa_id": empresa.id,
                "quantidade": quantidade,
                "competencia_inicio": competencia_inicio.isoformat(),
            },
        )
    return registro
