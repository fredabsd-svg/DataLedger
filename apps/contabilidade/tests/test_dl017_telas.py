"""Testes da DL-017, fase B: as telas da contabilidade (views_web.py).

Cada teste referencia o critério de aceite numerado do plano
docs/planos/DL-017-interface-da-contabilidade.md. Dados 100% sintéticos,
criados nos próprios testes (nenhum dado real de cliente).

Este módulo TAMBÉM funciona como urlconf de teste (`urlpatterns` abaixo,
usado via `@pytest.mark.urls(__name__)`): as rotas de `apps.contabilidade.
urls_web` JÁ estão costuradas em `config/urls.py` (a costura entre as
fases, feita pelo arquiteto-senior) no prefixo "contabilidade/painel/"
documentado em `urls_web.py` — este urlconf de teste espelha esse mesmo
prefixo por isolamento (não depender de `config/urls.py` para testar só
esta fase), não porque a costura esteja pendente. O achado 13 da auditoria
da DL-017 (rodada 1) encontrou esta afirmação já desmentida pelo próprio
commit em que vivia: comentário desatualizado é o mesmo defeito que a
instrução permanente do Fred em CLAUDE.md cobra para `docs/agents/
estado.md` — só que em código. Quem quiser testar contra o urlconf REAL
(não este espelho) encontra isso em
`apps.contabilidade.tests.test_dl017_urlconf_integrado` (achado 9 /
BL-95, responsabilidade do desenvolvedor-pleno).
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth import views as auth_views
from django.urls import include, path, reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import (
    Conta,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# urlconf de teste — ver docstring do módulo.
urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("empresas/", include("apps.empresas.urls")),
    path("contabilidade/", include("apps.contabilidade.urls")),
    path("contabilidade/painel/", include("apps.contabilidade.urls_web")),
    path("", include("apps.tenancy.urls")),
]

pytestmark = [pytest.mark.django_db, pytest.mark.urls(__name__)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


@pytest.fixture
def cenario():
    """Escritório A (o cenário principal) e Escritório B (só para o
    critério 2 — isolamento), com um plano de contas de três níveis em A:

        1       Ativo            (sintética)
        1.1     Circulante       (aceita lançamento E tem filhas)
        1.1.01  Caixa            (analítica)
        1.1.02  Bancos           (analítica)
        2       Capital Social   (analítica, credora)
    """
    escritorio_a = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj="44455566000183"
    )

    ativo = Conta.objects.create(
        empresa=empresa_a,
        codigo="1",
        nome="Ativo",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    circulante = Conta.objects.create(
        empresa=empresa_a,
        codigo="1.1",
        nome="Circulante",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=True,
        conta_pai=ativo,
    )
    caixa = Conta.objects.create(
        empresa=empresa_a,
        codigo="1.1.01",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=circulante,
    )
    bancos = Conta.objects.create(
        empresa=empresa_a,
        codigo="1.1.02",
        nome="Bancos",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=circulante,
    )
    capital = Conta.objects.create(
        empresa=empresa_a,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "ativo": ativo,
        "circulante": circulante,
        "caixa": caixa,
        "bancos": bancos,
        "capital": capital,
    }


def _hoje_str():
    return timezone.localdate().isoformat()


def _extrair_valores_ptbr(html, classe="valor-monetario"):
    """Extrai os textos dentro de `<... class="{classe}">...</...>` de um
    HTML renderizado, para os testes de conciliação (critério 6) sem
    depender de um parser de HTML completo.
    """
    padrao = re.compile(rf'class="{classe}"[^>]*>([^<]+)<')
    return [texto.strip() for texto in padrao.findall(html)]


def _extrair_valor_por_rotulo(html, rotulo):
    """BL-308 (achado A2 da auditoria DL-024, rodada 3): extrai o valor
    monetário ANCORADO pelo rótulo de texto que o precede, em vez de pela
    N-ésima ocorrência de `class="valor-monetario"` no trecho.

    A extração POSICIONAL (`_extrair_valores_ptbr`) é frágil justamente
    onde ela importa mais: no estado "não fecha", a faixa tem um TERCEIRO
    valor monetário antes dos dois de sempre (a diferença, dentro do
    próprio texto do veredito — ver `balancete.html`), o que desloca os
    índices; e, mais grave, ela não prova QUAL rótulo está associado a
    QUAL número — uma troca de `total_creditos_ptbr` por
    `total_debitos_ptbr` no template não muda a CONTAGEM de valores, só
    o CONTEÚDO sob um rótulo específico. Ancorar pelo rótulo é o que
    permite a uma asserção dizer "o número sob 'Créditos' é X", que é a
    afirmação que de fato importa aqui.
    """
    padrao = re.compile(
        rf'<span class="contexto-rotulo">{re.escape(rotulo)}</span>\s*'
        r'<strong class="valor-monetario">([^<]+)</strong>'
    )
    m = padrao.search(html)
    assert m, f"rótulo {rotulo!r} não encontrado em: {html}"
    return m.group(1).strip()


def _ptbr_para_decimal(texto):
    return Decimal(texto.strip().replace(".", "").replace(",", "."))


def _exige_veredito_balancete(contexto, esperado):
    """BL-290/BL-302 (rodada 4 da auditoria DL-024): `veredito_balancete`
    tem que EXISTIR no contexto de renderização e valer EXATAMENTE
    `esperado` — nunca aceito por AUSÊNCIA. `contexto["chave"]` levanta
    `KeyError` quando a chave não existe em NENHUM dos contextos
    renderizados (é o comportamento de `django.test.client.ContextList`,
    que soma os contextos de `base.html` e `balancete.html`); deixamos
    subir, de propósito — não convertemos em `False`/`None` nem
    engolimos, porque "a chave não existe" e "a chave existe e está
    errada" são dois defeitos DIFERENTES e os dois precisam reprovar.

    Correção pedida pelo arquiteto-senior nesta rodada: um teste que só
    lesse o TEXTO renderizado da faixa continuaria verde mesmo com a
    chave AUSENTE, porque o template (de propósito — ver o comentário em
    balancete.html) cai no mesmo ramo visual de "nada a conferir" quando
    `veredito_balancete` não bate com "fecha" nem "nao_fecha". Comportamento
    certo POR ACIDENTE (a ausência da chave) é indistinguível de
    comportamento certo POR DECISÃO até o dia em que a causa acidental
    muda sem que a tela mude — e nenhum teste que só olhasse o texto
    saberia a diferença. Esta função força a leitura pela CHAVE, não pelo
    efeito visual dela.
    """
    valor = contexto["veredito_balancete"]
    assert valor == esperado, f"veredito_balancete = {valor!r}, esperado {esperado!r}"


def test_controle_exige_veredito_balancete_distingue_ausencia_de_valor_errado():
    """Controle de `_exige_veredito_balancete` — prova, por mutação
    SINTÉTICA (não tocando em `views_web.py`, fora do meu escopo de
    arquivos nesta rodada), os três casos que a função precisa distinguir:
    chave ausente reprova (`KeyError`), chave certa passa, chave presente
    mas com o valor ERRADO reprova (`AssertionError`). Sem este controle,
    a própria guarda poderia estar "de enfeite" sem que nada acusasse —
    lição repetida desta rodada (A2/BL-290: mecanismo que declara guardar
    e não guarda).
    """
    with pytest.raises(KeyError):
        _exige_veredito_balancete({}, "nada_a_conferir")

    _exige_veredito_balancete({"veredito_balancete": "nada_a_conferir"}, "nada_a_conferir")

    with pytest.raises(AssertionError):
        _exige_veredito_balancete({"veredito_balancete": "fecha"}, "nada_a_conferir")


# ---------------------------------------------------------------------------
# Critérios 1, 2 e 3 — autorização e sigilo
# ---------------------------------------------------------------------------


def _urls_de_leitura(empresa_id, conta_id):
    return {
        "plano_de_contas": reverse("contabilidade_web:plano_de_contas", args=[empresa_id]),
        "diario": reverse("contabilidade_web:diario", args=[empresa_id]),
        "razao": reverse("contabilidade_web:razao", args=[empresa_id, conta_id]),
        "balancete": reverse("contabilidade_web:balancete", args=[empresa_id]),
        "conferencia": reverse("contabilidade_web:conferencia", args=[empresa_id]),
    }


@pytest.mark.parametrize(
    "papel,espera_acesso",
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, True),
        (Papel.FINANCEIRO, True),
        (Papel.PARALEGAL, True),
        (Papel.CLIENTE, False),
    ],
)
def test_leitura_das_telas_depende_do_papel_igual_a_api(client, cenario, papel, espera_acesso):
    """Critério 1: a MESMA função (`papel_pode_ler_contabilidade`) decide a
    leitura na tela — o papel CLIENTE recebe negativa em TODAS as cinco
    telas de leitura, e os cinco papéis operacionais têm acesso. Este teste
    é independente do de `test_permissoes_contabilidade.py` (que testa a
    função direto) e do de `test_dl015_saidas_com_periodo.py` (que testa a
    API): nenhum deriva do outro, e uma mutação na regra compartilhada
    derruba os três.
    """
    _autenticar(client, cenario["escritorio_a"], papel=papel, username=f"u-{papel}")
    urls = _urls_de_leitura(cenario["empresa_a"].id, cenario["caixa"].id)
    for nome, url in urls.items():
        resposta = client.get(url)
        if espera_acesso:
            assert resposta.status_code in (200, 400), f"{nome}: {resposta.status_code}"
        else:
            assert resposta.status_code == 403, f"{nome}: esperava 403, veio {resposta.status_code}"
            assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


@pytest.mark.parametrize(
    "papel,espera_acesso",
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, True),
        (Papel.FINANCEIRO, True),
        (Papel.PARALEGAL, False),  # PodeEscriturar não inclui PARALEGAL
        (Papel.CLIENTE, False),
    ],
)
def test_escrita_das_telas_depende_do_papel_igual_a_api(client, cenario, papel, espera_acesso):
    """Critério 1 (lado escrita): a tela de criar conta e a de lançar usam
    a MESMA `PodeEscriturar` que a API já usa — não uma segunda lista de
    papéis.
    """
    _autenticar(client, cenario["escritorio_a"], papel=papel, username=f"w-{papel}")
    empresa_id = cenario["empresa_a"].id
    urls = [
        reverse("contabilidade_web:conta_nova", args=[empresa_id]),
        reverse("contabilidade_web:lancamento_novo", args=[empresa_id]),
    ]
    for url in urls:
        resposta = client.get(url)
        if espera_acesso:
            assert resposta.status_code == 200, url
        else:
            assert resposta.status_code == 403, url
            assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


def test_empresa_de_outro_escritorio_da_404_em_toda_tela(client, cenario):
    """Critério 2: pedir a empresa B (de outro escritório) autenticado no
    escritório A nunca devolve dado — sempre 404, em toda tela.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa_b_id = cenario["empresa_b"].id
    urls = list(_urls_de_leitura(empresa_b_id, cenario["caixa"].id).values())
    urls.append(reverse("contabilidade_web:conta_nova", args=[empresa_b_id]))
    urls.append(reverse("contabilidade_web:lancamento_novo", args=[empresa_b_id]))
    for url in urls:
        resposta = client.get(url)
        assert resposta.status_code == 404, url


