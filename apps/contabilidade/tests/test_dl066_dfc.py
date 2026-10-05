"""DL-066, fatia 1 — a DFC (CTB-15): os campos da conta e a apuração
(`apurar_dfc`, `avaliar_emissao_da_dfc`).

A decisão que sustenta tudo é a **E1** do plano: o FATO da DFC é o
lançamento que mexe uma conta de caixa e equivalentes e uma conta de fora
dela. A atividade vem da conta de fora, e a soma das três atividades é a
variação do saldo de caixa **por construção** — não por conciliação
posterior. É isso que faz do item 45 uma identidade que precisa valer, com
veto quando não vale.

Cobre os critérios de aceite 2, 3, 5 e 7 do plano
(`docs/planos/DL-066-dfc.md`); o caso de referência (critério 1) e a
apresentação do método indireto (critério 8) são da etapa seguinte da fatia.

- 2: a variação apurada pelas atividades é **igual** à variação dos saldos
  das contas de caixa e equivalentes, lida pelo mesmo motor do Balanço;
- 3: movimento entre duas contas de caixa **não** é fluxo (item 9 do CPC 03);
- 5: contrapartida sem atividade veta e **nomeia** a conta;
- 7: conta de caixa sem movimento no período não entra no saldo conciliado;
- mais: o item 12 (uma transação, duas atividades) veta nomeando, e a guarda
  de coerência do modelo (caixa **e** atividade na mesma conta).

Dados 100% sintéticos, criados nos próprios testes. Datas em 2026.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contabilidade.models import (
    ClassificacaoFluxoCaixa,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    _TITULOS_DAS_PENDENCIAS_DA_DFC,
    apurar_dfc,
    avaliar_emissao_da_dfc,
    criar_lancamento,
)
from apps.contabilidade.tests import test_dl061_dmpl as _base

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
ATIVO = TipoConta.ATIVO
RECEITA = TipoConta.RECEITA
DESPESA = TipoConta.DESPESA

ATIV = ClassificacaoFluxoCaixa.OPERACIONAL
INVEST = ClassificacaoFluxoCaixa.INVESTIMENTO
FINANC = ClassificacaoFluxoCaixa.FINANCIAMENTO

ANO = 2026
MES = 3


def _dec(valor):
    return Decimal(valor)


def _conta(empresa, codigo, nome, tipo, natureza, *, dfc=None, caixa=False):
    """Conta criada e validada por `full_clean()`, no mesmo padrão do resto
    do módulo: o plano de teste só contém contas que o próprio cadastro
    aceitaria."""
    conta = _base._conta(empresa, codigo, nome, tipo, natureza)
    if dfc is not None:
        conta.classificacao_dfc = dfc
    conta.caixa_e_equivalentes = caixa
    conta.full_clean()
    conta.save()
    return conta


def _cenario(nome="dl066"):
    """Empresa mínima de DFC: duas contas de caixa e as três contrapartes —
    receita, imobilizado e empréstimo, uma por atividade."""
    empresa = _base._empresa(f"Empresa {nome}")
    gestor = _base._gestor(empresa, f"gestor-{nome}-{empresa.pk}")
    contas = {
        "caixa": _conta(empresa, "1.1", "Caixa", ATIVO, D, caixa=True),
        "banco": _conta(empresa, "1.2", "Banco Conta Corrente", ATIVO, D, caixa=True),
        "receita": _conta(empresa, "4.1", "Receita de Vendas", RECEITA, C, dfc=ATIV),
        "imobilizado": _conta(empresa, "1.3", "Veículos", ATIVO, D, dfc=INVEST),
        "emprestimo": _conta(
            empresa, "2.1", "Empréstimo de Longo Prazo", TipoConta.PASSIVO, C, dfc=FINANC
        ),
        "despesa": _conta(empresa, "5.1", "Despesa Operacional", DESPESA, D, dfc=ATIV),
    }
    return empresa, contas, gestor


def _lancar(empresa, data, historico, debito, credito, valor, *, criado_por=None):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": _dec(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": _dec(valor)},
        ],
        criado_por=criado_por,
    )


# ---------------------------------------------------------------------------
# Critério 2 — a identidade do item 45
# ---------------------------------------------------------------------------


def test_criterio2_a_variacao_das_atividades_iguala_a_dos_saldos():
    """A conciliação do CPC 03 (R2), item 45: "apresentar uma conciliação dos
    montantes em sua demonstração dos fluxos de caixa com os respectivos
    itens apresentados no balanço patrimonial". Aqui ela é uma IDENTIDADE, e
    não um ajuste — porque o número sai do lançamento, não de soma de
    ajustes."""
    empresa, contas, gestor = _cenario("c2")
    # Abertura com 40.000,00 de caixa, o que a norma chama de caixa inicial
    # do caso de referência do plano.
    _lancar(empresa, date(2025, 12, 31), "Abertura", contas["caixa"], contas["receita"], "40000.00")
    # Operação: entra 100.000,00 de venda.
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    # Investimento: sai 30.000,00 para o veículo.
    _lancar(
        empresa,
        date(2026, 3, 12),
        "Compra de veículo",
        contas["imobilizado"],
        contas["banco"],
        "30000.00",
    )
    # Financiamento: entra 10.000,00 de empréstimo.
    _lancar(
        empresa, date(2026, 3, 15), "Empréstimo", contas["banco"], contas["emprestimo"], "10000.00"
    )
    # Operação: sai 15.000,00 de despesa.
    _lancar(
        empresa, date(2026, 3, 20), "Despesa paga", contas["despesa"], contas["caixa"], "15000.00"
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    assert dfc["atividades"] == {
        ATIV: _dec("85000.00"),
        INVEST: _dec("-30000.00"),
        FINANC: _dec("10000.00"),
    }
    assert dfc["caixa"]["inicial"] == _dec("40000.00")
    assert dfc["caixa"]["final"] == _dec("105000.00")
    assert dfc["caixa"]["variacao"] == _dec("65000.00")
    assert dfc["conciliacao"]["diferenca"] == _dec("0.00"), (
        "a soma das três atividades tem de bater com a variação do saldo de "
        "caixa — é o item 45, e é identidade, não conciliação"
    )
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is True


# ---------------------------------------------------------------------------
# Critério 3 — o item 9: movimento entre contas de caixa não é fluxo
# ---------------------------------------------------------------------------


def test_criterio3_transferencia_entre_contas_de_caixa_nao_e_fluxo():
    """Item 9 do CPC 03 (R2): *"os fluxos de caixa excluem movimentos entre
    itens que constituem caixa ou equivalentes de caixa"*.

    É também a resposta ao risco que o mapa de paridade apontava: tratar
    reclassificação e ajuste que passam pela conta banco como se fossem
    dinheiro entrando e saindo da empresa."""
    empresa, contas, gestor = _cenario("c3")
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    saldo_antes = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)["caixa"]["final"]
    # Transferência de 60.000,00 da conta banco para a conta caixa: o total
    # não muda, e **nenhum** fluxo pode aparecer.
    _lancar(
        empresa,
        date(2026, 3, 18),
        "Transferência entre contas",
        contas["caixa"],
        contas["banco"],
        "60000.00",
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    assert dfc["atividades"][ATIV] == _dec("100000.00"), "a transferência entrou como fluxo"
    assert dfc["caixa"]["final"] == saldo_antes, "o saldo de caixa mudou sem entrada de dinheiro"
    assert dfc["conciliacao"]["diferenca"] == _dec("0.00")


# ---------------------------------------------------------------------------
# Critério 5 — contrapartida sem atividade
# ---------------------------------------------------------------------------


def test_criterio5_contrapartida_sem_atividade_veta_e_nomeia_a_conta():
    empresa, contas, gestor = _cenario("c5")
    sem_atividade = _base._conta(empresa, "1.9", "Ajusta de Regularização", ATIVO, D)
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    _lancar(empresa, date(2026, 3, 22), "Ajuste", contas["banco"], sem_atividade, "500.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    emissao = avaliar_emissao_da_dfc(dfc)

    assert emissao["pode_emitir"] is False
    pendencia = dfc["pendencias"]["lancamentos_sem_atividade"]
    assert len(pendencia) == 1
    assert "1.9" in pendencia[0]["contas"], "o veto tem de dizer QUAL conta falta classificar"
    assert "Ajusta de Regularização" in pendencia[0]["contas"]
    assert any("atividade" in motivo for motivo in emissao["motivos"])


# ---------------------------------------------------------------------------
# Limite — o item 12: uma transação, duas atividades
# ---------------------------------------------------------------------------


def test_limite_uma_transacao_com_duas_atividades_veta_nomeando():
    """Item 12 do CPC 03 (R2): *"uma única transação pode incluir fluxos de
    caixa classificados em mais de uma atividade"* — o exemplo da norma é o
    pagamento de empréstimo, em que os juros são operacionais e o principal
    é de financiamento. A regra por conta não decide esse caso."""
    empresa, contas, gestor = _cenario("c12")
    juros = _conta(empresa, "5.2", "Juros sobre Empréstimo", DESPESA, D, dfc=ATIV)
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    # **UM** lançamento, três partidas: juros (operacional) e principal do
    # empréstimo (financiamento) contra o banco. É o exemplo do item 12, e é
    # por isso que ele é um lançamento só — em dois lançamentos separados a
    # regra por conta decidiria, e o caso nem apareceria.
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 25),
        historico="Pagamento de parcela — juros e principal",
        itens=[
            {"conta": juros, "tipo": TipoPartida.DEBITO, "valor": _dec("1000.00")},
            {"conta": contas["emprestimo"], "tipo": TipoPartida.DEBITO, "valor": _dec("9000.00")},
            {"conta": contas["banco"], "tipo": TipoPartida.CREDITO, "valor": _dec("10000.00")},
        ],
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    assert dfc["pendencias"]["lancamento_com_atividades_conflitantes"], (
        "o lançamento com duas atividades tem de vetar, esperando a marcação manual"
    )
    conflito = dfc["pendencias"]["lancamento_com_atividades_conflitantes"][0]
    assert sorted(conflito["atividades"]) == sorted([ATIV, FINANC])
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is False


# ---------------------------------------------------------------------------
# Critério 7 — conta de caixa sem movimento
# ---------------------------------------------------------------------------


def test_criterio7_conta_de_caixa_sem_movimento_nao_entra_no_saldo():
    empresa, contas, gestor = _cenario("c7")
    # A conta existe, é caixa e equivalentes, e nunca se move: tem de entrar
    # na conciliação do item 45 com zero nos dois lados.
    _conta(empresa, "1.4", "Aplicação de Curto Prazo", ATIVO, D, caixa=True)
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    codigos = [linha["conta"] for linha in dfc["caixa"]["contas"]]
    assert "1.4" in codigos, "a conta de caixa tem de aparecer na conciliação do item 45"
    proxima = next(linha for linha in dfc["caixa"]["contas"] if linha["conta"] == "1.4")
    assert proxima["saldo_inicial"] == _dec("0.00")
    assert proxima["saldo_final"] == _dec("0.00")


# ---------------------------------------------------------------------------
# O contrato das pendências e a partição
# ---------------------------------------------------------------------------


def test_as_tuplas_de_pendencias_particionam_o_inventario_da_apuracao():
    """Teste derivado, como o de `apurar_dlpa` e `apurar_dmpl`: a união das
    pendências que vetam com as que só avisam tem de ser **exatamente** o
    inventário de chaves de `apurar_dfc["pendencias"]`, e nenhuma chave pode
    estar nas duas. Sem isso, uma pendência nova nasce invisível para a
    decisão de emissão."""
    empresa, contas, gestor = _cenario("contrato")
    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    assert set(dfc["pendencias"]) == set(_TITULOS_DAS_PENDENCIAS_DA_DFC)


# ---------------------------------------------------------------------------
# As guardas de coerência do modelo
# ---------------------------------------------------------------------------


def test_conta_de_caixa_nao_pode_ter_atividade():
    """Na DFC a conta de caixa é o LADO CAIXA do fluxo e a atividade é da
    contrapartida (E1). Uma conta que é as duas coisas faria a apuração
    contar o mesmo fluxo duas vezes."""
    empresa, contas, gestor = _cenario("coerencia")
    contas["banco"].classificacao_dfc = ATIV
    with pytest.raises(ValidationError) as erro:
        contas["banco"].full_clean()
    assert "caixa e equivalente" in str(erro.value)


def test_item_sem_caixa_somente_em_conta_de_resultado():
    empresa, contas, gestor = _cenario("coerencia-2")
    contas["imobilizado"].item_de_resultado_sem_caixa = True
    with pytest.raises(ValidationError) as erro:
        contas["imobilizado"].full_clean()
    assert "resultado" in str(erro.value)


def test_receita_pode_ser_item_sem_caixa():
    """O item 20(b) existe para depreciação, amortização e provisões — são
    despesa e receita. A guarda acima não pode estreitar a regra."""
    empresa, contas, gestor = _cenario("coerencia-3")
    contas["despesa"].item_de_resultado_sem_caixa = True
    contas["despesa"].full_clean()
    contas["despesa"].save()
    contas["despesa"].refresh_from_db()
    assert contas["despesa"].item_de_resultado_sem_caixa is True


def test_saldo_bancario_a_descoberto_e_caixa_e_equivalentes():
    """**Item 8 do CPC 03 (R2)** (DE-099): *"saldos bancários a descoberto,
    decorrentes de (…) cheques especiais ou contas correntes garantidas […]
    são incluídos como componente de caixa e equivalentes de caixa"*.

    É o caso que faz o campo aceitar conta de PASSIVO: o descoberto é ativo
    negativo na prática contábil e conta de passivo no plano brasileiro. E é
    justamente um caso em que o **sinal** importa — somar um saldo credor como
    se fosse dinheiro em caixa inflaria a conciliação do item 45."""
    empresa, contas, gestor = _cenario("descoberto")
    descoberto = _conta(empresa, "2.9", "Cheque Especial", TipoConta.PASSIVO, C, caixa=True)
    # A empresa recebe 100.000,00 e usa o cheque especial em 30.000,00.
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    _lancar(
        empresa,
        date(2026, 3, 15),
        "Pagamento com cheque especial",
        contas["despesa"],
        descoberto,
        "30000.00",
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    linha = next(linha for linha in dfc["caixa"]["contas"] if linha["conta"] == "2.9")
    assert linha["saldo_final"] == _dec("-30000.00"), (
        "o descoberto é ativo negativo: somar 30.000,00 de passivo como se fosse "
        "caixa inflaria a conciliação do item 45"
    )
    # 100.000,00 entraram e 30.000,00 saíram pelo cheque especial: a variação
    # do conjunto de caixa e equivalentes é 70.000,00.
    assert dfc["caixa"]["variacao"] == _dec("70000.00")
    assert dfc["conciliacao"]["diferenca"] == _dec("0.00")


def test_classificacao_dfc_vazia_e_normalizada_para_none():
    """Mesma defesa das outras três classificações: `""` nunca é estado
    válido, senão a apuração a leria como atividade DESCONHECIDA em vez de
    "sem classificação"."""
    empresa, contas, gestor = _cenario("vazia")
    contas["receita"].classificacao_dfc = ""
    contas["receita"].full_clean()
    assert contas["receita"].classificacao_dfc is None
