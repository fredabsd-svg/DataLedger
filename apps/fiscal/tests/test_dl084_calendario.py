"""DL-084, itens 1 e 2 (puro, sem banco): vencimento antecipado por dia sem expediente bancário, e
avisos de feriado local que não mudam a data.

As datas esperadas estão ESCRITAS À MÃO nos comentários e nas asserções. Elas não vêm do código
sob teste. Anos escolhidos: com Páscoa em março (2024, 2032) e em abril (2028, 2029, 2033, 2034).
"""

from datetime import date

import pytest

from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab

# ---------------------------------------------------------------------------
# Páscoa e dias sem expediente, com datas escritas à mão
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ano", "pascoa"),
    [
        (2024, date(2024, 3, 31)),  # Páscoa em março
        (2032, date(2032, 3, 28)),  # Páscoa em março
        (2028, date(2028, 4, 16)),  # Páscoa em abril
        (2033, date(2033, 4, 17)),  # Páscoa em abril
        (2034, date(2034, 4, 9)),  # Páscoa em abril
    ],
)
def test_pascoa_em_anos_de_marco_e_de_abril(ano, pascoa):
    assert calc.pascoa(ano) == pascoa


def test_dias_sem_expediente_de_2028_sao_as_quatro_datas_escritas_a_mao():
    # Páscoa 16/04/2028. Segunda de Carnaval = 28/02 (P−48); terça = 29/02 (P−47); Sexta-feira
    # Santa = 14/04 (P−2); Corpus Christi = 15/06 (P+60).
    assert set(calc.dias_sem_expediente_bancario(2028)) == {
        date(2028, 2, 28),
        date(2028, 2, 29),
        date(2028, 4, 14),
        date(2028, 6, 15),
    }


def test_dias_sem_expediente_de_2024_com_pascoa_em_marco():
    # Páscoa 31/03/2024. Segunda de Carnaval 12/02; terça 13/02; Sexta-feira Santa 29/03; Corpus
    # Christi 30/05.
    assert set(calc.dias_sem_expediente_bancario(2024)) == {
        date(2024, 2, 12),
        date(2024, 2, 13),
        date(2024, 3, 29),
        date(2024, 5, 30),
    }


def test_toda_entrada_da_tabela_de_dias_sem_expediente_tem_fonte():
    # Cada dia da tabela cita a fonte (norma ou instrução lida). Sem fonte, não entra.
    assert len(tab.DIAS_SEM_EXPEDIENTE_BANCARIO) == 4
    for _deslocamento, nome, fonte in tab.DIAS_SEM_EXPEDIENTE_BANCARIO:
        assert nome and "lida" in fonte, nome


# ---------------------------------------------------------------------------
# Critério 1: vencimento antecipado nas quatro datas (último dia útil do mês)
# ---------------------------------------------------------------------------


def test_sexta_feira_santa_antecipa_em_ano_de_pascoa_em_marco():
    # Março de 2024: 31/03 é domingo; 30/03 sábado; 29/03 é Sexta-feira Santa (sem expediente).
    # Recua para quinta, 28/03/2024.
    assert calc.ultimo_dia_util(2024, 3) == (date(2024, 3, 28), True)


def test_sexta_feira_santa_antecipa_em_ano_de_pascoa_em_abril():
    # Março de 2029: 31/03 é sábado; 30/03 é Sexta-feira Santa (Páscoa 01/04/2029). Recua para
    # quinta, 29/03/2029.
    assert calc.ultimo_dia_util(2029, 3) == (date(2029, 3, 29), True)


def test_terca_de_carnaval_antecipa_com_a_segunda_no_mesmo_recuo():
    # Fevereiro de 2028: 29/02 é terça de Carnaval (Páscoa 16/04/2028). 28/02 é segunda de Carnaval.
    # 27 e 26 são fim de semana. Sexta 25/02/2028 é o dia útil.
    assert calc.ultimo_dia_util(2028, 2) == (date(2028, 2, 25), True)


def test_segunda_de_carnaval_antecipa_quando_e_o_ultimo_dia_do_mes():
    # Fevereiro de 2033: 28/02 é segunda de Carnaval (Páscoa 17/04/2033). Recua pelo fim de semana
    # até sexta 25/02/2033.
    assert calc.ultimo_dia_util(2033, 2) == (date(2033, 2, 25), True)


