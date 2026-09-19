"""DL-028, fatia 1 (docs/planos/DL-028-o-juiz-aponta-para-o-produto.md):
instrumento que responde, por MEDIÇÃO DO NAVEGADOR sobre o PRODUTO REAL —
não sobre protótipos autônomos, e não por simulação de cascata CSS em
Python — se cada documento imprimível do produto sai com a identificação
do ESCRITÓRIO emitente.

**Por que este instrumento existe.** A oitava auditoria da DL-026
(docs/auditorias/2026-09-19-dl-026-rodada-8.md, §7) mediu que o juiz de
bancada (`docs/assets/design/gauntlet/juiz.py`) só consome HTML autônomo
das variantes do gauntlet — nunca `static/css/base.css` + `templates/**`,
que é o que o cliente do escritório de fato recebe. Para a pergunta "o
emitente aparece no papel?", isso deixava a guarda do `pytest`
(`apps/contabilidade/tests/test_bl329_marca_fora_do_papel.py` e
`test_bl331_timbre_do_escritorio_no_papel.py`, que simulam cascata CSS SEM
navegador) como a ÚNICA camada, não a primeira de duas — e o mesmo
relatório mediu **onze construções banais de CSS** que apagam a
identificação do escritório com aquela suíte inteira verde (H1).

**O que este instrumento NÃO é.** Não substitui a suíte `pytest` (que
continua sendo a "primeira linha barata" — rebaixamento formalizado na
fatia 3 deste plano). Não roda na integração contínua (isso é a fatia 2).
É ferramenta de BANCADA, como `docs/assets/design/gauntlet/juiz.py` e
`scripts/medir_impressao.py`: quem fecha uma etapa que mexa em
`static/css/base.css`, em `templates/**` ou em qualquer tela nova com
timbre roda este script manualmente contra o produto antes de declarar a
etapa pronta.

**Os dois interpretadores, a mesma separação de `medir_impressao.py`.** O
Python da venv do projeto (3.14) não tem Playwright — não é dependência de
`requirements/`, de propósito. Este script usa a venv do projeto para
RENDERIZAR o produto (Django real, `django.test.Client`, banco descartável
semeado) e delega só a medição no NAVEGADOR (visibilidade sob impressão +
PDF A4) a um subprocesso do Python DO SISTEMA
(`DL_PYTHON_DO_SISTEMA`, default `/usr/bin/python3`), que tem Playwright.

**Nenhum caminho fixo de navegador.** A resolução do executável do
Chromium é feita por `docs/assets/design/gauntlet/sonda_visibilidade.
resolver_executavel_do_chromium` — variável de ambiente
`DL_CHROMIUM_EXECUTAVEL` ou descoberta nativa do Playwright — nunca um
literal de caminho de uma máquina específica.

**O conjunto de telas é DERIVADO, nunca escrito à mão** (`_descobrir_telas_
com_timbre`, abaixo): este script anda por TODA a urlconf nomeada do
projeto (exceto o `django.contrib.admin`, terceiro reconhecido — nunca
carrega `.timbre-impressao`), requisita (GET, autenticado) cada rota cujos
parâmetros são conhecidos da base semeada (`empresa_id`, `conta_id` — os
dois que este script sabe preencher hoje) e mantém as respostas cujo HTML
contém a classe `timbre-impressao`. Se amanhã uma tela nova (Fiscal, por
exemplo) ganhar timbre e só precisar de `empresa_id` para ser alcançada,
ela entra aqui SOZINHA — é o BL-363 resolvido, para o navegador real, no
mesmo espírito da correção que a rodada 12 da DL-026 está fazendo (em
arquivo DISJUNTO: `apps/contabilidade/tests/**`) no motor CSS simulado.
Rotas cujos parâmetros este script NÃO conhece são PULADAS, com aviso
explícito em stderr — nunca silenciosamente ausentes (BL-356).

**Identificação PARCIAL conta como falha** (decisão desta etapa, a
confirmar com o Fred): não basta o CONTÊINER `.timbre-impressao` estar
visível — CADA linha (`Escritorio.linhas_do_timbre`, um `<p>` por linha)
precisa estar visível E aparecer no texto extraído do PDF. Uma sabotagem
que esconda só uma linha (ex.: `.timbre-impressao p:nth-of-type(2) {
display: none }` — o registro profissional some, a razão social continua)
REPROVA aqui, porque o documento sai com identificação incompleta, não
íntegra.

**Falha de infraestrutura é distinguível de falha de conteúdo** (BL-356).
Códigos de saída:

- `0`: sucesso — todas as telas derivadas saem com o emitente completo.
- `1`: **REPROVADO** — o script rodou até o fim, mas ao menos uma tela saiu
  sem o emitente completo. É um achado sobre o PRODUTO.
- `2`: **Recusado** — falha de infraestrutura (banco ausente, poppler-utils
  ausente, Python do sistema sem Playwright, Chromium indisponível, zero
  telas derivadas). Não é um veredito sobre o produto.

## Como usar

```bash
export DL_CONFIRMO_BANCO_DESCARTAVEL='<nome exato do banco>'
python scripts/medir_identificacao_do_emitente.py [pasta-de-saida] [--telas=balancete,razao]
```

`pasta-de-saida` (opcional): onde preservar os PDFs A4 gerados (padrão:
pasta temporária descartada ao fim). `--telas=` (opcional): restringe a
MEDIÇÃO às telas nomeadas — a DERIVAÇÃO continua completa; é só um filtro
de saída, útil em bancada para repetir uma sabotagem numa tela só sem
esperar as demais.
"""

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Reaproveita a infraestrutura de `medir_impressao.py` — Django configurado,
# cliente autenticado, cenário (empresa/conta) da base semeada, reescrita do
# CSS para `file://` — NUNCA reimplementada aqui (docstring do módulo).
import medir_impressao  # noqa: E402 — precisa vir depois de ajustar o sys.path

