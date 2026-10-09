"""DL-083 (A8; HI-133): nota de 2027 não se efetiva, e o Presumido e a tela dizem isso com o motivo
certo.

- `motivo_bloqueio_efetivacao` é a checagem pura de data: a tela a usa para desabilitar o botão, e o
  serviço a usa no POST. O ano é o de São Paulo (31/12/2026 23:59 é de 2026).
- Nota de 2027 em rascunho ou a escriturar NÃO é "NF-e não escriturada" no Presumido: não pode ser
  escriturada. Tem recusa própria, `nfe_2027_pendente`, com o texto da A8.
- Na tela, o botão "Efetivar" fica desabilitado com o motivo (teste em `test_dl083_telas.py`).
"""

from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

FUSO = ZoneInfo("America/Sao_Paulo")
MENSAGEM = "regra de receita de 2027 pendente: NT 2026.008 e vNF"
MENSAGEM_NFE_2027 = (
    "NF-e de 2027 sem regra de receita (NT 2026.008 e vNF): não pode ser escriturada"
)


def _doc(*ano_mes_dia_hora_min):
    """Documento sintético com `dh_emissao` no fuso de São Paulo (só o que a checagem lê)."""
    return SimpleNamespace(dh_emissao=datetime(*ano_mes_dia_hora_min, tzinfo=FUSO))


# ---------------------------------------------------------------------------------------------
# Checagem pura de data
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instante", "motivo"),
    [
        ((2026, 12, 31, 23, 59), None),
        ((2026, 1, 1, 0, 0), None),
        ((2027, 1, 1, 0, 0), MENSAGEM),
        ((2027, 6, 15, 12, 0), MENSAGEM),
    ],
)
def test_motivo_de_bloqueio_pela_data_de_sao_paulo(instante, motivo):
    """31/12/2026 23:59 de São Paulo efetiva. 01/01/2027 00:00 de São Paulo não."""
    assert servico.motivo_bloqueio_efetivacao(_doc(*instante)) == motivo


def test_fuso_de_utc_nao_muda_o_ano_da_nota_de_2026():
    """31/12/2026 23:59 de São Paulo é 01/01/2027 02:59 UTC. Uma comparação em UTC recusaria a nota
    de
    2026. A checagem usa o ano de São Paulo, então a nota efetiva."""
    documento = SimpleNamespace(dh_emissao=datetime(2027, 1, 1, 2, 59, tzinfo=ZoneInfo("UTC")))
    assert servico.motivo_bloqueio_efetivacao(documento) is None


# ---------------------------------------------------------------------------------------------
# Presumido: recusa própria, não a de "não escriturada"
# ---------------------------------------------------------------------------------------------


@pytest.fixture
def empresa_2027(escritorio_a):
    gestor = usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-2027-dl083")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Regra 2027 DL083 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2027, 1, 1),
    )
    presumido_servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2027, 1, 1), "padrao": True},
        gestor,
    )
    return empresa, gestor


@pytest.mark.django_db
def test_nota_de_2027_em_rascunho_gera_recusa_propria_no_presumido(escritorio_a, empresa_2027):
    empresa, gestor = empresa_2027
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, vprod="800.00", icms_xml=xml.icms(csosn="102"))],
            vnf="800.00",
            totais={"vProd": "800.00"},
            numero="2701",
            dh_emi="2027-02-10T10:00:00-03:00",
            emitente=("CNPJ", CNPJ_EMITENTE_A),
        ),
    )
    servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)

    apuracao = presumido_servico.apurar_trimestre(empresa, 2027, 1)

    recusas = {r.codigo: r for r in apuracao.recusas}
    assert "nfe_nao_escriturada" not in recusas
    assert recusas["nfe_2027_pendente"].mensagem == MENSAGEM_NFE_2027
    assert apuracao.situacao == "parcial"
    assert apuracao.irpj is None
