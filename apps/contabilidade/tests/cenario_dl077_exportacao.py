"""Cenário SINTÉTICO da exportação de lançamentos e saldos (DL-077, fatia 2).

Dados fictícios: razões sociais e CNPJs de teste, contas genéricas, valores redondos. Não há
dado de cliente. Este módulo não começa com `test_`, então o pytest não o coleta: ele só é
importado pelos três arquivos `test_dl077_exportacao_lancamentos_*.py`.

O cenário é desenhado para que TODO número esperado possa ser conferido à mão. Os saldos de
janeiro a março de 2026 estão calculados na docstring de `montar_cenario_de_referencia`.
"""

from datetime import date
from decimal import Decimal

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import (
    _chave_idempotencia_zeramento,
    criar_lancamento,
    estornar_lancamento,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

CNPJ_DA_EMPRESA = "77777777000177"
CNPJ_DA_OUTRA_EMPRESA = "88888888000188"

# (código, nome, código da conta superior, analítica, tipo, natureza). Ordem: superior antes.
PLANO = (
    ("1", "Ativo", None, False, TipoConta.ATIVO, NaturezaConta.DEVEDORA),
    ("1.1", "Circulante", "1", False, TipoConta.ATIVO, NaturezaConta.DEVEDORA),
    ("1.1.1", "Caixa", "1.1", True, TipoConta.ATIVO, NaturezaConta.DEVEDORA),
    ("1.1.2", "Banco", "1.1", True, TipoConta.ATIVO, NaturezaConta.DEVEDORA),
    ("2", "Passivo", None, False, TipoConta.PASSIVO, NaturezaConta.CREDORA),
    ("2.1", "Fornecedores", "2", True, TipoConta.PASSIVO, NaturezaConta.CREDORA),
    ("3", "Receitas", None, False, TipoConta.RECEITA, NaturezaConta.CREDORA),
    ("3.1", "Vendas", "3", True, TipoConta.RECEITA, NaturezaConta.CREDORA),
    ("4", "Despesas", None, False, TipoConta.DESPESA, NaturezaConta.DEVEDORA),
    ("4.1", "Aluguel", "4", True, TipoConta.DESPESA, NaturezaConta.DEVEDORA),
    ("5", "Patrimonio liquido", None, False, TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA),
    ("5.1", "Capital", "5", True, TipoConta.PATRIMONIO_LIQUIDO, NaturezaConta.CREDORA),
)


def criar_empresa(*, escritorio, razao_social, cnpj):
    return Empresa.objects.create(escritorio=escritorio, razao_social=razao_social, cnpj=cnpj)


def criar_escritorio(nome, cnpj):
    return Escritorio.objects.create(nome=nome, cnpj=cnpj)


def criar_plano(empresa):
    """Cria o plano sintético da empresa e devolve {código: Conta}."""
    contas = {}
    for codigo, nome, pai, analitica, tipo, natureza in PLANO:
        contas[codigo] = Conta.objects.create(
            empresa=empresa,
            codigo=codigo,
            nome=nome,
            conta_pai=contas[pai] if pai else None,
            aceita_lancamento=analitica,
            tipo=tipo,
            natureza=natureza,
        )
    return contas


def lancar(empresa, contas, data, historico, debitos, creditos, **extra):
    """Cria um lançamento. `debitos` e `creditos` são listas de (código da conta, valor texto)."""
    itens = [
        {"conta": contas[c], "tipo": TipoPartida.DEBITO, "valor": Decimal(v)} for c, v in debitos
    ] + [
        {"conta": contas[c], "tipo": TipoPartida.CREDITO, "valor": Decimal(v)} for c, v in creditos
    ]
    return criar_lancamento(empresa=empresa, data=data, historico=historico, itens=itens, **extra)


def montar_cenario_de_referencia(empresa, contas):
    """Lançamentos de janeiro a março de 2026, com N×M, estorno e zeramento.

    Os números, para conferir à mão (valores em reais):

    Movimento por mês, por conta (D = débito, C = crédito):
      jan: Caixa D 1000 | Capital C 1000
      fev: Caixa D 500, C 200 | Vendas C 500 | Aluguel D 300 | Fornecedores C 100
      mar: Caixa D 10, C 500 | Banco D 170 | Fornecedores C 215 | Vendas D 515, C 15
           | Aluguel D 50, C 350 | Capital D 335

    Saldos (D − C) no fim de cada mês:
      jan: Caixa 1000 | Capital -1000
      fev: Caixa 1300 | Aluguel 300 | Fornecedores -100 | Vendas -500 | Capital -1000
      mar: Caixa 810 | Banco 170 | Fornecedores -315 | Vendas 0 | Aluguel 0 | Capital -665

    Os saldos iniciais de março são os finais de fevereiro, e os de fevereiro, os de janeiro.
    Zero para março: Vendas e Aluguel, zerados pelo lançamento de encerramento.
    """
    l1 = lancar(
        empresa,
        contas,
        date(2026, 1, 10),
        "Aporte de capital",
        [("1.1.1", "1000.00")],
        [("5.1", "1000.00")],
    )
    l2 = lancar(
        empresa,
        contas,
        date(2026, 2, 5),
        "Venda à vista",
        [("1.1.1", "500.00")],
        [("3.1", "500.00")],
    )
    l3 = lancar(
        empresa,
        contas,
        date(2026, 2, 20),
        "Pagamento de aluguel e luz",
        [("4.1", "300.00")],
        [("1.1.1", "200.00"), ("2.1", "100.00")],
    )
    l4 = lancar(
        empresa,
        contas,
        date(2026, 3, 3),
        'Compra a prazo; fornecedor "Alfa"',
        [("1.1.2", "150.00"), ("4.1", "50.00")],
        [("2.1", "200.00")],
    )
    estorno = estornar_lancamento(l2, historico="Estorno: Venda à vista", data=date(2026, 3, 4))
    l5 = lancar(
        empresa,
        contas,
        date(2026, 3, 15),
        "Operação com dois e dois",
        [("1.1.1", "10.00"), ("1.1.2", "20.00")],
        [("3.1", "15.00"), ("2.1", "15.00")],
    )
    zeramento = lancar(
        empresa,
        contas,
        date(2026, 3, 31),
        "Encerramento do resultado",
        [("3.1", "15.00"), ("5.1", "335.00")],
        [("4.1", "350.00")],
        # O mesmo formato de chave que `zerar_resultado` grava (DL-043), e a mesma
        # passagem de `permitir_prefixo_reservado` que ele usa.
        chave_idempotencia=_chave_idempotencia_zeramento(
            empresa_id=empresa.id, ano=2026, mes=3, etapa=1, complemento=0
        ),
        permitir_prefixo_reservado=True,
    )
    return {
        "l1": l1,
        "l2": l2,
        "l3": l3,
        "l4": l4,
        "estorno": estorno,
        "l5": l5,
        "zeramento": zeramento,
    }
