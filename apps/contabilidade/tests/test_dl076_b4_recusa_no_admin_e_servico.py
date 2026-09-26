"""Achado B4 da auditoria rodada 1 (DL-038, R5): a recusa de contabilidade
por partidas dobradas para empresa em modo livro-caixa passa a valer também
no admin (`Conta.clean()`) e no serviço de escrita (`criar_lancamento`) —
antes desta correção, só o mixin da API e o decorador da tela recusavam;
`admin:contabilidade_conta_add` devolvia 302 com 1 conta criada.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.contabilidade.models import Conta, ModoEscrituracao, NaturezaConta, TipoConta
from apps.contabilidade.services import LancamentoInvalido, criar_lancamento
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório B4", cnpj="91100000000030")


@pytest.fixture
def empresa_livro_caixa(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa Livro-Caixa B4 Ltda",
        cnpj="11122233000183",
        modo_escrituracao=ModoEscrituracao.LIVRO_CAIXA,
    )


@pytest.fixture
def empresa_contabilidade(escritorio):
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa Contabilidade B4 Ltda", cnpj="11444777000161"
    )


# --- Conta.clean() (admin, DE-008) -------------------------------------


def test_conta_clean_recusa_para_empresa_livro_caixa(empresa_livro_caixa):
    conta = Conta(
        empresa=empresa_livro_caixa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    with pytest.raises(ValidationError, match="livro-caixa"):
        conta.clean()


def test_conta_clean_permite_para_empresa_contabilidade(empresa_contabilidade):
    conta = Conta(
        empresa=empresa_contabilidade,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    conta.clean()  # não levanta


def test_conta_clean_com_empresa_inexistente_continua_com_mensagem_propria(empresa_contabilidade):
    # Achado da correção do B4: a checagem de livro-caixa NÃO pode quebrar
    # o guard existente de "empresa inexistente" (BL-264/rodada 6) — antes
    # de consertar, `self.empresa` levantava `Empresa.DoesNotExist` cru.
    conta = Conta(
        empresa_id=999999,
        codigo="9",
        nome="Conta Órfã",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    with pytest.raises(ValidationError) as excinfo:
        conta.full_clean()
    # Não é a mensagem de livro-caixa (não dá para saber o modo de uma
    # empresa que não existe) — é a mensagem de FK, do guard já existente.
    assert "livro-caixa" not in str(excinfo.value)


def test_admin_conta_add_recusa_para_empresa_livro_caixa_sem_criar_nada(empresa_livro_caixa):
    get_user_model().objects.create_superuser(
        username="admin-b4", password="senha-forte-123", email="admin-b4@x.com.br"
    )
    client = Client()
    client.login(username="admin-b4", password="senha-forte-123")

    resposta = client.post(
        reverse("admin:contabilidade_conta_add"),
        data={
            "empresa": empresa_livro_caixa.pk,
            "codigo": "1",
            "nome": "Caixa",
            "tipo": "ativo",
            "natureza": "devedora",
            "aceita_lancamento": "on",
            "ativo": "on",
        },
    )

    assert resposta.status_code == 200, resposta.content
    assert "livro-caixa" in resposta.content.decode()
    assert not Conta.objects.filter(empresa=empresa_livro_caixa).exists()


def test_admin_conta_add_continua_funcionando_para_empresa_contabilidade(empresa_contabilidade):
    get_user_model().objects.create_superuser(
        username="admin-b4b", password="senha-forte-123", email="admin-b4b@x.com.br"
    )
    client = Client()
    client.login(username="admin-b4b", password="senha-forte-123")

    resposta = client.post(
        reverse("admin:contabilidade_conta_add"),
        data={
            "empresa": empresa_contabilidade.pk,
            "codigo": "1",
            "nome": "Caixa",
            "tipo": "ativo",
            "natureza": "devedora",
            "aceita_lancamento": "on",
            "ativo": "on",
        },
    )

    assert resposta.status_code == 302, resposta.content
    assert Conta.objects.filter(empresa=empresa_contabilidade, codigo="1").exists()


# --- criar_lancamento (serviço de escrita) ------------------------------


def test_criar_lancamento_recusa_para_empresa_livro_caixa(empresa_livro_caixa):
    # A empresa em livro-caixa nunca teria conta cadastrada de verdade
    # (R5 já recusaria a criação da própria conta), mas o serviço de
    # lançamento precisa recusar de qualquer forma, mesmo que uma conta
    # tenha entrado por algum caminho não coberto (defesa em profundidade,
    # não dependente de nenhuma outra camada).
    caixa = Conta.objects.create(
        empresa=empresa_livro_caixa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa_livro_caixa,
        codigo="3",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    with pytest.raises(LancamentoInvalido, match="livro-caixa"):
        criar_lancamento(
            empresa=empresa_livro_caixa,
            data=date(2026, 1, 15),
            historico="Tentativa de lançamento em livro-caixa",
            itens=[
                {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
                {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
            ],
        )


def test_criar_lancamento_continua_funcionando_para_empresa_contabilidade(empresa_contabilidade):
    caixa = Conta.objects.create(
        empresa=empresa_contabilidade,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa_contabilidade,
        codigo="3",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )

    lancamento = criar_lancamento(
        empresa=empresa_contabilidade,
        data=date(2026, 1, 15),
        historico="Lançamento normal",
        itens=[
            {"conta": caixa, "tipo": "debito", "valor": Decimal("100.00")},
            {"conta": capital, "tipo": "credito", "valor": Decimal("100.00")},
        ],
    )
    assert lancamento.pk is not None
