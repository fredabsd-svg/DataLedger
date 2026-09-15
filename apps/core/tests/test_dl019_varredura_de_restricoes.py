"""Varredura de repositório das restrições de banco (BL-167/BL-157).

## Por que este arquivo existe

`apps/core/restricoes.py` **afirmava por escrito** que este módulo já
existia — que ele "percorre TODOS os modelos dos apps do projeto" e que "uma
constraint nova sem tradução reprova a suíte". O arquivo **não existia**
(achado do inventário de 2026-09-15, BL-167): décima-segunda ocorrência da
família "comentário que afirma mais do que a defesa entrega", e a mais
irônica delas, porque o comentário descrevia exatamente o mecanismo que a
BL-157 pede e explicava por que ele é necessário — *"conferência manual não
reprova build; registro + varredura de repositório reprova"*.

O histórico justifica a desconfiança: o critério da BL-144 era "para cada
`Meta.constraints` existe caminho de API que a converte em 400", a
conferência **foi feita**, e ainda assim **duas** constraints ficaram de fora
— as duas `CheckConstraint` de canonização de CNPJ, declaradas no MESMO
`Meta` que a BL-144 fechou.

## O que a varredura exige, e o que ela deliberadamente NÃO cobre

**Exige:** todo nome de restrição declarado em `Meta.constraints` de qualquer
modelo de `apps/**` aparece em UM dos TRÊS registros de
`apps.core.restricoes` — `MENSAGENS_DE_RESTRICAO` (traduzida por
`restricao_como_400`), `RESTRICOES_TRADUZIDAS_FORA_DO_MAPA` (traduzida em
outro ponto, nomeado e verificado) ou `RESTRICOES_SEM_CAMINHO_DE_CLIENTE`
(sem caminho de escrita por cliente, com razão escrita). O que a varredura
proíbe é o **silêncio**, não a ausência de tradução: uma restrição que
nenhuma requisição alcança pode ficar sem tradução, mas não pode ficar sem
declaração.

**Não cobre:** os índices únicos IMPLÍCITOS, criados por `unique=True` em
campo (`accounts_usuario_username_key` e companhia). Eles não estão em
`Meta.constraints` e não são alcançáveis por esta varredura sem uma segunda
gramática de nomes, própria do PostgreSQL. A fronteira não fica implícita:
`test_o_conjunto_de_indices_unicos_implicitos_e_conhecido` prende a lista
atual, então um `unique=True` NOVO reprova a suíte e força a decisão em vez
de escapar — que é a mesma armadilha da "décima quinta `APIView`" da BL-134.
"""

import importlib

import pytest
from django.apps import apps as registro_de_apps
from django.db import models

from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO,
    RESTRICOES_SEM_CAMINHO_DE_CLIENTE,
    RESTRICOES_TRADUZIDAS_FORA_DO_MAPA,
)

# As 7 restrições de `Meta.constraints` conferidas uma a uma no inventário de
# 2026-09-15. Controle NOMINAL, no molde de `test_permission_classes_
# explicito.test_varredura_inclui_as_14_apiviews_conferidas_pelo_auditor`: se
# uma sumir (renomeada, movida, removida), o teste falha apontando QUAL, em
# vez de o total só cair em silêncio.
RESTRICOES_CONFERIDAS = {
    "codigo_unico_por_empresa": "contabilidade.Conta",
    "estorno_de_unico": "contabilidade.LancamentoContabil",
    "chave_idempotencia_unica_por_empresa": "contabilidade.LancamentoContabil",
    "empresa_cnpj_canonico": "empresas.Empresa",
    "uma_matriz_por_empresa": "empresas.Estabelecimento",
    "estabelecimento_cnpj_canonico": "empresas.Estabelecimento",
    "unico_vinculo_usuario_escritorio": "tenancy.VinculoUsuarioEscritorio",
}

