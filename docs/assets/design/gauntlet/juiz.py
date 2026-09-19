"""Juiz mecânico do gauntlet de design do DataLedger.

Ele NÃO julga beleza. Ele mede o que a régua do brief define como
eliminatório ou contável, para que a parte subjetiva do julgamento aconteça
depois — e sobre variantes que já passaram no que é objetivo.

Rode com o Python do sistema (tem playwright):
    /usr/bin/python3 juiz.py <pasta-da-variante> [...]

**Este juiz NÃO roda na integração contínua.** Ele abre um Chromium de
verdade (resolvido por `sonda_visibilidade.lancar_chromium`, sem caminho
fixo) — a suíte `pytest` do projeto não tem esse binário disponível, e não
é objetivo deste instrumento ganhar essa dependência. É ferramenta de
BANCADA: quem fecha uma etapa de design que
mexa no "momento da verdade" de um módulo (contábil: débito/crédito; ver
docs/projeto/direcao-de-arte.md §3) roda este script manualmente contra a
tela renderizada antes de declarar a etapa pronta — a mesma obrigação que
o BL-300 já registrou para a densidade de linhas. Nenhuma etapa deste
projeto pode citar a saída deste juiz como prova de CI: é prova de bancada,
com o nome de quem rodou e quando, como qualquer medição fora do pytest.

BL-314 (achado M5 da auditoria DL-026, rodada 3;
docs/auditorias/2026-09-19-dl-024-rodada-4.md, §3): o veredito "em três
camadas" do módulo contábil (contexto do servidor, texto renderizado,
mutação de condição sempre falsa — ver
apps/contabilidade/tests/test_dl024_veredito_no_html_renderizado.py) são
três formas de ler TEXTO em HTML; nenhuma pergunta se o contador **vê**
alguma coisa. `display: none` no CSS derrota as três ao mesmo tempo e a
suíte `pytest` inteira continua verde, porque nenhuma delas roda num
motor de layout. Este juiz cobre exatamente essa lacuna, para os dois
elementos do "momento da verdade" da contabilidade (`MOMENTO_DA_VERDADE_
SELETORES`, abaixo) — visibilidade REAL (medida pelo motor de layout do
Chromium, não por uma lista de propriedades CSS suspeitas — ver
`visivelDeVerdade` na sonda) e contraste (reaproveitando a composição de
camadas de transparência que já existia para o resto da tela).

DL-028, fatia 1 (docs/planos/DL-028-o-juiz-aponta-para-o-produto.md): a
sonda de visibilidade (`JS_VISIVEL_DE_VERDADE`) e a montagem da sonda de
impressão (`js_sonda_impressao`) foram EXTRAÍDAS para
`sonda_visibilidade.py`, módulo irmão deste arquivo — agora também
importado por `scripts/medir_identificacao_do_emitente.py`, o instrumento
NOVO que aponta para o PRODUTO real (não para os protótipos autônomos que
este juiz mede). Este arquivo continua servindo só o gauntlet; nada do
comportamento dele mudou, só deixou de RETYPAR a lógica que os dois
consumidores compartilham (AGENTS.md §8). O caminho fixo do Chromium
(`CHROMIUM`, que existia aqui) também saiu: `sonda_visibilidade.
lancar_chromium` resolve por variável de ambiente ou pela descoberta
nativa do Playwright — nunca por um literal de caminho de uma máquina
específica (ver a docstring daquela função).
"""

import json
import re
import sys
from pathlib import Path

import sonda_visibilidade
from playwright.sync_api import sync_playwright

LARGURAS = [(1280, 800), (1920, 1080)]

# Os dois elementos do "momento da verdade" do módulo contábil (direção de
# arte §3: "Débito é igual a crédito?") — os mesmos seletores que
# `templates/contabilidade/lancamento_form.html` e
# `templates/contabilidade/balancete.html` usam para o texto do veredito.
# Isto É uma lista, mas ela lista O QUE checar (dois elementos nomeados da
# TELA), não COMO detectar "escondido" — essa segunda lista é o que o
# BL-314 pede para não existir, e `visivelDeVerdade` não enumera técnicas
# de esconder: ela pergunta ao motor de layout se o elemento é visível
# (`Element.checkVisibility`), se ocupa área na página
# (`getBoundingClientRect`) e se essa área é alcançável por rolagem — três
# medições GERAIS, não uma lista de `display`/`visibility`/`opacity`.
MOMENTO_DA_VERDADE_SELETORES = [".veredito-fechamento", ".faixa-fechamento__veredito"]

