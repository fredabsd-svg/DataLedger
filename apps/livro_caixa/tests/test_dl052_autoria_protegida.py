"""RC-144 / DL-052: a autoria do registro do livro-caixa e do carnê-leão
sobrevive ao usuário — apagar quem escriturou é recusado (PROTECT), em vez de
anular `criado_por`. Dados sintéticos; o cenário vem do arquivo do livro-caixa."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError

from apps.livro_caixa.models import DependentesCarneLeaoCliente, LancamentoCaixa, OrigemRecebimento
from apps.livro_caixa.services import criar_lancamento_caixa
from apps.livro_caixa.tests.test_dl046_livro_caixa import cenario  # noqa: F401

pytestmark = pytest.mark.django_db


def _autor(nome):
    return get_user_model().objects.create_user(
        username=nome, email=f"{nome}@escritorio.com.br", password="senha-forte-123"
    )


def test_apagar_usuario_que_lancou_no_livro_caixa_e_recusado(cenario):  # noqa: F811
    autor = _autor("autor-caixa-052")
    lancamento = criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 1, 15),
        valor="10.00",
        historico="Lançamento do autor",
        recebido_de=OrigemRecebimento.PJ,
        criado_por=autor,
    )

    with pytest.raises(ProtectedError):
        autor.delete()

    assert get_user_model().objects.filter(pk=autor.pk).exists()
    assert LancamentoCaixa.objects.get(pk=lancamento.pk).criado_por_id == autor.pk


def test_apagar_usuario_que_informou_dependentes_e_recusado(cenario):  # noqa: F811
    autor = _autor("autor-dep-052")
    registro = DependentesCarneLeaoCliente.objects.create(
        empresa=cenario["empresa_a"],
        quantidade=2,
        competencia_inicio=date(2026, 1, 1),
        criado_por=autor,
    )

    with pytest.raises(ProtectedError):
        autor.delete()

    registro.refresh_from_db()
    assert registro.criado_por_id == autor.pk
