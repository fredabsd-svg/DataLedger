"""DL-083: ajustes de integração do arquiteto depois da reconferência (sem terceira rodada, §3.1).

- R1: o limite de tamanho da natureza na tela e na API vem do campo do modelo. Antes era 24, e a
  natureza `devolucao_combustivel_consumo` (29) era recusada com 400.
- R2: a nota efetivada antes da HI-138 que a atribuição nova recusaria é LIDA pelo critério
  anterior, sem derrubar a receita do mês nem a tela.
- R3: a nota de ajuste (finNFe 2) com frete efetiva com receita zero, como antes da DL-083.
- Lacunas de mutação da reconferência: A04 (arredondamento HALF_UP) e A18 (as linhas do período
  usam a atribuição).

Os valores esperados são escritos à mão.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import api_escrituracao_nfe, views_web
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.itens_nfe import AtribuicaoDaNota, atribuir_receita_da_nota
from apps.fiscal.models import EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

D = Decimal


# ---------------------------------------------------------------------------------------------
# R1: limite da natureza
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("natureza", list(N.values))
def test_toda_natureza_cabe_no_limite_da_tela_e_da_api(natureza):
    assert len(natureza) <= views_web._TAMANHO_NATUREZA_NFE
    assert len(natureza) <= api_escrituracao_nfe._TAMANHO_NATUREZA


def test_limites_vem_do_campo_do_modelo():
    tamanho = NaturezaItemNFe._meta.get_field("natureza").max_length
    assert views_web._TAMANHO_NATUREZA_NFE == tamanho
    assert api_escrituracao_nfe._TAMANHO_NATUREZA == tamanho


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-ajustes-dl083")


@pytest.fixture
def destinataria(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Destinataria Ajustes DL083",
        cnpj=xml.CNPJ_DESTINATARIO_A,
    )


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Ajustes DL083", cnpj=CNPJ_EMITENTE_A
    )


def _devolucao_de_gasolina_recebida(escritorio, gestor, empresa, numero):
    return receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[
                xml.det(
                    1, cfop="5662", vprod="1000.00", ncm="27101259", icms_xml=xml.icms(csosn="102")
                )
            ],
            vnf="1000.00",
            totais={"vProd": "1000.00"},
            numero=str(numero),
            emitente=("CNPJ", xml.CNPJ_EMITENTE_A),
            destinatario=("CNPJ", empresa.cnpj),
            tp_nf="1",
            fin_nfe="4",
        ),
    )


@pytest.mark.django_db
def test_natureza_de_29_caracteres_pela_tela(escritorio_a, gestor, destinataria, client):
    documento = _devolucao_de_gasolina_recebida(escritorio_a, gestor, destinataria, 8301)
    v = vinculo(documento, destinataria)
    client.force_login(gestor)
    url = reverse(
        "fiscal_web:nfe_escriturar", kwargs={"empresa_id": destinataria.pk, "vinculo_id": v.pk}
    )
    assert client.post(url, {"acao": "criar"}).status_code == 302
    registro = NaturezaItemNFe.objects.select_related("item").get(escrituracao__vinculo=v)
    resposta = client.post(
        url,
        {"acao": "item", "item_id": registro.item_id, "natureza": N.DEVOLUCAO_COMBUSTIVEL_CONSUMO},
    )
    assert resposta.status_code == 302
    registro.refresh_from_db()
    assert registro.natureza == N.DEVOLUCAO_COMBUSTIVEL_CONSUMO


@pytest.mark.django_db
def test_natureza_de_29_caracteres_pela_api(escritorio_a, gestor, destinataria, client):
    documento = _devolucao_de_gasolina_recebida(escritorio_a, gestor, destinataria, 8302)
    rascunho = servico.criar_rascunho(vinculo(documento, destinataria), usuario=gestor)
    registro = NaturezaItemNFe.objects.get(escrituracao=rascunho)
    client.force_login(gestor)
    resposta = client.post(
        reverse("fiscal_api:nfe_escrituracao_naturezas", args=[destinataria.pk, rascunho.pk]),
        data=json.dumps({"natureza": N.DEVOLUCAO_COMBUSTIVEL_CONSUMO, "itens": [registro.item_id]}),
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    registro.refresh_from_db()
    assert registro.natureza == N.DEVOLUCAO_COMBUSTIVEL_CONSUMO


# ---------------------------------------------------------------------------------------------
# R2: nota efetivada antes da HI-138
# ---------------------------------------------------------------------------------------------


def _efetivar(escritorio, gestor, empresa, xml_bytes, naturezas):
    documento = receber(escritorio, gestor, xml_bytes)
    rascunho = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    registros = list(NaturezaItemNFe.objects.filter(escrituracao=rascunho).order_by("item__n_item"))
    for registro, natureza in zip(registros, naturezas, strict=True):
        servico.definir_natureza(rascunho, natureza, [registro.item_id], gestor)
    return servico.efetivar(rascunho, usuario=gestor)


@pytest.mark.django_db
def test_remessa_com_frete_efetivada_antes_da_regra_nova_nao_derruba_a_leitura(
    escritorio_a, gestor, emitente, client, monkeypatch
):
    """Revenda de 1.000,00 efetivada pela regra nova. Remessa pura indTot 1 (vProd 300,00, frete
    50,00) efetivada como na DL-081, quando o frete do item que não é receita somava zero. A regra
    nova recusaria essa nota; a leitura usa o critério anterior: receita do mês 1.000,00."""
    _efetivar(
        escritorio_a,
        gestor,
        emitente,
        xml.nfe(dets=[xml.det(1, vprod="1000.00")], vnf="1000.00", numero="8311"),
        [N.REVENDA],
    )
    zeros = lambda pares: AtribuicaoDaNota(  # noqa: E731
        {item.pk: D("0.00") for item, _ in pares}, D("0.00"), ()
    )
    monkeypatch.setattr(servico, "atribuir_receita_da_nota", zeros)
    antiga = _efetivar(
        escritorio_a,
        gestor,
        emitente,
        xml.nfe(dets=[xml.det(1, vprod="300.00", vfrete="50.00")], vnf="350.00", numero="8312"),
        [N.REMESSA_RETORNO],
    )
    monkeypatch.undo()
    assert antiga.estado == EstadoEscrituracao.EFETIVADA

    conferencia = servico.conferencia_do_mes(emitente, 2026, 3)
    assert conferencia.receita_por_natureza[N.REVENDA]["soma_na_receita"] == D("1000.00")
    assert conferencia.receita_por_natureza[N.REMESSA_RETORNO]["soma_na_receita"] == D("0.00")
    assert servico.segregacao_da_escrituracao(antiga)["normal"] == D("0.00")
    linhas = receita_servico.linhas_nfe_do_periodo(emitente, (2026, 3), (2026, 3))
    assert sum((linha.valor for linha in linhas if linha.papel == "receita"), D("0")) == D(
        "1000.00"
    )

    client.force_login(gestor)
    url = reverse(
        "fiscal_web:nfe_escriturar",
        kwargs={"empresa_id": emitente.pk, "vinculo_id": antiga.vinculo_id},
    )
    assert client.get(url).status_code == 200


# ---------------------------------------------------------------------------------------------
# R3: nota de ajuste com frete
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("despesa", [{}, {"vfrete": "5.00"}, {"voutro": "5.00"}])
def test_nota_de_ajuste_com_despesa_efetiva_com_receita_zero(
    escritorio_a, gestor, emitente, despesa
):
    vnf = D("100.00") + D(next(iter(despesa.values()), "0"))
    esc = _efetivar(
        escritorio_a,
        gestor,
        emitente,
        xml.nfe(
            dets=[xml.det(1, cfop="5949", vprod="100.00", **despesa)],
            vnf=f"{vnf:.2f}",
            totais={"vProd": "100.00"},
            numero="8321",
            fin_nfe="2",
        ),
        [N.AJUSTE],
    )
    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert esc.receita_bruta == D("0.00")


# ---------------------------------------------------------------------------------------------
# Lacunas de mutação da reconferência
# ---------------------------------------------------------------------------------------------


def _item(n_item, vprod, *, ind_tot="1", vfrete=None):
    return SimpleNamespace(
        pk=n_item,
        n_item=n_item,
        v_prod=D(vprod),
        ind_tot=ind_tot,
        v_desc=None,
        v_frete=None if vfrete is None else D(vfrete),
        v_seg=None,
        v_outro=None,
        v_icms_deson=None,
        ind_deduz_deson=None,
    )


def test_arredondamento_half_up_com_diferenca_negativa_no_item_de_maior_valor():
    """A04: três revendas de 100,00 e frete de 0,02 numa bonificação indTot 0. Cada cota é
    0,02 × 100/300 = 0,00666… → 0,01 (HALF_UP). Soma 0,03, diferença −0,01 no item de maior valor
    (empate: menor nItem, o 1). Resultado: 100,00, 100,01 e 100,01."""
    pares = [
        (_item(1, "100.00"), N.REVENDA),
        (_item(2, "100.00"), N.REVENDA),
        (_item(3, "100.00"), N.REVENDA),
        (_item(4, "0.00", ind_tot="0", vfrete="0.02"), N.BONIFICACAO),
    ]
    valores = atribuir_receita_da_nota(pares).valores
    assert [valores[1], valores[2], valores[3], valores[4]] == [
        D("100.00"),
        D("100.01"),
        D("100.01"),
        D("0.00"),
    ]


@pytest.mark.django_db
def test_linhas_do_periodo_trazem_a_receita_atribuida(escritorio_a, gestor, emitente):
    """A18: revenda de 600,00 e de 400,00, bonificação indTot 0 com frete de 100,00 e desconto de
    10,00 (resíduo +90,00). Rateio: 54,00 e 36,00. Linhas: 654,00 e 436,00; soma 1.090,00."""
    dets = [
        xml.det(1, vprod="600.00"),
        xml.det(2, vprod="400.00"),
        xml.det(3, vprod="20.00", ind_tot="0", vfrete="100.00", vdesc="10.00"),
    ]
    _efetivar(
        escritorio_a,
        gestor,
        emitente,
        xml.nfe(dets=dets, vnf="1090.00", numero="8331"),
        [N.REVENDA, N.MONOFASICO, N.BONIFICACAO],
    )
    linhas = receita_servico.linhas_nfe_do_periodo(emitente, (2026, 3), (2026, 3))
    por_natureza = {linha.natureza: linha.valor for linha in linhas if linha.papel == "receita"}
    assert por_natureza == {N.REVENDA: D("654.00"), N.MONOFASICO: D("436.00")}
