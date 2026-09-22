"""DL-033, fatia 1 — critério 6 do plano: a migração 0007 (que adiciona
`Conta.classificacao_patrimonial`) NÃO classifica conta nenhuma e NÃO muda
saldo nenhum, mesmo sobre uma base COM DADOS pré-existentes.

Mesmo padrão de `test_criterio11_migracao_0006_sobre_base_com_dados_nao_
altera_competencia_existente` (`test_dl016_fatia1_fechamento_reabertura_
entrega.py`): volta o schema da `contabilidade` para ANTES desta migração,
grava contas e um lançamento com o modelo HISTÓRICO (sem o campo novo),
reaplica a migração e confere com o modelo ATUAL.

⚠️ **Ao contrário da DL-032, esta etapa TEM migração** — é por isso que este
teste existe: a DL-032 só mudava a CAMADA de leitura, sem `AddField` nenhum.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import Conta, TipoPartida
from apps.contabilidade.services import apurar_saldos, criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_criterio6_migracao_0007_nao_classifica_conta_existente_nem_muda_saldo():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    escritorio = Escritorio.objects.create(nome="Escritório Migração DL-033", cnpj="40404040000140")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Migração DL-033 Ltda", cnpj="40404040000141"
    )

    # `alvo_anterior` fica HARDCODED de propósito — ele nomeia "antes desta
    # migração ESPECÍFICA" (0007), e é exatamente essa migração que este
    # teste existe para verificar. `alvo_atual` NÃO pode ser hardcoded
    # (BL-489, achado A4 da auditoria: o mesmo literal que a correção da
    # DL-016 acabara de trocar por `leaf_nodes` foi REINTRODUZIDO aqui, um
    # commit depois — o auditor provou o dano simulando uma migração `0008`
    # e medindo que o `finally` abaixo deixava o schema sem a coluna nova
    # pelo resto da execução, derrubando testes de outro arquivo).
    # `leaf_nodes(...)` lê a migração mais recente do GRAFO em tempo de
    # execução — nunca mais fica desatualizado quando a `contabilidade`
    # ganhar a próxima migração.
    alvo_anterior = [("contabilidade", "0006_fechamento_reabertura_e_entrega_de_competencia")]
    alvo_atual = MigrationExecutor(db_connection).loader.graph.leaf_nodes("contabilidade")
    try:
        # Volta o SCHEMA da `contabilidade` para ANTES desta migração — a
        # coluna `classificacao_patrimonial` não existe na tabela ainda.
        MigrationExecutor(db_connection).migrate(alvo_anterior)

        # Modelo HISTÓRICO, congelado em 0006 — NUNCA o `Conta` importado no
        # topo deste arquivo, que já tem o campo novo e quebraria o INSERT
        # contra o schema antigo (a coluna simplesmente não existe ainda).
        apps_antigos = MigrationExecutor(db_connection).loader.project_state(alvo_anterior).apps
        ContaAntes = apps_antigos.get_model("contabilidade", "Conta")
        caixa_antes = ContaAntes.objects.create(
            empresa_id=empresa.id, codigo="1", nome="Caixa", tipo="ativo", natureza="devedora"
        )
        capital_antes = ContaAntes.objects.create(
            empresa_id=empresa.id,
            codigo="3",
            nome="Capital",
            tipo="patrimonio_liquido",
            natureza="credora",
        )
        caixa_id, capital_id = caixa_antes.pk, capital_antes.pk
    finally:
        # SEMPRE volta ao estado mais recente antes de sair — inclusive se
        # uma asserção falhar abaixo.
        MigrationExecutor(db_connection).migrate(alvo_atual)

    # Lançamento criado DEPOIS de voltar ao schema ATUAL — as tabelas de
    # lançamento não mudam nesta migração, então o service normal serve.
    caixa = Conta.objects.get(pk=caixa_id)
    capital = Conta.objects.get(pk=capital_id)
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 15),
        historico="Movimento pré-existente à migração",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
        ],
    )

    caixa.refresh_from_db()
    capital.refresh_from_db()
    # O ponto central do critério 6: NENHUMA conta pré-existente nasce
    # classificada — nenhum `RunPython` desta migração adivinha grupo
    # nenhum a partir do código ou do nome da conta.
    assert caixa.classificacao_patrimonial is None
    assert capital.classificacao_patrimonial is None

    # E nenhum saldo muda: a conta corrente com 1.000,00 e o capital com
    # 1.000,00, exatamente como o lançamento gravou — a migração é
    # estritamente aditiva (só `AddField`, coluna NULL por padrão).
    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))
    linhas = {linha["conta"]: linha for linha in saldos["contas"]}
    assert linhas["1"]["saldo"] == Decimal("1000.00")
    assert linhas["3"]["saldo"] == Decimal("1000.00")
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")
    # E as duas contas, sem classificação nenhuma, são DECLARADAS — nunca
    # silenciosamente ignoradas.
    declaradas = {linha["conta"] for linha in saldos["contas_sem_classificacao_patrimonial"]}
    assert {"1", "3"} & declaradas == {"1"}  # "3" é Patrimônio Líquido — RC-106 não a classifica
