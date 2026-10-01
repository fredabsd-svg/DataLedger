"""DL-061, fatia 1 — rodada ÚNICA de correção da TELA (achados N3, N4, N5,
N9 [parte de tela], N10 e N11 da auditoria
docs/auditorias/2026-10-01-dl-061-rodada-1.md, mais a mensagem de recusa da
marca de adoção antecipada, N6, vista da tela).

Cada teste aqui REPROVA sem a correção correspondente e passa com ela (a
prova de que reprova está no relatório da rodada).

**Contratos novos do SERVIDOR** (entregues pelo `desenvolvedor-pleno`, em
outra cópia isolada; nesta base ainda não existem):

- `dmpl["avisos"]["resultado_na_conta_de_passagem"]` — `[]` ou
  `[{"valor": Decimal, "contas": [{"conta_id", "conta", "nome", "saldo"}]}]`;
- `classificavel: bool` e `orientacao: str` nos itens de
  `dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]`;
- `definir_adocao_antecipada_da_nbc_tg_51` levanta `ParametroContabilInvalido`
  quando nenhum exercício anterior a 2027 começa dentro da vigência.

Os testes de TELA montam esses dicts por `monkeypatch` da apuração (a tela só
obedece ao que o servidor entrega). Os testes de INTEGRAÇÃO, com a apuração
REAL, têm o prefixo `test_integracao_` e conferem o contrato de ponta a ponta;
nasceram marcados como falha esperada enquanto as duas cópias corriam em
paralelo e viraram testes comuns na integração.

Os testes de NAVEGADOR (`_navegador`) usam o Chromium do Playwright e o
`pdftotext`, e são PULADOS, com o motivo dito, onde faltam.
"""

import mimetypes
import os
import re
import shutil
import subprocess
from contextlib import contextmanager
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.contabilidade import views_web
from apps.contabilidade.models import (
    ClassificacaoDlpa,
    Conta,
    LancamentoContabil,
    PeriodicidadeZeramento,
)
from apps.contabilidade.services import (
    estornar_lancamento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    MES,
    PL,
    C,
    D,
    _caso_a,
    _conta,
    _contas_do_caso_b,
    _empresa,
    _gestor,
    _lancar,
    _parametro_do_zeramento,
    _plano_basico,
)
from apps.contabilidade.tests.test_dl061_tela_dmpl import (
    RAIZ,
    _entrar,
    _marcar,
    _texto,
    _url,
    _url_parametros,
    _veto_conta_de_pl_sem_coluna,
    _veto_par_sem_regra,
    _vigencia,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

# ---------------------------------------------------------------------------
# Auxiliares
# ---------------------------------------------------------------------------


def _com_aviso_de_passagem(monkeypatch, itens):
    """Faz a apuração entregar o aviso `resultado_na_conta_de_passagem` (o
    contrato novo do servidor), sem mexer no resto."""
    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        dmpl["avisos"] = {**dmpl["avisos"], "resultado_na_conta_de_passagem": itens}
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)


def _item_de_passagem(contas, valor="25000.00"):
    return {
        "valor": Decimal(valor),
        "contas": [
            {
                "conta_id": conta.id,
                "conta": conta.codigo,
                "nome": conta.nome,
                "saldo": Decimal(valor),
            }
            for conta in contas
        ],
    }


def _caso_a_com_transferencia_estornada():
    """O cenário do auditor (caso 3): o caso A e, depois, o ESTORNO da
    transferência do resultado para lucros acumulados (procedimento de
    correção do projeto, RC-103). A conta "Resultado do Exercício" fica com
    25.000,00 e a DMPL perde esse valor em relação ao Balanço."""
    empresa, contas, gestor = _caso_a()
    etapa_2 = [
        lancamento
        for lancamento in LancamentoContabil.objects.filter(empresa=empresa)
        if "Zeramento" in lancamento.historico and "contas de resultado" not in lancamento.historico
    ]
    assert len(etapa_2) == 1, "o cenário depende do histórico gravado pelo zeramento"
    estornar_lancamento(etapa_2[0], criado_por=gestor, data=date(2026, 3, 31))
    return empresa, contas, gestor


# ---------------------------------------------------------------------------
# N3 — saldo na conta de passagem: aviso na tela E nota no papel
# ---------------------------------------------------------------------------


