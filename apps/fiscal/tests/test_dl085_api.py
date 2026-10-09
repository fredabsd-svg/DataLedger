"""DL-085 (frente A), critério 6 e a API: permissões no servidor, isolamento, e o contrato de
status.

Status: 200 (progresso), 409 (assinatura desatualizada, ou lote em andamento com outro ato), 400
(entrada inválida), 404 (empresa ou lote de outro escritório, ou de outra empresa). CLIENTE é 403.
"""

import json

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import EscrituracaoNFe, LoteEscrituracaoNFe, NaturezaItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.suporte_dl085 import (
    CNPJ_SEGUNDA_EMPRESA,
    NCM_COMBUSTIVEL,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _json(resposta):
    return json.loads(resposta.content)


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-api-dl085")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-api-dl085")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-api-b-dl085")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto API DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def empresa_vizinha(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Vizinha API DL085 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )


def _notas(escritorio, usuario):
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio, usuario, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio, usuario, numero=numero, valor="80.00", cfop="5102", csosn="102")


def test_previa_devolve_grupos_fora_do_lote_e_a_assinatura(escritorio_a, gestor, empresa, client):
    _notas(escritorio_a, gestor)
    nfce(escritorio_a, gestor, numero=9, cfop="5949", csosn="102")
    client.force_login(gestor)

    # A prévia não lê XML: a leitura do mês é feita pelo endpoint antes.
    client.post(
        _url("nfe_lote_ler", empresa.pk),
        data=json.dumps({"ano": 2026, "mes": 3, "limite": 50}),
        content_type="application/json",
    )
    resposta = client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3")

    assert resposta.status_code == 200
    corpo = _json(resposta)
    assert len(corpo["assinatura"]) == 64
    assert sorted(g["notas"] for g in corpo["grupos"]) == [2, 3]
    combustivel = next(g for g in corpo["grupos"] if g["notas"] == 3)
    assert combustivel["receita_bruta"] == "390.00"
    assert combustivel["assinaturas"][0]["natureza_sugerida"] == "combustivel"
    assert combustivel["assinaturas"][0]["rotulo_natureza"]
    assert {n["natureza"] for n in combustivel["naturezas_permitidas"]} >= {"combustivel"}
    assert corpo["fora_do_lote"]["por_motivo"] == {"sem_sugestao": 1}
    assert corpo["fora_do_lote"]["notas"][0]["motivo"] == (
        "item 1: sem sinal suficiente: escolha a natureza"
    )
    assert corpo["lote_em_andamento"] is None


def test_paralegal_le_a_previa_mas_nao_confirma(escritorio_a, gestor, paralegal, empresa, client):
    _notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    client.force_login(paralegal)

    assert client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3").status_code == 200
    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {"ano": 2026, "mes": 3, "assinatura": previa.assinatura},
    )
    assert resposta.status_code == 403
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_cliente_recebe_403_na_previa_e_na_confirmacao(
    escritorio_a, gestor, usuario_cliente_a, empresa, client
):
    _notas(escritorio_a, gestor)
    client.force_login(usuario_cliente_a)

    assert client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3").status_code == 403
    assert (
        _post(client, _url("nfe_lote_confirmar", empresa.pk), {"ano": 2026, "mes": 3}).status_code
        == 403
    )


def test_empresa_de_outro_escritorio_responde_404(escritorio_a, gestor, gestor_b, empresa, client):
    _notas(escritorio_a, gestor)
    client.force_login(gestor_b)

    assert client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3").status_code == 404
    assert (
        _post(client, _url("nfe_lote_confirmar", empresa.pk), {"ano": 2026, "mes": 3}).status_code
        == 404
    )


def test_confirmacao_com_assinatura_desatualizada_responde_409_e_nada_e_efetivado(
    escritorio_a, gestor, empresa, client
):
    _notas(escritorio_a, gestor)
    antiga = previa_lida(empresa, 2026, 3).assinatura
    nfce(escritorio_a, gestor, numero=6, valor="10.00")
    client.force_login(gestor)

    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {"ano": 2026, "mes": 3, "assinatura": antiga},
    )

    assert resposta.status_code == 409
    assert "Nada foi efetivado" in _json(resposta)["detail"]
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_confirmacao_em_partes_pela_api_ate_terminar(escritorio_a, gestor, empresa, client):
    """200 com o progresso. A continuação leva só `lote_id`. A última parte devolve `terminou`."""
    _notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    client.force_login(gestor)

    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {"ano": 2026, "mes": 3, "assinatura": previa.assinatura, "limite": 2},
    )
    assert resposta.status_code == 200
    progresso = _json(resposta)
    assert progresso["efetivadas_nesta_chamada"] == 2
    assert progresso["restantes"] == 3
    assert progresso["terminou"] is False
    lote_id = progresso["lote_id"]

    partes = 0
    while not progresso["terminou"]:
        resposta = _post(
            client, _url("nfe_lote_confirmar", empresa.pk), {"lote_id": lote_id, "limite": 2}
        )
        assert resposta.status_code == 200
        progresso = _json(resposta)
        partes += 1
        assert partes < 10
    assert progresso["efetivadas_total"] == 5
    assert progresso["falhas_total"] == 0
    assert progresso["falhas_nesta_chamada"] == []
    assert RegistroAuditoria.objects.filter(
        acao="escrituracao_nfe.lote_concluido", objeto_id=str(lote_id)
    ).exists()


