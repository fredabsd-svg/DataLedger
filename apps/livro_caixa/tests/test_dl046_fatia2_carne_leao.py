"""DL-046, fatia 2 — apuração mensal e anual do carnê-leão (RC-131 a
RC-134, HI-32 a HI-36). Servidor + API; a tela vem depois pelo
`especialista-frontend`.

Cobre: motor de cálculo puro com casos calculados à mão (faixa isenta, cada
faixa, os quatro pontos notáveis da redução da Lei 15.270/2025, excesso de
livro-caixa carregado e não carregado ao ano seguinte, dependentes,
desconto simplificado mais/menos benéfico, valor abaixo de R$ 10,00
acumulado, centavos, compensação do imposto pago no exterior); troca de
vigência no meio do ano; RC-130 (estorno no mês original refletindo no
encadeamento); isolamento entre empresas/escritórios; autorização; recusa
por modo de escrituração; e a prova de que a tabela nunca vem de constante
Python.

**Achado material, documentado no plano DL-046** (seção "Implementação da
fatia 2"): a Lei nº 9.250/1995, art. 3º-A (redação da Lei 15.270/2025),
descreve a redução até R$ 5.000,00 de rendimento como "de modo que o
imposto devido seja zero" — mas a combinação, LITERAL, da tabela
progressiva confirmada (RC-131) com a fórmula de redução (também
confirmada) produz, para R$ 5.000,00 de rendimento SEM outras deduções,
imposto de R$ 153,38, não zero (a redução máxima de R$ 312,89 não cobre o
imposto de R$ 466,27 que a tabela sozinha já produziria nessa faixa). Os
testes abaixo verificam o valor MATEMATICAMENTE DERIVADO das duas fontes
confirmadas, não a frase descritiva da lei — ver o plano para a hipótese
sobre a origem da diferença (a lei parece calibrada para a FOLHA DE
PAGAMENTO, onde o INSS já reduz a base antes da tabela; o carnê-leão não
tem dedução equivalente). Validação profissional do Fred antes de uso com
cliente real, como já vale para toda a fatia 1.
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.carne_leao import (
    DependentesCarneLeaoInvalido,
    TabelaCarneLeaoNaoConfigurada,
    _agregados_do_mes,
    _imposto_pela_tabela,
    _reducao_bruta,
    apurar_carne_leao_anual,
    apurar_carne_leao_mensal,
    registrar_dependentes_carne_leao,
)
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    DependentesCarneLeaoCliente,
    FaixaTabelaProgressivaCarneLeao,
    NaturezaCaixa,
    OrigemRecebimento,
    VigenciaDependenteCarneLeao,
    VigenciaReducaoCarneLeao,
    VigenciaTabelaProgressivaCarneLeao,
)
from apps.livro_caixa.services import criar_lancamento_caixa, estornar_lancamento_caixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório Carnê A", cnpj="22233344000155")
    escritorio_b = Escritorio.objects.create(nome="Escritório Carnê B", cnpj="66677788000199")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano Autônomo",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="12345678909",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Ciclano Autônomo",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Ltda",
        cnpj="22233344000155".replace("0155", "0122"),
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )

    # A tabela/redução SEMEADAS pela migração 0004 só cobrem a partir de
    # 2025-05-01/2026-01-01 (RC-131) — mas `criar_lancamento_caixa` recusa
    # data futura além de "hoje + 30 dias" (RC-77), e a apuração sempre
    # recalcula de JANEIRO do ano pedido. Testar um ano-calendário INTEIRO
    # (inclusive dezembro) exige um ano inteiramente no PASSADO com
    # vigência cobrindo os 12 meses — por isso esta vigência SINTÉTICA de
    # teste, com os MESMOS valores confirmados de RC-131 (nunca inventados;
    # só a DATA de início é fictícia, para o teste caber num ano seguro),
    # cobrindo desde 2024-01-01. Os testes deste arquivo usam o ano-
    # calendário de 2024/2025 (passado), nunca "hoje".
    vigencia_tabela_teste = VigenciaTabelaProgressivaCarneLeao.objects.create(
        vigencia_inicio=date(2024, 1, 1),
        fonte="Vigência sintética de TESTE, valores idênticos a RC-131 (só a data é fictícia).",
    )
    for ordem, limite_inferior, limite_superior, aliquota, parcela in [
        (1, Decimal("0.00"), Decimal("2428.80"), Decimal("0.0000"), Decimal("0.00")),
        (2, Decimal("2428.81"), Decimal("2826.65"), Decimal("0.0750"), Decimal("182.16")),
        (3, Decimal("2826.66"), Decimal("3751.05"), Decimal("0.1500"), Decimal("394.16")),
        (4, Decimal("3751.06"), Decimal("4664.68"), Decimal("0.2250"), Decimal("675.49")),
        (5, Decimal("4664.69"), None, Decimal("0.2750"), Decimal("908.73")),
    ]:
        FaixaTabelaProgressivaCarneLeao.objects.create(
            vigencia=vigencia_tabela_teste,
            ordem=ordem,
            limite_inferior=limite_inferior,
            limite_superior=limite_superior,
            aliquota=aliquota,
            parcela_a_deduzir=parcela,
        )
    VigenciaReducaoCarneLeao.objects.create(
        vigencia_inicio=date(2024, 1, 1),
        fonte="Vigência sintética de TESTE, valores idênticos a RC-131 (só a data é fictícia).",
        limite_faixa_plena=Decimal("5000.00"),
        reducao_maxima=Decimal("312.89"),
        constante_formula=Decimal("978.62"),
        coeficiente=Decimal("0.133145"),
        limite_superior=Decimal("7350.00"),
    )

    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    conta_notarial = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RN",
        nome="Emolumentos",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.002",
    )
    conta_aluguel = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RA",
        nome="Aluguel recebido",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_pensao_recebida = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RP",
        nome="Pensão alimentícia recebida",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.002.001",
    )
    conta_despesa_dedutivel = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="D10",
        nome="Despesa dedutível (livro-caixa)",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P10.001",
    )
    conta_previdencia = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DPREV",
        nome="Previdência oficial",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00001",
    )
    conta_pensao_paga = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DPENSAO",
        nome="Pensão alimentícia paga",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00002",
    )
    conta_imposto_exterior = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DEXT",
        nome="Imposto pago no exterior",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00003",
    )

    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "conta_trabalho": conta_trabalho,
        "conta_notarial": conta_notarial,
        "conta_aluguel": conta_aluguel,
        "conta_pensao_recebida": conta_pensao_recebida,
        "conta_despesa_dedutivel": conta_despesa_dedutivel,
        "conta_previdencia": conta_previdencia,
        "conta_pensao_paga": conta_pensao_paga,
        "conta_imposto_exterior": conta_imposto_exterior,
    }


def _lancar_trabalho(empresa, conta, data, valor):
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=data,
        valor=valor,
        historico="Honorários",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento="11144477735",
        cpf_beneficiario_nao_informado=True,
    )


def _lancar_despesa(empresa, conta, data, valor, historico="Despesa"):
    return criar_lancamento_caixa(
        empresa=empresa, conta=conta, data=data, valor=valor, historico=historico
    )


# ---------------------------------------------------------------------------
# 1. Motor de cálculo PURO — casos calculados à mão (critério 1 do plano).
#
# Tabela vigente (RC-131, semeada pela migração 0004, desde 2025-05-01):
#   até 2.428,80 — 0% — 0,00
#   2.428,81 a 2.826,65 — 7,5% — 182,16
#   2.826,66 a 3.751,05 — 15% — 394,16
#   3.751,06 a 4.664,68 — 22,5% — 675,49
#   acima de 4.664,68 — 27,5% — 908,73
# Redução (RC-131, desde 2026-01-01): até 5.000,00 → até 312,89 (zero,
# SEGUNDO A LEI); 5.000,01 a 7.350,00 → 978,62 − 0,133145×rendimento;
# acima de 7.350,00 → zero.


@pytest.fixture
def faixas():
    vigencia = VigenciaTabelaProgressivaCarneLeao.objects.get(vigencia_inicio=date(2025, 5, 1))
    return list(vigencia.faixas.order_by("ordem"))


@pytest.fixture
def reducao_cfg():
    # A REAL, semeada pela migração 0004 (RC-131) — não a sintética de teste
    # da fixture `cenario` (esta fixture não depende de `cenario`).
    return VigenciaReducaoCarneLeao.objects.get(vigencia_inicio=date(2026, 1, 1))


def test_faixa_isenta_imposto_zero(faixas):
    # 2.000,00 está na primeira faixa (até 2.428,80, alíquota 0%).
    # Cálculo à mão: 2000,00 × 0 − 0,00 = 0,00.
    assert _imposto_pela_tabela(Decimal("2000.00"), faixas) == Decimal("0.00")


@pytest.mark.parametrize(
    "base,imposto_esperado",
    [
        # Cálculo à mão de cada faixa, no MEIO dela (evita ambiguidade de
        # fronteira, testada separadamente abaixo):
        ("2600.00", "12.84"),  # 2600,00 × 0,075 − 182,16 = 195,00 − 182,16 = 12,84
        ("3300.00", "100.84"),  # 3300,00 × 0,15 − 394,16 = 495,00 − 394,16 = 100,84
        ("4200.00", "269.51"),  # 4200,00 × 0,225 − 675,49 = 945,00 − 675,49 = 269,51
        ("5500.00", "603.77"),  # 5500,00 × 0,275 − 908,73 = 1512,50 − 908,73 = 603,77
    ],
)
def test_cada_faixa_da_tabela(faixas, base, imposto_esperado):
    assert _imposto_pela_tabela(Decimal(base), faixas) == Decimal(imposto_esperado)


def test_rendimento_5000_sem_outras_deducoes_nao_zera_o_imposto(faixas, reducao_cfg):
    """Achado material (ver o docstring do módulo): a lei descreve a
    redução até R$ 5.000,00 como "imposto zero", mas a combinação literal
    das duas fontes confirmadas produz R$ 153,38 de imposto devido.

    Cálculo à mão:
    - imposto pela tabela: 5000,00 × 0,275 − 908,73 = 1375,00 − 908,73 = 466,27
    - redução (base ≤ 5.000,00 → redução máxima): 312,89
    - imposto após redução: 466,27 − 312,89 = 153,38
    """
    imposto_tabela = _imposto_pela_tabela(Decimal("5000.00"), faixas)
    assert imposto_tabela == Decimal("466.27")
    reducao = _reducao_bruta(Decimal("5000.00"), reducao_cfg)
    assert reducao == Decimal("312.89")
    assert imposto_tabela - reducao == Decimal("153.38")


def test_rendimento_6000_reducao_parcial(faixas, reducao_cfg):
    # imposto pela tabela: 6000,00 × 0,275 − 908,73 = 1650,00 − 908,73 = 741,27
    # redução: 978,62 − 0,133145 × 6000,00 = 978,62 − 798,87 = 179,75
    # imposto após redução: 741,27 − 179,75 = 561,52
    imposto_tabela = _imposto_pela_tabela(Decimal("6000.00"), faixas)
    assert imposto_tabela == Decimal("741.27")
    reducao = _reducao_bruta(Decimal("6000.00"), reducao_cfg)
    assert reducao == Decimal("179.75")
    assert imposto_tabela - reducao == Decimal("561.52")


def test_rendimento_7350_fim_da_reducao(faixas, reducao_cfg):
    # imposto pela tabela: 7350,00 × 0,275 − 908,73 = 2021,25 − 908,73 = 1112,52
    # redução: 978,62 − 0,133145 × 7350,00 = 978,62 − 978,61575 = 0,00425 → 0,00
    imposto_tabela = _imposto_pela_tabela(Decimal("7350.00"), faixas)
    assert imposto_tabela == Decimal("1112.52")
    assert _reducao_bruta(Decimal("7350.00"), reducao_cfg) == Decimal("0.00")


def test_rendimento_7350_01_sem_reducao(faixas, reducao_cfg):
    # §2º do art. 3º-A: acima de R$ 7.350,00, NENHUMA redução.
    assert _reducao_bruta(Decimal("7350.01"), reducao_cfg) == Decimal("0.00")
    assert _imposto_pela_tabela(Decimal("7350.01"), faixas) == Decimal("1112.52")


def test_centavos_nao_se_perdem(faixas):
    # 2826.66 é o primeiro centavo da faixa de 15% — a fronteira exata
    # entre duas faixas nunca deve "vazar" para a faixa vizinha.
    # 2826,66 × 0,15 − 394,16 = 423,999 − 394,16 = 29,839 → 29,84 (MEIO_PARA_CIMA)
    assert _imposto_pela_tabela(Decimal("2826.66"), faixas) == Decimal("29.84")
    # 2826,65 (último centavo da faixa de 7,5%):
    # 2826,65×0,075−182,16 = 211,99875−182,16 = 29,83875 → 29,84
    assert _imposto_pela_tabela(Decimal("2826.65"), faixas) == Decimal("29.84")


# ---------------------------------------------------------------------------
# 2. Motor de cálculo ORM — excesso de livro-caixa, dependentes, desconto
# simplificado, valor abaixo de R$ 10,00, compensação do exterior.


def test_excesso_de_livro_caixa_carregado_ao_mes_seguinte(cenario):
    empresa = cenario["empresa_a"]
    # Janeiro: R$ 1.000,00 de trabalho não assalariado, R$ 2.500,00 de
    # despesa dedutível — excesso de R$ 1.500,00 sobre a receita do mês.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 1, 10), "1000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2024, 1, 15), "2500.00")
    resultado_jan = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=1)
    assert resultado_jan["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_jan["excesso_livro_caixa_novo"] == Decimal("1500.00")

    # Fevereiro: mais R$ 1.000,00 de trabalho, sem despesa nova — o excesso
    # de janeiro (R$ 1.500,00) some aplicado contra a receita de fevereiro.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 2, 10), "1000.00")
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=2)
    assert resultado_fev["excesso_livro_caixa_anterior"] == Decimal("1500.00")
    # disponível = 0 (sem despesa nova) + 1500 anterior = 1500; limitado à
    # receita do mês (1000) -> dedução = 1000; excesso novo = 500.
    assert resultado_fev["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_fev["excesso_livro_caixa_novo"] == Decimal("500.00")
    assert resultado_fev["base_de_calculo"] == Decimal("0.00")


def test_excesso_de_dezembro_nao_passa_para_janeiro(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 12, 5), "1000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2024, 12, 10), "3000.00")
    resultado_dez = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=12)
    # Disponível = 3000; limitado à receita (1000); dedução = 1000; excesso
    # SERIA 2000, mas dezembro ZERA (art. 69, §1º, RIR/2018) — nunca passa
    # ao ano seguinte.
    assert resultado_dez["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_dez["excesso_livro_caixa_novo"] == Decimal("0.00")

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2025, 1, 5), "1000.00")
    resultado_jan_2025 = apurar_carne_leao_mensal(empresa=empresa, ano=2025, mes=1)
    assert resultado_jan_2025["excesso_livro_caixa_anterior"] == Decimal("0.00")
    assert resultado_jan_2025["base_de_calculo"] == Decimal("1000.00")


def test_dependentes_reduzem_a_base(cenario):
    empresa = cenario["empresa_a"]
    registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=2, competencia_inicio=date(2024, 1, 1)
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 3, 10), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=3)
    # 2 dependentes × R$ 189,59 = R$ 379,18.
    assert resultado["dependentes_valor"] == Decimal("379.18")
    assert resultado["base_de_calculo"] == Decimal("2620.82")  # 3000,00 - 379,18


def test_dependentes_vigencia_mensal_nao_retroage(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 2, 10), "3000.00")
    registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=1, competencia_inicio=date(2024, 3, 1)
    )
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=2)
    assert resultado_fev["dependentes_quantidade"] == 0


def test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais(cenario):
    empresa = cenario["empresa_a"]
    # Sem NENHUMA dedução real, rendimento de R$ 6.000,00:
    # - reais: base 6000,00 -> imposto tabela 741,27 -> redução 179,75
    #   (978,62 − 0,133145×6000) -> imposto após redução 561,52.
    # - simplificado: desconto 25% de 2.428,80 = 607,20 -> base 5.392,80
    #   -> imposto tabela 574,29 -> redução 260,60 -> imposto após redução
    #   313,69 — ESTRITAMENTE menor que 561,52: simplificado vence.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 4, 10), "6000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=4)
    assert resultado["desconto_simplificado"] == Decimal("607.20")
    assert resultado["memoria_deducoes_reais"]["imposto_apos_reducao"] == Decimal("561.52")
    assert resultado["memoria_desconto_simplificado"]["imposto_apos_reducao"] == Decimal("313.69")
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["base_de_calculo"] == Decimal("5392.80")  # 6000 - 607.20
    assert resultado["imposto_apos_reducao"] == Decimal("313.69")


def test_deducoes_reais_mais_beneficio_quando_maiores_que_o_simplificado(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 5, 10), "3000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2024, 5, 12), "2000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=5)
    assert resultado["deducoes_reais_total"] == Decimal("2000.00")
    assert resultado["forma_escolhida"] == "real"
    assert resultado["base_de_calculo"] == Decimal("1000.00")  # 3000 - 2000, melhor que 3000-607.20


def test_valor_abaixo_de_dez_reais_acumula_para_o_mes_seguinte(cenario):
    empresa = cenario["empresa_a"]
    # Rendimento pequeno todo mês: base pequena o bastante para o imposto
    # devido, mês a mês, ficar abaixo de R$ 10,00.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 1, 10), "2826.70")
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 2, 10), "2826.70")
    resultado_jan = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=1)
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=2)
    assert resultado_jan["imposto_devido_no_mes"] < Decimal("10.00")
    assert resultado_jan["valor_a_pagar"] == Decimal("0.00")
    assert (
        resultado_jan["saldo_pendente_abaixo_de_dez_novo"] == resultado_jan["imposto_devido_no_mes"]
    )
    esperado_fev = resultado_jan["imposto_devido_no_mes"] + resultado_fev["imposto_devido_no_mes"]
    if esperado_fev >= Decimal("10.00"):
        assert resultado_fev["valor_a_pagar"] == esperado_fev
        assert resultado_fev["saldo_pendente_abaixo_de_dez_novo"] == Decimal("0.00")
    else:
        assert resultado_fev["valor_a_pagar"] == Decimal("0.00")


def test_compensacao_do_imposto_pago_no_exterior(cenario):
    empresa = cenario["empresa_a"]
    # Rendimento do exterior de R$ 6.000,00, ÚNICA receita do mês — sem
    # ele, o rendimento sujeito seria zero (imposto zero); com ele, o
    # imposto após redução é R$ 313,69 (mesmo cálculo de
    # `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`).
    # O limite de compensação do exterior (Q267, P&R IRPF 2026) é essa
    # diferença inteira (313,69 − 0,00); o crédito de R$ 50,00 pago no
    # exterior cabe dentro do limite e compensa integralmente.
    lancamento_exterior = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_aluguel"],
        data=date(2024, 6, 10),
        valor="6000.00",
        historico="Aluguel do exterior",
        recebido_de=OrigemRecebimento.EX,
    )
    assert lancamento_exterior.recebido_de == "EX"
    _lancar_despesa(
        empresa,
        cenario["conta_imposto_exterior"],
        date(2024, 6, 10),
        "50.00",
        "Imposto pago no exterior",
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=6)
    assert resultado["limite_compensacao_exterior"] > Decimal("0.00")
    assert resultado["compensacao_exterior_aplicada"] == Decimal("50.00")
    assert resultado["imposto_devido_no_mes"] == (
        resultado["imposto_apos_reducao"] - Decimal("50.00")
    )


def test_rendimento_de_pessoa_juridica_nao_entra_na_base_do_trabalho_nao_assalariado(cenario):
    empresa = cenario["empresa_a"]
    lancamento = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_trabalho"],
        data=date(2024, 7, 10),
        valor="5000.00",
        historico="Honorários de pessoa jurídica",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador="11222333000181",
    )
    assert lancamento.recebido_de == "PJ"
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=7)
    assert resultado["rendimento_total_sujeito"] == Decimal("0.00")


def test_pensao_alimenticia_recebida_e_imune_ao_carne_leao(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=date(2024, 7, 15),
        valor="2000.00",
        historico="Pensão alimentícia recebida",
        recebido_de=OrigemRecebimento.PF,
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=7)
    assert resultado["rendimento_total_sujeito"] == Decimal("0.00")


def test_rendimento_notarial_de_pessoa_juridica_entra_na_base(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=date(2024, 8, 10),
        valor="4000.00",
        historico="Emolumentos pagos por pessoa jurídica",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador="11222333000181",
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=8)
    assert resultado["rendimento_total_sujeito"] == Decimal("4000.00")


# ---------------------------------------------------------------------------
# 3. Troca de vigência no meio do ano (critério 2 do plano).


def _criar_vigencia_tabela_diferente(vigencia_inicio):
    vigencia = VigenciaTabelaProgressivaCarneLeao.objects.create(
        vigencia_inicio=vigencia_inicio, fonte="Vigência sintética de teste (critério 2)."
    )
    FaixaTabelaProgressivaCarneLeao.objects.create(
        vigencia=vigencia,
        ordem=1,
        limite_inferior=Decimal("0.00"),
        limite_superior=Decimal("1000.00"),
        aliquota=Decimal("0.0000"),
        parcela_a_deduzir=Decimal("0.00"),
    )
    FaixaTabelaProgressivaCarneLeao.objects.create(
        vigencia=vigencia,
        ordem=2,
        limite_inferior=Decimal("1000.01"),
        limite_superior=None,
        aliquota=Decimal("0.5000"),
        parcela_a_deduzir=Decimal("500.00"),
    )
    return vigencia


def test_troca_de_vigencia_nao_altera_apuracao_de_mes_anterior(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 3, 10), "5000.00")
    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=3)

    _criar_vigencia_tabela_diferente(date(2024, 6, 1))

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=3)
    assert resultado_depois == resultado_antes
    assert resultado_depois["tabela_vigencia_inicio"] == date(2024, 1, 1)

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 6, 10), "5000.00")
    resultado_junho = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=6)
    assert resultado_junho["tabela_vigencia_inicio"] == date(2024, 6, 1)
    # Tabela sintética: 5000,00 × 0,50 − 500,00 = 2000,00 — bem diferente
    # do que a tabela real produziria (466,27) — prova de que a vigência
    # NOVA é a que está sendo usada. Lido na memória de cálculo das
    # DEDUÇÕES REAIS (sem depender de qual forma — real ou simplificado —
    # a apuração escolheu como mais benéfica).
    assert resultado_junho["memoria_deducoes_reais"]["imposto_tabela"] == Decimal("2000.00")


# ---------------------------------------------------------------------------
# 4. RC-130 — estorno no mês original reflete no mês e no encadeamento.


def test_estorno_no_mes_original_reflete_no_encadeamento(cenario):
    empresa = cenario["empresa_a"]
    despesa = _lancar_despesa(
        empresa, cenario["conta_despesa_dedutivel"], date(2024, 1, 10), "2000.00"
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 3, 10), "500.00")

    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=3)
    assert resultado_antes["excesso_livro_caixa_anterior"] == Decimal("2000.00")

    # Correção rastreável: o mês original (janeiro) é REABERTO por
    # ESTORNO — nunca edição silenciosa (RC-130/AGENTS.md §10).
    estornar_lancamento_caixa(despesa, data=date(2024, 1, 20))

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=3)
    assert resultado_depois["excesso_livro_caixa_anterior"] == Decimal("0.00")
    assert resultado_depois != resultado_antes


# ---------------------------------------------------------------------------
# 5. Isolamento, autorização e modo de escrituração — API.


def test_api_carne_leao_mensal_recusa_empresa_de_outro_escritorio(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-a")
    client.login(username="admin-a", password="senha-forte-123")
    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_b"].id})
    resposta = client.get(url, {"ano": "2024", "mes": "3"})
    assert resposta.status_code == 404


def test_api_carne_leao_mensal_recusa_empresa_em_modo_contabilidade(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-b")
    client.login(username="admin-b", password="senha-forte-123")
    url = reverse(
        "livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_contabilidade"].id}
    )
    resposta = client.get(url, {"ano": "2024", "mes": "3"})
    assert resposta.status_code == 400


def test_api_carne_leao_mensal_recusa_papel_sem_permissao(client, cenario):
    # PARALEGAL lê a contabilidade/livro-caixa (matriz da fatia 1) — o
    # carnê-leão usa a MESMA matriz de leitura; então um usuário SEM
    # NENHUM vínculo é quem prova a recusa por autorização.
    get_user_model().objects.create_user(
        username="sem-vinculo", email="sv@escritorio.com.br", password="senha-forte-123"
    )
    client.login(username="sem-vinculo", password="senha-forte-123")
    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_a"].id})
    resposta = client.get(url, {"ano": "2024", "mes": "3"})
    assert resposta.status_code in (403, 404)


def test_api_carne_leao_mensal_isolamento_entre_empresas_do_mesmo_escritorio(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-iso")
    client.login(username="admin-iso", password="senha-forte-123")
    empresa_c = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Outro Cliente",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="98765432100",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    conta_c = ContaLivroCaixa.objects.create(
        empresa=empresa_c,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    _lancar_trabalho(empresa_c, conta_c, date(2024, 3, 10), "9000.00")
    _lancar_trabalho(cenario["empresa_a"], cenario["conta_trabalho"], date(2024, 3, 10), "500.00")

    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_a"].id})
    resposta = client.get(url, {"ano": "2024", "mes": "3"})
    assert resposta.status_code == 200
    assert resposta.json()["rendimento_total_sujeito"] == "500.00"


def test_api_dependentes_post_registra_e_isola_por_empresa(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-dep")
    client.login(username="admin-dep", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao", kwargs={"empresa_id": cenario["empresa_a"].id}
    )
    resposta = client.post(
        url,
        data=json.dumps({"quantidade": 3, "competencia_inicio": "2024-01-01"}),
        content_type="application/json",
    )
    assert resposta.status_code == 201
    assert resposta.json()["quantidade"] == 3
    assert DependentesCarneLeaoCliente.objects.filter(empresa=cenario["empresa_a"]).count() == 1

    url_outra_empresa = reverse(
        "livro_caixa:dependentes-carne-leao", kwargs={"empresa_id": cenario["empresa_b"].id}
    )
    resposta_outra = client.get(url_outra_empresa)
    assert resposta_outra.status_code == 404


def test_api_dependentes_post_recusa_empresa_em_modo_contabilidade(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-dep2")
    client.login(username="admin-dep2", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao",
        kwargs={"empresa_id": cenario["empresa_contabilidade"].id},
    )
    resposta = client.post(
        url,
        data=json.dumps({"quantidade": 1, "competencia_inicio": "2024-01-01"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


def test_servico_dependentes_recusa_modo_contabilidade(cenario):
    with pytest.raises(DependentesCarneLeaoInvalido):
        registrar_dependentes_carne_leao(
            empresa=cenario["empresa_contabilidade"],
            quantidade=1,
            competencia_inicio=date(2024, 1, 1),
        )


def test_modelo_dependentes_recusa_competencia_fora_do_primeiro_dia(cenario):
    registro = DependentesCarneLeaoCliente(
        empresa=cenario["empresa_a"], quantidade=1, competencia_inicio=date(2024, 1, 15)
    )
    with pytest.raises(ValidationError):
        registro.full_clean()


# ---------------------------------------------------------------------------
# 6. Critério 5 — nenhum número normativo vem de constante no código.


def test_apuracao_falha_sem_tabela_vigente_configurada(cenario):
    empresa = cenario["empresa_a"]
    FaixaTabelaProgressivaCarneLeao.objects.all().delete()
    VigenciaTabelaProgressivaCarneLeao.objects.all().delete()
    VigenciaReducaoCarneLeao.objects.all().delete()
    VigenciaDependenteCarneLeao.objects.all().delete()
    with pytest.raises(TabelaCarneLeaoNaoConfigurada):
        apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=1)


def test_apuracao_le_valor_do_banco_nao_de_constante(cenario):
    """Muda um valor normativo SÓ NO BANCO (nunca no código) e confirma que
    o resultado muda — se o motor lesse de uma constante Python, esta
    alteração via ORM não teria efeito nenhum.

    Cenário: rendimento de R$ 6.000,00 com R$ 1.200,00 de despesa dedutível
    -> base real R$ 4.800,00 (faixa de redução PLENA, ≤ R$ 5.000,00, e
    imposto pela tabela de R$ 411,27 — MAIOR que a redução máxima de
    R$ 312,89, então a redução NÃO está limitada pelo imposto aqui, e a
    mudança de `reducao_maxima` se reflete inteira no resultado). As
    deduções reais (R$ 1.200,00) vencem o desconto simplificado (R$
    607,20) — a forma escolhida continua "real" antes e depois da
    mutação, então a comparação isola só o efeito do valor normativo.
    """
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 9, 10), "6000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2024, 9, 12), "1200.00")
    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=9)
    assert resultado_antes["forma_escolhida"] == "real"
    assert resultado_antes["reducao_lei_15270_2025"] == Decimal("312.89")

    VigenciaReducaoCarneLeao.objects.filter(vigencia_inicio=date(2024, 1, 1)).update(
        reducao_maxima=Decimal("999.99")
    )

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=9)
    assert resultado_depois["forma_escolhida"] == "real"
    assert resultado_depois["reducao_lei_15270_2025"] == Decimal("411.27")
    assert resultado_depois["reducao_lei_15270_2025"] != resultado_antes["reducao_lei_15270_2025"]


def test_apuracao_anual_devolve_os_12_meses(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2024, 1, 10), "1000.00")
    resultado = apurar_carne_leao_anual(empresa=empresa, ano=2024)
    assert len(resultado["meses"]) == 12
    assert [m["mes"] for m in resultado["meses"]] == list(range(1, 13))


def test_agregados_do_mes_estorno_tem_sinal_invertido():
    """Sanidade do motor de agregação isolado (sem banco): um estorno de
    receita SUBTRAI do total, nunca soma como receita nova — mesma
    convenção de `apurar_livro_caixa` (D3, fatia 1)."""

    class _ContaFake:
        def __init__(self, natureza, codigo):
            self.natureza = natureza
            self.codigo_carne_leao = codigo

    class _LancamentoFake:
        def __init__(self, conta, valor, estorno_de_id, recebido_de="PF"):
            self.conta = conta
            self.valor = valor
            self.estorno_de_id = estorno_de_id
            self.recebido_de = recebido_de

    conta = _ContaFake(NaturezaCaixa.RECEITA, "R01.001.001")
    original = _LancamentoFake(conta, Decimal("500.00"), None)
    estorno = _LancamentoFake(conta, Decimal("500.00"), 1)
    agregados = _agregados_do_mes([original, estorno])
    assert agregados["rendimento_total_sujeito"] == Decimal("0.00")
