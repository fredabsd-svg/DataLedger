"""DL-083 (A1, A6; HI-139 e HI-140): devolução de combustível recebida e própria, e o NCM na
sugestão.

- A1: a devolução RECEBIDA (CFOP 5.660 a 5.662 e 6.660 a 6.662, empresa destinatária) é
  reconhecida. A
  recusa `devolucao_combustivel` saiu: a natureza escolhida pelo contador (consumo 1,6% ou revenda
  8%)
  é o caminho, e a memória avisa quando o x.662 ficou como `devolucao_venda`.
- A6: a sugestão de combustível pelo CFOP exige NCM de combustível (lista positiva); lubrificante
  vai
  para a revenda com aviso (HI-139).
- Consulta, item 3.6: NF-e de devolução de COMPRA emitida pela própria empresa (tpNF 1, finNFe 4)
  não
  entra na escrituração e não deduz nada.

Os valores são escritos à mão. Dados sintéticos: CNPJs de teste de `xml_nfe_dl081`.
"""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import NaturezaItemNFe, PapelNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.ncm_combustivel import normalizar_ncm
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.tenancy.models import Papel

D = Decimal
COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
COMBUSTIVEIS = tab.REVENDA_COMBUSTIVEIS
GASOLINA = "27101259"
LUBRIFICANTE = "27101932"
CERVEJA = "22030000"


def _sugestao(cfop, ncm, *, fin="1", csosn="102", cst=None):
    """Sugestão de um item, com o documento e o item sintéticos. Sem banco."""
    documento = SimpleNamespace(
        fin_nfe=fin, id_dest="1", transferencia_entre_estabelecimentos=False
    )
    item = SimpleNamespace(cfop=cfop, csosn=csosn, cst=cst, ncm=ncm)
    tipo = servico.TipoEscrituracaoNFe.DEVOLUCAO if fin == "4" else "saida_propria"
    return servico.sugerir_natureza_item(documento, item, tipo)


# ---------------------------------------------------------------------------------------------
# HI-139: NCM na sugestão de VENDA
# ---------------------------------------------------------------------------------------------


def test_normalizar_ncm_aceita_com_e_sem_pontos_e_vazio():
    assert normalizar_ncm("2710.12.59") == GASOLINA
    assert normalizar_ncm(GASOLINA) == GASOLINA
    assert normalizar_ncm("") == ""
    assert normalizar_ncm(None) == ""


@pytest.mark.parametrize(
    ("cfop", "ncm", "natureza"),
    [
        ("5656", GASOLINA, N.COMBUSTIVEL),
        (
            "6656",
            "27102000",
            N.COMBUSTIVEL,
        ),  # óleo diesel B: álcool e diesel, com CFOP de combustível
        ("5656", "22071010", N.COMBUSTIVEL),  # álcool etílico: só com CFOP de combustível
        ("5655", "27101921", N.COMBUSTIVEL_REVENDA),
        ("5655", LUBRIFICANTE, N.REVENDA),
        ("5656", LUBRIFICANTE, N.REVENDA),
        ("5102", CERVEJA, N.REVENDA),  # CFOP genérico de revenda: NCM não entra
    ],
)
def test_sugestao_de_venda_com_cfop_de_combustivel_depende_do_ncm(cfop, ncm, natureza):
    assert _sugestao(cfop, ncm).natureza == natureza


def test_lubrificante_com_cfop_de_combustivel_sugere_revenda_com_o_aviso():
    """Posto com óleo de motor na pista: CFOP 5.656 ("combustíveis ou lubrificantes"), NCM
    2710.19.32.
    A sugestão é a revenda (8%), e o motivo cita o 1,6% e a Lei 9.249, art. 15, § 1º, I."""
    sugestao = _sugestao("5656", LUBRIFICANTE)
    assert sugestao.natureza == N.REVENDA
    assert "lubrificante: fora do 1,6% (Lei 9.249, art. 15, § 1º, I" in sugestao.motivo


@pytest.mark.parametrize("ncm", ["", CERVEJA])
def test_cfop_de_combustivel_com_ncm_ausente_ou_fora_da_lista_nao_tem_sugestao(ncm):
    """Sem NCM de combustível, o CFOP não basta: sem sugestão, com o motivo nomeado."""
    sugestao = _sugestao("5656", ncm)
    assert sugestao.natureza is None
    assert "CFOP de combustível com NCM ausente ou fora da lista" in sugestao.motivo


