"""Sonda de visibilidade REAL (motor de layout do navegador) — módulo
reutilizável extraído de `juiz.py`.

**Por que este módulo existe (DL-028, fatia 1;
docs/planos/DL-028-o-juiz-aponta-para-o-produto.md).** Até esta etapa,
`visivelDeVerdade` e a sonda de impressão (`SONDA_IMPRESSAO`) só existiam
DENTRO de `juiz.py` — que mede protótipos AUTÔNOMOS do gauntlet
(`pasta.glob("*.html")`), nunca o produto real (`static/css/base.css` +
`templates/**`). A oitava auditoria da DL-026
(docs/auditorias/2026-09-19-dl-026-rodada-8.md, §7) apontou a consequência:
para a pergunta "o documento que sai para o cliente vem identificado?", a
guarda do `pytest` (que simula cascata CSS em Python, sem navegador) não era
a PRIMEIRA de duas camadas — era a ÚNICA, porque a segunda ("o juiz de
bancada cobre o que só um motor de layout decide") nunca olhava para o
produto.

Este módulo é a peça COMUM entre `juiz.py` (que continua servindo o
gauntlet) e `scripts/medir_identificacao_do_emitente.py` (o instrumento
NOVO desta etapa, que aponta para o produto real). A lógica de "o que é
visível de verdade" e "como perguntar isso sob impressão" mora AQUI, uma
vez só — AGENTS.md §8: duas implementações da mesma regra divergem assim
que uma for corrigida sem a outra.

Este módulo não importa Django nem Playwright: só monta strings de
JavaScript e resolve o executável do navegador. Quem chama decide COMO
abrir a página (arquivo local, cliente Django de teste, etc.).
"""

import json
import os

# ---------------------------------------------------------------------------
# A derivação certa de "visível de verdade" (BL-314/BL-329, ver o comentário
# completo abaixo) — movida de juiz.py, TEXTO VERBATIM: três medições
# GERAIS do motor de layout, não uma lista de técnicas de esconder.
# ---------------------------------------------------------------------------

# BL-314/BL-329: visibilidade REAL do elemento — não uma lista de
# propriedades CSS suspeitas (display/visibility/opacity), e sim três
# medições GERAIS que o motor de layout do navegador já faz por conta
# própria:
#
# 1. `Element.checkVisibility({checkOpacity, checkVisibilityCSS})` — a
#    própria API do navegador para "este elemento está excluído da árvore
#    visual por display/visibility/content-visibility/opacidade (do
#    elemento OU de qualquer ancestral)". Delega a pergunta a quem já
#    resolve cascata e herança corretamente — não a este script.
# 2. `getBoundingClientRect()` tem ÁREA (largura E altura > 0) — pega
#    técnicas que `checkVisibility` não cobre por definição:
#    `width/height: 0`, `transform: scale(0)`. MEDIDO neste projeto (não
#    presumido): as duas passam por `checkVisibility` (que devolve `true`)
#    e são pegas SÓ pela área.
# 3. O retângulo é ALCANÇÁVEL por rolagem da página — pega posicionamento
#    fora da tela (`position: absolute; left: -9999px`), que não muda
#    `checkVisibility` nem zera a área.
#
# As três, JUNTAS, cobrem `display: none`, `visibility: hidden`,
# `opacity: 0` e "fora da tela" sem este script precisar SABER que essas
# são as técnicas — é o requisito ("qualquer forma de esconder"), não a
# lista de quatro exemplos.
#
# Limite MEDIDO e declarado, não descoberto por auditoria depois:
# `clip-path: inset(100%)` NÃO é pego por nenhuma das três — o elemento
# continua com `checkVisibility() === true` e a mesma área, porque
# `clip-path` recorta o PIXEL pintado, não a caixa de layout que
# `getBoundingClientRect` mede. Um texto ilegível por `color: transparent`
# (mesma cor do fundo) também não é pego AQUI — mas esse caso cai no
# cálculo de CONTRASTE que `juiz.py` já faz para o resto da tela (razão
# ~1:1 contra o próprio fundo); o instrumento do DL-028
# (`scripts/medir_identificacao_do_emitente.py`) fecha o mesmo caso por um
# caminho DIFERENTE e mais direto para o seu domínio: o texto lido do PDF
# A4 por `pdftotext` — `color: transparent` não impede o Chromium de
# PINTAR o glifo (é pixel idêntico ao fundo, não texto ausente), então o
# PDF ainda TEM o texto extraível, e é exatamente esse descolamento entre
# "está no PDF" e "dá para LER" que a checagem dupla (visibilidade +
# texto) do instrumento expõe.
JS_VISIVEL_DE_VERDADE = r"""
    const visivelDeVerdade = (el) => {
        const suportaApi = typeof el.checkVisibility === 'function';
        const apiDiz = suportaApi
            ? el.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})
            : true;
        const r = el.getBoundingClientRect();
        const temArea = r.width > 0 && r.height > 0;
        const alcancavelPorRolagem = r.right > 0 && r.bottom > 0
            && r.left < document.scrollingElement.scrollWidth
            && r.top < document.scrollingElement.scrollHeight;
        return {
            visivel: apiDiz && temArea && alcancavelPorRolagem,
            suporta_check_visibility: suportaApi,
            check_visibility: apiDiz,
            tem_area: temArea,
            alcancavel_por_rolagem: alcancavelPorRolagem,
            retangulo: {largura: r.width, altura: r.height, esquerda: r.left, topo: r.top},
        };
    };
"""


