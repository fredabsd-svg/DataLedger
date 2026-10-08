"""DL-074 (frente A) — concorrência entre confirmação, estorno e receita informada.

Cada thread usa a SUA conexão de PostgreSQL, por isso o teste é `transaction=True`: sem
commit real uma thread não enxergaria a outra (mesmo padrão de
`test_dl072_concorrencia.py`).

Três provas:
1. Confirmar o mês e estornar a escrituração ao mesmo tempo, em rodadas repetidas. Os
   dois desfechos possíveis são aceitos, e nenhum outro: (a) confirmou antes → o mês fica
   "a retificar" (reaberto, com a marca); (b) estornou antes → o mês foi confirmado com o
   total já sem a escrituração. Nunca fica "confirmado" com o total antigo.
2. Duas confirmações do mesmo mês ao mesmo tempo: uma passa, a outra recebe erro de
   negócio (409), e há UMA linha.
3. Confirmar receita informada e confirmar o mês ao mesmo tempo: ou a receita entra no
   total do mês, ou o mês fica confirmado sem ela e a receita fica em rascunho.

Todo `join()` tem timeout e uma asserção depois: thread travada vira falha visível.
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection

from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import receita as servico
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EstadoConfirmacaoMes,
    EstadoEscrituracao,
    EstadoReceitaInformada,
    MercadoReceita,
)
from apps.fiscal.tests.test_dl074_suporte import (
    escriturar,
    fixar_inicio_de_uso,
    preparar_simples,
)

pytestmark = pytest.mark.django_db(transaction=True)

TIMEOUT_SEGUNDOS = 30
RODADAS = 6


def _em_paralelo(alvos):
    """Roda `alvos` (callables) em threads, cada uma com a própria conexão.

    Devolve [(resultado, erro)] na ordem dos alvos. A barreira faz as threads partirem juntas.
    """
    barreira = threading.Barrier(len(alvos))
    resultados = [None] * len(alvos)

    def correr(indice, alvo):
        try:
            barreira.wait(timeout=TIMEOUT_SEGUNDOS)
            resultados[indice] = (alvo(), None)
        except BaseException as exc:  # noqa: BLE001 — o erro é o dado do teste
            resultados[indice] = (None, exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=correr, args=(i, a)) for i, a in enumerate(alvos)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=TIMEOUT_SEGUNDOS)
    assert not any(t.is_alive() for t in threads), "thread travada: falha, não espera infinita"
    assert all(r is not None for r in resultados), "alguma thread não devolveu resultado"
    return resultados


@pytest.fixture
def empresa(empresa_a):
    fixar_inicio_de_uso(empresa_a, 2024, 1)
    return preparar_simples(empresa_a, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1))


def test_confirmar_mes_e_estornar_escrituracao_ao_mesmo_tempo_nunca_deixa_total_antigo_confirmado(
    empresa, escritorio_a, usuario_gestor_a
):
    desfechos = []
    for rodada in range(RODADAS):
        ano, mes = 2024, 1 + rodada
        escrituracao = escriturar(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            sufixo=500 + rodada,
            competencia=(ano, mes),
            valor="1000",
        )

        resultados = _em_paralelo(
            [
                # Valores padrão prendem as variáveis do laço: cada alvo roda antes da
                # rodada seguinte (o `_em_paralelo` espera as threads).
                lambda ano=ano, mes=mes: servico.confirmar_mes(empresa, ano, mes, usuario_gestor_a),
                lambda escrituracao=escrituracao: servico_escrituracao.estornar_escrituracao(
                    escrituracao, "Nota cancelada.", usuario_gestor_a
                ),
            ]
        )

        assert [erro for _, erro in resultados] == [None, None], resultados
        escrituracao.refresh_from_db()
        assert escrituracao.estado == EstadoEscrituracao.ESTORNADA
        confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=ano, mes=mes)
        if confirmacao.estado == EstadoConfirmacaoMes.REABERTA:
            # (a) a confirmação veio antes: o estorno reabriu o mês e o marcou a retificar.
            assert confirmacao.a_retificar is True
            assert f"escrituração nº {escrituracao.pk}" in confirmacao.motivo_reabertura
            desfechos.append("confirmou_antes")
        else:
            # (b) o estorno veio antes: a confirmação já é do total sem a escrituração.
            assert confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
            assert confirmacao.valor_confirmado_interno == Decimal("0.00")
            assert servico.situacao_do_mes(empresa, ano, mes) == "confirmado"
            desfechos.append("estornou_antes")

    # Os desfechos são só os dois aceitos (a prova não depende de qual aconteceu em cada rodada).
    assert set(desfechos) <= {"confirmou_antes", "estornou_antes"}
    assert len(desfechos) == RODADAS


def test_duas_confirmacoes_do_mesmo_mes_ao_mesmo_tempo_uma_passa_e_a_outra_e_409(
    empresa, usuario_gestor_a
):
    resultados = _em_paralelo(
        [
            lambda: servico.confirmar_mes(empresa, 2024, 9, usuario_gestor_a),
            lambda: servico.confirmar_mes(empresa, 2024, 9, usuario_gestor_a),
        ]
    )

    sucessos = [r for r, erro in resultados if erro is None]
    erros = [erro for _, erro in resultados if erro is not None]
    assert len(sucessos) == 1, resultados
    assert len(erros) == 1
    assert isinstance(erros[0], servico.ReceitaErro), erros[0]
    assert ConfirmacaoReceitaMensal.objects.filter(empresa=empresa, ano=2024, mes=9).count() == 1


def test_confirmar_receita_e_confirmar_mes_ao_mesmo_tempo_sao_consistentes(
    empresa, usuario_gestor_a
):
    for rodada in range(RODADAS):
        ano, mes = 2023, 1 + rodada
        receita = servico.lancar_receita_informada(
            empresa,
            ano,
            mes,
            MercadoReceita.INTERNO,
            "100.00",
            "ajuste",
            "Motivo sintético.",
            "Suporte sintético.",
            usuario_gestor_a,
            situacao_iss="proprio_municipio",
        )

        resultados = _em_paralelo(
            [
                lambda receita=receita: servico.confirmar_receita_informada(
                    receita, usuario_gestor_a
                ),
                lambda ano=ano, mes=mes: servico.confirmar_mes(empresa, ano, mes, usuario_gestor_a),
            ]
        )

        receita_erro, mes_erro = resultados[0][1], resultados[1][1]
        assert mes_erro is None, resultados
        receita.refresh_from_db()
        confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=ano, mes=mes)
        if receita.estado == EstadoReceitaInformada.CONFIRMADA:
            # A receita veio antes: entrou no total que o mês confirmou.
            assert receita_erro is None
            assert confirmacao.valor_confirmado_interno == Decimal("100.00")
        else:
            # O mês veio antes: a receita foi recusada e continua em rascunho, fora do total.
            assert isinstance(receita_erro, servico.ReceitaErro), resultados
            assert confirmacao.valor_confirmado_interno == Decimal("0.00")
        assert servico.situacao_do_mes(empresa, ano, mes) == "confirmado"


def test_efetivacao_em_paralelo_com_confirmacao_deixa_o_mes_na_situacao_real(
    empresa, escritorio_a, usuario_gestor_a
):
    # Efetivar não passa pelo gancho. Se a confirmação vier antes da efetivação, o total
    # guardado no ato não bate com o atual e o mês fica "a retificar". Se vier depois, o ato
    # já pega a escrituração e o mês fica confirmado. Nos dois casos a situação segue o total.
    from apps.fiscal import services as recepcao
    from apps.fiscal.escrituracao import efetivar_escrituracao
    from apps.fiscal.models import DocumentoFiscal, PapelDocumento, VinculoDocumentoEmpresa
    from apps.fiscal.tests.test_dl074_suporte import NATUREZA_INTERNA
    from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

    ano, mes = 2022, 3
    identificador = identificador_nfse(602)
    recepcao.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(
            identificador=identificador,
            numero="602",
            d_compet="2022-03-10",
            dh_emi="2022-03-10T10:00:00-03:00",
            v_serv="20.00",
            v_liq="20.00",
        ),
        nome_arquivo="nota-602.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a, identificador=identificador)
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )

    resultados = _em_paralelo(
        [
            lambda: servico.confirmar_mes(empresa, ano, mes, usuario_gestor_a),
            lambda: efetivar_escrituracao(vinculo, NATUREZA_INTERNA, usuario_gestor_a),
        ]
    )

    assert [erro for _, erro in resultados] == [None, None], resultados
    total_atual = (
        servico.receita_do_mes(empresa, ano, mes).composicao.de(MercadoReceita.INTERNO).total
    )
    confirmacao = ConfirmacaoReceitaMensal.objects.get(empresa=empresa, ano=ano, mes=mes)
    if confirmacao.valor_confirmado_interno == total_atual:
        assert total_atual == Decimal("20.00")
        assert servico.situacao_do_mes(empresa, ano, mes) == "confirmado"
    else:
        assert confirmacao.valor_confirmado_interno == Decimal("0.00")
        assert servico.situacao_do_mes(empresa, ano, mes) == "a_retificar"
