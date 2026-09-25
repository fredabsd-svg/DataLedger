"""Testes de `apps.fiscal.permissoes` — HI-21.

Cobre todos os valores de `Papel`, inclusive `None` (sem escritório ativo).
Mutar `PAPEIS_QUE_RECEBEM_DOCUMENTOS`/`PAPEIS_QUE_CONSULTAM_DOCUMENTOS` ou
as funções que as consultam derruba algum destes testes — é a garantia de
que não existe uma segunda cópia da decisão em outro lugar do módulo.
"""

import pytest

from apps.fiscal.permissoes import papel_pode_consultar_documentos, papel_pode_receber_documentos
from apps.tenancy.models import Papel


@pytest.mark.parametrize(
    ("papel", "esperado"),
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, True),
        (Papel.FINANCEIRO, True),
        (Papel.PARALEGAL, False),
        (Papel.CLIENTE, False),
        (None, False),
    ],
)
def test_papel_pode_receber_documentos(papel, esperado):
    assert papel_pode_receber_documentos(papel) is esperado


@pytest.mark.parametrize(
    ("papel", "esperado"),
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, True),
        (Papel.FINANCEIRO, True),
        (Papel.PARALEGAL, True),
        (Papel.CLIENTE, False),
        (None, False),
    ],
)
def test_papel_pode_consultar_documentos(papel, esperado):
    assert papel_pode_consultar_documentos(papel) is esperado


def test_quem_recebe_e_subconjunto_de_quem_consulta():
    # Invariante de coerência: ninguém pode ENVIAR sem poder CONSULTAR.
    from apps.fiscal.permissoes import PAPEIS_QUE_CONSULTAM_DOCUMENTOS, PAPEIS_QUE_RECEBEM_DOCUMENTOS

    assert set(PAPEIS_QUE_RECEBEM_DOCUMENTOS) <= set(PAPEIS_QUE_CONSULTAM_DOCUMENTOS)
