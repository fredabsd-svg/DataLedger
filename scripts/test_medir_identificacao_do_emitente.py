"""Testes de `medir_identificacao_do_emitente.py` — DL-028 fatia 2
(docs/planos/DL-028-o-juiz-aponta-para-o-produto.md) e BL-434 (décima
primeira auditoria, rodada 2 da DL-029,
docs/planos/DL-029-a-frase-executavel-do-criterio-9.md).

**Por que este arquivo existe agora, e não na fatia 1.** Enquanto o
instrumento era só ferramenta de BANCADA (fatia 1), o precedente de
`scripts/medir_impressao.py` (zero cobertura `pytest`, por depender de
Playwright/Chromium/banco) era razoável. A partir da fatia 2 este
instrumento **reprova pull request** — e uma ferramenta que reprova PR é
infraestrutura da equipe: um erro nela ou trava todo mundo com falso alarme,
ou aprova em silêncio um documento sem emitente. As duas coisas custam mais
do que escrever este arquivo.

**DUAS classes de teste, desde o BL-434 — não confunda uma com a outra.**

1. **Funções PURAS** (a maioria do arquivo): não precisam de Playwright nem
   de Django — a checagem de "tinta invisível" (`_tinta_invisivel`), a
   distinção entre falha de INFRAESTRUTURA (código de saída `2`,
   `_recusar`) e falha de CONTEÚDO (código `1`, `_reprovar_por_conteudo`),
   a rasterização em cor, o oráculo de contraste, etc. Rodam em
   MILISSEGUNDOS, sempre, em qualquer ambiente.
2. **`test_ponta_a_ponta_*`** (seção própria, ao final): rodam
   `instrumento.main()` de VERDADE — Django real, subprocesso real do
   Python do sistema, Playwright/Chromium real, poppler-utils real — contra
   um cenário sintético e sabotagens aplicadas só EM MEMÓRIA (nunca em
   `static/css/base.css` nem em `templates/**`). Existem porque a décima
   primeira auditoria mediu que a classe 1, sozinha, deixa passar defeito
   de ORDEM/ALCANÇABILIDADE de código — o L1/BL-427 (uma cláusula da frase
   escrita em código que NUNCA executava) era exatamente esse tipo de
   defeito, e nenhum teste puro o alcançava. PULAM (não falham) com o
   motivo nomeado quando o ambiente não tem Chromium lançável ou
   poppler-utils no PATH — ver `_diagnostico_ambiente_ponta_a_ponta`.

Importar este arquivo NÃO exige Playwright nem banco para a classe 1: o
módulo só toca Django/Playwright DENTRO de funções, nunca no carregamento do
arquivo (ver a docstring dele, "Os dois interpretadores") — mas o
DIAGNÓSTICO de disponibilidade da classe 2 roda no CARREGAMENTO deste
arquivo de teste (não do instrumento), porque `pytest.mark.skipif` precisa
da decisão na COLETA, e é um lançamento de Chromium real, não um mock
(AGENTS.md §7: "mocks são adequados para testes isolados, mas não comprovam
a integração real").
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import medir_identificacao_do_emitente as instrumento  # noqa: E402
import pytest  # noqa: E402

# ---------------------------------------------------------------------------
# _tinta_invisivel — fecha o limite declarado de `visivelDeVerdade` (ver o
# comentário em sonda_visibilidade.js_sonda_container_e_filhos): texto com
# `color: transparent` passa por `checkVisibility`, área e alcançabilidade
# — só o alfa da cor computada denuncia a tinta que não pinta pixel nenhum.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cor_css", "esperado"),
    [
        # Alfa ZERO — a construção medida no H1 (`color: transparent`), que
        # a sonda de visibilidade sozinha NÃO pega (checkVisibility/área/
        # rolagem continuam "visível"). MEDIDO construindo o instrumento:
        # a primeira versão passava, sem esta checagem.
        ("rgba(0, 0, 0, 0)", True),
        ("rgba(255, 255, 255, 0)", True),
        ("rgba(10, 20, 30, 0.0)", True),
        # Tinta normal — opaca (sem componente alfa, `rgb(...)`) ou alfa 1.
        ("rgb(0, 0, 0)", False),
        ("rgba(0, 0, 0, 1)", False),
        # Semitransparente NÃO é a construção medida (alfa > 0, o pixel
        # ainda pinta algo) — este instrumento não reprova por contraste
        # baixo, só por tinta que não pinta NADA. Distinção deliberada,
        # não esquecimento: contraste é problema de outro instrumento
        # (`scripts/juiz.py`, para a tela).
        ("rgba(1, 2, 3, 0.5)", False),
        # Entradas degeneradas: nunca finge certeza que não tem.
        (None, False),
        ("", False),
        ("var(--nao-resolvido)", False),
    ],
)
def test_tinta_invisivel(cor_css, esperado):
    assert instrumento._tinta_invisivel(cor_css) is esperado


# ---------------------------------------------------------------------------
# A distinção infra (código 2) vs. conteúdo (código 1) — BL-356. O job da
# fatia 2 lê o código de saída para decidir a mensagem que mostra a quem
# abre o PR ("não consegui subir o navegador" vs. "o documento saiu sem
# emitente" são coisas diferentes, e precisam de reação diferente).
# ---------------------------------------------------------------------------


def test_recusar_sai_com_codigo_dois_de_infraestrutura(capsys):
    with pytest.raises(SystemExit) as excinfo:
        instrumento._recusar("motivo qualquer")
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "motivo qualquer" in saida.err


def test_reprovar_por_conteudo_sai_com_codigo_um(capsys):
    with pytest.raises(SystemExit) as excinfo:
        instrumento._reprovar_por_conteudo("balancete sem emitente")
    assert excinfo.value.code == 1
    saida = capsys.readouterr()
    assert "REPROVADO:" in saida.err
    assert "balancete sem emitente" in saida.err


def test_recusar_e_reprovar_por_conteudo_nunca_compartilham_codigo():
    """O contrato central: quem lê o código de saída (o job de CI, ou um
    humano) tem que conseguir separar as duas classes de falha SEM ler a
    mensagem. Testado aqui diretamente contra os dois códigos, não contra
    um número mágico repetido em cada teste acima — se algum dia alguém
    igualar os dois valores, este teste nomeia exatamente por quê isso é
    errado."""
    try:
        instrumento._recusar("x")
    except SystemExit as erro_infra:
        codigo_infra = erro_infra.code
    try:
        instrumento._reprovar_por_conteudo("y")
    except SystemExit as erro_conteudo:
        codigo_conteudo = erro_conteudo.code
    assert codigo_infra != codigo_conteudo, (
        "falha de infraestrutura e falha de conteúdo saindo com o MESMO "
        "código — BL-356: quem chama este script não consegue mais "
        "distinguir 'não consegui subir o navegador' de "
        "'o documento saiu sem emitente' pelo código de saída"
    )


# ---------------------------------------------------------------------------
# _com_saida_de_infraestrutura — RENORMALIZA a saída de funções reaproveitadas
# de medir_impressao.py (que saem com sys.exit(str), código 1 por padrão)
# para código 2, preservando a mensagem. Testado com funções FALSAS — não
# chama medir_impressao de verdade, que precisaria de Django.
# ---------------------------------------------------------------------------


def test_com_saida_de_infraestrutura_repassa_retorno_normal():
    resultado = instrumento._com_saida_de_infraestrutura(lambda: "valor qualquer")
    assert resultado == "valor qualquer"


def test_com_saida_de_infraestrutura_repassa_argumentos():
    resultado = instrumento._com_saida_de_infraestrutura(lambda a, b: a + b, 2, b=3)
    assert resultado == 5


def test_com_saida_de_infraestrutura_renormaliza_sys_exit_str_para_dois(capsys):
    def falha_como_medir_impressao():
        # O MESMO padrão de `medir_impressao._exigir_banco_descartavel` e
        # companhia: `sys.exit("Recusado: ...")`, que por si só sai com
        # código 1 (o mesmo da REPROVAÇÃO de conteúdo) — exatamente o que
        # este wrapper existe para corrigir.
        sys.exit("Recusado: banco não confirmado")

    with pytest.raises(SystemExit) as excinfo:
        instrumento._com_saida_de_infraestrutura(falha_como_medir_impressao)
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "banco não confirmado" in saida.err


def test_com_saida_de_infraestrutura_nao_mascara_excecao_diferente_de_systemexit():
    def explode():
        raise ValueError("isto não é uma recusa, é um bug")

    with pytest.raises(ValueError):
        instrumento._com_saida_de_infraestrutura(explode)


# ---------------------------------------------------------------------------
# BL-378 (achado J7 da nona auditoria): `pdftotext`/`pdftoppm` PRESENTES no
# PATH mas QUEBRADOS (biblioteca do sistema faltando, I/O, etc.) são falha
# de INFRAESTRUTURA (código 2), nunca REPROVAÇÃO de conteúdo (código 1) —
# a inversão exata do BL-370. Testado contra um binário FALSO de verdade,
# executado via subprocess (não um mock de `subprocess.run`): o mesmo
# método que o auditor usou para reproduzir o defeito ("`pdftotext`
# presente mas quebrado, injetado antes no PATH"). Não precisa de Django
# nem de Playwright — só do `PATH` do processo de teste.
# ---------------------------------------------------------------------------


@pytest.fixture
def path_com_binario_quebrado(tmp_path, monkeypatch):
    """Prepara um diretório com um executável `nome` que sempre falha
    (`exit 1`, imprime uma mensagem fixa em stderr) e o coloca na FRENTE
    do `PATH` — o subprocesso encontra ele antes do binário de verdade."""

    def _preparar(nome):
        caminho = tmp_path / nome
        caminho.write_text("#!/bin/sh\necho 'binario de teste quebrado' >&2\nexit 1\n")
        caminho.chmod(0o755)
        monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
        return caminho

    return _preparar


def test_texto_do_pdf_com_pdftotext_quebrado_recusa_em_vez_de_reprovar(
    path_com_binario_quebrado, capsys
):
    path_com_binario_quebrado("pdftotext")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._texto_do_pdf("qualquer.pdf")
    assert excinfo.value.code == 2  # nunca 1 — não é veredito sobre o produto
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "pdftotext" in saida.err


def test_palavras_da_pagina_com_pdftotext_quebrado_recusa(path_com_binario_quebrado, capsys):
    path_com_binario_quebrado("pdftotext")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._palavras_da_pagina("qualquer.pdf")
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err


def test_rasterizar_pagina_com_pdftoppm_quebrado_recusa(path_com_binario_quebrado, capsys):
    path_com_binario_quebrado("pdftoppm")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._rasterizar_pagina("qualquer.pdf")
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "pdftoppm" in saida.err


def test_total_de_paginas_com_pdfinfo_quebrado_recusa(path_com_binario_quebrado, capsys):
    # DL-029/C1: `_total_de_paginas` é o que permite ao oráculo do papel
    # procurar uma linha em páginas além da primeira (K7/BL-410) — a MESMA
    # classe de falha de infraestrutura de `pdftotext`/`pdftoppm` acima.
    path_com_binario_quebrado("pdfinfo")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._total_de_paginas("qualquer.pdf")
    assert excinfo.value.code == 2  # nunca 1 — não é veredito sobre o produto
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "pdfinfo" in saida.err


def test_total_de_paginas_le_a_saida_do_pdfinfo(tmp_path, monkeypatch):
    # `pdfinfo` de verdade não é chamado aqui — só o CONTRATO de leitura da
    # saída (a linha "Pages: N"), com um binário FALSO que imprime uma
    # saída fixa, o mesmo padrão de `path_com_binario_quebrado` acima, sem
    # exigir um PDF real.
    caminho = tmp_path / "pdfinfo"
    caminho.write_text(
        "#!/bin/sh\n"
        "cat <<'EOF'\n"
        "Title:          -\n"
        "Producer:       Skia/PDF\n"
        "Pages:          3\n"
        "Page size:      595.32 x 841.92 pts (A4)\n"
        "EOF\n"
    )
    caminho.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    assert instrumento._total_de_paginas("qualquer.pdf") == 3


# ---------------------------------------------------------------------------
# C5 nos METADADOS do PDF (achado do arquiteto-senior no meio da etapa,
# não do plano original): "a folha A4 exportada … não carrega nenhum
# identificador do fornecedor" cobre o ARQUIVO PDF inteiro, não só o
# texto visível na folha — `<title>` de templates/base.html alimenta
# `/Title` do PDF exportado. MEDIDO (não hipotetizado), em cópia isolada,
# contra as três telas reais deste instrumento — ver o comentário de
# `_CAMPOS_DE_METADADO_PDF`, acima do código, para a saída completa de
# `pdfinfo`.
# ---------------------------------------------------------------------------


def test_metadados_do_pdf_com_pdfinfo_quebrado_recusa(path_com_binario_quebrado, capsys):
    path_com_binario_quebrado("pdfinfo")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._metadados_do_pdf("qualquer.pdf")
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "pdfinfo" in saida.err


def test_metadados_do_pdf_le_titulo_autor_criador_produtor(tmp_path, monkeypatch):
    # Saída MEDIDA de verdade contra o Balancete real (ver o comentário de
    # `_CAMPOS_DE_METADADO_PDF`): `Author` AUSENTE da saída do poppler
    # quando o campo está vazio — este teste confirma que a ausência vira
    # string vazia, nunca erro nem `KeyError`.
    caminho = tmp_path / "pdfinfo"
    caminho.write_text(
        "#!/bin/sh\n"
        "cat <<'EOF'\n"
        "Title:           Balancete — Comércio Sintético de Materiais Ltda\n"
        "Creator:         Chromium\n"
        "Producer:        Skia/PDF m153\n"
        "Pages:           4\n"
        "EOF\n",
        encoding="utf-8",
    )
    caminho.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ['PATH']}")
    metadados = instrumento._metadados_do_pdf("qualquer.pdf")
    assert metadados["Title"] == "Balancete — Comércio Sintético de Materiais Ltda"
    assert metadados["Creator"] == "Chromium"
    assert metadados["Producer"] == "Skia/PDF m153"
    assert metadados["Author"] == ""  # ausente na saída -> vazio, não erro


def test_checar_marca_do_fornecedor_nos_metadados_acha_no_titulo():
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    metadados = {
        "Title": "Relatório — DataLedger",
        "Author": "",
        "Creator": "Chromium",
        "Producer": "Skia/PDF m153",
    }
    assert instrumento._checar_marca_do_fornecedor_nos_metadados(metadados, marca_normalizada) == (
        "Title"
    )


def test_checar_marca_do_fornecedor_nos_metadados_pega_grafia_normalizada():
    # A MESMA propriedade do C5 no corpo do PDF — caixa/espaço/pontuação
    # não escondem o identificador nos metadados.
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    metadados = {"Title": "gerado por DATA-LEDGER", "Author": "", "Creator": "", "Producer": ""}
    assert instrumento._checar_marca_do_fornecedor_nos_metadados(metadados, marca_normalizada) == (
        "Title"
    )


def test_checar_marca_do_fornecedor_nos_metadados_devolve_none_quando_limpo():
    # MEDIDO: é exatamente o estado ATUAL do produto (ver o comentário de
    # `_CAMPOS_DE_METADADO_PDF`) — `Creator`/`Producer` são identidade do
    # Chromium/Skia, nunca do produto, e o `Title` das telas com timbre já
    # não carrega o sufixo do fornecedor (BL-332/RC-97).
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    metadados = {
        "Title": "Balancete — Comércio Sintético de Materiais Ltda",
        "Author": "",
        "Creator": "Chromium",
        "Producer": "Skia/PDF m153",
    }
    assert instrumento._checar_marca_do_fornecedor_nos_metadados(metadados, marca_normalizada) is (
        None
    )


# ---------------------------------------------------------------------------
# M2/BL-444 (décima segunda auditoria, docs/auditorias/2026-09-20-dl-029-
# dl-030-rodada-12.md) — TERCEIRO canal do C5: anotação de link (`/URI`
# dentro de `/Annot`). MEDIDO pelo auditor: `<a href="https://
# dataledger.com.br/">Emitido pelo sistema</a>` no corpo do documento
# grava `/URI (https://dataledger.com.br/)` no PDF, invisível a
# `pdftotext` (só lê o TEXTO âncora) e ausente do dicionário `Info` — o
# C5 aprovava com `exit 0`. Testado aqui com bytes SINTÉTICOS de PDF (o
# MESMO padrão dos testes de PGM/PPM acima) — sem `pdftotext`/`pdfinfo`
# de verdade, só o CONTRATO de extração.
# ---------------------------------------------------------------------------


def test_anotacoes_de_link_do_pdf_extrai_uri_simples(tmp_path):
    caminho = tmp_path / "sintetico.pdf"
    caminho.write_bytes(
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Type /Annot /Subtype /Link /Rect [0 0 1 1] "
        b"/A << /S /URI /URI (https://dataledger.com.br/) >> >>\n"
        b"endobj\n"
        b"%%EOF\n"
    )
    assert instrumento._anotacoes_de_link_do_pdf(caminho) == ["https://dataledger.com.br/"]


def test_anotacoes_de_link_do_pdf_desescapa_parenteses_da_string_literal_do_pdf(tmp_path):
    # PDF Reference §7.3.4.2: `\(` e `\)` dentro de uma string literal
    # representam parênteses LITERAIS do conteúdo, não delimitadores — um
    # parser ingênuo que corta no primeiro `)` cortaria a URL no meio.
    caminho = tmp_path / "sintetico.pdf"
    caminho.write_bytes(b"1 0 obj << /A << /URI (https://exemplo.com.br/a\\(1\\)) >> >> endobj\n")
    assert instrumento._anotacoes_de_link_do_pdf(caminho) == ["https://exemplo.com.br/a(1)"]


def test_anotacoes_de_link_do_pdf_le_varias_anotacoes_na_ordem(tmp_path):
    # O padrão REAL do produto: cada linha de Balancete/Diário/Razão vira
    # um link interno de volta para a aplicação — 268 delas num Balancete
    # (medido pelo auditor). Este teste confirma que TODAS são lidas, não
    # só a primeira.
    caminho = tmp_path / "sintetico.pdf"
    caminho.write_bytes(
        b"1 0 obj << /A << /URI (file:///contabilidade/1/) >> >> endobj\n"
        b"2 0 obj << /A << /URI (file:///contabilidade/2/) >> >> endobj\n"
    )
    assert instrumento._anotacoes_de_link_do_pdf(caminho) == [
        "file:///contabilidade/1/",
        "file:///contabilidade/2/",
    ]


def test_anotacoes_de_link_do_pdf_devolve_lista_vazia_sem_anotacao_nenhuma(tmp_path):
    caminho = tmp_path / "sintetico.pdf"
    caminho.write_bytes(b"%PDF-1.4\nsem anotacao de link nenhuma aqui\n%%EOF\n")
    assert instrumento._anotacoes_de_link_do_pdf(caminho) == []


def test_anotacao_de_link_com_marca_do_fornecedor_acha_o_alvo_sabotado():
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    anotacoes = ["file:///contabilidade/1/", "https://dataledger.com.br/"]
    assert (
        instrumento._anotacao_de_link_com_marca_do_fornecedor(anotacoes, marca_normalizada)
        == "https://dataledger.com.br/"
    )


def test_anotacao_de_link_com_marca_do_fornecedor_pega_grafia_normalizada():
    # A MESMA propriedade do C5 nos outros dois canais — caixa/pontuação
    # não escondem o identificador na anotação de link.
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    anotacoes = ["https://DATA-LEDGER.example/"]
    assert (
        instrumento._anotacao_de_link_com_marca_do_fornecedor(anotacoes, marca_normalizada)
        == "https://DATA-LEDGER.example/"
    )


def test_anotacao_de_link_com_marca_do_fornecedor_devolve_none_quando_limpo():
    # MEDIDO: o padrão real do produto — anotações INTERNAS (`file:///
    # contabilidade/painel/...`), nenhuma com o domínio do fornecedor.
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    anotacoes = [
        "file:///contabilidade/painel/empresas/1/razao/17/?inicio=2026-03-01",
        "file:///contabilidade/painel/empresas/1/lancamento/42/",
    ]
    resultado = instrumento._anotacao_de_link_com_marca_do_fornecedor(anotacoes, marca_normalizada)
    assert resultado is None


# ---------------------------------------------------------------------------
# Piso de regressão (TELAS_MINIMAS_COM_TIMBRE_ESPERADAS) — a resposta ao
# eixo do BL-363 no instrumento novo (Fred/arquiteto-senior, DL-028 fatia
# 2): MEDIDO construindo o instrumento que uma sabotagem em
# `templates/contabilidade/razao.html` que remove o bloco do timbre
# INTEIRO faz a derivação por presença de marcador simplesmente NÃO achar
# a tela — sem este piso, o instrumento saía com código 0 (sucesso) e
# "2 telas derivadas", nunca nomeando a Razão. Este teste não reproduz a
# sabotagem (exigiria Django) — verifica só a CONSTANTE que ancora a
# checagem, para que ninguém a esvazie ou apague sem notar.
# ---------------------------------------------------------------------------


def test_piso_de_telas_esperadas_tem_as_tres_telas_do_criterio_3_da_dl026():
    # BL-374 (achado J3 da nona auditoria): o piso passou a ser chaveado
    # pelo NOME COMPLETO da rota (`namespace:nome`), nunca pelo nome
    # curto — nome curto colide entre apps (ver o comentário da
    # constante). Este teste fixa os TRÊS nomes completos esperados, para
    # ninguém trocar de volta para o nome curto sem notar.
    assert instrumento.TELAS_MINIMAS_COM_TIMBRE_ESPERADAS == frozenset(
        {
            "contabilidade_web:balancete",
            "contabilidade_web:diario",
            "contabilidade_web:razao",
        }
    )


# ---------------------------------------------------------------------------
# Oráculo do papel (BL-372, achado J1 da nona auditoria) — funções PURAS
# (parsing de PGM, contagem de pixel, casamento de bbox), testadas com
# bytes/estruturas SINTÉTICAS, sem chamar `pdftoppm`/`pdftotext` de
# verdade (essas chamadas de subprocesso são verificadas por EXECUÇÃO de
# bancada, o mesmo padrão que `_texto_do_pdf` já tinha antes desta etapa
# — AGENTS.md §7: mock de subprocesso provaria só que o mock funciona).
# ---------------------------------------------------------------------------


def _pgm_sintetico(largura, altura, valores):
    """Monta bytes de um PGM binário (`P5`) `largura`×`altura`, 8 bits,
    com `valores` (lista de `int`, um por pixel, ordem linha-a-linha) —
    o MESMO formato que `pdftoppm -gray` produz, sem depender dele."""
    assert len(valores) == largura * altura
    cabecalho = f"P5\n{largura} {altura}\n255\n".encode("ascii")
    return cabecalho + bytes(valores)


def test_pgm_para_matriz_le_cabecalho_e_corpo():
    dados = _pgm_sintetico(3, 2, [10, 20, 30, 200, 210, 220])
    largura, altura, corpo = instrumento._pgm_para_matriz(dados)
    assert (largura, altura) == (3, 2)
    assert list(corpo) == [10, 20, 30, 200, 210, 220]


def test_pgm_para_matriz_ignora_comentario_no_cabecalho():
    # O formato PGM permite `#comentário\n` entre os tokens do cabeçalho
    # — poppler não os emite, mas um parser que quebra num comentário
    # válido é um parser errado, não um limite documentado (ver o
    # comentário de `_pgm_para_matriz`).
    dados = b"P5\n#gerado para teste\n2 1\n255\n" + bytes([5, 250])
    largura, altura, corpo = instrumento._pgm_para_matriz(dados)
    assert (largura, altura) == (2, 1)
    assert list(corpo) == [5, 250]


def test_pgm_para_matriz_recusa_assinatura_errada():
    with pytest.raises(ValueError):
        instrumento._pgm_para_matriz(b"P6\n1 1\n255\n\x00")


def test_pgm_para_matriz_recusa_corpo_truncado():
    cabecalho = b"P5\n2 2\n255\n"
    with pytest.raises(ValueError):
        instrumento._pgm_para_matriz(cabecalho + bytes([0, 0]))  # faltam 2 bytes


def test_pgm_para_matriz_recusa_maxval_de_16_bits():
    with pytest.raises(ValueError):
        instrumento._pgm_para_matriz(b"P5\n1 1\n65535\n\x00\x00")


# ---------------------------------------------------------------------------
# BL-429/DE-060 (décima primeira auditoria) — a rasterização em COR (PPM
# `P6`) que substitui `-gray` (PGM `P5`) no caminho de produção. O parser
# compartilha `_cabecalho_e_corpo_netpbm` com `_pgm_para_matriz` — os
# testes de PGM acima continuam cobrindo o cabeçalho comum; os daqui
# cobrem o que é ESPECÍFICO de 3 bytes por pixel.
# ---------------------------------------------------------------------------


def _ppm_sintetico(largura, altura, pixels_rgb):
    """Monta bytes de um PPM binário (`P6`) `largura`×`altura`, 8 bits por
    canal, com `pixels_rgb` (lista de tuplas `(r, g, b)`, ordem
    linha-a-linha) — o MESMO formato que `pdftoppm` produz nativamente
    SEM `-gray`/`-mono`/`-png`, sem depender dele."""
    assert len(pixels_rgb) == largura * altura
    cabecalho = f"P6\n{largura} {altura}\n255\n".encode("ascii")
    corpo = bytes(byte for pixel in pixels_rgb for byte in pixel)
    return cabecalho + corpo


def test_ppm_para_matriz_le_cabecalho_e_corpo_intercalado():
    dados = _ppm_sintetico(2, 1, [(255, 0, 0), (0, 128, 255)])
    largura, altura, corpo = instrumento._ppm_para_matriz(dados)
    assert (largura, altura) == (2, 1)
    assert list(corpo) == [255, 0, 0, 0, 128, 255]


def test_ppm_para_matriz_recusa_assinatura_errada():
    with pytest.raises(ValueError):
        instrumento._ppm_para_matriz(b"P5\n1 1\n255\n\x00")


def test_ppm_para_matriz_recusa_corpo_truncado():
    cabecalho = b"P6\n2 1\n255\n"
    with pytest.raises(ValueError):
        instrumento._ppm_para_matriz(cabecalho + bytes([0, 0, 0]))  # faltam 3 bytes (1 pixel)


def test_cor_do_papel_e_a_moda_por_canal():
    # Fundo branco majoritário, com um pixel de "tinta" azul no meio —
    # a moda de CADA canal, isoladamente, ainda recompõe o branco.
    pixels = [(255, 255, 255)] * 8 + [(10, 20, 200)]
    dados = _ppm_sintetico(3, 3, pixels)
    assert instrumento._cor_do_papel(dados) == (255, 255, 255)


def test_luminancia_relativa_rgb_cinza_puro_bate_com_a_versao_de_um_canal():
    # Para R=G=B (cinza puro), a luminância RGB pondera os TRÊS canais
    # com o MESMO valor de entrada — matematicamente idêntica a aplicar
    # `_luminancia_relativa_srgb` uma vez (0,2126+0,7152+0,0722 == 1).
    for nivel in (0, 64, 128, 200, 255):
        esperado = instrumento._luminancia_relativa_srgb(nivel / 255)
        assert instrumento._luminancia_relativa_rgb(nivel, nivel, nivel) == pytest.approx(
            esperado, abs=1e-9
        )


def test_razao_de_contraste_rgb_vermelho_puro_sobre_branco_e_a_razao_wcag_real():
    # BL-429/L3: a razão WCAG 2.2 REAL de #FF0000 sobre #FFFFFF é 4,00:1
    # — MEDIDO pelo auditor contra o instrumento em cinza, que relatava
    # 8,45:1 (2,1× mais contraste do que existe). Esta é a fórmula que a
    # etiqueta da mensagem promete.
    razao = instrumento._razao_de_contraste_rgb((255, 0, 0), (255, 255, 255))
    assert razao == pytest.approx(4.00, abs=0.01)


def test_razao_de_contraste_rgb_diverge_da_versao_em_cinza_para_tinta_colorida():
    # A divergência que o BL-429 mede, ao lado da propriedade — DE-060
    # exige que o substituto (cinza) e a divergência dele fiquem medidos
    # juntos, não só a correção. `pdftoppm -gray` converteria #FF0000
    # para um nível de cinza próximo a 76 (luma padrão) — a razão em
    # cinza contra 255 fica muito acima da razão RGB real.
    razao_rgb = instrumento._razao_de_contraste_rgb((255, 0, 0), (255, 255, 255))
    razao_cinza_aproximada = instrumento._razao_de_contraste(255, 76)
    assert razao_cinza_aproximada > razao_rgb * 1.5


def test_razao_de_contraste_rgb_preto_e_branco_e_o_maximo_da_escala():
    assert instrumento._razao_de_contraste_rgb((0, 0, 0), (255, 255, 255)) == pytest.approx(
        21.0, abs=0.01
    )


def test_razao_de_contraste_rgb_e_simetrica():
    a = instrumento._razao_de_contraste_rgb((10, 20, 30), (250, 240, 230))
    b = instrumento._razao_de_contraste_rgb((250, 240, 230), (10, 20, 30))
    assert a == pytest.approx(b)


def test_diagnostico_de_contraste_na_faixa_cor_conta_so_dentro_do_retangulo():
    # MESMA estrutura de `test_diagnostico_de_contraste_na_faixa_conta_so_
    # dentro_do_retangulo` (versão cinza), em COR: uma faixa vermelha
    # (alto contraste RGB) cercada de branco (papel).
    largura, altura = 10, 10
    pixels = [(255, 255, 255)] * (largura * altura)
    # Linha y=5, x de 2 a 6 (5 pixels) pintada de vermelho puro.
    for x in range(2, 7):
        pixels[5 * largura + x] = (255, 0, 0)
    dados = _ppm_sintetico(largura, altura, pixels)
    # Retângulo em PONTOS de PDF: a 96 dpi, 1 ponto == 1 pixel (fator 1.0)
    # — mesma conversão de `DPI_ORACULO_DO_PAPEL`/`PONTOS_POR_POLEGADA`.
    retangulo_pt = (2 * 72 / 96, 5 * 72 / 96, 6 * 72 / 96, 5 * 72 / 96)
    # Piso de texto GRANDE (3,0), não o de texto normal (4,5) — a razão
    # RGB real do vermelho puro contra branco é 4,00:1 (ver o teste de
    # `_razao_de_contraste_rgb` acima), que passa o primeiro e NÃO passa
    # o segundo; usar 3,0 aqui isola a pergunta "conta só dentro do
    # retângulo" da pergunta "o piso é respeitado" (coberta pelo teste
    # seguinte).
    contagem, contraste_maximo = instrumento._diagnostico_de_contraste_na_faixa_cor(
        dados, retangulo_pt, cor_do_papel=(255, 255, 255), razao_minima=3.0, margem_px=0
    )
    assert contraste_maximo == pytest.approx(4.00, abs=0.01)
    assert contagem == 5  # os 5 pixels vermelhos, nenhum do fundo branco


def test_diagnostico_de_contraste_na_faixa_cor_respeita_a_razao_minima_informada():
    largura, altura = 6, 6
    pixels = [(255, 255, 255)] * (largura * altura)
    pixels[3 * largura + 3] = (255, 0, 0)  # vermelho puro, 4,00:1 contra branco
    dados = _ppm_sintetico(largura, altura, pixels)
    retangulo_pt = (3 * 72 / 96, 3 * 72 / 96, 3 * 72 / 96, 3 * 72 / 96)
    # Piso ABAIXO do contraste do vermelho: conta.
    contagem_abaixo, _ = instrumento._diagnostico_de_contraste_na_faixa_cor(
        dados, retangulo_pt, cor_do_papel=(255, 255, 255), razao_minima=3.0, margem_px=0
    )
    assert contagem_abaixo == 1
    # Piso ACIMA (o piso de texto normal do WCAG, 4,5:1): não conta.
    contagem_acima, _ = instrumento._diagnostico_de_contraste_na_faixa_cor(
        dados, retangulo_pt, cor_do_papel=(255, 255, 255), razao_minima=4.5, margem_px=0
    )
    assert contagem_acima == 0


def test_fator_altura_de_glifo_foi_removido_bl437():
    # BL-437 (verificação independente, rodada 3 da DL-029): a constante
    # FATOR_ALTURA_DE_GLIFO_SOBRE_FONTE_DECLARADA (rodada 2) media a
    # razão bbox/declarado numa família tipográfica só e não generalizava
    # entre famílias (0,93-0,97 em monospace/sans-serif/serif genéricos,
    # contra 1,088 medido na fonte do produto) — falso alarme em
    # `font-family: monospace` no PISO exato (11px). Foi REMOVIDA, não
    # ajustada — a correção substituta usa escala acumulada medida no
    # NAVEGADOR (`escala_acumulada`/`tamanho_efetivo_px`, ver o
    # comentário de `js_fonte_das_linhas`), que não depende de fonte
    # nenhuma. Este teste guarda que ela não volte por engano.
    assert not hasattr(instrumento, "FATOR_ALTURA_DE_GLIFO_SOBRE_FONTE_DECLARADA")


# ---------------------------------------------------------------------------
# C2 da DL-029 — contraste medido contra o fundo da PRÓPRIA folha, com o
# piso do WCAG 2.2 (1.4.3, "Contraste (Mínimo)", nível AA — W3C
# Recommendation, 5 de outubro de 2023), aplicado POR LINHA a partir do
# tamanho/peso de fonte REALMENTE renderizados. Decisão do
# arquiteto-senior: a versão anterior desta correção fixava uma razão
# ÚNICA (2,4) escolhida para caber entre dois casos de teste — a MESMA
# forma de defeito que esta etapa combate (BL-407/K4), só que como razão
# em vez de lista. Substituída por um padrão publicado e externo.
#
# ⚠️ EMPRÉSTIMO DECLARADO: o WCAG rege conteúdo WEB, não papel impresso,
# e não é norma contábil — adotado por ESCOLHA deste projeto, na falta de
# piso próprio para documento contábil (ver o comentário completo de
# RAZAO_MINIMA_WCAG_TEXTO_NORMAL, no módulo).
# ---------------------------------------------------------------------------


def test_razao_de_contraste_e_simetrica_e_minima_um():
    # Dois pixels idênticos: contraste mínimo possível, 1.0.
    assert instrumento._razao_de_contraste(200, 200) == pytest.approx(1.0)
    # Simétrica: não importa qual argumento é o mais claro.
    assert instrumento._razao_de_contraste(255, 0) == instrumento._razao_de_contraste(0, 255)


def test_razao_de_contraste_preto_e_branco_e_o_maximo_da_escala():
    # WCAG: preto puro contra branco puro é o contraste MÁXIMO (21:1).
    assert instrumento._razao_de_contraste(255, 0) == pytest.approx(21.0, abs=0.01)


def test_razao_de_contraste_valores_medidos_da_varredura_de_opacidade():
    # MEDIDO em cópia isolada, varrendo `opacity` no timbre real (ver o
    # relatório desta etapa): a 0,40, a linha mais fraca do timbre mede
    # 2,81:1 — ABAIXO do piso de texto grande do WCAG (3:1) e do piso de
    # texto normal (4,5:1). A 0,60, já ultrapassa os dois (5,74:1).
    assert instrumento._razao_de_contraste(255, 154) == pytest.approx(2.814, abs=0.01)
    assert instrumento._razao_de_contraste(255, 104) == pytest.approx(5.572, abs=0.01)


def test_razoes_minimas_wcag_sao_as_do_padrao_publicado():
    # 4,5:1 (texto normal) e 3:1 (texto grande/negrito) são os dois
    # números do Critério de Sucesso 1.4.3 do WCAG 2.2 — não escolhas
    # deste projeto.
    assert instrumento.RAZAO_MINIMA_WCAG_TEXTO_NORMAL == 4.5
    assert instrumento.RAZAO_MINIMA_WCAG_TEXTO_GRANDE == 3.0


def test_razao_minima_wcag_para_linha_texto_normal_pequeno():
    # 12px, peso 400 (o corpo do timbre): nem grande, nem negrito grande
    # — piso de texto NORMAL.
    assert instrumento._razao_minima_wcag_para_linha(12, 400) == 4.5


def test_razao_minima_wcag_para_linha_texto_grande_por_tamanho():
    # >= 18pt (24px CSS a 96dpi — 1pt = 96/72 px, NUNCA 72/96: achado
    # próprio corrigido nesta revisão, ver o comentário de
    # TAMANHO_MINIMO_TEXTO_GRANDE_PX) em QUALQUER peso é "texto grande".
    tamanho_18pt_em_px = 18 * (96 / 72)
    assert tamanho_18pt_em_px == pytest.approx(24.0)
    assert instrumento._razao_minima_wcag_para_linha(tamanho_18pt_em_px, 400) == 3.0
    # Uma fração abaixo de 18pt, no mesmo peso normal, continua "normal".
    assert instrumento._razao_minima_wcag_para_linha(tamanho_18pt_em_px - 0.5, 400) == 4.5


def test_razao_minima_wcag_para_linha_texto_grande_por_negrito():
    # >= 14pt (18,67px CSS) EM NEGRITO (peso >= 700) também é "grande" —
    # mesmo abaixo do limiar de 18pt que vale para peso normal.
    tamanho_14pt_em_px = 14 * (96 / 72)
    assert tamanho_14pt_em_px == pytest.approx(18.6667, abs=0.001)
    assert instrumento._razao_minima_wcag_para_linha(tamanho_14pt_em_px, 700) == 3.0
    # O MESMO tamanho, em peso normal, não se qualifica — só o negrito
    # baixa o limiar de tamanho.
    assert instrumento._razao_minima_wcag_para_linha(tamanho_14pt_em_px, 400) == 4.5


def test_razao_minima_wcag_para_linha_timbre_real_14px_peso_normal_e_texto_normal():
    # ACHADO PRÓPRIO/regressão: o bug de conversão (pontos↔pixels
    # invertido) fazia as linhas de 14px/peso 400 do timbre REAL (endereço
    # e registro profissional, MEDIDO via getComputedStyle no produto)
    # caírem em "texto grande" por engano — 14px está bem ABAIXO dos
    # 24px de 18pt, e peso 400 não é negrito, então nem o limiar de 14pt
    # bold se aplica. Tem de exigir o piso de texto NORMAL (4,5:1).
    assert instrumento._razao_minima_wcag_para_linha(14, 400) == 4.5
    # A razão social do timbre (negrito, 16px, MEDIDO via getComputedStyle)
    # também fica abaixo dos dois limiares de "grande" — 16px < 24px, e
    # 16px < 18,67px (o limiar do negrito) — então TAMBÉM exige 4,5:1.
    assert instrumento._razao_minima_wcag_para_linha(16, 700) == 4.5


def test_razao_minima_wcag_para_linha_negrito_pequeno_continua_normal():
    # Negrito sozinho não basta — precisa do tamanho mínimo de 14pt
    # também. Um negrito de 10px continua exigindo o piso de texto normal.
    assert instrumento._razao_minima_wcag_para_linha(10, 700) == 4.5


# ---------------------------------------------------------------------------
# BL-424 (verificação independente, depois do C2 fechar) — o piso de
# CONTAGEM sozinho aprovava `font-size: 8px` (contraste 19,8:1/9,29:1,
# muito acima do piso; 57–58 pixels, acima do piso de 40). A contagem
# deixou de guardar "o texto ficou pequeno demais?" quando o CONTRASTE
# passou a guardar "a tinta sumiu?" — TAMANHO_MINIMO_RENDERIZADO_PX fecha
# essa pergunta, como ESCOLHA DECLARADA (não padrão WCAG — o WCAG não
# define piso de tamanho para papel).
# ---------------------------------------------------------------------------


def test_tamanho_minimo_renderizado_px_bate_com_o_piso_legivel_ja_declarado_do_produto():
    # O valor NÃO é escolhido para bater com o corte antigo (8px passava,
    # 11 > 8 então a correção MUDA o veredito) — é emprestado de uma
    # decisão JÁ TOMADA pelo produto: `--tipo-2xs` em
    # static/css/base.css, documentado ali (BL-283) como "o próprio piso
    # legível já usado" para texto de interface. Lido do ARQUIVO real do
    # repositório — se o produto um dia mudar esse token, este teste é o
    # primeiro a notar a divergência (o mesmo padrão de
    # test_derivar_marca_do_fornecedor_le_do_template_real_do_produto).
    caminho_css = Path(__file__).resolve().parents[1] / "static" / "css" / "base.css"
    conteudo = caminho_css.read_text(encoding="utf-8")
    casamento = re.search(r"--tipo-2xs:\s*([\d.]+)rem", conteudo)
    assert casamento is not None, "static/css/base.css não declara mais --tipo-2xs em rem"
    tipo_2xs_em_px = float(casamento.group(1)) * 16  # 1rem = 16px, raiz padrão do produto
    assert tipo_2xs_em_px == pytest.approx(11.0, abs=0.01)
    assert instrumento.TAMANHO_MINIMO_RENDERIZADO_PX == pytest.approx(tipo_2xs_em_px, abs=0.01)


def test_luminancia_do_papel_e_a_moda_da_folha_inteira():
    # Fundo=255 dominante (17 dos 21 pixels) com um bloco de tinta
    # (0, 4 pixels) — a MODA tem de ser o fundo, não a média nem o valor
    # mais escuro.
    dados = _pgm_sintetico(7, 3, [255] * 17 + [0, 0, 0, 0])
    assert instrumento._luminancia_do_papel(dados) == 255


def test_niveis_de_cinza_com_contraste_suficiente_bate_com_razao_de_contraste():
    # O CONJUNTO pré-computado (usado pixel a pixel dentro da faixa) tem
    # de concordar, nível a nível, com `_razao_de_contraste` calculada
    # direto — mesma pergunta, dois caminhos. Testado com os DOIS pisos do
    # WCAG (a função agora recebe a razão explicitamente, nunca lê uma
    # constante única).
    for razao_minima in (3.0, 4.5):
        niveis = instrumento._niveis_de_cinza_com_contraste_suficiente(255, razao_minima)
        for nivel in (0, 100, 104, 127, 153, 154, 200, 255):
            esperado = instrumento._razao_de_contraste(255, nivel) >= razao_minima
            assert (nivel in niveis) is esperado


def test_diagnostico_de_contraste_na_faixa_conta_so_dentro_do_retangulo():
    # Página 10x10: um quadrado ESCURO (valor 0, contraste máximo contra
    # fundo 255) em x=2..4, y=2..4 (3x3=9 pixels), o resto BRANCO (255).
    # `margem_px=0` para o teste medir exatamente o retângulo pedido.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    for y in range(2, 5):
        for x in range(2, 5):
            valores[y * largura + x] = 0
    dados = _pgm_sintetico(largura, altura, valores)

    contagem, contraste_maximo = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(2, 2, 4, 4),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    assert contagem == 9  # o quadrado 3x3 inteiro, e nada além dele
    assert contraste_maximo == pytest.approx(21.0, abs=0.01)  # preto puro contra branco puro

    contagem_fora, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(6, 6, 8, 8),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    assert contagem_fora == 0


def test_diagnostico_de_contraste_na_faixa_respeita_a_razao_minima_informada():
    # 172 fica FORA do piso de texto normal (4,5:1) mas o teste confirma
    # que É a RAZÃO INFORMADA que decide, não uma constante interna:
    # com um piso mais frouxo (2,0), o MESMO pixel passa a contar.
    dados = _pgm_sintetico(1, 1, [172])
    contagem_normal, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 1, 1),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    contagem_frouxa, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 1, 1),
        luminancia_do_papel=255,
        razao_minima=2.0,
        dpi=72,
        margem_px=0,
    )
    assert contagem_normal == 0
    assert contagem_frouxa == 1


def test_diagnostico_de_contraste_na_faixa_usa_o_fundo_medido_nao_255():
    # C2: "o fundo da PRÓPRIA folha" — se o papel medido nesta rasterização
    # não é 255, a razão de contraste muda, e o mesmo pixel pode contar
    # DIFERENTE conforme o fundo informado. 120 contra 255 dá ~3,49:1
    # (>= 3,0); 120 contra ELE MESMO dá 1:1 (nunca >= 3,0).
    dados = _pgm_sintetico(1, 1, [120])
    contra_papel_branco, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 1, 1),
        luminancia_do_papel=255,
        razao_minima=3.0,
        dpi=72,
        margem_px=0,
    )
    contra_papel_escuro, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 1, 1),
        luminancia_do_papel=120,
        razao_minima=3.0,
        dpi=72,
        margem_px=0,
    )
    assert contra_papel_branco == 1  # 120 contra 255: contraste suficiente
    assert contra_papel_escuro == 0  # 120 contra ELE MESMO: contraste 1:1


def test_diagnostico_de_contraste_na_faixa_margem_expande_a_busca():
    # Pixel de contraste máximo (0) em x=5, y=5. Um retângulo pedido "ao
    # lado" (x=6..7) só o alcança com margem >= 1.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    valores[5 * largura + 5] = 0
    dados = _pgm_sintetico(largura, altura, valores)

    sem_margem, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(6, 5, 7, 6),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    com_margem, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(6, 5, 7, 6),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=1,
    )
    assert sem_margem == 0
    assert com_margem == 1

    # Margem grande perto da borda da página não estoura o índice (clampado).
    instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 1, 1),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=1000,
    )


def test_diagnostico_de_contraste_na_faixa_converte_pontos_para_pixel_pelo_dpi():
    # 1 ponto = 1/72 polegada; a 96 dpi, 1 ponto = 96/72 = 4/3 pixel. Um
    # retângulo de 3x3 PONTOS a 96 dpi cobre 4x4 PIXELS (arredondando para
    # baixo o início e para cima o fim) — confirma que a conversão de
    # unidade participa da conta, não o valor exato.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    for y in range(4):
        for x in range(4):
            valores[y * largura + x] = 0
    dados = _pgm_sintetico(largura, altura, valores)
    contagem, _ = instrumento._diagnostico_de_contraste_na_faixa(
        dados,
        retangulo_pt=(0, 0, 3, 3),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=96,
        margem_px=0,
    )
    assert contagem == 16  # 4x4, não 3x3 — a conversão de unidade aconteceu


def test_diagnostico_de_contraste_na_faixa_distingue_contraste_de_contagem():
    # A REGRA DUPLA (exigência do arquiteto-senior): uma faixa com tinta
    # CLARA DEMAIS (contraste máximo abaixo do piso) é uma causa; uma
    # faixa com tinta PRETA mas MINÚSCULA (poucos pixels, contraste
    # máximo alto) é outra. As dois cenários têm de ser DISTINGUÍVEIS pelo
    # `contraste_maximo_medido` devolvido, não só pela contagem.
    largura, altura = 5, 5
    # Cenário 1: tinta clara demais (nível 200) preenchendo a faixa toda.
    dados_contraste_insuficiente = _pgm_sintetico(largura, altura, [200] * (largura * altura))
    contagem_1, contraste_1 = instrumento._diagnostico_de_contraste_na_faixa(
        dados_contraste_insuficiente,
        retangulo_pt=(0, 0, 5, 5),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    assert contraste_1 < 4.5  # nenhum pixel jamais alcançaria o piso
    assert contagem_1 == 0

    # Cenário 2: tinta PRETA (contraste máximo altíssimo) mas só 1 pixel.
    valores_2 = [255] * (largura * altura)
    valores_2[12] = 0  # um único pixel preto no meio da faixa
    dados_contagem_insuficiente = _pgm_sintetico(largura, altura, valores_2)
    contagem_2, contraste_2 = instrumento._diagnostico_de_contraste_na_faixa(
        dados_contagem_insuficiente,
        retangulo_pt=(0, 0, 5, 5),
        luminancia_do_papel=255,
        razao_minima=4.5,
        dpi=72,
        margem_px=0,
    )
    assert contraste_2 == pytest.approx(21.0, abs=0.01)  # a tinta É preta
    assert contagem_2 == 1  # só 1 pixel — pouco, mas não é problema de contraste


# ---------------------------------------------------------------------------
# _bbox_da_linha — casamento de sequência de palavras do `pdftotext -bbox`
# contra o texto esperado de uma linha do timbre.
# ---------------------------------------------------------------------------


def _palavra(xmin, ymin, xmax, ymax, texto):
    return (float(xmin), float(ymin), float(xmax), float(ymax), texto)


def test_bbox_da_linha_encontra_sequencia_de_varias_palavras():
    palavras = [
        _palavra(0, 0, 10, 5, "EMPRESA"),  # ruído antes, não deve ser incluído
        _palavra(0, 10, 20, 20, "Escritório"),
        _palavra(22, 10, 40, 20, "Contábil"),
        _palavra(42, 10, 55, 20, "Sintético"),
        _palavra(57, 10, 65, 20, "ME"),
        _palavra(0, 30, 10, 35, "Balancete"),  # ruído depois
    ]
    caixa = instrumento._bbox_da_linha(palavras, "Escritório Contábil Sintético ME")
    assert caixa == (0, 10, 65, 20)


def test_bbox_da_linha_tolera_pontuacao_tokenizada_a_parte():
    # `pdftotext -bbox` pode devolver a vírgula/hífen como token PRÓPRIO,
    # colado ao caractere vizinho de forma diferente de `str.split()` —
    # MEDIDO com o endereço sintético real de
    # `scripts/semear_base_de_medicao.py`. O casamento é por
    # concatenação SEM espaço dos dois lados, então isto tem que casar
    # mesmo com uma tokenização "estranha".
    palavras = [
        _palavra(0, 0, 10, 10, "Rua"),
        _palavra(11, 0, 30, 10, "Sintética"),
        _palavra(31, 0, 45, 10, "100,"),
        _palavra(46, 0, 60, 10, "Sala"),
        _palavra(61, 0, 65, 10, "2"),
        _palavra(66, 0, 70, 10, "-"),
        _palavra(71, 0, 95, 10, "Palmas/TO"),
    ]
    caixa = instrumento._bbox_da_linha(palavras, "Rua Sintética 100, Sala 2 - Palmas/TO")
    assert caixa == (0, 0, 95, 10)


def test_bbox_da_linha_devolve_none_quando_a_linha_nao_aparece():
    palavras = [_palavra(0, 0, 10, 10, "Balancete")]
    assert instrumento._bbox_da_linha(palavras, "Escritório Contábil Sintético ME") is None


def test_bbox_da_linha_devolve_none_para_texto_esperado_vazio():
    assert instrumento._bbox_da_linha([_palavra(0, 0, 1, 1, "x")], "   ") is None


def test_bbox_da_linha_nao_casa_prefixo_parcial_de_uma_palavra_maior():
    # "ME" não deveria casar dentro de "MEDIÇÃO" nem coisa parecida —
    # como o casamento exige que a soma acumulada seja EXATAMENTE igual
    # ao alvo (não um prefixo dele), uma palavra maior nunca casa sozinha.
    palavras = [_palavra(0, 0, 10, 10, "MEDIÇÃO")]
    assert instrumento._bbox_da_linha(palavras, "ME") is None


# ---------------------------------------------------------------------------
# _localizar_bloco_do_timbre — C4/C3 da DL-029 (K2/BL-405, décima
# auditoria): ancora as N linhas do timbre por OCORRÊNCIA (bloco contíguo),
# nunca pelo primeiro texto igual em qualquer lugar da página.
# ---------------------------------------------------------------------------


def test_localizar_bloco_do_timbre_ignora_decoy_de_texto_igual_ANTES_do_bloco():
    # Reproduz o K2/BL-405: um "rodapé" repete a linha 0 ANTES do timbre
    # real. A caixa devolvida para a linha 0 tem de ser a do TIMBRE (a
    # SEGUNDA ocorrência), não a do decoy isolado (a primeira) — porque
    # só a posição real tem "linha0" IMEDIATAMENTE seguida por "linha1"
    # seguida por "linha2".
    palavras = [
        _palavra(0, 0, 50, 10, "Escritório"),  # decoy (rodapé), isolado
        _palavra(51, 0, 60, 10, "ME"),
        _palavra(0, 100, 50, 110, "Escritório"),  # timbre de verdade
        _palavra(51, 100, 60, 110, "ME"),
        _palavra(0, 120, 40, 130, "Endereco"),
        _palavra(0, 140, 30, 150, "Registro"),
    ]
    linhas_esperadas = ["Escritório ME", "Endereco", "Registro"]
    caixas = instrumento._localizar_bloco_do_timbre(palavras, linhas_esperadas)
    assert caixas[0] == (0, 100, 60, 110)  # a posição REAL do timbre, não (0,0,60,10)
    assert caixas[1] == (0, 120, 40, 130)
    assert caixas[2] == (0, 140, 30, 150)


def test_localizar_bloco_do_timbre_com_texto_duplicado_dentro_do_proprio_timbre():
    # Quando as N linhas realmente se repetem, JUNTAS, o bloco fecha
    # normalmente — cada ocorrência casa com sua própria posição.
    palavras = [
        _palavra(0, 0, 20, 10, "Razão"),
        _palavra(0, 20, 20, 30, "Igual"),
        _palavra(0, 40, 20, 50, "Igual"),
    ]
    linhas_esperadas = ["Razão", "Igual", "Igual"]
    caixas = instrumento._localizar_bloco_do_timbre(palavras, linhas_esperadas)
    assert caixas == [(0, 0, 20, 10), (0, 20, 20, 30), (0, 40, 20, 50)]


def test_localizar_bloco_do_timbre_devolve_todos_none_quando_uma_duplicata_falta():
    # O cenário exato do K2/K4: `registro_no_timbre == endereco_no_timbre`
    # e o `<p>` da SEGUNDA ocorrência escondido — só existe UMA cópia de
    # "Igual" no papel, mas o timbre declara DUAS. O bloco de 3 linhas
    # nunca fecha em lugar nenhum (C3: "faltar linha reprova").
    palavras = [
        _palavra(0, 0, 20, 10, "Razão"),
        _palavra(0, 20, 20, 30, "Igual"),
    ]
    linhas_esperadas = ["Razão", "Igual", "Igual"]
    assert instrumento._localizar_bloco_do_timbre(palavras, linhas_esperadas) == [None, None, None]


def test_localizar_bloco_do_timbre_devolve_none_quando_pagina_vazia():
    assert instrumento._localizar_bloco_do_timbre([], ["Qualquer coisa"]) == [None]


def test_localizar_bloco_do_timbre_devolve_none_para_texto_esperado_vazio():
    palavras = [_palavra(0, 0, 10, 10, "x")]
    assert instrumento._localizar_bloco_do_timbre(palavras, ["   "]) == [None]


def test_localizar_bloco_do_timbre_com_uma_linha_so_e_igual_a_bbox_da_linha():
    # Caso degenerado (N=1): sem sequência para ancorar, o resultado tem
    # de coincidir com a busca individual de sempre.
    palavras = [_palavra(0, 0, 10, 10, "Único")]
    assert instrumento._localizar_bloco_do_timbre(palavras, ["Único"]) == [
        instrumento._bbox_da_linha(palavras, "Único")
    ]


def test_localizar_bloco_do_timbre_falha_quando_ha_palavra_intrusa_entre_as_linhas():
    # LIMITE DECLARADO (ver a docstring de _localizar_bloco_do_timbre,
    # apontado pelo arquiteto-senior no meio da DL-029, nomeando a
    # DL-027): a contiguidade é propriedade do TEMPLATE de hoje, não do
    # requisito. Uma palavra ESTRANHA entre a linha 0 e a linha 1 (ex.:
    # legenda de um logotipo futuro) quebra o bloco — devolve
    # [None, None] mesmo com as DUAS linhas presentes e corretas, cada
    # uma isolada. Quem depende disso não é este teste (é `main`, que cai
    # para a busca individual + a checagem de visibilidade do navegador —
    # ver o comentário sobre o que continua seguro nesse caminho).
    palavras = [
        _palavra(0, 0, 20, 10, "Linha0"),
        _palavra(0, 15, 30, 25, "Intruso"),  # quebra a contiguidade
        _palavra(0, 30, 20, 40, "Linha1"),
    ]
    assert instrumento._localizar_bloco_do_timbre(palavras, ["Linha0", "Linha1"]) == [None, None]


# ---------------------------------------------------------------------------
# C5 da DL-029 (K1/BL-404, décima auditoria) — o identificador do
# fornecedor é DERIVADO de `templates/base.html`, nunca um literal
# repetido, e a busca é por AUSÊNCIA NORMALIZADA (caixa, espaço, pontuação
# e separadores desprezados).
# ---------------------------------------------------------------------------


def test_derivar_marca_do_fornecedor_le_do_template_real_do_produto():
    # Sem mock nem fixture: lê o ARQUIVO de verdade do repositório — se
    # `templates/base.html` mudar de forma incompatível, este teste é o
    # primeiro a acusar (AGENTS.md §8: duas cópias do mesmo texto
    # divergem; aqui a "segunda cópia" é ESTE TESTE, que tem de continuar
    # concordando com o produto).
    assert instrumento._derivar_marca_do_fornecedor() == "DataLedger"


def test_derivar_marca_do_fornecedor_recusa_quando_titulo_e_marca_divergem(tmp_path, monkeypatch):
    # DE-056: este instrumento não escolhe uma das duas fontes por conta
    # própria quando elas divergem — recusa (infraestrutura, código 2),
    # nomeando as duas.
    template_fake = tmp_path / "templates"
    template_fake.mkdir()
    (template_fake / "base.html").write_text(
        "<title>{% block titulo %}Nome1{% endblock %}{% block titulo_sufixo_do_fornecedor %}"
        " — Nome1{% endblock %}</title>\n"
        '<div class="marca">\n'
        "    <a href=\"{% url 'tenancy:painel' %}\">Nome2"
        '<span class="marca__ponto">.</span></a>\n'
        "</div>\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(instrumento, "_CAMINHO_BASE_HTML", template_fake / "base.html")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._derivar_marca_do_fornecedor()
    assert excinfo.value.code == 2


def test_derivar_marca_do_fornecedor_recusa_quando_template_nao_existe(tmp_path, monkeypatch):
    monkeypatch.setattr(instrumento, "_CAMINHO_BASE_HTML", tmp_path / "nao-existe.html")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._derivar_marca_do_fornecedor()
    assert excinfo.value.code == 2


@pytest.mark.parametrize(
    ("grafia", "deveria_ser_encontrada"),
    [
        ("Relatorio gerado por DATALEDGER - dataledger.com.br", True),
        ("Sistema dataledger", True),
        ("Produzido em Data Ledger", True),
        ("D a t a L e d g e r", True),
        ("Consulte dataledger.com.br para mais informações", True),
        ("marca registrada: DaTaLeDgEr", True),
        ("Balancete da Empresa Sintética Ltda", False),
        ("", False),
    ],
)
def test_normalizar_para_busca_do_fornecedor_fecha_todas_as_grafias_do_k1(
    grafia, deveria_ser_encontrada
):
    # AC 1 do plano da DL-029: DATALEDGER, dataledger, Data Ledger,
    # D a t a L e d g e r e dataledger.com.br têm de fechar de UMA vez,
    # por PROPRIEDADE (ausência normalizada), não por lista de grafias.
    marca_normalizada = instrumento._normalizar_para_busca_do_fornecedor("DataLedger")
    texto_normalizado = instrumento._normalizar_para_busca_do_fornecedor(grafia)
    assert (marca_normalizada in texto_normalizado) is deveria_ser_encontrada


def test_normalizar_para_busca_do_fornecedor_despreza_pontuacao_e_quebra_de_linha():
    # "é" some junto (não é [a-z0-9] depois de minúsculas) — a normalização
    # é ASCII estrita, o mesmo tratamento que qualquer acento receberia.
    assert (
        instrumento._normalizar_para_busca_do_fornecedor("Data-Ledger.com.br\né\num\tproduto")
        == "dataledgercombrumproduto"
    )


def test_normalizar_para_busca_do_fornecedor_com_entrada_vazia_ou_none():
    assert instrumento._normalizar_para_busca_do_fornecedor("") == ""
    assert instrumento._normalizar_para_busca_do_fornecedor(None) == ""


# ---------------------------------------------------------------------------
# BL-432 (décima primeira auditoria, L6) — duas asserções que guardam a
# PREMISSA que `_luminancia_do_papel`/`_cor_do_papel` documentam em tom de
# medição: "hoje o papel é sempre branco porque (1) `print_background`
# nunca é passado ao subprocesso e (2) `print-color-adjust` não existe no
# CSS de produção". Sem estas duas linhas, a premissa podia deixar de
# valer (ex.: a DL-027 introduzindo fidelidade de cor na impressão) sem
# NADA ficar vermelho — DE-058: afirmação de medição sem o teste que a
# reprova não é medição, é esperança.
# ---------------------------------------------------------------------------


def test_bl432_print_background_nunca_e_passado_ao_subprocesso_de_medicao():
    assert "print_background" not in instrumento._SCRIPT_DO_SUBPROCESSO, (
        "'print_background' apareceu em _SCRIPT_DO_SUBPROCESSO — a premissa que "
        "_luminancia_do_papel/_cor_do_papel documentam ('hoje o papel é SEMPRE "
        "branco, porque page.pdf() nunca recebe print_background=True') pode ter "
        "deixado de valer. Releia a docstring de _luminancia_do_papel ANTES de "
        "decidir se este teste deve mudar — ela explica o efeito de religar isso "
        "(o fundo passa a ser medido de verdade, e uma folha com background "
        "escuro passaria a reprovar por contraste)."
    )


def test_bl432_print_color_adjust_exact_nunca_esta_no_css_de_producao():
    conteudo = (instrumento.RAIZ / "static" / "css" / "base.css").read_text(encoding="utf-8")
    assert "print-color-adjust" not in conteudo, (
        "'print-color-adjust' apareceu em static/css/base.css — a premissa que "
        "_luminancia_do_papel/_cor_do_papel documentam ('hoje o papel é SEMPRE "
        "branco') pode ter deixado de valer. Releia a docstring de "
        "_luminancia_do_papel ANTES de decidir se este teste deve mudar."
    )


# ---------------------------------------------------------------------------
# BL-434 (décima primeira auditoria, L9/método (c)) — "para CADA cláusula
# da frase, UM caso de aceite ponta a ponta que afirme o CÓDIGO DE SAÍDA e
# a SUBSTRING DA MENSAGEM". Até esta correção havia 60+ testes PUROS
# excelentes e ZERO desses — e o L1 (BL-427) é exatamente o defeito que um
# teste assim teria pego: a cláusula C3 estava escrita em código
# INALCANÇÁVEL, e nenhum teste executava o caminho real o bastante para
# notar.
#
# **Isto RODA de verdade** — Django real (`@pytest.mark.django_db`,
# escritório/empresa sintéticos criados na própria transação de teste,
# nunca dependendo de `scripts/semear_base_de_medicao.py` nem de uma
# segunda base), `django.test.Client` real contra a rota real do
# Balancete, e depois `instrumento.main([])` de verdade — subprocesso real
# do Python do sistema, Playwright/Chromium real, `pdftotext`/`pdftoppm`/
# `pdfinfo` reais. As DUAS únicas coisas substituídas (`monkeypatch`) são
# QUAIS telas existem (`_descobrir_telas_com_timbre`) e QUAL cenário
# autenticar (`medir_impressao._preparar_cliente_e_cenario_de_medicao`) —
# só para não depender da varredura de TODA a urlconf nem de uma base
# externa; nenhuma das duas participa do JULGAMENTO da cláusula.
#
# **Sabotagem SEMPRE em memória** (string do HTML já renderizado pelo
# Django, nunca `static/css/base.css` nem `templates/**` — proibidos
# nesta etapa e, aqui, nem tocados: a sabotagem é uma tag <style> extra
# ou uma remoção de <p>, aplicada ao HTML DEPOIS de o Django já o ter
# gerado, exatamente equivalente a uma folha de estilo adicional que o
# navegador aplicaria por cima, sem escrever em nenhum arquivo
# rastreado).
#
# Gate: estes testes exigem poppler-utils no PATH e um Python do sistema
# (`DL_PYTHON_DO_SISTEMA`, padrão `/usr/bin/python3`) com Playwright — a
# MESMA exigência que o instrumento já verifica sozinho
# (`_exigir_ferramentas_de_pdf`/`_exigir_python_do_sistema_com_playwright`).
# Ausente, os testes são PULADOS com o motivo nomeado — nunca escondidos
# como "passou".
# ---------------------------------------------------------------------------


def _diagnostico_ambiente_ponta_a_ponta():
    """`None` se o ambiente tem tudo que esta seção precisa; senão, a
    STRING do motivo (nomeada no skip, nunca escondida).

    **Por que LANÇA o Chromium de verdade, e não só confere `import
    playwright.sync_api`**: o job "Backend" (`.github/workflows/
    backend.yml`) instala o PACOTE Playwright (`requirements/dev.txt`,
    via `pip install`) mas NUNCA roda `playwright install chromium` — só
    `.github/workflows/identificacao-do-emitente.yml` faz isso. Um
    ambiente assim IMPORTA `playwright.sync_api` com sucesso e MESMO
    ASSIM não consegue abrir um navegador (`sonda_visibilidade.
    NavegadorIndisponivel`) — a checagem rasa deixaria os testes ponta a
    ponta RODAREM no job errado e falharem com o código de infraestrutura
    (2) em vez do código de conteúdo que cada teste espera, quebrando o
    job "Backend" por um motivo que não é dele. Lançar e fechar o
    Chromium aqui, UMA VEZ (no diagnóstico, não por teste), custa
    menos de 1s e responde a pergunta CERTA: "este ambiente consegue
    medir de verdade?"."""
    faltando = [f for f in ("pdftotext", "pdftoppm", "pdfinfo") if shutil.which(f) is None]
    if faltando:
        return f"poppler-utils ausente no PATH: {', '.join(faltando)}"
    python_do_sistema = os.environ.get("DL_PYTHON_DO_SISTEMA", "/usr/bin/python3")
    diretorio_sonda = str(Path(__file__).resolve().parent)
    codigo_de_verificacao = (
        f"import sys; sys.path.insert(0, {diretorio_sonda!r}); "
        "import sonda_visibilidade as sv; "
        "from playwright.sync_api import sync_playwright; "
        "p = sync_playwright().start(); "
        "navegador = sv.lancar_chromium(p); "
        "navegador.close(); "
        "p.stop()"
    )
    try:
        resultado = subprocess.run(
            [python_do_sistema, "-c", codigo_de_verificacao],
            capture_output=True,
            timeout=30,
        )
    except OSError as erro:
        # BL-434: um DL_PYTHON_DO_SISTEMA apontando para um caminho
        # inexistente/sem permissão de execução levanta OSError (ex.:
        # FileNotFoundError) ANTES de qualquer código de saída existir —
        # sem este `try`, a COLETA inteira deste arquivo quebrava (o
        # diagnóstico roda no carregamento do módulo, não dentro de um
        # teste), derrubando também os 89 testes PUROS que nada têm a
        # ver com Playwright. Um ambiente indisponível tem de PULAR os
        # testes ponta a ponta, nunca reprovar a coleta inteira.
        return f"{python_do_sistema!r} não pôde ser executado: {erro}"
    except subprocess.TimeoutExpired:
        return f"{python_do_sistema!r} não respondeu em 30s ao tentar lançar o Chromium"
    if resultado.returncode != 0:
        detalhe = resultado.stderr.decode(errors="replace").strip().splitlines()
        return (
            f"{python_do_sistema!r} não conseguiu lançar o Chromium do Playwright: "
            f"{detalhe[-1] if detalhe else '(sem detalhe na saída de erro)'}"
        )
    return None


