"""Testes do validador de conformidade IBS/CBS das NFS-e recebidas (DL-073,
modo AVISO). Cada teste cita o critério de aceite de
docs/planos/DL-073-validador-ibscbs.md (critérios 1 a 11).

Dados 100% SINTÉTICOS. O gerador `xml_1_01` é PRÓPRIO deste arquivo: monta o
grupo IBS/CBS do leiaute 1.01, que `xml_sinteticos.py` não compõe. Ele só
reaproveita os CNPJs e o identificador de NFS-e daquele módulo, sem editá-lo.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa
from apps.fiscal.ibscbs import (
    SITUACAO_COM_GRUPO,
    SITUACAO_LEIAUTE_SEM_GRUPO,
    SITUACAO_SEM_GRUPO,
    SITUACAO_XML_ILEGIVEL,
    avaliar_conformidade,
    conformidade_do_mes,
    ler_grupo_ibscbs,
    situacao_de_conformidade,
)
from apps.fiscal.leitor import NS_NFSE
from apps.fiscal.models import DocumentoFiscal
from apps.fiscal.services import receber_envio
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_PRESTADOR_PADRAO,
    CNPJ_TOMADOR_PADRAO,
    identificador_nfse,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Gerador próprio de NFS-e 1.01 com o grupo IBS/CBS (dados sintéticos)
# ---------------------------------------------------------------------------


def _el(nome, valor):
    """Elemento simples; `None` omite o elemento (é o que os testes de
    ausência usam)."""
    return "" if valor is None else f"<{nome}>{valor}</{nome}>"


def _caixa(nome, *partes):
    """Contêiner; some por inteiro quando nenhum filho existe."""
    conteudo = "".join(partes)
    return f"<{nome}>{conteudo}</{nome}>" if conteudo else ""


def xml_1_01(
    *,
    sufixo=1,
    d_compet="2026-10-05",
    versao="1.01",
    opsimpnac="1",
    grupo_nfse=True,
    grupo_dps=True,
    cst="000",
    cclass="000001",
    cst_nt009=None,
    cclass_nt009=None,
    v_serv="100.00",
    v_desc_incond=None,
    v_calc_ree_rep_res=None,
    v_iss_qn=None,
    v_pis=None,
    v_cofins=None,
    v_bc="100.00",
    p_ibs_uf="0.10",
    p_aliq_efet_uf=None,
    p_ibs_mun="0",
    p_aliq_efet_mun=None,
    p_cbs="0.90",
    p_aliq_efet_cbs=None,
    v_ibs_uf="0.10",
    v_ibs_mun="0.00",
    v_cbs="0.90",
    tomador=True,
) -> bytes:
    """NFS-e sintética com o grupo IBS/CBS. Os valores padrão são
    CONSISTENTES entre si: uma nota padrão não gera nenhum aviso (a
    competência padrão é 05/10/2026, 2026, e o prestador é não optante)."""
    ibs_nfse = ""
    if grupo_nfse:
        uf = _caixa("uf", _el("pIBSUF", p_ibs_uf), _el("pAliqEfetUF", p_aliq_efet_uf))
        mun = _caixa("mun", _el("pIBSMun", p_ibs_mun), _el("pAliqEfetMun", p_aliq_efet_mun))
        fed = _caixa("fed", _el("pCBS", p_cbs), _el("pAliqEfetCBS", p_aliq_efet_cbs))
        valores = _caixa(
            "valores",
            _el("vBC", v_bc),
            _el("vCalcReeRepRes", v_calc_ree_rep_res),
            uf,
            mun,
            fed,
        )
        gibs = _caixa(
            "gIBS",
            _el("vIBSTot", "0.10"),
            _caixa("gIBSUFTot", _el("vIBSUF", v_ibs_uf)),
            _caixa("gIBSMunTot", _el("vIBSMun", v_ibs_mun)),
        )
        gcbs = _caixa("gCBS", _el("vCBS", v_cbs))
        tot = _caixa("totCIBS", _el("vTotNF", "100.00"), gibs, gcbs)
        ibs_nfse = _caixa(
            "IBSCBS",
            _el("cLocalidadeIncid", "3550308"),
            _el("xLocalidadeIncid", "Município Sintético"),
            valores,
            tot,
        )

    regtrib = _caixa("regTrib", _el("opSimpNac", opsimpnac))
    prest = f"<prest><CNPJ>{CNPJ_PRESTADOR_PADRAO}</CNPJ>{regtrib}</prest>"
    toma = (
        f"<toma><CNPJ>{CNPJ_TOMADOR_PADRAO}</CNPJ><xNome>Tomador Sintético Ltda</xNome></toma>"
        if tomador
        else ""
    )
    piscofins = _caixa("piscofins", _el("vPis", v_pis), _el("vCofins", v_cofins))
    valores_dps = "".join(
        [
            "<valores>",
            f"<vServPrest><vServ>{v_serv}</vServ></vServPrest>",
            _caixa("vDescCondIncond", _el("vDescIncond", v_desc_incond)),
            "<trib><tribMun><tpRetISSQN>1</tpRetISSQN></tribMun>",
            _caixa("tribFed", piscofins),
            "</trib>",
            "</valores>",
        ]
    )

    ibs_dps = ""
    if grupo_dps:
        trib_conteudo = (
            _caixa("gIBSCBS", _el("CST", cst), _el("cClassTrib", cclass))
            + _el("CST", cst_nt009)
            + _el("cClassTrib", cclass_nt009)
        )
        ibs_dps = _caixa(
            "IBSCBS",
            _el("finNFSe", "0"),
            _el("indDest", "1"),
            _caixa("valores", _caixa("trib", trib_conteudo)),
        )

    dps_id = "DPS" + "0" * 42
    dps = (
        f'<DPS versao="{versao}"><infDPS Id="{dps_id}">'
        "<tpAmb>1</tpAmb>"
        f"<dhEmi>{d_compet}T10:00:00-03:00</dhEmi>"
        f"<dCompet>{d_compet}</dCompet>"
        f"{prest}{toma}{valores_dps}{ibs_dps}"
        "</infDPS></DPS>"
    )
    corpo = (
        f'<NFSe xmlns="{NS_NFSE}" versao="{versao}">'
        f'<infNFSe Id="{identificador_nfse(sufixo)}">'
        f"<nNFSe>{sufixo}</nNFSe>"
        "<emit>"
        f"<CNPJ>{CNPJ_PRESTADOR_PADRAO}</CNPJ><xNome>Prestador Sintético Ltda</xNome>"
        "</emit>"
        "<valores>"
        f"{_el('vISSQN', v_iss_qn)}"
        "<vLiq>100.00</vLiq>"
        "</valores>"
        f"{ibs_nfse}{dps}"
        "</infNFSe></NFSe>"
    )
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + corpo).encode("utf-8")


def _nota(xml: bytes, d_compet: date, versao: str = "1.01"):
    """Objeto com os atributos que o validador lê de um `DocumentoFiscal`.
    Usado nos testes de regra (sem banco); o caminho real está nos testes de
    tela e de `conformidade_do_mes`."""
    return SimpleNamespace(versao=versao, xml_original=xml, d_competencia=d_compet)


def _avisos(xml: bytes, d_compet: date = date(2026, 10, 5), versao: str = "1.01"):
    return avaliar_conformidade(_nota(xml, d_compet, versao))


def _codigos(avisos):
    return {aviso.codigo for aviso in avisos}


# ---------------------------------------------------------------------------
# Critério 1 — leiaute 1.00: "sem grupo", nunca "desconforme"
# ---------------------------------------------------------------------------


def test_criterio_1_nota_1_00_e_leiaute_sem_grupo_sem_nenhum_aviso():
    # Competência de 2026 e prestador não optante: se o validador tratasse a
    # 1.00 como 1.01, esta nota geraria `grupo_ausente`. Não deve gerar nada.
    xml = xml_1_01(versao="1.00", grupo_nfse=False, grupo_dps=False)
    nota = _nota(xml, date(2026, 10, 5), versao="1.00")
    assert situacao_de_conformidade(nota) == SITUACAO_LEIAUTE_SEM_GRUPO
    assert avaliar_conformidade(nota) == []


# ---------------------------------------------------------------------------
# Critério 2 — presença, com a fronteira de 01/10/2026
# ---------------------------------------------------------------------------


def test_criterio_2_sem_grupo_nao_optante_a_partir_de_01_10_avisa_com_cronograma():
    xml = xml_1_01(grupo_nfse=False, grupo_dps=False, d_compet="2026-10-01", opsimpnac="1")
    avisos = _avisos(xml, date(2026, 10, 1))
    ausencia = [a for a in avisos if a.codigo == "grupo_ausente"]
    assert len(ausencia) == 1
    assert "01/10/2026" in ausencia[0].mensagem
    assert "01/12/2026" in ausencia[0].mensagem
    assert "15.1" in ausencia[0].fonte


def test_criterio_2_fronteira_30_09_nao_avisa_ausencia():
    xml = xml_1_01(grupo_nfse=False, grupo_dps=False, d_compet="2026-09-30", opsimpnac="1")
    assert "grupo_ausente" not in _codigos(_avisos(xml, date(2026, 9, 30)))


def test_criterio_2_mesma_nota_de_setembro_de_2026_nao_avisa_ausencia():
    xml = xml_1_01(grupo_nfse=False, grupo_dps=False, d_compet="2026-09-15", opsimpnac="1")
    assert "grupo_ausente" not in _codigos(_avisos(xml, date(2026, 9, 15)))


# ---------------------------------------------------------------------------
# Critério 3 — prestador optante do Simples não recebe aviso de ausência em 2026
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("opsimpnac", ["2", "3"])
def test_criterio_3_optante_do_simples_em_2026_nao_avisa_ausencia(opsimpnac):
    xml = xml_1_01(grupo_nfse=False, grupo_dps=False, opsimpnac=opsimpnac)
    codigos = _codigos(_avisos(xml))
    assert "grupo_ausente" not in codigos
    assert "regime_nao_informado" not in codigos


def test_regime_ausente_sem_grupo_pede_conferencia_em_vez_de_presumir():
    xml = xml_1_01(grupo_nfse=False, grupo_dps=False, opsimpnac=None)
    avisos = _avisos(xml)
    codigos = _codigos(avisos)
    assert "regime_nao_informado" in codigos
    assert "grupo_ausente" not in codigos
    texto = next(a.mensagem for a in avisos if a.codigo == "regime_nao_informado")
    assert "regime do prestador não informado na nota — conferir" in texto


def test_regime_ausente_com_grupo_presente_nao_gera_aviso_de_regime():
    # Presença só é cobrada quando o grupo falta. Com o grupo presente, o
    # regime não entra na conta.
    xml = xml_1_01(opsimpnac=None)
    assert "regime_nao_informado" not in _codigos(_avisos(xml))


# ---------------------------------------------------------------------------
# Critério 4 — CST e cClassTrib nas DUAS posições e no formato
# ---------------------------------------------------------------------------


def test_criterio_4_codigos_validos_na_posicao_de_producao_nao_avisam():
    assert _avisos(xml_1_01()) == []


def test_criterio_4_codigos_validos_na_posicao_da_nt009_nao_avisam():
    xml = xml_1_01(cst=None, cclass=None, cst_nt009="000", cclass_nt009="000001")
    codigos = _codigos(_avisos(xml))
    assert not codigos & {"cst_ausente", "cst_formato", "cclasstrib_ausente", "cclasstrib_formato"}


def test_criterio_4_cst_com_dois_digitos_avisa_formato():
    assert "cst_formato" in _codigos(_avisos(xml_1_01(cst="00")))


def test_criterio_4_cclasstrib_com_cinco_digitos_avisa_formato():
    assert "cclasstrib_formato" in _codigos(_avisos(xml_1_01(cclass="00001")))


def test_criterio_4_cst_com_letra_avisa_formato():
    assert "cst_formato" in _codigos(_avisos(xml_1_01(cst="0A0")))


def test_criterio_4_cst_ausente_nas_duas_posicoes_avisa():
    xml = xml_1_01(cst=None, cclass=None, cst_nt009=None, cclass_nt009=None)
    codigos = _codigos(_avisos(xml))
    assert {"cst_ausente", "cclasstrib_ausente"} <= codigos


def test_criterio_4_cst_diferente_entre_as_posicoes_avisa_divergencia():
    assert "cst_divergente" in _codigos(_avisos(xml_1_01(cst="000", cst_nt009="010")))


def test_criterio_4_codigos_nao_sao_cobrados_sem_grupo_na_dps():
    xml = xml_1_01(grupo_dps=False, cst=None, cclass=None)
    assert not _codigos(_avisos(xml)) & {"cst_ausente", "cclasstrib_ausente"}


# ---------------------------------------------------------------------------
# Critério 5 — alíquotas de teste de 2026
# ---------------------------------------------------------------------------


def test_criterio_5_cbs_diferente_da_de_teste_avisa_com_esperado_e_fonte():
    avisos = _avisos(xml_1_01(p_cbs="0.95", v_cbs="0.95"))
    cbs = [a for a in avisos if a.codigo == "aliquota_cbs"]
    assert len(cbs) == 1
    assert "0,90" in cbs[0].mensagem
    assert "art. 346" in cbs[0].fonte


def test_criterio_5_aliquotas_certas_nao_avisam():
    codigos = _codigos(_avisos(xml_1_01(p_cbs="0.90", p_ibs_uf="0.10", p_ibs_mun="0")))
    assert not codigos & {"aliquota_cbs", "aliquota_ibs_uf", "aliquota_ibs_mun"}


def test_criterio_5_0_9_e_0_90_sao_a_mesma_aliquota():
    assert "aliquota_cbs" not in _codigos(_avisos(xml_1_01(p_cbs="0.9", v_cbs="0.9")))


def test_criterio_5_ibs_uf_e_municipal_diferentes_avisam_cada_uma():
    xml = xml_1_01(p_ibs_uf="0.12", v_ibs_uf="0.12", p_ibs_mun="0.05", v_ibs_mun="0.05")
    codigos = _codigos(_avisos(xml))
    assert {"aliquota_ibs_uf", "aliquota_ibs_mun"} <= codigos


def test_criterio_5_aliquota_de_2027_nao_e_conferida_pelo_teste_de_2026():
    xml = xml_1_01(d_compet="2027-03-10", p_cbs="0.95", v_cbs="0.95")
    assert "aliquota_cbs" not in _codigos(_avisos(xml, date(2027, 3, 10)))


# ---------------------------------------------------------------------------
# Critério 6 — aritmética, com a fronteira de R$ 0,01
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("v_cbs", ["0.89", "0.90", "0.91", "0.9"])
def test_criterio_6_vcbs_dentro_de_um_centavo_passa(v_cbs):
    assert "valor_cbs" not in _codigos(_avisos(xml_1_01(v_cbs=v_cbs)))


@pytest.mark.parametrize("v_cbs", ["0.88", "0.92"])
def test_criterio_6_vcbs_com_dois_centavos_de_diferenca_avisa(v_cbs):
    assert "valor_cbs" in _codigos(_avisos(xml_1_01(v_cbs=v_cbs)))


@pytest.mark.parametrize("v_ibs_uf", ["0.09", "0.11"])
def test_criterio_6_vibsuf_dentro_de_um_centavo_passa(v_ibs_uf):
    assert "valor_ibs_uf" not in _codigos(_avisos(xml_1_01(v_ibs_uf=v_ibs_uf)))


@pytest.mark.parametrize("v_ibs_uf", ["0.08", "0.12"])
def test_criterio_6_vibsuf_com_dois_centavos_de_diferenca_avisa(v_ibs_uf):
    assert "valor_ibs_uf" in _codigos(_avisos(xml_1_01(v_ibs_uf=v_ibs_uf)))


def test_criterio_6_vibsmun_com_aliquota_zero_fronteira_de_um_e_dois_centavos():
    assert "valor_ibs_mun" not in _codigos(_avisos(xml_1_01(v_ibs_mun="0.01")))
    assert "valor_ibs_mun" in _codigos(_avisos(xml_1_01(v_ibs_mun="0.02")))


def test_criterio_6_aliquota_efetiva_informada_substitui_a_nominal():
    # NT 009: vCBS = vBC x (pCBS ou pAliqEfetCBS). Com pAliqEfetCBS 0,50, o
    # valor certo é 0,50 e não 0,90.
    xml = xml_1_01(p_aliq_efet_cbs="0.50", v_cbs="0.50")
    assert "valor_cbs" not in _codigos(_avisos(xml))
    assert "valor_cbs" in _codigos(_avisos(xml_1_01(p_aliq_efet_cbs="0.50", v_cbs="0.90")))


def test_criterio_6_aliquota_efetiva_zero_nao_cai_para_a_nominal():
    # Regressão: `Decimal("0")` é falso. Com `or`, a efetiva zero seria trocada
    # pela nominal 0,90 e esta nota (valor 0,00 correto) geraria aviso falso.
    xml = xml_1_01(p_aliq_efet_cbs="0.00", v_cbs="0.00")
    assert "valor_cbs" not in _codigos(_avisos(xml))


# ---------------------------------------------------------------------------
# Critério 7 — vBC contra a fórmula da E1530 de 2026
# ---------------------------------------------------------------------------

# vServ 100,00 − vDescIncond 5,00 − vCalcReeRepRes 2,00 − vISSQN 3,00 −
# vPis 0,65 − vCofins 3,00 = 86,35. vCBS e vIBSUF acompanham a base 86,35
# (0,78 e 0,09 ficam dentro de um centavo), para o teste da E1530 ficar isolado.
_E1530 = dict(
    v_serv="100.00",
    v_desc_incond="5.00",
    v_calc_ree_rep_res="2.00",
    v_iss_qn="3.00",
    v_pis="0.65",
    v_cofins="3.00",
    v_cbs="0.78",
    v_ibs_uf="0.09",
)


@pytest.mark.parametrize("v_bc", ["86.35", "86.36", "86.34"])
def test_criterio_7_vbc_dentro_de_um_centavo_da_formula_passa(v_bc):
    assert "base_calculo" not in _codigos(_avisos(xml_1_01(v_bc=v_bc, **_E1530)))


@pytest.mark.parametrize("v_bc", ["86.37", "86.33"])
def test_criterio_7_vbc_com_dois_centavos_fora_da_formula_avisa(v_bc):
    avisos = _avisos(xml_1_01(v_bc=v_bc, **_E1530))
    assert "base_calculo" in _codigos(avisos)
    assert "E1530" in next(a.fonte for a in avisos if a.codigo == "base_calculo")


def test_criterio_7_termo_opcional_ausente_conta_como_zero():
    # Sem deduções opcionais, a base é o próprio vServ.
    assert "base_calculo" not in _codigos(_avisos(xml_1_01(v_serv="100.00", v_bc="100.00")))
    assert "base_calculo" in _codigos(_avisos(xml_1_01(v_serv="100.00", v_bc="90.00")))


def test_criterio_7_formula_de_2026_nao_e_aplicada_em_2027():
    xml = xml_1_01(d_compet="2027-01-15", v_serv="100.00", v_bc="90.00")
    assert "base_calculo" not in _codigos(_avisos(xml, date(2027, 1, 15)))


# ---------------------------------------------------------------------------
# Critério 8 — decimais como Decimal, aceitando 0.9 e 0.90
# ---------------------------------------------------------------------------


def test_criterio_8_decimais_sao_decimal_e_0_9_igual_a_0_90():
    grupo_curto = ler_grupo_ibscbs(xml_1_01(p_cbs="0.9"), "1.01")
    grupo_longo = ler_grupo_ibscbs(xml_1_01(p_cbs="0.90"), "1.01")
    assert grupo_curto.p_cbs == grupo_longo.p_cbs == Decimal("0.90")
    assert type(grupo_curto.p_cbs) is Decimal
    assert type(grupo_curto.v_bc) is Decimal


def test_criterio_8_valor_com_virgula_vira_aviso_de_formato_e_nao_excecao():
    grupo = ler_grupo_ibscbs(xml_1_01(p_cbs="0,90"), "1.01")
    assert grupo.p_cbs is None
    assert "NFSe/infNFSe/IBSCBS/valores/fed/pCBS" in grupo.invalidos
    assert "valor_invalido" in _codigos(_avisos(xml_1_01(p_cbs="0,90")))


def test_criterio_8_valor_negativo_vira_aviso_de_formato():
    assert "valor_invalido" in _codigos(_avisos(xml_1_01(v_cbs="-0.90")))


# ---------------------------------------------------------------------------
# Critério 9 — XML malformado ou sem o elemento esperado: aviso nomeado
# ---------------------------------------------------------------------------

_NS_ATR = f'xmlns="{NS_NFSE}"'


@pytest.mark.parametrize(
    "xml",
    [
        b"",
        f'<NFSe {_NS_ATR} versao="1.01"><infNFSe'.encode(),
        f'<NFSe {_NS_ATR} versao="1.01"></NFSe>'.encode(),
        f'<evento {_NS_ATR} versao="1.01"></evento>'.encode(),
        b'<?xml version="1.0"?><!DOCTYPE NFSe [<!ENTITY x "y">]>'
        + f'<NFSe {_NS_ATR} versao="1.01">&x;</NFSe>'.encode(),
    ],
)
def test_criterio_9_xml_ilegivel_vira_aviso_nomeado_sem_excecao(xml):
    nota = _nota(xml, date(2026, 10, 5))
    assert situacao_de_conformidade(nota) == SITUACAO_XML_ILEGIVEL
    avisos = avaliar_conformidade(nota)
    assert _codigos(avisos) == {"xml_ilegivel"}
    assert avisos[0].mensagem.startswith("XML não pôde ser lido")
    assert avisos[0].fonte


def test_criterio_9_leitura_de_xml_ilegivel_nao_levanta_excecao():
    grupo = ler_grupo_ibscbs(b"<NFSe", "1.01")
    assert grupo.erro_leitura is not None


def test_criterio_9_elemento_esperado_ausente_e_nomeado_pelo_caminho():
    avisos = _avisos(xml_1_01(v_ibs_uf=None))
    ausentes = [a for a in avisos if a.codigo == "elemento_ausente"]
    assert len(ausentes) == 1
    assert "NFSe/infNFSe/IBSCBS/totCIBS/gIBS/gIBSUFTot/vIBSUF" in ausentes[0].mensagem
    # Sem vIBSUF, a conferência dele não é feita e não aparece como erro.
    assert "valor_ibs_uf" not in _codigos(avisos)


def test_criterio_9_base_ausente_nao_gera_conta_com_zero():
    avisos = _avisos(xml_1_01(v_bc=None))
    codigos = _codigos(avisos)
    assert "elemento_ausente" in codigos
    assert "base_calculo" not in codigos
    assert "valor_cbs" not in codigos


def test_criterio_9_situacao_de_nota_com_grupo_e_com_grupo_presente():
    assert situacao_de_conformidade(_nota(xml_1_01(), date(2026, 10, 5))) == SITUACAO_COM_GRUPO
    xml_sem = xml_1_01(grupo_nfse=False, grupo_dps=False)
    assert situacao_de_conformidade(_nota(xml_sem, date(2026, 10, 5))) == SITUACAO_SEM_GRUPO


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"grupo_nfse": False, "grupo_dps": True},
        {"grupo_nfse": True, "grupo_dps": False},
        {"opsimpnac": None},
        {"p_cbs": "0.95", "v_cbs": "0.95"},
        {"v_ibs_uf": None, "v_bc": None},
        {"cst": "0A", "cclass": None},
    ],
)
def test_todo_aviso_tem_codigo_mensagem_e_fonte(kwargs):
    for aviso in _avisos(xml_1_01(**kwargs)):
        assert aviso.codigo
        assert aviso.mensagem
        assert aviso.fonte


# ---------------------------------------------------------------------------
# Banco: isolamento, permissão, tela e contagem de consultas (critérios 10 e 11)
# ---------------------------------------------------------------------------


def _usuario_com_papel(escritorio, papel, nome):
    usuario = get_user_model().objects.create_user(
        username=nome,
        email=f"{nome}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _receber(escritorio, usuario, xml):
    return receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=xml, nome_arquivo="nota-sintetica.xml"
    )


def _documento(escritorio, sufixo):
    return DocumentoFiscal.objects.get(
        escritorio=escritorio, identificador=identificador_nfse(sufixo)
    )


def test_criterio_10_conformidade_do_mes_nao_mistura_escritorios(
    escritorio_a, escritorio_b, empresa_a, usuario_gestor_a
):
    # O mesmo CNPJ de prestador existe nos DOIS escritórios (DE-041). A
    # conferência de A nunca pode trazer a nota recebida por B.
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Prestadora B", cnpj=CNPJ_PRESTADOR_PADRAO
    )
    usuario_b = _usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-dl073-b")
    _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=1))
    _receber(escritorio_b, usuario_b, xml_1_01(sufixo=2))

    notas = conformidade_do_mes(empresa_a, 2026, 10)
    assert [nota.documento.identificador for nota in notas] == [identificador_nfse(1)]


def test_criterio_10_empresa_de_outro_escritorio_e_404(client, usuario_gestor_a, empresa_b):
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_b.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 404


def test_criterio_10_cliente_recebe_403(client, escritorio_a, empresa_a):
    cliente = _usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-dl073")
    client.force_login(cliente)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 403


def test_criterio_10_paralegal_consulta_a_conferencia(client, escritorio_a, empresa_a):
    paralegal = _usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-dl073")
    client.force_login(paralegal)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 200


def test_criterio_10_sem_escritorio_nao_mostra_notas(client, usuario_sem_vinculo):
    client.force_login(usuario_sem_vinculo)
    resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"))
    assert resposta.status_code == 200
    assert "fiscal/conformidade_ibscbs.html" not in [t.name for t in resposta.templates]


def test_tela_conformidade_ibscbs_e_acessivel(client, usuario_gestor_a, empresa_a):
    """Cobertura da tela de conferência, exigida pela guarda
    `test_toda_rota_do_produto_esta_coberta_ou_excluida` (registrada como
    `fiscal_web:conformidade_ibscbs` em NOMES_DE_TELA_FISCAL_FORA_DA_
    CONTABILIDADE, em apps/contabilidade/tests/test_dl024_atalhos_e_
    acessibilidade.py). Com empresa e competência, para a tabela e os avisos
    entrarem na checagem."""
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 200
    assert "fiscal/conformidade_ibscbs.html" in [t.name for t in resposta.templates]
    assert_moldura_acessivel(resposta.content.decode())


def test_tela_exige_login(client):
    resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"))
    assert resposta.status_code == 302


def test_tela_sem_parametros_mostra_formulario_e_avisos_de_conferencia(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"))
    assert resposta.status_code == 200
    assert "fiscal/conformidade_ibscbs.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "CONFERÊNCIA" in conteudo
    assert "cClassTrib na tabela oficial" in conteudo
    assert "não é verificada nesta etapa" in conteudo


def test_tela_lista_a_nota_com_aviso_e_a_fonte(client, usuario_gestor_a, empresa_a):
    _receber(
        empresa_a.escritorio,
        usuario_gestor_a,
        xml_1_01(sufixo=3, grupo_nfse=False, grupo_dps=False, d_compet="2026-10-05"),
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Sem grupo IBS/CBS em nota de competência a partir de 01/10/2026" in conteudo
    # Autoescape do Django: "P&R" sai como "P&amp;R" no HTML.
    assert "Fonte: P&amp;R NFS-e v1.1, item 15.1" in conteudo
    assert "<caption" in conteudo


def test_tela_mostra_nota_1_00_como_leiaute_sem_grupo_e_sem_aviso(
    client, usuario_gestor_a, empresa_a
):
    _receber(
        empresa_a.escritorio,
        usuario_gestor_a,
        xml_1_01(sufixo=4, versao="1.00", grupo_nfse=False, grupo_dps=False),
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    conteudo = resposta.content.decode()
    assert SITUACAO_LEIAUTE_SEM_GRUPO in conteudo
    assert "Sem aviso." in conteudo


def test_tela_sem_notas_no_mes_mostra_estado_vazio(client, usuario_gestor_a, empresa_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(
        reverse("fiscal_web:conformidade_ibscbs"),
        {"empresa": empresa_a.id, "ano": "2026", "mes": "10"},
    )
    assert resposta.status_code == 200
    assert "Nenhuma nota de prestação desta empresa em 10/2026." in resposta.content.decode()


@pytest.mark.parametrize(
    "parametros",
    [
        {"empresa": "abc", "ano": "2026", "mes": "10"},
        {"empresa": "", "ano": "2026", "mes": "10"},
        {"ano": "2026", "mes": "13"},
        {"ano": "abc", "mes": "10"},
    ],
)
def test_tela_com_entrada_invalida_devolve_400_sem_500(client, usuario_gestor_a, parametros):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"), parametros)
    assert resposta.status_code == 400


def test_criterio_11_consulta_do_mes_custa_uma_consulta_com_2_e_com_20_notas(
    escritorio_a, empresa_a, usuario_gestor_a
):
    for sufixo in (1, 2):
        _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=sufixo))
    with CaptureQueriesContext(connection) as com_2:
        notas_2 = conformidade_do_mes(empresa_a, 2026, 10)
    for sufixo in range(3, 21):
        _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=sufixo))
    with CaptureQueriesContext(connection) as com_20:
        notas_20 = conformidade_do_mes(empresa_a, 2026, 10)

    assert len(notas_2) == 2
    assert len(notas_20) == 20
    assert len(com_2.captured_queries) == 1
    assert len(com_20.captured_queries) == 1


def test_criterio_11_a_tela_custa_o_mesmo_com_2_e_com_20_notas(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    parametros = {"empresa": empresa_a.id, "ano": "2026", "mes": "10"}
    _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=1))
    _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=2))
    client.force_login(usuario_gestor_a)
    # Primeira requisição: grava a escolha de escritório na sessão. Só depois
    # de ela o custo de cada requisição fica estável; por isso a medição vem
    # a seguir, e não nesta.
    client.get(reverse("fiscal_web:conformidade_ibscbs"), parametros)

    with CaptureQueriesContext(connection) as com_2:
        resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"), parametros)
    assert resposta.status_code == 200

    for sufixo in range(3, 21):
        _receber(escritorio_a, usuario_gestor_a, xml_1_01(sufixo=sufixo))
    with CaptureQueriesContext(connection) as com_20:
        resposta = client.get(reverse("fiscal_web:conformidade_ibscbs"), parametros)
    assert resposta.status_code == 200
    assert resposta.content.decode().count("<tr>") >= 21  # cabeçalho + 20 notas

    assert len(com_2.captured_queries) == len(com_20.captured_queries)
