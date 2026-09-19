"""BL-289 (A1 da auditoria DL-026 rodada 2,
docs/auditorias/2026-09-18-dl-024-rodada-2.md): o veredito "Fecha" do
lançamento MENTIA em quatro estados alcançáveis, porque o template comparava
TEXTO pt-BR (`total_debito_ptbr == total_credito_ptbr`) em vez de `Decimal`.
`_valor_ptbr(Decimal("0"))` devolve `"0,00"`, que é verdadeiro em template
Django, e `"0,00" == "0,00"` também — formulário em branco, linhas
descartadas, total zero e total negativo caíam todos em "Fecha".

Este arquivo testa a DECISÃO (responsabilidade do `desenvolvedor-pleno`:
`apps.contabilidade.views_web._veredito_fechamento`/
`_contexto_form_lancamento`), lendo `response.context["veredito_fechamento"]`
— nunca o HTML renderizado, que é responsabilidade do `especialista-frontend`
e está sendo corrigido em paralelo contra o MESMO contrato de chaves. Testar
via `response.context` prova exatamente o que é meu: a VIEW nunca mais
decide "fecha" fora das quatro condições que também autorizam gravar.

Dados 100% sintéticos, criados nos próprios testes.
"""

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
    escritorio = Escritorio.objects.create(nome="Escritório de teste", cnpj="22222222000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-289 Ltda", cnpj="22233344000194"
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
        username="gestora-bl289",
        email="gestora-bl289@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _login(client, cen):
    assert client.login(username="gestora-bl289", password="senha-forte-123")


def _url_tela(cen):
    return reverse("contabilidade_web:lancamento_novo", args=[cen["empresa"].id])


def _post_duas_linhas(client, cen, *, acao, valor_debito, valor_credito, chave, historico="BL-289"):
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


# ---------------------------------------------------------------------------
# Os cinco estados que o A1 mediu, um a um — cada um exigindo
# `veredito_fechamento` explicitamente, nunca deduzido do HTML.
# ---------------------------------------------------------------------------


def test_formulario_em_branco_nao_e_fecha(client, cen):
    """Passo 1 da reprodução do A1: formulário totalmente em branco +
    "Adicionar linha". Media pelo auditor: `Fecha` em verde sobre
    Débito/Crédito 0,00/0,00. Não pode mais acontecer: nenhuma linha
    preenchida não tem o que conferir."""
    _login(client, cen)
    resposta = client.post(
        _url_tela(cen),
        {
            "acao": "adicionar_linha",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "",
            "chave_idempotencia": "k-bl289-branco",
            "conta_1": "",
            "tipo_1": "",
            "valor_1": "",
            "conta_2": "",
            "tipo_2": "",
            "valor_2": "",
        },
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    assert resposta.context["diferenca_fechamento_ptbr"] is None
    assert resposta.context["lado_faltante_fechamento"] is None


def test_duas_linhas_com_valor_invalido_descartadas_nao_e_fecha(client, cen):
    """Passo 2: duas linhas com conta e tipo certos, valor "abc"/"xyz" —
    a própria tela avisa que as duas linhas foram descartadas do total
    (`linhas_excluidas_do_total`), e o rodapé não pode dizer "Fecha" logo
    abaixo desse aviso."""
    _login(client, cen)
    resposta = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="abc",
        valor_credito="xyz",
        chave="k-bl289-invalidas",
    )
    assert resposta.status_code == 200
    assert resposta.context["linhas_excluidas_do_total"] == 2
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    assert resposta.context["diferenca_fechamento_ptbr"] is None


def test_totais_zerados_nao_e_fecha_e_gravar_recusa(client, cen):
    """Passo 3: `0,00`/`0,00`. Antes desta correção: "Fecha" no rodapé E
    `acao=gravar` no mesmo corpo devolvendo 400 — a MESMA tela dizendo duas
    coisas contraditórias ao mesmo tempo. Confere as duas metades: o
    veredito de conferência E a recusa real."""
    _login(client, cen)
    resposta_conferencia = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="0,00",
        valor_credito="0,00",
        chave="k-bl289-zero",
    )
    assert resposta_conferencia.status_code == 200
    assert resposta_conferencia.context["veredito_fechamento"] == "nao_conferido"

    resposta_gravar = _post_duas_linhas(
        client,
        cen,
        acao="gravar",
        valor_debito="0,00",
        valor_credito="0,00",
        chave="k-bl289-zero",
    )
    assert resposta_gravar.status_code == 400
    assert resposta_gravar.context["veredito_fechamento"] == "nao_conferido"
    assert LancamentoContabil.objects.count() == 0


def test_totais_negativos_nao_e_fecha(client, cen):
    """Passo 4: `-100,00`/`-100,00` — os dois lados SÃO iguais em texto
    (`"-100,00" == "-100,00"`), mas um total não positivo nunca fecha."""
    _login(client, cen)
    resposta = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="-100,00",
        valor_credito="-100,00",
        chave="k-bl289-negativo",
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    assert resposta.context["diferenca_fechamento_ptbr"] is None


