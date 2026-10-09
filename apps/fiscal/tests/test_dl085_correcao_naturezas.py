"""DL-085, correção da auditoria rodada 1 (2026-10-09): natureza já escolhida no rascunho (A2).

Opção (a) do arquiteto: um rascunho cuja natureza já gravada difere da sugestão sai do lote, com o
motivo "natureza já escolhida no rascunho: escriture esta nota individualmente". Sem natureza
gravada, ou com a mesma natureza da sugestão, a nota entra como antes. A mesma regra vale na
efetivação: se a natureza escolhida aparece depois da confirmação, a nota falha e não é sobrescrita.

Dados sintéticos (`suporte_dl085`). Os valores esperados estão escritos à mão.
"""

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    DocumentoNFe,
    EscrituracaoNFe,
    EstadoEscrituracao,
    ItemNFe,
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
    NaturezaItemNFe,
)
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import CFOP_REVENDA, nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

ANO, MES = 2026, 3
NATUREZA_DA_SUGESTAO = "revenda"
NATUREZA_ESCOLHIDA = "bonificacao"

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-naturezas-dl085")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Naturezas DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _revenda(escritorio, usuario, numero, valor="100.00"):
    """NFC-e de revenda (CFOP 5102, CSOSN 102): a sugestão é `revenda`."""
    return nfce(escritorio, usuario, numero=numero, valor=valor, cfop=CFOP_REVENDA, csosn="102")


def _rascunho_com_natureza(documento, empresa, natureza, usuario):
    """Rascunho individual com a natureza escolhida pelo contador, em todos os itens da nota."""
    rascunho = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = [item.pk for item in ItemNFe.objects.filter(documento=documento)]
    servico_nfe.definir_natureza(rascunho, natureza, ids, usuario=usuario)
    return rascunho


def _naturezas(rascunho):
    return set(
        NaturezaItemNFe.objects.filter(escrituracao=rascunho).values_list("natureza", flat=True)
    )


def test_rascunho_com_natureza_diferente_da_sugestao_sai_do_lote_com_o_motivo(
    escritorio_a, gestor, empresa
):
    _revenda(escritorio_a, gestor, 1)
    _revenda(escritorio_a, gestor, 2, valor="50.00")
    documento_1 = DocumentoNFe.objects.get(numero="1")
    rascunho = _rascunho_com_natureza(documento_1, empresa, NATUREZA_ESCOLHIDA, gestor)

    previa = previa_lida(empresa, ANO, MES)

    recusa = next(r for r in previa.fora if r.numero == "1")
    assert recusa.codigo == lote.CODIGO_NATUREZA_ESCOLHIDA
    assert recusa.motivo == "natureza já escolhida no rascunho: escriture esta nota individualmente"
    assert [n.numero for g in previa.grupos for n in g.notas] == ["2"]

    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=100)

    assert progresso.efetivadas_total == 1
    rascunho.refresh_from_db()
    # A natureza do contador não muda em silêncio, e a nota não é efetivada pelo lote.
    assert _naturezas(rascunho) == {NATUREZA_ESCOLHIDA}
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert not EscrituracaoNFe.objects.filter(
        vinculo__documento__numero="1", estado=EstadoEscrituracao.EFETIVADA
    ).exists()


def test_rascunho_com_a_natureza_sugerida_entra_no_lote(escritorio_a, gestor, empresa):
    _revenda(escritorio_a, gestor, 1)
    _revenda(escritorio_a, gestor, 2, valor="50.00")
    _rascunho_com_natureza(
        DocumentoNFe.objects.get(numero="1"), empresa, NATUREZA_DA_SUGESTAO, gestor
    )

    previa = previa_lida(empresa, ANO, MES)

    assert previa.fora == ()
    assert sorted(n.numero for g in previa.grupos for n in g.notas) == ["1", "2"]
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=100)
    assert progresso.efetivadas_total == 2


def test_natureza_escolhida_depois_da_confirmacao_falha_a_nota_sem_sobrescrever(
    escritorio_a, gestor, empresa
):
    """Confirmado sem o rascunho. Depois da primeira parte, o contador escolhe outra natureza para
    a nota pendente. A parte não a sobrescreve: a nota falha, com o motivo, e o rascunho fica como
    está."""
    _revenda(escritorio_a, gestor, 1)
    _revenda(escritorio_a, gestor, 2, valor="50.00")
    previa = previa_lida(empresa, ANO, MES)
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    assert progresso.efetivadas_total == 1
    pendente = LoteEscrituracaoNFeNota.objects.select_related("vinculo__documento").get(
        lote_id=progresso.lote_id, estado="pendente"
    )
    rascunho = _rascunho_com_natureza(
        pendente.vinculo.documento, empresa, NATUREZA_ESCOLHIDA, gestor
    )

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, gestor, limite=100, lote_id=progresso.lote_id
    )

    assert progresso.terminou
    assert progresso.falhas_total == 1
    falha = progresso.falhas_nesta_chamada[0]
    assert falha.vinculo_id == pendente.vinculo_id
    assert falha.motivo == lote.MENSAGEM_NATUREZA_ESCOLHIDA
    rascunho.refresh_from_db()
    assert _naturezas(rascunho) == {NATUREZA_ESCOLHIDA}
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    pendente.refresh_from_db()
    assert pendente.estado == "falhou"
    assert LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id).estado == "concluido"
