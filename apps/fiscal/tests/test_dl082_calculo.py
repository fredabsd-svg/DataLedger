"""DL-082 (frente A): cálculo de mercadoria no Simples, Anexos I e II (critérios 1, 2 e 3).

Todos os valores ESPERADOS são literais escritos à mão, a partir da consulta de 09/10/2026 e do
Manual
do PGDAS-D (exemplos 1, 2, 3 e 6). Nenhum esperado chama a produção. Os casos DB-level passam pelo
pré-DAS real (escrituração, receita, RBT12 e memória). Os casos de cálculo puro usam
`calcular_anexo`
com a receita já segregada, e são declarados onde o catálogo não chega ao caso (ver `test_caso_f`).
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal.models import (
    ANEXO_I,
    ANEXO_II,
    EnquadramentoAtividade,
    NaturezaOperacaoNFe,
    segmento_da_mercadoria,
)
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, informar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import atividade_padrao
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa_a(escritorio_a):
    """Emitente das NF-e sintéticas (CNPJ_EMITENTE_A). Sobrescreve o fixture do conftest, que usa
    outro CNPJ e não recebe as notas de saída destes testes."""
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Comercio DL082 Ltda",
        cnpj=CNPJ_EMITENTE_A,
    )


IRPJ, CSLL, COFINS, PIS, CPP, ICMS, IPI, ISS = (
    "IRPJ",
    "CSLL",
    "COFINS",
    "PIS",
    "CPP",
    "ICMS",
    "IPI",
    "ISS",
)


def _valores(segmento):
    """Valor de cada tributo do segmento, como o pré-DAS o devolve (sem desconsiderados)."""
    return {linha.tributo: linha.valor for linha in segmento.linhas}


def _por_anexo(resultado, mercado, anexo):
    (apurado,) = [a for a in resultado.anexos if a.mercado == mercado and a.anexo == anexo]
    return apurado


# ---------------------------------------------------------------------------
# Exemplos oficiais do Manual do PGDAS-D, passando pelo pré-DAS real (critério 1)
# ---------------------------------------------------------------------------


def test_exemplo_1_manual_anexo_i_segunda_faixa_centavo_a_centavo(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Manual, exemplo 1: RBT12 300.000,00; revenda do mês 100.000,00 (Anexo I, 2ª faixa).

    Esperado (à mão): alíquota efetiva 5,32%; IRPJ 292,60; CSLL 186,20; Cofins 677,77; PIS 146,83;
    CPP 2.207,80; ICMS 1.808,80; total 5.320,00.
    """
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=101,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NaturezaOperacaoNFe.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    assert (anexo.anexo, anexo.faixa) == ("I", 2)
    assert anexo.aliquota_efetiva == Decimal("0.0532")
    (segmento,) = anexo.segmentos
    assert segmento.segmento == "normal"
    assert _valores(segmento) == {
        IRPJ: Decimal("292.60"),
        CSLL: Decimal("186.20"),
        COFINS: Decimal("677.77"),
        PIS: Decimal("146.83"),
        CPP: Decimal("2207.80"),
        ICMS: Decimal("1808.80"),
    }
    assert resultado.total == Decimal("5320.00")


