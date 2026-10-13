"""DL-091 (frente A2): a nota de ENTRADA na lista do mês.

Regra (docs/planos/DL-091-nfe-de-entrada.md, A2, item 5): a compra aparece no mês da DATA DE
ENTRADA quando já está escriturada (rascunho ou efetivada), e no mês de EMISSÃO enquanto não está.
Estornada, volta para o mês de emissão. A competência da efetivação (`competencia`) é a mesma data
de entrada.

Dados sintéticos. A emissão é 15/03/2026, em São Paulo.
"""

from datetime import date

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _rascunho
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Competência entrada A2 Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


def _numeros(empresa, mes):
    return {nota.documento.numero for nota in servico.notas_do_mes(empresa, 2026, mes)}


def test_compra_sem_escrituracao_fica_no_mes_de_emissao(escritorio_a, usuario_gestor_a, empresa):
    _rascunho(
        escritorio_a, usuario_gestor_a, empresa, numero="3001"
    )  # ainda rascunho: já escriturada
    from apps.fiscal.tests.test_dl091_entradas import _nota

    _nota(escritorio_a, usuario_gestor_a, empresa, numero="3002")  # recebida, sem escrituração
    assert {"3001", "3002"} <= _numeros(empresa, 3)
    assert "3002" not in _numeros(empresa, 4)


def test_compra_efetivada_com_data_de_entrada_em_abril_sai_de_marco_e_entra_em_abril(
    escritorio_a, usuario_gestor_a, empresa
):
    rascunho = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="3101")
    entradas.definir_data_de_entrada(rascunho, date(2026, 4, 2), usuario=usuario_gestor_a)
    _confirmar(rascunho, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    servico.efetivar(rascunho, usuario=usuario_gestor_a)

    assert "3101" in _numeros(empresa, 4)
    assert "3101" not in _numeros(empresa, 3)
    nota = next(n for n in servico.notas_do_mes(empresa, 2026, 4) if n.documento.numero == "3101")
    assert nota.escrituracao.competencia == date(2026, 4, 1)
    assert nota.escrituracao.data_entrada == date(2026, 4, 2)


def test_rascunho_com_data_de_entrada_em_abril_ja_aparece_em_abril(
    escritorio_a, usuario_gestor_a, empresa
):
    rascunho = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="3201")
    entradas.definir_data_de_entrada(rascunho, date(2026, 4, 9), usuario=usuario_gestor_a)
    assert "3201" in _numeros(empresa, 4)
    assert "3201" not in _numeros(empresa, 3)


def test_compra_estornada_volta_para_o_mes_de_emissao(escritorio_a, usuario_gestor_a, empresa):
    rascunho = _rascunho(escritorio_a, usuario_gestor_a, empresa, numero="3301")
    entradas.definir_data_de_entrada(rascunho, date(2026, 4, 2), usuario=usuario_gestor_a)
    _confirmar(rascunho, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    efetivada = servico.efetivar(rascunho, usuario=usuario_gestor_a)
    servico.estornar(efetivada, "teste de competência", usuario=usuario_gestor_a)

    assert "3301" in _numeros(empresa, 3)
    assert "3301" not in _numeros(empresa, 4)
