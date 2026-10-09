"""DL-083 (HI-138, A3): atribuição do valor de item que não é receita à receita da venda da nota.

Os valores esperados são escritos à mão, em centavos, com a conta em comentário. Nenhum teste
calcula
o esperado chamando a função de produção. Os testes de unidade usam itens sintéticos (sem banco). Os
de integração efetivam notas pelo serviço real, com XML sintético de `xml_nfe_dl081`.

Regras (HI-138, consulta de 09/10/2026, item 1):
- resíduo = Σ do valor cobrado dos itens que não são receita: frete, seguro, outras despesas e, no
  item indTot 0, o desconto e o ICMS desonerado. A mercadoria de item indTot 1 fica fora;
- rateio proporcional à receita de cada item de receita, a centavo (ROUND_HALF_UP); a diferença de
  arredondamento vai para o item de maior valor (empate: menor nItem);
- bloqueios, com mensagem fixa: nota sem item de receita com resíduo; resíduo negativo maior que a
  receita; resíduo sem base para ratear.
"""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.escrituracao_nfe import conferencia_do_mes
from apps.fiscal.itens_nfe import (
    MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR,
    MENSAGEM_RESIDUO_MAIOR_QUE_A_RECEITA,
    MENSAGEM_RESIDUO_SEM_BASE_DE_RATEIO,
    ResiduoNaoAtribuivel,
    atribuir_receita_da_nota,
    avisos_da_atribuicao,
    receita_do_item,
    valor_cobrado_do_item,
)
from apps.fiscal.models import NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

D = Decimal


def _item(
    n_item,
    *,
    vprod="0.00",
    ind_tot="1",
    vdesc=None,
    vfrete=None,
    vseg=None,
    voutro=None,
    vicms_deson=None,
    ind_deduz_deson=None,
):
    """Item sintético com os campos que a receita lê. `pk` = nItem, para as chaves de `valores`."""
    return SimpleNamespace(
        pk=n_item,
        n_item=n_item,
        v_prod=D(vprod),
        ind_tot=ind_tot,
        v_desc=None if vdesc is None else D(vdesc),
        v_frete=None if vfrete is None else D(vfrete),
        v_seg=None if vseg is None else D(vseg),
        v_outro=None if voutro is None else D(voutro),
        v_icms_deson=None if vicms_deson is None else D(vicms_deson),
        ind_deduz_deson=ind_deduz_deson,
    )


# ---------------------------------------------------------------------------------------------
# Unidade: casos de referência, à mão
# ---------------------------------------------------------------------------------------------


