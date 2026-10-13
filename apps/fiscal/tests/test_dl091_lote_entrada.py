"""DL-091 (frente A2): lote da DL-085 para ENTRADAS (compra).

Cobre: a prévia por grupo com o CFOP de entrada sugerido (e a nota sem CFOP padrão fora do lote); a
compra sem receita (sem atribuição de receita e sem W16, só o vNF); a equivalência entre o lote e a
escrituração individual; a assinatura que muda quando a regra muda (409 para a confirmação antiga);
a recusa de uma natureza escolhida sem CFOP de entrada padrão; e a confirmação em partes, sem
duplicar.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, A2 (item 4 do escopo).
"""

from datetime import date

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import classificacao as cl
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    MemoriaEntradaItemNFe,
    PapelNFe,
    TipoEscrituracaoNFe,
    VinculoNFeEmpresa,
)
from apps.fiscal.models import (
    NaturezaOperacaoNFe as N,
)
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, previa_lida
from apps.fiscal.tests.test_dl091_entradas import _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A

pytestmark = pytest.mark.django_db

ENTRADA = TipoEscrituracaoNFe.ENTRADA
MARCO = (2026, 3)
ABRIL = (2026, 4)
DH_MARCO = "2026-03-15T10:00:00-03:00"
DH_ABRIL = "2026-04-10T10:00:00-03:00"


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Compradora lote A2 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _compra(escritorio, usuario, empresa, numero, dh=DH_MARCO, **campos):
    return _nota(escritorio, usuario, empresa, numero=numero, dh_emi=dh, **campos)


def _grupo_de_entrada(previa):
    grupos = [g for g in previa.grupos if g.tipo == ENTRADA]
    assert len(grupos) == 1, previa.grupos
    return grupos[0]


def _resumo_das_notas(empresa):
    """(número, natureza, CFOP de entrada, marca) de cada item das compras efetivadas."""
    saida = []
    for esc in EscrituracaoNFe.objects.filter(empresa=empresa, tipo=ENTRADA).order_by(
        "vinculo__documento__numero"
    ):
        for registro in esc.naturezas_dos_itens.select_related("item").order_by("item__n_item"):
            memoria = MemoriaEntradaItemNFe.objects.get(natureza_item=registro)
            saida.append(
                (
                    esc.vinculo.documento.numero,
                    registro.natureza,
                    registro.cfop_entrada,
                    memoria.marca_credito,
                )
            )
    return saida


# ---------------------------------------------------------------------------
# Prévia
# ---------------------------------------------------------------------------


def test_previa_agrupa_compras_com_cfop_de_entrada_e_deixa_fora_a_sem_padrao(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1001")
    _compra(escritorio_a, usuario_gestor_a, empresa, "1002")
    # CFOP 5949 não tem sinal de entrada: a sugestão é vazia, e a nota sai do lote com o motivo.
    _compra(escritorio_a, usuario_gestor_a, empresa, "1003", cfop="5949")

    previa = previa_lida(empresa, *MARCO)

    grupo = _grupo_de_entrada(previa)
    assert grupo.quantidade_notas == 2
    assert {a.natureza for a in grupo.assinaturas} == {N.ENTRADA_COMERCIALIZACAO}
    assert {a.cfop_entrada for a in grupo.assinaturas} == {"1102"}
    assert grupo.receita_bruta == 0 and grupo.devolucao == 0
    fora = {f.numero: f.codigo for f in previa.fora}
    assert fora == {"1003": "sem_sugestao"}


def test_compra_com_natureza_sem_cfop_padrao_sai_do_lote_com_motivo(
    escritorio_a, usuario_gestor_a, empresa
):
    """Regra fixa a natureza de uso e consumo para o 5.102, sem CFOP de entrada. A A1 não sugere o
    1.556 para o 5.102 (o grupo de uso tem vários CFOP), então não há padrão e a nota fica fora."""
    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo=ENTRADA,
            cfop="5102",
            natureza=N.ENTRADA_USO_CONSUMO,
            vigencia_inicio=date(2026, 1, 1),
        ),
        usuario=usuario_gestor_a,
    )
    _compra(escritorio_a, usuario_gestor_a, empresa, "1101")

    previa = previa_lida(empresa, *MARCO)

    assert not [g for g in previa.grupos if g.tipo == ENTRADA]
    fora = {f.numero: f.codigo for f in previa.fora}
    assert fora == {"1101": lote.CODIGO_CFOP_DE_ENTRADA_A_ESCOLHER}


