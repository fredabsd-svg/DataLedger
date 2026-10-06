"""DL-066, etapa 2 (TELA) — a DFC (CTB-15) renderizada e a porta de
classificação da conta: permissão, estados, documento (método direto
resumido + método indireto), veredito do servidor, item 52A e a ponte entre
as duas telas novas.

Cobre os critérios de aceite 20 e 21 da etapa 2
(`docs/planos/DL-066-dfc.md`):

- 20: a tela da DFC OBEDECE o veredito (`avaliar_emissao_da_dfc`) — com
  pendência, NENHUMA parte da demonstração é montada (sem tabela, sem
  totais, sem carimbo, sem bloco de identificação impresso) e o motivo
  nomeado pelo servidor aparece; emitindo, o documento traz o bloco de
  identificação (`identificacao-do-documento`, classe Demonstração) em cada
  `<thead>`, o método direto resumido (três atividades, variação, caixa
  inicial/final e a conciliação do item 45) e o método indireto (lucro
  líquido, ajustes do item 20 com item/sinal/valor, total, fluxo
  operacional e a conferência contra o direto) — e **nenhum** campo de valor
  por ação (CPC 03, item 52A: na DFC é proibido);
- 21: as duas telas novas existem no universo de telas (guarda derivada em
  `test_dl024_atalhos_e_acessibilidade`), com a navegação da empresa
  presente; a classificação da conta renderiza os três campos e o POST grava
  pela MESMA porta que a API usa (`classificar_conta_na_dfc`).

Os números e a apuração são do servidor e já têm testes próprios
(`test_dl066_dfc.py`, `test_dl066_indireto.py`, `test_dl066_classificacao.py`);
aqui se prova que a TELA os mostra certos, no lugar certo, para quem pode
vê-los — e só para esses. Cenários reaproveitados dos testes de servidor
(caso de referência do critério 16 calculado à mão); dados 100% sintéticos.
Hoje é 2026-10-01; o exercício é o ano civil (HI-28).

Dinheiro NUNCA aparece como número cru: as asserções de valores esperam o
texto pt-BR do `_valor_dre.html` ("85.000,00", "(30.000,00)") e varrem o
HTML atrás das formas cruas ("85000.00") para reprovar se alguma vazar.
"""

from datetime import date
from re import sub

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import ClassificacaoDre, Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import (
    _TITULOS_DAS_PENDENCIAS_DA_DFC,
    classificar_conta_na_dfc,
    encerrar_competencia,
)
from apps.contabilidade.tests import test_dl048_dlpa as _tela
from apps.contabilidade.tests import test_dl061_dmpl as _base
from apps.contabilidade.tests import test_dl066_classificacao as _porta
from apps.contabilidade.tests import test_dl066_dfc as _servidor
from apps.contabilidade.tests import test_dl066_indireto as _indireto
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_pagina_acessivel
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA
ATIVO = TipoConta.ATIVO
PASSIVO = TipoConta.PASSIVO
DESPESA = TipoConta.DESPESA

ATIV = _indireto.ATIV
FINANC = _indireto.FINANC

ANO = _indireto.ANO
MES = _indireto.MES


def _url(empresa, ano=ANO, mes=MES):
    return f"{reverse('contabilidade_web:dfc', args=[empresa.id])}?ano={ano}&mes={mes}"


def _url_classificar(empresa, conta):
    return reverse("contabilidade_web:conta_classificacao_dfc", args=[empresa.id, conta.id])


def _entrar(client, empresa, papel=Papel.GESTOR, nome="usuario-tela"):
    _tela._autenticar(client, empresa.escritorio, f"{nome}-{papel.value}-{empresa.pk}", papel=papel)


def _texto(html):
    """O HTML com toda sequência de espaço/quebra de linha reduzida a um
    espaço: o texto de uma frase pode atravessar linhas do template, e o
    navegador a mostra numa linha só (mesmo molde da tela da DMPL)."""
    return " ".join(html.split())


def _texto_visivel(html):
    """O texto VISÍVEL da página — sem as tags — e normalizado como acima.
    É o que o contador lê no papel, e o único lugar onde "(30.000,00)" existe
    inteiro: o parêntese do negativo fica FORA do `<span>` do valor
    (`_valor_dre.html`), então a forma literal "(30.000,00)" não sobrevive
    no código-fonte do HTML (mesma leitura que `_linhas_da_tabela` faz na
    tela da DMPL)."""
    return _texto(sub(r"<[^>]+>", "", html))


