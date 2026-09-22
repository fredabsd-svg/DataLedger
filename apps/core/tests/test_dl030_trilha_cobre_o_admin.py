"""DL-030 — a trilha cobre o admin, além do que a DL-024/BL-244 já cobria.

Contexto: o `arquiteto-senior` pediu esta etapa achando que a trilha do
admin NÃO EXISTIA (BL-435, medido em `ab35715`). Medição própria (banco
isolado, `test_dl024_trilha_admin.py`) mostrou que ela já existia desde a
DL-024, mesclada antes da própria medição da BL-435 — a conclusão
"nenhum registrar() em apps/empresas/admin.py, logo não há trilha" media
um SUBSTITUTO (o arquivo `admin.py`) no lugar da propriedade (existe
RegistroAuditoria quando o admin altera o objeto?) e a propriedade já
valia, por um signal genérico em `apps/auditoria/signals.py`. DE-060
aplicada ao processo do `arquiteto-senior`, não só ao código.

O que ficou como gap real, medido contra R1–R8 do plano
`docs/planos/DL-030-a-trilha-cobre-o-admin.md`, e o que este arquivo prova:

- **R1/R2** — a cobertura antiga era uma tupla explícita de seis modelos
  (anti-padrão nomeado pela DE-056); a nova é "todo modelo concreto dos
  apps PRÓPRIOS do projeto, menos uma exclusão pequena e justificada"
  (`apps.auditoria.signals.modelos_cobertos_pela_trilha`), com uma guarda
  que percorre `admin.site._registry` e reprova NOMEANDO qualquer
  `ModelAdmin` sem cobertura (`modelos_admin_sem_cobertura`). A prova de
  força (critério de aceite 3 do plano original) está em
  `test_guarda_reprova_e_nomeia_modeladmin_sem_cobertura` abaixo.
- **R4** — `Usuario` não tinha NENHUMA cobertura (não estava na tupla
  antiga); alterar senha pelo admin não deixava rastro nenhum. Agora está
  coberto pela regra ampla, e o valor é redigido por widget
  (`ReadOnlyPasswordHashWidget`/`PasswordInput`) — nunca o hash.
- **R5** — a atomicidade do caminho ADMIN nunca tinha sido MEDIDA (só a
  das seis views de API/web da BL-14 original, em
  `test_dl024_atomicidade_trilha.py`). Medida aqui por execução: falha em
  `RegistroAuditoria.objects.create` durante um `POST` no `change` do
  admin reverte a alteração do objeto — porque o admin do Django já
  envolve `_changeform_view`/`_delete_view` em `transaction.atomic()`
  (`django/contrib/admin/options.py`, três ocorrências, Django 6.1.1).
- **R6** — a versão anterior derivava `escritorio` SEMPRE de
  `request.escritorio` (o escritório ATIVO da sessão de quem edita). Um
  superusuário sem `VinculoUsuarioEscritorio` — o perfil comum de quem
  mexe no admin — gravava `escritorio=None` mesmo alterando uma `Empresa`
  com escritório óbvio. Agora deriva do OBJETO por inspeção do modelo
  (`_escritorio_do_objeto`), com a sessão como segunda opção só quando o
  objeto não tem um escritório "dono" (`Usuario`).
- **R7** — o inline de `Estabelecimento` nunca tinha sido provado PELA
  MESMA SUPERFÍCIE (POST no `change` de `Empresa` alterando o formset).
"""

from unittest import mock

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model
from django.db import IntegrityError, models
from django.test import Client

from apps.auditoria import signals
from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, Estabelecimento
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

# CNPJs válidos (dígito verificador conferido por apps.empresas.validators.
# validar_cnpj), gerados para este arquivo e não usados em nenhum outro —
# evita colisão de `unique=True` ao rodar a suíte inteira.
CNPJ_EMPRESA_1 = "91000000000066"
CNPJ_EMPRESA_2 = "91000000000147"
CNPJ_EMPRESA_3 = "91000000000228"
CNPJ_EMPRESA_4 = "91000000000309"
CNPJ_ESTABELECIMENTO_1 = "91000000000490"
CNPJ_ESTABELECIMENTO_2 = "91000000000570"


