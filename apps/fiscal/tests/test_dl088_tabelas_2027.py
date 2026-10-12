"""DL-088, frente A1: tabelas do Simples de 2027 e 2028 (HI-146), conferidas número a número.

Os números de referência ficam ESCRITOS À MÃO aqui, transcritos da consulta de 09/10/2026, seção 1
(DOU 10/08/2026, Ed. 149-A, Seção 1 Extra A, Res. CGSN 190/2026, art. 6º). Não são lidos do módulo
`simples_tabelas`: um teste que lê a própria tabela não prova nada (AGENTS.md §7).

Sem banco: é cálculo de dado puro.
"""

from datetime import date
from decimal import Decimal

from apps.fiscal import simples_tabelas as tabelas

CBS, IBS, IRPJ, CSLL, CPP = "CBS", "IBS", "IRPJ", "CSLL", "CPP"
ICMS, IPI, ISS = "ICMS", "IPI", "ISS"


def dec(texto: str) -> Decimal:
    """'15,33' → Decimal('15.33') (um número em percentual, sem a escala de fração)."""
    return Decimal(texto.replace(".", "").replace(",", ".")) if "," in texto else Decimal(texto)


# (alíquota nominal %, parcela a deduzir R$, repartição em %) por faixa, 1ª a 6ª.
# A parcela "–" da consulta vira 0. Os limites de RBT12 são os mesmos para os cinco anexos.
REF_2027 = {
    "I": [
        (
            "4,00",
            "0",
            {IRPJ: "5,50", CSLL: "3,50", CBS: "15,33", CPP: "41,50", ICMS: "34,00", IBS: "0,17"},
        ),
        (
            "7,30",
            "5940,00",
            {IRPJ: "5,50", CSLL: "3,50", CBS: "15,33", CPP: "41,50", ICMS: "34,00", IBS: "0,17"},
        ),
        (
            "9,50",
            "13860,00",
            {IRPJ: "5,50", CSLL: "3,50", CBS: "15,33", CPP: "42,00", ICMS: "33,50", IBS: "0,17"},
        ),
        (
            "10,70",
            "22500,00",
            {IRPJ: "5,50", CSLL: "3,50", CBS: "15,33", CPP: "42,00", ICMS: "33,50", IBS: "0,17"},
        ),
        (
            "14,30",
            "87300,00",
            {IRPJ: "5,50", CSLL: "3,50", CBS: "15,33", CPP: "42,00", ICMS: "33,50", IBS: "0,17"},
        ),
        ("18,90", "378000,00", {IRPJ: "13,58", CSLL: "10,06", CBS: "34,02", CPP: "42,34"}),
    ],
    "II": [
        (
            "4,50",
            "0",
            {
                IRPJ: "5,50",
                CSLL: "3,50",
                CBS: "13,85",
                CPP: "37,50",
                IPI: "7,50",
                ICMS: "32,00",
                IBS: "0,15",
            },
        ),
        (
            "7,80",
            "5940,00",
            {
                IRPJ: "5,50",
                CSLL: "3,50",
                CBS: "13,85",
                CPP: "37,50",
                IPI: "7,50",
                ICMS: "32,00",
                IBS: "0,15",
            },
        ),
        (
            "10,00",
            "13860,00",
            {
                IRPJ: "5,50",
                CSLL: "3,50",
                CBS: "13,85",
                CPP: "37,50",
                IPI: "7,50",
                ICMS: "32,00",
                IBS: "0,15",
            },
        ),
        (
            "11,20",
            "22500,00",
            {
                IRPJ: "5,50",
                CSLL: "3,50",
                CBS: "13,85",
                CPP: "37,50",
                IPI: "7,50",
                ICMS: "32,00",
                IBS: "0,15",
            },
        ),
        (
            "14,70",
            "85500,00",
            {
                IRPJ: "5,50",
                CSLL: "3,50",
                CBS: "13,85",
                CPP: "37,50",
                IPI: "7,50",
                ICMS: "32,00",
                IBS: "0,15",
            },
        ),
        (
            "29,90",
            "720000,00",
            {IRPJ: "8,53", CSLL: "7,53", CBS: "25,22", CPP: "23,59", IPI: "35,13"},
        ),
    ],
    "III": [
        (
            "6,00",
            "0",
            {IRPJ: "4,00", CSLL: "3,50", CBS: "15,43", CPP: "43,40", ISS: "33,50", IBS: "0,17"},
        ),
        (
            "11,20",
            "9360,00",
            {IRPJ: "4,00", CSLL: "3,50", CBS: "16,91", CPP: "43,40", ISS: "32,00", IBS: "0,19"},
        ),
        (
            "13,50",
            "17640,00",
            {IRPJ: "4,00", CSLL: "3,50", CBS: "16,41", CPP: "43,40", ISS: "32,50", IBS: "0,19"},
        ),
        (
            "16,00",
            "35640,00",
            {IRPJ: "4,00", CSLL: "3,50", CBS: "16,41", CPP: "43,40", ISS: "32,50", IBS: "0,19"},
        ),
        (
            "21,00",
            "125640,00",
            {IRPJ: "4,00", CSLL: "3,50", CBS: "15,43", CPP: "43,40", ISS: "33,50", IBS: "0,17"},
        ),
        ("32,90", "648000,00", {IRPJ: "35,09", CSLL: "15,04", CBS: "19,29", CPP: "30,58"}),
    ],
    "IV": [
        ("4,50", "0", {IRPJ: "18,80", CSLL: "15,20", CBS: "21,26", ISS: "44,50", IBS: "0,24"}),
        (
            "9,00",
            "8100,00",
            {IRPJ: "19,80", CSLL: "15,20", CBS: "24,73", ISS: "40,00", IBS: "0,27"},
        ),
        (
            "10,20",
            "12420,00",
            {IRPJ: "20,80", CSLL: "15,20", CBS: "23,74", ISS: "40,00", IBS: "0,26"},
        ),
        (
            "14,00",
            "39780,00",
            {IRPJ: "17,80", CSLL: "19,20", CBS: "22,75", ISS: "40,00", IBS: "0,25"},
        ),
        (
            "22,00",
            "183780,00",
            {IRPJ: "18,80", CSLL: "19,20", CBS: "21,76", ISS: "40,00", IBS: "0,24"},
        ),
        ("32,90", "828000,00", {IRPJ: "53,71", CSLL: "21,59", CBS: "24,70"}),
    ],
    "V": [
        (
            "15,50",
            "0",
            {IRPJ: "25,00", CSLL: "15,00", CBS: "16,96", CPP: "28,85", ISS: "14,00", IBS: "0,19"},
        ),
        (
            "18,00",
            "4500,00",
            {IRPJ: "23,00", CSLL: "15,00", CBS: "16,96", CPP: "27,85", ISS: "17,00", IBS: "0,19"},
        ),
        (
            "19,50",
            "9900,00",
            {IRPJ: "24,00", CSLL: "15,00", CBS: "17,95", CPP: "23,85", ISS: "19,00", IBS: "0,20"},
        ),
        (
            "20,50",
            "17100,00",
            {IRPJ: "21,00", CSLL: "15,00", CBS: "18,94", CPP: "23,85", ISS: "21,00", IBS: "0,21"},
        ),
        (
            "23,00",
            "62100,00",
            {IRPJ: "23,00", CSLL: "12,50", CBS: "16,96", CPP: "23,85", ISS: "23,50", IBS: "0,19"},
        ),
        ("30,40", "540000,00", {IRPJ: "35,10", CSLL: "15,54", CBS: "19,78", CPP: "29,58"}),
    ],
}

