"""Correções da rodada 2 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-2.md) atribuídas ao `especialista-frontend`:
R2-1 (bloqueador, DE-029), R2-2, R2-3, R2-5, R2-6, R2-8, R2-9 e R2-10.

R2-4 e R2-7 (o byte NUL e o dígito Unicode em `apps.core.dinheiro`) são do
`desenvolvedor-pleno` e não têm teste aqui. Dados 100% sintéticos, criados
nos próprios testes.

BL-284 (rodada 3 da DL-024, 2026-09-18): `descricoes_de_data_sem_defesa` e
os dois testes que a usam substituem a forma antiga do teste do R2-9/
DE-031/A5. O REQUISITO do DE-031/A5 não mudou — texto de apoio de formato
de data VISÍVEL, associado por `aria-describedby` — o que ficou obsoleto
foi a IMPLEMENTAÇÃO que aquele teste assumia (um parágrafo próprio por
campo, `id="{campo}_ajuda"` literal): corrigir o BL-277 no Balancete (a
mesma frase repetida uma vez por campo custava uma linha inteira do
filtro em 1280×800, medido na revisão integrada 2307de6) trocou aquele
desenho por um parágrafo COMPARTILHADO entre "Início" e "Fim". A nova
guarda verifica o invariante (o `id` que `aria-describedby` aponta EXISTE
e é visível) em vez do formato do `id`, e por isso vale tanto para
descrição própria (Diário, Razão, Lançamento) quanto compartilhada
(Balancete) — e fica MAIS exigente que antes: a versão anterior nunca
cruzava o `id` apontado por `aria-describedby` com um `id` que de fato
existisse no documento, então uma referência pendurada passaria.
"""

import contextlib
import inspect
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
from apps.core.marcacao import tem_classe
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
# A8/BL-132 (rodada 4) — a PRIMEIRA camada da gramática pt-BR, testada
# SOZINHA. A DE-029 publicava `_GRAMATICA_VALOR_PTBR` com `\d` (que casa
# QUALQUER dígito Unicode) enquanto o código sempre usou `[0-9]` — a
# mesma classe do R2-7, com os papéis trocados (texto errado, código
# certo). O texto já foi corrigido (BL-122); o que faltava é o teste: até
# aqui, `_GRAMATICA_VALOR_PTBR` só era defendida pela SEGUNDA camada
# (`para_decimal`, que recusa dígito Unicode por conta própria) — o
# mutante que trocasse `[0-9]` por `\d` na gramática sobrevivia a 608
# testes, porque nenhum deles chamava a gramática ISOLADA da segunda
# camada. Defesa em profundidade só conta quando CADA camada é testada
# por si (a mesma lição do BL-119/A4, aplicada aqui à primeira camada em
# vez da condição de pulo).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "０１０,00",  # dígito fullwidth
        "١٢٣,٤٥",  # dígito índico-arábico
        "๑๐,00",  # dígito tailandês
        "1.０00,00",  # um único dígito Unicode dentro de um texto pt-BR bem formado
    ],
)
def test_gramatica_ptbr_recusa_digito_unicode_sozinha_sem_ajuda_de_para_decimal(texto):
    """A8/BL-132: chama `_GRAMATICA_VALOR_PTBR.fullmatch` DIRETAMENTE —
    sem passar por `_decimal_do_formulario` nem por `para_decimal` (a
    segunda camada, que já tem seu próprio teste em
    `apps/core/tests/test_dinheiro.py` e não é o que este teste mede).
    Se a gramática algum dia voltar a usar `\\d` em vez de `[0-9]`
    (exatamente o texto que a DE-029 publicou antes da BL-122), ela
    passaria a CASAR estes textos — e é isso que este teste reprova,
    independentemente de qualquer camada posterior.
    """
    assert views_web._GRAMATICA_VALOR_PTBR.fullmatch(texto) is None, texto


def test_gramatica_ptbr_aceita_digito_ascii_equivalente_como_controle():
    """Controle positivo do teste acima: a MESMA forma, em dígitos ASCII,
    é aceita pela gramática — a recusa dos dígitos Unicode não é a
    gramática rejeitando TUDO por acidente.
    """
    assert views_web._GRAMATICA_VALOR_PTBR.fullmatch("1.000,00") is not None


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
    # Tocado na DL-024 (DE-053/RC-89) — mesmo motivo do teste equivalente em
    # test_dl017_rodada1_correcoes.py: a classe `valor-monetario` migrou do
    # `<span>` interno para o `<td>` que já continha o rótulo, para fechar o
    # achado da varredura de interface (classe no lugar certo para tabular a
    # célula inteira). O texto agora vem com o rótulo embutido.
    valores_rodape = re.findall(r'class="valor-monetario">([^<]+)<', rodape)
    # A soma PARCIAL continua correta (a intenção da correção da rodada 1
    # é preservada) — só as duas linhas completas entram.
    assert valores_rodape == ["Débito: 1.000,00", "Crédito: 1.000,00"], valores_rodape
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
    """R2-10: `teto + 2` partidas enviadas (as `teto` primeiras batendo, e
    as 2 últimas TAMBÉM batendo em 77,00/77,00). A recusa por teto está
    correta (nada é gravado — é o ponto do achado 5), mas antes desta
    correção os valores das duas linhas excedentes desapareciam da
    RESPOSTA inteira: a tela só re-exibia as `teto` primeiras, e a mensagem
    mandava "grave em dois lançamentos" sem repetir o que não coube.

    RC-79/BL-207 (rodada 6): derivado de
    `views_web.LINHAS_MAXIMAS_LANCAMENTO`, nunca de "22" escrito à mão — o
    teto de negócio passou para 200 e este teste voltaria a medir um lote
    LEGÍTIMO, devolvendo 302 e falhando por motivo errado.
    """
    _login(client, cen)
    empresa = cen["empresa"]
    teto = views_web.LINHAS_MAXIMAS_LANCAMENTO
    dados = {
        "acao": "gravar",
        "num_linhas": str(teto + 2),
        "data": timezone.localdate().isoformat(),
        "historico": f"R2-10: {teto + 2} partidas",
        "chave_idempotencia": "r2-10-preserva",
    }
    for i in range(1, teto + 1):
        e_debito = i <= teto // 2
        dados[f"conta_{i}"] = str((cen["caixa"] if e_debito else cen["receita"]).id)
        dados[f"tipo_{i}"] = "debito" if e_debito else "credito"
        dados[f"valor_{i}"] = "10,00"
    dados[f"conta_{teto + 1}"] = str(cen["caixa"].id)
    dados[f"tipo_{teto + 1}"] = "debito"
    dados[f"valor_{teto + 1}"] = "77,00"
    dados[f"conta_{teto + 2}"] = str(cen["receita"].id)
    dados[f"tipo_{teto + 2}"] = "credito"
    dados[f"valor_{teto + 2}"] = "77,00"

    resposta = client.post(reverse("contabilidade_web:lancamento_novo", args=[empresa.id]), dados)
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    conteudo = resposta.content.decode()
    # Antes desta correção, "77,00" simplesmente não existia na resposta
    # inteira — as duas linhas excedentes desapareciam por completo.
    assert "77,00" in conteudo
    assert "Linhas que não couberam" in conteudo
    assert f"linha {teto + 1}" in conteudo and f"linha {teto + 2}" in conteudo


# ---------------------------------------------------------------------------
# R2-8 / DE-031 / A5 (rodada 4) — o rótulo do campo de data NÃO PODE
# afirmar um formato que `<input type="date">` não controla.
#
# A correção do R2-8 (rodada 2) consertou a FORMA — acrescentou um texto
# de apoio — e ERROU o CONTEÚDO: o rótulo passou a dizer "(dd/mm/aaaa)",
# uma AFIRMAÇÃO de formato que o campo nativo não garante (o formato vem
# do *locale* do navegador, sem JavaScript não há como forçar — critério
# 15). A própria captura entregue na rodada 3 mostrava "09/01/2026"
# (mês/dia/ano) embaixo do rótulo "(dd/mm/aaaa)" — o rótulo mentia. A
# DE-031 decidiu a correção real: manter o seletor nativo (acessibilidade
# — teclado, leitor de tela) e trocar a PROMESSA — o rótulo nomeia o
# campo sem prometer formato; o texto de apoio diz que o campo segue o
# navegador, e que TODA data exibida pelo sistema (fora deste campo de
# entrada) é dd/mm/aaaa. A decisão foi registrada e não executada por uma
# rodada inteira (achado A5) — este teste é o que falta para o mecanismo,
# não só o lembrete, garantir que não regride: um rótulo que volte a
# afirmar "(dd/mm/aaaa)" reprova aqui.
# ---------------------------------------------------------------------------


