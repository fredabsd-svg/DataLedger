"""Varredura de repositório das restrições de banco (BL-214/BL-204).

## Por que este arquivo existe

`apps/core/restricoes.py` **afirmava por escrito** que este módulo já
existia — que ele "percorre TODOS os modelos dos apps do projeto" e que "uma
constraint nova sem tradução reprova a suíte". O arquivo **não existia**
(achado do inventário de 2026-09-15, BL-214): décima-segunda ocorrência da
família "comentário que afirma mais do que a defesa entrega", e a mais
irônica delas, porque o comentário descrevia exatamente o mecanismo que a
BL-204 pede e explicava por que ele é necessário — *"conferência manual não
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

**Não cobre pela varredura principal:** os índices únicos IMPLÍCITOS. Eles
não estão em `Meta.constraints`, e nomeá-los exige uma segunda gramática de
nomes, própria do banco. São **três** formas, e a terceira entrou com a
BL-219 (achado A6 da auditoria DL-020 rodada 1), porque a fronteira estava
declarada como completa nomeando só a primeira:

1. `unique=True` em campo → `<tabela>_<coluna>_key` no PostgreSQL.
2. A chave primária → `_pkey`, deliberadamente fora: nenhuma requisição de
   cliente escolhe o `id`.
3. `Meta.unique_together` → nome gerado pelo **próprio Django** (sufixo
   `_uniq`, com hash de tabela e colunas). O auditor mediu: acrescentar
   `unique_together` a `Conta.Meta` passava com **47 passed**, invisível às
   duas metades da varredura. Gravidade baixa (Django e DRF validam
   `unique_together` na camada de formulário e serializer, e
   `makemigrations --check` acusaria a mudança de modelo) — o que a tornou um
   achado foi a fronteira declarada como completa sem o ser.

A fronteira não fica implícita:
`test_o_conjunto_de_indices_unicos_implicitos_e_conhecido` prende a lista
atual — nas três formas —, então um `unique=True` ou um `unique_together`
NOVO reprova a suíte e força a decisão em vez de escapar, que é a mesma
armadilha da "décima quinta `APIView`" da BL-134. E
`test_cada_indice_unico_implicito_aparece_em_um_dos_tres_registros` (BL-220)
exige que cada um deles tenha razão escrita, com o mesmo piso de 40
caracteres que as restrições de `Meta` já tinham: uma restrição de banco não
pode ficar sem razão conferível por causa da FORMA como foi declarada.
"""

import importlib

import pytest
from django.apps import apps as registro_de_apps
from django.db import connection, models

from apps.core.restricoes import (
    MENSAGENS_DE_RESTRICAO,
    RESTRICOES_SEM_CAMINHO_DE_CLIENTE,
    RESTRICOES_TRADUZIDAS_FORA_DO_MAPA,
)

# As 10 restrições de `Meta.constraints` conferidas uma a uma no
# inventário de 2026-09-15 (DL-019) e expandido em 2026-09-18
# (DL-016 rodada 1, auditoria). Controle NOMINAL, no molde de
# `test_permission_classes_explicito.test_varredura_inclui_as_14_
# apiviews_conferidas_pelo_auditor`: se uma sumir (renomeada, movida,
# removida), o teste falha apontando QUAL, em vez de o total só cair em
# silêncio. As três entradas de `Competencia` foram acrescentadas na
# auditoria rodada 1 da DL-016 (2026-09-18) para refletir o estado real
# pós-PR #31 — sem isso, a fotografia nominal ficava desatualizada, e a
# próxima auditoria perguntaria "por que essas três não estão na lista?".
RESTRICOES_CONFERIDAS = {
    "codigo_unico_por_empresa": "contabilidade.Conta",
    "estorno_de_unico": "contabilidade.LancamentoContabil",
    "chave_idempotencia_unica_por_empresa": "contabilidade.LancamentoContabil",
    "empresa_cnpj_canonico": "empresas.Empresa",
    "uma_matriz_por_empresa": "empresas.Estabelecimento",
    "estabelecimento_cnpj_canonico": "empresas.Estabelecimento",
    "unico_vinculo_usuario_escritorio": "tenancy.VinculoUsuarioEscritorio",
    # DL-016 (PR #31, F1): as três invariantes do modelo `Competencia`.
    # Conferidas na auditoria rodada 1 de 2026-09-18
    # (docs/auditorias/2026-09-18-dl-016-rodada-1.md).
    "competencia_unica_por_empresa_ano_mes": "contabilidade.Competencia",
    "competencia_mes_entre_1_e_12": "contabilidade.Competencia",
    "competencia_ano_entre_1970_e_2999": "contabilidade.Competencia",
}

