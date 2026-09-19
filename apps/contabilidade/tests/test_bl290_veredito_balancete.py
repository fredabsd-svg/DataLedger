"""BL-290 (A2 da auditoria DL-026 rodada 2,
docs/auditorias/2026-09-18-dl-024-rodada-2.md): a faixa de fechamento do
balancete comparava TEXTO pt-BR (`total_debitos_ptbr == total_creditos_ptbr`)
em vez de `Decimal` — a mesma classe de defeito do BL-289/A1, agora na tela
do balancete —, e o ramo "Fecha" cobria também o dia 1º de todo mês (sem
movimento nenhum no período), mostrando "Fecha" verde sobre 0,00/0,00
(BL-302/B4).

Escopo desta correção: entrou no meio da rodada 4 por decisão do
arquiteto-senior — o CONTRATO DE CONTEXTO original já descrevia as chaves
`veredito_balancete`/`diferenca_balancete_ptbr` para os dois lados
(view + template), mas a distribuição inicial só endereçou o BL-290 ao
`especialista-frontend`, que está proibido de editar `views_web.py`; a
metade do servidor ficou sem dono. O `especialista-frontend` já escreveu o
template e um teste de tela esperando essas chaves
(`test_dl017_telas.py::test_balancete_veredito_nao_fecha_e_exercitado_com_
totais_divergentes`); este arquivo testa a DECISÃO em si, lendo
`response.context`, sem depender do HTML renderizado pelo outro lado.

Dados 100% sintéticos, criados nos próprios testes.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade import views_web
from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório de teste", cnpj="44444444000144")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-290 Ltda", cnpj="44455566000156"
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
        username="gestora-bl290",
        email="gestora-bl290@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-bl290", password="senha-forte-123")


def _url(cen, *, inicio=None, fim=None):
    base = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    if inicio is None or fim is None:
        return base
    return f"{base}?inicio={inicio.isoformat()}&fim={fim.isoformat()}"


def test_sem_movimento_no_periodo_e_nada_a_conferir(client, cen):
    """BL-302/B4: dia 1º de todo mês, sem nenhum lançamento — a faixa não
    pode dizer "Fecha" sobre 0,00/0,00; tem de dizer que não há o que
    conferir."""
    _login(client, cen)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "nada_a_conferir"
    assert resposta.context["diferenca_balancete_ptbr"] is None


def test_movimento_balanceado_e_fecha(client, cen):
    """Um lançamento efetivado sempre tem débito == crédito
    (`criar_lancamento` garante) — com movimento real no período, a faixa
    tem de dizer "fecha", nunca "nada_a_conferir" nem "nao_fecha"."""
    _login(client, cen)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-290 movimento balanceado",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("500.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("500.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl290-fecha",
    )
    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "fecha"
    assert resposta.context["diferenca_balancete_ptbr"] is None


def test_totais_divergentes_e_nao_fecha_com_diferenca(client, cen, monkeypatch):
    """O ramo "nao_fecha" é, por construção de partidas dobradas, uma rede
    de segurança contra CORRUPÇÃO de dado — não há caminho de escrita real
    que produza débito != crédito no total do período. Forçado aqui via
    `monkeypatch` na função de apuração, no mesmo padrão que
    `test_dl017_telas.py` já usa para o mesmo fim: prova que o ramo existe
    e calcula certo, em vez de ficar sem nunca ter sido exercitado."""
    _login(client, cen)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-290 base para divergência",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl290-base",
    )

    apuracao_real = views_web.apurar_balancete(
        empresa=cen["empresa"], inicio=hoje.replace(day=1), fim=hoje, nivel=None
    )

    def _apuracao_divergente(*, empresa, inicio, fim, nivel=None):
        # Só o TOTAL é corrompido — as linhas continuam vindo da apuração
        # real, para a soma "própria" das linhas bater com o rodapé (o que
        # já é coberto por outro teste); aqui o que importa é só a faixa.
        divergente = dict(apuracao_real)
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.01")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_divergente)

    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "nao_fecha"
    assert resposta.context["diferenca_balancete_ptbr"] == "0,01"


def test_veredito_e_decidido_em_decimal_nao_por_texto(client, cen, monkeypatch):
    """Controle de regressão direto contra a causa do A2: uma divergência
    ABAIXO do centavo (que `_valor_ptbr` arredondaria para o MESMO texto
    dos dois lados) precisa continuar sendo pega, porque a comparação é em
    `Decimal` sobre os totais de ORIGEM — nunca entre os dois textos já
    formatados."""
    _login(client, cen)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-290 base para divergência de sub-centavo",
        itens=[
            {"conta": cen["caixa"], "tipo": "debito", "valor": Decimal("300.00")},
            {"conta": cen["receita"], "tipo": "credito", "valor": Decimal("300.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl290-subcentavo-base",
    )
    apuracao_real = views_web.apurar_balancete(
        empresa=cen["empresa"], inicio=hoje.replace(day=1), fim=hoje, nivel=None
    )

    def _apuracao_quase_igual(*, empresa, inicio, fim, nivel=None):
        divergente = dict(apuracao_real)
        # `_valor_ptbr` faz `.quantize(Decimal("0.01"))` — 300,004 e 300,00
        # formatam para o MESMO texto ("300,00"); só a comparação em
        # Decimal enxerga a diferença.
        divergente["total_creditos"] = apuracao_real["total_creditos"] + Decimal("0.004")
        return divergente

    monkeypatch.setattr(views_web, "apurar_balancete", _apuracao_quase_igual)

    resposta = client.get(_url(cen, inicio=hoje.replace(day=1), fim=hoje))
    assert resposta.status_code == 200
    assert resposta.context["veredito_balancete"] == "nao_fecha"
    assert resposta.context["total_debitos_ptbr"] == resposta.context["total_creditos_ptbr"], (
        "controle: os dois TEXTOS precisam ser iguais para este caso valer algo "
        "— é exatamente a comparação de string que o A2 reprovou"
    )
