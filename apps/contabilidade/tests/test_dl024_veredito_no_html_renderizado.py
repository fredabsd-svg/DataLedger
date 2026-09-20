"""Achado do `arquiteto-senior`, revisão integrada `65af1dc`, rodada 4 da
DL-026 (docs/auditorias/2026-09-18-dl-024-rodada-2.md, achado A1).

Os 13 testes de `apps/contabilidade/tests/test_bl289_veredito_fechamento.py`
(do `desenvolvedor-pleno`) afirmam sobre a CHAVE do contexto de
renderização — `veredito_fechamento`/`veredito_balancete`. Correto para a
fronteira dele: ele testa a DECISÃO, que é o que a view entrega.

Só que o achado A1 nunca foi sobre a decisão — era sobre a FRASE que o
contador lê antes de gravar. Entre a chave certa e a frase certa existe um
template, e nenhum teste, em nenhum arquivo, conferia o TEXTO que a tela
de fato mostra. Prova: o arquiteto trocou, numa CÓPIA fora do repositório,
`{% if veredito_fechamento == "fecha" %}` de volta para
`{% if total_debito_ptbr == total_credito_ptbr %}` — o defeito original do
A1. Com o formulário em branco, a CHAVE do contexto continuava certa
(`nao_conferido` — a view nem foi tocada), mas a TELA voltou a mostrar
"Fecha" (`None == None` é verdadeiro em template Django). A suíte inteira,
inclusive os 13 testes do BL-289, continuou verde.

Este arquivo fecha essa lacuna. Três coisas, para cada uma das duas telas
(lançamento e balancete):

1. Para cada um dos três estados, o texto do estado ESPERADO está
   presente e os outros DOIS estão ausentes — nunca só `"X" not in html`,
   que passaria trivialmente se o veredito sumisse do HTML inteiro.
2. Uma mutação que reproduz EXATAMENTE o defeito do achado A1 (comparar
   `total_..._ptbr` em vez de ramificar pela chave) tem que produzir o
   texto ERRADO — a prova de que os testes do item 1, rodados contra um
   template mutado, morreriam.
3. A PÁGINA REAL (seção "3" abaixo) — cliente de teste do Django, URL de
   verdade, view de verdade, template de verdade. Achado do
   `arquiteto-senior`, na revisão integrada `65af1dc` desta mesma sessão:
   os itens 1 e 2 extraem o FRAGMENTO do `{% if %}` e o renderizam
   ISOLADO — provam que o fragmento, SE EXECUTADO, produz o texto certo,
   mas não provam que ele É executado. Uma sabotagem que envolve o bloco
   inteiro (intacto por dentro) numa condição sempre falsa
   (`{% if nunca_definido_no_contexto %}...{% endif %}`) não muda o
   fragmento — a extração dos itens 1 e 2 continua achando o `{% if
   veredito_... == "fecha" %}` de sempre — e o veredito INTEIRO some da
   página renderizada de verdade. É a QUARTA vez, nesta mesma etapa, que
   o teste fica um passo antes de onde o defeito aparece (a faixa nasceu
   sem teste — A2; o balancete acertava por ausência de chave, não por
   decisão — BL-302; a decisão foi testada e a entrega não — achado
   anterior desta rodada). A seção 3 testa a ENTREGA: a resposta HTTP que
   o contador de fato recebe.

**O que estes três itens NÃO são: três camadas.** Correção de redação do
`arquiteto-senior` (BL-314, achado M5 da auditoria DL-026 rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md), sobre texto que eu mesmo
mandei escrever. A versão anterior descrevia o veredito como protegido
"em três camadas", e quem lesse isso daqui a seis meses concluiria que
existem três espécies de garantia. Não existem: os três itens leem
**texto em HTML**, e nenhum deles pergunta se o contador **vê** alguma
coisa. O auditor mediu a diferença acrescentando uma única regra ao
`static/css/base.css` —

    .veredito-fechamento, .faixa-fechamento { display: none }

— e a suíte respondeu **1451 passed**. O veredito tinha sumido da tela e
nada acusou.

A redação honesta é **três pontos da mesma cadeia**, cada um mais perto
da entrega que o anterior: o fragmento renderizado isolado (1 e 2), e a
resposta HTTP inteira (3). O item 3 amplia o **alcance** — mata a
sabotagem do bloco inalcançável, que os itens 1 e 2 não pegavam —, não a
**natureza** da verificação. Contar como camada o que é do mesmo tipo
infla a garantia declarada, e garantia inflada é pior que garantia
ausente: ninguém procura o que acredita já ter.

**Onde a visibilidade É medida, e por que não aqui.** A §4.8 do relatório
da rodada 3 declara que navegador não roda na integração contínua deste
projeto — então "o contador vê" não é uma pergunta que a CI possa
responder. Quem a responde é o juiz do gauntlet,
`scripts/juiz.py`, que abre a página em Chromium de
verdade e consulta `MOMENTO_DA_VERDADE_SELETORES` com
`Element.checkVisibility({checkOpacity, checkVisibilityCSS})` mais a área
ocupada — delegando ao motor de layout em vez de enumerar as maneiras
conhecidas de esconder um elemento (BL-314, parte do
`especialista-frontend`). Isso é medição **fora da CI**, executada sob
demanda, e está declarado assim de propósito: uma medição que roda fora
da CI é uma medição que pode deixar de ser feita. Enquanto for assim, a
garantia deste arquivo é "a decisão do servidor chega corretamente ao
HTML entregue" — não "o contador enxerga o veredito".

Método de mutação dos itens 1 e 2: extrai o FRAGMENTO do `{% if %}` do
ARQUIVO REAL a cada chamada (nunca retypado à mão — a mesma lição do
BL-296: cópia que descreve o original diverge assim que o original muda)
e o RENDERIZA como STRING em memória, com
`django.template.engines["django"].from_string` mais um contexto
sintético — nunca escrevendo no arquivo do repositório. É o MESMO método
que `test_dl017_rodada2_frontend.py` já usa para mutar
`static/css/base.css` ("aplica o mutante numa CÓPIA do CSS real, nunca o
arquivo do repositório") — aqui aplicado a um fragmento de template em vez
de uma folha de estilo.

Método de mutação do item 3 (a condição sempre falsa) — CORRIGIDO pelo
BL-311 (achado M2 da auditoria DL-026, rodada 3,
docs/auditorias/2026-09-18-dl-024-rodada-3.md): esta sabotagem é sobre o
que a URL de verdade SERVE — não há como reproduzi-la sem que o Django
resolva o template pelo NOME, através dos `loaders` configurados
(`config/settings.py`, `APP_DIRS: True`). A versão anterior (até a rodada
4) fazia isso escrevendo o conteúdo MUTADO no ARQUIVO REAL do
repositório, dentro de um `try`/`finally` que restaurava o conteúdo
ORIGINAL. O auditor mediu, por instrumentação a cada 0,5 ms e por seis
rodadas de execução concorrente na MESMA árvore, que essa técnica
CORROMPE o repositório de forma ACUMULATIVA sob concorrência: a segunda
execução lê como "original" o conteúdo já mutado pela primeira e
restaura para ELE — rodar de novo não conserta —, e ao menos uma das
execuções concorrentes termina com código de saída 0. O projeto tem
BL-273 justamente porque agentes já escreveram na mesma árvore ao mesmo
tempo.

A técnica atual prova a MESMA coisa — URL real, view real, loader real —
sem nunca escrever no repositório: `_arvore_de_templates_com_mutacao`
copia o diretório `templates/` INTEIRO (com `shutil.copytree`) para
dentro do `tmp_path` que o pytest cria, ISOLADO e EXCLUSIVO por
invocação de teste (inclusive entre execuções concorrentes do MESMO
arquivo, que é exatamente o cenário que corrompia a árvore antes), e
mutação vai só nessa CÓPIA. A requisição roda sob
`django.test.override_settings(TEMPLATES=[...])`, apontando `DIRS` para
a cópia mutada — o Django resolve a URL, a view e o `{% extends
"base.html" %}` normalmente, através do MESMO mecanismo de loader que o
`runserver` usa, só que lendo de um diretório temporário em vez do
repositório. `override_settings` troca a configuração só durante o
bloco `with` e a restaura ao sair (e dispara `setting_changed`, que o
próprio Django usa para limpar o cache de `django.template.engines` —
ver `django.test.signals.reset_template_engines` —, então a troca de
`DIRS` é enxergada pela PRÓXIMA renderização sem precisar de
`reset_loaders()` manual). Como nada é escrito fora de `tmp_path`, não
há restauração a fazer nem risco de o repositório ficar mutado — a
prova de concorrência (na seção de testes) roda o MESMO arquivo de teste
duas vezes em paralelo, repetidas vezes, com `git status` limpo ao fim de
todas.
"""

