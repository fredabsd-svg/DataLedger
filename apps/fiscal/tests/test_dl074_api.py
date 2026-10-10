"""DL-074 (frente A) — API: receita do mês, confirmação, receita informada, RBT12 e caixa.

Critério 10 (isolamento e permissões como na DL-072): 404 para empresa de outro escritório
e para registro de outra empresa do mesmo escritório; 403 para CLIENTE e para papel sem
permissão de escriturar; 400 para campo fora do contrato. Cliente HTTP real, com sessão e
escritório ativo resolvidos pelo middleware.
"""

import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.fiscal import receita as servico
from apps.fiscal.models import ConfirmacaoReceitaMensal, EstadoReceitaInformada
from apps.fiscal.tests.test_dl074_suporte import (
    escriturar,
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
)
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


def _post(client, url, corpo=None):
    if corpo is None:
        return client.post(url)
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _base(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


@pytest.fixture
def empresa(empresa_a):
    fixar_inicio_de_uso(empresa_a, 2025, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def usuario_paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl074-a")


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-dl074-b")


# ---------------------------------------------------------------------------
# Critério 10 — isolamento
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404_em_todas_as_rotas(
    client, empresa, usuario_gestor_b, escritorio_a
):
    receita = servico.lancar_receita_informada(
        empresa,
        2026,
        5,
        "interno",
        "10",
        "ajuste",
        "M.",
        "S.",
        _usuario(escritorio_a, Papel.GESTOR, "gestor-dl074-a-iso"),
        situacao_iss="proprio_municipio",
    )
    client.force_login(usuario_gestor_b)

    assert client.get(f"{_base(empresa)}/receita/?ano=2026&mes=5").status_code == 404
    assert client.get(f"{_base(empresa)}/rbt12/?ano=2026&mes=5").status_code == 404
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5}).status_code
        == 404
    )
    assert (
        _post(
            client, f"{_base(empresa)}/receita/reabrir/", {"ano": 2026, "mes": 5, "motivo": "M."}
        ).status_code
        == 404
    )
    assert _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2026}).status_code == 404
    assert (
        _post(client, f"{_base(empresa)}/receitas-informadas/{receita.pk}/confirmar/").status_code
        == 404
    )


def test_receita_de_outra_empresa_do_mesmo_escritorio_responde_404(
    client, empresa, empresa_a2, usuario_gestor_a, escritorio_a
):
    # empresa_a2 é do MESMO escritório. A receita da empresa A não pode ser alcançada pela URL dela.
    receita = servico.lancar_receita_informada(
        empresa,
        2026,
        5,
        "interno",
        "10",
        "ajuste",
        "M.",
        "S.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    client.force_login(usuario_gestor_a)

    resposta = _post(client, f"{_base(empresa_a2)}/receitas-informadas/{receita.pk}/confirmar/")

    assert resposta.status_code == 404
    receita.refresh_from_db()
    assert receita.estado == EstadoReceitaInformada.RASCUNHO


# ---------------------------------------------------------------------------
# Critério 10 — permissões
# ---------------------------------------------------------------------------


def test_cliente_nao_le_nem_escreve(client, empresa, usuario_cliente_a):
    client.force_login(usuario_cliente_a)

    assert client.get(f"{_base(empresa)}/receita/?ano=2026&mes=5").status_code == 403
    assert client.get(f"{_base(empresa)}/rbt12/?ano=2026&mes=5").status_code == 403
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5}).status_code
        == 403
    )
    assert (
        _post(
            client,
            f"{_base(empresa)}/receitas-informadas/",
            {
                "ano": 2026,
                "mes": 5,
                "mercado": "interno",
                "situacao_iss": "proprio_municipio",
                "valor": "10",
                "origem": "ajuste",
                "motivo": "M.",
                "documento_suporte": "S.",
            },
        ).status_code
        == 403
    )
    assert not ConfirmacaoReceitaMensal.objects.exists()


def test_paralegal_le_mas_nao_escreve(client, empresa, usuario_paralegal_a):
    client.force_login(usuario_paralegal_a)

    assert client.get(f"{_base(empresa)}/receita/?ano=2026&mes=5").status_code == 200
    assert client.get(f"{_base(empresa)}/rbt12/?ano=2026&mes=5").status_code == 200
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5}).status_code
        == 403
    )
    assert _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2026}).status_code == 403
    assert not ConfirmacaoReceitaMensal.objects.exists()


