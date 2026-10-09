"""DL-082: o anexo da mercadoria pela descrição oficial do CFOP (decisão do arquiteto).

Regra: `revenda` → Anexo I e `producao_propria` → Anexo II, pela natureza. Para
`revenda_st_substituido`,
`substituto_st`, `monofasico`, `exportacao_direta` e `comercial_exportadora`, o anexo vem da
descrição
oficial do CFOP do item. Se a descrição não decide, o pré-DAS recusa, nomeando natureza e CFOP.

Valores esperados escritos à mão. O caso F (Anexo II com ST e exportação) roda ponta a ponta aqui.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.models import (
    ANEXO_I,
    ANEXO_II,
    NaturezaOperacaoNFe,
    anexo_da_mercadoria,
    classificacao_da_venda,
)
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

NF = NaturezaOperacaoNFe


@pytest.fixture
def empresa_a(escritorio_a):
    """Emitente das NF-e sintéticas (CNPJ_EMITENTE_A)."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Comercio CFOP DL082 Ltda", cnpj=CNPJ_EMITENTE_A
    )


# ---------------------------------------------------------------------------
# A regra, função pura (sem banco)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("natureza", "cfop", "anexo"),
    [
        # Produção com ST (5.401): "Venda de produção do estabelecimento em operação com ..." → II.
        (NF.REVENDA_ST_SUBSTITUIDO, "5401", ANEXO_II),
        # Revenda com ST (5.403 e 5.405): "Venda de mercadoria adquirida ou recebida de terceiros" →
        # I.
        (NF.REVENDA_ST_SUBSTITUIDO, "5403", ANEXO_I),
        (NF.REVENDA_ST_SUBSTITUIDO, "5405", ANEXO_I),
        # Exportação de produção (7.101) → II; de revenda (7.102) → I.
        (NF.EXPORTACAO_DIRETA, "7101", ANEXO_II),
        (NF.EXPORTACAO_DIRETA, "7102", ANEXO_I),
        # Comercial exportadora: remessa com fim específico de exportação (5.501 produção; 5.502
        # terceiros).
        (NF.COMERCIAL_EXPORTADORA, "5501", ANEXO_II),
        (NF.COMERCIAL_EXPORTADORA, "5502", ANEXO_I),
        # Substituto e monofásico: 5.101 produção → II; 5.102 terceiros → I.
        (NF.SUBSTITUTO_ST, "5101", ANEXO_II),
        (NF.SUBSTITUTO_ST, "5102", ANEXO_I),
        (NF.MONOFASICO, "5101", ANEXO_II),
        (NF.MONOFASICO, "5102", ANEXO_I),
        # Natureza fixa: revenda → I e produção própria → II, qualquer que seja o CFOP.
        (NF.REVENDA, "5101", ANEXO_I),
        (NF.PRODUCAO_PROPRIA, "5102", ANEXO_II),
        # CFOP que não decide (5.949, "Outra saída ... não especificada"): anexo None → recusa.
        (NF.REVENDA_ST_SUBSTITUIDO, "5949", None),
        (NF.EXPORTACAO_DIRETA, "5949", None),
        # CFOP fora da tabela oficial não decide.
        (NF.SUBSTITUTO_ST, "9999", None),
    ],
)
def test_anexo_da_mercadoria_segue_a_natureza_ou_o_cfop(natureza, cfop, anexo):
    assert anexo_da_mercadoria(natureza, cfop) == anexo


def test_descricoes_citadas_no_comentario_conferem_com_a_tabela_oficial():
    """Trava as descrições que o comentário de `models` cita: se a tabela mudar, este teste
    acusa."""
    assert consultar_cfop("5401").descricao.startswith("Venda de produção do estabelecimento")
    assert consultar_cfop("5403").descricao.startswith(
        "Venda de mercadoria adquirida ou recebida de terceiros"
    )
    assert consultar_cfop("5405").descricao.startswith(
        "Venda de mercadoria adquirida ou recebida de terceiros"
    )
    assert consultar_cfop("7101").descricao.startswith("Venda de produção do estabelecimento")
    assert consultar_cfop("7102").descricao.startswith(
        "Venda de mercadoria adquirida ou recebida de terceiros"
    )
    assert consultar_cfop("5501").descricao.startswith("Remessa de produção do estabelecimento")
    assert consultar_cfop("5502").descricao.startswith(
        "Remessa de mercadoria adquirida ou recebida de terceiros"
    )
    assert consultar_cfop("5949").descricao.startswith("Outra saída de mercadoria")


def test_combustivel_nao_e_mercadoria_do_corte():
    """Combustível não entra na classificação de mercadoria: o pré-DAS a recusa pela natureza."""
    assert classificacao_da_venda(NF.COMBUSTIVEL, False, "5656") is None
    assert classificacao_da_venda(NF.COMBUSTIVEL_REVENDA, False, "5656") is None


