"""DL-061, fatia 2 (BL-605) — a TELA da marcação manual: a guia "DMPL" do
lançamento (E19, docs/planos/DL-061-dmpl.md).

O acesso humano à marcação manual: as marcações atuais, o efeito do
lançamento por coluna (o Σ que o conjunto precisa reproduzir, E16), o
formulário do CONJUNTO (gravado de uma vez) e o botão "Remover marcações".
A regra de verdade é do SERVIÇO (`salvar_marcacoes_da_dmpl`/`remover_
marcacoes_da_dmpl`, já testado em `test_dl061_bl605_marcacao_manual.py`);
aqui se prova que a TELA mostra o certo, grava pelo serviço, traduz a
recusa para erro de página (nunca 500) e obedece às permissões.

Cobre os critérios de aceite 5 da fatia 2 ("tela: guia do lançamento grava o
conjunto e o veto da DMPL linka até ela; sem marcação, o comportamento atual
não muda em nada") e os cenários obrigatórios vistos pela tela:

- a guia mostra as marcações e o efeito por coluna; o conjunto gravado
  reflete na apuração (a DMPL emite);
- a recusa do serviço (Σ por coluna errado) aparece como erro na página e
  nada é gravado;
- "Remover marcações" limpa e o veto volta;
- CLIENTE não grava; quem só lê lê (sem formulário); a leitura segue as
  permissões atuais;
- a página de veto da DMPL aponta para a guia do lançamento;
- o formulário NÃO aparece (com a explicação) quando a regra decide o
  lançamento (E17: o servidor recusa — a tela não promete o que ele não faz).

Os cenários são os MESMOS do arquivo de serviço (`_cenario_m3`,
`_permuta_de_tesouraria`, `_caso_a`), importados de lá — os mesmos números,
para a tela ser conferível contra a apuração já testada. Dados 100%
sintéticos.
"""

from datetime import date

import pytest
from django.urls import reverse

from apps.contabilidade import views_web
from apps.contabilidade.models import ClassificacaoDmpl, MarcacaoDmpl
from apps.contabilidade.services import avaliar_emissao_da_dmpl, salvar_marcacoes_da_dmpl
from apps.contabilidade.tests.test_dl048_dlpa import _autenticar
from apps.contabilidade.tests.test_dl061_bl605_marcacao_manual import (
    LINHA_ALIENACAO,
    LINHA_AQUISICAO,
    LINHA_DIVIDENDOS,
    RESERVA_LEGAL,
    TESOURARIA,
    _cenario_m3,
    _permuta_de_tesouraria,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    MES,
    _apurar,
    _caso_a,
    _celula,
    _chaves_das_linhas,
    _dec,
    _lancar,
    _pendencias_nao_vazias,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

PAPEIS_QUE_LEEM = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
)
PAPEIS_QUE_ESCRITURAM = (Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO)

COLUNA_TESOURARIA = ClassificacaoDmpl.ACOES_OU_QUOTAS_EM_TESOURARIA.label
COLUNA_RESERVA_LEGAL = ClassificacaoDmpl.RESERVA_LEGAL.label


# ---------------------------------------------------------------------------
# Helpers — no molde de test_dl061_tela_dmpl.py
# ---------------------------------------------------------------------------


def _url(empresa, lancamento):
    return reverse("contabilidade_web:lancamento_marcacao_dmpl", args=[empresa.id, lancamento.id])


def _url_detalhe(empresa, lancamento):
    return reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, lancamento.id])


def _url_dmpl(empresa):
    return f"{reverse('contabilidade_web:dmpl', args=[empresa.id])}?ano={ANO}&mes={MES}"


def _entrar(client, empresa, papel=Papel.GESTOR, nome="gestor-tela-marcacao"):
    _autenticar(client, empresa.escritorio, f"{nome}-{papel.value}-{empresa.pk}", papel=papel)


def _post(client, empresa, lancamento, triplas=(), acao="salvar"):
    """POST do formulário da guia — campos REPETIDOS `linha`/`coluna`/
    `valor` (uma tripla por marcação), valores em pt-BR, como o `<form>`
    emite. `triplas` vazio com `acao=salvar` é o "Salvar" sem linha nenhuma."""
    dados = {"acao": acao, "linha": [], "coluna": [], "valor": []}
    for linha, coluna, valor in triplas:
        dados["linha"].append(linha)
        dados["coluna"].append(coluna)
        dados["valor"].append(valor)
    return client.post(_url(empresa, lancamento), dados)


def _texto(html):
    return " ".join(html.split())


def _marcacoes_gravadas(lancamento):
    return {
        (m.linha, m.coluna, m.valor) for m in MarcacaoDmpl.objects.filter(lancamento=lancamento)
    }


