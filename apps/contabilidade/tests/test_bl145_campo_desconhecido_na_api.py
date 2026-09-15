"""Achado R5-6 da auditoria DL-017, rodada 5 (BL-145 — minha parte, a
política combinada com o `especialista-frontend`, que já recusa campo
desconhecido no corpo da TELA).

Medido pelo auditor: a API aceitava e IGNORAVA em silêncio campo
desconhecido no corpo (`empresa`, `id`, `criado_por`, `estornado` no
topo; `xpto` dentro de um item), enquanto a tela já recusa. É a MESMA
classe do achado 5 (BL-116 — "nenhum dado enviado numa requisição deixa
de ser lido ou recusado"), pela superfície da API.

O agravante concreto: quem manda `"chave_idempotencia"` NO CORPO (em vez
do cabeçalho `Idempotency-Key`, o único contrato válido de BL-41) não era
avisado e recebia a DUPLICIDADE que a chave existe para impedir — dois
POSTs com o mesmo corpo (incluindo o mesmo `"chave_idempotencia"` inútil)
criavam DOIS lançamentos. Corrigido pela MESMA recusa genérica: `"chave_
idempotencia"` no corpo é, por construção, um campo não reconhecido.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import (
    Conta,
    ItemLancamento,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
)
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório BL-145", cnpj="13131313000144")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa BL-145 Ltda", cnpj="13141516000177"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    receita = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    usuario = get_user_model().objects.create_user(
        username="gestor-bl145", email="gestor-bl145@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"escritorio": escritorio, "empresa": empresa, "caixa": caixa, "receita": receita}


def _cliente_autenticado(client, cenario):
    assert client.login(username="gestor-bl145", password="senha-forte-123")


def _sem_nada_gravado():
    return not LancamentoContabil.objects.exists() and not ItemLancamento.objects.exists()


def _corpo_valido(cenario, extra_topo=None, extra_item=None):
    corpo = {
        "data": "2026-01-15",
        "historico": "R5-6 / BL-145",
        "itens": [
            {
                "conta": cenario["caixa"].id,
                "tipo": "debito",
                "valor": "10.00",
                **(extra_item or {}),
            },
            {"conta": cenario["receita"].id, "tipo": "credito", "valor": "10.00"},
        ],
        **(extra_topo or {}),
    }
    return corpo


def _post(client, cenario, corpo, chave_header=None):
    extra = {}
    if chave_header is not None:
        extra["HTTP_IDEMPOTENCY_KEY"] = chave_header
    return client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        corpo,
        content_type="application/json",
        **extra,
    )


@pytest.mark.parametrize(
    "campo_extra", ["empresa", "id", "criado_por", "estornado", "chave_idempotencia"]
)
def test_campo_desconhecido_no_topo_e_recusado_nomeando_a_chave(client, cenario, campo_extra):
    """Os quatro campos medidos pelo auditor, mais `chave_idempotencia`
    (o agravante): antes, todos eram aceitos e IGNORADOS (201, sem
    efeito). Agora: 400, nomeando o campo, nada gravado."""
    _cliente_autenticado(client, cenario)
    corpo = _corpo_valido(cenario, extra_topo={campo_extra: "qualquer-coisa"})

    resposta = _post(client, cenario, corpo)

    assert resposta.status_code == 400, (campo_extra, resposta.status_code, resposta.content)
    assert campo_extra in resposta.content.decode(), resposta.content
    assert _sem_nada_gravado()


def test_campo_desconhecido_dentro_de_um_item_e_recusado(client, cenario):
    """`xpto` dentro de um item: antes, ignorado em silêncio (201). Agora:
    400, nada gravado."""
    _cliente_autenticado(client, cenario)
    corpo = _corpo_valido(cenario, extra_item={"xpto": 1})

    resposta = _post(client, cenario, corpo)

    assert resposta.status_code == 400, (resposta.status_code, resposta.content)
    assert _sem_nada_gravado()


def test_chave_idempotencia_no_corpo_nao_produz_mais_duplicidade_sem_aviso(client, cenario):
    """O agravante concreto do achado: antes, `"chave_idempotencia"` no
    CORPO (sem cabeçalho) não tinha efeito de idempotência NENHUM — dois
    POSTs idênticos, com essa chave inútil no corpo, criavam DOIS
    lançamentos, sem aviso algum de que a chave "enviada" não valia nada.
    Agora: o corpo com esse campo é recusado de cara, 400 nas duas vezes —
    o cliente aprende IMEDIATAMENTE que a superfície está errada, em vez
    de descobrir por duplicidade.
    """
    _cliente_autenticado(client, cenario)
    corpo = _corpo_valido(cenario, extra_topo={"chave_idempotencia": "minha-chave-no-lugar-errado"})

    primeira = _post(client, cenario, corpo)
    segunda = _post(client, cenario, corpo)

    assert primeira.status_code == 400, (primeira.status_code, primeira.content)
    assert segunda.status_code == 400, (segunda.status_code, segunda.content)
    assert _sem_nada_gravado()


def test_corpo_so_com_campos_permitidos_continua_funcionando(client, cenario):
    """Controle positivo: a correção não pode ter apertado o caminho
    normal — só `data`/`historico`/`itens` no topo, só `conta`/`tipo`/
    `valor` em cada item."""
    _cliente_autenticado(client, cenario)
    corpo = _corpo_valido(cenario)

    resposta = _post(client, cenario, corpo, chave_header="bl145-ok")

    assert resposta.status_code == 201, (resposta.status_code, resposta.content)


def test_idempotency_key_no_cabecalho_continua_funcionando_sem_regressao(client, cenario):
    """Controle positivo do CONTRATO real (BL-41): o cabeçalho
    `Idempotency-Key` — a única superfície válida — continua funcionando
    exatamente como antes, incluindo a garantia de não duplicar."""
    _cliente_autenticado(client, cenario)
    corpo = _corpo_valido(cenario)

    primeira = _post(client, cenario, corpo, chave_header="bl145-header-ok")
    segunda = _post(client, cenario, corpo, chave_header="bl145-header-ok")

    assert primeira.status_code == 201, (primeira.status_code, primeira.content)
    assert segunda.status_code == 200, (segunda.status_code, segunda.content)
    assert LancamentoContabil.objects.count() == 1
