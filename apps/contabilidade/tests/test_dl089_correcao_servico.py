"""DL-089, correção da rodada 1 (A6, T5): o serviço recusa o que o banco também recusa, e antes.

- Origem e tipo de documento pareados: `importacao` só com `importacao_lancamentos`;
  `escrita_fiscal` só com NF-e ou NFS-e.
- Identificador de documento sem espaço nas pontas e não vazio após aparar. O serviço recusa
  (não aparar em silêncio), e a mesma regra vale na consulta por documento.

Estes testes rodam em qualquer banco: a regra é do serviço. A CHECK correspondente é testada
em PostgreSQL em `test_dl089_correcao_banco.py`. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import (
    LancamentoContabil,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import (
    LancamentoInvalido,
    criar_lancamento,
    lancamentos_do_documento_de_origem,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)

pytestmark = pytest.mark.django_db

NFE = TipoDocumentoOrigem.ESCRITURACAO_NFE
NFSE = TipoDocumentoOrigem.ESCRITURACAO_NFSE
LOTE = TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 serviço", "89894000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Serviço Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    return {"empresa": empresa, "contas": criar_plano(empresa)}


def _criar(cenario, origem, documento):
    contas = cenario["contas"]
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Teste de pareamento (sintético)",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
        origem=origem,
        documento_origem=documento,
    )


@pytest.mark.parametrize(
    "origem, tipo",
    [
        (OrigemLancamento.IMPORTACAO, NFE),
        (OrigemLancamento.IMPORTACAO, NFSE),
        (OrigemLancamento.ESCRITA_FISCAL, LOTE),
    ],
)
def test_a6_servico_recusa_par_origem_tipo_incoerente_sem_gravar(cenario, origem, tipo):
    antes = LancamentoContabil.objects.count()

    with pytest.raises(LancamentoInvalido):
        _criar(cenario, origem, (tipo, "1"))

    assert LancamentoContabil.objects.count() == antes


@pytest.mark.parametrize(
    "origem, tipo",
    [
        (OrigemLancamento.IMPORTACAO, LOTE),
        (OrigemLancamento.ESCRITA_FISCAL, NFE),
        (OrigemLancamento.ESCRITA_FISCAL, NFSE),
    ],
)
def test_a6_servico_aceita_par_origem_tipo_coerente(cenario, origem, tipo):
    """Controle positivo: os três pares admitidos continuam gravando."""
    lancamento = _criar(cenario, origem, (tipo, "1"))

    lancamento.refresh_from_db()
    assert (lancamento.origem, lancamento.documento_origem_tipo) == (origem, tipo)


@pytest.mark.parametrize("identificador", [" 12", "12 ", " 12 ", "\t12", "12\n"])
def test_a6_servico_recusa_identificador_com_espaco_nas_pontas_sem_aparar_em_silencio(
    cenario, identificador
):
    antes = LancamentoContabil.objects.count()

    with pytest.raises(LancamentoInvalido, match="espaço no início ou no fim"):
        _criar(cenario, OrigemLancamento.IMPORTACAO, (LOTE, identificador))

    assert LancamentoContabil.objects.count() == antes


@pytest.mark.parametrize("identificador", ["", "   ", "\t"])
def test_a6_servico_recusa_identificador_vazio_ou_so_de_espaco(cenario, identificador):
    with pytest.raises(LancamentoInvalido, match="não pode ser vazio"):
        _criar(cenario, OrigemLancamento.IMPORTACAO, (LOTE, identificador))


def test_a6_identificador_sem_espaco_e_gravado_como_foi_enviado(cenario):
    lancamento = _criar(cenario, OrigemLancamento.IMPORTACAO, (LOTE, "12"))

    lancamento.refresh_from_db()
    assert lancamento.documento_origem_id == "12"


def test_a6_consulta_por_documento_recusa_grafia_com_espaco(cenario):
    """A consulta usa o mesmo normalizador: `" 12"` não encontra o documento `12` por engano
    (nem é tratado como documento sem lançamento)."""
    _criar(cenario, OrigemLancamento.IMPORTACAO, (LOTE, "12"))

    with pytest.raises(LancamentoInvalido):
        list(
            lancamentos_do_documento_de_origem(
                empresa=cenario["empresa"], tipo=LOTE, identificador=" 12"
            )
        )
