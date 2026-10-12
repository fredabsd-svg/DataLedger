"""DL-088, frente A2: a receita de NF-e de 2027 (HI-149) e os motivos nomeados das recusas.

O contrato (HI-149; NT 2026.008 v1.00, lida em cópia local; consulta de 09/10/2026, seção 3):

- para a empresa do Simples no REGIME ÚNICO do semestre, a nota de 2027 se efetiva com receita
  igual ao `vProd` (que passa a conter IBS e CBS por dentro); o `vProdLiq` vira memória quando o
  leitor o trouxer (BL-687 — o leitor de hoje não o tem);
- para o Presumido, para quem optou pelo regime REGULAR e para o Simples sem a opção do semestre
  informada, a recusa continua, cada caso com o motivo nomeado.

O MUTANTE que os testes de recusa derrubam: aceitar a nota de 2027 sem checar o regime.
"""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    EstadoEscrituracao,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    RegimeIbsCbsSimples,
)
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl075_suporte import cenario_simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_ALFANUMERICO, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

D = Decimal
FUSO = ZoneInfo("America/Sao_Paulo")


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-nfe-2027-dl088")


@pytest.fixture
def empresa_simples(escritorio_a):
    """Empresa do Simples desde 2018 (a opção do semestre é que libera a nota de 2027)."""
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Simples 2027 DL088 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    return cenario_simples(empresa, abertura=date(2015, 1, 1), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def empresa_presumida(escritorio_a):
    """Empresa do Lucro Presumido em 2027: a receita de NF-e de 2027 continua bloqueada (HI-149).

    Outro CNPJ para caber no mesmo escritório junto com a `empresa_simples` (a unicidade de CNPJ é
    por escritório).
    """
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Presumida 2027 DL088 Ltda", cnpj=CNPJ_ALFANUMERICO
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    return empresa


def _nota_de_2027(numero=1, emitente_cnpj=CNPJ_EMITENTE_A) -> bytes:
    """NF-e de saída emitida em 10/02/2027, UM item: vProd 100,00 e frete 10,00.

    Pela regra do MOC (`itens_nfe.receita_do_item`) a receita seria 110,00 (vProd + frete); pela
    regra de 2027 (HI-149) é o `vProd`, 100,00. O vNF 110,00 fecha a W16, mas a W16 não é aplicada
    em 2027 (a composição do vNF não está publicada — PE-84.4).
    """
    return xml.nfe(
        dets=[xml.det(1, vprod="100.00", vfrete="10.00", icms_xml=xml.icms(csosn="102"))],
        vnf="110.00",
        totais={"vProd": "100.00"},
        numero=str(numero),
        dh_emi="2027-02-10T10:00:00-03:00",
        emitente=("CNPJ", emitente_cnpj),
    )


def _efetivar(escritorio, gestor, empresa, *, emitente_cnpj=CNPJ_EMITENTE_A, numero=1):
    documento = receber(escritorio, gestor, _nota_de_2027(numero, emitente_cnpj))
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    servico.definir_natureza(esc, NaturezaOperacaoNFe.REVENDA, ids, gestor)
    return servico.efetivar(esc, usuario=gestor)


def _opcao(empresa, gestor, regime, semestre=1):
    return servico_receita.registrar_opcao_regime_ibs_cbs(empresa, 2027, semestre, regime, gestor)


# ---------------------------------------------------------------------------
# Aceita: Simples no regime único, com receita igual ao vProd
# ---------------------------------------------------------------------------


def test_nota_de_2027_no_regime_unico_efetiva_com_receita_igual_ao_vprod(
    escritorio_a, gestor, empresa_simples
):
    """Opção REGIME ÚNICO do 1º semestre de 2027: a nota de 10/02/2027 efetiva com receita 100,00
    (o `vProd`), e NÃO 110,00 (o que a regra do MOC somaria com o frete).

    A memória da efetivação registra a regra e o `vProdLiq` quando existir: com o leitor de hoje
    (sem o campo, BL-687), `v_prod_liq` sai nulo.
    """
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_UNICO)

    esc = _efetivar(escritorio_a, gestor, empresa_simples)

    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert esc.receita_bruta == D("100.00")
    assert esc.soma_itens == D("100.00")
    assert esc.devolucao == D("0.00")
    assert esc.valor_nf == D("110.00")
    assert esc.data_emissao == date(2027, 2, 10)
    assert esc.competencia == date(2027, 2, 1)
    registro = RegistroAuditoria.objects.get(acao="escrituracao_nfe.efetivada")
    assert registro.detalhes["receita_2027"] == {
        "regra": "vProd (HI-149)",
        "v_prod": "100.00",
        "v_prod_liq": None,
    }


def test_a_composicao_do_mes_usa_o_vprod_da_nota_de_2027(escritorio_a, gestor, empresa_simples):
    """A mesma regra vale para quem lê a nota depois de efetivada (pré-DAS, RBT12, Presumido):
    a composição do mês traz o item com o `vProd`, 100,00, e não a receita do MOC, 110,00."""
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_UNICO)
    _efetivar(escritorio_a, gestor, empresa_simples)

    linhas = servico_receita.linhas_nfe_do_periodo(empresa_simples, (2027, 2), (2027, 2))

    (linha,) = linhas
    assert linha.papel == "receita"
    assert linha.valor == D("100.00")