import copy
import re
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.template import engines as _template_engines
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

# Fixture e auxiliares da seção 3 (página real) — dados 100% sintéticos,
# no MESMO padrão que todo outro arquivo desta suíte usa para o próprio
# cenário (test_dl017_telas.py::cenario, test_bl289_veredito_fechamento.py
# ::cen, test_bl290_veredito_balancete.py::cen): cada arquivo cria o seu.
# Tentei reaproveitar `cen`/`_login`/`_url_tela` dos dois arquivos do
# `desenvolvedor-pleno` por IMPORT (proibido editá-los, mas não importar
# deles) — funciona para o pytest (que resolve fixture pelo nome no
# namespace do módulo, não pelo `__name__` da função original), mas o
# `ruff` não distingue "nome de parâmetro que o pytest injeta" de
# "variável nunca lida", e sinaliza F401/F811 em cada função. Uma fixture
# PRÓPRIA, pequena, evita a escolha entre calar o lint em cada função ou
# deixar `ruff check` sujo.


@pytest.fixture
def cenario_pagina_real():
    """Escritório, empresa e duas contas (uma devedora, uma credora) — o
    mínimo para lançar (lançamento) e para o balancete ter movimento."""
    escritorio = Escritorio.objects.create(
        nome="Escritório veredito-na-página", cnpj="55555555000155"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Veredito na Página Ltda",
        cnpj="55566677000155",
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-veredito-pagina",
        email="gestora-veredito-pagina@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client):
    assert client.login(username="gestora-veredito-pagina", password="senha-forte-123")


def _url_lancamento(cenario):
    return reverse("contabilidade_web:lancamento_novo", args=[cenario["empresa"].id])


def _url_balancete(cenario, *, inicio=None, fim=None):
    base = reverse("contabilidade_web:balancete", args=[cenario["empresa"].id])
    if inicio is None or fim is None:
        return base
    return f"{base}?inicio={inicio.isoformat()}&fim={fim.isoformat()}"


def _post_duas_linhas(client, cenario, *, acao, valor_debito, valor_credito, chave):
    return client.post(
        _url_lancamento(cenario),
        {
            "acao": acao,
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "Página real — veredito",
            "chave_idempotencia": chave,
            "conta_1": str(cenario["caixa"].id),
            "tipo_1": "debito",
            "valor_1": valor_debito,
            "conta_2": str(cenario["receita"].id),
            "tipo_2": "credito",
            "valor_2": valor_credito,
        },
    )


_RAIZ = Path(__file__).resolve().parents[3]
_CAMINHO_LANCAMENTO = _RAIZ / "templates" / "contabilidade" / "lancamento_form.html"
_CAMINHO_BALANCETE = _RAIZ / "templates" / "contabilidade" / "balancete.html"

_MARCADOR_INICIO_LANCAMENTO = '{% if veredito_fechamento == "fecha" %}'
_MARCADOR_FIM_LANCAMENTO = "{% endif %}"

_MARCADOR_INICIO_BALANCETE = '{% if veredito_balancete == "fecha" %}'
_MARCADOR_FIM_BALANCETE = "</div>"


def _fragmento(texto, marcador_inicio, marcador_fim):
    inicio = texto.index(marcador_inicio)
    fim = texto.index(marcador_fim, inicio) + len(marcador_fim)
    return texto[inicio:fim]


def _fragmento_veredito_lancamento():
    """O `{% if %}...{% endif %}` que decide o veredito do lançamento,
    extraído do ARQUIVO REAL a cada chamada — nunca uma cópia retypada à
    mão."""
    texto = _CAMINHO_LANCAMENTO.read_text(encoding="utf-8")
    return _fragmento(texto, _MARCADOR_INICIO_LANCAMENTO, _MARCADOR_FIM_LANCAMENTO)


def _fragmento_veredito_balancete():
    texto = _CAMINHO_BALANCETE.read_text(encoding="utf-8")
    return _fragmento(texto, _MARCADOR_INICIO_BALANCETE, _MARCADOR_FIM_BALANCETE)


def _renderizar(fragmento, contexto):
    template = _template_engines["django"].from_string(fragmento)
    return template.render(contexto)


def _texto_veredito_lancamento(contexto, fragmento=None):
    fragmento = fragmento if fragmento is not None else _fragmento_veredito_lancamento()
    html = _renderizar(fragmento, contexto)
    m = re.search(r'<strong class="veredito-fechamento">(.*?)</strong>', html, re.DOTALL)
    assert m, 'o fragmento não produziu nenhum <strong class="veredito-fechamento">: ' + html
    # Normaliza espaço: o `<span class="valor-monetario">` do "não fecha"
    # quebra a frase em mais de uma linha no HTML.
    return re.sub(r"\s+", " ", m.group(1)).strip()


def _texto_veredito_balancete(contexto, fragmento=None):
    fragmento = fragmento if fragmento is not None else _fragmento_veredito_balancete()
    html = _renderizar(fragmento, contexto)
    m = re.search(r'<strong class="faixa-fechamento__veredito">(.*?)</strong>', html, re.DOTALL)
    assert m, 'o fragmento não produziu nenhum <strong class="faixa-fechamento__veredito">: ' + html
    return re.sub(r"\s+", " ", m.group(1)).strip()


# ---------------------------------------------------------------------------
# Contextos sintéticos — um por estado, para as duas telas. Os valores
# pt-BR são arbitrários (não vêm de `_valor_ptbr`, de propósito: este
# arquivo testa o TEMPLATE, não o cálculo — o cálculo já tem cobertura
# própria em test_bl289_veredito_fechamento.py/test_bl290_veredito_
# balancete.py, do desenvolvedor-pleno).
# ---------------------------------------------------------------------------

_CTX_LANCAMENTO_FECHA = {
    "veredito_fechamento": "fecha",
    "total_debito_ptbr": "777,77",
    "total_credito_ptbr": "777,77",
    "diferenca_fechamento_ptbr": None,
    "lado_faltante_fechamento": None,
}
_CTX_LANCAMENTO_NAO_FECHA = {
    "veredito_fechamento": "nao_fecha",
    "total_debito_ptbr": "1.500,00",
    "total_credito_ptbr": "900,00",
    "diferenca_fechamento_ptbr": "600,00",
    "lado_faltante_fechamento": "crédito",
}
_CTX_LANCAMENTO_NAO_CONFERIDO = {
    "veredito_fechamento": "nao_conferido",
    "total_debito_ptbr": None,
    "total_credito_ptbr": None,
    "diferenca_fechamento_ptbr": None,
    "lado_faltante_fechamento": None,
}

_CTX_BALANCETE_FECHA = {
    "veredito_balancete": "fecha",
    "diferenca_balancete_ptbr": None,
    "total_debitos_ptbr": "1.700,00",
    "total_creditos_ptbr": "1.700,00",
}
_CTX_BALANCETE_NAO_FECHA = {
    "veredito_balancete": "nao_fecha",
    "diferenca_balancete_ptbr": "0,01",
    "total_debitos_ptbr": "300,00",
    "total_creditos_ptbr": "300,01",
}
_CTX_BALANCETE_NADA_A_CONFERIR = {
    "veredito_balancete": "nada_a_conferir",
    "diferenca_balancete_ptbr": None,
    "total_debitos_ptbr": "0,00",
    "total_creditos_ptbr": "0,00",
}


# ---------------------------------------------------------------------------
# 1) O texto certo, presente; os outros dois, ausentes — lançamento
# ---------------------------------------------------------------------------


def test_lancamento_fecha_mostra_fecha_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_FECHA)
    assert texto == "Fecha", texto
    assert "Não fecha" not in texto
    assert "Ainda não conferido" not in texto


