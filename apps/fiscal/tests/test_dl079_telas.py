"""DL-079, frente B: telas do Lucro Presumido (fluxo, recusas, permissões, isolamento).

As NFS-e prestadas passam pelo pipeline real (`suporte_presumido_dl079`); as receitas, atividades,
declarações, confirmações e medidas passam pelas TELAS (POST com CSRF ligado). Os valores esperados
são os da consulta de 08/10/2026 (itens 4 e 6), escritos à mão em pt-BR. Dados sintéticos.
"""

import re
from datetime import date
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import (
    AtividadePresuncaoEmpresa,
    ConfirmacaoRetencaoPresumido,
    DeclaracaoReceitasIntegrais,
    MedidaJudicialLC224,
    ReceitaTrimestralPresumido,
)
from apps.fiscal.tests.suporte_presumido_dl079 import nota_efetivada
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def relogio_fim_de_2026(monkeypatch):
    """O controle do limite só mostra o fechamento com o 4º trimestre iniciado (A1). Fixa a data
    para que o teste não dependa do dia em que roda."""
    monkeypatch.setattr(servico, "_hoje", lambda: date(2026, 12, 31))


COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
SERVICOS = tab.SERVICOS_GERAIS
SENHA = "senha-forte-123"


# ---------------------------------------------------------------------------
# Auxiliares: usuários, URLs e ações pela tela
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio-fiscal-teste.com.br", password=SENHA
    )
    if escritorio is not None and papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _url(nome, *args, **consulta):
    url = reverse(f"fiscal_web:{nome}", args=list(args))
    return url + ("?" + urlencode(consulta) if consulta else "")


def _html(resposta):
    return resposta.content.decode("utf-8")


def _ids_referenciados_existem(html):
    """Todo `aria-describedby` e todo `for` aponta para um `id` que existe na própria página."""
    existentes = set(re.findall(r'\bid="([^"]+)"', html))
    referencias = set()
    for bloco in re.findall(r'aria-describedby="([^"]+)"', html):
        referencias.update(bloco.split())
    referencias.update(re.findall(r'\bfor="([^"]+)"', html))
    return referencias - existentes


def _nota(empresa, escritorio, usuario, sufixo, valor, competencia, irrf=None, csll=None):
    return nota_efetivada(
        escritorio,
        empresa,
        usuario,
        sufixo=sufixo,
        v_serv=valor,
        d_compet=competencia,
        ret_irrf=irrf,
        ret_csll=csll,
        tp_ret="8" if csll is not None else None,
    )