# -----------------------------------------------------------------------
# R2 — a guarda da cobertura é derivada, e prova a própria força
# -----------------------------------------------------------------------


def test_registro_admin_real_nao_tem_modeladmin_sem_cobertura():
    """Propriedade, sobre o `admin.site` REAL do projeto: nenhum
    `ModelAdmin` hoje registrado fica de fora da trilha sem exclusão
    declarada. Lista vazia é o estado correto — se um dia alguém
    registrar um `ModelAdmin` sem decidir a trilha, este teste reprova
    NOMEANDO o modelo."""
    sem_cobertura = signals.modelos_admin_sem_cobertura(django_admin.site)
    assert sem_cobertura == [], (
        f"DL-030: ModelAdmin registrado sem cobertura de trilha: "
        f"{[m.__name__ for m in sem_cobertura]}"
    )


def test_guarda_reprova_e_nomeia_modeladmin_sem_cobertura():
    """Prova de força do R2 (critério de aceite 3 do plano DL-030):
    registra, DENTRO deste teste, um `ModelAdmin` de mentira para um
    modelo que não pertence a nenhum app do projeto (`app_label` de um
    app de terceiros já instalado, `sessions`) — logo não pode estar em
    `modelos_cobertos_pela_trilha()` (que só enumera `apps.*`) nem em
    `EXCLUSAO_DA_TRILHA_DO_ADMIN`. A varredura precisa REPROVAR e NOMEAR
    esse modelo especificamente.

    O registro é desfeito no `finally`, para não vazar estado global do
    `admin.site` para outros testes do processo.
    """

    class _ModeloDeMentiraSemCoberturaDL030(models.Model):
        class Meta:
            app_label = "sessions"  # app de terceiros — nunca é `apps.*`
            managed = False  # não migrado: este teste nunca toca o banco

    django_admin.site.register(_ModeloDeMentiraSemCoberturaDL030)
    try:
        sem_cobertura = signals.modelos_admin_sem_cobertura(django_admin.site)
        assert _ModeloDeMentiraSemCoberturaDL030 in sem_cobertura, (
            "DL-030: a guarda não detectou/nomeou um ModelAdmin de mentira "
            f"sem cobertura. Obtido: {[m.__name__ for m in sem_cobertura]}"
        )
    finally:
        django_admin.site.unregister(_ModeloDeMentiraSemCoberturaDL030)


# -----------------------------------------------------------------------
# Helpers de fixture — reaproveitados pelos testes runtime abaixo
# -----------------------------------------------------------------------


def _criar_escritorio(nome, cnpj):
    return Escritorio.objects.create(nome=nome, cnpj=cnpj)


def _criar_superusuario(username, password="senha-forte-dl030"):
    """Superusuário SEM `VinculoUsuarioEscritorio` — é exatamente o
    perfil que a versão anterior do mecanismo fazia perder o isolamento
    (R6): `request.escritorio` fica `None` porque não há vínculo, mas o
    superusuário continua acessando o admin normalmente (a permissão de
    admin do Django não depende de `VinculoUsuarioEscritorio`)."""
    return get_user_model().objects.create_superuser(
        username=username, password=password, email=f"{username}@example.com"
    )


def _login(client, username, password="senha-forte-dl030"):
    assert client.login(username=username, password=password)


# -----------------------------------------------------------------------
# R6 — escritório derivado do OBJETO, não da sessão de quem edita
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_superusuario_sem_vinculo_editando_empresa_grava_escritorio_do_objeto():
    """O caso que o `arquiteto-senior` marcou como o mais grave dos sete
    gaps: superusuário SEM `VinculoUsuarioEscritorio` (logo
    `request.escritorio is None`) edita `razao_social` de uma `Empresa`
    do Escritório X pelo admin. Antes desta etapa, `RegistroAuditoria.
    escritorio` saía `None`. Agora precisa ser o Escritório X — derivado
    do OBJETO (`Empresa.escritorio`), não da sessão de quem edita.
    """
    escritorio = _criar_escritorio("Escr R6", "91100000000000")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Original R6", cnpj=CNPJ_EMPRESA_1
    )
    _criar_superusuario("super-sem-vinculo-r6")

    client = Client()
    _login(client, "super-sem-vinculo-r6")

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        data={
            "escritorio": escritorio.pk,
            "razao_social": "Atualizada R6",
            "nome_fantasia": "",
            "cnpj": CNPJ_EMPRESA_1,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "0",
            "estabelecimentos-INITIAL_FORMS": "0",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
        },
        follow=False,
    )
    assert resposta.status_code == 302, resposta.content

    reg = RegistroAuditoria.objects.filter(acao="empresas.empresa.admin_atualizado").get()
    assert reg.escritorio_id == escritorio.pk, (
        "DL-030 (R6): RegistroAuditoria.escritorio precisa ser o escritório "
        "DA EMPRESA editada, não None — mesmo com o editor sem vínculo. "
        f"Obtido: {reg.escritorio_id!r}"
    )


