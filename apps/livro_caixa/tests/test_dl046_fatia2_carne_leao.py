"""DL-046, fatia 2 — apuração mensal e anual do carnê-leão (RC-131 a
RC-134, HI-32, HI-35 a HI-37). Servidor + API; a tela vem depois pelo
`especialista-frontend`.

Cobre: motor de cálculo puro com casos calculados à mão, adaptados dos
CINCO exemplos oficiais da Receita Federal ("Exemplos de Aplicação da Lei
15.270/2025", gov.br/receitafederal — RC-133) — "salário bruto" tratado
como rendimento do trabalho não assalariado, "contribuição previdenciária"
como previdência oficial (P20.01.00001); excesso de livro-caixa carregado
e não carregado ao ano seguinte; dependentes; valor abaixo de R$ 10,00
acumulado; compensação do imposto pago no exterior; troca de vigência no
meio do ano; RC-130 (estorno no mês original refletindo no encadeamento);
isolamento entre empresas/escritórios; autorização; recusa por modo de
escrituração; e a prova de que a tabela nunca vem de constante Python.

**Correção de 2026-09-27 (ordem do arquiteto-senior), registrada no plano
DL-046 ("Correção da RC-133"):** a primeira versão desta fatia usava a
BASE DE CÁLCULO (após deduções) como referência da redução da Lei
15.270/2025 — ERRADO. A Receita Federal usa o RENDIMENTO BRUTO (antes de
qualquer dedução) tanto para decidir a FAIXA da redução (até R$ 5.000,00 /
R$ 5.000,01 a R$ 7.350,00 / acima de R$ 7.350,00) quanto para a fórmula em
si — confirmado pelo Exemplo 5 oficial, que usa expressamente "o valor do
salário (R$ 7.607,20), e não o da base de cálculo (R$ 7.000,00)" mesmo com
a base dentro do limite de R$ 7.350,00. A consequência do que era
apresentado como "achado material" (R$ 5.000,00 não zerar o imposto)
DEIXA DE EXISTIR com a correção: o motor sempre encontra, via desconto
simplificado quando mais benéfico, imposto ZERO para todo rendimento bruto
até R$ 5.000,00 — ver `test_bruto_ate_5000_sempre_zera_via_forma_mais_beneficia`.
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.carne_leao import (
    DependentesCarneLeaoInvalido,
    ImpostoExteriorSemRendimentoExterior,
    TabelaCarneLeaoNaoConfigurada,
    _agregados_do_mes,
    _apurar_um_mes,
    _imposto_pela_tabela,
    _pipeline,
    _reducao_bruta,
    apurar_carne_leao_anual,
    apurar_carne_leao_mensal,
    registrar_dependentes_carne_leao,
    retificar_dependentes_carne_leao,
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

    # DE-091 item 5 (M-5, correção da rodada 1 da auditoria): ano < 2025
    # passou a ser explicitamente fora do escopo — este arquivo já não
    # pode mais testar um ano-calendário fictício de teste com vigência
    # SINTÉTICA "de propósito no passado" (a versão anterior usava
    # 2024/2025). Em vez de recriar valores que já existem, os testes
    # abaixo usam as vigências REAIS semeadas pela migração 0004/0006
    # (tabela desde 2025-05-01, redução desde 2026-01-01, ambas com os
    # MESMOS valores que esta fixture antes recriava "sinteticamente") —
    # cada teste escolhe um mês seguro (não futuro em relação a "hoje",
    # RC-77) dentro de 2025/2026, documentado caso a caso.
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


def test_reducao_por_faixa_do_rendimento_bruto(faixas, reducao_cfg):
    """`_reducao_bruta` recebe o RENDIMENTO BRUTO (RC-133) — casos com
    base = bruto (sem outras deduções), para isolar só a fórmula da
    redução por faixa, sem envolver ainda a escolha entre formas.

    - até R$ 5.000,00: redução fixa R$ 312,89 (limitada ao imposto, §1º).
      Em 6000,00: imposto pela tabela 6000,00×0,275−908,73=741,27,
      redução 312,89 < 741,27 → não teria efeito de limite aqui, é só a
      faixa PLENA. Testado separadamente com R$ 4.000,00, abaixo.
    - de R$ 5.000,01 a R$ 7.350,00: 978,62 − 0,133145×bruto — em
      R$ 6.000,00: 978,62 − 798,87 = 179,75.
    - a partir de R$ 7.350,00 (inclusive o limite): decrescente até zerar.
      Em R$ 7.350,00: 978,62 − 978,61575 = 0,00425 → 0,00 (MEIO_PARA_CIMA).
    - acima de R$ 7.350,00: SEM redução (§2º) — R$ 7.350,01 e R$ 7.607,20
      (bruto do Exemplo 5 oficial da Receita).
    """
    assert _reducao_bruta(Decimal("4000.00"), reducao_cfg) == Decimal("312.89")
    # A2 (auditoria, mutante da fronteira de R$ 5.000,00, `<=` → `<`):
    # exatamente R$ 5.000,00 ainda está na faixa PLENA (redução 312,89) —
    # se a fronteira virasse `<`, cairia na faixa linear e daria 312,895 →
    # 312,90 (arredondado), um valor DIFERENTE que provaria o mutante.
    assert _reducao_bruta(Decimal("5000.00"), reducao_cfg) == Decimal("312.89")
    assert _reducao_bruta(Decimal("6000.00"), reducao_cfg) == Decimal("179.75")
    assert _reducao_bruta(Decimal("7350.00"), reducao_cfg) == Decimal("0.00")
    assert _reducao_bruta(Decimal("7350.01"), reducao_cfg) == Decimal("0.00")
    assert _reducao_bruta(Decimal("7607.20"), reducao_cfg) == Decimal("0.00")


def test_imposto_pela_tabela_em_cada_bruto_notavel(faixas):
    # 6000,00 × 0,275 − 908,73 = 1650,00 − 908,73 = 741,27
    assert _imposto_pela_tabela(Decimal("6000.00"), faixas) == Decimal("741.27")
    # 7350,00 × 0,275 − 908,73 = 2021,25 − 908,73 = 1112,52
    assert _imposto_pela_tabela(Decimal("7350.00"), faixas) == Decimal("1112.52")
    assert _imposto_pela_tabela(Decimal("7350.01"), faixas) == Decimal("1112.52")


def test_centavos_nao_se_perdem(faixas):
    # 2826.66 é o primeiro centavo da faixa de 15% — a fronteira exata
    # entre duas faixas nunca deve "vazar" para a faixa vizinha.
    # 2826,66 × 0,15 − 394,16 = 423,999 − 394,16 = 29,839 → 29,84 (MEIO_PARA_CIMA)
    assert _imposto_pela_tabela(Decimal("2826.66"), faixas) == Decimal("29.84")
    # 2826,65 (último centavo da faixa de 7,5%):
    # 2826,65×0,075−182,16 = 211,99875−182,16 = 29,83875 → 29,84
    assert _imposto_pela_tabela(Decimal("2826.65"), faixas) == Decimal("29.84")


def test_aud_a17_arredondamento_meio_centavo_e_meio_para_cima(faixas):
    """A17 (auditoria, mutante do arredondamento ABNT/meio-par): 2.826,70 ×
    15% − 394,16 = 424,005 − 394,16 = 29,845 → MEIO_PARA_CIMA arredonda
    para 29,85 (HI-36). Arredondamento "meio para o par" (ABNT NBR 5891)
    arredondaria para 29,84 (o algarismo anterior, 4, já é par) — valor
    DIFERENTE, prova de que a política é MEIO_PARA_CIMA, nunca a outra."""
    assert _imposto_pela_tabela(Decimal("2826.70"), faixas) == Decimal("29.85")


# ---------------------------------------------------------------------------
# 1B. Os CINCO exemplos oficiais da Receita Federal ("Exemplos de Aplicação
# da Lei 15.270/2025", gov.br/receitafederal, publicado 22/12/2025,
# atualizado 04/03/2026 — cópia em scratchpad/exemplos15270.html),
# adaptados ao carnê-leão: "salário bruto" -> rendimento do trabalho não
# assalariado; "contribuição previdenciária" (dedução real) -> previdência
# oficial. `_pipeline` recebe (base, RENDIMENTO BRUTO, faixas, redução) —
# RC-133: a redução usa SEMPRE o bruto, nunca a base, nas duas chamadas
# (real e simplificado) do mesmo mês.
#
# Cada teste reproduz o texto oficial LITERALMENTE no comentário e
# confere que o valor produzido pelo motor bate com o valor publicado —
# não é o motor "inspirando-se" no exemplo, é o exemplo batendo o próprio
# resultado do motor, número a número.


def test_exemplo_oficial_1_alicota_zero(faixas, reducao_cfg):
    """Exemplo 1 (Receita Federal): "João recebe salário bruto de
    R$ 3.036,00 ... dedução ... contribuição previdenciária ... R$ 257,73."
    "desconto simplificado mensal ... 25% de R$ 2.428,80 = R$ 607,20 ...
    mais vantajoso" -> base "R$ 3.036,00 – R$ 607,20 = R$ 2.428,00" -> 1ª
    faixa, 0% -> "R$ 0,00".

    ⚠️ O texto oficial soma R$ 3.036,00 − R$ 607,20 = R$ 2.428,00 — a
    subtração correta é R$ 2.428,80 (aparente erro de digitação da própria
    Receita, sem efeito no resultado: as duas quantias caem na MESMA 1ª
    faixa, isenta). Este teste usa o valor MATEMATICAMENTE CORRETO
    (R$ 2.428,80); o resultado final ("R$ 0,00") bate com o texto oficial
    do mesmo jeito.
    """
    bruto = Decimal("3036.00")
    deducao_real = Decimal("257.73")
    desconto_simplificado = Decimal("607.20")
    real = _pipeline(bruto - deducao_real, bruto, faixas, reducao_cfg)
    simplificado = _pipeline(bruto - desconto_simplificado, bruto, faixas, reducao_cfg)
    assert simplificado["base"] == Decimal("2428.80")
    assert simplificado["imposto_apos_reducao"] == Decimal("0.00")
    escolhido = min(real, simplificado, key=lambda p: p["imposto_apos_reducao"])
    assert escolhido["imposto_apos_reducao"] == Decimal("0.00")  # RFB: "R$ 0,00"


def test_exemplo_oficial_2_renda_abaixo_de_5000(faixas, reducao_cfg):
    """Exemplo 2: bruto R$ 4.000,00, previdência R$ 373,41. Simplificado
    mais vantajoso -> base R$ 4.000,00 − R$ 607,20 = R$ 3.392,80 -> 3ª
    faixa (15%, deduzir R$ 394,16): "R$ 3.392,80 × 15% − R$ 394,16 =
    R$ 114,76." Bruto (R$ 4.000,00) na 1ª faixa da redução (até R$5.000,00)
    -> "redução ... até R$ 312,89 (de modo a que o imposto devido seja
    zero)" -> "R$ 114,76 − R$ 114,76 = R$ 0,00" (limitada ao imposto)."""
    bruto = Decimal("4000.00")
    deducao_real = Decimal("373.41")
    desconto_simplificado = Decimal("607.20")
    real = _pipeline(bruto - deducao_real, bruto, faixas, reducao_cfg)
    simplificado = _pipeline(bruto - desconto_simplificado, bruto, faixas, reducao_cfg)
    assert simplificado["imposto_tabela"] == Decimal("114.76")  # RFB: "R$ 114,76"
    assert simplificado["reducao_aplicada"] == Decimal("114.76")  # limitada ao imposto
    assert simplificado["imposto_apos_reducao"] == Decimal("0.00")
    escolhido = min(real, simplificado, key=lambda p: p["imposto_apos_reducao"])
    assert escolhido["imposto_apos_reducao"] == Decimal("0.00")


