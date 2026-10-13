"""DL-091, correção da rodada 1, achado A1 (alta): o crédito olha o regime do COMPRADOR.

O comprador optante do Simples não se apropria de crédito (LC 123, art. 23, caput). Antes da
correção, a marca de crédito ignorava o regime: uma compra de comprador do Simples aparecia como
"crédito destacado: elegível" e entrava no total da conferência. Teste T1 da auditoria.

Regra pura (sem banco) com contexto explícito, e efetivação real (com banco) para a memória gravada
e a conferência. Dados sintéticos (CNPJs de teste). Plano: docs/planos/DL-091-nfe-de-entrada.md,
seção "Decisões para a correção (rodada 1)", A1.
"""

import html
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import conferencia_entradas as conferencia
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import MarcaCreditoEntrada, MemoriaEntradaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.test_dl091_entradas import (
    PRESUMIDO,
    _confirmar,
    _marca,
    _matriz,
    _nota,
    _rascunho,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A

pytestmark = pytest.mark.django_db

ICMS_18 = "<modBC>3</modBC><vBC>100.00</vBC><pICMS>18.00</pICMS><vICMS>18.00</vICMS>"
SIMPLES = entradas.ContextoDaEntrada(simples=True, normal=False, uf_empresa="TO")
SEM_REGIME = entradas.ContextoDaEntrada(simples=False, normal=False, uf_empresa="TO")
AMBIGUO_NO_DIA = entradas.ContextoDaEntrada(simples=True, normal=True, uf_empresa="TO")
SEM_CREDITO_OPTANTE = MarcaCreditoEntrada.SEM_CREDITO_OPTANTE_DO_SIMPLES


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora A1 rodada 1 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


def _regime(empresa, regime, inicio=date(2026, 1, 1), fim=None):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=regime, vigencia_inicio=inicio, vigencia_fim=fim
    )


# ---------------------------------------------------------------------------
# Regra pura: a marca pelo regime do comprador
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "natureza",
    [N.ENTRADA_COMERCIALIZACAO, N.ENTRADA_USO_CONSUMO, N.ENTRADA_ST, N.ENTRADA_ATIVO],
)
def test_comprador_do_simples_nunca_tem_credito_elegivel_em_nenhuma_natureza(
    escritorio_a, usuario_gestor_a, empresa, natureza
):
    """Vale para toda natureza que daria crédito no regime normal, inclusive com vICMS destacado."""
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, icms=xml.icms(cst="00", filhos=ICMS_18)
    )
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, natureza, SIMPLES) == (SEM_CREDITO_OPTANTE, None)


def test_comprador_do_simples_com_fornecedor_do_simples_e_pcredsn_tambem_nao_tem_credito(
    escritorio_a, usuario_gestor_a, empresa
):
    """T1: o fornecedor CRT 1 informa pCredSN e vCredICMSSN. O comprador optante não se credita, e
    o valor do fornecedor não vira crédito elegível (LC 123, art. 23, caput)."""
    icms = xml.icms(csosn="101", filhos="<pCredSN>2.8000</pCredSN><vCredICMSSN>28.00</vCredICMSSN>")
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, crt="1", icms=icms, vprod="1000.00")
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO, SIMPLES) == (
        SEM_CREDITO_OPTANTE,
        None,
    )


def test_comprador_do_regime_normal_com_mesma_nota_continua_com_credito_destacado(
    escritorio_a, usuario_gestor_a, empresa
):
    """Controle: a mesma compra, com comprador do Presumido, tem o crédito de 18,00 como antes."""
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, icms=xml.icms(cst="00", filhos=ICMS_18)
    )
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO, PRESUMIDO) == (
        MarcaCreditoEntrada.CREDITO_DESTACADO,
        Decimal("18.00"),
    )


