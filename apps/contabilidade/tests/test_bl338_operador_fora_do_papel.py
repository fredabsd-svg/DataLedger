"""BL-338 (achado B2 da auditoria DL-026, rodada 5,
docs/auditorias/2026-09-19-dl-026-rodada-5.md): sob impressão, o papel
começava por "USUÁRIO <quem operou a tela>" — ANTES até do timbre do
escritório (BL-282/BL-331) — com o nome do escritório aparecendo DE NOVO
logo depois (a faixa de contexto de tela, "Escritório ativo", e o timbre,
que também traz o nome do escritório). Texto medido pelo auditor, sob
mídia de impressão:

    ['USUÁRIO', 'medicao', 'ESCRITÓRIO ATIVO', '<escritório>', 'EMPRESA',
     '<empresa>', 'PERÍODO', '01/03/2026 a 31/03/2026', '<escritório>',
     'Balancete de verificação', ...]

DECISÃO (Fred, 2026-09-19, RC-97), com fundamento NORMATIVO, não estético:
o documento impresso identifica o ESCRITÓRIO e o PROFISSIONAL responsável,
não o usuário que operou a tela — NBC ITG 2000, item 12: "a escrituração
contábil e a emissão de relatórios [...] são de atribuição e de
responsabilidade EXCLUSIVAS do profissional da contabilidade legalmente
habilitado". Quem operou a tela é trilha de auditoria (`apps/auditoria/`),
não identificação do documento.

⚠️ REGRESSÃO CORRIGIDA (arquiteto-senior, mesmo dia da rodada 8, antes de
integrar): a PRIMEIRA redação desta correção escondia "Usuário" E
"Escritório ativo" incondicionalmente, em TODA tela autenticada — inclusive
`plano_de_contas`, `conferencia`, `lancamento_novo`, `conta_nova` e
`lancamento_detalhe`, que NÃO têm `.timbre-impressao` (só Balancete/Diário/
Razão têm, desde o BL-282). Nessas cinco telas, "Escritório ativo" era a
ÚNICA identificação de EMITENTE que existia no papel — a correção original
a apagava sem repor nada, a MESMA classe do achado A1/BL-331 ("esconder
sem repor é pior que o defeito original", texto do próprio comentário do
BL-282 em `static/css/base.css`). Corrigido tornando a ocultação de
"Escritório ativo" CONDICIONAL: `templates/base.html` define o bloco
`classe_escritorio_ativo_na_impressao` com PADRÃO VAZIO (escritório
VISÍVEL — o lado SEGURO para uma tela nova nascer identificada), e só
`balancete.html`/`diario.html`/`razao.html` (as telas COM timbre)
sobrescrevem esse bloco para ocultá-lo. "Usuário" continua INCONDICIONAL —
não depende de timbre, porque quem operou a tela nunca é identificação do
documento, com ou sem timbre.

O QUE ESTE ARQUIVO VERIFICA, em DUAS camadas:

**Camada 1 — cascata CSS estática** (mesmo motor do BL-329,
`_algum_ancestral_removido_do_papel` e companhia, importados de
test_bl329_marca_fora_do_papel.py — nunca reescritos aqui): usada para os
itens cuja visibilidade NÃO depende de qual tela renderiza — "Usuário"
(sempre oculto, vive inteiramente em `templates/base.html`) e "Empresa"/
"Período" (sempre visíveis, `{% block contexto_extra %}`, combinando
ancestrais de `.cabecalho__contexto` com as locais da tela — mesma técnica
de test_bl331_timbre_do_escritorio_no_papel.py).

**Camada 2 — renderização real** (cliente de teste do Django, URL de
verdade, view de verdade): usada para "Escritório ativo", cuja classe final
no HTML depende da COMPOSIÇÃO de dois arquivos (o bloco em
`templates/base.html` MAIS a sobrescrita, quando existir, da tela) — algo
que um parser de UM arquivo só (Camada 1) não reproduz corretamente, porque
o conteúdo do bloco é substituído DENTRO do valor do atributo `class`
através da herança de templates do Django, não por uma estrutura de nós
que a árvore estática combine. A propriedade central, pedida pelo
arquiteto: **"nenhum documento impresso sai sem identificação do
emitente"** — verificada derivando, PARA CADA rota de contabilidade
conhecida (`NOMES_DE_TELA_DE_CONTABILIDADE`, importado de
test_dl024_atalhos_e_acessibilidade.py — a MESMA fonte que
`test_toda_rota_do_produto_esta_coberta_ou_excluida`, naquele arquivo,
usa para garantir que NENHUMA rota nova do produto fique de fora sem ser
classificada — nunca uma lista de "telas sem timbre" escrita à mão aqui),
se a página TEM timbre (presença estrutural de `.timbre-impressao` no
HTML RENDERIZADO — não uma lista de nomes) e, a partir disso, se
"Escritório ativo" está oculto (tem timbre) ou visível (não tem). Uma
tela nova sem timbre que ganhasse a classe por engano reprovaria; uma tela
nova COM timbre que esquecesse de ocultar também reprovaria.

⚠️ Nunca escreva a palavra "title" (nem outra) entre sinais de menor/maior
nos textos deste módulo ou nos templates que ele lê — ver a docstring de
BL-332 em templates/base.html: o parser tolerante a HTML usado na Camada 1
trata "title"/"textarea" como conteúdo RCDATA de verdade (Python stdlib) e
engole, em silêncio, todo o resto do arquivo sem fechamento correspondente.
A Camada 2 usa o MESMO parser sobre HTML RENDERIZADO — mas ali o `<title>`
real do documento é um par bem formado (abre e fecha na mesma linha), o
que não é perigoso; o perigo é só texto SOLTO entre sinais de menor/maior
dentro de comentário de template, que não existe em HTML renderizado.

O QUE ESTE ARQUIVO NÃO VERIFICA — mesmo limite de
test_bl329_marca_fora_do_papel.py/test_bl331_timbre_do_escritorio_no_papel.
py: se o CONTADOR vê isso de verdade no papel (motor de layout real,
Chromium) é responsabilidade de ferramenta de bancada
(scripts/medir_impressao.py). A Camada 1 simula a cascata CSS em
memória/`tmp_path`, sem banco de dados; a Camada 2 usa banco de dados
sintético (cliente de teste do Django), mas não tem motor de CSS — ela só
prova que a classe CERTA está (ou não está) no HTML que o navegador
recebe, e a Camada 1 já provou, separadamente, que aquela classe É
suficiente para produzir `display: none` sob impressão (mesma regra CSS,
`.contexto-item--somente-tela`, usada pelos dois lados).
"""

