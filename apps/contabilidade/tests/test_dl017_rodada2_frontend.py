"""Correções da rodada 2 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-2.md) atribuídas ao `especialista-frontend`:
R2-1 (bloqueador, DE-029), R2-2, R2-3, R2-5, R2-6, R2-8, R2-9 e R2-10.

R2-4 e R2-7 (o byte NUL e o dígito Unicode em `apps.core.dinheiro`) são do
`desenvolvedor-pleno` e não têm teste aqui. Dados 100% sintéticos, criados
nos próprios testes.
"""

import json
import re
import shutil
import subprocess
import tempfile
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório rodada 2", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Rodada 2 Ltda", cnpj="11122233000183"
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
        username="gestora-r2", email="gestora-r2@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-r2", password="senha-forte-123")


def _url_lancamento(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


# ---------------------------------------------------------------------------
# R2-1 (BLOQUEADOR) — DE-029: texto digitado -> valor gravado
# ---------------------------------------------------------------------------

# A MESMA tabela de 12 valores que a rodada 2 da auditoria mediu
# ("1.000" gravava 1,00" — 9 de 12 gravavam 1/1000 do valor digitado). O
# terceiro elemento é o valor Decimal esperado no banco, OU `None` se o
# texto deve ser RECUSADO (nunca gravado com outro número).
TABELA_R2_1_TEXTO_DIGITADO_PARA_VALOR_GRAVADO = [
    ("1.000", Decimal("1000.00")),
    ("1.500", Decimal("1500.00")),
    ("2.000", Decimal("2000.00")),
    ("2.500", Decimal("2500.00")),
    ("10.000", Decimal("10000.00")),
    ("25.000", Decimal("25000.00")),
    ("1.250", Decimal("1250.00")),
    ("150.000", Decimal("150000.00")),
    ("3.750", Decimal("3750.00")),
    ("1.000.000", Decimal("1000000.00")),
    ("1.234", Decimal("1234.00")),
    ("1.999", Decimal("1999.00")),
    ("1.000,00", Decimal("1000.00")),
    # Controles: formato CANÔNICO DA API (ponto DECIMAL), não pt-BR — a
    # DE-029 recusa de propósito, para não ter que ADIVINHAR entre duas
    # leituras do mesmo texto.
    ("10.00", None),
    ("1.00", None),
    ("100.00", None),
]


@pytest.mark.parametrize("texto,esperado", TABELA_R2_1_TEXTO_DIGITADO_PARA_VALOR_GRAVADO)
def test_texto_digitado_vira_exatamente_o_valor_gravado_ou_e_recusado(client, cen, texto, esperado):
    """DE-029 — o teste que é o CORAÇÃO da decisão. Instituído porque o
    teste de equivalência tela<->API que a DE-027 já exigia
    (`test_tela_e_api_recusam_o_mesmo_texto_nunca_500` /
    `test_tela_e_api_aceitam_o_mesmo_texto_quando_e_pt_br_valido`, em
    test_dl017_rodada1_correcoes.py) NÃO PODIA pegar o bloqueador R2-1 por
    construção: ele compara tela e API DEPOIS da tradução de locale, e o
    defeito estava NA tradução. Este teste compara o TEXTO DIGITADO com o
    VALOR GRAVADO diretamente: ou é exatamente o que o texto significa em
    pt-BR, ou a requisição é recusada com 400 — nunca 302 com outro
    número.

    Reprodução ANTES desta correção (isolando a função pré-fix, `git show
    HEAD:apps/contabilidade/views_web.py`, mesma lógica de `9b22b03`/
    `ab77b80`): 9 dos 12 primeiros valores gravavam 1/1000 do texto
    digitado ("1.000" -> grava 1,00); só "1.000.000" era recusado (por
    acidente: dois pontos não casavam o regex antigo, não por julgamento
    de gramática).
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    chave = f"r2-1-{texto}"
    dados = {
        "acao": "gravar",
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": "R2-1: texto digitado -> valor gravado",
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": texto,
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": texto,
    }
    resposta = client.post(_url_lancamento(cen), dados)

    if esperado is None:
        assert resposta.status_code == 400, (texto, resposta.status_code)
        assert LancamentoContabil.objects.count() == antes
        return

    assert resposta.status_code == 302, (texto, resposta.status_code, resposta.content)
    lancamento = LancamentoContabil.objects.get(chave_idempotencia=chave)
    valores_gravados = {item.valor for item in lancamento.itens.all()}
    assert valores_gravados == {esperado}, (texto, valores_gravados)


# ---------------------------------------------------------------------------
# R2-2 — 'nivel' do Balancete: mesmo padrão [0-9] da API, sem 500 por URL
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nivel_bruto",
    [
        "9" * 5000,  # antes: 500 (ValueError do int(), limite de conversão do Python)
        "9" * 4301,  # idem, um dígito acima do limite
        "０１",  # dígito Unicode fullwidth — antes: 200, interpretado como 1
        "٢",  # dígito Unicode índico-arábico — antes: 200, interpretado como 2
        "abc",  # controle: já recusado antes, continua recusado
    ],
)
def test_nivel_com_digito_unicode_ou_magnitude_absurda_nunca_500(client, cen, nivel_bruto):
    """R2-2: `bruto.isdigit()` aceita QUALQUER dígito decimal Unicode (a
    mesma classe do achado 2 da rodada 1, em outro campo), e nada
    protegia o `int()` seguinte de um texto de milhares de dígitos —
    `ValueError: Exceeds the limit (4300 digits) for integer string
    conversion`, um 500 alcançável só por uma URL colada/favoritada.
    Agora a tela reaproveita `_PADRAO_NIVEL_SIMPLES` (`[0-9]+`) da API, e
    o `int()` está protegido por `try/except`.
    """
    _login(client, cen)
    resposta = client.get(
        reverse("contabilidade_web:balancete", args=[cen["empresa"].id]),
        {"nivel": nivel_bruto},
    )
    assert resposta.status_code == 400, (nivel_bruto[:30], resposta.status_code)
    assert "Nível" in resposta.content.decode()


def test_nivel_no_limite_de_conversao_do_python_da_mensagem_de_intervalo_nao_500(client, cen):
    """Controle: exatamente 4300 dígitos (o limite do Python, `int()` não
    levanta) é um número absurdamente grande mas CONVERSÍVEL — a tela
    recusa pela regra de NEGÓCIO (`nivel > NIVEL_MAXIMO`), não por um 500.
    """
    _login(client, cen)
    resposta = client.get(
        reverse("contabilidade_web:balancete", args=[cen["empresa"].id]),
        {"nivel": "9" * 4300},
    )
    assert resposta.status_code == 400
    assert "entre 1 e" in resposta.content.decode()


# ---------------------------------------------------------------------------
# R2-3 — num_linhas malformado não pode fazer a view ler menos linhas do
# que o POST realmente contém
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("num_linhas_malformado", ["abc", "", "2.5", "1e1", "None"])
def test_num_linhas_malformado_ainda_le_todas_as_partidas_do_post(
    client, cen, num_linhas_malformado
):
    """R2-3: a correção da rodada 1 (BL-91) só fechou a porta de CIMA —
    um `num_linhas` INFLADO já não truncava mais o lote. A porta de BAIXO
    continuava aberta: `num_linhas` malformado, vazio ou simplesmente
    menor do que o conteúdo real do POST fazia a view cair no valor
    padrão (`LINHAS_INICIAIS_LANCAMENTO`, 4) e ler só as 4 primeiras
    linhas, descartando em silêncio as duas últimas — o MESMO dano do
    achado 5 (77,00 de débito e 77,00 de crédito somem, o lote fecha
    "balanceado"), pela causa que o comentário da rodada 1 negava
    explicitamente. Agora a view deriva a quantidade de linhas do PRÓPRIO
    POST (`_maior_indice_de_linha_no_post`), nunca do campo oculto.
    """
    _login(client, cen)
    empresa = cen["empresa"]
    dados = {
        "acao": "gravar",
        "num_linhas": num_linhas_malformado,
        "data": timezone.localdate().isoformat(),
        "historico": f"R2-3 num_linhas={num_linhas_malformado!r}",
        "chave_idempotencia": f"r2-3-{num_linhas_malformado}",
        # 4 primeiras linhas batendo em 20,00/20,00 — o que o código
        # ANTIGO já conseguia ler (LINHAS_INICIAIS_LANCAMENTO = 4).
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "10,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "10,00",
        "conta_3": str(cen["caixa"].id),
        "tipo_3": "debito",
        "valor_3": "10,00",
        "conta_4": str(cen["receita"].id),
        "tipo_4": "credito",
        "valor_4": "10,00",
        # Linhas 5 e 6: o que a view ANTIGA descartava em silêncio.
        "conta_5": str(cen["caixa"].id),
        "tipo_5": "debito",
        "valor_5": "77,00",
        "conta_6": str(cen["receita"].id),
        "tipo_6": "credito",
        "valor_6": "77,00",
    }
    resposta = client.post(reverse("contabilidade_web:lancamento_novo", args=[empresa.id]), dados)
    assert resposta.status_code == 302, (
        num_linhas_malformado,
        resposta.status_code,
        resposta.content,
    )
    lancamento = LancamentoContabil.objects.get(chave_idempotencia=f"r2-3-{num_linhas_malformado}")
    assert lancamento.itens.count() == 6, (num_linhas_malformado, lancamento.itens.count())
    total_debito = sum(item.valor for item in lancamento.itens.all() if item.tipo == "debito")
    total_credito = sum(item.valor for item in lancamento.itens.all() if item.tipo == "credito")
    assert total_debito == total_credito == Decimal("97.00"), (
        num_linhas_malformado,
        total_debito,
        total_credito,
    )


def test_comentario_sobre_o_piso_de_leitura_nao_afirma_mais_o_contrario_do_codigo(client, cen):
    """Achado 13/R2-3: o comentário antigo em `views_web.py` afirmava que
    o piso de leitura "nunca faz esta view LER menos campos do que os
    que o cliente possa ter enviado" — e a tabela do R2-3 provava o
    contrário (cinco casos em que fazia exatamente isso). Este teste não
    lê o comentário (comentário não é testável por si só); ele é a prova
    EXECUTÁVEL de que a afirmação agora é verdadeira — mesmo cenário do
    teste acima, verificado uma vez mais como documentação do que o
    comentário reescrito passa a descrever.
    """
    _login(client, cen)
    empresa = cen["empresa"]
    dados = {
        "acao": "gravar",
        "num_linhas": "abc",
        "data": timezone.localdate().isoformat(),
        "historico": "prova do comentário reescrito",
        "chave_idempotencia": "r2-3-comentario",
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "1,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "1,00",
        "conta_3": str(cen["caixa"].id),
        "tipo_3": "debito",
        "valor_3": "1,00",
        "conta_4": str(cen["receita"].id),
        "tipo_4": "credito",
        "valor_4": "1,00",
        "conta_5": str(cen["caixa"].id),
        "tipo_5": "debito",
        "valor_5": "50,00",
        "conta_6": str(cen["receita"].id),
        "tipo_6": "credito",
        "valor_6": "50,00",
    }
    resposta = client.post(reverse("contabilidade_web:lancamento_novo", args=[empresa.id]), dados)
    assert resposta.status_code == 302
    lancamento = LancamentoContabil.objects.get(chave_idempotencia="r2-3-comentario")
    assert lancamento.itens.count() == 6


# ---------------------------------------------------------------------------
# R2-5 — a conferência ANUNCIA a linha excluída do total, não só soma o resto
# ---------------------------------------------------------------------------


def test_adicionar_linha_anuncia_quantas_linhas_ficam_fora_do_total(client, cen):
    """R2-5: antes, uma linha INCOMPLETA (tipo e valor preenchidos, conta
    esquecida) era excluída do total em SILÊNCIO — o rodapé mostrava os
    dois lados "batendo" (1.000,00 / 1.000,00) enquanto 500,00 ficavam
    preenchidos ao lado, ignorados, sem uma palavra. "Batendo" é
    justamente o sinal que convida a gravar. Agora a exclusão é
    ANUNCIADA, mantendo a soma parcial (que continua sendo útil).
    """
    _login(client, cen)
    resposta = client.post(
        _url_lancamento(cen),
        {
            "acao": "adicionar_linha",
            "num_linhas": "4",
            "data": timezone.localdate().isoformat(),
            "historico": "R2-5: linha incompleta some do total",
            "chave_idempotencia": "r2-5-conf",
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "1.000,00",
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": "1.000,00",
            # Linha 3: tipo e valor preenchidos, CONTA esquecida.
            "tipo_3": "debito",
            "valor_3": "500,00",
        },
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)
    valores_rodape = re.findall(r'class="valor-monetario">([^<]+)<', rodape)
    # A soma PARCIAL continua correta (a intenção da correção da rodada 1
    # é preservada) — só as duas linhas completas entram.
    assert valores_rodape == ["1.000,00", "1.000,00"], valores_rodape
    # E agora a exclusão é ANUNCIADA — antes esta asserção não tinha como
    # passar, porque não existia texto nenhum sobre exclusão na página.
    assert "1 linha" in conteudo
    assert "NÃO entram" in conteudo
    assert LancamentoContabil.objects.count() == 0


def test_adicionar_linha_sem_linha_incompleta_nao_mostra_aviso(client, cen):
    """Controle negativo: com todas as linhas preenchidas (ou em branco,
    nunca parcialmente preenchidas), nenhum aviso de exclusão aparece —
    a correção não pode inventar um aviso onde não há nada excluído.
    """
    _login(client, cen)
    resposta = client.post(
        _url_lancamento(cen),
        {
            "acao": "adicionar_linha",
            "num_linhas": "4",
            "data": timezone.localdate().isoformat(),
            "historico": "sem linha incompleta",
            "chave_idempotencia": "r2-5-sem-aviso",
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "10,00",
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": "10,00",
        },
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "NÃO entram" not in conteudo
    assert "linha-aviso-conferencia" not in conteudo


# ---------------------------------------------------------------------------
# R2-10 — a recusa por teto não perde as partidas que excederam o limite
# ---------------------------------------------------------------------------


def test_recusa_por_teto_preserva_os_valores_digitados_na_mensagem(client, cen):
    """R2-10: 22 partidas enviadas (as 20 primeiras batendo, e as 2
    últimas TAMBÉM batendo em 77,00/77,00). A recusa por teto está
    correta (nada é gravado — é o ponto do achado 5), mas antes desta
    correção os valores das duas linhas excedentes desapareciam da
    RESPOSTA inteira: a tela só re-exibia as 20 primeiras, e a mensagem
    mandava "grave em dois lançamentos" sem repetir o que não coube.
    """
    _login(client, cen)
    empresa = cen["empresa"]
    contas_debito = [
        Conta.objects.create(
            empresa=empresa,
            codigo=f"1.{i}",
            nome=f"Conta débito R2-10 {i}",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )
        for i in range(1, 12)
    ]
    contas_credito = [
        Conta.objects.create(
            empresa=empresa,
            codigo=f"2.{i}",
            nome=f"Conta crédito R2-10 {i}",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=NaturezaConta.CREDORA,
        )
        for i in range(1, 12)
    ]
    dados = {
        "acao": "gravar",
        "num_linhas": "22",
        "data": timezone.localdate().isoformat(),
        "historico": "R2-10: 22 partidas",
        "chave_idempotencia": "r2-10-preserva",
    }
    for i in range(1, 11):
        dados[f"conta_{i}"] = str(contas_debito[i - 1].id)
        dados[f"tipo_{i}"] = "debito"
        dados[f"valor_{i}"] = "10,00"
    for i in range(11, 21):
        dados[f"conta_{i}"] = str(contas_credito[i - 11].id)
        dados[f"tipo_{i}"] = "credito"
        dados[f"valor_{i}"] = "10,00"
    dados["conta_21"] = str(contas_debito[10].id)
    dados["tipo_21"] = "debito"
    dados["valor_21"] = "77,00"
    dados["conta_22"] = str(contas_credito[10].id)
    dados["tipo_22"] = "credito"
    dados["valor_22"] = "77,00"

    resposta = client.post(reverse("contabilidade_web:lancamento_novo", args=[empresa.id]), dados)
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    conteudo = resposta.content.decode()
    # Antes desta correção, "77,00" simplesmente não existia na resposta
    # inteira — as linhas 21 e 22 desapareciam por completo.
    assert "77,00" in conteudo
    assert "Linhas que não couberam" in conteudo
    assert "linha 21" in conteudo and "linha 22" in conteudo


# ---------------------------------------------------------------------------
# R2-8 — texto de apoio nos rótulos de data (ambiguidade do <input type=date>)
# ---------------------------------------------------------------------------


def test_rotulos_de_data_trazem_dica_de_formato_ptbr(client, cen):
    """R2-8: `<input type="date">` exibe o formato do NAVEGADOR do
    usuário, não um formato que este projeto controle — sem JavaScript
    (critério 15) não há como forçar. A captura da rodada 1 mostrava
    "09/01/2026" (mês/dia/ano) três centímetros abaixo de um cabeçalho
    "01/09/2026" (dia/mês/ano) na MESMA tela. O texto de apoio explícito
    no rótulo é o que dá para fazer sem JS.
    """
    _login(client, cen)
    empresa_id = cen["empresa"].id

    resposta = client.get(_url_lancamento(cen))
    assert "Data (dd/mm/aaaa)" in resposta.content.decode()

    for nome_rota, args in [
        ("contabilidade_web:diario", [empresa_id]),
        ("contabilidade_web:balancete", [empresa_id]),
        ("contabilidade_web:razao", [empresa_id, cen["caixa"].id]),
    ]:
        conteudo = client.get(reverse(nome_rota, args=args)).content.decode()
        assert "Início (dd/mm/aaaa)" in conteudo, nome_rota
        assert "Fim (dd/mm/aaaa)" in conteudo, nome_rota


# ---------------------------------------------------------------------------
# R2-6 + R2-9 — indentação medida pelo EFEITO (getComputedStyle), não pela
# ausência de `style=` inline
# ---------------------------------------------------------------------------


def _caminho_chromium():
    candidatos = [
        "/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
    ]
    for candidato in candidatos:
        if candidato and Path(candidato).exists():
            return candidato
    return None


_CHROMIUM = _caminho_chromium()

precisa_de_chromium = pytest.mark.skipif(
    _CHROMIUM is None,
    reason=(
        "R2-6/R2-9: medir CSS calculado exige um navegador real — indisponível "
        "neste ambiente (nenhum Chromium encontrado)."
    ),
)


# ---------------------------------------------------------------------------
# R2-6/R2-9, defendido SEM NAVEGADOR — a rede que falta quando não há
# Chromium/Playwright (a integração contínua do projeto não tem nenhum dos
# dois: `.github/workflows/` não instala navegador). Os testes com
# `@precisa_de_chromium` abaixo ficam PULADOS lá — honestamente pulados
# (`test_indentacao_por_efeito_pula_com_motivo_quando_nao_ha_navegador`
# prova isso), mas pulado não é aprovado, e o mutante ME2 sobreviveria
# exatamente no lugar que decide se um PR entra ou não. É o achado R2-6
# outra vez, um nível acima: "controle correto, sem teste" — só que agora
# o "controle" é o próprio teste de navegador, e falta o que o DEFENDE na
# CI. Apontado pelo arquiteto-senior na revisão desta entrega.
#
# Este teste lê o CSS como TEXTO (nenhum subprocess, nenhum Chromium) e
# mede a MESMA propriedade que os testes de navegador medem no DOM:
# 1. Cada `.nivel-N` só conta se vier PREFIXADO por `.tabela-dados td`
#    (a especificidade (0,2,1) que vence a regra genérica (0,1,1) — é
#    exatamente o que ME2 remove, trocando para `.nivel-N` isolado,
#    (0,1,0), que PERDE para a regra genérica).
# 2. O passo é ADITIVO sobre o recuo da célula comum (R2-9) e
#    ESTRITAMENTE crescente por nível (R2-6).
# Sob ME2, a regra deixa de casar o padrão PREFIXADO — os níveis somem
# do dicionário `niveis` e a asserção de presença falha. Roda em
# QUALQUER ambiente, CI incluída.
# ---------------------------------------------------------------------------


_REGRA_NIVEL_PREFIXADA = re.compile(
    r"\.tabela-dados td\.nivel-(\d+)\s*\{\s*padding-left:\s*([0-9.]+)rem;?\s*\}"
)
# Detecta a FORMA do mutante ME2 diretamente: um seletor ".nivel-N" cuja
# especificidade não veio de ".tabela-dados td" na frente — o lookbehind
# de largura fixa "td" (2 caracteres) é exatamente o que a substituição
# do mutante apaga.
_REGRA_NIVEL_SEM_PREFIXO = re.compile(r"(?<!td)\.nivel-\d+\s*\{")


def _parse_indentacao_do_css(css_texto):
    """Lê `static/css/base.css` como STRING e devolve
    `(padding_base_rem, {nivel: padding_left_rem})` — sem abrir
    navegador nenhum. `padding_base_rem` vem da regra genérica
    `.tabela-dados th, .tabela-dados td { padding: Y X; ... }` (o
    segundo valor do atalho `padding` é o `padding-left`/`padding-right`
    na forma de duas grandezas). Cada entrada de `niveis` só existe se a
    regra `.nivel-N` correspondente estiver PREFIXADA por
    `.tabela-dados td` — é a mesma checagem de especificidade que o
    comentário do CSS documenta, agora verificada por texto.
    """
    casamento_base = re.search(
        r"\.tabela-dados td\s*\{[^}]*padding:\s*[0-9.]+rem\s+([0-9.]+)rem",
        css_texto,
    )
    assert casamento_base, "não encontrei a regra de padding da célula comum (.tabela-dados td)"
    padding_base = Decimal(casamento_base.group(1))

    niveis = {}
    for casamento in _REGRA_NIVEL_PREFIXADA.finditer(css_texto):
        niveis[int(casamento.group(1))] = Decimal(casamento.group(2))
    return padding_base, niveis


def test_regra_de_indentacao_tem_prefixo_de_especificidade_sem_navegador():
    """Metade 1 da defesa textual: nenhuma regra `.nivel-N` pode aparecer
    SEM o prefixo `.tabela-dados td` — checagem direta da FORMA do
    mutante ME2 (a substituição que ele aplica é justamente apagar esse
    prefixo). Roda em qualquer ambiente; não abre subprocess.
    """
    css_texto = Path("static/css/base.css").read_text(encoding="utf-8")
    orfaos = _REGRA_NIVEL_SEM_PREFIXO.findall(css_texto)
    assert not orfaos, (
        "regra de nível sem o prefixo de especificidade '.tabela-dados td' "
        f"(especificidade insuficiente para vencer a regra genérica): {orfaos}"
    )


def test_regra_de_indentacao_e_aditiva_e_estritamente_crescente_sem_navegador():
    """Metade 2 da defesa textual: com as regras PREFIXADAS (extraídas do
    próprio CSS, não assumidas), o nível 0 e o nível 1 alinham com o
    recuo da célula comum (R2-9 — a raiz não sai da coluna), e cada
    nível seguinte soma EXATAMENTE 1.25rem (20px) ao anterior — nunca
    achatado, nunca menor que o passo pretendido. Sob ME2, `niveis` fica
    vazio (nenhuma regra prefixada casa) e a primeira asserção de
    presença já falha — não precisa da checagem de forma acima para
    detectar o mutante; as duas se reforçam.
    """
    css_texto = Path("static/css/base.css").read_text(encoding="utf-8")
    padding_base, niveis = _parse_indentacao_do_css(css_texto)

    for nivel in range(0, 11):
        assert nivel in niveis, f"falta (ou está sem prefixo) a regra .nivel-{nivel}"

    # R2-9: raiz (nivel-1) e o caso degenerado de ciclo (nivel-0) alinham
    # com a célula comum — nunca ficam à esquerda do cabeçalho.
    assert niveis[0] == padding_base, (niveis[0], padding_base)
    assert niveis[1] == padding_base, (niveis[1], padding_base)

    # R2-6 + R2-9: passo aditivo de exatamente 1.25rem, estritamente
    # crescente — nunca achatado (o efeito de ME2 seria todo mundo igual
    # à regra genérica, o que aqui aparece como "sumiu do dicionário").
    passo_esperado = Decimal("1.25")
    for nivel in range(2, 11):
        passo = niveis[nivel] - niveis[nivel - 1]
        assert passo == passo_esperado, (nivel, niveis[nivel - 1], niveis[nivel], passo)


def test_defesa_textual_nao_depende_de_chromium_estar_disponivel(monkeypatch):
    """Prova de que as duas defesas acima independem de `_CHROMIUM`: força
    o módulo a se comportar como se nenhum navegador tivesse sido
    encontrado (o cenário real da CI) e repete a mesma leitura de texto.
    """
    import apps.contabilidade.tests.test_dl017_rodada2_frontend as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM", None)
    css_texto = Path("static/css/base.css").read_text(encoding="utf-8")
    padding_base, niveis = _parse_indentacao_do_css(css_texto)
    assert niveis[1] == padding_base
    assert niveis[2] - niveis[1] == Decimal("1.25")


def _padding_left_computado(corpo_html, seletor):
    """Renderiza `corpo_html` (com o CSS REAL do projeto, static/css/
    base.css, inlinado) num Chromium headless e devolve o `padding-left`
    computado de cada elemento que casa `seletor`, na ordem do DOM.

    R2-6: só medir o EFEITO (getComputedStyle) prova que a indentação
    funciona — o teste que já existia
    (`test_indentacao_..._nunca_usa_style_inline`, em
    test_dl017_rodada1_correcoes.py) verifica a AUSÊNCIA de `style=`
    inline, que é a FORMA da correção da rodada 1, não o EFEITO desta. O
    mutante ME2 do relatório da rodada 2 (trocar `.tabela-dados
    td.nivel-N` por `.nivel-N`) sobrevivia a 487 testes exatamente porque
    nenhum deles chegava a medir isto.
    """
    css = Path("static/css/base.css").read_text(encoding="utf-8")
    script = f"""
    <script>
    var els = document.querySelectorAll({seletor!r});
    var out = [];
    els.forEach(function(e) {{ out.push(getComputedStyle(e).paddingLeft); }});
    document.title = JSON.stringify(out);
    </script>
    """
    html = (
        f"<!DOCTYPE html><html><head><style>{css}</style></head>"
        f"<body>{corpo_html}{script}</body></html>"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        caminho = f.name
    try:
        resultado = subprocess.run(
            [
                _CHROMIUM,
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--dump-dom",
                f"file://{caminho}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        casamento = re.search(r"<title>(.*?)</title>", resultado.stdout, re.DOTALL)
        assert casamento, (
            f"Chromium não devolveu <title>: stdout={resultado.stdout[:500]!r} "
            f"stderr={resultado.stderr[:500]!r}"
        )
        return json.loads(casamento.group(1))
    finally:
        Path(caminho).unlink(missing_ok=True)


@precisa_de_chromium
def test_indentacao_hierarquica_e_aditiva_e_estritamente_crescente_por_nivel(client, cen):
    """R2-6 (defende o efeito, não a forma) + R2-9 (a indentação é
    ADITIVA sobre o recuo padrão da célula, não parte de zero).

    Mede, no HTML REAL entregue pelo Plano de Contas (3 níveis) com o CSS
    REAL do projeto:

    1. Uma célula COMUM (`<td>` sem classe de nível — a coluna "Código",
       por exemplo) e a raiz do plano (`nivel-1`) têm o MESMO
       `padding-left` — a raiz não fica mais à esquerda que o cabeçalho
       (o defeito do R2-9: antes, a raiz tinha 0px contra 12px da célula
       comum).
    2. Cada nível seguinte soma EXATAMENTE 20px ao anterior — nunca 8px
       (o defeito do R2-9) e nunca igual ao nível anterior (o que ME2
       causaria: especificidade reduzida faz TODOS os níveis caírem na
       regra genérica da tabela, e todos os valores ficam idênticos).
    """
    empresa = cen["empresa"]
    grupo = Conta.objects.create(
        empresa=empresa,
        codigo="9",
        nome="Grupo de teste",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    subgrupo = Conta.objects.create(
        empresa=empresa,
        codigo="9.1",
        nome="Subgrupo de teste",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
        conta_pai=grupo,
    )
    Conta.objects.create(
        empresa=empresa,
        codigo="9.1.01",
        nome="Folha de teste",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=subgrupo,
    )

    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:plano_de_contas", args=[empresa.id]))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()

    tabela = re.search(r"<table.*?</table>", conteudo, re.DOTALL).group(0)

    padding_celula_comum = _padding_left_computado(tabela, "td:not([class])")
    assert padding_celula_comum, "esperava ao menos uma célula sem classe de nível (ex.: Código)"
    base_px = int(padding_celula_comum[0].removesuffix("px"))

    # Consulta CADA nível separadamente (não uma lista combinada): o
    # cenário (`cen`) já tem duas contas raiz próprias (Caixa, Receita),
    # então "nivel-1" nunca tem só UM elemento — o que importa é que TODO
    # elemento de um nível dá o MESMO padding, e que o valor sobe 20px de
    # nível para nível, não a posição numa lista combinada.
    def _valores_unicos(nivel):
        valores = _padding_left_computado(tabela, f".nivel-{nivel}")
        assert valores, f"esperava ao menos um elemento nivel-{nivel}"
        unicos = {int(v.removesuffix("px")) for v in valores}
        assert len(unicos) == 1, (nivel, valores)
        return unicos.pop()

    nivel_1 = _valores_unicos(1)
    nivel_2 = _valores_unicos(2)
    nivel_3 = _valores_unicos(3)

    # R2-9: a raiz (nivel-1) não sai da coluna — mesmo valor da célula comum.
    assert nivel_1 == base_px, (nivel_1, base_px)
    # R2-6 (o efeito real) + R2-9 (o passo certo): 20px por nível, sempre
    # ESTRITAMENTE crescente — nunca achatado (o que a especificidade
    # reduzida de ME2 causaria: os três valores ficariam iguais).
    assert nivel_2 == nivel_1 + 20, (nivel_1, nivel_2)
    assert nivel_3 == nivel_2 + 20, (nivel_2, nivel_3)


@precisa_de_chromium
def test_mutante_me2_especificidade_reduzida_e_detectado_pela_medicao(tmp_path):
    """Evidência de que o teste acima MATA o mutante ME2 do relatório da
    rodada 2 ("`.tabela-dados td.nivel-N` -> `.nivel-N`", a primeira
    tentativa de correção do achado 6 da rodada 1, que o próprio
    comentário do CSS registra como não corrigindo nada). Aplica o
    mutante numa CÓPIA do CSS real (nunca o arquivo do repositório) e
    mede: com a especificidade reduzida, `.nivel-N` isolado perde para a
    regra genérica `.tabela-dados td` (mais específica), e todos os
    níveis caem no MESMO `padding-left` — a asserção "estritamente
    crescente" do teste acima falharia.
    """
    css_original = Path("static/css/base.css").read_text(encoding="utf-8")
    css_mutado = re.sub(r"\.tabela-dados td(\.nivel-\d+)", r"\1", css_original)
    assert css_mutado != css_original, "o mutante precisa alterar o CSS de verdade"

    tabela = (
        '<table class="tabela-dados">'
        "<tr><td>código comum</td></tr>"
        '<tr><td class="nivel-1">raiz</td></tr>'
        '<tr><td class="nivel-2">filho</td></tr>'
        '<tr><td class="nivel-3">neto</td></tr>'
        "</table>"
    )
    script = """
    <script>
    var els = document.querySelectorAll('.nivel-1, .nivel-2, .nivel-3');
    var out = [];
    els.forEach(function(e) { out.push(getComputedStyle(e).paddingLeft); });
    document.title = JSON.stringify(out);
    </script>
    """
    html_mutado = (
        f"<!DOCTYPE html><html><head><style>{css_mutado}</style></head>"
        f"<body>{tabela}{script}</body></html>"
    )
    caminho = tmp_path / "mutante_me2.html"
    caminho.write_text(html_mutado, encoding="utf-8")

    resultado = subprocess.run(
        [
            _CHROMIUM,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--dump-dom",
            f"file://{caminho}",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    casamento = re.search(r"<title>(.*?)</title>", resultado.stdout, re.DOTALL)
    assert casamento, resultado.stdout[:500]
    valores_sob_mutante = json.loads(casamento.group(1))

    # Sob o mutante, os três níveis colapsam no MESMO padding — a asserção
    # "estritamente crescente" do teste real FALHARIA aqui. É a prova de
    # que o teste morre sob ME2.
    assert len(set(valores_sob_mutante)) == 1, (
        "o mutante deveria achatar todos os níveis no mesmo padding-left",
        valores_sob_mutante,
    )


def test_indentacao_por_efeito_pula_com_motivo_quando_nao_ha_navegador():
    """Documenta o limite honesto: sem Chromium, os dois testes acima são
    PULADOS, não aprovados por omissão — `_caminho_chromium()` devolve
    `None` e o `skipif` carrega o motivo. Este teste garante que a busca
    de binário em si não lança exceção em nenhum ambiente.
    """
    assert _caminho_chromium() is None or Path(_caminho_chromium()).exists()


# ---------------------------------------------------------------------------
# Regressão: a chave de idempotência de um duplo clique continua intacta
# com a nova derivação de num_linhas (R2-3 não pode ter afetado isto).
# ---------------------------------------------------------------------------


def test_duplo_clique_continua_intacto_apos_a_derivacao_de_num_linhas_do_post(client, cen):
    _login(client, cen)
    dados = {
        "acao": "gravar",
        "num_linhas": "abc",  # malformado de propósito — não pode quebrar a idempotência
        "data": timezone.localdate().isoformat(),
        "historico": "duplo clique com num_linhas malformado",
        "chave_idempotencia": "r2-3-duplo-clique",
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "1.500,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "1.500,00",
    }
    r1 = client.post(_url_lancamento(cen), dados)
    r2 = client.post(_url_lancamento(cen), dados)
    assert r1.status_code == 302 and r2.status_code == 302
    assert r1.url == r2.url
    assert LancamentoContabil.objects.count() == 1


def test_post_sem_csrf_continua_recusado_apos_esta_rodada(cen):
    cliente_estrito = Client(enforce_csrf_checks=True)
    assert cliente_estrito.login(username="gestora-r2", password="senha-forte-123")
    resposta = cliente_estrito.post(
        _url_lancamento(cen),
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "sem csrf",
            "chave_idempotencia": "r2-sem-csrf",
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "10,00",
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": "10,00",
        },
    )
    assert resposta.status_code == 403
    assert LancamentoContabil.objects.count() == 0
