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
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
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