# BL-329: elemento que carrega a MARCA DO FORNECEDOR — o "DataLedger." que o
# BL-282 tirou do papel (`templates/base.html`, dentro de `.marca`, dentro de
# `.cabecalho__topo`). Mesma distinção do comentário acima: isto nomeia O QUE
# checar (um elemento nomeado da tela pela classe que `static/css/base.css` e
# `templates/base.html` já usam para o mesmo conceito), não COMO detectar
# escondido — `visivelDeVerdade`, reaproveitada abaixo em
# `JS_VISIVEL_DE_VERDADE`, é a mesma função GERAL usada pelo momento da
# verdade contábil, agora também sob mídia de IMPRESSÃO (ver
# `SONDA_IMPRESSAO` e o uso em `julgar_arquivo`).
SELETOR_MARCA_DO_FORNECEDOR = ".marca"

# BL-331 (achado A1 da auditoria DL-026, rodada 5): a metade SIMÉTRICA do
# requisito do BL-329 — não basta a marca do FORNECEDOR sair do papel, o
# timbre do ESCRITÓRIO precisa ENTRAR. `apps/contabilidade/tests/
# test_bl331_timbre_do_escritorio_no_papel.py` já prova isto por simulação
# de cascata CSS (sem Chromium); esta constante estende a MEDIÇÃO de
# bancada (motor de layout real) ao mesmo elemento, ao lado de
# `SELETOR_MARCA_DO_FORNECEDOR` — a classe que `static/css/base.css` e
# `templates/contabilidade/balancete.html` já usam para o mesmo conceito.
SELETOR_TIMBRE_DO_ESCRITORIO = ".timbre-impressao"

# BL-314/BL-329: a função `visivelDeVerdade` (visibilidade REAL via motor de
# layout) passa a ser usada por DUAS sondas deste arquivo: SONDA (mídia de
# TELA, momento da verdade contábil) e SONDA_IMPRESSAO (mídia de IMPRESSÃO,
# marca do fornecedor/timbre do escritório — BL-329/BL-331) — e, desde a
# DL-028 fatia 1, também por `scripts/medir_identificacao_do_emitente.py`,
# fora deste arquivo. Por isso ela mora em `sonda_visibilidade.py` (módulo
# irmão), não aqui: duas sondas DENTRO deste arquivo já exigiam constante
# própria para não divergir (mesmo raciocínio de `fundoComposto`, comentado
# dentro de SONDA); um consumidor a mais tornaria uma cópia local ainda mais
# arriscada. `JS_VISIVEL_DE_VERDADE`, abaixo, é só uma referência ao texto
# importado — não um literal novo.
JS_VISIVEL_DE_VERDADE = sonda_visibilidade.JS_VISIVEL_DE_VERDADE


def _luminancia(componentes):
    def canal(v):
        v = v / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (canal(c) for c in componentes)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _rgb(texto):
    numeros = [float(n) for n in re.findall(r"[\d.]+", texto or "")]
    if len(numeros) < 3:
        return None
    if len(numeros) >= 4 and numeros[3] == 0:
        return None  # transparente: quem vale é o fundo de trás
    return numeros[:3]


def contraste(cor_a, cor_b):
    a, b = _luminancia(cor_a), _luminancia(cor_b)
    claro, escuro = max(a, b), min(a, b)
    return (claro + 0.05) / (escuro + 0.05)


def _limiar_de_contraste(tamanho_str, peso_str):
    """4,5:1 para texto normal, 3:1 para texto GRANDE (WCAG 1.4.3): >= 24px,
    ou >= 18,66px (~14pt) em negrito (peso >= 700). Extraído para função
    (BL-314) porque a amostra geral de `pares_de_cor` e a checagem
    dedicada do "momento da verdade" precisam da MESMA regra — reescrevê-la
    duas vezes é o jeito de uma delas divergir da outra sem ninguém notar
    (AGENTS.md §8)."""
    tamanho = float(re.findall(r"[\d.]+", tamanho_str)[0])
    peso = int(peso_str) if str(peso_str).isdigit() else 400
    grande = tamanho >= 24 or (tamanho >= 18.66 and peso >= 700)
    return 3.0 if grande else 4.5


