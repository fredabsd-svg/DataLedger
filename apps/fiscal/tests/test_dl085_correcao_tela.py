"""DL-085, correção da auditoria rodada 1 (2026-10-09): tela do lote (A3, A9 e o redirecionamento).

- A3 (T7): a coluna "Devolução" da tabela de grupos mostra o valor do grupo de devolução.
- A9 (T8): cada caixa "incluir" tem um nome acessível próprio (CFOP, CST e natureza do grupo).
- A9 (Post/Redirect/Get): confirmar e continuar respondem com redirecionamento. O progresso aparece
  uma vez, no GET seguinte, e a recarga da página não reenvia o POST.

Dados sintéticos (`suporte_dl085`, `xml_nfe_dl081`). Os valores esperados estão escritos à mão.
"""

import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import DocumentoNFe, EscrituracaoNFe, ItemNFe, LoteEscrituracaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.suporte_dl085 import CFOP_REVENDA, nfce, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A, CNPJ_SEM_CADASTRO

ANO, MES = 2026, 3

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-tela-correcao-dl085")


@pytest.fixture
def posto(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Tela Correção DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _url(empresa, ano=ANO, mes=MES):
    return reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + f"?ano={ano}&mes={mes}"


def _post(client, empresa, dados, **kwargs):
    return client.post(reverse("fiscal_web:nfe_lote", args=[empresa.pk]), dados, **kwargs)


def _html(resposta):
    return resposta.content.decode("utf-8")


def _linhas(html):
    return re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)


def _dados_de_confirmacao(html):
    chaves = re.findall(r'<input type="hidden" name="grupo" value="([^"]+)"', html)
    dados = {
        "acao": "confirmar",
        "ano": ANO,
        "mes": MES,
        "assinatura": re.search(r'name="assinatura" value="([0-9a-f]{64})"', html).group(1),
        "grupo": chaves,
        "incluir": chaves,
    }
    for chave in chaves:
        dados[f"assinatura_{chave}"] = re.findall(
            rf'name="assinatura_{re.escape(chave)}" value="([^"]+)"', html
        )
        dados[f"escolha_{chave}"] = ""
    return dados


# ---------------------------------------------------------------------------
# A3 — devolução na tabela de grupos (T7)
# ---------------------------------------------------------------------------


def test_devolucao_de_40_aparece_na_coluna_devolucao_do_grupo(escritorio_a, gestor, posto, client):
    receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="1202", vprod="40.00", icms_xml=xml.icms(csosn="102"))],
            vnf="40.00",
            totais={"vProd": "40.00"},
            numero="5",
            tp_nf="0",
            fin_nfe="4",
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", CNPJ_SEM_CADASTRO),
        ),
    )
    client.force_login(gestor)
    assert _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES}).status_code == 302

    html = _html(client.get(_url(posto)))

    assert '<th scope="col">Devolução</th>' in html
    linha = next(texto for texto in _linhas(html) if "1202" in texto)
    assert '<td class="valor-monetario">40,00</td>' in linha
    assert "devolução de 40,00" in html


# ---------------------------------------------------------------------------
# A9 — nome acessível de cada caixa "incluir" (T8)
# ---------------------------------------------------------------------------


def test_cada_caixa_de_grupo_tem_nome_acessivel_proprio(escritorio_a, gestor, posto, client):
    for numero in (1, 2, 3):
        nfce(escritorio_a, gestor, numero=numero, valor="10.00")
    for numero in (4, 5):
        nfce(escritorio_a, gestor, numero=numero, valor="20.00", cfop=CFOP_REVENDA, csosn="102")
    client.force_login(gestor)
    _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES})

    html = _html(client.get(_url(posto)))

    nomes = re.findall(r'<input type="checkbox"[^>]*aria-label="([^"]+)"', html)
    assert len(nomes) == 2
    assert len(set(nomes)) == 2, "duas caixas com o mesmo nome acessível"
    assert any("CFOP 5656" in nome for nome in nomes)
    assert any(f"CFOP {CFOP_REVENDA}" in nome for nome in nomes)
    assert all("natureza" in nome and "CST ou CSOSN" in nome for nome in nomes)


