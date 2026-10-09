"""DL-081, correção da rodada 1 (A4): conferência da receita com o vNF pela regra W16 do MOC 7.0.

Fórmula conferida aqui (a do `escrituracao_nfe.conferir_valores`):

    Σ vProd (indTot 1) − Σ vDesc (todos) + Σ (vFrete + vSeg + vOutro) (todos)
        = vNF − vST − vFCPST − vIPI − vII − vIPIDevol

Com os dois bloqueios (item indTot 0 com desconto ou despesa; ICMS desonerado deduzido), o lado
esquerdo é a soma da receita dos itens indTot 1. Os valores são escritos à mão, ou em centavos
inteiros (nunca em ponto flutuante). Os XML são sintéticos.
"""

import random
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import itens_nfe
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-w16-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente W16 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _centavos(c: int) -> str:
    """Centavos inteiros -> texto decimal, sem passar por float."""
    sinal = "-" if c < 0 else ""
    return f"{sinal}{abs(c) // 100}.{abs(c) % 100:02d}"


def _tentar_efetivar(escritorio, gestor, emitente, xml_bytes):
    documento = receber(escritorio, gestor, xml_bytes)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, ids, gestor)
    return servico.efetivar(esc, usuario=gestor)


# --- nota com vFCPST: a regra subtrai o FCP-ST declarado --------------------------------------


def test_nota_com_vfcpst_2_60_e_efetivada_quando_vnf_inclui_o_fcp_st(
    escritorio_a, gestor, emitente
):
    """Substituto tributário com FCP-ST: vNF = vProd + vST + vFCPST = 100,00 + 5,00 + 2,60 = 107,60.
    Antes da correção, o vFCPST não era subtraído, e a nota era bloqueada sem motivo válido."""
    xml_bytes = xml.nfe(
        dets=[xml.det(1, vprod="100.00")],
        vnf="107.60",
        totais={"vProd": "100.00", "vST": "5.00", "vFCPST": "2.60"},
        numero="201",
    )
    esc = _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes)
    assert esc.estado == "efetivada"
    assert esc.soma_itens == Decimal("100.00")
    assert esc.valor_nf == Decimal("107.60")


def test_leitura_guarda_o_vfcpst_declarado_no_total(escritorio_a, gestor, emitente):
    """O total vem de ICMSTot/vFCPST, o declarado na nota (a escolha está no docstring de
    `conferir_valores`)."""
    xml_bytes = xml.nfe(
        dets=[xml.det(1, vprod="100.00")],
        vnf="107.60",
        totais={"vProd": "100.00", "vST": "5.00", "vFCPST": "2.60"},
        numero="202",
    )
    documento = receber(escritorio_a, gestor, xml_bytes)
    assert itens_nfe.ler_itens(documento).v_fcp_st_total == Decimal("2.60")


@pytest.mark.parametrize("diferenca_centavos", [1, -1])
def test_diferenca_de_um_centavo_no_vnf_e_recusada(
    escritorio_a, gestor, emitente, diferenca_centavos
):
    """A tolerância é zero: 0,01 para mais ou para menos bloqueia, com os valores escritos."""
    vnf_c = 10760 + diferenca_centavos
    xml_bytes = xml.nfe(
        dets=[xml.det(1, vprod="100.00")],
        vnf=_centavos(vnf_c),
        totais={"vProd": "100.00", "vST": "5.00", "vFCPST": "2.60"},
        numero="203",
    )
    with pytest.raises(servico.DivergenciaComVnf) as erro:
        _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes)
    assert "diverge" in erro.value.mensagem
    assert "100,00" in erro.value.mensagem


# --- os dois bloqueios nomeados (PE-85) ---------------------------------------------------------


@pytest.mark.parametrize(
    "despesa",
    [{"vdesc": "5.00"}, {"vfrete": "10.00"}, {"vseg": "1.00"}, {"voutro": "2.00"}],
)
def test_item_fora_do_total_com_desconto_ou_despesa_bloqueia_com_a_mensagem(
    escritorio_a, gestor, emitente, despesa
):
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="50.00", ind_tot="0", **despesa),
    ]
    xml_bytes = xml.nfe(dets=dets, vnf="100.00", numero="204")
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes)
    assert erro.value.mensagem == servico.MENSAGEM_ITEM_FORA_DO_TOTAL
    assert "regra a decidir (PE-85)" in erro.value.mensagem
    assert not isinstance(erro.value, servico.DivergenciaComVnf)


def test_icms_desonerado_deduzido_do_total_bloqueia_com_a_mensagem(escritorio_a, gestor, emitente):
    """indDeduzDeson 1 (leiauteNFe_v4.00.xsd:2586): o vICMSDeson deduz do total da nota."""
    icms = xml.icms(
        cst="40", filhos="<vICMSDeson>10.00</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
    )
    xml_bytes = xml.nfe(dets=[xml.det(1, vprod="100.00", icms_xml=icms)], vnf="90.00", numero="205")
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes)
    assert erro.value.mensagem == servico.MENSAGEM_ICMS_DESONERADO_DEDUZIDO
    assert "ICMS desonerado deduzido do total da nota" in erro.value.mensagem


