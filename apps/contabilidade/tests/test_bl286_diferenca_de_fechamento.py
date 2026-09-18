"""BL-286 (rodada 3 da DL-024): o veredito "Não fecha" precisa dizer DE
QUANTO — critério de aceite do BL-278 que ficou pendente na rodada 1
(achado M2, docs/auditorias/2026-09-18-dl-024-rodada-1.md).

A diferença exibida vem de `Decimal`, calculada em
`apps.contabilidade.views_web._contexto_form_lancamento` sobre os totais de
ORIGEM (nunca sobre o texto pt-BR já formatado) — este arquivo confere que o
NÚMERO exibido bate com o `Decimal` que o teste computa de forma
independente, nos dois caminhos que produzem o veredito ("adicionar_linha",
que só confere, e a tentativa de gravação recusada por não fechar), e que os
três estados (fecha / não fecha com diferença / ainda não conferido)
continuam distinguíveis.

Dados 100% sintéticos, criados nos próprios testes.
"""

import re
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.contabilidade.models import Conta, LancamentoContabil, NaturezaConta, TipoConta
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
        username="gestora-bl286",
        email="gestora-bl286@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-bl286", password="senha-forte-123")


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _post(client, cen, *, acao, valor_debito, valor_credito, chave, historico="Teste BL-286"):
    return client.post(
        _url_tela(cen),
        {
            "acao": acao,
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": historico,
            "chave_idempotencia": chave,
            "conta_1": str(cen["caixa"].id),
            "tipo_1": "debito",
            "valor_1": valor_debito,
            "conta_2": str(cen["receita"].id),
            "tipo_2": "credito",
            "valor_2": valor_credito,
        },
    )


def _linha_total(conteudo):
    return re.search(r'<tr class="linha-total">.*?</tr>', conteudo, re.DOTALL).group(0)


def _ptbr_para_decimal(texto):
    return Decimal(texto.strip().replace(".", "").replace(",", "."))


# BL-286 (rodada 3, decisão do arquiteto-senior): a diferença NÃO vai entre
# parênteses em nenhuma célula de valor — nesta tela, parêntese numa célula
# de valor já tem um significado reservado, "valor invertido em relação à
# natureza do registro" (docs/projeto/direcao-de-arte.md §2A). A diferença
# entra como frase dentro da célula do veredito, com o NÚMERO embrulhado
# num invólucro com a classe do sistema (`valor-monetario`) — nunca a
# célula inteira, que misturaria texto corrido com fonte tabulada.
_PADRAO_VEREDITO_NAO_FECHA = re.compile(
    r'Não fecha, faltam <span class="valor-monetario">([^<]+)</span> no (débito|crédito)'
)


