"""DL-046, fatia 3 — o campo `codigo_ocupacao` na TELA.

Achado 2 da rodada 1 da auditoria independente: o campo existia no MODELO,
na API e no formulário, mas **nenhum teste exercitava o caminho de tela** —
mutação mental trocando a condição do `clean()` por `False`, ou removendo a
entrada do contrato da requisição, não reprovava nada. O AGENTS.md §7 exige
teste do comportamento alterado em interface.

Os testes de API e de modelo já cobrem a REGRA em si
(`test_dl046_fatia3_restricao_ocupacao_como_400.py` e
`apps/livro_caixa/tests/test_dl046_fatia3_arquivos_carne_leao.py`); estes
aqui provam que a TELA obedece — nunca reconferem a regra, para não pagar
duas vezes a mesma prova.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import TipoInscricao
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

OCUPACAO_VALIDA = "225"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório Ocupação Tela", cnpj="91100000000080")


@pytest.fixture
def autenticado(client, escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-ocupacao-tela",
        email="gestor-ocupacao-tela@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestor-ocupacao-tela", password="senha-forte-123")
    return client


# ---------------------------------------------------------------------------
# EmpresaForm (cadastro de empresa pela tela)
# ---------------------------------------------------------------------------


def test_o_campo_de_ocupacao_aparece_no_formulario_de_empresa():
    """`empresas/form.html` itera `form` — o campo precisa existir nele, senão
    a tela nunca o oferece e o arquivo do Carnê-Leão Web sai com a linha da
    ocupação vazia (pendência)."""
    assert "codigo_ocupacao" in EmpresaForm().fields


def test_tela_cadastra_empresa_pf_com_ocupacao_valida(autenticado, escritorio):
    resposta = autenticado.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano Ocupação Tela",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "codigo_ocupacao": OCUPACAO_VALIDA,
            "modo_escrituracao": "livro_caixa",
            "csrfmiddlewaretoken": "x",
        },
    )
    assert resposta.status_code == 302, resposta.content
    from apps.empresas.models import Empresa

    assert Empresa.objects.get(cpf="11144477735").codigo_ocupacao == OCUPACAO_VALIDA


def test_tela_recusa_ocupacao_em_empresa_cnpj_com_o_mesmo_texto_da_api(autenticado, escritorio):
    """DE-026: a tela e a API nunca contam duas histórias diferentes do mesmo
    motivo. O texto é o MESMO de `EmpresaSerializer.validate`."""
    resposta = autenticado.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa CNPJ Ocupação Tela",
            "tipo_inscricao": "CNPJ",
            "cnpj": "11122233000183",
            "codigo_ocupacao": OCUPACAO_VALIDA,
            "modo_escrituracao": "contabilidade",
            "csrfmiddlewaretoken": "x",
        },
    )
    assert resposta.status_code == 200, resposta.content
    conteudo = resposta.content.decode()
    assert "Código de ocupação só é aceito para empresa com tipo de inscrição CPF." in conteudo
    # O digitado volta para o formulário, nunca é apagado pela recusa.
    assert 'value="225"' in conteudo
    from apps.empresas.models import Empresa

    assert not Empresa.objects.filter(razao_social="Empresa CNPJ Ocupação Tela").exists()


def test_tela_recusa_ocupacao_fora_da_tabela_oficial(autenticado, escritorio):
    """O FORMATO e o pertencimento à tabela são do validador do campo do
    modelo (`clean_fields`) — a tela tem de propagar a recusa, não engoli-la."""
    resposta = autenticado.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano Ocupação Inválida",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "codigo_ocupacao": "999",
            "modo_escrituracao": "livro_caixa",
            "csrfmiddlewaretoken": "x",
        },
    )
    assert resposta.status_code == 200, resposta.content
    from apps.empresas.models import Empresa

    assert not Empresa.objects.filter(razao_social="Fulano Ocupação Inválida").exists()


def test_controle_tela_sem_ocupacao_continua_cadastrando(autenticado, escritorio):
    """O campo é OPCIONAL — o caso sem ele não pode ter sido afetado."""
    resposta = autenticado.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano Sem Ocupação",
            "tipo_inscricao": "CPF",
            "cpf": "11144477735",
            "codigo_ocupacao": "",
            "modo_escrituracao": "livro_caixa",
            "csrfmiddlewaretoken": "x",
        },
    )
    assert resposta.status_code == 302, resposta.content
    from apps.empresas.models import Empresa

    assert Empresa.objects.get(cpf="11144477735").codigo_ocupacao == ""


def test_a_regra_de_coerencia_do_formulario_e_de_fato_exercitada():
    """Controle do instrumento: sem a checagem em `EmpresaForm.clean()`, o
    teste de recusa acima passaria pelo caminho do BANCO (que também recusa)
    e não provaria que a TELA avisa. Este teste isola a checagem do
    formulário, para a mutação "condição trocada por `False`" morrer."""
    form = EmpresaForm(
        data={
            "razao_social": "Empresa CNPJ Com Ocupação",
            "tipo_inscricao": TipoInscricao.CNPJ,
            "cnpj": "11122233000183",
            "codigo_ocupacao": OCUPACAO_VALIDA,
            "modo_escrituracao": "contabilidade",
        }
    )
    assert not form.is_valid()
    assert "codigo_ocupacao" in form.errors
    assert (
        "Código de ocupação só é aceito para empresa com tipo de inscrição CPF."
        in form.errors["codigo_ocupacao"]
    )