def test_lancamento_nao_fecha_mostra_a_diferenca_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_FECHA)
    assert texto.startswith("Não fecha, faltam"), texto
    assert "600,00" in texto
    assert "crédito" in texto
    assert texto != "Fecha"
    assert "Ainda não conferido" not in texto


def test_lancamento_nao_conferido_mostra_texto_proprio_e_nao_os_outros_dois():
    texto = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_CONFERIDO)
    assert texto == "Ainda não conferido", texto
    assert "Fecha" not in texto
    assert "Não fecha" not in texto


# ---------------------------------------------------------------------------
# 1) O texto certo, presente; os outros dois, ausentes — balancete
# ---------------------------------------------------------------------------


def test_balancete_fecha_mostra_fecha_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_FECHA)
    assert texto == "Fecha", texto
    assert "Não fecha" not in texto
    assert "Nada a conferir" not in texto


def test_balancete_nao_fecha_mostra_a_diferenca_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_NAO_FECHA)
    assert texto.startswith("Não fecha"), texto
    assert "0,01" in texto
    assert texto != "Fecha"
    assert "Nada a conferir" not in texto


def test_balancete_nada_a_conferir_mostra_texto_proprio_e_nao_os_outros_dois():
    texto = _texto_veredito_balancete(_CTX_BALANCETE_NADA_A_CONFERIR)
    assert texto == "Nada a conferir neste período", texto
    assert "Fecha" not in texto
    assert "Não fecha" not in texto


