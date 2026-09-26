"""Serviços do livro-caixa (DL-046, fatia 1) — RC-113/RC-114/RC-128.

Mesmo desenho geral de `apps.contabilidade.services` (criação com
validação centralizada, idempotência por impressão digital, estorno
rastreável, trilha de auditoria na MESMA transação), simplificado para o
regime de CAIXA: um lançamento tem uma conta e um valor só (nunca partidas
dobradas — isso é a contabilidade).
"""

import hashlib
import json
from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.core.dinheiro import ValorMonetarioInvalido, casas_decimais, para_decimal
from apps.core.restricoes import mensagens_de, restricao_como_400
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
)
from apps.livro_caixa.validators import (
    mensagem_de_data_de_lancamento_caixa_fora_da_faixa,
)

# Mesma escala da escrituração manual contábil (DE-010) — recusa, nunca
# arredonda.
ESCALA_MAXIMA_LANCAMENTO_CAIXA = 2


class LancamentoCaixaInvalido(Exception):
    """Erro de domínio na criação/estorno de um lançamento de caixa —
    mesmo papel de `LancamentoInvalido` (contabilidade): todo erro de
    negócio deste módulo usa este tipo, para a view traduzir para 400 sem
    precisar conhecer cada causa em separado."""


class ChaveIdempotenciaConflitanteCaixa(Exception):
    """A MESMA `chave_idempotencia`, na MESMA empresa, foi reaproveitada
    para um lançamento de caixa com conteúdo DIFERENTE (mesmo espírito de
    `ChaveIdempotenciaConflitante`, contabilidade) — nunca devolve o
    lançamento errado como se fosse sucesso."""


