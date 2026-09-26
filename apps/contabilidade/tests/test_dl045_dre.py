"""DL-045, fatias 1 e 2 — classificação da DRE na conta (RC-118) e a
apuração (`apurar_dre`, RC-119/RC-120, HI-28, HI-29).

Cada teste cita o critério do plano
(`docs/planos/DL-045-demonstracao-do-resultado.md`) que cobre. Dados 100%
sintéticos, criados nos próprios testes. Datas em 2026, sempre no passado
(hoje é 2026-09-26).
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.urls import reverse

from apps.contabilidade import services as contabilidade_services
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
    classificar_conta_na_dre,
    criar_lancamento,
    estornar_lancamento,
    mensagens_da_validacao_django,
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
    filha), com a MESMA linha — dado redundante no cadastro, mas a DRE
    sai CORRETA (decisão do arquiteto, DE-085/A1: só a linha DIFERENTE
    veta), declarado em `contas_com_classificacao_dre_aninhada_mesma_
    linha`, nunca somado duas vezes."""
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
    aninhadas = {
        item["conta"] for item in coluna["contas_com_classificacao_dre_aninhada_mesma_linha"]
    }
    assert filha_classificada.codigo in aninhadas
    # Não veta — a linha é a MESMA do ancestral.
    assert coluna["contas_com_classificacao_dre_aninhada_linha_diferente"] == []


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


def _url_classificacao_dre(empresa_id, conta_id):
    return reverse("contabilidade:conta-classificacao-dre", args=[empresa_id, conta_id])


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


# ---------------------------------------------------------------------------
# Correção da rodada 1 de auditoria (DE-085) — A1 a A10, mutantes M04 a M30
# do relatório `docs/auditorias/2026-09-26-dl-045-rodada-1.md`. Cada teste
# cita o achado/mutante que cobre.
# ---------------------------------------------------------------------------


def _empresa_referencia_completa():
    """Plano de contas COMPLETO com três níveis (raiz sem classificação ->
    grupo classificado -> folha herdando), replicando o cenário que o
    auditor calculou à mão na rodada 1 (seção 2 do relatório) — os MESMOS
    valores, para o teste 1 da lista proposta cobrir M04 (início do
    exercício), M05/M06 (limite de dia) e M12/M13/M14 (linhas fora do
    lugar nos subtotais) de uma vez, com números JÁ CONFERIDOS pelo
    auditor de forma independente."""
    escritorio, empresa = _nova_empresa("DL-045 Referência Completa", sufixo=90)
    caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)

    raiz_receitas = _conta(empresa, "3", "RECEITAS", TipoConta.RECEITA, NaturezaConta.CREDORA)
    g_receita_bruta = _conta(
        empresa,
        "3.1",
        "Receita Bruta",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.RECEITA_BRUTA,
        conta_pai=raiz_receitas,
    )
    vendas = _conta(
        empresa,
        "3.1.01",
        "Vendas",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=g_receita_bruta,
    )
    servicos = _conta(
        empresa,
        "3.1.02",
        "Serviços",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=g_receita_bruta,
    )
    g_deducoes = _conta(
        empresa,
        "3.2",
        "Deduções",
        TipoConta.RECEITA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DEDUCOES_DA_RECEITA,
        conta_pai=raiz_receitas,
    )
    icms = _conta(
        empresa, "3.2.01", "ICMS", TipoConta.RECEITA, NaturezaConta.DEVEDORA, conta_pai=g_deducoes
    )
    devolucoes = _conta(
        empresa,
        "3.2.02",
        "Devoluções",
        TipoConta.RECEITA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_deducoes,
    )
    g_outras_receitas = _conta(
        empresa,
        "3.3",
        "Outras Receitas",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.OUTRAS_RECEITAS,
        conta_pai=raiz_receitas,
    )
    outras_receitas_folha = _conta(
        empresa,
        "3.3.01",
        "Outras Receitas — folha",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=g_outras_receitas,
    )
    g_mep_ganho = _conta(
        empresa,
        "3.4",
        "MEP (ganho)",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL,
        conta_pai=raiz_receitas,
    )
    mep_ganho_folha = _conta(
        empresa,
        "3.4.01",
        "MEP ganho — folha",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=g_mep_ganho,
    )
    g_receitas_financeiras = _conta(
        empresa,
        "3.5",
        "Receitas Financeiras",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.RECEITAS_FINANCEIRAS,
        conta_pai=raiz_receitas,
    )
    receitas_financeiras_folha = _conta(
        empresa,
        "3.5.01",
        "Receitas Financeiras — folha",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        conta_pai=g_receitas_financeiras,
    )

    raiz_despesas = _conta(empresa, "4", "DESPESAS", TipoConta.DESPESA, NaturezaConta.DEVEDORA)
    g_custo = _conta(
        empresa,
        "4.1",
        "Custo",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.CUSTO,
        conta_pai=raiz_despesas,
    )
    custo_folha = _conta(
        empresa,
        "4.1.01",
        "Custo — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_custo,
    )
    g_vendas = _conta(
        empresa,
        "4.2",
        "Despesas com Vendas",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_COM_VENDAS,
        conta_pai=raiz_despesas,
    )
    despesas_vendas_folha = _conta(
        empresa,
        "4.2.01",
        "Despesas com Vendas — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_vendas,
    )
    g_dga = _conta(
        empresa,
        "4.3",
        "Despesas Gerais e Administrativas",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS,
        conta_pai=raiz_despesas,
    )
    salarios = _conta(
        empresa, "4.3.01", "Salários", TipoConta.DESPESA, NaturezaConta.DEVEDORA, conta_pai=g_dga
    )
    aluguel = _conta(
        empresa, "4.3.02", "Aluguel", TipoConta.DESPESA, NaturezaConta.DEVEDORA, conta_pai=g_dga
    )
    g_outras_despesas_operacionais = _conta(
        empresa,
        "4.4",
        "Outras Despesas Operacionais",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS,
        conta_pai=raiz_despesas,
    )
    outras_despesas_operacionais_folha = _conta(
        empresa,
        "4.4.01",
        "Outras Despesas Operacionais — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_outras_despesas_operacionais,
    )
    g_outras_despesas = _conta(
        empresa,
        "4.5",
        "Outras Despesas",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.OUTRAS_DESPESAS,
        conta_pai=raiz_despesas,
    )
    outras_despesas_folha = _conta(
        empresa,
        "4.5.01",
        "Outras Despesas — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_outras_despesas,
    )
    g_mep_perda = _conta(
        empresa,
        "4.6",
        "MEP (perda)",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL,
        conta_pai=raiz_despesas,
    )
    mep_perda_folha = _conta(
        empresa,
        "4.6.01",
        "MEP perda — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_mep_perda,
    )
    g_despesas_financeiras = _conta(
        empresa,
        "4.7",
        "Despesas Financeiras",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_FINANCEIRAS,
        conta_pai=raiz_despesas,
    )
    juros = _conta(
        empresa,
        "4.7.01",
        "Juros",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_despesas_financeiras,
    )
    descontos_obtidos = _conta(
        empresa,
        "4.7.02",
        "Descontos Obtidos (retificadora)",
        TipoConta.DESPESA,
        NaturezaConta.CREDORA,  # retificadora, dentro do MESMO grupo (RC-61)
        conta_pai=g_despesas_financeiras,
    )
    g_irpj = _conta(
        empresa,
        "4.8",
        "Provisão IRPJ/CSLL",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.PROVISAO_IRPJ_CSLL,
        conta_pai=raiz_despesas,
    )
    irpj_folha = _conta(
        empresa,
        "4.8.01",
        "IRPJ/CSLL — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_irpj,
    )
    g_participacoes = _conta(
        empresa,
        "4.9",
        "Participações",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.PARTICIPACOES,
        conta_pai=raiz_despesas,
    )
    participacoes_folha = _conta(
        empresa,
        "4.9.01",
        "Participações — folha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=g_participacoes,
    )

    resultado = _conta(
        empresa,
        "2.9.1",
        "Resultado do Exercício",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.CREDORA,
    )
    lucros = _conta(
        empresa, "2.9.2", "Lucros Acumulados", TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA
    )
    prejuizos = _conta(
        empresa,
        "2.9.3",
        "(-) Prejuízos Acumulados",
        TipoConta.PATRIMONIO_LIQUIDO,
        NaturezaConta.DEVEDORA,
    )

    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-dl045-ref-completa")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=resultado,
        conta_lucros_acumulados=lucros,
        conta_prejuizos_acumulados=prejuizos,
        vigencia_inicio=date(2025, 1, 1),
        usuario=gestor,
    )

    contas = {
        "caixa": caixa,
        "vendas": vendas,
        "servicos": servicos,
        "icms": icms,
        "devolucoes": devolucoes,
        "outras_receitas_folha": outras_receitas_folha,
        "mep_ganho_folha": mep_ganho_folha,
        "receitas_financeiras_folha": receitas_financeiras_folha,
        "custo_folha": custo_folha,
        "despesas_vendas_folha": despesas_vendas_folha,
        "salarios": salarios,
        "aluguel": aluguel,
        "outras_despesas_operacionais_folha": outras_despesas_operacionais_folha,
        "outras_despesas_folha": outras_despesas_folha,
        "mep_perda_folha": mep_perda_folha,
        "juros": juros,
        "descontos_obtidos": descontos_obtidos,
        "irpj_folha": irpj_folha,
        "participacoes_folha": participacoes_folha,
        "resultado": resultado,
        "lucros": lucros,
        "prejuizos": prejuizos,
    }
    return escritorio, empresa, gestor, contas