@pytest.fixture
def empresa_presumida(empresa_a, escritorio_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    return empresa_a


@pytest.fixture
def gestor(escritorio_a):
    return _usuario(escritorio_a, Papel.GESTOR, "gestor-presumido-telas")


@pytest.fixture
def paralegal(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-presumido-telas")


@pytest.fixture
def cliente(escritorio_a):
    return _usuario(escritorio_a, Papel.CLIENTE, "cliente-presumido-telas")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-presumido-b")


@pytest.fixture
def cenario(empresa_presumida, escritorio_a, gestor):
    """Atividades (comércio padrão, serviços gerais) e critério de 2026, pela camada de serviço."""
    servico.criar_atividade(
        empresa_presumida,
        {"atividade": COMERCIO, "inicio": date(2026, 1, 1), "padrao": True},
        gestor,
    )
    servicos = servico.criar_atividade(
        empresa_presumida,
        {"atividade": SERVICOS, "inicio": date(2026, 1, 1), "padrao": False},
        gestor,
    )
    servico.definir_criterio(empresa_presumida, 2026, "competencia", gestor)
    return {"empresa": empresa_presumida, "servicos": servicos}


# ---------------------------------------------------------------------------
# 1. Fluxo completo pela tela: os números da consulta, escritos à mão em pt-BR
# ---------------------------------------------------------------------------


def test_fluxo_completo_pela_tela_bate_com_o_exemplo_da_consulta(
    client, empresa_presumida, escritorio_a, gestor
):
    # Atividades e critério pela TELA (não pelo serviço), como o contador faria.
    _logar(client, gestor)
    empresa = empresa_presumida
    url_atividade = _url("presumido_atividade_nova", empresa.pk)
    assert client.get(url_atividade).status_code == 200
    resposta = client.post(
        url_atividade,
        {"atividade": COMERCIO, "inicio": "01/01/2026", "padrao": "1"},
    )
    assert resposta.status_code == 302
    resposta = client.post(
        url_atividade,
        {"atividade": SERVICOS, "inicio": "01/01/2026"},
    )
    assert resposta.status_code == 302
    servicos = AtividadePresuncaoEmpresa.objects.get(empresa=empresa, atividade=SERVICOS)
    assert (
        client.post(
            _url("presumido_criterio_gravar", empresa.pk),
            {"ano": "2026", "criterio": "competencia"},
        ).status_code
        == 302
    )

    # Notas de comércio (padrão), com IRRF e CSLL retidos, pelo pipeline real de recepção.
    notas = {
        1: _nota(
            empresa, escritorio_a, gestor, 101, "600000.00", "2026-01-15", "4500.00", "3000.00"
        ),
        2: _nota(
            empresa, escritorio_a, gestor, 102, "1200000.00", "2026-04-15", "9500.00", "6300.00"
        ),
        3: _nota(
            empresa, escritorio_a, gestor, 103, "800000.00", "2026-07-15", "6000.00", "4000.00"
        ),
        4: _nota(
            empresa, escritorio_a, gestor, 104, "1000000.00", "2026-10-15", "7500.00", "5000.00"
        ),
    }

    # Receitas de serviços (informadas, com atividade) e integrais, digitadas em pt-BR.
    url_receitas = _url("presumido_receita_nova", empresa.pk)
    for trimestre, valor in [
        (1, "300.000,00"),
        (2, "700.000,00"),
        (3, "400.000,00"),
        (4, "500.000,00"),
    ]:
        resposta = client.post(
            url_receitas,
            {
                "ano": "2026",
                "trimestre": str(trimestre),
                "tipo": "presuncao",
                "atividade_id": str(servicos.pk),
                "valor": valor,
                "descricao": f"serviços do {trimestre}º trimestre (sintético)",
                "suporte": f"NF sintética {trimestre}",
            },
        )
        assert resposta.status_code == 302
    for trimestre, valor in [(2, "12.000,00"), (4, "8.000,00")]:
        resposta = client.post(
            url_receitas,
            {
                "ano": "2026",
                "trimestre": str(trimestre),
                "tipo": "integral",
                "valor": valor,
                "descricao": "receita financeira sintética",
                "suporte": "extrato sintético",
            },
        )
        assert resposta.status_code == 302

    # Declaração de integrais: "não houve" no 1º e 3º trimestres; total declarado no 2º e 4º.
    url_integrais = _url("presumido_integrais_declarar", empresa.pk)
    for trimestre, modo in [
        (1, "sem_integrais"),
        (2, "declarar"),
        (3, "sem_integrais"),
        (4, "declarar"),
    ]:
        resposta = client.post(
            url_integrais,
            {"ano": "2026", "trimestre": str(trimestre), "modo": modo, "observacao": ""},
        )
        assert resposta.status_code == 302
    assert DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa).count() == 4

    # Confirmação das retenções pela tela: valor igual ao proposto, sem motivo.
    for trimestre, irrf, csll in [
        (1, "4.500,00", "3.000,00"),
        (2, "9.500,00", "6.300,00"),
        (3, "6.000,00", "4.000,00"),
        (4, "7.500,00", "5.000,00"),
    ]:
        url = _url("presumido_retencao_confirmar", empresa.pk, notas[trimestre].pk)
        assert client.get(url, {"ano": 2026, "trimestre": trimestre}).status_code == 200
        resposta = client.post(
            url,
            {
                "ano": "2026",
                "trimestre": str(trimestre),
                "irrf_confirmado": irrf,
                "csll_confirmada": csll,
                "motivo": "",
            },
        )
        assert resposta.status_code == 302
    assert ConfirmacaoRetencaoPresumido.objects.filter(estado="ativa").count() == 4

    # Apuração do 2º trimestre: os números da consulta, à mão.
    html = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=2)))
    assert "Completa" in html
    # IRPJ do 2º trimestre: base sem LC 224 332.000,00 e com LC 224 337.052,63.
    assert "332.000,00" in html and "337.052,63" in html
    # Imposto: sem LC 224 77.000,00; com LC 224 78.263,15; parcela da LC 224 1.263,15.
    assert "77.000,00" in html and "78.263,15" in html and "1.263,15" in html
    # Retenção de IRRF do 2º trimestre: 9.500,00; a recolher: 78.263,15 − 9.500,00 = 68.763,15.
    assert "9.500,00" in html and "68.763,15" in html
    # Os percentuais de comércio: 8% e 8,8% (multiplicado por 1,10, não 10 pontos).
    assert "8,8%" in html
    assert "Parcela da LC 224" in html
    assert "Conferência — não é guia nem DARF." in html
    assert "2089 — IRPJ Lucro Presumido" in html
    # Nenhum valor sai com ponto decimal de máquina.
    assert "78263.15" not in html and "68763.15" not in html

    # 4º trimestre: caso III (ExcAnual 500.000 ≥ S 300.000). Dedução zero; a recolher é 49.300,00.
    html4 = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=4)))
    assert "Caso III" in html4
    assert "56.800,00" in html4 and "49.300,00" in html4


def test_controle_do_limite_pela_tela_mostra_o_caso_e_a_sobra(
    client, cenario, escritorio_a, gestor
):
    empresa = cenario["empresa"]
    for trimestre, valor in [
        (1, "600000.00"),
        (2, "1200000.00"),
        (3, "800000.00"),
        (4, "1000000.00"),
    ]:
        _nota(
            empresa,
            escritorio_a,
            gestor,
            200 + trimestre,
            valor,
            f"2026-{(trimestre - 1) * 3 + 1:02d}-10",
        )
    _logar(client, gestor)
    html = _html(client.get(_url("presumido_limite", empresa=empresa.pk, ano=2026, tributo="irpj")))
    # A CSLL tem o mesmo controle, com o próprio início (2º trimestre) e o limite do ano.
    html_csll = _html(
        client.get(_url("presumido_limite", empresa=empresa.pk, ano=2026, tributo="csll"))
    )
    assert "CSLL em 2026" in html_csll
    # Sobra do 1º trimestre: 1.250.000,00 − 600.000,00 = 650.000,00. O limite do 2º trimestre é
    # 1.250.000,00 + 650.000,00 = 1.900.000,00, e a receita de 1.200.000,00 não o excede.
    assert "650.000,00" in html
    assert "1.900.000,00" in html
    assert "Caso" in html