# Limites de RBT12 das faixas 1ª a 6ª (mesmos para os cinco anexos).
LIMITES_REF = ["180000.00", "360000.00", "720000.00", "1800000.00", "3600000.00", "4800000.00"]

# Tetos do ISS (nota (*)): limiar da alíquota efetiva, e redistribuição em % (soma 100,00).
TETO_REF = {
    "III": ("14,92537", {IRPJ: "6,02", CSLL: "5,26", CBS: "23,20", CPP: "65,26", IBS: "0,26"}),
    "IV": ("12,5", {IRPJ: "31,33", CSLL: "32,00", CBS: "36,27", IBS: "0,40"}),
}


def test_seis_faixas_por_anexo_batem_com_a_consulta_numero_a_numero():
    for numero, faixas_ref in REF_2027.items():
        anexo = tabelas.anexo(numero, 2027, 1)
        assert len(anexo.faixas) == 6, numero
        for indice, (aliquota, deducao, rep_ref) in enumerate(faixas_ref, start=1):
            faixa = anexo.faixa(indice)
            assert faixa.numero == indice
            assert faixa.limite_superior == Decimal(LIMITES_REF[indice - 1]), (numero, indice)
            assert faixa.aliquota_nominal == dec(aliquota) / 100, (numero, indice)
            assert faixa.parcela_a_deduzir == dec(deducao), (numero, indice)
            # A repartição do módulo é exatamente a da consulta, tributo por tributo.
            assert dict(faixa.reparticao) == {t: dec(v) / 100 for t, v in rep_ref.items()}, (
                numero,
                indice,
            )


