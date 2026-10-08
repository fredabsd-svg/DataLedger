"""DL-074 (frente A) — data de abertura no CNPJ da empresa (HI-65).

Critério 1 da frente A: campo opcional no banco, não futuro, lido e escrito pela API de
empresa. A obrigatoriedade para apurar é verificada no RBT12 (ver test_dl074_rbt12_referencia).
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa, validar_data_abertura_nao_futura
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CNPJ = "11122233000183"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL074", cnpj="91100000000074")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-dl074-abertura", email="gestor-dl074@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def empresa(escritorio):
    return Empresa.objects.create(escritorio=escritorio, razao_social="Abertura Ltda", cnpj=CNPJ)


def test_campo_nasce_nulo_e_opcional(empresa):
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj is None


def test_validador_recusa_data_futura_e_aceita_hoje_passado_e_vazio():
    hoje = timezone.localdate()

    validar_data_abertura_nao_futura(None)
    validar_data_abertura_nao_futura(hoje)
    validar_data_abertura_nao_futura(hoje - timedelta(days=3650))
    with pytest.raises(ValidationError, match="não pode ser futura"):
        validar_data_abertura_nao_futura(hoje + timedelta(days=1))


def test_full_clean_da_empresa_recusa_abertura_futura(empresa):
    empresa.data_abertura_cnpj = timezone.localdate() + timedelta(days=1)

    with pytest.raises(ValidationError) as info:
        empresa.full_clean()

    assert "data_abertura_cnpj" in info.value.message_dict


def test_api_cria_com_data_de_abertura_e_devolve_o_campo(client, gestor):
    client.login(username="gestor-dl074-abertura", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data={
            "razao_social": "Nova Abertura Ltda",
            "cnpj": CNPJ,
            "data_abertura_cnpj": "2026-03-10",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert resposta.json()["data_abertura_cnpj"] == "2026-03-10"
    assert Empresa.objects.get(
        razao_social="Nova Abertura Ltda"
    ).data_abertura_cnpj.isoformat() == ("2026-03-10")


def test_api_recusa_data_futura_com_400_no_campo(client, gestor, empresa):
    client.login(username="gestor-dl074-abertura", password="senha-forte-123")
    futura = (timezone.localdate() + timedelta(days=5)).isoformat()

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"data_abertura_cnpj": futura},
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "data_abertura_cnpj" in resposta.json()
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj is None


def test_patch_sem_o_campo_mantem_a_data_gravada(client, gestor, empresa):
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj="2015-03-10")
    client.login(username="gestor-dl074-abertura", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"nome_fantasia": "Fantasia Sintética"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj.isoformat() == "2015-03-10"


# ---------------------------------------------------------------------------
# A2 (Proposta 2) — PATCH/PUT que altera `data_abertura_cnpj` gravava com 500 (a data
# não é JSON-serializável na trilha). Agora grava, e a trilha guarda a data em ISO 8601.
# ---------------------------------------------------------------------------


def _login_gestor(client):
    client.login(username="gestor-dl074-abertura", password="senha-forte-123")


def _trilha_da_atualizacao(empresa):
    from apps.auditoria.models import RegistroAuditoria

    return list(
        RegistroAuditoria.objects.filter(acao="empresa.atualizada", objeto_id=str(empresa.pk))
    )


def test_patch_que_muda_a_data_grava_e_registra_antes_e_depois_em_iso(client, gestor, empresa):
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj="2019-01-01")
    _login_gestor(client)

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"data_abertura_cnpj": "2021-02-02"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj.isoformat() == "2021-02-02"
    trilha = _trilha_da_atualizacao(empresa)
    assert len(trilha) == 1
    assert trilha[0].detalhes["valores_anteriores"] == {"data_abertura_cnpj": "2019-01-01"}
    assert trilha[0].detalhes["valores_novos"] == {"data_abertura_cnpj": "2021-02-02"}


def test_patch_que_preenche_data_em_empresa_sem_data_grava_com_200(client, gestor, empresa):
    # Caso central do achado: empresa já cadastrada, sem data, recebe a data pela API.
    _login_gestor(client)

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"data_abertura_cnpj": "2020-05-17"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj.isoformat() == "2020-05-17"
    trilha = _trilha_da_atualizacao(empresa)
    assert trilha[0].detalhes["valores_anteriores"] == {"data_abertura_cnpj": None}
    assert trilha[0].detalhes["valores_novos"] == {"data_abertura_cnpj": "2020-05-17"}


def test_patch_que_limpa_a_data_grava_com_200_e_registra_null(client, gestor, empresa):
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj="2019-01-01")
    _login_gestor(client)

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"data_abertura_cnpj": None},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj is None
    trilha = _trilha_da_atualizacao(empresa)
    assert trilha[0].detalhes["valores_anteriores"] == {"data_abertura_cnpj": "2019-01-01"}
    assert trilha[0].detalhes["valores_novos"] == {"data_abertura_cnpj": None}


def test_put_com_data_de_abertura_grava_com_200(client, gestor, empresa):
    _login_gestor(client)

    resposta = client.put(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={
            "razao_social": "Abertura Ltda",
            "cnpj": CNPJ,
            "data_abertura_cnpj": "2018-01-01",
        },
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    empresa.refresh_from_db()
    assert empresa.data_abertura_cnpj.isoformat() == "2018-01-01"
    trilha = _trilha_da_atualizacao(empresa)
    assert trilha[0].detalhes["valores_novos"]["data_abertura_cnpj"] == "2018-01-01"


def test_reenviar_a_mesma_data_nao_gera_trilha_nova(client, gestor, empresa):
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj="2019-01-01")
    _login_gestor(client)

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.pk]),
        data={"data_abertura_cnpj": "2019-01-01"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    assert _trilha_da_atualizacao(empresa) == []