def test_rotulo_de_data_nao_afirma_formato_que_o_campo_nao_controla(client, cen):
    """Guarda de regressão (R2-8→DE-031/A5): nenhum rótulo de campo de
    data pode voltar a dizer "(dd/mm/aaaa)" — essa é exatamente a
    afirmação que a captura da rodada 3 provou falsa.
    """
    _login(client, cen)
    empresa_id = cen["empresa"].id

    urls = [_url_lancamento(cen)]
    for nome_rota, args in [
        ("contabilidade_web:diario", [empresa_id]),
        ("contabilidade_web:balancete", [empresa_id]),
        ("contabilidade_web:razao", [empresa_id, cen["caixa"].id]),
    ]:
        urls.append(reverse(nome_rota, args=args))

    for url in urls:
        conteudo = client.get(url).content.decode()
        assert "(dd/mm/aaaa)" not in conteudo, url
        # Nenhum rótulo de campo de data (Data/Início/Fim) pode conter
        # QUALQUER string de formato entre parênteses — não só a
        # pt-BR — porque a promessa errada é a classe, não o texto exato.
        for rotulo in re.findall(r'<label for="id_(?:data|inicio|fim)">([^<]*)</label>', conteudo):
            assert "/" not in rotulo, (url, rotulo)


def _elemento_por_id(html, alvo):
    """Devolve `(tag, atributos_da_abertura, texto_interno)` do PRIMEIRO
    elemento com `id="{alvo}"` em `html`, ou `None` se nenhum elemento com
    esse `id` existir no documento.

    Não é um parser de HTML geral — não lida com um elemento do MESMO NOME
    aninhado dentro dele (ex. um `<p>` com outro `<p>` por dentro) — mas os
    elementos de ajuda desta tela são sempre um `<p>` sem filhos de bloco,
    e é exatamente essa forma que o teste precisa reconhecer.
    """
    abertura = re.search(r'<([a-zA-Z][\w-]*)\b([^>]*\bid="' + re.escape(alvo) + r'"[^>]*)>', html)
    if not abertura:
        return None
    tag, atributos = abertura.group(1), abertura.group(2)
    fim_abertura = abertura.end()
    fechamento = html.find(f"</{tag}>", fim_abertura)
    texto_interno = html[fim_abertura:fechamento] if fechamento != -1 else ""
    return tag, atributos, texto_interno


def descricoes_de_data_sem_defesa(html, ids_de_campo):
    """BL-284 (rodada 3, DL-024): guarda REESCRITA depois que corrigir o
    BL-277 no Balancete (texto de ajuda de formato de data repetido uma
    vez por campo, custando uma linha inteira do filtro em 1280×800)
    quebrou a versão anterior deste teste — que não verificava o
    REQUISITO (DE-031/A5: "o campo tem texto de apoio VISÍVEL, associado
    por `aria-describedby`"), verificava a IMPLEMENTAÇÃO de uma rodada
    anterior (um parágrafo próprio por campo, com `id="{campo}_ajuda"`
    literal e a frase contada duas vezes). Duas telas atendiam ao mesmo
    requisito com desenhos diferentes — Balancete agora comparte um único
    parágrafo entre "Início" e "Fim" (o `aria-describedby` dos dois
    campos aponta para o MESMO `id`) — e o teste antigo reprovava a
    correta por causa da forma, não do conteúdo.

    Esta função devolve a lista de problemas achados (lista vazia = tudo
    certo) e é usada tanto pelo teste positivo quanto pelo teste de
    mutação abaixo — a mesma função tem que ACUSAR quando o defeito é
    reintroduzido, senão ela é decoração, não guarda (lição da BL-271,
    repetida pelo arquiteto-senior na auditoria da DL-024).

    O achado que motivou reescrever em vez de só afrouxar: a versão
    antiga verificava `f'aria-describedby="{id}_ajuda" in conteudo` e
    `f'id="{id}_ajuda"' in conteudo` como duas checagens SEPARADAS — nunca
    testava que o `id` apontado por `aria-describedby` fosse o MESMO que
    o `id` que de fato existe no documento. Um `aria-describedby` pendurado
    (apontando para um `id` inexistente) passaria: o leitor de tela
    anunciaria o campo SEM descrição nenhuma, e a suíte juraria que
    estava tudo certo. Por isso o requisito 2 abaixo resolve o `id`
    apontado contra o documento de verdade, não apenas grepa as duas
    substrings.

    Requisitos, por campo:
    1. Tem `aria-describedby` (não fica sem descrição nenhuma).
    2. TODO `id` que o `aria-describedby` aponta EXISTE no documento —
       referência pendurada reprova aqui.
    3. O elemento apontado é VISÍVEL: carrega a classe `texto-apoio` e
       não está `aria-hidden="true"` nem `visualmente-oculto` — as duas
       técnicas que o projeto usa para esconder conteúdo de quem enxerga
       ou de quem usa leitor de tela.
    4. O texto do elemento apontado traz a orientação de formato (segue
       o navegador; toda data exibida pelo sistema é dd/mm/aaaa) — sem
       fixar a frase exata, porque a frase exata É a forma, não o
       requisito.

    Descrição PRÓPRIA por campo (Diário, Razão, Lançamento, hoje) e
    descrição COMPARTILHADA (Balancete, desde o BL-277) passam as duas —
    nada aqui assume qual das duas formas a tela escolheu.
    """
    problemas = []
    for id_campo in ids_de_campo:
        padrao = re.compile(
            r'\bid="' + re.escape(id_campo) + r'"[^>]*\baria-describedby="([^"]*)"'
            r"|"
            r'\baria-describedby="([^"]*)"[^>]*\bid="' + re.escape(id_campo) + r'"'
        )
        m = padrao.search(html)
        if not m:
            problemas.append(f"#{id_campo}: campo sem aria-describedby")
            continue
        ids_apontados = (m.group(1) or m.group(2) or "").split()
        if not ids_apontados:
            problemas.append(f"#{id_campo}: aria-describedby vazio")
            continue

        textos = []
        for alvo in ids_apontados:
            elemento = _elemento_por_id(html, alvo)
            if elemento is None:
                problemas.append(
                    f"#{id_campo}: aria-describedby aponta para '#{alvo}', "
                    "que não existe no documento (referência pendurada)"
                )
                continue
            _tag, atributos, texto_interno = elemento
            # M6/BL-297 (rodada 4 da auditoria DL-024): as duas checagens
            # abaixo eram substring (`"texto-apoio" in atributos` /
            # "visualmente-oculto" in atributos`) — `class="texto-apoio-
            # legenda"` é uma classe CSS DIFERENTE (o seletor `.texto-apoio`
            # não a alcança, o parágrafo perde o estilo) e PASSAVA. `tem_classe`
            # (apps.core.marcacao, casamento por TOKEN do atributo `class` —
            # a mesma função que a varredura de interface e a guarda de
            # atalhos usam, extraída para não ser escrita uma quarta vez)
            # exige o nome INTEIRO como um dos tokens.
            # `tem_classe` usa `re.search` internamente (não `re.match`):
            # não precisa da tag de abertura inteira, só do trecho que
            # contém `class="..."` — `atributos` (o grupo capturado por
            # `_elemento_por_id`, ver acima) já serve como está.
            if not tem_classe(atributos, "texto-apoio"):
                problemas.append(
                    f"#{id_campo}: '#{alvo}' não tem a classe texto-apoio "
                    "(nada garante que fique visível)"
                )
            if 'aria-hidden="true"' in atributos:
                problemas.append(f"#{id_campo}: '#{alvo}' está aria-hidden")
            if tem_classe(atributos, "visualmente-oculto"):
                problemas.append(f"#{id_campo}: '#{alvo}' está visualmente-oculto")
            textos.append(texto_interno)

        texto_junto = " ".join(textos)
        if "navegador" not in texto_junto:
            problemas.append(f"#{id_campo}: a descrição não diz que o campo segue o navegador")
        if "dd/mm/aaaa" not in texto_junto:
            problemas.append(f"#{id_campo}: a descrição não afirma o formato dd/mm/aaaa do sistema")
    return problemas


