"""DL-091, correção da rodada 1, A11: data de entrada posterior a hoje é recusada.

Uma data digitada errada (p. ex., 2062) coloca a compra num mês que a lista não mostra, e a nota
"some" sem aviso. A recusa é de serviço, e a API e a tela a herdam, com a mensagem nomeada.

O teto é HOJE (em São Paulo). Quando a própria emissão já é posterior a hoje (relógio do emitente
adiantado), o teto é a emissão: a data-padrão, que é a emissão, não pode ser recusada.

O relógio é fixo (AGENTS.md §7): `timezone.now()` é controlado pelo teste.
"""

import json
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

FUSO = ZoneInfo("America/Sao_Paulo")
MOTIVO = entradas.MOTIVO_DATA_POSTERIOR_A_HOJE


@pytest.fixture
def hoje_e_13_10_2026(monkeypatch):
    """Relógio fixo: 13/10/2026, meio-dia em São Paulo."""
    instante = datetime(2026, 10, 13, 12, 0, tzinfo=FUSO)
    monkeypatch.setattr(timezone, "now", lambda: instante)
    return instante


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Data futura rodada 1 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )


def _trilhas_de_data():
    """Quantas trocas de data ficaram na trilha de auditoria (a recusa não pode deixar nenhuma)."""
    return RegistroAuditoria.objects.filter(acao="escrituracao_nfe.data_entrada_definida").count()


# ---------------------------------------------------------------------------
# Serviço
# ---------------------------------------------------------------------------


def test_criacao_com_data_posterior_a_hoje_e_recusada_com_motivo_nomeado(
    escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7101")

    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        servico.criar_rascunho(
            vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 10, 14)
        )

    assert erro.value.mensagem == MOTIVO
    assert not EscrituracaoNFe.objects.filter(vinculo=vinculo(documento, empresa)).exists()


def test_data_de_hoje_e_aceita(escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7102")

    esc = servico.criar_rascunho(
        vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 10, 13)
    )

    assert esc.data_entrada == date(2026, 10, 13)


def test_troca_de_data_para_2062_e_recusada_e_a_data_anterior_fica(
    escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    """O caso do erro de digitação: 2062 em vez de 2026. A data antiga fica e a trilha não
    cresce."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7103")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    trilhas_antes = _trilhas_de_data()

    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        entradas.definir_data_de_entrada(esc, date(2062, 3, 15), usuario=usuario_gestor_a)

    assert erro.value.mensagem == MOTIVO
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 15)
    assert _trilhas_de_data() == trilhas_antes


def test_emissao_futura_aceita_a_propria_emissao_como_data_e_recusa_o_dia_seguinte(
    escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    """Relógio do emitente adiantado: a nota sai com dhEmi de 20/10/2026. O padrão (= emissão) é
    aceito; um dia depois da emissão é recusado."""
    documento = _nota(
        escritorio_a,
        usuario_gestor_a,
        empresa,
        numero="7104",
        dh_emi="2026-10-20T10:00:00-03:00",
    )

    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    assert esc.data_entrada == date(2026, 10, 20)

    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        entradas.definir_data_de_entrada(esc, date(2026, 10, 21), usuario=usuario_gestor_a)
    assert erro.value.mensagem == MOTIVO


def test_compra_com_data_anterior_a_emissao_continua_com_o_motivo_proprio(
    escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    """Controle: a recusa de data anterior à emissão não foi substituída pela de data futura."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7105")

    with pytest.raises(servico.EntradaInvalidaNFe) as erro:
        servico.criar_rascunho(
            vinculo(documento, empresa), usuario=usuario_gestor_a, data_entrada=date(2026, 3, 14)
        )

    assert erro.value.mensagem == entradas.MOTIVO_DATA_ANTERIOR_A_EMISSAO


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def test_api_recusa_data_futura_na_criacao_e_na_troca_com_400_e_nada_muda(
    client, escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7106")
    client.force_login(usuario_gestor_a)

    criacao = _post(
        client,
        reverse("fiscal_api:nfe_escrituracao_lista", args=[empresa.pk]),
        {"vinculo_id": vinculo(documento, empresa).pk, "data_entrada": "2062-03-15"},
    )
    assert criacao.status_code == 400
    assert MOTIVO in json.dumps(json.loads(criacao.content), ensure_ascii=False)
    assert not EscrituracaoNFe.objects.filter(vinculo=vinculo(documento, empresa)).exists()

    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    troca = _post(
        client,
        reverse("fiscal_api:nfe_escrituracao_data_entrada", args=[empresa.pk, esc.pk]),
        {"data_entrada": "2062-03-15"},
    )
    assert troca.status_code == 400
    assert MOTIVO in json.dumps(json.loads(troca.content), ensure_ascii=False)
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 15)


# ---------------------------------------------------------------------------
# Tela
# ---------------------------------------------------------------------------


def test_tela_recusa_data_futura_na_troca_com_a_mensagem_no_campo(
    client, escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7107")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk]),
        {"acao": "data_entrada", "data_entrada": "15/03/2062"},
    )

    assert resposta.status_code == 400
    texto = resposta.content.decode("utf-8")
    assert MOTIVO in texto
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 15)


def test_usuario_sem_escrita_nao_chega_a_recusa_de_data(
    client, escritorio_a, usuario_gestor_a, empresa, hoje_e_13_10_2026
):
    """Controle de permissão: quem só consulta recebe 403 antes de qualquer regra de data."""
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="7108")
    servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    leitor = usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-a11-rodada1")
    client.force_login(leitor)

    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk]),
        {"acao": "data_entrada", "data_entrada": "15/03/2062"},
    )

    assert resposta.status_code == 403
