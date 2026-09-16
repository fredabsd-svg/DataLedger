"""BL-57 (DL-024): PUT/PATCH gera trilha com diff derivado do contrato.

Antes desta correção, `EmpresaDetailView.perform_update` NÃO chamava
`registrar()` — mudar CNPJ, razão social, nome fantasia ou ativo saía
sem rastro na trilha. A vista `/auditoria/` continuava dizendo "tudo
certo" porque não havia nada para mostrar.

Esta correção adiciona `registrar(acao='empresa.atualizada', ...)` com
`detalhes = {valores_anteriores, valores_novos}`, dentro do mesmo
`transaction.atomic()` da BL-14. A lista de campos auditados vem do
CONTRATO (`_campos_gravaveis(serializer)`, mesma fonte da BL-196/DE-034),
não de uma lista copiada — campo novo no serializer amanhã entra na
trilha sozinho, e o teste de derivação cobre.

Testes:

1. **Estático** (`test_*`): lê o fonte via `inspect.getsource` e confirma
   a forma da correção. Roda sem banco.

2. **Runtime** (`@pytest.mark.django_db(transaction=True)`): usa o ORM
   de verdade, faz PATCH/PUT por HTTP, e lê o `RegistroAuditoria`
   resultante. A CI é quem roda — `pytest-django` exige PostgreSQL.
"""

import inspect

import pytest

# -----------------------------------------------------------------------
# 1. Fonte estático — diff derivado do contrato, formato `valores_anteriores`
# -----------------------------------------------------------------------


def test_helper_de_diff_existe_e_se_chama_dos_campos_gravaveis():
    """`apps/empresas/views.py` precisa expor um helper `_diff_dos_campos_gravaveis`
    que recebe o `serializer` e a instância atual, e devolve um par de dicts
    alinhados por campo. O `perform_update` usa esse helper.
    """
    from apps.empresas import views

    src = inspect.getsource(views)
    assert "def _diff_dos_campos_gravaveis" in src, (
        "BL-57: helper `_diff_dos_campos_gravaveis` precisa existir em apps/empresas/views.py"
    )
    assert "_campos_gravaveis" in src, (
        "BL-57: o helper precisa derivar a lista de campos via "
        "`_campos_gravaveis` (não lista hardcoded)"
    )


def test_perform_update_chama_registrar_com_detalhes_de_diff():
    """`EmpresaDetailView.perform_update` chama `registrar(...)` com
    `detalhes={'valores_anteriores': ..., 'valores_novos': ...}` e dentro
    do mesmo `transaction.atomic()` da BL-14.
    """
    from apps.empresas.views import EmpresaDetailView

    src = inspect.getsource(EmpresaDetailView.perform_update)
    assert 'acao="empresa.atualizada"' in src, (
        "BL-57: `registrar(acao='empresa.atualizada', ...)` precisa "
        "ser chamado em perform_update.\n"
        f"perform_update atual:\n{src}"
    )
    assert '"valores_anteriores"' in src or "'valores_anteriores'" in src, (
        "BL-57: `detalhes` precisa do par `valores_anteriores` / "
        "`valores_novos` (mesmo formato de `valores_antigos` em "
        "excluir_ultimo_regime_tributario)"
    )
    assert '"valores_novos"' in src or "'valores_novos'" in src, (
        "BL-57: `detalhes` precisa do par `valores_anteriores` / `valores_novos`"
    )
    assert "with (" in src and "transaction.atomic()" in src, (
        "BL-57: `registrar()` precisa estar dentro do `transaction.atomic()` "
        "que protege o UPDATE — sem isso, atomicidade da BL-14 não cobre a "
        "trilha nova."
    )