def test_o_aviso_de_passagem_aparece_na_tela_com_valor_contas_e_onde_conferir(client, monkeypatch):
    empresa, contas, _ = _caso_a()
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem([contas["resultado"]])])
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    html = resposta.content.decode()
    texto = _texto(html)

    assert resposta.status_code == 200
    # Nunca veta: a demonstração é montada.
    assert "DMPL pronta para emissão" in html and "tabela-dmpl" in html
    aviso = _texto(html[html.index('id="aviso-da-dmpl"') :])
    assert "Resultado do exercício na conta de passagem, ainda não transferido" in aviso
    assert "Há saldo de R$ 25.000,00 na conta de resultado do exercício" in aviso
    assert "ainda não transferido para lucros ou prejuízos acumulados" in aviso
    assert "Conta 3.0 — Resultado do Exercício: saldo 25.000,00" in aviso
    # Onde conferir: Diário e Fechamento da própria empresa.
    assert reverse("contabilidade_web:diario", args=[empresa.id]) in html
    assert reverse("contabilidade_web:fechamento", args=[empresa.id]) in html
    # É conferência de bancada: não sai no papel.
    posicao = html.index('id="aviso-da-dmpl"')
    assert "mensagem--somente-tela" in html[html.rindex("<div", 0, posicao) : posicao]
    assert "Com ressalva" in texto


def test_a_faixa_de_pronta_para_emissao_aponta_para_o_aviso_de_passagem(client, monkeypatch):
    """A faixa verde sozinha diz "pronta" e some a explicação do total que
    não bate com o Balanço: a ressalva é TEXTO na própria faixa e leva ao
    aviso (âncora que existe na página)."""
    empresa, contas, _ = _caso_a()
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem([contas["resultado"]])])
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    faixa = html[html.index("DMPL pronta para emissão") :]
    faixa = faixa[: faixa.index("</div>")]
    assert 'href="#aviso-da-dmpl"' in faixa
    assert "Com ressalva" in faixa
    assert html.count('id="aviso-da-dmpl"') == 1


def test_a_nota_do_papel_diz_o_valor_e_que_o_total_difere_do_balanco(client, monkeypatch):
    empresa, contas, _ = _caso_a()
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem([contas["resultado"]])])
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()

    notas = html[html.index('<div class="notas-do-documento">') :]
    notas = _texto(notas[: notas.index("</div>")])
    assert (
        "Há saldo de R$ 25.000,00 na conta de resultado do exercício, ainda não transferido "
        "para lucros ou prejuízos acumulados. Por isso o total desta demonstração difere do "
        "patrimônio líquido do Balanço Patrimonial de 31/03/2026 nesse valor."
    ) in notas
    # A nota é parte do DOCUMENTO: está antes dos blocos de bancada, que não saem no papel.
    assert html.index("nota-do-resultado-na-conta-de-passagem") < html.index("bloco--somente-tela")


def test_a_nota_de_saldo_devedor_na_passagem_usa_parenteses(client, monkeypatch):
    empresa, contas, _ = _caso_a()
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem([contas["resultado"]], "-3000.00")])
    _entrar(client, empresa)
    notas = _texto(client.get(_url(empresa)).content.decode())
    assert "Há saldo de R$ (3.000,00) na conta de resultado do exercício" in notas
    assert "(valor entre parênteses é saldo devedor)" in notas


def test_sem_o_aviso_do_servidor_nada_e_impresso_sobre_a_passagem(client):
    """Controle POSITIVO do outro lado: o caso A fecha sem saldo na passagem;
    o papel não ganha nota nenhuma e a faixa não ganha ressalva."""
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "DMPL pronta para emissão" in html
    assert "nota-do-resultado-na-conta-de-passagem" not in html
    assert "Com ressalva" not in html
    assert "conta de resultado do exercício, ainda não transferido" not in _texto(html)


def test_vetada_por_outro_motivo_a_tela_mostra_o_aviso_e_nao_monta_a_nota(client, monkeypatch):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    contas_do_resultado = list(Conta.objects.filter(empresa=empresa, codigo="3.0"))
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem(contas_do_resultado)])
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "A DMPL NÃO pode ser emitida nesta competência" in html
    assert "Resultado do exercício na conta de passagem, ainda não transferido" in html
    assert "nota-do-resultado-na-conta-de-passagem" not in html, "sem demonstração, sem nota"
    assert "Com ressalva" not in html


