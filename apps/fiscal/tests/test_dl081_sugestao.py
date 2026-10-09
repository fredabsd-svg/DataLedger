"""DL-081 (frente A), sugestão de natureza por sinais e elegibilidade (consulta, item 2; HI-118).

Funções puras: a nota e o item são objetos simples, sem banco. Os valores esperados são os da
consulta de 09/10/2026. Conflito de sinais deixa a sugestão em branco; comercial exportadora,
bonificação e monofásico nunca têm sugestão.
"""

from types import SimpleNamespace

import pytest

from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import PapelNFe, TipoEscrituracaoNFe


def nota(**campos):
    base = {
        "modelo": "55",
        "tp_nf": "1",
        "fin_nfe": "1",
        "id_dest": "1",
        "transferencia_entre_estabelecimentos": False,
    }
    base.update(campos)
    return SimpleNamespace(**base)


def item(cfop, csosn=None, cst=None, ncm="22030000"):
    # NCM padrão de cerveja (fora de combustível e lubrificante): a sugestão de combustível (HI-139)
    # lê o NCM de todo item de devolução e de venda com CFOP de combustível.
    return SimpleNamespace(cfop=cfop, csosn=csosn, cst=cst, ncm=ncm)


# --- sinais de CFOP ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cfop", "esperado"),
    [
        ("5102", N.REVENDA),
        ("5104", N.REVENDA),
        ("6102", N.REVENDA),
        ("5101", N.PRODUCAO_PROPRIA),
        ("5103", N.PRODUCAO_PROPRIA),
    ],
)
def test_cfop_de_revenda_e_de_producao(cfop, esperado):
    sugestao = servico.sugerir_natureza_item(nota(), item(cfop, csosn="102"))
    assert sugestao.natureza == esperado


def test_cupom_5929_leva_a_natureza_13():
    sugestao = servico.sugerir_natureza_item(nota(), item("5929", csosn="102"))
    assert sugestao.natureza == N.CUPOM_NFCE


def test_transferencia_so_com_emitente_igual_ao_destinatario():
    com = nota(transferencia_entre_estabelecimentos=True)
    assert servico.sugerir_natureza_item(com, item("5151", csosn="102")).natureza == N.TRANSFERENCIA
    sem = nota(transferencia_entre_estabelecimentos=False)
    assert servico.sugerir_natureza_item(sem, item("5151", csosn="102")).natureza is None


def test_cfop_fora_da_tabela_e_a_classificar_nunca_suposicao():
    sugestao = servico.sugerir_natureza_item(nota(), item("5000", csosn="102"))
    assert sugestao.natureza is None
    assert "a classificar" in sugestao.motivo


@pytest.mark.parametrize("cfop", ["5501", "5502", "5910", "5911"])
def test_comercial_exportadora_e_bonificacao_nunca_tem_sugestao(cfop):
    sugestao = servico.sugerir_natureza_item(nota(), item(cfop, csosn="102"))
    assert sugestao.natureza is None
    assert "sem sugestão" in sugestao.motivo


def test_devolucao_de_compra_em_saida_nao_vira_devolucao_de_venda():
    """5.202 tem indDevol 1 na tabela, mas em saída é devolução de compra: fora do catálogo."""
    sugestao = servico.sugerir_natureza_item(nota(), item("5202", csosn="102"))
    assert sugestao.natureza is None
    assert "devolução de compra" in sugestao.motivo


# --- sinais de CST/CSOSN ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("csosn", "cst", "esperado"),
    [
        ("500", None, N.REVENDA_ST_SUBSTITUIDO),  # CSOSN 500 (consulta, item 2)
        (None, "60", N.REVENDA_ST_SUBSTITUIDO),  # CST 60
        ("201", None, N.SUBSTITUTO_ST),  # CSOSN 201
        ("202", None, N.SUBSTITUTO_ST),
        ("203", None, N.SUBSTITUTO_ST),
        (None, "10", N.SUBSTITUTO_ST),  # CST 10
        (None, "30", N.SUBSTITUTO_ST),
        (None, "70", N.SUBSTITUTO_ST),
    ],
)
def test_csosn_e_cst_de_st(csosn, cst, esperado):
    """Sem CFOP de revenda, o sinal de ST decide sozinho (5405 e 5401 não têm sinal no catálogo)."""
    sugestao = servico.sugerir_natureza_item(
        nota(), item("5405" if cst == "60" or csosn == "500" else "5401", csosn=csosn, cst=cst)
    )
    assert sugestao.natureza == esperado


def test_csosn_102_sozinho_nao_sugere_nada():
    sugestao = servico.sugerir_natureza_item(nota(), item("5405", csosn="102"))
    assert sugestao.natureza is None


def test_pis_monofasico_nao_sugere_monofasico():
    """PIS CST 04 não decide monofásico (consulta, item 3): o NCM é que decide, e não há tabela."""
    sugestao = servico.sugerir_natureza_item(nota(), item("5102", csosn="102"))
    assert sugestao.natureza == N.REVENDA
    assert sugestao.natureza != N.MONOFASICO


# --- conflito e exportação --------------------------------------------------------------------


def test_cfop_de_revenda_com_csosn_500_e_conflito_e_fica_em_branco():
    """Consulta, item 2 e Hipótese 2: CFOP 5.102 com CSOSN 500 rebaixa a sugestão para branco."""
    sugestao = servico.sugerir_natureza_item(nota(), item("5102", csosn="500"))
    assert sugestao.natureza is None
    assert "conflito" in sugestao.motivo