def test_corpus_christi_antecipa_quando_cai_no_ultimo_dia_do_mes():
    # Maio de 2029: 31/05 é quinta, Corpus Christi (Páscoa 01/04/2029 + 60). Recua para quarta,
    # 30/05/2029.
    assert calc.ultimo_dia_util(2029, 5) == (date(2029, 5, 30), True)


def test_fim_de_semana_recua_sem_marcar_antecipacao():
    # 31/10/2026 é sábado: recua para sexta 30/10. Não há dia sem expediente, então não antecipa.
    assert calc.ultimo_dia_util(2026, 10) == (date(2026, 10, 30), False)


def test_corpus_christi_fora_do_ultimo_dia_nao_altera_o_vencimento():
    # 30/05/2024 é Corpus Christi, mas o último dia útil de maio de 2024 é 31/05 (sexta). Corpus
    # não está nesse dia, então o vencimento fica e não antecipa.
    assert calc.ultimo_dia_util(2024, 5) == (date(2024, 5, 31), False)


def test_fevereiro_sem_carnaval_no_fim_do_mes_nao_antecipa():
    # 2027: 28/02 é domingo; 26/02 sexta é o dia útil. Carnaval de 2027 é 08 e 09/02, longe do fim.
    assert calc.ultimo_dia_util(2027, 2) == (date(2027, 2, 26), False)


def test_20_de_novembro_de_2026_e_feriado_nacional_e_recua_o_vencimento_de_novembro():
    # 20/11/2026 é sexta. Não é o último dia do mês, então nenhuma quota muda. A função reconhece.
    assert calc.feriado_nacional_fixo(date(2026, 11, 20)) is True
    assert calc.ultimo_dia_util(2026, 11) == (date(2026, 11, 30), False)


def test_quotas_do_trimestre_de_marco_de_2029_antecipam_a_de_maio_pelo_corpus_christi():
    # Trimestre de março de 2029. 1ª quota: 30/04 (segunda). 2ª: último dia de maio é 31/05, quinta,
    # Corpus Christi, então vence em 30/05. 3ª: 30/06 é sábado, vence em 29/06 (sexta).
    opcoes = calc.opcoes_de_quota(_d("3000.00"), 2029, 1)
    assert [p.vencimento for p in opcoes.tres_quotas] == [
        date(2029, 4, 30),
        date(2029, 5, 30),
        date(2029, 6, 29),
    ]
    segunda = opcoes.tres_quotas[1]
    assert segunda.antecipada_de == date(2029, 5, 31)
    assert segunda.aviso_calendario is False
    assert opcoes.tres_quotas[0].antecipada_de is None


def _d(texto):
    from decimal import Decimal

    return Decimal(texto)


# ---------------------------------------------------------------------------
# Critério 2: feriado local mostra o aviso e não muda a data; dois níveis; exceção por ano
# ---------------------------------------------------------------------------

_LEI_SEM_FONTE = ("Lei estadual 098/1989, art. 1º (teste)",)


def _estadual(mes, dia, fonte="", excecoes=()):
    return calc.FeriadoLocalDado(
        descricao="feriado de teste",
        mes=mes,
        dia=dia,
        vigencia_inicio=date(1990, 1, 1),
        vigencia_fim=None,
        fonte_bancaria=fonte,
        excecoes=tuple(excecoes),
    )


FONTE_FEBRABAN = "Febraban (teste sintético)"


def test_feriado_local_com_fonte_bancaria_da_dois_avisos_de_praca():
    # Dia 19/03/2027 em Palmas: a lista bancária confirma o fechamento. Dois avisos.
    feriados = (_estadual(3, 19, fonte=FONTE_FEBRABAN),)
    assert calc.avisos_de_feriado_local(date(2027, 3, 19), feriados, "Palmas") == (
        "feriado bancário em Palmas (Febraban)",
        "antecipar: sem expediente bancário na praça",
    )


def test_feriado_local_sem_fonte_bancaria_da_o_aviso_mais_fraco():
    # 05/10/2027 em Palmas: a lei estadual fixa, mas a lista não confirma. Aviso fraco.
    feriados = (_estadual(10, 5),)
    assert calc.avisos_de_feriado_local(date(2027, 10, 5), feriados, "Palmas") == (
        "feriado local: confirmar expediente bancário na praça",
    )


