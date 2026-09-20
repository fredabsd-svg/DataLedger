"""BL-16 (DL-024): imutabilidade do `RegistroAuditoria` contra
`update()`/`delete()` em massa.

Medido pelo auditor: o caminho individual (admin) já estava fechado pela
DL-023 — `RegistroAuditoriaAdmin.has_delete_permission` e
`has_change_permission` devolvem `False`. Mas o `QuerySet` do manager
continuava aberto:

- `RegistroAuditoria.objects.all().delete()` retornava `(N,)` e esvaziava
  a tabela em silêncio.
- `RegistroAuditoria.objects.filter(acao='login.sucesso').update(acao='foo')`
  retornava `3` e reescrevia o histórico sem deixar rastro.

`apps/auditoria/admin.py` cobre a INTERFACE; o manager do modelo cobre
`QuerySet.update()`/`delete()`/`bulk_update()`, que não emitem signals; e
este módulo cobre os caminhos de instância. Os dois níveis precisam falhar
o mais cedo possível para que `registrar()` na camada de serviço (BL-14)
também não seja capaz de reescrever o histórico.

Quem NÃO é bloqueado:
- `RegistroAuditoria.objects.create(...)` continua funcionando — novos
  registros são o que a trilha é feita de. O `pre_save` distingue
  INSERT de UPDATE por `_state.adding`, e só bloqueia o segundo.
- A leitura (`filter`, `get`, `count`, listagens) segue igual.

BL-244 (DL-024) / DL-030: trilha para o painel administrativo.

**Histórico da DE-060 sobre este mecanismo, que é o motivo desta reescrita**
(DL-030 — docs/planos/DL-030-a-trilha-cobre-o-admin.md): a primeira versão
(DL-024) media a cobertura por uma tupla explícita de seis modelos
(`MODELOS_DA_TRILHA_DO_ADMIN`). O `arquiteto-senior` pediu, na abertura da
DL-030, para trocar essa tupla pela leitura de `admin.site._registry` — e
depois reconheceu que ESSE pedido também estava errado, pelo mesmo motivo
(DE-060 aplicada a si mesmo): `admin.site._registry` só enxerga o que está
registrado no admin, e este mecanismo precisa cobrir **todo caminho de
escrita** (admin, API, shell, comando de gerência), não só o admin. A
decisão final, registrada no plano: cobrir **todo modelo concreto dos
apps PRÓPRIOS do projeto** (por inspeção do registro de apps do Django —
`apps.get_app_configs()` filtrado por `name.startswith("apps.")`, nunca uma
lista de seis nomes), com uma lista PEQUENA do que fica de fora, cada item
com o motivo escrito (`EXCLUSAO_DA_TRILHA_DO_ADMIN` abaixo) — é o mesmo
"lado seguro" que a BL-415 já aplicou (enumerar o que pode legitimamente
ficar de fora é mais seguro que enumerar o que entra: modelo novo criado em
`apps/*/models.py` passa a ser coberto SOZINHO, sem editar este arquivo).

Esta seção registra signals `pre_save`, `post_save` e `pre_delete` SEM
`sender=` (rodam para todo modelo do projeto Django, inclusive os de
terceiros — `django.contrib.sessions.Session`, `ContentType` etc.) e saem
cedo, por `modelos_cobertos_pela_trilha()`, quando o modelo não é do
projeto. A detecção do "caminho admin" usa `apps.core.current_request` —
preenchida por `apps.core.middleware.CurrentRequestMiddleware` — e o teste
de `request.path.startswith("/admin/")`. Se a request não é do admin (API,
teste, management command), os handlers caem fora silenciosamente — as
views continuam responsáveis pelo seu próprio `registrar()` (BL-14), e
a BL-244 não duplica trilha.

Atomicidade (R5 da DL-030): o admin do Django envolve `_changeform_view` e
`_delete_view` (`django/contrib/admin/options.py`) em
`transaction.atomic()` — MEDIDO nesta árvore (Django 6.1.1,
`inspect.getsource(ModelAdmin)`, três ocorrências de
`with transaction.atomic(using=router.db_for_write(self.model)):`,
cobrindo add/change e delete). Os signals deste módulo rodam DENTRO dessa
transação (Django dispara `pre_save`/`post_save`/`pre_delete` de dentro do
próprio `save()`/`delete()`, que o admin chama de dentro do `atomic()`). Se
`registrar()` falhar (ex.: `IntegrityError` na criação do
`RegistroAuditoria`), a exceção propaga para fora do `atomic()` do admin e
TODA a transação reverte — gravação do objeto incluída. Prova por execução
(não por leitura do comentário, que é exatamente o que a DE-058 proíbe
publicar sem medir): `apps/core/tests/test_dl030_trilha_cobre_o_admin.py`,
`test_change_de_empresa_via_admin_reverte_se_registrar_falha`.

Volume e custo (riscos declarados do plano DL-030): cada objeto de NÍVEL
SUPERIOR alterado gera NO MÁXIMO um `RegistroAuditoria` por save/delete
(independente de quantos campos mudaram dentro dele), e cada objeto de
INLINE alterado gera o seu próprio — uma sessão típica de edição (um
`change` de Empresa, às vezes com um Estabelecimento alterado no mesmo
POST) produz 1 ou 2 registros, não um por campo. Custo por requisição,
medido nesta árvore (`CaptureQueriesContext`, `POST` no `change` de
`Empresa` sem alteração de inline): 16 consultas SQL ANTES desta etapa
(mecanismo da DL-024, com `request.escritorio` fixo) e 17 DEPOIS — a
derivação do escritório pelo objeto (R6) custa **uma** consulta adicional
por evento quando a cadeia FK precisa ser seguida (`Conta`/
`Estabelecimento`/`HistoricoRegimeTributario`, um nível de indireção); a
lookup de widget para redação (R4) não soma consulta (só lê a classe do
formulário e seus campos, já carregados em memória pelo Django).
"""

