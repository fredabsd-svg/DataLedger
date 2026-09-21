"""DL-033, fatia 1 — a camada de saldos DEVOLVE os grupos circulante × não
circulante (`apps.contabilidade.services.apurar_saldos`, chave
`totais_por_classificacao`), o subtotal pelos QUATRO grupos da lei
(`totais_por_grupo`), a identidade aritmética que GARANTE a reconciliação
(`residuo_por_tipo`) e três listas DECLARADAS, não autoritativas
(`contas_com_classificacao_aninhada`, `contas_com_classificacao_desconhecida`,
`contas_sem_classificacao_patrimonial`).

Cobre os critérios do plano `docs/planos/DL-033-circulante-e-nao-circulante.md`
**depois da correção do BLOQUEADOR BL-486** (rodada 1 de auditoria): o
critério 4 deixou de ser "a soma bate quando a cobertura é total" e passou a
ser a IDENTIDADE `Σ(totais_por_classificacao do tipo) + residuo_por_tipo[tipo]
== totais_por_tipo[tipo]`, sempre — não só no caso feliz.

1. Os grupos vêm de `ClassificacaoPatrimonial`, derivado do MODELO — nunca
   uma tupla escrita à mão (DE-056). O mesmo vale para `GrupoDaLei`
   (BL-490): o mapa dos sete valores para os quatro grupos, nunca
   `startswith`.
4. A identidade aritmética do resíduo NUNCA quebra — inclusive nos dois
   casos que a auditoria mediu como bloqueador/alto: contas IRMÃS com
   naturezas diferentes classificadas independentemente (BL-486) e nó
   intermediário desclassificado com movimento próprio (BL-487).
5. Conta sem classificação, COM SALDO, é DECLARADA (BL-493: a régua é o
   saldo, não a marca de `ativo`) — lista própria, vazia quando tudo está
   classificado (controle positivo obrigatório).
6. Migração NÃO classifica conta nenhuma (prova por `MigrationExecutor`
   sobre base COM dados, em `test_dl033_migracao.py`).
7. Isolamento entre empresas não regride.

`apurar_saldos` continua REUSANDO o motor do Balancete — não reimplementa a
regra única de saldo (DE-020). Dados 100% sintéticos, criados nos próprios
testes.
"""

import itertools
from datetime import date
from decimal import Decimal

import pytest

from apps.contabilidade.models import (
    GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL,
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    ClassificacaoPatrimonial,
    Conta,
    GrupoDaLei,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import apurar_saldos, criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _empresa(nome="Empresa DL-033"):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=_cnpj_sintetico())
    return Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=_cnpj_sintetico()
    )


def _conta(
    empresa,
    *,
    codigo,
    nome,
    tipo,
    natureza,
    pai=None,
    classificacao=None,
    aceita_lancamento=True,
):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_patrimonial=classificacao,
        aceita_lancamento=aceita_lancamento,
    )


def _lancar(empresa, data, historico, debito, credito, valor):
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


