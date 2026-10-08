"""DL-075 (frente A) — API: pré-DAS, atividades e folha para o fator r.

Critério 10 (isolamento e permissões como na DL-072 e na DL-074): 404 para empresa de
outro escritório e para registro de outra empresa do mesmo escritório; 403 para CLIENTE
e para papel sem permissão de escriturar; 400 para campo fora do contrato. Cliente HTTP
real, com sessão e escritório ativo resolvidos pelo middleware.
"""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.fiscal import pre_das as servico
from apps.fiscal.models import EnquadramentoAtividade, FolhaFatorR
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    folhas_dos_12_meses,
    janela_de_receitas,
    receber_e_confirmar_mes,
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


def _patch(client, url, corpo):
    return client.patch(url, data=json.dumps(corpo), content_type="application/json")


def _base(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


@pytest.fixture
def empresa(empresa_a, usuario_gestor_a):
    return cenario_simples(empresa_a)


@pytest.fixture
def usuario_paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-dl075-a")


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-dl075-b")


def _atividade_payload(**mudancas):
    corpo = {
        "descricao": "Consultoria sintética",
        "codigo_subitem": "17.01",
        "enquadramento": EnquadramentoAtividade.ANEXO_III,
        "inicio": "2018-01-01",
        "padrao": True,
    }
    corpo.update(mudancas)
    return corpo


def _folha_payload(ano=2026, mes=5, **mudancas):
    corpo = {
        "ano": ano,
        "mes": mes,
        "remuneracao_empregados_avulsos": "1000.00",
        "pro_labore_autonomos": "0.00",
        "decimo_terceiro": "0.00",
        "cpp_recolhida": "0.00",
        "fgts_recolhido": "0.00",
        "documento_suporte": SUPORTE_SINTETICO,
    }
    corpo.update(mudancas)
    return corpo


# ---------------------------------------------------------------------------
# Pré-DAS: leitura, 409 com a lista de bloqueios, 400 na competência
# ---------------------------------------------------------------------------


def test_pre_das_responde_200_com_os_valores_em_texto_exato(client, empresa, usuario_gestor_a):
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=6")

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total"] == "8080.00"
    assert dados["total_por_tributo"]["CPP"] == "3506.72"
    anexo = dados["anexos"][0]
    assert (anexo["anexo"], anexo["faixa"], anexo["aliquota_efetiva"]) == ("III", 2, "0.0808")
    assert any("§ 1º-A" in passo["dispositivo"] for passo in dados["memoria"])


def test_pre_das_recusado_responde_409_com_todos_os_bloqueios(client, empresa, usuario_gestor_a):
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=6")

    assert resposta.status_code == 409
    codigos = {b["codigo"] for b in resposta.json()["bloqueios"]}
    assert "sem_atividade_padrao" in codigos
    assert "mes_nao_confirmado" in codigos


def test_pre_das_2027_responde_409_citando_a_res_190(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = client.get(f"{_base(empresa)}/pre-das/?ano=2027&mes=1")

    assert resposta.status_code == 409
    assert "190/2026" in resposta.json()["bloqueios"][0]["mensagem"]


def test_pre_das_com_competencia_invalida_responde_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    assert client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=13").status_code == 400
    assert client.get(f"{_base(empresa)}/pre-das/?ano=abc&mes=1").status_code == 400


def test_pre_das_de_empresa_de_outro_escritorio_responde_404(client, empresa, usuario_gestor_b):
    client.force_login(usuario_gestor_b)

    assert client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=6").status_code == 404


def test_cliente_nao_le_o_pre_das_nem_as_folhas(client, empresa, usuario_cliente_a):
    client.force_login(usuario_cliente_a)

    assert client.get(f"{_base(empresa)}/pre-das/?ano=2026&mes=6").status_code == 403
    assert client.get(f"{_base(empresa)}/folhas-fator-r/").status_code == 403
    assert client.get(f"{_base(empresa)}/atividades/").status_code == 403


# ---------------------------------------------------------------------------
# Atividades: cadastro com vigência, contrato, isolamento e permissão
# ---------------------------------------------------------------------------


def test_cadastrar_atividade_responde_201(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(client, f"{_base(empresa)}/atividades/nova/", _atividade_payload())

    assert resposta.status_code == 201
    assert resposta.json()["enquadramento"] == "anexo_iii"


def test_atividade_com_enquadramento_fora_do_catalogo_responde_400(
    client, empresa, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/atividades/nova/", _atividade_payload(enquadramento="anexo_i")
    )

    assert resposta.status_code == 400


def test_atividade_com_campo_fora_do_contrato_responde_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/atividades/nova/", _atividade_payload(aliquota="0.0808")
    )

    assert resposta.status_code == 400
    assert "aliquota" in str(resposta.json())


def test_padrao_sobreposta_responde_409(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    assert (
        _post(client, f"{_base(empresa)}/atividades/nova/", _atividade_payload()).status_code == 201
    )

    resposta = _post(
        client,
        f"{_base(empresa)}/atividades/nova/",
        _atividade_payload(inicio="2026-01-01", enquadramento="anexo_iv"),
    )

    assert resposta.status_code == 409


def test_alterar_vigencia_da_atividade_responde_200(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    criada = _post(client, f"{_base(empresa)}/atividades/nova/", _atividade_payload()).json()

    resposta = _patch(client, f"{_base(empresa)}/atividades/{criada['id']}/", {"fim": "2026-06-30"})

    assert resposta.status_code == 200
    assert resposta.json()["fim"] == "2026-06-30"


def test_excluir_atividade_em_uso_responde_409(client, empresa, usuario_gestor_a):
    from apps.fiscal import receita as servico_receita
    from apps.fiscal.models import AtividadeEmpresa

    atividade = AtividadeEmpresa.objects.create(
        empresa=empresa,
        descricao="Usada",
        enquadramento=EnquadramentoAtividade.ANEXO_III,
        inicio=date(2018, 1, 1),
        criada_por=usuario_gestor_a,
    )
    servico_receita.lancar_receita_informada(
        empresa,
        2026,
        5,
        "interno",
        "1000.00",
        "outras_receitas_atividade",
        "Motivo sintético.",
        SUPORTE_SINTETICO,
        usuario_gestor_a,
        atividade=atividade,
    )
    client.force_login(usuario_gestor_a)

    resposta = client.delete(f"{_base(empresa)}/atividades/{atividade.pk}/")

    assert resposta.status_code == 409


def test_atividade_de_outra_empresa_responde_404(client, empresa, empresa_a2, usuario_gestor_a):
    criada = servico.cadastrar_atividade(
        empresa_a2,
        {
            "descricao": "Da outra empresa",
            "codigo_subitem": "",
            "enquadramento": EnquadramentoAtividade.ANEXO_III,
            "inicio": date(2018, 1, 1),
            "fim": None,
            "padrao": False,
        },
        usuario_gestor_a,
    )
    client.force_login(usuario_gestor_a)

    assert (
        _patch(
            client, f"{_base(empresa)}/atividades/{criada.pk}/", {"fim": "2026-01-01"}
        ).status_code
        == 404
    )


def test_receita_informada_com_atividade_de_outra_empresa_responde_404(
    client, empresa, empresa_a2, usuario_gestor_a
):
    outra = servico.cadastrar_atividade(
        empresa_a2,
        {
            "descricao": "Da outra empresa",
            "codigo_subitem": "",
            "enquadramento": EnquadramentoAtividade.ANEXO_III,
            "inicio": date(2018, 1, 1),
            "fim": None,
            "padrao": False,
        },
        usuario_gestor_a,
    )
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/",
        {
            "ano": 2026,
            "mes": 5,
            "mercado": "interno",
            "valor": "1000.00",
            "origem": "outras_receitas_atividade",
            "motivo": "Motivo sintético.",
            "documento_suporte": SUPORTE_SINTETICO,
            "atividade": outra.pk,
        },
    )

    assert resposta.status_code == 404


def test_paralegal_nao_cadastra_atividade(client, empresa, usuario_paralegal_a):
    client.force_login(usuario_paralegal_a)

    assert (
        _post(client, f"{_base(empresa)}/atividades/nova/", _atividade_payload()).status_code == 403
    )


# ---------------------------------------------------------------------------
# Folha: lançar, confirmar, estornar; contrato, isolamento e permissão
# ---------------------------------------------------------------------------


def test_folha_lanca_confirma_e_estorna_com_os_codigos_certos(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    criada = _post(client, f"{_base(empresa)}/folhas-fator-r/nova/", _folha_payload())
    assert criada.status_code == 201
    folha_id = criada.json()["id"]
    assert criada.json()["estado"] == "rascunho"

    confirmada = _post(client, f"{_base(empresa)}/folhas-fator-r/{folha_id}/confirmar/")
    assert confirmada.status_code == 200
    assert confirmada.json()["estado"] == "confirmada"

    segunda_confirmacao = _post(client, f"{_base(empresa)}/folhas-fator-r/{folha_id}/confirmar/")
    assert segunda_confirmacao.status_code == 409

    estornada = _post(
        client,
        f"{_base(empresa)}/folhas-fator-r/{folha_id}/estornar/",
        {"motivo": "Erro de digitação."},
    )
    assert estornada.status_code == 200
    assert estornada.json()["estado"] == "estornada"


def test_folha_sem_motivo_no_estorno_responde_400(client, empresa, usuario_gestor_a):
    folha = folha_confirmada(empresa, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/folhas-fator-r/{folha.pk}/estornar/", {"motivo": " "}
    )

    assert resposta.status_code == 400


def test_folha_com_campo_fora_do_contrato_responde_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/folhas-fator-r/nova/", _folha_payload(estado="confirmada")
    )

    assert resposta.status_code == 400
    assert "estado" in str(resposta.json())


def test_folha_com_mais_de_duas_casas_responde_400(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/folhas-fator-r/nova/",
        _folha_payload(remuneracao_empregados_avulsos="1000.001"),
    )

    assert resposta.status_code == 400


def test_folha_de_outra_empresa_responde_404_ao_confirmar(
    client, empresa, empresa_a2, usuario_gestor_a
):
    folha = folha_confirmada(empresa_a2, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/folhas-fator-r/{folha.pk}/estornar/", {"motivo": "X"}
    )

    assert resposta.status_code == 404
    folha.refresh_from_db()
    assert folha.estado == "confirmada"


def test_listagem_de_folhas_filtra_por_ano_e_rejeita_ano_invalido(
    client, empresa, usuario_gestor_a
):
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [Decimal("1000")] * 12)
    client.force_login(usuario_gestor_a)

    lista = client.get(f"{_base(empresa)}/folhas-fator-r/?ano=2025")
    assert lista.status_code == 200
    assert {f["ano"] for f in lista.json()} == {2025}
    assert client.get(f"{_base(empresa)}/folhas-fator-r/?ano=x").status_code == 400


def test_paralegal_nao_lanca_folha(client, empresa, usuario_paralegal_a):
    client.force_login(usuario_paralegal_a)

    assert (
        _post(client, f"{_base(empresa)}/folhas-fator-r/nova/", _folha_payload()).status_code == 403
    )
    assert FolhaFatorR.objects.filter(empresa=empresa).count() == 0
