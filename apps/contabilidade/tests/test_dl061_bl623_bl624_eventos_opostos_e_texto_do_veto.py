"""DL-061, etapa 2 — BL-623 (RC-155) e BL-624 (M3 da reconferência).

BL-623: o lançamento que debita e credita a MESMA coluna do PL com eventos
opostos (compra e venda de tesouraria, redução e aumento de capital) é
recusado em vez de mostrar o líquido — o número líquido não é evento nenhum.
A subscrição com integralização parcial continua saindo como "Aumento de
capital" pelo valor integralizado (é o par conta principal × retificadora do
MESMO evento), e a subscrição pura continua com efeito zero.

BL-624: o veto não sai com estorno (o lançamento efetivado é imutável), e a
mensagem tem de dizer isso — a saída prevista é a marcação manual por
lançamento (fatia 2, BL-605). Os textos antigos mandavam "estornar" ou
"dividir o lançamento", o que não resolve nada.
"""

from datetime import date

import pytest

from apps.contabilidade.services import (
    avaliar_emissao_da_dmpl,
    estornar_lancamento,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    COL,
    PL,
    C,
    D,
    _apurar,
    _caso_a,
    _celula,
    _conta,
    _contas_do_caso_b,
    _dec,
    _lancar,
    _lancar_itens,
)

pytestmark = pytest.mark.django_db

CAPITAL = COL.CAPITAL_SOCIAL
TESOURARIA = COL.ACOES_OU_QUOTAS_EM_TESOURARIA
LINHA_AUMENTO = "aumento_de_capital"
LINHA_AQUISICAO = "aquisicao_de_acoes_ou_quotas_em_tesouraria"


def _caso_com_tesouraria():
    empresa, contas, gestor = _caso_a()
    contas.update(_contas_do_caso_b(empresa, contas["pl"]))
    return empresa, contas, gestor


def _mensagem(dmpl, lista):
    itens = dmpl["pendencias"][lista]
    assert itens, f"{lista} deveria estar preenchida"
    return itens[0]["mensagem"]


def _linhas_de_evento(dmpl):
    """As linhas de evento da DMPL — sem "saldo_inicial"/"saldo_final", que
    trazem o saldo da coluna e não um movimento."""
    return [
        linha for linha in dmpl["linhas"] if linha["chave"] not in ("saldo_inicial", "saldo_final")
    ]


def _diz_a_verdade(mensagem):
    """BL-624: nada de mandar estornar ou dividir o lançamento (o efetivado é
    imutável); a saída dita é a marcação manual da fatia 2."""
    baixa = mensagem.lower()
    assert "estorne" not in baixa, mensagem
    assert "divida o lançamento" not in baixa, mensagem
    assert "marcação manual" in baixa, mensagem


# ---------------------------------------------------------------------------
# BL-623 — eventos opostos na mesma coluna são recusados (RC-155)
# ---------------------------------------------------------------------------


def test_compra_e_venda_de_acoes_em_tesouraria_no_mesmo_lancamento_e_recusada():
    """O caso M2 da reconferência: aquisição de 1.500 e alienação de 1.000 no
    MESMO lançamento — o líquido (500) não é evento nenhum e a emissão é
    recusada. O saldo da coluna continua correto (o veto não quebra o número)."""
    empresa, contas, _ = _caso_com_tesouraria()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta de ações em tesouraria",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is False
    (entrada,) = dmpl["pendencias"]["lancamentos_ambiguos"]
    assert entrada["colunas"] == ["Ações ou quotas em tesouraria"]
    # Nenhuma célula fabricada: o veto não publica evento nenhum…
    assert all(linha["valores"][TESOURARIA] == _dec("0.00") for linha in _linhas_de_evento(dmpl))
    # …mas o saldo final da coluna continua o efeito líquido real.
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("-500.00")


