"""DL-046 fatia 3 — o FIO da restrição de código de ocupação até as views.

O registro da tradução
`empresa_codigo_ocupacao_so_para_cpf_com_formato_valido` já existia em
`apps/core/restricoes.py` (a varredura de
`apps/core/tests/test_dl019_varredura_de_restricoes.py` exige o registro),
mas o **fio** até `EmpresaListCreateView.perform_create` e
`EmpresaDetailView.update` faltava — o próprio comentário do registro
marcava o GAP: uma corrida residual que violasse esta constraint
específica vazaria `IntegrityError` cru (500), não o texto de negócio.

O molde é o de `test_dl039_bl533_gatilho_sem_500.py` (casos 2 e 3): a
checagem em Python que normalmente recusaria ANTES do INSERT/UPDATE é
neutralizada — a "janela de corrida" — e só a defesa de BANCO sobra.

## Por que há um `monkeypatch` num suprimento de nome de constraint

`restricao_como_400` traduz lendo `exc.__cause__.diag.constraint_name`
(`apps/core/restricoes.py:_nome_da_constraint_violada`) — diagnóstico que
**só o psycopg (PostgreSQL) anexa**. O driver do SQLite não tem `.diag`,
então, neste backend, qualquer restrição de `Meta.constraints` vaza
`IntegrityError` crua **independentemente de o fio estar ligado**. É
limitação de ambiente, não do produto: a CI roda PostgreSQL 16, e é a
evidência dela que vale para merge.

Isso já é assim antes desta etapa —
`apps/empresas/tests/test_dl019_canonizacao_como_400.py` falha nos cinco
testes que dependem do diagnóstico real quando roda em SQLite (medido em
2026-09-27, Python 3.14.7, sem PostgreSQL nesta máquina).

Por isso os testes abaixo se dividem em três camadas, cada uma provando
uma coisa distinta e declarando a que não prova:

1. **Fio estrutural** — o nome está nos dois `mensagens_de(...)` e no mapa
   de campo. Roda em qualquer banco; é o que impede a regressão de o nome
   ser removido.
2. **Cadeia comportamental** — com o nome do banco suprido (o que o psycopg
   faria), a API devolve 400 no campo certo com a mensagem do REGISTRO.
   Prova view → `restricao_como_400` → `RestricaoViolada` → 400.
3. **Nome real da constraint** — `bulk_create` com a violação de verdade,
   comparando o nome que o banco devolve com o registrado. Só faz sentido
   onde há `diag` (PostgreSQL); em SQLite é pulado com o motivo escrito.
"""

from __future__ import annotations

import inspect
import json

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse

from apps.empresas import serializers as empresas_serializers
from apps.empresas import views as empresas_views
from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.views import _CAMPO_DA_RESTRICAO_DE_EMPRESA, _campo_da_restricao_de_empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

NOME_DA_CONSTRAINT = "empresa_codigo_ocupacao_so_para_cpf_com_formato_valido"

# Valor DENTRO da tabela oficial do Carnê-Leão Web e com formato válido —
# o que estes testes não medem é o FORMATO (isso já é provado em
# `test_dl046_fatia3_arquivos_carne_leao.py`); é a COERÊNCIA com o tipo de
# inscrição, e só ela.
OCUPACAO_VALIDA = "225"

# Trecho que SÓ a mensagem registrada em `MENSAGENS_DE_RESTRICAO` tem —
# ver a seção 2 do docstring: é o oráculo que separa "recusou o banco" de
# "recusou o serializer".
ORACULO_DO_BANCO = "tabela oficial"


def _tem_diagnostico_de_constraint():
    """`True` quando o driver do banco anexa `diag.constraint_name` — hoje,
    só o psycopg. Quem roda em SQLite pula o teste que exige o nome real e
    fica sabendo por quê."""
    return connection.vendor == "postgresql"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório DL-046 F3", cnpj="91100000000080")


