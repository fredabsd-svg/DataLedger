"""Testes da correção dos bloqueadores BL-40 e BL-41 (plano DL-007).

Cobre os 10 cenários da tabela "Cenários de teste" do plano. Dados 100%
sintéticos, criados nos próprios testes.
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.contabilidade.serializers import ContaSerializer
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    LancamentoInvalido,
    _impressao_digital,
    criar_lancamento,
    estornar_lancamento,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    """Duas empresas no MESMO escritório, e uma terceira em OUTRO escritório.

    Necessário para cobrir a distinção do BL-40: a fronteira de isolamento é a
    empresa, não apenas o escritório.
    """
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_c = Escritorio.objects.create(nome="Escritório C", cnpj="33333333000133")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa B Ltda", cnpj="44455566000183"
    )
    empresa_c = Empresa.objects.create(
        escritorio=escritorio_c, razao_social="Empresa C Ltda", cnpj="77788899000122"
    )
    caixa_a = Conta.objects.create(
        empresa=empresa_a,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital_a = Conta.objects.create(
        empresa=empresa_a,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    conta_b = Conta.objects.create(
        empresa=empresa_b,
        codigo="1.1",
        nome="Caixa B",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_c = Conta.objects.create(
        empresa=empresa_c,
        codigo="1.1",
        nome="Caixa C",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    return {
        "escritorio_a": escritorio_a,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "empresa_c": empresa_c,
        "caixa_a": caixa_a,
        "capital_a": capital_a,
        "conta_b": conta_b,
        "conta_c": conta_c,
    }


# --- BL-40: conta_pai atravessa empresa -------------------------------------


def test_conta_pai_de_outra_empresa_mesmo_escritorio_retorna_400(client, cenario):
    """conta_pai de outra empresa DO MESMO escritório -> 400, nada criado."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "1.1.1",
            "nome": "Sub caixa",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": cenario["conta_b"].id,
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert not Conta.objects.filter(empresa=cenario["empresa_a"], codigo="1.1.1").exists()


def test_conta_pai_de_outra_empresa_outro_escritorio_nao_cria_conta(client, cenario):
    """conta_pai de outra empresa de OUTRO escritório -> 400 ou 404, nada criado."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "1.1.1",
            "nome": "Sub caixa",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": cenario["conta_c"].id,
        },
        content_type="application/json",
    )

    assert response.status_code in (400, 404)
    assert not Conta.objects.filter(empresa=cenario["empresa_a"], codigo="1.1.1").exists()


def test_conta_pai_da_propria_empresa_e_aceita(client, cenario):
    """conta_pai da própria empresa continua funcionando (sem regressão)."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "1.1.1",
            "nome": "Sub caixa",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": cenario["caixa_a"].id,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    conta_criada = Conta.objects.get(empresa=cenario["empresa_a"], codigo="1.1.1")
    assert conta_criada.conta_pai_id == cenario["caixa_a"].id


