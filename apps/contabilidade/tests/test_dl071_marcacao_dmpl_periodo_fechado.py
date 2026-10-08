"""DL-071 (BL-655) — a marcação manual da DMPL respeita o período fechado.

A marcação (`MarcacaoDmpl`, DL-061 fatia 2) é um ato de classificação POR
LANÇAMENTO, com o mesmo efeito da reclassificação de conta que a DL-065 já
trava: muda a célula em que um valor aparece numa demonstração. Medido em
08/10/2026 (reprodução do plano, 12 combinações): com a competência
encerrada ou entregue, trocar a marcação movia 1.000,00 de linha, remover
fazia `pode_emitir` ir de True a False e marcar pela primeira vez fazia ir de
False a True — a DMPL de um período fechado mudando sem aviso.

Este arquivo cobre os critérios 1 a 10 do plano
(`docs/planos/DL-071-marcacao-da-dmpl-em-periodo-fechado.md`); o 11
(mutação) e o 12 (suíte) são medidos por execução e registrados na entrega.

- 1: encerrada — trocar, remover e marcar pela primeira vez são recusados no
  serviço e na API (409); nada é gravado, a trilha não ganha registro e a DMPL
  apurada é idêntica;
- 2: o mesmo com a competência ENTREGUE, e a mensagem não manda reabrir;
- 3: competência POSTERIOR do mesmo exercício fechada recusa; de outro
  exercício, não — e a fronteira é MEDIDA contra `apurar_dmpl`, não presumida;
- 4: tudo aberto, o comportamento é o de sempre;
- 5: competência reaberta depois de encerrada aceita;
- 6: a tela mostra a recusa na própria guia, com status 200, sem gravar;
- 7: corrida com o fechamento (duas threads, PostgreSQL);
- 8: `lock_timeout` estourado vira recusa (409 / mensagem), nunca 500;
- 9: lançamento de outra empresa ou de outro escritório continua 404, antes de
  qualquer consulta de período;
- 10: o custo da guarda não cresce com o histórico de competências fechadas.

Dados 100% sintéticos (os mesmos cenários do BL-605). Datas em 2026.
"""

import json
import threading
import time
from datetime import date

import pytest
from django.contrib import admin
from django.db import OperationalError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    Competencia,
    EstadoCompetencia,
    ItemLancamento,
    LancamentoContabil,
    MarcacaoDmpl,
    TipoPartida,
)
from apps.contabilidade.services import (
    ClassificacaoAlteraPeriodoFechado,
    apurar_dmpl,
    avaliar_emissao_da_dmpl,
    encerrar_competencia,
    marcar_competencia_como_entregue,
    reabrir_competencia,
    remover_marcacoes_da_dmpl,
    salvar_marcacoes_da_dmpl,
)
from apps.contabilidade.tests.test_dl048_dlpa import _autenticar
from apps.contabilidade.tests.test_dl061_bl605_marcacao_manual import (
    LINHA_ALIENACAO,
    LINHA_AQUISICAO,
    TESOURARIA,
    _com_tesouraria,
    _marc,
)
from apps.contabilidade.tests.test_dl061_dmpl import (
    _apurar,
    _cnpj_sintetico,
    _dec,
    _empresa,
    _gestor,
    _lancar,
    _lancar_itens,
    _plano_basico,
)
from apps.empresas.models import Empresa

pytestmark = pytest.mark.django_db

ACAO_DA_TRILHA = "lancamento.marcacoes_dmpl_alteradas"
ANO = 2026


# ---------------------------------------------------------------------------
# Cenário e instrumentos de medida
# ---------------------------------------------------------------------------


def _cenario(*, marcar=("p1", "p2")):
    """Duas permutas de ações em tesouraria em fevereiro/2026 — eventos
    opostos no MESMO lançamento, que a regra automática não decide (RC-151) e
    por isso aceitam marcação. Com `marcar`, grava a marcação válida dos
    lançamentos pedidos com a competência ainda ABERTA (o controle positivo:
    a marcação só passa a ser recusada depois de o período fechar)."""
    empresa, contas, gestor = _com_tesouraria()
    p1 = _lancar_itens(
        empresa,
        date(2026, 2, 5),
        "Permuta 1",
        [
            (contas["tesouraria"], "D", "1500.00"),
            (contas["caixa"], "D", "1000.00"),
            (contas["caixa"], "C", "1500.00"),
            (contas["tesouraria"], "C", "1000.00"),
        ],
    )
    p2 = _lancar_itens(
        empresa,
        date(2026, 2, 6),
        "Permuta 2",
        [
            (contas["tesouraria"], "D", "700.00"),
            (contas["caixa"], "D", "300.00"),
            (contas["caixa"], "C", "700.00"),
            (contas["tesouraria"], "C", "300.00"),
        ],
    )
    if "p1" in marcar:
        salvar_marcacoes_da_dmpl(
            lancamento=p1,
            marcacoes=[
                _marc(LINHA_AQUISICAO, TESOURARIA, "-1500.00"),
                _marc(LINHA_ALIENACAO, TESOURARIA, "1000.00"),
            ],
            usuario=gestor,
        )
    if "p2" in marcar:
        salvar_marcacoes_da_dmpl(
            lancamento=p2,
            marcacoes=[
                _marc(LINHA_AQUISICAO, TESOURARIA, "-700.00"),
                _marc(LINHA_ALIENACAO, TESOURARIA, "300.00"),
            ],
            usuario=gestor,
        )
    return empresa, contas, gestor, p1, p2


def _fechar(empresa, gestor, mes, *, entregue=False, ano=ANO):
    encerrar_competencia(empresa=empresa, ano=ano, mes=mes, usuario=gestor)
    if entregue:
        marcar_competencia_como_entregue(empresa=empresa, ano=ano, mes=mes, usuario=gestor)