def _cenario_de_referencia(nome):
    """O caso de referência do plano (critério 16), que EMITE com os dois
    métodos conferindo — o mesmo cenário dos testes de servidor."""
    empresa, contas, gestor = _indireto._cenario(nome)
    _indireto._referencia(empresa, contas)
    return empresa, contas, gestor


# Valores do caso de referência (calculados à mão no plano, conferidos por
# test_dl066_indireto): nada aqui recalcula, só mede o que a tela imprime.
VALORES_CRUS_QUE_NAO_PODEM_VAZAR = (
    "85000.00",
    "90000.00",
    "20000.00",
    "15000.00",
    "5000.00",
    "65000.00",
    "105000.00",
    "40000.00",
    "30000.00",
    "10000.00",
)


# ---------------------------------------------------------------------------
# A tela da DFC: navegação, identificação e estados (critério 20)
# ---------------------------------------------------------------------------


def test_a_dfc_renderiza_200_com_a_navegacao_da_empresa_e_a_identificacao_do_documento(
    client,
):
    empresa, _, _ = _cenario_de_referencia("tela-base")
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    # A navegação da empresa: a moldura com os sete atalhos da contabilidade
    # (guarda renderizada, não lista de template) e a pílula da empresa.
    assert_pagina_acessivel(html)
    assert '<span class="contexto-rotulo">Empresa</span>' in html
    assert '<span class="item-atual" aria-current="page">DFC</span>' in html
    # O bloco de identificação do documento, dentro do <thead> (repete em
    # toda página impressa) — classe "Demonstração", item 51 da NBC TG 26.
    cabecalho = _texto(html[html.index("<thead>") : html.index("</thead>")])
    assert "linha-identificacao-do-documento" in cabecalho
    assert "identificacao-do-documento" in cabecalho
    assert empresa.razao_social in cabecalho
    assert "Demonstração dos Fluxos de Caixa" in cabecalho
    assert "Valores em Real (R$)" in cabecalho
    assert "período de 01/01/2026 a 31/03/2026" in cabecalho


def test_o_metodo_direto_mostra_as_tres_atividades_a_variacao_e_o_caixa(client):
    empresa, _, _ = _cenario_de_referencia("tela-direto")
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    texto = _texto_visivel(html)
    for titulo, valor in (
        ("Fluxos de caixa das atividades operacionais", "85.000,00"),
        ("Fluxos de caixa das atividades de investimento", "(30.000,00)"),
        ("Fluxos de caixa das atividades de financiamento", "10.000,00"),
        ("Variação do caixa e equivalentes de caixa no período", "65.000,00"),
        ("Caixa e equivalentes de caixa no início do período", "40.000,00"),
        ("Caixa e equivalentes de caixa no fim do período", "105.000,00"),
    ):
        assert titulo in texto, titulo
        assert valor in texto, valor
    # Conciliação do item 45 — o documento a apresenta, não só a calcula.
    assert "Conciliação do item 45 — variação apurada pelas três atividades" in texto
    assert (
        "Conciliação do item 45 — variação dos saldos das contas de caixa e equivalentes" in texto
    )
    assert "Conciliação do item 45 — diferença entre as duas variações" in texto
    # Negativo entre parênteses (RC-90), não só com o sinal.
    assert "valor-invertido" in html


def test_o_metodo_indireto_mostra_lucro_ajustes_com_item_sinal_e_valor_e_fluxo(client):
    empresa, _, _ = _cenario_de_referencia("tela-indireto")
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    texto = _texto_visivel(html)
    assert "Lucro líquido do período" in texto and "90.000,00" in texto
    # Os ajustes do item 20, cada um com item, conta, nome, descrição, SINAL
    # e valor (o contrato do serviço — a tela não inventa linha nem
    # recalcula nada): a linha inteira, como sai no papel.
    assert (
        "20(a) 1.4 Contas a Receber variação de conta patrimonial operacional - 20.000,00" in texto
    )
    assert "20(b) 5.2 Depreciação item de resultado que não afeta o caixa + 15.000,00" in texto
    assert "Total dos ajustes do método indireto" in texto and "(5.000,00)" in texto
    assert "Fluxo de caixa das atividades operacionais — método indireto" in texto
    assert "Fluxo de caixa das atividades operacionais — método direto" in texto
    assert "Diferença entre os dois métodos" in texto
    assert "Os dois métodos conferem" in texto
    assert "85.000,00" in texto, "o fluxo operacional conferido pelos dois métodos"


