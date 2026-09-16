"""DL-023, critério 12 — varredura enumerativa do admin do Django.

## Por que este arquivo existe

BL-211/classe: "dois achados independentes na mesma superfície (BL-83 e o
inline de regime tributário) significam que a superfície não foi varrida, e
não que existam dois defeitos isolados." O `arquiteto-senior` mandou varrer
`24f6bbc` inteiro antes de corrigir qualquer coisa, e o inventário (feito
pelo `auxiliar-pesquisa`) encontrou **onze** superfícies de escrita
registradas: `EmpresaAdmin`, `EstabelecimentoInline`,
`HistoricoRegimeTributarioInline`, `ContaAdmin`, `ItemLancamentoInline`,
`LancamentoContabilAdmin`, `EscritorioAdmin`, `VinculoInline`,
`VinculoUsuarioEscritorioAdmin`, `UserAdmin` e `RegistroAuditoriaAdmin`.

**Discrepância encontrada por este teste, e registrada aqui porque não
estava no inventário do `arquiteto-senior`:** `admin.site._registry` também
contém `auth.Group -> django.contrib.auth.admin.GroupAdmin`, registrado
automaticamente pelo próprio `django.contrib.auth` (nenhum `admin.py` deste
projeto o menciona). São **doze** superfícies de nível 1 (mais os
`Inline`s), não onze — a diferença fica declarada no relatório da etapa.

## O que a varredura exige

Toda `ModelAdmin` registrada em `admin.site._registry` e todo `Inline`
EFETIVAMENTE anexado a cada uma delas (`get_inlines(request)` — não o
atributo `inlines` da classe) aparece em `DECISOES`, com uma categoria
(`"defendida"`, `"deliberadamente livre"` ou `"fora do produto"`) e uma
razão com pelo menos 40 caracteres — mesmo piso que `apps.core.restricoes.
RESTRICOES_SEM_CAMINHO_DE_CLIENTE` já usa para o mesmo tipo de declaração.
Superfície nova sem decisão **reprova nomeada**; não existe categoria
"ainda não olhamos".

**BL-257 (achado A4 da auditoria DL-023 rodada 1):** a primeira versão
desta varredura lia `modeladmin.inlines` — o ATRIBUTO de classe — direto.
O auditor reintroduziu `HistoricoRegimeTributarioInline` por
`get_inlines()` sobrescrito (resolução DINÂMICA, com o atributo `inlines`
intacto e vazio) e esta varredura **não viu** — quem matou o mutante foi
`test_admin_nao_cria_regime_tributario_mesmo_recebendo_os_campos_do_antigo_
inline` (teste POR REQUISIÇÃO, em `test_dl023_regime_tributario_periodo_
unico.py`), não a varredura estrutural. A correção é chamar
`modeladmin.get_inlines(request)` — o método que o Django REALMENTE chama
para montar a tela do `change` (o padrão da classe-base só devolve
`self.inlines`, mas uma subclasse pode sobrescrevê-lo, e foi exatamente
isso que escapou) — e nunca o atributo diretamente.

`_modeladmins`/`_inlines`/`_todas_as_superficies` recebem o registro (e um
`request`, para `_inlines`) como PARÂMETRO — não os buscam sozinhas — para
que o mutante "superfície nova sem decisão" E o mutante "inline por
`get_inlines()` dinâmico" possam ser reconstruídos dentro do próprio
teste, no molde da BL-197, sem registrar nenhuma `ModelAdmin` real no
`admin.site` global (que vazaria para o resto da suíte).

O `HistoricoRegimeTributarioInline` que existia em `24f6bbc` NÃO aparece
mais: foi REMOVIDO do `EmpresaAdmin` nesta etapa (BL-211/A2) — ver o
docstring de `apps/empresas/admin.py`. Uma superfície removida não precisa
de decisão registrada aqui; só as que continuam existindo precisam.
"""

