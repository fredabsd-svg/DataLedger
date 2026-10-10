"""DL-075 (frente A) — tabelas do Simples como dado: conferência célula a célula.

Os números abaixo foram DIGITADOS À MÃO a partir de
docs/projeto/consultas/2026-10-08-tabelas-simples-2026.md (seção 2), e não copiados
de `simples_tabelas.py`. Este teste é a conferência independente: se a tabela do
código divergir do documento, ele reprova. A conversão de texto para fração é feita
aqui, com outra implementação (divisão por 100 de um Decimal lido de string).
"""

from datetime import date
from decimal import Decimal

from apps.fiscal import simples_tabelas as tabelas


def _pct(texto: str) -> Decimal:
    """'11,20%' → Decimal('0.1120'), por divisão exata (conversão independente da do código)."""
    return Decimal(texto.rstrip("%").replace(",", ".")) / Decimal(100)


def _rs(texto: str) -> Decimal:
    return Decimal("0.00") if texto == "–" else Decimal(texto.replace(".", "").replace(",", "."))


# Faixas: (limite superior, início da faixa, como está no documento).
LIMITES_DO_DOCUMENTO = [
    "180.000,00",
    "360.000,00",
    "720.000,00",
    "1.800.000,00",
    "3.600.000,00",
    "4.800.000,00",
]
INICIOS_DO_DOCUMENTO = [
    None,  # 1ª: "Até 180.000,00"
    "De 180.000,01",
    "De 360.000,01",
    "De 720.000,01",
    "De 1.800.000,01",
    "De 3.600.000,01",
]

# Alíquota nominal / parcela a deduzir, por faixa, como na tabela "Alíquota nominal e valor
# a deduzir, por faixa".
ALIQUOTA_E_PD = {
    "I": [
        ("4,00%", "–"),
        ("7,30%", "5.940,00"),
        ("9,50%", "13.860,00"),
        ("10,70%", "22.500,00"),
        ("14,30%", "87.300,00"),
        ("19,00%", "378.000,00"),
    ],
    "II": [
        ("4,50%", "–"),
        ("7,80%", "5.940,00"),
        ("10,00%", "13.860,00"),
        ("11,20%", "22.500,00"),
        ("14,70%", "85.500,00"),
        ("30,00%", "720.000,00"),
    ],
    "III": [
        ("6,00%", "–"),
        ("11,20%", "9.360,00"),
        ("13,50%", "17.640,00"),
        ("16,00%", "35.640,00"),
        ("21,00%", "125.640,00"),
        ("33,00%", "648.000,00"),
    ],
    "IV": [
        ("4,50%", "–"),
        ("9,00%", "8.100,00"),
        ("10,20%", "12.420,00"),
        ("14,00%", "39.780,00"),
        ("22,00%", "183.780,00"),
        ("33,00%", "828.000,00"),
    ],
    "V": [
        ("15,50%", "–"),
        ("18,00%", "4.500,00"),
        ("19,50%", "9.900,00"),
        ("20,50%", "17.100,00"),
        ("23,00%", "62.100,00"),
        ("30,50%", "540.000,00"),
    ],
}