_MOTIVO_SEM_AMBIENTE_PONTA_A_PONTA = _diagnostico_ambiente_ponta_a_ponta()

pytestmark_ponta_a_ponta = pytest.mark.skipif(
    _MOTIVO_SEM_AMBIENTE_PONTA_A_PONTA is not None,
    reason=f"ambiente ponta a ponta indisponível: {_MOTIVO_SEM_AMBIENTE_PONTA_A_PONTA}",
)


def _criar_cenario_sintetico():
    """Escritório + Empresa + usuário sintéticos MÍNIMOS, com as TRÊS
    linhas de timbre (razão social/endereço/registro profissional) — o
    mesmo padrão de `scripts/semear_base_de_medicao.py`, criados DENTRO
    da transação de teste do pytest-django (revertida ao final; nenhum
    dado sobrevive ao teste). Dados sintéticos, os MESMOS já publicados
    no relatório desta e de auditorias anteriores — CNPJ numericamente
    válido, não pertence a ninguém real."""
    from django.contrib.auth import get_user_model

    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    usuario_modelo = get_user_model()
    usuario = usuario_modelo.objects.create_user(
        username="ponta_a_ponta", password="sintetica-irrelevante-para-o-teste"
    )
    escritorio = Escritorio.objects.create(
        nome="Escritório Sintético Ponta a Ponta",
        cnpj="11222333000181",
        razao_social_no_timbre="Escritório Contábil Sintético ME",
        endereco_no_timbre="Rua Sintética 100, Sala 2 - Palmas/TO",
        registro_no_timbre="CRC-TO 000000/O-0 (sintético)",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ADMINISTRADOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Comércio Sintético Ponta a Ponta Ltda",
        cnpj="44555666000199",
    )
    return usuario, escritorio, empresa