# `sonda_visibilidade.py` é módulo IRMÃO de `juiz.py`, não um pacote
# instalado. A venv do projeto (Python 3.14, sem Playwright) NÃO importa
# este módulo em tempo de execução normal — só o Python DO SISTEMA
# (subprocesso, abaixo) importa de verdade, porque só ele usa Playwright.
# O caminho é só uma STRING passada ao subprocesso via JSON; `_verificar_
# sonda_disponivel` (abaixo) confirma cedo, na venv, que o ARQUIVO existe e
# tem sintaxe válida — sem precisar de Playwright para isso — em vez de
# deixar um caminho errado só aparecer como erro dentro do subprocesso.
_GAUNTLET_DIR = str((RAIZ / "docs" / "assets" / "design" / "gauntlet").resolve())

SELETOR_TIMBRE_CONTAINER = ".timbre-impressao"
SELETOR_TIMBRE_FILHOS = ".timbre-impressao p"

# BL-282/BL-331: a marca de quem VENDE o software — precisa estar AUSENTE
# do papel. Checado no texto do PDF ao lado da presença do timbre, pelo
# mesmo motivo que `scripts/medir_impressao.py` já checa isto: as duas
# metades do critério 9 ("o fornecedor sai" e "o escritório entra") só
# se provam JUNTAS — uma sozinha não garante que o papel saiu identificado.
MARCA_DO_FORNECEDOR = "DataLedger"


def _recusar(mensagem):
    """Saída de código `2` — FALHA DE INFRAESTRUTURA (ver a tabela de
    códigos de saída na docstring do módulo). `sys.exit(str)` sozinho
    sempre sai com código `1`, o MESMO código do achado de CONTEÚDO
    (`_reprovar_por_conteudo`, abaixo) — as duas coisas precisam ser
    distinguíveis por quem chama este script (BL-356/DL-028 fatia 2: é o
    job de integração contínua quem lê este código agora), então a saída
    de infraestrutura passa sempre por aqui, nunca por um `sys.exit(str)`
    direto. Par de `_reprovar_por_conteudo` — as duas funções existem
    lado a lado, com o MESMO formato, de propósito: a distinção entre os
    dois códigos é um contrato, não uma convenção espalhada em `sys.exit`
    soltos pelo arquivo (testado em
    `scripts/test_medir_identificacao_do_emitente.py`, sem Playwright nem
    Django)."""
    sys.stderr.write(f"Recusado: {mensagem}\n")
    sys.exit(2)


