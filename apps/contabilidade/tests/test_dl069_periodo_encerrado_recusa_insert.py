"""DL-069, fatia 2 — período encerrado recusa INSERT no banco (contabilidade).

Antes desta fatia, a trava de competência só existia em `criar_lancamento` e a
permanência da entrega só em `reabrir_competencia`/`Competencia`. Um
`objects.create()`, um `bulk_create()` ou um SQL direto gravavam lançamento em
competência encerrada/entregue; um `QuerySet.update()` zerava `entregue_em` ou
reabria a competência entregue. As migrações 0023 (contabilidade) e 0012
(livro-caixa) criam os gatilhos — este arquivo cobre a contabilidade.

Critérios do plano cobertos (números do plano da fatia 2):

1. INSERT de `LancamentoContabil` com data em competência que não está
   `aberta` é recusado pelo BANCO (`IntegrityError` nomeando a restrição),
   por ORM e por SQL direto, com a competência achada PELA DATA.
3. `Competencia.entregue_em` não volta a NULL (ORM e SQL).
4. Competência entregue não volta a `aberta` (RC-101; ORM e SQL).
5. Continua permitido: backfill NULL→valor (inclusive em competência já
   encerrada), estorno em mês aberto (RC-103), reabertura de competência NÃO
   entregue e o ciclo dos serviços.
6. As restrições estão registradas em `MENSAGENS_DE_RESTRICAO_DE_GATILHO` e o
   tradutor `restricao_como_400` converte a recusa real do banco.
8. Cenários negativos e mutação: sem o gatilho, a escrita passa.
10/11. Migração reversível (para trás e para frente) e no-op declarado fora do
   PostgreSQL.

Os testes de gatilho exigem PostgreSQL e são PULADOS em SQLite, com motivo
declarado (as migrações são no-op lá — mesmo limite aceito da 0009/0013).
A prova dos gatilhos é da CI (`postgres:16-alpine`). Dados sintéticos.

Cada lançamento gravado por fora do serviço leva as partidas balanceadas que a
invariante do livro exige no COMMIT (DL-052, migração 0013): sem elas, o
`CONSTRAINT TRIGGER` adiado reprovaria a MONTAGEM do dado, não o que o teste
mede — e o marcador de item da 0016 exige lançamento e itens na MESMA
transação (por isso os dois saem juntos, dentro de um `transaction.atomic()`).
"""

# ruff: noqa: F811
# (a fixture `cenario` importada é usada como parâmetro, o padrão do repositório)
import importlib
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.contabilidade.models import (
    Competencia,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    TipoPartida,
)
from apps.contabilidade.services import (
    CompetenciaJaEntregue,
    criar_lancamento,
    encerrar_competencia,
    estornar_lancamento,
    marcar_competencia_como_entregue,
    reabrir_competencia,
)
from apps.contabilidade.tests.gatilhos_do_livro import gatilho_desligado, modelos_do_esquema
from apps.contabilidade.tests.test_dl052_invariantes_no_banco import (  # noqa: F401
    cenario,
)
from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO_DE_GATILHO,
    RestricaoViolada,
    mensagens_de_gatilho,
    restricao_como_400,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason=(
        "Os gatilhos da migração 0023 (DL-069, fatia 2) existem só em PostgreSQL; em SQLite "
        "a trava de período fica na aplicação (limite aceito, como na 0009, 0013 e 0011)."
    ),
)

TABELA_LANCAMENTO = LancamentoContabil._meta.db_table
TABELA_COMPETENCIA = Competencia._meta.db_table

# `(tabela, gatilho)` no formato de `gatilhos_do_livro.gatilho_desligado`, para
# o teste de mutação (critério 8) desligar SÓ o gatilho medido.
GATILHO_INSERT_LANCAMENTO = (TABELA_LANCAMENTO, "trg_lancamento_contabil_so_em_competencia_aberta")
GATILHO_UPDATE_COMPETENCIA = (TABELA_COMPETENCIA, "trg_competencia_entregue_protegida")