def test_conta_pai_nulo_e_aceito(client, cenario):
    """conta_pai ausente continua aceito (sem regressão)."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:contas", args=[cenario["empresa_a"].id]),
        data={
            "codigo": "3",
            "nome": "Receitas",
            "tipo": TipoConta.RECEITA,
            "natureza": NaturezaConta.CREDORA,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert Conta.objects.get(empresa=cenario["empresa_a"], codigo="3").conta_pai_id is None


def test_validate_conta_pai_falha_fechada_sem_empresa_no_contexto(cenario):
    """Controle de isolamento entre empresas tem que falhar FECHADO.

    Se algum código futuro reaproveitar `ContaSerializer` sem popular
    `context["empresa"]`, a validação de `conta_pai` não pode ser
    silenciosamente ignorada — isso reabriria o BL-40 sem que nenhum teste de
    view acusasse (nenhuma view real chegaria a esse estado hoje). Testamos o
    serializer isoladamente, sem contexto, para provar que ele recusa.
    """
    serializer = ContaSerializer(
        data={
            "codigo": "9",
            "nome": "Conta qualquer",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": cenario["caixa_a"].id,
        },
        context={},
    )

    assert not serializer.is_valid()
    assert "conta_pai" in serializer.errors


def test_validate_conta_pai_sem_empresa_no_contexto_mas_sem_conta_pai_e_aceito(cenario):
    """Sem `conta_pai` no payload, a ausência de empresa no contexto é irrelevante."""
    serializer = ContaSerializer(
        data={
            "codigo": "9",
            "nome": "Conta qualquer",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
        },
        context={},
    )

    assert serializer.is_valid(), serializer.errors


# --- BL-41(a): estorno único -------------------------------------------------


@pytest.fixture
def lancamento_original(cenario):
    return criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Integralização de capital",
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("1000.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("1000.00")},
        ],
    )


def test_segundo_estorno_retorna_400_e_existe_um_unico_estorno(
    client, cenario, lancamento_original
):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:estornar", args=[cenario["empresa_a"].id, lancamento_original.id])

    primeira = client.post(url)
    segunda = client.post(url)

    assert primeira.status_code == 201
    assert segunda.status_code == 400
    assert LancamentoContabil.objects.filter(estorno_de=lancamento_original).count() == 1


def test_estornar_lancamento_duas_vezes_via_servico_recusa_a_segunda(cenario, lancamento_original):
    estornar_lancamento(lancamento_original)

    with pytest.raises(LancamentoInvalido):
        estornar_lancamento(lancamento_original)

    assert LancamentoContabil.objects.filter(estorno_de=lancamento_original).count() == 1


def test_estorno_de_estorno_e_recusado_sem_regressao(cenario, lancamento_original):
    estorno = estornar_lancamento(lancamento_original)

    with pytest.raises(LancamentoInvalido):
        estornar_lancamento(estorno)


def test_constraint_de_banco_impede_dois_estornos_do_mesmo_original(cenario, lancamento_original):
    """Prova que a proteção de BANCO existe, além da checagem prévia do serviço.

    Cria os dois estornos diretamente via `LancamentoContabil.objects.create`,
    contornando `estornar_lancamento` de propósito, para isolar a restrição de
    unicidade (`estorno_de_unico`) do restante da lógica de negócio.
    """
    LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 2),
        historico="Estorno manual 1",
        estorno_de=lancamento_original,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa_a"],
                data=date(2024, 1, 3),
                historico="Estorno manual 2",
                estorno_de=lancamento_original,
            )

    assert LancamentoContabil.objects.filter(estorno_de=lancamento_original).count() == 1


def test_constraint_de_banco_permite_multiplos_lancamentos_sem_estorno(cenario):
    """`estorno_de` nulo em várias linhas continua permitido (NULL não colide).

    Sanidade de uso, não prova de arquitetura: um UNIQUE comum do PostgreSQL
    já aceita múltiplos NULL por padrão, então este teste sobrevive mesmo se
    alguém remover a `condition=` do `UniqueConstraint`. A prova real da
    condição está em `test_indice_parcial_de_estorno_unico_existe_no_banco`
    (achado A6 da auditoria), que inspeciona o catálogo do PostgreSQL.
    """
    primeiro = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 1), historico="Lançamento 1"
    )
    segundo = LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"], data=date(2024, 1, 2), historico="Lançamento 2"
    )

    assert primeiro.estorno_de_id is None
    assert segundo.estorno_de_id is None


def _indexdef(nome_indice):
    with connection.cursor() as cursor:
        cursor.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s", [nome_indice])
        linha = cursor.fetchone()
    return linha[0] if linha else None


def test_indice_parcial_de_estorno_unico_existe_no_banco(cenario):
    """Prova, pelo catálogo do PostgreSQL, que `estorno_de_unico` é um ÍNDICE
    PARCIAL (tem `WHERE`), não um UNIQUE comum (achado A6 da auditoria).

    Um teste que só cria lançamentos com `estorno_de` nulo (o teste anterior)
    não distingue as duas situações, porque o comportamento de UNIQUE comum
    com NULL no PostgreSQL já é esse por padrão. A prova real precisa
    inspecionar `pg_indexes.indexdef`.
    """
    definicao = _indexdef("estorno_de_unico")

    assert definicao is not None, "Índice/constraint 'estorno_de_unico' não existe no banco."
    assert "WHERE" in definicao.upper()


def test_indice_parcial_de_chave_idempotencia_existe_no_banco(cenario):
    """Mesma prova do teste acima, para a constraint de idempotência (A5/A6):
    `chave_idempotencia_unica_por_empresa` também precisa ser um índice
    parcial, não um UNIQUE comum sobre (empresa, chave_idempotencia).
    """
    definicao = _indexdef("chave_idempotencia_unica_por_empresa")

    assert definicao is not None, (
        "Índice/constraint 'chave_idempotencia_unica_por_empresa' não existe no banco."
    )
    assert "WHERE" in definicao.upper()


def test_constraint_de_banco_da_chave_de_idempotencia_existe(cenario):
    """Prova que a unicidade de (empresa, chave_idempotencia) é de BANCO
    (achado A5 da auditoria), não só da checagem prévia do serviço —
    contorna `criar_lancamento` de propósito, criando as duas linhas direto.
    """
    LancamentoContabil.objects.create(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Direto 1",
        chave_idempotencia="chave-direta-banco",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LancamentoContabil.objects.create(
                empresa=cenario["empresa_a"],
                data=date(2024, 1, 2),
                historico="Direto 2",
                chave_idempotencia="chave-direta-banco",
            )

    assert LancamentoContabil.objects.filter(chave_idempotencia="chave-direta-banco").count() == 1


def test_criar_lancamento_direto_com_violacao_de_integridade_nao_mascara_como_does_not_exist(
    cenario,
):
    """Achado A1 (o que ele realmente exigia): violação de integridade que
    não é da chave de idempotência não pode virar `DoesNotExist` — um 500
    disfarçado de outro tipo de 500. Chamar `criar_lancamento` diretamente
    (uso indevido interno, não um caminho real do produto) com `estorno_de`
    já estornado e uma chave de idempotência NOVA (nunca usada) reproduz a
    violação da constraint `estorno_de_unico`; antes da correção A1, o código
    buscava a linha existente com `.get()` e explodia com
    `LancamentoContabil.DoesNotExist`, porque nenhuma linha tem esta chave.

    A expectativa NÃO é `LancamentoInvalido` (uma versão anterior desta
    correção presumiu isso e o arquiteto-senior corrigiu essa premissa): usar
    `criar_lancamento` fora do caminho que o produto realmente percorre
    (`estornar_lancamento`) é uso indevido interno, e `IntegrityError`
    propagando é a resposta correta — visível como 500, alertável, e não
    atribuída ao cliente como se fosse erro dele. O caminho real do produto
    (via `estornar_lancamento`) é coberto por
    `test_segundo_estorno_retorna_400_e_existe_um_unico_estorno` e por
    `test_estornar_lancamento_duas_vezes_via_servico_recusa_a_segunda`, que
    continuam exigindo 400 / `LancamentoInvalido`.
    """
    original = criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Original",
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("500.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("500.00")},
        ],
    )
    estornar_lancamento(original)  # já tem um estorno; um segundo violaria estorno_de_unico

    with pytest.raises(IntegrityError) as excinfo:
        criar_lancamento(
            empresa=cenario["empresa_a"],
            data=date(2024, 1, 2),
            historico="Segundo estorno manual, via chamada direta",
            itens=[
                {"conta": cenario["caixa_a"], "tipo": "credito", "valor": Decimal("500.00")},
                {"conta": cenario["capital_a"], "tipo": "debito", "valor": Decimal("500.00")},
            ],
            estorno_de=original,
            chave_idempotencia="chave-nunca-usada-antes",
        )

    # É exatamente isso que o achado A1 proibia: DoesNotExist mascarando a
    # violação real. IntegrityError é a resposta correta; DoesNotExist seria
    # o defeito (um 500 "errado" no lugar do 500 "certo").
    assert not isinstance(excinfo.value, LancamentoContabil.DoesNotExist)

    # A chave nova não deve ter sido "adotada" por engano por nenhuma linha.
    assert not LancamentoContabil.objects.filter(
        chave_idempotencia="chave-nunca-usada-antes"
    ).exists()


# --- BL-41(b): idempotência opcional na criação de lançamento --------------


def test_mesma_idempotency_key_duas_vezes_cria_um_unico_lancamento(client, cenario):
    """Decisão de contrato do arquiteto: 201 só quando cria; 200 quando reaproveita.

    `201 Created` afirma um fato ("isto foi criado agora"); numa repetição
    nada foi criado, então afirmar 201 seria impreciso. Devolver 200 na
    repetição também torna a duplicidade de requisição observável no log e na
    resposta, em vez de escondê-la atrás de um 201 idêntico ao da primeira.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    payload = {
        "data": "2024-01-01",
        "historico": "Aporte repetido por duplo clique",
        "itens": [
            {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.00"},
            {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.00"},
        ],
    }
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])

    primeira = client.post(
        url,
        data=payload,
        content_type="application/json",
        headers={"Idempotency-Key": "chave-123"},
    )
    segunda = client.post(
        url,
        data=payload,
        content_type="application/json",
        headers={"Idempotency-Key": "chave-123"},
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert primeira.json()["id"] == segunda.json()["id"]
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa_a"]).count() == 1


def test_repeticao_idempotente_gera_acao_de_auditoria_distinta_e_nao_falsa(client, cenario):
    """A trilha de auditoria não pode afirmar 'criado' quando nada foi criado.

    AGENTS.md §11 exige registrar operação E resultado; um registro de
    'lancamento.criado' numa repetição seria um fato falso na trilha (prova
    para conciliação). A repetição precisa virar uma ação própria e
    rastreável, referenciando o lançamento original — sem suprimir o registro,
    porque a repetição em si é informação útil (duplo clique, retentativa).
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    payload = {
        "data": "2024-01-01",
        "historico": "Aporte repetido",
        "itens": [
            {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.00"},
            {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.00"},
        ],
    }
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    headers = {"Idempotency-Key": "chave-auditoria-1"}

    client.post(url, data=payload, content_type="application/json", headers=headers)
    resposta_repetida = client.post(
        url, data=payload, content_type="application/json", headers=headers
    )
    lancamento_id = str(resposta_repetida.json()["id"])

    assert RegistroAuditoria.objects.filter(acao="lancamento.criado").count() == 1
    registros_repeticao = RegistroAuditoria.objects.filter(acao="lancamento.criacao_repetida")
    assert registros_repeticao.count() == 1
    assert registros_repeticao.first().objeto_id == lancamento_id


def test_mesma_chave_em_empresas_diferentes_nao_colide(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    headers = {"Idempotency-Key": "chave-compartilhada"}

    resposta_a = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Lançamento empresa A",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "50.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "50.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )
    resposta_b = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_b"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Lançamento empresa B",
            "itens": [
                {"conta": cenario["conta_b"].id, "tipo": "debito", "valor": "50.00"},
                {"conta": cenario["conta_b"].id, "tipo": "credito", "valor": "50.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )

    assert resposta_a.status_code == 201
    assert resposta_b.status_code == 201
    assert resposta_a.json()["id"] != resposta_b.json()["id"]
    assert LancamentoContabil.objects.filter(chave_idempotencia="chave-compartilhada").count() == 2


# --- A2: chave repetida com conteúdo diferente nunca pode ser sucesso -------


def test_mesma_chave_com_corpo_diferente_retorna_409_e_nao_descarta_o_original(client, cenario):
    """Achado A2 (o mais grave): reaproveitar a chave para OUTRO conteúdo é
    conflito (409), nunca um 200 devolvendo silenciosamente o lançamento
    errado. É a 'corrupção por omissão' que o plano DL-007 chama de pior que
    a duplicidade — o cliente acharia que gravou 999999,00 e na verdade
    continua existindo só o lançamento de 100,00 original.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    headers = {"Idempotency-Key": "chave-conteudo-1"}

    primeira = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Original",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )
    segunda = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Conteúdo diferente",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "999999.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "999999.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 409
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa_a"]).count() == 1
    original_id = primeira.json()["id"]
    original_no_banco = LancamentoContabil.objects.get(pk=original_id)
    assert original_no_banco.historico == "Original"
    assert original_no_banco.itens.get(conta=cenario["caixa_a"]).valor == Decimal("100.00")


def test_mesma_chave_com_corpo_desbalanceado_na_repeticao_retorna_400(client, cenario):
    """A validação contábil roda ANTES do atalho de idempotência (achado A2).

    Reprodução exata do auditor: primeira chamada com corpo balanceado (201);
    repetição com a MESMA chave mas débito 100 / crédito 70 (desbalanceado)
    tinha, antes da correção, um atalho que devolvia 200 sem nunca checar a
    igualdade de partidas — porque a busca pela chave existente rodava antes
    de qualquer validação. Isso desligava a invariante contábil sempre que o
    cliente reaproveitasse uma chave.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    headers = {"Idempotency-Key": "chave-desbalanceado-1"}

    primeira = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Balanceado",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )
    segunda = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Desbalanceado",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "70.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 400
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa_a"]).count() == 1


def test_impressao_digital_diferente_via_servico_gera_conflito(cenario):
    """Mesmo teste do conflito de conteúdo, chamando o serviço diretamente."""
    kwargs_originais = dict(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Original via serviço",
        chave_idempotencia="chave-servico-conflito",
    )
    criar_lancamento(
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("10.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("10.00")},
        ],
        **kwargs_originais,
    )

    with pytest.raises(ChaveIdempotenciaConflitante):
        criar_lancamento(
            itens=[
                {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("20.00")},
                {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("20.00")},
            ],
            **kwargs_originais,
        )

    assert (
        LancamentoContabil.objects.filter(chave_idempotencia="chave-servico-conflito").count() == 1
    )


def test_impressao_digital_com_tipo_trocado_gera_conflito(cenario):
    """Confirma que trocar só o `tipo` de um item (mesmo valor, mesma conta)
    continua sendo detectado como conteúdo diferente — débito e crédito
    trocados não são a mesma coisa, mesmo que a soma dê no mesmo total.
    """
    kwargs = dict(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Mesmo histórico",
        chave_idempotencia="chave-tipo-trocado",
    )
    criar_lancamento(
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("30.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("30.00")},
        ],
        **kwargs,
    )

    with pytest.raises(ChaveIdempotenciaConflitante):
        criar_lancamento(
            itens=[
                {"conta": cenario["caixa_a"], "tipo": "credito", "valor": Decimal("30.00")},
                {"conta": cenario["capital_a"], "tipo": "debito", "valor": Decimal("30.00")},
            ],
            **kwargs,
        )


def test_impressao_digital_com_data_diferente_gera_conflito(cenario):
    """Confirma que trocar só a `data` do lançamento (mesmo histórico, mesmos
    itens) continua sendo detectado como conteúdo diferente.
    """
    itens = [
        {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("40.00")},
        {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("40.00")},
    ]
    criar_lancamento(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Mesmo histórico",
        itens=itens,
        chave_idempotencia="chave-data-diferente",
    )

    with pytest.raises(ChaveIdempotenciaConflitante):
        criar_lancamento(
            empresa=cenario["empresa_a"],
            data=date(2024, 1, 2),
            historico="Mesmo histórico",
            itens=itens,
            chave_idempotencia="chave-data-diferente",
        )


def test_impressao_digital_nao_colide_por_ambiguidade_do_separador(cenario):
    """Achado N1: a codificação da impressão digital precisa ser INJETIVA.

    Reprodução exata do auditor: uma versão anterior concatenava as partes
    com "|" sem escape, e estes dois conteúdos DIFERENTES produziam a MESMA
    impressão (mesmo SHA-256), porque o "|" dentro do `historico` (texto
    livre do cliente) se confundia com o separador entre campos:

    - historico="Honorario" com itens [3:debito:100.00, 4:credito:100.00,
      5:credito:0.00];
    - historico="Honorario|3:debito:100.00" com itens [4:credito:100.00,
      5:credito:0.00].

    Ambos batem débito = crédito = 100,00 e são alcançáveis pela API. Se a
    impressão colidisse, a segunda chamada devolveria em silêncio o
    lançamento da primeira, reabrindo exatamente o achado A2 (o mais grave
    desta etapa) por uma porta lateral. A correção trocou a concatenação por
    `json.dumps(..., sort_keys=True)`, que escapa qualquer caractere especial
    dentro das strings — a fronteira entre campos não pode mais ser forjada
    pelo conteúdo de um campo.
    """
    caixa = cenario["caixa_a"]
    capital = cenario["capital_a"]
    # Duas contas adicionais só para ocupar os "códigos" 3, 4 e 5 do exemplo
    # do auditor de forma equivalente — o que importa é reproduzir a mesma
    # AMBIGUIDADE de concatenação, não os ids exatos que ele usou.
    conta_extra = Conta.objects.create(
        empresa=cenario["empresa_a"],
        codigo="9.9",
        nome="Conta extra",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    impressao_1 = _impressao_digital(
        empresa_id=cenario["empresa_a"].id,
        data=date(2024, 1, 1),
        historico="Honorario",
        itens=[
            {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
            {"conta": conta_extra, "tipo": "credito", "valor": Decimal("0.01")},
        ],
    )
    impressao_2 = _impressao_digital(
        empresa_id=cenario["empresa_a"].id,
        data=date(2024, 1, 1),
        historico="Honorario|" + f"{caixa.pk}:debito:100.00",
        itens=[
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
            {"conta": conta_extra, "tipo": "credito", "valor": Decimal("0.01")},
        ],
    )

    assert impressao_1 != impressao_2


# --- N2: comportamentos da impressão digital, sem mutante sobrevivente -----


def test_itens_em_ordem_invertida_nao_geram_falso_conflito(client, cenario):
    """N2 / mata M13: a ordem em que o cliente envia os itens não pode
    importar — só o CONTEÚDO importa. Sem ordenar os itens antes de somar a
    impressão, reenviar a mesma requisição com os itens em outra ordem geraria
    um falso conflito (409 recusando um lançamento legítimo).
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    headers = {"Idempotency-Key": "chave-ordem-invertida"}

    primeira = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Ordem original",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "60.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "60.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )
    segunda = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Ordem original",
            "itens": [
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "60.00"},
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "60.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert primeira.json()["id"] == segunda.json()["id"]
    assert (
        LancamentoContabil.objects.filter(chave_idempotencia="chave-ordem-invertida").count() == 1
    )


def test_valores_com_escalas_diferentes_nao_geram_falso_conflito(client, cenario):
    """N2 / mata M14: "100", "100.0" e "100.000" representam o MESMO valor
    monetário. Sem normalizar a escala antes de calcular a impressão, o
    cliente que reenviasse a mesma requisição com o valor escrito de forma
    ligeiramente diferente (comum em serialização JSON de diferentes
    clientes) receberia um falso conflito.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    headers = {"Idempotency-Key": "chave-escalas-diferentes"}

    primeira = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Escala 1",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.0"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )
    segunda = client.post(
        url,
        data={
            "data": "2024-01-01",
            "historico": "Escala 1",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "100.000"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "100.00"},
            ],
        },
        content_type="application/json",
        headers=headers,
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert primeira.json()["id"] == segunda.json()["id"]
    assert (
        LancamentoContabil.objects.filter(chave_idempotencia="chave-escalas-diferentes").count()
        == 1
    )


def test_mesma_chave_e_conteudo_em_empresas_diferentes_nao_gera_conflito(cenario):
    """N2: duas empresas usando, por coincidência, a MESMA chave de
    idempotência e o MESMO conteúdo lógico não podem colidir nem gerar
    conflito — são lançamentos de escriturações completamente diferentes.

    Este teste cobre o COMPORTAMENTO observável pela API. Ele **não** prova
    que `empresa_id` entra na impressão digital, e a docstring anterior
    afirmava isso indevidamente (achado N4 da verificação dirigida): a
    consulta de idempotência já é filtrada por `empresa`, e o índice único é
    parcial por empresa, então remover `empresa_id` do hash é inobservável
    por teste de comportamento. Aquela afirmação foi corrigida em vez de
    mantida — comentário que promete cobertura inexistente gera confiança
    indevida (AGENTS.md §9 e a regra de honestidade em relatórios).

    A prova de que `empresa_id` participa do hash está em
    `test_impressao_digital_considera_empresa_id`, que compara os hashes
    diretamente.
    """
    kwargs_comuns = dict(
        data=date(2024, 1, 1),
        historico="Mesmo conteúdo lógico",
        chave_idempotencia="chave-cross-empresa",
    )

    lancamento_a = criar_lancamento(
        empresa=cenario["empresa_a"],
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("15.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("15.00")},
        ],
        **kwargs_comuns,
    )
    lancamento_b = criar_lancamento(
        empresa=cenario["empresa_b"],
        itens=[
            {"conta": cenario["conta_b"], "tipo": "debito", "valor": Decimal("15.00")},
            {"conta": cenario["conta_b"], "tipo": "credito", "valor": Decimal("15.00")},
        ],
        **kwargs_comuns,
    )

    assert lancamento_a.pk != lancamento_b.pk
    assert lancamento_a.criado_agora is True
    assert lancamento_b.criado_agora is True
    assert LancamentoContabil.objects.filter(chave_idempotencia="chave-cross-empresa").count() == 2


def test_impressao_digital_considera_empresa_id(cenario):
    """Prova direta de que `empresa_id` participa da impressão digital (N4).

    Precisa ser um teste DIRETO da função: por comportamento via API isto é
    inobservável, porque a consulta de idempotência já filtra por empresa e o
    índice único é parcial por empresa. O `empresa_id` no hash é defesa em
    profundidade — se algum dia a consulta deixar de ser escopada (ou alguém
    reaproveitar esta função em outro contexto, como um cache global), é ele
    que impede que a escrituração de uma empresa seja confundida com a de
    outra. Sem esta asserção, remover `empresa_id` da estrutura não derruba
    nenhum teste da suíte, e a defesa se perde silenciosamente.
    """
    comuns = dict(
        data=date(2024, 1, 1),
        historico="Mesmo conteúdo lógico",
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("15.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("15.00")},
        ],
    )

    impressao_empresa_1 = _impressao_digital(empresa_id=1, **comuns)
    impressao_empresa_2 = _impressao_digital(empresa_id=2, **comuns)

    assert impressao_empresa_1 != impressao_empresa_2, (
        "A impressão digital deve mudar com a empresa: sem isso, o conteúdo de "
        "uma empresa poderia ser confundido com o de outra caso a consulta "
        "deixe de ser escopada por empresa."
    )
    # E, mantendo a empresa, a impressão é estável e reprodutível.
    assert impressao_empresa_1 == _impressao_digital(empresa_id=1, **comuns)


# --- A3: cabeçalho longo demais nunca pode virar 500 ------------------------


def test_idempotency_key_no_limite_de_255_e_aceita(client, cenario):
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    chave = "k" * 255
    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "No limite",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "5.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "5.00"},
            ],
        },
        content_type="application/json",
        headers={"Idempotency-Key": chave},
    )

    assert response.status_code == 201
    assert LancamentoContabil.objects.filter(chave_idempotencia=chave).exists()


def test_idempotency_key_com_256_caracteres_retorna_400_nao_500(client, cenario):
    """Achado A3: entrada do cliente nunca pode virar 500 (`DataError` do
    PostgreSQL por exceder `max_length=255`) — tem que ser um 400 recusado na
    fronteira da API, antes de qualquer tentativa de gravação.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    chave = "k" * 256
    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id]),
        data={
            "data": "2024-01-01",
            "historico": "Acima do limite",
            "itens": [
                {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "5.00"},
                {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "5.00"},
            ],
        },
        content_type="application/json",
        headers={"Idempotency-Key": chave},
    )

    assert response.status_code == 400
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa_a"]).exists()


