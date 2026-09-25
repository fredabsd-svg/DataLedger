"""BL-308 (achado A2 da auditoria DL-026, rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md): o teste que fechou o
BL-290 (`test_dl017_telas.py::test_balancete_soma_das_linhas_proprias_bate_
com_rodape`) afirmava:

    assert faixa[0] == rodape_debitos == Decimal("1700.00")
    assert faixa[1] == rodape_creditos == Decimal("1700.00")

Os DOIS lados são 1700,00. Por partida dobrada, débito e crédito de um
balancete fechado são SEMPRE iguais — então essa comparação não distingue
débito de crédito nenhuma vez que fosse escrita nesse estado. Medido pelo
auditor: trocar `total_creditos_ptbr` por `total_debitos_ptbr` na
`<strong>` de "Créditos próprios do período" (`templates/contabilidade/
balancete.html`) deu `1451 passed`. E no único estado em que a faixa
importa — apuração DIVERGENTE, o `monkeypatch` que o projeto já usa —, a
faixa sob a sabotagem CONTRADIZ a si mesma: anuncia "diferença de 0,01"
exibindo 300,00 e 300,00, enquanto o rodapé mostra 300,00 e 300,01.

Requisito geral do arquiteto-senior para esta rodada (não só este
achado): NENHUM teste desta faixa pode afirmar uma igualdade/diferença
num estado em que os dois valores comparados são INDISTINGUÍVEIS POR
CONSTRUÇÃO. Desde a correção da auditoria B.2+B.3, a view veta o estado
divergente sem renderizar esta faixa; o endpoint é testado para recusar
sem entregar conteúdo do relatório. Este arquivo mantém a verificação
isolada do fragmento em contextos sintéticos, para que a sabotagem exata:

1. É PEGA no estado divergente (débitos 300,00 / créditos 300,01 — os
   dois distinguíveis por construção).
2. É INVISÍVEL, por construção, no estado balanceado (débitos == créditos
   == 1700,00) — não por falta de teste, mas porque não existe
   observação possível que distinga as duas situações nesse estado. Isto
   não é um achado novo: é a demonstração de POR QUE o achado A2 existia,
   e de por que nenhuma asserção escrita ali poderia tê-lo fechado.

Método de mutação: em MEMÓRIA, nunca no arquivo do repositório — o MESMO
método que `test_dl024_veredito_no_html_renderizado.py` já usa para os
itens 1 e 2 do módulo irmão (extrai o fragmento do `{% if %}` do ARQUIVO
REAL a cada chamada, nunca uma cópia retypada à mão, e renderiza como
STRING via `django.template.engines["django"].from_string`, sem escrever
em disco). BL-311 (nesta mesma rodada) troca justamente a mutação que
ESCREVIA no arquivo real por este tipo de método; este arquivo já nasce
sem a necessidade de `try`/`finally` nem de `reset_loaders()` porque o
fragmento sob teste aqui não depende de outro fragmento fora dele (ao
contrário da sabotagem "condição sempre falsa" do BL-311, que precisa da
URL de verdade).
"""

import re
from pathlib import Path

from django.template import engines as _template_engines

_RAIZ = Path(__file__).resolve().parents[3]
_CAMINHO_BALANCETE = _RAIZ / "templates" / "contabilidade" / "balancete.html"

_MARCADOR_INICIO = '{% if veredito_balancete == "fecha" %}'
_MARCADOR_FIM = "</div>"

# A sabotagem exata medida pelo auditor: a <strong> de "Créditos próprios
# do período" passa a mostrar `total_debitos_ptbr` em vez de
# `total_creditos_ptbr`. Cada uma das duas variáveis aparece EXATAMENTE
# uma vez no fragmento (uma por <span class="contexto-item">), então
# `.replace(..., 1)` não tem ambiguidade de qual ocorrência está sendo
# trocada.
_MARCADOR_CREDITOS = "{{ total_creditos_ptbr }}"
_SABOTAGEM_CREDITOS_POR_DEBITOS = "{{ total_debitos_ptbr }}"


def _fragmento_faixa():
    """Extrai a `<div class="faixa-fechamento">...</div>` do ARQUIVO REAL
    a cada chamada — nunca uma cópia retypada à mão (mesma lição do
    BL-296: cópia que descreve o original diverge assim que o original
    muda). Mesmos marcadores que `test_dl024_veredito_no_html_
    renderizado.py::_fragmento_veredito_balancete` já usa.
    """
    texto = _CAMINHO_BALANCETE.read_text(encoding="utf-8")
    inicio = texto.index(_MARCADOR_INICIO)
    fim = texto.index(_MARCADOR_FIM, inicio) + len(_MARCADOR_FIM)
    return texto[inicio:fim]


def _renderizar(fragmento, contexto):
    template = _template_engines["django"].from_string(fragmento)
    return template.render(contexto)


def _valor_por_rotulo(html, rotulo):
    """Extrai o valor monetário ANCORADO pelo rótulo que o precede — não
    pela N-ésima ocorrência de `class="valor-monetario"` (que, no ramo
    "não fecha", inclui também o valor da diferença e desloca a posição).
    """
    padrao = re.compile(
        rf'<span class="contexto-rotulo">{re.escape(rotulo)}</span>\s*'
        r'<strong class="valor-monetario">([^<]+)</strong>'
    )
    m = padrao.search(html)
    assert m, f"rótulo {rotulo!r} não encontrado em: {html}"
    return m.group(1).strip()


def _fragmento_sabotado(fragmento_real):
    fragmento_mutado = fragmento_real.replace(
        _MARCADOR_CREDITOS, _SABOTAGEM_CREDITOS_POR_DEBITOS, 1
    )
    assert fragmento_mutado != fragmento_real, "controle: a mutação precisa mudar o fragmento"
    return fragmento_mutado


