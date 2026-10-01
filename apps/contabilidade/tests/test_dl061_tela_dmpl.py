"""DL-061, fatia 1 (TELA) — a Demonstração das Mutações do Patrimônio Líquido
(DMPL) renderizada: permissão, estados, documento, norma por vigência,
rastreabilidade, classificação da coluna, marca de adoção antecipada da NBC
TG 51 e vitrine (plano de contas, hub, menu).

Cobre os critérios de aceite 6 (parte HTML; a medição de PAPEL está em
`scripts/medir_identificacao_do_emitente.py`), 7 e 10 do plano
(docs/planos/DL-061-dmpl.md). Os números e a apuração são do servidor e
já têm testes próprios em `test_dl061_dmpl.py`; aqui se prova que a TELA os
mostra certos, no lugar certo, para quem pode vê-los — e só para esses.

Os cenários reaproveitam os do servidor (casos A e B do plano, calculados à
mão) importando os construtores de `test_dl061_dmpl.py`; dados 100%
sintéticos. Hoje é 2026-10-01; o exercício é o ano civil (HI-28).

Toda regra de tela tem um teste que derrubaria uma mutação plausível dela:
limite de colunas do retrato, permissão da marca (administrador/gestor, não
"quem escritura"), link de correção só para quem escritura, filtro por
empresa dos lançamentos de origem, "—" no lugar do zero, parênteses no
negativo, início do exercício vindo do contexto.
"""

from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade import views_web
from apps.contabilidade.models import (
    ClassificacaoDlpa,
    Conta,
    LancamentoContabil,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
)
from apps.contabilidade.services import (
    _LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO,
    _TITULOS_DAS_PENDENCIAS_DA_DMPL,
    definir_adocao_antecipada_da_nbc_tg_51,
    registrar_parametro_contabil,
)
from apps.contabilidade.tests.test_dl048_dlpa import _autenticar, _cnpj_sintetico
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    LUCROS,
    MES,
    PL,
    C,
    D,
    _caso_a,
    _caso_b,
    _conta,
    _empresa,
    _lancar,
    _lancar_itens,
    _plano_basico,
)
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
from apps.tenancy.models import Escritorio, Papel

pytestmark = pytest.mark.django_db

PAPEIS_QUE_LEEM = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
)
PAPEIS_QUE_ESCRITURAM = (Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO)
PAPEIS_QUE_GEREM_PARAMETRO = (Papel.ADMINISTRADOR, Papel.GESTOR)

RAIZ = Path(__file__).resolve().parents[3]


def _url(empresa, ano=ANO, mes=MES):
    return f"{reverse('contabilidade_web:dmpl', args=[empresa.id])}?ano={ano}&mes={mes}"


def _entrar(client, empresa, papel=Papel.GESTOR, nome="usuario-tela"):
    _autenticar(client, empresa.escritorio, f"{nome}-{papel.value}-{empresa.pk}", papel=papel)