import json

from django import forms as django_forms
from django.apps import apps as django_apps
from django.contrib import admin
from django.contrib.auth.forms import ReadOnlyPasswordHashWidget
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from apps.auditoria.models import MENSAGEM_IMUTABILIDADE, RegistroAuditoria
from apps.auditoria.services import registrar
from apps.core.current_request import get_current_request
from apps.tenancy.models import Escritorio

# --- BL-16 ----------------------------------------------------------------

MENSAGEM_DELETE = (
    f"{MENSAGEM_IMUTABILIDADE}: "
    "registros de auditoria são imutáveis — "
    "delete (incluindo o do QuerySet em massa) é proibido. "
    "Se a trilha precisa ser corrigida, registre um novo evento, "
    "não reescreva o histórico."
)
MENSAGEM_UPDATE = (
    f"{MENSAGEM_IMUTABILIDADE}: "
    "registros de auditoria são imutáveis — "
    "update (incluindo o do QuerySet em massa) é proibido. "
    "Se a trilha precisa ser corrigida, registre um novo evento, "
    "não reescreva o histórico."
)


@receiver(pre_delete, sender=RegistroAuditoria)
def _registro_auditoria_imutavel_para_delete(sender, instance, **kwargs):
    """Bloqueia `instance.delete()` e `QuerySet.delete()`.

    Disparado pelo signal `pre_delete` do Django, que cobre tanto a
    exclusão individual (`instance.delete()`) quanto a do manager
    (`QuerySet.delete()`) — qualquer `delete()` que chegue ao ORM
    passa por aqui antes de o ORM emitir o SQL.
    """
    raise PermissionDenied(MENSAGEM_DELETE)


@receiver(pre_save, sender=RegistroAuditoria)
def _registro_auditoria_imutavel_para_update(sender, instance, **kwargs):
    """Bloqueia o caminho de UPDATE; deixa o de INSERT passar.

    `pre_save` é disparado tanto para `create()` quanto para `save()` em
    instância já persistida. O atributo Django `_state.adding` distingue:
    é `True` enquanto a instância nunca foi gravada (INSERT), e vira
    `False` depois do primeiro save. Bloquear só quando `adding` é `False`
    é o que mantém `create()` (a única escrita legítima) funcionando.
    """
    if not instance._state.adding:
        raise PermissionDenied(MENSAGEM_UPDATE)