# ---------------------------------------------------------------------------
# 2. Recusas: entrada inválida volta com a mensagem e NÃO grava nada
# ---------------------------------------------------------------------------


def test_recusas_nao_gravam_nada(client, cenario, escritorio_a, gestor):
    empresa = cenario["empresa"]
    _logar(client, gestor)
    servicos = cenario["servicos"]
    receitas_antes = ReceitaTrimestralPresumido.objects.count()

    # Serviço hospitalar sem os dois requisitos legais confirmados.
    resposta = client.post(
        _url("presumido_atividade_nova", empresa.pk),
        {"atividade": tab.SERVICOS_HOSPITALARES, "inicio": "01/01/2026"},
    )
    assert resposta.status_code == 400
    assert "requisitos legais" in _html(resposta)
    assert not AtividadePresuncaoEmpresa.objects.filter(
        empresa=empresa, atividade=tab.SERVICOS_HOSPITALARES
    ).exists()

    # Encerramento com data anterior ao início da vigência.
    resposta = client.post(
        _url("presumido_atividade_encerrar", empresa.pk, servicos.pk), {"fim": "01/01/2025"}
    )
    assert resposta.status_code == 400
    servicos.refresh_from_db()
    assert servicos.fim is None

    # Critério já definido: trocar é conflito (409), e o critério continua o mesmo.
    resposta = client.post(
        _url("presumido_criterio_gravar", empresa.pk), {"ano": "2026", "criterio": "caixa"}
    )
    assert resposta.status_code == 409
    assert servico.criterio_do_ano(empresa, 2026) == "competencia"

    # Receita de presunção sem atividade, e valor digitado com formato ambíguo.
    url_receita = _url("presumido_receita_nova", empresa.pk)
    base = {"ano": "2026", "trimestre": "1", "descricao": "x", "suporte": "y"}
    resposta = client.post(url_receita, {**base, "tipo": "presuncao", "valor": "1.000,00"})
    assert resposta.status_code == 400
    assert "atividade" in _html(resposta)
    resposta = client.post(
        url_receita,
        {**base, "tipo": "presuncao", "atividade_id": str(servicos.pk), "valor": "1.23,4"},
    )
    assert resposta.status_code == 400
    assert ReceitaTrimestralPresumido.objects.count() == receitas_antes

    # Receita integral lançada: "não houve receitas integrais" vira conflito, sem declaração.
    assert (
        client.post(url_receita, {**base, "tipo": "integral", "valor": "500,00"}).status_code == 302
    )
    resposta = client.post(
        _url("presumido_integrais_declarar", empresa.pk),
        {"ano": "2026", "trimestre": "1", "modo": "sem_integrais", "observacao": ""},
    )
    assert resposta.status_code == 409
    assert "declare o total" in _html(resposta)
    assert DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa).count() == 0

    # Estorno sem motivo: a receita continua ativa.
    receita = ReceitaTrimestralPresumido.objects.get(empresa=empresa, tipo="integral")
    resposta = client.post(
        _url("presumido_receita_estornar", empresa.pk, receita.pk), {"motivo": ""}
    )
    assert resposta.status_code == 400
    receita.refresh_from_db()
    assert receita.estado == "ativa"

    # Nota de comércio com retenção confirmada diferente do proposto, sem motivo.
    escrituracao = _nota(empresa, escritorio_a, gestor, 300, "1000000.00", "2026-02-10", "5000.00")
    url_retencao = _url("presumido_retencao_confirmar", empresa.pk, escrituracao.pk)
    resposta = client.post(
        url_retencao,
        {
            "ano": "2026",
            "trimestre": "1",
            "irrf_confirmado": "4.000,00",
            "csll_confirmada": "",
            "motivo": "",
        },
    )
    assert resposta.status_code == 400
    assert "informe o motivo" in _html(resposta)
    assert not ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=escrituracao).exists()
    # Com o motivo, a mesma confirmação grava (controle positivo).
    resposta = client.post(
        url_retencao,
        {
            "ano": "2026",
            "trimestre": "1",
            "irrf_confirmado": "4.000,00",
            "csll_confirmada": "",
            "motivo": "comprovante do tomador",
        },
    )
    assert resposta.status_code == 302
    assert ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=escrituracao).count() == 1

    # Medida com data de decisão inválida, e revogação sem motivo.
    resposta = client.post(
        _url("presumido_medida_nova", empresa.pk),
        {
            "tributo": "irpj",
            "ano_inicial": "2026",
            "trimestre_inicial": "2",
            "numero_processo": "5000000-00.2026.4.02.5116",
            "orgao": "Vara sintética",
            "data_decisao": "31/02/2026",
            "suporte": "decisão sintética",
        },
    )
    assert resposta.status_code == 400
    assert "dd/mm/aaaa" in _html(resposta)
    assert MedidaJudicialLC224.objects.filter(empresa=empresa).count() == 0


