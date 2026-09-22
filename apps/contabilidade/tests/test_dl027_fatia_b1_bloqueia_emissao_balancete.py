"""DL-027 Fatia B — bloqueia emissão do Balancete quando débito ≠ crédito.

Plano DL-027 §Fatia B, item 3: "Bloquear a emissão quando débito ≠ crédito
— o produto já calcula 'Fecha / Não fecha'; falta transformar em trava."

Esta é a primeira entrega da Fatia B: a PORTA do servidor recusa renderizar
o Balancete quando os totais do período divergem. A faixa "Não fecha" deixa
de ser um aviso para virar veto. O critério 9 do plano diz que a mensagem
tem que "dizer o que fazer, não só que falhou" — o teste prova que o veto
carrega a diferença em pt-BR e uma orientação textual, não só um 409 seco.

Arquitetura:
- `avaliar_emissao_do_balancete(apuracao)` em `apps.contabilidade.services`
  decide se o documento PODE ser emitido e devolve um veredito estruturado
  (`pode_emitir`, `veredito`, `diferenca_ptbr`).
- A view chama o avaliador e, quando `pode_emitir` é `False`, devolve 409
  com a orientação na mensagem — mesmo padrão que `HierarquiaInconsistente`
  no Balancete e no Balanço (precedente medido).

Razão para levantar como função nova em vez de in-linear na view: a regra
"bloquear quando diverge" é compartilhada por Diário/Razão/Balanço na
mesma etapa (RC-19 e o catálogo do plano). AGENTS.md §8 proíbe
duplicação entre tela, API, tarefa e IA — a decisão mora no services, a
view pergunta e obedece (mesmo contrato de `avaliar_emissao_do_balanco`,
DL-034).
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import (
    avaliar_emissao_do_balancete,
    criar_lancamento,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório DL-027 B", cnpj="55555555000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-027 B Ltda", cnpj="55566677000188"
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
        username="gestor-dl027b",
        email="gestor-dl027b@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestor-dl027b", password="senha-forte-123")


def _url(cen, *, inicio=None, fim=None):
    base = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    if inicio is None or fim is None:
        return base
    return f"{base}?inicio={inicio.isoformat()}&fim={fim.isoformat()}"


# ---------------------------------------------------------------------------
# 1) `avaliar_emissao_do_balancete` (services): três ramos do veredito, e o
# único veto é `nao_fecha`. Função pura — não toca em banco, não lê
# request — recebe a apuração pronta e devolve um dict estruturado.
# ---------------------------------------------------------------------------


def test_avaliador_quando_totais_batem_diz_pode_emitir_com_veredito_fecha(cen):
    """BL-027 B.1: a base do veredito. Totais batem e há movimento →
    pode emitir com 'fecha'. O default 'nada_a_conferir' (sem movimento)
    TAMBÉM pode emitir — o veto é só na divergência."""
    apuracao = {
        "contas": [],
        "total_debitos": Decimal("300.00"),
        "total_creditos": Decimal("300.00"),
    }
    resultado = avaliar_emissao_do_balancete(apuracao)
    assert resultado["pode_emitir"] is True
    assert resultado["veredito"] == "fecha"
    assert resultado["diferenca_ptbr"] is None


def test_avaliador_quando_totais_zero_diz_pode_emitir_com_nada_a_conferir(cen):
    """Sem movimento no período (0,00/0,00) também pode emitir: o
    critério do plano proíbe o veto silencioso (o BL-302/B4 da DL-026
    corrigiu exatamente isso)."""
    apuracao = {
        "contas": [],
        "total_debitos": Decimal("0"),
        "total_creditos": Decimal("0"),
    }
    resultado = avaliar_emissao_do_balancete(apuracao)
    assert resultado["pode_emitir"] is True
    assert resultado["veredito"] == "nada_a_conferir"
    assert resultado["diferenca_ptbr"] is None


def test_avaliador_quando_totais_divergem_diz_nao_pode_emitir_com_diferenca(cen):
    """O veto. Total débitos 300,00 e créditos 300,01 — diferença de
    0,01 —, `pode_emitir` False e a diferença em pt-BR para a tela
    mostrar onde está o desvio."""
    apuracao = {
        "contas": [],
        "total_debitos": Decimal("300.00"),
        "total_creditos": Decimal("300.01"),
    }
    resultado = avaliar_emissao_do_balancete(apuracao)
    assert resultado["pode_emitir"] is False
    assert resultado["veredito"] == "nao_fecha"
    assert resultado["diferenca_ptbr"] == "0,01"


# ---------------------------------------------------------------------------
# 2) View: o veto vira HTTP 409 + mensagem orientativa — o que o critério
# 9 do plano exige.
# ---------------------------------------------------------------------------


def test_view_balancete_quando_totais_divergem_retorna_409_e_nao_renderiza(
    client, cen, monkeypatch
):
    """O caminho de divergência que NUNCA acontece em uso normal do
    produto (criar_lancamento garante débitos == créditos por construção
    de partidas dobradas), mas que pode acontecer por corrupção de
    dado. Aqui o veto se prova: HTTP 409, não 200, e o contexto carrega
    a estrutura que a tela usa para orientar — veredito, diferença em
    pt-BR, e a flag `emissao_recusada` que o template vai usar para
    mostrar a faixa de erro."""
    _login(client, cen)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="DL-027 B.1 base para divergência",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-dl027b1-base",
    )
    apuracao_real = views_web.apurar_balancete(
        empresa=cen["empresa"], inicio=hoje.replace(day=1), fim=hoje, nivel=None
    )

    def _apuracao_divergente(*, empresa, inicio, fim, nivel=None):
        divergente = dict(apuracao_real)
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.01")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_divergente)

    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))

    assert resposta.status_code == 409, (
        "Divergência de totais deve recusar a emissão com 409; um 200 "
        "faria a tela abrir mostrando 'Não fecha' como se fosse uma "
        "situação normal, e o contador entrega o documento ao cliente sem "
        "ver que o sistema detectou o desvio."
    )
    # Estrutura completa do contexto que a view passa para o template
    # — é o que a tela vai ler para orientar, e que esta separado do
    # código de status (mensagens vão no `messages.error()`).
    assert resposta.context["veredito_balancete"] == "nao_fecha"
    assert resposta.context["diferenca_balancete_ptbr"] == "0,01"
    assert resposta.context["emissao_recusada"] is True
    # Os totais em pt-BR continuam no contexto — a tela precisa exibi-los
    # lado a lado para o contador VER onde está a diferença (o BL-310
    # prova que o texto pt-BR divergente É a única coisa que torna a
    # troca débito/crédito pela faixa DETECTÁVEL). Aqui a divergência
    # foi de 0,01 em cima de 300,00 — o crédito fica em "300,01".
    assert resposta.context["total_debitos_ptbr"] == "300,00"
    assert resposta.context["total_creditos_ptbr"] == "300,01"


def test_view_balancete_quando_totais_batem_segue_200_com_veredito_fecha(client, cen, monkeypatch):
    """Controle positivo: o veto NÃO bloqueia o caso normal. Totais
    batem, com movimento no período, e o Balancete abre em 200 com o
    veredito 'fecha'. Regressão direta — se o gate for ingênuo e
    sempre vetar, este teste cai."""
    _login(client, cen)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="DL-027 B.1 base que fecha",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-dl027b1-fecha",
    )
    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "fecha"


def test_view_balancete_sem_movimento_segue_200_com_nada_a_conferir(client, cen):
    """O segundo controle positivo: sem movimento no período, a tela
    também abre em 200 — o veto é só sobre a divergência. O BL-302/B4
    da DL-026 já validou que 'nada a conferir' é o estado certo
    quando não há o que fechar."""
    _login(client, cen)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "nada_a_conferir"