# --- BL-244 / DL-030: cobertura da trilha do admin -------------------------


def _apps_do_projeto():
    """`AppConfig` dos apps PRÓPRIOS do projeto.

    `apps.` é o pacote Python deste repositório (`apps/accounts`,
    `apps/auditoria`, `apps/contabilidade`, `apps/core`, `apps/empresas`,
    `apps/tenancy`) — nunca confundir com os apps de terceiros do
    `INSTALLED_APPS` (`django.contrib.*`, `rest_framework`, que não tem
    modelo). Por INSPEÇÃO do registro de apps do Django (prefixo do
    `AppConfig.name`), não por uma lista dos nomes: um app novo criado em
    `apps/` entra sozinho, sem editar este arquivo (R1/DE-056).
    """
    return [cfg for cfg in django_apps.get_app_configs() if cfg.name.startswith("apps.")]


# Modelos deliberadamente FORA da trilha do admin, com o motivo de cada um.
# Lado seguro (BL-415, aplicado aqui pelo mesmo argumento): a lista PEQUENA
# é do que fica de fora — todo modelo concreto NOVO criado em
# `apps/*/models.py` entra na cobertura por padrão, sem decisão explícita
# de ninguém. Adicionar um modelo aqui é que é a decisão consciente.
EXCLUSAO_DA_TRILHA_DO_ADMIN = {
    RegistroAuditoria: (
        "é o próprio destino da trilha: se ele se auto-registrasse, uma "
        "alteração administrativa produziria um segundo RegistroAuditoria "
        "sobre o primeiro, indefinidamente (laço). Também é dispensável na "
        "prática — RegistroAuditoriaAdmin já recusa add/change "
        "(has_add_permission/has_change_permission = False, DL-023) e "
        "delete (has_delete_permission = False, BL-16), então não existe "
        "INSERT, UPDATE nem DELETE administrativo deste modelo para "
        "registrar."
    ),
    Group: (
        "não é modelo de app do PROJETO — é `django.contrib.auth.Group`, "
        "registrado no admin pelo PRÓPRIO Django (`django/contrib/auth/"
        "admin.py`), não por código deste repositório, e por isso a "
        "guarda do R2 (`modelos_admin_sem_cobertura`) o encontraria sem "
        "esta linha. Medido: nenhum `apps/*/*.py` do projeto importa ou "
        "usa `django.contrib.auth.models.Group`/`Permission` — a "
        "autorização do DataLedger é `apps.tenancy.models.Papel` "
        "(campo `VinculoUsuarioEscritorio.papel`), não o esquema de "
        "grupos/permissões do Django. Se o produto passar a usar Group, "
        "cobri-lo é decisão nova, não extensão silenciosa desta lista."
    ),
}


def modelos_cobertos_pela_trilha():
    """Conjunto de modelos cobertos pela trilha do admin (R1 da DL-030).

    Todo modelo concreto de app PRÓPRIO do projeto (`_apps_do_projeto`),
    exceto os declarados em `EXCLUSAO_DA_TRILHA_DO_ADMIN`. `AppConfig.
    get_models()` já devolve só modelos concretos e gerenciados (não
    devolve abstratos nem proxies não registrados) — não há necessidade de
    filtrar `_meta.abstract`/`_meta.proxy` de novo aqui.

    DE-060 — propriedade medida: "todo modelo do PROJETO grava trilha
    quando alterado pelo admin". O que este conjunto NÃO cobre, por
    desenho, e é intencional: modelos de apps de terceiros
    (`django.contrib.sessions.Session`, `django.contrib.admin.LogEntry`,
    `django.contrib.auth.Permission`, `ContentType`) — `Group` é o único
    desses com `ModelAdmin` registrado hoje, e por isso está em
    `EXCLUSAO_DA_TRILHA_DO_ADMIN` explicitamente (a guarda do R2 o
    encontraria sem essa entrada); os demais nunca aparecem em
    `admin.site._registry`, então a guarda não teria como acusá-los — se
    um dia ganharem `ModelAdmin` ou precisarem de trilha, é decisão nova.
    """
    cobertos = set()
    for app_config in _apps_do_projeto():
        for model in app_config.get_models():
            if model not in EXCLUSAO_DA_TRILHA_DO_ADMIN:
                cobertos.add(model)
    return cobertos


