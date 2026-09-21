"""DL-032, fatia 1 — a camada de saldos (`apps.contabilidade.services.apurar_saldos`).

Cobre os oito critérios de aceite do plano
(`docs/planos/DL-032-a-camada-de-saldos.md`) e os dois casos que o **RC-104**
revelou como faltantes (zeramento do exercício por lançamento, confirmado
pelo Fred em 2026-09-20, enquanto esta etapa estava em desenvolvimento): uma
base DEPOIS do zeramento, em que `(receita − despesa)` é exatamente zero, e
uma retificadora DENTRO do Patrimônio Líquido, que precisa SUBTRAIR, não
somar.

`apurar_saldos` REUSA o motor do Balancete (`apurar_balancete`, DE-020) — não
reimplementa a regra única de saldo. Por isso a maioria destes testes não
precisa de login/permissão: nenhuma das duas funções verifica autorização —
isso é responsabilidade da VIEW (que esta fatia não cria).

Dados 100% sintéticos, criados nos próprios testes.
"""

import itertools
import random
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.contabilidade.models import (
    Conta,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    HierarquiaInconsistente,
    apurar_balancete,
    apurar_saldos,
    criar_lancamento,
    encerrar_competencia,
    marcar_competencia_como_entregue,
    obter_ou_criar_competencia,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

D = NaturezaConta.DEVEDORA
C = NaturezaConta.CREDORA


# ---------------------------------------------------------------------------
# Fixtures e helpers — a mesma árvore de contas serve à maioria dos testes.
# Ela já nasce com as DUAS retificadoras que este projeto conhece: uma no
# Ativo ("(-) Prov. devedores duvidosos", child de "1"/ATIVO) e uma no PL
# ("(-) Prejuízos Acumulados", child de "3"/PATRIMÔNIO LÍQUIDO) — o mesmo
# padrão já usado em `scripts/semear_base_de_medicao.py` ("(-) Depreciação
# acumulada", "Deduções da receita bruta") e agora confirmado como caso real
# do plano de contas do Fred pelo RC-104.
# ---------------------------------------------------------------------------


_CONTADOR_DE_CNPJ = itertools.count(1)


def _cnpj_sintetico():
    """14 dígitos únicos e determinísticos — nenhuma validação de dígito
    verificador roda em `.objects.create()` (só em `full_clean()`, ver
    `Empresa.save()`), então um contador simples basta e evita qualquer
    dependência de `hash()` (que varia de processo para processo)."""
    return f"{next(_CONTADOR_DE_CNPJ):014d}"


def _empresa(nome="Empresa DL-032"):
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=_cnpj_sintetico())
    return Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=_cnpj_sintetico()
    )


def _conta(empresa, *, codigo, nome, tipo, natureza, pai=None, aceita_lancamento=True):
    return Conta.objects.create(
        empresa=empresa,
        conta_pai=pai,
        codigo=codigo,
        nome=nome,
        tipo=tipo,
        natureza=natureza,
        aceita_lancamento=aceita_lancamento,
    )


def _arvore(empresa):
    """A árvore de referência (cinco raízes, uma por `TipoConta`, com as
    duas retificadoras do RC-104/base de medição) — devolve dict codigo ->
    `Conta`."""
    contas = {}
    raiz_ativo = _conta(
        empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D, aceita_lancamento=False
    )
    contas["caixa"] = _conta(
        empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D, pai=raiz_ativo
    )
    contas["prov_devedores"] = _conta(
        empresa,
        codigo="1.2",
        nome="(-) Prov. devedores duvidosos",
        tipo=TipoConta.ATIVO,
        natureza=C,  # retificadora: natureza OPOSTA ao grupo (Ativo é devedor)
        pai=raiz_ativo,
    )

    raiz_passivo = _conta(
        empresa,
        codigo="2",
        nome="PASSIVO",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        aceita_lancamento=False,
    )
    contas["fornecedores"] = _conta(
        empresa,
        codigo="2.1",
        nome="Fornecedores",
        tipo=TipoConta.PASSIVO,
        natureza=C,
        pai=raiz_passivo,
    )

    raiz_pl = _conta(
        empresa,
        codigo="3",
        nome="PATRIMÔNIO LÍQUIDO",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        aceita_lancamento=False,
    )
    contas["capital"] = _conta(
        empresa,
        codigo="3.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    contas["lucros_acumulados"] = _conta(
        empresa,
        codigo="3.2",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )
    contas["prejuizos_acumulados"] = _conta(
        empresa,
        codigo="3.3",
        nome="(-) Prejuízos Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=D,  # retificadora RC-104: natureza OPOSTA ao grupo (PL é credor)
        pai=raiz_pl,
    )
    contas["resultado_do_exercicio"] = _conta(
        empresa,
        codigo="3.4",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=C,
        pai=raiz_pl,
    )

    raiz_receita = _conta(
        empresa,
        codigo="4",
        nome="RECEITA",
        tipo=TipoConta.RECEITA,
        natureza=C,
        aceita_lancamento=False,
    )
    contas["vendas"] = _conta(
        empresa, codigo="4.1", nome="Vendas", tipo=TipoConta.RECEITA, natureza=C, pai=raiz_receita
    )

    raiz_despesa = _conta(
        empresa,
        codigo="5",
        nome="DESPESA",
        tipo=TipoConta.DESPESA,
        natureza=D,
        aceita_lancamento=False,
    )
    contas["despesas_gerais"] = _conta(
        empresa,
        codigo="5.1",
        nome="Despesas Gerais",
        tipo=TipoConta.DESPESA,
        natureza=D,
        pai=raiz_despesa,
    )

    contas["_raizes"] = {
        "ativo": raiz_ativo,
        "passivo": raiz_passivo,
        "pl": raiz_pl,
        "receita": raiz_receita,
        "despesa": raiz_despesa,
    }
    return contas


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