# ---------------------------------------------------------------------------
# 2) A mutação do arquiteto-senior tem que produzir o texto ERRADO — a
# prova de que os seis testes acima, rodados contra um template mutado,
# morreriam.
# ---------------------------------------------------------------------------


def test_mutacao_comparar_texto_no_lancamento_reproduz_o_a1_e_mente():
    """Reproduz, caractere por caractere, a mutação da revisão `65af1dc`:
    `{% if veredito_fechamento == "fecha" %}` -> `{% if total_debito_ptbr
    == total_credito_ptbr %}`. No estado "ainda não conferido" do
    formulário em branco, os dois totais chegam `None`
    (`total_debito_ptbr`/`total_credito_ptbr`) — `None == None` é
    verdadeiro em template Django, então o mutante cai no ramo "Fecha"
    mesmo a CHAVE do contexto dizendo `"nao_conferido"`. É o defeito
    original do achado A1, voltando por uma linha só.
    """
    fragmento_real = _fragmento_veredito_lancamento()
    fragmento_mutado = fragmento_real.replace(
        _MARCADOR_INICIO_LANCAMENTO,
        "{% if total_debito_ptbr == total_credito_ptbr %}",
        1,
    )
    assert fragmento_mutado != fragmento_real, "controle: a mutação precisa mudar o fragmento"

    texto_sob_mutante = _texto_veredito_lancamento(
        _CTX_LANCAMENTO_NAO_CONFERIDO, fragmento=fragmento_mutado
    )
    assert texto_sob_mutante == "Fecha", (
        "a mutação deveria reproduzir o A1 (tela mente 'Fecha' com a chave em "
        f"'nao_conferido') — texto obtido sob o mutante: {texto_sob_mutante!r}"
    )

    # E o fragmento REAL, no MESMO contexto, continua dizendo a verdade —
    # é o que prova que os testes da seção 1 morreriam sob esta mutação
    # (eles exigem "Ainda não conferido", o mutante entrega "Fecha").
    texto_real = _texto_veredito_lancamento(_CTX_LANCAMENTO_NAO_CONFERIDO)
    assert texto_real == "Ainda não conferido", texto_real