def modelos_admin_sem_cobertura(admin_site=None):
    """R2 da DL-030 — a guarda da cobertura.

    Percorre `admin_site._registry` (todo `ModelAdmin` REALMENTE
    registrado, hoje) e devolve a lista dos modelos cujo `ModelAdmin` não
    está coberto por `modelos_cobertos_pela_trilha()` nem justificado em
    `EXCLUSAO_DA_TRILHA_DO_ADMIN`. Lista vazia é o estado correto.

    Broad por construção: cobre também um `ModelAdmin` registrado para um
    modelo de fora dos apps do projeto (ex.: um app de terceiros que
    ganhasse um `ModelAdmin` amanhã) — esse modelo não estaria em
    `modelos_cobertos_pela_trilha()` (que só enumera `apps.*`) e também não
    estaria em `EXCLUSAO_DA_TRILHA_DO_ADMIN`, então apareceria aqui,
    nomeado. É esta função — não a cobertura em si — que precisa saber do
    `admin.site`, porque é aqui que a pergunta é "o que está registrado no
    admin e não tem trilha?", e não "o que tem trilha?" (a distinção que a
    DE-060 cobrou: a primeira é a propriedade que a guarda do R2 promete
    medir; `modelos_cobertos_pela_trilha()` sozinha não a mede, porque um
    modelo de fora de `apps.*` nunca apareceria nela).
    """
    if admin_site is None:
        admin_site = admin.site
    cobertos = modelos_cobertos_pela_trilha()
    return [
        model
        for model in admin_site._registry
        if model not in cobertos and model not in EXCLUSAO_DA_TRILHA_DO_ADMIN
    ]


def _vem_do_admin(request):
    """Detecta se a operação em curso vem do painel administrativo.

    Heurística: `request.path.startswith("/admin/")`. Simples, estável,
    não depende do `resolver_match` (que pode não estar disponível no
    ponto em que o middleware rodou) e cobre tanto o admin do Django
    quanto qualquer customização que mantenha o prefixo `/admin/`.
    """
    if request is None:
        return False
    return request.path.startswith("/admin/")


def _snapshot_dos_campos(instance):
    """Devolve um dict simples com os campos do modelo para uso na
    trilha. Não é ISO 8601, não é serialização completa — é só o que
    o usuário precisa para entender o que mudou.

    DE-060 — propriedade medida: este snapshot lê `instance._meta.fields`
    de uma instância buscada do BANCO (`sender.objects.get(pk=...)` no
    `pre_save`, ou a própria `instance` recém-salva no `post_save`) — é o
    estado REALMENTE PERSISTIDO, não uma visão de formulário. O R3
    original da DL-030 pedia o inverso (usar `form.changed_data`/
    `form.initial`) e foi RETIRADO pelo `arquiteto-senior`: `form.initial`
    é a visão que o FORMULÁRIO tem do dado no momento do `GET`, e diverge
    do banco em edição concorrente entre o `GET` e o `POST`, em campo fora
    do formulário, e em valor alterado por `save()` do próprio modelo
    (ex.: `Empresa.save()` re-normaliza o CNPJ) — o formulário seria o
    substituto, a linha do banco é a propriedade.

    Risco declarado (plano DL-030, "campo grande"): um `TextField` longo
    alterado entraria DUAS vezes no JSON de `detalhes` (valor anterior e
    novo), sem truncamento. Medido nesta árvore: nenhum modelo coberto
    por `modelos_cobertos_pela_trilha()` tem `TextField` hoje (`grep -rn
    "TextField" apps/*/models.py` não devolve nada — o maior `CharField`
    é `Escritorio.endereco_no_timbre`, `max_length=300`). Por isso NÃO
    há truncamento implementado aqui — implementá-lo sem um caso real
    para calibrar o limite seria adivinhação. Se um `TextField` for
    adicionado a um modelo coberto no futuro, esta ausência de
    truncamento precisa ser revisitada ANTES (não depois) de expor esse
    campo no admin.
    """
    campos = {f.name: f.value_from_object(instance) for f in instance._meta.fields}
    return json.loads(json.dumps(campos, cls=DjangoJSONEncoder))