def test_gestor_e_analista_escrevem(client, empresa, usuario_gestor_a, usuario_analista_a):
    # Papéis que escrituram (permissoes.PAPEIS_QUE_ESCRITURAM_FISCAL) confirmam o mês.
    client.force_login(usuario_gestor_a)
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 7}).status_code
        == 200
    )
    client.force_login(usuario_analista_a)
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 8}).status_code
        == 200
    )


# ---------------------------------------------------------------------------
# Critério 10 — campo fora do contrato e entrada inválida
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url, corpo",
    [
        ("receita/confirmar/", {"ano": 2026, "mes": 5, "valor_confirmado_interno": "0"}),
        ("receita/reabrir/", {"ano": 2026, "mes": 5, "motivo": "M.", "a_retificar": True}),
        (
            "receitas-informadas/",
            {
                "ano": 2026,
                "mes": 5,
                "mercado": "interno",
                "situacao_iss": "proprio_municipio",
                "valor": "10",
                "origem": "ajuste",
                "motivo": "M.",
                "documento_suporte": "S.",
                "estado": "confirmada",
            },
        ),
        ("regime-caixa/", {"ano": 2026, "estado": "x"}),
    ],
)
def test_campo_fora_do_contrato_e_400(client, empresa, usuario_gestor_a, url, corpo):
    client.force_login(usuario_gestor_a)

    assert _post(client, f"{_base(empresa)}/{url}", corpo).status_code == 400


def test_receita_sem_corpo_recusa_qualquer_campo(client, empresa, usuario_gestor_a):
    receita = informar_e_confirmar(empresa, usuario_gestor_a, 2026, 5, "10")
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/{receita.pk}/estornar/",
        {"motivo": "Motivo.", "extra": 1},
    )

    assert resposta.status_code == 400


@pytest.mark.parametrize(
    "valor, mensagem_campo",
    [("10.005", "valor"), ("0", "valor"), ("-3", "valor")],
)
def test_valor_invalido_e_400_pelo_contrato(
    client, empresa, usuario_gestor_a, valor, mensagem_campo
):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/",
        {
            "ano": 2026,
            "mes": 5,
            "mercado": "interno",
            "situacao_iss": "proprio_municipio",
            "valor": valor,
            "origem": "ajuste",
            "motivo": "M.",
            "documento_suporte": "S.",
        },
    )

    assert resposta.status_code == 400
    assert mensagem_campo in resposta.json()


def test_origem_historico_depois_do_inicio_de_uso_e_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/",
        {
            "ano": 2025,
            "mes": 3,
            "mercado": "interno",
            "situacao_iss": "proprio_municipio",
            "valor": "10",
            "origem": "historico_pre_sistema",
            "motivo": "M.",
            "documento_suporte": "S.",
        },
    )

    assert resposta.status_code == 400
    assert "início de uso" in str(resposta.json())


# ---------------------------------------------------------------------------
# Fluxo completo pela API
# ---------------------------------------------------------------------------


def test_fluxo_completo_pela_api(client, empresa, escritorio_a, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=701, competencia=(2026, 5), valor="1000"
    )

    criada = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/",
        {
            "ano": 2026,
            "mes": 5,
            "mercado": "interno",
            "situacao_iss": "proprio_municipio",
            "valor": "200.50",
            "origem": "outras_receitas_atividade",
            "motivo": "Outras receitas.",
            "documento_suporte": "Extrato PGDAS-D PA 05/2026 (sintético).",
        },
    )
    assert criada.status_code == 201
    receita_id = criada.json()["id"]
    assert criada.json()["estado"] == "rascunho"

    confirmada = _post(client, f"{_base(empresa)}/receitas-informadas/{receita_id}/confirmar/")
    assert confirmada.status_code == 200
    assert confirmada.json()["estado"] == "confirmada"

    mes = _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5})
    assert mes.status_code == 200
    assert mes.json()["situacao"] == "confirmado"
    assert mes.json()["por_mercado"]["interno"] == {
        "documento": "1000.00",
        "informado": "200.50",
        "total": "1200.50",
    }

    segunda = _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5})
    assert segunda.status_code == 409

    estornada = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/{receita_id}/estornar/",
        {"motivo": "Valor digitado errado."},
    )
    assert estornada.status_code == 200
    assert estornada.json()["estado"] == "estornada"

    depois = client.get(f"{_base(empresa)}/receita/?ano=2026&mes=5").json()
    assert depois["situacao"] == "a_retificar"
    assert depois["a_retificar"] is True
    assert depois["por_mercado"]["interno"]["total"] == "1000.00"

    # Mês já reaberto pelo estorno: não é confirmado, então não há o que reabrir (409).
    reaberta = _post(
        client, f"{_base(empresa)}/receita/reabrir/", {"ano": 2026, "mes": 5, "motivo": "Revisão."}
    )
    assert reaberta.status_code == 409


