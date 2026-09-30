"""DL-055 (nível 1, isolamento): o papel CLIENTE não lê a carteira do escritório.

Contrato (plano DL-055, critérios 1-4; DE-020 §4): o CLIENTE recebe 403 em
TODA rota de leitura de empresa e de estabelecimento, pela API e pela tela,
sem nenhum dado de empresa no corpo e sem revelar se o id existe. Os outros
cinco papéis mantêm o comportamento anterior. A escrita que já era recusada ao
CLIENTE continua recusada.

Dados sintéticos: razões sociais e CNPJ fictícios, com marcas únicas para
procurar no corpo da resposta.
"""

import json
import re

import pytest
from django.contrib.auth import get_user_model
from django.urls import get_resolver, reverse

from apps.empresas.models import (
    Empresa,
    Estabelecimento,
    HistoricoRegimeTributario,
    RegimeTributario,
    TipoEstabelecimento,
)
from apps.empresas.permissoes import PAPEIS_QUE_LEEM_CARTEIRA
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
OUTROS_PAPEIS = [p for p in Papel if p != Papel.CLIENTE]

# Marcas que jamais podem voltar a um CLIENTE.
RAZAO = "Sigilo Alfa Comercio Ltda"
CNPJ = "11122233000183"
CNPJ_MASCARADO = "11.122.233/0001-83"
NOME_FILIAL = "Filial Sigilosa Beta"
CNPJ_FILIAL = "44455566000264"
RAZAO_OUTRO_ESCRITORIO = "Empresa De Outro Escritorio Gama"
SENSIVEIS = [
    RAZAO,
    CNPJ,
    CNPJ_MASCARADO,
    NOME_FILIAL,
    CNPJ_FILIAL,
    "Filial Sigilosa",
    RAZAO_OUTRO_ESCRITORIO,
]

ID_INEXISTENTE = 999_999


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL055", cnpj="11111111000111")
    outro = Escritorio.objects.create(nome="Outro DL055", cnpj="22222222000122")
    empresa = Empresa.objects.create(escritorio=escritorio, razao_social=RAZAO, cnpj=CNPJ)
    empresa_de_outro = Empresa.objects.create(
        escritorio=outro, razao_social=RAZAO_OUTRO_ESCRITORIO, cnpj="99988877000166"
    )
    Estabelecimento.objects.create(
        empresa=empresa, tipo=TipoEstabelecimento.FILIAL, nome=NOME_FILIAL, cnpj=CNPJ_FILIAL
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio="2024-01-01",
    )
    return {"escritorio": escritorio, "empresa": empresa, "empresa_de_outro": empresa_de_outro}


def _entrar(client, cenario, papel):
    usuario = get_user_model().objects.create_user(
        username=f"u-{papel}", email=f"{papel}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=cenario["escritorio"], papel=papel
    )
    assert client.login(username=usuario.username, password=SENHA)


def _corpo(resposta):
    return resposta.content.decode()


def _sem_token_csrf(resposta):
    """O corpo da tela muda a cada requisição SÓ pelo token CSRF do menu; a
    comparação "id existente x inexistente" precisa ignorá-lo."""
    return re.sub(r'name="csrfmiddlewaretoken" value="[^"]+"', "", _corpo(resposta))


def _sem_dado_de_empresa(resposta):
    corpo = _corpo(resposta)
    for marca in SENSIVEIS:
        assert marca not in corpo, f"{marca!r} vazou no corpo de {resposta.status_code}"


# ---------------------------------------------------------------------------
# As rotas de LEITURA do app. Cada uma devolve (url para id existente, url
# para id inexistente); `None` quando a rota não tem id.
# ---------------------------------------------------------------------------


