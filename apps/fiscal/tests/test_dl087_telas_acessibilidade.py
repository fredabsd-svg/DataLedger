"""DL-087 (frente B): acessibilidade das telas da classificação, verificada no HTML renderizado.

O que se confere, com um parser do HTML (não busca de texto):
- todo campo visível tem um `<label for=…>` que aponta para ele;
- todo `aria-describedby` aponta para um `id` que existe na página;
- todo erro de campo é um elemento `role="alert"` com id, e o campo o referencia;
- toda tabela tem `<caption>`, e todo `<th>` tem `scope`;
- a trilha marca a tela atual com `aria-current="page"`.

Não cobre: leitor de tela real (não foi usado, e está dito na direção de arte §7) e o foco visível
desenhado pelo CSS global, que é verificado pela varredura de interface existente, não aqui.
"""

from html.parser import HTMLParser

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import classificacao
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
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


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Posto Acessibilidade DL087 Ltda",
        cnpj=CNPJ_EMITENTE_A,
    )


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-acessibilidade-dl087")


CAMPOS = ("input", "select", "textarea")
SEM_ROTULO_PROPRIO = ("hidden", "submit", "button")


class Auditor(HTMLParser):
    """Coleta o que a conferência precisa: ids, rótulos, campos, referências e tabelas."""

    def __init__(self):
        super().__init__()
        self.ids = set()
        self.rotulos_para = set()
        self.campos = []  # (tag, id, type)
        self.referencias = []  # ids citados em aria-describedby
        self.alertas = set()
        self.tabelas = 0
        self.legendas_de_tabela = 0
        self.cabecalhos_sem_escopo = 0
        self.cabecalhos = 0
        self.atual = []
        self._em_tabela = 0

    def handle_starttag(self, tag, attrs):
        dados_ = dict(attrs)
        if dados_.get("id"):
            self.ids.add(dados_["id"])
        if tag == "label" and dados_.get("for"):
            self.rotulos_para.add(dados_["for"])
        if tag in CAMPOS and dados_.get("type") not in SEM_ROTULO_PROPRIO:
            self.campos.append((tag, dados_.get("id"), dados_.get("type")))
        if dados_.get("aria-describedby"):
            self.referencias.extend(dados_["aria-describedby"].split())
        if dados_.get("role") == "alert" and dados_.get("id"):
            self.alertas.add(dados_["id"])
        if tag == "table":
            self.tabelas += 1
            self._em_tabela += 1
        if tag == "caption" and self._em_tabela:
            self.legendas_de_tabela += 1
        if tag == "th":
            self.cabecalhos += 1
            if not dados_.get("scope"):
                self.cabecalhos_sem_escopo += 1
        if dados_.get("aria-current") == "page":
            self.atual.append(tag)

    def handle_endtag(self, tag):
        if tag == "table":
            self._em_tabela -= 1


def _auditar(html):
    auditor = Auditor()
    auditor.feed(html)
    return auditor


def _conferir_rotulos_e_referencias(auditor):
    """Cada campo visível tem rótulo, e nenhuma referência aponta para o nada."""
    sem_rotulo = [
        (tag, campo_id)
        for tag, campo_id, _tipo in auditor.campos
        if campo_id is None or campo_id not in auditor.rotulos_para
    ]
    assert not sem_rotulo, f"campos sem rótulo ligado: {sem_rotulo}"
    orfas = [ref for ref in auditor.referencias if ref not in auditor.ids]
    assert not orfas, f"aria-describedby que aponta para id inexistente: {orfas}"


def _conferir_tabelas(auditor):
    assert auditor.legendas_de_tabela == auditor.tabelas, "tabela sem <caption>"
    assert auditor.cabecalhos_sem_escopo == 0, "<th> sem scope"