import copy
import shutil
from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.test_bl329_marca_fora_do_papel import (
    _BASE_CSS,
    _BASE_HTML,
    _RAIZ,
    _algum_ancestral_removido_do_papel,
    _cadeia_de_ancestrais,
    _escrever_css_mutado,
    _parsear_html,
    _percorrer,
    _tem_timbre_impressao,
)
from apps.contabilidade.tests.universo_de_telas import (
    NOMES_DE_TELA_DE_CONTABILIDADE,
    UNIVERSO_DE_ROTAS_DE_TELA,
    _urls_de_contabilidade,
    url_por_nome_de_rota,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

_RAIZ_TEMPLATES = _RAIZ / "templates"
_BALANCETE_HTML = _RAIZ_TEMPLATES / "contabilidade" / "balancete.html"
_DIARIO_HTML = _RAIZ_TEMPLATES / "contabilidade" / "diario.html"
_RAZAO_HTML = _RAIZ_TEMPLATES / "contabilidade" / "razao.html"
_PLANO_DE_CONTAS_HTML = _RAIZ_TEMPLATES / "contabilidade" / "plano_de_contas.html"

_TELAS_COM_CONTEXTO_EXTRA = {
    "balancete": _BALANCETE_HTML,
    "diario": _DIARIO_HTML,
    "razao": _RAZAO_HTML,
}


def _arvore_de(caminho_ou_texto, *, de_arquivo=True):
    texto = caminho_ou_texto.read_text(encoding="utf-8") if de_arquivo else caminho_ou_texto
    return _parsear_html(texto)


def _no_por_rotulo(raiz, texto_rotulo):
    """Localiza `<span class="contexto-rotulo">` cujo texto PRÓPRIO é
    EXATAMENTE `texto_rotulo` e devolve o PAI dele (o `<span
    class="contexto-item...">` que carrega o valor) — a mesma estrutura
    de `.contexto-item`/`.contexto-rotulo` usada em toda a faixa de
    contexto (base.html e os três `contexto_extra`)."""
    for no in _percorrer(raiz):
        if (
            no.tag == "span"
            and "contexto-rotulo" in no.classes
            and no.texto_proprio.strip() == texto_rotulo
        ):
            assert no.pai is not None, f"controle: rótulo {texto_rotulo!r} sem pai"
            return no.pai
    raise AssertionError(
        f'controle: não achei <span class="contexto-rotulo"> com o texto '
        f"{texto_rotulo!r} — a estrutura que este teste espera mudou"
    )


def _no_do_cabecalho_contexto():
    """Localiza `<div class="cabecalho__contexto">` em `templates/base.html`
    — o contêiner onde `{% block contexto_extra %}` é injetado, e onde o
    item "Usuário" já vive diretamente."""
    for no in _percorrer(_arvore_de(_BASE_HTML)):
        if "cabecalho__contexto" in no.classes:
            return no
    raise AssertionError(
        'controle: não achei <div class="cabecalho__contexto"> em '
        "templates/base.html — a estrutura que este teste espera mudou"
    )


def _cadeia_em_base_html(texto_rotulo):
    """Cadeia raiz→nó para um item que vive inteiramente em
    `templates/base.html`, com visibilidade que NÃO depende de qual tela
    renderiza (hoje: só "Usuário" — "Escritório ativo" passou a depender
    da tela, e por isso tem sua própria verificação, por RENDERIZAÇÃO,
    mais abaixo)."""
    raiz = _arvore_de(_BASE_HTML)
    no = _no_por_rotulo(raiz, texto_rotulo)
    return _cadeia_de_ancestrais(no), no


def _cadeia_no_contexto_extra(caminho_template, texto_rotulo):
    """Cadeia raiz→nó combinando as ancestrais de `.cabecalho__contexto`
    (base.html, onde `{% block contexto_extra %}` é injetado) com as
    ancestrais LOCAIS do item dentro da tela — mesma técnica de
    `_cadeia_do_timbre_do_escritorio` em
    test_bl331_timbre_do_escritorio_no_papel.py."""
    no_contexto = _no_do_cabecalho_contexto()
    ancestrais_do_contexto = _cadeia_de_ancestrais(no_contexto)

    no_item = _no_por_rotulo(_arvore_de(caminho_template), texto_rotulo)
    ancestrais_locais = _cadeia_de_ancestrais(no_item)

    return ancestrais_do_contexto + ancestrais_locais, no_item


# ---------------------------------------------------------------------------
# Camada 1 — cascata CSS estática (itens cuja visibilidade não varia por
# tela: "Usuário", sempre oculto; "Empresa"/"Período", sempre visíveis).
# ---------------------------------------------------------------------------


def test_item_usuario_tem_display_none_efetivo_na_impressao():
    """CONTROLE POSITIVO do achado B2: o nome de quem operou a tela não sai
    mais no papel — em NENHUMA tela, com ou sem timbre (incondicional)."""
    cadeia, no = _cadeia_em_base_html("Usuário")
    escondido, _ = _algum_ancestral_removido_do_papel(cadeia, _BASE_CSS.read_text(encoding="utf-8"))
    assert escondido, (
        f"o item 'Usuário' (cadeia: {[(n.tag, n.classes) for n in cadeia]}) NÃO tem "
        f"display:none efetivo sob impressão — o nome de quem operou a tela ainda "
        f"sai no papel"
    )
    assert no is not None


@pytest.mark.parametrize("tela", sorted(_TELAS_COM_CONTEXTO_EXTRA))
@pytest.mark.parametrize("rotulo", ["Empresa", "Período"])
def test_empresa_e_periodo_continuam_visiveis_sob_impressao(tela, rotulo):
    """CONTROLE NEGATIVO exigido pelo pedido desta etapa: a correção do
    achado B2 não pode apagar a identificação OBRIGATÓRIA do documento
    (RC-93) — Empresa e Período continuam sem `display: none` efetivo sob
    impressão, nas três telas que preenchem `{% block contexto_extra %}`."""
    caminho = _TELAS_COM_CONTEXTO_EXTRA[tela]
    cadeia, no = _cadeia_no_contexto_extra(caminho, rotulo)
    escondido, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, _BASE_CSS.read_text(encoding="utf-8")
    )
    assert not escondido, (
        f"o item {rotulo!r} de {tela} (cadeia: {[(n.tag, n.classes) for n in cadeia]}) TEM "
        f"display:none efetivo sob impressão, resolvido em "
        f"{(no_que_esconde.tag, no_que_esconde.classes) if no_que_esconde else None} — "
        f"identificação OBRIGATÓRIA (RC-93) sumiu do papel"
    )
    assert no is not None


