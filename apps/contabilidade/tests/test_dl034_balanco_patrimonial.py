"""DL-034 — a frente de SERVIDOR da tela do Balanço Patrimonial.

Cobre o critério 1 do plano
(`docs/planos/DL-034-a-tela-do-balanco.md`), na redação corrigida pela
RESSALVA R1 da rodada 2 de auditoria da DL-033 (DE-068) e pela DE-067:

1. **BL-496 (correção de FUNDO)** — `apurar_saldos` soma um nó TOPO
   classificado normalizando o sinal pela natureza NATURAL do TIPO
   (`NATUREZA_NATURAL_DO_TIPO`, models.py), não pela natureza CADASTRADA da
   própria conta. Prova por dois cenários do relatório de auditoria: **V1d**
   (dois defeitos calibrados para se anularem — retificadora entre irmãs
   MAIS nó intermediário desclassificado com movimento próprio) exige
   RECUSA; e um controle positivo, com os mesmos valores em R$ que a
   auditoria usou para "o número certo" (`ativo_circulante == 2.750,00`,
   `ativo_nao_circulante == 8.500,00`), exige EMISSÃO liberada.
2. **`avaliar_emissao_do_balanco`** — a função do SERVIDOR que decide "pode
   emitir?", CONJUNÇÃO de TRÊS condições de VETO, DERIVADA (nunca um `if`
   por condição escrito à mão).
3. **`identificacao_da_demonstracao`** — os três campos do item 51 (b, d,
   e) que não existiam, declarados como constante, nunca deduzidos.
4. **DE-067** — `apurar_balanco_patrimonial` lê sob snapshot
   (`REPEATABLE READ`); prova de CORRIDA real (duas conexões), não só
   afirmada, com o par "antes/depois" (sem e com o wrapper).
5. **Rodada de CORREÇÃO da auditoria da DL-034 (rodada 1, REPROVADA por
   A1)** — BL-499 (a guarda da condição 3 tratava TODA raiz como irmã),
   BL-500/DE-070 (a condição 3 deixa de VETAR, vira aviso declarado em
   `listas_informativas`, SEPARADA de `listas_pendentes` — correção de
   contrato pedida pelo arquiteto-senior) e BL-502/BL-492 (as duas tuplas
   `_LISTAS_QUE_IMPEDEM_A_EMISSAO`/`_LISTAS_QUE_SO_AVISAM` PROVADAS uma
   partição exata do inventário real de `apurar_saldos`, chaves
   congeladas).

Dados 100% sintéticos, criados nos próprios testes.
"""

import itertools
import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection, transaction

from apps.contabilidade import services as contabilidade_services
from apps.contabilidade.models import (
    ClassificacaoPatrimonial,
    Conta,
    GrupoDaLei,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    apurar_balanco_patrimonial,
    apurar_saldos,
    avaliar_emissao_do_balanco,
    criar_lancamento,
    identificacao_da_demonstracao,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA

_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _empresa(nome="Empresa DL-034"):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=_cnpj_sintetico())
    return Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=_cnpj_sintetico()
    )


def _conta(empresa, *, codigo, nome, tipo, natureza, pai=None, classificacao=None):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        classificacao_patrimonial=classificacao,
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


# ---------------------------------------------------------------------------
# BL-496 / critério 1 — V1d (recusa) e controle positivo (números certos)
# ---------------------------------------------------------------------------