def _client_autenticado(usuario):
    from django.test import Client

    cliente = Client()
    cliente.force_login(usuario)
    return cliente


def _html_real_do_balancete(cliente, empresa):
    """GET real contra a rota real do Balancete — HTML genuinamente
    renderizado pelo Django (template real, contexto real), com o `href`
    do CSS reescrito para `file://` (`medir_impressao._com_css_local`,
    reaproveitado, nunca reimplementado) para o Chromium do subprocesso
    conseguir abrir localmente."""
    import medir_impressao
    from django.urls import reverse

    url = reverse("contabilidade_web:balancete", kwargs={"empresa_id": empresa.id})
    periodo = f"?inicio={medir_impressao.PERIODO_INICIO}&fim={medir_impressao.PERIODO_FIM}"
    resposta = cliente.get(url + periodo)
    assert resposta.status_code == 200, (
        f"GET {url} devolveu {resposta.status_code} — o cenário sintético deste "
        "teste ficou incompatível com a rota real; confira "
        "apps/contabilidade/urls_web.py e views_web.py."
    )
    html = resposta.content.decode()
    return url, medir_impressao._com_css_local(html)


def _injetar_estilo_de_impressao(html, regras_css):
    """Insere um `<style>` com `@media print { <regras_css> }` antes de
    `</head>` — sabotagem SÓ NA STRING em memória, nunca em
    `static/css/base.css` nem em `templates/**` (proibidos nesta etapa,
    e nem tocados aqui): equivalente a uma folha de estilo adicional que
    o navegador aplicaria por cima da folha real."""
    assert "</head>" in html
    bloco = f"<style>@media print {{ {regras_css} }}</style></head>"
    return html.replace("</head>", bloco, 1)


