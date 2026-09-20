"""Testes da FATIA 1 da DL-016 — trava de competência encerrada, NO SERVIDOR.

Cada teste referencia o critério de aceite numerado da seção "Critérios de
aceite da FATIA 1" do plano
`docs/planos/DL-016-competencia-e-fechamento.md`. Dados 100% sintéticos,
criados nos próprios testes.

Datas usadas nos meses de competência ficam em 2026, entre janeiro e agosto
— sempre no PASSADO em relação a "hoje" (2026-09-20 no momento em que esta
etapa foi escrita), o que evita qualquer interação acidental com a faixa de
data de LANÇAMENTO do RC-77 (01/01/2000 até hoje + 30 dias). Fechar/reabrir/
entregar uma competência não tem essa faixa — só o LANÇAMENTO tem —, mas
manter os meses no passado deixa os cenários inequívocos de ler.
"""

import threading
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade import services as contabilidade_services
from apps.contabilidade.models import (
    Competencia,
    Conta,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.services import (
    CompetenciaEncerrada,
    CompetenciaJaEntregue,
    CompetenciaOperacaoInvalida,
    CompetenciaOperacaoRecusada,
    criar_lancamento,
    encerrar_competencia,
    estornar_lancamento,
    marcar_competencia_como_entregue,
    reabrir_competencia,
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


@pytest.fixture
def cenario():
    """Uma empresa com plano de contas mínimo, pronta para lançar."""
    escritorio = Escritorio.objects.create(nome="Escritório DL-016 F1", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="ACME LTDA", cnpj="11.444.777/0001-61"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital Social",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "caixa": caixa,
        "capital": capital,
    }


def _lancar(empresa, caixa, capital, data, historico="Lançamento de teste", criado_por=None):
    return criar_lancamento(
        empresa=empresa,
        data=data,
        historico=historico,
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
        criado_por=criado_por,
    )


# ---------------------------------------------------------------------------
# Critério 1 — lançar em competência encerrada é recusado NO SERVIDOR, 409,
# com mensagem que diz qual competência está fechada. Teste de serviço E de
# requisição HTTP autenticada (lição do BL-211).
# ---------------------------------------------------------------------------


def test_criterio1_servico_recusa_lancamento_em_competencia_encerrada(cenario):
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c1-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=gestor)

    with pytest.raises(CompetenciaEncerrada) as excinfo:
        _lancar(empresa, caixa, capital, date(2026, 3, 10))

    mensagem = str(excinfo.value)
    assert "03/2026" in mensagem
    assert "encerrada" in mensagem
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


def test_criterio1_api_recusa_lancamento_em_competencia_encerrada_com_409(client, cenario):
    """BL-211: a garantia precisa ser medida por REQUISIÇÃO HTTP, não só de serviço."""
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c1-api-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=3, usuario=gestor)

    client.login(username="c1-api-gestor", password="senha-forte-123")
    response = client.post(
        reverse("contabilidade:lancamentos", args=[empresa.id]),
        data={
            "data": "2026-03-10",
            "historico": "Tentativa em mês fechado",
            "itens": [
                {"conta": caixa.id, "tipo": "debito", "valor": "50.00"},
                {"conta": capital.id, "tipo": "credito", "valor": "50.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 409
    assert "03/2026" in response.json()["detail"]
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


# ---------------------------------------------------------------------------
# Critério 2 — estorno também é recusado quando CAIRIA em competência
# encerrada. O que decide é a competência do ESTORNO (data de hoje, nunca a
# do original) — RC-57, confirmado pelo Fred: original fechado + estorno em
# mês aberto PASSA.
# ---------------------------------------------------------------------------


def test_criterio2_estorno_recusado_quando_a_competencia_de_hoje_esta_encerrada(client, cenario):
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    hoje = timezone.localdate()
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c2-gestor")

    original = _lancar(empresa, caixa, capital, hoje, criado_por=gestor)
    # Fecha a competência de HOJE — é ela, não a do original (que é a mesma
    # aqui de propósito, para provar que a checagem realmente olha a data do
    # ESTORNO), que vai decidir a recusa.
    encerrar_competencia(empresa=empresa, ano=hoje.year, mes=hoje.month, usuario=gestor)

    with pytest.raises(CompetenciaEncerrada):
        estornar_lancamento(original, criado_por=gestor)

    assert not original.estornos.exists()
    assert LancamentoContabil.objects.filter(empresa=empresa).count() == 1


def test_criterio2_estorno_permitido_quando_original_fechado_e_estorno_em_mes_aberto(cenario):
    """RC-57, confirmado pelo Fred: original em mês fechado, estorno em mês
    aberto PASSA — porque quem decide é a competência do estorno."""
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c2-positivo-gestor")

    original = _lancar(empresa, caixa, capital, date(2026, 1, 10), criado_por=gestor)
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    # Estorno explicitamente datado em fevereiro — mês diferente, ABERTO.
    estorno = estornar_lancamento(original, criado_por=gestor, data=date(2026, 2, 5))

    assert estorno.pk is not None
    assert estorno.competencia.ano == 2026
    assert estorno.competencia.mes == 2
    assert original.estornos.filter(pk=estorno.pk).exists()


def test_criterio2_api_estorno_recusa_com_409_quando_competencia_do_estorno_fechada(
    client, cenario
):
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    hoje = timezone.localdate()
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c2-api-gestor")
    original = _lancar(empresa, caixa, capital, hoje, criado_por=gestor)
    encerrar_competencia(empresa=empresa, ano=hoje.year, mes=hoje.month, usuario=gestor)

    client.login(username="c2-api-gestor", password="senha-forte-123")
    response = client.post(
        reverse("contabilidade:estornar", args=[empresa.id, original.id]),
        content_type="application/json",
    )

    assert response.status_code == 409
    assert not original.estornos.exists()


# ---------------------------------------------------------------------------
# BL-456/A1 (rodada 2 de auditoria) — BLOQUEADOR. A versão anterior lia
# `competencia.estado` do objeto em memória, sem travar a linha: uma corrida
# real entre `criar_lancamento` e `encerrar_competencia` gravava lançamento
# numa competência que terminava encerrada — 11 a 17 de 30 tentativas
# "gravaram e fecharam" nas medições desta rodada, em AMBOS os códigos
# (antes e depois da correção), porque "gravou e fechou" sozinho não
# distingue corrida de sequência legítima (lançar, depois fechar). A prova
# que distingue as duas é se o LOCK realmente bloqueia — é isso que os dois
# testes abaixo provam, de forma DETERMINÍSTICA (não uma contagem
# probabilística que pode sair diferente a cada execução).
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_bl456_for_share_bloqueia_encerrar_competencia_ate_o_lancamento_commitar(monkeypatch):
    """Prova DETERMINÍSTICA de que `_travar_competencia_em_modo_compartilhado`
    (FOR SHARE) segura a linha da competência pela duração INTEIRA da
    transação de `criar_lancamento` — e que `encerrar_competencia` (FOR
    UPDATE) fica genuinamente BLOQUEADO nesse intervalo, só terminando
    DEPOIS que o lançamento commitou.

    Mecanismo: o teste embrulha `_travar_competencia_em_modo_compartilhado`
    para segurar o lock por 0,5 s ANTES de devolver o estado — o `FOR SHARE`
    já foi executado (a query rodou), então o lock está ATIVO durante essa
    pausa, dentro da MESMA transação. Se `encerrar_competencia` terminar
    ANTES do lançamento (tempo relativo desde o início da corrida), o lock
    não bloqueou nada — e este teste haveria de falhar, provando a ausência
    da trava (é o que acontecia antes da correção do BL-456).
    """
    escritorio = Escritorio.objects.create(
        nome="Escritório BL-456 determinístico", cnpj="11222333000144"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa BL-456 Determinística Ltda",
        cnpj="11222333000225",
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    gestor = get_user_model().objects.create_user(
        username="bl456-determ", email="bl456-determ@escritorio.com.br", password="senha-forte-123"
    )
    # Pré-criada de propósito: se a linha nascesse DENTRO da corrida, as
    # duas threads disputariam o `get_or_create` de `obter_ou_criar_
    # competencia` — a PRIMEIRA a chegar faz um INSERT não commitado, e a
    # OUTRA fica bloqueada esperando aquele INSERT resolver (commit ou
    # rollback) para saber se a `UniqueConstraint(empresa, ano, mes)` foi
    # violada. Esse bloqueio é REAL, mas é do INSERT — não tem nada a ver
    # com o `FOR SHARE`/`FOR UPDATE` que este teste existe para provar, e
    # confundia a medição (uma thread esperava a outra por um motivo, o
    # teste JULGAVA que era por outro). Pré-criar a competência elimina essa
    # corrida lateral: as duas threads só fazem `SELECT` em `obter_ou_criar_
    # competencia`, sem risco de INSERT concorrente.
    Competencia.objects.create(empresa=empresa, ano=2015, mes=6)

    original = contabilidade_services._travar_competencia_em_modo_compartilhado

    def trava_e_segura(competencia):
        estado = original(competencia)
        # O SELECT ... FOR SHARE já rodou dentro de `original(...)` — o lock
        # está ativo. Segurar aqui, ainda DENTRO da mesma transação (a
        # chamadora, `criar_lancamento`, só sai do `with transaction.
        # atomic()` bem depois), é o que testa se o lock aguenta uma janela
        # longa.
        time.sleep(0.5)
        return estado

    monkeypatch.setattr(
        contabilidade_services, "_travar_competencia_em_modo_compartilhado", trava_e_segura
    )

    tempos = {}
    inicio = time.monotonic()

    def lancar():
        criar_lancamento(
            empresa=empresa,
            data=date(2015, 6, 10),
            historico="BL-456 determinístico",
            itens=[
                {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
                {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
            ],
            criado_por=gestor,
        )
        tempos["lancamento_fim"] = time.monotonic() - inicio
        connection.close()

    def fechar():
        time.sleep(0.1)  # dá tempo do lançamento pegar o FOR SHARE primeiro
        encerrar_competencia(empresa=empresa, ano=2015, mes=6, usuario=gestor)
        tempos["fechamento_fim"] = time.monotonic() - inicio
        connection.close()

    t1 = threading.Thread(target=lancar)
    t2 = threading.Thread(target=fechar)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # O fechamento só pode ter terminado DEPOIS do lançamento (que segurou
    # o lock por 0,5s) — se terminasse antes, o FOR UPDATE não esperou.
    assert tempos["fechamento_fim"] > tempos["lancamento_fim"]
    # E o fechamento precisa ter de fato ESPERADO pelo menos os 0,5s do
    # lock — não é coincidência de agendamento de thread.
    assert tempos["fechamento_fim"] >= 0.5

    assert LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2015, data__month=6
    ).exists()
    competencia = Competencia.objects.get(empresa=empresa, ano=2015, mes=6)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


@pytest.mark.django_db(transaction=True)
def test_bl456_lancamento_concorrente_e_recusado_quando_o_fechamento_ja_commitou(monkeypatch):
    """O outro lado da mesma prova: se `encerrar_competencia` já COMMITOU
    (FOR UPDATE liberado) antes de `criar_lancamento` tentar travar, o
    `FOR SHARE` deste último enxerga o estado JÁ ATUALIZADO — nunca um
    retrato antigo — e a trava recusa. Determinístico via `threading.Event`:
    o lançamento só tenta travar a competência DEPOIS que o fechamento
    sinaliza ter commitado.
    """
    escritorio = Escritorio.objects.create(nome="Escritório BL-456 recusa", cnpj="13141516000177")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-456 Recusa Ltda", cnpj="13141516000258"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    gestor = get_user_model().objects.create_user(
        username="bl456-recusa", email="bl456-recusa@escritorio.com.br", password="senha-forte-123"
    )
    # Pré-criada de propósito — ver o comentário equivalente no teste
    # anterior: sem isto, as duas threads disputam o `get_or_create` de
    # `obter_ou_criar_competencia`, e o INSERT não commitado de uma trava a
    # outra até resolver a `UniqueConstraint` — um bloqueio real, mas de
    # INSERT, não do `FOR SHARE`/`FOR UPDATE` que este teste mede. Foi essa
    # corrida lateral (não instrumentada, e por isso invisível na primeira
    # leitura) que causou o teste a ficar ~20% flaky antes desta correção:
    # às vezes o `fechar()` bloqueava no PRÓPRIO INSERT esperando o
    # `lancar()` commitar, sem nunca chegar a rodar `encerrar_competencia`
    # de verdade — e o `wait(timeout=5)` do lançamento estourava o prazo e
    # seguia com dado desatualizado, produzindo exatamente o falso positivo
    # que este teste existe para não deixar passar.
    Competencia.objects.create(empresa=empresa, ano=2016, mes=3)

    fechamento_commitou = threading.Event()
    # Garante que o `fechar()` só comece depois que o `lancar()` já está,
    # deterministicamente, parado dentro da trava — condição que este teste
    # existe para exercitar (e não uma corrida de "quem chega primeiro").
    lancamento_entrou_na_trava = threading.Event()
    original = contabilidade_services._travar_competencia_em_modo_compartilhado

    def trava_depois_do_fechamento(competencia):
        lancamento_entrou_na_trava.set()
        fechamento_commitou.wait(timeout=5)
        return original(competencia)

    monkeypatch.setattr(
        contabilidade_services,
        "_travar_competencia_em_modo_compartilhado",
        trava_depois_do_fechamento,
    )

    resultado = {}

    def lancar():
        try:
            criar_lancamento(
                empresa=empresa,
                data=date(2016, 3, 10),
                historico="BL-456 recusa",
                itens=[
                    {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
                    {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
                ],
                criado_por=gestor,
            )
            resultado["ok"] = True
        except CompetenciaEncerrada:
            resultado["ok"] = False
        finally:
            connection.close()

    def fechar():
        # Só começa depois que o lançamento está, comprovadamente, parado
        # dentro da trava (ver o comentário acima).
        assert lancamento_entrou_na_trava.wait(timeout=5)
        encerrar_competencia(empresa=empresa, ano=2016, mes=3, usuario=gestor)
        connection.close()
        fechamento_commitou.set()

    t1 = threading.Thread(target=lancar)
    t2 = threading.Thread(target=fechar)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert resultado["ok"] is False
    assert not LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2016, data__month=3
    ).exists()


@pytest.mark.django_db(transaction=True)
def test_bl456_reproducao_2_lancamento_concorrente_recusado_em_competencia_entregue(monkeypatch):
    """Reprodução 2 do relatório de auditoria — o caso que fere o cliente:
    um lançamento concorrente NUNCA entra numa competência já marcada como
    ENTREGUE ao cliente. Usa o mesmo mecanismo determinístico do teste
    anterior (o fechamento — aqui, fechar + entregar — commita, e só então
    o lançamento tenta travar)."""
    escritorio = Escritorio.objects.create(nome="Escritório BL-456 entregue", cnpj="14141414000114")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-456 Entregue Ltda", cnpj="14141414000203"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    gestor = get_user_model().objects.create_user(
        username="bl456-entregue",
        email="bl456-entregue@escritorio.com.br",
        password="senha-forte-123",
    )
    # Pré-criada de propósito — ver o comentário equivalente nos dois testes
    # anteriores (evita a corrida lateral de INSERT em `get_or_create`).
    Competencia.objects.create(empresa=empresa, ano=2017, mes=4)

    entrega_commitou = threading.Event()
    # Mesma correção de sincronização do teste anterior (BL-456): garante
    # que o `fechar_e_entregar()` só comece depois que o lançamento já
    # esteja parado, deterministicamente, dentro da trava.
    lancamento_entrou_na_trava = threading.Event()
    original = contabilidade_services._travar_competencia_em_modo_compartilhado

    def trava_depois_da_entrega(competencia):
        lancamento_entrou_na_trava.set()
        entrega_commitou.wait(timeout=5)
        return original(competencia)

    monkeypatch.setattr(
        contabilidade_services, "_travar_competencia_em_modo_compartilhado", trava_depois_da_entrega
    )

    resultado = {}

    def lancar():
        try:
            criar_lancamento(
                empresa=empresa,
                data=date(2017, 4, 10),
                historico="BL-456 mês entregue",
                itens=[
                    {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
                    {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
                ],
                criado_por=gestor,
            )
            resultado["ok"] = True
        except CompetenciaEncerrada:
            resultado["ok"] = False
        finally:
            connection.close()

    def fechar_e_entregar():
        assert lancamento_entrou_na_trava.wait(timeout=5)
        encerrar_competencia(empresa=empresa, ano=2017, mes=4, usuario=gestor)
        marcar_competencia_como_entregue(empresa=empresa, ano=2017, mes=4, usuario=gestor)
        connection.close()
        entrega_commitou.set()

    t1 = threading.Thread(target=lancar)
    t2 = threading.Thread(target=fechar_e_entregar)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert resultado["ok"] is False
    assert not LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2017, data__month=4
    ).exists()
    competencia = Competencia.objects.get(empresa=empresa, ano=2017, mes=4)
    assert competencia.estado == EstadoCompetencia.ENCERRADA
    assert competencia.entregue_em is not None


@pytest.mark.django_db(transaction=True)
def test_bl456_corrida_natural_sem_instrumentacao_e_internamente_consistente():
    """Complementa os testes determinísticos acima com a MESMA corrida
    "natural" que a auditoria usou (sem monkeypatch, duas threads, a que
    fecha começando ~0,6 ms depois da que lança), repetida várias vezes.

    ⚠️ Medição feita durante esta correção (não presumida): a contagem bruta
    de "lançou E fechou" NÃO é, por si só, um indicador de corrida — ela
    aparece tanto no código ANTES da correção (violação real) quanto DEPOIS
    dela (resultado LEGÍTIMO: o lançamento venceu o `FOR SHARE` e o
    fechamento esperou e fechou depois, como o próprio relatório da
    auditoria admite ser aceitável: "o lançamento entrou e o fechamento
    devia ter... esperado"). O que este teste garante, de forma que
    qualquer execução consegue verificar sozinha: NENHUMA exceção
    inesperada, e toda vez que o lançamento é recusado, a competência
    realmente terminou encerrada (a recusa nunca é por outro motivo). A
    prova de que a corrida em si fecha é dos dois testes determinísticos
    acima, que não dependem de quem chega primeiro.
    """
    escritorio = Escritorio.objects.create(nome="Escritório BL-456 natural", cnpj="15151515000115")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-456 Natural Ltda", cnpj="15151515000206"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    gestor = get_user_model().objects.create_user(
        username="bl456-natural",
        email="bl456-natural@escritorio.com.br",
        password="senha-forte-123",
    )

    pares_ano_mes = [(2003, m) for m in range(1, 13)] + [(2004, m) for m in range(1, 7)]
    assert len(set(pares_ano_mes)) == 18

    for ano, mes in pares_ano_mes:
        resultado = {}

        def lancar(ano=ano, mes=mes, resultado=resultado):
            try:
                criar_lancamento(
                    empresa=empresa,
                    data=date(ano, mes, 10),
                    historico=f"corrida natural {ano}-{mes:02d}",
                    itens=[
                        {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
                        {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
                    ],
                    criado_por=gestor,
                )
                resultado["lancamento"] = "gravado"
            except CompetenciaEncerrada:
                resultado["lancamento"] = "recusado"
            finally:
                connection.close()

        def fechar(ano=ano, mes=mes):
            time.sleep(0.0006)
            encerrar_competencia(empresa=empresa, ano=ano, mes=mes, usuario=gestor)
            connection.close()

        t1 = threading.Thread(target=lancar)
        t2 = threading.Thread(target=fechar)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Nunca "outra coisa" além de gravado/recusado — nenhuma exceção crua.
        assert resultado.get("lancamento") in ("gravado", "recusado")

        competencia = Competencia.objects.get(empresa=empresa, ano=ano, mes=mes)
        if resultado["lancamento"] == "recusado":
            # Recusa só pode ser por competência realmente encerrada.
            assert competencia.estado == EstadoCompetencia.ENCERRADA


# ---------------------------------------------------------------------------
# BL-457/A2 (rodada 2 de auditoria) — ALTA. A ÚNICA tela de lançamento do
# produto (`views_web.lancamento_novo`, em produção desde a DL-017) devolvia
# HTTP 500 quando a trava disparava: `CompetenciaEncerrada` é subclasse
# direta de `Exception`, deliberadamente NÃO de `LancamentoInvalido`, e o
# bloco `except` da tela só capturava três exceções — nenhuma delas a dela.
# Nada era gravado (a trava funcionava); só a APRESENTAÇÃO da recusa
# quebrava. Controle positivo no MESMO teste, como a auditoria exigiu.
# ---------------------------------------------------------------------------


def test_bl457_tela_de_lancamento_recusa_com_400_em_mes_encerrado_e_grava_em_mes_aberto(
    client, cenario
):
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl457-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=5, usuario=gestor)
    client.login(username="bl457-gestor", password="senha-forte-123")
    url = reverse("contabilidade_web:lancamento_novo", args=[empresa.id])

    def _post(data_texto, chave):
        return client.post(
            url,
            {
                "acao": "gravar",
                "num_linhas": "2",
                "data": data_texto,
                "historico": "BL-457",
                "chave_idempotencia": chave,
                "conta_1": str(caixa.id),
                "tipo_1": "debito",
                "valor_1": "10,00",
                "conta_2": str(capital.id),
                "tipo_2": "credito",
                "valor_2": "10,00",
            },
        )

    # Mês FECHADO: antes desta correção, 500 — sem nenhuma palavra sobre
    # competência encerrada, e o contador via uma página de erro genérica.
    resposta_fechado = _post("2026-05-10", "bl457-fechado")
    assert resposta_fechado.status_code == 400
    corpo = resposta_fechado.content.decode("utf-8")
    assert "encerrada" in corpo
    assert not LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2026, data__month=5
    ).exists()

    # CONTROLE POSITIVO, no MESMO teste (a auditoria foi explícita sobre
    # isto): o MESMO POST, só trocando o mês para um aberto, grava (302) —
    # prova de que o 400 acima é especificamente da trava, não de outro
    # motivo qualquer (campo errado, permissão, etc.).
    resposta_aberto = _post("2026-06-10", "bl457-aberto")
    assert resposta_aberto.status_code == 302
    assert LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2026, data__month=6
    ).exists()


# ---------------------------------------------------------------------------
# Critério 3 — fechar grava autor, data, trilha. Fechar com LOTE
# DESBALANCEADO na base é recusado (RC-58).
# ---------------------------------------------------------------------------


def test_criterio3_encerrar_grava_autor_e_data(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c3-gestor")

    antes = timezone.now()
    competencia = encerrar_competencia(empresa=empresa, ano=2026, mes=5, usuario=gestor)
    depois = timezone.now()

    assert competencia.estado == EstadoCompetencia.ENCERRADA
    assert competencia.fechada_por_id == gestor.id
    assert antes <= competencia.fechada_em <= depois
    assert competencia.encerrada_agora is True


def test_criterio3_api_encerrar_grava_registro_na_trilha(client, cenario):
    empresa = cenario["empresa"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c3-api-gestor")
    client.login(username="c3-api-gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 5]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 200
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=5)
    registro = RegistroAuditoria.objects.get(
        acao="competencia.encerrada", objeto_id=str(competencia.pk)
    )
    assert registro.usuario.username == "c3-api-gestor"
    assert registro.objeto_tipo == "Competencia"


def test_criterio3_encerrar_recusa_com_lote_desbalanceado_na_base(cenario):
    empresa, caixa = cenario["empresa"], cenario["caixa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c3-desbalanceado")

    # Lote TORTO gravado por fora de `criar_lancamento` (o único caminho que
    # `localizar_lotes_desbalanceados` existe para achar — ver seu docstring).
    competencia = Competencia.objects.create(empresa=empresa, ano=2026, mes=6)
    lancamento = LancamentoContabil.objects.create(
        empresa=empresa,
        data=date(2026, 6, 10),
        historico="Lote torto (só débito, sem contrapartida)",
        competencia=competencia,
    )
    ItemLancamento.objects.create(
        lancamento=lancamento, conta=caixa, tipo=TipoPartida.DEBITO, valor=Decimal("10.00")
    )

    with pytest.raises(CompetenciaOperacaoRecusada):
        encerrar_competencia(empresa=empresa, ano=2026, mes=6, usuario=gestor)

    competencia.refresh_from_db()
    assert competencia.estado == EstadoCompetencia.ABERTA
    assert competencia.fechada_em is None


def test_criterio3_api_encerrar_recusa_com_409_quando_ha_lote_desbalanceado(client, cenario):
    empresa, caixa = cenario["empresa"], cenario["caixa"]
    competencia = Competencia.objects.create(empresa=empresa, ano=2026, mes=6)
    lancamento = LancamentoContabil.objects.create(
        empresa=empresa, data=date(2026, 6, 10), historico="Lote torto", competencia=competencia
    )
    ItemLancamento.objects.create(
        lancamento=lancamento, conta=caixa, tipo=TipoPartida.DEBITO, valor=Decimal("10.00")
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c3-api-desbalanceado")
    client.login(username="c3-api-desbalanceado", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 409
    competencia.refresh_from_db()
    assert competencia.estado == EstadoCompetencia.ABERTA


# ---------------------------------------------------------------------------
# Critério 4 — fechamento é IDEMPOTENTE: fechar duas vezes não duplica
# registro nem troca o autor do primeiro fechamento.
# ---------------------------------------------------------------------------


def test_criterio4_encerrar_e_idempotente_nao_duplica_nem_troca_autor(cenario):
    empresa = cenario["empresa"]
    primeiro_gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c4-primeiro")
    segundo_gestor = _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio"], "c4-segundo")

    primeiro = encerrar_competencia(empresa=empresa, ano=2026, mes=7, usuario=primeiro_gestor)
    assert primeiro.encerrada_agora is True
    fechada_em_original = primeiro.fechada_em

    segundo = encerrar_competencia(empresa=empresa, ano=2026, mes=7, usuario=segundo_gestor)

    assert segundo.encerrada_agora is False
    assert segundo.fechada_por_id == primeiro_gestor.id  # autor do PRIMEIRO nunca troca
    assert segundo.fechada_em == fechada_em_original
    assert Competencia.objects.filter(empresa=empresa, ano=2026, mes=7).count() == 1


def test_criterio4_api_encerrar_duas_vezes_grava_um_unico_registro_de_trilha(client, cenario):
    empresa = cenario["empresa"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c4-api-gestor")
    client.login(username="c4-api-gestor", password="senha-forte-123")
    url = reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 8])

    primeira = client.post(url, data={}, content_type="application/json")
    segunda = client.post(url, data={}, content_type="application/json")

    assert primeira.status_code == 200
    assert segunda.status_code == 200
    assert RegistroAuditoria.objects.filter(acao="competencia.encerrada").count() == 1


# ---------------------------------------------------------------------------
# Critério 5 — reabrir EXIGE motivo não vazio. Motivo em branco ou só
# espaços é recusado.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("motivo_invalido", [None, "", "   "])
def test_criterio5_reabrir_exige_motivo_nao_vazio(cenario, motivo_invalido):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c5-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    with pytest.raises(CompetenciaOperacaoInvalida):
        reabrir_competencia(
            empresa=empresa, ano=2026, mes=1, usuario=gestor, motivo=motivo_invalido
        )

    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=1)
    assert competencia.estado == EstadoCompetencia.ENCERRADA  # nada mudou


def test_criterio5_api_reabrir_com_motivo_so_espaco_retorna_400_e_nada_muda(client, cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c5-api-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    client.login(username="c5-api-gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:reabrir-competencia", args=[empresa.id, 2026, 1]),
        data={"motivo": "   "},
        content_type="application/json",
    )

    assert response.status_code == 400
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=1)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


def test_criterio5_reabrir_com_motivo_valido_grava_na_trilha(client, cenario):
    empresa = cenario["empresa"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c5-valido-gestor")
    client.login(username="c5-valido-gestor", password="senha-forte-123")
    client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 1]),
        data={},
        content_type="application/json",
    )

    response = client.post(
        reverse("contabilidade:reabrir-competencia", args=[empresa.id, 2026, 1]),
        data={"motivo": "Ajuste solicitado pelo cliente"},
        content_type="application/json",
    )

    assert response.status_code == 200
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=1)
    assert competencia.estado == EstadoCompetencia.ABERTA
    assert competencia.fechada_em is None
    assert competencia.fechada_por_id is None
    registro = RegistroAuditoria.objects.get(
        acao="competencia.reaberta", objeto_id=str(competencia.pk)
    )
    assert registro.detalhes["motivo"] == "Ajuste solicitado pelo cliente"


# ---------------------------------------------------------------------------
# Critério 6 — reabrir competência JÁ ENTREGUE é recusado (RC-101), com 409
# e mensagem que diz a data da entrega e orienta o ajuste no mês aberto.
# ---------------------------------------------------------------------------


def test_criterio6_reabrir_recusa_competencia_ja_entregue(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c6-gestor")
    encerrar_competencia(empresa=empresa, ano=2026, mes=2, usuario=gestor)
    entregue = marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=2, usuario=gestor)

    with pytest.raises(CompetenciaJaEntregue) as excinfo:
        reabrir_competencia(
            empresa=empresa, ano=2026, mes=2, usuario=gestor, motivo="Erro de digitação"
        )

    mensagem = str(excinfo.value)
    assert timezone.localtime(entregue.entregue_em).strftime("%d/%m/%Y") in mensagem
    assert "mês aberto" in mensagem

    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=2)
    assert competencia.estado == EstadoCompetencia.ENCERRADA  # nada mudou


def test_criterio6_api_reabrir_competencia_entregue_retorna_409(client, cenario):
    empresa = cenario["empresa"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c6-api-gestor")
    client.login(username="c6-api-gestor", password="senha-forte-123")
    client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 2]),
        data={},
        content_type="application/json",
    )
    client.post(
        reverse("contabilidade:entregar-competencia", args=[empresa.id, 2026, 2]),
        data={},
        content_type="application/json",
    )

    response = client.post(
        reverse("contabilidade:reabrir-competencia", args=[empresa.id, 2026, 2]),
        data={"motivo": "Cliente pediu correção"},
        content_type="application/json",
    )

    assert response.status_code == 409
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=2)
    assert competencia.estado == EstadoCompetencia.ENCERRADA


