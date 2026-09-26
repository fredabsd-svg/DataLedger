"""Regras de domínio PURAS do livro-caixa — formato do código do Carnê-Leão
Web e faixa de data (DL-046, fatia 1).

Mesmo desenho de `apps.contabilidade.validators` (DE-034 item 2 — o mesmo
campo nas outras superfícies): módulo sem ORM, para poder ser importado
tanto por `models.py` (validador de campo, alcança o admin) quanto por
`services.py` (caminho de negócio, API) sem risco de import circular.
"""

import re

from django.core.exceptions import ValidationError

from apps.contabilidade.validators import (
    DATA_MINIMA_LANCAMENTO as _DATA_MINIMA_LANCAMENTO_CONTABIL,
)
from apps.contabilidade.validators import (
    data_maxima_lancamento as _data_maxima_lancamento_contabil,
)
from apps.contabilidade.validators import (
    mensagem_de_data_de_lancamento_fora_da_faixa as _mensagem_fora_da_faixa_contabil,
)

# ⚠️ **Faixa de data REUTILIZADA por ANALOGIA, não uma segunda confirmação
# do Fred especificamente para o livro-caixa** — o RC-77 (2000-01-01 até
# hoje + 30 dias) foi confirmado pelo Fred para o LANÇAMENTO CONTÁBIL
# (2026-09-15). O livro-caixa tem o MESMO risco que motivou a regra (BL-198:
# um "9" digitado no lugar de um "2" grava um lançamento em `9999-12-31`,
# invisível em qualquer relatório de operação normal) — mas ninguém
# perguntou ao Fred se a faixa vale, com os MESMOS números, para o
# livro-caixa. Reportado, não decidido: se ele quiser uma faixa diferente
# para o livro-caixa, é só desacoplar estas duas linhas de import por
# `apps.contabilidade.validators` e definir constantes próprias aqui.
DATA_MINIMA_LANCAMENTO_CAIXA = _DATA_MINIMA_LANCAMENTO_CONTABIL


def data_maxima_lancamento_caixa():
    return _data_maxima_lancamento_contabil()


def mensagem_de_data_de_lancamento_caixa_fora_da_faixa(data):
    return _mensagem_fora_da_faixa_contabil(data)


def validar_data_de_lancamento_caixa_do_modelo(valor):
    """Validador de CAMPO DE MODELO para `LancamentoCaixa.data` — mesmo
    contrato de `apps.contabilidade.validators.
    validar_data_de_lancamento_do_modelo` (levanta `ValidationError`, o
    único tipo que `full_clean()` sabe agregar)."""
    mensagem = mensagem_de_data_de_lancamento_caixa_fora_da_faixa(valor)
    if mensagem is not None:
        raise ValidationError(mensagem)


# ---------------------------------------------------------------------------
# HI-30: a dedutibilidade de cada conta do livro-caixa decorre do código do
# Carnê-Leão Web associado a ela — RENDIMENTO (`R01.xxx.xxx`, receita) ou
# PAGAMENTO (`P10.`/`P11.`/`P20.` + código da conta, despesa). Formato
# levantado nos modelos de arquivo de importação da Receita Federal
# (`escrituracao-carne-leao.zip`, instruções de 2025 — ver o plano
# DL-046 e `docs/projeto/requisitos.md`, RC-127/HI-30). Os arquivos de
# REFERÊNCIA usados para levantar este formato ficam em scratchpad, NUNCA
# copiados para o repositório (instrução da tarefa) — só o FORMATO
# (padrão de dígitos e separadores) é reproduzido aqui, não o conteúdo.
#
# Rendimento: `R01` + "." + TRÊS grupos de dígitos. Exemplos observados:
# `R01.001.001` (trabalho não assalariado / recibo Receita Saúde),
# `R01.001.002` (serviços notariais e de registro), `R01.003.001`
# (aluguel), `R01.004.001` (outros rendimentos).
_REGEX_CODIGO_RENDIMENTO = r"^R01\.\d{3}\.\d{3}$"

# Pagamento: `P10`/`P11` (dedutível/não dedutível — instrução oficial:
# "P10 + . + código da conta" / "P11 + . + código da conta", onde o código
# da conta é do PRÓPRIO plano de contas do usuário, formato livre) ou `P20`
# (imposto pago, pensão alimentícia, previdência oficial — código FIXO da
# Receita, ex. `P20.01.00001`). Nos três casos, um ou mais grupos de
# dígitos separados por ponto depois do prefixo.
_REGEX_CODIGO_PAGAMENTO = r"^P(10|11|20)(\.\d+)+$"

CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO = "R01.001.001"


def codigo_carne_leao_e_rendimento(codigo):
    """`True` se `codigo` tem o formato de um código de RENDIMENTO
    (`R01.xxx.xxx`) — usado para decidir a NATUREZA esperada da conta
    (receita)."""
    return bool(re.fullmatch(_REGEX_CODIGO_RENDIMENTO, codigo or ""))


def codigo_carne_leao_e_pagamento(codigo):
    """`True` se `codigo` tem o formato de um código de PAGAMENTO
    (`P10`/`P11`/`P20` + dígitos) — usado para decidir a NATUREZA esperada
    da conta (despesa)."""
    return bool(re.fullmatch(_REGEX_CODIGO_PAGAMENTO, codigo or ""))


def mensagem_de_codigo_carne_leao_invalido(codigo, *, natureza):
    """Mensagem de recusa se `codigo` não bater com o FORMATO esperado para
    `natureza` ("receita" espera `R01.xxx.xxx`; "despesa" espera
    `P10`/`P11`/`P20` + dígitos); `None` se estiver correto.

    Devolve mensagem em vez de levantar — mesmo padrão de `apps.
    contabilidade.validators.mensagem_de_data_de_lancamento_fora_da_faixa`:
    os consumidores (validador de campo do modelo, guarda de `clean()`,
    serializer) precisam de tipos de exceção diferentes para a MESMA regra.
    """
    if not isinstance(codigo, str) or not codigo:
        return "O código do Carnê-Leão Web é obrigatório."
    if natureza == "receita":
        if not codigo_carne_leao_e_rendimento(codigo):
            return (
                f"O código do Carnê-Leão Web '{codigo}' não tem o formato de "
                "rendimento (R01.xxx.xxx) esperado para uma conta de receita."
            )
    elif natureza == "despesa":
        if not codigo_carne_leao_e_pagamento(codigo):
            return (
                f"O código do Carnê-Leão Web '{codigo}' não tem o formato de "
                "pagamento (P10/P11/P20 seguido de dígitos) esperado para uma "
                "conta de despesa."
            )
    else:
        return f"Natureza '{natureza}' desconhecida — não é possível validar o código."
    return None