def test_exemplo_oficial_3_renda_de_5000(faixas, reducao_cfg):
    """Exemplo 3: bruto R$ 5.000,00, previdência R$ 509,60. Simplificado
    mais vantajoso -> base R$ 5.000,00 − R$ 607,20 = R$ 4.392,80 -> 4ª
    faixa (22,5%, deduzir R$ 675,49): "R$ 4.392,80 × 22,5% − R$ 675,49 =
    R$ 312,89." Bruto (R$ 5.000,00) ainda na 1ª faixa da redução -> "R$
    312,89 − R$ 312,89 = R$ 0,00"."""
    bruto = Decimal("5000.00")
    deducao_real = Decimal("509.60")
    desconto_simplificado = Decimal("607.20")
    real = _pipeline(bruto - deducao_real, bruto, faixas, reducao_cfg)
    simplificado = _pipeline(bruto - desconto_simplificado, bruto, faixas, reducao_cfg)
    assert simplificado["imposto_tabela"] == Decimal("312.89")  # RFB: "R$ 312,89"
    assert simplificado["imposto_apos_reducao"] == Decimal("0.00")
    escolhido = min(real, simplificado, key=lambda p: p["imposto_apos_reducao"])
    assert escolhido["imposto_apos_reducao"] == Decimal("0.00")


def test_bruto_ate_5000_sempre_zera_via_forma_mais_beneficia(faixas, reducao_cfg):
    """Consequência da correção da RC-133 (ver o docstring do módulo): a
    frase da lei ("de modo que o imposto devido seja zero" até R$
    5.000,00) volta a se verificar — para QUALQUER bruto até R$ 5.000,00,
    SEM outras deduções, a forma simplificada sempre produz imposto zero
    (a redução PLENA, R$ 312,89, sempre alcança ou supera o imposto da
    tabela sobre `bruto − R$ 607,20`, que nunca passa de R$ 312,89 dentro
    desta faixa) — e a apuração escolhe a forma mais benéfica (HI-33), que
    aqui é sempre zero. Substitui o "achado material" da versão anterior
    desta fatia, que usava a BASE em vez do BRUTO na redução (corrigido)."""
    for bruto_str in ("100.00", "2428.80", "3036.00", "4000.00", "5000.00"):
        bruto = Decimal(bruto_str)
        real = _pipeline(bruto, bruto, faixas, reducao_cfg)  # sem outras deduções
        simplificado = _pipeline(bruto - Decimal("607.20"), bruto, faixas, reducao_cfg)
        escolhido = min(real, simplificado, key=lambda p: p["imposto_apos_reducao"])
        assert escolhido["imposto_apos_reducao"] == Decimal("0.00"), bruto_str


def test_exemplo_oficial_4_renda_acima_de_5000_com_reducao(faixas, reducao_cfg):
    """Exemplo 4: bruto R$ 6.000,00, previdência R$ 649,60 — MAIOR que o
    desconto simplificado (R$ 607,20), "a fonte pagadora deve considerar
    as deduções legais permitidas". Base R$ 6.000,00 − R$ 649,60 =
    R$ 5.350,40 -> 5ª faixa (27,5%, deduzir R$ 908,73): "R$ 5.350,40 ×
    27,5% − R$ 908,73 = R$ 562,63." Bruto (R$ 6.000,00) na 2ª faixa da
    redução -> "R$ 978,62 − (0,133145 × R$ 6.000,00) = ... R$ 179,75" ->
    "R$ 562,63 − R$ 179,75 = R$ 382,88" — e as deduções REAIS vencem o
    desconto simplificado (a apuração escolhe a forma mais benéfica)."""
    bruto = Decimal("6000.00")
    deducao_real = Decimal("649.60")
    desconto_simplificado = Decimal("607.20")
    real = _pipeline(bruto - deducao_real, bruto, faixas, reducao_cfg)
    simplificado = _pipeline(bruto - desconto_simplificado, bruto, faixas, reducao_cfg)
    assert real["imposto_tabela"] == Decimal("562.63")  # RFB: "R$ 562,63"
    assert real["reducao_aplicada"] == Decimal("179.75")  # RFB: "R$ 179,75"
    assert real["imposto_apos_reducao"] == Decimal("382.88")  # RFB: "R$ 382,88"
    escolhido = min(real, simplificado, key=lambda p: p["imposto_apos_reducao"])
    assert escolhido is real  # deduções reais vencem, como no exemplo oficial
    assert escolhido["imposto_apos_reducao"] == Decimal("382.88")


