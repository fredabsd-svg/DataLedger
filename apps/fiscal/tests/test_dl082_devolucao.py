"""DL-082 (frente A): devolução deduz SÓ dentro do segmento da mercadoria devolvida (HI-129,
HI-130).

Valores escritos à mão. O saldo de devolução é lido pela apuração real do mês (`mercadoria_do_mes` e
`composicao_do_mes`), e o pré-DAS recusa a devolução sem segmento confirmado (critério 4).
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    ANEXO_E_SEGMENTO_DA_DEVOLUCAO,
    ANEXO_I,
    ANEXO_II,
    ItemNFe,
    NaturezaOperacaoNFe,
    SegmentoDevolucao,
)
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

NF = NaturezaOperacaoNFe


@pytest.fixture
def empresa_a(escritorio_a):
    """Emitente das NF-e sintéticas (CNPJ_EMITENTE_A). Ver o módulo de cálculo (DL-082)."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Comercio Devolucao DL082 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _por_segmento(apuracao, mercado, anexo):
    return {
        (s.anexo, s.segmento): s
        for s in apuracao.segmentos
        if s.mercado == mercado and s.anexo == anexo
    }


def test_devolucao_de_revenda_deduz_do_segmento_normal_do_anexo_i(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Venda de revenda de 100.000 em junho; devolução de 20.000 de revenda (CFOP 1.202) confirmada
    como `revenda` (Anexo I, normal). Esperado (à mão): o segmento normal segrega 80.000; bruto
    100.000, deduzido 20.000. Alíquota 5,32% (RBT12 300.000): total 80.000 × 5,32% = 4.256,00."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=301,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: NF.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=302,
        itens=[{"cfop": "1202", "vprod": "20000.00"}],
        devolucao=True,
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        devolucao,
        {1: NF.DEVOLUCAO_VENDA},
        segmentos={1: SegmentoDevolucao.REVENDA},
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    (anexo,) = resultado.anexos
    (segmento,) = anexo.segmentos
    assert (segmento.segmento, segmento.bruto, segmento.deduzido) == (
        "normal",
        Decimal("100000.00"),
        Decimal("20000.00"),
    )
    assert segmento.receita == Decimal("80000.00")
    assert resultado.total == Decimal("4256.00")


def test_devolucao_de_st_nao_deduz_da_venda_normal_e_o_saldo_fica_no_seu_segmento(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Maio: devolução de 20.000 de ST (CSOSN 500, `revenda_st`), sem venda de ST. Junho: venda
    normal
    de 50.000 e venda de ST de 30.000.

    Esperado (à mão): o saldo de 20.000 da devolução de ST NÃO é consumido pela venda normal; deduz
    20.000 da venda de ST (30.000 → líquido 10.000), e a venda normal fica com 50.000 inteiros.
    """
    empresa = cenario(empresa_a)
    devolucao_de_maio = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=303,
        itens=[{"cfop": "1411", "vprod": "20000.00", "csosn": "500"}],
        devolucao=True,
        dh_emi="2026-05-10T10:00:00-03:00",
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        devolucao_de_maio,
        {1: NF.DEVOLUCAO_VENDA},
        segmentos={1: SegmentoDevolucao.REVENDA_ST},
    )
    venda_normal = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=304,
        itens=[{"cfop": "5102", "vprod": "50000.00"}],
        dh_emi="2026-06-10T10:00:00-03:00",
    )
    escriturar(empresa, usuario_gestor_a, venda_normal, {1: NF.REVENDA})
    venda_st = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=305,
        itens=[{"cfop": "5405", "vprod": "30000.00", "csosn": "500"}],
        dh_emi="2026-06-11T10:00:00-03:00",
    )
    escriturar(empresa, usuario_gestor_a, venda_st, {1: NF.REVENDA_ST_SUBSTITUIDO})

    junho = _por_segmento(servico_receita.mercadoria_do_mes(empresa, 2026, 6), "interno", ANEXO_I)

    assert junho[(ANEXO_I, "normal")].bruto == Decimal("50000.00")
    assert junho[(ANEXO_I, "normal")].deduzido == Decimal("0.00")
    assert junho[(ANEXO_I, "sujeita_st")].bruto == Decimal("30000.00")
    assert junho[(ANEXO_I, "sujeita_st")].deduzido == Decimal("20000.00")
    assert junho[(ANEXO_I, "sujeita_st")].liquido == Decimal("10000.00")
    # O saldo de maio, de ST, está ao fim de junho, no mercado interno.
    composicao = servico_receita.composicao_do_mes(empresa, 2026, 6)
    assert composicao.interno.saldo_transportado == Decimal("0.00")


def test_saldo_de_devolucao_nao_passa_para_outro_segmento_e_fica_transportado(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Devolução de 20.000 de ST em maio, sem venda de ST depois: a venda normal de junho (50.000)
    não a consome, e o saldo aparece como transportado na composição do mês de maio.

    Esperado (à mão): saldo transportado de maio = 20.000,00; deduzido em junho = 0,00.
    """
    empresa = cenario(empresa_a)
    devolucao_de_maio = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=311,
        itens=[{"cfop": "1411", "vprod": "20000.00", "csosn": "500"}],
        devolucao=True,
        dh_emi="2026-05-10T10:00:00-03:00",
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        devolucao_de_maio,
        {1: NF.DEVOLUCAO_VENDA},
        segmentos={1: SegmentoDevolucao.REVENDA_ST},
    )
    venda_normal = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=312,
        itens=[{"cfop": "5102", "vprod": "50000.00"}],
        dh_emi="2026-06-10T10:00:00-03:00",
    )
    escriturar(empresa, usuario_gestor_a, venda_normal, {1: NF.REVENDA})

    maio = servico_receita.composicao_do_mes(empresa, 2026, 5)
    junho = servico_receita.composicao_do_mes(empresa, 2026, 6)

    assert maio.interno.saldo_transportado == Decimal("20000.00")
    assert junho.interno.saldo_entrada == Decimal("20000.00")
    assert junho.interno.deduzido == Decimal("0.00")
    assert junho.interno.total == Decimal("50000.00")


