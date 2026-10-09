"""DL-082 (frente A): cada recusa nomeada do primeiro corte tem teste e mensagem (critério 5).

Também testa o aviso do CSOSN 900 (não recusa) e os casos que NÃO recusam por desenho: comercial
exportadora (a própria natureza é a confirmação) e mês só de mercadoria sem atividade padrão.
"""

from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal.models import EnquadramentoAtividade, NaturezaOperacaoNFe
from apps.fiscal.pre_das import MENSAGEM_IPI_E_ISS
from apps.fiscal.tests.suporte_dl082 import confirmar_pa, escriturar, informar, janela, nota
from apps.fiscal.tests.test_dl075_suporte import atividade_padrao
from apps.fiscal.tests.test_dl075_suporte import cenario_simples as cenario
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

NF = NaturezaOperacaoNFe


@pytest.fixture
def empresa_a(escritorio_a):
    """Emitente das NF-e sintéticas (CNPJ_EMITENTE_A). Ver o módulo de cálculo (DL-082)."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Comercio Recusas DL082 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _codigos(exc):
    return {b.codigo: b.mensagem for b in exc.value.bloqueios}


def _mes_com_venda(
    escritorio,
    usuario,
    empresa,
    *,
    natureza,
    cfop="5102",
    csosn="102",
    vprod="100000.00",
    id_dest="1",
    numero=401,
):
    """Janela de 300.000 e uma venda do PA, na natureza dada. O PA (06/2026) fica confirmado."""
    janela(empresa, usuario, 2026, 6, [25000] * 12)
    documento = nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        itens=[{"cfop": cfop, "vprod": vprod, "csosn": csosn}],
        id_dest=id_dest,
    )
    escriturar(empresa, usuario, documento, {1: natureza})
    confirmar_pa(empresa, usuario)


@pytest.mark.parametrize(
    ("natureza", "trecho"),
    [
        (NF.COMBUSTIVEL, "combustível para consumo"),
        (NF.COMBUSTIVEL_REVENDA, "combustível para revenda"),
        (NF.SERVICO_CONJUGADA, "serviço em NF-e conjugada"),
    ],
)
def test_natureza_fora_do_corte_recusa_com_nome(
    escritorio_a, usuario_gestor_a, empresa_a, natureza, trecho
):
    empresa = cenario(empresa_a)
    cfop = "5933" if natureza == NF.SERVICO_CONJUGADA else "5656"
    _mes_com_venda(escritorio_a, usuario_gestor_a, empresa, natureza=natureza, cfop=cfop)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    codigos = _codigos(erro)
    assert "natureza_fora_do_corte" in codigos
    assert trecho in codigos["natureza_fora_do_corte"]


def test_devolucao_de_combustivel_recusa_com_nome(escritorio_a, usuario_gestor_a, empresa_a):
    """Devolução de combustível (natureza `devolucao_combustivel_consumo`): fora do primeiro
    corte."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    venda = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=411,
        itens=[{"cfop": "5102", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, venda, {1: NF.REVENDA})
    devolucao = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=412,
        itens=[{"cfop": "1662", "vprod": "2000.00"}],
        devolucao=True,
    )
    escriturar(empresa, usuario_gestor_a, devolucao, {1: NF.DEVOLUCAO_COMBUSTIVEL_CONSUMO})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    assert "devolução de combustível" in _codigos(erro)["natureza_fora_do_corte"]


@pytest.mark.parametrize(("csosn", "numero"), [("103", 421), ("300", 422), ("400", 423)])
def test_csosn_de_beneficio_sem_parametro_recusa_com_nome(
    escritorio_a, usuario_gestor_a, empresa_a, csosn, numero
):
    """CSOSN 103, 300 e 400: benefício ou imunidade de ICMS sem parâmetro estadual (HI-131)."""
    empresa = cenario(empresa_a)
    _mes_com_venda(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        natureza=NF.REVENDA,
        csosn=csosn,
        numero=numero,
    )

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    mensagem = _codigos(erro)["beneficio_icms_sem_parametro"]
    assert "benefício ou imunidade de ICMS sem parâmetro estadual" in mensagem
    assert f"CSOSN {csosn}" in mensagem


def test_csosn_900_nao_recusa_e_gera_aviso(escritorio_a, usuario_gestor_a, empresa_a):
    """CSOSN 900 não recusa: o pré-DAS calcula pela natureza e avisa para conferir (HI-131).

    Esperado (à mão): RBT12 300.000, revenda 100.000 (5,32%): total 5.320,00; aviso com "CSOSN 900".
    """
    empresa = cenario(empresa_a)
    _mes_com_venda(
        escritorio_a, usuario_gestor_a, empresa, natureza=NF.REVENDA, csosn="900", numero=431
    )

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("5320.00")
    assert len(resultado.avisos) == 1
    assert "CSOSN 900" in resultado.avisos[0]


def test_ipi_e_iss_no_mesmo_mes_recusa_com_nome(escritorio_a, usuario_gestor_a, empresa_a):
    """Produção própria (Anexo II, com IPI) e serviço com ISS no mesmo mês: fora do primeiro
    corte."""
    empresa = cenario(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar(empresa, usuario_gestor_a, 2026, 6, 20000)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=441,
        itens=[{"cfop": "5101", "vprod": "100000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.PRODUCAO_PROPRIA})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    assert _codigos(erro)["atividade_com_ipi_e_iss"] == MENSAGEM_IPI_E_ISS


def test_rbt12_acima_de_3_6_milhoes_recusa_com_nome(escritorio_a, usuario_gestor_a, empresa_a):
    """RBT12 de 3.720.000 (12 × 310.000), acima do primeiro corte de 3.600.000 (HI-68)."""
    empresa = cenario(empresa_a)
    janela(empresa, usuario_gestor_a, 2026, 6, [310000] * 12)
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=451,
        itens=[{"cfop": "5102", "vprod": "1000.00"}],
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.REVENDA})
    confirmar_pa(empresa, usuario_gestor_a)

    with pytest.raises(servico_pre_das.PreDasRecusado) as erro:
        servico_pre_das.pre_das(empresa, 2026, 6)

    assert "rbt12_acima_do_primeiro_corte" in _codigos(erro)


def test_comercial_exportadora_calcula_pela_propria_natureza(
    escritorio_a, usuario_gestor_a, empresa_a
):
    """Comercial exportadora: a escolha da natureza `comercial_exportadora` na escrituração é a
    confirmação do contador (a própria escrituração só se efetiva com a natureza confirmada). Por
    isso não há recusa. Documentado na DL-082.

    Esperado (à mão): mercado externo, RBT12 1.000.000 (4ª faixa, 8,45%), exportação de 50.000:
    IRPJ 232,38; CSLL 147,88; CPP 1.774,50; total 2.154,76. Mercado interno sem receita.
    """
    empresa = cenario(empresa_a)
    janela(
        empresa,
        usuario_gestor_a,
        2026,
        6,
        interno=[0] * 12,
        externo=[100000] * 10 + [0, 0],
    )
    documento = nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero=461,
        itens=[{"cfop": "7101", "vprod": "50000.00"}],
        id_dest="3",
    )
    escriturar(empresa, usuario_gestor_a, documento, {1: NF.COMERCIAL_EXPORTADORA})
    confirmar_pa(empresa, usuario_gestor_a)

    resultado = servico_pre_das.pre_das(empresa, 2026, 6)

    assert resultado.total == Decimal("2154.76")
    (anexo,) = resultado.anexos
    assert (anexo.mercado, anexo.anexo) == ("externo", "I")
    (segmento,) = anexo.segmentos
    assert segmento.segmento == "exportacao"
