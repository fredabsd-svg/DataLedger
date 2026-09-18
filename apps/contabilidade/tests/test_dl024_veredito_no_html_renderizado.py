"""Achado do `arquiteto-senior`, revisão integrada `65af1dc`, rodada 4 da
DL-024 (docs/auditorias/2026-09-18-dl-024-rodada-2.md, achado A1).

Os 13 testes de `apps/contabilidade/tests/test_bl289_veredito_fechamento.py`
(do `desenvolvedor-pleno`) afirmam sobre a CHAVE do contexto de
renderização — `veredito_fechamento`/`veredito_balancete`. Correto para a
fronteira dele: ele testa a DECISÃO, que é o que a view entrega.

Só que o achado A1 nunca foi sobre a decisão — era sobre a FRASE que o
contador lê antes de gravar. Entre a chave certa e a frase certa existe um
template, e nenhum teste, em nenhum arquivo, conferia o TEXTO que a tela
de fato mostra. Prova: o arquiteto trocou, numa CÓPIA fora do repositório,
`{% if veredito_fechamento == "fecha" %}` de volta para
`{% if total_debito_ptbr == total_credito_ptbr %}` — o defeito original do
A1. Com o formulário em branco, a CHAVE do contexto continuava certa
(`nao_conferido` — a view nem foi tocada), mas a TELA voltou a mostrar
"Fecha" (`None == None` é verdadeiro em template Django). A suíte inteira,
inclusive os 13 testes do BL-289, continuou verde.

Este arquivo fecha essa lacuna. Duas coisas, para cada uma das duas telas
(lançamento e balancete):

1. Para cada um dos três estados, o texto do estado ESPERADO está
   presente e os outros DOIS estão ausentes — nunca só `"X" not in html`,
   que passaria trivialmente se o veredito sumisse do HTML inteiro.
2. Uma mutação que reproduz EXATAMENTE o defeito do achado A1 (comparar
   `total_..._ptbr` em vez de ramificar pela chave) tem que produzir o
   texto ERRADO — a prova de que os testes do item 1, rodados contra um
   template mutado, morreriam.

Método de mutação: extrai o FRAGMENTO do `{% if %}` do ARQUIVO REAL a cada
chamada (nunca retypado à mão — a mesma lição do BL-296: cópia que
descreve o original diverge assim que o original muda) e o RENDERIZA como
STRING em memória, com `django.template.engines["django"].from_string`
mais um contexto sintético — nunca escrevendo no arquivo do repositório.
É o MESMO método que `test_dl017_rodada2_frontend.py` já usa para mutar
`static/css/base.css` ("aplica o mutante numa CÓPIA do CSS real, nunca o
arquivo do repositório") — aqui aplicado a um fragmento de template em vez
de uma folha de estilo.
"""

import re
from pathlib import Path

from django.template import engines as _template_engines

_RAIZ = Path(__file__).resolve().parents[3]
_CAMINHO_LANCAMENTO = _RAIZ / "templates" / "contabilidade" / "lancamento_form.html"
_CAMINHO_BALANCETE = _RAIZ / "templates" / "contabilidade" / "balancete.html"

_MARCADOR_INICIO_LANCAMENTO = '{% if veredito_fechamento == "fecha" %}'
_MARCADOR_FIM_LANCAMENTO = "{% endif %}"

_MARCADOR_INICIO_BALANCETE = '{% if veredito_balancete == "fecha" %}'
_MARCADOR_FIM_BALANCETE = "</div>"


def _fragmento(texto, marcador_inicio, marcador_fim):
    inicio = texto.index(marcador_inicio)
    fim = texto.index(marcador_fim, inicio) + len(marcador_fim)
    return texto[inicio:fim]


def _fragmento_veredito_lancamento():
    """O `{% if %}...{% endif %}` que decide o veredito do lançamento,
    extraído do ARQUIVO REAL a cada chamada — nunca uma cópia retypada à
    mão."""
    texto = _CAMINHO_LANCAMENTO.read_text(encoding="utf-8")
    return _fragmento(texto, _MARCADOR_INICIO_LANCAMENTO, _MARCADOR_FIM_LANCAMENTO)


def _fragmento_veredito_balancete():
    texto = _CAMINHO_BALANCETE.read_text(encoding="utf-8")
    return _fragmento(texto, _MARCADOR_INICIO_BALANCETE, _MARCADOR_FIM_BALANCETE)


def _renderizar(fragmento, contexto):
    template = _template_engines["django"].from_string(fragmento)
    return template.render(contexto)