def test_devolucao_sem_segmento_confirmado_recusa_o_pre_das_do_mes(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Devolução de revenda de 20.000 SEM segmento confirmado. O pré-DAS recusa o mês com o motivo
    nomeado. Não há rateio: a dedução não é alocada a segmento nenhum (HI-129)."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=321,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: NF.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=322,
        itens=[{"cfop": "1202", "vprod": "20000.00"}],
        devolucao=True,
    )
    escriturar(empresa, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_VENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    bloqueios = {b.codigo: b.mensagem for b in erro.value.bloqueios}
    assert "devolucao_sem_segmento_confirmado" in bloqueios
    assert "sem segmento confirmado" in bloqueios["devolucao_sem_segmento_confirmado"]
    assert "322" in bloqueios["devolucao_sem_segmento_confirmado"]


def test_devolucao_com_segmento_de_exportacao_so_com_cfop_3(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Confirmação de segmento: exportação exige CFOP 3.xxx, e CFOP 3.xxx exige exportação."""
    empresa = cenario(empresa_a)
    devolucao_interna = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=331,
        itens=[{"cfop": "1202", "vprod": "1000.00"}],
        devolucao=True,
    )
    esc = servico_nfe.criar_rascunho(vinculo(devolucao_interna, empresa), usuario=usuario_gestor_a)
    item = ItemNFe.objects.get(documento=devolucao_interna)
    servico_nfe.definir_natureza(esc, NF.DEVOLUCAO_VENDA, [item.pk], usuario=usuario_gestor_a)
    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.definir_segmento_devolucao(
            esc, [item.pk], SegmentoDevolucao.REVENDA_EXPORTACAO, usuario=usuario_gestor_a
        )
    assert "CFOP 3.xxx" in erro.value.mensagem


def test_segmento_da_devolucao_so_se_aplica_a_devolucao_de_venda(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Confirmar segmento num item que é venda é recusado, nomeando o problema."""
    empresa = cenario(empresa_a)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=341,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = servico_nfe.criar_rascunho(vinculo(venda, empresa), usuario=usuario_gestor_a)
    item = ItemNFe.objects.get(documento=venda)
    servico_nfe.definir_natureza(esc, NF.REVENDA, [item.pk], usuario=usuario_gestor_a)
    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.definir_segmento_devolucao(
            esc, [item.pk], SegmentoDevolucao.REVENDA, usuario=usuario_gestor_a
        )
    assert "não é devolução de venda" in erro.value.mensagem


# ---------------------------------------------------------------------------
# Sugestão do segmento da devolução (HI-129): função pura, pelo CFOP, CSOSN/CST e marca
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cfop", "csosn", "cst", "monofasico", "esperado"),
    [
        ("1201", "102", None, False, SegmentoDevolucao.PRODUCAO),
        ("1202", "102", None, False, SegmentoDevolucao.REVENDA),
        ("1410", "102", None, False, SegmentoDevolucao.PRODUCAO_ST),
        ("1411", "102", None, False, SegmentoDevolucao.REVENDA_ST),
        ("1202", "500", None, False, SegmentoDevolucao.REVENDA_ST),
        ("1201", None, "60", False, SegmentoDevolucao.PRODUCAO_ST),
        ("1202", "102", None, True, SegmentoDevolucao.REVENDA_MONOFASICO),
        ("1201", "500", None, True, SegmentoDevolucao.PRODUCAO_ST_MONOFASICO),
        ("3202", "102", None, False, SegmentoDevolucao.REVENDA_EXPORTACAO),
        ("3201", "102", None, False, SegmentoDevolucao.PRODUCAO_EXPORTACAO),
        ("1660", "102", None, False, None),
        ("5102", "102", None, False, None),
    ],
)
def test_sugestao_do_segmento_da_devolucao_pelo_item(cfop, csosn, cst, monofasico, esperado):
    """Esperado escrito à mão, pela regra do plano (HI-129): x.201/x.410 produção, x.202/x.411
    revenda,
    ST por x.410/x.411 ou CSOSN/CST 500 (60), monofásico pela marca, exportação por CFOP 3.xxx."""
    item = SimpleNamespace(cfop=cfop, csosn=csosn, cst=cst)
    sugestao = servico_nfe.sugerir_segmento_devolucao(item, monofasico)
    assert sugestao.segmento == (esperado.value if esperado else None)


def test_mapa_de_segmento_da_devolucao_tem_os_dez_pares_do_plano():
    """Cada `SegmentoDevolucao` aponta para um (anexo, segmento) distinto: a devolução cai num lugar
    só."""
    assert len(ANEXO_E_SEGMENTO_DA_DEVOLUCAO) == 10
    assert len(set(ANEXO_E_SEGMENTO_DA_DEVOLUCAO.values())) == 10
    assert ANEXO_E_SEGMENTO_DA_DEVOLUCAO[SegmentoDevolucao.PRODUCAO] == (ANEXO_II, "normal")
    assert ANEXO_E_SEGMENTO_DA_DEVOLUCAO[SegmentoDevolucao.REVENDA] == (ANEXO_I, "normal")
