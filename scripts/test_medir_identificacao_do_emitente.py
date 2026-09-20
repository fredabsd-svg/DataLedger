"""Testes das funções PURAS de `medir_identificacao_do_emitente.py` — DL-028
fatia 2 (docs/planos/DL-028-o-juiz-aponta-para-o-produto.md).

**Por que este arquivo existe agora, e não na fatia 1.** Enquanto o
instrumento era só ferramenta de BANCADA (fatia 1), o precedente de
`scripts/medir_impressao.py` (zero cobertura `pytest`, por depender de
Playwright/Chromium/banco) era razoável. A partir da fatia 2 este
instrumento **reprova pull request** — e uma ferramenta que reprova PR é
infraestrutura da equipe: um erro nela ou trava todo mundo com falso alarme,
ou aprova em silêncio um documento sem emitente. As duas coisas custam mais
do que escrever este arquivo.

**O que este arquivo cobre, e o que NÃO cobre.** Só as funções que não
precisam de Playwright nem de Django: a checagem de "tinta invisível"
(`_tinta_invisivel`) e a distinção entre falha de INFRAESTRUTURA (código de
saída `2`, `_recusar`) e falha de CONTEÚDO (código `1`,
`_reprovar_por_conteudo`) — o contrato central do BL-356 que o job de
integração contínua da fatia 2 lê para decidir a mensagem que mostra a quem
abre o PR. A medição no navegador em si (derivação de telas, sonda de
visibilidade, geração de PDF) continua verificada por EXECUÇÃO real de
bancada — não por mock de Playwright, que provaria só que o mock funciona
(AGENTS.md §7: "mocks são adequados para testes isolados, mas não comprovam
a integração real").

Importar `medir_identificacao_do_emitente` aqui NÃO exige Playwright nem
banco: o módulo só toca Django/Playwright DENTRO de funções, nunca no
carregamento do arquivo (ver a docstring dele, "Os dois interpretadores").
"""

import os
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
