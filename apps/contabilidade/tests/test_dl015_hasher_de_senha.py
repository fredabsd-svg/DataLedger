"""Achado novo 4 da auditoria da DL-015, rodada 3 (DE-024 §3): a condição
dupla que troca o hasher de senha para MD5 exclusivamente em teste
(`config/settings.py`, achado da rodada 2 / BL-80) não tinha teste nenhum. O
auditor mutou a condição de duas formas e a suíte inteira passou:

- M21: `if "PYTEST_VERSION" in os.environ and DEBUG:` -> `if DEBUG:`
- M22: a mesma condição -> `if True:`

Com qualquer uma das duas, TODA senha do sistema, em QUALQUER ambiente,
passaria a ser guardada em MD5 puro — sem defesa nenhuma contra força
bruta — e nada acusava.

Este teste mede as QUATRO combinações de `PYTEST_VERSION` presente/ausente
× `DEBUG` verdadeiro/falso, cada uma em um SUBPROCESSO isolado: o hasher
fraco só pode aparecer quando as DUAS condições são verdadeiras ao mesmo
tempo. Precisa de subprocesso porque `config.settings` só é importado (e
`PASSWORD_HASHERS` só é decidido) UMA vez por processo — testar as quatro
combinações no mesmo processo Python leria sempre o valor da primeira
importação.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ_DO_REPOSITORIO = Path(__file__).resolve().parents[3]
HASHER_FRACO = "django.contrib.auth.hashers.MD5PasswordHasher"

_SCRIPT_QUE_IMPRIME_O_PRIMEIRO_HASHER = (
    "import django; django.setup(); "
    "from django.conf import settings; "
    "print(settings.PASSWORD_HASHERS[0])"
)


@pytest.mark.parametrize(
    ("pytest_version_presente", "debug"),
    [
        (True, True),  # a ÚNICA combinação em que o hasher fraco é esperado
        (True, False),
        (False, True),
        (False, False),
    ],
)
def test_hasher_de_senha_fraco_so_na_combinacao_dupla(pytest_version_presente, debug):
    ambiente = os.environ.copy()
    ambiente["DJANGO_SETTINGS_MODULE"] = "config.settings"
    ambiente["DJANGO_SECRET_KEY"] = "chave-apenas-para-este-subprocesso-de-teste"
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DEBUG"] = "True" if debug else "False"
    if debug:
        # Em DEBUG=True, DATABASE_URL ausente é aceito (cai no SQLite local,
        # com aviso) — não precisamos de um Postgres real para este teste,
        # que só importa `config.settings`, nunca conecta no banco.
        ambiente.pop("DATABASE_URL", None)
    else:
        # Em DEBUG=False, a checagem de banco EXIGE uma URL PostgreSQL (não
        # aceita SQLite nem ausência) — uma URL sintaticamente válida basta,
        # porque só o ENGINE é inspecionado na subida; nenhuma conexão real
        # é aberta por este teste.
        ambiente["DATABASE_URL"] = "postgres://usuario:senha@localhost:5432/banco_de_teste"
    if pytest_version_presente:
        ambiente["PYTEST_VERSION"] = "8.0.0"
    else:
        ambiente.pop("PYTEST_VERSION", None)

    resultado = subprocess.run(
        [sys.executable, "-c", _SCRIPT_QUE_IMPRIME_O_PRIMEIRO_HASHER],
        env=ambiente,
        capture_output=True,
        text=True,
        cwd=str(RAIZ_DO_REPOSITORIO),
    )

    assert resultado.returncode == 0, (
        f"Subprocesso falhou ao importar as configurações "
        f"(PYTEST_VERSION={pytest_version_presente}, DEBUG={debug}):\n{resultado.stderr}"
    )
    primeiro_hasher = resultado.stdout.strip()

    espera_hasher_fraco = pytest_version_presente and debug
    if espera_hasher_fraco:
        assert primeiro_hasher == HASHER_FRACO
    else:
        assert primeiro_hasher != HASHER_FRACO
