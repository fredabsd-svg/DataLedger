"""DL-062 (TELA) — a continuação da DMPL: dica da diferença com o Balanço (G4),
tela que não depende de lista fixa de colunas/linhas e a DMPL de 13 colunas no
papel.

O servidor (`desenvolvedor-pleno`, outra cópia isolada) acrescenta a coluna
"Dividendo adicional proposto" e a linha de mesmo nome. Esta base ainda não as
tem, então os testes de contrato injetam, por `monkeypatch` da apuração, uma
coluna de GRUPO NOVO e uma linha NOVA no formato que `apurar_dmpl` documenta
(`colunas` com grupo/grupo_titulo, `linhas` com título): a tela tem de obedecer
ao contrato, não a uma lista. Nomes fictícios de propósito — se algum trecho da
tela dependesse de um nome conhecido, o teste reprovaria.

Os testes de NAVEGADOR usam o Chromium do Playwright e o `pdftotext`, e são
PULADOS, com o motivo dito, onde faltam (`DL_CHROMIUM_EXECUTAVEL` aponta o
executável).
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.db import models

from apps.contabilidade import views_web
from apps.contabilidade.models import (
    GRUPO_DA_CLASSIFICACAO_DMPL,
    ClassificacaoDmpl,
    GrupoDaDmpl,
    LancamentoContabil,
)
from apps.contabilidade.tests.test_dl061_dmpl import COL, LUCROS, PL, D, _caso_a, _conta, _lancar
from apps.contabilidade.tests.test_dl061_tela_dmpl import (
    _entrar,
    _linhas_da_tabela,
    _texto,
    _url,
    _url_classificar,
    _veto_conta_de_pl_sem_coluna,
    _veto_diferenca_de_fechamento,
)
from apps.contabilidade.tests.test_dl061_tela_dmpl_correcoes import (
    LARGURA_UTIL_A4_PAISAGEM_PX,
    PONTOS_DE_8_MM,
    _abrir,
    _doze_colunas,
    _navegador,
    _palavras_do_pdf,
)
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

TITULO_DA_SEM_COLUNA = "Conta do patrimônio líquido com movimento ou saldo e sem coluna da DMPL"
TITULO_DA_DIFERENCA = "Diferença entre a DMPL e o Balanço"
TRECHO_DA_RETIFICADORA = "FORA do grupo “Patrimônio Líquido” do plano de contas"


# ---------------------------------------------------------------------------
# G4 (M4 da reconferência da DL-061) — a dica da diferença com o Balanço
# ---------------------------------------------------------------------------


def _veto_com_conta_sem_coluna_e_diferenca():
    """Conta de PL movimentada e SEM coluna: o Balanço a soma ao patrimônio
    líquido e a DMPL não a mostra. A apuração REAL entrega, juntas, a
    pendência da conta e a diferença de fechamento (a própria conta é a causa
    da diferença)."""
    empresa, _ = _veto_conta_de_pl_sem_coluna()
    return empresa


def test_cenario_real_entrega_a_conta_sem_coluna_e_a_diferenca_juntas(client):
    """Pré-condição dos testes seguintes, com a apuração real: se o servidor
    deixar de entregar as duas pendências juntas, este teste acusa que o
    cenário saiu do ar — e não que a dica ficou certa por acaso."""
    empresa = _veto_com_conta_sem_coluna_e_diferenca()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    assert TITULO_DA_SEM_COLUNA in html
    assert TITULO_DA_DIFERENCA in html


@pytest.mark.parametrize(
    "cenario",
    [_veto_com_conta_sem_coluna_e_diferenca, lambda: _veto_diferenca_de_fechamento()[0]],
    ids=["conta_de_pl_sem_coluna", "subconta_de_reserva_movimentada"],
)
def test_com_conta_sem_coluna_a_diferenca_aponta_para_a_conta_listada_acima(client, cenario):
    empresa = cenario()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    texto = _texto(html)

    assert views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA in texto
    assert "provavelmente decorre da(s) conta(s) listada(s) acima" in texto
    # A dica da retificadora é a causa de OUTRO caso: aqui ela mandaria o
    # contador procurar no lugar errado.
    assert TRECHO_DA_RETIFICADORA not in texto
    assert "conta retificadora do patrimônio líquido" not in texto
    # "acima" é verdade na tela: a lista da conta vem antes da diferença.
    assert html.index(TITULO_DA_SEM_COLUNA) < html.index(TITULO_DA_DIFERENCA)
    # E a pendência da conta continua com a ação própria dela.
    assert "Dê uma coluna da DMPL a cada conta listada" in texto


@pytest.mark.parametrize("papel", [Papel.GESTOR, Papel.PARALEGAL])
def test_a_dica_da_diferenca_vale_para_quem_escritura_e_para_quem_so_le(client, papel):
    empresa = _veto_com_conta_sem_coluna_e_diferenca()
    _entrar(client, empresa, papel)
    texto = _texto(client.get(_url(empresa)).content.decode())
    assert views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA in texto
    assert TRECHO_DA_RETIFICADORA not in texto


def _veto_so_com_a_diferenca():
    """A retificadora de PL cadastrada FORA do grupo, mas COM coluna (BL-604):
    o Balanço a soma, a DMPL a subtrai, e nenhuma conta fica sem coluna — a
    diferença é a única pendência."""
    empresa, contas, _ = _caso_a()
    solta = _conta(
        empresa, "9", "Tesouraria solta na raiz", PL, D, dmpl=COL.ACOES_OU_QUOTAS_EM_TESOURARIA
    )
    _lancar(empresa, date(2026, 3, 20), "Compra de ações", solta, contas["caixa"], "2000.00")
    return empresa


def test_diferenca_sozinha_mantem_a_dica_da_retificadora_fora_do_grupo(client):
    """A regra inversa: sem a pendência da conta sem coluna, a causa mais
    provável continua sendo a retificadora fora do grupo (N11 da DL-061)."""
    empresa = _veto_so_com_a_diferenca()
    _entrar(client, empresa)
    html = client.get(_url(empresa)).content.decode()
    texto = _texto(html)
    assert TITULO_DA_DIFERENCA in html and TITULO_DA_SEM_COLUNA not in html
    assert TRECHO_DA_RETIFICADORA in texto
    assert views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA not in texto
    assert "provavelmente decorre da(s) conta(s) listada(s) acima" not in texto


def _com_pendencias(monkeypatch, *, sem_coluna, diferenca):
    """Faz a apuração entregar as duas listas escolhidas — a conta sem coluna
    com a forma que o servidor documenta, e uma diferença de coluna."""
    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        pendencias = dmpl["pendencias"]
        if sem_coluna:
            pendencias["contas_do_patrimonio_liquido_sem_coluna"] = [
                {
                    "conta_id": 999_999,
                    "conta": "3.9",
                    "nome": "Conta de teste",
                    "saldo_inicial": Decimal("0"),
                    "movimento_no_exercicio": True,
                    "classificavel": True,
                    "orientacao": "",
                }
            ]
        if diferenca:
            pendencias["diferenca_de_fechamento"] = [
                {
                    "coluna": "reserva_legal",
                    "titulo": "Reserva legal",
                    "saldo_na_dmpl": Decimal("1250.00"),
                    "saldo_no_balanco": Decimal("1750.00"),
                    "diferenca": Decimal("-500.00"),
                    "contas": [],
                }
            ]
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)


@pytest.mark.parametrize(
    ("sem_coluna", "dica_da_retificadora"), [(True, False), (False, True)], ids=["com", "sem"]
)
def test_a_dica_acompanha_a_presenca_da_pendencia_da_conta_com_apuracao_substituida(
    client, monkeypatch, sem_coluna, dica_da_retificadora
):
    """As duas pendências juntas e a diferença sozinha, com o mesmo cenário-base
    e a apuração substituída — o que muda de um caso para o outro é só a
    presença da lista da conta sem coluna."""
    empresa, _, _ = _caso_a()
    _com_pendencias(monkeypatch, sem_coluna=sem_coluna, diferenca=True)
    _entrar(client, empresa)
    texto = _texto(client.get(_url(empresa)).content.decode())
    assert (TRECHO_DA_RETIFICADORA in texto) is dica_da_retificadora
    assert (
        views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA in texto
    ) is not dica_da_retificadora


def test_conta_sem_coluna_sozinha_nao_acrescenta_dica_de_diferenca(client, monkeypatch):
    empresa, _, _ = _caso_a()
    _com_pendencias(monkeypatch, sem_coluna=True, diferenca=False)
    _entrar(client, empresa)
    texto = _texto(client.get(_url(empresa)).content.decode())
    assert TITULO_DA_SEM_COLUNA in texto and TITULO_DA_DIFERENCA not in texto
    assert views_web.ACAO_DA_DIFERENCA_DE_FECHAMENTO_COM_CONTA_SEM_COLUNA not in texto


def test_a_acao_do_lancamento_ambiguo_nao_manda_dividir_lancamento_efetivado():
    """DL-062/G3 na tela: lançamento efetivado não se altera. A saída é estornar
    e relançar cada evento em lançamento próprio."""
    acao = views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA["lancamentos_ambiguos"]
    assert "Divida" not in acao and "divida" not in acao
    assert "estorne o lançamento listado" in acao
    assert "cada evento em um lançamento próprio" in acao


# ---------------------------------------------------------------------------
# A tela obedece ao contrato (colunas com grupo, linhas com título) e não a
# uma lista — coluna de grupo novo e linha nova, injetadas por stub
# ---------------------------------------------------------------------------

COLUNA_NOVA = {
    "chave": "coluna_nova_do_teste",
    "titulo": "Coluna Inventada Pelo Teste",
    "grupo": "grupo_novo_do_teste",
    "grupo_titulo": "Grupo Inventado Pelo Teste",
}
LINHA_NOVA = ("linha_nova_do_teste", "Linha Inventada Pelo Teste")


def _id_de_um_lancamento(empresa):
    return LancamentoContabil.objects.filter(empresa=empresa).order_by("id").first().id


def _com_coluna_e_linha_novas(
    monkeypatch, empresa, *, coluna, linha, valor, depois_de="dividendos"
):
    """Faz `apurar_dmpl` entregar UMA coluna a mais, no fim, e UMA linha a mais,
    logo depois de `depois_de` (ou antes do saldo final, se a linha não
    existir), no formato documentado em `apurar_dmpl`.

    A linha move `valor` da coluna de lucros acumulados para a coluna nova
    (total da linha zero), como a proposta de dividendo adicional; o saldo
    final e a conciliação acompanham, para a tabela continuar fechando.
    """
    id_do_lancamento = _id_de_um_lancamento(empresa)
    zero = Decimal("0")
    original = views_web.apurar_dmpl

    def apurar(**kwargs):
        dmpl = original(**kwargs)
        chave = coluna["chave"]
        dmpl["colunas"] = [*dmpl["colunas"], dict(coluna)]
        for item in dmpl["linhas"]:
            item["valores"][chave] = zero
        chave_da_linha, titulo_da_linha = linha
        nova = {
            "chave": chave_da_linha,
            "titulo": titulo_da_linha,
            "valores": {c["chave"]: zero for c in dmpl["colunas"]},
            "total": zero,
            "lancamentos": {LUCROS: [id_do_lancamento], chave: [id_do_lancamento]},
        }
        nova["valores"][LUCROS] = -valor
        nova["valores"][chave] = valor
        chaves = [item["chave"] for item in dmpl["linhas"]]
        posicao = chaves.index(depois_de) + 1 if depois_de in chaves else len(chaves) - 1
        dmpl["linhas"].insert(posicao, nova)
        final = dmpl["linhas"][-1]
        final["valores"][LUCROS] -= valor
        final["valores"][chave] += valor
        por_coluna = dmpl["conciliacao"]["por_coluna"]
        por_coluna[LUCROS]["saldo_na_dmpl"] -= valor
        por_coluna[LUCROS]["saldo_no_balanco"] -= valor
        por_coluna[chave] = {
            "saldo_na_dmpl": valor,
            "saldo_no_balanco": valor,
            "diferenca": zero,
        }
        return dmpl

    monkeypatch.setattr(views_web, "apurar_dmpl", apurar)


def _cabecalhos(html):
    """Texto de cada <th> do <thead> (fora o bloco de identificação), em ordem."""
    thead = re.search(r"<thead>(.*?)</thead>", html, re.S).group(1)
    sem_identificacao = re.sub(
        r'<tr class="linha-identificacao-do-documento">.*?</tr>', "", thead, flags=re.S
    )
    return [
        " ".join(re.sub(r"<[^>]+>", " ", th).split())
        for th in re.findall(r"<th[^>]*>(.*?)</th>", sem_identificacao, re.S)
    ]


def test_coluna_de_grupo_novo_ganha_cabecalho_de_grupo_na_ordem_do_contrato(client, monkeypatch):
    empresa, _, _ = _caso_a()
    _com_coluna_e_linha_novas(
        monkeypatch, empresa, coluna=COLUNA_NOVA, linha=LINHA_NOVA, valor=Decimal("30.00")
    )
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    html = resposta.content.decode()
    tabela = resposta.context["tabela"]

    # Cabeçalho de grupo e de coluna vêm do contrato, na ordem em que chegaram.
    assert [g["titulo"] for g in tabela["grupos"]][-1] == "Grupo Inventado Pelo Teste"
    # No HTML: 1ª linha do cabeçalho (grupos, na ordem do contrato, e o Total) e,
    # depois, a 2ª linha (colunas dos grupos) — a nova é a última de todas.
    cabecalhos = _cabecalhos(html)
    assert cabecalhos.index("Grupo Inventado Pelo Teste") < cabecalhos.index("Total")
    assert cabecalhos[-1] == "Coluna Inventada Pelo Teste"
    # Grupo com UMA coluna de título diferente não é fundido: tem dois níveis.
    ultimo = tabela["grupos"][-1]
    assert ultimo["fundido"] is False and len(ultimo["colunas"]) == 1
    assert tabela["colunas_do_segundo_nivel"][-1]["titulo"] == "Coluna Inventada Pelo Teste"
    # A largura do bloco de identificação acompanha a quantidade de colunas.
    assert tabela["quantidade_de_colunas_da_tabela"] == len(tabela["colunas"]) + 2
    assert f'colspan="{len(tabela["colunas"]) + 2}"' in html


def test_linha_nova_aparece_na_posicao_do_contrato_com_valores_nas_colunas_certas(
    client, monkeypatch
):
    empresa, _, _ = _caso_a()
    _com_coluna_e_linha_novas(
        monkeypatch, empresa, coluna=COLUNA_NOVA, linha=LINHA_NOVA, valor=Decimal("30.00")
    )
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    tabela = resposta.context["tabela"]
    titulos = [linha["titulo"] for linha in tabela["linhas"]]
    assert titulos[titulos.index("Dividendos") + 1] == "Linha Inventada Pelo Teste"
    assert titulos[-1] == "Saldo no fim do período"

    linha = tabela["linhas"][titulos.index("Linha Inventada Pelo Teste")]
    chaves = [c["chave"] for c in tabela["colunas"]]
    por_chave = dict(zip(chaves, linha["celulas"], strict=True))
    assert por_chave[LUCROS]["valor"]["negativo"] is True
    assert por_chave[COLUNA_NOVA["chave"]]["valor"]["negativo"] is False
    assert por_chave[chaves[0]] is None  # coluna sem movimento nesta linha: "—"
    html = resposta.content.decode()
    corpo = _linhas_da_tabela(html)
    nova = next(celulas for celulas in corpo if celulas[0] == "Linha Inventada Pelo Teste")
    # Histórico + todas as colunas + Total: uma célula por coluna do contrato.
    assert len(nova) == len(chaves) + 2
    assert "(30,00)" in nova[1 + chaves.index(LUCROS)]
    assert nova[1 + chaves.index(COLUNA_NOVA["chave"])].startswith("30,00")
    assert nova[-1].startswith("0,00")
    # A célula da coluna nova leva aos lançamentos de origem, como qualquer outra.
    assert 'href="#origem-linha_nova_do_teste-coluna_nova_do_teste"' in html
    assert 'id="origem-linha_nova_do_teste-coluna_nova_do_teste"' in html
    # E a conferência com o Balanço lista a coluna nova, com o título do contrato.
    assert "Coluna Inventada Pelo Teste" in _texto(html.split("Conferência com o Balanço")[1])


def test_coluna_nova_empurra_a_dmpl_para_paisagem_pela_contagem_do_contrato(client, monkeypatch):
    """Quatro colunas ainda cabem em retrato; a quinta, vinda do contrato, não."""
    empresa, _, _ = _caso_a()
    _entrar(client, empresa)
    antes = client.get(_url(empresa)).context
    quantidade = len(antes["tabela"]["colunas"])
    assert (quantidade > views_web._COLUNAS_DA_DMPL_QUE_CABEM_EM_RETRATO) is antes[
        "imprime_em_paisagem"
    ]
    _com_coluna_e_linha_novas(
        monkeypatch, empresa, coluna=COLUNA_NOVA, linha=LINHA_NOVA, valor=Decimal("1.00")
    )
    depois = client.get(_url(empresa)).context
    assert len(depois["tabela"]["colunas"]) == quantidade + 1
    assert (len(depois["tabela"]["colunas"]) > views_web._COLUNAS_DA_DMPL_QUE_CABEM_EM_RETRATO) is (
        depois["imprime_em_paisagem"]
    )


def _enums_com_membro_novo():
    """Réplicas dos dois enums com UM membro novo de GRUPO novo no fim — o que
    o servidor fará quando acrescentar a coluna. Mesmo mecanismo do Django
    (`TextChoices` por API funcional)."""
    grupo = models.TextChoices(
        "GrupoFalso",
        [(m.name, (m.value, m.label)) for m in GrupoDaDmpl]
        + [("NOVO", ("grupo_novo_do_teste", "Grupo Inventado Pelo Teste"))],
    )
    coluna = models.TextChoices(
        "ColunaFalsa",
        [(m.name, (m.value, m.label)) for m in ClassificacaoDmpl]
        + [("NOVA", ("coluna_nova_do_teste", "Coluna Inventada Pelo Teste"))],
    )
    mapa = {coluna(c.value): grupo(GRUPO_DA_CLASSIFICACAO_DMPL[c].value) for c in ClassificacaoDmpl}
    mapa[coluna.NOVA] = grupo.NOVO
    return grupo, coluna, mapa


def test_formulario_de_classificacao_oferece_membro_novo_no_grupo_novo_sem_lista_fixa(
    client, monkeypatch
):
    empresa, contas, _ = _caso_a()
    grupo, coluna, mapa = _enums_com_membro_novo()
    monkeypatch.setattr(views_web, "GrupoDaDmpl", grupo)
    monkeypatch.setattr(views_web, "ClassificacaoDmpl", coluna)
    monkeypatch.setattr(views_web, "GRUPO_DA_CLASSIFICACAO_DMPL", mapa)
    _entrar(client, empresa)
    html = client.get(_url_classificar(empresa, contas["reserva_legal"])).content.decode()

    assert '<optgroup label="Grupo Inventado Pelo Teste">' in html
    assert '<option value="coluna_nova_do_teste">Coluna Inventada Pelo Teste</option>' in html
    # O grupo novo vem DEPOIS dos que já existiam, e a opção fica dentro dele.
    rotulos = re.findall(r'<optgroup label="([^"]+)">', html)
    assert rotulos == [m.label for m in grupo]
    bloco_novo = html.split('<optgroup label="Grupo Inventado Pelo Teste">')[1].split(
        "</optgroup>"
    )[0]
    assert "coluna_nova_do_teste" in bloco_novo and bloco_novo.count("<option") == 1
    # Todo membro de hoje continua oferecido (nada some por causa do novo).
    for membro in ClassificacaoDmpl:
        assert f'value="{membro.value}"' in html


def test_toda_coluna_de_hoje_aparece_no_formulario_sob_o_grupo_do_enum(client):
    """Sem stub: a lista de grupos e de opções do formulário é a do enum
    (derivada), seja ele de 12 ou de 13 colunas."""
    empresa, contas, _ = _caso_a()
    _entrar(client, empresa)
    html = client.get(_url_classificar(empresa, contas["reserva_legal"])).content.decode()
    rotulos_esperados = list(
        dict.fromkeys(GrupoDaDmpl(GRUPO_DA_CLASSIFICACAO_DMPL[c]).label for c in ClassificacaoDmpl)
    )
    assert re.findall(r'<optgroup label="([^"]+)">', html) == rotulos_esperados
    for membro in ClassificacaoDmpl:
        grupo = GrupoDaDmpl(GRUPO_DA_CLASSIFICACAO_DMPL[membro]).label
        bloco = html.split(f'<optgroup label="{grupo}">')[1].split("</optgroup>")[0]
        assert f'value="{membro.value}"' in bloco, (membro, grupo)


# ---------------------------------------------------------------------------
# Papel: a DMPL de 13 colunas na A4 paisagem (navegador real)
# ---------------------------------------------------------------------------


def _treze_colunas(monkeypatch):
    """O cenário de 12 colunas (as do item 111A, valores de seis dígitos) mais a
    13ª, "Dividendo adicional proposto", em grupo próprio — a forma que o
    servidor entregará. A proposta de 30.000,00 sai dos lucros acumulados."""
    empresa, contas = _doze_colunas()
    _com_coluna_e_linha_novas(
        monkeypatch,
        empresa,
        coluna={
            "chave": "dividendo_adicional_proposto",
            "titulo": "Dividendo adicional proposto",
            "grupo": "demais_contas_exigidas",
            "grupo_titulo": "Demais contas exigidas",
        },
        linha=("dividendo_adicional_proposto", "Dividendo adicional proposto"),
        valor=Decimal("30000.00"),
    )
    return empresa, contas


def _medir_o_pdf(html, pdf):
    with _navegador() as navegador:
        contexto, pagina = _abrir(
            navegador, html, largura=LARGURA_UTIL_A4_PAISAGEM_PX, media="print"
        )
        try:
            largura_do_documento = pagina.evaluate("document.documentElement.scrollWidth")
            pagina.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True)
        finally:
            contexto.close()
    return largura_do_documento, _palavras_do_pdf(pdf)


def test_navegador_treze_colunas_cabem_na_a4_paisagem_com_margem_direita_de_8mm(
    client, monkeypatch, tmp_path
):
    """A 13ª coluna não pode empurrar o "Total" para fora da folha: o texto mais
    à direita fica a pelo menos 8 mm da borda (`xMax` ≤ largura − 23 pt) e a
    tabela cabe NATIVAMENTE na área útil (sem o navegador reduzir a letra
    abaixo do piso de 11 px)."""
    empresa, _ = _treze_colunas(monkeypatch)
    _entrar(client, empresa)
    resposta = client.get(_url(empresa))
    html = resposta.content.decode()
    assert resposta.context["imprime_em_paisagem"] is True
    assert len(resposta.context["tabela"]["colunas"]) == 13

    pdf = tmp_path / "dmpl13.pdf"
    largura_do_documento, paginas = _medir_o_pdf(html, pdf)

    assert largura_do_documento <= LARGURA_UTIL_A4_PAISAGEM_PX + 1, (
        f"a tabela de 13 colunas tem {largura_do_documento}px e a área útil tem "
        f"{LARGURA_UTIL_A4_PAISAGEM_PX}px: o navegador reduziria a letra"
    )
    assert paginas, "o PDF não tem páginas"
    assert 840 < paginas[0]["largura"] < 844, "A4 paisagem (842 pt)"
    # Uma folha só: a nota do rodapé não vai sozinha para uma 2ª folha, onde a
    # identificação do emitente não se repete (ela só acompanha a tabela).
    assert len(paginas) == 1, f"a DMPL de 13 colunas saiu em {len(paginas)} folhas"
    for pagina_do_pdf in paginas:
        x_max = max(x_max for _, x_max, _ in pagina_do_pdf["palavras"])
        x_min = min(x_min for x_min, _, _ in pagina_do_pdf["palavras"])
        assert x_max <= pagina_do_pdf["largura"] - PONTOS_DE_8_MM, (
            f"xMax={x_max:.1f} pt passa de {pagina_do_pdf['largura'] - PONTOS_DE_8_MM:.1f} pt"
        )
        assert x_min >= PONTOS_DE_8_MM, f"xMin={x_min:.1f} pt (margem esquerda < 8 mm)"
    textos = {texto for _, _, texto in paginas[0]["palavras"]}
    # A 13ª coluna e o Total estão de fato no papel, e a proposta com o valor.
    assert {"Total", "Demais", "exigidas", "30.000,00", "296.000,00"} <= textos