# ---------------------------------------------------------------------------
# Contextos sintéticos — os MESMOS números que o auditor mediu no produto,
# para rastreabilidade direta com o relatório.
# ---------------------------------------------------------------------------

_CTX_DIVERGENTE = {
    "veredito_balancete": "nao_fecha",
    "diferenca_balancete_ptbr": "0,01",
    "total_debitos_ptbr": "300,00",
    "total_creditos_ptbr": "300,01",
}

_CTX_BALANCEADO = {
    "veredito_balancete": "fecha",
    "diferenca_balancete_ptbr": None,
    "total_debitos_ptbr": "1.700,00",
    "total_creditos_ptbr": "1.700,00",
}


# ---------------------------------------------------------------------------
# 1) O template REAL, sob o estado divergente, distingue débito de
#    crédito — controle positivo, sem o qual os testes abaixo não
#    provariam nada.
# ---------------------------------------------------------------------------


def test_controle_estado_divergente_e_distinguivel_por_construcao():
    html = _renderizar(_fragmento_faixa(), _CTX_DIVERGENTE)
    debitos = _valor_por_rotulo(html, "Débitos próprios do período")
    creditos = _valor_por_rotulo(html, "Créditos próprios do período")
    assert debitos == "300,00", debitos
    assert creditos == "300,01", creditos
    assert debitos != creditos, "controle: o estado divergente TEM que ser distinguível"


# ---------------------------------------------------------------------------
# 2) A sabotagem exata do relatório É PEGA no estado divergente — a
#    reprodução, em memória, do que o auditor mediu no produto.
# ---------------------------------------------------------------------------


def test_sabotagem_creditos_por_debitos_e_pega_no_estado_divergente():
    fragmento_real = _fragmento_faixa()
    fragmento_mutado = _fragmento_sabotado(fragmento_real)

    html_mutado = _renderizar(fragmento_mutado, _CTX_DIVERGENTE)
    creditos_sob_mutante = _valor_por_rotulo(html_mutado, "Créditos próprios do período")
    debitos_sob_mutante = _valor_por_rotulo(html_mutado, "Débitos próprios do período")

    # A prova de que a mutação É PEGA: o rótulo "Créditos" passa a
    # mostrar o valor de DÉBITO (300,00) em vez do de crédito (300,01).
    assert creditos_sob_mutante == "300,00", (
        "a sabotagem deveria fazer 'Créditos próprios do período' mostrar o valor "
        f"de débito — obtido: {creditos_sob_mutante!r}"
    )

    # E a faixa passa a CONTRADIZER o próprio texto do veredito: o
    # veredito diz "diferença de 0,01" e os dois valores exibidos ficam
    # IGUAIS — a MESMA contradição que o auditor mediu no produto (300,00
    # e 300,00 sob "diferença de 0,01").
    assert debitos_sob_mutante == creditos_sob_mutante == "300,00", (
        debitos_sob_mutante,
        creditos_sob_mutante,
    )
    assert "diferença de" in html_mutado
    assert "0,01" in html_mutado

    # O fragmento REAL, no MESMO contexto sintético, não tem essa
    # contradição: o real distingue, o mutante não.
    html_real = _renderizar(fragmento_real, _CTX_DIVERGENTE)
    creditos_real = _valor_por_rotulo(html_real, "Créditos próprios do período")
    debitos_real = _valor_por_rotulo(html_real, "Débitos próprios do período")
    assert creditos_real != debitos_real, (creditos_real, debitos_real)


# ---------------------------------------------------------------------------
# 3) A MESMA sabotagem é INVISÍVEL no estado balanceado — não é um
#    achado novo, é a demonstração de por que o teste original do BL-290
#    (escrito nesse estado) nunca poderia ter servido de guarda.
# ---------------------------------------------------------------------------


def test_sabotagem_e_invisivel_no_estado_balanceado_por_construcao():
    """Débito e crédito são SEMPRE iguais no estado 'fecha' (partida
    dobrada) — a troca de um pelo outro não muda NADA observável por
    igualdade de texto. É o mesmo fato que tornou o teste original do
    BL-290 (`faixa[0] == rodape_debitos == 1700,00` e
    `faixa[1] == rodape_creditos == 1700,00`) incapaz de reprovar a troca
    — 1451 passed, medido pelo auditor. Este teste não é uma falha de
    cobertura a corrigir: é a prova, por construção, de que NENHUMA
    asserção de igualdade escrita no estado balanceado pode ser guarda
    contra esta classe de sabotagem — por isso os testes do fragmento
    usam o estado divergente sintético (teste 2, acima). A view tem uma
    guarda própria para impedir que esse estado produza um Balancete.
    """
    fragmento_real = _fragmento_faixa()
    fragmento_mutado = _fragmento_sabotado(fragmento_real)

    html_real = _renderizar(fragmento_real, _CTX_BALANCEADO)
    html_mutado = _renderizar(fragmento_mutado, _CTX_BALANCEADO)

    creditos_real = _valor_por_rotulo(html_real, "Créditos próprios do período")
    creditos_mutado = _valor_por_rotulo(html_mutado, "Créditos próprios do período")
    debitos_real = _valor_por_rotulo(html_real, "Débitos próprios do período")
    debitos_mutado = _valor_por_rotulo(html_mutado, "Débitos próprios do período")

    # A sabotagem NÃO MUDA NADA observável no estado balanceado: real e
    # mutante renderizam "1.700,00" para os dois rótulos.
    assert creditos_real == creditos_mutado == "1.700,00"
    assert debitos_real == debitos_mutado == "1.700,00"
