"""DL-078, critério 8: API das NFS-e tomadas — permissões no servidor e isolamento.

- Consultar (lista, ISS retido, retenções federais): quem pode consultar documentos. PARALEGAL lê;
  CLIENTE não.
- Escriturar, estornar e informar data de pagamento: quem escritura (ADMINISTRADOR, GESTOR,
  ANALISTA, FINANCEIRO). PARALEGAL e CLIENTE não.
- Empresa ou escrituração de outro escritório: 404. Campo não contratado: 400.

Cliente HTTP real; autorização vem do papel do vínculo com o escritório ativo (middleware).
"""

import json

import pytest
from django.contrib.auth import get_user_model

from apps.fiscal import tomadas as servico
from apps.fiscal.models import EscrituracaoTomada, EstadoEscrituracao
from apps.fiscal.tests.suporte_tomada_dl078 import (
    T1,
    receber_tomada,
    tomada_efetivada,
    vinculo_tomador,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("relogio_do_teste")]


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _url_lista(empresa, ano=2026, mes=10):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/?ano={ano}&mes={mes}"


def _url_iss(empresa, ano=2026, mes=10):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/iss-retido/?ano={ano}&mes={mes}"


def _url_federais(empresa, ano=2026, mes=10):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/retencoes-federais/?ano={ano}&mes={mes}"


def _url_rascunho(empresa, vinculo):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/{vinculo.pk}/rascunho/"


def _url_efetivar(empresa, vinculo):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/{vinculo.pk}/efetivar/"


def _url_estornar(empresa, escrituracao):
    return f"/fiscal/api/empresas/{empresa.pk}/tomadas/escrituracoes/{escrituracao.pk}/estornar/"


def _url_data_pagamento(empresa, escrituracao):
    return (
        f"/fiscal/api/empresas/{empresa.pk}/tomadas/escrituracoes/{escrituracao.pk}/data-pagamento/"
    )


@pytest.fixture
def nota(escritorio_a, usuario_gestor_a, empresa_a2):
    """Nota tomada de Palmas, retida pelo tomador (T1), recebida pelo pipeline real."""
    return receber_tomada(
        escritorio_a,
        usuario_gestor_a,
        8801,
        tomador_documento=empresa_a2.cnpj,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
    )


@pytest.fixture
def paralegal(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-tomadas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-tomadas")


# ---------------------------------------------------------------------------
# Permissões: consultar e escriturar
# ---------------------------------------------------------------------------


def test_cliente_nao_consulta_nem_escritura_tomadas(
    client, escritorio_a, empresa_a2, usuario_cliente_a, nota
):
    _logar(client, usuario_cliente_a)
    vinculo = vinculo_tomador(nota, empresa_a2)

    assert client.get(_url_lista(empresa_a2)).status_code == 403
    assert client.get(_url_iss(empresa_a2)).status_code == 403
    assert client.get(_url_federais(empresa_a2)).status_code == 403
    assert _post(client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1}).status_code == 403
    assert EscrituracaoTomada.objects.count() == 0


def test_paralegal_le_as_tomadas_mas_nao_escritura(
    client, escritorio_a, empresa_a2, paralegal, nota
):
    _logar(client, paralegal)
    vinculo = vinculo_tomador(nota, empresa_a2)

    assert client.get(_url_lista(empresa_a2)).status_code == 200
    assert client.get(_url_iss(empresa_a2)).status_code == 200
    assert client.get(_url_federais(empresa_a2)).status_code == 200
    assert _post(client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1}).status_code == 403
    assert _post(client, _url_rascunho(empresa_a2, vinculo), {"natureza": T1}).status_code == 403
    assert EscrituracaoTomada.objects.count() == 0


def test_gestor_efetiva_estorna_e_informa_a_data_de_pagamento_pela_api(
    client, escritorio_a, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)
    vinculo = vinculo_tomador(nota, empresa_a2)

    criada = _post(client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1})
    assert criada.status_code == 201
    assert criada.json()["estado"] == EstadoEscrituracao.EFETIVADA
    escrituracao_id = criada.json()["id"]

    repetida = _post(client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1})
    assert repetida.status_code == 200  # idempotente: mesma natureza, nada novo

    escrituracao = EscrituracaoTomada.objects.get(pk=escrituracao_id)
    pagamento = _post(
        client,
        _url_data_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "2026-10-30", "motivo": "Comprovante sintético"},
    )
    assert pagamento.status_code == 201
    assert pagamento.json()["data_pagamento"] == "2026-10-30"

    iss = client.get(_url_iss(empresa_a2)).json()
    assert iss["grupos"][0]["municipio"] == "1721000"
    assert iss["grupos"][0]["total"] == "50.00"
    assert iss["grupos"][0]["vencimento"] == "2026-11-15"

    estorno = _post(client, _url_estornar(empresa_a2, escrituracao), {"motivo": "Teste da API"})
    assert estorno.status_code == 200
    assert estorno.json()["estado"] == EstadoEscrituracao.ESTORNADA


