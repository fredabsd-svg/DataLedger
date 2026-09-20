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
        # (`docs/assets/design/gauntlet/juiz.py`, para a tela).
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


def test_rasterizar_primeira_pagina_com_pdftoppm_quebrado_recusa(path_com_binario_quebrado, capsys):
    path_com_binario_quebrado("pdftoppm")
    with pytest.raises(SystemExit) as excinfo:
        instrumento._rasterizar_primeira_pagina("qualquer.pdf")
    assert excinfo.value.code == 2
    saida = capsys.readouterr()
    assert "Recusado:" in saida.err
    assert "pdftoppm" in saida.err


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


def test_pixels_escuros_na_faixa_conta_so_dentro_do_retangulo_e_do_limiar():
    # Página 10x10: um quadrado ESCURO (valor 0) em x=2..4, y=2..4 (3x3=9
    # pixels), o resto BRANCO (255). `margem_px=0` para o teste medir
    # exatamente o retângulo pedido, sem a folga de produção.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    for y in range(2, 5):
        for x in range(2, 5):
            valores[y * largura + x] = 0
    dados = _pgm_sintetico(largura, altura, valores)

    # Retângulo em "pontos", com dpi=72 (1 ponto = 1 pixel, sem
    # conversão) para o teste comparar direto com a grade acima.
    contagem = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(2, 2, 4, 4), dpi=72, margem_px=0
    )
    assert contagem == 9  # o quadrado 3x3 inteiro, e nada além dele

    # Um retângulo que NÃO toca o quadrado escuro conta zero.
    contagem_fora = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(6, 6, 8, 8), dpi=72, margem_px=0
    )
    assert contagem_fora == 0


def test_pixels_escuros_na_faixa_respeita_o_limiar_de_luminancia():
    # Um pixel cinza-claro (200) NÃO conta como "escuro" contra o limiar
    # de produção (128); um pixel cinza-escuro (100) conta.
    dados = _pgm_sintetico(2, 1, [200, 100])
    assert instrumento.LIMIAR_LUMINANCIA_TINTA == 128
    contagem = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(0, 0, 2, 1), dpi=72, margem_px=0
    )
    assert contagem == 1


def test_pixels_escuros_na_faixa_margem_expande_a_busca_sem_ultrapassar_a_pagina():
    # Quadrado escuro em x=5, y=5 (1 pixel). Um retângulo pedido "ao
    # lado" (x=6..7) só o alcança com margem >= 1.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    valores[5 * largura + 5] = 0
    dados = _pgm_sintetico(largura, altura, valores)

    sem_margem = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(6, 5, 7, 6), dpi=72, margem_px=0
    )
    com_margem = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(6, 5, 7, 6), dpi=72, margem_px=1
    )
    assert sem_margem == 0
    assert com_margem == 1

    # Margem grande perto da borda da página não estoura o índice (clampado).
    instrumento._pixels_escuros_na_faixa(dados, retangulo_pt=(0, 0, 1, 1), dpi=72, margem_px=1000)


def test_pixels_escuros_na_faixa_converte_pontos_para_pixel_pelo_dpi():
    # 1 ponto = 1/72 polegada; a 96 dpi, 1 ponto = 96/72 = 4/3 pixel. Um
    # retângulo de 3x3 PONTOS a 96 dpi cobre 4x4 PIXELS (arredondando
    # para baixo o início e para cima o fim) — usado aqui só para
    # confirmar que a conversão participa da conta, não o valor exato.
    largura, altura = 10, 10
    valores = [255] * (largura * altura)
    for y in range(4):
        for x in range(4):
            valores[y * largura + x] = 0
    dados = _pgm_sintetico(largura, altura, valores)
    contagem = instrumento._pixels_escuros_na_faixa(
        dados, retangulo_pt=(0, 0, 3, 3), dpi=96, margem_px=0
    )
    assert contagem == 16  # 4x4, não 3x3 — a conversão de unidade aconteceu


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
