"""DL-061, etapa 2 — BL-603 (RC-153): a coluna "dividendo adicional proposto"
na DMPL, com linha própria para a destinação e para a aprovação.

O caso do cliente que motivou a demanda: conta de PL "dividendo adicional
proposta" movimentada — antes da etapa 2 a emissão ficava VETADA por falta de
coluna. Agora os dois eventos têm linha definida e a identidade com a DLPA
vale por construção (mesma chave `dividendo_adicional_proposto` nas duas
apurações — a tabela de identidade é a fonte do teste).

Base normativa citada por NOME apenas: ICPC 08 (R1), Contabilização da
Proposta de Pagamento de Dividendos (CVM 683/12; CFC — ITG 08) — a proposta
além do mínimo obrigatório permanece no PL, em conta específica, até a
deliberação dos acionistas (PE-75: o texto integral não foi lido, e por isso
nenhum item numerado aparece em código nem em documento).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contabilidade.models import (
    ClassificacaoDlpa,
    Conta,
    TipoConta,
)
from apps.contabilidade.services import (
    apurar_dlpa,
    avaliar_emissao_da_dmpl,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    ANO,
    COL,
    LUCROS,
    MES,
    PL,
    C,
    _apurar,
    _caso_a,
    _celula,
    _conferir_identidade_com_a_dlpa,
    _conta,
    _dec,
    _empresa,
    _lancar,
    _plano_basico,
)

pytestmark = pytest.mark.django_db

DAP = COL.DIVIDENDO_ADICIONAL_PROPOSTO
LINHA_PROPOSTO = "dividendo_adicional_proposto"


def _linha_de(dmpl, chave):
    for linha in dmpl["linhas"]:
        if linha["chave"] == chave:
            return linha
    raise AssertionError(f"linha {chave!r} ausente em {[x['chave'] for x in dmpl['linhas']]}")


def _linha_da_dlpa(dlpa, chave):
    for linha in dlpa["linhas"]:
        if linha["chave"] == chave:
            return linha
    return None


def _proposto(empresa, contas):
    """A conta do cliente: PL, "Dividendo Adicional Proposto", com o par EXATO
    de classificações que a etapa 2 fixou (DLPA = coluna da DMPL)."""
    return _conta(
        empresa,
        "3.7",
        "Dividendo Adicional Proposto",
        PL,
        C,
        dmpl=DAP,
        dlpa=ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO,
        pai=contas["pl"],
    )


# ---------------------------------------------------------------------------
# A destinação (proposta) — linha própria, total zero, identidade com a DLPA
# ---------------------------------------------------------------------------


def test_destinacao_de_lucros_ao_proposto_e_linha_propria_com_total_zero():
    """D lucros / C dividendo adicional proposto: a coluna de lucros cai e a
    coluna nova sobe no MESMO valor — o total da linha é zero (é movimento
    interno do PL), e a DLPA mostra o mesmo evento na linha própria."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Proposta de dividendo adicional",
        contas["lucros"],
        proposto,
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_PROPOSTO, LUCROS) == _dec("-1000.00")
    assert _celula(dmpl, LINHA_PROPOSTO, DAP) == _dec("1000.00")
    assert _linha_de(dmpl, LINHA_PROPOSTO)["total"] == _dec("0.00")

    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    proposta = _linha_da_dlpa(dlpa, LINHA_PROPOSTO)
    assert proposta is not None
    assert proposta["valor"] == _dec("-1000.00")

    _conferir_identidade_com_a_dlpa(empresa)


def test_aprovacao_com_contrapartida_classificada_dividendo_vai_para_a_linha_dividendos():
    """D proposto / C dividendos a pagar (classificada como dividendo): o
    proposto sai do PL na MESMA leitura da DLPA — contrapartida classificada
    decide a linha "Dividendos", agora também na coluna nova."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 15),
        "Deliberação que transfere o proposto ao passivo",
        proposto,
        contas["dividendos"],
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, "dividendos", DAP) == _dec("-1000.00")
    # O caso A já distribui 10.000 de dividendos: a linha soma os dois fatos.
    assert _linha_de(dmpl, "dividendos")["total"] == _dec("-11000.00")

    # A DLPA não enxerga o evento: ele não toca a conta sujeito. O caso A já
    # distribui 10.000 de dividendos — o número da linha não muda aqui.
    dlpa = apurar_dlpa(empresa=empresa, ano=ANO, mes=MES)
    assert _linha_da_dlpa(dlpa, LINHA_PROPOSTO) is None
    dividendos = _linha_da_dlpa(dlpa, "dividendo")
    assert dividendos["valor"] == _dec("-10000.00")

    _conferir_identidade_com_a_dlpa(empresa)


def test_aprovacao_com_contrapartida_sem_classificacao_tambem_vai_para_dividendos():
    """A aprovação/pagamento é decidida pela DIREÇÃO do débito na coluna nova:
    o proposto saindo do PL é dividido distribuído, mesmo sem classificação na
    contrapartida."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 15),
        "Pagamento do dividendo proposto",
        proposto,
        contas["caixa"],
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]
    assert _celula(dmpl, "dividendos", DAP) == _dec("-1000.00")