def test_v1d_dois_defeitos_calibrados_para_se_anular_e_recusado():
    """Reprodução do cenário **V1d** da RESSALVA R1 (rodada 2 de auditoria
    da DL-033): retificadora entre IRMÃS topo-classificadas ("Clientes"
    3.000,00 D / "(-) PDD" 250,00 C, ambas `ativo_circulante`) MAIS um nó
    intermediário "IMOBILIZADO" desclassificado com movimento PRÓPRIO de
    500,00, cujo ÚNICO filho classificado ("Veículos", 8.000,00) cobre só
    parte da subárvore.

    ⚠️ **O que a correção do BL-496 muda aqui, medido e não afirmado:**
    ANTES da correção, os dois defeitos se ANULAVAM na soma agregada —
    resíduo `0,00`, cinco listas vazias, equação fechando, com o Balanço
    errado em R$ 500,00 em dois grupos (o achado da rodada 2). DEPOIS da
    correção (b), o lado "Clientes/PDD" fica CERTO (2.750,00 em vez de
    3.250,00) — e isso QUEBRA a compensação exata: o lado "Imobilizado"
    continua com a MESMA falta de cobertura (8.000,00, sem os 500,00 do nó
    "IMOBILIZADO"), então o resíduo deixa de ser zero e passa a nomear
    exatamente os 500,00 que a correção de sinal NÃO tinha como fechar (ela
    corrige SINAL, não COBERTURA). As duas guardas ESTRUTURAIS (condições 3
    e 4) TAMBÉM disparam, de forma independente — recusa em TRIPLICATA.
    """
    empresa = _empresa("DL-034 V1d")
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
    imobilizado = _conta(
        empresa, codigo="1.3", nome="IMOBILIZADO", tipo=TipoConta.ATIVO, natureza=D, pai=raiz_ativo
    )
    veiculos = _conta(
        empresa,
        codigo="1.3.1",
        nome="Veículos",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=imobilizado,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
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
    _lancar(empresa, date(2026, 1, 2), "Capitalização — Clientes", clientes, capital, "3000.00")
    _lancar(empresa, date(2026, 1, 3), "Provisão — PDD", capital, pdd, "250.00")
    # Movimento PRÓPRIO do nó "IMOBILIZADO", desclassificado — a topologia
    # do BL-487, reaproveitada aqui.
    _lancar(
        empresa,
        date(2026, 1, 4),
        "Movimento próprio do IMOBILIZADO",
        imobilizado,
        capital,
        "500.00",
    )
    _lancar(empresa, date(2026, 1, 5), "Capitalização — Veículos", veiculos, capital, "8000.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    # Total por TIPO (via a raiz, nunca afetado por classificação) — o
    # mesmo total que a auditoria mediu: 11.250,00.
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("11250.00")
    # O lado Clientes/PDD já sai CERTO (BL-496).
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        Decimal("2750.00")
    )
    # O lado Imobilizado continua com a MESMA falta de cobertura — (b) é
    # correção de SINAL, não de COBERTURA; os 500,00 do nó "IMOBILIZADO"
    # seguem fora da soma por classificação.
    assert saldos["totais_por_classificacao"][
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO
    ] == Decimal("8000.00")
    # A compensação exata da rodada 2 QUEBROU: o resíduo agora nomeia os
    # 500,00 que a correção de sinal não tinha como cobrir.
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("500.00")

    # As duas guardas ESTRUTURAIS disparam, cada uma de forma
    # independente do resíduo.
    irmas = {
        linha["conta"]
        for linha in saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"]
    }
    assert irmas == {"1.1", "1.2"}
    nao_folha = {
        linha["conta"]
        for linha in saldos["contas_nao_folha_sem_classificacao_com_movimento_proprio"]
    }
    assert nao_folha == {"1.3"}

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao["pode_emitir"] is False
    # ⚠️ **A PROVA NOMINAL de QUAL condição recusa (rodada de correção da
    # DL-034, critério 5) — o CONTRATO separa as duas classes: desde a
    # DE-070, `listas_pendentes` só contém o que IMPEDE, e a lista de
    # irmãs divergentes (condição 3) vai para `listas_informativas`, que
    # NUNCA decide `pode_emitir` (prova isolada complementar em
    # `test_de070_condicao_3_sozinha_nao_veta_a_emissao`, abaixo). A
    # recusa AQUI vem só do RESÍDUO (condição 1) e da condição 4
    # (cobertura) — as duas asserções seguintes nomeiam as duas causas
    # explicitamente, e a terceira prova que a condição 3 NÃO está entre
    # elas (mesmo aparecendo, declarada, em `listas_informativas`).
    assert emissao["residuo_pendente"] == {TipoConta.ATIVO: Decimal("500.00")}, (
        "causa 1 — resíduo pendente"
    )
    assert (
        "contas_nao_folha_sem_classificacao_com_movimento_proprio" in emissao["listas_pendentes"]
    ), "causa 2 — condição 4 (cobertura)"
    assert set(emissao["listas_pendentes"]) == {
        "contas_nao_folha_sem_classificacao_com_movimento_proprio",
    }
    # A condição 3 NÃO é causa — está em `listas_informativas`, separada.
    assert set(emissao["listas_informativas"]) == {
        "contas_topo_classificadas_com_natureza_divergente_entre_irmas",
    }


def test_bl496_numeros_certos_quando_totalmente_classificado():
    """Controle positivo com os MESMOS valores em R$ que a RESSALVA R1 usa
    para "o número certo" (`ativo_circulante == 2.750,00`,
    `ativo_nao_circulante == 8.500,00`) — mas SEM o defeito de cobertura do
    V1d: o nó "IMOBILIZADO" recebe classificação PRÓPRIA (em vez de deixar
    só o filho classificado), então o movimento próprio dele de 500,00
    fica DENTRO do consolidado do grupo, como já garante a regra única de
    saldo (DE-020) — não depende da correção do BL-496 para isto, que já
    era comportamento correto e testado. As retificadoras aqui são
    ANINHADAS (dentro do grupo, no molde do RC-104), não entre IRMÃS topo
    classificadas — por isso a guarda ESTRUTURAL da condição 3 não
    dispara, e o Balanço FECHA."""
    empresa = _empresa("DL-034 Números Certos")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    ativo_circulante = _conta(
        empresa,
        codigo="1.1",
        nome="ATIVO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    clientes = _conta(
        empresa,
        codigo="1.1.1",
        nome="Clientes",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=ativo_circulante,
    )
    pdd = _conta(
        empresa,
        codigo="1.1.2",
        nome="(-) PDD",
        tipo=TipoConta.ATIVO,
        natureza=C,
        pai=ativo_circulante,
    )
    imobilizado = _conta(
        empresa,
        codigo="1.2",
        nome="IMOBILIZADO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
    )
    veiculos = _conta(
        empresa, codigo="1.2.1", nome="Veículos", tipo=TipoConta.ATIVO, natureza=D, pai=imobilizado
    )
    depreciacao = _conta(
        empresa,
        codigo="1.2.2",
        nome="(-) Depreciação Acumulada",
        tipo=TipoConta.ATIVO,
        natureza=C,
        pai=imobilizado,
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
    _lancar(empresa, date(2026, 1, 2), "Capitalização — Clientes", clientes, capital, "3000.00")
    _lancar(empresa, date(2026, 1, 3), "Provisão — PDD", capital, pdd, "250.00")
    _lancar(empresa, date(2026, 1, 4), "Capitalização — Veículos", veiculos, capital, "9000.00")
    _lancar(empresa, date(2026, 1, 5), "Depreciação do exercício", capital, depreciacao, "500.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("11250.00")
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        Decimal("2750.00")
    )
    assert saldos["totais_por_classificacao"][
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO
    ] == Decimal("8500.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_CIRCULANTE] == Decimal("2750.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE] == Decimal("8500.00")
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("0.00")
    assert saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"] == []
    assert saldos["contas_nao_folha_sem_classificacao_com_movimento_proprio"] == []

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao == {
        "pode_emitir": True,
        "residuo_pendente": {},
        "listas_pendentes": {},
        "listas_informativas": {},
    }


def test_v1c_cinco_classificacoes_retificadoras_e_centavos_quebrados():
    """Reprodução do cenário **V1c** (controle positivo mais duro da
    rodada 2 de auditoria): as CINCO classificações do Ativo (circulante +
    os quatro subgrupos do não circulante), retificadora dentro do
    circulante E dentro do imobilizado, passivo nos dois grupos, e
    centavos que não fecham redondo — inclusive `0,01` e `12,34`. Exige
    resíduo `0,00` nos DOIS tipos e emissão liberada."""
    empresa = _empresa("DL-034 V1c")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    circulante = _conta(
        empresa,
        codigo="1.1",
        nome="ATIVO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    clientes = _conta(
        empresa, codigo="1.1.1", nome="Clientes", tipo=TipoConta.ATIVO, natureza=D, pai=circulante
    )
    pdd = _conta(
        empresa, codigo="1.1.2", nome="(-) PDD", tipo=TipoConta.ATIVO, natureza=C, pai=circulante
    )
    realizavel = _conta(
        empresa,
        codigo="1.2",
        nome="REALIZÁVEL A LONGO PRAZO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO,
    )
    investimentos = _conta(
        empresa,
        codigo="1.3",
        nome="INVESTIMENTOS",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS,
    )
    imobilizado = _conta(
        empresa,
        codigo="1.4",
        nome="IMOBILIZADO",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
    )
    veiculos = _conta(
        empresa, codigo="1.4.1", nome="Veículos", tipo=TipoConta.ATIVO, natureza=D, pai=imobilizado
    )
    depreciacao = _conta(
        empresa,
        codigo="1.4.2",
        nome="(-) Depreciação Acumulada",
        tipo=TipoConta.ATIVO,
        natureza=C,
        pai=imobilizado,
    )
    intangivel = _conta(
        empresa,
        codigo="1.5",
        nome="INTANGÍVEL",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL,
    )

    raiz_passivo = _conta(empresa, codigo="2", nome="PASSIVO", tipo=TipoConta.PASSIVO, natureza=C)
    passivo_circulante = _conta(
        empresa,
        codigo="2.1",
        nome="PASSIVO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=raiz_passivo,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    fornecedores = _conta(
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
    )
    financiamentos = _conta(
        empresa,
        codigo="2.2.1",
        nome="Financiamentos LP",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=passivo_nao_circulante,
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

    data = date(2026, 1, 2)
    _lancar(empresa, data, "Clientes", clientes, capital, "1000.01")
    _lancar(empresa, data, "PDD", capital, pdd, "12.34")
    _lancar(empresa, data, "Realizável LP", realizavel, capital, "300.07")
    _lancar(empresa, data, "Investimentos", investimentos, capital, "200.02")
    _lancar(empresa, data, "Veículos", veiculos, capital, "900.09")
    _lancar(empresa, data, "Depreciação", capital, depreciacao, "45.06")
    _lancar(empresa, data, "Intangível", intangivel, capital, "100.03")
    # Passivo e PL precisam financiar o excedente de Ativo — fecha a
    # equação com Capital absorvendo o resíduo.
    _lancar(empresa, data, "Fornecedores", capital, fornecedores, "321.76")
    _lancar(empresa, data, "Financiamentos LP", capital, financiamentos, "777.07")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    circulante_esperado = Decimal("1000.01") - Decimal("12.34")
    imobilizado_esperado = Decimal("900.09") - Decimal("45.06")
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        circulante_esperado
    )
    assert (
        saldos["totais_por_classificacao"][
            ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO
        ]
        == imobilizado_esperado
    )
    assert saldos["totais_por_classificacao"][
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_REALIZAVEL_A_LONGO_PRAZO
    ] == Decimal("300.07")
    assert saldos["totais_por_classificacao"][
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS
    ] == Decimal("200.02")
    assert saldos["totais_por_classificacao"][
        ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INTANGIVEL
    ] == Decimal("100.03")
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.PASSIVO_CIRCULANTE] == (
        Decimal("321.76")
    )
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE] == (
        Decimal("777.07")
    )
    assert saldos["residuo_por_tipo"] == {
        TipoConta.ATIVO: Decimal("0.00"),
        TipoConta.PASSIVO: Decimal("0.00"),
    }
    assert saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"] == []
    assert saldos["contas_nao_folha_sem_classificacao_com_movimento_proprio"] == []
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao == {
        "pode_emitir": True,
        "residuo_pendente": {},
        "listas_pendentes": {},
        "listas_informativas": {},
    }


