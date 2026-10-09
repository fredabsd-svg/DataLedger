"""DL-081, correção da rodada 1: regras que os mutantes sobreviventes mostraram sem teste.

- X4b: nota cancelada depois do rascunho não é efetivada.
- X13 e X14: efetivar e estornar em mês confirmado deixam a trilha "a retificar" (com a ação
própria).
- X17: o aviso de CRT 1, 2 ou 4 com grupo IBS/CBS vale só para 2026.
- M7b e M7c: a conferência e a lista do mês não trazem notas de outra empresa do mesmo escritório.
- E6: o vNFTot não substitui o vNF na conferência.

Valores escritos à mão. CNPJ sintético.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import itens_nfe
from apps.fiscal.models import EventoNFe, NaturezaItemNFe, NaturezaOperacaoNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl074_suporte import (
    confirmar_meses,
    fixar_inicio_de_uso,
    preparar_simples,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

N = NaturezaOperacaoNFe


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-regras-rodada1-dl081")


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Regras Rodada 1 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    fixar_inicio_de_uso(empresa, 2024, 1)
    return preparar_simples(empresa, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Regras Rodada 1 Outra Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _nota(escritorio, usuario, *, numero, valor="100.00", emitente=None, dh_emi=None, **kwargs):
    return receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=[xml.det(1, vprod=valor, icms_xml=xml.icms(csosn="102"))],
            vnf=valor,
            totais={"vProd": valor},
            numero=str(numero),
            dh_emi=dh_emi or "2026-03-15T10:00:00-03:00",
            emitente=emitente or ("CNPJ", CNPJ_EMITENTE_A),
            **kwargs,
        ),
    )


def _rascunho(usuario, empresa_da_nota, documento, natureza=N.REVENDA):
    esc = servico.criar_rascunho(vinculo(documento, empresa_da_nota), usuario=usuario)
    NaturezaItemNFe.objects.filter(escrituracao=esc).update(natureza=natureza)
    return esc


# --- X4b: cancelada depois do rascunho não efetiva ---------------------------------------------


def test_nota_cancelada_depois_do_rascunho_nao_e_efetivada(escritorio_a, gestor, empresa):
    documento = _nota(escritorio_a, gestor, numero=41)
    esc = _rascunho(gestor, empresa, documento)
    EventoNFe.objects.create(
        escritorio=escritorio_a,
        identificador=f"ID110111{documento.chave}01",
        tp_evento="110111",
        n_seq_evento=1,
        chave=documento.chave,
        dh_evento=documento.dh_emissao,
        autor_tipo_documento="CNPJ",
        autor_documento=CNPJ_EMITENTE_A,
        c_stat="135",
        xml_original=b"<evento-sintetico/>",
        sha256_arquivo="2" * 64,
    )
    with pytest.raises(servico.EscrituracaoNFeErro) as erro:
        servico.efetivar(esc, usuario=gestor)
    assert "cancelada" in erro.value.mensagem
    esc.refresh_from_db()
    assert esc.estado == "rascunho"


# --- X13 e X14: a trilha da retificação em mês confirmado ---------------------------------------


def test_efetivar_em_mes_confirmado_grava_a_trilha_a_retificar_por_efetivacao(
    escritorio_a, gestor, empresa
):
    confirmar_meses(empresa, gestor, [(2026, 3)])
    documento = _nota(escritorio_a, gestor, numero=42)
    esc = _rascunho(gestor, empresa, documento)
    servico.efetivar(esc, usuario=gestor)
    assert RegistroAuditoria.objects.filter(
        acao="receita_mensal.a_retificar_por_efetivacao"
    ).exists()


def test_estornar_em_mes_confirmado_grava_a_trilha_a_retificar_por_estorno(
    escritorio_a, gestor, empresa
):
    """A efetivação vem ANTES da confirmação, e o estorno depois: o mês confirmado volta a
    "a retificar" pelo estorno, com a trilha do estorno. (Se o mês já estivesse "a retificar" por
    uma efetivação, o estorno não grava trilha nova: a marca já está, por desenho.)"""
    documento = _nota(escritorio_a, gestor, numero=43)
    esc = servico.efetivar(_rascunho(gestor, empresa, documento), usuario=gestor)
    confirmar_meses(empresa, gestor, [(2026, 3)])
    servico.estornar(esc, "Estorno para testar a trilha da retificação", usuario=gestor)
    assert RegistroAuditoria.objects.filter(acao="receita_mensal.a_retificar_por_estorno").exists()


# --- X17: o aviso de CRT 1, 2 ou 4 com IBS/CBS vale só para 2026 ---------------------------------


def test_aviso_de_ibscbs_em_crt_1_so_aparece_em_2026(escritorio_a, gestor, empresa):
    documento_2026 = _nota(
        escritorio_a,
        gestor,
        numero=44,
        crt="1",
        dh_emi="2026-03-15T10:00:00-03:00",
        ibscbs_total=("100.00", "0.10", "0.90"),
    )
    documento_2027 = _nota(
        escritorio_a,
        gestor,
        numero=45,
        crt="1",
        dh_emi="2027-03-15T10:00:00-03:00",
        ibscbs_total=("100.00", "0.10", "0.90"),
    )
    codigos_2026 = {
        a.codigo for a in servico.avisos_ibscbs(documento_2026, itens_nfe.ler_itens(documento_2026))
    }
    codigos_2027 = {
        a.codigo for a in servico.avisos_ibscbs(documento_2027, itens_nfe.ler_itens(documento_2027))
    }
    assert "ibscbs_presente_em_crt_1_2_4" in codigos_2026
    assert "ibscbs_presente_em_crt_1_2_4" not in codigos_2027


# --- M7b e M7c: a conferência e a lista não trazem a outra empresa --------------------------------


def test_lista_e_conferencia_nao_trazem_notas_de_outra_empresa_do_mesmo_escritorio(
    escritorio_a, gestor, empresa, outra_empresa
):
    _nota(escritorio_a, gestor, numero=46)
    _nota(escritorio_a, gestor, numero=47)
    _nota(
        escritorio_a,
        gestor,
        numero=48,
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    notas_a = servico.notas_do_mes(empresa, 2026, 3)
    assert len(notas_a) == 2
    assert all(n.vinculo.empresa_id == empresa.pk for n in notas_a)
    conferencia = servico.conferencia_do_mes(empresa, 2026, 3)
    assert conferencia.recebidas == 2
    assert conferencia.pendentes == 2

    # A receita por natureza da conferência também filtra a empresa: a nota EFETIVADA de outra
    # empresa não aparece na conferência de `empresa` (M7b).
    efetivada_b = _nota(
        escritorio_a,
        gestor,
        numero=50,
        valor="70.00",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    servico.efetivar(_rascunho(gestor, outra_empresa, efetivada_b), usuario=gestor)
    assert servico.conferencia_do_mes(empresa, 2026, 3).receita_por_natureza == {}
    assert servico.conferencia_do_mes(outra_empresa, 2026, 3).valor_bruto_por_cfop == {
        "5102": Decimal("70.00")
    }


# --- E6: o vNFTot não substitui o vNF --------------------------------------------------------


def test_vnftot_diferente_nao_substitui_o_vnf_na_conferencia(escritorio_a, gestor, empresa):
    """vNF 100,00 (o valor da conferência) e vNFTot 999,00 (com IBS/CBS). A efetivação segue o
    vNF."""
    documento = _nota(
        escritorio_a,
        gestor,
        numero=49,
        ibscbs_total=("100.00", "0.10", "0.90"),
        ibscbs_total_vnftot="999.00",
    )
    esc = servico.efetivar(_rascunho(gestor, empresa, documento), usuario=gestor)
    assert esc.estado == "efetivada"
    assert esc.valor_nf == Decimal("100.00")