def test_o_dinheiro_da_tela_nunca_aparece_como_numero_cru(client):
    """Pt-BR ou nada: o `Decimal`/JSON cru é o sintoma de um template que
    recebeu o valor sem passar pela formatação do módulo (`_valor_dre`)."""
    empresa, _, _ = _cenario_de_referencia("tela-moeda")
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    for cru in VALORES_CRUS_QUE_NAO_PODEM_VAZAR:
        assert cru not in html, cru
    assert "Decimal(" not in html


def test_nenhum_trecho_de_valor_por_acao_aparece_em_nenhuma_parte_do_html(client):
    """CPC 03 (R2), item 52A: na DFC o valor por ação é VEDADO. O produto não
    registra quantidade de ações e a tela nunca monta o campo — a varredura
    é no HTML INTEIRO (documento, pendências, moldura), nos dois desfechos."""
    empresa, _, _ = _cenario_de_referencia("tela-52a")
    _entrar(client, empresa)
    emitida = client.get(_url(empresa)).content.decode()
    assert "por ação" not in emitida.lower()
    assert "por acao" not in emitida.lower()
    # E também no desfecho vetado (o veto é a outra metade do alcance).
    veto, _, _ = _veto_contrapartida_sem_atividade()
    _entrar(client, veto, nome="usuario-52a")
    vetada = client.get(_url(veto)).content.decode()
    assert "por ação" not in vetada.lower()
    assert "por acao" not in vetada.lower()


def test_sem_conta_de_caixa_marcada_a_tela_nomeia_a_ausencia_do_indireto(client):
    """Retorno antecipado do serviço (`operacional_indireto = None`): a tela
    NOMEIA a ausência, nunca apresenta número que a apuração não apurou."""
    empresa = _base._empresa("Empresa sem caixa marcada")
    _base._plano_basico(empresa)
    _entrar(client, empresa)
    html = _texto(client.get(_url(empresa)).content.decode())
    assert "DFC pronta para emissão" in html
    assert "Método indireto não apresentado" in html
    assert "nenhuma conta está marcada como caixa e equivalentes" in html


# ---------------------------------------------------------------------------
# O veto: o veredito é do servidor e a tela só obedece (regra B.2/B.3)
# ---------------------------------------------------------------------------


def _veto_contrapartida_sem_atividade():
    empresa, contas, _ = _servidor._cenario("veto-sem-atividade")
    sem_atividade = _servidor._conta(empresa, "1.9", "Ajuste de Regularização", ATIVO, D)
    _servidor._lancar(
        empresa, date(2026, 3, 10), "Venda", contas["banco"], contas["receita"], "100000.00"
    )
    lancamento = _servidor._lancar(
        empresa, date(2026, 3, 22), "Ajuste", contas["banco"], sem_atividade, "500.00"
    )
    return (
        empresa,
        "lancamentos_sem_atividade",
        [
            "contrapartida sem atividade",
            "1.9 — Ajuste de Regularização",
            reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, lancamento.id]),
        ],
    )


def _veto_conta_com_os_dois_papeis():
    empresa, contas, _ = _servidor._cenario("veto-dois-papeis")
    Conta.objects.filter(pk=contas["emprestimo"].pk).update(caixa_e_equivalentes=True)
    _servidor._lancar(
        empresa, date(2026, 3, 15), "Empréstimo", contas["banco"], contas["emprestimo"], "50000.00"
    )
    return (
        empresa,
        "conta_com_dois_papeis",
        [
            "Conta 2.1 — Empréstimo de Longo Prazo",
            _url_classificar(empresa, contas["emprestimo"]),
        ],
    )