class _LeitorDoCorpoDaTabela(HTMLParser):
    """Lê o `<tbody>` da tabela da DMPL (`.tabela-dmpl`) como lista de linhas,
    cada uma `[cabeçalho_da_linha, célula, célula, …, total]` com o TEXTO
    VISÍVEL de cada célula — o que o contador lê no papel. O texto só para
    leitor de tela (`.visualmente-oculto`) fica de fora."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.dentro = False
        self.no_corpo = False
        self.linhas = []
        self._celula = None
        self._oculto = False

    def handle_starttag(self, tag, attrs):
        classes = (dict(attrs).get("class") or "").split()
        if tag == "table" and "tabela-dmpl" in classes:
            self.dentro = True
        elif self.dentro and tag == "tbody":
            self.no_corpo = True
        elif self.dentro and self.no_corpo and tag == "tr":
            self.linhas.append([])
        elif self.dentro and self.no_corpo and tag in ("td", "th"):
            self._celula = []
        elif tag == "span" and "visualmente-oculto" in classes and self._celula is not None:
            self._oculto = True

    def handle_endtag(self, tag):
        if tag == "span" and self._oculto:
            self._oculto = False
        elif tag in ("td", "th") and self._celula is not None:
            self.linhas[-1].append(" ".join("".join(self._celula).split()))
            self._celula = None
        elif tag == "tbody" and self.dentro:
            self.no_corpo = False
        elif tag == "table" and self.dentro:
            self.dentro = False

    def handle_data(self, data):
        if self._celula is not None and not self._oculto:
            self._celula.append(data)


def _texto(html):
    """O HTML com toda sequência de espaço/quebra de linha reduzida a um
    espaço: o texto de uma frase pode atravessar linhas do template, e o
    navegador a mostra numa linha só."""
    return " ".join(html.split())


def _linhas_da_tabela(html):
    leitor = _LeitorDoCorpoDaTabela()
    leitor.feed(html)
    return leitor.linhas


# ---------------------------------------------------------------------------
# Permissão, isolamento e recusa de livro-caixa (critérios 7 e 8)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", PAPEIS_QUE_LEEM)
def test_todo_papel_que_le_a_contabilidade_ve_a_dmpl_pronta(client, papel):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, papel)
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "DMPL pronta para emissão" in conteudo
    assert "115.000,00" in conteudo


def test_cliente_recebe_403_e_nenhum_valor_nem_nome_da_empresa(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.CLIENTE)
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    conteudo = resposta.content.decode()
    assert "Seu papel não permite" in conteudo
    for valor in ("115.000,00", "100.000,00", "13.750,00"):
        assert valor not in conteudo, valor
    # (O nome do escritório de teste contém o da empresa; o que não pode
    # aparecer é a pílula "Empresa" do contexto, nem o CNPJ dela.)
    assert '<span class="contexto-rotulo">Empresa</span>' not in conteudo
    assert empresa.cnpj not in conteudo


def test_empresa_de_outro_escritorio_da_404_e_nao_confirma_a_existencia(client):
    empresa, _, _ = _caso_a()
    outro = Escritorio.objects.create(nome="Outro Escritório DMPL", cnpj=_cnpj_sintetico())
    _autenticar(client, outro, "gestor-outro-dmpl")
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 404
    assert '<span class="contexto-rotulo">Empresa</span>' not in resposta.content.decode()


def test_sem_escritorio_ativo_a_tela_nao_monta_nada(client):
    empresa, _, _ = _caso_a()
    get_user_model().objects.create_user(username="sem-vinculo-dmpl", password="senha-forte-123")
    assert client.login(username="sem-vinculo-dmpl", password="senha-forte-123")
    resposta = client.get(_url(empresa))
    conteudo = resposta.content.decode()
    assert "115.000,00" not in conteudo and "tabela-dmpl" not in conteudo
    assert empresa.cnpj not in conteudo


def test_empresa_em_livro_caixa_e_recusada_na_dmpl_e_na_classificacao(client):
    """A varredura de `test_dl038_recusa_livro_caixa.py` já cobre as rotas; aqui
    o efeito concreto: a mensagem única, e nada gravado pelo POST."""
    escritorio = Escritorio.objects.create(
        nome="Escritório Livro-Caixa DMPL", cnpj=_cnpj_sintetico()
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Livro-Caixa DMPL Ltda",
        cnpj=_cnpj_sintetico(),
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    _autenticar(client, escritorio, "gestor-livro-caixa-dmpl")
    resposta = client.get(reverse("contabilidade_web:dmpl", args=[empresa.id]))
    assert resposta.status_code == 403
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()
    resposta = client.post(
        reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, 1]),
        {"classificacao_dmpl": COL.CAPITAL_SOCIAL},
    )
    assert resposta.status_code == 403
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()


# ---------------------------------------------------------------------------
# Estados: vazio, competência malformada, navegação
# ---------------------------------------------------------------------------


def test_empresa_sem_contas_mostra_o_estado_vazio_com_o_caminho_para_sair_dele(client):
    escritorio = Escritorio.objects.create(nome="Escritório Vazio DMPL", cnpj=_cnpj_sintetico())
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Vazia DMPL Ltda", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, escritorio, "gestor-vazio-dmpl")
    resposta = client.get(reverse("contabilidade_web:dmpl", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ainda não tem nenhuma conta cadastrada" in conteudo
    assert reverse("contabilidade_web:plano_de_contas", args=[empresa.id]) in conteudo
    assert "identificacao-do-documento" not in conteudo


def test_competencia_malformada_recebe_400_com_o_caminho_de_volta(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.get(f"{reverse('contabilidade_web:dmpl', args=[empresa.id])}?ano=abc&mes=3")
    assert resposta.status_code == 400
    conteudo = resposta.content.decode()
    assert "nenhum dado foi carregado" in conteudo
    assert "115.000,00" not in conteudo


def test_a_navegacao_por_mes_leva_ao_mes_anterior_e_ao_seguinte(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    conteudo = client.get(_url(empresa)).content.decode()
    base = reverse("contabilidade_web:dmpl", args=[empresa.id])
    assert f"{base}?ano=2026&mes=2" in conteudo
    assert f"{base}?ano=2026&mes=4" in conteudo
    assert "Até Março de 2026" in conteudo


# ---------------------------------------------------------------------------
# O documento: caso A, valores, parênteses, "—" (critérios 1 e 9 vistos pela tela)
# ---------------------------------------------------------------------------


def test_caso_a_aparece_com_os_valores_certos_o_negativo_entre_parenteses_e_traco_sem_movimento(
    client,
):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert _linhas_da_tabela(html) == [
        ["Saldo no início do exercício", "100.000,00", "0,00", "0,00", "100.000,00"],
        ["Resultado do exercício", "—", "—", "25.000,00", "25.000,00"],
        ["Constituição de reservas", "—", "1.250,00", "(1.250,00)", "0,00"],
        ["Dividendos", "—", "—", "(10.000,00)", "(10.000,00)"],
        ["Saldo no fim do período", "100.000,00", "1.250,00", "13.750,00", "115.000,00"],
    ]
    assert "valor-invertido" in html, "o negativo sai pela classe que o imprime entre parênteses"


def test_caso_b_aparece_com_as_cinco_colunas_na_ordem_do_item_111a(client):
    empresa, _, _ = _caso_b()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    linhas = _linhas_da_tabela(html)
    assert linhas[-1] == [
        "Saldo no fim do período",
        "120.000,00",
        "3.000,00",
        "1.250,00",
        "(2.000,00)",
        "13.750,00",
        "136.000,00",
    ]
    # Cada evento do caso B, na célula certa e na ordem da decisão E4.
    titulos = [linha[0] for linha in linhas]
    assert titulos == [
        "Saldo no início do exercício",
        "Aumento de capital",
        "Aquisição de ações ou quotas em tesouraria",
        "Resultado do exercício",
        "Outros resultados abrangentes",
        "Constituição de reservas",
        "Dividendos",
        "Saldo no fim do período",
    ]
    por_titulo = {linha[0]: linha for linha in linhas}
    assert por_titulo["Aquisição de ações ou quotas em tesouraria"][1:] == [
        "—",
        "—",
        "—",
        "(2.000,00)",
        "—",
        "(2.000,00)",
    ]
    # Posição das colunas no cabeçalho: a ordem do 111A, sem inversão.
    posicoes = [
        html.index(titulo)
        for titulo in (
            "Capital social",
            "Ajustes de avaliação patrimonial",
            "Reservas de lucros",
            "Ações ou quotas em tesouraria",
            "Lucros ou prejuízos acumulados",
        )
    ]
    assert posicoes == sorted(posicoes)


def test_celula_sem_movimento_diz_sem_movimento_ao_leitor_de_tela_e_nao_e_zero(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert (
        '<span aria-hidden="true">—</span><span class="visualmente-oculto">sem movimento</span>'
        in html
    )


def test_o_cabecalho_agrupa_as_colunas_pelo_grupo_do_item_111a(client):
    """Duas reservas de lucros viram UM cabeçalho de grupo de duas colunas;
    grupo de uma coluna só, de mesmo título, vira célula única de duas
    linhas (sem repetir o nome)."""
    empresa, contas, _ = _caso_a()
    estatutaria = _conta(
        empresa,
        "3.8",
        "Reserva Estatutária",
        PL,
        C,
        dmpl=COL.RESERVA_ESTATUTARIA,
        dlpa=ClassificacaoDlpa.RESERVA_ESTATUTARIA,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 3, 31), "Estatutária", contas["lucros"], estatutaria, "100.00")
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert 'scope="colgroup" class="cabecalho-grupo" colspan="2">Reservas de lucros</th>' in html
    assert 'class="cabecalho-numerico" rowspan="2">Capital social</th>' in html
    assert 'colspan="1">Capital social' not in html, "grupo fundido não repete o título"
    assert 'rowspan="2">Total</th>' in html


def test_o_total_e_a_soma_das_colunas_em_toda_linha_do_documento(client):
    empresa, _, _ = _caso_b()
    _entrar(client, empresa)
    from decimal import Decimal

    def numero(texto):
        if texto == "—":
            return Decimal("0")
        negativo = texto.startswith("(")
        valor = Decimal(texto.strip("()").replace(".", "").replace(",", "."))
        return -valor if negativo else valor

    for linha in _linhas_da_tabela(client.get(_url(empresa)).content.decode()):
        assert sum(numero(c) for c in linha[1:-1]) == numero(linha[-1]), linha


# ---------------------------------------------------------------------------
# Identificação do emitente, período e norma por vigência (critérios 5 e 6)
# ---------------------------------------------------------------------------


def test_o_documento_tem_identificacao_dentro_do_thead_e_cobre_todas_as_colunas(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    # Dentro do <thead>: é o que repete em cada página impressa.
    cabecalho = _texto(html[html.index("<thead>") : html.index("</thead>")])
    assert "linha-identificacao-do-documento" in cabecalho
    assert "identificacao-do-documento" in cabecalho
    assert empresa.razao_social in cabecalho
    # Histórico + 3 colunas + Total = 5.
    assert 'scope="colgroup" colspan="5"' in cabecalho
    assert "Demonstração das Mutações do Patrimônio Líquido" in cabecalho
    assert "exercício de 01/01/2026 a 31/03/2026" in cabecalho
    assert "conferidos com o Balanço Patrimonial de 31/03/2026" in cabecalho


def test_o_inicio_do_exercicio_vem_do_contexto_e_nao_de_um_literal_do_template(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    assert resposta.context["data_inicio_exercicio"] == date(2026, 1, 1)
    assert resposta.context["data_fim"] == date(2026, 3, 31)
    fonte = (RAIZ / "templates/contabilidade/dmpl.html").read_text(encoding="utf-8")
    assert "01/01/{{" not in fonte, "o início do exercício nunca é escrito como 01/01/{{ ano }}"


def test_2026_cita_a_nbc_tg_26_r5_com_os_itens_da_r5(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "Base normativa: NBC TG 26 (R5), itens 106 a 110" in html
    assert "item 106B" in html
    assert "identificação conforme o item 51" in html
    # E8: o dividendo por ação, com o item da norma vigente (107 na R5).
    assert "Dividendo por ação ou por quota: não apresentado" in html
    assert "NBC TG 26 (R5), item 107" in html
    assert "NBC TG 51" not in html
    assert "Adoção antecipada" not in html


def test_2027_cita_a_nbc_tg_51_com_os_itens_da_tg_51(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa, ano=2027, mes=3))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Base normativa: NBC TG 51, itens 107 a 112" in html
    assert "item 111A" in html
    assert "identificação conforme o item 27" in html
    assert "NBC TG 51, item 110" in html, "dividendo por ação: item 110 na TG 51"
    assert "exercício de 01/01/2027 a 31/03/2027" in html
    assert "NBC TG 26 (R5)" not in html
    # A sequência é contínua: o saldo inicial de 2027 é o final de 2026.
    assert _linhas_da_tabela(html)[0][0:2] == ["Saldo no início do exercício", "100.000,00"]
    assert "Adoção antecipada" not in html, "em 2027 a TG 51 é obrigatória, não antecipada"


def test_2026_com_adocao_antecipada_cita_a_nbc_tg_51_e_diz_que_e_antecipada(client):
    empresa, _, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "Base normativa: NBC TG 51, itens 107 a 112" in html
    assert "identificação conforme o item 27" in html
    assert "Adoção antecipada da NBC TG 51, declarada nos parâmetros contábeis da empresa" in html
    assert "NBC TG 26 (R5)" not in html


# ---------------------------------------------------------------------------
# Impressão: paisagem para muitas colunas, conferência só na tela (critério 6)
# ---------------------------------------------------------------------------


def test_ate_quatro_colunas_imprime_em_retrato_e_acima_disso_em_paisagem(client):
    empresa_a, _, _ = _caso_a()
    _entrar(client, empresa_a)
    resposta = client.get(_url(empresa_a))
    assert len(resposta.context["tabela"]["colunas"]) == 3
    assert resposta.context["imprime_em_paisagem"] is False
    assert "pagina-dmpl-impressao" not in resposta.content.decode()

    empresa_b, _, _ = _caso_b()
    _entrar(client, empresa_b)
    resposta = client.get(_url(empresa_b))
    assert len(resposta.context["tabela"]["colunas"]) == 5
    assert resposta.context["imprime_em_paisagem"] is True
    assert '<body class="pagina-dmpl-impressao">' in resposta.content.decode()


def test_exatamente_quatro_colunas_ainda_cabem_em_retrato(client):
    """Limite: a fronteira é "mais de quatro". Mutação típica: `>=`."""
    empresa, contas, _ = _caso_a()
    ajustes = _conta(
        empresa,
        "3.5",
        "Ajustes",
        PL,
        C,
        dmpl=COL.AJUSTES_DE_AVALIACAO_PATRIMONIAL,
        pai=contas["pl"],
    )
    _lancar(empresa, date(2026, 3, 10), "Reavaliação", contas["imobilizado"], ajustes, "3000.00")
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    assert len(resposta.context["tabela"]["colunas"]) == 4
    assert resposta.context["imprime_em_paisagem"] is False


def test_a_folha_de_estilo_imprime_a_dmpl_em_paisagem_e_sem_a_conferencia_de_bancada():
    css = (RAIZ / "static/css/base.css").read_text(encoding="utf-8")
    # A orientação e a margem do @page são conferidas em
    # `test_dl061_tela_dmpl_correcoes.py` (N5, com a margem lida do próprio bloco).
    assert "@page dmpl-paisagem {\n    size: A4 landscape;" in css
    impressao = css[css.index("@media print") :]
    assert "page: dmpl-paisagem;" in impressao
    assert ".bloco--somente-tela {\n        display: none;\n    }" in impressao


def test_conferencia_e_origens_ficam_em_blocos_que_nao_saem_no_papel(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    for titulo in ("Conferência com o Balanço de 31/03/2026", "Lançamentos de origem"):
        trecho = html[: html.index(titulo)]
        assert trecho.rfind('class="bloco--somente-tela"') > trecho.rfind("</table>"), titulo
    # O documento (tabela + notas) NÃO está dentro de bloco somente-tela.
    assert html.index("notas-do-documento") < html.index("bloco--somente-tela")
    assert "Dividendo por ação ou por quota" in html


def test_a_conferencia_mostra_a_prova_com_o_balanco_e_diferenca_zero(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    secao = _texto(html[html.index("Conferência com o Balanço de 31/03/2026") :])
    assert "derivada do item 106(d) da NBC TG 26 (R5)" in secao
    assert "a norma não a manda em letra" in secao
    assert "Total do patrimônio líquido" in secao
    assert "115.000,00" in secao
    assert "Saldo no Balanço" in secao


# ---------------------------------------------------------------------------
# Rastreabilidade por célula
# ---------------------------------------------------------------------------


def test_cada_celula_com_movimento_leva_aos_lancamentos_de_origem(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    dividendos = LancamentoContabil.objects.get(empresa=empresa, historico="Dividendos")
    reserva = LancamentoContabil.objects.get(empresa=empresa, historico="Reserva legal")
    # Âncora no valor da célula…
    assert 'href="#origem-dividendos-lucros_ou_prejuizos_acumulados"' in html
    assert 'href="#origem-constituicao_de_reservas-reserva_legal"' in html
    assert 'href="#origem-constituicao_de_reservas-lucros_ou_prejuizos_acumulados"' in html
    # …e o bloco de destino, com o lançamento aberto no detalhe.
    destino = html[html.index('id="origem-dividendos-lucros_ou_prejuizos_acumulados"') :]
    assert "31/03/2026 — Dividendos" in destino
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, dividendos.id]) in destino
    )
    destino = html[html.index('id="origem-constituicao_de_reservas-reserva_legal"') :]
    assert reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, reserva.id]) in destino
    # O nome acessível do link começa pelo valor visível.
    assert "ver lançamentos de origem: Dividendos, Lucros ou prejuízos acumulados" in html


def test_celula_sem_lancamento_de_origem_nao_vira_link(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    # Só as 4 células de EVENTO com lançamento (resultado; constituição em
    # duas colunas; dividendos) são link; saldos e totais não têm âncora.
    assert html.count('class="valor-com-origem"') == 4
    assert "#origem-saldo_inicial" not in html and "#origem-saldo_final" not in html


def test_lancamento_de_outra_empresa_injetado_na_apuracao_nunca_aparece(client, monkeypatch):
    """Defesa em profundidade (DL-058/B2): mesmo que um id alheio escape da
    apuração, a tela só resolve lançamentos DA EMPRESA da requisição."""
    empresa, _, _ = _caso_a()
    alheia = _empresa("Empresa Alheia Ltda")
    contas_alheias = _plano_basico(alheia)
    segredo = _lancar(
        alheia,
        date(2026, 3, 9),
        "SEGREDO-DA-OUTRA-EMPRESA",
        contas_alheias["caixa"],
        contas_alheias["capital"],
        "1.00",
    )
    original = views_web.apurar_dmpl

    def com_id_alheio(**kwargs):
        dmpl = original(**kwargs)
        dmpl["linhas"][1]["lancamentos"].setdefault(LUCROS, []).append(segredo.id)
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", com_id_alheio)
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "SEGREDO-DA-OUTRA-EMPRESA" not in html
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, segredo.id]) not in html
    )


def test_resultado_nao_transferido_e_aviso_na_tela_e_nunca_veto(client):
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 29),
        "Receita nova, sem zerar",
        contas["caixa"],
        contas["receita"],
        "777.00",
    )
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "DMPL pronta para emissão" in html
    assert "Resultado do exercício ainda não zerado" in html
    assert "Ainda há resultado sem zerar: 777,00" in html
    # Aviso é conferência de bancada: marcado para não sair no papel.
    aviso = html[html.rindex('<div class="mensagem mensagem-warning') :]
    assert "mensagem--somente-tela" in aviso.split(">")[0]


def test_dmpl_sem_movimento_traz_so_os_saldos_e_diz_que_nao_houve_movimento(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa, ano=2026, mes=1)).content.decode()
    assert "Não houve movimento no patrimônio líquido entre 01/01/2026 e 31/01/2026" in _texto(html)
    assert [linha[0] for linha in _linhas_da_tabela(html)] == [
        "Saldo no início do exercício",
        "Saldo no fim do período",
    ]


# ---------------------------------------------------------------------------
# O veto: cada pendência na tela, com ação e link só para quem escritura
# ---------------------------------------------------------------------------


def _veto_nenhuma_coluna():
    empresa = _empresa()
    _conta(empresa, "3.1", "Capital Social", PL, C)
    _conta(empresa, "1.1", "Caixa", TipoConta.ATIVO, D)
    return empresa, ["Nenhuma conta está classificada em uma coluna da DMPL"]


def _veto_conta_de_pl_sem_coluna():
    empresa, contas, _ = _caso_a()
    sem = _conta(empresa, "3.8", "PL com movimento", PL, C)
    _lancar(empresa, date(2026, 3, 10), "Movimento", contas["caixa"], sem, "10.00")
    return empresa, [
        "Conta 3.8 — PL com movimento: saldo no início do exercício 0,00, "
        "com movimento no exercício.",
        reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, sem.id]),
    ]


def _veto_contrapartida_sem_classificacao():
    empresa, contas, _ = _caso_a()
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Lucros contra o caixa",
        contas["lucros"],
        contas["caixa"],
        "50.00",
    )
    return empresa, [
        "Conta 1.1 — Caixa",
        "coluna afetada: Lucros ou prejuízos acumulados; 1 lançamento(s)",
        "20/03/2026 — Lucros contra o caixa",
        reverse(
            "contabilidade_web:conta_classificacao_dlpa", args=[empresa.id, contas["caixa"].id]
        ),
    ]


def _veto_par_sem_regra():
    empresa, contas, _ = _caso_a()
    estatutaria = _conta(
        empresa,
        "3.8",
        "Reserva Estatutária",
        PL,
        C,
        dmpl=COL.RESERVA_ESTATUTARIA,
        dlpa=ClassificacaoDlpa.RESERVA_ESTATUTARIA,
        pai=contas["pl"],
    )
    _lancar(
        empresa, date(2026, 3, 26), "Entre reservas", contas["reserva_legal"], estatutaria, "100.00"
    )
    return empresa, [
        "Movimento de “Reserva legal” para “Reserva estatutária” (1 lançamento(s))",
        "26/03/2026 — Entre reservas",
    ]


def _veto_lancamento_ambiguo():
    empresa, contas, _ = _caso_a()
    agio = _conta(
        empresa, "3.7", "Ágio", PL, C, dmpl=COL.AGIO_NA_EMISSAO_DE_ACOES, pai=contas["pl"]
    )
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 27),
        "Dois débitos e dois créditos em colunas",
        [
            (contas["lucros"], "D", "100.00"),
            (contas["reserva_legal"], "D", "50.00"),
            (contas["capital"], "C", "70.00"),
            (agio, "C", "80.00"),
        ],
    )
    return empresa, [
        "Lançamento de 27/03/2026 (colunas:",
        "estorne-o e lance de novo cada evento em um lançamento separado",
        reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, ambiguo.id]),
    ]


def _veto_dlpa_e_dmpl_divergentes():
    empresa, contas, _ = _caso_a()
    Conta.objects.filter(pk=contas["reserva_legal"].pk).update(
        classificacao_dmpl=COL.RESERVA_ESTATUTARIA
    )
    return empresa, [
        "Conta 3.2 — Reserva Legal",
        reverse(
            "contabilidade_web:conta_classificacao_dmpl",
            args=[empresa.id, contas["reserva_legal"].id],
        ),
        reverse(
            "contabilidade_web:conta_classificacao_dlpa",
            args=[empresa.id, contas["reserva_legal"].id],
        ),
    ]


def _veto_coluna_desconhecida():
    empresa, contas, _ = _caso_a()
    corrompida = _conta(empresa, "3.9", "Coluna corrompida", PL, C, pai=contas["pl"])
    Conta.objects.filter(pk=corrompida.pk).update(classificacao_dmpl="coluna_inventada")
    return empresa, [
        "Conta 3.9 — Coluna corrompida: a coluna gravada (“coluna_inventada”) não existe mais",
        reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, corrompida.id]),
    ]


def _veto_diferenca_de_fechamento():
    empresa, contas, _ = _caso_a()
    filha = _conta(empresa, "3.2.1", "Reserva Legal - Subconta", PL, C, pai=contas["reserva_legal"])
    _lancar(empresa, date(2026, 3, 30), "Movimento na subconta", contas["caixa"], filha, "500.00")
    return empresa, [
        "Coluna “Reserva legal”: saldo final na DMPL 1.250,00, saldo no Balanço 1.750,00 — "
        "diferença (500,00).",
        "Conta 3.2 — Reserva Legal: saldo no Balanço 1.750,00",
        "Total do patrimônio líquido: soma das colunas na DMPL 115.000,00",
    ]


VETOS = {
    "nenhuma_coluna_classificada": _veto_nenhuma_coluna,
    "contas_do_patrimonio_liquido_sem_coluna": _veto_conta_de_pl_sem_coluna,
    "contrapartidas_sem_classificacao": _veto_contrapartida_sem_classificacao,
    "pares_de_colunas_sem_regra": _veto_par_sem_regra,
    "lancamentos_ambiguos": _veto_lancamento_ambiguo,
    "contas_com_classificacao_dlpa_e_dmpl_divergentes": _veto_dlpa_e_dmpl_divergentes,
    "contas_com_classificacao_dmpl_desconhecida": _veto_coluna_desconhecida,
    "diferenca_de_fechamento": _veto_diferenca_de_fechamento,
}


def test_todas_as_listas_de_pendencia_tem_titulo_acao_e_cenario_de_tela():
    """Derivado: lista nova no serviço sem ação cadastrada na tela, ou sem
    cenário de veto aqui, reprova."""
    chaves = set(_LISTAS_DA_DMPL_QUE_IMPEDEM_A_EMISSAO)
    assert set(views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA) == chaves
    assert set(_TITULOS_DAS_PENDENCIAS_DA_DMPL) == chaves
    assert set(VETOS) == chaves


@pytest.mark.parametrize("lista", sorted(VETOS))
def test_cada_pendencia_veta_a_tela_nomeia_o_que_falta_e_a_acao_que_resolve(client, lista):
    empresa, esperado = VETOS[lista]()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 200, "veto é a tela respondendo, nunca erro de protocolo"
    html = resposta.content.decode()
    assert "A DMPL NÃO pode ser emitida nesta competência" in html
    assert _TITULOS_DAS_PENDENCIAS_DA_DMPL[lista] in html
    acao = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA[lista]
    if lista == "diferenca_de_fechamento":
        # DL-062/G4: o cenário desta lista tem também uma subconta de PL movimentada e sem
        # coluna; com as duas pendências juntas a ação é a que aponta para a conta listada
        # acima (a da retificadora fora do grupo é testada, sozinha, em test_dl062_tela_dmpl).
        acao = views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA
    assert acao.split(" (link")[0] in html
    for trecho in esperado:
        assert trecho in html, (lista, trecho)
    # E a demonstração NÃO é montada: nem tabela, nem total, nem faixa de pronto.
    assert "DMPL pronta para emissão" not in html
    assert "tabela-dmpl" not in html
    assert "identificacao-do-documento" not in html
    assert "100.000,00" not in html


def test_o_veto_nomeia_cada_lista_pendente_ao_mesmo_tempo_sem_esconder_nenhuma(client):
    empresa, contas, _ = _caso_a()
    sem = _conta(empresa, "3.8", "Reserva Não Classificada", PL, C, pai=contas["pl"])
    _lancar(
        empresa, date(2026, 3, 24), "Destinação sem classificação", contas["lucros"], sem, "44.00"
    )
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert _TITULOS_DAS_PENDENCIAS_DA_DMPL["contas_do_patrimonio_liquido_sem_coluna"] in html
    assert _TITULOS_DAS_PENDENCIAS_DA_DMPL["contrapartidas_sem_classificacao"] in html
    assert "Reserva Não Classificada" in html


@pytest.mark.parametrize("papel", PAPEIS_QUE_LEEM)
def test_link_de_correcao_do_veto_so_aparece_para_quem_escritura(client, papel):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    _entrar(client, empresa, papel)
    html = client.get(_url(empresa)).content.decode()
    link = esperado[1]
    assert "Conta 3.8 — PL com movimento" in html, "a pendência aparece para todo papel que lê"
    if papel in PAPEIS_QUE_ESCRITURAM:
        assert link in html and "definir a coluna da DMPL" in html
    else:
        assert link not in html and "definir a coluna da DMPL" not in html
        assert "peça a quem escritura" in _texto(html), (
            "quem só lê vê o que fazer: falar com quem escritura"
        )


def test_link_de_conferencia_do_lancamento_aparece_para_quem_so_le(client):
    empresa, esperado = _veto_lancamento_ambiguo()
    _entrar(client, empresa, Papel.PARALEGAL)
    html = client.get(_url(empresa)).content.decode()
    assert esperado[-1] in html, "abrir o lançamento é leitura, não correção"


def test_o_veto_lista_so_alguns_lancamentos_por_extenso_e_conta_o_resto(client):
    empresa, contas, _ = _caso_a()
    for dia in range(1, 8):
        _lancar(
            empresa,
            date(2026, 3, dia),
            f"Lucros contra caixa {dia}",
            contas["lucros"],
            contas["caixa"],
            "1.00",
        )
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "7 lançamento(s)" in html
    assert "e mais 2 lançamento(s); veja o Diário." in html


# ---------------------------------------------------------------------------
# Classificar a coluna (porta de tela do plano de contas)
# ---------------------------------------------------------------------------


def _url_classificar(empresa, conta):
    return reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, conta.id])


def test_classificacao_get_mostra_a_coluna_atual_as_opcoes_agrupadas_e_o_aviso(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.get(_url_classificar(empresa, contas["reserva_legal"]))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Coluna atual: <strong>Reserva legal</strong>" in html
    for grupo in (
        "Capital social",
        "Reservas de capital",
        "Ajustes de avaliação patrimonial",
        "Reservas de lucros",
        "Ações ou quotas em tesouraria",
        "Lucros ou prejuízos acumulados",
    ):
        assert f'<optgroup label="{grupo}">' in html, grupo
    assert '<option value="reserva_legal" selected>Reserva legal</option>' in html
    assert "Sem coluna na DMPL" in html
    assert "não altera nenhum saldo" in _texto(html)


def test_classificacao_post_grava_a_coluna_com_trilha_de_antes_e_depois(client):
    empresa, contas, _ = _caso_a()
    nova = _conta(empresa, "3.8", "Reserva Estatutária", PL, C, pai=contas["pl"])
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, nova), {"classificacao_dmpl": COL.RESERVA_ESTATUTARIA}
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    nova.refresh_from_db()
    assert nova.classificacao_dmpl == COL.RESERVA_ESTATUTARIA
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dmpl_alterada", objeto_id=str(nova.pk)
    ).get()
    assert registro.detalhes["classificacao_dmpl_antes"] is None
    assert registro.detalhes["classificacao_dmpl_depois"] == COL.RESERVA_ESTATUTARIA


def test_classificacao_post_remover_volta_para_nenhuma_e_registra(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.post(_url_classificar(empresa, contas["capital"]), {"classificacao_dmpl": ""})
    # A DLPA da conta (lucro incorporado ao capital) não exige coluna: remover é aceito.
    assert resposta.status_code == 302
    contas["capital"].refresh_from_db()
    assert contas["capital"].classificacao_dmpl is None
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dmpl_alterada", objeto_id=str(contas["capital"].pk)
    ).get()
    assert registro.detalhes["classificacao_dmpl_antes"] == COL.CAPITAL_SOCIAL
    assert registro.detalhes["classificacao_dmpl_depois"] is None


def test_classificacao_de_conta_que_nao_e_de_patrimonio_liquido_e_recusada_sem_gravar(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, contas["caixa"]), {"classificacao_dmpl": COL.CAPITAL_SOCIAL}
    )
    assert resposta.status_code == 200, "recusa de regra é a tela respondendo, nunca um 500"
    assert 'role="alert"' in resposta.content.decode()
    contas["caixa"].refresh_from_db()
    assert contas["caixa"].classificacao_dmpl is None
    assert not RegistroAuditoria.objects.filter(acao="conta.classificacao_dmpl_alterada").exists()


def test_classificacao_divergente_da_dlpa_e_recusada_e_o_valor_gravado_permanece(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, contas["reserva_legal"]),
        {"classificacao_dmpl": COL.RESERVA_ESTATUTARIA},
    )
    assert resposta.status_code == 200
    contas["reserva_legal"].refresh_from_db()
    assert contas["reserva_legal"].classificacao_dmpl == COL.RESERVA_LEGAL
    assert "Coluna atual: <strong>Reserva legal</strong>" in resposta.content.decode()


def test_classificacao_com_valor_fora_das_opcoes_e_recusada_no_formulario(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, contas["capital"]), {"classificacao_dmpl": "coluna_inventada"}
    )
    assert resposta.status_code == 200
    contas["capital"].refresh_from_db()
    assert contas["capital"].classificacao_dmpl == COL.CAPITAL_SOCIAL


def test_classificacao_campo_extra_no_corpo_recebe_400_e_nada_e_gravado(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, contas["capital"]),
        {"classificacao_dmpl": "", "xpto": "1"},
    )
    assert resposta.status_code == 400
    contas["capital"].refresh_from_db()
    assert contas["capital"].classificacao_dmpl == COL.CAPITAL_SOCIAL


@pytest.mark.parametrize("papel", (Papel.PARALEGAL, Papel.CLIENTE))
def test_classificacao_sem_permissao_de_escriturar_recebe_403_no_get_e_no_post(client, papel):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa, papel)
    url = _url_classificar(empresa, contas["capital"])
    assert client.get(url).status_code == 403
    resposta = client.post(url, {"classificacao_dmpl": ""})
    assert resposta.status_code == 403
    assert "Seu papel não permite classificar a coluna da DMPL" in resposta.content.decode()
    contas["capital"].refresh_from_db()
    assert contas["capital"].classificacao_dmpl == COL.CAPITAL_SOCIAL


@pytest.mark.parametrize("papel", (Papel.ANALISTA, Papel.FINANCEIRO))
def test_quem_escritura_classifica_mesmo_sem_gerir_parametro(client, papel):
    empresa, contas, _ = _caso_a()
    nova = _conta(empresa, "3.8", "Reserva Estatutária", PL, C, pai=contas["pl"])
    _entrar(client, empresa, papel)
    resposta = client.post(
        _url_classificar(empresa, nova), {"classificacao_dmpl": COL.RESERVA_ESTATUTARIA}
    )
    assert resposta.status_code == 302


def test_classificacao_de_conta_de_outra_empresa_do_mesmo_escritorio_da_404(client):
    empresa, contas, _ = _caso_a()
    outra = Empresa.objects.create(
        escritorio=empresa.escritorio,
        razao_social="Outra do mesmo escritório",
        cnpj=_cnpj_sintetico(),
    )
    _entrar(client, empresa)
    url = reverse(
        "contabilidade_web:conta_classificacao_dmpl", args=[outra.id, contas["capital"].id]
    )
    assert client.get(url).status_code == 404
    assert client.post(url, {"classificacao_dmpl": ""}).status_code == 404
    contas["capital"].refresh_from_db()
    assert contas["capital"].classificacao_dmpl == COL.CAPITAL_SOCIAL


def test_classificacao_de_conta_de_outro_escritorio_da_404(client):
    empresa, contas, _ = _caso_a()
    outro = Escritorio.objects.create(
        nome="Outro Escritório Classifica DMPL", cnpj=_cnpj_sintetico()
    )
    _autenticar(client, outro, "gestor-outro-classifica-dmpl")
    assert client.get(_url_classificar(empresa, contas["capital"])).status_code == 404


def test_a_classificacao_feita_na_tela_muda_a_dmpl_emitida(client):
    """Ponta a ponta: o veto aponta a conta, a tela classifica, a DMPL emite
    — com a coluna nova e a linha certa (lucros para reserva)."""
    empresa, contas, _ = _caso_a()
    nova = _conta(empresa, "3.8", "Reserva Estatutária", PL, C, pai=contas["pl"])
    _lancar(empresa, date(2026, 3, 31), "Estatutária", contas["lucros"], nova, "100.00")
    _entrar(client, empresa)
    assert "A DMPL NÃO pode ser emitida" in client.get(_url(empresa)).content.decode()
    resposta = client.post(
        _url_classificar(empresa, nova), {"classificacao_dmpl": COL.RESERVA_ESTATUTARIA}
    )
    assert resposta.status_code == 302
    html = client.get(_url(empresa)).content.decode()
    assert "DMPL pronta para emissão" in html
    linhas = {linha[0]: linha for linha in _linhas_da_tabela(html)}
    assert linhas["Saldo no fim do período"][-1] == "115.000,00"
    assert "100,00" in "".join(linhas["Constituição de reservas"])


# ---------------------------------------------------------------------------
# Plano de contas, hub de relatórios e menu
# ---------------------------------------------------------------------------


def test_plano_de_contas_mostra_a_coluna_e_o_botao_so_para_conta_de_pl(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()
    assert '<th scope="col">Coluna da DMPL</th>' in html
    assert "<td>Reserva legal</td>" in html
    assert _url_classificar(empresa, contas["capital"]) in html
    assert _url_classificar(empresa, contas["caixa"]) not in html, "ativo não tem coluna na DMPL"
    assert _url_classificar(empresa, contas["receita"]) not in html


def test_plano_de_contas_nao_oferece_o_botao_a_quem_so_le(client):
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa, Papel.PARALEGAL)
    html = client.get(
        reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    ).content.decode()
    assert "Coluna da DMPL" in html, "a coluna cadastrada é leitura"
    assert _url_classificar(empresa, contas["capital"]) not in html


def test_dmpl_aparece_no_hub_de_relatorios_e_no_menu_lateral(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(reverse("contabilidade_web:relatorios", args=[empresa.id])).content.decode()
    assert reverse("contabilidade_web:dmpl", args=[empresa.id]) in html, "cartão ausente do hub"
    assert "#icone-dmpl" in html and 'id="icone-dmpl"' in html, "ícone ausente do sprite"
    assert ">DMPL</a>" in html, "item de menu ausente"


def test_no_menu_a_propria_tela_e_texto_e_nao_link(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert '<span class="item-atual" aria-current="page">DMPL</span>' in html
    assert f'href="{reverse("contabilidade_web:dmpl", args=[empresa.id])}">DMPL</a>' not in html


# ---------------------------------------------------------------------------
# Marca de adoção antecipada da NBC TG 51 (tela de parâmetros contábeis)
# ---------------------------------------------------------------------------


def _url_parametros(empresa):
    return reverse("contabilidade_web:parametros_contabeis", args=[empresa.id])


def _vigencia(empresa):
    return ParametroContabilEmpresa.objects.get(empresa=empresa)


def _marcar(client, empresa, adota="1", **extra):
    corpo = {
        "acao": "adocao_antecipada_nbc_tg_51",
        "vigencia_id": str(_vigencia(empresa).id),
        "adota": adota,
    }
    corpo.update(extra)
    return client.post(_url_parametros(empresa), corpo)


def test_a_tela_de_parametros_mostra_a_marca_e_oferece_marcar_ao_gestor(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url_parametros(empresa)).content.decode()
    assert '<th scope="col">NBC TG 51 antecipada</th>' in html
    assert "Marcar adoção antecipada" in html and "Desmarcar adoção antecipada" not in html
    assert "só decide qual norma as demonstrações citam" in _texto(html)
    assert "não muda saldo" in html


def test_marcar_grava_com_trilha_e_a_dmpl_passa_a_citar_a_nbc_tg_51(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    resposta = _marcar(client, empresa, "1")
    assert resposta.status_code == 302
    assert resposta.url == _url_parametros(empresa)
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is True
    registro = RegistroAuditoria.objects.get(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    )
    assert registro.detalhes["adota_nbc_tg_51_antecipadamente_antes"] is False
    assert registro.detalhes["adota_nbc_tg_51_antecipadamente_depois"] is True
    # A mensagem diz o efeito, e a tela passa a mostrar a marca e o botão inverso.
    pagina = client.get(_url_parametros(empresa)).content.decode()
    assert "Desmarcar adoção antecipada" in pagina and "Marcar adoção antecipada" not in pagina
    assert "<strong>Sim</strong>" in pagina
    # E o efeito real, na demonstração.
    assert "Base normativa: NBC TG 51" in client.get(_url(empresa)).content.decode()


def test_a_mensagem_de_sucesso_diz_o_efeito_da_marca(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    pagina = client.post(
        _url_parametros(empresa),
        {
            "acao": "adocao_antecipada_nbc_tg_51",
            "vigencia_id": str(_vigencia(empresa).id),
            "adota": "1",
        },
        follow=True,
    ).content.decode()
    assert "Adoção antecipada da NBC TG 51 marcada na vigência iniciada em 01/01/2026" in pagina
    assert "passam a citar a NBC TG 51 em vez da NBC TG 26 (R5)" in pagina
    assert "Nenhum saldo nem lançamento muda" in pagina


def test_desmarcar_volta_a_nbc_tg_26_r5_e_registra_a_segunda_alteracao(client):
    empresa, _, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    _entrar(client, empresa, Papel.GESTOR)
    pagina = client.post(
        _url_parametros(empresa),
        {
            "acao": "adocao_antecipada_nbc_tg_51",
            "vigencia_id": str(_vigencia(empresa).id),
            "adota": "0",
        },
        follow=True,
    ).content.decode()
    assert "desmarcada na vigência iniciada em 01/01/2026" in pagina
    assert "voltam a citar a NBC TG 26 (R5)" in pagina
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False
    assert (
        RegistroAuditoria.objects.filter(
            acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
        ).count()
        == 2
    )
    assert "Base normativa: NBC TG 26 (R5)" in client.get(_url(empresa)).content.decode()


def test_marcar_de_novo_nao_grava_nem_registra_outra_trilha(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    _marcar(client, empresa, "1")
    pagina = client.post(
        _url_parametros(empresa),
        {
            "acao": "adocao_antecipada_nbc_tg_51",
            "vigencia_id": str(_vigencia(empresa).id),
            "adota": "1",
        },
        follow=True,
    ).content.decode()
    assert "já estava marcada: nada foi alterado" in pagina
    assert (
        RegistroAuditoria.objects.filter(
            acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
        ).count()
        == 1
    )


@pytest.mark.parametrize(
    "papel", (Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE)
)
def test_quem_nao_gere_parametro_recebe_403_e_nada_e_gravado(client, papel):
    """A marca segue a regra DA TELA de parâmetros (administrador ou gestor),
    não a de classificar conta: analista e financeiro escrituram e, ainda
    assim, não marcam. Mutação típica: trocar a checagem por `_pode_escriturar`."""
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, papel)
    resposta = _marcar(client, empresa, "1")
    assert resposta.status_code == 403
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False
    assert not RegistroAuditoria.objects.filter(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    ).exists()


@pytest.mark.parametrize("papel", PAPEIS_QUE_GEREM_PARAMETRO)
def test_administrador_e_gestor_marcam(client, papel):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, papel)
    assert _marcar(client, empresa, "1").status_code == 302
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is True


def test_quem_so_le_ve_a_marca_mas_nao_o_botao(client):
    empresa, _, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    _entrar(client, empresa, Papel.ANALISTA)
    html = client.get(_url_parametros(empresa)).content.decode()
    assert "<strong>Sim</strong>" in html
    assert "Marcar adoção antecipada" not in html and "Desmarcar adoção antecipada" not in html


def test_vigencia_de_outra_empresa_da_404_e_nao_altera_nada(client):
    empresa, _, _ = _caso_a()
    outra, _, _ = _caso_a(_empresa("Outra com Parâmetro Ltda"))
    _entrar(client, empresa, Papel.GESTOR)
    resposta = client.post(
        _url_parametros(empresa),
        {
            "acao": "adocao_antecipada_nbc_tg_51",
            "vigencia_id": str(_vigencia(outra).id),
            "adota": "1",
        },
    )
    assert resposta.status_code == 404
    assert _vigencia(outra).adota_nbc_tg_51_antecipadamente is False


@pytest.mark.parametrize(
    "corpo",
    (
        {"adota": "talvez"},
        {"adota": ""},
        {"vigencia_id": "abc"},
        {"vigencia_id": ""},
    ),
)
def test_valor_invalido_da_marca_e_recusado_com_mensagem_sem_alterar(client, corpo):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    base = {
        "acao": "adocao_antecipada_nbc_tg_51",
        "vigencia_id": str(_vigencia(empresa).id),
        "adota": "1",
    }
    base.update(corpo)
    resposta = client.post(_url_parametros(empresa), base, follow=True)
    assert resposta.status_code == 200
    assert "nada foi alterado" in resposta.content.decode()
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False


def test_campo_extra_na_marca_e_recusado_pelo_contrato_sem_alterar(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    resposta = _marcar(client, empresa, "1", xpto="1")
    assert resposta.status_code == 302
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False
    assert not RegistroAuditoria.objects.filter(
        acao="parametro_contabil.adocao_antecipada_nbc_tg_51_alterada"
    ).exists()


def test_o_registro_de_vigencia_continua_funcionando_sem_o_campo_acao(client):
    """A marca é uma ação extra da MESMA URL: o formulário de nova vigência,
    que não manda `acao`, segue seu caminho de sempre e HERDA a marca."""
    empresa, contas, gestor = _caso_a()
    definir_adocao_antecipada_da_nbc_tg_51(
        empresa=empresa, data_inicio_exercicio=date(2026, 1, 1), adota=True, usuario=gestor
    )
    _entrar(client, empresa, Papel.GESTOR)
    resposta = client.post(
        _url_parametros(empresa),
        {
            "periodicidade_zeramento": "mensal",
            "conta_resultado_do_exercicio": contas["resultado"].id,
            "conta_lucros_acumulados": contas["lucros"].id,
            "conta_prejuizos_acumulados": contas["prejuizos"].id,
            "vigencia_inicio": "2027-01-01",
        },
    )
    assert resposta.status_code == 302
    nova = (
        ParametroContabilEmpresa.objects.filter(empresa=empresa)
        .order_by("-vigencia_inicio")
        .first()
    )
    assert nova.vigencia_inicio == date(2027, 1, 1)
    assert nova.adota_nbc_tg_51_antecipadamente is True


def test_marcar_uma_vigencia_encerrada_vale_para_o_exercicio_que_ela_cobre(client):
    """O caso comum: o exercício de 2026 está numa vigência já encerrada
    (porque uma nova abriu em 2027). A marca nela muda a norma de 2026, não a
    de 2027."""
    empresa, contas, gestor = _caso_a()
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2027, 1, 1),
        usuario=gestor,
    )
    antiga = ParametroContabilEmpresa.objects.get(empresa=empresa, vigencia_inicio=date(2026, 1, 1))
    assert antiga.vigencia_fim == date(2026, 12, 31)
    _entrar(client, empresa, Papel.GESTOR)
    pagina = client.get(_url_parametros(empresa)).content.decode()
    assert pagina.count("Marcar adoção antecipada") == 2, "uma por vigência, aberta ou encerrada"
    resposta = client.post(
        _url_parametros(empresa),
        {"acao": "adocao_antecipada_nbc_tg_51", "vigencia_id": str(antiga.id), "adota": "1"},
    )
    assert resposta.status_code == 302
    assert "Base normativa: NBC TG 51" in client.get(_url(empresa, ano=2026)).content.decode()
    assert "Adoção antecipada" in client.get(_url(empresa, ano=2026)).content.decode()
    assert "Base normativa: NBC TG 51" in client.get(_url(empresa, ano=2027)).content.decode()
    assert "Adoção antecipada" not in client.get(_url(empresa, ano=2027)).content.decode()
