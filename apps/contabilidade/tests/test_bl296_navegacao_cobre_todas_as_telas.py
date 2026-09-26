"""BL-296 (M5, rodada 4 da auditoria DL-026,
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

Este arquivo fechou a lacuna VARRENDO a pasta em vez de enumerar telas à
mão: toda tela de `templates/contabilidade/` (tudo que NÃO começa com `_`
— convenção Django/deste projeto para parcial) precisava incluir a parcial
de navegação. Uma tela nova não precisava que ninguém lembre de acrescentar
seu nome a uma lista em outro arquivo — só precisava existir na pasta.

ADAPTAÇÃO (DL-044, 4ª iteração — achado do arquiteto-senior: "a queixa
central do Fred, 'tudo junto num lugar só', continua: a linha de abas
repete EXATAMENTE os itens do submenu lateral"). A linha de abas
(`_navegacao_empresa.html`) foi REMOVIDA — os sete atalhos de teclado
migraram para o submenu "Contabilidade" da barra lateral
(`templates/base.html`), que é RENDERIZADO SEMPRE (não é mais opt-in por
template: nenhuma tela precisa de um `{% include %}` para ganhar o
mecanismo). Isso muda a PROPRIEDADE que ainda pode falhar em silêncio: já
não é "uma tela esqueceu de incluir a parcial" (estruturalmente impossível
agora — o submenu vive em `base.html`, e toda tela do produto estende
`base.html`), é "uma tela de contabilidade não identifica a EMPRESA na
faixa de contexto do topo" (`{% block contexto_extra %}`, RC-93) — sem
isso, a tela nem faz sentido como tela de UMA empresa, e a convenção
`<span class="contexto-rotulo">Empresa</span>` já era, antes desta
adaptação, seguida por TODAS as 16 telas reais de `templates/contabilidade/`
(a 17ª, `balancete_emissao_recusada.html`, é uma exceção DOCUMENTADA e já
testada à parte — ver `TELAS_SEM_EMPRESA_NO_CONTEXTO`, abaixo). A MESMA
técnica de varredura (glob da pasta, nunca lista escrita à mão) continua
pegando uma tela nova automaticamente — só o SINAL verificado mudou, do
texto do `{% include %}` extinto para o texto do pill "Empresa" que já
era, e continua sendo, obrigatório (RC-93).

Não reduz o que a guarda original verificava: o RISCO que BL-296 existia
para pegar — tela nova sem cobertura de acessibilidade — não pode mais
acontecer da forma antiga (mecanismo deixou de ser opt-in), e esta versão
pega a forma NOVA do mesmo risco (tela nova sem identificação de empresa,
que também compromete a garantia de isolamento "o usuário sempre sabe em
que empresa está operando", AGENTS.md §11).
"""

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[3]
PASTA_CONTABILIDADE = RAIZ / "templates" / "contabilidade"

PILL_DE_EMPRESA_ESPERADA = '<span class="contexto-rotulo">Empresa</span>'

# Telas de `templates/contabilidade/` que LEGITIMAMENTE não identificam a
# empresa na faixa de contexto — hoje só uma, com motivo já documentado no
# PRÓPRIO template (não inventado aqui): a resposta 409 de emissão
# recusada do Balancete não pode incluir NENHUM dado da empresa em NENHUM
# lugar do documento (medido por test_dl024_veredito_no_html_renderizado.
# test_pagina_real_balancete_nao_fecha_com_totais_forcados). Uma tela nova
# que genuinamente não precise da identificação entra aqui COM o nome e o
# motivo — nunca por a exceção ficar implícita num "esqueceram de pôr".
TELAS_SEM_EMPRESA_NO_CONTEXTO = frozenset(
    {
        "balancete_emissao_recusada": (
            "resposta 409 do Balancete — nenhum dado da empresa em nenhum lugar do "
            "documento, por desenho (ver o comentário no próprio template)"
        ),
    }
)


def _telas_de_verdade(pasta):
    """Todo `.html` de `pasta`, exceto as PARCIAIS (prefixo `_`) — uma
    parcial não é uma TELA, é incluída POR uma tela."""
    return sorted(caminho for caminho in pasta.glob("*.html") if not caminho.name.startswith("_"))


def _telas_sem_empresa_no_contexto(pasta, excecoes=frozenset()):
    """Nomes (`arquivo.html`) das telas de `pasta` que não identificam a
    empresa na faixa de contexto do topo — vazia quando está tudo certo."""
    sem_empresa = []
    for caminho in _telas_de_verdade(pasta):
        if caminho.stem in excecoes:
            continue
        texto = caminho.read_text(encoding="utf-8")
        if PILL_DE_EMPRESA_ESPERADA not in texto:
            sem_empresa.append(caminho.name)
    return sem_empresa