def test_exportacao_direta_com_idDest_3_e_cfop_7():
    sugestao = servico.sugerir_natureza_item(nota(id_dest="3"), item("7102", csosn="102"))
    assert sugestao.natureza == N.EXPORTACAO_DIRETA


def test_cfop_7_sem_idDest_3_nao_e_exportacao():
    sugestao = servico.sugerir_natureza_item(nota(id_dest="1"), item("7102", csosn="102"))
    assert sugestao.natureza is None


def test_exportacao_com_st_e_conflito_e_fica_em_branco():
    sugestao = servico.sugerir_natureza_item(nota(id_dest="3"), item("7102", csosn="500"))
    assert sugestao.natureza is None


# --- finalidade (finNFe) ----------------------------------------------------------------------


@pytest.mark.parametrize("fin", ["2", "3", "5", "6"])
def test_finalidades_de_ajuste_sao_ajuste(fin):
    sugestao = servico.sugerir_natureza_item(nota(fin_nfe=fin), item("5102", csosn="102"))
    assert sugestao.natureza == N.AJUSTE


def test_finNFe_4_com_indDevol_1_e_devolucao_de_venda():
    sugestao = servico.sugerir_natureza_item(
        nota(tp_nf="0", fin_nfe="4"), item("1202", csosn="102")
    )
    assert sugestao.natureza == N.DEVOLUCAO_VENDA


def test_finNFe_4_com_cfop_sem_indDevol_e_conflito():
    """Devolução declarada (finNFe 4) com CFOP de venda: sinais contrários, sem sugestão."""
    sugestao = servico.sugerir_natureza_item(nota(fin_nfe="4"), item("5102", csosn="102"))
    assert sugestao.natureza is None
    assert "conflito" in sugestao.motivo


def test_devolucao_nao_depende_da_faixa_mas_da_coluna():
    """5.410 tem indDevol 1 e entra como devolução com finNFe 4, mesmo fora da faixa de 1.2xx."""
    sugestao = servico.sugerir_natureza_item(
        nota(tp_nf="0", fin_nfe="4"), item("5410", csosn="102")
    )
    assert sugestao.natureza == N.DEVOLUCAO_VENDA


# --- elegibilidade ----------------------------------------------------------------------------


@pytest.mark.parametrize("modelo", ["55", "65"])
def test_saida_propria_e_elegivel_em_nfe_e_nfce(modelo):
    tipo = servico.tipo_da_nota(nota(modelo=modelo), PapelNFe.EMITENTE)
    assert tipo == TipoEscrituracaoNFe.SAIDA_PROPRIA


@pytest.mark.parametrize("fin", ["2", "3", "5", "6"])
def test_ajustes_so_na_saida_propria(fin):
    assert servico.tipo_da_nota(nota(fin_nfe=fin), PapelNFe.EMITENTE) == TipoEscrituracaoNFe.AJUSTE
    assert servico.tipo_da_nota(nota(fin_nfe=fin, tp_nf="0"), PapelNFe.EMITENTE) is None


def test_devolucao_recebida_de_terceiro_e_destinatario_com_finNFe_4():
    tipo = servico.tipo_da_nota(nota(tp_nf="1", fin_nfe="4"), PapelNFe.DESTINATARIO)
    assert tipo == TipoEscrituracaoNFe.DEVOLUCAO


def test_devolucao_propria_de_entrada_e_emitente_com_tpNF_0_e_finNFe_4():
    assert servico.tipo_da_nota(nota(tp_nf="0", fin_nfe="4"), PapelNFe.EMITENTE) == (
        TipoEscrituracaoNFe.DEVOLUCAO
    )


def test_compra_e_entrada_de_terceiro_ficam_fora():
    assert servico.tipo_da_nota(nota(tp_nf="1", fin_nfe="1"), PapelNFe.DESTINATARIO) is None
    assert servico.tipo_da_nota(nota(tp_nf="0", fin_nfe="1"), PapelNFe.DESTINATARIO) is None


def test_saida_que_nao_e_venda_nem_ajuste_fica_fora_com_motivo():
    assert servico.tipo_da_nota(nota(tp_nf="1", fin_nfe="4"), PapelNFe.EMITENTE) is None
    motivo = servico.motivo_fora_da_escrituracao(nota(tp_nf="1", fin_nfe="4"), PapelNFe.EMITENTE)
    assert "finNFe 4" in motivo


def test_modelo_fora_de_55_e_65_fica_fora():
    assert servico.tipo_da_nota(nota(modelo="57"), PapelNFe.EMITENTE) is None


def test_naturezas_permitidas_por_tipo():
    assert servico.naturezas_permitidas(TipoEscrituracaoNFe.AJUSTE) == {N.AJUSTE}
    # HI-140: a devolução aceita as duas naturezas de devolução (a do 8% e a do 1,6%).
    assert servico.naturezas_permitidas(TipoEscrituracaoNFe.DEVOLUCAO) == {
        N.DEVOLUCAO_VENDA,
        N.DEVOLUCAO_COMBUSTIVEL_CONSUMO,
    }
    saida = servico.naturezas_permitidas(TipoEscrituracaoNFe.SAIDA_PROPRIA)
    assert N.DEVOLUCAO_VENDA not in saida and N.DEVOLUCAO_COMBUSTIVEL_CONSUMO not in saida
    assert N.AJUSTE not in saida
    assert N.REVENDA in saida and N.CUPOM_NFCE in saida