def test_exemplo_2_mais_de_um_anexo_com_um_rbt12_centavo_a_centavo(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Manual, exemplo 2: RBT12 ÚNICO de 300.000,00; revenda 300.000,00 (Anexo I) e serviço
    100.000,00 (Anexo III, sem fator r).

    Esperado (à mão): Anexo I, 5,32%: IRPJ 877,80; CSLL 558,60; Cofins 2.033,30; PIS 440,50;
    CPP 6.623,40; ICMS 5.426,40; subtotal 15.960,00. Anexo III, 8,08%: IRPJ 323,20; CSLL 282,80;
    Cofins 1.135,24; PIS 246,44; CPP 3.506,72; ISS 2.585,60; subtotal 8.080,00. Total 24.040,00.
    """
    empresa = cenario(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar(empresa, usuario_gestor_a, 2026, 6, 100000)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=102,
        itens=[{"cfop": "5102", "vprod": "300000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NaturezaOperacaoNFe.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.rbt12 == {"interno": Decimal("300000.00")}
    comercio = _por_anexo(resultado, "interno", ANEXO_I)
    assert comercio.aliquota_efetiva == Decimal("0.0532")
    assert _valores(comercio.segmentos[0]) == {
        IRPJ: Decimal("877.80"),
        CSLL: Decimal("558.60"),
        COFINS: Decimal("2033.30"),
        PIS: Decimal("440.50"),
        CPP: Decimal("6623.40"),
        ICMS: Decimal("5426.40"),
    }
    assert comercio.total == Decimal("15960.00")
    servicos = _por_anexo(resultado, "interno", "III")
    assert servicos.aliquota_efetiva == Decimal("0.0808")
    assert _valores(servicos.segmentos[0]) == {
        IRPJ: Decimal("323.20"),
        CSLL: Decimal("282.80"),
        COFINS: Decimal("1135.24"),
        PIS: Decimal("246.44"),
        CPP: Decimal("3506.72"),
        ISS: Decimal("2585.60"),
    }
    assert servicos.total == Decimal("8080.00")
    assert resultado.total == Decimal("24040.00")


def test_exemplo_3_inicio_de_atividade_centavo_a_centavo_pelo_calculo():
    """Manual, exemplo 3 (início em 01/2018): calculado pelo cálculo de um anexo, com o RBT12 do
    mês.

    Limitação declarada: o PA de 2018 não tem limites cadastrados (HI-70), e o pré-DAS recusa esse
    mês. Por isso o exemplo 3 é conferido no cálculo puro, com o RBT12 proporcional do Manual
    (jan: 0; fev: 10.000 × 12; mar: (10.000 + 100.000) / 2 × 12 = 660.000). A apuração do RBT12
    proporcional fica com o DL-074.

    Esperado (à mão): janeiro 4% → 400,00 (IRPJ 22,00; CSLL 14,00; Cofins 50,96; PIS 11,04;
    CPP 166,00; ICMS 136,00); fevereiro 4% → 4.000,00 (IRPJ 220,00; CSLL 140,00; Cofins 509,60;
    PIS 110,40; CPP 1.660,00; ICMS 1.360,00); março 7,40% → 7.400,00 (IRPJ 407,00; CSLL 259,00;
    Cofins 942,76; PIS 204,24; CPP 3.108,00; ICMS 2.479,00).
    """
    janeiro = servico_pre_das.calcular_anexo(
        ANEXO_I, Decimal("0"), [("normal", Decimal("10000.00"))]
    )
    assert janeiro.efetiva == Decimal("0.04")
    assert _valores(janeiro.segmentos[0]) == {
        IRPJ: Decimal("22.00"),
        CSLL: Decimal("14.00"),
        COFINS: Decimal("50.96"),
        PIS: Decimal("11.04"),
        CPP: Decimal("166.00"),
        ICMS: Decimal("136.00"),
    }
    assert janeiro.total == Decimal("400.00")

    fevereiro = servico_pre_das.calcular_anexo(
        ANEXO_I, Decimal("120000"), [("normal", Decimal("100000.00"))]
    )
    assert _valores(fevereiro.segmentos[0]) == {
        IRPJ: Decimal("220.00"),
        CSLL: Decimal("140.00"),
        COFINS: Decimal("509.60"),
        PIS: Decimal("110.40"),
        CPP: Decimal("1660.00"),
        ICMS: Decimal("1360.00"),
    }
    assert fevereiro.total == Decimal("4000.00")

    marco = servico_pre_das.calcular_anexo(
        ANEXO_I, Decimal("660000"), [("normal", Decimal("100000.00"))]
    )
    assert marco.efetiva == Decimal("0.074")
    assert _valores(marco.segmentos[0]) == {
        IRPJ: Decimal("407.00"),
        CSLL: Decimal("259.00"),
        COFINS: Decimal("942.76"),
        PIS: Decimal("204.24"),
        CPP: Decimal("3108.00"),
        ICMS: Decimal("2479.00"),
    }
    assert marco.total == Decimal("7400.00")


def test_exemplo_6_exportacao_dois_mercados_centavo_a_centavo(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Manual, exemplo 6: RBT12 interno 2.000.000 (5ª faixa) e externo 1.000.000 (4ª faixa).

    Mercado interno: revenda do mês 100.000 (Anexo I). Mercado externo: exportação de 50.000.
    Esperado (à mão), total interno 9.935,02 (soma dos tributos arredondados, não 9.935,00):
    alíquota 9,935%: IRPJ 546,43; CSLL 347,73; Cofins 1.265,72; PIS 274,21; CPP 4.172,70;
    ICMS 3.328,23. Externo, alíquota 8,45%, Cofins, PIS e ICMS desconsiderados: IRPJ 232,38;
    CSLL 147,88; CPP 1.774,50; subtotal 2.154,76. Total 12.089,78.
    """
    empresa = cenario(empresa_a)
    janela(
        empresa,
        usuario_gestor_a,
        2026,
        6,
        interno=[200000] * 10 + [0, 0],
        externo=[100000] * 10 + [0, 0],
    )
    documento_interno = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=106,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento_interno, {1: NaturezaOperacaoNFe.REVENDA})
    documento_externo = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=107,
        # 7.102: exportação de mercadoria adquirida de terceiros (revenda). Anexo I pela descrição
        # oficial do CFOP (DL-082). Com 7.101 seria venda de produção (Anexo II).
        itens=[{"cfop": "7102", "vprod": "50000.00"}],
        id_dest="3",
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        documento_externo,
        {1: NaturezaOperacaoNFe.EXPORTACAO_DIRETA},
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    interno = _por_anexo(resultado, "interno", ANEXO_I)
    assert interno.faixa == 5
    assert interno.aliquota_efetiva == Decimal("0.09935")
    assert _valores(interno.segmentos[0]) == {
        IRPJ: Decimal("546.43"),
        CSLL: Decimal("347.73"),
        COFINS: Decimal("1265.72"),
        PIS: Decimal("274.21"),
        CPP: Decimal("4172.70"),
        ICMS: Decimal("3328.23"),
    }
    assert interno.total == Decimal("9935.02")

    externo = _por_anexo(resultado, "externo", ANEXO_I)
    assert externo.faixa == 4
    assert externo.aliquota_efetiva == Decimal("0.0845")
    tributos_externo = {linha.tributo: linha for linha in externo.segmentos[0].linhas}
    assert tributos_externo[IRPJ].valor == Decimal("232.38")
    assert tributos_externo[CSLL].valor == Decimal("147.88")
    assert tributos_externo[CPP].valor == Decimal("1774.50")
    for desconsiderado in (COFINS, PIS, ICMS):
        assert tributos_externo[desconsiderado].desconsiderado is True
        assert tributos_externo[desconsiderado].valor == Decimal("0.00")
    assert externo.total == Decimal("2154.76")
    assert resultado.total == Decimal("12089.78")


