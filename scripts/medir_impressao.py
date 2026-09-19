"""BL-337 (achado M5 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): instrumento VERSIONADO para
medir a PAGINAÇÃO real da impressão do BL-282 — quantas folhas A4 cada
relatório ocupa, se o cabeçalho da tabela repete em toda folha, e se
alguma linha é cortada ENTRE duas páginas.

**Por que este script existe.** O backlog declarava "Balancete 3 folhas,
Diário 3, Razão 4, cabeçalho repetido em todas", mas `grep -rn "\\.pdf("
docs/assets/design/gauntlet/juiz.py scripts/` devolvia só um comentário
dizendo que a paginação real estava FORA do escopo do juiz. Os PDFs que
sustentavam o número viviam soltos no scratchpad volátil de quem mediu —
o auditor da rodada 5 CONFIRMOU os números, mas precisou escrever a sonda
do zero para isso (achado M5: "medição que só uma pessoa consegue repetir
não é medição do projeto" — a mesma lição que já valia para densidade,
`scripts/semear_base_de_medicao.py`, e não tinha sido transportada para
impressão).

**DECISÃO (o arquiteto deveria revisar): script NOVO, não extensão de
`docs/assets/design/gauntlet/juiz.py`.** O juiz consome pastas de HTML
AUTÔNOMO — protótipos do gauntlet de design, sem Django nem banco. As
telas medidas aqui são RENDERIZAÇÃO REAL do produto (dados de
`scripts/semear_base_de_medicao.py`, usuário autenticado,
`request.escritorio` resolvido pelo middleware de verdade) — o
instrumento PRECISA estar dentro do processo Django para produzi-las. Só
a geração do PDF em si depende de Chromium/Playwright, que não está nas
dependências do projeto (`requirements/`) — a MESMA separação de ambiente
que o próprio `juiz.py` já declara ("Rode com o Python do sistema (tem
playwright)") e que o auditor precisou reproduzir manualmente com uma
venv isolada. Este script orquestra as DUAS pontas com UM comando
publicado: renderiza com o Django do venv do projeto e delega só a
geração do PDF a um subprocesso do PYTHON DO SISTEMA
(`DL_PYTHON_DO_SISTEMA`, com o mesmo padrão de `CHROMIUM` do `juiz.py`).

Medição de página (contagem de folhas, texto por página) usa
`pdfinfo`/`pdftotext` (poppler-utils) via subprocesso — de propósito
NENHUMA biblioteca Python de PDF nova em `requirements/` por uma
ferramenta de BANCADA que não roda na CI.

## Como usar

Depois de `scripts/semear_base_de_medicao.py` já ter semeado o banco:

```bash
export DL_CONFIRMO_BANCO_DESCARTAVEL='<nome exato do banco>'
python scripts/medir_impressao.py [pasta-de-saida]
```

`pasta-de-saida` é opcional (padrão: pasta temporária descartada ao fim);
informe um caminho para inspecionar os PDFs depois.

## Os dois modos de impressão medidos, sempre os DOIS

⚠️ Achado A2 da auditoria DL-026, rodada 5: medir só `page.pdf()` com as
opções padrão da FERRAMENTA (sem cabeçalho/rodapé, margem zero) não é
medir o que o contador RECEBE — no Chrome e no Edge, a caixa "Cabeçalhos e
rodapés" do diálogo de impressão vem MARCADA por padrão, e a margem vem em
"Padrão", não zero. Este script gera e mede os DOIS modos para CADA
relatório:

1. **sem-cabecalho** — `display_header_footer=False`, margem zero (o que
   o implementador do BL-282 mediu).
2. **com-cabecalho** — `display_header_footer=True`, margem 10mm (o modo
   PADRÃO do navegador — o que produziu o achado A2: "DataLedger" no
   cabeçalho de toda folha, com a URL interna).

**Fora do escopo desta etapa** (não é responsabilidade do
`especialista-frontend` nesta rodada — BL-332/BL-338 estão com o Fred,
porque o texto que substitui é decisão de produto): o `<title>` da página
e a ordem do cabeçalho impresso não são alterados aqui. Se a sonda abaixo
acusar "DataLedger" no cabeçalho do navegador ou o nome do operador antes
do timbre do escritório, isso é o resultado ESPERADO desta medição — vai
para o relatório da etapa, não para uma correção de código neste script.

## Limitação declarada da checagem de "linha não partida" e "cabeçalho repete"

MEDIDO nesta etapa: `pdftotext` — com ou sem `-layout` — lê o `<thead>` de
duas linhas (com `rowspan`/`colspan`) e cada `<tr>` de dados numa ORDEM
FÍSICA de colunas que **não é** a ordem lógica do HTML de origem (uma
comparação ingênua por substring do texto inteiro, na ordem do DOM,
produzia falso alarme em quase toda linha — descoberto rodando o script
contra a base real, não hipotetizado). Por isso as duas checagens abaixo
são por CONJUNTO/ÂNCORA, não por comparação exata do texto inteiro:

- **Cabeçalho repete**: todas as palavras SIGNIFICATIVAS (mais de duas
  letras) do `<thead>` aparecem, em QUALQUER ordem, no texto de cada
  página — não a frase inteira, na ordem original.
- **Linha partida**: as âncoras da linha (código de conta, ÚLTIMO valor
  monetário e, no Diário/Razão, o histórico sintético — `_ancoras_da_linha`)
  precisam cair todas numa página em COMUM. Uma âncora que não é
  encontrada em página NENHUMA é reportada À PARTE
  (`ancoras_ausentes`) — é falha de extração (texto raro demais, ou
  âncora perto do limite de detecção do próprio `pdftotext`), não prova
  de corte entre páginas, e o relatório NUNCA confunde as duas.

Texto `.visualmente-oculto` (leitor de tela, nunca pintado no papel) é
removido do HTML de origem ANTES de calcular âncoras — sem isso, a
explicação "invertido em relação à natureza cadastrada..." (BL-281) conta
como texto da linha e nunca é achada no PDF, porque o Chromium
corretamente não a pinta.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Mesmo binário que docs/assets/design/gauntlet/juiz.py já usa — não
# retypado como literal novo: se o caminho mudar lá, este script também
# precisa mudar, e um `grep` encontra os dois de uma vez por serem a
# MESMA string.
CHROMIUM = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# O Python do VENV do projeto não tem Playwright (não é dependência de
# `requirements/` — decisão registrada na docstring do módulo). Este
# script delega só a geração do PDF a um interpretador DIFERENTE, o mesmo
# que `juiz.py` já assume ter Playwright instalado.
PYTHON_DO_SISTEMA = os.environ.get("DL_PYTHON_DO_SISTEMA", "/usr/bin/python3")

# Constantes da base semeada por scripts/semear_base_de_medicao.py — os
# MESMOS CNPJ/usuário/competência de lá, nunca reinventados aqui. Se a
# base mudar de forma, os dois scripts precisam mudar juntos.
CNPJ_ESCRITORIO_DE_MEDICAO = "11222333000181"
CNPJ_EMPRESA_DE_MEDICAO = "44555666000199"
USUARIO_DE_MEDICAO = "medicao"
PERIODO_INICIO = "2026-03-01"
PERIODO_FIM = "2026-03-31"

MODOS_DE_IMPRESSAO = {
    "sem-cabecalho": {
        "display_header_footer": False,
        "margin": {"top": "0mm", "bottom": "0mm", "left": "0mm", "right": "0mm"},
    },
    "com-cabecalho": {
        "display_header_footer": True,
        "margin": {"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
    },
}


def _exigir_banco_descartavel(nome_do_banco):
    """Mesma trava, mesmo raciocínio de `_exigir_banco_descartavel` em
    `scripts/semear_base_de_medicao.py` (BL-316): confirmação genérica é
    clicada sem ler; digitar o nome do banco exige olhar para ele. Este
    script não GRAVA lançamento nenhum, mas autentica e navega contra o
    banco configurado — o mesmo cuidado de "não rodar por engano contra a
    base de um escritório de verdade" se aplica."""
    confirmado = os.environ.get("DL_CONFIRMO_BANCO_DESCARTAVEL")
    if confirmado != nome_do_banco:
        sys.exit(
            "Recusado: este script autentica um cliente Django e navega contra o "
            "banco configurado, e DL_CONFIRMO_BANCO_DESCARTAVEL não corresponde a "
            "ele.\n"
            "Defina a variável com o nome EXATO do banco — o mesmo já usado para "
            "rodar scripts/semear_base_de_medicao.py.\n\n"
            "Para descobrir o banco em uso:\n"
            "  python manage.py shell -c "
            '"from django.conf import settings; '
            "print(settings.DATABASES['default']['NAME'])\""
        )