def test_data_sem_feriado_local_nao_tem_aviso():
    feriados = (_estadual(10, 5),)
    assert calc.avisos_de_feriado_local(date(2027, 10, 6), feriados, "Palmas") == ()


def test_excecao_do_ano_move_o_aviso_para_a_data_observada_e_tira_da_normativa():
    # 2026: o 05/10 foi observado em 09/10 (decreto). Na data normativa não há aviso; na observada,
    # há o aviso bancário (lista da praça).
    excecao = calc.ExcecaoFeriadoDado(
        ano=2026, data_observada=date(2026, 10, 9), fonte_bancaria=FONTE_FEBRABAN
    )
    feriados = (_estadual(10, 5, excecoes=(excecao,)),)
    assert calc.avisos_de_feriado_local(date(2026, 10, 5), feriados, "Palmas") == ()
    assert calc.avisos_de_feriado_local(date(2026, 10, 9), feriados, "Palmas") == (
        "feriado bancário em Palmas (Febraban)",
        "antecipar: sem expediente bancário na praça",
    )


def test_excecao_nao_se_aplica_a_outro_ano():
    # A exceção de 2026 não muda 2027: em 2027 o 05/10 volta a ser a data normativa, com aviso
    # fraco.
    excecao = calc.ExcecaoFeriadoDado(ano=2026, data_observada=date(2026, 10, 9), fonte_bancaria="")
    feriados = (_estadual(10, 5, excecoes=(excecao,)),)
    assert calc.avisos_de_feriado_local(date(2027, 10, 5), feriados, "Palmas") == (
        "feriado local: confirmar expediente bancário na praça",
    )


def test_feriado_local_fora_da_vigencia_nao_avisa():
    feriado = calc.FeriadoLocalDado(
        descricao="transitório",
        mes=6,
        dia=10,
        vigencia_inicio=date(2000, 1, 1),
        vigencia_fim=date(2001, 12, 31),
        fonte_bancaria="",
    )
    assert calc.avisos_de_feriado_local(date(2026, 6, 10), (feriado,), "Palmas") == ()


def test_aviso_de_feriado_local_nao_muda_a_data_do_vencimento():
    # Feriado SINTÉTICO (só para teste) no dia de uma quota: 29/06/2029 é a 3ª quota. O aviso sai,
    # e a data fica como o cálculo a deu. Quem muda a data é o calendário nacional, nunca isto.
    from apps.fiscal import presumido as servico

    opcoes = calc.opcoes_de_quota(_d("3000.00"), 2029, 1)
    feriado_sintetico = _estadual(6, 29, fonte=FONTE_FEBRABAN)
    com_aviso = servico._com_avisos_locais(opcoes, "Palmas", (feriado_sintetico,))
    terceira = com_aviso.tres_quotas[2]
    assert terceira.vencimento == date(2029, 6, 29)
    assert terceira.avisos_locais == (
        "feriado bancário em Palmas (Febraban)",
        "antecipar: sem expediente bancário na praça",
    )
    assert [p.vencimento for p in com_aviso.tres_quotas] == [
        p.vencimento for p in opcoes.tres_quotas
    ]


def test_sem_praca_ou_sem_feriados_as_opcoes_voltam_intactas():
    from apps.fiscal import presumido as servico

    opcoes = calc.opcoes_de_quota(_d("3000.00"), 2029, 1)
    assert servico._com_avisos_locais(opcoes, None, ()) is opcoes


def test_chave_de_municipio_ignora_acento_caixa_e_espacos():
    assert calc.chave_municipio("Palmas") == "PALMAS"
    assert calc.chave_municipio("  Araguaína ") == "ARAGUAINA"
    assert calc.chave_municipio("São   Paulo") == "SAO PAULO"


def test_avisos_de_feriado_local_pedem_a_praca_pelo_nome_recebido():
    # O nome da praça vai na mensagem: o aviso não diz "Palmas" para um município de outro nome.
    feriados = (_estadual(8, 15, fonte=FONTE_FEBRABAN),)
    assert calc.avisos_de_feriado_local(date(2027, 8, 15), feriados, "Araguaína") == (
        "feriado bancário em Araguaína (Febraban)",
        "antecipar: sem expediente bancário na praça",
    )