def test_toda_tela_de_contabilidade_identifica_a_empresa_no_contexto():
    """Critério de aceite do BL-296, adaptado na DL-044 (4ª iteração): varre
    `templates/contabilidade/` de verdade (não uma lista escrita à mão) e
    reprova nomeando qualquer tela que não identifique a empresa na faixa
    de contexto do topo (RC-93)."""
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
    achados = _telas_sem_empresa_no_contexto(PASTA_CONTABILIDADE, TELAS_SEM_EMPRESA_NO_CONTEXTO)
    assert not achados, "tela(s) de contabilidade sem a empresa na faixa de contexto: " + repr(
        achados
    )


def test_varredura_por_pasta_pega_tela_nova_sem_precisar_de_lista(tmp_path):
    """M5/BL-296 — controle da guarda acima (lição da BL-271: teste que
    não morre quando a defesa é removida não é guarda, é enfeite). Repete
    a sabotagem do auditor — um template NOVO, sem a identificação de
    empresa e sem entrar em lista nenhuma — mas num diretório SINTÉTICO
    (`tmp_path`), não na pasta real do projeto: a lógica varrida é
    parametrizada pela pasta (`_telas_de_verdade`/`_telas_sem_empresa_no_
    contexto` recebem `pasta` como argumento), então provar o mecanismo
    aqui não exige escrever nem apagar arquivo nenhum dentro de
    `templates/contabilidade/` — evita disputar o mesmo diretório com
    qualquer outra sessão rodando testes contra o repositório real ao
    mesmo tempo (BL-273).
    """
    (tmp_path / "balancete.html").write_text(
        "{% extends 'base.html' %}\n"
        '{% block contexto_extra %}<span class="contexto-item">'
        '<span class="contexto-rotulo">Empresa</span><strong>{{ empresa.razao_social }}</strong>'
        "</span>{% endblock %}\n",
        encoding="utf-8",
    )
    (tmp_path / "exportacao.html").write_text(
        "{% extends 'base.html' %}\n<p>Tela nova, sem identificação de empresa.</p>\n",
        encoding="utf-8",
    )
    # Parcial de verdade (prefixo `_`): não é tela, fica de fora da
    # varredura mesmo sem ter o pill de empresa.
    (tmp_path / "_qualquer_parcial.html").write_text(
        "<p>parcial, não é tela</p>\n", encoding="utf-8"
    )

    telas = _telas_de_verdade(tmp_path)
    assert {caminho.name for caminho in telas} == {"balancete.html", "exportacao.html"}, (
        "controle: a parcial (_*.html) precisa ficar de fora da varredura, "
        f"achado: {[c.name for c in telas]}"
    )

    achados = _telas_sem_empresa_no_contexto(tmp_path)
    assert achados == ["exportacao.html"], (
        "a tela nova sem identificação de empresa não foi detectada pela varredura por pasta: "
        + repr(achados)
    )


def test_controle_positivo_excecao_declarada_tira_a_tela_do_alcance():
    """A EXCEÇÃO (`TELAS_SEM_EMPRESA_NO_CONTEXTO`) precisa mesmo excluir a
    tela nomeada — testado num diretório sintético, sem depender da pasta
    real ter (ou não ter) exceção nenhuma hoje."""
    import tempfile

    with tempfile.TemporaryDirectory() as diretorio:
        pasta = Path(diretorio)
        (pasta / "sem_empresa.html").write_text("<p>Tela sem o pill.</p>\n", encoding="utf-8")
        assert _telas_sem_empresa_no_contexto(pasta) == ["sem_empresa.html"]
        assert _telas_sem_empresa_no_contexto(pasta, excecoes={"sem_empresa"}) == []


def test_excecao_declarada_bate_com_a_pasta_real():
    """Controle inverso: nada declarado em `TELAS_SEM_EMPRESA_NO_CONTEXTO`
    pode ter deixado de existir — senão a exceção estaria protegendo uma
    tela fantasma, e uma correção de verdade (a tela passou a identificar
    a empresa) nunca seria percebida porque a exceção continuaria
    escondendo-a da varredura."""
    nomes_reais = {caminho.stem for caminho in _telas_de_verdade(PASTA_CONTABILIDADE)}
    excedentes = set(TELAS_SEM_EMPRESA_NO_CONTEXTO) - nomes_reais
    assert not excedentes, (
        "nome declarado em TELAS_SEM_EMPRESA_NO_CONTEXTO que não existe (mais) em "
        "templates/contabilidade/: " + repr(sorted(excedentes))
    )