# Índices únicos implícitos (`unique=True` em campo) existentes hoje, com o
# nome que o PostgreSQL dá a cada um. Ver o docstring do módulo: eles estão
# FORA da varredura principal, e esta lista é o que impede que "estar fora"
# se transforme em "passar sem ninguém ver".
INDICES_UNICOS_IMPLICITOS_CONHECIDOS = {
    "accounts_usuario_username_key",
    "accounts_usuario_email_key",
    "tenancy_escritorio_cnpj_key",
    "empresas_empresa_cnpj_key",
    "empresas_estabelecimento_cnpj_key",
}


def _modelos_do_repositorio():
    """Todo modelo concreto de um app do PROJETO (`apps.*`).

    Usa o registro de apps do Django, não uma varredura de arquivos: um
    modelo declarado fora de `models.py`, ou herdado de uma base abstrata,
    também aparece — e um app novo entra na varredura sem ninguém editar
    este arquivo. O filtro `cfg.name.startswith("apps.")` exclui os apps do
    próprio Django e de terceiros, cujas constraints não são invariantes
    deste produto.
    """
    modelos = []
    for cfg in registro_de_apps.get_app_configs():
        if not cfg.name.startswith("apps."):
            continue
        modelos.extend(cfg.get_models())
    return modelos


def constraints_declaradas(modelos):
    """`{nome_da_constraint: "app_label.Modelo"}` para os modelos dados.

    Recebe os modelos como PARÂMETRO, e não os busca por conta própria, para
    que `test_a_varredura_reprova_constraint_nova_sem_traducao` possa
    reconstruir o mutante — uma constraint nova, sem tradução — dentro do
    próprio teste, sem tocar em nenhum modelo real (modelo da BL-150: a
    demonstração não pode depender de alguém ter lembrado de registrar que
    viu o teste falhar).
    """
    encontradas = {}
    for modelo in modelos:
        for constraint in modelo._meta.constraints:
            rotulo = f"{modelo._meta.app_label}.{modelo.__name__}"
            encontradas[constraint.name] = rotulo
    return encontradas


def _nomes_registrados():
    """União dos TRÊS registros de `apps.core.restricoes`."""
    return (
        set(MENSAGENS_DE_RESTRICAO)
        | set(RESTRICOES_TRADUZIDAS_FORA_DO_MAPA)
        | set(RESTRICOES_SEM_CAMINHO_DE_CLIENTE)
    )


def constraints_sem_registro(modelos):
    """A função que a varredura afirma existir: `{nome: modelo}` das
    restrições declaradas em `Meta` que NÃO aparecem em nenhum dos três
    registros. Vazio é o único resultado aceitável para os modelos reais.
    """
    registrados = _nomes_registrados()
    return {
        nome: modelo
        for nome, modelo in constraints_declaradas(modelos).items()
        if nome not in registrados
    }


def _indices_unicos_implicitos(modelos):
    """Nome PostgreSQL do índice único que cada `unique=True` de campo cria.

    O padrão do PostgreSQL para a restrição de unicidade de coluna é
    `<tabela>_<coluna>_key` (é dele que vem `empresas_empresa_cnpj_key`, o
    nome que `apps.empresas.services.mensagem_se_cnpj_duplicado` já
    reconhece hoje). Chaves primárias ficam fora: são `_pkey`, e nenhuma
    requisição de cliente escolhe o `id`.
    """
    nomes = set()
    for modelo in modelos:
        for campo in modelo._meta.local_fields:
            if getattr(campo, "unique", False) and not campo.primary_key:
                nomes.add(f"{modelo._meta.db_table}_{campo.column}_key")
    return nomes


# ---------------------------------------------------------------------------
# Controle de que a varredura enxerga algo — se estes caírem, suspeite dos
# auxiliares antes de confiar no teste principal.
# ---------------------------------------------------------------------------


def test_a_varredura_encontra_as_constraints_declaradas_hoje():
    declaradas = constraints_declaradas(_modelos_do_repositorio())
    assert len(declaradas) >= len(RESTRICOES_CONFERIDAS), declaradas