def test_memoria_do_v_prod_liq_sai_quando_o_leitor_tiver_o_campo():
    """BL-687: o `vProdLiq` só vira memória quando o leitor o trouxer. O leitor de hoje não o tem
    (sem subir a versão nesta etapa), e aí não há valor que guardar: `None`, como no caso acima."""
    itens_com_campo = [
        SimpleNamespace(n_item=1, v_prod_liq=D("90.00")),
        SimpleNamespace(n_item=2, v_prod_liq=D("180.00")),
    ]
    assert servico.memoria_v_prod_liq(itens_com_campo) == {"1": "90.00", "2": "180.00"}

    itens_do_leitor_de_hoje = [SimpleNamespace(n_item=1), SimpleNamespace(n_item=2)]
    assert servico.memoria_v_prod_liq(itens_do_leitor_de_hoje) is None

    # Item com o campo vazio também não tem valor que guardar.
    assert servico.memoria_v_prod_liq([SimpleNamespace(n_item=1, v_prod_liq=None)]) is None


# ---------------------------------------------------------------------------
# Recusas nomeadas: regime regular, Presumido e opção não informada
# ---------------------------------------------------------------------------


def test_nota_de_2027_no_regime_regular_e_recusada(escritorio_a, gestor, empresa_simples):
    """Quem optou pelo regime REGULAR (art. 22-A) não tem receita de NF-e em 2027: a receita do
    regime regular depende do DL 1.598, art. 12, § 4º, não lido (HI-149). Recusa nomeada.

    MUTANTE que este teste derruba: aceitar a nota de 2027 sem checar o regime.
    """
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_REGULAR)

    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar(escritorio_a, gestor, empresa_simples)

    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_REGIME_REGULAR
    assert "regime regular" in erro.value.mensagem


def test_nota_de_2027_no_presumido_e_recusada(escritorio_a, gestor, empresa_presumida):
    """Presumido: a recusa continua, com o motivo nomeado (a receita do regime depende do
    DL 1.598, art. 12, § 4º)."""
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar(
            escritorio_a, gestor, empresa_presumida, emitente_cnpj=CNPJ_ALFANUMERICO, numero=2
        )

    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_PRESUMIDO
    assert "Presumido" in erro.value.mensagem


def test_nota_de_2027_sem_a_opcao_do_semestre_e_recusada(escritorio_a, gestor, empresa_simples):
    """Simples SEM a opção do semestre informada: não se sabe se a empresa está no regime único,
    e nada se presume — a nota não se efetiva, com o motivo nomeado."""
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar(escritorio_a, gestor, empresa_simples)

    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_SEM_OPCAO
    assert "190/2026" in erro.value.mensagem


def test_a_opcao_do_outro_semestre_nao_libera_a_nota(escritorio_a, gestor, empresa_simples):
    """A opção é por semestre: a nota de 10/02/2027 (1º semestre) não se aproveita da opção do
    2º semestre."""
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_UNICO, semestre=2)

    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        _efetivar(escritorio_a, gestor, empresa_simples)

    assert erro.value.mensagem == servico.MENSAGEM_RECEITA_2027_SEM_OPCAO


# ---------------------------------------------------------------------------
# O portão, caso a caso (e o contrato antigo da checagem pura de data)
# ---------------------------------------------------------------------------


def _doc_de_2027():
    return SimpleNamespace(dh_emissao=datetime(2027, 2, 10, 10, 0, tzinfo=FUSO))


def test_motivo_bloqueio_efetivacao_com_empresa_nomeia_cada_caso(
    escritorio_a, gestor, empresa_simples, empresa_presumida
):
    """Com a empresa, o portão de 2027 diz o caso: regime único libera; os demais nomeiam."""
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_UNICO)
    assert servico.motivo_bloqueio_efetivacao(_doc_de_2027(), empresa_simples) is None

    # Mesma empresa, com a opção REGIME REGULAR do semestre: recusa nomeada (outro semestre, para
    # não depender do estado da outra linha).
    _opcao(empresa_simples, gestor, RegimeIbsCbsSimples.REGIME_REGULAR, semestre=2)
    doc_julho = SimpleNamespace(dh_emissao=datetime(2027, 7, 10, 10, 0, tzinfo=FUSO))
    assert (
        servico.motivo_bloqueio_efetivacao(doc_julho, empresa_simples)
        == servico.MENSAGEM_RECEITA_2027_REGIME_REGULAR
    )

    assert (
        servico.motivo_bloqueio_efetivacao(_doc_de_2027(), empresa_presumida)
        == servico.MENSAGEM_RECEITA_2027_PRESUMIDO
    )


def test_checagem_pura_de_data_continua_com_o_contrato_da_dl083():
    """Sem `empresa`, a checagem é a pura data da DL-083 (A8): 2027 recusa com o motivo fixo que a
    tela mostra, e 2026 passa. Contrato dos testes antigos, preservado."""
    assert servico.motivo_bloqueio_efetivacao(_doc_de_2027()) == (
        servico.MENSAGEM_RECEITA_2027_PENDENTE
    )
    doc_2026 = SimpleNamespace(dh_emissao=datetime(2026, 12, 31, 23, 59, tzinfo=FUSO))
    assert servico.motivo_bloqueio_efetivacao(doc_2026) is None