def test_classificacao_da_venda_une_o_anexo_do_cfop_e_o_segmento_da_marca():
    """Monofásico pela marca, com o anexo do CFOP: produção com ST e marca → (II, st_monofasico)."""
    assert classificacao_da_venda(NF.REVENDA_ST_SUBSTITUIDO, True, "5401") == (
        ANEXO_II,
        "st_monofasico",
    )
    assert classificacao_da_venda(NF.REVENDA_ST_SUBSTITUIDO, False, "5949") == (
        None,
        "sujeita_st",
    )


# ---------------------------------------------------------------------------
# Pelo pré-DAS real
# ---------------------------------------------------------------------------


def test_produção_com_st_cfop_5401_vai_para_o_anexo_ii(escritorio_a, usuario_gestor_a, empresa_a):
    """Produção própria com ST substituído (CFOP 5.401, CSOSN 500) → Anexo II, segmento sujeita_st.

    Esperado (à mão): RBT12 300.000 → Anexo II, 2ª faixa (nominal 7,80%, parcela 5.940,00), efetiva
    (300.000 × 7,80% − 5.940) / 300.000 = 5,82%. Receita líquida 10.000, ICMS desconsiderado.
    IRPJ 32,01; CSLL 20,37; Cofins 66,99; PIS 14,49; CPP 218,25; IPI 43,65; ICMS 0,00. Total 395,76.
    """
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=801,
        itens=[{"cfop": "5401", "vprod": "10000.00", "csosn": "500"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.REVENDA_ST_SUBSTITUIDO})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    assert anexo.anexo == "II"
    assert anexo.aliquota_efetiva == Decimal("0.0582")
    (segmento,) = anexo.segmentos
    assert segmento.segmento == "sujeita_st"
    valores = {linha.tributo: linha for linha in segmento.linhas}
    assert valores["ICMS"].desconsiderado is True
    assert valores["IRPJ"].valor == Decimal("32.01")
    assert valores["CSLL"].valor == Decimal("20.37")
    assert valores["COFINS"].valor == Decimal("66.99")
    assert valores["PIS"].valor == Decimal("14.49")
    assert valores["CPP"].valor == Decimal("218.25")
    assert valores["IPI"].valor == Decimal("43.65")
    assert resultado.total == Decimal("395.76")


def test_cfop_que_nao_decide_recusa_o_pre_das_com_natureza_e_cfop(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Revenda com ST (natureza) com CFOP 5.949: o anexo não é decidido, e o pré-DAS recusa."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=802,
        itens=[{"cfop": "5949", "vprod": "10000.00", "csosn": "500"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.REVENDA_ST_SUBSTITUIDO})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    bloqueios = {b.codigo: b.mensagem for b in erro.value.bloqueios}
    assert "anexo_da_mercadoria_a_confirmar" in bloqueios
    assert (
        "anexo da mercadoria a confirmar (natureza revenda_st_substituido, CFOP 5949)"
        in bloqueios["anexo_da_mercadoria_a_confirmar"]
    )


def test_caso_f_ponta_a_ponta_anexo_ii_com_st_e_exportacao_de_producao(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso F inteiro pelo pré-DAS real, sem o limite de natureza da versão anterior.

    RBT12 interno 900.000 (75.000 × 12, Anexo II, 4ª faixa, efetiva 8,70%): produção própria 40.000
    (5.101) e ST substituído de produção 10.000 (5.401). RBT12 externo 150.000 (12.500 × 12, 1ª
    faixa,
    4,50%): exportação de produção 20.000 (7.101).

    Esperado (à mão): interno normal 3.480,00 e ST 591,60; externo exportação 418,50. Total
    4.490,10.
    """
    empresa = cenario(empresa_a)
    janela(
        empresa,
        usuario_gestor_a,
        2026,
        6,
        interno=[75000] * 12,
        externo=[12500] * 12,
    )
    producao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=811,
        itens=[{"cfop": "5101", "vprod": "40000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, producao, {1: NF.PRODUCAO_PROPRIA})
    st_producao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=812,
        itens=[{"cfop": "5401", "vprod": "10000.00", "csosn": "500"}],
    )
    escriturar(empresa, usuario_gestor_a, st_producao, {1: NF.REVENDA_ST_SUBSTITUIDO})
    exportacao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=813,
        itens=[{"cfop": "7101", "vprod": "20000.00"}],
        id_dest="3",
    )
    escriturar(empresa, usuario_gestor_a, exportacao, {1: NF.EXPORTACAO_DIRETA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    interno = [a for a in resultado.anexos if a.mercado == "interno"]
    externo = [a for a in resultado.anexos if a.mercado == "externo"]
    assert [a.anexo for a in interno] == ["II"]
    assert [a.anexo for a in externo] == ["II"]
    por_segmento = {s.segmento: s for s in interno[0].segmentos}
    assert por_segmento["normal"].total == Decimal("3480.00")
    assert por_segmento["sujeita_st"].total == Decimal("591.60")
    (exp,) = externo[0].segmentos
    assert exp.segmento == "exportacao"
    assert exp.total == Decimal("418.50")
    assert resultado.total == Decimal("4490.10")
