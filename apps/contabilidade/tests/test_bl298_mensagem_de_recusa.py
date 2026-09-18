"""BL-298 (M7 da auditoria DL-024 rodada 2,
docs/auditorias/2026-09-18-dl-024-rodada-2.md): a mensagem de recusa do
`acao=gravar` se contradizia quando os totais eram IGUAIS e não positivos.

`gravar` com `0,00`/`0,00` respondia *"Débitos (0,00) e créditos (0,00)
precisam ser iguais antes de gravar"* — e eles SÃO iguais. O motivo real da
recusa (total não positivo) não era dito; o contador que lesse a mensagem ia
conferir a igualdade, achar tudo certo e não saber o que fazer.

Correção: `apps.contabilidade.views_web.lancamento_novo` separa os dois
ramos — `total_debito != total_credito` mantém a frase de divergência
(inalterada); `total_debito == total_credito` mas `total_debito <= 0` ganha
frase própria, que nunca afirma uma divergência inexistente.

Dados 100% sintéticos, criados nos próprios testes.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório de teste", cnpj="33333333000133")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-298 Ltda", cnpj="33344455000175"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl298",
        email="gestora-bl298@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-bl298", password="senha-forte-123")


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _gravar(client, cen, *, valor_debito, valor_credito, chave):
    return client.post(
        _url_tela(cen),
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "Teste BL-298",
            "chave_idempotencia": chave,
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": valor_debito,
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": valor_credito,
        },
    )


def _mensagens(resposta):
    return [str(m) for m in resposta.context["messages"]]


@pytest.mark.parametrize("valor", ["0,00", "-5,00"])
def test_totais_iguais_e_nao_positivos_nao_afirmam_divergencia(client, cen, valor):
    """Antes: `gravar` com 0,00/0,00 (ou -5,00/-5,00) respondia "Débitos
    (X) e créditos (X) precisam ser iguais" — mentira, porque X == X. A
    mensagem não pode mais conter "precisam ser iguais" quando os totais
    JÁ são iguais."""
    _login(client, cen)
    resposta = _gravar(
        client, cen, valor_debito=valor, valor_credito=valor, chave=f"k-bl298-{valor}"
    )
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    mensagens = _mensagens(resposta)
    assert not any("precisam ser iguais" in m for m in mensagens), mensagens
    assert any("maior que zero" in m for m in mensagens), mensagens


def test_totais_divergentes_mantem_a_frase_original(client, cen):
    """A frase de divergência não pode desaparecer nem mudar quando os
    totais REALMENTE divergem — é o caso em que ela é verdadeira."""
    _login(client, cen)
    resposta = _gravar(
        client, cen, valor_debito="1.500,00", valor_credito="900,00", chave="k-bl298-divergente"
    )
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    mensagens = _mensagens(resposta)
    assert any(
        "Débitos (1.500,00) e créditos (900,00) precisam ser iguais antes de gravar" in m
        for m in mensagens
    ), mensagens
    assert not any("maior que zero" in m for m in mensagens), mensagens


def test_totais_negativos_e_diferentes_mantem_a_frase_de_divergencia(client, cen):
    """Caso limite: totais negativos E diferentes — a frase de divergência
    continua correta (eles NÃO são iguais), mesmo que os dois sejam
    negativos; não é o caso do BL-298 (esse exige igualdade)."""
    _login(client, cen)
    resposta = _gravar(
        client, cen, valor_debito="-10,00", valor_credito="-20,00", chave="k-bl298-neg-diff"
    )
    assert resposta.status_code == 400
    mensagens = _mensagens(resposta)
    assert any(
        "Débitos (-10,00) e créditos (-20,00) precisam ser iguais antes de gravar" in m
        for m in mensagens
    ), mensagens