# ---------------------------------------------------------------------------
# 1. A guia: marcações atuais, efeito por coluna e o conjunto gravado
# ---------------------------------------------------------------------------


def test_a_guia_mostra_as_marcacoes_atuais_e_o_efeito_por_coluna(client):
    """O contador precisa conferir o Σ: a guia mostra o que está marcado e o
    efeito do lançamento em cada coluna — o MESMO número que o serviço exige
    que o conjunto reproduza (E16)."""
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    # Marcação gravada pelo SERVIÇO (o caminho da API), para a guia ser
    # medida sobre o mesmo dado que `test_dl061_bl605_marcacao_manual` usa.
    salvar_marcacoes_da_dmpl(
        lancamento=pagamento,
        marcacoes=[{"linha": LINHA_DIVIDENDOS, "coluna": RESERVA_LEGAL, "valor": _dec("1000.00")}],
        usuario=gestor,
    )

    _entrar(client, empresa)
    resposta = client.get(_url(empresa, pagamento))
    assert resposta.status_code == 200
    guia = resposta.context["guia_dmpl"]

    assert [(m["linha_titulo"], m["coluna_titulo"], m["valor"]) for m in guia["marcacoes"]] == [
        ("Dividendos", COLUNA_RESERVA_LEGAL, {"ptbr": "1.000,00", "negativo": False})
    ]
    assert [(e["coluna_titulo"], e["valor"]) for e in guia["efeito_por_coluna"]] == [
        (COLUNA_RESERVA_LEGAL, {"ptbr": "1.000,00", "negativo": False})
    ]
    # …e as duas coisas aparecem para quem lê a página, não só no contexto.
    html = _texto(resposta.content.decode())
    assert "Marcações manuais atuais deste lançamento na DMPL" in html
    assert "Efeito deste lançamento em cada coluna da DMPL" in html
    assert "Dividendos" in html and COLUNA_RESERVA_LEGAL in html


def test_o_efeito_por_coluna_mostra_o_liquido_com_o_negativo_entre_parenteses(client):
    """A convenção contábil da direção de arte vale na guia também: valor
    invertido sai entre parênteses, nunca só com o sinal."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    guia = client.get(_url(empresa, permuta)).context["guia_dmpl"]
    assert [(e["coluna_titulo"], e["valor"]) for e in guia["efeito_por_coluna"]] == [
        (COLUNA_TESOURARIA, {"ptbr": "500,00", "negativo": True})
    ]
    html = _texto(client.get(_url(empresa, permuta)).content.decode())
    # O parêntese envolve o número tabulado (`_valor_dre.html`): negativo
    # nunca sai só com o sinal.
    assert (
        '<span class="valor-invertido">(<span class="valor-monetario">500,00</span>)</span>' in html
    )


def test_post_grava_o_conjunto_de_uma_vez_e_a_dmpl_emite(client):
    """O contrato E16 visto pela tela: o par marcado reproduz o efeito por
    coluna, a emissão deixa de ser vetada e as células do documento são as
    da marcação — com os brutos nas duas linhas."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)

    resposta = _post(
        client,
        empresa,
        permuta,
        [
            (LINHA_AQUISICAO, TESOURARIA, "-1.500,00"),
            (LINHA_ALIENACAO, TESOURARIA, "1.000,00"),
        ],
    )
    assert resposta.status_code == 302
    assert resposta.url == _url_detalhe(empresa, permuta)

    assert _marcacoes_gravadas(permuta) == {
        (LINHA_AQUISICAO, TESOURARIA, _dec("-1500.00")),
        (LINHA_ALIENACAO, TESOURARIA, _dec("1000.00")),
    }
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_AQUISICAO, TESOURARIA) == _dec("-1500.00")
    assert _celula(dmpl, LINHA_ALIENACAO, TESOURARIA) == _dec("1000.00")
    # E a guia reflete o que foi gravado (a tela de volta, via redirect).
    guia = client.get(_url(empresa, permuta)).context["guia_dmpl"]
    assert len(guia["marcacoes"]) == 2