# ---------------------------------------------------------------------------
# Casos calculados D, E, G e H da consulta (critério 2), pelo pré-DAS real
# ---------------------------------------------------------------------------


def test_caso_d_anexo_i_terceira_faixa_com_st_e_monofasico(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso D: RBT12 600.000 (3ª faixa, efetiva 7,19%). Mês: normal 30.000 + ST substituído 12.000
    (CSOSN 500) + monofásico 8.000 (natureza monofásica).

    Esperado (à mão): normal 2.157,01 (IRPJ 118,64; CSLL 75,50; Cofins 274,80; PIS 59,53;
    CPP 905,94; ICMS 722,60); ST 573,76 (ICMS 0,00; IRPJ 47,45; CSLL 30,20; Cofins 109,92; PIS
    23,81;
    CPP 362,38); monofásico 486,04 (Cofins 0,00 e PIS 0,00; IRPJ 31,64; CSLL 20,13; CPP 241,58;
    ICMS 192,69). Total 3.216,81.
    """
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=201,
        itens=[
            {"cfop": "5102", "vprod": "30000.00", "csosn": "102"},
            {"cfop": "5405", "vprod": "12000.00", "csosn": "500"},
            {"cfop": "5102", "vprod": "8000.00", "csosn": "102"},
        ],
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        documento,
        {
            1: NaturezaOperacaoNFe.REVENDA,
            2: NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO,
            3: NaturezaOperacaoNFe.MONOFASICO,
        },
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    anexo = _por_anexo(resultado, "interno", ANEXO_I)
    assert anexo.faixa == 3
    assert anexo.aliquota_efetiva == Decimal("0.0719")
    por_segmento = {s.segmento: s for s in anexo.segmentos}
    assert _valores(por_segmento["normal"]) == {
        IRPJ: Decimal("118.64"),
        CSLL: Decimal("75.50"),
        COFINS: Decimal("274.80"),
        PIS: Decimal("59.53"),
        CPP: Decimal("905.94"),
        ICMS: Decimal("722.60"),
    }
    assert por_segmento["normal"].total == Decimal("2157.01")
    assert _valores(por_segmento["sujeita_st"]) == {
        IRPJ: Decimal("47.45"),
        CSLL: Decimal("30.20"),
        COFINS: Decimal("109.92"),
        PIS: Decimal("23.81"),
        CPP: Decimal("362.38"),
        ICMS: Decimal("0.00"),
    }
    assert por_segmento["sujeita_st"].total == Decimal("573.76")
    assert _valores(por_segmento["monofasico"]) == {
        IRPJ: Decimal("31.64"),
        CSLL: Decimal("20.13"),
        COFINS: Decimal("0.00"),
        PIS: Decimal("0.00"),
        CPP: Decimal("241.58"),
        ICMS: Decimal("192.69"),
    }
    assert por_segmento["monofasico"].total == Decimal("486.04")
    assert resultado.total == Decimal("3216.81")


def test_caso_e_st_e_monofasico_no_mesmo_item_pela_marca(escritorio_a, usuario_gestor_a, empresa_a):
    """Caso E: ST substituído E monofásico no MESMO item (natureza de ST + marca do contador,
    HI-128).

    Mesma empresa do caso D (RBT12 600.000). Item de 5.000 com CSOSN 500 e a marca de monofásico.
    Esperado (à mão): IRPJ 19,77; CSLL 12,58; Cofins 0,00; PIS 0,00; CPP 150,99; ICMS 0,00. Total
    183,34.
    """
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=202,
        itens=[{"cfop": "5405", "vprod": "5000.00", "csosn": "500"}],
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        documento,
        {1: NaturezaOperacaoNFe.REVENDA_ST_SUBSTITUIDO},
        marcas=[1],
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (segmento,) = _por_anexo(resultado, "interno", ANEXO_I).segmentos
    assert segmento.segmento == "st_monofasico"
    assert _valores(segmento) == {
        IRPJ: Decimal("19.77"),
        CSLL: Decimal("12.58"),
        COFINS: Decimal("0.00"),
        PIS: Decimal("0.00"),
        CPP: Decimal("150.99"),
        ICMS: Decimal("0.00"),
    }
    assert resultado.total == Decimal("183.34")


def test_caso_g_dois_anexos_com_rbt12_unico(escritorio_a, usuario_gestor_a, empresa_a):
    """Caso G: RBT12 300.000; revenda 60.000 (Anexo I, 5,32%) e serviço 20.000 (Anexo III, 8,08%).

    Esperado (à mão): revenda IRPJ 175,56; CSLL 111,72; Cofins 406,66; PIS 88,10; CPP 1.324,68;
    ICMS 1.085,28; subtotal 3.192,00. Serviço IRPJ 64,64; CSLL 56,56; Cofins 227,05; PIS 49,29;
    CPP 701,34; ISS 517,12; subtotal 1.616,00. Total 4.808,00.
    """
    empresa = cenario(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar(empresa, usuario_gestor_a, 2026, 6, 20000)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=207,
        itens=[{"cfop": "5102", "vprod": "60000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NaturezaOperacaoNFe.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    comercio = _por_anexo(resultado, "interno", ANEXO_I)
    assert _valores(comercio.segmentos[0]) == {
        IRPJ: Decimal("175.56"),
        CSLL: Decimal("111.72"),
        COFINS: Decimal("406.66"),
        PIS: Decimal("88.10"),
        CPP: Decimal("1324.68"),
        ICMS: Decimal("1085.28"),
    }
    assert comercio.total == Decimal("3192.00")
    servicos = _por_anexo(resultado, "interno", "III")
    assert _valores(servicos.segmentos[0]) == {
        IRPJ: Decimal("64.64"),
        CSLL: Decimal("56.56"),
        COFINS: Decimal("227.05"),
        PIS: Decimal("49.29"),
        CPP: Decimal("701.34"),
        ISS: Decimal("517.12"),
    }
    assert servicos.total == Decimal("1616.00")
    assert resultado.total == Decimal("4808.00")


def test_caso_h_substituto_com_vst_fora_da_receita(escritorio_a, usuario_gestor_a, empresa_a):
    """Caso H: substituto (CSOSN 201). Operação própria de 10.000 com vST de 1.800 que NÃO é
    receita.

    Esperado (à mão): IRPJ 39,55; CSLL 25,17; Cofins 91,60; PIS 19,84; CPP 301,98; ICMS 240,87.
    Total 719,01 (o ICMS-ST de 1.800 vai à SEFAZ por fora, e não entra no DAS).
    """
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=208,
        itens=[{"cfop": "5102", "vprod": "10000.00", "csosn": "201", "vst": "1800.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NaturezaOperacaoNFe.SUBSTITUTO_ST})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (segmento,) = _por_anexo(resultado, "interno", ANEXO_I).segmentos
    assert segmento.receita == Decimal("10000.00")
    assert _valores(segmento) == {
        IRPJ: Decimal("39.55"),
        CSLL: Decimal("25.17"),
        COFINS: Decimal("91.60"),
        PIS: Decimal("19.84"),
        CPP: Decimal("301.98"),
        ICMS: Decimal("240.87"),
    }
    assert resultado.total == Decimal("719.01")


# ---------------------------------------------------------------------------
# Caso F (Anexo II com ST e exportação): cálculo puro (critério 2, com limite declarado)
# ---------------------------------------------------------------------------


def test_caso_f_anexo_ii_com_st_e_exportacao_calculo_puro():
    """Caso F: Anexo II. RBT12 interno 900.000 (4ª faixa, efetiva 8,70%): normal 40.000 e ST
    substituído 10.000. RBT12 externo 150.000 (1ª faixa, 4,50%): exportação 20.000.

    Cálculo puro, com a receita já segregada. O mesmo caso roda ponta a ponta em
    `test_dl082_anexo_cfop.py::test_caso_f_ponta_a_ponta...` (anexo pelo CFOP).

    Esperado (à mão): normal IRPJ 191,40; CSLL 121,80; Cofins 400,55; PIS 86,65; CPP 1.305,00;
    IPI 261,00; ICMS 1.113,60; subtotal 3.480,00. ST IRPJ 47,85; CSLL 30,45; Cofins 100,14; PIS
    21,66;
    CPP 326,25; IPI 65,25; ICMS 0,00; subtotal 591,60. Exportação IRPJ 49,50; CSLL 31,50; CPP
    337,50;
    Cofins, PIS, IPI e ICMS 0,00; subtotal 418,50. Total 4.490,10.
    """
    interno = servico_pre_das.calcular_anexo(
        ANEXO_II,
        Decimal("900000"),
        [("normal", Decimal("40000")), ("sujeita_st", Decimal("10000"))],
    )
    assert interno.efetiva == Decimal("0.087")
    assert interno.faixa.numero == 4
    normal, st = interno.segmentos
    assert _valores(normal) == {
        IRPJ: Decimal("191.40"),
        CSLL: Decimal("121.80"),
        COFINS: Decimal("400.55"),
        PIS: Decimal("86.65"),
        CPP: Decimal("1305.00"),
        IPI: Decimal("261.00"),
        ICMS: Decimal("1113.60"),
    }
    assert normal.total == Decimal("3480.00")
    assert _valores(st) == {
        IRPJ: Decimal("47.85"),
        CSLL: Decimal("30.45"),
        COFINS: Decimal("100.14"),
        PIS: Decimal("21.66"),
        CPP: Decimal("326.25"),
        IPI: Decimal("65.25"),
        ICMS: Decimal("0.00"),
    }
    assert st.total == Decimal("591.60")

    externo = servico_pre_das.calcular_anexo(
        ANEXO_II, Decimal("150000"), [("exportacao", Decimal("20000"))]
    )
    assert externo.efetiva == Decimal("0.045")
    (exportacao,) = externo.segmentos
    assert _valores(exportacao) == {
        IRPJ: Decimal("49.50"),
        CSLL: Decimal("31.50"),
        COFINS: Decimal("0.00"),
        PIS: Decimal("0.00"),
        CPP: Decimal("337.50"),
        IPI: Decimal("0.00"),
        ICMS: Decimal("0.00"),
    }
    assert exportacao.total == Decimal("418.50")
    assert normal.total + st.total + exportacao.total == Decimal("4490.10")


# ---------------------------------------------------------------------------
# Conjunto desconsiderado por condição, e a união nas combinações (critérios 3 e 4 do plano)
# ---------------------------------------------------------------------------


def test_conjuntos_desconsiderados_por_segmento_de_mercadoria():
    """Esperado escrito à mão, pela norma (Res. CGSN 140, art. 25, §§ 3º, 6º a 8º): cada
    conjunto."""
    desconsiderados = servico_pre_das._desconsiderados
    assert desconsiderados(ANEXO_I, "normal") == frozenset()
    assert desconsiderados(ANEXO_I, "sujeita_st") == frozenset({ICMS})
    assert desconsiderados(ANEXO_I, "monofasico") == frozenset({PIS, COFINS})
    assert desconsiderados(ANEXO_I, "st_monofasico") == frozenset({ICMS, PIS, COFINS})
    assert desconsiderados(ANEXO_II, "exportacao") == frozenset({PIS, COFINS, IPI, ICMS, ISS})
    assert desconsiderados(ANEXO_I, "exportacao") == frozenset({PIS, COFINS, IPI, ICMS, ISS})


def test_exportacao_inclui_ipi_no_conjunto():
    """A exportação tira IPI, que faltava no conjunto de hoje (Res. CGSN 140, art. 25, § 3º)."""
    assert IPI in servico_pre_das._desconsiderados(ANEXO_II, "exportacao")


def test_servico_mantem_o_conjunto_da_dl075():
    """Anexo III: exportação de serviço tira PIS, Cofins e ISS, como antes (DL-075, sem mudança)."""
    desconsiderados = servico_pre_das._desconsiderados
    assert desconsiderados("III", "exportacao") == frozenset({PIS, COFINS, ISS})
    assert desconsiderados("III", "iss_retido") == frozenset({ISS})


def test_uniao_das_condicoes_de_mercadoria():
    """Combinação: a união dos conjuntos, e exportação já contém ST e monofásico (§ 3º)."""
    assert segmento_da_mercadoria(st=True, monofasico=True, exportacao=False) == "st_monofasico"
    assert segmento_da_mercadoria(st=True, monofasico=False, exportacao=True) == "exportacao"
    assert segmento_da_mercadoria(st=True, monofasico=True, exportacao=True) == "exportacao"
    assert segmento_da_mercadoria(st=False, monofasico=False, exportacao=False) == "normal"