import pytest
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.admin import Usuario
from apps.auditoria.admin import RegistroAuditoriaAdmin
from apps.contabilidade.admin import ContaAdmin, ItemLancamentoInline, LancamentoContabilAdmin
from apps.empresas.admin import EmpresaAdmin, EstabelecimentoInline
from apps.tenancy.admin import EscritorioAdmin, VinculoInline, VinculoUsuarioEscritorioAdmin

# ---------------------------------------------------------------------------
# Descoberta, por PARÂMETRO — ver o docstring do módulo.
# ---------------------------------------------------------------------------


def _requisicao_para_varredura():
    """Uma requisição mínima, só para `get_inlines(request)` ter o que
    pedir — a implementação padrão do Django (`ModelAdmin.get_inlines`)
    nem olha para dentro dela, mas uma subclasse PODE (é exatamente o que
    a defesa desta varredura precisa suportar, e não presumir). Usuário
    anônimo: nenhum `get_inlines` deste projeto precisa de usuário
    autenticado, e isso evita depender do banco só para varrer estrutura."""
    request = RequestFactory().get("/admin/")
    request.user = AnonymousUser()
    return request


def _modeladmins(registro):
    """`{"app_label.ModelName": modeladmin_ou_classe}` para cada entrada de
    nível 1 do registro do admin."""
    resultado = {}
    for modelo, modeladmin in registro.items():
        resultado[f"{modelo._meta.app_label}.{modelo._meta.object_name}"] = modeladmin
    return resultado


def _inlines(registro, request):
    """`{"modulo.Classe": inline_cls}` para cada `Inline` EFETIVAMENTE
    anexado (`get_inlines(request)`, não o atributo `inlines`), de todas
    as `ModelAdmin` do registro — ver BL-257 no docstring do módulo.

    Chaveado pela classe do INLINE (não pelo pai): é assim que o inventário
    do `arquiteto-senior` nomeia cada um (`EstabelecimentoInline`,
    `VinculoInline`, `ItemLancamentoInline`), e um inline hoje só é anexado
    a um admin — se um dia o mesmo inline for reaproveitado em dois
    admins, a chave colide e a decisão registrada vale para os dois, o que
    é o comportamento correto (é a MESMA classe, a mesma regra de negócio).
    """
    resultado = {}
    for modeladmin in registro.values():
        obter_inlines = getattr(modeladmin, "get_inlines", None)
        if callable(obter_inlines):
            # `obj=None`: mesma chamada que o Django faz para a tela de
            # `add` (`ModelAdmin.get_inline_instances`, sem instância
            # ainda) — a varredura estrutural não tem um objeto real para
            # oferecer, e não deveria precisar de um para saber QUAIS
            # classes de inline existem.
            inlines = obter_inlines(request, None)
        else:
            # Retaguarda só para os `ModelAdmin` FALSOS dos testes de
            # mutação abaixo, que não precisam imitar a classe inteira do
            # Django — qualquer `ModelAdmin` real sempre tem `get_inlines`
            # (é método da classe-base).
            inlines = getattr(modeladmin, "inlines", [])
        for inline_cls in inlines:
            resultado[f"{inline_cls.__module__}.{inline_cls.__qualname__}"] = inline_cls
    return resultado


def _todas_as_superficies(registro, request=None):
    superficies = _modeladmins(registro)
    superficies.update(_inlines(registro, request or _requisicao_para_varredura()))
    return superficies


CATEGORIAS_VALIDAS = {"defendida", "deliberadamente livre", "fora do produto"}

# ---------------------------------------------------------------------------
# O inventário: DOZE superfícies de nível 1 (onze do achado do
# `arquiteto-senior` + `auth.Group`, achado desta varredura) mais os
# QUATRO `Inline`s. Cada entrada é (categoria, razão).
# ---------------------------------------------------------------------------

