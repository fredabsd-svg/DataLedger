"""DL-081, correção da rodada 1 (API): valor acima do campo, bloqueios de A4, A12 e permissões.

- A5: valor acima do numeric(15,2) vira nota ilegível com motivo. Nada de 500 na API.
- A4 na API: o bloqueio que nomeia a regra pendente (PE-85) sai com 409 e a mensagem.
- A12: o campo da conferência é `valor_bruto_por_cfop`, e o filtro de CFOP aceita "5.102".
- W6: estornar a escrituração de OUTRA empresa, pela URL de uma empresa, responde 404.
- W7: quem só consulta (PARALEGAL) não estorna: responde 403, e a escrituração segue efetivada.

Todo CNPJ é sintético. Os valores são escritos à mão.
"""

import json

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EstadoEscrituracao, LeituraItensNFe, NaturezaItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def paralegal_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-rodada1-api-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API Rodada 1 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API Rodada 1 Outra Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _json(resposta):
    return json.loads(resposta.content)


def _nota(escritorio, usuario, dets, *, vnf, numero, vprod_total=None):
    return receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=dets,
            vnf=vnf,
            totais={"vProd": vprod_total or vnf},
            numero=str(numero),
            dh_emi="2026-03-15T10:00:00-03:00",
        ),
    )


def _rascunho_com_natureza(usuario, empresa_da_nota, documento, natureza="revenda"):
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return esc


# --- A5: valor acima do campo, sem 500 ----------------------------------------------------------


def test_valor_acima_do_campo_vira_nota_ilegivel_sem_500_na_api(
    escritorio_a, usuario_gestor_a, empresa, client
):
    """vProd 9.999.999.999.999,99 mais vFrete 5,00: a receita passa de numeric(15,2). A rodada 1
    dava 500 na criação do rascunho. Agora a nota é bloqueada com o motivo, e nada é gravado."""
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        [xml.det(1, vprod="9999999999999.99", vfrete="5.00")],
        vnf="9999999999999.99",
        numero=31,
    )
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        _url("nfe_escrituracao_lista", empresa.pk),
        {"vinculo_id": vinculo(documento, empresa).pk},
    )
    assert resposta.status_code == 409
    assert "receita do item acima do limite" in _json(resposta)["detail"]
    leitura = LeituraItensNFe.objects.get(documento=documento)
    assert leitura.estado == LeituraItensNFe.ESTADO_ILEGIVEL
    assert "receita do item acima do limite" in leitura.motivo


# --- A4 na API: bloqueio nomeado, com 409 e a regra pendente -------------------------------------


def test_efetivar_com_item_fora_do_total_responde_409_com_a_mensagem_nomeada(
    escritorio_a, usuario_gestor_a, empresa, client
):
    """DL-083 (item 3): item indTot 0 com frete e natureza sem receita recusa com a mensagem
    nomeada. Antes da DL-083, o mesmo caso recusava com a regra pendente da PE-85."""
    from apps.fiscal.escrituracao_nfe import MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR

    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="50.00", ind_tot="0", vfrete="10.00"),
    ]
    documento = _nota(escritorio_a, usuario_gestor_a, dets, vnf="100.00", numero=32)
    esc = _rascunho_com_natureza(usuario_gestor_a, empresa, documento, natureza="bonificacao")
    client.force_login(usuario_gestor_a)
    resposta = _post(client, _url("nfe_escrituracao_efetivar", empresa.pk, esc.pk), {})
    assert resposta.status_code == 409
    assert _json(resposta)["detail"] == MENSAGEM_ITEM_FORA_DO_TOTAL_COM_VALOR
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.RASCUNHO


# --- A12: campo da conferência e filtro de CFOP com ponto ---------------------------------------


def test_conferencia_da_api_expoe_valor_bruto_por_cfop_e_nao_o_nome_antigo(
    escritorio_a, usuario_gestor_a, empresa, client
):
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        [xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        numero=33,
    )
    esc = _rascunho_com_natureza(usuario_gestor_a, empresa, documento)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    corpo = _json(client.get(_url("nfe_conferencia", empresa.pk) + "?ano=2026&mes=3"))
    assert corpo["valor_bruto_por_cfop"] == {"5102": "100.00"}
    assert "receita_por_cfop" not in corpo


def test_filtro_de_cfop_com_ponto_e_aceito_e_normalizado(
    escritorio_a, usuario_gestor_a, empresa, client
):
    """ "5.102" casava nada, em silêncio. Agora é "5102", e a reclassificação atinge o item."""
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        [xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        numero=34,
    )
    _rascunho_com_natureza(usuario_gestor_a, empresa, documento, natureza="producao_propria")
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        _url("nfe_escrituracao_reclassificar", empresa.pk),
        {"natureza": "revenda", "cfop": "5.102"},
    )
    assert resposta.status_code == 200
    assert _json(resposta)["itens_alterados"] == 1


@pytest.mark.parametrize("cfop", ["51", "51022", "5x02"])
def test_filtro_de_cfop_fora_do_formato_responde_400(
    escritorio_a, usuario_gestor_a, empresa, client, cfop
):
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        _url("nfe_escrituracao_reclassificar", empresa.pk),
        {"natureza": "revenda", "cfop": cfop},
    )
    assert resposta.status_code == 400


# --- W6 e W7: estorno pela API -----------------------------------------------------------------


def _efetivada(escritorio, usuario, empresa_da_nota, numero):
    documento = _nota(
        escritorio,
        usuario,
        [xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="100.00",
        numero=numero,
    )
    esc = _rascunho_com_natureza(usuario, empresa_da_nota, documento)
    return servico.efetivar(esc, usuario=usuario)


def test_estornar_escrituracao_de_outra_empresa_pela_url_de_outra_responde_404(
    escritorio_a, usuario_gestor_a, empresa, outra_empresa, client
):
    """W6: a escrituração é de `empresa`. Pela URL de `outra_empresa`, o estorno não a encontra."""
    esc = _efetivada(escritorio_a, usuario_gestor_a, empresa, numero=35)
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        _url("nfe_escrituracao_estornar", outra_empresa.pk, esc.pk),
        {"motivo": "tentativa de estorno cruzado"},
    )
    assert resposta.status_code == 404
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.EFETIVADA


def test_paralegal_que_so_consulta_nao_estorna_e_recebe_403(
    escritorio_a, usuario_gestor_a, paralegal_a, empresa, client
):
    """W7: PARALEGAL lê a escrituração, mas não estorna. A permissão é de escrita."""
    esc = _efetivada(escritorio_a, usuario_gestor_a, empresa, numero=36)
    client.force_login(paralegal_a)
    resposta = _post(
        client,
        _url("nfe_escrituracao_estornar", empresa.pk, esc.pk),
        {"motivo": "estorno sem poder"},
    )
    assert resposta.status_code == 403
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.EFETIVADA


def test_valor_acima_do_campo_na_tela_responde_409_com_o_motivo_sem_500(
    escritorio_a, usuario_gestor_a, empresa, client
):
    """A5 na tela: criar o rascunho de nota com valor acima do campo responde 409 com o motivo."""
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        [xml.det(1, vprod="9999999999999.99", vfrete="5.00")],
        vnf="9999999999999.99",
        numero=37,
    )
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk]),
        {"acao": "criar"},
    )
    assert resposta.status_code == 409
    assert "receita do item acima do limite" in resposta.content.decode()
