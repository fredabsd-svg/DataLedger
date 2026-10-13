"""DL-091 (frente B): tela "Conferência de entradas do mês" (classe conferência, sem impressão).

Cenário sintético de março/2026. Os totais esperados foram escritos À MÃO antes de rodar o código
(a mesma lista de totais do teste de serviço `test_dl091_conferencia_entradas`):

  n1  5.102 → E1 (1.102), vProd 100,00, vICMS 18,00 CST 00, regime normal → crédito destacado 18,00
  n2  5.556 → E4 (1.556), vProd 200,00, vICMS 18,00 CST 00, de SP para TO → vedado, aviso de DIFAL
  n3  5.405 com ST (CST 60, vICMSSTRet 7,00) → E3 (1.403), vProd 300,00, ST retido 7,00
  n4  rascunho (sem natureza) → a escriturar
  n5  devolução de venda recebida (finNFe 4) → fora, com o motivo nomeado
  Outra empresa do MESMO escritório com uma compra de 999,00 → não entra (isolamento).

Esperado na tela:
  recebidas 5; escrituradas 3; a escriturar 1; fora 1.
  por natureza: E1 1 item 100,00; E3 1 item 300,00; E4 1 item 200,00.
  por CFOP de entrada: 1.102 → 100,00; 1.403 → 300,00; 1.556 → 200,00.
  crédito destacado elegível 18,00; ST retido 7,00 (1 item).
  marcas: crédito destacado 1 (18,00); vedado até 2032 1 (0,00); ST retido 1 (0,00).
  aviso de outro estado: só n2.
"""

import html
import re
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import conferencia_entradas as conferencia
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import (
    EscrituracaoNFe,
)
from apps.fiscal.models import (
    NaturezaOperacaoNFe as N,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.test_dl091_entradas import (
    _com_regime,
    _confirmar,
    _matriz,
    _nota,
    _rascunho,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

MARCO = {"ano": 2026, "mes": 3}
DH_MARCO = "2026-03-10T10:00:00-03:00"


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora conferência DL091 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)
    return empresa


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa):
    """As notas de março da tabela do topo, com cada efetivação feita pelo serviço da A1."""
    n1 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3101",
        cfop="5102",
        vprod="100.00",
        dh_emi=DH_MARCO,
    )
    _confirmar(n1, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(n1, usuario=usuario_gestor_a)

    n2 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3102",
        cfop="5556",
        vprod="200.00",
        dh_emi=DH_MARCO,
    )
    _confirmar(n2, N.ENTRADA_USO_CONSUMO, "1556", usuario_gestor_a)
    servico.efetivar(n2, usuario=usuario_gestor_a)

    icms_st = xml.icms(cst="60", filhos="<vBCSTRet>50.00</vBCSTRet><vICMSSTRet>7.00</vICMSSTRet>")
    n3 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3103",
        cfop="5405",
        vprod="300.00",
        icms=icms_st,
        dh_emi=DH_MARCO,
    )
    _confirmar(n3, N.ENTRADA_ST, "1403", usuario_gestor_a)
    servico.efetivar(n3, usuario=usuario_gestor_a)

    _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3104",
        cfop="5102",
        vprod="50.00",
        dh_emi=DH_MARCO,
    )
    # Devolução de venda RECEBIDA: a empresa é a destinatária (emitente é terceiro), finNFe 4.
    _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="3105",
        cfop="6202",
        fin_nfe="4",
        vprod="30.00",
        dh_emi=DH_MARCO,
    )
    return {"n1": n1, "n2": n2, "n3": n3}


def _url(empresa, **consulta):
    base = {"ano": 2026, "mes": 3}
    base.update(consulta)
    return (
        reverse("fiscal_web:nfe_conferencia_entradas", args=[empresa.pk])
        + "?"
        + ("&".join(f"{chave}={valor}" for chave, valor in base.items()))
    )


def _texto(resposta):
    return " ".join(html.unescape(resposta.content.decode("utf-8")).split())