def test_mutacao_comparar_texto_no_balancete_reproduz_o_a2_e_mente():
    """Mesma família, na faixa do balancete — reproduz o defeito original
    do A2/rodada 1: `{% if veredito_balancete == "fecha" %}` ->
    `{% if total_debitos_ptbr == total_creditos_ptbr %}`. No estado "nada
    a conferir" (sem movimento no período), os dois totais chegam
    `"0,00"` — `"0,00" == "0,00"` é verdadeiro em texto, e o mutante cai
    em "Fecha" mesmo a CHAVE dizendo `"nada_a_conferir"`.
    """
    fragmento_real = _fragmento_veredito_balancete()
    fragmento_mutado = fragmento_real.replace(
        _MARCADOR_INICIO_BALANCETE,
        "{% if total_debitos_ptbr == total_creditos_ptbr %}",
        1,
    )
    assert fragmento_mutado != fragmento_real, "controle: a mutação precisa mudar o fragmento"

    texto_sob_mutante = _texto_veredito_balancete(
        _CTX_BALANCETE_NADA_A_CONFERIR, fragmento=fragmento_mutado
    )
    assert texto_sob_mutante == "Fecha", (
        "a mutação deveria reproduzir o A2 (faixa mente 'Fecha' com a chave em "
        f"'nada_a_conferir') — texto obtido sob o mutante: {texto_sob_mutante!r}"
    )

    texto_real = _texto_veredito_balancete(_CTX_BALANCETE_NADA_A_CONFERIR)
    assert texto_real == "Nada a conferir neste período", texto_real


# ---------------------------------------------------------------------------
# Controle: os fragmentos extraídos do arquivo real batem com os
# marcadores esperados — se alguém reescrever o `{% if %}` para outro
# formato (ex.: trocar a ordem dos ramos), este teste avisa ANTES de os
# testes acima começarem a testar fragmento vazio ou errado em silêncio.
# ---------------------------------------------------------------------------


def test_controle_fragmentos_extraidos_contem_os_tres_ramos():
    fragmento_lancamento = _fragmento_veredito_lancamento()
    for pedaco in ('veredito_fechamento == "fecha"', "elif", "else", "veredito-fechamento"):
        assert pedaco in fragmento_lancamento, (pedaco, fragmento_lancamento)

    fragmento_balancete = _fragmento_veredito_balancete()
    for pedaco in ('veredito_balancete == "fecha"', "elif", "else", "faixa-fechamento__veredito"):
        assert pedaco in fragmento_balancete, (pedaco, fragmento_balancete)


# ---------------------------------------------------------------------------
# 3) A PÁGINA REAL — cliente de teste do Django, URL de verdade, view de
# verdade, template de verdade. Ver o docstring do módulo para o achado
# que motivou esta seção (a sabotagem da condição sempre falsa, que os
# itens 1 e 2 acima não pegam).
# ---------------------------------------------------------------------------