def _arvore_totalmente_classificada(empresa):
    """Plano de contas com a hierarquia REAL de um Balanço: a classificação
    mora nos NÓS DE GRUPO (um ou dois níveis abaixo da raiz "Ativo"/
    "Passivo", nunca na raiz inteira — a lei não classifica "Ativo", só as
    suas subdivisões, RC-106), com uma retificadora DENTRO do Ativo
    Circulante (mesmo padrão do RC-104/DL-032). Devolve dict codigo -> `Conta`.
    """
    contas = {}
    raiz_ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    ativo_circulante = _conta(
        empresa,
        codigo="1.1",
        nome="ATIVO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
        aceita_lancamento=False,
    )
    contas["caixa"] = _conta(
        empresa,
        codigo="1.1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo_circulante,
    )
    contas["prov_devedores"] = _conta(
        empresa,
        codigo="1.1.2",
        nome="(-) Prov. devedores duvidosos",
        tipo=TipoConta.ATIVO,
        natureza=C,  # retificadora dentro do Ativo Circulante
        pai=ativo_circulante,
    )
    ativo_nao_circulante = _conta(
        empresa,
        codigo="1.2",
        nome="ATIVO NÃO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        aceita_lancamento=False,
    )
    imobilizado = _conta(
        empresa,
        codigo="1.2.1",
        nome="IMOBILIZADO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo_nao_circulante,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
        aceita_lancamento=False,
    )
    contas["veiculos"] = _conta(
        empresa,
        codigo="1.2.1.1",
        nome="Veículos",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=imobilizado,
    )

    raiz_passivo = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    passivo_circulante = _conta(
        empresa,
        codigo="2.1",
        nome="PASSIVO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=raiz_passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
        aceita_lancamento=False,
    )
    contas["fornecedores"] = _conta(
        empresa,
        codigo="2.1.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo_circulante,
    )
    passivo_nao_circulante = _conta(
        empresa,
        codigo="2.2",
        nome="PASSIVO NÃO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=raiz_passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE,
        aceita_lancamento=False,
    )
    contas["financiamentos_lp"] = _conta(
        empresa,
        codigo="2.2.1",
        nome="Financiamentos LP",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo_nao_circulante,
    )

    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    contas["capital"] = _conta(
        empresa,
        codigo="3.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )

    raiz_receita = _conta(empresa, codigo="4", nome="RECEITA", tipo=TipoConta.RECEITA, natureza=C)
    contas["vendas"] = _conta(
        empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C, pai=raiz_receita
    )

    raiz_despesa = _conta(empresa, codigo="5", nome="DESPESA", tipo=TipoConta.DESPESA, natureza=D)
    contas["despesas_gerais"] = _conta(
        empresa,
        codigo="5.1",
        nome="Despesas Gerais",
        tipo=TipoConta.DESPESA,
        natureza=D,
        pai=raiz_despesa,
    )
    return contas


@pytest.fixture
def cenario_classificado():
    """Números conferidos à mão (não são "o que o código devolveu"):

    Ativo Circulante = 1.550,00 (Caixa líquido 1.600,00 − Prov. devedores 50,00)
    Ativo Não Circulante (Imobilizado) = 400,00 (Veículos)
    Ativo total = 1.950,00 (1.550,00 + 400,00)
    Passivo Circulante = 400,00 (Fornecedores)
    Passivo Não Circulante = 300,00 (Financiamentos LP)
    Passivo total = 700,00 (400,00 + 300,00)
    PL = 1.000,00 (Capital)
    Receita = 500,00 (Vendas) / Despesa = 250,00 (200,00 + 50,00)
    Equação: 1.950,00 = 700,00 + 1.000,00 + (500,00 − 250,00) = 1.950,00.
    """
    empresa = _empresa("DL-033 Classificado")
    contas = _arvore_totalmente_classificada(empresa)
    _lancar(
        empresa, date(2026, 1, 2), "Capitalização", contas["caixa"], contas["capital"], "1000.00"
    )
    _lancar(empresa, date(2026, 1, 5), "Venda à vista", contas["caixa"], contas["vendas"], "500.00")
    _lancar(
        empresa,
        date(2026, 1, 10),
        "Pagamento de despesa",
        contas["despesas_gerais"],
        contas["caixa"],
        "200.00",
    )
    _lancar(
        empresa,
        date(2026, 1, 12),
        "Provisão para devedores duvidosos",
        contas["despesas_gerais"],
        contas["prov_devedores"],
        "50.00",
    )
    _lancar(
        empresa,
        date(2026, 1, 20),
        "Compra de veículo a prazo",
        contas["veiculos"],
        contas["fornecedores"],
        "400.00",
    )
    _lancar(
        empresa,
        date(2026, 1, 31),
        "Empréstimo bancário de longo prazo",
        contas["caixa"],
        contas["financiamentos_lp"],
        "300.00",
    )
    return {"empresa": empresa, "contas": contas, "data_base": date(2026, 1, 31)}


# ---------------------------------------------------------------------------
# Critério 1 — os grupos vêm de uma fonte única (DE-056)
# ---------------------------------------------------------------------------


def test_totais_por_classificacao_tem_exatamente_as_chaves_do_modelo(cenario_classificado):
    """Teste DERIVADO, no molde de
    `test_totais_por_tipo_tem_exatamente_as_chaves_do_modelo_tipoconta`
    (DL-032): se `ClassificacaoPatrimonial` ganhar um valor novo sem
    tratamento, este teste reprova — o dict não teria a chave nova."""
    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )
    assert set(saldos["totais_por_classificacao"].keys()) == set(ClassificacaoPatrimonial.values)
    for classificacao in ClassificacaoPatrimonial.values:
        assert isinstance(saldos["totais_por_classificacao"][classificacao], Decimal)