def test_conferencia_de_entradas_bate_com_o_servico_e_tem_legenda_e_cabecalhos(
    client, usuario_gestor_a, empresa, cenario
):
    client.force_login(usuario_gestor_a)

    resposta = client.get(_url(empresa))
    texto = _texto(resposta)
    servico_mes = conferencia.conferencia_de_entradas(empresa, 2026, 3)

    assert resposta.status_code == 200
    # Números escritos à mão (a tabela do topo do módulo), conferidos contra o serviço.
    assert servico_mes.recebidas == 5 and servico_mes.escrituradas == 3
    assert servico_mes.a_escriturar == 1 and len(servico_mes.fora) == 1
    assert 'Recebidas no mês (empresa destinatária)</th> <td class="valor-monetario">5</td>' in (
        texto
    )
    assert 'class="valor-monetario">3</td>' in texto
    assert "Compras efetivadas, por natureza" in texto
    assert 'E1 · Compra para comercialização</th> <td class="valor-monetario">1</td>' in texto
    assert "E3 · Compra com ICMS-ST (substituído)</th>" in texto
    assert "E4 · Compra para uso ou consumo</th>" in texto
    assert '1.102</th> <td class="valor-monetario">1</td> <td class="valor-monetario">100,00' in (
        texto
    )
    assert '1.403</th> <td class="valor-monetario">1</td> <td class="valor-monetario">300,00' in (
        texto
    )
    assert '1.556</th> <td class="valor-monetario">1</td> <td class="valor-monetario">200,00' in (
        texto
    )
    assert "Crédito destacado elegível" in texto and ">18,00</td>" in texto
    assert "ICMS-ST retido (vICMSSTRet), sem crédito e compondo o custo: 1 item(ns)" in texto
    assert ">7,00</td>" in texto
    assert "Crédito destacado: elegível (LC 87, art. 20)</th>" in texto
    assert "Crédito vedado até 31/12/2032 (LC 87, art. 33, I)</th>" in texto
    assert "possível DIFAL (CF art. 155, § 2º, VII e VIII, não conferido)" in texto
    assert "Devolução de venda recebida" in texto
    assert "devolução de venda recebida (finNFe 4): fica na escrituração de saída" in texto
    # Legenda e cabeçalhos: cada tabela tem caption e cabeçalho de coluna.
    assert texto.count("<caption>") == texto.count("<table")
    assert texto.count('<th scope="col">') >= 8
    # Trilha: a tela atual é texto, com aria-current, e não link para ela mesma.
    assert '<li aria-current="page">Conferência de entradas</li>' in texto


def test_conferencia_nao_mostra_compra_de_outra_empresa_do_mesmo_escritorio(
    client, usuario_gestor_a, escritorio_a, empresa, cenario
):
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra compradora DL091", cnpj="77888999000155"
    )
    _rascunho(
        escritorio_a,
        usuario_gestor_a,
        outra,
        numero="9001",
        cfop="5102",
        vprod="999.00",
        dh_emi=DH_MARCO,
        destinatario=("CNPJ", "77888999000155"),
    )
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url(empresa)))

    assert "999,00" not in texto


def test_conferencia_de_entradas_vazia_mostra_o_estado_vazio(
    client, usuario_gestor_a, escritorio_a, empresa
):
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url(empresa, ano=2025, mes=1)))

    assert "Nenhuma NF-e recebida pela empresa em 01/2025." in texto
    assert "estado-vazio" in texto
    assert "<table" not in texto


def test_conferencia_de_entradas_de_outro_escritorio_responde_404(
    client, escritorio_b, empresa, cenario
):
    usuario_de_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-conferencia-dl091")
    client.force_login(usuario_de_b)

    assert client.get(_url(empresa)).status_code == 404


def test_conferencia_de_entradas_sem_permissao_responde_403_e_paralegal_le(
    client, escritorio_a, empresa, cenario
):
    cliente = usuario_com_papel(escritorio_a, Papel.CLIENTE, "cliente-conferencia-dl091")
    paralegal = usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-conferencia-dl091")

    client.force_login(cliente)
    assert client.get(_url(empresa)).status_code == 403
    client.force_login(paralegal)
    assert client.get(_url(empresa)).status_code == 200


def test_conferencia_de_entradas_nao_altera_estado(client, usuario_gestor_a, empresa, cenario):
    client.force_login(usuario_gestor_a)
    antes = EscrituracaoNFe.objects.count()

    client.get(_url(empresa))

    assert EscrituracaoNFe.objects.count() == antes


def test_conferencia_de_entradas_nao_tem_timbre_de_impressao(
    client, usuario_gestor_a, empresa, cenario
):
    client.force_login(usuario_gestor_a)

    texto = _texto(client.get(_url(empresa)))

    assert "não é livro de entradas" in texto.lower() or "não é livro registro" in texto.lower()
    assert "timbre-impressao" not in texto
    assert re.search(r"<h1>Conferência de entradas do mês</h1>", texto)
    assert (
        Decimal("18.00")
        == conferencia.conferencia_de_entradas(empresa, 2026, 3).credito_destacado_elegivel
    )