def test_integracao_estorno_da_transferencia_gera_aviso_e_nota_com_a_apuracao_real(client):
    """Cenário do auditor (caso 3), com a apuração REAL: o contrato novo do
    servidor produz o aviso de 25.000,00; a tela o mostra e o papel o anota."""
    empresa, _, _ = _caso_a_com_transferencia_estornada()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "DMPL pronta para emissão" in html
    assert "Há saldo de R$ 25.000,00 na conta de resultado do exercício" in _texto(html)
    assert "nota-do-resultado-na-conta-de-passagem" in html
    assert "Com ressalva" in html


# ---------------------------------------------------------------------------
# N4 — conta de PL que não aceita coluna: sem link, com orientação
# ---------------------------------------------------------------------------

ORIENTACAO = (
    "Conta classificada como dividendo na DLPA não tem coluna na DMPL: mova-a para o "
    "passivo ou aguarde a decisão sobre o dividendo adicional proposto."
)


def _sem_coluna_possivel(monkeypatch, classificavel, orientacao=ORIENTACAO):
    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        for item in dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]:
            item["classificavel"] = classificavel
            item["orientacao"] = orientacao
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)


def test_conta_que_nao_aceita_coluna_nao_recebe_link_e_mostra_a_orientacao(client, monkeypatch):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    _sem_coluna_possivel(monkeypatch, classificavel=False)
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url(empresa)).content.decode()

    link_de_coluna, texto = esperado[1], _texto(html)
    assert "Conta 3.8 — PL com movimento" in html
    assert link_de_coluna not in html, "o servidor recusaria essa ação: a tela não a oferece"
    assert "definir a coluna da DMPL" not in html
    assert "Como resolver:" in html and ORIENTACAO in texto
    # E a ação da lista deixa de mandar "dar uma coluna a cada conta listada".
    assert "Dê uma coluna da DMPL a cada conta listada" not in html
    assert "As contas com orientação própria não aceitam coluna" in texto


def test_conta_que_aceita_coluna_continua_com_o_link_e_sem_orientacao(client, monkeypatch):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    _sem_coluna_possivel(monkeypatch, classificavel=True, orientacao="")
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url(empresa)).content.decode()
    assert esperado[1] in html and "definir a coluna da DMPL" in html
    assert "Como resolver:" not in html
    assert "Dê uma coluna da DMPL a cada conta listada" in html


def test_com_uma_conta_de_cada_tipo_so_a_classificavel_tem_link(client, monkeypatch):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    contas_proprias = Conta.objects.get(empresa=empresa, codigo="3.8")
    dividendo = _conta(
        empresa,
        "3.9",
        "Dividendos Propostos (PL)",
        PL,
        D,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=Conta.objects.get(empresa=empresa, codigo="3"),
    )
    caixa = Conta.objects.get(empresa=empresa, codigo="1.1")
    _lancar(empresa, date(2026, 3, 12), "Dividendos propostos", dividendo, caixa, "50.00")

    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        for item in dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]:
            item["classificavel"] = item["conta_id"] == contas_proprias.id
            item["orientacao"] = "" if item["classificavel"] else ORIENTACAO
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url(empresa)).content.decode()
    url_dividendo = reverse(
        "contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, dividendo.id]
    )
    assert esperado[1] in html, "a conta classificável mantém o link"
    assert url_dividendo not in html, "a que não aceita coluna não"
    assert "Dê uma coluna da DMPL às contas que têm o link ao lado." in _texto(html)
    assert html.count("Como resolver:") == 1


@pytest.mark.parametrize("papel", [Papel.PARALEGAL, Papel.GESTOR])
def test_a_orientacao_aparece_para_quem_so_le_e_para_quem_escritura(client, monkeypatch, papel):
    empresa, _ = _veto_conta_de_pl_sem_coluna()
    _sem_coluna_possivel(monkeypatch, classificavel=False)
    _entrar(client, empresa, papel)
    assert ORIENTACAO in _texto(client.get(_url(empresa)).content.decode())


def test_sem_orientacao_do_servidor_a_tela_ainda_nao_oferece_o_link(client, monkeypatch):
    empresa, esperado = _veto_conta_de_pl_sem_coluna()
    _sem_coluna_possivel(monkeypatch, classificavel=False, orientacao="")
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url(empresa)).content.decode()
    assert esperado[1] not in html
    assert "Esta conta não aceita coluna na DMPL" in _texto(html)


