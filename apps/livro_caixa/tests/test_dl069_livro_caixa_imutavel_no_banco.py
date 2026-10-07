"""DL-069, fatia 1 — o lançamento do livro-caixa é imutável NO BANCO.

Antes desta fatia, a imutabilidade do `LancamentoCaixa` só existia em
`save()`/`delete()` do modelo, e o fechamento de mês só tinha a disciplina dos
dois serviços. `QuerySet.update()`, `QuerySet.delete()`, `bulk_update()` e SQL
direto passavam por cima. A migração 0011 cria os gatilhos (padrão da 0013 da
contabilidade, DL-052).

Critérios do plano cobertos (números do plano):

1. `LancamentoCaixa`: `update()` de qualquer coluna, `UPDATE` por SQL,
   `QuerySet.delete()` e `DELETE` por SQL recusados, e o dado não muda.
2. `FechamentoMesCaixa`: DELETE (ORM e SQL) recusado; UPDATE de `empresa_id`,
   `ano`, `mes` ou `criado_em` recusado.
3. Encerrar, reabrir, a cascata da DL-054, lançar e estornar continuam
   funcionando (e a suíte existente de `apps/livro_caixa` passa com o gatilho
   LIGADO — é a prova de que nenhuma outra porta do produto faz UPDATE/DELETE
   nessas tabelas).
4. A recusa chega traduzida: as duas restrições estão em
   `MENSAGENS_DE_RESTRICAO_DE_GATILHO` e é o tradutor `restricao_como_400` que
   as converte. NENHUMA porta do produto (tela, API, admin) faz UPDATE ou
   DELETE no lançamento — ver `test_admin_*` e os testes positivos —, então não
   há requisição que provoque a recusa; o que se prova é que a mensagem existe,
   está em português e é a usada pelo tradutor quando o banco recusa de verdade.
5. A migração é reversível (migra para trás e para frente; depois de voltar o
   UPDATE passa).
6. Em SQLite as travas não existem: os testes de recusa são PULADOS, com o
   motivo declarado, e o no-op da migração é testado.

Dados 100% sintéticos.
"""

# ruff: noqa: F811
# (a fixture `cenario` importada é usada como parâmetro, o padrão do repositório)
import importlib
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO_DE_GATILHO,
    RestricaoViolada,
    mensagens_de_gatilho,
    restricao_como_400,
)
from apps.livro_caixa.models import EstadoMesCaixa, FechamentoMesCaixa, LancamentoCaixa
from apps.livro_caixa.services import (
    encerrar_mes_caixa,
    estornar_lancamento_caixa,
    reabrir_mes_caixa,
    reabrir_mes_caixa_em_cascata,
)
from apps.livro_caixa.tests.test_dl053_fechamento_do_mes import (  # noqa: F401
    _encerrar,
    _lancar,
    _reabrir,
    _usuario,
    cenario,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason=(
        "Os gatilhos da migração 0011 (DL-069) existem só em PostgreSQL; em SQLite a "
        "imutabilidade fica na aplicação (limite aceito, como na 0009 e na 0013 da contabilidade)."
    ),
)

TABELA_LANCAMENTO = LancamentoCaixa._meta.db_table
TABELA_FECHAMENTO = FechamentoMesCaixa._meta.db_table

# `(tabela, gatilho)` no formato de `apps.contabilidade.tests.gatilhos_do_livro.
# gatilho_desligado`, para os testes existentes que montam dado "torto" de
# propósito (ver `test_dl046_fatia3_arquivos_carne_leao` e
# `test_dl046_telas_arquivos_carne_leao`).
IMUTAVEL_LANCAMENTO_CAIXA = (TABELA_LANCAMENTO, "trg_lancamento_caixa_imutavel")
IMUTAVEL_FECHAMENTO_CAIXA = (TABELA_FECHAMENTO, "trg_fechamento_mes_caixa_imutavel")

RESTRICAO_LANCAMENTO = "lancamento_caixa_imutavel"
RESTRICAO_FECHAMENTO = "fechamento_mes_caixa_imutavel"


def _nome_da_restricao(erro):
    return erro.value.__cause__.diag.constraint_name


def _linha(modelo, pk):
    """Todas as colunas da linha, para provar que NADA mudou depois da recusa."""
    return modelo.objects.filter(pk=pk).values().get()