SONDA = r"""
() =>{
    const resultado = {
        rolagem_horizontal: document.scrollingElement.scrollWidth > window.innerWidth + 1,
        largura_conteudo: document.scrollingElement.scrollWidth,
        linhas_tabela_total: document.querySelectorAll('table tbody tr').length,
        linhas_visiveis_no_primeiro_ecra: 0,
        tabular_nums: {com: 0, sem: 0, exemplos_sem: []},
        celulas_numericas: 0,
        tem_caption: document.querySelectorAll('table caption').length,
        tem_scope: document.querySelectorAll('th[scope]').length,
        th_total: document.querySelectorAll('th').length,
        sticky: document.querySelectorAll('*').length && [...document.querySelectorAll('thead th, tfoot td, tfoot th, thead')].some(
            e => getComputedStyle(e).position === 'sticky'),
        pares_de_cor: [],
        focaveis: 0,
        script_tags: document.querySelectorAll('script').length,
        script_inline_bytes: [...document.querySelectorAll('script')].reduce((s, e) => s + (e.textContent || '').length, 0),
    };

    // Linhas visíveis sem rolar: o critério de densidade.
    for (const tr of document.querySelectorAll('table tbody tr')) {
        const r = tr.getBoundingClientRect();
        if (r.top >= 0 && r.bottom <= window.innerHeight) resultado.linhas_visiveis_no_primeiro_ecra++;
    }

    // Tabulação de algarismos — CORRIGIDO depois de um erro meu (arquiteto):
    // a primeira versão lia o estilo da CÉLULA, mas o número costuma morar
    // num elemento-folha dentro dela (<span class="valor">). A célula dizia
    // "serifada, fvn normal" enquanto o número renderizava monoespaçado e
    // tabulado — 210 falsos negativos numa variante que estava certa.
    // Agora mede o elemento-folha e, mais importante, mede COMPORTAMENTO:
    // "111111" e "888888" têm de ter a mesma largura. Declaração de fonte não
    // prova tabulação; largura igual prova.
    const medirLargura = (estilo, txt) => {
        const sp = document.createElement('span');
        sp.style.cssText = estilo;
        sp.style.position = 'absolute';
        sp.style.visibility = 'hidden';
        sp.textContent = txt;
        document.body.appendChild(sp);
        const w = sp.getBoundingClientRect().width;
        sp.remove();
        return w;
    };
    const cacheTabulacao = new Map();
    for (const celula of document.querySelectorAll('td, th')) {
        const folhas = celula.children.length
            ? [...celula.querySelectorAll('*')].filter(e => !e.children.length)
            : [celula];
        for (const folha of folhas) {
            const texto = (folha.textContent || '').trim();
            if (!/\\d[\\d.]*,\\d{2}/.test(texto)) continue;
            resultado.celulas_numericas++;
            const s = getComputedStyle(folha);
            const chave = [s.fontFamily, s.fontVariantNumeric, s.fontFeatureSettings, s.fontSize].join('|');
            if (!cacheTabulacao.has(chave)) {
                const estilo = `font-family:${s.fontFamily};font-variant-numeric:${s.fontVariantNumeric};`
                    + `font-feature-settings:${s.fontFeatureSettings};font-size:${s.fontSize};`;
                cacheTabulacao.set(chave,
                    Math.abs(medirLargura(estilo, '111111') - medirLargura(estilo, '888888')) < 0.5);
            }
            if (cacheTabulacao.get(chave)) resultado.tabular_nums.com++;
            else {
                resultado.tabular_nums.sem++;
                if (resultado.tabular_nums.exemplos_sem.length < 4)
                    resultado.tabular_nums.exemplos_sem.push(texto.slice(0, 24) + ' @' + s.fontFamily.split(',')[0]);
            }
        }
    }

    // Fundo composto por trás de UM elemento, subindo a árvore até achar um
    // fundo opaco e compondo as camadas transparentes no caminho por ALFA.
    // Extraído para função (BL-314) porque agora dois lugares precisam da
    // MESMA composição — a amostra geral de contraste, abaixo, e a checagem
    // dedicada do "momento da verdade" mais adiante — e a correção do
    // terceiro defeito deste instrumento (parar no primeiro fundo NÃO
    // transparente tratava um branco de 6% de opacidade como cor final,
    // acusando 1,11:1 num par que tinha contraste alto de verdade) só vale
    // se as duas chamadas usarem o MESMO código, não uma cópia cada uma.
    const fundoComposto = (el) => {
        const camadas = [];
        let no = el;
        while (no) {
            const c = getComputedStyle(no).backgroundColor;
            const m = (c || '').match(/[\d.]+/g);
            if (m && m.length >= 3) {
                const alfa = m.length >= 4 ? parseFloat(m[3]) : 1;
                if (alfa > 0) {
                    camadas.push([+m[0], +m[1], +m[2], alfa]);
                    if (alfa >= 1) break;
                }
            }
            no = no.parentElement;
        }
        if (!camadas.length || camadas[camadas.length - 1][3] < 1) camadas.push([255, 255, 255, 1]);
        let composto = camadas[camadas.length - 1].slice(0, 3);
        for (let i = camadas.length - 2; i >= 0; i--) {
            const [r, g, b, a] = camadas[i];
            composto = [r * a + composto[0] * (1 - a),
                        g * a + composto[1] * (1 - a),
                        b * a + composto[2] * (1 - a)];
        }
        return `rgb(${composto.map(v => Math.round(v)).join(', ')})`;
    };

    // Amostra de pares texto/fundo, subindo até achar fundo opaco.
    // Só entra na amostra quem PINTA texto com a própria cor: elemento cujo
    // texto vem de um filho (um <li> que contém um <a>) herda uma cor que não
    // é usada em pixel nenhum. Foi o quarto defeito deste instrumento: ele
    // acusava 1,19:1 num <li> cuja única "cor de texto" jamais é desenhada.
    const temTextoProprio = e => [...e.childNodes].some(
        n => n.nodeType === 3 && (n.textContent || '').trim().length > 0);
    const amostra = [...document.querySelectorAll(
        'td, th, p, span, a, button, label, h1, h2, h3, li, small, legend, caption')]
        .filter(e => temTextoProprio(e) && e.getClientRects().length);
    const vistos = new Set();
    for (const el of amostra) {
        const estilo = getComputedStyle(el);
        const fundo = fundoComposto(el);
        const chave = estilo.color + '|' + fundo + '|' + estilo.fontSize + '|' + estilo.fontWeight;
        if (vistos.has(chave)) continue;
        vistos.add(chave);
        const inerte = el.closest('[disabled], [aria-disabled="true"], fieldset[disabled]') !== null
            || el.disabled === true;
        resultado.pares_de_cor.push({
            cor: estilo.color, fundo, tamanho: estilo.fontSize, peso: estilo.fontWeight,
            tag: el.tagName.toLowerCase(), texto: (el.textContent || '').trim().slice(0, 30),
            inerte,
        });
    }

    resultado.focaveis = document.querySelectorAll(
        'a[href], button, input, select, textarea, [tabindex]:not([tabindex="-1"])').length;

    // BL-314 (M5 da auditoria DL-026, rodada 3): visibilidade REAL do
    // "momento da verdade" contábil — não uma lista de propriedades CSS
    // suspeitas (display/visibility/opacity), e sim três medições GERAIS
    // que o motor de layout do navegador já faz por conta própria:
    //
    // 1. `Element.checkVisibility({checkOpacity, checkVisibilityCSS})` —
    //    a própria API do navegador para "este elemento está excluído da
    //    árvore visual por display/visibility/content-visibility/opacidade
    //    (do elemento OU de qualquer ancestral)". Delega a pergunta a quem
    //    já resolve cascata e herança corretamente — não a este script.
    // 2. `getBoundingClientRect()` tem ÁREA (largura E altura > 0) — pega
    //    técnicas que `checkVisibility` não cobre por definição:
    //    `width/height: 0`, `transform: scale(0)`. MEDIDO neste projeto
    //    (não presumido): as duas passam por `checkVisibility` (que
    //    devolve `true`) e são pegas SÓ pela área.
    // 3. O retângulo é ALCANÇÁVEL por rolagem da página — pega
    //    posicionamento fora da tela (`position: absolute; left: -9999px`),
    //    que não muda `checkVisibility` nem zera a área.
    //
    // As três, JUNTAS, cobrem `display: none`, `visibility: hidden`,
    // `opacity: 0` e "fora da tela" sem este script precisar SABER que
    // essas são as técnicas — é o requisito ("qualquer forma de esconder"),
    // não a lista de quatro exemplos.
    //
    // Limite MEDIDO e declarado, não descoberto por auditoria depois:
    // `clip-path: inset(100%)` NÃO é pego por nenhuma das três — o
    // elemento continua com `checkVisibility() === true` e a mesma área,
    // porque `clip-path` recorta o PIXEL pintado, não a caixa de layout
    // que `getBoundingClientRect` mede. Um texto ilegível por
    // `color: transparent` (mesma cor do fundo) também não é pego aqui —
    // mas ESSE caso cai no cálculo de CONTRASTE abaixo (razão ~1:1 contra
    // o próprio fundo), então as duas medições juntas (visibilidade +
    // contraste) fecham mais do que qualquer uma sozinha.
    // Sem suporte à API (navegador antigo): a régua de retângulo decide
    // sozinha, e o resultado fica marcado como tal (nunca finge certeza que
    // não tem). Definição de `visivelDeVerdade` interpolada de
    // JS_VISIVEL_DE_VERDADE (Python, acima) — reaproveitada por
    // SONDA_IMPRESSAO (BL-329), não retypada aqui.
    __JS_VISIVEL_DE_VERDADE__

    resultado.momento_da_verdade = __MOMENTO_DA_VERDADE_SELETORES_JSON__.map(seletor => {
        const el = document.querySelector(seletor);
        if (!el) return {seletor, encontrado: false};
        const visibilidade = visivelDeVerdade(el);
        const item = Object.assign({seletor, encontrado: true}, visibilidade);
        if (visibilidade.visivel) {
            const estilo = getComputedStyle(el);
            item.cor = estilo.color;
            item.fundo = fundoComposto(el);
            item.tamanho = estilo.fontSize;
            item.peso = estilo.fontWeight;
            item.texto = (el.textContent || '').trim().slice(0, 60);
        }
        return item;
    });

    return resultado;
}
"""

