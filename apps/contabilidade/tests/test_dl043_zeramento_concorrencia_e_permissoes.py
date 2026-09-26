"""Testes de risco alto da fatia 2 da DL-043 (zeramento do resultado):
idempotência/complemento, concorrência REAL, competência encerrada,
permissão (RC-102) no servidor e isolamento entre empresas/escritórios.

Os casos de referência calculados à mão (lucro, prejuízo, resultado zero,
só receitas, só despesas, retificadora, centavos, periodicidade) estão em
`test_dl043_zeramento_referencia.py`; este arquivo cobre o que resta do
critério 5 do plano DL-043 (idempotência, complemento e concorrência) e os
critérios 6 e 8 (competência encerrada, 403 sem gravar, isolamento).

Datas em 2026, entre janeiro e agosto — sempre no PASSADO em relação a
"hoje" (a suíte foi escrita em 2026-09-26), o que evita qualquer interação
com a faixa de data de LANÇAMENTO do RC-77 (01/01/2000 até hoje + 30 dias).
Dados 100% sintéticos, criados nos próprios testes.
"""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse

from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
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
    criar_lancamento,
    encerrar_competencia,
    registrar_parametro_contabil,
    zerar_resultado,
)
from apps.empresas.models import Empresa, ModoEscrituracao
from apps.empresas.services import EmpresaEmModoLivroCaixa
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


def _plano_de_contas(empresa):
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="3.1",
        nome="Receita de Serviços",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    despesa = Conta.objects.create(
        empresa=empresa,
        codigo="4.1",
        nome="Despesas Administrativas",
        tipo=TipoConta.DESPESA,
        natureza=NaturezaConta.DEVEDORA,
    )
    resultado = Conta.objects.create(
        empresa=empresa,
        codigo="2.9.1",
        nome="Resultado do Exercício",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    lucros = Conta.objects.create(
        empresa=empresa,
        codigo="2.9.2",
        nome="Lucros Acumulados",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    prejuizos = Conta.objects.create(
        empresa=empresa,
        codigo="2.9.3",
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


@pytest.fixture
def cenario():
    """Empresa com plano de contas mínimo e parâmetro contábil MENSAL
    vigente desde 2020 — cobre qualquer data usada nos testes deste
    arquivo sem precisar registrar vigência em cada um."""
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-043 concorrência", cnpj="11333555000199"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME Zeramento Ltda", cnpj="11444777000161"
    )
    contas = _plano_de_contas(empresa)
    gestor = _usuario_com_papel(Papel.GESTOR, escritorio, "gestor-dl043")
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


def _lancar_receita_e_despesa(cenario, *, data, receita_valor, despesa_valor):
    itens = []
    if receita_valor:
        itens += [
            {"conta": cenario["caixa"], "tipo": TipoPartida.DEBITO, "valor": receita_valor},
            {"conta": cenario["receita"], "tipo": TipoPartida.CREDITO, "valor": receita_valor},
        ]
    if despesa_valor:
        itens += [
            {"conta": cenario["despesa"], "tipo": TipoPartida.DEBITO, "valor": despesa_valor},
            {"conta": cenario["caixa"], "tipo": TipoPartida.CREDITO, "valor": despesa_valor},
        ]
    criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico="Movimento de teste",
        itens=itens,
        criado_por=cenario["gestor"],
    )


# ---------------------------------------------------------------------------
# Idempotência e complemento (critério 5 do plano)
# ---------------------------------------------------------------------------


def test_repetir_sem_movimento_novo_nao_gera_nada(cenario):
    """Chamar `zerar_resultado` duas vezes seguidas, sem nenhum lançamento
    novo entre as duas, não duplica nada: a segunda chamada encontra saldo
    zero em toda conta (o zeramento anterior já levou tudo a zero) e não
    grava lançamento nenhum."""
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 3, 31), receita_valor=Decimal("1000.00"), despesa_valor=None
    )

    primeira = zerar_resultado(
        empresa=cenario["empresa"], ano=2026, mes=3, usuario=cenario["gestor"]
    )
    assert primeira["criado_etapa1"] is True
    assert primeira["criado_etapa2"] is True

    total_antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()

    segunda = zerar_resultado(
        empresa=cenario["empresa"], ano=2026, mes=3, usuario=cenario["gestor"]
    )
    assert segunda["lancamento_etapa1"] is None
    assert segunda["criado_etapa1"] is False
    assert segunda["lancamento_etapa2"] is None
    assert segunda["criado_etapa2"] is False

    total_depois = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    assert total_depois == total_antes