def test_caso1_referencia_completa_bate_com_o_calculo_independente_do_auditor():
    """Teste 1 da lista proposta pela auditoria (rodada 1): reproduz o
    cenário que o auditor calculou à MÃO, de forma independente (seção 2
    do relatório) — 13 linhas, 6 subtotais, retificadora de despesa
    financeira, MEP com ganho E perda, movimento no PRIMEIRO e no ÚLTIMO
    dia do mês, e movimento em 31/12 do ano ANTERIOR (fora do exercício).
    Mata M04 (início do exercício), M05/M06 (limite de dia) e M12/M13/M14
    (linhas fora do lugar nos subtotais)."""
    escritorio, empresa, gestor, c = _empresa_referencia_completa()

    # Fora do exercício (2025) — NUNCA deve aparecer em nenhuma coluna de
    # 2026 (mata M04: início do exercício = ano-1 incluiria isto).
    _lancar(
        empresa,
        data=date(2025, 12, 31),
        debito=c["caixa"],
        credito=c["vendas"],
        valor="5000.00",
        usuario=gestor,
    )
    # Fevereiro/2026: +600,00 de lucro líquido isolado (para o acumulado).
    _lancar(
        empresa,
        data=date(2026, 2, 15),
        debito=c["caixa"],
        credito=c["outras_receitas_folha"],
        valor="600.00",
        usuario=gestor,
    )

    # Março/2026 — os valores do relatório do auditor, com movimento no
    # PRIMEIRO dia (mata M06: gte->gt excluiria) e no ÚLTIMO dia (mata
    # M05: lte->lt excluiria).
    _lancar(
        empresa,
        data=date(2026, 3, 1),
        debito=c["caixa"],
        credito=c["vendas"],
        valor="50000.10",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["caixa"],
        credito=c["servicos"],
        valor="12345.67",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["icms"],
        credito=c["caixa"],
        valor="9000.02",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["devolucoes"],
        credito=c["caixa"],
        valor="1234.56",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["custo_folha"],
        credito=c["caixa"],
        valor="20000.33",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["despesas_vendas_folha"],
        credito=c["caixa"],
        valor="1500.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["salarios"],
        credito=c["caixa"],
        valor="8000.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["aluguel"],
        credito=c["caixa"],
        valor="2500.50",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["outras_despesas_operacionais_folha"],
        credito=c["caixa"],
        valor="300.01",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["outras_despesas_folha"],
        credito=c["caixa"],
        valor="199.99",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["caixa"],
        credito=c["outras_receitas_folha"],
        valor="1000.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["caixa"],
        credito=c["mep_ganho_folha"],
        valor="700.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["mep_perda_folha"],
        credito=c["caixa"],
        valor="250.25",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["caixa"],
        credito=c["receitas_financeiras_folha"],
        valor="123.45",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["juros"],
        credito=c["caixa"],
        valor="2000.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 15),
        debito=c["caixa"],
        credito=c["descontos_obtidos"],
        valor="150.00",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=c["irpj_folha"],
        credito=c["caixa"],
        valor="4833.39",
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=c["participacoes_folha"],
        credito=c["caixa"],
        valor="1450.02",
        usuario=gestor,
    )

    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    mes = dre["coluna_mes"]

    assert mes["linhas"][ClassificacaoDre.RECEITA_BRUTA] == Decimal("62345.77")
    assert mes["linhas"][ClassificacaoDre.DEDUCOES_DA_RECEITA] == Decimal("10234.58")
    assert mes["linhas"][ClassificacaoDre.CUSTO] == Decimal("20000.33")
    assert mes["linhas"][ClassificacaoDre.DESPESAS_COM_VENDAS] == Decimal("1500.00")
    assert mes["linhas"][ClassificacaoDre.DESPESAS_GERAIS_E_ADMINISTRATIVAS] == Decimal("10500.50")
    assert mes["linhas"][ClassificacaoDre.OUTRAS_DESPESAS_OPERACIONAIS] == Decimal("300.01")
    assert mes["linhas"][ClassificacaoDre.OUTRAS_DESPESAS] == Decimal("199.99")
    assert mes["linhas"][ClassificacaoDre.OUTRAS_RECEITAS] == Decimal("1000.00")
    assert mes["linhas"][ClassificacaoDre.RESULTADO_EQUIVALENCIA_PATRIMONIAL] == Decimal("449.75")
    assert mes["linhas"][ClassificacaoDre.RECEITAS_FINANCEIRAS] == Decimal("123.45")
    assert mes["linhas"][ClassificacaoDre.DESPESAS_FINANCEIRAS] == Decimal("1850.00")
    assert mes["linhas"][ClassificacaoDre.PROVISAO_IRPJ_CSLL] == Decimal("4833.39")
    assert mes["linhas"][ClassificacaoDre.PARTICIPACOES] == Decimal("1450.02")

    assert mes["subtotais"]["receita_liquida"] == Decimal("52111.19")
    assert mes["subtotais"]["lucro_bruto"] == Decimal("32110.86")
    assert mes["subtotais"]["resultado_antes_das_receitas_e_despesas_financeiras"] == Decimal(
        "21060.11"
    )
    assert mes["subtotais"]["resultado_financeiro"] == Decimal("-1726.55")
    assert mes["subtotais"]["resultado_antes_dos_tributos_sobre_o_lucro"] == Decimal("19333.56")
    assert mes["subtotais"]["lucro_liquido"] == Decimal("13050.15")
    assert mes["residuo_por_tipo"][TipoConta.RECEITA] == Decimal("0.00")
    assert mes["residuo_por_tipo"][TipoConta.DESPESA] == Decimal("0.00")

    dre_janeiro = apurar_dre(empresa=empresa, ano=2026, mes=1)
    dre_fevereiro = apurar_dre(empresa=empresa, ano=2026, mes=2)
    assert dre_janeiro["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("0.00")
    assert dre_fevereiro["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("600.00")
    # Acumulado de março = soma dos três meses (critério 5) — e o
    # movimento de 2025 NUNCA entra (mata M04).
    assert dre["coluna_acumulado"]["subtotais"]["lucro_liquido"] == Decimal("13650.15")

    # Zeramentos em ordem (dez/2025 primeiro — RC-104 exige ordem
    # cronológica): a etapa 2 de março transfere o MESMO lucro líquido.
    zerar_resultado(empresa=empresa, ano=2025, mes=12, usuario=gestor)
    zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    zerar_resultado(empresa=empresa, ano=2026, mes=2, usuario=gestor)
    resultado_marco = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=gestor)
    item_destino = next(
        item
        for item in resultado_marco["lancamento_etapa2"].itens.all()
        if item.conta_id == c["lucros"].id
    )
    assert item_destino.valor == Decimal("13050.15")


def test_caso2_raiz_despesa_sem_classificacao_com_movimento_veta_pelo_residuo(client, cenario):
    """Teste 2 da lista proposta: raiz DESPESA sem classificação, com
    movimento PRÓPRIO (7,00), e uma filha classificada — o resíduo de
    DESPESA fica diferente de zero e veta. Mata M08 (`if residuo or
    pendentes` -> `if pendentes`, que ignoraria o resíduo)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    raiz_despesa_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="4.99",
        nome="Raiz de despesa sem classificação",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    filha_classificada = _conta(
        empresa,
        "4.99.01",
        "Filha classificada",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.OUTRAS_DESPESAS,
        conta_pai=raiz_despesa_sem_classificacao,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=raiz_despesa_sem_classificacao,
        credito=cenario["caixa"],
        valor="7.00",
        usuario=g,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=filha_classificada,
        credito=cenario["caixa"],
        valor="50.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-caso2")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    corpo = resposta.json()
    assert corpo["pode_emitir"] is False
    assert corpo["residuo_pendente"]["coluna_mes"][str(TipoConta.DESPESA)] == "7.00"


def test_caso3_conta_despesa_sem_classificacao_com_movimento_aparece_na_lista(client, cenario):
    """Teste 3 da lista proposta: conta de DESPESA (não só RECEITA) sem
    classificação, com movimento, aparece em `contas_sem_classificacao_
    dre_com_movimento`. Mata M30 (que ignorava DESPESA nessa lista)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    despesa_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="4.98",
        nome="Despesa esquecida",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=despesa_sem_classificacao,
        credito=cenario["caixa"],
        valor="90.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-caso3")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    pendentes = resposta.json()["listas_pendentes"]["coluna_mes"][
        "contas_sem_classificacao_dre_com_movimento"
    ]
    assert any(item["conta"] == "4.98" for item in pendentes)


