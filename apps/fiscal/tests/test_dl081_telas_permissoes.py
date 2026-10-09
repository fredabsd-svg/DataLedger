"""DL-081, frente B: permissões e isolamento das telas da escrituração de NF-e.

Regras (AGENTS.md §11, verificadas no SERVIDOR, não só na tela):
- quem escritura (ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO) escreve;
- PARALEGAL lê a lista, a escrituração e a conferência, mas não vê botão de escrita e recebe 403
  em qualquer POST, e em estorno e reclassificação (telas só de ação);
- CLIENTE recebe 403 em todas as telas novas;
- anônimo vai para o login;
- empresa ou nota de outro escritório responde 404, e de outra empresa do mesmo escritório também
  (IDOR), sem confirmar que o ID existe.
"""

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch

from apps.empresas.models import Empresa
from apps.fiscal.models import EscrituracaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl081_telas import _escriturar_com_o_exemplo, simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Permissoes DL081 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Outra Permissoes DL081 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-permissoes-dl081")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-permissoes-dl081")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-permissoes-dl081")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-permissoes-dl081")


@pytest.fixture
def nota_com_escrituracao(escritorio_a, gestor, emitente, outra):
    """Uma nota efetivada da empresa `emitente` e uma rascunho da `outra`, no mesmo escritório."""
    minha = vinculo(receber(escritorio_a, gestor, simples(numero="1")), emitente)
    client = Client()
    client.force_login(gestor)
    _escriturar_com_o_exemplo(client, emitente, minha)
    client.post(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, minha.pk]), {"acao": "efetivar"}
    )
    alheia = vinculo(
        receber(
            escritorio_a,
            gestor,
            xml.nfe(
                dets=[xml.det(1, cfop="5102", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
                vnf="100.00",
                totais={"vProd": "100.00"},
                emitente=("CNPJ", CNPJ_DESTINATARIO_A),
                emitente_nome=outra.razao_social,
                destinatario=None,
                numero="7",
            ),
        ),
        outra,
    )
    client.post(reverse("fiscal_web:nfe_escriturar", args=[outra.pk, alheia.pk]), {"acao": "criar"})
    return {
        "minha": minha,
        "escrituracao": EscrituracaoNFe.objects.get(vinculo=minha),
        "alheia": alheia,
        "alheia_rascunho": EscrituracaoNFe.objects.get(vinculo=alheia),
    }


def _urls(empresa, nota):
    """As rotas novas, GET, com a empresa e a nota dadas."""
    return {
        "lista": reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={empresa.pk}&ano=2026&mes=3",
        "escriturar": reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, nota["minha"].pk]),
        "estornar": reverse("fiscal_web:nfe_estornar", args=[empresa.pk, nota["escrituracao"].pk]),
        "reclassificar": reverse("fiscal_web:nfe_reclassificar") + f"?empresa={empresa.pk}",
        "conferencia": reverse("fiscal_web:nfe_conferencia")
        + f"?empresa={empresa.pk}&ano=2026&mes=3",
    }


def _logado(client, usuario):
    client.force_login(usuario)
    return client


def _post_de_escrita(empresa, nota):
    """Um POST de escrita em cada rota de escrita (criar, efetivar, bloco, estorno, reclass)."""
    return [
        (
            reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, nota["alheia"].pk]),
            {"acao": "criar"},
        ),
        (
            reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, nota["minha"].pk]),
            {"acao": "efetivar"},
        ),
        (
            reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, nota["minha"].pk]),
            {"acao": "bloco", "sinal": "revenda"},
        ),
        (
            reverse("fiscal_web:nfe_estornar", args=[empresa.pk, nota["escrituracao"].pk]),
            {"motivo": "teste"},
        ),
        (
            reverse("fiscal_web:nfe_reclassificar"),
            {"empresa": empresa.pk, "natureza": "revenda", "acao": "previa"},
        ),
        (
            reverse("fiscal_web:nfe_reclassificar"),
            {
                "empresa": empresa.pk,
                "natureza": "revenda",
                "acao": "confirmar",
                "previstas_notas": "1",
                "previstos_itens": "1",
            },
        ),
    ]


# ---------------------------------------------------------------------------
# PARALEGAL: lê, mas não escreve e não vê botão de escrita
# ---------------------------------------------------------------------------