def _veredito_lancamento_na_pagina(html):
    """`None` quando o veredito SOME da página — é exatamente o efeito da
    sabotagem "condição sempre falsa": o bloco continua no arquivo,
    intacto, mas nunca é alcançado na renderização real."""
    m = re.search(r'<strong class="veredito-fechamento">(.*?)</strong>', html, re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _veredito_balancete_na_pagina(html):
    m = re.search(r'<strong class="faixa-fechamento__veredito">(.*?)</strong>', html, re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else None


def _exige_texto_do_estado_na_pagina(extrator, html, esperado_prefixo, *proibidos):
    """Exige que o veredito EXISTA na página renderizada de verdade
    (`None` reprova — a armadilha que o arquiteto-senior nomeou: um teste
    que só confere "X not in html" passaria quando o veredito
    simplesmente sumisse) e que o texto comece com `esperado_prefixo`; os
    textos em `proibidos` (os OUTROS estados) não podem aparecer."""
    texto = extrator(html)
    assert texto is not None, "o veredito SUMIU da página renderizada — nenhum <strong> encontrado"
    assert texto.startswith(esperado_prefixo), (
        f"veredito na página = {texto!r}, esperado prefixo {esperado_prefixo!r}"
    )
    for proibido in proibidos:
        assert proibido not in texto, (
            f"veredito na página = {texto!r} não deveria conter {proibido!r}"
        )
    return texto


# --- Lançamento — três estados, página real -------------------------------


@pytest.mark.django_db
def test_pagina_real_lancamento_fecha(client, cenario_pagina_real):
    _login(client)
    resposta = _post_duas_linhas(
        client,
        cenario_pagina_real,
        acao="adicionar_linha",
        valor_debito="777,77",
        valor_credito="777,77",
        chave="k-pagina-real-fecha",
    )
    assert resposta.status_code == 200
    html = resposta.content.decode()
    _exige_texto_do_estado_na_pagina(
        _veredito_lancamento_na_pagina, html, "Fecha", "Não fecha", "Ainda não conferido"
    )


@pytest.mark.django_db
def test_pagina_real_lancamento_nao_fecha(client, cenario_pagina_real):
    _login(client)
    resposta = _post_duas_linhas(
        client,
        cenario_pagina_real,
        acao="adicionar_linha",
        valor_debito="1.500,00",
        valor_credito="900,00",
        chave="k-pagina-real-nao-fecha",
    )
    assert resposta.status_code == 200
    html = resposta.content.decode()
    texto = _exige_texto_do_estado_na_pagina(
        _veredito_lancamento_na_pagina, html, "Não fecha, faltam", "Ainda não conferido"
    )
    assert "600,00" in texto
    assert texto != "Fecha"


@pytest.mark.django_db
def test_pagina_real_lancamento_ainda_nao_conferido_formulario_em_branco(
    client, cenario_pagina_real
):
    _login(client)
    resposta = client.get(_url_lancamento(cenario_pagina_real))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    _exige_texto_do_estado_na_pagina(
        _veredito_lancamento_na_pagina, html, "Ainda não conferido", "Fecha", "Não fecha"
    )


# --- Balancete — três estados, página real ---------------------------------


@pytest.mark.django_db
def test_pagina_real_balancete_fecha(client, cenario_pagina_real):
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cenario_pagina_real["empresa"],
        data=hoje,
        historico="página real — fecha",
        itens=[
            {"conta": cenario_pagina_real["caixa"], "tipo": "debito", "valor": Decimal("500.00")},
            {
                "conta": cenario_pagina_real["receita"],
                "tipo": "credito",
                "valor": Decimal("500.00"),
            },
        ],
        criado_por=None,
        chave_idempotencia="k-pagina-real-bal-fecha",
    )
    resposta = client.get(_url_balancete(cenario_pagina_real, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    _exige_texto_do_estado_na_pagina(
        _veredito_balancete_na_pagina, html, "Fecha", "Não fecha", "Nada a conferir"
    )


@pytest.mark.django_db
def test_pagina_real_balancete_nada_a_conferir(client, cenario_pagina_real):
    _login(client)
    resposta = client.get(_url_balancete(cenario_pagina_real))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    _exige_texto_do_estado_na_pagina(
        _veredito_balancete_na_pagina, html, "Nada a conferir", "Fecha", "Não fecha"
    )


@pytest.mark.django_db
def test_pagina_real_balancete_nao_fecha_com_totais_forcados(
    client, cenario_pagina_real, monkeypatch
):
    """O ramo "não fecha" do balancete é uma REDE DE SEGURANÇA — partida
    dobrada garante débito == crédito por construção; forçado aqui via
    `monkeypatch` em `apurar_balancete`, mesmo padrão já usado em
    `test_dl017_telas.py` e em `test_bl290_veredito_balancete.py`."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cenario_pagina_real["empresa"],
        data=hoje,
        historico="página real — base para divergência",
        itens=[
            {"conta": cenario_pagina_real["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {
                "conta": cenario_pagina_real["receita"],
                "tipo": "credito",
                "valor": Decimal("300.00"),
            },
        ],
        criado_por=None,
        chave_idempotencia="k-pagina-real-bal-divergente",
    )
    apuracao_real = views_web.apurar_balancete(
        empresa=cenario_pagina_real["empresa"], inicio=hoje.replace(day=1), fim=hoje, nivel=None
    )

    def _apuracao_divergente(*, empresa, inicio, fim, nivel=None):
        divergente = dict(apuracao_real)
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.01")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_divergente)

    resposta = client.get(_url_balancete(cenario_pagina_real, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    texto = _exige_texto_do_estado_na_pagina(
        _veredito_balancete_na_pagina, html, "Não fecha", "Nada a conferir"
    )
    assert texto != "Fecha"


# ---------------------------------------------------------------------------
# Prova por mutação (b): a condição sempre falsa — CORRIGIDA pelo BL-311
# (achado M2 da auditoria DL-026, rodada 3): a versão anterior mutava o
# ARQUIVO REAL (com try/finally e restauração byte a byte). O auditor
# mediu que duas execuções concorrentes deste MESMO arquivo, na mesma
# árvore, corrompem o repositório de forma ACUMULATIVA — a segunda
# execução lê "original" o que a primeira já tinha mutado. A técnica
# abaixo nunca escreve fora de `tmp_path`; ver o docstring do módulo para
# a explicação completa (`_arvore_de_templates_com_mutacao`).
# ---------------------------------------------------------------------------

_RAIZ_TEMPLATES = _RAIZ / "templates"


def _arvore_de_templates_com_mutacao(tmp_path, caminho_real, mutar):
    """Copia `templates/` INTEIRO (com `shutil.copytree`) para dentro do
    `tmp_path` que o pytest cria — ISOLADO e EXCLUSIVO por chamada de
    teste, inclusive entre execuções concorrentes do MESMO arquivo de
    teste — e aplica `mutar` (texto original -> texto mutado) só no
    arquivo correspondente a `caminho_real`, DENTRO DA CÓPIA. O arquivo
    do repositório é só LIDO, nunca escrito. Devolve o diretório
    `templates/` da cópia, pronto para `TEMPLATES[0]["DIRS"]`.
    """
    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)

    caminho_relativo = caminho_real.relative_to(_RAIZ_TEMPLATES)
    caminho_na_copia = raiz_copia / caminho_relativo

    conteudo_original = caminho_real.read_text(encoding="utf-8")  # leitura, nunca escrita
    conteudo_mutado = mutar(conteudo_original)
    assert conteudo_mutado != conteudo_original, "controle: a mutação precisa mudar o conteúdo"
    caminho_na_copia.write_text(conteudo_mutado, encoding="utf-8")  # escreve SÓ na cópia

    return raiz_copia


def _templates_com_dirs(raiz_copia):
    """As MESMAS opções de `django.conf.settings.TEMPLATES` — só `DIRS`
    muda, para a cópia mutada. Preservar `APP_DIRS` e os
    `context_processors` importa: são eles que fazem `base.html` (herdado
    por `{% extends %}`) e o contexto de autenticação/mensagens se
    comportarem OS MESMOS que em produção; qualquer diferença aqui
    provaria menos do que a página real.

    BL-325 (achado B2 da auditoria DL-026, rodada 4,
    docs/auditorias/2026-09-19-dl-024-rodada-4.md): a versão anterior
    desta função TRANSCREVIA `context_processors` à mão, numa constante de
    módulo (`_OPTIONS_TEMPLATES_ORIGINAIS`) — a promessa do comentário
    ("as MESMAS opções") já era uma CÓPIA, não uma LEITURA. O auditor
    mediu: acrescentar `django.template.context_processors.static` a
    `config/settings.py` deixava este teste rodando sob a lista ANTIGA —
    `17 passed`, sem nada acusar, e a alegação "página real" passaria a
    valer para uma configuração que a produção não usa mais.

    `copy.deepcopy` porque `settings.TEMPLATES` é uma lista de
    dicionários aninhados (`OPTIONS` é, por sua vez, outro dicionário com
    uma lista dentro); sobrescrever `DIRS` num dicionário copiado por
    REFERÊNCIA mutaria a configuração que `django.conf.settings` usa de
    verdade — a mesma classe de acoplamento por compartilhamento que
    motivou copiar a ÁRVORE inteira de templates em
    `_arvore_de_templates_com_mutacao`, agora aplicada à CONFIGURAÇÃO em
    vez de ao arquivo.
    """
    motor = copy.deepcopy(settings.TEMPLATES)
    # Esta função só sabe substituir o `DIRS` de UM motor de template. Se
    # o projeto um dia configurar um segundo motor (ex.: Jinja2), a
    # escolha de qual `DIRS` a cópia isolada substitui precisa ser
    # CONSCIENTE, não "o primeiro da lista" — por isso a asserção reprova
    # em vez de ignorar o motor extra em silêncio.
    assert len(motor) == 1, (
        "settings.TEMPLATES tem mais de um motor configurado; "
        "_templates_com_dirs precisa decidir explicitamente qual DIRS substituir "
        f"(achei {len(motor)})"
    )
    motor[0]["DIRS"] = [raiz_copia]
    return motor


def test_templates_com_dirs_deriva_de_settings_e_nao_de_transcricao_manual(
    client, cenario_pagina_real, tmp_path
):
    """Prova a leitura, não só a declara. BL-325: acrescenta
    `django.template.context_processors.static` (que expõe `STATIC_URL`
    no contexto de toda renderização) a uma CÓPIA de
    `settings.TEMPLATES`, ativa essa cópia só para a duração deste teste
    (`override_settings` — nunca escreve em `config/settings.py`, que é
    arquivo de outro responsável) e confirma que a PÁGINA REAL, servida
    pela árvore isolada de `_templates_com_dirs`, TRAZ `STATIC_URL` no
    contexto.

    Sob a transcrição manual anterior (`_OPTIONS_TEMPLATES_ORIGINAIS`),
    esta asserção teria falhado: o processador acrescentado não estaria
    na lista copiada, e a página real ficaria sem `STATIC_URL` mesmo com
    `settings.TEMPLATES` pedindo por ele — o próprio silêncio que o
    achado B2 descreve, agora convertido em teste que MORRE se a leitura
    voltar a ser transcrição.
    """
    raiz_copia = tmp_path / "templates"
    shutil.copytree(_RAIZ_TEMPLATES, raiz_copia)

    # Simula "alguém acrescentou um processador a config/settings.py":
    # nunca tocamos o arquivo real, só a CÓPIA de settings.TEMPLATES que
    # override_settings vai instalar — settings.py é arquivo do
    # desenvolvedor-pleno, fora do escopo desta etapa.
    templates_com_processador_novo = copy.deepcopy(settings.TEMPLATES)
    assert len(templates_com_processador_novo) == 1
    templates_com_processador_novo[0]["OPTIONS"]["context_processors"].append(
        "django.template.context_processors.static"
    )

    with override_settings(TEMPLATES=templates_com_processador_novo):
        templates_da_copia = _templates_com_dirs(raiz_copia)
        # Controle: _templates_com_dirs precisa ter LIDO o processador
        # novo — se este `assert` falhar, o resto do teste não prova nada.
        assert (
            "django.template.context_processors.static"
            in templates_da_copia[0]["OPTIONS"]["context_processors"]
        ), "controle: _templates_com_dirs não refletiu o processador acrescentado a settings"

        with override_settings(TEMPLATES=templates_da_copia):
            _login(client)
            resposta = client.get(_url_lancamento(cenario_pagina_real))
            assert resposta.status_code == 200
            assert resposta.context is not None, (
                "controle: a renderização precisa ter usado RequestContext "
                "para o teste conseguir inspecionar o contexto"
            )
            assert resposta.context.get("STATIC_URL") is not None, (
                "o processador acrescentado a settings.TEMPLATES não chegou à "
                "PÁGINA REAL — _templates_com_dirs está transcrevendo OPTIONS "
                "em vez de derivar de settings.TEMPLATES (o defeito do BL-325)"
            )

    # Fora dos dois `with`: a página volta a não ter STATIC_URL no
    # contexto (a configuração original não inclui o processador de
    # static) — controle de que a mutação não vazou para fora do bloco.
    resposta_normal = client.get(_url_lancamento(cenario_pagina_real))
    assert resposta_normal.status_code == 200
    assert resposta_normal.context.get("STATIC_URL") is None, (
        "controle: fora do override, o processador de static não deveria estar ativo"
    )


def _mutacao_condicao_sempre_falsa(fragmento):
    def _mutar(conteudo_original):
        return conteudo_original.replace(
            fragmento,
            "{% if nunca_definido_no_contexto %}" + fragmento + "{% endif %}",
            1,
        )

    return _mutar


@pytest.mark.django_db
def test_mutacao_condicao_sempre_falsa_esconde_o_veredito_da_pagina_lancamento(
    client, cenario_pagina_real, tmp_path
):
    conteudo_do_repositorio_antes = _CAMINHO_LANCAMENTO.read_text(encoding="utf-8")

    raiz_copia = _arvore_de_templates_com_mutacao(
        tmp_path,
        _CAMINHO_LANCAMENTO,
        _mutacao_condicao_sempre_falsa(_fragmento_veredito_lancamento()),
    )

    with override_settings(TEMPLATES=_templates_com_dirs(raiz_copia)):
        _login(client)
        resposta = client.get(_url_lancamento(cenario_pagina_real))
        assert resposta.status_code == 200
        texto = _veredito_lancamento_na_pagina(resposta.content.decode())
        assert texto is None, (
            "a mutação (condição sempre falsa) deveria fazer o veredito SUMIR da "
            f"página, e não sumiu — achado: {texto!r}. A guarda da seção 3 não pegaria "
            "esta sabotagem."
        )

    # `override_settings` já restaurou `TEMPLATES` ao sair do `with` (e
    # disparou o `setting_changed` que limpa o cache de
    # `django.template.engines` — ver o docstring do módulo). Controle de
    # que a mutação realmente rodou SOB a `override_settings` e não
    # vazou para fora dela: a MESMA página, fora do bloco, volta a
    # mostrar o veredito de verdade.
    resposta_normal = client.get(_url_lancamento(cenario_pagina_real))
    assert resposta_normal.status_code == 200
    texto_normal = _veredito_lancamento_na_pagina(resposta_normal.content.decode())
    assert texto_normal == "Ainda não conferido", texto_normal

    # O arquivo do REPOSITÓRIO nunca foi escrito — nada a restaurar. Esta
    # asserção é o que, nesta suíte, ocupa o lugar da antiga conferência
    # byte a byte pós-restauração: aqui ela prova AUSÊNCIA de escrita, não
    # sucesso de restauração.
    assert _CAMINHO_LANCAMENTO.read_text(encoding="utf-8") == conteudo_do_repositorio_antes


@pytest.mark.django_db
def test_mutacao_condicao_sempre_falsa_esconde_o_veredito_da_pagina_balancete(
    client, cenario_pagina_real, tmp_path
):
    conteudo_do_repositorio_antes = _CAMINHO_BALANCETE.read_text(encoding="utf-8")

    raiz_copia = _arvore_de_templates_com_mutacao(
        tmp_path,
        _CAMINHO_BALANCETE,
        _mutacao_condicao_sempre_falsa(_fragmento_veredito_balancete()),
    )

    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cenario_pagina_real["empresa"],
        data=hoje,
        historico="mutação — condição sempre falsa",
        itens=[
            {
                "conta": cenario_pagina_real["caixa"],
                "tipo": "debito",
                "valor": Decimal("500.00"),
            },
            {
                "conta": cenario_pagina_real["receita"],
                "tipo": "credito",
                "valor": Decimal("500.00"),
            },
        ],
        criado_por=None,
        chave_idempotencia="k-mutacao-bal-sempre-falsa",
    )

    with override_settings(TEMPLATES=_templates_com_dirs(raiz_copia)):
        _login(client)
        resposta = client.get(
            _url_balancete(cenario_pagina_real, inicio=hoje.replace(day=1), fim=hoje)
        )
        assert resposta.status_code == 200
        texto = _veredito_balancete_na_pagina(resposta.content.decode())
        assert texto is None, (
            "a mutação (condição sempre falsa) deveria fazer o veredito SUMIR da "
            f"página, e não sumiu — achado: {texto!r}."
        )

    resposta_normal = client.get(
        _url_balancete(cenario_pagina_real, inicio=hoje.replace(day=1), fim=hoje)
    )
    assert resposta_normal.status_code == 200
    texto_normal = _veredito_balancete_na_pagina(resposta_normal.content.decode())
    assert texto_normal == "Fecha", texto_normal

    assert _CAMINHO_BALANCETE.read_text(encoding="utf-8") == conteudo_do_repositorio_antes
