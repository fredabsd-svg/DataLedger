"""DL-075 (frente A) — bloqueios do pré-DAS (critério 7) e tabelas fora de vigência (critério 9).

Cada bloqueio recusa com um código e uma mensagem que NOMEIA o que falta. Quando há
mais de um motivo, a recusa lista todos (o contador vê de uma vez o que falta).
"""

from datetime import date

import pytest

from apps.fiscal import pre_das as servico
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import EnquadramentoAtividade, NaturezaOperacao
from apps.fiscal.tests.test_dl074_suporte import escriturar, informar_e_confirmar
from apps.fiscal.tests.test_dl075_suporte import (
    atividade_padrao,
    cenario_simples,
    janela_de_receitas,
    receber_e_confirmar_mes,
    sequencia_anterior,
)

pytestmark = pytest.mark.django_db


def _codigos(excecao: servico.PreDasRecusado) -> set[str]:
    return {bloqueio.codigo for bloqueio in excecao.bloqueios}


def _recusa(empresa, ano, mes) -> servico.PreDasRecusado:
    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, ano, mes)
    return excecao.value


def test_mes_nao_confirmado_recusa_e_nomeia_o_mes(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 6, "100000.00")  # sem confirmar o mês

    excecao = _recusa(empresa, 2026, 6)

    assert "mes_nao_confirmado" in _codigos(excecao)
    assert "06/2026" in " ".join(b.mensagem for b in excecao.bloqueios)


def test_rbt12_nao_apuravel_nomeia_o_mes_da_janela_que_falta(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    meses = sequencia_anterior(2026, 6)
    for ano, mes in meses[:-1]:
        receber_e_confirmar_mes(empresa, usuario_gestor_a, ano, mes, "25000.00")
    # Mês 05/2026 tem receita informada, mas NÃO foi confirmado como completo.
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 5, "25000.00")
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert "rbt12_nao_apuravel" in _codigos(excecao)
    assert "05/2026" in " ".join(b.mensagem for b in excecao.bloqueios)


def test_regime_de_caixa_em_2026_recusa_o_pre_das(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    servico_receita.registrar_opcao_regime_caixa(empresa, 2026, usuario_gestor_a)

    excecao = _recusa(empresa, 2026, 6)

    assert "regime_de_caixa" in _codigos(excecao)


def test_sem_atividade_padrao_recusa_e_nomeia_o_que_cadastrar(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert "sem_atividade_padrao" in _codigos(excecao)
    assert "atividade padrão" in " ".join(b.mensagem for b in excecao.bloqueios)


def test_atividade_padrao_que_termina_no_meio_do_mes_recusa(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(
        empresa,
        usuario_gestor_a,
        EnquadramentoAtividade.ANEXO_III,
        fim=date(2026, 6, 15),
    )
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert "atividade_padrao_muda_no_mes" in _codigos(excecao)


def test_fator_r_exigido_sem_folha_recusa_nomeando_o_mes_ausente(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [40000] * 11 + [60000])
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "10000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert "folha_nao_confirmada" in _codigos(excecao)
    texto = " ".join(b.mensagem for b in excecao.bloqueios)
    assert "06/2025" in texto and "05/2026" in texto


def test_rbt12_acima_do_primeiro_corte_recusa(empresa_a, usuario_gestor_a):
    """RBT12 de 4.500.000 (12 × 375.000): 6ª faixa fica fora do primeiro corte (HI-68)."""
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [375000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "1000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert "rbt12_acima_do_primeiro_corte" in _codigos(excecao)


def test_natureza_fora_do_primeiro_corte_recusa_com_o_nome_da_natureza(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    escriturar(
        empresa_a.escritorio,
        empresa,
        usuario_gestor_a,
        sufixo=9201,
        competencia=(2026, 6),
        valor="100000.00",
        natureza=NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO,
    )
    servico_receita.confirmar_mes(empresa, 2026, 6, usuario_gestor_a)

    excecao = _recusa(empresa, 2026, 6)

    assert "natureza_fora_do_corte" in _codigos(excecao)
    assert "imune" in " ".join(b.mensagem for b in excecao.bloqueios)


def test_recusa_lista_todos_os_motivos_de_uma_vez(empresa_a, usuario_gestor_a):
    """Sem atividade E com mês não confirmado: as duas causas aparecem na mesma recusa."""
    empresa = cenario_simples(empresa_a)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    informar_e_confirmar(empresa, usuario_gestor_a, 2026, 6, "100000.00")

    excecao = _recusa(empresa, 2026, 6)

    assert {"mes_nao_confirmado", "sem_atividade_padrao"} <= _codigos(excecao)


def test_tabela_de_2027_recusada_citando_a_res_cgsn_190(empresa_a, usuario_gestor_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2027, 1)
    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "tabela_fora_de_vigencia"
    assert "190/2026" in bloqueio.mensagem
    assert "01/2027" in bloqueio.mensagem


def test_competencia_antes_de_2018_recusada_com_a_vigencia(empresa_a):
    empresa = cenario_simples(empresa_a)
    with pytest.raises(servico.PreDasRecusado) as excecao:
        servico.pre_das(empresa, 2017, 12)
    (bloqueio,) = excecao.value.bloqueios
    assert bloqueio.codigo == "tabela_fora_de_vigencia"
    assert "01/01/2018" in bloqueio.mensagem


def test_pre_das_de_outra_empresa_do_mesmo_escritorio_nao_enxerga_a_receita(
    empresa_a, empresa_a2, usuario_gestor_a
):
    """Isolamento (critério 10): a receita confirmada da empresa A não aparece na A2.

    A2 tem Simples próprio e nenhuma receita. Se a receita da A vazasse, a RBT12 da A2
    seria apurável; o esperado é "não apurável" e o mês sem confirmação.
    """
    empresa_a_simples = cenario_simples(empresa_a)
    atividade_padrao(empresa_a_simples, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa_a_simples, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa_a_simples, usuario_gestor_a, 2026, 6, "100000.00")
    empresa_a2_simples = cenario_simples(empresa_a2)
    atividade_padrao(empresa_a2_simples, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)

    excecao = _recusa(empresa_a2_simples, 2026, 6)

    assert {"mes_nao_confirmado", "rbt12_nao_apuravel"} <= _codigos(excecao)