def test_integracao_conta_de_pl_classificada_como_dividendo_nao_recebe_link_de_coluna(client):
    """Caso 4 do auditor, com a apuração REAL: conta de PL classificada como
    dividendo na DLPA e movimentada. O servidor a marca como não
    classificável; a tela não oferece o link e traz a orientação."""
    empresa, contas, _ = _caso_a()
    dividendo = _conta(
        empresa,
        "3.5",
        "Dividendos Propostos (PL)",
        PL,
        D,
        dlpa=ClassificacaoDlpa.DIVIDENDO,
        pai=contas["pl"],
    )
    _lancar(
        empresa, date(2026, 3, 15), "Dividendos propostos", dividendo, contas["caixa"], "100.00"
    )
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url(empresa)).content.decode()
    assert "Conta 3.5 — Dividendos Propostos (PL)" in html
    assert (
        reverse("contabilidade_web:conta_classificacao_dmpl", args=[empresa.id, dividendo.id])
        not in html
    )
    assert "Como resolver:" in html


# ---------------------------------------------------------------------------
# N9 (parte de tela) — link de lançamento de outra empresa nunca é gerado
# ---------------------------------------------------------------------------


def _lancamento_de_outra_empresa():
    alheia = _empresa("Empresa Alheia Ltda")
    contas = _plano_basico(alheia)
    return _lancar(
        alheia,
        date(2026, 3, 9),
        "SEGREDO-DA-OUTRA-EMPRESA",
        contas["caixa"],
        contas["capital"],
        "1.00",
    )


def test_links_de_origem_omitem_o_lancamento_de_outra_empresa():
    """Mata o mutante N10 do auditor (omitir o filtro "o lançamento pertence ao
    mapa da empresa"): sem o filtro, o id alheio dá `KeyError` ao montar o link."""
    empresa, _, _ = _caso_a()
    meu = LancamentoContabil.objects.filter(empresa=empresa).first()
    alheio = _lancamento_de_outra_empresa()
    mapa_da_empresa = {meu.id: {"descricao": "31/03/2026 — Meu lançamento"}}

    links, resto = views_web._links_de_lancamentos_da_pendencia(
        empresa, [meu.id, alheio.id], mapa_da_empresa
    )

    assert [link["rotulo"] for link in links] == ["lançamento de 31/03/2026 — Meu lançamento"]
    assert resto == 0
    assert links[0]["url"] == reverse(
        "contabilidade_web:lancamento_detalhe", args=[empresa.id, meu.id]
    )


def test_pendencia_com_lancamento_alheio_injetado_nao_gera_link_nem_quebra_a_tela(
    client, monkeypatch
):
    empresa, _ = _veto_par_sem_regra()
    alheio = _lancamento_de_outra_empresa()
    original = views_web.apurar_dmpl

    def com_id_alheio(**kwargs):
        dmpl = original(**kwargs)
        for item in dmpl["pendencias"]["pares_de_colunas_sem_regra"]:
            item["lancamentos"] = [*item["lancamentos"], alheio.id]
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", com_id_alheio)
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    html = resposta.content.decode()

    assert resposta.status_code == 200
    assert "26/03/2026 — Entre reservas" in html, "o lançamento da própria empresa tem link"
    assert "SEGREDO-DA-OUTRA-EMPRESA" not in html
    assert reverse("contabilidade_web:lancamento_detalhe", args=[empresa.id, alheio.id]) not in html
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[alheio.empresa_id, alheio.id])
        not in html
    )


# ---------------------------------------------------------------------------
# N11 — a mensagem da diferença de fechamento cita a causa conhecida
# ---------------------------------------------------------------------------


def test_a_diferenca_de_fechamento_cita_a_retificadora_fora_do_grupo_de_pl():
    acao = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA["diferenca_de_fechamento"]
    texto = _texto(acao)
    assert "retificadora do patrimônio líquido" in texto
    assert "FORA do grupo “Patrimônio Líquido” do plano de contas" in texto
    assert "capital a integralizar" in texto and "ações em tesouraria" in texto
    assert "Não deveria acontecer" not in acao and "não deveria acontecer" not in acao


def test_a_tela_do_veto_mostra_a_causa_conhecida_da_diferenca(client):
    """A retificadora de PL cadastrada FORA do grupo (BL-604): o Balanço a
    soma, a DMPL a subtrai; o veto é o correto e a mensagem tem de apontar
    para a causa, não para "dado íntegro"."""
    empresa, contas, _ = _caso_a()
    solta = _conta(
        empresa, "9", "Tesouraria solta na raiz", PL, D, dmpl=COL.ACOES_OU_QUOTAS_EM_TESOURARIA
    )
    _lancar(empresa, date(2026, 3, 20), "Compra de ações", solta, contas["caixa"], "2000.00")
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert "A DMPL NÃO pode ser emitida nesta competência" in html
    assert "FORA do grupo “Patrimônio Líquido” do plano de contas" in _texto(html)
    assert "dado íntegro" not in html