DECISOES = {
    # --- ModelAdmin de nível 1 -------------------------------------------
    "empresas.Empresa": (
        "defendida",
        "DL-023 (BL-211/A3): Empresa.clean() recusa troca de escritório com "
        "escrituração, e EmpresaAdmin.get_readonly_fields trava 'escritorio' "
        "no change — testado por requisição em test_dl023_empresa_nao_muda_"
        "de_escritorio.py.",
    ),
    "contabilidade.Conta": (
        "defendida",
        "DL-023 (BL-83): Conta.clean() recusa troca de empresa com movimento "
        "ou filhas, e troca de natureza/tipo com movimento — testado por "
        "requisição em test_dl023_conta_nao_muda_de_empresa_ou_natureza.py.",
    ),
    "contabilidade.LancamentoContabil": (
        "defendida",
        "Pré-existente à DL-023 (DE-023/BL-79): has_add_permission, "
        "has_change_permission e has_delete_permission devolvem False; "
        "lançamento também é imutável no modelo (LancamentoImutavelError). "
        "Coberto por apps/contabilidade/tests/test_dl015_saidas_com_"
        "periodo.py e test_dl019_faixa_de_data.py.",
    ),
    "auditoria.RegistroAuditoria": (
        "defendida",
        "DL-023 (critério 13): has_add_permission e has_change_permission já "
        "devolviam False; has_delete_permission passou a devolver False "
        "nesta etapa — testado por requisição individual e em lote em "
        "test_dl023_registro_de_auditoria_nao_se_apaga.py.",
    ),
    "tenancy.Escritorio": (
        "deliberadamente livre",
        "Cadastro de escritório (a fronteira mais externa de isolamento) não "
        "tem invariante estrutural equivalente a BL-83/BL-211 medida nesta "
        "etapa. O único índice único implícito (cnpj) já está registrado em "
        "apps.core.restricoes.RESTRICOES_SEM_CAMINHO_DE_CLIENTE.",
    ),
    "tenancy.VinculoUsuarioEscritorio": (
        "deliberadamente livre",
        "A constraint 'unico_vinculo_usuario_escritorio' (Meta.constraints) "
        "já é validada por full_clean() do ModelForm do admin — registrada "
        "em apps.core.restricoes.RESTRICOES_SEM_CAMINHO_DE_CLIENTE. Sem "
        "invariante adicional identificada nesta etapa (papel/escritório).",
    ),
    "accounts.Usuario": (
        "deliberadamente livre",
        "UserAdmin é a classe padrão do próprio Django "
        "(django.contrib.auth.admin), não subclasse deste projeto. Sem "
        "invariante de domínio do DataLedger identificada nesta etapa; "
        "primeiro acesso e criação de usuário são escopo da DL-018.",
    ),
    "auth.Group": (
        "fora do produto",
        "Registrado automaticamente por django.contrib.auth (GroupAdmin), "
        "não por nenhum admin.py deste projeto. 'Group' é o modelo de "
        "permissões do próprio Django, não uma entidade de negócio do "
        "DataLedger — mesma fronteira que exclui módulos django.* na "
        "varredura de contratos (apps/core/tests/test_dl019_varredura_de_"
        "contratos.py).",
    ),
    # --- Inline --------------------------------------------------------
    "apps.empresas.admin.EstabelecimentoInline": (
        "deliberadamente livre",
        "As duas constraints de Estabelecimento (uma_matriz_por_empresa, "
        "estabelecimento_cnpj_canonico) já são Meta.constraints validadas "
        "por full_clean() do ModelForm do admin — mesmo mecanismo do "
        "'unico_vinculo_usuario_escritorio' acima. Sem invariante "
        "equivalente a BL-83/BL-211 identificada nesta etapa.",
    ),
    "apps.contabilidade.admin.ItemLancamentoInline": (
        "defendida",
        "Pré-existente (DE-023/BL-79): inatingível por requisição porque "
        "LancamentoContabilAdmin.has_add_permission e "
        "has_change_permission devolvem False — o admin nunca oferece a "
        "tela onde este inline apareceria. ItemLancamento.clean() é defesa "
        "em profundidade adicional, para qualquer outro ModelForm.",
    ),
    "apps.tenancy.admin.VinculoInline": (
        "deliberadamente livre",
        "Mesma constraint 'unico_vinculo_usuario_escritorio' do "
        "VinculoUsuarioEscritorioAdmin acima, já validada por full_clean() "
        "do ModelForm do admin. Sem invariante adicional identificada "
        "nesta etapa.",
    ),
}


