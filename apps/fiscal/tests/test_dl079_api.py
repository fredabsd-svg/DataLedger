"""DL-079, critério 9 e a parte de API: permissões no servidor, isolamento e entrada estranha.

- Ler (GET): ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO e PARALEGAL. CLIENTE: 403.
- Escrever (POST): quem escritura (ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO).
  PARALEGAL e CLIENTE: 403.
- Empresa de outro escritório: 404. Registro de OUTRA empresa do mesmo escritório, em URL
  de empresa diferente: 404.
- Entrada estranha (ano, trimestre, campo extra, float): 400, nunca 500.
Cliente HTTP real; a autorização vem do papel do vínculo com o escritório ativo (middleware).
"""

import json
from datetime import date

import pytest
from django.contrib.auth import get_user_model

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fim_de_2026(monkeypatch):
    """O controle do limite só mostra o fechamento com o 4º trimestre iniciado (A1). Fixa a data
    para que o teste não dependa do dia em que roda."""
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))


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


def _json(client, metodo, url, corpo=None):
    if metodo == "get":
        return client.get(url)
    return client.post(url, data=json.dumps(corpo or {}), content_type="application/json")


@pytest.fixture
def presumido_api(empresa_a, usuario_gestor_a, escritorio_a):
    """Empresa de Lucro Presumido em 2026, com critério e atividade padrão (comércio)."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    atividade = servico.criar_atividade(
        empresa_a,
        {
            "atividade": tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA,
            "inicio": date(2026, 1, 1),
            "padrao": True,
        },
        usuario_gestor_a,
    )
    return {"empresa": empresa_a, "atividade": atividade}


@pytest.fixture
def paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-presumido-a")


@pytest.fixture
def financeiro_a(escritorio_a):
    return _usuario(escritorio_a, Papel.FINANCEIRO, "financeiro-presumido-a")


def _url(empresa, sufixo):
    return f"/fiscal/api/empresas/{empresa.pk}/presumido/{sufixo}"


# ---------------------------------------------------------------------------
# Permissões
# ---------------------------------------------------------------------------


def test_gestor_le_e_escreve_a_apuracao_do_presumido(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    resposta = _json(
        client, "get", _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
    )
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["ano"] == 2026 and corpo["trimestre"] == 1
    assert corpo["situacao"] == "parcial"  # sem declaração de integrais
    assert corpo["declaracao_integrais"]["valida"] is False


def test_paralegal_le_mas_nao_escreve(client, presumido_api, paralegal_a):
    _logar(client, paralegal_a)
    assert (
        _json(
            client, "get", _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
        ).status_code
        == 200
    )
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "receitas/"),
        {
            "ano": 2026,
            "trimestre": 1,
            "tipo": "integral",
            "valor": "10.00",
            "descricao": "x",
            "suporte": "y",
        },
    )
    assert resposta.status_code == 403


def test_cliente_recebe_403_em_leitura_e_escrita(client, presumido_api, usuario_cliente_a):
    _logar(client, usuario_cliente_a)
    assert (
        _json(
            client, "get", _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
        ).status_code
        == 403
    )
    assert _json(client, "get", _url(presumido_api["empresa"], "atividades/")).status_code == 403
    assert (
        _json(
            client,
            "post",
            _url(presumido_api["empresa"], "criterio/"),
            {"ano": 2027, "criterio": "competencia"},
        ).status_code
        == 403
    )


def test_financeiro_pode_escriturar_como_quem_escritura_a_contabilidade(
    client, presumido_api, financeiro_a
):
    _logar(client, financeiro_a)
    resposta = _json(
        client, "post", _url(presumido_api["empresa"], "integrais/"), {"ano": 2026, "trimestre": 1}
    )
    assert resposta.status_code == 201


def test_empresa_de_outro_escritorio_responde_404(client, presumido_api, usuario_gestor_b_fixture):
    _logar(client, usuario_gestor_b_fixture)
    assert (
        _json(
            client, "get", _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
        ).status_code
        == 404
    )
    assert (
        _json(
            client,
            "post",
            _url(presumido_api["empresa"], "atividades/"),
            {"atividade": "servicos_gerais", "inicio": "2026-01-01"},
        ).status_code
        == 404
    )


@pytest.fixture
def usuario_gestor_b_fixture(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-presumido-b")


def test_registro_de_outra_empresa_do_mesmo_escritorio_responde_404(
    client, presumido_api, usuario_gestor_a, escritorio_a
):
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra cliente A Ltda", cnpj="77888999000155"
    )
    atividade_da_outra = servico.criar_atividade(
        outra,
        {"atividade": "servicos_gerais", "inicio": date(2026, 1, 1)},
        usuario_gestor_a,
    )
    _logar(client, usuario_gestor_a)
    # A atividade pertence à `outra`, mas a URL é da empresa do fixture: 404.
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], f"atividades/{atividade_da_outra.pk}/encerrar/"),
        {"fim": "2026-12-31"},
    )
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Entrada estranha: 400, nunca 500
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sufixo",
    [
        "apuracao/?ano=abc&trimestre=1",
        "apuracao/?ano=2026&trimestre=9",
        "apuracao/?ano=1999&trimestre=1",
        "apuracao/?ano=2026",
        "retencoes/?ano=2026&trimestre=0",
        "limite/?ano=2026&tributo=pis",
        "limite/?ano=2026",
        "criterio/?ano=abc",
    ],
)
def test_consulta_com_ano_ou_trimestre_estranho_responde_400(
    client, presumido_api, usuario_gestor_a, sufixo
):
    _logar(client, usuario_gestor_a)
    assert _json(client, "get", _url(presumido_api["empresa"], sufixo)).status_code == 400


def test_post_com_campo_nao_contratado_responde_400_nomeando_a_chave(
    client, presumido_api, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "receitas/"),
        {
            "ano": 2026,
            "trimestre": 1,
            "tipo": "integral",
            "valor": "10.00",
            "descricao": "x",
            "suporte": "y",
            "campo_inventado": 1,
        },
    )
    assert resposta.status_code == 400
    assert "campo_inventado" in resposta.content.decode()


def test_valor_em_json_numerico_e_recusado_com_400(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "receitas/"),
        {
            "ano": 2026,
            "trimestre": 1,
            "tipo": "integral",
            "valor": 10.5,
            "descricao": "x",
            "suporte": "y",
        },
    )
    assert resposta.status_code == 400


def test_corpo_que_nao_e_objeto_responde_400(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    resposta = client.post(
        _url(presumido_api["empresa"], "criterio/"), data="[1, 2]", content_type="application/json"
    )
    assert resposta.status_code == 400


def test_criterio_invalido_responde_400(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "criterio/"),
        {"ano": 2027, "criterio": "lucro_real_inventado"},
    )
    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# Fluxo feliz e erros de estado (409)
# ---------------------------------------------------------------------------


def test_receita_criada_depois_estornada_e_estorno_repetido_e_409(
    client, presumido_api, usuario_gestor_a
):
    _logar(client, usuario_gestor_a)
    criada = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "receitas/"),
        {
            "ano": 2026,
            "trimestre": 1,
            "tipo": "presuncao",
            "atividade_id": presumido_api["atividade"].pk,
            "valor": "1500.00",
            "descricao": "Serviço informado",
            "suporte": "NF 123",
        },
    )
    assert criada.status_code == 201
    receita_id = criada.json()["id"]
    assert criada.json()["valor"] == "1500.00"
    primeiro = _json(
        client,
        "post",
        _url(presumido_api["empresa"], f"receitas/{receita_id}/estornar/"),
        {"motivo": "lançada em duplicidade"},
    )
    assert primeiro.status_code == 200 and primeiro.json()["estado"] == "estornada"
    segundo = _json(
        client,
        "post",
        _url(presumido_api["empresa"], f"receitas/{receita_id}/estornar/"),
        {"motivo": "de novo"},
    )
    assert segundo.status_code == 409


def test_confirmacao_de_retencao_de_nota_de_outra_empresa_responde_404(
    client, presumido_api, usuario_gestor_a, escritorio_a
):
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra cliente B Ltda", cnpj="77888999000155"
    )
    escrituracao = nota_efetivada(
        escritorio_a,
        outra,
        usuario_gestor_a,
        sufixo=601,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_irrf="10.00",
        prestador="77888999000155",
    )
    _logar(client, usuario_gestor_a)
    resposta = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "retencoes/"),
        {"escrituracao_id": escrituracao.pk, "irrf_confirmado": "10.00"},
    )
    assert resposta.status_code == 404


def test_retencoes_do_trimestre_mostram_proposta_e_confirmacao(
    client, presumido_api, usuario_gestor_a, escritorio_a
):
    escrituracao = nota_efetivada(
        escritorio_a,
        presumido_api["empresa"],
        usuario_gestor_a,
        sufixo=602,
        # DL-084 (HI-103): 465,00 é 4,65% de 10.000,00. Com 20.000,00 a nota não confere com a regra
        # e cairia em "a classificar". A expectativa abaixo (100,00) não muda.
        v_serv="10000.00",
        d_compet="2026-01-10",
        ret_irrf="300.00",
        ret_csll="465.00",
        tp_ret="3",
    )
    _logar(client, usuario_gestor_a)
    antes = _json(
        client, "get", _url(presumido_api["empresa"], "retencoes/?ano=2026&trimestre=1")
    ).json()
    linha = antes["retencoes"][0]
    assert linha["escrituracao_id"] == escrituracao.pk
    assert linha["irrf_proposto"] == "300.00"
    assert linha["csll_situacao"] == "estimada"
    assert linha["csll_proposta"] == "100.00"
    assert linha["irrf_confirmado"] is None
    confirmada = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "retencoes/"),
        {"escrituracao_id": escrituracao.pk, "irrf_confirmado": "300.00"},
    )
    assert confirmada.status_code == 201
    depois = _json(
        client, "get", _url(presumido_api["empresa"], "retencoes/?ano=2026&trimestre=1")
    ).json()
    assert depois["retencoes"][0]["irrf_confirmado"] == "300.00"


def test_medida_cadastrada_e_revogada_pela_api(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    cadastro = _json(
        client,
        "post",
        _url(presumido_api["empresa"], "medidas/"),
        {
            "tributo": "ambos",
            "ano_inicial": 2026,
            "trimestre_inicial": 1,
            "numero_processo": "processo-ficticio-1",
            "orgao": "Vara fictícia",
            "data_decisao": "2026-03-01",
            "suporte": "decisão sintética",
        },
    )
    assert cadastro.status_code == 201
    medida_id = cadastro.json()["id"]
    revogada = _json(
        client,
        "post",
        _url(presumido_api["empresa"], f"medidas/{medida_id}/revogar/"),
        {"motivo": "decisão cassada"},
    )
    assert revogada.status_code == 200 and revogada.json()["ativa"] is False
    assert (
        _json(
            client,
            "post",
            _url(presumido_api["empresa"], f"medidas/{medida_id}/revogar/"),
            {"motivo": "de novo"},
        ).status_code
        == 409
    )


def test_limite_do_ano_responde_linhas_e_fechamento(client, presumido_api, usuario_gestor_a):
    _logar(client, usuario_gestor_a)
    resposta = _json(client, "get", _url(presumido_api["empresa"], "limite/?ano=2026&tributo=csll"))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["tributo"] == "csll"
    assert len(corpo["linhas"]) == 4
    assert corpo["primeiro_trimestre"] == 2  # CSLL começa em 01/04/2026


def test_apuracao_expoe_tributos_com_as_tres_colunas_e_strings_decimais(
    client, presumido_api, usuario_gestor_a, escritorio_a
):
    nota_efetivada(
        escritorio_a,
        presumido_api["empresa"],
        usuario_gestor_a,
        sufixo=603,
        v_serv="100000.00",
        d_compet="2026-01-10",
    )
    servico.declarar_receitas_integrais(presumido_api["empresa"], 2026, 1, "", usuario_gestor_a)
    _logar(client, usuario_gestor_a)
    corpo = _json(
        client, "get", _url(presumido_api["empresa"], "apuracao/?ano=2026&trimestre=1")
    ).json()
    assert corpo["situacao"] == "completa"
    irpj = corpo["irpj"]
    assert irpj["imposto_sem_lc224"] == "1200.00"  # 8.000 × 15%: a base do exemplo, sem acréscimo
    assert irpj["parcela_lc224"] == "0.00"
    assert irpj["quotas"]["quota_unica"][0]["valor"] == "1200.00"
    assert isinstance(irpj["base_sem_lc224"], str)


ROTAS_DO_PRESUMIDO = [
    ("get", "atividades/"),
    ("post", "atividades/"),
    ("post", "atividades/1/encerrar/"),
    ("get", "criterio/?ano=2026"),
    ("post", "criterio/"),
    ("get", "receitas/?ano=2026&trimestre=1"),
    ("post", "receitas/"),
    ("post", "receitas/1/estornar/"),
    ("post", "integrais/"),
    ("get", "retencoes/?ano=2026&trimestre=1"),
    ("post", "retencoes/"),
    ("get", "medidas/"),
    ("post", "medidas/"),
    ("post", "medidas/1/revogar/"),
    ("get", "apuracao/?ano=2026&trimestre=1"),
    ("get", "limite/?ano=2026&tributo=irpj"),
]


@pytest.mark.parametrize(("metodo", "sufixo"), ROTAS_DO_PRESUMIDO)
def test_cliente_recebe_403_em_toda_rota_do_presumido(
    client, presumido_api, usuario_cliente_a, metodo, sufixo
):
    # A permissão é verificada antes do corpo da rota: 403 vem mesmo com corpo inválido.
    _logar(client, usuario_cliente_a)
    assert _json(client, metodo, _url(presumido_api["empresa"], sufixo)).status_code == 403


@pytest.mark.parametrize(("metodo", "sufixo"), ROTAS_DO_PRESUMIDO)
def test_paralegal_so_le_em_toda_rota_do_presumido(
    client, presumido_api, paralegal_a, metodo, sufixo
):
    _logar(client, paralegal_a)
    resposta = _json(client, metodo, _url(presumido_api["empresa"], sufixo))
    if metodo == "get":
        assert resposta.status_code != 403
    else:
        assert resposta.status_code == 403


@pytest.mark.parametrize(("metodo", "sufixo"), [r for r in ROTAS_DO_PRESUMIDO if r[0] == "post"])
def test_gestor_passa_da_permissao_em_toda_rota_de_escrita(
    client, presumido_api, usuario_gestor_a, metodo, sufixo
):
    # Chega ao corpo da rota: 400 (corpo vazio) ou 404/409 de registro, nunca 403.
    _logar(client, usuario_gestor_a)
    assert _json(client, metodo, _url(presumido_api["empresa"], sufixo)).status_code != 403
