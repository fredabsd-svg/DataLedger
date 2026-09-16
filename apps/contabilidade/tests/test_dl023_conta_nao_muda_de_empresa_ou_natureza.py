"""DL-023, critérios 1 a 4 e 11 (BL-83, achado novo 1 da auditoria DL-015
rodada 4).

O defeito medido: `ContaAdmin` deixava mover conta COM movimento para OUTRA
empresa e trocar a NATUREZA/TIPO de conta já movimentada. Efeito: o
balancete da empresa de origem passava a mostrar zero de débito contra mil
de crédito, o Diário continuava fechando, e nenhuma das quatro categorias da
conferência acusava nada — trocar a natureza inverte o sinal de todo o
histórico da conta.

A defesa mora em `Conta.clean()` (apps/contabilidade/models.py), chamado
por `full_clean()` — o que qualquer `ModelForm`, inclusive o do admin,
executa. Todo teste aqui é por REQUISIÇÃO autenticada ao admin, com o
objeto reconferido no banco depois da resposta: `full_clean()` verde não
prova que o admin o chama.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import apurar_balancete, criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    escritorio = Escritorio.objects.create(nome="Escritório DL-023", cnpj="10101010000122")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa DL-023 Ltda", cnpj="10111213000144"
    )
    outra_empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Outra Empresa DL-023 Ltda", cnpj="20212223000155"
    )
    admin = get_user_model().objects.create_superuser(
        username="admin-dl023-conta",
        email="admin-dl023-conta@escritorio.com.br",
        password=SENHA,
    )
    return {
        "escritorio": escritorio,
        "empresa": empresa,
        "outra_empresa": outra_empresa,
        "admin": admin,
    }


def _conta(
    empresa,
    *,
    codigo,
    nome="Conta",
    tipo=TipoConta.ATIVO,
    natureza=NaturezaConta.DEVEDORA,
    pai=None,
):
    return Conta.objects.create(
        empresa=empresa, conta_pai=pai, codigo=codigo, nome=nome, tipo=tipo, natureza=natureza
    )


def _com_movimento(cenario, conta):
    """Dá movimento PRÓPRIO a `conta`: um lançamento balanceado contra uma
    segunda conta descartável da mesma empresa."""
    contrapartida = _conta(
        cenario["empresa"],
        codigo=f"contra-{conta.codigo}",
        nome="Contrapartida",
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 1, 15),
        historico="DL-023 movimento",
        itens=[
            {"conta": conta, "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
            {"conta": contrapartida, "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
        ],
    )
    return conta


def _login_admin(client, cenario):
    assert client.login(username="admin-dl023-conta", password=SENHA)


def _post_change(client, conta, dados):
    payload = {
        "empresa": conta.empresa_id,
        "conta_pai": conta.conta_pai_id or "",
        "codigo": conta.codigo,
        "nome": conta.nome,
        "tipo": conta.tipo,
        "natureza": conta.natureza,
        "aceita_lancamento": "on" if conta.aceita_lancamento else "",
        "ativo": "on" if conta.ativo else "",
        "_continue": "Salvar e continuar editando",
    }
    payload.update(dados)
    return client.post(f"/admin/contabilidade/conta/{conta.pk}/change/", payload)


# ---------------------------------------------------------------------------
# Critério 1: conta COM PARTIDAS não muda de empresa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_empresa_de_conta_com_partidas(client, cenario):
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    estado_antes = (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"empresa": cenario["outra_empresa"].id})

    # 200 = formulário reapresentado com erro (302 seria "salvou e
    # redirecionou") — mesmo critério já usado no resto do projeto para
    # distinguir recusa de sucesso no admin.
    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    # "byte a byte": empresa, natureza e tipo — os três campos que o
    # critério 1 nomeia — continuam exatamente como estavam.
    assert (conta.empresa_id, conta.natureza, conta.tipo, conta.codigo, conta.nome) == estado_antes


# ---------------------------------------------------------------------------
# Critério 2: conta COM FILHAS não muda de empresa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_empresa_de_conta_com_filhas(client, cenario):
    pai = _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO)
    _conta(cenario["empresa"], codigo="1.1", pai=pai, nome="Filha")
    _login_admin(client, cenario)

    resposta = _post_change(client, pai, {"empresa": cenario["outra_empresa"].id})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    pai.refresh_from_db()
    assert pai.empresa_id == cenario["empresa"].id


# ---------------------------------------------------------------------------
# Critério 3: natureza/tipo de conta COM MOVIMENTO não mudam
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_natureza_de_conta_com_movimento(client, cenario):
    conta = _com_movimento(
        cenario, _conta(cenario["empresa"], codigo="1", natureza=NaturezaConta.DEVEDORA)
    )
    periodo = {"inicio": date(2026, 1, 1), "fim": date(2026, 1, 31)}
    balancete_antes = apurar_balancete(empresa=cenario["empresa"], **periodo)
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"natureza": NaturezaConta.CREDORA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    assert conta.natureza == NaturezaConta.DEVEDORA
    balancete_depois = apurar_balancete(empresa=cenario["empresa"], **periodo)
    # O Balancete continua conciliável — débito igual a crédito — e
    # IDÊNTICO ao de antes da tentativa: nada mudou de sinal nem de valor.
    assert balancete_depois["total_debitos"] == balancete_depois["total_creditos"]
    assert balancete_antes == balancete_depois


def test_admin_recusa_trocar_tipo_de_conta_com_movimento(client, cenario):
    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1", tipo=TipoConta.ATIVO))
    _login_admin(client, cenario)

    resposta = _post_change(client, conta, {"tipo": TipoConta.DESPESA})

    assert resposta.status_code == 200, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    assert conta.tipo == TipoConta.ATIVO


# ---------------------------------------------------------------------------
# Critério 4: conta SEM movimento e SEM filhas continua editável
# ---------------------------------------------------------------------------


def test_admin_continua_editando_conta_sem_movimento_e_sem_filhas(client, cenario):
    """A defesa não pode engessar o cadastro legítimo: sem movimento e sem
    filhas, trocar empresa, natureza e tipo continua permitido."""
    conta = _conta(
        cenario["empresa"], codigo="9", natureza=NaturezaConta.DEVEDORA, tipo=TipoConta.ATIVO
    )
    _login_admin(client, cenario)

    resposta = _post_change(
        client,
        conta,
        {
            "empresa": cenario["outra_empresa"].id,
            "natureza": NaturezaConta.CREDORA,
            "tipo": TipoConta.PASSIVO,
        },
    )

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    conta.refresh_from_db()
    assert conta.empresa_id == cenario["outra_empresa"].id
    assert conta.natureza == NaturezaConta.CREDORA
    assert conta.tipo == TipoConta.PASSIVO


# ---------------------------------------------------------------------------
# A mesma defesa fora do admin: `full_clean()` chamado diretamente — prova
# que a regra mora no MODELO, e não é dependente de o admin a chamar (a
# distinção que o próprio critério de teste da etapa exige: a prova de
# ADMIN é por requisição, acima; esta é a prova de MODELO, isolada).
# ---------------------------------------------------------------------------


def test_full_clean_recusa_troca_de_empresa_de_conta_com_movimento(cenario):
    from django.core.exceptions import ValidationError

    conta = _com_movimento(cenario, _conta(cenario["empresa"], codigo="1"))
    conta.empresa = cenario["outra_empresa"]

    with pytest.raises(ValidationError):
        conta.full_clean()