def _recusado(restricao, operacao):
    """Executa `operacao()` dentro de um savepoint e exige a recusa do gatilho."""
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic():
            operacao()
    assert _nome_da_restricao(erro) == restricao


def _sql(sql, parametros=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, parametros)


# ---------------------------------------------------------------------------
# Critério 1 — LancamentoCaixa: TODO update e todo delete são recusados
# ---------------------------------------------------------------------------

# Cada caso é uma coluna que o plano ou o modelo apontam como alvo de adulteração.
_ALTERACOES_DO_LANCAMENTO = {
    "valor": lambda c, outro: {"valor": Decimal("1.00")},
    "data": lambda c, outro: {"data": date(2026, 3, 11)},
    "empresa_id": lambda c, outro: {"empresa_id": c["empresa_irma"].id},
    "estorno_de_id": lambda c, outro: {"estorno_de_id": outro.pk},
    "historico": lambda c, outro: {"historico": "Reescrito"},
    "conta_id": lambda c, outro: {"conta_id": c["conta_irma"].id},
    "documento_origem": lambda c, outro: {"documento_origem": "NF-FORJADA"},
    "chave_idempotencia": lambda c, outro: {"chave_idempotencia": "chave-forjada"},
    "criado_por_id": lambda c, outro: {"criado_por_id": None},
    "criado_em": lambda c, outro: {"criado_em": timezone.now() - timedelta(days=400)},
    "valor_irrf": lambda c, outro: {"valor_irrf": Decimal("9.99")},
    "todas_de_uma_vez": lambda c, outro: {
        "valor": Decimal("2.00"),
        "historico": "Tudo de uma vez",
        "data": date(2026, 3, 12),
    },
}


@so_postgresql
@pytest.mark.parametrize("coluna", sorted(_ALTERACOES_DO_LANCAMENTO))
def test_update_de_qualquer_coluna_do_lancamento_e_recusado_e_nada_muda(cenario, coluna):
    lancamento = _lancar(cenario, date(2026, 3, 10))
    outro = _lancar(cenario, date(2026, 3, 11), valor="5.00")
    antes = _linha(LancamentoCaixa, lancamento.pk)
    alteracao = _ALTERACOES_DO_LANCAMENTO[coluna](cenario, outro)

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.filter(pk=lancamento.pk).update(**alteracao),
    )

    assert _linha(LancamentoCaixa, lancamento.pk) == antes


@so_postgresql
def test_update_que_nao_muda_valor_algum_tambem_e_recusado(cenario):
    """ "Recusa TUDO": sem exceção para o UPDATE que regrava os mesmos valores."""
    lancamento = _lancar(cenario, date(2026, 3, 10))

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.filter(pk=lancamento.pk).update(valor=lancamento.valor),
    )


@so_postgresql
def test_bulk_update_do_lancamento_e_recusado_e_nada_muda(cenario):
    lancamento = _lancar(cenario, date(2026, 3, 10))
    antes = _linha(LancamentoCaixa, lancamento.pk)
    lancamento.valor = Decimal("1.00")

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.bulk_update([lancamento], ["valor"]),
    )

    assert _linha(LancamentoCaixa, lancamento.pk) == antes


@so_postgresql
def test_delete_em_massa_do_lancamento_e_recusado_e_nada_some(cenario):
    lancamento = _lancar(cenario, date(2026, 3, 10))
    antes = _linha(LancamentoCaixa, lancamento.pk)

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.filter(pk=lancamento.pk).delete(),
    )
    _recusado(RESTRICAO_LANCAMENTO, lambda: LancamentoCaixa.objects.all().delete())

    assert _linha(LancamentoCaixa, lancamento.pk) == antes


@so_postgresql
@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE {t} SET valor = 1 WHERE id = %s",
        "UPDATE {t} SET empresa_id = empresa_id WHERE id = %s",
        "UPDATE {t} SET estorno_de_id = NULL WHERE id = %s",
        "DELETE FROM {t} WHERE id = %s",
    ],
    ids=["update_valor", "update_sem_mudar_nada", "update_estorno_de", "delete"],
)
def test_sql_direto_no_lancamento_e_recusado_e_nada_muda(cenario, sql):
    lancamento = _lancar(cenario, date(2026, 3, 10))
    antes = _linha(LancamentoCaixa, lancamento.pk)

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: _sql(sql.format(t=TABELA_LANCAMENTO), [lancamento.pk]),
    )

    assert _linha(LancamentoCaixa, lancamento.pk) == antes


