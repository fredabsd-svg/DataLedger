"""DL-088, frente A1: RBT12 a partir de 01/2027 (defasado, HI-147) e início de atividade.

Os números são escritos à mão em cada teste, com a conta no comentário. A receita é informada e
confirmada pelos serviços reais (`informar_e_confirmar`, `confirmar_mes`), sem banco simulado.
Cada fase de início de atividade tem o seu próprio cenário: a divisão pelo número de meses precisa
dar exata, e os meses de uma fase são os da outra.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import MercadoReceita
from apps.fiscal.tests.test_dl074_suporte import fixar_hoje
from apps.fiscal.tests.test_dl075_suporte import cenario_simples, receber_e_confirmar_mes

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fixo(monkeypatch):
    """Relógio de Brasília em 15/03/2028 (A7: só se confirma mês completo). Os meses de 2027 e
    de 01 e 02/2028 dos cenários ficam confirmáveis, e o teste não depende da data real."""
    fixar_hoje(monkeypatch, date(2028, 3, 15))


D = Decimal


def confirmar_meses(empresa, usuario, meses_e_valores, mercado=MercadoReceita.INTERNO):
    """Confirma cada (ano, mês) com a receita dada. Valor zero só confirma o mês."""
    for (ano, mes), valor in meses_e_valores:
        if valor:
            receber_e_confirmar_mes(empresa, usuario, ano, mes, valor, mercado=mercado)
        else:
            servico_receita.confirmar_mes(empresa, ano, mes, usuario)


def meses(primeiro, ultimo):
    """Lista de (ano, mês) de `primeiro` até `ultimo`, inclusive (tuplas)."""
    indice, fim = primeiro[0] * 12 + primeiro[1] - 1, ultimo[0] * 12 + ultimo[1] - 1
    return [((i // 12), (i % 12) + 1) for i in range(indice, fim + 1)]


def janela_de(resultado):
    return [(m.ano, m.mes) for m in resultado.janela]


# ---------------------------------------------------------------------------
# Janela defasada (§ 1º a partir de 01/2027)
# ---------------------------------------------------------------------------


def test_janela_de_2027_e_12_2025_a_11_2026_e_nao_inclui_o_mes_anterior(
    empresa_a, usuario_gestor_a
):
    """PA 01/2027: janela = 12/2025 a 11/2026 (pa−13 a pa−2). 12/2026 NÃO entra.

    Receita: 12/2025 = 1.000; 01/2026 a 11/2026 = 2.000 cada (11 × 2.000 = 22.000); 12/2026 =
    900.000. Conta da janela defasada: 1.000 + 22.000 = 23.000. Sem defasagem (janela 01/2026 a
    12/2026): 22.000 + 900.000 = 922.000. O teste guarda a diferença.
    """
    empresa = cenario_simples(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [((2025, 12), 1000)]
        + [(m, 2000) for m in meses((2026, 1), (2026, 11))]
        + [((2026, 12), 900000)],
    )

    resultado = apuracao.rbt12(empresa, 2027, 1)

    assert resultado.regra == "§ 1º"
    assert janela_de(resultado) == meses((2025, 12), (2026, 11))
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("23000")
    assert resultado.apuravel


def test_2026_nao_muda_a_janela_e_o_12_2026_usa_12_2025_a_11_2026(empresa_a, usuario_gestor_a):
    """PA 12/2026 (ainda não defasado): janela pa−12 a pa−1 = 12/2025 a 11/2026. Mesma soma de
    23.000, e o mês 12/2026 é o PA, não entra. A janela de 2026 é a antiga, e só ela."""
    empresa = cenario_simples(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [((2025, 12), 1000)]
        + [(m, 2000) for m in meses((2026, 1), (2026, 11))]
        + [((2026, 12), 900000)],
    )

    resultado = apuracao.rbt12(empresa, 2026, 12)

    assert resultado.regra == "§ 1º"
    assert janela_de(resultado) == meses((2025, 12), (2026, 11))
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("23000")


def test_janela_de_2026_ainda_e_pa_menos_12_a_pa_menos_1(empresa_a, usuario_gestor_a):
    """PA 11/2026 (2026, ainda sem defasagem): janela 11/2025 a 10/2026 — pa−12 a pa−1."""
    empresa = cenario_simples(empresa_a)
    resultado = apuracao.rbt12(empresa, 2026, 11)
    assert resultado.regra == "§ 1º"
    assert janela_de(resultado) == meses((2025, 11), (2026, 10))


def test_fs12_do_fator_r_usa_a_mesma_janela_defasada(empresa_a):
    """A janela que o FS12 do fator r usa é a do RBT12: 12/2025 a 11/2026 no PA 01/2027."""
    empresa = cenario_simples(empresa_a)
    janela = apuracao.janela_da_apuracao(empresa, 2027, 1)
    assert janela.regra == "§ 1º"
    assert janela.meses == tuple(meses((2025, 12), (2026, 11)))


def test_limites_de_2027_e_2028_tem_vigencia_e_2029_nao_tem(empresa_a):
    """Sublimite de 3,6 mi e 300 mil/mês (Res. 190, arts. 9º e 12, § 2º). 2029: sem limite."""
    assert apuracao.limite_vigente("sublimite_anual", date(2027, 3, 1)).valor == D("3600000")
    assert apuracao.limite_vigente("sublimite_proporcional_mes", date(2028, 1, 1)).valor == D(
        "300000"
    )
    assert apuracao.limite_vigente("limite_anual", date(2028, 12, 1)).valor == D("4800000")
    assert apuracao.limite_vigente("limite_anual", date(2029, 1, 1)) is None


def test_2029_em_diante_continua_recusado_citando_a_190(empresa_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(apuracao.ApuracaoRecusada) as excecao:
        apuracao.rbt12(empresa, 2029, 1)
    assert "190/2026" in excecao.value.mensagem
    assert "HI-146" in excecao.value.mensagem


# ---------------------------------------------------------------------------
# Início de atividade em três fases (abertura em 15/01/2027)
# ---------------------------------------------------------------------------


def _abertura_em_2027(empresa_a):
    return cenario_simples(empresa_a, abertura=date(2027, 1, 15), inicio_simples=date(2027, 1, 15))


def test_primeiro_e_segundo_mes_sao_a_primeira_faixa_sem_rbt12_numerico(
    empresa_a, usuario_gestor_a
):
    """Abertura em 15/01/2027. PA 01/2027 (mês 1) e PA 02/2027 (mês 2): 1ª faixa.

    Não há RBT12 numérico (apurado None), a janela é vazia, e `apuravel` é False. Quem pergunta
    pelo motivo lê `primeira_faixa`. O FS12 do fator r recusa nesse estado.
    """
    empresa = _abertura_em_2027(empresa_a)
    for mes in (1, 2):
        resultado = apuracao.rbt12(empresa, 2027, mes)
        assert resultado.primeira_faixa, mes
        assert resultado.regra == apuracao.REGRA_PRIMEIRA_FAIXA
        assert resultado.de(MercadoReceita.INTERNO).apurado is None
        assert resultado.janela == ()
        assert not resultado.apuravel

    with pytest.raises(apuracao.ApuracaoRecusada) as excecao:
        apuracao.janela_da_apuracao(empresa, 2027, 1)
    assert "1º ou o 2º mês" in excecao.value.mensagem


def test_terceiro_mes_e_a_media_de_1_mes_vezes_12(empresa_a, usuario_gestor_a):
    """PA 03/2027 (mês 3): média dos meses ANTERIORES AO MÊS ANTERIOR (abertura até 01/2027) × 12.

    Receita de 01/2027 = 1.000. Média = 1.000 / 1 mês; × 12 = 12.000. Divisor 1 = n − 2.
    """
    empresa = _abertura_em_2027(empresa_a)
    confirmar_meses(empresa, usuario_gestor_a, [((2027, 1), 1000), ((2027, 2), 0)])

    resultado = apuracao.rbt12(empresa, 2027, 3)

    assert resultado.regra == apuracao.REGRA_MEDIA_2027
    assert janela_de(resultado) == [(2027, 1)]
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("12000")
    assert resultado.de(MercadoReceita.INTERNO).divisor == 1


def test_quarto_mes_e_a_media_de_2_meses_vezes_12(empresa_a, usuario_gestor_a):
    """PA 04/2027 (mês 4): meses 01 e 02/2027 = 1.000 e 2.500. Soma 3.500 × 12 = 42.000; ÷ 2.

    O mês 03/2027 (o anterior ao PA) não entra: está fora da janela de média."""
    empresa = _abertura_em_2027(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [((2027, 1), 1000), ((2027, 2), 2500), ((2027, 3), 777777)],
    )

    resultado = apuracao.rbt12(empresa, 2027, 4)

    assert resultado.regra == apuracao.REGRA_MEDIA_2027
    assert janela_de(resultado) == [(2027, 1), (2027, 2)]
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("21000")
    assert resultado.de(MercadoReceita.INTERNO).divisor == 2


def test_decimo_terceiro_mes_divide_por_onze_meses(empresa_a, usuario_gestor_a):
    """PA 01/2028 (mês 13): média dos meses 01/2027 a 11/2027, todos 1.000. Soma 11.000;
    × 12 = 132.000; ÷ 11 = 12.000. O divisor é 11 (n − 2), e não 12 (daria 11.000)."""
    empresa = _abertura_em_2027(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [(m, 1000) for m in meses((2027, 1), (2027, 11))],
    )

    resultado = apuracao.rbt12(empresa, 2028, 1)

    assert resultado.regra == apuracao.REGRA_MEDIA_2027
    assert janela_de(resultado) == meses((2027, 1), (2027, 11))
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("12000")
    assert resultado.de(MercadoReceita.INTERNO).divisor == 11


def test_decimo_quarto_mes_e_a_regra_geral_defasada(empresa_a, usuario_gestor_a):
    """PA 02/2028 (mês 14): regra geral, janela 01/2027 a 12/2027 (pa−13 a pa−2).

    Receita de 12 meses = 1.000 cada: soma 12.000. O mês 01/2028 (anterior ao PA) tem 999.999 e
    NÃO entra: se entrasse, a soma passaria de 12.000."""
    empresa = _abertura_em_2027(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [(m, 1000) for m in meses((2027, 1), (2027, 12))] + [((2028, 1), 999999)],
    )

    resultado = apuracao.rbt12(empresa, 2028, 2)

    assert resultado.regra == "§ 1º"
    assert janela_de(resultado) == meses((2027, 1), (2027, 12))
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("12000")


def test_abertura_em_2026_e_pa_01_2027_usa_a_media_do_mes_11_2026(empresa_a, usuario_gestor_a):
    """Abertura em 10/11/2026 (ano anterior à 1ª apuração defasada). PA 01/2027 é o 3º mês: média
    de 11/2026 (o único mês entre a abertura e o mês anterior, 12/2026) × 12. Receita de 11/2026 =
    1.000: resultado 12.000. Caso que atravessa a virada do ano."""
    empresa = cenario_simples(
        empresa_a, abertura=date(2026, 11, 10), inicio_simples=date(2026, 11, 10)
    )
    confirmar_meses(empresa, usuario_gestor_a, [((2026, 11), 1000), ((2026, 12), 555555)])

    resultado = apuracao.rbt12(empresa, 2027, 1)

    assert resultado.regra == apuracao.REGRA_MEDIA_2027
    assert janela_de(resultado) == [(2026, 11)]
    assert resultado.de(MercadoReceita.INTERNO).apurado == D("12000")


def test_avisos_de_limite_de_2027_vem_com_o_sublimite_da_res_190(empresa_a, usuario_gestor_a):
    """O sublimite de 2027 é o de 3,6 mi (Res. 190, art. 9º): aparece no resultado da apuração."""
    empresa = cenario_simples(empresa_a)
    confirmar_meses(
        empresa,
        usuario_gestor_a,
        [((2025, 12), 1000)]
        + [(m, 2000) for m in meses((2026, 1), (2026, 11))]
        + [((2026, 12), 1000)],
    )
    resultado = apuracao.rbt12(empresa, 2027, 1)
    assert resultado.de(MercadoReceita.INTERNO).teto_sublimite == D("3600000.00")
