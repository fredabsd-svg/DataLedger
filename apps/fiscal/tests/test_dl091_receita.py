"""DL-091 (frente A1), critério 1: nenhuma entrada mexe em receita, RBT12, pré-DAS, Presumido nem
IRPJ/CSLL, e a devolução de compra não entra no saldo de devolução do Simples (art. 17).

O teste é escrito à mão: a mesma empresa, com as mesmas vendas, é apurada ANTES e DEPOIS de
escriturar compras (e uma devolução de compra). O resultado tem de ser idêntico campo a campo. Os
valores de venda são sintéticos. Nada aqui é alíquota: a comparação é só de igualdade.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import pre_das as pre_das_servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import receita as receita_servico
from apps.fiscal.itens_nfe import ler_itens
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    fixar_inicio_de_uso,
    preparar_simples,
    sequencia,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A, chave_nfe
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-dl091-receita")


def _nota(
    escritorio,
    usuario,
    *,
    numero,
    cnpj_emitente,
    cnpj_destinatario,
    cfop,
    vprod,
    tp_nf,
    fin_nfe="1",
    csosn="102",
    icms=None,
    dh_emi="2026-03-15T10:00:00-03:00",
):
    chave = chave_nfe(cuf="35", emitente=cnpj_emitente, modelo="55", numero=numero)
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[xml.det(1, cfop=cfop, vprod=vprod, icms_xml=icms or xml.icms(csosn=csosn))],
            vnf=vprod,
            totais={"vProd": vprod},
            chave=chave,
            numero=numero,
            tp_nf=tp_nf,
            fin_nfe=fin_nfe,
            dh_emi=dh_emi,
            emitente=("CNPJ", cnpj_emitente),
            destinatario=("CNPJ", cnpj_destinatario),
        ),
    )
    ler_itens(documento)
    return documento


def _efetivar(documento, empresa, usuario, natureza, *, data_entrada=None):
    """Escriturada pelo serviço real. A entrada recebe o CFOP de entrada do grupo da natureza."""
    from apps.fiscal import entradas

    esc = servico.criar_rascunho(
        vinculo(documento, empresa), usuario=usuario, data_entrada=data_entrada
    )
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    if esc.tipo == "entrada":
        # O CFOP de entrada sai do CFOP do emitente: primeiro dígito 5→1, 6→2, 7→3; grupo da
        # natureza.
        emitente = esc.vinculo.documento.itens.get(n_item=1).cfop
        cfop_entrada = entradas.PRIMEIRO_DIGITO_DA_ENTRADA[emitente[0]] + emitente[1:]
        entradas.definir_natureza_de_entrada(esc, natureza, cfop_entrada, ids, usuario=usuario)
    else:
        servico.definir_natureza(esc, natureza, ids, usuario=usuario)
    return servico.efetivar(esc, usuario=usuario)


def _vendas_do_simples(escritorio, usuario, empresa):
    """Duas vendas de março (a empresa é a emitente, saída própria, CSOSN 102)."""
    for numero, vprod in (("101", "10000.00"), ("102", "2500.00")):
        documento = _nota(
            escritorio,
            usuario,
            numero=numero,
            cnpj_emitente=CNPJ_EMITENTE_A,
            cnpj_destinatario=CNPJ_DESTINATARIO_A,
            cfop="5102",
            vprod=vprod,
            tp_nf="1",
        )
        _efetivar(documento, empresa, usuario, N.REVENDA)


def _compras(escritorio, usuario, empresa):
    """Compras escrituradas: duas em março e uma de fevereiro com data de entrada em março."""
    for numero, vprod, data_emi, entrada in (
        ("201", "4000.00", "2026-03-10T10:00:00-03:00", None),
        ("202", "900.00", "2026-03-20T10:00:00-03:00", None),
        ("203", "1200.00", "2026-02-27T10:00:00-03:00", date(2026, 3, 2)),
    ):
        documento = _nota(
            escritorio,
            usuario,
            numero=numero,
            cnpj_emitente=CNPJ_DESTINATARIO_A,
            cnpj_destinatario=CNPJ_EMITENTE_A,
            cfop="6102",
            vprod=vprod,
            tp_nf="1",
            dh_emi=data_emi,
            icms=xml.icms(cst="00", filhos=_icms_00(vprod)),
        )
        _efetivar(documento, empresa, usuario, N.ENTRADA_COMERCIALIZACAO, data_entrada=entrada)


def _icms_00(vprod: str) -> str:
    """ICMS destacado de 12%, com duas casas (o leitor confere o padrão de valor do XSD)."""
    vicms = (Decimal(vprod) * Decimal("0.12")).quantize(Decimal("0.01"))
    return f"<modBC>3</modBC><vBC>{vprod}</vBC><pICMS>12.00</pICMS><vICMS>{vicms}</vICMS>"


def _devolucao_de_compra(escritorio, usuario, empresa):
    """Devolução de compra (saída própria, CFOP 5.202, indDevol 1) de 300,00 em março."""
    documento = _nota(
        escritorio,
        usuario,
        numero="301",
        cnpj_emitente=CNPJ_EMITENTE_A,
        cnpj_destinatario=CNPJ_DESTINATARIO_A,
        cfop="5202",
        vprod="300.00",
        tp_nf="1",
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, N.DEVOLUCAO_COMPRA, ids, usuario=usuario)
    return servico.efetivar(esc, usuario=usuario)


# ---------------------------------------------------------------------------
# Simples: receita, RBT12, pré-DAS e saldo de devolução (art. 17)
# ---------------------------------------------------------------------------


@pytest.fixture
def simples(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Simples DL091 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2025, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _fotografia_do_simples(empresa):
    """O que o Simples lê: receita do período (por linha da NF-e), RBT12 e o pré-DAS de março."""
    linhas = receita_servico.linhas_nfe_do_periodo(empresa, (2026, 1), (2026, 3))
    pre = pre_das_servico.pre_das(empresa, 2026, 3)
    return {
        "linhas": [
            (linha.natureza, linha.papel, linha.valor, linha.competencia) for linha in linhas
        ],
        "rbt12": pre.rbt12,
        "total_do_das": pre.total,
        "anexos": pre.anexos,
        "devolucao_deduzida_no_periodo": receita_servico._primeiro_mes_com_devolucao(empresa),
    }


def test_simples_receita_rbt12_pre_das_e_saldo_nao_mudam_com_compras(escritorio_a, gestor, simples):
    """Vendas e devolução de compra antes de confirmar; depois, as compras. Os meses ficam
    confirmados, e a compra escriturada NÃO os reabre (a entrada não é gatilho de receita)."""
    _vendas_do_simples(escritorio_a, gestor, simples)
    _devolucao_de_compra(escritorio_a, gestor, simples)
    confirmar_meses(simples, gestor, sequencia(2025, 3, 13))
    antes = _fotografia_do_simples(simples)
    assert antes["linhas"], "sem vendas, o teste não prova nada"

    _compras(escritorio_a, gestor, simples)
    depois = _fotografia_do_simples(simples)

    assert depois == antes
    # A devolução de compra não abriu saldo de devolução do art. 17: nenhum mês com devolução.
    assert depois["devolucao_deduzida_no_periodo"] is None


def test_compra_com_data_de_entrada_em_outro_mes_nao_muda_o_mes_da_receita(
    escritorio_a, gestor, simples
):
    _vendas_do_simples(escritorio_a, gestor, simples)
    confirmar_meses(simples, gestor, sequencia(2025, 3, 13))
    antes = _fotografia_do_simples(simples)
    _compras(escritorio_a, gestor, simples)
    depois = _fotografia_do_simples(simples)
    assert depois["linhas"] == antes["linhas"]
    assert depois["total_do_das"] == antes["total_do_das"]


# ---------------------------------------------------------------------------
# Lucro Presumido: receita, IRPJ e CSLL
# ---------------------------------------------------------------------------


@pytest.fixture
def presumido(escritorio_a, gestor):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumido DL091 Ltda", cnpj=CNPJ_EMITENTE_A
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


def _apuracao_do_presumido(empresa):
    apuracao = presumido_servico.apurar_trimestre(empresa, 2026, 1)
    return {
        "situacao": apuracao.situacao,
        "recusas": apuracao.recusas,
        "receitas": apuracao.receitas,
        "nfe": apuracao.nfe,
        "devolucao_deduzida": apuracao.devolucao_deduzida,
        "irpj": apuracao.irpj,
        "csll": apuracao.csll,
    }


def test_presumido_receita_irpj_e_csll_nao_mudam_com_compras(escritorio_a, gestor, presumido):
    _vendas_do_simples(escritorio_a, gestor, presumido)
    antes = _apuracao_do_presumido(presumido)
    assert antes["nfe"], "sem vendas, o teste não prova nada"

    _compras(escritorio_a, gestor, presumido)
    _devolucao_de_compra(escritorio_a, gestor, presumido)
    depois = _apuracao_do_presumido(presumido)

    assert depois == antes
    assert depois["devolucao_deduzida"] == Decimal("0.00")


def test_compra_nao_escriturada_nao_bloqueia_o_presumido(escritorio_a, gestor, presumido):
    """A NF-e de entrada recebida e ainda não escriturada NÃO é recusa do trimestre (critério 1)."""
    _vendas_do_simples(escritorio_a, gestor, presumido)
    antes = _apuracao_do_presumido(presumido)
    _nota(
        escritorio_a,
        gestor,
        numero="401",
        cnpj_emitente=CNPJ_DESTINATARIO_A,
        cnpj_destinatario=CNPJ_EMITENTE_A,
        cfop="6102",
        vprod="700.00",
        tp_nf="1",
    )
    depois = _apuracao_do_presumido(presumido)
    assert depois["recusas"] == antes["recusas"]
    assert not any(recusa.codigo == "nfe_nao_escriturada" for recusa in depois["recusas"])


def test_natureza_nao_receita_de_entrada_nao_entra_em_linhas_de_receita(
    escritorio_a, gestor, simples
):
    """A linha da compra existe na escrituração, mas nenhuma linha de receita ou dedução a leva."""
    _compras(escritorio_a, gestor, simples)
    assert receita_servico.linhas_nfe_do_periodo(simples, (2026, 1), (2026, 3)) == []


def test_devolucao_de_compra_nao_entra_em_linhas_nem_em_parcelas_de_deducao(
    escritorio_a, gestor, simples
):
    """A devolução de compra é saída, mas NÃO é dedução de venda: as linhas de receita e as parcelas
    de dedução (que alimentam o saldo do art. 17) ficam idênticas com e sem ela."""
    _vendas_do_simples(escritorio_a, gestor, simples)
    linhas_antes = receita_servico.linhas_nfe_do_periodo(simples, (2026, 1), (2026, 3))
    parcelas_antes = receita_servico._parcelas_do_periodo(simples, (2026, 1), (2026, 3))
    _devolucao_de_compra(escritorio_a, gestor, simples)
    assert receita_servico.linhas_nfe_do_periodo(simples, (2026, 1), (2026, 3)) == linhas_antes
    assert receita_servico._parcelas_do_periodo(simples, (2026, 1), (2026, 3)) == parcelas_antes