# ---------------------------------------------------------------------------
# BL-499/BL-500/BL-502 — rodada de CORREÇÃO da auditoria da DL-034 (rodada
# 1, REPROVADA por A1: agrupar só por pai cruzava raízes de tipos
# diferentes. Três achados, três correções:
#
# - **BL-499 (ALTA)**: `apurar_saldos` agrupava os nós topo-classificados
#   só por `linha["conta_pai"]`; todas as raízes compartilham `None`, então
#   contas de Ativo e Passivo entravam no mesmo grupo e podiam impedir a
#   emissão com mensagem factualmente falsa. Corrigido com a chave
#   `(conta_pai, tipo)`, que separa tipos diferentes. O BL-516 remove a
#   exclusão de raiz: divergência de natureza entre raízes do mesmo tipo
#   continua nomeada como aviso, sem vetar.
# - **BL-500 (DE-070)**: a condição 3 deixa de VETAR a emissão — vira
#   aviso declarado, em `listas_informativas` (correção de CONTRATO
#   pedida pelo arquiteto-senior: `listas_pendentes` só contém o que
#   IMPEDE, nunca uma lista que "pende" sem impedir nada).
# - **BL-502 (+ BL-492)**: `_LISTAS_QUE_IMPEDEM_A_EMISSAO` e
#   `_LISTAS_QUE_SO_AVISAM` PROVADAS uma partição exata do inventário real
#   de `apurar_saldos` (união == inventário, interseção vazia), nunca só
#   escritas à mão — e as chaves de `apurar_saldos` precisam de
#   congelamento.
# ---------------------------------------------------------------------------


def test_bl499_tres_raizes_de_tipos_diferentes_nao_se_cruzam_e_emitem():
    """Reprodução EXATA do achado A1 (auditoria da DL-034, rodada 1) —
    plano mínimo, TRÊS raízes, sem pai nenhum:

        1  ATIVO CIRCULANTE    (devedora)  -> ativo_circulante
        2  PASSIVO CIRCULANTE  (credora)   -> passivo_circulante
        3  CAPITAL SOCIAL      (credora)   -> (PL, sem classificação)

    Plano inteiramente VÁLIDO — `Conta.full_clean()` aceita as três (a
    guarda de `Conta.clean()` só cruza classificação × TIPO, nunca posição
    na árvore). ANTES da correção do BL-499, a guarda da condição 3
    agrupava por `conta_pai` (== `None` para as três, já que são raízes) e
    acusava `['1', '2']` como "irmãs de natureza divergente" — falso: as
    duas não têm ancestral NENHUM, são de TIPOS diferentes (Ativo/Passivo),
    e a natureza oposta entre elas é exatamente a REGRA (Lei 6.404/76).
    Com a chave `(conta_pai, tipo)`, as raízes de Ativo e Passivo ficam em
    grupos separados: a lista sai VAZIA, e o Balanço emite."""
    empresa = _empresa("DL-034 BL-499 Três Raízes")
    ativo_circulante = _conta(
        empresa,
        codigo="1",
        nome="ATIVO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    passivo_circulante = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    capital_social = _conta(
        empresa, codigo="3", nome="CAPITAL SOCIAL", tipo=TipoConta.PATRIMONIO_LIQUIDO, natureza=C
    )
    # Fecha a equação: Ativo (1.500,00) == Passivo (500,00) + PL (1.000,00).
    _lancar(empresa, date(2026, 1, 2), "Capitalização", ativo_circulante, capital_social, "1000.00")
    _lancar(
        empresa, date(2026, 1, 3), "Financiamento", ativo_circulante, passivo_circulante, "500.00"
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.ATIVO_CIRCULANTE] == (
        Decimal("1500.00")
    )
    assert saldos["totais_por_classificacao"][ClassificacaoPatrimonial.PASSIVO_CIRCULANTE] == (
        Decimal("500.00")
    )
    assert saldos["residuo_por_tipo"] == {
        TipoConta.ATIVO: Decimal("0.00"),
        TipoConta.PASSIVO: Decimal("0.00"),
    }
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")
    # A chave por tipo evita cruzar Ativo e Passivo, mesmo com natureza
    # cadastrada divergente entre eles.
    assert saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"] == []

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao == {
        "pode_emitir": True,
        "residuo_pendente": {},
        "listas_pendentes": {},
        "listas_informativas": {},
    }