def test_paralegal_le_lista_escrituracao_e_conferencia_sem_botao_de_escrita(
    client, paralegal, gestor, emitente, escritorio_a, nota_com_escrituracao
):
    # Uma nota SEM escrituração no mês: é nela que a lista mostraria "Criar rascunho" indevidamente.
    pendente = vinculo(receber(escritorio_a, gestor, simples(numero="3")), emitente)
    urls = _urls(emitente, nota_com_escrituracao)
    _logado(client, paralegal)

    lista = client.get(urls["lista"]).content.decode("utf-8")
    escriturar = client.get(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, pendente.pk])
    ).content.decode("utf-8")
    conferencia = client.get(urls["conferencia"])

    assert client.get(urls["lista"]).status_code == 200
    assert "Sem escrituração" in lista
    assert "Criar rascunho" not in lista
    assert 'name="acao"' not in escriturar
    assert "Efetivar escrituração" not in escriturar
    assert "Estornar escrituração" not in escriturar
    assert "Reclassificar em massa" not in lista
    assert conferencia.status_code == 200


def test_paralegal_recebe_403_nas_telas_de_acao(client, paralegal, emitente, nota_com_escrituracao):
    urls = _urls(emitente, nota_com_escrituracao)
    _logado(client, paralegal)

    assert client.get(urls["estornar"]).status_code == 403
    assert client.get(urls["reclassificar"]).status_code == 403


@pytest.mark.parametrize("indice", range(6))
def test_paralegal_recebe_403_em_toda_escrita_e_nada_muda(
    client, paralegal, emitente, nota_com_escrituracao, indice
):
    url, dados = _post_de_escrita(emitente, nota_com_escrituracao)[indice]
    antes = EscrituracaoNFe.objects.filter(empresa=emitente).count()
    _logado(client, paralegal)

    resposta = client.post(url, dados)

    assert resposta.status_code == 403
    assert EscrituracaoNFe.objects.filter(empresa=emitente).count() == antes
    nota_com_escrituracao["escrituracao"].refresh_from_db()
    assert nota_com_escrituracao["escrituracao"].estado == "efetivada"


# ---------------------------------------------------------------------------
# CLIENTE: 403 em tudo; anônimo: login
# ---------------------------------------------------------------------------


def test_cliente_recebe_403_em_todas_as_telas_novas(
    client, cliente, emitente, nota_com_escrituracao
):
    urls = _urls(emitente, nota_com_escrituracao)
    _logado(client, cliente)

    for nome, url in urls.items():
        assert client.get(url).status_code == 403, nome


@pytest.mark.parametrize("indice", range(6))
def test_cliente_recebe_403_em_toda_escrita(
    client, cliente, emitente, nota_com_escrituracao, indice
):
    url, dados = _post_de_escrita(emitente, nota_com_escrituracao)[indice]
    _logado(client, cliente)

    assert client.post(url, dados).status_code == 403


def test_anonimo_vai_para_o_login_em_todas_as_telas_novas(client, emitente, nota_com_escrituracao):
    urls = _urls(emitente, nota_com_escrituracao)

    for nome, url in urls.items():
        resposta = client.get(url)
        assert resposta.status_code == 302, nome
        assert "/login" in resposta["Location"] or "login" in resposta["Location"], nome


def test_anonimo_nao_escreve(client, emitente, nota_com_escrituracao):
    for url, dados in _post_de_escrita(emitente, nota_com_escrituracao):
        assert client.post(url, dados).status_code == 302


# ---------------------------------------------------------------------------
# Isolamento: outro escritório e outra empresa do mesmo escritório
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404_na_lista_e_na_conferencia(
    client, gestor_b, emitente, nota_com_escrituracao
):
    _logado(client, gestor_b)

    assert client.get(_urls(emitente, nota_com_escrituracao)["lista"]).status_code == 404
    assert client.get(_urls(emitente, nota_com_escrituracao)["conferencia"]).status_code == 404


def test_nota_de_outro_escritorio_responde_404_na_tela_de_escriturar(
    client, gestor_b, emitente, nota_com_escrituracao
):
    _logado(client, gestor_b)

    assert client.get(_urls(emitente, nota_com_escrituracao)["escriturar"]).status_code == 404


def test_reclassificacao_com_empresa_de_outro_escritorio_responde_404_e_nada_muda(
    client, gestor_b, emitente, nota_com_escrituracao
):
    _logado(client, gestor_b)
    antes = nota_com_escrituracao["alheia_rascunho"]

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {
            "empresa": emitente.pk,
            "natureza": "revenda",
            "acao": "confirmar",
            "previstas_notas": "1",
            "previstos_itens": "1",
        },
    )

    assert resposta.status_code == 404
    antes.refresh_from_db()
    assert antes.estado == "rascunho"


