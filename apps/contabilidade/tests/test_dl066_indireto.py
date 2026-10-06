"""DL-066, etapa 2 — o método INDIRETO da DFC (`operacional_indireto`).

A apresentação do mesmo número da E1: o fluxo operacional continua sendo o
apurado pelos lançamentos, e o indireto é a conciliação entre o LUCRO LÍQUIDO
do período e esse número, com os ajustes do item 20 do CPC 03 derivados das
contas — família 20(a) (variação de conta patrimonial operacional), 20(b)
(item de resultado que não afeta o caixa) e 20(c) (item de resultado tratado
como investimento ou financiamento).

Cobre os critérios de aceite 16, 17 e 18 da etapa 2
(`docs/planos/DL-066-dfc.md`):

- 16: o caso de referência do plano fecha **ao centavo** no método indireto,
  com `confere = True` (LL 90.000,00 + depreciação 15.000,00 − aumento de
  Contas a Receber 20.000,00 = 85.000,00);
- 17: as três famílias do item 20 aparecem nomeadas, com sinal, e o
  lançamento de zeramento não contamina nenhuma delas;
- 18: a identidade que não fecha veta (`indireto_nao_fecha`) e nomeia a
  diferença — e nenhum saldo é ajustado para fechar.

Mais: a precedência 20(b) sobre 20(c), e o retorno antecipado (empresa sem
conta de caixa marcada) mantendo `operacional_indireto = None`.

Dados 100% sintéticos. Datas em 2026 (abertura em 2025, fora da janela).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import (
    ClassificacaoDre,
    ClassificacaoFluxoCaixa,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    apurar_dfc,
    avaliar_emissao_da_dfc,
    criar_lancamento,
)
from apps.contabilidade.tests import test_dl061_dmpl as _base

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
ATIVO = TipoConta.ATIVO
PASSIVO = TipoConta.PASSIVO
RECEITA = TipoConta.RECEITA
DESPESA = TipoConta.DESPESA

ATIV = ClassificacaoFluxoCaixa.OPERACIONAL
INVEST = ClassificacaoFluxoCaixa.INVESTIMENTO
FINANC = ClassificacaoFluxoCaixa.FINANCIAMENTO

ANO = 2026
MES = 3


def _dec(valor):
    return Decimal(valor)


def _conta_dfc(
    empresa,
    codigo,
    nome,
    tipo,
    natureza,
    *,
    dfc=None,
    caixa=False,
    sem_caixa=False,
    dre=None,
    pai=None,
):
    """Conta criada como o cadastro aceitaria (`full_clean()`), já com os
    campos da DFC e — quando informada — a linha da DRE. A linha da DRE é
    necessária porque o lucro líquido vem do MESMO motor que publica a DRE
    (DE-020): conta de resultado sem linha cai no resíduo e não entra no
    lucro."""
    conta = _base._conta(empresa, codigo, nome, tipo, natureza, pai=pai)
    if dfc is not None:
        conta.classificacao_dfc = dfc
    conta.caixa_e_equivalentes = caixa
    conta.item_de_resultado_sem_caixa = sem_caixa
    if dre is not None:
        conta.classificacao_dre = dre
    conta.full_clean()
    conta.save()
    return conta


def _lancar(empresa, data, historico, debito, credito, valor):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": _dec(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": _dec(valor)},
        ],
        criado_por=None,
    )


def _cenario(nome="indireto"):
    """O caso de referência do plano (critério 16), montado lançamento a
    lançamento — os mesmos números da tabela do plano."""
    empresa = _base._empresa(f"Empresa {nome}")
    contas = _base._plano_basico(empresa)
    gestor = _base._gestor(empresa, f"gestor-{nome}-{empresa.pk}")
    caixa = contas["caixa"]
    caixa.caixa_e_equivalentes = True
    caixa.full_clean()
    caixa.save()
    receita = contas["receita"]
    receita.classificacao_dre = ClassificacaoDre.RECEITA_BRUTA
    receita.classificacao_dfc = ATIV
    receita.full_clean()
    receita.save()
    extras = {
        "caixa": caixa,
        "receita": receita,
        "capital": contas["capital"],
        "resultado": contas["resultado"],
        "a_receber": _conta_dfc(empresa, "1.4", "Contas a Receber", ATIVO, D, dfc=ATIV),
        "depreciacao": _conta_dfc(
            empresa,
            "5.2",
            "Depreciação",
            DESPESA,
            D,
            sem_caixa=True,
            dre=ClassificacaoDre.OUTRAS_DESPESAS,
        ),
        "da_acumulada": _conta_dfc(empresa, "1.5", "Depreciação Acumulada", ATIVO, C),
        "veiculo": _conta_dfc(empresa, "1.6", "Veículos", ATIVO, D, dfc=INVEST),
        "emprestimo": _conta_dfc(
            empresa, "2.2", "Empréstimo de Longo Prazo", PASSIVO, C, dfc=FINANC
        ),
    }
    return empresa, extras, gestor


def _referencia(empresa, contas):
    """Os seis lançamentos do caso de referência. A abertura fica em 2025, FORA
    da janela da apuração — ela só existe para o caixa inicial ter 40.000,00."""
    _lancar(empresa, date(2025, 12, 31), "Abertura", contas["caixa"], contas["capital"], "40000.00")
    _lancar(
        empresa,
        date(2026, 2, 10),
        "Venda a prazo",
        contas["a_receber"],
        contas["receita"],
        "20000.00",
    )
    _lancar(
        empresa, date(2026, 3, 10), "Venda a vista", contas["caixa"], contas["receita"], "85000.00"
    )
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Depreciação do período",
        contas["depreciacao"],
        contas["da_acumulada"],
        "15000.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 12),
        "Compra de veículo",
        contas["veiculo"],
        contas["caixa"],
        "30000.00",
    )
    _lancar(
        empresa, date(2026, 3, 15), "Empréstimo", contas["caixa"], contas["emprestimo"], "10000.00"
    )


# ---------------------------------------------------------------------------
# Critério 16 — o caso de referência, ao centavo
# ---------------------------------------------------------------------------


def test_criterio16_o_caso_de_referencia_fecha_no_indireto_ao_centavo():
    empresa, contas, gestor = _cenario("c16")
    _referencia(empresa, contas)

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    indireto = dfc["operacional_indireto"]

    assert indireto["lucro_liquido"] == _dec("90000.00")
    assert indireto["total_dos_ajustes"] == _dec("-5000.00")
    assert indireto["fluxo_operacional"] == _dec("85000.00")
    assert indireto["fluxo_operacional_pelo_direto"] == _dec("85000.00")
    assert indireto["diferenca"] == _dec("0.00")
    assert indireto["confere"] is True
    # E a conciliação do item 45 segue valendo: 40.000,00 + 65.000,00.
    assert dfc["caixa"]["inicial"] == _dec("40000.00")
    assert dfc["caixa"]["final"] == _dec("105000.00")
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is True


def test_criterio16_os_ajustes_vem_nomeados_com_item_sinal_e_valor():
    empresa, contas, gestor = _cenario("ajustes")
    _referencia(empresa, contas)

    ajustes = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)["operacional_indireto"]["ajustes"]

    assert [
        (ajuste["item"], ajuste["conta"], ajuste["sinal"], ajuste["valor"]) for ajuste in ajustes
    ] == [
        ("20(a)", "1.4", "-", _dec("20000.00")),
        ("20(b)", "5.2", "+", _dec("15000.00")),
    ]
    assert ajustes[0]["efeito"] == _dec("-20000.00")
    assert ajustes[1]["efeito"] == _dec("15000.00")
    # Ordenação: 20(a), 20(b), 20(c) — e dentro do item, por código.
    assert [ajuste["item"] for ajuste in ajustes] == ["20(a)", "20(b)"]


# ---------------------------------------------------------------------------
# Critério 17 — cada família isolada, e o zeramento de fora
# ---------------------------------------------------------------------------


def test_criterio17_familia_20a_a_variacao_de_conta_patrimonial_operacional():
    """Aumento de ativo operacional consome caixa: o ajuste é NEGATIVO, como
    o aumento de Contas a Receber do caso de referência."""
    empresa, contas, gestor = _cenario("20a")
    estoque = _conta_dfc(empresa, "1.7", "Estoques", ATIVO, D, dfc=ATIV)
    _lancar(empresa, date(2026, 3, 10), "Compra de estoque", estoque, contas["caixa"], "10000.00")

    indireto = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)["operacional_indireto"]

    assert indireto["lucro_liquido"] == _dec("0.00")
    assert indireto["ajustes"] == [
        {
            "item": "20(a)",
            "conta": "1.7",
            "nome": "Estoques",
            "descricao": "variação de conta patrimonial operacional",
            "valor": _dec("10000.00"),
            "sinal": "-",
            "efeito": _dec("-10000.00"),
        }
    ]
    assert indireto["confere"] is True
    assert indireto["fluxo_operacional"] == _dec("-10000.00")


def test_criterio17_familia_20b_o_item_de_resultado_que_nao_afeta_caixa():
    """Depreciação: reduz o lucro sem mexer em caixa, e volta com sinal +."""
    empresa, contas, gestor = _cenario("20b")
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Depreciação do período",
        contas["depreciacao"],
        contas["da_acumulada"],
        "15000.00",
    )

    indireto = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)["operacional_indireto"]

    assert indireto["lucro_liquido"] == _dec("-15000.00")
    assert [(a["item"], a["sinal"], a["valor"]) for a in indireto["ajustes"]] == [
        ("20(b)", "+", _dec("15000.00"))
    ]
    assert indireto["confere"] is True
    assert indireto["fluxo_operacional"] == _dec("0.00")


def test_criterio17_familia_20c_o_resultado_tratado_como_outra_atividade():
    """Despesa financeira classificada como financiamento: o efeito dela sai do
    operacional, e o caixa pago já foi direto para financiamento."""
    empresa, contas, gestor = _cenario("20c")
    financeira = _conta_dfc(
        empresa,
        "5.3",
        "Despesas Financeiras",
        DESPESA,
        D,
        dfc=FINANC,
        dre=ClassificacaoDre.DESPESAS_FINANCEIRAS,
    )
    _lancar(empresa, date(2026, 3, 10), "Juros pagos", financeira, contas["caixa"], "10000.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    indireto = dfc["operacional_indireto"]

    assert dfc["atividades"][FINANC] == _dec("-10000.00")
    assert indireto["lucro_liquido"] == _dec("-10000.00")
    assert [(a["item"], a["sinal"], a["valor"]) for a in indireto["ajustes"]] == [
        ("20(c)", "+", _dec("10000.00"))
    ]
    assert indireto["confere"] is True
    assert indireto["fluxo_operacional"] == _dec("0.00")


def test_criterio17_o_zeramento_do_resultado_nao_contamina_nenhuma_familia():
    """A armadilha que a DL-061 já registrou: o zeramento é gravado no ÚLTIMO
    DIA do período e, sem o filtro (o mesmo da DRE), a receita do mês sairia
    zerada e a identidade acusaria uma diferença que não existe. Aqui ele é
    fabricado direto pelo ORM porque `criar_lancamento` recusa a chave
    reservada `zeramento:` — o teste cobre o FILTRO da apuração."""
    empresa, contas, gestor = _cenario("zeramento")
    _lancar(
        empresa, date(2026, 1, 10), "Venda a vista", contas["caixa"], contas["receita"], "1000.00"
    )
    lancamento_de_zeramento = LancamentoContabil.objects.create(
        empresa=empresa,
        data=date(2026, 1, 31),
        historico="Zeramento do resultado (fabricado pelo teste)",
        chave_idempotencia="zeramento:2026-01:etapa1:teste-do-indireto",
    )
    ItemLancamento.objects.create(
        lancamento=lancamento_de_zeramento,
        conta=contas["receita"],
        tipo=TipoPartida.DEBITO,
        valor=_dec("1000.00"),
    )
    ItemLancamento.objects.create(
        lancamento=lancamento_de_zeramento,
        conta=contas["resultado"],
        tipo=TipoPartida.CREDITO,
        valor=_dec("1000.00"),
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=1)
    indireto = dfc["operacional_indireto"]

    assert indireto["lucro_liquido"] == _dec("1000.00"), (
        "o zeramento não pode entrar no lucro do período"
    )
    assert indireto["ajustes"] == []
    assert indireto["confere"] is True
    assert dfc["pendencias"]["indireto_nao_fecha"] == []


def test_precedencia_o_20b_vem_antes_do_20c():
    """Conta marcada "sem caixa" E classificada como financiamento: "não afeta
    caixa" declara que ela está fora do fluxo inteiro, e a família é a 20(b) —
    a atividade não a move para a 20(c)."""
    empresa, contas, gestor = _cenario("precedencia")
    conta_mista = _conta_dfc(
        empresa,
        "5.4",
        "Despesa Mista",
        DESPESA,
        D,
        dfc=FINANC,
        sem_caixa=True,
        dre=ClassificacaoDre.OUTRAS_DESPESAS,
    )
    contraparte = _conta_dfc(empresa, "1.8", "Contraparte Neutra", ATIVO, D)
    _lancar(empresa, date(2026, 3, 10), "Ajuste sem caixa", conta_mista, contraparte, "5000.00")

    indireto = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)["operacional_indireto"]

    assert [(a["item"], a["conta"]) for a in indireto["ajustes"]] == [("20(b)", "5.4")]
    assert indireto["confere"] is True


# ---------------------------------------------------------------------------
# Critério 18 — a identidade que não fecha VETA e nomeia a diferença
# ---------------------------------------------------------------------------


def test_criterio18_a_identidade_que_nao_fecha_veta_e_nomeia_a_diferenca():
    """A marcação dupla — a despesa marcada "sem caixa" E a contrapartida
    patrimonial marcada "operacional" — ajusta o MESMO fato duas vezes. A
    identidade acusa, a pendência veta, e NENHUM saldo é ajustado para
    fechar: o número continua sendo o dos lançamentos."""
    empresa, contas, gestor = _cenario("nao-fecha")
    despesa = _conta_dfc(
        empresa,
        "5.5",
        "Despesa de Provisão",
        DESPESA,
        D,
        sem_caixa=True,
        dre=ClassificacaoDre.OUTRAS_DESPESAS,
    )
    provisao = _conta_dfc(empresa, "2.3", "Provisão Operacional", PASSIVO, C, dfc=ATIV)
    _lancar(empresa, date(2026, 3, 10), "Provisão do período", despesa, provisao, "10000.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    indireto = dfc["operacional_indireto"]

    assert indireto["confere"] is False
    assert indireto["diferenca"] == _dec("10000.00")
    assert indireto["fluxo_operacional"] == _dec("10000.00")
    assert indireto["fluxo_operacional_pelo_direto"] == _dec("0.00")

    pendencias = dfc["pendencias"]["indireto_nao_fecha"]
    assert len(pendencias) == 1
    assert pendencias[0]["diferenca"] == _dec("10000.00")

    veredito = avaliar_emissao_da_dfc(dfc)
    assert veredito["pode_emitir"] is False
    assert any("conciliação do método indireto" in motivo for motivo in veredito["motivos"])

    # Nenhum saldo foi calibrado para fechar: a conciliação do item 45 continua
    # valendo (sem caixa nenhum, variação zero), e a identidade do caixa não
    # vira pendência — o que diverge é a decomposição, e ela é que nomeia.
    assert dfc["conciliacao"]["diferenca"] == _dec("0.00")
    assert dfc["pendencias"]["diferenca_de_caixa"] == []


# ---------------------------------------------------------------------------
# Retorno antecipado — a semântica da fatia 1 é preservada
# ---------------------------------------------------------------------------


def test_sem_conta_de_caixa_marcada_o_indireto_continua_none():
    empresa = _base._empresa("Empresa sem caixa marcada")
    _base._plano_basico(empresa)

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    assert dfc["operacional_indireto"] is None
