#!/bin/bash
# Gancho de início de sessão do Claude Code (DL-014).
#
# Duas funções, e a ordem importa:
#
# 1. LEITURA OBRIGATÓRIA. Tudo o que este script imprime entra no contexto
#    da sessão antes da primeira ação do agente. Por isso ele imprime o
#    AGENTS.md inteiro e o "Próximo passo" de docs/agents/estado.md. Não é
#    pedido para o agente ler as regras — é o mecanismo que as coloca na
#    frente dele. Pedido é comportamental; isto é técnico.
#
# 2. AMBIENTE PRONTO. Instala as dependências e sobe o PostgreSQL local, para
#    que `ruff`, `pytest` e `manage.py` funcionem numa sessão nova sem que o
#    agente tenha de improvisar um ambiente à parte — que foi o que aconteceu
#    nas primeiras sessões deste projeto.
#
# Roda só no Claude Code na web (CLAUDE_CODE_REMOTE=true). Local, não faz
# nada. É idempotente: pode rodar quantas vezes for preciso.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

RAIZ="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
cd "$RAIZ"

aviso() { printf '\n[session-start] AVISO: %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# 1. Leitura obrigatória — vai para o contexto do agente.
# ---------------------------------------------------------------------------
cat <<'CABECALHO'
================================================================================
DATALEDGER — LEITURA OBRIGATÓRIA ANTES DE QUALQUER ALTERAÇÃO
================================================================================
Este bloco é injetado automaticamente no início de toda sessão (DL-014). As
regras abaixo são do AGENTS.md e PREVALECEM sobre qualquer preferência de
estilo. Depois delas vem o "Próximo passo" de docs/agents/estado.md, que é a
fonte única do estado do projeto.

Resumo do que é imposto tecnicamente, e não só pedido:
  - PR sem a caixa "Li o AGENTS.md" marcada e sem plano DL citado REPROVA na CI
    (workflow "Regras do projeto").
  - Etapa com plano que não apareça no README e em estado.md REPROVA na CI
    (apps/core/tests/test_documentacao_do_estado.py).
  - A branch main só recebe alteração por PR com as verificações verdes.
================================================================================

CABECALHO
cat AGENTS.md
printf '\n\n================================================================================\nPRÓXIMO PASSO (docs/agents/estado.md)\n================================================================================\n'
awk '/^## Próximo passo/{f=1} /^## Estado do repositório/{f=0} f' docs/agents/estado.md
printf '\n================================================================================\nFim da leitura obrigatória. Registre estado em docs/agents/estado.md ao concluir.\n================================================================================\n'

# ---------------------------------------------------------------------------
# 2. Python: a CI roda em 3.14; usar a versão mais próxima disponível.
# ---------------------------------------------------------------------------
PY=""
for candidato in python3.14 python3.13 python3.12; do
  if command -v "$candidato" >/dev/null 2>&1; then PY="$candidato"; break; fi
done
if [ -z "$PY" ]; then
  aviso "nenhum Python 3.12+ encontrado; Django 6.1 exige 3.12 ou superior (DE-007). Dependências NÃO instaladas."
else
  if [ ! -x .venv/bin/python ]; then
    if command -v uv >/dev/null 2>&1; then
      uv venv --python "$PY" .venv >/dev/null
    else
      "$PY" -m venv .venv
    fi
  fi
  if command -v uv >/dev/null 2>&1; then
    uv pip install --python .venv/bin/python -q -r requirements/dev.txt
  else
    .venv/bin/python -m pip install -q -r requirements/dev.txt
  fi
  echo "export PATH=\"$RAIZ/.venv/bin:\$PATH\"" >> "${CLAUDE_ENV_FILE:-/dev/null}"
  echo "[session-start] dependências instaladas em .venv com $($PY --version 2>&1)."
fi

# ---------------------------------------------------------------------------
# 3. Variáveis mínimas de desenvolvimento. Valores públicos e descartáveis:
#    servem só para a suíte rodar. Produção usa o ambiente real (BL-50/51).
# ---------------------------------------------------------------------------
{
  echo 'export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-chave-apenas-para-sessao-de-desenvolvimento}"'
  echo 'export DEBUG="${DEBUG:-True}"'
  echo 'export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-localhost,127.0.0.1}"'
} >> "${CLAUDE_ENV_FILE:-/dev/null}"

# ---------------------------------------------------------------------------
# 4. PostgreSQL local, para pytest e migrate. Melhor esforço: se não houver
#    cluster, o agente é avisado em vez de descobrir na primeira falha.
#    Usuário e senha coincidem com .env.example — desenvolvimento apenas.
# ---------------------------------------------------------------------------
if command -v pg_lsclusters >/dev/null 2>&1; then
  if pg_lsclusters 2>/dev/null | grep -q "down"; then
    pg_ctlcluster 16 main start 2>/dev/null || aviso "não consegui iniciar o cluster PostgreSQL 16/main."
  fi
fi
if pg_isready -h localhost -p 5432 -q 2>/dev/null; then
  sudo -n -u postgres psql -v ON_ERROR_STOP=1 -q <<'SQL' 2>/dev/null || aviso "PostgreSQL ativo, mas não consegui criar usuário/banco 'dataledger'."
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'dataledger') THEN
    CREATE ROLE dataledger LOGIN PASSWORD 'dataledger' CREATEDB;
  ELSE
    ALTER ROLE dataledger WITH LOGIN PASSWORD 'dataledger' CREATEDB;
  END IF;
END $$;
SQL
  if ! sudo -n -u postgres psql -tAq -c "select 1 from pg_database where datname='dataledger'" 2>/dev/null | grep -q 1; then
    sudo -n -u postgres createdb -O dataledger dataledger 2>/dev/null || aviso "não consegui criar o banco 'dataledger'."
  fi
  echo 'export DATABASE_URL="${DATABASE_URL:-postgres://dataledger:dataledger@localhost:5432/dataledger}"' >> "${CLAUDE_ENV_FILE:-/dev/null}"
  echo "[session-start] PostgreSQL pronto em localhost:5432 (banco dataledger)."
else
  aviso "PostgreSQL não está acessível em localhost:5432. pytest e migrate vão falhar até DATABASE_URL apontar para um PostgreSQL."
fi

echo "[session-start] concluído."
