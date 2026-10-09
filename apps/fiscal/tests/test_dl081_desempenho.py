"""DL-081, correção da rodada 1 (A6): desempenho das consultas, com o número de consultas fixo.

- RBT12 com 60 meses de devolução: abaixo de 100 consultas (o saldo é percorrido uma vez).
- A composição de 60 meses não repete o histórico a cada mês (cada mês da janela não relê tudo).
- Lista e conferência do mês: o número de consultas não cresce com o número de notas.

Valores esperados escritos à mão: devolução de 100,00 em cada um dos 60 meses de 2021 a 2025, e
venda de 1.000,00 em cada um dos 12 meses da janela (mar/2025 a fev/2026). Pela regra do saldo
(Res. CGSN 140, art. 17): entram em mar/2025 os 5.000,00 de devolução de antes da janela (50 meses
de 100,00), e dentro da janela há mais 10 devoluções de 100,00 (mar a dez/2025). Total a deduzir:
6.000,00, e a venda de 12.000,00 o absorve por inteiro. O RBT12 interno é 12.000,00 − 6.000,00 =
6.000,00. Nenhum saldo sobra para 2026.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import NaturezaItemNFe, NaturezaOperacaoNFe, VinculoNFeEmpresa
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    fixar_hoje,
    fixar_inicio_de_uso,
    preparar_simples,
    sequencia,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-desempenho-dl081")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Desempenho Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _nota_efetivada(escritorio, usuario, empresa_da_nota, *, valor, natureza, numero, dh_emi):
    """Uma nota de um item, confirmada e efetivada pelos serviços. Devolução: tp_nf 0, finNFe 4."""
    devolucao = natureza == N.DEVOLUCAO_VENDA
    documento = receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[
                xml.det(
                    1,
                    cfop="1202" if devolucao else "5102",
                    vprod=valor,
                    icms_xml=xml.icms(csosn="102"),
                )
            ],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi,
            tp_nf="0" if devolucao else "1",
            fin_nfe="4" if devolucao else "1",
        ),
    )
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return servico.efetivar(esc, usuario=usuario)


def test_rbt12_com_60_meses_de_devolucao_fica_abaixo_de_100_consultas(
    escritorio_a, gestor, empresa, monkeypatch, django_assert_max_num_queries
):
    """Antes da correção: 2.134 consultas e 4,04 s. Agora, o saldo anda uma vez pela janela."""
    fixar_inicio_de_uso(empresa, 2021, 1)
    preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))
    fixar_hoje(monkeypatch, date(2026, 4, 15))

    numero = 1
    for ano in range(2021, 2026):
        for mes in range(1, 13):
            _nota_efetivada(
                escritorio_a,
                gestor,
                empresa,
                valor="100.00",
                natureza=N.DEVOLUCAO_VENDA,
                numero=numero,
                dh_emi=f"{ano}-{mes:02d}-10T10:00:00-03:00",
            )
            numero += 1
    for ano, mes in sequencia(2025, 3, 12):
        _nota_efetivada(
            escritorio_a,
            gestor,
            empresa,
            valor="1000.00",
            natureza=N.REVENDA,
            numero=numero,
            dh_emi=f"{ano}-{mes:02d}-12T10:00:00-03:00",
        )
        numero += 1
    confirmar_meses(empresa, gestor, sequencia(2025, 3, 12))

    # Medido: 19 consultas. O requisito era "abaixo de 100"; o teto de 25 é mais justo, e pega a
    # releitura do saldo mês a mês (que daria cerca de 70 consultas).
    with django_assert_max_num_queries(25):
        resultado = apuracao.rbt12(empresa, 2026, 3)
    assert resultado.por_mercado["interno"].soma == Decimal("6000.00")


def test_composicao_de_um_mes_nao_depende_de_quantos_meses_de_historico_ha(
    escritorio_a, gestor, empresa, django_assert_max_num_queries
):
    """O mesmo mês com 3 meses de histórico e com 60: o número de consultas é o mesmo. A
    composição do mês não relê o histórico mês a mês (A6: cada mês repetia o histórico inteiro)."""
    for numero, mes in enumerate(range(1, 4), start=1):
        _nota_efetivada(
            escritorio_a,
            gestor,
            empresa,
            valor="100.00",
            natureza=N.DEVOLUCAO_VENDA,
            numero=numero,
            dh_emi=f"2026-{mes:02d}-10T10:00:00-03:00",
        )
    with django_assert_max_num_queries(12) as curto:
        servico_receita.composicao_do_mes(empresa, 2026, 4)
    consultas_curto = len(curto.captured_queries)

    for numero, (ano, mes) in enumerate(sequencia(2021, 1, 60), start=100):
        _nota_efetivada(
            escritorio_a,
            gestor,
            empresa,
            valor="100.00",
            natureza=N.DEVOLUCAO_VENDA,
            numero=numero,
            dh_emi=f"{ano}-{mes:02d}-10T10:00:00-03:00",
        )
    with django_assert_max_num_queries(12) as longo:
        servico_receita.composicao_do_mes(empresa, 2026, 4)
    assert len(longo.captured_queries) == consultas_curto


# --- lista e conferência do mês: o número de consultas não cresce com as notas (A6) -------------


def _notas_recebidas_e_lidas(escritorio, usuario, quantidade, inicio):
    """`quantidade` NF-e em mar/2026, cada uma já lida (leitura lida, sem rascunho)."""
    from apps.fiscal import itens_nfe

    for numero in range(inicio, inicio + quantidade):
        documento = receber(
            escritorio,
            usuario,
            xml.nfe(
                # CFOP 5501 não tem sugestão de natureza: cada nota conta 1 item sem sugestão.
                dets=[xml.det(1, cfop="5501", vprod="100.00", icms_xml=xml.icms(csosn="102"))],
                vnf="100.00",
                totais={"vProd": "100.00"},
                numero=str(numero),
                dh_emi="2026-03-15T10:00:00-03:00",
            ),
        )
        itens_nfe.ler_itens(documento)


def _consultas(funcao) -> int:
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as contexto:
        funcao()
    return len(contexto.captured_queries)


def test_lista_do_mes_tem_o_mesmo_numero_de_consultas_com_5_e_com_60_notas(
    escritorio_a, gestor, empresa
):
    """Antes: uma consulta de situação de cancelamento por nota (411 consultas com 400 notas)."""
    _notas_recebidas_e_lidas(escritorio_a, gestor, 5, inicio=1)
    cinco = _consultas(lambda: servico_nfe.notas_do_mes(empresa, 2026, 3))
    _notas_recebidas_e_lidas(escritorio_a, gestor, 55, inicio=6)
    sessenta = _consultas(lambda: servico_nfe.notas_do_mes(empresa, 2026, 3))
    assert len(servico_nfe.notas_do_mes(empresa, 2026, 3)) == 60
    assert sessenta == cinco


def test_conferencia_do_mes_tem_o_mesmo_numero_de_consultas_com_5_e_com_60_notas(
    escritorio_a, gestor, empresa
):
    """A conferência lê as notas uma vez e os itens sem sugestão em uma consulta (A6)."""
    _notas_recebidas_e_lidas(escritorio_a, gestor, 5, inicio=101)
    cinco = _consultas(lambda: servico_nfe.conferencia_do_mes(empresa, 2026, 3))
    _notas_recebidas_e_lidas(escritorio_a, gestor, 55, inicio=106)
    sessenta = _consultas(lambda: servico_nfe.conferencia_do_mes(empresa, 2026, 3))
    conferencia = servico_nfe.conferencia_do_mes(empresa, 2026, 3)
    assert conferencia.recebidas == 60 and conferencia.itens_sem_sugestao == 60
    assert sessenta == cinco


def test_nota_unica_nao_lista_o_mes_e_recusa_vinculo_de_outra_empresa(
    escritorio_a, gestor, empresa, django_assert_max_num_queries
):
    """A tela de uma nota busca a nota pelo vínculo (A6). Número de consultas pequeno, mesmo com o
    mês cheio, e vínculo de outra empresa é recusado (isolamento)."""
    _notas_recebidas_e_lidas(escritorio_a, gestor, 60, inicio=201)
    vinculo_da_nota = VinculoNFeEmpresa.objects.filter(empresa=empresa).first()
    with django_assert_max_num_queries(6):
        nota = servico_nfe.nota_do_vinculo(empresa, vinculo_da_nota)
    assert nota.vinculo.pk == vinculo_da_nota.pk and nota.leitura_estado == "lida"

    outra = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra Desempenho Ltda", cnpj=CNPJ_DESTINATARIO_A
    )
    with pytest.raises(LookupError):
        servico_nfe.nota_do_vinculo(outra, vinculo_da_nota)
