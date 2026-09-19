"""Vazamento de texto nas ilustrações SVG de `docs/assets/` — achado do Fred
em 2026-09-18, ao abrir a página inicial do GitHub e ver "nomes saindo de
dentro dos quadrados" no `hero.svg`.

**A causa raiz não é "texto comprido".** Os SVG declaram
``font-family="Inter,Segoe UI,Arial,sans-serif"``, e o GitHub renderiza o
SVG na máquina de QUEM VISITA, com a fonte que aquela máquina tiver. O Fred
mediu a MESMA frase ("Contabilidade básica") em quatro fontes e achou um
espalhamento de 30%: Inter e Segoe UI em 153,1px, Arial (via Liberation
Sans, a substituta metricamente compatível) em 170,6px, e DejaVu Sans — o
padrão em muito Linux sem as três primeiras instaladas — em 199,9px. **Não
existe "cabe" sem dizer em qual fonte.**

## A escolha de mecanismo, e por que ela é esta (opção "a" do pedido)

O pedido oferecia três caminhos: (a) medir de verdade e pular quando não
houver Chromium, deixando claro que isso não protege a integração contínua
sozinho; (b) aproximação estática com tabela de largura de glifo por fonte,
com margem de erro declarada; (c) outra, justificada.

Escolhida **(a)**, e não por preguiça — por **precedente já provado neste
mesmo repositório**. `apps/contabilidade/tests/test_dl017_rodada2_frontend.py`
resolveu exatamente este dilema para medir CSS calculado (R2-6/R2-9) e
documentou, em detalhe rastreável (BL-119, R5-1/BL-140, R6-1/BL-195), por
que a alternativa (b) — aproximar sem navegador — não bastava: largura de
glifo depende de kerning, hinting, peso da fonte e substituição do sistema,
e uma tabela estática ficaria errada silenciosamente na primeira mudança de
fonte do sistema operacional do runner. O mesmo argumento vale aqui, palavra
por palavra: medir largura de texto renderizado é exatamente o problema que
motivou aquele mecanismo, e reescrever pior o que já existe provado seria
o erro oposto de "não aproveitar padrão existente" (`AGENTS.md`, §8).

**O que ESTE arquivo reaproveita e o que ele NÃO reaproveita.** As funções
`_caminho_chromium`, `_chromium_funciona`, `_perfil_de_navegador_descartavel`
e `_pular_se_chromium_nao_funcional` abaixo são a MESMA lógica (adaptada) do
arquivo citado — não um `import` cruzado (aquele módulo é de outro papel,
`apps/contabilidade/**`, fora do que esta etapa autoriza tocar; e importar
função de nome `_privado` de outro módulo de teste seria acoplamento frágil
de qualquer forma). O que NÃO foi copiado é a bateria adversarial completa
de testes-meta daquele arquivo (BL-129, BL-140, BL-195 — dezenas de casos
provando que o PRÓPRIO mecanismo de pular resiste a mutação). Aquele
mecanismo já está provado, neste mesmo repositório, com esse nível de
rigor; duplicá-lo aqui seria o mesmo código sendo auditado duas vezes sem
ganho. Este arquivo mantém só um teste estrutural + um comportamental do
gate (abaixo) como rede mínima, e concentra o rigor de controle
positivo/negativo — a exigência real desta tarefa — no que é NOVO aqui: o
detector de vazamento de SVG.

## O que isto prova, e o que isto NÃO prova

Quando o Chromium funciona e a fonte pedida está genuinamente instalada
(verificado por comportamento — ver `_fonte_esta_disponivel` — nunca
presumido), os testes de efeito medem de verdade e reprovam a suíte se
algum texto vazar. **Isto protege a máquina que tem Chromium funcional e a
fonte testada.** Não protege, e não finge proteger, uma execução sem
Chromium: aí os testes de efeito PULAM, com `pytest.skip` explicando a
causa real medida (não um texto fixo genérico) — nunca em silêncio (a
lição da BL-275 desta mesma etapa: "guarda que finge cobrir é pior que
guarda ausente"). Rodando `pytest -rs`, cada pulo aparece na lista com o
motivo.

Neste projeto, hoje, o runner do GitHub Actions traz `google-chrome` sem
instalação adicional (`.github/workflows/backend.yml`, comentário da
BL-119) e imagens Ubuntu trazem DejaVu Sans e Liberation Sans no conjunto
básico de fontes — por isso a expectativa realista é que os testes do pior
caso (DejaVu Sans) e do caso Arial-equivalente (Liberation Sans) **rodem de
verdade na CI**, e não apenas na máquina de quem tem Chromium. Isto é
expectativa, não promessa: se um runner futuro não tiver uma dessas fontes,
o teste correspondente pula com o motivo — não finge.

## Três detectores, um só instrumento

1. **Vazamento da CAIXA** — o pedido original: texto cuja borda direita
   passa da borda direita do menor `<rect>` que contém o seu CENTRO, com
   folga menor que `max(8px, 6% da largura da caixa)`. Retângulo do
   fundo/borda do próprio canvas (largura ≈ a largura do SVG) não conta
   como "caixa" — ninguém pediu para o texto caber dentro da moldura
   inteira, só dentro dos cartões e emblemas internos.
2. **Vazamento do CANVAS** — achado ao instrumentar a verificação, não
   pedido explicitamente, e mais grave que o primeiro: um elemento cuja
   caixa de renderização sai da área visível do próprio SVG fica cortado
   (o `contributing.svg` tinha um emblema inteiro, "pronto para revisão",
   17px abaixo da borda inferior do canvas — não "apertado", INVISÍVEL).
3. **COLISÃO com retângulo alheio** — também achado, não pedido: texto que
   não está preso a nenhuma caixa pequena (por isso o detector 1 não o
   vê) mas cuja renderização, numa fonte mais larga, invade um retângulo
   de OUTRO elemento sem estar contido nele (nesting normal — caixa
   pequena dentro de painel maior — não conta; só invasão PARCIAL conta).
   Foi assim que o título do `hero.svg` ("Contabilidade brasileira,") foi
   flagrado colidindo com o painel do navegador mockup em DejaVu Sans, sem
   nunca ter estado "dentro" de retângulo nenhum.

Os três juntos são o que "nenhum texto vaza" significa de verdade — medir
só o primeiro teria deixado os outros dois passar batido, exatamente como
passaram batido na primeira leitura visual do Fred.
"""