def _rotas_de_api(cenario):
    e = cenario["empresa"].pk
    return {
        "api-lista": (reverse("empresas:api-lista"), None),
        "api-detalhe": (
            reverse("empresas:api-detalhe", args=[e]),
            reverse("empresas:api-detalhe", args=[ID_INEXISTENTE]),
        ),
        "api-estabelecimentos": (
            reverse("empresas:api-estabelecimentos", args=[e]),
            reverse("empresas:api-estabelecimentos", args=[ID_INEXISTENTE]),
        ),
        "api-regime-tributario": (
            reverse("empresas:api-regime-tributario", args=[e]),
            reverse("empresas:api-regime-tributario", args=[ID_INEXISTENTE]),
        ),
    }


def _rotas_de_tela(cenario):
    e = cenario["empresa"].pk
    return {
        "lista": (reverse("empresas:lista"), None),
        # Tela que redireciona para a empresa escolhida: era um oráculo de
        # existência (302 x 404) e precisa responder igual ao CLIENTE.
        "trocar-secao": (
            reverse("empresas:trocar-secao") + f"?empresa_id={e}",
            reverse("empresas:trocar-secao") + f"?empresa_id={ID_INEXISTENTE}",
        ),
    }


# Rotas do namespace que NÃO são leitura: escrita pura ou formulário que já
# recusa o CLIENTE. Precisam estar aqui para o teste de descoberta abaixo.
_ROTAS_DE_ESCRITA = {"criar", "api-regime-tributario-detalhe"}


def test_toda_rota_do_app_empresas_esta_classificada(cenario):
    """Rota nova em `apps.empresas.urls` reprova aqui até alguém decidir se é
    leitura (entra na matriz) ou escrita (entra em `_ROTAS_DE_ESCRITA`).

    Derivado do urlconf, não de uma lista de teste: é o que impede a DL-055 de
    valer só para "as rotas que lembramos" (a lição da DE-020 §4).
    """
    _prefixo, resolvedor = get_resolver().namespace_dict["empresas"]
    nomes = {padrao.name for padrao in resolvedor.url_patterns}
    cobertos = set(_rotas_de_api(cenario)) | set(_rotas_de_tela(cenario)) | _ROTAS_DE_ESCRITA
    assert nomes == cobertos


# ---------------------------------------------------------------------------
# Critério 1 e 3: CLIENTE -> 403, sem dado, igual para id existente e não.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("metodo", ["get", "head", "options"])
def test_cliente_recebe_403_em_toda_leitura_da_api(client, cenario, metodo):
    _entrar(client, cenario, Papel.CLIENTE)
    for nome, (url_existente, url_inexistente) in _rotas_de_api(cenario).items():
        resposta = getattr(client, metodo)(url_existente)
        assert resposta.status_code == 403, f"{nome} {metodo}"
        _sem_dado_de_empresa(resposta)
        if url_inexistente is not None:
            inexistente = getattr(client, metodo)(url_inexistente)
            # Critério 3: nem status nem corpo distinguem existente de inexistente.
            assert inexistente.status_code == 403, f"{nome} {metodo} (inexistente)"
            assert inexistente.content == resposta.content, f"{nome} {metodo}"