def _exigir_ferramentas_de_pdf():
    faltando = [f for f in ("pdfinfo", "pdftotext") if shutil.which(f) is None]
    if faltando:
        sys.exit(
            f"Recusado: {', '.join(faltando)} (poppler-utils) não encontrado(s) no "
            "PATH — este script mede paginação com pdfinfo/pdftotext DE PROPÓSITO, "
            "para não acrescentar biblioteca Python de PDF a requirements/ por uma "
            "ferramenta de bancada que não roda na CI (ver a docstring do módulo). "
            "Instale poppler-utils (ex.: apt install poppler-utils)."
        )


def _exigir_python_do_sistema_com_playwright():
    resultado = subprocess.run(
        [PYTHON_DO_SISTEMA, "-c", "import playwright.sync_api"],
        capture_output=True,
    )
    if resultado.returncode != 0:
        sys.exit(
            f"Recusado: {PYTHON_DO_SISTEMA!r} não importa playwright.sync_api — este "
            "script delega a geração do PDF a um Python DIFERENTE do venv do "
            "projeto (a mesma separação de ambiente que docs/assets/design/gauntlet/"
            "juiz.py já assume). Aponte DL_PYTHON_DO_SISTEMA para um interpretador "
            "com Playwright instalado, ou instale Playwright nele."
        )