def _forcar_estado(empresa, ano, mes, estado):
    """Põe a competência no estado pedido SEM passar pelo serviço de
    fechamento — só para montar cenários de medida (muitas competências, ida e
    volta), onde o que interessa é o estado que a guarda lê."""
    Competencia.objects.update_or_create(
        empresa=empresa, ano=ano, mes=mes, defaults={"estado": estado}
    )


def _foto(empresa, meses=(2, 3)):
    """O que o documento diz hoje, para provar que a recusa não o moveu: se
    emite, o que veta, as células da tesouraria e a conciliação."""
    saida = {}
    for mes in meses:
        dmpl = _apurar(empresa, mes=mes)
        saida[mes] = {
            "pode_emitir": avaliar_emissao_da_dmpl(dmpl)["pode_emitir"],
            "pendencias": sorted(nome for nome, itens in dmpl["pendencias"].items() if itens),
            "celulas": {
                linha["chave"]: str(linha["valores"].get(TESOURARIA))
                for linha in dmpl["linhas"]
                if linha["valores"].get(TESOURARIA) not in (None, 0)
            },
            "saldo_final": str(dmpl["saldo_final"]["valores"].get(TESOURARIA)),
            "diferenca": str(dmpl["conciliacao"]["por_coluna"][TESOURARIA]["diferenca"]),
        }
    return json.dumps(saida, sort_keys=True)


def _marcacoes(lancamento):
    return [
        (m.linha, m.coluna, str(m.valor))
        for m in MarcacaoDmpl.objects.filter(lancamento=lancamento).order_by("id")
    ]


def _trilhas():
    return RegistroAuditoria.objects.filter(acao=ACAO_DA_TRILHA).count()


def _url_api(empresa, lancamento):
    return reverse("contabilidade:marcacao-dmpl", args=[empresa.id, lancamento.id])


def _url_tela(empresa, lancamento):
    return reverse("contabilidade_web:lancamento_marcacao_dmpl", args=[empresa.id, lancamento.id])


def _corpo(marcacoes):
    return {
        "marcacoes": [
            {"linha": m["linha"], "coluna": m["coluna"], "valor": str(m["valor"])}
            for m in marcacoes
        ]
    }


def _tentar_pelo_servico(tentativa, lancamento, usuario):
    if tentativa == "remover":
        return remover_marcacoes_da_dmpl(lancamento=lancamento, usuario=usuario)
    marcacoes = [_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")]
    if tentativa == "nova":
        marcacoes = [_marc(LINHA_AQUISICAO, TESOURARIA, "-400.00")]
    return salvar_marcacoes_da_dmpl(lancamento=lancamento, marcacoes=marcacoes, usuario=usuario)


def _tentar_pela_api(client, tentativa, empresa, lancamento):
    url = _url_api(empresa, lancamento)
    if tentativa == "remover":
        return client.delete(url)
    valor = "-400.00" if tentativa == "nova" else "-500.00"
    corpo = _corpo([_marc(LINHA_AQUISICAO, TESOURARIA, valor)])
    return client.put(url, data=corpo, content_type="application/json")


# ---------------------------------------------------------------------------
# Critérios 1 e 2 — competência ENCERRADA ou ENTREGUE: trocar, remover e
# marcar pela primeira vez, no serviço e na API (as 12 combinações medidas)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("estado", ["encerrada", "entregue"])
@pytest.mark.parametrize("tentativa", ["trocar", "remover", "nova"])
@pytest.mark.parametrize("via", ["servico", "api"])
def test_criterio1_e_2_marcacao_em_competencia_fechada_e_recusada_e_nada_muda(
    client, estado, tentativa, via
):
    # "nova" precisa de um lançamento SEM marcação: p2 fica de fora.
    marcar = ("p1",) if tentativa == "nova" else ("p1", "p2")
    empresa, contas, gestor, p1, p2 = _cenario(marcar=marcar)
    _fechar(empresa, gestor, 2, entregue=(estado == "entregue"))
    alvo = p2 if tentativa == "nova" else p1

    marcacoes_antes = _marcacoes(alvo)
    trilhas_antes = _trilhas()
    foto_antes = _foto(empresa)

    if via == "servico":
        with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
            _tentar_pelo_servico(tentativa, alvo, gestor)
        mensagem = str(erro.value)
    else:
        _autenticar(client, empresa.escritorio, f"gestor-dl071-{estado}-{tentativa}")
        resposta = _tentar_pela_api(client, tentativa, empresa, alvo)
        assert resposta.status_code == 409, resposta.content
        mensagem = resposta.json()["detail"]

    # A mensagem NOMEIA o período, como a da DL-065 (E4) — recusa sem nome
    # devolve o trabalho ao contador sem caminho.
    assert "02/2026" in mensagem
    assert estado in mensagem
    if estado == "entregue":
        # Critério 2 / lição A3 da DL-065: competência entregue NÃO se reabre
        # (RC-101); mandar reabrir seria mandar o contador a uma porta que o
        # próprio produto fecha.
        assert "Reabra" not in mensagem
        assert "não pode ser reaberta" in mensagem
    else:
        assert "Reabra a competência 02/2026" in mensagem

    assert _marcacoes(alvo) == marcacoes_antes, "a recusa não pode gravar nada"
    assert _trilhas() == trilhas_antes, "a recusa não deixa registro na trilha"
    assert _foto(empresa) == foto_antes, "a DMPL do período fechado não pode mudar"


def test_criterio1_o_controle_positivo_com_a_competencia_aberta_a_troca_passa():
    """Sem este controle, os testes de recusa poderiam estar medindo um
    cenário que NUNCA aceita a marcação (dado errado, não guarda)."""
    empresa, contas, gestor, p1, p2 = _cenario()
    assert Competencia.objects.get(empresa=empresa, ano=ANO, mes=2).estado == "aberta"

    salvar_marcacoes_da_dmpl(
        lancamento=p1,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
        usuario=gestor,
    )
    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]