RESTRICAO_LANCAMENTO = "dl069_lancamento_contabil_so_em_competencia_aberta"
RESTRICAO_ENTREGUE_NULL = "dl069_competencia_entregue_nao_volta_a_null"
RESTRICAO_ENTREGUE_REABRE = "dl069_competencia_entregue_nao_reabre"
RESTRICOES_DA_CONTABILIDADE = (
    RESTRICAO_LANCAMENTO,
    RESTRICAO_ENTREGUE_NULL,
    RESTRICAO_ENTREGUE_REABRE,
)

# Estados que NÃO são `aberta` e devem bloquear o INSERT (critério 1). O
# terceiro é fora do enum de propósito: "estado desconhecido bloqueia, nunca
# libera" — a mesma regra de `criar_lancamento` (`!= ABERTA`).
ESTADOS_QUE_BLOQUEIAM = ["encerrada", "em_encerramento", "arquivada"]


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _recusado(restricao, operacao):
    """Executa `operacao()` dentro de um savepoint e exige a recusa do gatilho."""
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            operacao()
    assert _nome_da_restricao(erro) == restricao


def _sql(sql, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parametros)


def _linha(modelo, pk):
    """Todas as colunas da linha, para provar que NADA mudou depois da recusa."""
    return modelo.objects.filter(pk=pk).values().get()


def _usuario(prefixo="autor"):
    nome = f"{prefixo}-dl069-f2"
    return get_user_model().objects.create_user(
        username=nome, email=f"{nome}@escritorio.com.br", password="senha-forte-123"
    )


def _competencia_com_estado(cenario, *, ano, mes, estado, entregue_em=None):
    """`Competencia` direto pelo ORM, com o estado que o teste precisa. Criar
    por fora é a MONTAGEM do dado destes testes de banco; quem valida a
    transição são os serviços, cobertos por testes próprios."""
    return Competencia.objects.create(
        empresa=cenario["empresa"],
        ano=ano,
        mes=mes,
        estado=estado,
        entregue_em=entregue_em,
    )


def _lancamento_direto(
    cenario, *, data, competencia=None, historico="Direto pelo ORM", esquema=None
):
    """Lançamento gravado por FORA de `criar_lancamento` (ORM direto), com as
    partidas balanceadas exigidas pela invariante do livro — ver o docstring do
    módulo. Lançamento e itens saem na MESMA transação por causa do marcador da
    migração 0016 (item só entra em lançamento da própria transação).

    `esquema` (DL-089): registro histórico (`modelos_do_esquema`) quando a gravação acontece
    dentro de uma janela de migração anterior à 0026, que não tem a coluna `origem`.
    """
    modelo_lancamento = (
        LancamentoContabil
        if esquema is None
        else esquema.get_model("contabilidade", "LancamentoContabil")
    )
    modelo_item = (
        ItemLancamento if esquema is None else esquema.get_model("contabilidade", "ItemLancamento")
    )
    with transaction.atomic():
        lancamento = modelo_lancamento.objects.create(
            empresa_id=cenario["empresa"].pk,
            data=data,
            historico=historico,
            competencia=competencia,
        )
        modelo_item.objects.bulk_create(
            [
                modelo_item(
                    lancamento_id=lancamento.pk,
                    conta_id=cenario["caixa"].pk,
                    tipo=TipoPartida.DEBITO,
                    valor=Decimal("10.00"),
                ),
                modelo_item(
                    lancamento_id=lancamento.pk,
                    conta_id=cenario["capital"].pk,
                    tipo=TipoPartida.CREDITO,
                    valor=Decimal("10.00"),
                ),
            ]
        )
    return lancamento


# ---------------------------------------------------------------------------
# Critério 1 — INSERT em competência que não está `aberta` é recusado
# ---------------------------------------------------------------------------


@so_postgresql
@pytest.mark.parametrize("estado", ESTADOS_QUE_BLOQUEIAM)
def test_orm_create_em_competencia_que_nao_esta_aberta_e_recusado(cenario, estado):
    _competencia_com_estado(cenario, ano=2026, mes=3, estado=estado)
    antes = LancamentoContabil.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 10)),
    )

    assert LancamentoContabil.objects.count() == antes


@so_postgresql
def test_save_e_bulk_create_em_competencia_encerrada_sao_recusados(cenario):
    _competencia_com_estado(cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA)
    antes = LancamentoContabil.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoContabil(
            empresa=cenario["empresa"], data=date(2026, 3, 10), historico="Via save()"
        ).save(),
    )
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoContabil.objects.bulk_create(
            [
                LancamentoContabil(
                    empresa=cenario["empresa"], data=date(2026, 3, 11), historico="Via bulk_create"
                )
            ]
        ),
    )

    assert LancamentoContabil.objects.count() == antes