# A lista de seletores só existe em `MOMENTO_DA_VERDADE_SELETORES` (Python,
# topo do arquivo) — substituída aqui por SERIALIZAÇÃO, não retypada dentro
# da string JS. Duas listas manuais da mesma coisa divergem assim que
# alguém atualiza uma (BL-296, BL-325 e vizinhos são a família inteira
# desse defeito neste projeto).
SONDA = SONDA.replace(
    "__MOMENTO_DA_VERDADE_SELETORES_JSON__", json.dumps(MOMENTO_DA_VERDADE_SELETORES)
)
SONDA = SONDA.replace("__JS_VISIVEL_DE_VERDADE__", JS_VISIVEL_DE_VERDADE)

# BL-331: os DOIS elementos do critério 9 da DL-026 — a marca do
# FORNECEDOR (que precisa SAIR do papel) e o timbre do ESCRITÓRIO (que
# precisa ENTRAR) — nomeados aqui, não retypados dentro da sonda JS
# (SELETORES_DE_IMPRESSAO_JSON, abaixo, serializa este dicionário do
# mesmo jeito que MOMENTO_DA_VERDADE_SELETORES_JSON já faz para a SONDA
# principal — duas listas manuais da mesma coisa divergem assim que
# alguém atualiza uma, BL-296/BL-325).
SELETORES_DE_IMPRESSAO = {
    "marca_do_fornecedor": SELETOR_MARCA_DO_FORNECEDOR,
    "timbre_do_escritorio": SELETOR_TIMBRE_DO_ESCRITORIO,
}