def test_formulario_vazio_tem_rotulo_em_todo_campo_e_referencias_validas(client, gestor, empresa):
    client.force_login(gestor)

    auditor = _auditar(client.get(url_nova(empresa)).content.decode("utf-8"))

    assert auditor.campos, "o formulário precisa ter campos"
    _conferir_rotulos_e_referencias(auditor)


def test_erro_de_campo_e_anunciado_e_referenciado_pelo_proprio_campo(client, gestor, empresa):
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa),
        {
            "escopo": "empresa",
            "tipo": "saida_propria",
            "cfop": "5000",
            "natureza": "revenda",
            "vigencia_inicio": "01/03/2026",
            "acao": "criar",
            "competencia": "03/2026",
        },
    )

    assert resposta.status_code == 400
    auditor = _auditar(resposta.content.decode("utf-8"))
    assert "erro_cfop" in auditor.alertas, "o erro do CFOP precisa ser role=alert com id"
    assert "erro_cfop" in auditor.referencias, "o campo CFOP precisa citar o erro"
    _conferir_rotulos_e_referencias(auditor)


def test_erro_do_motivo_da_desativacao_e_associado_ao_campo(client, gestor, empresa, escritorio_a):
    regra = classificacao.criar_regra(
        escritorio=escritorio_a, empresa=None, dados=dados(), usuario=gestor
    )
    client.force_login(gestor)

    resposta = client.post(url_desativar(empresa, regra), {"motivo": ""})

    auditor = _auditar(resposta.content.decode("utf-8"))
    assert "erro_motivo" in auditor.alertas
    assert "erro_motivo" in auditor.referencias
    assert "id_motivo" in auditor.rotulos_para
    _conferir_rotulos_e_referencias(auditor)


def test_tabelas_das_telas_tem_legenda_e_cabecalho_com_escopo(
    client, gestor, empresa, escritorio_a
):
    classificacao.criar_regra(escritorio=escritorio_a, empresa=None, dados=dados(), usuario=gestor)
    client.force_login(gestor)

    lista = _auditar(client.get(url_regras(empresa)).content.decode("utf-8"))
    produto = _auditar(
        client.get(reverse("fiscal_web:classificacao_produto")).content.decode("utf-8")
    )
    fila = _auditar(client.get(url_fila(empresa)).content.decode("utf-8"))

    assert lista.tabelas == 1 and lista.cabecalhos >= 8
    _conferir_tabelas(lista)
    _conferir_tabelas(produto)
    _conferir_tabelas(fila)


def test_trilha_marca_a_tela_atual_com_aria_current(client, gestor, empresa):
    client.force_login(gestor)

    # O menu também marca o módulo ativo (um <summary>); a trilha é o <li> da própria tela.
    for url in (url_regras(empresa), url_nova(empresa), url_fila(empresa)):
        auditor = _auditar(client.get(url).content.decode("utf-8"))
        assert "li" in auditor.atual, url


def test_campos_de_filtro_da_lista_tem_rotulo(client, gestor, empresa):
    client.force_login(gestor)

    auditor = _auditar(client.get(url_regras(empresa)).content.decode("utf-8"))

    assert {"id_filtro_escopo", "id_filtro_situacao"} <= auditor.rotulos_para
    _conferir_rotulos_e_referencias(auditor)


def test_fila_com_grupo_tem_rotulo_no_campo_de_competencia_e_tabela_conferida(
    client, gestor, empresa, escritorio_a
):
    from apps.fiscal import escrituracao_nfe_lote as lote
    from apps.fiscal.tests.suporte_dl085 import nfce

    nfce(escritorio_a, gestor, numero=1, cfop="5949", csosn="102", ncm="22030000")
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    client.force_login(gestor)

    auditor = _auditar(client.get(url_fila(empresa)).content.decode("utf-8"))

    assert {"id_fila_ano", "id_fila_mes"} <= auditor.rotulos_para
    assert auditor.tabelas == 1
    _conferir_tabelas(auditor)
    _conferir_rotulos_e_referencias(auditor)