def test_toda_superficie_do_admin_registrado_tem_decisao():
    superficies = _todas_as_superficies(admin.site._registry)
    sem_decisao = sorted(set(superficies) - set(DECISOES))

    assert not sem_decisao, (
        "Superfície nova no admin sem decisão registrada em "
        "apps/core/tests/test_dl023_varredura_admin.py:DECISOES:\n"
        + "\n".join(f"  {nome}" for nome in sem_decisao)
        + "\n\nEscolha UMA categoria: 'defendida' (regra mora no modelo ou em "
        "permissão, testada por requisição), 'deliberadamente livre' (sem "
        "invariante estrutural identificada) ou 'fora do produto' "
        "(registrado por terceiro, não por admin.py deste projeto). "
        "Superfície nova sem dono é o defeito, não a exceção."
    )


def test_nenhuma_decisao_registrada_esta_orfa():
    """Direção inversa: uma entrada de `DECISOES` que não corresponda a
    nenhuma superfície REAL (removida, renomeada) encobriria a próxima
    superfície que herdasse o mesmo nome, ou simplesmente envelheceria sem
    ninguém notar."""
    superficies = _todas_as_superficies(admin.site._registry)
    orfas = sorted(set(DECISOES) - set(superficies))

    assert not orfas, orfas


@pytest.mark.parametrize("chave", sorted(DECISOES))
def test_cada_decisao_tem_categoria_valida_e_razao_com_tamanho_minimo(chave):
    categoria, razao = DECISOES[chave]

    assert categoria in CATEGORIAS_VALIDAS, (chave, categoria)
    # Mesmo piso de 40 caracteres que RESTRICOES_SEM_CAMINHO_DE_CLIENTE já
    # usa (apps/core/restricoes.py): uma razão vazia ou de uma palavra
    # seria dispensa disfarçada de decisão.
    assert len(razao.strip()) >= 40, (chave, razao)


# ---------------------------------------------------------------------------
# A demonstração da defesa (critério 14, prova por mutação): reconstruída
# dentro do próprio teste, sem tocar em `admin.site` real — mesmo molde de
# `test_a_varredura_reprova_constraint_nova_sem_traducao`
# (apps/core/tests/test_dl019_varredura_de_restricoes.py).
# ---------------------------------------------------------------------------


def test_a_varredura_reprova_superficie_nova_sem_decisao_registrada():
    class _ModeloFalso:
        class _meta:
            app_label = "app_ficticio"
            object_name = "ModeloNovo"

    class _ModelAdminFalso:
        inlines = []

    registro_falso = {_ModeloFalso: _ModelAdminFalso()}

    superficies = _todas_as_superficies(registro_falso)
    sem_decisao = sorted(set(superficies) - set(DECISOES))

    assert sem_decisao == ["app_ficticio.ModeloNovo"]


def test_a_varredura_enxerga_inline_novo_sem_decisao_registrada():
    class _ModeloFalso:
        class _meta:
            app_label = "app_ficticio"
            object_name = "ModeloComInline"

    class _InlineFalso:
        pass

    _InlineFalso.__module__ = "app_ficticio.admin"
    _InlineFalso.__qualname__ = "InlineFalso"

    class _ModelAdminFalso:
        inlines = [_InlineFalso]

    registro_falso = {_ModeloFalso: _ModelAdminFalso()}

    superficies = _todas_as_superficies(registro_falso)

    assert "app_ficticio.admin.InlineFalso" in superficies
    assert "app_ficticio.admin.InlineFalso" not in DECISOES