def test_rotulo_de_data_tem_texto_de_apoio_visivel_e_associado(client, cen):
    """DE-031: o rótulo nomeia o campo sem prometer formato — mas o
    contador não fica sem informação nenhuma. O texto de apoio (VISÍVEL,
    não só para leitor de tela — o problema que ele resolve é uma
    confusão visual) diz que o campo segue o navegador e que toda
    exibição de data do sistema é dd/mm/aaaa, associado ao campo por
    `aria-describedby` — descrição própria por campo OU compartilhada
    entre campos do mesmo formulário, ver `descricoes_de_data_sem_defesa`.
    """
    _login(client, cen)
    empresa_id = cen["empresa"].id

    urls_e_ids = [
        (_url_lancamento(cen), ["id_data"]),
        (reverse("contabilidade_web:diario", args=[empresa_id]), ["id_inicio", "id_fim"]),
        (reverse("contabilidade_web:balancete", args=[empresa_id]), ["id_inicio", "id_fim"]),
        (
            reverse("contabilidade_web:razao", args=[empresa_id, cen["caixa"].id]),
            ["id_inicio", "id_fim"],
        ),
    ]
    for url, ids_de_campo in urls_e_ids:
        conteudo = client.get(url).content.decode()
        problemas = descricoes_de_data_sem_defesa(conteudo, ids_de_campo)
        assert not problemas, (url, problemas)


def test_mutacao_aria_describedby_pendurado_e_detectada(client, cen):
    """Controle da guarda acima (lição da BL-271: teste que não morre
    quando a defesa é removida não é guarda, é enfeite). Reproduz sobre
    HTML REAL renderizado o modo de falha que motivou reescrever o teste
    anterior: um `aria-describedby` que aponta para um `id` que não
    existe no documento. A versão anterior deste arquivo não tinha como
    detectar isso — grepava duas substrings sem nunca cruzar uma com a
    outra.
    """
    _login(client, cen)
    url = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    conteudo = client.get(url).content.decode()

    assert not descricoes_de_data_sem_defesa(conteudo, ["id_inicio"]), (
        "controle: a página real não deveria ter problema nenhum"
    )

    # A mutação: pendura a referência do campo "Início" num `id` que
    # nunca existiu, sem tocar no elemento de ajuda em si (ele continua
    # no documento, só deixa de ser apontado por este campo).
    mutado = conteudo.replace(
        'aria-describedby="id_periodo_ajuda"', 'aria-describedby="id_periodo_ajuda-quebrado"', 1
    )
    assert mutado != conteudo, "controle: a mutação precisa mudar alguma coisa no HTML real"

    achados = descricoes_de_data_sem_defesa(mutado, ["id_inicio"])
    assert achados, "a mutação (aria-describedby pendurado) não foi detectada — a guarda não guarda"
    assert any("não existe no documento" in achado for achado in achados), achados


def test_mutacao_classe_texto_apoio_por_substring_e_detectada(client, cen):
    """M6/BL-297 (rodada 4 da auditoria DL-024): repete a sabotagem do
    auditor no parágrafo COMPARTILHADO do Balancete (BL-277) —
    `class="texto-apoio ajuda-formato-data"` vira `class="texto-apoio-
    legenda ajuda-formato-data"`, uma classe CSS DIFERENTE que o seletor
    `.texto-apoio` não alcança (o parágrafo perde o estilo que a guarda
    existe para garantir). Antes desta correção (checagem por substring,
    `"texto-apoio" in atributos`), a mutação passava — 61 passed. Agora
    `tem_classe` (apps.core.marcacao) casa por TOKEN e a mutação tem que
    continuar sendo detectada.
    """
    _login(client, cen)
    url = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    conteudo = client.get(url).content.decode()

    assert not descricoes_de_data_sem_defesa(conteudo, ["id_inicio"]), (
        "controle: a página real não deveria ter problema nenhum"
    )

    mutado = conteudo.replace(
        'class="texto-apoio ajuda-formato-data"',
        'class="texto-apoio-legenda ajuda-formato-data"',
        1,
    )
    assert mutado != conteudo, "controle: a mutação precisa mudar alguma coisa no HTML real"

    achados = descricoes_de_data_sem_defesa(mutado, ["id_inicio"])
    assert achados, "a mutação (texto-apoio-legenda por substring) não foi detectada"
    assert any("não tem a classe texto-apoio" in achado for achado in achados), achados


def test_controle_tem_classe_texto_apoio_distingue_token_de_substring():
    """Controle sintético, sem banco: os três casos do critério de
    verificação do BL-297 — `class="texto-apoio-legenda"` reprova;
    `class="texto-apoio"` e `class="texto-apoio ajuda-formato-data"`
    continuam passando."""
    assert not tem_classe(' class="texto-apoio-legenda"', "texto-apoio")
    assert tem_classe(' class="texto-apoio"', "texto-apoio")
    assert tem_classe(' class="texto-apoio ajuda-formato-data"', "texto-apoio")


# ---------------------------------------------------------------------------
# R2-6 + R2-9 — indentação medida pelo EFEITO (getComputedStyle), não pela
# ausência de `style=` inline
# ---------------------------------------------------------------------------


def _caminho_chromium():
    """Localiza o binário do Chromium por caminho fixo conhecido ou pelo
    `PATH`.

    `DATALEDGER_TESTE_CHROMIUM_CAMINHO`, se definida, FORÇA o caminho
    devolvido (string vazia força "nenhum encontrado") — é um hook SÓ DE
    VERIFICAÇÃO desta suíte, nunca lido por código de produção, que
    existe para as próprias medições abaixo poderem simular um binário
    ausente ou QUEBRADO sem mexer no `PATH` real do sistema (compartilhado
    por outros processos desta sessão).
    """
    if "DATALEDGER_TESTE_CHROMIUM_CAMINHO" in os.environ:
        forcado = os.environ["DATALEDGER_TESTE_CHROMIUM_CAMINHO"]
        return forcado or None
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


# R6-1/BL-195 (rodada 6) — o DESCARTE de um recurso temporário nunca pode
# reprovar a suíte, e nunca pode ser confundido com "o navegador não
# funciona".
#
# O que o dado disse: o `-rs` dos dois jobs de `38efbf9f` acusava
# `OSError(39, 'Directory not empty')` com a mensagem "erro de sistema
# operacional AO EXECUTAR". Não foi ao executar. `errno 39` (`ENOTEMPTY`)
# não pode vir de `subprocess.run`: vinha do `shutil.rmtree` do `__exit__`
# do `tempfile.TemporaryDirectory` do `--user-data-dir`, DEPOIS de o
# navegador ter rodado e devolvido o DOM certo — o Chrome deixa processos
# filhos escrevendo no diretório de perfil, e eles criam arquivos novos
# entre o `scandir` e o `rmdir` do descarte. Reproduzido aqui 3 de 3, com
# um navegador falso que renderiza CERTO e deixa um filho gravando no
# perfil:
#
#     _chromium_funciona   -> False, "erro ... ao executar: OSError(39, ...)"
#     _renderizar_e_medir  -> OSError(39) ESCAPANDO (o `except` cobria a
#                             CHAMADA, não a saída do `with`)
#
# Eram DOIS defeitos de sinal oposto na mesma causa: um falso NEGATIVO
# (navegador bom reprovado na checagem, os dois testes de efeito pulando
# para sempre — nunca rodaram na integração contínua, em nenhuma rodada) e
# uma armadilha armada (bastava subir o timeout para a medição rodar e a
# mesma exceção reprovar a suíte, agora fora de qualquer `except`).
#
# A classe, escrita pelo efeito proibido (DE-032): **nenhuma falha de
# recurso externo de ambiente reprova a suíte, INCLUSIVE falha na limpeza
# do recurso** — e nenhuma falha de limpeza é relatada como incapacidade
# do navegador. Estas duas funções são o ponto ÚNICO de descarte dos dois
# recursos temporários que o instrumento cria (o arquivo HTML e o
# diretório de perfil); nenhuma das duas medições volta a chamar
# `TemporaryDirectory`, `rmtree` ou `unlink` por conta própria.
def _descartar_caminho_temporario(caminho):
    """Apaga um arquivo OU diretório temporário sem NUNCA levantar.

    `ignore_errors=True` já cobre o `ENOTEMPTY` do descarte concorrente; o
    `try/except OSError` em volta cobre o resto da família (`PermissionError`
    do `unlink`, sistema de arquivos somente-leitura, caminho que virou
    outra coisa entre a checagem e o descarte). Nenhum dos dois é
    redundância decorativa: o primeiro é o caso medido, o segundo é a
    classe.
    """
    try:
        if os.path.isdir(caminho):
            shutil.rmtree(caminho, ignore_errors=True)
        else:
            Path(caminho).unlink(missing_ok=True)
    except OSError:
        pass


@contextlib.contextmanager
def _perfil_de_navegador_descartavel():
    """Cria um `--user-data-dir` próprio e o descarta ao sair, com a falha
    de descarte SEMPRE engolida.

    É a forma "criar o perfil e descartá-lo em `finally` com erro
    ignorado" recomendada pelo auditor, encapsulada — em vez de um
    `tempfile.TemporaryDirectory()` cujo `__exit__` levanta dentro da
    região que julga se o navegador funciona. Usar `mkdtemp` explícito é
    deliberado: deixa o descarte visível numa linha só, no lugar de
    escondido num `__exit__` que nem parece código.
    """
    perfil = tempfile.mkdtemp(prefix="dataledger-perfil-chromium-")
    try:
        yield perfil
    finally:
        _descartar_caminho_temporario(perfil)


