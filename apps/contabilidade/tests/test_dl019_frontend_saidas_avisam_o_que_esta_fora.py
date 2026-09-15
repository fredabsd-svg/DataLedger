"""BL-151 (b) e BL-156 — o que as TELAS mostram sobre o que está fora do
período, e o que elas dizem quando não há movimento nenhum.

## Por que este arquivo existe

É o item que fez a DL-019 existir: um lançamento datado `9999-12-31` **não
aparece em nenhuma tela de operação normal**, e o balancete do período
**concilia** — então nenhuma conferência acusa. O aviso é a rede.

O inventário de 2026-09-15 mediu que o parcial
`_aviso_movimento_fora_do_periodo.html` está incluído por `diario.html:48`,
`razao.html:49` e `balancete.html:51`, e que a Conferência tem categoria
própria — mas que **só o Razão ganhou teste de tela** (e no arquivo do
BL-165). Diário, Balancete e Conferência eram código sem teste. A mensagem
do Balancete sem movimento (BL-156) também era código sem teste: nenhum
teste referenciava `sem_movimento_no_periodo` nem o texto.

## O desenho destes testes, e a parte que não é detalhe

O lançamento fora da faixa é criado **por acesso direto ao ORM**, nunca pelo
serviço. `criar_lancamento` agora recusa a data fora da faixa (RC-77,
implementado e testado), então um teste que dependesse da porta normal
deixaria de poder existir justamente quando o sistema ficou correto. **O que
o aviso protege é o que JÁ ESTÁ GRAVADO** — dado que entrou antes da faixa
existir, ou por uma porta que não passa pela tela.

Cada afirmação tem o seu controle negativo: as telas **não** avisam quando
não há nada fora do período, e o Balancete **não** diz "sem movimento"
quando há movimento. Sem os controles, um aviso preso em "sempre visível"
passaria em tudo — é o item 8 da ordem de risco da BL-169.

Dados 100% sintéticos, criados nos próprios testes.
"""

from datetime import date
from decimal import Decimal
from html import unescape

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import escape, strip_tags

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
PERIODO = {"inicio": "2024-01-01", "fim": "2024-01-31"}
INICIO = date(2024, 1, 1)
FIM = date(2024, 1, 31)
DATA_ABSURDA = date(9999, 12, 31)


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-151", cnpj="66666666000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-151 Ltda", cnpj="66677788000144"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl151", email="gestora-bl151@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "capital": capital}


def _autenticar(client):
    assert client.login(username="gestora-bl151", password=SENHA)


def _lancamento_no_periodo(cenario, valor="100.00"):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2024, 1, 15),
        historico="Dentro do período",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": cenario["capital"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _lancamento_fora_da_faixa_por_orm(cenario, *, data=DATA_ABSURDA, valor="5000.00"):
    """O lançamento do achado R6-4b, gravado por ORM direto — o caminho que
    NÃO passa por `criar_lancamento` e por isso não é barrado pela faixa do
    RC-77. É como o dado chegou à base real (`9` digitado no lugar de `2`,
    ou uma porta que não é a tela), e é justamente esse dado que o aviso
    existe para revelar."""
    lancamento = LancamentoContabil.objects.create(
        empresa=cenario["empresa"], data=data, historico=f"Fora da faixa: {data}"
    )
    for conta, tipo in (
        (cenario["caixa"], TipoPartida.DEBITO),
        (cenario["capital"], TipoPartida.CREDITO),
    ):
        ItemLancamento.objects.create(
            lancamento=lancamento, conta=conta, tipo=tipo, valor=Decimal(valor)
        )
    return lancamento


def _url(cenario, rota):
    return reverse(f"contabilidade_web:{rota}", args=[cenario["empresa"].id])