def test_criterio2_competencia_entregue_vence_a_encerrada_na_mensagem():
    """Fevereiro ENTREGUE e março apenas ENCERRADA: reabrir março não adianta,
    fevereiro continua barrando. A mensagem tem de falar do caminho que
    existe (ajuste na competência aberta), e não mandar reabrir março."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2, entregue=True)
    _fechar(empresa, gestor, 3)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert "02/2026" in mensagem and "entregue" in mensagem
    assert "Reabra" not in mensagem
    assert "lançamento de ajuste" in mensagem


def test_criterio2_a_mensagem_de_encerrada_nomeia_todas_as_competencias_a_reabrir():
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    _fechar(empresa, gestor, 3)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert "02/2026 e 03/2026" in mensagem
    assert "Reabra as competências 02/2026 e 03/2026" in mensagem


# ---------------------------------------------------------------------------
# Critério 3 — a fronteira é a da apuração: o exercício desde 01/01 até o mês
# ---------------------------------------------------------------------------


def test_criterio3_fevereiro_aberto_com_marco_encerrado_no_mesmo_exercicio_e_recusado():
    """`apurar_dmpl(ano, mes)` lê de 01/01 até o fim de `mes`: a DMPL de março
    LÊ o lançamento de fevereiro. Fechar março congela essa DMPL, e trocar a
    marcação de fevereiro a reescreveria — mesmo com fevereiro aberto."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 3)
    assert Competencia.objects.get(empresa=empresa, ano=ANO, mes=2).estado == "aberta"
    foto_antes = _foto(empresa)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert "03/2026" in mensagem and "encerrada" in mensagem
    # Fevereiro está aberto: a mensagem manda reabrir março, que é o que barra.
    assert "Reabra a competência 03/2026" in mensagem
    assert "Reabra a competência 02/2026" not in mensagem
    assert _marcacoes(p1)[0] == (LINHA_AQUISICAO, TESOURARIA, "-1500.00")
    assert _foto(empresa) == foto_antes


def test_criterio3_competencia_posterior_de_outro_exercicio_nao_trava():
    """A DMPL de 2027 começa em 01/01/2027 e não lê um lançamento de 2026 —
    medido adiante, em `test_criterio3_a_fronteira_da_guarda_e_a_da_apuracao`."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 3, ano=2027)
    _fechar(empresa, gestor, 12, ano=2025)

    salvar_marcacoes_da_dmpl(
        lancamento=p1,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
        usuario=gestor,
    )
    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]


def test_criterio3_competencia_anterior_do_mesmo_exercicio_nao_trava():
    """A DMPL até janeiro não lê um lançamento de fevereiro: janeiro fechado
    não impede marcar fevereiro."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 1)

    salvar_marcacoes_da_dmpl(
        lancamento=p1,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
        usuario=gestor,
    )
    remover_marcacoes_da_dmpl(lancamento=p2, usuario=gestor)
    assert _marcacoes(p2) == []


def test_criterio3_a_fronteira_da_guarda_e_a_da_apuracao():
    """A regra 2 do plano: a guarda não pode filtrar por um critério diferente
    do que a apuração filtra (lição A1 da DL-065). Aqui a fronteira não é
    afirmada, é MEDIDA: para cada competência candidata, vê-se se a DMPL dela
    contém o lançamento em alguma célula e se fechá-la faz a guarda recusar.
    As duas respostas têm de coincidir em todas.

    Derivado da PROPRIEDADE (a DMPL do período lê o lançamento), e não de uma
    lista de meses: se a apuração mudar a janela, este teste acusa."""
    empresa, contas, gestor, p1, p2 = _cenario()

    def _lido_pela_dmpl(ano, mes):
        dmpl = apurar_dmpl(empresa=empresa, ano=ano, mes=mes)
        return any(
            p1.id in ids
            for linha in dmpl["linhas"]
            for ids in linha.get("lancamentos", {}).values()
        )

    candidatas = [(2025, 12), (2026, 1), (2026, 2), (2026, 3), (2026, 12), (2027, 1), (2027, 12)]
    lidas = {c for c in candidatas if _lido_pela_dmpl(*c)}
    # Sanidade da medida: a janela real, de fevereiro de 2026 a dezembro de 2026.
    assert lidas == {(2026, 2), (2026, 3), (2026, 12)}, lidas

    for ano, mes in candidatas:
        _forcar_estado(empresa, ano, mes, EstadoCompetencia.ENCERRADA)
        try:
            salvar_marcacoes_da_dmpl(
                lancamento=p1,
                marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
                usuario=gestor,
            )
            recusou = False
        except ClassificacaoAlteraPeriodoFechado:
            recusou = True
        finally:
            _forcar_estado(empresa, ano, mes, EstadoCompetencia.ABERTA)
        assert recusou == ((ano, mes) in lidas), (
            f"competência {mes:02d}/{ano}: a DMPL dela "
            f"{'lê' if (ano, mes) in lidas else 'não lê'} o lançamento, mas a guarda "
            f"{'recusou' if recusou else 'aceitou'}"
        )