# PASSO 3 do BL-195 — aplicado só DEPOIS de (1) o descarte do perfil sair
# da região julgada nas duas funções e (2) os quatro testes de falha de
# limpeza (no fim deste arquivo) conseguirem falhar. Nesta ordem, e não na
# outra: subir o timeout sozinho faz a medição rodar e a `ENOTEMPTY` do
# descarte reprovar a suíte, que é o bloqueador da rodada 5 reaberto.
#
# BL-215 (segunda rodada da DL-020): a frase anterior afirmava que os quatro
# testes "foram vistos falhar contra os mutantes que os removem", e **não
# havia registro nenhum disso** — afirmação não é registro, e esta é
# justamente a propriedade que a etapa inteira exige demonstrar. O registro
# passou a existir (relatório de entrega da segunda rodada da DL-020), e o
# que fica aqui é a RECEITA, conferível em um minuto por quem duvidar:
#
#   - devolver `tempfile.TemporaryDirectory()` à região julgada de
#     `_renderizar_e_medir` mata `test_renderizar_e_medir_pula_quando_
#     limpeza_falha_e_o_titulo_nao_serve` e `..._mede_normalmente_com_
#     limpeza_de_perfil_falhando`, os dois com `OSError(39)` — a armadilha
#     deste passo 3, exatamente;
#   - devolvê-lo à região julgada de `_chromium_funciona` mata
#     `test_chromium_funciona_aceita_navegador_bom_com_limpeza_de_perfil_
#     falhando` (o falso negativo: navegador bom, `False`);
#   - tirar o `ignore_errors=True`/`except OSError` de
#     `_descartar_caminho_temporario` mata os QUATRO.
#
# `test_perfil_descartavel_de_fato_apaga_o_diretorio_quando_consegue`
# sobrevive aos três de propósito: é o controle positivo do descarte, e o
# mutante que o mata é o oposto (uma função de descarte que não apaga nada).
#
# O teto era 10s, e o dado mostrou que o limiar curto era ELE MESMO uma
# fonte de falso negativo: dos dois jobs de `38efbf9f`, um acusou `timeout
# de 10s` e o OUTRO, do mesmo commit, chegou a renderizar — o binário é
# capaz de responder dentro de 10s ÀS VEZES, e um limiar instável não é
# prova de navegador quebrado. Agora a checagem e a medição usam o MESMO
# número: se o navegador presta para medir, ele presta para a checagem, e
# não existem dois tetos que possam divergir. O preço é uma sessão de teste
# esperar até 30s num ambiente sem navegador; o preço do erro oposto foi
# duas medições de CSS que nunca rodaram na integração contínua.
#
# Quem precisa de um teto curto passa `timeout=` explicitamente — é o que
# o teste do binário que trava faz, para não somar 30s à suíte.
_TIMEOUT_MEDICAO_S = 30
_TIMEOUT_VERIFICACAO_DE_SESSAO_S = _TIMEOUT_MEDICAO_S