# -----------------------------------------------------------------------
# 2. Runtime — diff calculado de verdade por requisição HTTP (CI only)
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_patch_empresa_gera_trilha_com_diff_apenas_do_campo_alterado():
    """PUT/PATCH de UM campo gera um `RegistroAuditoria` com
    `valores_anteriores` e `valores_novos` contendo SÓ esse campo."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="E BL-57", cnpj="11111111000111")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl57", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Original",
        nome_fantasia="Fantasia Original",
        cnpj="22222222000122",
    )

    from django.test import Client

    client = Client()
    client.login(username="gestor-bl57", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.id]),
        data={"razao_social": "Atualizada"},
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content

    regs = RegistroAuditoria.objects.filter(acao="empresa.atualizada")
    assert regs.count() == 1, f"Esperado 1 registro, obtido {regs.count()}"
    detalhes = regs.first().detalhes
    assert detalhes["valores_anteriores"] == {"razao_social": "Original"}
    assert detalhes["valores_novos"] == {"razao_social": "Atualizada"}


@pytest.mark.django_db(transaction=True)
def test_patch_sem_alteracao_nao_gera_trilha():
    """PUT/PATCH que não muda nada (mesmo payload reenviado) NÃO gera
    registro. Anti-P8 da DL-011 rodada 3.
    """
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="E BL-57 anti-P8", cnpj="33333333000133")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl57-p8", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Mantida",
        nome_fantasia="Mantida",
        cnpj="44444444000144",
    )

    client = Client()
    client.login(username="gestor-bl57-p8", password="senha-forte-123")

    # PATCH com os mesmos valores que já estão lá.
    client.patch(
        reverse("empresas:api-detalhe", args=[empresa.id]),
        data={"razao_social": "Mantida", "nome_fantasia": "Mantida"},
        content_type="application/json",
    )
    assert RegistroAuditoria.objects.filter(acao="empresa.atualizada").count() == 0, (
        "PATCH sem alteração não deveria gerar trilha"
    )


@pytest.mark.django_db(transaction=True)
def test_patch_multiplos_campos_gera_trilha_com_cada_campo_no_diff():
    """PATCH de vários campos lista CADA um nos dois dicts do diff."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="E BL-57 multi", cnpj="55555555000155")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl57-m", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="A",
        nome_fantasia="B",
        cnpj="66666666000166",
        ativo=True,
    )

    client = Client()
    client.login(username="gestor-bl57-m", password="senha-forte-123")

    client.patch(
        reverse("empresas:api-detalhe", args=[empresa.id]),
        data={"razao_social": "A2", "ativo": False},
        content_type="application/json",
    )
    reg = RegistroAuditoria.objects.filter(acao="empresa.atualizada").get()
    assert reg.detalhes["valores_anteriores"] == {"razao_social": "A", "ativo": True}
    assert reg.detalhes["valores_novos"] == {"razao_social": "A2", "ativo": False}


@pytest.mark.django_db(transaction=True)
def test_puts_sucessivos_registram_diffs_independentes():
    """Dois PUTs sucessivos devem gerar dois eventos, cada um com apenas
    o campo que mudou naquela operação."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    escritorio = Escritorio.objects.create(nome="E BL-57 PUT", cnpj="10101010000110")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl57-put", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Original",
        nome_fantasia="Fantasia",
        cnpj="11122233000183",
    )
    client = Client()
    client.login(username="gestor-bl57-put", password="senha-forte-123")
    url = reverse("empresas:api-detalhe", args=[empresa.id])

    resposta_cnpj = client.put(
        url,
        data={
            "razao_social": "Original",
            "nome_fantasia": "Fantasia",
            "cnpj": "44455566000183",
            "ativo": True,
        },
        content_type="application/json",
    )
    resposta_razao = client.put(
        url,
        data={
            "razao_social": "Atualizada",
            "nome_fantasia": "Fantasia",
            "cnpj": "44455566000183",
            "ativo": True,
        },
        content_type="application/json",
    )

    assert resposta_cnpj.status_code == 200, resposta_cnpj.content
    assert resposta_razao.status_code == 200, resposta_razao.content
    registros = list(
        RegistroAuditoria.objects.filter(acao="empresa.atualizada").order_by("criado_em", "id")
    )
    assert len(registros) == 2
    assert registros[0].detalhes == {
        "valores_anteriores": {"cnpj": "11122233000183"},
        "valores_novos": {"cnpj": "44455566000183"},
    }
    assert registros[1].detalhes == {
        "valores_anteriores": {"razao_social": "Original"},
        "valores_novos": {"razao_social": "Atualizada"},
    }


@pytest.mark.django_db(transaction=True)
def test_put_campo_adicionado_ao_serializer_entra_na_trilha(monkeypatch, client):
    """A mutação adiciona um campo gravável ao serializer, sem tocar na
    lista de produção; o diff precisa acompanhá-lo por contrato."""
    from django.contrib.auth import get_user_model
    from django.urls import reverse
    from rest_framework import serializers

    from apps.auditoria.models import RegistroAuditoria
    from apps.empresas.models import Empresa
    from apps.empresas.serializers import EmpresaSerializer
    from apps.empresas.views import EmpresaDetailView
    from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

    class SerializerComCampoDerivado(EmpresaSerializer):
        apelido = serializers.CharField(required=False)

        class Meta(EmpresaSerializer.Meta):
            fields = [*EmpresaSerializer.Meta.fields, "apelido"]

    escritorio = Escritorio.objects.create(nome="E BL-57 contrato", cnpj="14141414000114")
    usuario = get_user_model().objects.create_user(
        username="gestor-bl57-contrato", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Contrato", cnpj="15151515000115"
    )
    monkeypatch.setattr(Empresa, "apelido", "", raising=False)
    monkeypatch.setattr(EmpresaDetailView, "serializer_class", SerializerComCampoDerivado)
    client.login(username="gestor-bl57-contrato", password="senha-forte-123")

    resposta = client.patch(
        reverse("empresas:api-detalhe", args=[empresa.id]),
        data={"apelido": "Campo novo"},
        content_type="application/json",
    )

    assert resposta.status_code == 200, resposta.content
    registro = RegistroAuditoria.objects.get(acao="empresa.atualizada")
    assert registro.detalhes == {
        "valores_anteriores": {"apelido": ""},
        "valores_novos": {"apelido": "Campo novo"},
    }