def test_gravar_com_formulario_em_branco_e_nao_conferido_nao_fecha(client, cen):
    """Passo 5: `acao=gravar` direto num formulário em branco — 400,
    "Informe ao menos duas partidas", e o rodapé não pode dizer "Fecha"."""
    _login(client, cen)
    resposta = client.post(
        _url_tela(cen),
        {
            "acao": "gravar",
            "num_linhas": "2",
            "data": timezone.localdate().isoformat(),
            "historico": "",
            "chave_idempotencia": "k-bl289-gravar-branco",
            "conta_1": "",
            "tipo_1": "",
            "valor_1": "",
            "conta_2": "",
            "tipo_2": "",
            "valor_2": "",
        },
    )
    assert resposta.status_code == 400
    assert resposta.context["veredito_fechamento"] == "nao_conferido"
    assert LancamentoContabil.objects.count() == 0


# ---------------------------------------------------------------------------
# Controles positivos: os dois estados que CONTINUAM existindo, sem
# regressão — "fecha" de verdade e "não fecha" com diferença.
# ---------------------------------------------------------------------------


def test_totais_iguais_e_positivos_e_fecha(client, cen):
    _login(client, cen)
    resposta = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="777,77",
        valor_credito="777,77",
        chave="k-bl289-fecha",
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "fecha"
    assert resposta.context["diferenca_fechamento_ptbr"] is None
    assert resposta.context["lado_faltante_fechamento"] is None


def test_totais_divergentes_sem_exclusao_e_nao_fecha(client, cen):
    _login(client, cen)
    resposta = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="1.500,00",
        valor_credito="900,00",
        chave="k-bl289-nao-fecha",
    )
    assert resposta.status_code == 200
    assert resposta.context["veredito_fechamento"] == "nao_fecha"
    assert resposta.context["diferenca_fechamento_ptbr"] == "600,00"
    assert resposta.context["lado_faltante_fechamento"] == "crédito"


# ---------------------------------------------------------------------------
# A invariante única exigida pela auditoria — GENÉRICA, não um caso isolado:
# "se a tela diz Fecha, gravar com o mesmo corpo tem de devolver 302, nunca
# 400". Testada contra uma bateria de valores representativos (redondo,
# centavo, grande, fracionário) — cada um confirma a PRÉ-CONDIÇÃO (o corpo
# realmente fecha) antes de exercitar a invariante, para não passar por
# vacuidade se a lógica de "fecha" um dia mudar de critério sem que ninguém
# perceba.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor_debito, valor_credito",
    [
        ("777,77", "777,77"),
        ("1.500,00", "1.500,00"),
        ("0,01", "0,01"),
        ("999.999,99", "999.999,99"),
        ("10.000,50", "10.000,50"),
    ],
)
def test_invariante_fecha_implica_gravar_302_nunca_400(client, cen, valor_debito, valor_credito):
    """BL-289: a invariante que a auditoria pediu explicitamente, "além dos
    casos individuais" — cobre de uma vez os cinco estados que mentiam
    antes desta correção, porque nenhum deles chega a "fecha" depois dela
    (ver os testes acima), e prova que todo "fecha" genuíno continua
    gravando.
    """
    _login(client, cen)
    chave = f"k-bl289-invariante-{valor_debito}-{valor_credito}"
    resposta_conferencia = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito=valor_debito,
        valor_credito=valor_credito,
        chave=chave,
    )
    assert resposta_conferencia.context["veredito_fechamento"] == "fecha", (
        "pré-condição do teste: este corpo deveria fechar — "
        f"{resposta_conferencia.context.get('veredito_fechamento')!r}"
    )

    resposta_gravar = _post_duas_linhas(
        client,
        cen,
        acao="gravar",
        valor_debito=valor_debito,
        valor_credito=valor_credito,
        chave=chave,
    )
    assert resposta_gravar.status_code == 302, (
        f"veredito dizia 'fecha' mas gravar devolveu {resposta_gravar.status_code}: "
        f"{getattr(resposta_gravar, 'content', b'')[:300]!r}"
    )
    assert LancamentoContabil.objects.filter(chave_idempotencia=chave).exists()
    lancamento = LancamentoContabil.objects.get(chave_idempotencia=chave)
    itens = list(lancamento.itens.all())
    total_debito = sum((i.valor for i in itens if i.tipo == "debito"), Decimal("0"))
    total_credito = sum((i.valor for i in itens if i.tipo == "credito"), Decimal("0"))
    assert total_debito == total_credito
    esperado = Decimal(valor_debito.replace(".", "").replace(",", "."))
    assert total_debito == esperado


def test_invariante_a_contrapositiva_nao_fecha_nunca_grava(client, cen):
    """Contraponto de sanidade (não pedido pela auditoria como obrigatório,
    mas fecha o raciocínio): um corpo que NÃO fecha nunca pode devolver
    302 em `gravar` — já garantido por `criar_lancamento`, aqui confirmado
    junto com o veredito."""
    _login(client, cen)
    resposta_conferencia = _post_duas_linhas(
        client,
        cen,
        acao="adicionar_linha",
        valor_debito="0,00",
        valor_credito="0,00",
        chave="k-bl289-contrapositiva",
    )
    assert resposta_conferencia.context["veredito_fechamento"] != "fecha"

    resposta_gravar = _post_duas_linhas(
        client,
        cen,
        acao="gravar",
        valor_debito="0,00",
        valor_credito="0,00",
        chave="k-bl289-contrapositiva",
    )
    assert resposta_gravar.status_code == 400
    assert LancamentoContabil.objects.count() == 0