def test_rascunho_pela_api_nao_conta_no_total(
    client, escritorio_a, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)
    vinculo = vinculo_tomador(nota, empresa_a2)

    rascunho = _post(client, _url_rascunho(empresa_a2, vinculo), {"natureza": T1})

    assert rascunho.status_code == 200
    assert rascunho.json()["estado"] == EstadoEscrituracao.RASCUNHO
    assert client.get(_url_iss(empresa_a2)).json()["grupos"] == []


# ---------------------------------------------------------------------------
# Isolamento e contrato
# ---------------------------------------------------------------------------


def test_outro_escritorio_recebe_404_na_empresa_e_na_escrituracao(
    client, empresa_a2, gestor_b, usuario_gestor_a, nota, escritorio_a
):
    _logar(client, gestor_b)
    vinculo = vinculo_tomador(nota, empresa_a2)
    escrituracao = servico.efetivar_escrituracao_tomada(vinculo, T1, usuario_gestor_a)

    assert client.get(_url_lista(empresa_a2)).status_code == 404
    assert client.get(_url_iss(empresa_a2)).status_code == 404
    assert client.get(_url_federais(empresa_a2)).status_code == 404
    assert _post(client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1}).status_code == 404
    assert (
        _post(client, _url_estornar(empresa_a2, escrituracao), {"motivo": "x"}).status_code == 404
    )
    assert (
        _post(
            client,
            _url_data_pagamento(empresa_a2, escrituracao),
            {"data_pagamento": "2026-10-30", "motivo": "x"},
        ).status_code
        == 404
    )
    assert EstadoEscrituracao.EFETIVADA == EscrituracaoTomada.objects.get(pk=escrituracao.pk).estado


def test_escrituracao_de_outra_empresa_do_mesmo_escritorio_recebe_404(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao_tomada(
        vinculo_tomador(nota, empresa_a2), T1, usuario_gestor_a
    )

    # Mesmo escritório, empresa errada na URL: a escrituração é buscada DENTRO da empresa.
    assert _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": "x"}).status_code == 404


def test_campo_nao_contratado_e_recusado_com_400(client, empresa_a2, usuario_gestor_a, nota):
    _logar(client, usuario_gestor_a)
    vinculo = vinculo_tomador(nota, empresa_a2)

    resposta = _post(
        client, _url_efetivar(empresa_a2, vinculo), {"natureza": T1, "valor_servico": "1.00"}
    )

    assert resposta.status_code == 400
    assert "valor_servico" in json.dumps(resposta.json())


def test_natureza_fora_do_catalogo_e_nota_incompativel_sao_400(
    client, empresa_a2, usuario_gestor_a, nota
):
    _logar(client, usuario_gestor_a)
    vinculo = vinculo_tomador(nota, empresa_a2)

    assert _post(client, _url_rascunho(empresa_a2, vinculo), {"natureza": "T4"}).status_code == 400
    assert EscrituracaoTomada.objects.count() == 0


def test_data_de_pagamento_com_formato_errado_e_400(client, empresa_a2, usuario_gestor_a, nota):
    _logar(client, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao_tomada(
        vinculo_tomador(nota, empresa_a2), T1, usuario_gestor_a
    )

    resposta = _post(
        client,
        _url_data_pagamento(empresa_a2, escrituracao),
        {"data_pagamento": "30/10/2026", "motivo": "x"},
    )

    assert resposta.status_code == 400
    escrituracao.refresh_from_db()
    assert escrituracao.data_pagamento is None


def test_estorno_sem_motivo_e_400(client, empresa_a2, usuario_gestor_a, nota):
    _logar(client, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao_tomada(
        vinculo_tomador(nota, empresa_a2), T1, usuario_gestor_a
    )

    assert (
        _post(client, _url_estornar(empresa_a2, escrituracao), {"motivo": "  "}).status_code == 400
    )
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA


def test_retencoes_federais_pela_api_mostram_pendente_sem_data(
    client, escritorio_a, empresa_a2, usuario_gestor_a
):
    tomada_efetivada(
        escritorio_a,
        empresa_a2,
        usuario_gestor_a,
        8810,
        T1,
        tp_ret_issqn="2",
        v_iss_qn="50.00",
        v_liq="950.00",
        c_loc_incid="1721000",
        d_compet="2026-10-05",
        v_ret_csll="20.00",
        tp_ret_pis_cofins="3",
    )
    _logar(client, usuario_gestor_a)

    federais = client.get(_url_federais(empresa_a2)).json()

    assert federais["csrf"]["total"] is None  # sem data de pagamento: nada no agrupamento por data
    assert len(federais["pendentes_de_pagamento"]) == 1
    assert federais["inss"]["total"] is None  # nenhuma vRetCP: ausência, não zero
