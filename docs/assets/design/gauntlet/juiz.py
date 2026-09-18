"""Juiz mecânico do gauntlet de design do DataLedger.

Ele NÃO julga beleza. Ele mede o que a régua do brief define como
eliminatório ou contável, para que a parte subjetiva do julgamento aconteça
depois — e sobre variantes que já passaram no que é objetivo.

Rode com o Python do sistema (tem playwright):
    /usr/bin/python3 juiz.py <pasta-da-variante> [...]
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
LARGURAS = [(1280, 800), (1920, 1080)]


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
        // CORRIGIDO depois do terceiro defeito deste instrumento: a versão
        // anterior parava no primeiro fundo que não fosse totalmente
        // transparente — e tomava um branco de 6% de opacidade como se fosse
        // a cor final. Resultado: acusou 1,11:1 num link creme sobre verde
        // escuro, que na verdade tem contraste alto (conferido pixel a pixel
        // na captura). Agora as camadas são COMPOSTAS por alfa, de cima para
        // baixo, até chegar numa opaca.
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
        const fundo = `rgb(${composto.map(v => Math.round(v)).join(', ')})`;
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
    return resultado;
}
"""


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
        tamanho = float(re.findall(r"[\d.]+", par["tamanho"])[0])
        peso = int(par["peso"]) if str(par["peso"]).isdigit() else 400
        grande = tamanho >= 24 or (tamanho >= 18.66 and peso >= 700)
        minimo = 3.0 if grande else 4.5
        if razao < minimo:
            piores.append({**par, "contraste": round(razao, 2), "minimo": minimo})
    dados["contrastes_reprovados"] = sorted(piores, key=lambda p: p["contraste"])[:8]
    dados["contrastes_isentos_por_desabilitado"] = isentos

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

    # Desfaz o foco que a sonda acabou de aplicar: sem isso, a captura sai com
    # o atalho "Pular para o conteúdo" por cima da navegação, e quem olhasse a
    # imagem julgaria um defeito que o instrumento criou.
    pagina.evaluate("() => document.activeElement && document.activeElement.blur()")
    return dados


def main(pastas):
    relatorio = {}
    with sync_playwright() as p:
        navegador = p.chromium.launch(executable_path=CHROMIUM)
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