# ---------------------------------------------------------------------------
# Renderização real (Django, venv do projeto).
# ---------------------------------------------------------------------------


def _renderizar_paginas():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()

    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.test.utils import setup_test_environment

    from apps.contabilidade.models import Conta
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio

    _exigir_banco_descartavel(settings.DATABASES["default"]["NAME"])

    # Fora do pytest, ALLOWED_HOSTS não ganha "testserver" sozinho — é o
    # próprio Django quem faz isso em `setup_test_environment` (a mesma
    # função que a infraestrutura de teste chama por baixo). Chamada aqui
    # de propósito, não como cópia às cegas: só ALLOWED_HOSTS importa para
    # este script, que não usa sinal nenhum do restante do ambiente de teste.
    setup_test_environment()

    usuario_modelo = get_user_model()
    try:
        escritorio = Escritorio.objects.get(cnpj=CNPJ_ESCRITORIO_DE_MEDICAO)
        empresa = Empresa.objects.get(cnpj=CNPJ_EMPRESA_DE_MEDICAO, escritorio=escritorio)
        usuario = usuario_modelo.objects.get(username=USUARIO_DE_MEDICAO)
    except (Escritorio.DoesNotExist, Empresa.DoesNotExist, usuario_modelo.DoesNotExist) as exc:
        sys.exit(
            "Recusado: base de medição não encontrada neste banco — rode primeiro "
            "'python scripts/semear_base_de_medicao.py' contra o MESMO banco antes "
            f"deste script.\nDetalhe: {exc}"
        )

    conta = Conta.objects.filter(empresa=empresa, aceita_lancamento=True).order_by("codigo").first()
    if conta is None:
        sys.exit("Recusado: a empresa semeada não tem conta analítica nenhuma — base incompleta.")

    cliente = Client()
    # force_login não devolve nada — se falhar, lança exceção; nada a checar aqui.
    cliente.force_login(usuario)

    periodo = f"?inicio={PERIODO_INICIO}&fim={PERIODO_FIM}"
    rotas = {
        "balancete": f"/contabilidade/painel/empresas/{empresa.id}/balancete/{periodo}",
        "diario": f"/contabilidade/painel/empresas/{empresa.id}/diario/{periodo}",
        "razao": f"/contabilidade/painel/empresas/{empresa.id}/razao/{conta.id}/{periodo}",
    }

    caminho_css = (RAIZ / "static" / "css" / "base.css").resolve()
    paginas = {}
    for nome, url in rotas.items():
        resposta = cliente.get(url)
        if resposta.status_code != 200:
            sys.exit(
                f"Recusado: {nome} respondeu {resposta.status_code} em {url!r} — "
                "a base semeada ou a rota mudou de forma incompatível com este script."
            )
        html = resposta.content.decode()
        # O Chromium do subprocesso abre o arquivo via file:// — sem
        # servidor Django nenhum para resolver "/static/css/base.css".
        # Reescreve para o caminho REAL do arquivo no disco (o mesmo que
        # o servidor de desenvolvimento serve) — nunca uma cópia à parte,
        # que divergiria do CSS de verdade assim que alguém o editasse.
        html = html.replace(
            'href="/static/css/base.css"',
            f'href="file://{caminho_css}"',
        )
        paginas[nome] = html
    return paginas


