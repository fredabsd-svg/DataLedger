"""DL-069, fatia 2 — a migração 0012 de `livro_caixa` não quebra o SQLite.

Mesmo contrato e mesmo formato de
`apps/empresas/tests/test_dl039_bl529_gatilho_sqlite.py` e do teste irmão em
`apps/contabilidade/tests/test_dl069_gatilho_sqlite.py`: a migração de gatilho
é `RunPython` com no-op fora do PostgreSQL, e `manage.py migrate` completo
(ida e volta) precisa funcionar num SQLite TEMPORÁRIO. Os testes de
comportamento do gatilho em si são pulados fora do PostgreSQL (ver
`test_dl069_mes_encerrado_recusa_insert.py`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# apps/livro_caixa/tests/test_x.py -> apps/livro_caixa -> apps -> raiz do repo.
BASE_DIR = Path(__file__).resolve().parents[3]

SECRET_KEY_DE_TESTE = "chave-apenas-para-verificar-migracao-sqlite-de-teste"
MIGRACAO = "livro_caixa.0012_dl069_mes_encerrado_recusa_insert"
ANTERIOR = "0011"


def _ambiente(banco_path):
    ambiente = dict(os.environ)
    ambiente["DJANGO_SECRET_KEY"] = SECRET_KEY_DE_TESTE
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DEBUG"] = "True"
    # SQLite explícito em `tmp_path` — nunca `BASE_DIR/db.sqlite3` (ver o
    # comentário do mesmo tipo em test_dl039_bl529_gatilho_sqlite.py).
    ambiente["DATABASE_URL"] = f"sqlite:///{banco_path}"
    return ambiente


def _rodar_manage(banco_path, *argumentos, timeout=180):
    return subprocess.run(
        [sys.executable, "manage.py", *argumentos],
        cwd=BASE_DIR,
        env=_ambiente(banco_path),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_migrate_completo_funciona_em_sqlite_sem_quebrar_na_migracao_0012(tmp_path):
    banco = tmp_path / "dl069_f2_caixa_sqlite_teste.sqlite3"

    resultado = _rodar_manage(banco, "migrate")

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert f"Applying {MIGRACAO}... OK" in resultado.stdout
    assert "OperationalError" not in resultado.stderr
    assert banco.exists()


def test_migrate_reverte_a_0011_em_sqlite_sem_quebrar(tmp_path):
    banco = tmp_path / "dl069_f2_caixa_sqlite_reversao.sqlite3"
    resultado_ida = _rodar_manage(banco, "migrate")
    assert resultado_ida.returncode == 0, resultado_ida.stdout + resultado_ida.stderr

    resultado_volta = _rodar_manage(banco, "migrate", "livro_caixa", ANTERIOR)

    assert resultado_volta.returncode == 0, resultado_volta.stdout + resultado_volta.stderr
    assert f"Unapplying {MIGRACAO}... OK" in resultado_volta.stdout
    assert "OperationalError" not in resultado_volta.stderr
