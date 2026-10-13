"""DL-091, correção da rodada 1: lote de compras (DL-085 para ENTRADA).

- A4 (teste T4): o CFOP de entrada gravado no rascunho que difere do sugerido é escolha do contador.
  A nota sai do lote com `CODIGO_NATUREZA_ESCOLHIDA`, na prévia e na revalidação da efetivação.
  Antes,
  o lote regravava o CFOP sugerido em silêncio.
- A8 (teste T10, lote): compra de 2027 (Presumido) entra no lote e efetiva, como a individual.
- A8 (teste T12, lote): a natureza escolhida no lote leva o CFOP FINAL (o da natureza escolhida),
  e não o sugerido.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

from datetime import date

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    EstadoEscrituracao,
    LoteEscrituracaoNFeNota,
    NaturezaItemNFe,
)
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, previa_lida
from apps.fiscal.tests.test_dl091_entradas import _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A

pytestmark = pytest.mark.django_db

DH_MARCO = "2026-03-15T10:00:00-03:00"
DH_2027 = "2027-02-10T10:00:00-03:00"


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Lote rodada 1 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _rascunho_com_cfop(documento, empresa, usuario, natureza, cfop):
    """Rascunho com natureza e CFOP de entrada escolhidos pelo contador, em todos os itens."""
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    entradas.definir_natureza_de_entrada(esc, natureza, cfop, ids, usuario=usuario)
    return esc


def _registros(escrituracao):
    return list(NaturezaItemNFe.objects.filter(escrituracao=escrituracao).order_by("item__n_item"))


# ---------------------------------------------------------------------------
# A4: CFOP escolhido no rascunho não é trocado em silêncio (T4)
# ---------------------------------------------------------------------------


def test_rascunho_com_cfop_escolhido_diferente_do_sugerido_sai_do_lote(
    escritorio_a, usuario_gestor_a, empresa
):
    """Natureza E1 é a sugerida, mas o contador gravou o CFOP 1.113 (válido no grupo E1). O sugerido
    é 1.102. Antes da correção o lote confirmava com 1.102, sem aviso."""
    doc_1 = _nota(escritorio_a, usuario_gestor_a, empresa, numero="1")
    doc_2 = _nota(escritorio_a, usuario_gestor_a, empresa, numero="2")
    rascunho = _rascunho_com_cfop(
        doc_1, empresa, usuario_gestor_a, N.ENTRADA_COMERCIALIZACAO, "1113"
    )

    previa = previa_lida(empresa, 2026, 3)

    recusa = next(f for f in previa.fora if f.numero == "1")
    assert recusa.codigo == lote.CODIGO_NATUREZA_ESCOLHIDA
    assert [n.numero for g in previa.grupos for n in g.notas] == [doc_2.numero]
    progresso = confirmar_tudo(empresa, usuario_gestor_a, 2026, 3, previa)
    assert progresso.efetivadas_total == 1
    rascunho.refresh_from_db()
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert [(r.natureza, r.cfop_entrada) for r in _registros(rascunho)] == [
        (N.ENTRADA_COMERCIALIZACAO, "1113")
    ]


def test_rascunho_com_o_cfop_sugerido_entra_no_lote(escritorio_a, usuario_gestor_a, empresa):
    """Controle: escolha igual à sugestão (E1, 1.102) não é divergência, e a nota entra."""
    doc_1 = _nota(escritorio_a, usuario_gestor_a, empresa, numero="1")
    _rascunho_com_cfop(doc_1, empresa, usuario_gestor_a, N.ENTRADA_COMERCIALIZACAO, "1102")

    previa = previa_lida(empresa, 2026, 3)

    assert previa.fora == ()
    progresso = confirmar_tudo(empresa, usuario_gestor_a, 2026, 3, previa)
    assert progresso.efetivadas_total == 1


def test_cfop_escolhido_depois_da_previa_falha_a_nota_na_revalidacao_sem_sobrescrever(
    escritorio_a, usuario_gestor_a, empresa
):
    """A prévia não viu o rascunho. Depois da primeira parte, o contador grava o CFOP 1.113 na nota
    pendente. A revalidação da efetivação recusa a nota com a mensagem, e o CFOP não muda."""
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="1")
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="2")
    previa = previa_lida(empresa, 2026, 3)
    progresso = lote.confirmar_lote(
        empresa, 2026, 3, previa.assinatura, {}, usuario_gestor_a, limite=1
    )
    assert progresso.efetivadas_total == 1
    pendente = LoteEscrituracaoNFeNota.objects.select_related("vinculo__documento").get(
        lote_id=progresso.lote_id, estado="pendente"
    )
    rascunho = _rascunho_com_cfop(
        pendente.vinculo.documento, empresa, usuario_gestor_a, N.ENTRADA_COMERCIALIZACAO, "1113"
    )

    progresso = lote.confirmar_lote(
        empresa, None, None, None, None, usuario_gestor_a, limite=100, lote_id=progresso.lote_id
    )

    assert progresso.terminou
    assert progresso.falhas_total == 1
    falha = progresso.falhas_nesta_chamada[0]
    assert falha.motivo == lote.MENSAGEM_NATUREZA_ESCOLHIDA
    rascunho.refresh_from_db()
    assert rascunho.estado == EstadoEscrituracao.RASCUNHO
    assert [r.cfop_entrada for r in _registros(rascunho)] == ["1113"]


# ---------------------------------------------------------------------------
# A8 (lote): compra de 2027 e natureza escolhida com o CFOP final (T10, T12)
# ---------------------------------------------------------------------------


def test_compra_de_2027_entra_no_lote_e_efetiva_no_presumido(
    escritorio_a, usuario_gestor_a, empresa
):
    """T10 (lote): a regra de receita de 2027 não se aplica à compra. Ela entra no lote e efetiva,
    como a individual (ver o teste da efetivação individual abaixo)."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="2702", dh_emi=DH_2027)

    previa = previa_lida(empresa, 2027, 2)

    assert [f for f in previa.fora if f.numero == "2702"] == []
    assert [n.numero for g in previa.grupos for n in g.notas] == ["2702"]
    progresso = confirmar_tudo(empresa, usuario_gestor_a, 2027, 2, previa)
    assert progresso.efetivadas_total == 1


