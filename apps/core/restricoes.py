"""Módulo compartilhado para traduzir violação de restrição de banco
declarada em `Meta.constraints` (`UniqueConstraint`/`CheckConstraint`) em
mensagem de negócio — 400, nunca 500 (BL-144, achado R5-5 da auditoria
DL-017 rodada 5).

O padrão já existia, uma vez, em `apps.empresas.services.
erro_de_cnpj_duplicado_como_400` — só para a unicidade de CNPJ. A DE-034
manda varrer TODA `Meta.constraints` do repositório com a mesma pergunta:
"existe caminho de API que converte esta violação em 400?" — e a resposta
era não para `Conta.codigo_unico_por_empresa` (contabilidade) e
`Estabelecimento.uma_matriz_por_empresa` (empresas), mesmo esta última
vivendo na MESMA função que já trata a unicidade do CNPJ:
`EstabelecimentoListCreateView.perform_create` já abre `with
transaction.atomic(), erro_de_cnpj_duplicado_como_400():` — a defesa
existe, e não cobre a constraint declarada quatro linhas abaixo no mesmo
`Meta`.

**Por que um módulo novo, e não generalizar `erro_de_cnpj_duplicado_
como_400`:** aquela função tem histórico próprio (achados A1/B1/R4 de
três rodadas anteriores), testes que dependem do formato exato de
`CNPJDuplicado` (`ValidationError` com `message_dict["cnpj"]`), e é
consumida por `criar_empresa` (view HTML, fora do escopo desta correção).
Reescrevê-la para generalizar arriscava esses três consumidores por um
ganho marginal. Este módulo cobre as constraints NOVAS com o mesmo
princípio (traduzir pelo nome da constraint, nunca por heurística de
mensagem), sem tocar no que já funciona.

Uso:

    try:
        with transaction.atomic(), restricao_como_400(
            {"codigo_unico_por_empresa": "Já existe uma conta com este código nesta empresa."}
        ):
            conta = serializer.save(empresa=empresa)
    except RestricaoViolada as exc:
        raise DRFValidationError(str(exc)) from exc

`transaction.atomic()` fica por fora, a cargo de quem chama — é o
savepoint que isola o `IntegrityError` para a conexão continuar utilizável
depois (mesmo desenho de `erro_de_cnpj_duplicado_como_400`).
"""

from contextlib import contextmanager

from django.db import IntegrityError

# ---------------------------------------------------------------------------
# Registro ÚNICO das restrições de banco e de como cada uma vira erro de
# negócio (BL-157, achado R6-10 da auditoria DL-017 rodada 6).
#
# Por que um registro, e não a conferência manual que havia: o critério da
# BL-144 dizia "para cada `Meta.constraints` existe caminho de API que a
# converte em 400", a varredura foi FEITA, e ainda assim **duas** constraints
# ficaram de fora — as duas `CheckConstraint` de canonização de CNPJ
# (`empresa_cnpj_canonico`, `estabelecimento_cnpj_canonico`), que são a outra
# metade do MESMO `Meta` que a BL-144 fechou (item 3 da DE-034). Conferência
# manual não reprova build; registro + varredura de repositório reprova.
#
# `apps/core/tests/test_dl019_varredura_de_restricoes.py` percorre TODOS os
# modelos dos apps do projeto e exige que cada constraint declarada em `Meta`
# apareça em UM dos TRÊS registros deste módulo (este mapa, o de traduções
# fora do mapa e o de restrições sem caminho de cliente). Uma constraint nova
# sem tradução reprova a suíte — que é a única forma de isto não se repetir.
#
# A frase acima já esteve aqui afirmando um arquivo que NÃO existia (BL-167,
# achado do inventário de 2026-09-15): o comentário descrevia o mecanismo,
# explicava por que ele era necessário, e o mecanismo não estava lá. O
# arquivo existe desde a segunda rodada da DL-019, e a varredura foi vista
# reprovar com uma `CheckConstraint` nova e sem tradução acrescentada a um
# modelo real — `test_a_varredura_reprova_constraint_nova_sem_traducao`
# reconstrói esse mutante dentro do próprio teste, para a demonstração não
# depender de ninguém ter registrado que a viu falhar.
MENSAGENS_DE_RESTRICAO = {
    "codigo_unico_por_empresa": "Já existe uma conta com este código nesta empresa.",
    "uma_matriz_por_empresa": "Esta empresa já tem uma matriz cadastrada.",
    # As duas de canonização de CNPJ (BL-157). Inalcançáveis pelo caminho
    # normal da API — `Empresa.save()`/`Estabelecimento.save()` canonizam
    # ANTES do INSERT —, mas `apps/empresas/tests/test_canonizacao_constraint.
    # py` já prova que `bulk_create`/`bulk_update`/`QuerySet.update()` vazam
    # `IntegrityError` cru, e o comentário do próprio modelo aponta a DL-010
    # (importação em lote) como "candidata natural a usar bulk_create por
    # desempenho". A armadilha estava ARMADA para a próxima etapa; mapeá-las
    # aqui é o que a desarma antes de a importação existir.
    "empresa_cnpj_canonico": (
        "O CNPJ da empresa precisa ser gravado em formato canônico: só letras "
        "maiúsculas e dígitos, sem máscara."
    ),
    "estabelecimento_cnpj_canonico": (
        "O CNPJ do estabelecimento precisa ser gravado em formato canônico: só "
        "letras maiúsculas e dígitos, sem máscara."
    ),
}