@pytest.fixture
def cenario_completo():
    """A árvore de referência com movimento em TODOS os cinco `TipoConta`,
    incluindo as duas retificadoras — os números abaixo foram conferidos à
    mão no relatório de entrega desta etapa (não são "o que o código
    devolveu", são a conta independente que o código precisa bater):

    Ativo = 1.170,00 (Caixa líquido 1.220,00 − Prov. devedores 50,00)
    Passivo = 150,00 (Fornecedores)
    PL = 920,00 (Capital 1.000,00 − Prejuízos Acumulados 80,00)
    Receita = 500,00 (Vendas)
    Despesa = 400,00 (Despesas Gerais: 200,00 + 50,00 + 150,00)
    Resultado do período = 100,00 (500,00 − 400,00)
    Equação: 1.170,00 = 150,00 + 920,00 + 100,00 — fecha nos dois lados.

    BL-477/achado A3: o último lançamento ("Despesa a prazo") está datado
    EXATAMENTE em `data_base` (31/01), de propósito — não é 20/01 por
    acaso. Sem movimento algum NO DIA de `data_base`, `saldo_anterior` e
    `saldo_final` ficam iguais para toda conta, e o critério 1
    (`apurar_saldos` bate com `apurar_balancete`) deixa de exercitar a
    coluna que ele existe para provar: a guarda reprovava por coincidência
    de outro teste, não pelo teste do critério 1 em si (medido pelo
    auditor por mutação). Os totais acima não mudam — é a mesma soma,
    só datada no dia certo.
    """
    empresa = _empresa("DL-032 Completo")
    contas = _arvore(empresa)
    jan = date(2026, 1, 31)
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
        date(2026, 1, 15),
        "Baixa de prejuízo acumulado",
        contas["prejuizos_acumulados"],
        contas["caixa"],
        "80.00",
    )
    _lancar(
        empresa,
        jan,
        "Despesa a prazo",
        contas["despesas_gerais"],
        contas["fornecedores"],
        "150.00",
    )
    return {"empresa": empresa, "contas": contas, "data_base": jan}


# ---------------------------------------------------------------------------
# Critério 1 — apurar_saldos e apurar_balancete NUNCA discordam.
# ---------------------------------------------------------------------------


def test_apurar_saldos_bate_com_apurar_balancete_conta_a_conta(cenario_completo):
    """Compara, conta a conta, o saldo de `apurar_saldos` com o `saldo_final`
    de `apurar_balancete` no MESMO ponto no tempo — para VÁRIOS `inicio`
    diferentes, provando a independência que o docstring de `apurar_saldos`
    afirma (a prova algébrica de que `saldo_final` não depende de `inicio`
    quando `fim` é fixo). Reprova no primeiro centavo de diferença."""
    empresa = cenario_completo["empresa"]
    data_base = cenario_completo["data_base"]

    saldos = apurar_saldos(empresa=empresa, data_base=data_base)
    saldo_por_codigo = {linha["conta"]: linha["saldo"] for linha in saldos["contas"]}

    for inicio in (date(2000, 1, 1), date(2026, 1, 1), date(2026, 1, 15), data_base):
        balancete = apurar_balancete(empresa=empresa, inicio=inicio, fim=data_base)
        assert len(balancete["contas"]) == len(saldos["contas"])
        for linha in balancete["contas"]:
            assert saldo_por_codigo[linha["conta"]] == linha["saldo_final"], (
                f"conta {linha['conta']}: apurar_saldos deu "
                f"{saldo_por_codigo[linha['conta']]}, apurar_balancete "
                f"(inicio={inicio}) deu {linha['saldo_final']}"
            )