def test_compra_de_2027_efetiva_individualmente_no_presumido(
    escritorio_a, usuario_gestor_a, empresa
):
    """T10 (individual): a mesma compra de 2027 efetiva pelo caminho individual."""
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="2703", dh_emi=DH_2027)
    esc = _rascunho_com_cfop(
        documento, empresa, usuario_gestor_a, N.ENTRADA_COMERCIALIZACAO, "1102"
    )

    efetivada = servico.efetivar(esc, usuario=usuario_gestor_a)

    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.competencia.year == 2027


def test_escolha_de_natureza_no_lote_grava_o_cfop_final_da_natureza_escolhida(
    escritorio_a, usuario_gestor_a, empresa
):
    """T12 (lote): o grupo sugerido é E1 (CFOP 1.102). O contador escolhe E6 (combustível para
    revenda), cujo CFOP de entrada é 1.652. A efetivação grava 1.652, e não o sugerido 1.102, que
    não pertence ao grupo E6."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="1201")
    previa = previa_lida(empresa, 2026, 3)
    grupo = next(g for g in previa.grupos if g.tipo == "entrada")
    assinatura = grupo.assinaturas[0]
    assert assinatura.natureza == N.ENTRADA_COMERCIALIZACAO

    progresso = confirmar_tudo(
        empresa,
        usuario_gestor_a,
        2026,
        3,
        previa,
        escolhas={grupo.chave: {assinatura.id: N.ENTRADA_COMBUSTIVEL_REVENDA}},
    )

    assert progresso.efetivadas_total == 1
    efetivada = EscrituracaoNFe.objects.get(
        vinculo__documento=documento, estado=EstadoEscrituracao.EFETIVADA
    )
    assert [(r.natureza, r.cfop_entrada) for r in _registros(efetivada)] == [
        (N.ENTRADA_COMBUSTIVEL_REVENDA, "1652")
    ]