def js_sonda_impressao(seletores):
    """Monta a sonda de impressão (JS) para o dicionário `nome -> seletor
    CSS` informado — avaliada por `page.evaluate(...)` depois de
    `page.emulate_media(media="print")`. Extraída de `SONDA_IMPRESSAO`
    (antes só dentro de `juiz.py`, fixa em dois seletores) para aceitar
    QUALQUER conjunto: `juiz.py` continua chamando com
    `SELETORES_DE_IMPRESSAO` (marca do fornecedor + timbre do escritório);
    `scripts/medir_identificacao_do_emitente.py` chama com o seletor do
    timbre, um por tela. Duas cópias da mesma sonda, uma por consumidor,
    divergiriam assim que uma fosse corrigida sem a outra (AGENTS.md §8) —
    por isso a MONTAGEM mora aqui, não em cada consumidor.
    """
    sonda = r"""
() => {
    __JS_VISIVEL_DE_VERDADE__
    const seletores = __SELETORES_JSON__;
    const resultado = {};
    for (const [nome, seletor] of Object.entries(seletores)) {
        const el = document.querySelector(seletor);
        resultado[nome] = el
            ? Object.assign({seletor, encontrado: true}, visivelDeVerdade(el))
            : {seletor, encontrado: false};
    }
    return resultado;
}
"""
    sonda = sonda.replace("__JS_VISIVEL_DE_VERDADE__", JS_VISIVEL_DE_VERDADE)
    sonda = sonda.replace("__SELETORES_JSON__", json.dumps(seletores))
    return sonda


def js_sonda_container_e_filhos(seletor_container, seletor_filhos):
    """Sonda de impressão para um CONTÊINER e cada um dos seus elementos
    FILHOS (ex.: `.timbre-impressao` e `.timbre-impressao p`) — usada
    quando a pergunta não é só "o bloco está visível?", mas "CADA LINHA
    dentro dele está?".

    Por quê isto existe separado de `js_sonda_impressao`: uma sabotagem
    como `.timbre-impressao p:nth-of-type(2) { display: none }` esconde
    só UMA linha (ex.: o registro profissional), mantendo o contêiner e a
    primeira linha visíveis — reprovar só pelo contêiner NÃO pega
    identificação PARCIAL. `visivelDeVerdade` continua sendo a MESMA
    função (reaproveitada, nunca reimplementada) — o que muda é enumerar
    os filhos em vez de olhar um seletor fixo por vez.

    **Acrescenta `cor_efetiva` (o `getComputedStyle(el).color` cru) a CADA
    elemento — container e filhos.** Isto fecha, para quem consome esta
    sonda, o limite que `visivelDeVerdade` já declara por escrito (ver o
    comentário de `JS_VISIVEL_DE_VERDADE`, acima): `color: transparent`
    NÃO muda `checkVisibility()`, NÃO zera a área do retângulo, e o texto
    continua no fluxo — as três medições dizem "visível". Só que tinta
    com alfa zero não é identificação nenhuma: `color: transparent`
    equivale, na prática, a `rgba(0, 0, 0, 0)`. `visivelDeVerdade` em si
    NÃO ganha essa checagem (ela é a derivação GERAL, usada também pela
    marca do fornecedor e pelo momento da verdade contábil, onde o limite
    já está declarado e coberto por CONTRASTE — ver `juiz.py`); é este
    probe ESPECÍFICO de identificação do emitente que expõe a cor bruta
    para quem chama decidir (`scripts/medir_identificacao_do_emitente.py`
    trata alfa zero como "não legível", ao lado do texto extraído do PDF).
    """
    sonda = r"""
() => {
    __JS_VISIVEL_DE_VERDADE__
    const container = document.querySelector(__SELETOR_CONTAINER_JSON__);
    const resultado = {
        seletor_container: __SELETOR_CONTAINER_JSON__,
        encontrado: !!container,
    };
    if (container) {
        Object.assign(resultado, visivelDeVerdade(container));
        resultado.cor_efetiva = getComputedStyle(container).color;
        resultado.filhos = [...document.querySelectorAll(__SELETOR_FILHOS_JSON__)].map((el) => {
            const v = visivelDeVerdade(el);
            v.texto = (el.textContent || '').trim();
            v.cor_efetiva = getComputedStyle(el).color;
            return v;
        });
    } else {
        resultado.filhos = [];
    }
    return resultado;
}
"""
    sonda = sonda.replace("__JS_VISIVEL_DE_VERDADE__", JS_VISIVEL_DE_VERDADE)
    sonda = sonda.replace("__SELETOR_CONTAINER_JSON__", json.dumps(seletor_container))
    sonda = sonda.replace("__SELETOR_FILHOS_JSON__", json.dumps(seletor_filhos))
    return sonda