def test_bl499_cinco_raizes_grupo_com_naturezas_coerentes_emitem():
    """Segundo cenário do achado A1: as raízes SÃO os próprios grupos —
    `1 AC`, `2 ANC`, `3 PC`, `4 PNC`, `5 PL`. ANTES da correção do BL-499,
    a lista acusava QUATRO contas (`['1','2','3','4']`); com a chave
    `(conta_pai, tipo)`, grupos de tipos diferentes não se cruzam e as
    naturezas dentro de cada tipo são coerentes, então a lista fica vazia."""
    empresa = _empresa("DL-034 BL-499 Cinco Raízes-Grupo")
    ativo_circulante = _conta(
        empresa,
        codigo="1",
        nome="ATIVO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    ativo_nao_circulante = _conta(
        empresa,
        codigo="2",
        nome="ATIVO NÃO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_INVESTIMENTOS,
    )
    passivo_circulante = _conta(
        empresa,
        codigo="3",
        nome="PASSIVO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao=ClassificacaoPatrimonial.PASSIVO_CIRCULANTE,
    )
    passivo_nao_circulante = _conta(
        empresa,
        codigo="4",
        nome="PASSIVO NÃO CIRCULANTE",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        classificacao=ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE,
    )
    pl = _conta(
        empresa,
        codigo="5",
        nome="PATRIMÔNIO LÍQUIDO",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )

    # `ativo_circulante` (1200,00) só recebe a capitalização; `ativo_nao_
    # circulante` (2) só recebe os DOIS financiamentos abaixo — 300,00 +
    # 100,00 = 400,00, nunca 700,00 (não há uma terceira entrada nele).
    _lancar(empresa, date(2026, 1, 2), "Capitalização — AC", ativo_circulante, pl, "1200.00")
    _lancar(
        empresa,
        date(2026, 1, 3),
        "Financiamento curto prazo",
        ativo_nao_circulante,
        passivo_circulante,
        "300.00",
    )
    _lancar(
        empresa,
        date(2026, 1, 4),
        "Financiamento longo prazo",
        ativo_nao_circulante,
        passivo_nao_circulante,
        "100.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_CIRCULANTE] == Decimal("1200.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE] == Decimal("400.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.PASSIVO_CIRCULANTE] == Decimal("300.00")
    assert saldos["totais_por_grupo"][GrupoDaLei.PASSIVO_NAO_CIRCULANTE] == Decimal("100.00")
    assert saldos["residuo_por_tipo"] == {
        TipoConta.ATIVO: Decimal("0.00"),
        TipoConta.PASSIVO: Decimal("0.00"),
    }
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")
    assert saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"] == []

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao == {
        "pode_emitir": True,
        "residuo_pendente": {},
        "listas_pendentes": {},
        "listas_informativas": {},
    }


def test_bl516_duas_raizes_do_mesmo_tipo_com_natureza_divergente_sao_informadas():
    """Cenário L4 do BL-516: duas contas-raiz de Ativo, ambas no mesmo
    grupo patrimonial, com naturezas cadastradas diferentes. A lista
    informativa volta a nomear os códigos `1` e `2`; a chave não inventa
    ancestral para elas e essa condição continua sem vetar a emissão."""
    empresa = _empresa("DL-035 BL-516 Duas Raízes do Ativo")
    clientes = _conta(
        empresa,
        codigo="1",
        nome="Clientes",
        tipo=TipoConta.ATIVO,
        natureza=D,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    pdd = _conta(
        empresa,
        codigo="2",
        nome="(-) PDD",
        tipo=TipoConta.ATIVO,
        natureza=C,
        classificacao=ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
    )
    capital = _conta(
        empresa,
        codigo="3",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
    )
    _lancar(empresa, date(2026, 1, 2), "Clientes", clientes, capital, "1220.00")
    _lancar(empresa, date(2026, 1, 3), "Provisão — PDD", capital, pdd, "50.00")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))
    aviso = saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"]
    assert {linha["conta"] for linha in aviso} == {"1", "2"}

    emissao = avaliar_emissao_do_balanco(saldos)
    assert (
        emissao["listas_informativas"][
            "contas_topo_classificadas_com_natureza_divergente_entre_irmas"
        ]
        == aviso
    )
    assert (
        emissao["listas_pendentes"].get(
            "contas_topo_classificadas_com_natureza_divergente_entre_irmas"
        )
        is None
    )


