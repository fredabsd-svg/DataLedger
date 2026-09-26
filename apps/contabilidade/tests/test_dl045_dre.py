"""DL-045, fatias 1 e 2 — classificação da DRE na conta (RC-118) e a
apuração (`apurar_dre`, RC-119/RC-120, HI-28, HI-29).

Cada teste cita o critério do plano
(`docs/planos/DL-045-demonstracao-do-resultado.md`) que cobre. Dados 100%
sintéticos, criados nos próprios testes. Datas em 2026, sempre no passado
(hoje é 2026-09-26).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.contabilidade.models import (
    ClassificacaoDre,
    Conta,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    PeriodicidadeZeramento,
    apurar_dre,
    criar_lancamento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    if papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel, username):
    usuario = _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")
    return usuario


def _conta(empresa, codigo, nome, tipo, natureza, classificacao_dre=None, conta_pai=None):
    return Conta.objects.create(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_dre=classificacao_dre,
        conta_pai=conta_pai,
    )


def _plano_de_contas_dre(empresa):
    """Plano mínimo para exercitar TODAS as linhas do art. 187 (HI-29):
    receita bruta, deduções (retificadora, natureza DEVEDORA dentro do
    tipo RECEITA), custo, despesas com vendas, despesas G&A, outras
    receitas/despesas, outras despesas operacionais, equivalência
    patrimonial, receitas/despesas financeiras, provisão IRPJ/CSLL,
    participações."""
    return {
        "caixa": _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA),
        "receita_bruta": _conta(
            empresa,
            "3.1",
            "Receita Bruta",
            TipoConta.RECEITA,
            NaturezaConta.CREDORA,
            ClassificacaoDre.RECEITA_BRUTA,
        ),
        "deducoes": _conta(
            empresa,
            "3.2",
            "Deduções da Receita",
            TipoConta.RECEITA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.DEDUCOES_DA_RECEITA,
        ),
        "custo": _conta(
            empresa,
            "4.1",
            "Custo",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.CUSTO,
        ),
        "despesas_vendas": _conta(
            empresa,
            "4.2",
            "Despesas com Vendas",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.DESPESAS_COM_VENDAS,
        ),
        "despesas_adm": _conta(
            empresa,
            "4.3",
            "Despesas Gerais e Administrativas",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS,
        ),
        "outras_receitas": _conta(
            empresa,
            "3.3",
            "Outras Receitas",
            TipoConta.RECEITA,
            NaturezaConta.CREDORA,
            ClassificacaoDre.OUTRAS_RECEITAS,
        ),
        "outras_despesas": _conta(
            empresa,
            "4.4",
            "Outras Despesas",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.OUTRAS_DESPESAS,
        ),
        "outras_despesas_operacionais": _conta(
            empresa,
            "4.5",
            "Outras Despesas Operacionais",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS,
        ),
        "equivalencia": _conta(
            empresa,
            "3.4",
            "Resultado de Equivalência Patrimonial",
            TipoConta.RECEITA,
            NaturezaConta.CREDORA,
            ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL,
        ),
        "receitas_financeiras": _conta(
            empresa,
            "3.5",
            "Receitas Financeiras",
            TipoConta.RECEITA,
            NaturezaConta.CREDORA,
            ClassificacaoDre.RECEITAS_FINANCEIRAS,
        ),
        "despesas_financeiras": _conta(
            empresa,
            "4.6",
            "Despesas Financeiras",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.DESPESAS_FINANCEIRAS,
        ),
        "provisao_irpj_csll": _conta(
            empresa,
            "4.7",
            "Provisão IRPJ/CSLL",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.PROVISAO_IRPJ_CSLL,
        ),
        "participacoes": _conta(
            empresa,
            "4.8",
            "Participações",
            TipoConta.DESPESA,
            NaturezaConta.DEVEDORA,
            ClassificacaoDre.PARTICIPACOES,
        ),
        "resultado": _conta(
            empresa,
            "2.9.1",
            "Resultado do Exercício",
            TipoConta.PATRIMONIO_LIQUIDO,
            NaturezaConta.CREDORA,
        ),
        "lucros": _conta(
            empresa,
            "2.9.2",
            "Lucros Acumulados",
            TipoConta.PATRIMONIO_LIQUIDO,
            NaturezaConta.CREDORA,
        ),
        "prejuizos": _conta(
            empresa,
            "2.9.3",
            "(-) Prejuízos Acumulados",
            TipoConta.PATRIMONIO_LIQUIDO,
            NaturezaConta.DEVEDORA,
        ),
    }


def _nova_empresa(nome, *, sufixo):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=f"1{sufixo:013d}")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=f"2{sufixo:013d}"
    )
    return escritorio, empresa


@pytest.fixture
def cenario():
    escritorio, empresa = _nova_empresa("DL-045", sufixo=1)
    contas = _plano_de_contas_dre(empresa)
    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-dl045")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    return {"escritorio": escritorio, "empresa": empresa, "gestor": gestor, **contas}


def _lancar(empresa, *, data, debito, credito, valor, usuario):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico="Movimento de teste DL-045",
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
        criado_por=usuario,
    )


# ---------------------------------------------------------------------------
# Critério 1 — classificação: só em conta de resultado; recusa com
# mensagem; herança pela hierarquia (mesmo desenho da DL-033, confirmado).
# ---------------------------------------------------------------------------


def test_criterio1a_classificacao_dre_em_conta_patrimonial_e_recusada(cenario):
    """Só conta de RECEITA/DESPESA recebe `classificacao_dre` — conta
    patrimonial (aqui, Ativo) é recusada no MODELO (`full_clean()`)."""
    caixa = cenario["caixa"]
    caixa.classificacao_dre = ClassificacaoDre.RECEITA_BRUTA
    with pytest.raises(ValidationError, match="não é compatível com o"):
        caixa.full_clean()


def test_criterio1b_classificacao_dre_incompativel_com_o_tipo_e_recusada(cenario):
    """Uma linha "tipo DESPESA" (custo) numa conta de RECEITA é recusada —
    guarda granular, não só "resultado em geral" (mesmo nível de
    detalhe da DL-033, que também valida por linha, não só por
    Ativo/Passivo)."""
    conta_receita = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="3.9",
        nome="Receita solta",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    conta_receita.classificacao_dre = ClassificacaoDre.CUSTO
    with pytest.raises(ValidationError, match="não é compatível com o"):
        conta_receita.full_clean()


def test_criterio1c_classificacao_dre_compativel_e_aceita(cenario):
    """Conta de DESPESA com uma linha tipo DESPESA passa limpo."""
    conta_despesa = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="4.9",
        nome="Despesa solta",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_despesa.classificacao_dre = ClassificacaoDre.OUTRAS_DESPESAS
    conta_despesa.full_clean()  # não levanta


def test_criterio1d_reclassificar_conta_com_movimento_e_recusado(cenario):
    """Mudar `classificacao_dre` de uma conta que já tem movimento é
    recusado — mesma guarda de TRANSIÇÃO da `classificacao_patrimonial`
    (DL-033/HI-18): reescreveria uma DRE de período já apurado."""
    empresa = cenario["empresa"]
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="100.00",
        usuario=cenario["gestor"],
    )
    conta = Conta.objects.get(pk=cenario["receita_bruta"].pk)
    conta.classificacao_dre = ClassificacaoDre.OUTRAS_RECEITAS
    with pytest.raises(ValidationError, match="Não é possível mudar a classificação"):
        conta.full_clean()


def test_criterio1e_primeira_classificacao_com_movimento_e_livre(cenario):
    """A PRIMEIRA classificação (gravada `None` -> um valor) é sempre
    livre, mesmo com movimento — é o caminho para classificar o plano de
    contas já em uso (mesma regra da DL-033)."""
    empresa = cenario["empresa"]
    conta_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="3.8",
        nome="Receita ainda não classificada",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=cenario["caixa"],
        credito=conta_sem_classificacao,
        valor="50.00",
        usuario=cenario["gestor"],
    )
    conta_sem_classificacao.classificacao_dre = ClassificacaoDre.OUTRAS_RECEITAS
    conta_sem_classificacao.full_clean()  # não levanta


def test_criterio1f_heranca_pela_hierarquia_consolida_a_subarvore(cenario):
    """Herança pela hierarquia (mesmo desenho da DL-033): classificar o
    nó TOPO (não cada folha) faz a apuração consolidar TODA a subárvore
    — duas folhas SEM classificação própria, sob um pai classificado,
    entram na mesma linha da DRE."""
    empresa = cenario["empresa"]
    receita_bruta_grupo = cenario["receita_bruta"]
    filha_a = _conta(
        empresa,
        "3.1.01",
        "Vendas região A",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=receita_bruta_grupo,
    )
    filha_b = _conta(
        empresa,
        "3.1.02",
        "Vendas região B",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=receita_bruta_grupo,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=filha_a,
        valor="300.00",
        usuario=cenario["gestor"],
    )
    _lancar(
        empresa,
        data=date(2026, 3, 20),
        debito=cenario["caixa"],
        credito=filha_b,
        valor="200.00",
        usuario=cenario["gestor"],
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    linhas = dre["coluna_mes"]["linhas"]
    assert linhas[ClassificacaoDre.RECEITA_BRUTA] == Decimal("500.00")
    # As duas filhas, folhas sem classificação própria mas com ancestral
    # classificado, NÃO aparecem como pendência.
    assert dre["coluna_mes"]["contas_sem_classificacao_dre_com_movimento"] == []


def test_criterio1g_classificacao_aninhada_e_declarada_nunca_somada_em_dobro(cenario):
    """Duas contas da MESMA árvore com classificação PRÓPRIA (pai e
    filha) — dado inconsistente, declarado em `contas_com_classificacao_
    dre_aninhada`, nunca somado duas vezes."""
    empresa = cenario["empresa"]
    pai = cenario["receita_bruta"]
    filha_classificada = _conta(
        empresa,
        "3.1.03",
        "Filha também classificada",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.RECEITA_BRUTA,
        conta_pai=pai,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=filha_classificada,
        valor="400.00",
        usuario=cenario["gestor"],
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    coluna = dre["coluna_mes"]
    # Consolidado no PAI (regra única de saldo) — não duplicado.
    assert coluna["linhas"][ClassificacaoDre.RECEITA_BRUTA] == Decimal("400.00")
    aninhadas = {item["conta"] for item in coluna["contas_com_classificacao_dre_aninhada"]}
    assert filha_classificada.codigo in aninhadas


def test_criterio1h_equivalencia_patrimonial_aceita_conta_de_despesa(cenario):
    """Decisão do arquiteto, 26/09/2026: "resultado de equivalência
    patrimonial" pode ser ganho OU perda — aceita conta de tipo DESPESA
    (a perda de equivalência costuma ficar no grupo de despesas), ao
    lado da conta de tipo RECEITA que já existia (`cenario["equivalencia"]`)."""
    conta_despesa_mep = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="4.9",
        nome="Perda de Equivalência Patrimonial",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_despesa_mep.classificacao_dre = ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL
    conta_despesa_mep.full_clean()  # não levanta


def test_criterio1i_equivalencia_patrimonial_recusa_conta_patrimonial(cenario):
    """A flexibilidade RECEITA/DESPESA da MEP não abre a linha para conta
    PATRIMONIAL — continua só RECEITA ou DESPESA (Lei 6.404/76, art. 187)."""
    caixa = cenario["caixa"]
    caixa.classificacao_dre = ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL
    with pytest.raises(ValidationError, match="não é compatível com o"):
        caixa.full_clean()


def test_criterio1j_ganho_e_perda_de_mep_no_mesmo_periodo_liquido_correto(cenario):
    """Uma conta RECEITA (ganho) e uma conta DESPESA (perda), as DUAS
    classificadas em "resultado de equivalência patrimonial" — o total da
    linha é o LÍQUIDO (ganho − perda), pelo lado natural CREDOR da linha
    (`NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE`), e o resíduo por tipo fecha
    em zero nos dois tipos (RECEITA e DESPESA) — prova de que cada conta
    contribui para o resíduo do seu PRÓPRIO tipo, não de um tipo fixo da
    linha (o achado que motivou `soma_classificada_por_tipo`)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    ganho_mep = cenario["equivalencia"]  # tipo RECEITA, já no plano
    perda_mep = Conta.objects.create(
        empresa=empresa,
        codigo="4.9",
        nome="Perda de Equivalência Patrimonial",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
        classificacao_dre=ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL,
    )
    # Ganho de MEP: crédito na conta de ganho (natureza CREDORA, tipo
    # RECEITA) contra o Caixa.
    _lancar(
        empresa,
        data=date(2026, 3, 5),
        debito=cenario["caixa"],
        credito=ganho_mep,
        valor="900.00",
        usuario=g,
    )
    # Perda de MEP: débito na conta de perda (natureza DEVEDORA, tipo
    # DESPESA) contra o Caixa.
    _lancar(
        empresa,
        data=date(2026, 3, 6),
        debito=perda_mep,
        credito=cenario["caixa"],
        valor="350.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    coluna = dre["coluna_mes"]

    # Líquido: 900,00 (ganho) − 350,00 (perda) = 550,00, no lado CREDOR
    # (natural da linha).
    assert coluna["linhas"][ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL] == Decimal(
        "550.00"
    )
    # Resíduo fecha em zero nos DOIS tipos — cada conta contribuiu para o
    # resíduo do seu PRÓPRIO tipo (RECEITA para o ganho, DESPESA para a
    # perda), não os dois empilhados no tipo "esperado" da linha.
    assert coluna["residuo_por_tipo"][TipoConta.RECEITA] == Decimal("0.00")
    assert coluna["residuo_por_tipo"][TipoConta.DESPESA] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Critério 2 — casos de referência calculados à MÃO.
# ---------------------------------------------------------------------------


def test_criterio2a_lucro_simples(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="10000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["custo"],
        credito=cenario["caixa"],
        valor="3000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_vendas"],
        credito=cenario["caixa"],
        valor="500.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="300.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["receita_liquida"] == Decimal("10000.00")
    assert s["lucro_bruto"] == Decimal("7000.00")
    assert s["resultado_antes_das_receitas_e_despesas_financeiras"] == Decimal("6200.00")
    assert s["resultado_financeiro"] == Decimal("0.00")
    assert s["resultado_antes_dos_tributos_sobre_o_lucro"] == Decimal("6200.00")
    assert s["lucro_liquido"] == Decimal("6200.00")


def test_criterio2b_prejuizo(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="1000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="5000.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["lucro_liquido"] == Decimal("-4000.00")


def test_criterio2c_so_receita(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="800.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["receita_liquida"] == Decimal("800.00")
    assert s["lucro_liquido"] == Decimal("800.00")


def test_criterio2d_deducoes_com_devolucao_retificadora_por_heranca(cenario):
    """Deduções da receita (impostos, direto na conta do grupo) + uma
    devolução lançada numa conta FILHA sem classificação própria (herda
    `DEDUCOES_DA_RECEITA` do pai) — as duas somam na MESMA linha, regra
    única de saldo (DE-020), mesmo padrão de herança do critério 1f."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    devolucoes = _conta(
        empresa,
        "3.2.01",
        "Devoluções de Vendas",
        TipoConta.RECEITA,
        NaturezaConta.DEVEDORA,
        conta_pai=cenario["deducoes"],
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="10000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["deducoes"],
        credito=cenario["caixa"],
        valor="800.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=devolucoes,
        credito=cenario["caixa"],
        valor="200.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    coluna = dre["coluna_mes"]
    assert coluna["linhas"][ClassificacaoDre.DEDUCOES_DA_RECEITA] == Decimal("1000.00")
    assert coluna["subtotais"]["receita_liquida"] == Decimal("9000.00")
    # O resíduo por tipo tem que fechar em zero mesmo com "deduções da
    # receita" guardando a magnitude no lado DEVEDOR enquanto o total do
    # tipo RECEITA é apurado no lado CREDOR — é exatamente a conversão que
    # a correção deste teste expôs (ver NATUREZA_NATURAL_DA_CLASSIFICACAO_
    # DRE, models.py).
    assert coluna["residuo_por_tipo"][TipoConta.RECEITA] == Decimal("0.00")
    assert coluna["residuo_por_tipo"][TipoConta.DESPESA] == Decimal("0.00")


def test_criterio2e_retificadora_de_natureza_oposta_reduz_o_grupo(cenario):
    """RC-61: conta retificadora DENTRO do grupo (natureza OPOSTA à do
    grupo) reduz o total — "Descontos concedidos" (natureza DEVEDORA,
    retificadora) dentro de "Outras Receitas" (CREDORA). Ponto crítico
    de mutação (sinal da retificadora): consolidado bruto (débito=100,
    crédito=1000) tem que aplicar a natureza UMA vez, no fim (900,00),
    nunca somar os dois lados já assinados pela própria natureza de cada
    conta (o que daria 1000 + 100 = 1100,00, o dobro do desconto)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    descontos = _conta(
        empresa,
        "3.3.01",
        "Descontos Concedidos",
        TipoConta.RECEITA,
        NaturezaConta.DEVEDORA,
        conta_pai=cenario["outras_receitas"],
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["outras_receitas"],
        valor="1000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=descontos,
        credito=cenario["caixa"],
        valor="100.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    assert dre["coluna_mes"]["linhas"][ClassificacaoDre.OUTRAS_RECEITAS] == Decimal("900.00")


def test_criterio2f_resultado_financeiro_negativo(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="5000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receitas_financeiras"],
        valor="50.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_financeiras"],
        credito=cenario["caixa"],
        valor="800.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["resultado_financeiro"] == Decimal("-750.00")
    assert s["lucro_liquido"] == Decimal("5000.00") - Decimal("750.00")


def test_criterio2g_com_irpj_csll_e_participacoes(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="20000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["custo"],
        credito=cenario["caixa"],
        valor="5000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["provisao_irpj_csll"],
        credito=cenario["caixa"],
        valor="3000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["participacoes"],
        credito=cenario["caixa"],
        valor="500.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["resultado_antes_dos_tributos_sobre_o_lucro"] == Decimal("15000.00")
    assert s["lucro_liquido"] == Decimal("15000.00") - Decimal("3000.00") - Decimal("500.00")
    assert s["lucro_liquido"] == Decimal("11500.00")


def test_criterio2h_centavos(cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="100.01",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="33.34",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    s = dre["coluna_mes"]["subtotais"]
    assert s["lucro_liquido"] == Decimal("66.67")
    assert isinstance(s["lucro_liquido"], Decimal)


# ---------------------------------------------------------------------------
# Critérios 3, 4 e 5 — DRE de período zerado == antes do zeramento;
# conciliação com o zeramento; acumulado == soma dos meses.
# ---------------------------------------------------------------------------


def test_criterio3_dre_de_mes_zerado_e_igual_a_antes_do_zeramento(cenario):
    """Zerar março (RC-104, DL-043) não pode mudar a DRE de março: o
    lançamento de zeramento é excluído do cálculo (o PROBLEMA que o plano
    desta etapa nomeia). Três zeramentos mensais seguidos (jan, fev, mar)
    — a DRE de cada mês, e o acumulado até março, continuam os mesmos
    antes e depois."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 1, 15),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="1000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 2, 15),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="2000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 2, 15),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="500.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=cenario["custo"],
        credito=cenario["caixa"],
        valor="300.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="3000.00",
        usuario=g,
    )

    dre_marco_antes = apurar_dre(empresa=empresa, ano=2026, mes=3)

    zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=g)
    zerar_resultado(empresa=empresa, ano=2026, mes=2, usuario=g)
    zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=g)

    dre_marco_depois = apurar_dre(empresa=empresa, ano=2026, mes=3)

    assert dre_marco_depois["coluna_mes"]["subtotais"] == dre_marco_antes["coluna_mes"]["subtotais"]
    assert (
        dre_marco_depois["coluna_acumulado"]["subtotais"]
        == dre_marco_antes["coluna_acumulado"]["subtotais"]
    )
    assert dre_marco_depois["coluna_mes"]["linhas"] == dre_marco_antes["coluna_mes"]["linhas"]


def test_criterio4_lucro_liquido_concilia_com_o_zeramento(cenario):
    """O lucro líquido da DRE do mês é EXATAMENTE o valor que a etapa 2
    do zeramento do MESMO período transfere para Lucros (ou Prejuízos,
    se negativo)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="7000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="1500.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    lucro_liquido_dre = dre["coluna_mes"]["subtotais"]["lucro_liquido"]

    resultado_zeramento = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=g)
    item_destino = next(
        item
        for item in resultado_zeramento["lancamento_etapa2"].itens.all()
        if item.conta_id in (cenario["lucros"].id, cenario["prejuizos"].id)
    )
    valor_transferido = item_destino.valor if lucro_liquido_dre >= 0 else -item_destino.valor
    assert resultado_zeramento["destino_etapa2"] == "lucros_acumulados"
    assert valor_transferido == lucro_liquido_dre


def test_criterio4_prejuizo_concilia_com_o_zeramento(cenario):
    """Mesmo critério 4, agora com PREJUÍZO — o valor vai para `(-)
    Prejuízos Acumulados`, e a conciliação usa o sinal correto."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="500.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="2000.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    lucro_liquido_dre = dre["coluna_mes"]["subtotais"]["lucro_liquido"]
    assert lucro_liquido_dre < 0

    resultado_zeramento = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=g)
    assert resultado_zeramento["destino_etapa2"] == "prejuizos_acumulados"
    item_destino = next(
        item
        for item in resultado_zeramento["lancamento_etapa2"].itens.all()
        if item.conta_id == cenario["prejuizos"].id
    )
    assert -item_destino.valor == lucro_liquido_dre


def test_criterio5_acumulado_e_a_soma_dos_meses(cenario):
    """O acumulado do exercício até março = soma das DREs mensais de
    janeiro, fevereiro e março (mesmo plano de contas, sem zeramento no
    meio — a soma "crua" do movimento tem que bater)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 1, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="1000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 2, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="2000.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 2, 10),
        debito=cenario["despesas_adm"],
        credito=cenario["caixa"],
        valor="300.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="1500.00",
        usuario=g,
    )

    lucro_liquido_jan = apurar_dre(empresa=empresa, ano=2026, mes=1)["coluna_mes"]["subtotais"][
        "lucro_liquido"
    ]
    lucro_liquido_fev = apurar_dre(empresa=empresa, ano=2026, mes=2)["coluna_mes"]["subtotais"][
        "lucro_liquido"
    ]
    lucro_liquido_mar = apurar_dre(empresa=empresa, ano=2026, mes=3)["coluna_mes"]["subtotais"][
        "lucro_liquido"
    ]
    acumulado_mar = apurar_dre(empresa=empresa, ano=2026, mes=3)["coluna_acumulado"]["subtotais"][
        "lucro_liquido"
    ]

    assert acumulado_mar == lucro_liquido_jan + lucro_liquido_fev + lucro_liquido_mar


# ---------------------------------------------------------------------------
# API: expõe/aceita `classificacao_dre` no plano de contas (fatia 1),
# endpoint de leitura da DRE (fatia 2) — critérios 6 e 8.
# ---------------------------------------------------------------------------


def _url_contas(empresa_id):
    return reverse("contabilidade:contas", args=[empresa_id])


def _url_dre(empresa_id, ano, mes):
    return reverse("contabilidade:dre", args=[empresa_id, ano, mes])


def test_api_cria_conta_com_classificacao_dre(client, cenario):
    """A API de plano de contas aceita e devolve `classificacao_dre` —
    mesma autorização de hoje (`PodeEscriturar` no POST)."""
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-api-contas")
    resposta = client.post(
        _url_contas(empresa.id),
        data={
            "codigo": "3.9",
            "nome": "Outra receita qualquer",
            "tipo": "receita",
            "natureza": "credora",
            "classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS,
        },
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["classificacao_dre"] == ClassificacaoDre.OUTRAS_RECEITAS


def test_api_recusa_classificacao_dre_incompativel_com_o_tipo(client, cenario):
    """Compatibilidade `classificacao_dre` × `tipo` é validada na API
    (não só no modelo) — DRF não chama `full_clean()` (BL-40/DE-008)."""
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-api-contas2")
    resposta = client.post(
        _url_contas(empresa.id),
        data={
            "codigo": "1.9",
            "nome": "Caixa 2",
            "tipo": "ativo",
            "natureza": "devedora",
            "classificacao_dre": ClassificacaoDre.RECEITA_BRUTA,
        },
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert not Conta.objects.filter(empresa=empresa, codigo="1.9").exists()


def test_criterio6_pendencia_de_classificacao_recusa_a_dre_via_api(client, cenario):
    """Conta de resultado ANALÍTICA com movimento no mês e SEM
    classificação (nem própria nem ancestral) faz a leitura da DRE
    devolver 409, listando a conta pendente — nada "emitido" com dado
    faltando."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    conta_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="3.7",
        nome="Receita esquecida",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=conta_sem_classificacao,
        valor="100.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-criterio6")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    pendentes = corpo["listas_pendentes"]["coluna_mes"][
        "contas_sem_classificacao_dre_com_movimento"
    ]
    assert any(item["conta"] == "3.7" for item in pendentes)


def test_criterio6b_pendencia_so_no_acumulado_tambem_veta_e_indica_a_coluna(client, cenario):
    """Decisão do arquiteto, 26/09/2026: as DUAS colunas vetam, cada uma
    marcada com o nome de onde vem. Conta usada em janeiro (sem
    classificação) não aparece no MÊS de março (sem movimento em março),
    mas aparece no ACUMULADO do exercício até março (que inclui janeiro)
    — e isso já é suficiente para vetar a DRE de março inteira."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    conta_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="3.8",
        nome="Receita de janeiro esquecida",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _lancar(
        empresa,
        data=date(2026, 1, 15),
        debito=cenario["caixa"],
        credito=conta_sem_classificacao,
        valor="300.00",
        usuario=g,
    )
    # Março tem movimento normal, classificado — sem pendência PRÓPRIA do
    # mês de março.
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="500.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-criterio6b")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    assert "coluna_mes" not in corpo["listas_pendentes"], corpo["listas_pendentes"]
    pendentes_acumulado = corpo["listas_pendentes"]["coluna_acumulado"][
        "contas_sem_classificacao_dre_com_movimento"
    ]
    assert any(item["conta"] == "3.8" for item in pendentes_acumulado)


def test_dre_sem_pendencia_e_200(client, cenario):
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="500.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-dre-200")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["pode_emitir"] is True
    assert corpo["coluna_mes"]["subtotais"]["lucro_liquido"] == "500.00"


# ---------------------------------------------------------------------------
# Critério 8 — autorização no servidor; isolamento entre empresas e
# escritórios.
# ---------------------------------------------------------------------------


def test_criterio8a_papel_sem_permissao_recebe_403(client, cenario):
    """CLIENTE não lê a contabilidade (mesma regra de Diário/Razão/
    Balancete) — `PodeLerContabilidade`, nunca uma regra nova."""
    _autenticar(client, cenario["escritorio"], Papel.CLIENTE, "cliente-dl045")
    resposta = client.get(_url_dre(cenario["empresa"].id, 2026, 3))
    assert resposta.status_code == 403


def test_criterio8b_isolamento_entre_empresas_e_404(client, cenario):
    """Empresa de OUTRO escritório: 404, nunca vazamento de dado nem
    autorização emprestada (mesmo padrão de `EmpresaEscopadaContabilMixin`
    já usado pelas outras saídas)."""
    outro_escritorio, _outra_empresa = _nova_empresa("Outro Escritório DL-045", sufixo=99)
    _autenticar(client, outro_escritorio, Papel.ADMINISTRADOR, "outro-adm-dl045")
    resposta = client.get(_url_dre(cenario["empresa"].id, 2026, 3))
    assert resposta.status_code == 404


def test_criterio8c_isolamento_de_dados_entre_empresas(cenario):
    """Movimento de uma empresa nunca aparece na DRE de outra — mesmo
    escritório, empresas diferentes."""
    empresa_a = cenario["empresa"]
    g = cenario["gestor"]
    _, empresa_b = _nova_empresa("DL-045 B", sufixo=2)
    contas_b = _plano_de_contas_dre(empresa_b)
    gestor_b = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "gestor-dl045-b")
    registrar_parametro_contabil(
        empresa=empresa_b,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas_b["resultado"],
        conta_lucros_acumulados=contas_b["lucros"],
        conta_prejuizos_acumulados=contas_b["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor_b,
    )
    _lancar(
        empresa_a,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="999.00",
        usuario=g,
    )
    _lancar(
        empresa_b,
        data=date(2026, 3, 10),
        debito=contas_b["caixa"],
        credito=contas_b["receita_bruta"],
        valor="111.00",
        usuario=gestor_b,
    )

    dre_a = apurar_dre(empresa=empresa_a, ano=2026, mes=3)
    dre_b = apurar_dre(empresa=empresa_b, ano=2026, mes=3)
    assert dre_a["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("999.00")
    assert dre_b["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("111.00")


# ---------------------------------------------------------------------------
# Número de consultas CONSTANTE em relação ao número de contas.
# ---------------------------------------------------------------------------


def test_numero_de_consultas_e_constante_com_o_numero_de_contas(cenario):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    empresa = cenario["empresa"]
    g = cenario["gestor"]

    def _preparar(quantidade, sufixo):
        for indice in range(quantidade):
            conta = _conta(
                empresa,
                f"7.{sufixo}.{indice:04d}",
                f"Receita extra {sufixo} {indice}",
                TipoConta.RECEITA,
                NaturezaConta.CREDORA,
                ClassificacaoDre.OUTRAS_RECEITAS,
            )
            _lancar(
                empresa,
                data=date(2026, 3, 5),
                debito=cenario["caixa"],
                credito=conta,
                valor="1.00",
                usuario=g,
            )

    _preparar(10, "a")
    with CaptureQueriesContext(connection) as capturado_10:
        apurar_dre(empresa=empresa, ano=2026, mes=3)
    numero_de_consultas_10 = len(capturado_10.captured_queries)

    _preparar(40, "b")  # total 50 contas extras
    with CaptureQueriesContext(connection) as capturado_50:
        apurar_dre(empresa=empresa, ano=2026, mes=3)
    numero_de_consultas_50 = len(capturado_50.captured_queries)

    assert numero_de_consultas_10 == numero_de_consultas_50, (
        f"número de consultas cresceu com o número de contas "
        f"({numero_de_consultas_10} -> {numero_de_consultas_50})"
    )


def test_sinal_da_linha_usa_a_natureza_natural_da_linha_nunca_a_da_conta(cenario):
    """Ponto crítico de mutação: o sinal de cada linha topo-classificada
    usa `NATUREZA_NATURAL_DA_CLASSIFICACAO_DRE` (fixo por LINHA), nunca a
    natureza CADASTRADA da conta que a declara — mesma lição do BL-486
    (DL-034): uma conta "Deduções da Receita" cadastrada, por erro de
    digitação, com natureza CREDORA (o convencional é DEVEDORA) ainda
    precisa reduzir a receita líquida, porque é a LINHA que define o lado
    natural, não o cadastro de UMA conta específica."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    deducoes_natureza_atipica = _conta(
        empresa,
        "3.6",
        "Deduções cadastradas com natureza atípica",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,  # atípico: o normal seria DEVEDORA
        ClassificacaoDre.DEDUCOES_DA_RECEITA,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="10000.00",
        usuario=g,
    )
    # Lançamento normal de dedução: débito na conta (reduz receita na
    # prática, INDEPENDENTE de qual natureza está cadastrada nela).
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=deducoes_natureza_atipica,
        credito=cenario["caixa"],
        valor="700.00",
        usuario=g,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    coluna = dre["coluna_mes"]
    assert coluna["linhas"][ClassificacaoDre.DEDUCOES_DA_RECEITA] == Decimal("700.00")
    assert coluna["subtotais"]["receita_liquida"] == Decimal("9300.00")
