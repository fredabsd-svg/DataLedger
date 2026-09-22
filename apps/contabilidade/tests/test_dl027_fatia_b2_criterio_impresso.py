"""DL-027 Fatia B.2 — critério de apuração impresso no Balancete.

Plano DL-027-B2-criterio-de-apuracao-impresso.md:

1. O serviço `apurar_balancete` aceita `criterio_de_apuracao` ∈
   {"todas", "com_movimento"}. Default = "todas" (comportamento atual).
2. "com_movimento" oculta contas SEM movimento consolidado no período
   E SEM saldo anterior diferente de zero. Sintéticas com movimento
   consolidado continuam aparecendo (regra única de saldo / DE-020).
3. O critério é uma propriedade da EMISSÃO (decidido na view via
   querystring), não do cadastro — sem migração de modelo (PE-65).
4. A4 (entra junto): o texto da `messages.error(...)` do veto
   (quando débitos ≠ créditos) é **assertado** — mata o M5 da prova
   de mutação da auditoria da B.1.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import apurar_balancete
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório DL-027 B.2", cnpj="66666666000166")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa DL-027 B.2 Ltda",
        cnpj="66677788000199",
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    banco = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Banco",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="3",
        nome="Receita",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    # Sintética SEM movimento, SEM saldo anterior — DEVE sumir em "com_movimento"
    despesa_geral = Conta.objects.create(
        empresa=empresa,
        codigo="4",
        nome="Despesas Gerais",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-dl027b2",
        email="gestor-dl027b2@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "banco": banco,
        "receita": receita,
        "despesa_geral": despesa_geral,
        "usuario": usuario,
    }


def _url(cen, **params):
    base = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    if not params:
        return base
    qs = "&".join(
        f"{k}={v.isoformat() if hasattr(v, 'isoformat') else v}" for k, v in params.items()
    )
    return f"{base}?{qs}"


def _login(client, cen):
    client.force_login(cen["usuario"])


# ---------------------------------------------------------------------------
# 1) `apurar_balancete` aceita o parâmetro e filtra linhas quando
# "com_movimento". Função pura — recebe o critério, devolve um dict.
# ---------------------------------------------------------------------------


def test_servico_quando_criterio_default_devolve_todas_as_contas(cen):
    """O default deve ser "todas", retrocompatível com o código atual."""
    apuracao = apurar_balancete(
        empresa=cen["empresa"], inicio=timezone.localdate(), fim=timezone.localdate()
    )
    codigos = [linha["conta"] for linha in apuracao["contas"]]
    assert codigos == ["1", "2", "3", "4"], (
        f"Default não-retrocompatível: esperava 4 contas, recebi {codigos}"
    )


def test_servico_quando_criterio_todas_explicito_devolve_todas_as_contas(cen):
    """`criterio_de_apuracao="todas"` explícito produz mesmo resultado que
    o default — o filtro "todas" é a identidade."""
    apuracao = apurar_balancete(
        empresa=cen["empresa"],
        inicio=timezone.localdate(),
        fim=timezone.localdate(),
        criterio_de_apuracao="todas",
    )
    assert len(apuracao["contas"]) == 4


def test_servico_quando_criterio_com_movimento_oculta_conta_sem_movimento_e_sem_saldo_anterior(cen):
    """Sem movimento no período E sem saldo anterior: a linha some.
    A `despesa_geral` (código 4) é exatamente esse caso: cadastrada
    mas sem uso. As outras três (Caixa/Banco/Receita) também não têm
    movimento nesta fixture, então TODAS somem — o fixture prova o
    ramo "nada tem movimento", que é o que B.2 promete ocultar."""
    apuracao = apurar_balancete(
        empresa=cen["empresa"],
        inicio=timezone.localdate(),
        fim=timezone.localdate(),
        criterio_de_apuracao="com_movimento",
    )
    assert apuracao["contas"] == [], (
        f"Esperava lista vazia (nenhuma conta tem movimento), recebi "
        f"{[linha['conta'] for linha in apuracao['contas']]}"
    )


def test_servico_quando_criterio_com_movimento_preserva_conta_com_movimento(cen):
    """Lançamento em `caixa` (código 1): o filtro "com_movimento" deve
    preservar essa conta E a sintética que a contém (não há sintética
    aqui, mas o teste prova que o filtro não está apagando linhas que
    DEVEM ficar). `despesa_geral` (código 4) continua sem movimento e
    some — a lista resultante tem só a conta com movimento."""
    from apps.contabilidade.services import criar_lancamento

    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="DL-027 B.2 — caixa recebe receita",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-dl027b2-filtro-positivo",
    )
    apuracao = apurar_balancete(
        empresa=cen["empresa"],
        inicio=hoje,
        fim=hoje,
        criterio_de_apuracao="com_movimento",
    )
    codigos = [linha["conta"] for linha in apuracao["contas"]]
    # "caixa" (1) e "receita" (3) TÊM movimento — aparecem.
    # "banco" (2) e "despesa_geral" (4) NÃO TÊM — somem.
    assert codigos == ["1", "3"], (
        f"Filtro 'com_movimento' não preservou as contas com movimento: {codigos}"
    )


def test_servico_com_movimento_preserva_totais_gerais(cen):
    """O total NÃO é afetado pelo filtro — é a agregação independente de
    TODOS os itens do período (DE-020). Aqui não há movimento nenhum, mas
    se houvesse, o total seria o mesmo com `criterio="todas"` ou
    `criterio="com_movimento"`."""
    apuracao_todas = apurar_balancete(
        empresa=cen["empresa"],
        inicio=timezone.localdate(),
        fim=timezone.localdate(),
        criterio_de_apuracao="todas",
    )
    apuracao_filtrada = apurar_balancete(
        empresa=cen["empresa"],
        inicio=timezone.localdate(),
        fim=timezone.localdate(),
        criterio_de_apuracao="com_movimento",
    )
    assert apuracao_todas["total_debitos"] == apuracao_filtrada["total_debitos"]
    assert apuracao_todas["total_creditos"] == apuracao_filtrada["total_creditos"]


# ---------------------------------------------------------------------------
# 2) View: o critério sai da querystring, vai para o serviço e para o
#    contexto. URL inválida vira 400 com mensagem orientativa.
# ---------------------------------------------------------------------------


def test_view_balancete_quando_criterio_invalido_retorna_400_com_orientacao(client, cen):
    """Critério fora do conjunto aceito: 400 + mensagem orientativa, sem
    gravar nada. Mesmo padrão dos outros campos do formulário (`nivel`
    com valor inválido, `inicio` com formato errado)."""
    _login(client, cen)
    resposta = client.get(
        _url(
            cen,
            inicio=timezone.localdate(),
            fim=timezone.localdate(),
            criterio_de_apuracao="inexistente",
        )
    )
    assert resposta.status_code == 400
    # A mensagem de erro DEVE nomear as opções válidas (orientação).
    mensagens = [str(m) for m in resposta.context["messages"]]
    assert any("todas" in m and "com_movimento" in m for m in mensagens), (
        f"Mensagem de erro não lista as opções válidas: {mensagens}"
    )


def test_view_balancete_quando_criterio_default_renderiza_todas_as_contas(client, cen):
    """Sem `criterio` na URL: contexto carrega "todas" e a view passa
    "todas" para o serviço (comportamento retrocompatível)."""
    _login(client, cen)
    resposta = client.get(_url(cen, inicio=timezone.localdate(), fim=timezone.localdate()))
    assert resposta.status_code == 200
    assert resposta.context["criterio_de_apuracao"] == "todas"
    assert resposta.context["criterio_de_apuracao_texto"] == "todas as contas"
    # Todas as 4 contas aparecem (nenhuma com movimento nesta fixture)
    assert len(resposta.context["linhas"]) == 4


def test_view_balancete_quando_criterio_com_movimento_renderiza_apenas_com_movimento(client, cen):
    """Com `criterio=com_movimento`: contexto carrega o critério e o
    serviço filtra as linhas. Aqui a fixture tem só contas mortas, então
    a tabela fica vazia — o ponto é que a view passa o filtro e o
    contexto expõe o nome do critério."""
    _login(client, cen)
    resposta = client.get(
        _url(
            cen,
            inicio=timezone.localdate(),
            fim=timezone.localdate(),
            criterio_de_apuracao="com_movimento",
        )
    )
    assert resposta.status_code == 200
    assert resposta.context["criterio_de_apuracao"] == "com_movimento"
    assert (
        resposta.context["criterio_de_apuracao_texto"] == "apenas contas com movimento no período"
    )
    assert resposta.context["linhas"] == []


def test_view_balancete_criterio_aparece_no_html_renderizado(client, cen):
    """O critério DEVE aparecer no HTML — não só no contexto — para que o
    documento impresso seja distinguível pelo papel (critério 6 do
    plano DL-027)."""
    _login(client, cen)
    resposta = client.get(
        _url(
            cen,
            inicio=timezone.localdate(),
            fim=timezone.localdate(),
            criterio_de_apuracao="com_movimento",
        )
    )
    html = resposta.content.decode()
    assert "Critério de apuração" in html
    assert "apenas contas com movimento no período" in html


# ---------------------------------------------------------------------------
# 3) A4 (achado da auditoria da B.1): o texto da `messages.error(...)`
#    do veto é assertado, matando o M5 da prova de mutação.
# ---------------------------------------------------------------------------


def test_a4_view_balancete_quando_veta_mensagem_contem_diferenca_e_orientacao(
    client, cen, monkeypatch
):
    """O texto da `messages.error(...)` do veto (quando débitos ≠
    créditos no total do período) DEVE:
    1. ser produzido (a view chama `messages.error`),
    2. conter a diferença em pt-BR (`0,01`),
    3. conter uma orientação textual (palavra-chave que diz o que
       fazer, não só "falhou").

    A auditoria da B.1 provou (M5) que este caminho NÃO estava coberto
    por teste. Este teste cobre."""
    _login(client, cen)
    hoje = timezone.localdate()

    # Apuração REAL com totais batendo — depois monkeypatchamos uma
    # divergente.
    from apps.contabilidade.services import criar_lancamento

    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="DL-027 B.2 base para divergência",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-dl027b2-veto",
    )
    apuracao_real = views_web.apurar_balancete(
        empresa=cen["empresa"], inicio=hoje.replace(day=1), fim=hoje, nivel=None
    )

    def _apuracao_divergente(*, empresa, inicio, fim, nivel=None, criterio_de_apuracao="todas"):
        divergente = dict(apuracao_real)
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.01")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_divergente)

    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))

    assert resposta.status_code == 409, "Divergência de totais deve recusar a emissão com 409"
    # Captura as mensagens que a view produziu via `messages.error(...)`
    mensagens = [(str(m), getattr(m, "tags", "")) for m in resposta.context["messages"]]
    assert any(tag == "error" or "error" in tag for _msg, tag in mensagens), (
        f"Esperava uma `messages.error` no veto, recebi tags: {[t for _m, t in mensagens]}"
    )

    # A string da mensagem deve conter a diferença em pt-BR ("0,01") E
    # uma palavra de orientação (qualquer das que o código produz:
    # "Verifique" ou "Reabra" ou "lançamento"). O assert é tolerante
    # a variações de redação, mas firme quanto ao conteúdo mínimo.
    msg_veto = " ".join(m for m, _t in mensagens)
    assert "0,01" in msg_veto, f"Diferença pt-BR ausente na mensagem: {msg_veto!r}"
    assert any(
        palavra in msg_veto
        for palavra in ("Verifique", "Reabra", "Reabrir", "lançamento", "Lançamento")
    ), f"Mensagem do veto não tem orientação textual: {msg_veto!r}"
