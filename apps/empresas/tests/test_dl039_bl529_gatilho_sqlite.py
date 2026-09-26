"""Revisão da DL-039 (Fred, revisão do commit): a migração 0010
(apps/empresas/migrations/0010_bl529_gatilho_estabelecimento_empresa_cpf.py)
cria gatilhos com sintaxe exclusiva do PostgreSQL (`CREATE TRIGGER`/
`plpgsql`). `config/settings.py` permite SQLite em desenvolvimento
(`DEBUG=True` sem `DATABASE_URL`, BL-50/DE-014) — um `RunSQL`
incondicional quebrava `manage.py migrate` inteiro em SQLite:
`django.db.utils.OperationalError: near "OR": syntax error`.

Medido ANTES da correção: `env -u DATABASE_URL DEBUG=True python manage.py
migrate` (sem DATABASE_URL — cai no SQLite local de desenvolvimento)
quebrava exatamente nesta migração.

Reaproveita o padrão de `apps/core/tests/test_configuracao_producao.py`
(BL-50/BL-51, DE-014): sobe um processo `manage.py` NOVO, com o ambiente
controlado, e observa o resultado — nunca escreve na árvore do projeto
(o caminho do SQLite aponta para `tmp_path`, nunca para `BASE_DIR`).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# apps/empresas/tests/test_x.py -> apps/empresas -> apps -> raiz do repo,
# onde mora manage.py — mesmo cálculo de test_configuracao_producao.py.
BASE_DIR = Path(__file__).resolve().parents[3]

SECRET_KEY_DE_TESTE = "chave-apenas-para-verificar-migracao-sqlite-de-teste"


def _rodar_manage_migrate_em_sqlite(banco_path, timeout=120):
    ambiente = dict(os.environ)
    ambiente["DJANGO_SECRET_KEY"] = SECRET_KEY_DE_TESTE
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DEBUG"] = "True"
    # Aponta explicitamente para o arquivo temporário — nunca para
    # `BASE_DIR / "db.sqlite3"` (o padrão de `settings.py` quando
    # `DATABASE_URL` está AUSENTE). Um `DATABASE_URL` de SQLite explícito
    # exercita exatamente a mesma `ENGINE = "django.db.backends.sqlite3"`
    # que o padrão implícito usaria, sem risco de sujar a árvore do
    # projeto com um banco de teste.
    ambiente["DATABASE_URL"] = f"sqlite:///{banco_path}"

    return subprocess.run(
        [sys.executable, "manage.py", "migrate"],
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_migrate_completo_funciona_em_sqlite_sem_quebrar_na_migracao_0010(tmp_path):
    # ACHADO (fora do escopo desta etapa, registrado no relatório de
    # entrega): `apps/core/tests/test_configuracao_producao.py::test_
    # debug_true_sem_database_url_sobe_com_aviso_declarado` (BL-50/BL-51,
    # pré-existente) já deixa um `db.sqlite3` de 0 bytes em `BASE_DIR` como
    # efeito colateral de `manage.py check` sem `DATABASE_URL`. Por isso
    # este teste NÃO afirma "BASE_DIR/db.sqlite3 não existe" (a suíte
    # completa, rodando os dois arquivos, tornaria essa afirmação instável
    # e dependente de ORDEM) — em vez disso, prova que ESTE subprocesso
    # específico não TOCA nesse arquivo: aponta `DATABASE_URL` explicitamente
    # para `tmp_path`, e confirma que o mtime de um eventual `db.sqlite3`
    # pré-existente em `BASE_DIR` não muda.
    marcador_base_dir = BASE_DIR / "db.sqlite3"
    mtime_antes = marcador_base_dir.stat().st_mtime if marcador_base_dir.exists() else None

    banco = tmp_path / "dl039_sqlite_teste.sqlite3"

    resultado = _rodar_manage_migrate_em_sqlite(banco)

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "empresas.0010_bl529_gatilho_estabelecimento_empresa_cpf... OK" in resultado.stdout
    assert "OperationalError" not in resultado.stderr
    assert banco.exists()

    mtime_depois = marcador_base_dir.stat().st_mtime if marcador_base_dir.exists() else None
    assert mtime_depois == mtime_antes, (
        "este subprocesso não deveria ter tocado em BASE_DIR/db.sqlite3"
    )


def test_migrate_reverte_a_0010_em_sqlite_sem_quebrar(tmp_path):
    # A migração completa (para trás, até a 0009) também não pode quebrar
    # em SQLite — a função de reversão tem a MESMA guarda de vendor.
    banco = tmp_path / "dl039_sqlite_reversao.sqlite3"
    resultado_ida = _rodar_manage_migrate_em_sqlite(banco)
    assert resultado_ida.returncode == 0, resultado_ida.stdout + resultado_ida.stderr

    ambiente = dict(os.environ)
    ambiente["DJANGO_SECRET_KEY"] = SECRET_KEY_DE_TESTE
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DEBUG"] = "True"
    ambiente["DATABASE_URL"] = f"sqlite:///{banco}"

    resultado_volta = subprocess.run(
        [sys.executable, "manage.py", "migrate", "empresas", "0009"],
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert resultado_volta.returncode == 0, resultado_volta.stdout + resultado_volta.stderr
    assert "Unapplying empresas.0010_bl529_gatilho_estabelecimento_empresa_cpf... OK" in (
        resultado_volta.stdout
    )
    assert "OperationalError" not in resultado_volta.stderr