# ---------------------------------------------------------------------------
# Camada 2 — renderização real. "Escritório ativo" depende da COMPOSIÇÃO de
# templates/base.html com a tela; só a renderização real prova a classe
# final. "Quem tem timbre" é derivado do PRÓPRIO HTML renderizado — nunca
# de uma lista escrita à mão — e o conjunto de telas testadas vem de
# NOMES_DE_TELA_DE_CONTABILIDADE (test_dl024_atalhos_e_acessibilidade.py),
# a mesma fonte que aquele arquivo usa para garantir, separadamente
# (test_toda_rota_do_produto_esta_coberta_ou_excluida), que nenhuma rota
# nova do produto fica sem classificação.
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario_bl338(client):
    escritorio = Escritorio.objects.create(nome="Escritório BL-338", cnpj="77788899000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-338 Ltda", cnpj="77788899000202"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl338",
        email="gestora-bl338@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestora-bl338", password="senha-forte-123")
    lancamento = criar_lancamento(
        empresa=empresa,
        data=timezone.localdate(),
        historico="BL-338 — movimento para as telas terem o que mostrar",
        itens=[
            {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=usuario,
        chave_idempotencia="k-bl338",
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "lancamento": lancamento}


def _tem_timbre_e_classe_do_escritorio_ativo(html):
    """Sobre o HTML RENDERIZADO de uma tela: devolve (tem_timbre,
    classes_do_item_escritorio_ativo). "Tem timbre" é ESTRUTURAL — a
    presença de `<div class="timbre-impressao">` no próprio HTML que o
    navegador recebeu, não uma lista de nomes de tela decidida aqui.
    `_tem_timbre_impressao` vem de test_bl329_marca_fora_do_papel.py —
    BL-344/F2: a MESMA derivação que test_bl332_titulo_sem_marca_do_
    fornecedor.py usa para "esta tela é documento?", compartilhada em vez
    de duplicada."""
    raiz = _arvore_de(html, de_arquivo=False)
    tem_timbre = _tem_timbre_impressao(raiz)
    no_escritorio = _no_por_rotulo(raiz, "Escritório ativo")
    return tem_timbre, no_escritorio.classes


@pytest.mark.parametrize("nome_tela", sorted(NOMES_DE_TELA_DE_CONTABILIDADE))
def test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre(client, cenario_bl338, nome_tela):
    """A propriedade central pedida pelo arquiteto: "nenhum documento
    impresso sai sem identificação do emitente". Onde há timbre
    (`.timbre-impressao` no HTML renderizado), "Escritório ativo" fica
    OCULTO sob impressão — o timbre já identifica, e mantê-lo também
    visível na faixa de tela é a DUPLICIDADE original do achado B2. Onde
    NÃO há timbre, "Escritório ativo" tem que continuar VISÍVEL — é a
    ÚNICA identificação do emitente que a tela tem no papel, e escondê-la
    sem repor nada é a regressão que esta correção existe para não
    repetir."""
    url = _urls_de_contabilidade(cenario_bl338)[nome_tela]
    resposta = client.get(url)
    assert resposta.status_code == 200, f"{nome_tela}: {resposta.status_code}"
    html = resposta.content.decode()

    tem_timbre, classes_escritorio = _tem_timbre_e_classe_do_escritorio_ativo(html)
    oculto = "contexto-item--somente-tela" in classes_escritorio

    if tem_timbre:
        assert oculto, (
            f"{nome_tela} TEM timbre de impressão, mas 'Escritório ativo' continua "
            f"visível na faixa de tela — o escritório sairia DUAS vezes no papel "
            f"(classes: {classes_escritorio!r})"
        )
    else:
        assert not oculto, (
            f"{nome_tela} NÃO TEM timbre de impressão, e 'Escritório ativo' está "
            f"oculto na impressão — o documento sairia SEM identificação nenhuma do "
            f"emitente (classes: {classes_escritorio!r})"
        )


# ---------------------------------------------------------------------------
# BL-345 (F3 da auditoria DL-026, rodada 6,
# docs/auditorias/2026-09-19-dl-026-rodada-6.md): a guarda ACIMA só corre
# sobre as OITO telas de `NOMES_DE_TELA_DE_CONTABILIDADE`. O
# `arquiteto-senior` já tinha declarado essa limitação (BL-342) e a
# empurrado para a DL-027; o auditor mediu que a correção NÃO dependia
# disso — as seis telas de fora (login, empresas:lista, empresas:criar,
# tenancy:painel, tenancy:aceitar-convite, tenancy:bootstrap-primeiro-acesso)
# já estão em `UNIVERSO_DE_ROTAS_DE_TELA`, importado de
# apps/contabilidade/tests/universo_de_telas.py.
#
# BL-352 (rodada 10 da auditoria DL-026): antes desta correção, este
# conjunto era RECONSTRUÍDO aqui a partir de duas listas vivendo em
# test_dl024_atalhos_e_acessibilidade.py; a guarda irmã de título
# (test_bl332_titulo_sem_marca_do_fornecedor.py), escrita no MESMO commit,
# importava só UMA das duas — a fonte comum (`universo_de_telas.py`) fecha
# essa divergência na raiz, em vez de deixar cada guarda reconstruir a
# mesma soma à mão.
#
# Reprodução do auditor: `templates/empresas/lista.html` ganha a MESMA
# sobrescrita condicional que `balancete.html` tem
# (`classe_escritorio_ativo_na_impressao`), e a tela passa a imprimir SEM
# identificação nenhuma de emitente — com `1775 passed`.
#
# A guarda abaixo estende a MESMA propriedade central para a UNIÃO dos
# dois conjuntos. Duas das seis telas de fora NUNCA renderizam com
# `request.escritorio` presente — não é limitação da guarda, é a FORMA da
# rota, e por isso são exclusão NOMEADA, com o motivo escrito, em vez de
# silenciosamente ignoradas:
#
# - "login": tela PRÉ-AUTENTICAÇÃO — `request.user.is_authenticated` é
#   `False`, então nem o bloco `{% if request.escritorio %}` de
#   `templates/base.html` chega a avaliar (o middleware
#   `EscritorioAtivoMiddleware` só resolve `request.escritorio` para
#   usuário autenticado) — o item "Escritório ativo" nem EXISTE no HTML,
#   então não há nada para a propriedade "oculto se, e só se, tem timbre"
#   avaliar.
# - "tenancy:bootstrap-primeiro-acesso": a VIEW (apps/tenancy/views.py,
#   `bootstrap_primeiro_acesso`) REDIRECIONA (302) para `tenancy:painel`
#   sempre que o usuário JÁ tem vínculo ativo — só devolve 200 para quem
#   ainda NÃO tem escritório nenhum. Logo, um 200 desta rota NUNCA tem
#   `request.escritorio` presente — pela MESMA razão do login, não por
#   acaso.
# ---------------------------------------------------------------------------

_TELAS_SEM_REQUEST_ESCRITORIO = {
    "login": (
        "tela pré-autenticação (request.user.is_authenticated é False) — "
        "EscritorioAtivoMiddleware só resolve request.escritorio para usuário "
        "autenticado, e o bloco 'Escritório ativo' de templates/base.html nem "
        "existe no HTML sem ele"
    ),
    "tenancy:bootstrap-primeiro-acesso": (
        "só renderiza 200 para usuário SEM vínculo nenhum — apps/tenancy/"
        "views.py (bootstrap_primeiro_acesso) redireciona (302) para "
        "tenancy:painel quando já existe vínculo ativo, então um 200 desta "
        "rota nunca tem request.escritorio presente"
    ),
}

# BL-352 (rodada 10): a UNIÃO em si (nomes de ROTA COMPLETOS, namespace:nome)
# vem PRONTA de `universo_de_telas.UNIVERSO_DE_ROTAS_DE_TELA` — este arquivo
# não a reconstrói mais somando NOMES_DE_TELA_DE_CONTABILIDADE.values() com
# NOMES_DE_TELA_FORA_DA_CONTABILIDADE (essa soma, escrita à mão aqui E
# também em test_bl332, foi o que divergiu). O que CONTINUA sendo desta
# guarda, e só dela — o RECORTE, com o motivo escrito — é a subtração de
# `_TELAS_SEM_REQUEST_ESCRITORIO` logo acima: a propriedade "Escritório
# ativo oculto se, e só se, tem timbre" não tem o que avaliar numa rota sem
# `request.escritorio`, e essa razão é ESPECÍFICA desta guarda, não do
# universo. Uma guarda de outra propriedade (ex. a de TÍTULO, em
# test_bl332_titulo_sem_marca_do_fornecedor.py) NÃO herda esta subtração —
# ela declara seu próprio recorte, com sua própria justificativa, sobre o
# MESMO `UNIVERSO_DE_ROTAS_DE_TELA`.
_NOMES_DE_ROTA_COM_ESCRITORIO = UNIVERSO_DE_ROTAS_DE_TELA - set(_TELAS_SEM_REQUEST_ESCRITORIO)

# A resolução de URL para qualquer rota do universo (tanto as de
# `NOMES_DE_TELA_DE_CONTABILIDADE` quanto as de fora) é mecânica comum a
# qualquer guarda — promovida para `universo_de_telas.url_por_nome_de_rota`
# (BL-352) em vez de reimplementada aqui. `_url_por_nome_de_rota` continua
# existindo como nome LOCAL só para não precisar renomear cada chamada
# abaixo — é o MESMO objeto importado, não uma cópia.
_url_por_nome_de_rota = url_por_nome_de_rota


@pytest.mark.parametrize("nome_de_rota", sorted(_NOMES_DE_ROTA_COM_ESCRITORIO))
def test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre_em_toda_tela_do_produto(
    client, cenario_bl338, nome_de_rota
):
    """BL-345/F3: a MESMA propriedade central de
    `test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre`, agora
    sobre a UNIÃO de `NOMES_DE_TELA_DE_CONTABILIDADE` e
    `NOMES_DE_TELA_FORA_DA_CONTABILIDADE` — não só as oito telas de
    contabilidade. O auditor mediu que a limitação declarada no BL-342
    (adiada para a DL-027) não dependia dela: a fonte de derivação já
    estava importada neste mesmo arquivo."""
    url = _url_por_nome_de_rota(nome_de_rota, cenario_bl338)
    resposta = client.get(url)
    assert resposta.status_code == 200, f"{nome_de_rota}: {resposta.status_code}"
    html = resposta.content.decode()

    tem_timbre, classes_escritorio = _tem_timbre_e_classe_do_escritorio_ativo(html)
    oculto = "contexto-item--somente-tela" in classes_escritorio

    if tem_timbre:
        assert oculto, (
            f"{nome_de_rota} TEM timbre de impressão, mas 'Escritório ativo' continua "
            f"visível na faixa de tela — o escritório sairia DUAS vezes no papel "
            f"(classes: {classes_escritorio!r})"
        )
    else:
        assert not oculto, (
            f"{nome_de_rota} NÃO TEM timbre de impressão, e 'Escritório ativo' está "
            f"oculto na impressão — o documento sairia SEM identificação nenhuma do "
            f"emitente (classes: {classes_escritorio!r})"
        )


@pytest.mark.parametrize(
    "nome_de_rota,caminho_relativo",
    [
        ("empresas:lista", "empresas/lista.html"),
        ("tenancy:painel", "tenancy/painel.html"),
    ],
)
def test_sabotagem_ocultar_escritorio_ativo_fora_da_contabilidade_mata_a_guarda(
    client, cenario_bl338, tmp_path, nome_de_rota, caminho_relativo
):
    """BL-345/F3: reprodução EXATA da sabotagem do achado — uma tela de
    FORA da contabilidade (aqui, `empresas/lista.html` e
    `tenancy/painel.html`, as duas que o auditor mediu) ganha a MESMA
    sobrescrita condicional que `balancete.html` tem
    (`classe_escritorio_ativo_na_impressao`), sem NUNCA ganhar timbre —
    reproduzindo a regressão do BL-342 num diretório onde a guarda de
    Camada 2 antiga (parametrizada só sobre `NOMES_DE_TELA_DE_
    CONTABILIDADE`) não olhava. A guarda estendida acima PRECISA morrer:
    a tela passaria a imprimir SEM identificação nenhuma de emitente."""
    caminho_real = _RAIZ_TEMPLATES / caminho_relativo
    conteudo_antes = caminho_real.read_text(encoding="utf-8")

    marcador = "{% block titulo %}"
    assert caminho_real.read_text(encoding="utf-8").count(marcador) >= 1, (
        f"controle: marcador de título não encontrado em {caminho_relativo}"
    )
    sobrescrita_regressiva = (
        "{% block classe_escritorio_ativo_na_impressao %} "
        "contexto-item--somente-tela{% endblock %}\n" + marcador
    )
    conteudo_mutado = conteudo_antes.replace(marcador, sobrescrita_regressiva, 1)
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    (raiz_copia / caminho_relativo).write_text(conteudo_mutado, encoding="utf-8")

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1
    motor[0]["DIRS"] = [raiz_copia]

    url = _url_por_nome_de_rota(nome_de_rota, cenario_bl338)
    with override_settings(TEMPLATES=motor):
        resposta = client.get(url)
        assert resposta.status_code == 200
        html = resposta.content.decode()
        tem_timbre, classes_escritorio = _tem_timbre_e_classe_do_escritorio_ativo(html)
        # BL-352 (rodada 10): mensagem CORRIGIDA — a redação anterior dizia
        # "a mutação não mexeu no timbre", o que seria FALSO para uma
        # sabotagem que também adicionasse '.timbre-impressao' (a versão
        # COERENTE que o auditor mediu contra a guarda de TÍTULO, em
        # test_bl332). ESTA sabotagem, em particular, só acrescenta a
        # sobrescrita de `classe_escritorio_ativo_na_impressao` — nunca toca
        # em `.timbre-impressao` — então o que o assert abaixo verifica é
        # que essa premissa (tela sem timbre, só com a sobrescrita
        # regressiva) continua valendo para `nome_de_rota` depois da
        # mutação; se falhar, é a COMPOSIÇÃO do template que mudou (ganhou
        # timbre por outro motivo), não a mutação em si.
        assert tem_timbre is False, (
            f"controle: {nome_de_rota} passou a ter '.timbre-impressao' — esta sabotagem "
            f"só acrescenta a sobrescrita de classe_escritorio_ativo_na_impressao e não "
            f"deveria, sozinha, introduzir timbre nenhum; a premissa deste teste (tela SEM "
            f"timbre) não vale mais para {nome_de_rota}"
        )
        oculto = "contexto-item--somente-tela" in classes_escritorio
        assert oculto, (
            "a sabotagem deveria ter reproduzido a regressão (tela SEM timbre "
            "imprimindo SEM identificação de emitente), e 'Escritório ativo' continuou "
            "visível — a mutação não teve efeito"
        )
        # `oculto is True` aqui é exatamente o valor que faz
        # test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre_em_toda_tela_
        # do_produto REPROVAR contra este mesmo HTML — a prova de que a guarda morre.

    # Fora do override: a tela volta ao normal, e o arquivo real nunca foi escrito.
    resposta_normal = client.get(url)
    _, classes_normais = _tem_timbre_e_classe_do_escritorio_ativo(resposta_normal.content.decode())
    assert "contexto-item--somente-tela" not in classes_normais
    assert caminho_real.read_text(encoding="utf-8") == conteudo_antes


# Controle positivo EXPLÍCITO (pedido do arquiteto: pelo menos duas das
# cinco telas sem timbre, provando que o escritório sai no papel delas) —
# além da cobertura genérica acima, que já inclui as cinco.
#
# ⚠️ BL-349 (F7 da auditoria DL-026, rodada 6,
# docs/auditorias/2026-09-19-dl-026-rodada-6.md): a lista
# `["plano_de_contas", "conferencia"]`, abaixo, é uma escolha de DUAS
# telas para exercitar de propósito — não a fonte de verdade de "quem tem
# timbre" (essa fonte é o HTML, em `_tem_timbre_e_classe_do_escritorio_
# ativo`/`test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre`,
# acima). O auditor mediu: transformar `conferencia` numa tela de
# documento, de forma COERENTE (com timbre e ocultação certa), morre
# `assert not tem_timbre` aqui — e é a coisa CERTA que aconteceu com o
# produto, não um defeito. **A falha deste teste específico significa "a
# composição do produto mudou — `nome_tela` deixou de ser uma tela sem
# timbre; revise a lista acima" — NUNCA "há um defeito de impressão".**
# Quem receber essa falha deve trocar a tela na lista (ou remover, se
# sobrar só uma das cinco), não "corrigir" a implementação. A guarda que
# DETECTA defeito de verdade é a genérica, acima — esta aqui é controle
# de ESTRUTURA da própria suíte.
@pytest.mark.parametrize("nome_tela", ["plano_de_contas", "conferencia"])
def test_telas_sem_timbre_mostram_escritorio_ativo_na_impressao(client, cenario_bl338, nome_tela):
    url = _urls_de_contabilidade(cenario_bl338)[nome_tela]
    resposta = client.get(url)
    assert resposta.status_code == 200
    html = resposta.content.decode()

    tem_timbre, classes_escritorio = _tem_timbre_e_classe_do_escritorio_ativo(html)
    assert not tem_timbre, (
        f"CONTROLE DE ESTRUTURA (não é defeito de impressão): {nome_tela!r} passou a "
        f"ter .timbre-impressao — a composição do produto mudou, e esta tela não serve "
        f"mais como exemplo de 'tela sem timbre' para este controle explícito. Troque "
        f"{nome_tela!r} por outra das cinco telas sem timbre na parametrização acima "
        f"(a guarda que detecta defeito de verdade é "
        f"test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre, que já cobre "
        f"todas as telas e não depende desta lista)"
    )
    assert "contexto-item--somente-tela" not in classes_escritorio, (
        f"{nome_tela}: 'Escritório ativo' está oculto na impressão sem nenhum timbre "
        f"para substituí-lo — documento sem identificação de emitente"
    )
    # Controle de conteúdo: o NOME do escritório de fato está no HTML (não
    # é só a classe que está certa; o valor precisa existir para a classe
    # importar).
    assert cenario_bl338["escritorio"].nome in html


def test_sabotagem_reproduzir_a_regressao_original_mata_a_guarda_da_camada_2(
    client, cenario_bl338, tmp_path
):
    """CRITÉRIO 1 do arquiteto, reproduzido literalmente: sobrescreve, numa
    CÓPIA de `templates/contabilidade/plano_de_contas.html` (BL-311: nunca
    no arquivo real), o bloco `classe_escritorio_ativo_na_impressao` com
    `contexto-item--somente-tela` — exatamente a sobrescrita que
    `balancete.html` tem, e que a PRIMEIRA redação desta correção aplicava,
    por engano, a TODA tela (a regressão que o arquiteto apontou antes de
    integrar). Plano de contas NÃO tem `.timbre-impressao` — reproduzir
    essa sobrescrita nele tem que fazer a guarda de
    `test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre`/
    `test_telas_sem_timbre_mostram_escritorio_ativo_na_impressao` MORRER
    (a tela passa a imprimir sem identificação nenhuma de emitente)."""
    conteudo_antes = _PLANO_DE_CONTAS_HTML.read_text(encoding="utf-8")
    marcador = "{% block titulo %}Plano de contas — {{ empresa.razao_social }}{% endblock %}"
    assert marcador in conteudo_antes, "controle: marcador do título não encontrado"

    sobrescrita_regressiva = (
        marcador
        + "\n{% block classe_escritorio_ativo_na_impressao %} "
        + "contexto-item--somente-tela{% endblock %}"
    )
    conteudo_mutado = conteudo_antes.replace(marcador, sobrescrita_regressiva, 1)
    assert conteudo_mutado != conteudo_antes, "controle: a mutação precisa mudar o conteúdo"

    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)
    (raiz_copia / "contabilidade" / "plano_de_contas.html").write_text(
        conteudo_mutado, encoding="utf-8"
    )

    motor = copy.deepcopy(settings.TEMPLATES)
    assert len(motor) == 1
    motor[0]["DIRS"] = [raiz_copia]

    url = _urls_de_contabilidade(cenario_bl338)["plano_de_contas"]
    with override_settings(TEMPLATES=motor):
        resposta = client.get(url)
        assert resposta.status_code == 200
        html = resposta.content.decode()
        tem_timbre, classes_escritorio = _tem_timbre_e_classe_do_escritorio_ativo(html)
        # BL-352 (rodada 10): mensagem CORRIGIDA — ver o comentário gêmeo em
        # test_sabotagem_ocultar_escritorio_ativo_fora_da_contabilidade_
        # mata_a_guarda, acima. Esta sabotagem só acrescenta a sobrescrita
        # de classe_escritorio_ativo_na_impressao a Plano de contas; o
        # assert abaixo verifica que ISSO, sozinho, não introduziu timbre —
        # nunca "a mutação não mexeu no timbre" como afirmação genérica
        # sobre qualquer mutação.
        assert tem_timbre is False, (
            "controle: 'plano_de_contas' passou a ter '.timbre-impressao' — esta "
            "sabotagem só acrescenta a sobrescrita de classe_escritorio_ativo_na_"
            "impressao e não deveria, sozinha, introduzir timbre nenhum; a premissa "
            "deste teste (Plano de contas SEM timbre) não vale mais"
        )
        oculto = "contexto-item--somente-tela" in classes_escritorio
        assert oculto, (
            "a sabotagem deveria ter reproduzido a regressão (Plano de contas SEM timbre "
            "imprimindo SEM identificação de emitente), e 'Escritório ativo' continuou "
            "visível — a mutação não teve efeito"
        )
        # `oculto is True` aqui é exatamente o valor que faz
        # `test_escritorio_ativo_visivel_exatamente_onde_nao_ha_timbre`/
        # `test_telas_sem_timbre_mostram_escritorio_ativo_na_impressao` REPROVAR
        # contra este mesmo HTML — a prova de que a guarda morre.

    # Fora do override: a tela volta ao normal, e o arquivo real nunca foi escrito.
    resposta_normal = client.get(url)
    _, classes_normais = _tem_timbre_e_classe_do_escritorio_ativo(resposta_normal.content.decode())
    assert "contexto-item--somente-tela" not in classes_normais
    assert _PLANO_DE_CONTAS_HTML.read_text(encoding="utf-8") == conteudo_antes


# ---------------------------------------------------------------------------
# Prova por mutação (BL-311: sabotagem só em CÓPIA dentro de `tmp_path`,
# nunca no arquivo real). Controle POSITIVO (sabotagem 1: reverter a
# correção faz o operador voltar) e NEGATIVO (sabotagem 2: uma correção
# larga demais que apaga Empresa/Período junto tem que ser pega pelo teste
# de controle negativo acima). As duas seguem válidas depois da correção
# de regressão: a regra CSS (`.contexto-item--somente-tela`) não mudou,
# só QUEM recebe a classe no HTML.
# ---------------------------------------------------------------------------


def test_sabotagem_remover_a_regra_que_esconde_o_operador_mata_a_guarda(tmp_path):
    """Sabotagem 1 — CONTROLE POSITIVO: remove, de uma CÓPIA de
    `static/css/base.css`, a regra `.contexto-item--somente-tela { display:
    none; }` inteira — reproduz o estado ANTES desta correção, em que
    "Usuário" continuava saindo no papel. A guarda do item "Usuário"
    PRECISA morrer (deixar de reportar `escondido`)."""
    cadeia, _ = _cadeia_em_base_html("Usuário")
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    escondido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert escondido_antes, "controle: o CSS real precisa passar ANTES da sabotagem"

    alvo = "    .contexto-item--somente-tela {\n        display: none;\n    }"
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, "")
    escondido_depois, _ = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois is False, (
        "remover a regra que esconde 'Usuário' na impressão deveria ter feito a guarda "
        "MORRER, e ela continuou aprovando"
    )