def test_exemplo_oficial_5_base_menor_que_7350_mas_bruto_maior_sem_reducao(faixas, reducao_cfg):
    """Exemplo 5, o caso central da correção da RC-133: bruto
    R$ 7.607,20, sem dedução real. Simplificado (mais vantajoso, único
    disponível) -> base R$ 7.607,20 − R$ 607,20 = R$ 7.000,00 -> 5ª faixa:
    "R$ 7.000,00 × 27,5% − R$ 908,73 = R$ 1.016,27." "o salário
    (rendimento tributável sujeito à incidência mensal) é superior ao
    valor de R$ 7.350,00 ... não é permitida a redução ... Importante
    observar que se utiliza nessa tabela de redução o valor do SALÁRIO
    (R$ 7.607,20), e não o da BASE DE CÁLCULO (R$ 7.000,00)" — a BASE
    (R$ 7.000,00) está dentro do limite de R$ 7.350,00, mas o BRUTO não;
    prevalece o bruto."""
    bruto = Decimal("7607.20")
    desconto_simplificado = Decimal("607.20")
    simplificado = _pipeline(bruto - desconto_simplificado, bruto, faixas, reducao_cfg)
    assert simplificado["base"] == Decimal("7000.00")  # < 7.350,00
    assert simplificado["imposto_tabela"] == Decimal("1016.27")  # RFB: "R$ 1.016,27"
    assert simplificado["reducao_disponivel"] == Decimal("0.00")  # bruto > 7.350,00: SEM redução
    assert simplificado["imposto_apos_reducao"] == Decimal("1016.27")


def test_reducao_limitada_ao_imposto_com_deducoes_reais_altas(faixas, reducao_cfg):
    """Critério adicional (ordem do arquiteto-senior): bruto ≤ R$ 5.000,00
    com deduções reais tão altas que a base de cálculo real fica muito
    abaixo do que a redução plena (R$ 312,89) cobriria — a redução fica
    LIMITADA ao imposto pela tabela (§1º do art. 3º-A), nunca produz
    "crédito": bruto R$ 4.000,00 (1ª faixa da redução, R$ 312,89
    disponível), previdência R$ 3.800,00 -> base R$ 200,00 (1ª faixa da
    tabela, 0%) -> imposto pela tabela R$ 0,00 -> redução APLICADA
    R$ 0,00 (não R$ 312,89, que seria negativo em excesso) -> devido
    R$ 0,00."""
    bruto = Decimal("4000.00")
    deducao_real = Decimal("3800.00")
    real = _pipeline(bruto - deducao_real, bruto, faixas, reducao_cfg)
    assert real["base"] == Decimal("200.00")
    assert real["imposto_tabela"] == Decimal("0.00")
    assert real["reducao_disponivel"] == Decimal("312.89")  # disponível na faixa
    assert real["reducao_aplicada"] == Decimal("0.00")  # mas LIMITADA ao imposto (zero)
    assert real["imposto_apos_reducao"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# 2. Motor de cálculo ORM — excesso de livro-caixa, dependentes, desconto
# simplificado, valor abaixo de R$ 10,00, compensação do exterior.


def test_excesso_de_livro_caixa_carregado_ao_mes_seguinte(cenario):
    empresa = cenario["empresa_a"]
    # Janeiro: R$ 1.000,00 de trabalho não assalariado, R$ 2.500,00 de
    # despesa dedutível — excesso de R$ 1.500,00 sobre a receita do mês.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "1000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2026, 1, 15), "2500.00")
    resultado_jan = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)
    assert resultado_jan["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_jan["excesso_livro_caixa_novo"] == Decimal("1500.00")

    # Fevereiro: mais R$ 1.000,00 de trabalho, sem despesa nova — o excesso
    # de janeiro (R$ 1.500,00) some aplicado contra a receita de fevereiro.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 2, 10), "1000.00")
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=2)
    assert resultado_fev["excesso_livro_caixa_anterior"] == Decimal("1500.00")
    # disponível = 0 (sem despesa nova) + 1500 anterior = 1500; limitado à
    # receita do mês (1000) -> dedução = 1000; excesso novo = 500.
    assert resultado_fev["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_fev["excesso_livro_caixa_novo"] == Decimal("500.00")
    assert resultado_fev["base_de_calculo"] == Decimal("0.00")


def test_excesso_de_dezembro_nao_passa_para_janeiro(cenario):
    # DE-091 item 5 (M-5, correção da rodada 1): dezembro/2025 usa a tabela
    # REAL vigente desde 2025-05-01 (RC-131), SEM redução (legítima
    # ausência, Lei 15.270/2025 só produz efeito a partir de janeiro/2026);
    # janeiro/2026 já tem a redução REAL (2026-01-01). Datas escolhidas
    # para ficarem SEMPRE no passado em relação a "hoje" (RC-77).
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2025, 12, 5), "1000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2025, 12, 10), "3000.00")
    resultado_dez = apurar_carne_leao_mensal(empresa=empresa, ano=2025, mes=12)
    # Disponível = 3000; limitado à receita (1000); dedução = 1000; excesso
    # SERIA 2000, mas dezembro ZERA (art. 69, §1º, RIR/2018) — nunca passa
    # ao ano seguinte.
    assert resultado_dez["deducao_livro_caixa_aplicada"] == Decimal("1000.00")
    assert resultado_dez["excesso_livro_caixa_novo"] == Decimal("0.00")

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 5), "1000.00")
    resultado_jan_2025 = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)
    assert resultado_jan_2025["excesso_livro_caixa_anterior"] == Decimal("0.00")
    # DE-091 item 2 (M-1, correção da rodada 1): sem despesa de livro-caixa
    # em janeiro/2025, a dedução REAL é R$ 0,00 e o desconto simplificado é
    # R$ 607,20 — o desconto simplificado é MAIOR, então vence pelo novo
    # critério (maior dedução, antes da redução), mesmo os DOIS produzindo
    # imposto ZERO depois da redução (a versão anterior comparava só o
    # imposto final e, no empate, ficava com "real" — achado M-1 da
    # auditoria da rodada 1; os dois testes que fixavam esse desempate
    # foram corrigidos, este é um deles).
    assert resultado_jan_2025["forma_escolhida"] == "simplificado"
    assert resultado_jan_2025["base_de_calculo"] == Decimal("392.80")  # 1000,00 − 607,20
    assert resultado_jan_2025["imposto_apos_reducao"] == Decimal("0.00")
    assert resultado_jan_2025["criterio_escolha_forma"] == (
        "Aplicada a forma com maior dedução: desconto simplificado "
        "(R$ 607,20) contra deduções reais (R$ 0,00)."
    )


def test_dependentes_reduzem_a_base(cenario):
    empresa = cenario["empresa_a"]
    # DE-091 item 2 (M-1, correção da rodada 1): a forma é escolhida pela
    # MAIOR DEDUÇÃO — com só 2 dependentes (R$ 379,18) a dedução real seria
    # MENOR que o desconto simplificado (R$ 607,20) e o simplificado
    # venceria, mascarando o efeito da dedução de dependentes na BASE. Com
    # 4 dependentes (R$ 758,36 > R$ 607,20), a dedução real continua sendo
    # a MAIOR, e o teste continua provando o que se propõe: dependentes
    # reduzem a base quando a forma real é a escolhida.
    registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=4, competencia_inicio=date(2026, 1, 1)
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    # 4 dependentes × R$ 189,59 = R$ 758,36.
    assert resultado["dependentes_valor"] == Decimal("758.36")
    assert resultado["forma_escolhida"] == "real"
    assert resultado["base_de_calculo"] == Decimal("2241.64")  # 3000,00 - 758,36


def test_dependentes_vigencia_mensal_nao_retroage(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 2, 10), "3000.00")
    registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=1, competencia_inicio=date(2026, 3, 1)
    )
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=2)
    assert resultado_fev["dependentes_quantidade"] == 0


def test_aud_a11_dependentes_valem_desde_o_proprio_mes_de_vigencia(cenario):
    """A11 (auditoria, mutante "dependentes entram um mês depois"): uma
    vigência com `competencia_inicio` no PRÓPRIO mês pedido já vale NAQUELE
    mês — nunca só a partir do mês seguinte."""
    empresa = cenario["empresa_a"]
    registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=2, competencia_inicio=date(2026, 3, 1)
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "1000.00")
    resultado_marco = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado_marco["dependentes_quantidade"] == 2


