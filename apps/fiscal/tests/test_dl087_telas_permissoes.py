"""DL-087 (frente B): permissão, isolamento e CSRF das telas da classificação.

Regras (AGENTS.md §11, decididas no SERVIDOR, nunca só na tela):
- leitura (lista, fila, formulário vazio, regras do produto): quem consulta documentos fiscais;
  PARALEGAL lê; CLIENTE recebe 403;
- regra de EMPRESA: quem escritura no fiscal (ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO);
- regra do ESCRITÓRIO: só ADMINISTRADOR e GESTOR. Forjar o POST com `escopo=escritorio` não passa;
- desativar: a permissão é a do escopo DA REGRA, e não a do que a URL pede;
- empresa ou regra de OUTRO escritório, ou de OUTRA empresa do mesmo escritório: 404;
- POST sem CSRF: 403, sem gravar nada.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import classificacao
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import RegraClassificacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.suporte_dl085 import CNPJ_SEGUNDA_EMPRESA, nfce
from apps.fiscal.tests.test_dl087_telas import (  # funções auxiliares do arquivo de telas
    dados,
    url_desativar,
    url_fila,
    url_nova,
    url_regras,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


def formulario(**campos):
    base = {
        "escopo": "empresa",
        "tipo": "saida_propria",
        "cfop": "5102",
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
        "natureza": "revenda",
        "vigencia_inicio": "01/03/2026",
        "vigencia_fim": "",
        "competencia": "03/2026",
        "acao": "criar",
    }
    base.update(campos)
    return base


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Permissoes DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-permissoes-dl087")


@pytest.fixture
def analista(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.ANALISTA, "analista-permissoes-dl087")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-permissoes-dl087")


@pytest.fixture
def cliente(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-permissoes-dl087")


@pytest.fixture
def financeiro(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.FINANCEIRO, "financeiro-permissoes-dl087")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-permissoes-dl087")


@pytest.fixture
def empresa_b(escritorio_b):
    return Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B DL087 Ltda", cnpj="77888999000155"
    )


@pytest.fixture
def vizinha(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Vizinha DL087 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )


@pytest.fixture
def regra_do_escritorio(escritorio_a, gestor, empresa):
    return classificacao.criar_regra(
        escritorio=escritorio_a, empresa=None, dados=dados(), usuario=gestor
    )


@pytest.fixture
def regra_da_empresa(escritorio_a, gestor, empresa):
    return classificacao.criar_regra(
        escritorio=escritorio_a, empresa=empresa, dados=dados(cfop="5102"), usuario=gestor
    )


def _logado(client, usuario):
    client.force_login(usuario)
    return client


# ---------------------------------------------------------------------------
# Cliente e anônimo
# ---------------------------------------------------------------------------


def test_cliente_recebe_403_em_todas_as_telas(client, cliente, empresa, regra_do_escritorio):
    _logado(client, cliente)
    paginas = [
        url_regras(empresa),
        url_nova(empresa),
        url_fila(empresa),
        url_desativar(empresa, regra_do_escritorio),
        reverse("fiscal_web:classificacao_produto"),
    ]

    for url in paginas:
        assert client.get(url).status_code == 403, url


def test_cliente_recebe_403_em_toda_escrita_e_nada_muda(
    client, cliente, empresa, regra_do_escritorio
):
    _logado(client, cliente)
    antes = RegraClassificacaoNFe.objects.count()

    assert client.post(url_nova(empresa), formulario()).status_code == 403
    assert (
        client.post(url_desativar(empresa, regra_do_escritorio), {"motivo": "x"}).status_code == 403
    )
    assert RegraClassificacaoNFe.objects.count() == antes
    regra_do_escritorio.refresh_from_db()
    assert regra_do_escritorio.ativa


def test_anonimo_vai_para_o_login_em_todas_as_telas(client, empresa, regra_do_escritorio):
    paginas = [
        url_regras(empresa),
        url_nova(empresa),
        url_fila(empresa),
        url_desativar(empresa, regra_do_escritorio),
        reverse("fiscal_web:classificacao_produto"),
    ]

    for url in paginas:
        resposta = client.get(url)
        assert resposta.status_code == 302, url
        assert "login" in resposta["Location"], url


def test_anonimo_nao_escreve(client, empresa):
    assert client.post(url_nova(empresa), formulario()).status_code == 302
    assert not RegraClassificacaoNFe.objects.exists()


# ---------------------------------------------------------------------------
# PARALEGAL: lê, não escreve, e a tela não convida a escrever
# ---------------------------------------------------------------------------


def test_paralegal_le_lista_fila_e_produto(client, paralegal, empresa, regra_da_empresa):
    _logado(client, paralegal)

    assert client.get(url_regras(empresa)).status_code == 200
    assert client.get(url_fila(empresa)).status_code == 200
    assert client.get(reverse("fiscal_web:classificacao_produto")).status_code == 200


def test_paralegal_nao_ve_criar_regra_na_fila_nem_o_botao_na_lista(
    client, paralegal, gestor, empresa, escritorio_a, regra_da_empresa
):
    # Uma nota sem sugestão, para a fila ter um grupo que OFERECERIA criar regra a quem pudesse.
    for numero in (1, 2):
        nfce(escritorio_a, gestor, numero=numero, cfop="5949", csosn="102", ncm="22030000")
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    _logado(client, paralegal)

    lista = client.get(url_regras(empresa)).content.decode("utf-8")
    fila = client.get(url_fila(empresa)).content.decode("utf-8")

    assert url_nova(empresa) not in lista
    assert 'aria-describedby="id_motivo_sem_criar"' in lista
    assert "Sem sugestão" in fila  # o grupo existe…
    assert "Criar regra" not in fila  # …mas sem o convite a criar
    assert "cfop=5949" not in fila  # e sem o link pré-preenchido


def test_paralegal_recebe_403_em_toda_escrita_e_nada_muda(
    client, paralegal, empresa, regra_da_empresa
):
    _logado(client, paralegal)
    antes = RegraClassificacaoNFe.objects.count()

    assert client.post(url_nova(empresa), formulario(escopo="empresa")).status_code == 403
    assert client.post(url_nova(empresa), formulario(escopo="escritorio")).status_code == 403
    assert client.post(url_desativar(empresa, regra_da_empresa), {"motivo": "x"}).status_code == 403
    assert RegraClassificacaoNFe.objects.count() == antes
    regra_da_empresa.refresh_from_db()
    assert regra_da_empresa.ativa


def test_paralegal_recebe_403_na_confirmacao_de_desativar(
    client, paralegal, empresa, regra_da_empresa
):
    _logado(client, paralegal)

    assert client.get(url_desativar(empresa, regra_da_empresa)).status_code == 403


def test_paralegal_com_403_nao_aprende_nada_das_regras(
    client, paralegal, empresa, regra_do_escritorio
):
    """Forjar um POST de escritório com dado inválido: a resposta é 403, e não 400 com a regra."""
    _logado(client, paralegal)

    resposta = client.post(url_nova(empresa), formulario(escopo="escritorio", cfop="9999"))

    assert resposta.status_code == 403
    assert "fora da tabela" not in resposta.content.decode("utf-8")


# ---------------------------------------------------------------------------
# ANALISTA e FINANCEIRO: regra de empresa sim, regra do escritório não
# ---------------------------------------------------------------------------


def test_analista_cria_regra_de_empresa(client, analista, empresa):
    _logado(client, analista)

    resposta = client.post(url_nova(empresa), formulario(escopo="empresa"))

    assert resposta.status_code == 302
    assert RegraClassificacaoNFe.objects.filter(empresa=empresa).count() == 1


def test_analista_forjando_escopo_escritorio_recebe_403_e_nada_muda(client, analista, empresa):
    _logado(client, analista)

    resposta = client.post(url_nova(empresa), formulario(escopo="escritorio"))

    assert resposta.status_code == 403
    assert "administrador e gestor" in resposta.content.decode("utf-8")
    assert not RegraClassificacaoNFe.objects.exists()


def test_analista_nao_ve_a_opcao_de_escritorio_no_formulario(client, analista, empresa):
    _logado(client, analista)

    html = client.get(url_nova(empresa)).content.decode("utf-8")

    assert 'value="escritorio"' not in html


def test_analista_nao_desativa_regra_do_escritorio(client, analista, empresa, regra_do_escritorio):
    _logado(client, analista)

    assert client.get(url_desativar(empresa, regra_do_escritorio)).status_code == 403
    assert (
        client.post(url_desativar(empresa, regra_do_escritorio), {"motivo": "não"}).status_code
        == 403
    )
    regra_do_escritorio.refresh_from_db()
    assert regra_do_escritorio.ativa


def test_analista_desativa_regra_da_empresa(client, analista, empresa, regra_da_empresa):
    _logado(client, analista)

    resposta = client.post(url_desativar(empresa, regra_da_empresa), {"motivo": "troca"})

    assert resposta.status_code == 302
    regra_da_empresa.refresh_from_db()
    assert not regra_da_empresa.ativa


def test_financeiro_cria_regra_de_empresa_e_nao_de_escritorio(client, financeiro, empresa):
    _logado(client, financeiro)

    assert client.post(url_nova(empresa), formulario(escopo="escritorio")).status_code == 403
    assert client.post(url_nova(empresa), formulario(escopo="empresa")).status_code == 302


def test_gestor_cria_e_desativa_regra_do_escritorio(client, gestor, empresa):
    _logado(client, gestor)

    criada = client.post(url_nova(empresa), formulario(escopo="escritorio"))
    regra = RegraClassificacaoNFe.objects.get()
    desativada = client.post(url_desativar(empresa, regra), {"motivo": "fim da regra"})

    assert criada.status_code == 302
    assert desativada.status_code == 302
    regra.refresh_from_db()
    assert not regra.ativa


# ---------------------------------------------------------------------------
# Isolamento: outro escritório, e outra empresa do MESMO escritório
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404_em_todas_as_telas(
    client, gestor_b, empresa, regra_da_empresa
):
    _logado(client, gestor_b)

    assert client.get(url_regras(empresa)).status_code == 404
    assert client.get(url_nova(empresa)).status_code == 404
    assert client.get(url_fila(empresa)).status_code == 404
    assert client.get(url_desativar(empresa, regra_da_empresa)).status_code == 404
    assert client.post(url_nova(empresa), formulario()).status_code == 404


def test_regra_de_outro_escritorio_responde_404_ao_desativar_pela_url_da_empresa_dele(
    client, gestor_b, gestor, empresa_b, empresa, regra_da_empresa
):
    criada = classificacao.criar_regra(
        escritorio=empresa_b.escritorio, empresa=empresa_b, dados=dados(), usuario=gestor_b
    )
    _logado(client, gestor)

    assert client.post(url_desativar(empresa, criada), {"motivo": "x"}).status_code == 404
    criada.refresh_from_db()
    assert criada.ativa


def test_regra_da_empresa_vizinha_responde_404_pela_url_de_outra_empresa(
    client, gestor, empresa, vizinha, escritorio_a
):
    da_vizinha = classificacao.criar_regra(
        escritorio=escritorio_a, empresa=vizinha, dados=dados(cfop="5103"), usuario=gestor
    )
    _logado(client, gestor)

    assert client.get(url_desativar(empresa, da_vizinha)).status_code == 404
    assert client.post(url_desativar(empresa, da_vizinha), {"motivo": "x"}).status_code == 404
    da_vizinha.refresh_from_db()
    assert da_vizinha.ativa


def test_lista_da_empresa_nao_mostra_regra_da_vizinha(
    client, gestor, empresa, vizinha, escritorio_a, regra_do_escritorio
):
    classificacao.criar_regra(
        escritorio=escritorio_a, empresa=vizinha, dados=dados(cfop="5103"), usuario=gestor
    )
    _logado(client, gestor)

    html = client.get(url_regras(empresa)).content.decode("utf-8")

    assert "CFOP 5103" not in html
    assert "CFOP 5949" in html  # a do escritório, que vale para todas


def test_mesmo_cnpj_em_outro_escritorio_nao_vaza_a_regra(
    client, gestor_b, escritorio_b, escritorio_a, gestor, regra_do_escritorio
):
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Mesmo CNPJ B DL087", cnpj="77888999000155"
    )
    _logado(client, gestor_b)

    html = client.get(url_regras(empresa_b)).content.decode("utf-8")

    assert "CFOP 5949" not in html


# ---------------------------------------------------------------------------
# CSRF: POST sem o token é recusado, e não grava
# ---------------------------------------------------------------------------


def test_post_sem_token_csrf_e_recusado_e_nao_grava(gestor, empresa):
    client = Client(enforce_csrf_checks=True)
    client.force_login(gestor)

    resposta = client.post(url_nova(empresa), formulario(escopo="empresa"))

    assert resposta.status_code == 403
    assert not RegraClassificacaoNFe.objects.exists()


def test_desativar_sem_token_csrf_e_recusado_e_nao_desativa(gestor, empresa, regra_do_escritorio):
    client = Client(enforce_csrf_checks=True)
    client.force_login(gestor)

    resposta = client.post(url_desativar(empresa, regra_do_escritorio), {"motivo": "x"})

    assert resposta.status_code == 403
    regra_do_escritorio.refresh_from_db()
    assert regra_do_escritorio.ativa