@pytest.mark.parametrize("natureza", [N.ENTRADA_COMERCIALIZACAO, N.ENTRADA_USO_CONSUMO])
def test_regime_desconhecido_na_data_fica_a_conferir_e_nao_e_elegivel(
    escritorio_a, usuario_gestor_a, empresa, natureza
):
    """Sem regime cadastrado na data, nem "elegível" nem "vedado": "a conferir", sem valor."""
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, icms=xml.icms(cst="00", filhos=ICMS_18)
    )
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, natureza, SEM_REGIME) == (MarcaCreditoEntrada.A_CONFERIR, None)


def test_regime_ambiguo_no_dia_de_transicao_fica_a_conferir(
    escritorio_a, usuario_gestor_a, empresa
):
    """Simples e normal ao mesmo tempo na data (transição no dia): não se escolhe um dos dois."""
    documento = _nota(
        escritorio_a, usuario_gestor_a, empresa, icms=xml.icms(cst="00", filhos=ICMS_18)
    )
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMERCIALIZACAO, AMBIGUO_NO_DIA) == (
        MarcaCreditoEntrada.A_CONFERIR,
        None,
    )


def test_monofasico_pelo_ncm_vem_antes_do_regime_e_nao_vira_optante(
    escritorio_a, usuario_gestor_a, empresa
):
    """A marca de monofásico é um fato do produto (LC 192, art. 2º): vale para o optante também,
    e a ordem das regras mantém essa marca, sem o rótulo de optante."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, ncm="27101921", cfop="5655")
    item = documento.itens.get(n_item=1)
    assert _marca(documento, item, N.ENTRADA_COMBUSTIVEL_REVENDA, SIMPLES) == (
        MarcaCreditoEntrada.MONOFASICO,
        None,
    )


# ---------------------------------------------------------------------------
# Com banco: efetivação, memória gravada, conferência e tela
# ---------------------------------------------------------------------------


def test_efetivacao_do_comprador_do_simples_grava_marca_sem_credito_e_a_conferencia_nao_soma(
    escritorio_a, usuario_gestor_a, empresa
):
    _regime(empresa, RegimeTributario.SIMPLES_NACIONAL)
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)

    servico.efetivar(esc, usuario=usuario_gestor_a)

    memoria = MemoriaEntradaItemNFe.objects.get(natureza_item__escrituracao=esc)
    assert memoria.marca_credito == SEM_CREDITO_OPTANTE
    assert memoria.credito_elegivel is None
    # O vICMS da nota continua copiado (é fato da nota), mas não é crédito aproveitável.
    assert memoria.v_icms == Decimal("18.00")
    resultado = conferencia.conferencia_de_entradas(empresa, 2026, 3)
    assert resultado.credito_destacado_elegivel == Decimal("0.00")
    assert [(t.marca, t.itens, t.credito) for t in resultado.por_marca] == [
        (SEM_CREDITO_OPTANTE, 1, Decimal("0.00"))
    ]


def test_conferencia_soma_o_credito_do_comprador_do_regime_normal(
    escritorio_a, usuario_gestor_a, empresa
):
    """Controle com banco: o comprador do Presumido tem o total elegível de 18,00."""
    _regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)

    resultado = conferencia.conferencia_de_entradas(empresa, 2026, 3)

    assert resultado.credito_destacado_elegivel == Decimal("18.00")


def test_tela_mostra_o_rotulo_de_optante_e_nenhum_credito_admitido(
    client, escritorio_a, usuario_gestor_a, empresa
):
    _regime(empresa, RegimeTributario.SIMPLES_NACIONAL)
    _matriz(empresa, escritorio_a, "TO")
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.get(
        reverse(
            "fiscal_web:nfe_escriturar",
            args=[empresa.pk, vinculo(esc.vinculo.documento, empresa).pk],
        )
    )

    texto = " ".join(html.unescape(resposta.content.decode("utf-8")).split())
    assert resposta.status_code == 200
    assert "Sem crédito: comprador optante do Simples (LC 123, art. 23, caput)" in texto
    # O template envolve o valor num <span>: a asserção casa o HTML real, não o texto puro.
    assert 'Crédito admitido: <span class="valor-monetario">nenhum</span>' in texto
    assert "Crédito destacado: elegível" not in texto
