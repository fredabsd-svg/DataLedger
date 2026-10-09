"""DL-082, correção da rodada 1 (A1, A3, A9 e A12): devolução, segmento e reclassificação.

Dados sintéticos (`suporte_dl082`, `suporte_dl085`). Os números esperados são escritos à mão, com a
conta ao lado de cada teste.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal.models import (
    EscrituracaoNFe,
    ItemNFe,
    MercadoReceita,
    NaturezaItemNFe,
    segmentos_permitidos,
)
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import SegmentoDevolucao as SD
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, previa_lida
from apps.fiscal.tests.test_dl075_suporte import cenario_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa_a(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Correção DL082 Devolução Ltda",
        cnpj=CNPJ_EMITENTE_A,
    )


def _rascunho(empresa, usuario, documento, naturezas, marcas=(), segmentos=None):
    """Rascunho com naturezas, marcas e segmentos por número de item. NÃO efetiva."""
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = {i.n_item: i.pk for i in ItemNFe.objects.filter(documento=documento)}
    for n_item, natureza in naturezas.items():
        servico_nfe.definir_natureza(esc, natureza, [ids[n_item]], usuario=usuario)
    if marcas:
        servico_nfe.definir_marca_monofasico(esc, [ids[n] for n in marcas], True, usuario)
    for n_item, segmento in (segmentos or {}).items():
        servico_nfe.definir_segmento_devolucao(esc, [ids[n_item]], segmento, usuario)
    return esc


# ---------------------------------------------------------------------------
# A1: o lote não efetiva devolução; a recusa efetivada diz que é preciso estornar
# ---------------------------------------------------------------------------


def test_lote_nao_efetiva_devolucao_e_a_nota_sai_com_o_motivo(escritorio_a, usuario_gestor_a):
    """Caso 3 da auditoria. Esperado (à mão): venda 5102 de 20.000 e devolução 1202 de 5.000 no
    mesmo mês. O lote efetiva a venda e NÃO efetiva a devolução. A devolução sai do lote com o
    código `devolucao_segmento_a_confirmar`, e o motivo manda escriturar a nota individualmente.
    Antes: as duas eram efetivadas, e a devolução ficava sem segmento, com o mês travado."""
    empresa = cenario_simples(
        Empresa.objects.create(
            escritorio=escritorio_a,
            razao_social="Lote Devolução DL082",
            cnpj=CNPJ_EMITENTE_A,
        )
    )
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "20000.00"}],
    )
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=2,
        itens=[{"cfop": "1202", "vprod": "5000.00"}],
        devolucao=True,
    )

    previa = previa_lida(empresa, 2026, 6)
    fora = {f.codigo: f.motivo for f in previa.fora}
    assert fora["devolucao_segmento_a_confirmar"] == (
        "segmento da devolução a confirmar: escriture esta nota individualmente"
    )
    confirmar_tudo(empresa, usuario_gestor_a, 2026, 6, previa)

    estados = sorted(EscrituracaoNFe.objects.filter(empresa=empresa).values_list("tipo", "estado"))
    assert estados == [("saida_propria", "efetivada")]
    assert not EscrituracaoNFe.objects.filter(vinculo__documento=devolucao).exists()


def test_devolucao_escriturada_pelo_caminho_individual_entra_no_pre_das(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """O caminho que o motivo manda seguir funciona. Esperado (à mão): RBT12 600.000 (50.000 × 12);
    venda 5102 de 20.000 e devolução 1202 de 5.000 confirmada como revenda (Anexo I, normal).
    Líquido de revenda: 15.000. Alíquota efetiva do Anexo I, faixa 3 (RBT12 entre 360.000 e
    720.000): 9,5% − 13.860 / 600.000 = 9,5% − 2,31% = 7,19%. Cada tributo é arredondado a centavo
    (HI-71) e o total é a soma: IRPJ 5,5% → 59,32; CSLL 3,5% → 37,75; Cofins 12,74% → 137,40;
    PIS 2,76% → 29,77; CPP 42% → 452,97; ICMS 33,5% → 361,30. Soma: 1.078,51 (não 1.078,50, que
    seria o produto arredondado de uma vez)."""
    empresa = cenario_simples(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "20000.00"}],
    )
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=2,
        itens=[{"cfop": "1202", "vprod": "5000.00"}],
        devolucao=True,
    )
    previa = previa_lida(empresa, 2026, 6)
    confirmar_tudo(empresa, usuario_gestor_a, 2026, 6, previa)
    escriturar(
        empresa, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA}
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("1078.51")


def test_devolucao_efetivada_sem_segmento_recusa_dizendo_que_precisa_de_estorno(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """A1, a mensagem. Uma devolução já efetivada sem segmento recusa o mês, e a mensagem diz que a
    nota precisa de estorno para confirmar o segmento (a escrituração efetivada não muda)."""
    empresa = cenario_simples(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12)
    nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5102", "vprod": "20000.00"}],
    )
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=322,
        itens=[{"cfop": "1202", "vprod": "5000.00"}],
        devolucao=True,
    )
    escriturar(empresa, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)
    recusas = {b.codigo: b.mensagem for b in erro.value.bloqueios}
    mensagem = recusas["devolucao_sem_segmento_confirmado"]

    assert "sem segmento confirmado" in mensagem
    assert "nota(s) 322" in mensagem
    assert "precisa de estorno" in mensagem
    assert "O pré-DAS não rateia a devolução (HI-129)." in mensagem


# ---------------------------------------------------------------------------
# A3: devolução de exportação (1.503 a 1.506, 2.503 a 2.506) é do mercado externo
# ---------------------------------------------------------------------------


def test_devolucao_de_comercial_exportadora_deduz_do_externo_e_total_e_3494_50(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Caso 2 da auditoria. Esperado (à mão): janela interna 50.000 × 12 (RBT12 600.000) e externa
    10.000 × 12 (RBT12 120.000).
    - Interno, Anexo II (produção 5.101 de 40.000). Faixa 3: 10% − 13.860/600.000 = 7,69%.
      40.000 × 7,69% = 3.076,00.
    - Externo, Anexo II (5.501 de 30.000 à comercial exportadora, menos a devolução 1.503 de
      10.000 com segmento producao_exportacao = 20.000). Faixa 1: 4,5%. Exportação tira PIS,
      Cofins, IPI e ICMS: sobram IRPJ 5,5, CSLL 3,5 e CPP 37,5 = 46,5% de 4,5% = 2,0925%.
      20.000 × 2,0925% = 418,50.
    - Total: 3.076,00 + 418,50 = 3.494,50.
    Antes: a devolução caía no interno (só o CFOP `3.xxx` era de exportação), e o total saía
    2.934,77."""
    empresa = cenario_simples(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [50000] * 12, [10000] * 12)
    venda_externa = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=1,
        itens=[{"cfop": "5501", "vprod": "30000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda_externa, {1: N.COMERCIAL_EXPORTADORA})
    venda_interna = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=2,
        itens=[{"cfop": "5101", "vprod": "40000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda_interna, {1: N.PRODUCAO_PROPRIA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=3,
        itens=[{"cfop": "1503", "vprod": "10000.00"}],
        devolucao=True,
    )
    escriturar(
        empresa,
        usuario_gestor_a,
        devolucao,
        {1: N.DEVOLUCAO_VENDA},
        segmentos={1: SD.PRODUCAO_EXPORTACAO},
    )
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    por_anexo = {(a.mercado, a.anexo): a.total for a in resultado.anexos}
    assert por_anexo[(MercadoReceita.INTERNO, "II")] == Decimal("3076.00")
    assert por_anexo[(MercadoReceita.EXTERNO, "II")] == Decimal("418.50")
    assert resultado.total == Decimal("3494.50")


def test_sugestao_do_segmento_de_devolucao_de_exportacao(escritorio_a, usuario_gestor_a, empresa_a):
    """A3 e a sugestão. O anexo sai da descrição oficial: 1.503 e 1.505 são de produção (II); 1.504
    e 1.506 são de mercadoria de terceiros (I). Os 3.503 não dizem o anexo: sem sugestão."""
    empresa = cenario_simples(empresa_a)
    casos = {
        "1503": SD.PRODUCAO_EXPORTACAO,
        "1504": SD.REVENDA_EXPORTACAO,
        "1505": SD.PRODUCAO_EXPORTACAO,
        "1506": SD.REVENDA_EXPORTACAO,
        "2503": SD.PRODUCAO_EXPORTACAO,
        "2506": SD.REVENDA_EXPORTACAO,
    }
    for numero, (cfop, segmento) in enumerate(casos.items(), start=10):
        documento = nota(
            escritorio_a,
            usuario_gestor_a,
            empresa,
            numero=numero,
            itens=[{"cfop": cfop, "vprod": "1000.00"}],
            devolucao=True,
        )
        # Os itens só existem depois do rascunho (a leitura os grava): o rascunho vem antes.
        _rascunho(empresa, usuario_gestor_a, documento, {1: N.DEVOLUCAO_VENDA})
        item = ItemNFe.objects.get(documento=documento)
        assert servico_nfe.sugerir_segmento_devolucao(item, False).segmento == segmento, cfop

    sem_anexo = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=30,
        itens=[{"cfop": "3503", "vprod": "1000.00"}],
        devolucao=True,
    )
    _rascunho(empresa, usuario_gestor_a, sem_anexo, {1: N.DEVOLUCAO_VENDA})
    item_sem_anexo = ItemNFe.objects.get(documento=sem_anexo)
    assert servico_nfe.sugerir_segmento_devolucao(item_sem_anexo, False).segmento is None


def test_definir_segmento_recusa_exportacao_e_o_contrario(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """A3, a validação nos dois sentidos. Devolução 1.503 aceita o segmento de exportação e recusa o
    interno. Devolução 1.202 (interna) recusa o de exportação. A mensagem começa por "Devolução de
    exportação tem CFOP 3.xxx", como as telas e os testes antigos a citam."""
    empresa = cenario_simples(empresa_a)
    devolucao_503 = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=40,
        itens=[{"cfop": "1503", "vprod": "1000.00"}],
        devolucao=True,
    )
    esc_503 = _rascunho(empresa, usuario_gestor_a, devolucao_503, {1: N.DEVOLUCAO_VENDA})
    item_503 = ItemNFe.objects.get(documento=devolucao_503).pk
    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.definir_segmento_devolucao(esc_503, [item_503], SD.PRODUCAO, usuario_gestor_a)
    assert erro.value.mensagem.startswith("Devolução de exportação tem CFOP 3.xxx")

    devolucao_1202 = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=41,
        itens=[{"cfop": "1202", "vprod": "1000.00"}],
        devolucao=True,
    )
    esc_1202 = _rascunho(empresa, usuario_gestor_a, devolucao_1202, {1: N.DEVOLUCAO_VENDA})
    item_1202 = ItemNFe.objects.get(documento=devolucao_1202).pk
    with pytest.raises(servico_nfe.EntradaInvalidaNFe):
        servico_nfe.definir_segmento_devolucao(
            esc_1202, [item_1202], SD.REVENDA_EXPORTACAO, usuario_gestor_a
        )
    servico_nfe.definir_segmento_devolucao(
        esc_503, [item_503], SD.REVENDA_EXPORTACAO, usuario_gestor_a
    )


# ---------------------------------------------------------------------------
# A9: o domínio diz quais segmentos cabem no item (a tela usa só isto)
# ---------------------------------------------------------------------------


def test_segmentos_permitidos_separam_exportacao_do_mercado_interno():
    """Escrito à mão: os dois de exportação, e os demais, são os valores de `SegmentoDevolucao`."""
    exportacao = {"revenda_exportacao", "producao_exportacao"}
    interno = {
        "revenda",
        "producao",
        "revenda_st",
        "producao_st",
        "revenda_monofasico",
        "producao_monofasico",
        "revenda_st_monofasico",
        "producao_st_monofasico",
    }
    assert set(segmentos_permitidos("1503")) == exportacao
    assert set(segmentos_permitidos("2506")) == exportacao
    assert set(segmentos_permitidos("3202")) == exportacao
    assert set(segmentos_permitidos("1661")) == interno
    assert set(segmentos_permitidos("1202")) == interno


# ---------------------------------------------------------------------------
# A12: a reclassificação em massa recusa a operação inteira se um item não cabe na natureza nova
# ---------------------------------------------------------------------------


def test_reclassificacao_recusa_tudo_se_um_item_com_marca_nao_cabe_na_natureza_nova(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Uma venda de revenda em rascunho, com a marca de monofásico. Reclassificar para remessa
    (natureza que não é de mercadoria) recusa com a mensagem nomeada, e nada muda: a natureza
    continua revenda e a marca continua marcada."""
    empresa = cenario_simples(empresa_a)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=50,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(empresa, usuario_gestor_a, venda, {1: N.REVENDA}, marcas=(1,))

    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.reclassificar_em_massa(
            empresa,
            N.REMESSA_RETORNO,
            servico_nfe.FiltrosReclassificacao(cfop="5102"),
            usuario_gestor_a,
        )

    assert "não aceita a marca de monofásico" in erro.value.mensagem
    assert "Nada foi alterado" in erro.value.mensagem
    registro = NaturezaItemNFe.objects.get(escrituracao=esc)
    assert registro.natureza == N.REVENDA
    assert registro.monofasico is True


def test_reclassificacao_recusa_tudo_se_devolucao_com_segmento_vai_a_natureza_sem_segmento(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Devolução com segmento confirmado (revenda) não cabe na natureza de devolução de combustível
    para consumo, que não aceita o segmento. Recusa, e nada muda."""
    empresa = cenario_simples(empresa_a)
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=51,
        itens=[{"cfop": "1202", "vprod": "1000.00"}],
        devolucao=True,
    )
    esc = _rascunho(
        empresa,
        usuario_gestor_a,
        devolucao,
        {1: N.DEVOLUCAO_VENDA},
        segmentos={1: SD.REVENDA},
    )

    with pytest.raises(servico_nfe.EntradaInvalidaNFe) as erro:
        servico_nfe.reclassificar_em_massa(
            empresa,
            N.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
            servico_nfe.FiltrosReclassificacao(cfop="1202"),
            usuario_gestor_a,
        )

    assert "segmento de devolução" in erro.value.mensagem
    registro = NaturezaItemNFe.objects.get(escrituracao=esc)
    assert registro.natureza == N.DEVOLUCAO_VENDA
    assert registro.segmento_devolucao == SD.REVENDA


def test_reclassificacao_compativel_continua_permitida(escritorio_a, usuario_gestor_a, empresa_a):
    """O lado sem recusa: revenda com marca vai para produção própria (mercadoria), e a marca
    fica."""
    empresa = cenario_simples(empresa_a)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=52,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    esc = _rascunho(empresa, usuario_gestor_a, venda, {1: N.REVENDA}, marcas=(1,))

    resultado = servico_nfe.reclassificar_em_massa(
        empresa,
        N.PRODUCAO_PROPRIA,
        servico_nfe.FiltrosReclassificacao(cfop="5102"),
        usuario_gestor_a,
    )

    assert resultado.itens_alterados == 1
    registro = NaturezaItemNFe.objects.get(escrituracao=esc)
    assert registro.natureza == N.PRODUCAO_PROPRIA
    assert registro.monofasico is True