def _remover_linha_do_timbre(html, indice):
    """Remove, EM MEMÓRIA, o `<p>` de índice `indice` (0-based) de dentro
    de `.timbre-impressao` — simula, sem tocar template nenhum, o cenário
    do BL-427/C3 (o `{% for %}` do servidor perdeu uma linha)."""
    inicio = html.index('class="timbre-impressao"')
    fechamento = html.index("</div>", inicio)
    bloco = html[inicio:fechamento]
    paragrafos = re.findall(r"<p>.*?</p>", bloco, re.DOTALL)
    assert indice < len(paragrafos), f"timbre tem só {len(paragrafos)} linha(s)"
    novo_bloco = bloco.replace(paragrafos[indice], "", 1)
    return html[:inicio] + novo_bloco + html[fechamento:]


def _acrescentar_linha_extra_no_timbre(html):
    """Insere um `<p>` EXTRA dentro de `.timbre-impressao` — a direção
    'sobrar' do BL-427/C3, em memória."""
    inicio = html.index('class="timbre-impressao"')
    fim_da_tag = html.index(">", inicio) + 1
    return html[:fim_da_tag] + "<p>Linha extra intrusa</p>" + html[fim_da_tag:]


def _injetar_link_de_sabotagem_no_corpo(html, href, texto_ancora):
    """Insere, EM MEMÓRIA logo após a abertura de `<body ...>`, um `<a
    href="...">` — sabotagem de CONTEÚDO (não CSS), fora do
    `.timbre-impressao`: equivalente a um link que o template escrevesse
    em qualquer lugar da página. Reproduz o M2/BL-444: o ALVO do link
    carrega o identificador do fornecedor; o TEXTO ÂNCORA, de propósito,
    não — é exatamente o que faz `_texto_do_pdf` (que só lê o texto
    visível) não pegar a sabotagem."""
    inicio_body = html.index("<body")
    fim_da_tag = html.index(">", inicio_body) + 1
    link = f'<p><a href="{href}">{texto_ancora}</a></p>'
    return html[:fim_da_tag] + link + html[fim_da_tag:]