@pytest.mark.django_db(transaction=True)
def test_usuario_sem_escritorio_derivavel_cai_para_escritorio_de_quem_edita():
    """`Usuario` não tem FK para `Escritorio` nem para algo que tenha —
    não há "o" escritório de um usuário (pode ter vínculo com vários, ou
    nenhum). Quando o objeto não resolve, a segunda opção declarada é
    `request.escritorio`: o escritório ativo de quem fez a alteração.
    """
    escritorio_do_editor = _criar_escritorio("Escr do editor R6b", "91100000000001")
    editor = _criar_superusuario("editor-com-vinculo-r6b")
    VinculoUsuarioEscritorio.objects.create(
        usuario=editor, escritorio=escritorio_do_editor, papel=Papel.ADMINISTRADOR
    )
    alvo = get_user_model().objects.create_user(
        username="alvo-r6b", password="outra-senha-r6b", email="alvo-r6b@example.com"
    )

    client = Client()
    _login(client, "editor-com-vinculo-r6b")
    # Fixa o escritório ativo da sessão do editor (o middleware seleciona
    # sozinho quando há um único vínculo, mas fixar explicitamente deixa
    # o teste independente dessa seleção automática).
    sessao = client.session
    sessao["escritorio_id"] = escritorio_do_editor.pk
    sessao.save()

    resposta = client.post(
        f"/admin/accounts/usuario/{alvo.pk}/change/",
        data={
            "username": "alvo-r6b",
            "email": "alvo-r6b-novo@example.com",
            "first_name": "",
            "last_name": "",
            "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00",
        },
        follow=False,
    )
    assert resposta.status_code == 302, resposta.content

    reg = RegistroAuditoria.objects.filter(acao="accounts.usuario.admin_atualizado").get()
    assert reg.escritorio_id == escritorio_do_editor.pk, (
        "DL-030 (R6): sem escritório derivável do OBJETO (Usuario), o "
        "registro precisa cair para request.escritorio (quem editou)."
    )


# -----------------------------------------------------------------------
# R4 — segredo redigido, derivado do widget (Usuario.password)
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_alterar_senha_pelo_admin_grava_nome_do_campo_sem_o_valor_nem_o_hash():
    """Critério de aceite 4 do plano DL-030. `Usuario` não tinha NENHUMA
    cobertura antes desta etapa (não estava na tupla explícita da
    DL-024) — este teste prova as duas coisas juntas: que `Usuario` agora
    é coberto, e que o valor do campo `password` nunca aparece, nem
    redigido incorretamente (a marca de redação não pode, por acidente,
    conter o hash)."""
    _criar_superusuario("super-r4")
    alvo = get_user_model().objects.create_user(
        username="alvo-senha-r4", password="senha-original-r4", email="alvo-r4@example.com"
    )
    hash_original = alvo.password

    client = Client()
    _login(client, "super-r4")

    resposta = client.post(
        f"/admin/accounts/usuario/{alvo.pk}/password/",
        data={
            "password1": "senha-nova-bastante-forte-r4",
            "password2": "senha-nova-bastante-forte-r4",
        },
        follow=False,
    )
    assert resposta.status_code == 302, resposta.content

    reg = RegistroAuditoria.objects.filter(acao="accounts.usuario.admin_atualizado").get()
    assert "password" in reg.detalhes["valores_anteriores"], (
        "DL-030 (R4): o NOME do campo precisa aparecer na trilha, mesmo redigido."
    )
    valor_anterior = reg.detalhes["valores_anteriores"]["password"]
    valor_novo = reg.detalhes["valores_novos"]["password"]
    assert valor_anterior == signals.MARCA_DE_REDACAO
    assert valor_novo == signals.MARCA_DE_REDACAO
    assert hash_original not in str(reg.detalhes), (
        "DL-030 (R4): o HASH antigo da senha não pode aparecer em lugar nenhum de detalhes."
    )
    alvo.refresh_from_db()
    assert alvo.password not in str(reg.detalhes), (
        "DL-030 (R4): o HASH novo da senha não pode aparecer em detalhes."
    )