def test_falta_de_permissao_nunca_e_500_nem_texto_cru(client, cenario):
    """Critério 3: o template dedicado aparece, com explicação e caminho de
    volta — nunca um 500, nunca uma mensagem crua sem contexto.
    """
    _autenticar(client, cenario["escritorio_a"], papel=Papel.CLIENTE, username="cliente")
    resposta = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[cenario["empresa_a"].id])
    )
    assert resposta.status_code == 403
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    assert "<a href=" in conteudo  # caminho de volta


def test_criar_conta_com_codigo_duplicado_da_erro_no_campo_sem_500(client, cenario):
    """Regressão dirigida: `empresa` fica FORA dos campos do formulário
    (nunca é escolha do cliente), e por isso o Django EXCLUI a
    UniqueConstraint "codigo_unico_por_empresa" da checagem de
    `validate_unique()` dentro de `full_clean()` — uma constraint composta
    é pulada quando qualquer campo dela está fora do formulário. Sem o
    `try/except IntegrityError` em `conta_nova`, isto seria um 500 do
    Postgres, não um erro de formulário.
    """
    empresa = cenario["empresa_a"]  # já tem uma conta com código "1" (Ativo)
    _autenticar(client, cenario["escritorio_a"])
    antes = Conta.objects.filter(empresa=empresa).count()

    resposta = client.post(
        reverse("contabilidade_web:conta_nova", args=[empresa.id]),
        {
            "codigo": "1",
            "nome": "Outra conta com o mesmo código",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
        },
    )

    assert resposta.status_code == 200  # re-renderiza o formulário, não 500
    assert Conta.objects.filter(empresa=empresa).count() == antes
    assert "Já existe uma conta com este código" in resposta.content.decode()


