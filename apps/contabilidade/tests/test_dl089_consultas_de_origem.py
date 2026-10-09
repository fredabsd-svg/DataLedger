"""DL-089 (BL-72) — consultas nos dois sentidos, com isolamento por empresa e escritório.

Critério 3 do plano: documento → lançamentos e lançamento → documento funcionam, e nenhuma
das duas enxerga outra empresa, mesmo quando o identificador do documento é o mesmo.

Inclui o caminho REAL da importação (DL-077): a efetivação grava `origem=importacao` com o
lote como documento, e a consulta acha os lançamentos a partir do lote. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    LancamentoContabil,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import (
    DocumentoDeOrigem,
    LancamentoInvalido,
    criar_lancamento,
    documento_de_origem_do_lancamento,
    lancamentos_do_documento_de_origem,
    listar_diario,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    criar_empresa,
    criar_escritorio,
    criar_plano,
)

pytestmark = pytest.mark.django_db

LOTE = TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS


@pytest.fixture
def cenario():
    escritorio_a = criar_escritorio("Escritório DL-089 consultas A", "89891000000189")
    escritorio_b = criar_escritorio("Escritório DL-089 consultas B", "89892000000189")
    empresa_a1 = criar_empresa(
        escritorio=escritorio_a, razao_social="Empresa A1 DL-089 Ltda", cnpj="89893000000189"
    )
    empresa_a2 = criar_empresa(
        escritorio=escritorio_a, razao_social="Empresa A2 DL-089 Ltda", cnpj="89894000000189"
    )
    empresa_b1 = criar_empresa(
        escritorio=escritorio_b, razao_social="Empresa B1 DL-089 Ltda", cnpj="89895000000189"
    )
    planos = {}
    for empresa in (empresa_a1, empresa_a2, empresa_b1):
        planos[empresa.pk] = criar_plano(empresa)
    return {
        "a1": empresa_a1,
        "a2": empresa_a2,
        "b1": empresa_b1,
        "planos": planos,
    }


def _lancar(cenario, empresa, *, data=date(2026, 3, 10), **extra):
    contas = cenario["planos"][empresa.pk]
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico="Lançamento sintético DL-089",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
        **extra,
    )


def _automatico(cenario, empresa, identificador, *, data=date(2026, 3, 10)):
    return _lancar(
        cenario,
        empresa,
        data=data,
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(LOTE, identificador),
    )


# ---------------------------------------------------------------------------
# Documento → lançamentos
# ---------------------------------------------------------------------------


def test_documento_devolve_os_lancamentos_dele_em_ordem_cronologica(cenario):
    tarde = _automatico(cenario, cenario["a1"], 42, data=date(2026, 3, 20))
    cedo = _automatico(cenario, cenario["a1"], 42, data=date(2026, 3, 5))

    encontrados = list(
        lancamentos_do_documento_de_origem(empresa=cenario["a1"], tipo=LOTE, identificador=42)
    )

    assert [lanc.pk for lanc in encontrados] == [cedo.pk, tarde.pk]


def test_documento_nao_devolve_lancamento_manual_nem_de_outro_documento(cenario):
    _lancar(cenario, cenario["a1"])  # manual, sem documento
    _automatico(cenario, cenario["a1"], 99)  # outro documento
    alvo = _automatico(cenario, cenario["a1"], 42)

    encontrados = list(
        lancamentos_do_documento_de_origem(empresa=cenario["a1"], tipo=LOTE, identificador="42")
    )

    assert [lanc.pk for lanc in encontrados] == [alvo.pk]


def test_documento_com_mesmo_identificador_em_outra_empresa_nao_vaza(cenario):
    """ISOLAMENTO: o mesmo tipo e o mesmo número em outra empresa, e em outro escritório,
    não aparecem. Mutação de referência: sem o filtro `empresa=`, este teste reprova."""
    minha = _automatico(cenario, cenario["a1"], 42)
    _automatico(cenario, cenario["a2"], 42)  # mesmo escritório, outra empresa
    _automatico(cenario, cenario["b1"], 42)  # outro escritório

    encontrados = list(
        lancamentos_do_documento_de_origem(empresa=cenario["a1"], tipo=LOTE, identificador=42)
    )

    assert [lanc.pk for lanc in encontrados] == [minha.pk]
    assert all(lanc.empresa_id == cenario["a1"].pk for lanc in encontrados)


def test_documento_de_empresa_sem_lancamento_volta_vazio(cenario):
    _automatico(cenario, cenario["b1"], 42)

    encontrados = list(
        lancamentos_do_documento_de_origem(empresa=cenario["a1"], tipo=LOTE, identificador=42)
    )

    assert encontrados == []


def test_tipo_de_documento_desconhecido_e_recusado_e_nao_vira_consulta_vazia(cenario):
    _automatico(cenario, cenario["a1"], 42)

    with pytest.raises(LancamentoInvalido):
        lancamentos_do_documento_de_origem(
            empresa=cenario["a1"], tipo="escrituracao_inventada", identificador=42
        )


@pytest.mark.parametrize("identificador", [None, "", "   ", True])
def test_identificador_invalido_na_consulta_e_recusado(cenario, identificador):
    with pytest.raises(LancamentoInvalido):
        lancamentos_do_documento_de_origem(
            empresa=cenario["a1"], tipo=LOTE, identificador=identificador
        )


# ---------------------------------------------------------------------------
# Lançamento → documento
# ---------------------------------------------------------------------------


def test_lancamento_devolve_o_documento_que_o_originou(cenario):
    lancamento = _automatico(cenario, cenario["a1"], 42)

    documento = documento_de_origem_do_lancamento(
        empresa=cenario["a1"], lancamento_id=lancamento.pk
    )

    assert documento == DocumentoDeOrigem(tipo=LOTE, identificador="42")


def test_lancamento_manual_nao_tem_documento(cenario):
    lancamento = _lancar(cenario, cenario["a1"])

    assert (
        documento_de_origem_do_lancamento(empresa=cenario["a1"], lancamento_id=lancamento.pk)
        is None
    )


def test_lancamento_de_outra_empresa_nao_e_revelado_pela_consulta(cenario):
    """ISOLAMENTO: pedir o documento de um lançamento de outra empresa (mesmo do mesmo
    escritório, ou de outro escritório) falha como se o lançamento não existisse."""
    de_a2 = _automatico(cenario, cenario["a2"], 42)
    de_b1 = _automatico(cenario, cenario["b1"], 43)

    for alheio in (de_a2, de_b1):
        with pytest.raises(LancamentoContabil.DoesNotExist):
            documento_de_origem_do_lancamento(empresa=cenario["a1"], lancamento_id=alheio.pk)


# ---------------------------------------------------------------------------
# Caminho REAL da importação (DL-077): a efetivação grava origem e lote
# ---------------------------------------------------------------------------

CONTEUDO_PROPRIO = (
    "numero;data;historico;conta;lado;valor\r\n"
    "1;2026-03-10;Compra sintética;1.1.1;D;100.00\r\n"
    "1;2026-03-10;Compra sintética;5.1;C;100.00\r\n"
    "2;2026-03-11;Pagamento sintético;5.1;D;30.00\r\n"
    "2;2026-03-11;Pagamento sintético;1.1.1;C;30.00\r\n"
).encode("utf-8")


def test_efetivacao_da_importacao_grava_origem_importacao_e_o_lote_como_documento(cenario):
    importacao = servico.receber(
        empresa=cenario["a1"],
        formato="proprio",
        conteudo=CONTEUDO_PROPRIO,
        nome_arquivo="sintetico-dl089-efetivacao.txt",
        usuario=None,
    )
    if importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo:
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True)

    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    lancamentos = list(LancamentoContabil.objects.filter(empresa=cenario["a1"]).order_by("id"))
    assert len(lancamentos) == 2
    for lancamento in lancamentos:
        assert lancamento.origem == OrigemLancamento.IMPORTACAO
        assert lancamento.documento_origem_tipo == LOTE
        assert lancamento.documento_origem_id == str(importacao.pk)

    # A consulta parte do lote e chega aos dois lançamentos, e só a eles.
    achados = list(
        lancamentos_do_documento_de_origem(
            empresa=cenario["a1"], tipo=LOTE, identificador=importacao.pk
        )
    )
    assert [lanc.pk for lanc in achados] == [lanc.pk for lanc in lancamentos]


def test_diario_filtra_por_origem_e_so_soma_o_que_listou(cenario):
    manual = _lancar(cenario, cenario["a1"], data=date(2026, 3, 10))
    automatico = _automatico(cenario, cenario["a1"], 42, data=date(2026, 3, 11))

    so_automaticos = list(
        listar_diario(
            empresa=cenario["a1"],
            inicio=date(2026, 3, 1),
            fim=date(2026, 3, 31),
            origem=OrigemLancamento.IMPORTACAO,
        )
    )
    tudo = list(
        listar_diario(empresa=cenario["a1"], inicio=date(2026, 3, 1), fim=date(2026, 3, 31))
    )

    assert [lanc.pk for lanc in so_automaticos] == [automatico.pk]
    assert {lanc.pk for lanc in tudo} == {manual.pk, automatico.pk}


def test_diario_recusa_origem_desconhecida(cenario):
    with pytest.raises(LancamentoInvalido):
        listar_diario(
            empresa=cenario["a1"],
            inicio=date(2026, 3, 1),
            fim=date(2026, 3, 31),
            origem="inventada",
        )