# Restrições cuja tradução NÃO passa por `restricao_como_400`, com o ponto
# exato que as traduz. Existir aqui não é dispensa: é declaração verificável
# de onde a tradução mora, e a varredura confere que o objeto apontado existe
# e é chamável (um caminho que alguém renomeie ou apague reprova a suíte).
#
# Nenhuma delas pode ser movida para o mapa acima sem revisar o ponto citado:
# as três traduzem para exceções de negócio DIFERENTES, com semântica de HTTP
# diferente (409 de conflito de idempotência não é 400 de entrada inválida).
RESTRICOES_TRADUZIDAS_FORA_DO_MAPA = {
    "empresas_empresa_cnpj_key": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "empresas_estabelecimento_cnpj_key": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "estorno_de_unico": "apps.contabilidade.services.estornar_lancamento",
    "chave_idempotencia_unica_por_empresa": "apps.contabilidade.services.criar_lancamento",
}

# Terceira categoria, e ela é declaração de LIMITE, não de cobertura:
# restrições que nenhuma requisição de cliente alcança hoje, com o motivo
# escrito. A varredura aceita, mas exige que estejam aqui NOMEADAS — o que
# ela proíbe é o silêncio, não a ausência de tradução.
#
# Quando uma delas ganhar caminho de escrita por cliente (API, tela ou
# importação), ela sai daqui e entra num dos dois de cima. O item de backlog
# que cobre a varredura do admin contra as regras de negócio é a BL-164.
RESTRICOES_SEM_CAMINHO_DE_CLIENTE = {
    "unico_vinculo_usuario_escritorio": (
        "Vínculo usuário-escritório só é criado pelo admin do Django "
        "(apps/tenancy/admin.py) e por código de teste; não há rota de API nem "
        "tela do produto que o grave. No admin, o `ModelForm` chama "
        "`full_clean()`, cujo `validate_unique()` converte a violação em erro "
        "de formulário ANTES do INSERT — então ela não chega ao cliente como "
        "5xx por esse caminho."
    ),
}


def mensagens_de(*nomes):
    """Subconjunto de `MENSAGENS_DE_RESTRICAO` para passar a `restricao_como_400`.

    Recebe nomes de constraint e devolve `{nome: mensagem}`. Levanta `KeyError`
    para nome que não exista no registro — de propósito: um erro de digitação
    no nome da constraint produziria, em silêncio, um `with` que não traduz
    nada, e o 500 voltaria sem nenhum sinal. Falhar no import é melhor.

    Cada view pede só as constraints que a SUA gravação pode violar, porque o
    campo em que o erro é reportado (`{"codigo": [...]}`, `{"cnpj": [...]}`)
    depende da rota — passar o registro inteiro em toda view reportaria a
    constraint certa no campo errado.
    """
    return {nome: MENSAGENS_DE_RESTRICAO[nome] for nome in nomes}


class RestricaoViolada(Exception):
    """Levantada quando uma `IntegrityError` corresponde a uma das
    constraints mapeadas em `restricao_como_400`. A mensagem já é a
    mensagem de negócio pronta para o cliente (não o texto cru do banco).

    `nome` carrega o nome da constraint violada, separado da mensagem
    (BL-157): uma view que trate DUAS constraints no mesmo `with` precisa
    saber QUAL delas caiu para reportar o erro no campo certo — sem isso, a
    violação da canonização de CNPJ apareceria no campo `tipo` só porque a
    view já tratava `uma_matriz_por_empresa` ali. Comparar texto de mensagem
    para descobrir isso seria pior: a mensagem é conteúdo de produto e muda.
    """

    def __init__(self, mensagem, *, nome=None):
        self.nome = nome
        super().__init__(mensagem)


def _nome_da_constraint_violada(exc):
    """Extrai o nome da constraint de banco que causou `exc`, via o
    diagnóstico do driver (psycopg) — mesmo mecanismo de
    `apps.empresas.services.mensagem_se_cnpj_duplicado`. Devolve `None`
    quando não há diagnóstico (driver diferente, ou erro sem constraint
    nomeada) — quem chama trata isso como "não é uma das constraints
    mapeadas" e deixa o erro original subir.
    """
    diagnostico = getattr(exc.__cause__, "diag", None)
    return getattr(diagnostico, "constraint_name", None)


@contextmanager
def restricao_como_400(mapa_constraint_para_mensagem):
    """Traduz `IntegrityError` de uma constraint MAPEADA em `RestricaoViolada`.

    `mapa_constraint_para_mensagem` é um `dict` `{nome_da_constraint:
    mensagem_de_negocio}`. Só a(s) constraint(s) nomeadas no mapa são
    traduzidas; qualquer outra `IntegrityError` sobe SEM tradução — nunca
    converter toda `IntegrityError` em erro de cliente (a mesma instrução
    que rege `erro_de_cnpj_duplicado_como_400` e
    `criar_lancamento`/`estornar_lancamento`: um `IntegrityError` de
    origem desconhecida pode ser defeito de sistema, não erro do cliente,
    e mascará-lo como 400 esconde o defeito de quem monitora 500 — decisão
    revista depois de um erro parecido na DL-007).
    """
    try:
        yield
    except IntegrityError as exc:
        nome_constraint = _nome_da_constraint_violada(exc)
        mensagem = mapa_constraint_para_mensagem.get(nome_constraint)
        if mensagem is None:
            raise
        raise RestricaoViolada(mensagem, nome=nome_constraint) from exc