def test_previa_de_impacto_de_regra_de_entrada_conta_a_compra_que_sai_da_fila(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1201", cfop="5949")
    dados = cl.DadosDaRegra(
        tipo=ENTRADA,
        cfop="5949",
        natureza=N.ENTRADA_SERVICO,
        vigencia_inicio=date(2026, 1, 1),
    )
    impacto = cl.previa_de_impacto(empresa, 2026, 3, dados, cl.ESCOPO_ESCRITORIO)
    assert impacto.itens_a_escriturar == 1
    assert impacto.itens_que_saem_da_fila == 1
    assert impacto.itens_que_mudam == 1


# ---------------------------------------------------------------------------
# Assinatura: muda com a regra, e a confirmação antiga recebe 409
# ---------------------------------------------------------------------------


def test_assinatura_inclui_o_cfop_de_entrada_e_muda_quando_a_regra_muda(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1301")
    antes = previa_lida(empresa, *MARCO)

    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo=ENTRADA,
            cfop="5102",
            natureza=N.ENTRADA_COMERCIALIZACAO,
            cfop_entrada="1113",
            vigencia_inicio=date(2026, 1, 1),
        ),
        usuario=usuario_gestor_a,
    )
    depois = lote.previa_do_lote(empresa, *MARCO)

    assert depois.assinatura != antes.assinatura
    assert _grupo_de_entrada(depois).assinaturas[0].cfop_entrada == "1113"


def test_confirmacao_com_previa_antiga_recebe_409_e_nada_e_efetivado(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1401")
    antes = previa_lida(empresa, *MARCO)
    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo=ENTRADA,
            cfop="5102",
            natureza=N.ENTRADA_COMERCIALIZACAO,
            cfop_entrada="1113",
            vigencia_inicio=date(2026, 1, 1),
        ),
        usuario=usuario_gestor_a,
    )

    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(empresa, *MARCO, antes.assinatura, {}, usuario_gestor_a)
    assert not EscrituracaoNFe.objects.filter(empresa=empresa, estado="efetivada").exists()


# ---------------------------------------------------------------------------
# Escolha de natureza e confirmação
# ---------------------------------------------------------------------------


