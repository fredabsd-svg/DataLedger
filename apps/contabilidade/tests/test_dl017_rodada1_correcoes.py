"""Correções da rodada 1 da auditoria da DL-017 (docs/auditorias/
2026-09-14-dl-017-rodada-1.md), achados 1 a 6 e 8, 10 a 14 — BL-87 a BL-99.

Usa o urlconf REAL (`config/urls.py`), sem `pytest.mark.urls`: as rotas da
tela (`contabilidade_web:`) e da API (`contabilidade:`) já estão costuradas
lá (achado 9 / BL-95, corrigido pelo desenvolvedor-pleno). Dados 100%
sintéticos, criados nos próprios testes.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
)
from apps.contabilidade.views import TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório de teste", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa de Teste Ltda", cnpj="11122233000183"
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
        username="gestora", email="gestora@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora", password="senha-forte-123")


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _url_api(cen):
    return reverse("contabilidade:lancamentos", args=[cen["empresa"].id])


def _post_tela(client, cen, valor_texto, *, chave, historico="Equivalência tela/API", extra=None):
    dados = {
        "acao": "gravar",
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": historico,
        "chave_idempotencia": chave,
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": valor_texto,
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": valor_texto,
    }
    if extra:
        dados.update(extra)
    return client.post(_url_tela(cen), dados)


def _post_api(client, cen, valor_texto, *, chave, historico="Equivalência tela/API"):
    corpo = {
        "data": timezone.localdate().isoformat(),
        "historico": historico,
        "itens": [
            {"conta": cen["caixa"].id, "tipo": "debito", "valor": valor_texto},
            {"conta": cen["receita"].id, "tipo": "credito", "valor": valor_texto},
        ],
    }
    return client.post(
        _url_api(cen), corpo, content_type="application/json", HTTP_IDEMPOTENCY_KEY=chave
    )


# ---------------------------------------------------------------------------
# BL-87 (achado 1) + BL-89 (achado 2, DE-027): equivalência tela <-> API
# ---------------------------------------------------------------------------

# Textos SEM tradução de locale ambígua: ou não têm vírgula (a troca
# comma->ponto de `_decimal_do_formulario` é um no-op), ou têm vírgula que
# CONTINUA malformada depois da troca (espaço remanescente, múltiplas
# vírgulas). Para estes, a tela e a API devem concordar sobre o mesmo texto
# LITERAL — é a comparação que o auditor fez (mesmos textos, os dois
# caminhos) e é o núcleo de BL-87/89.
TEXTOS_SEMPRE_RECUSADOS = [
    "NaN",
    "nan",
    "-NaN",
    "sNaN",
    "Infinity",
    "inf",
    "-Infinity",
    "1e500",
    "1e3",
    "1E-3",
    "1_000",
    "1,2,3",
    "--10",
    "10,00 ",  # espaço à direita: sobra depois da troca de vírgula por ponto
]


@pytest.mark.parametrize("texto", TEXTOS_SEMPRE_RECUSADOS)
def test_tela_e_api_recusam_o_mesmo_texto_nunca_500(client, cen, texto):
    """BL-87 (achado 1): nenhum destes textos pode derrubar a tela com 500
    — antes da correção, 8 deles (NaN/variantes, Infinity/variantes,
    1e500) derrubavam `_valor_ptbr` com `ValueError`/`InvalidOperation` ao
    tentar formatar a mensagem de recusa.

    BL-89 (achado 2, DE-027): para o MESMO texto, tela e API dão o MESMO
    veredito — aqui, as duas RECUSAM (400), porque `_decimal_do_formulario`
    delega o julgamento de formato a `para_decimal`, o MESMO módulo que a
    API usa.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()

    resposta_tela = _post_tela(client, cen, texto, chave=f"tela-{texto}")
    assert resposta_tela.status_code == 400, (texto, resposta_tela.status_code)

    resposta_api = _post_api(client, cen, texto, chave=f"api-{texto}")
    assert resposta_api.status_code == 400, (texto, resposta_api.status_code, resposta_api.content)

    assert LancamentoContabil.objects.count() == antes