# ---------------------------------------------------------------------------
# N6 (vista da tela) — recusa da marca de adoção antecipada, com mensagem clara
# ---------------------------------------------------------------------------


def test_a_tela_de_parametros_avisa_quando_a_marca_tem_efeito(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    texto = _texto(client.get(_url_parametros(empresa)).content.decode())
    assert (
        "só tem efeito em vigência que cubra o dia 1º de janeiro de algum exercício anterior a 2027"
        in texto
    )
    assert "o sistema recusa a marcação e diz por quê" in texto


def test_recusa_do_servidor_na_marca_aparece_como_erro_e_nada_e_gravado(client, monkeypatch):
    from apps.contabilidade.services import ParametroContabilInvalido

    mensagem = (
        "Nenhum exercício anterior a 2027 começa dentro da vigência iniciada em 01/03/2026: "
        "a marca não teria efeito. Registre uma vigência que cubra o dia 1º de janeiro."
    )

    def recusa(**kwargs):
        raise ParametroContabilInvalido(mensagem)

    monkeypatch.setattr(views_web, "definir_adocao_antecipada_da_nbc_tg_51", recusa)
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    resposta = client.post(
        _url_parametros(empresa),
        {
            "acao": "adocao_antecipada_nbc_tg_51",
            "vigencia_id": str(_vigencia(empresa).id),
            "adota": "1",
        },
        follow=True,
    )
    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert mensagem in _texto(html)
    assert "Erro:" in html or "mensagem-error" in html
    assert "marcada na vigência" not in html, "a recusa não pode parecer sucesso"
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False


def test_integracao_marca_em_vigencia_iniciada_depois_de_1_de_janeiro_e_recusada(client):
    """Caso 6 do auditor, com o serviço REAL: vigência iniciada em 01/03/2026
    não cobre o 1º de janeiro de nenhum exercício anterior a 2027."""
    empresa = _empresa("Empresa Entrou No Meio Do Ano Ltda")
    contas = _plano_basico(empresa)
    gestor = _gestor(empresa, "gestor-meio-do-ano")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2026, 3, 1),
        usuario=gestor,
    )
    _entrar(client, empresa, Papel.GESTOR)
    resposta = _marcar(client, empresa, "1")
    assert resposta.status_code == 302
    pagina = client.get(_url_parametros(empresa)).content.decode()
    assert "mensagem-error" in pagina or "Erro:" in pagina
    assert "marcada na vigência" not in pagina
    assert _vigencia(empresa).adota_nbc_tg_51_antecipadamente is False


# ---------------------------------------------------------------------------
# N10 — tela de parâmetros: a tabela rola, a página não (HTML)
# ---------------------------------------------------------------------------


def test_a_tabela_de_vigencias_esta_num_envolucro_de_rolagem_acessivel(client):
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url_parametros(empresa)).content.decode()
    envolucro = html[: html.index('<table class="tabela-dados">')]
    envolucro = envolucro[envolucro.rindex("<div") :]
    assert 'class="tabela-com-rolagem-horizontal"' in envolucro
    assert 'role="region"' in envolucro and 'tabindex="0"' in envolucro
    assert (
        'aria-label="Vigências de parâmetro contábil — tabela com rolagem horizontal"' in envolucro
    )
    # E o envolucro fecha logo depois da tabela, antes do texto de apoio.
    depois = html[html.index("</table>") :]
    assert depois.index("</div>") < depois.index("Adoção antecipada da NBC TG 51:")


# ---------------------------------------------------------------------------
# N5 — margem da folha impressa (CSS)
# ---------------------------------------------------------------------------


def _margens_do_page_da_dmpl():
    css = (RAIZ / "static/css/base.css").read_text(encoding="utf-8")
    bloco = re.search(r"@page dmpl-paisagem \{(.*?)\n\}", css, re.S)
    assert bloco, "@page dmpl-paisagem não encontrado"
    declaracao = re.search(r"(?m)^\s*margin:\s*([^;]+);", bloco.group(1))
    assert declaracao, "o @page da DMPL precisa de margem EXPLÍCITA (N5)"
    valores = declaracao.group(1).split()
    assert all(valor.endswith("mm") for valor in valores), valores
    mm = [float(valor[:-2]) for valor in valores]
    topo = mm[0]
    direita = mm[1] if len(mm) > 1 else mm[0]
    base = mm[2] if len(mm) > 2 else topo
    esquerda = mm[3] if len(mm) > 3 else direita
    return {"topo": topo, "direita": direita, "base": base, "esquerda": esquerda}, bloco.group(1)


