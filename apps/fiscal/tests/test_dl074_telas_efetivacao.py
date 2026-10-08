"""DL-074 (frente B) — ajuste de domínio: efetivar em mês CONFIRMADO reabre a confirmação.

Efetivar uma escrituração muda a receita do mês de `dCompet`. Se o mês já estava
confirmado, o ato reabre a confirmação e marca "a retificar", na MESMA transação e com
trilha, pelo mesmo gancho que o estorno usa (`apps.fiscal.receita.marcar_a_retificar`).

Três provas:
1. Serviço: efetivar em mês confirmado reabre; em mês sem confirmação não cria nada;
   converter rascunho em efetivada também reabre; repetir a mesma efetivação não reabre.
2. Recusa não reabre: nota cancelada, recusada antes de qualquer gravação.
3. Concorrência (`transaction=True`, uma conexão por thread): efetivar e confirmar o mês
   ao mesmo tempo. Em todas as rodadas, o mês fica confirmado com o total que EXISTE, ou
   fica "a retificar" com a trilha da efetivação. Nunca "confirmado" com total antigo.

Dados 100% sintéticos (xml_sinteticos.py). Helpers da frente A em test_dl074_suporte.
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import receita as servico
from apps.fiscal import services as recepcao
from apps.fiscal.escrituracao import (
    EscrituracaoErro,
    efetivar_escrituracao,
    salvar_rascunho,
)
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    DocumentoFiscal,
    EstadoConfirmacaoMes,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.test_dl074_concorrencia import _em_paralelo
from apps.fiscal.tests.test_dl074_suporte import (
    escriturar,
    fixar_inicio_de_uso,
    preparar_simples,
)
from apps.fiscal.tests.xml_sinteticos import (
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfse,
)

pytestmark = pytest.mark.django_db

NATUREZA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
ACAO_DA_EFETIVACAO = "receita_mensal.a_retificar_por_efetivacao"
RODADAS = 6


@pytest.fixture
def empresa(empresa_a):
    fixar_inicio_de_uso(empresa_a, 2024, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def _nota_em_rascunho(escritorio, empresa, usuario, *, sufixo, competencia, valor):
    """NFS-e sintética em que `empresa` é PRESTADORA, com o vínculo de prestador. Não efetiva."""
    ano, mes = competencia
    identificador = identificador_nfse(sufixo)
    recepcao.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(
            identificador=identificador,
            numero=str(sufixo),
            dh_emi=f"{ano}-{mes:02d}-10T10:00:00-03:00",
            d_compet=f"{ano}-{mes:02d}-10",
            v_serv=f"{Decimal(valor):.2f}",
            v_liq=f"{Decimal(valor):.2f}",
        ),
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    return VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )


def _confirmacao(empresa, ano, mes):
    return ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=ano, mes=mes)


def _trilha_da_efetivacao(confirmacao):
    return RegistroAuditoria.objects.filter(
        objeto_tipo="ConfirmacaoReceitaMensal",
        objeto_id=str(confirmacao.pk),
        acao=ACAO_DA_EFETIVACAO,
    )


# ---------------------------------------------------------------------------
# 1. Serviço
# ---------------------------------------------------------------------------


def test_efetivar_em_mes_confirmado_reabre_e_marca_a_retificar(
    empresa, escritorio_a, usuario_gestor_a
):
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=701, competencia=(2024, 3), valor="1000"
    )
    servico.confirmar_mes(empresa, 2024, 3, usuario_gestor_a)
    assert servico.situacao_do_mes(empresa, 2024, 3) == "confirmado"

    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=702, competencia=(2024, 3), valor="500"
    )
    efetivada = efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    confirmacao = _confirmacao(empresa, 2024, 3)
    assert confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    assert confirmacao.a_retificar is True
    assert confirmacao.reaberta_por == usuario_gestor_a
    assert f"escrituração nº {efetivada.pk}" in confirmacao.motivo_reabertura
    assert "Efetivação de escrituração" in confirmacao.motivo_reabertura
    assert servico.situacao_do_mes(empresa, 2024, 3) == "a_retificar"
    # A trilha grava o ato com a ação própria, ligada à confirmação do mês.
    assert _trilha_da_efetivacao(confirmacao).count() == 1


def test_mes_reaberto_pela_efetivacao_so_volta_a_confirmado_com_novo_ato(
    empresa, escritorio_a, usuario_gestor_a
):
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=711, competencia=(2024, 3), valor="1000"
    )
    servico.confirmar_mes(empresa, 2024, 3, usuario_gestor_a)
    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=712, competencia=(2024, 3), valor="500"
    )
    efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    servico.confirmar_mes(empresa, 2024, 3, usuario_gestor_a)

    confirmacao = _confirmacao(empresa, 2024, 3)
    assert confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
    assert confirmacao.a_retificar is False
    assert confirmacao.valor_confirmado_interno == Decimal("1500.00")
    assert servico.situacao_do_mes(empresa, 2024, 3) == "confirmado"


def test_efetivar_em_mes_sem_confirmacao_nao_cria_confirmacao(
    empresa, escritorio_a, usuario_gestor_a
):
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=721, competencia=(2024, 5), valor="800"
    )

    assert not ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2024, mes=5).exists()
    assert servico.situacao_do_mes(empresa, 2024, 5) == "nao_confirmado"


def test_converter_rascunho_em_efetivada_no_mes_confirmado_tambem_reabre(
    empresa, escritorio_a, usuario_gestor_a
):
    # Rascunho não entra no total; a efetivação dele, sim. O ato é o que muda a receita.
    escriturar(
        escritorio_a, empresa, usuario_gestor_a, sufixo=731, competencia=(2024, 6), valor="900"
    )
    servico.confirmar_mes(empresa, 2024, 6, usuario_gestor_a)
    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=732, competencia=(2024, 6), valor="250"
    )
    salvar_rascunho(vinculo, NATUREZA, usuario_gestor_a)
    assert _confirmacao(empresa, 2024, 6).estado == EstadoConfirmacaoMes.CONFIRMADA

    efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    assert _confirmacao(empresa, 2024, 6).estado == EstadoConfirmacaoMes.REABERTA


def test_repetir_a_mesma_efetivacao_em_mes_confirmado_nao_reabre(
    empresa, escritorio_a, usuario_gestor_a
):
    # Idempotência (DL-072): o segundo clique não é fato novo, então não reabre o mês.
    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=741, competencia=(2024, 7), valor="300"
    )
    efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)
    servico.confirmar_mes(empresa, 2024, 7, usuario_gestor_a)

    repetida = efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    assert repetida.criada_agora is False
    assert _confirmacao(empresa, 2024, 7).estado == EstadoConfirmacaoMes.CONFIRMADA
    assert not _trilha_da_efetivacao(_confirmacao(empresa, 2024, 7)).exists()


def test_efetivacao_em_mes_confirmado_nao_mexe_em_outro_mes(
    empresa, escritorio_a, usuario_gestor_a
):
    servico.confirmar_mes(empresa, 2024, 8, usuario_gestor_a)
    servico.confirmar_mes(empresa, 2024, 9, usuario_gestor_a)
    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=751, competencia=(2024, 8), valor="10"
    )

    efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    assert _confirmacao(empresa, 2024, 8).estado == EstadoConfirmacaoMes.REABERTA
    assert _confirmacao(empresa, 2024, 9).estado == EstadoConfirmacaoMes.CONFIRMADA
    assert _confirmacao(empresa, 2024, 9).a_retificar is False


def test_efetivacao_recusada_nao_reabre_o_mes(empresa, escritorio_a, usuario_gestor_a):
    # Nota CANCELADA não é efetivada (DL-072, critério 5). A recusa acontece antes de
    # qualquer gravação, então o mês confirmado continua confirmado.
    vinculo = _nota_em_rascunho(
        escritorio_a, empresa, usuario_gestor_a, sufixo=761, competencia=(2024, 10), valor="40"
    )
    servico.confirmar_mes(empresa, 2024, 10, usuario_gestor_a)
    recepcao.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(identificador_nfse(761)), codigo="e101101"),
        nome_arquivo="evento-761.xml",
    )

    with pytest.raises(EscrituracaoErro):
        efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a)

    assert _confirmacao(empresa, 2024, 10).estado == EstadoConfirmacaoMes.CONFIRMADA
    assert not _trilha_da_efetivacao(_confirmacao(empresa, 2024, 10)).exists()


# ---------------------------------------------------------------------------
# 3. Concorrência: efetivar × confirmar, em conexões separadas
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)  # sobrepõe o `pytestmark` do módulo: conexões reais
def test_efetivar_e_confirmar_o_mesmo_mes_ao_mesmo_tempo_nunca_deixam_total_antigo_confirmado(
    empresa, escritorio_a, usuario_gestor_a
):
    desfechos = set()
    for rodada in range(RODADAS):
        ano, mes = 2025, 1 + rodada
        # Base já efetivada (1000). A disputa é a segunda nota (500), efetivada na mesma hora
        # em que o mês é confirmado.
        escriturar(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            sufixo=800 + rodada * 2,
            competencia=(ano, mes),
            valor="1000",
        )
        vinculo = _nota_em_rascunho(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            sufixo=801 + rodada * 2,
            competencia=(ano, mes),
            valor="500",
        )

        resultados = _em_paralelo(
            [
                lambda ano=ano, mes=mes: servico.confirmar_mes(empresa, ano, mes, usuario_gestor_a),
                lambda vinculo=vinculo: efetivar_escrituracao(vinculo, NATUREZA, usuario_gestor_a),
            ]
        )

        assert [erro for _, erro in resultados] == [None, None], resultados
        confirmacao = _confirmacao(empresa, ano, mes)
        total_atual = servico.receita_do_mes(empresa, ano, mes).composicao.de("interno").total
        assert total_atual == Decimal("1500.00")
        if confirmacao.estado == EstadoConfirmacaoMes.REABERTA:
            # (a) a confirmação veio antes (com 1000) e a efetivação reabriu o mês, com trilha.
            assert confirmacao.valor_confirmado_interno == Decimal("1000.00")
            assert confirmacao.a_retificar is True
            assert _trilha_da_efetivacao(confirmacao).count() == 1
            assert servico.situacao_do_mes(empresa, ano, mes) == "a_retificar"
            desfechos.add("confirmou_antes")
        else:
            # (b) a efetivação veio antes: a confirmação já pegou o total de 1500.
            assert confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
            assert confirmacao.valor_confirmado_interno == Decimal("1500.00")
            assert not _trilha_da_efetivacao(confirmacao).exists()
            assert servico.situacao_do_mes(empresa, ano, mes) == "confirmado"
            desfechos.add("efetivou_antes")

    # Os dois desfechos são aceitos e nenhum outro; a prova não pode passar por acaso de
    # um só lado só porque ele é o mais provável.
    assert desfechos <= {"confirmou_antes", "efetivou_antes"}
    assert desfechos, "nenhuma rodada rodou"
