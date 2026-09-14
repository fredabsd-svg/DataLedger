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
from django.test import override_settings
from django.urls import reverse

from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

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
# destas duas sem que nenhuma linha delas mudasse. A prova de que a correção
# fecha esse risco é afrouxar o padrão global DENTRO do teste
# (`override_settings`) e confirmar que a recusa a anônimo CONTINUA — só é
# possível porque a permissão agora está fixada na própria classe.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome_rota", ["tenancy:api-escritorios", "tenancy:api-escritorio-ativo"])
def test_apiview_de_tenancy_recusa_usuario_anonimo(client, nome_rota):
    resposta = client.get(reverse(nome_rota))
    assert resposta.status_code == 403, (nome_rota, resposta.status_code)


@pytest.mark.parametrize("nome_rota", ["tenancy:api-escritorios", "tenancy:api-escritorio-ativo"])
def test_apiview_de_tenancy_recusa_anonimo_mesmo_com_padrao_global_afrouxado(client, nome_rota):
    """R3-10: a prova de que a permissão está DECLARADA na view, não só
    herdada do padrão global. Se `permission_classes = [IsAuthenticated]`
    fosse removido das duas views, este teste teria que FALHAR — a rota
    passaria a aceitar anônimo, porque o padrão global abaixo é `AllowAny`.
    A mutação que reproduz esse "antes" está na matriz de verificação desta
    entrega, não neste teste (que testa o estado CORRIGIDO).
    """
    padrao_afrouxado = {"DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"]}
    with override_settings(REST_FRAMEWORK=padrao_afrouxado):
        resposta = client.get(reverse(nome_rota))
    assert resposta.status_code == 403, (nome_rota, resposta.status_code)


def test_apiview_de_tenancy_aceita_usuario_autenticado(client, usuario_com_dois_escritorios):
    """Controle positivo: a declaração explícita de `permission_classes`
    não pode ter apertado o caminho normal — usuário autenticado continua
    acessando as duas rotas."""
    client.login(username="ana", password="senha-forte-123")
    resposta_escritorios = client.get(reverse("tenancy:api-escritorios"))
    assert resposta_escritorios.status_code == 200
    resposta_ativo = client.get(reverse("tenancy:api-escritorio-ativo"))
    assert resposta_ativo.status_code == 200
