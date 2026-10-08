"""DL-069, fatia 2 — a migração 0023 de `contabilidade` não quebra o SQLite.

As migrações de gatilho são `RunPython` com no-op fora do PostgreSQL (a
sintaxe `CREATE TRIGGER`/`plpgsql` é exclusiva do PostgreSQL, e
`config/settings.py` permite SQLite em desenvolvimento). Este teste prova o
contrato no formato de
`apps/empresas/tests/test_dl039_bl529_gatilho_sqlite.py`: `manage.py migrate`
completo (ida e volta) funciona num SQLite TEMPORÁRIO — nunca na árvore do
projeto. Os testes de comportamento do gatilho em si são pulados fora do
PostgreSQL (ver `test_dl069_periodo_encerrado_recusa_insert.py`); aqui se
prova só o no-op da migração.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# apps/contabilidade/tests/test_x.py -> apps/contabilidade -> apps -> raiz do
# repo, onde mora manage.py — mesmo cálculo de test_dl039_bl529_gatilho_sqlite.
BASE_DIR = Path(__file__).resolve().parents[3]

SECRET_KEY_DE_TESTE = "chave-apenas-para-verificar-migracao-sqlite-de-teste"
MIGRACAO = "contabilidade.0023_dl069_periodo_encerrado_recusa_insert"
ANTERIOR = "0022"


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


def test_migrate_completo_funciona_em_sqlite_sem_quebrar_na_migracao_0023(tmp_path):
    banco = tmp_path / "dl069_f2_sqlite_teste.sqlite3"

    resultado = _rodar_manage(banco, "migrate")

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert f"Applying {MIGRACAO}... OK" in resultado.stdout
    assert "OperationalError" not in resultado.stderr
    assert banco.exists()


def test_migrate_reverte_a_0022_em_sqlite_sem_quebrar(tmp_path):
    # A reversão tem a MESMA guarda de vendor: não emite SQL nenhum fora do
    # PostgreSQL e não pode quebrar em SQLite.
    banco = tmp_path / "dl069_f2_sqlite_reversao.sqlite3"
    resultado_ida = _rodar_manage(banco, "migrate")
    assert resultado_ida.returncode == 0, resultado_ida.stdout + resultado_ida.stderr

    resultado_volta = _rodar_manage(banco, "migrate", "contabilidade", ANTERIOR)

    assert resultado_volta.returncode == 0, resultado_volta.stdout + resultado_volta.stderr
    assert f"Unapplying {MIGRACAO}... OK" in resultado_volta.stdout
    assert "OperationalError" not in resultado_volta.stderr
