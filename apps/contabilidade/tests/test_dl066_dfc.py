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
    ClassificacaoDre,
    ClassificacaoFluxoCaixa,
    Conta,
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


def _conta(empresa, codigo, nome, tipo, natureza, *, dfc=None, caixa=False, pai=None, dre=None):
    """Conta criada e validada por `full_clean()`, no mesmo padrão do resto
    do módulo: o plano de teste só contém contas que o próprio cadastro
    aceitaria."""
    conta = _base._conta(empresa, codigo, nome, tipo, natureza, pai=pai)
    if dfc is not None:
        conta.classificacao_dfc = dfc
    conta.caixa_e_equivalentes = caixa
    if dre is not None:
        # Etapa 2: a linha da DRE entra no cenário porque o método indireto
        # tira o lucro do MESMO motor que publica a DRE (DE-020) — conta de
        # resultado sem linha cai no resíduo, e a identidade do item 20A veta
        # a emissão com razão (critério 8 do plano). Sem isto, os cenários
        # deste arquivo mediam `pode_emitir` de um plano que não publica
        # demonstração nenhuma.
        conta.classificacao_dre = dre
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
        "receita": _conta(
            empresa,
            "4.1",
            "Receita de Vendas",
            RECEITA,
            C,
            dfc=ATIV,
            dre=ClassificacaoDre.RECEITA_BRUTA,
        ),
        "imobilizado": _conta(empresa, "1.3", "Veículos", ATIVO, D, dfc=INVEST),
        "emprestimo": _conta(
            empresa, "2.1", "Empréstimo de Longo Prazo", TipoConta.PASSIVO, C, dfc=FINANC
        ),
        "despesa": _conta(
            empresa,
            "5.1",
            "Despesa Operacional",
            DESPESA,
            D,
            dfc=ATIV,
            dre=ClassificacaoDre.OUTRAS_DESPESAS,
        ),
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


# BL-629 (N4 da reconferência da DL-066): esta lista é EXPLÍCITA e digitada
# aqui, e não derivada de `_TITULOS_DAS_PENDENCIAS_DA_DFC` — o teste antigo
# comparava a apuração com o mesmo dicionário que a construía (tautológico:
# remover uma chave dele não fazia o teste falhar, e uma pendência nova sob
# chave fora do dicionário estouraria `KeyError` sem ninguém perceber). Com a
# enumeração deliberada, adicionar ou remover chave exige DECIDIR aqui.
CHAVES_ESPERADAS_DAS_PENDENCIAS_DA_DFC = {
    "conta_com_dois_papeis",
    "lancamentos_sem_atividade",
    "classificacao_fora_do_enum",
    "lancamento_com_atividades_conflitantes",
    "diferenca_de_caixa",
    "indireto_nao_fecha",
}


def test_as_tuplas_de_pendencias_particionam_o_inventario_da_apuracao():
    """Teste derivado, como o de `apurar_dlpa` e `apurar_dmpl`: a união das
    pendências que vetam com as que só avisam tem de ser **exatamente** o
    inventário de chaves de `apurar_dfc["pendencias"]`, e nenhuma chave pode
    estar nas duas. Sem isso, uma pendência nova nasce invisível para a
    decisão de emissão (BL-629: e a enumeração tem de ser nossa, não do
    dicionário que o código constrói)."""
    empresa, contas, gestor = _cenario("contrato")
    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    assert set(dfc["pendencias"]) == CHAVES_ESPERADAS_DAS_PENDENCIAS_DA_DFC
    assert set(_TITULOS_DAS_PENDENCIAS_DA_DFC) == CHAVES_ESPERADAS_DAS_PENDENCIAS_DA_DFC


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


# ---------------------------------------------------------------------------
# Correção única da auditoria da fatia 1 (AGENTS.md §3.1: uma auditoria, uma
# correção, uma reconferência). Cada teste abaixo é a reprodução do achado.
# ---------------------------------------------------------------------------