# --- A4: chave precisa ser normalizada --------------------------------------


def test_idempotency_key_somente_espacos_e_tratada_como_ausente(client, cenario):
    """Achado A4: `"  "` e `"   "` não podem contar como duas chaves
    DISTINTAS — depois de `strip()`, uma chave que só tem espaço em branco
    equivale a não ter enviado o cabeçalho, e cada POST cria um lançamento
    normalmente (nenhuma proteção de idempotência é esperada nesse caso).
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    payload = {
        "data": "2024-01-01",
        "historico": "Chave em branco",
        "itens": [
            {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "1.00"},
            {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "1.00"},
        ],
    }

    primeira = client.post(
        url, data=payload, content_type="application/json", headers={"Idempotency-Key": "  "}
    )
    segunda = client.post(
        url, data=payload, content_type="application/json", headers={"Idempotency-Key": "   "}
    )

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json()["id"] != segunda.json()["id"]
    assert (
        LancamentoContabil.objects.filter(
            empresa=cenario["empresa_a"], chave_idempotencia__isnull=False
        ).count()
        == 0
    )


# --- A5: corrida real (duas threads), não só afirmada -----------------------


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_estorno_produz_um_unico_estorno():
    """Duas threads, duas conexões de banco reais, tentam estornar o MESMO
    lançamento ao mesmo tempo (achado A5 da auditoria — os critérios 6 e 8
    do plano DL-007 estavam afirmados, não provados, porque os testes
    anteriores não usavam concorrência real). `django_db(transaction=True)`
    é necessário para que as duas threads, cada uma com sua própria conexão,
    vejam de fato commits uma da outra — o modo padrão de teste do Django
    envolve tudo numa única transação que não seria visível entre conexões.
    """
    escritorio = Escritorio.objects.create(nome="Escritório Corrida", cnpj="55566677000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida Ltda", cnpj="88899911000100"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    original = criar_lancamento(
        empresa=empresa,
        data=date(2024, 1, 1),
        historico="Original",
        itens=[
            {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
        ],
    )

    resultados = []
    barreira = threading.Barrier(2)

    def tentar_estornar():
        barreira.wait()
        try:
            estornar_lancamento(original)
            resultados.append("ok")
        except LancamentoInvalido:
            resultados.append("recusado")
        finally:
            connection.close()  # cada thread precisa fechar a própria conexão

    threads = [threading.Thread(target=tentar_estornar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(resultados) == ["ok", "recusado"]
    assert LancamentoContabil.objects.filter(estorno_de=original).count() == 1


@pytest.mark.django_db(transaction=True)
def test_corrida_real_de_idempotencia_produz_um_unico_lancamento():
    """Duas threads chamam `criar_lancamento` com a MESMA Idempotency-Key e o
    MESMO conteúdo, ao mesmo tempo. Prova que a constraint de banco
    `chave_idempotencia_unica_por_empresa` fecha a corrida quando a checagem
    prévia (SELECT antes do INSERT) não é suficiente por si só — as duas
    threads podem passar pelo SELECT antes de qualquer COMMIT da outra.
    """
    escritorio = Escritorio.objects.create(nome="Escritório Corrida 2", cnpj="55566677000255")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Corrida 2 Ltda", cnpj="88899911000200"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    resultados = []
    barreira = threading.Barrier(2)

    def tentar_criar():
        barreira.wait()
        try:
            lancamento = criar_lancamento(
                empresa=empresa,
                data=date(2024, 1, 1),
                historico="Corrida de idempotência",
                itens=[
                    {"conta": caixa, "tipo": "debito", "valor": Decimal("77.00")},
                    {"conta": capital, "tipo": "credito", "valor": Decimal("77.00")},
                ],
                chave_idempotencia="chave-corrida-real-1",
            )
            resultados.append(lancamento.pk)
        finally:
            connection.close()

    threads = [threading.Thread(target=tentar_criar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(resultados) == 2
    assert resultados[0] == resultados[1]
    assert LancamentoContabil.objects.filter(chave_idempotencia="chave-corrida-real-1").count() == 1


# --- A8: a chave crua do cliente não pode ir para a trilha de auditoria ----


def test_auditoria_de_repeticao_nao_grava_chave_crua(client, cenario):
    """Achado A8: `detalhes` de auditoria só pode ter dados não sensíveis
    (AGENTS.md §11). A chave é string arbitrária do cliente — gravamos um
    hash curto, nunca o valor original, ainda assim permitindo correlacionar
    repetições da MESMA chave entre registros de auditoria.
    """
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])
    payload = {
        "data": "2024-01-01",
        "historico": "Repetição auditada",
        "itens": [
            {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "1.00"},
            {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "1.00"},
        ],
    }
    chave_crua = "chave-secreta-do-cliente-nao-deve-aparecer"
    headers = {"Idempotency-Key": chave_crua}

    client.post(url, data=payload, content_type="application/json", headers=headers)
    client.post(url, data=payload, content_type="application/json", headers=headers)

    registro = RegistroAuditoria.objects.get(acao="lancamento.criacao_repetida")
    assert chave_crua not in str(registro.detalhes)
    assert "chave_idempotencia_hash" in registro.detalhes


def test_post_sem_idempotency_key_continua_criando_normalmente(client, cenario):
    """Sem o cabeçalho, comportamento atual preservado: cada POST cria um lançamento."""
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio_a"], "gestor")
    client.login(username="gestor", password="senha-forte-123")
    payload = {
        "data": "2024-01-01",
        "historico": "Aporte sem chave",
        "itens": [
            {"conta": cenario["caixa_a"].id, "tipo": "debito", "valor": "10.00"},
            {"conta": cenario["capital_a"].id, "tipo": "credito", "valor": "10.00"},
        ],
    }
    url = reverse("contabilidade:lancamentos", args=[cenario["empresa_a"].id])

    primeira = client.post(url, data=payload, content_type="application/json")
    segunda = client.post(url, data=payload, content_type="application/json")

    assert primeira.status_code == 201
    assert segunda.status_code == 201
    assert primeira.json()["id"] != segunda.json()["id"]
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa_a"]).count() == 2


def test_criar_lancamento_com_chave_idempotencia_via_servico_nao_duplica(cenario):
    """Idempotência também é garantida chamando o serviço diretamente (não só a view)."""
    kwargs = dict(
        empresa=cenario["empresa_a"],
        data=date(2024, 1, 1),
        historico="Aporte via serviço",
        itens=[
            {"conta": cenario["caixa_a"], "tipo": "debito", "valor": Decimal("200.00")},
            {"conta": cenario["capital_a"], "tipo": "credito", "valor": Decimal("200.00")},
        ],
        chave_idempotencia="chave-servico-1",
    )

    primeiro = criar_lancamento(**kwargs)
    segundo = criar_lancamento(**kwargs)

    assert primeiro.pk == segundo.pk
    assert LancamentoContabil.objects.filter(chave_idempotencia="chave-servico-1").count() == 1
    # `criado_agora` é o que permite à view (e a qualquer chamador) saber se
    # deve registrar "criado" ou "repetição" na auditoria, e devolver 201 ou
    # 200, sem precisar reconsultar o banco para adivinhar.
    assert primeiro.criado_agora is True
    assert segundo.criado_agora is False