def test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais(cenario):
    empresa = cenario["empresa_a"]
    # Sem NENHUMA dedução real, rendimento (bruto) de R$ 6.000,00. RC-133:
    # a redução usa o BRUTO nas duas formas (mesmo valor, R$ 6.000,00):
    # - reais: base 6000,00 -> imposto tabela 741,27 -> redução 179,75
    #   (978,62 − 0,133145×6000, bruto) -> imposto após redução 561,52.
    # - simplificado: desconto 25% de 2.428,80 = 607,20 -> base 5.392,80
    #   -> imposto tabela 574,29 -> redução 179,75 (MESMO bruto 6000,00,
    #   não a base 5.392,80) -> imposto após redução 394,54 —
    #   ESTRITAMENTE menor que 561,52: simplificado vence.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 4, 10), "6000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=4)
    assert resultado["desconto_simplificado"] == Decimal("607.20")
    assert resultado["memoria_deducoes_reais"]["reducao_aplicada"] == Decimal("179.75")
    assert resultado["memoria_deducoes_reais"]["imposto_apos_reducao"] == Decimal("561.52")
    assert resultado["memoria_desconto_simplificado"]["reducao_aplicada"] == Decimal("179.75")
    assert resultado["memoria_desconto_simplificado"]["imposto_apos_reducao"] == Decimal("394.54")
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["base_de_calculo"] == Decimal("5392.80")  # 6000 - 607.20
    assert resultado["imposto_apos_reducao"] == Decimal("394.54")


def test_deducoes_reais_mais_beneficio_quando_maiores_que_o_simplificado(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 5, 10), "3000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2026, 5, 12), "2000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=5)
    assert resultado["deducoes_reais_total"] == Decimal("2000.00")
    assert resultado["forma_escolhida"] == "real"
    assert resultado["base_de_calculo"] == Decimal("1000.00")  # 3000 - 2000, melhor que 3000-607.20


def test_valor_abaixo_de_dez_reais_acumula_para_o_mes_seguinte(cenario):
    empresa = cenario["empresa_a"]
    # Rendimento pequeno todo mês: base pequena o bastante para o imposto
    # devido, mês a mês, ficar abaixo de R$ 10,00.
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "2826.70")
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 2, 10), "2826.70")
    resultado_jan = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=2)
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
    # imposto após redução é R$ 394,54 (mesmo cálculo de
    # `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`,
    # RC-133: redução pelo BRUTO). O limite de compensação do exterior
    # (Q267, P&R IRPF 2026) é essa diferença inteira (394,54 − 0,00); o
    # crédito de R$ 50,00 pago no exterior cabe dentro do limite e
    # compensa integralmente.
    lancamento_exterior = criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_aluguel"],
        data=date(2026, 6, 10),
        valor="6000.00",
        historico="Aluguel do exterior",
        recebido_de=OrigemRecebimento.EX,
    )
    assert lancamento_exterior.recebido_de == "EX"
    _lancar_despesa(
        empresa,
        cenario["conta_imposto_exterior"],
        date(2026, 6, 10),
        "50.00",
        "Imposto pago no exterior",
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=6)
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
        data=date(2026, 7, 10),
        valor="5000.00",
        historico="Honorários de pessoa jurídica",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador="11222333000181",
    )
    assert lancamento.recebido_de == "PJ"
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=7)
    assert resultado["rendimento_total_sujeito"] == Decimal("0.00")


def test_pensao_alimenticia_recebida_e_imune_ao_carne_leao(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=date(2026, 7, 15),
        valor="2000.00",
        historico="Pensão alimentícia recebida",
        recebido_de=OrigemRecebimento.PF,
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=7)
    assert resultado["rendimento_total_sujeito"] == Decimal("0.00")


def test_rendimento_notarial_de_pessoa_juridica_entra_na_base(cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_notarial"],
        data=date(2026, 8, 10),
        valor="4000.00",
        historico="Emolumentos pagos por pessoa jurídica",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador="11222333000181",
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=8)
    assert resultado["rendimento_total_sujeito"] == Decimal("4000.00")


# ---------------------------------------------------------------------------
# 3. Troca de vigência no meio do ano (critério 2 do plano).


def _criar_vigencia_tabela_diferente(vigencia_inicio):
    vigencia = VigenciaTabelaProgressivaCarneLeao.objects.create(
        vigencia_inicio=vigencia_inicio,
        fonte="Vigência sintética de teste (critério 2).",
        percentual_desconto_simplificado=Decimal("0.25"),
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
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "5000.00")
    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)

    _criar_vigencia_tabela_diferente(date(2026, 6, 1))

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado_depois == resultado_antes
    # Março/2026 usa a tabela REAL vigente desde 2025-05-01 (RC-131,
    # "mantida em 2026") — não há vigência SINTÉTICA de teste nesta fatia
    # (DE-091 item 5/M-5): as vigências REAIS já bastam.
    assert resultado_depois["tabela_vigencia_inicio"] == date(2025, 5, 1)

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 6, 10), "5000.00")
    resultado_junho = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=6)
    assert resultado_junho["tabela_vigencia_inicio"] == date(2026, 6, 1)
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
        empresa, cenario["conta_despesa_dedutivel"], date(2026, 1, 10), "2000.00"
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "500.00")

    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado_antes["excesso_livro_caixa_anterior"] == Decimal("2000.00")

    # Correção rastreável: o mês original (janeiro) é REABERTO por
    # ESTORNO — nunca edição silenciosa (RC-130/AGENTS.md §10).
    estornar_lancamento_caixa(despesa, data=date(2026, 1, 20))

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado_depois["excesso_livro_caixa_anterior"] == Decimal("0.00")
    assert resultado_depois != resultado_antes


# ---------------------------------------------------------------------------
# 5. Isolamento, autorização e modo de escrituração — API.


def test_api_carne_leao_mensal_recusa_empresa_de_outro_escritorio(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-a")
    client.login(username="admin-a", password="senha-forte-123")
    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_b"].id})
    resposta = client.get(url, {"ano": "2026", "mes": "3"})
    assert resposta.status_code == 404


def test_api_carne_leao_mensal_recusa_empresa_em_modo_contabilidade(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-b")
    client.login(username="admin-b", password="senha-forte-123")
    url = reverse(
        "livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_contabilidade"].id}
    )
    resposta = client.get(url, {"ano": "2026", "mes": "3"})
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
    resposta = client.get(url, {"ano": "2026", "mes": "3"})
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
    _lancar_trabalho(empresa_c, conta_c, date(2026, 3, 10), "9000.00")
    _lancar_trabalho(cenario["empresa_a"], cenario["conta_trabalho"], date(2026, 3, 10), "500.00")

    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": cenario["empresa_a"].id})
    resposta = client.get(url, {"ano": "2026", "mes": "3"})
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
        data=json.dumps({"quantidade": 3, "competencia_inicio": "2026-01-01"}),
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
        data=json.dumps({"quantidade": 1, "competencia_inicio": "2026-01-01"}),
        content_type="application/json",
    )
    assert resposta.status_code == 400


def test_servico_dependentes_recusa_modo_contabilidade(cenario):
    with pytest.raises(DependentesCarneLeaoInvalido):
        registrar_dependentes_carne_leao(
            empresa=cenario["empresa_contabilidade"],
            quantidade=1,
            competencia_inicio=date(2026, 1, 1),
        )


def test_modelo_dependentes_recusa_competencia_fora_do_primeiro_dia(cenario):
    registro = DependentesCarneLeaoCliente(
        empresa=cenario["empresa_a"], quantidade=1, competencia_inicio=date(2026, 1, 15)
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
        apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)


