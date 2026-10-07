# DL-069, fatia 1 — o lançamento do livro-caixa passa a ser imutável NO BANCO.
#
# POR QUÊ. `LancamentoCaixa.save()`/`delete()` já recusam alteração e exclusão
# (`LancamentoCaixaImutavelError`, apps/livro_caixa/models.py), e o estorno é um
# lançamento NOVO. Mas isso só vale para quem passa pelo modelo: um
# `QuerySet.update()`, um `QuerySet.delete()` num script, uma migração de dados
# ou um SQL de manutenção reescrevem ou apagam o livro que alimenta o carnê-leão,
# sem rastro. Mesma classe de falha que a DL-052 fechou na contabilidade.
#
# PADRÃO SEGUIDO. Cópia deliberada da migração 0013 de `contabilidade`
# (gatilho `BEFORE UPDATE OR DELETE ... FOR EACH ROW`, `RAISE EXCEPTION ... USING
# ERRCODE = '23514', CONSTRAINT = '<nome>'`, `RunPython` com no-op fora do
# PostgreSQL, reversa com `DROP ... IF EXISTS`) e da técnica da 0017
# (`to_jsonb(NEW) - <colunas permitidas> = to_jsonb(OLD) - <colunas permitidas>`,
# que cobre também colunas acrescentadas no futuro: coluna nova nasce imutável,
# sem ninguém precisar lembrar de editar o gatilho).
#
# O QUE ESTA MIGRAÇÃO FAZ (só PostgreSQL; em SQLite é no-op — mesmo LIMITE
# ACEITO e declarado da 0009 e da 0013 de `contabilidade`: produção nunca roda
# SQLite, `config/settings.py` recusa subir assim com `DEBUG=False`):
#
# 1. `LancamentoCaixa` (`livro_caixa_lancamentocaixa`): recusa TODO UPDATE e todo
#    DELETE, sem exceção. Medido em 07/10/2026: nenhum caminho do produto faz
#    UPDATE ou DELETE nessa tabela depois do INSERT — todas as chaves
#    estrangeiras que apontam para ela ou saem dela são PROTECT (nenhum
#    `SET_NULL`/`CASCADE` emite UPDATE/DELETE), e o admin não tem permissão de
#    alterar nem apagar. Restrição: `lancamento_caixa_imutavel`.
#
# 2. `FechamentoMesCaixa` (`livro_caixa_fechamentomescaixa`): recusa todo DELETE
#    (reabrir NÃO apaga a linha: muda `estado`) e só aceita o UPDATE que um dos
#    dois serviços faz. As colunas que cada um escreve foram LIDAS em
#    `apps/livro_caixa/services.py`:
#
#    - ENCERRAR um mês que já teve linha (`encerrar_mes_caixa`, services.py:1167-1170,
#      `save(update_fields=["estado", "fechado_em", "fechado_por"])`):
#      `estado` (aberto -> encerrado), `fechado_em` e `fechado_por`
#      (coluna `fechado_por_id`). O primeiro encerramento é um INSERT
#      (services.py:1154-1163) e não passa por este gatilho.
#    - REABRIR (`_reabrir_linha`, services.py:1250-1254, chamada pela reabertura
#      simples e por cada mês da cascata da DL-054, services.py:1398):
#      `estado` (encerrado -> aberto), `reaberto_em`, `reaberto_por`
#      (coluna `reaberto_por_id`) e `motivo_reabertura`.
#
#    Nenhum outro UPDATE de `FechamentoMesCaixa` existe no produto (nem no admin,
#    que não o registra). Qualquer outra coluna — `empresa_id`, `ano`, `mes`,
#    `criado_em` e as que vierem a existir — fica imutável pela técnica `to_jsonb`.
#
#    DECISÃO ALÉM DA LISTA DE COLUNAS (registrada no relatório da fatia): as
#    colunas permitidas são amarradas à TRANSIÇÃO que as escreve, porque o plano
#    lista como cenário negativo "trocar `fechado_por` ... por fora do serviço".
#    Se a lista valesse sozinha, trocar `fechado_por` num mês encerrado, ou
#    apagar `motivo_reabertura`, passaria. Então:
#
#    - `aberto -> encerrado`: só `estado`, `fechado_em`, `fechado_por_id` mudam;
#    - `encerrado -> aberto`: só `estado`, `reaberto_em`, `reaberto_por_id` e
#      `motivo_reabertura` mudam;
#    - sem mudança de `estado`, nenhuma coluna muda (UPDATE que regrava os
#      mesmos valores é aceito: não altera nada).
#
#    Todo UPDATE dos dois serviços é uma dessas duas transições (encerrar recusa
#    mês já encerrado; reabrir recusa mês já aberto), então o produto não perde
#    nada. Restrição: `fechamento_mes_caixa_imutavel`.
#
# LIMITE DECLARADO (o mesmo do BL-569). As travas protegem contra escrita
# ACIDENTAL, não contra quem tem acesso de dono ao banco: `TRUNCATE` não aciona
# gatilho de linha, e quem pode `ALTER TABLE ... DISABLE TRIGGER` as desliga.
# Restrição de papéis do PostgreSQL é assunto de implantação, não desta migração.
#
# O GATILHO VÊ COLUNAS, NÃO A TRILHA (A3 da auditoria da fatia 1). Um UPDATE por
# SQL que faça uma reabertura COMPLETA (`encerrado→aberto` com `reaberto_em`,
# `reaberto_por_id` e motivo preenchidos) passa: é indistinguível, para o
# banco, da reabertura do serviço, mas não grava trilha. Contra escrita
# acidental isto basta (uma reabertura parcial é recusada aqui ou pelo CHECK
# `fechamento_mes_caixa_reabertura_completa`); contra quem reabre por SQL de
# propósito, é o limite acima.
#
# NENHUMA PORTA DO PRODUTO FAZ UPDATE/DELETE NESTAS TABELAS por fora das duas
# transições, por isso a recusa nunca chega ao usuário hoje. As mensagens estão
# registradas em `MENSAGENS_DE_RESTRICAO_DE_GATILHO`, mas NENHUMA verificação
# automática exige esse registro (A1). Quem criar uma tela que altere estas
# tabelas precisa traduzir a recusa com `restricao_como_400`, ou ela vira 500.
#
# EFEITO EM RESTAURAÇÃO DE BACKUP. `pg_restore --data-only` de um backup só de
# dados regrava linhas por INSERT, que o gatilho não alcança; mas uma carga que
# faça UPDATE/DELETE nestas tabelas (por exemplo, sobrescrever um banco já
# populado) passa a exigir `--disable-triggers` (e papel de superusuário para
# isso). O mesmo limite já declarado para a contabilidade (PE-07).
#
# `RAISE ... USING ERRCODE = '23514', CONSTRAINT = '<nome>'` faz
# `IntegrityError.__cause__.diag.constraint_name` chegar ao Django com um nome
# ESTÁVEL, registrado em `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_GATILHO`.
# `%` do `RAISE` do plpgsql pode ser escrito simples: `schema_editor.execute(sql,
# params=None)` não passa a string por placeholders do driver.
#
# Custo: o gatilho só dispara em UPDATE e DELETE; o INSERT (o caminho quente do
# livro) não paga nada.
#
# Dados: nenhum dado é lido nem alterado; a migração só cria funções e gatilhos.
# Reversão: `migrate livro_caixa 0010` remove gatilhos e funções, sem perda de
# dado.