# --- R6: escritório derivado do OBJETO, não da sessão de quem edita -------


def _fk_para_escritorio(model):
    """Nome do campo do `model` que é FK direta para `Escritorio`, ou
    `None`. Por INSPEÇÃO do modelo (`field.related_model is Escritorio`),
    não por nome de campo — um FK chamado diferente de `escritorio` que
    apontasse para `Escritorio` seria achado do mesmo jeito."""
    for field in model._meta.get_fields():
        if not getattr(field, "many_to_one", False):
            continue
        if getattr(field, "related_model", None) is Escritorio:
            return field.name
    return None


def _escritorio_do_objeto(instance):
    """Deriva o escritório a que `instance` pertence, por inspeção do
    modelo (R6 da DL-030) — nunca por lista de nomes de campo.

    Ordem:
    1. O próprio objeto, se `instance` for um `Escritorio`.
    2. FK direta do modelo para `Escritorio` (`Empresa.escritorio`,
       `VinculoUsuarioEscritorio.escritorio`, `ConviteEscritorio.
       escritorio`).
    3. Um nível de indireção: para cada FK do modelo, se o modelo
       relacionado tiver FK direta para `Escritorio`, segue a cadeia
       (`Conta.empresa.escritorio`, `Estabelecimento.empresa.escritorio`,
       `HistoricoRegimeTributario.empresa.escritorio`).

    Devolve `None` quando nenhuma dessas resolver — é o caso de `Usuario`
    (não tem "um" escritório dono: um usuário pode ter vínculo com vários)
    e de qualquer modelo excluído da trilha. `_registrar_evento_de_admin`
    passa este resultado como `escritorio=` para `registrar()`, que já
    tem a REGRA declarada para `None`: cai para `request.escritorio` (o
    escritório ATIVO de quem fez a alteração — apps/auditoria/services.py)
    — e se esse também faltar (superuser do admin sem nenhum
    `VinculoUsuarioEscritorio`, caso comum de quem administra o Django
    admin), o registro grava `escritorio=None`. Declarado, não escondido:
    é exatamente o ponto que o `arquiteto-senior` marcou como o mais grave
    dos sete gaps medidos — a versão anterior deste mecanismo SEMPRE usava
    `request.escritorio`, e por isso um superuser sem vínculo editando
    Empresa do Escritório X gravava `escritorio=None` mesmo havendo um
    escritório óbvio (o da própria Empresa). Este passo 2/3 fecha
    exatamente esse caso.

    DE-060 — a cadeia 2/3 mede a PROPRIEDADE (o escritório real do
    objeto, pela FK que o modelo já declara). O fallback para
    `request.escritorio`, quando esta função devolve `None`, é
    estruturalmente um SUBSTITUTO diferente — não "a quem pertence o
    objeto", e sim "quem estava logado fazendo a alteração"; para
    `Usuario` isso pode gravar o escritório do ADMINISTRADOR que mexeu na
    conta, não um escritório do próprio usuário-alvo (que pode não ter
    nenhum, ou ter vários). É a melhor aproximação disponível quando a
    propriedade não existe (Usuario não tem "um" escritório), e fica
    escrita aqui como tal — não como a mesma coisa.
    """
    model = type(instance)
    if model is Escritorio:
        return instance
    campo_direto = _fk_para_escritorio(model)
    if campo_direto is not None:
        return getattr(instance, campo_direto)
    for field in model._meta.get_fields():
        if not getattr(field, "many_to_one", False):
            continue
        relacionado = getattr(field, "related_model", None)
        if relacionado is None:
            continue
        campo_indireto = _fk_para_escritorio(relacionado)
        if campo_indireto is None:
            continue
        # Evita disparar uma consulta para uma FK nula (ex.: campo
        # opcional sem valor): só segue a cadeia se o `_id` existir.
        if getattr(instance, f"{field.name}_id", None) is None:
            continue
        objeto_relacionado = getattr(instance, field.name, None)
        if objeto_relacionado is None:
            continue
        return getattr(objeto_relacionado, campo_indireto)
    return None


