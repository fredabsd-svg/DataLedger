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
    # DL-046 (RC-129): mesma classe de armadilha das duas de cima — o
    # serializer (`EmpresaSerializer.validate`) já recusa CAEPF fora do
    # formato ou fora de empresa CPF antes de qualquer INSERT/UPDATE, mas
    # `bulk_create`/`QuerySet.update()` vazariam `IntegrityError` cru sem
    # este mapeamento; `apps/empresas/views.py` já a passa para
    # `restricao_como_400` via `mensagens_de(...)`.
    "empresa_caepf_so_para_cpf_com_formato_valido": (
        "CAEPF só é aceito para empresa com tipo de inscrição CPF, e precisa "
        "ter 14 dígitos numéricos, sem máscara."
    ),
    # DL-046, fatia 3 (RC-127/HI-34): mesma classe de armadilha do CAEPF,
    # acima — `EmpresaSerializer.validate` já recusa código de ocupação
    # fora de empresa CPF ANTES de qualquer INSERT/UPDATE no caminho
    # SEQUENCIAL comum (e o campo do serializer, auto-gerado pelo
    # `ModelSerializer` a partir de `Empresa.codigo_ocupacao`, já herda
    # `validators=[validar_codigo_ocupacao]` do MODELO — confere formato e
    # tabela oficial antes de `validate` rodar).
    #
    # O FIO até as views está LIGADO desde 2026-09-27: esta chave entra em
    # `mensagens_de(...)` dos dois `perform_create`/`perform_update` de
    # `apps/empresas/views.py`, e `"codigo_ocupacao"` é a entrada dela em
    # `_CAMPO_DA_RESTRICAO_DE_EMPRESA` (sem ela, a corrida caía no
    # `.get(..., "cnpj")` e reportava o erro no campo errado — o mesmo
    # defeito do CAEPF, achado da rodada 1). A janela de corrida que esta
    # camada segura é a mesma já documentada para o CAEPF: PATCH que omite
    # `tipo_inscricao`, concorrente com uma troca de tipo. Prova do fio:
    # `apps/empresas/tests/test_dl046_fatia3_restricao_ocupacao_como_400.py`.
    "empresa_codigo_ocupacao_so_para_cpf_com_formato_valido": (
        "Código de ocupação só é aceito para empresa com tipo de inscrição "
        "CPF, e precisa ter 3 dígitos numéricos da tabela oficial do "
        "Carnê-Leão Web."
    ),
    # DL-046 (fatia 1) — mesmo desenho de "codigo_unico_por_empresa"
    # (contabilidade), agora para o plano de contas do livro-caixa.
    "conta_livro_caixa_codigo_unico_por_empresa": (
        "Já existe uma conta do livro-caixa com este código nesta empresa."
    ),
    # DL-046 (fatia 2): esta constraint agora tem `violation_error_message`
    # PRÓPRIA no modelo (B-4, ver `apps/livro_caixa/models.py`), que cobre o
    # caminho SEQUENCIAL (`full_clean()`/`validate_unique()`). Este registro
    # cobre só o caminho RESIDUAL de corrida (`IntegrityError`, dois `POST`
    # simultâneos para a MESMA competência) — mesmo padrão de
    # "codigo_unico_por_empresa", acima. Mesma mensagem, para não contar
    # duas histórias diferentes do mesmo motivo (DE-026).
    "dependentes_carne_leao_competencia_unica_por_empresa": (
        "Já existe uma quantidade de dependentes registrada para esta empresa a partir "
        "deste mês — use Retificar para corrigir o valor, em vez de um novo registro."
    ),
    # DL-074 (frente A): receita mensal, confirmação e opção pelo caixa. Os serviços
    # (apps.fiscal.receita) validam antes de gravar; a restrição é a última barreira.
    "receita_informada_mes_valido": (
        "Competência de receita informada fora de ano 1970-2999 ou mês fora de 1 a 12."
    ),
    "receita_informada_valor_positivo": (
        "Receita informada com valor não positivo. O serviço recusa antes; "
        "só SQL direto chega aqui."
    ),
    "receita_informada_catalogos_validos": (
        "Mercado, origem ou estado de receita informada fora do catálogo fechado (DL-074)."
    ),
    "receita_informada_campos_obrigatorios": (
        "Receita informada sem motivo ou sem documento de suporte. Ambos são obrigatórios."
    ),
    "receita_informada_campos_coerentes_com_o_estado": (
        "Colunas do ato (confirmação e estorno) fora de sincronia com o estado da "
        "receita informada."
    ),
    # DL-075 (HI-80): situação do ISS. O serviço recusa antes de gravar (mensagem nomeada);
    # estas restrições são a última barreira. A regra "interno exige situação" NÃO está
    # aqui: linhas anteriores à migração 0005 não a cumprem, e o pré-DAS a trata.
    "receita_informada_situacao_iss_valida": (
        "Situação do ISS da receita informada fora do catálogo (próprio município, outro "
        "município ou retido)."
    ),
    "receita_informada_iss_so_no_interno": (
        "Receita informada de exportação com situação do ISS: a exportação não tem essa "
        "situação. Deixe o campo em branco."
    ),
    "confirmacao_mes_valido": (
        "Confirmação de receita mensal com competência fora de 1970-2999 ou mês fora de 1 a 12."
    ),
    "confirmacao_estado_valido": (
        "Estado da confirmação de receita mensal fora de confirmada e reaberta."
    ),
    "confirmacao_valores_nao_negativos": (
        "Total confirmado de receita mensal negativo: receita não é negativa neste registro."
    ),
    "confirmacao_campos_coerentes_com_o_estado": (
        "Reabertura da confirmação sem motivo/autor, ou confirmada com marcas de reabertura."
    ),
    "opcao_caixa_so_ate_2026": (
        "Opção pelo regime de caixa fora de 2000-2026. A partir de 2027 a base é a "
        "competência (HI-66)."
    ),
}