def test_combo_de_conta_pai_nao_lista_conta_de_outra_empresa(client, cenario):
    """Achado 8 / BL-94: mutante sobrevivente na rodada 1 — trocar
    `Conta.objects.filter(empresa=empresa)` por `Conta.objects.all()` em
    `ContaCriarForm.__init__` (views_web.py) sobrevivia à suíte inteira (0
    falhas em 446). O controle já funcionava (verificado por medição na
    auditoria), só não tinha teste. Cobre as DUAS formas de vazamento que
    o critério 2 do plano proíbe: uma empresa do MESMO escritório (que
    `escritorio=request.escritorio` sozinho NÃO filtra — só `empresa=`
    filtra) e uma empresa de OUTRO escritório.

    Se este teste voltar a passar depois de `Conta.objects.all()` no
    lugar do filtro, o formulário "Nova conta" passaria a exibir o plano
    de contas inteiro de todos os clientes de todos os escritórios —
    código e nome, que revelam estrutura societária, bancos e litígios.
    """
    empresa_a = cenario["empresa_a"]
    empresa_a2 = Empresa.objects.create(
        escritorio=cenario["escritorio_a"],
        razao_social="Empresa A2 Ltda",
        cnpj="99988877000199",
    )
    conta_mesmo_escritorio = Conta.objects.create(
        empresa=empresa_a2,
        codigo="9.99",
        nome="Conta sigilosa da Empresa A2",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta_outro_escritorio = Conta.objects.create(
        empresa=cenario["empresa_b"],
        codigo="8.88",
        nome="Conta sigilosa da Empresa B",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )

    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(reverse("contabilidade_web:conta_nova", args=[empresa_a.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    assert conta_mesmo_escritorio.nome not in conteudo
    assert conta_mesmo_escritorio.codigo not in conteudo
    assert conta_outro_escritorio.nome not in conteudo
    assert conta_outro_escritorio.codigo not in conteudo
    # Positivo: as contas da PRÓPRIA empresa continuam disponíveis como
    # conta-pai — a correção não pode isolar demais e esvaziar o combo.
    assert cenario["circulante"].nome in conteudo


# ---------------------------------------------------------------------------
# Critérios 4, 5 e 6 — apresentação contábil
# ---------------------------------------------------------------------------


def test_valores_em_ptbr_e_saldo_com_indicador_dc(client, cenario):
    """Critérios 4 e 5: 1234567.89 aparece como "1.234.567,89"; o saldo vem
    com indicador D/C, nunca com sinal negativo.
    """
    empresa = cenario["empresa_a"]
    criar_lancamento(
        empresa=empresa,
        data=timezone.localdate(),
        historico="Aporte de capital",
        itens=[
            {
                "conta": cenario["caixa"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("1234567.89"),
            },
            {
                "conta": cenario["capital"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("1234567.89"),
            },
        ],
    )
    _autenticar(client, cenario["escritorio_a"])
    inicio = timezone.localdate().replace(day=1).isoformat()
    fim = _hoje_str()
    url = reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    resposta = client.get(url)
    conteudo = resposta.content.decode()
    assert resposta.status_code == 200
    assert "1.234.567,89" in conteudo
    assert "-1.234.567,89" not in conteudo
    assert "−1.234.567,89" not in conteudo
    # Caixa é devedora e recebeu débito: saldo devedor -> "D".
    assert '<span class="indicador-natureza">D' in conteudo
    # Capital é credora e recebeu crédito: saldo credor -> "C".
    assert '<span class="indicador-natureza">C' in conteudo


def test_saldo_zero_e_natureza_invertida_na_tela_nunca_negativo(client, cenario):
    """Ressalva do critério 5 na auditoria da DL-017, rodada 1: M4 (saldo
    zero ganhando natureza D), M5 (natureza apurada nunca inverte) e M6
    (saldo voltando a poder ser negativo) só eram mortos por testes da
    API — nenhum teste de TELA cobria os três, mesmo a função sendo a
    MESMA (`_saldo_absoluto_com_natureza`, reaproveitada de views.py por
    DE-026). Cobre os três pelo lado da tela (Razão e Balancete).
    """
    empresa = cenario["empresa_a"]
    hoje = timezone.localdate()

    # Caixa é CADASTRADA devedora; um período em que ela recebe mais
    # CRÉDITO (250) do que DÉBITO (100) apura saldo CREDOR (150) — a
    # natureza apurada inverte em relação à cadastrada (M5), e o valor
    # tem que aparecer absoluto, nunca com sinal negativo (M6).
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Entrada em Caixa",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Saída maior que o saldo devedor de Caixa",
        itens=[
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("250.00")},
            {"conta": cenario["caixa"], "tipo": TipoPartida.CREDITO, "valor": Decimal("250.00")},
        ],
    )
    # Bancos (também devedora) recebe débito e crédito IGUAIS: saldo
    # ZERO, que RC-61 diz não ter lado nenhum (M4).
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Entrada em Bancos",
        itens=[
            {"conta": cenario["bancos"], "tipo": TipoPartida.DEBITO, "valor": Decimal("40.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("40.00")},
        ],
    )
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Devolução em Bancos",
        itens=[
            {"conta": cenario["capital"], "tipo": TipoPartida.DEBITO, "valor": Decimal("40.00")},
            {"conta": cenario["bancos"], "tipo": TipoPartida.CREDITO, "valor": Decimal("40.00")},
        ],
    )

    _autenticar(client, cenario["escritorio_a"])
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()

    # Razão de Caixa: saldo final apurado é CREDOR (150,00), embora Caixa
    # seja cadastrada devedora.
    url_razao = (
        reverse("contabilidade_web:razao", args=[empresa.id, cenario["caixa"].id])
        + f"?inicio={inicio}&fim={fim}"
    )
    resposta = client.get(url_razao)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "150,00" in conteudo
    assert "-150,00" not in conteudo
    assert "−150,00" not in conteudo
    assert '<span class="indicador-natureza">C' in conteudo

    # Balancete: a linha de Bancos tem saldo final "0,00" SEM indicador de
    # natureza nenhum — nem "D", nem "C".
    url_balancete = (
        reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    )
    resposta = client.get(url_balancete)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    # Divide pelas aberturas de `<tr>`: o pedaço que contém "1.1.02" (o
    # código de Bancos) vai do início da SUA própria linha até a próxima
    # `<tr>` — nunca cruza para a linha de outra conta (ao contrário de um
    # `re.search` não ancorado, que pegaria da PRIMEIRA `<tr>` do documento).
    pedacos = conteudo.split("<tr>")
    trecho = next(pedaco for pedaco in pedacos if "1.1.02" in pedaco)
    assert "0,00" in trecho
    assert '<span class="indicador-natureza">' not in trecho


def test_balancete_soma_das_linhas_proprias_bate_com_rodape(client, cenario):
    """Critério 6: a soma dos valores PRÓPRIOS de todas as linhas exibidas
    é igual ao total do rodapé (DE-024 §2) — mesmo com uma conta (Circulante)
    que tem movimento próprio E filhas ao mesmo tempo.
    """
    empresa = cenario["empresa_a"]
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Caixa",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
        ],
    )
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Banco",
        itens=[
            {"conta": cenario["bancos"], "tipo": TipoPartida.DEBITO, "valor": Decimal("500.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("500.00")},
        ],
    )
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Movimento próprio do grupo Circulante",
        itens=[
            {
                "conta": cenario["circulante"],
                "tipo": TipoPartida.DEBITO,
                "valor": Decimal("200.00"),
            },
            {
                "conta": cenario["capital"],
                "tipo": TipoPartida.CREDITO,
                "valor": Decimal("200.00"),
            },
        ],
    )

    _autenticar(client, cenario["escritorio_a"])
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()
    url = reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    # BL-276/BL-278 (rodada 2 da auditoria DL-024): a `.faixa-fechamento`
    # no topo da página (fora da tabela) TAMBÉM usa a classe
    # "valor-monetario" nos seus dois totais — é dinheiro, tem que
    # tabular, a regra não abre exceção por estar fora de `<table>`. Por
    # isso a extração abaixo passa a ser escopada à PRÓPRIA tabela: sem
    # isso, os dois valores da faixa entrariam na contagem do "corpo" e
    # deslocariam a fatia de 6 em 6 usada logo adiante.
    tabela = re.search(r"<table\b.*?</table>", conteudo, re.DOTALL).group(0)

    # Extrai as colunas "Débitos próprios" e "Créditos próprios" pela
    # classe compartilhada "valor-monetario": cada linha do corpo tem 6
    # valores monetários, na ordem em que o template os escreve (saldo
    # anterior, débitos, créditos, débitos próprios, créditos próprios,
    # saldo final). O rodapé tem 2 (total débitos, total créditos).
    todos_os_valores = _extrair_valores_ptbr(tabela)
    # Descobre o total do rodapé (as duas últimas ocorrências antes do fim
    # da tabela) usando o texto ao redor, que é mais robusto do que contar
    # posições: procura os dois <td class="valor-monetario"> dentro de
    # <tr class="linha-total">.
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)
    valores_rodape = _extrair_valores_ptbr(rodape)
    assert len(valores_rodape) == 2
    total_debitos_rodape = _ptbr_para_decimal(valores_rodape[0])
    total_creditos_rodape = _ptbr_para_decimal(valores_rodape[1])

    # 5 linhas (Ativo, Circulante, Caixa, Bancos, Capital) x 6 colunas
    # monetárias = 30 valores no corpo, mais 2 no rodapé = 32.
    assert len(todos_os_valores) == 32
    valores_corpo = todos_os_valores[:-2]
    soma_debitos_proprios = Decimal("0")
    soma_creditos_proprios = Decimal("0")
    for i in range(0, len(valores_corpo), 6):
        linha = valores_corpo[i : i + 6]
        soma_debitos_proprios += _ptbr_para_decimal(linha[3])
        soma_creditos_proprios += _ptbr_para_decimal(linha[4])

    assert soma_debitos_proprios == total_debitos_rodape == Decimal("1700.00")
    assert soma_creditos_proprios == total_creditos_rodape == Decimal("1700.00")

    # BL-308 (achado A2 da auditoria DL-024, rodada 3): o par de
    # asserções acima tem o MESMO vício que a faixa tinha — soma o
    # débito próprio e o crédito próprio de TODAS as linhas e compara os
    # dois totais contra o rodapé. Por partida dobrada, esses dois totais
    # são SEMPRE iguais (1700,00 = 1700,00), então uma sabotagem que
    # trocasse `debitos_proprios_ptbr` por `creditos_proprios_ptbr` (e
    # vice-versa) em TODA linha do template não mudaria nenhuma das duas
    # SOMAS — cada uma continuaria fechando em 1700,00, porque a soma dos
    # débitos próprios de todo o plano é igual à soma dos créditos
    # próprios de todo o plano, com ou sem a troca. As linhas
    # individualmente, porém, são ASSIMÉTRICAS (Caixa só foi debitada;
    # Capital só foi creditada — nenhuma das duas tem os dois lados
    # iguais), e é isso que dá o poder de distinguir: uma checagem POR
    # LINHA, ancorada pelo NOME da conta (não pela posição), pega a troca
    # que a soma escondia.
    pedacos_de_linha = tabela.split("<tr>")

    def _proprios_da_conta(nome_conta):
        # A ÚLTIMA linha do corpo (Capital) não tem outro "<tr>" depois
        # dela antes do rodapé — o `<tr class="linha-total">` do `<tfoot>`
        # NÃO casa com o split por "<tr>" exato (tem atributo), então o
        # pedaço dela continuaria até o fim da tabela, absorvendo também
        # os 2 valores do rodapé. Corta no primeiro "</tr>" PRÓPRIO da
        # linha, que sempre existe (é a linha se fechando).
        trecho_completo = next(pedaco for pedaco in pedacos_de_linha if nome_conta in pedaco)
        trecho = trecho_completo.split("</tr>", 1)[0]
        valores = _extrair_valores_ptbr(trecho)
        assert len(valores) == 6, (nome_conta, valores)
        return _ptbr_para_decimal(valores[3]), _ptbr_para_decimal(valores[4])

    debito_proprio_caixa, credito_proprio_caixa = _proprios_da_conta("Caixa")
    assert debito_proprio_caixa == Decimal("1000.00"), debito_proprio_caixa
    assert credito_proprio_caixa == Decimal("0.00"), credito_proprio_caixa

    debito_proprio_capital, credito_proprio_capital = _proprios_da_conta("Capital Social")
    assert debito_proprio_capital == Decimal("0.00"), debito_proprio_capital
    assert credito_proprio_capital == Decimal("1700.00"), credito_proprio_capital

    # BL-290 (achado A2 da auditoria DL-024, rodada 2): a faixa de
    # fechamento (fora da <table>, por isso extraída separadamente) tem
    # que mostrar os MESMOS dois números do rodapé — é a mesma dupla de
    # totais em dois lugares da tela (BL-276/BL-278), não dois cálculos
    # independentes que por acaso deveriam bater. Antes desta correção,
    # nenhum teste conferia isso: o auditor trocou o crédito da faixa pelo
    # débito e fixou o veredito em "Fecha" — 1363 passed.
    #
    # ⚠️ BL-308 (achado A2 da rodada 3): ESTE bloco, sozinho, NÃO É GUARDA
    # contra a troca "crédito da faixa pelo débito" — o estado é
    # BALANCEADO (débito == crédito == 1700,00 por partida dobrada), e a
    # troca de um pelo outro é INVISÍVEL quando os dois já são o mesmo
    # número: o auditor mediu exatamente essa troca dando 1451 passed
    # aqui. O que este bloco prova é outra coisa, legítima por si só — que
    # a faixa e o rodapé mostram o MESMO valor sob rótulo equivalente
    # (conciliação, critério 6) —, mas não prova QUAL rótulo tem qual
    # valor. A extração agora é ANCORADA PELO RÓTULO (não mais pela
    # posição: o estado "não fecha" tem um terceiro valor monetário — a
    # diferença — que desloca a contagem). A guarda de verdade contra a
    # troca débito/crédito só é possível no estado DIVERGENTE, onde os
    # dois números são diferentes entre si por construção — ver
    # `test_balancete_veredito_nao_fecha_e_exercitado_com_totais_divergentes`,
    # logo abaixo, que é quem a exerce.
    faixa = re.search(r'<div class="faixa-fechamento[^"]*"[^>]*>.*?</div>', conteudo, re.DOTALL)
    assert faixa, "controle: a faixa de fechamento precisa estar presente com movimento"
    debitos_proprios_faixa = _extrair_valor_por_rotulo(
        faixa.group(0), "Débitos próprios do período"
    )
    creditos_proprios_faixa = _extrair_valor_por_rotulo(
        faixa.group(0), "Créditos próprios do período"
    )
    assert _ptbr_para_decimal(debitos_proprios_faixa) == total_debitos_rodape == Decimal("1700.00")
    assert (
        _ptbr_para_decimal(creditos_proprios_faixa) == total_creditos_rodape == Decimal("1700.00")
    )

    # E o veredito é "Fecha" — ramo ALCANÇADO de verdade (os totais fecham
    # por construção, partida dobrada — ver o comentário do template), não
    # decidido por comparação de texto pt-BR (BL-289/BL-290: o "if" agora
    # ramifica por `veredito_balancete`, uma palavra vinda da view em
    # `Decimal`, nunca por igualdade de `total_debitos_ptbr`/
    # `total_creditos_ptbr`). A checagem pela CHAVE do contexto
    # (`_exige_veredito_balancete`) vem primeiro, de propósito: ela
    # reprova tanto a ausência da chave quanto um valor errado — olhar só
    # o TEXTO da faixa não distingue "está certo por decisão" de "está
    # certo por acidente" (ver o docstring da função).
    _exige_veredito_balancete(resposta.context, "fecha")
    assert "Fecha" in faixa.group(0)
    assert "Não fecha" not in faixa.group(0)
    assert "faixa-fechamento--nao-fecha" not in faixa.group(0)
    assert "faixa-fechamento--nada-a-conferir" not in faixa.group(0)


# ---------------------------------------------------------------------------
# Critérios 7, 8 e 9 — datas, contexto e período
# ---------------------------------------------------------------------------


def test_datas_em_ptbr_na_exibicao(client, cenario):
    """Critério 7: datas aparecem em dd/mm/aaaa na exibição."""
    empresa = cenario["empresa_a"]
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Teste de data",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )
    _autenticar(client, cenario["escritorio_a"])
    url = reverse("contabilidade_web:diario", args=[empresa.id]) + (
        f"?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    resposta = client.get(url)
    assert hoje.strftime("%d/%m/%Y") in resposta.content.decode()


def test_contexto_visivel_empresa_e_periodo(client, cenario):
    """Critério 8: em toda tela de dados, o usuário identifica escritório,
    empresa e (quando aplicável) período em que está operando.
    """
    empresa = cenario["empresa_a"]
    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()

    resposta = client.get(reverse("contabilidade_web:plano_de_contas", args=[empresa.id]))
    conteudo = resposta.content.decode()
    assert "Escritório A" in conteudo  # já vem do header (base.html/DL-009)
    assert "Empresa A Ltda" in conteudo

    url = reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    resposta = client.get(url)
    conteudo = resposta.content.decode()
    assert "Empresa A Ltda" in conteudo
    # BL-283(a)/rodada 2 da DL-024: o rótulo de contexto perdeu o
    # dois-pontos e passou a envolver o valor em <strong> — mesma marcação
    # que "Usuário"/"Escritório ativo" já usavam em base.html (a
    # inconsistência era exatamente essa: metade da faixa em um padrão,
    # metade em outro). O texto por extenso continua presente; só a
    # marcação mudou.
    assert '<span class="contexto-rotulo">Período</span>' in conteudo
    assert hoje.replace(day=1).strftime("%d/%m/%Y") in conteudo


def test_periodo_ausente_usa_mes_corrente_como_sugestao(client, cenario):
    """Critério 9: sem 'inicio'/'fim' na querystring, a tela usa o MÊS
    CORRENTE como período sugerido — diferente da API (DE-016), que recusa
    ausência. A tela nunca faz o contador topar com um 400 só por abrir a
    página pela primeira vez.
    """
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(reverse("contabilidade_web:diario", args=[cenario["empresa_a"].id]))
    assert resposta.status_code == 200
    hoje = timezone.localdate()
    primeiro_dia = hoje.replace(day=1)
    assert primeiro_dia.strftime("%d/%m/%Y") in resposta.content.decode()


def test_periodo_invalido_da_mensagem_util_nao_quebra(client, cenario):
    """Critério 9: período malformado ou invertido gera mensagem útil, não
    500 nem período implícito silencioso.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa_id = cenario["empresa_a"].id

    resposta = client.get(
        reverse("contabilidade_web:diario", args=[empresa_id]) + "?inicio=2026-99-99&fim=2026-01-01"
    )
    assert resposta.status_code == 400
    assert "Data inválida" in resposta.content.decode()

    resposta = client.get(
        reverse("contabilidade_web:diario", args=[empresa_id]) + "?inicio=2026-02-01&fim=2026-01-01"
    )
    assert resposta.status_code == 400
    assert "não pode ser posterior" in resposta.content.decode()


def test_balancete_erro_de_periodo_oferece_saida_navegavel(client, cenario):
    """BL-301 (achado B3 da auditoria DL-024, rodada 2): o estado de erro
    do Balancete deixava a tela quase vazia — 397px de 800, sem tabela e
    sem saída, só a mensagem de erro e o formulário de período. Esta
    correção não muda o comportamento da VIEW (que continua recusando o
    período inválido com 400 e a mensagem de erro): acrescenta, no
    TEMPLATE, um link de volta ao período padrão — a mesma URL sem
    querystring, que a própria view já resolve para o mês corrente — como
    saída navegável equivalente à que o estado vazio já oferece (link para
    o plano de contas).
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa_id = cenario["empresa_a"].id
    url_balancete_sem_querystring = reverse("contabilidade_web:balancete", args=[empresa_id])

    resposta = client.get(url_balancete_sem_querystring + "?inicio=abacaxi&fim=2026-03-31")
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "Data inválida" in conteudo
    # A saída: um link para a MESMA URL, sem querystring — reproduzível
    # sem depender do texto exato do restante da frase.
    assert f'<a href="{url_balancete_sem_querystring}">' in conteudo
    # Controle negativo: o estado de SUCESSO (período válido) não mostra
    # este aviso — ele é exclusivo do estado de erro.
    hoje = timezone.localdate()
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()
    resposta_ok = client.get(url_balancete_sem_querystring + f"?inicio={inicio}&fim={fim}")
    assert resposta_ok.status_code == 200
    assert f'<a href="{url_balancete_sem_querystring}">' not in resposta_ok.content.decode()

    # E o link de fato funciona: segui-lo devolve 200 com uma resposta
    # válida (o período padrão, mês corrente) — não é um link decorativo.
    resposta_recuperada = client.get(url_balancete_sem_querystring)
    assert resposta_recuperada.status_code == 200


def test_balancete_veredito_nao_fecha_e_exercitado_com_totais_divergentes(
    client, cenario, monkeypatch
):
    """BL-290 (achado A2 da auditoria DL-024, rodada 2): o ramo "Não
    fecha" da faixa de fechamento é uma REDE DE SEGURANÇA — a apuração do
    Balancete garante débito igual a crédito por construção (partida
    dobrada dos lançamentos de origem), então esse ramo é INALCANÇÁVEL por
    qualquer fluxo legítimo da aplicação. "Inalcançável" não pode
    significar "não testado": o auditor mutou os dois valores da faixa e o
    veredito, e a suíte inteira devolveu 1363 passed, porque NADA
    exercitava o ramo "Não fecha".

    Este teste força a divergência sem corromper nenhum dado real: troca
    `apurar_balancete` (apps.contabilidade.services, importado por
    `apps.contabilidade.views_web`) por uma versão que devolve totais
    PROPOSITALMENTE diferentes — o mesmo tipo de defeito que o ramo existe
    para denunciar (corrupção de dado ou falha de agregação), simulado sem
    tocar no banco.
    """
    empresa = cenario["empresa_a"]
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Movimento para o cenário de divergência forçada",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("300.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("300.00")},
        ],
    )

    apuracao_real = views_web.apurar_balancete(
        empresa=empresa,
        inicio=hoje.replace(day=1),
        fim=hoje,
        nivel=None,
    )

    def _apuracao_divergente(*, empresa, inicio, fim, nivel=None):
        # As LINHAS continuam vindo da apuração real (para a tabela e a
        # soma "própria" do rodapé baterem entre si, como já testado por
        # test_balancete_soma_das_linhas_proprias_bate_com_rodape) — só o
        # TOTAL que a faixa mostra é corrompido, propositalmente, para
        # forçar o ramo que nenhum lançamento balanceado alcança.
        divergente = dict(apuracao_real)
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.01")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_divergente)

    _autenticar(client, cenario["escritorio_a"])
    url = (
        reverse("contabilidade_web:balancete", args=[empresa.id])
        + f"?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    resposta = client.get(url)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    # Pela CHAVE primeiro (ver o docstring de `_exige_veredito_balancete`):
    # reprova ausência de `veredito_balancete` ou valor errado, não só o
    # texto que o ramo "Não fecha" produz na tela.
    _exige_veredito_balancete(resposta.context, "nao_fecha")

    faixa = re.search(r'<div class="faixa-fechamento[^"]*"[^>]*>.*?</div>', conteudo, re.DOTALL)
    assert faixa, "controle: a faixa precisa estar presente"
    assert "faixa-fechamento--nao-fecha" in faixa.group(0), (
        "o ramo 'Não fecha' não foi exercitado: " + faixa.group(0)
    )
    assert "Não fecha" in faixa.group(0)
    assert "Fecha</strong>" not in faixa.group(0).replace("Não fecha", "")
    # O rodapé (dentro da <table>) continua mostrando os totais
    # DIVERGENTES tal como a view os recebeu — a tela não esconde a
    # inconsistência, denuncia.
    tabela = re.search(r"<table\b.*?</table>", conteudo, re.DOTALL).group(0)
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', tabela, re.DOTALL).group(0)
    valores_rodape = _extrair_valores_ptbr(rodape)
    total_debitos_rodape = _ptbr_para_decimal(valores_rodape[0])
    total_creditos_rodape = _ptbr_para_decimal(valores_rodape[1])
    assert total_debitos_rodape != total_creditos_rodape

    # BL-308 (achado A2 da auditoria DL-024, rodada 3) — A GUARDA DE
    # VERDADE contra "o crédito da faixa foi trocado pelo débito" só
    # existe AQUI, neste estado divergente: é o único em que os dois
    # números não são iguais por construção, então é o único em que a
    # troca de um pelo outro produz um resultado OBSERVÁVEL. O teste do
    # estado balanceado
    # (`test_balancete_soma_das_linhas_proprias_bate_com_rodape`) compara
    # 1700,00 com 1700,00 — a mesma troca lá dá `1451 passed`, medido pelo
    # auditor; não conta como guarda contra esta classe de sabotagem,
    # ainda que sirva de conciliação (critério 6).
    #
    # Extração ANCORADA PELO RÓTULO (não pela posição do N-ésimo
    # `class="valor-monetario"`): a faixa, no ramo "não fecha", tem um
    # valor monetário A MAIS antes dos dois de sempre — a própria
    # diferença, dentro do texto do veredito —, então contar posição
    # pegaria o valor errado.
    debitos_proprios_faixa = _extrair_valor_por_rotulo(
        faixa.group(0), "Débitos próprios do período"
    )
    creditos_proprios_faixa = _extrair_valor_por_rotulo(
        faixa.group(0), "Créditos próprios do período"
    )
    # Os dois números da faixa batem com os do rodapé, cada um sob o seu
    # PRÓPRIO rótulo — não apenas "os dois conjuntos de números
    # coincidem", que a troca de um pelo outro também satisfaria.
    assert _ptbr_para_decimal(debitos_proprios_faixa) == total_debitos_rodape == Decimal("300.00")
    assert _ptbr_para_decimal(creditos_proprios_faixa) == total_creditos_rodape == Decimal("300.01")
    # E os dois são DIFERENTES entre si — a faixa não pode dizer "diferença
    # de 0,01" e mostrar dois números iguais: é exatamente a contradição
    # que o auditor mediu no produto (300,00 e 300,00 sob "diferença de
    # 0,01"), e que este par de asserções torna impossível passar
    # despercebido.
    assert debitos_proprios_faixa != creditos_proprios_faixa, (
        debitos_proprios_faixa,
        creditos_proprios_faixa,
    )


def test_balancete_sem_movimento_diz_nada_a_conferir_por_decisao(client, cenario):
    """BL-302 (achado B4 da auditoria DL-024, rodada 2): a entrada padrão
    do Balancete — empresa com contas cadastradas, mês corrente sem
    NENHUM movimento ainda (o estado em que a tela abre no dia 1º de todo
    mês, em qualquer escritório real) — não pode dizer "Fecha": zero
    fecha com zero, não é FALSO, mas é a resposta mais destacada da tela
    virando ruído ambiente, no lugar que a DE-053 §3 reserva para a
    pergunta central. O veredito correto é "nada_a_conferir", vindo da
    VIEW pela chave `veredito_balancete` — `_exige_veredito_balancete`
    reprova tanto a ausência da chave quanto um valor incorreto (ver o
    controle acima e o docstring da função).
    """
    empresa = cenario["empresa_a"]  # tem 5 contas, NENHUM lançamento nesta fixture
    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()
    resposta = client.get(
        reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    )
    assert resposta.status_code == 200
    _exige_veredito_balancete(resposta.context, "nada_a_conferir")

    conteudo = resposta.content.decode()
    faixa = re.search(r'<div class="faixa-fechamento[^"]*"[^>]*>.*?</div>', conteudo, re.DOTALL)
    assert faixa, (
        "controle: mesmo sem movimento, a empresa tem contas cadastradas — a faixa aparece"
    )
    assert "Nada a conferir" in faixa.group(0)
    assert "Fecha</strong>" not in faixa.group(0)
    assert "faixa-fechamento--nada-a-conferir" in faixa.group(0)
    assert "faixa-fechamento--nao-fecha" not in faixa.group(0)


# ---------------------------------------------------------------------------
# Critérios 10 e 11 — lançamento: conferência de total e idempotência
# ---------------------------------------------------------------------------


def _post_lancamento(client, empresa_id, *, chave, data=None, historico="Teste", linhas=None):
    dados = {
        "acao": "gravar",
        "num_linhas": "4",
        "data": data or _hoje_str(),
        "historico": historico,
        "chave_idempotencia": chave,
    }
    for i, (conta_id, tipo, valor) in enumerate(linhas or [], start=1):
        dados[f"conta_{i}"] = str(conta_id)
        dados[f"tipo_{i}"] = tipo
        dados[f"valor_{i}"] = valor
    return client.post(reverse("contabilidade_web:lancamento_novo", args=[empresa_id]), dados)


def test_totais_diferentes_sao_recusados_mesmo_burlando_a_tela(client, cenario):
    """Critério 10: a tela mostra os dois totais e impede o envio enquanto
    forem diferentes — mas quem prova isto é o SERVIDOR. Este teste POSTa
    DIRETO para a view (o próprio "servidor" desta arquitetura — DE-026: não
    há API separada por trás), com débito != crédito, como faria um cliente
    que ignorasse qualquer aviso da tela. Nenhum lançamento pode ser criado.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    antes = LancamentoContabil.objects.count()

    resposta = _post_lancamento(
        client,
        empresa.id,
        chave="tentativa-burlada",
        linhas=[
            (cenario["caixa"].id, "debito", "100,00"),
            (cenario["capital"].id, "credito", "50,00"),
        ],
    )

    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == antes
    conteudo = resposta.content.decode()
    assert "100,00" in conteudo and "50,00" in conteudo
    assert "precisam ser iguais antes de gravar" in conteudo


def test_duplo_clique_nao_cria_dois_lancamentos(client, cenario):
    """Critério 11 (BL-43): duas submissões com a MESMA chave de
    idempotência (o duplo clique real: o navegador reenvia o MESMO corpo,
    inclusive o campo oculto, sem JavaScript nenhum) resultam em UM único
    lançamento gravado.
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    linhas = [
        (cenario["caixa"].id, "debito", "300,00"),
        (cenario["capital"].id, "credito", "300,00"),
    ]

    primeira = _post_lancamento(client, empresa.id, chave="duplo-clique-1", linhas=linhas)
    segunda = _post_lancamento(client, empresa.id, chave="duplo-clique-1", linhas=linhas)

    assert primeira.status_code == 302
    assert segunda.status_code == 302
    assert primeira["Location"] == segunda["Location"]
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1


def test_chave_reaproveitada_com_conteudo_diferente_nao_grava_o_lancamento_errado(client, cenario):
    """Complemento do critério 11: reaproveitar a MESMA chave para um
    conteúdo DIFERENTE nunca é aceito como se fosse sucesso (a mesma
    garantia que `criar_lancamento` já dá à API — ver `services.py`).
    """
    _autenticar(client, cenario["escritorio_a"])
    empresa = cenario["empresa_a"]
    _post_lancamento(
        client,
        empresa.id,
        chave="chave-conflitante",
        linhas=[
            (cenario["caixa"].id, "debito", "10,00"),
            (cenario["capital"].id, "credito", "10,00"),
        ],
    )
    antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    resposta = _post_lancamento(
        client,
        empresa.id,
        chave="chave-conflitante",
        linhas=[
            (cenario["caixa"].id, "debito", "20,00"),
            (cenario["capital"].id, "credito", "20,00"),
        ],
    )
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == antes


# ---------------------------------------------------------------------------
# Critério 12 — navegação de conferência
# ---------------------------------------------------------------------------


def test_navegacao_do_balancete_para_razao_e_do_razao_para_lancamento(client, cenario):
    empresa = cenario["empresa_a"]
    hoje = timezone.localdate()
    lancamento = criar_lancamento(
        empresa=empresa,
        data=hoje,
        historico="Navegação",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("77.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("77.00")},
        ],
    )
    _autenticar(client, cenario["escritorio_a"])
    inicio = hoje.replace(day=1).isoformat()
    fim = hoje.isoformat()

    resposta_balancete = client.get(
        reverse("contabilidade_web:balancete", args=[empresa.id]) + f"?inicio={inicio}&fim={fim}"
    )
    conteudo_balancete = resposta_balancete.content.decode()
    url_razao_esperada = (
        reverse("contabilidade_web:razao", args=[empresa.id, cenario["caixa"].id])
        + f"?inicio={inicio}&fim={fim}"
    )
    assert url_razao_esperada in conteudo_balancete

    resposta_razao = client.get(url_razao_esperada)
    assert resposta_razao.status_code == 200
    conteudo_razao = resposta_razao.content.decode()
    url_lancamento_esperada = reverse(
        "contabilidade_web:lancamento_detalhe", args=[empresa.id, lancamento.id]
    )
    assert url_lancamento_esperada in conteudo_razao

    resposta_lancamento = client.get(url_lancamento_esperada)
    assert resposta_lancamento.status_code == 200
    assert "77,00" in resposta_lancamento.content.decode()


# ---------------------------------------------------------------------------
# Critério 13 — estados vazio e erro controlado
# ---------------------------------------------------------------------------


def test_diario_vazio_mostra_mensagem_nao_tabela_vazia(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    url = reverse("contabilidade_web:diario", args=[cenario["empresa_a"].id]) + (
        f"?inicio={hoje.isoformat()}&fim={hoje.isoformat()}"
    )
    resposta = client.get(url)
    conteudo = resposta.content.decode()
    assert "Nenhum lançamento no período" in conteudo
    assert "<table" not in conteudo


def test_balancete_sem_contas_mostra_mensagem(client, cenario):
    escritorio = Escritorio.objects.create(nome="Escritório vazio", cnpj="99999999000199")
    empresa_vazia = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa sem plano", cnpj="99988877000166"
    )
    _autenticar(client, escritorio)
    hoje = timezone.localdate()
    url = reverse("contabilidade_web:balancete", args=[empresa_vazia.id]) + (
        f"?inicio={hoje.isoformat()}&fim={hoje.isoformat()}"
    )
    resposta = client.get(url)
    assert "ainda não tem nenhuma conta cadastrada" in resposta.content.decode()


def test_conferencia_sem_inconsistencia_diz_isso_explicitamente(client, cenario):
    # Empresa PRÓPRIA para este teste, sem a conta "Circulante" do cenário
    # padrão: aquela conta é DELIBERADAMENTE "aceita lançamento E tem
    # filhas" (para os testes de reconciliação do critério 6), o que é a
    # TERCEIRA categoria da conferência (DE-022) — correta, mas não é
    # "tudo certo". Este teste quer o caso realmente limpo, nas quatro
    # categorias ao mesmo tempo.
    escritorio = cenario["escritorio_a"]
    empresa_limpa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Limpa Ltda", cnpj="55566677000144"
    )
    Conta.objects.create(
        empresa=empresa_limpa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    _autenticar(client, escritorio)
    resposta = client.get(reverse("contabilidade_web:conferencia", args=[empresa_limpa.id]))
    assert "Nenhuma inconsistência encontrada" in resposta.content.decode()


def test_hierarquia_inconsistente_da_resposta_controlada_nao_500(client, cenario):
    """Ciclo na hierarquia (só alcançável por fora do caminho validado, ex.:
    `.update()` direto no ORM — `Conta.clean()` já impede pelo formulário)
    tem que virar uma resposta controlada (409), nunca um 500 mudo, tanto
    no Razão quanto no Balancete.
    """
    empresa = cenario["empresa_a"]
    # Ciclo direto: caixa vira "pai" de circulante, que já é ANCESTRAL dela
    # — contorna Conta.clean() de propósito, via .update() (mesmo recurso
    # que o docstring de HierarquiaInconsistente descreve).
    Conta.objects.filter(pk=cenario["circulante"].pk).update(conta_pai=cenario["caixa"].pk)

    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    periodo = f"?inicio={hoje.isoformat()}&fim={hoje.isoformat()}"

    resposta_balancete = client.get(
        reverse("contabilidade_web:balancete", args=[empresa.id]) + periodo
    )
    assert resposta_balancete.status_code == 409

    resposta_razao = client.get(
        reverse("contabilidade_web:razao", args=[empresa.id, cenario["caixa"].id]) + periodo
    )
    assert resposta_razao.status_code == 409


# ---------------------------------------------------------------------------
# Critérios 14 e 15 — acessibilidade e uso sem JavaScript
# ---------------------------------------------------------------------------


def test_formulario_de_lancamento_tem_rotulos_associados(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse("contabilidade_web:lancamento_novo", args=[cenario["empresa_a"].id])
    )
    conteudo = resposta.content.decode()
    assert 'for="id_data"' in conteudo and 'id="id_data"' in conteudo
    assert 'for="id_historico"' in conteudo and 'id="id_historico"' in conteudo
    assert 'for="id_conta_1"' in conteudo and 'id="id_conta_1"' in conteudo
    assert 'for="id_valor_1"' in conteudo and 'id="id_valor_1"' in conteudo


def test_tabelas_tem_cabecalho_associado(client, cenario):
    empresa = cenario["empresa_a"]
    criar_lancamento(
        empresa=empresa,
        data=timezone.localdate(),
        historico="x",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1.00")},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1.00")},
        ],
    )
    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    url = reverse("contabilidade_web:diario", args=[empresa.id]) + (
        f"?inicio={hoje.isoformat()}&fim={hoje.isoformat()}"
    )
    conteudo = client.get(url).content.decode()
    assert '<th scope="col">' in conteudo
    assert "<caption" in conteudo


