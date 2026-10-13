"""DL-091, ajustes do arquiteto depois da reconferência (N1, N2, N3 e N5; §3.1 do AGENTS.md).

A reconferência foi a última rodada permitida. Cada ajuste tem aqui o teste que o prende. Dados
sintéticos. Relatório: docs/auditorias/2026-10-13-dl-091-reconferencia.md.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe, EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

UTC = ZoneInfo("UTC")
FUSO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def empresa(escritorio_a):
    """Empresa que compra (destinatária) e que também emite (venda e devolução de compra)."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Ajustes DL091 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _relogio(monkeypatch, instante):
    monkeypatch.setattr(timezone, "now", lambda: instante)


# ---------------------------------------------------------------------------
# N1: a efetivação também recusa data de entrada posterior a hoje
# ---------------------------------------------------------------------------


def test_n1_efetivacao_recusa_rascunho_com_data_de_entrada_futura(
    escritorio_a, usuario_gestor_a, empresa, monkeypatch
):
    _relogio(monkeypatch, datetime(2026, 10, 13, 12, 0, tzinfo=FUSO))
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="9101")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    # Rascunho gravado por outro caminho (não pela tela, pela API nem pelo serviço de troca).
    EscrituracaoNFe.objects.filter(pk=esc.pk).update(data_entrada=date(2062, 3, 15))

    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(EscrituracaoNFe.objects.get(pk=esc.pk), usuario=usuario_gestor_a)

    assert erro.value.mensagem == entradas.MOTIVO_DATA_POSTERIOR_A_HOJE
    assert EscrituracaoNFe.objects.get(pk=esc.pk).estado == EstadoEscrituracao.RASCUNHO


# ---------------------------------------------------------------------------
# N2: "hoje" é o dia em São Paulo, não em UTC
# ---------------------------------------------------------------------------


def test_n2_hoje_e_o_dia_em_sao_paulo(escritorio_a, usuario_gestor_a, empresa, monkeypatch):
    """01h30 UTC de 14/10 ainda é 22h30 de 13/10 em São Paulo: 14/10 é futuro, 13/10 vale."""
    _relogio(monkeypatch, datetime(2026, 10, 14, 1, 30, tzinfo=UTC))
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="9102")

    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        servico.criar_rascunho(
            vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 10, 14)
        )
    assert erro.value.mensagem == entradas.MOTIVO_DATA_POSTERIOR_A_HOJE

    esc = servico.criar_rascunho(
        vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 10, 13)
    )
    assert esc.data_entrada == date(2026, 10, 13)


# ---------------------------------------------------------------------------
# N3: a reclassificação em massa deixa a devolução de compra de fora
# ---------------------------------------------------------------------------


def _saida_propria(escritorio, usuario, empresa, *, numero, cfop, fin_nfe):
    return _nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        cfop=cfop,
        tp_nf="1",
        fin_nfe=fin_nfe,
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )


def test_n3_reclassificacao_altera_a_venda_e_deixa_a_devolucao_de_compra(
    escritorio_a, usuario_gestor_a, empresa
):
    venda = _saida_propria(
        escritorio_a, usuario_gestor_a, empresa, numero="9103", cfop="5102", fin_nfe="1"
    )
    esc_venda = servico.criar_rascunho(vinculo(venda, empresa), usuario=usuario_gestor_a)
    devolucao = _saida_propria(
        escritorio_a, usuario_gestor_a, empresa, numero="9104", cfop="5202", fin_nfe="4"
    )
    esc_dev = servico.criar_rascunho(vinculo(devolucao, empresa), usuario=usuario_gestor_a)
    ids_dev = list(
        NaturezaItemNFe.objects.filter(escrituracao=esc_dev).values_list("item_id", flat=True)
    )
    servico.definir_natureza(esc_dev, N.DEVOLUCAO_COMPRA, ids_dev, usuario=usuario_gestor_a)

    resultado = servico.reclassificar_em_massa(
        empresa, N.REVENDA, servico.FiltrosReclassificacao(), usuario_gestor_a
    )

    assert resultado.escrituracoes_afetadas == 1
    assert set(
        NaturezaItemNFe.objects.filter(escrituracao=esc_venda).values_list("natureza", flat=True)
    ) == {N.REVENDA}
    assert set(
        NaturezaItemNFe.objects.filter(escrituracao=esc_dev).values_list("natureza", flat=True)
    ) == {N.DEVOLUCAO_COMPRA}


# ---------------------------------------------------------------------------
# N5: o estorno da devolução de compra é chamado pelo nome
# ---------------------------------------------------------------------------


def test_n5_estorno_da_devolucao_de_compra_diz_devolucao_de_compra(
    client, escritorio_a, usuario_gestor_a, empresa
):
    devolucao = _saida_propria(
        escritorio_a, usuario_gestor_a, empresa, numero="9105", cfop="5202", fin_nfe="4"
    )
    esc = servico.criar_rascunho(vinculo(devolucao, empresa), usuario=usuario_gestor_a)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario_gestor_a)
    esc = servico.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    html = client.get(reverse("fiscal_web:nfe_estornar", args=[empresa.pk, esc.pk])).content.decode(
        "utf-8"
    )

    assert "A escrituração da devolução de compra nº 9105" in html
    assert "A compra não compõe a receita" in html
