# Achado U-B1 da auditoria da DL-041 rodada 1
# (docs/auditorias/2026-09-26-dl-041-rodada-1.md). NÃO edita a 0012 (só o
# comentário da 0012 foi corrigido, achado U-B2, sem tocar nas
# `operations`) — recria o gatilho de sincronização e acrescenta um novo,
# com `CREATE OR REPLACE`/`DROP` + `CREATE`, mesmo padrão da 0011 sobre a
# 0010.
#
# O auditor mediu DOIS caminhos pelos quais a coluna `escritorio` de
# `Estabelecimento` podia divergir da empresa, mesmo com o gatilho da
# 0012:
#
# 1. `QuerySet.update(escritorio=...)` DIRETO no estabelecimento (ou
#    `bulk_update`, ou SQL bruto `UPDATE ... SET escritorio_id`): o
#    gatilho da 0012 só disparava em `INSERT` ou `UPDATE OF empresa_id` —
#    nunca em `UPDATE OF escritorio_id`. Sem caminho de CLIENTE (nenhuma
#    tela/API/admin grava esse campo — é `editable=False`), mas ainda é
#    um jeito de o banco aceitar um dado inconsistente por ORM/SQL direto,
#    e a auditoria mediu o EFEITO: com um estabelecimento marcado como de
#    outro escritório por essa via, um SEGUNDO estabelecimento com o
#    MESMO CNPJ foi aceito dentro do escritório de origem — a unicidade
#    por escritório fica anulada.
# 2. `Empresa.objects.filter(...).update(escritorio=...)`: a DL-023 proíbe
#    a TROCA de escritório de uma empresa só na APLICAÇÃO (`Empresa.
#    clean()`, `readonly_fields` do admin) — nunca no banco. Trocar por
#    `QuerySet.update()` (que não chama `clean()`) passa direto, e os
#    estabelecimentos daquela empresa ficam no escritório ANTIGO (o
#    gatilho de sincronização só olha para `Estabelecimento`, nunca para
#    o lado contrário).
#
# DUAS correções, DECISÃO do arquiteto-senior registrada aqui:
#
# 1. O gatilho de sincronização (`trg_estabelecimento_sincroniza_
#    escritorio`) passa a disparar TAMBÉM em `UPDATE OF escritorio_id` —
#    a FUNÇÃO não muda (já recalcula `NEW.escritorio_id` a partir de
#    `NEW.empresa_id` sempre); só a lista de colunas que disparam o
#    gatilho cresce. `DROP TRIGGER` + `CREATE TRIGGER` (não há `ALTER
#    TRIGGER` para mudar a lista de colunas de um `UPDATE OF` no
#    PostgreSQL).
# 2. Para `empresas_empresa`: RECUSAR a troca de `escritorio_id`, não
#    propagá-la para os estabelecimentos. Decisão do arquiteto-senior:
#    propagar exigiria um SEGUNDO gatilho (em `empresas_empresa`) que
#    escrevesse em `empresas_estabelecimento` — trigger cruzado entre
#    tabelas, mais uma superfície de invariante para manter, para um
#    caminho que a aplicação já declara não suportado (DL-023, P1: "a
#    pendência de transferir empresa entre escritórios não foi
#    respondida pelo Fred"). RECUSAR no banco é a MESMA resposta que a
#    aplicação já dá, só que também para ORM direto e SQL — camada 1 da
#    DE-008 para uma invariante que já tinha só a camada 2 (Python).
#
# Sem caminho de CLIENTE para nenhum dos dois lados (nenhuma tela, API ou
# admin grava `Estabelecimento.escritorio` nem troca `Empresa.escritorio`
# depois de criada) — a correção é defesa em profundidade, não fecha um
# vazamento explorável hoje.
#
# Condicionada ao PostgreSQL (como a 0010, 0011 e 0012): `CREATE TRIGGER`/
# `plpgsql` não existe em SQLite — `RunPython` com guarda de `connection.
# vendor`, NO-OP fora do PostgreSQL. Reversível: a função de volta recria
# o gatilho de sincronização EXATAMENTE como a 0012 o deixou (só `UPDATE
# OF empresa_id`) e remove o gatilho novo de `empresas_empresa`.

from django.db import migrations

_ATUALIZAR_GATILHO_ESTABELECIMENTO_SQL = """
DROP TRIGGER IF EXISTS trg_estabelecimento_sincroniza_escritorio
    ON empresas_estabelecimento;

CREATE TRIGGER trg_estabelecimento_sincroniza_escritorio
    BEFORE INSERT OR UPDATE OF empresa_id, escritorio_id ON empresas_estabelecimento
    FOR EACH ROW
    EXECUTE FUNCTION empresas_sincronizar_escritorio_do_estabelecimento();
"""

_RESTAURAR_GATILHO_ESTABELECIMENTO_DA_0012_SQL = """
DROP TRIGGER IF EXISTS trg_estabelecimento_sincroniza_escritorio
    ON empresas_estabelecimento;

CREATE TRIGGER trg_estabelecimento_sincroniza_escritorio
    BEFORE INSERT OR UPDATE OF empresa_id ON empresas_estabelecimento
    FOR EACH ROW
    EXECUTE FUNCTION empresas_sincronizar_escritorio_do_estabelecimento();
"""

_CRIAR_GATILHO_EMPRESA_SQL = """
CREATE OR REPLACE FUNCTION empresas_recusar_troca_de_escritorio()
RETURNS trigger AS $$
BEGIN
    IF NEW.escritorio_id IS DISTINCT FROM OLD.escritorio_id THEN
        RAISE EXCEPTION
            'Não é possível mudar o escritório desta empresa (DL-023): '
            'transferir empresa entre escritórios não é suportado pelo '
            'cadastro comum.'
            USING ERRCODE = '23514',
                  CONSTRAINT = 'empresa_escritorio_imutavel';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_empresa_recusa_troca_de_escritorio
    BEFORE UPDATE OF escritorio_id ON empresas_empresa
    FOR EACH ROW
    EXECUTE FUNCTION empresas_recusar_troca_de_escritorio();
"""

_REMOVER_GATILHO_EMPRESA_SQL = """
DROP TRIGGER IF EXISTS trg_empresa_recusa_troca_de_escritorio ON empresas_empresa;
DROP FUNCTION IF EXISTS empresas_recusar_troca_de_escritorio();
"""


def _aplicar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_ATUALIZAR_GATILHO_ESTABELECIMENTO_SQL)
    schema_editor.execute(_CRIAR_GATILHO_EMPRESA_SQL)


def _reverter(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHO_EMPRESA_SQL)
    schema_editor.execute(_RESTAURAR_GATILHO_ESTABELECIMENTO_DA_0012_SQL)


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0012_dl041_unicidade_por_escritorio"),
    ]

    operations = [
        migrations.RunPython(_aplicar, _reverter),
    ]