def test_apurar_saldos_expoe_codigo_nome_tipo_natureza_e_nivel(cenario_completo):
    """Escopo item 1: cada linha traz código, nome, tipo, natureza e nível —
    não só o saldo."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    caixa = next(linha for linha in saldos["contas"] if linha["conta"] == "1.1")
    assert caixa["nome"] == "Caixa"
    assert caixa["tipo"] == TipoConta.ATIVO
    assert caixa["natureza"] == NaturezaConta.DEVEDORA
    assert caixa["nivel"] == 2
    assert caixa["saldo"] == Decimal("1220.00")


def test_lancamento_no_dia_exato_da_data_base_entra_no_saldo(cenario_completo):
    """BL-477/achado A3: a fronteira em si — `data_base` no MESMO dia de um
    lançamento inclui (`<=`, não `<`) — nunca tinha sido afirmada por um
    teste nomeado (caso de teste da auditoria). Fixture DEDICADA (não usa
    `cenario_completo`) para isolar exatamente a fronteira: um único
    lançamento, datado no dia da `data_base` testada."""
    empresa = _empresa("DL-032 Fronteira")
    contas = _arvore(empresa)
    dia = date(2026, 1, 31)
    _lancar(
        empresa, dia, "Capitalização na fronteira", contas["caixa"], contas["capital"], "1000.00"
    )

    no_dia = apurar_saldos(empresa=empresa, data_base=dia)
    saldo_caixa_no_dia = next(
        linha["saldo"] for linha in no_dia["contas"] if linha["conta"] == "1.1"
    )
    assert saldo_caixa_no_dia == Decimal("1000.00")
    assert no_dia["equacao"]["diferenca"] == Decimal("0")

    antes = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 30))
    saldo_caixa_antes = next(linha["saldo"] for linha in antes["contas"] if linha["conta"] == "1.1")
    assert saldo_caixa_antes == Decimal("0")
    assert antes["equacao"]["diferenca"] == Decimal("0")


# ---------------------------------------------------------------------------
# Critério 2 — a equação é reportada, nunca forçada.
# ---------------------------------------------------------------------------


def test_equacao_fecha_em_base_correta(cenario_completo):
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    equacao = saldos["equacao"]
    assert equacao["ativo"] == Decimal("1170.00")
    assert equacao["passivo"] == Decimal("150.00")
    assert equacao["patrimonio_liquido"] == Decimal("920.00")
    assert equacao["resultado_nao_transferido"] == Decimal("100.00")
    assert equacao["diferenca"] == Decimal("0.00")


def test_diferenca_aparece_com_valor_e_sinal_e_nenhum_saldo_e_alterado(cenario_completo):
    """Base DELIBERADAMENTE torta: um `ItemLancamento` gravado direto pelo
    ORM, contornando `criar_lancamento` (mesma técnica já usada por
    `test_conferencia_encontra_lote_desbalanceado_gravado_via_orm` na
    DL-015 — é o único jeito de produzir um lote desbalanceado, porque o
    serviço nunca grava um). A diferença tem que aparecer, com o valor e o
    sinal exatos do desbalanço — e o saldo de CADA conta, inclusive o da
    conta afetada, continua sendo exatamente o que os lançamentos (tortos
    ou não) somam, nunca "ajustado" para fechar."""
    empresa = cenario_completo["empresa"]
    contas = cenario_completo["contas"]
    data_base = cenario_completo["data_base"]

    antes = apurar_saldos(empresa=empresa, data_base=data_base)
    saldo_caixa_antes = next(linha["saldo"] for linha in antes["contas"] if linha["conta"] == "1.1")

    lote_torto = LancamentoContabil.objects.create(
        empresa=empresa, data=data_base, historico="Ajuste torto (DL-032, critério 2)"
    )
    ItemLancamento.objects.create(
        lancamento=lote_torto,
        conta=contas["caixa"],
        tipo=TipoPartida.DEBITO,
        valor=Decimal("300.00"),
    )
    # SEM a contrapartida de crédito — é isto que torna a base torta.

    depois = apurar_saldos(empresa=empresa, data_base=data_base)

    # O momento da verdade: a diferença aparece, com sinal — nunca é
    # escondida nem usada para "consertar" nenhum saldo.
    assert depois["equacao"]["diferenca"] == Decimal("300.00")
    saldo_caixa_depois = next(
        linha["saldo"] for linha in depois["contas"] if linha["conta"] == "1.1"
    )
    # O saldo do Caixa reflete FIELMENTE o débito torto somado — não foi
    # revertido nem "corrigido" para manter a equação fechada.
    assert saldo_caixa_depois == saldo_caixa_antes + Decimal("300.00")
    # As outras quatro pernas da equação são estranhas ao ajuste torto (ele
    # só tocou o Ativo) — continuam intactas.
    assert depois["equacao"]["passivo"] == antes["equacao"]["passivo"]
    assert depois["equacao"]["patrimonio_liquido"] == antes["equacao"]["patrimonio_liquido"]
    assert (
        depois["equacao"]["resultado_nao_transferido"]
        == antes["equacao"]["resultado_nao_transferido"]
    )


# ---------------------------------------------------------------------------
# Critério 3 — precisão exata (Decimal), nunca ponto flutuante binário.
# ---------------------------------------------------------------------------


def test_precisao_decimal_com_valores_que_quebram_float():
    """0.10 + 0.20 é o exemplo clássico de erro de ponto flutuante binário
    (`0.1 + 0.2 == 0.30000000000000004` em `float` puro do Python). Se
    `apurar_saldos` (ou o motor que reusa) usasse `float` em algum ponto do
    caminho, o saldo sairia com essa sujeira; com `Decimal` de ponta a
    ponta (campo do banco é `DecimalField`), o resultado é EXATO."""
    empresa = _empresa("DL-032 Precisão")
    contas = _arvore(empresa)
    data_base = date(2026, 1, 31)
    _lancar(empresa, date(2026, 1, 2), "Depósito 1", contas["caixa"], contas["capital"], "0.10")
    _lancar(empresa, date(2026, 1, 3), "Depósito 2", contas["caixa"], contas["capital"], "0.20")

    saldos = apurar_saldos(empresa=empresa, data_base=data_base)
    caixa = next(linha for linha in saldos["contas"] if linha["conta"] == "1.1")

    assert isinstance(caixa["saldo"], Decimal)
    assert caixa["saldo"] == Decimal("0.30")
    assert repr(caixa["saldo"]) == "Decimal('0.30')"
    # Documenta o defeito que este teste está provando que NÃO acontece
    # aqui: em `float` puro, a mesma soma dá "sujeira" de ponto flutuante
    # binário, não 0.30 exato.
    assert 0.10 + 0.20 != 0.30


# ---------------------------------------------------------------------------
# Critério 4 — os cinco tipos somam o universo, DERIVADO do modelo (DE-056).
# ---------------------------------------------------------------------------


def test_totais_por_tipo_tem_exatamente_as_chaves_do_modelo_tipoconta(cenario_completo):
    """Não compara contra uma tupla escrita à mão: lê `TipoConta.values`
    diretamente do MODELO. Se algum dia `apurar_saldos` for reescrito com
    uma tupla de cinco strings fixas (o anti-padrão que este projeto já
    pagou caro), e o modelo ganhar um sexto `TipoConta`, este teste
    reprova — o dict não teria a chave nova."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    assert set(saldos["totais_por_tipo"].keys()) == set(TipoConta.values)
    for tipo in TipoConta.values:
        assert isinstance(saldos["totais_por_tipo"][tipo], Decimal)


def test_totais_por_tipo_valores_conferidos_a_mao(cenario_completo):
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    totais = saldos["totais_por_tipo"]
    assert totais[TipoConta.ATIVO] == Decimal("1170.00")
    assert totais[TipoConta.PASSIVO] == Decimal("150.00")
    assert totais[TipoConta.PATRIMONIO_LIQUIDO] == Decimal("920.00")
    assert totais[TipoConta.RECEITA] == Decimal("500.00")
    assert totais[TipoConta.DESPESA] == Decimal("400.00")


def test_tipo_sem_nenhuma_conta_entra_com_zero_nao_fica_de_fora(cenario_completo):
    """Um `TipoConta` sem raiz na empresa (aqui, Passivo teria zero movimento
    se removêssemos Fornecedores) ainda aparece no dict — com zero, nunca
    ausente. Prova indireta: a própria empresa do cenário JÁ tem essa
    garantia, porque `totais_por_tipo` nasce de `TipoConta.values`, não de
    quais tipos têm movimento."""
    empresa_vazia = _empresa("DL-032 Sem Movimento")
    _arvore(empresa_vazia)  # contas existem, mas NENHUM lançamento
    saldos = apurar_saldos(empresa=empresa_vazia, data_base=date(2026, 1, 31))
    assert saldos["totais_por_tipo"] == {tipo: Decimal("0") for tipo in TipoConta.values}
    assert saldos["equacao"]["diferenca"] == Decimal("0")