# ---------------------------------------------------------------------------
# Geração de PDF (subprocesso do Python do sistema, com Playwright).
# ---------------------------------------------------------------------------

_SCRIPT_DO_SUBPROCESSO = r"""
import json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

especificacao = json.loads(sys.argv[1])
chromium = especificacao["chromium"]
pasta_html = Path(especificacao["pasta_html"])
pasta_saida = Path(especificacao["pasta_saida"])
nomes = especificacao["nomes"]
modos = especificacao["modos"]

pasta_saida.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    navegador = p.chromium.launch(executable_path=chromium)
    pagina = navegador.new_page()
    for nome in nomes:
        pagina.goto((pasta_html / f"{nome}.html").as_uri(), wait_until="networkidle")
        for modo_nome, opcoes in modos.items():
            pagina.pdf(
                path=str(pasta_saida / f"{nome}-{modo_nome}.pdf"),
                format="A4",
                display_header_footer=opcoes["display_header_footer"],
                margin=opcoes["margin"],
            )
    navegador.close()
print("OK")
"""


def _gerar_pdfs(pasta_html, pasta_saida, nomes):
    especificacao = json.dumps(
        {
            "chromium": CHROMIUM,
            "pasta_html": str(pasta_html),
            "pasta_saida": str(pasta_saida),
            "nomes": nomes,
            "modos": MODOS_DE_IMPRESSAO,
        }
    )
    resultado = subprocess.run(
        [PYTHON_DO_SISTEMA, "-c", _SCRIPT_DO_SUBPROCESSO, especificacao],
        capture_output=True,
        text=True,
    )
    if resultado.returncode != 0:
        sys.exit(
            "Recusado: a geração de PDF (subprocesso do Python do sistema) falhou:\n"
            f"saida padrao: {resultado.stdout}\nerro: {resultado.stderr}"
        )


# ---------------------------------------------------------------------------
# Medição (pdfinfo/pdftotext via subprocesso — nenhuma lib Python de PDF).
# ---------------------------------------------------------------------------


def _numero_de_paginas(caminho_pdf):
    saida = subprocess.run(
        ["pdfinfo", str(caminho_pdf)], capture_output=True, text=True, check=True
    ).stdout
    m = re.search(r"^Pages:\s+(\d+)", saida, re.MULTILINE)
    assert m, f"controle: pdfinfo não devolveu 'Pages:' para {caminho_pdf}"
    return int(m.group(1))