@so_postgresql
def test_sql_direto_em_competencia_encerrada_e_recusado_e_nada_entra(cenario):
    _competencia_com_estado(cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA)
    antes = LancamentoContabil.objects.count()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _sql(
            f"INSERT INTO {TABELA_LANCAMENTO} (empresa_id, data, historico, criado_em, "
            "competencia_id) VALUES (%s, %s, %s, %s, %s)",
            [cenario["empresa"].pk, date(2026, 3, 10), "SQL direto", timezone.now(), None],
        ),
    )

    assert LancamentoContabil.objects.count() == antes


@so_postgresql
def test_a_competencia_e_achada_pela_data_nao_pela_fk(cenario):
    """A FK `competencia` é anulável em dado legado e pode mentir em dado
    torto (DL-016 F5/F6). Quem decide é a DATA — a mesma coisa que filtram as
    apurações (a lição do achado A1 da DL-065)."""
    encerrada = _competencia_com_estado(
        cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA
    )
    aberta_de_outro_mes = Competencia.objects.create(empresa=cenario["empresa"], ano=2026, mes=4)
    antes = LancamentoContabil.objects.count()

    # FK NULL, data em março (encerrada): recusado.
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 10), competencia=None),
    )
    # FK apontando para abril (aberta), mas data em março (encerrada): recusado.
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(
            cenario, data=date(2026, 3, 10), competencia=aberta_de_outro_mes
        ),
    )
    # E a inversa não confunde: data em abril (aberta) passa mesmo com a FK
    # apontando para a competência encerrada de março — quem julga é a data.
    lancamento = _lancamento_direto(cenario, data=date(2026, 4, 10), competencia=encerrada)

    assert LancamentoContabil.objects.count() == antes + 1
    assert lancamento.pk


# ---------------------------------------------------------------------------
# Critério 5 — o que continua permitido, com os gatilhos LIGADOS
# ---------------------------------------------------------------------------


def test_lancamento_em_competencia_aberta_passa_com_os_gatilhos_ligados(cenario):
    """Tanto pelo serviço quanto por ORM direto — o gatilho não inventa regra."""
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Serviço",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    direto = _lancamento_direto(cenario, data=date(2026, 3, 12))

    assert LancamentoContabil.objects.filter(pk__in=[lancamento.pk, direto.pk]).count() == 2


def test_estorno_em_mes_aberto_continua_permitido(cenario):
    """RC-103: o original fica no mês fechado e o estorno entra num mês ABERTO
    — o gatilho julga a competência da DATA do estorno, como o serviço."""
    gestor = _usuario()
    original = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Original de março",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=3, usuario=gestor)

    estorno = estornar_lancamento(original, criado_por=gestor)

    assert estorno.estorno_de_id == original.pk
    assert estorno.data > original.data


def test_backfill_null_para_valor_passa_mesmo_em_competencia_encerrada(cenario):
    """O backfill (DL-016 F5) preenche a FK de dado LEGADO — inclusive em mês
    já encerrado, que é justamente onde o dado legado vive. Ele faz
    `QuerySet.update(competencia=...)`, não INSERT, e o gatilho novo é só de
    INSERT: nada muda para ele."""
    gestor = _usuario()
    legado = _lancamento_direto(cenario, data=date(2026, 3, 10), historico="Legado sem FK")
    assert legado.competencia_id is None
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=3, usuario=gestor)
    assert (
        Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3).estado
        == EstadoCompetencia.ENCERRADA
    )

    call_command("backfill_lancamento_competencia", "--apply")

    legado.refresh_from_db()
    assert legado.competencia_id is not None
    assert legado.competencia.ano == 2026 and legado.competencia.mes == 3


def test_reabertura_de_competencia_nao_entregue_continua_permitida(cenario):
    gestor = _usuario()
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=3, usuario=gestor)

    reaberta = reabrir_competencia(
        empresa=cenario["empresa"],
        ano=2026,
        mes=3,
        usuario=gestor,
        motivo="Corrigir lançamento de março",
    )

    assert reaberta.estado == EstadoCompetencia.ABERTA


