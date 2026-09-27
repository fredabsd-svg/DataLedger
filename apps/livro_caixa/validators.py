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


def codigo_carne_leao_e_deducao_do_carne_leao(codigo):
    """`True` se `codigo` é `P20` (imposto pago, previdência oficial ou
    pensão alimentícia) — D3/DE-087 item 13: estes pagamentos são
    DEDUÇÕES do carnê-leão (art. 68, RIR/2018), não despesas de custeio, e
    por isso `apurar_livro_caixa` os separa num grupo próprio na
    apresentação do relatório, embora ambos os grupos continuem
    subtraindo do saldo de CAIXA (regime de caixa: toda saída de dinheiro
    reduz o saldo, independentemente da classificação tributária)."""
    return bool(codigo) and codigo.startswith("P20")


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


# ---------------------------------------------------------------------------
# DE-088 item 1 (reabertura da DE-087 item 6, rodada de reconferência): a
# exigência de CPF/CNPJ não é universal para toda receita — o leiaute
# oficial do Carnê-Leão Web (instruções dos modelos de importação, Receita,
# 2025) aplica a regra POR MODELO de rendimento. Tabela levantada a partir
# dos seis arquivos-modelo oficiais em scratchpad (NUNCA copiados para o
# repositório — só o formato/composição de campos é reproduzido aqui):
#
# - `Modelo de arquivo para rendimentos do Trabalho não Assalariado.csv`
#   (código `R01.001.001`, também usado por
#   `Modelo de arquivo para recibos do Receita Saúde.csv`, sempre PF):
#   PF — CPF do titular do pagamento obrigatório; CPF do beneficiário do
#   serviço OU o indicador "CPF do beneficiário não informado" (nunca os
#   dois, nunca nenhum dos dois). PJ — CNPJ obrigatório (+ indicador de
#   IRRF, fora desta fatia — RC-127/fatia 3). EX — nenhum campo.
# - `Modelo de arquivo para rendimentos de Serviços Notariais e de
#   Registro.csv` (`R01.001.002`): PF — CPF do titular obrigatório; CPF do
#   beneficiário e o indicador ficam VAZIOS (o modelo nem tem a exigência
#   que o indicador pressupõe — instrução do campo 10: "só nos casos em que
#   houver a exigência do CPF do beneficiário"). PJ — CNPJ obrigatório.
#   EX — nenhum campo.
# - `Modelo de Arquivo para Aluguel e Outros rendimentos.csv`
#   (`R01.003.001` aluguel, `R01.004.001` outros rendimentos): o leiaute só
#   tem 7 campos (sem nenhum de CPF/CNPJ) — nunca exige nem aceita CPF do
#   titular/beneficiário, o indicador, ou CNPJ, em NENHUM `recebido_de`.
#
# Código de rendimento fora destes quatro (qualquer outro `R01.xxx.xxx`):
# sem tabela oficial completa ainda (PE-71) — "sem exigência de CPF/CNPJ",
# mas a coerência universal abaixo (CPF só em PF, CNPJ só em PJ, indicador
# só onde o modelo o prevê — que um código desconhecido nunca prevê)
# continua valendo.
MODELO_TRABALHO_NAO_ASSALARIADO = "trabalho_nao_assalariado"
MODELO_NOTARIAL = "notarial"
MODELO_ALUGUEL_OUTROS = "aluguel_outros"
MODELO_DESCONHECIDO = "desconhecido"

_CODIGO_PARA_MODELO_DE_RENDIMENTO = {
    "R01.001.001": MODELO_TRABALHO_NAO_ASSALARIADO,
    "R01.001.002": MODELO_NOTARIAL,
    "R01.003.001": MODELO_ALUGUEL_OUTROS,
    "R01.004.001": MODELO_ALUGUEL_OUTROS,
}


def modelo_do_codigo_de_rendimento(codigo):
    """Devolve o MODELO oficial (uma das constantes `MODELO_*`) associado a
    `codigo`, ou `MODELO_DESCONHECIDO` se `codigo` não estiver na tabela
    (PE-71 — tabela completa de códigos ainda não confirmada)."""
    return _CODIGO_PARA_MODELO_DE_RENDIMENTO.get(codigo, MODELO_DESCONHECIDO)