# ---------------------------------------------------------------------------
# DE-029 (rodada 2): este teste SUBSTITUI o antigo
# `test_tela_e_api_aceitam_o_mesmo_texto_sem_virgula`, que parametrizava
# ["100.00", "1", "0.50", "1500.00"] como "controle positivo da
# equivalência". Essa premissa estava ERRADA: os quatro textos são o
# formato CANÔNICO DA API (ponto como separador DECIMAL), não pt-BR — e a
# DE-029 institui uma gramática pt-BR explícita (`^[+-]?(\d+|\d{1,3}
# (\.\d{3})+)(,\d{1,2})?$`) que RECUSA três deles na tela ("100.00",
# "0.50", "1500.00": nenhum é grupo de milhar bem formado). Isso não é
# regressão — é exatamente o comportamento que fechou o bloqueador R2-1
# ("1.000" gravado como 1,00): "10.00"/"100.00" deixam de ser
# reinterpretados como pt-BR "por acidente", porque deixam de ser aceitos
# nenhuma leitura.
#
# Os dois testes abaixo separam o que era uma única afirmação confusa em
# duas verdadeiras: um texto pt-BR bem formado (dígitos, ponto de milhar a
# cada três casas, vírgula de centavos) grava o MESMO valor nos dois
# caminhos; um texto no formato canônico da API (ponto DECIMAL) é
# RECUSADO pela tela e ACEITO pela API — divergência intencional, prevista
# na própria DE-029.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("texto", ["1", "1000", "1.000", "0,50", "1.234.567,89"])
def test_tela_e_api_aceitam_o_mesmo_texto_quando_e_pt_br_valido(client, cen, texto):
    """DE-029: para um texto DENTRO da gramática pt-BR (dígitos sem
    separador, ou agrupados de três em três por ponto, com centavos
    opcionais depois da vírgula), a tela grava o mesmo valor que a API
    grava para a TRADUÇÃO desse mesmo texto (pontos de milhar removidos,
    vírgula decimal virada ponto) — a única tradução de locale que a tela
    faz, e a mesma que ela aplica internamente antes de perguntar a
    `para_decimal`.
    """
    _login(client, cen)
    resposta_tela = _post_tela(client, cen, texto, chave=f"tela-ptbr-{texto}")
    assert resposta_tela.status_code == 302, (texto, resposta_tela.status_code)

    traduzido = texto.replace(".", "").replace(",", ".")
    resposta_api = _post_api(client, cen, traduzido, chave=f"api-ptbr-{texto}")
    assert resposta_api.status_code == 201, (texto, resposta_api.status_code, resposta_api.content)