# BL-329/BL-331: sonda DEDICADA, avaliada sob `page.emulate_media(media=
# "print")` (ver `julgar_arquivo`) — pergunta, para CADA seletor de
# `SELETORES_DE_IMPRESSAO`, se o elemento continua visível quando a
# página é IMPRESSA. Montada por `sonda_visibilidade.js_sonda_impressao`
# (DL-028 fatia 1: antes um literal só deste arquivo, agora a mesma
# montagem que `scripts/medir_identificacao_do_emitente.py` usa para o
# produto real) — reaproveita `visivelDeVerdade`, não uma cópia JS
# separada. Deliberadamente pequena: não reavalia densidade, contraste nem
# o resto da sonda principal, que não fazem sentido sob mídia de impressão
# (a paginação real só existe em `page.pdf()` — ver
# `scripts/medir_impressao.py`, BL-337, fora do escopo deste juiz).
SONDA_IMPRESSAO = sonda_visibilidade.js_sonda_impressao(SELETORES_DE_IMPRESSAO)


def externo(url):
    return url.startswith("http://") or url.startswith("https://")


def julgar_arquivo(pagina, caminho, largura, altura):
    requisicoes_externas = []
    pagina.on("request", lambda r: externo(r.url) and requisicoes_externas.append(r.url))
    pagina.set_viewport_size({"width": largura, "height": altura})
    pagina.goto(caminho.as_uri(), wait_until="networkidle")
    dados = pagina.evaluate(SONDA)
    dados["requisicoes_externas"] = requisicoes_externas

    piores = []
    isentos = 0
    for par in dados.pop("pares_de_cor"):
        cor, fundo = _rgb(par["cor"]), _rgb(par["fundo"])
        if not cor or not fundo:
            continue
        razao = contraste(cor, fundo)
        if par.pop("inerte", False):
            # Controle desabilitado é isento pela WCAG 1.4.3. Isento é contado,
            # não escondido: a variante que abusar de "desabilitado" para
            # escapar do contraste aparece neste número.
            isentos += 1
            continue
        minimo = _limiar_de_contraste(par["tamanho"], par["peso"])
        if razao < minimo:
            piores.append({**par, "contraste": round(razao, 2), "minimo": minimo})
    dados["contrastes_reprovados"] = sorted(piores, key=lambda p: p["contraste"])[:8]
    dados["contrastes_isentos_por_desabilitado"] = isentos

    # BL-314: para cada elemento do "momento da verdade" (contábil: veredito
    # de fechamento do lançamento e faixa do balancete — ver
    # MOMENTO_DA_VERDADE_SELETORES), acrescenta o veredito de CONTRASTE ao
    # que a sonda já mediu de VISIBILIDADE. `contraste_ok` fica `None`
    # quando a pergunta não se aplica — elemento ausente nesta variante, ou
    # invisível (visibilidade É o achado; contraste de algo que não se vê
    # não significa nada) —, nunca `False` por omissão: um `None`
    # silencioso não pode virar "reprovado" nem "aprovado" por acidente de
    # leitura de quem consome este relatório.
    for item in dados.get("momento_da_verdade", []):
        if not item.get("encontrado") or not item.get("visivel"):
            item["contraste_ok"] = None
            continue
        cor, fundo = _rgb(item.get("cor")), _rgb(item.get("fundo"))
        if not cor or not fundo:
            item["contraste_ok"] = None
            continue
        razao = contraste(cor, fundo)
        minimo = _limiar_de_contraste(item["tamanho"], item["peso"])
        item["contraste"] = round(razao, 2)
        item["contraste_minimo"] = minimo
        item["contraste_ok"] = razao >= minimo

    # Foco visível: mede o primeiro focável de verdade, comparando o estilo
    # calculado antes e depois do foco. Sem isso, "tem :focus-visible no CSS"
    # seria leitura estática, não medição.
    dados["foco_muda_estilo"] = pagina.evaluate("""
        () => {
            const alvo = document.querySelector('a[href], button, input, select');
            if (!alvo) return null;
            const antes = getComputedStyle(alvo);
            const retrato = a => [a.outlineStyle, a.outlineWidth, a.outlineColor,
                                  a.boxShadow, a.borderColor, a.backgroundColor].join('|');
            const r1 = retrato(antes);
            alvo.focus();
            const r2 = retrato(getComputedStyle(alvo));
            return r1 !== r2;
        }
    """)

    # BL-329/BL-331: sob mídia de IMPRESSÃO (`page.emulate_media`), a marca
    # do FORNECEDOR continua visível (não deveria) e o timbre do ESCRITÓRIO
    # continua visível (deveria)? Esta é a MEDIDA QUE A CI NÃO PODE DAR — a
    # suíte `pytest` (test_bl329_marca_fora_do_papel.py e
    # test_bl331_timbre_do_escritorio_no_papel.py) já cobre a metade que dá
    # para provar sem navegador (cascata CSS simulada, `display: none`
    # efetivo); esta metade responde à pergunta que só um motor de layout
    # real decide: o contador VÊ a marca/o timbre no papel? `visivelDeVerdade`
    # (a MESMA função do momento da verdade contábil, acima) já cobre
    # `display`, `visibility` e posicionamento fora da tela sem enumerar
    # técnicas — ver o comentário completo dela, mais acima nesta sonda, e a
    # decisão registrada na docstring do módulo de teste sobre por que a
    # guarda de CI é mais estrita (exige `display: none` especificamente,
    # não "invisível por qualquer meio").
    pagina.emulate_media(media="print")
    impressao = pagina.evaluate(SONDA_IMPRESSAO)
    # Nomes de chave PRESERVADOS (não um único `dados["impressao"]` novo):
    # quem já consome o relatório deste juiz procurando
    # "marca_do_fornecedor_na_impressao" continua encontrando-a.
    dados["marca_do_fornecedor_na_impressao"] = impressao["marca_do_fornecedor"]
    dados["timbre_do_escritorio_na_impressao"] = impressao["timbre_do_escritorio"]
    # Volta à mídia de TELA antes de qualquer outra medição/captura: sem
    # isto, as capturas de imagem (mais abaixo, em `main`) e o teste de foco
    # acima sairiam avaliados sob impressão, misturando as duas garantias
    # numa só — exatamente o erro de redação que o BL-314 corrigiu (contar
    # como uma camada o que eram duas).
    pagina.emulate_media(media=None)

    # Desfaz o foco que a sonda acabou de aplicar: sem isso, a captura sai com
    # o atalho "Pular para o conteúdo" por cima da navegação, e quem olhasse a
    # imagem julgaria um defeito que o instrumento criou.
    pagina.evaluate("() => document.activeElement && document.activeElement.blur()")
    return dados