def test_sabotagem_esconder_todo_contexto_item_mata_a_guarda_de_empresa_e_periodo(tmp_path):
    """Sabotagem 2 — CONTROLE NEGATIVO: troca o seletor
    `.contexto-item--somente-tela` por `.contexto-item` (uma correção
    LARGA DEMAIS, plausível se alguém "simplificar" a regra sem notar que
    ela passa a casar com TODOS os itens da faixa) — Empresa e Período
    passam a ter `display: none` efetivo também, e a guarda de controle
    negativo (`test_empresa_e_periodo_continuam_visiveis_sob_impressao`)
    PRECISA morrer (reportar `escondido`, o que ela recusa por padrão)."""
    caminho_balancete = _TELAS_COM_CONTEXTO_EXTRA["balancete"]
    cadeia, _ = _cadeia_no_contexto_extra(caminho_balancete, "Empresa")
    css_original = _BASE_CSS.read_text(encoding="utf-8")

    escondido_antes, _ = _algum_ancestral_removido_do_papel(cadeia, css_original)
    assert escondido_antes is False, "controle: Empresa precisa estar VISÍVEL antes da sabotagem"

    alvo = "    .contexto-item--somente-tela {\n        display: none;\n    }"
    substituto = "    .contexto-item {\n        display: none;\n    }"
    caminho_mutado = _escrever_css_mutado(tmp_path, css_original, alvo, substituto)
    escondido_depois, no_que_esconde = _algum_ancestral_removido_do_papel(
        cadeia, caminho_mutado.read_text(encoding="utf-8")
    )
    assert escondido_depois, (
        "a sabotagem que amplia o seletor para TODO '.contexto-item' deveria ter feito "
        "a guarda de Empresa/Período MORRER (Empresa escondida junto com Usuário), e ela "
        "continuou aprovando"
    )
    assert no_que_esconde is not None