def test_cenario_correto_nao_tem_conta_com_tipo_divergente_da_raiz(cenario_completo):
    """BL-475/achado A2 — CONTROLE POSITIVO: no plano de contas coerente
    (nenhuma conta com `tipo` diferente do `tipo` da sua raiz),
    `contas_com_tipo_divergente_da_raiz` sai VAZIA. Sem este teste, um
    mutante que zerasse a detecção (sempre devolvendo `[]`) passaria
    despercebido — e uma detecção que acusasse TUDO viraria ruído sem que
    nada o revelasse."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    assert saldos["contas_com_tipo_divergente_da_raiz"] == []


def test_conta_descendente_com_tipo_diferente_da_raiz_e_declarada_nunca_corrigida():
    """BL-475/achado A2 — reproduz a sonda P2 da auditoria: uma conta
    "Despesa" (1.9) pendurada sob a raiz do Ativo (mau cadastro). O saldo
    dela é somado no grupo da RAIZ (Ativo) pela regra única de saldo — a
    decisão está CERTA e não muda aqui (mutantes M4/M5 do relatório provam
    que agregar de outro jeito quebra a retificadora do RC-104). O que
    tinha que existir e não existia é a DECLARAÇÃO: a conta 1.9 nomeada em
    `contas_com_tipo_divergente_da_raiz`, com o `tipo` próprio E o
    `tipo_da_raiz`, para o mesmo dicionário deixar de se contradizer em
    silêncio."""
    empresa = _empresa("DL-032 Tipo Divergente")
    raiz_ativo = _conta(empresa, codigo="1", nome="ATIVO", tipo=TipoConta.ATIVO, natureza=D)
    caixa = _conta(
        empresa, codigo="1.1", nome="Caixa", tipo=TipoConta.ATIVO, natureza=D, pai=raiz_ativo
    )
    despesa_mal_cadastrada = _conta(
        empresa,
        codigo="1.9",
        nome="Despesa mal cadastrada",
        tipo=TipoConta.DESPESA,  # tipo DIFERENTE do tipo da raiz (Ativo)
        natureza=D,
        pai=raiz_ativo,
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
    data_base = date(2026, 1, 31)
    _lancar(empresa, date(2026, 1, 2), "Capitalização", caixa, capital, "1000.00")
    _lancar(
        empresa,
        date(2026, 1, 10),
        "Lançamento mal classificado",
        despesa_mal_cadastrada,
        caixa,
        "300.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=data_base)

    divergentes = {linha["conta"]: linha for linha in saldos["contas_com_tipo_divergente_da_raiz"]}
    assert "1.9" in divergentes, saldos["contas_com_tipo_divergente_da_raiz"]
    assert divergentes["1.9"]["tipo"] == TipoConta.DESPESA
    assert divergentes["1.9"]["tipo_da_raiz"] == TipoConta.ATIVO
    # A linha da conta 1.9 continua dizendo `tipo=despesa` — não é
    # reclassificada — mas agora a divergência está NOMEADA em vez de só
    # contradizer `totais_por_tipo` em silêncio (achado A2 original).
    linha_1_9 = next(linha for linha in saldos["contas"] if linha["conta"] == "1.9")
    assert linha_1_9["tipo"] == TipoConta.DESPESA
    # O saldo consolidado do Ativo continua sendo o que a regra única de
    # saldo (DE-020) manda somar — esta correção NUNCA move dinheiro.
    assert saldos["totais_por_tipo"][TipoConta.ATIVO] == Decimal("1000.00")
    assert saldos["equacao"]["diferenca"] == Decimal("0.00")


def test_tipo_gravado_fora_de_tipoconta_e_nomeado_nunca_derruba():
    """BL-476/achado A1 — reproduz a sonda Q1: um `tipo` gravado fora de
    `TipoConta` (só alcançável por escrita direta no ORM/SQL — a tela e o
    serializer sempre validam `choices`) não pode estourar `KeyError` nem
    ser criado como chave nova dentro de `totais_por_tipo` (o que
    desmontaria a garantia do critério 4/DE-056 de que as chaves são
    EXATAMENTE as de `TipoConta.values`). Tem que aparecer, nomeado, em
    `contas_com_tipo_desconhecido`."""
    empresa = _empresa("DL-032 Tipo Desconhecido")
    raiz_torta = _conta(
        empresa, codigo="7", nome="Conta corrompida", tipo=TipoConta.ATIVO, natureza=D
    )
    Conta.objects.filter(pk=raiz_torta.pk).update(tipo="custo")

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))

    assert set(saldos["totais_por_tipo"].keys()) == set(TipoConta.values)  # nunca cria chave nova
    desconhecidos = {linha["conta"]: linha for linha in saldos["contas_com_tipo_desconhecido"]}
    assert "7" in desconhecidos, saldos["contas_com_tipo_desconhecido"]
    assert desconhecidos["7"]["tipo"] == "custo"
    assert desconhecidos["7"]["nome"] == "Conta corrompida"


def test_tipos_tratados_na_equacao_batem_com_tipoconta(cenario_completo):
    """BL-479/achado A5 — guarda DERIVADA, no molde de
    `test_target_version_do_ruff_bate_com_requires_python`
    (`apps/core/tests/test_versao_minima_python.py`): as chaves da
    `equacao` que representam um `TipoConta` (tudo, exceto `diferenca` e
    `resultado_nao_transferido`, que não são tipos) são lidas do próprio
    resultado em tempo de execução — não copiadas à mão aqui — e
    comparadas contra `set(TipoConta.values)`, derivado do MODELO. Se um
    sexto `TipoConta` nascer sem que a equação passe a tratá-lo, este
    teste reprova NOMEANDO o tipo esquecido, em vez de o valor dele
    reaparecer como `diferenca` anônima (o defeito medido pela sonda S3 da
    auditoria)."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    chaves_que_nao_sao_tipo = {"diferenca", "resultado_nao_transferido"}
    tipos_tratados_na_equacao = set(saldos["equacao"].keys()) - chaves_que_nao_sao_tipo
    assert tipos_tratados_na_equacao == set(TipoConta.values), (
        f"a equação trata {sorted(tipos_tratados_na_equacao)}, mas "
        f"TipoConta.values é {sorted(TipoConta.values)} — tipo(s) sem "
        f"tratamento na equação: {set(TipoConta.values) - tipos_tratados_na_equacao}"
    )


# ---------------------------------------------------------------------------
# Critério 5 — isolamento entre empresas (e entre escritórios).
# ---------------------------------------------------------------------------


