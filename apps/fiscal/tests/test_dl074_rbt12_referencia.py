"""DL-074 (frente A) — RBT12 por mercado: casos de referência e regras do art. 22.

Critérios do plano cobertos aqui: 2 (regra geral em casos de referência), 3 (ano de
início: os números da consulta de 08/10/2026), 4 (abertura no ano anterior à opção),
5 (mês sem confirmação → não apurável com a lista; sem abertura → recusa nomeada),
8 (avisos de sublimite, limite e excesso de 20%; limite proporcional), 9 (regime de
caixa em 2026) e 12 (2027 recusado).

REGRA DO TESTE: todo número esperado está escrito LITERAL no teste, calculado à mão
a partir dos valores lançados (e não chamando o código). A conta de cada caso está no
comentário ao lado.

O critério 3 pede também o exemplo do Manual do PGDAS-D (abertura 02/2018). Ele está no
fim deste arquivo, em `test_exemplo_do_manual_abertura_12_02_2018_bate_com_120_mil_e_2_4_milhoes`,
com os números escritos à mão a partir do Manual (item 8.3).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import MercadoReceita, NaturezaOperacao
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    escriturar,
    fixar_hoje,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
    sequencia,
)

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO
EXTERNO = MercadoReceita.EXTERNO


def _lancar_meses(empresa, usuario, pares, mercado=INTERNO):
    """Lança e confirma uma receita por mês de `pares` ((ano, mês), valor).

    Valor zero só confirma o mês (mês sem receita entra como zero e exige confirmação).
    A receita é lançada ANTES da confirmação do mês: lançar depois mudaria um mês
    confirmado, e o mês viraria "a retificar".
    """
    for (ano, mes), valor in pares:
        if Decimal(valor) != 0:
            informar_e_confirmar(empresa, usuario, ano, mes, valor, mercado=mercado)
        confirmar_meses(empresa, usuario, [(ano, mes)])


@pytest.fixture
def empresa_antiga(empresa_a):
    # Empresa aberta em 2015 e optante desde 2018: a regra geral (§ 1º) vale em todo PA de 2026.
    fixar_inicio_de_uso(empresa_a, 2026, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


# ---------------------------------------------------------------------------
# Critério 3 — o exemplo da consulta: abertura 10/03/2026 (ano de início, § 2º e § 3º)
# ---------------------------------------------------------------------------


def test_exemplo_da_consulta_abertura_10_03_2026_bate_com_os_quatro_numeros(
    empresa_a, usuario_gestor_a
):
    # Números da consulta (item 2 e tabela do item 7): RBT12 mar 240.000; abr 240.000;
    # mai 300.000; jun 300.000. Receitas do exemplo: mar 20.000; abr 30.000; mai 25.000.
    # Junho recebe 10.000 só para mostrar que a receita do PRÓPRIO mês não entra na média.
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(
        empresa,
        usuario_gestor_a,
        [((2026, 3), "20000"), ((2026, 4), "30000"), ((2026, 5), "25000"), ((2026, 6), "10000")],
    )

    marco = apuracao.rbt12(empresa, 2026, 3)
    abril = apuracao.rbt12(empresa, 2026, 4)
    maio = apuracao.rbt12(empresa, 2026, 5)
    junho = apuracao.rbt12(empresa, 2026, 6)

    assert marco.regra == "§ 2º"
    assert marco.de(INTERNO).apurado == Decimal("240000")  # 20.000 × 12
    assert abril.regra == "§ 3º"
    assert abril.de(INTERNO).apurado == Decimal("240000")  # média(20.000) × 12
    assert maio.de(INTERNO).apurado == Decimal("300000")  # média(20.000; 30.000) = 25.000 × 12
    assert junho.regra == "§ 3º"
    assert junho.de(INTERNO).apurado == Decimal(
        "300000"
    )  # média(20.000; 30.000; 25.000) = 25.000 × 12


def test_junho_sem_confirmacao_nao_muda_o_rbt12_do_proprio_mes(empresa_a, usuario_gestor_a):
    # O mês do próprio PA não entra na média do § 3º: se não está confirmado, a apuração
    # do PA continua valendo. Só o aviso de limite fica pendente.
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(
        empresa,
        usuario_gestor_a,
        [((2026, 3), "20000"), ((2026, 4), "30000"), ((2026, 5), "25000")],
    )

    junho = apuracao.rbt12(empresa, 2026, 6)

    assert junho.apuravel
    assert junho.de(INTERNO).apurado == Decimal("300000")
    assert junho.pendentes_do_ano == ((2026, 6, "nao_confirmado"),)
    assert [a.codigo for a in junho.avisos] == ["limites_nao_apurados"]


# ---------------------------------------------------------------------------
# Critério 2 — regra geral (§ 1º): três casos de referência com 12 meses
# ---------------------------------------------------------------------------


def test_regra_geral_caso_de_referencia_1_soma_dos_doze_meses(empresa_antiga, usuario_gestor_a):
    # PA jan/2026 → janela jan/2025 a dez/2025 (12 meses).
    # 10.000 + 20.000 + 0 + 5.000 + 15.000 + 25.000 + 30.000 + 0 + 40.000 + 10.000
    #   + 12.345,67 + 7.654,33 = 175.000,00
    valores_2025 = [
        "10000",
        "20000",
        "0",
        "5000",
        "15000",
        "25000",
        "30000",
        "0",
        "40000",
        "10000",
        "12345.67",
        "7654.33",
    ]
    pares = list(zip(sequencia(2025, 1, 12), valores_2025, strict=True)) + [((2026, 1), "0")]
    _lancar_meses(empresa_antiga, usuario_gestor_a, pares)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert resultado.regra == "§ 1º"
    assert resultado.de(INTERNO).apurado == Decimal("175000.00")
    assert len(resultado.janela) == 12


def test_regra_geral_caso_de_referencia_2_janela_com_meses_de_2026(
    empresa_antiga, usuario_gestor_a
):
    # PA jun/2026 → janela jun/2025 a mai/2026.
    # 0 + 30.000 + 0 + 40.000 + 10.000 + 12.345,67 + 7.654,33 + 1.000 + 2.000 + 3.000 + 4.000
    #   + 5.000 = 115.000,00
    valores = [
        ((2025, 6), "0"),
        ((2025, 7), "30000"),
        ((2025, 8), "0"),
        ((2025, 9), "40000"),
        ((2025, 10), "10000"),
        ((2025, 11), "12345.67"),
        ((2025, 12), "7654.33"),
        ((2026, 1), "1000"),
        ((2026, 2), "2000"),
        ((2026, 3), "3000"),
        ((2026, 4), "4000"),
        ((2026, 5), "5000"),
        ((2026, 6), "0"),
    ]
    _lancar_meses(empresa_antiga, usuario_gestor_a, valores)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 6)

    assert resultado.de(INTERNO).apurado == Decimal("115000.00")


def test_regra_geral_caso_de_referencia_3_com_fim_de_ano(
    empresa_antiga, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 12, 31))  # confirma dez/2026: o hoje tem de alcançá-lo
    # PA dez/2026 → janela dez/2025 a nov/2026: 1.000 (dez/2025) + 11 × 10.000 (jan a nov/2026)
    # = 111.000,00. O mês do próprio PA (dez/2026) não entra.
    valores = [((2025, 12), "1000")] + [((2026, mes), "10000") for mes in range(1, 12)]
    valores.append(((2026, 12), "0"))
    _lancar_meses(empresa_antiga, usuario_gestor_a, valores)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 12)

    assert resultado.regra == "§ 1º"
    assert resultado.de(INTERNO).apurado == Decimal("111000.00")


# ---------------------------------------------------------------------------
# Critério 4 — abertura no ano anterior à opção: § 4º até o 12º mês, § 1º no 13º
# ---------------------------------------------------------------------------


def test_abertura_no_ano_anterior_usa_s4_ate_o_12_mes_e_s1_no_13(
    empresa_a, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 12, 31))  # confirma até nov/2026
    # Abertura 15/11/2025 (mês de atividade 1); opção com efeitos desde 01/01/2026.
    # Meses de atividade: nov/25 = 1, dez/25 = 2, jan/26 = 3, ..., out/26 = 12, nov/26 = 13.
    # Receitas: nov/25 10.000; dez/25 20.000; jan/26 70.000; fev/26 20.000;
    #           mar a set/26 30.000 cada (7 meses); out/26 50.000.
    fixar_inicio_de_uso(empresa_a, 2025, 11)
    empresa = preparar_simples(
        empresa_a, abertura=date(2025, 11, 15), inicio_simples=date(2026, 1, 1)
    )
    receitas = {
        (2025, 11): "10000",
        (2025, 12): "20000",
        (2026, 1): "70000",
        (2026, 2): "20000",
        (2026, 10): "50000",
    }
    for ano_mes in sequencia(2026, 3, 7):
        receitas[ano_mes] = "30000"
    pares = [(ano_mes, receitas.get(ano_mes, "0")) for ano_mes in sequencia(2025, 11, 13)]
    _lancar_meses(empresa, usuario_gestor_a, pares)

    # Mês 12 de atividade (out/26): § 4º = média dos meses ANTERIORES (nov/25 a set/26, 11 meses).
    # Soma = 10.000 + 20.000 + 70.000 + 20.000 + 7 × 30.000 = 330.000.
    # Média = 330.000 ÷ 11 = 30.000. × 12 = 360.000.
    decimo_segundo = apuracao.rbt12(empresa, 2026, 10)
    assert decimo_segundo.regra == "§ 4º"
    assert decimo_segundo.de(INTERNO).apurado == Decimal("360000")
    assert decimo_segundo.de(INTERNO).divisor == 11

    # Mês 13 de atividade (nov/26): § 1º = soma dos 12 meses nov/25 a out/26.
    # 330.000 + 50.000 = 380.000.
    decimo_terceiro = apuracao.rbt12(empresa, 2026, 11)
    assert decimo_terceiro.regra == "§ 1º"
    assert decimo_terceiro.de(INTERNO).apurado == Decimal("380000")


# ---------------------------------------------------------------------------
# Critério 1/2 (mercados separados) — exportação tem RBT12 próprio, não soma no interno
# ---------------------------------------------------------------------------


def test_exportacao_tem_rbt12_proprio_e_nao_soma_no_interno(
    empresa_antiga, escritorio_a, usuario_gestor_a
):
    # Janela jan/25 a dez/25. Interno: 3.000 (nov/25, escriturada) + 10.000 (dez/25, informada).
    # Externo: 5.000 (dez/25, exportação escriturada). Esperado: interno 13.000,00 e
    # externo 5.000,00. Nenhum dos dois soma o outro.
    # Ordem: primeiro os lançamentos, depois a confirmação de cada mês (ver _lancar_meses).
    escriturar(
        escritorio_a,
        empresa_antiga,
        usuario_gestor_a,
        sufixo=901,
        competencia=(2025, 11),
        valor="3000",
    )
    informar_e_confirmar(empresa_antiga, usuario_gestor_a, 2025, 12, "10000", mercado=INTERNO)
    escriturar(
        escritorio_a,
        empresa_antiga,
        usuario_gestor_a,
        sufixo=902,
        competencia=(2025, 12),
        valor="5000",
        natureza=NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO,
    )
    confirmar_meses(empresa_antiga, usuario_gestor_a, sequencia(2025, 1, 13))

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert resultado.de(INTERNO).apurado == Decimal("13000.00")
    assert resultado.de(EXTERNO).apurado == Decimal("5000.00")


# ---------------------------------------------------------------------------
# Critério 8 — limites proporcionais e cheios, sublimite, e avisos com o dispositivo
# ---------------------------------------------------------------------------


def test_limite_e_sublimite_proporcionais_de_10_meses_no_ano_de_inicio(empresa_a, usuario_gestor_a):
    # Abertura 10/03/2026: março a dezembro = 10 meses (fração conta como mês inteiro).
    # Limite proporcional: 400.000 × 10 = 4.000.000. Sublimite: 300.000 × 10 = 3.000.000.
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "20000"), ((2026, 4), "30000")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    interno = resultado.de(INTERNO)
    assert resultado.modo_limite == "proporcional (10 meses)"
    assert interno.teto_limite == Decimal("4000000")
    assert interno.teto_sublimite == Decimal("3000000")
    assert resultado.avisos == ()


def test_limites_cheios_fora_do_ano_de_inicio(empresa_antiga, usuario_gestor_a):
    _lancar_meses(empresa_antiga, usuario_gestor_a, [((2026, 1), "0")])

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert resultado.modo_limite == "cheio"
    assert resultado.de(INTERNO).teto_limite == Decimal("4800000")
    assert resultado.de(INTERNO).teto_sublimite == Decimal("3600000")


def test_sublimite_excedido_ate_20_por_cento_gera_aviso_com_dispositivo(
    empresa_a, usuario_gestor_a
):
    # Abertura 10/03/2026 → sublimite proporcional 3.000.000. Receita de março: 3.100.000.
    # Excesso do sublimite: 100.000 / 3.000.000 = 3,33% (até 20%). Limite 4.000.000 não passa.
    # RBT12 de abril = 3.100.000 × 12 = 37.200.000 acima do limite, com o ano ainda dentro (§ 5º).
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "3100000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    codigos = {aviso.codigo for aviso in resultado.avisos}
    assert codigos == {"sublimite_excedido_ate_20", "rbt12_acima_do_limite_ano_dentro"}
    sublimite = next(a for a in resultado.avisos if a.codigo == "sublimite_excedido_ate_20")
    assert sublimite.mercado == INTERNO
    assert "LC 123, art. 3º, §§ 11 e 13" in sublimite.dispositivo
    assert "Res. CGSN 140, art. 12" in sublimite.dispositivo


def test_limite_ate_20_com_sublimite_acima_de_20_gera_os_dois_avisos(empresa_a, usuario_gestor_a):
    # Receita de março 4.500.000 com limite proporcional 4.000.000 e sublimite 3.000.000.
    # Limite: excesso 500.000 / 4.000.000 = 12,5% (até 20%). Sublimite: 1.500.000 / 3.000.000 = 50%.
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "4500000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    codigos = {aviso.codigo for aviso in resultado.avisos}
    assert "limite_excedido_ate_20" in codigos
    assert "sublimite_excedido_acima_20" in codigos
    limite = next(a for a in resultado.avisos if a.codigo == "limite_excedido_ate_20")
    assert "art. 81, II, 'a', 2" in limite.dispositivo


def test_limite_acima_de_20_por_cento_gera_aviso_de_efeito_retroativo(empresa_a, usuario_gestor_a):
    # Receita de março 5.000.000 com limite proporcional 4.000.000: excesso 25% (acima de 20%).
    fixar_inicio_de_uso(empresa_a, 2026, 3)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "5000000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    codigos = {aviso.codigo for aviso in resultado.avisos}
    assert "limite_excedido_acima_20" in codigos
    limite = next(a for a in resultado.avisos if a.codigo == "limite_excedido_acima_20")
    assert "art. 81, II, 'a', 1 e 'b', 1" in limite.dispositivo


def test_rbt12_acima_do_limite_com_o_ano_ainda_dentro_gera_aviso_s5(
    empresa_antiga, usuario_gestor_a, monkeypatch
):
    fixar_hoje(monkeypatch, date(2026, 12, 31))  # confirma dez/2026
    # PA dez/2026, janela dez/2025 a nov/2026:
    # 3.000.000 (dez/25) + 11 × 200.000 = 5.200.000 > 4.800.000.
    # Receita acumulada em 2026 até dez/26: 11 × 200.000 + 100.000 = 2.300.000 ≤ 4.800.000.
    valores = [((2025, 12), "3000000")] + [((2026, m), "200000") for m in range(1, 12)]
    valores.append(((2026, 12), "100000"))
    _lancar_meses(empresa_antiga, usuario_gestor_a, valores)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 12)

    assert resultado.de(INTERNO).apurado == Decimal("5200000.00")
    aviso = next(a for a in resultado.avisos if a.codigo == "rbt12_acima_do_limite_ano_dentro")
    # Dispositivo mudou com a consulta ao contador-senior: § 5º, I e II, com o limite cheio.
    assert aviso.dispositivo == "Res. CGSN 140/2018, art. 22, § 5º, I e II, e art. 2º, § 1º"
    assert not any(a.codigo.startswith("limite_excedido") for a in resultado.avisos)


def test_sem_cadastro_de_sublimite_para_2025_avisa_em_vez_de_inventar(
    empresa_antiga, usuario_gestor_a
):
    # O sublimite está cadastrado só para 2026 (Portaria CGSN 54/2025, HI-70). Em 2025 o
    # aviso diz que não há limite, e o RBT12 sai mesmo assim (ele não depende de limite).
    # PA dez/2025 → janela dez/2024 a nov/2025 com 1.000 por mês = 12.000.
    _lancar_meses(empresa_antiga, usuario_gestor_a, [(m, "1000") for m in sequencia(2024, 12, 13)])

    resultado = apuracao.rbt12(empresa_antiga, 2025, 12)

    assert resultado.de(INTERNO).apurado == Decimal("12000.00")
    assert resultado.de(INTERNO).teto_sublimite is None
    assert "limites_nao_cadastrados" in {a.codigo for a in resultado.avisos}


# ---------------------------------------------------------------------------
# Critério 5 — não apurável com a lista; recusas nomeadas
# ---------------------------------------------------------------------------


def test_mes_da_janela_sem_confirmacao_e_nao_apuravel_e_lista_o_mes(
    empresa_antiga, usuario_gestor_a
):
    # PA jan/2026 precisa de jun/2025 confirmado. Só ele não foi confirmado.
    pares = [(ano_mes, "1000") for ano_mes in sequencia(2025, 1, 12) if ano_mes != (2025, 6)]
    pares.append(((2026, 1), "0"))
    _lancar_meses(empresa_antiga, usuario_gestor_a, pares)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert not resultado.apuravel
    assert resultado.pendentes_da_janela == ((2025, 6, "nao_confirmado"),)
    assert resultado.de(INTERNO).apurado is None
    assert resultado.de(EXTERNO).apurado is None


def test_receita_escriturada_depois_da_confirmacao_deixa_o_mes_a_retificar(
    empresa_antiga, escritorio_a, usuario_gestor_a
):
    # Mês confirmado depois muda por uma escrituração efetivada (sem passar pelo estorno).
    # O mês vira "a retificar" e sai da apuração. Esse é o caso que o gancho do estorno não cobre.
    pares = [(ano_mes, "1000") for ano_mes in sequencia(2025, 1, 12)] + [((2026, 1), "0")]
    _lancar_meses(empresa_antiga, usuario_gestor_a, pares)
    escriturar(
        escritorio_a,
        empresa_antiga,
        usuario_gestor_a,
        sufixo=950,
        competencia=(2025, 3),
        valor="500",
    )

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert resultado.pendentes_da_janela == ((2025, 3, "a_retificar"),)
    assert resultado.de(INTERNO).apurado is None


def test_sem_data_de_abertura_recusa_nomeada(empresa_a):
    empresa = preparar_simples(empresa_a, abertura=None, inicio_simples=date(2018, 1, 1))

    with pytest.raises(apuracao.ApuracaoRecusada, match="data de abertura no CNPJ"):
        apuracao.rbt12(empresa, 2026, 1)


def test_competencia_anterior_a_abertura_e_recusada(empresa_a):
    # Simples desde a abertura (consistente com R4). A recusa é a da competência, que vem
    # antes de procurar o período: fevereiro é anterior à abertura de 10/03/2026.
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )

    with pytest.raises(apuracao.ApuracaoRecusada, match="anterior à abertura"):
        apuracao.rbt12(empresa, 2026, 2)


def test_sem_periodo_do_simples_no_pa_e_recusado(empresa_a):
    # Abertura cadastrada, mas nenhum período do Simples cobre janeiro/2026.
    Empresa.objects.filter(pk=empresa_a.pk).update(data_abertura_cnpj=date(2015, 3, 10))
    empresa_a.refresh_from_db()

    with pytest.raises(apuracao.ApuracaoRecusada, match="período do Simples Nacional"):
        apuracao.rbt12(empresa_a, 2026, 1)


def test_2029_e_recusado_nomeando_a_resolucao_190(empresa_antiga):
    # DL-088: 2027 e 2028 têm limites e a janela defasada (Res. 190). 2029 segue recusado (HI-146).
    with pytest.raises(apuracao.ApuracaoRecusada, match="190/2026"):
        apuracao.rbt12(empresa_antiga, 2029, 1)


# ---------------------------------------------------------------------------
# Critério 9 — regime de caixa em 2026: RBT12 pela competência + aviso
# ---------------------------------------------------------------------------


def test_regime_de_caixa_em_2026_mantem_rbt12_por_competencia_e_avisa(
    empresa_antiga, usuario_gestor_a
):
    pares = [(ano_mes, "1000") for ano_mes in sequencia(2025, 1, 12)] + [((2026, 1), "0")]
    _lancar_meses(empresa_antiga, usuario_gestor_a, pares)
    servico_receita.registrar_opcao_regime_caixa(empresa_antiga, 2026, usuario_gestor_a)

    resultado = apuracao.rbt12(empresa_antiga, 2026, 1)

    assert resultado.de(INTERNO).apurado == Decimal("12000.00")
    aviso = next(a for a in resultado.avisos if a.codigo == "regime_caixa_em_ano")
    assert "pré-DAS fica bloqueado" in aviso.mensagem
    assert "Res. CGSN 140, arts. 16 e 19" in aviso.dispositivo


# ---------------------------------------------------------------------------
# Precisão: sem arredondamento do RBT12
# ---------------------------------------------------------------------------


def test_media_nao_exata_fica_com_precisao_guardada_sem_arredondar_a_centavos(
    empresa_a, usuario_gestor_a
):
    # Abertura 05/01/2026 e PA ago/2026: janela jan a jul = 7 meses. Soma 10.000,00.
    # RBT12 = 10.000 × 12 / 7 = 17.142,857142... Não pode virar 17.142,86 (centavos).
    fixar_inicio_de_uso(empresa_a, 2026, 1)
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 1, 5), inicio_simples=date(2026, 1, 5)
    )
    _lancar_meses(
        empresa,
        usuario_gestor_a,
        [((2026, 1), "10000")] + [((2026, mes), "0") for mes in range(2, 9)],
    )

    resultado = apuracao.rbt12(empresa, 2026, 8)

    apurado = resultado.de(INTERNO).apurado
    assert isinstance(apurado, Decimal)
    assert resultado.de(INTERNO).divisor == 7
    assert apurado != Decimal("17142.86")
    # Mais de duas casas decimais guardadas: a precisão não foi cortada a centavos.
    assert apurado.as_tuple().exponent < -10
    assert abs(apurado * 7 - Decimal("120000")) < Decimal("1e-20")


# ---------------------------------------------------------------------------
# A1 (HI-76, achado A1 da auditoria rodada 1) — o § 3º vale na VIRADA do ano.
# Os 12 primeiros meses de atividade usam a média × 12, mesmo que o PA caia em ano
# diferente do da opção. Números escritos à mão; nenhum vem do código.
# ---------------------------------------------------------------------------


def _meses_ate_o_pa(abertura: date, pa: tuple[int, int]):
    """(ano, mês) do mês da abertura até o PA, inclusive, em ordem."""
    n = (pa[0] * 12 + pa[1] - 1) - (abertura.year * 12 + abertura.month - 1) + 1
    return sequencia(abertura.year, abertura.month, n)


@pytest.mark.parametrize(
    ("abertura", "inicio_simples", "receitas", "pa", "regra", "apurado"),
    [
        # C9: abertura 15/10/2025, opção na abertura. PA 02/2026 é o 5º mês de atividade.
        # Janela out/25 a jan/26 (4 meses): 10.000 + 20.000 + 30.000 + 40.000 = 100.000.
        # Média = 100.000 ÷ 4 = 25.000; × 12 = 300.000. Antes de HI-76 saía § 1º: 100.000.
        pytest.param(
            date(2025, 10, 15),
            date(2025, 10, 15),
            {(2025, 10): "10000", (2025, 11): "20000", (2025, 12): "30000", (2026, 1): "40000"},
            (2026, 2),
            "§ 3º",
            "300000",
            id="C9-pa-02-2026-300000",
        ),
        # C9, mesmo lançamento: PA 12/2025 é o 3º mês. Janela out/25 e nov/25: 30.000 ÷ 2 × 12.
        pytest.param(
            date(2025, 10, 15),
            date(2025, 10, 15),
            {(2025, 10): "10000", (2025, 11): "20000", (2025, 12): "30000", (2026, 1): "40000"},
            (2025, 12),
            "§ 3º",
            "180000",
            id="C9-pa-12-2025-180000",
        ),
        # T1: abertura 03/11/2025, opção igual. PA 01/2026 é o 3º mês. Janela nov e dez:
        # (10.000 + 20.000) ÷ 2 × 12 = 180.000.
        pytest.param(
            date(2025, 11, 3),
            date(2025, 11, 3),
            {(2025, 11): "10000", (2025, 12): "20000"},
            (2026, 1),
            "§ 3º",
            "180000",
            id="T1-pa-01-2026-180000",
        ),
        # T2: abertura 15/06/2025, 1.000 por mês de jun/25 a mai/26. PA 05/2026 é o 12º mês:
        # janela jun/25 a abr/26 (11 meses, 11.000) ÷ 11 × 12 = 12.000.
        pytest.param(
            date(2025, 6, 15),
            date(2025, 6, 15),
            {ano_mes: "1000" for ano_mes in sequencia(2025, 6, 12)},
            (2026, 5),
            "§ 3º",
            "12000",
            id="T2-pa-05-2026-12000",
        ),
        # T2, PA 06/2026 é o 13º mês: § 1º = soma de jun/25 a mai/26 = 12 × 1.000 = 12.000.
        pytest.param(
            date(2025, 6, 15),
            date(2025, 6, 15),
            {ano_mes: "1000" for ano_mes in sequencia(2025, 6, 12)},
            (2026, 6),
            "§ 1º",
            "12000",
            id="T2-pa-06-2026-12000-s1",
        ),
    ],
)
def test_proporcional_vale_na_virada_do_ano_quando_a_abertura_e_no_ano_da_opcao(
    empresa_a, usuario_gestor_a, abertura, inicio_simples, receitas, pa, regra, apurado
):
    empresa = preparar_simples(empresa_a, abertura=abertura, inicio_simples=inicio_simples)
    pares = [(ano_mes, receitas.get(ano_mes, "0")) for ano_mes in _meses_ate_o_pa(abertura, pa)]
    _lancar_meses(empresa, usuario_gestor_a, pares)

    resultado = apuracao.rbt12(empresa, *pa)

    assert resultado.regra == regra
    assert resultado.de(INTERNO).apurado == Decimal(apurado)


# ---------------------------------------------------------------------------
# A5 (HI-77) — o aviso do § 5º compara o RBT12 com o limite CHEIO (4.800.000);
# o teto proporcional do ano de início vale só para a receita acumulada no ano.
# ---------------------------------------------------------------------------


def _avisos_de_s5(resultado):
    return [a for a in resultado.avisos if a.codigo == "rbt12_acima_do_limite_ano_dentro"]


def test_a5_abertura_01_12_2026_com_100_mil_nao_gera_aviso_s5(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Caso do relatório. Abertura 01/12/2026 (1º mês): § 2º = 100.000 × 12 = 1.200.000,00.
    # O limite cheio é 4.800.000: o RBT12 não passa dele. O teto proporcional (1 mês,
    # 400.000) só vale para a receita do ano (100.000): também dentro. Sem aviso de § 5º.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 12, 1), inicio_simples=date(2026, 12, 1)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 12), "100000")])

    resultado = apuracao.rbt12(empresa, 2026, 12)

    assert resultado.de(INTERNO).apurado == Decimal("1200000")
    assert _avisos_de_s5(resultado) == []


def test_a5_abertura_05_10_2026_com_150_mil_nao_gera_aviso_s5(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Segundo caso do relatório. Abertura 05/10/2026, § 2º: 150.000 × 12 = 1.800.000,00.
    # Abaixo de 4.800.000 (limite cheio), mesmo acima do teto proporcional de 1.200.000.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 10, 5), inicio_simples=date(2026, 10, 5)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 10), "150000")])

    resultado = apuracao.rbt12(empresa, 2026, 10)

    assert resultado.de(INTERNO).apurado == Decimal("1800000")
    assert _avisos_de_s5(resultado) == []


def test_a5_rbt12_acima_do_limite_cheio_com_receita_do_ano_dentro_do_teto_gera_aviso(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Abertura 01/10/2026: teto proporcional do ano = 3 meses × 400.000 = 1.200.000.
    # § 2º: 450.000 × 12 = 5.400.000,00 > 4.800.000 (limite cheio) → aviso de § 5º.
    # Receita acumulada no ano = 450.000 ≤ 1.200.000 → o ano ainda está dentro do teto.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 10, 1), inicio_simples=date(2026, 10, 1)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 10), "450000")])

    resultado = apuracao.rbt12(empresa, 2026, 10)

    assert resultado.de(INTERNO).apurado == Decimal("5400000")
    avisos = _avisos_de_s5(resultado)
    assert len(avisos) == 1
    # Dispositivo mudou com a consulta ao contador-senior: § 5º, I e II, com o limite cheio.
    assert avisos[0].dispositivo == "Res. CGSN 140/2018, art. 22, § 5º, I e II, e art. 2º, § 1º"
    assert "4800000" in avisos[0].mensagem


# ---------------------------------------------------------------------------
# A7 (a) — receita confirmada em mês ANTERIOR à abertura não entra no RBT12, e o RBT12
# avisa em vez de descartá-la em silêncio (achado A7 da auditoria rodada 1).
# ---------------------------------------------------------------------------


def test_a7_receita_confirmada_antes_da_abertura_gera_aviso_nomeado(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Abertura 10/03/2026. Receita informada CONFIRMADA de 50.000 em 01/2026 (antes da
    # abertura). PA 04/2026: janela só março (1.000) → RBT12 = 1.000 × 12 = 12.000.
    # Os 50.000 de janeiro não entram, e o aviso diz isso.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 1, "50000")
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "1000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    assert resultado.de(INTERNO).apurado == Decimal("12000")
    avisos = [a for a in resultado.avisos if a.codigo == "receita_antes_da_abertura"]
    assert len(avisos) == 1
    assert avisos[0].mercado == INTERNO
    assert (
        "receita de 01/2026 anterior à abertura no CNPJ (10/03/2026) não entra no RBT12"
        in avisos[0].mensagem
    )
    assert "confira a data de abertura" in avisos[0].mensagem


def test_a7_receita_escriturada_antes_da_abertura_tambem_avisa(
    empresa_a, escritorio_a, usuario_gestor_a, monkeypatch
):
    # A escrituração efetivada (DL-072) em 02/2026 também é receita confirmada, e fica de fora.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=971, competencia=(2026, 2), valor="7000"
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "0"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    mensagens = [a.mensagem for a in resultado.avisos if a.codigo == "receita_antes_da_abertura"]
    assert len(mensagens) == 1
    assert "receita de 02/2026 anterior à abertura no CNPJ (10/03/2026)" in mensagens[0]


def test_a7_sem_receita_antes_da_abertura_nao_ha_aviso(empresa_a, usuario_gestor_a, monkeypatch):
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "1000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    assert not any(a.codigo == "receita_antes_da_abertura" for a in resultado.avisos)


# ---------------------------------------------------------------------------
# A6 (Proposta 8) — exemplo do Manual do PGDAS-D, item 8.3 (abertura 12/02/2018).
# Números escritos à mão: fev 10.000, mar 0, abr 590.000, mai 50.000.
# ---------------------------------------------------------------------------


def test_exemplo_do_manual_abertura_12_02_2018_bate_com_120_mil_e_2_4_milhoes(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # PA 02/2018 = 1º mês: 10.000 × 12 = 120.000. PA 05/2018 = 4º mês: janela fev a abr,
    # soma 10.000 + 0 + 590.000 = 600.000, média 600.000 ÷ 3 = 200.000, × 12 = 2.400.000.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2018, 2, 12), inicio_simples=date(2018, 2, 12)
    )
    _lancar_meses(
        empresa,
        usuario_gestor_a,
        [((2018, 2), "10000"), ((2018, 3), "0"), ((2018, 4), "590000"), ((2018, 5), "50000")],
    )

    fevereiro = apuracao.rbt12(empresa, 2018, 2)
    maio = apuracao.rbt12(empresa, 2018, 5)

    assert fevereiro.regra == "§ 2º"
    assert fevereiro.de(INTERNO).apurado == Decimal("120000")
    assert maio.regra == "§ 3º"
    assert maio.de(INTERNO).apurado == Decimal("2400000")


# ---------------------------------------------------------------------------
# R3 da reconferência — fronteiras do § 5º e da varredura pré-abertura (mutantes N5b, N5c, N11b)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("receita_jan", "aviso_esperado"),
    [
        # Exatamente 400.000 × 12 = 4.800.000,00 = limite cheio: "acima" não se aplica (N5c).
        pytest.param("400000", False, id="exatamente-no-limite-sem-aviso"),
        # 400.000,01 × 12 = 4.800.000,12: acima do limite, com o ano dentro do teto → aviso.
        pytest.param("400000.01", True, id="um-centavo-acima-com-aviso"),
    ],
)
def test_r3_n5c_rbt12_na_fronteira_do_limite_cheio(
    empresa_a, usuario_gestor_a, monkeypatch, receita_jan, aviso_esperado
):
    # Abertura 05/01/2026 (1º mês): § 2º, RBT12 = receita do próprio mês × 12. O teto
    # proporcional do ano é 400.000 × 12 = 4.800.000 e a receita do ano é de no máximo
    # 400.000,01, então o aviso do § 5º é o único que pode aparecer na fronteira.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 1, 5), inicio_simples=date(2026, 1, 5)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 1), receita_jan)])

    resultado = apuracao.rbt12(empresa, 2026, 1)

    assert resultado.regra == "§ 2º"
    assert resultado.de(INTERNO).apurado == Decimal(receita_jan) * 12
    assert bool(_avisos_de_s5(resultado)) is aviso_esperado


def test_r3_n5b_inciso_II_do_s5_usa_o_limite_cheio_nao_o_proporcional(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Abertura 01/11/2026 (2 meses no ano). PA dez/2026, § 3º: 450.000 × 12 = 5.400.000 > 4.800.000
    # (inciso I). Acumulado do ano = 450.000 + 400.000 = 850.000. Teto proporcional = 400.000 × 2
    # = 800.000, então o acumulado passou dele: isso gera o aviso de LIMITE excedido, à parte.
    # O inciso II do § 5º compara o acumulado com o limite CHEIO (850.000 ≤ 4.800.000): o § 5º
    # dispara. Se fosse comparado com o proporcional (N5b), o § 5º sumiria.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 11, 1), inicio_simples=date(2026, 11, 1)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 11), "450000"), ((2026, 12), "400000")])

    resultado = apuracao.rbt12(empresa, 2026, 12)

    assert resultado.de(INTERNO).apurado == Decimal("5400000")
    assert len(_avisos_de_s5(resultado)) == 1
    codigos = {a.codigo for a in resultado.avisos}
    assert "limite_excedido_ate_20" in codigos


def test_r3_n11b_aviso_pre_abertura_varre_a_janela_inteira_e_cita_11_2025(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Abertura 10/02/2026. Receita confirmada de 1.000 em 11/2025, ANTES da abertura, dentro da
    # janela de 12 meses do PA 10/2026. A varredura começa no mês mais antigo da janela (N11b:
    # com `max` começaria em 01/2026 e perderia 11/2025).
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 2, 10), inicio_simples=date(2026, 2, 10)
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2025, 11, "1000")
    _lancar_meses(empresa, usuario_gestor_a, [((2026, mes), "0") for mes in range(2, 11)])

    resultado = apuracao.rbt12(empresa, 2026, 10)

    avisos = [a for a in resultado.avisos if a.codigo == "receita_antes_da_abertura"]
    assert len(avisos) == 1
    assert avisos[0].mercado == INTERNO
    assert "receita de 11/2025 anterior à abertura no CNPJ (10/02/2026)" in avisos[0].mensagem


# ---------------------------------------------------------------------------
# R4 da reconferência — período do Simples que começa antes da abertura é recusado
# ---------------------------------------------------------------------------


def test_r4_simples_desde_antes_da_abertura_e_recusado_com_mensagem_nomeada(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # Caso do relatório: Simples desde 01/01/2025, abertura 10/03/2026, PA 05/2026, mar 20 mil
    # e abr 30 mil. Antes da correção caía em § 1º e saía 50.000 (abr/mar em 1º mês de
    # atividade), com aviso só de limites não apurados: erro silencioso e para menos.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2025, 1, 1)
    )
    _lancar_meses(
        empresa,
        usuario_gestor_a,
        [((2026, 3), "20000"), ((2026, 4), "30000"), ((2026, 5), "0")],
    )

    with pytest.raises(apuracao.ApuracaoRecusada, match="Dado inconsistente") as info:
        apuracao.rbt12(empresa, 2026, 5)

    mensagem = str(info.value)
    assert "começa em 01/01/2025" in mensagem
    assert "antes da abertura no CNPJ (10/03/2026)" in mensagem


def test_r4_inicio_do_simples_no_mesmo_mes_mas_antes_do_dia_da_abertura_e_recusado(
    empresa_a, usuario_gestor_a, monkeypatch
):
    # A regra é de DATA, não só de ano: 01/03/2026 é anterior a 10/03/2026 mesmo no mesmo mês.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 1)
    )

    with pytest.raises(apuracao.ApuracaoRecusada, match="Dado inconsistente"):
        apuracao.rbt12(empresa, 2026, 4)


def test_r4_inicio_do_simples_igual_a_abertura_e_aceito(empresa_a, usuario_gestor_a, monkeypatch):
    # Fronteira: o Simples começar no próprio dia da abertura é consistente e não é recusado.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(
        empresa_a, abertura=date(2026, 3, 10), inicio_simples=date(2026, 3, 10)
    )
    _lancar_meses(empresa, usuario_gestor_a, [((2026, 3), "1000"), ((2026, 4), "0")])

    resultado = apuracao.rbt12(empresa, 2026, 4)

    assert resultado.de(INTERNO).apurado == Decimal("12000")


@pytest.mark.parametrize(
    ("abertura", "inicio_simples", "pa", "regra"),
    [
        # Início em 01/01 de ano posterior à abertura: consistente, § 4º (PA 02/2026 = 12º mês).
        pytest.param(
            date(2025, 3, 5), date(2026, 1, 1), (2026, 2), "§ 4º", id="01-01-ano-posterior"
        ),
        # Início no mesmo dia da abertura, dia diferente de 1: consistente, § 3º (PA 04/2026).
        pytest.param(
            date(2026, 3, 15), date(2026, 3, 15), (2026, 4), "§ 3º", id="mesmo-dia-dia-15"
        ),
    ],
)
def test_r4_inicio_do_simples_em_data_consistente_nao_e_recusado(
    empresa_a, monkeypatch, abertura, inicio_simples, pa, regra
):
    # A recusa é por DATA: início igual ou posterior à abertura passa, qualquer que seja o dia.
    fixar_hoje(monkeypatch, date(2026, 12, 31))
    empresa = preparar_simples(empresa_a, abertura=abertura, inicio_simples=inicio_simples)

    resultado = apuracao.rbt12(empresa, *pa)

    assert resultado.regra == regra