from django.db import migrations

_CRIAR_GATILHOS_SQL = """
-- Espelha LancamentoCaixa.save/delete (apps/livro_caixa/models.py): lançamento
-- efetivado nunca se edita nem se apaga; corrige-se por estorno.
CREATE OR REPLACE FUNCTION livro_caixa_recusar_alteracao_do_lancamento()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION
        'Lançamento do livro-caixa não pode ser alterado nem excluído (% do lançamento %); '
        'registre um estorno.', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'lancamento_caixa_imutavel';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lancamento_caixa_imutavel
    BEFORE UPDATE OR DELETE ON livro_caixa_lancamentocaixa
    FOR EACH ROW
    EXECUTE FUNCTION livro_caixa_recusar_alteracao_do_lancamento();

-- Fechamento de mês: nunca se apaga; só encerrar e reabrir o atualizam, e cada
-- um mexe só nas colunas que o serviço escreve (ver o cabeçalho da migração).
CREATE OR REPLACE FUNCTION livro_caixa_recusar_alteracao_do_fechamento()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- Regravar os mesmos valores não altera nada.
        IF to_jsonb(NEW) = to_jsonb(OLD) THEN
            RETURN NEW;
        END IF;

        -- `encerrar_mes_caixa` sobre mês reaberto (services.py:1167-1170).
        IF OLD.estado = 'aberto' AND NEW.estado = 'encerrado'
           AND (to_jsonb(NEW) - ARRAY['estado', 'fechado_em', 'fechado_por_id'])
             = (to_jsonb(OLD) - ARRAY['estado', 'fechado_em', 'fechado_por_id'])
        THEN
            RETURN NEW;
        END IF;

        -- `_reabrir_linha`, reabertura simples e cascata (services.py:1250-1254).
        IF OLD.estado = 'encerrado' AND NEW.estado = 'aberto'
           AND (to_jsonb(NEW) - ARRAY['estado', 'reaberto_em', 'reaberto_por_id', 'motivo_reabertura'])
             = (to_jsonb(OLD) - ARRAY['estado', 'reaberto_em', 'reaberto_por_id', 'motivo_reabertura'])
        THEN
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION
        'Fechamento de mês do livro-caixa não pode ser excluído, e só muda pelo encerramento '
        'ou pela reabertura do mês (% do fechamento %).', TG_OP, OLD.id
        USING ERRCODE = '23514',
              CONSTRAINT = 'fechamento_mes_caixa_imutavel';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_fechamento_mes_caixa_imutavel
    BEFORE UPDATE OR DELETE ON livro_caixa_fechamentomescaixa
    FOR EACH ROW
    EXECUTE FUNCTION livro_caixa_recusar_alteracao_do_fechamento();
"""

_REMOVER_GATILHOS_SQL = """
DROP TRIGGER IF EXISTS trg_fechamento_mes_caixa_imutavel ON livro_caixa_fechamentomescaixa;
DROP TRIGGER IF EXISTS trg_lancamento_caixa_imutavel ON livro_caixa_lancamentocaixa;
DROP FUNCTION IF EXISTS livro_caixa_recusar_alteracao_do_fechamento();
DROP FUNCTION IF EXISTS livro_caixa_recusar_alteracao_do_lancamento();
"""


def _criar_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_GATILHOS_SQL, params=None)


def _remover_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHOS_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("livro_caixa", "0010_dl053_fechamento_de_mes_do_livro_caixa"),
    ]

    operations = [
        migrations.RunPython(_criar_gatilhos, _remover_gatilhos),
    ]