def _texto_veredito_lancamento(contexto, fragmento=None):
    fragmento = fragmento if fragmento is not None else _fragmento_veredito_lancamento()
    html = _renderizar(fragmento, contexto)
    m = re.search(r'<strong class="veredito-fechamento">(.*?)</strong>', html, re.DOTALL)
    assert m, 'o fragmento não produziu nenhum <strong class="veredito-fechamento">: ' + html
    # Normaliza espaço: o `<span class="valor-monetario">` do "não fecha"
    # quebra a frase em mais de uma linha no HTML.
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _texto_veredito_balancete(contexto, fragmento=None):
    fragmento = fragmento if fragmento is not None else _fragmento_veredito_balancete()
    html = _renderizar(fragmento, contexto)
    m = re.search(r'<strong class="faixa-fechamento__veredito">(.*?)</strong>', html, re.DOTALL)
    assert m, 'o fragmento não produziu nenhum <strong class="faixa-fechamento__veredito">: ' + html
    return re.sub(r"\s+", " ", m.group(1)).strip()


# ---------------------------------------------------------------------------
# Contextos sintéticos — um por estado, para as duas telas. Os valores
# pt-BR são arbitrários (não vêm de `_valor_ptbr`, de propósito: este
# arquivo testa o TEMPLATE, não o cálculo — o cálculo já tem cobertura
# própria em test_bl289_veredito_fechamento.py/test_bl290_veredito_
# balancete.py, do desenvolvedor-pleno).
# ---------------------------------------------------------------------------

_CTX_LANCAMENTO_FECHA = {
    "veredito_fechamento": "fecha",
    "total_debito_ptbr": "777,77",
    "total_credito_ptbr": "777,77",
    "diferenca_fechamento_ptbr": None,
    "lado_faltante_fechamento": None,
}
_CTX_LANCAMENTO_NAO_FECHA = {
    "veredito_fechamento": "nao_fecha",
    "total_debito_ptbr": "1.500,00",
    "total_credito_ptbr": "900,00",
    "diferenca_fechamento_ptbr": "600,00",
    "lado_faltante_fechamento": "crédito",
}
_CTX_LANCAMENTO_NAO_CONFERIDO = {
    "veredito_fechamento": "nao_conferido",
    "total_debito_ptbr": None,
    "total_credito_ptbr": None,
    "diferenca_fechamento_ptbr": None,
    "lado_faltante_fechamento": None,
}

_CTX_BALANCETE_FECHA = {
    "veredito_balancete": "fecha",
    "diferenca_balancete_ptbr": None,
    "total_debitos_ptbr": "1.700,00",
    "total_creditos_ptbr": "1.700,00",
}
_CTX_BALANCETE_NAO_FECHA = {
    "veredito_balancete": "nao_fecha",
    "diferenca_balancete_ptbr": "0,01",
    "total_debitos_ptbr": "300,00",
    "total_creditos_ptbr": "300,01",
}
_CTX_BALANCETE_NADA_A_CONFERIR = {
    "veredito_balancete": "nada_a_conferir",
    "diferenca_balancete_ptbr": None,
    "total_debitos_ptbr": "0,00",
    "total_creditos_ptbr": "0,00",
}


# ---------------------------------------------------------------------------
# 1) O texto certo, presente; os outros dois, ausentes — lançamento
# ---------------------------------------------------------------------------


def test_lancamento_fecha_mostra_fecha_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_FECHA)
    assert texto == "Fecha", texto
    assert "Não fecha" not in texto
    assert "Ainda não conferido" not in texto


def test_lancamento_nao_fecha_mostra_a_diferenca_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_FECHA)
    assert texto.startswith("Não fecha, faltam"), texto
    assert "600,00" in texto
    assert "crédito" in texto
    assert texto != "Fecha"
    assert "Ainda não conferido" not in texto


def test_lancamento_nao_conferido_mostra_texto_proprio_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_CONFERIDO)
    assert texto == "Ainda não conferido", texto
    assert "Fecha" not in texto
    assert "Não fecha" not in texto


# ---------------------------------------------------------------------------
# 1) O texto certo, presente; os outros dois, ausentes — balancete
# ---------------------------------------------------------------------------


def test_balancete_fecha_mostra_fecha_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_FECHA)
    assert texto == "Fecha", texto
    assert "Não fecha" not in texto
    assert "Nada a conferir" not in texto


def test_balancete_nao_fecha_mostra_a_diferenca_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_NAO_FECHA)
    assert texto.startswith("Não fecha"), texto
    assert "0,01" in texto
    assert texto != "Fecha"
    assert "Nada a conferir" not in texto


def test_balancete_nada_a_conferir_mostra_texto_proprio_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_NADA_A_CONFERIR)
    assert texto == "Nada a conferir neste período", texto
    assert "Fecha" not in texto
    assert "Não fecha" not in texto


