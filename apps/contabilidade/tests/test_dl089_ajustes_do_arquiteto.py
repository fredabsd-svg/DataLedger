"""DL-089, ajustes do arquiteto depois da reconferência (R1, R2 e R3; §3.1 do AGENTS.md).

A reconferência foi a última rodada permitida. Cada ajuste tem aqui o teste que o prende.
Dados sintéticos.

- R1: origem automática sem documento de origem é recusada no serviço e no banco.
- R2: o seletor do Diário só enxerga a origem da PRÓPRIA empresa.
- R3: a trilha e a mensagem do 403 dizem qual regra tornou o lançamento automático.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import OrigemLancamento, TipoDocumentoOrigem, TipoPartida
from apps.contabilidade.services import (
    EstornoDeOrigemAutomaticaNaoPermitido,
    LancamentoInvalido,
    criar_lancamento,
    criterio_de_estorno_automatico,
    estornar_lancamento,
    existe_lancamento_de_origem,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
TABELA = "contabilidade_lancamentocontabil"
CHAVE_NFE = "35261099999999999999550010000000011000000011"
SHA_SINTETICO = "a" * 64

so_postgresql = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="As CHECKs de origem existem só em PostgreSQL (DL-089).",
)


def _empresa(nome, cnpj_escritorio):
    escritorio = criar_escritorio(f"Escritório {nome}", cnpj_escritorio)
    empresa = criar_empresa(
        escritorio=escritorio, razao_social=f"Empresa {nome} Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    return {"escritorio": escritorio, "empresa": empresa, "contas": criar_plano(empresa)}


@pytest.fixture
def cenario():
    return _empresa("DL-089 ajustes A", "89897000000189")


def _itens(contas):
    return [
        {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
        {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
    ]


def _lancar(cenario, **kwargs):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Lançamento (sintético)",
        itens=_itens(cenario["contas"]),
        **kwargs,
    )


# ---------------------------------------------------------------------------
# R1: origem automática exige documento de origem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("origem", [OrigemLancamento.IMPORTACAO, OrigemLancamento.ESCRITA_FISCAL])
def test_r1_servico_recusa_origem_automatica_sem_documento(cenario, origem):
    with pytest.raises(LancamentoInvalido, match="exige o documento de origem"):
        _lancar(cenario, origem=origem)


def test_r1_manual_sem_documento_continua_aceito(cenario):
    lancamento = _lancar(cenario)

    assert lancamento.origem == OrigemLancamento.MANUAL
    assert lancamento.documento_origem_tipo is None


@so_postgresql
@pytest.mark.parametrize("origem", [OrigemLancamento.IMPORTACAO, OrigemLancamento.ESCRITA_FISCAL])
def test_r1_banco_recusa_origem_automatica_sem_documento(cenario, origem):
    with pytest.raises(IntegrityError) as erro:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO {TABELA} (empresa_id, data, historico, origem, criado_em) "
                "VALUES (%s, %s, %s, %s, NOW())",
                [cenario["empresa"].pk, date(2026, 3, 10), "SQL (sintético)", origem],
            )

    nome = erro.value.__cause__.diag.constraint_name
    assert nome == "ck_lancamentocontabil_origem_pareada_ao_documento"


# ---------------------------------------------------------------------------
# R2: o seletor do Diário não enxerga a origem de outra empresa
# ---------------------------------------------------------------------------


def test_r2_seletor_nao_ve_escrita_fiscal_de_outra_empresa(client, cenario):
    outra = _empresa("DL-089 ajustes B", "89896000000189")
    _lancar(
        outra,
        origem=OrigemLancamento.ESCRITA_FISCAL,
        documento_origem=(TipoDocumentoOrigem.ESCRITURACAO_NFE, CHAVE_NFE),
    )
    _lancar(cenario)
    usuario = get_user_model().objects.create_user(
        username="analista-ajustes-dl089",
        email="analista-ajustes-dl089@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=cenario["escritorio"], papel=Papel.ANALISTA
    )
    assert client.login(username="analista-ajustes-dl089", password=SENHA)

    assert (
        existe_lancamento_de_origem(
            empresa=cenario["empresa"], origem=OrigemLancamento.ESCRITA_FISCAL
        )
        is False
    )
    assert (
        existe_lancamento_de_origem(
            empresa=outra["empresa"], origem=OrigemLancamento.ESCRITA_FISCAL
        )
        is True
    )
    conteudo = client.get(
        reverse("contabilidade_web:diario", args=[cenario["empresa"].id]),
        {"inicio": "2026-03-01", "fim": "2026-03-31"},
    ).content.decode("utf-8")
    seletor = conteudo.split('<select id="id_origem"', 1)[1].split("</select>", 1)[0]
    assert 'value="escrita_fiscal"' not in seletor


# ---------------------------------------------------------------------------
# R3: o critério que tornou o lançamento automático
# ---------------------------------------------------------------------------


def test_r3_criterio_de_cada_regra(cenario):
    manual = _lancar(cenario)
    por_origem = _lancar(
        cenario,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, 1),
    )
    por_chave_de_importacao = _lancar(
        cenario,
        chave_idempotencia=f"importacao:{SHA_SINTETICO}:1",
        permitir_prefixo_da_importacao=True,
    )
    por_chave_de_zeramento = _lancar(
        cenario, chave_idempotencia="zeramento:2026-03", permitir_prefixo_reservado=True
    )

    assert criterio_de_estorno_automatico(manual) is None
    assert criterio_de_estorno_automatico(por_origem) == "origem"
    assert criterio_de_estorno_automatico(por_chave_de_importacao) == "chave_importacao"
    assert criterio_de_estorno_automatico(por_chave_de_zeramento) == "chave_zeramento"


def test_r3_mensagem_do_zeramento_nao_fala_em_escrita_fiscal(cenario):
    zeramento = _lancar(
        cenario, chave_idempotencia="zeramento:2026-03", permitir_prefixo_reservado=True
    )

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido) as erro:
        estornar_lancamento(zeramento, papel=Papel.ANALISTA)

    assert "zeramento do resultado" in str(erro.value)
    assert "escrita fiscal" not in str(erro.value)
    assert erro.value.criterio == "chave_zeramento"


def test_r3_trilha_da_negativa_grava_o_criterio(client, cenario):
    legado = _lancar(
        cenario,
        chave_idempotencia=f"importacao:{SHA_SINTETICO}:2",
        permitir_prefixo_da_importacao=True,
    )
    usuario = get_user_model().objects.create_user(
        username="analista-trilha-dl089",
        email="analista-trilha-dl089@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=cenario["escritorio"], papel=Papel.ANALISTA
    )
    assert client.login(username="analista-trilha-dl089", password=SENHA)

    resposta = client.post(
        reverse("contabilidade:estornar", args=[cenario["empresa"].id, legado.id])
    )

    assert resposta.status_code == 403
    negativa = RegistroAuditoria.objects.get(acao="lancamento.estorno_negado")
    assert negativa.detalhes == {
        "papel": Papel.ANALISTA,
        "origem": OrigemLancamento.MANUAL,
        "motivo": "origem_automatica_sem_permissao",
        "criterio": "chave_importacao",
    }
