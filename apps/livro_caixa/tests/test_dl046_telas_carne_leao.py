"""DL-046, fatia 2 — telas do carnê-leão (`especialista-frontend`).

Cobre: renderização do demonstrativo MENSAL com a memória de cálculo,
demonstrativo ANUAL (12 meses + totais), qual forma foi aplicada (real x
simplificado), isolamento entre empresas/escritórios (404), recusa para
empresa em modo contabilidade (403), papel sem permissão (403), formulário
de dependentes (sucesso, erro, sem permissão), e número de consultas
CONSTANTE em relação ao volume de lançamentos/meses.

O motor (`apps.livro_caixa.carne_leao`) já tem suíte própria
(`test_dl046_fatia2_carne_leao.py`) com os casos de referência calculados à
mão — este arquivo testa só a TELA: que ela apresenta o que o motor devolve,
sem recalcular nada, e que os cinco estados (vazio, carregando — não
aplicável a uma view síncrona —, erro, sucesso, sem permissão) existem.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, ModoEscrituracao, TipoInscricao
from apps.livro_caixa.models import ContaLivroCaixa, DependentesCarneLeaoCliente, NaturezaCaixa
from apps.livro_caixa.services import criar_lancamento_caixa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_CLIENTE_A = "11144477735"
CPF_CLIENTE_B = "22255588846"


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel=Papel.GESTOR, username="gestor-cl"):
    _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")


@pytest.fixture
def cenario():
    escritorio_a = Escritorio.objects.create(nome="Escritório Carnê-Leão A", cnpj="77788899000111")
    escritorio_b = Escritorio.objects.create(nome="Escritório Carnê-Leão B", cnpj="77788899000222")
    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano de Tal — Carnê-Leão",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_CLIENTE_A,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
        caepf="11144477735001",
    )
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Ciclano de Tal — Carnê-Leão",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_CLIENTE_B,
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    empresa_contabilidade = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Empresa Contabilidade Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.CONTABILIDADE,
    )
    conta_receita = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="R1",
        nome="Aluguel recebido",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.003.001",
    )
    conta_trabalho = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="RT",
        nome="Trabalho não assalariado",
        natureza=NaturezaCaixa.RECEITA,
        codigo_carne_leao="R01.001.001",
    )
    conta_imposto_exterior = ContaLivroCaixa.objects.create(
        empresa=empresa_a,
        codigo="DEXT",
        nome="Imposto pago no exterior",
        natureza=NaturezaCaixa.DESPESA,
        codigo_carne_leao="P20.01.00003",
    )
    return {
        "escritorio_a": escritorio_a,
        "escritorio_b": escritorio_b,
        "empresa_a": empresa_a,
        "empresa_b": empresa_b,
        "empresa_contabilidade": empresa_contabilidade,
        "conta_receita": conta_receita,
        "conta_trabalho": conta_trabalho,
        "conta_imposto_exterior": conta_imposto_exterior,
    }


def _lancar_receita(empresa, conta, valor, dia=None):
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=dia or date(2026, 3, 15),
        valor=Decimal(valor),
        historico="Aluguel recebido — teste de tela",
        recebido_de="PF",
    )


def _lancar_trabalho(empresa, conta, dia, valor, *, recebido_de="PF", cnpj_pagador=""):
    """Mesmo padrão de `_lancar_trabalho`/`_lancar_trabalho_pj`
    (test_dl046_fatia2_carne_leao.py) — o modelo de trabalho não
    assalariado exige titular OU indicador de beneficiário não informado
    quando PF; PJ exige CNPJ do pagador."""
    kwargs = {"cpf_titular_pagamento": CPF_CLIENTE_A, "cpf_beneficiario_nao_informado": True}
    if recebido_de == "PJ":
        kwargs = {"cnpj_pagador": cnpj_pagador or "11222333000181"}
    return criar_lancamento_caixa(
        empresa=empresa,
        conta=conta,
        data=dia,
        valor=Decimal(valor),
        historico="Honorários — teste de tela",
        recebido_de=recebido_de,
        **kwargs,
    )


def _lancar_despesa(empresa, conta, dia, valor, historico="Despesa — teste de tela"):
    return criar_lancamento_caixa(
        empresa=empresa, conta=conta, data=dia, valor=Decimal(valor), historico=historico
    )


# ---------------------------------------------------------------------------
# Demonstrativo MENSAL — sucesso, memória de cálculo, forma aplicada.
# ---------------------------------------------------------------------------


def test_carne_leao_mensal_renderiza_a_memoria_de_calculo(client, cenario):
    """Mês com rendimento alto o bastante para gerar imposto: a tela mostra
    a memória de cálculo completa, o bloco de identificação do documento
    (nome, CPF, CAEPF, base legal) e a linha do DARF/vencimento."""
    _autenticar(client, cenario["escritorio_a"])
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "20000.00", date(2026, 3, 10))

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    assert resposta.status_code == 200
    assert "livro_caixa/carne_leao_mensal.html" in [t.name for t in resposta.templates]
    html = resposta.content.decode()

    # Identificação do documento (nome, CPF, CAEPF, base legal) — presente
    # mesmo sem imprimir (o marcador é o mesmo do Livro Caixa).
    assert "identificacao-do-documento" in html
    assert "Fulano de Tal" in html
    assert "111.444.777-35" in html
    assert "11144477735001" in html
    assert "RIR/2018" in html
    assert "Lei nº 15.270/2025" in html

    # Memória de cálculo — rótulos e o valor bruto usado pela redução,
    # explicitamente marcado como BRUTO (RC-133).
    assert "Rendimentos sujeitos ao carnê-leão" in html
    assert "Deduções reais" in html
    assert "Desconto simplificado" in html
    assert "Calculada sobre o rendimento tributável BRUTO" in html
    assert "20.000,00" in html

    # Resultado do mês, código do DARF e vencimento (mês SEGUINTE, texto
    # literal "último dia útil", sem resolver o dia exato).
    assert "0190" in html
    assert "Último dia útil de 04/2026" in html


def test_carne_leao_mensal_marca_a_forma_aplicada_com_selo(client, cenario):
    """Sem nenhuma dedução real lançada, o desconto simplificado (sempre
    positivo) é estritamente mais benéfico que zero de dedução real — a
    tela marca "Aplicada" na linha do desconto simplificado, nunca nas
    deduções reais."""
    _autenticar(client, cenario["escritorio_a"])
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "20000.00", date(2026, 3, 10))

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    html = resposta.content.decode()
    inicio_simplificado = html.find("via do desconto SIMPLIFICADO")
    inicio_reais = html.find("via das deduções REAIS")
    assert inicio_simplificado != -1 and inicio_reais != -1
    # A linha do desconto simplificado carrega o selo "Aplicada"; a das
    # deduções reais, não — procurando o selo só até a próxima linha
    # ("Forma aplicada neste mês").
    fim_bloco = html.find("Forma aplicada neste mês")
    bloco_simplificado = html[inicio_simplificado:fim_bloco]
    bloco_reais = html[inicio_reais:inicio_simplificado]
    assert '<span class="selo">Aplicada</span>' in bloco_simplificado
    assert '<span class="selo">Aplicada</span>' not in bloco_reais
    # "Forma aplicada neste mês" nomeia por extenso qual das duas venceu.
    assert "Desconto simplificado" in html[fim_bloco : fim_bloco + 600]


def test_carne_leao_mensal_sem_movimento_mostra_aviso_de_estado(client, cenario):
    """Mês sem nenhum lançamento: a memória de cálculo continua saindo
    (com zeros), e um aviso de estado (não de erro) explica a ausência de
    movimento — nenhuma informação contábil é escondida."""
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Nenhum rendimento sujeito ao carnê-leão" in html
    assert "0,00" in html
    assert "Nenhum valor a pagar nesta competência." in html


def test_carne_leao_mensal_competencia_invalida_mostra_estado_de_erro(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "abc", "mes": "3"},
    )
    assert resposta.status_code == 400
    assert "livro_caixa/carne_leao_mensal.html" in [t.name for t in resposta.templates]
    assert "competência padrão" in resposta.content.decode()


def test_carne_leao_mensal_navegacao_de_competencia(client, cenario):
    """‹ Mês anterior / Mês seguinte › apontam para a competência
    adjacente — mesmo padrão da DRE."""
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    html = resposta.content.decode()
    assert "ano=2026&amp;mes=2" in html or "ano=2026&mes=2" in html
    assert "ano=2026&amp;mes=4" in html or "ano=2026&mes=4" in html


# ---------------------------------------------------------------------------
# Demonstrativo ANUAL — 12 meses + totais.
# ---------------------------------------------------------------------------


def test_carne_leao_anual_renderiza_os_doze_meses_e_totais(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "20000.00", date(2026, 3, 10))
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "5000.00", date(2026, 7, 5))

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_anual", args=[cenario["empresa_a"].id]),
        {"ano": "2026"},
    )
    assert resposta.status_code == 200
    assert "livro_caixa/carne_leao_anual.html" in [t.name for t in resposta.templates]
    html = resposta.content.decode()

    for mes_nome in ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho"]:
        assert mes_nome in html
    assert "Total do ano" in html
    # O total de rendimento sujeito soma exatamente os dois lançamentos —
    # nenhum cálculo tributário novo, só soma de apresentação (25.000,00).
    assert "25.000,00" in html


def test_carne_leao_anual_ano_invalido_mostra_estado_de_erro(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_anual", args=[cenario["empresa_a"].id]),
        {"ano": "99999"},
    )
    assert resposta.status_code == 400
    assert "ano padrão" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Isolamento entre empresas/escritórios.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_da_rota",
    ["carne_leao_mensal", "carne_leao_anual", "dependentes_carne_leao"],
)
def test_isolamento_entre_escritorios_da_404(client, cenario, nome_da_rota):
    """O escritório A nunca alcança a empresa do escritório B pelas telas
    do carnê-leão — mesma garantia de isolamento das demais telas do
    livro-caixa (`_empresa_do_escritorio_ativo`, `get_object_or_404`)."""
    _autenticar(client, cenario["escritorio_a"])
    url = reverse(f"livro_caixa_web:{nome_da_rota}", args=[cenario["empresa_b"].id])
    resposta = client.get(url)
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Recusa para cliente em modo CONTABILIDADE.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_da_rota",
    ["carne_leao_mensal", "carne_leao_anual", "dependentes_carne_leao"],
)
def test_recusa_para_empresa_em_modo_contabilidade(client, cenario, nome_da_rota):
    _autenticar(client, cenario["escritorio_a"])
    resposta = client.get(
        reverse(f"livro_caixa_web:{nome_da_rota}", args=[cenario["empresa_contabilidade"].id])
    )
    assert resposta.status_code == 403
    html = resposta.content.decode()
    assert "não está em modo" in html or "livro-caixa" in html


# ---------------------------------------------------------------------------
# Papel sem permissão de leitura (CLIENTE não lê livro-caixa nenhum).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_da_rota",
    ["carne_leao_mensal", "carne_leao_anual", "dependentes_carne_leao"],
)
def test_papel_sem_permissao_de_leitura_e_recusado(client, cenario, nome_da_rota):
    _autenticar(client, cenario["escritorio_a"], papel=Papel.CLIENTE, username="cliente-cl")
    url = reverse(f"livro_caixa_web:{nome_da_rota}", args=[cenario["empresa_a"].id])
    resposta = client.get(url)
    assert resposta.status_code == 403


# ---------------------------------------------------------------------------
# Formulário de dependentes — sucesso, erro, sem permissão de escrita.
# ---------------------------------------------------------------------------


def test_dependentes_formulario_sucesso(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    url = reverse("livro_caixa_web:dependentes_carne_leao", args=[cenario["empresa_a"].id])
    resposta = client.post(url, {"quantidade": "2", "competencia_inicio": "2026-10-01"})
    assert resposta.status_code == 302
    assert DependentesCarneLeaoCliente.objects.filter(
        empresa=cenario["empresa_a"], quantidade=2, competencia_inicio=date(2026, 10, 1)
    ).exists()

    seguindo = client.get(url)
    assert "2" in seguindo.content.decode()


def test_dependentes_formulario_erro_dia_diferente_de_um(client, cenario):
    """Dia diferente de 1: o formulário NÃO grava nada, some com o texto
    digitado (o formulário não some — Django ModelForm reexibe o que foi
    enviado) e mostra o erro no campo certo."""
    _autenticar(client, cenario["escritorio_a"])
    url = reverse("livro_caixa_web:dependentes_carne_leao", args=[cenario["empresa_a"].id])
    resposta = client.post(url, {"quantidade": "4", "competencia_inicio": "2026-10-15"})
    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert "primeiro dia de um mês" in html
    assert not DependentesCarneLeaoCliente.objects.filter(empresa=cenario["empresa_a"]).exists()
    # O que a pessoa digitou continua no formulário (arquétipo B, §2).
    assert 'value="4"' in html


def test_dependentes_formulario_sem_permissao_de_escrita(client, cenario):
    """PARALEGAL lê o carnê-leão, mas não pode registrar dependentes — o
    GET mostra a tabela sem formulário; o POST é recusado (403) mesmo que
    alguém force a requisição."""
    _autenticar(client, cenario["escritorio_a"], papel=Papel.PARALEGAL, username="paralegal-cl")
    url = reverse("livro_caixa_web:dependentes_carne_leao", args=[cenario["empresa_a"].id])

    consulta = client.get(url)
    assert consulta.status_code == 200
    html_da_consulta = consulta.content.decode()
    # Existe SEMPRE um formulário de logout na moldura (base.html) — a
    # ausência que importa é a do FORMULÁRIO DE REGISTRO, identificado
    # pelo próprio título que só ele carrega.
    assert "Registrar nova vigência" not in html_da_consulta

    forcado = client.post(url, {"quantidade": "2", "competencia_inicio": "2026-10-01"})
    assert forcado.status_code == 403
    assert not DependentesCarneLeaoCliente.objects.filter(empresa=cenario["empresa_a"]).exists()


# ---------------------------------------------------------------------------
# Número de consultas CONSTANTE.
# ---------------------------------------------------------------------------


def test_carne_leao_mensal_numero_de_consultas_e_constante(client, cenario):
    """O motor (`_apurar_ano_calendario`) já garante número de consultas
    constante em relação ao número de lançamentos — esta guarda prova que
    a TELA não soma nenhuma consulta própria por lançamento (ex.: um
    template que percorresse item a item fazendo uma consulta cada)."""
    _autenticar(client, cenario["escritorio_a"])
    url = reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id])

    for dia in range(1, 4):
        _lancar_receita(
            cenario["empresa_a"], cenario["conta_receita"], "100.00", date(2026, 3, dia)
        )
    # Aquecimento (mesmo padrão de test_dl015_saidas_com_periodo.py): a
    # PRIMEIRA requisição paga custo único (cache de ContentType, sessão
    # etc.) que não tem relação com o volume de lançamentos — sem esta
    # chamada extra, comparar a primeira captura "a frio" contra a segunda
    # "aquecida" mediria o aquecimento, não o efeito do volume.
    client.get(url, {"ano": "2026", "mes": "3"})
    with CaptureQueriesContext(connection) as poucos:
        resposta_poucos = client.get(url, {"ano": "2026", "mes": "3"})
    assert resposta_poucos.status_code == 200

    for dia in range(4, 25):
        _lancar_receita(
            cenario["empresa_a"], cenario["conta_receita"], "100.00", date(2026, 3, dia)
        )
    with CaptureQueriesContext(connection) as muitos:
        resposta_muitos = client.get(url, {"ano": "2026", "mes": "3"})
    assert resposta_muitos.status_code == 200

    assert len(muitos.captured_queries) == len(poucos.captured_queries)


def test_carne_leao_anual_numero_de_consultas_e_constante(client, cenario):
    """Mesma garantia, comparando um mês só de lançamentos contra NOVE
    meses do ano — o demonstrativo anual não soma uma consulta por mês.

    ⚠️ Só até o mês 9: `criar_lancamento_caixa` recusa data futura além de
    "hoje + 30 dias" (mesma faixa da contabilidade, por analogia) — meses
    além do corrente cairiam fora da faixa aceita dependendo da data em
    que a suíte roda. Nove meses de dados já bastam para provar que o
    número de consultas não cresce por mês."""
    _autenticar(client, cenario["escritorio_a"])
    url = reverse("livro_caixa_web:carne_leao_anual", args=[cenario["empresa_a"].id])

    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "1000.00", date(2026, 3, 10))
    # Aquecimento — mesmo motivo do teste mensal, acima.
    client.get(url, {"ano": "2026"})
    with CaptureQueriesContext(connection) as um_mes:
        resposta_um_mes = client.get(url, {"ano": "2026"})
    assert resposta_um_mes.status_code == 200

    for mes in range(1, 9):
        _lancar_receita(
            cenario["empresa_a"], cenario["conta_receita"], "1000.00", date(2026, mes, 5)
        )
    with CaptureQueriesContext(connection) as varios_meses:
        resposta_varios_meses = client.get(url, {"ano": "2026"})
    assert resposta_varios_meses.status_code == 200

    assert len(varios_meses.captured_queries) == len(um_mes.captured_queries)


# ---------------------------------------------------------------------------
# Integração de 2026-09-27 (DE-091, motor corrigido) — contrato novo:
# rendimentos por código/origem, faixa aplicada, critério de escolha
# pronto do motor, imposto com/sem exterior, ImpostoExteriorSemRendimento
# Exterior, e retificação de dependentes.
# ---------------------------------------------------------------------------


def test_carne_leao_mensal_mostra_rendimentos_por_codigo_e_origem(client, cenario):
    """`rendimentos` (item 7/M-2 do contrato) — um item por (código,
    origem), com o motivo de exclusão quando não entra na base (aqui,
    trabalho não assalariado recebido de PJ)."""
    _autenticar(client, cenario["escritorio_a"])
    _lancar_trabalho(cenario["empresa_a"], cenario["conta_trabalho"], date(2026, 3, 10), "2000.00")
    _lancar_trabalho(
        cenario["empresa_a"],
        cenario["conta_trabalho"],
        date(2026, 3, 11),
        "1000.00",
        recebido_de="PJ",
    )

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "R01.001.001" in html
    assert "Pessoa física" in html
    assert "Pessoa jurídica" in html
    assert "Não integra a base" in html
    assert "retenção na fonte" in html


def test_carne_leao_mensal_mostra_aviso_fixo_do_aluguel_quando_ha_rendimento_r01_003_001(
    client, cenario
):
    """Item 3 da integração (DE-091) — o aviso fixo do art. 42 do
    RIR/2018 só aparece quando há rendimento do código R01.003.001
    (aluguel) no mês; some quando não há."""
    _autenticar(client, cenario["escritorio_a"])
    # Só a parte que cabe numa única linha do template (há uma quebra de
    # linha entre "pelo" e "locador" no HTML renderizado).
    texto_aviso = "Lance o aluguel sem IPTU, condomínio e taxa de administração pagos pelo"

    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "2000.00", date(2026, 3, 10))
    com_aluguel = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    assert texto_aviso in com_aluguel.content.decode()

    _lancar_trabalho(cenario["empresa_a"], cenario["conta_trabalho"], date(2026, 4, 10), "2000.00")
    sem_aluguel = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "4"},
    )
    assert texto_aviso not in sem_aluguel.content.decode()


def test_carne_leao_mensal_mostra_faixa_aplicada_e_criterio_pronto_do_motor(client, cenario):
    """`faixa_aplicada` (limites/alíquota/parcela) e `criterio_escolha_
    forma` — a tela imprime o texto EXATO que o motor devolveu, nunca um
    texto fixo próprio."""
    from apps.livro_caixa.carne_leao import apurar_carne_leao_mensal

    _autenticar(client, cenario["escritorio_a"])
    _lancar_trabalho(cenario["empresa_a"], cenario["conta_trabalho"], date(2026, 3, 10), "3000.00")

    resultado = apurar_carne_leao_mensal(empresa=cenario["empresa_a"], ano=2026, mes=3)
    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "3"},
    )
    html = resposta.content.decode()
    assert "Faixa aplicada" in html
    assert resultado["criterio_escolha_forma"] in html
    # Nunca o texto fixo antigo, isolado numa etapa anterior desta fatia
    # (achado corrigido nesta integração).
    assert "MENOR imposto após a" not in html


def test_carne_leao_mensal_mostra_comparacao_com_e_sem_exterior(client, cenario):
    """`imposto_com_exterior`/`imposto_sem_exterior` só aparecem quando há
    rendimento sujeito de origem exterior no mês."""
    _autenticar(client, cenario["escritorio_a"])

    sem_exterior = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "4"},
    )
    html_sem_exterior = sem_exterior.content.decode()
    assert "Imposto após a redução, COM o rendimento do exterior" not in html_sem_exterior

    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "3000.00", date(2026, 4, 10))
    criar_lancamento_caixa(
        empresa=cenario["empresa_a"],
        conta=cenario["conta_receita"],
        data=date(2026, 4, 11),
        valor=Decimal("2000.00"),
        historico="Aluguel do exterior",
        recebido_de="EX",
    )
    com_exterior = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "4"},
    )
    html = com_exterior.content.decode()
    assert "Imposto após a redução, COM o rendimento do exterior" in html
    assert "Imposto após a redução, SEM o rendimento do exterior" in html


def test_carne_leao_mensal_imposto_exterior_sem_rendimento_e_erro_nao_500(client, cenario):
    """HI-38/DE-091 item 3 — imposto pago no exterior lançado sem nenhum
    rendimento sujeito de origem exterior no MESMO mês: a tela mostra
    erro claro (409), nunca 500."""
    _autenticar(client, cenario["escritorio_a"])
    _lancar_despesa(
        cenario["empresa_a"], cenario["conta_imposto_exterior"], date(2026, 5, 10), "50.00"
    )

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_mensal", args=[cenario["empresa_a"].id]),
        {"ano": "2026", "mes": "5"},
    )
    assert resposta.status_code == 409
    html = resposta.content.decode()
    assert "sem nenhum" in html
    assert "rendimento" in html.lower()


def test_carne_leao_anual_imposto_exterior_sem_rendimento_e_erro_nao_500(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    _lancar_despesa(
        cenario["empresa_a"], cenario["conta_imposto_exterior"], date(2026, 5, 10), "50.00"
    )

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_anual", args=[cenario["empresa_a"].id]), {"ano": "2026"}
    )
    assert resposta.status_code == 409
    assert "mensagem-error" in resposta.content.decode()


def test_carne_leao_anual_usa_totais_do_motor_sem_somar_na_view(client, cenario):
    """`resultado["totais"]` (motor) aparece, formatado, na linha "Total
    do ano" — critério novo da integração: nenhuma soma nasce na view.
    Dois meses com valores DIFERENTES (não múltiplos redondos um do
    outro), para que um total errado — por exemplo, uma soma feita de
    novo na view a partir de campos que não são os de `totais` — não
    coincida por acaso com o valor certo."""
    from apps.livro_caixa.carne_leao import apurar_carne_leao_anual

    _autenticar(client, cenario["escritorio_a"])
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "1000.00", date(2026, 3, 10))
    _lancar_receita(cenario["empresa_a"], cenario["conta_receita"], "777.35", date(2026, 6, 15))

    resultado = apurar_carne_leao_anual(empresa=cenario["empresa_a"], ano=2026)
    totais = resultado["totais"]

    resposta = client.get(
        reverse("livro_caixa_web:carne_leao_anual", args=[cenario["empresa_a"].id]), {"ano": "2026"}
    )
    html = resposta.content.decode()
    assert "Total do ano" in html
    for campo, valor in totais.items():
        valor_ptbr = f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))
        assert valor_ptbr in html, f"{campo} = {valor_ptbr} não apareceu na tela"


# ---------------------------------------------------------------------------
# Retificação de dependentes (DE-091 item 6/M-6).
# ---------------------------------------------------------------------------


def test_dependentes_retificar_sucesso(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    registro = DependentesCarneLeaoCliente.objects.create(
        empresa=cenario["empresa_a"], quantidade=1, competencia_inicio=date(2026, 3, 1)
    )
    url = reverse(
        "livro_caixa_web:dependentes_carne_leao_retificar",
        args=[cenario["empresa_a"].id, registro.id],
    )
    resposta = client.post(url, {"quantidade": "3"})
    assert resposta.status_code == 302
    registro.refresh_from_db()
    assert registro.quantidade == 3


def test_dependentes_retificar_quantidade_invalida_e_erro_sem_gravar(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    registro = DependentesCarneLeaoCliente.objects.create(
        empresa=cenario["empresa_a"], quantidade=1, competencia_inicio=date(2026, 3, 1)
    )
    url = reverse(
        "livro_caixa_web:dependentes_carne_leao_retificar",
        args=[cenario["empresa_a"].id, registro.id],
    )
    resposta = client.post(url, {"quantidade": "abc"})
    assert resposta.status_code == 302  # redireciona de volta com mensagem de erro
    registro.refresh_from_db()
    assert registro.quantidade == 1


def test_dependentes_retificar_sem_permissao_de_escrita(client, cenario):
    _autenticar(client, cenario["escritorio_a"], papel=Papel.PARALEGAL, username="paralegal-ret")
    registro = DependentesCarneLeaoCliente.objects.create(
        empresa=cenario["empresa_a"], quantidade=1, competencia_inicio=date(2026, 3, 1)
    )
    url = reverse(
        "livro_caixa_web:dependentes_carne_leao_retificar",
        args=[cenario["empresa_a"].id, registro.id],
    )
    resposta = client.post(url, {"quantidade": "5"})
    assert resposta.status_code == 403
    registro.refresh_from_db()
    assert registro.quantidade == 1


def test_dependentes_retificar_isolamento_entre_empresas_da_404(client, cenario):
    """Um `dependente_id` de OUTRA empresa nunca é alcançado."""
    _autenticar(client, cenario["escritorio_a"])
    registro_de_b = DependentesCarneLeaoCliente.objects.create(
        empresa=cenario["empresa_b"], quantidade=1, competencia_inicio=date(2026, 3, 1)
    )
    url = reverse(
        "livro_caixa_web:dependentes_carne_leao_retificar",
        args=[cenario["empresa_a"].id, registro_de_b.id],
    )
    resposta = client.post(url, {"quantidade": "5"})
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Estorno de lançamento de caixa — continua funcionando com a nova regra
# do servidor (data do estorno = mês do original; corrida com outro mês
# é recusada, mas esta tela nunca envia data explícita).
# ---------------------------------------------------------------------------


def test_lancamento_caixa_estorno_continua_funcionando(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    lancamento = _lancar_receita(
        cenario["empresa_a"], cenario["conta_receita"], "100.00", date(2026, 3, 10)
    )
    url = reverse(
        "livro_caixa_web:lancamento_estornar", args=[cenario["empresa_a"].id, lancamento.id]
    )
    resposta = client.post(url)
    assert resposta.status_code == 302


def test_lancamento_caixa_estorno_duplicado_e_erro_de_formulario_nao_500(client, cenario):
    _autenticar(client, cenario["escritorio_a"])
    lancamento = _lancar_receita(
        cenario["empresa_a"], cenario["conta_receita"], "100.00", date(2026, 3, 10)
    )
    url = reverse(
        "livro_caixa_web:lancamento_estornar", args=[cenario["empresa_a"].id, lancamento.id]
    )
    primeiro = client.post(url)
    assert primeiro.status_code == 302
    segundo = client.post(url)
    assert segundo.status_code == 400
    assert "mensagem-error" in segundo.content.decode()
