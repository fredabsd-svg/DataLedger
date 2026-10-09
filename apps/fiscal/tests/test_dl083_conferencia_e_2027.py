"""DL-083 (frente A), critérios 2 e 4.

Critério 2: a conferência W16 (tolerância zero) fecha ao centavo nas notas que antes bloqueavam
(item indTot 0 com despesa, ICMS desonerado deduzido). A nota que não fecha continua bloqueada.

Critério 4: nota com dhEmi em 2027 ou depois não é efetivada, com a mensagem nomeada. O ano é o de
São Paulo: 31/12/2026 23:59 efetiva, e 01/01/2027 00:00 em São Paulo (03:00 UTC) recusa.

O gerador de notas é o da DL-081 (`xml_nfe_dl081`). Cada vNF é calculado AQUI, em centavos inteiros,
pela identidade W16 escrita à mão: não pela função de produção.
"""

import random
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EstadoEscrituracao, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-w16-2027-dl083")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _centavos(c: int) -> str:
    """Centavos inteiros -> texto decimal, sem passar por float."""
    sinal = "-" if c < 0 else ""
    return f"{sinal}{abs(c) // 100}.{abs(c) % 100:02d}"


def _efetivar(escritorio, gestor, emitente, xml_bytes, natureza=NaturezaOperacaoNFe.REVENDA):
    documento = receber(escritorio, gestor, xml_bytes)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, natureza, ids, gestor)
    return servico.efetivar(esc, usuario=gestor)


# --- critério 2: W16 com indTot 0, frete, desconto e deson -----------------------------------


