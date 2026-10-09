"""DL-089 (BL-73) — estornar lançamento de origem automática exige permissão própria.

Critério 4 do plano: sem a permissão nova, o estorno de lançamento automático dá 403 e nada
muda; com ela, passa e o estorno fica marcado (herda origem e documento do original).

Papéis que estornam automático: ADMINISTRADOR e GESTOR (matriz de RC-102, em
`apps.contabilidade.permissoes.PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA`). Lançamento manual
continua estornável por quem lança (`PodeEscriturar`), sem mudança.

A verificação é do SERVIDOR: a API e o serviço `estornar_lancamento` recusam, e a recusa do
serviço vale para qualquer caminho que o chame. A tela não tem ação de estorno hoje (confirmado
por busca no código), então não há ação de tela a proteger nesta etapa. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import (
    LancamentoContabil,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.permissoes import (
    PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA,
    papel_pode_estornar_origem_automatica,
)
from apps.contabilidade.services import (
    EstornoDeOrigemAutomaticaNaoPermitido,
    criar_lancamento,
    estornar_lancamento,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
LOTE = TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório DL-089 permissão", "89896000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Permissão Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    return {"escritorio": escritorio, "empresa": empresa, "contas": contas}


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _automatico(cenario, identificador=1):
    contas = cenario["contas"]
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Compra importada (sintética)",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(LOTE, identificador),
    )


def _manual(cenario):
    contas = cenario["contas"]
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Lançamento digitado (sintético)",
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )


def _url_estorno(cenario, lancamento):
    return reverse("contabilidade:estornar", args=[cenario["empresa"].id, lancamento.id])


def _estornos_de(lancamento):
    return LancamentoContabil.objects.filter(estorno_de=lancamento).count()


def _total_de_lancamentos(cenario):
    return LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()


# ---------------------------------------------------------------------------
# A função de decisão (fonte única)
# ---------------------------------------------------------------------------


def test_papeis_que_estornam_automatico_sao_administrador_e_gestor():
    assert set(PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA) == {Papel.ADMINISTRADOR, Papel.GESTOR}


@pytest.mark.parametrize(
    "papel, esperado",
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, False),
        (Papel.FINANCEIRO, False),
        (Papel.PARALEGAL, False),
        (Papel.CLIENTE, False),
        (None, False),
    ],
)
def test_funcao_de_decisao_responde_por_papel(papel, esperado):
    assert papel_pode_estornar_origem_automatica(papel) is esperado


# ---------------------------------------------------------------------------
# Serviço: a recusa vale para qualquer chamador, não só para a view
# ---------------------------------------------------------------------------


def test_servico_sem_papel_recusa_estorno_automatico_e_nada_muda(cenario):
    original = _automatico(cenario)
    antes = _total_de_lancamentos(cenario)

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(original)

    assert _total_de_lancamentos(cenario) == antes
    assert _estornos_de(original) == 0


@pytest.mark.parametrize(
    "papel", [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE]
)
def test_servico_recusa_estorno_automatico_para_papel_sem_permissao(cenario, papel):
    original = _automatico(cenario)
    antes = _total_de_lancamentos(cenario)

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(original, papel=papel)

    assert _total_de_lancamentos(cenario) == antes
    assert _estornos_de(original) == 0


@pytest.mark.parametrize("papel", [Papel.ADMINISTRADOR, Papel.GESTOR])
def test_servico_estorna_automatico_para_papel_com_permissao_e_herda_a_marca(cenario, papel):
    original = _automatico(cenario, identificador=77)

    estorno = estornar_lancamento(original, papel=papel)

    estorno.refresh_from_db()
    assert estorno.estorno_de_id == original.pk
    assert estorno.origem == OrigemLancamento.IMPORTACAO
    assert estorno.documento_origem_tipo == LOTE
    assert estorno.documento_origem_id == "77"


def test_recusa_de_permissao_vem_antes_de_estado_do_lancamento(cenario):
    """Quem não pode estornar automático não recebe informação sobre o estado do
    lançamento: a recusa é 403, mesmo que o original já tenha sido estornado."""
    original = _automatico(cenario)
    estornar_lancamento(original, papel=Papel.GESTOR)

    with pytest.raises(EstornoDeOrigemAutomaticaNaoPermitido):
        estornar_lancamento(original, papel=Papel.ANALISTA)


# ---------------------------------------------------------------------------
# API: 403 sem a permissão, nada muda; com ela, passa e fica marcado
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "papel",
    [Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL, Papel.CLIENTE],
)
def test_api_dar_403_no_estorno_automatico_sem_permissao_e_nada_muda(client, cenario, papel):
    original = _automatico(cenario)
    antes = _total_de_lancamentos(cenario)
    _usuario(cenario["escritorio"], papel, f"sem-permissao-{papel}")
    assert client.login(username=f"sem-permissao-{papel}", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 403
    assert _total_de_lancamentos(cenario) == antes
    assert _estornos_de(original) == 0
    assert RegistroAuditoria.objects.filter(acao="lancamento.estornado").count() == 0


@pytest.mark.parametrize("papel", [Papel.ADMINISTRADOR, Papel.GESTOR])
def test_api_passa_no_estorno_automatico_com_permissao_e_fica_marcado(client, cenario, papel):
    original = _automatico(cenario, identificador=55)
    _usuario(cenario["escritorio"], papel, f"com-permissao-{papel}")
    assert client.login(username=f"com-permissao-{papel}", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 201
    corpo = response.json()
    assert corpo["origem"] == OrigemLancamento.IMPORTACAO
    assert corpo["documento_de_origem"] == {"tipo": LOTE, "identificador": "55"}
    estorno = LancamentoContabil.objects.get(pk=corpo["id"])
    assert estorno.estorno_de_id == original.pk
    trilha = RegistroAuditoria.objects.get(acao="lancamento.estornado")
    assert trilha.detalhes["origem"] == OrigemLancamento.IMPORTACAO
    assert trilha.detalhes["lancamento_original_id"] == original.pk


def test_api_estorno_manual_continua_livre_para_quem_lanca(client, cenario):
    """Sem regressão: lançamento manual segue estornável por ANALISTA (PodeEscriturar)."""
    original = _manual(cenario)
    _usuario(cenario["escritorio"], Papel.ANALISTA, "analista-manual")
    assert client.login(username="analista-manual", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 201
    assert response.json()["origem"] == OrigemLancamento.MANUAL
    assert response.json()["documento_de_origem"] is None


def test_api_automatico_ja_estornado_por_quem_nao_pode_da_403_nao_400(client, cenario):
    original = _automatico(cenario)
    estornar_lancamento(original, papel=Papel.GESTOR)
    _usuario(cenario["escritorio"], Papel.ANALISTA, "analista-repetido")
    assert client.login(username="analista-repetido", password=SENHA)

    response = client.post(_url_estorno(cenario, original))

    assert response.status_code == 403
    assert _estornos_de(original) == 1