def test_nota_de_outra_empresa_do_mesmo_escritorio_responde_404_idor(
    client, gestor, emitente, outra, nota_com_escrituracao
):
    """A nota de `outra` (mesmo escritório) pela URL de `emitente`: 404, não a nota."""
    _logado(client, gestor)
    alheia = nota_com_escrituracao["alheia"]

    assert (
        client.get(reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, alheia.pk])).status_code
        == 404
    )
    assert (
        client.post(
            reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, alheia.pk]),
            {"acao": "efetivar"},
        ).status_code
        == 404
    )


def test_escrituracao_de_outra_empresa_responde_404_no_estorno_idor(
    client, gestor, emitente, outra, nota_com_escrituracao
):
    _logado(client, gestor)
    rascunho_alheio = nota_com_escrituracao["alheia_rascunho"]

    resposta = client.post(
        reverse("fiscal_web:nfe_estornar", args=[emitente.pk, rascunho_alheio.pk]),
        {"motivo": "tentativa de IDOR"},
    )

    assert resposta.status_code == 404
    rascunho_alheio.refresh_from_db()
    assert rascunho_alheio.estado == "rascunho"


def test_mesmo_cnpj_em_dois_escritorios_nao_vaza_a_nota(
    client, gestor_b, escritorio_b, emitente, nota_com_escrituracao
):
    """Outro escritório com empresa de MESMO CNPJ: a lista dele mostra só a dele."""
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Mesmo CNPJ em B Ltda", cnpj=CNPJ_EMITENTE_A
    )
    _logado(client, gestor_b)

    resposta = client.get(
        reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={empresa_b.pk}&ano=2026&mes=3"
    )

    assert resposta.status_code == 200
    assert "2.970,00" not in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# CSRF e menu
# ---------------------------------------------------------------------------


def test_post_sem_token_csrf_e_recusado(gestor, emitente, nota_com_escrituracao):
    client = Client(enforce_csrf_checks=True)
    _logado(client, gestor)
    alheia = nota_com_escrituracao["alheia"]
    url = reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, alheia.pk])
    antes = EscrituracaoNFe.objects.filter(vinculo=alheia).count()

    resposta = client.post(url, {"acao": "efetivar"})

    assert resposta.status_code == 403
    assert EscrituracaoNFe.objects.filter(vinculo=alheia).count() == antes
    assert EscrituracaoNFe.objects.get(vinculo=alheia).estado == "rascunho"


def test_menu_nao_convida_paralegal_a_reclassificar(
    client, paralegal, emitente, nota_com_escrituracao
):
    _logado(client, paralegal)

    # Na própria lista (e não na conferência, em que o item atual sai como texto e não como link).
    html = client.get(_urls(emitente, nota_com_escrituracao)["lista"]).content.decode("utf-8")

    assert 'aria-labelledby="grupo-escrituracao-nfe"' in html
    assert reverse("fiscal_web:nfe_reclassificar") not in html
    assert f'href="{reverse("fiscal_web:nfe_conferencia")}"' in html


def test_menu_convida_o_gestor_a_reclassificar(client, gestor, emitente, nota_com_escrituracao):
    _logado(client, gestor)

    html = client.get(_urls(emitente, nota_com_escrituracao)["lista"]).content.decode("utf-8")

    assert f'href="{reverse("fiscal_web:nfe_reclassificar")}"' in html


def test_rotas_novas_existem_no_nome_esperado():
    for nome in (
        "fiscal_web:nfe_a_escriturar",
        "fiscal_web:nfe_conferencia",
        "fiscal_web:nfe_reclassificar",
    ):
        assert reverse(nome)
    with pytest.raises(NoReverseMatch):
        reverse("fiscal_web:nfe_escriturar")


def test_usuario_de_outro_escritorio_nao_ve_o_nome_da_empresa_no_menu(
    client, gestor_b, emitente, nota_com_escrituracao
):
    """O menu nunca repete nomes de empresa de outro escritório (DL-040)."""
    _logado(client, gestor_b)

    html = client.get(reverse("fiscal_web:nfe_a_escriturar")).content.decode("utf-8")

    assert emitente.razao_social not in html
    assert get_user_model().objects.filter(pk=gestor_b.pk).exists()
