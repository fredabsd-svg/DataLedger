"""DL-079, critérios 1, 4, 5, 7, 8, 9 e 10: serviço do presumido com banco real.

Notas prestadas sintéticas passam pelo pipeline real (`receber_envio`) e são efetivadas pelo serviço
real. Os valores esperados são os da consulta (itens 4 e 6), escritos à mão nos comentários.
"""

from datetime import date
from decimal import Decimal as D

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal.models import (
    AtividadePresuncaoEmpresa,
    ConfirmacaoRetencaoPresumido,
    DeclaracaoReceitasIntegrais,
    ReceitaTrimestralPresumido,
)
from apps.fiscal.tests.suporte_presumido_dl079 import (
    efetivar_prestada,
    nota_efetivada,
    receber_prestada,
)
from apps.fiscal.tests.suporte_tomada_dl078 import cancelar

pytestmark = pytest.mark.django_db

COMERCIO = tab.COMERCIO_INDUSTRIA_TRANSPORTE_CARGA
SERVICOS = tab.SERVICOS_GERAIS


@pytest.fixture
def outra_cliente_a(escritorio_a):
    """Outra cliente do MESMO escritório: é quem presta a nota que não deve entrar na apuraç
    ão de A."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra cliente A Ltda", cnpj="77888999000155"
    )


@pytest.fixture
def presumido(empresa_a, usuario_gestor_a, escritorio_a):
    """Empresa de Lucro Presumido em 2026, critério de competência, comércio como padrão das NFS-e.

    Serviços em geral entram como atividade NÃO padrão (receita informada, que nomeia a atividade).
    Só pode haver UMA padrão em aberto; por isso comércio é a padrão e serviços é informada.
    """
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    servico.definir_criterio(empresa_a, 2026, "competencia", usuario_gestor_a)
    padrao = servico.criar_atividade(
        empresa_a,
        {"atividade": COMERCIO, "inicio": date(2026, 1, 1), "padrao": True},
        usuario_gestor_a,
    )
    servicos_gerais = servico.criar_atividade(
        empresa_a,
        {"atividade": SERVICOS, "inicio": date(2026, 1, 1), "padrao": False},
        usuario_gestor_a,
    )
    return {"empresa": empresa_a, "padrao": padrao, "servicos": servicos_gerais}


def _regime(empresa, *periodos):
    HistoricoRegimeTributario.objects.filter(empresa=empresa).delete()
    for regime, inicio, fim in periodos:
        HistoricoRegimeTributario.objects.create(
            empresa=empresa, regime=regime, vigencia_inicio=inicio, vigencia_fim=fim
        )


def _receita(presumido, usuario, trimestre, valor, atividade=None, tipo="presuncao", sufixo="x"):
    dados = {
        "tipo": tipo,
        "valor": valor,
        "descricao": f"receita informada {sufixo}",
        "suporte": f"NF de suporte {sufixo}",
    }
    if tipo == "presuncao":
        dados["atividade_id"] = (atividade or presumido["servicos"]).pk
    return servico.criar_receita(presumido["empresa"], 2026, trimestre, dados, usuario)


def _apurar(presumido, trimestre):
    return servico.apurar_trimestre(presumido["empresa"], 2026, trimestre)


# ---------------------------------------------------------------------------
# Critério 1 e 2: exemplo de quatro trimestres de 2026, pelo serviço
# ---------------------------------------------------------------------------


def _exemplo_de_quatro_trimestres(presumido, escritorio, usuario):
    """Notas de comércio (padrão) com IRRF e CSLL (tpRetPisCofins 8); serviços em receita in
    formada."""
    empresa = presumido["empresa"]
    notas = [
        (1, "600000.00", "2026-01-15", "4500.00", "3000.00"),
        (2, "1200000.00", "2026-04-15", "9500.00", "6300.00"),
        (3, "800000.00", "2026-07-15", "6000.00", "4000.00"),
        (4, "1000000.00", "2026-10-15", "7500.00", "5000.00"),
    ]
    escrituracoes = {}
    for trimestre, valor, competencia, irrf, csll in notas:
        escrituracoes[trimestre] = nota_efetivada(
            escritorio,
            empresa,
            usuario,
            sufixo=100 + trimestre,
            v_serv=valor,
            d_compet=competencia,
            ret_irrf=irrf,
            ret_csll=csll,
            tp_ret="8",
        )
    for trimestre, valor in [(1, "300000"), (2, "700000"), (3, "400000"), (4, "500000")]:
        _receita(presumido, usuario, trimestre, valor, sufixo=f"serv-{trimestre}")
    _receita(presumido, usuario, 2, "12000", tipo="integral", sufixo="int-2")
    _receita(presumido, usuario, 4, "8000", tipo="integral", sufixo="int-4")
    for trimestre in (1, 2, 3, 4):
        servico.declarar_receitas_integrais(empresa, 2026, trimestre, "", usuario)
    for trimestre, escrituracao in escrituracoes.items():
        confirmacao = servico.confirmar_retencao(
            empresa,
            escrituracao.pk,
            str(dict(notas_irrf())[trimestre]),
            str(dict(notas_csll())[trimestre]),
            "",
            usuario,
        )
        assert confirmacao.estado == "ativa"
    return escrituracoes


def notas_irrf():
    return [(1, "4500.00"), (2, "9500.00"), (3, "6000.00"), (4, "7500.00")]


def notas_csll():
    return [(1, "3000.00"), (2, "6300.00"), (3, "4000.00"), (4, "5000.00")]


def test_exemplo_de_quatro_trimestres_pelo_servico_bate_com_a_consulta(
    presumido, escritorio_a, usuario_gestor_a
):
    # Tabela da consulta (item 4). IRPJ a pagar: 25.500,00 / 68.763,15 / 36.000,00 / 49.300,00.
    # CSLL a pagar: 12.120,00 / 29.033,05 / 16.160,00 / 21.256,00. Situação completa (todas
    # declaradas).
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    irpj = {t: _apurar(presumido, t).irpj for t in (1, 2, 3, 4)}
    csll = {t: _apurar(presumido, t).csll for t in (1, 2, 3, 4)}
    assert [irpj[t].a_recolher for t in (1, 2, 3, 4)] == [
        D("25500.00"),
        D("68763.15"),
        D("36000.00"),
        D("49300.00"),
    ]
    assert [csll[t].a_recolher for t in (1, 2, 3, 4)] == [
        D("12120.00"),
        D("29033.05"),
        D("16160.00"),
        D("21256.00"),
    ]
    assert irpj[2].imposto_com_lc224 == D("78263.15")
    assert irpj[2].imposto_sem_lc224 == D("77000.00")
    assert irpj[2].parcela_lc224 == D("1263.15")
    assert irpj[4].imposto_com_lc224 == D("56800.00")
    assert _apurar(presumido, 4).fechamento_irpj.caso == "III"
    assert _apurar(presumido, 4).fechamento_csll.excedente_anual == D("850000.00")
    assert _apurar(presumido, 2).situacao == "completa"
    assert _apurar(presumido, 2).recusas == ()


def test_quotas_do_trimestre_de_2026_pelo_servico(presumido, escritorio_a, usuario_gestor_a):
    # IRPJ do 2º trimestre a recolher: 68.763,15. Em três quotas: 22.921,05 × 3 = 68.763,15 (exato).
    # Vencimentos: o 2º trimestre termina em junho; 1ª, 2ª e 3ª vencem em julho, agosto e setembro.
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    quotas = _apurar(presumido, 2).irpj.quotas
    assert [p.valor for p in quotas.tres_quotas] == [D("22921.05")] * 3
    assert [p.juros for p in quotas.tres_quotas][1] == "1%"
    assert quotas.tres_quotas[0].vencimento.month == 7


def test_caso_ii_com_excesso_de_deducao_vai_para_saldo_per_dcomp(
    presumido, escritorio_a, usuario_gestor_a
):
    # Exemplo do domínio: T1 2.500.000 e T2 2.500.000 de comércio, T3 0, T4 50.000 (ExcAnual 50.000,
    # S 2.500.000, caso II). Dedução = 4.900,00 (ver test_dl079_calculo). IRPJ de T4 = 600,00.
    # A dedução vira 600,00 aplicado e 4.300,00 em saldo PER/DCOMP: mostrado, nunca abatido de
    # outro.
    empresa = presumido["empresa"]
    for trimestre, valor in [(1, "2500000.00"), (2, "2500000.00"), (4, "50000.00")]:
        nota_efetivada(
            escritorio_a,
            empresa,
            usuario_gestor_a,
            sufixo=200 + trimestre,
            v_serv=valor,
            d_compet=f"2026-{(trimestre - 1) * 3 + 1:02d}-10",
        )
    for trimestre in (1, 2, 3, 4):
        servico.declarar_receitas_integrais(empresa, 2026, trimestre, "", usuario_gestor_a)
    apuracao = _apurar(presumido, 4)
    assert apuracao.irpj.deducao_quarto_trimestre == D("600.00")
    assert apuracao.irpj.saldo_per_dcomp == D("4300.00")
    assert apuracao.irpj.a_recolher == D("0.00")


# ---------------------------------------------------------------------------
# Critério 8: recusas nomeadas
# ---------------------------------------------------------------------------


def test_recusa_regime_diferente_de_lucro_presumido(presumido, escritorio_a, usuario_gestor_a):
    _regime(presumido["empresa"], (RegimeTributario.SIMPLES_NACIONAL, date(2026, 1, 1), None))
    apuracao = _apurar(presumido, 1)
    assert [r.codigo for r in apuracao.recusas] == ["regime_diferente"]
    assert apuracao.irpj is None and apuracao.csll is None


def test_recusa_mudanca_de_regime_dentro_do_trimestre(presumido, escritorio_a, usuario_gestor_a):
    _regime(
        presumido["empresa"],
        (RegimeTributario.SIMPLES_NACIONAL, date(2026, 1, 1), date(2026, 2, 10)),
        (RegimeTributario.LUCRO_PRESUMIDO, date(2026, 2, 11), None),
    )
    apuracao = _apurar(presumido, 1)
    assert [r.codigo for r in apuracao.recusas] == ["regime_muda_no_trimestre"]


def test_recusa_trimestre_sem_regime_cadastrado(presumido, escritorio_a, usuario_gestor_a):
    _regime(presumido["empresa"], (RegimeTributario.LUCRO_PRESUMIDO, date(2026, 4, 1), None))
    apuracao = _apurar(presumido, 1)
    assert [r.codigo for r in apuracao.recusas] == ["regime_nao_informado"]


def test_recusa_criterio_nao_informado(empresa_a, usuario_gestor_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    apuracao = servico.apurar_trimestre(empresa_a, 2026, 1)
    assert "criterio_nao_informado" in [r.codigo for r in apuracao.recusas]


def test_recusa_criterio_caixa_com_citacao_da_in_1700(presumido, escritorio_a, usuario_gestor_a):
    presumido_empresa = presumido["empresa"]
    from apps.fiscal.models import CriterioReceitaPresumido

    CriterioReceitaPresumido.objects.filter(empresa=presumido_empresa, ano=2026).delete()
    servico.definir_criterio(presumido_empresa, 2026, "caixa", usuario_gestor_a)
    apuracao = _apurar(presumido, 1)
    recusa = next(r for r in apuracao.recusas if r.codigo == "criterio_caixa")
    assert "1.700" in recusa.mensagem and "art. 223" in recusa.mensagem


def test_recusa_nota_sem_atividade_lista_as_notas(presumido, escritorio_a, usuario_gestor_a):
    # Atividade padrão começa em 01/03: a nota de janeiro não tem atividade vigente (recusa
    # nomeada).
    empresa = presumido["empresa"]
    AtividadePresuncaoEmpresa.objects.filter(pk=presumido["padrao"].pk).update(
        inicio=date(2026, 3, 1)
    )
    nota_efetivada(
        escritorio_a, empresa, usuario_gestor_a, sufixo=301, v_serv="1000.00", d_compet="2026-01-20"
    )
    apuracao = _apurar(presumido, 1)
    recusa = next(r for r in apuracao.recusas if r.codigo == "nota_sem_atividade")
    assert recusa.itens == ("301",)


def test_recusa_receita_sem_atividade_vigente_no_trimestre(
    presumido, escritorio_a, usuario_gestor_a
):
    # Receita criada no 2º trimestre com atividade vigente; depois a atividade encerra antes de
    # abril.
    _receita(presumido, usuario_gestor_a, 2, "1000.00", sufixo="antes-do-fim")
    servico.encerrar_atividade(
        presumido["empresa"], presumido["servicos"].pk, date(2026, 3, 31), usuario_gestor_a
    )
    apuracao = _apurar(presumido, 2)
    assert "receita_sem_atividade_vigente" in [r.codigo for r in apuracao.recusas]


def test_trimestre_antes_da_abertura_e_inicio_no_segundo_trimestre(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    Empresa.objects.filter(pk=empresa.pk).update(data_abertura_cnpj=date(2026, 5, 10))
    empresa.refresh_from_db()
    assert [r.codigo for r in _apurar(presumido, 1).recusas] == ["trimestre_antes_da_abertura"]
    apuracao_2 = _apurar(presumido, 2)
    assert apuracao_2.recusas == ()
    assert apuracao_2.avisos == (tab.AVISO_ADI,)


@pytest.mark.parametrize(("ano", "trimestre"), [(2025, 1), (2026, 0), (2026, 5), (1999, 4)])
def test_ano_ou_trimestre_invalido_vira_recusa_nomeada(presumido, ano, trimestre):
    apuracao = servico.apurar_trimestre(presumido["empresa"], ano, trimestre)
    assert [r.codigo for r in apuracao.recusas] == ["ano_ou_trimestre_invalido"]
    assert apuracao.irpj is None and apuracao.csll is None


# ---------------------------------------------------------------------------
# Receita da nota: desconto, rascunho, cancelada, estornada, outra empresa
# ---------------------------------------------------------------------------


def test_desconto_incondicional_reduz_a_base_e_ausencia_e_zero(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=401,
        v_serv="1000.00",
        d_compet="2026-01-10",
        desc_incond="200.00",
    )
    nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=402,
        v_serv="500.00",
        d_compet="2026-01-11",
    )
    apuracao = _apurar(presumido, 1)
    por_numero = {n.numero: (n.desconto_incondicionado, n.base) for n in apuracao.notas}
    assert por_numero["401"] == (D("200.00"), D("800.00"))  # 1.000 − 200 incondicional
    assert por_numero["402"] == (D("0.00"), D("500.00"))  # sem vDescIncond no XML: desconto ZERO


def test_desconto_maior_que_o_servico_recusa(presumido, escritorio_a, usuario_gestor_a):
    nota_efetivada(
        escritorio_a,
        presumido["empresa"],
        usuario_gestor_a,
        sufixo=403,
        v_serv="100.00",
        d_compet="2026-01-10",
        desc_incond="150.00",
    )
    apuracao = _apurar(presumido, 1)
    assert "desconto_maior_que_servico" in [r.codigo for r in apuracao.recusas]


def test_rascunho_cancelada_e_outra_empresa_nao_entram(
    presumido, escritorio_a, usuario_gestor_a, outra_cliente_a
):
    empresa = presumido["empresa"]
    # Rascunho: a nota é recebida e não efetivada.
    documento_rascunho = receber_prestada(
        escritorio_a, usuario_gestor_a, 404, v_serv="7000.00", d_compet="2026-01-12"
    )
    from apps.fiscal import escrituracao as escrituracao_servico
    from apps.fiscal.models import NaturezaOperacao, PapelDocumento, VinculoDocumentoEmpresa

    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento_rascunho, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )
    escrituracao_servico.salvar_rascunho(
        vinculo, NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR, usuario_gestor_a
    )
    # Cancelada depois de efetivada.
    documento_cancelado = receber_prestada(
        escritorio_a, usuario_gestor_a, 405, v_serv="9000.00", d_compet="2026-01-13"
    )
    efetivar_prestada(documento_cancelado, empresa, usuario_gestor_a)
    cancelar(escritorio_a, usuario_gestor_a, documento_cancelado, sufixo_evento=5)
    # Nota de outra empresa, do OUTRO cliente (prestadora CNPJ de empresa_b): nunca entra.
    nota_efetivada(
        escritorio_a,
        outra_cliente_a,
        usuario_gestor_a,
        sufixo=406,
        v_serv="50000.00",
        d_compet="2026-01-14",
        prestador="77888999000155",
    )
    apuracao = _apurar(presumido, 1)
    assert apuracao.notas == ()
    assert apuracao.recusas == ()


def test_receita_estornada_nao_entra(presumido, escritorio_a, usuario_gestor_a):
    receita = _receita(presumido, usuario_gestor_a, 1, "5000.00", sufixo="estornar")
    assert _apurar(presumido, 1).receitas[0].valor == D("5000.00")
    servico.estornar_receita(
        presumido["empresa"], receita.pk, "lançado em duplicidade", usuario_gestor_a
    )
    assert _apurar(presumido, 1).receitas == ()


# ---------------------------------------------------------------------------
# Critério 5: retenção proposta, confirmada, estimada, a classificar, saldo negativo
# ---------------------------------------------------------------------------


def test_retencao_nao_confirmada_nao_entra_e_confirmada_entra(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=501,
        v_serv="100000.00",
        d_compet="2026-01-10",
        ret_irrf="1000.00",
    )
    for trimestre in (1,):
        servico.declarar_receitas_integrais(empresa, 2026, trimestre, "", usuario_gestor_a)
    antes = _apurar(presumido, 1).irpj
    assert antes.retencao_confirmada == D("0.00")
    servico.confirmar_retencao(empresa, escrituracao.pk, "1000.00", None, "", usuario_gestor_a)
    depois = _apurar(presumido, 1).irpj
    assert depois.retencao_confirmada == D("1000.00")
    assert depois.a_recolher == antes.a_recolher - D("1000.00")


def test_retencao_so_deduz_no_trimestre_da_competencia_da_nota(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=502,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="800.00",
    )
    servico.confirmar_retencao(empresa, escrituracao.pk, "800.00", None, "", usuario_gestor_a)
    assert _apurar(presumido, 2).irpj.retencao_confirmada == D("0.00")


def test_csll_estimada_com_codigo_3_e_a_classificar_com_outros_codigos(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    estimada = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=503,
        v_serv="5000.00",
        d_compet="2026-01-10",
        ret_csll="465.00",
        tp_ret="3",
    )
    classificar = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=504,
        v_serv="5000.00",
        d_compet="2026-01-11",
        ret_csll="500.00",
        tp_ret="5",
    )
    retencoes = servico.retencoes_do_trimestre(empresa, 2026, 1)
    linhas = {linha.escrituracao_id: linha for linha in retencoes}
    assert linhas[estimada.pk].csll_proposta == D("100.00")
    assert linhas[estimada.pk].csll_situacao == "estimada"
    assert linhas[classificar.pk].csll_proposta is None
    assert linhas[classificar.pk].csll_situacao == "a_classificar"


def test_saldo_negativo_nao_passa_para_o_trimestre_seguinte(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    # Nota pequena (IRPJ pequeno) com IRRF confirmado maior que o imposto do trimestre.
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=505,
        v_serv="10000.00",
        d_compet="2026-01-10",
        ret_irrf="5000.00",
    )
    servico.confirmar_retencao(empresa, escrituracao.pk, "5000.00", None, "", usuario_gestor_a)
    for trimestre in (1, 2, 3, 4):
        servico.declarar_receitas_integrais(empresa, 2026, trimestre, "", usuario_gestor_a)
    apuracao = _apurar(presumido, 1)
    # IRPJ de 10.000 de comércio: 800 + 10% × 0 = 15% × 800 = 120,00 (base 800). IRRF 5.000 > 120.
    assert apuracao.irpj.a_recolher == D("0.00")
    assert apuracao.irpj.saldo_negativo == D("4880.00")
    assert _apurar(presumido, 2).irpj.retencao_confirmada == D("0.00")


def test_confirmar_de_novo_substitui_a_anterior_com_trilha(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=506,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="1000.00",
    )
    servico.confirmar_retencao(empresa, escrituracao.pk, "1000.00", None, "", usuario_gestor_a)
    servico.confirmar_retencao(empresa, escrituracao.pk, "1000.00", None, "", usuario_gestor_a)
    ativas = ConfirmacaoRetencaoPresumido.objects.filter(escrituracao=escrituracao, estado="ativa")
    assert ativas.count() == 1
    assert (
        ConfirmacaoRetencaoPresumido.objects.filter(
            escrituracao=escrituracao, estado="substituida"
        ).count()
        == 1
    )


def test_valor_confirmado_diferente_do_proposto_exige_motivo(
    presumido, escritorio_a, usuario_gestor_a
):
    from apps.fiscal.presumido import EntradaInvalidaPresumido

    empresa = presumido["empresa"]
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=507,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="1000.00",
    )
    with pytest.raises(EntradaInvalidaPresumido):
        servico.confirmar_retencao(empresa, escrituracao.pk, "900.00", None, "", usuario_gestor_a)
    confirmacao = servico.confirmar_retencao(
        empresa,
        escrituracao.pk,
        "900.00",
        None,
        "retenção conferida no comprovante",
        usuario_gestor_a,
    )
    assert confirmacao.motivo == "retenção conferida no comprovante"


def test_retencao_de_nota_de_outra_empresa_responde_nao_encontrada(
    presumido, escritorio_a, usuario_gestor_a, outra_cliente_a
):
    from apps.fiscal.presumido import NaoEncontradoPresumido

    outra = nota_efetivada(
        escritorio_a,
        outra_cliente_a,
        usuario_gestor_a,
        sufixo=508,
        v_serv="1000.00",
        d_compet="2026-01-10",
        ret_irrf="10.00",
        prestador="77888999000155",
    )
    with pytest.raises(NaoEncontradoPresumido):
        servico.confirmar_retencao(
            presumido["empresa"], outra.pk, "10.00", None, "", usuario_gestor_a
        )


def test_confirmacao_ativa_repetida_no_banco_vira_conflito(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    escrituracao = nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=509,
        v_serv="20000.00",
        d_compet="2026-01-10",
        ret_irrf="100.00",
    )
    servico.confirmar_retencao(empresa, escrituracao.pk, "100.00", None, "", usuario_gestor_a)
    segunda = ConfirmacaoRetencaoPresumido(
        escrituracao=escrituracao,
        irrf_confirmado=D("100.00"),
        estado="ativa",
        confirmada_por=usuario_gestor_a,
    )
    with pytest.raises(servico.PresumidoConflito):
        servico._inserir(
            segunda,
            "presumido_confirmacao_ativa_unica_por_escrituracao",
            "conflito de confirmação",
        )


# ---------------------------------------------------------------------------
# Medida judicial, declaração e situação
# ---------------------------------------------------------------------------


def _medida(empresa, usuario, **extra):
    dados = {
        "tributo": "irpj",
        "ano_inicial": 2026,
        "trimestre_inicial": 2,
        "ano_final": 2026,
        "trimestre_final": 2,
        "numero_processo": "5000000-00.2026.4.02.5116",
        "orgao": "Vara Federal (fictício)",
        "data_decisao": "2026-06-01",
        "deposito_judicial": False,
        "suporte": "decisão sintética",
    }
    dados.update(extra)
    return servico.cadastrar_medida(empresa, dados, usuario)


def test_medida_judicial_suspende_a_parcela_e_usa_a_coluna_sem_lc224(
    presumido, escritorio_a, usuario_gestor_a
):
    # 2º trimestre: IRPJ com LC 224 = 68.763,15 a pagar (78.263,15 − 9.500 IRRF) e sem = 77.000 −
    # 9.500.
    # Com a medida, a recolher usa a coluna sem o acréscimo: 77.000,00 − 9.500,00 = 67.500,00.
    # A parcela 1.263,15 aparece como suspensa.
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    _medida(presumido["empresa"], usuario_gestor_a)
    irpj = _apurar(presumido, 2).irpj
    assert irpj.medida == "suspensa"
    assert irpj.valor_suspenso == D("1263.15")
    assert irpj.a_recolher == D("67500.00")
    assert irpj.coluna_escolhida == "sem_lc224"


def test_medida_com_deposito_judicial_mostra_depositar(presumido, escritorio_a, usuario_gestor_a):
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    _medida(presumido["empresa"], usuario_gestor_a, deposito_judicial=True)
    irpj = _apurar(presumido, 2).irpj
    assert irpj.medida == "depositar"
    assert irpj.a_recolher == D("67500.00")


def test_sem_medida_usa_a_coluna_com_lc224_e_medida_nao_vale_fora_do_periodo(
    presumido, escritorio_a, usuario_gestor_a
):
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    _medida(presumido["empresa"], usuario_gestor_a)  # só o 2º trimestre
    assert _apurar(presumido, 3).irpj.medida == "nenhuma"
    assert _apurar(presumido, 3).irpj.coluna_escolhida == "com_lc224"


def test_medida_revogada_deixa_de_valer(presumido, escritorio_a, usuario_gestor_a):
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    medida = _medida(presumido["empresa"], usuario_gestor_a)
    servico.revogar_medida(presumido["empresa"], medida.pk, "decisão cassada", usuario_gestor_a)
    irpj = _apurar(presumido, 2).irpj
    assert irpj.medida == "nenhuma"
    assert irpj.a_recolher == D("68763.15")


def test_declaracao_cai_quando_o_total_das_integrais_muda(
    presumido, escritorio_a, usuario_gestor_a
):
    empresa = presumido["empresa"]
    _receita(presumido, usuario_gestor_a, 1, "1000.00", tipo="integral", sufixo="i1")
    servico.declarar_receitas_integrais(empresa, 2026, 1, "", usuario_gestor_a)
    assert _apurar(presumido, 1).declaracao_valida is True
    _receita(presumido, usuario_gestor_a, 1, "1.00", tipo="integral", sufixo="i2")
    apuracao = _apurar(presumido, 1)
    assert apuracao.declaracao_valida is False
    assert apuracao.situacao == "parcial"
    servico.declarar_receitas_integrais(empresa, 2026, 1, "nova declaração", usuario_gestor_a)
    assert _apurar(presumido, 1).situacao == "completa"
    assert DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa, trimestre=1).count() == 2


def test_situacao_parcial_sem_declaracao_de_integrais(presumido, escritorio_a, usuario_gestor_a):
    _receita(presumido, usuario_gestor_a, 1, "1000.00", sufixo="sem-decl")
    apuracao = _apurar(presumido, 1)
    assert apuracao.situacao == "parcial"
    assert apuracao.declaracao_valida is False
    assert apuracao.recusas == ()  # parcial não é recusa: o número sai, sinalizado


def test_integral_fora_do_limite_nao_entra_no_limite(presumido, escritorio_a, usuario_gestor_a):
    # Receita de presunção 1.250.000 (limite exato, E = 0) e integral 500.000: a integral entra na
    # base
    # e NÃO conta no limite. Base = 1.250.000 × 8% + 500.000 = 600.000 (comércio, padrão).
    empresa = presumido["empresa"]
    nota_efetivada(
        escritorio_a,
        empresa,
        usuario_gestor_a,
        sufixo=510,
        v_serv="1250000.00",
        d_compet="2026-01-10",
    )
    _receita(presumido, usuario_gestor_a, 1, "500000", tipo="integral", sufixo="fora-limite")
    servico.declarar_receitas_integrais(empresa, 2026, 1, "", usuario_gestor_a)
    irpj = _apurar(presumido, 1).irpj
    assert irpj.receitas_integrais == D("500000.00")
    assert irpj.imposto_sem_lc224 == D("144000.00")  # 600.000: 90.000 + 10% × 540.000 = 54.000
    assert irpj.parcela_lc224 == D("0.00")


# ---------------------------------------------------------------------------
# Atividades, critério e receitas: regras de cadastro
# ---------------------------------------------------------------------------


def test_padrao_com_vigencia_sobreposta_recusa(presumido, usuario_gestor_a):
    with pytest.raises(servico.PresumidoConflito):
        servico.criar_atividade(
            presumido["empresa"],
            {"atividade": SERVICOS, "inicio": date(2026, 6, 1), "padrao": True},
            usuario_gestor_a,
        )


def test_servico_hospitalar_exige_requisitos_confirmados(presumido, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_atividade(
            presumido["empresa"],
            {"atividade": tab.SERVICOS_HOSPITALARES, "inicio": date(2026, 1, 1)},
            usuario_gestor_a,
        )
    atividade = servico.criar_atividade(
        presumido["empresa"],
        {
            "atividade": tab.SERVICOS_HOSPITALARES,
            "inicio": date(2026, 1, 1),
            "requisitos_hospitalares_confirmados": True,
        },
        usuario_gestor_a,
    )
    assert atividade.requisitos_hospitalares_confirmados is True


def test_atividade_fora_do_catalogo_recusa(presumido, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_atividade(
            presumido["empresa"],
            {"atividade": "atividade_inventada", "inicio": date(2026, 1, 1)},
            usuario_gestor_a,
        )


def test_encerrar_atividade_grava_fim_e_nao_repete(presumido, usuario_gestor_a):
    atividade = servico.encerrar_atividade(
        presumido["empresa"], presumido["servicos"].pk, date(2026, 12, 31), usuario_gestor_a
    )
    assert atividade.fim == date(2026, 12, 31)
    with pytest.raises(servico.PresumidoConflito):
        servico.encerrar_atividade(
            presumido["empresa"], presumido["servicos"].pk, date(2026, 12, 31), usuario_gestor_a
        )


def test_padrao_em_aberto_unica_no_banco(presumido, usuario_gestor_a):
    # Segunda padrão em aberto, direto no ORM: a restrição do banco recusa.
    with pytest.raises(IntegrityError), transaction.atomic():
        AtividadePresuncaoEmpresa.objects.create(
            empresa=presumido["empresa"],
            atividade=COMERCIO,
            inicio=date(2027, 1, 1),
            padrao=True,
            criada_por=usuario_gestor_a,
        )


def test_criterio_do_ano_nao_se_troca_e_repetir_e_idempotente(presumido, usuario_gestor_a):
    empresa = presumido["empresa"]
    _, criado = servico.definir_criterio(empresa, 2026, "competencia", usuario_gestor_a)
    assert criado is False  # já definido pelo fixture
    with pytest.raises(servico.PresumidoConflito):
        servico.definir_criterio(empresa, 2026, "caixa", usuario_gestor_a)


@pytest.mark.parametrize(
    ("valor", "motivo"),
    [(1000.5, "ponto flutuante"), ("1.234", "duas casas"), ("0", "positivo"), ("-5", "formato")],
)
def test_valor_da_receita_precisa_ser_texto_decimal_positivo(
    presumido, usuario_gestor_a, valor, motivo
):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_receita(
            presumido["empresa"],
            2026,
            1,
            {
                "tipo": "presuncao",
                "valor": valor,
                "descricao": "x",
                "suporte": "y",
                "atividade_id": presumido["servicos"].pk,
            },
            usuario_gestor_a,
        )


def test_receita_de_presuncao_exige_atividade_da_mesma_empresa(
    presumido, usuario_gestor_a, empresa_b
):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_receita(
            presumido["empresa"],
            2026,
            1,
            {"tipo": "presuncao", "valor": "100.00", "descricao": "x", "suporte": "y"},
            usuario_gestor_a,
        )
    outra_atividade = AtividadePresuncaoEmpresa.objects.create(
        empresa=empresa_b, atividade=SERVICOS, inicio=date(2026, 1, 1), criada_por=usuario_gestor_a
    )
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_receita(
            presumido["empresa"],
            2026,
            1,
            {
                "tipo": "presuncao",
                "valor": "100.00",
                "descricao": "x",
                "suporte": "y",
                "atividade_id": outra_atividade.pk,
            },
            usuario_gestor_a,
        )


def test_receita_integral_nao_leva_atividade(presumido, usuario_gestor_a):
    with pytest.raises(servico.EntradaInvalidaPresumido):
        servico.criar_receita(
            presumido["empresa"],
            2026,
            1,
            {
                "tipo": "integral",
                "valor": "100.00",
                "descricao": "x",
                "suporte": "y",
                "atividade_id": presumido["servicos"].pk,
            },
            usuario_gestor_a,
        )


def test_receita_do_banco_recusa_atividade_de_outra_empresa(presumido, usuario_gestor_a, empresa_b):
    outra = AtividadePresuncaoEmpresa.objects.create(
        empresa=empresa_b, atividade=SERVICOS, inicio=date(2026, 1, 1), criada_por=usuario_gestor_a
    )
    with pytest.raises(IntegrityError), transaction.atomic():
        ReceitaTrimestralPresumido.objects.create(
            empresa=presumido["empresa"],
            ano=2026,
            trimestre=1,
            tipo="presuncao",
            atividade=outra,
            descricao="x",
            valor=D("10.00"),
            suporte="y",
            criada_por=usuario_gestor_a,
        )


def test_controle_do_limite_mostra_sobra_e_fechamento(presumido, escritorio_a, usuario_gestor_a):
    # Mesmo exemplo: L2 = 1.600.000 (sobra de T1 = 350.000), E2 = 300.000; fechamento caso III.
    _exemplo_de_quatro_trimestres(presumido, escritorio_a, usuario_gestor_a)
    controle = servico.controle_limite_ano(presumido["empresa"], 2026, "irpj")
    linha2 = controle.linhas[1]
    assert linha2.limite == D("1600000.00")
    assert linha2.excedente == D("300000.00")
    assert controle.linhas[0].sobra == D("350000.00")
    assert controle.fechamento.caso == "III"


def test_nota_de_outra_empresa_nao_contamina_o_controle_de_limite(
    presumido, escritorio_a, usuario_gestor_a, outra_cliente_a
):
    nota_efetivada(
        escritorio_a,
        outra_cliente_a,
        usuario_gestor_a,
        sufixo=511,
        v_serv="9000000.00",
        d_compet="2026-01-10",
        prestador="77888999000155",
    )
    controle = servico.controle_limite_ano(presumido["empresa"], 2026, "irpj")
    assert controle.linhas[0].receita_presumida == D("0.00")


def test_sem_data_de_abertura_a_apuracao_avisa_atividade_no_ano_inteiro(presumido):
    apuracao = _apurar(presumido, 1)
    assert any("Data de abertura no CNPJ não informada" in aviso for aviso in apuracao.avisos)


# ---------------------------------------------------------------------------
# Item 0 (correção de dupla contagem) pelo serviço, com banco real
# ---------------------------------------------------------------------------


def _notas_caso_i(presumido, escritorio, usuario):
    """Comércio: T1 2.000.000, T2 500.000, T3 500.000, T4 1.000.000 → caso I (Σ R = 4.000.000)."""
    empresa = presumido["empresa"]
    for trimestre, valor, competencia in [
        (1, "2000000.00", "2026-01-10"),
        (2, "500000.00", "2026-04-10"),
        (3, "500000.00", "2026-07-10"),
        (4, "1000000.00", "2026-10-10"),
    ]:
        nota_efetivada(
            escritorio,
            empresa,
            usuario,
            sufixo=300 + trimestre,
            v_serv=valor,
            d_compet=competencia,
        )


def test_caso_i_sem_medida_deduz_1500_do_t1_pelo_servico(presumido, escritorio_a, usuario_gestor_a):
    # Controle positivo, valor de antes da correção. T4: IRPJ 14.000,00 (80.000 × 15% = 12.000 +
    # 10% × 20.000 = 2.000). Dedução 1.500,00 (parcela de T1). A recolher = 12.500,00.
    _notas_caso_i(presumido, escritorio_a, usuario_gestor_a)
    apuracao = _apurar(presumido, 4)
    assert apuracao.fechamento_irpj.caso == "I"
    assert apuracao.irpj.deducao_quarto_trimestre == D("1500.00")
    assert apuracao.irpj.a_recolher == D("12500.00")
    assert apuracao.irpj.linhas_do_ano[0].suspensa_por_medida is False


def test_caso_i_com_medida_no_t1_tira_o_t1_da_deducao_do_quarto(
    presumido, escritorio_a, usuario_gestor_a
):
    # T1 com medida: recolhe a coluna sem acréscimo, 34.000,00 (24.000 + 10.000). A parcela de
    # 1.500,00 fica suspensa e NÃO é devolvida no 4º trimestre. T4 passa a recolher 14.000,00.
    # A memória do ano mostra T1 como "suspensa", com a diferença que não entrou na dedução.
    _notas_caso_i(presumido, escritorio_a, usuario_gestor_a)
    _medida(presumido["empresa"], usuario_gestor_a, trimestre_inicial=1, trimestre_final=1)
    apuracao = _apurar(presumido, 4)
    assert apuracao.irpj.deducao_quarto_trimestre == D("0.00")
    assert apuracao.irpj.a_recolher == D("14000.00")
    t1 = apuracao.irpj.linhas_do_ano[0]
    assert t1.suspensa_por_medida is True
    assert t1.diferenca_recalculo == D("1500.00")
    assert _apurar(presumido, 1).irpj.a_recolher == D("34000.00")
    assert _apurar(presumido, 1).irpj.valor_suspenso == D("1500.00")
    controle = servico.controle_limite_ano(presumido["empresa"], 2026, "irpj")
    assert controle.deducao_quarto_trimestre == D("0.00")
    assert controle.linhas[0].suspensa_por_medida is True
    assert controle.linhas[0].excedente == D("750000.00")  # o limite não muda


def _notas_caso_ii(presumido, escritorio, usuario):
    """T1 2.500.000, T2 2.500.000, T3 zero, T4 50.000 → caso II, dedução total de 4.900,00."""
    empresa = presumido["empresa"]
    for trimestre, valor in [(1, "2500000.00"), (2, "2500000.00"), (4, "50000.00")]:
        nota_efetivada(
            escritorio,
            empresa,
            usuario,
            sufixo=400 + trimestre,
            v_serv=valor,
            d_compet=f"2026-{(trimestre - 1) * 3 + 1:02d}-10",
        )


def _deducao_total(irpj):
    """Dedução que o 4º trimestre apurou: a aplicada no imposto mais a que vira saldo PER/DCOMP."""
    return irpj.deducao_quarto_trimestre + irpj.saldo_per_dcomp


def test_caso_ii_com_medida_em_parte_dos_trimestres_pelo_servico(
    presumido, escritorio_a, usuario_gestor_a
):
    # Sem medida, a dedução é 4.900,00 (2.450 de T1 + 2.450 de T2). Com medida só no T1, cai para
    # 2.450,00. Com medida em T1 e T2, cai para zero. O IRPJ de T4 (600,00) não muda.
    _notas_caso_ii(presumido, escritorio_a, usuario_gestor_a)
    assert _deducao_total(_apurar(presumido, 4).irpj) == D("4900.00")
    _medida(presumido["empresa"], usuario_gestor_a, trimestre_inicial=1, trimestre_final=1)
    irpj = _apurar(presumido, 4).irpj
    assert _deducao_total(irpj) == D("2450.00")
    assert irpj.deducao_quarto_trimestre == D("600.00")  # aplicado no devido de T4
    assert irpj.saldo_per_dcomp == D("1850.00")
    assert [linha.suspensa_por_medida for linha in irpj.linhas_do_ano] == [
        True,
        False,
        False,
        False,
    ]
    _medida(presumido["empresa"], usuario_gestor_a, trimestre_inicial=2, trimestre_final=2)
    irpj = _apurar(presumido, 4).irpj
    assert _deducao_total(irpj) == D("0.00")
    assert irpj.a_recolher == D("600.00")