@pytest.mark.parametrize("texto", ["100.00", "0.50", "1500.00", "10.00"])
def test_tela_recusa_formato_canonico_da_api_por_nao_ser_pt_br(client, cen, texto):
    """DE-029: ponto como separador DECIMAL ("100.00") não é uma leitura
    pt-BR válida — não é grupo de milhar bem formado (exige exatamente
    três dígitos após cada ponto). A tela RECUSA (recusar é o
    comportamento CORRETO: reinterpretar seria adivinhar entre duas
    leituras possíveis do mesmo texto); a API, que fala o formato dela
    mesma, ACEITA o texto literal. A divergência é intencional e
    documentada na DE-029 ("10.00 passa a ser recusado, e isso é
    correto") — diferente da equivalência que se aplica ao que ESTÁ
    dentro da gramática de cada porta (teste acima).
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    resposta_tela = _post_tela(client, cen, texto, chave=f"tela-canonico-{texto}")
    assert resposta_tela.status_code == 400, (texto, resposta_tela.status_code)
    assert LancamentoContabil.objects.count() == antes

    resposta_api = _post_api(client, cen, texto, chave=f"api-canonico-{texto}")
    assert resposta_api.status_code == 201, (texto, resposta_api.status_code, resposta_api.content)


def test_valor_com_sinal_positivo_e_espaco_na_tela_documentado(client, cen):
    """Achado 2, ressalva de método: `para_decimal("+100.00")` é
    comportamento ESTABELECIDO e testado (`apps/core/tests/test_dinheiro.
    py`) — não é meu para alterar. Depois da correção de DE-027, a tela
    converte "+10,00" para "+10.00" e ENTREGA a `para_decimal`, que aceita
    o sinal "+" — a tela grava 10,00. Isto diverge do que a API faz se
    receber o MESMO texto ("+10,00") literalmente: a API nunca traduz
    vírgula (não é o formato dela), então a vírgula por si só já reprova
    pelo regex. A divergência aqui não é um guarda contornado (o valor
    numérico é o MESMO nos dois casos, 10,00) — é a tela aplicando a ÚNICA
    tradução de locale que lhe cabe (DE-027) antes de perguntar ao mesmo
    juiz. Registrado como decisão a confirmar com o arquiteto-senior (ver
    relatório de entrega) — este teste apenas fixa o comportamento ATUAL,
    para não regredir sem ninguém notar.
    """
    _login(client, cen)
    resposta = _post_tela(client, cen, "+10,00", chave="sinal-positivo")
    assert resposta.status_code == 302
    lancamento = LancamentoContabil.objects.get()
    assert {item.valor for item in lancamento.itens.all()} == {Decimal("10.00")}


# ---------------------------------------------------------------------------
# Varredura adicional (critério de aceite 1): mesma classe de defeito em
# outros campos do POST que chegam direto ao banco sem checagem de limite.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "9" * 30,  # 30 dígitos: maior que LIMITE_MAGNITUDE_VALOR (10**16), formato válido
        "1" + "0" * 20,
    ],
)
def test_valor_com_magnitude_absurda_nunca_500(client, cen, texto):
    """Achado da varredura (critério de aceite 1, não relatado pelo
    auditor): um valor com FORMATO válido (só dígitos, sem vírgula/ponto)
    mas magnitude maior do que `ItemLancamento.valor` comporta
    (DecimalField max_digits=18, decimal_places=2) passava por
    `_decimal_do_formulario` (finito, formato ok) e só falhava no INSERT
    do Postgres com `DataError: numeric field overflow` — 500, mesma
    classe dos achados 1 e 4. `_itens_e_totais` agora verifica o MESMO
    `LIMITE_MAGNITUDE_VALOR` que a API já verificava em `_extrair_itens`.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    resposta = _post_tela(client, cen, texto, chave=f"magnitude-{texto}")
    assert resposta.status_code == 400, (texto, resposta.status_code)
    assert LancamentoContabil.objects.count() == antes
    assert "grande demais" in resposta.content.decode()


def test_chave_idempotencia_longa_nunca_500(client, cen):
    """Achado da varredura (critério de aceite 1): `chave_idempotencia` é
    um campo OCULTO (o navegador nunca a alonga), mas nada impedia um
    POST direto com um valor maior que `LancamentoContabil.
    chave_idempotencia` (CharField max_length=255) — reproduzido antes da
    correção: `django.db.utils.DataError: value too long for type
    character varying(255)`, um 500 cru no INSERT. A API já tem o mesmo
    limite (`TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA`); a tela agora reaproveita
    o mesmo valor.
    """
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    chave_longa = "k" * (TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA + 1)
    resposta = client.post(
        _url_tela(cen),
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "chave longa",
            "chave_idempotencia": chave_longa,
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "10,00",
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": "10,00",
        },
    )
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    assert "chave de idempotência" in resposta.content.decode().lower()


# ---------------------------------------------------------------------------
# BL-88 (achado 3): rodapé de conferência
# ---------------------------------------------------------------------------