def _texto_por_pagina(caminho_pdf, total_paginas):
    textos = []
    for pagina_num in range(1, total_paginas + 1):
        saida = subprocess.run(
            [
                "pdftotext",
                "-f",
                str(pagina_num),
                "-l",
                str(pagina_num),
                "-layout",
                str(caminho_pdf),
                "-",
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        textos.append(re.sub(r"\s+", " ", saida).strip())
    return textos


# Extração do <thead>/<tbody> do HTML de origem — regex sobre a marcação,
# no mesmo estilo já usado em apps/contabilidade/tests/
# test_dl024_atalhos_e_acessibilidade.py (PADRAO_TAG_KBD e companhia):
# suficiente para uma tabela sem aninhamento de <table> dentro de <table>,
# que é a forma real de `.tabela-dados` neste projeto.
_PADRAO_THEAD = re.compile(r"<thead[^>]*>(.*?)</thead>", re.IGNORECASE | re.DOTALL)
_PADRAO_TBODY = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.IGNORECASE | re.DOTALL)
_PADRAO_TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_PADRAO_TAG = re.compile(r"<[^>]+>")

# `.visualmente-oculto` (apps/core/marcacao e static/css/base.css) tira o
# elemento da TINTA sem tirar do FLUXO nem do leitor de tela — é conteúdo
# real no HTML que o PAPEL nunca pinta. Medido nesta etapa: sem remover
# isto primeiro, o texto extraído do HTML contém a explicação de saldo
# invertido ("— invertido em relação à natureza cadastrada...") e o
# `<caption>`, que `pdftotext` corretamente NÃO devolve (porque o
# Chromium nunca os PINTA) — comparar um com o outro sem esta remoção
# produzia falso "linha partida"/"âncora ausente" em quase toda linha.
_PADRAO_OCULTO = re.compile(
    r'<(span|abbr|caption)\b[^>]*\bclass="[^"]*visualmente-oculto[^"]*"[^>]*>.*?</\1>',
    re.IGNORECASE | re.DOTALL,
)

# Âncoras usadas para localizar uma LINHA da tabela dentro do texto de uma
# página: um código de conta hierárquico ("1.1.1.01" — Balancete/Plano de
# contas) e o último valor monetário formatado da linha (a coluna mais à
# direita — "Saldo final"/"Saldo" conforme o relatório). Para Diário/Razão
# (sem código de conta na linha), o histórico ("Lançamento sintético NN",
# só existe nos dados de scripts/semear_base_de_medicao.py) serve de
# âncora textual adicional.
_PADRAO_CODIGO_DE_CONTA = re.compile(r"\b\d+(?:\.\d+){1,3}\b")
_PADRAO_VALOR_MONETARIO = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
_PADRAO_HISTORICO_SINTETICO = re.compile(r"Lançamento sintético \d+")


def _remover_visualmente_oculto(html_fragmento):
    anterior = None
    atual = html_fragmento
    while anterior != atual:
        anterior = atual
        atual = _PADRAO_OCULTO.sub("", atual)
    return atual


def _texto_sem_tags(html_fragmento):
    sem_oculto = _remover_visualmente_oculto(html_fragmento)
    sem_tags = _PADRAO_TAG.sub(" ", sem_oculto)
    return re.sub(r"\s+", " ", sem_tags).strip()


def _cabecalho_repete_em_todas_as_paginas(cabecalho, textos_das_paginas):
    """Checagem por CONJUNTO de palavras (não substring do texto inteiro):
    medido nesta etapa que `pdftotext` — com ou sem `-layout` — lê um
    `<thead>` de DUAS linhas com `rowspan`/`colspan` numa ORDEM diferente
    da ordem lógica do HTML (colunas físicas, não células do DOM). A ORDEM
    das palavras do cabeçalho no PDF não é a mesma da origem — a PRESENÇA
    de cada palavra significativa, é. Palavras de 1-2 letras (o rótulo de
    natureza "D"/"C", por exemplo) são ignoradas por não serem
    específicas o bastante para provar repetição de cabeçalho."""
    if not textos_das_paginas:
        return None
    palavras_do_cabecalho = {p for p in re.findall(r"\w+", cabecalho.lower()) if len(p) > 2}
    if not palavras_do_cabecalho:
        return None
    return all(
        palavras_do_cabecalho <= {p for p in re.findall(r"\w+", texto.lower())}
        for texto in textos_das_paginas
    )


def _ancoras_da_linha(linha):
    """Tokens ESPECÍFICOS o bastante para identificar a linha dentro do
    texto de uma página — não o primeiro/último token cru (frágil demais
    contra a reordenação que `pdftotext` aplica a colunas físicas, ver o
    comentário de `_cabecalho_repete_em_todas_as_paginas`): o código de
    conta (se houver) e o ÚLTIMO valor monetário da linha (a coluna mais à
    direita); para Diário/Razão, também o histórico sintético, que é
    único por lançamento."""
    ancoras = []
    codigos = _PADRAO_CODIGO_DE_CONTA.findall(linha)
    if codigos:
        ancoras.append(codigos[0])
    valores = _PADRAO_VALOR_MONETARIO.findall(linha)
    if valores:
        ancoras.append(valores[-1])
    historico = _PADRAO_HISTORICO_SINTETICO.search(linha)
    if historico:
        ancoras.append(historico.group(0))
    return ancoras


def _linhas_partidas_entre_paginas(linhas, textos_das_paginas):
    """Para cada linha, localiza a(s) página(s) de CADA âncora
    (`_ancoras_da_linha`) por substring (a ordem interna da página não
    importa: só a MEMBRESIA numa página comum). Se todas as âncoras da
    linha caem numa página em COMUM, a linha não foi partida. Se caem em
    páginas diferentes, foi. Se uma âncora não é achada em página nenhuma,
    isso é reportado À PARTE — é falha de extração (âncora rara demais ou
    ausente do texto pintado), não prova de corte entre páginas."""
    partidas = []
    ancoras_ausentes = []
    for linha in linhas:
        ancoras = _ancoras_da_linha(linha)
        if not ancoras:
            continue
        paginas_por_ancora = []
        faltou = False
        for ancora in ancoras:
            paginas = {i for i, t in enumerate(textos_das_paginas) if ancora in t}
            if not paginas:
                ancoras_ausentes.append((linha[:80], ancora))
                faltou = True
                break
            paginas_por_ancora.append(paginas)
        if faltou:
            continue
        comuns = set.intersection(*paginas_por_ancora)
        if not comuns:
            partidas.append((linha[:80], [sorted(p) for p in paginas_por_ancora]))
    return {"partidas": partidas, "ancoras_ausentes": ancoras_ausentes}


def _medir(paginas, pasta_saida):
    relatorio = {}
    for nome, html in paginas.items():
        thead_m = _PADRAO_THEAD.search(html)
        tbody_m = _PADRAO_TBODY.search(html)
        cabecalho = _texto_sem_tags(thead_m.group(1)) if thead_m else None
        linhas = (
            [
                _texto_sem_tags(tr)
                for tr in _PADRAO_TR.findall(tbody_m.group(1))
                if _texto_sem_tags(tr)
            ]
            if tbody_m
            else []
        )

        relatorio[nome] = {}
        for modo_nome in MODOS_DE_IMPRESSAO:
            caminho_pdf = pasta_saida / f"{nome}-{modo_nome}.pdf"
            paginas_no_pdf = _numero_de_paginas(caminho_pdf)
            textos = _texto_por_pagina(caminho_pdf, paginas_no_pdf)
            texto_completo = " ".join(textos)
            relatorio[nome][modo_nome] = {
                "arquivo": str(caminho_pdf),
                "folhas": paginas_no_pdf,
                "cabecalho_repete_em_todas_as_paginas": (
                    _cabecalho_repete_em_todas_as_paginas(cabecalho, textos) if cabecalho else None
                ),
                "linhas_partidas_entre_paginas": _linhas_partidas_entre_paginas(linhas, textos),
                # BL-332/BL-338 (Fred, fora do escopo desta etapa — ver a
                # docstring do módulo): só REPORTADO, nunca corrigido aqui.
                "dataledger_no_texto_impresso": "DataLedger" in texto_completo,
            }
    return relatorio


def main(argv):
    _exigir_ferramentas_de_pdf()
    _exigir_python_do_sistema_com_playwright()

    paginas = _renderizar_paginas()

    pasta_informada = Path(argv[0]).resolve() if argv else None
    with tempfile.TemporaryDirectory(prefix="dl-medir-impressao-") as pasta_temp:
        pasta_html = Path(pasta_temp) / "html"
        pasta_html.mkdir()
        for nome, html in paginas.items():
            (pasta_html / f"{nome}.html").write_text(html, encoding="utf-8")

        pasta_saida = pasta_informada or (Path(pasta_temp) / "pdfs")
        pasta_saida.mkdir(parents=True, exist_ok=True)

        _gerar_pdfs(pasta_html, pasta_saida, list(paginas))
        relatorio = _medir(paginas, pasta_saida)

    print(json.dumps(relatorio, ensure_ascii=False, indent=2))

    for nome, modos in relatorio.items():
        for modo_nome, medida in modos.items():
            aviso_dataledger = (
                " [DataLedger no texto impresso]" if medida["dataledger_no_texto_impresso"] else ""
            )
            n_partidas = len(medida["linhas_partidas_entre_paginas"]["partidas"])
            n_ausentes = len(medida["linhas_partidas_entre_paginas"]["ancoras_ausentes"])
            aviso_partidas = f" [{n_partidas} linha(s) partida(s)]" if n_partidas else ""
            aviso_ausentes = f" [{n_ausentes} âncora(s) não encontrada(s)]" if n_ausentes else ""
            aviso_partidas = aviso_partidas + aviso_ausentes
            print(
                f"{nome} ({modo_nome}): {medida['folhas']} folha(s), "
                f"cabeçalho repetido: {medida['cabecalho_repete_em_todas_as_paginas']}"
                f"{aviso_partidas}{aviso_dataledger}"
            )
    if pasta_informada:
        print(f"\nPDFs preservados em: {pasta_informada}")


if __name__ == "__main__":
    main(sys.argv[1:])