@pytest.mark.parametrize("nome", sorted(RESTRICOES_CONFERIDAS))
def test_varredura_inclui_cada_restricao_conferida_no_inventario(nome):
    declaradas = constraints_declaradas(_modelos_do_repositorio())
    assert nome in declaradas, sorted(declaradas)
    assert declaradas[nome] == RESTRICOES_CONFERIDAS[nome]


# ---------------------------------------------------------------------------
# O teste principal: nenhuma constraint declarada fica sem registro.
# ---------------------------------------------------------------------------


def test_toda_constraint_de_meta_aparece_em_um_dos_tres_registros():
    """BL-157/BL-167. É este teste que o comentário de `apps/core/restricoes.
    py` promete: uma `CheckConstraint`/`UniqueConstraint` nova, declarada num
    `Meta` e sem tradução nem declaração, reprova a suíte.
    """
    orfas = constraints_sem_registro(_modelos_do_repositorio())

    assert not orfas, (
        "Restrição de banco declarada em Meta.constraints e ausente dos três "
        "registros de apps/core/restricoes.py:\n"
        + "\n".join(f"  {nome} ({modelo})" for nome, modelo in sorted(orfas.items()))
        + "\n\nEscolha UM: MENSAGENS_DE_RESTRICAO (a API traduz para 400), "
        "RESTRICOES_TRADUZIDAS_FORA_DO_MAPA (outro ponto traduz — aponte qual) "
        "ou RESTRICOES_SEM_CAMINHO_DE_CLIENTE (nenhuma requisição de cliente a "
        "alcança — escreva por quê). Deixar de fora não é opção: foi assim que "
        "as duas CheckConstraint de canonização de CNPJ passaram pela "
        "conferência manual da BL-144."
    )


def test_a_varredura_reprova_constraint_nova_sem_traducao():
    """A demonstração da defesa, reconstruída dentro do próprio teste.

    Modelo imitado: `test_a_varredura_mata_o_m17_reconstruido_a_partir_do_
    fonte_real` (BL-150), a única defesa da DL-019 que já estava demonstrada
    no inventário. O mutante desta varredura é "acrescentar uma constraint
    nova sem mapear", e aqui ele é construído em memória — um objeto com o
    mesmo `_meta.constraints` que um modelo real expõe, carregando uma
    `CheckConstraint` de verdade — para que a prova não dependa de ninguém
    ter registrado que viu a suíte falhar, nem de editar um modelo real.

    O par com o teste acima é o que fecha a lógica: aquele prova que a
    varredura passa para o repositório de hoje; este prova que ela **sabe
    reprovar**. Um dos dois sozinho é controle positivo, e controle positivo
    só mata o mutante "a função não faz nada".
    """

    class _MetaFalso:
        app_label = "app_ficticio"
        constraints = (
            models.CheckConstraint(
                condition=models.Q(valor__gte=0),
                name="constraint_nova_que_ninguem_mapeou",
            ),
        )

    class ModeloComConstraintNova:
        _meta = _MetaFalso()

    # Sanidade: o nome do mutante não pode existir de verdade, ou o teste
    # estaria medindo outra coisa.
    assert "constraint_nova_que_ninguem_mapeou" not in _nomes_registrados()

    orfas = constraints_sem_registro([ModeloComConstraintNova])

    assert orfas == {"constraint_nova_que_ninguem_mapeou": "app_ficticio.ModeloComConstraintNova"}


# ---------------------------------------------------------------------------
# Os registros não podem envelhecer: cada entrada tem de continuar
# correspondendo a algo real.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("nome", sorted(MENSAGENS_DE_RESTRICAO))
def test_cada_nome_de_mensagens_de_restricao_e_uma_constraint_que_existe(nome):
    """Direção INVERSA da varredura, e ela pega um defeito diferente: um nome
    de constraint escrito errado no registro (ou deixado para trás depois de
    uma renomeação) produziria um `with restricao_como_400(...)` que nunca
    traduz nada — o 500 voltaria em silêncio, com o registro dando a
    impressão de cobertura. `mensagens_de()` levanta `KeyError` para nome
    fora do registro; nada, até aqui, checava o contrário.
    """
    declaradas = constraints_declaradas(_modelos_do_repositorio())
    assert nome in declaradas, sorted(declaradas)