def test_caixa_pela_tela_sai_com_recusa_nomeada(client, cenario, gestor):
    empresa = cenario["empresa"]
    _logar(client, gestor)
    empresa.refresh_from_db()
    # Ano sem critério definido: o critério caixa é gravado pela tela e a apuração recusa, nomeando
    # o artigo da IN. Nenhum número de imposto sai.
    assert (
        client.post(
            _url("presumido_criterio_gravar", empresa.pk), {"ano": "2027", "criterio": "caixa"}
        ).status_code
        == 302
    )
    html = _html(client.get(_url("presumido_criterio", empresa=empresa.pk, ano=2027)))
    assert "IN RFB 1.700/2017, art. 223" in html
    html_ap = _html(
        client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2027, trimestre=1))
    )
    assert "Parcial" in html_ap
    assert "art. 223" in html_ap


# ---------------------------------------------------------------------------
# 3. Permissões e isolamento em todas as rotas novas
# ---------------------------------------------------------------------------

ROTAS_DE_CONSULTA = [
    "presumido_atividades",
    "presumido_criterio",
    "presumido_receitas",
    "presumido_retencoes",
    "presumido_medidas",
    "presumido_apuracao",
    "presumido_limite",
]


@pytest.fixture
def dados(cenario, escritorio_a, gestor):
    """Um lançamento de cada tipo, para as rotas que operam sobre um registro existente."""
    empresa = cenario["empresa"]
    receita = ReceitaTrimestralPresumido.objects.create(
        empresa=empresa,
        ano=2026,
        trimestre=1,
        tipo="presuncao",
        atividade=cenario["servicos"],
        descricao="receita sintética",
        valor="1000.00",
        suporte="suporte sintético",
        criada_por=gestor,
    )
    escrituracao = _nota(empresa, escritorio_a, gestor, 400, "1000000.00", "2026-02-10", "5000.00")
    medida = MedidaJudicialLC224.objects.create(
        empresa=empresa,
        tributo="irpj",
        ano_inicial=2026,
        trimestre_inicial=2,
        numero_processo="5000000-00.2026.4.02.5116",
        orgao="Vara sintética",
        data_decisao=date(2026, 6, 1),
        suporte="decisão sintética",
        criada_por=gestor,
    )
    return {"receita": receita, "escrituracao": escrituracao, "medida": medida}


def _rotas_de_escrita(empresa, cenario, dados):
    """(nome, args, query) de cada tela de escrita: GET do formulário, quando existe, e POST."""
    return [
        ("presumido_atividade_nova", [empresa.pk], {}),
        ("presumido_atividade_encerrar", [empresa.pk, cenario["servicos"].pk], {}),
        ("presumido_receita_estornar", [empresa.pk, dados["receita"].pk], {}),
        (
            "presumido_retencao_confirmar",
            [empresa.pk, dados["escrituracao"].pk],
            {"ano": 2026, "trimestre": 1},
        ),
        ("presumido_medida_nova", [empresa.pk], {}),
        ("presumido_medida_revogar", [empresa.pk, dados["medida"].pk], {}),
    ]


def _rotas_de_post_so(empresa):
    return [
        ("presumido_criterio_gravar", [empresa.pk]),
        ("presumido_receita_nova", [empresa.pk]),
        ("presumido_integrais_declarar", [empresa.pk]),
    ]


def _contagem_de_escrita(empresa):
    return (
        AtividadePresuncaoEmpresa.objects.filter(empresa=empresa).count(),
        ReceitaTrimestralPresumido.objects.filter(empresa=empresa).count(),
        DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa).count(),
        ConfirmacaoRetencaoPresumido.objects.filter(escrituracao__empresa=empresa).count(),
        MedidaJudicialLC224.objects.filter(empresa=empresa).count(),
    )


def test_cliente_recebe_403_em_todas_as_rotas_e_nada_grava(client, cenario, dados, cliente):
    empresa = cenario["empresa"]
    _logar(client, cliente)
    antes = _contagem_de_escrita(empresa)
    for nome in ROTAS_DE_CONSULTA:
        assert client.get(_url(nome, empresa=empresa.pk, ano=2026, trimestre=1)).status_code == 403
    for nome, args, query in _rotas_de_escrita(empresa, cenario, dados):
        assert client.get(_url(nome, *args, **query)).status_code == 403
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403
    for nome, args in _rotas_de_post_so(empresa):
        assert client.post(_url(nome, *args), {"ano": "2026"}).status_code == 403
    assert _contagem_de_escrita(empresa) == antes


