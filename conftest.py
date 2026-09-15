"""Instrumentação de sessão do pytest — BL-171 (achado A5 da auditoria DL-019
rodada 1) e BL-178 (achado B5 da rodada 2).

Duas coisas moram aqui, e as duas são de SESSÃO:

1. O elo de execução, que amarra superfície de escrita a execução real.
2. A independência da suíte em relação a artefato **não versionado** — a
   fixture `estaticos_independentes_do_manifesto`, no fim do arquivo. As duas
   têm o mesmo dono porque foi a segunda que desligou a primeira: sessão
   vermelha faz `pytest_sessionfinish` sair cedo, e a conferência do elo nunca
   chegou a rodar na integração contínua.

## O elo que este arquivo fecha

A varredura de contratos (`apps/core/tests/test_dl019_varredura_de_contratos.
py`) prova que toda superfície de escrita **chama** a política dos cinco
dicionários. Ela não prova — e declara, com todas as letras, que não prova —
que alguém **exercitou** essa chamada numa requisição de teste. Uma superfície
pode ter a linha no fonte e nunca ter sido tocada por teste nenhum.

A BL-149 tinha um critério de aceite que guardava essa cobertura, e ele foi
retirado por uma razão legítima: amarrar superfície a ARQUIVO DE TESTE por
casamento de nome é a promessa que a BL-166 nomeou como não sustentável. A
retirada, porém, ficou sem substituto e sem dono — a DE-033 pelo avesso.

O substituto, proposto pelo auditor, **não usa heurística nenhuma**: ele amarra
superfície a **execução**. A política de produção é embrulhada por uma função
que registra quem a chamou (pela pilha real de quadros, não por nome de
arquivo), e no fim da sessão toda superfície descoberta pela varredura tem de
ter aparecido nesse registro, **nomeando** a que faltar. O que prova é a
chamada ter acontecido.

## A ressalva do arquiteto, atendida aqui

Instrumentação que embrulha função de produção **falha em silêncio** se o
embrulho deixar de ser aplicado — e aí o mecanismo passa a aprovar tudo, que é
o mesmo defeito da varredura rodando sobre lista vazia. Por isso o embrulho
tem controle positivo próprio, em
`apps/core/tests/test_dl019_elo_de_execucao.py`:

- um teste prova que o **registro registra**, fazendo uma requisição HTTP real
  a uma superfície conhecida e exigindo que ela apareça no registro;
- um teste prova que o **embrulho está aplicado** em cada módulo de produção
  que importou a política pelo nome (`from ... import ...` copia a
  referência: patchear só `apps.core.requisicao` não alcançaria nenhum deles);
- um teste prova que a **conferência final sabe reprovar**, com uma superfície
  fictícia que ninguém exercitou.

Sem esses três, este arquivo seria mais uma afirmação que a defesa não
entrega — a família de defeito que a DL-019 inteira existe para matar.

## Por que a conferência só vale na suíte inteira

`pytest apps/core` não exercita a tela de lançamento, e reprovar por isso
seria ruído que ninguém suporta por muito tempo — e mecanismo que todo mundo
aprende a ignorar é mecanismo desligado. A conferência só roda quando a
invocação pediu a suíte inteira (`pytest`, que é o que a integração contínua
executa: `.github/workflows/backend.yml`). A regra está em
`conferencia_de_execucao_se_aplica`, que é função pura justamente para poder
ser testada com entradas sintéticas — sem isso, "a conferência nunca roda"
seria uma falha silenciosa indistinguível de "a conferência passou". E a
sessão **anuncia** o que decidiu, inclusive quando decide não conferir.

## O que o registro guarda, e por que a classe da instância importa

O registro guarda, de cada quadro de produção da pilha, **dois** nomes: o do
código (`modulo.ClasseQueDefine.metodo`) e o **efetivo**
(`modulo.ClasseDaInstancia.metodo`). A conferência só aceita o efetivo. Sem
isso, duas superfícies que compartilhassem o handler de um mixin
compartilhariam o único nome guardado, e exercitar uma marcaria a outra como
exercitada, sem ninguém a ter tocado (BL-179/B6). Não há instância viva hoje —
os 14 handlers foram mapeados e nenhum se repete —, e o desenho é provável para
a DL-010, com duas rotas de importação e o mesmo `post`.

**Limite declarado:** o registro é um conjunto em memória do processo. Sob
execução distribuída (`pytest-xdist`, que este projeto NÃO usa — ver
`requirements/`), cada trabalhador teria o seu, e a conferência acusaria
falta onde não há. Se um dia entrar xdist, este mecanismo precisa de
consolidação entre trabalhadores antes de continuar valendo.
"""

