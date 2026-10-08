"""DL-072 (frente A) — quem escritura NFS-e prestada.

A regra do plano é "os mesmos papéis que escrituram na contabilidade". Este
teste não confia na lista escrita à mão: compara, papel por papel, a função
do fiscal com a permissão DRF real da contabilidade (`PodeEscriturar`). Se
um dos dois lados mudar sem o outro, a suíte reprova.
"""

import pytest

from apps.contabilidade.views import PodeEscriturar
from apps.fiscal.permissoes import (
    PAPEIS_QUE_ESCRITURAM_FISCAL,
    papel_pode_consultar_documentos,
    papel_pode_escriturar_fiscal,
)
from apps.tenancy.models import Papel


class _RequisicaoComPapel:
    def __init__(self, papel):
        self.papel = papel


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
def test_papel_pode_escriturar_fiscal(papel, esperado):
    assert papel_pode_escriturar_fiscal(papel) is esperado


@pytest.mark.parametrize("papel", list(Papel.values) + [None])
def test_composicao_e_a_mesma_de_quem_escritura_na_contabilidade(papel):
    # A permissão real da contabilidade decide para a requisição com este papel.
    contabilidade = PodeEscriturar().has_permission(_RequisicaoComPapel(papel), None)
    assert papel_pode_escriturar_fiscal(papel) is contabilidade


def test_cliente_nunca_escritura_nem_consulta():
    assert papel_pode_escriturar_fiscal(Papel.CLIENTE) is False
    assert papel_pode_consultar_documentos(Papel.CLIENTE) is False


def test_quem_escritura_tambem_consulta():
    # Ninguém pode escriturar sem poder consultar a própria escrituração.
    for papel in PAPEIS_QUE_ESCRITURAM_FISCAL:
        assert papel_pode_consultar_documentos(papel) is True
