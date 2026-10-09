"""DL-082, correção da rodada 1 (A2, A8 e A9): telas e API da escrituração e do pré-DAS.

Dados sintéticos (`suporte_dl082`). Os textos e valores esperados são escritos à mão. A tela é
conferida pelo que o contador lê (HTML sem entidades).
"""

import html as html_lib
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal.models import ItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.models import SegmentoDevolucao as SD
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

ANO, MES = 2026, 6

pytestmark = pytest.mark.django_db


@pytest.fixture
def loja(escritorio_a):
    return cenario(
        Empresa.objects.create(
            escritorio=escritorio_a, razao_social="Telas DL082 Ltda", cnpj=CNPJ_EMITENTE_A
        )
    )


def _texto(resposta):
    return html_lib.unescape(resposta.content.decode("utf-8"))


def _url_escriturar(empresa, documento):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])


def _rascunho_de_devolucao(empresa, usuario, devolucao):
    """Rascunho com a natureza de devolução de venda. Só assim o seletor de segmento aparece: a
    tela oferece o segmento quando o item já é devolução (`_marcas_do_item_na_tela`)."""
    esc = servico_nfe.criar_rascunho(vinculo(devolucao, empresa), usuario=usuario)
    item = ItemNFe.objects.get(documento=devolucao)
    servico_nfe.definir_natureza(esc, N.DEVOLUCAO_VENDA, [item.pk], usuario=usuario)
    return esc


# ---------------------------------------------------------------------------
# A9: o seletor de segmento oferece só o que o domínio aceita para o CFOP do item
# ---------------------------------------------------------------------------


def test_seletor_de_segmento_de_devolucao_de_exportacao_so_oferece_exportacao(
    client, escritorio_a, usuario_gestor_a, loja
):
    """Devolução 1.503 em rascunho. Esperado (à mão): o seletor oferece só os dois segmentos de
    exportação. Antes: oferecia os 10, e a escolha de um interno dava 400 depois do envio."""
    janela(loja, usuario_gestor_a, ANO, MES, [25000] * 12)
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=601,
        itens=[{"cfop": "1503", "vprod": "10000.00"}],
        devolucao=True,
    )
    _rascunho_de_devolucao(loja, usuario_gestor_a, devolucao)
    client.force_login(usuario_gestor_a)

    html = _texto(client.get(_url_escriturar(loja, devolucao)))

    assert 'value="revenda_exportacao"' in html
    assert 'value="producao_exportacao"' in html
    assert 'value="producao"' not in html
    assert 'value="revenda"' not in html


def test_seletor_de_segmento_de_devolucao_interna_nao_oferece_exportacao(
    client, escritorio_a, usuario_gestor_a, loja
):
    """Devolução 1.202 (interna) em rascunho: o seletor não oferece os segmentos de exportação."""
    janela(loja, usuario_gestor_a, ANO, MES, [25000] * 12)
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=602,
        itens=[{"cfop": "1202", "vprod": "10000.00"}],
        devolucao=True,
    )
    _rascunho_de_devolucao(loja, usuario_gestor_a, devolucao)
    client.force_login(usuario_gestor_a)

    html = _texto(client.get(_url_escriturar(loja, devolucao)))

    assert 'value="revenda"' in html
    assert 'value="producao"' in html
    assert 'value="revenda_exportacao"' not in html
    assert 'value="producao_exportacao"' not in html


# ---------------------------------------------------------------------------
# A8: ST com monofásico tem a chave e o rótulo próprios, na memória, na API e na tela
# ---------------------------------------------------------------------------


def test_st_com_monofasico_tem_chave_propria_na_memoria(escritorio_a, usuario_gestor_a, loja):
    """Venda ST de 20.000 (5405, natureza revenda_st_substituido) com a marca de monofásico.
    Esperado (à mão): st_monofasico 20.000,00; sujeita_st 0,00. Antes: 20.000,00 em sujeita_st."""
    janela(loja, usuario_gestor_a, ANO, MES, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=603,
        itens=[{"cfop": "5405", "vprod": "20000.00", "csosn": "500"}],
    )
    esc = escriturar(loja, usuario_gestor_a, venda, {1: N.REVENDA_ST_SUBSTITUIDO}, marcas=(1,))

    memoria = servico_nfe.segregacao_da_escrituracao(esc)

    assert memoria["st_monofasico"] == Decimal("20000.00")
    assert memoria["sujeita_st"] == Decimal("0.00")
    assert memoria["monofasico"] == Decimal("0.00")


def test_st_com_monofasico_aparece_com_rotulo_proprio_na_tela_e_na_api(
    client, escritorio_a, usuario_gestor_a, loja
):
    janela(loja, usuario_gestor_a, ANO, MES, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=604,
        itens=[{"cfop": "5405", "vprod": "20000.00", "csosn": "500"}],
    )
    esc = escriturar(loja, usuario_gestor_a, venda, {1: N.REVENDA_ST_SUBSTITUIDO}, marcas=(1,))
    client.force_login(usuario_gestor_a)

    html = _texto(client.get(_url_escriturar(loja, venda)))
    assert "ST e monofásico (natureza 3 com marca de monofásico)" in html

    api = client.get(reverse("fiscal_api:nfe_escrituracao_detalhe", args=[loja.pk, esc.pk]))
    assert api.status_code == 200
    segregacao = api.json()["segregacao"]
    assert Decimal(segregacao["st_monofasico"]) == Decimal("20000.00")
    assert Decimal(segregacao["sujeita_st"]) == Decimal("0.00")


# ---------------------------------------------------------------------------
# A2 e A5: a recusa de nota efetivada chega à tela com o texto nomeado, sem erro de página
# ---------------------------------------------------------------------------


def test_devolucao_de_combustivel_recusa_chega_a_tela_com_o_texto_nomeado(
    client, escritorio_a, usuario_gestor_a, loja
):
    """Caso 1 da auditoria, pela tela. Esperado: a página do pré-DAS mostra a recusa com o CFOP e a
    frase de que a nota já está efetivada. Não mostra o total."""
    janela(loja, usuario_gestor_a, ANO, MES, [50000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=605,
        itens=[{"cfop": "5102", "vprod": "40000.00"}],
    )
    escriturar(loja, usuario_gestor_a, venda, {1: N.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        loja,
        numero=606,
        itens=[{"cfop": "1661", "vprod": "10000.00", "ncm": "27101259"}],
        devolucao=True,
    )
    escriturar(loja, usuario_gestor_a, devolucao, {1: N.DEVOLUCAO_VENDA}, segmentos={1: SD.REVENDA})
    confirmar_pa(loja, usuario_gestor_a, ANO, MES)
    client.force_login(usuario_gestor_a)

    resposta = client.get(
        reverse("fiscal_web:pre_das"), {"empresa": loja.pk, "ano": ANO, "mes": MES}
    )
    html = _texto(resposta)

    assert resposta.status_code == 200
    assert "Devolução de venda de combustível ou lubrificante em 06/2026" in html
    assert "CFOP 1661" in html
    assert "a nota já está efetivada" in html
    assert "Total do pré-DAS" not in html
