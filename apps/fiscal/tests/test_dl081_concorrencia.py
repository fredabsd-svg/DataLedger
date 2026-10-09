"""DL-081 (frente A), concorrência: duas requisições ao mesmo tempo sobre a MESMA nota.

Banco transacional (os dados são confirmados, e cada thread tem a sua conexão): é o único jeito de
exercitar a trava `select_for_update` e a restrição parcial do banco de verdade. Resultado esperado:
nunca duas escriturações ativas, nunca duas trilhas de efetivação, e nenhum erro 500.
"""

import threading
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe, EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db(transaction=True)


def _duas_threads(alvo, argumentos):
    """Roda `alvo` em duas threads ao mesmo tempo (barreira), cada uma com a sua conexão."""
    barreira = threading.Barrier(2)
    resultados = [None, None]

    def corpo(indice):
        try:
            barreira.wait(timeout=10)
            resultados[indice] = ("ok", alvo(*argumentos))
        except Exception as exc:  # o resultado de cada corrida é conferido pelo teste
            resultados[indice] = ("erro", exc)
        finally:
            connection.close()

    fios = [threading.Thread(target=corpo, args=(i,)) for i in range(2)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)
    return resultados


@pytest.fixture
def cenario(escritorio_a):
    gestor = usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-corrida-dl081")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Corrida Ltda", cnpj=CNPJ_EMITENTE_A
    )
    documento = receber(
        escritorio_a,
        gestor,
        xml.nfe(
            dets=[xml.det(1, cfop="5101", vprod="10000.00", icms_xml=xml.icms(csosn="102"))],
            vnf="10000.00",
            totais={"vProd": "10000.00"},
            dh_emi="2026-03-15T10:00:00-03:00",
        ),
    )
    return gestor, empresa, documento


def test_duas_efetivacoes_simultaneas_geram_uma_so_trilha(cenario):
    gestor, empresa, documento = cenario
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="producao_propria")

    resultados = _duas_threads(servico.efetivar, (esc, gestor))

    for tipo, valor in resultados:
        assert tipo == "ok", valor
    criadas = [valor.criada_agora for _, valor in resultados]
    assert sorted(criadas) == [False, True]  # uma efetiva; a outra vê a já efetivada
    esc.refresh_from_db()
    assert esc.estado == EstadoEscrituracao.EFETIVADA
    assert RegistroAuditoria.objects.filter(acao="escrituracao_nfe.efetivada").count() == 1
    assert EscrituracaoNFe.objects.filter(vinculo=esc.vinculo).count() == 1


def test_dois_rascunhos_simultaneos_da_mesma_nota_geram_um_so(cenario):
    gestor, empresa, documento = cenario
    vinc = vinculo(documento, empresa)

    resultados = _duas_threads(servico.criar_rascunho, (vinc, gestor))

    erros = [valor for tipo, valor in resultados if tipo == "erro"]
    for erro in erros:
        # A corrida perdedora recebe erro de NEGÓCIO (409), nunca erro de banco (500).
        assert isinstance(erro, servico.EscrituracaoNFeErro), repr(erro)
    ativas = EscrituracaoNFe.objects.filter(
        vinculo=vinc, estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA]
    )
    assert ativas.count() == 1


def test_valor_da_receita_nao_muda_entre_as_duas_efetivacoes(cenario):
    """A receita gravada é a mesma nas duas corridas: uma vence e a outra não regrava o valor."""
    gestor, empresa, documento = cenario
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza="producao_propria")
    _duas_threads(servico.efetivar, (esc, gestor))
    esc.refresh_from_db()
    assert esc.receita_bruta == Decimal("10000.00")
    assert esc.soma_itens == Decimal("10000.00")
    assert get_user_model().objects.filter(pk=gestor.pk).exists()