# ---------------------------------------------------------------------------
# Critério 7 — marcar como entregue grava entregue_em/entregue_por. Só
# competência ENCERRADA pode ser entregue.
# ---------------------------------------------------------------------------


def test_criterio7_entregar_recusa_mes_aberto(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c7-gestor")

    # A função inteira é `@transaction.atomic`: a recusa desfaz TUDO,
    # inclusive a `Competencia` que `obter_ou_criar_competencia` teria
    # criado — nenhuma linha residual fica para trás de uma operação que
    # falhou (mesmo padrão de `criar_lancamento`: erro de domínio não deixa
    # rastro parcial no banco).
    with pytest.raises(CompetenciaOperacaoRecusada):
        marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=4, usuario=gestor)

    assert not Competencia.objects.filter(empresa=empresa, ano=2026, mes=4).exists()

    # Mesma recusa quando a competência JÁ existe (aberta) — o estado dela
    # também não muda.
    Competencia.objects.create(empresa=empresa, ano=2026, mes=4)
    with pytest.raises(CompetenciaOperacaoRecusada):
        marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=4, usuario=gestor)

    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=4)
    assert competencia.estado == EstadoCompetencia.ABERTA
    assert competencia.entregue_em is None
    assert competencia.entregue_por_id is None


def test_criterio7_entregar_competencia_encerrada_grava_entregue_em_e_por(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c7-gestor-ok")
    encerrar_competencia(empresa=empresa, ano=2026, mes=4, usuario=gestor)

    antes = timezone.now()
    entregue = marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=4, usuario=gestor)
    depois = timezone.now()

    assert entregue.entregue_por_id == gestor.id
    assert antes <= entregue.entregue_em <= depois
    assert entregue.entregue_agora is True


