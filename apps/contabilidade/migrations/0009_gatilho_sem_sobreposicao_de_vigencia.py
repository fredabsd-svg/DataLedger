# DL-043 (BL-474, RC-104/RC-105), critério 1 do plano — camada 2 da
# não sobreposição de vigência de `ParametroContabilEmpresa`, no MESMO
# padrão condicionado a `connection.vendor` das migrações 0010–0013 de
# `apps.empresas` (DL-039/DL-041): um GATILHO, só em PostgreSQL, que
# RECUSA qualquer INSERT/UPDATE cujo intervalo `[vigencia_inicio,
# vigencia_fim ou infinito]` se sobreponha ao de OUTRA linha da MESMA
# empresa.
#
# Por que um gatilho, e não `django.contrib.postgres.constraints.
# ExclusionConstraint`: este projeto não tem `django.contrib.postgres` em
# `INSTALLED_APPS` (nenhum app usa campo de intervalo hoje), e uma
# `ExclusionConstraint` de igualdade sobre uma coluna NÃO-intervalo
# (`empresa_id`) exige a extensão `btree_gist` — uma dependência de banco
# nova, para um projeto que ainda não tem nenhuma. O plano da etapa
# (DL-043) já previa esta alternativa ("ExclusionConstraint/gatilho ou
# alternativa medida"): um gatilho comparando `daterange(...) &&
# daterange(...)` faz a MESMA pergunta ("os dois intervalos se cruzam?")
# sem extensão nenhuma — `daterange` é tipo embutido do PostgreSQL. Mesma
# decisão de reuso de padrão já existente no repositório (AGENTS.md §8) em
# vez de introduzir mecanismo novo.
#
# A UniqueConstraint da migração 0008 (camada 1) já impede DUAS vigências
# ABERTAS ao mesmo tempo para a mesma empresa — mas ela não alcança a
# sobreposição entre uma vigência FECHADA e outra (só a condição
# `vigencia_fim IS NULL` participa dela). Este gatilho é quem cobre esse
# caso, e cobre também caminhos que o serviço não usa (`bulk_create`/
# `QuerySet.update()`/SQL direto) — defesa em profundidade: o serviço
# `apps.contabilidade.services.registrar_parametro_contabil` já fecha a
# vigência anterior de forma sequencial (nunca produz sobreposição pelo
# caminho normal), então este gatilho só dispara sob concorrência real ou
# escrita fora da aplicação.
#
# `NEW.id` já está preenchido quando um gatilho BEFORE INSERT roda no
# PostgreSQL (o valor da sequência/identity é atribuído ANTES de o
# gatilho de linha ser invocado — documentado no manual do PostgreSQL,
# capítulo de gatilhos), então `p.id <> NEW.id` exclui corretamente a
# própria linha tanto em INSERT quanto em UPDATE.
#
# `CONSTRAINT = 'parametro_contabil_sem_sobreposicao'` no `RAISE
# EXCEPTION`: é o que faz `IntegrityError.__cause__.diag.constraint_name`
# chegar preenchido ao Django, e `apps.contabilidade.services.
# registrar_parametro_contabil` traduz esse nome (via `apps.core.
# restricoes.mensagens_de_gatilho`/`restricao_como_400`) para
# `VigenciaParametroContabilConflitante` (409), nunca um 500 cru — mesmo
# mecanismo das migrações 0011/0013 de `apps.empresas`.
#
# `%%` (não `%`) dentro de `_CRIAR_GATILHO_SQL`, no `RAISE EXCEPTION`:
# `schema_editor.execute()` passa a string por `psycopg`, que varre TODA a
# string (inclusive dentro de comentário SQL `--`, que o driver não
# distingue de código) procurando `%` como início de placeholder do
# PRÓPRIO driver — o mesmo `%` que o `RAISE` do plpgsql usa para o
# argumento posicional (`NEW.empresa_id`). Medido ao aplicar esta
# migração: um `%` (ou `` `%` `` dentro de um comentário explicativo)
# sozinho levanta `psycopg.ProgrammingError` ("incomplete placeholder" ou
# "only '%s', '%b', '%t' são allowed"). `%%` chega ao PostgreSQL já
# reduzido a um único `%`, que é o que o `RAISE` espera.
#
# Condicionada ao PostgreSQL (como as 0010–0013 de `apps.empresas`):
# `CREATE TRIGGER`/`plpgsql`/`daterange` não têm equivalente em SQLite.
# `RunPython` com guarda de `connection.vendor`, NO-OP fora do PostgreSQL —
# LIMITE ACEITO e declarado: em desenvolvimento local (SQLite, DE-014) só
# a camada 1 (UniqueConstraint da 0008) protege; produção nunca roda
# SQLite (`config/settings.py` recusa subir com SQLite e `DEBUG=False`).
# Reversível: a função de reversão remove o gatilho e a função.

from django.db import migrations

_CRIAR_GATILHO_SQL = """
CREATE OR REPLACE FUNCTION contabilidade_recusar_sobreposicao_parametro_contabil()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM contabilidade_parametrocontabilempresa p
        WHERE p.empresa_id = NEW.empresa_id
          AND p.id <> NEW.id
          AND daterange(p.vigencia_inicio, COALESCE(p.vigencia_fim, 'infinity'::date), '[]')
              && daterange(NEW.vigencia_inicio, COALESCE(NEW.vigencia_fim, 'infinity'::date), '[]')
    ) THEN
        -- Sinal de porcentagem duplicado abaixo de propósito: ver o
        -- comentário Python no topo do arquivo.
        RAISE EXCEPTION
            'Esta vigência de parâmetro contábil sobrepõe outra já gravada '
            'para a empresa %% (DL-043).', NEW.empresa_id
            USING ERRCODE = '23514',
                  CONSTRAINT = 'parametro_contabil_sem_sobreposicao';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_parametro_contabil_sem_sobreposicao
    BEFORE INSERT OR UPDATE OF empresa_id, vigencia_inicio, vigencia_fim
    ON contabilidade_parametrocontabilempresa
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_recusar_sobreposicao_parametro_contabil();
"""

_REMOVER_GATILHO_SQL = """
DROP TRIGGER IF EXISTS trg_parametro_contabil_sem_sobreposicao
    ON contabilidade_parametrocontabilempresa;
DROP FUNCTION IF EXISTS contabilidade_recusar_sobreposicao_parametro_contabil();
"""


def _criar_gatilho(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_GATILHO_SQL)


def _remover_gatilho(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHO_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0008_parametrocontabilempresa"),
    ]

    operations = [
        migrations.RunPython(_criar_gatilho, _remover_gatilho),
    ]
