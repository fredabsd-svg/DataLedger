"""DL-081, correção da rodada 1 (telas). A7: a tela "Receita do mês" mostra a parcela da NF-e.

A rodada 1 mostrava "Documentos escriturados 0,00 | Receita informada 0,00 | Total 2.880,00" com uma
NF-e de 2.880,00 no mês: as colunas não somavam o total. Aqui a tela é lida como HTML, e a soma das
colunas tem de ser igual ao total, de cada mercado.
"""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import fixar_inicio_de_uso, preparar_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-telas-rodada1-dl081")


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Receita Tela Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2025, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _nota(escritorio, usuario, empresa_da_nota, *, valor, natureza, numero, devolucao=False):
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[
                xml.det(
                    1,
                    cfop="1202" if devolucao else "5102",
                    vprod=valor,
                    icms_xml=xml.icms(csosn="102"),
                )
            ],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi="2026-03-15T10:00:00-03:00",
            tp_nf="0" if devolucao else "1",
            fin_nfe="4" if devolucao else "1",
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    servico.efetivar(esc, usuario=usuario)


def _valor_ptbr_para_decimal(texto: str) -> Decimal:
    """'2.880,00' -> Decimal('2880.00'). Só o texto da tela, sem float."""
    return Decimal(texto.replace(".", "").replace(",", "."))


def _linhas_da_tabela_de_mercado(html: str) -> dict[str, list[Decimal]]:
    """Cada linha da tabela 'Receita ... por mercado': rótulo do mercado e os valores das
    colunas."""
    inicio = html.index("<caption>Receita de")
    tabela = html[inicio : html.index("</table>", inicio)]
    linhas = {}
    for linha in re.findall(r"<tr>(.*?)</tr>", tabela, flags=re.S):
        rotulo = re.search(r'<th scope="row">([^<]+)</th>', linha)
        if rotulo is None:
            continue
        valores = re.findall(r'<td class="valor-monetario">([^<]+)</td>', linha)
        linhas[rotulo.group(1).strip()] = [_valor_ptbr_para_decimal(v) for v in valores]
    return linhas


def test_tela_da_receita_do_mes_soma_as_colunas_ate_o_total(escritorio_a, gestor, empresa, client):
    """Com NF-e de 2.880,00 e devolução de 300,00 no mês: NFS-e 0 + NF-e 2.880,00 + informado 0 −
    devolução deduzida 300,00 = total 2.580,00, no mercado interno. Cada linha fecha consigo."""
    _nota(escritorio_a, gestor, empresa, valor="2880.00", natureza=N.REVENDA, numero=1)
    _nota(
        escritorio_a,
        gestor,
        empresa,
        valor="300.00",
        natureza=N.DEVOLUCAO_VENDA,
        numero=2,
        devolucao=True,
    )
    client.force_login(gestor)
    resposta = client.get(
        reverse("fiscal_web:receita_do_mes"), {"empresa": empresa.pk, "ano": 2026, "mes": 3}
    )
    assert resposta.status_code == 200
    linhas = _linhas_da_tabela_de_mercado(resposta.content.decode())

    interno = linhas["Mercado interno"]
    # Colunas: NFS-e, NF-e de saída, receita informada, devolução deduzida, total do mês.
    documentos, nfe, informado, devolucao, total = interno
    assert nfe == Decimal("2880.00")
    assert devolucao == Decimal("300.00")
    assert total == Decimal("2580.00")
    assert documentos + nfe + informado - devolucao == total