def _texto(resposta):
    """O HTML entregue com os espaços em branco colapsados.

    O template quebra frases em várias linhas por legibilidade; procurar a
    frase no HTML bruto encontraria "não" onde o texto renderizado diz
    exatamente o que se quer — um teste que falha por indentação e não por
    comportamento é um teste que alguém vai enfraquecer.
    """
    return " ".join(resposta.content.decode().split())


def _texto_visivel(resposta):
    """O texto que o contador LÊ: sem marcação e com os espaços colapsados.

    Necessário porque as frases deste aviso trazem `<strong>` no meio
    ("com data **posterior** a 31/01/2024"), e afirmar a frase contra o HTML
    amarraria o teste à marcação — mudar a ênfase de lugar quebraria um
    teste de comportamento sem que o comportamento mudasse.
    """
    return " ".join(unescape(strip_tags(resposta.content.decode())).split())


# ---------------------------------------------------------------------------
# BL-151 (b) — o aviso nas saídas de período que NÃO tinham teste de tela:
# Diário e Balancete (o Razão tem o seu em test_dl019_razao_reaproveita_
# ids_contas.py)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rota", ["diario", "balancete"])
def test_a_saida_avisa_que_ha_movimento_fora_do_periodo(client, cenario, rota):
    """O aviso aparece, diz a QUANTIDADE e a DATA EXTREMA, não depende de
    cor (começa pela palavra "Atenção" em texto), interrompe a leitura
    (`role="alert"`) e traz o caminho de correção — um link que AMPLIA o
    período, nunca substitui.

    A data extrema é o que revela um ano digitado errado à primeira vista;
    sem ela o aviso diria apenas "existe algo", que é quase nada.
    """
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_da_faixa_por_orm(cenario)

    resposta = client.get(_url(cenario, rota), PERIODO)

    assert resposta.status_code == 200
    aviso = resposta.context["movimento_fora_do_periodo"]
    assert aviso is not None, rota
    assert aviso["posteriores"] == {"quantidade": 1, "data_extrema": DATA_ABSURDA}
    assert aviso["anteriores"] is None
    # Recorte da EMPRESA nestas duas saídas (nenhuma delas é por conta), e
    # por isso o texto fala da empresa.
    assert aviso["conta"] is None
    html = _texto(resposta)
    assert 'role="alert"' in html
    assert "Atenção" in html
    assert "esta empresa tem movimento" in html
    assert "fora do período consultado" in html
    assert "31/12/9999" in html  # data extrema em dd/mm/aaaa (critério 7)
    assert "1 lançamento com data posterior a 31/01/2024" in _texto_visivel(resposta)
    # O caminho de correção AMPLIA o período: continua começando em
    # 01/01/2024 e vai até a data extrema.
    assert aviso["inicio_ampliado"] == INICIO
    assert aviso["fim_ampliado"] == DATA_ABSURDA
    assert "inicio=2024-01-01" in aviso["url_ampliada"]
    assert "fim=9999-12-31" in aviso["url_ampliada"]
    # O link chega ao HTML com o `&` escapado — é o mesmo endereço.
    assert f'href="{escape(aviso["url_ampliada"])}"' in html