@pytest.fixture
def gestor(escritorio):
    usuario = get_user_model().objects.create_user(
        username="gestor-dl046f3", email="gestor-dl046f3@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def autenticado(client, gestor):
    assert client.login(username="gestor-dl046f3", password="senha-forte-123")
    return client


@pytest.fixture
def empresa_cnpj(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa CNPJ DL-046 F3 Ltda",
        tipo_inscricao=TipoInscricao.CNPJ,
        cnpj="11122233000183",
    )


@pytest.fixture
def sem_checagem_de_ocupacao_no_serializer(monkeypatch):
    """Neutraliza SÓ a checagem cruzada tipo × código de ocupação, deixando
    passar tudo o mais.

    Ao contrário do `recusar_transicao_para_cpf_com_estabelecimento` (que é
    função nomeada e por isso é pego por `monkeypatch.setattr` direto), esta
    checagem é um `if` inline dentro de `EmpresaSerializer.validate`. A
    solução é envolver o `validate` original e engolir APENAS a recusa cujo
    dicionário de erro tem `codigo_ocupacao` como única chave — qualquer
    outra recusa (consistência de inscrição, CAEPF, CNPJ de estabelecimento
    alheio) continua valendo, e um payload que dispare mais de uma coisa
    continua sendo recusado.

    Com a checagem fora do caminho, o INSERT/UPDATE alcança o banco, a
    `CheckConstraint` dispara e é `restricao_como_400` que precisa traduzir
    — exatamente o fio sob teste.
    """
    validate_original = empresas_serializers.EmpresaSerializer.validate

    def validate_sem_o_bloqueio_de_ocupacao(self, attrs):
        from rest_framework import serializers as drf_serializers

        try:
            return validate_original(self, attrs)
        except drf_serializers.ValidationError as exc:
            detalhe = getattr(exc, "detail", {})
            if isinstance(detalhe, dict) and set(detalhe) == {"codigo_ocupacao"}:
                return attrs
            raise

    monkeypatch.setattr(
        empresas_serializers.EmpresaSerializer,
        "validate",
        validate_sem_o_bloqueio_de_ocupacao,
    )


@pytest.fixture
def com_nome_de_constraint_do_banco(monkeypatch):
    """Supre o `diag.constraint_name` que só o psycopg anexa.

    O alvo é `apps.core.restricoes._nome_da_constraint_violada`, o ÚNICO
    ponto que lê o diagnóstico — forçar o nome aqui não mascara nada do que
    estes testes querem medir (a presença do fio e a tradução para 400),
    porque o nome suprido é exatamente o que o banco devolveria. O que fica
    sem prova neste backend é o NOME REAL da constraint batendo com o
    registrado — e é para isso que existe o teste da seção 3, que só roda
    onde há diagnóstico.
    """
    import apps.core.restricoes as modulo_restricoes

    monkeypatch.setattr(
        modulo_restricoes,
        "_nome_da_constraint_violada",
        lambda exc: NOME_DA_CONSTRAINT,
    )


# ---------------------------------------------------------------------------
# 1. Fio estrutural — o nome está ligado nas DUAS superfícies de gravação
# ---------------------------------------------------------------------------


def test_a_restricao_de_ocupacao_entra_no_mensagens_de_da_criacao():
    """`perform_create` é um dos dois caminhos de gravação do campo.

    Este teste não depende de banco nenhum: é o que impede a regressão de o
    nome ser removido do `with restricao_como_400(mensagens_de(...))` — o
    tipo de corte que deixaria o 500 voltar sem quebrar nenhum teste de
    comportamento até a próxima corrida acontecer em produção.
    """
    origem = inspect.getsource(empresas_views.EmpresaListCreateView.perform_create)
    assert NOME_DA_CONSTRAINT in origem, origem


def test_a_restricao_de_ocupacao_entra_no_mensagens_de_da_atualizacao():
    """A atualização é o OUTRO caminho de gravação do mesmo campo — fechar
    só a criação repetiria, em duas rotas vizinhas do mesmo arquivo, o
    padrão que a DL-011 já nomeou."""
    origem = inspect.getsource(empresas_views.EmpresaDetailView.perform_update)
    assert NOME_DA_CONSTRAINT in origem, origem


def test_o_campo_reportado_e_codigo_ocupacao_nao_cnpj():
    """Mesmo achado do CAEPF (rodada 1 da DL-046): sem a entrada em
    `_CAMPO_DA_RESTRICAO_DE_EMPRESA`, a corrida desta constraint caía no
    `.get(..., "cnpj")` (o padrão da função) e reportava o erro no campo
    errado — o cliente via o erro em cima de um campo que estava certo."""
    assert NOME_DA_CONSTRAINT in _CAMPO_DA_RESTRICAO_DE_EMPRESA
    assert _campo_da_restricao_de_empresa(NOME_DA_CONSTRAINT) == "codigo_ocupacao"


# ---------------------------------------------------------------------------
# 2. Cadeia comportamental — a corrida alcança o banco e a API devolve 400
# ---------------------------------------------------------------------------


def test_post_de_empresa_com_ocupacao_na_janela_de_corrida_da_400_nao_500(
    sem_checagem_de_ocupacao_no_serializer,
    com_nome_de_constraint_do_banco,
    autenticado,
    escritorio,
):
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Empresa Ocupacao Corrida Ltda",
                "tipo_inscricao": "CNPJ",
                "cnpj": "11122233000183",
                "codigo_ocupacao": OCUPACAO_VALIDA,
                "modo_escrituracao": "contabilidade",
            }
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    corpo = resposta.json()
    assert "codigo_ocupacao" in corpo, corpo
    # O oráculo que separa banco de Python: só a mensagem registrada fala em
    # "tabela oficial". Se o texto vier da checagem do serializer, o fio não
    # foi exercitado e este teste está provando a coisa errada.
    assert ORACULO_DO_BANCO in json.dumps(corpo, ensure_ascii=False), corpo
    assert not Empresa.objects.filter(razao_social="Empresa Ocupacao Corrida Ltda").exists()


