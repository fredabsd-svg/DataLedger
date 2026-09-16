"""DL-023, BL-249 (achado P5 da auditoria rodada 1).

`apps/empresas/models.py` dizia, numa mensagem de `ValidationError` que o
CONTADOR pode ver na tela do admin: "...fale com o **arquiteto-senior** se
este for um caso real do escritório." Quem lê é o Fred — "arquiteto-senior"
é o nome de um agente de IA deste repositório, não existe para o cliente, e
a frase expunha a estrutura interna da equipe numa mensagem de produto.

Este teste varre as mensagens de erro de domínio (`ValidationError` de
`Conta.clean()` e `Empresa.clean()`) contra a lista de papéis internos da
equipe — não o CÓDIGO-FONTE inteiro (que legitimamente cita esses nomes em
comentários de desenvolvedor), só o TEXTO que chega ao usuário.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

# A mesma lista de papéis que docs/agents/equipe.md declara — nenhum deles
# é nome que o Fred deva ler numa mensagem de erro do produto.
PAPEIS_INTERNOS_DA_EQUIPE = [
    "arquiteto-senior",
    "desenvolvedor-pleno",
    "especialista-frontend",
    "auditor-qa",
    "auxiliar-pesquisa",
    "auxiliar-implementacao",
    "auxiliar-verificacao",
]


def _mensagens_de(erro: ValidationError):
    """Achata `ValidationError.messages` (funciona tanto para a forma
    simples quanto para `message_dict`)."""
    if hasattr(erro, "message_dict"):
        return [msg for mensagens in erro.message_dict.values() for msg in mensagens]
    return list(erro.messages)


def _sem_papel_interno(mensagens):
    for mensagem in mensagens:
        for papel in PAPEIS_INTERNOS_DA_EQUIPE:
            assert papel not in mensagem, (papel, mensagem)


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-023 BL-249", cnpj="10101010000199")
    outro_escritorio = Escritorio.objects.create(
        nome="Escritório DL-023 BL-249 (outro)", cnpj="20202020000188"
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-023 BL-249 Ltda", cnpj="11222333000181"
    )
    return {"escritorio": escritorio, "outro_escritorio": outro_escritorio, "empresa": empresa}


def test_mensagem_de_empresa_sem_escrituracao_nao_cita_papel_interno(cenario):
    """Mesmo com escrituração (o caso que dispara a mensagem), o texto não
    pode citar papel interno."""
    empresa = cenario["empresa"]
    Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    empresa.escritorio = cenario["outro_escritorio"]

    with pytest.raises(ValidationError) as excinfo:
        empresa.full_clean()

    _sem_papel_interno(_mensagens_de(excinfo.value))


def test_mensagem_de_conta_sem_movimento_nao_cita_papel_interno(cenario):
    empresa = cenario["empresa"]
    conta = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    contrapartida = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Receita",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 15),
        historico="BL-249",
        itens=[
            {"conta": conta, "tipo": TipoPartida.DEBITO, "valor": Decimal("10.00")},
            {"conta": contrapartida, "tipo": TipoPartida.CREDITO, "valor": Decimal("10.00")},
        ],
    )
    conta.natureza = NaturezaConta.CREDORA

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    _sem_papel_interno(_mensagens_de(excinfo.value))


def test_mensagem_de_conta_cruzando_escritorio_nao_cita_papel_interno(cenario):
    outra_empresa = Empresa.objects.create(
        escritorio=cenario["outro_escritorio"],
        razao_social="Outra empresa DL-023 BL-249",
        cnpj="11122233000183",
    )
    conta = Conta.objects.create(
        empresa=cenario["empresa"],
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta.empresa = outra_empresa

    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()

    _sem_papel_interno(_mensagens_de(excinfo.value))