def test_reversao_da_destinacao_e_o_mesmo_evento_com_sinal_trocado():
    """D proposto / C lucros (cancelamento da proposta): a MESMA linha, com
    sinal trocado — como em "dividendos", a DLPA mostra qualquer sinal."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Proposta de dividendo adicional",
        contas["lucros"],
        proposto,
        "1000.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 20),
        "Cancelamento parcial da proposta",
        proposto,
        contas["lucros"],
        "400.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert _celula(dmpl, LINHA_PROPOSTO, LUCROS) == _dec("-600.00")
    assert _celula(dmpl, LINHA_PROPOSTO, DAP) == _dec("600.00")
    _conferir_identidade_com_a_dlpa(empresa)


# ---------------------------------------------------------------------------
# Erro e limite — o que a regra recusa, e a saída que a pendência aponta
# ---------------------------------------------------------------------------


def test_credito_livre_na_coluna_do_proposto_nao_tem_regra_e_veta():
    """`D caixa / C proposto` não é a destinação (ela vem dos lucros, par de
    colunas): a regra não decide e a RC-151 manda recusar, nunca presumir."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Crédito sem origem decidida",
        contas["caixa"],
        proposto,
        "500.00",
    )
    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is False
    assert dmpl["pendencias"]["contrapartidas_sem_classificacao"], dmpl["pendencias"]


def test_par_do_proposto_com_outra_coluna_sem_regra_veta_nomeando_o_par():
    """`D proposto / C capital`: par sem regra (a proposta só tem regra com os
    lucros acumulados) — pendência que veta e nomeia origem e destino."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa, date(2026, 3, 10), "Proposto contra capital", proposto, contas["capital"], "500.00"
    )
    dmpl = _apurar(empresa)
    emissao = avaliar_emissao_da_dmpl(dmpl)
    assert emissao["pode_emitir"] is False
    pares = dmpl["pendencias"]["pares_de_colunas_sem_regra"]
    assert pares, dmpl["pendencias"]
    assert pares[0]["origem"] == DAP
    assert pares[0]["destino"] == COL.CAPITAL_SOCIAL


def test_o_cenario_do_cliente_sai_de_vetado_a_emitivel_quando_ganha_a_coluna():
    """BL-603, critério 1: o caso do Fred (conta de PL de dividendo adicional
    proposto movimentada) — vetado por falta de coluna, emitível depois dela.
    A pendência, no meio do caminho, já diz que a coluna EXISTE
    (`classificavel = True`): não manda mais esperar."""
    empresa, contas, _ = _caso_a()
    proposto = _conta(
        empresa,
        "3.7",
        "Dividendo Adicional Proposto",
        PL,
        C,
        dlpa=ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO,
        pai=contas["pl"],
    )
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Proposta de dividendo adicional",
        contas["lucros"],
        proposto,
        "1000.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is False
    (entrada,) = dmpl["pendencias"]["contas_do_patrimonio_liquido_sem_coluna"]
    assert entrada["conta"] == "3.7"
    assert entrada["classificavel"] is True
    assert entrada["orientacao"] == ""

    proposto.classificacao_dmpl = DAP
    proposto.full_clean()
    proposto.save()
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True, dmpl["pendencias"]


def test_combinacoes_inconsistentes_de_classificacao_sao_recusadas_no_cadastro():
    """O par é EXATO (critério 4): linha da DLPA "dividendo adicional proposto"
    só combina com a coluna igual, e a coluna nova só aceita conta de PL."""
    empresa = _empresa()
    contas = _plano_basico(empresa)

    def _recusar(**campos):
        with pytest.raises(ValidationError):
            Conta(
                empresa=empresa,
                codigo="3.9",
                nome="Conta de teste",
                natureza=C,
                conta_pai=contas["pl"],
                **campos,
            ).full_clean()

    _recusar(
        tipo=PL,
        classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO,
        classificacao_dmpl=COL.CAPITAL_SOCIAL,
    )
    _recusar(
        tipo=PL,
        classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO,
        classificacao_dmpl=DAP,
    )
    _recusar(
        tipo=PL,
        classificacao_dlpa=ClassificacaoDlpa.RESERVA_LEGAL,
        classificacao_dmpl=DAP,
    )
    _recusar(
        tipo=TipoConta.PASSIVO,
        classificacao_dlpa=ClassificacaoDlpa.DIVIDENDO_ADICIONAL_PROPOSTO,
    )
    _recusar(tipo=TipoConta.PASSIVO, classificacao_dmpl=DAP)

    # O par exato é aceito (o plano de todos os testes acima já o usa).
    assert _proposto(empresa, contas).classificacao_dmpl == DAP


def test_conciliacao_com_o_balanco_fecha_com_a_coluna_nova():
    """Critério 3: o saldo final da coluna nova bate com o Balancete e o total
    com o PL do Balanço — divergência veta e nomeia, e aqui não há divergência."""
    empresa, contas, _ = _caso_a()
    proposto = _proposto(empresa, contas)
    _lancar(
        empresa,
        date(2026, 3, 10),
        "Proposta de dividendo adicional",
        contas["lucros"],
        proposto,
        "1000.00",
    )
    _lancar(
        empresa,
        date(2026, 3, 15),
        "Deliberação que transfere o proposto ao passivo",
        proposto,
        contas["dividendos"],
        "300.00",
    )
    dmpl = _apurar(empresa)
    assert avaliar_emissao_da_dmpl(dmpl)["pode_emitir"] is True
    assert dmpl["saldo_final"]["valores"][DAP] == _dec("700.00")
    assert dmpl["conciliacao"]["por_coluna"][DAP]["diferenca"] == _dec("0.00")
    assert dmpl["conciliacao"]["total"]["diferenca"] == _dec("0.00")
    assert isinstance(dmpl["saldo_final"]["valores"][DAP], Decimal)