import functools
import sys

import pytest

NOME_DA_POLITICA = "recusar_dado_nao_contratado"

# `{"apps.modulo.qualname", ...}` — todo quadro de código de PRODUÇÃO de
# `apps.` que estava na pilha no momento de cada chamada da política. A pilha
# inteira, e não só o chamador imediato, porque a política é alcançada por
# ponte do app (`apps.empresas.views._recusar_dado_nao_contratado`) em algumas
# superfícies e diretamente em outras: o que interessa é que a REQUISIÇÃO que
# passou por `EmpresaDetailView.put` tenha chegado até a política.
CHAMADORES_DA_POLITICA = set()

_ATRIBUTO_DE_INSTRUMENTACAO = "instrumentada_para_o_elo_de_execucao"


def e_codigo_de_teste(nome_pontilhado):
    """`True` quando `nome_pontilhado` é módulo (ou caminho) de teste.

    Módulos de teste não contam para o elo de execução: o que se quer provar é
    que uma superfície de PRODUÇÃO foi exercitada, não que alguém chamou a
    política de dentro de um teste unitário dela.

    Esta função é a ÚNICA resposta do repositório para essa pergunta, e a
    varredura de contratos a importa daqui (BL-181/B7). Antes havia duas
    regras diferentes para a mesma pergunta, e as duas tinham o mesmo buraco:
    a marca `".tests."` não casa `apps.foo.tests` — o leiaute `tests.py`
    padrão do Django —, porque falta o ponto final, e aquele módulo seria
    tratado como produção. Hoje nenhum app usa `tests.py` e o `pyproject.toml`
    fixa `python_files = ["test_*.py"]`, então o buraco era latente; o que o
    tornava achado era a fronteira ser mais estreita do que a sua redação.
    """
    partes = nome_pontilhado.split(".")
    return "tests" in partes or any(parte.startswith("test_") for parte in partes)


def _nomes_registraveis_do_quadro(quadro):
    """Os nomes com que este quadro da pilha entra no registro.

    Dois, quando o quadro é de um método: o nome do CÓDIGO
    (`modulo.ClasseQueDefine.metodo`) e o nome EFETIVO
    (`modulo.ClasseDaInstancia.metodo`, lido de `self.__class__`).

    O nome efetivo é o que a conferência usa, e é a correção do BL-179/B6:
    duas superfícies que compartilhem o handler de um mixin têm o MESMO nome
    de código, e aceitar esse nome fazia exercitar uma marcar a outra como
    exercitada, sem ninguém tê-la tocado. Com a classe da instância, cada rota
    responde por si. O nome do código continua sendo registrado porque é ele
    que identifica as pontes de módulo (`_recusar_dado_nao_contratado`) e as
    views de função, que não têm `self`.
    """
    nome_modulo = quadro.f_globals.get("__name__", "") or ""
    if not nome_modulo.startswith("apps.") or e_codigo_de_teste(nome_modulo):
        return ()
    codigo = quadro.f_code
    nomes = [f"{nome_modulo}.{codigo.co_qualname}"]
    if codigo.co_varnames[:1] == ("self",):
        instancia = quadro.f_locals.get("self")
        classe = type(instancia) if instancia is not None else None
        if classe is not None and getattr(classe, "__module__", "").startswith("apps."):
            metodo = codigo.co_qualname.rsplit(".", 1)[-1]
            nomes.append(f"{classe.__module__}.{classe.__qualname__}.{metodo}")
    return nomes


def _politica_instrumentada(original):
    @functools.wraps(original)
    def envolvida(*args, **kwargs):
        quadro = sys._getframe(1)
        while quadro is not None:
            CHAMADORES_DA_POLITICA.update(_nomes_registraveis_do_quadro(quadro))
            quadro = quadro.f_back
        return original(*args, **kwargs)

    setattr(envolvida, _ATRIBUTO_DE_INSTRUMENTACAO, True)
    return envolvida