def test_paralegal_le_e_nao_escreve(client, cenario, dados, paralegal):
    empresa = cenario["empresa"]
    _logar(client, paralegal)
    antes = _contagem_de_escrita(empresa)
    for nome in ROTAS_DE_CONSULTA:
        assert client.get(_url(nome, empresa=empresa.pk, ano=2026, trimestre=1)).status_code == 200
    for nome, args, query in _rotas_de_escrita(empresa, cenario, dados):
        assert client.get(_url(nome, *args, **query)).status_code == 403
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 403
    for nome, args in _rotas_de_post_so(empresa):
        assert client.post(_url(nome, *args), {"ano": "2026"}).status_code == 403
    assert _contagem_de_escrita(empresa) == antes


def test_paralegal_le_e_nao_ve_o_botao_de_escrita(client, cenario, dados, paralegal):
    """PARALEGAL lê a tela de receitas e não vê formulário nem botão que grava (AGENTS.md §11)."""
    empresa = cenario["empresa"]
    _logar(client, paralegal)
    html = _html(client.get(_url("presumido_receitas", empresa=empresa.pk, ano=2026, trimestre=1)))
    assert "receita sintética" in html  # a consulta mostra o que existe
    assert reverse("fiscal_web:presumido_receita_nova", args=[empresa.pk]) not in html
    assert reverse("fiscal_web:presumido_integrais_declarar", args=[empresa.pk]) not in html
    assert 'name="modo"' not in html
    assert 'value="sem_integrais"' not in html
    assert "Seu papel consulta as receitas" in html  # o motivo fica ao lado do botão desabilitado
    html_ret = _html(
        client.get(_url("presumido_retencoes", empresa=empresa.pk, ano=2026, trimestre=1))
    )
    assert "Seu papel consulta as retenções" in html_ret
    assert (
        reverse(
            "fiscal_web:presumido_retencao_confirmar", args=[empresa.pk, dados["escrituracao"].pk]
        )
        not in html_ret
    )
    html_med = _html(client.get(_url("presumido_medidas", empresa=empresa.pk)))
    assert reverse("fiscal_web:presumido_medida_nova", args=[empresa.pk]) not in html_med


def test_outro_escritorio_recebe_404(client, cenario, dados, gestor_b):
    empresa = cenario["empresa"]
    _logar(client, gestor_b)
    antes = _contagem_de_escrita(empresa)
    for nome in ROTAS_DE_CONSULTA:
        assert client.get(_url(nome, empresa=empresa.pk, ano=2026, trimestre=1)).status_code == 404
    for nome, args, query in _rotas_de_escrita(empresa, cenario, dados):
        assert client.get(_url(nome, *args, **query)).status_code == 404
        assert client.post(_url(nome, *args), {"motivo": "x"}).status_code == 404
    assert _contagem_de_escrita(empresa) == antes


def test_outra_empresa_do_mesmo_escritorio_recebe_404_no_registro(
    client, cenario, dados, empresa_a2, gestor
):
    """Registro de empresa_a pelo caminho de empresa_a2: 404, sem gravar nada."""
    empresa = cenario["empresa"]
    _logar(client, gestor)
    antes = _contagem_de_escrita(empresa)
    # Cadastro (atividade e medida novas) não tem registro de empresa_a: empresa_a2, do mesmo
    # escritório, pode recebê-lo. O isolamento vale para os registros que já existem.
    registros = [
        r
        for r in _rotas_de_escrita(empresa, cenario, dados)
        if r[0] not in ("presumido_atividade_nova", "presumido_medida_nova")
    ]
    for nome, args, query in registros:
        args_outra = [empresa_a2.pk, *args[1:]]
        assert client.get(_url(nome, *args_outra, **query)).status_code == 404
        # A confirmação recebe o período no corpo: a POST completa chega até a busca da nota.
        corpo = (
            {
                "ano": "2026",
                "trimestre": "1",
                "irrf_confirmado": "1,00",
                "csll_confirmada": "",
                "motivo": "x",
            }
            if nome == "presumido_retencao_confirmar"
            else {"motivo": "x"}
        )
        assert client.post(_url(nome, *args_outra), corpo).status_code == 404
    assert _contagem_de_escrita(empresa) == antes


def test_anonimo_vai_para_o_login(client, cenario, dados):
    empresa = cenario["empresa"]
    for nome in ROTAS_DE_CONSULTA:
        resposta = client.get(_url(nome, empresa=empresa.pk, ano=2026, trimestre=1))
        assert resposta.status_code == 302 and "login" in resposta["Location"]
    for nome, args, query in _rotas_de_escrita(empresa, cenario, dados):
        resposta = client.get(_url(nome, *args, **query))
        assert resposta.status_code == 302 and "login" in resposta["Location"]


def test_post_sem_csrf_e_recusado_e_nada_grava(cenario, gestor):
    """CSRF ligado: o cliente de teste normal ignora o token; este verifica a recusa de verdade."""
    empresa = cenario["empresa"]
    cliente_com_csrf = Client(enforce_csrf_checks=True)
    _logar(cliente_com_csrf, gestor)
    resposta = cliente_com_csrf.post(
        _url("presumido_receita_nova", empresa.pk),
        {
            "ano": "2026",
            "trimestre": "1",
            "tipo": "integral",
            "valor": "100,00",
            "descricao": "x",
            "suporte": "y",
        },
    )
    assert resposta.status_code == 403
    assert ReceitaTrimestralPresumido.objects.filter(empresa=empresa).count() == 0


