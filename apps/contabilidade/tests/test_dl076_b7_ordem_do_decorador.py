"""Achado B7 da auditoria rodada 1 (DL-038): a recusa de livro-caixa
precisa rodar DEPOIS do escritório ativo e do papel serem checados — nunca
antes. Antes desta correção, a recusa de livro-caixa (então um decorador
aplicado por FORA da view) rodava primeiro, e dois efeitos foram medidos:

1. Usuário SEM escritório ativo em `contabilidade_web:diario` recebia 404
   (a empresa nunca era resolvida pelo caminho que checa isso primeiro),
   quando deveria ver a tela "sem escritório ativo".
2. `CLIENTE` (que não tem permissão de LEITURA da contabilidade) numa
   empresa livro-caixa recebia a MENSAGEM DE LIVRO-CAIXA em vez de "sem
   permissão" — revelando o MODO de escrituração da empresa a quem nem
   pode ler o resto.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório B7", cnpj="91100000000050")


@pytest.fixture
def empresa_livro_caixa(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Livro-Caixa B7 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )


def test_usuario_sem_escritorio_ativo_ve_tela_de_sem_escritorio_nao_404(
    client, empresa_livro_caixa
):
    # Usuário AUTENTICADO mas SEM nenhum vínculo com escritório nenhum —
    # `request.escritorio` fica `None` (EscritorioAtivoMiddleware).
    get_user_model().objects.create_user(
        username="sem-escritorio-b7",
        email="sem-escritorio-b7@x.com.br",
        password="senha-forte-123",
    )
    client.login(username="sem-escritorio-b7", password="senha-forte-123")

    resposta = client.get(
        reverse("contabilidade_web:diario", kwargs={"empresa_id": empresa_livro_caixa.pk})
    )

    # NUNCA 404 (a empresa nem chegou a ser resolvida) nem a mensagem de
    # livro-caixa (que pressuporia ter resolvido a empresa) — a checagem de
    # escritório é a PRIMEIRA a rodar.
    assert resposta.status_code == 200
    assert "empresas/sem_escritorio.html" in [t.name for t in resposta.templates if t.name]
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA not in resposta.content.decode()


def test_cliente_sem_permissao_de_leitura_nao_ve_a_mensagem_de_livro_caixa(
    client, escritorio, empresa_livro_caixa
):
    # CLIENTE não lê contabilidade (PAPEIS_QUE_LEEM_CONTABILIDADE não o
    # inclui) — a mensagem que ele vê tem que ser a de PERMISSÃO, nunca a
    # de livro-caixa (que revelaria o MODO de escrituração da empresa a
    # quem não tem acesso nem para ler o resto).
    usuario = get_user_model().objects.create_user(
        username="cliente-b7", email="cliente-b7@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.CLIENTE
    )
    client.login(username="cliente-b7", password="senha-forte-123")

    resposta = client.get(
        reverse("contabilidade_web:diario", kwargs={"empresa_id": empresa_livro_caixa.pk})
    )

    assert resposta.status_code == 403
    conteudo = resposta.content.decode()
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA not in conteudo
    assert "não permite ler a contabilidade" in conteudo


def test_gestor_em_empresa_livro_caixa_ve_a_mensagem_de_livro_caixa(
    client, escritorio, empresa_livro_caixa
):
    # Controle positivo: um papel que TEM permissão de leitura, mas a
    # empresa está em livro-caixa — aí sim a mensagem específica aparece
    # (ele já tinha acesso para saber o motivo).
    usuario = get_user_model().objects.create_user(
        username="gestor-b7", email="gestor-b7@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    client.login(username="gestor-b7", password="senha-forte-123")

    resposta = client.get(
        reverse("contabilidade_web:diario", kwargs={"empresa_id": empresa_livro_caixa.pk})
    )

    assert resposta.status_code == 403
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()


def test_empresa_de_outro_escritorio_continua_dando_404_antes_de_qualquer_recusa(
    client, empresa_livro_caixa
):
    # Isolamento (critério 2) continua intacto: `_empresa_do_escritorio_
    # ativo` roda ANTES da recusa de livro-caixa (e antes dela, o papel);
    # uma empresa que não pertence ao escritório ativo do usuário dá 404,
    # nunca 403 nem a mensagem de livro-caixa.
    outro_escritorio = Escritorio.objects.create(nome="Outro Escritório B7", cnpj="91100000000051")
    usuario = get_user_model().objects.create_user(
        username="gestor-outro-b7", email="gestor-outro-b7@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=outro_escritorio, papel=Papel.GESTOR
    )
    client.login(username="gestor-outro-b7", password="senha-forte-123")

    resposta = client.get(
        reverse("contabilidade_web:diario", kwargs={"empresa_id": empresa_livro_caixa.pk})
    )

    assert resposta.status_code == 404