def main(pastas):
    relatorio = {}
    with sync_playwright() as p:
        # DL-028 fatia 1: sem caminho fixo — ver a docstring de
        # `lancar_chromium` (variável de ambiente ou descoberta nativa do
        # Playwright). `NavegadorIndisponivel` é FALHA DE INFRAESTRUTURA,
        # reportada com `sys.exit` e mensagem própria, nunca confundida com
        # um veredito de variante (BL-356).
        try:
            navegador = sonda_visibilidade.lancar_chromium(p)
        except sonda_visibilidade.NavegadorIndisponivel as erro:
            sys.exit(f"Recusado: {erro}")
        for pasta in pastas:
            pasta = Path(pasta).resolve()
            nome = pasta.name
            relatorio[nome] = {}
            saida = pasta / "capturas"
            saida.mkdir(exist_ok=True)
            for html in sorted(pasta.glob("*.html")):
                relatorio[nome][html.name] = {}
                for largura, altura in LARGURAS:
                    contexto = navegador.new_context(
                        viewport={"width": largura, "height": altura},
                        device_scale_factor=1,
                    )
                    pagina = contexto.new_page()
                    try:
                        dados = julgar_arquivo(pagina, html, largura, altura)
                        pagina.screenshot(
                            path=str(saida / f"{html.stem}-{largura}.png"), full_page=False
                        )
                        pagina.screenshot(
                            path=str(saida / f"{html.stem}-{largura}-inteira.png"), full_page=True
                        )
                    except Exception as erro:  # noqa: BLE001 - relatar, não abortar o juiz
                        dados = {"erro": f"{type(erro).__name__}: {erro}"}
                    relatorio[nome][html.name][f"{largura}x{altura}"] = dados
                    contexto.close()
        navegador.close()
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