def test_criterio3_lancamento_sem_competencia_gravada_e_achado_pela_data():
    """Lição A1 da DL-065: `LancamentoContabil.competencia_id` é anulável, e
    a apuração lê o movimento pela DATA, nunca pela FK. Lançamento legado sem
    competência gravada entra na DMPL do período encerrado do mesmo jeito."""
    empresa, contas, gestor, p1, p2 = _cenario(marcar=())
    legado = LancamentoContabil.objects.create(
        empresa=empresa,
        data=date(2026, 2, 8),
        historico="Permuta legada sem competência gravada",
        competencia=None,
    )
    for conta, tipo, valor in (
        (contas["tesouraria"], TipoPartida.DEBITO, "900.00"),
        (contas["caixa"], TipoPartida.DEBITO, "200.00"),
        (contas["caixa"], TipoPartida.CREDITO, "900.00"),
        (contas["tesouraria"], TipoPartida.CREDITO, "200.00"),
    ):
        ItemLancamento.objects.create(lancamento=legado, conta=conta, tipo=tipo, valor=_dec(valor))
    _fechar(empresa, gestor, 2)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        salvar_marcacoes_da_dmpl(
            lancamento=legado,
            marcacoes=[
                _marc(LINHA_AQUISICAO, TESOURARIA, "-900.00"),
                _marc(LINHA_ALIENACAO, TESOURARIA, "200.00"),
            ],
            usuario=gestor,
        )
    assert "02/2026" in str(erro.value)
    assert not MarcacaoDmpl.objects.filter(lancamento=legado).exists()


# ---------------------------------------------------------------------------
# Critérios 4 e 5 — tudo aberto não muda; reaberta volta a aceitar
# ---------------------------------------------------------------------------


def test_criterio4_com_tudo_aberto_trocar_remover_e_marcar_seguem_aceitos():
    empresa, contas, gestor, p1, p2 = _cenario(marcar=("p1",))
    for competencia in Competencia.objects.filter(empresa=empresa):
        assert competencia.estado == EstadoCompetencia.ABERTA

    salvar_marcacoes_da_dmpl(
        lancamento=p1,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
        usuario=gestor,
    )
    salvar_marcacoes_da_dmpl(
        lancamento=p2,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-400.00")],
        usuario=gestor,
    )
    remover_marcacoes_da_dmpl(lancamento=p1, usuario=gestor)

    assert _marcacoes(p1) == []
    assert _marcacoes(p2) == [(LINHA_AQUISICAO, TESOURARIA, "-400.00")]