@so_postgresql
def test_o_estorno_tambem_e_imutavel_e_o_original_fica_intacto(cenario):
    original = _lancar(cenario, date(2026, 3, 10))
    estorno = estornar_lancamento_caixa(original, criado_por=cenario["gestor"])
    antes = (_linha(LancamentoCaixa, original.pk), _linha(LancamentoCaixa, estorno.pk))

    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.filter(pk=estorno.pk).update(valor=Decimal("1.00")),
    )
    _recusado(RESTRICAO_LANCAMENTO, lambda: LancamentoCaixa.objects.filter(pk=estorno.pk).delete())

    assert (_linha(LancamentoCaixa, original.pk), _linha(LancamentoCaixa, estorno.pk)) == antes


def test_a_guarda_em_python_continua_recusando_antes_do_banco(cenario):
    """O gatilho é a SEGUNDA camada: `save()`/`delete()` do modelo seguem
    recusando por conta própria (vale também em SQLite)."""
    from apps.livro_caixa.models import LancamentoCaixaImutavelError

    lancamento = _lancar(cenario, date(2026, 3, 10))

    with pytest.raises(LancamentoCaixaImutavelError):
        lancamento.save()
    with pytest.raises(LancamentoCaixaImutavelError):
        lancamento.delete()


# ---------------------------------------------------------------------------
# Critério 2 — FechamentoMesCaixa: nunca se apaga; só encerrar/reabrir o atualizam
# ---------------------------------------------------------------------------


def _mes_encerrado(cenario, mes=1):
    return _encerrar(cenario, ano=2026, mes=mes)


def _mes_reaberto(cenario, mes=1):
    _encerrar(cenario, ano=2026, mes=mes)
    return _reabrir(cenario, ano=2026, mes=mes)


@so_postgresql
@pytest.mark.parametrize("estado_do_mes", ["encerrado", "reaberto"])
def test_delete_do_fechamento_e_recusado_em_qualquer_estado(cenario, estado_do_mes):
    fechamento = _mes_encerrado(cenario) if estado_do_mes == "encerrado" else _mes_reaberto(cenario)
    antes = _linha(FechamentoMesCaixa, fechamento.pk)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).delete(),
    )
    _recusado(RESTRICAO_FECHAMENTO, fechamento.delete)
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: _sql(f"DELETE FROM {TABELA_FECHAMENTO} WHERE id = %s", [fechamento.pk]),
    )

    assert _linha(FechamentoMesCaixa, fechamento.pk) == antes


_ALTERACOES_DAS_COLUNAS_IMUTAVEIS = {
    "empresa_id": lambda c: {"empresa_id": c["empresa_irma"].id},
    "ano": lambda c: {"ano": 2027},
    "mes": lambda c: {"mes": 7},
    "criado_em": lambda c: {"criado_em": timezone.now() - timedelta(days=400)},
}


@so_postgresql
@pytest.mark.parametrize("estado_do_mes", ["encerrado", "reaberto"])
@pytest.mark.parametrize("coluna", sorted(_ALTERACOES_DAS_COLUNAS_IMUTAVEIS))
def test_update_de_coluna_imutavel_do_fechamento_e_recusado_e_nada_muda(
    cenario, coluna, estado_do_mes
):
    fechamento = _mes_encerrado(cenario) if estado_do_mes == "encerrado" else _mes_reaberto(cenario)
    antes = _linha(FechamentoMesCaixa, fechamento.pk)
    alteracao = _ALTERACOES_DAS_COLUNAS_IMUTAVEIS[coluna](cenario)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).update(**alteracao),
    )

    assert _linha(FechamentoMesCaixa, fechamento.pk) == antes


@so_postgresql
def test_trocar_fechado_por_ou_fechado_em_de_um_mes_encerrado_por_fora_do_servico_e_recusado(
    cenario,
):
    """Cenário negativo do plano. `fechado_por`/`fechado_em` SÃO colunas que o
    serviço escreve, mas só ao encerrar um mês reaberto; num mês que continua
    encerrado, ninguém os troca."""
    fechamento = _mes_encerrado(cenario)
    outro = _usuario(Papel.GESTOR, cenario["escritorio_a"], "outro")
    antes = _linha(FechamentoMesCaixa, fechamento.pk)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).update(fechado_por_id=outro.pk),
    )
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).update(
            fechado_em=timezone.now() - timedelta(days=30)
        ),
    )

    assert _linha(FechamentoMesCaixa, fechamento.pk) == antes


