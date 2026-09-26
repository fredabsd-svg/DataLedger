# Achado B2 (ressalva) e N18 da reconferência da DL-010/DL-038
# (docs/auditorias/2026-09-25-dl-010-f1-dl-038-reconferencia.md) — BL-529
# (docs/planos/DL-039-ressalvas-recepcao-e-pessoa-fisica.md).
#
# DECISÃO REGISTRADA (o achado pede isso explicitamente): "estabelecimento
# é conceito de pessoa jurídica" é uma invariante ENTRE DUAS TABELAS
# (Estabelecimento.empresa.tipo_inscricao) — uma `CheckConstraint` do
# Django/PostgreSQL não alcança isso, porque ela só enxerga colunas da
# PRÓPRIA linha/tabela (documentado em `apps/core/restricoes.py`, que
# continua sendo a fonte única de onde CADA invariante está defendida).
# A alternativa escolhida foi um GATILHO (`CREATE TRIGGER`/`plpgsql`) — a
# única ferramenta do PostgreSQL que expressa checagem entre tabelas SEM
# duplicar a regra numa VIEW materializada ou denormalizar
# `tipo_inscricao` para `Estabelecimento` (que criaria uma SEGUNDA fonte
# da verdade, exatamente o problema oposto).
#
# Dois gatilhos, nas DUAS pontas da mesma invariante (fecha a corrida que
# a reconferência registrou como "não verificado" — criar estabelecimento
# e trocar a empresa para CPF são operações em tabelas DIFERENTES, cada
# uma precisa da própria defesa):
#
# 1. `trg_estabelecimento_recusa_empresa_cpf` — antes de INSERT/UPDATE em
#    `empresas_estabelecimento`, recusa se a empresa referenciada já é
#    CPF. Cobre o caminho que `Estabelecimento.clean()`
#    (apps/empresas/models.py) NÃO alcança: `objects.create()` direto,
#    `bulk_create()`, migração de dado, ou qualquer SQL fora do ORM —
#    nenhum deles chama `full_clean()`.
# 2. `trg_empresa_recusa_transicao_cpf_com_estabelecimento` — antes de
#    UPDATE de `tipo_inscricao` em `empresas_empresa`, recusa a transição
#    para CPF se já existe estabelecimento gravado. Cobre o mesmo tipo de
#    caminho para o lado inverso — o que `Empresa.clean()` (a checagem em
#    Python, achado N18) também não alcança fora de `full_clean()`.
#
# `RAISE EXCEPTION ... USING ERRCODE = '23514'` (check_violation, classe
# 23 do SQLSTATE — a MESMA classe de uma `CheckConstraint` nativa) é
# proposital: o driver (psycopg) mapeia qualquer SQLSTATE de classe 23
# para o equivalente de `IntegrityError`, e é isso que o Django repassa
# como `django.db.IntegrityError` — o MESMO tipo de exceção que qualquer
# outra restrição de banco deste projeto já produz (nenhum código
# chamador precisa aprender um tipo de exceção novo só por causa do
# gatilho).
#
# Migração REVERSÍVEL: o `reverse_sql` remove os dois gatilhos e as duas
# funções, sem tocar em dado nenhum (não há coluna nova, não há
# reescrita de linha) — `migrate empresas 0009` desfaz por completo.
#
# Risco de falhar em banco com dado real: BAIXO. Só falha ao criar se já
# existir uma empresa CPF com estabelecimento gravado ANTES desta
# migração — nesse caso, o gatilho nasceria de acordo com um dado que já
# viola a invariante nova, mas a CRIAÇÃO do gatilho em si (`CREATE
# TRIGGER`) não varre linhas existentes (diferente de uma
# `CheckConstraint` com `NOT VALID` ausente) — só passa a valer para
# escritas FUTURAS. Uma inconsistência pré-existente não impede a
# migração; só deixaria de ser aceitável daqui para frente, que é o
# comportamento CORRETO (avisar antes de reforçar uma invariante que já
# foi violada, não silenciar — mesmo espírito do comentário da 0009).

from django.db import migrations

_CRIAR_GATILHOS_SQL = """
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

CREATE TRIGGER trg_estabelecimento_recusa_empresa_cpf
    BEFORE INSERT OR UPDATE OF empresa_id ON empresas_estabelecimento
    FOR EACH ROW
    EXECUTE FUNCTION empresas_recusar_estabelecimento_para_empresa_cpf();

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

CREATE TRIGGER trg_empresa_recusa_transicao_cpf_com_estabelecimento
    BEFORE UPDATE OF tipo_inscricao ON empresas_empresa
    FOR EACH ROW
    EXECUTE FUNCTION empresas_recusar_transicao_para_cpf_com_estabelecimento();
"""

_REMOVER_GATILHOS_SQL = """
DROP TRIGGER IF EXISTS trg_empresa_recusa_transicao_cpf_com_estabelecimento
    ON empresas_empresa;
DROP FUNCTION IF EXISTS empresas_recusar_transicao_para_cpf_com_estabelecimento();

DROP TRIGGER IF EXISTS trg_estabelecimento_recusa_empresa_cpf
    ON empresas_estabelecimento;
DROP FUNCTION IF EXISTS empresas_recusar_estabelecimento_para_empresa_cpf();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("empresas", "0009_empresa_empresa_modo_escrituracao_valido"),
    ]

    operations = [
        migrations.RunSQL(sql=_CRIAR_GATILHOS_SQL, reverse_sql=_REMOVER_GATILHOS_SQL),
    ]