def _impressao_digital_caixa(
    *,
    empresa_id,
    conta_id,
    data,
    valor,
    historico,
    documento_origem,
    recebido_de,
    cpf_titular_pagamento,
    cpf_beneficiario_servico,
    cnpj_pagador,
    estorno_de_id,
):
    """Hash estável do conteúdo de um lançamento de caixa, para a
    idempotência — mesmo desenho de `_impressao_digital` (contabilidade):
    `json.dumps(..., sort_keys=True)` para a fronteira entre campos nunca
    ser forjável pelo conteúdo de um campo de texto livre."""
    estrutura = {
        "empresa_id": empresa_id,
        "conta_id": conta_id,
        "data": data.isoformat(),
        "valor": str(Decimal(valor).quantize(Decimal("0.01"))),
        "historico": (historico or "").strip(),
        "documento_origem": (documento_origem or "").strip(),
        "recebido_de": recebido_de or "",
        "cpf_titular_pagamento": cpf_titular_pagamento or "",
        "cpf_beneficiario_servico": cpf_beneficiario_servico or "",
        "cnpj_pagador": cnpj_pagador or "",
        "estorno_de_id": estorno_de_id,
    }
    bruto = json.dumps(estrutura, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(bruto).hexdigest()


def criar_conta_livro_caixa(
    *, empresa, codigo, nome, natureza, codigo_carne_leao, ativa=True, criado_por=None, request=None
):
    """Cria uma conta do livro-caixa, validando tudo por `full_clean()`
    ANTES de gravar — um lugar só para a recusa por modo de escrituração e
    a coerência natureza <-> código do Carnê-Leão Web
    (`ContaLivroCaixa.clean()`), em vez de duplicar essas regras aqui.

    `DjangoValidationError` (de `full_clean()`) propaga para quem chamou
    sem tradução — a view é quem sabe traduzir para o protocolo HTTP,
    preservando o campo de cada erro (`message_dict`).
    """
    conta = ContaLivroCaixa(
        empresa=empresa,
        codigo=codigo,
        nome=nome,
        natureza=natureza,
        codigo_carne_leao=codigo_carne_leao,
        ativa=ativa,
    )
    conta.full_clean()

    with (
        transaction.atomic(),
        restricao_como_400(mensagens_de("conta_livro_caixa_codigo_unico_por_empresa")),
    ):
        conta.save()
        registrar(
            acao="conta_livro_caixa.criada",
            usuario=criado_por,
            escritorio=empresa.escritorio,
            objeto=conta,
            request=request,
            detalhes={"empresa_id": empresa.id, "codigo": codigo, "natureza": natureza},
        )
    return conta


@transaction.atomic
def criar_lancamento_caixa(
    *,
    empresa,
    conta,
    data,
    valor,
    historico,
    documento_origem="",
    recebido_de=None,
    cpf_titular_pagamento="",
    cpf_beneficiario_servico="",
    cnpj_pagador="",
    criado_por=None,
    chave_idempotencia=None,
    estorno_de=None,
    request=None,
):
    """Cria um lançamento de caixa, validando tudo ANTES de gravar.

    Mesma ordem de `criar_lancamento` (contabilidade): recusa por modo de
    escrituração primeiro (defesa em profundidade — a view já recusa
    antes de chegar aqui), depois validação de dado, e só então a
    checagem de idempotência (nunca "atalha" para sucesso com um corpo
    inválido só porque a chave já existe).

    `chave_idempotencia` opcional: repetir a chamada com a MESMA chave,
    na MESMA empresa, e o MESMO conteúdo (comparado por impressão
    digital) devolve o lançamento já existente em vez de duplicar
    (`criado_agora=False`, atributo não persistido). Chave repetida com
    conteúdo DIFERENTE levanta `ChaveIdempotenciaConflitanteCaixa`.
    """
    try:
        recusar_se_nao_livro_caixa(empresa)
    except EmpresaNaoEmModoLivroCaixa as exc:
        raise LancamentoCaixaInvalido(exc.mensagem) from exc

    if conta.empresa_id != empresa.id:
        raise LancamentoCaixaInvalido(
            "A conta do livro-caixa informada não pertence a esta empresa."
        )

    try:
        valor = para_decimal(valor)
    except ValorMonetarioInvalido as exc:
        raise LancamentoCaixaInvalido(str(exc)) from exc
    if valor <= 0:
        raise LancamentoCaixaInvalido(
            f"O valor do lançamento deve ser maior que zero; recebido {valor}."
        )
    escala = casas_decimais(valor)
    if escala > ESCALA_MAXIMA_LANCAMENTO_CAIXA:
        raise LancamentoCaixaInvalido(
            f"O valor {valor} tem {escala} casas decimais; o livro-caixa aceita no "
            f"máximo {ESCALA_MAXIMA_LANCAMENTO_CAIXA}."
        )
    # `casas_decimais()` normaliza (zero à direita não é precisão real) —
    # mas o `DecimalField.decimal_places=2` do modelo NÃO normaliza: o
    # `DecimalValidator` do próprio Django olha o expoente CRU de
    # `Decimal`, e "100.000" tem exponent=-3 mesmo valendo exatamente
    # "100.00". Sem este `quantize()`, um valor como "100.000" passaria
    # aqui e ainda assim seria recusado por `full_clean()` mais abaixo, com
    # uma mensagem que contradiz esta checagem ("não pode ter mais de 2
    # casas decimais" depois de este código já ter aceitado 0 casas
    # SIGNIFICATIVAS). `quantize()` é seguro exatamente porque `escala` já
    # provou que a redução para 2 casas não perde informação nenhuma.
    valor = valor.quantize(Decimal("0.01"))

    mensagem_data = mensagem_de_data_de_lancamento_caixa_fora_da_faixa(data)
    if mensagem_data is not None:
        raise LancamentoCaixaInvalido(mensagem_data)

    if "\x00" in (historico or ""):
        raise LancamentoCaixaInvalido("O histórico não pode conter o caractere nulo (código 0).")
    if chave_idempotencia and "\x00" in chave_idempotencia:
        raise LancamentoCaixaInvalido(
            "A chave de idempotência não pode conter o caractere nulo (código 0)."
        )

    if chave_idempotencia:
        impressao = _impressao_digital_caixa(
            empresa_id=empresa.id,
            conta_id=conta.id,
            data=data,
            valor=valor,
            historico=historico,
            documento_origem=documento_origem,
            recebido_de=recebido_de,
            cpf_titular_pagamento=cpf_titular_pagamento,
            cpf_beneficiario_servico=cpf_beneficiario_servico,
            cnpj_pagador=cnpj_pagador,
            estorno_de_id=estorno_de.id if estorno_de is not None else None,
        )
        existente = LancamentoCaixa.objects.filter(
            empresa=empresa, chave_idempotencia=chave_idempotencia
        ).first()
        if existente is not None:
            if existente.chave_idempotencia_fingerprint == impressao:
                existente.criado_agora = False
                return existente
            raise ChaveIdempotenciaConflitanteCaixa(
                "Esta chave de idempotência já foi usada nesta empresa para um "
                "lançamento de caixa com conteúdo diferente."
            )
    else:
        impressao = None

    lancamento = LancamentoCaixa(
        empresa=empresa,
        conta=conta,
        data=data,
        valor=valor,
        historico=historico,
        documento_origem=documento_origem or "",
        recebido_de=recebido_de or None,
        cpf_titular_pagamento=cpf_titular_pagamento or "",
        cpf_beneficiario_servico=cpf_beneficiario_servico or "",
        cnpj_pagador=cnpj_pagador or "",
        chave_idempotencia=chave_idempotencia or None,
        chave_idempotencia_fingerprint=impressao,
        estorno_de=estorno_de,
        criado_por=criado_por,
    )
    try:
        lancamento.full_clean()
    except DjangoValidationError as exc:
        raise LancamentoCaixaInvalido("; ".join(exc.messages)) from exc

    try:
        lancamento.save()
    except IntegrityError:
        raise

    registrar(
        acao="lancamento_caixa.criado",
        usuario=criado_por,
        escritorio=empresa.escritorio,
        objeto=lancamento,
        request=request,
        detalhes={
            "empresa_id": empresa.id,
            "conta": conta.codigo,
            "valor": str(valor),
            "data": data.isoformat(),
            "estorno_de_id": estorno_de.id if estorno_de is not None else None,
        },
    )
    lancamento.criado_agora = True
    return lancamento


def estornar_lancamento_caixa(
    lancamento, *, criado_por=None, data=None, historico=None, request=None
):
    """Cria o lançamento reverso de `lancamento` — mesma conta, mesmo
    valor, `estorno_de=lancamento`. Nunca edita nem apaga o original.

    Estorno único (mesmo padrão de `estornar_lancamento`, contabilidade):
    `select_for_update()` bloqueia a linha do original durante toda a
    operação (evita duas chamadas concorrentes passarem pela checagem
    "ainda não foi estornado" antes de qualquer gravação); a constraint de
    banco `lancamento_caixa_estorno_de_unico` é a defesa residual de
    corrida.

    A data do estorno nunca pode ser anterior à do original (mesmo RC-78
    da contabilidade, aplicado por analogia — reportado, não uma segunda
    confirmação do Fred para o livro-caixa).
    """
    with transaction.atomic():
        lancamento = LancamentoCaixa.objects.select_for_update().get(pk=lancamento.pk)

        if lancamento.estorno_de_id is not None:
            raise LancamentoCaixaInvalido(
                "Não é possível estornar um lançamento que já é um estorno."
            )
        if lancamento.estornos.exists():
            raise LancamentoCaixaInvalido("Este lançamento já foi estornado.")

        data_do_estorno = data or timezone.localdate()
        if data_do_estorno < lancamento.data:
            raise LancamentoCaixaInvalido(
                "A data do estorno não pode ser anterior à data do lançamento original "
                f"({lancamento.data.strftime('%d/%m/%Y')})."
            )

        return criar_lancamento_caixa(
            empresa=lancamento.empresa,
            conta=lancamento.conta,
            data=data_do_estorno,
            valor=lancamento.valor,
            historico=historico or f"Estorno do lançamento de caixa {lancamento.pk}",
            documento_origem=lancamento.documento_origem,
            recebido_de=lancamento.recebido_de,
            cpf_titular_pagamento=lancamento.cpf_titular_pagamento,
            cpf_beneficiario_servico=lancamento.cpf_beneficiario_servico,
            cnpj_pagador=lancamento.cnpj_pagador,
            criado_por=criado_por,
            estorno_de=lancamento,
            request=request,
        )


def apurar_livro_caixa(*, empresa, inicio, fim):
    """Relatório "Livro Caixa" do período `[inicio, fim]` — lançamentos em
    ordem cronológica, totais de entradas (receita) e saídas (despesa), e
    saldo, CONCILIÁVEL com os lançamentos (critério 3 do plano).

    Um ESTORNO aparece como uma linha PRÓPRIA (nunca oculta nem cancela o
    original na listagem — "os estornos visíveis" do critério da tarefa),
    mas contribui aos TOTAIS com o sinal INVERTIDO do original: um estorno
    de receita SUBTRAI da receita total, um estorno de despesa SUBTRAI da
    despesa total — nunca aparece como uma despesa/receita nova. Sem essa
    conversão de sinal, o total do período dobraria a magnitude do
    lançamento estornado, em vez de zerar o seu efeito.

    UMA consulta (`select_related` na conta), número de consultas
    CONSTANTE em relação ao número de lançamentos.
    """
    lancamentos = list(
        LancamentoCaixa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .select_related("conta")
        .order_by("data", "id")
    )

    zero = Decimal("0.00")
    total_entradas = zero
    total_saidas = zero
    itens = []
    for lancamento in lancamentos:
        e_estorno = lancamento.estorno_de_id is not None
        sinal = -1 if e_estorno else 1
        contribuicao = sinal * lancamento.valor
        if lancamento.conta.natureza == NaturezaCaixa.RECEITA:
            total_entradas += contribuicao
        else:
            total_saidas += contribuicao
        itens.append(
            {
                "lancamento_id": lancamento.id,
                "data": lancamento.data,
                "conta": lancamento.conta.codigo,
                "conta_nome": lancamento.conta.nome,
                "natureza": lancamento.conta.natureza,
                "valor": lancamento.valor,
                "historico": lancamento.historico,
                "documento_origem": lancamento.documento_origem,
                "estorno_de_id": lancamento.estorno_de_id,
                "e_estorno": e_estorno,
            }
        )

    return {
        "empresa_id": empresa.id,
        "data_inicio": inicio,
        "data_fim": fim,
        "itens": itens,
        "total_entradas": total_entradas,
        "total_saidas": total_saidas,
        "saldo": total_entradas - total_saidas,
    }