def modulos_de_producao_que_importaram_a_politica():
    """Módulos de `apps.` (fora de testes) que têm a política ligada a um nome
    próprio.

    `from apps.core.requisicao import recusar_dado_nao_contratado` COPIA a
    referência para o módulo que importa. Trocar só o atributo de
    `apps.core.requisicao` não alcançaria nenhuma das superfícies já
    importadas — o embrulho simplesmente nunca rodaria, e o registro ficaria
    vazio sem ninguém saber por quê. Esta função é o que
    `test_o_embrulho_esta_aplicado_em_toda_superficie_que_importou_a_politica`
    usa para conferir que o embrulho pegou.
    """
    encontrados = {}
    for nome_modulo, modulo in list(sys.modules.items()):
        if not nome_modulo.startswith("apps.") or e_codigo_de_teste(nome_modulo):
            continue
        if modulo is None:
            continue
        alvo = getattr(modulo, NOME_DA_POLITICA, None)
        if callable(alvo):
            encontrados[nome_modulo] = alvo
    return encontrados


def aplicar_instrumentacao():
    """Embrulha a política no módulo de origem e em todo módulo de produção
    que já a importou pelo nome. Idempotente."""
    import apps.core.requisicao as requisicao

    original = requisicao.recusar_dado_nao_contratado
    if getattr(original, _ATRIBUTO_DE_INSTRUMENTACAO, False):
        return original

    envolvida = _politica_instrumentada(original)
    # A origem primeiro: quem importar DEPOIS desta linha já recebe a versão
    # instrumentada, sem precisar de nova varredura de módulos.
    requisicao.recusar_dado_nao_contratado = envolvida
    for nome_modulo, alvo in modulos_de_producao_que_importaram_a_politica().items():
        if alvo is original:
            setattr(sys.modules[nome_modulo], NOME_DA_POLITICA, envolvida)
    return envolvida


def conferencia_de_execucao_se_aplica(argumentos, palavra_chave, expressao_de_marca, diretorio):
    """`True` quando a invocação do pytest pediu a suíte INTEIRA.

    Função pura, com as decisões todas nos parâmetros, para
    `test_a_regra_de_quando_conferir_e_a_que_esta_escrita` poder medi-la com
    entradas sintéticas. É a parte do mecanismo que pode desligá-lo por
    inteiro, e um mecanismo desligado que ninguém percebe é o defeito que a
    BL-171 existe para não cometer.
    """
    if palavra_chave or expressao_de_marca:
        return False
    alvos = [str(argumento) for argumento in argumentos if not str(argumento).startswith("-")]
    return not alvos or alvos == [str(diretorio)]


def superficies_nao_exercitadas(chamadores):
    """`{superficie: motivo}` para cada superfície de escrita que a varredura
    descobre e que nunca chegou à política durante a sessão."""
    from apps.core.tests.test_dl019_varredura_de_contratos import (
        _alvos_alcancaveis,
        superficies_de_escrita,
    )

    superficies, _ = superficies_de_escrita(_alvos_alcancaveis())
    faltando = {}
    for nome, superficie in superficies.items():
        # `nome_efetivo` é o nome da CLASSE ROTEADA mais o atributo que
        # responde (`apps.empresas.views.EmpresaDetailView.put`), ou o da view
        # de função. O handler pode vir de um mixin do projeto, e nesse caso o
        # quadro da pilha traz o qualname do MIXIN — que é compartilhado. O
        # registro resolve isso pela classe da instância (ver
        # `_nomes_registraveis_do_quadro`), e aqui só se aceita o nome
        # efetivo: exercitar uma rota não marca outra que use o mesmo mixin
        # (BL-179/B6).
        if superficie.nome_efetivo not in chamadores:
            faltando[nome] = (
                "nenhuma requisição de teste desta sessão fez esta superfície chegar a "
                f"apps.core.requisicao.{NOME_DA_POLITICA}"
            )
    return faltando


def pytest_configure(config):
    # Cedo, e não numa fixture, para que qualquer módulo de produção importado
    # durante a COLETA já pegue a versão instrumentada pela origem.
    aplicar_instrumentacao()


# ---------------------------------------------------------------------------
# BL-178 (achado B5 da rodada 2): nenhum teste pode depender de artefato NÃO
# VERSIONADO
# ---------------------------------------------------------------------------

