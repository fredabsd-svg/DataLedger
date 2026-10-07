# DL-069, fatia 2 — mês encerrado recusa INSERT de lançamento NO BANCO
# (item 2 do escopo; os itens 1, 3 e 4, da contabilidade, são a migração 0023
# de `apps.contabilidade`).
#
# POR QUÊ. `criar_lancamento_caixa` já recusa lançamento em mês encerrado e em
# mês anterior a um mês encerrado do mesmo ano (o encadeamento da DL-054 —
# `_recusar_se_mes_caixa_encerrado`, `apps/livro_caixa/services.py:569-639`).
# Mas isso só vale para quem passa pelo serviço: um `objects.create()`, um
# `bulk_create()`, uma migração de dados ou um SQL de manutenção gravavam
# lançamento em mês fechado, mudando o carnê-leão já entregue ao cliente sem
# rastro. Mesma classe de falha que a fatia 1 desta DL-069 fechou para
# UPDATE/DELETE em `LancamentoCaixa`.
#
# PADRÃO SEGUIDO. Cópia deliberada da migração 0011 de `livro_caixa` (fatia 1)
# e das 0013/0016 de `contabilidade` (`RAISE EXCEPTION ... USING ERRCODE =
# '23514', CONSTRAINT = '<nome>'`, `RunPython` com no-op fora do PostgreSQL,
# reversa com `DROP ... IF EXISTS`).
#
# O QUE ESTA MIGRAÇÃO FAZ (só PostgreSQL; em SQLite é no-op, mesmo LIMITE
# ACEITO e declarado da 0009/0013/0011):
#
# `BEFORE INSERT` em `livro_caixa_lancamentocaixa`
# (`trg_lancamento_caixa_so_em_mes_aberto`): recusa INSERT quando o mês do
# lançamento OU qualquer mês POSTERIOR do MESMO ano-calendário está com estado
# diferente de `aberto` (mês sem linha é aberto — decisão 3 do plano da
# DL-053). Restrição: `dl069_lancamento_caixa_so_em_mes_aberto`.
#
# A REGRA É CÓPIA LITERAL de `_recusar_se_mes_caixa_encerrado`
# (apps/livro_caixa/services.py:569-639), o trecho que `criar_lancamento_caixa`
# chama antes de gravar (services.py:835) e que `estornar_lancamento_caixa`
# alcança por ele (a data do estorno é a do original, DE-091 item 4 —
# services.py:1000-1021, então o estorno do mês encerrado é recusado como o
# lançamento):
#
#   - o segundo caso é o encadeamento do carnê-leão (DL-054, RC-148): um
#     lançamento em janeiro muda o resultado de fevereiro, e fevereiro
#     encerrado é resultado entregue que não pode mudar em silêncio. Só o ANO
#     importa — o encadeamento é anual, então mês encerrado de outro ano não
#     recusa (services.py:573-581);
#   - a leitura é `estado <> 'aberto'` (não `= 'encerrado'`): estado
#     desconhecido bloqueia, nunca libera (services.py:584-587);
#   - a mensagem nomeia o PRIMEIRO mês encerrado alcançado, e distingue "o
#     próprio mês está encerrado" de "um mês seguinte está encerrado" (e
#     lançamento de estorno), com as mesmas frases do serviço
#     (services.py:617-639) — para API/admin nunca contarem duas histórias
#     diferentes do mesmo motivo (DE-026).
#
# DECISÃO DE LOCK — o ponto de maior risco técnico do escopo (BL-456). O
# gatilho faz a MESMA leitura protegida contra corrida que o serviço faz,
# ANTES de julgar o estado: o lock consultivo COMPARTILHADO do mês e de todos
# os posteriores do ano, em ordem crescente, e só então a leitura do estado.
# É espelho exato de `_adquirir_locks_dos_meses_do_ano(exclusivo=False)` +
# `_recusar_se_mes_caixa_encerrado` (services.py:547-639).
#
# - Por que lock consultivo, e não lock de linha: o mês nasce SEM linha
#   (`FechamentoMesCaixa` só existe depois do primeiro fechamento) — ver o
#   bloco "A trava e a corrida" em services.py:270-321, que é a especificação
#   deste parágrafo. Um lançamento que lê "não há linha" e um fechamento que
#   insere a linha e commita logo em seguida não se enxergam; o lock
#   consultivo por (empresa, ano, mês) existe antes de a linha nascer.
# - A CHAVE é a MESMA de `_chave_do_lock_do_mes`
#   (services.py:339-346): `namespace (0x4C) << 56 | empresa << 16 | índice
#   do mês desde 1970`, na forma de UM bigint — mesma família de locks, mesma
#   semântica; se as duas fórmulas divergirem, as travas param de se ver (e
#   `test_dl069_mes_encerrado_recusa_insert` e os testes de corrida da DL-053/
#   DL-054 são os que avisam).
# - ORDEM, sem ciclo possível: lançamento toma os meses em ordem CRESCENTE
#   (services.py:561-563) — o gatilho repete exatamente essa ordem; encerrar
#   toma um mês só; a cascata da reabertura toma os meses em ordem crescente.
#   Pelo caminho do serviço o lock já foi tomado antes do INSERT e o gatilho
#   o re-toma na mesma transação (recebido na hora); o que o gatilho acrescenta
#   é o INSERT por FORA do serviço.
# - Em qualquer das duas ordens, ou o lançamento commita antes do fechamento
#   (ordem legítima — ele foi gravado com o mês ainda aberto) ou o fechamento
#   commita primeiro e o INSERT é recusado. O lançamento nunca termina em
#   período encerrado.
#
# O ESTORNO entra pela mesma regra porque sua `data` é a do lançamento
# original (DE-091 item 4): `estornar_lancamento_caixa` recusa estorno fora do
# mês do original, e estornar lançamento de mês encerrado exige reabrir o mês
# primeiro (RC-130) — services.py:985-1016.
#
# EFEITO EM RESTAURAÇÃO DE BACKUP. `pg_restore --data-only` que faça INSERT em
# lançamento de mês fechado passa a exigir `--disable-triggers` (super-
# usuário) — o mesmo limite declarado na fatia 1 e na contabilidade (PE-07).
#
# `RAISE ... USING ERRCODE = '23514', CONSTRAINT = '<nome>'` faz
# `IntegrityError.__cause__.diag.constraint_name` chegar ao Django com um nome
# ESTÁVEL, registrado em
# `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_GATILHO`. `%` do `RAISE` do
# plpgsql pode ser escrito simples: `schema_editor.execute(sql, params=None)`
# não passa a string por placeholders do driver.
#
# Custo: por INSERT, até 12 aquisições de lock consultivo (em memória) e UMA
# busca indexada em `fechamento_mes_caixa` por (empresa, ano, mes). O serviço
# já paga exatamente isso antes do INSERT (services.py:835).
#
# Dados: nenhum dado é lido nem alterado; a migração só cria função e gatilho.
# Reversão: `migrate livro_caixa 0011` remove gatilho e função, sem perda de
# dado.