import contextlib
import inspect
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
DOCS_ASSETS = RAIZ / "docs" / "assets"

# Folga mínima exigida pelo pedido: 8px OU 6% da largura da caixa, o que for
# maior — "folga de 1px não é aprovação, é sorte".
MARGEM_MINIMA_PX = 8
MARGEM_MINIMA_PROPORCIONAL = 0.06


def _svgs_com_texto_em_caixa():
    """Todo `.svg` de `docs/assets/` (recursivo — cobre `docs/assets/telas/`
    se um dia existir SVG lá) que tenha `<text` E `<rect` — a combinação que
    o pedido descreve ("texto dentro de retângulo"). Descoberto por
    varredura, não hardcoded: um quinto arquivo com o mesmo padrão entra
    nesta suíte sem precisar editar este arquivo.
    """
    achados = []
    for caminho in sorted(DOCS_ASSETS.rglob("*.svg")):
        texto = caminho.read_text(encoding="utf-8")
        if "<text" in texto and "<rect" in texto:
            achados.append(caminho)
    return achados


ARQUIVOS_SVG = _svgs_com_texto_em_caixa()

# A pilha declarada nos quatro SVG, na ordem, mais o pior caso que o Fred
# mediu e que NÃO está na pilha (é o padrão do sistema quando nenhuma das
# três primeiras existe). "como_declarado" (sem forçar nada) mede o que a
# pilha real resolve NESTA máquina — sempre roda, nunca pula por fonte
# ausente, porque não força nome nenhum. Os outros quatro forçam um nome
# específico e só rodam se ele existir de verdade (ver
# `_fonte_esta_disponivel`).
MODOS_DE_FONTE = ["como_declarado", "Inter", "Segoe UI", "Arial", "Liberation Sans", "DejaVu Sans"]