def test_patch_de_empresa_com_ocupacao_na_janela_de_corrida_da_400_nao_500(
    sem_checagem_de_ocupacao_no_serializer,
    com_nome_de_constraint_do_banco,
    autenticado,
    empresa_cnpj,
):
    resposta = autenticado.patch(
        reverse("empresas:api-detalhe", kwargs={"pk": empresa_cnpj.pk}),
        data=json.dumps({"codigo_ocupacao": OCUPACAO_VALIDA}),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    corpo = resposta.json()
    assert "codigo_ocupacao" in corpo, corpo
    assert ORACULO_DO_BANCO in json.dumps(corpo, ensure_ascii=False), corpo
    empresa_cnpj.refresh_from_db()
    assert empresa_cnpj.codigo_ocupacao == ""


def test_controle_o_caminho_do_banco_e_de_fato_alcancado(
    sem_checagem_de_ocupacao_no_serializer, autenticado, escritorio
):
    """Controle do instrumento: com a janela aberta, MAS sem o suprimento do
    nome da constraint, a violação chega ao banco de verdade.

    É o que garante que os dois testes acima estão medindo o fio e não um
    atalho: se algum dia eles continuarem verdes sem que o banco seja
    alcançado, este controle deixa de descrever o que acontece.

    Em SQLite o `IntegrityError` **sobe** (o test client do Django
    re-lança a exceção em vez de devolver uma página de 500, e
    `restricao_como_400` não tem `diag` para traduzir) — é a limitação de
    ambiente já documentada, não o comportamento do produto em PostgreSQL.
    """
    from django.db import IntegrityError

    if _tem_diagnostico_de_constraint():
        pytest.skip(
            "em PostgreSQL o nome vem do driver e o fio traduz mesmo sem "
            "suprimento — o controle não tem o que mostrar"
        )

    with pytest.raises(IntegrityError) as excinfo:
        autenticado.post(
            reverse("empresas:api-lista"),
            data=json.dumps(
                {
                    "razao_social": "Empresa Ocupacao Sem Nome Ltda",
                    "tipo_inscricao": "CNPJ",
                    "cnpj": "11122233000183",
                    "codigo_ocupacao": OCUPACAO_VALIDA,
                    "modo_escrituracao": "contabilidade",
                }
            ),
            content_type="application/json",
        )

    # O erro é o do BANCO, com o nome da constraint — nunca a recusa curta
    # do serializer. É a prova de que a janela está de fato aberta e de que
    # os dois testes acima exercitam o fio.
    assert NOME_DA_CONSTRAINT in str(excinfo.value), str(excinfo.value)
    assert not Empresa.objects.filter(razao_social="Empresa Ocupacao Sem Nome Ltda").exists()


def test_controle_sem_a_janela_o_serializer_recusa_antes_do_banco(autenticado, escritorio):
    """Sem o `monkeypatch`, a recusa vem do serializer (400, e não 500) e o
    texto é o DELE, não o do banco. Prova que a neutralização do fixture é
    que leva o teste ao banco — sem este controle, os dois testes acima
    poderiam estar passando pela camada errada sem ninguém notar."""
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Empresa Ocupacao Controle Ltda",
                "tipo_inscricao": "CNPJ",
                "cnpj": "11122233000183",
                "codigo_ocupacao": OCUPACAO_VALIDA,
                "modo_escrituracao": "contabilidade",
            }
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    corpo = resposta.json()
    assert "codigo_ocupacao" in corpo, corpo
    assert ORACULO_DO_BANCO not in json.dumps(corpo, ensure_ascii=False), corpo
    assert not Empresa.objects.filter(razao_social="Empresa Ocupacao Controle Ltda").exists()


