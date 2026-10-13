"""DL-091 (frente A1), API da escrituração de ENTRADA: criação com data de entrada, natureza com
CFOP de entrada, data de entrada em rascunho, efetivação, memória e avisos no detalhe, permissões no
servidor, isolamento (404) e entrada estranha (400, nunca 500).

Permissões seguem o mesmo mapa da DL-081: leitura para quem consulta; escrita para quem escritura.
Os dados são sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, critérios 4, 6 e 9.
"""

import json
from datetime import date

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import EscrituracaoNFe, NaturezaItemNFe, TipoEscrituracaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def paralegal_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-api-dl091")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-api-b-dl091")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Compradora API DL091 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra API DL091 Ltda", cnpj="12345678000195"
    )


@pytest.fixture
def compra(escritorio_a, usuario_gestor_a, empresa):
    """Compra de 100,00 de SP para a empresa, CFOP 6.102 (interestadual), CST 00, CRT 3.

    A empresa é do Presumido na data (DL-091, rodada 1, A1): a marca de crédito depende do regime
    do comprador, e sem regime cadastrado ela seria "a conferir".
    """
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    icms = xml.icms(
        cst="00",
        filhos="<modBC>3</modBC><vBC>100.00</vBC><pICMS>12.00</pICMS><vICMS>12.00</vICMS>",
    )
    documento = receber(
        escritorio_a,
        usuario_gestor_a,
        xml.nfe(
            dets=[xml.det(1, cfop="6102", vprod="100.00", icms_xml=icms)],
            vnf="100.00",
            totais={"vProd": "100.00"},
            chave=chave_nfe(cuf="35", emitente=CNPJ_EMITENTE_A, modelo="55", numero="801"),
            numero="801",
            dh_emi="2026-03-15T10:00:00-03:00",
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
            crt="3",
        ),
    )
    ler_itens(documento)
    return documento


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _json(resposta):
    return json.loads(resposta.content)


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _criar(client, empresa, documento, **extra):
    corpo = {"vinculo_id": vinculo(documento, empresa).pk, **extra}
    return _post(client, _url("nfe_escrituracao_lista", empresa.pk), corpo)


def test_criar_rascunho_de_compra_com_data_de_entrada(client, usuario_gestor_a, empresa, compra):
    client.force_login(usuario_gestor_a)
    resposta = _criar(client, empresa, compra, data_entrada="2026-04-02")
    assert resposta.status_code == 201
    corpo = _json(resposta)
    assert corpo["tipo"] == TipoEscrituracaoNFe.ENTRADA
    assert corpo["data_entrada"] == "2026-04-02"


def test_natureza_com_cfop_de_entrada_e_detalhe_com_sugestao_e_previa(
    client, usuario_gestor_a, empresa, compra
):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra))
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao_id=esc["id"]).values_list("item_id", flat=True)
    )

    url = _url("nfe_escrituracao_naturezas", empresa.pk, esc["id"])
    resposta = _post(
        client, url, {"natureza": "entrada_comercializacao", "itens": ids, "cfop_entrada": "2102"}
    )
    assert resposta.status_code == 200

    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc["id"])))
    item = detalhe["itens"][0]
    assert item["cfop_entrada"] == "2102"
    assert item["cfop"] == "6102"  # o do emitente não muda
    assert item["cfop_entrada_sugerido"]["cfop"] == "2102"
    assert item["memoria"]["fonte"] == "previa"
    assert item["memoria"]["marca_credito"] == "credito_destacado"


def test_natureza_de_entrada_sem_cfop_e_recusada_com_400(client, usuario_gestor_a, empresa, compra):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra))
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao_id=esc["id"]).values_list("item_id", flat=True)
    )
    resposta = _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc["id"]),
        {"natureza": "entrada_comercializacao", "itens": ids},
    )
    assert resposta.status_code == 400


def test_cfop_de_entrada_com_primeiro_digito_errado_e_400(
    client, usuario_gestor_a, empresa, compra
):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra))
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao_id=esc["id"]).values_list("item_id", flat=True)
    )
    resposta = _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc["id"]),
        {"natureza": "entrada_comercializacao", "itens": ids, "cfop_entrada": "1102"},
    )
    assert resposta.status_code == 400


def test_data_de_entrada_anterior_a_emissao_e_400_e_depois_troca_em_rascunho(
    client, usuario_gestor_a, empresa, compra
):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra))
    url = _url("nfe_escrituracao_data_entrada", empresa.pk, esc["id"])
    assert _post(client, url, {"data_entrada": "2026-03-01"}).status_code == 400
    resposta = _post(client, url, {"data_entrada": "2026-04-10"})
    assert resposta.status_code == 200
    assert _json(resposta)["data_entrada"] == "2026-04-10"


def test_fluxo_completo_de_entrada_pela_api_efetiva_e_mostra_a_memoria_gravada(
    client, usuario_gestor_a, empresa, compra
):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra, data_entrada="2026-04-02"))
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao_id=esc["id"]).values_list("item_id", flat=True)
    )
    _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc["id"]),
        {"natureza": "entrada_comercializacao", "itens": ids, "cfop_entrada": "2102"},
    )
    efetivada = _post(client, _url("nfe_escrituracao_efetivar", empresa.pk, esc["id"]), {})
    assert efetivada.status_code == 201, efetivada.content  # ato criado (convenção da DL-081)
    corpo = _json(efetivada)
    assert corpo["estado"] == "efetivada"
    assert corpo["competencia"] == "2026-04-01"  # a competência é a da data de entrada

    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc["id"])))
    item = detalhe["itens"][0]
    assert item["memoria"]["fonte"] == "efetivada"
    assert item["memoria"]["marca_credito"] == "credito_destacado"
    assert detalhe["motivo_bloqueio_efetivacao"] is None  # a regra de receita de 2027 não se aplica


def test_paralegal_le_mas_nao_cria_compra(client, paralegal_a, empresa, compra):
    client.force_login(paralegal_a)
    assert _criar(client, empresa, compra).status_code == 403


def test_nota_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, usuario_gestor_a, empresa, outra_empresa, compra
):
    """O vínculo é o da compra da primeira empresa; o endereço é o da outra. Tem de dar 404."""
    client.force_login(usuario_gestor_a)
    vinculo_da_empresa = vinculo(compra, empresa).pk
    resposta = _post(
        client,
        _url("nfe_escrituracao_lista", outra_empresa.pk),
        {"vinculo_id": vinculo_da_empresa},
    )
    assert resposta.status_code == 404


def test_outro_escritorio_nao_enxerga_a_empresa_de_entrada(client, gestor_b, empresa, compra):
    client.force_login(gestor_b)
    assert _criar(client, empresa, compra, data_entrada="2026-04-02").status_code == 404


def test_campo_fora_do_contrato_e_recusado_antes_do_banco(
    client, usuario_gestor_a, empresa, compra
):
    client.force_login(usuario_gestor_a)
    esc = _json(_criar(client, empresa, compra))
    ids = list(
        NaturezaItemNFe.objects.filter(escrituracao_id=esc["id"]).values_list("item_id", flat=True)
    )
    resposta = _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc["id"]),
        {"natureza": "entrada_comercializacao", "itens": ids, "cfop_entrada": "2102", "extra": 1},
    )
    assert resposta.status_code == 400
    assert not EscrituracaoNFe.objects.filter(pk=esc["id"], estado="efetivada").exists()
