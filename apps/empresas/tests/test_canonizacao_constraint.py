"""Testes da CheckConstraint de canonicidade do CNPJ (A2, reauditoria rodada 3).

``apps.empresas.models._CNPJ_E_CANONICO`` é a camada 1 (DE-008) do R1: mesmo
``bulk_create``/``bulk_update``/``QuerySet.update``, que não passam por
``Model.save()`` e portanto não canonizam em Python, são barrados pelo
próprio banco se o CNPJ gravado não estiver canônico. Até esta rodada essa
correção — a principal mudança estrutural do R1 — não tinha um único teste:
o auditor removeu as duas ``CheckConstraint`` (do ``Meta`` dos dois modelos
e da migração) e a suíte inteira continuou passando. Os quatro casos abaixo
são os que ele especificou, incluindo o que distingue as duas metades da
condição (``Q(cnpj=Upper("cnpj"))`` e ``~Q(cnpj__regex=r"[^A-Z0-9]")``).

Todas as asserções prendem a constraint pelo NOME (``empresa_cnpj_canonico``/
``estabelecimento_cnpj_canonico``), não só o tipo da exceção: se a
constraint for renomeada ou removida numa refatoração futura, um
IntegrityError diferente (ou nenhum) não deve passar por estes testes sem
ser notado.
"""

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")


def test_bulk_create_com_cnpj_minusculo_e_barrado_pelo_banco(escritorio):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.bulk_create(
            [
                Empresa(
                    escritorio=escritorio,
                    razao_social="Empresa Lote Ltda",
                    cnpj="ab123cde000155",
                )
            ]
        )

    assert "empresa_cnpj_canonico" in str(excinfo.value)


def test_bulk_create_estabelecimento_com_cnpj_minusculo_e_barrado_pelo_banco(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Estabelecimento.objects.bulk_create(
            [
                Estabelecimento(
                    empresa=empresa,
                    tipo=TipoEstabelecimento.MATRIZ,
                    nome="Matriz",
                    cnpj="ab123cde000155",
                )
            ]
        )

    assert "estabelecimento_cnpj_canonico" in str(excinfo.value)


def test_queryset_update_para_cnpj_minusculo_e_barrado(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.filter(pk=empresa.pk).update(cnpj="ab123cde000155")

    assert "empresa_cnpj_canonico" in str(excinfo.value)


def test_bulk_update_para_cnpj_minusculo_e_barrado(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    empresa.cnpj = "ab123cde000155"

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.bulk_update([empresa], ["cnpj"])

    assert "empresa_cnpj_canonico" in str(excinfo.value)


def test_bulk_create_com_cnpj_contendo_caractere_nao_alfanumerico_e_barrado(escritorio):
    # O caso que distingue as duas metades da condição: 14 caracteres, já
    # em maiúsculas (a metade Q(cnpj=Upper("cnpj")) passaria sozinha, sem
    # precisar da outra), mas com um espaço no meio — só a metade
    # ~Q(cnpj__regex=r"[^A-Z0-9]") pega isso. Um mutante que removesse essa
    # metade da condição sobreviveria aos quatro testes acima, mas não a
    # este.
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Empresa.objects.bulk_create(
            [
                Empresa(
                    escritorio=escritorio,
                    razao_social="Empresa Espaco Ltda",
                    cnpj="11222333 00018",
                )
            ]
        )

    assert "empresa_cnpj_canonico" in str(excinfo.value)