# ---------------------------------------------------------------------------
# A9 — Post/Redirect/Get: o progresso aparece uma vez, e a recarga não reenvia o POST
# ---------------------------------------------------------------------------


def test_confirmar_redireciona_e_o_progresso_aparece_uma_vez(escritorio_a, gestor, posto, client):
    for numero in (1, 2, 3):
        nfce(escritorio_a, gestor, numero=numero, valor="10.00")
    client.force_login(gestor)
    _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES})
    html = _html(client.get(_url(posto)))

    resposta = _post(client, posto, _dados_de_confirmacao(html))

    assert resposta.status_code == 302
    assert resposta["Location"] == _url(posto)
    assert LoteEscrituracaoNFe.objects.filter(empresa=posto).count() == 1
    assert EscrituracaoNFe.objects.filter(empresa=posto).count() == 3

    primeiro_get = _html(client.get(resposta["Location"]))
    assert "Lote concluído" in primeiro_get
    assert "<strong>3</strong> efetivada(s)" in primeiro_get

    # A recarga (um GET novo) mostra a prévia, não reenvia nada: o progresso saiu da sessão.
    segundo_get = _html(client.get(resposta["Location"]))
    assert "Lote concluído" not in segundo_get
    assert "Nada a escriturar em 03/2026." in segundo_get
    assert LoteEscrituracaoNFe.objects.filter(empresa=posto).count() == 1
    assert EscrituracaoNFe.objects.filter(empresa=posto).count() == 3


def test_continuar_redireciona_com_o_progresso_da_parte(
    escritorio_a, gestor, posto, client, monkeypatch
):
    monkeypatch.setattr(lote, "LIMITE_PADRAO_DA_PARTE", 2)
    for numero in (1, 2, 3, 4):
        nfce(escritorio_a, gestor, numero=numero, valor="10.00")
    client.force_login(gestor)
    _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES})
    html = _html(client.get(_url(posto)))
    _post(client, posto, _dados_de_confirmacao(html))
    client.get(_url(posto))  # consome o progresso da confirmação
    lote_id = LoteEscrituracaoNFe.objects.get(empresa=posto).pk

    resposta = _post(
        client,
        posto,
        {"acao": "continuar", "ano": ANO, "mes": MES, "lote_id": lote_id},
    )

    assert resposta.status_code == 302
    html = _html(client.get(resposta["Location"]))
    assert "Lote concluído" in html
    assert "<strong>4</strong> efetivada(s)" in html
    assert EscrituracaoNFe.objects.filter(empresa=posto).count() == 4


# ---------------------------------------------------------------------------
# A2 — o motivo "natureza já escolhida" aparece com rótulo na tela
# ---------------------------------------------------------------------------


def test_natureza_ja_escolhida_aparece_na_tela_com_rotulo_e_motivo(
    escritorio_a, gestor, posto, client
):
    nfce(escritorio_a, gestor, numero=1, valor="100.00", cfop=CFOP_REVENDA, csosn="102")
    nfce(escritorio_a, gestor, numero=2, valor="50.00", cfop=CFOP_REVENDA, csosn="102")
    documento = DocumentoNFe.objects.get(numero="1")
    rascunho = servico_nfe.criar_rascunho(vinculo(documento, posto), usuario=gestor)
    servico_nfe.definir_natureza(
        rascunho,
        "bonificacao",
        [item.pk for item in ItemNFe.objects.filter(documento=documento)],
        usuario=gestor,
    )
    client.force_login(gestor)
    _post(client, posto, {"acao": "ler", "ano": ANO, "mes": MES})

    html = _html(client.get(_url(posto)))

    assert "Natureza já escolhida no rascunho" in html
    assert "natureza_escolhida" not in html
    assert lote.MENSAGEM_NATUREZA_ESCOLHIDA in html