def test_o_conjunto_novo_substitui_o_antigo_nao_se_acumula(client):
    """Substituição atômica (E15): o POST é o conjunto INTEIRO — o conjunto
    antigo some, e a linha de folga do formulário nunca vira marcação."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    _post(
        client,
        empresa,
        permuta,
        [
            (LINHA_AQUISICAO, TESOURARIA, "-1.500,00"),
            (LINHA_ALIENACAO, TESOURARIA, "1.000,00"),
        ],
    )
    resposta = _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "-500,00")])
    assert resposta.status_code == 302
    assert _marcacoes_gravadas(permuta) == {(LINHA_AQUISICAO, TESOURARIA, _dec("-500.00"))}
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True


# ---------------------------------------------------------------------------
# 2. Recusa do serviço vira erro de página — e nada é gravado
# ---------------------------------------------------------------------------


def test_recusa_do_servico_aparece_como_erro_na_pagina_e_nada_e_gravado(client):
    """Σ por coluna errado: a mensagem do serviço (que nomeia a coluna e os
    DOIS valores) aparece na própria guia, o formulário continua lá com o que
    foi digitado e nada é gravado. NUNCA 500."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)

    resposta = _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "-1.000,00")])

    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "As marcações não reproduzem o efeito do lançamento por coluna" in html
    assert COLUNA_TESOURARIA in html
    # O que a pessoa digitou continua na tela (arquétipo B) e o formulário
    # não sumiu.
    assert "-1.000,00" in html
    assert "Salvar marcações" in html
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is False


def test_recusa_por_valor_no_formato_errado_e_erro_de_formulario(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    resposta = _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "10.00")])
    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "não está no formato aceito" in html
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_marcacao_pela_metade_diz_o_que_falta(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    resposta = _post(client, empresa, permuta, [(LINHA_AQUISICAO, "", "")])
    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "está incompleta" in html and "coluna" in html and "valor" in html
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_campo_extra_no_corpo_recebe_400_e_nada_e_gravado(client):
    """Política dos cinco dicionários (BL-196): campo que esta tela não lê é
    recusado nomeando, nunca ignorado em silêncio."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    resposta = client.post(
        _url(empresa, permuta),
        {
            "acao": "salvar",
            "linha": [LINHA_AQUISICAO],
            "coluna": [TESOURARIA],
            "valor": ["-500,00"],
            "xpto": "1",
        },
    )
    assert resposta.status_code == 400
    assert "Não reconheço o(s) campo(s) enviado(s)" in _texto(resposta.content.decode())
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_salvar_sem_nenhuma_linha_nao_limpa_as_marcacoes(client):
    """A limpeza tem botão próprio ("Remover marcações"): um "Salvar" vazio
    jamais apaga o conjunto sem ninguém pedir."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "-500,00")])

    resposta = _post(client, empresa, permuta, [])
    assert resposta.status_code == 200
    assert "Nenhuma marcação informada" in _texto(resposta.content.decode())
    assert _marcacoes_gravadas(permuta) == {(LINHA_AQUISICAO, TESOURARIA, _dec("-500.00"))}


# ---------------------------------------------------------------------------
# 3. "Remover marcações" limpa — e o veto volta
# ---------------------------------------------------------------------------


def test_remover_marcacoes_limpa_e_o_veto_volta(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    _post(
        client,
        empresa,
        permuta,
        [
            (LINHA_AQUISICAO, TESOURARIA, "-1.500,00"),
            (LINHA_ALIENACAO, TESOURARIA, "1.000,00"),
        ],
    )
    assert avaliar_emissao_da_dmpl(_apurar(empresa))["pode_emitir"] is True

    resposta = _post(client, empresa, permuta, acao="remover")

    assert resposta.status_code == 302
    assert resposta.url == _url_detalhe(empresa, permuta)
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert "lancamentos_ambiguos" in _pendencias_nao_vazias(dmpl)
    # A volta ao veto é exatamente a de antes de marcar: o lançamento
    # ambíguo não publica célula nenhuma — as duas linhas da marcação somem
    # do documento.
    assert LINHA_AQUISICAO not in _chaves_das_linhas(dmpl)
    assert LINHA_ALIENACAO not in _chaves_das_linhas(dmpl)
    # …e a guia volta a mostrar "nenhuma marcação".
    guia = client.get(_url(empresa, permuta)).context["guia_dmpl"]
    assert guia["marcacoes"] == []


# ---------------------------------------------------------------------------
# 4. Permissões: CLIENTE não grava; quem só lê, lê (sem formulário)
# ---------------------------------------------------------------------------


def test_cliente_recebe_403_ao_marcar_e_nada_e_gravado(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa, Papel.CLIENTE)
    resposta = _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "-500,00")])
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]
    assert "Seu papel não permite" in resposta.content.decode()
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