def test_classificacao_sem_nenhuma_conta_entra_com_zero_nao_fica_de_fora(cenario_classificado):
    """`cenario_classificado` não usa os quatro subgrupos "realizável a
    longo prazo", "investimentos" e "intangível" — mesmo assim aparecem no
    dict, com zero, nunca ausentes."""
    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )
    totais = saldos["totais_por_classificacao"]
    assert totais[
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO
    ] == Decimal("0")
    assert totais[ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS] == Decimal("0")
    assert totais[ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL] == Decimal("0")


# ---------------------------------------------------------------------------
# Critério 4 — a soma dos grupos bate com os totais por tipo
# ---------------------------------------------------------------------------


def test_totais_por_classificacao_valores_conferidos_a_mao(cenario_classificado):
    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )
    totais = saldos["totais_por_classificacao"]
    assert totais[ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == Decimal("1550.00")
    assert totais[ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO] == Decimal("400.00")
    assert totais[ClassificacaoPatrimonial.PASSIVO_CIRCULANTE] == Decimal("400.00")
    assert totais[ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE] == Decimal("300.00")


def test_soma_dos_grupos_bate_com_totais_por_tipo_no_primeiro_centavo(cenario_classificado):
    """O critério 4, na redação corrigida depois do BL-486: a IDENTIDADE
    `Σ(grupos do tipo) + residuo_por_tipo[tipo] == totais_por_tipo[tipo]`
    — nunca por `startswith` (BL-490): a soma "do lado do Ativo" usa o
    mapa DERIVADO `TIPO_DA_CLASSIFICACAO_PATRIMONIAL`. Com cobertura TOTAL
    (todo o Ativo e todo o Passivo classificados, no nó de GRUPO — nunca
    em folhas irmãs), o resíduo é EXATAMENTE zero — controle positivo."""
    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )
    totais_classificacao = saldos["totais_por_classificacao"]
    totais_tipo = saldos["totais_por_tipo"]
    residuo = saldos["residuo_por_tipo"]

    soma_ativo = sum(
        (
            valor
            for classificacao, valor in totais_classificacao.items()
            if TIPO_DA_CLASSIFICACAO_PATRIMONIAL[classificacao] == TipoConta.ATIVO
        ),
        Decimal("0"),
    )
    soma_passivo = sum(
        (
            valor
            for classificacao, valor in totais_classificacao.items()
            if TIPO_DA_CLASSIFICACAO_PATRIMONIAL[classificacao] == TipoConta.PASSIVO
        ),
        Decimal("0"),
    )
    assert soma_ativo == totais_tipo[TipoConta.ATIVO] == Decimal("1950.00")
    assert soma_passivo == totais_tipo[TipoConta.PASSIVO] == Decimal("700.00")
    # A IDENTIDADE do critério 4, testada diretamente pela chave que a
    # camada devolve — não recalculada aqui por fora.
    assert soma_ativo + residuo[TipoConta.ATIVO] == totais_tipo[TipoConta.ATIVO]
    assert soma_passivo + residuo[TipoConta.PASSIVO] == totais_tipo[TipoConta.PASSIVO]
    # Controle positivo: cobertura total, no nó de GRUPO — resíduo
    # EXATAMENTE zero. Sem este teste, um mutante que sempre devolvesse
    # resíduo diferente de zero passaria despercebido.
    assert residuo[TipoConta.ATIVO] == Decimal("0.00")
    assert residuo[TipoConta.PASSIVO] == Decimal("0.00")
    # E a equação continua fechando — a classificação NUNCA move dinheiro.
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")


