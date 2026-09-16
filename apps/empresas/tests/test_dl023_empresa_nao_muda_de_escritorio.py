"""DL-023, critério 5 (BL-211/A3, achado A3 da auditoria DL-020 rodada 1).

O defeito medido: `EmpresaAdmin` deixava mover uma empresa INTEIRA de
escritório com um único POST — medido pelo auditor: `302`,
`escritorio agora: 4 | era: 3`. Levava junto plano de contas, escrituração e
estabelecimentos, sem nenhum `RegistroAuditoria`.

Duas camadas, cada uma testada separadamente (ver o docstring de
`EmpresaAdmin` em apps/empresas/admin.py para a decisão completa):

1. `EmpresaAdmin.get_readonly_fields` trava `escritorio` no `change`,
   INCONDICIONALMENTE — inclusive para empresa SEM nenhuma escrituração
   ainda, porque a pendência P1 (transferir empresa entre escritórios é
   operação real do escritório?) segue sem resposta do Fred, e o lado
   seguro é recusar sempre no caminho cotidiano.
2. `Empresa.clean()` recusa a troca quando existe escrituração — camada de
   modelo, redundante com a 1 hoje (só o admin expõe `escritorio` como
   campo editável), mas testada isoladamente para que a remoção dela seja
   detectável independente do `readonly_fields` (critério 14, prova por
   mutação).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.contabilidade.models import Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.empresas.admin import EmpresaAdmin
from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.tenancy.models import Escritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db


@pytest.fixture
def cenario():
    origem = Escritorio.objects.create(nome="Escritório de origem DL-023", cnpj="30303030000111")
    destino = Escritorio.objects.create(nome="Escritório de destino DL-023", cnpj="40404040000122")
    empresa = Empresa.objects.create(
        escritorio=origem, razao_social="Empresa DL-023-E Ltda", cnpj="11222333000181"
    )
    admin = get_user_model().objects.create_superuser(
        username="admin-dl023-empresa",
        email="admin-dl023-empresa@escritorio.com.br",
        password=SENHA,
    )
    return {"origem": origem, "destino": destino, "empresa": empresa, "admin": admin}


def _dar_escrituracao(empresa):
    """Plano de contas + lançamento, as duas primeiras das três formas de
    escrituração que o critério 5 nomeia."""
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
        tipo=TipoConta.RECEITA,
        natureza=NaturezaConta.CREDORA,
    )
    criar_lancamento(
        empresa=empresa,
        data=date(2026, 1, 10),
        historico="DL-023 escrituração",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("50.00")},
            {"conta": receita, "tipo": TipoPartida.CREDITO, "valor": Decimal("50.00")},
        ],
    )
    return caixa, receita


def _login_admin(client, cenario):
    assert client.login(username="admin-dl023-empresa", password=SENHA)


def _post_change_escritorio(client, empresa, novo_escritorio):
    return client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        {
            "escritorio": novo_escritorio.id,
            "razao_social": empresa.razao_social,
            "nome_fantasia": empresa.nome_fantasia,
            "cnpj": empresa.cnpj,
            "ativo": "on" if empresa.ativo else "",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "_continue": "Salvar e continuar editando",
        },
    )


# ---------------------------------------------------------------------------
# Critério 5, literal: empresa COM escrituração, POST no change → recusa
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_escritorio_de_empresa_com_escrituracao(client, cenario):
    empresa = cenario["empresa"]
    caixa, _ = _dar_escrituracao(empresa)
    _login_admin(client, cenario)

    resposta = _post_change_escritorio(client, empresa, cenario["destino"])

    # A tentativa não é recusada com erro de FORMULÁRIO (o campo está
    # readonly, então o Django simplesmente ignora o valor enviado para
    # ele e salva o resto — 302, "sucesso", mas SEM mudar o escritório):
    # é essa a forma real de "recusa" pelo readonly_fields.
    assert resposta.status_code in (200, 302), (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id
    # A consulta pelo escritório de ORIGEM continua devolvendo a empresa, o
    # plano de contas e os lançamentos — nada migrou.
    assert Empresa.objects.filter(escritorio=cenario["origem"], pk=empresa.pk).exists()
    assert caixa.itens_lancamento.exists()
    assert not Empresa.objects.filter(escritorio=cenario["destino"], pk=empresa.pk).exists()


def test_admin_recusa_trocar_escritorio_de_empresa_com_so_estabelecimento(client, cenario):
    """A terceira forma de escrituração que o critério 5 nomeia,
    isoladamente: estabelecimento, sem plano de contas nem lançamento."""
    empresa = cenario["empresa"]
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz",
        cnpj="11122233000183",
    )
    _login_admin(client, cenario)

    resposta = _post_change_escritorio(client, empresa, cenario["destino"])

    assert resposta.status_code in (200, 302), (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id


# ---------------------------------------------------------------------------
# Camada 1 (admin): readonly_fields é INCONDICIONAL — vale também para
# empresa SEM nenhuma escrituração, porque o lado seguro (P1 em aberto) é
# recusar sempre no caminho cotidiano. Isto é o que torna a remoção do
# `readonly_fields` MATAVELMENTE detectável (critério 14): sem escrituração,
# `Empresa.clean()` sozinho PERMITIRIA a troca.
# ---------------------------------------------------------------------------


def test_admin_recusa_trocar_escritorio_mesmo_sem_escrituracao(client, cenario):
    empresa = cenario["empresa"]
    assert not empresa.contas.exists()
    assert not empresa.lancamentos.exists()
    assert not empresa.estabelecimentos.exists()
    _login_admin(client, cenario)

    resposta = _post_change_escritorio(client, empresa, cenario["destino"])

    assert resposta.status_code in (200, 302), (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id


def test_get_readonly_fields_trava_escritorio_no_change_e_libera_no_add(cenario):
    """Unidade direta do método do admin (não por requisição): é o que
    torna a defesa 1 (readonly_fields) matavelmente detectável por si só,
    independente de `Empresa.clean()` — ver o docstring do módulo."""
    modeladmin = EmpresaAdmin(Empresa, django_admin.site)

    assert modeladmin.get_readonly_fields(None, obj=None) == []
    assert modeladmin.get_readonly_fields(None, obj=cenario["empresa"]) == ["escritorio"]


# ---------------------------------------------------------------------------
# Camada 2 (modelo): `Empresa.clean()`, isolada de qualquer readonly do
# admin — prova que a regra do critério "defesas de modelo" existe por
# conta própria, e não só como efeito do formulário.
# ---------------------------------------------------------------------------


def test_full_clean_recusa_troca_de_escritorio_com_escrituracao(cenario):
    empresa = cenario["empresa"]
    _dar_escrituracao(empresa)
    empresa.escritorio = cenario["destino"]

    with pytest.raises(ValidationError):
        empresa.full_clean()


def test_full_clean_aceita_troca_de_escritorio_sem_escrituracao(cenario):
    """Controle positivo do MESMO caminho: sem escrituração nenhuma, o
    MODELO (isoladamente) não recusa — é o admin, com o readonly_fields
    incondicional, quem decide recusar sempre mesmo assim (P1)."""
    empresa = cenario["empresa"]
    empresa.escritorio = cenario["destino"]

    empresa.full_clean()  # não levanta
