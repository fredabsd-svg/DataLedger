"""Testes das views HTML de tenancy (DL-009: aviso na troca de escritório).

Antes desta etapa, `ativar_escritorio` redirecionava em silêncio quando o
vínculo não existia — o usuário não tinha como saber se a troca funcionou.
Cobre também landmarks e rótulo do seletor, que dependem do HTML renderizado
de verdade, não só do template como texto.

Pós-auditoria (2026-09-12): as asserções sobre mensagem de sucesso passaram
a checar `resposta.context["messages"]` em vez de procurar o texto no HTML
inteiro — o achado A2 mostrou que "Escritório ativo: Escritório B" também
aparece no `<h1>` do painel, então a asserção antiga passava mesmo sem
nenhuma mensagem ter sido criada (removida `messages.success(...)` da view,
os 34 testes da suíte ainda passavam). Também cobre A4 (críticos 9, 13 e 15
sem teste antes) e A9 (GET em `ativar_escritorio` voltava em silêncio).
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.permissions import IsAuthenticated

from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio
from apps.tenancy.views import EscritorioAtivoView, MeusEscritoriosView

pytestmark = pytest.mark.django_db


@pytest.fixture
def usuario_com_dois_escritorios():
    Usuario = get_user_model()
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    escritorio_sem_vinculo = Escritorio.objects.create(nome="Escritório C", cnpj="33333333000133")

    usuario = Usuario.objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_a, papel=Papel.GESTOR
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )

    return {
        "usuario": usuario,
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "escritorio_sem_vinculo": escritorio_sem_vinculo,
    }


def _mensagens(resposta):
    """Extrai o texto das mensagens de django.contrib.messages já renderizadas.

    Usa o contexto capturado pelo cliente de teste (populado pelo sinal
    template_rendered), não uma busca por substring no HTML inteiro — ver
    docstring do módulo sobre o achado A2.
    """
    return [str(m) for m in resposta.context["messages"]]


def test_ativar_escritorio_sem_vinculo_mostra_mensagem_de_erro(
    client, usuario_com_dois_escritorios
):
    client.login(username="ana", password="senha-forte-123")
    escritorio_sem_vinculo = usuario_com_dois_escritorios["escritorio_sem_vinculo"]

    resposta = client.post(
        reverse("tenancy:ativar"), {"escritorio_id": escritorio_sem_vinculo.id}, follow=True
    )

    assert resposta.status_code == 200
    assert any("Escritório inválido ou sem vínculo ativo" in m for m in _mensagens(resposta))
    assert 'role="alert"' in resposta.content.decode()
    # A troca não pode ter sido aplicada apesar da falha.
    assert client.session.get("escritorio_id") != escritorio_sem_vinculo.id


def test_ativar_escritorio_com_valor_nao_numerico_nao_quebra_e_avisa(
    client, usuario_com_dois_escritorios
):
    client.login(username="ana", password="senha-forte-123")

    resposta = client.post(reverse("tenancy:ativar"), {"escritorio_id": "abc"}, follow=True)

    assert resposta.status_code == 200
    assert any("Escritório inválido" in m for m in _mensagens(resposta))


def test_ativar_escritorio_com_sucesso_mostra_mensagem_de_confirmacao(
    client, usuario_com_dois_escritorios
):
    client.login(username="ana", password="senha-forte-123")
    escritorio_b = usuario_com_dois_escritorios["escritorio_b"]

    resposta = client.post(
        reverse("tenancy:ativar"), {"escritorio_id": escritorio_b.id}, follow=True
    )

    assert resposta.status_code == 200
    # Mensagem de verdade (não o <h1>, que tem o texto parecido mas sem
    # ponto final e sem passar pelo mecanismo de messages).
    assert any("Escritório ativo: Escritório B." in m for m in _mensagens(resposta))
    assert "mensagem-success" in resposta.content.decode()
    assert client.session.get("escritorio_id") == escritorio_b.id


def test_ativar_escritorio_via_get_nao_troca_e_avisa(client, usuario_com_dois_escritorios):
    """A9: GET nesta URL não deve trocar nada nem voltar em silêncio."""
    client.login(username="ana", password="senha-forte-123")
    escritorio_b = usuario_com_dois_escritorios["escritorio_b"]

    resposta = client.get(reverse("tenancy:ativar"), follow=True)

    assert resposta.status_code == 200
    assert any("formulário do painel" in m for m in _mensagens(resposta))
    assert client.session.get("escritorio_id") != escritorio_b.id


def test_painel_tem_landmarks_atalho_e_select_com_rotulo(client, usuario_com_dois_escritorios):
    client.login(username="ana", password="senha-forte-123")

    resposta = client.get(reverse("tenancy:painel"))

    assert "base.html" in [t.name for t in resposta.templates if t.name]
    conteudo = resposta.content.decode()
    assert "<header" in conteudo
    assert "<nav" in conteudo
    assert '<main id="conteudo"' in conteudo
    assert 'href="#conteudo"' in conteudo
    # O select de troca de escritório precisa de rótulo associado, não só
    # de um <select> solto (achado da auditoria de 2026-09-11).
    assert 'for="id_escritorio_id"' in conteudo
    assert 'id="id_escritorio_id"' in conteudo
    # O formulário de logout agora vive no cabeçalho, fora de qualquer <p>
    # (a estrutura antiga tinha <form> aninhado em <p>, HTML inválido).
    assert 'class="form-sair"' in conteudo


def test_cabecalho_mostra_escritorio_ativo_em_toda_pagina_autenticada(
    client, usuario_com_dois_escritorios
):
    """Critério 15, sem teste antes do achado A4: o cabeçalho precisa dizer
    em qual escritório o usuário está operando, não só o <h1> do painel.

    Cuidado que este teste corrige em si mesmo: a troca de escritório gera
    uma mensagem flash "Escritório ativo: Escritório A." — texto quase
    idêntico ao do cabeçalho. Uma primeira asserção ingênua por substring
    passava só por causa da mensagem, mesmo com o trecho do cabeçalho
    removido (a mensagem, sendo "usada" uma vez, não aparece mais depois).
    Por isso: 1) uma requisição a mais para consumir a mensagem antes de
    verificar; 2) a asserção usa a marcação específica do cabeçalho
    (`contexto-rotulo`), não o texto solto.
    """
    client.login(username="ana", password="senha-forte-123")
    escritorio_a = usuario_com_dois_escritorios["escritorio_a"]
    client.post(reverse("tenancy:ativar"), {"escritorio_id": escritorio_a.id})
    client.get(reverse("empresas:lista"))  # consome a mensagem flash da troca

    resposta = client.get(reverse("empresas:lista"))

    conteudo = resposta.content.decode()
    assert '<span class="contexto-rotulo">Escritório ativo:</span>' in conteudo
    assert "Escritório A" in conteudo
    assert "mensagem-success" not in conteudo  # garante que não sobrou flash


# ---------------------------------------------------------------------------
# R3-10 (auditoria DL-017, rodada 3): `MeusEscritoriosView` e
# `EscritorioAtivoView` (apps/tenancy/views.py) são as ÚNICAS duas `APIView`
# do repositório que não declaravam `permission_classes` própria — dependiam
# só do padrão global (`REST_FRAMEWORK.DEFAULT_PERMISSION_CLASSES`,
# `config/settings.py`). Não havia vazamento (o padrão já é
# `IsAuthenticated`), mas o risco era de MANUTENÇÃO: relaxar o padrão
# global no futuro (para uma rota pública qualquer) tiraria a autenticação
# destas duas sem que nenhuma linha delas mudasse.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_rota", ["tenancy:api-escritorios", "tenancy:api-escritorio-ativo"])
def test_apiview_de_tenancy_recusa_usuario_anonimo(client, nome_rota):
    resposta = client.get(reverse(nome_rota))
    assert resposta.status_code == 403, (nome_rota, resposta.status_code)


@pytest.mark.parametrize("nome_view", [MeusEscritoriosView.__name__, EscritorioAtivoView.__name__])
def test_apiview_de_tenancy_declara_permission_classes_na_propria_classe(nome_view):
    """R3-10: a prova de que a permissão está DECLARADA na view, não herdada
    do padrão global — de forma determinística, não por comportamento em
    tempo de execução.

    **Por que não `override_settings(REST_FRAMEWORK=...)`, que era a
    primeira forma que este teste tomou.** Medi, na mutação desta entrega
    (mutante: apagar `permission_classes = [IsAuthenticated]` das duas
    views): um teste baseado em `override_settings` só detecta a ausência
    da declaração quando é a PRIMEIRA requisição DRF do processo de teste —
    em qualquer execução posterior (a normal, com a suíte inteira), o
    mutante SOBREVIVE em silêncio, porque `rest_framework.views.APIView`
    fixa `permission_classes = api_settings.DEFAULT_PERMISSION_CLASSES`
    como atributo de classe NA IMPORTAÇÃO do módulo — uma vez por processo.
    `override_settings` dispara o sinal que invalida o CACHE de
    `api_settings`, mas não reescreve o atributo de classe já fixado em
    `APIView`, que é exatamente o que uma view SEM `permission_classes`
    próprio herdaria. É a mesma classe de "medição que não consegue falhar"
    do R3-4 (o `tail -1 && echo OK`) — e eu só a encontrei porque apliquei o
    mutante na ordem em que a suíte real roda, não isolado.

    A prova correta é ESTRUTURAL, e não depende de nenhum comportamento de
    cache do DRF nem da ordem de execução: `permission_classes` precisa
    estar no `__dict__` da PRÓPRIA classe (`view_classe.__dict__`), não só
    acessível por herança (`getattr`/MRO acharia o atributo herdado de
    `APIView` de qualquer forma, mutante ou não — por isso não usei
    `getattr`). Recebe o NOME da classe, não a classe em si, porque
    `pytest.mark.parametrize` não pode fixar valores de classe direto no
    id do teste de forma legível; resolve pelo nome dentro do teste.
    """
    view_classe = {
        "MeusEscritoriosView": MeusEscritoriosView,
        "EscritorioAtivoView": EscritorioAtivoView,
    }[nome_view]
    assert "permission_classes" in view_classe.__dict__, (
        f"{nome_view} não declara `permission_classes` na própria classe — "
        "dependeria do padrão global herdado via MRO, o risco de manutenção "
        "que o achado R3-10 aponta."
    )
    assert view_classe.__dict__["permission_classes"] == [IsAuthenticated]


def test_apiview_de_tenancy_aceita_usuario_autenticado(client, usuario_com_dois_escritorios):
    """Controle positivo: a declaração explícita de `permission_classes`
    não pode ter apertado o caminho normal — usuário autenticado continua
    acessando as duas rotas."""
    client.login(username="ana", password="senha-forte-123")
    resposta_escritorios = client.get(reverse("tenancy:api-escritorios"))
    assert resposta_escritorios.status_code == 200
    resposta_ativo = client.get(reverse("tenancy:api-escritorio-ativo"))
    assert resposta_ativo.status_code == 200