def test_o_page_da_dmpl_declara_paisagem_e_margem_lateral_de_pelo_menos_8mm():
    margens, bloco = _margens_do_page_da_dmpl()
    assert "size: A4 landscape;" in bloco
    assert margens["direita"] >= 8 and margens["esquerda"] >= 8
    assert margens["topo"] >= 5 and margens["base"] >= 5


# ---------------------------------------------------------------------------
# Navegador real (Chromium do Playwright + pdftotext)
# ---------------------------------------------------------------------------

LARGURA_UTIL_A4_PAISAGEM_PX = 1054  # (297 mm − 2 × 9 mm) a 96 dpi, arredondado para cima
PONTOS_DE_8_MM = 23  # 8 mm = 22,7 pt; a checagem usa 23 pt (o contrato da auditoria)


@contextmanager
def _navegador():
    """O Chromium do Playwright, ou `pytest.skip` com o motivo. É um gerenciador
    de contexto (não uma fixture) de propósito: o Playwright síncrono mantém um
    laço `asyncio` aberto na thread, e o Django recusa operação de banco com
    laço aberto — por isso os testes buscam TUDO no banco (cenário e HTML)
    antes de abrir o navegador."""
    playwright_api = pytest.importorskip("playwright.sync_api")
    if shutil.which("pdftotext") is None:
        pytest.skip("pdftotext (poppler-utils) ausente: não há como medir o PDF")
    executavel = os.environ.get("DL_CHROMIUM_EXECUTAVEL") or None
    with playwright_api.sync_playwright() as playwright:
        try:
            navegador = playwright.chromium.launch(executable_path=executavel)
        except Exception as exc:  # noqa: BLE001 — qualquer falha de lançamento é infraestrutura
            pytest.skip(f"Chromium do Playwright indisponível: {str(exc).splitlines()[0]}")
        try:
            yield navegador
        finally:
            navegador.close()


def _abrir(navegador, html, *, largura, altura=900, media="screen"):
    """Abre o HTML renderizado pelo Django numa página do Chromium, servindo
    `/static/**` do disco do projeto (o CSS e as fontes REAIS)."""
    contexto = navegador.new_context(viewport={"width": largura, "height": altura})
    pagina = contexto.new_page()

    def rota(route):
        url = route.request.url
        if url == "http://testserver/pagina":
            route.fulfill(body=html, content_type="text/html; charset=utf-8")
        elif "/static/" in url:
            caminho = RAIZ / "static" / url.split("/static/", 1)[1].split("?", 1)[0]
            if caminho.is_file():
                tipo = mimetypes.guess_type(str(caminho))[0] or "application/octet-stream"
                route.fulfill(path=str(caminho), content_type=tipo)
            else:
                route.fulfill(status=404, body="")
        else:
            route.abort()

    pagina.route("**/*", rota)
    pagina.goto("http://testserver/pagina")
    pagina.emulate_media(media=media)
    return contexto, pagina


def _palavras_do_pdf(caminho):
    saida = subprocess.run(
        ["pdftotext", "-bbox", str(caminho), "-"], capture_output=True, text=True, check=True
    ).stdout
    paginas = []
    for largura, _altura, corpo in re.findall(
        r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', saida, re.S
    ):
        palavras = [
            (float(x_min), float(x_max), texto)
            for x_min, x_max, texto in re.findall(
                r'xMin="([\d.]+)" yMin="[\d.]+" xMax="([\d.]+)" yMax="[\d.]+">(.*?)</word>', corpo
            )
        ]
        paginas.append({"largura": float(largura), "palavras": palavras})
    return paginas