# Achado D1 da auditoria da DL-039 rodada 1 (BL-533): os dois gatilhos de
# PostgreSQL da migração 0010/0011 (apps/empresas/migrations/
# 0011_bl533_bl534_gatilho_com_nome_e_trava.py) agora informam `CONSTRAINT`
# no `RAISE EXCEPTION`, então `IntegrityError` chega ao Django com
# `diag.constraint_name` preenchido — traduzível pelo MESMO
# `restricao_como_400` que já traduz `Meta.constraints`.
#
# Registro SEPARADO de `MENSAGENS_DE_RESTRICAO`, DE PROPÓSITO: aquele é
# varrido por `apps/core/tests/test_dl019_varredura_de_restricoes.py`
# contra `Meta.constraints` REAIS de modelo Django (`modelo._meta.
# constraints`) — um gatilho SQL não é metadado do ORM, não tem
# `Meta.constraints` nenhuma, e misturar os dois registros quebraria
# aquela varredura (`test_cada_nome_de_mensagens_de_restricao_e_uma_
# constraint_que_existe`) sem ganho nenhum: ela existe para pegar nome
# ERRADO/desatualizado num registro que promete corresponder ao ORM, e um
# gatilho nunca vai aparecer lá porque genuinamente não é uma
# `Meta.constraint`. As MESMAS mensagens (texto idêntico) das funções de
# serviço equivalentes — `apps.empresas.services.
# recusar_estabelecimento_para_empresa_cpf`/`recusar_transicao_para_cpf_
# com_estabelecimento` — para a API/admin nunca contarem duas histórias
# diferentes do mesmo motivo (DE-026), mesmo quando é o BANCO, não o
# Python, quem recusou (a janela de corrida entre a checagem em Python e
# o INSERT/UPDATE).
MENSAGENS_DE_RESTRICAO_DE_GATILHO = {
    # DL-077 (fatia 3, frente A), gatilhos da migração 0024 de `apps.contabilidade`: a importação
    # de lançamentos é área de conferência, e depois de efetivada ou descartada nenhuma linha muda.
    "importacao_lancamentos_sem_exclusao": (
        "Importação de lançamentos não pode ser excluída; descarte-a com motivo."
    ),
    "importacao_lancamentos_imutavel_depois_de_fechada": (
        "Importação já efetivada ou descartada não pode ser alterada."
    ),
    "lancamento_importado_sem_exclusao": (
        "Lançamento importado não pode ser excluído: ele faz parte da trilha da importação."
    ),
    "lancamento_importado_imutavel_depois_de_fechada": (
        "Lançamento de importação já efetivada ou descartada não pode ser alterado."
    ),
    "estabelecimento_empresa_nao_e_cpf": (
        "Não é possível cadastrar estabelecimento (matriz/filial) para uma "
        "empresa do tipo CPF: NIRE e estabelecimento são exclusivos de pessoa "
        "jurídica (CNPJ)."
    ),
    "empresa_transicao_cpf_com_estabelecimento": (
        "Não é possível mudar esta empresa para CPF: ela já tem estabelecimento "
        "(matriz/filial) gravado. Exclua os estabelecimentos antes de trocar o "
        "tipo de inscrição."
    ),
    # DL-043 (BL-474), camada 2 da não sobreposição de vigência de
    # `ParametroContabilEmpresa` (migração 0009 de `apps.contabilidade`,
    # mesmo padrão condicionado a `connection.vendor` das migrações
    # 0010–0013 de `apps.empresas`): gatilho, só PostgreSQL, que recusa
    # qualquer INSERT/UPDATE cujo intervalo de vigência se sobreponha ao de
    # outra linha da MESMA empresa — inclusive vigências já FECHADAS, que a
    # `UniqueConstraint` "um_periodo_de_parametro_contabil_aberto_por_
    # empresa" não alcança (ela só protege a vigência aberta). Traduzido
    # por `apps.contabilidade.services.registrar_parametro_contabil` via
    # `restricao_como_400`/`mensagens_de_gatilho`, para
    # `VigenciaParametroContabilConflitante` (409).
    "parametro_contabil_sem_sobreposicao": (
        "Esta vigência de parâmetro contábil sobrepõe outra já gravada para a mesma empresa."
    ),
    # DL-052 (A1), migração 0013 de `apps.contabilidade` — gatilhos só em
    # PostgreSQL que espelham no BANCO as regras de `criar_lancamento` e de
    # `save()`/`delete()` dos modelos. NENHUMA porta de escrita do produto as
    # alcança (os serviços validam antes, e nenhum caminho legítimo faz
    # UPDATE/DELETE em lançamento ou item); as mensagens existem para que, se
    # um dia uma alcançar, o erro seja legível e não um 500 cru.
    "lancamento_contabil_imutavel": (
        "Lançamento contábil efetivado não pode ser alterado nem excluído; registre um estorno."
    ),
    "item_lancamento_imutavel": (
        "Item de lançamento efetivado não pode ser alterado nem excluído; registre um estorno."
    ),
    "lancamento_debito_igual_a_credito": (
        "O total de débitos do lançamento deve ser igual ao total de créditos."
    ),
    "lancamento_com_debito_e_credito": (
        "O lançamento precisa ter ao menos um débito e um crédito de valor maior que zero."
    ),
    # DL-052 rodada 1 (D2), migração 0016: partida nova só entra em lançamento
    # criado na MESMA transação (marcador local à transação).
    "item_lancamento_em_lancamento_efetivado": (
        "Lançamento efetivado não recebe partida nova: registre um estorno."
    ),
    # DL-069 (fatia 1), migração 0011 de `apps.livro_caixa` — gatilhos só em
    # PostgreSQL que espelham no BANCO `LancamentoCaixa.save()/delete()` e o
    # fechamento de mês (reabrir não apaga a linha). NENHUMA porta de escrita do
    # produto as alcança (nenhum caminho legítimo faz UPDATE/DELETE no
    # lançamento; o fechamento só muda por encerrar e reabrir); as mensagens
    # existem para que, se uma alcançar, o erro seja legível e não um 500 cru.
    "lancamento_caixa_imutavel": (
        "Lançamento do livro-caixa não pode ser alterado nem excluído; registre um estorno."
    ),
    "fechamento_mes_caixa_imutavel": (
        "O fechamento de mês do livro-caixa não pode ser excluído e só muda por encerramento "
        "ou reabertura do mês, com o motivo registrado."
    ),
    # DL-069 (fatia 2), migrações 0023 de `contabilidade` e 0012 de
    # `livro_caixa` — gatilhos só em PostgreSQL que espelham no BANCO as
    # regras de período dos serviços: lançamento novo só em competência/mês
    # ABERTO (a competência achada pela DATA, nunca pela FK — a FK é anulável
    # em dado legado), e a entrega da competência ao cliente como fato datado
    # que não se desfaz (RC-19/RC-101). As mensagens REGISTRADAS abaixo contam
    # a mesma história dos serviços (`criar_lancamento`,
    # `_recusar_se_mes_caixa_encerrado`, `reabrir_competencia`) em forma
    # genérica — o registro é estático e não carrega mês, ano nem nome da
    # empresa. O texto exato de cada recusa está no `RAISE` da migração
    # correspondente, igual ao do serviço menos o nome da empresa (que o
    # gatilho não tem). O que importa para API/admin é não contarem duas
    # histórias diferentes do mesmo motivo (DE-026) — mesmo quando é o BANCO,
    # não o Python, quem recusou. NENHUMA porta de escrita do produto alcança essas
    # recusas hoje (os serviços recusam antes, com a mensagem da
    # competência/mês); as mensagens existem para que, se uma alcançar, o erro
    # seja legível e traduzível por `restricao_como_400`, e não um 500 cru.
    "dl069_lancamento_contabil_so_em_competencia_aberta": (
        "O lançamento cai em uma competência que não está aberta (encerrada ou já entregue ao "
        "cliente); não é possível gravá-lo. Reabra a competência, se ela ainda não foi "
        "entregue, ou lance o ajuste em uma competência aberta, com histórico apontando para a "
        "competência de origem."
    ),
    "dl069_lancamento_caixa_so_em_mes_aberto": (
        "O mês do lançamento no livro-caixa está encerrado, ou um mês seguinte do mesmo ano "
        "está encerrado e o carnê-leão dele depende deste mês; não é possível gravar o "
        "lançamento. Reabra o mês (informando o motivo), ou os meses encerrados seguintes do "
        "ano, ou lance em um mês aberto."
    ),
    "dl069_competencia_entregue_nao_volta_a_null": (
        "A competência já foi entregue ao cliente: a data da entrega é um fato datado e não "
        "volta a ficar em branco. Para registrar uma entrega posterior, marque a competência "
        "como entregue de novo."
    ),
    "dl069_competencia_entregue_nao_reabre": (
        "A competência já foi entregue ao cliente e não volta a aberta (RC-101); lance o "
        "ajuste em uma competência aberta, com histórico apontando para a competência de "
        "origem."
    ),
    # DL-072 (frente A), gatilhos de PostgreSQL da escrituração fiscal
    # (apps.fiscal, migração 0002). Só alcançáveis por SQL direto ou por
    # `QuerySet.update()` fora dos serviços — os serviços validam antes.
    "escrituracao_vinculo_prestador_da_empresa": (
        "A escrituração fiscal só pode apontar para um vínculo de PRESTADOR "
        "da MESMA empresa: nota tomada não se escritura, e a empresa da "
        "escrituração tem de ser a do vínculo."
    ),
    "escrituracao_imutavel_depois_de_efetivada": (
        "Escrituração fiscal efetivada não se altera nem se exclui. A única "
        "correção é o estorno, com motivo, que fica na trilha."
    ),
    # DL-074 (frente A), gatilhos da migração fiscal 0003 (receita informada e confirmação).
    "receita_informada_imutavel_depois_de_confirmada": (
        "Receita informada confirmada ou estornada não se altera nem se exclui. A única "
        "correção é o estorno, com motivo, que fica na trilha."
    ),
    "confirmacao_mes_imutavel_depois_de_confirmada": (
        "Confirmação de receita mensal não se altera diretamente. Para retificar o mês, "
        "reabra com motivo; o estorno de escrituração ou receita reabre o mês sozinho."
    ),
    # DL-075 (frente A), gatilho da migração fiscal 0004 (folha para o fator r).
    "folha_imutavel_depois_de_confirmada": (
        "Folha confirmada não se altera nem se exclui. A correção é o estorno, com motivo, "
        "e um novo lançamento do mês."
    ),
    # DL-078 (frente A), gatilhos da migração fiscal 0008 (escrituração de NFS-e tomada). Mesmo
    # desenho da escrituração prestada: só o banco recusa o que escapa de `QuerySet.update()`.
    "escrituracao_tomada_vinculo_tomador_da_empresa": (
        "A escrituração de tomada só pode apontar para um vínculo de TOMADOR da MESMA empresa: "
        "nota prestada não se escritura como tomada, e a empresa tem de ser a do vínculo."
    ),
    "escrituracao_tomada_efetivada_bate_com_o_documento": (
        "Escrituração de tomada efetivada com valor, competência ou retenção diferentes do "
        "documento de origem. Os valores são os do documento, copiados na efetivação."
    ),
    "escrituracao_tomada_imutavel_depois_de_efetivada": (
        "Escrituração de tomada efetivada não se altera nem se exclui, a não ser a data de "
        "pagamento informada. A correção do resto é o estorno, com motivo, que fica na trilha."
    ),
}