def test_a1_contrapartida_sem_classificacao_veta_mesmo_com_outra_classificada():
    """**Achado A1 (GRAVE).** A versão anterior filtrava as contrapartes sem
    classificação ANTES de avaliar, e uma contraparte classificada sozinha
    decidia o lançamento inteiro.

    Reprodução do auditor: uma contraparte classificada decidia o lançamento
    inteiro, e as outras eram silenciosamente descartadas — **sem nenhuma
    pendência**, com `pode_emitir=True` e a conciliação fechando. O veto do
    item 45 **não** pega isso, porque a identidade continua valendo — é
    exatamente o risco que a E1 promete eliminar.

    O caso **precisa tocar caixa** (é o lançamento que mexe caixa que é fluxo)
    e precisa ter **as duas** situações no mesmo lançamento. Um lançamento que
    não mexe caixa não é fluxo pelo item 9 e não chega nem aqui — foi o
    defeito da primeira versão deste teste, apontado pela execução em SQLite
    antes de subir para a CI."""
    empresa, contas, gestor = _cenario("a1")
    sem_atividade = _conta(empresa, "2.8", "Empréstimo a Classificar", TipoConta.PASSIVO, C)
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    # UM lançamento, três partidas: despesa classificada como operacional,
    # empréstimo SEM classificação, e a saída de caixa. A versão anterior
    # somava o fluxo inteiro na operação e não gerava pendência nenhuma.
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, 22),
        historico="Amortização com contrapartida parcialmente classificada",
        itens=[
            {"conta": contas["despesa"], "tipo": TipoPartida.DEBITO, "valor": _dec("10000.00")},
            {"conta": sem_atividade, "tipo": TipoPartida.DEBITO, "valor": _dec("10000.00")},
            {"conta": contas["banco"], "tipo": TipoPartida.CREDITO, "valor": _dec("20000.00")},
        ],
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    pendencia = dfc["pendencias"]["lancamentos_sem_atividade"]
    assert len(pendencia) == 1, "a contraparte sem classificação tem de vetar"
    assert "2.8" in pendencia[0]["contas"], "e o veto tem de dizer qual conta"
    assert dfc["atividades"][ATIV] == _dec("100000.00"), (
        "os 10.000 não podem entrar na operação: a classificação é do EMPRÉSTIMO, não da despesa"
    )
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is False


def test_a2_atividade_fora_do_enum_veta_em_vez_de_explodir():
    """**Achado A2 (GRAVE).** `atividades[chave] += fluxo` **lê antes de
    escrever** em Python, então chave nova nunca nasce e o `KeyError` subia
    cru — 500 em tela e API. O `CheckConstraint` barra `""`, mas **não** barra
    valor fora do enum, e o padrão do módulo (BL-476/BL-493) é o oposto: valor
    ilegível aparece **nomeado**."""
    empresa, contas, gestor = _cenario("a2")
    Conta.objects.filter(pk=contas["receita"].pk).update(classificacao_dfc="bancaria")
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    pendencia = dfc["pendencias"]["classificacao_fora_do_enum"]
    assert len(pendencia) == 1, "atividade fora do enum tem de vetar, não estourar"
    assert "4.1" in pendencia[0]["contas"]
    assert "bancaria" in pendencia[0]["contas"], "o valor corrompido tem de aparecer"
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is False


def test_a3_grupo_de_caixa_marcado_nao_conta_a_filha_duas_vezes():
    """**Achado A3 (MÉDIA).** O `saldo` do motor é consolidado (próprio +
    subárvore), então somar um grupo marcado e a filha marcada contava o
    mesmo dinheiro duas vezes — o auditor mediu 200.000 numa empresa com
    100.000.

    A apuração soma **só as contas marcadas mais altas**, e o modelo recusa a
    marcação dupla — são as duas metades da mesma defesa.

    ⚠️ O estado duplo é criado **por ORM direto**, de propósito: pelo caminho
    validado ele é impossível, porque a guarda do modelo recusa. O que este
    teste cobre é a **segunda** metade — a apuração não pode contar o mesmo
    dinheiro duas vezes mesmo com dado corrompido vindo de fora."""
    empresa, contas, gestor = _cenario("a3")
    grupo = _conta(empresa, "1.0", "Tesouraria", ATIVO, D, caixa=True)
    filha = _conta(empresa, "1.0.2", "Aplicação da Tesouraria", ATIVO, D, pai=grupo)
    # Marca a filha por fora da validação: é o caminho que a apuração precisa
    # sobreviver.
    Conta.objects.filter(pk=filha.pk).update(caixa_e_equivalentes=True)
    _lancar(empresa, date(2026, 3, 10), "Venda", filha, contas["receita"], "100000.00")

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    assert dfc["caixa"]["variacao"] == _dec("100000.00"), (
        "o grupo e a filha marcadas não podem contar o mesmo dinheiro duas vezes"
    )
    assert dfc["conciliacao"]["diferenca"] == _dec("0.00")


def test_a3_o_modelo_recusa_grupo_e_filha_marcados():
    empresa, contas, gestor = _cenario("a3-modelo")
    grupo = _conta(empresa, "1.0", "Tesouraria", ATIVO, D, caixa=True)
    filha = _conta(empresa, "1.0.2", "Aplicação", ATIVO, D, pai=grupo)
    filha.caixa_e_equivalentes = True
    with pytest.raises(ValidationError) as erro:
        filha.full_clean()
    assert "duas vezes" in str(erro.value)


