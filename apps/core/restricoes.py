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
# negócio (BL-204, achado R6-10 da auditoria DL-017 rodada 6).
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
# A frase acima já esteve aqui afirmando um arquivo que NÃO existia (BL-214,
# achado do inventário de 2026-09-15): o comentário descrevia o mecanismo,
# explicava por que ele era necessário, e o mecanismo não estava lá. O
# arquivo existe desde a segunda rodada da DL-020, e a varredura foi vista
# reprovar com uma `CheckConstraint` nova e sem tradução acrescentada a um
# modelo real — `test_a_varredura_reprova_constraint_nova_sem_traducao`
# reconstrói esse mutante dentro do próprio teste, para a demonstração não
# depender de ninguém ter registrado que a viu falhar.
MENSAGENS_DE_RESTRICAO = {
    "codigo_unico_por_empresa": "Já existe uma conta com este código nesta empresa.",
    "uma_matriz_por_empresa": "Esta empresa já tem uma matriz cadastrada.",
    # As duas de canonização de CNPJ (BL-204). Inalcançáveis pelo caminho
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
    # DL-038 (R1/R2): as duas constraints novas de `Empresa` — formato do
    # CPF e consistência entre tipo_inscricao/cnpj/cpf. Mesma classe de
    # armadilha das duas de cima: inalcançáveis pelo caminho normal (o
    # serializer valida antes), mas `bulk_create`/`QuerySet.update()`
    # vazam `IntegrityError` cru, e `apps/empresas/views.py` já as passa
    # para `restricao_como_400` via `mensagens_de(...)` em
    # `perform_create`/`perform_update`.
    "empresa_cpf_formato_valido": (
        "O CPF da empresa precisa ter 11 dígitos numéricos, sem máscara."
    ),
    "empresa_inscricao_consistente_com_tipo": (
        "O tipo de inscrição da empresa precisa bater com o campo preenchido: "
        "CNPJ preenchido e CPF vazio para tipo CNPJ; CPF preenchido e CNPJ vazio "
        "para tipo CPF."
    ),
}

