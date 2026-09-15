"""As duas `CheckConstraint` de canonização de CNPJ traduzidas para 400
(BL-204, achado R6-10 — segunda metade, que o inventário de 2026-09-15
mediu como ausente).

## O que faltava, e por que isto não é detalhe

As duas restrições estão mapeadas em `apps.core.restricoes.
MENSAGENS_DE_RESTRICAO` e aplicadas em `apps/empresas/views.py`, mas
**nenhum teste exercitava a tradução**: `test_canonizacao_constraint.py` (da
DL-011) prova que `bulk_create`/`bulk_update`/`QuerySet.update()` vazam
`IntegrityError` **cru** — o que continua verdade para o ORM direto, porque
esses caminhos não passam por `restricao_como_400` nenhum — e nada media o
outro lado: que, **onde a tradução existe**, a violação chega ao cliente como
400 de negócio.

Sem estes testes, o mapeamento era controle positivo: um nome de constraint
escrito errado no registro, ou um `with restricao_como_400(...)` removido de
`perform_create`, não mataria teste nenhum. A DL-010 (importação fiscal em
lote) é a etapa que vai usar `bulk_create` — a armadilha estava armada para
ela, e desarmar significa ter a tradução **medida**, não declarada.

## Os dois níveis, de propósito

**1. Unitário sobre o banco REAL** (`restricao_como_400` em volta de um
`bulk_create` que viola a constraint de verdade). `apps/core/tests/
test_restricoes.py` já cobre a lógica de tradução com um `IntegrityError`
sintético; o que ele **não** pode cobrir é se o nome no registro bate com o
nome que o PostgreSQL devolve no diagnóstico do driver. Aqui bate ou não
bate: o `IntegrityError` vem do banco.

**2. De requisição** (`POST` na API devolvendo 400, nunca 500). A
canonização é neutralizada com `monkeypatch` — mesmo recurso, e mesmo
motivo, de `test_criar_empresa_via_api_com_corrida_neutralizando_o_unique_
validator_da_400`: o caminho normal da API canoniza antes do INSERT, então a
constraint é inalcançável por ele. Neutralizar a canonização reproduz,
determinística, a situação de um caminho de gravação que **não** canoniza —
que é exatamente o `bulk_create` que a DL-010 vai escrever.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse

from apps.core.restricoes import MENSAGENS_DE_RESTRICAO, RestricaoViolada, restricao_como_400
from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"

# CNPJ com dígito verificador VÁLIDO (o mesmo que a suíte já usa para o caso
# alfanumérico), escrito em minúsculas: passa por `validar_cnpj` e só viola a
# canonização se nada o converter para maiúsculas antes do INSERT.
CNPJ_VALIDO_MINUSCULO = "ab123cde000155"
CNPJ_VALIDO_CANONICO = "AB123CDE000155"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório BL-204", cnpj="11111111000111")


@pytest.fixture
def empresa(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-204 Ltda", cnpj="11122233000183"
    )


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-bl157", email="gestor-bl157@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def autenticado(client, gestor):
    assert client.login(username="gestor-bl157", password=SENHA)
    return client


@pytest.fixture
def sem_canonizacao(monkeypatch):
    """Neutraliza a canonização do CNPJ nos DOIS pontos que a aplicam.

    `normalizar_cnpj` é importado por nome em `apps.empresas.fields` (usado
    pelo `CNPJSerializerField`, no laço por-campo do DRF) e em
    `apps.empresas.models` (usado por `Empresa.save`/`Estabelecimento.save`).
    Patch no módulo de origem (`apps.empresas.validators`) NÃO teria efeito
    sobre esses dois nomes já ligados — é por isso que são dois
    `monkeypatch`, e não um.

    `validar_cnpj` continua valendo: o valor enviado tem dígito verificador
    correto, e o que este fixture remove é só a CONVERSÃO para o formato
    canônico — o que sobra é exatamente o caminho de gravação que a camada 1
    da DE-008 existe para segurar.
    """
    import apps.empresas.fields as modulo_fields
    import apps.empresas.models as modulo_models

    monkeypatch.setattr(modulo_fields, "normalizar_cnpj", lambda valor: valor)
    monkeypatch.setattr(modulo_models, "normalizar_cnpj", lambda valor: valor)


# ---------------------------------------------------------------------------
# Nível 1: o nome registrado bate com o nome que o banco devolve
# ---------------------------------------------------------------------------


def test_restricao_como_400_traduz_a_violacao_real_de_empresa_cnpj_canonico(escritorio):
    """`bulk_create` com CNPJ minúsculo, dentro de `restricao_como_400`.

    O `IntegrityError` é do PostgreSQL, com o diagnóstico do driver: se
    `MENSAGENS_DE_RESTRICAO` tiver o nome da constraint escrito diferente do
    nome real, `_nome_da_constraint_violada` não encontra a chave, nada é
    traduzido e este teste falha com `IntegrityError` em vez de
    `RestricaoViolada`.
    """
    with pytest.raises(RestricaoViolada) as excinfo:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO):
            Empresa.objects.bulk_create(
                [
                    Empresa(
                        escritorio=escritorio,
                        razao_social="Empresa Em Lote Ltda",
                        cnpj=CNPJ_VALIDO_MINUSCULO,
                    )
                ]
            )

    assert excinfo.value.nome == "empresa_cnpj_canonico"
    assert str(excinfo.value) == MENSAGENS_DE_RESTRICAO["empresa_cnpj_canonico"]
    assert not Empresa.objects.filter(cnpj=CNPJ_VALIDO_MINUSCULO).exists()


def test_restricao_como_400_traduz_a_violacao_real_de_estabelecimento_cnpj_canonico(empresa):
    with pytest.raises(RestricaoViolada) as excinfo:
        with transaction.atomic(), restricao_como_400(MENSAGENS_DE_RESTRICAO):
            Estabelecimento.objects.bulk_create(
                [
                    Estabelecimento(
                        empresa=empresa,
                        tipo=TipoEstabelecimento.MATRIZ,
                        nome="Matriz em lote",
                        cnpj=CNPJ_VALIDO_MINUSCULO,
                    )
                ]
            )

    assert excinfo.value.nome == "estabelecimento_cnpj_canonico"
    assert str(excinfo.value) == MENSAGENS_DE_RESTRICAO["estabelecimento_cnpj_canonico"]
    assert not Estabelecimento.objects.filter(cnpj=CNPJ_VALIDO_MINUSCULO).exists()


# ---------------------------------------------------------------------------
# Nível 2: a API responde 400 de negócio, nunca 500
# ---------------------------------------------------------------------------


def test_post_de_empresa_sem_canonizacao_devolve_400_no_campo_cnpj(autenticado, sem_canonizacao):
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        data={"razao_social": "Empresa Sem Canonizar Ltda", "cnpj": CNPJ_VALIDO_MINUSCULO},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert mensagem == MENSAGENS_DE_RESTRICAO["empresa_cnpj_canonico"]
    # Nada gravado, em nenhuma das duas formas: o savepoint de
    # `transaction.atomic()` desfez o INSERT e a conexão seguiu utilizável
    # (a resposta 400 acima é a prova de que seguiu).
    assert not Empresa.objects.filter(
        cnpj__in=[CNPJ_VALIDO_MINUSCULO, CNPJ_VALIDO_CANONICO]
    ).exists()


def test_put_de_empresa_sem_canonizacao_devolve_400_no_campo_cnpj(
    autenticado, empresa, sem_canonizacao
):
    """A alteração é o OUTRO caminho de gravação do mesmo campo (DE-034 item
    2): `perform_update` tem o mesmo `with`, e fechar só a criação repetiria,
    em duas rotas vizinhas do mesmo arquivo, o padrão do R6-2."""
    resposta = autenticado.put(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa.pk}),
        data={"razao_social": "Empresa BL-204 Ltda", "cnpj": CNPJ_VALIDO_MINUSCULO},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert mensagem == MENSAGENS_DE_RESTRICAO["empresa_cnpj_canonico"]
    empresa.refresh_from_db()
    assert empresa.cnpj == "11122233000183"


def test_post_de_estabelecimento_sem_canonizacao_devolve_400_no_campo_cnpj(
    autenticado, empresa, sem_canonizacao
):
    """Também prova que o campo do erro sai de `exc.nome`, e não da ordem em
    que as constraints entraram no `with`: esta view trata `uma_matriz_por_
    empresa` (campo `tipo`) e `estabelecimento_cnpj_canonico` (campo `cnpj`)
    no MESMO gerenciador de contexto. Um mutante que fixasse o campo em
    `"tipo"` reportaria a violação de canonização no campo errado e este
    teste falharia."""
    resposta = autenticado.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": CNPJ_VALIDO_MINUSCULO},
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    (mensagem,) = resposta.json()["cnpj"]
    assert mensagem == MENSAGENS_DE_RESTRICAO["estabelecimento_cnpj_canonico"]
    assert not Estabelecimento.objects.exists()


def test_com_canonizacao_o_mesmo_payload_e_aceito(autenticado, empresa):
    """Controle negativo do fixture: sem neutralizar nada, o MESMO CNPJ
    minúsculo é aceito e gravado canônico. Sem este teste, um erro no
    `monkeypatch` (nome errado de módulo, por exemplo) poderia fazer os dois
    testes acima medirem outra coisa — e um deles passar por acidente.
    """
    resposta = autenticado.post(
        reverse("empresas:api-estabelecimentos", kwargs={"empresa_id": empresa.pk}),
        data={"tipo": "matriz", "nome": "Matriz", "cnpj": CNPJ_VALIDO_MINUSCULO},
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Estabelecimento.objects.get().cnpj == CNPJ_VALIDO_CANONICO