@so_postgresql
def test_apagar_ou_trocar_a_reabertura_de_um_mes_reaberto_por_fora_do_servico_e_recusado(cenario):
    fechamento = _mes_reaberto(cenario)
    outro = _usuario(Papel.GESTOR, cenario["escritorio_a"], "outro")
    antes = _linha(FechamentoMesCaixa, fechamento.pk)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).update(
            motivo_reabertura="Motivo reescrito depois"
        ),
    )
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=fechamento.pk).update(
            reaberto_por_id=outro.pk
        ),
    )

    assert _linha(FechamentoMesCaixa, fechamento.pk) == antes


@so_postgresql
def test_transicao_legitima_com_coluna_de_fora_da_transicao_e_recusada(cenario):
    """Reabrir mexe em `reaberto_*`/`motivo_reabertura`, nunca em `fechado_*`;
    encerrar mexe em `fechado_*`, nunca em `motivo_reabertura`. Misturar é
    adulterar o histórico do período."""
    outro = _usuario(Papel.GESTOR, cenario["escritorio_a"], "outro")
    encerrado = _mes_encerrado(cenario, mes=1)
    reaberto = _mes_reaberto(cenario, mes=2)
    antes = (_linha(FechamentoMesCaixa, encerrado.pk), _linha(FechamentoMesCaixa, reaberto.pk))
    agora = timezone.now()

    # Reabertura que também troca quem fechou.
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=encerrado.pk).update(
            estado=EstadoMesCaixa.ABERTO,
            reaberto_em=agora,
            reaberto_por_id=outro.pk,
            motivo_reabertura="Reabertura com adulteração",
            fechado_por_id=outro.pk,
        ),
    )
    # Reabertura que também muda o mês.
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=encerrado.pk).update(
            estado=EstadoMesCaixa.ABERTO,
            reaberto_em=agora,
            reaberto_por_id=outro.pk,
            motivo_reabertura="Reabertura com adulteração",
            mes=8,
        ),
    )
    # Reencerramento que também apaga a reabertura anterior.
    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=reaberto.pk).update(
            estado=EstadoMesCaixa.ENCERRADO,
            fechado_em=agora,
            fechado_por_id=outro.pk,
            motivo_reabertura="Reabertura anterior reescrita",
        ),
    )

    assert (
        _linha(FechamentoMesCaixa, encerrado.pk),
        _linha(FechamentoMesCaixa, reaberto.pk),
    ) == antes


@so_postgresql
def test_update_que_regrava_os_mesmos_valores_do_fechamento_nao_altera_nada_e_passa(cenario):
    fechamento = _mes_encerrado(cenario)
    antes = _linha(FechamentoMesCaixa, fechamento.pk)

    _sql(f"UPDATE {TABELA_FECHAMENTO} SET estado = estado WHERE id = %s", [fechamento.pk])

    assert _linha(FechamentoMesCaixa, fechamento.pk) == antes


# ---------------------------------------------------------------------------
# Critério 3 — o que o produto faz continua funcionando (gatilho LIGADO)
# ---------------------------------------------------------------------------