def test_criterio5_competencia_reaberta_depois_de_encerrada_aceita_de_novo():
    """A regra acompanha o ESTADO, não o registro de que houve recusa."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    with pytest.raises(ClassificacaoAlteraPeriodoFechado):
        _tentar_pelo_servico("trocar", p1, gestor)

    reabrir_competencia(
        empresa=empresa, ano=ANO, mes=2, usuario=gestor, motivo="Correção da marcação"
    )
    salvar_marcacoes_da_dmpl(
        lancamento=p1,
        marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
        usuario=gestor,
    )
    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]


# ---------------------------------------------------------------------------
# Critério 6 — a tela mostra a recusa na guia, com 200, sem gravar
# ---------------------------------------------------------------------------


def _texto(html):
    return " ".join(html.split())


@pytest.mark.parametrize("acao", ["salvar", "remover"])
@pytest.mark.parametrize("estado", ["encerrada", "entregue"])
def test_criterio6_tela_mostra_a_recusa_com_200_e_nao_grava(client, acao, estado):
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2, entregue=(estado == "entregue"))
    _autenticar(client, empresa.escritorio, f"gestor-dl071-tela-{acao}-{estado}")
    marcacoes_antes = _marcacoes(p1)
    trilhas_antes = _trilhas()
    foto_antes = _foto(empresa)

    dados = {"acao": acao, "linha": [LINHA_AQUISICAO], "coluna": [TESOURARIA], "valor": ["-500,00"]}
    resposta = client.post(_url_tela(empresa, p1), dados)

    assert resposta.status_code == 200
    html = _texto(resposta.content.decode())
    assert "Não é possível alterar" in html
    assert "02/2026" in html and estado in html
    if estado == "entregue":
        assert "Reabra" not in html
    else:
        assert "Reabra a competência 02/2026" in html
    assert _marcacoes(p1) == marcacoes_antes
    assert _trilhas() == trilhas_antes
    assert _foto(empresa) == foto_antes


def test_criterio6_tela_com_competencia_aberta_segue_gravando_e_redirecionando(client):
    empresa, contas, gestor, p1, p2 = _cenario()
    _autenticar(client, empresa.escritorio, "gestor-dl071-tela-aberta")
    dados = {
        "acao": "salvar",
        "linha": [LINHA_AQUISICAO],
        "coluna": [TESOURARIA],
        "valor": ["-500,00"],
    }
    resposta = client.post(_url_tela(empresa, p1), dados)
    assert resposta.status_code == 302
    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]


# ---------------------------------------------------------------------------
# Critério 7 — corrida com o fechamento (PostgreSQL, duas threads)
# ---------------------------------------------------------------------------


def _na_thread(alvo, resultado):
    """Roda `alvo` numa thread com conexão própria; guarda o que ela devolver
    ou levantar em `resultado` (nunca engole), e fecha a conexão ao fim."""

    def _corpo():
        try:
            resultado["valor"] = alvo()
        except Exception as exc:  # noqa: BLE001 — vai para o assert, não some
            resultado["erro"] = exc
        finally:
            connection.close()

    return threading.Thread(target=_corpo)


@pytest.mark.django_db(transaction=True)
def test_criterio7_fechamento_que_venceu_a_corrida_recusa_a_marcacao():
    """O desfecho PROIBIDO é o mês terminar encerrado com a marcação trocada
    DEPOIS do fechamento. A guarda lê o estado sob `FOR SHARE`, que espera o
    `FOR UPDATE` do fechamento: a marcação acorda vendo `encerrada` e recusa.

    Sem a trava (leitura simples do estado), a marcação leria `aberta`, passaria
    e gravaria por cima de um período que acabou de fechar — o primeiro
    `assert` abaixo (a marcação continua BLOQUEADA) é o que cai."""
    empresa, contas, gestor, p1, p2 = _cenario()
    competencia = Competencia.objects.get(empresa=empresa, ano=ANO, mes=2)

    fechamento_em_curso = threading.Event()
    liberar_fechamento = threading.Event()
    do_fechamento = {}

    def _fechar_e_segurar():
        with transaction.atomic():
            travada = Competencia.objects.select_for_update().get(pk=competencia.pk)
            travada.estado = EstadoCompetencia.ENCERRADA
            travada.save(update_fields=["estado"])
            fechamento_em_curso.set()
            liberar_fechamento.wait(timeout=30)

    def _marcar():
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '20s'")
        return salvar_marcacoes_da_dmpl(
            lancamento=p1,
            marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
            usuario=gestor,
        )

    da_marcacao = {}
    t_fechamento = _na_thread(_fechar_e_segurar, do_fechamento)
    t_marcacao = _na_thread(_marcar, da_marcacao)
    t_fechamento.start()
    try:
        assert fechamento_em_curso.wait(timeout=30), "o fechamento não chegou a segurar a linha"
        t_marcacao.start()
        time.sleep(0.6)
        assert t_marcacao.is_alive(), (
            "a marcação não esperou o fechamento: leu o estado sem trava e "
            "decidiria sobre um período prestes a fechar"
        )
    finally:
        liberar_fechamento.set()
        t_fechamento.join(timeout=30)
        t_marcacao.join(timeout=30)
    assert not t_fechamento.is_alive() and not t_marcacao.is_alive(), "thread não concluiu"
    assert "erro" not in do_fechamento, do_fechamento

    assert isinstance(da_marcacao.get("erro"), ClassificacaoAlteraPeriodoFechado), da_marcacao
    assert "encerrada" in str(da_marcacao["erro"])
    assert Competencia.objects.get(pk=competencia.pk).estado == EstadoCompetencia.ENCERRADA
    assert _marcacoes(p1)[0] == (LINHA_AQUISICAO, TESOURARIA, "-1500.00"), "marcação trocada"


@pytest.mark.django_db(transaction=True)
def test_criterio7_a_marcacao_em_curso_segura_a_competencia_aberta():
    """O outro lado da corrida, pelo MECANISMO: enquanto a marcação não
    commita, um fechamento concorrente é obrigado a esperar (a linha da
    competência fica com `FOR SHARE` até o fim da transação), e o resultado
    legítimo é "marcou, depois fechou"."""
    empresa, contas, gestor, p1, p2 = _cenario()
    competencia = Competencia.objects.get(empresa=empresa, ano=ANO, mes=2)

    marcou = threading.Event()
    liberar = threading.Event()
    da_marcacao = {}

    def _marcar_e_segurar():
        with transaction.atomic():
            salvar_marcacoes_da_dmpl(
                lancamento=p1,
                marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
                usuario=gestor,
            )
            marcou.set()
            liberar.wait(timeout=30)

    t = _na_thread(_marcar_e_segurar, da_marcacao)
    t.start()
    try:
        assert marcou.wait(timeout=30), "a marcação não terminou a tempo"
        with pytest.raises(OperationalError):
            with transaction.atomic():
                Competencia.objects.select_for_update(nowait=True).get(pk=competencia.pk)
    finally:
        liberar.set()
        t.join(timeout=30)
    assert not t.is_alive(), "thread não concluiu"
    assert "erro" not in da_marcacao, da_marcacao
    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]


# ---------------------------------------------------------------------------
# Critério 8 — lock_timeout estourado: recusa legível, nunca 500
# ---------------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_criterio8_lock_timeout_vira_recusa_no_servico_na_api_e_na_tela(client):
    """O `FOR SHARE` da guarda espera o `FOR UPDATE` de um fechamento em
    curso. Se a espera estoura o `lock_timeout`, o `OperationalError` cru do
    driver chegaria à view como 500 (lição N1 da DL-065). A guarda o traduz
    para a mesma recusa de período — 409 na API, mensagem na tela — dizendo
    para tentar de novo, e NÃO diz que a competência está encerrada, que seria
    falso."""
    empresa, contas, gestor, p1, p2 = _cenario()
    competencia = Competencia.objects.get(empresa=empresa, ano=ANO, mes=2)
    _autenticar(client, empresa.escritorio, "gestor-dl071-timeout")

    segurando = threading.Event()
    largar = threading.Event()
    da_thread = {}

    def _segurar():
        with transaction.atomic():
            Competencia.objects.select_for_update().get(pk=competencia.pk)
            segurando.set()
            largar.wait(timeout=60)

    t = _na_thread(_segurar, da_thread)
    t.start()
    try:
        assert segurando.wait(timeout=30), "a outra transação não segurou a competência"
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '200ms'")

        with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
            _tentar_pelo_servico("trocar", p1, gestor)
        assert "Tente de novo" in str(erro.value)
        assert "02/2026" in str(erro.value)
        assert "encerrada" not in str(erro.value)

        resposta = _tentar_pela_api(client, "trocar", empresa, p1)
        assert resposta.status_code == 409, resposta.content
        assert "Tente de novo" in resposta.json()["detail"]

        resposta = _tentar_pela_api(client, "remover", empresa, p1)
        assert resposta.status_code == 409, resposta.content

        dados = {
            "acao": "salvar",
            "linha": [LINHA_AQUISICAO],
            "coluna": [TESOURARIA],
            "valor": ["-500,00"],
        }
        resposta = client.post(_url_tela(empresa, p1), dados)
        assert resposta.status_code == 200
        assert "Tente de novo" in _texto(resposta.content.decode())
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET lock_timeout")
        largar.set()
        t.join(timeout=60)
    assert not t.is_alive(), "thread não concluiu"
    assert "erro" not in da_thread, da_thread
    assert _marcacoes(p1)[0] == (LINHA_AQUISICAO, TESOURARIA, "-1500.00"), "recusa não grava"


@pytest.mark.django_db(transaction=True)
def test_a2_lock_timeout_na_trava_do_lancamento_vira_recusa_e_nao_500(client):
    """A2 da auditoria da DL-071 (critério 8 por inteiro). A trava do
    LANÇAMENTO (`select_for_update` em `salvar_marcacoes_da_dmpl`) roda ANTES
    da guarda e, sob `lock_timeout`, deixava o `OperationalError` cru chegar
    à view: 500 na API (PUT e DELETE) e na tela. Agora é a mesma recusa de
    período (409 na API, mensagem na tela) com texto próprio — "tente de
    novo", sem dizer que o período está encerrado — e NADA é gravado.

    A ordem dos blocos importa: a API vem primeiro, então, antes da correção,
    a falha aparece como `500 == 409`, que é a prova do dano."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _autenticar(client, empresa.escritorio, "gestor-dl071-timeout-lancamento")
    # Sem isto o cliente de teste relança a exceção em vez de devolver o 500
    # que o usuário veria — e a medida precisa ser a resposta HTTP.
    client.raise_request_exception = False
    marcacoes_antes = _marcacoes(p1)
    trilhas_antes = _trilhas()

    segurando = threading.Event()
    largar = threading.Event()
    da_thread = {}

    def _segurar_o_lancamento():
        with transaction.atomic():
            LancamentoContabil.objects.select_for_update().get(pk=p1.pk)
            segurando.set()
            largar.wait(timeout=60)

    t = _na_thread(_segurar_o_lancamento, da_thread)
    t.start()
    try:
        assert segurando.wait(timeout=30), "a outra transação não segurou o lançamento"
        with connection.cursor() as cursor:
            cursor.execute("SET lock_timeout = '200ms'")

        resposta = _tentar_pela_api(client, "trocar", empresa, p1)
        assert resposta.status_code == 409, resposta.content
        assert "Tente de novo" in resposta.json()["detail"]
        assert "encerrad" not in resposta.json()["detail"]

        resposta = _tentar_pela_api(client, "remover", empresa, p1)
        assert resposta.status_code == 409, resposta.content

        dados = {
            "acao": "salvar",
            "linha": [LINHA_AQUISICAO],
            "coluna": [TESOURARIA],
            "valor": ["-500,00"],
        }
        resposta = client.post(_url_tela(empresa, p1), dados)
        assert resposta.status_code == 200, resposta.content
        assert "Tente de novo" in _texto(resposta.content.decode())

        dados = {
            "acao": "remover",
            "linha": [LINHA_AQUISICAO],
            "coluna": [TESOURARIA],
            "valor": ["-500,00"],
        }
        resposta = client.post(_url_tela(empresa, p1), dados)
        assert resposta.status_code == 200, resposta.content
        assert "Tente de novo" in _texto(resposta.content.decode())

        with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
            _tentar_pelo_servico("trocar", p1, gestor)
        assert "Tente de novo" in str(erro.value)
        assert "encerrad" not in str(erro.value)
        assert "entregue" not in str(erro.value)
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET lock_timeout")
        largar.set()
        t.join(timeout=60)
    assert not t.is_alive(), "thread não concluiu"
    assert "erro" not in da_thread, da_thread
    assert _marcacoes(p1) == marcacoes_antes, "recusa por lock não pode gravar nem remover"
    assert _trilhas() == trilhas_antes, "recusa por lock não pode gerar trilha"