@pytest.mark.parametrize("papel", PAPEIS_QUE_LEEM)
def test_quem_le_a_guia_ve_o_dado_mas_nao_o_formulario(client, papel):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa, papel)
    resposta = client.get(_url(empresa, permuta))
    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    # Leitura segue as permissões atuais do detalhe: a guia e o efeito por
    # coluna aparecem para todo papel que lê a contabilidade.
    assert "Marcações manuais atuais deste lançamento na DMPL" in html
    assert COLUNA_TESOURARIA in html
    if papel in PAPEIS_QUE_ESCRITURAM:
        assert "Salvar marcações" in html
    else:
        assert "Salvar marcações" not in html and "Remover marcações" not in html
        assert "peça a quem escritura" in html


@pytest.mark.parametrize("papel", [Papel.PARALEGAL, Papel.CLIENTE])
def test_quem_nao_escritura_nao_grava_nem_limpa(client, papel):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa, papel)
    for resposta in (
        _post(client, empresa, permuta, [(LINHA_AQUISICAO, TESOURARIA, "-500,00")]),
        _post(client, empresa, permuta, acao="remover"),
    ):
        assert resposta.status_code == 403
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


def test_lancamento_de_outra_empresa_da_404_e_nada_e_gravado(client):
    """Isolamento: o lançamento é buscado DENTRO da empresa da URL — empresa
    alheia nunca confirma a existência de lançamento alheio."""
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    alheio = _caso_a()[0].lancamentos.first()
    _entrar(client, empresa)

    resposta = _post(client, empresa, alheio, [(LINHA_AQUISICAO, TESOURARIA, "-500,00")])

    assert resposta.status_code == 404
    assert not MarcacaoDmpl.objects.filter(lancamento=alheio).exists()
    assert not MarcacaoDmpl.objects.filter(lancamento=permuta).exists()


# ---------------------------------------------------------------------------
# 5. O veto da DMPL aponta para a guia do lançamento
# ---------------------------------------------------------------------------


def test_o_veto_por_lancamento_ambiguo_aponta_para_a_guia_do_lancamento(client):
    empresa, contas, gestor, permuta = _permuta_de_tesouraria()
    _entrar(client, empresa)
    html = _texto(client.get(_url_dmpl(empresa)).content.decode())
    acao = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA["lancamentos_ambiguos"]
    assert "guia “DMPL”" in acao
    assert acao in html
    # O link de conferência já existente continua levando ao detalhe — que é
    # onde a guia está (a MESMA renderização da rota da guia).
    assert _url_detalhe(empresa, permuta) in html
    baixa = acao.lower()
    assert "estorne" not in baixa and "divida" not in baixa


def test_o_veto_por_contrapartida_sem_classificacao_tambem_aponta_para_a_guia(client):
    empresa, contas, gestor, pagamento, estorno = _cenario_m3()
    _entrar(client, empresa)
    html = _texto(client.get(_url_dmpl(empresa)).content.decode())
    acao = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA[
        "contrapartidas_sem_classificacao"
    ]
    assert "guia “DMPL”" in acao
    assert acao in html
    assert _url_detalhe(empresa, pagamento) in html
    baixa = acao.lower()
    assert "estorne" not in baixa and "divida" not in baixa


# ---------------------------------------------------------------------------
# 6. E17: quando a regra decide, NÃO há formulário (e o servidor recusa)
# ---------------------------------------------------------------------------


def _lancamento_decidido_pela_regra():
    """Aumento de capital em dinheiro — a regra decide sozinha (a mesma
    construção de `test_recusa_lancamento_que_a_regra_decide_so_zinho`)."""
    empresa, contas, gestor = _caso_a()
    decidido = _lancar(
        empresa,
        date(2026, 2, 10),
        "Aumento de capital",
        contas["caixa"],
        contas["capital"],
        "200.00",
    )
    return empresa, contas, decidido


def test_o_formulario_nao_aparece_quando_a_regra_decide_e_a_guia_explica(client):
    empresa, contas, decidido = _lancamento_decidido_pela_regra()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa, decidido))
    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "Salvar marcações" not in html
    # A explicação certa: é a regra que decide, e a marcação é a exceção —
    # a tela não promete o que o servidor não faz.
    assert "decidido pela regra automática da DMPL" in html
    assert "marcação manual é a exceção prevista pela RC-151" in html


def test_mesmo_assim_o_servidor_recusa_e_a_recusa_aparece_na_pagina(client):
    """A tela pode ser contornada à mão (POST direto): o servidor recusa e a
    recusa vira erro de página — nunca grava, nunca 500 (E17)."""
    empresa, contas, decidido = _lancamento_decidido_pela_regra()
    _entrar(client, empresa)
    resposta = _post(
        client,
        empresa,
        decidido,
        [("aumento_de_capital", "capital_social", "200,00")],
    )
    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "regra automática" in html
    assert not MarcacaoDmpl.objects.filter(lancamento=decidido).exists()