def test_reabertura_de_competencia_entregue_e_recusada_pelo_servico_antes_do_banco():
    """As duas camadas contam a MESMA história (DE-026): o serviço recusa com
    `CompetenciaJaEntregue` antes de qualquer escrita, e o gatilho é a defesa
    para quem passar por fora."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-069 f2", cnpj="69696969000169")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-069 f2 Ltda", cnpj="69696969000170"
    )
    gestor = _usuario("rc101")
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=3, usuario=gestor)

    with pytest.raises(CompetenciaJaEntregue):
        reabrir_competencia(
            empresa=empresa,
            ano=2026,
            mes=3,
            usuario=gestor,
            motivo="Tentativa de reabrir o que já foi entregue",
        )

    assert Competencia.objects.get(empresa=empresa, ano=2026, mes=3).entregue_em is not None


# ---------------------------------------------------------------------------
# Critérios 3 e 4 — a entrega da competência não se desfaz
# ---------------------------------------------------------------------------


def _entregue(cenario, *, ano=2026, mes=3, prefixo="entregue"):
    """Competência encerrada e ENTREGUE pelos caminhos reais do produto."""
    gestor = _usuario(prefixo)
    encerrar_competencia(empresa=cenario["empresa"], ano=ano, mes=mes, usuario=gestor)
    marcar_competencia_como_entregue(empresa=cenario["empresa"], ano=ano, mes=mes, usuario=gestor)
    return gestor


@so_postgresql
def test_entregue_em_nao_volta_a_null_por_orm(cenario):
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    assert competencia.entregue_em is not None
    antes = _linha(Competencia, competencia.pk)

    _recusado(
        RESTRICAO_ENTREGUE_NULL,
        lambda: Competencia.objects.filter(pk=competencia.pk).update(entregue_em=None),
    )

    assert _linha(Competencia, competencia.pk) == antes


@so_postgresql
def test_entregue_em_nao_volta_a_null_por_sql(cenario):
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    antes = _linha(Competencia, competencia.pk)

    _recusado(
        RESTRICAO_ENTREGUE_NULL,
        lambda: _sql(
            f"UPDATE {TABELA_COMPETENCIA} SET entregue_em = NULL WHERE id = %s",
            [competencia.pk],
        ),
    )

    assert _linha(Competencia, competencia.pk) == antes


@so_postgresql
def test_competencia_entregue_nao_volta_a_aberta_por_orm(cenario):
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    antes = _linha(Competencia, competencia.pk)

    _recusado(
        RESTRICAO_ENTREGUE_REABRE,
        lambda: Competencia.objects.filter(pk=competencia.pk).update(estado="aberta"),
    )

    assert _linha(Competencia, competencia.pk) == antes


@so_postgresql
def test_reabertura_completa_por_sql_em_competencia_entregue_e_recusada(cenario):
    """Cenário negativo do plano: a "reabertura completa" por SQL — a que
    imita `reabrir_competencia`, zerando `fechada_*` junto — também é recusada."""
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    antes = _linha(Competencia, competencia.pk)

    _recusado(
        RESTRICAO_ENTREGUE_REABRE,
        lambda: _sql(
            f"UPDATE {TABELA_COMPETENCIA} SET estado = 'aberta', fechada_em = NULL, "
            "fechada_por_id = NULL WHERE id = %s",
            [competencia.pk],
        ),
    )

    assert _linha(Competencia, competencia.pk) == antes


@so_postgresql
def test_update_que_zera_a_entrega_e_reabre_de_uma_vez_e_recusado(cenario):
    """As duas travas juntas: a primeira (a entrega não volta a NULL) é a que
    nomeia a restrição, e nenhuma das duas mudanças passa."""
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    antes = _linha(Competencia, competencia.pk)

    _recusado(
        RESTRICAO_ENTREGUE_NULL,
        lambda: Competencia.objects.filter(pk=competencia.pk).update(
            entregue_em=None, estado="aberta"
        ),
    )

    assert _linha(Competencia, competencia.pk) == antes


def test_entrega_repetida_atualiza_a_data_e_passa(cenario):
    """A entrega pode repetir-se (balancete, depois ECD): o serviço ATUALIZA
    `entregue_em` para o evento mais recente, e isso continua permitido."""
    gestor = _entregue(cenario)
    primeira = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3).entregue_em

    marcar_competencia_como_entregue(empresa=cenario["empresa"], ano=2026, mes=3, usuario=gestor)

    segunda = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3).entregue_em
    assert segunda >= primeira


@so_postgresql
def test_entregar_de_novo_por_sql_atualiza_a_data_e_passa(cenario):
    """O par do anterior, por SQL: gravar uma data NOVA é a entrega seguinte,
    não o desfazimento da anterior — só o NULL é recusado."""
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)
    nova_data = timezone.now()

    _sql(
        f"UPDATE {TABELA_COMPETENCIA} SET entregue_em = %s WHERE id = %s",
        [nova_data, competencia.pk],
    )

    competencia.refresh_from_db()
    assert competencia.entregue_em == nova_data


# ---------------------------------------------------------------------------
# Critério 6 — a recusa vira mensagem em português pelo tradutor do projeto
# ---------------------------------------------------------------------------


def test_as_restricoes_da_fatia_2_estao_registradas_em_portugues():
    for nome in RESTRICOES_DA_CONTABILIDADE:
        mensagem = MENSAGENS_DE_RESTRICAO_DE_GATILHO[nome]
        assert mensagem.strip() and mensagem.endswith(".")
        # Sem jargão de banco: o contador lê esta frase.
        assert not {"trigger", "gatilho", "constraint", "SQL"} & set(mensagem.split())
    assert "competência" in MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_LANCAMENTO]
    assert "entrega" in MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_ENTREGUE_NULL]
    assert "RC-101" in MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_ENTREGUE_REABRE]
    # `mensagens_de_gatilho` levanta KeyError para nome fora do registro: é a
    # prova de que o nome que a migração grava é o que o tradutor procura.
    assert set(mensagens_de_gatilho(*RESTRICOES_DA_CONTABILIDADE)) == set(
        RESTRICOES_DA_CONTABILIDADE
    )


@so_postgresql
def test_o_tradutor_converte_a_recusa_real_do_banco_na_mensagem_registrada(cenario):
    """O nome que o gatilho informa tem de ser o que o registro traduz —
    medido com a recusa de VERDADE, uma por restrição."""
    _competencia_com_estado(cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA)
    with pytest.raises(RestricaoViolada) as do_lancamento:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            _lancamento_direto(cenario, data=date(2026, 3, 10))

    _entregue(cenario, ano=2026, mes=4, prefixo="entregue-tradutor")
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=4)
    with pytest.raises(RestricaoViolada) as do_null:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            Competencia.objects.filter(pk=competencia.pk).update(entregue_em=None)
    with pytest.raises(RestricaoViolada) as do_reabre:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            Competencia.objects.filter(pk=competencia.pk).update(estado="aberta")

    for erro, nome in (
        (do_lancamento, RESTRICAO_LANCAMENTO),
        (do_null, RESTRICAO_ENTREGUE_NULL),
        (do_reabre, RESTRICAO_ENTREGUE_REABRE),
    ):
        assert erro.value.nome == nome
        assert str(erro.value) == MENSAGENS_DE_RESTRICAO_DE_GATILHO[nome]


# ---------------------------------------------------------------------------
# Critério 8 — mutação: sem o gatilho, os testes de recusa caem
# ---------------------------------------------------------------------------


@so_postgresql
def test_sem_o_gatilho_a_escrita_em_periodo_encerrado_passa(cenario):
    """É o que prova que era o GATILHO quem recusava: desligado só ele, a
    mesma escrita passa — e religado, a recusa volta."""
    _competencia_com_estado(cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA)

    with gatilho_desligado(GATILHO_INSERT_LANCAMENTO):
        lancamento = _lancamento_direto(cenario, data=date(2026, 3, 10))
        assert LancamentoContabil.objects.filter(pk=lancamento.pk).exists()

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 11)),
    )


@so_postgresql
def test_sem_o_gatilho_a_entrega_se_desfaz(cenario):
    _entregue(cenario)
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=3)

    with gatilho_desligado(GATILHO_UPDATE_COMPETENCIA):
        atualizadas = Competencia.objects.filter(pk=competencia.pk).update(entregue_em=None)
        assert atualizadas == 1

    competencia.refresh_from_db()
    assert competencia.entregue_em is None  # o gatilho desligado deixou


# ---------------------------------------------------------------------------
# Critérios 10/11 — migração reversível; SQLite é no-op declarado
# ---------------------------------------------------------------------------

ANTERIOR = [("contabilidade", "0022_alter_conta_item_de_resultado_sem_caixa")]
ESTA = "0023_dl069_periodo_encerrado_recusa_insert"

# Os DOIS gatilhos que esta migração cria (o de INSERT do lançamento e o de
# UPDATE da competência): a reversão precisa levar os dois embora, e as
# asserções de ida/volta abaixo cobrem o conjunto inteiro — o mesmo cuidado do
# `GATILHOS_ESPERADOS` da fatia 1 (auditoria R1: sem o segundo nome, uma
# reversão que deixasse o gatilho de UPDATE para trás continuaria verde).
GATILHOS_ESPERADOS = {
    "trg_lancamento_contabil_so_em_competencia_aberta",
    "trg_competencia_entregue_protegida",
}
FUNCOES_ESPERADAS = {
    "contabilidade_recusar_lancamento_fora_de_competencia_aberta",
    "contabilidade_proteger_entrega_da_competencia",
}


def _gatilhos_da_fatia_2():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            f"AND tgrelid IN ('{TABELA_LANCAMENTO}'::regclass, '{TABELA_COMPETENCIA}'::regclass)"
        )
        return {linha[0] for linha in cursor.fetchall()}


def _funcoes_da_fatia_2():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT proname FROM pg_proc WHERE proname = ANY(%s)", [list(FUNCOES_ESPERADAS)]
        )
        return {linha[0] for linha in cursor.fetchall()}


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_migracao_e_reversivel_e_depois_de_voltar_a_escrita_passa(cenario):
    from django.db.migrations.executor import MigrationExecutor

    executor = MigrationExecutor(connection)
    alvo_atual = executor.loader.graph.leaf_nodes("contabilidade")
    assert ("contabilidade", ESTA) in executor.loader.applied_migrations
    assert GATILHOS_ESPERADOS <= _gatilhos_da_fatia_2()
    assert _funcoes_da_fatia_2() == FUNCOES_ESPERADAS

    _competencia_com_estado(cenario, ano=2026, mes=3, estado=EstadoCompetencia.ENCERRADA)

    try:
        MigrationExecutor(connection).migrate(ANTERIOR)

        assert not (GATILHOS_ESPERADOS & _gatilhos_da_fatia_2())
        assert _funcoes_da_fatia_2() == set()
        # Sem o gatilho, o INSERT passa — é o que prova que era ele quem
        # recusava (a mutação derruba os testes de recusa acima). Modelo HISTÓRICO do
        # estado ANTERIOR: o atual tem a coluna `origem` (DL-089), que a janela não tem.
        lancamento = _lancamento_direto(
            cenario, data=date(2026, 3, 10), esquema=modelos_do_esquema(ANTERIOR)
        )
        assert LancamentoContabil.objects.filter(pk=lancamento.pk).exists()
    finally:
        MigrationExecutor(connection).migrate(alvo_atual)

    # Para a frente de novo: gatilho de volta e a recusa volta junto.
    assert GATILHOS_ESPERADOS <= _gatilhos_da_fatia_2()
    assert _funcoes_da_fatia_2() == FUNCOES_ESPERADAS
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _lancamento_direto(cenario, data=date(2026, 3, 11)),
    )


def test_a_migracao_e_no_op_fora_do_postgresql():
    """Critério 10: em SQLite as travas não existem, e a migração declara isso
    por não emitir SQL nenhum — nem na ida, nem na volta. Vale em qualquer
    banco (não é um teste de gatilho; é do no-op)."""
    migracao = importlib.import_module(f"apps.contabilidade.migrations.{ESTA}")

    class _Conexao:
        vendor = "sqlite"

    class _EditorQueNaoDeveExecutar:
        connection = _Conexao()

        def execute(self, *args, **kwargs):
            raise AssertionError("a migração emitiu SQL fora do PostgreSQL")

    editor = _EditorQueNaoDeveExecutar()
    migracao._criar_gatilhos(None, editor)
    migracao._remover_gatilhos(None, editor)
