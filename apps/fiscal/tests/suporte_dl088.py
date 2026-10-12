"""Suporte da DL-088 (frente A1): janela defasada de 2027 com receita SINTÉTICA.

Não contém casos de teste nem calcula valor esperado: os números ficam escritos à mão nos testes.
Reusa os serviços reais de receita (`receber_e_confirmar_mes`), sem simular o banco.
"""

from apps.fiscal import receita as servico_receita
from apps.fiscal.tests.test_dl075_suporte import receber_e_confirmar_mes

# Janela do § 1º para o PA 01/2027: os 12 meses antecedentes ao MÊS ANTERIOR (12/2026), ou seja
# 12/2025 a 11/2026. Mês anterior ao PA, 12/2026, NÃO entra na janela.
JANELA_DE_2027_01 = [(2025, 12)] + [(2026, mes) for mes in range(1, 12)]
MES_ANTERIOR_AO_PA_2027_01 = (2026, 12)


def confirmar_janela_de_2027_01(empresa, usuario, valor_mensal, *, valor_mes_anterior=0):
    """Confirma os 12 meses da janela com `valor_mensal` cada (interno) e 12/2026 com
    `valor_mes_anterior`. Se o cálculo usasse a janela antiga (01/2026 a 12/2026), o resultado
    mudaria: é o que estes testes guardam."""
    for ano, mes in JANELA_DE_2027_01:
        receber_e_confirmar_mes(empresa, usuario, ano, mes, valor_mensal)
    if valor_mes_anterior:
        receber_e_confirmar_mes(empresa, usuario, *MES_ANTERIOR_AO_PA_2027_01, valor_mes_anterior)
    else:
        servico_receita.confirmar_mes(empresa, *MES_ANTERIOR_AO_PA_2027_01, usuario)


def receber_pa_2027_01(empresa, usuario, valor, mercado="interno"):
    """Receita do PA 01/2027 informada e confirmada (o mês fica confirmado completo)."""
    return receber_e_confirmar_mes(empresa, usuario, 2027, 1, valor, mercado=mercado)
