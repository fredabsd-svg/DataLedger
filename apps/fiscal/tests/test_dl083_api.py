"""DL-083 (frente A), critério 7 de API: o que a tela vai precisar, expostos pela API.

- Escrituração: por item, `receita_do_item` e `avisos` ("item n fora do total: vProd R$ X não
  compõe a receita"; "ICMS desonerado deduzido do total: R$ X"); e as duas naturezas de combustível
  no catálogo.
- Presumido: a apuração expõe as linhas de NF-e (origem "NF-e", natureza, atividade e valor), a
  devolução deduzida e o saldo que passa.
- Permissões e isolamento, com o padrão da DL-081 e da DL-079: PARALEGAL lê; CLIENTE recebe 403;
  outra empresa do mesmo escritório e outro escritório recebem 404.

Valores de entrada escritos à mão. Dados sintéticos.
"""

import json
from datetime import date

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _json(resposta):
    return json.loads(resposta.content)


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-api-dl083")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-api-dl083")


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-api-b-dl083")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def empresa_presumido(escritorio_a, gestor):
    """Lucro Presumido em 2026. Atividade padrão: serviços gerais (32%). NF-e não usa o padrão."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API Presumida DL083 Ltda", cnpj="77888999000155"
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", gestor)
    presumido_servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        gestor,
    )
    return empresa


def _nota_com_itens_de_avisos(escritorio, gestor):
    """Três itens: 1 normal (100,00); 2 com indTot 0, vProd 50,00 e frete 10,00 (receita 10,00);
    3 com ICMS desonerado deduzido de 20,00 (receita 180,00). Total da nota: 290,00."""
    icms_deson = xml.icms(
        cst="40", filhos="<vICMSDeson>20.00</vICMSDeson><indDeduzDeson>1</indDeduzDeson>"
    )
    dets = [
        xml.det(1, vprod="100.00"),
        xml.det(2, vprod="50.00", ind_tot="0", vfrete="10.00"),
        xml.det(3, vprod="200.00", icms_xml=icms_deson),
    ]
    return receber(
        escritorio,
        gestor,
        xml.nfe(dets=dets, vnf="290.00", numero="951", emitente=("CNPJ", CNPJ_EMITENTE_A)),
    )


def _rascunho(usuario, empresa, documento, natureza=None):
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    if natureza is not None:
        NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return esc


def _itens_por_numero(corpo):
    return {item["n_item"]: item for item in corpo["itens"]}


# ---------------------------------------------------------------------------------------------
# Escrituração: receita do item, avisos e o catálogo com as duas naturezas
# ---------------------------------------------------------------------------------------------


def test_detalhe_da_escrituracao_expoe_receita_do_item_e_avisos(
    escritorio_a, gestor, empresa, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(gestor)
    resposta = client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk))
    assert resposta.status_code == 200
    itens = _itens_por_numero(_json(resposta))

    assert itens[1]["receita_do_item"] == "100.00"
    assert itens[1]["avisos"] == []

    # Item 2: o valor bruto é 60,00 (campo gravado, inalterado), e a receita é só o frete, 10,00.
    assert itens[2]["receita_bruta_item"] == "60.00"
    assert itens[2]["receita_do_item"] == "10.00"
    assert itens[2]["avisos"] == ["item 2 fora do total: vProd R$ 50,00 não compõe a receita"]

    # Item 3: 200,00 − 20,00 (ICMS desonerado deduzido) = 180,00.
    assert itens[3]["receita_do_item"] == "180.00"
    assert itens[3]["avisos"] == ["ICMS desonerado deduzido do total: R$ 20,00"]


def test_catalogo_da_escrituracao_tem_as_duas_naturezas_de_combustivel(
    escritorio_a, gestor, empresa, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(gestor)
    corpo = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)))
    catalogo = corpo["catalogo"]
    assert (
        catalogo["combustivel"]["rotulo"] == "Revenda de combustíveis para consumo (1,6% no IRPJ)"
    )
    assert catalogo["combustivel_revenda"]["rotulo"] == (
        "Revenda de combustíveis para revenda (8% no IRPJ)"
    )
    assert catalogo["combustivel_revenda"]["papel"] == "receita"
    assert "combustivel_revenda" in corpo["naturezas_permitidas"]


def test_natureza_de_combustivel_revenda_e_aceita_pela_api(escritorio_a, gestor, empresa, client):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(gestor)
    corpo = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)))
    ids = [item["item_id"] for item in corpo["itens"]]
    resposta = client.post(
        _url("nfe_escrituracao_naturezas", empresa.pk, esc.pk),
        data=json.dumps({"natureza": "combustivel_revenda", "itens": ids}),
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    assert NaturezaItemNFe.objects.filter(
        escrituracao=esc, natureza=NaturezaOperacaoNFe.COMBUSTIVEL_REVENDA
    ).count() == len(ids)


# ---------------------------------------------------------------------------------------------
# Presumido: a apuração expõe as linhas de NF-e, a devolução e o saldo
# ---------------------------------------------------------------------------------------------


def _rascunho_nfe(
    escritorio, gestor, empresa, natureza, numero, valor, dh_emi, cfop="5102", tp_nf="1", fin="1"
):
    documento = receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", empresa.cnpj),
            tp_nf=tp_nf,
            fin_nfe=fin,
        ),
    )
    return _rascunho(gestor, empresa, documento, natureza=natureza)


def test_apuracao_do_presumido_expoe_linhas_de_nfe_devolucao_e_saldo(
    escritorio_a, gestor, empresa_presumido, client
):
    esc = _rascunho_nfe(
        escritorio_a,
        gestor,
        empresa_presumido,
        NaturezaOperacaoNFe.REVENDA,
        numero=961,
        valor="5000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    servico.efetivar(esc, usuario=gestor)
    esc_comb = _rascunho_nfe(
        escritorio_a,
        gestor,
        empresa_presumido,
        NaturezaOperacaoNFe.COMBUSTIVEL,
        numero=962,
        valor="3000.00",
        dh_emi="2026-02-11T10:00:00-03:00",
        cfop="5656",
    )
    servico.efetivar(esc_comb, usuario=gestor)

    client.force_login(gestor)
    resposta = client.get(
        _url("presumido_apuracao", empresa_presumido.pk) + "?ano=2026&trimestre=1"
    )
    assert resposta.status_code == 200, resposta.content
    corpo = _json(resposta)
    assert corpo["recusas"] == []
    assert corpo["devolucao_deduzida"] == "0.00"
    assert corpo["saldo_devolucao_transportado"] == "0.00"
    linhas = [(n["origem"], n["natureza"], n["atividade"], n["valor"]) for n in corpo["nfe"]]
    assert linhas == [
        ("NF-e", "revenda", tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA, "5000.00"),
        ("NF-e", "combustivel", tab.REVENDA_COMBUSTIVEIS, "3000.00"),
    ]


def test_apuracao_com_recusa_de_nfe_nao_escriturada_responde_com_o_motivo(
    escritorio_a, gestor, empresa_presumido, client
):
    _rascunho(
        gestor,
        empresa_presumido,
        receber(
            escritorio_a,
            gestor,
            xml.nfe(
                dets=[xml.det(1, cfop="5102", vprod="800.00", icms_xml=xml.icms(csosn="102"))],
                vnf="800.00",
                totais={"vProd": "800.00"},
                numero="963",
                dh_emi="2026-02-10T10:00:00-03:00",
                emitente=("CNPJ", empresa_presumido.cnpj),
            ),
        ),
        natureza=NaturezaOperacaoNFe.REVENDA,
    )
    client.force_login(gestor)
    corpo = _json(
        client.get(_url("presumido_apuracao", empresa_presumido.pk) + "?ano=2026&trimestre=1")
    )
    assert corpo["situacao"] == "parcial"
    assert {r["codigo"]: r["mensagem"] for r in corpo["recusas"]} == {
        "nfe_nao_escriturada": "NF-e do trimestre ainda não escriturada"
    }


# ---------------------------------------------------------------------------------------------
# Permissões e isolamento
# ---------------------------------------------------------------------------------------------


def test_paralegal_le_a_escrituracao_e_a_apuracao(
    escritorio_a, gestor, paralegal, empresa, empresa_presumido, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(paralegal)
    assert client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)).status_code == 200
    assert (
        client.get(
            _url("presumido_apuracao", empresa_presumido.pk) + "?ano=2026&trimestre=1"
        ).status_code
        == 200
    )


def test_cliente_recebe_403_na_escrituracao_e_na_apuracao(
    escritorio_a, gestor, usuario_cliente_a, empresa, empresa_presumido, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(usuario_cliente_a)
    assert client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)).status_code == 403
    assert (
        client.get(
            _url("presumido_apuracao", empresa_presumido.pk) + "?ano=2026&trimestre=1"
        ).status_code
        == 403
    )


def test_outra_empresa_do_mesmo_escritorio_recebe_404(
    escritorio_a, gestor, empresa, empresa_presumido, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(gestor)
    assert (
        client.get(_url("nfe_escrituracao_detalhe", empresa_presumido.pk, esc.pk)).status_code
        == 404
    )


def test_outro_escritorio_nao_ve_a_escrituracao_nem_a_apuracao(
    escritorio_a, gestor, gestor_b, empresa, empresa_presumido, client
):
    documento = _nota_com_itens_de_avisos(escritorio_a, gestor)
    esc = _rascunho(gestor, empresa, documento)
    client.force_login(gestor_b)
    assert client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)).status_code == 404
    assert (
        client.get(
            _url("presumido_apuracao", empresa_presumido.pk) + "?ano=2026&trimestre=1"
        ).status_code
        == 404
    )
