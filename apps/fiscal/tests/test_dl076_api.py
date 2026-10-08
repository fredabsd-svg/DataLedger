"""DL-076 (frente A), critério 8: API do ISS por município — permissões e isolamento.

Cliente HTTP real, com sessão e escritório ativo resolvidos pelo middleware. Quem escritura
(gestor) escreve; PARALEGAL só lê; CLIENTE não acessa. Empresa ou alíquota de outro escritório
responde 404. Campo fora do contrato responde 400 com o nome do campo.
"""

import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.fiscal import iss_municipal as iss
from apps.fiscal.models import AliquotaIssMunicipal, RegimeIss, RegimeIssEmpresa
from apps.fiscal.tests.suporte_iss_dl076 import PALMAS, aliquota, cenario_outubro, regime_aliquota
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def usuario_paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl076-a")


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-dl076-b")


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _patch(client, url, corpo):
    return client.patch(url, data=json.dumps(corpo), content_type="application/json")


def _aliquota_payload(**mudancas):
    corpo = {
        "municipio_ibge": PALMAS,
        "subitem": "17.01",
        "percentual": "5.0000",
        "fonte": "Alíquota sintética (teste DL-076)",
        "inicio_vigencia": "2026-01-01",
    }
    corpo.update(mudancas)
    return corpo


# ---------------------------------------------------------------------------
# Alíquota: escrita pelo escritório ativo, com a faixa de 2% a 5%
# ---------------------------------------------------------------------------


def test_gestor_cadastra_aliquota_e_recebe_201(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(client, "/fiscal/api/iss/aliquotas/nova/", _aliquota_payload())
    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["percentual"] == "5.0000"
    assert corpo["avisos"] == []


def test_excecao_do_minimo_sai_com_aviso_no_201(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        "/fiscal/api/iss/aliquotas/nova/",
        _aliquota_payload(subitem="07.02", percentual="1.5000"),
    )
    assert resposta.status_code == 201
    assert resposta.json()["avisos"][0]["codigo"] == "aliquota_abaixo_do_minimo_excecao"


def test_aliquota_acima_de_5_recebe_400_com_a_mensagem_da_lei(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client, "/fiscal/api/iss/aliquotas/nova/", _aliquota_payload(percentual="5.5000")
    )
    assert resposta.status_code == 400
    assert "máximo de 5%" in str(resposta.json())
    assert AliquotaIssMunicipal.objects.count() == 0


def test_sobreposicao_recebe_409(client, usuario_gestor_a, escritorio_a):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client, "/fiscal/api/iss/aliquotas/nova/", _aliquota_payload(inicio_vigencia="2026-06-01")
    )
    assert resposta.status_code == 409


