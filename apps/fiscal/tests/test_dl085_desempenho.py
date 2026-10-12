"""DL-085 (frente A): sem N+1 na prévia. O número de consultas não cresce com o número de notas.

Medido com 20 e com 200 notas já lidas. A prévia de notas já lidas lê as notas em consultas fixas
(a lista do mês, os itens em lotes de 5.000 notas) e não consulta nada por nota.
A PRIMEIRA leitura de uma nota (nunca lida) é por nota, por desenho, e está documentada no módulo.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.tests.suporte_dl085 import nfce, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db


def _consultas(funcao) -> int:
    with CaptureQueriesContext(connection) as contexto:
        funcao()
    return len(contexto.captured_queries)


def _notas(escritorio, usuario, inicio, quantidade):
    for numero in range(inicio, inicio + quantidade):
        if numero % 2:
            nfce(escritorio, usuario, numero=numero, valor="10.00")
        else:
            nfce(escritorio, usuario, numero=numero, valor="12.00", cfop="5102", csosn="102")


def test_previa_de_notas_ja_lidas_tem_o_mesmo_numero_de_consultas_com_20_e_com_200(escritorio_a):
    """Critério de N+1. As notas são lidas pela leitura em partes; a prévia seguinte é medida."""
    usuario = usuario_gestor(escritorio_a, "gestor-desempenho-dl085")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Desempenho DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    _notas(escritorio_a, usuario, 1, 20)
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    vinte = _consultas(lambda: lote.previa_do_lote(empresa, 2026, 3))

    _notas(escritorio_a, usuario, 21, 180)
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    duzentas = _consultas(lambda: lote.previa_do_lote(empresa, 2026, 3))

    assert sum(g.quantidade_notas for g in lote.previa_do_lote(empresa, 2026, 3).grupos) == 200
    print(f"[DL-085 consultas] previa com 20 notas lidas: {vinte}; com 200: {duzentas}")
    assert duzentas == vinte, f"consultas da prévia: {vinte} com 20 notas, {duzentas} com 200"


def test_previa_de_notas_nao_lidas_tambem_tem_o_mesmo_numero_de_consultas(escritorio_a):
    """A prévia não lê XML: com notas ainda não lidas, o número de consultas também não cresce."""
    usuario = usuario_gestor(escritorio_a, "gestor-desempenho-dl085")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Desempenho DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    _notas(escritorio_a, usuario, 1, 20)
    vinte = _consultas(lambda: lote.previa_do_lote(empresa, 2026, 3))
    _notas(escritorio_a, usuario, 21, 180)
    duzentas = _consultas(lambda: lote.previa_do_lote(empresa, 2026, 3))
    assert duzentas == vinte
    assert (
        lote.previa_do_lote(empresa, 2026, 3).a_ler
        and len(lote.previa_do_lote(empresa, 2026, 3).a_ler) == 200
    )