def test_nenhuma_tela_usa_javascript(client, cenario):
    """Critério 15: a tela é utilizável sem JavaScript — não há `<script`
    em nenhuma das telas da contabilidade.
    """
    empresa = cenario["empresa_a"]
    _autenticar(client, cenario["escritorio_a"])
    hoje = timezone.localdate()
    periodo = f"?inicio={hoje.isoformat()}&fim={hoje.isoformat()}"
    urls = [
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id]),
        reverse("contabilidade_web:conta_nova", args=[empresa.id]),
        reverse("contabilidade_web:lancamento_novo", args=[empresa.id]),
        reverse("contabilidade_web:diario", args=[empresa.id]) + periodo,
        reverse("contabilidade_web:razao", args=[empresa.id, cenario["caixa"].id]) + periodo,
        reverse("contabilidade_web:balancete", args=[empresa.id]) + periodo,
        reverse("contabilidade_web:conferencia", args=[empresa.id]),
    ]
    for url in urls:
        conteudo = client.get(url).content.decode()
        assert "<script" not in conteudo.lower(), url


# ---------------------------------------------------------------------------
# Critério 16 — fluxo completo pelo "navegador" (cliente de teste do Django)
# ---------------------------------------------------------------------------


def test_fluxo_completo_criar_conta_lancar_e_conferir(client, cenario):
    """Critério 16: do zero — criar conta, lançar, conferir no Diário, no
    Razão e no Balancete. Evidência via cliente de teste do Django (sem
    Playwright/Selenium disponíveis neste ambiente — ver o relatório da
    entrega).
    """
    empresa = cenario["empresa_a"]
    _autenticar(client, cenario["escritorio_a"], papel=Papel.GESTOR, username="fluxo-completo")
    hoje = timezone.localdate()

    # 1) Criar conta nova (além das já existentes no cenário).
    resposta = client.post(
        reverse("contabilidade_web:conta_nova", args=[empresa.id]),
        {
            "codigo": "3",
            "nome": "Despesas Administrativas",
            "tipo": TipoConta.DESPESA,
            "natureza": NaturezaConta.DEVEDORA,
            "conta_pai": "",
            "aceita_lancamento": "on",
        },
    )
    assert resposta.status_code == 302
    despesa = Conta.objects.get(empresa=empresa, codigo="3")

    resposta = client.get(reverse("contabilidade_web:plano_de_contas", args=[empresa.id]))
    assert "Despesas Administrativas" in resposta.content.decode()

    # 2) Lançar (débito na conta nova, crédito no Caixa já existente).
    resposta = _post_lancamento(
        client,
        empresa.id,
        chave="fluxo-completo-1",
        historico="Pagamento de despesa administrativa",
        linhas=[
            (despesa.id, "debito", "1.500,25"),
            (cenario["caixa"].id, "credito", "1.500,25"),
        ],
    )
    assert resposta.status_code == 302
    lancamento = LancamentoContabil.objects.get(empresa=empresa, historico__contains="despesa")

    # 3) Conferir no Diário.
    periodo = f"?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    resposta = client.get(reverse("contabilidade_web:diario", args=[empresa.id]) + periodo)
    conteudo = resposta.content.decode()
    assert "1.500,25" in conteudo
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, lancamento.id])
        in conteudo
    )

    # 4) Conferir no Razão (da conta de despesa, que recebeu o débito).
    resposta = client.get(
        reverse("contabilidade_web:razao", args=[empresa.id, despesa.id]) + periodo
    )
    conteudo = resposta.content.decode()
    assert "1.500,25" in conteudo
    assert '<span class="indicador-natureza">D' in conteudo  # despesa devedora, débito

    # 5) Conferir no Balancete.
    resposta = client.get(reverse("contabilidade_web:balancete", args=[empresa.id]) + periodo)
    conteudo = resposta.content.decode()
    assert "1.500,25" in conteudo
    assert "Despesas Administrativas" in conteudo