def test_apuracao_le_valor_do_banco_nao_de_constante(cenario):
    """Muda um valor normativo SÓ NO BANCO (nunca no código) e confirma que
    o resultado muda — se o motor lesse de uma constante Python, esta
    alteração via ORM não teria efeito nenhum.

    Cenário: rendimento (bruto) de R$ 4.800,00, sem outras deduções. Como
    R$ 4.800,00 > R$ 5.000,00 é falso (está dentro da faixa PLENA da
    redução) mas o imposto pela tabela nesta faixa (R$ 411,27) é MAIOR que
    a redução máxima vigente (R$ 312,89), a redução das deduções REAIS
    fica LIMITADA a R$ 312,89 — mudar esse valor no banco muda
    `memoria_deducoes_reais.reducao_aplicada`. (A forma ESCOLHIDA no fim
    continua sendo a simplificada, que já zera o devido nesta faixa — RC-133
    — por isso a asserção mira a MEMÓRIA de cálculo, uma linha que a API
    expõe de qualquer forma, não o campo do topo que reflete só a forma
    vencedora.)
    """
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 9, 10), "4800.00")
    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=9)
    assert resultado_antes["memoria_deducoes_reais"]["imposto_tabela"] == Decimal("411.27")
    assert resultado_antes["memoria_deducoes_reais"]["reducao_aplicada"] == Decimal("312.89")

    VigenciaReducaoCarneLeao.objects.filter(vigencia_inicio=date(2026, 1, 1)).update(
        reducao_maxima=Decimal("999.99")
    )

    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=9)
    assert resultado_depois["memoria_deducoes_reais"]["reducao_aplicada"] == Decimal("411.27")
    assert (
        resultado_depois["memoria_deducoes_reais"]["reducao_aplicada"]
        != resultado_antes["memoria_deducoes_reais"]["reducao_aplicada"]
    )


def test_apuracao_anual_devolve_os_12_meses(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "1000.00")
    resultado = apurar_carne_leao_anual(empresa=empresa, ano=2026)
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


# ---------------------------------------------------------------------------
# 7. Correção da rodada 1 da auditoria da fatia 2 (DE-091) — casos
# propostos pelo `auditor-qa` (docs/auditorias/2026-09-27-dl-046-fatia2-
# rodada-1.md, seção 5) e os demais itens da decisão. Datas em 2025/2026
# (nunca no futuro em relação a "hoje", RC-77); as vigências normativas
# usadas são as REAIS (migrações 0004/0006), nunca sintéticas.


def _lancar_notarial_pf(empresa, conta, data, valor):
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=data,
        valor=valor,
        historico="Emolumentos",
        recebido_de=OrigemRecebimento.PF,
        cpf_titular_pagamento="11144477735",
    )


def _lancar_trabalho_pj(empresa, conta, data, valor):
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=data,
        valor=valor,
        historico="Honorários de pessoa jurídica",
        recebido_de=OrigemRecebimento.PJ,
        cnpj_pagador="11222333000181",
    )


def test_aud_a1_notarial_livro_caixa(cenario):
    """A-1 (ALTO, corrigido): o limite do livro-caixa soma a receita
    NOTARIAL, não só a de trabalho não assalariado (P&R 427: "inclusive os
    titulares de serviços notariais e de registro"). Caso do relatório:
    notarial PF 20.000,00 + P10 12.000,00, jul/2026 → imposto 1.291,27
    (base 8.000,00; 8.000×0,275−908,73=1.291,27, sem redução por bruto >
    7.350)."""
    empresa = cenario["empresa_a"]
    _lancar_notarial_pf(empresa, cenario["conta_notarial"], date(2026, 7, 10), "20000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2026, 7, 15), "12000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=7)
    assert resultado["deducao_livro_caixa_aplicada"] == Decimal("12000.00")
    assert resultado["excesso_livro_caixa_novo"] == Decimal("0.00")
    assert resultado["imposto_devido_no_mes"] == Decimal("1291.27")


def test_aud_a2_pj_no_limite_do_livro_caixa(cenario):
    """A-2 (ALTO, corrigido): receita de trabalho recebida de PJ NÃO
    integra a base (RC-132), mas integra o LIMITE do livro-caixa (P&R 428:
    "limitado ao valor da receita mensal recebida de pessoa física OU
    JURÍDICA"). Caso do relatório: jan trabalho PJ 10.000 + P10 3.000 (sem
    excesso, pois o limite de 10.000 cobre a despesa inteira, mas SEM
    dedução real — a base do PJ não existe); fev trabalho PF 6.000, sem
    despesa nova → simplificado, imposto 394,54 (mesmo cálculo de
    `test_desconto_simplificado_mais_beneficio_quando_sem_deducoes_reais`,
    com redução ativa em 2026)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho_pj(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "10000.00")
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2026, 1, 15), "3000.00")
    resultado_jan = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)
    # O limite (10.000, PJ incluído) cobre a despesa (3.000) inteira — sem
    # excesso — mas a BASE (rendimento sujeito) é 0,00 (PJ fora da base),
    # então a dedução real aplicada também é 0,00 (min contra a base).
    assert resultado_jan["deducao_livro_caixa_aplicada"] == Decimal("0.00")
    assert resultado_jan["excesso_livro_caixa_novo"] == Decimal("0.00")

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 2, 10), "6000.00")
    resultado_fev = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=2)
    assert resultado_fev["imposto_devido_no_mes"] == Decimal("394.54")


def test_aud_a6_aluguel_nao_entra_no_limite_do_livro_caixa(cenario):
    """A6 (mutante que sobreviveu à auditoria): aluguel (`R01.003.001`) NÃO
    é receita de ATIVIDADE (trabalho/notarial) — não integra o limite do
    livro-caixa. Aluguel PF 5.000,00 + P10 3.000,00 → dedução 0,00 (limite
    de atividade é 0,00, já que não há trabalho nem notarial no mês)."""
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_aluguel"],
        data=date(2026, 7, 10),
        valor="5000.00",
        historico="Aluguel recebido",
        recebido_de=OrigemRecebimento.PF,
    )
    _lancar_despesa(empresa, cenario["conta_despesa_dedutivel"], date(2026, 7, 15), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=7)
    assert resultado["deducao_livro_caixa_aplicada"] == Decimal("0.00")
    assert resultado["excesso_livro_caixa_novo"] == Decimal("3000.00")


# ---------------------------------------------------------------------------
# 8. M-1 — forma escolhida pela MAIOR DEDUÇÃO, via ORM/API (sem `min()` no
# teste), com os Exemplos 1 e 2 oficiais da Receita.


def test_aud_exemplo1_forma_escolhida_via_orm(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "3036.00")
    _lancar_despesa(empresa, cenario["conta_previdencia"], date(2026, 1, 10), "257.73")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=1)
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["base_de_calculo"] == Decimal("2428.80")
    assert resultado["imposto_apos_reducao"] == Decimal("0.00")
    assert resultado["criterio_escolha_forma"] == (
        "Aplicada a forma com maior dedução: desconto simplificado "
        "(R$ 607,20) contra deduções reais (R$ 257,73)."
    )


def test_aud_exemplo2_forma_escolhida_via_orm(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 2, 10), "4000.00")
    _lancar_despesa(empresa, cenario["conta_previdencia"], date(2026, 2, 10), "373.41")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=2)
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["base_de_calculo"] == Decimal("3392.80")
    assert resultado["imposto_pela_tabela"] == Decimal("114.76")
    assert resultado["imposto_apos_reducao"] == Decimal("0.00")


def test_aud_criterio_escolha_forma_no_empate(faixas, reducao_cfg):
    """Acréscimo do arquiteto-senior ao item 7: o texto de
    `criterio_escolha_forma` MUDA com a forma escolhida — e no empate exato
    entre as duas deduções, o texto é o de empate (nunca o de "maior
    dedução"), com o simplificado vencendo (DE-091 item 2)."""
    agregados = _agregados_do_mes([])
    # Sem nenhuma dedução real (deducoes_reais_total == 0,00) e sem nenhum
    # rendimento (desconto_simplificado também cai a 0,00 só se
    # `rendimento_total` for 0 e a base ficar negativa não muda o VALOR do
    # desconto, que é fixo pela faixa) — para um empate REAL, zeramos as
    # duas deduções: chamando `_apurar_um_mes` com `faixas` cuja faixa
    # zero tenha `limite_superior` tal que 25% dela seja exatamente 0,00
    # não é prático; em vez disso, forçamos uma dedução REAL artificial
    # (previdência) igual ao desconto simplificado (607,20).
    agregados_com_previdencia = dict(agregados)
    agregados_com_previdencia["previdencia_oficial"] = Decimal("607.20")
    resultado = _apurar_um_mes(
        ano=2026,
        mes=3,
        agregados=agregados_com_previdencia,
        quantidade_dependentes=0,
        valor_por_dependente=Decimal("189.59"),
        faixas=faixas,
        reducao_cfg=reducao_cfg,
        percentual_desconto_simplificado=Decimal("0.25"),
        vigencia_tabela_inicio=date(2025, 5, 1),
        excesso_livro_caixa_anterior=Decimal("0.00"),
        saldo_credito_exterior_anterior=Decimal("0.00"),
        saldo_pendente_abaixo_de_dez_anterior=Decimal("0.00"),
    )
    assert resultado["deducoes_reais_total"] == Decimal("607.20")
    assert resultado["desconto_simplificado"] == Decimal("607.20")
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["criterio_escolha_forma"] == (
        "Deduções iguais: aplicado o desconto simplificado, que dispensa comprovação."
    )


# ---------------------------------------------------------------------------
# 9. M-3/HI-38 — compensação do imposto pago no exterior (leitura literal)
# e recusa por imposto exterior sem rendimento exterior no mês.


def test_aud_exterior_limite(cenario):
    """`exterior_limite` (seção 5 da auditoria): EX 3.000 + PF 6.000,
    imposto pago no exterior 1.200,00 → limite 1.004,75 (diferença entre o
    imposto COM e SEM o rendimento do exterior); devido 394,54; saldo do
    crédito do exterior NOVO = 0,00 (DE-091 item 3 — instrução explícita do
    arquiteto-senior: "saldo 0,00 quando o excedente é acima do limite" —
    a parte que passa do limite, 195,25, nunca compensa nem carrega, é
    simplesmente perdida para o carnê-leão)."""
    empresa = cenario["empresa_a"]
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_aluguel"],
        data=date(2026, 4, 10),
        valor="3000.00",
        historico="Aluguel do exterior",
        recebido_de=OrigemRecebimento.EX,
    )
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 4, 10), "6000.00")
    _lancar_despesa(
        empresa,
        cenario["conta_imposto_exterior"],
        date(2026, 4, 10),
        "1200.00",
        "Imposto pago no exterior",
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=4)
    assert resultado["limite_compensacao_exterior"] == Decimal("1004.75")
    assert resultado["imposto_devido_no_mes"] == Decimal("394.54")
    assert resultado["compensacao_exterior_aplicada"] == Decimal("1004.75")
    assert resultado["saldo_credito_exterior_novo"] == Decimal("0.00")
    assert resultado["imposto_com_exterior"] == Decimal("1399.29")
    assert resultado["imposto_sem_exterior"] == Decimal("394.54")