def _veto_indireto_nao_fecha():
    empresa, contas, _ = _indireto._cenario("veto-indireto")
    despesa = _indireto._conta_dfc(
        empresa,
        "5.5",
        "Despesa de Provisão",
        DESPESA,
        D,
        sem_caixa=True,
        dre=ClassificacaoDre.OUTRAS_DESPESAS,
    )
    provisao = _indireto._conta_dfc(empresa, "2.3", "Provisão Operacional", PASSIVO, C, dfc=ATIV)
    _indireto._lancar(
        empresa, date(2026, 3, 10), "Provisão do período", despesa, provisao, "10000.00"
    )
    return empresa, "indireto_nao_fecha", ["diferença 10.000,00"]


VETOS = {
    "lancamentos_sem_atividade": _veto_contrapartida_sem_atividade,
    "conta_com_dois_papeis": _veto_conta_com_os_dois_papeis,
    "indireto_nao_fecha": _veto_indireto_nao_fecha,
}


@pytest.mark.parametrize("chave", sorted(VETOS))
def test_quando_o_veredito_veta_nao_ha_demonstracao_e_o_motivo_nomeado_aparece(client, chave):
    empresa, _, esperado = VETOS[chave]()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    assert resposta.status_code == 200, "veto é a tela respondendo, nunca erro de protocolo"
    html = resposta.content.decode()
    assert "A DFC NÃO pode ser emitida nesta competência" in html
    # O motivo NOMEADO vem do servidor (título da lista, veredito).
    assert _TITULOS_DAS_PENDENCIAS_DA_DFC[chave] in html
    for trecho in esperado:
        assert trecho in html, (chave, trecho)
    # E a demonstração NÃO é montada: sem tabela, sem totais, sem carimbo,
    # sem bloco de identificação impresso (regra B.2/B.3).
    assert "tabela-dfc" not in html
    assert "identificacao-do-documento" not in html
    assert "carimbo" not in html
    assert "DFC pronta para emissão" not in html
    assert "valor-monetario" not in html, "nenhuma célula de valor é montada na recusa"
    assert "Fluxos de caixa das atividades" not in html


def test_o_link_de_correcao_do_veto_so_aparece_para_quem_escritura(client):
    empresa, _, esperado = _veto_conta_com_os_dois_papeis()
    link = esperado[-1]
    _entrar(client, empresa, Papel.PARALEGAL)
    html = client.get(_url(empresa)).content.decode()
    assert "Conta 2.1 — Empréstimo de Longo Prazo" in html, (
        "a pendência aparece para todo papel que lê"
    )
    assert link not in html, "quem só lê não recebe link de correção"
    assert "classificar esta conta" not in html
    assert "peça a quem escritura" in _texto(html)
    _entrar(client, empresa, Papel.ANALISTA, nome="escritor")
    html = client.get(_url(empresa)).content.decode()
    assert link in html and "classificar esta conta" in html


def test_toda_pendencia_da_dfc_tem_titulo_no_servico_e_acao_na_tela():
    """Guarda derivada, no molde da DMPL: lista nova no serviço sem ação
    cadastrada na tela (ou fora do inventário explícito de chaves) reprova —
    nunca uma pendência nasce sem o que dizer ao contador."""
    from apps.contabilidade.views_web import ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DFC_POR_LISTA

    chaves = set(_servidor.CHAVES_ESPERADAS_DAS_PENDENCIAS_DA_DFC)
    assert set(_TITULOS_DAS_PENDENCIAS_DA_DFC) == chaves
    assert set(ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DFC_POR_LISTA) == chaves


# ---------------------------------------------------------------------------
# Classificar a conta: os três campos num formulário só (critério 21)
# ---------------------------------------------------------------------------


def test_classificacao_renderiza_200_com_os_tres_campos(client):
    empresa, contas, _, _, receita = _porta._cenario("tela-form")
    _entrar(client, empresa)
    resposta = client.get(_url_classificar(empresa, receita))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    for campo in (
        "id_caixa_e_equivalentes",
        "id_classificacao_dfc",
        "id_item_de_resultado_sem_caixa",
    ):
        assert f'id="{campo}"' in html, campo
    assert '<option value="operacional"' in html
    assert '<option value="investimento"' in html
    assert '<option value="financiamento"' in html
    assert "Atividade atual: <strong>Sem atividade</strong>" in html
    assert_pagina_acessivel(html)