def test_totais_por_grupo_soma_os_quatro_subgrupos_do_ativo_nao_circulante():
    """BL-490: `totais_por_grupo` some os QUATRO subgrupos do Ativo Não
    Circulante (realizável a longo prazo, investimentos, imobilizado,
    intangível) num único total — o subtotal que a Lei 6.404/76 art. 178
    manda IMPRIMIR no Balanço. Cenário com TRÊS subgrupos diferentes
    movimentados, para provar que não é só o caso de um subgrupo só."""
    empresa = _empresa("DL-033 Totais Por Grupo")
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    realizavel = _conta(
        empresa,
        codigo="1.1",
        nome="Realizável a Longo Prazo",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO,
    )
    investimentos = _conta(
        empresa,
        codigo="1.2",
        nome="Investimentos",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS,
    )
    intangivel = _conta(
        empresa,
        codigo="1.3",
        nome="Intangível",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL,
    )
    _lancar(empresa, date(2026, 1, 2), "Realizável LP", realizavel, capital, "100.00")
    _lancar(empresa, date(2026, 1, 3), "Investimentos", investimentos, capital, "200.00")
    _lancar(empresa, date(2026, 1, 4), "Intangível", intangivel, capital, "300.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert set(saldos["totais_por_grupo"].keys()) == set(GrupoDaLei.values)
    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE] == Decimal("600.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_CIRCULANTE] == Decimal("0")
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("0.00")


def test_mapa_grupo_da_lei_cobre_exatamente_os_valores_do_enum_classificacao():
    """DE-056/BL-490: teste DERIVADO — se `ClassificacaoPatrimonial` ganhar
    um valor novo sem entrada em `GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL`,
    este teste reprova nomeando o valor esquecido."""
    assert set(GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL.keys()) == set(
        ClassificacaoPatrimonial.values
    )
    assert set(GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL.values()) == set(GrupoDaLei.values)


# ---------------------------------------------------------------------------
# BL-486 (BLOQUEADOR) e BL-487 (ALTA) — a identidade do resíduo reprova os
# dois casos que a auditoria mediu, nenhum dos quais as três listas
# declaradas conseguiam nomear.
# ---------------------------------------------------------------------------


def test_bl486_contas_irmas_com_naturezas_diferentes_produzem_residuo_nao_zero():
    """Reprodução EXATA da sonda do auditor: "Clientes" (devedora,
    1.220,00) e "(-) PDD" (credora, retificadora, 50,00), IRMÃS (nenhuma
    ancestral da outra), ambas classificadas `ativo_circulante`
    DIRETAMENTE. `totais_por_classificacao['ativo_circulante']` fica
    ERRADO (1.270,00 — soma os dois valores, cada um já assinado pela
    PRÓPRIA natureza, em vez de aplicar uma natureza sobre o bruto
    combinado), mas o RESÍDUO nomeia a diferença: não fecha mais em
    silêncio."""
    empresa = _empresa("DL-033 BL-486")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    clientes = _conta(
        empresa,
        codigo="1.1",
        nome="Clientes",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    pdd = _conta(
        empresa,
        codigo="1.2",
        nome="(-) PDD",
        tipo=TipoConta.ATIVO,
        natureza=C,  # retificadora
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    _lancar(empresa, date(2026, 1, 2), "Capitalização", clientes, capital, "1220.00")
    _lancar(empresa, date(2026, 1, 5), "Provisão", capital, pdd, "50.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    # O totais_por_tipo (via a RAIZ, correto) é 1.170,00 — a mesma conta
    # que o implementador fez à mão para justificar o desenho.
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("1170.00")
    # A soma por classificação fica ERRADA (1.270,00) — não corrigimos
    # isso, DECLARAMOS via resíduo.
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        Decimal("1270.00")
    )
    # O resíduo nomeia o excesso de 100,00 (o DOBRO da retificadora),
    # negativo porque a soma dos grupos ficou MAIOR que o total do tipo.
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("-100.00")
    # A identidade continua valendo, por construção.
    soma_ativo = saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE]
    assert soma_ativo + saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("1170.00")
    # E a equação do Balancete, que não usa classificação nenhuma,
    # continua correta e fechando — o dinheiro nunca se moveu de verdade.
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")


def test_bl487_no_intermediario_desclassificado_com_movimento_produz_residuo_nao_zero():
    """Reprodução EXATA da sonda do auditor: desdobramento de conta já em
    uso. "1.1 Caixa" nasce com 500,00 de movimento PRÓPRIO; depois o
    contador cria "1.1.01" (classificada `ativo_circulante`) como filha —
    "1.1" deixa de ser folha (`analitica=False`), mas continua SEM
    classificação própria nem ancestral classificado. A DE-022 registra
    que esse desdobramento é ROTINA normal, não erro — e mesmo assim os
    500,00 de "1.1" ficavam invisíveis para `contas_sem_classificacao_
    patrimonial` (que só olhava folhas). O resíduo os nomeia de qualquer
    jeito."""
    empresa = _empresa("DL-033 BL-487")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    caixa = _conta(
        empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D, pai=raiz_ativo
    )
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    _lancar(empresa, date(2026, 1, 2), "Capitalização inicial", caixa, capital, "500.00")

    # Desdobramento: "1.1" ganha uma FILHA classificada — "1.1" mesma
    # continua SEM classificação e SEM ser folha.
    caixa_classificado = _conta(
        empresa,
        codigo="1.1.01",
        nome="Caixa — Operacional",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=caixa,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    _lancar(
        empresa,
        date(2026, 1, 10),
        "Novo movimento já no desdobramento",
        caixa_classificado,
        capital,
        "1000.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("1500.00")
    # Só os 1.000,00 de "1.1.01" entram na soma por classificação — os
    # 500,00 de "1.1" (não-folha, sem classificação própria) somem dali.
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        Decimal("1000.00")
    )
    # O resíduo nomeia os 500,00 perdidos.
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("500.00")


def test_cenario_totalmente_classificado_nao_tem_conta_aninhada_nem_sem_classificacao(
    cenario_classificado,
):
    """Controle positivo do critério 5 — SEM ele, um mutante que sempre
    devolvesse listas vazias passaria despercebido."""
    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )
    assert saldos["contas_com_classificacao_aninhada"] == []
    assert saldos["contas_sem_classificacao_patrimonial"] == []
    assert saldos["contas_com_classificacao_desconhecida"] == []
    assert saldos["residuo_por_tipo"] == {
        TipoConta.ATIVO: Decimal("0"),
        TipoConta.PASSIVO: Decimal("0"),
    }


def test_classificacao_gravada_fora_do_enum_e_nomeada_nunca_derruba():
    """Mesma defesa do achado A1/BL-476 (`contas_com_tipo_desconhecido`),
    agora para `classificacao_patrimonial`: um valor gravado fora de
    `ClassificacaoPatrimonial` (só alcançável por escrita direta no
    ORM/SQL — a guarda de consistência do `Conta.clean()` nunca deixa
    passar pelo caminho validado) não pode estourar `KeyError` nem criar
    chave nova dentro de `totais_por_classificacao`."""
    empresa = _empresa("DL-033 Classificação Desconhecida")
    conta = _conta(empresa, codigo="1", nome="Conta corrompida", tipo=TipoConta.ATIVO, natureza=D)
    Conta.objects.filter(pk=conta.pk).update(classificacao_patrimonial="grupo-que-nao-existe")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert set(saldos["totais_por_classificacao"].keys()) == set(ClassificacaoPatrimonial.values)
    desconhecidas = {
        linha["conta"]: linha for linha in saldos["contas_com_classificacao_desconhecida"]
    }
    assert "1" in desconhecidas, saldos["contas_com_classificacao_desconhecida"]
    assert desconhecidas["1"]["classificacao_patrimonial"] == "grupo-que-nao-existe"
    # E não entra, silenciosamente, em nenhum grupo real.
    assert sum(saldos["totais_por_classificacao"].values(), Decimal("0")) == Decimal("0")


# ---------------------------------------------------------------------------
# Critério 5 — conta sem classificação é DECLARADA, nunca presumida
# ---------------------------------------------------------------------------


def test_folha_de_ativo_sem_classificacao_propria_nem_ancestral_e_declarada():
    """Reproduz o caso central do critério 5: uma folha de tipo ATIVO cujo
    ramo INTEIRO (do topo até ela) nunca declarou circulante nem não
    circulante — nem ela, nem nenhum ancestral. A camada NUNCA infere pelo
    nome ("Estoque" não vira "circulante" sozinho, é a classe de erro do
    BL-475/DL-032) — apenas NOMEIA a conta na lista."""
    empresa = _empresa("DL-033 Sem Classificação")
    raiz_ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    estoque = _conta(
        empresa, codigo="1.1", nome="Estoque", tipo=TipoConta.ATIVO, natureza=D, pai=raiz_ativo
    )
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    _lancar(empresa, date(2026, 1, 2), "Capitalização em estoque", estoque, capital, "700.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    sem_classificacao = {
        linha["conta"]: linha for linha in saldos["contas_sem_classificacao_patrimonial"]
    }
    assert "1.1" in sem_classificacao, saldos["contas_sem_classificacao_patrimonial"]
    assert sem_classificacao["1.1"]["tipo"] == TipoConta.ATIVO
    # A raiz "1" NÃO entra na lista: não é analítica (tem descendente) — só
    # a FOLHA, onde o dinheiro de fato está, precisa da declaração.
    assert "1" not in sem_classificacao
    # O dinheiro continua no Ativo — a ausência de classificação NUNCA
    # tira a conta do total por TIPO, só do total por CLASSIFICAÇÃO.
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("700.00")
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == Decimal(
        "0"
    )


def test_bl493_conta_inativa_com_saldo_continua_declarada_sem_saldo_sai():
    """BL-493 (achado A8, decisão do arquiteto-senior): "a régua é o
    saldo, não a marca de `ativo`" — mesmo princípio do BL-482/A9 da
    DL-032 (conta desativada com saldo residual continua somando no
    total). Aqui, o espelho: conta INATIVA e COM saldo continua na lista
    de pendências (ela aparece no Balanço, precisa de grupo); conta
    INATIVA e SEM saldo sai (classificá-la não muda nada). Duas contas
    lado a lado, mesma árvore, uma só diferindo da outra por ter ou não
    saldo."""
    empresa = _empresa("DL-033 BL-493")
    raiz_ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    inativa_com_saldo = _conta(
        empresa,
        codigo="1.1",
        nome="Conta Inativa Com Saldo",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
    )
    inativa_sem_saldo = _conta(
        empresa,
        codigo="1.2",
        nome="Conta Inativa Sem Saldo",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
    )
    inativa_com_saldo.ativo = False
    inativa_com_saldo.save(update_fields=["ativo"])
    inativa_sem_saldo.ativo = False
    inativa_sem_saldo.save(update_fields=["ativo"])
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    _lancar(empresa, date(2026, 1, 2), "Saldo residual", inativa_com_saldo, capital, "150.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    sem_classificacao = {linha["conta"] for linha in saldos["contas_sem_classificacao_patrimonial"]}
    assert "1.1" in sem_classificacao, saldos["contas_sem_classificacao_patrimonial"]
    assert "1.2" not in sem_classificacao, saldos["contas_sem_classificacao_patrimonial"]


def test_bl493_conta_ativa_sem_saldo_tambem_nao_e_declarada():
    """Controle cruzado: a régua é o SALDO, não a marca de `ativo` — uma
    conta ATIVA (não desativada) recém-cadastrada, sem nenhum movimento,
    também não entra na lista. Classificá-la hoje não mudaria nada no
    Balanço; o contador pode classificá-la quando ela ganhar movimento."""
    empresa = _empresa("DL-033 BL-493 Ativa Sem Saldo")
    raiz_ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    _conta(
        empresa,
        codigo="1.1",
        nome="Conta Nova Sem Movimento",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    sem_classificacao = {linha["conta"] for linha in saldos["contas_sem_classificacao_patrimonial"]}
    assert "1.1" not in sem_classificacao, saldos["contas_sem_classificacao_patrimonial"]


def test_conta_de_patrimonio_liquido_nunca_entra_na_lista_de_sem_classificacao():
    """Controle: PL não faz parte da separação circulante/não circulante
    (RC-106) — mesmo sem `classificacao_patrimonial`, uma conta de PL
    nunca é declarada como "faltando classificação"."""
    empresa = _empresa("DL-033 PL Sem Classificação")
    raiz_pl = _conta(
        empresa,
        codigo="3",
        nome="PL",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        aceita_lancamento=False,
    )
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    raiz_ativo = _conta(empresa, codigo="1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D)
    _lancar(empresa, date(2026, 1, 2), "Capitalização", raiz_ativo, capital, "100.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    contas_declaradas = {linha["conta"] for linha in saldos["contas_sem_classificacao_patrimonial"]}
    assert "3.1" not in contas_declaradas
    assert "3" not in contas_declaradas


def test_classificacao_aninhada_e_declarada_nunca_soma_duas_vezes():
    """Duas contas da MESMA árvore declarando o MESMO grupo: a raiz "1"
    (tipo Ativo) recebe `ATIVO_CIRCULANTE` E a sua filha "1.1" TAMBÉM —
    dado inconsistente. A camada NUNCA soma a filha de novo (o saldo dela
    já está dentro do `saldo_final` CONSOLIDADO da raiz, regra única de
    saldo — DE-020): soma só uma vez, na conta MAIS ALTA da árvore
    (critério de "topo classificado"), e DECLARA a filha aninhada."""
    empresa = _empresa("DL-033 Aninhada")
    raiz = _conta(
        empresa,
        codigo="1",
        nome="ATIVO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
        aceita_lancamento=False,
    )
    filha = _conta(
        empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    raiz_pl = _conta(empresa, codigo="3", nome="PL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C)
    capital = _conta(
        empresa,
        codigo="3.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    _lancar(empresa, date(2026, 1, 2), "Capitalização", filha, capital, "900.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    aninhadas = {linha["conta"] for linha in saldos["contas_com_classificacao_aninhada"]}
    assert "1.1" in aninhadas, saldos["contas_com_classificacao_aninhada"]
    assert "1" not in aninhadas  # "1" é o TOPO classificado — não está aninhada
    # Soma UMA vez só (na raiz, que já consolida a filha) — não 1.800,00.
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == Decimal(
        "900.00"
    )
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("900.00")
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# Critério 7 — isolamento entre empresas não regride
# ---------------------------------------------------------------------------


def test_isolamento_totais_por_classificacao_entre_empresas(cenario_classificado):
    """A empresa vizinha, com um plano de contas classificado DIFERENTE,
    não vaza para os totais desta empresa."""
    vizinha = _empresa("DL-033 Vizinha")
    contas_vizinha = _arvore_totalmente_classificada(vizinha)
    raiz_pl_vizinha = Conta.objects.get(empresa=vizinha, codigo="3")
    _lancar(
        vizinha,
        date(2026, 1, 15),
        "Movimento da vizinha",
        contas_vizinha["caixa"],
        contas_vizinha["capital"],
        "50000.00",
    )

    saldos = apurar_saldos(
        empresa=cenario_classificado["empresa"], data_base=cenario_classificado["data_base"]
    )

    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == Decimal(
        "1550.00"
    )
    assert raiz_pl_vizinha.empresa_id == vizinha.id  # a vizinha existe e é distinta
