"""DL-081 (frente A), API da escrituração das NF-e (item 8; critério 9 e entradas do plano).

Permissões: leitura para quem consulta (PARALEGAL lê; CLIENTE recebe 403); escrita para quem
escritura (ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO; PARALEGAL recebe 403). IDOR: outra empresa
ou outro escritório recebe 404. Entrada estranha: 400, nunca 500 (byte nulo, substituto, número
gigante, data fora de faixa, campo fora do contrato).
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe, NaturezaItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def paralegal_a(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-api-dl081")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-api-b-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API Emitente Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API Outra Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


@pytest.fixture
def nota(escritorio_a, usuario_gestor_a, empresa):
    """Saída própria de 2.880,00 (dois itens: 1.880 de revenda e 1.000 de produção)."""
    dets = [
        xml.det(1, cfop="5102", vprod="1880.00", icms_xml=xml.icms(csosn="102")),
        xml.det(2, cfop="5101", vprod="1000.00", icms_xml=xml.icms(csosn="102")),
    ]
    documento = receber(
        escritorio_a,
        usuario_gestor_a,
        xml.nfe(
            dets=dets,
            vnf="2880.00",
            totais={"vProd": "2880.00"},
            numero="7",
            dh_emi="2026-03-15T10:00:00-03:00",
        ),
    )
    return documento


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _json(resposta):
    return json.loads(resposta.content)


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _rascunho(escritorio, usuario, empresa_da_nota, documento):
    return servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)


# --- permissões --------------------------------------------------------------------------------


def test_paralegal_le_a_lista_do_mes(client, paralegal_a, empresa, nota):
    client.force_login(paralegal_a)
    resposta = client.get(_url("nfe_escrituracao_lista", empresa.pk) + "?ano=2026&mes=3")
    assert resposta.status_code == 200
    assert _json(resposta)["notas"][0]["situacao"] == "a_escriturar"


def test_paralegal_nao_cria_rascunho(client, paralegal_a, empresa, nota):
    client.force_login(paralegal_a)
    vinc = vinculo(nota, empresa)
    resposta = _post(client, _url("nfe_escrituracao_lista", empresa.pk), {"vinculo_id": vinc.pk})
    assert resposta.status_code == 403
    assert not EscrituracaoNFe.objects.exists()


def test_cliente_recebe_403_na_leitura_e_na_escrita(client, usuario_cliente_a, empresa, nota):
    client.force_login(usuario_cliente_a)
    assert (
        client.get(_url("nfe_escrituracao_lista", empresa.pk) + "?ano=2026&mes=3").status_code
        == 403
    )
    assert client.get(_url("nfe_conferencia", empresa.pk) + "?ano=2026&mes=3").status_code == 403
    vinc = vinculo(nota, empresa)
    assert (
        _post(
            client, _url("nfe_escrituracao_lista", empresa.pk), {"vinculo_id": vinc.pk}
        ).status_code
        == 403
    )


def test_gestor_cria_rascunho_201_e_repetir_da_200(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    vinc = vinculo(nota, empresa)
    url = _url("nfe_escrituracao_lista", empresa.pk)
    primeira = _post(client, url, {"vinculo_id": vinc.pk})
    assert primeira.status_code == 201
    assert _json(primeira)["estado"] == "rascunho"
    segunda = _post(client, url, {"vinculo_id": vinc.pk})
    assert segunda.status_code == 200
    assert _json(segunda)["id"] == _json(primeira)["id"]


# --- IDOR: outra empresa e outro escritório ------------------------------------------------------


def test_nota_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, usuario_gestor_a, empresa, outra_empresa, nota
):
    client.force_login(usuario_gestor_a)
    vinc = vinculo(nota, empresa)
    resposta = _post(
        client, _url("nfe_escrituracao_lista", outra_empresa.pk), {"vinculo_id": vinc.pk}
    )
    assert resposta.status_code == 404


def test_escrituracao_de_outra_empresa_recebe_404(
    client, usuario_gestor_a, empresa, outra_empresa, nota
):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    resposta = client.get(_url("nfe_escrituracao_detalhe", outra_empresa.pk, esc.pk))
    assert resposta.status_code == 404


def test_outro_escritorio_nao_enxerga_a_empresa_nem_a_nota(client, gestor_b, empresa, nota):
    client.force_login(gestor_b)
    assert (
        client.get(_url("nfe_escrituracao_lista", empresa.pk) + "?ano=2026&mes=3").status_code
        == 404
    )
    vinc = vinculo(nota, empresa)
    assert (
        _post(
            client, _url("nfe_escrituracao_lista", empresa.pk), {"vinculo_id": vinc.pk}
        ).status_code
        == 404
    )


# --- fluxo feliz ---------------------------------------------------------------------------------


def test_fluxo_completo_pela_api(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    vinc = vinculo(nota, empresa)
    criado = _json(
        _post(client, _url("nfe_escrituracao_lista", empresa.pk), {"vinculo_id": vinc.pk})
    )
    esc_id = criado["id"]
    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc_id)))
    ids = [item["item_id"] for item in detalhe["itens"]]
    assert [i["sugestao"]["natureza"] for i in detalhe["itens"]] == ["revenda", "producao_propria"]
    # Sem natureza confirmada, nada é segregado: a receita só existe depois da confirmação.
    assert detalhe["segregacao"]["normal"] == "0.00"
    naturezas = _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc_id),
        {"natureza": "revenda", "itens": ids[:1]},
    )
    assert naturezas.status_code == 200
    _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc_id),
        {"natureza": "producao_propria", "itens": ids[1:]},
    )
    efetivada = _post(client, _url("nfe_escrituracao_efetivar", empresa.pk, esc_id), {})
    assert efetivada.status_code == 201
    assert _json(efetivada)["receita_bruta"] == "2880.00"
    depois = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc_id)))
    assert depois["segregacao"]["normal"] == "2880.00"
    assert (
        _post(client, _url("nfe_escrituracao_efetivar", empresa.pk, esc_id), {}).status_code == 200
    )
    estorno = _post(
        client,
        _url("nfe_escrituracao_estornar", empresa.pk, esc_id),
        {"motivo": "Lançamento de teste"},
    )
    assert estorno.status_code == 200
    assert _json(estorno)["estado"] == "estornada"


def test_detalhe_traz_avisos_e_sugestao_com_motivo(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)))
    assert "avisos" in detalhe and isinstance(detalhe["avisos"], list)
    assert all("motivo" in i["sugestao"] for i in detalhe["itens"])


def test_efetivar_com_divergencia_responde_409_com_os_valores(
    client, usuario_gestor_a, empresa, escritorio_a
):
    divergente = xml.nfe(
        dets=[xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
        vnf="101.00",
        totais={"vProd": "100.00"},
        numero="8",
    )
    documento = receber(escritorio_a, usuario_gestor_a, divergente)
    esc = _rascunho(None, usuario_gestor_a, empresa, documento)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="revenda")
    client.force_login(usuario_gestor_a)
    resposta = _post(client, _url("nfe_escrituracao_efetivar", empresa.pk, esc.pk), {})
    assert resposta.status_code == 409
    assert "diverge" in _json(resposta)["detail"]


def test_conferencia_do_mes_pela_api(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    _rascunho(None, usuario_gestor_a, empresa, nota)
    resposta = client.get(_url("nfe_conferencia", empresa.pk) + "?ano=2026&mes=3")
    assert resposta.status_code == 200
    corpo = _json(resposta)
    assert corpo["recebidas"] == 1 and corpo["pendentes"] == 1 and corpo["escrituradas"] == 0
    assert corpo["itens_sem_sugestao"] == 0


def test_receita_do_mes_expoe_as_parcelas_de_nfe_numa_chave_propria(
    client, usuario_gestor_a, empresa, nota
):
    """`por_mercado` mantém o contrato da DL-074. As parcelas de NF-e vêm em `nfe_por_mercado`."""
    client.force_login(usuario_gestor_a)
    corpo = _json(client.get(_url("receita_do_mes", empresa.pk) + "?ano=2026&mes=3"))
    assert set(corpo["por_mercado"]["interno"]) == {"documento", "informado", "total"}
    interno = corpo["nfe_por_mercado"]["interno"]
    for campo in ("mercadoria", "devolucao", "saldo_entrada", "deduzido", "saldo_transportado"):
        assert interno[campo] == "0.00"


def test_reclassificacao_pela_api_conta_e_responde(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    _rascunho(None, usuario_gestor_a, empresa, nota)
    resposta = _post(
        client,
        _url("nfe_escrituracao_reclassificar", empresa.pk),
        {"natureza": "revenda", "cfop": "5102"},
    )
    assert resposta.status_code == 200
    assert _json(resposta) == {
        "natureza": "revenda",
        "escrituracoes_afetadas": 1,
        "itens_alterados": 1,
    }


# --- entrada estranha: 400, nunca 500 ----------------------------------------------------------


@pytest.mark.parametrize(
    "corpo",
    [
        {"natureza": "revenda\u0000", "itens": [1]},  # byte nulo
        {"natureza": "revenda\ud800", "itens": [1]},  # substituto isolado
        {"natureza": "revenda", "itens": [10**30]},  # número fora da faixa do banco
        {"natureza": "revenda", "itens": [2**63]},  # bigint estourado
        {"natureza": "revenda", "itens": []},  # lista vazia
        {"natureza": "revenda", "itens": [1] * 5001},  # lista acima do limite
        {"natureza": "revenda", "itens": [1], "campo_extra": 1},  # fora do contrato
        {"natureza": "", "itens": [1]},  # natureza vazia
    ],
)
def test_naturezas_com_entrada_estranha_respondem_400(
    client, usuario_gestor_a, empresa, nota, corpo
):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    resposta = _post(client, _url("nfe_escrituracao_naturezas", empresa.pk, esc.pk), corpo)
    assert resposta.status_code == 400


def test_id_gigante_na_rota_responde_400_e_nao_500(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    gigante = 10**25
    assert (
        client.get(f"/fiscal/api/empresas/{gigante}/nfe/escrituracao/?ano=2026&mes=3").status_code
        == 400
    )


def test_escrituracao_id_gigante_responde_400(client, usuario_gestor_a, empresa):
    client.force_login(usuario_gestor_a)
    gigante = 10**25
    resposta = client.get(f"/fiscal/api/empresas/{empresa.pk}/nfe/escrituracao/{gigante}/")
    assert resposta.status_code == 400


@pytest.mark.parametrize(
    "consulta",
    ["ano=2026&mes=13", "ano=1&mes=3", "ano=99999999999999999999&mes=3", "ano=abc&mes=3"],
)
def test_ano_e_mes_fora_da_faixa_respondem_400(client, usuario_gestor_a, empresa, consulta):
    client.force_login(usuario_gestor_a)
    assert client.get(_url("nfe_conferencia", empresa.pk) + "?" + consulta).status_code == 400


@pytest.mark.parametrize(
    "corpo",
    [
        {"natureza": "revenda", "inicio": "0001-01-01"},  # data fora da faixa
        {"natureza": "revenda", "fim": "9999-12-31"},  # data fora da faixa
        {"natureza": "revenda", "inicio": "2026-04-10", "fim": "2026-04-01"},  # inicio > fim
        {"natureza": "revenda", "cfop": "5102\u0000"},  # byte nulo no filtro
        {"natureza": "revenda", "ncm": "2203\ud800"},  # substituto no filtro
        {"natureza": "revenda", "inicio": "não é data"},  # formato errado
        {"natureza": "inventada"},  # natureza fora do catálogo
    ],
)
def test_reclassificacao_com_entrada_estranha_responde_400(
    client, usuario_gestor_a, empresa, corpo
):
    client.force_login(usuario_gestor_a)
    assert (
        _post(client, _url("nfe_escrituracao_reclassificar", empresa.pk), corpo).status_code == 400
    )


def test_estorno_com_motivo_nulo_responde_400(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    resposta = _post(
        client, _url("nfe_escrituracao_estornar", empresa.pk, esc.pk), {"motivo": "motivo\u0000"}
    )
    assert resposta.status_code == 400


def test_estorno_sem_motivo_responde_400(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    assert (
        _post(
            client, _url("nfe_escrituracao_estornar", empresa.pk, esc.pk), {"motivo": "   "}
        ).status_code
        == 400
    )


def test_corpo_de_efetivar_com_campo_estranho_responde_400(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    assert (
        _post(
            client, _url("nfe_escrituracao_efetivar", empresa.pk, esc.pk), {"natureza": "revenda"}
        ).status_code
        == 400
    )


def test_decimal_da_api_e_texto_sem_float(client, usuario_gestor_a, empresa, nota):
    client.force_login(usuario_gestor_a)
    esc = _rascunho(None, usuario_gestor_a, empresa, nota)
    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)))
    for item in detalhe["itens"]:
        assert isinstance(item["v_prod"], str)
        assert Decimal(item["v_prod"]) >= 0