def test_aud_a14_saldo_exterior_zera_em_dezembro(faixas, reducao_cfg):
    """A14: o saldo de crédito do exterior de DEZEMBRO nunca passa a
    janeiro (mesma regra do excesso de livro-caixa, HI-37/art. 69 § 1º
    aplicado por analogia ao exterior, P&R 267 "Atenção").

    ⚠️ Achado da correção: sob a definição LITERAL do limite (a diferença
    entre o imposto COM e SEM o rendimento do exterior — P&R 267), o
    crédito disponível de QUALQUER mês nunca EXCEDE o imposto daquele mês
    (a diferença nunca é maior que o imposto "com"), então a apuração
    real NUNCA produz naturalmente um saldo residual para testar a virada
    do ano — o teste força um `saldo_credito_exterior_anterior` ARTIFICIAL
    (nunca produzido pela apuração de verdade) para provar que a linha
    defensiva `if mes == 12: ... = _ZERO` está lá e funciona, caso a
    fórmula mude no futuro."""
    resultado = _apurar_um_mes(
        ano=2026,
        mes=12,
        agregados=_agregados_do_mes([]),
        quantidade_dependentes=0,
        valor_por_dependente=Decimal("189.59"),
        faixas=faixas,
        reducao_cfg=reducao_cfg,
        percentual_desconto_simplificado=Decimal("0.25"),
        vigencia_tabela_inicio=date(2025, 5, 1),
        excesso_livro_caixa_anterior=Decimal("0.00"),
        saldo_credito_exterior_anterior=Decimal("500.00"),
        saldo_pendente_abaixo_de_dez_anterior=Decimal("0.00"),
    )
    assert resultado["saldo_credito_exterior_novo"] == Decimal("0.00")


def test_aud_hi38_imposto_exterior_sem_rendimento_exterior_e_recusado(cenario):
    """HI-38: imposto pago no exterior lançado num mês SEM nenhum
    rendimento sujeito de fonte no exterior → apuração recusa o mês
    inteiro com mensagem clara (decisão: recusa na APURAÇÃO, não na
    gravação do lançamento — ver o docstring de
    `ImpostoExteriorSemRendimentoExterior`)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 5, 10), "3000.00")
    _lancar_despesa(
        empresa,
        cenario["conta_imposto_exterior"],
        date(2026, 5, 10),
        "50.00",
        "Imposto pago no exterior sem rendimento do exterior",
    )
    with pytest.raises(ImpostoExteriorSemRendimentoExterior):
        apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=5)


def test_aud_api_recusa_mes_com_imposto_exterior_sem_rendimento(client, cenario):
    empresa = cenario["empresa_a"]
    _lancar_despesa(
        empresa,
        cenario["conta_imposto_exterior"],
        date(2026, 5, 10),
        "50.00",
        "Imposto pago no exterior sem rendimento do exterior",
    )
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-hi38")
    client.login(username="admin-hi38", password="senha-forte-123")
    url = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": empresa.id})
    resposta = client.get(url, {"ano": "2026", "mes": "5"})
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# 10. M-4 — alerta de rendimento líquido negativo.


def test_aud_m4_alerta_rendimento_liquido_negativo(cenario):
    """Dedução (real ou simplificada) maior que o rendimento sujeito do
    mês → alerta explícito na resposta (a base de cálculo já zera, mas o
    alerta avisa a tela)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 6, 10), "400.00")
    _lancar_despesa(empresa, cenario["conta_previdencia"], date(2026, 6, 10), "1200.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=6)
    assert resultado["base_de_calculo"] == Decimal("0.00")
    assert len(resultado["alertas"]) >= 1
    assert any("negativo" in alerta for alerta in resultado["alertas"])


def test_aud_m4_sem_alerta_quando_rendimento_liquido_nao_e_negativo(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 6, 10), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=6)
    assert resultado["alertas"] == []


# ---------------------------------------------------------------------------
# 11. M-5 — jan-abr/2025 (tabela nova) e ano < 2025 fora do escopo.


def test_aud_m5_fevereiro_2025_sem_reducao_tabela_jan_abr(cenario):
    """Fevereiro/2025: tabela NOVA (jan-abr/2025, P&R 267) — faixa zero até
    2.259,20; SEM redução (legítima ausência, Lei 15.270/2025 só vale a
    partir de 2026). Trabalho PF 3.000,00, sem outra dedução → simplificado
    (25% × 2.259,20 = 564,80) vence (564,80 > 0,00 real) — base 2.435,20 →
    2.435,20 × 7,5% − 169,44 = 13,20 (cálculo à mão, conferido antes de
    rodar o motor)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2025, 2, 10), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2025, mes=2)
    assert resultado["reducao_vigencia_inicio"] is None
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["desconto_simplificado"] == Decimal("564.80")
    assert resultado["base_de_calculo"] == Decimal("2435.20")
    assert resultado["reducao_lei_15270_2025"] == Decimal("0.00")
    assert resultado["imposto_apos_reducao"] == Decimal("13.20")


def test_aud_m5_junho_2025_tabela_rc131_sem_reducao(cenario):
    """Junho/2025: tabela RC-131 (vigente desde 2025-05-01, "mantida em
    2026") — SEM redução (mesma ausência legítima, ainda antes de 2026).
    Trabalho PF 6.000,00, sem outra dedução → simplificado (25% × 2.428,80
    = 607,20) — base 5.392,80 → 5.392,80 × 27,5% − 908,73 = 574,29 (cálculo
    à mão; SEM a redução de 179,75 que o mesmo cenário tem em 2026 —
    prova de que a ausência de redução em 2025 é real, não um placeholder
    zerado por engano)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2025, 6, 10), "6000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2025, mes=6)
    assert resultado["reducao_vigencia_inicio"] is None
    assert resultado["forma_escolhida"] == "simplificado"
    assert resultado["reducao_lei_15270_2025"] == Decimal("0.00")
    assert resultado["imposto_apos_reducao"] == Decimal("574.29")