def test_campo_fora_do_contrato_e_recusado_com_o_nome(client, cenario, gestor):
    empresa = cenario["empresa"]
    _logar(client, gestor)
    resposta = client.post(
        _url("presumido_criterio_gravar", empresa.pk),
        {"ano": "2026", "criterio": "competencia", "campo_inventado": "x"},
    )
    assert resposta.status_code == 400
    assert "campo_inventado" in _html(resposta)


# ---------------------------------------------------------------------------
# 4. Medidas judiciais pela tela, e o item 0 vista pela tela
# ---------------------------------------------------------------------------


def test_medida_cadastrada_e_revogada_pela_tela(client, cenario, escritorio_a, gestor):
    empresa = cenario["empresa"]
    _logar(client, gestor)
    resposta = client.post(
        _url("presumido_medida_nova", empresa.pk),
        {
            "tributo": "irpj",
            "ano_inicial": "2026",
            "trimestre_inicial": "2",
            "ano_final": "2026",
            "trimestre_final": "2",
            "numero_processo": "5000000-00.2026.4.02.5116",
            "orgao": "Vara sintética",
            "data_decisao": "01/06/2026",
            "deposito_judicial": "",
            "suporte": "decisão sintética",
        },
    )
    assert resposta.status_code == 302
    html = _html(client.get(_url("presumido_medidas", empresa=empresa.pk)))
    assert "5000000-00.2026.4.02.5116" in html
    assert "ADI 7936 e ADI 7944" in html
    assert "08/10/2026" in html  # data da última conferência, como na frente A
    medida = MedidaJudicialLC224.objects.get(empresa=empresa)
    resposta = client.post(
        _url("presumido_medida_revogar", empresa.pk, medida.pk), {"motivo": "decisão cassada"}
    )
    assert resposta.status_code == 302
    medida.refresh_from_db()
    assert medida.ativa is False
    assert "Revogada: decisão cassada" in _html(
        client.get(_url("presumido_medidas", empresa=empresa.pk))
    )


def _notas_do_caso_i(cenario, escritorio, usuario):
    empresa = cenario["empresa"]
    for trimestre, valor, competencia in [
        (1, "2000000.00", "2026-01-10"),
        (2, "500000.00", "2026-04-10"),
        (3, "500000.00", "2026-07-10"),
        (4, "1000000.00", "2026-10-10"),
    ]:
        _nota(empresa, escritorio, usuario, 500 + trimestre, valor, competencia)


def test_item_0_pela_tela_medida_no_t1_tira_a_parcela_da_deducao(
    client, cenario, escritorio_a, gestor
):
    """Caso I (Σ R 4.000.000). Sem medida, o 4º deduz 1.500,00 do 1º; com medida, não deduz."""
    empresa = cenario["empresa"]
    _notas_do_caso_i(cenario, escritorio_a, gestor)
    _logar(client, gestor)
    sem = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=4)))
    assert "Caso I:" in sem
    assert "1.500,00" in sem  # a dedução do 4º trimestre
    assert "12.500,00" in sem  # a recolher: 14.000,00 − 1.500,00
    assert (
        client.post(
            _url("presumido_medida_nova", empresa.pk),
            {
                "tributo": "irpj",
                "ano_inicial": "2026",
                "trimestre_inicial": "1",
                "ano_final": "2026",
                "trimestre_final": "1",
                "numero_processo": "5000000-00.2026.4.02.5116",
                "orgao": "Vara sintética",
                "data_decisao": "01/03/2026",
                "suporte": "decisão sintética",
            },
        ).status_code
        == 302
    )
    com = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=4)))
    assert "14.000,00" in com  # a recolher sem a dedução
    assert "12.500,00" not in com
    assert "parcela suspensa por medida judicial — fora da dedução" in com
    limite = _html(
        client.get(_url("presumido_limite", empresa=empresa.pk, ano=2026, tributo="irpj"))
    )
    assert "parcela suspensa por medida judicial — fora da dedução" in limite


# ---------------------------------------------------------------------------
# 5. Acessibilidade: o mesmo auxiliar das telas da DL-078, e mais as referências dos campos
# ---------------------------------------------------------------------------


def test_acessibilidade_das_telas_do_presumido(client, cenario, dados, gestor):
    empresa = cenario["empresa"]
    _logar(client, gestor)
    paginas = [
        _url("presumido_atividades", empresa=empresa.pk),
        _url("presumido_criterio", empresa=empresa.pk, ano=2026),
        _url("presumido_receitas", empresa=empresa.pk, ano=2026, trimestre=1),
        _url("presumido_retencoes", empresa=empresa.pk, ano=2026, trimestre=1),
        _url("presumido_medidas", empresa=empresa.pk),
        _url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=1),
        _url("presumido_limite", empresa=empresa.pk, ano=2026, tributo="irpj"),
        _url("presumido_atividade_nova", empresa.pk),
        _url("presumido_atividade_encerrar", empresa.pk, cenario["servicos"].pk),
        _url("presumido_receita_estornar", empresa.pk, dados["receita"].pk),
        _url(
            "presumido_retencao_confirmar",
            empresa.pk,
            dados["escrituracao"].pk,
            ano=2026,
            trimestre=1,
        ),
        _url("presumido_medida_nova", empresa.pk),
        _url("presumido_medida_revogar", empresa.pk, dados["medida"].pk),
    ]
    for url in paginas:
        resposta = client.get(url)
        assert resposta.status_code == 200, url
        html = _html(resposta)
        assert_moldura_acessivel(html)
        assert not _ids_referenciados_existem(html), (url, _ids_referenciados_existem(html))
        assert html.count("<table") == html.count("<caption"), url
        assert "<th " not in html or 'scope="' in html, url
        assert "style=" not in html, url  # nada de medida solta fora dos tokens


