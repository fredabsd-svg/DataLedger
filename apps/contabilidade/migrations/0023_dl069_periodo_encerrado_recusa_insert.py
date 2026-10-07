# DL-069, fatia 2 — período encerrado recusa INSERT NO BANCO, e a entrega da
# competência não se desfaz (itens 1, 3 e 4 do escopo; o item 2, do
# livro-caixa, é a migração 0012 de `apps.livro_caixa`).
#
# POR QUÊ. `criar_lancamento` já recusa lançamento em competência que não está
# `aberta` (`apps/contabilidade/services.py:1026-1052`), e `reabrir_competencia`
# já recusa competência entregue (RC-101, services.py:1414-1421). Mas isso só
# vale para quem passa pelo serviço: um `objects.create()`, um `bulk_create()`,
# uma migração de dados ou um SQL de manutenção gravavam lançamento em período
# fechado — e um `QuerySet.update()` ou SQL direto zerava `entregue_em` ou
# reabria a competência entregue, apagando o fato de que o documento já foi
# entregue ao cliente (RC-19/RC-101). Mesma classe de falha que a DL-052
# fechou para UPDATE/DELETE e que a fatia 1 desta mesma DL-069 fechou para o
# livro-caixa.
#
# PADRÃO SEGUIDO. Cópia deliberada das migrações 0013/0016 de `contabilidade`
# e 0011 de `livro_caixa` (gatilho `BEFORE ... FOR EACH ROW`, `RAISE EXCEPTION
# ... USING ERRCODE = '23514', CONSTRAINT = '<nome>'`, `RunPython` com no-op
# fora do PostgreSQL, reversa com `DROP ... IF EXISTS`). Só PostgreSQL: em
# SQLite a migração não emite SQL nenhum — mesmo LIMITE ACEITO e declarado da
# 0009/0013/0011 (produção nunca roda SQLite; `config/settings.py` recusa subir
# assim com `DEBUG=False`).
#
# O QUE ESTA MIGRAÇÃO FAZ:
#
# 1. `BEFORE INSERT` em `contabilidade_lancamentocontabil`
#    (`trg_lancamento_contabil_so_em_competencia_aberta`): recusa INSERT cuja
#    DATA caia em competência que não está `aberta`. Restrição:
#    `dl069_lancamento_contabil_so_em_competencia_aberta`.
#
#    A competência é achada PELA DATA (empresa + ano/mês de `NEW.data`), NUNCA
#    pela FK `competencia_id`: a FK é anulável em dado legado (DL-016 F5/F6 —
#    `backfill_lancamento_competencia` existe justamente para preenchê-la) e em
#    dado torto pode apontar para mês diferente da data. A apuração (DRE,
#    DLPA, DMPL, saldos) também filtra por DATA — guarda que filtra por
#    critério diferente do que a apuração filtra é guarda contornável (a
#    lição do achado A1 da DL-065, que vive em `docs/agents/estado.md`).
#
#    A comparação é `estado <> 'aberta'`, NÃO `estado = 'encerrada'`:
#    `em_encerramento` (reservado) e qualquer estado fora do enum também
#    bloqueiam — "estado desconhecido bloqueia, nunca libera", a mesma regra
#    que `criar_lancamento` aplica (`estado_travado != EstadoCompetencia.
#    ABERTA`, services.py:1026).
#
#    MÊS SEM LINHA DE `Competencia` é ABERTO e o INSERT passa: é o mesmo
#    julgamento de `obter_ou_criar_competencia` (services.py:410-458), que
#    cria a linha como `aberta` no primeiro lançamento do serviço. O gatilho
#    NÃO cria a linha (ver "decisão de lock", abaixo).
#
# 2. `BEFORE UPDATE` em `contabilidade_competencia`
#    (`trg_competencia_entregue_protegida`), com DOIS bloqueios nomeados:
#
#    - `dl069_competencia_entregue_nao_volta_a_null`: `entregue_em` preenchido
#      não volta a NULL. "Entregue" é FATO DATADO (decisão do
#      arquiteto-senior, RC-101 — ver o docstring de `Competencia`): o
#      serviço `marcar_competencia_como_entregue` ATUALIZA a data para o
#      evento mais recente (permitido aqui), mas nenhum service limpa os
#      campos, e o banco passa a recusar quem limpar por fora.
#    - `dl069_competencia_entregue_nao_reabre`: competência com `entregue_em`
#      preenchido não faz a transição para `aberta` (RC-101) — é o que
#      `reabrir_competencia` recusa em Python (services.py:1414-1421) e que o
#      SQL direto (`UPDATE ... SET estado='aberta', fechada_em=NULL, ...`)
#      fazia por fora. A trava é amarrada à TRANSIÇÃO (`NEW.estado='aberta'` e
#      `OLD.estado <> 'aberta'`), o mesmo desenho da migração 0011 da fatia 1
#      (amarado à transição, não à lista de colunas): "não VOLTA a aberta" é
#      um movimento, e uma linha já `aberta` não está voltando a lugar nenhum.
#      Na prática `entregue_em` só existe sobre competência `encerrada`
#      (`marcar_competencia_como_entregue` exige isso,
#      services.py:1489-1493), então a diferença só aparece em dado torto.
#      UPDATE que regrava os mesmos valores não altera fato nenhum e passa.
#
#    DELETE de `Competencia` e as outras colunas ficam FORA deste escopo
#    (a fatia 3 cuida da trilha; `competencia` é PROTECT e não há caminho de
#    exclusão no produto).
#
# DECISÃO DE LOCK — o ponto de maior risco técnico do escopo (BL-456). O
# gatilho faz a MESMA leitura protegida contra corrida que o serviço faz,
# ANTES de julgar o estado:
#
# - `SELECT estado, entregue_em ... FOR SHARE` sobre a linha da competência
#   achada pela data — espelho exato de
#   `_travar_competencia_em_modo_compartilhado` (services.py:526-667), que
#   `criar_lancamento` chama antes de gravar. `FOR SHARE` é COMPARTILHADO:
#   dois lançamentos do mesmo mês não se bloqueiam entre si; e ele CONFLITA
#   com o `FOR UPDATE` de `encerrar_competencia`/`reabrir_competencia`/
#   `marcar_competencia_como_entregue` (todas passam por
#   `_travar_competencia_para_transicao`, services.py:670-695). Assim, um
#   fechamento em andamento faz o INSERT esperar e reler o estado JÁ
#   ATUALIZADO (recusa); um INSERT em andamento faz o fechamento esperar, e o
#   lançamento aconteceu ANTES do fechamento, que é ordem legítima.
# - Pelo caminho do SERVIÇO a trava do serviço já está segurando o `FOR SHARE`
#   desde antes do INSERT (services.py:1023) — o gatilho re-toma o mesmo lock
#   na mesma transação, recebido na hora. O que o gatilho acrescenta é o
#   INSERT por FORA do serviço (ORM/SQL), que não passava por trava nenhuma.
# - ORDEM DE LOCK, sem ciclo possível: o gatilho toma UM lock só (a linha da
#   competência) e nenhum outro antes dele; o fechamento toma um lock só por
#   transição. `FOR SHARE` não conflita com o `FOR KEY SHARE` das chaves
#   estrangeiras (Django as declara DEFERRABLE, julgadas no COMMIT), então o
#   INSERT também não cria espera nova ali.
# - LIMITE DECIDIDO E DECLARADO: quando NÃO existe linha de `Competencia`
#   para a data, o gatilho deixa o INSERT passar sem lock (não há linha para
#   travar) e NÃO cria a linha. A corrida que fica aberta é só esta: INSERT
#   por fora do serviço em mês que ainda não tem `Competencia`, cruzado com o
#   PRIMEIRO fechamento daquele mês. O caminho do serviço não a tem
#   (`obter_ou_criar_competencia` cria a linha antes do INSERT, e o
#   fechamento passa pelo mesmo `get_or_create` + `FOR UPDATE`), e o INSERT
#   direto com linha existente também não (`FOR SHARE` aqui contra `FOR
#   UPDATE` lá). Criar a linha a partir do gatilho fecharia o canto, mas daria
#   ao INSERT um efeito colateral que nenhum teste nem nenhum dado legado
#   espera (toda gravação direta, inclusive a de dado torto que os testes e o
#   backfill montam, passaria a nascer com `Competencia`) — optou-se por
#   reproduzir o julgamento do serviço sem escrever no meio do INSERT.
#
# EFEITO EM RESTAURAÇÃO DE BACKUP. `pg_restore --data-only` que faça INSERT em
# lançamento de período fechado passa a exigir `--disable-triggers` (super-
# usuário) — o mesmo limite já declarado para a contabilidade (PE-07) e para a
# fatia 1 desta DL.
#
# `RAISE ... USING ERRCODE = '23514', CONSTRAINT = '<nome>'` faz
# `IntegrityError.__cause__.diag.constraint_name` chegar ao Django com um nome
# ESTÁVEL, registrado em
# `apps.core.restricoes.MENSAGENS_DE_RESTRICAO_DE_GATILHO`. `%` do `RAISE` do
# plpgsql pode ser escrito simples: `schema_editor.execute(sql, params=None)`
# não passa a string por placeholders do driver (mesma observação da 0013).
#
# Custo: uma busca pela competência (índice único (empresa, ano, mes)) por
# INSERT de lançamento, com `FOR SHARE` na linha; e um `to_jsonb` por UPDATE de
# competência (que só acontece em encerrar/reabrir/entregar). Nenhum caminho
# quente paga mais do que isso.
#
# Dados: nenhum dado é lido nem alterado; a migração só cria funções e
# gatilhos. Reversão: `migrate contabilidade 0022` remove gatilhos e funções,
# sem perda de dado.

