"""DL-074 — R2 da reconferência: quatro lançamentos iguais ao mesmo tempo geram UMA receita.

Mutante N8e: sem `travar_empresa` antes da checagem de duplicata, duas threads leem "não
existe" e as duas gravam. A trava da empresa é o que serializa a checagem e o INSERT.

Cada thread usa a SUA conexão de PostgreSQL, por isso o teste é `transaction=True` (mesmo
padrão de `test_dl074_concorrencia.py`). A barreira faz as quatro partirem juntas. Todo
`join()` tem timeout e uma asserção depois: thread travada vira falha visível.
"""

import threading

import pytest
from django.db import connection

from apps.fiscal import receita as servico
from apps.fiscal.models import MercadoReceita, ReceitaInformada
from apps.fiscal.tests.test_dl074_suporte import ORIGEM_OUTRAS

pytestmark = pytest.mark.django_db(transaction=True)

INTERNO = MercadoReceita.INTERNO
TIMEOUT_SEGUNDOS = 30
THREADS = 4


def test_r2_quatro_lancamentos_iguais_simultaneos_geram_uma_receita_so(empresa_a, usuario_gestor_a):
    barreira = threading.Barrier(THREADS)
    desfechos = [None] * THREADS

    def lancar(indice):
        try:
            barreira.wait(timeout=TIMEOUT_SEGUNDOS)
            servico.lancar_receita_informada(
                empresa_a,
                2026,
                5,
                INTERNO,
                "1500.00",
                ORIGEM_OUTRAS,
                "Motivo sintético.",
                "NF 123 sintética",
                usuario_gestor_a,
                situacao_iss="proprio_municipio",
            )
            desfechos[indice] = "ok"
        except servico.ReceitaErro:
            desfechos[indice] = "ReceitaErro"
        except BaseException as exc:  # noqa: BLE001 — o erro inesperado é o dado do teste
            desfechos[indice] = f"inesperado: {exc!r}"
        finally:
            connection.close()

    threads = [threading.Thread(target=lancar, args=(i,)) for i in range(THREADS)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT_SEGUNDOS)

    assert not any(t.is_alive() for t in threads), "thread travada: falha, não espera infinita"
    assert all(d is not None for d in desfechos), "alguma thread não devolveu desfecho"
    assert sorted(desfechos) == ["ReceitaErro"] * (THREADS - 1) + ["ok"], desfechos
    assert ReceitaInformada.objects.filter(empresa=empresa_a).count() == 1