# ---------------------------------------------------------------------------
# 6. Menu, home, inventário, pt-BR e as colunas da memória
# ---------------------------------------------------------------------------


def test_menu_e_home_do_fiscal_mostram_o_lucro_presumido(client, cenario, gestor, cliente):
    _logar(client, gestor)
    html = _html(client.get(reverse("tenancy:painel")))
    assert "Lucro Presumido" in html
    assert _url("presumido_apuracao") in html
    assert _url("presumido_medidas") in html
    resposta = client.get(reverse("module_home:home", args=["fiscal"]))
    atalhos = resposta.context["home"]["atalhos"]
    assert any(
        atalho["rotulo"].startswith("Lucro Presumido")
        and atalho["url"].startswith(_url("presumido_apuracao"))
        for atalho in atalhos
    )
    # Quem não consulta o Fiscal não vê o grupo nem o atalho.
    _logar(client, cliente)
    assert _url("presumido_apuracao") not in _html(client.get(reverse("tenancy:painel")))


def test_rotas_do_presumido_estao_no_inventario_do_dl024():
    """Toda rota `presumido_*` da urlconf REAL está no inventário do DL-024, e nenhuma sobra."""
    from django.urls import get_resolver

    from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import (
        NOMES_DE_TELA_DO_LUCRO_PRESUMIDO,
    )

    _, namespace = get_resolver().namespace_dict["fiscal_web"]
    reais = {
        f"fiscal_web:{nome}"
        for nome in namespace.reverse_dict.keys()
        if isinstance(nome, str) and nome.startswith("presumido_")
    }
    assert len(reais) == 16
    assert reais == set(NOMES_DE_TELA_DO_LUCRO_PRESUMIDO)


def test_valores_em_pt_br_escritos_a_mao_e_sem_ponto_de_maquina(
    client, cenario, escritorio_a, gestor
):
    """O 2º trimestre da consulta, em pt-BR, escrito à mão. Nenhum valor sai como 78263.15."""
    empresa = cenario["empresa"]
    _notas_do_exemplo_do_2_trimestre(cenario, escritorio_a, gestor)
    _logar(client, gestor)
    html = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=2)))
    for valor in ["337.052,63", "78.263,15", "1.263,15", "68.763,15"]:
        assert f'valor-monetario">{valor}' in html or f">{valor}<" in html, valor
    # Nenhum número com ponto decimal de máquina dentro de uma célula de valor.
    assert re.search(r">\s*-?\d{3,}\.\d{2}\s*<", html) is None


def test_a_memoria_tem_a_coluna_da_parcela_da_lc224(client, cenario, escritorio_a, gestor):
    """As três colunas: sem LC 224, com LC 224 e a parcela. A parcela é cabeçalho de coluna."""
    empresa = cenario["empresa"]
    _notas_do_exemplo_do_2_trimestre(cenario, escritorio_a, gestor)
    _logar(client, gestor)
    html = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=2)))
    assert re.search(r'<th scope="col">Parcela da LC 224</th>', html)
    assert re.search(r'<th scope="col">Sem LC 224</th>', html)
    assert re.search(r'<th scope="col">Com LC 224</th>', html)
    assert re.search(r'<td class="valor-monetario">1\.263,15</td>', html)


def _notas_do_exemplo_do_2_trimestre(cenario, escritorio, usuario):
    """2º trimestre da consulta: comércio 1.200.000 (IRRF 9.500 confirmado), serviços 700.000 e
    integral 12.000 declarada. Números sintéticos; o IRPJ esperado está nos testes que chamam."""
    empresa = cenario["empresa"]
    # O 1º trimestre do exemplo (900.000) gera a sobra de 350.000 que entra no limite do 2º.
    _nota(empresa, escritorio, usuario, 600, "600000.00", "2026-01-15")
    servico.criar_receita(
        empresa,
        2026,
        1,
        {
            "tipo": "presuncao",
            "valor": "300000.00",
            "descricao": "serviços do 1º trimestre",
            "suporte": "NF sintética",
            "atividade_id": cenario["servicos"].pk,
        },
        usuario,
    )
    nota = _nota(
        empresa, escritorio, usuario, 601, "1200000.00", "2026-04-15", "9500.00", "6300.00"
    )
    servico.criar_receita(
        empresa,
        2026,
        2,
        {
            "tipo": "presuncao",
            "valor": "700000.00",
            "descricao": "serviços sintéticos",
            "suporte": "NF sintética",
            "atividade_id": cenario["servicos"].pk,
        },
        usuario,
    )
    servico.criar_receita(
        empresa,
        2026,
        2,
        {"tipo": "integral", "valor": "12000.00", "descricao": "financeira", "suporte": "extrato"},
        usuario,
    )
    servico.declarar_receitas_integrais(empresa, 2026, 2, "", usuario)
    servico.confirmar_retencao(empresa, nota.pk, "9500.00", "6300.00", "", usuario)
    return nota


