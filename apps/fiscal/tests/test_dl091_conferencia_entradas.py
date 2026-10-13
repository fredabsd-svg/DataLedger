"""DL-091 (frente A2): conferência das entradas do mês (serviço e API).

Cenário sintético de março/2026, com TODOS os totais calculados à mão antes de rodar o código (o
critério 9 da DL-091 pede isto: "teste escrito à mão"). A conferência é só leitura, classe
"conferência": não é impressão oficial nem livro.

Notas da empresa (destinatária), em março, com a memória que cada uma deve gerar:
  n1  5.102 → E1 (1.102), vprod 100,00, vICMS 18,00 CST 00, regime normal → crédito destacado 18,00
  n2  5.556 → E4 (1.556), vprod 200,00, vICMS 18,00 CST 00 → crédito VEDADO, aviso de DIFAL
     (SP → TO)
  n3  5.102 de fornecedor do Simples (CRT 1, vCredICMSSN 5,00, pCredSN) → E1 (1.102), crédito 5,00
  n4  5.405 com ST (CST 60, vICMSSTRet 7,00) → E3 (1.403), vprod 300,00, ST retido, sem crédito
  n5  rascunho (sem natureza) → a escriturar
  n6  devolução de venda recebida (finNFe 4) → fora, com o motivo da devolução
  n7  NFC-e em que a empresa é destinatária → fora, com o motivo nomeado
  Outra empresa do mesmo escritório, com uma compra de 999,00 → NÃO entra (isolamento).

Totais esperados:
  recebidas 7 (n1..n7); escrituradas 4; a escriturar 1; fora 2.
  por natureza: entrada_comercializacao 2 itens = 150,00; entrada_st 1 = 300,00; entrada_uso_consumo
  1 = 200,00.
  por CFOP de entrada: 1102 → 2 itens = 150,00; 1403 → 1 = 300,00; 1556 → 1 = 200,00.
  crédito destacado elegível: 18,00 + 5,00 = 23,00. Por marca: destacado 1 (18,00),
  limitado 1 (5,00), ST retido 1 (0,00), vedado 1 (0,00). ST retido: 7,00 (1 item).
  avisos de outro estado: só n2.
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, RegimeTributario
from apps.fiscal import conferencia_entradas as conferencia
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import MarcaCreditoEntrada
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl091_entradas import (
    ICMS_00,
    _com_regime,
    _confirmar,
    _matriz,
    _nota,
    _rascunho,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DE_FORA, CNPJ_DESTINATARIO_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

MARCO = {"ano": 2026, "mes": 3}


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Compradora conferência A2 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa):
    """Monta o cenário de março. A empresa é do regime normal, com matriz no Tocantins."""
    _matriz(empresa, escritorio_a, "TO")
    _com_regime(empresa, RegimeTributario.LUCRO_PRESUMIDO)

    n1 = _rascunho(
        escritorio_a, usuario_gestor_a, empresa, numero="2001", cfop="5102", vprod="100.00"
    )
    _confirmar(n1, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(n1, usuario=usuario_gestor_a)

    n2 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="2002",
        cfop="5556",
        ncm="22030000",
        vprod="200.00",
    )
    _confirmar(n2, N.ENTRADA_USO_CONSUMO, "1556", usuario_gestor_a)
    servico.efetivar(n2, usuario=usuario_gestor_a)

    n3 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="2003",
        cfop="5102",
        crt="1",
        icms=xml.icms(
            csosn="101", filhos="<pCredSN>2.8000</pCredSN><vCredICMSSN>5.00</vCredICMSSN>"
        ),
        vprod="50.00",
    )
    _confirmar(n3, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(n3, usuario=usuario_gestor_a)

    n4 = _rascunho(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="2004",
        cfop="5405",
        vprod="300.00",
        icms=xml.icms(cst="60", filhos="<vBCSTRet>100.00</vBCSTRet><vICMSSTRet>7.00</vICMSSTRet>"),
    )
    _confirmar(n4, N.ENTRADA_ST, "1403", usuario_gestor_a)
    servico.efetivar(n4, usuario=usuario_gestor_a)

    _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="2005", cfop="5102", vprod="10.00")

    _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="2006",
        fin_nfe="4",
        tp_nf="1",
        vprod="30.00",
    )
    _nota(escritorio_a, usuario_gestor_a, empresa, numero="2007", modelo="65", vprod="40.00")

    # Outra empresa do MESMO escritório: a compra dela não pode entrar na conferência desta.
    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra cliente A2 Ltda", cnpj=CNPJ_DE_FORA
    )
    # Efetivada, com natureza e memória: se a conferência somasse escrituração de outra empresa, o
    # valor e o crédito dela apareceriam aqui (mutante "soma de outra empresa").
    compra_alheia = _nota(
        escritorio_a,
        usuario_gestor_a,
        outra,
        numero="2099",
        vprod="999.00",
        destinatario=("CNPJ", CNPJ_DE_FORA),
        icms=xml.icms(cst="00", filhos=ICMS_00),
    )
    alheia = _rascunho_de(escritorio_a, usuario_gestor_a, outra, compra_alheia)
    _confirmar(alheia, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(alheia, usuario=usuario_gestor_a)
    return empresa


def _rascunho_de(escritorio, usuario, empresa, documento):
    """Rascunho de uma nota que já foi recebida (a fábrica `_rascunho` recebe de novo)."""
    return servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)


def _por_chave(linhas):
    return {linha.chave: linha for linha in linhas}


def test_contagens_recebidas_escrituradas_a_escriturar_e_fora(cenario):
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)

    assert resultado.recebidas == 7
    assert resultado.escrituradas == 4
    assert resultado.a_escriturar == 1
    assert len(resultado.fora) == 2


def test_fora_traz_o_motivo_nomeado_de_cada_nota(cenario):
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)

    motivos = {nota.numero: nota.codigo for nota in resultado.fora}
    assert motivos == {
        "2006": conferencia.CODIGO_DEVOLUCAO_DE_VENDA,
        "2007": conferencia.CODIGO_FORA_DA_ESCRITURACAO,
    }
    nfce = next(nota for nota in resultado.fora if nota.numero == "2007")
    assert "NFC-e" in nfce.motivo


def test_totais_por_natureza_e_por_cfop_de_entrada_batem_com_a_mao(cenario):
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)

    por_natureza = _por_chave(resultado.por_natureza)
    assert set(por_natureza) == {
        N.ENTRADA_COMERCIALIZACAO,
        N.ENTRADA_ST,
        N.ENTRADA_USO_CONSUMO,
    }
    assert (
        por_natureza[N.ENTRADA_COMERCIALIZACAO].itens,
        por_natureza[N.ENTRADA_COMERCIALIZACAO].valor,
    ) == (2, Decimal("150.00"))
    assert (por_natureza[N.ENTRADA_ST].itens, por_natureza[N.ENTRADA_ST].valor) == (
        1,
        Decimal("300.00"),
    )
    assert (
        por_natureza[N.ENTRADA_USO_CONSUMO].itens,
        por_natureza[N.ENTRADA_USO_CONSUMO].valor,
    ) == (1, Decimal("200.00"))

    por_cfop = _por_chave(resultado.por_cfop_de_entrada)
    assert (por_cfop["1102"].itens, por_cfop["1102"].valor) == (2, Decimal("150.00"))
    assert (por_cfop["1403"].itens, por_cfop["1403"].valor) == (1, Decimal("300.00"))
    assert (por_cfop["1556"].itens, por_cfop["1556"].valor) == (1, Decimal("200.00"))


def test_credito_elegivel_e_st_retido_batem_com_a_mao(cenario):
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)

    assert resultado.credito_destacado_elegivel == Decimal("23.00")
    por_marca = {t.marca: t for t in resultado.por_marca}
    assert por_marca[MarcaCreditoEntrada.CREDITO_DESTACADO].credito == Decimal("18.00")
    assert por_marca[MarcaCreditoEntrada.CREDITO_LIMITADO].credito == Decimal("5.00")
    assert por_marca[MarcaCreditoEntrada.VEDADO_ATE_2032].credito == Decimal("0.00")
    assert por_marca[MarcaCreditoEntrada.VEDADO_ATE_2032].itens == 1
    assert por_marca[MarcaCreditoEntrada.ST_RETIDO].itens == 1
    assert resultado.st_retido == Decimal("7.00")
    assert resultado.itens_com_st_retido == 1


def test_so_a_nota_com_diferencial_aparece_na_lista_de_outro_estado(cenario):
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)

    assert [nota.numero for nota in resultado.notas_com_aviso_de_outro_estado] == ["2002"]
    aviso = resultado.notas_com_aviso_de_outro_estado[0].avisos
    assert aviso == (entradas.AVISO_NORMAL_OUTRO_ESTADO_USO,)


def test_a_compra_de_outra_empresa_nao_entra_e_a_conferencia_nao_grava_nada(
    cenario, usuario_gestor_a
):
    from apps.fiscal.models import EscrituracaoNFe

    antes = EscrituracaoNFe.objects.count()
    resultado = conferencia.conferencia_de_entradas(cenario, **MARCO)
    assert EscrituracaoNFe.objects.count() == antes
    assert resultado.recebidas == 7
    assert "2099" not in {nota.numero for nota in resultado.fora}


# ---------------------------------------------------------------------------
# API: leitura por empresa, com permissão no servidor
# ---------------------------------------------------------------------------


def _url(empresa):
    return reverse("fiscal_api:nfe_conferencia_entradas", args=[empresa.pk])


def test_api_devolve_os_mesmos_totais_do_servico(client, cenario, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url(cenario), {"ano": 2026, "mes": 3})

    assert resposta.status_code == 200
    corpo = json.loads(resposta.content)
    assert corpo["classe"] == "conferencia"
    assert (corpo["recebidas"], corpo["escrituradas"], corpo["a_escriturar"]) == (7, 4, 1)
    assert corpo["fora"]["total"] == 2
    assert corpo["credito_destacado_elegivel"] == "23.00"
    assert corpo["st_retido"] == "7.00"
    assert {n["natureza"]: n["valor"] for n in corpo["por_natureza"]} == {
        N.ENTRADA_COMERCIALIZACAO: "150.00",
        N.ENTRADA_ST: "300.00",
        N.ENTRADA_USO_CONSUMO: "200.00",
    }
    assert [n["numero"] for n in corpo["notas_com_aviso_de_outro_estado"]] == ["2002"]


def test_api_nega_quem_nao_consulta_o_fiscal(client, cenario, usuario_cliente_a):
    client.force_login(usuario_cliente_a)
    assert client.get(_url(cenario), {"ano": 2026, "mes": 3}).status_code == 403


def test_api_responde_404_para_empresa_de_outro_escritorio(client, cenario, escritorio_b):
    gestor_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-conferencia-b")
    client.force_login(gestor_b)
    assert client.get(_url(cenario), {"ano": 2026, "mes": 3}).status_code == 404