# ---------------------------------------------------------------------------
# Capacidade do navegador — mesma lógica de
# apps/contabilidade/tests/test_dl017_rodada2_frontend.py (_caminho_chromium /
# _chromium_funciona / _perfil_de_navegador_descartavel /
# _pular_se_chromium_nao_funcional), adaptada. Ver o docstring do módulo para
# o motivo de não importar aquele arquivo nem duplicar a bateria adversarial
# completa dele.
# ---------------------------------------------------------------------------


def _caminho_chromium():
    """Localiza um binário de Chromium/Chrome por caminho fixo conhecido ou
    pelo `PATH`. `DATALEDGER_TESTE_CHROMIUM_CAMINHO`, se definida, FORÇA o
    caminho devolvido (string vazia força "nenhum encontrado") — hook só de
    verificação desta suíte, nunca lido por código de produção.
    """
    if "DATALEDGER_TESTE_CHROMIUM_CAMINHO" in os.environ:
        forcado = os.environ["DATALEDGER_TESTE_CHROMIUM_CAMINHO"]
        return forcado or None
    candidatos = [
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).exists():
            return candidato
    return None


def _descartar_caminho_temporario(caminho):
    """Apaga um arquivo OU diretório temporário sem NUNCA levantar — a falha
    de LIMPEZA de um recurso de ambiente não pode reprovar a suíte nem ser
    confundida com "o navegador não funciona" (lição da R6-1/BL-195 do
    arquivo irmão: `ENOTEMPTY` do descarte concorrente do perfil do Chrome
    escapava como se fosse falha de execução)."""
    try:
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            Path(caminho).unlink(missing_ok=True)
    except OSError:
        pass


@contextlib.contextmanager
def _perfil_de_navegador_descartavel():
    """`--user-data-dir` próprio e descartável — nunca um perfil
    compartilhado, que pode estar travado por outro processo desta sessão."""
    perfil = tempfile.mkdtemp(prefix="dataledger-perfil-svg-")
    try:
        yield perfil
    finally:
        _descartar_caminho_temporario(perfil)


_TIMEOUT_MEDICAO_S = 30

_FLAGS_CHROME_HEADLESS = [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--disable-dev-shm-usage",
]


