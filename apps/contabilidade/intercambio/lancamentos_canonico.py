"""Registros neutros da EXPORTAÇÃO de lançamentos e saldos (DL-077, fatia 2).

É o espelho, para o caminho de saída, do que `canonico.py` é para o de entrada.
Os escritores de lançamento (`formatos/*_lancamentos.py`) recebem SOMENTE estes
dados, nunca o ORM. Assim a regra de formato fica testável sem banco, e a regra
de dados (quais lançamentos saem, quais saldos) fica em `lancamentos.py`.

Convenções:
- `valor` é `Decimal` com exatamente 2 casas, igual a `ItemLancamento.valor`.
- `saldo_inicial` e `saldo_final` são saldos COM SINAL de débito menos crédito:
  positivo = saldo devedor, negativo = saldo credor. É a forma que a ECD pede
  (VL_SLD_* com IND_DC_*) e não depende da natureza cadastrada da conta.
- `numero` é o identificador estável do lançamento no DataLedger (a chave
  primária). Na ECD vira NUM_LCTO; no formato próprio, a coluna `numero`.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import LADO_CREDITO, LADO_DEBITO


@dataclass(frozen=True)
class PartidaParaExportar:
    """Um lado de um lançamento: conta (pelo código), débito ou crédito, valor."""

    codigo_conta: str
    lado: str  # `LADO_DEBITO` ou `LADO_CREDITO` (canonico.py)
    valor: Decimal


@dataclass(frozen=True)
class LancamentoParaExportar:
    """Um lançamento efetivado, com suas partidas, pronto para ser escrito.

    `zeramento` marca o lançamento gerado pelo zeramento do resultado (DL-043): na
    ECD ele sai com IND_LCTO = E. `estorno` marca o lançamento reverso de outro:
    ele sai como lançamento normal, com o próprio histórico.
    """

    numero: int
    data: date
    historico: str
    zeramento: bool
    estorno: bool
    partidas: tuple[PartidaParaExportar, ...]

    @property
    def total_debito(self) -> Decimal:
        return sum((p.valor for p in self.partidas if p.lado == LADO_DEBITO), Decimal("0.00"))

    @property
    def total_credito(self) -> Decimal:
        return sum((p.valor for p in self.partidas if p.lado == LADO_CREDITO), Decimal("0.00"))


@dataclass(frozen=True)
class SaldoDaConta:
    """Saldo de uma conta analítica num mês, com sinal de débito menos crédito."""

    codigo_conta: str
    saldo_inicial: Decimal
    debitos: Decimal
    creditos: Decimal
    saldo_final: Decimal


@dataclass(frozen=True)
class PeriodoDeSaldo:
    """Um mês completo de saldos (I150) e as contas analíticas com saldo ou movimento (I155)."""

    inicio: date
    fim: date
    contas: tuple[SaldoDaConta, ...]