# ---------------------------------------------------------------------------
# Resolução do executável do Chromium — SEM caminho fixo em arquivo
# versionado (restrição da DL-028/DE-057: o `/opt/pw-browsers/...` desta
# máquina é acidente do ambiente, não configuração do projeto).
# ---------------------------------------------------------------------------

VARIAVEL_DE_AMBIENTE_CHROMIUM = "DL_CHROMIUM_EXECUTAVEL"


class NavegadorIndisponivel(RuntimeError):
    """Falha de INFRAESTRUTURA — nunca de conteúdo. BL-356 (instrumento
    que degrada em silêncio): "não consegui abrir o navegador" e "o
    documento saiu sem emitente" são coisas diferentes, e quem chama este
    módulo precisa poder distingui-las pela EXCEÇÃO, não só pela
    mensagem — por isso é um tipo próprio, não um `sys.exit` direto
    daqui."""


def resolver_executavel_do_chromium():
    """Resolve o caminho do executável do Chromium por DUAS formas, nesta
    ordem, nunca por um literal escrito no código:

    1. Variável de ambiente `DL_CHROMIUM_EXECUTAVEL`, se definida — permite
       apontar para um binário específico (outra versão, outro caminho de
       instalação) sem editar nenhum arquivo.
    2. Descoberta NATIVA do Playwright: devolver `None` aqui e deixar quem
       chama fazer `playwright_instance.chromium.launch()` SEM
       `executable_path` — o próprio pacote resolve o executável instalado
       pelo seu gerenciador (`playwright install chromium`), na versão que
       corresponde ao pacote Python instalado. É a MESMA resolução que
       qualquer outro consumidor de Playwright usaria; não há nada para
       este módulo reimplementar além de expor a escolha.

    Levanta `NavegadorIndisponivel` (não `sys.exit`: quem chama decide como
    reportar) quando a variável está definida mas não aponta para um
    executável de verdade — falha cedo, com o motivo, em vez de deixar o
    Playwright produzir um erro genérico de "arquivo não encontrado" três
    camadas depois.
    """
    caminho = os.environ.get(VARIAVEL_DE_AMBIENTE_CHROMIUM)
    if not caminho:
        return None
    if not (os.path.isfile(caminho) and os.access(caminho, os.X_OK)):
        raise NavegadorIndisponivel(
            f"{VARIAVEL_DE_AMBIENTE_CHROMIUM}={caminho!r} não é um arquivo "
            "executável. Corrija a variável, ou remova-a para usar a "
            "descoberta nativa do Playwright (playwright install chromium)."
        )
    return caminho


def lancar_chromium(playwright_instance, **kwargs):
    """Lança o Chromium do Playwright, resolvendo o executável por
    `resolver_executavel_do_chromium` (nunca um caminho fixo). Qualquer
    falha do lançamento — executável ausente, `playwright install` nunca
    rodado, biblioteca de sistema faltando — é reembalada em
    `NavegadorIndisponivel`: FALHA DE INFRAESTRUTURA, com mensagem que diz
    o que fazer, distinguível por quem chama de uma falha de CONTEÚDO
    (documento sem emitente)."""
    caminho = resolver_executavel_do_chromium()
    try:
        if caminho:
            return playwright_instance.chromium.launch(executable_path=caminho, **kwargs)
        return playwright_instance.chromium.launch(**kwargs)
    except NavegadorIndisponivel:
        raise
    except Exception as erro:  # noqa: BLE001 — reembalado com o tipo certo, não silenciado
        raise NavegadorIndisponivel(
            f"não foi possível iniciar o Chromium do Playwright: "
            f"{type(erro).__name__}: {erro}. Defina "
            f"{VARIAVEL_DE_AMBIENTE_CHROMIUM} com o caminho de um executável, "
            "ou rode 'playwright install chromium' no interpretador usado "
            "para este script."
        ) from erro