def test_a2_retificadora_de_grupo_emite_com_totais_por_grupo_certo():
    """Cenário **L4** da auditoria (achado A2): grupo retificador inteiro,
    IRMÃO de fato do grupo bruto (mesmo pai NÃO raiz — "1.2 NÃO
    CIRCULANTE", sem classificação própria):

        1.2   NAO CIRCULANTE                 (sem classificação)
        1.2.3 Imobilizado bruto      D 15.000,00  -> imobilizado
        1.2.9 (-) Depreciação acum.  C  3.000,00  -> imobilizado

    A auditoria mediu que a correção (b) dá o número CERTO também aqui —
    `ativo_nao_circulante == 12.000,00`, conciliando com `totais_por_tipo`
    no primeiro centavo (DE-070). A guarda da condição 3 CONTINUA
    nomeando as duas (são irmãs DE FATO — mesmo pai, que não é raiz), como
    AVISO — e o Balanço emite mesmo assim."""
    empresa = _empresa("DL-034 A2 Retificadora de Grupo")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    nao_circulante = _conta(
        empresa,
        codigo="1.2",
        nome="NAO CIRCULANTE",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=raiz_ativo,
    )
    imobilizado_bruto = _conta(
        empresa,
        codigo="1.2.3",
        nome="Imobilizado bruto",
        tipo=TipoConta.ATIVO,
        natureza=D,
        pai=nao_circulante,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
    )
    depreciacao_acumulada = _conta(
        empresa,
        codigo="1.2.9",
        nome="(-) Depreciação Acumulada",
        tipo=TipoConta.ATIVO,
        natureza=C,
        pai=nao_circulante,
        classificacao=ClassificacaoPatrimonial.ATIVO_NAO_CIRCULANTE_IMOBILIZADO,
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
    _lancar(empresa, date(2026, 1, 2), "Imobilizado bruto", imobilizado_bruto, capital, "15000.00")
    _lancar(
        empresa,
        date(2026, 1, 3),
        "Depreciação acumulada",
        capital,
        depreciacao_acumulada,
        "3000.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE] == Decimal("12000.00")
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("12000.00")
    assert saldos["residuo_por_tipo"][TipoConta.ATIVO] == Decimal("0.00")

    # AVISO, não veto: as duas contas SÃO irmãs de fato (mesmo pai "1.2",
    # que não é raiz) — a guarda continua a nomear.
    irmas = {
        linha["conta"]
        for linha in saldos["contas_topo_classificadas_com_natureza_divergente_entre_irmas"]
    }
    assert irmas == {"1.2.3", "1.2.9"}

    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao["pode_emitir"] is True
    assert emissao["residuo_pendente"] == {}
    # A condição 3 NUNCA impede — mesmo não vazia, fica fora de
    # `listas_pendentes` e aparece SÓ em `listas_informativas`.
    assert emissao["listas_pendentes"] == {}
    assert (
        "contas_topo_classificadas_com_natureza_divergente_entre_irmas"
        in emissao["listas_informativas"]
    )


# ---------------------------------------------------------------------------
# `avaliar_emissao_do_balanco` ISOLADA — prova NOMINAL de qual condição
# VETA e qual só AVISA (critério 5 da tarefa de correção: "o V1d continua
# recusado, e o teste tem de provar POR QUÊ" — resíduo e condição 4, nunca
# mais a condição 3). Função PURA (sem `apurar_saldos`/banco), por isso os
# testes abaixo isolam cada condição sem interferência das outras.
# ---------------------------------------------------------------------------


def _saldos_minimos_para_avaliacao(
    *,
    residuo_por_tipo=None,
    contas_topo_classificadas_com_natureza_divergente_entre_irmas=None,
    contas_nao_folha_sem_classificacao_com_movimento_proprio=None,
):
    """Monta o `saldos` MÍNIMO que `avaliar_emissao_do_balanco` lê — só as
    oito chaves que a função usa, sem passar por `apurar_saldos` nem
    banco nenhum. Todas as listas nascem vazias; o chamador só informa o
    que quer NÃO vazio, para isolar qual condição está sendo exercitada."""
    return {
        "residuo_por_tipo": residuo_por_tipo or {},
        "contas_com_tipo_desconhecido": [],
        "contas_com_tipo_divergente_da_raiz": [],
        "contas_com_classificacao_aninhada": [],
        "contas_com_classificacao_desconhecida": [],
        "contas_sem_classificacao_patrimonial": [],
        "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
            contas_topo_classificadas_com_natureza_divergente_entre_irmas or []
        ),
        "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
            contas_nao_folha_sem_classificacao_com_movimento_proprio or []
        ),
    }


_LISTA_INFORMATIVA_DE_CONTRATO_BL515 = (
    "contas_topo_classificadas_com_natureza_divergente_entre_irmas"
)


def test_bl515_a_tupla_de_veto_preserva_as_travas_revisadas():
    """A parametrização abaixo acompanha a tupla atual, então remover um
    item também removeria seu caso de teste. Este contrato independente
    deriva as travas do inventário local de `saldos` menos a única lista
    informativa confirmada, e acusa uma remoção de lado pelo nome. Ele
    protege a presença do cenário; não substitui a prova comportamental
    parametrizada. Nomes novos continuam ganhando cenário pela tupla."""
    nomes_de_listas = {
        nome for nome in _saldos_minimos_para_avaliacao() if nome.startswith("contas_")
    }
    esperadas = nomes_de_listas - {_LISTA_INFORMATIVA_DE_CONTRATO_BL515}
    atuais = set(contabilidade_services._LISTAS_QUE_IMPEDEM_A_EMISSAO)
    informativas = tuple(contabilidade_services._LISTAS_QUE_SO_AVISAM)
    assert informativas == (_LISTA_INFORMATIVA_DE_CONTRATO_BL515,), (
        "BL-515: lista(s) movida(s) para avisos: "
        f"{sorted(set(informativas) - {_LISTA_INFORMATIVA_DE_CONTRATO_BL515})}"
    )
    assert atuais == esperadas, (
        "BL-515: a tupla de veto divergiu do inventário esperado; "
        f"retiradas: {sorted(esperadas - atuais)}; adicionadas: {sorted(atuais - esperadas)}"
    )


@pytest.mark.parametrize(
    "lista_que_veta",
    contabilidade_services._LISTAS_QUE_IMPEDEM_A_EMISSAO,
)
def test_bl515_cada_lista_que_veta_sozinha_continua_impedindo(lista_que_veta):
    """DE-071/BL-515: cada trava da tupla, isolada das demais, recusa a
    emissão com resíduo zero. Os IDs de pytest vêm do próprio nome da
    lista, então a mutação de uma trava acusa qual delas deixou de vetar."""
    saldos = _saldos_minimos_para_avaliacao()
    saldos[lista_que_veta] = [{"marcador": lista_que_veta}]
    assert saldos["residuo_por_tipo"] == {}
    assert (
        sum(bool(saldos[nome]) for nome in contabilidade_services._LISTAS_QUE_IMPEDEM_A_EMISSAO)
        == 1
    )

    emissao = avaliar_emissao_do_balanco(saldos)

    assert emissao["pode_emitir"] is False, (
        f"{lista_que_veta} deixou de impedir a emissão quando movida para a tupla de avisos"
    )
    assert emissao["listas_pendentes"] == {lista_que_veta: saldos[lista_que_veta]}
    assert emissao["listas_informativas"] == {}