def test_reducao_e_aumento_de_capital_no_mesmo_lancamento_e_recusado():
    """Variante do capital (M2): `D capital 200 / D caixa 800 / C capital 1.000`
    — redução e aumento no mesmo lançamento; o líquido (800) seria publicado
    como "Aumento de capital" e não é evento nenhum."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Redução e aumento de capital no mesmo lançamento",
        [
            (contas["capital"], "D", "200.00"),
            (contas["caixa"], "D", "800.00"),
            (contas["capital"], "C", "1000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert dmpl["pendencias"]["lancamentos_ambiguos"]
    assert all(linha["valores"][CAPITAL] == _dec("0.00") for linha in _linhas_de_evento(dmpl))


def test_duas_contas_de_tesouraria_nos_dois_lados_tambem_sao_eventos_opostos():
    """A propriedade é a NATUREZA cadastrada, não o nome da conta: duas
    retificadoras da mesma coluna, uma em cada lado, são eventos opostos."""
    empresa, contas, _ = _caso_com_tesouraria()
    outra_tesouraria = _conta(
        empresa,
        "3.8",
        "(-) Ações em Tesouraria — Outra Série",
        PL,
        D,
        dmpl=TESOURARIA,
        pai=contas["pl"],
    )
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Troca entre séries de ações em tesouraria",
        [
            (contas["tesouraria"], "D", "600.00"),
            (contas["caixa"], "D", "100.00"),
            (outra_tesouraria, "C", "500.00"),
            (contas["caixa"], "C", "200.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert dmpl["pendencias"]["lancamentos_ambiguos"]


def test_subscricao_com_integralizacao_parcial_continua_aumento_de_capital_liquido():
    """O que NÃO muda (RC-155): `D caixa 20.000 / D (-) capital a integralizar
    10.000 / C capital 30.000` é UM evento — o par conta principal ×
    retificadora — e sai como "Aumento de capital" pelo valor integralizado."""
    empresa, contas, _ = _caso_a()
    a_integralizar = _conta(
        empresa,
        "3.7",
        "(-) Capital a Integralizar",
        PL,
        D,
        dmpl=CAPITAL,
        pai=contas["pl"],
    )
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Subscrição com integralização parcial",
        [
            (contas["caixa"], "D", "20000.00"),
            (a_integralizar, "D", "10000.00"),
            (contas["capital"], "C", "30000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, LINHA_AUMENTO, CAPITAL) == _dec("20000.00")


def test_subscricao_pura_contra_a_retificadora_continua_efeito_zero():
    empresa, contas, _ = _caso_a()
    a_integralizar = _conta(
        empresa,
        "3.7",
        "(-) Capital a Integralizar",
        PL,
        D,
        dmpl=CAPITAL,
        pai=contas["pl"],
    )
    _lancar(
        empresa,
        date(2026, 2, 5),
        "Subscrição ainda não integralizada",
        a_integralizar,
        contas["capital"],
        "50000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert not any(
        linha["valores"].get(CAPITAL, _dec("0.00")) != _dec("0.00")
        for linha in _linhas_de_evento(dmpl)
    )
    assert dmpl["saldo_final"]["valores"][CAPITAL] == _dec("100000.00")


def test_reserva_debitada_e_creditada_com_outra_partida_continua_vetada():
    """Regressão da N7: nas reservas de lucros o veto continua — a DLPA lê
    item a item e a DMPL somaria por coluna."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Reserva debitada e creditada com lucros",
        [
            (contas["reserva_legal"], "D", "3300.00"),
            (contas["reserva_legal"], "C", "1300.00"),
            (contas["lucros"], "C", "2000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert dmpl["pendencias"]["lancamentos_ambiguos"]


def test_lucros_e_prejuizos_na_mesma_coluna_continuam_fora_da_regra():
    """Regressão da exceção registrada (M1/BL-622): a coluna de lucros
    acumulados fica de fora do veto — a DLPA também soma os itens."""
    empresa, contas, _ = _caso_a()
    _lancar_itens(
        empresa,
        date(2026, 3, 20),
        "Compensação de prejuízo com lucro e capitalização de dividendo",
        [
            (contas["prejuizos"], "D", "2700.00"),
            (contas["dividendos"], "D", "1500.00"),
            (contas["lucros"], "C", "2700.00"),
            (contas["capital"], "C", "1500.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert not dmpl["pendencias"]["lancamentos_ambiguos"], dmpl["pendencias"]
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]


def test_tesouraria_com_natureza_fora_do_padrao_tambem_e_eventos_opostos():
    """Limite achado na auditoria da etapa 2 (A2): na coluna de tesouraria a
    direção define eventos opostos por construção (aquisição × alienação), e o
    veto não pode depender da natureza cadastrada — conta de tesouraria
    creditada como "credora" não escapa do veto publicando o líquido."""
    empresa, contas, _ = _caso_com_tesouraria()
    tesouraria_credora = _conta(
        empresa,
        "3.8",
        "Ações em Tesouraria (credora)",
        PL,
        C,
        dmpl=TESOURARIA,
        pai=contas["pl"],
    )
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Compra e venda de tesouraria com conta fora do padrão",
        [
            (contas["tesouraria"], "D", "600.00"),
            (contas["caixa"], "D", "50.00"),
            (tesouraria_credora, "C", "500.00"),
            (contas["caixa"], "C", "150.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    assert dmpl["pendencias"]["lancamentos_ambiguos"]
    # O veto não publica evento nenhum, e o saldo segue o efeito líquido real
    # da coluna (crédito 500 − débito 600 = −100).
    assert dmpl["saldo_final"]["valores"][TESOURARIA] == _dec("-100.00")


def test_a_mensagem_dos_eventos_opostos_nomeia_a_coluna_e_diz_a_verdade():
    empresa, contas, _ = _caso_com_tesouraria()
    _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta de ações em tesouraria",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    dmpl = _apurar(empresa)
    mensagem = _mensagem(dmpl, "lancamentos_ambiguos")
    assert "eventos opostos" in mensagem
    _diz_a_verdade(mensagem)


# ---------------------------------------------------------------------------
# BL-624 — o estorno não libera, e a mensagem não manda fazer o impossível
# ---------------------------------------------------------------------------


def test_estorno_do_dividendo_em_reserva_nao_libera_e_a_mensagem_diz_a_verdade():
    """Caso (a) da M3: `D dividendos a pagar / C reserva legal` vetado; o
    estorno exato existe e mesmo assim NÃO libera a emissão — e a mensagem
    não pode mandar estornar nem dividir o lançamento."""
    empresa, contas, gestor = _caso_a()
    pagamento = _lancar(
        empresa,
        date(2026, 3, 10),
        "Dividendo pago com a reserva legal",
        contas["dividendos"],
        contas["reserva_legal"],
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    _diz_a_verdade(_mensagem(dmpl, "contrapartidas_sem_classificacao"))

    estornar_lancamento(pagamento, data=date(2026, 3, 20), criado_por=gestor)
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    _diz_a_verdade(_mensagem(dmpl, "contrapartidas_sem_classificacao"))


def test_estorno_do_lancamento_ambiguo_nao_libera_e_a_mensagem_diz_a_verdade():
    """Caso (b) da M3: o lançamento ambíguo estornado continua na lista — e o
    texto diz que a saída é a marcação manual, não o estorno."""
    empresa, contas, gestor = _caso_a()
    ambiguo = _lancar_itens(
        empresa,
        date(2026, 3, 10),
        "Ambíguo de propósito",
        [
            (contas["reserva_legal"], "D", "300.00"),
            (contas["lucros"], "D", "200.00"),
            (contas["capital"], "C", "500.00"),
        ],
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    _diz_a_verdade(_mensagem(dmpl, "lancamentos_ambiguos"))

    estornar_lancamento(ambiguo, data=date(2026, 3, 20), criado_por=gestor)
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    _diz_a_verdade(_mensagem(dmpl, "lancamentos_ambiguos"))


def test_nenhuma_das_acoes_da_tela_da_dmpl_manda_estornar_ou_dividir():
    """BL-624 (A3 da auditoria): a AÇÃO que a tela oferece ao lado de cada
    lista de pendência também não pode mandar estornar nem dividir — era a
    única parte do texto sem guarda de regressão."""
    from apps.contabilidade import views_web

    for lista, acao in views_web.ACAO_QUE_RESOLVE_A_PENDENCIA_DA_DMPL_POR_LISTA.items():
        baixa = acao.lower()
        assert "estorne" not in baixa, (lista, acao)
        assert "divida" not in baixa, (lista, acao)


def test_nenhuma_das_mensagens_de_veto_da_dmpl_manda_estornar_ou_dividir():
    """Propriedade sobre os textos: nenhuma mensagem de pendência da DMPL
    oferece como saída um estorno ou uma divisão de lançamento — o livro
    efetivado não muda, e dizer o contrário é orientação falsa (M3)."""
    empresa, contas, _ = _caso_a()
    proposto = _conta(
        empresa,
        "3.7",
        "Dividendo Adicional Proposto",
        PL,
        C,
        pai=contas["pl"],
    )
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Movimento sem coluna",
        contas["caixa"],
        proposto,
        "100.00",
    )
    dmpl = _apurar(empresa)
    for lista, itens in dmpl["pendencias"].items():
        for item in itens:
            mensagem = item.get("mensagem", "")
            assert "estorne" not in mensagem.lower(), (lista, mensagem)
            assert "divida o lançamento" not in mensagem.lower(), (lista, mensagem)