@pytest.mark.parametrize("rota", ["diario", "balancete"])
def test_a_saida_NAO_avisa_quando_nao_ha_nada_fora_do_periodo(client, cenario, rota):
    """O controle negativo, e ele não é formalidade: um aviso preso em
    "sempre visível" passaria em todos os testes acima e ensinaria o
    contador a ignorá-lo — é o item 8 da ordem de risco da BL-169."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)

    resposta = client.get(_url(cenario, rota), PERIODO)

    assert resposta.status_code == 200
    assert resposta.context["movimento_fora_do_periodo"] is None, rota
    html = _texto(resposta)
    assert "fora do período consultado" not in html
    assert "aviso-fora-do-periodo" not in html


@pytest.mark.parametrize("rota", ["diario", "balancete"])
def test_o_aviso_nao_esconde_nem_altera_a_tabela_ao_lado(client, cenario, rota):
    """A regra de apresentação que o aviso não pode violar: ele
    ACRESCENTA informação e não corrige número nenhum. Os 100,00 do período
    continuam aparecendo, e o 5.000,00 de fora **não** entra em nenhum
    total desta tela — o que o aviso diz é exatamente isso.
    """
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    _lancamento_fora_da_faixa_por_orm(cenario)

    resposta = client.get(_url(cenario, rota), PERIODO)
    html = _texto(resposta)

    assert resposta.context["movimento_fora_do_periodo"] is not None
    assert "100,00" in html
    # A tabela continua na tela (o aviso vem ANTES dela, nunca em vez dela).
    assert "tabela-dados" in html
    if rota == "balancete":
        assert resposta.context["total_debitos_ptbr"] == "100,00"
        assert resposta.context["total_creditos_ptbr"] == "100,00"
        assert "5.000,00" not in html
    else:
        assert resposta.context["total_debito_ptbr"] == "100,00"


# ---------------------------------------------------------------------------
# BL-151 (b) na Conferência — a única tela de uso normal em que o lançamento
# com data absurda aparece SEM o contador precisar suspeitar primeiro
# ---------------------------------------------------------------------------


def test_conferencia_mostra_na_tela_o_lancamento_com_data_fora_da_faixa(client, cenario):
    """A Conferência não tem período, então o aviso equivalente é outro:
    lançamento com data fora da faixa do RC-77. A tela precisa mostrar a
    DATA, o caminho até o lançamento e o que fazer — correção de lançamento
    efetivado é por estorno, nunca edição silenciosa.
    """
    _autenticar(client)
    _lancamento_no_periodo(cenario)
    fora = _lancamento_fora_da_faixa_por_orm(cenario)

    resposta = client.get(_url(cenario, "conferencia"))

    assert resposta.status_code == 200
    assert list(resposta.context["lancamentos_com_data_fora_da_faixa"]) == [fora]
    # A Conferência deixa de dizer "tudo certo" — se ela dissesse, o
    # contador não teria por que abrir mais nada.
    assert resposta.context["tudo_certo"] is False
    html = _texto(resposta)
    assert "Lançamentos com data fora da faixa aceita" in html
    assert "31/12/9999" in html
    assert (
        reverse("contabilidade_web:lancamento_detalhe", args=[cenario["empresa"].id, fora.id])
        in html
    )
    assert "estorne-o e lance de novo com a data certa" in html
    # A faixa aceita é exibida, para o contador saber o que é "fora".
    assert "01/01/2000" in html


def test_conferencia_em_base_sadia_diz_que_nao_ha_data_fora_da_faixa(client, cenario):
    """Controle negativo da categoria nova: numa base sadia a Conferência
    afirma a ausência — nunca fica muda, e nunca aponta um lançamento
    legítimo."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)

    resposta = client.get(_url(cenario, "conferencia"))

    assert resposta.status_code == 200
    assert list(resposta.context["lancamentos_com_data_fora_da_faixa"]) == []
    assert resposta.context["tudo_certo"] is True
    html = _texto(resposta)
    assert "Nenhum lançamento com data fora da faixa aceita." in html