def _doze_colunas():
    """O cenário de 12 colunas do auditor: as doze colunas do item 111A,
    valores de até seis dígitos, zeramento de verdade."""
    empresa = _empresa("Empresa Doze Colunas Ltda")
    c = _plano_basico(empresa)
    c.update(_contas_do_caso_b(empresa, c["pl"]))
    gestor = _gestor(empresa, "gestor-doze-colunas")
    _parametro_do_zeramento(empresa, c, gestor)
    extra = {}
    for codigo, nome, coluna, dlpa in [
        ("3.7", "Ágio", COL.AGIO_NA_EMISSAO_DE_ACOES, None),
        (
            "3.8",
            "Alienação de partes beneficiárias",
            COL.ALIENACAO_DE_PARTES_BENEFICIARIAS_E_BONUS_DE_SUBSCRICAO,
            None,
        ),
        (
            "3.9",
            "Reserva Estatutária",
            COL.RESERVA_ESTATUTARIA,
            ClassificacaoDlpa.RESERVA_ESTATUTARIA,
        ),
        (
            "3.10",
            "Reserva Contingências",
            COL.RESERVA_PARA_CONTINGENCIAS,
            ClassificacaoDlpa.RESERVA_PARA_CONTINGENCIAS,
        ),
        (
            "3.11",
            "Reserva Incentivos",
            COL.RESERVA_DE_INCENTIVOS_FISCAIS,
            ClassificacaoDlpa.RESERVA_DE_INCENTIVOS_FISCAIS,
        ),
        (
            "3.12",
            "Reserva Retenção",
            COL.RESERVA_DE_RETENCAO_DE_LUCROS,
            ClassificacaoDlpa.RESERVA_DE_RETENCAO_DE_LUCROS,
        ),
        (
            "3.13",
            "Reserva a Realizar",
            COL.RESERVA_DE_LUCROS_A_REALIZAR,
            ClassificacaoDlpa.RESERVA_DE_LUCROS_A_REALIZAR,
        ),
    ]:
        extra[coluna] = _conta(empresa, codigo, nome, PL, C, dmpl=coluna, dlpa=dlpa, pai=c["pl"])
    caixa = c["caixa"]
    _lancar(empresa, date(2025, 12, 31), "cap", caixa, c["capital"], "100000.00")
    _lancar(empresa, date(2026, 1, 5), "aumento", caixa, c["capital"], "20000.00")
    _lancar(
        empresa, date(2026, 1, 6), "agio", caixa, extra[COL.AGIO_NA_EMISSAO_DE_ACOES], "4000.00"
    )
    _lancar(
        empresa,
        date(2026, 1, 7),
        "alienacao",
        caixa,
        extra[COL.ALIENACAO_DE_PARTES_BENEFICIARIAS_E_BONUS_DE_SUBSCRICAO],
        "1000.00",
    )
    _lancar(empresa, date(2026, 2, 1), "ajuste", c["imobilizado"], c["ajustes"], "3000.00")
    _lancar(empresa, date(2026, 2, 2), "tesouraria", c["tesouraria"], caixa, "2000.00")
    _lancar(empresa, date(2026, 3, 5), "receita", caixa, c["receita"], "250000.00")
    _lancar(empresa, date(2026, 3, 6), "despesa", c["despesa"], caixa, "50000.00")
    zerar_resultado(empresa=empresa, ano=ANO, mes=MES, usuario=gestor)
    destinos = [
        (COL.RESERVA_LEGAL, "10000.00"),
        (COL.RESERVA_ESTATUTARIA, "1000.00"),
        (COL.RESERVA_PARA_CONTINGENCIAS, "2000.00"),
        (COL.RESERVA_DE_INCENTIVOS_FISCAIS, "3000.00"),
        (COL.RESERVA_DE_RETENCAO_DE_LUCROS, "4000.00"),
        (COL.RESERVA_DE_LUCROS_A_REALIZAR, "5000.00"),
    ]
    for coluna, valor in destinos:
        conta = c["reserva_legal"] if coluna == COL.RESERVA_LEGAL else extra[coluna]
        _lancar(empresa, date(2026, 3, 31), "destinação", c["lucros"], conta, valor)
    _lancar(empresa, date(2026, 3, 31), "dividendos", c["lucros"], c["dividendos"], "30000.00")
    _lancar(empresa, date(2026, 3, 31), "incorporação", c["lucros"], c["capital"], "20000.00")
    return empresa, c