def test_caso4_datas_invalidas_devolvem_400(client, cenario):
    """Teste 4 da lista proposta: mês 13/0 e ano 1969/3000 devolvem 400;
    ano 1970/2999 (limites válidos) devolvem 200 ou 409, nunca 500. Mata
    M25 (sem `_validar_ano_mes`, mês 13 viraria 500 por `calendar.
    monthrange`)."""
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-caso4")

    for ano, mes in ((2026, 13), (2026, 0), (1969, 3), (3000, 3)):
        resposta = client.get(_url_dre(empresa.id, ano, mes))
        assert resposta.status_code == 400, (ano, mes, resposta.status_code, resposta.content)

    for ano, mes in ((1970, 1), (2999, 12)):
        resposta = client.get(_url_dre(empresa.id, ano, mes))
        assert resposta.status_code in (200, 409), (ano, mes, resposta.status_code)


def test_caso5_ciclo_na_hierarquia_devolve_409_nunca_500(client, cenario):
    """Teste 5 da lista proposta: ciclo criado por `QuerySet.update`
    (contorna `Conta.clean()`) faz a leitura da DRE devolver 409 com
    `detail`, nunca um 500 mudo. Mata M28 (`HierarquiaInconsistente` não
    tratada na view)."""
    empresa = cenario["empresa"]
    a1 = Conta.objects.create(
        empresa=empresa,
        codigo="9.1",
        nome="A1",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    a2 = Conta.objects.create(
        empresa=empresa,
        codigo="9.2",
        nome="A2",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=a1,
    )
    Conta.objects.filter(pk=a1.id).update(conta_pai=a2.id)  # ciclo A1 <-> A2
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-caso5")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    assert "detail" in resposta.json()


def test_caso6_isolamento_dos_totais_entre_empresas(cenario):
    """Teste 6 da lista proposta: `total_debitos`/`total_creditos` de UMA
    empresa nunca incluem movimento de outra. Mata M27 (agregação sem
    filtro de empresa). Um lançamento de RECEITA (credita `total_
    creditos`) e um de DESPESA (credita `total_debitos`) — os dois lados
    da conta patrimonial (Caixa) nunca entram nesta soma (A10: só RECEITA/
    DESPESA), então cada lançamento simples só alimenta UM dos dois
    totais; somando os dois tipos os dois totais ficam iguais e
    comparáveis com o valor de B, que teria que ser MUITO maior se
    vazasse."""
    empresa_a = cenario["empresa"]
    g = cenario["gestor"]
    _lancar(
        empresa_a,
        data=date(2026, 3, 10),
        debito=cenario["custo"],
        credito=cenario["caixa"],
        valor="10.00",
        usuario=g,
    )
    _lancar(
        empresa_a,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="10.00",
        usuario=g,
    )

    _outro_escritorio, empresa_b = _nova_empresa("DL-045 Outra Empresa Caso6", sufixo=91)
    contas_b = _plano_de_contas_dre(empresa_b)
    _lancar(
        empresa_b,
        data=date(2026, 3, 10),
        debito=contas_b["custo"],
        credito=contas_b["caixa"],
        valor="999.00",
        usuario=g,
    )
    _lancar(
        empresa_b,
        data=date(2026, 3, 10),
        debito=contas_b["caixa"],
        credito=contas_b["receita_bruta"],
        valor="999.00",
        usuario=g,
    )

    dre_a = apurar_dre(empresa=empresa_a, ano=2026, mes=3)
    assert dre_a["coluna_mes"]["total_debitos"] == Decimal("10.00")
    assert dre_a["coluna_mes"]["total_creditos"] == Decimal("10.00")


def test_a1_aninhada_com_linha_diferente_da_herdada_veta(client, cenario):
    """A1 (auditoria DL-045, rodada 1): filha classificada com linha
    DIFERENTE da do ancestral (grupo em CUSTO, filha em DESPESAS_COM_
    VENDAS) põe o valor na linha ERRADA — 409, nunca 200 (medido pelo
    auditor: DRE saía com "custo 500,00 / despesas com vendas 0", sem
    nenhuma recusa)."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    grupo_custo = cenario["custo"]
    filha_vendas = _conta(
        empresa,
        "4.1.01",
        "Filha em outra linha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_COM_VENDAS,
        conta_pai=grupo_custo,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=filha_vendas,
        credito=cenario["caixa"],
        valor="500.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a1")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    pendentes = resposta.json()["listas_pendentes"]["coluna_mes"][
        "contas_com_classificacao_dre_aninhada_linha_diferente"
    ]
    assert any(item["conta"] == "4.1.01" for item in pendentes)


def test_a2a_conta_ativo_sob_receita_bruta_veta(client, cenario):
    """A2 (auditoria DL-045, rodada 1) — cenário (a): conta ATIVO
    pendurada sob "receita bruta" (evento puramente patrimonial) entra
    silenciosamente como receita, sem esta correção. Medido pelo
    auditor: DRE 700,00 contra zeramento de 1.000,00 para uma
    transferência patrimonial de 300,00."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    conta_ativo_sob_receita = _conta(
        empresa,
        "3.1.99",
        "Transferência patrimonial",
        TipoConta.ATIVO,
        NaturezaConta.DEVEDORA,
        conta_pai=cenario["receita_bruta"],
    )
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
        debito=conta_ativo_sob_receita,
        credito=cenario["caixa"],
        valor="300.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a2a")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    pendentes = resposta.json()["listas_pendentes"]["coluna_mes"][
        "contas_com_tipo_divergente_da_linha"
    ]
    assert any(item["conta"] == "3.1.99" for item in pendentes)

    # Prova adicional (critério 4): quando a DRE devolve 200 (sem esta
    # conta), ela concilia com o zeramento; este cenário deliberadamente
    # NÃO concilia, e é exatamente por isso que tem que vetar.
    zeramento = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=g)
    item_destino = next(
        item
        for item in zeramento["lancamento_etapa2"].itens.all()
        if item.conta_id == cenario["lucros"].id
    )
    assert item_destino.valor == Decimal("1000.00")  # zeramento não sabe da divergência