def test_campo_fora_do_contrato_recebe_400_nomeando_o_campo(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(client, "/fiscal/api/iss/aliquotas/nova/", _aliquota_payload(taxa="5"))
    assert resposta.status_code == 400
    assert "taxa" in str(resposta.json())


def test_paralegal_nao_cadastra_aliquota_403(client, usuario_paralegal_a):
    client.force_login(usuario_paralegal_a)
    resposta = _post(client, "/fiscal/api/iss/aliquotas/nova/", _aliquota_payload())
    assert resposta.status_code == 403
    assert AliquotaIssMunicipal.objects.count() == 0


def test_paralegal_le_as_aliquotas_do_escritorio(
    client, usuario_paralegal_a, escritorio_a, usuario_gestor_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    client.force_login(usuario_paralegal_a)
    resposta = client.get("/fiscal/api/iss/aliquotas/")
    assert resposta.status_code == 200
    assert [a["subitem"] for a in resposta.json()] == ["17.01"]


def test_cliente_nao_acessa_as_aliquotas_403(client, usuario_cliente_a):
    client.force_login(usuario_cliente_a)
    assert client.get("/fiscal/api/iss/aliquotas/").status_code == 403


def test_alteracao_de_aliquota_de_outro_escritorio_recebe_404(
    client, usuario_gestor_b, escritorio_a, usuario_gestor_a
):
    alvo = aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    client.force_login(usuario_gestor_b)
    resposta = _patch(client, f"/fiscal/api/iss/aliquotas/{alvo.pk}/", {"fonte": "invadida"})
    assert resposta.status_code == 404
    alvo.refresh_from_db()
    assert alvo.fonte != "invadida"


def test_lista_de_aliquotas_nao_mostra_o_outro_escritorio(
    client, usuario_gestor_a, usuario_gestor_b, escritorio_b
):
    aliquota(escritorio_b, usuario_gestor_b, "17.01", "4.0000")
    client.force_login(usuario_gestor_a)
    assert client.get("/fiscal/api/iss/aliquotas/").json() == []


def test_patch_encerra_a_vigencia_sem_excluir(client, usuario_gestor_a, escritorio_a):
    alvo = aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    client.force_login(usuario_gestor_a)
    resposta = _patch(
        client, f"/fiscal/api/iss/aliquotas/{alvo.pk}/", {"fim_vigencia": "2026-09-30"}
    )
    assert resposta.status_code == 200
    alvo.refresh_from_db()
    assert alvo.fim_vigencia == date(2026, 9, 30)


# ---------------------------------------------------------------------------
# Regime por empresa, com isolamento
# ---------------------------------------------------------------------------


def _regime_payload(**mudancas):
    corpo = {"exercicio": 2026, "regime": RegimeIss.ALIQUOTA, "municipio_ibge": PALMAS}
    corpo.update(mudancas)
    return corpo


def test_gestor_cadastra_regime_e_repetir_o_exercicio_da_409(client, usuario_gestor_a, empresa_a):
    client.force_login(usuario_gestor_a)
    url = f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/nova/"
    assert _post(client, url, _regime_payload()).status_code == 201
    assert _post(client, url, _regime_payload(regime=RegimeIss.FIXO_AUTONOMO)).status_code == 409


def test_regime_de_empresa_de_outro_escritorio_recebe_404(client, usuario_gestor_b, empresa_a):
    client.force_login(usuario_gestor_b)
    url = f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/nova/"
    assert _post(client, url, _regime_payload()).status_code == 404
    assert client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/").status_code == 404


def test_paralegal_le_regime_mas_nao_grava(
    client, usuario_paralegal_a, empresa_a, usuario_gestor_a
):
    regime_aliquota(empresa_a, usuario_gestor_a)
    client.force_login(usuario_paralegal_a)
    assert client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/").status_code == 200
    assert (
        _post(
            client,
            f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/nova/",
            _regime_payload(exercicio=2027),
        ).status_code
        == 403
    )


def test_regime_fora_do_catalogo_recebe_400(client, usuario_gestor_a, empresa_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(
        client,
        f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/nova/",
        _regime_payload(regime="lucro"),
    )
    assert resposta.status_code == 400


def test_alterar_regime_muda_o_valor_com_trilha(client, usuario_gestor_a, empresa_a):
    regime = regime_aliquota(empresa_a, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    resposta = _patch(
        client,
        f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/{regime.pk}/",
        {"regime": RegimeIss.FIXO_AUTONOMO},
    )
    assert resposta.status_code == 200
    regime.refresh_from_db()
    assert regime.regime == RegimeIss.FIXO_AUTONOMO


# ---------------------------------------------------------------------------
# Apurações e relatórios: leitura, isolamento e recusa com a lista de bloqueios
# ---------------------------------------------------------------------------


def test_apuracao_pela_api_devolve_total_e_vencimentos(
    client, usuario_gestor_a, escritorio_a, empresa_a
):
    cenario_outubro(escritorio_a, usuario_gestor_a, empresa_a)
    client.force_login(usuario_gestor_a)
    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=10")
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["total"] == "237.70"
    assert corpo["vencimento_proprio"] == "2026-11-10"
    assert corpo["vencimento_retido"] == "2026-11-15"
    assert {p["numero"] for p in corpo["pendencias"]} == {"1004", "1006"}
    assert all(p["dispositivo"] for p in corpo["memoria"])


def test_apuracao_recusada_devolve_409_com_todos_os_bloqueios(client, usuario_gestor_a, empresa_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=10")
    assert resposta.status_code == 409
    assert [b["codigo"] for b in resposta.json()["bloqueios"]] == ["regime_iss_ausente"]


def test_apuracao_de_empresa_de_outro_escritorio_recebe_404(client, usuario_gestor_b, empresa_a):
    client.force_login(usuario_gestor_b)
    assert (
        client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=10").status_code
        == 404
    )
    assert (
        client.get(
            f"/fiscal/api/empresas/{empresa_a.pk}/iss/retido-sofrido/?ano=2026&mes=10"
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/fiscal/api/empresas/{empresa_a.pk}/iss/outros-municipios/?ano=2026&mes=10"
        ).status_code
        == 404
    )


def test_apuracao_do_fixo_devolve_409_com_as_notas_listadas(client, usuario_gestor_a, empresa_a):
    RegimeIssEmpresa.objects.create(
        empresa=empresa_a,
        exercicio=2026,
        regime=RegimeIss.FIXO_SOCIEDADE_PROFISSIONAIS,
        municipio_ibge=PALMAS,
        criado_por=usuario_gestor_a,
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=10")
    assert resposta.status_code == 409
    assert resposta.json()["bloqueios"][0]["codigo"] == "regime_fixo"
    assert resposta.json()["notas"] == []


def test_consulta_sem_ano_ou_mes_recebe_400(client, usuario_gestor_a, empresa_a):
    client.force_login(usuario_gestor_a)
    assert client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/").status_code == 400
    assert (
        client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=13").status_code
        == 400
    )


def test_cliente_nao_le_apuracao_403(client, usuario_cliente_a, empresa_a):
    client.force_login(usuario_cliente_a)
    assert (
        client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano=2026&mes=10").status_code
        == 403
    )


def test_paralegal_le_relatorios_e_regras(client, usuario_paralegal_a, empresa_a):
    client.force_login(usuario_paralegal_a)
    assert (
        client.get(
            f"/fiscal/api/empresas/{empresa_a.pk}/iss/retido-sofrido/?ano=2026&mes=10"
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/fiscal/api/empresas/{empresa_a.pk}/iss/outros-municipios/?ano=2026&mes=10"
        ).status_code
        == 200
    )
    regras = client.get("/fiscal/api/iss/regras-municipio/").json()
    assert any(r["municipio_ibge"] == PALMAS and r["dia_vencimento_proprio"] == 10 for r in regras)


def test_regras_nao_tem_rota_de_escrita(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = _post(client, "/fiscal/api/iss/regras-municipio/", {"municipio_ibge": "1100205"})
    assert resposta.status_code == 405


def test_cadastro_de_regra_tem_so_servico_e_nenhuma_rota_de_escrita():
    # A regra do município é dado legal: o serviço existe, e nenhuma rota de API o chama.
    from apps.fiscal import api as api_fiscal
    from apps.fiscal import urls_api

    assert callable(iss.cadastrar_regra_municipio)
    assert not hasattr(api_fiscal, "cadastrar_regra_municipio")
    nomes = {p.name for p in urls_api.urlpatterns}
    assert not any("regra" in nome and "cadastr" in nome for nome in nomes)