def test_aud_m5_ano_anterior_a_2025_e_explicitamente_fora_do_escopo(cenario):
    empresa = cenario["empresa_a"]
    with pytest.raises(TabelaCarneLeaoNaoConfigurada, match="fora do escopo"):
        apurar_carne_leao_mensal(empresa=empresa, ano=2024, mes=12)


# ---------------------------------------------------------------------------
# 12. M-6 — retificação (PATCH) da quantidade de dependentes, com trilha.


def test_aud_m6_retificacao_de_dependentes_com_trilha(cenario):
    from apps.auditoria.models import RegistroAuditoria

    empresa = cenario["empresa_a"]
    registro = registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=2, competencia_inicio=date(2026, 1, 1)
    )
    usuario = _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-retifica")
    retificado = retificar_dependentes_carne_leao(registro, quantidade=5, retificado_por=usuario)
    assert retificado.quantidade == 5
    registro.refresh_from_db()
    assert registro.quantidade == 5

    trilha = RegistroAuditoria.objects.filter(acao="dependentes_carne_leao.retificado").first()
    assert trilha is not None
    assert trilha.detalhes["quantidade_anterior"] == 2
    assert trilha.detalhes["quantidade_nova"] == 5


def test_aud_m6_api_patch_dependentes_sucesso(client, cenario):
    empresa = cenario["empresa_a"]
    registro = registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=1, competencia_inicio=date(2026, 1, 1)
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-patch")
    client.login(username="gestor-patch", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao-retificar",
        kwargs={"empresa_id": empresa.id, "dependente_id": registro.id},
    )
    resposta = client.patch(
        url, data=json.dumps({"quantidade": 3}), content_type="application/json"
    )
    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["quantidade"] == 3


def test_aud_m6_api_patch_dependentes_outro_escritorio_404(client, cenario):
    registro_b = registrar_dependentes_carne_leao(
        empresa=cenario["empresa_b"], quantidade=1, competencia_inicio=date(2026, 1, 1)
    )
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-outro-esc")
    client.login(username="admin-outro-esc", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao-retificar",
        kwargs={"empresa_id": cenario["empresa_a"].id, "dependente_id": registro_b.id},
    )
    resposta = client.patch(
        url, data=json.dumps({"quantidade": 3}), content_type="application/json"
    )
    assert resposta.status_code == 404


def test_aud_m6_api_patch_dependentes_papel_sem_escrita_403(client, cenario):
    empresa = cenario["empresa_a"]
    registro = registrar_dependentes_carne_leao(
        empresa=empresa, quantidade=1, competencia_inicio=date(2026, 1, 1)
    )
    _usuario_com_papel(Papel.PARALEGAL, cenario["escritorio_a"], "paralegal-patch")
    client.login(username="paralegal-patch", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao-retificar",
        kwargs={"empresa_id": empresa.id, "dependente_id": registro.id},
    )
    resposta = client.patch(
        url, data=json.dumps({"quantidade": 3}), content_type="application/json"
    )
    assert resposta.status_code == 403


def test_aud_dependentes_isolados_entre_empresas(cenario):
    """`dependentes_isolados_entre_empresas` (seção 5 da auditoria):
    dependentes registrados em OUTRA empresa não valem para esta."""
    registrar_dependentes_carne_leao(
        empresa=cenario["empresa_b"], quantidade=9, competencia_inicio=date(2026, 1, 1)
    )
    empresa_a = cenario["empresa_a"]
    _lancar_trabalho(empresa_a, cenario["conta_trabalho"], date(2026, 3, 10), "3000.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa_a, ano=2026, mes=3)
    assert resultado["dependentes_quantidade"] == 0


def test_aud_a23_paralegal_nao_pode_criar_dependentes(client, cenario):
    """A23 (auditoria, mutante "POST de dependentes com permissão de
    leitura"): PARALEGAL LÊ o livro-caixa (`PAPEIS_QUE_LEEM_LIVRO_CAIXA`)
    mas não ESCRITURA — o `POST` de dependentes exige `PodeEscriturarLivro
    Caixa`, nunca `PodeLerLivroCaixa`."""
    _usuario_com_papel(Papel.PARALEGAL, cenario["escritorio_a"], "paralegal-dep-post")
    client.login(username="paralegal-dep-post", password="senha-forte-123")
    url = reverse(
        "livro_caixa:dependentes-carne-leao", kwargs={"empresa_id": cenario["empresa_a"].id}
    )
    resposta = client.post(
        url,
        data=json.dumps({"quantidade": 2, "competencia_inicio": "2026-01-01"}),
        content_type="application/json",
    )
    assert resposta.status_code == 403


def test_aud_a19_pensao_paga_deduz(cenario):
    """A19 (auditoria, mutante "pensão paga ignorada"): bruto 8.000,00 com
    pensão alimentícia PAGA 1.500,00 → base 6.500,00 (real vence: 1.500,00
    > 607,20 simplificado); bruto > 7.350,00 → sem redução;
    6.500,00×27,5%−908,73 = 878,77 (cálculo à mão, seção 2 da auditoria)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 5, 10), "8000.00")
    _lancar_despesa(
        empresa, cenario["conta_pensao_paga"], date(2026, 5, 10), "1500.00", "Pensão paga"
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=5)
    assert resultado["forma_escolhida"] == "real"
    assert resultado["base_de_calculo"] == Decimal("6500.00")
    assert resultado["imposto_apos_reducao"] == Decimal("878.77")


def test_aud_exatamente_dez_reais_paga(cenario):
    """`exatamente_dez_reais_paga` (seção 5 da auditoria): bruto 7.400,00,
    previdência 4.837,87 → base 2.562,13 × 7,5% − 182,16 = 9,99975 → 10,00
    (MEIO_PARA_CIMA) — paga (não acumula, A10: `<` na fronteira de R$
    10,00, nunca `<=`)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 6, 10), "7400.00")
    _lancar_despesa(
        empresa, cenario["conta_previdencia"], date(2026, 6, 10), "4837.87", "Previdência"
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=6)
    assert resultado["imposto_devido_no_mes"] == Decimal("10.00")
    assert resultado["valor_a_pagar"] == Decimal("10.00")
    assert resultado["saldo_pendente_abaixo_de_dez_novo"] == Decimal("0.00")


def test_aud_lancamento_no_ultimo_dia_do_mes(cenario):
    """`lancamento_no_ultimo_dia_do_mes` (seção 5 da auditoria; A13):
    lançamento de 31/03 precisa ENTRAR na apuração de março — R$ 5.100,00
    sem outra dedução → simplificado (607,20) → base 4.492,80 → imposto
    335,39, redução 299,58 → devido 35,81 (cálculo à mão)."""
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 31), "5100.00")
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado["imposto_apos_reducao"] == Decimal("35.81")


# ---------------------------------------------------------------------------
# 13. M-2/B-6 — contrato da API: rendimentos por (código, origem),
# imposto com/sem exterior, vencimento, alertas e totais anuais exatos.


def test_aud_m2_rendimentos_por_codigo_e_origem(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 8, 10), "2000.00")
    _lancar_trabalho_pj(empresa, cenario["conta_trabalho"], date(2026, 8, 11), "1000.00")
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_pensao_recebida"],
        data=date(2026, 8, 12),
        valor="500.00",
        historico="Pensão recebida",
        recebido_de=OrigemRecebimento.PF,
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=8)
    rendimentos = {(item["codigo"], item["origem"]): item for item in resultado["rendimentos"]}

    trabalho_pf = rendimentos[("R01.001.001", "PF")]
    assert trabalho_pf["valor"] == Decimal("2000.00")
    assert trabalho_pf["entra_na_base"] is True
    assert trabalho_pf["motivo_exclusao"] is None

    trabalho_pj = rendimentos[("R01.001.001", "PJ")]
    assert trabalho_pj["valor"] == Decimal("1000.00")
    assert trabalho_pj["entra_na_base"] is False
    assert trabalho_pj["motivo_exclusao"] is not None

    pensao = rendimentos[("R01.002.001", "PF")]
    assert pensao["valor"] == Decimal("500.00")
    assert pensao["entra_na_base"] is False
    assert "imune" in pensao["motivo_exclusao"].lower()