def test_a4_o_item_9_preserva_o_vertice_de_emissao():
    """**Achado A4 (MÉDIA).** O teste do item 9 só afirmava as atividades, o
    saldo final e a conciliação — **não** afirmava `pode_emitir` nem que as
    pendências estavam vazias. Desligando o `if not contrapartes`, a
    transferência cairia em `lancamentos_sem_atividade` e os três asserts
    seguiriam verdes. Aqui o teste aperta o que faltava."""
    empresa, contas, gestor = _cenario("a4")
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    _lancar(
        empresa,
        date(2026, 3, 18),
        "Transferência entre contas",
        contas["caixa"],
        contas["banco"],
        "60000.00",
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    # A transferência NÃO pode virar pendência: o item 9 diz que ela não é
    # fluxo, e "não é fluxo" não é "não sei classificar".
    assert dfc["pendencias"]["lancamentos_sem_atividade"] == []
    assert dfc["pendencias"]["lancamento_com_atividades_conflitantes"] == []
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is True


def test_a5_conta_com_os_dois_papeis_veta_nomeando():
    """**Achado A5 (MÉDIA).** A guarda de coerência vive em `Conta.clean()`,
    que é o caminho validado; por ORM direto as duas marcações convivem e o
    lançamento que toca as duas **some da DFC sem veto** — o caixa é o lado do
    fluxo e a atividade é da contrapartida, então nenhum dos dois o registra.
    Cinquenta mil desapareciam com `pode_emitir=True`."""
    empresa, contas, gestor = _cenario("a5")
    Conta.objects.filter(pk=contas["emprestimo"].pk).update(caixa_e_equivalentes=True)
    _lancar(
        empresa, date(2026, 3, 15), "Empréstimo", contas["banco"], contas["emprestimo"], "50000.00"
    )

    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)

    pendencia = dfc["pendencias"]["conta_com_dois_papeis"]
    assert len(pendencia) == 1, (
        "conta com os dois papéis tem de vetar, mesmo vinda de dado corrompido"
    )
    assert pendencia[0]["conta"] == "2.1"
    assert avaliar_emissao_da_dfc(dfc)["pode_emitir"] is False


def test_a6_sem_data_inicio_a_apuracao_e_o_acumulado_do_ano():
    """**Achado A6 (BAIXA).** Sem `data_inicio`, `apurar_dfc` devolve o
    acumulado do ano até o mês — e nenhum teste passava `data_inicio`, então o
    mês isolado não tinha prova nenhuma."""
    empresa, contas, gestor = _cenario("a6")
    _lancar(
        empresa,
        date(2026, 2, 10),
        "Venda de fevereiro",
        contas["banco"],
        contas["receita"],
        "1000.00",
    )
    _lancar(
        empresa, date(2026, 3, 10), "Venda de março", contas["banco"], contas["receita"], "2000.00"
    )

    acumulado = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    so_marco = apurar_dfc(empresa=empresa, ano=ANO, mes=MES, data_inicio=date(2026, 3, 1))

    assert acumulado["atividades"][ATIV] == _dec("3000.00"), "sem data_inicio é o acumulado do ano"
    assert so_marco["atividades"][ATIV] == _dec("2000.00"), "com data_inicio é o mês"


def test_criterio9_a_conciliacao_que_nao_fecha_veta_sem_ajustar_saldo():
    """O auditor verificou por execução que a diferença veta e nomeia, mas
    **não havia teste**. Veto que ninguém exercita é veto que ninguém sabe que
    existe."""
    empresa, contas, gestor = _cenario("c9")
    _lancar(empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00")
    dfc = apurar_dfc(empresa=empresa, ano=ANO, mes=MES)
    # Corrompe a conciliação pelo caminho que só dado adulterado alcança.
    dfc["pendencias"]["diferenca_de_caixa"].append({"diferenca": Decimal("1000.00")})

    emissao = avaliar_emissao_da_dfc(dfc)

    assert emissao["pode_emitir"] is False
    assert "diferenca_de_caixa" in emissao["listas_pendentes"]
    assert dfc["caixa"]["final"] == _dec("100000.00"), "nenhum saldo é ajustado para fechar"


def test_criterio10_isolamento_entre_empresas():
    """O auditor verificou por execução e não houve teste."""
    empresa_a, contas_a, _ = _cenario("iso-a")
    _lancar(
        empresa_a, date(2026, 3, 10), "Venda", contas_a["banco"], contas_a["receita"], "777777.00"
    )

    empresa_b, contas_b, _ = _cenario("iso-b")
    _lancar(empresa_b, date(2026, 3, 10), "Venda", contas_b["banco"], contas_b["receita"], "100.00")

    dfc_a = apurar_dfc(empresa=empresa_a, ano=ANO, mes=MES)
    dfc_b = apurar_dfc(empresa=empresa_b, ano=ANO, mes=MES)

    assert dfc_a["atividades"][ATIV] == _dec("777777.00")
    assert dfc_b["atividades"][ATIV] == _dec("100.00")
    assert dfc_a["caixa"]["final"] != dfc_b["caixa"]["final"]