from django.db import migrations

_CRIAR_GATILHO_SQL = """
-- Lançamento novo só em mês ABERTO, com o encadeamento anual do carnê-leão
-- (cópia literal de `_recusar_se_mes_caixa_encerrado`,
-- apps/livro_caixa/services.py:569-639).
CREATE OR REPLACE FUNCTION livro_caixa_recusar_lancamento_em_mes_encerrado()
RETURNS trigger AS $$
DECLARE
    v_ano integer;
    v_mes_do_lancamento integer;
    v_mes_corrido integer;
    v_primeiro_encerrado integer;
    v_mes_fmt text;
    v_encerrado_fmt text;
BEGIN
    v_ano := EXTRACT(YEAR FROM NEW.data)::integer;
    v_mes_do_lancamento := EXTRACT(MONTH FROM NEW.data)::integer;
    -- Mesmo formato das frases do serviço (`f"{mes:02d}/{ano}"`): "03/2026",
    -- nunca "3/2026" (auditoria R2).
    v_mes_fmt := lpad(v_mes_do_lancamento::text, 2, '0') || '/' || v_ano;

    -- Lock consultivo COMPARTILHADO do mês e dos posteriores do mesmo ano,
    -- em ordem crescente — espelho de `_adquirir_locks_dos_meses_do_ano`
    -- (services.py:547-566). A chave é a de `_chave_do_lock_do_mes`
    -- (services.py:339-346): namespace 0x4C (76) | empresa | índice do mês
    -- desde 1970. Cada `<<` e cada `|` está entre parênteses de propósito:
    -- `<<` e `|` têm a MESMA precedência no PostgreSQL e associam à esquerda.
    FOR v_mes_corrido IN v_mes_do_lancamento .. 12 LOOP
        PERFORM pg_advisory_xact_lock_shared(
            (76::bigint << 56)
            | (NEW.empresa_id::bigint << 16)
            | (((v_ano - 1970) * 12 + (v_mes_corrido - 1))::bigint)
        );
    END LOOP;

    -- Só DEPOIS do lock o estado é lido (services.py:583-613). Mês sem linha
    -- é aberto; `<> 'aberto'` bloqueia estado desconhecido também.
    SELECT mes INTO v_primeiro_encerrado
      FROM livro_caixa_fechamentomescaixa
     WHERE empresa_id = NEW.empresa_id
       AND ano = v_ano
       AND mes >= v_mes_do_lancamento
       AND estado IS DISTINCT FROM 'aberto'
     ORDER BY mes
     LIMIT 1;

    IF v_primeiro_encerrado IS NULL THEN
        RETURN NEW;
    END IF;
    v_encerrado_fmt := lpad(v_primeiro_encerrado::text, 2, '0') || '/' || v_ano;

    -- As frases abaixo reproduzem as do serviço (services.py:617-639),
    -- inclusive a separação entre estorno e lançamento comum (DE-026), menos
    -- o nome da empresa (o gatilho não o tem; o texto que o usuário vê é o
    -- registrado em `MENSAGENS_DE_RESTRICAO_DE_GATILHO`).
    IF v_primeiro_encerrado = v_mes_do_lancamento THEN
        IF NEW.estorno_de_id IS NOT NULL THEN
            RAISE EXCEPTION
                'O mês % do livro-caixa está encerrado; não é possível estornar lançamento '
                'dele. Reabra o mês (informando o motivo) para corrigir o lançamento no mês '
                'original.', v_mes_fmt
                USING ERRCODE = '23514',
                      CONSTRAINT = 'dl069_lancamento_caixa_so_em_mes_aberto';
        END IF;
        RAISE EXCEPTION
            'O mês % do livro-caixa está encerrado; não é possível gravar lançamento nele. '
            'Reabra o mês (informando o motivo) ou lance em um mês aberto.',
            v_mes_fmt
            USING ERRCODE = '23514',
                  CONSTRAINT = 'dl069_lancamento_caixa_so_em_mes_aberto';
    END IF;

    IF NEW.estorno_de_id IS NOT NULL THEN
        RAISE EXCEPTION
            'O mês % do livro-caixa está encerrado e o carnê-leão dele depende de % (o '
            'excesso de livro-caixa e o saldo passam de um mês para o seguinte no ano); não é '
            'possível estornar lançamento de % sem alterar um resultado encerrado. Reabra % '
            'e os meses encerrados seguintes do ano (informando o motivo) antes de corrigir.',
            v_encerrado_fmt, v_mes_fmt, v_mes_fmt, v_encerrado_fmt
            USING ERRCODE = '23514',
                  CONSTRAINT = 'dl069_lancamento_caixa_so_em_mes_aberto';
    END IF;
    RAISE EXCEPTION
        'O mês % do livro-caixa está encerrado e o carnê-leão dele depende de % (o excesso '
        'de livro-caixa e o saldo passam de um mês para o seguinte no ano); não é possível '
        'gravar lançamento em % sem alterar um resultado encerrado. Reabra % e os meses '
        'encerrados seguintes do ano (informando o motivo) antes de corrigir.',
        v_encerrado_fmt, v_mes_fmt, v_mes_fmt, v_encerrado_fmt
        USING ERRCODE = '23514',
              CONSTRAINT = 'dl069_lancamento_caixa_so_em_mes_aberto';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lancamento_caixa_so_em_mes_aberto
    BEFORE INSERT ON livro_caixa_lancamentocaixa
    FOR EACH ROW
    EXECUTE FUNCTION livro_caixa_recusar_lancamento_em_mes_encerrado();
"""

_REMOVER_GATILHO_SQL = """
DROP TRIGGER IF EXISTS trg_lancamento_caixa_so_em_mes_aberto ON livro_caixa_lancamentocaixa;
DROP FUNCTION IF EXISTS livro_caixa_recusar_lancamento_em_mes_encerrado();
"""


def _criar_gatilho(apps, schema_editor):
    # NO-OP fora do PostgreSQL (ver o cabeçalho): em SQLite as travas não
    # existem e a migração declara isso não emitindo SQL nenhum.
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_GATILHO_SQL, params=None)


def _remover_gatilho(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHO_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("livro_caixa", "0011_dl069_livro_caixa_imutavel_no_banco"),
    ]

    operations = [
        migrations.RunPython(_criar_gatilho, _remover_gatilho),
    ]