# Repartição por tributo, por faixa, na ordem das colunas do documento. "–" = não existe.
REPARTICAO = {
    "I": [
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,74%"),
            ("PIS", "2,76%"),
            ("CPP", "41,50%"),
            ("ICMS", "34,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,74%"),
            ("PIS", "2,76%"),
            ("CPP", "41,50%"),
            ("ICMS", "34,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,74%"),
            ("PIS", "2,76%"),
            ("CPP", "42,00%"),
            ("ICMS", "33,50%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,74%"),
            ("PIS", "2,76%"),
            ("CPP", "42,00%"),
            ("ICMS", "33,50%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,74%"),
            ("PIS", "2,76%"),
            ("CPP", "42,00%"),
            ("ICMS", "33,50%"),
        ],
        [
            ("IRPJ", "13,50%"),
            ("CSLL", "10,00%"),
            ("COFINS", "28,27%"),
            ("PIS", "6,13%"),
            ("CPP", "42,10%"),
        ],
    ],
    "II": [
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "11,51%"),
            ("PIS", "2,49%"),
            ("CPP", "37,50%"),
            ("IPI", "7,50%"),
            ("ICMS", "32,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "11,51%"),
            ("PIS", "2,49%"),
            ("CPP", "37,50%"),
            ("IPI", "7,50%"),
            ("ICMS", "32,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "11,51%"),
            ("PIS", "2,49%"),
            ("CPP", "37,50%"),
            ("IPI", "7,50%"),
            ("ICMS", "32,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "11,51%"),
            ("PIS", "2,49%"),
            ("CPP", "37,50%"),
            ("IPI", "7,50%"),
            ("ICMS", "32,00%"),
        ],
        [
            ("IRPJ", "5,50%"),
            ("CSLL", "3,50%"),
            ("COFINS", "11,51%"),
            ("PIS", "2,49%"),
            ("CPP", "37,50%"),
            ("IPI", "7,50%"),
            ("ICMS", "32,00%"),
        ],
        [
            ("IRPJ", "8,50%"),
            ("CSLL", "7,50%"),
            ("COFINS", "20,96%"),
            ("PIS", "4,54%"),
            ("CPP", "23,50%"),
            ("IPI", "35,00%"),
        ],
    ],
    "III": [
        [
            ("IRPJ", "4,00%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,82%"),
            ("PIS", "2,78%"),
            ("CPP", "43,40%"),
            ("ISS", "33,50%"),
        ],
        [
            ("IRPJ", "4,00%"),
            ("CSLL", "3,50%"),
            ("COFINS", "14,05%"),
            ("PIS", "3,05%"),
            ("CPP", "43,40%"),
            ("ISS", "32,00%"),
        ],
        [
            ("IRPJ", "4,00%"),
            ("CSLL", "3,50%"),
            ("COFINS", "13,64%"),
            ("PIS", "2,96%"),
            ("CPP", "43,40%"),
            ("ISS", "32,50%"),
        ],
        [
            ("IRPJ", "4,00%"),
            ("CSLL", "3,50%"),
            ("COFINS", "13,64%"),
            ("PIS", "2,96%"),
            ("CPP", "43,40%"),
            ("ISS", "32,50%"),
        ],
        [
            ("IRPJ", "4,00%"),
            ("CSLL", "3,50%"),
            ("COFINS", "12,82%"),
            ("PIS", "2,78%"),
            ("CPP", "43,40%"),
            ("ISS", "33,50%"),
        ],
        [
            ("IRPJ", "35,00%"),
            ("CSLL", "15,00%"),
            ("COFINS", "16,03%"),
            ("PIS", "3,47%"),
            ("CPP", "30,50%"),
        ],
    ],
    "IV": [
        [
            ("IRPJ", "18,80%"),
            ("CSLL", "15,20%"),
            ("COFINS", "17,67%"),
            ("PIS", "3,83%"),
            ("ISS", "44,50%"),
        ],
        [
            ("IRPJ", "19,80%"),
            ("CSLL", "15,20%"),
            ("COFINS", "20,55%"),
            ("PIS", "4,45%"),
            ("ISS", "40,00%"),
        ],
        [
            ("IRPJ", "20,80%"),
            ("CSLL", "15,20%"),
            ("COFINS", "19,73%"),
            ("PIS", "4,27%"),
            ("ISS", "40,00%"),
        ],
        [
            ("IRPJ", "17,80%"),
            ("CSLL", "19,20%"),
            ("COFINS", "18,90%"),
            ("PIS", "4,10%"),
            ("ISS", "40,00%"),
        ],
        [
            ("IRPJ", "18,80%"),
            ("CSLL", "19,20%"),
            ("COFINS", "18,08%"),
            ("PIS", "3,92%"),
            ("ISS", "40,00%"),
        ],
        [("IRPJ", "53,50%"), ("CSLL", "21,50%"), ("COFINS", "20,55%"), ("PIS", "4,45%")],
    ],
    "V": [
        [
            ("IRPJ", "25,00%"),
            ("CSLL", "15,00%"),
            ("COFINS", "14,10%"),
            ("PIS", "3,05%"),
            ("CPP", "28,85%"),
            ("ISS", "14,00%"),
        ],
        [
            ("IRPJ", "23,00%"),
            ("CSLL", "15,00%"),
            ("COFINS", "14,10%"),
            ("PIS", "3,05%"),
            ("CPP", "27,85%"),
            ("ISS", "17,00%"),
        ],
        [
            ("IRPJ", "24,00%"),
            ("CSLL", "15,00%"),
            ("COFINS", "14,92%"),
            ("PIS", "3,23%"),
            ("CPP", "23,85%"),
            ("ISS", "19,00%"),
        ],
        [
            ("IRPJ", "21,00%"),
            ("CSLL", "15,00%"),
            ("COFINS", "15,74%"),
            ("PIS", "3,41%"),
            ("CPP", "23,85%"),
            ("ISS", "21,00%"),
        ],
        [
            ("IRPJ", "23,00%"),
            ("CSLL", "12,50%"),
            ("COFINS", "14,10%"),
            ("PIS", "3,05%"),
            ("CPP", "23,85%"),
            ("ISS", "23,50%"),
        ],
        [
            ("IRPJ", "35,00%"),
            ("CSLL", "15,50%"),
            ("COFINS", "16,44%"),
            ("PIS", "3,56%"),
            ("CPP", "29,50%"),
        ],
    ],
}

# Teto do ISS (notas (*) de III e IV): limiar, e a redistribuição aos federais.
TETO = {
    "III": (
        "14,92537%",
        [
            ("IRPJ", "6,02%"),
            ("CSLL", "5,26%"),
            ("COFINS", "19,28%"),
            ("PIS", "4,18%"),
            ("CPP", "65,26%"),
        ],
    ),
    "IV": (
        "12,5%",
        [("IRPJ", "31,33%"), ("CSLL", "32,00%"), ("COFINS", "30,13%"), ("PIS", "6,54%")],
    ),
}


