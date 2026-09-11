from django.db import transaction
from django.utils import timezone

from apps.contabilidade.models import ItemLancamento, LancamentoContabil, TipoPartida


class LancamentoInvalido(Exception):
    """Levantado quando os dados de um lançamento violam uma regra contábil."""


@transaction.atomic
def criar_lancamento(*, empresa, data, historico, itens, criado_por=None, estorno_de=None):
    """Cria um lançamento contábil validando a igualdade de partidas dobradas.

    `itens` é uma lista de dicts {"conta": Conta, "tipo": TipoPartida, "valor": Decimal}.
    Toda validação acontece antes de qualquer gravação, e a criação do
    lançamento com seus itens é atômica: ou tudo é gravado, ou nada é.
    """
    if len(itens) < 2:
        raise LancamentoInvalido("Um lançamento precisa de ao menos duas partidas.")

    total_debito = sum(
        (item["valor"] for item in itens if item["tipo"] == TipoPartida.DEBITO),
        start=type(itens[0]["valor"])(0),
    )
    total_credito = sum(
        (item["valor"] for item in itens if item["tipo"] == TipoPartida.CREDITO),
        start=type(itens[0]["valor"])(0),
    )

    if total_debito != total_credito:
        raise LancamentoInvalido(
            f"Débitos ({total_debito}) e créditos ({total_credito}) devem ser iguais."
        )
    if total_debito <= 0:
        raise LancamentoInvalido("O lançamento precisa ter valor maior que zero.")

    for item in itens:
        conta = item["conta"]
        if conta.empresa_id != empresa.id:
            raise LancamentoInvalido(f"A conta {conta} não pertence a esta empresa.")
        if not conta.aceita_lancamento:
            raise LancamentoInvalido(f"A conta {conta} não aceita lançamento direto.")

    lancamento = LancamentoContabil.objects.create(
        empresa=empresa,
        data=data,
        historico=historico,
        criado_por=criado_por,
        estorno_de=estorno_de,
    )
    for item in itens:
        ItemLancamento.objects.create(
            lancamento=lancamento, conta=item["conta"], tipo=item["tipo"], valor=item["valor"]
        )
    return lancamento


def estornar_lancamento(lancamento, *, criado_por=None, data=None, historico=None):
    """Cria o lançamento reverso (débito e crédito trocados) do original.

    Nunca edita nem apaga o lançamento original — o estorno é sempre um
    novo lançamento, preservando a trilha contábil completa.
    """
    if lancamento.estorno_de_id is not None:
        raise LancamentoInvalido("Não é possível estornar um lançamento que já é um estorno.")

    itens_invertidos = [
        {
            "conta": item.conta,
            "tipo": TipoPartida.CREDITO if item.tipo == TipoPartida.DEBITO else TipoPartida.DEBITO,
            "valor": item.valor,
        }
        for item in lancamento.itens.all()
    ]

    return criar_lancamento(
        empresa=lancamento.empresa,
        data=data or timezone.localdate(),
        historico=historico or f"Estorno do lançamento {lancamento.pk}",
        itens=itens_invertidos,
        criado_por=criado_por,
        estorno_de=lancamento,
    )