# ---------------------------------------------------------------------------
# 7. O que a tela promete e a regra sustenta: declaração, recusa nomeada, parcial e quotas
# ---------------------------------------------------------------------------


def test_declaracao_vale_ou_cai_na_tela_e_situacao_parcial_tem_motivo(
    client, cenario, escritorio_a, gestor
):
    empresa = cenario["empresa"]
    _notas_do_exemplo_do_2_trimestre(cenario, escritorio_a, gestor)
    _logar(client, gestor)
    # Sem declaração de integrais no 1º trimestre: a apuração sai parcial, e a tela diz por quê.
    html1 = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=1)))
    assert "Parcial: receitas integrais do trimestre não declaradas" in html1
    # Declaração do 2º trimestre (12.000,00) vale enquanto o total não muda.
    html_receitas = _html(
        client.get(_url("presumido_receitas", empresa=empresa.pk, ano=2026, trimestre=2))
    )
    assert "A declaração vale" in html_receitas
    # Uma integral a mais muda o total: a declaração cai, e a tela diz por que.
    assert (
        client.post(
            _url("presumido_receita_nova", empresa.pk),
            {
                "ano": "2026",
                "trimestre": "2",
                "tipo": "integral",
                "valor": "1,00",
                "descricao": "outra receita",
                "suporte": "extrato",
            },
        ).status_code
        == 302
    )
    html_receitas = _html(
        client.get(_url("presumido_receitas", empresa=empresa.pk, ano=2026, trimestre=2))
    )
    assert "A declaração caiu porque o total mudou" in html_receitas
    html2 = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=2)))
    assert "a declaração de receitas integrais caiu" in html2


def test_retencoes_mostram_a_confirmacao_ativa_e_a_marca_da_regra(
    client, cenario, escritorio_a, gestor
):
    empresa = cenario["empresa"]
    nota = _nota(
        empresa, escritorio_a, gestor, 700, "1000000.00", "2026-02-10", "7500.00", "5000.00"
    )
    _logar(client, gestor)
    html_antes = _html(
        client.get(_url("presumido_retencoes", empresa=empresa.pk, ano=2026, trimestre=1))
    )
    assert "não confirmado" in html_antes
    assert "exata, tpRetPisCofins 8" in html_antes
    assert (
        client.post(
            _url("presumido_retencao_confirmar", empresa.pk, nota.pk),
            {
                "ano": "2026",
                "trimestre": "1",
                "irrf_confirmado": "7.500,00",
                "csll_confirmada": "5.000,00",
                "motivo": "",
            },
        ).status_code
        == 302
    )
    html_depois = _html(
        client.get(_url("presumido_retencoes", empresa=empresa.pk, ano=2026, trimestre=1))
    )
    assert "7.500,00" in html_depois and "5.000,00" in html_depois
    assert "não confirmado" not in html_depois


def test_nota_sem_atividade_recusa_a_apuracao_e_lista_a_nota(
    client, empresa_presumida, escritorio_a, gestor
):
    """Sem atividade de presunção cadastrada, a nota não tem percentual: a apuração recusa e a tela
    diz qual nota. Nenhum número de imposto sai."""
    servico.definir_criterio(empresa_presumida, 2026, "competencia", gestor)
    nota = _nota(empresa_presumida, escritorio_a, gestor, 800, "1000000.00", "2026-02-10")
    _logar(client, gestor)
    html = _html(
        client.get(_url("presumido_apuracao", empresa=empresa_presumida.pk, ano=2026, trimestre=1))
    )
    assert "Nota sem atividade de presunção vigente na competência." in html
    assert (nota.vinculo.documento.numero or nota.vinculo.documento.identificador) in html
    assert "Situação: Parcial" in html
    assert "2089 — IRPJ Lucro Presumido" not in html


def test_quotas_e_fonte_do_darf_aparecem_na_memoria(client, cenario, escritorio_a, gestor):
    empresa = cenario["empresa"]
    _notas_do_exemplo_do_2_trimestre(cenario, escritorio_a, gestor)
    _logar(client, gestor)
    html = _html(client.get(_url("presumido_apuracao", empresa=empresa.pk, ano=2026, trimestre=2)))
    # IRPJ a recolher 68.763,15: três quotas de 22.921,05, e a 3ª com Selic + 1%, sem taxa embutida.
    assert "22.921,05" in html
    assert "taxa não embutida" in html
    assert "gov.br" in html  # fonte do código de DARF, informativo
    assert "2372 — CSLL Lucro Presumido" in html
    assert "Conferência — não é guia nem DARF." in html
