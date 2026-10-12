"""DL-087 (frente B): a origem da sugestão aparece na escrituração e no lote, com link para a regra.

A origem é a que o SERVIÇO devolve (`origem`, `regra_ids`, `escopo_regra` e, no lote, `fonte`); a
tela só a traduz. Este arquivo prova: (a) a regra, o conflito, o produto e o padrão aparecem com
o texto certo; (b) a regra tem link para a própria lista, com âncora; (c) o lote, por assinatura,
mostra a regra com link; (d) a lista "NF-e a escriturar" leva à fila e às regras.

Dados sintéticos: NFC-e geradas pela recepção real (`suporte_dl085.nfce`).
"""

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import classificacao, views_web
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.escrituracao_nfe_lote import AssinaturaDoItem
from apps.fiscal.models import ParametrosPresumidoEmpresa
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl085 import nfce
from apps.fiscal.tests.test_dl087_telas import dados, url_regras
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Origem DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-origem-dl087")


def _ler(empresa_):
    lote.ler_notas_do_mes(empresa_, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)


def _url_escriturar(empresa_, vinculo_):
    return reverse("fiscal_web:nfe_escriturar", args=[empresa_.pk, vinculo_.pk])


def _url_lote(empresa_):
    return reverse("fiscal_web:nfe_lote", args=[empresa_.pk]) + "?ano=2026&mes=3"


def _regra_do_escritorio(escritorio, usuario, **campos):
    return classificacao.criar_regra(
        escritorio=escritorio, empresa=None, dados=dados(**campos), usuario=usuario
    )


# ---------------------------------------------------------------------------
# A escrituração: a origem de cada sugestão, com o link para a regra
# ---------------------------------------------------------------------------


def test_escrituracao_mostra_a_regra_do_escritorio_e_o_link_para_ela(
    client, gestor, empresa, escritorio_a
):
    regra = _regra_do_escritorio(escritorio_a, gestor)
    documento = nfce(escritorio_a, gestor, numero=1, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_escriturar(empresa, vinculo(documento, empresa))).content.decode("utf-8")

    assert f"Origem da sugestão: regra n.º {regra.pk} (do escritório)" in html
    assert f"{url_regras(empresa)}#regra-{regra.pk}" in html


def test_rascunho_mostra_a_origem_da_regra_com_o_link_na_linha_do_item(
    client, gestor, empresa, escritorio_a
):
    """No rascunho a linha tem o campo de natureza: a origem vem ao lado da sugestão, com link."""
    regra = _regra_do_escritorio(escritorio_a, gestor)
    documento = nfce(escritorio_a, gestor, numero=7, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    vinculo_ = vinculo(documento, empresa)
    client.force_login(gestor)
    client.post(_url_escriturar(empresa, vinculo_), {"acao": "criar"})

    html = client.get(_url_escriturar(empresa, vinculo_)).content.decode("utf-8")

    assert "Confirmar natureza" in html  # é de fato o ramo do rascunho
    assert f"Origem da sugestão: regra n.º {regra.pk} (do escritório)." in html
    assert f'href="{url_regras(empresa)}#regra-{regra.pk}"' in html


def test_escrituracao_mostra_a_sugestao_do_produto_sem_link_de_regra(
    client, gestor, empresa, escritorio_a
):
    documento = nfce(escritorio_a, gestor, numero=2, cfop="5102", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_escriturar(empresa, vinculo(documento, empresa))).content.decode("utf-8")

    assert "Origem da sugestão: sugestão do produto." in html
    assert "#regra-" not in html


def test_escrituracao_mostra_o_conflito_com_os_links_das_duas_regras(
    client, gestor, empresa, escritorio_a
):
    """Duas regras do mesmo escopo, critérios iguais e natureza diferente, valendo no mesmo dia.

    A criação recusa duplicata SÓ entre regras ativas. Por isso a primeira é desativada (a vigência
    dela termina ontem, e ainda cobre março) antes de criar a segunda.
    """
    primeira = _regra_do_escritorio(escritorio_a, gestor, natureza="revenda")
    classificacao.desativar_regra(primeira, motivo="troca para testar conflito", usuario=gestor)
    segunda = _regra_do_escritorio(escritorio_a, gestor, natureza="producao_propria")
    documento = nfce(escritorio_a, gestor, numero=3, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_escriturar(empresa, vinculo(documento, empresa))).content.decode("utf-8")

    assert (
        f"Origem da sugestão: regras em conflito: regra n.º {primeira.pk} e regra n.º {segunda.pk}."
        in html
    )
    assert f"#regra-{primeira.pk}" in html and f"#regra-{segunda.pk}" in html


# ---------------------------------------------------------------------------
# O lote: a origem de cada par, e o link para a fila do mês
# ---------------------------------------------------------------------------


def test_lote_mostra_a_origem_da_regra_com_link_e_o_link_para_a_fila(
    client, gestor, empresa, escritorio_a
):
    regra = _regra_do_escritorio(escritorio_a, gestor)
    nfce(escritorio_a, gestor, numero=4, cfop="5949", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_lote(empresa)).content.decode("utf-8")

    # O link envolve o texto da origem: o trecho é "…>regra n.º N (do escritório)</a>".
    assert f"regra n.º {regra.pk} (do escritório)</a>" in html
    assert f'href="{url_regras(empresa)}#regra-{regra.pk}"' in html
    assert reverse("fiscal_web:classificacao_fila", args=[empresa.pk]) in html


def test_lote_sem_regra_diz_que_a_origem_e_produto_ou_padrao(client, gestor, empresa, escritorio_a):
    nfce(escritorio_a, gestor, numero=5, cfop="5102", csosn="102", ncm="22030000")
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_lote(empresa)).content.decode("utf-8")

    assert "Origem: sugestão do produto ou padrão de combustível da empresa" in html


