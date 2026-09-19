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