def test_icms_desonerado_sem_deducao_nao_bloqueia(escritorio_a, gestor, emitente):
    """indDeduzDeson 0: o vICMSDeson NÃO deduz; a nota segue a fórmula e efetiva com o vNF cheio."""
    icms = xml.icms(
        cst="40", filhos="<vICMSDeson>10.00</vICMSDeson><indDeduzDeson>0</indDeduzDeson>"
    )
    xml_bytes = xml.nfe(
        dets=[xml.det(1, vprod="100.00", icms_xml=icms)], vnf="100.00", numero="206"
    )
    assert _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes).estado == "efetivada"


def test_item_indtot_zero_sem_desconto_nem_despesa_nao_bloqueia(escritorio_a, gestor, emitente):
    """Item que não compõe o total e não tem desconto nem despesa: fica fora da conta, sem
    bloqueio."""
    dets = [xml.det(1, vprod="100.00"), xml.det(2, vprod="50.00", ind_tot="0")]
    xml_bytes = xml.nfe(dets=dets, vnf="100.00", numero="207")
    assert _tentar_efetivar(escritorio_a, gestor, emitente, xml_bytes).estado == "efetivada"


# --- propriedade: notas geradas em centavos, todas dentro da regra --------------------------


def _nota_aleatoria(rng: random.Random, numero: int, delta_centavos: int = 0) -> bytes:
    """Uma nota que segue a W16 sem os dois bloqueios. `delta_centavos` soma ao vNF (0 ou 1).

    Todo valor sai de `rng` em centavos inteiros. Com o mesmo estado de `rng`, a nota "ruim" é a
    mesma nota com 0,01 a mais no vNF.
    """
    dets = []
    soma_receita_c = 0
    soma_vprod_c = 0
    for n in range(1, rng.randint(1, 4) + 1):
        ind_tot = "1" if rng.random() < 0.8 else "0"
        vprod_c = rng.randint(1000, 900000)
        soma_vprod_c += vprod_c
        kwargs = {}
        if ind_tot == "1":
            # Desconto e despesas só em item indTot 1: é o caso que a fórmula cobre sem bloqueio.
            desc_c = rng.randint(1, vprod_c // 2) if rng.random() < 0.3 else 0
            frete_c = rng.randint(1, 5000) if rng.random() < 0.4 else 0
            seg_c = rng.randint(1, 500) if rng.random() < 0.2 else 0
            outro_c = rng.randint(1, 500) if rng.random() < 0.2 else 0
            if desc_c:
                kwargs["vdesc"] = _centavos(desc_c)
            if frete_c:
                kwargs["vfrete"] = _centavos(frete_c)
            if seg_c:
                kwargs["vseg"] = _centavos(seg_c)
            if outro_c:
                kwargs["voutro"] = _centavos(outro_c)
            soma_receita_c += vprod_c - desc_c + frete_c + seg_c + outro_c
        dets.append(xml.det(n, vprod=_centavos(vprod_c), ind_tot=ind_tot, **kwargs))
    vst_c = rng.randint(1, 20000) if rng.random() < 0.4 else 0
    fcp_st_c = rng.randint(1, 5000) if rng.random() < 0.4 else 0
    vipi_c = rng.randint(1, 8000) if rng.random() < 0.3 else 0
    vii_c = rng.randint(1, 2000) if rng.random() < 0.2 else 0
    totais = {"vProd": _centavos(soma_vprod_c), "vST": _centavos(vst_c)}
    if fcp_st_c:
        totais["vFCPST"] = _centavos(fcp_st_c)
    if vipi_c:
        totais["vIPI"] = _centavos(vipi_c)
    if vii_c:
        totais["vII"] = _centavos(vii_c)
    vnf_c = soma_receita_c + vst_c + fcp_st_c + vipi_c + vii_c + delta_centavos
    return xml.nfe(dets=dets, vnf=_centavos(vnf_c), totais=totais, numero=str(numero))


def test_notas_geradas_que_seguem_a_w16_efetivam_e_um_centavo_a_mais_bloqueia(
    escritorio_a, gestor, emitente
):
    """Propriedade com semente fixa: 16 notas que seguem a W16 efetivam; com 0,01 a mais no vNF
    (mesma nota, mesma semente), a efetivação é recusada. Gerador próprio, em centavos."""
    rng = random.Random(20261009)
    for numero in range(300, 316):
        estado = rng.getstate()
        boa = _nota_aleatoria(rng, numero)
        fim = rng.getstate()
        rng.setstate(estado)
        ruim = _nota_aleatoria(rng, numero + 1000, delta_centavos=1)
        rng.setstate(fim)

        esc = _tentar_efetivar(escritorio_a, gestor, emitente, boa)
        assert esc.estado == "efetivada", numero
        with pytest.raises(servico.DivergenciaComVnf):
            _tentar_efetivar(escritorio_a, gestor, emitente, ruim)
