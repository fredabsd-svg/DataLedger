"""DL-081, correção da rodada 1 (A10): a confirmação da reclassificação compara o CONJUNTO.

A rodada 1 comparava só as contagens (notas e itens). Cenário do relatório: prévia com 2 notas e 2
itens; entre a prévia e a confirmação, uma nota é efetivada e outra é criada. Os números batem, e a
confirmação reclassificou a nota nova, que não estava na prévia. Agora a prévia grava uma assinatura
(hash dos pares escrituração/item) no formulário, e a confirmação recusa quando o conjunto mudou.
"""

import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.test_dl081_reclassificacao import naturezas_da, nota_com_itens
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-a10-reclassificacao-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Reclassificacao A10 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _dados_da_reclassificacao(empresa, **extra):
    dados = {
        "acao": "previa",
        "empresa": empresa.pk,
        "natureza": N.PRODUCAO_PROPRIA,
        "inicio": "",
        "fim": "",
        "cfop": "5102",
        "cst_csosn": "",
        "ncm": "",
    }
    dados.update(extra)
    return dados


def _campo_oculto(html: str, nome: str) -> str:
    achado = re.search(rf'name="{nome}" value="([^"]*)"', html)
    assert achado is not None, nome
    return achado.group(1)


def _previa(client, empresa):
    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"), _dados_da_reclassificacao(empresa)
    )
    assert resposta.status_code == 200
    html = resposta.content.decode()
    return {
        "notas": _campo_oculto(html, "previstas_notas"),
        "itens": _campo_oculto(html, "previstos_itens"),
        "assinatura": _campo_oculto(html, "previstas_assinatura"),
    }


def _confirmar(client, empresa, previa, **extra):
    dados = _dados_da_reclassificacao(
        empresa,
        acao="confirmar",
        previstas_notas=previa["notas"],
        previstos_itens=previa["itens"],
        previstas_assinatura=previa["assinatura"],
    )
    dados.update(extra)
    return client.post(reverse("fiscal_web:nfe_reclassificar"), dados)


def test_confirmacao_sem_mudanca_reclassifica_o_que_a_previa_mostrou(
    escritorio_a, gestor, empresa, client
):
    """Controle: sem mudança entre a prévia e a confirmação, a reclassificação acontece."""
    a = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=1,
        itens=[("5102", "102", "22030000", "100.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    client.force_login(gestor)
    previa = _previa(client, empresa)
    assert previa["notas"] == "1" and previa["itens"] == "1" and len(previa["assinatura"]) == 64
    resposta = _confirmar(client, empresa, previa)
    assert resposta.status_code == 302
    assert naturezas_da(a) == [(1, N.PRODUCAO_PROPRIA)]


def test_confirmacao_recusa_quando_o_conjunto_muda_com_as_mesmas_contagens(
    escritorio_a, gestor, empresa, client
):
    """O cenário do relatório. Prévia: A e B (rascunhos). Depois, B é efetivada e C é criada.
    Contagens: 2 notas e 2 itens nas duas pontas. Só a assinatura do conjunto acusa a mudança."""
    a = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=11,
        itens=[("5102", "102", "22030000", "100.00")],
        dh_emi="2026-03-10T10:00:00-03:00",
    )
    b = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=12,
        itens=[("5102", "102", "22030000", "200.00")],
        dh_emi="2026-03-11T10:00:00-03:00",
    )
    client.force_login(gestor)
    previa = _previa(client, empresa)
    assert (previa["notas"], previa["itens"]) == ("2", "2")

    # Entre a prévia e a confirmação: B é efetivada, e C (de mesmo CFOP) entra como rascunho.
    NaturezaItemNFe.objects.filter(escrituracao=b).update(natureza=N.REVENDA)
    servico.efetivar(b, usuario=gestor)
    c = nota_com_itens(
        escritorio_a,
        gestor,
        empresa,
        numero=13,
        itens=[("5102", "102", "22030000", "300.00")],
        dh_emi="2026-03-12T10:00:00-03:00",
    )

    resposta = _confirmar(client, empresa, previa)
    assert resposta.status_code == 409
    assert naturezas_da(c) == [(1, "")], (
        "a nota criada depois da prévia não pode ser reclassificada"
    )
    assert naturezas_da(a) == [(1, "")], "nada muda quando a confirmação é recusada"