def test_de070_condicao_3_sozinha_nao_veta_a_emissao():
    """Prova ISOLADA da DE-070: com resíduo zero e a condição 4 vazia, uma
    condição 3 NÃO vazia, SOZINHA, não impede `pode_emitir` — e (correção
    de contrato pedida pelo arquiteto-senior) NÃO aparece mais em
    `listas_pendentes`: vai inteira para `listas_informativas`, que NUNCA
    decide nada. Um nome chamado "pendência" cujo conteúdo não impede é
    que estava errado, não a decisão em si."""
    saldos = _saldos_minimos_para_avaliacao(
        contas_topo_classificadas_com_natureza_divergente_entre_irmas=[
            {
                "conta": "1.1",
                "nome": "Clientes",
                "classificacao_patrimonial": ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
                "natureza": D,
            },
            {
                "conta": "1.2",
                "nome": "(-) PDD",
                "classificacao_patrimonial": ClassificacaoPatrimonial.ATIVO_CIRCULANTE,
                "natureza": C,
            },
        ],
    )
    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao["pode_emitir"] is True
    assert emissao["residuo_pendente"] == {}
    assert emissao["listas_pendentes"] == {}
    assert set(emissao["listas_informativas"]) == {
        "contas_topo_classificadas_com_natureza_divergente_entre_irmas"
    }


def test_de070_condicao_4_sozinha_continua_vetando_a_emissao():
    """Controle POSITIVO da mesma prova: a condição 4 (cobertura, BL-487)
    CONTINUA vetando sozinha — a DE-070 aposentou só a condição 3. Esta é
    a mutação "M-BL502 sentido 3" do arquiteto: se alguém mover
    `contas_nao_folha_sem_classificacao_com_movimento_proprio` de
    `_LISTAS_QUE_IMPEDEM_A_EMISSAO` para `_LISTAS_QUE_SO_AVISAM`, é ESTE
    teste que reprova (`pode_emitir` viraria `True`)."""
    saldos = _saldos_minimos_para_avaliacao(
        contas_nao_folha_sem_classificacao_com_movimento_proprio=[
            {"conta": "1.3", "nome": "IMOBILIZADO", "tipo": TipoConta.ATIVO},
        ],
    )
    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao["pode_emitir"] is False
    assert emissao["residuo_pendente"] == {}
    assert set(emissao["listas_pendentes"]) == {
        "contas_nao_folha_sem_classificacao_com_movimento_proprio"
    }
    assert emissao["listas_informativas"] == {}


def test_residuo_sozinho_continua_vetando_a_emissao():
    """Controle POSITIVO: o resíduo (condição 1) continua vetando sozinho
    — nunca foi tocado por esta correção."""
    saldos = _saldos_minimos_para_avaliacao(residuo_por_tipo={TipoConta.ATIVO: Decimal("500.00")})
    emissao = avaliar_emissao_do_balanco(saldos)
    assert emissao["pode_emitir"] is False
    assert emissao["residuo_pendente"] == {TipoConta.ATIVO: Decimal("500.00")}
    assert emissao["listas_pendentes"] == {}
    assert emissao["listas_informativas"] == {}


# ---------------------------------------------------------------------------
# BL-502 (+ BL-492) — correção de CONTRATO pedida pelo arquiteto-senior:
# não uma tupla-inventário só, com exceção embutida em `avaliar_emissao_
# do_balanco`, mas DUAS tuplas explícitas e DISJUNTAS
# (`_LISTAS_QUE_IMPEDEM_A_EMISSAO`/`_LISTAS_QUE_SO_AVISAM`), cuja UNIÃO
# prova ser igual ao inventário real de `apurar_saldos` — e as chaves de
# `apurar_saldos` CONGELADAS.
# ---------------------------------------------------------------------------


def test_bl502_as_duas_tuplas_particionam_o_inventario_real_de_apurar_saldos(_cenario_simples):
    """As DUAS tuplas — `_LISTAS_QUE_IMPEDEM_A_EMISSAO` e
    `_LISTAS_QUE_SO_AVISAM` — têm de formar uma PARTIÇÃO exata das chaves
    `contas_*` que `apurar_saldos` de fato devolve: toda lista pertence a
    UMA das duas, NUNCA a nenhuma, NUNCA às duas.

    1. **União == inventário real**: nenhuma lista fica de fora das duas
       classificações (esquecida) — é a mutação M6 do auditor mordendo de
       novo: acrescentar uma oitava lista de pendência a `apurar_saldos`
       SEM inscrevê-la em nenhuma das duas tuplas reprova aqui.
    2. **Interseção vazia**: nenhuma lista é as duas coisas ao mesmo
       tempo — inscrever a mesma lista nova nas DUAS tuplas também
       reprova aqui.

    A partição prova somente o inventário e sua forma; não prova que cada
    item da tupla de veto recusa. O teste independente
    `test_bl515_a_tupla_de_veto_preserva_as_travas_revisadas` acusa a
    remoção de uma lista pelo nome, e
    `test_bl515_cada_lista_que_veta_sozinha_continua_impedindo` prova o
    comportamento de cada item restante, parametrizando a própria tupla."""
    saldos = apurar_saldos(empresa=_cenario_simples["empresa"], data_base=date(2026, 1, 31))
    chaves_contas_em_saldos = {chave for chave in saldos if chave.startswith("contas_")}
    impedem = set(contabilidade_services._LISTAS_QUE_IMPEDEM_A_EMISSAO)
    so_avisam = set(contabilidade_services._LISTAS_QUE_SO_AVISAM)
    assert impedem | so_avisam == chaves_contas_em_saldos, "sentido 1 — união == inventário real"
    assert impedem & so_avisam == set(), "sentido 2 — interseção vazia"


