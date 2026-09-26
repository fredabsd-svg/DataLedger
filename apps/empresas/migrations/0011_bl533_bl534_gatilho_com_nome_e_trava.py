# Achados D1 e D2 da auditoria da DL-039 rodada 1
# (docs/auditorias/2026-09-26-dl-039-rodada-1.md) — BL-533 e BL-534
# (docs/projeto/backlog.md). NÃO edita a migração 0010 (já está em branch
# compartilhada) — recria as MESMAS duas funções com `CREATE OR REPLACE
# FUNCTION` (os gatilhos em si, criados pela 0010, continuam apontando
# para essas funções pelo NOME; não é preciso recriar `CREATE TRIGGER`).
#
# D1 (BL-533): o `RAISE EXCEPTION` dos dois gatilhos não informava
# `CONSTRAINT`, então `exc.__cause__.diag.constraint_name` chegava vazio
# ao Django e `apps.core.restricoes._nome_da_constraint_violada`
# (usada por `restricao_como_400`) não tinha como traduzir — o gatilho
# disparando virava 500 (admin) ou 500 (API), quando deveria virar erro de
# formulário (200, admin) ou 400 (API). Agora os dois `RAISE EXCEPTION`
# levam `CONSTRAINT = '<nome>'` — os NOMES (não são `Meta.constraints` do
# Django; são pseudo-restrições só do gatilho, registradas em
# `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_GATILHO`, um registro
# SEPARADO de `MENSAGENS_DE_RESTRICAO` de propósito — aquele é varrido por
# `apps/core/tests/test_dl019_varredura_de_restricoes.py` contra
# `Meta.constraints` REAIS de modelo, e um nome de gatilho SQL não é
# metadado do ORM; misturá-los quebraria essa varredura em vão):
#
# - `estabelecimento_empresa_nao_e_cpf` (gatilho de Estabelecimento).
# - `empresa_transicao_cpf_com_estabelecimento` (gatilho de Empresa).
#
# D2 (BL-534): o comentário da 0010 afirmava que os dois gatilhos "fecham
# a corrida" entre criar estabelecimento e trocar a empresa para CPF —
# **era falso**, e o auditor mediu: com duas conexões reais, a trava
# automática de FK do INSERT (`FOR KEY SHARE`) não conflita com a do
# UPDATE de coluna comum (`FOR NO KEY UPDATE`), então as duas transações
# corriam em paralelo sem nunca se travarem uma na outra, e as duas
# confirmavam — empresa CPF com estabelecimento gravada, exatamente o
# estado que os gatilhos existem para impedir.
#
# Correção: o gatilho de Estabelecimento agora lê a empresa com `SELECT
# ... FOR SHARE`. `FOR SHARE` CONFLITA com `FOR NO KEY UPDATE` (a trava
# implícita de um `UPDATE` de coluna comum, como `tipo_inscricao`) — as
# duas ordens passam a serializar:
#
# - Se o INSERT do estabelecimento roda PRIMEIRO e ainda não confirmou, o
#   `FOR SHARE` já está preso na linha da empresa; o `UPDATE` de
#   `tipo_inscricao` para CPF, na outra transação, ESPERA até o INSERT
#   confirmar ou desistir. Se confirmar, o gatilho de transição vê o
#   estabelecimento (já committed) e recusa a mudança de tipo.
# - Se o UPDATE roda PRIMEIRO e ainda não confirmou, o `FOR SHARE` do
#   gatilho de Estabelecimento ESPERA até o UPDATE confirmar ou desistir.
#   Se confirmar, o `SELECT ... FOR SHARE` enxerga `tipo_inscricao='CPF'`
#   já committed, e o gatilho de Estabelecimento recusa o INSERT.
#
# Em QUALQUER ordem, uma das duas transações sempre perde — nunca as duas
# confirmam com o estado inconsistente. A perdedora recebe a MESMA
# `IntegrityError`/`RAISE EXCEPTION` de sempre (D1 cuida de traduzir isso
# em erro legível, nunca 500). `FOR SHARE` (não `FOR UPDATE`): duas
# leituras concorrentes do gatilho de Estabelecimento (dois INSERTs de
# estabelecimentos DIFERENTES para a MESMA empresa, nenhum deles mudando
# `tipo_inscricao`) continuam livres para coexistir — só quem quer
# ESCREVER a linha da empresa (o UPDATE de tipo) precisa esperar.
#
# Migração REVERSÍVEL para a versão da 0010: a função de volta recria as
# DUAS funções com o corpo EXATO da 0010 (sem `CONSTRAINT`, sem `FOR
# SHARE`) — `migrate empresas 0010` restaura o comportamento anterior
# (com as ressalvas D1/D2 de volta), sem tocar em dado nenhum.
#
# Condicionada ao PostgreSQL, como a 0010: `CREATE OR REPLACE FUNCTION` é
# sintaxe exclusiva do PostgreSQL, e SQLite não tem os gatilhos da 0010
# para recriar — `RunPython` com guarda de `connection.vendor`, NO-OP fora
# do PostgreSQL.

