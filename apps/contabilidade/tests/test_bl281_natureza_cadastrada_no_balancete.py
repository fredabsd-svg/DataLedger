"""BL-281 (M5 da auditoria DL-026, rodada 1,
docs/projeto/backlog.md): os parênteses de saldo invertido (DE-053/RC-90)
só existiam no Razão, porque só o Razão tinha a conta CADASTRADA no
contexto de cada linha (`conta` vem da própria URL). O Balancete tinha
apenas o sinal COMPUTADO (`saldo_final_natureza`) — uma conta `1 ATIVO`
(devedora) com saldo `13.366,61 C` saía sem marcação nenhuma, exatamente
onde o contador procura anomalia.

Prova de onde vem a natureza cadastrada (pedida pelo arquiteto-senior):
`apps/contabilidade/services.py`, função `apurar_balancete`, linha ~1100
(`"natureza": conta.natureza`) — o comentário imediatamente acima (linhas
~1088-1099) já documentava que este campo é "Natureza CADASTRADA da conta
(`Conta.natureza`) — exposta aqui só para permitir à VIEW converter
saldo_anterior/saldo_final [...] em valor absoluto + natureza APURADA". A
view (`apps/contabilidade/views_web.py::balancete`) já CONSUMIA esse valor
para calcular a natureza apurada via `_saldo_absoluto_com_natureza`; só não
REPASSAVA para o contexto de cada linha. É essa lacuna que esta correção
fecha.

Escopo desta etapa (servidor apenas — ver o pedido da tarefa): a view passa
a expor `linha["conta"]["natureza"]` no contexto de cada linha, no formato
que `templates/contabilidade/_saldo.html` já sabe ler (`conta.natureza`
resolve `conta["natureza"]` em Django Template Language — lookup de
dicionário tentado ANTES de atributo, `Variable._resolve_lookup`). O
`especialista-frontend` NÃO pode editar `templates/contabilidade/
balancete.html` nesta rodada (fora do escopo desta tarefa) — os testes
abaixo verificam o CONTEXTO da resposta (`response.context["linhas"]`),
que já passa hoje. Fica escrito aqui, para a próxima onda, quais asserções
de HTML precisam ser ACRESCENTADAS quando `balancete.html` passar a incluir
`_saldo.html` nas colunas de saldo:

    - conta devedora + saldo credor -> a célula de saldo contém
      `<span class="valor-invertido">(` e o valor entre parênteses.
    - conta devedora + saldo devedor -> a célula NÃO contém
      `valor-invertido`.
    - o mesmo par, espelhado, para conta credora.
    - saldo zero -> célula sem `indicador-natureza` nem `valor-invertido`
      (RC-61: zero não tem lado).

Dados 100% sintéticos, criados nos próprios testes.
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cen():
    escritorio = Escritorio.objects.create(nome="Escritório BL-281", cnpj="55555555000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-281 Ltda", cnpj="55566677000188"
    )
    ativo = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    passivo = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=NaturezaConta.CREDORA,
    )
    # Contrapartida usada só para fechar as partidas dobradas dos
    # lançamentos abaixo — não é asserida em nenhum teste.
    contrapartida = Conta.objects.create(
        empresa=empresa,
        codigo="3",
        nome="Diversos",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    # Conta SEM nenhum lançamento no período: saldo zero, para o caso (d).
    conta_zero = Conta.objects.create(
        empresa=empresa,
        codigo="4",
        nome="Sem movimento",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestora-bl281",
        email="gestora-bl281@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "ativo": ativo,
        "passivo": passivo,
        "contrapartida": contrapartida,
        "conta_zero": conta_zero,
    }


def _login(client):
    assert client.login(username="gestora-bl281", password="senha-forte-123")


def _url(cen):
    hoje = timezone.localdate()
    base = reverse("contabilidade_web:balancete", args=[cen["empresa"].id])
    return f"{base}?inicio={hoje.replace(day=1).isoformat()}&fim={hoje.isoformat()}"


def _linha(resposta, codigo):
    for linha in resposta.context["linhas"]:
        if linha["codigo"] == codigo:
            return linha
    raise AssertionError(f"conta {codigo!r} não apareceu em response.context['linhas']")


def test_conta_devedora_com_saldo_credor_sai_marcada_como_invertida(client, cen):
    """(a): crédito lançado numa conta ATIVO (devedora) sem débito
    correspondente inverte o saldo apurado para credor — a marcação de
    parênteses (RC-90) precisa ser possível: `conta.natureza` cadastrada
    ("devedora") diverge da letra apurada ("C")."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo invertido em conta devedora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": cen["ativo"], "tipo": "credito", "valor": Decimal("100.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-a",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "1")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"]["letra"] == "C"