# ---------------------------------------------------------------------------
# A lista "NF-e a escriturar" leva à fila e às regras
# ---------------------------------------------------------------------------


def test_lista_nfe_a_escriturar_tem_links_para_a_fila_e_para_as_regras(client, gestor, empresa):
    client.force_login(gestor)

    html = client.get(
        reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={empresa.pk}&ano=2026&mes=3"
    ).content.decode("utf-8")

    fila = reverse("fiscal_web:classificacao_fila", args=[empresa.pk]) + "?ano=2026&amp;mes=3"
    assert f'href="{fila}"' in html
    assert f'href="{url_regras(empresa)}"' in html


# ---------------------------------------------------------------------------
# O helper de origem: os quatro casos, direto (inclusive o padrão de combustível)
# ---------------------------------------------------------------------------


def test_origem_da_sugestao_cobre_regra_produto_padrao_conflito_e_sem_sugestao(empresa):
    regra = servico_nfe.Sugestao(
        "revenda",
        "sugerida pela regra n.º 7",
        origem=servico_nfe.ORIGEM_DA_SUGESTAO_REGRA,
        regra_ids=(7,),
        escopo_regra="escritorio",
    )
    produto = servico_nfe.Sugestao("revenda", "x", origem=servico_nfe.ORIGEM_DA_SUGESTAO_PRODUTO)
    padrao = servico_nfe.Sugestao("combustivel", "x", origem=servico_nfe.ORIGEM_DA_SUGESTAO_PADRAO)
    conflito = servico_nfe.Sugestao(
        None,
        "conflito",
        origem=servico_nfe.ORIGEM_DA_SUGESTAO_CONFLITO_DE_REGRAS,
        regra_ids=(7, 9),
        escopo_regra="empresa",
    )
    sem = servico_nfe.Sugestao(None, "sem sinal")

    assert views_web._origem_da_sugestao_na_tela(regra, empresa)["origem_texto"] == (
        "regra n.º 7 (do escritório)"
    )
    assert views_web._origem_da_sugestao_na_tela(produto, empresa)["origem_texto"] == (
        "sugestão do produto"
    )
    assert views_web._origem_da_sugestao_na_tela(padrao, empresa)["origem_texto"] == (
        "padrão de combustível da empresa"
    )
    assert views_web._origem_da_sugestao_na_tela(conflito, empresa)["origem_texto"] == (
        "regras em conflito: regra n.º 7 e regra n.º 9"
    )
    assert views_web._origem_da_sugestao_na_tela(sem, empresa)["origem_texto"] == (
        "nenhuma (sem sugestão)"
    )
    links = views_web._origem_da_sugestao_na_tela(regra, empresa)["origem_links"]
    assert links == [{"rotulo": "regra n.º 7", "url": f"{url_regras(empresa)}#regra-7"}]
    assert views_web._origem_da_sugestao_na_tela(regra, None)["origem_links"] == []


def test_origem_do_par_do_lote_distingue_regra_de_produto_ou_padrao(empresa):
    com_regra = AssinaturaDoItem("5949", "102", "revenda", "regra:12")
    sem_regra = AssinaturaDoItem("5949", "102", "revenda", "")

    assert views_web._origem_da_assinatura_na_tela(com_regra, empresa, {})["origem_texto"] == (
        "regra n.º 12"
    )
    origem_sem = views_web._origem_da_assinatura_na_tela(sem_regra, empresa, {})
    assert origem_sem["origem_texto"] == "sugestão do produto ou padrão de combustível da empresa"
    assert origem_sem["origem_url"] is None


def test_padrao_de_combustivel_da_empresa_aparece_como_origem_na_escrituracao(
    client, gestor, empresa, escritorio_a
):
    """Posto com padrão de combustível: o CFOP não decide, o CSOSN não tem sinal, e o NCM é de
    combustível. (Com CSOSN 500 o próprio produto decide: a origem seria 'produto', e isso é
    coberto pelo teste de escrituração acima.)"""
    ParametrosPresumidoEmpresa.objects.create(
        empresa=empresa,
        forma_recolhimento="quota_unica",
        atualizado_por=gestor,
        padrao_combustivel="posto",
    )
    documento = nfce(
        escritorio_a, gestor, numero=6, cfop="5949", csosn="102", ncm="27101259", valor="100.00"
    )
    _ler(empresa)
    client.force_login(gestor)

    html = client.get(_url_escriturar(empresa, vinculo(documento, empresa))).content.decode("utf-8")

    assert "Origem da sugestão: padrão de combustível da empresa." in html