def test_a2b_conta_despesa_sob_receita_bruta_veta(client, cenario):
    """A2, cenário (b): conta de DESPESA pendurada sob "receita bruta" —
    tipo errado dentro do tipo certo (RECEITA), nunca declarado antes
    desta correção."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    despesa_sob_receita = _conta(
        empresa,
        "3.1.90",
        "ICMS s/ vendas (no lugar errado)",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=cenario["receita_bruta"],
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=despesa_sob_receita,
        credito=cenario["caixa"],
        valor="180.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a2b")

    resposta = client.get(_url_dre(empresa.id, 2026, 3))

    assert resposta.status_code == 409, resposta.content
    pendentes = resposta.json()["listas_pendentes"]["coluna_mes"][
        "contas_com_tipo_divergente_da_linha"
    ]
    assert any(item["conta"] == "3.1.90" for item in pendentes)


def test_a3_estorno_de_zeramento_nao_dobra_o_acumulado(cenario):
    """A3 (auditoria DL-045, rodada 1): receita de 1.000,00 em janeiro,
    zerada; o ESTORNO das duas etapas do zeramento de janeiro acontece em
    fevereiro; mais 200,00 de receita legítima em fevereiro. Sem a
    correção, o acumulado de fevereiro contava a receita de janeiro DUAS
    vezes (1.200,00 esperado, 2.200,00 medido pelo auditor). Com a
    correção, o acumulado de fevereiro é 1.200,00 — igual à variação real
    do PL — e a lista informativa `estornos_de_zeramento_na_coluna`
    explica a divergência do MÊS do estorno."""
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
    zeramento_janeiro = zerar_resultado(empresa=empresa, ano=2026, mes=1, usuario=g)

    # Estorna as DUAS etapas do zeramento de janeiro, em fevereiro — a
    # PE-69 ("desfazer zeramento") ainda não existe como operação
    # própria; isto é o caminho AVANÇADO que a auditoria exercitou.
    for lancamento_zeramento in filter(
        None,
        [zeramento_janeiro.get("lancamento_etapa2")]
        + list(zeramento_janeiro.get("lancamentos_etapa1") or []),
    ):
        estornar_lancamento(lancamento_zeramento, data=date(2026, 2, 10))

    _lancar(
        empresa,
        data=date(2026, 2, 20),
        debito=cenario["caixa"],
        credito=cenario["receita_bruta"],
        valor="200.00",
        usuario=g,
    )

    dre_fevereiro = apurar_dre(empresa=empresa, ano=2026, mes=2)
    assert dre_fevereiro["coluna_acumulado"]["subtotais"]["lucro_liquido"] == Decimal("1200.00")
    assert dre_fevereiro["coluna_mes"]["estornos_de_zeramento_na_coluna"] != []
    for item in dre_fevereiro["coluna_mes"]["estornos_de_zeramento_na_coluna"]:
        assert item["data"] == date(2026, 2, 10)


def test_a4_post_com_string_vazia_grava_none_e_libera_a_primeira_classificacao(client, cenario):
    """A4 (auditoria DL-045, rodada 1): `POST` com `"classificacao_dre":
    ""` grava `None` (nunca `""`), e a PRIMEIRA classificação de verdade
    (depois do `""`) é aceita — antes da correção, `""` travava a conta
    para sempre (a guarda tratava `""` como "já classificada")."""
    empresa = cenario["empresa"]
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a4")

    resposta = client.post(
        _url_contas(empresa.id),
        data={
            "codigo": "3.90",
            "nome": "Conta com branco",
            "tipo": "receita",
            "natureza": "credora",
            "classificacao_dre": "",
        },
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    conta_id = resposta.json()["id"]
    conta = Conta.objects.get(pk=conta_id)
    assert conta.classificacao_dre is None

    # Movimento e depois a PRIMEIRA classificação de verdade — livre,
    # mesmo com movimento (mesma guarda de sempre; "" nunca existiu).
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=cenario["caixa"],
        credito=conta,
        valor="10.00",
        usuario=cenario["gestor"],
    )
    conta.classificacao_dre = ClassificacaoDre.OUTRAS_RECEITAS
    conta.full_clean()  # não levanta


def test_a4_check_constraint_recusa_string_vazia_por_sql_direto():
    """A4, defesa de BANCO: a `CheckConstraint` recusa `""` gravado
    IGNORANDO o ORM por completo (INSERT via cursor), o caminho que nem
    `clean()` nem `save()` alcançam. `savepoint`/`savepoint_rollback`
    explícitos (mesmo padrão de `test_dl016_f6_check_empresa_not_null.py`)
    porque o PostgreSQL aborta a transação inteira depois de um
    `IntegrityError` — sem o savepoint, o rollback do PRÓPRIO teste (que o
    `pytest.mark.django_db` faz no final) seria a única saída, mas
    qualquer consulta ORM ENTRE o erro e o fim do teste quebraria."""
    from django.db import IntegrityError
    from django.db import transaction as transacao

    escritorio, empresa = _nova_empresa("DL-045 Constraint A4", sufixo=92)
    with pytest.raises(IntegrityError):
        with transacao.atomic():
            sid = transacao.savepoint()
            try:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO contabilidade_conta "
                        "(empresa_id, codigo, nome, tipo, natureza, classificacao_dre, "
                        "aceita_lancamento, ativo, criado_em) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
                        [
                            empresa.id,
                            "3.92",
                            "Via SQL direto",
                            "receita",
                            "credora",
                            "",
                            True,
                            True,
                        ],
                    )
                transacao.savepoint_commit(sid)
            except IntegrityError:
                transacao.savepoint_rollback(sid)
                raise
    assert not Conta.objects.filter(empresa=empresa, codigo="3.92").exists()


# ---------------------------------------------------------------------------
# A5 — leitura sob snapshot (DE-067). Mesmo par de testes de corrida do
# Balanço (`test_dl034_..._snapshot...`), adaptado: o crédito concorrente
# em "receita bruta" (conta JÁ conhecida antes da pausa) aparece na
# leitura, mas o débito correspondente, numa conta NOVA sem classificação
# (fora da hierarquia carregada), não — produzindo um lucro líquido
# "limpo" (resíduo zero, sem pendência) que NUNCA existiu de verdade: nem
# antes nem depois da escrita concorrente. Isto é MAIS grave que uma
# diferença visível, porque não acende luz nenhuma sozinho.
# ---------------------------------------------------------------------------


def _apurar_dre_sem_snapshot(*, empresa, ano, mes):
    """Réplica MÍNIMA do corpo de `apurar_dre`, SEM o wrapper de
    snapshot — chama `_construir_hierarquia`/`_apurar_coluna_dre` direto,
    o mesmo desenho de `apurar_saldos` (sem wrapper) vs.
    `apurar_balanco_patrimonial` (com wrapper) no Balanço. Usada só para
    o teste "ANTES" desta correção — `apurar_dre` (a função pública) JÁ
    inclui o wrapper, então chamá-la sempre testaria a versão protegida."""
    import calendar

    data_inicio_mes = date(ano, mes, 1)
    data_fim_mes = date(ano, mes, calendar.monthrange(ano, mes)[1])
    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    contas_por_id, filhos_de, _nivel_de = contabilidade_services._construir_hierarquia(contas)
    coluna_mes = contabilidade_services._apurar_coluna_dre(
        empresa=empresa,
        inicio=data_inicio_mes,
        fim=data_fim_mes,
        contas=contas,
        filhos_de=filhos_de,
        contas_por_id=contas_por_id,
    )
    return {"coluna_mes": coluna_mes}


def _empresa_corrida_dre():
    escritorio, empresa = _nova_empresa("DL-045 Corrida A5", sufixo=93)
    caixa = _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, NaturezaConta.DEVEDORA)
    receita_bruta = _conta(
        empresa,
        "3.1",
        "Receita Bruta",
        TipoConta.RECEITA,
        NaturezaConta.CREDORA,
        ClassificacaoDre.RECEITA_BRUTA,
    )
    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-corrida-a5")
    _lancar(
        empresa,
        data=date(2026, 3, 5),
        debito=caixa,
        credito=receita_bruta,
        valor="1000.00",
        usuario=gestor,
    )
    return empresa, caixa, receita_bruta, gestor


@pytest.mark.django_db(transaction=True)
def test_a5_sem_o_wrapper_a_escrita_concorrente_produz_lucro_fantasma(monkeypatch):
    """**ANTES** (a vulnerabilidade é real, medida pelo auditor — não
    presumida): um crédito concorrente em "receita bruta" (conta JÁ
    carregada antes da pausa) aparece na consulta de agregação (que roda
    DEPOIS da pausa, sob READ COMMITTED), mas o débito da MESMA partida,
    lançado contra uma conta NOVA e sem classificação (fora da
    hierarquia já carregada), fica invisível — a leitura racy produz um
    lucro líquido MAIOR do que qualquer leitura real (antes OU depois da
    escrita concorrente) mostraria, com resíduo zero e sem pendência
    (parece limpo — é o que torna isto mais grave que uma diferença
    visível)."""
    empresa, caixa, receita_bruta, gestor = _empresa_corrida_dre()

    liberar_escrita = threading.Event()
    escrita_commitou = threading.Event()
    original = contabilidade_services._construir_hierarquia

    def pausa_apos_carregar_contas(contas):
        resultado = original(contas)
        liberar_escrita.set()
        assert escrita_commitou.wait(timeout=5), "a escrita concorrente não commitou a tempo"
        return resultado

    monkeypatch.setattr(contabilidade_services, "_construir_hierarquia", pausa_apos_carregar_contas)

    resultado = {}

    def ler():
        resultado["dre"] = _apurar_dre_sem_snapshot(empresa=empresa, ano=2026, mes=3)
        connection.close()

    def escrever():
        assert liberar_escrita.wait(timeout=5), "a leitura não chegou à pausa a tempo"
        conta_nova_sem_classificacao = Conta.objects.create(
            empresa=empresa,
            codigo="4.9",
            nome="Despesa Nova Concorrente",
            tipo=TipoConta.DESPESA,
            natureza=NaturezaConta.DEVEDORA,
        )
        criar_lancamento(
            empresa=empresa,
            data=date(2026, 3, 15),
            historico="Escrita concorrente",
            itens=[
                {
                    "conta": conta_nova_sem_classificacao,
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("500.00"),
                },
                {"conta": receita_bruta, "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
            ],
        )
        escrita_commitou.set()
        connection.close()

    t1 = threading.Thread(target=ler)
    t2 = threading.Thread(target=escrever)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()

    dre_racy = resultado["dre"]
    # Fantasma: recebeu o crédito (receita_bruta já conhecida) sem o
    # débito correspondente (conta nova, fora da hierarquia carregada) —
    # lucro 1.500,00 (1.000,00 originais + 500,00 fantasma), resíduo
    # zero, SEM pendência — não existiu nunca, nem antes nem depois.
    assert dre_racy["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("1500.00")
    assert dre_racy["coluna_mes"]["residuo_por_tipo"][TipoConta.RECEITA] == Decimal("0.00")
    assert dre_racy["coluna_mes"]["contas_sem_classificacao_dre_com_movimento"] == []

    # Releitura LIMPA (sem corrida): mostra a pendência de verdade — a
    # despesa nova, sem classificação, com movimento — e VETA.
    connection.close()
    dre_depois = apurar_dre(empresa=empresa, ano=2026, mes=3)
    pendentes_depois = dre_depois["coluna_mes"]["contas_sem_classificacao_dre_com_movimento"]
    assert any(item["conta"] == "4.9" for item in pendentes_depois)


@pytest.mark.django_db(transaction=True)
def test_a5_com_o_wrapper_o_snapshot_protege_do_lucro_fantasma(monkeypatch):
    """**DEPOIS** (DE-067 paga a dívida): a MESMA corrida, agora através
    de `apurar_dre` com o `SET TRANSACTION ISOLATION LEVEL REPEATABLE
    READ` — a consulta de agregação enxerga o MESMO snapshot da consulta
    que listou as contas (tirado ANTES da escrita concorrente commitar):
    nem o crédito novo em "receita bruta" nem a conta nova aparecem
    nesta leitura, e o lucro líquido continua o valor ORIGINAL (1.000,00,
    nunca 1.500,00)."""
    empresa, caixa, receita_bruta, gestor = _empresa_corrida_dre()

    liberar_escrita = threading.Event()
    escrita_commitou = threading.Event()
    original = contabilidade_services._construir_hierarquia

    def pausa_apos_carregar_contas(contas):
        resultado = original(contas)
        liberar_escrita.set()
        assert escrita_commitou.wait(timeout=5), "a escrita concorrente não commitou a tempo"
        return resultado

    monkeypatch.setattr(contabilidade_services, "_construir_hierarquia", pausa_apos_carregar_contas)

    resultado = {}

    def ler():
        resultado["dre"] = apurar_dre(empresa=empresa, ano=2026, mes=3)
        connection.close()

    def escrever():
        assert liberar_escrita.wait(timeout=5), "a leitura não chegou à pausa a tempo"
        conta_nova_sem_classificacao = Conta.objects.create(
            empresa=empresa,
            codigo="4.9",
            nome="Despesa Nova Concorrente",
            tipo=TipoConta.DESPESA,
            natureza=NaturezaConta.DEVEDORA,
        )
        criar_lancamento(
            empresa=empresa,
            data=date(2026, 3, 15),
            historico="Escrita concorrente",
            itens=[
                {
                    "conta": conta_nova_sem_classificacao,
                    "tipo": TipoPartida.DEBITO,
                    "valor": Decimal("500.00"),
                },
                {"conta": receita_bruta, "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
            ],
        )
        escrita_commitou.set()
        connection.close()

    t1 = threading.Thread(target=ler)
    t2 = threading.Thread(target=escrever)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()

    dre_com_snapshot = resultado["dre"]
    assert dre_com_snapshot["coluna_mes"]["subtotais"]["lucro_liquido"] == Decimal("1000.00")


# ---------------------------------------------------------------------------
# A6 — a guarda de transição não pode ser contornada por (a) classificar
# o PAI de uma descendente já classificada com movimento, nem por (b)
# reparentar uma conta para outra linha da DRE.
# ---------------------------------------------------------------------------


def test_a6a_primeira_classificacao_do_pai_sobre_filha_ja_classificada_e_recusada(cenario):
    """A6, cenário (a): grupo SEM classificação, filha JÁ classificada
    (DESPESAS_COM_VENDAS) com movimento. Classificar o PAI agora (CUSTO,
    por exemplo) "engoliria" a filha na consolidação do pai — a DRE de um
    período já apurado mudaria retroativamente. Medido pelo auditor: "custo
    400,00 / despesas com vendas 0" virava "custo 0 / despesas com vendas
    400,00", sem recusa nenhuma."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    grupo_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="4.97",
        nome="Grupo sem classificação",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    filha_classificada = _conta(
        empresa,
        "4.97.01",
        "Filha já classificada",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_COM_VENDAS,
        conta_pai=grupo_sem_classificacao,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=filha_classificada,
        credito=cenario["caixa"],
        valor="400.00",
        usuario=g,
    )

    grupo_sem_classificacao.classificacao_dre = ClassificacaoDre.CUSTO
    with pytest.raises(ValidationError, match="descendente já classificada"):
        grupo_sem_classificacao.full_clean()