def test_posto_com_gasolina_e_lubrificante_so_sugere_o_1_6_na_gasolina():
    """Consulta, item 4: NFC-e de posto com gasolina (2710.12.59) e óleo lubrificante (2710.19.32),
    ambos CFOP 5.656 e CSOSN 500. Só a gasolina recebe a sugestão de 1,6%."""
    assert _sugestao("5656", GASOLINA, csosn="500").natureza == N.COMBUSTIVEL
    assert _sugestao("5656", LUBRIFICANTE, csosn="500").natureza == N.REVENDA


# ---------------------------------------------------------------------------------------------
# A1 / HI-140: sugestão de DEVOLUÇÃO de combustível (venda própria e recebida)
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cfop", "ncm", "natureza"),
    [
        # x.662 (consumidor final), com NCM de combustível: 1,6%.
        ("5662", GASOLINA, N.DEVOLUCAO_COMBUSTIVEL_CONSUMO),
        ("6662", "27101921", N.DEVOLUCAO_COMBUSTIVEL_CONSUMO),
        ("1662", GASOLINA, N.DEVOLUCAO_COMBUSTIVEL_CONSUMO),
        ("2662", "27111910", N.DEVOLUCAO_COMBUSTIVEL_CONSUMO),
        # x.660 e x.661 (industrialização e comercialização): revenda, 8%.
        ("5661", GASOLINA, N.DEVOLUCAO_VENDA),
        ("6660", "", N.DEVOLUCAO_VENDA),
        ("1661", GASOLINA, N.DEVOLUCAO_VENDA),
        # Lubrificante, mesmo com x.662: fora do 1,6%.
        ("5662", LUBRIFICANTE, N.DEVOLUCAO_VENDA),
    ],
)
def test_sugestao_de_devolucao_de_combustivel_pela_destinacao_e_pelo_ncm(cfop, ncm, natureza):
    assert _sugestao(cfop, ncm, fin="4").natureza == natureza


def test_x_662_sem_ncm_de_combustivel_nao_tem_sugestao():
    sugestao = _sugestao("5662", "", fin="4")
    assert sugestao.natureza is None
    assert "NCM ausente ou fora da lista de combustível" in sugestao.motivo


@pytest.mark.parametrize("cfop", ["1202", "5202"])
def test_cfop_generico_de_devolucao_com_ncm_de_combustivel_nao_tem_sugestao(cfop):
    """CFOP genérico (1.202) com NCM de combustível: só o contador sabe se a venda foi para consumo
    (1,6%) ou revenda (8%). Sem sugestão, com o motivo."""
    sugestao = _sugestao(cfop, GASOLINA, fin="4")
    assert sugestao.natureza is None
    assert sugestao.motivo == "devolução de combustível: escolha consumo (1,6%) ou revenda (8%)"


def test_cfop_generico_de_devolucao_sem_combustivel_e_devolucao_venda_como_antes():
    assert _sugestao("1202", CERVEJA, fin="4").natureza == N.DEVOLUCAO_VENDA


# ---------------------------------------------------------------------------------------------
# Integração: devolução RECEBIDA (empresa destinatária) pelo serviço real
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-recebida-dl083")


