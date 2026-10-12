"""DL-084, frente B1: o padrão de combustível ligado aos caminhos de sugestão (RC-173, item 3).

A regra mora em `sugerir_natureza_com_padrao` e a especificação é `test_dl084_parametros.py`
(PE-85.1): o padrão decide SÓ quando a sugestão base não decidiu (natureza `None`), o CFOP não é de
combustível e o NCM é de combustível. Aqui está a LIGAÇÃO: conferência do mês (rascunho), prévia e
confirmação do lote, e a API de escrituração passam a chamar a variante com padrão.

Cada teste de caminho derruba a mutação do critério 9 do plano: trocar a chamada de
`sugerir_natureza_com_padrao` de volta para `sugerir_natureza_item` naquele caminho reprova o teste
que o nomeia. Os casos sintéticos usam CFOP 5949 (não separa consumo de revenda) e NCM 2710.12.59
(óleos leves, lista `NCM_COMBUSTIVEL`), as mesmas amostras da especificação.

O lote consulta o padrão da empresa UMA vez por chamada e o repassa aos itens (BL-698: o orçamento
de tempo do lote não paga consulta por item); o teste de consultas prende esse número.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal import itens_nfe, presumido
from apps.fiscal.models import EscrituracaoNFe, EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import confirmar_tudo, nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3

# CFOP de saída genérico: não diz consumo nem revenda (5.949, "outras saídas"). Só o padrão da
# empresa pode decidir, e só com NCM de combustível.
CFOP_SEM_DECISAO = "5949"
CSOSN_SEM_SINAL = "102"
NCM_DE_COMBUSTIVEL = "27101259"  # 2710.12.59, óleos leves (NCM_COMBUSTIVEL)
NCM_COMUM = "22030000"  # 2203.00.00, cerveja de malte: item de conveniência, não combustível


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-ligacao-dl084")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Ligação DL084 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _definir_padrao(empresa, usuario, padrao: str):
    """Grava o padrão de combustível pelo serviço real (com trilha), como a tela faz."""
    return presumido.definir_parametros(empresa, {"padrao_combustivel": padrao}, usuario)


def _nota(
    escritorio, usuario, numero: int, quantidade_de_itens: int = 1, *, ncm=NCM_DE_COMBUSTIVEL
):
    """NFC-e cujo CFOP não decide a natureza: só o padrão da empresa pode sugerir (ou não)."""
    dets = [
        xml.det(
            n,
            cfop=CFOP_SEM_DECISAO,
            vprod="100.00",
            ncm=ncm,
            icms_xml=xml.icms(csosn=CSOSN_SEM_SINAL),
        )
        for n in range(1, quantidade_de_itens + 1)
    ]
    total = f"{100 * quantidade_de_itens}.00"
    return nfce(escritorio, usuario, numero=numero, dets=dets, vnf=total, totais={"vProd": total})


def _consultas_de_parametros(contexto) -> int:
    """Quantas consultas do contexto tocaram a tabela dos parâmetros do Presumido."""
    return sum(1 for q in contexto.captured_queries if "parametros" in q["sql"].lower())


# ---------------------------------------------------------------------------
# Caminho 1 — conferência do mês, sobre rascunho e nota a escriturar
# (`escrituracao_nfe._itens_sem_sugestao_do_mes`)
# ---------------------------------------------------------------------------


def test_conferencia_do_mes_respeita_o_padrao_quando_o_cfop_nao_decide(
    escritorio_a, empresa, gestor
):
    """MUTAÇÃO (critério 9): voltar `_itens_sem_sugestao_do_mes` para `sugerir_natureza_item`
    derruba este teste — os dois itens voltam a contar como "sem sugestão"."""
    _definir_padrao(empresa, gestor, "posto")
    com_rascunho = _nota(escritorio_a, gestor, numero=1)
    servico.criar_rascunho(vinculo(com_rascunho, empresa), usuario=gestor)
    a_escrever = _nota(escritorio_a, gestor, numero=2)
    itens_nfe.ler_itens(a_escrever)

    conferencia = servico.conferencia_do_mes(empresa, ANO, MES)

    assert conferencia.pendentes == 2
    assert conferencia.itens_sem_sugestao == 0


@pytest.mark.parametrize("padrao", ["", "distribuidora"])
def test_conferencia_sem_padrao_ou_com_distribuidora_conta_o_item_como_estava(
    escritorio_a, empresa, gestor, padrao
):
    """Regressão: sem padrão, ou com distribuidora (quem decide é o item), nada muda em relação a
    hoje — o item continua sem sugestão e a conferência o conta."""
    if padrao:
        _definir_padrao(empresa, gestor, padrao)
    documento = _nota(escritorio_a, gestor, numero=1)
    servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)

    assert servico.conferencia_do_mes(empresa, ANO, MES).itens_sem_sugestao == 1


# ---------------------------------------------------------------------------
# Caminho 2 — prévia do lote (`escrituracao_nfe_lote._calcular`)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("padrao", ["posto", "trr"])
def test_previa_do_lote_respeita_o_padrao_quando_o_cfop_nao_decide(
    escritorio_a, empresa, gestor, padrao
):
    """MUTAÇÃO (critério 9): voltar `_calcular` para `sugerir_natureza_item` derruba este teste —
    a nota cai em `fora` com "sem sugestão" em vez de entrar no grupo com a natureza do padrão."""
    _definir_padrao(empresa, gestor, padrao)
    _nota(escritorio_a, gestor, numero=1)

    previa = previa_lida(empresa, ANO, MES)

    assert previa.fora == ()
    (grupo,) = previa.grupos
    (assinatura,) = grupo.assinaturas
    assert assinatura.natureza == "combustivel"


@pytest.mark.parametrize("padrao", ["", "distribuidora"])
def test_previa_sem_padrao_ou_com_distribuidora_deixa_a_nota_fora_como_estava(
    escritorio_a, empresa, gestor, padrao
):
    """Regressão: sem padrão, ou com distribuidora, a nota continua fora do lote com o motivo de
    sempre — o padrão não decide nada por conta própria."""
    if padrao:
        _definir_padrao(empresa, gestor, padrao)
    _nota(escritorio_a, gestor, numero=1)

    previa = previa_lida(empresa, ANO, MES)

    assert previa.grupos == ()
    (recusa,) = previa.fora
    assert recusa.codigo == lote.CODIGO_SEM_SUGESTAO


def test_item_comum_de_posto_nao_recebe_o_padrao_de_combustivel(escritorio_a, empresa, gestor):
    """Regressão (loja de conveniência): o NCM não é de combustível, e o padrão "posto" não decide
    o item comum — a nota segue fora do lote, como hoje."""
    _definir_padrao(empresa, gestor, "posto")
    _nota(escritorio_a, gestor, numero=1, ncm=NCM_COMUM)

    previa = previa_lida(empresa, ANO, MES)

    assert previa.grupos == ()
    (recusa,) = previa.fora
    assert recusa.codigo == lote.CODIGO_SEM_SUGESTAO


# ---------------------------------------------------------------------------
# Caminho 2b — confirmação do lote (`escrituracao_nfe_lote._desvio_desde_a_confirmacao`)
# ---------------------------------------------------------------------------


def test_confirmacao_do_lote_efetiva_com_a_natureza_do_padrao(escritorio_a, empresa, gestor):
    """MUTAÇÃO (critério 9): voltar `_desvio_desde_a_confirmacao` para `sugerir_natureza_item`
    derruba este teste — a sugestão de hoje (None) deixa de bater com a fixada ("combustivel"), a
    nota falha como desvio e nada é efetivado."""
    _definir_padrao(empresa, gestor, "posto")
    _nota(escritorio_a, gestor, numero=1)
    previa = previa_lida(empresa, ANO, MES)

    progresso = confirmar_tudo(empresa, gestor, ANO, MES, previa)

    assert progresso.terminou and progresso.falhas_total == 0
    escrituracao = EscrituracaoNFe.objects.get(empresa=empresa)
    assert escrituracao.estado == EstadoEscrituracao.EFETIVADA
    naturezas = NaturezaItemNFe.objects.filter(escrituracao=escrituracao)
    assert [n.natureza for n in naturezas] == ["combustivel"]


# ---------------------------------------------------------------------------
# Caminho 3 — API de escrituração (`api_escrituracao_nfe.EscrituracaoNFeDetalheView`)
# ---------------------------------------------------------------------------


def _url_detalhe(empresa, escrituracao):
    return reverse("fiscal_api:nfe_escrituracao_detalhe", args=[empresa.pk, escrituracao.pk])


def test_api_de_escrituracao_sugere_pelo_padrao_quando_o_cfop_nao_decide(
    client, escritorio_a, empresa, gestor
):
    """MUTAÇÃO (critério 9): voltar o detalhe para `sugerir_natureza_item` derruba este teste — a
    API devolve sugestão nula em vez da natureza decidida pelo padrão."""
    _definir_padrao(empresa, gestor, "posto")
    documento = _nota(escritorio_a, gestor, numero=1)
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    client.force_login(gestor)

    detalhe = client.get(_url_detalhe(empresa, escrituracao)).json()

    (item,) = detalhe["itens"]
    assert item["sugestao"]["natureza"] == "combustivel"
    assert "padrão de combustível" in item["sugestao"]["motivo"]


@pytest.mark.parametrize("padrao", ["", "distribuidora"])
def test_api_sem_padrao_ou_com_distribuidora_nao_muda_a_sugestao(
    client, escritorio_a, empresa, gestor, padrao
):
    """Regressão: sem padrão, ou com distribuidora, a API devolve a sugestão de sempre (nenhuma)."""
    if padrao:
        _definir_padrao(empresa, gestor, padrao)
    documento = _nota(escritorio_a, gestor, numero=1)
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    client.force_login(gestor)

    detalhe = client.get(_url_detalhe(empresa, escrituracao)).json()

    (item,) = detalhe["itens"]
    assert item["sugestao"]["natureza"] is None


# ---------------------------------------------------------------------------
# Consultas: o lote não consulta o padrão por item (BL-698)
# ---------------------------------------------------------------------------


def test_o_lote_nao_consulta_o_padrao_por_item(escritorio_a, empresa, gestor):
    """A prévia consulta o padrão UMA vez por chamada, com 6 itens em jogo; a confirmação consulta
    uma vez por chamada de `_processar_nota` — a nota de 4 itens paga 1 consulta do padrão, não 4.
    Consulta por item (6 e 5, respectivamente) reprova aqui e estoura o orçamento do lote."""
    _definir_padrao(empresa, gestor, "posto")
    _nota(escritorio_a, gestor, numero=1, quantidade_de_itens=1)
    _nota(escritorio_a, gestor, numero=2, quantidade_de_itens=4)
    lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_MAXIMO_DA_LEITURA)

    with CaptureQueriesContext(connection) as da_previa:
        previa = lote.previa_do_lote(empresa, ANO, MES)
    assert _consultas_de_parametros(da_previa) == 1, (
        "o padrão é lido uma vez na prévia, não por item"
    )

    with CaptureQueriesContext(connection) as da_parte:
        lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=10)
    # 1 da prévia que grava o lote + 1 por nota processada (2 notas, 5 itens): nunca por item.
    assert _consultas_de_parametros(da_parte) == 3