# Restrições cuja tradução NÃO passa por `restricao_como_400`, com o ponto
# exato que as traduz. Existir aqui não é dispensa: é declaração verificável
# de onde a tradução mora, e a varredura confere que o objeto apontado existe
# e é chamável (um caminho que alguém renomeie ou apague reprova a suíte).
#
# Nenhuma delas pode ser movida para o mapa acima sem revisar o ponto citado:
# elas traduzem para exceções de negócio DIFERENTES, com semântica de HTTP
# diferente (409 de conflito de idempotência não é 400 de entrada inválida).
RESTRICOES_TRADUZIDAS_FORA_DO_MAPA = {
    # DL-038: `empresas_empresa_cnpj_key` (índice implícito de `unique=True`
    # de campo) foi SUBSTITUÍDO por `empresa_cnpj_unico` — uma
    # `UniqueConstraint` condicional, porque a unicidade do CNPJ de
    # `Empresa` deixou de poder ser incondicional (empresa CPF tem
    # `cnpj == ""`, e dois vazios nunca podem colidir). Mesmo ponto de
    # tradução de sempre. `empresa_cpf_unico` é a entrada NOVA, simétrica.
    "empresa_cnpj_unico": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "empresa_cpf_unico": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "empresas_estabelecimento_cnpj_key": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "estorno_de_unico": "apps.contabilidade.services.estornar_lancamento",
    "chave_idempotencia_unica_por_empresa": "apps.contabilidade.services.criar_lancamento",
    # DL-018 — token do convite é gerado com `get_random_string(32)` (~190
    # bits de entropia). A colisão é praticamente impossível, mas não
    # impossível; o `save()` do modelo tem um loop defensivo e o
    # `IntegrityError` daí é convertido para `ConviteTokenColidiu`
    # pelo service `emitir_convite_para_escritorio` — que a view
    # `emitir_convite` traduz para 503 (não 409, porque retry com novo
    # token é o caminho correto). O caminho de escrita por cliente é o
    # POST /convites/emitir/, exclusivo para ADMINISTRADOR do escritório.
    "tenancy_conviteescritorio_token_key": (
        "apps.tenancy.services.primeiro_acesso.emitir_convite_para_escritorio"
    ),
    # DL-023 (BL-211/A2): a restrição que garante UM período de regime
    # tributário aberto por empresa. A tradução mora dentro de
    # `registrar_regime_tributario`, e não em `restricao_como_400`, porque a
    # checagem de negócio acontece ANTES: o serviço fecha o período vigente
    # anterior e só chega a violar a restrição na corrida residual — duas
    # requisições simultâneas quando ainda não existe linha alguma para o
    # `select_for_update()` travar. Nesse caminho o serviço converte o
    # `IntegrityError` em `ValueError`, que a view devolve como 400.
    #
    # ⚠️ CORREÇÃO DE UMA AFIRMAÇÃO FALSA QUE ESTAVA AQUI (achado P2 da rodada 1
    # da auditoria DL-023, BL-246). Este comentário dizia que "a classe da
    # BL-144 vale TAMBÉM para a perdedora da corrida". O auditor mediu:
    # **não valia**. Esta restrição tem DOIS caminhos de escrita capazes de
    # violá-la — `registrar_regime_tributario` (traduzido) e
    # `excluir_ultimo_regime_tributario`, que reabre o período anterior e
    # colide com a linha criada por um POST concorrente. O segundo devolvia
    # **500**, reproduzido em 6 execuções de 8. A correção está na BL-246.
    #
    # E a lição de mecanismo, registrada como BL-256: este registro é
    # `nome -> UM ponteiro`, então a varredura confere que o ponteiro existe e
    # é chamável, mas nunca pergunta QUANTOS caminhos de escrita alcançam a
    # restrição e se todos traduzem. Foi por essa fenda que o 500 passou
    # verde. Enquanto a estrutura for de ponteiro único, o que está escrito
    # aqui é "onde a tradução mora", nunca "a cobertura está completa".
    "um_periodo_de_regime_aberto_por_empresa": (
        "apps.empresas.services.registrar_regime_tributario"
    ),
    # DL-010 F1 (DE-074 item 5, critério 28 do plano): as duas restrições
    # de deduplicação por escritório da recepção de NFS-e. Não traduzem
    # para 400 — a repetição de um documento/evento já recebido NÃO é erro
    # de entrada, é o caso NORMAL de reimportar um lote (RC-69). A
    # tradução vira um resultado de NEGÓCIO ("duplicado" em
    # `ResultadoDoArquivo`), dentro do savepoint por arquivo de
    # `_processar_um_arquivo` — nunca sobe como exceção HTTP.
    "documento_fiscal_unico_por_escritorio": "apps.fiscal.services._processar_um_arquivo",
    "evento_fiscal_unico_por_escritorio": "apps.fiscal.services._processar_um_arquivo",
}

