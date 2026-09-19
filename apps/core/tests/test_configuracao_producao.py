"""Testes de BL-50 e BL-51 (DE-014): a aplicação recusa subir com banco
inadequado para produção, e sobe sem avisos de segurança quando corretamente
configurada para produção.

`config/settings.py` valida a escolha de banco e ativa os cabeçalhos de
segurança em código de MÓDULO — roda uma única vez, na importação das
configurações do Django. Isso torna `override_settings` inadequado aqui: uma
vez que o processo de teste já importou `config.settings` com um
`DATABASES` válido, não há como "reimportar" o módulo com outra combinação
de DEBUG/DATABASE_URL sem efeitos colaterais no restante da suíte (o
auditor já registrou que ligar SECURE_SSL_REDIRECT no meio da suíte, por
exemplo, derruba testes de cliente por redirecionamento).

Por isso cada cenário sobe um processo Python **novo**, com o ambiente
exatamente como estaria numa implantação real, e observamos o resultado
(código de saída e mensagem) — o mesmo que aconteceria ao iniciar o
servidor de verdade.
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

# apps/core/tests/test_x.py -> apps/core -> apps -> raiz do repositório,
# onde mora manage.py.
BASE_DIR = Path(__file__).resolve().parents[3]

# Segredo só para permitir a subida do processo nos cenários que não testam
# a força do SECRET_KEY; nunca é usado para proteger dado real.
SECRET_KEY_DE_TESTE = "chave-apenas-para-verificar-subida-do-processo-de-teste"


def _rodar_manage_check(overrides, deploy=False, timeout=60):
    """Sobe `manage.py check` num processo separado com o ambiente indicado.

    `overrides` substitui/inclui variáveis no ambiente do subprocesso.
    Partimos de uma cópia do ambiente do processo de teste (para preservar
    PATH, HOME etc.), mas sempre forçamos `DATABASE_URL=""` antes de aplicar
    `overrides` — string vazia sobrepõe o que `django-environ` leria do
    `.env` da raiz do repositório, e cai no branch "ausente" da guarda
    (`if not _database_url`). Sem isso, os testes de "sem DATABASE_URL"
    passariam falsamente porque o `.env` da máquina de teste define a
    variável para o Postgres do docker-compose.
    """
    ambiente = dict(os.environ)
    ambiente["DJANGO_SECRET_KEY"] = SECRET_KEY_DE_TESTE
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DATABASE_URL"] = ""
    ambiente.update(overrides)

    comando = [sys.executable, "manage.py", "check"]
    if deploy:
        comando.append("--deploy")

    return subprocess.run(
        comando,
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def test_debug_false_sem_database_url_recusa_subir():
    """Critério de aceite 1: sem DATABASE_URL e fora de desenvolvimento, a
    aplicação não pode cair em SQLite em silêncio — precisa recusar subir
    com mensagem que diga o que configurar."""
    resultado = _rodar_manage_check({"DEBUG": "False"})

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DATABASE_URL" in resultado.stderr
    assert "PostgreSQL" in resultado.stderr


def test_debug_false_com_database_url_sqlite_recusa_subir(tmp_path):
    """Critério de aceite 2: configurar explicitamente SQLite em produção é
    tão grave quanto não configurar nada — também deve recusar subir.

    O caminho do banco aponta para `tmp_path`, e não para a raiz do
    repositório, de propósito. A primeira versão deste teste usava
    `BASE_DIR / "nao_deve_ser_criado.sqlite3"`: enquanto a guarda funciona o
    arquivo nunca nasce, mas basta alguém desligar a guarda — numa
    refatoração, ou num teste de mutação como o que o `arquiteto-senior`
    rodou em 2026-09-13 — para o Django criar o arquivo **dentro da árvore
    versionada**. Foi exatamente o que aconteceu.

    Um arquivo SQLite solto no repositório é risco real num sistema
    contábil: é um banco de dados inteiro, e num descuido vai parar num
    commit com dado dentro. Teste não escreve na árvore do projeto.
    """
    banco = tmp_path / "nao_deve_ser_criado.sqlite3"
    resultado = _rodar_manage_check({"DEBUG": "False", "DATABASE_URL": f"sqlite:///{banco}"})

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "ImproperlyConfigured" in resultado.stderr
    assert "SQLite" in resultado.stderr
    # A recusa é na validação de settings, então o arquivo de banco nunca
    # chega a ser criado no disco.
    assert not banco.exists()


def test_debug_true_sem_database_url_sobe_com_aviso_declarado():
    """Critério de aceite 3: em desenvolvimento, SQLite continua permitido,
    mas o aviso precisa aparecer — não pode ser uma escolha silenciosa."""
    resultado = _rodar_manage_check({"DEBUG": "True"})

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "RuntimeWarning" in resultado.stderr
    assert "SQLite" in resultado.stderr
    assert "db.sqlite3" not in resultado.stdout


def test_debug_false_com_postgres_sobe_sem_erro():
    """Regressão: a validação não pode recusar um PostgreSQL legítimo — só
    SQLite (ou ausência de configuração) é que deve ser bloqueado."""
    resultado = _rodar_manage_check(
        {
            "DEBUG": "False",
            "DATABASE_URL": "postgres://usuario:senha@host:5432/banco",
        }
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_check_deploy_com_debug_false_nao_gera_avisos():
    """Critério de aceite 4 (BL-51): `check --deploy` com DEBUG=False deve
    sair sem nenhum aviso de segurança, dado um SECRET_KEY forte e um banco
    PostgreSQL configurado. Não é preciso um PostgreSQL de verdade
    respondendo: `check` valida a configuração declarada, não a
    conectividade."""
    segredo_forte = secrets.token_urlsafe(64)

    resultado = _rodar_manage_check(
        {
            "DEBUG": "False",
            "DATABASE_URL": "postgres://usuario:senha@host:5432/banco",
            "DJANGO_SECRET_KEY": segredo_forte,
            "DJANGO_ALLOWED_HOSTS": "app.exemplo.com.br",
        },
        deploy=True,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "System check identified no issues" in resultado.stdout
    assert "WARNINGS" not in resultado.stdout
