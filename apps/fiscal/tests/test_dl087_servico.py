"""DL-087 (frente A), serviço: a regra muda a SUGESTÃO das notas a escriturar, da prévia do lote, da
conferência e da fila; nunca muda escrituração efetivada nem natureza já escolhida em rascunho;
a origem da natureza confirmada é gravada; a confirmação com prévia antiga recebe 409; e a regra
criada pela fila esvazia o grupo. Critérios 4, 6 e o ajuste 6 e 7 do arquiteto.

Dados sintéticos (NFC-e pela recepção real). Mês de teste: março de 2026.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from apps.fiscal import classificacao as cl
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    ItemNFe,
    NaturezaItemNFe,
    OrigemNaturezaItemNFe,
)
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, nfce, previa_lida
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3
FUSO = ZoneInfo("America/Sao_Paulo")
CFOP_SEM_SINAL = "5949"  # sem sinal na sugestão embutida: vai para a fila
NCM_CERVEJA = "22030000"


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-servico-dl087")


@pytest.fixture
def empresa(escritorio_a):
    from apps.empresas.models import Empresa

    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Servico DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _origem(linha) -> OrigemNaturezaItemNFe | None:
    """A origem gravada da natureza confirmada, ou None (linha anterior à DL-087)."""
    return OrigemNaturezaItemNFe.objects.filter(natureza_item=linha).first()


def _ler(empresa):
    """Lê o mês em partes, como a tela faz antes da fila, da conferência e da prévia."""
    leitura = lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    assert leitura.terminou and not leitura.falhas_nesta_chamada, leitura


def _notas_sem_sinal(escritorio, usuario, quantidade, inicio=1):
    return [
        nfce(escritorio, usuario, numero=n, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA)
        for n in range(inicio, inicio + quantidade)
    ]


def _regra_da_empresa(escritorio, usuario, empresa, **campos):
    base = {
        "tipo": "saida_propria",
        "cfop": CFOP_SEM_SINAL,
        "natureza": "revenda",
        "vigencia_inicio": date(ANO, MES, 1),
    }
    base.update(campos)
    return cl.criar_regra(
        escritorio=escritorio,
        empresa=empresa,
        dados=cl.DadosDaRegra(**base),
        usuario=usuario,
    )


# ---------------------------------------------------------------------------
# Critério 4: a regra muda a sugestão e a prévia; a confirmação antiga recebe 409
# ---------------------------------------------------------------------------


def test_regra_muda_a_previa_do_lote_e_a_assinatura_e_a_fonte_aparece(
    escritorio_a, gestor, empresa
):
    _notas_sem_sinal(escritorio_a, gestor, 2)
    _ler(empresa)
    antes = previa_lida(empresa, ANO, MES)
    assert antes.grupos == ()
    assert len(antes.fora) == 2  # sem sugestão: fora do lote, com o motivo

    _regra_da_empresa(escritorio_a, gestor, empresa)
    depois = lote.previa_do_lote(empresa, ANO, MES)

    assert depois.assinatura != antes.assinatura
    (grupo,) = depois.grupos
    assert len(grupo.notas) == 2
    (assinatura,) = grupo.assinaturas
    assert assinatura.natureza == "revenda"
    assert assinatura.fonte.startswith("regra:")
    assert assinatura.id.endswith(assinatura.fonte)


def test_confirmacao_com_previa_antiga_recebe_409_depois_de_criar_regra(
    escritorio_a, gestor, empresa
):
    _notas_sem_sinal(escritorio_a, gestor, 1)
    previa_antiga = previa_lida(empresa, ANO, MES)
    _regra_da_empresa(escritorio_a, gestor, empresa)

    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(empresa, ANO, MES, previa_antiga.assinatura, {}, gestor, limite=10)
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_nota_confirmada_falha_com_desvio_quando_regra_e_criada_depois_da_confirmacao(
    escritorio_a, gestor, empresa
):
    """Duas notas com sugestão embutida (CFOP 5102, CSOSN 102: revenda). A primeira parte (limite 1)
    efetiva uma. Entre as partes, uma regra muda a sugestão da segunda: ela falha com o desvio, e
    nada é efetivado com a sugestão antiga."""
    from apps.fiscal.models import LoteEscrituracaoNFe

    for numero in (1, 2):
        nfce(escritorio_a, gestor, numero=numero, cfop="5102", csosn="102", ncm=NCM_CERVEJA)
    _ler(empresa)
    previa = lote.previa_do_lote(empresa, ANO, MES)
    primeira = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    assert primeira.efetivadas_total == 1 and not primeira.terminou

    _regra_da_empresa(escritorio_a, gestor, empresa, cfop="5102", natureza="producao_propria")
    progresso = lote.confirmar_lote(
        empresa,
        None,
        None,
        None,
        None,
        gestor,
        limite=10,
        lote_id=LoteEscrituracaoNFe.objects.get(empresa=empresa).pk,
    )

    assert progresso.falhas_total == 1
    assert progresso.efetivadas_total == 1
    assert "mudou desde a confirmação" in progresso.falhas_nesta_chamada[0].motivo


def test_regra_nao_muda_nota_efetivada_nem_a_natureza_gravada(escritorio_a, gestor, empresa):
    documento = nfce(
        escritorio_a, gestor, numero=1, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA
    )
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao, "producao_propria", ids, usuario=gestor)
    servico.efetivar(escrituracao, usuario=gestor)

    _regra_da_empresa(escritorio_a, gestor, empresa, natureza="revenda")

    efetivada = NaturezaItemNFe.objects.get(escrituracao=escrituracao)
    assert efetivada.natureza == "producao_propria"
    assert _origem(efetivada).origem == "manual"
    assert EscrituracaoNFe.objects.get(pk=escrituracao.pk).estado == "efetivada"


def test_regra_nao_muda_natureza_escolhida_em_rascunho_e_a_previa_recusa_a_nota(
    escritorio_a, gestor, empresa
):
    documento = nfce(
        escritorio_a, gestor, numero=1, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA
    )
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao, "producao_propria", ids, usuario=gestor)

    _regra_da_empresa(escritorio_a, gestor, empresa, natureza="revenda")

    assert NaturezaItemNFe.objects.get(escrituracao=escrituracao).natureza == "producao_propria"
    previa = lote.previa_do_lote(empresa, ANO, MES)
    nota = [f for f in previa.fora if f.documento_id == documento.pk]
    assert nota and nota[0].codigo == lote.CODIGO_NATUREZA_ESCOLHIDA


def test_rascunho_sem_natureza_ganha_a_sugestao_da_regra(escritorio_a, gestor, empresa):
    documento = nfce(
        escritorio_a, gestor, numero=1, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA
    )
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    _regra_da_empresa(escritorio_a, gestor, empresa, natureza="revenda")

    (linha,) = NaturezaItemNFe.objects.filter(escrituracao=escrituracao)
    assert linha.natureza == ""  # a regra só sugere; nada é gravado sozinho
    assert servico.conferencia_do_mes(empresa, ANO, MES).itens_sem_sugestao == 0


def test_conferencia_do_mes_conta_os_itens_sem_sugestao_com_e_sem_regra(
    escritorio_a, gestor, empresa
):
    _notas_sem_sinal(escritorio_a, gestor, 3)
    _ler(empresa)
    assert servico.conferencia_do_mes(empresa, ANO, MES).itens_sem_sugestao == 3
    _regra_da_empresa(escritorio_a, gestor, empresa)
    assert servico.conferencia_do_mes(empresa, ANO, MES).itens_sem_sugestao == 0


# ---------------------------------------------------------------------------
# Ajuste 6: a origem da natureza CONFIRMADA é gravada (regra FK, produto, manual)
# ---------------------------------------------------------------------------


def test_origem_da_natureza_confirmada_pela_regra_fica_gravada(escritorio_a, gestor, empresa):
    documento = nfce(
        escritorio_a, gestor, numero=1, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA
    )
    regra = _regra_da_empresa(escritorio_a, gestor, empresa, natureza="revenda")
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))

    servico.definir_natureza(escrituracao, "revenda", ids, usuario=gestor)

    linha = NaturezaItemNFe.objects.get(escrituracao=escrituracao)
    assert _origem(linha).origem == "regra"
    assert _origem(linha).regra_classificacao_id == regra.pk
    assert regra.itens_confirmados.count() == 1


def test_origem_produto_e_manual_sao_gravadas_sem_regra(escritorio_a, gestor, empresa):
    produto = nfce(escritorio_a, gestor, numero=1, cfop="5102", csosn="102", ncm=NCM_CERVEJA)
    escrituracao_p = servico.criar_rascunho(vinculo(produto, empresa), usuario=gestor)
    ids_p = list(ItemNFe.objects.filter(documento=produto).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao_p, "revenda", ids_p, usuario=gestor)
    assert _origem(NaturezaItemNFe.objects.get(escrituracao=escrituracao_p)).origem == "produto"

    manual = nfce(escritorio_a, gestor, numero=2, cfop="5102", csosn="102", ncm=NCM_CERVEJA)
    escrituracao_m = servico.criar_rascunho(vinculo(manual, empresa), usuario=gestor)
    ids_m = list(ItemNFe.objects.filter(documento=manual).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao_m, "producao_propria", ids_m, usuario=gestor)
    origem = _origem(NaturezaItemNFe.objects.get(escrituracao=escrituracao_m))
    assert origem.origem == "manual"
    assert origem.regra_classificacao_id is None


def test_lote_efetivado_grava_a_origem_da_regra(escritorio_a, gestor, empresa):
    _notas_sem_sinal(escritorio_a, gestor, 2)
    regra = _regra_da_empresa(escritorio_a, gestor, empresa, natureza="revenda")
    previa = previa_lida(empresa, ANO, MES)
    progresso = confirmar_tudo(empresa, gestor, ANO, MES, previa)
    assert progresso.efetivadas_total == 2
    origens = set(OrigemNaturezaItemNFe.objects.values_list("origem", flat=True))
    assert origens == {"regra"}
    assert regra.itens_confirmados.count() == 2


def test_linhas_efetivadas_antes_da_dl087_ficam_com_origem_nula(escritorio_a, gestor, empresa):
    """Ajuste 6: nada de reescrita. Uma linha sem origem (anterior à DL-087) continua válida."""
    documento = nfce(escritorio_a, gestor, numero=1, cfop="5102", csosn="102", ncm=NCM_CERVEJA)
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=escrituracao).update(natureza="revenda")
    assert _origem(NaturezaItemNFe.objects.get(escrituracao=escrituracao)) is None


# ---------------------------------------------------------------------------
# Critério 6: fila agrupa; criar a regra pela fila esvazia o grupo
# ---------------------------------------------------------------------------


def test_fila_agrupa_notas_iguais_e_traz_os_criterios_do_grupo(escritorio_a, gestor, empresa):
    _notas_sem_sinal(escritorio_a, gestor, 3)
    _ler(empresa)
    fila = cl.fila_a_classificar(empresa, ANO, MES)
    (grupo,) = fila.grupos
    assert grupo.notas == 3 and grupo.itens == 3
    assert grupo.cfop == CFOP_SEM_SINAL and grupo.ncm == NCM_CERVEJA
    assert grupo.criterios_da_regra == {
        "tipo": "saida_propria",
        "cfop": CFOP_SEM_SINAL,
        "ncm": NCM_CERVEJA,
        "ncm_modo": "exato",
        "cst_csosn": "102",
        "id_dest": "1",
        "vigencia_inicio": "2026-03-01",
    }
    assert fila.quantidade_notas == 3 and fila.quantidade_itens == 3


def test_criar_regra_a_partir_do_grupo_esvazia_o_grupo(escritorio_a, gestor, empresa):
    _notas_sem_sinal(escritorio_a, gestor, 2)
    _ler(empresa)
    grupo = cl.fila_a_classificar(empresa, ANO, MES).grupos[0]
    criterios = grupo.criterios_da_regra
    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=empresa,
        dados=cl.DadosDaRegra(
            tipo=criterios["tipo"],
            cfop=criterios["cfop"],
            natureza="revenda",
            vigencia_inicio=date.fromisoformat(criterios["vigencia_inicio"]),
            ncm=criterios["ncm"],
            ncm_modo=criterios["ncm_modo"],
            cst_csosn=criterios["cst_csosn"],
            id_dest=criterios["id_dest"],
        ),
        usuario=gestor,
    )
    assert cl.fila_a_classificar(empresa, ANO, MES).grupos == ()


def test_fila_nao_lista_item_de_rascunho_com_natureza_escolhida(escritorio_a, gestor, empresa):
    documento = nfce(
        escritorio_a, gestor, numero=1, cfop=CFOP_SEM_SINAL, csosn="102", ncm=NCM_CERVEJA
    )
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao, "revenda", ids, usuario=gestor)
    assert cl.fila_a_classificar(empresa, ANO, MES).grupos == ()


def test_conflito_real_entre_regras_do_mesmo_escopo_vai_para_a_fila_com_as_duas_nomeadas(
    escritorio_a, gestor, empresa
):
    """Conflito REAL no banco, depois da revogação (A1).

    Uma regra revogada não disputa mais nota nenhuma, então o conflito só sobra entre regras ATIVAS
    do mesmo escopo e mesma especificidade, com critérios distintos que casam o MESMO item. Aqui: a
    nota traz CSOSN 102 e CST 60 (os dois campos), e as regras pedem um e outro, com naturezas
    diferentes. Sem padrão silencioso: a nota vai para a fila, com as duas regras nomeadas.
    """
    from apps.fiscal.tests.suporte_dl085 import nfce as nfce_por_data

    nfce_por_data(
        escritorio_a,
        gestor,
        numero=1,
        cfop=CFOP_SEM_SINAL,
        csosn="102",
        ncm=NCM_CERVEJA,
        dh_emi="2026-03-15T10:00:00-03:00",
    )
    _ler(empresa)
    # O item passa a ter também CST 60. Nota em rascunho: o gatilho de item não recusa.
    ItemNFe.objects.filter(cfop=CFOP_SEM_SINAL).update(cst="60")
    revenda = cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo="saida_propria",
            cfop=CFOP_SEM_SINAL,
            natureza="revenda",
            vigencia_inicio=date(ANO, 3, 1),
            cst_csosn="102",
        ),
        usuario=gestor,
    )
    producao = cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo="saida_propria",
            cfop=CFOP_SEM_SINAL,
            natureza="producao_propria",
            vigencia_inicio=date(ANO, 3, 1),
            cst_csosn="60",
        ),
        usuario=gestor,
    )
    fila = cl.fila_a_classificar(empresa, ANO, MES)
    (grupo,) = fila.grupos
    assert grupo.situacao == "conflito"
    assert f"regra n.º {revenda.pk}" in grupo.motivo
    assert f"regra n.º {producao.pk}" in grupo.motivo


def test_fila_conta_as_notas_sem_leitura_e_marca_o_mes_confirmado(escritorio_a, gestor, empresa):
    from apps.fiscal import receita

    _notas_sem_sinal(escritorio_a, gestor, 1)
    antes = cl.fila_a_classificar(empresa, ANO, MES)
    assert antes.notas_sem_leitura == 1 and antes.grupos == ()
    _ler(empresa)
    depois = cl.fila_a_classificar(empresa, ANO, MES)
    assert depois.notas_sem_leitura == 0 and len(depois.grupos) == 1
    assert depois.mes_confirmado is False and depois.aviso_do_mes == ""
    assert receita.confirmacao_do_mes(empresa, ANO, MES) is None


def test_previa_de_impacto_nao_grava_e_conta_grupos(escritorio_a, gestor, empresa):
    from apps.fiscal.models import RegraClassificacaoNFe

    _notas_sem_sinal(escritorio_a, gestor, 4)
    _ler(empresa)
    antes_regras = RegraClassificacaoNFe.objects.count()
    previa = cl.previa_de_impacto(
        empresa,
        ANO,
        MES,
        cl.DadosDaRegra(
            tipo="saida_propria",
            cfop=CFOP_SEM_SINAL,
            natureza="revenda",
            vigencia_inicio=date(ANO, MES, 1),
        ),
        cl.ESCOPO_EMPRESA,
    )
    assert previa.itens_a_escriturar == 4
    assert previa.itens_que_saem_da_fila == 4
    assert previa.grupos_afetados == 1
    assert previa.notas_afetadas == 4
    assert RegraClassificacaoNFe.objects.count() == antes_regras == 0
    assert cl.fila_a_classificar(empresa, ANO, MES).quantidade_itens == 4


def test_mes_confirmado_marca_a_fila_com_o_aviso_e_nao_bloqueia_os_grupos(
    escritorio_a, gestor, empresa
):
    """Ajuste 8: o código não bloqueia escrituração em mês confirmado (a efetivação reabre e marca
    a retificar, DL-074). A fila sinaliza o mês com o aviso e MANTÉM os grupos acionáveis."""
    from decimal import Decimal

    from apps.fiscal.models import ConfirmacaoReceitaMensal, EstadoConfirmacaoMes

    _notas_sem_sinal(escritorio_a, gestor, 2)
    _ler(empresa)
    ConfirmacaoReceitaMensal.objects.create(
        empresa=empresa,
        ano=ANO,
        mes=MES,
        estado=EstadoConfirmacaoMes.CONFIRMADA,
        valor_confirmado_interno=Decimal("0.00"),
        valor_confirmado_externo=Decimal("0.00"),
        confirmada_em=datetime(2026, 4, 2, 10, 0, tzinfo=FUSO),
        confirmada_por=gestor,
    )
    fila = cl.fila_a_classificar(empresa, ANO, MES)
    assert fila.mes_confirmado is True
    assert "a retificar" in fila.aviso_do_mes
    assert len(fila.grupos) == 1 and fila.grupos[0].criavel is True