# ---------------------------------------------------------------------------
# Critério 9 — isolamento: 404 antes de qualquer consulta de período
# ---------------------------------------------------------------------------


def _sql_toca_competencia(consultas):
    tabela = Competencia._meta.db_table
    return [c["sql"] for c in consultas if tabela in c["sql"]]


@pytest.mark.parametrize("metodo", ["put", "delete"])
def test_criterio9_lancamento_de_outra_empresa_do_mesmo_escritorio_e_404_sem_consultar_periodo(
    client, metodo
):
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    irma = Empresa.objects.create(
        escritorio=empresa.escritorio, razao_social="Irmã DL-071", cnpj=_cnpj_sintetico()
    )
    contas_irma = _plano_basico(irma)
    alheio = _lancar(
        irma,
        date(2026, 2, 7),
        "Lançamento da irmã",
        contas_irma["caixa"],
        contas_irma["capital"],
        "10",
    )
    _autenticar(client, empresa.escritorio, f"gestor-dl071-iso-{metodo}")

    with CaptureQueriesContext(connection) as consultas:
        if metodo == "put":
            resposta = client.put(
                _url_api(empresa, alheio),
                data=_corpo([_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")]),
                content_type="application/json",
            )
        else:
            resposta = client.delete(_url_api(empresa, alheio))

    assert resposta.status_code == 404, resposta.content
    assert _sql_toca_competencia(consultas.captured_queries) == []
    assert not MarcacaoDmpl.objects.filter(lancamento=alheio).exists()


def test_criterio9_lancamento_de_outro_escritorio_e_404_na_api_e_na_tela(client):
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    outra = _empresa("Outro escritório DL-071")
    contas_outra = _plano_basico(outra)
    alheio = _lancar(
        outra,
        date(2026, 2, 7),
        "Lançamento alheio",
        contas_outra["caixa"],
        contas_outra["capital"],
        "10",
    )
    _autenticar(client, empresa.escritorio, "gestor-dl071-iso-escritorio")

    with CaptureQueriesContext(connection) as consultas:
        pela_api = client.put(
            _url_api(empresa, alheio),
            data=_corpo([_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")]),
            content_type="application/json",
        )
        pela_tela = client.post(_url_tela(empresa, alheio), {"acao": "remover"})

    assert pela_api.status_code == 404
    assert pela_tela.status_code == 404
    assert _sql_toca_competencia(consultas.captured_queries) == []


# ---------------------------------------------------------------------------
# Critério 10 — o custo da guarda não cresce com o histórico
# ---------------------------------------------------------------------------


def test_competencia_fechada_de_outra_empresa_nao_trava_nem_e_travada():
    """A3 da auditoria da DL-071: a guarda filtra as competências por
    `empresa_id` do lançamento. Sem esse filtro, a marcação da empresa A seria
    recusada por março fechado da empresa B e tomaria `FOR SHARE` na linha de
    fevereiro aberto dela — nenhum teste acusava. Aqui a outra empresa tem, na
    mesma janela do ano, fevereiro ABERTO (que a guarda travaria), março
    ENCERRADO e abril ENTREGUE: qualquer vazamento de empresa aparece."""
    empresa, contas, gestor, p1, p2 = _cenario()
    outra = _empresa("Outra empresa DL-071")
    gestor_outra = _gestor(outra, "gestor-dl071-outra-empresa")
    _forcar_estado(outra, ANO, 2, EstadoCompetencia.ABERTA)
    _fechar(outra, gestor_outra, 3)
    _fechar(outra, gestor_outra, 4, entregue=True)
    pks_da_outra = list(Competencia.objects.filter(empresa=outra).values_list("pk", flat=True))
    assert len(pks_da_outra) == 3

    with CaptureQueriesContext(connection) as consultas:
        salvar_marcacoes_da_dmpl(
            lancamento=p1,
            marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "-500.00")],
            usuario=gestor,
        )

    assert _marcacoes(p1) == [(LINHA_AQUISICAO, TESOURARIA, "-500.00")]
    travas_alheias = [
        c["sql"]
        for c in consultas.captured_queries
        if "FOR SHARE" in c["sql"] and any(f"= {pk} FOR SHARE" in c["sql"] for pk in pks_da_outra)
    ]
    assert not travas_alheias, f"a guarda travou competência de outra empresa: {travas_alheias}"


def _consultas_da_guarda(lancamento):
    """Consultas pagas pela guarda sozinha. Importada aqui dentro para o
    arquivo carregar mesmo quando a guarda ainda não existe (a execução
    "antes da correção" precisa mostrar os demais testes falhando por si)."""
    from apps.contabilidade.services import _recusar_marcacao_da_dmpl_em_periodo_fechado

    with CaptureQueriesContext(connection) as consultas:
        with transaction.atomic():
            try:
                _recusar_marcacao_da_dmpl_em_periodo_fechado(lancamento)
            except ClassificacaoAlteraPeriodoFechado:
                pass
    return len(consultas)


@pytest.mark.django_db(transaction=True)
def test_criterio10_o_custo_nao_cresce_com_o_historico_de_competencias_fechadas():
    """Mesma empresa e mesmo lançamento com 1 e com 25 competências
    encerradas FORA da janela da DMPL (um e dois anos antes): o número de
    consultas da guarda é o mesmo. Lição N2 da DL-065 — o defeito que a
    auditoria mediu era justamente o crescimento com o histórico."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _forcar_estado(empresa, 2025, 12, EstadoCompetencia.ENCERRADA)
    com_uma = _consultas_da_guarda(p1)

    for ano in (2023, 2024):
        for mes in range(1, 13):
            _forcar_estado(empresa, ano, mes, EstadoCompetencia.ENCERRADA)
    assert Competencia.objects.filter(empresa=empresa, estado="encerrada").count() == 25
    com_vinte_e_cinco = _consultas_da_guarda(p1)

    assert com_vinte_e_cinco <= com_uma, (
        f"a guarda pagou {com_uma} consultas com 1 competência encerrada e "
        f"{com_vinte_e_cinco} com 25 — o custo não pode depender do histórico"
    )


@pytest.mark.django_db(transaction=True)
def test_criterio10_o_custo_da_recusa_nao_cresce_com_as_competencias_que_barram():
    """Mesma medida no caminho da RECUSA: 1 competência encerrada barrando
    contra 11 (de fevereiro a dezembro, a janela inteira da DMPL)."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _forcar_estado(empresa, ANO, 2, EstadoCompetencia.ENCERRADA)
    com_uma = _consultas_da_guarda(p1)

    for mes in range(3, 13):
        _forcar_estado(empresa, ANO, mes, EstadoCompetencia.ENCERRADA)
    assert (
        Competencia.objects.filter(empresa=empresa, ano=ANO, mes__gte=2, estado="encerrada").count()
        == 11
    )
    com_onze = _consultas_da_guarda(p1)

    assert com_onze <= com_uma, (
        f"a recusa pagou {com_uma} consultas com 1 competência barrando e {com_onze} com 11"
    )


# ---------------------------------------------------------------------------
# Achados A4, B2 e B3 da auditoria da DL-071 (rodada 1)
# ---------------------------------------------------------------------------


def test_periodo_fechado_vem_antes_do_conteudo_invalido():
    """A4 da auditoria: a guarda vem ANTES da validação do conteúdo. Valor
    zero é conteúdo inválido (`MarcacaoDmplInvalida`), e com o período
    fechado a resposta tem de ser a recusa de período — o contador não deve
    ser mandado corrigir um conteúdo que não poderia entrar de qualquer jeito.
    Com a ordem trocada (M7), a recusa de conteúdo sairia no lugar."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    marcacoes_antes = _marcacoes(p1)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado):
        salvar_marcacoes_da_dmpl(
            lancamento=p1,
            marcacoes=[_marc(LINHA_AQUISICAO, TESOURARIA, "0.00")],
            usuario=gestor,
        )
    assert _marcacoes(p1) == marcacoes_antes


def test_b2_estado_gravado_que_nao_e_encerrada_nem_entregue_e_nomeado_sem_reabra():
    """B2 da auditoria (lição A4 da DL-065): a mensagem nomeia o estado que
    está GRAVADO, como `Conta.clean()` faz, e não uma palavra fixa. `EM_
    ENCERRAMENTO` é reservado e só existe por ORM. Só `ENCERRADA` recebe a
    sugestão de reabrir; `reabrir_competencia` não reabre este estado, então
    mandar reabrir seria mandar o contador a uma porta que o produto fecha."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _forcar_estado(empresa, ANO, 2, EstadoCompetencia.EM_ENCERRAMENTO)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    rotulo = EstadoCompetencia.EM_ENCERRAMENTO.label.lower()
    assert "02/2026" in mensagem
    assert f"está {rotulo}" in mensagem, mensagem
    assert "Reabra" not in mensagem, mensagem
    assert "encerrada" not in mensagem, mensagem
    assert _marcacoes(p1)[0] == (LINHA_AQUISICAO, TESOURARIA, "-1500.00")


def test_b2_estados_misturados_nomeiam_cada_um_e_nao_mandam_reabrir():
    """B2 com dois estados que barram: a mensagem nomeia cada competência com
    o próprio estado, e não manda reabrir — reabrir só a encerrada não
    destrava a marcação, porque a outra continuaria barrando."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 3)
    _forcar_estado(empresa, ANO, 2, EstadoCompetencia.EM_ENCERRAMENTO)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert "02/2026 (em encerramento)" in mensagem, mensagem
    assert "03/2026 (encerrada)" in mensagem, mensagem
    assert "Reabra" not in mensagem, mensagem


def test_b3_duas_competencias_encerradas_concordam_no_plural():
    """B3 da auditoria: com duas competências, o sujeito e os verbos vão no
    plural — "as DMPLs de ... acumulam ... e incluem". No singular (um teste
    abaixo) continua "a DMPL de ... acumula ... e inclui"."""
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)
    _fechar(empresa, gestor, 3)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert (
        "as DMPLs de 02/2026 e 03/2026 acumulam o exercício desde janeiro e incluem este lançamento"
        in mensagem
    ), mensagem
    assert "a DMPL de 02/2026" not in mensagem


def test_b3_duas_competencias_entregues_concordam_no_plural():
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2, entregue=True)
    _fechar(empresa, gestor, 3, entregue=True)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert (
        "as DMPLs de 02/2026 e 03/2026 acumulam o exercício desde janeiro e incluem este lançamento"
        in mensagem
    ), mensagem
    assert "Reabra" not in mensagem


def test_b3_uma_competencia_concorda_no_singular():
    empresa, contas, gestor, p1, p2 = _cenario()
    _fechar(empresa, gestor, 2)

    with pytest.raises(ClassificacaoAlteraPeriodoFechado) as erro:
        _tentar_pelo_servico("trocar", p1, gestor)

    mensagem = str(erro.value)
    assert (
        "a DMPL de 02/2026 acumula o exercício desde janeiro e inclui este lançamento" in mensagem
    ), mensagem
    assert "as DMPLs" not in mensagem


# ---------------------------------------------------------------------------
# Portas: toda escrita da marcação passa pela regra
# ---------------------------------------------------------------------------


def test_nao_ha_admin_que_grave_marcacao_da_dmpl():
    """Lição E1 da DL-065: o admin escapava dos serviços. A `MarcacaoDmpl`
    não tem admin, então as únicas portas de escrita são o serviço, a API e a
    tela — as três passam por `salvar_marcacoes_da_dmpl`. Se alguém registrar
    um admin, este teste cai e obriga a decidir como a regra vale lá (o
    `ModelForm` grava por `full_clean()`, sem passar pelo serviço)."""
    assert MarcacaoDmpl not in admin.site._registry


@pytest.mark.django_db(transaction=True)
def test_erro_de_banco_que_nao_e_lock_sobe_intacto_e_nao_vira_recusa():
    """R1 da reconferência da DL-071: só `lock_timeout` (55P03) e deadlock
    (40P01) na trava do lançamento viram "tente de novo". Qualquer outro erro
    do banco — aqui um `statement_timeout` (57014) — precisa subir intacto, ou
    uma falha real seria mostrada ao contador como simples concorrência.
    Teste proposto pelo auditor, que o executou: passa no código e cai com o
    mutante que transforma todo `OperationalError` em recusa (A2c)."""
    empresa, contas, gestor, p1, p2 = _cenario()
    antes = _marcacoes(p1)
    segurando, largar, da_thread = threading.Event(), threading.Event(), {}

    def _segurar():
        with transaction.atomic():
            LancamentoContabil.objects.select_for_update().get(pk=p1.pk)
            segurando.set()
            largar.wait(timeout=60)

    t = _na_thread(_segurar, da_thread)
    t.start()
    try:
        assert segurando.wait(timeout=30)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '200ms'")  # SQLSTATE 57014, não 55P03
        with pytest.raises(OperationalError) as erro:
            _tentar_pelo_servico("trocar", p1, gestor)
        assert erro.value.__cause__.sqlstate == "57014"
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET statement_timeout")
        largar.set()
        t.join(timeout=60)
    assert not t.is_alive()
    assert _marcacoes(p1) == antes