def _chromium_funciona(caminho, *, timeout=_TIMEOUT_MEDICAO_S):
    """Confirma que o binário RENDERIZA de verdade um arquivo local — não só
    que existe. Usa `file://` sobre um arquivo temporário real (nunca uma
    URL `data:`), porque é exatamente esse caminho que quebra sob um
    Chromium empacotado como snap (`/tmp` privado, não enxerga o arquivo) —
    achado documentado em detalhe no arquivo irmão (R5-1/BL-140). Qualquer
    falha aqui — timeout, código de saída, exceção do sistema operacional,
    marca ausente no DOM — vira `False`, nunca uma exceção que reprovaria a
    suíte."""
    global _DIAGNOSTICO_CHROMIUM
    if not caminho:
        _DIAGNOSTICO_CHROMIUM = "nenhum candidato de caminho encontrado (nem fixo, nem no PATH)"
        return False
    marca = "sessao-de-verificacao-svg"
    caminho_html = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".html", delete=False, encoding="utf-8"
        ) as arquivo:
            arquivo.write(f"<title>{marca}</title>")
            caminho_html = arquivo.name
        with _perfil_de_navegador_descartavel() as perfil:
            resultado = subprocess.run(
                [
                    caminho,
                    *_FLAGS_CHROME_HEADLESS,
                    f"--user-data-dir={perfil}",
                    "--dump-dom",
                    f"file://{caminho_html}",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    except subprocess.TimeoutExpired:
        _DIAGNOSTICO_CHROMIUM = f"{caminho}: timeout de {timeout}s"
        return False
    except OSError as exc:
        _DIAGNOSTICO_CHROMIUM = f"{caminho}: erro de sistema operacional ao executar: {exc!r}"
        return False
    finally:
        if caminho_html is not None:
            _descartar_caminho_temporario(caminho_html)
    if resultado.returncode != 0:
        _DIAGNOSTICO_CHROMIUM = (
            f"{caminho}: saiu com código {resultado.returncode}; stderr={resultado.stderr[:500]!r}"
        )
        return False
    if marca not in resultado.stdout:
        _DIAGNOSTICO_CHROMIUM = (
            f"{caminho}: rodou (código 0) mas não devolveu a marca esperada no DOM; "
            f"stdout={resultado.stdout[:300]!r}"
        )
        return False
    _DIAGNOSTICO_CHROMIUM = None
    return True


_DIAGNOSTICO_CHROMIUM = None
_CHROMIUM = _caminho_chromium()
_CHROMIUM_FUNCIONAL = _chromium_funciona(_CHROMIUM)

_MOTIVO_DO_PULO = (
    "Medir se texto de SVG vaza da caixa em fontes diferentes exige um "
    "navegador REAL e FUNCIONAL — sem ele, este teste NÃO protege esta "
    "execução da integração contínua, só a máquina de quem tiver Chromium "
    "(ver o docstring do módulo)."
)


def _pular_se_chromium_nao_funcional():
    """Ponto ÚNICO que decide se um teste de EFEITO roda ou pula — chamado
    no CORPO do teste, nunca em `@pytest.mark.skipif` (que travaria a
    condição na importação do módulo e não seria testável em tempo de
    execução — a lição da A4/BL-129 do arquivo irmão).
    """
    if not _CHROMIUM_FUNCIONAL:
        pytest.skip(
            f"{_MOTIVO_DO_PULO} Binário tentado: {_CHROMIUM!r}. "
            f"Diagnóstico: {_DIAGNOSTICO_CHROMIUM}"
        )


def test_gate_de_navegador_deriva_de_chromium_funcional_nao_de_chromium():
    """ESTRUTURAL: `_pular_se_chromium_nao_funcional` decide por
    `_CHROMIUM_FUNCIONAL` (capacidade medida), nunca por `_CHROMIUM is None`
    (mera presença do binário) — a troca exata que causou a CI cair com
    `SIGKILL` em vez de pular, no achado que originou este mecanismo no
    arquivo irmão."""
    codigo_fonte = inspect.getsource(_pular_se_chromium_nao_funcional)
    assert "_CHROMIUM_FUNCIONAL" in codigo_fonte
    assert "_CHROMIUM is None" not in codigo_fonte
    assert "_CHROMIUM is not None" not in codigo_fonte


def test_pular_dispara_quando_chromium_nao_funcional(monkeypatch):
    import apps.core.tests.test_dl024_svg_texto_nao_vaza_da_caixa as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM_FUNCIONAL", False)
    with pytest.raises(pytest.skip.Exception):
        este_modulo._pular_se_chromium_nao_funcional()


def test_nao_pular_quando_chromium_funcional(monkeypatch):
    import apps.core.tests.test_dl024_svg_texto_nao_vaza_da_caixa as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM_FUNCIONAL", True)
    este_modulo._pular_se_chromium_nao_funcional()  # não deve levantar nem pular


# ---------------------------------------------------------------------------
# O instrumento: renderiza um SVG (opcionalmente forçando uma fonte),
# devolve vazamentos de caixa, vazamentos de canvas e colisões.
# ---------------------------------------------------------------------------

# `local('<fonte>')` só resolve se a fonte estiver REALMENTE instalada no
# sistema — ao contrário de simplesmente escrever `font-family: '<fonte>'`
# (que a cascata do CSS substitui em SILÊNCIO pela próxima da lista, e é
# EXATAMENTE esse silêncio que causou o defeito original). Confirmado por
# medição antes de usar (não presumido): `document.fonts.check()` sozinho
# devolveu `true` até para um nome de fonte INVENTADO nesta máquina — a
# checagem "óbvia" mente. `@font-face { src: local(...) }` seguido de
# `document.fonts.load(...)` é o único caminho que devolveu `false` para a
# fonte inventada E para fontes genuinamente ausentes (Inter/Segoe UI nesta
# máquina) enquanto devolvia `true` para as que existem de verdade (DejaVu
# Sans, Liberation Sans) — os seis casos foram medidos antes desta escolha
# entrar no arquivo.
_PROBE_JS = r"""
(async function() {
  var FAMILIA = __FAMILIA_JSON__;
  var FORCAR = __FORCAR_JSON__;
  var MARGEM_MINIMA_PX = __MARGEM_PX__;
  var MARGEM_MINIMA_PROPORCIONAL = __MARGEM_PROP__;

  var disponivel = true;
  if (FORCAR) {
    var sonda = document.createElement('style');
    sonda.textContent = "@font-face { font-family: 'sonda-svg-vazamento'; " +
      "src: local('" + FAMILIA + "'); }";
    document.head.appendChild(sonda);
    try {
      var carregadas = await document.fonts.load("16px 'sonda-svg-vazamento'");
      disponivel = carregadas.length > 0;
    } catch (e) { disponivel = false; }
  }

  var resultado = {
    fonte_disponivel: disponivel, vazamentos_caixa: [], vazamentos_canvas: [], colisoes: []
  };

  if (disponivel) {
    if (FORCAR) {
      var forca = document.createElement('style');
      forca.textContent = "svg text { font-family: '" + FAMILIA + "' !important; }";
      document.head.appendChild(forca);
    }

    var svg = document.querySelector('svg');
    var svgBox = svg.getBoundingClientRect();
    var W = svg.viewBox.baseVal.width || svgBox.width;
    var H = svg.viewBox.baseVal.height || svgBox.height;

    var rects = [];
    svg.querySelectorAll('rect').forEach(function(r) {
      var bb = r.getBoundingClientRect();
      if (bb.width > 20 && bb.height > 12) rects.push(bb);
    });

    svg.querySelectorAll('text').forEach(function(t) {
      var tb = t.getBoundingClientRect();
      if (!tb.width) return;
      var texto = t.textContent.trim().slice(0, 60);

      // 1) Vazamento do próprio CANVAS — mais grave que vazar de uma caixa
      // interna: fica cortado/invisível na maioria dos motores de
      // renderização (overflow implícito da raiz de um documento SVG
      // autônomo).
      var esq = tb.left - svgBox.left, topo = tb.top - svgBox.top;
      var dir = (svgBox.left + W) - tb.right, baixo = (svgBox.top + H) - tb.bottom;
      if (esq < -0.5 || topo < -0.5 || dir < -0.5 || baixo < -0.5) {
        resultado.vazamentos_canvas.push({
          texto: texto, esq: +esq.toFixed(1), topo: +topo.toFixed(1),
          dir: +dir.toFixed(1), baixo: +baixo.toFixed(1)
        });
      }

      // 2) Vazamento da CAIXA dona — o menor <rect> que contém o CENTRO do
      // texto, excluindo o fundo/borda do próprio canvas (largura ~= W).
      var cx = tb.left + tb.width / 2, cy = tb.top + tb.height / 2;
      var dono = null, area = Infinity;
      rects.forEach(function(rb) {
        var rw = rb.width * rb.height;
        if (cx >= rb.left && cx <= rb.right && cy >= rb.top && cy <= rb.bottom && rw < area) {
          dono = rb; area = rw;
        }
      });
      if (dono && dono.width < W - 5) {
        var folga = dono.right - tb.right;
        var exigida = Math.max(MARGEM_MINIMA_PX, MARGEM_MINIMA_PROPORCIONAL * dono.width);
        if (folga < exigida) {
          resultado.vazamentos_caixa.push({
            texto: texto, folga: +folga.toFixed(1), exigida: +exigida.toFixed(1),
            largura: +tb.width.toFixed(1), caixa: +dono.width.toFixed(1)
          });
        }
      }

      // 3) Colisão com retângulo ALHEIO — texto que não mora em nenhuma
      // caixa pequena (por isso o item 2 não o vê) mas invade PARCIALMENTE
      // um retângulo de outro elemento. Conter o texto INTEIRO é
      // aninhamento normal (cartão pequeno dentro de painel maior) e não
      // conta; só invasão parcial conta.
      rects.forEach(function(rb) {
        if (rb === dono) return;
        if (rb.width >= W - 5) return;
        var contido = tb.left >= rb.left - 0.5 && tb.right <= rb.right + 0.5 &&
                      tb.top >= rb.top - 0.5 && tb.bottom <= rb.bottom + 0.5;
        if (contido) return;
        var invade = tb.left < rb.right && tb.right > rb.left &&
                     tb.top < rb.bottom && tb.bottom > rb.top;
        if (invade) {
          resultado.colisoes.push({
            texto: texto, rect_w: Math.round(rb.width), rect_h: Math.round(rb.height)
          });
        }
      });
    });
  }

  document.title = JSON.stringify(resultado);
})();
"""


def _medir_svg(caminho_svg_ou_html, *, familia=None, timeout=_TIMEOUT_MEDICAO_S):
    """Renderiza `caminho_svg_ou_html` (um arquivo `.svg` de verdade, ou um
    corpo HTML sintético para os controles) num Chromium headless.

    Se `familia` for `None`, mede a pilha DECLARADA no próprio SVG, sem
    forçar nada (sempre roda). Se `familia` for um nome, verifica primeiro
    se essa fonte está REALMENTE instalada (`local()`) e só mede se
    estiver — caso contrário devolve `{"fonte_disponivel": False, ...}` e
    quem chama decide pular com o motivo.

    Qualquer falha do NAVEGADOR (timeout, erro de sistema operacional,
    `<title>` ausente ou que não é JSON) leva a `pytest.skip` — nunca
    reprova a suíte por causa do AMBIENTE, só por causa do CONTEÚDO
    medido. Mesma disciplina de `_renderizar_e_medir` no arquivo irmão.
    """
    caminho = Path(caminho_svg_ou_html)
    if caminho.suffix == ".svg" and caminho.exists():
        corpo = caminho.read_text(encoding="utf-8")
    else:
        corpo = str(caminho_svg_ou_html)  # corpo HTML sintético já pronto

    script = (
        _PROBE_JS.replace("__FAMILIA_JSON__", json.dumps(familia or ""))
        .replace("__FORCAR_JSON__", "true" if familia else "false")
        .replace("__MARGEM_PX__", str(MARGEM_MINIMA_PX))
        .replace("__MARGEM_PROP__", str(MARGEM_MINIMA_PROPORCIONAL))
    )
    html = f"<!DOCTYPE html><html><head></head><body>{corpo}<script>{script}</script></body></html>"

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        caminho_html = f.name
    try:
        with _perfil_de_navegador_descartavel() as perfil:
            try:
                resultado = subprocess.run(
                    [
                        _CHROMIUM,
                        *_FLAGS_CHROME_HEADLESS,
                        f"--user-data-dir={perfil}",
                        # `document.fonts.load()` é assíncrono; `--dump-dom`
                        # sozinho não espera por ele (só espera o evento
                        # `load`, que não inclui promises pendentes).
                        # `--virtual-time-budget` avança o tempo virtual e
                        # aguarda a fila de tarefas assentar antes de
                        # despejar o DOM — confirmado por medição: sem ele,
                        # o `<title>` fica vazio; com ele, vem o JSON
                        # resolvido.
                        "--virtual-time-budget=4000",
                        "--dump-dom",
                        f"file://{caminho_html}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                pytest.skip(f"Chromium presente mas não funcionou ao medir: {exc!r}")
        casamento = re.search(r"<title>(.*?)</title>", resultado.stdout, re.DOTALL)
        if not casamento:
            pytest.skip(
                "Chromium rodou mas o DOM despejado não tem <title> — "
                f"stdout={resultado.stdout[:300]!r}"
            )
        try:
            return json.loads(casamento.group(1))
        except json.JSONDecodeError:
            pytest.skip(
                "Chromium rodou mas o <title> não é o JSON esperado (ambiente "
                f"quebrado, não regressão de SVG): {casamento.group(1)[:300]!r}"
            )
    finally:
        _descartar_caminho_temporario(caminho_html)


# ---------------------------------------------------------------------------
# Controles positivo e negativo — prova de que o instrumento sabe reprovar
# ANTES de confiar nele contra os arquivos reais (a mesma disciplina que
# `test_dl024_varredura_de_interface.py` já exige de si mesmo, e o mesmo
# cuidado que o Fred pediu: "confira o instrumento antes de confiar nele").
# Usam `familia=None` (a pilha "como está", sem forçar) porque o que estes
# testes provam é a LÓGICA do detector, não uma fonte específica — não
# precisam pular por fonte ausente.
# ---------------------------------------------------------------------------

_SVG_SINTETICO_CAIXA_RUIM = """
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120" viewBox="0 0 300 120">
  <rect x="10" y="10" width="120" height="40" fill="#eee"/>
  <text x="15" y="35" font-size="22">Isto vaza um pouco</text>
</svg>
"""

_SVG_SINTETICO_CAIXA_BOA = """
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120" viewBox="0 0 300 120">
  <rect x="10" y="10" width="260" height="40" fill="#eee"/>
  <text x="15" y="35" font-size="12">cabe</text>
</svg>
"""

_SVG_SINTETICO_CANVAS_RUIM = """
<svg xmlns="http://www.w3.org/2000/svg" width="120" height="60" viewBox="0 0 120 60">
  <rect x="10" y="10" width="200" height="20" fill="#eee"/>
  <text x="15" y="25" font-size="14">este texto sai bem para a direita do canvas inteiro</text>
</svg>
"""

_SVG_SINTETICO_COLISAO_RUIM = """
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120" viewBox="0 0 300 120">
  <rect x="150" y="10" width="120" height="90" fill="#eee"/>
  <text x="10" y="55" font-size="28">Texto que atravessa o retangulo vizinho de propósito</text>
</svg>
"""

_SVG_SINTETICO_COLISAO_BOA = """
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="120" viewBox="0 0 300 120">
  <rect x="150" y="10" width="120" height="90" fill="#eee"/>
  <text x="10" y="25" font-size="12">longe do vizinho</text>
</svg>
"""


def test_controle_positivo_detector_de_vazamento_de_caixa():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_CAIXA_RUIM)
    assert resultado["vazamentos_caixa"], (
        "o detector deixou passar um texto claramente maior que a caixa"
    )


def test_controle_negativo_detector_de_vazamento_de_caixa():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_CAIXA_BOA)
    assert not resultado["vazamentos_caixa"], (
        f"texto com folga clara foi acusado de vazar: {resultado['vazamentos_caixa']}"
    )


def test_controle_positivo_detector_de_vazamento_de_canvas():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_CANVAS_RUIM)
    assert resultado["vazamentos_canvas"], (
        "o detector deixou passar texto que sai do canvas inteiro"
    )


def test_controle_negativo_detector_de_vazamento_de_canvas():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_CAIXA_BOA)
    assert not resultado["vazamentos_canvas"], (
        f"texto dentro do canvas foi acusado de vazar dele: {resultado['vazamentos_canvas']}"
    )