def test_criterio7_api_entregar_mes_aberto_retorna_409(client, cenario):
    empresa = cenario["empresa"]
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c7-api-gestor")
    client.login(username="c7-api-gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:entregar-competencia", args=[empresa.id, 2026, 4]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 409
    assert not Competencia.objects.filter(
        empresa=empresa, ano=2026, mes=4, entregue_em__isnull=False
    ).exists()


# ---------------------------------------------------------------------------
# Critério 8 — autorização verificada NO SERVIDOR (RC-102, confirmado pelo
# Fred: "Administrador e gestor pode, analista não"). Usuário sem o papel
# recebe 403 e NADA muda no banco.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.ADMINISTRADOR, Papel.GESTOR])
def test_criterio8_papel_autorizado_encerra_reabre_e_entrega(client, cenario, papel):
    empresa = cenario["empresa"]
    username = f"c8-autorizado-{papel.value}"
    _usuario_com_papel(papel, cenario["escritorio"], username)
    client.login(username=username, password="senha-forte-123")

    r_encerrar = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )
    r_reabrir = client.post(
        reverse("contabilidade:reabrir-competencia", args=[empresa.id, 2026, 6]),
        data={"motivo": "conferência"},
        content_type="application/json",
    )
    r_encerrar_de_novo = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )
    r_entregar = client.post(
        reverse("contabilidade:entregar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )

    assert r_encerrar.status_code == 200
    assert r_reabrir.status_code == 200
    assert r_encerrar_de_novo.status_code == 200
    assert r_entregar.status_code == 200


@pytest.mark.parametrize(
    "papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]
)
def test_criterio8_papel_nao_autorizado_recebe_403_e_banco_intacto(client, cenario, papel):
    """RC-102: ANALISTA lança e não fecha/reabre/entrega. Os demais papéis
    nunca estiveram em questão para esta operação — todos ficam de fora.

    Medido pelo BANCO, não só pelo código HTTP (lição do BL-211: 403 sozinho
    já enganou este projeto antes).
    """
    empresa = cenario["empresa"]
    username = f"c8-negado-{papel.value}"
    _usuario_com_papel(papel, cenario["escritorio"], username)
    client.login(username=username, password="senha-forte-123")

    r_encerrar = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )
    r_reabrir = client.post(
        reverse("contabilidade:reabrir-competencia", args=[empresa.id, 2026, 6]),
        data={"motivo": "x"},
        content_type="application/json",
    )
    r_entregar = client.post(
        reverse("contabilidade:entregar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )

    assert r_encerrar.status_code == 403
    assert r_reabrir.status_code == 403
    assert r_entregar.status_code == 403

    # Nada mudou no banco: nem a competência chegou a nascer (as três
    # tentativas foram recusadas ANTES de `post()` rodar — DRF checa
    # `has_permission` antes do handler), nem há trilha da operação recusada.
    assert not Competencia.objects.filter(empresa=empresa, ano=2026, mes=6).exists()
    assert not RegistroAuditoria.objects.filter(acao__startswith="competencia.").exists()


def test_criterio8_analista_continua_podendo_lancar_mas_nao_fechar(client, cenario):
    """Distingue as duas permissões: ANALISTA está em `PodeEscriturar`
    (lança normalmente) e fica de fora de `PodeFecharCompetencia`."""
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    _usuario_com_papel(Papel.ANALISTA, cenario["escritorio"], "c8-analista-lanca")
    client.login(username="c8-analista-lanca", password="senha-forte-123")

    resposta_lancamento = client.post(
        reverse("contabilidade:lancamentos", args=[empresa.id]),
        data={
            "data": "2026-06-10",
            "historico": "Lançamento do analista",
            "itens": [
                {"conta": caixa.id, "tipo": "debito", "valor": "10.00"},
                {"conta": capital.id, "tipo": "credito", "valor": "10.00"},
            ],
        },
        content_type="application/json",
    )
    resposta_fechar = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa.id, 2026, 6]),
        data={},
        content_type="application/json",
    )

    assert resposta_lancamento.status_code == 201
    assert resposta_fechar.status_code == 403