# --- R4: segredo redigido, derivado do WIDGET do formulário do admin ------


def _campos_secretos_por_widget(model, request, obj):
    """Nomes de campo do MODELO cujo widget, no formulário do `ModelAdmin`
    REGISTRADO para ele, é de senha — `PasswordInput` ou
    `ReadOnlyPasswordHashWidget` (usado por `UserChangeForm.password`).
    Deriva do WIDGET (R4 da DL-030), nunca de uma lista de nomes de campo
    — medido nesta árvore (Django 6.1.1): `UserChangeForm().base_fields
    ["password"].widget` é `ReadOnlyPasswordHashWidget`, e
    `UserCreationForm().base_fields["password1"].widget` é
    `PasswordInput` (mas `password1`/`password2` não são campos do
    MODELO — só existem no formulário de criação — então nunca aparecem
    no snapshot de qualquer forma; o campo do MODELO que carrega o hash
    é só `password`, coberto pelo primeiro caso).

    Limite declarado, não fechado (R4/DE-056 exigem a declaração, não
    prometem alcance total):

    1. Só enxerga o formulário do `ModelAdmin` registrado DIRETAMENTE em
       `admin.site._registry` (`model_admin.get_form`). Um campo secreto
       num modelo que só existe como INLINE de outro admin (hoje:
       `Estabelecimento`, inline de `EmpresaAdmin`) não tem seu widget
       consultado por este caminho — precisaria também percorrer
       `ModelAdmin.inlines`/`get_inline_instances`. Não é risco hoje
       (`Estabelecimento` não tem campo de senha), mas fica escrito para
       quando alguém adicionar um.
    2. Um campo que armazena segredo mas usa um widget comum (`TextInput`/
       `CharField` sem widget de senha declarado) não é detectado. Exemplo
       CONCRETO já existente no projeto:
       `apps.tenancy.models.ConviteEscritorio.token` — `CharField` opaco,
       sem `ModelAdmin` registrado hoje (então nem alcançável pelo admin
       ainda), mas se um dia ganhar um `ModelAdmin` sem `widget=
       PasswordInput` explícito no formulário, este mecanismo NÃO o
       redigirá — o token entraria em claro na trilha. Fora do escopo da
       DL-030 (nenhum admin novo está sendo criado aqui); registrado para
       quem criar esse admin no futuro.
    3. Campo ausente do formulário do admin (`exclude`/`fields` não o
       inclui) não tem widget para consultar — este mecanismo não o vê.
       Hoje nenhum modelo coberto está nesse caso para um campo secreto.
    """
    model_admin = admin.site._registry.get(model)
    if model_admin is None:
        return frozenset()
    form_class = model_admin.get_form(request, obj)
    campos_do_modelo = {f.name for f in model._meta.fields}
    widgets_de_senha = (django_forms.PasswordInput, ReadOnlyPasswordHashWidget)
    return frozenset(
        nome
        for nome, campo_formulario in form_class.base_fields.items()
        if nome in campos_do_modelo and isinstance(campo_formulario.widget, widgets_de_senha)
    )


MARCA_DE_REDACAO = "[valor redigido — RegistroAuditoria nunca grava segredo (AGENTS.md §11)]"


def _redigir(valores, secretos):
    """Devolve uma CÓPIA de `valores` com os campos de `secretos`
    substituídos por `MARCA_DE_REDACAO`. Nunca por vazio/`None` (que se
    confundiria com um valor real ausente) e nunca removendo a CHAVE — o
    critério de aceite 4 da DL-030 exige que o NOME do campo continue
    aparecendo, só não o valor."""
    if not secretos:
        return valores
    return {
        campo: (MARCA_DE_REDACAO if campo in secretos else valor)
        for campo, valor in valores.items()
    }


