"""DL-091, correção da rodada 1: A2 (devolução de compra não reabre o mês confirmado) e A3
(reclassificação em massa só mexe em rascunho de saída e de devolução de venda).

A2 (teste T2): a `DEVOLUCAO_COMPRA` tem natureza fora da receita, como a compra. Efetivar ou
estornar
não pode marcar o mês confirmado "a retificar", senão o pré-DAS é recusado sem mudança de receita.
A venda continua reabrindo o mês (contra-teste).

A3 (teste T3): a troca em massa de natureza não pode tocar compra nem devolução de compra, cujo CFOP
de entrada é confirmado junto com a natureza.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

from datetime import date

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import EscrituracaoNFe, EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import test_dl091_receita as receita_dl091
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    fixar_inicio_de_uso,
    preparar_simples,
    sequencia,
)
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _nota, _rascunho
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

CONFIRMADO = receita_servico.SITUACAO_CONFIRMADO
A_RETIFICAR = receita_servico.SITUACAO_A_RETIFICAR


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-rodada1-mes")


@pytest.fixture
def simples(escritorio_a):
    """Simples Nacional com março de 2026 confirmado (o caso em que o pré-DAS é lido)."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Simples rodada 1 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2025, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _venda(escritorio, usuario, empresa, *, numero, cfop="5102", vprod="50.00"):
    """Saída própria (a empresa emite, tpNF 1, finNFe 1) para um destinatário sintético."""
    return _nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        cfop=cfop,
        vprod=vprod,
        tp_nf="1",
        fin_nfe="1",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )


# ---------------------------------------------------------------------------
# A2: a devolução de compra não reabre o mês confirmado (T2)
# ---------------------------------------------------------------------------


def test_devolucao_de_compra_efetivada_nao_reabre_o_mes_confirmado(escritorio_a, gestor, simples):
    receita_dl091._vendas_do_simples(escritorio_a, gestor, simples)
    confirmar_meses(simples, gestor, sequencia(2025, 3, 13))
    assert receita_servico.situacao_do_mes(simples, 2026, 3) == CONFIRMADO

    receita_dl091._devolucao_de_compra(escritorio_a, gestor, simples)

    assert receita_servico.situacao_do_mes(simples, 2026, 3) == CONFIRMADO
    # O pré-DAS só recusa mês que não está confirmado. Com a devolução, março continua confirmado.
    pre_das_servico.pre_das(simples, 2026, 3)


def test_estorno_de_devolucao_de_compra_tambem_nao_reabre_o_mes(escritorio_a, gestor, simples):
    receita_dl091._vendas_do_simples(escritorio_a, gestor, simples)
    confirmar_meses(simples, gestor, sequencia(2025, 3, 13))
    devolucao = receita_dl091._devolucao_de_compra(escritorio_a, gestor, simples)

    servico.estornar(devolucao, "lançada no mês errado", gestor)

    assert receita_servico.situacao_do_mes(simples, 2026, 3) == CONFIRMADO
    pre_das_servico.pre_das(simples, 2026, 3)


def test_venda_efetivada_em_mes_confirmado_ainda_reabre_o_mes(escritorio_a, gestor, simples):
    """Contra-teste: só a devolução de compra é poupada. A venda muda a receita e continua
    marcando o mês "a retificar"."""
    receita_dl091._vendas_do_simples(escritorio_a, gestor, simples)
    confirmar_meses(simples, gestor, sequencia(2025, 3, 13))
    venda = receita_dl091._nota(
        escritorio_a,
        gestor,
        numero="901",
        cnpj_emitente=CNPJ_EMITENTE_A,
        cnpj_destinatario=CNPJ_DESTINATARIO_A,
        cfop="5102",
        vprod="50.00",
        tp_nf="1",
    )

    receita_dl091._efetivar(venda, simples, gestor, N.REVENDA)

    assert receita_servico.situacao_do_mes(simples, 2026, 3) == A_RETIFICAR


# ---------------------------------------------------------------------------
# A3: reclassificação em massa só em saída e devolução de venda (T3)
# ---------------------------------------------------------------------------


def test_reclassificacao_em_massa_altera_a_venda_e_preserva_a_compra_em_rascunho(
    escritorio_a, usuario_gestor_a, empresa_de_teste
):
    """Venda e compra em rascunho, ambas com CFOP 5.102 do emitente. O filtro por CFOP casa as
    duas, e antes da correção a operação era recusada inteira por causa da compra."""
    venda = _venda(escritorio_a, usuario_gestor_a, empresa_de_teste, numero="911")
    esc_venda = servico.criar_rascunho(vinculo(venda, empresa_de_teste), usuario=usuario_gestor_a)
    compra = _rascunho(escritorio_a, usuario_gestor_a, empresa_de_teste, numero="912")
    _confirmar(compra, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)

    resultado = servico.reclassificar_em_massa(
        empresa_de_teste,
        N.REVENDA,
        servico.FiltrosReclassificacao(cfop="5102"),
        usuario_gestor_a,
    )

    assert resultado.escrituracoes_afetadas == 1
    assert resultado.itens_alterados == 1
    assert set(
        NaturezaItemNFe.objects.filter(escrituracao=esc_venda).values_list("natureza", flat=True)
    ) == {N.REVENDA}
    registro_compra = NaturezaItemNFe.objects.get(escrituracao=compra)
    assert (registro_compra.natureza, registro_compra.cfop_entrada) == (
        N.ENTRADA_COMERCIALIZACAO,
        "1102",
    )


def test_reclassificacao_de_natureza_de_entrada_com_so_compra_nao_muda_nada(
    escritorio_a, usuario_gestor_a, empresa_de_teste
):
    """Antes da correção, E1 com CFOP 1.102 virava E4 com o CFOP 1.102 gravado: combinação inválida,
    que a efetivação recusava depois. Agora a compra fica fora, e nada muda."""
    compra = _rascunho(escritorio_a, usuario_gestor_a, empresa_de_teste, numero="913")
    _confirmar(compra, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)

    resultado = servico.reclassificar_em_massa(
        empresa_de_teste,
        N.ENTRADA_USO_CONSUMO,
        servico.FiltrosReclassificacao(cfop="5102"),
        usuario_gestor_a,
    )

    assert resultado.escrituracoes_afetadas == 0
    assert resultado.itens_alterados == 0
    registro = NaturezaItemNFe.objects.get(escrituracao=compra)
    assert (registro.natureza, registro.cfop_entrada) == (N.ENTRADA_COMERCIALIZACAO, "1102")
    assert EscrituracaoNFe.objects.get(pk=compra.pk).estado == EstadoEscrituracao.RASCUNHO


@pytest.fixture
def empresa_de_teste(escritorio_a):
    """Empresa com o CNPJ de destinatário das compras sintéticas (a empresa compra e vende)."""
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Reclassificação rodada 1 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