def test_cliente_recebe_403_nas_telas_de_leitura(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    for nome, (url_existente, url_inexistente) in _rotas_de_tela(cenario).items():
        resposta = client.get(url_existente)
        assert resposta.status_code == 403, nome
        _sem_dado_de_empresa(resposta)
        if url_inexistente is not None:
            inexistente = client.get(url_inexistente)
            assert inexistente.status_code == 403, f"{nome} (inexistente)"
            assert _sem_token_csrf(inexistente) == _sem_token_csrf(resposta), nome


def test_cliente_na_troca_de_secao_nao_distingue_id_valido_de_malformado(client, cenario):
    """O 403 vem antes de interpretar `empresa_id`: ausente, malformado,
    existente, de outro escritório e inexistente dão a MESMA resposta."""
    _entrar(client, cenario, Papel.CLIENTE)
    base = reverse("empresas:trocar-secao")
    alvos = [
        "",
        "?empresa_id=abc",
        f"?empresa_id={cenario['empresa'].pk}",
        f"?empresa_id={cenario['empresa_de_outro'].pk}",
        f"?empresa_id={ID_INEXISTENTE}",
        f"?empresa_id={cenario['empresa'].pk}&secao=balancete",
    ]
    respostas = [client.get(base + alvo) for alvo in alvos]
    assert {r.status_code for r in respostas} == {403}
    assert len({_sem_token_csrf(r) for r in respostas}) == 1
    _sem_dado_de_empresa(respostas[0])


def test_cliente_nao_distingue_empresa_de_outro_escritorio(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    propria = client.get(reverse("empresas:api-detalhe", args=[cenario["empresa"].pk]))
    alheia = client.get(reverse("empresas:api-detalhe", args=[cenario["empresa_de_outro"].pk]))
    assert propria.status_code == alheia.status_code == 403
    assert propria.content == alheia.content


def test_filtros_e_buscas_da_lista_tambem_dao_403_ao_cliente(client, cenario):
    """Querystring de filtro/busca não abre exceção: a recusa não depende dos
    parâmetros (`?search=`, `?cnpj=`, `?q=`, paginação)."""
    _entrar(client, cenario, Papel.CLIENTE)
    for rota in ("empresas:api-lista", "empresas:lista"):
        for consulta in (
            "?search=Sigilo",
            f"?cnpj={CNPJ}",
            "?q=Alfa&ordering=razao_social",
            "?page=1&page_size=100",
            "?ativo=true",
        ):
            resposta = client.get(reverse(rota) + consulta)
            assert resposta.status_code == 403, f"{rota}{consulta}"
            _sem_dado_de_empresa(resposta)


def test_cliente_sem_sessao_continua_nao_autenticado(client, cenario):
    """Controle: a recusa por papel não mascara a recusa por falta de login."""
    resposta = client.get(reverse("empresas:api-lista"))
    assert resposta.status_code in (401, 403)
    _sem_dado_de_empresa(resposta)


# ---------------------------------------------------------------------------
# Critério 2: os outros cinco papéis ficam exatamente como estavam.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", OUTROS_PAPEIS)
def test_demais_papeis_leem_a_api_como_antes(client, cenario, papel):
    _entrar(client, cenario, papel)
    rotas = _rotas_de_api(cenario)

    lista = client.get(rotas["api-lista"][0])
    assert lista.status_code == 200
    assert [i["razao_social"] for i in lista.json()] == [RAZAO]
    assert lista.json()[0]["cnpj"] == CNPJ

    detalhe = client.get(rotas["api-detalhe"][0])
    assert detalhe.status_code == 200
    assert detalhe.json()["razao_social"] == RAZAO

    estabelecimentos = client.get(rotas["api-estabelecimentos"][0])
    assert estabelecimentos.status_code == 200
    assert [i["nome"] for i in estabelecimentos.json()] == [NOME_FILIAL]

    regimes = client.get(rotas["api-regime-tributario"][0])
    assert regimes.status_code == 200
    assert len(regimes.json()) == 1

    # Id inexistente continua 404 para quem lê (o 403 é só do CLIENTE).
    for nome in ("api-detalhe", "api-estabelecimentos", "api-regime-tributario"):
        assert client.get(rotas[nome][1]).status_code == 404, nome
    # Empresa de OUTRO escritório continua 404, não 403 nem 200.
    alheia = reverse("empresas:api-detalhe", args=[cenario["empresa_de_outro"].pk])
    assert client.get(alheia).status_code == 404

    assert client.options(rotas["api-lista"][0]).status_code == 200
    assert client.head(rotas["api-lista"][0]).status_code == 200


@pytest.mark.parametrize("papel", OUTROS_PAPEIS)
def test_demais_papeis_leem_as_telas_como_antes(client, cenario, papel):
    _entrar(client, cenario, papel)
    rotas = _rotas_de_tela(cenario)

    lista = client.get(rotas["lista"][0])
    assert lista.status_code == 200
    assert RAZAO in _corpo(lista)

    troca = client.get(rotas["trocar-secao"][0])
    assert troca.status_code == 302
    assert str(cenario["empresa"].pk) in troca["Location"]
    assert client.get(rotas["trocar-secao"][1]).status_code == 404
    assert client.get(reverse("empresas:trocar-secao")).status_code == 404


def test_a_regra_do_servidor_e_a_tupla_unica_de_papeis():
    """Os cinco papéis que leem são exatamente os da tupla; o CLIENTE fica de
    fora. Um papel novo nasce sem ler a carteira (lista de permitidos)."""
    assert set(PAPEIS_QUE_LEEM_CARTEIRA) == set(OUTROS_PAPEIS)
    assert Papel.CLIENTE not in PAPEIS_QUE_LEEM_CARTEIRA


# ---------------------------------------------------------------------------
# Critério 4: escrita já recusada continua recusada — e nada é gravado.
# ---------------------------------------------------------------------------


def test_escrita_continua_recusada_ao_cliente_e_nada_e_gravado(client, cenario):
    _entrar(client, cenario, Papel.CLIENTE)
    empresa = cenario["empresa"]
    antes = (
        Empresa.objects.count(),
        Estabelecimento.objects.count(),
        HistoricoRegimeTributario.objects.count(),
    )
    registro = HistoricoRegimeTributario.objects.get(empresa=empresa)

    def enviar(metodo, url, corpo):
        return getattr(client, metodo)(url, data=json.dumps(corpo), content_type="application/json")

    respostas = {
        "POST lista": enviar(
            "post",
            reverse("empresas:api-lista"),
            {"razao_social": "Nova Ltda", "cnpj": "55566677000188"},
        ),
        "PUT detalhe": enviar(
            "put",
            reverse("empresas:api-detalhe", args=[empresa.pk]),
            {"razao_social": "Trocada Ltda", "cnpj": CNPJ},
        ),
        "PATCH detalhe": enviar(
            "patch",
            reverse("empresas:api-detalhe", args=[empresa.pk]),
            {"razao_social": "Trocada Ltda"},
        ),
        "POST estabelecimento": enviar(
            "post",
            reverse("empresas:api-estabelecimentos", args=[empresa.pk]),
            {"tipo": "filial", "nome": "Nova Filial", "cnpj": "77788899000100"},
        ),
        "POST regime": enviar(
            "post",
            reverse("empresas:api-regime-tributario", args=[empresa.pk]),
            {"regime": "lucro_real", "vigencia_inicio": "2025-01-01"},
        ),
        "DELETE regime": client.delete(
            reverse("empresas:api-regime-tributario-detalhe", args=[empresa.pk, registro.pk])
        ),
        "GET criar": client.get(reverse("empresas:criar")),
        "POST criar": client.post(
            reverse("empresas:criar"), {"razao_social": "Nova Ltda", "cnpj": "55566677000188"}
        ),
    }
    for nome, resposta in respostas.items():
        assert resposta.status_code == 403, nome
        _sem_dado_de_empresa(resposta)

    empresa.refresh_from_db()
    assert empresa.razao_social == RAZAO
    assert (
        Empresa.objects.count(),
        Estabelecimento.objects.count(),
        HistoricoRegimeTributario.objects.count(),
    ) == antes


def test_escrita_autorizada_continua_funcionando_para_o_gestor(client, cenario):
    """Controle: o novo `PodeLerCarteira` não atrapalha quem escreve."""
    _entrar(client, cenario, Papel.GESTOR)
    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps({"razao_social": "Nova Ltda", "cnpj": "11222333000181"}),
        content_type="application/json",
    )
    assert resposta.status_code == 201
