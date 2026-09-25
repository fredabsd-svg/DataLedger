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


def _post_change(client, empresa, dados):
    """POST no `change` de `empresa`, com um payload sempre VÁLIDO por
    padrão — `dados` sobrescreve só os campos que o teste quer alterar.

    BL-254 (achado A1, auditoria DL-023 rodada 1): o payload-base precisa
    validar de verdade, senão "200 ou 302" + "nada mudou" fica satisfeito
    tanto por uma recusa de NEGÓCIO quanto por um formulário QUEBRADO
    (medido pelo auditor: trocar o CNPJ por "CNPJ-INVALIDO-!!" não matava
    nenhum dos testes antigos, porque nenhum exigia status EXATO nem
    conferia que outro campo do MESMO POST foi gravado de verdade)."""
    payload = {
        "escritorio": empresa.escritorio_id,
        "razao_social": empresa.razao_social,
        "nome_fantasia": empresa.nome_fantasia,
        # DL-038: `tipo_inscricao`/`modo_escrituracao`/`cpf` entraram no
        # `ModelForm` automático do admin (que expõe TODOS os campos do
        # modelo, sem `fields`/`exclude` em `EmpresaAdmin`) — o payload-base
        # precisa continuar "sempre VÁLIDO" (ver o comentário da função),
        # e por isso leva os valores ATUAIS da empresa, não um literal fixo.
        "tipo_inscricao": empresa.tipo_inscricao,
        "cnpj": empresa.cnpj,
        "cpf": empresa.cpf,
        "modo_escrituracao": empresa.modo_escrituracao,
        "ativo": "on" if empresa.ativo else "",
        "estabelecimentos-TOTAL_FORMS": "0",
        "estabelecimentos-INITIAL_FORMS": "0",
        "estabelecimentos-MIN_NUM_FORMS": "0",
        "estabelecimentos-MAX_NUM_FORMS": "1000",
        "_continue": "Salvar e continuar editando",
    }
    payload.update(dados)
    return client.post(f"/admin/empresas/empresa/{empresa.pk}/change/", payload)


def _post_change_escritorio(client, empresa, novo_escritorio):
    """Tenta trocar `escritorio` E `razao_social` no MESMO POST — a
    segunda mudança é o controle positivo (BL-254): se o formulário
    estivesse quebrado por qualquer outro motivo (CNPJ inválido, campo
    obrigatório faltando), `razao_social` TAMBÉM não mudaria, e o teste
    que só olhasse `escritorio` não distinguiria os dois casos."""
    return _post_change(
        client,
        empresa,
        {"escritorio": novo_escritorio.id, "razao_social": "Nome alterado pelo teste Ltda"},
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
    # ele e salva o resto — 302 EXATO, "sucesso", mas SEM mudar o
    # escritório): é essa a forma real de "recusa" pelo readonly_fields.
    # Status EXATO (não "in (200, 302)"): um payload quebrado por outro
    # motivo (BL-254) daria 200, nunca 302 — exigir 302 já distingue os
    # dois casos.
    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id
    # Controle positivo NO MESMO POST (BL-254): `razao_social` FOI
    # gravada de verdade — prova que o formulário validou e salvou, e que
    # o `escritorio` inalterado é efeito do `readonly_fields`, não de um
    # formulário quebrado por inteiro.
    assert empresa.razao_social == "Nome alterado pelo teste Ltda"
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

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id
    assert empresa.razao_social == "Nome alterado pelo teste Ltda"


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

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.escritorio_id == cenario["origem"].id
    assert empresa.razao_social == "Nome alterado pelo teste Ltda"


def test_admin_grava_razao_social_de_verdade_pela_mesma_url(client, cenario):
    """Controle positivo DEDICADO (BL-254): a mesma URL, com um payload que
    não mexe em `escritorio`, grava de verdade. Sem este teste, um "200 ou
    302" + "nada mudou" nos testes de recusa não prova que a URL funciona —
    só que ela não fez nada, o que também é verdade para um formulário
    quebrado."""
    empresa = cenario["empresa"]
    _login_admin(client, cenario)

    resposta = _post_change(client, empresa, {"razao_social": "Empresa DL-023-E Renomeada Ltda"})

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    empresa.refresh_from_db()
    assert empresa.razao_social == "Empresa DL-023-E Renomeada Ltda"


def test_get_readonly_fields_trava_escritorio_no_change_e_libera_no_add(cenario):
    """Unidade direta do método do admin (não por requisição): é o que
    torna a defesa 1 (readonly_fields) matavelmente detectável por si só,
    independente de `Empresa.clean()` — ver o docstring do módulo."""
    modeladmin = EmpresaAdmin(Empresa, django_admin.site)

    assert modeladmin.get_readonly_fields(None, obj=None) == []
    assert modeladmin.get_readonly_fields(None, obj=cenario["empresa"]) == ["escritorio"]


# ---------------------------------------------------------------------------
# BL-258 (achado A5 da auditoria DL-023 rodada 1): H1 ("escritorio livre no
# add") só tinha prova UNITÁRIA (o teste acima) — nenhuma requisição ao
# `add` de EmpresaAdmin era exercida em lugar nenhum da suíte. Como H1 é a
# metade PERMISSIVA da decisão, é ela que precisa de prova por requisição.
# ---------------------------------------------------------------------------


def test_admin_add_grava_empresa_no_escritorio_escolhido(client, cenario):
    _login_admin(client, cenario)

    resposta = client.post(
        "/admin/empresas/empresa/add/",
        {
            "escritorio": cenario["destino"].id,
            "razao_social": "Empresa nascida no add Ltda",
            "nome_fantasia": "",
            # DL-038: campos novos do ModelForm automático do admin.
            "tipo_inscricao": "CNPJ",
            "cnpj": "11122233000183",
            "cpf": "",
            "modo_escrituracao": "contabilidade",
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "_continue": "Salvar e continuar editando",
        },
    )

    assert resposta.status_code == 302, (resposta.status_code, resposta.content)
    nova = Empresa.objects.get(razao_social="Empresa nascida no add Ltda")
    assert nova.escritorio_id == cenario["destino"].id


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