def test_bl492_congelamento_das_chaves_de_apurar_saldos(_cenario_simples):
    """BL-492 (aberto desde a DL-032 — o QUINTO acréscimo de chave em
    cinco etapas): `sorted(saldos)` contra literais ESCRITOS À MÃO neste
    teste. ⚠️ Se este teste reprovar porque `apurar_saldos` ganhou (ou
    perdeu) uma chave, atualizar a lista abaixo é DE PROPÓSITO — não é
    "consertar o teste e seguir": é o sinal de que toda documentação que
    depende da forma de `apurar_saldos` (o CONTRATO entre as duas frentes
    da DL-034, o docstring de `avaliar_emissao_do_balanco`,
    `_LISTAS_QUE_IMPEDEM_A_EMISSAO`/`_LISTAS_QUE_SO_AVISAM`) precisa ser
    revista de propósito."""
    saldos = apurar_saldos(empresa=_cenario_simples["empresa"], data_base=date(2026, 1, 31))
    assert sorted(saldos) == sorted(
        [
            "data_base",
            "contas",
            "totais_por_tipo",
            "contas_com_tipo_desconhecido",
            "contas_com_tipo_divergente_da_raiz",
            "totais_por_classificacao",
            "totais_por_grupo",
            "residuo_por_tipo",
            "contas_com_classificacao_aninhada",
            "contas_com_classificacao_desconhecida",
            "contas_sem_classificacao_patrimonial",
            "contas_topo_classificadas_com_natureza_divergente_entre_irmas",
            "contas_nao_folha_sem_classificacao_com_movimento_proprio",
            "equacao",
        ]
    )


# ---------------------------------------------------------------------------
# `identificacao_da_demonstracao` — item 51, alíneas (b), (d), (e)
# ---------------------------------------------------------------------------


def test_identificacao_da_demonstracao_devolve_os_tres_campos_declarados():
    """Constante, declarada com fonte (RC-95/RC-96/DE-010) — nunca
    deduzida de dado nenhum, e por isso não recebe argumento nenhum."""
    identificacao = identificacao_da_demonstracao()
    assert identificacao == {
        "entidade_individual_ou_grupo": "individual",
        "moeda_de_apresentacao": "Real (R$)",
        "nivel_de_arredondamento": "unidade de real, com centavos",
    }


def test_identificacao_da_demonstracao_e_pura_nao_toca_o_banco(django_assert_num_queries):
    """Não é `apurar_saldos`: não consulta banco nenhum — o mesmo dict,
    sempre, para qualquer empresa/data."""
    with django_assert_num_queries(0):
        identificacao_da_demonstracao()


# ---------------------------------------------------------------------------
# `apurar_balanco_patrimonial` — DE-067, o snapshot
# ---------------------------------------------------------------------------