from django.db import migrations

_CRIAR_GATILHOS_SQL = """
-- Item 1: lançamento novo só entra em competência ABERTA, achada pela DATA.
CREATE OR REPLACE FUNCTION contabilidade_recusar_lancamento_fora_de_competencia_aberta()
RETURNS trigger AS $$
DECLARE
    v_estado varchar;
    v_entregue_em timestamptz;
    v_mes integer;
    v_ano integer;
BEGIN
    v_ano := EXTRACT(YEAR FROM NEW.data)::integer;
    v_mes := EXTRACT(MONTH FROM NEW.data)::integer;

    -- FOR SHARE ANTES de julgar: espelho de
    -- `_travar_competencia_em_modo_compartilhado`
    -- (apps/contabilidade/services.py:526-667). Sem o lock, uma leitura
    -- qualquer enxergaria o estado ANTIGO enquanto um fechamento concorrente
    -- commita por cima — é exatamente a corrida medida no BL-456.
    SELECT estado, entregue_em INTO v_estado, v_entregue_em
      FROM contabilidade_competencia
     WHERE empresa_id = NEW.empresa_id
       AND ano = v_ano
       AND mes = v_mes
     FOR SHARE;

    -- Sem linha, o mês nasce ABERTO: mesmo julgamento de
    -- `obter_ou_criar_competencia` (services.py:410-458), que cria a linha
    -- como `aberta` no primeiro lançamento do serviço. Ver o limite declarado
    -- no cabeçalho desta migração.
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    IF v_estado IS DISTINCT FROM 'aberta' THEN
        IF v_entregue_em IS NOT NULL THEN
            -- Mesma frase do serviço, para API/admin não contarem duas
            -- histórias do mesmo motivo (DE-026): services.py:1040-1047.
            RAISE EXCEPTION
                'A competência %/% já foi entregue ao cliente; não é possível gravar '
                'lançamento nela e ela não pode ser reaberta (RC-101). Lance o ajuste em '
                'uma competência aberta, com histórico apontando para a competência de '
                'origem (%/%).', v_mes, v_ano, v_mes, v_ano
                USING ERRCODE = '23514',
                      CONSTRAINT = 'dl069_lancamento_contabil_so_em_competencia_aberta';
        END IF;
        -- Mesma frase do serviço (services.py:1048-1052).
        RAISE EXCEPTION
            'A competência %/% está ''%'': não é possível gravar lançamento nela. '
            'Reabra a competência ou lance em uma competência aberta.',
            v_mes, v_ano, v_estado
            USING ERRCODE = '23514',
                  CONSTRAINT = 'dl069_lancamento_contabil_so_em_competencia_aberta';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_lancamento_contabil_so_em_competencia_aberta
    BEFORE INSERT ON contabilidade_lancamentocontabil
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_recusar_lancamento_fora_de_competencia_aberta();

-- Itens 3 e 4: a entrega da competência ao cliente é um fato datado que não
-- se desfaz (RC-19/RC-101).
CREATE OR REPLACE FUNCTION contabilidade_proteger_entrega_da_competencia()
RETURNS trigger AS $$
BEGIN
    -- Regravar os mesmos valores não altera fato nenhum (mesmo critério da
    -- migração 0011 de `livro_caixa`, da fatia 1).
    IF to_jsonb(NEW) = to_jsonb(OLD) THEN
        RETURN NEW;
    END IF;

    -- Item 3: `entregue_em` preenchido não volta a NULL. Atualizar para uma
    -- data NOVA continua permitido — é o que `marcar_competencia_como_entregue`
    -- faz quando a entrega se repete (balancete, depois ECD;
    -- services.py:1459-1498).
    IF OLD.entregue_em IS NOT NULL AND NEW.entregue_em IS NULL THEN
        RAISE EXCEPTION
            'A competência %/% já foi entregue ao cliente em %: a data da entrega não '
            'volta a ficar em branco.', OLD.mes, OLD.ano, OLD.entregue_em
            USING ERRCODE = '23514',
                  CONSTRAINT = 'dl069_competencia_entregue_nao_volta_a_null';
    END IF;

    -- Item 4 (RC-101): entregue não volta a `aberta` — a trava é amarrada à
    -- TRANSIÇÃO, como na migração 0011 da fatia 1. O serviço recusa o mesmo
    -- caso antes da escrita (`reabrir_competencia`, services.py:1414-1421).
    IF OLD.entregue_em IS NOT NULL
       AND NEW.estado = 'aberta'
       AND OLD.estado IS DISTINCT FROM 'aberta'
    THEN
        RAISE EXCEPTION
            'A competência %/% já foi entregue ao cliente e não volta a aberta (RC-101): '
            'lance o ajuste em uma competência aberta, com histórico apontando para a '
            'competência de origem.', OLD.mes, OLD.ano
            USING ERRCODE = '23514',
                  CONSTRAINT = 'dl069_competencia_entregue_nao_reabre';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_competencia_entregue_protegida
    BEFORE UPDATE ON contabilidade_competencia
    FOR EACH ROW
    EXECUTE FUNCTION contabilidade_proteger_entrega_da_competencia();
"""

_REMOVER_GATILHOS_SQL = """
DROP TRIGGER IF EXISTS trg_competencia_entregue_protegida ON contabilidade_competencia;
DROP TRIGGER IF EXISTS trg_lancamento_contabil_so_em_competencia_aberta ON contabilidade_lancamentocontabil;
DROP FUNCTION IF EXISTS contabilidade_proteger_entrega_da_competencia();
DROP FUNCTION IF EXISTS contabilidade_recusar_lancamento_fora_de_competencia_aberta();
"""


def _criar_gatilhos(apps, schema_editor):
    # NO-OP fora do PostgreSQL (ver o cabeçalho): em SQLite as travas não
    # existem e a migração declara isso não emitindo SQL nenhum.
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_CRIAR_GATILHOS_SQL, params=None)


def _remover_gatilhos(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(_REMOVER_GATILHOS_SQL, params=None)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidade", "0022_alter_conta_item_de_resultado_sem_caixa"),
    ]

    operations = [
        migrations.RunPython(_criar_gatilhos, _remover_gatilhos),
    ]