@pytest.mark.parametrize("nome", sorted(RESTRICOES_SEM_CAMINHO_DE_CLIENTE))
def test_cada_restricao_sem_caminho_de_cliente_existe_e_tem_razao_escrita(nome):
    declaradas = constraints_declaradas(_modelos_do_repositorio())
    assert nome in declaradas, sorted(declaradas)
    razao = RESTRICOES_SEM_CAMINHO_DE_CLIENTE[nome]
    # "Sem caminho de cliente" é declaração de LIMITE e precisa de motivo
    # legível — um registro com string vazia viraria dispensa silenciosa, que
    # é exatamente o que esta varredura existe para impedir.
    assert isinstance(razao, str) and len(razao.strip()) >= 40, razao


@pytest.mark.parametrize("nome", sorted(RESTRICOES_TRADUZIDAS_FORA_DO_MAPA))
def test_cada_restricao_traduzida_fora_do_mapa_aponta_para_objeto_chamavel(nome):
    """O registro diz ONDE a tradução mora; se o caminho citado for renomeado
    ou apagado, a afirmação passa a ser falsa. Importar e conferir que o
    objeto existe e é chamável transforma a citação em verificação — é o
    contrário de `apps/core/restricoes.py` afirmando um arquivo de teste que
    não existia (BL-167).
    """
    caminho = RESTRICOES_TRADUZIDAS_FORA_DO_MAPA[nome]
    modulo_nome, atributo = caminho.rsplit(".", 1)
    modulo = importlib.import_module(modulo_nome)
    alvo = getattr(modulo, atributo, None)
    assert alvo is not None, f"{caminho} não existe mais"
    assert callable(alvo), f"{caminho} existe mas não é chamável"


@pytest.mark.parametrize("nome", sorted(RESTRICOES_TRADUZIDAS_FORA_DO_MAPA))
def test_cada_restricao_traduzida_fora_do_mapa_e_de_meta_ou_indice_implicito(nome):
    """Toda entrada deste registro corresponde a uma restrição REAL: ou está
    em `Meta.constraints`, ou é o índice único implícito de um campo
    `unique=True` (as duas `*_cnpj_key`). Sem isto, renomear `Empresa.cnpj`
    — ou a tabela — deixaria `empresas_empresa_cnpj_key` apontando para nada,
    e a tradução de CNPJ duplicado voltaria a ser 500 sem nenhum sinal.
    """
    modelos = _modelos_do_repositorio()
    reais = set(constraints_declaradas(modelos)) | _indices_unicos_implicitos(modelos)
    assert nome in reais, sorted(reais)


def test_o_conjunto_de_indices_unicos_implicitos_e_conhecido():
    """A fronteira declarada no docstring do módulo, virada verificação.

    Índice único implícito não entra na varredura principal (não está em
    `Meta.constraints`), mas violar um deles produz `IntegrityError` igual.
    Prender a lista atual faz um `unique=True` NOVO reprovar a suíte, com a
    pergunta na mensagem — em vez de nascer sem tradução, que é a armadilha
    da "décima quinta `APIView`" da BL-134.
    """
    encontrados = _indices_unicos_implicitos(_modelos_do_repositorio())

    assert encontrados == INDICES_UNICOS_IMPLICITOS_CONHECIDOS, (
        "A lista de índices únicos implícitos mudou. Para cada NOVO nome, "
        "responda: existe caminho de escrita por cliente que possa violá-lo? "
        "Se sim, ele precisa de tradução para 400 (como as duas *_cnpj_key, "
        "em RESTRICOES_TRADUZIDAS_FORA_DO_MAPA); se não, registre o motivo. "
        f"Esperado: {sorted(INDICES_UNICOS_IMPLICITOS_CONHECIDOS)}; "
        f"encontrado: {sorted(encontrados)}."
    )