def mensagens_de_gatilho(*nomes):
    """Mesmo papel de `mensagens_de()`, para `MENSAGENS_DE_RESTRICAO_DE_
    GATILHO` — ver o comentário do registro acima sobre por que os dois
    ficam separados."""
    return {nome: MENSAGENS_DE_RESTRICAO_DE_GATILHO[nome] for nome in nomes}


# Restrições cuja tradução NÃO passa por `restricao_como_400`, com o ponto
# exato que as traduz. Existir aqui não é dispensa: é declaração verificável
# de onde a tradução mora, e a varredura confere que o objeto apontado existe
# e é chamável (um caminho que alguém renomeie ou apague reprova a suíte).
#
# Nenhuma delas pode ser movida para o mapa acima sem revisar o ponto citado:
# elas traduzem para exceções de negócio DIFERENTES, com semântica de HTTP
# diferente (409 de conflito de idempotência não é 400 de entrada inválida).
RESTRICOES_TRADUZIDAS_FORA_DO_MAPA = {
    # DL-077 (fatia 3, frente A): as unicidades da importação de lançamentos são checadas pelo
    # serviço antes de gravar (`receber` recusa o arquivo repetido com 409; o IntegrityError de
    # corrida é reconvertido ali) e o de-para é gravado por `definir_de_para` (update_or_create).
    "importacao_lancamentos_sha_unico_por_empresa": (
        "apps.contabilidade.intercambio.importacao_lancamentos.receber"
    ),
    "lancamento_importado_numero_unico_por_importacao": (
        "apps.contabilidade.intercambio.importacao_lancamentos.receber"
    ),
    "depara_conta_unica_por_empresa_formato_origem": (
        "apps.contabilidade.intercambio.importacao_lancamentos.definir_de_para"
    ),
    # DL-038: `empresas_empresa_cnpj_key` (índice implícito de `unique=True`
    # de campo) foi SUBSTITUÍDO por `empresa_cnpj_unico` — uma
    # `UniqueConstraint` condicional, porque a unicidade do CNPJ de
    # `Empresa` deixou de poder ser incondicional (empresa CPF tem
    # `cnpj == ""`, e dois vazios nunca podem colidir). Mesmo ponto de
    # tradução de sempre. `empresa_cpf_unico` foi a entrada nova, simétrica.
    #
    # DL-041 (RC-115/DE-077, decisão do Fred na PE-68): as TRÊS renomeadas
    # para "..._por_escritorio" — a unicidade deixou de ser GLOBAL (um
    # escritório não pode mais descobrir, pelo cadastro, que um CNPJ/CPF
    # já é cliente de outro). `estabelecimento_cnpj_unico_por_escritorio`
    # substitui o índice implícito `empresas_estabelecimento_cnpj_key`
    # (Estabelecimento.cnpj deixou de ser `unique=True` de campo — ganhou
    # a coluna `escritorio`, desnormalizada de `empresa.escritorio`, ver
    # `apps/empresas/models.py`). Mesmo ponto de tradução dos três, sem
    # mudança nenhuma na FUNÇÃO — só o NOME da constraint mudou.
    "empresa_cnpj_unico_por_escritorio": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "empresa_cpf_unico_por_escritorio": "apps.empresas.services.erro_de_cnpj_duplicado_como_400",
    "estabelecimento_cnpj_unico_por_escritorio": (
        "apps.empresas.services.erro_de_cnpj_duplicado_como_400"
    ),
    "estorno_de_unico": "apps.contabilidade.services.estornar_lancamento",
    "chave_idempotencia_unica_por_empresa": "apps.contabilidade.services.criar_lancamento",
    # DL-046 (fatia 1) — mesmo desenho das duas de cima, para o livro-caixa:
    # `estornar_lancamento_caixa` usa `select_for_update()` + checagem
    # "ainda não foi estornado" ANTES de gravar (a constraint é a defesa
    # residual de corrida); `criar_lancamento_caixa` compara a impressão
    # digital do conteúdo ANTES de tentar o INSERT com a mesma chave.
    "lancamento_caixa_estorno_de_unico": "apps.livro_caixa.services.estornar_lancamento_caixa",
    "lancamento_caixa_chave_idempotencia_unica_por_empresa": (
        "apps.livro_caixa.services.criar_lancamento_caixa"
    ),
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
    # DL-072 (frente A): no máximo uma escrituração NÃO estornada por vínculo.
    # A corrida que escapa da trava de `select_for_update` chega aqui como
    # violação e vira 409 com mensagem, no savepoint de `_inserir_escrituracao`
    # (apps.fiscal.escrituracao). Não é 400: é conflito de estado, não entrada.
    "escrituracao_ativa_unica_por_vinculo": "apps.fiscal.escrituracao._inserir_escrituracao",
    # DL-078 (frente A): mesma corrida, na escrituração de NFS-e tomada. Savepoint e 409 como a
    # prestada (apps.fiscal.tomadas._inserir_escrituracao_tomada).
    "escrituracao_tomada_ativa_unica_por_vinculo": (
        "apps.fiscal.tomadas._inserir_escrituracao_tomada"
    ),
    "evento_fiscal_unico_por_escritorio": "apps.fiscal.services._processar_um_arquivo",
    # DL-043 (BL-474): a restrição que garante UMA vigência de parâmetro
    # contábil ABERTA por empresa — mesmo molde de
    # "um_periodo_de_regime_aberto_por_empresa", acima, e pelo MESMO
    # motivo: `registrar_parametro_contabil` fecha a vigência anterior
    # ANTES de criar a nova, então só chega a violar esta restrição na
    # corrida residual (duas requisições simultâneas quando ainda não
    # existe nenhuma vigência para o `select_for_update()` travar). O
    # serviço converte o `IntegrityError` em
    # `VigenciaParametroContabilConflitante` (409 — é conflito de ESTADO,
    # não entrada malformada; ver a exceção em `apps.contabilidade.
    # services`).
    "um_periodo_de_parametro_contabil_aberto_por_empresa": (
        "apps.contabilidade.services.registrar_parametro_contabil"
    ),
    # DL-074 (frente A): unicidades traduzidas para 409 pelo serviço `_inserir`, em
    # apps.fiscal.receita (savepoint por INSERT, mesmo molde de `_inserir_escrituracao`).
    "confirmacao_mes_unica_por_empresa": "apps.fiscal.receita._inserir",
    "opcao_caixa_unica_por_ano": "apps.fiscal.receita._inserir",
    # DL-075 (frente A): folha, um lançamento ativo por mês → 409 (conflito de estado).
    "folha_mes_unica_ativa_por_empresa": "apps.fiscal.folha_fator_r._inserir",
    # DL-075 (frente A): atividades. A padrão em aberto e a vigência/enquadramento
    # inválidos saem como 409 e 400, pelo mesmo `_inserir_atividade`.
    "atividade_padrao_unica_em_aberto": "apps.fiscal.pre_das._inserir_atividade",
    "atividade_fim_depois_do_inicio": "apps.fiscal.pre_das._inserir_atividade",
    "atividade_enquadramento_valido": "apps.fiscal.pre_das._inserir_atividade",
    # DL-076 (frente A): ISS por município. Os cadastros de alíquota e de regime recusam
    # o dado ANTES do INSERT (serviços de apps.fiscal.iss_municipal). Estas restrições são o
    # último barramento, e o savepoint de cada `_gravar_*` as traduz: dado fora da regra
    # sai como 400, e unicidade ou vigência repetida como 409 (conflito de estado).
    "aliquota_iss_codigo_ibge": "apps.fiscal.iss_municipal._gravar_aliquota",
    "aliquota_iss_subitem_valido": "apps.fiscal.iss_municipal._gravar_aliquota",
    "aliquota_iss_percentual_ate_5": "apps.fiscal.iss_municipal._gravar_aliquota",
    "aliquota_iss_piso_2_salvo_excecao": "apps.fiscal.iss_municipal._gravar_aliquota",
    "aliquota_iss_fonte_preenchida": "apps.fiscal.iss_municipal._gravar_aliquota",
    "aliquota_iss_fim_depois_do_inicio": "apps.fiscal.iss_municipal._gravar_aliquota",
    "regime_iss_unico_por_empresa_exercicio": "apps.fiscal.iss_municipal._gravar_regime",
    "regime_iss_exercicio_valido": "apps.fiscal.iss_municipal._gravar_regime",
    "regime_iss_regime_valido": "apps.fiscal.iss_municipal._gravar_regime",
    "regime_iss_codigo_ibge": "apps.fiscal.iss_municipal._gravar_regime",
    # Regra do município: só o serviço `cadastrar_regra_municipio` grava (sem rota de
    # cliente); a semeadura de Palmas é da migração 0006, que não passa por esta tradução.
    "regra_iss_codigo_ibge": "apps.fiscal.iss_municipal._gravar_regra",
    "regra_iss_dias_entre_1_e_28": "apps.fiscal.iss_municipal._gravar_regra",
    "regra_iss_fim_depois_do_inicio": "apps.fiscal.iss_municipal._gravar_regra",
    "regra_iss_fonte_preenchida": "apps.fiscal.iss_municipal._gravar_regra",
    "regra_iss_unica_por_inicio": "apps.fiscal.iss_municipal._gravar_regra",
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
    # DL-077 (fatia 3, frente A): restrições de domínio fechado escritas só pelo serviço.
    "ck_importacao_lancamentos_estado_valido": (
        "O estado da importação é escrito só pelo serviço de importação, com os três valores do "
        "enum; nenhuma entrada do cliente chega a este campo."
    ),
    "ck_importacao_lancamentos_formato_valido": (
        "O formato da importação vem de uma lista fechada, validada pelo serviço antes de gravar; "
        "a entrada do cliente é recusada antes do INSERT."
    ),
    "ck_depara_conta_codigo_origem_nao_vazio": (
        "O código de origem é aparado (strip) e conferido por `definir_de_para` antes do INSERT; "
        "o campo não é gravado direto a partir de texto do cliente."
    ),
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
    # DL-052 (A1, critério 5): `valor > 0` no banco. `criar_lancamento` já
    # recusa valor <= 0 item a item ANTES de gravar (e a API/tela só gravam por
    # ela); a constraint é a defesa contra `objects.create()`/`bulk_create()`/
    # SQL direto, que não passam por `MinValueValidator` nem pelo serviço.
    "ck_itemlancamento_valor_positivo": (
        "`CheckConstraint(valor > 0)` do modelo `ItemLancamento` (DL-052). "
        "`criar_lancamento` recusa valor menor ou igual a zero antes de "
        "gravar, e nenhum caminho de cliente (API, tela, importação) grava "
        "`ItemLancamento` sem passar por ele. Defesa em profundidade contra "
        "escrita direta no ORM ou no banco."
    ),
    # DL-052 rodada 1 (D1): `tipo` só débito/crédito no banco. `criar_lancamento`
    # e o formulário só aceitam `TipoPartida`; nenhum caminho de cliente grava
    # `ItemLancamento` sem passar por eles. Defesa contra escrita direta.
    "ck_itemlancamento_tipo_valido": (
        "`CheckConstraint(tipo IN ('debito','credito'))` do modelo `ItemLancamento` "
        "(DL-052, rodada 1, D1). `criar_lancamento` só aceita `TipoPartida` e nenhum "
        "caminho de cliente (API, tela, importação) grava `ItemLancamento` sem passar "
        "por ele. Defesa em profundidade contra escrita direta no ORM ou no banco."
    ),
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
    # A4 (auditoria DL-045, rodada 1): `classificacao_dre=""` era um estado
    # alcançável pela API antes da correção — a `CheckConstraint` fecha o
    # buraco na origem (defesa de banco), mas os DOIS caminhos de cliente
    # que gravam `classificacao_dre` já normalizam `""` para `None` ANTES
    # do INSERT: a API usa `ContaSerializer.validate_classificacao_dre`
    # (`apps/contabilidade/serializers.py`, roda em `validate_<campo>`,
    # antes de qualquer escrita); o admin do Django chama `full_clean()`,
    # cujo `Conta.clean()` (`apps/contabilidade/models.py`) normaliza
    # `""` para `None` como a PRIMEIRA linha do método, antes de qualquer
    # outra guarda rodar. Um `INSERT`/`UPDATE` forjado direto no banco
    # (fora do ORM) é o único caminho que ainda alcança esta constraint —
    # e é exatamente o que ela existe para recusar.
    "ck_conta_classificacao_dre_nao_vazia": (
        "`CheckConstraint` de `Conta.classificacao_dre` (DL-045, A4 da "
        'auditoria da rodada 1): recusa `""` (string vazia) — só `NULL` '
        "ou um valor de `ClassificacaoDre`. Os dois caminhos de cliente "
        '(API e admin) já normalizam `""` para `None` ANTES do INSERT '
        "(ver `ContaSerializer.validate_classificacao_dre` e o topo de "
        "`Conta.clean()`); só ORM/SQL direto, fora de qualquer requisição "
        'de cliente, alcançaria esta constraint com `""`.'
    ),
    # DL-048/CTB-12: constraint NOVA no dia um do campo
    # `classificacao_dlpa`, pelo mesmo motivo da de cima — só que aqui ela
    # nasce junto (a migração 0012 a cria já no AddField), nunca precisou
    # de correção retroativa. Os caminhos de cliente que gravam o campo
    # hoje são a tela de classificação (`conta_classificacao_dlpa`, que só
    # grava via `classificar_conta_na_dlpa` → `full_clean()`), o formulário
    # de conta nova (`ContaCriarForm` → `full_clean()`), o admin (idem) e
    # o cadastro de conta pela API (`ContaSerializer` — ainda sem o campo;
    # quando entrar, é `validate_classificacao_dlpa` no mesmo molde). Todos
    # normalizam `""` para `None` antes do INSERT pelo topo de
    # `Conta.clean()`; só ORM/SQL direto alcançaria a constraint com `""`.
    "ck_conta_classificacao_dlpa_nao_vazia": (
        "`CheckConstraint` de `Conta.classificacao_dlpa` (DL-048/CTB-12): "
        'recusa `""` (string vazia) — só `NULL` ou um valor de '
        "`ClassificacaoDlpa`. Todos os caminhos de cliente que gravam o "
        'campo passam por `Conta.clean()` (topo do método normaliza `""` '
        "para `None`); só ORM/SQL direto, fora de qualquer requisição de "
        'cliente, alcançaria esta constraint com `""`.'
    ),
    # DL-061/CTB-14: constraint NOVA no dia um do campo `classificacao_dmpl`,
    # pelo mesmo motivo das duas de cima. Os caminhos de cliente que gravam
    # o campo hoje são só o serviço `classificar_conta_na_dmpl`
    # (`full_clean()`) e o admin (idem); a tela e a API chegam com a fatia
    # do `especialista-frontend`/fatia 2, e também passam por `Conta.clean()`
    # (o topo do método normaliza `""` para `None`).
    "ck_conta_classificacao_dmpl_nao_vazia": (
        "`CheckConstraint` de `Conta.classificacao_dmpl` (DL-061/CTB-14): "
        'recusa `""` (string vazia) — só `NULL` ou um valor de '
        "`ClassificacaoDmpl`. Todos os caminhos de cliente que gravam o "
        'campo passam por `Conta.clean()` (topo do método normaliza `""` '
        "para `None`); só ORM/SQL direto, fora de qualquer requisição de "
        'cliente, alcançaria esta constraint com `""`.'
    ),
    # DL-066/CTB-15: mesma defesa de BANCO das duas de cima, desde o dia um
    # do campo — `""` nunca é estado válido, e sem a constraint ele
    # apareceria como atividade DESCONHECIDA na apuração da DFC em vez de
    # "sem classificação". O `choices=` do campo e o `ChoiceField` do
    # formulário restringem o domínio antes de qualquer escrita de cliente;
    # `Conta.clean()` normaliza `""` → `None` no caminho validado. Só
    # ORM/SQL direto, fora de qualquer requisição, alcançaria a constraint
    # com `""`.
    "ck_conta_classificacao_dfc_nao_vazia": (
        "`CheckConstraint` de `Conta.classificacao_dfc` (DL-066/CTB-15): "
        'recusa `""` (string vazia) — só `NULL` ou um valor de '
        "`ClassificacaoFluxoCaixa`. Todos os caminhos de cliente que gravam "
        "o campo passam por `Conta.clean()` (topo do método normaliza `"
        "` "
        "para `None`); só ORM/SQL direto, fora de qualquer requisição de "
        'cliente, alcançaria esta constraint com `""`.'
    ),
    # DL-046 (fatia 1): domínio de `ContaLivroCaixa.natureza` — mesmo
    # motivo de `empresa_modo_escrituracao_valido` acima (achado B8/
    # DL-038): `choices=` no campo só vale para form/serializer, nunca
    # para ORM direto. O serializer (`ContaLivroCaixaSerializer`) e o
    # `ChoiceField` do formulário do admin já restringem o domínio antes
    # de qualquer escrita real de cliente.
    "conta_livro_caixa_natureza_valida": (
        "`CheckConstraint` de domínio de `ContaLivroCaixa.natureza` "
        "(DL-046). Os dois caminhos de cliente (API e admin) usam "
        "`ChoiceField`/`choices=` do próprio campo — valor fora do domínio "
        "nunca passa de `to_internal_value`/validação de formulário, 400 "
        "antes de qualquer escrita. Sem caminho de escrita por cliente "
        "REALISTA para o valor inválido."
    ),
    # DL-046, fatia 3 (RC-127/HI-34): FORMATO do código de ocupação da
    # conta (sobreposição opcional) — `criar_conta_livro_caixa` sempre
    # chama `conta.full_clean()` antes do INSERT, que valida o campo
    # (`validar_codigo_ocupacao`, formato e tabela oficial) e `clean()`
    # (coerência com o modelo de rendimento da conta) ANTES de qualquer
    # escrita. Sem caminho de escrita por cliente REALISTA para o valor
    # inválido; só ORM/SQL direto alcançaria esta constraint.
    "conta_livro_caixa_codigo_ocupacao_formato_valido": (
        "`CheckConstraint` de formato de `ContaLivroCaixa.codigo_ocupacao` "
        "(DL-046, fatia 3): 3 dígitos numéricos ou vazio. `criar_conta_"
        "livro_caixa` já recusa antes do INSERT; só ORM/SQL direto "
        "alcançaria esta constraint."
    ),
    # DL-046 (fatia 1): `MinValueValidator(Decimal("0.01"))` no campo já
    # recusa valor <= 0 em qualquer `full_clean()` (admin), e
    # `criar_lancamento_caixa` valida o mesmo antes do INSERT (mesmo
    # padrão de `criar_lancamento`/`ESCALA_MAXIMA_LANCAMENTO_MANUAL` na
    # contabilidade) — a `CheckConstraint` é defesa de banco redundante
    # para ORM/SQL direto.
    "lancamento_caixa_valor_positivo": (
        "`CheckConstraint` de `LancamentoCaixa.valor` (DL-046): recusa "
        "valor <= 0. O caminho de cliente (`criar_lancamento_caixa`) já "
        "recusa antes do INSERT; só ORM/SQL direto alcançaria esta "
        "constraint."
    ),
    # DL-046, fatia 3 (RC-127): os três valores monetários novos e a
    # competência do pagamento de previdência oficial — mesmo motivo de
    # "lancamento_caixa_valor_positivo", acima: `criar_lancamento_caixa`
    # (`_valor_monetario_opcional`) e `LancamentoCaixa.clean()` já recusam
    # antes do INSERT; só ORM/SQL direto alcançaria estas constraints.
    "lancamento_caixa_valor_irrf_nao_negativo": (
        "`CheckConstraint` de `LancamentoCaixa.valor_irrf` (DL-046, fatia "
        "3): recusa valor negativo. O caminho de cliente já recusa antes "
        "do INSERT; só ORM/SQL direto alcançaria esta constraint."
    ),
    "lancamento_caixa_multa_previdencia_nao_negativa": (
        "`CheckConstraint` de `LancamentoCaixa.multa_previdencia` (DL-046, "
        "fatia 3): recusa valor negativo. O caminho de cliente já recusa "
        "antes do INSERT; só ORM/SQL direto alcançaria esta constraint."
    ),
    "lancamento_caixa_juros_previdencia_nao_negativa": (
        "`CheckConstraint` de `LancamentoCaixa.juros_previdencia` (DL-046, "
        "fatia 3): recusa valor negativo. O caminho de cliente já recusa "
        "antes do INSERT; só ORM/SQL direto alcançaria esta constraint."
    ),
    "lancamento_caixa_competencia_previdencia_dia_1": (
        "`CheckConstraint` de `LancamentoCaixa.competencia_previdencia` "
        "(DL-046, fatia 3): exige o primeiro dia do mês. `criar_lancamento_"
        "caixa` chama `validate_constraints()` explicitamente antes do "
        "INSERT (mesmo padrão dos três acima) — um dia diferente de 1 já "
        "vira `LancamentoCaixaInvalido` (400) nesse ponto; só ORM/SQL "
        "direto alcançaria a constraint de banco diretamente."
    ),
    # DL-046 (fatia 2): as SEIS restrições das quatro tabelas normativas do
    # carnê-leão (`apps.livro_caixa.models`). Nenhuma delas tem caminho de
    # ESCRITA de cliente — de propósito (ver o comentário de
    # `VigenciaTabelaProgressivaCarneLeao`, no modelo): estas tabelas só são
    # gravadas por MIGRAÇÃO DE DADOS, revisada e versionada; este app não
    # registra `ModelAdmin` para elas nesta fatia, e não há rota de API que
    # as grave. Quando (e se) ganharem caminho de escrita — por exemplo, um
    # cadastro de nova vigência pela tela —, saem daqui e entram no mapa
    # traduzido.
    "faixa_carne_leao_ordem_unica_por_vigencia": (
        "`UniqueConstraint(vigencia, ordem)` de `FaixaTabelaProgressivaCarneLeao` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    "faixa_carne_leao_ordem_positiva": (
        "`CheckConstraint` de `FaixaTabelaProgressivaCarneLeao.ordem` (DL-046, "
        "fatia 2): recusa ordem < 1. Só gravada por migração de dados; sem "
        "caminho de escrita por cliente."
    ),
    "faixa_carne_leao_aliquota_valida": (
        "`CheckConstraint` de `FaixaTabelaProgressivaCarneLeao.aliquota` "
        "(DL-046, fatia 2): domínio [0, 1] (fração). Só gravada por migração "
        "de dados; sem caminho de escrita por cliente."
    ),
    "faixa_carne_leao_limite_inferior_nao_negativo": (
        "`CheckConstraint` de `FaixaTabelaProgressivaCarneLeao.limite_inferior` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    "reducao_carne_leao_valores_nao_negativos": (
        "`CheckConstraint` de `VigenciaReducaoCarneLeao` (DL-046, fatia 2): "
        "`limite_faixa_plena`/`reducao_maxima`/`limite_superior` não negativos. "
        "Só gravada por migração de dados; sem caminho de escrita por cliente."
    ),
    "dependente_carne_leao_valor_nao_negativo": (
        "`CheckConstraint` de `VigenciaDependenteCarneLeao.valor_por_dependente` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    # DL-046 (fatia 2, DE-089): unicidade de `vigencia_inicio` declarada por
    # `UniqueConstraint` em `Meta.constraints` (NUNCA `unique=True` de
    # campo, que geraria um índice único IMPLÍCITO — ver o comentário nos
    # três modelos, em `apps/livro_caixa/models.py`). Mesma classe das seis
    # de cima: só gravadas por migração de dados, sem caminho de escrita
    # por cliente.
    "vigencia_tabela_carne_leao_inicio_unico": (
        "`UniqueConstraint(vigencia_inicio)` de `VigenciaTabelaProgressivaCarneLeao` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    "vigencia_reducao_carne_leao_inicio_unico": (
        "`UniqueConstraint(vigencia_inicio)` de `VigenciaReducaoCarneLeao` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    "vigencia_dependente_carne_leao_inicio_unico": (
        "`UniqueConstraint(vigencia_inicio)` de `VigenciaDependenteCarneLeao` "
        "(DL-046, fatia 2). Só gravada por migração de dados; sem caminho de "
        "escrita por cliente."
    ),
    # DL-046 (fatia 2, correção da rodada 1, B-5): toda vigência normativa
    # começa no dia 1º — só gravada por migração de dados, sem caminho de
    # escrita por cliente para as três tabelas globais.
    "vigencia_tabela_carne_leao_inicio_dia_1": (
        "`CheckConstraint` de `VigenciaTabelaProgressivaCarneLeao.vigencia_inicio` "
        "(DL-046, fatia 2, B-5). Só gravada por migração de dados; sem caminho "
        "de escrita por cliente."
    ),
    "vigencia_tabela_carne_leao_percentual_simplificado_valido": (
        "`CheckConstraint` de `VigenciaTabelaProgressivaCarneLeao."
        "percentual_desconto_simplificado` (DL-046, fatia 2, B-1). Só gravada "
        "por migração de dados; sem caminho de escrita por cliente."
    ),
    "vigencia_reducao_carne_leao_inicio_dia_1": (
        "`CheckConstraint` de `VigenciaReducaoCarneLeao.vigencia_inicio` "
        "(DL-046, fatia 2, B-5). Só gravada por migração de dados; sem "
        "caminho de escrita por cliente."
    ),
    "vigencia_dependente_carne_leao_inicio_dia_1": (
        "`CheckConstraint` de `VigenciaDependenteCarneLeao.vigencia_inicio` "
        "(DL-046, fatia 2, B-5). Só gravada por migração de dados; sem "
        "caminho de escrita por cliente."
    ),
    # DL-046 (fatia 2, B-5): `DependentesCarneLeaoCliente.competencia_inicio`
    # JÁ é validada em `clean()` (mensagem própria, citando HI-35) — os dois
    # caminhos de escrita (API e `registrar_dependentes_carne_leao`/
    # `retificar_dependentes_carne_leao`) chamam `full_clean()` ANTES de
    # qualquer INSERT/UPDATE; só ORM/SQL direto alcançaria esta constraint.
    "dependentes_carne_leao_competencia_dia_1": (
        "`CheckConstraint` de `DependentesCarneLeaoCliente.competencia_inicio` "
        "(DL-046, fatia 2, B-5). Já validada em `clean()` antes de qualquer "
        "escrita real de cliente."
    ),
    # DL-053 (RC-145/RC-146): as seis restrições de `FechamentoMesCaixa`.
    # O único caminho de escrita é `encerrar_mes_caixa`/`reabrir_mes_caixa`
    # (`apps.livro_caixa.services`), que validam ano/mês/motivo ANTES de
    # gravar (400) e serializam por lock consultivo do (empresa, ano, mês) —
    # duas requisições simultâneas de fechamento do MESMO mês nunca chegam
    # juntas ao INSERT, então a unicidade não é alcançável por corrida de
    # cliente. Só ORM/SQL direto alcançaria qualquer uma das seis.
    "fechamento_mes_caixa_unico_por_empresa_ano_mes": (
        "`UniqueConstraint(empresa, ano, mes)` de `FechamentoMesCaixa` "
        "(DL-053). `encerrar_mes_caixa` toma o lock consultivo exclusivo do "
        "mês e lê a linha antes de criar; a constraint é a defesa de banco "
        "para ORM/SQL direto."
    ),
    "fechamento_mes_caixa_mes_entre_1_e_12": (
        "`CheckConstraint` de `FechamentoMesCaixa.mes` (DL-053): 1 <= mes <= "
        "12. API e serviço recusam mês fora da faixa (400) antes de qualquer "
        "gravação; só ORM/SQL direto alcançaria a constraint."
    ),
    "fechamento_mes_caixa_ano_entre_1970_e_2999": (
        "`CheckConstraint` de `FechamentoMesCaixa.ano` (DL-053): 1970 <= ano "
        "<= 2999. API e serviço recusam ano fora da faixa (400) antes de "
        "qualquer gravação; só ORM/SQL direto alcançaria a constraint."
    ),
    "fechamento_mes_caixa_estado_valido": (
        "`CheckConstraint` de domínio de `FechamentoMesCaixa.estado` (DL-053): "
        "'aberto' ou 'encerrado'. Os serviços só escrevem os dois valores de "
        "`EstadoMesCaixa`; nenhuma rota recebe o estado do cliente."
    ),
    "fechamento_mes_caixa_reabertura_completa": (
        "`CheckConstraint` de `FechamentoMesCaixa` (DL-053, RC-146): "
        "reaberto_em, reaberto_por e motivo_reabertura são todos vazios ou "
        "todos preenchidos, com motivo não vazio. `reabrir_mes_caixa` recusa "
        "motivo em branco (400) antes de gravar; só ORM/SQL direto alcançaria "
        "a constraint."
    ),
    "fechamento_mes_caixa_aberto_exige_reabertura": (
        "`CheckConstraint` de `FechamentoMesCaixa` (DL-053): a linha nasce "
        "encerrada, então 'aberto' sem reabertura registrada não é produzido "
        "por nenhum fluxo. Só ORM/SQL direto alcançaria a constraint."
    ),
    # DL-061, fatia 2 (BL-605): as duas restrições de `MarcacaoDmpl`, o
    # contrato do conjunto de marcação manual da DMPL (E15/E16). O ÚNICO
    # caminho de escrita é `salvar_marcacoes_da_dmpl`
    # (`apps.contabilidade.services`), que valida as duas regras ANTES do
    # INSERT — linha × coluna única por lançamento é checada contra o
    # CONJUNTO novo, e `valor != 0` roda em `MarcacaoDmpl.clean()` via
    # `full_clean()` — e grava sob a trava `select_for_update()` do
    # lançamento, então nem a corrida de duas substituições concorrentes do
    # MESMO lançamento alcança a unicidade. Só ORM/SQL direto (fora de
    # qualquer requisição de cliente) alcançaria as duas.
    "marcacao_dmpl_unica_por_linha_e_coluna": (
        "`UniqueConstraint(lancamento, linha, coluna)` de `MarcacaoDmpl` "
        "(DL-061, fatia 2): cada célula (linha × coluna) aparece uma única "
        "vez por lançamento. `salvar_marcacoes_da_dmpl` recusa a duplicata "
        "no conjunto antes do INSERT; só ORM/SQL direto alcançaria a "
        "constraint."
    ),
    "ck_marcacaodmpl_valor_diferente_de_zero": (
        "`CheckConstraint(valor != 0)` de `MarcacaoDmpl` (DL-061, fatia 2): "
        "marcação de valor zero não descreve evento nenhum. "
        "`salvar_marcacoes_da_dmpl` recusa antes do INSERT (via "
        "`MarcacaoDmpl.clean()`); só ORM/SQL direto alcançaria a constraint."
    ),
    # DL-072 (frente A): a forma da linha. Os serviços (apps.fiscal.escrituracao)
    # sempre gravam estado e colunas do ato coerentes; nenhuma rota de API
    # recebe esses campos do cliente, só natureza e motivo.
    "escrituracao_estado_valido": (
        "Estado de escrituração fiscal fora de rascunho, efetivada e estornada. "
        "Só os serviços de apps.fiscal.escrituracao gravam o estado, sempre "
        "com um dos três valores; a API recebe apenas natureza e motivo."
    ),
    "escrituracao_campos_coerentes_com_o_estado": (
        "Colunas do ato (efetivação e estorno) fora de sincronia com o estado. "
        "Os serviços preenchem as colunas no mesmo UPDATE/INSERT que muda o "
        "estado; nenhuma rota recebe esses campos do cliente."
    ),
    # DL-075 (frente A): folha. O serviço `lancar_folha` valida mês, valores e suporte
    # ANTES do INSERT (EntradaInvalidaFolha, 400); o estado e as colunas do ato só
    # mudam pelos serviços de confirmar e estornar.
    "folha_mes_valido": (
        "Mês e ano fora da faixa da competência. `lancar_folha` valida com "
        "`validar_competencia` e o serializer limita ano e mês antes do INSERT."
    ),
    "folha_valores_nao_negativos": (
        "Componente da folha negativo. `_valor_nao_negativo` recusa antes do INSERT "
        "(400, com o nome do componente); o serializer também limita o mínimo a zero."
    ),
    "folha_campos_obrigatorios": (
        "Documento de suporte vazio. `lancar_folha` recusa o texto vazio antes do INSERT "
        "(400); a rota nunca grava folha sem a fonte declarada."
    ),
    "folha_estado_valido": (
        "Estado da folha fora de rascunho, confirmada e estornada. Só os serviços de "
        "apps.fiscal.folha_fator_r gravam o estado; a API não recebe esse campo."
    ),
    "folha_campos_coerentes_com_o_estado": (
        "Colunas do ato (confirmação e estorno) fora de sincronia com o estado. Os "
        "serviços preenchem as colunas no mesmo UPDATE que muda o estado."
    ),
    # DL-075 (frente A): o padrão e a vigência de atividade têm caminho de cliente
    # (cadastro) e são traduzidos em `RESTRICOES_TRADUZIDAS_FORA_DO_MAPA`.
    # DL-078 (frente A): escrituração de NFS-e tomada. A API não recebe estado nem colunas do
    # ato; natureza e motivo são validados pelo serviço (apps.fiscal.tomadas) antes do INSERT.
    "escrituracao_tomada_estado_valido": (
        "Estado de escrituração de tomada fora de rascunho, efetivada e estornada. Só os "
        "serviços de apps.fiscal.tomadas gravam o estado; a API recebe apenas natureza, motivo "
        "e data de pagamento."
    ),
    "escrituracao_tomada_campos_coerentes_com_o_estado": (
        "Colunas do ato (efetivação e estorno) fora de sincronia com o estado. Os serviços "
        "preenchem as colunas no mesmo UPDATE/INSERT que muda o estado; nenhuma rota recebe "
        "esses campos do cliente."
    ),
    "escrituracao_tomada_pagamento_com_informante": (
        "Data de pagamento sem quem informou, quando, ou sem motivo. `informar_data_pagamento` "
        "recusa motivo vazio antes do UPDATE e grava quem e quando informou no mesmo UPDATE."
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