def erros_de_cpf_cnpj_do_rendimento(
    modelo,
    *,
    recebido_de,
    cpf_titular_pagamento,
    cpf_beneficiario_servico,
    cpf_beneficiario_nao_informado,
    cnpj_pagador,
):
    """Devolve um `dict` `{campo: mensagem}` com os erros de CPF/CNPJ do
    lançamento de RECEITA, conforme `modelo` (`MODELO_*`) e `recebido_de`
    ("PF"/"PJ"/"EX") — vazio (`{}`) quando está tudo coerente.

    Função PURA (sem ORM, sem levantar exceção — mesmo padrão de
    `mensagem_de_codigo_carne_leao_invalido`): quem chama decide o tipo de
    exceção. Só cuida de CPF/CNPJ/indicador; a obrigatoriedade de
    `recebido_de` em si é responsabilidade de quem chama.
    """
    erros = {}

    # Coerência UNIVERSAL, para TODOS os modelos (inclusive o desconhecido):
    # CPF (titular, beneficiário ou o indicador) só é aceito quando PF;
    # CNPJ só quando PJ. Checada ANTES da regra por modelo — um valor fora
    # do lugar é sempre incoerente, independente do que o modelo exigiria.
    if recebido_de != "PF":
        if cpf_titular_pagamento:
            erros["cpf_titular_pagamento"] = (
                "CPF do titular só é aceito quando 'recebido de' é pessoa física (PF)."
            )
        if cpf_beneficiario_servico:
            erros["cpf_beneficiario_servico"] = (
                "CPF do beneficiário só é aceito quando 'recebido de' é pessoa física (PF)."
            )
        if cpf_beneficiario_nao_informado:
            erros["cpf_beneficiario_nao_informado"] = (
                "O indicador de CPF do beneficiário não informado só é aceito quando "
                "'recebido de' é pessoa física (PF)."
            )
    if recebido_de != "PJ" and cnpj_pagador:
        erros["cnpj_pagador"] = "CNPJ só é aceito quando 'recebido de' é pessoa jurídica (PJ)."
    if erros:
        return erros

    if modelo == MODELO_TRABALHO_NAO_ASSALARIADO:
        if recebido_de == "PF":
            if not cpf_titular_pagamento:
                erros["cpf_titular_pagamento"] = (
                    "Rendimento de trabalho não assalariado recebido de pessoa física "
                    "exige o CPF do titular do pagamento (leiaute oficial do "
                    "Carnê-Leão Web)."
                )
            tem_beneficiario = bool(cpf_beneficiario_servico)
            tem_indicador = bool(cpf_beneficiario_nao_informado)
            if tem_beneficiario and tem_indicador:
                erros["cpf_beneficiario_nao_informado"] = (
                    "Não é possível marcar 'CPF do beneficiário não informado' quando "
                    "o CPF do beneficiário foi informado."
                )
            elif not tem_beneficiario and not tem_indicador:
                erros["cpf_beneficiario_servico"] = (
                    "Informe o CPF do beneficiário do serviço, ou marque 'CPF do "
                    "beneficiário não informado' (leiaute oficial do Carnê-Leão Web, "
                    "modelo de trabalho não assalariado)."
                )
        elif recebido_de == "PJ" and not cnpj_pagador:
            erros["cnpj_pagador"] = (
                "Rendimento de trabalho não assalariado recebido de pessoa jurídica "
                "exige o CNPJ do pagador (leiaute oficial do Carnê-Leão Web)."
            )
    elif modelo == MODELO_NOTARIAL:
        if recebido_de == "PF":
            if not cpf_titular_pagamento:
                erros["cpf_titular_pagamento"] = (
                    "Rendimento de serviços notariais e de registro recebido de "
                    "pessoa física exige o CPF do titular do pagamento (leiaute "
                    "oficial do Carnê-Leão Web)."
                )
            if cpf_beneficiario_servico:
                erros["cpf_beneficiario_servico"] = (
                    "O modelo de serviços notariais e de registro não tem CPF do "
                    "beneficiário do serviço — deixe em branco."
                )
            if cpf_beneficiario_nao_informado:
                erros["cpf_beneficiario_nao_informado"] = (
                    "O modelo de serviços notariais e de registro não usa o indicador "
                    "de CPF do beneficiário não informado — deixe desmarcado."
                )
        elif recebido_de == "PJ" and not cnpj_pagador:
            erros["cnpj_pagador"] = (
                "Rendimento de serviços notariais e de registro recebido de pessoa "
                "jurídica exige o CNPJ do pagador (leiaute oficial do Carnê-Leão Web)."
            )
    elif modelo == MODELO_ALUGUEL_OUTROS:
        # O leiaute oficial de aluguel e outros rendimentos não tem CAMPO
        # nenhum de CPF/CNPJ — nunca exige, e por isso também nunca ACEITA,
        # em nenhum `recebido_de` (a coerência universal, acima, já cobriu
        # CNPJ fora de PJ; aqui fechamos o restante).
        if cpf_titular_pagamento:
            erros["cpf_titular_pagamento"] = (
                "O modelo de aluguel e outros rendimentos não tem CPF do titular do "
                "pagamento — deixe em branco."
            )
        if cpf_beneficiario_servico:
            erros["cpf_beneficiario_servico"] = (
                "O modelo de aluguel e outros rendimentos não tem CPF do beneficiário "
                "do serviço — deixe em branco."
            )
        if cpf_beneficiario_nao_informado:
            erros["cpf_beneficiario_nao_informado"] = (
                "O modelo de aluguel e outros rendimentos não usa o indicador de CPF "
                "do beneficiário não informado — deixe desmarcado."
            )
        if cnpj_pagador:
            erros["cnpj_pagador"] = (
                "O modelo de aluguel e outros rendimentos não tem CNPJ do pagador — "
                "deixe em branco."
            )
    else:  # MODELO_DESCONHECIDO
        # PE-71: sem tabela oficial completa, sem exigência de CPF/CNPJ —
        # mas o indicador só é aceito "onde o modelo o prevê" (DE-088), e
        # um código desconhecido nunca prevê.
        if cpf_beneficiario_nao_informado:
            erros["cpf_beneficiario_nao_informado"] = (
                "O indicador de CPF do beneficiário não informado só é aceito nos "
                "códigos de rendimento cujo leiaute oficial o prevê."
            )

    return erros