def test_conta_devedora_com_saldo_devedor_sai_sem_marcacao(client, cen):
    """(b): débito líquido numa conta devedora é o lado NORMAL — a letra
    apurada bate com a cadastrada, então `_saldo.html` não deve marcar
    parênteses quando a próxima onda incluir a parcial aqui."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo normal em conta devedora",
        itens=[
            {"conta": cen["ativo"], "tipo": "debito", "valor": Decimal("200.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("200.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-b",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "1")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"]["letra"] == "D"


def test_conta_credora_com_saldo_devedor_sai_marcada_como_invertida(client, cen):
    """(c): espelho de (a) — débito lançado numa conta PASSIVO (credora)
    sem crédito correspondente inverte o saldo apurado para devedor."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo invertido em conta credora",
        itens=[
            {"conta": cen["passivo"], "tipo": "debito", "valor": Decimal("150.00")},
            {"conta": cen["contrapartida"], "tipo": "credito", "valor": Decimal("150.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-c",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "2")
    assert linha["conta"]["natureza"] == "credora"
    assert linha["saldo_final_natureza"]["letra"] == "D"


def test_conta_credora_com_saldo_credor_sai_sem_marcacao(client, cen):
    """(c espelhado/normal): crédito líquido numa conta credora é o lado
    NORMAL — sem marcação."""
    _login(client)
    hoje = timezone.localdate()
    criar_lancamento(
        empresa=cen["empresa"],
        data=hoje,
        historico="BL-281 saldo normal em conta credora",
        itens=[
            {"conta": cen["contrapartida"], "tipo": "debito", "valor": Decimal("250.00")},
            {"conta": cen["passivo"], "tipo": "credito", "valor": Decimal("250.00")},
        ],
        criado_por=None,
        chave_idempotencia="k-bl281-d",
    )
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "2")
    assert linha["conta"]["natureza"] == "credora"
    assert linha["saldo_final_natureza"]["letra"] == "C"


def test_saldo_zero_nao_recebe_natureza_apurada(client, cen):
    """(d): sem nenhum lançamento no período, o saldo é zero — RC-61 diz
    que zero não tem lado. `saldo_final_natureza` precisa ser `None`
    (mesma regra que já protege o Razão), o que faz `_saldo.html` nunca
    alcançar a comparação com `conta.natureza` nesse caso — a marcação de
    invertido não depende de `conta` ter valor válido quando o saldo é
    zero. `conta.natureza` continua exposta (é a cadastrada da conta), só
    não é ela quem decide aqui."""
    _login(client)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    linha = _linha(resposta, "4")
    assert linha["conta"]["natureza"] == "devedora"
    assert linha["saldo_final_natureza"] is None


def test_natureza_cadastrada_do_contexto_bate_com_a_conta_no_banco(client, cen):
    """Controle direto contra a causa do BL-281: o valor exposto em
    `linha["conta"]["natureza"]` é a mesma string gravada em
    `Conta.natureza` — não um valor recalculado ou copiado do saldo
    apurado (que poderia coincidir por acaso em alguns casos e mascarar
    uma regressão)."""
    _login(client)
    resposta = client.get(_url(cen))
    assert resposta.status_code == 200
    for codigo, conta in (("1", cen["ativo"]), ("2", cen["passivo"])):
        linha = _linha(resposta, codigo)
        assert linha["conta"]["natureza"] == conta.natureza