def test_a_varredura_enxerga_inline_anexado_por_get_inlines_dinamico():
    """BL-257 (achado A4): reconstrução do mutante exato do auditor — um
    `ModelAdmin` com `inlines = []` ESTÁTICO (vazio, de propósito) que
    sobrescreve `get_inlines(request)` para devolver um inline mesmo assim.
    Ler só o atributo `inlines` (a versão anterior desta varredura) via
    `getattr(modeladmin, "inlines", [])` devolveria `[]` e o mutante
    passaria em silêncio — é exatamente essa fuga que o achado mediu."""

    class _ModeloFalso:
        class _meta:
            app_label = "app_ficticio"
            object_name = "ModeloComInlineDinamico"

    class _InlineDinamicoFalso:
        pass

    _InlineDinamicoFalso.__module__ = "app_ficticio.admin"
    _InlineDinamicoFalso.__qualname__ = "InlineDinamicoFalso"

    class _ModelAdminComInlineDinamico:
        inlines = []  # ESTÁTICO vazio, de propósito — é o que engana a leitura ingênua

        def get_inlines(self, request, obj=None):
            return [_InlineDinamicoFalso]

    registro_falso = {_ModeloFalso: _ModelAdminComInlineDinamico()}

    # Confere primeiro que a leitura ESTÁTICA (a versão antiga) não veria
    # nada — é o que prova que o mutante É invisível por esse caminho.
    assert list(_ModelAdminComInlineDinamico.inlines) == []

    superficies = _todas_as_superficies(registro_falso, _requisicao_para_varredura())

    assert "app_ficticio.admin.InlineDinamicoFalso" in superficies
    assert "app_ficticio.admin.InlineDinamicoFalso" not in DECISOES


# ---------------------------------------------------------------------------
# Controle: o inventário conferido (BL-211, achado da rodada 1 da DL-020 e
# do inventário de abertura desta etapa) continua batendo com o que o
# repositório REGISTRA hoje — se alguém remover um admin.py inteiro sem
# querer, este teste nomeia o que sumiu.
# ---------------------------------------------------------------------------

SUPERFICIES_CONFERIDAS_NO_INVENTARIO_DE_24F6BBC = {
    "empresas.Empresa": EmpresaAdmin,
    "contabilidade.Conta": ContaAdmin,
    "contabilidade.LancamentoContabil": LancamentoContabilAdmin,
    "auditoria.RegistroAuditoria": RegistroAuditoriaAdmin,
    "tenancy.Escritorio": EscritorioAdmin,
    "tenancy.VinculoUsuarioEscritorio": VinculoUsuarioEscritorioAdmin,
    "apps.empresas.admin.EstabelecimentoInline": EstabelecimentoInline,
    "apps.contabilidade.admin.ItemLancamentoInline": ItemLancamentoInline,
    "apps.tenancy.admin.VinculoInline": VinculoInline,
}


@pytest.mark.parametrize("chave", sorted(SUPERFICIES_CONFERIDAS_NO_INVENTARIO_DE_24F6BBC))
def test_superficie_conferida_no_inventario_continua_registrada(chave):
    superficies = _todas_as_superficies(admin.site._registry)
    esperado = SUPERFICIES_CONFERIDAS_NO_INVENTARIO_DE_24F6BBC[chave]

    assert chave in superficies, sorted(superficies)
    encontrado = superficies[chave]
    # `ModelAdmin` de nível 1 aparece como INSTÂNCIA em `admin.site.
    # _registry`; `Inline` aparece como a própria CLASSE (nunca
    # instanciado nesse ponto) — daí a checagem em duas formas.
    assert encontrado is esperado or isinstance(encontrado, esperado)


def test_usuario_e_o_modelo_de_usuario_configurado_do_projeto():
    """Confere que `Usuario` (import usado só para não deixar `accounts.
    Usuario` como texto solto) é de fato o AUTH_USER_MODEL — não uma
    suposição."""
    from django.contrib.auth import get_user_model

    assert get_user_model() is Usuario