def test_aud_m2_vencimento_ultimo_dia_util_do_mes_seguinte(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "1000.00")
    resultado_marco = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    assert resultado_marco["vencimento"] == "último dia útil de 04/2026"

    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2025, 12, 10), "1000.00")
    resultado_dezembro = apurar_carne_leao_mensal(empresa=empresa, ano=2025, mes=12)
    assert resultado_dezembro["vencimento"] == "último dia útil de 01/2026"


def test_aud_m2_imposto_com_e_sem_exterior_no_mensal(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 4, 10), "6000.00")
    criar_lancamento_caixa(
        empresa=empresa,
        conta=cenario["conta_aluguel"],
        data=date(2026, 4, 10),
        valor="3000.00",
        historico="Aluguel do exterior",
        recebido_de=OrigemRecebimento.EX,
    )
    resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=4)
    assert resultado["imposto_com_exterior"] == Decimal("1399.29")
    assert resultado["imposto_sem_exterior"] == Decimal("394.54")


def test_aud_m2_totais_anuais_sao_a_soma_exata_dos_12_meses(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 1, 10), "3000.00")
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 6, 10), "6000.00")
    resultado = apurar_carne_leao_anual(empresa=empresa, ano=2026)

    def _campo_do_mes(mes_resultado, campo_anual):
        if campo_anual == "deducoes_aplicadas":
            if mes_resultado["forma_escolhida"] == "simplificado":
                return mes_resultado["desconto_simplificado"]
            return mes_resultado["deducoes_reais_total"]
        mapa = {
            "rendimento_bruto": "rendimento_total_sujeito",
            "base": "base_de_calculo",
            "imposto_tabela": "imposto_pela_tabela",
            "reducao_aplicada": "reducao_lei_15270_2025",
            "compensacao_exterior": "compensacao_exterior_aplicada",
            "imposto_devido": "imposto_devido_no_mes",
            "valor_a_pagar": "valor_a_pagar",
        }
        return mes_resultado[mapa[campo_anual]]

    for campo_anual in (
        "rendimento_bruto",
        "deducoes_aplicadas",
        "base",
        "imposto_tabela",
        "reducao_aplicada",
        "compensacao_exterior",
        "imposto_devido",
        "valor_a_pagar",
    ):
        soma_esperada = sum(
            (_campo_do_mes(mes, campo_anual) for mes in resultado["meses"]), Decimal("0.00")
        )
        assert resultado["totais"][campo_anual] == soma_esperada, campo_anual


# ---------------------------------------------------------------------------
# 14. Acréscimo do arquiteto-senior ao item 7 — `faixa_aplicada` e
# `vigencia_tabela_inicio` em cada memória de cálculo.


def test_aud_faixa_aplicada_e_vigencia_em_cada_memoria(cenario):
    """Cada faixa da tabela real (2025-05-01), testada por um bruto no
    MEIO dela — a memória de cálculo (deduções reais, sem nenhuma dedução
    real de propósito, para a base bater com o bruto) devolve a faixa
    exatamente como está no banco."""
    casos = [
        # (bruto, ordem, limite_inferior, limite_superior, aliquota, parcela)
        (
            Decimal("2000.00"),
            1,
            Decimal("0.00"),
            Decimal("2428.80"),
            Decimal("0.0000"),
            Decimal("0.00"),
        ),
        (
            Decimal("2600.00"),
            2,
            Decimal("2428.81"),
            Decimal("2826.65"),
            Decimal("0.0750"),
            Decimal("182.16"),
        ),
        (
            Decimal("3300.00"),
            3,
            Decimal("2826.66"),
            Decimal("3751.05"),
            Decimal("0.1500"),
            Decimal("394.16"),
        ),
        (
            Decimal("4200.00"),
            4,
            Decimal("3751.06"),
            Decimal("4664.68"),
            Decimal("0.2250"),
            Decimal("675.49"),
        ),
        (Decimal("5500.00"), 5, Decimal("4664.69"), None, Decimal("0.2750"), Decimal("908.73")),
    ]
    for indice, (bruto, _ordem, limite_inferior, limite_superior, aliquota, parcela) in enumerate(
        casos
    ):
        escritorio = Escritorio.objects.create(
            nome=f"Escritório faixa {indice}", cnpj=f"{indice + 1:014d}"
        )
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social=f"Autônomo faixa {indice}",
            tipo_inscricao=TipoInscricao.CPF,
            cpf="12345678909",
            modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
        )
        conta = ContaLivroCaixa.objects.create(
            empresa=empresa,
            codigo="RT",
            nome="Trabalho não assalariado",
            natureza=NaturezaCaixa.RECEITA,
            codigo_carne_leao="R01.001.001",
        )
        _lancar_trabalho(empresa, conta, date(2026, 9, 10), str(bruto))
        resultado = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=9)
        memoria = resultado["memoria_deducoes_reais"]
        assert memoria["vigencia_tabela_inicio"] == date(2025, 5, 1)
        faixa = memoria["faixa_aplicada"]
        assert faixa["limite_inferior"] == limite_inferior
        assert faixa["limite_superior"] == limite_superior
        assert faixa["aliquota"] == aliquota
        assert faixa["parcela_a_deduzir"] == parcela


# ---------------------------------------------------------------------------
# 15. B-1 — percentual do desconto simplificado vem do BANCO.


def test_aud_b1_percentual_simplificado_muda_so_no_banco(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 9, 10), "1000.00")
    resultado_antes = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=9)
    assert resultado_antes["desconto_simplificado"] == Decimal("607.20")

    VigenciaTabelaProgressivaCarneLeao.objects.filter(vigencia_inicio=date(2025, 5, 1)).update(
        percentual_desconto_simplificado=Decimal("0.10")
    )
    resultado_depois = apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=9)
    assert resultado_depois["desconto_simplificado"] == Decimal("242.88")  # 2428,80 × 0,10
    assert resultado_depois["desconto_simplificado"] != resultado_antes["desconto_simplificado"]


# ---------------------------------------------------------------------------
# 16. Snapshot (transaction=True) e API — permissões e isolamento restantes.


@pytest.mark.django_db(transaction=True)
def test_aud_snapshot_usa_repeatable_read(cenario):
    empresa = cenario["empresa_a"]
    _lancar_trabalho(empresa, cenario["conta_trabalho"], date(2026, 3, 10), "1000.00")
    with CaptureQueriesContext(connection) as capturado:
        apurar_carne_leao_mensal(empresa=empresa, ano=2026, mes=3)
    sqls = [item["sql"] for item in capturado.captured_queries]
    assert any("REPEATABLE READ" in sql for sql in sqls)


def test_aud_api_cliente_recusado_no_mensal_e_no_anual(client, cenario):
    _usuario_com_papel(Papel.CLIENTE, cenario["escritorio_a"], "cliente-carne")
    client.login(username="cliente-carne", password="senha-forte-123")
    empresa = cenario["empresa_a"]

    url_mensal = reverse("livro_caixa:carne-leao-mensal", kwargs={"empresa_id": empresa.id})
    resposta_mensal = client.get(url_mensal, {"ano": "2026", "mes": "3"})
    assert resposta_mensal.status_code == 403

    url_anual = reverse("livro_caixa:carne-leao-anual", kwargs={"empresa_id": empresa.id})
    resposta_anual = client.get(url_anual, {"ano": "2026"})
    assert resposta_anual.status_code == 403


def test_aud_api_anual_recusa_empresa_em_modo_contabilidade(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor-anual-contab")
    client.login(username="gestor-anual-contab", password="senha-forte-123")
    url = reverse(
        "livro_caixa:carne-leao-anual",
        kwargs={"empresa_id": cenario["empresa_contabilidade"].id},
    )
    resposta = client.get(url, {"ano": "2026"})
    assert resposta.status_code == 400


def test_aud_api_anual_recusa_empresa_de_outro_escritorio(client, cenario):
    _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio_a"], "admin-anual-outro")
    client.login(username="admin-anual-outro", password="senha-forte-123")
    url = reverse("livro_caixa:carne-leao-anual", kwargs={"empresa_id": cenario["empresa_b"].id})
    resposta = client.get(url, {"ano": "2026"})
    assert resposta.status_code == 404