def test_movimento_novo_no_periodo_ainda_aberto_gera_so_o_complemento(cenario):
    """Depois do primeiro zeramento, um lançamento NOVO na mesma competência
    (ainda aberta) faz a chamada seguinte gerar só a DIFERENÇA ainda não
    zerada — o "complemento" — nunca duplicar o que já foi zerado.

    Conta à mão: primeira rodada — receita 1.000,00, sem despesa: lucro de
    1.000,00 (etapa1 crédito 1.000 em Resultado; etapa2 transfere 1.000,00
    para Lucros Acumulados). Movimento novo: mais 500,00 de receita no
    MESMO mês. Segunda rodada deve gerar etapa1 com item de 500,00 na
    Receita (não 1.500,00) e etapa2 transferindo mais 500,00 (não 1.500,00)
    — o total acumulado em Lucros Acumulados ao final é 1.500,00.
    """
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 4, 30), receita_valor=Decimal("1000.00"), despesa_valor=None
    )
    primeira = zerar_resultado(
        empresa=cenario["empresa"], ano=2026, mes=4, usuario=cenario["gestor"]
    )
    assert primeira["lancamento_etapa1"].chave_idempotencia.endswith(":etapa1:0")
    assert primeira["lancamento_etapa2"].chave_idempotencia.endswith(":etapa2:0")

    # Movimento novo, competência ainda ABERTA (RC-57 exige recusa só para
    # competência ENCERRADA — este teste não encerra nada).
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 4, 30), receita_valor=Decimal("500.00"), despesa_valor=None
    )

    segunda = zerar_resultado(
        empresa=cenario["empresa"], ano=2026, mes=4, usuario=cenario["gestor"]
    )
    assert segunda["criado_etapa1"] is True
    assert segunda["lancamento_etapa1"].chave_idempotencia.endswith(":etapa1:1")
    itens_complemento = {
        item.conta_id: (item.tipo, item.valor) for item in segunda["lancamento_etapa1"].itens.all()
    }
    # O item da Receita no COMPLEMENTO é de 500,00 — não 1.500,00: a
    # `_saldo_assinado_ate` já lê o saldo ACUMULADO, e o zeramento anterior
    # já levou a Receita a zero, então o que resta agora é só o movimento
    # novo.
    assert itens_complemento[cenario["receita"].pk] == (TipoPartida.DEBITO, Decimal("500.00"))
    assert itens_complemento[cenario["resultado"].pk] == (TipoPartida.CREDITO, Decimal("500.00"))

    assert segunda["criado_etapa2"] is True
    assert segunda["lancamento_etapa2"].chave_idempotencia.endswith(":etapa2:1")
    itens_complemento2 = {
        item.conta_id: (item.tipo, item.valor) for item in segunda["lancamento_etapa2"].itens.all()
    }
    assert itens_complemento2[cenario["lucros"].pk] == (TipoPartida.CREDITO, Decimal("500.00"))

    # Total acumulado: 1.000,00 (primeira rodada) + 500,00 (complemento).
    total_lucros = sum(
        item.valor
        for lanc in LancamentoContabil.objects.filter(
            empresa=cenario["empresa"], chave_idempotencia__contains=":etapa2:"
        )
        for item in lanc.itens.filter(conta=cenario["lucros"])
    )
    assert total_lucros == Decimal("1500.00")