def test_e1_bonificacao_indtot_0_com_desconto_reduz_a_venda_para_90():
    """E1 (A3): venda 100,00 e bonificação indTot 0, vProd 10,00, vDesc 10,00. O vNF é 90,00.
    Resíduo: −10,00 (o desconto do item não-receita). A venda fica com 100,00 − 10,00 = 90,00."""
    venda = _item(1, vprod="100.00")
    bonificacao = _item(2, vprod="10.00", ind_tot="0", vdesc="10.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (bonificacao, N.BONIFICACAO)])
    assert atribuicao.residuo_total == D("-10.00")
    assert atribuicao.valores[venda.pk] == D("90.00")
    assert atribuicao.valores[bonificacao.pk] == D("0.00")


def test_e2_bonificacao_indtot_1_com_frete_soma_50_na_venda_150():
    """E2 (A3): venda 100,00 e bonificação indTot 1, vProd 10,00, vDesc 10,00, vFrete 50,00.
    A mercadoria da bonificação é 10,00 − 10,00 = 0,00, e o frete de 50,00 vai para a venda:
    150,00."""
    venda = _item(1, vprod="100.00")
    bonificacao = _item(2, vprod="10.00", vdesc="10.00", vfrete="50.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (bonificacao, N.BONIFICACAO)])
    assert atribuicao.residuo_total == D("50.00")
    assert atribuicao.valores[venda.pk] == D("150.00")


def test_remessa_indtot_1_de_mercadoria_nao_vira_receita_da_venda():
    """A mercadoria de remessa indTot 1 (vProd 300,00, sem despesa) não é receita e não entra no
    resíduo. É a regra que mantém a DL-081 (HI-124): natureza que não é receita soma zero."""
    venda = _item(1, vprod="100.00")
    remessa = _item(2, vprod="300.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (remessa, N.REMESSA_RETORNO)])
    assert atribuicao.residuo_total == D("0.00")
    assert atribuicao.valores[venda.pk] == D("100.00")
    assert atribuicao.valores[remessa.pk] == D("0.00")


def test_valor_cobrado_indtot_1_leva_so_despesa_e_indtot_0_leva_a_receita_do_item():
    """Definição do valor cobrado: indTot 1 leva só as despesas (vFrete, vSeg, vOutro); indTot 0
    leva
    `receita_do_item` inteiro (desconto e ICMS desonerado com indDeduzDeson 1, mais as despesas)."""
    indtot_1 = _item(1, vprod="10.00", vdesc="10.00", vfrete="50.00", vseg="1.00", vicms_deson="4")
    assert valor_cobrado_do_item(indtot_1) == D("51.00")
    indtot_0 = _item(
        2,
        vprod="50.00",
        ind_tot="0",
        vdesc="5.00",
        vfrete="2.00",
        ind_deduz_deson="1",
        vicms_deson="1",
    )
    assert valor_cobrado_do_item(indtot_0) == receita_do_item(indtot_0) == D("-4.00")


def test_rateio_a_centavo_com_diferenca_no_item_de_maior_valor_e_empate_no_menor_nitem():
    """Rateio à mão. Três itens de receita de 100,00 (1 revenda, 2 produção própria, 3 revenda) e um
    frete de 10,00 numa bonificação indTot 0.
    Cota de cada um: 10,00 × 100,00 / 300,00 = 3,3333… → ROUND_HALF_UP → 3,33.
    Soma das cotas: 9,99. Diferença: 0,01. Os três têm o mesmo valor, então vai ao de menor nItem.
    Resultado: 1 = 103,34; 2 = 103,33; 3 = 103,33. Soma: 310,00."""
    v1 = _item(1, vprod="100.00")
    v2 = _item(2, vprod="100.00")
    v3 = _item(3, vprod="100.00")
    bonificacao = _item(4, ind_tot="0", vfrete="10.00")
    atribuicao = atribuir_receita_da_nota(
        [(v1, N.REVENDA), (v2, N.PRODUCAO_PROPRIA), (v3, N.REVENDA), (bonificacao, N.BONIFICACAO)]
    )
    assert atribuicao.valores[v1.pk] == D("103.34")
    assert atribuicao.valores[v2.pk] == D("103.33")
    assert atribuicao.valores[v3.pk] == D("103.33")
    assert sum(atribuicao.valores.values(), D("0.00")) == D("310.00")


def test_diferenca_de_arredondamento_vai_para_o_item_de_maior_valor_e_nao_para_o_primeiro():
    """Venda 1 = 100,00, venda 2 = 100,00, venda 3 = 150,00, frete de 0,05.
    Cotas: 0,05 × 100 / 350 = 0,01428… → 0,01; a mesma para a 2; 0,05 × 150 / 350 = 0,02142… → 0,02.
    Soma das cotas: 0,04. Diferença: 0,01. O maior é a venda 3 (150,00), e ela recebe a diferença:
    a 3 fica com 150,00 + 0,02 + 0,01 = 150,03. A 1 e a 2 ficam com 100,01 cada. Soma: 350,05."""
    v1 = _item(1, vprod="100.00")
    v2 = _item(2, vprod="100.00")
    v3 = _item(3, vprod="150.00")
    frete = _item(4, ind_tot="0", vfrete="0.05")
    atribuicao = atribuir_receita_da_nota(
        [(v1, N.REVENDA), (v2, N.REVENDA), (v3, N.REVENDA), (frete, N.BONIFICACAO)]
    )
    assert atribuicao.valores[v1.pk] == D("100.01")
    assert atribuicao.valores[v2.pk] == D("100.01")
    assert atribuicao.valores[v3.pk] == D("150.03")
    assert sum(atribuicao.valores.values(), D("0.00")) == D("350.05")


def test_rateio_com_tres_itens_sem_diferenca_de_arredondamento():
    """Dois itens de 100,00 e um de 300,00, frete de 0,10. Cotas: 0,10 × 100 / 500 = 0,02 cada;
    0,10 ×
    300 / 500 = 0,06. Soma 0,10, sem diferença: 100,02; 100,02; 300,06."""
    v1 = _item(1, vprod="100.00")
    v2 = _item(2, vprod="100.00")
    v3 = _item(3, vprod="300.00")
    frete = _item(4, ind_tot="0", vfrete="0.10")
    atribuicao = atribuir_receita_da_nota(
        [(v1, N.REVENDA), (v2, N.REVENDA), (v3, N.REVENDA), (frete, N.BONIFICACAO)]
    )
    assert [atribuicao.valores[k] for k in (1, 2, 3)] == [D("100.02"), D("100.02"), D("300.06")]


def test_residuo_negativo_maior_que_a_receita_bloqueia_com_a_mensagem():
    """Desconto de 500,00 num item indTot 0 de bonificação, com venda de 100,00: a receita ficaria
    em −400,00. Bloqueio com a mensagem fixa (b)."""
    venda = _item(1, vprod="100.00")
    bonificacao = _item(2, vprod="500.00", ind_tot="0", vdesc="500.00")
    with pytest.raises(ResiduoNaoAtribuivel) as erro:
        atribuir_receita_da_nota([(venda, N.REVENDA), (bonificacao, N.BONIFICACAO)])
    assert erro.value.motivo == MENSAGEM_RESIDUO_MAIOR_QUE_A_RECEITA


def test_residuo_negativo_igual_a_receita_nao_bloqueia_e_zera_a_venda():
    """O limite exato é permitido: desconto de 100,00 com venda de 100,00 zera a receita, sem
    bloqueio."""
    venda = _item(1, vprod="100.00")
    bonificacao = _item(2, vprod="100.00", ind_tot="0", vdesc="100.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (bonificacao, N.BONIFICACAO)])
    assert atribuicao.valores[venda.pk] == D("0.00")


def test_nota_so_de_remessa_com_frete_bloqueia_com_a_mensagem_de_escolha_de_natureza():
    """Nota sem item de receita e com frete cobrado: não há onde compor a receita (a)."""
    remessa = _item(1, vprod="300.00", vfrete="10.00")
    with pytest.raises(ResiduoNaoAtribuivel) as erro:
        atribuir_receita_da_nota([(remessa, N.REMESSA_RETORNO)])
    assert erro.value.motivo == MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR


def test_residuo_sem_base_de_rateio_bloqueia():
    """Venda com desconto total (receita zero) e bonificação com frete: o frete não tem base."""
    venda = _item(1, vprod="100.00", vdesc="100.00")
    bonificacao = _item(2, ind_tot="0", vfrete="10.00")
    with pytest.raises(ResiduoNaoAtribuivel) as erro:
        atribuir_receita_da_nota([(venda, N.REVENDA), (bonificacao, N.BONIFICACAO)])
    assert erro.value.motivo == MENSAGEM_RESIDUO_SEM_BASE_DE_RATEIO


def test_devolucao_com_frete_nao_bloqueia_e_fica_com_o_valor_cru():
    """Devolução de 100,00 com frete de 5,00 (papel dedução) e sem venda: não entra no resíduo, não
    bloqueia, e fica com o seu `receita_do_item` cru: 105,00."""
    devolucao = _item(1, vprod="100.00", vfrete="5.00")
    atribuicao = atribuir_receita_da_nota([(devolucao, N.DEVOLUCAO_VENDA)])
    assert atribuicao.residuo_total == D("0.00")
    assert atribuicao.valores[devolucao.pk] == D("105.00")


def test_devolucao_com_frete_em_nota_com_venda_nao_entra_no_residuo():
    """Venda de 100,00 e devolução de 30,00 com frete de 5,00 na devolução. O frete da devolução não
    vai para a venda: a venda fica com 100,00 e a devolução deduz 35,00."""
    venda = _item(1, vprod="100.00")
    devolucao = _item(2, vprod="30.00", vfrete="5.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (devolucao, N.DEVOLUCAO_VENDA)])
    assert atribuicao.residuo_total == D("0.00")
    assert atribuicao.valores[venda.pk] == D("100.00")
    assert atribuicao.valores[devolucao.pk] == D("35.00")


def test_item_sem_natureza_fica_fora_da_atribuicao():
    """Na tela, um item sem natureza ainda não tem papel: não entra no resíduo nem na receita."""
    venda = _item(1, vprod="100.00")
    sem_natureza = _item(2, ind_tot="0", vfrete="10.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (sem_natureza, "")])
    assert atribuicao.residuo_total == D("0.00")
    assert sem_natureza.pk not in atribuicao.valores


def test_avisos_da_atribuicao_dizem_o_que_foi_para_a_venda_e_o_rateio_por_natureza():
    """O aviso por item sai quando o resíduo é diferente de zero. Com mais de uma natureza de
    receita,
    traz o rateio por natureza: revenda 6,67 (3,34 + 3,33) e produção própria 3,33."""
    v1 = _item(1, vprod="100.00")
    v2 = _item(2, vprod="100.00")
    v3 = _item(3, vprod="100.00")
    bonificacao = _item(4, ind_tot="0", vfrete="10.00")
    atribuicao = atribuir_receita_da_nota(
        [(v1, N.REVENDA), (v2, N.PRODUCAO_PROPRIA), (v3, N.REVENDA), (bonificacao, N.BONIFICACAO)]
    )
    avisos = avisos_da_atribuicao(atribuicao)
    assert set(avisos) == {4}
    (texto,) = avisos[4]
    assert texto == (
        "item 4 (Bonificação, doação, brinde ou amostra (incondicional)): R$ 10,00 de "
        "frete/seguro/outros/desconto atribuído à receita da venda desta nota "
        "(rateio: Venda de mercadoria adquirida de terceiros (revenda) R$ 6,67; "
        "Venda de produção própria R$ 3,33)"
    )


def test_sem_residuo_nao_ha_aviso_de_atribuicao():
    venda = _item(1, vprod="100.00")
    remessa = _item(2, vprod="300.00")
    atribuicao = atribuir_receita_da_nota([(venda, N.REVENDA), (remessa, N.REMESSA_RETORNO)])
    assert avisos_da_atribuicao(atribuicao) == {}


def test_conservacao_do_valor_a_receita_mais_a_mercadoria_nao_receita_e_a_soma_crua():
    """A atribuição move o resíduo, não cria nem perde valor. Com a soma crua de `receita_do_item`
    (o que o W16 confere), a diferença é exatamente a mercadoria dos itens não-receita.

    Venda 100,00; bonificação indTot 1 (vProd 10,00, vDesc 10,00, frete 50,00) = 50,00 cobrado;
    remessa indTot 1 (vProd 300,00, frete 7,00) = 307,00 crua, 7,00 cobrado; devolução (vProd 30,00,
    frete 5,00) = 35,00.
    Soma crua: 100 + 50 + 307 + 35 = 492,00. Mercadoria da remessa: 300,00 (não é receita).
    Receita atribuída à venda: 100 + 50 + 7 = 157,00. Devolução: 35,00. Soma atribuída: 192,00.
    492,00 − 192,00 = 300,00, a mercadoria da remessa."""
    venda = _item(1, vprod="100.00")
    bonificacao = _item(2, vprod="10.00", vdesc="10.00", vfrete="50.00")
    remessa = _item(3, vprod="300.00", vfrete="7.00")
    devolucao = _item(4, vprod="30.00", vfrete="5.00")
    pares = [
        (venda, N.REVENDA),
        (bonificacao, N.BONIFICACAO),
        (remessa, N.REMESSA_RETORNO),
        (devolucao, N.DEVOLUCAO_VENDA),
    ]
    atribuicao = atribuir_receita_da_nota(pares)
    assert atribuicao.valores[venda.pk] == D("157.00")
    assert atribuicao.valores[devolucao.pk] == D("35.00")
    assert atribuicao.residuo_total == D("57.00")
    soma_crua = sum((receita_do_item(item) for item, _ in pares), D("0.00"))
    soma_atribuida = sum(atribuicao.valores.values(), D("0.00"))
    assert soma_crua == D("492.00")
    assert soma_atribuida == D("192.00")
    assert soma_crua - soma_atribuida == D("300.00")


# ---------------------------------------------------------------------------------------------
# Integração: efetivação real pelo serviço, com W16 ao centavo
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-atribuicao-dl083")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Atribuicao DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _efetivar_com_naturezas(escritorio, gestor, emitente, xml_bytes, naturezas):
    """Recebe a NF-e, cria o rascunho, confirma a natureza de cada item (na ordem de nItem) e
    efetiva pelo serviço real."""
    documento = receber(escritorio, gestor, xml_bytes)
    rascunho = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    registros = list(
        NaturezaItemNFe.objects.filter(escrituracao=rascunho)
        .select_related("item")
        .order_by("item__n_item")
    )
    assert len(registros) == len(naturezas)
    for registro, natureza in zip(registros, naturezas, strict=True):
        servico.definir_natureza(rascunho, natureza, [registro.item_id], gestor)
    return servico.efetivar(rascunho, usuario=gestor)


@pytest.mark.django_db
def test_e1_efetiva_com_receita_90_e_w16_ao_centavo(escritorio_a, gestor, emitente):
    """E1 pela efetivação: venda 100,00 (nItem 1) + bonificação indTot 0, vProd 10,00, vDesc 10,00
    (nItem 2). vNF = 90,00. Receita gravada: 90,00. Soma da nota: 90,00 (W16)."""
    dets = [xml.det(1, vprod="100.00"), xml.det(2, vprod="10.00", ind_tot="0", vdesc="10.00")]
    xml_bytes = xml.nfe(dets=dets, vnf="90.00", numero="9101")
    esc = _efetivar_com_naturezas(
        escritorio_a, gestor, emitente, xml_bytes, [N.REVENDA, N.BONIFICACAO]
    )
    assert esc.estado == "efetivada"
    assert esc.receita_bruta == D("90.00")
    assert esc.soma_itens == D("90.00")


@pytest.mark.django_db
def test_e2_efetiva_com_receita_150_e_w16_ao_centavo(escritorio_a, gestor, emitente):
    """E2 pela efetivação: venda 100,00 + bonificação indTot 1, vProd 10,00, vDesc 10,00, vFrete
    50,00. vNF = 150,00. Receita gravada: 150,00."""
    dets = [xml.det(1, vprod="100.00"), xml.det(2, vprod="10.00", vdesc="10.00", vfrete="50.00")]
    xml_bytes = xml.nfe(dets=dets, vnf="150.00", numero="9102")
    esc = _efetivar_com_naturezas(
        escritorio_a, gestor, emitente, xml_bytes, [N.REVENDA, N.BONIFICACAO]
    )
    assert esc.receita_bruta == D("150.00")
    assert esc.soma_itens == D("150.00")


@pytest.mark.django_db
def test_nota_so_de_remessa_com_frete_bloqueia_a_efetivacao(escritorio_a, gestor, emitente):
    dets = [xml.det(1, vprod="300.00", ind_tot="0", vfrete="10.00")]
    xml_bytes = xml.nfe(dets=dets, vnf="10.00", numero="9103")
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar_com_naturezas(escritorio_a, gestor, emitente, xml_bytes, [N.REMESSA_RETORNO])
    assert erro.value.mensagem == MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR


@pytest.mark.django_db
def test_devolucao_com_frete_nao_bloqueia_a_efetivacao(escritorio_a, gestor, emitente):
    """Devolução (CFOP 1202, nota própria de entrada, finNFe 4) com frete de 5,00: a natureza de
    dedução fica fora da atribuição. Efetiva, com devolução de 105,00 (vProd 100,00 + frete
    5,00)."""
    dets = [xml.det(1, cfop="1202", vprod="100.00", vfrete="5.00")]
    xml_bytes = xml.nfe(dets=dets, vnf="105.00", numero="9104", tp_nf="0", fin_nfe="4")
    esc = _efetivar_com_naturezas(escritorio_a, gestor, emitente, xml_bytes, [N.DEVOLUCAO_VENDA])
    assert esc.estado == "efetivada"
    assert esc.devolucao == D("105.00")


@pytest.mark.django_db
def test_residuo_negativo_maior_que_a_receita_bloqueia_a_efetivacao(escritorio_a, gestor, emitente):
    """Venda de 100,00, remessa de mercadoria indTot 1 de 300,00 (não é receita) e bonificação
    indTot 0
    com desconto de 150,00. O vNF é 100 + 300 − 150 = 250,00 (válido). O resíduo é −150,00, maior
    que a receita da venda (100,00): bloqueio (b), e nada é gravado."""
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="300.00"),
        xml.det(3, vprod="150.00", ind_tot="0", vdesc="150.00"),
    ]
    xml_bytes = xml.nfe(dets=dets, vnf="250.00", numero="9105")
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar_com_naturezas(
            escritorio_a,
            gestor,
            emitente,
            xml_bytes,
            [N.REVENDA, N.REMESSA_RETORNO, N.BONIFICACAO],
        )
    assert erro.value.mensagem == MENSAGEM_RESIDUO_MAIOR_QUE_A_RECEITA


@pytest.mark.django_db
def test_rateio_pela_efetivacao_e_pela_conferencia_do_mes_com_centavo_de_diferenca(
    escritorio_a, gestor, emitente
):
    """Revenda 100,00 (nItem 1), produção própria 100,00 (nItem 2), revenda 100,00 (nItem 3) e
    bonificação indTot 0 com frete de 10,00 (nItem 4). vNF = 310,00. Pela conta à mão (ver o teste
    unitário): revenda 103,34 + 103,33 = 206,67; produção própria 103,33; bonificação 0,00.
    A conferência do mês, que lê a mesma atribuição, tem de mostrar esses três números."""
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="100.00"),
        xml.det(3, vprod="100.00"),
        xml.det(4, vprod="0.00", ind_tot="0", vfrete="10.00"),
    ]
    xml_bytes = xml.nfe(dets=dets, vnf="310.00", numero="9106")
    esc = _efetivar_com_naturezas(
        escritorio_a,
        gestor,
        emitente,
        xml_bytes,
        [N.REVENDA, N.PRODUCAO_PROPRIA, N.REVENDA, N.BONIFICACAO],
    )
    assert esc.receita_bruta == D("310.00")
    conferencia = conferencia_do_mes(emitente, 2026, 3)
    por_natureza = {
        n: linha["soma_na_receita"] for n, linha in conferencia.receita_por_natureza.items()
    }
    assert por_natureza[N.REVENDA] == D("206.67")
    assert por_natureza[N.PRODUCAO_PROPRIA] == D("103.33")
    assert por_natureza[N.BONIFICACAO] == D("0.00")