def _nota_w16(rng: random.Random, numero: int, delta_centavos: int = 0) -> bytes:
    """Nota com itens indTot 1 e 0, desconto, frete, seguro, outras despesas e ICMS desonerado
    deduzido (indDeduzDeson 1). Tudo em centavos. O vNF é a identidade W16 escrita à mão:

        vNF = Σ receita dos itens + vST + vFCPST + vIPI
        receita do item = (vProd se indTot 1, senão 0)
                          − vDesc − vICMSDeson (se deduz) + frete + seg + outro

    A receita de cada item fica não negativa (o vNF do XSD não aceita sinal): desconto e deson são
    limitados ao vProd, e no item indTot 0 o frete cobre o que sai dele. `delta_centavos` soma ao
    vNF: 0 é a nota que fecha; 1 é a que não fecha.
    """
    dets = []
    soma_receita_c = 0
    soma_vprod_indtot1_c = 0
    for n in range(1, rng.randint(1, 4) + 1):
        ind_tot = "1" if rng.random() < 0.5 else "0"
        vprod_c = rng.randint(10_000, 900_000)
        if ind_tot == "1":
            soma_vprod_indtot1_c += vprod_c
        kwargs = {}
        desc_c = rng.randint(1, vprod_c // 4) if rng.random() < 0.4 else 0
        deson_c = rng.randint(1, vprod_c // 5) if rng.random() < 0.4 else 0
        frete_c = rng.randint(1, 5_000) if rng.random() < 0.5 else 0
        seg_c = rng.randint(1, 500) if rng.random() < 0.3 else 0
        outro_c = rng.randint(1, 500) if rng.random() < 0.3 else 0
        if ind_tot == "0":
            # Sem o vProd, o que sai do item (desconto e deson) é coberto pelo frete do item.
            frete_c = max(frete_c, desc_c + deson_c)
        if desc_c:
            kwargs["vdesc"] = _centavos(desc_c)
        if frete_c:
            kwargs["vfrete"] = _centavos(frete_c)
        if seg_c:
            kwargs["vseg"] = _centavos(seg_c)
        if outro_c:
            kwargs["voutro"] = _centavos(outro_c)
        icms = xml.icms(csosn="102")
        if deson_c:
            icms = xml.icms(
                cst="40",
                filhos=(
                    f"<vICMSDeson>{_centavos(deson_c)}</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
                ),
            )
        receita_c = (
            (vprod_c if ind_tot == "1" else 0) - desc_c - deson_c + frete_c + seg_c + outro_c
        )
        soma_receita_c += receita_c
        dets.append(xml.det(n, vprod=_centavos(vprod_c), ind_tot=ind_tot, icms_xml=icms, **kwargs))
    vst_c = rng.randint(1, 20_000) if rng.random() < 0.4 else 0
    fcp_st_c = rng.randint(1, 5_000) if rng.random() < 0.3 else 0
    vipi_c = rng.randint(1, 8_000) if rng.random() < 0.3 else 0
    totais = {"vProd": _centavos(soma_vprod_indtot1_c), "vST": _centavos(vst_c)}
    if fcp_st_c:
        totais["vFCPST"] = _centavos(fcp_st_c)
    if vipi_c:
        totais["vIPI"] = _centavos(vipi_c)
    vnf_c = soma_receita_c + vst_c + fcp_st_c + vipi_c + delta_centavos
    return xml.nfe(dets=dets, vnf=_centavos(vnf_c), totais=totais, numero=str(numero))


def test_nota_com_indtot_0_frete_desconto_e_deson_fecha_ao_centavo(escritorio_a, gestor, emitente):
    """Nota de três itens, escrita à mão:
      item 1: indTot 1, vProd 100,00, frete 10,00                  → receita 110,00
      item 2: indTot 0, vProd 50,00 (não cobrado), vSeg 2,00       → receita   2,00
      item 3: indTot 1, vProd 200,00, vICMSDeson 20,00 (deduz 1)   → receita 180,00
    Soma = 292,00. vNF = 292,00. Antes da DL-083, o item 2 bloqueava a nota."""
    icms_deson = xml.icms(
        cst="40", filhos="<vICMSDeson>20.00</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
    )
    dets = [
        xml.det(1, vprod="100.00", vfrete="10.00"),
        xml.det(2, vprod="50.00", ind_tot="0", vseg="2.00"),
        xml.det(3, vprod="200.00", icms_xml=icms_deson),
    ]
    esc = _efetivar(escritorio_a, gestor, emitente, xml.nfe(dets=dets, vnf="292.00", numero="801"))
    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert esc.soma_itens == Decimal("292.00")
    assert esc.receita_bruta == Decimal("292.00")


@pytest.mark.parametrize("delta", [1, -1])
def test_nota_com_indtot_0_e_deson_que_nao_fecha_continua_bloqueada(
    escritorio_a, gestor, emitente, delta
):
    """Mesma nota, com vNF 0,01 a mais ou a menos: a tolerância é zero, e a divergência bloqueia."""
    icms_deson = xml.icms(
        cst="40", filhos="<vICMSDeson>20.00</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
    )
    dets = [
        xml.det(1, vprod="100.00", vfrete="10.00"),
        xml.det(2, vprod="50.00", ind_tot="0", vseg="2.00"),
        xml.det(3, vprod="200.00", icms_xml=icms_deson),
    ]
    vnf_c = 29200 + delta
    xml_bytes = xml.nfe(dets=dets, vnf=_centavos(vnf_c), numero=str(802 + (delta > 0)))
    with pytest.raises(servico.DivergenciaComVnf) as erro:
        _efetivar(escritorio_a, gestor, emitente, xml_bytes)
    assert "diverge" in erro.value.mensagem
    assert "292,00" in erro.value.mensagem


def test_notas_geradas_que_seguem_a_w16_com_as_parcelas_novas_efetivam(
    escritorio_a, gestor, emitente
):
    """Propriedade com semente fixa: 14 notas com indTot 0, desconto, frete, seguro, outras despesas
    e ICMS desonerado deduzido. A que segue a identidade W16 efetiva. A mesma nota com 0,01 a mais
    no vNF é recusada. Todo valor sai do gerador em centavos inteiros."""
    rng = random.Random(20261009)
    for numero in range(900, 914):
        estado = rng.getstate()
        boa = _nota_w16(rng, numero)
        fim = rng.getstate()
        rng.setstate(estado)
        ruim = _nota_w16(rng, numero + 1000, delta_centavos=1)
        rng.setstate(fim)

        assert _efetivar(escritorio_a, gestor, emitente, boa).estado == "efetivada", numero
        with pytest.raises(servico.DivergenciaComVnf):
            _efetivar(escritorio_a, gestor, emitente, ruim)


# --- critério 4: receita de 2027 não se efetiva; o ano é o de São Paulo ----------------------


def _nota_em(dh_emi: str, numero: int) -> bytes:
    return xml.nfe(
        dets=[xml.det(1, vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        totais={"vProd": "100.00"},
        numero=str(numero),
        dh_emi=dh_emi,
    )


def test_nota_de_2027_recusa_a_efetivacao_com_a_mensagem_nomeada(escritorio_a, gestor, emitente):
    """01/01/2027 00:00 em São Paulo (03:00 UTC): já é 2027, e a receita não se efetiva."""
    documento = receber(escritorio_a, gestor, _nota_em("2027-01-01T00:00:00-03:00", 811))
    assert documento.dh_emissao == datetime(2027, 1, 1, 3, 0, tzinfo=UTC)
    esc = servico.criar_rascunho(vinculo(documento, emitente), usuario=gestor)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, ids, gestor)
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=gestor)
    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_PENDENTE
    assert erro.value.mensagem == "regra de receita de 2027 pendente: NT 2026.008 e vNF"
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


def test_nota_de_31_12_2026_23h59_em_sao_paulo_efetiva(escritorio_a, gestor, emitente):
    """31/12/2026 23:59 em São Paulo ainda é 2026 (em UTC já é 01/01/2027 02:59). Efetiva, com a
    competência de dezembro de 2026."""
    from datetime import date

    esc = _efetivar(
        escritorio_a,
        gestor,
        emitente,
        _nota_em("2026-12-31T23:59:00-03:00", 812),
    )
    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert esc.competencia == date(2026, 12, 1)
    assert esc.data_emissao == date(2026, 12, 31)


def test_nota_de_2027_em_junho_tambem_recusa(escritorio_a, gestor, emitente):
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar(
            escritorio_a,
            gestor,
            emitente,
            _nota_em("2027-06-15T10:00:00-03:00", 813),
        )
    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_PENDENTE
