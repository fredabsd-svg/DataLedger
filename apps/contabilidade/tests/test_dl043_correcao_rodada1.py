"""Correção da rodada 1 de auditoria da DL-043 (REPROVADA — dois
bloqueadores de dano contábil).

Relatório: `docs/auditorias/2026-09-26-dl-043-rodada-1.md`. Decisão da
correção: **DE-078** (`docs/projeto/decisoes.md`) e **HI-25**
(`docs/projeto/requisitos.md`). Cada teste deste arquivo cita o achado
(B1-B10) ou o(s) mutante(s) (M...) que ele mata — a numeração é a da
seção "Casos de teste propostos" do relatório.

Datas em 2026, entre janeiro e agosto (hoje é 2026-09-26) — sempre no
PASSADO, exceto no caso 5b (mês futuro), que é o próprio objeto do teste.
Dados 100% sintéticos, criados nos próprios testes.
"""

import threading
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    ParametroContabilEmpresa,
    PeriodicidadeZeramento,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    CompetenciaEncerrada,
    ParametroContabilInvalido,
    VigenciaParametroContabilConflitante,
    ZeramentoForaDeOrdem,
    apurar_balancete,
    criar_lancamento,
    encerrar_competencia,
    encerrar_vigencia_de_parametro_contabil,
    pre_visualizar_zeramento,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _usuario_com_papel(papel, escritorio, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    if papel is not None:
        VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _autenticar(client, escritorio, papel, username):
    usuario = _usuario_com_papel(papel, escritorio, username)
    assert client.login(username=username, password="senha-forte-123")
    return usuario


def _plano_de_contas(empresa, *, sufixo_codigo=""):
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo=f"1.1{sufixo_codigo}",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo=f"3.1{sufixo_codigo}",
        nome="Receita de Serviços",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    despesa = Conta.objects.create(
        empresa=empresa,
        codigo=f"4.1{sufixo_codigo}",
        nome="Despesas Administrativas",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    resultado = Conta.objects.create(
        empresa=empresa,
        codigo=f"2.9.1{sufixo_codigo}",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    lucros = Conta.objects.create(
        empresa=empresa,
        codigo=f"2.9.2{sufixo_codigo}",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    prejuizos = Conta.objects.create(
        empresa=empresa,
        codigo=f"2.9.3{sufixo_codigo}",
        nome="(-) Prejuízos Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.DEVEDORA,
    )
    return {
        "caixa": caixa,
        "receita": receita,
        "despesa": despesa,
        "resultado": resultado,
        "lucros": lucros,
        "prejuizos": prejuizos,
    }


def _novo_cenario(nome, *, cnpj_sufixo):
    """Empresa nova, com plano de contas mínimo e parâmetro MENSAL vigente
    desde 2020 — usada pelos testes que precisam de empresas ISOLADAS
    entre si (concorrência entre rodadas, por exemplo)."""
    escritorio = Escritorio.objects.create(nome=f"Escritório {nome}", cnpj=f"1{cnpj_sufixo:013d}")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=f"{nome} Ltda", cnpj=f"2{cnpj_sufixo:013d}"
    )
    contas = _plano_de_contas(empresa)
    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, f"gestor-{cnpj_sufixo}")
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    return {"escritorio": escritorio, "empresa": empresa, "gestor": gestor, **contas}


@pytest.fixture
def cenario():
    return _novo_cenario("DL-043 correção", cnpj_sufixo=1)


def _lancar(empresa, *, data, debito, credito, valor, usuario):
    criar_lancamento(
        empresa=empresa,
        data=data,
        historico="Movimento de teste",
        itens=[
            {"conta": debito, "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": credito, "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
        criado_por=usuario,
    )


def _lancar_receita(cenario, data, valor):
    _lancar(
        cenario["empresa"],
        data=data,
        debito=cenario["caixa"],
        credito=cenario["receita"],
        valor=valor,
        usuario=cenario["gestor"],
    )


def _lancar_bypass_validacoes(empresa, *, data, historico, itens, usuario):
    """Grava um lançamento DIRETO pelo ORM, contornando `criar_lancamento`
    (inclusive a recusa de conta que não aceita lançamento) — simula um
    estado LEGADO (carga de dados antiga, `.update()` direto, importação
    por fora do produto). É exatamente o cenário que o achado B1 exige
    que o zeramento RECUSE, em vez de ignorar em silêncio."""
    lancamento = LancamentoContabil.objects.create(
        empresa=empresa, data=data, historico=historico, criado_por=usuario
    )
    for item in itens:
        ItemLancamento.objects.create(
            lancamento=lancamento, conta=item["conta"], tipo=item["tipo"], valor=item["valor"]
        )
    return lancamento


def _total_lucros(empresa, conta_lucros):
    return sum(
        item.valor
        for lanc in LancamentoContabil.objects.filter(
            empresa=empresa, chave_idempotencia__contains=":etapa2:"
        )
        for item in lanc.itens.filter(conta=conta_lucros)
    )


# ---------------------------------------------------------------------------
# Caso 1 — B1 (BLOQUEADOR): hierarquia "4" -> "4.1" -> "4.1.01", zerar pelo
# saldo PRÓPRIO — nunca o consolidado.
# ---------------------------------------------------------------------------


def test_b1_hierarquia_zera_pelo_saldo_proprio_sem_dobrar(cenario):
    """Conta à mão: 100,00 na raiz "4", 200,00 na filha "4.1" e 300,00 na
    neta "4.1.01" — todas ACEITAM lançamento (o estado PADRÃO do
    cadastro). Lucro esperado: exatamente 600,00 (nunca 1.200,00, que é o
    que a consolidação de B1 produzia: cada nível contava também o
    movimento dos descendentes)."""
    empresa = cenario["empresa"]
    raiz = Conta.objects.create(
        empresa=empresa,
        codigo="9",
        nome="Receita raiz",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    filha = Conta.objects.create(
        empresa=empresa,
        conta_pai=raiz,
        codigo="9.1",
        nome="Receita filha",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    neta = Conta.objects.create(
        empresa=empresa,
        conta_pai=filha,
        codigo="9.1.01",
        nome="Receita neta",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    for conta, valor in ((raiz, "100.00"), (filha, "200.00"), (neta, "300.00")):
        _lancar(
            empresa,
            data=date(2026, 3, 31),
            debito=cenario["caixa"],
            credito=conta,
            valor=valor,
            usuario=cenario["gestor"],
        )

    resultado = zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])
    assert resultado["destino_etapa2"] == "lucros_acumulados"
    total_lucros = sum(
        item.valor for item in resultado["lancamento_etapa2"].itens.filter(conta=cenario["lucros"])
    )
    assert total_lucros == Decimal("600.00")

    balancete = apurar_balancete(empresa=empresa, inicio=date(2026, 3, 31), fim=date(2026, 3, 31))
    saldos = {linha["conta"]: linha["saldo_final"] for linha in balancete["contas"]}
    assert saldos["9"] == Decimal("0")
    assert saldos["9.1"] == Decimal("0")
    assert saldos["9.1.01"] == Decimal("0")


def test_b1_sintetica_legada_com_saldo_proprio_recusa_sem_gravar(cenario):
    """Variante do caso 1: conta "9" marcada `aceita_lancamento=False`
    (sintética) mas com saldo PRÓPRIO diferente de zero (estado LEGADO,
    só alcançável por fora do caminho normal de escrituração). Esperado:
    `zerar_resultado` recusa com mensagem apontando a conta, banco
    inalterado."""
    empresa = cenario["empresa"]
    raiz = Conta.objects.create(
        empresa=empresa,
        codigo="9",
        nome="Receita sintética legada",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
        aceita_lancamento=False,
    )
    filha = Conta.objects.create(
        empresa=empresa,
        conta_pai=raiz,
        codigo="9.1",
        nome="Receita filha",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=cenario["caixa"],
        credito=filha,
        valor="50.00",
        usuario=cenario["gestor"],
    )
    _lancar_bypass_validacoes(
        empresa,
        data=date(2026, 3, 20),
        historico="Movimento legado direto na sintética",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": raiz, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
        usuario=cenario["gestor"],
    )

    total_antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    with pytest.raises(ParametroContabilInvalido, match="9"):
        zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_antes


# ---------------------------------------------------------------------------
# Caso 2 — B2 (BLOQUEADOR): fora de ordem.
# ---------------------------------------------------------------------------


def test_b2_zerar_fora_de_ordem_e_recusado_sem_gravar(cenario):
    """100,00 em março e 50,00 em abril; zera abril PRIMEIRO. Zerar março
    DEPOIS é recusado (`ZeramentoForaDeOrdem`, 409), banco inalterado.

    Conta à mão para o Lucros esperado: `zerar_resultado` lê o saldo
    ACUMULADO até a data final — o zeramento de abril, rodado ANTES do de
    março, já lê o saldo acumulado até 30/04, que inclui os 100,00 de
    março (ainda não zerados) MAIS os 50,00 de abril = 150,00, e zera tudo
    de uma vez (nenhum dinheiro perdido — é assim que o desenho evita
    contar em dobro mesmo fora de ordem, quando o período POSTERIOR
    "alcança" o residual do anterior). Por isso a tentativa de zerar março
    DEPOIS encontraria o mesmo movimento já zerado (recusada), e o Lucros
    final é 150,00 — não 50,00.
    """
    empresa = cenario["empresa"]
    _lancar_receita(cenario, date(2026, 3, 31), "100.00")
    _lancar_receita(cenario, date(2026, 4, 30), "50.00")
    resultado_abril = zerar_resultado(empresa=empresa, ano=2026, mes=4, usuario=cenario["gestor"])
    total_lucros_apos_abril = sum(
        item.valor
        for item in resultado_abril["lancamento_etapa2"].itens.filter(conta=cenario["lucros"])
    )
    assert total_lucros_apos_abril == Decimal("150.00")

    total_antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    with pytest.raises(ZeramentoForaDeOrdem):
        zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_antes

    # Nenhum lançamento novo — o total continua 150,00, nunca 200,00 (que
    # seria a duplicidade que a recusa existe para impedir).
    assert _total_lucros(empresa, cenario["lucros"]) == Decimal("150.00")


# ---------------------------------------------------------------------------
# Caso 3 — B2 (BLOQUEADOR): complemento tardio depois de período posterior.
# ---------------------------------------------------------------------------


def test_b2_complemento_tardio_depois_de_periodo_posterior_e_recusado(cenario):
    """Sequência do achado B2: (1) 100,00 em março, zera março; (2) 50,00
    em abril, zera abril; (3) lançamento tardio de 30,00 em 20/03 (março
    ainda aberto); (4) zera maio — o resíduo de 30,00 entra em maio,
    corretamente; (5) pedir o complemento de março DEPOIS disso é
    recusado (`ZeramentoForaDeOrdem`) — sem isso, o resíduo de 30,00 seria
    zerado DUAS VEZES (uma em maio, outra no complemento de março).
    Lucros final: 100 + 50 + 30 = 180,00, nunca 210,00."""
    empresa = cenario["empresa"]
    _lancar_receita(cenario, date(2026, 3, 31), "100.00")
    zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])

    _lancar_receita(cenario, date(2026, 4, 30), "50.00")
    zerar_resultado(empresa=empresa, ano=2026, mes=4, usuario=cenario["gestor"])

    _lancar_receita(cenario, date(2026, 3, 20), "30.00")

    resultado_maio = zerar_resultado(empresa=empresa, ano=2026, mes=5, usuario=cenario["gestor"])
    assert resultado_maio["criado_etapa1"] is True

    total_antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    with pytest.raises(ZeramentoForaDeOrdem):
        zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_antes

    assert _total_lucros(empresa, cenario["lucros"]) == Decimal("180.00")

    balancete = apurar_balancete(empresa=empresa, inicio=date(2026, 5, 31), fim=date(2026, 5, 31))
    saldo_receita = next(
        linha["saldo_final"]
        for linha in balancete["contas"]
        if linha["conta"] == cenario["receita"].codigo
    )
    assert saldo_receita == Decimal("0")


# ---------------------------------------------------------------------------
# Caso 4 — B2 (BLOQUEADOR): concorrência entre meses DIFERENTES, 15 rodadas
# reais no PostgreSQL. A trava de EMPRESA (DE-078 item 3) é o que serializa
# março e abril — a trava de competência sozinha NÃO bastava (a auditoria
# mediu 15 de 15 rodadas erradas sem ela).
#
# ⚠️ **O resultado CORRETO de duas threads concorrentes NÃO é "as duas
# sempre sucedem"** — é "o dinheiro nunca é contado em dobro, e nenhuma das
# duas levanta um erro que não seja `ZeramentoForaDeOrdem`". Qual das duas
# WINS a corrida pela trava de empresa é não determinístico: se ABRIL
# comitar primeiro, seu cálculo já lê o saldo ACUMULADO até 30/04 — que
# inclui o resíduo de março, ainda não zerado — e zera os 150,00 de uma
# vez só; a tentativa de MARÇO, que roda depois, encontra o mesmo
# movimento já zerado e é corretamente RECUSADA (`ZeramentoForaDeOrdem`)
# para não contar em dobro. Se MARÇO comitar primeiro, as duas sucedem
# separadamente (100 + 50). As DUAS ordens são seguras; o que a correção
# do B2 proíbe é qualquer ordem que produza um total DIFERENTE de 150,00,
# ou uma excepção que não seja essa recusa esperada.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_b2_concorrencia_entre_meses_diferentes_nunca_conta_em_dobro():
    falhas = []
    for rodada in range(15):
        escritorio = Escritorio.objects.create(
            nome=f"Escritório B2 concorrência {rodada}", cnpj=f"9{rodada:013d}"
        )
        empresa = Empresa.objects.create(
            escritorio=escritorio,
            razao_social=f"B2 Concorrência {rodada} Ltda",
            cnpj=f"8{rodada:013d}",
        )
        contas = _plano_de_contas(empresa)
        gestor = get_user_model().objects.create_user(
            username=f"gestor-b2-{rodada}",
            email=f"gestor-b2-{rodada}@escritorio.com.br",
            password="senha-forte-123",
        )
        registrar_parametro_contabil(
            empresa=empresa,
            periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
            conta_resultado_do_exercicio=contas["resultado"],
            conta_lucros_acumulados=contas["lucros"],
            conta_prejuizos_acumulados=contas["prejuizos"],
            vigencia_inicio=date(2020, 1, 1),
            usuario=gestor,
        )
        _lancar(
            empresa,
            data=date(2026, 3, 31),
            debito=contas["caixa"],
            credito=contas["receita"],
            valor="100.00",
            usuario=gestor,
        )
        _lancar(
            empresa,
            data=date(2026, 4, 30),
            debito=contas["caixa"],
            credito=contas["receita"],
            valor="50.00",
            usuario=gestor,
        )

        erros = {}
        barreira = threading.Barrier(2)

        def _chamar(mes, nome, empresa=empresa, gestor=gestor, erros=erros, barreira=barreira):
            try:
                barreira.wait(timeout=5)
                zerar_resultado(empresa=empresa, ano=2026, mes=mes, usuario=gestor)
            except Exception as exc:  # noqa: BLE001 — reportado, nunca silenciado
                erros[nome] = exc  # noqa: B023 — `erros` é vinculado por padrão de parâmetro acima
            finally:
                connection.close()

        t1 = threading.Thread(target=_chamar, args=(3, "marco"))
        t2 = threading.Thread(target=_chamar, args=(4, "abril"))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Só `ZeramentoForaDeOrdem` é um resultado ACEITÁVEL de erro — é a
        # recusa correta de quem perde a corrida contra um período
        # posterior que já absorveu o resíduo (ver a nota acima). Qualquer
        # OUTRA exceção é falha real.
        erros_inesperados = {
            nome: exc for nome, exc in erros.items() if not isinstance(exc, ZeramentoForaDeOrdem)
        }
        if erros_inesperados:
            falhas.append((rodada, "erro inesperado", erros_inesperados))
            continue

        total_lucros = _total_lucros(empresa, contas["lucros"])
        if total_lucros != Decimal("150.00"):
            falhas.append(
                (rodada, "lucros incorretos (dinheiro contado em dobro ou perdido)", total_lucros)
            )

    assert falhas == [], f"{len(falhas)} de 15 rodadas fora do esperado: {falhas}"


# ---------------------------------------------------------------------------
# Caso 5 — B3 (ALTA): quatro 500 previsíveis viram 400/409.
# ---------------------------------------------------------------------------


def test_b3_5a_duzentas_contas_de_resultado_divide_a_etapa1_sem_500(client, cenario):
    """DE-078 item 5: mais de 199 contas de receita/despesa com saldo faz a
    etapa 1 ser DIVIDIDA em vários lançamentos (nunca 500 por estourar o
    teto de partidas do RC-79)."""
    empresa = cenario["empresa"]
    quantidade = 205
    for indice in range(quantidade):
        conta = Conta.objects.create(
            empresa=empresa,
            codigo=f"5.{indice:04d}",
            nome=f"Receita {indice}",
            tipo=TipoConta.RECEITA,
            natureza=NaturezaConta.CREDORA,
        )
        _lancar(
            empresa,
            data=date(2026, 3, 31),
            debito=cenario["caixa"],
            credito=conta,
            valor="1.00",
            usuario=cenario["gestor"],
        )

    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-b3-5a")
    resposta = client.post(
        reverse("contabilidade:zeramento", args=[empresa.pk, 2026, 3]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert len(corpo["lancamentos_etapa1"]) == 2, corpo["lancamentos_etapa1"]
    assert corpo["destino_etapa2"] == "lucros_acumulados"

    total_lucros = _total_lucros(empresa, cenario["lucros"])
    assert total_lucros == Decimal(quantidade) * Decimal("1.00")

    balancete = apurar_balancete(empresa=empresa, inicio=date(2026, 3, 31), fim=date(2026, 3, 31))
    saldos = {linha["conta"]: linha["saldo_final"] for linha in balancete["contas"]}
    assert saldos["5.0000"] == Decimal("0")
    assert saldos[f"5.{quantidade - 1:04d}"] == Decimal("0")


def test_b3_5b_mes_futuro_e_400_sem_gravar(client, cenario):
    """HI-25: período ainda não terminado — 400, nunca 500, e nunca
    aceito como "hoje é passado o suficiente"."""
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-b3-5b")
    total_antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    resposta = client.post(
        reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 11]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 400, resposta.content
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == total_antes


def test_b3_5c_chave_ja_ocupada_e_409_sem_gravar(client, cenario, monkeypatch):
    """DE-078 item 6/item 3: a chave que a etapa 1 usaria já existe, com
    conteúdo DIFERENTE — `ChaveIdempotenciaConflitante` vira 409, nunca
    500 (achado B3).

    ⚠️ **Por que precisa de `monkeypatch`, e isto é um efeito COLATERAL
    correto das outras correções, não um artifício:** depois da correção
    de `_proximo_complemento` (que agora avança para o PRÓXIMO número
    livre, nunca reutiliza um já gravado) e da trava por empresa (B2(b)),
    uma colisão de chave para o zeramento deixou de ser alcançável por
    QUALQUER caminho legítimo — nem sequencial nem concorrente: o sistema
    sempre escolhe uma chave livre antes de gravar. O `except
    ChaveIdempotenciaConflitante` na view continua sendo defesa em
    profundidade (para o dia em que outro código grave nessa chave por
    fora, ou para um bug futuro em `_proximo_complemento`) — este teste
    verifica ESSA defesa diretamente, forçando `_proximo_complemento` a
    devolver um número já ocupado, em vez de tentar (e não conseguir)
    reproduzir a colisão pela via normal.
    """
    empresa = cenario["empresa"]
    _lancar_receita(cenario, date(2026, 3, 31), "100.00")
    lancamento_ocupante = _lancar_bypass_validacoes(
        empresa,
        data=date(2026, 3, 31),
        historico="Chave de zeramento ocupada por fora, com conteúdo diferente",
        itens=[
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("1.00")},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal("1.00")},
        ],
        usuario=cenario["gestor"],
    )
    LancamentoContabil.objects.filter(pk=lancamento_ocupante.pk).update(
        chave_idempotencia=f"zeramento:{empresa.pk}:2026-03:etapa1:0"
    )

    from apps.contabilidade import services as contabilidade_services

    monkeypatch.setattr(contabilidade_services, "_proximo_complemento", lambda **kwargs: 0)

    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-b3-5c")
    total_antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    resposta = client.post(
        reverse("contabilidade:zeramento", args=[empresa.pk, 2026, 3]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 409, resposta.content
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_antes


@pytest.mark.django_db(transaction=True)
def test_b3_5d_lock_timeout_real_na_empresa_e_409_sem_500():
    """`lock_timeout` real (1210ms, `config/settings.py`) estourado na
    trava de EMPRESA — `EmpresaTravadaPorOutraOperacao` (409), nunca o
    `OperationalError` cru que a auditoria mediu vazando como 500."""
    escritorio = Escritorio.objects.create(nome="Escritório B3 lock real", cnpj="71111111000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="B3 Lock Real Ltda", cnpj="71111111000281"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username="gestor-b3-5d", email="gestor-b3-5d@escritorio.com.br", password="senha-forte-123"
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2026, 3, 31),
        debito=contas["caixa"],
        credito=contas["receita"],
        valor="100.00",
        usuario=gestor,
    )

    segurando_o_lock = threading.Event()

    def segurar_for_update_alem_do_lock_timeout():
        with transaction.atomic():
            Empresa.objects.select_for_update().get(pk=empresa.pk)
            segurando_o_lock.set()
            time.sleep(2.0)
        connection.close()

    resultado = {}

    def zerar():
        assert segurando_o_lock.wait(timeout=5)
        try:
            zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=gestor)
        except Exception as exc:  # noqa: BLE001 — capturado para o assert, não silenciado
            resultado["erro"] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=segurar_for_update_alem_do_lock_timeout)
    t2 = threading.Thread(target=zerar)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert "erro" in resultado, (
        "esperava EmpresaTravadaPorOutraOperacao, nenhuma exceção foi levantada"
    )
    from apps.contabilidade.services import EmpresaTravadaPorOutraOperacao

    assert isinstance(resultado["erro"], EmpresaTravadaPorOutraOperacao)
    assert not LancamentoContabil.objects.filter(
        empresa=empresa, chave_idempotencia__contains=":etapa1:"
    ).exists()


# ---------------------------------------------------------------------------
# Caso 6 — B4 (MÉDIA): prefixo de chave reservado.
# ---------------------------------------------------------------------------


def test_b4_chave_reservada_e_400_e_nao_bloqueia_o_gestor(client, cenario):
    """ANALISTA tenta forjar a marca de zeramento por `POST .../lancamentos/`
    — 400, banco inalterado. Depois, o zeramento e o registro de vigência
    do GESTOR continuam funcionando normalmente (a marca não ficou
    bloqueada)."""
    empresa = cenario["empresa"]
    _lancar_receita(cenario, date(2026, 3, 31), "100.00")

    _usuario_com_papel(Papel.ANALISTA, cenario["escritorio"], "analista-b4")
    assert client.login(username="analista-b4", password="senha-forte-123")

    total_antes = LancamentoContabil.objects.filter(empresa=empresa).count()
    resposta = client.post(
        reverse("contabilidade:lancamentos", args=[empresa.pk]),
        data={
            "data": "2026-03-31",
            "historico": "Lançamento forjado como zeramento",
            "itens": [
                {"conta": cenario["caixa"].pk, "tipo": "debito", "valor": "1.00"},
                {"conta": cenario["receita"].pk, "tipo": "credito", "valor": "1.00"},
            ],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY=f"zeramento:{empresa.pk}:2026-03:etapa1:0",
    )
    assert resposta.status_code == 400, resposta.content
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_antes

    client.logout()
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-b4")
    resposta_zeramento = client.post(
        reverse("contabilidade:zeramento", args=[empresa.pk, 2026, 3]),
        data={},
        content_type="application/json",
    )
    assert resposta_zeramento.status_code == 200, resposta_zeramento.content
    assert resposta_zeramento.json()["criado_etapa1"] is True


# ---------------------------------------------------------------------------
# Caso 7 — M16/M17, B8: trilha com IP.
# ---------------------------------------------------------------------------


def test_b8_trilha_do_zeramento_tem_ip_usuario_e_escritorio(client, cenario):
    """M16 (registrar() removido do zeramento) e B8 (trilha sem IP): depois
    do POST, um `RegistroAuditoria` de `zeramento.resultado` existe, com
    usuário, escritório e `endereco_ip` preenchidos."""
    empresa = cenario["empresa"]
    _lancar_receita(cenario, date(2026, 3, 31), "100.00")
    gestor = _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-b8")

    resposta = client.post(
        reverse("contabilidade:zeramento", args=[empresa.pk, 2026, 3]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content

    registro = RegistroAuditoria.objects.filter(acao="zeramento.resultado").order_by("-id").first()
    assert registro is not None
    assert registro.usuario_id == gestor.pk
    assert registro.escritorio_id == cenario["escritorio"].pk
    assert registro.endereco_ip, "endereco_ip não foi preenchido na trilha do zeramento"
    assert registro.detalhes.get("criado_etapa1") is True


def test_m17_trilha_do_parametro_contabil_e_gravada():
    """M17 (registrar() removido do registro de parâmetro): depois do
    POST de `parametros-contabeis`, um `RegistroAuditoria` de
    `parametro_contabil.vigencia_registrada` existe."""
    escritorio = Escritorio.objects.create(nome="Escritório M17", cnpj="61111111000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="M17 Ltda", cnpj="61111111000281"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username="gestor-m17", email="gestor-m17@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestor, escritorio=escritorio, papel=Papel.GESTOR
    )

    parametro = registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    registro = RegistroAuditoria.objects.filter(
        acao="parametro_contabil.vigencia_registrada", objeto_id=str(parametro.pk)
    ).first()
    assert registro is not None
    assert registro.usuario_id == gestor.pk
    assert registro.escritorio_id == escritorio.pk


# ---------------------------------------------------------------------------
# Caso 8 — M22: periodicidade anual recusa CADA mês de 1 a 11.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mes", list(range(1, 12)))
def test_m22_anual_recusa_cada_mes_diferente_de_dezembro(mes):
    escritorio = Escritorio.objects.create(nome=f"Escritório M22 mes{mes}", cnpj=f"5{mes:013d}")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=f"M22 mes{mes} Ltda", cnpj=f"4{mes:013d}"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username=f"gestor-m22-{mes}",
        email=f"gestor-m22-{mes}@escritorio.com.br",
        password="senha-forte-123",
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.ANUAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    with pytest.raises(ParametroContabilInvalido):
        pre_visualizar_zeramento(empresa=empresa, ano=2025, mes=mes)
    with pytest.raises(ParametroContabilInvalido):
        zerar_resultado(empresa=empresa, ano=2025, mes=mes, usuario=gestor)
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


def test_m22_anual_aceita_dezembro():
    escritorio = Escritorio.objects.create(nome="Escritório M22 dezembro", cnpj="59999999000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="M22 Dezembro Ltda", cnpj="49999999000281"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username="gestor-m22-dez",
        email="gestor-m22-dez@escritorio.com.br",
        password="senha-forte-123",
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.ANUAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    _lancar(
        empresa,
        data=date(2025, 6, 15),
        debito=contas["caixa"],
        credito=contas["receita"],
        valor="900.00",
        usuario=gestor,
    )
    resultado = zerar_resultado(empresa=empresa, ano=2025, mes=12, usuario=gestor)
    assert resultado["criado_etapa1"] is True


# ---------------------------------------------------------------------------
# Caso 9 — M12: vigência com `vigencia_fim`, sem sucessora.
# ---------------------------------------------------------------------------


def test_m12_zerar_apos_vigencia_fim_sem_sucessora_e_recusado():
    """Mensal com `vigencia_fim=31/05` e SEM vigência sucessora: zerar
    junho (data final 30/06, depois do fim da vigência) é recusado por
    "sem parâmetro vigente" — não pode ignorar `vigencia_fim`."""
    escritorio = Escritorio.objects.create(nome="Escritório M12", cnpj="31111111000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="M12 Ltda", cnpj="31111111000281"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username="gestor-m12", email="gestor-m12@escritorio.com.br", password="senha-forte-123"
    )
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
        conta_resultado_do_exercicio=contas["resultado"],
        conta_lucros_acumulados=contas["lucros"],
        conta_prejuizos_acumulados=contas["prejuizos"],
        vigencia_inicio=date(2020, 1, 1),
        usuario=gestor,
    )
    parametro = ParametroContabilEmpresa.objects.get(empresa=empresa)
    parametro.vigencia_fim = date(2026, 5, 31)
    parametro.save(update_fields=["vigencia_fim"])

    with pytest.raises(ParametroContabilInvalido, match="vigente"):
        zerar_resultado(empresa=empresa, ano=2026, mes=6, usuario=gestor)
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Caso 10 — M20: encerrar vigência com início futuro.
# ---------------------------------------------------------------------------


def test_m20_encerrar_vigencia_com_inicio_futuro_e_409_sem_gravar(cenario):
    """Uma vigência aberta cujo `vigencia_inicio` só começa no futuro não
    pode ser encerrada HOJE (intervalo invertido) — 409, banco
    inalterado."""
    empresa = cenario["empresa"]
    # Data fixa, bem no futuro — não há teto de `vigencia_inicio` para
    # parâmetro contábil (ao contrário do regime tributário, RC-85): o
    # plano não pediu essa restrição, e este teste só precisa de UMA
    # vigência aberta cujo início ainda não chegou.
    inicio_futuro = date(2099, 1, 1)
    registrar_parametro_contabil(
        empresa=empresa,
        periodicidade_zeramento=PeriodicidadeZeramento.TRIMESTRAL,
        conta_resultado_do_exercicio=cenario["resultado"],
        conta_lucros_acumulados=cenario["lucros"],
        conta_prejuizos_acumulados=cenario["prejuizos"],
        vigencia_inicio=inicio_futuro,
        usuario=cenario["gestor"],
    )
    vigencia_fim_antes = ParametroContabilEmpresa.objects.get(
        empresa=empresa, vigencia_inicio=inicio_futuro
    ).vigencia_fim
    assert vigencia_fim_antes is None

    with pytest.raises(VigenciaParametroContabilConflitante):
        encerrar_vigencia_de_parametro_contabil(empresa=empresa, usuario=cenario["gestor"])

    parametro_depois = ParametroContabilEmpresa.objects.get(
        empresa=empresa, vigencia_inicio=inicio_futuro
    )
    assert parametro_depois.vigencia_fim is None


# ---------------------------------------------------------------------------
# Caso 11 — M4: competência encerrada SEM NADA a zerar.
# ---------------------------------------------------------------------------


def test_m4_competencia_encerrada_sem_movimento_recusa_sem_trilha_nem_gravacao(cenario):
    """M4 (checagem de estado ABERTA removida de `zerar_resultado`):
    competência SEM NENHUM movimento, encerrada, e então `zerar_resultado`
    chamado — como não há saldo nenhum para zerar, `criar_lancamento`
    NUNCA seria chamado (nada o impediria de "suceder" silenciosamente
    sem a checagem de estado). Esperado: `CompetenciaEncerrada`, nenhum
    `RegistroAuditoria` de `zeramento.resultado` novo, nenhum
    `LancamentoContabil` gravado."""
    empresa = cenario["empresa"]
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=3)
    assert competencia.estado == EstadoCompetencia.ENCERRADA

    total_trilha_antes = RegistroAuditoria.objects.filter(acao="zeramento.resultado").count()
    total_lancamentos_antes = LancamentoContabil.objects.filter(empresa=empresa).count()

    with pytest.raises(CompetenciaEncerrada):
        zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=cenario["gestor"])

    assert (
        RegistroAuditoria.objects.filter(acao="zeramento.resultado").count() == total_trilha_antes
    )
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == total_lancamentos_antes


# ---------------------------------------------------------------------------
# Caso 12 — M24: conta de outra empresa devolve a MESMA mensagem que uma
# conta inexistente (nunca permite enumerar ids de outra empresa).
# ---------------------------------------------------------------------------


def test_m24_conta_de_outra_empresa_tem_a_mesma_mensagem_que_conta_inexistente(client, cenario):
    """`_conta_da_empresa_ou_400` (views.py) precisa devolver o MESMO
    texto para "id não existe" e "id existe, mas é de outra empresa" —
    distinguir os dois confirmaria a um cliente sem acesso que aquele id
    existe em outra empresa (vazamento de enumeração)."""
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"],
        razao_social="Outra Empresa M24 Ltda",
        cnpj="41111111000100",
    )
    conta_de_outra_empresa = Conta.objects.create(
        empresa=outra_empresa,
        codigo="2.9.9",
        nome="Resultado de outra empresa",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-m24")

    def _corpo(conta_resultado_id):
        return {
            "periodicidade_zeramento": "mensal",
            "conta_resultado_do_exercicio": conta_resultado_id,
            "conta_lucros_acumulados": cenario["lucros"].pk,
            "conta_prejuizos_acumulados": cenario["prejuizos"].pk,
            "vigencia_inicio": "2030-01-01",
        }

    url = reverse("contabilidade:parametros-contabeis", args=[cenario["empresa"].pk])
    resposta_inexistente = client.post(url, data=_corpo(999999), content_type="application/json")
    resposta_outra_empresa = client.post(
        url, data=_corpo(conta_de_outra_empresa.pk), content_type="application/json"
    )

    assert resposta_inexistente.status_code == 400
    assert resposta_outra_empresa.status_code == 400
    assert resposta_inexistente.json() == resposta_outra_empresa.json()
    assert not ParametroContabilEmpresa.objects.filter(
        empresa=cenario["empresa"], vigencia_inicio=date(2030, 1, 1)
    ).exists()


# ---------------------------------------------------------------------------
# Caso 13 — B5: número de consultas CONSTANTE em relação ao número de
# contas de resultado (correção do cálculo QUADRÁTICO).
# ---------------------------------------------------------------------------


def test_b5_numero_de_consultas_e_constante_com_o_numero_de_contas(cenario):
    """B5 (correção do cálculo QUADRÁTICO): antes desta correção,
    `_calcular_zeramento` chamava `apurar_balancete` (3 consultas) UMA VEZ
    POR CONTA de receita/despesa — o número de consultas crescia com o
    número de contas. Agora é UMA chamada só, para todas as contas; o
    número de consultas de `pre_visualizar_zeramento` não deve mudar
    entre 10 e 50 contas de resultado."""
    from django.test.utils import CaptureQueriesContext

    empresa = cenario["empresa"]

    def _preparar(quantidade, sufixo):
        for indice in range(quantidade):
            conta = Conta.objects.create(
                empresa=empresa,
                codigo=f"7.{sufixo}.{indice:04d}",
                nome=f"Receita B5 {sufixo} {indice}",
                tipo=TipoConta.RECEITA,
                natureza=NaturezaConta.CREDORA,
            )
            _lancar(
                empresa,
                data=date(2026, 1, 31),
                debito=cenario["caixa"],
                credito=conta,
                valor="1.00",
                usuario=cenario["gestor"],
            )

    _preparar(10, "a")
    with CaptureQueriesContext(connection) as capturado_10:
        pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    numero_de_consultas_10 = len(capturado_10.captured_queries)

    _preparar(40, "b")  # total 50 contas de resultado
    with CaptureQueriesContext(connection) as capturado_50:
        pre_visualizar_zeramento(empresa=empresa, ano=2026, mes=1)
    numero_de_consultas_50 = len(capturado_50.captured_queries)

    assert numero_de_consultas_10 == numero_de_consultas_50, (
        "o número de consultas cresceu com o número de contas — voltou o "
        f"cálculo quadrático do B5 ({numero_de_consultas_10} -> {numero_de_consultas_50})"
    )