def test_lancar_estornar_encerrar_reabrir_cascata_e_reencerrar_continuam_funcionando(cenario):
    """O ciclo inteiro de escrita do livro-caixa, pelos serviços. Em PostgreSQL
    roda com o gatilho ligado; em SQLite é o mesmo roteiro sem gatilho."""
    original = _lancar(cenario, date(2026, 1, 10))
    estorno = estornar_lancamento_caixa(original, criado_por=cenario["gestor"])
    assert estorno.estorno_de_id == original.pk

    # INSERT do fechamento (nenhum UPDATE ainda).
    for mes in (1, 2, 3):
        _encerrar(cenario, ano=2026, mes=mes)
    assert {f.mes: f.estado for f in FechamentoMesCaixa.objects.all()} == {
        1: EstadoMesCaixa.ENCERRADO,
        2: EstadoMesCaixa.ENCERRADO,
        3: EstadoMesCaixa.ENCERRADO,
    }

    # Cascata da DL-054: janeiro reabre junto com fevereiro e março (UPDATE de
    # reabertura em três linhas, na mesma transação).
    reabertos = reabrir_mes_caixa_em_cascata(
        empresa=cenario["empresa"],
        ano=2026,
        mes=1,
        usuario=cenario["gestor"],
        motivo="Corrigir despesa de janeiro lançada a menos",
        meses_confirmados={(2026, 2), (2026, 3)},
    )
    assert [f.mes for f in reabertos] == [1, 2, 3]
    assert {f.estado for f in FechamentoMesCaixa.objects.all()} == {EstadoMesCaixa.ABERTO}

    # Mês reaberto aceita lançamento de novo; o estorno também.
    novo = _lancar(cenario, date(2026, 1, 20), valor="30.00")
    estornar_lancamento_caixa(novo, criado_por=cenario["gestor"])

    # Reencerrar reaproveita a linha: UPDATE de `fechado_em`/`fechado_por` por OUTRO
    # usuário (aberto -> encerrado).
    outro = _usuario(Papel.GESTOR, cenario["escritorio_a"], "outro")
    refeito = encerrar_mes_caixa(empresa=cenario["empresa"], ano=2026, mes=1, usuario=outro)
    assert refeito.estado == EstadoMesCaixa.ENCERRADO
    assert FechamentoMesCaixa.objects.get(mes=1).fechado_por_id == outro.pk

    # Reabertura simples (encerrado -> aberto, motivo novo sobrescreve o anterior).
    reaberto = reabrir_mes_caixa(
        empresa=cenario["empresa"],
        ano=2026,
        mes=1,
        usuario=cenario["gestor"],
        motivo="Segundo motivo, escrito pelo serviço",
    )
    assert reaberto.estado == EstadoMesCaixa.ABERTO
    assert reaberto.motivo_reabertura == "Segundo motivo, escrito pelo serviço"
    assert LancamentoCaixa.objects.filter(empresa=cenario["empresa"]).count() == 4


# ---------------------------------------------------------------------------
# Critério 4 — a recusa vira mensagem em português pelo tradutor do projeto
# ---------------------------------------------------------------------------


def test_as_duas_restricoes_estao_registradas_com_mensagem_em_portugues_para_o_contador():
    for nome in (RESTRICAO_LANCAMENTO, RESTRICAO_FECHAMENTO):
        mensagem = MENSAGENS_DE_RESTRICAO_DE_GATILHO[nome]
        assert mensagem.strip() and mensagem.endswith(".")
        # Sem jargão de banco: o contador lê esta frase.
        assert not {"trigger", "gatilho", "constraint", "SQL"} & set(mensagem.split())
    assert "estorno" in MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_LANCAMENTO]
    assert "reabertura" in MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_FECHAMENTO]
    # `mensagens_de_gatilho` levanta KeyError para nome fora do registro: é a prova
    # de que o nome que a migração grava é o que o tradutor procura.
    assert set(mensagens_de_gatilho(RESTRICAO_LANCAMENTO, RESTRICAO_FECHAMENTO)) == {
        RESTRICAO_LANCAMENTO,
        RESTRICAO_FECHAMENTO,
    }


@so_postgresql
def test_o_tradutor_converte_a_recusa_real_do_banco_na_mensagem_registrada(cenario):
    """Nenhuma porta do produto emite UPDATE/DELETE aqui; este teste faz o banco
    recusar DE VERDADE e passa o erro pelo MESMO tradutor que o admin de empresas
    usa para os gatilhos (`restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO)`):
    o nome que o gatilho informa tem de ser o que o registro traduz."""
    lancamento = _lancar(cenario, date(2026, 3, 10))
    fechamento = _mes_encerrado(cenario)

    with pytest.raises(RestricaoViolada) as do_lancamento:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            LancamentoCaixa.objects.filter(pk=lancamento.pk).update(valor=Decimal("1.00"))
    with pytest.raises(RestricaoViolada) as do_fechamento:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO_DE_GATILHO):
            fechamento.delete()

    assert do_lancamento.value.nome == RESTRICAO_LANCAMENTO
    assert str(do_lancamento.value) == MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_LANCAMENTO]
    assert do_fechamento.value.nome == RESTRICAO_FECHAMENTO
    assert str(do_fechamento.value) == MENSAGENS_DE_RESTRICAO_DE_GATILHO[RESTRICAO_FECHAMENTO]