def test_escolha_de_natureza_sem_cfop_padrao_e_recusada_e_nada_e_gravado(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1501")
    previa = previa_lida(empresa, *MARCO)
    grupo = _grupo_de_entrada(previa)
    escolha = {grupo.chave: {grupo.assinaturas[0].id: N.ENTRADA_USO_CONSUMO}}

    with pytest.raises(servico.EntradaInvalidaNFe):
        lote.confirmar_lote(empresa, *MARCO, previa.assinatura, escolha, usuario_gestor_a)
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_lote_de_compras_e_equivalente_a_escrituracao_individual(
    escritorio_a, usuario_gestor_a, empresa
):
    """Mesmas compras, em dois meses: março pelo lote e abril nota a nota. Natureza, CFOP de
    entrada, marca de crédito e situação saem iguais (DL-085, critério 3)."""
    for numero in ("1601", "1602"):
        _compra(escritorio_a, usuario_gestor_a, empresa, numero, dh=DH_MARCO)
        _compra(escritorio_a, usuario_gestor_a, empresa, f"{numero}9", dh=DH_ABRIL)

    previa = previa_lida(empresa, *MARCO)
    confirmar_tudo(empresa, usuario_gestor_a, *MARCO, previa)

    for vinculo_de_abril in _compras_do_mes(empresa, *ABRIL):
        escrituracao = servico.criar_rascunho(vinculo_de_abril, usuario=usuario_gestor_a)
        ids = list(escrituracao.naturezas_dos_itens.values_list("item_id", flat=True))
        entradas.definir_natureza_de_entrada(
            escrituracao, N.ENTRADA_COMERCIALIZACAO, "1102", ids, usuario=usuario_gestor_a
        )
        servico.efetivar(escrituracao, usuario=usuario_gestor_a)

    resumo = _resumo_das_notas(empresa)
    do_lote = [r[1:] for r in resumo if not r[0].endswith("9")]
    individual = [r[1:] for r in resumo if r[0].endswith("9")]
    assert len(do_lote) == len(individual) == 2
    assert do_lote == individual
    assert do_lote == [(N.ENTRADA_COMERCIALIZACAO, "1102", do_lote[0][2])] * 2
    efetivadas = EscrituracaoNFe.objects.filter(empresa=empresa, tipo=ENTRADA, estado="efetivada")
    assert efetivadas.count() == 4
    assert all(esc.receita_bruta == 0 for esc in efetivadas)


def _compras_do_mes(empresa, ano, mes):
    """Vínculos de compra de abril (ainda não escriturados). As de março já estão no lote."""
    return [
        v
        for v in VinculoNFeEmpresa.objects.filter(
            empresa=empresa,
            papel=PapelNFe.DESTINATARIO,
            documento__dh_emissao__year=ano,
            documento__dh_emissao__month=mes,
        ).select_related("documento")
        if v.documento.numero.endswith("9")
    ]


def test_lote_de_compras_confirma_em_partes_sem_duplicar(escritorio_a, usuario_gestor_a, empresa):
    for numero in ("1701", "1702", "1703"):
        _compra(escritorio_a, usuario_gestor_a, empresa, numero)

    previa = previa_lida(empresa, *MARCO)
    progresso = lote.confirmar_lote(
        empresa, *MARCO, previa.assinatura, {}, usuario_gestor_a, limite=1
    )
    assert not progresso.terminou
    total = 1
    while not progresso.terminou:
        progresso = lote.confirmar_lote(
            empresa, None, None, None, None, usuario_gestor_a, limite=1, lote_id=progresso.lote_id
        )
        total += 1
        assert total < 10
    assert progresso.efetivadas_total == 3
    assert (
        EscrituracaoNFe.objects.filter(empresa=empresa, tipo=ENTRADA, estado="efetivada").count()
        == 3
    )
    assert lote.previa_do_lote(empresa, *MARCO).grupos == ()


def test_compra_efetivada_pelo_lote_nao_altera_receita_do_mes(
    escritorio_a, usuario_gestor_a, empresa
):
    _compra(escritorio_a, usuario_gestor_a, empresa, "1801")
    previa = previa_lida(empresa, *MARCO)
    confirmar_tudo(empresa, usuario_gestor_a, *MARCO, previa)

    conferencia = servico.conferencia_do_mes(empresa, *MARCO)
    assert conferencia.valor_bruto_por_cfop == {}
    assert all(linha["soma_na_receita"] == 0 for linha in conferencia.receita_por_natureza.values())


def test_assinatura_da_previa_inclui_o_cfop_de_entrada_do_grupo():
    """Mutante "assinatura do lote sem o CFOP de entrada": dois grupos iguais em tudo, exceto o CFOP
    de entrada, têm de ter assinaturas diferentes. Com regra, a fonte já distingue; sem regra, só o
    CFOP distingue (o caso que este teste prova)."""
    from apps.fiscal.escrituracao_nfe_lote import (
        AssinaturaDoItem,
        GrupoDoLote,
        ItemDoLote,
        NotaDoLote,
        _assinatura_da_previa,
    )

    def grupo(cfop_entrada):
        item = ItemDoLote(1, 1, "5102", "00", N.ENTRADA_COMERCIALIZACAO, "", cfop_entrada)
        nota = NotaDoLote(
            vinculo_id=10,
            documento_id=10,
            numero="1",
            serie="1",
            chave="x",
            dh_emissao=None,
            itens=(item,),
            receita_bruta=0,
            devolucao=0,
        )
        assinatura = AssinaturaDoItem("5102", "00", N.ENTRADA_COMERCIALIZACAO, "", cfop_entrada)
        return GrupoDoLote(
            chave="entrada-fixa",  # a chave do grupo é a mesma: só o CFOP de entrada muda
            tipo=ENTRADA,
            assinaturas=(assinatura,),
            notas=(nota,),
        )

    com_1102 = _assinatura_da_previa(1, 2026, 3, [grupo("1102")], [])
    com_1113 = _assinatura_da_previa(1, 2026, 3, [grupo("1113")], [])
    assert com_1102 != com_1113
    assert (
        AssinaturaDoItem("5102", "00", "x", "", "1102").id
        != AssinaturaDoItem("5102", "00", "x", "", "1113").id
    )
