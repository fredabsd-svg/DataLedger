# ruff: noqa: F811 — as fixtures são importadas do módulo de proteção e recebidas por parâmetro.
"""DL-081 — ajustes da reconferência, integrados pelo arquiteto.

Pela regra de parada do §3.1 não há nova rodada de correção. Da reconferência
(docs/auditorias/2026-10-09-dl-081-reconferencia.md):

- R1: o quadro do limite do ano do Presumido também sai com a recusa nomeada quando há NF-e
  efetivada no ano, como a apuração do trimestre (HI-122).
- N4b (lacuna de teste): a efetivação recusa a leitura dos itens feita por versão anterior do
  leitor, e a escrituração continua em rascunho.

Dados sintéticos.
"""

from datetime import date

import pytest

from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import presumido as presumido_servico
from apps.fiscal.models import EstadoEscrituracao, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.test_dl081_protecao import (  # noqa: F401 (fixtures)
    CODIGO_NAO_ESCRITURADA,
    empresa_presumido,
    gestor,
    nfe_pendente,
)

pytestmark = pytest.mark.django_db

# DL-083: a recusa do controle do ano é a NF-e não escriturada (a NF-e efetivada já entra).
CODIGO = CODIGO_NAO_ESCRITURADA


def _codigos_do_controle(empresa, ano):
    controle = presumido_servico.controle_limite_ano(empresa, ano, "irpj", hoje=date(ano, 12, 31))
    return tuple(r.codigo for r in controle.recusas)


def test_controle_do_limite_do_ano_sai_com_a_recusa_quando_ha_nfe_pendente_no_ano(
    escritorio_a, gestor, empresa_presumido
):
    assert CODIGO not in _codigos_do_controle(empresa_presumido, 2026)
    nfe_pendente(
        escritorio_a,
        gestor,
        empresa_presumido,
        numero=21,
        valor="300000.00",
        dh_emi="2026-02-10T10:00:00-03:00",
    )
    assert CODIGO in _codigos_do_controle(empresa_presumido, 2026)
    # O ano seguinte não é afetado.
    assert CODIGO not in _codigos_do_controle(empresa_presumido, 2027)


def test_efetivar_recusa_leitura_de_versao_anterior_do_leitor(
    escritorio_a, gestor, empresa_presumido, monkeypatch
):
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5102", vprod="1000.00", icms_xml=xml.icms(csosn="102"))],
            vnf="1000.00",
            totais={"vProd": "1000.00"},
            numero="31",
            dh_emi="2026-03-10T10:00:00-03:00",
        ),
    )
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa_presumido), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=escrituracao).update(
        natureza=NaturezaOperacaoNFe.REVENDA
    )
    # Uma versão nova do leitor torna a leitura gravada "anterior".
    monkeypatch.setattr(servico, "VERSAO_LEITOR_ITENS", servico.VERSAO_LEITOR_ITENS + 1)
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(escrituracao, usuario=gestor)
    assert "versão anterior" in str(erro.value)
    escrituracao.refresh_from_db()
    assert escrituracao.estado == EstadoEscrituracao.RASCUNHO