def test_classificacao_post_grava_os_tres_campos_e_registra_a_trilha(client):
    """A ponte: o POST da tela passa pela MESMA porta de serviço que a API
    (`classificar_conta_na_dfc`) — os três campos chegam como estado desejado
    completo e a trilha registra antes/depois do que mudou."""
    empresa, contas, _, caixa, receita = _porta._cenario("tela-post")
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, receita),
        {
            "caixa_e_equivalentes": "",
            "classificacao_dfc": ATIV,
            "item_de_resultado_sem_caixa": "on",
        },
    )
    assert resposta.status_code == 302
    assert resposta.url == reverse("contabilidade_web:plano_de_contas", args=[empresa.id])
    receita.refresh_from_db()
    assert receita.caixa_e_equivalentes is False
    assert receita.classificacao_dfc == ATIV
    assert receita.item_de_resultado_sem_caixa is True
    registro = RegistroAuditoria.objects.filter(
        acao="conta.classificacao_dfc_alterada", objeto_id=str(receita.pk)
    ).get()
    assert registro.detalhes == {
        "classificacao_dfc": {"antes": None, "depois": ATIV},
        "item_de_resultado_sem_caixa": {"antes": False, "depois": True},
    }


def test_classificacao_em_periodo_fechado_recusa_com_orientacao_e_sem_500(client):
    """A tradução `ClassificacaoAlteraPeriodoFechado` → recusa no formulário
    (200, com a orientação verdadeira do servidor) — nunca um 500, e nada
    gravado. O serviço tem os testes da regra; aqui se prova a PONTE."""
    empresa, contas, gestor, caixa, receita = _porta._cenario("tela-fechado")
    classificar_conta_na_dfc(
        conta=receita,
        caixa_e_equivalentes=False,
        classificacao_dfc=ATIV,
        item_de_resultado_sem_caixa=False,
        usuario=gestor,
    )
    _porta._movimentar(empresa, contas, receita)
    encerrar_competencia(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    _entrar(client, empresa)
    resposta = client.post(
        _url_classificar(empresa, receita),
        {
            "caixa_e_equivalentes": "",
            "classificacao_dfc": FINANC,
            "item_de_resultado_sem_caixa": "",
        },
    )
    assert resposta.status_code == 200, "recusa de regra é a tela respondendo, nunca um 500"
    html = _texto(resposta.content.decode())
    assert 'role="alert"' in html
    assert "Reabra a competência para corrigir a classificação" in html
    receita.refresh_from_db()
    assert receita.classificacao_dfc == ATIV, "o valor gravado permanece"
    assert "Atividade atual: <strong>Operacional</strong>" in html


# ---------------------------------------------------------------------------
# A ponte entre as duas telas novas: classificar pela tela, emitir a DFC
# ---------------------------------------------------------------------------


def test_a_classificacao_feita_na_tela_libera_a_emissao_da_dfc(client):
    """Ponta a ponta: o veto aponta a conta, a tela classifica, a DFC emite —
    com o número novo na atividade operacional."""
    empresa, contas, gestor = _indireto._cenario("tela-ponte")
    sem_atividade = _indireto._conta_dfc(empresa, "1.9", "Ajuste de Regularização", ATIVO, D)
    _indireto._lancar(
        empresa, date(2026, 3, 10), "Venda", contas["caixa"], contas["receita"], "100000.00"
    )
    _indireto._lancar(
        empresa, date(2026, 3, 22), "Ajuste", contas["caixa"], sem_atividade, "500.00"
    )
    _entrar(client, empresa)
    assert "A DFC NÃO pode ser emitida" in client.get(_url(empresa)).content.decode()
    resposta = client.post(
        _url_classificar(empresa, sem_atividade),
        {
            "caixa_e_equivalentes": "",
            "classificacao_dfc": ATIV,
            "item_de_resultado_sem_caixa": "",
        },
    )
    assert resposta.status_code == 302
    html = _texto(client.get(_url(empresa)).content.decode())
    assert "DFC pronta para emissão" in html
    assert "Fluxos de caixa das atividades operacionais" in html
    assert "100.500,00" in html