def test_conferencia_nao_mostra_lancamento_fora_da_faixa_de_OUTRA_empresa(client, cenario):
    """Isolamento entre empresas na categoria nova: o lançamento absurdo
    está na empresa VIZINHA do mesmo escritório e não pode aparecer aqui —
    nem na tela, nem no `tudo_certo`."""
    _autenticar(client)
    vizinha = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Empresa vizinha Ltda",
        cnpj="66677788000225",
    )
    conta_vizinha = Conta.objects.create(
        empresa=vizinha,
        codigo="1",
        nome="Caixa da vizinha",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    lancamento = LancamentoContabil.objects.create(
        empresa=vizinha, data=DATA_ABSURDA, historico="Absurdo da vizinha"
    )
    ItemLancamento.objects.create(
        lancamento=lancamento,
        conta=conta_vizinha,
        tipo=TipoPartida.DEBITO,
        valor=Decimal("1.00"),
    )

    resposta = client.get(_url(cenario, "conferencia"))

    assert list(resposta.context["lancamentos_com_data_fora_da_faixa"]) == []
    assert "Absurdo da vizinha" not in _texto(resposta)


# ---------------------------------------------------------------------------
# BL-156 — o Balancete sem movimento no período explica o que se está vendo,
# e NÃO esconde a tabela
# ---------------------------------------------------------------------------


def test_balancete_sem_movimento_no_periodo_explica_sem_esconder_a_tabela(client, cenario):
    """Critério 13, texto literal: "empresa sem lançamento no período mostra
    MENSAGEM, não tabela vazia sem explicação". O Balancete mostrava linhas
    e zeros, sem uma palavra.

    As duas metades importam, e a segunda é a metade contábil: a mensagem
    aparece **antes** da tabela e a tabela **continua inteira**. Esconder o
    balancete zerado trocaria um defeito de explicação por um de omissão —
    um balancete com saldo anterior e sem movimento no mês é informação
    legítima.
    """
    _autenticar(client)
    # O movimento existe, mas em JANEIRO; o período consultado é FEVEREIRO.
    _lancamento_no_periodo(cenario)

    resposta = client.get(_url(cenario, "balancete"), {"inicio": "2024-02-01", "fim": "2024-02-29"})

    assert resposta.status_code == 200
    assert resposta.context["sem_movimento_no_periodo"] is True
    html = _texto(resposta)
    assert "Nenhum movimento neste período" in html
    # `role="status"`, não `alert`: não é erro nem anomalia — é a resposta
    # correta para um período sem movimento.
    assert 'role="status"' in html
    assert "01/02/2024 a 29/02/2024" in html
    # A tabela continua, com as contas e os saldos anteriores — nada
    # escondido.
    assert "tabela-dados" in html
    assert resposta.context["linhas"], "a tabela do balancete não pode desaparecer"
    assert "Capital Social" in html
    # A mensagem vem ANTES da tabela (é o que faz o contador ler antes de
    # interpretar os zeros).
    assert html.index("Nenhum movimento neste período") < html.index("tabela-dados")
    # E o que ela afirma é verdade: os dois totais do período em zero.
    assert resposta.context["total_debitos_ptbr"] == "0,00"
    assert resposta.context["total_creditos_ptbr"] == "0,00"


def test_balancete_com_movimento_no_periodo_nao_mostra_a_mensagem(client, cenario):
    """Controle negativo: com movimento no período a mensagem não aparece —
    caso contrário ela seria decoração permanente e deixaria de informar."""
    _autenticar(client)
    _lancamento_no_periodo(cenario)

    resposta = client.get(_url(cenario, "balancete"), PERIODO)

    assert resposta.status_code == 200
    assert resposta.context["sem_movimento_no_periodo"] is False
    assert "Nenhum movimento neste período" not in _texto(resposta)


def test_balancete_de_empresa_sem_conta_nenhuma_nao_usa_a_mensagem_de_sem_movimento(
    client, cenario
):
    """A condição é "nenhum movimento no período", não "nenhuma linha": uma
    empresa sem plano de contas é outro estado vazio, com outra explicação
    (a que o próprio template já dá para tabela sem linha). Misturar os dois
    diria "nenhum movimento neste período" para quem ainda não cadastrou
    conta nenhuma.
    """
    _autenticar(client)
    sem_plano = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Empresa sem plano Ltda",
        cnpj="66677788000306",
    )

    resposta = client.get(
        reverse("contabilidade_web:balancete", args=[sem_plano.id]),
        PERIODO,
    )

    assert resposta.status_code == 200
    assert resposta.context["linhas"] == []
    assert resposta.context["sem_movimento_no_periodo"] is False
    assert "Nenhum movimento neste período" not in _texto(resposta)
