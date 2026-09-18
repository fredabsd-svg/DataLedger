"""BL-296 (M5, rodada 4 da auditoria DL-024,
docs/auditorias/2026-09-18-dl-024-rodada-2.md): o comentário de
`templates/contabilidade/_navegacao_empresa.html` afirmava que "o teste em
apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py reprova
quando um dos dois deixa de bater com o outro" — mas aquele teste é
parametrizado por uma LISTA LITERAL de oito nomes
(`ATALHOS_CONTABILIDADE`/`_urls_de_contabilidade`); nada em `apps/`
enumerava a pasta `templates/contabilidade/`. O auditor criou um nono
template (`exportacao.html`), sem a parcial e sem entrar em lista nenhuma:
a suíte inteira devolveu 1363 passed — o comentário afirmava um mecanismo
que não existia (a mesma família de defeito do A3 da rodada 1,
`base.css:540-546`, agora sobre um teste).

Este arquivo fecha a lacuna VARRENDO a pasta em vez de enumerar telas à
mão: toda tela de `templates/contabilidade/` (tudo que NÃO começa com `_`
— convenção Django/deste projeto para parcial) precisa incluir a parcial
de navegação. Uma tela nova não precisa que ninguém lembre de acrescentar
seu nome a uma lista em outro arquivo — só precisa existir na pasta.
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PASTA_CONTABILIDADE = RAIZ / "templates" / "contabilidade"

INCLUDE_ESPERADO = '{% include "contabilidade/_navegacao_empresa.html"'

# Telas de `templates/contabilidade/` que LEGITIMAMENTE não incluem a
# navegação da empresa — hoje nenhuma. Declarada e comentada, no mesmo
# padrão de `PASTAS_QUE_NAO_SAO_MODULO`
# (apps.core.tests.test_dl024_varredura_de_interface): um novo template
# que genuinamente não precise do atalho compartilhado (ex.: uma tela de
# erro dedicada, sem contexto de empresa) entra aqui COM o nome e o
# motivo — nunca por a exceção ficar implícita num "esqueceram de
# incluir".
TELAS_SEM_NAVEGACAO_DE_EMPRESA = frozenset()


def _telas_de_verdade(pasta):
    """Todo `.html` de `pasta`, exceto as PARCIAIS (prefixo `_`) — uma
    parcial não é uma TELA, é incluída POR uma tela; contar como tela
    duplicaria a cobrança (a própria `_navegacao_empresa.html` não inclui
    a si mesma)."""
    return sorted(caminho for caminho in pasta.glob("*.html") if not caminho.name.startswith("_"))


def _telas_sem_navegacao(pasta, excecoes=frozenset()):
    """Nomes (`arquivo.html`) das telas de `pasta` que não incluem a
    parcial de navegação — vazia quando está tudo certo."""
    sem_navegacao = []
    for caminho in _telas_de_verdade(pasta):
        if caminho.stem in excecoes:
            continue
        texto = caminho.read_text(encoding="utf-8")
        if INCLUDE_ESPERADO not in texto:
            sem_navegacao.append(caminho.name)
    return sem_navegacao


def test_toda_tela_de_contabilidade_inclui_a_navegacao_da_empresa():
    """Critério de aceite do BL-296: varre `templates/contabilidade/` de
    verdade (não uma lista escrita à mão) e reprova nomeando qualquer tela
    sem a parcial."""
    telas = _telas_de_verdade(PASTA_CONTABILIDADE)
    # Controle: se a pasta real perdesse arquivo (refatoração que junta
    # templates, por exemplo) e ficasse com menos de oito, este teste
    # continuaria "passando" por não ter mais nada para reprovar — o
    # mínimo abaixo garante que a varredura está de fato vendo as telas
    # conhecidas hoje (balancete, conferência, conta_form, diário,
    # lançamento_detalhe, lançamento_form, plano_de_contas, razão).
    assert len(telas) >= 8, (
        "controle: a pasta real precisa ter pelo menos as oito telas conhecidas: " + repr(telas)
    )
    achados = _telas_sem_navegacao(PASTA_CONTABILIDADE, TELAS_SEM_NAVEGACAO_DE_EMPRESA)
    assert not achados, "tela(s) de contabilidade sem a parcial de navegação: " + repr(achados)


def test_varredura_por_pasta_pega_tela_nova_sem_precisar_de_lista(tmp_path):
    """M5/BL-296 — controle da guarda acima (lição da BL-271: teste que
    não morre quando a defesa é removida não é guarda, é enfeite). Repete
    a sabotagem do auditor — um template NOVO, sem a parcial e sem entrar
    em lista nenhuma — mas num diretório SINTÉTICO (`tmp_path`), não na
    pasta real do projeto: a lógica varrida é parametrizada pela pasta
    (`_telas_de_verdade`/`_telas_sem_navegacao` recebem `pasta` como
    argumento), então provar o mecanismo aqui não exige escrever nem
    apagar arquivo nenhum dentro de `templates/contabilidade/` — evita
    disputar o mesmo diretório com qualquer outra sessão rodando testes
    contra o repositório real ao mesmo tempo (BL-273).
    """
    (tmp_path / "balancete.html").write_text(
        "{% extends 'base.html' %}\n" + INCLUDE_ESPERADO + ' with pagina_atual="balancete" %}\n',
        encoding="utf-8",
    )
    (tmp_path / "exportacao.html").write_text(
        "{% extends 'base.html' %}\n<p>Tela nova, sem a parcial.</p>\n", encoding="utf-8"
    )
    # Parcial de verdade: não é tela, tem que ficar de fora da varredura
    # mesmo sem incluir a si mesma.
    (tmp_path / "_navegacao_empresa.html").write_text(
        "<nav>parcial de navegação, não é tela</nav>\n", encoding="utf-8"
    )

    telas = _telas_de_verdade(tmp_path)
    assert {caminho.name for caminho in telas} == {"balancete.html", "exportacao.html"}, (
        "controle: a parcial (_*.html) precisa ficar de fora da varredura, "
        f"achado: {[c.name for c in telas]}"
    )

    achados = _telas_sem_navegacao(tmp_path)
    assert achados == ["exportacao.html"], (
        "a tela nova sem a parcial não foi detectada pela varredura por pasta: " + repr(achados)
    )


def test_controle_positivo_excecao_declarada_tira_a_tela_do_alcance():
    """A EXCEÇÃO (`TELAS_SEM_NAVEGACAO_DE_EMPRESA`) precisa mesmo excluir
    a tela nomeada — testado num diretório sintético, sem depender da
    pasta real ter (ou não ter) exceção nenhuma hoje."""
    import tempfile

    with tempfile.TemporaryDirectory() as diretorio:
        pasta = Path(diretorio)
        (pasta / "sem_parcial.html").write_text("<p>Tela sem a parcial.</p>\n", encoding="utf-8")
        assert _telas_sem_navegacao(pasta) == ["sem_parcial.html"]
        assert _telas_sem_navegacao(pasta, excecoes={"sem_parcial"}) == []