def test_a6a_primeira_classificacao_do_pai_e_livre_quando_a_filha_nao_tem_movimento(cenario):
    """Contraprova do A6a: a mesma classificação do pai é ACEITA quando a
    filha classificada NÃO tem movimento — a guarda protege o que já foi
    apurado, não o cadastro em si."""
    empresa = cenario["empresa"]
    grupo_sem_classificacao = Conta.objects.create(
        empresa=empresa,
        codigo="4.96",
        nome="Grupo sem classificação",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    _conta(
        empresa,
        "4.96.01",
        "Filha classificada, sem movimento",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.DESPESAS_COM_VENDAS,
        conta_pai=grupo_sem_classificacao,
    )

    grupo_sem_classificacao.classificacao_dre = ClassificacaoDre.CUSTO
    grupo_sem_classificacao.full_clean()  # não levanta


def test_a6b_reparentamento_que_muda_a_linha_efetiva_com_movimento_e_recusado(cenario):
    """A6, cenário (b): conta SEM classificação própria (herda do pai),
    com movimento, reparentada para um grupo de OUTRA linha da DRE, MESMA
    natureza (a guarda de natureza, sozinha, não dispara) — recusado.
    Medido pelo auditor: conta com 250,00 sob "custo" mudava para
    "despesas com vendas" sem nenhum lançamento novo."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    grupo_custo = cenario["custo"]
    grupo_despesas_vendas = cenario["despesas_vendas"]
    filha_sem_classificacao_propria = _conta(
        empresa,
        "4.1.05",
        "Filha sem classificação própria",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=grupo_custo,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=filha_sem_classificacao_propria,
        credito=cenario["caixa"],
        valor="250.00",
        usuario=g,
    )

    filha_sem_classificacao_propria.conta_pai = grupo_despesas_vendas
    with pytest.raises(ValidationError, match="linha da DRE herdada mudaria"):
        filha_sem_classificacao_propria.full_clean()


def test_a6b_reparentamento_e_livre_quando_a_linha_efetiva_nao_muda(cenario):
    """Contraprova do A6b: reparentar para outra conta da MESMA linha
    (ou para uma conta sem classificação, cujo ancestral mais próximo
    ainda resolve para a MESMA linha) não muda nada de fato — livre."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    grupo_custo = cenario["custo"]
    outro_grupo_custo = _conta(
        empresa,
        "4.1.99",
        "Outro subgrupo, mesma linha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        ClassificacaoDre.CUSTO,
        conta_pai=grupo_custo,
    )
    filha = _conta(
        empresa,
        "4.1.06",
        "Filha",
        TipoConta.DESPESA,
        NaturezaConta.DEVEDORA,
        conta_pai=grupo_custo,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=filha,
        credito=cenario["caixa"],
        valor="10.00",
        usuario=g,
    )

    filha.conta_pai = outro_grupo_custo
    filha.full_clean()  # não levanta — a linha efetiva continua CUSTO


# ---------------------------------------------------------------------------
# A7 — o serviço `classificar_conta_na_dre` e a porta PATCH.
# ---------------------------------------------------------------------------


def test_a7_servico_classifica_conta_existente_e_grava_trilha(cenario):
    """O serviço classifica uma conta EXISTENTE (sem passar pelo admin) e
    grava um registro de auditoria com o valor de antes e de depois."""
    from apps.auditoria.models import RegistroAuditoria

    empresa = cenario["empresa"]
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="3.95",
        nome="Conta a classificar",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )

    classificar_conta_na_dre(
        conta=conta,
        classificacao=ClassificacaoDre.OUTRAS_RECEITAS,
        usuario=cenario["gestor"],
    )

    conta.refresh_from_db()
    assert conta.classificacao_dre == ClassificacaoDre.OUTRAS_RECEITAS
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dre_alterada", objeto_id=str(conta.pk)
    ).latest("id")
    assert registro.detalhes["classificacao_dre_antes"] is None
    assert registro.detalhes["classificacao_dre_depois"] == ClassificacaoDre.OUTRAS_RECEITAS