@pytest.fixture
def cliente(escritorio_a, gestor):
    """Empresa destinatária da devolução: o CNPJ de destinatário de `xml_nfe_dl081`."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Cliente Devolucao DL083 Ltda",
        cnpj=xml.CNPJ_DESTINATARIO_A,
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


def _devolucao_recebida(escritorio, gestor, empresa, *, cfop, ncm, numero, valor, dh_emi):
    """NF-e de devolução de compra: emitida PELO CLIENTE (tpNF 1, finNFe 4), com a empresa
    destinatária."""
    return receber(
        escritorio,
        gestor,
        xml.nfe(
            dets=[
                xml.det(1, cfop=cfop, vprod=valor, ncm=ncm, icms_xml=xml.icms(csosn="102")),
            ],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", xml.CNPJ_EMITENTE_A),
            destinatario=("CNPJ", empresa.cnpj),
            tp_nf="1",
            fin_nfe="4",
        ),
    )


@pytest.mark.django_db
def test_devolucao_recebida_x662_tem_a_sugestao_de_consumo_e_entra_como_devolucao(
    escritorio_a, gestor, cliente
):
    documento = _devolucao_recebida(
        escritorio_a,
        gestor,
        cliente,
        cfop="5662",
        ncm=GASOLINA,
        numero=201,
        valor="10000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    rascunho = servico.criar_rascunho(vinculo(documento, cliente), usuario=gestor)
    assert rascunho.tipo == servico.TipoEscrituracaoNFe.DEVOLUCAO
    item = NaturezaItemNFe.objects.select_related("item").get(escrituracao=rascunho).item
    assert servico.sugerir_natureza_item(documento, item, rascunho.tipo).natureza == (
        N.DEVOLUCAO_COMBUSTIVEL_CONSUMO
    )


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("cfop", "aviso_esperado"),
    [
        ("5660", False),
        ("5661", False),
        ("5662", True),
        ("6660", False),
        ("6661", False),
        ("6662", True),
    ],
)
def test_devolucao_recebida_nao_recusa_e_avisa_so_o_x662_na_natureza_de_venda(
    escritorio_a, gestor, cliente, cfop, aviso_esperado
):
    """A1 (A1 da auditoria): as devoluções recebidas (5.660 a 5.662 e 6.660 a 6.662) não recusam
    mais. Com
    natureza `devolucao_venda` (8%), o x.662 avisa para conferir; o x.660 e o x.661 não. Venda
    própria de
    100.000,00 no mesmo trimestre, e devolução de 10.000,00 deduzida do comércio (8%)."""
    # Venda própria da empresa de 100.000,00 em fevereiro (natureza de revenda, 8%): é a receita de
    # comércio que a devolução vai absorver.
    venda = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, vprod="100000.00", ncm=CERVEJA, icms_xml=xml.icms(csosn="102"))],
            vnf="100000.00",
            totais={"vProd": "100000.00"},
            numero="211",
            dh_emi="2026-02-05T10:00:00-03:00",
            emitente=("CNPJ", cliente.cnpj),
            destinatario=("CNPJ", xml.CNPJ_EMITENTE_A),
        ),
    )
    esc_venda = servico.criar_rascunho(vinculo(venda, cliente), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc_venda).update(natureza=N.REVENDA)
    servico.efetivar(esc_venda, usuario=gestor)
    documento = _devolucao_recebida(
        escritorio_a,
        gestor,
        cliente,
        cfop=cfop,
        ncm=CERVEJA,
        numero=212,
        valor="10000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    esc = servico.criar_rascunho(vinculo(documento, cliente), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=N.DEVOLUCAO_VENDA)
    servico.efetivar(esc, usuario=gestor)

    apuracao = presumido_servico.apurar_trimestre(cliente, 2026, 1)
    assert "devolucao_combustivel" not in {r.codigo for r in apuracao.recusas}
    assert apuracao.devolucao_por_atividade == ((COMERCIO, D("10000.00")),)
    avisos = [a for a in apuracao.avisos if "confira a natureza" in a]
    assert bool(avisos) is aviso_esperado


# ---------------------------------------------------------------------------------------------
# Consulta, item 3.6: devolução de COMPRA emitida pela própria empresa não é dedução
# ---------------------------------------------------------------------------------------------


@pytest.mark.django_db
def test_devolucao_de_compra_emitida_pela_propria_empresa_nao_entra_na_escrituracao(
    escritorio_a, gestor, cliente
):
    """NF-e de saída da própria empresa (tpNF 1, finNFe 4) com CFOP 5.661: é devolução de COMPRA,
    saída
    própria. Não é elegível (a escrituração de devolução é de nota de terceiro ou de entrada
    própria):
    o tipo é None, e a criação do rascunho recusa com o motivo."""
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[
                xml.det(
                    1, cfop="5661", vprod="10000.00", ncm=GASOLINA, icms_xml=xml.icms(csosn="102")
                )
            ],
            vnf="10000.00",
            totais={"vProd": "10000.00"},
            numero="221",
            dh_emi="2026-02-10T10:00:00-03:00",
            emitente=("CNPJ", cliente.cnpj),
            destinatario=("CNPJ", xml.CNPJ_EMITENTE_A),
            tp_nf="1",
            fin_nfe="4",
        ),
    )
    assert servico.tipo_da_nota(documento, PapelNFe.EMITENTE) is None
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.criar_rascunho(vinculo(documento, cliente), usuario=gestor)
    assert "finNFe 4" in erro.value.mensagem