def _chromium_funciona(caminho, *, timeout=_TIMEOUT_VERIFICACAO_DE_SESSAO_S):
    """Confirma que o binário não só EXISTE, mas RENDERIZA de verdade —
    pelo MESMO mecanismo que a medição real usa.

    Achado da integração contínua (`aa10f20`, apontado pelo
    arquiteto-senior): o runner do GitHub TINHA `/usr/bin/chromium`
    presente — `_caminho_chromium()` o encontrava, o `skipif` antigo (que
    só checava `_CHROMIUM is None`) não pulava, o teste de efeito RODAVA
    — e o processo travava (D-Bus ausente em contêiner, sandbox, perfil)
    até estourar os 30s de timeout e morrer com `SIGKILL` (-9),
    reprovando a suíte inteira em vez de pular com motivo. **Presença de
    binário não é navegador funcionando** — é a mesma classe de erro que
    esta etapa inteira vem corrigindo: medir a FORMA (o arquivo existe)
    em vez do EFEITO (ele renderiza).

    R5-1/BL-140 (rodada 5, BLOQUEADOR — a CI ficou VERMELHA, `failed` em
    vez de `skipped`): esta função verificava a capacidade com uma URL
    `data:` — que **nunca toca o sistema de arquivos**. A medição real
    (`_renderizar_e_medir`, abaixo) sempre usou `file://` sobre um
    arquivo temporário. No runner, o `apt-get install chromium-browser`
    do `ubuntu-noble` instala um INVÓLUCRO que sobe o **snap** do
    Chromium — que roda com `/tmp` PRIVADO e não enxerga o arquivo que
    `file://` aponta. O navegador sobe, "funciona", devolve DOM de
    verdade — só que é o DOM da PRÓPRIA PÁGINA DE ERRO do navegador
    (`<title>` = a URL pedida), porque o arquivo é invisível para ele. A
    checagem de capacidade com `data:` não tinha como pegar isso: mediu o
    mecanismo ERRADO. Corrigido escrevendo um arquivo temporário de
    verdade (`tempfile.NamedTemporaryFile`, igual à medição real) com uma
    marca conhecida no `<title>`, e renderizando ele por `file://` — o
    MESMO caminho que quebra sob o snap. Um Chromium que não enxerga
    `/tmp` (ou o arquivo temporário, onde quer que esteja) falha AQUI,
    pula os testes de efeito com motivo, e a CI fica verde em vez de
    vermelha.

    R6-1/BL-195 (rodada 6): o descarte do `--user-data-dir` NÃO fica mais
    dentro da região julgada por esta função — ver
    `_perfil_de_navegador_descartavel`. Uma falha de LIMPEZA do perfil não
    é incapacidade do navegador, e era relatada como se fosse ("erro de
    sistema operacional ao executar", com o navegador tendo rodado
    perfeitamente). E o `timeout` deixou de ser um limiar curto próprio:
    por padrão é o MESMO da medição real (ver `_TIMEOUT_MEDICAO_S`), porque
    o limiar curto reprovava um navegador bom em metade dos jobs. Quem
    precisa de teto curto passa `timeout=` explicitamente.

    Faz UMA tentativa e confirma que voltou a MARCA esperada no DOM — não
    só "algum" DOM. Qualquer falha aqui — timeout, código de saída diferente de
    zero, exceção do sistema operacional, marca ausente (a assinatura do
    snap: o `<title>` existe, mas é a URL, não a marca) — vira `False`,
    NUNCA uma exceção que reprovaria a suíte. Chamada UMA VEZ por sessão
    de teste (na importação deste módulo, armazenada em
    `_CHROMIUM_FUNCIONAL`), não uma vez por teste.
    """
    global _DIAGNOSTICO_CHROMIUM
    if not caminho:
        _DIAGNOSTICO_CHROMIUM = "nenhum candidato de caminho encontrado (nem fixo, nem no PATH)"
        return False
    marca = "sessao-de-verificacao-por-arquivo"
    caminho_html = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".html", delete=False, encoding="utf-8"
        ) as arquivo:
            arquivo.write(f"<title>{marca}</title>")
            caminho_html = arquivo.name
        # R6-1/BL-195: `_perfil_de_navegador_descartavel`, nunca
        # `tempfile.TemporaryDirectory()` — o `__exit__` daquele levanta
        # `ENOTEMPTY` DENTRO deste `try`, e o `except OSError` abaixo
        # classificava a falha de LIMPEZA como "o navegador não funciona"
        # (falso negativo medido 3 de 3). Ver o comentário do helper.
        with _perfil_de_navegador_descartavel() as perfil:
            resultado = subprocess.run(
                [
                    caminho,
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    f"--user-data-dir={perfil}",
                    "--dump-dom",
                    f"file://{caminho_html}",
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
    # R3-4: forma com parênteses — ver o comentário equivalente em
    # views_web.py. É a que funciona na versão mínima declarada
    # (`requires-python = ">=3.12"`); quem garante que `ruff format` não
    # a reescreve de volta para a PEP 758 é o alinhamento `[tool.ruff]
    # target-version = "py312"` em `pyproject.toml`, travado por
    # `test_target_version_do_ruff_bate_com_requires_python`
    # (apps/core/tests/test_versao_minima_python.py).
    except subprocess.TimeoutExpired:
        _DIAGNOSTICO_CHROMIUM = f"{caminho}: timeout de {timeout}s"
        return False
    except OSError as exc:
        _DIAGNOSTICO_CHROMIUM = f"{caminho}: erro de sistema operacional ao executar: {exc!r}"
        return False
    finally:
        # R6-1/BL-195: o descarte do arquivo temporário está num `finally`
        # — e exceção levantada num `finally` propaga mesmo com os
        # `except` acima. `_descartar_caminho_temporario` nunca levanta.
        if caminho_html is not None:
            _descartar_caminho_temporario(caminho_html)
    if resultado.returncode != 0:
        _DIAGNOSTICO_CHROMIUM = (
            f"{caminho}: saiu com código {resultado.returncode}; stderr={resultado.stderr[:500]!r}"
        )
        return False
    if marca not in resultado.stdout:
        _DIAGNOSTICO_CHROMIUM = (
            f"{caminho}: rodou (código 0) mas não devolveu a marca esperada no DOM; "
            f"stdout={resultado.stdout[:300]!r}"
        )
        return False
    _DIAGNOSTICO_CHROMIUM = None
    return True


# R5-1/BL-140 — investigação do arquiteto-senior: o runner tem QUATRO
# navegadores registrados (`google-chrome`, `google-chrome-stable`,
# `chromium`, `chromium-browser` — os dois últimos apontando para
# `/usr/local/share/chromium/chrome-linux/chrome`, o Chromium do
# Playwright, não um pacote do sistema) e MESMO ASSIM a checagem de
# capacidade considerava esse binário não-funcional ANTES de qualquer
# instalação — o que motivou (por suposição, não por dado) a instalação
# que causou o R5-1. `_DIAGNOSTICO_CHROMIUM` guarda o MOTIVO exato da
# última falha de `_chromium_funciona` (timeout, código de saída,
# stderr, ou DOM sem a marca esperada) para que a PRÓXIMA vez que os
# testes de efeito pularem na CI, o `-rs` do pytest mostre o motivo real
# — dado, não suposição — sem precisar tocar no workflow.
_DIAGNOSTICO_CHROMIUM = None
_CHROMIUM = _caminho_chromium()
_CHROMIUM_FUNCIONAL = _chromium_funciona(_CHROMIUM)

_MOTIVO_DO_PULO = (
    "R2-6/R2-9: medir CSS calculado exige um navegador REAL e FUNCIONAL. "
    "A condição de pulo mede CAPACIDADE (uma renderização de verificação "
    "com timeout curto, uma vez por sessão) — não só presença de binário. "
    "Achado da CI (aa10f20): /usr/bin/chromium existia e mesmo assim não "
    "subia (D-Bus, sandbox, /dev/shm), estourando timeout e derrubando a "
    "suíte com SIGKILL em vez de pular. A defesa textual sem navegador "
    "(acima) continua valendo mesmo aqui."
)


def _pular_se_chromium_nao_funcional():
    """Ponto ÚNICO que decide se um teste de EFEITO (medição real no
    navegador) roda ou pula — chamado no CORPO de cada um desses testes,
    nunca num `@pytest.mark.skipif` na definição da função.

    A4 (rodada 4, BL-129): um `@pytest.mark.skipif(CONDICAO, ...)`
    decorando a função tem `CONDICAO` avaliada UMA VEZ, na importação do
    módulo — vira um `bool` estático dentro do marcador, e nada num teste
    rodando depois consegue mudar essa decisão já tomada. Foi por isso que
    o mutante MH (trocar `not _CHROMIUM_FUNCIONAL` por `_CHROMIUM is
    None` — a condição EXATA que derrubou a CI em `aa10f20`) sobrevivia a
    608 testes: não havia como, dentro da suíte, FORÇAR a condição para
    `False` e observar o comportamento — o valor já tinha sido decidido
    antes de qualquer teste rodar.

    Com a decisão MOVIDA para dentro do corpo do teste, chamada por uma
    função só, ela passa a ser TESTÁVEL das duas formas que a BL-129 exige,
    em par:

    1. Estrutural — `test_gate_de_navegador_deriva_de_chromium_funcional`
       lê o CÓDIGO-FONTE desta função (`inspect.getsource`) e afirma que
       ela decide por `_CHROMIUM_FUNCIONAL`, nunca por `_CHROMIUM is
       None`. Pega o mutante ANTES de rodar qualquer coisa.
    2. Comportamental — `test_pular_dispara_quando_chromium_nao_funcional`
       e `test_nao_pular_quando_chromium_funcional` chamam esta função com
       `monkeypatch.setattr(..., "_CHROMIUM_FUNCIONAL", False/True)` e
       observam o efeito real: `pytest.skip` disparado ou não. Pega o
       mutante mesmo que a inspeção de texto falhe por algum motivo.

    E os dois testes de EFEITO (`test_indentacao_hierarquica_...` e
    `test_mutante_me2_...`) chamam esta função como a PRIMEIRA linha do
    corpo — `test_chamadores_do_gate_pulam_pela_funcao_compartilhada`
    confirma isso também por inspeção de código-fonte, para que ninguém
    volte a decorar um dos dois com `@pytest.mark.skipif` direto e
    reabra exatamente o mesmo buraco por outro caminho.
    R5-1/BL-140: o motivo do pulo agora inclui `_DIAGNOSTICO_CHROMIUM` —
    a causa REAL medida por `_chromium_funciona` (timeout, código de
    saída, stderr, ou DOM sem a marca esperada) para o binário
    encontrado (`_CHROMIUM`). Antes, o motivo era um texto FIXO que só
    explicava a classe do defeito, nunca o caso do ambiente atual — quem
    lesse o `-rs` da CI via "por que existe esta checagem", nunca "por
    que ESTE binário, HOJE, falhou". Dado, não suposição.
    """
    if not _CHROMIUM_FUNCIONAL:
        pytest.skip(
            f"{_MOTIVO_DO_PULO} Binário tentado: {_CHROMIUM!r}. "
            f"Diagnóstico: {_DIAGNOSTICO_CHROMIUM}"
        )


# ---------------------------------------------------------------------------
# R2-6/R2-9, defendido SEM NAVEGADOR — a rede que falta quando não há
# Chromium/Playwright funcional (a CI só instalou o binário depois da
# BL-119; e mesmo com o binário presente, "presente" não é "funcional" —
# ver `_chromium_funciona`). Os testes de EFEITO abaixo chamam
# `_pular_se_chromium_nao_funcional()` como primeira linha do corpo — não
# um `@pytest.mark.skipif` na definição da função (ver o docstring
# daquela função para o motivo: um marcador não é testável em tempo de
# execução). Pulado com motivo não é aprovado, e o mutante ME2
# sobreviveria exatamente no lugar que decide se um PR entra ou não. É o
# achado R2-6 outra vez, um nível acima: "controle correto, sem teste" —
# só que agora o "controle" é o próprio teste de navegador, e falta o que
# o DEFENDE. Apontado pelo arquiteto-senior na revisão da rodada 2, e de
# novo pelo auditor-qa na rodada 4 (A4/BL-129), porque a primeira correção
# consertou o CÁLCULO da condição de pulo e não a TESTABILIDADE dela.
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
    r"\.tabela-dados td\.nivel-(\d+)\s*\{\s*padding-left:\s*([0-9.a-z()\-]+?);?\s*\}"
)
# Detecta a FORMA do mutante ME2 diretamente: um seletor ".nivel-N" cuja
# especificidade não veio de ".tabela-dados td" na frente — o lookbehind
# de largura fixa "td" (2 caracteres) é exatamente o que a substituição
# do mutante apaga.
_REGRA_NIVEL_SEM_PREFIXO = re.compile(r"(?<!td)\.nivel-\d+\s*\{")

# DL-024/DE-053: o CSS virou sistema de tokens (docs/projeto/
# direcao-de-arte.md §1 — "nenhuma cor ou medida solta fora das
# variáveis"). O padding da célula comum, que antes era um número `rem`
# literal na própria regra, agora é `var(--esp-N)` apontando para o
# :root. Resolver a variável ANTES de comparar mantém o teste medindo o
# EFEITO (o valor final em rem) — a invariante que ele defende (aditivo,
# prefixado, estritamente crescente) não mudou; só a representação do
# valor-base mudou, e um parser cego a `var()` não é mais able a "ler o
# CSS como texto" de verdade. Tocado nesta etapa (DL-024): relatado no
# fechamento da etapa, não é enfraquecimento — os mesmos limites
# (nivel-0/1 == padding_base; passo == 1.25rem; estritamente crescente)
# continuam verificados, e o defeito original (ME2, especificidade sem
# prefixo) continua coberto por `_REGRA_NIVEL_SEM_PREFIXO` sem alteração.
_TOKEN_NO_ROOT = re.compile(r"--([\w-]+):\s*([0-9.]+)rem")


def _tokens_do_root(css_texto):
    """`{nome-sem-'--': Decimal(valor-em-rem)}` para todo token do :root
    declarado em rem (a escala de espaçamento inteira é assim)."""
    return {nome: Decimal(valor) for nome, valor in _TOKEN_NO_ROOT.findall(css_texto)}


def _resolver_rem(bruto, tokens):
    """Aceita tanto `1.25rem` (literal) quanto `var(--esp-3)` (token) e
    devolve o Decimal em rem dos dois jeitos — é a MESMA grandeza, só a
    representação difere."""
    bruto = bruto.strip()
    casamento_var = re.fullmatch(r"var\(--([\w-]+)\)", bruto)
    if casamento_var:
        nome = casamento_var.group(1)
        assert nome in tokens, f"token --{nome} não está declarado no :root"
        return tokens[nome]
    casamento_literal = re.fullmatch(r"([0-9.]+)rem", bruto)
    assert casamento_literal, (
        f"valor de padding não reconhecido (nem rem literal, nem var()): {bruto!r}"
    )
    return Decimal(casamento_literal.group(1))


def _parse_indentacao_do_css(css_texto):
    """Lê `static/css/base.css` como STRING e devolve
    `(padding_base_rem, {nivel: padding_left_rem})` — sem abrir
    navegador nenhum. `padding_base_rem` vem da regra genérica
    `.tabela-dados th, .tabela-dados td { padding: Y X; ... }` (o
    segundo valor do atalho `padding` é o `padding-left`/`padding-right`
    na forma de duas grandezas, literal ou `var(--esp-N)`). Cada entrada
    de `niveis` só existe se a regra `.nivel-N` correspondente estiver
    PREFIXADA por `.tabela-dados td` — é a mesma checagem de
    especificidade que o comentário do CSS documenta, agora verificada
    por texto.
    """
    tokens = _tokens_do_root(css_texto)

    casamento_base = re.search(
        r"\.tabela-dados td\s*\{[^}]*padding:\s*[0-9.a-z()\-]+?\s+([0-9.a-z()\-]+?);",
        css_texto,
    )
    assert casamento_base, "não encontrei a regra de padding da célula comum (.tabela-dados td)"
    padding_base = _resolver_rem(casamento_base.group(1), tokens)

    niveis = {}
    for casamento in _REGRA_NIVEL_PREFIXADA.finditer(css_texto):
        niveis[int(casamento.group(1))] = _resolver_rem(casamento.group(2), tokens)
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


def _renderizar_e_medir(corpo_html, seletor, *, css_texto=None):
    """Renderiza `corpo_html` (com `css_texto`, ou o CSS REAL do projeto —
    static/css/base.css — se omitido) num Chromium headless e devolve o
    `padding-left` computado de cada elemento que casa `seletor`, na
    ordem do DOM.

    R2-6: só medir o EFEITO (getComputedStyle) prova que a indentação
    funciona — o teste que já existia
    (`test_indentacao_..._nunca_usa_style_inline`, em
    test_dl017_rodada1_correcoes.py) verifica a AUSÊNCIA de `style=`
    inline, que é a FORMA da correção da rodada 1, não o EFEITO desta. O
    mutante ME2 do relatório da rodada 2 (trocar `.tabela-dados
    td.nivel-N` por `.nivel-N`) sobrevivia a 487 testes exatamente porque
    nenhum deles chegava a medir isto.

    Hardening pós-`aa10f20`: `--disable-dev-shm-usage` (um `/dev/shm`
    pequeno ou ausente em contêiner é causa clássica do processo morrer
    com `SIGKILL`, retorno -9) e um `--user-data-dir` TEMPORÁRIO E
    PRÓPRIO por chamada (nunca um perfil compartilhado, que pode estar
    travado por outro processo desta sessão). Mesmo assim, se o
    navegador falhar aqui — timeout, exceção do sistema operacional, DOM
    sem o `<title>` esperado — este teste PULA, nunca reprova a suíte: a
    classe "recurso externo de ambiente indisponível ou quebrado" nunca
    pode derrubar o build por si só. A checagem de capacidade
    (`_chromium_funciona`, uma vez por sessão) já deveria ter pulado
    antes de chegar aqui — isto é defesa em profundidade, não a primeira
    linha de defesa.

    R5-1/BL-140: o modo de falha MEDIDO na CI não foi nenhum dos dois
    acima — foi `<title>` PRESENTE e NÃO-JSON. O snap do Chromium (ver o
    docstring de `_chromium_funciona`) sobe, renderiza, devolve DOM real
    — só que da PRÓPRIA PÁGINA DE ERRO, cujo `<title>` é a URL
    `file://...` pedida, não o `JSON.stringify` que o script acima
    escreveria. O `json.loads` de antes ficava FORA de qualquer `try`:
    um título assim virava `JSONDecodeError` cru, **reprovando a suíte**
    — a nona ocorrência de "comentário que promete mais que a defesa
    entrega" (este docstring já dizia "nunca reprova a suíte" e não
    entregava). Agora o `json.loads` está no MESMO `try` que decide
    pular: título que não é JSON é ambiente quebrado, não regressão de
    CSS.
    """
    if css_texto is None:
        css_texto = Path("static/css/base.css").read_text(encoding="utf-8")
    script = f"""
    <script>
    var els = document.querySelectorAll({seletor!r});
    var out = [];
    els.forEach(function(e) {{ out.push(getComputedStyle(e).paddingLeft); }});
    document.title = JSON.stringify(out);
    </script>
    """
    html = (
        f"<!DOCTYPE html><html><head><style>{css_texto}</style></head>"
        f"<body>{corpo_html}{script}</body></html>"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        caminho_html = f.name
    try:
        # R6-1/BL-195: mesma troca de `_chromium_funciona`, e aqui ela é a
        # metade GRAVE do achado — o `except (TimeoutExpired, OSError)`
        # abaixo está DENTRO do `with`, então cobria a exceção da CHAMADA e
        # nunca a da SAÍDA do `with`. Com `TemporaryDirectory`, a
        # `ENOTEMPTY` do descarte escapava desta função como `OSError` cru
        # (medido 3 de 3), reprovando a suíte e contradizendo o docstring
        # acima, que promete pulo. Ver o comentário do helper.
        with _perfil_de_navegador_descartavel() as perfil:
            try:
                resultado = subprocess.run(
                    [
                        _CHROMIUM,
                        "--headless=new",
                        "--disable-gpu",
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        f"--user-data-dir={perfil}",
                        "--dump-dom",
                        f"file://{caminho_html}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=_TIMEOUT_MEDICAO_S,
                )
            except (subprocess.TimeoutExpired, OSError) as exc:
                pytest.skip(f"Chromium presente mas não funcionou ao medir: {exc!r}")
        casamento = re.search(r"<title>(.*?)</title>", resultado.stdout, re.DOTALL)
        if not casamento:
            pytest.skip(
                "Chromium presente mas não devolveu <title> ao medir: "
                f"stdout={resultado.stdout[:300]!r} stderr={resultado.stderr[:300]!r}"
            )
        # R5-1/BL-140: `<title>` PRESENTE, mas não-JSON, é a assinatura do
        # snap (ver o docstring desta função) — ambiente quebrado, não
        # regressão de CSS. Mesmo `pytest.skip` que os dois casos acima,
        # nunca um `JSONDecodeError` cru reprovando a suíte.
        try:
            return json.loads(casamento.group(1))
        except json.JSONDecodeError:
            pytest.skip(
                "Chromium presente mas devolveu <title> que não é JSON ao "
                f"medir (ambiente quebrado, não regressão de CSS): {casamento.group(1)[:300]!r}"
            )
    finally:
        # R6-1/BL-195: ver o `finally` equivalente em `_chromium_funciona`
        # — descarte no `finally` propaga por cima de qualquer `except`.
        _descartar_caminho_temporario(caminho_html)


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
    _pular_se_chromium_nao_funcional()
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

    padding_celula_comum = _renderizar_e_medir(tabela, "td:not([class])")
    assert padding_celula_comum, "esperava ao menos uma célula sem classe de nível (ex.: Código)"
    base_px = int(padding_celula_comum[0].removesuffix("px"))

    # Consulta CADA nível separadamente (não uma lista combinada): o
    # cenário (`cen`) já tem duas contas raiz próprias (Caixa, Receita),
    # então "nivel-1" nunca tem só UM elemento — o que importa é que TODO
    # elemento de um nível dá o MESMO padding, e que o valor sobe 20px de
    # nível para nível, não a posição numa lista combinada.
    def _valores_unicos(nivel):
        valores = _renderizar_e_medir(tabela, f".nivel-{nivel}")
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


def test_mutante_me2_especificidade_reduzida_e_detectado_pela_medicao():
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
    _pular_se_chromium_nao_funcional()
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
    valores_sob_mutante = _renderizar_e_medir(
        tabela, ".nivel-1, .nivel-2, .nivel-3", css_texto=css_mutado
    )

    # Sob o mutante, os três níveis colapsam no MESMO padding — a asserção
    # "estritamente crescente" do teste real FALHARIA aqui. É a prova de
    # que o teste morre sob ME2.
    assert len(set(valores_sob_mutante)) == 1, (
        "o mutante deveria achatar todos os níveis no mesmo padding-left",
        valores_sob_mutante,
    )


# ---------------------------------------------------------------------------
# A4/BL-129 — par ESTRUTURAL + COMPORTAMENTAL para a condição de pulo dos
# testes de efeito. O teste antigo (`assert _CHROMIUM_FUNCIONAL in (True,
# False)`) era uma TAUTOLOGIA — `_chromium_funciona` só pode devolver um
# `bool`, então a asserção nunca podia falhar, e o mutante MH (trocar
# `not _CHROMIUM_FUNCIONAL` por `_CHROMIUM is None` — a condição EXATA
# que derrubou a CI em `aa10f20`) sobrevivia a 608 testes. Substituído
# pelos dois abaixo, que juntos PEGAM esse mutante.
# ---------------------------------------------------------------------------


def test_gate_de_navegador_deriva_de_chromium_funcional_nao_de_chromium():
    """ESTRUTURAL: lê o CÓDIGO-FONTE de `_pular_se_chromium_nao_funcional`
    (a função que os dois testes de efeito chamam) e afirma que ela decide
    por `_CHROMIUM_FUNCIONAL` — nunca pela forma que derrubou a CI em
    `aa10f20` (`_CHROMIUM is None`, presença de binário). Pega o mutante
    MH pela FORMA, antes de qualquer coisa rodar; o par comportamental
    abaixo pega pelo EFEITO.
    """
    codigo_fonte = inspect.getsource(_pular_se_chromium_nao_funcional)
    assert "_CHROMIUM_FUNCIONAL" in codigo_fonte
    assert "_CHROMIUM is None" not in codigo_fonte


def test_chamadores_do_gate_pulam_pela_funcao_compartilhada():
    """ESTRUTURAL, complementar: os dois testes de EFEITO chamam
    `_pular_se_chromium_nao_funcional()` como parte do próprio corpo —
    nenhum dos dois volta a usar `@pytest.mark.skipif` direto (o que
    reabriria o buraco do A4 por outro caminho, mesmo com a função acima
    correta).
    """
    for teste in (
        test_indentacao_hierarquica_e_aditiva_e_estritamente_crescente_por_nivel,
        test_mutante_me2_especificidade_reduzida_e_detectado_pela_medicao,
    ):
        assert "_pular_se_chromium_nao_funcional()" in inspect.getsource(teste), teste.__name__
        assert not any(marca.name == "skipif" for marca in getattr(teste, "pytestmark", [])), (
            teste.__name__
        )


def test_pular_dispara_quando_chromium_nao_funcional(monkeypatch):
    """COMPORTAMENTAL (metade 1): força `_CHROMIUM_FUNCIONAL = False` — o
    cenário real da CI antes da BL-119 — e exige que
    `_pular_se_chromium_nao_funcional()` de fato PULE, com o motivo
    declarado. Isto é o que o mutante MH, se reaplicado, faria parar de
    acontecer: com `_CHROMIUM is None` no lugar de `_CHROMIUM_FUNCIONAL`,
    forçar esta variável para `False` NÃO mudaria nada, porque `_CHROMIUM`
    (o caminho do binário) continuaria não-`None` no ambiente real.
    """
    monkeypatch.setattr(
        "apps.contabilidade.tests.test_dl017_rodada2_frontend._CHROMIUM_FUNCIONAL",
        False,
    )
    # `pytest.skip.Exception` é o alias PÚBLICO da exceção que
    # `pytest.skip()` levanta — documentado exatamente para este caso,
    # testar código que chama `pytest.skip()` sem depender de `_pytest`.
    with pytest.raises(pytest.skip.Exception) as excinfo:
        _pular_se_chromium_nao_funcional()
    assert "navegador" in str(excinfo.value).lower()


def test_nao_pular_quando_chromium_funcional(monkeypatch):
    """COMPORTAMENTAL (metade 2), controle: com `_CHROMIUM_FUNCIONAL =
    True` forçado, a função NÃO pula — devolve normalmente. Sem este
    controle, uma versão de `_pular_se_chromium_nao_funcional` que
    sempre pulasse (não só quando deveria) passaria no teste acima e
    esconderia os dois testes de efeito atrás de um pulo permanente.
    """
    monkeypatch.setattr(
        "apps.contabilidade.tests.test_dl017_rodada2_frontend._CHROMIUM_FUNCIONAL",
        True,
    )
    _pular_se_chromium_nao_funcional()  # não deve levantar nem pular


@pytest.mark.parametrize("comportamento", ["dormir_alem_do_timeout", "sair_com_erro"])
def test_binario_presente_mas_quebrado_e_detectado_sem_travar(tmp_path, comportamento):
    """Prova da CLASSE de correção — não só do caso — pedida na revisão
    depois da queda da CI em `aa10f20`: um executável chamado
    "chromium" que EXISTE mas não FUNCIONA precisa fazer
    `_chromium_funciona` devolver `False`, **dentro do timeout que ela
    recebeu** e SEM lançar exceção — exatamente o cenário do runner do
    GitHub: binário presente, navegador não funcional.

    Os dois comportamentos cobrem as duas classes clássicas de falha
    citadas pelo arquiteto-senior: travar (o processo nunca retorna —
    aqui simulado por `sleep`, no lugar do travamento real por D-Bus/
    sandbox/`/dev/shm`) e sair com erro (`exit 1`, no lugar de uma
    falha de inicialização que o Chromium real reportaria com código
    diferente de zero).

    R6-1/BL-195: o timeout passa a ser EXPLÍCITO neste teste (2s), e a
    afirmação é "respeita o teto que recebeu", não mais "tem um teto
    curto próprio, menor que o das medições". O padrão da função subiu
    para os mesmos 30s da medição (ver `_TIMEOUT_MEDICAO_S` e o motivo
    medido lá); herdar esse padrão aqui somaria 30s de `sleep` à suíte
    para provar a mesma coisa. A promessa escrita e o que o teste
    entrega ficam iguais — é a família de defeito desta etapa inteira.
    """
    teto_curto_s = 2
    script = tmp_path / "chromium-quebrado"
    if comportamento == "dormir_alem_do_timeout":
        script.write_text(f"#!/bin/sh\nsleep {teto_curto_s + 30}\n")
    else:
        script.write_text("#!/bin/sh\nexit 1\n")
    script.chmod(0o755)

    inicio = time.monotonic()
    assert _chromium_funciona(str(script), timeout=teto_curto_s) is False
    duracao = time.monotonic() - inicio
    assert duracao < teto_curto_s + 5, duracao
    if comportamento == "dormir_alem_do_timeout":
        # O diagnóstico precisa nomear o teto REALMENTE usado — era ele
        # que, fixo em 10s, fazia o `-rs` da CI acusar "timeout de 10s"
        # para um binário que o outro job do mesmo commit conseguiu usar.
        assert f"timeout de {teto_curto_s}s" in _DIAGNOSTICO_CHROMIUM


# ---------------------------------------------------------------------------
# R5-1/BL-140 — a checagem de capacidade tem que exercitar o MESMO
# mecanismo (`file://` sobre um arquivo temporário) que a medição real usa
# — não um atalho (`data:`) que nunca toca o sistema de arquivos. É
# exatamente esse atalho que deixou passar o snap do Chromium na CI: ele
# "funciona" para `data:` e falha (silenciosamente, devolvendo a própria
# URL como `<title>`) só para `file://`.
# ---------------------------------------------------------------------------


def test_chromium_funciona_detecta_navegador_que_so_falha_em_file(tmp_path):
    """Simula EXATAMENTE o sintoma medido pelo auditor no snap do Ubuntu:
    um "navegador" que processa uma URL `data:` normalmente (devolveria
    `True` numa checagem que usasse `data:`, como a de antes desta
    correção), mas devolve a PRÓPRIA URL como `<title>` quando recebe
    `file://` — porque não enxerga o arquivo (perfil confinado, `/tmp`
    privado). Antes do R5-1/BL-140, `_chromium_funciona` teria devolvido
    `True` aqui (mediu o mecanismo ERRADO); depois, devolve `False`,
    porque agora testa `file://`, o MESMO caminho da medição real —
    exatamente o que teria pulado os dois testes de efeito na CI em vez
    de deixá-los falhar.
    """
    script = tmp_path / "chromium-tipo-snap"
    script.write_text(
        "#!/bin/bash\n"
        'ultimo="${!#}"\n'
        'case "$ultimo" in\n'
        '  file://*) echo "<title>$ultimo</title>" ;;\n'
        '  *) echo "<title>sessao-de-verificacao-por-arquivo</title>" ;;\n'
        "esac\n"
        "exit 0\n"
    )
    script.chmod(0o755)
    assert _chromium_funciona(str(script)) is False


def test_chromium_funciona_aceita_navegador_que_le_arquivo_de_verdade(tmp_path):
    """Controle do teste acima: um "navegador" que devolve a marca
    esperada tanto para `data:` quanto para `file://` (o caso REAL, sem
    snap) continua sendo aceito — sem este controle, uma versão de
    `_chromium_funciona` que sempre devolvesse `False` passaria no teste
    de cima e escondería os testes de efeito atrás de um pulo permanente.
    """
    script = tmp_path / "chromium-de-verdade"
    script.write_text("#!/bin/bash\necho '<title>sessao-de-verificacao-por-arquivo</title>'\n")
    script.chmod(0o755)
    assert _chromium_funciona(str(script)) is True


def test_chromium_funciona_usa_file_nao_data(tmp_path):
    """ESTRUTURAL, complementar aos dois comportamentais acima: a
    checagem de capacidade constrói a URL com `file://`, nunca com
    `data:` — a inspeção de texto pega o retrocesso antes mesmo de rodar
    um processo.
    """
    codigo_fonte = inspect.getsource(_chromium_funciona)
    assert 'f"file://{caminho_html}"' in codigo_fonte
    assert "data:text/html" not in codigo_fonte


def test_renderizar_e_medir_pula_quando_title_nao_e_json(monkeypatch, tmp_path):
    """R5-1/BL-140 — reproduz o sintoma medido na CI diretamente na
    função de MEDIÇÃO (não só na checagem de capacidade): um Chromium que
    devolve `<title>` PRESENTE, mas igual à própria URL `file://` pedida
    (não o `JSON.stringify` que o script real escreveria). Antes desta
    correção, `json.loads` sobre isso era `json.JSONDecodeError` CRU,
    reprovando a suíte — o `pytest.skip.Exception` é o efeito exigido
    agora, exatamente como qualquer outra falha de ambiente já tratada
    por esta função.
    """
    script = tmp_path / "chromium-tipo-snap-na-medicao"
    script.write_text('#!/bin/bash\nultimo="${!#}"\necho "<title>$ultimo</title>"\nexit 0\n')
    script.chmod(0o755)

    import apps.contabilidade.tests.test_dl017_rodada2_frontend as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM", str(script))
    with pytest.raises(pytest.skip.Exception) as excinfo:
        _renderizar_e_medir("<p></p>", "p", css_texto="")
    assert "json" in str(excinfo.value).lower() or "não é json" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# R6-1/BL-195 (rodada 6) — a OUTRA METADE do par acima: falha na LIMPEZA do
# recurso temporário. O `test_renderizar_e_medir_pula_quando_title_nao_e_
# json` cobre "o navegador respondeu coisa errada"; os quatro testes a
# seguir cobrem "o navegador respondeu certo e o DESCARTE do perfil
# falhou", que é o que de fato acontece no runner do GitHub.
#
# A falha é forçada substituindo `shutil.rmtree` por uma função que levanta
# a MESMA exceção medida na integração contínua (`OSError(39,
# 'Directory not empty')`). É deliberado NÃO reproduzir a corrida real
# (um navegador falso que deixa um processo filho gravando no perfil):
# ela depende de o filho vencer o descarte, e um teste cuja evidência
# depende de quem chega primeiro é a família de defeito que esta etapa
# passou seis rodadas pagando. A corrida real foi reproduzida à mão, 3 de
# 3, antes da correção; o que fica versionado é o efeito, determinístico.
# ---------------------------------------------------------------------------


_ENOTEMPTY_DO_RUNNER = OSError(39, "Directory not empty")


def _fazer_a_limpeza_falhar(monkeypatch):
    """Substitui `shutil.rmtree` por uma função que SEMPRE levanta a
    exceção medida no runner. Afeta tanto `_descartar_caminho_temporario`
    quanto o `__exit__` de um eventual `tempfile.TemporaryDirectory` (que
    também descarta por `shutil.rmtree`) — é o que faz o mutante "voltar a
    usar `TemporaryDirectory`" morrer nestes testes.
    """

    def rmtree_que_falha(*args, **kwargs):
        raise _ENOTEMPTY_DO_RUNNER

    monkeypatch.setattr(shutil, "rmtree", rmtree_que_falha)


def test_descarte_de_temporario_nunca_levanta_mesmo_quando_a_limpeza_falha(monkeypatch, tmp_path):
    """Unidade do ponto único de descarte: com a limpeza falhando, a
    função devolve normalmente — nunca propaga `OSError`. É a classe
    inteira em uma linha ("falha na limpeza do recurso não reprova a
    suíte"), no nível mais baixo em que ela pode ser afirmada.
    """
    _fazer_a_limpeza_falhar(monkeypatch)
    diretorio = tmp_path / "perfil"
    diretorio.mkdir()
    _descartar_caminho_temporario(str(diretorio))  # não deve levantar


def test_perfil_descartavel_de_fato_apaga_o_diretorio_quando_consegue():
    """Controle do teste acima — sem ele, um `_descartar_caminho_
    temporario` que não fizesse NADA passaria em todos os outros testes
    deste bloco, e o instrumento passaria a vazar um diretório de perfil
    por medição.
    """
    with _perfil_de_navegador_descartavel() as perfil:
        assert os.path.isdir(perfil)
        Path(perfil, "algum-arquivo-de-perfil").write_text("x", encoding="utf-8")
    assert not os.path.exists(perfil)


def test_chromium_funciona_aceita_navegador_bom_com_limpeza_de_perfil_falhando(
    monkeypatch, tmp_path
):
    """O FALSO NEGATIVO medido na integração contínua, como teste: um
    navegador que renderiza CERTO (código 0 e a marca esperada no DOM)
    continua sendo aceito mesmo quando o descarte do `--user-data-dir`
    falha. Antes da correção, esta situação devolvia `False` com o
    diagnóstico "erro de sistema operacional AO EXECUTAR" — e por isso as
    duas medições de CSS por efeito nunca rodaram na integração contínua,
    em nenhuma rodada.
    """
    script = tmp_path / "chromium-bom-com-limpeza-ruim"
    script.write_text("#!/bin/bash\necho '<title>sessao-de-verificacao-por-arquivo</title>'\n")
    script.chmod(0o755)
    _fazer_a_limpeza_falhar(monkeypatch)

    assert _chromium_funciona(str(script)) is True


def test_renderizar_e_medir_mede_normalmente_com_limpeza_de_perfil_falhando(monkeypatch, tmp_path):
    """A ARMADILHA, como teste: com o descarte do perfil falhando, uma
    medição BEM-SUCEDIDA continua devolvendo a medida — nunca um `OSError`
    cru. Era exatamente isto que estouraria na integração contínua no
    instante em que alguém subisse o timeout sem tirar o descarte da
    região julgada (medido pelo auditor, 3 de 3).
    """
    script = tmp_path / "chromium-que-mede-com-limpeza-ruim"
    script.write_text("#!/bin/bash\necho '<title>[\"12px\"]</title>'\n")
    script.chmod(0o755)

    import apps.contabilidade.tests.test_dl017_rodada2_frontend as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM", str(script))
    _fazer_a_limpeza_falhar(monkeypatch)

    assert _renderizar_e_medir("<p></p>", "p", css_texto="") == ["12px"]


def test_renderizar_e_medir_pula_quando_limpeza_falha_e_o_titulo_nao_serve(monkeypatch, tmp_path):
    """As duas falhas SOMADAS — ambiente com navegador inútil E descarte
    de perfil falhando. O desfecho exigido é o pulo com motivo (a falha de
    AMBIENTE que o instrumento já sabia relatar), nunca o `OSError` da
    limpeza, que chegaria ANTES e esconderia o motivo real.
    """
    script = tmp_path / "chromium-inutil-com-limpeza-ruim"
    script.write_text('#!/bin/bash\nultimo="${!#}"\necho "<title>$ultimo</title>"\nexit 0\n')
    script.chmod(0o755)

    import apps.contabilidade.tests.test_dl017_rodada2_frontend as este_modulo

    monkeypatch.setattr(este_modulo, "_CHROMIUM", str(script))
    _fazer_a_limpeza_falhar(monkeypatch)

    with pytest.raises(pytest.skip.Exception) as excinfo:
        _renderizar_e_medir("<p></p>", "p", css_texto="")
    assert "json" in str(excinfo.value).lower()


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