# Terceira categoria, e ela é declaração de LIMITE, não de cobertura:
# restrições que nenhuma requisição de cliente alcança hoje, com o motivo
# escrito. A varredura aceita, mas exige que estejam aqui NOMEADAS — o que
# ela proíbe é o silêncio, não a ausência de tradução.
#
# Quando uma delas ganhar caminho de escrita por cliente (API, tela ou
# importação), ela sai daqui e entra num dos dois de cima. O item de backlog
# que cobre a varredura do admin contra as regras de negócio é a BL-211.
#
# BL-220 (achado A7 da auditoria DL-020 rodada 1): os índices únicos
# IMPLÍCITOS entram aqui pela mesma porta. A assimetria que o achado nomeia
# era real — uma restrição de `Meta` sem caminho de cliente exigia razão de 40
# caracteres verificada por teste, e uma restrição de banco idêntica, só que
# criada por `unique=True` em campo, não exigia nada. Três nomes estavam
# presos em `INDICES_UNICOS_IMPLICITOS_CONHECIDOS` sem aparecer em registro
# nenhum. A forma como a restrição foi DECLARADA não muda o que acontece
# quando ela é violada.
RESTRICOES_SEM_CAMINHO_DE_CLIENTE = {
    "unico_vinculo_usuario_escritorio": (
        "Vínculo usuário-escritório só é criado pelo admin do Django "
        "(apps/tenancy/admin.py) e por código de teste; não há rota de API nem "
        "tela do produto que o grave. No admin, o `ModelForm` chama "
        "`full_clean()`, cujo `validate_unique()` converte a violação em erro "
        "de formulário ANTES do INSERT — então ela não chega ao cliente como "
        "5xx por esse caminho."
    ),
    # Os três índices únicos implícitos que a BL-220 encontrou sem registro.
    # A verificação de que HOJE não existe caminho de escrita de cliente para
    # `Escritorio` nem para `Usuario` é do auditor da rodada 1, e é o que
    # sustenta a classificação — não uma presunção.
    "tenancy_escritorio_cnpj_key": (
        "Índice único implícito de `Escritorio.cnpj` (`unique=True`). "
        "Escritório só é criado pelo admin do Django (apps/tenancy/admin.py) e "
        "por código de teste: não existe rota de API nem tela do produto que o "
        "grave — as duas rotas de `apps.tenancy.views` apenas LEEM o vínculo do "
        "usuário e trocam o escritório ativo da sessão. No admin, o `ModelForm` "
        "converte a violação em erro de formulário antes do INSERT. "
        "ATENÇÃO: a DL-018 (primeiro acesso) é a etapa que abre esse caminho — "
        "quando abrir, esta entrada sai daqui e vira tradução para 400, como as "
        "duas `*_cnpj_key` de empresas já são."
    ),
    "accounts_usuario_username_key": (
        "Índice único implícito de `Usuario.username` (`unique=True`, herdado de "
        "`AbstractUser`). Usuário só nasce pelo admin do Django, por "
        "`createsuperuser` e por código de teste: `apps/accounts` não tem "
        "`views.py` e nenhuma rota do projeto cria usuário. "
        "ATENÇÃO: a DL-018 (primeiro acesso) é a etapa que abre esse caminho, e "
        "cadastro público com nome de usuário repetido é exatamente o 500 que "
        "esta entrada existe para antecipar."
    ),
    "accounts_usuario_email_key": (
        "Índice único implícito de `Usuario.email` (`unique=True`). Mesma "
        "situação de `accounts_usuario_username_key`, e com o mesmo prazo: não "
        "há caminho de escrita de cliente hoje, e a DL-018 o abre. O e-mail "
        "duplicado é o caso mais provável dos dois na prática, porque o usuário "
        "escolhe o nome mas não escolhe ter só um e-mail."
    ),
    # DL-016 / F1 — três restrições do modelo `Competencia`. Nenhuma rota de
    # cliente cria `Competencia` diretamente: a única gravação por caminho do
    # produto é o `Competencia.objects.get_or_create(...)` dentro de
    # `apps.contabilidade.services.criar_lancamento` (F2), que tem savepoint
    # próprio e trata `IntegrityError` como CORRIDA INTERNA (reconsulta via
    # `get()` e segue) — não traduz para 400, é consistência transacional do
    # service. O importador em massa da DL-010 pode vir a chamar `bulk_create`
    # direto sobre `Competencia` e expor estas restrições ao cliente; quando
    # isso acontecer, saem daqui e viram tradução para 400, como as duas de
    # canonização de CNPJ já viraram (mesmo desenho, mesma lição).
    "competencia_ano_entre_1970_e_2999": (
        "`CheckConstraint` do modelo `Competencia` (DL-016 / F1): garante "
        "1970 <= ano <= 2999. Hoje `criar_lancamento` só cria competências a "
        "partir de `data.year`/`data.month` de um lançamento, que são sempre "
        "válidos por construção; nenhum caminho de cliente alcança esta "
        "restrição com valor inválido. Ver nota do bloco sobre DL-010."
    ),
    "competencia_mes_entre_1_e_12": (
        "`CheckConstraint` do modelo `Competencia` (DL-016 / F1): garante "
        "1 <= mes <= 12. Mesma situação de `competencia_ano_entre_1970_e_2999`: "
        "hoje inalcançável por caminho de cliente, e o importador em massa da "
        "DL-010 é o gatilho natural para revisão."
    ),
    "competencia_unica_por_empresa_ano_mes": (
        "`UniqueConstraint(empresa, ano, mes)` do modelo `Competencia` "
        "(DL-016 / F1). O único caminho de escrita hoje é o "
        "`get_or_create(...)` dentro de `criar_lancamento` "
        "(`apps/contabilidade/services.py:387-411`), que captura "
        "`IntegrityError` em savepoint próprio, reconsulta via `get()` e "
        "segue — a violação é tratada como CORRIDA entre requisições "
        "concorrentes, não como erro de negócio. Quando a DL-010 abrir "
        "importação em lote, esta entrada precisa ser revisada."
    ),
    # BL-455 (achado A5 da rodada 2 de auditoria da fatia 1 da DL-016):
    # `ck_lancamentocontabil_empresa_not_null` foi adicionada ao BANCO pela
    # migração 0005 de `contabilidade` (`AddConstraint` avulso, hand-written)
    # mas nunca tinha sido declarada em `LancamentoContabil.Meta.
    # constraints` — a divergência já reprovava `manage.py makemigrations
    # --check` em HEAD limpo, e a auditoria MEDIU o tamanho do risco: quem
    # aplicasse o `RemoveConstraint` que o Django propunha derrubava a rede
    # de segurança da DL-016 F6 (`apps/contabilidade/tests/test_dl016_f6_
    # check_empresa_not_null.py` reprova 2 de 4 testes sem ela). Declarada
    # agora em `Meta.constraints`; entra aqui porque `empresa` já é uma
    # `ForeignKey` OBRIGATÓRIA (sem `null=True`) — nenhum `ModelForm`,
    # serializer ou service deste projeto grava `LancamentoContabil` sem
    # `empresa`, a ausência já é recusada ANTES do INSERT pela validação de
    # campo obrigatório do Django. Esta `CheckConstraint` é defesa em
    # profundidade contra INSERT direto via psql/shell-admin que contorne o
    # ORM inteiro — nenhuma rota de cliente (API, tela ou importação) pode
    # alcançá-la.
    "ck_lancamentocontabil_empresa_not_null": (
        "`CheckConstraint(empresa_id IS NOT NULL)` do modelo "
        "`LancamentoContabil` (DL-016 F6/DE-051). `empresa` já é uma "
        "`ForeignKey` obrigatória — nenhum caminho de cliente grava "
        "`LancamentoContabil` sem `empresa`. Defesa em profundidade contra "
        "INSERT direto via psql/shell-admin, sem caminho de escrita por "
        "cliente."
    ),
    # DL-010 F1: `apps.fiscal.services._vincular_participantes` nunca monta
    # dois vínculos para a MESMA empresa no mesmo documento (o ramo do
    # tomador é descartado quando `empresa_tomador == empresa_prestador`) —
    # e a criação do documento, que aconteceria ANTES na mesma
    # `transaction.atomic()`, já teria levantado `documento_fiscal_unico_
    # por_escritorio` primeiro num reenvio. Nenhum caminho de cliente
    # alcança esta restrição hoje.
    "vinculo_documento_empresa_unico": (
        "`UniqueConstraint(documento, empresa)` de `VinculoDocumentoEmpresa` "
        "(DL-010 F1). `_vincular_participantes` nunca gera dois vínculos "
        "para a mesma empresa no mesmo documento, e um documento duplicado "
        "já é barrado antes disso por `documento_fiscal_unico_por_"
        "escritorio`. Sem caminho de escrita por cliente hoje."
    ),
    # Achado B8 da auditoria rodada 1 (DL-038): CheckConstraint de DOMÍNIO
    # nova (`modo_escrituracao` só {"contabilidade", "livro_caixa"}).
    "empresa_modo_escrituracao_valido": (
        "`CheckConstraint` de domínio de `Empresa.modo_escrituracao` "
        "(DL-038). Os DOIS caminhos de cliente que gravam este campo "
        "restringem o valor ANTES do INSERT: a API usa `serializers."
        "ChoiceField(choices=ModoEscrituracao.choices)` (EmpresaSerializer, "
        "apps/empresas/serializers.py) — valor fora do domínio nunca passa "
        "de `to_internal_value`, 400 antes de qualquer escrita; o admin do "
        "Django usa o `<select>` gerado pelo `ChoiceField` do próprio "
        "campo do modelo — não existe como submeter um valor fora da "
        "lista pelo formulário (um POST forjado direto, fora do "
        "navegador, cairia na constraint do banco como IntegrityError cru "
        "— não há relato nem teste desse caminho hoje). Sem caminho de "
        "escrita por cliente REALISTA para o valor inválido."
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
    (BL-204): uma view que trate DUAS constraints no mesmo `with` precisa
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