# ---------------------------------------------------------------------------
# Critério 9 — isolamento: competência encerrada de uma empresa não afeta
# outra empresa nem outro escritório.
# ---------------------------------------------------------------------------


def test_criterio9_isolamento_entre_empresas_e_escritorios(cenario):
    empresa_a, escritorio_a = cenario["empresa"], cenario["escritorio"]
    gestor_a = _usuario_com_papel(Papel.GESTOR, escritorio_a, "c9-gestor-a")
    encerrar_competencia(empresa=empresa_a, ano=2026, mes=2, usuario=gestor_a)

    # Outra empresa, MESMO escritório — mesma competência (ano, mês), mas
    # NENHUMA linha de Competencia própria ainda, e livre para lançar.
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa B do Mesmo Escritório", cnpj="33344455000122"
    )
    caixa_b = Conta.objects.create(
        empresa=empresa_b,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital_b = Conta.objects.create(
        empresa=empresa_b,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    assert not Competencia.objects.filter(empresa=empresa_b, ano=2026, mes=2).exists()
    lancamento_b = _lancar(empresa_b, caixa_b, capital_b, date(2026, 2, 15))
    assert lancamento_b.pk is not None

    # Empresa em OUTRO escritório inteiro — mesmo cenário.
    escritorio_c = Escritorio.objects.create(nome="Outro Escritório", cnpj="22222222000122")
    empresa_c = Empresa.objects.create(
        escritorio=escritorio_c, razao_social="Empresa de Outro Escritório", cnpj="22233344000194"
    )
    caixa_c = Conta.objects.create(
        empresa=empresa_c,
        codigo="1.1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital_c = Conta.objects.create(
        empresa=empresa_c,
        codigo="2.1",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    assert not Competencia.objects.filter(empresa=empresa_c, ano=2026, mes=2).exists()
    lancamento_c = _lancar(empresa_c, caixa_c, capital_c, date(2026, 2, 15))
    assert lancamento_c.pk is not None

    # E a competência da empresa A continua a única encerrada.
    assert (
        Competencia.objects.filter(estado=EstadoCompetencia.ENCERRADA, ano=2026, mes=2).count() == 1
    )


def test_criterio9_api_isolamento_empresa_de_outro_escritorio_e_404(client, cenario):
    """Uma empresa de outro escritório nem é ENCONTRADA por esta sessão —
    `EmpresaEscopadaMixin` devolve 404, não 403 (não confirma existência)."""
    escritorio_x = Escritorio.objects.create(nome="Escritório X", cnpj="33333333000133")
    empresa_x = Empresa.objects.create(
        escritorio=escritorio_x, razao_social="Empresa X Ltda", cnpj="44455566000183"
    )
    _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "c9-api-gestor")
    client.login(username="c9-api-gestor", password="senha-forte-123")

    response = client.post(
        reverse("contabilidade:encerrar-competencia", args=[empresa_x.id, 2026, 2]),
        data={},
        content_type="application/json",
    )

    assert response.status_code == 404
    assert not Competencia.objects.filter(empresa=empresa_x).exists()


# ---------------------------------------------------------------------------
# Critério 10 — concorrência: duas requisições SIMULTÂNEAS de fechamento da
# MESMA competência produzem UM registro. Teste concorrente real em
# PostgreSQL (mesmo padrão de `test_bl40_bl41.py::test_corrida_real_de_
# estorno_produz_um_unico_estorno`).
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_criterio10_corrida_real_de_fechamento_produz_um_unico_fechamento():
    escritorio = Escritorio.objects.create(
        nome="Escritório Corrida Fechamento", cnpj="55566677000111"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Corrida Fechamento Ltda",
        cnpj="66677788000199",
    )
    gestor = get_user_model().objects.create_user(
        username="c10-gestor", email="c10-gestor@escritorio.com.br", password="senha-forte-123"
    )
    administrador = get_user_model().objects.create_user(
        username="c10-admin", email="c10-admin@escritorio.com.br", password="senha-forte-123"
    )

    resultados = []
    barreira = threading.Barrier(2)

    def fechar(usuario):
        barreira.wait()
        try:
            competencia = encerrar_competencia(empresa=empresa, ano=2026, mes=4, usuario=usuario)
            resultados.append(competencia.encerrada_agora)
        finally:
            connection.close()  # cada thread precisa fechar a própria conexão

    threads = [threading.Thread(target=fechar, args=(u,)) for u in (gestor, administrador)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(resultados) == [False, True]
    assert Competencia.objects.filter(empresa=empresa, ano=2026, mes=4).count() == 1
    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=4)
    assert competencia.estado == EstadoCompetencia.ENCERRADA
    assert competencia.fechada_por_id in (gestor.id, administrador.id)


# ---------------------------------------------------------------------------
# `EM_ENCERRAMENTO` é reservado e não alcançável pela fatia 1 (ver o
# docstring de `EstadoCompetencia` em models.py).
# ---------------------------------------------------------------------------


def test_em_encerramento_nao_e_alcancado_por_nenhum_service_da_fatia_1(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "reservado-gestor")

    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    reabrir_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor, motivo="conferir")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    assert not Competencia.objects.filter(estado=EstadoCompetencia.EM_ENCERRAMENTO).exists()


def test_bl461_lancamento_e_recusado_em_competencia_em_encerramento(cenario):
    """BL-461/A7 (rodada 2 de auditoria): `em_encerramento` é inalcançável
    pelos services desta fatia (teste acima), mas até esta correção a trava
    de `criar_lancamento` comparava `== ENCERRADA` — e uma competência nesse
    terceiro estado (só alcançável por ORM direta, ex.: um importador
    futuro) ACEITAVA lançamento. A condição passou para `!= ABERTA`: mais
    segura, e sem efeito prático hoje porque nenhum service escreve esse
    valor."""
    empresa, caixa, capital = cenario["empresa"], cenario["caixa"], cenario["capital"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl461-gestor")
    Competencia.objects.create(
        empresa=empresa, ano=2026, mes=1, estado=EstadoCompetencia.EM_ENCERRAMENTO
    )

    with pytest.raises(CompetenciaEncerrada) as excinfo:
        _lancar(empresa, caixa, capital, date(2026, 1, 10), criado_por=gestor)

    assert "em encerramento" in str(excinfo.value)
    assert not LancamentoContabil.objects.filter(
        empresa=empresa, data__year=2026, data__month=1
    ).exists()


# ---------------------------------------------------------------------------
# BL-458/BL-459 (rodada 2 de auditoria) — a trilha mora no SERVIÇO, não na
# view: chamada direta a `encerrar_competencia`/`reabrir_competencia`/
# `marcar_competencia_como_entregue` (sem passar por view nenhuma — shell,
# comando de gerência, futuro importador) grava `RegistroAuditoria` do mesmo
# jeito. `detalhes` carrega `ano`/`mes`/`empresa_id` nas três, e
# `fechada_por_anterior`/`fechada_em_anterior` na reabertura.
# ---------------------------------------------------------------------------


def test_bl458_encerrar_direto_do_servico_sem_view_grava_trilha(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl458-encerrar")

    antes = RegistroAuditoria.objects.count()
    competencia = encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    depois = RegistroAuditoria.objects.count()

    assert depois == antes + 1
    registro = RegistroAuditoria.objects.get(
        acao="competencia.encerrada", objeto_id=str(competencia.pk)
    )
    assert registro.usuario_id == gestor.id
    assert registro.escritorio_id == cenario["escritorio"].id
    assert registro.detalhes == {"ano": 2026, "mes": 1, "empresa_id": empresa.id}


def test_bl458_encerrar_idempotente_direto_do_servico_nao_duplica_trilha(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl458-idempotente")

    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    antes = RegistroAuditoria.objects.filter(acao="competencia.encerrada").count()
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)  # repetição
    depois = RegistroAuditoria.objects.filter(acao="competencia.encerrada").count()

    assert depois == antes  # nenhum registro novo


def test_bl458_reabrir_direto_do_servico_sem_view_grava_trilha_com_valores_anteriores(cenario):
    empresa = cenario["empresa"]
    administrador = _usuario_com_papel(Papel.ADMINISTRADOR, cenario["escritorio"], "bl458-admin")
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl458-reabrir")

    fechada = encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=administrador)
    fechada_em_original = fechada.fechada_em

    antes = RegistroAuditoria.objects.count()
    competencia = reabrir_competencia(
        empresa=empresa, ano=2026, mes=1, usuario=gestor, motivo="Correção de lançamento"
    )
    depois = RegistroAuditoria.objects.count()

    assert depois == antes + 1
    # A LINHA perde fechada_em/fechada_por (ver o docstring do serviço) —
    # mas a TRILHA preserva os dois, exatamente o que o BL-459 exige.
    assert competencia.fechada_em is None
    assert competencia.fechada_por_id is None
    registro = RegistroAuditoria.objects.get(
        acao="competencia.reaberta", objeto_id=str(competencia.pk)
    )
    assert registro.detalhes["ano"] == 2026
    assert registro.detalhes["mes"] == 1
    assert registro.detalhes["empresa_id"] == empresa.id
    assert registro.detalhes["motivo"] == "Correção de lançamento"
    assert registro.detalhes["fechada_por_anterior"] == administrador.id
    assert registro.detalhes["fechada_em_anterior"] == fechada_em_original.isoformat()


def test_bl458_entregar_direto_do_servico_sem_view_grava_trilha(cenario):
    empresa = cenario["empresa"]
    gestor = _usuario_com_papel(Papel.GESTOR, cenario["escritorio"], "bl458-entregar")
    encerrar_competencia(empresa=empresa, ano=2026, mes=1, usuario=gestor)

    antes = RegistroAuditoria.objects.count()
    competencia = marcar_competencia_como_entregue(empresa=empresa, ano=2026, mes=1, usuario=gestor)
    depois = RegistroAuditoria.objects.count()

    assert depois == antes + 1
    registro = RegistroAuditoria.objects.get(
        acao="competencia.entregue", objeto_id=str(competencia.pk)
    )
    assert registro.detalhes == {"ano": 2026, "mes": 1, "empresa_id": empresa.id}


# ---------------------------------------------------------------------------
# Critério 11 — migração sobre base COM DADOS: nenhuma competência existente
# nasce encerrada nem entregue. O estado inicial é tudo aberto.
#
# Complementa a verificação manual em `manage.py migrate` (registrada no
# relatório de entrega) com uma regressão AUTOMÁTICA: usa `MigrationExecutor`
# do próprio Django para migrar a `contabilidade` de volta para ANTES desta
# migração (0005), gravar uma `Competencia` com o SCHEMA ANTIGO (sem os
# quatro campos novos, via o modelo HISTÓRICO do `apps` congelado naquele
# ponto — nunca o modelo atual), reaplicar a migração 0006 e conferir com o
# modelo ATUAL que a linha sobreviveu sem ganhar `estado='encerrada'` nem
# `entregue_em` preenchido.
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_criterio11_migracao_0006_sobre_base_com_dados_nao_altera_competencia_existente():
    from django.db import connection as db_connection
    from django.db.migrations.executor import MigrationExecutor

    escritorio = Escritorio.objects.create(nome="Escritório Migração", cnpj="10101010000100")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Migração Ltda", cnpj="10101010000101"
    )

    alvo_anterior = [("contabilidade", "0005_check_lancamento_empresa_not_null")]
    alvo_atual = [("contabilidade", "0006_fechamento_reabertura_e_entrega_de_competencia")]
    try:
        # Volta o SCHEMA da `contabilidade` para o estado ANTERIOR a esta
        # migração — as outras apps (tenancy, empresas) permanecem na versão
        # mais recente, intocadas: só a tabela desta migração muda.
        MigrationExecutor(db_connection).migrate(alvo_anterior)

        # O modelo HISTÓRICO, congelado em 0005 — NUNCA o `Competencia`
        # importado no topo deste arquivo, que já tem os quatro campos
        # novos e quebraria o INSERT contra o schema antigo.
        apps_antigos = MigrationExecutor(db_connection).loader.project_state(alvo_anterior).apps
        CompetenciaAntes = apps_antigos.get_model("contabilidade", "Competencia")
        competencia_antes = CompetenciaAntes.objects.create(empresa_id=empresa.id, ano=2026, mes=9)
        competencia_id = competencia_antes.pk
    finally:
        # SEMPRE volta ao estado mais recente antes de sair — inclusive se
        # uma asserção falhar abaixo —, para não deixar a tabela desta app
        # com o schema errado para o resto da sessão de teste.
        MigrationExecutor(db_connection).migrate(alvo_atual)

    competencia = Competencia.objects.get(pk=competencia_id)
    assert competencia.estado == EstadoCompetencia.ABERTA
    assert competencia.fechada_em is None
    assert competencia.fechada_por_id is None
    assert competencia.entregue_em is None
    assert competencia.entregue_por_id is None