# ---------------------------------------------------------------------------
# 2) A mutação do arquiteto-senior tem que produzir o texto ERRADO — a
# prova de que os seis testes acima, rodados contra um template mutado,
# morreriam.
# ---------------------------------------------------------------------------


def test_mutacao_comparar_texto_no_lancamento_reproduz_o_a1_e_mente():
    """Reproduz, caractere por caractere, a mutação da revisão `65af1dc`:
    `{% if veredito_fechamento == "fecha" %}` -> `{% if total_debito_ptbr
    == total_credito_ptbr %}`. No estado "ainda não conferido" do
    formulário em branco, os dois totais chegam `None`
    (`total_debito_ptbr`/`total_credito_ptbr`) — `None == None` é
    verdadeiro em template Django, então o mutante cai no ramo "Fecha"
    mesmo a CHAVE do contexto dizendo `"nao_conferido"`. É o defeito
    original do achado A1, voltando por uma linha só.
    """
    fragmento_real = _fragmento_veredito_lancamento()
    fragmento_mutado = fragmento_real.replace(
        _MARCADOR_INICIO_LANCAMENTO,
        "{% if total_debito_ptbr == total_credito_ptbr %}",
        1,
    )
    assert fragmento_mutado != fragmento_real, "controle: a mutação precisa mudar o fragmento"

    texto_sob_mutante = _texto_veredito_lancamento(
        _CTX_LANCAMENTO_NAO_CONFERIDO, fragmento=fragmento_mutado
    )
    assert texto_sob_mutante == "Fecha", (
        "a mutação deveria reproduzir o A1 (tela mente 'Fecha' com a chave em "
        f"'nao_conferido') — texto obtido sob o mutante: {texto_sob_mutante!r}"
    )

    # E o fragmento REAL, no MESMO contexto, continua dizendo a verdade —
    # é o que prova que os testes da seção 1 morreriam sob esta mutação
    # (eles exigem "Ainda não conferido", o mutante entrega "Fecha").
    texto_real = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_CONFERIDO)
    assert texto_real == "Ainda não conferido", texto_real


def test_mutacao_comparar_texto_no_balancete_reproduz_o_a2_e_mente():
    """Mesma família, na faixa do balancete — reproduz o defeito original
    do A2/rodada 1: `{% if veredito_balancete == "fecha" %}` ->
    `{% if total_debitos_ptbr == total_creditos_ptbr %}`. No estado "nada
    a conferir" (sem movimento no período), os dois totais chegam
    `"0,00"` — `"0,00" == "0,00"` é verdadeiro em texto, e o mutante cai
    em "Fecha" mesmo a CHAVE dizendo `"nada_a_conferir"`.
    """
    fragmento_real = _fragmento_veredito_balancete()
    fragmento_mutado = fragmento_real.replace(
        _MARCADOR_INICIO_BALANCETE,
        "{% if total_debitos_ptbr == total_creditos_ptbr %}",
        1,
    )
    assert fragmento_mutado != fragmento_real, "controle: a mutação precisa mudar o fragmento"

    texto_sob_mutante = _texto_veredito_balancete(
        _CTX_BALANCETE_NADA_A_CONFERIR, fragmento=fragmento_mutado
    )
    assert texto_sob_mutante == "Fecha", (
        "a mutação deveria reproduzir o A2 (faixa mente 'Fecha' com a chave em "
        f"'nada_a_conferir') — texto obtido sob o mutante: {texto_sob_mutante!r}"
    )

    texto_real = _texto_veredito_balancete(_CTX_BALANCETE_NADA_A_CONFERIR)
    assert texto_real == "Nada a conferir neste período", texto_real


# ---------------------------------------------------------------------------
# Controle: os fragmentos extraídos do arquivo real batem com os
# marcadores esperados — se alguém reescrever o `{% if %}` para outro
# formato (ex.: trocar a ordem dos ramos), este teste avisa ANTES de os
# testes acima começarem a testar fragmento vazio ou errado em silêncio.
# ---------------------------------------------------------------------------


def test_controle_fragmentos_extraidos_contem_os_tres_ramos():
    fragmento_lancamento = _fragmento_veredito_lancamento()
    for pedaco in ('veredito_fechamento == "fecha"', "elif", "else", "veredito-fechamento"):
        assert pedaco in fragmento_lancamento, (pedaco, fragmento_lancamento)

    fragmento_balancete = _fragmento_veredito_balancete()
    for pedaco in ('veredito_balancete == "fecha"', "elif", "else", "faixa-fechamento__veredito"):
        assert pedaco in fragmento_balancete, (pedaco, fragmento_balancete)
