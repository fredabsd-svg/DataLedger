"""DL-091, correção da rodada 1, A9 (T14): o número de consultas da tela e da API da compra não
cresce
com o número de itens.

Antes da correção, a prévia da memória lia o regime da data de entrada por item, e o detalhe da API
lia a memória de cada item: uma nota de 30 itens custava dezenas de consultas a mais que uma de 2.
O teste mede as consultas de uma nota de 2 itens e de uma de 30, no rascunho e na efetivada, e exige
que a diferença fique em no máximo 5.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe

pytestmark = pytest.mark.django_db

ICMS_10 = "<modBC>3</modBC><vBC>10.00</vBC><pICMS>18.00</pICMS><vICMS>1.80</vICMS>"
FOLGA = 5  # consultas a mais que a nota de 30 itens pode ter em relação à de 2 itens


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Consultas rodada 1 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio="2026-01-01"
    )
    return empresa


def _compra_com_itens(escritorio, usuario, empresa, *, numero, quantidade):
    """Compra sintética de `quantidade` itens, cada um de 10,00, CFOP 5.102, CST 00, CRT 3."""
    dets = [
        xml.det(
            n,
            cfop="5102",
            vprod="10.00",
            ncm="22030000",
            icms_xml=xml.icms(cst="00", filhos=ICMS_10),
        )
        for n in range(1, quantidade + 1)
    ]
    total = f"{10 * quantidade:.2f}"
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=dets,
            vnf=total,
            totais={"vProd": total},
            chave=chave_nfe(cuf="35", emitente=CNPJ_EMITENTE_A, modelo="55", numero=numero),
            numero=numero,
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", empresa.cnpj),
            crt="3",
        ),
    )
    ler_itens(documento)
    return documento


def _rascunho_confirmado(documento, empresa, usuario):
    """Rascunho com a natureza e o CFOP de entrada de todos os itens, como a tela e a API deixam."""
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    entradas.definir_natureza_de_entrada(
        esc, N.ENTRADA_COMERCIALIZACAO, "1102", ids, usuario=usuario
    )
    return esc


def _consultas(client, url):
    """Número de consultas de uma leitura. Uma leitura antes aquece o que a sessão cacheia."""
    client.get(url)
    with CaptureQueriesContext(connection) as contexto:
        resposta = client.get(url)
    assert resposta.status_code == 200, resposta.status_code
    return len(contexto.captured_queries)


def _enderecos(empresa, esc, documento):
    return {
        "tela": reverse(
            "fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk]
        ),
        "api": reverse("fiscal_api:nfe_escrituracao_detalhe", args=[empresa.pk, esc.pk]),
    }


def test_consultas_da_tela_e_da_api_nao_crescem_com_o_numero_de_itens(
    client, escritorio_a, usuario_gestor_a, empresa
):
    """T14: 2 itens contra 30, no rascunho (com a prévia da memória) e na efetivada (com a
    memória)."""
    pequena = _compra_com_itens(
        escritorio_a, usuario_gestor_a, empresa, numero="1401", quantidade=2
    )
    grande = _compra_com_itens(
        escritorio_a, usuario_gestor_a, empresa, numero="1402", quantidade=30
    )
    esc_pequena = _rascunho_confirmado(pequena, empresa, usuario_gestor_a)
    esc_grande = _rascunho_confirmado(grande, empresa, usuario_gestor_a)
    client.force_login(usuario_gestor_a)
    enderecos = {
        "pequena": _enderecos(empresa, esc_pequena, pequena),
        "grande": _enderecos(empresa, esc_grande, grande),
    }

    def medir():
        return {
            (quem, tela): _consultas(client, enderecos[quem][tela])
            for quem in enderecos
            for tela in ("tela", "api")
        }

    no_rascunho = medir()
    servico.efetivar(esc_pequena, usuario=usuario_gestor_a)
    servico.efetivar(esc_grande, usuario=usuario_gestor_a)
    na_efetivada = medir()

    for tela in ("tela", "api"):
        assert no_rascunho[("grande", tela)] - no_rascunho[("pequena", tela)] <= FOLGA, (
            tela,
            "rascunho",
            no_rascunho,
        )
        assert na_efetivada[("grande", tela)] - na_efetivada[("pequena", tela)] <= FOLGA, (
            tela,
            "efetivada",
            na_efetivada,
        )


def test_api_devolve_a_memoria_de_cada_item_na_efetivada(
    client, escritorio_a, usuario_gestor_a, empresa
):
    """A API efetivada traz a memória de TODOS os itens (não só do primeiro), com o crédito do ICMS
    de 1,80 em cada um, lido em lote."""
    documento = _compra_com_itens(
        escritorio_a, usuario_gestor_a, empresa, numero="1403", quantidade=3
    )
    esc = _rascunho_confirmado(documento, empresa, usuario_gestor_a)
    servico.efetivar(esc, usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    corpo = json.loads(
        client.get(
            reverse("fiscal_api:nfe_escrituracao_detalhe", args=[empresa.pk, esc.pk])
        ).content
    )

    assert [item["memoria"]["fonte"] for item in corpo["itens"]] == ["efetivada"] * 3
    assert all(item["memoria"]["credito_elegivel"] == "1.80" for item in corpo["itens"])