def test_controle_positivo_detector_de_colisao():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_COLISAO_RUIM)
    assert resultado["colisoes"], (
        "o detector deixou passar um texto que atravessa um retângulo vizinho"
    )


def test_controle_negativo_detector_de_colisao():
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_COLISAO_BOA)
    assert not resultado["colisoes"], (
        f"texto longe do vizinho foi acusado de colidir: {resultado['colisoes']}"
    )


def test_controle_negativo_caixa_pequena_dentro_de_caixa_grande_nao_e_colisao():
    """Um cartão pequeno morar dentro de um painel maior é a estrutura
    NORMAL de todos os quatro SVG reais (ex.: o cartão "Contabilidade
    básica" mora dentro do painel do navegador mockup do `hero.svg`) — o
    detector de colisão não pode confundir aninhamento com invasão."""
    _pular_se_chromium_nao_funcional()
    aninhado = """
    <svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200">
      <rect x="10" y="10" width="280" height="180" fill="#eee"/>
      <rect x="30" y="30" width="100" height="40" fill="#ccc"/>
      <text x="35" y="55" font-size="12">cartao pequeno</text>
    </svg>
    """
    resultado = _medir_svg(aninhado)
    assert not resultado["colisoes"], (
        f"aninhamento normal (caixa pequena dentro de painel) foi confundido com colisão: "
        f"{resultado['colisoes']}"
    )