def test_o_admin_nao_oferece_alterar_nem_apagar_lancamento_do_livro_caixa(cenario, client):
    """A única porta de interface que poderia emitir UPDATE/DELETE em lançamento
    é o admin; ele recusa antes do banco (403), e a linha continua lá."""
    lancamento = _lancar(cenario, date(2026, 3, 10))
    antes = _linha(LancamentoCaixa, lancamento.pk)
    superusuario = get_user_model().objects.create_superuser(
        username="super-dl069", email="super-dl069@escritorio.com.br", password="senha-forte-123"
    )
    client.force_login(superusuario)
    base = f"/admin/livro_caixa/lancamentocaixa/{lancamento.pk}"

    assert client.get(f"{base}/delete/").status_code == 403
    assert client.post(f"{base}/delete/", {"post": "yes"}).status_code == 403
    assert client.post(f"{base}/change/", {"historico": "Reescrito"}).status_code == 403

    assert _linha(LancamentoCaixa, lancamento.pk) == antes


# ---------------------------------------------------------------------------
# Critério 5 — a migração é reversível; Critério 6 — SQLite é no-op declarado
# ---------------------------------------------------------------------------

ANTERIOR = [("livro_caixa", "0010_dl053_fechamento_de_mes_do_livro_caixa")]
ESTA = "0011_dl069_livro_caixa_imutavel_no_banco"

GATILHOS_ESPERADOS = {"trg_lancamento_caixa_imutavel", "trg_fechamento_mes_caixa_imutavel"}
FUNCOES_ESPERADAS = (
    "livro_caixa_recusar_alteracao_do_lancamento",
    "livro_caixa_recusar_alteracao_do_fechamento",
)


def _gatilhos_do_livro_caixa():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal "
            "AND tgrelid IN (%s::regclass, %s::regclass)",
            [TABELA_LANCAMENTO, TABELA_FECHAMENTO],
        )
        return {linha[0] for linha in cursor.fetchall()}


def _funcoes_do_livro_caixa():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT proname FROM pg_proc WHERE proname = ANY(%s)", [list(FUNCOES_ESPERADAS)]
        )
        return {linha[0] for linha in cursor.fetchall()}


@so_postgresql
@pytest.mark.django_db(transaction=True)
def test_migracao_e_reversivel_e_depois_de_voltar_o_update_passa(cenario):
    from django.db.migrations.executor import MigrationExecutor

    alvo_atual = MigrationExecutor(connection).loader.graph.leaf_nodes("livro_caixa")
    assert ("livro_caixa", ESTA) in alvo_atual, "a 0011 deve ser a folha do app"
    assert _gatilhos_do_livro_caixa() == GATILHOS_ESPERADOS
    assert _funcoes_do_livro_caixa() == set(FUNCOES_ESPERADAS)

    lancamento = _lancar(cenario, date(2026, 3, 10))
    fechamento = _mes_encerrado(cenario)

    try:
        MigrationExecutor(connection).migrate(ANTERIOR)

        assert not (GATILHOS_ESPERADOS & _gatilhos_do_livro_caixa())
        assert _funcoes_do_livro_caixa() == set()
        # Sem o gatilho, o UPDATE passa — é o que prova que era ele que recusava.
        atualizados = LancamentoCaixa.objects.filter(pk=lancamento.pk).update(
            historico="Alterado com a migração revertida"
        )
        assert atualizados == 1
        assert (
            LancamentoCaixa.objects.get(pk=lancamento.pk).historico
            == "Alterado com a migração revertida"
        )
    finally:
        MigrationExecutor(connection).migrate(alvo_atual)

    # Para a frente de novo: gatilhos de volta e a recusa volta junto.
    assert _gatilhos_do_livro_caixa() == GATILHOS_ESPERADOS
    assert _funcoes_do_livro_caixa() == set(FUNCOES_ESPERADAS)
    _recusado(
        RESTRICAO_LANCAMENTO,
        lambda: LancamentoCaixa.objects.filter(pk=lancamento.pk).update(historico="De novo"),
    )
    _recusado(RESTRICAO_FECHAMENTO, fechamento.delete)


def test_a_migracao_e_no_op_fora_do_postgresql():
    """Critério 6: em SQLite as travas não existem, e a migração declara isso por
    não emitir SQL nenhum — nem na ida, nem na volta. Vale em qualquer banco."""
    migracao = importlib.import_module(f"apps.livro_caixa.migrations.{ESTA}")

    class _Conexao:
        vendor = "sqlite"

    class _EditorQueNaoDeveExecutar:
        connection = _Conexao()

        def execute(self, *args, **kwargs):
            raise AssertionError("a migração emitiu SQL fora do PostgreSQL")

    editor = _EditorQueNaoDeveExecutar()
    migracao._criar_gatilhos(None, editor)
    migracao._remover_gatilhos(None, editor)