def test_adicionar_linha_mostra_o_total_real_das_linhas_preenchidas(client, cen):
    """Achado 3 / BL-88: antes da correção, `acao=adicionar_linha` com as
    linhas JÁ preenchidas devolvia rodapé "0,00 / 0,00", HTTP 200 — o
    único total que esta tela mostra num caminho sem erro (não há
    JavaScript, critério 15) estava sempre errado. Agora o rodapé é a
    soma real das linhas exibidas.
    """
    _login(client, cen)
    resposta = client.post(
        _url_tela(cen),
        {
            "acao": "adicionar_linha",
            "num_linhas": "4",
            "data": timezone.localdate().isoformat(),
            "historico": "conferência",
            "chave_idempotencia": "k-conferencia",
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": "1.500,00",
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": "1.500,00",
        },
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)
    valores_rodape = re.findall(r'class="valor-monetario">([^<]+)<', rodape)
    assert valores_rodape == ["1.500,00", "1.500,00"], valores_rodape
    # As linhas continuam preenchidas na mesma página (nada foi gravado).
    assert LancamentoContabil.objects.count() == 0
    assert re.findall(r'name="valor_\d+" value="([^"]*)"', conteudo)[:2] == [
        "1.500,00",
        "1.500,00",
    ]


def test_get_inicial_mostra_nao_conferido_nunca_0_00(client, cen):
    """BL-88, critério complementar: na primeira visita (GET, formulário em
    branco) o total ainda não foi calculado nenhuma vez — a tela precisa
    dizer isso explicitamente, nunca mostrar "0,00" como se fosse uma
    conferência real já feita.
    """
    _login(client, cen)
    resposta = client.get(_url_tela(cen))
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "ainda não conferido" in conteudo
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)
    assert "0,00" not in rodape


# ---------------------------------------------------------------------------
# BL-90 (achado 4): histórico acima do limite do modelo
# ---------------------------------------------------------------------------


def test_historico_acima_do_limite_do_modelo_nunca_500(client, cen):
    _login(client, cen)
    antes = LancamentoContabil.objects.count()
    resposta = _post_tela(client, cen, "10,00", chave="historico-longo", historico="X" * 400)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == antes
    assert "não pode ter mais de 300 caracteres" in resposta.content.decode()


def test_historico_no_limite_do_modelo_e_aceito(client, cen):
    """Controle positivo: exatamente 300 caracteres continua sendo aceito
    (a correção não pode ter apertado o limite real do modelo)."""
    _login(client, cen)
    resposta = _post_tela(client, cen, "10,00", chave="historico-300", historico="X" * 300)
    assert resposta.status_code == 302, resposta.status_code


# ---------------------------------------------------------------------------
# BL-91 (achado 5): partidas além do teto nunca são descartadas em silêncio
# ---------------------------------------------------------------------------


