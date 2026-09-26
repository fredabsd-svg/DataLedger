"""DL-044 (3ª iteração — retorno do Fred: "Início continua 60% vazio").

`apps.tenancy.views._indicadores_do_painel` (faixa de números do topo) e
`apps.tenancy.views._empresas_da_carteira` (tabela "Empresas da carteira")
são consultas NOVAS de apresentação, autorizadas pelo arquiteto-senior sob
duas condições explícitas: sempre filtradas pelo escritório ATIVO, e com
teste de isolamento e número de consultas CONSTANTE. Este arquivo prova as
duas — `test_dl042_fila_de_atencao.py` já cobre a fila de atenção em si e
o teto de consultas do painel inteiro (que esta etapa ajustou); aqui o foco
é só o que esta iteração acrescentou.

Duas garantias:

1. Isolamento — nenhuma empresa/indicador de um escritório aparece na
   "Empresas da carteira" nem soma na faixa de indicadores de outro.
2. Número de consultas CONSTANTE — a mesma quantidade de consultas com
   UMA empresa na carteira ou com VÁRIAS (a garantia real de que não há
   N+1 por empresa, não um número cravado).
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _empresa(escritorio, cnpj, razao_social):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social=razao_social,
        cnpj=cnpj,
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )


# ---------------------------------------------------------------------------
# 1. Isolamento entre escritórios
# ---------------------------------------------------------------------------


def test_empresas_da_carteira_isola_por_escritorio(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório Carteira A", cnpj="11222333000181")
    escritorio_b = Escritorio.objects.create(nome="Escritório Carteira B", cnpj="99888777000162")
    _empresa(escritorio_a, "22444666000177", "Empresa Exclusiva da Carteira A Ltda")
    _empresa(escritorio_b, "33555777000188", "Empresa Exclusiva da Carteira B Ltda")
    _usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-carteira-a")

    assert client.login(username="gestor-carteira-a", password="senha-forte-123")
    html = client.get(reverse("tenancy:painel")).content.decode()

    assert "Empresa Exclusiva da Carteira A Ltda" in html
    assert "Empresa Exclusiva da Carteira B Ltda" not in html


def test_indicador_de_empresas_ativas_isola_por_escritorio(client):
    escritorio_a = Escritorio.objects.create(nome="Escritório Indicador A", cnpj="11222333000181")
    escritorio_b = Escritorio.objects.create(nome="Escritório Indicador B", cnpj="99888777000162")
    _empresa(escritorio_a, "22444666000177", "Empresa Ativa A Ltda")
    for numero in range(3):
        _empresa(escritorio_b, f"3355577700{numero:04d}", f"Empresa Ativa B {numero} Ltda")
    _usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-indicador-a")

    assert client.login(username="gestor-indicador-a", password="senha-forte-123")
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    # O indicador conta só as empresas do escritório ATIVO (1), nunca a
    # soma dos dois escritórios (4) — a prova fica no context, não numa
    # busca de texto no HTML (o número "1" apareceria em muitos lugares).
    indicador_empresas_ativas = next(
        item for item in resposta.context["indicadores"] if item["chave"] == "empresas-ativas"
    )
    assert indicador_empresas_ativas["total"] == 1


def test_papel_cliente_nao_ve_empresas_da_carteira(client):
    """Mesma classe de defeito que
    test_dl042_fila_de_atencao.py::test_papel_cliente_nao_ve_a_fila_de_
    atencao — "Empresas da carteira" é conteúdo operacional (pendência,
    última competência fechada), a mesma classe de informação que a fila
    já restringe a quem lê contabilidade."""
    escritorio = Escritorio.objects.create(
        nome="Escritório Cliente Carteira", cnpj="11222333000181"
    )
    _empresa(escritorio, "22444666000177", "Empresa Não Vista Pelo Cliente Ltda")
    _usuario_com_papel(escritorio, Papel.CLIENTE, "cliente-carteira")

    assert client.login(username="cliente-carteira", password="senha-forte-123")
    resposta = client.get(reverse("tenancy:painel"))
    html = resposta.content.decode()

    assert resposta.context["empresas_da_carteira"] is None
    assert "Empresa Não Vista Pelo Cliente Ltda" not in html


# ---------------------------------------------------------------------------
# 2. Número de consultas CONSTANTE (nunca N+1 por empresa)
# ---------------------------------------------------------------------------


def test_numero_de_consultas_da_carteira_nao_cresce_com_o_numero_de_empresas(client):
    """Prova de verdade de "consulta de tamanho constante": mede o número
    de consultas com UMA empresa e com DEZ, e exige o MESMO número — não
    um teto largo (que um N+1 discreto passaria por baixo), a igualdade
    exata entre os dois cenários."""
    escritorio_uma = Escritorio.objects.create(
        nome="Escritório Carteira Uma", cnpj="11222333000181"
    )
    _empresa(escritorio_uma, "22444666000177", "Empresa Única Ltda")
    _usuario_com_papel(escritorio_uma, Papel.GESTOR, "gestor-carteira-uma")

    escritorio_dez = Escritorio.objects.create(
        nome="Escritório Carteira Dez", cnpj="99888777000162"
    )
    for numero in range(10):
        _empresa(escritorio_dez, f"335557{numero:08d}", f"Empresa {numero} Ltda")
    _usuario_com_papel(escritorio_dez, Papel.GESTOR, "gestor-carteira-dez")

    assert client.login(username="gestor-carteira-uma", password="senha-forte-123")
    with CaptureQueriesContext(connection) as consultas_uma:
        resposta_uma = client.get(reverse("tenancy:painel"))
    assert resposta_uma.status_code == 200
    client.logout()

    assert client.login(username="gestor-carteira-dez", password="senha-forte-123")
    with CaptureQueriesContext(connection) as consultas_dez:
        resposta_dez = client.get(reverse("tenancy:painel"))
    assert resposta_dez.status_code == 200

    assert len(resposta_dez.context["empresas_da_carteira"]) == 10
    assert len(resposta_uma.context["empresas_da_carteira"]) == 1
    assert len(consultas_dez) == len(consultas_uma), (
        "número de consultas cresceu com o número de empresas — N+1 na "
        f"carteira: {len(consultas_uma)} consulta(s) com 1 empresa, "
        f"{len(consultas_dez)} com 10."
    )