def _reprovar_por_conteudo(mensagem):
    """Saída de código `1` — achado sobre o PRODUTO (documento sem
    emitente completo), NUNCA sobre infraestrutura. Par de `_recusar`
    (acima) — ver o comentário de lá para o porquê da distinção existir
    como duas funções nomeadas em vez de `sys.exit` soltos."""
    sys.stderr.write(f"REPROVADO: {mensagem}\n")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Derivação do conjunto de telas — NUNCA uma lista escrita à mão (BL-363,
# resolvido aqui para o navegador real).
# ---------------------------------------------------------------------------

# Namespace de terceiro RECONHECIDO (não é "produto"): nunca carrega
# `.timbre-impressao`, e andar pelas suas ~dezenas de rotas (uma por
# modelo registrado) só adicionaria tempo de execução e ruído ao relatório
# de rotas puladas, sem chance de achar uma tela imprimível. Não é uma
# lista de TELAS (o que o BL-363 proíbe) — é a exclusão de um subsistema
# de terceiro já reconhecido em outras guardas deste projeto (ex.:
# apps/core/tests/test_dl019_varredura_de_contratos.py).
NAMESPACES_DE_TERCEIRO_IGNORADOS = {"admin"}


def _todas_as_rotas_get_nomeadas():
    """`[(nome_completo, {chaves_de_kwargs})]` para TODA rota nomeada da
    urlconf do projeto, andando recursivamente por `include()` — a mesma
    IDEIA de `apps/core/tests/test_dl019_varredura_de_contratos.py::
    _percorrer_callbacks` (não a mesma função: aquele módulo é teste,
    este é instrumento de bancada, e nenhum dos dois deveria depender do
    outro para enumerar rotas). Rota sem `name` é invisível a
    `django.urls.reverse` — não entra aqui, e portanto não é candidata a
    este instrumento (o mesmo furo do BL-334/H3 da rodada 8, fora do
    escopo desta etapa)."""
    from django.urls import get_resolver

    encontradas = []

    def percorrer(padroes, prefixo):
        for padrao in padroes:
            sub_padroes = getattr(padrao, "url_patterns", None)
            if sub_padroes is not None:
                namespace = getattr(padrao, "namespace", None)
                if namespace in NAMESPACES_DE_TERCEIRO_IGNORADOS:
                    continue
                novo_prefixo = f"{prefixo}{namespace}:" if namespace else prefixo
                percorrer(sub_padroes, novo_prefixo)
                continue
            nome = getattr(padrao, "name", None)
            if not nome:
                continue
            conversores = set(getattr(padrao.pattern, "converters", {}) or {})
            encontradas.append((f"{prefixo}{nome}", conversores))

    percorrer(get_resolver().url_patterns, "")
    return encontradas


def _descobrir_telas_com_timbre(cliente, empresa, conta):
    """DERIVA o conjunto de telas do produto que carregam
    `.timbre-impressao` — ver a docstring do módulo. Devolve
    `{nome_curto: {"rota": ..., "url": ..., "html": ...}}` (HTML já com o
    `href` do CSS reescrito para `file://`, via `medir_impressao.
    _com_css_local` — reaproveitado, não reimplementado)."""
    from django.urls import reverse

    kwargs_conhecidos = {"empresa_id": empresa.id, "conta_id": conta.id}
    periodo = f"?inicio={medir_impressao.PERIODO_INICIO}&fim={medir_impressao.PERIODO_FIM}"
    padrao_timbre = re.compile(r'class="[^"]*\btimbre-impressao\b[^"]*"')

    telas = {}
    puladas = []
    for nome_completo, chaves in _todas_as_rotas_get_nomeadas():
        if not chaves.issubset(kwargs_conhecidos):
            puladas.append((nome_completo, sorted(chaves - set(kwargs_conhecidos))))
            continue
        args = {k: kwargs_conhecidos[k] for k in chaves}
        try:
            url = reverse(nome_completo, kwargs=args)
        except Exception:  # noqa: BLE001 — rota não-reversível não é candidata
            continue

        resposta = cliente.get(url + periodo)
        if resposta.status_code != 200:
            continue
        html = resposta.content.decode()
        if not padrao_timbre.search(html):
            continue
        nome_curto = nome_completo.rsplit(":", 1)[-1]
        telas[nome_curto] = {
            "rota": nome_completo,
            "url": url,
            "html": medir_impressao._com_css_local(html),
        }

    if puladas:
        print(
            f"AVISO (não é falha): {len(puladas)} rota(s) nomeada(s) puladas na "
            "varredura por precisarem de parâmetro que este instrumento não sabe "
            "preencher hoje (só empresa_id/conta_id são conhecidos) — uma tela "
            "nova que dependa só desses dois entraria sozinha; uma que dependa de "
            "outro parâmetro precisa de extensão deste script:",
            file=sys.stderr,
        )
        for nome, faltando in puladas:
            print(f"  - {nome}: falta {faltando}", file=sys.stderr)

    return telas


# ---------------------------------------------------------------------------
# Medição no navegador (subprocesso do Python do sistema, com Playwright) —
# mesma separação de `medir_impressao.py`.
# ---------------------------------------------------------------------------

_SCRIPT_DO_SUBPROCESSO = r"""
import json, sys
from pathlib import Path

especificacao = json.loads(sys.argv[1])
sys.path.insert(0, especificacao["gauntlet_dir"])
import sonda_visibilidade
from playwright.sync_api import sync_playwright

pasta_html = Path(especificacao["pasta_html"])
pasta_saida = Path(especificacao["pasta_saida"])
pasta_saida.mkdir(parents=True, exist_ok=True)
sonda = sonda_visibilidade.js_sonda_container_e_filhos(
    especificacao["seletor_container"], especificacao["seletor_filhos"]
)

resultados = {}
erro_infra = None
try:
    with sync_playwright() as p:
        navegador = sonda_visibilidade.lancar_chromium(p)
        pagina = navegador.new_page()
        for nome in especificacao["telas"]:
            try:
                pagina.goto((pasta_html / f"{nome}.html").as_uri(), wait_until="networkidle")
                # Espera a troca de font-display: swap terminar (BL-347/F5,
                # o mesmo cuidado de medir_impressao.py) -- texto medido
                # ANTES da troca ainda é visivel/legivel, mas a altura de
                # linha pode diferir; nao afeta a pergunta deste script
                # (existe/esta visivel), so a mantem consistente com o
                # resto do projeto.
                pagina.evaluate("() => document.fonts.ready.then(() => true)")
                pagina.emulate_media(media="print")
                medida = pagina.evaluate(sonda)
                pagina.pdf(
                    path=str(pasta_saida / f"{nome}.pdf"),
                    format="A4",
                    display_header_footer=False,
                    margin={"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
                )
                pagina.emulate_media(media=None)
                resultados[nome] = medida
            except Exception as erro:
                resultados[nome] = {"erro": f"{type(erro).__name__}: {erro}"}
        navegador.close()
except sonda_visibilidade.NavegadorIndisponivel as erro:
    erro_infra = f"{erro}"

print(json.dumps({"resultados": resultados, "erro_infra": erro_infra}, ensure_ascii=False))
"""


def _medir_no_navegador(pasta_html, pasta_saida, nomes_das_telas):
    especificacao = json.dumps(
        {
            "gauntlet_dir": _GAUNTLET_DIR,
            "pasta_html": str(pasta_html),
            "pasta_saida": str(pasta_saida),
            "telas": nomes_das_telas,
            "seletor_container": SELETOR_TIMBRE_CONTAINER,
            "seletor_filhos": SELETOR_TIMBRE_FILHOS,
        }
    )
    resultado = subprocess.run(
        [medir_impressao.PYTHON_DO_SISTEMA, "-c", _SCRIPT_DO_SUBPROCESSO, especificacao],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        _recusar(
            "a medição no navegador (subprocesso do Python do sistema) "
            f"terminou com código {resultado.returncode}.\n"
            f"saida padrao: {resultado.stdout}\nerro: {resultado.stderr}"
        )
    try:
        saida = json.loads(resultado.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError) as exc:
        _recusar(
            "a saída do subprocesso de medição não é o JSON esperado.\n"
            f"Detalhe: {exc}\nsaida bruta: {resultado.stdout!r}"
        )
    if saida.get("erro_infra"):
        _recusar(str(saida["erro_infra"]))
    return saida["resultados"]


def _verificar_sonda_disponivel():
    """Confirma cedo, na venv do projeto (sem precisar de Playwright), que
    `sonda_visibilidade.py` existe e importa sem erro de sintaxe — em vez
    de deixar um `_GAUNTLET_DIR` errado só se manifestar como erro dentro
    do subprocesso do Python do sistema, três camadas depois."""
    import importlib.util

    caminho = Path(_GAUNTLET_DIR) / "sonda_visibilidade.py"
    especificacao = importlib.util.spec_from_file_location("sonda_visibilidade", caminho)
    if especificacao is None or especificacao.loader is None:
        _recusar(f"não encontrei {caminho}.")
    modulo = importlib.util.module_from_spec(especificacao)
    try:
        especificacao.loader.exec_module(modulo)
    except Exception as erro:  # noqa: BLE001 — reportado, não engolido
        _recusar(f"{caminho} não importa: {type(erro).__name__}: {erro}")


def _texto_do_pdf(caminho_pdf):
    """Texto do PDF inteiro, espaço normalizado — mesma técnica de
    `medir_impressao.py` (`-layout`, depois `re.sub(r"\\s+", " ", ...)`),
    não reimplementada com outra assinatura."""
    saida = subprocess.run(
        ["pdftotext", "-layout", str(caminho_pdf), "-"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return re.sub(r"\s+", " ", saida).strip()


_PADRAO_COR_RGBA = re.compile(r"[\d.]+")


def _tinta_invisivel(cor_css):
    """`True` quando `cor_css` (o `getComputedStyle(...).color` bruto, ex.:
    `"rgba(0, 0, 0, 0)"`) tem alfa ZERO — "tinta" que não pinta pixel
    nenhum. Fecha o limite que `visivelDeVerdade` já declara por escrito
    (ver o comentário em `sonda_visibilidade.js_sonda_container_e_filhos`):
    `color: transparent` MEDIDO nesta etapa: não muda `checkVisibility()`,
    não zera a área, e o texto AINDA aparece no `pdftotext` — o glifo é
    pintado (com tinta transparente), `pdftotext` lê o OBJETO de texto do
    PDF, não o pixel renderizado. Sem esta checagem, `.timbre-impressao {
    color: transparent }` passaria pelas duas medições deste script
    (visibilidade E texto do PDF) — falso negativo medido, não hipotético,
    ao construir este instrumento."""
    numeros = [float(n) for n in _PADRAO_COR_RGBA.findall(cor_css or "")]
    return len(numeros) >= 4 and numeros[3] == 0


def _com_saida_de_infraestrutura(func, *args, **kwargs):
    """Chama uma rotina `_exigir_*`/`_preparar_*` REAPROVEITADA de
    `medir_impressao.py` — que sai com `sys.exit(str)` (código `1`) em
    caso de falha — e RENORMALIZA a saída para código `2`, preservando a
    mensagem original. Sem isto, uma falha de infraestrutura vinda de uma
    função reaproveitada sairia com o MESMO código do achado de CONTEÚDO
    (REPROVADO, no fim de `main`), quebrando a distinção que este script
    promete na própria docstring (BL-356)."""
    try:
        return func(*args, **kwargs)
    except SystemExit as erro:
        if erro.code not in (0, None):
            sys.stderr.write(f"{erro.code}\n")
            sys.exit(2)
        raise


# ---------------------------------------------------------------------------
# Orquestração.
# ---------------------------------------------------------------------------


def main(argv):
    inicio = time.monotonic()

    _com_saida_de_infraestrutura(medir_impressao._exigir_ferramentas_de_pdf)
    _com_saida_de_infraestrutura(medir_impressao._exigir_python_do_sistema_com_playwright)
    _verificar_sonda_disponivel()

    pasta_informada = None
    filtro_telas = None
    for arg in argv:
        if arg.startswith("--telas="):
            filtro_telas = set(arg.removeprefix("--telas=").split(","))
        else:
            pasta_informada = Path(arg).resolve()

    cliente, empresa, conta = _com_saida_de_infraestrutura(
        medir_impressao._preparar_cliente_e_cenario_de_medicao
    )
    escritorio = empresa.escritorio
    # Contrato ÚNICO servidor→template (Escritorio.linhas_do_timbre, ver
    # apps/tenancy/models.py) -- as linhas ESPERADAS no papel vêm do MESMO
    # método que o template usa para desenhá-las, nunca de um literal
    # reescrito aqui (duas fontes do mesmo texto divergem, AGENTS.md §8).
    linhas_esperadas = [linha.strip() for linha in escritorio.linhas_do_timbre]
    if not linhas_esperadas:
        _recusar(
            "Escritorio.linhas_do_timbre devolveu lista vazia para a base "
            "semeada — contrato quebrado (o método nunca deveria devolver vazio)."
        )

    telas = _descobrir_telas_com_timbre(cliente, empresa, conta)
    if not telas:
        _recusar(
            "a varredura de rotas não achou NENHUMA tela com "
            "'.timbre-impressao' — o produto tem pelo menos três (Balancete, "
            "Diário, Razão), então isto é sinal de regressão na urlconf, no "
            "HTML ou na varredura em si, não ausência real. Investigue antes "
            "de confiar em qualquer resultado deste instrumento."
        )
    print(
        f"telas derivadas com timbre ({len(telas)}): {', '.join(sorted(telas))}",
        file=sys.stderr,
    )

    nomes_para_medir = sorted(telas if filtro_telas is None else (telas.keys() & filtro_telas))
    if filtro_telas and not nomes_para_medir:
        _recusar(
            f"--telas={sorted(filtro_telas)} não bate com nenhuma tela derivada ({sorted(telas)})."
        )

    with tempfile.TemporaryDirectory(prefix="dl-medir-emitente-") as pasta_temp:
        pasta_html = Path(pasta_temp) / "html"
        pasta_html.mkdir()
        for nome in nomes_para_medir:
            (pasta_html / f"{nome}.html").write_text(telas[nome]["html"], encoding="utf-8")

        pasta_saida = pasta_informada or (Path(pasta_temp) / "pdfs")
        pasta_saida.mkdir(parents=True, exist_ok=True)

        resultados_navegador = _medir_no_navegador(pasta_html, pasta_saida, nomes_para_medir)

        relatorio = {}
        reprovacoes = []
        for nome in nomes_para_medir:
            medida = resultados_navegador.get(nome, {})
            entrada = {
                "url": telas[nome]["url"],
                "rota": telas[nome]["rota"],
                "medicao_navegador": medida,
            }
            relatorio[nome] = entrada

            if "erro" in medida:
                reprovacoes.append(f"{nome}: erro de navegação/medição — {medida['erro']}")
                entrada["veredito"] = "ERRO"
                continue

            caminho_pdf = pasta_saida / f"{nome}.pdf"
            texto_pdf = _texto_do_pdf(caminho_pdf) if caminho_pdf.exists() else ""
            entrada["pdf"] = str(caminho_pdf)
            entrada["pdf_contem_marca_do_fornecedor"] = MARCA_DO_FORNECEDOR in texto_pdf

            motivos = []
            if not medida.get("encontrado"):
                motivos.append("container '.timbre-impressao' não encontrado no HTML")
            elif not medida.get("visivel"):
                motivos.append("container '.timbre-impressao' NÃO visível sob impressão")
            elif _tinta_invisivel(medida.get("cor_efetiva")):
                motivos.append(
                    "container '.timbre-impressao' com tinta de alfa zero "
                    f"({medida.get('cor_efetiva')!r}) — visível por layout, ilegível na prática"
                )

            filhos = medida.get("filhos", [])
            linhas_no_pdf = {}
            for linha in linhas_esperadas:
                filho_da_linha = next(
                    (f for f in filhos if f.get("texto", "").strip() == linha), None
                )
                visivel_no_navegador = bool(filho_da_linha and filho_da_linha.get("visivel"))
                legivel = visivel_no_navegador and not _tinta_invisivel(
                    filho_da_linha.get("cor_efetiva") if filho_da_linha else None
                )
                presente_no_pdf = linha in texto_pdf
                linhas_no_pdf[linha] = {
                    "visivel_no_navegador": visivel_no_navegador,
                    "legivel": legivel,
                    "presente_no_pdf": presente_no_pdf,
                }
                if not visivel_no_navegador:
                    motivos.append(f"linha do timbre NÃO visível sob impressão: {linha!r}")
                elif not legivel:
                    motivos.append(f"linha do timbre com tinta de alfa zero (ilegível): {linha!r}")
                if not presente_no_pdf:
                    motivos.append(f"linha do timbre AUSENTE do texto do PDF: {linha!r}")
            entrada["linhas_do_timbre"] = linhas_no_pdf

            if entrada["pdf_contem_marca_do_fornecedor"]:
                motivos.append(f"marca do fornecedor ({MARCA_DO_FORNECEDOR!r}) presente no PDF")

            entrada["veredito"] = "PASSOU" if not motivos else "REPROVADO"
            entrada["motivos"] = motivos
            if motivos:
                reprovacoes.append(f"{nome}: {'; '.join(motivos)}")

        tempo = time.monotonic() - inicio
        print(json.dumps(relatorio, ensure_ascii=False, indent=2))
        for nome, entrada in relatorio.items():
            print(f"{nome}: {entrada['veredito']} — {entrada['url']}")
        print(f"\ntempo de execução: {tempo:.1f}s", file=sys.stderr)
        if pasta_informada:
            print(f"PDFs preservados em: {pasta_informada}", file=sys.stderr)

        if reprovacoes:
            detalhe = "\n".join(f"  - {linha}" for linha in reprovacoes)
            _reprovar_por_conteudo(
                f"{len(reprovacoes)} de {len(nomes_para_medir)} tela(s) sem "
                f"identificação completa do emitente no papel:\n{detalhe}"
            )


if __name__ == "__main__":
    main(sys.argv[1:])