# -----------------------------------------------------------------------
# R5 — atomicidade do caminho ADMIN, medida por execução (não só afirmada)
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_change_de_empresa_via_admin_reverte_se_registrar_falha():
    """DE-058: o comentário em `signals.py` AFIRMA atomicidade porque o
    admin do Django embrulha `_changeform_view` em `transaction.atomic()`
    — este teste MEDE. Mocka `RegistroAuditoria.objects.create` para
    levantar `IntegrityError` durante o `POST` no `change`; se a defesa
    valer, a alteração de `razao_social` REVERTE junto com a falha da
    trilha (mesma transação)."""
    escritorio = _criar_escritorio("Escr R5", "91100000000002")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Original R5", cnpj=CNPJ_EMPRESA_2
    )
    _criar_superusuario("super-r5")

    client = Client()
    _login(client, "super-r5")

    contagem_antes = RegistroAuditoria.objects.count()
    with mock.patch.object(
        RegistroAuditoria.objects, "create", side_effect=IntegrityError("audit falhou (DL-030 R5)")
    ):
        client.raise_request_exception = False
        resposta = client.post(
            f"/admin/empresas/empresa/{empresa.pk}/change/",
            data={
                "escritorio": escritorio.pk,
                "razao_social": "NAO PODE GRAVAR R5",
                "nome_fantasia": "",
                "cnpj": CNPJ_EMPRESA_2,
                "ativo": "on",
                "estabelecimentos-TOTAL_FORMS": "0",
                "estabelecimentos-INITIAL_FORMS": "0",
                "estabelecimentos-MIN_NUM_FORMS": "0",
                "estabelecimentos-MAX_NUM_FORMS": "1000",
            },
            follow=False,
        )

    assert resposta.status_code >= 500, (
        "DL-030 (R5): com a trilha falhando, a resposta precisa refletir o "
        f"erro do servidor (mock de IntegrityError), obtido {resposta.status_code}."
    )
    empresa.refresh_from_db()
    assert empresa.razao_social == "Original R5", (
        "DL-030 (R5): a gravação do objeto REVERTEU quando a trilha falhou? "
        f"razao_social ficou {empresa.razao_social!r} — atomicidade quebrada."
    )
    assert RegistroAuditoria.objects.count() == contagem_antes, (
        "DL-030 (R5): nenhum RegistroAuditoria pode sobrar de uma transação revertida."
    )


# -----------------------------------------------------------------------
# Critério de aceite 2 — POST no `delete` de Empresa grava trilha
# -----------------------------------------------------------------------
#
# O plano afirma "isto já passa hoje" para add/change/delete — add e
# change já tinham teste por requisição em test_dl024_trilha_admin.py;
# `delete` NÃO tinha nenhum teste por requisição no repositório (só o
# `pre_delete` genérico, nunca exercitado por um POST real ao admin).
# Não basta a afirmação do plano — fica provado aqui, também.


@pytest.mark.django_db(transaction=True)
def test_delete_de_empresa_via_admin_gera_trilha_com_valores_anteriores():
    """`POST /admin/empresas/empresa/<pk>/delete/` (confirmação de
    exclusão) precisa gravar `RegistroAuditoria` com
    `acao='empresas.empresa.admin_excluido'` e `valores_anteriores`
    contendo o estado do objeto apagado."""
    escritorio = _criar_escritorio("Escr CA2", "91100000000004")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa a apagar CA2", cnpj=CNPJ_EMPRESA_4
    )
    _criar_superusuario("super-ca2")

    client = Client()
    _login(client, "super-ca2")

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/delete/",
        data={"post": "yes"},
        follow=False,
    )
    assert resposta.status_code == 302, resposta.content
    assert not Empresa.objects.filter(pk=empresa.pk).exists()

    reg = RegistroAuditoria.objects.filter(acao="empresas.empresa.admin_excluido").get()
    assert reg.detalhes["valores_anteriores"].get("razao_social") == "Empresa a apagar CA2"
    assert reg.escritorio_id == escritorio.pk