@receiver(pre_save)
def _admin_pre_save_snapshot(sender, instance, **kwargs):
    """Tira snapshot dos valores ANTES do save.

    Roda para qualquer `pre_save` de qualquer modelo. Só atua quando:
    - `sender` está em `modelos_cobertos_pela_trilha()`, E
    - a operação NÃO é INSERT (`_state.adding == False`), E
    - a request corrente vem do admin.

    Nos outros casos, sai sem fazer nada (registros via API continuam
    sendo responsabilidade da view). O snapshot fica em
    `instance._valores_anteriores` e é lido por `_admin_post_save` e
    `_admin_pre_delete`. Não redige segredo aqui: este snapshot só vive na
    memória do processo durante a mesma requisição, nunca é persistido —
    a redação (R4) acontece no ponto em que o valor é escrito em
    `RegistroAuditoria.detalhes`.
    """
    if sender not in modelos_cobertos_pela_trilha():
        return
    if instance._state.adding:
        return  # INSERT: nada a comparar
    if not _vem_do_admin(get_current_request()):
        return  # não-admin: a view já registra por conta própria
    try:
        anterior = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        instance._valores_anteriores = {}
        return
    instance._valores_anteriores = _snapshot_dos_campos(anterior)


@receiver(post_save)
def _admin_post_save_registra(sender, instance, created, **kwargs):
    """Registra a trilha após save feito pelo admin.

    Só atua quando o `pre_save` deixou `_valores_anteriores` na
    instance — ou seja, é UPDATE via admin. INSERT via admin também
    é coberto, com diff vazio e `detalhes` mínimo (sem valores
    anteriores — nada a redigir, porque nada é gravado).
    """
    if sender not in modelos_cobertos_pela_trilha():
        return
    request = get_current_request()
    if not _vem_do_admin(request):
        return
    valores_anteriores = getattr(instance, "_valores_anteriores", {}) or {}
    diff_anterior = {}
    diff_novo = {}
    if not created and valores_anteriores:
        valores_novos = _snapshot_dos_campos(instance)
        secretos = _campos_secretos_por_widget(sender, request, instance)
        for campo in valores_anteriores:
            if campo in valores_novos and valores_anteriores[campo] != valores_novos[campo]:
                diff_anterior[campo] = valores_anteriores[campo]
                diff_novo[campo] = valores_novos[campo]
        diff_anterior = _redigir(diff_anterior, secretos)
        diff_novo = _redigir(diff_novo, secretos)
    if created or diff_anterior:
        # `model._meta.label_lower` ("empresa.empresa") dá a origem
        # estável do sinal. A acao distingue INSERT/UPDATE/DELETE.
        sufixo = "admin_criado" if created else "admin_atualizado"
        detalhes = {}
        if diff_anterior:
            detalhes["valores_anteriores"] = diff_anterior
            detalhes["valores_novos"] = diff_novo
        registrar(
            acao=f"{sender._meta.label_lower}.{sufixo}",
            objeto=instance,
            escritorio=_escritorio_do_objeto(instance),
            request=request,
            detalhes=detalhes,
        )


@receiver(pre_delete)
def _admin_pre_delete_registra(sender, instance, **kwargs):
    """Registra a trilha ANTES do delete feito pelo admin.

    O snapshot precisa ter sido tirado antes do save — então lemos o
    `_valores_anteriores` deixado por `_admin_pre_save_snapshot` (que
    rodou no save anterior). Se nunca houve save anterior (registro
    criado direto e já apagado sem passar pelo admin), o dict está
    vazio e a trilha registra `admin_excluido` com `detalhes`
    mínimos — ainda é melhor que nada. Segredo é redigido (R4) do mesmo
    jeito que no update.
    """
    if sender not in modelos_cobertos_pela_trilha():
        return
    request = get_current_request()
    if not _vem_do_admin(request):
        return
    valores_anteriores = getattr(instance, "_valores_anteriores", None)
    if valores_anteriores is None:
        valores_anteriores = _snapshot_dos_campos(instance)
    secretos = _campos_secretos_por_widget(sender, request, instance)
    valores_anteriores = _redigir(valores_anteriores, secretos)
    registrar(
        acao=f"{sender._meta.label_lower}.admin_excluido",
        objeto=instance,
        escritorio=_escritorio_do_objeto(instance),
        request=request,
        detalhes={"valores_anteriores": valores_anteriores},
    )