# ---------------------------------------------------------------------------
# Concorrência REAL (critério 5) — dois pedidos simultâneos no PostgreSQL
# resultam num único zeramento, nunca dois. `_travar_competencia_para_
# transicao` (o mesmo `SELECT ... FOR UPDATE` de `encerrar_competencia`)
# serializa as duas chamadas: a que perde a corrida só lê o estado depois
# que a primeira COMMITOU, e encontra saldo zero em tudo.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_concorrencia_real_dois_pedidos_produzem_um_unico_zeramento():
    """`django_db(transaction=True)` (sobrepõe o `pytestmark` do módulo, que
    é `django_db` comum): threads reais precisam de conexões PostgreSQL
    reais e de COMMIT de fato — o padrão que os testes de concorrência de
    `test_dl016_fatia1_fechamento_reabertura_entrega.py` e
    `test_bl40_bl41.py` já usam. Sem isto, o `TestCase` padrão embrulha
    tudo numa transação nunca commitada e as duas threads nem chegariam a
    disputar o `FOR UPDATE`.
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório DL-043 concorrência real", cnpj="11333555000280"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME Concorrência Ltda", cnpj="11444777000242"
    )
    contas = _plano_de_contas(empresa)
    gestor = get_user_model().objects.create_user(
        username="gestor-concorrencia-dl043",
        email="gestor-concorrencia-dl043@escritorio.com.br",
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
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 5, 31),
        historico="Receita de maio",
        itens=[
            {"conta": contas["caixa"], "tipo": TipoPartida.DEBITO, "valor": Decimal("2000.00")},
            {"conta": contas["receita"], "tipo": TipoPartida.CREDITO, "valor": Decimal("2000.00")},
        ],
        criado_por=gestor,
    )
    # A linha de `Competencia` já existe a esta altura — `criar_lancamento`,
    # acima, já a criou via `obter_ou_criar_competencia` na mesma transação
    # do lançamento de maio. Não recriar aqui (mesmo cuidado do BL-456/
    # `test_dl016_...`): se ela nascesse DENTRO da corrida, as duas threads
    # disputariam o `get_or_create`, um bloqueio real mas de OUTRA causa (o
    # INSERT concorrente), que confundiria a medição — e recriá-la agora
    # violaria a `UniqueConstraint(empresa, ano, mes)` à toa.
    assert Competencia.objects.filter(empresa=empresa, ano=2026, mes=5).exists()

    resultados = {}
    erros = {}
    barreira = threading.Barrier(2)

    def _chamar(nome):
        try:
            barreira.wait(timeout=5)
            resultados[nome] = zerar_resultado(empresa=empresa, ano=2026, mes=5, usuario=gestor)
        except Exception as exc:  # noqa: BLE001 — captura para reportar no assert, não silenciar
            erros[nome] = exc
        finally:
            connection.close()

    t1 = threading.Thread(target=_chamar, args=("t1",))
    t2 = threading.Thread(target=_chamar, args=("t2",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert erros == {}, erros
    assert set(resultados) == {"t1", "t2"}

    # Exatamente UM zeramento gravado para o período, nunca dois: a trava
    # de competência (`_travar_competencia_para_transicao`, FOR UPDATE)
    # serializa as duas chamadas, e quem perde a corrida encontra saldo
    # zero (a outra já zerou) e não grava nada.
    lancamentos_etapa1 = LancamentoContabil.objects.filter(
        empresa=empresa, chave_idempotencia__contains=":etapa1:"
    )
    lancamentos_etapa2 = LancamentoContabil.objects.filter(
        empresa=empresa, chave_idempotencia__contains=":etapa2:"
    )
    assert lancamentos_etapa1.count() == 1
    assert lancamentos_etapa2.count() == 1

    # Exatamente UMA das duas chamadas de fato criou os lançamentos; a
    # outra viu o no-op idempotente.
    criaram_etapa1 = [resultados[nome]["criado_etapa1"] for nome in ("t1", "t2")]
    assert sorted(criaram_etapa1) == [False, True]


# ---------------------------------------------------------------------------
# Competência encerrada (RC-57) — recusa ANTES de calcular qualquer saldo.
# ---------------------------------------------------------------------------


def test_competencia_encerrada_recusa_sem_gravar_nada(cenario):
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 6, 30), receita_valor=Decimal("800.00"), despesa_valor=None
    )
    encerrar_competencia(empresa=cenario["empresa"], ano=2026, mes=6, usuario=cenario["gestor"])
    competencia = Competencia.objects.get(empresa=cenario["empresa"], ano=2026, mes=6)
    assert competencia.estado == EstadoCompetencia.ENCERRADA

    total_antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()

    with pytest.raises(CompetenciaEncerrada):
        zerar_resultado(empresa=cenario["empresa"], ano=2026, mes=6, usuario=cenario["gestor"])

    total_depois = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    assert total_depois == total_antes
    # A correção de um período encerrado segue o estorno (RC-103), nunca
    # um zeramento por cima: nenhum novo `ParametroContabilEmpresa` nem
    # `LancamentoContabil` de zeramento apareceu.
    assert not LancamentoContabil.objects.filter(
        empresa=cenario["empresa"], chave_idempotencia__contains=":etapa1:"
    ).exists()


# ---------------------------------------------------------------------------
# Permissão RC-102 no SERVIDOR (403 sem gravar) e isolamento entre
# empresas/escritórios — pela API (`ZerarResultadoView`).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]
)
def test_papel_sem_permissao_recebe_403_sem_gravar(client, cenario, papel):
    """RC-102: só ADMINISTRADOR/GESTOR zeram o resultado — o mesmo par que
    fecha competência. Verificado NO SERVIDOR: o teste manda a requisição
    com o papel errado e confere que o BANCO não mudou (BL-211 — 403
    sozinho já enganou este projeto antes)."""
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 7, 31), receita_valor=Decimal("100.00"), despesa_valor=None
    )
    _autenticar(client, cenario["escritorio"], papel, f"sem-permissao-{papel}")

    total_antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    resposta = client.post(
        reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 7]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 403
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == total_antes


def test_administrador_consegue_zerar_pela_api(client, cenario):
    """Controle positivo do teste acima: o MESMO cenário, com papel
    autorizado, deve funcionar — sem isso, um 403 universal (bug que
    bloqueasse todo mundo) passaria disfarçado de "seguro"."""
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 8, 31), receita_valor=Decimal("300.00"), despesa_valor=None
    )
    _autenticar(client, cenario["escritorio"], Papel.ADMINISTRADOR, "administrador-dl043")

    resposta = client.post(
        reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 8]),
        data={},
        content_type="application/json",
    )
    assert resposta.status_code == 200
    assert resposta.json()["criado_etapa1"] is True
    assert resposta.json()["destino_etapa2"] == "lucros_acumulados"


def test_prevía_get_nao_grava_nada(client, cenario):
    """GET (prévia) devolve os valores que SERIAM lançados, sem gravar —
    critério da fatia 2."""
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 2, 28), receita_valor=Decimal("450.00"), despesa_valor=None
    )
    _autenticar(client, cenario["escritorio"], Papel.GESTOR, "gestor-previa-dl043")

    total_antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    resposta = client.get(reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 2]))
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["etapa1"]["itens"], corpo
    assert corpo["etapa2"]["destino"] == "lucros_acumulados"
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == total_antes


def test_isolamento_entre_escritorios_devolve_404(client, cenario):
    """Empresa de OUTRO escritório: 404, nunca 403 nem dado da outra
    empresa (`EmpresaEscopadaMixin.get_empresa()`)."""
    outro_escritorio = Escritorio.objects.create(
        nome="Outro escritório DL-043", cnpj="22333444000155"
    )
    _autenticar(client, outro_escritorio, Papel.ADMINISTRADOR, "administrador-outro-dl043")

    resposta = client.get(reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 3]))
    assert resposta.status_code == 404

    resposta_post = client.post(
        reverse("contabilidade:zeramento", args=[cenario["empresa"].pk, 2026, 3]),
        data={},
        content_type="application/json",
    )
    assert resposta_post.status_code == 404
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()


def test_isolamento_entre_empresas_do_mesmo_escritorio(cenario):
    """Zerar o resultado da empresa A não gera lançamento nem
    `ParametroContabilEmpresa` para a empresa B do MESMO escritório —
    ainda que as duas compartilhem escritório, contas e competências são
    por empresa."""
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["escritorio"], razao_social="Outra Empresa Ltda", cnpj="11444777000323"
    )
    _lancar_receita_e_despesa(
        cenario, data=date(2026, 3, 31), receita_valor=Decimal("900.00"), despesa_valor=None
    )
    zerar_resultado(empresa=cenario["empresa"], ano=2026, mes=3, usuario=cenario["gestor"])

    assert not LancamentoContabil.objects.filter(empresa=outra_empresa).exists()
    assert not ParametroContabilEmpresa.objects.filter(empresa=outra_empresa).exists()
    assert not Competencia.objects.filter(empresa=outra_empresa).exists()


# ---------------------------------------------------------------------------
# Empresa em modo livro-caixa (DL-038) — recusada, sem gravar nada.
# ---------------------------------------------------------------------------


def test_empresa_livro_caixa_recusa_zeramento():
    escritorio = Escritorio.objects.create(nome="Escritório livro-caixa", cnpj="11555666000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Livro Caixa Ltda",
        cnpj="11444777000404",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    gestor = get_user_model().objects.create_user(
        username="gestor-livro-caixa-dl043",
        email="gestor-livro-caixa-dl043@escritorio.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestor, escritorio=escritorio, papel=Papel.GESTOR
    )

    with pytest.raises(ParametroContabilInvalido):
        zerar_resultado(empresa=empresa, ano=2026, mes=3, usuario=gestor)

    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()


def test_registrar_parametro_contabil_recusa_empresa_livro_caixa():
    """Fatia 1: `registrar_parametro_contabil` também recusa — empresa em
    livro-caixa nunca deveria ter parâmetro de partidas dobradas gravado.
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório livro-caixa param.", cnpj="11555666000258"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Livro Caixa Parâmetro Ltda",
        cnpj="11444777000505",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )
    contas = _plano_de_contas(empresa)

    with pytest.raises((ParametroContabilInvalido, EmpresaEmModoLivroCaixa)):
        registrar_parametro_contabil(
            empresa=empresa,
            periodicidade_zeramento=PeriodicidadeZeramento.MENSAL,
            conta_resultado_do_exercicio=contas["resultado"],
            conta_lucros_acumulados=contas["lucros"],
            conta_prejuizos_acumulados=contas["prejuizos"],
            vigencia_inicio=date(2020, 1, 1),
        )
    assert not ParametroContabilEmpresa.objects.filter(empresa=empresa).exists()