def test_fonte_esta_disponivel_devolve_false_para_nome_inventado():
    """Prova de que a checagem por `local()` não é permissiva: um nome de
    fonte que certamente não existe em máquina nenhuma tem que reprovar —
    e foi medido nesta mesma etapa que `document.fonts.check()` sozinho
    (sem o truque de `local()`) devolve `true` até para isto, o que o
    tornaria inútil como guarda."""
    _pular_se_chromium_nao_funcional()
    resultado = _medir_svg(_SVG_SINTETICO_CAIXA_BOA, familia="NomeDeFonteQueDataLedgerNaoTem12345")
    assert resultado["fonte_disponivel"] is False


# ---------------------------------------------------------------------------
# Os testes de efeito contra os SVG reais.
# ---------------------------------------------------------------------------


def _relatar(caminho, familia, resultado):
    nome = familia or "como declarado no arquivo (sem forçar)"
    partes = []
    if resultado["vazamentos_caixa"]:
        partes.append(
            "vazamentos de caixa: " + json.dumps(resultado["vazamentos_caixa"], ensure_ascii=False)
        )
    if resultado["vazamentos_canvas"]:
        partes.append(
            "vazamentos de canvas: "
            + json.dumps(resultado["vazamentos_canvas"], ensure_ascii=False)
        )
    if resultado["colisoes"]:
        partes.append("colisões: " + json.dumps(resultado["colisoes"], ensure_ascii=False))
    return f"{caminho.relative_to(RAIZ)} [{nome}]: " + "; ".join(partes)