def test_faixas_e_limites_conferem_com_o_documento():
    for numero in tabelas.ANEXOS:
        anexo = tabelas.anexo(numero)
        assert len(anexo.faixas) == 6
        for indice, faixa in enumerate(anexo.faixas):
            assert faixa.limite_superior == _rs(LIMITES_DO_DOCUMENTO[indice]), (numero, indice + 1)


def test_aliquota_nominal_e_parcela_a_deduzir_celula_a_celula():
    for numero, linhas in ALIQUOTA_E_PD.items():
        anexo = tabelas.anexo(numero)
        for indice, (aliquota, parcela) in enumerate(linhas):
            faixa = anexo.faixa(indice + 1)
            assert faixa.aliquota_nominal == _pct(aliquota), (numero, indice + 1)
            assert faixa.parcela_a_deduzir == _rs(parcela), (numero, indice + 1)


def test_reparticao_celula_a_celula_com_os_tributos_de_cada_anexo():
    for numero, faixas in REPARTICAO.items():
        anexo = tabelas.anexo(numero)
        assert len(faixas) == 6
        for indice, esperado in enumerate(faixas):
            faixa = anexo.faixa(indice + 1)
            transcrito = tuple((tributo, _pct(valor)) for tributo, valor in esperado)
            assert faixa.reparticao == transcrito, (numero, indice + 1)


def test_teto_do_iss_conferindo_limiar_e_redistribuicao():
    for numero, (limiar, redistribuicao) in TETO.items():
        teto = tabelas.anexo(numero).teto_iss
        assert teto is not None
        assert teto.limiar_efetiva == _pct(limiar)
        assert teto.percentual_iss == _pct("5%")
        assert teto.faixa == 5
        assert teto.redistribuicao == tuple((t, _pct(v)) for t, v in redistribuicao)
    assert tabelas.anexo("I").teto_iss is None
    assert tabelas.anexo("II").teto_iss is None
    assert tabelas.anexo("V").teto_iss is None


def test_cada_reparticao_soma_100_por_cento():
    for numero in tabelas.ANEXOS:
        for faixa in tabelas.anexo(numero).faixas:
            assert sum(valor for _t, valor in faixa.reparticao) == Decimal(1), (
                numero,
                faixa.numero,
            )
    for numero, (_limiar, redistribuicao) in TETO.items():
        assert sum(_pct(v) for _t, v in redistribuicao) == Decimal(1), numero


def test_faixas_sao_continuas():
    """Cada faixa começa em centavo acima do limite da anterior, como no documento."""
    for numero in tabelas.ANEXOS:
        faixas = tabelas.anexo(numero).faixas
        for anterior, atual in zip(faixas, faixas[1:], strict=False):
            assert atual.limite_superior > anterior.limite_superior
        for indice in range(1, 6):
            anterior = tabelas.anexo(numero).faixa(indice).limite_superior
            inicio_documento = _rs(INICIOS_DO_DOCUMENTO[indice][len("De ") :])
            assert inicio_documento == anterior + Decimal("0.01"), (numero, indice + 1)


def test_valores_sao_decimal_nunca_float():
    for numero in tabelas.ANEXOS:
        anexo = tabelas.anexo(numero)
        for faixa in anexo.faixas:
            for valor in (faixa.limite_superior, faixa.aliquota_nominal, faixa.parcela_a_deduzir):
                assert isinstance(valor, Decimal)
            for _t, valor in faixa.reparticao:
                assert isinstance(valor, Decimal)


def test_vigencia_e_fonte_de_cada_anexo():
    for numero, anexo in tabelas.ANEXOS.items():
        assert anexo.inicio == date(2018, 1, 1), numero
        assert anexo.fim == date(2026, 12, 31), numero
        assert "LC 123/2006" in anexo.dispositivo and "LC 155/2016" in anexo.dispositivo
        assert "Planalto" in anexo.fonte and "08/10/2026" in anexo.fonte


def test_tabelas_vigentes_so_entre_2018_e_2028():
    # DL-088: a vigência cadastrada passou a chegar a 2028 (tabela de 2027-2028, HI-146).
    assert tabelas.tabelas_vigentes_em(2018, 1)
    assert tabelas.tabelas_vigentes_em(2026, 12)
    assert not tabelas.tabelas_vigentes_em(2017, 12)
    assert tabelas.tabelas_vigentes_em(2028, 12)
    assert not tabelas.tabelas_vigentes_em(2029, 1)


def test_anexo_iv_nao_tem_cpp():
    assert "CPP" not in tabelas.anexo("IV").tributos
    assert "CPP" in tabelas.anexo("III").tributos


def test_primeiro_corte_e_o_ultimo_limite_do_anexo_iii_quinta_faixa():
    assert tabelas.anexo("III").faixa(5).limite_superior == Decimal("3600000.00")
