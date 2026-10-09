"""DL-085 (correção da auditoria rodada 1, A7): pico de memória da prévia, com NFC-e sintéticas.

Roda SÓ com `DL085_MEDIR_MEMORIA=1` (sem a variável, os testes ficam pulados). Mede com
`tracemalloc` o pico de memória do Python de:

- a prévia com as notas ainda não lidas (`previa_do_lote`, sem XML);
- a prévia depois da leitura de todas as notas (só cabeçalho e itens já gravados);
- a leitura de uma parte (`ler_notas_do_mes`, que carrega o XML de cada nota, como deve ser).

`DL085_NOTAS` (padrão 2000) é o número de NFC-e do mês. Use `pytest -s` para ver os números. O teste
não fixa um teto de memória: ele registra os picos, para comparar antes e depois da mudança.
"""

import os
import time
import tracemalloc

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.tests.suporte_dl085 import nfce, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

MEDIR = os.environ.get("DL085_MEDIR_MEMORIA") == "1"
NOTAS = int(os.environ.get("DL085_NOTAS", "2000"))

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not MEDIR, reason="medida de memória: defina DL085_MEDIR_MEMORIA=1"),
]


def _pico(funcao):
    """(resultado, pico em MB, segundos) de `funcao`, medidos com tracemalloc."""
    tracemalloc.start()
    inicio = time.perf_counter()
    try:
        resultado = funcao()
        _atual, pico = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return resultado, pico / (1024 * 1024), time.perf_counter() - inicio


def test_medida_de_memoria_da_previa(escritorio_a):
    usuario = usuario_gestor(escritorio_a, "gestor-memoria")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Memória", cnpj=CNPJ_EMITENTE_A
    )
    for numero in range(1, NOTAS + 1):
        nfce(escritorio_a, usuario, numero=numero, valor="10.00")

    previa_sem_leitura, pico_sem_leitura, tempo_sem_leitura = _pico(
        lambda: lote.previa_do_lote(empresa, 2026, 3)
    )
    assert len(previa_sem_leitura.a_ler) == NOTAS

    # A primeira parte é a medida; as seguintes só completam a leitura do mês.
    _leitura, pico_leitura, tempo_leitura = _pico(
        lambda: lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    )
    while not _leitura.terminou:
        _leitura = lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)

    previa_lida, pico_lida, tempo_lida = _pico(lambda: lote.previa_do_lote(empresa, 2026, 3))
    assert previa_lida.a_ler == ()
    assert sum(g.quantidade_notas for g in previa_lida.grupos) == NOTAS

    print(
        f"\nDL085 memória, {NOTAS} NFC-e: prévia sem leitura {pico_sem_leitura:.1f} MB "
        f"({tempo_sem_leitura:.2f} s); leitura de uma parte de "
        f"{lote.LIMITE_MAXIMO_DA_LEITURA} notas {pico_leitura:.1f} MB ({tempo_leitura:.2f} s); "
        f"prévia já lida {pico_lida:.1f} MB ({tempo_lida:.2f} s)."
    )