# Backend de estáticos que a SUÍTE usa. O de produção
# (`whitenoise.storage.CompressedManifestStaticFilesStorage`, em
# `config/settings.py`) exige o `staticfiles.json` que só existe depois de
# `collectstatic` — e a integração contínua roda `collectstatic` DEPOIS do
# pytest, de propósito (DE-012): se rodasse antes, a CI passaria com um
# `{% static %}` que falharia na máquina de quem desenvolve.
#
# O efeito colateral disso foi o inverso, e ninguém media: a árvore de trabalho
# tinha um `staticfiles/` de uma execução antiga (ignorado pelo Git), o teste
# que renderiza o admin passava LOCALMENTE e falhava na CI com
# `ValueError: Missing staticfiles manifest entry for 'admin/css/base.css'`.
# "1058 passed" foi declarado quatro vezes enquanto a CI dizia
# `1 failed, 1055 passed`.
#
# O manifesto é artefato de IMPLANTAÇÃO, não insumo de teste. A suíte passa a
# usar o storage simples e um `STATIC_ROOT` temporário e vazio, de modo que o
# resultado seja o MESMO em árvore limpa e em árvore com sobras — que é a
# propriedade que faltava. O pipeline de estáticos continua exercido pela CI
# (passo `collectstatic`) e pelo `Dockerfile`; nada foi afrouxado ali.
BACKEND_DE_ESTATICOS_DA_SUITE = "django.contrib.staticfiles.storage.StaticFilesStorage"


@pytest.fixture(scope="session", autouse=True)
def estaticos_independentes_do_manifesto(django_test_environment, tmp_path_factory):
    """Sessão inteira, e não só o teste que renderiza o admin: a classe do
    defeito é "teste que passa por causa de artefato não versionado", e tratar
    caso a caso deixa o próximo nascer.

    `apps/core/tests/test_dl019_estaticos_da_suite.py` é o controle positivo —
    ele aponta `STATIC_ROOT` para um diretório vazio e renderiza uma página do
    admin, de forma que remover esta fixture reprove a suíte **inclusive em
    árvore suja**, que é onde a medição era permissiva.
    """
    from django.conf import settings
    from django.test import override_settings

    substituicao = override_settings(
        STORAGES={
            **settings.STORAGES,
            "staticfiles": {"BACKEND": BACKEND_DE_ESTATICOS_DA_SUITE},
        },
        STATIC_ROOT=str(tmp_path_factory.mktemp("estaticos-da-suite")),
    )
    substituicao.enable()
    try:
        yield
    finally:
        substituicao.disable()


def _anunciar(config, texto, vermelho=False):
    escritor = config.pluginmanager.get_plugin("terminalreporter")
    if escritor is not None:
        escritor.write_line(texto, red=vermelho)
    else:  # pragma: no cover - pytest sem relatório de terminal
        print(texto)


def pytest_sessionfinish(session, exitstatus):
    """Conferência final do elo de execução.

    Só reprova quando a sessão já estava verde: uma suíte com falhas pode ter
    interrompido superfícies legitimamente, e transformar uma falha em duas
    esconde a primeira.

    Anuncia SEMPRE o que fez — inclusive quando decide não conferir. Um
    mecanismo que só fala quando reprova é indistinguível de um mecanismo
    desligado, e "a conferência não rodou" foi exatamente a forma da falha que
    a BL-170 acabou de corrigir na varredura de contratos.
    """
    if exitstatus != 0:
        _anunciar(
            session.config, "BL-171: conferência do elo de execução pulada (sessão vermelha)."
        )
        return
    if not conferencia_de_execucao_se_aplica(
        session.config.args,
        getattr(session.config.option, "keyword", ""),
        getattr(session.config.option, "markexpr", ""),
        session.config.invocation_params.dir,
    ):
        _anunciar(
            session.config,
            "BL-171: conferência do elo de execução pulada (execução parcial — "
            "ela só vale para a suíte inteira).",
        )
        return

    faltando = superficies_nao_exercitadas(CHAMADORES_DA_POLITICA)
    if not faltando:
        _anunciar(
            session.config,
            "BL-171: toda superfície de escrita da varredura foi exercitada nesta "
            f"sessão ({len(CHAMADORES_DA_POLITICA)} pontos de produção chegaram à política).",
        )
        return

    session.exitstatus = 1
    linhas = [
        "",
        "BL-171 — superfície de escrita que a varredura conhece e que NENHUM "
        "teste desta sessão exercitou:",
    ]
    linhas += [f"  {nome}: {motivo}" for nome, motivo in sorted(faltando.items())]
    linhas += [
        "",
        "A política estar escrita no fonte não prova que ela roda. Escreva um "
        "teste que faça uma requisição a esta superfície — ou, se a superfície "
        "não devia existir, tire-a do urlconf.",
        "",
        "Atenção ao ler a saída: o resumo do pytest conta TESTES, e nenhum "
        "teste falhou. Quem reprova aqui é o CÓDIGO DE SAÍDA da sessão, que "
        "esta conferência acaba de pôr em 1 — é ele que a integração contínua "
        "lê.",
        "",
    ]
    _anunciar(session.config, "\n".join(linhas), vermelho=True)