# Índices únicos implícitos (`unique=True` em campo) existentes hoje, com o
# nome que o PostgreSQL dá a cada um. Ver o docstring do módulo: eles estão
# FORA da varredura principal, e esta lista é o que impede que "estar fora"
# se transforme em "passar sem ninguém ver".
INDICES_UNICOS_IMPLICITOS_CONHECIDOS = {
    "accounts_usuario_username_key",
    "accounts_usuario_email_key",
    "tenancy_escritorio_cnpj_key",
    "tenancy_conviteescritorio_token_key",  # DL-018 — token de convite
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
    próprio teste, sem tocar em nenhum modelo real (modelo da BL-197: a
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


def _nome_do_indice_de_unique_together(modelo, campos):
    """Nome do índice único que o Django dá a um `Meta.unique_together`.

    BL-219. Derivado pelo **próprio** gerador do Django (`_create_index_name`,
    do editor de esquema), e não por uma segunda cópia da regra de nomes: o
    nome carrega um hash de tabela e colunas e um truncamento que dependem do
    banco, e reimplementá-los aqui divergiria na primeira mudança — a
    DE-026 aplicada a nome de índice. Se o Django renomear esse gerador, esta
    função levanta `AttributeError` e a suíte reprova alto, que é o
    comportamento certo: o contrário seria a varredura voltar a não enxergar
    a terceira forma, em silêncio.
    """
    colunas = [modelo._meta.get_field(nome).column for nome in campos]
    return connection.schema_editor()._create_index_name(
        modelo._meta.db_table, colunas, suffix="_uniq"
    )


def _indices_unicos_implicitos(modelos):
    """Nome do índice único que cada restrição de unicidade NÃO declarada em
    `Meta.constraints` cria no banco.

    Duas origens, e a segunda entrou com a BL-219:

    - `unique=True` em campo. O padrão do PostgreSQL para a restrição de
      unicidade de coluna é `<tabela>_<coluna>_key` (é dele que vem
      `empresas_empresa_cnpj_key`, o nome que `apps.empresas.services.
      mensagem_se_cnpj_duplicado` já reconhece hoje). Chaves primárias ficam
      fora: são `_pkey`, e nenhuma requisição de cliente escolhe o `id`.
    - `Meta.unique_together`. Cria restrição única no banco, não está em
      `Meta.constraints` e não é campo `unique=True` — as duas metades da
      varredura passavam por cima dela sem ver nada (achado A6, medido).

    Recebe os modelos como PARÂMETRO pelo mesmo motivo de
    `constraints_declaradas`: para o mutante da BL-219 poder ser reconstruído
    dentro do próprio teste, sem tocar em modelo real.
    """
    nomes = set()
    for modelo in modelos:
        for campo in modelo._meta.local_fields:
            if getattr(campo, "unique", False) and not campo.primary_key:
                nomes.add(f"{modelo._meta.db_table}_{campo.column}_key")
        for campos in getattr(modelo._meta, "unique_together", ()) or ():
            nomes.add(_nome_do_indice_de_unique_together(modelo, campos))
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
    """BL-204/BL-214. É este teste que o comentário de `apps/core/restricoes.
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
    fonte_real` (BL-197), a única defesa da DL-020 que já estava demonstrada
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
    """A entrada tem de corresponder a uma restrição REAL — de `Meta` ou
    índice único implícito (BL-220, mesma união que
    `test_cada_restricao_traduzida_fora_do_mapa_e_de_meta_ou_indice_implicito`
    já usava). Uma entrada que não corresponda a nada seria dispensa
    permanente de um nome que ninguém reconhece.
    """
    modelos = _modelos_do_repositorio()
    reais = set(constraints_declaradas(modelos)) | _indices_unicos_implicitos(modelos)
    assert nome in reais, sorted(reais)
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
    não existia (BL-214).
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


@pytest.mark.parametrize("nome", sorted(INDICES_UNICOS_IMPLICITOS_CONHECIDOS))
def test_cada_indice_unico_implicito_aparece_em_um_dos_tres_registros(nome):
    """BL-220 (achado A7). Estar FORA da varredura principal não pode
    significar estar fora de toda pergunta.

    A assimetria que este teste desfaz: `RESTRICOES_SEM_CAMINHO_DE_CLIENTE`
    exigia razão escrita de 40 caracteres, verificada por teste, para uma
    restrição de `Meta` sem caminho de cliente — e um índice único implícito
    na MESMA situação não exigia nada. Três nomes
    (`tenancy_escritorio_cnpj_key`, `accounts_usuario_username_key`,
    `accounts_usuario_email_key`) estavam presos na lista acima sem aparecer
    em registro nenhum e sem razão escrita em lugar nenhum. Violar um deles
    produz `IntegrityError` igual ao de uma `UniqueConstraint` de `Meta`; a
    forma como a restrição foi declarada não muda isso.

    Não é explorável hoje — não há caminho de escrita de cliente para
    `Escritorio` nem para `Usuario` —, e é precisamente por isso que o
    registro precisa existir ANTES: a DL-018, primeiro acesso, é a etapa que
    abre esse caminho.
    """
    assert nome in _nomes_registrados(), (
        f"O índice único implícito {nome} não aparece em nenhum dos três "
        "registros de apps/core/restricoes.py. Escolha UM: "
        "MENSAGENS_DE_RESTRICAO (a API traduz para 400), "
        "RESTRICOES_TRADUZIDAS_FORA_DO_MAPA (outro ponto traduz — aponte qual) "
        "ou RESTRICOES_SEM_CAMINHO_DE_CLIENTE (nenhuma requisição de cliente a "
        "alcança — escreva por quê, com o mesmo piso das restrições de Meta)."
    )


def test_a_varredura_enxerga_restricao_unica_declarada_por_unique_together():
    """BL-219 (achado A6), reconstruído dentro do próprio teste.

    O mutante do auditor foi acrescentar `unique_together = [["empresa",
    "nome"]]` ao `Meta` de `Conta`: as duas varreduras deram **47 passed** e
    nem a principal nem o teste que prende a lista de índices implícitos
    enxergaram a restrição nova. Aqui o modelo é fabricado — mesmo molde do
    `_MetaFalso` acima (BL-197) — para a prova não depender de ninguém ter
    editado um modelo real e registrado que viu a suíte falhar.
    """

    class _CampoFalso:
        def __init__(self, coluna):
            self.column = coluna
            self.unique = False
            self.primary_key = False

    class _MetaComUniqueTogether:
        db_table = "app_ficticio_conta"
        constraints = ()
        unique_together = (("empresa", "nome"),)
        local_fields = ()

        def get_field(self, nome):
            return _CampoFalso(f"{nome}_id" if nome == "empresa" else nome)

    class ModeloComUniqueTogether:
        _meta = _MetaComUniqueTogether()

    encontrados = _indices_unicos_implicitos([ModeloComUniqueTogether])

    # Um nome só, gerado pelo Django, com a tabela e as colunas dentro dele —
    # e é ele que aparece no `IntegrityError` quando a restrição é violada.
    assert len(encontrados) == 1, encontrados
    nome = next(iter(encontrados))
    assert nome.startswith("app_ficticio_conta_empresa_id_nome_")
    assert nome.endswith("_uniq")

    # E a consequência que fecha o achado: um `unique_together` novo num
    # modelo real faria a lista prendida divergir, e
    # `test_o_conjunto_de_indices_unicos_implicitos_e_conhecido` reprova.
    assert nome not in INDICES_UNICOS_IMPLICITOS_CONHECIDOS