from django.db import migrations

_ATUALIZAR_FUNCOES_SQL = """
CREATE OR REPLACE FUNCTION empresas_recusar_estabelecimento_para_empresa_cpf()
RETURNS trigger AS $$
DECLARE
    tipo_da_empresa varchar;
BEGIN
    -- D2/BL-534: FOR SHARE trava a linha da empresa contra qualquer
    -- UPDATE concorrente da MESMA linha (inclusive a transição de
    -- tipo_inscricao, que o outro gatilho abaixo protege) — ver o
    -- comentário completo no topo desta migração.
    SELECT tipo_inscricao INTO tipo_da_empresa
    FROM empresas_empresa
    WHERE id = NEW.empresa_id
    FOR SHARE;

    IF tipo_da_empresa = 'CPF' THEN
        RAISE EXCEPTION
            'Estabelecimento não pode ser vinculado a uma empresa com '
            'tipo_inscricao=CPF (DL-039/BL-529): matriz/filial é conceito '
            'de pessoa jurídica.'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'estabelecimento_empresa_nao_e_cpf';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION empresas_recusar_transicao_para_cpf_com_estabelecimento()
RETURNS trigger AS $$
BEGIN
    IF NEW.tipo_inscricao = 'CPF' AND OLD.tipo_inscricao IS DISTINCT FROM NEW.tipo_inscricao THEN
        IF EXISTS (SELECT 1 FROM empresas_estabelecimento WHERE empresa_id = NEW.id) THEN
            RAISE EXCEPTION
                'Empresa não pode mudar para tipo_inscricao=CPF com '
                'estabelecimento já gravado (DL-039/BL-529): desfaça ou '
                'apague o(s) estabelecimento(s) primeiro.'
                USING ERRCODE = '23514',
                      CONSTRAINT = 'empresa_transicao_cpf_com_estabelecimento';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_RESTAURAR_FUNCOES_DA_0010_SQL = """
CREATE OR REPLACE FUNCTION empresas_recusar_estabelecimento_para_empresa_cpf()
RETURNS trigger AS $$
DECLARE
    tipo_da_empresa varchar;
BEGIN
    SELECT tipo_inscricao INTO tipo_da_empresa
    FROM empresas_empresa
    WHERE id = NEW.empresa_id;

    IF tipo_da_empresa = 'CPF' THEN
        RAISE EXCEPTION
            'Estabelecimento não pode ser vinculado a uma empresa com '
            'tipo_inscricao=CPF (DL-039/BL-529): matriz/filial é conceito '
            'de pessoa jurídica.'
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION empresas_recusar_transicao_para_cpf_com_estabelecimento()
RETURNS trigger AS $$
BEGIN
    IF NEW.tipo_inscricao = 'CPF' AND OLD.tipo_inscricao IS DISTINCT FROM NEW.tipo_inscricao THEN
        IF EXISTS (SELECT 1 FROM empresas_estabelecimento WHERE empresa_id = NEW.id) THEN
            RAISE EXCEPTION
                'Empresa não pode mudar para tipo_inscricao=CPF com '
                'estabelecimento já gravado (DL-039/BL-529): desfaça ou '
                'apague o(s) estabelecimento(s) primeiro.'
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def _atualizar_funcoes(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ATUALIZAR_FUNCOES_SQL)


def _restaurar_funcoes_da_0010(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_RESTAURAR_FUNCOES_DA_0010_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0010_bl529_gatilho_estabelecimento_empresa_cpf"),
    ]

    operations = [
        migrations.RunPython(_atualizar_funcoes, _restaurar_funcoes_da_0010),
    ]