def test_isolamento_entre_empresas_de_escritorios_diferentes():
    empresa_a = _empresa("DL-032 Isolamento A")
    empresa_b = _empresa("DL-032 Isolamento B")
    contas_a = _arvore(empresa_a)
    contas_b = _arvore(empresa_b)
    data_base = date(2026, 1, 31)

    _lancar(
        empresa_a, date(2026, 1, 2), "Capital A", contas_a["caixa"], contas_a["capital"], "1000.00"
    )
    _lancar(
        empresa_b, date(2026, 1, 2), "Capital B", contas_b["caixa"], contas_b["capital"], "777.00"
    )

    saldos_a = apurar_saldos(empresa=empresa_a, data_base=data_base)
    saldos_b = apurar_saldos(empresa=empresa_b, data_base=data_base)

    caixa_a = next(linha["saldo"] for linha in saldos_a["contas"] if linha["conta"] == "1.1")
    caixa_b = next(linha["saldo"] for linha in saldos_b["contas"] if linha["conta"] == "1.1")
    assert caixa_a == Decimal("1000.00")
    assert caixa_b == Decimal("777.00")
    assert saldos_a["equacao"]["ativo"] == Decimal("1000.00")
    assert saldos_b["equacao"]["ativo"] == Decimal("777.00")
    # O código "1.1" é o MESMO nas duas empresas (mesmo plano de referência)
    # — se houvesse vazamento, o total de uma incluiria o da outra.
    assert saldos_a["equacao"]["ativo"] != saldos_b["equacao"]["ativo"]


# ---------------------------------------------------------------------------
# Critério 6 — leitura pura: apurar_saldos não grava nada.
# ---------------------------------------------------------------------------


def test_apurar_saldos_nao_grava_nada(cenario_completo):
    empresa = cenario_completo["empresa"]
    data_base = cenario_completo["data_base"]
    with CaptureQueriesContext(connection) as capturadas:
        apurar_saldos(empresa=empresa, data_base=data_base)

    assert len(capturadas) > 0  # o teste não pode passar por não ter medido nada
    for consulta in capturadas:
        comando = consulta["sql"].strip().split(" ", 1)[0].upper()
        assert comando == "SELECT", f"consulta não-SELECT durante leitura pura: {consulta['sql']}"


def test_competencia_encerrada_e_entregue_nao_muda_o_resultado_nem_grava(cenario_completo):
    """Competência encerrada ou entregue não muda o resultado (critério 6) —
    e a PRÓPRIA chamada de `apurar_saldos`, feita DEPOIS do fechamento,
    continua sem gravar nada."""
    empresa = cenario_completo["empresa"]
    data_base = cenario_completo["data_base"]
    usuario = get_user_model().objects.create_superuser(
        username="dl032-encerramento", email="dl032@escritorio.com.br", password="senha-forte-123"
    )

    antes = apurar_saldos(empresa=empresa, data_base=data_base)

    obter_ou_criar_competencia(empresa=empresa, ano=2026, mes=1)
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=usuario)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=1, usuario=usuario)

    competencia = obter_ou_criar_competencia(empresa=empresa, ano=2026, mes=1)
    assert competencia.estado == EstadoCompetencia.ENCERRADA

    with CaptureQueriesContext(connection) as capturadas:
        depois = apurar_saldos(empresa=empresa, data_base=data_base)
    for consulta in capturadas:
        comando = consulta["sql"].strip().split(" ", 1)[0].upper()
        assert comando == "SELECT"

    assert depois == antes


# ---------------------------------------------------------------------------
# Critério 7 — data futura e data absurda: sem erro cru, comportamento
# declarado. E o escopo item 5 (saldo de abertura).
# ---------------------------------------------------------------------------


def test_data_futura_sem_movimento_nenhum_devolve_o_mesmo_saldo(cenario_completo):
    """`data_base` bem à frente de qualquer lançamento (o mesmo ano-armadilha
    9999 que a DL-020/BL-198 usa) não levanta exceção — devolve exatamente
    o saldo acumulado até o último lançamento real, porque não há mais
    nada depois dele."""
    empresa = cenario_completo["empresa"]
    no_dia = apurar_saldos(empresa=empresa, data_base=cenario_completo["data_base"])
    no_futuro = apurar_saldos(empresa=empresa, data_base=date(9999, 12, 31))
    assert no_futuro["equacao"]["ativo"] == no_dia["equacao"]["ativo"]
    assert no_futuro["equacao"]["diferenca"] == no_dia["equacao"]["diferenca"]
    saldo_por_codigo_futuro = {linha["conta"]: linha["saldo"] for linha in no_futuro["contas"]}
    for linha in no_dia["contas"]:
        assert saldo_por_codigo_futuro[linha["conta"]] == linha["saldo"]


def test_data_absurda_no_passado_antes_de_qualquer_lancamento_devolve_zeros(cenario_completo):
    """Escopo item 5 — saldo de abertura: `data_base` anterior a QUALQUER
    lançamento (inclusive uma data absurda como `0001-01-01`, o mesmo
    exemplo de "data absurda" já usado no resto do projeto — RC-77/BL-205)
    devolve zeros em toda linha, sem erro."""
    empresa = cenario_completo["empresa"]
    saldos = apurar_saldos(empresa=empresa, data_base=date(1, 1, 1))
    assert saldos["contas"]  # as contas existem
    for linha in saldos["contas"]:
        assert linha["saldo"] == Decimal("0"), linha
    equacao = saldos["equacao"]
    assert equacao["ativo"] == equacao["passivo"] == equacao["patrimonio_liquido"] == Decimal("0")
    assert equacao["diferenca"] == Decimal("0")


def test_empresa_sem_nenhuma_conta_nao_quebra():
    empresa = _empresa("DL-032 Sem Conta")
    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))
    assert saldos["contas"] == []
    assert saldos["totais_por_tipo"] == {tipo: Decimal("0") for tipo in TipoConta.values}
    assert saldos["equacao"]["diferenca"] == Decimal("0")


# ---------------------------------------------------------------------------
# RC-104 (Fred, 2026-09-20) — os dois casos que o zeramento por lançamento
# revelou como faltantes.
# ---------------------------------------------------------------------------