def test_mais_partidas_que_o_teto_recusa_o_lote_inteiro(client, cen):
    """Achado 5 / BL-91: 22 partidas, as 20 primeiras batendo entre si e as
    2 últimas TAMBÉM batendo entre si (77,00 / 77,00). Antes da correção:
    o lote fechava com 20 partidas gravadas "com sucesso", perdendo
    77,00 de débito e 77,00 de crédito em silêncio. Agora: o POST inteiro
    é recusado, ZERO lançamentos gravados.
    """
    _login(client, cen)
    contas_debito = [
        Conta.objects.create(
            empresa=cen["empresa"],
            codigo=f"1.{i}",
            nome=f"Conta débito {i}",
            tipo=TipoConta.ATIVO,
            natureza=NaturezaConta.DEVEDORA,
        )
        for i in range(1, 12)
    ]
    contas_credito = [
        Conta.objects.create(
            empresa=cen["empresa"],
            codigo=f"2.{i}",
            nome=f"Conta crédito {i}",
            tipo=TipoConta.PATRIMONIO_LIQUIDO,
            natureza=NaturezaConta.CREDORA,
        )
        for i in range(1, 12)
    ]
    dados = {
        "acao": "gravar",
        "num_linhas": "22",
        "data": timezone.localdate().isoformat(),
        "historico": "22 partidas",
        "chave_idempotencia": "k-22-partidas",
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

    resposta = client.post(_url_tela(cen), dados)
    assert resposta.status_code == 400, resposta.status_code
    assert LancamentoContabil.objects.count() == 0
    assert ItemLancamento.objects.count() == 0
    conteudo = resposta.content.decode()
    assert "máximo" in conteudo and "20" in conteudo and "22" in conteudo


def test_teto_de_partidas_mostra_mensagem_explicativa(client, cen):
    """BL-99 (achado 14): ao chegar em 20 linhas, o botão "Adicionar linha"
    desaparece — a tela precisa dizer POR QUE (critério 13, saída
    navegável para um LIMITE, não só para um erro).
    """
    _login(client, cen)
    dados = {
        "acao": "adicionar_linha",
        "num_linhas": "20",
        "data": timezone.localdate().isoformat(),
        "historico": "no teto",
        "chave_idempotencia": "k-teto",
    }
    resposta = client.post(_url_tela(cen), dados)
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    assert "Adicionar linha" not in conteudo.split("</table>")[-1] or (
        "máximo de 20 partidas" in conteudo
    )
    assert "máximo de 20 partidas" in conteudo


# ---------------------------------------------------------------------------
# BL-92 (achado 6): indentação por classe CSS, nunca `style` inline com vírgula
# ---------------------------------------------------------------------------


def test_indentacao_do_plano_de_contas_e_do_balancete_nunca_usa_style_inline(client, cen):
    """Achado 6 / BL-92: `(nivel - 1) * 1.25` era `float`, e com
    `LANGUAGE_CODE = "pt-br"` o template localizava para `padding-left:
    1,25rem` — CSS inválido. Agora a indentação é por classe (`nivel-N`),
    sem NENHUM atributo `style="padding-left...` em nenhuma das duas
    telas.
    """
    _login(client, cen)
    ativo = Conta.objects.create(
        empresa=cen["empresa"],
        codigo="9",
        nome="Grupo de teste",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        aceita_lancamento=False,
    )
    Conta.objects.create(
        empresa=cen["empresa"],
        codigo="9.1",
        nome="Subconta de teste",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
        conta_pai=ativo,
    )

    url_plano = reverse("contabilidade_web:plano_de_contas", args=[cen["empresa"].id])
    resposta_plano = client.get(url_plano)
    conteudo_plano = resposta_plano.content.decode()
    assert "padding-left" not in conteudo_plano
    assert "nivel-1" in conteudo_plano and "nivel-2" in conteudo_plano

    hoje = timezone.localdate()
    url_balancete = (
        reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
        + f"?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    resposta_balancete = client.get(url_balancete)
    conteudo_balancete = resposta_balancete.content.decode()
    assert "padding-left" not in conteudo_balancete
    assert re.search(r'class="nivel-\d+"', conteudo_balancete)


# ---------------------------------------------------------------------------
# BL-96 (achado 10): colunas consolidadas do balancete marcadas como não somáveis
# ---------------------------------------------------------------------------


def test_colunas_consolidadas_do_balancete_marcadas_como_nao_somaveis(client, cen):
    _login(client, cen)
    hoje = timezone.localdate()
    url = (
        reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
        + f"?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"
    )
    resposta = client.get(url)
    conteudo = resposta.content.decode()
    rodape = re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)
    assert rodape.count("coluna-nao-somavel") == 2
    assert "não somável" in rodape.lower()
    # O cabeçalho também sinaliza (para leitor de tela) que "Débitos" e
    # "Créditos" são consolidados.
    assert conteudo.count("coluna-nao-somavel") >= 4  # 2 no cabeçalho + 2 no rodapé


# ---------------------------------------------------------------------------
# BL-97 (achado 11): aria-describedby sem id órfão
# ---------------------------------------------------------------------------


def test_aria_describedby_nunca_aponta_para_id_inexistente(client, cen):
    _login(client, cen)
    resposta = client.get(reverse("contabilidade_web:conta_nova", args=[cen["empresa"].id]))
    conteudo = resposta.content.decode()
    ids_referenciados = set()
    for atributo in re.findall(r'aria-describedby="([^"]+)"', conteudo):
        ids_referenciados.update(atributo.split())
    assert ids_referenciados, "esperava pelo menos um aria-describedby (campo com help_text)"
    for id_referenciado in ids_referenciados:
        assert re.search(rf'id="{re.escape(id_referenciado)}"', conteudo), id_referenciado


# ---------------------------------------------------------------------------
# BL-98 (achado 12): rótulo "Conta da linha N"
# ---------------------------------------------------------------------------


def test_rotulo_do_campo_conta_diz_conta_da_linha(client, cen):
    _login(client, cen)
    resposta = client.get(_url_tela(cen))
    conteudo = resposta.content.decode()
    assert re.search(r'for="id_conta_1">\s*Conta da linha 1\s*</label>', conteudo)
    assert re.search(r'for="id_tipo_1">\s*Tipo da linha 1\s*</label>', conteudo)
    assert re.search(r'for="id_valor_1">\s*Valor da linha 1\s*</label>', conteudo)


# ---------------------------------------------------------------------------
# Achado 13: comentários obsoletos (verificação de texto, não de código)
# ---------------------------------------------------------------------------


def test_urls_web_no_comentario_da_secao_do_plano_existe_de_verdade():
    """Achado 13, terceiro item: `urls_web.py` remetia a uma seção "Onde é
    fácil errar" do plano DL-017 que não existia. O arquiteto-senior
    escreveu a seção nesta mesma rodada — este teste confirma que a
    referência agora resolve para conteúdo real, não uma âncora quebrada.
    """
    from pathlib import Path

    plano = Path("docs/planos/DL-017-interface-da-contabilidade.md").read_text(encoding="utf-8")
    assert "## Onde é fácil errar" in plano


# ---------------------------------------------------------------------------
# Duplo clique / idempotência continuam intactos com a nova extração (regressão)
# ---------------------------------------------------------------------------


def test_duplo_clique_continua_nao_criando_dois_lancamentos_apos_a_correcao(client, cen):
    _login(client, cen)
    dados = {
        "acao": "gravar",
        "num_linhas": "2",
        "data": timezone.localdate().isoformat(),
        "historico": "duplo clique",
        "chave_idempotencia": "k-duplo-clique",
        "conta_1": str(cen["caixa"].id),
        "tipo_1": "debito",
        "valor_1": "1.500,00",
        "conta_2": str(cen["receita"].id),
        "tipo_2": "credito",
        "valor_2": "1.500,00",
    }
    r1 = client.post(_url_tela(cen), dados)
    r2 = client.post(_url_tela(cen), dados)
    assert r1.status_code == 302 and r2.status_code == 302
    assert r1.url == r2.url
    assert LancamentoContabil.objects.count() == 1
    assert ItemLancamento.objects.count() == 2


def test_post_sem_csrf_ainda_e_recusado_apos_a_correcao(cen):
    """Regressão: a extração para `_itens_e_totais` não pode ter afetado a
    proteção de CSRF (mecanismo do próprio Django, não desta view)."""
    cliente_estrito = Client(enforce_csrf_checks=True)
    assert cliente_estrito.login(username="gestora", password="senha-forte-123")
    resposta = _post_tela(cliente_estrito, cen, "10,00", chave="sem-csrf")
    assert resposta.status_code == 403
    assert LancamentoContabil.objects.count() == 0