@pytest.fixture
def _cenario_simples():
    empresa = _empresa("DL-034 Snapshot")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    caixa = _conta(
        empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=D,
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
    _lancar(empresa, date(2026, 1, 2), "Saldo inicial", caixa, capital, "5000.00")
    return {"empresa": empresa, "caixa": caixa, "capital": capital, "raiz_ativo": raiz_ativo}


@pytest.mark.django_db(transaction=True)
def test_apurar_balanco_patrimonial_devolve_os_tres_ingredientes(_cenario_simples):
    """`transaction=True`: o `django_db` PADRÃO do pytest-django já
    embrulha o corpo do teste inteiro num `transaction.atomic()` (para
    poder desfazer no fim) — dentro dele, `connection.in_atomic_block`
    SEMPRE seria `True`, e a guarda de precondição (DE-067) recusaria
    esta chamada mesmo sem nenhum atomic() explícito do teste. `transaction
    =True` desliga esse embrulho automático, para exercitar
    `apurar_balanco_patrimonial` como uma view real (fora de qualquer
    atomic — `ATOMIC_REQUESTS` está desligado, `config/settings.py`) de
    fato faria."""
    resultado = apurar_balanco_patrimonial(
        empresa=_cenario_simples["empresa"], data_base=date(2026, 1, 31)
    )
    assert set(resultado.keys()) == {"saldos", "emissao", "identificacao"}
    assert resultado["saldos"]["equacao"]["diferenca"] == Decimal("0.00")
    assert resultado["emissao"] == {
        "pode_emitir": True,
        "residuo_pendente": {},
        "listas_pendentes": {},
        "listas_informativas": {},
    }
    assert resultado["identificacao"] == identificacao_da_demonstracao()


def test_apurar_balanco_patrimonial_degrada_sem_quebrar_dentro_de_outro_atomic(_cenario_simples):
    """`SET TRANSACTION ISOLATION LEVEL` só é válido como primeira
    instrução depois do `BEGIN` — chamar de dentro de outro
    `transaction.atomic()` já aberto (o caso do cliente de teste do
    Django, que embrulha a requisição inteira; e de `pytestmark =
    pytest.mark.django_db` PADRÃO, sem `transaction=True`, deste próprio
    arquivo) faria o comando levantar erro do PostgreSQL. A função PULA o
    comando nesse caso, em vez de derrubar a página — continua devolvendo
    os três ingredientes normalmente, só sem a garantia extra do snapshot
    único (ver o docstring)."""
    with transaction.atomic():
        resultado = apurar_balanco_patrimonial(
            empresa=_cenario_simples["empresa"], data_base=date(2026, 1, 31)
        )
    assert set(resultado.keys()) == {"saldos", "emissao", "identificacao"}
    assert resultado["emissao"]["pode_emitir"] is True


@pytest.mark.django_db(transaction=True)
def test_dl034_sem_o_wrapper_a_escrita_concorrente_produz_diferenca_fantasma(monkeypatch):
    """**ANTES** (a vulnerabilidade é real, medida — não presumida):
    chamando `apurar_saldos` DIRETO (sem o wrapper de snapshot), uma
    escrita concorrente entre a consulta que lista as CONTAS e a consulta
    que agrega débito/crédito produz uma diferença TRANSITÓRIA na equação
    — exatamente o que a DE-067 (achado A6 da DL-032) descreve.

    Mecanismo: pausa dentro de `_construir_hierarquia` (chamada logo
    depois da consulta que lista as contas, e logo antes da consulta de
    agregados) — nesse intervalo, uma SEGUNDA conexão cria uma conta NOVA
    de Ativo (fora da lista já carregada) com um lançamento que a debita e
    credita "Capital" (PL, conta JÁ EXISTENTE). Sob `READ COMMITTED` (o
    padrão, sem transação em volta), a consulta de agregados enxerga o
    crédito em Capital (já estava na lista) mas o débito correspondente,
    na conta NOVA, nunca é somado (ela não entrou na hierarquia carregada
    nem na raiz "1" que a consolidaria) — o Ativo fica parado em 5.000,00
    enquanto o Patrimônio Líquido sobe para 6.000,00: a equação desbalanceia
    por exatamente o valor do lançamento concorrente, sem nenhum
    desbalanço real gravado na base (o lançamento, na origem, é perfeitamente
    balanceado — débito e crédito iguais).
    """
    empresa = _empresa("DL-034 Corrida Sem Snapshot")
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
    _lancar(empresa, date(2026, 1, 2), "Saldo inicial", caixa, capital, "5000.00")
    data_base = date(2026, 1, 31)

    liberar_escrita = threading.Event()
    escrita_commitou = threading.Event()
    original = contabilidade_services._construir_hierarquia

    def pausa_apos_carregar_contas(contas):
        resultado = original(contas)
        liberar_escrita.set()
        assert escrita_commitou.wait(timeout=5), "a escrita concorrente não commitou a tempo"
        return resultado

    monkeypatch.setattr(contabilidade_services, "_construir_hierarquia", pausa_apos_carregar_contas)

    resultado = {}

    def ler():
        resultado["saldos"] = apurar_saldos(empresa=empresa, data_base=data_base)
        connection.close()

    def escrever():
        assert liberar_escrita.wait(timeout=5), "a leitura não chegou à pausa a tempo"
        nova = Conta.objects.create(
            empresa=empresa,
            conta_pai=raiz_ativo,
            codigo="1.2",
            nome="Conta Nova Concorrente",
            tipo=TipoConta.ATIVO,
            natureza=D,
        )
        criar_lancamento(
            empresa=empresa,
            data=date(2026, 1, 15),
            historico="Escrita concorrente",
            itens=[
                {"conta": nova, "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
                {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
            ],
        )
        escrita_commitou.set()
        connection.close()

    t1 = threading.Thread(target=ler)
    t2 = threading.Thread(target=escrever)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()

    saldos = resultado["saldos"]
    # A diferença FANTASMA: o crédito concorrente em Capital entrou na
    # soma (já estava na hierarquia carregada), o débito na conta nova de
    # Ativo não — desbalanço de exatamente 1.000,00, sem nada de errado
    # gravado no banco (a prova está no teste par, abaixo, sob o wrapper,
    # e na releitura ao final DESTE teste).
    assert saldos["equacao"]["diferenca"] == Decimal("-1000.00")
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("5000.00")
    assert saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO] == Decimal("6000.00")

    # E a escrita REALMENTE aconteceu e commitou — lida de novo, SEM a
    # corrida (chamada nova, completa, sem pausa), o total bate: Ativo
    # sobe para 6.000,00, a conta nova aparece, e a equação fecha em
    # `0,00`. O que a corrida produziu acima foi um instante de leitura
    # INCONSISTENTE, nunca um dado errado gravado.
    connection.close()
    saldos_depois = apurar_saldos(empresa=empresa, data_base=data_base)
    assert saldos_depois["totais_por_tipo"][TipoConta.ATIVO] == Decimal("6000.00")
    assert saldos_depois["equacao"]["diferenca"] == Decimal("0.00")
    codigos_depois = {linha["conta"] for linha in saldos_depois["contas"]}
    assert "1.2" in codigos_depois


@pytest.mark.django_db(transaction=True)
def test_dl034_com_o_wrapper_o_snapshot_protege_da_diferenca_fantasma(monkeypatch):
    """**DEPOIS** (DE-067 paga a dívida): a MESMA corrida do teste par
    acima (mesma escrita concorrente: débito na conta NOVA de Ativo,
    crédito em "Capital"), agora através de `apurar_balanco_patrimonial`
    — a transação `REPEATABLE READ` faz a consulta de agregados enxergar
    o MESMO snapshot da consulta que lista as contas (tirado antes da
    escrita concorrente commitar): nem a conta nova nem o lançamento dela
    aparecem nesta leitura, e a equação fecha em `0,00`."""
    empresa = _empresa("DL-034 Corrida Com Snapshot")
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
    _lancar(empresa, date(2026, 1, 2), "Saldo inicial", caixa, capital, "5000.00")
    data_base = date(2026, 1, 31)

    liberar_escrita = threading.Event()
    escrita_commitou = threading.Event()
    original = contabilidade_services._construir_hierarquia

    def pausa_apos_carregar_contas(contas):
        resultado = original(contas)
        liberar_escrita.set()
        assert escrita_commitou.wait(timeout=5), "a escrita concorrente não commitou a tempo"
        return resultado

    monkeypatch.setattr(contabilidade_services, "_construir_hierarquia", pausa_apos_carregar_contas)

    resultado = {}

    def ler():
        resultado["balanco"] = apurar_balanco_patrimonial(empresa=empresa, data_base=data_base)
        connection.close()

    def escrever():
        assert liberar_escrita.wait(timeout=5), "a leitura não chegou à pausa a tempo"
        nova = Conta.objects.create(
            empresa=empresa,
            conta_pai=raiz_ativo,
            codigo="1.2",
            nome="Conta Nova Concorrente",
            tipo=TipoConta.ATIVO,
            natureza=D,
        )
        criar_lancamento(
            empresa=empresa,
            data=date(2026, 1, 15),
            historico="Escrita concorrente",
            itens=[
                {"conta": nova, "tipo": TipoPartida.DEBITO, "valor": Decimal("1000.00")},
                {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("1000.00")},
            ],
        )
        escrita_commitou.set()
        connection.close()

    t1 = threading.Thread(target=ler)
    t2 = threading.Thread(target=escrever)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)
    assert not t1.is_alive()
    assert not t2.is_alive()

    saldos = resultado["balanco"]["saldos"]
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")
    codigos = {linha["conta"] for linha in saldos["contas"]}
    assert "1.2" not in codigos
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("5000.00")
    assert saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO] == Decimal("5000.00")

    # E a escrita concorrente REALMENTE aconteceu e commitou — não é que
    # o teste "não viu porque não rodou": ela está lá, para quem ler DEPOIS,
    # com uma leitura NOVA e completa (sem a pausa — devolve o monkeypatch
    # à função original antes) e SEM transação especial nenhuma.
    monkeypatch.setattr(contabilidade_services, "_construir_hierarquia", original)
    connection.close()
    saldos_depois = apurar_saldos(empresa=empresa, data_base=data_base)
    assert saldos_depois["totais_por_tipo"][TipoConta.ATIVO] == Decimal("6000.00")
    assert saldos_depois["equacao"]["diferenca"] == Decimal("0.00")
    codigos_depois = {linha["conta"] for linha in saldos_depois["contas"]}
    assert "1.2" in codigos_depois
