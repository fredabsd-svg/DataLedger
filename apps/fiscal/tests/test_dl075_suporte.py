"""Apoio dos testes da DL-075 (frente A): fábricas de dados SINTÉTICOS.

Não contém casos de teste. Os números dos casos de referência ficam escritos à mão
nos próprios testes (`test_dl075_referencia.py`), nunca calculados aqui. Reusa as
fábricas da DL-074 (`test_dl074_suporte`) para receita e escrituração.
"""

from datetime import date
from decimal import Decimal

from apps.fiscal import folha_fator_r as folha_servico
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import EnquadramentoAtividade
from apps.fiscal.tests.test_dl074_suporte import (
    fixar_inicio_de_uso,
    informar_e_confirmar,
    preparar_simples,
)

COMPONENTES_ZERO = {
    "remuneracao_empregados_avulsos": Decimal("0"),
    "pro_labore_autonomos": Decimal("0"),
    "decimo_terceiro": Decimal("0"),
    "cpp_recolhida": Decimal("0"),
    "fgts_recolhido": Decimal("0"),
}
SUPORTE_SINTETICO = "Extrato sintético de teste (folha)."


def cenario_simples(empresa_a, *, abertura=date(2015, 3, 10), inicio_simples=date(2018, 1, 1)):
    """Empresa com início de uso em 2025/01 (receita informada sem restrição de histórico),
    abertura no CNPJ e Simples a partir de `inicio_simples`."""
    fixar_inicio_de_uso(empresa_a, 2025, 1)
    return preparar_simples(empresa_a, abertura=abertura, inicio_simples=inicio_simples)


def atividade_padrao(empresa, usuario, enquadramento, *, inicio=date(2018, 1, 1), fim=None):
    """Atividade padrão, cadastrada pelo serviço (com trilha)."""
    return servico_pre_das.cadastrar_atividade(
        empresa,
        {
            "descricao": "Serviço sintético de teste",
            "codigo_subitem": "",
            "enquadramento": enquadramento,
            "inicio": inicio,
            "fim": fim,
            "padrao": True,
        },
        usuario,
    )


def receber_e_confirmar_mes(empresa, usuario, ano, mes, valor, mercado="interno"):
    """Receita informada confirmada no mês e o mês confirmado como "receita completa"."""
    informar_e_confirmar(empresa, usuario, ano, mes, valor, mercado=mercado)
    return servico_receita.confirmar_mes(empresa, ano, mes, usuario)


def janela_de_receitas(empresa, usuario, ate_ano, ate_mes, valores_por_mes):
    """Confirma os 12 meses ANTERIORES ao PA com os valores dados (lista, do mais antigo).

    `valores_por_mes` tem 12 valores, em ordem, para os meses de (PA-12) a (PA-1).
    """
    assert len(valores_por_mes) == 12, "a janela do art. 22 tem 12 meses"
    for (ano, mes), valor in zip(
        sequencia_anterior(ate_ano, ate_mes), valores_por_mes, strict=True
    ):
        receber_e_confirmar_mes(empresa, usuario, ano, mes, valor)


def folha_confirmada(empresa, usuario, ano, mes, *, remuneracao=Decimal("0"), **outros):
    """Folha do mês lançada e confirmada. `remuneracao` vai no componente de empregados."""
    componentes = dict(COMPONENTES_ZERO)
    componentes["remuneracao_empregados_avulsos"] = Decimal(remuneracao)
    componentes.update({chave: Decimal(valor) for chave, valor in outros.items()})
    folha = folha_servico.lancar_folha(empresa, ano, mes, componentes, SUPORTE_SINTETICO, usuario)
    return folha_servico.confirmar_folha(folha, usuario)


def folhas_dos_12_meses(empresa, usuario, ate_ano, ate_mes, valores_por_mes):
    """Folha CONFIRMADA dos 12 meses anteriores ao PA (ordem: do mais antigo)."""
    assert len(valores_por_mes) == 12, "a janela do art. 22 tem 12 meses"
    for (ano, mes), valor in zip(
        sequencia_anterior(ate_ano, ate_mes), valores_por_mes, strict=True
    ):
        folha_confirmada(empresa, usuario, ano, mes, remuneracao=valor)


def sequencia_anterior(ano, mes):
    """Os 12 meses ANTERIORES ao PA `ano/mes`, do mais antigo ao mais recente."""
    indice = ano * 12 + (mes - 1)
    return [((indice - 12 + k) // 12, (indice - 12 + k) % 12 + 1) for k in range(12)]


def enquadramento_iii_ou_v():
    return EnquadramentoAtividade.ANEXO_III_OU_V_FATOR_R