def test_navegador_doze_colunas_cabem_na_a4_paisagem_com_margem_direita_de_8mm(client, tmp_path):
    """Caso 5 do auditor (N5): o PDF da DMPL de 12 colunas, impresso pelo
    Chromium, tem o texto mais à direita a pelo menos 8 mm da borda (`xMax` ≤
    largura − 23 pt) — e a tabela cabe NATIVAMENTE na área útil, isto é, sem o
    navegador reduzir a folha (reduzir levaria a letra abaixo do piso de 11 px)."""
    empresa, _ = _doze_colunas()
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    html = resposta.content.decode()
    assert resposta.context["imprime_em_paisagem"] is True
    assert len(resposta.context["tabela"]["colunas"]) == 12

    pdf = tmp_path / "dmpl12.pdf"
    with _navegador() as navegador:
        contexto, pagina = _abrir(
            navegador, html, largura=LARGURA_UTIL_A4_PAISAGEM_PX, media="print"
        )
        try:
            # 1) Sem encolher: o documento não é mais largo que a área útil da folha.
            largura_do_documento = pagina.evaluate("document.documentElement.scrollWidth")
            # 2) O PDF real, na folha que o CSS declara.
            pagina.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True)
        finally:
            contexto.close()
    assert largura_do_documento <= LARGURA_UTIL_A4_PAISAGEM_PX + 1, (
        f"a tabela de 12 colunas tem {largura_do_documento}px e a área útil tem "
        f"{LARGURA_UTIL_A4_PAISAGEM_PX}px: o navegador reduziria a letra"
    )

    paginas = _palavras_do_pdf(pdf)
    assert paginas, "o PDF não tem páginas"
    assert 840 < paginas[0]["largura"] < 844, "A4 paisagem (842 pt)"
    for pagina_do_pdf in paginas:
        x_max = max(x_max for _, x_max, _ in pagina_do_pdf["palavras"])
        x_min = min(x_min for x_min, _, _ in pagina_do_pdf["palavras"])
        assert x_max <= pagina_do_pdf["largura"] - PONTOS_DE_8_MM, (
            f"xMax={x_max:.1f} pt passa de {pagina_do_pdf['largura'] - PONTOS_DE_8_MM:.1f} pt"
        )
        assert x_min >= PONTOS_DE_8_MM, f"xMin={x_min:.1f} pt (margem esquerda < 8 mm)"
    # E a última coluna ("Total") está de fato no papel.
    textos = {texto for _, _, texto in paginas[0]["palavras"]}
    assert "Total" in textos and "296.000,00" in textos


def test_navegador_a_nota_da_passagem_sai_no_pdf_e_o_aviso_de_bancada_nao(
    client, monkeypatch, tmp_path
):
    empresa, contas, _ = _caso_a()
    _com_aviso_de_passagem(monkeypatch, [_item_de_passagem([contas["resultado"]])])
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    pdf = tmp_path / "dmpl_nota.pdf"
    with _navegador() as navegador:
        contexto, pagina = _abrir(navegador, html, largura=1000, media="print")
        try:
            pagina.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True)
        finally:
            contexto.close()
    texto = " ".join(
        subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, text=True).stdout.split()
    )
    assert "Há saldo de R$ 25.000,00 na conta de resultado do exercício" in texto
    assert "difere do patrimônio líquido do Balanço Patrimonial de 31/03/2026" in texto
    # O aviso de bancada (com os links) e a ressalva da faixa não saem no papel.
    assert "abrir o Fechamento" not in texto and "Com ressalva" not in texto
    assert "não impede a emissão da DMPL" not in texto


def test_navegador_parametros_contabeis_sem_rolagem_horizontal_da_pagina_a_390px(client):
    """Caso 10 do auditor (N10): a 390 px a PÁGINA não rola na horizontal
    (`scrollWidth` = 390) — a tabela de vigências rola dentro do envolucro, e
    todas as colunas continuam alcançáveis por ele."""
    empresa, _, _ = _caso_a()
    _entrar(client, empresa, Papel.GESTOR)
    html = client.get(_url_parametros(empresa)).content.decode()
    with _navegador() as navegador:
        contexto, pagina = _abrir(navegador, html, largura=390, altura=844)
        try:
            medidas = pagina.evaluate(
                """() => {
                    const envolucro = document.querySelector('.tabela-com-rolagem-horizontal');
                    return {
                        pagina: document.documentElement.scrollWidth,
                        janela: document.documentElement.clientWidth,
                        envolucro: envolucro.clientWidth,
                        tabela: envolucro.querySelector('table').scrollWidth,
                    };
                }"""
            )
            # O envolucro é alcançável por teclado.
            pagina.focus(".tabela-com-rolagem-horizontal")
            focado = pagina.evaluate(
                "document.activeElement.classList.contains('tabela-com-rolagem-horizontal')"
            )
        finally:
            contexto.close()
    assert medidas["janela"] == 390
    assert medidas["pagina"] == 390, f"a página rola na horizontal: {medidas}"
    assert medidas["tabela"] > medidas["envolucro"], (
        "a tabela é mais larga e rola DENTRO do envolucro"
    )
    assert focado