# -----------------------------------------------------------------------
# R7 — inline (Estabelecimento) provado pela MESMA superfície
# -----------------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_alterar_estabelecimento_via_inline_do_change_de_empresa_gera_trilha():
    """`EstabelecimentoInline` grava pelo MESMO `ModelForm`/formset do
    `change` de `Empresa` (apps/empresas/admin.py). Prova pela mesma
    superfície que o plano exige (critério de aceite 6): POST no
    `change` de Empresa alterando o campo `nome` do estabelecimento
    existente via formset — não uma chamada direta a `save_formset`."""
    escritorio = _criar_escritorio("Escr R7", "91100000000003")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa R7", cnpj=CNPJ_EMPRESA_3
    )
    estabelecimento = Estabelecimento.objects.create(
        empresa=empresa, tipo="matriz", nome="Matriz Original R7", cnpj=CNPJ_ESTABELECIMENTO_1
    )
    _criar_superusuario("super-r7")

    client = Client()
    _login(client, "super-r7")

    resposta = client.post(
        f"/admin/empresas/empresa/{empresa.pk}/change/",
        data={
            "escritorio": escritorio.pk,
            "razao_social": "Empresa R7",
            "nome_fantasia": "",
            "cnpj": CNPJ_EMPRESA_3,
            "ativo": "on",
            "estabelecimentos-TOTAL_FORMS": "1",
            "estabelecimentos-INITIAL_FORMS": "1",
            "estabelecimentos-MIN_NUM_FORMS": "0",
            "estabelecimentos-MAX_NUM_FORMS": "1000",
            "estabelecimentos-0-id": str(estabelecimento.pk),
            "estabelecimentos-0-empresa": str(empresa.pk),
            "estabelecimentos-0-tipo": "matriz",
            "estabelecimentos-0-nome": "Matriz Atualizada R7",
            "estabelecimentos-0-cnpj": CNPJ_ESTABELECIMENTO_1,
            "estabelecimentos-0-logradouro": "",
            "estabelecimentos-0-numero": "",
            "estabelecimentos-0-complemento": "",
            "estabelecimentos-0-bairro": "",
            "estabelecimentos-0-municipio": "",
            "estabelecimentos-0-uf": "",
            "estabelecimentos-0-cep": "",
            "estabelecimentos-0-ativo": "on",
        },
        follow=False,
    )
    assert resposta.status_code == 302, resposta.content

    reg = RegistroAuditoria.objects.filter(acao="empresas.estabelecimento.admin_atualizado").get()
    assert reg.detalhes["valores_anteriores"].get("nome") == "Matriz Original R7"
    assert reg.detalhes["valores_novos"].get("nome") == "Matriz Atualizada R7"
    # R6 no inline: escritório derivado por indireção (Estabelecimento →
    # Empresa → Escritorio), não pela sessão de quem editou.
    assert reg.escritorio_id == escritorio.pk


# -----------------------------------------------------------------------
# R8 / DE-060 — declaração está escrita no código, não só neste arquivo
# -----------------------------------------------------------------------


def test_declaracoes_de_de060_estao_escritas_no_modulo():
    """Não substitui a leitura humana da docstring — só confirma que a
    declaração exigida por R8 (propriedade vs. substituto, e a
    divergência quando for substituto) está PRESENTE no código-fonte de
    `signals.py`, para as três medições que este mecanismo faz."""
    import inspect

    fonte = inspect.getsource(signals)
    assert "DE-060" in fonte
    # As três medições que precisam da declaração: diff (propriedade),
    # escritório do objeto (propriedade, com substituto declarado no
    # fallback) e redação por widget (substituto, com divergência
    # nomeada).
    assert "propriedade" in fonte.lower()
    assert "substituto" in fonte.lower()
    assert "ConviteEscritorio" in fonte, (
        "R4: o limite da redação por widget precisa citar um exemplo "
        "CONCRETO do projeto, não só hipotético."
    )