def test_a7_servico_propaga_a_guarda_de_tipo_incompativel(cenario):
    """O serviço NÃO duplica as guardas: uma classificação incompatível
    com o tipo levanta `django.core.exceptions.ValidationError`, a MESMA
    guarda de `Conta.clean()`."""
    empresa = cenario["empresa"]
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="3.94",
        nome="Conta de receita",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    with pytest.raises(ValidationError, match="não é compatível com o"):
        classificar_conta_na_dre(
            conta=conta, classificacao=ClassificacaoDre.CUSTO, usuario=cenario["gestor"]
        )


def test_a7_mensagens_da_validacao_django_extrai_lista_plana():
    """Helper que a view usa para traduzir `ValidationError` do Django —
    tanto o formato "string única" (o que `Conta.clean()` sempre usa
    hoje) quanto o formato "por campo" (`message_dict`, que `full_clean()`
    também pode produzir via `clean_fields()`)."""
    erro_simples = ValidationError("mensagem única")
    assert mensagens_da_validacao_django(erro_simples) == ["mensagem única"]

    erro_por_campo = ValidationError({"classificacao_dre": ["campo obrigatório"]})
    assert mensagens_da_validacao_django(erro_por_campo) == ["campo obrigatório"]


def test_a7_patch_classifica_conta_existente_via_api(client, cenario):
    """A porta PATCH (`ContaClassificacaoDreView`) usa o MESMO papel de
    quem escritura (`PodeEscriturar`) e devolve a conta serializada."""
    empresa = cenario["empresa"]
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="3.93",
        nome="Conta via PATCH",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a7-patch")

    resposta = client.patch(
        _url_classificacao_dre(empresa.id, conta.id),
        data={"classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["classificacao_dre"] == ClassificacaoDre.OUTRAS_RECEITAS
    conta.refresh_from_db()
    assert conta.classificacao_dre == ClassificacaoDre.OUTRAS_RECEITAS


def test_a7_patch_recusa_para_papel_que_nao_escritura(client, cenario):
    """`PodeEscriturar` é o MESMO papel que grava lançamento — CLIENTE
    (que nem lê a contabilidade) é recusado."""
    empresa = cenario["empresa"]
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="3.89",
        nome="Conta",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _autenticar(client, cenario["escritorio"], Papel.CLIENTE, "cliente-a7-patch")

    resposta = client.patch(
        _url_classificacao_dre(empresa.id, conta.id),
        data={"classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS},
        content_type="application/json",
    )

    assert resposta.status_code == 403


def test_a7_patch_traduz_a_guarda_de_movimento_para_400(client, cenario):
    """Reclassificar (não a primeira vez) uma conta com movimento é
    recusado pela MESMA guarda de `Conta.clean()`, traduzida para 400."""
    empresa = cenario["empresa"]
    g = cenario["gestor"]
    conta = cenario["custo"]  # já classificada (CUSTO), no plano do cenário
    _lancar(
        empresa,
        data=date(2026, 3, 10),
        debito=conta,
        credito=cenario["caixa"],
        valor="10.00",
        usuario=g,
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a7-patch-400")

    resposta = client.patch(
        _url_classificacao_dre(empresa.id, conta.id),
        data={"classificacao_dre": ClassificacaoDre.DESPESAS_COM_VENDAS},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert "movimento do exercício" in " ".join(resposta.json()["classificacao_dre"]).lower()


def test_a7_patch_isolamento_conta_de_outro_escritorio_e_404(client, cenario):
    """`ContaClassificacaoDreView` usa a MESMA `EmpresaEscopadaContabilMixin`
    — conta de outra empresa/escritório é 404, nunca vazamento."""
    _outro_escritorio, outra_empresa = _nova_empresa("DL-045 Outra A7", sufixo=94)
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-a7-isolamento")

    resposta = client.patch(
        _url_classificacao_dre(cenario["empresa"].id, 999999),
        data={"classificacao_dre": ClassificacaoDre.OUTRAS_RECEITAS},
        content_type="application/json",
    )
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# M21 — deduções da receita só aceita conta de tipo RECEITA. Era decisão
# provisória (D3 do relatório de auditoria) — CONFIRMADA como RC-123
# (docs/projeto/requisitos.md), por delegação do Fred ao arquiteto-senior
# e conferência nos manuais e normas (ITG 1000, art. 187, I).
# ---------------------------------------------------------------------------


def test_m21_deducoes_da_receita_recusa_conta_de_tipo_despesa(cenario):
    conta_deducao_tipo_errado = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="4.95",
        nome="Dedução cadastrada com tipo errado",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_deducao_tipo_errado.classificacao_dre = ClassificacaoDre.DEDUCOES_DA_RECEITA
    with pytest.raises(ValidationError, match="não é compatível com o"):
        conta_deducao_tipo_errado.full_clean()


# ---------------------------------------------------------------------------
# A1 (DE-085, item 2) — a partição das listas `contas_*` que vetam e que
# só avisam, no MOLDE de `test_bl502_as_duas_tuplas_particionam_o_
# inventario_real_de_apurar_saldos` (Balanço, DL-034). Prova que a
# entrega original AFIRMAVA (no plano) ser esta mesma partição sem
# realmente ser — a auditoria mediu.
# ---------------------------------------------------------------------------


def test_particao_das_listas_contas_da_dre_e_igual_ao_inventario_real(cenario):
    """As DUAS tuplas — `_LISTAS_DA_DRE_QUE_IMPEDEM_A_EMISSAO` e
    `_LISTAS_DA_DRE_QUE_SO_AVISAM` — têm que formar uma PARTIÇÃO exata
    das chaves `contas_*` que `_apurar_coluna_dre` de fato devolve: toda
    lista pertence a UMA das duas, nunca a nenhuma, nunca às duas.
    União == inventário real (nenhuma lista nova fica esquecida de fora
    das duas classificações) e interseção vazia (nenhuma lista é as duas
    coisas ao mesmo tempo)."""
    empresa = cenario["empresa"]
    dre = apurar_dre(empresa=empresa, ano=2026, mes=3)
    coluna = dre["coluna_mes"]
    chaves_contas_na_coluna = {chave for chave in coluna if chave.startswith("contas_")}
    impedem = set(contabilidade_services._LISTAS_DA_DRE_QUE_IMPEDEM_A_EMISSAO)
    so_avisam = set(contabilidade_services._LISTAS_DA_DRE_QUE_SO_AVISAM)
    assert impedem | so_avisam == chaves_contas_na_coluna, "sentido 1 — união == inventário real"
    assert impedem & so_avisam == set(), "sentido 2 — interseção vazia"