# ---------------------------------------------------------------------------
# Critério 1 e 2: a diferença é sempre positiva em módulo, some quando fecha
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor_debito, valor_credito, diferenca_esperada, lado_esperado",
    [
        # Caso "redondo" do próprio exemplo do BL-286.
        ("1.500,00", "900,00", Decimal("600.00"), "crédito"),
        # O lado que falta pode ser o débito também — a regra não pode
        # assumir uma direção fixa.
        ("900,00", "1.500,00", Decimal("600.00"), "débito"),
        # O caso que mais importa (instrução do BL-286): diferença de UM
        # centavo, o que o contador mais persegue e o que primeiro expõe
        # arredondamento errado.
        ("1.000,01", "1.000,00", Decimal("0.01"), "crédito"),
        ("1.000,00", "1.000,01", Decimal("0.01"), "débito"),
    ],
)
def test_adicionar_linha_mostra_a_diferenca_quando_nao_fecha(
    client, cen, valor_debito, valor_credito, diferenca_esperada, lado_esperado
):
    """`acao=adicionar_linha` só confere (nunca grava) — é o caminho sem
    JavaScript pelo qual o contador vê o rodapé atualizar a cada linha
    (critério 15 da direção de arte). Com débito e crédito diferentes, o
    veredito "Não fecha" precisa vir acompanhado da diferença certa, do
    lado certo, sempre em módulo (critério 1 do BL-286).
    """
    _login(client, cen)
    resposta = _post(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito=valor_debito,
        valor_credito=valor_credito,
        chave=f"k-{valor_debito}-{valor_credito}",
    )
    assert resposta.status_code == 200
    conteudo = resposta.content.decode()
    rodape = _linha_total(conteudo)

    assert "linha-total__veredito--nao-fecha" in rodape
    assert "Não fecha" in rodape

    achado = _PADRAO_VEREDITO_NAO_FECHA.search(rodape)
    assert achado, rodape
    diferenca_exibida, lado_exibido = achado.group(1), achado.group(2)

    # Nunca um sinal negativo na tela (critério 1) — a diferença é exibida
    # em módulo, com o lado à parte, como PALAVRA.
    assert "-" not in diferenca_exibida
    assert lado_exibido == lado_esperado

    # O NÚMERO exibido bate com o Decimal calculado de forma independente
    # neste teste (critério de aceite 2), não só com o texto esperado —
    # evita que um erro de arredondamento no `_valor_ptbr` da view e no
    # texto esperado do teste se cancelem por coincidência.
    diferenca_real = abs(
        Decimal(valor_debito.replace(".", "").replace(",", "."))
        - Decimal(valor_credito.replace(".", "").replace(",", "."))
    )
    assert diferenca_real == diferenca_esperada
    assert _ptbr_para_decimal(diferenca_exibida) == diferenca_esperada

    # As duas células de total voltam a mostrar SÓ o valor — sem parênteses,
    # que neste produto já significam "valor invertido" (direção de arte
    # §2A), nunca "diferença que falta".
    assert f"Débito: {valor_debito}</td>" in rodape
    assert f"Crédito: {valor_credito}</td>" in rodape
    assert "(" not in re.sub(_PADRAO_VEREDITO_NAO_FECHA, "", rodape)

    assert LancamentoContabil.objects.count() == 0


def test_gravar_recusado_por_nao_fechar_tambem_mostra_a_diferenca(client, cen):
    """O veredito não é exclusivo do botão "Adicionar linha": uma tentativa
    de GRAVAR com débito e crédito diferentes é recusada (400) e a MESMA
    tela reaparece — o veredito precisa continuar mostrando a diferença
    neste caminho, não só no de conferência.
    """
    _login(client, cen)
    resposta = _post(
        client,
        cen,
        acao="gravar",
        valor_debito="2.345,67",
        valor_credito="2.000,00",
        chave="k-gravar-nao-fecha",
    )
    assert resposta.status_code == 400
    assert LancamentoContabil.objects.count() == 0
    rodape = _linha_total(resposta.content.decode())
    assert "Não fecha" in rodape
    achado = _PADRAO_VEREDITO_NAO_FECHA.search(rodape)
    assert achado, rodape
    assert achado.group(2) == "crédito"
    assert _ptbr_para_decimal(achado.group(1)) == Decimal("345.67")
    assert "(" not in re.sub(_PADRAO_VEREDITO_NAO_FECHA, "", rodape)


def test_fecha_nao_mostra_diferenca_nenhuma(client, cen):
    """Critério 2: quando os totais fecham, não existe "diferença de 0,00"
    para exibir — nada de ruído. O texto "faltam" não pode aparecer.
    """
    _login(client, cen)
    resposta = _post(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="777,77",
        valor_credito="777,77",
        chave="k-fecha",
    )
    assert resposta.status_code == 200
    rodape = _linha_total(resposta.content.decode())
    assert "linha-total__veredito--fecha" in rodape
    assert ">Fecha<" in rodape
    assert "faltam" not in rodape
    assert "0,00" not in rodape


def test_ainda_nao_conferido_continua_distinto_de_nao_fecha(client, cen):
    """Critério 3: a primeira visita (GET, sem nenhuma linha preenchida
    ainda) mostra "ainda não conferido" — um RASCUNHO sem veredito nunca
    pode ser confundido com um lançamento que "não fecha".
    """
    _login(client, cen)
    resposta = client.get(_url_tela(cen))
    assert resposta.status_code == 200
    rodape = _linha_total(resposta.content.decode())
    assert "ainda não conferido" in rodape
    assert "Não fecha" not in rodape
    assert ">Fecha<" not in rodape
    assert "faltam" not in rodape