def test_escolha_pela_api_troca_a_natureza_do_grupo(escritorio_a, gestor, empresa, client):
    _notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    grupo = next(g for g in previa.grupos if g.quantidade_notas == 3)
    client.force_login(gestor)

    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {
            "ano": 2026,
            "mes": 3,
            "assinatura": previa.assinatura,
            "escolhas": [
                {"grupo": grupo.chave, "naturezas": {"5656|500|combustivel": "combustivel_revenda"}}
            ],
        },
    )

    assert resposta.status_code == 200
    assert _json(resposta)["efetivadas_total"] == 5
    assert (
        NaturezaItemNFe.objects.filter(
            escrituracao__empresa=empresa, natureza="combustivel_revenda"
        ).count()
        == 3
    )


@pytest.mark.parametrize(
    "corpo,trecho",
    [
        pytest.param({"assinatura": "x" * 64}, "ano", id="sem-ano-mes-nem-lote"),
        pytest.param({"ano": 2026, "mes": 13, "assinatura": "x"}, "mes", id="mes-fora-da-faixa"),
        pytest.param({"ano": 2026, "mes": 3, "limite": 0}, "limite", id="limite-zero"),
        pytest.param({"ano": 2026, "mes": 3, "limite": 151}, "limite", id="limite-acima-do-teto"),
        pytest.param({"ano": 2026, "mes": 3, "campo_novo": 1}, "campo_novo", id="campo-fora"),
        pytest.param(
            {
                "ano": 2026,
                "mes": 3,
                "escolhas": [
                    {"grupo": "a", "naturezas": {}},
                    {"grupo": "a", "naturezas": {}},
                ],
            },
            "repetido",
            id="grupo-repetido",
        ),
        pytest.param(
            {"ano": 2026, "mes": 3, "escolhas": [{"grupo": "g\x00", "naturezas": {}}]},
            "caractere",
            id="byte-nulo",
        ),
    ],
)
def test_entrada_invalida_responde_400_sem_gravar(
    escritorio_a, gestor, empresa, client, corpo, trecho
):
    _notas(escritorio_a, gestor)
    client.force_login(gestor)

    resposta = _post(client, _url("nfe_lote_confirmar", empresa.pk), corpo)

    assert resposta.status_code == 400, resposta.content
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_escolha_que_quebra_a_conferencia_responde_400_e_nao_grava(
    escritorio_a, gestor, empresa, client
):
    _notas(escritorio_a, gestor)
    nfce(
        escritorio_a,
        gestor,
        numero=6,
        dets=[
            xml.det(
                1,
                cfop="5656",
                vprod="100.00",
                vfrete="10.00",
                ncm=NCM_COMBUSTIVEL,
                icms_xml=xml.icms(csosn="102"),
            )
        ],
        vnf="110.00",
        totais={"vProd": "100.00", "vFrete": "10.00"},
    )
    previa = previa_lida(empresa, 2026, 3)
    grupo = next(g for g in previa.grupos if g.quantidade_notas == 1)
    client.force_login(gestor)

    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {
            "ano": 2026,
            "mes": 3,
            "assinatura": previa.assinatura,
            "escolhas": [
                {"grupo": grupo.chave, "naturezas": {"5656|102|combustivel": "remessa_retorno"}}
            ],
        },
    )

    assert resposta.status_code == 400
    assert "Nada foi efetivado" in str(_json(resposta))
    assert not LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_lote_de_outra_empresa_responde_404(escritorio_a, gestor, empresa, empresa_vizinha, client):
    """Lote da empresa vizinha, com a URL da empresa: 404. Lote que não existe: 404."""
    _notas(escritorio_a, gestor)
    previa = previa_lida(empresa, 2026, 3)
    progresso = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=1)
    client.force_login(gestor)

    assert (
        _post(
            client, _url("nfe_lote_confirmar", empresa_vizinha.pk), {"lote_id": progresso.lote_id}
        ).status_code
        == 404
    )
    assert (
        _post(client, _url("nfe_lote_confirmar", empresa.pk), {"lote_id": 999999}).status_code
        == 404
    )


def test_previa_com_ano_invalido_responde_400(escritorio_a, gestor, empresa, client):
    client.force_login(gestor)

    assert client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=1800&mes=3").status_code == 400
    assert client.get(_url("nfe_lote_previa", empresa.pk)).status_code == 400


def test_corrida_que_chega_ao_banco_responde_400_com_a_mensagem_do_registro(
    escritorio_a, gestor, empresa, client, monkeypatch
):
    """Corrida: outro lote em andamento foi gravado DEPOIS da checagem do serviço. O banco recusa
    o segundo (`lote_nfe_em_andamento_unico_por_mes`), e a API responde 400 com a mensagem do
    registro de restrições, não 500 (padrão BL-144). A checagem é simulada: não vê o lote aberto."""
    _notas(escritorio_a, gestor)
    lote.confirmar_lote(
        empresa, 2026, 3, previa_lida(empresa, 2026, 3).assinatura, {}, gestor, limite=1
    )
    assert LoteEscrituracaoNFe.objects.filter(empresa=empresa).count() == 1
    assinatura_atual = previa_lida(empresa, 2026, 3).assinatura
    monkeypatch.setattr(lote, "_lote_em_andamento", lambda *_a, **_k: None)
    client.force_login(gestor)

    resposta = _post(
        client,
        _url("nfe_lote_confirmar", empresa.pk),
        {"ano": 2026, "mes": 3, "assinatura": assinatura_atual},
    )

    assert resposta.status_code == 400, resposta.content
    assert "Já existe um lote de escrituração em andamento" in str(_json(resposta))
    assert LoteEscrituracaoNFe.objects.filter(empresa=empresa).count() == 1