def test_sexta_faixa_nominal_e_18_90_29_90_32_90_32_90_30_40():
    nominais = {
        numero: tabelas.anexo(numero, 2027, 1).faixa(6).aliquota_nominal
        for numero in ("I", "II", "III", "IV", "V")
    }
    assert nominais == {
        "I": Decimal("0.1890"),
        "II": Decimal("0.2990"),
        "III": Decimal("0.3290"),
        "IV": Decimal("0.3290"),
        "V": Decimal("0.3040"),
    }


def test_cada_linha_de_reparticao_soma_100_por_cento():
    for numero in REF_2027:
        for faixa in tabelas.anexo(numero, 2027, 1).faixas:
            soma = sum((valor for _tributo, valor in faixa.reparticao), Decimal(0))
            assert soma == Decimal("1.0000"), (numero, faixa.numero, soma)


def test_cada_teto_do_iss_soma_100_por_cento_e_cai_na_quinta_faixa():
    for numero, (limiar_ref, redistribuicao_ref) in TETO_REF.items():
        teto = tabelas.anexo(numero, 2027, 1).teto_iss
        assert teto is not None, numero
        assert teto.limiar_efetiva == dec(limiar_ref) / 100
        assert teto.percentual_iss == Decimal("0.05")
        assert teto.faixa == 5
        assert dict(teto.redistribuicao) == {t: dec(v) / 100 for t, v in redistribuicao_ref.items()}
        assert sum((v for _t, v in teto.redistribuicao), Decimal(0)) == Decimal("1.0000"), numero


def test_anexos_sem_teto_do_iss_sao_o_que_a_consulta_diz():
    for numero in ("I", "II", "V"):
        assert tabelas.anexo(numero, 2027, 1).teto_iss is None, numero


def test_tributos_de_2027_tem_cbs_e_ibs_e_nao_pis_nem_cofins():
    for numero in REF_2027:
        tributos = tabelas.anexo(numero, 2027, 1).tributos
        assert CBS in tributos and IBS in tributos, numero
        assert "PIS" not in tributos and "COFINS" not in tributos, numero
    assert "CPP" not in tabelas.anexo("IV", 2027, 1).tributos
    assert "CPP" in tabelas.anexo("III", 2027, 1).tributos
    assert "IPI" in tabelas.anexo("II", 2027, 1).tributos
    assert "IPI" not in tabelas.anexo("I", 2027, 1).tributos


def test_vigencia_2027_2028_pela_data_do_periodo():
    assert tabelas.anexo("III", 2027, 1) is tabelas.ANEXOS_2027_2028["III"]
    assert tabelas.anexo("III", 2028, 12) is tabelas.ANEXOS_2027_2028["III"]
    assert tabelas.anexo("III", 2026, 12) is tabelas.ANEXOS["III"]
    assert tabelas.anexo("III", 2018, 1) is tabelas.ANEXOS["III"]
    assert tabelas.tabelas_vigentes_em(2027, 1)
    assert tabelas.tabelas_vigentes_em(2028, 12)
    assert not tabelas.tabelas_vigentes_em(2029, 1)
    assert tabelas.ANEXOS_2027_2028["I"].inicio == date(2027, 1, 1)
    assert tabelas.ANEXOS_2027_2028["I"].fim == date(2028, 12, 31)


def test_2029_nao_tem_tabela_cadastrada():
    try:
        tabelas.anexo("I", 2029, 1)
    except ValueError as erro:
        assert "01/2029" in str(erro)
    else:  # pragma: no cover - se isto passar, a recusa de 2029 não existe mais.
        raise AssertionError("não deveria haver tabela de 2029")


def test_padrao_sem_periodo_continua_sendo_a_tabela_de_2026():
    """Chamadores anteriores à DL-088 (e os da DL-075) não passam período: ficam em 2026."""
    assert tabelas.anexo("III") is tabelas.ANEXOS["III"]
    assert tabelas.anexo("I").faixa(6).aliquota_nominal == Decimal("0.19")


def test_fonte_da_tabela_de_2027_cita_o_dou_a_url_e_a_leitura():
    fonte = tabelas.anexo("I", 2027, 1).fonte
    assert "DOU 10/08/2026" in fonte
    assert "Edição 149-A" in fonte and "Seção 1 – Extra A" in fonte
    assert "https://www.in.gov.br/en/web/dou/-/resolucao-cgsn-n-190-de-4-de-agosto-de-2026" in fonte
    assert "lido em 09/10/2026" in fonte
    assert "Res. CGSN 190/2026" in tabelas.anexo("I", 2027, 1).dispositivo
    assert "LC 214/2025, art. 519" in tabelas.anexo("I", 2027, 1).dispositivo