def test_controle_empresa_cpf_com_ocupacao_continua_sendo_aceita(autenticado, escritorio):
    """A regra é "só para CPF" — o caso válido não pode ter sido afetado."""
    resposta = autenticado.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Fulano Ocupacao Ok",
                "tipo_inscricao": "CPF",
                "cpf": "11144477735",
                "codigo_ocupacao": OCUPACAO_VALIDA,
                "modo_escrituracao": "livro_caixa",
            }
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.get(cpf="11144477735").codigo_ocupacao == OCUPACAO_VALIDA


# ---------------------------------------------------------------------------
# 3. Nome real da constraint — só onde há diagnóstico (PostgreSQL)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not _tem_diagnostico_de_constraint(),
    reason=(
        "exige diag.constraint_name do driver (psycopg): o SQLite não o anexa, "
        "então restricao_como_400 não tem como traduzir — limitação de "
        "ambiente, não do produto; a CI roda PostgreSQL 16"
    ),
)
def test_o_nome_registrado_bate_com_o_nome_que_o_banco_devolve(escritorio):
    """`bulk_create` (que NÃO passa por `full_clean()` nem pelo serializer)
    com código de ocupação em empresa CNPJ, dentro de
    `restricao_como_400(MENSAGENS_DE_RESTRICAO)`.

    Se o nome registrado divergir do nome real da constraint, nada é
    traduzido e este teste falha com `IntegrityError` crua — que é o 500 que
    a fatia 3 existe para eliminar.
    """
    from apps.core.restricoes import MENSAGENS_DE_RESTRICAO, RestricaoViolada, restricao_como_400

    with pytest.raises(RestricaoViolada) as excinfo:
        with restricao_como_400(MENSAGENS_DE_RESTRICAO):
            Empresa.objects.bulk_create(
                [
                    Empresa(
                        escritorio=escritorio,
                        razao_social="Bulk DL-046 F3 Ltda",
                        tipo_inscricao=TipoInscricao.CNPJ,
                        cnpj="11122233000183",
                        codigo_ocupacao=OCUPACAO_VALIDA,
                    )
                ]
            )
    assert excinfo.value.nome == NOME_DA_CONSTRAINT
