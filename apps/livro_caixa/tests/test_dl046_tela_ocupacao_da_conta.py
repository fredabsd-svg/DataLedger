"""DL-046, fatia 3 — o campo `codigo_ocupacao` na TELA da conta do
livro-caixa.

Achado 2 da rodada 1 da auditoria independente: o campo existia no MODELO e
na API, mas **nenhum teste exercitava o caminho de tela** — e há um agravante
aqui que não existe no cadastro de empresa: o formulário passa por
`recusar_dado_nao_contratado` (a política dos cinco dicionários do BL-196).
Sem a entrada do campo novo em `_CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA`, a
tela devolveria 400 **no próprio campo que acabou de ganhar** — e mutação
removendo essa entrada não reprovava nada.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.livro_caixa.models import NaturezaCaixa
from apps.livro_caixa.views_web import (
    _CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA,
    ContaCaixaForm,
)
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

OCUPACAO_MEDICO = "225"
CODIGO_TRABALHO_NAO_ASSALARIADO = "R01.001.001"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório Conta Ocupação", cnpj="91100000000080")


@pytest.fixture
def empresa(escritorio):
    from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao

    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Fulano Conta Ocupação",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="11144477735",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )


@pytest.fixture
def autenticado(client, escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-conta-ocupacao",
        email="gestor-conta-ocupacao@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestor-conta-ocupacao", password="senha-forte-123")
    return client


def test_o_campo_de_ocupacao_aparece_no_formulario_de_conta():
    """`livro_caixa/conta_form.html` itera `form` — o campo precisa existir
    nele, senão a sobreposição da ocupação do cliente por conta nunca é
    oferecida e a linha de rendimento sai com a ocupação errada ou vazia."""
    assert "codigo_ocupacao" in ContaCaixaForm().fields


def test_o_campo_de_ocupacao_aceito_pelo_contrato_da_tela_de_conta():
    """Sem esta entrada, `recusar_dado_nao_contratado` devolveria 400 no
    próprio campo novo — a tela ficaria inutilizável justamente para o que
    ela passou a oferecer."""
    assert "codigo_ocupacao" in _CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA.campos


def test_tela_cria_conta_de_trabalho_com_ocupacao_de_sobreposicao(autenticado, empresa):
    """A ocupação da conta SOBREPÕE a do cliente na geração do arquivo
    (`carne_leao_arquivos._ocupacao_efetiva`) — é o que permite dois
    clientes da mesma conta usarem ocupações diferentes."""
    resposta = autenticado.post(
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        {
            "csrfmiddlewaretoken": "x",
            "codigo": "R1",
            "nome": "Honorários recebidos",
            "natureza": NaturezaCaixa.RECEITA,
            "codigo_carne_leao": CODIGO_TRABALHO_NAO_ASSALARIADO,
            "codigo_ocupacao": OCUPACAO_MEDICO,
            "ativa": "on",
        },
    )
    assert resposta.status_code == 302, resposta.content
    from apps.livro_caixa.models import ContaLivroCaixa

    conta = ContaLivroCaixa.objects.get(empresa=empresa, codigo="R1")
    assert conta.codigo_ocupacao == OCUPACAO_MEDICO


def test_tela_recusa_ocupacao_em_conta_de_aluguel_que_nao_aceita_sobreposicao(autenticado, empresa):
    """A sobreposição só é pertinente em rendimento de trabalho não
    assalariado e de serviços notariais (`ContaLivroCaixa.clean()`); a tela
    tem de propagar a recusa do servidor com o erro no campo certo."""
    resposta = autenticado.post(
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        {
            "csrfmiddlewaretoken": "x",
            "codigo": "R2",
            "nome": "Aluguéis recebidos",
            "natureza": NaturezaCaixa.RECEITA,
            "codigo_carne_leao": "R01.003.001",
            "codigo_ocupacao": OCUPACAO_MEDICO,
            "ativa": "on",
        },
    )
    assert resposta.status_code == 200, resposta.content
    conteudo = resposta.content.decode()
    assert "codigo_ocupacao" in conteudo or "ocupação" in conteudo
    from apps.livro_caixa.models import ContaLivroCaixa

    assert not ContaLivroCaixa.objects.filter(empresa=empresa).exists()


def test_controle_tela_sem_ocupacao_continua_criando_a_conta(autenticado, empresa):
    """O campo é OPCIONAL — a conta continua sendo criada sem ele."""
    resposta = autenticado.post(
        reverse("livro_caixa_web:conta_nova", args=[empresa.id]),
        {
            "csrfmiddlewaretoken": "x",
            "codigo": "R1",
            "nome": "Honorários recebidos",
            "natureza": NaturezaCaixa.RECEITA,
            "codigo_carne_leao": CODIGO_TRABALHO_NAO_ASSALARIADO,
            "codigo_ocupacao": "",
            "ativa": "on",
        },
    )
    assert resposta.status_code == 302, resposta.content
    from apps.livro_caixa.models import ContaLivroCaixa

    assert ContaLivroCaixa.objects.get(empresa=empresa, codigo="R1").codigo_ocupacao == ""