def test_retificadora_dentro_do_patrimonio_liquido_subtrai_nunca_soma(cenario_completo):
    """RC-104: "(-) Prejuízos Acumulados" é retificadora dentro do PL,
    natureza DEVEDORA (oposta ao grupo, que é CREDOR). O total de PL tem
    que REFLETIR a subtração (Capital 1.000,00 − Prejuízo 80,00 = 920,00),
    nunca a soma ingênua que trataria a retificadora com a PRÓPRIA
    natureza dela isolada (o que daria 1.080,00 — errado, e é exatamente o
    defeito que a DE-020 já corrigiu uma vez no Balancete; reusar o motor
    herda o acerto, reimplementar herdaria o defeito)."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    pl = saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO]
    assert pl == Decimal("920.00")
    assert pl != Decimal("1080.00")  # a soma ingênua que a retificadora existe para evitar


def test_apos_zeramento_resultado_e_zero_e_equacao_fecha_na_forma_classica(cenario_completo):
    """RC-104: depois do zeramento (mensal/trimestral/anual, por lançamento
    — a rotina em si NÃO é desta etapa), Receita e Despesa terminam
    zeradas e o resultado já foi transferido ao PL. `(receita − despesa)`
    tem que dar EXATAMENTE zero, e a equação fecha na forma clássica
    Ativo = Passivo + PL — é o estado em que a maior parte das bases reais
    vai estar, e nenhum dos oito critérios originais nomeia esse caso
    isoladamente."""
    empresa = cenario_completo["empresa"]
    contas = cenario_completo["contas"]
    fev = date(2026, 2, 20)

    # Passo 1: zera Vendas (crédito 500,00) contra a conta transitória.
    _lancar(
        empresa,
        date(2026, 2, 1),
        "Zeramento — Vendas",
        contas["vendas"],
        contas["resultado_do_exercicio"],
        "500.00",
    )
    # Passo 2: zera Despesas Gerais (débito 400,00) contra a transitória.
    _lancar(
        empresa,
        date(2026, 2, 1),
        "Zeramento — Despesas Gerais",
        contas["resultado_do_exercicio"],
        contas["despesas_gerais"],
        "400.00",
    )
    # Passo 3: o lucro apurado (100,00) vai para Lucros Acumulados.
    _lancar(
        empresa,
        date(2026, 2, 1),
        "Transferência do resultado ao PL",
        contas["resultado_do_exercicio"],
        contas["lucros_acumulados"],
        "100.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=fev)
    equacao = saldos["equacao"]

    assert equacao["receita"] == Decimal("0.00")
    assert equacao["despesa"] == Decimal("0.00")
    assert equacao["resultado_nao_transferido"] == Decimal("0.00")
    # Forma clássica: Ativo = Passivo + PL (o termo de resultado é zero, não
    # "removido" — a MESMA fórmula, sem nenhum `if`, chega à forma
    # clássica por construção).
    assert equacao["ativo"] == equacao["passivo"] + equacao["patrimonio_liquido"]
    assert equacao["ativo"] == Decimal("1170.00")
    assert equacao["patrimonio_liquido"] == Decimal("1020.00")  # 1000 - 80 + 100
    assert equacao["diferenca"] == Decimal("0.00")

    saldo_por_codigo = {linha["conta"]: linha["saldo"] for linha in saldos["contas"]}
    assert saldo_por_codigo["4.1"] == Decimal("0.00")  # Vendas zerada
    assert saldo_por_codigo["5.1"] == Decimal("0.00")  # Despesas Gerais zerada
    assert saldo_por_codigo["3.4"] == Decimal("0.00")  # Resultado do Exercício de volta a zero


def test_apos_zeramento_resultado_nao_transferido_e_zero_mas_resultado_do_mes_nao(cenario_completo):
    """BL-478/achado A4 — fixa por TESTE, não por comentário, a diferença
    entre `resultado_nao_transferido` (o termo da equação: o SALDO ainda
    não transferido ao PL) e "o resultado do mês" (o MOVIMENTO do
    período, RC-104, penúltima ressalva: "a DRE de um período se constrói
    pelo MOVIMENTO do período, nunca pelo SALDO das contas"). Janeiro
    (`cenario_completo`) teve lucro de 100,00; depois do zeramento de
    fevereiro, `resultado_nao_transferido` é ZERO — mas o lucro de
    janeiro não deixou de existir, e continua mensurável pelo MOVIMENTO de
    janeiro (créditos de Receita menos débitos de Despesa DENTRO do
    período), obtido de `apurar_balancete(inicio, fim)` — nunca de
    `apurar_saldos`, que esta camada declara NÃO servir para apurar DRE."""
    empresa = cenario_completo["empresa"]
    contas = cenario_completo["contas"]

    _lancar(
        empresa,
        date(2026, 2, 1),
        "Zeramento — Vendas",
        contas["vendas"],
        contas["resultado_do_exercicio"],
        "500.00",
    )
    _lancar(
        empresa,
        date(2026, 2, 1),
        "Zeramento — Despesas Gerais",
        contas["resultado_do_exercicio"],
        contas["despesas_gerais"],
        "400.00",
    )
    _lancar(
        empresa,
        date(2026, 2, 1),
        "Transferência do resultado ao PL",
        contas["resultado_do_exercicio"],
        contas["lucros_acumulados"],
        "100.00",
    )

    saldos = apurar_saldos(empresa=empresa, data_base=date(2026, 2, 20))
    assert saldos["equacao"]["resultado_nao_transferido"] == Decimal("0.00")

    # O movimento de JANEIRO (a Zeramento está datada em FEVEREIRO, fora
    # desta janela) mostra o lucro que de fato ocorreu — 500,00 de Receita
    # creditada menos 400,00 de Despesa debitada, o MESMO 100,00 conferido
    # à mão na fixture — mesmo `resultado_nao_transferido` já tendo voltado
    # a zero.
    movimento_de_janeiro = apurar_balancete(
        empresa=empresa, inicio=date(2026, 1, 1), fim=date(2026, 1, 31)
    )
    vendas = next(linha for linha in movimento_de_janeiro["contas"] if linha["conta"] == "4")
    despesa = next(linha for linha in movimento_de_janeiro["contas"] if linha["conta"] == "5")
    resultado_do_mes = vendas["creditos"] - despesa["debitos"]

    assert resultado_do_mes == Decimal("100.00")
    assert resultado_do_mes != saldos["equacao"]["resultado_nao_transferido"]


# ---------------------------------------------------------------------------
# Achados baixos da rodada 1 (BL-480, BL-481, BL-482) — comportamento já
# correto, agora declarado no contrato E fixado por teste.
# ---------------------------------------------------------------------------


def test_hierarquia_inconsistente_propaga_ciclo_sem_recursion_error():
    """BL-480/achado A7 — herdado do reuso de `apurar_balancete`: um ciclo
    na hierarquia (a conta sendo sua própria ancestral) levanta
    `HierarquiaInconsistente`, nomeando a conta, em vez de um
    `RecursionError` cru. `apurar_saldos` NÃO trata a exceção — propaga,
    como o contrato agora declara."""
    empresa = _empresa("DL-032 Ciclo")
    a = _conta(empresa, codigo="1", nome="A", tipo=TipoConta.ATIVO, natureza=D)
    b = _conta(empresa, codigo="1.1", nome="B", tipo=TipoConta.ATIVO, natureza=D, pai=a)
    a.conta_pai = b
    a.save(update_fields=["conta_pai"])

    with pytest.raises(HierarquiaInconsistente):
        apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))


def test_hierarquia_inconsistente_propaga_conta_pai_de_outra_empresa():
    """BL-480/achado A7 — `conta_pai` apontando para conta de OUTRA
    empresa (só alcançável por ORM/SQL direto, BL-40) levanta
    `HierarquiaInconsistente`, nomeando a conta, em vez de `KeyError`."""
    empresa = _empresa("DL-032 Pai De Outra Empresa")
    outra_empresa = _empresa("DL-032 Outra Empresa")
    conta_de_outra = _conta(
        outra_empresa, codigo="1", nome="Raiz de outra empresa", tipo=TipoConta.ATIVO, natureza=D
    )
    conta_corrompida = _conta(empresa, codigo="1.1", nome="Órfã", tipo=TipoConta.ATIVO, natureza=D)
    Conta.objects.filter(pk=conta_corrompida.pk).update(conta_pai_id=conta_de_outra.pk)

    with pytest.raises(HierarquiaInconsistente):
        apurar_saldos(empresa=empresa, data_base=date(2026, 1, 31))


def test_raiz_de_cada_linha_e_exatamente_nivel_igual_a_um(cenario_completo):
    """BL-481/achado A8 — `linha["raiz"]` é repassado (não existia antes) e
    fixa por teste a equivalência com `nivel == 1`, que o contrato agora
    declara. Prova adicional: somar `contas` por `tipo` filtrando por
    `raiz` reproduz `totais_por_tipo` exatamente — a leitura que o
    critério 4 convida, sem contar nenhuma conta em dobro."""
    saldos = apurar_saldos(
        empresa=cenario_completo["empresa"], data_base=cenario_completo["data_base"]
    )
    for linha in saldos["contas"]:
        assert linha["raiz"] == (linha["nivel"] == 1), linha

    reproduzido = {tipo: Decimal("0") for tipo in TipoConta.values}
    for linha in saldos["contas"]:
        if linha["raiz"]:
            reproduzido[linha["tipo"]] += linha["saldo"]
    assert reproduzido == saldos["totais_por_tipo"]


def test_conta_inativa_com_saldo_residual_entra_no_total(cenario_completo):
    """BL-482/achado A9 — deliberado: uma conta desativada (`ativo=False`)
    com saldo residual continua aparecendo em `contas` e contribuindo
    para `totais_por_tipo` — do contrário o Balanço perderia dinheiro. O
    comportamento já era este; o que faltava era declará-lo e fixá-lo por
    teste."""
    empresa = cenario_completo["empresa"]
    contas = cenario_completo["contas"]
    data_base = cenario_completo["data_base"]

    antes = apurar_saldos(empresa=empresa, data_base=data_base)
    ativo_antes = antes["equacao"]["ativo"]

    contas["caixa"].ativo = False
    contas["caixa"].save(update_fields=["ativo"])

    depois = apurar_saldos(empresa=empresa, data_base=data_base)
    linha_caixa = next(linha for linha in depois["contas"] if linha["conta"] == "1.1")
    assert linha_caixa["saldo"] == Decimal("1220.00")  # continua aparecendo, com o saldo
    assert depois["equacao"]["ativo"] == ativo_antes  # e continua somado no total


# ---------------------------------------------------------------------------
# Risco declarado — desempenho num plano de contas realista.
# ---------------------------------------------------------------------------


def _plano_realista_73_contas_4_niveis():
    """O MESMO plano de referência de `scripts/semear_base_de_medicao.py`
    (73 contas, 4 níveis) — duplicado aqui de propósito, em vez de
    importado: `scripts/` não é um pacote do projeto (sem `__init__.py`,
    fora do `sys.path` do pytest), e a base de medição já está isolada por
    duas travas (senha e nome do banco) que não fazem sentido para um
    teste automático. Lista idêntica: qualquer divergência entre as duas é
    bug de cópia, não de design."""
    d, c = NaturezaConta.DEVEDORA, NaturezaConta.CREDORA
    a, p, pl, r, de = (
        TipoConta.ATIVO,
        TipoConta.PASSIVO,
        TipoConta.PATRIMONIO_LIQUIDO,
        TipoConta.RECEITA,
        TipoConta.DESPESA,
    )
    return [
        ("1", "ATIVO", a, d),
        ("1.1", "ATIVO CIRCULANTE", a, d),
        ("1.1.1", "Disponível", a, d),
        ("1.1.1.01", "Caixa geral", a, d),
        ("1.1.1.02", "Banco do Brasil c/c", a, d),
        ("1.1.1.03", "Itaú c/c", a, d),
        ("1.1.1.04", "Aplicações de liquidez imediata", a, d),
        ("1.1.2", "Créditos a receber", a, d),
        ("1.1.2.01", "Clientes nacionais", a, d),
        ("1.1.2.02", "Duplicatas a receber", a, d),
        ("1.1.2.03", "(-) Perdas estimadas em créditos", a, c),
        ("1.1.2.04", "Adiantamentos a fornecedores", a, d),
        ("1.1.3", "Estoques", a, d),
        ("1.1.3.01", "Mercadorias para revenda", a, d),
        ("1.1.3.02", "Materiais de embalagem", a, d),
        ("1.1.3.03", "Mercadorias em trânsito", a, d),
        ("1.1.4", "Tributos a recuperar", a, d),
        ("1.1.4.01", "ICMS a recuperar", a, d),
        ("1.1.4.02", "PIS a recuperar", a, d),
        ("1.1.4.03", "COFINS a recuperar", a, d),
        ("1.1.4.04", "IRRF a compensar", a, d),
        ("1.2", "ATIVO NÃO CIRCULANTE", a, d),
        ("1.2.1", "Imobilizado", a, d),
        ("1.2.1.01", "Móveis e utensílios", a, d),
        ("1.2.1.02", "Equipamentos de informática", a, d),
        ("1.2.1.03", "Veículos", a, d),
        ("1.2.1.04", "(-) Depreciação acumulada", a, c),
        ("2", "PASSIVO", p, c),
        ("2.1", "PASSIVO CIRCULANTE", p, c),
        ("2.1.1", "Fornecedores", p, c),
        ("2.1.1.01", "Fornecedores nacionais", p, c),
        ("2.1.1.02", "Fornecedores de serviços", p, c),
        ("2.1.2", "Obrigações trabalhistas", p, c),
        ("2.1.2.01", "Salários a pagar", p, c),
        ("2.1.2.02", "INSS a recolher", p, c),
        ("2.1.2.03", "FGTS a recolher", p, c),
        ("2.1.2.04", "Provisão de férias", p, c),
        ("2.1.3", "Obrigações tributárias", p, c),
        ("2.1.3.01", "ICMS a recolher", p, c),
        ("2.1.3.02", "Simples Nacional a recolher", p, c),
        ("2.1.3.03", "ISS a recolher", p, c),
        ("2.2", "PASSIVO NÃO CIRCULANTE", p, c),
        ("2.2.1", "Empréstimos de longo prazo", p, c),
        ("2.2.1.01", "Financiamento de veículos", p, c),
        ("3", "PATRIMÔNIO LÍQUIDO", pl, c),
        ("3.1", "Capital social", pl, c),
        ("3.1.1", "Capital subscrito", pl, c),
        ("3.1.1.01", "Capital integralizado", pl, c),
        ("3.2", "Resultados acumulados", pl, c),
        ("3.2.1", "Lucros acumulados", pl, c),
        ("3.2.1.01", "Lucros de exercícios anteriores", pl, c),
        ("4", "RECEITAS", r, c),
        ("4.1", "Receita operacional bruta", r, c),
        ("4.1.1", "Venda de mercadorias", r, c),
        ("4.1.1.01", "Vendas no mercado interno", r, c),
        ("4.1.1.02", "Vendas a prazo", r, c),
        ("4.2", "Deduções da receita bruta", r, d),
        ("4.2.1", "Impostos sobre vendas", r, d),
        ("4.2.1.01", "ICMS sobre vendas", r, d),
        ("5", "DESPESAS", de, d),
        ("5.1", "Despesas operacionais", de, d),
        ("5.1.1", "Despesas administrativas", de, d),
        ("5.1.1.01", "Aluguel", de, d),
        ("5.1.1.02", "Energia elétrica", de, d),
        ("5.1.1.03", "Telefone e internet", de, d),
        ("5.1.1.04", "Material de escritório", de, d),
        ("5.1.1.05", "Honorários contábeis", de, d),
        ("5.1.2", "Despesas com pessoal", de, d),
        ("5.1.2.01", "Salários e ordenados", de, d),
        ("5.1.2.02", "Encargos sociais", de, d),
        ("5.2", "Custo das mercadorias vendidas", de, d),
        ("5.2.1", "CMV", de, d),
        ("5.2.1.01", "Custo das mercadorias vendidas", de, d),
    ]


def test_desempenho_em_plano_de_contas_realista():
    """Risco declarado do plano DL-032: mede `apurar_saldos` num plano de
    contas realista (73 contas, 4 níveis — a mesma base do §4.8 da direção
    de arte) com 60 lançamentos. **Mede a chamada isolada**, não a criação
    dos dados (a criação não é o caminho que um usuário percorre; medir os
    dois juntos mediria o SUBSTITUTO, não a propriedade — DE-060).

    Sem N+1: `apurar_balancete` já é 3 consultas fixas; este teste também
    conta as consultas para provar que `apurar_saldos` não adiciona uma
    consulta por conta."""
    empresa = _empresa("DL-032 Desempenho")
    plano = _plano_realista_73_contas_4_niveis()
    criadas = {}
    for codigo, nome, tipo, natureza in plano:
        pai = criadas.get(codigo.rsplit(".", 1)[0]) if "." in codigo else None
        analitica = codigo.count(".") == 3
        criadas[codigo] = _conta(
            empresa,
            codigo=codigo,
            nome=nome,
            tipo=tipo,
            natureza=natureza,
            pai=pai,
            aceita_lancamento=analitica,
        )
    assert len(criadas) == 73
    assert max(codigo.count(".") for codigo in criadas) + 1 == 4

    analiticas = [conta for conta in criadas.values() if conta.aceita_lancamento]
    sorteio = random.Random(20260920)  # semente fixa: mesmo resultado sempre
    for i in range(60):
        debitada, creditada = sorteio.sample(analiticas, 2)
        valor = Decimal(sorteio.randrange(1000, 900000)) / 100
        _lancar(
            empresa,
            date(2026, 3, 1 + i % 28),
            f"Lançamento sintético {i + 1:02d}",
            debitada,
            creditada,
            valor,
        )

    data_base = date(2026, 3, 28)
    with CaptureQueriesContext(connection) as capturadas:
        inicio = time.perf_counter()
        saldos = apurar_saldos(empresa=empresa, data_base=data_base)
        duracao = time.perf_counter() - inicio

    assert len(saldos["contas"]) == 73
    # Mesma classe de custo do Balancete (3 consultas fixas): tolerância de
    # até 6 para não acoplar este teste a um número exato de consultas
    # auxiliares do Django em si (savepoints etc.), mas reprovar qualquer
    # crescimento LINEAR com o número de contas (73 contas, teto bem abaixo
    # de 73).
    assert len(capturadas) <= 6, f"{len(capturadas)} consultas — indício de N+1"
    # Declaração DE-060: este número É a propriedade medida (o tempo da
    # CHAMADA, isolado da criação dos dados), não um substituto dela. O
    # valor observado nesta máquina, registrado no relatório de entrega,
    # ficou bem abaixo do teto — o teto aqui é generoso de propósito
    # (ambiente de CI pode ser mais lento que a máquina de quem mediu
    # primeiro), não uma meta de performance.
    assert duracao < 2.0, (
        f"apurar_saldos levou {duracao:.4f}s em 73 contas — acima do teto declarado"
    )
    print(
        f"\nDL-032 desempenho: apurar_saldos em 73 contas/4 níveis/60 lançamentos: "
        f"{duracao:.4f}s, {len(capturadas)} consultas"
    )