@pytest.mark.parametrize("caminho", ARQUIVOS_SVG, ids=lambda c: c.name)
@pytest.mark.parametrize("familia", MODOS_DE_FONTE)
def test_svg_nao_vaza_da_caixa_nem_do_canvas_nem_colide(caminho, familia):
    """O teste de efeito central desta etapa: para cada SVG com `<text>`
    dentro de `<rect>` em `docs/assets/`, em cada fonte da pilha mais o pior
    caso (DejaVu Sans), nenhum texto pode vazar da caixa, vazar do canvas ou
    colidir com retângulo alheio.

    `familia=None` ("como_declarado") mede a pilha tal como está escrita no
    arquivo, com o que QUALQUER navegador real resolver nesta máquina — não
    pula nunca por fonte ausente (não força fonte nenhuma). As outras cinco
    pulam, com motivo, se a fonte pedida não estiver genuinamente instalada
    (`resultado["fonte_disponivel"] is False` — ver `_fonte_esta_disponivel`
    no docstring do módulo para por que isto não é feito por
    `document.fonts.check()` puro).
    """
    _pular_se_chromium_nao_funcional()
    familia_para_forcar = None if familia == "como_declarado" else familia
    resultado = _medir_svg(caminho, familia=familia_para_forcar)
    if familia_para_forcar and not resultado["fonte_disponivel"]:
        pytest.skip(
            f"A fonte {familia_para_forcar!r} não está instalada nesta máquina — "
            "este caso específico não roda aqui, só numa máquina que a tenha. "
            "Isto não é falha silenciosa: aparece no -rs como pulado, com este motivo."
        )
    assert not (
        resultado["vazamentos_caixa"] or resultado["vazamentos_canvas"] or resultado["colisoes"]
    ), _relatar(caminho, familia_para_forcar, resultado)


def test_ha_pelo_menos_um_svg_descoberto():
    """Controle de que `_svgs_com_texto_em_caixa` não ficou vazia por um
    engano de caminho — sem isto, `test_svg_nao_vaza_...` passaria por
    ausência de casos (0 testes parametrizados), não por aprovação real."""
    assert len(ARQUIVOS_SVG) >= 4, (
        f"esperados pelo menos os 4 SVG conhecidos com <text> e <rect>, achados: {ARQUIVOS_SVG}"
    )
    nomes = {c.name for c in ARQUIVOS_SVG}
    for esperado in ("hero.svg", "architecture.svg", "ciclo-de-qualidade.svg", "contributing.svg"):
        assert esperado in nomes, f"{esperado} não foi descoberto pela varredura"
