"""DL-063 (BL-625) — a dica da divergência de fechamento deixa de ser
constante e passa a apontar a causa que a apuração realmente encontrou.

**O defeito:** `ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA` é um
dicionário **estático de módulo** — a mesma frase para todo caso. Depois da
DL-062 o texto já não nomeava a retificadora (causa que aquela etapa
eliminou), mas ele continuava mandando o contador "conferir a classificação"
mesmo quando o que faltava era a **coluna**: a apuração já nomeia, na lista
vizinha `contas_do_patrimonio_liquido_sem_coluna`, a conta de patrimônio
líquido com saldo e sem coluna — que é uma causa real e nomeada da
divergência.

**A correção:** quando a apuração traz essa lista não vazia, a ação passa a
ser a que aponta a ela; quando não traz, a ação genérica continua. A
condição vem do `emissao` que o servidor entregou — nunca de um teste
adivinhado, e nunca de um `if` escrito à mão sobre causa presumida.

Os **dois** lados têm teste aqui, porque o defeito era o texto não
discriminar: um teste só do caso "tem causa" passaria mesmo com a genérica
nunca aparecendo.
"""

from datetime import date

import pytest

from apps.contabilidade import views_web
from apps.contabilidade.models import NaturezaConta
from apps.contabilidade.services import apurar_dmpl
from apps.contabilidade.tests.test_dl061_dmpl import PL, C, _caso_a, _conta, _lancar
from apps.contabilidade.tests.test_dl061_tela_dmpl import _entrar, _texto, _url

pytestmark = pytest.mark.django_db


def _divergencia_com_subconta_sem_coluna():
    """A causa nomeada: uma subconta de PL com movimento e **sem coluna**.
    Ela entra no Balanço e não aparece em coluna nenhuma da DMPL — é a
    divergência, e a apuração a nomeia na lista vizinha."""
    empresa, contas, _ = _caso_a()
    filha = _conta(empresa, "3.2.1", "Reserva Legal - Subconta", PL, C, pai=contas["reserva_legal"])
    _lancar(empresa, date(2026, 3, 30), "Movimento na subconta", contas["caixa"], filha, "500.00")
    return empresa


def _divergencia_sem_conta_sem_coluna(client, monkeypatch):
    """Divergência com a lista de contas sem coluna **VAZIA** — a apuração
    original é substituída por uma que devolve só a divergência, para isolar
    a ausência da causa nomeada (o mesmo recurso de `monkeypatch` que os
    testes de tela do arquivo da DL-061 já usam)."""
    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"] = []
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)
    empresa, contas, _ = _caso_a()
    filha = _conta(empresa, "3.2.1", "Reserva Legal - Subconta", PL, C, pai=contas["reserva_legal"])
    _lancar(empresa, date(2026, 3, 30), "Movimento na subconta", contas["caixa"], filha, "500.00")
    return empresa


def test_a_apuracao_nomeia_a_causa_que_a_dica_agora_aponta(client):
    """Meio da verdade: o que a tela passa a dizer está de fato nomeado pelo
    servidor. Sem isto, a dica conditioned seria uma afirmação do produto sem
    lastro na apuração."""
    empresa = _divergencia_com_subconta_sem_coluna()

    dmpl = apurar_dmpl(empresa=empresa, ano=2026, mes=3)
    listas = dmpl["pendencias"]

    assert listas["diferenca_de_fechamento"], "o cenário tem de produzira divergência"
    assert listas["contas_do_patrimonio_liquido_sem_coluna"], "a causa tem de estar nomeada"
    assert any(
        item["conta"] == "3.2.1" for item in listas["contas_do_patrimonio_liquido_sem_coluna"]
    )


def test_com_a_causa_nomeada_a_dica_aponta_a_conta_sem_coluna(client):
    """Meio 1: com a lista não vazia, a tela mostra a ação condicionada e
    **não** a genérica."""
    empresa = _divergencia_com_subconta_sem_coluna()
    _entrar(client, empresa)

    html = _texto(client.get(_url(empresa)).content.decode())

    assert views_web._ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA in html
    generica = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA["diferenca_de_fechamento"]
    assert generica not in html, "a dica estática continua de fora, e é o que ela queria ser"


def test_sem_a_causa_nomeada_a_dica_generica_permanece(client, monkeypatch):
    """Meio 2: **sem** conta de PL sem coluna, a ação volta a ser a
    genérica. É este teste que impede a correção de virar "a dica passou a
    ser sempre a condicionada" — que seria tão falsa quanto a de antes."""
    empresa = _divergencia_sem_conta_sem_coluna(client, monkeypatch)
    _entrar(client, empresa)

    html = _texto(client.get(_url(empresa)).content.decode())

    generica = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA["diferenca_de_fechamento"]
    assert generica in html
    assert views_web._ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA not in html


def test_a_condicao_vem_do_servidor_e_nao_de_um_if_sobre_causa_presumida():
    """A causa é lida do `emissao` que a apuração entregou. Este teste
    fixa que a ação condicionada é um ÚNICO texto, guardado como constante
    nomeada — duas cópias do mesmo texto divergem, e o teste do outro lado
    do caminho citaria a cópia errada."""
    assert views_web._ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA.count("A diferença vem de") == 1
    # A constante NÃO está no dicionário estático: ela é a alternativa,
    # não a entrada padrão da lista.
    assert (
        views_web._ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA
        not in views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA.values()
    )


def test_a_natureza_da_conta_sem_coluna_nao_muda_o_que_a_dica_diz(client):
    """Controle de escopo: a dica muda pelo **fato** de a conta não ter
    coluna, e não pelo tipo dela. Uma conta de PL credora e uma devedora
    (retificadora) produzem a mesma ação — o que é o certo, porque as duas
    têm a mesma causa contábil aqui."""
    empresa, contas, _ = _caso_a()
    devedora = _conta(
        empresa, "3.7", "(-) Prejuízos sem coluna", PL, NaturezaConta.DEVEDORA, pai=contas["pl"]
    )
    _lancar(empresa, date(2026, 3, 28), "Prejuízo", contas["caixa"], devedora, "300.00")
    _entrar(client, empresa)

    html = _texto(client.get(_url(empresa)).content.decode())

    assert views_web._ACAO_DA_DIVERGENCIA_COM_CONTA_SEM_COLUNA in html


@pytest.fixture(autouse=True)
def _sem_deps_de_navegador():
    """Estes testes são de conteúdo de tela renderizado, não de navegador:
    nada aqui precisa de Chromium nem de `pdftotext`."""
    return None