def test_reabrir_sem_motivo_e_400_e_reabrir_com_motivo_e_200(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    assert (
        _post(client, f"{_base(empresa)}/receita/confirmar/", {"ano": 2026, "mes": 5}).status_code
        == 200
    )

    assert (
        _post(
            client, f"{_base(empresa)}/receita/reabrir/", {"ano": 2026, "mes": 5, "motivo": "  "}
        ).status_code
        == 400
    )
    reaberta = _post(
        client,
        f"{_base(empresa)}/receita/reabrir/",
        {"ano": 2026, "mes": 5, "motivo": "Extrato corrigido."},
    )

    assert reaberta.status_code == 200
    assert reaberta.json()["situacao"] == "nao_confirmado"
    assert reaberta.json()["motivo_reabertura"] == "Extrato corrigido."


def test_rbt12_pela_api_nao_apuravel_com_lista_e_recusa_nomeada(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    # Nenhum mês confirmado: a janela de 2026-06 é não apurável, com a lista de meses.
    resposta = client.get(f"{_base(empresa)}/rbt12/?ano=2026&mes=6")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["apuravel"] is False
    assert corpo["por_mercado"]["interno"]["apurado"] is None
    assert len(corpo["meses_pendentes"]) == 12
    assert corpo["meses_pendentes"][0] == {"ano": 2025, "mes": 6, "situacao": "nao_confirmado"}


def test_rbt12_recusa_nomeada_vira_409(client, empresa_a, usuario_gestor_a):
    preparar_simples(empresa_a, abertura=None, inicio_simples=date(2018, 1, 1))
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/rbt12/?ano=2026&mes=6")

    assert resposta.status_code == 409
    assert "data de abertura no CNPJ" in resposta.json()["detail"]


def test_rbt12_de_2029_vira_409_com_a_resolucao_190(client, empresa, usuario_gestor_a):
    # DL-088: 2027 e 2028 são apurados (RBT12 defasado); a recusa passou a ser de 2029 (HI-146).
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"{_base(empresa)}/rbt12/?ano=2029&mes=1")

    assert resposta.status_code == 409
    assert "190/2026" in resposta.json()["detail"]


def test_regime_caixa_pela_api_2026_201_duplicado_409_e_2027_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    assert _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2027}).status_code == 400
    primeira = _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2026})
    assert primeira.status_code == 201
    assert primeira.json() == {"empresa_id": empresa.pk, "ano_calendario": 2026}
    assert _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2026}).status_code == 409


def test_aviso_de_caixa_aparece_no_rbt12_depois_da_opcao(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    _post(client, f"{_base(empresa)}/regime-caixa/", {"ano": 2026})

    corpo = client.get(f"{_base(empresa)}/rbt12/?ano=2026&mes=6").json()

    assert "regime_caixa_em_ano" in {aviso["codigo"] for aviso in corpo["avisos"]}


def test_receita_do_mes_mostra_a_composicao_e_as_receitas_do_mes(
    client, empresa, escritorio_a, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=702, competencia=(2026, 5), valor="300"
    )
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 5, "120.25")

    corpo = client.get(f"{_base(empresa)}/receita/?ano=2026&mes=5").json()

    assert corpo["situacao"] == "nao_confirmado"
    assert corpo["por_mercado"]["interno"] == {
        "documento": "300.00",
        "informado": "120.25",
        "total": "420.25",
    }
    assert corpo["por_mercado"]["externo"] == {
        "documento": "0.00",
        "informado": "0.00",
        "total": "0.00",
    }
    assert [r["origem"] for r in corpo["receitas_informadas"]] == ["outras_receitas_atividade"]