def _rodar_instrumento_sabotado(monkeypatch, capsys, cliente, empresa, html_sabotada, url):
    """Roda `instrumento.main([])` de VERDADE contra UMA tela fabricada a
    partir de HTML genuinamente renderizado — ver o comentário da seção,
    acima, para o que é e o que não é substituído. Devolve `(codigo_de_
    saida, saida_padrao, saida_de_erro)` — código `0` quando `main` não
    levanta `SystemExit` (o caminho de SUCESSO não chama `sys.exit`, ver
    o fim de `main`)."""
    import medir_impressao

    nome_tela = "contabilidade_web:balancete"
    monkeypatch.setattr(
        medir_impressao,
        "_preparar_cliente_e_cenario_de_medicao",
        lambda: (cliente, empresa, None),
    )
    monkeypatch.setattr(
        instrumento,
        "_descobrir_telas_com_timbre",
        lambda cliente_, empresa_, conta_: {
            nome_tela: {"rota": nome_tela, "url": url, "html": html_sabotada}
        },
    )
    monkeypatch.setattr(instrumento, "TELAS_MINIMAS_COM_TIMBRE_ESPERADAS", frozenset({nome_tela}))

    codigo = 0
    try:
        instrumento.main([])
    except SystemExit as exc:
        codigo = exc.code
    saida = capsys.readouterr()
    return codigo, saida.out, saida.err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_controle_limpo_passa_com_codigo_zero(monkeypatch, capsys):
    """Calibração: sem sabotagem nenhuma, o instrumento tem de PASSAR —
    sem isto, qualquer REPROVADO abaixo pode ser bug do CENÁRIO deste
    teste, não do produto."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html, url
    )

    assert codigo == 0, f"controle limpo REPROVOU — stderr:\n{err}"


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio11_c3_linha_faltando_reprova_por_conteudo_nomeando_a_contagem(
    monkeypatch, capsys
):
    """Critério 11 da rodada 2 (BL-427/C3): servidor declara 3 linhas,
    papel sai com 2 — código 1 (CONTEÚDO), nomeando a contagem. NUNCA
    código 2, NUNCA 'falha de infraestrutura' — é o defeito exato que o
    L1 mediu: a frase do C3 era código inalcançável."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _remover_linha_do_timbre(html, 1)  # some o endereço

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1 (conteúdo); saiu {codigo}. stderr:\n{err}"
    assert (
        "número de linhas do timbre no papel (2) diverge do número declarado pelo servidor (3)"
        in err
    )
    assert "FALHA DE INFRAESTRUTURA" not in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio11_c3_linha_extra_reprova_por_conteudo_nomeando_a_contagem(
    monkeypatch, capsys
):
    """Critério 11, direção 'sobrar': servidor declara 3, papel sai com
    4 — código 1, mesma frase, na direção oposta."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _acrescentar_linha_extra_no_timbre(html)

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1 (conteúdo); saiu {codigo}. stderr:\n{err}"
    assert (
        "número de linhas do timbre no papel (4) diverge do número declarado pelo servidor (3)"
        in err
    )


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio12_sonda_sem_fonte_das_linhas_continua_recusando_infraestrutura(
    monkeypatch, capsys
):
    """Critério 12 da rodada 2 — a distinção que o BL-427 precisa
    PRESERVAR: quando a sonda não devolve `fonte_das_linhas` nenhuma
    (subprocesso desatualizado, sem esse campo), continua sendo
    infraestrutura DE VERDADE — código 2, nunca 1. Simulado removendo só
    a ESCRITA daquele campo do script do subprocesso (a sonda continua
    rodando de verdade; só esse campo específico some do resultado)."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)

    alvo = 'medida["fonte_das_linhas"]'
    assert alvo in instrumento._SCRIPT_DO_SUBPROCESSO, "trecho não encontrado — confira o texto"
    script_sem_campo = instrumento._SCRIPT_DO_SUBPROCESSO.replace(
        alvo, 'medida["_fonte_das_linhas_desativada_para_teste_ponta_a_ponta"]'
    )
    monkeypatch.setattr(instrumento, "_SCRIPT_DO_SUBPROCESSO", script_sem_campo)

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html, url
    )

    assert codigo == 2, f"esperava código 2 (infraestrutura); saiu {codigo}. stderr:\n{err}"
    assert "fonte_das_linhas" in err
    assert "Recusado:" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio13_transform_scale_reprova_por_tamanho_medido_no_papel(
    monkeypatch, capsys
):
    """Critério 13 da rodada 2 (BL-428/C2): `transform: scale(0.6)` não
    muda a fonte DECLARADA (`getComputedStyle`), só a renderizada — tem
    de reprovar código 1, nomeando TAMANHO, com o tamanho EFETIVO
    medido pela escala acumulada do navegador (BL-437), nunca 'passa'
    por a fonte declarada continuar 14px."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao { transform: scale(0.6); transform-origin: top left; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err
    assert "CONTRASTE insuficiente" not in err
    assert "POUCOS PIXELS" not in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio13_zoom_reprova_por_tamanho_medido_no_papel(monkeypatch, capsys):
    """Critério 13, `zoom` — mesma família de `transform`: não muda a
    fonte declarada, muda o que chega ao papel."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(html, ".timbre-impressao { zoom: 0.6; }")

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio14_scale045_nomeia_tamanho_nunca_contraste_ou_contagem(
    monkeypatch, capsys
):
    """Critério 14 da rodada 2 (BL-428, agravante de mensagem): a tinta é
    PRETO PURO em `scale(0.45)` — se a mensagem culpar contraste ou
    contagem, é o mesmo defeito de forma que o K4/BL-321 já puniu
    (mensagem que culpa a tinta por um problema que não é de tinta)."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao { transform: scale(0.45); transform-origin: top left; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err
    assert "CONTRASTE insuficiente" not in err
    assert "POUCOS PIXELS" not in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio15_tinta_vermelha_reprova_pela_razao_rgb_real_do_wcag(
    monkeypatch, capsys
):
    """Critério 15 da rodada 2 (BL-429/C2, DE-060): a razão WCAG 2.2 REAL
    de `#FF0000` sobre `#FFFFFF` é 4,00:1 — abaixo do piso de texto
    normal (4,5:1). O instrumento em CINZA (antes desta correção)
    aprovava, relatando 8,45:1 — 2,1× mais contraste do que existe."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao, .timbre-impressao p { color: #FF0000 !important; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "CONTRASTE insuficiente" in err
    assert "4.00:1" in err or "4,00:1" in err
    assert "(WCAG 2.2, 1.4.3)" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio16_letter_spacing_nao_produz_falso_alarme_de_ausencia(
    monkeypatch, capsys
):
    """Critério 16 da rodada 2 (BL-430/C1-C3): `letter-spacing` no
    tamanho REAL do produto (14px) tem de PASSAR — código 0. Antes desta
    correção, o mecanismo de extração `-layout` inseria espaços espúrios
    e produzia 'AUSENTE do texto do PDF' sobre uma linha com centenas de
    pixels de tinta medidos na MESMA execução."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao p { letter-spacing: 0.2em !important; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 0, f"letter-spacing não podia reprovar — stderr:\n{err}"


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio16_fonte_extrema_reprova_por_tamanho_nunca_por_ausencia(
    monkeypatch, capsys
):
    """Critério 16, a outra metade: `font-size: 4px` tem de reprovar
    nomeando TAMANHO — nunca 'ausência' (o BL-425 media a linha como
    presente via bbox mesmo em fontes extremas; o defeito antigo era só
    de MENSAGEM, por causa do mecanismo de presença errado — BL-430)."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao p { font-size: 4px !important; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err
    assert "AUSENTE" not in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio19_font_size_8px_continua_reprovando_por_tamanho(
    monkeypatch, capsys
):
    """Critério 19 (nada regride) — o caso do BL-424, refeito ponta a
    ponta: `font-size: 8px`, sem `transform`/`zoom` nenhum, tem
    `escala_acumulada` = 1 (nenhuma transformação visual) — o tamanho
    EFETIVO é o próprio declarado, 8px, abaixo do piso de 11px."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao p { font-size: 8px !important; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_criterio19_tinta_branca_continua_reprovando(monkeypatch, capsys):
    """Critério 19 (nada regride) — tinta branca (a construção do
    BL-372/J1 que fundou o oráculo de contraste) continua reprovando,
    agora medida em COR: branco sobre branco é 1,00:1, bem abaixo do
    piso."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao, .timbre-impressao p { color: #FFFFFF !important; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "CONTRASTE insuficiente" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_clausula_c4_decoy_antes_do_timbre_nao_engana_a_ancora(monkeypatch, capsys):
    """Critério 18 (BL-434) para a cláusula **C4** ("cada uma no seu
    próprio lugar") — um rodapé/decoy ANTES do timbre, repetindo a
    PRIMEIRA linha, não pode enganar a âncora por bloco contíguo
    (K2/BL-405, décima auditoria): o bloco só fecha na posição REAL do
    timbre, então isto tem de PASSAR — nenhuma linha "sumiu" para o
    decoy."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    inicio = html.index('class="timbre-impressao"')
    inicio_div = html.rindex("<div", 0, inicio)
    decoy = "<p>Escritório Contábil Sintético ME</p>"
    html_sabotada = html[:inicio_div] + decoy + html[inicio_div:]

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 0, f"decoy antes do timbre não podia reprovar — stderr:\n{err}"


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_clausula_c5_pseudo_elemento_com_marca_do_fornecedor_reprova(
    monkeypatch, capsys
):
    """Critério 18 (BL-434) para a cláusula **C5** ("não carrega nenhum
    identificador do fornecedor") — o canal que a correção do K1/BL-404
    (décima auditoria) fechou: `content:` de pseudo-elemento CSS também
    vira texto extraível do PDF, e tem de reprovar com o identificador
    NOMEADO, normalizado."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        '.timbre-impressao::after { content: "Relatorio gerado por DATALEDGER - '
        'dataledger.com.br"; display: block; }',
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "identificador do fornecedor" in err
    assert "'dataledger'" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_bl436_tamanho_declarado_grande_mas_efetivo_normal_reprova(
    monkeypatch, capsys
):
    """BL-436 (verificação independente, rodada 3) — reprodução exata do
    verificador: `font-size: 24px` (declarado "grande", piso 3:1) +
    `transform: scale(0.6)` (tamanho EFETIVO ~14,4px, que já não é
    "grande") + tinta #D0D0D0. Antes da correção, a classificação
    "grande"/"normal" usava o tamanho DECLARADO e emprestava o piso
    frouxo (3:1) a uma linha que não é mais grande — FALSO CONFORME.
    Depois da correção, a classificação usa o tamanho EFETIVO
    (`escala_acumulada`) e exige o piso de texto normal (4,5:1)."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        ".timbre-impressao { transform: scale(0.6); transform-origin: top left; } "
        ".timbre-impressao, .timbre-impressao p { font-size: 24px !important; "
        "color: #D0D0D0 !important; }",
    )

    codigo, saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert '"razao_minima_wcag_exigida": 4.5' in saida, (
        "a classificação usou o piso de texto GRANDE (3.0) em vez do piso de "
        f"texto NORMAL (4.5) — o tamanho declarado (24px) venceu o efetivo "
        f"(~14,4px) na classificação. saida:\n{saida}"
    )


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_bl437_font_family_generica_no_piso_exato_passa(monkeypatch, capsys):
    """BL-437 (verificação independente, rodada 3) — reprodução exata do
    verificador: SEM sabotagem de tamanho nenhuma, só `font-family:
    monospace` e `font-size: 11px` (exatamente o piso). Antes da
    correção, a razão bbox/declarado media a fonte do PRODUTO (serif) e
    não generalizava para `monospace` — o piso efetivo virava ~12,3px, e
    11px (o próprio piso) reprovava por FALSO ALARME. Depois da
    correção, a escala acumulada é 1 (nenhum transform/zoom) e o
    tamanho efetivo é o próprio declarado — 11px, no piso, PASSA."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        ".timbre-impressao, .timbre-impressao p "
        "{ font-family: monospace !important; font-size: 11px !important; }",
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 0, f"font-family: monospace a 11px não podia reprovar — stderr:\n{err}"


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_bl437_font_family_serif_generica_no_piso_exato_passa(monkeypatch, capsys):
    """BL-437, segunda família testada pelo verificador (razão medida
    0,9269 em serif genérico, contra 1,088 na fonte do produto) — mesma
    calibração: 11px sem sabotagem de tamanho tem de passar."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        ".timbre-impressao, .timbre-impressao p "
        "{ font-family: serif !important; font-size: 11px !important; }",
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 0, f"font-family: serif a 11px não podia reprovar — stderr:\n{err}"


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_bl437_escala_acumulada_ainda_reprova_fonte_generica_pequena(
    monkeypatch, capsys
):
    """A direção oposta do BL-437 (aprovar tamanho pequeno demais numa
    família genérica) NÃO foi testada pelo verificador, e ele recusou-se
    a deduzi-la de três amostras — mas a correção (medir a escala no
    NAVEGADOR, sem depender de família nenhuma) não deveria depender de
    família para ESTE caso: `transform: scale(0.5)` em `monospace` a
    24px (efetivo 12px) ainda está acima do piso; a 20px (efetivo 10px)
    tem de reprovar, para confirmar que a correção não abriu um buraco
    na direção oposta."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        ".timbre-impressao { transform: scale(0.5); transform-origin: top left; } "
        ".timbre-impressao, .timbre-impressao p "
        "{ font-family: monospace !important; font-size: 20px !important; }",
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err


# ---------------------------------------------------------------------------
# M1/BL-428, BL-436 (décima segunda auditoria, achado do auditor-qa,
# docs/auditorias/2026-09-20-dl-029-dl-030-rodada-12.md) — a propriedade
# CSS `scale:` (a forma INDIVIDUAL, sem `transform:`) produzia a MESMA
# folha A4 exportada que `transform: scale(...)` (pixels de tinta e bbox
# do glifo idênticos ao milésimo de ponto, medido pelo auditor), mas o
# mecanismo antigo (`cs.transform`/`cs.zoom`) não a lia — `escala_
# acumulada` saía 1,0 em vez de 0,6, e o BL-428/BL-436 reabriam inteiros.
# A correção (sonda geométrica, ver `js_fonte_das_linhas`) não lê NENHUMA
# propriedade CSS nomeada — estes testes reproduzem `scale:` no
# `.timbre-impressao`, `scale:` no `<body>` (o caso do BL-428 original,
# "encolher a impressão para a tabela caber") e a combinação com o
# BL-436 (tamanho declarado grande, efetivo normal, contraste
# insuficiente) — os TRÊS casos que o "Como verificar" do M1 pede.
# ---------------------------------------------------------------------------


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_m1_propriedade_scale_no_timbre_reprova_por_tamanho_medido_no_papel(
    monkeypatch, capsys
):
    """M1: `scale: 0.6` (propriedade individual, SEM `transform:`) no
    `.timbre-impressao` tem de reprovar código 1 nomeando TAMANHO, com o
    número medido — exatamente como `transform: scale(0.6)` já reprova
    (ver o teste do critério 13)."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, ".timbre-impressao { scale: 0.6; transform-origin: top left; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err
    assert "CONTRASTE insuficiente" not in err
    assert "POUCOS PIXELS" not in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_m1_propriedade_scale_no_body_reprova_por_tamanho_medido_no_papel(
    monkeypatch, capsys
):
    """M1, o caso ANCESTRAL do BL-428 original ("encolher a impressão
    para a tabela caber", `@media print { body { scale: 0.6 } }") — a
    escala se aplica a um ANCESTRAL do timbre, não ao próprio contêiner.
    A sonda geométrica (filha de CADA linha) tem de herdar a escala do
    ancestral do mesmo jeito, sem ler `body` nomeadamente em lugar
    nenhum."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html, "body { scale: 0.6; transform-origin: top left; }"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "abaixo do mínimo de 11px" in err


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_m1_propriedade_scale_reabre_bl436_exige_4_5_para_1(monkeypatch, capsys):
    """M1 + BL-436 juntos, reprodução exata da tabela do auditor:
    `font-size: 24px` (declarado "grande", piso frouxo 3:1) + `scale:
    0.6` (tamanho EFETIVO ~14,4px, que já não é "grande") + tinta
    `#D0D0D0`. Com o mecanismo antigo isso saía `exit 0` relatando
    `razao_minima_wcag_exigida: 3.0` — o MESMO JSON, linha por linha, do
    BL-436 original, só que com `scale:` no lugar de `transform:`. A
    correção tem de classificar pelo tamanho EFETIVO e exigir 4,5:1."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_estilo_de_impressao(
        html,
        ".timbre-impressao { scale: 0.6; transform-origin: top left; } "
        ".timbre-impressao, .timbre-impressao p { font-size: 24px !important; "
        "color: #D0D0D0 !important; }",
    )

    codigo, saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert '"razao_minima_wcag_exigida": 4.5' in saida, (
        "a classificação usou o piso de texto GRANDE (3.0) em vez do piso de "
        f"texto NORMAL (4.5) — 'scale:' reabriu o BL-436. saida:\n{saida}"
    )


# ---------------------------------------------------------------------------
# M2/BL-444 (décima segunda auditoria) — reprodução ponta a ponta exata da
# sabotagem do auditor: o `<a href>` com o domínio do fornecedor E o
# controle limpo (com os links internos que o produto de hoje já embute)
# continuando a passar.
# ---------------------------------------------------------------------------


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_m2_anotacao_de_link_com_dominio_do_fornecedor_reprova(monkeypatch, capsys):
    """M2: `<a href="https://dataledger.com.br/">Emitido pelo
    sistema</a>` — texto âncora inócuo (nunca a palavra "DataLedger"), só
    o ALVO carrega o identificador. Antes desta correção, o C5 só olhava
    tinta (`_texto_do_pdf`, que não vê o alvo de um link) e metadados
    clássicos (que não têm o `/URI` de anotação) — `exit 0` com o domínio
    do fornecedor dentro do arquivo entregue ao cliente."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_link_de_sabotagem_no_corpo(
        html, "https://dataledger.com.br/", "Emitido pelo sistema"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 1, f"esperava código 1; saiu {codigo}. stderr:\n{err}"
    assert "anotação de link" in err
    assert "dataledger.com.br" in err.lower()


@pytestmark_ponta_a_ponta
@pytest.mark.django_db
def test_ponta_a_ponta_m2_link_interno_sem_marca_do_fornecedor_continua_passando(
    monkeypatch, capsys
):
    """M2, o controle: um link INTERNO (o padrão real do produto — cada
    linha de tabela vira um `file://.../lancamento/N/` clicável) não pode
    reprovar só por SER uma anotação de link — só quando o ALVO carrega o
    identificador do fornecedor."""
    usuario, _escritorio, empresa = _criar_cenario_sintetico()
    cliente = _client_autenticado(usuario)
    url, html = _html_real_do_balancete(cliente, empresa)
    html_sabotada = _injetar_link_de_sabotagem_no_corpo(
        html, "file:///contabilidade/painel/empresas/1/lancamento/42/", "Ver lançamento"
    )

    codigo, _saida, err = _rodar_instrumento_sabotado(
        monkeypatch, capsys, cliente, empresa, html_sabotada, url
    )

    assert codigo == 0, f"link interno sem marca não podia reprovar — stderr:\n{err}"