@so_postgresql
@pytest.mark.parametrize("coluna", sorted(_ALTERACOES_DAS_COLUNAS_IMUTAVEIS))
def test_reencerramento_com_coluna_imutavel_junto_e_recusado(cenario, coluna):
    """A2 da auditoria da DL-069, fatia 1: a transição de ENCERRAMENTO
    (`aberto→encerrado`, num mês reaberto) também não pode levar de carona
    `empresa_id`, `ano`, `mes` nem `criado_em`. Sem este teste, a mutação que
    acrescentava `criado_em` às colunas permitidas do encerramento sobrevivia
    aos 41 testes da fatia."""
    reaberto = _mes_reaberto(cenario)
    antes = _linha(FechamentoMesCaixa, reaberto.pk)
    alteracao = _ALTERACOES_DAS_COLUNAS_IMUTAVEIS[coluna](cenario)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=reaberto.pk).update(
            estado=EstadoMesCaixa.ENCERRADO,
            fechado_em=timezone.now(),
            fechado_por_id=cenario["gestor"].pk,
            **alteracao,
        ),
    )

    assert _linha(FechamentoMesCaixa, reaberto.pk) == antes


@so_postgresql
@pytest.mark.parametrize("coluna", sorted(_ALTERACOES_DAS_COLUNAS_IMUTAVEIS))
def test_reabertura_com_coluna_imutavel_junto_e_recusada(cenario, coluna):
    """O par simétrico do anterior: a transição de REABERTURA
    (`encerrado→aberto`) também não leva coluna imutável de carona."""
    encerrado = _mes_encerrado(cenario)
    antes = _linha(FechamentoMesCaixa, encerrado.pk)
    alteracao = _ALTERACOES_DAS_COLUNAS_IMUTAVEIS[coluna](cenario)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=encerrado.pk).update(
            estado=EstadoMesCaixa.ABERTO,
            reaberto_em=timezone.now(),
            reaberto_por_id=cenario["gestor"].pk,
            motivo_reabertura="Reabertura com coluna imutável de carona",
            **alteracao,
        ),
    )

    assert _linha(FechamentoMesCaixa, encerrado.pk) == antes


@so_postgresql
@pytest.mark.parametrize("coluna", ["reaberto_em", "reaberto_por_id"])
def test_reencerramento_nao_reescreve_a_reabertura_anterior(cenario, coluna):
    """R2 da reconferência da DL-069, fatia 1: o ENCERRAMENTO de um mês
    reaberto não pode reescrever quando nem por quem ele foi reaberto. Essa é
    a trilha da reabertura anterior, e o reencerramento do serviço a preserva
    (`services.py`, `save(update_fields=[estado, fechado_em, fechado_por])`)."""
    outro = _usuario(Papel.GESTOR, cenario["escritorio_a"], f"outro-{coluna}")
    reaberto = _mes_reaberto(cenario)
    antes = _linha(FechamentoMesCaixa, reaberto.pk)
    novo = {
        "reaberto_em": timezone.now() - timedelta(days=30),
        "reaberto_por_id": outro.pk,
    }[coluna]

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=reaberto.pk).update(
            estado=EstadoMesCaixa.ENCERRADO,
            fechado_em=timezone.now(),
            fechado_por_id=cenario["gestor"].pk,
            **{coluna: novo},
        ),
    )

    assert _linha(FechamentoMesCaixa, reaberto.pk) == antes


@so_postgresql
def test_reabertura_nao_reescreve_quando_o_mes_foi_fechado(cenario):
    """O par simétrico: a REABERTURA não reescreve `fechado_em`, que é o
    registro de quando o mês foi encerrado."""
    encerrado = _mes_encerrado(cenario)
    antes = _linha(FechamentoMesCaixa, encerrado.pk)

    _recusado(
        RESTRICAO_FECHAMENTO,
        lambda: FechamentoMesCaixa.objects.filter(pk=encerrado.pk).update(
            estado=EstadoMesCaixa.ABERTO,
            reaberto_em=timezone.now(),
            reaberto_por_id=cenario["gestor"].pk,
            motivo_reabertura="Reabertura que reescreve o fechamento",
            fechado_em=timezone.now() - timedelta(days=30),
        ),
    )

    assert _linha(FechamentoMesCaixa, encerrado.pk) == antes
