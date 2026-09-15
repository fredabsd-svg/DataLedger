# Backlog do DataLedger

Tarefas derivadas do diagnóstico inicial de 2026-09-11, registrado em
[docs/auditorias/2026-09-11-diagnostico-inicial.md](../auditorias/2026-09-11-diagnostico-inicial.md).

Este backlog **não substitui** os planos por demanda exigidos pelo
[AGENTS.md](../../AGENTS.md) §3. Cada item priorizado deve ganhar seu plano em
`docs/planos/DL-xxx.md` antes da implementação.

Requisitos citados (`RC-xx`, `HI-xx`, `PE-xx`) estão em
[requisitos.md](requisitos.md).

## Legenda

**Prioridade:** P0 bloqueia outras entregas · P1 próxima janela · P2 quando
houver espaço.

**Estado:** `planejada`, `em desenvolvimento`, `em validação`, `bloqueada`,
`em revisão`, `integrada` (vocabulário do AGENTS.md §3).

## P0 — achados bloqueadores da auditoria

Estes dois achados receberam gravidade **bloqueador** e o parecer **REPROVADO**
para promoção a ambiente com dados reais. Precisam de correção e teste antes de
qualquer funcionalidade nova.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-40 | Corrigir o vazamento entre empresas em `conta_pai` (achado 1). `ContaSerializer` expõe `conta_pai` gravável sem queryset restrito; a defesa está em `Conta.clean()`, que o DRF **não chama**. | `desenvolvedor-pleno` | — | **em desenvolvimento** ([DL-007](../planos/DL-007-correcao-bloqueadores-contabilidade.md)) | `POST /contabilidade/empresas/<A>/contas/` com `conta_pai` de outra empresa retorna 400. Teste no caminho HTTP, não só no modelo. |
| BL-41 | Impedir estorno duplicado e introduzir idempotência na escrituração (achado 2). Hoje um lançamento pode ser estornado várias vezes e um POST repetido duplica. | `desenvolvedor-pleno` | — | **em desenvolvimento** ([DL-007](../planos/DL-007-correcao-bloqueadores-contabilidade.md)) | Estorno chamado duas vezes produz exatamente um estorno; teste concorrente idem; POST repetido com a mesma chave de idempotência não duplica. |
| BL-42 | Decidir como garantir que validações de modelo valham no caminho da API. **Causa raiz comum de BL-40 e do achado 4:** o DRF não executa `full_clean()`, então regra escrita só em `Model.clean()` ou em validador de campo é decorativa via API. | `arquiteto-senior` decide; `desenvolvedor-pleno` implementa | — | **decidida** (DE-008) | Decisão registrada em [decisoes.md](decisoes.md) e aplicada de forma uniforme; teste que prove a validação ativa via HTTP. |
| BL-43 | Fazer a interface enviar `Idempotency-Key` nos formulários de lançamento. Decorre de DE-009: a proteção existe, mas só vale quando o cliente manda a chave. | `especialista-frontend` | BL-41, existir tela de lançamento | planejada | Formulário de lançamento envia chave única por tentativa; duplo clique não gera dois lançamentos. |

## P0 — defeito em vigor: CNPJ alfanumérico

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-46 | Aceitar **CNPJ alfanumérico** no cadastro, na validação e em tudo que compare CNPJ. Hoje o DataLedger **recusa** qualquer CNPJ alfanumérico. | `desenvolvedor-pleno` | **Resolvida**: NT Conjunta 2025.001 e IN RFB 2.229, fornecidas pelo Fred em 2026-09-12 | **integrada** na branch de trabalho — [DL-011](../planos/DL-011-cnpj-alfanumerico.md), commit `44f9fe6`. Cinco rodadas de auditoria: 1 reprovada, 2 a 4 aprovadas com ressalvas, 5 liberada para encerramento | CNPJ alfanumérico válido é aceito e persistido; CNPJ numérico existente continua válido; DV conferido pelo algoritmo **oficial**, com casos de referência; nenhum ponto do sistema descarta letras do CNPJ. |

### Por que é P0 e por que já está em vigor

Confirmado em fonte oficial da **Receita Federal** em 2026-09-12: a implantação
do CNPJ alfanumérico começou em **31 de julho de 2026**, regida pela **Instrução
Normativa RFB nº 2.229**, publicada em 15/10/2024. **Já está valendo.** CNPJs
numéricos existentes seguem inalterados.

**O defeito, demonstrado por execução:**

`apps/empresas/validators.py` faz
`digitos = "".join(filter(str.isdigit, valor))` — ou seja, **descarta as
letras** — e depois exige 14 dígitos. Um CNPJ alfanumérico de 14 caracteres é
reduzido a 9 dígitos e recusado com a mensagem "CNPJ deve ter 14 dígitos".

Reprodução:

| Entrada | Resultado hoje |
| --- | --- |
| `11.222.333/0001-81` (numérico) | Aceito |
| `12ABC34501DE35` (14 caracteres, com letras) | **Recusado** |

O impacto não é só o cadastro: **qualquer comparação de CNPJ** herda o problema,
inclusive a futura identificação da empresa no XML importado e a chave de acesso
da NF-e, que contém o CNPJ do emitente.

### Como deixou de estar bloqueada

Esteve bloqueada enquanto só havia o **fato** e a **data** em fonte oficial, sem
o **algoritmo do dígito verificador**. Fontes secundárias descreviam o cálculo,
mas implementar dígito verificador a partir de descrição de blog é exatamente o
que o [AGENTS.md](../../AGENTS.md) §10 proíbe: inventar fórmula. Um validador
errado recusaria empresa legítima ou aceitaria CNPJ inválido — os dois caros.

**Desbloqueada em 2026-09-12**, quando o Fred forneceu a **Nota Técnica Conjunta
CNPJ Alfanumérico, NT 2025.001, versão 1.00, de 25/04/2025**, do ENCAT, cujo
Anexo I traz a implementação de referência. Base legal: **IN RFB nº 2.229**, de
15/10/2024. Fonte e vigência registradas junto do código, em
`apps/empresas/validators.py`.

## P1 — achados preexistentes revelados pela reauditoria da DL-011

Nenhum dos dois foi causado pela DL-011. A reauditoria da rodada 2 os encontrou
ao atacar o entorno e os reproduziu por execução. Registrados para não se
perderem.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-48 | Decidir o escopo da unicidade de CNPJ. Hoje `Empresa.cnpj` e `Estabelecimento.cnpj` são `unique=True` **globais**, sem escopo de escritório, e a mensagem de erro confirma a existência do cadastro em **outro** escritório. | `arquiteto-senior` conduz; **decisão do Fred** | — | **bloqueada** — depende de PE-21 | Escritório A não consegue descobrir, por tentativa de cadastro, se um CNPJ já é cliente de outro escritório; cadastro duplicado **dentro** do próprio escritório continua com mensagem específica e útil. |
| BL-49 | `POST` *form-encoded* ou *multipart* na API de empresas cria a empresa com `ativo: false`, apesar de `default=True` no modelo. É o tratamento de entrada HTML do `BooleanField` do DRF. | `desenvolvedor-pleno` | — | planejada | Empresa criada por qualquer tipo de corpo de requisição nasce ativa, salvo se `ativo` for enviado explicitamente como falso; teste cobrindo JSON, *form-encoded* e *multipart*. |

### BL-48 — por que isto é comercial, não só técnico

Reproduzido pelo `auditor-qa` em 2026-09-12: com a empresa `AB123CDE000155`
cadastrada no **escritório B**, o gestor do **escritório A**, autenticado,
recebe `400 {"cnpj":["empresa com este CNPJ já existe."]}` ao tentar cadastrar o
mesmo CNPJ. A listagem dele continua vazia — **o isolamento de leitura está
correto** —, mas a mensagem de erro entrega a informação.

Na prática: um escritório consegue descobrir, um CNPJ por tentativa, se
determinada empresa já é cliente de **outro** escritório no mesmo DataLedger.
Não revela razão social nem qual escritório. Ainda assim, é informação
comercial num produto vendido a concorrentes entre si.

Contradiz a regra que o próprio projeto escreveu em `apps/empresas/mixins.py`:
*"404, não 403: não confirma nem a existência do registro para quem não tem
acesso."*

**Vem da DL-004**, não da DL-011. Mas a DL-011 **amplia** o alcance: antes, o
oráculo podia ser driblado por diferença de maiúscula e minúscula; agora a
canonização fecha essa fresta e o oráculo fica exato.

Registrado como **PE-21** em [requisitos.md](requisitos.md), porque a escolha
entre unicidade global e unicidade por escritório é decisão de produto — e é
difícil de reverter depois que houver dado real.

## P1 — ressalvas da auditoria da DL-011 que vão para backlog

O `auditor-qa` separou, a pedido, o que trava o fechamento da etapa e o que pode
esperar. Estes três podem esperar; A1, A2 e A4 entraram na própria etapa. Ver
[reauditoria da rodada 3](../auditorias/2026-09-12-dl-011-reauditoria-rodada-3.md).

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-54 | **Fortalecer a restrição de banco do CNPJ** (achado A5). Hoje `empresa_cnpj_canonico` garante **canonicidade**, não **formato**: por `bulk_create` passam `''`, `'ABC'`, `'AB123CDE000199'` (DV errado) e `'AB123CDE0001AA'` (letra no DV). O comentário no código aponta a restrição como garantia para a importação em lote da DL-010 — e nessa direção ela não garante. | `desenvolvedor-pleno` | — | planejada | Condição passa a `Q(cnpj__regex=r"^[A-Z0-9]{12}[0-9]{2}$")`, que é a regex oficial do Anexo I. `bulk_create` com `''`, `'ABC'` e `'AB123CDE0001AA'` levanta `IntegrityError`, com teste. O comentário declara explicitamente que o **dígito verificador não é conferido pelo banco**. |
| BL-55 | **Prender a camada do serializer sozinha** (achado A6). Os mutantes N6 (`to_internal_value` valida mas não normaliza) e N12 (remover o `UniqueValidator`) sobrevivem à suíte, porque `Model.save()` e a tradução do `IntegrityError` cobrem por trás. Defesa em profundidade funcionando — mas cada camada só está protegida pela existência da outra. | `desenvolvedor-pleno` | — | planejada | Teste que valide `EmpresaSerializer` isoladamente, sem `save()`, afirmando `validated_data["cnpj"] == "AB123CDE000155"` a partir de `"ab.123.cde/0001-55"`. N6 e N12 passam a morrer. |
| BL-57 | **Alterar o CNPJ de uma empresa por `PUT`/`PATCH` não gera registro na trilha de auditoria** (achado B3, **preexistente** da DL-004). Reproduzido: `PATCH` do CNPJ por gestor autorizado devolve 200, altera o identificador da empresa perante a Receita, e a trilha registra apenas `login.sucesso`. `perform_create` e `criar_empresa` registram; o caminho de alteração não. | `desenvolvedor-pleno` | — | planejada | `PATCH`/`PUT` que altere CNPJ gera `RegistroAuditoria` com ator, objeto, **valor anterior e novo**, com teste. Decidir com o Fred se o CNPJ anterior entra nos detalhes — a recomendação é que sim, é o dado que dá sentido ao registro. |
| BL-58 | **O Django admin grava CNPJ sem passar pelo tratamento de erro de duplicidade** (achado B4). `EmpresaAdmin` e `EstabelecimentoInline` não sobrescrevem `save_model` nem `save_formset`; sob corrida real, o `IntegrityError` sobe sem tradução e vira 500. Fecha o inventário de caminhos de gravação de CNPJ, que hoje são cinco. | `desenvolvedor-pleno` | — | planejada | `save_model`/`save_formset` usam `erro_de_cnpj_duplicado_como_400()` e convertem em erro de campo. Teste no `add_view` com `validate_unique` neutralizado, esperando erro de campo em vez de 500. |
| BL-56 | **Dica de digitação no campo de CNPJ** (achado A7). A correção do R2 removeu o `maxlength="14"` do HTML — corretamente, porque ele truncava a máscara no navegador antes de qualquer validação. Não há risco: o servidor recusa o que estiver fora do formato. É melhoria de experiência. | `especialista-frontend` | — | planejada | Campo orienta a digitação sem impedir a máscara: `maxlength="18"` é o máximo semanticamente possível. Nenhuma entrada legítima passa a ser recusada. |

**BL-54 deve estar resolvido antes de a [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) importar em lote**, e agora por **dois** motivos, não um. Além de a restrição garantir canonicidade e não formato, a auditoria da rodada 4 mostrou que é justamente ela permitir `cnpj` com menos de 14 caracteres que torna alcançável o **500** do achado B1. Fortalecer a restrição para `^[A-Z0-9]{12}[0-9]{2}$` elimina o gatilho por consequência.

## P1 — lacunas de validação encontradas de passagem

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-47 | Validar o CNPJ do **próprio escritório**. `apps/tenancy/models.py` declara `cnpj = CharField(max_length=14, unique=True)` **sem validador algum** — aceita qualquer texto de até 14 caracteres, inclusive `"abc"`. | `desenvolvedor-pleno` | DL-011 concluída **e** decisão do Fred sobre dados existentes | **bloqueada** — precisa de plano de dados, ver evidência abaixo | `Escritorio.cnpj` recusa valor inválido, aceita numérico e alfanumérico, com teste. Avaliar o que fazer com registros existentes que não passem na validação. |

Encontrado pelo `desenvolvedor-pleno` durante a DL-011, **fora do escopo da
etapa**, e reportado em vez de corrigido — a disciplina certa.

Por que não entrou na DL-011: o BL-46 trata do CNPJ das **empresas clientes**;
este é o CNPJ do **escritório contábil**, outro modelo e outro contexto.
Misturar os dois numa etapa faria o diff perder foco.

Cuidado ao implementar: pode haver escritório já cadastrado com CNPJ que não
passe na validação. Acrescentar validador a campo existente **quebra o
salvamento** desses registros. Verificar a base antes e decidir o tratamento —
não é caso de aplicar e ver o que acontece.

### O risco deixou de ser hipotético — evidência medida

Conferido pelo `arquiteto-senior` em 2026-09-12, durante a revisão da DL-011:
**os cinco CNPJs de `Escritorio` usados na suíte de testes são todos inválidos**
pelo dígito verificador.

| CNPJ no teste | DV informado | DV correto |
| --- | --- | --- |
| `11111111000111` | 11 | 91 |
| `22222222000122` | 22 | 91 |
| `33333333000133` | 33 | 91 |
| `55566677000155` | 55 | 83 |
| `55566677000255` | 55 | 64 |

Eles só existem porque `Escritorio.cnpj` nunca teve validador. Consequência
direta para o BL-47:

1. Acrescentar `validar_cnpj` ao campo **quebra a suíte inteira**, não um teste
   isolado. Os dados de teste precisam ser trocados por CNPJs sintéticos com DV
   correto, na mesma etapa.
2. Em base real, escritório com CNPJ inválido fica **impossível de salvar**,
   mesmo para alterar outro campo, se a canonização for feita em `save()` como
   foi em `Empresa.save()`. Isso exige levantar a base antes e decidir entre
   corrigir os dados, permitir gravação de registro herdado, ou bloquear com
   mensagem que oriente a correção.
3. Portanto o BL-47 **não é tarefa de uma linha**. Tem plano de dados, e o Fred
   precisa dizer o que fazer com escritório cujo CNPJ esteja errado no cadastro
   atual — corrigir na hora ou registrar pendência de cadastro.

## P0 — implantação em nuvem (DE-014)

Abertos em 2026-09-12, quando o Fred decidiu implantação **em nuvem** com cerca
de **50 usuários simultâneos** (RC-48, RC-49). Nenhum é urgente **hoje**, porque
não há nada em produção. Todos são **pré-condição para existir dado real de
cliente** — e por isso são P0, não P2.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-50 | **Impedir que o sistema suba sem PostgreSQL.** Hoje `config/settings.py` usa `env.db("DATABASE_URL", default="sqlite:///...")`: sem a variável configurada, cai em SQLite **em silêncio**. SQLite não suporta a escrita concorrente de 50 usuários e falharia **em uso**, não na instalação. | `desenvolvedor-pleno` | — | planejada | Com `DEBUG=False` e sem `DATABASE_URL`, a aplicação **recusa subir** com mensagem explícita. SQLite segue permitido apenas em desenvolvimento, de forma declarada. Teste automatizado. |
| BL-51 | **HTTPS e cabeçalhos de segurança.** Acesso pela internet sem cifra expõe senha e dado de cliente. Hoje não há proxy reverso nem configuração de `SECURE_*`. | `desenvolvedor-pleno` | — | planejada | `manage.py check --deploy` sem avisos; redirecionamento para HTTPS; HSTS; *cookies* de sessão e CSRF marcados como seguros; proxy reverso documentado no procedimento de implantação. |
| BL-52 | **Fila de tarefas em segundo plano.** Importar milhares de XMLs dentro de uma requisição web estoura tempo limite, prende trabalhador do servidor e degrada a experiência dos demais usuários. | `arquiteto-senior` decidiu (**DE-015**); `desenvolvedor-pleno` implementa junto com a DL-010 | — | **decidida** — `django.tasks` com backend `django-tasks-db`, sem infraestrutura nova | Importação submetida devolve resposta imediata com identificador; o processamento roda fora da requisição; o usuário consulta progresso e resultado depois; falha de um lote não derruba o processo. |
| BL-33 | **Cópia de segurança e restauração, com restauração efetivamente testada.** Elevado de P2 a P0 pela DE-014: banco único em nuvem significa que **o escritório inteiro para junto** se ele se perder. Cópia nunca restaurada não é cópia, é esperança. | `arquiteto-senior` define; `desenvolvedor-pleno` implementa | PE-07 | planejada | Restauração executada em ambiente descartável, a partir de cópia real, com evidência registrada e tempo de recuperação medido. |
| BL-53 | **Procedimento de implantação documentado e executado uma vez**, do zero ao sistema no ar, incluindo variáveis de ambiente obrigatórias, migração e `collectstatic`. | `arquiteto-senior` | BL-50, BL-51 | planejada | Documento que um terceiro consegue seguir; execução registrada com evidência. |

**A verificação do BL-52 revelou algo que muda mais ainda: nenhuma das filas candidatas se recupera sozinha da queda do trabalhador.** Com `kill -9` no meio do processamento, as duas deixam a tarefa presa para sempre, e subir um trabalhador novo não retoma. Consequência registrada na **DE-015**: a resiliência é **nossa**, e a DL-010 precisa de modelo próprio de lote com progresso por documento, sinal de vida, estado visível e idempotência pela chave de acesso. Sem esses quatro itens a etapa não fecha, por mais que a fila funcione.

**BL-52 muda o desenho da [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md).**
A etapa deixa de ser "ler arquivo e gravar" e passa a ser "receber arquivo,
enfileirar, processar em segundo plano e relatar". É melhor descobrir isso agora
do que depois de a etapa estar escrita.

## P0 — decisões e bloqueios

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-01 | Fred responder as pendências PE-01 a PE-08 de [requisitos.md](requisitos.md), com prioridade para PE-01 (prioridade de negócio) e PE-02 (política de arredondamento). | `arquiteto-senior` conduz; decisão é do Fred | — | planejada | Cada pendência vira requisito confirmado ou decisão registrada em [decisoes.md](decisoes.md). |
| BL-02 | Configurar proteção da branch `main`: exigir PR, revisão autorizada e verificações obrigatórias aprovadas. | `arquiteto-senior`, por pedido do Fred em 2026-09-13 ([DL-014](../planos/DL-014-guardas-de-processo.md)) | — | **em validação** | Merge direto em `main` recusado; PR sem CI aprovada não mescla. Registrar evidência da configuração. |

BL-02 é pendência herdada da DL-002, registrada no README e ainda não
resolvida. É **ação administrativa no GitHub**: nenhum agente pode executá-la.
Sem ela, o erro de encadeamento de PRs que motivou os PRs #7 a #9 pode
repetir-se.

## P1 — invariantes contábeis não implementadas

Estas lacunas são de **requisito declarado e não implementado**, não de defeito
no que existe. Foram localizadas no diagnóstico com arquivo e linha.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-10 | Implementar distinção entre **rascunho** e **lançamento efetivado** (RC-12). Hoje todo lançamento nasce efetivado e imutável; não existe campo de situação. | `desenvolvedor-pleno` | BL-01 (PE-01) | planejada | Campo de situação no modelo; rascunho editável e excluível; efetivação é transição explícita e auditada; efetivado permanece imutável. Testes para cada transição, incluindo as proibidas. |
| BL-11 | Implementar **controle de período encerrado** e reabertura autorizada (RC-16). Não existe hoje. | `desenvolvedor-pleno` | BL-10, BL-01 (PE-05) | planejada | Lançamento em período fechado é recusado no servidor; reabertura exige papel autorizado e gera registro de auditoria. Testes de recusa, de reabertura autorizada e de tentativa não autorizada. |
| BL-12 | Implementar **idempotência** na criação de lançamentos e no estorno (RC-14). Hoje o mesmo POST repetido cria lançamentos duplicados, e um lançamento pode ser estornado várias vezes. | `desenvolvedor-pleno` | — | planejada | POST repetido com a mesma chave de idempotência não duplica; segundo estorno do mesmo lançamento é recusado. Testes de repetição e de concorrência. |
| BL-13 | Avaliar **constraint de banco** para a igualdade débito=crédito. Hoje a invariante vive só na camada de serviço, e `LancamentoContabil.objects.create` direto a contorna. | `desenvolvedor-pleno` | BL-10 | planejada | Decisão registrada em [decisoes.md](decisoes.md). Se implementada, teste que prove a recusa no nível do banco. |
| BL-14 | Mover o registro de auditoria para **dentro da transação** do serviço. Hoje o `registrar` de auditoria fica fora da transação. | `desenvolvedor-pleno` | — | planejada | Falha após a gravação do lançamento não deixa lançamento sem trilha, nem trilha sem lançamento. Teste com falha induzida. |
| BL-16 | Proteger a imutabilidade contra mutação em massa e a trilha de auditoria contra exclusão (achado 3, gravidade alta). `QuerySet.update()`/`delete()` não passam por `save()`/`delete()`; `RegistroAuditoriaAdmin` não define `has_delete_permission`. | `desenvolvedor-pleno` | — | planejada | Testes com `objects.filter(...).update()` e `.delete()` falham; registro de auditoria não é excluível pelo admin. |
| BL-17 | Validar sinal e escala dos valores no serviço (achado 4, gravidade alta). Hoje `MinValueValidator` e `decimal_places` só rodam em `full_clean()`, nunca chamado: partida negativa passa e o arredondamento ocorre **depois** da checagem de igualdade. | `desenvolvedor-pleno` | BL-42, BL-01 (PE-02) | planejada | Testes de limite com valor negativo e com três casas decimais são recusados. Política de arredondamento declarada e aplicada. |
| BL-18 | Corrigir a auditoria de login (achado 8, gravidade média): eventos gravam `escritorio=None` e a listagem filtra por escritório, então **nunca aparecem**. O nome de usuário tentado é persistido — uma senha digitada no campo de usuário vazaria em texto claro. | `desenvolvedor-pleno` | — | planejada | Login e falha de login aparecem para o papel autorizado; nenhum dado potencialmente sensível é persistido. |
| BL-19 | Corrigir a corrida e a validação do regime tributário (achado 9, gravidade média): `select_for_update().filter(...).first()` não bloqueia quando não há período vigente, e `regime` não é validado contra as opções. | `desenvolvedor-pleno` | — | planejada | Teste concorrente não produz dois regimes vigentes; regime inválido é recusado com 400. |
| BL-15 | Definir e implementar o conceito de **competência** (RC-05). Não existe no código: nenhuma ocorrência em `apps/`, `config/` ou `templates/`. | `arquiteto-senior` define; `desenvolvedor-pleno` implementa | BL-01 | planejada | Modelo de competência definido e documentado; seletor disponível; lançamento vinculado a competência. |

## P1 — contabilidade utilizável ([DL-015](../planos/DL-015-contabilidade-utilizavel.md))

Lacunas levantadas em 2026-09-13 no cruzamento entre o
[mapa funcional contábil](mapa-funcional-contabil.md) e o código de
`apps/contabilidade/`. São **funcionalidade ausente**, não defeito: o núcleo de
partidas dobradas está correto e auditado.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-59 | **Razão e Balancete não aceitam período.** Verificado: nenhum filtro de data em `apps/contabilidade/views.py`. O Razão devolve todos os itens da conta desde o primeiro lançamento; o Balancete soma tudo. Um contador não emite balancete "de sempre", emite de um mês. | `desenvolvedor-pleno` | BL-15 | **em correção, rodada 3** — implementada em `8f2c209`, corrigida em `05f93f0`, reprovada nas rodadas 1 e 2 da auditoria | Razão e Balancete aceitam intervalo obrigatório de datas. Balancete devolve **saldo anterior, débitos do período, créditos do período e saldo final** por conta, e o total de débitos do período é igual ao total de créditos. Teste que confere a linha do Balancete contra a soma do Razão da mesma conta e período. |
| BL-60 | **Balancete não totaliza contas sintéticas** nem permite escolher o nível. Hoje lista só as analíticas. Um balancete de conferência precisa mostrar os grupos somando as filhas. | `desenvolvedor-pleno` | BL-59 | **em correção, rodada 3** — implementada em `8f2c209`, corrigida em `05f93f0`, reprovada nas rodadas 1 e 2 da auditoria | Balancete aceita o nível desejado; a soma de cada sintética é igual à soma das analíticas subordinadas; teste com hierarquia de três níveis. |
| BL-61 | **Não existe livro Diário.** O que há é a listagem cronológica da API. Falta a saída por lote, com totais de débito e crédito de cada lançamento e total do período. | `desenvolvedor-pleno` | BL-59 | **em correção, rodada 3** — implementada em `8f2c209`, corrigida em `05f93f0`, reprovada nas rodadas 1 e 2 da auditoria | Diário do período, por data e lote, com totais por lote e do período. O total do Diário do período é igual ao total de movimento do Balancete do mesmo período — teste que compara os dois. |
| BL-62 | **A contabilidade não tem interface.** Só API; os templates cobrem empresas, login, painel e erros. Enquanto durar, ninguém no escritório consegue usar o sistema sem programar. | `especialista-frontend` com `desenvolvedor-pleno` | BL-59, BL-20 a BL-24 | planejada | Telas de plano de contas, lançamento (com conferência do total antes de gravar), Razão e Balancete, com os cinco estados (carregando, vazio, erro, sucesso, sem permissão), em pt-BR, acessíveis por teclado. Um lançamento completo é feito e conferido pelo navegador, com evidência. |
| BL-63 | **Lançamento de abertura (saldos iniciais).** RC-53 e **RC-62**: um único lançamento com vários débitos e vários créditos, datado na data de encerramento do balanço do escritório anterior. Não exige modelo novo — exige o assistente que evita digitar dezenas de linhas à mão. | `desenvolvedor-pleno` | BL-59, **PE-38** para a parte de lucros acumulados | planejada | Lançamento identificável como abertura (origem própria, BL-72); a igualdade débito=crédito já é a validação certa, e a soma por grupo do balanço confere com o balancete do primeiro período; recusa conta de resultado, **exceto** o tratamento de lucros/prejuízos acumulados definido em PE-38; retificadora entra pelo lado da natureza dela; teste com o balanço de referência enviado pelo Fred (grupo do imobilizado fechando em 29.263,32 D). |
| BL-64 | **Conferência de lotes com diferença entre débito e crédito.** A igualdade é validada no serviço, mas nada varre a base: um lote gravado por caminho que não passe pelo serviço (migração, shell, importação futura) fica torto em silêncio. | `desenvolvedor-pleno` | — | **em correção, rodada 3** — implementada em `8f2c209`, corrigida em `05f93f0`, reprovada nas rodadas 1 e 2 da auditoria | Consulta que lista lotes desbalanceados da empresa, com a diferença; teste que grava um lote torto por caminho alternativo e prova que a consulta o encontra. |
| BL-65 | **Alteração em massa de lançamentos** (RC-51, desenho em **DE-017**). Período aberto: altera e guarda a versão anterior inteira. Período encerrado: só por lançamento de ajuste. | `desenvolvedor-pleno` | **BL-11** (fechamento), PE-35 (alcance dos campos) | planejada | Alteração em lote por filtro, com pré-visualização da contagem antes de aplicar; versão anterior gravada na mesma transação, com autor, data, motivo e identificador do lote; `save()` direto continua recusado; lançamento de período encerrado gera ajuste em vez de alteração; operação atômica e idempotente; teste com falha induzida no meio do lote provando que nada fica pela metade. |
| BL-66 | **Regeração de lançamentos derivados** (RC-59, desenho em **DE-018**): apagar os lançamentos gerados pela escrita fiscal num período e refazê-los a partir das notas — o caso real é trocar o plano de contas no meio do ano. Não é apagar escrituração: a origem permanece. | `desenvolvedor-pleno` | **BL-72** (origem no lançamento), **BL-11**, e a existência da integração fiscal→contábil | planejada | Alcança **só** lançamento de origem automática, nunca manual — teste que prova que o manual sobrevive; só período aberto (recusa, não aviso); preserva **por padrão** o que foi alterado à mão e o que está conciliado, e desligar essa proteção é ato explícito e registrado; idempotência por **chave natural** (documento de origem + tipo), para que reprocessar não duplique mesmo que a rotina falhe no meio; apaga e refaz na mesma transação, com teste de falha induzida provando que o período não fica sem lançamento; registra na trilha quantos saíram e quantos entraram. |
| BL-72 | **Origem e documento de origem no lançamento contábil.** Hoje `LancamentoContabil` não tem nenhum dos dois: não há como distinguir lançamento digitado de lançamento gerado, nem chegar da nota ao lançamento e vice-versa. É pré-requisito de BL-66 e da integração fiscal→contábil da DL-010. | `desenvolvedor-pleno` | — | planejada | Campo de origem com valores controlados; referência ao documento que originou o lançamento, quando houver; a origem não é alterável depois de gravada; consulta que parte do documento e chega aos lançamentos, e o caminho inverso; teste de isolamento entre empresas na consulta. Entra junto da DL-016 para não haver duas migrações do mesmo modelo. |
| BL-79 | **[RESOLVIDA]** O Django admin gravava lançamento que violava a partida dobrada (DE-023) (achado novo 6 da rodada 2). Pela tela de administração é possível gravar item com conta de outra empresa, lote desbalanceado e lote sem nenhuma partida — nenhum passa por `criar_lancamento`, e `ItemLancamento` não tem `clean()`. Não depende de migração, ao contrário de BL-78. | `desenvolvedor-pleno` | — | **integrada** | `ItemLancamento.clean()` exige que a conta e o lançamento sejam da mesma empresa; o campo de conta no admin só oferece contas da empresa do lançamento; decidido e implementado o que o admin pode gravar. Teste que faz o POST do admin nos três casos e exige recusa, sem nada gravado. |
| BL-80 | **[RESOLVIDA]** Acelerar a suíte trocando o algoritmo de senha em teste — medido: 199 s → 10 s, com 201 aprovados.  (observação 1 da rodada 2). Medido pelo auditor: `pytest apps/contabilidade` cai de **195 s para 4,4 s**, com os mesmos 173 testes passando, e a suíte completa de 297 s para poucos segundos. O custo de hoje é o cifrador de senha de produção rodando em cada login de teste. | `desenvolvedor-pleno` | — | **integrada** | Configuração aplicada **apenas** em teste, jamais em produção, com o motivo registrado no próprio arquivo; suíte com a mesma contagem de aprovados antes e depois. Ganho relevante para toda etapa futura: viabiliza campanhas de mutação mais amplas na auditoria. |
| BL-83 | **O `ContaAdmin` permite mover conta COM movimento para outra empresa e trocar a natureza de conta já movimentada** (achado novo 1 da [rodada 4](../auditorias/2026-09-14-dl-015-rodada-4.md)). Medido: o balancete da empresa passa a mostrar **zero de débito contra mil de crédito** enquanto o diário continua fechando, e as quatro categorias da conferência não acusam nada. Trocar a natureza inverte o sinal de todo o histórico da conta, com trilha só no log interno do Django. Pré-existente; exige perfil administrativo, que nenhum fluxo do produto concede. | `desenvolvedor-pleno` | — | planejada | **Bloqueador de implantação**: precisa estar fechado antes de existir dado real de cliente. `Conta.clean()` recusa troca de empresa em conta com partidas ou filhas, e troca de natureza/tipo em conta com movimento; teste com POST do admin exigindo recusa e objeto inalterado; docstring do `ContaAdmin` corrigido para declarar o risco de **alteração**, não só o de exclusão. |
| BL-84 | **A conferência não detecta partida cuja conta é de outra empresa** (achado novo 2 da rodada 4). É justamente o estado que BL-78 declara aceitável até a DL-016 **porque seria detectável** — e não é. | `desenvolvedor-pleno` | — | planejada | Quinta categoria na conferência, listando lançamento e conta; teste que cria o estado por ORM direto e exige que a conferência o aponte nomeando a conta. |
| BL-85 | **Lado credor da absorção por corte de nível sem teste** (achado novo 3 da rodada 4). O mutante que troca `creditos_proprios` pelo agregado ingênuo sobrevive à suíte inteira; o simétrico devedor morre. O código está certo hoje — falta a rede. | `desenvolvedor-pleno` | — | planejada | Cenário com movimento **credor** em neta de nível 3 e corte em `nivel=1`; o mutante passa a matar teste. |
| BL-86 | **A soma do balancete não vale sob escrituração concorrente** (achado novo 4 da rodada 4). As duas consultas do Balancete correm fora de transação; com um lançamento efetivado entre elas, a soma dos próprios deu 100,00 contra rodapé de 150,00. Transitório e sem corrupção, mas contradiz o "sempre" escrito em DE-024 §2 — e acontece justamente durante um fechamento de mês. | `arquiteto-senior` (texto) e `desenvolvedor-pleno` (código) | — | planejada | Ou leitura consistente por transação, ou o texto da DE-024 §2 passa a dizer "sobre um instantâneo consistente do banco". Teste que reproduza a janela. |
| BL-81 | **Conferir a suíte em árvore limpa antes de declarar contagem de testes** (DE-024 §1). A rodada 3 mostrou que "392 passed" foi medido numa árvore com `staticfiles/` de dois dias antes; em `checkout` novo o resultado era 1 falha. | `arquiteto-senior` | — | planejada | Procedimento registrado no AGENTS.md: antes de declarar contagem num commit ou relatório, extrair o commit em diretório vazio (`git archive`) e rodar ali. Avaliar um passo de integração contínua que falhe se a suíte depender de artefato não versionado. |
| BL-82 | **Guarda que recuse subir com `DEBUG=True` fora de desenvolvimento** (DE-024 §3, achado novo 4 da rodada 3). Hoje não existe, e raciocínios de segurança do projeto já se apoiam nela como se existisse — inclusive a segunda condição da troca de algoritmo de senha. | `desenvolvedor-pleno` | — | planejada | Definir o sinal de "fora de desenvolvimento" (variável explícita de ambiente, não inferência); com ele presente e `DEBUG=True`, a aplicação recusa subir com mensagem clara; teste em subprocesso, como os de BL-50/51. |
 item, conta e lançamento da mesma empresa** (achado 10 da auditoria, **DE-021**). A defesa em código já entrou; falta a do esquema, que atravessa três tabelas e exige desnormalizar a empresa para o item com chaves compostas. | `desenvolvedor-pleno` | **DL-016** (mesma migração de BL-72) | planejada | Gravar item cuja conta e cujo lançamento sejam de empresas diferentes é recusado **pelo banco**, com teste que tenta pelo ORM direto e falha. |
| BL-77 | **Saldo apresentado com natureza (`D`/`C`), nunca negativo** (RC-61). Hoje as saídas devolvem um número que pode vir negativo; o balanço que o contador lê traz valor absoluto com o indicador ao lado, e a conta retificadora com `(-)` no nome. | `desenvolvedor-pleno` com `especialista-frontend` | rodada 2 da DL-015 integrada | planejada | Cada saldo nas saídas traz valor absoluto e a natureza do saldo apurado; teste com conta credora, conta devedora e grupo com retificadora, conferindo os dois campos. **Caso de referência obrigatório** (balanço enviado pelo Fred, conferido por cálculo): grupo com 1.437,50 D + 29.900,00 D − 2.074,18 C resulta em **29.263,32 D**. |
| BL-76 | **Paginação e limite de volume nas saídas contábeis.** Achado 14 da auditoria: nenhuma das quatro saídas tem paginação. Um Diário anual de empresa movimentada é uma resposta única e completa em memória. Vira problema real na tela (BL-62) e no Razão consolidado de grupo (DE-020). | `arquiteto-senior` define o contrato; `especialista-frontend` e `desenvolvedor-pleno` implementam | BL-62 | planejada | Paginação nas três saídas de período, com o total do período **sempre completo**, nunca só da página exibida — um rodapé que some apenas a página é pior que não ter rodapé. Teto de consultas por página medido em teste. |
| BL-74 | **Configuração contábil da classificação de operação e dos impostos.** Levantado em 2026-09-13: a conta do lançamento gerado não vem do produto nem do participante — vem da **classificação da operação** (contas do valor principal, frete, seguro, despesas, parcelas) somada ao **cadastro de cada imposto** (contas de a recolher e a recuperar). É o que torna a integração fiscal→contábil possível. | `desenvolvedor-pleno` | BL-72, e a existência do módulo fiscal (DL-010) | planejada | Classificação de operação com vigência e configuração contábil própria; configuração contábil por imposto; conferência que lista operações e impostos **sem conta configurada** antes de qualquer geração — gerar lançamento pela metade é pior que não gerar. |
| BL-75 | **Histórico como modelo com variáveis.** O texto do lançamento gerado vem de modelo preenchido com dados do documento (número, participante, valor, data), não de texto fixo. | `desenvolvedor-pleno` | — | planejada | Modelo de histórico com variáveis declaradas; serviço que resolve o modelo na geração; variável inexistente no contexto é erro explícito, nunca texto cru no livro; teste com todas as variáveis e com uma inválida. |
| BL-73 | **Alterar lançamento de origem automática exige permissão própria.** Levantado em 2026-09-13 no material de referência e adotado por ser bom desenho: no sistema de referência, editar ou excluir lançamento vindo de outro módulo depende de uma permissão específica, distinta da de lançar. Faz sentido: quem digita não deveria, por acidente, desfazer o que a escrita fiscal gerou — e um lançamento alterado à mão é justamente o que a regeração não pode atropelar. | `desenvolvedor-pleno` | BL-72 | planejada | Permissão própria para alterar ou excluir lançamento de origem automática, verificada **no servidor**; sem ela, 403 e nada muda; lançamento de origem automática que tenha sido alterado fica marcado como tal, e a regeração (BL-66) o preserva por padrão. |
| BL-67 | **Centro de custo e departamento** (RC-54, RC-55). Cadastro, com habilitação por empresa **a partir de uma data** — habilitar não altera lançamento já gravado. | `desenvolvedor-pleno` | BL-59 | planejada | Departamento e centro de custo por empresa; parâmetro de habilitação com data de início; lançamento anterior à data não é afetado; isolamento entre empresas testado. |
| BL-68 | **Rateio por centro de custo definido na conta** (RC-55): percentuais vinculados à conta contábil, propostos no lançamento e materializados na partida. | `desenvolvedor-pleno` | BL-67 | planejada | Percentuais da conta somam exatamente 100%; o rateio gravado no lançamento soma **exatamente** o valor da partida, sem centavo perdido — a diferença de arredondamento tem destino definido e testado (DE-010); alterar o percentual da conta **não** altera lançamento já gravado. |
| BL-69 | **Saídas filtráveis por centro de custo** (RC-55): Diário, Razão, Balancete e, quando existirem, Balanço e DRE. | `desenvolvedor-pleno` | BL-68 | planejada | Filtro por um ou vários centros de custo; a soma dos valores de todos os centros de custo de um período é igual ao total do mesmo período sem filtro; contas sem rateio têm tratamento explícito e declarado na resposta. |
| BL-70 | **Numeração dos livros contábeis** (RC-56). Livro numerado tem sequência controlada, sem buraco e sem repetição, por empresa e por tipo de livro. | `desenvolvedor-pleno` | BL-61 | planejada | Número por empresa e tipo de livro, atribuído na emissão; sequência sem buraco e sem repetição sob concorrência (teste concorrente); um livro emitido não muda de número; teste que prova a recusa de dois livros com o mesmo número. |
| BL-71 | **Termo de abertura e encerramento** do livro, vinculado ao livro que ele abre e encerra. | `desenvolvedor-pleno` | BL-70 | planejada | Termo referencia número do livro, período e páginas consistentes com o próprio livro; não existe termo sem livro correspondente; teste de coerência entre os dois. |

## P0 — BLOQUEADOR EM VIGOR: a tela grava `1.000` como `1,00`

Achado **R2-1** da [auditoria DL-017 rodada 2](../auditorias/2026-09-14-dl-017-rodada-2.md).
**Está na `main`**, em `9b22b03`, desde a integração do PR #18 — não é regressão
da correção da rodada 1. Precisa estar fechado **antes de existir dado real de
cliente**, e o Fred foi avisado de que o sistema no ar dele tem o defeito.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-103 | **A tela grava um número diferente do que o contador digitou.** `_decimal_do_formulario` só remove o separador de milhar **quando há vírgula**: `1.000` vira `Decimal("1.000")`, que é 1. Medido em 9 de 12 valores de milhar comuns — `1.000`→1,00, `1.500`→1,50, `10.000`→10,00, `150.000`→150,00, `2.500`→2,50. A tela responde "Lançamento gravado com sucesso"; **nada reclama**, porque os dois lados sofreram a mesma divisão: o lote fecha, o balancete concilia, a conferência não acusa. | `especialista-frontend` | **DE-029** | **corrigida na branch de trabalho**, aguardando rodada 3 | Gramática pt-BR explícita da DE-029 (`^[+-]?([0-9]+\|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]{1,2})?$` — **`[0-9]`, nunca `\d`**, ver R3-6); texto fora dela **recusado** com mensagem que ensina o formato, nunca reinterpretado. `10.00` passa a ser recusado, e isso é correto. **E o teste que a DE-029 institui: texto digitado → valor gravado**, com a tabela de 12 valores — nunca 302 com outro número. |
| BL-104 | **Reescrever a DE-027 e instituir o teste que faltava.** A cláusula de tradução (*"separador de milhar sai"*) não corresponde ao que o código fazia nem ao que deve fazer, e corrigir o código para bater com ela seria pior (tiraria o ponto de `10.00`). A verdade que faltava: **`1.000` é ambíguo**, logo "tradução de locale" não é operação bem definida sobre ele. Pior: o teste de equivalência que a DE-027 institui **não pode pegar um defeito na tradução**, porque compara os dois lados depois dela. | `arquiteto-senior` | — | **feita** — [DE-029](decisoes.md), com aviso no topo da DE-027 | A gramática escrita como padrão, não como prosa; a regra de que **texto ambíguo se recusa**; e o teste "texto digitado → valor gravado" como obrigação, ao lado do de equivalência. |

## P0 — o primeiro acesso de uma instalação nova só existe pelo admin técnico

Encontrado **pelo Fred**, na máquina dele, em 2026-09-14, logo depois de o Docker
subir e de ele criar o usuário. Não veio de auditoria: veio de uso — como BL-100.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-125 | **Uma instalação nova não tem como começar a ser usada pelo produto.** Depois de `createsuperuser`, o Fred entrou e recebeu *"Nenhum escritório ativo — seu usuário não tem vínculo ativo com nenhum escritório"*. A tela está **correta** (explica e oferece o caminho de volta; é o estado vazio da DL-009 funcionando), mas o único jeito de sair dali é o **admin do Django**: criar `Escritorio`, criar `VinculoUsuarioEscritorio` com papel `ADMINISTRADOR`, e só então cadastrar empresa. Admin do Django é ferramenta técnica, não produto — e é o mesmo admin que BL-83 aponta como bloqueador de implantação por permitir mover conta com movimento. | `especialista-frontend` + `desenvolvedor-pleno` | DL-017 fechar | **planejada** — [DL-018](../planos/DL-018-primeiro-acesso.md), com três perguntas ao Fred antes de desenhar | **A classe é:** todo estado inicial alcançável por instalação limpa tem saída **pelo produto**, sem admin técnico e sem linha de comando além de subir o sistema. *Exemplo*: usuário sem vínculo consegue criar o primeiro escritório e tornar-se administrador dele pela interface; a partir daí, cadastrar empresa e usar a contabilidade. Teste que percorra instalação limpa → primeiro escritório → primeira empresa → primeiro lançamento **sem tocar em `/admin/`**. |

### Por que isto não apareceu em nenhuma das três rodadas

As três auditorias verificaram a DL-017 com **cenário já montado** — escritório,
empresa e vínculo criados pela fixture do teste. O estado "banco recém-criado,
um usuário, nada mais" **não é cenário de teste de nenhuma delas**, e é o
primeiro que um cliente encontra. O critério 13 pede vazio, erro, sucesso e sem
permissão "com saída navegável"; aqui a saída existe e é navegável — leva ao
admin técnico. Fica registrado como limite de método: **estado inicial de
instalação é um estado da interface**, e precisa entrar nos critérios das
próximas etapas.

## P0 — achados da rodada 5 da DL-017

Relatório integral em
[docs/auditorias/2026-09-14-dl-017-rodada-5.md](../auditorias/2026-09-14-dl-017-rodada-5.md).
**Os 12 achados da rodada 4 estão todos fechados**, medidos por mutação do
auditor — inclusive dois que sobreviviam havia três rodadas. E a dimensão
**concorrência real** foi varrida pela primeira vez: a contabilidade **passou
inteira** (8 requisições simultâneas com a mesma chave → 1 lançamento; 2 estornos
simultâneos → 1 estorno; 10 lançamentos concorrentes → balancete fecha exato).

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-140 | **BLOQUEADOR — a CI da revisão auditada está vermelha, e a causa fui eu.** Instalei `chromium-browser` no workflow (BL-119); no `ubuntu-noble` esse pacote tem 50 kB e é um **invólucro que instala o snap**. O snap roda confinado, com `/tmp` privado, e não enxerga o arquivo que a medição escreve: o navegador renderiza a página de erro, cujo `<title>` é a própria URL, e o `json.loads` estoura. Medido em `526a51db`: **`2 failed, 681 passed`**, e **zero `skipped`** — a instalação transformou dois testes pulados em dois **falhando**, que é pior que o estado que ela pretendia corrigir. Junto: `_chromium_funciona` verifica a capacidade com URL `data:` enquanto a medição usa `file://` — **a checagem não exercita o mecanismo que falha**. | `especialista-frontend` (instrumento) + `arquiteto-senior` (workflow) | — | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhuma falha de recurso externo de ambiente reprova a suíte, e nenhuma checagem de capacidade deixa de exercitar o mecanismo que ela protege. *Exemplos*: a checagem renderiza um **arquivo via `file://`**, não uma URL `data:`; o `json.loads` cai no mesmo `pytest.skip` (título não-JSON é ambiente quebrado, não regressão de CSS); o check `Lint e testes` fica **verde**, com os dois testes rodando **ou** pulando com motivo no `-rs`. E o critério da BL-119 passa a ter **três** desfechos. |
| BL-141 | **ALTA — o campo `regime` do regime tributário não tem gramática nenhuma.** Aceita lista, dicionário, número e booleano, **grava o lixo no banco e devolve na listagem** (`GET /empresas/api/empresas/` responde `"regime_atual":"{'a': 1}"`); `"SIMPLES_NACIONAL"` e `" simples_nacional "` entram fora das `choices`; texto de 500 caracteres dá **500**. É a **mesma função** cujo outro campo (`vigencia_inicio`, a linha de baixo) foi consertado nesta rodada pela BL-133. O regime tributário governa toda a apuração fiscal de um cliente. | `desenvolvedor-pleno` | DE-034 | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhum campo de domínio fechado aceita valor fora do domínio, e nenhum produz 5xx. *Exemplos*: os sete casos medidos devolvem 400 com a lista de opções; `"simples_nacional"` continua 201 gravando exatamente isso. **E a varredura vale para todo `request.data.get(...)` que alimente `choices` no repositório.** |
| BL-142 | **ALTA — na API, o `conta` do item vai direto ao ORM sem `para_id`.** Medido: `1.9` grava **na conta 1**; `true` grava na conta 1; `"٢"` grava **na conta 2**; `" 1 "` e `"+1"` idem — todos **HTTP 201, em silêncio**. Mesma coisa em `conta_pai` do serializer. É a assinatura do BL-139 (data errada) aplicada à **conta**: o lote fecha, nenhuma conferência aponta, e o Diário mostra um fato que ninguém escreveu. **Agravante:** dois comentários de `views_web.py` afirmam que "a API já usa `para_id`" — e `para_id` **não aparece uma vez** em `apps/contabilidade/views.py`. O comentário afirmou justamente a coisa que impediu de olhar. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhuma entrada de cliente é reinterpretada em silêncio para um identificador diferente do escrito, **em nenhuma superfície**. *Exemplos*: os seis casos medidos devolvem 400; `1` e `"1"` continuam 201 na conta 1; teste comportamental que suste `para_id` e exija que a API passe a recusar. **E os dois comentários falsos corrigidos.** |
| BL-143 | **A gramática de data da TELA não é defendida por teste nenhum** — três mutantes sobrevivem a 683 testes. Efeito medido na cópia mutada: `data="2026-W01-1"` → **302 "gravado com sucesso"**, lançamento com data `2025-12-29`. **É o BL-139 inteiro, na tela.** Hoje o código está certo; o que não existe é qualquer teste que o segure. Agravante: o comentário justifica a cópia privada citando `apps.contabilidade.views._PADRAO_DATA_SIMPLES`, **símbolo que a BL-133 removeu** — a divergência já está impressa no comentário. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** cada julgador de dado tipado tem um só dono, e cada uso dele é defendido por teste que alguém viu falhar. *Exemplos*: a tela usa `apps.core.datas.para_data` nos três pontos e a cópia privada some; MX4, MX9 e MX10 passam a matar ao menos um teste cada. |
| BL-144 | **Restrição de banco vira 500 na API, e sob concorrência três de uma vez.** `codigo` de conta repetido → **500**; segunda matriz → **500**; 4 criações simultâneas da mesma conta pela API → **`500, 201, 500, 500`** (pela tela: `200,200,200,302`, **1 conta, nenhum 500**). O dado **nunca** foi violado — a constraint segura. O que quebra é a resposta. **Agravante:** `EstabelecimentoListCreateView` já envolve a gravação em `erro_de_cnpj_duplicado_como_400()` — a defesa existe na mesma função, para a unicidade de CNPJ, e não para a constraint declarada quatro linhas abaixo. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhuma violação de invariante declarada no modelo chega ao cliente como 5xx. *Exemplos*: os três casos devolvem 400 com mensagem de negócio; as 4 simultâneas devolvem `201, 400, 400, 400`. **E uma varredura, no molde da BL-134: para cada `Meta.constraints` existe caminho de API que a converte em 400.** |
| BL-145 | **O que sobrou da classe BL-128: querystring num POST, e a chave de idempotência na superfície errada.** Querystring com um par completo de partidas num POST de lançamento → **302 "gravado", 2 itens** — nem lida nem recusada, quinto dicionário da requisição. E quem manda `Idempotency-Key` por cabeçalho **na tela** (ou `chave_idempotencia` no corpo **na API**) recebe **duplicidade**, sem aviso — exatamente o que o critério 11 existe para impedir. Assimetria: a tela recusa campo desconhecido, a API aceita e ignora. | `especialista-frontend` + `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhum dado enviado numa requisição deixa de ser lido ou recusado, **em nenhuma superfície e em nenhum dicionário**. *Exemplos*: querystring não vazia no POST do lançamento recusa nomeando a chave; a política da chave de idempotência é a mesma nas duas superfícies; campo desconhecido recusado também na API. |
| BL-146 | **Comentário que afirma "o mesmo julgador que X usa" vira afirmação verificável.** Oitava ocorrência da família nesta etapa, e a primeira em que o comentário **causou** a lacuna (BL-142) em vez de só descrevê-la mal. | `especialista-frontend` | BL-142 | **corrigida na branch de trabalho**, aguardando rodada 6 | **A classe é:** nenhuma afirmação de comentário sobre uso de julgador partilhado fica sem verificação. *Exemplo*: teste que, para cada frase do tipo "o mesmo julgador que X usa", confirme que X de fato o usa — se não usa, reprova. |
| BL-147 | **R5-7: o check "Regras do projeto" continua vermelho, com as três anotações idênticas às da rodada 4.** Terceira ocorrência. | `arquiteto-senior` | — | **corrigida na branch de trabalho**, aguardando rodada 6 | Corpo do PR com atestado de leitura, caixa de estado e referência `DL-017`. |

### BL-140 e a regra que eu escrevi e não apliquei

A **BL-137** está marcada "em vigor" desde a rodada 4 e diz, com todas as
letras: *"antes de declarar verificação, **ler os checks da revisão no
GitHub**, não só rodar a sequência local."* Meu relatório de entrada da rodada 5
declarou "683 passed", listou a sequência do workflow e **não mencionou os
checks** — que estavam vermelhos em dois lugares. O auditor leu, e é de lá que
saiu o bloqueador.

O diagnóstico é o meu próprio, devolvido: **regra sem gancho é a mesma coisa que
decisão sem tarefa** — foi o que eu disse da DE-031 na rodada 4, e que originou
a DE-033. Passa a valer com gancho: **nenhum relatório meu declara verificação
sem colar o resultado de `check-runs` da revisão.** Não é lembrete; é conteúdo
obrigatório do relatório, como a contagem de testes já é.

### O que a DE-034 rendeu na estreia, e um décimo teste que não conseguia falhar

A **DE-034** (a varredura começa no campo, não na linha) foi aplicada pela
primeira vez nesta rodada, e os dois implementadores a levaram além do pedido:

- O `desenvolvedor-pleno` migrou também o `tipo` de `_extrair_itens` para o
  julgador de escolha — *"era uma segunda cópia manual do mesmo padrão, correta
  por acidente de forma"*. Ninguém pediu.
- Criou o **quarto e o quinto módulos julgadores** (`apps/core/escolhas.py` e
  `apps/core/restricoes.py`), completando o desenho que começou em
  `dinheiro.py`: nenhuma camada interpreta dado tipado de cliente, e nenhuma
  violação de invariante do modelo chega ao cliente como 5xx.
- O `especialista-frontend` acrescentou `_DIAGNOSTICO_CHROMIUM`, que **não foi
  pedido** e é o melhor item da entrega dele: a mensagem de pulo passa a
  carregar a causa real (timeout, código de saída, `stderr`, marca ausente).
  Ele **se recusou a chutar** qual dos quatro navegadores do runner usar sem
  esse dado — que é exatamente a disciplina que faltou a mim antes de instalar
  o snap.

**E o décimo teste que não conseguia falhar**, encontrado pelo
`desenvolvedor-pleno` na própria bateria dele, registrado aqui porque é o mais
sutil dos dez:

> Os testes do BL-142 usavam o inteiro literal `1` para dizer "a conta 1". O
> banco de teste é compartilhado por toda a suíte e a sequência de chaves do
> PostgreSQL **não reseta entre testes** — então, rodando o arquivo inteiro,
> `pk=1` já tinha sido consumido por outra empresa. A "reinterpretação" que o
> teste queria pegar caía em `DoesNotExist`, **mascarada como recusa correta**,
> e o mutante **sobrevivia por engano**. Ele reescreveu todos os casos amarrados
> ao PK **real**, inclusive traduzindo dígito ASCII → fullwidth do PK real.

É a mesma família do `override_settings` da rodada 3: **evidência positiva que
depende da ordem de execução**. Ele achou sozinho, corrigiu e declarou.

## P1 — achados da rodada 4 da DL-017

Relatório integral em
[docs/auditorias/2026-09-14-dl-017-rodada-4.md](../auditorias/2026-09-14-dl-017-rodada-4.md).
**Primeira rodada sem bloqueador e sem achado de gravidade alta.** O que reprova
são critérios ainda não atendidos, todos médios ou baixos.

As classes abaixo estão escritas pelo **efeito proibido**, não pelo mecanismo
(DE-032) — é a correção da redação que fez BL-115 e BL-116 fecharem o caso e não
a classe.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-126 | **A1: `conta_id` com mais de 4300 dígitos derruba a gravação com HTTP 500**, e dígito Unicode (`７`) é reinterpretado como a conta 7. `isdigit()` + `int()` sem `try`. Confirmei por medição: `int("9"*4301)` levanta `ValueError` pelo limite do Python, e `"９".isdigit()` é `True`. **É a mesma classe que o R2-2 fechou para o campo `nivel` — e a lição está escrita 300 linhas acima, no mesmo arquivo.** | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhuma entrada de cliente produz resposta 5xx, e nenhuma é reinterpretada em silêncio para um valor diferente do escrito. *Exemplo*: `"9"*4301`, `"9"*6000`, `"７"`, `"٢"` em `conta_N` devolvem 400 — nunca 500, nunca 302 com outra conta. **E a varredura vale para todo o repositório**, não para este campo: onde houver conversão de texto de cliente para número, vale a mesma regra. |
| BL-127 | **A2: `escritorio_id` com mais de 4300 dígitos derruba a troca de escritório com HTTP 500.** Mesma classe do BL-126, em `apps/tenancy`. Agravante: o comentário logo acima **justifica** a escolha de `isdigit()` "para não depender de exceção" — e é essa escolha que cria o 500. Quinta ocorrência na etapa de comentário que afirma mais do que a defesa entrega. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** a mesma do BL-126, e os dois se resolvem pela mesma varredura. *Exemplo*: `"9"*6000` e `"９"` devolvem mensagem de erro e redirecionamento, nunca 500 e nunca aceitação. |
| BL-128 | **A3: a classe do achado 5 pela QUARTA vez — uma linha enviada como campo de arquivo some em silêncio, com 302 de sucesso.** Par completo e balanceado (500,00 D + 500,00 C) em `multipart/form-data`: grava 2 itens de 10,00, os 500,00 somem da tela e do total, e o aviso do R2-5 **não dispara** (a linha não é incompleta, é invisível). Confirmei: `request.FILES` aparece **zero vezes** em `views_web.py`. Junto: `CONTA_3`/`Conta_3` ignorados em silêncio, e `conta_1` em dígito fullwidth reinterpretado. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhum dado enviado numa requisição deixa de ser lido ou recusado — a política vale para a **requisição inteira**, não para um dicionário dela. *Exemplo*: qualquer chave em `request.FILES` recusa o POST nomeando-a; a tabela do achado devolve 4 partidas gravadas **ou** 400, nunca 302 com 2. |
| BL-129 | **A4: o teste que mede a condição de pulo do navegador não consegue falhar.** `assert _CHROMIUM_FUNCIONAL in (True, False)` é tautologia, e o mutante que devolve a condição à forma que derrubou a CI em `aa10f20` **sobrevive a 608 testes**. A correção mais delicada desta rodada está indefesa — e é citada nominalmente no plano como uma das que foram consertadas. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhuma condição que decida entre medir e pular passa sem teste que a veja falhar. *Exemplo*: par estrutural + comportamental (a regra que o plano já adotou para autorização); o mutante MH mata ao menos um teste. |
| BL-130 | **A6: dois testes do BL-115 falham PENDURANDO, não reprovando.** Sob o mutante, a suíte não retorna em 4 min; na primeira execução rodou 10 min, foi morta, e a sessão pendurada travou o banco de teste e envenenou a execução seguinte. Na CI isso vira estouro de `timeout-minutes` com uma causa que não se parece com a causa — a armadilha do `aa10f20` outra vez. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhum teste tem "pendurar" como modo de falha. *Exemplo*: medir a **propriedade** (a chave acima do teto não foi lida) em vez da duração de uma chamada ilimitada; ou teto de tempo que interrompa. |
| BL-131 | **A5: a DE-031 foi decidida e não executada.** Sete rótulos ainda dizem `(dd/mm/aaaa)` num campo cujo formato o navegador controla, e a captura entregue mostra `09/01/2026` embaixo deles. **Erro meu, de processo, não de medição**: registrei a decisão e não a transformei em tarefa. Origem da DE-033. | `especialista-frontend` | DE-031 | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhum texto de interface afirma um comportamento que o sistema não controla. *Exemplo*: rótulo nomeia o campo sem prometer formato, com apoio dizendo que o campo segue o navegador; teste que reprove rótulo afirmando formato de `<input type="date">`. |
| BL-132 | **A8: o mutante `\d` continua sobrevivendo.** O texto da DE-029 foi corrigido (R3-6 fechado nessa metade), o teste da primeira camada continua planejado, e o mutante sobrevive a 608 testes — idêntico ao M6 da rodada 3. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** cada camada de uma defesa em profundidade é testada **sozinha**. *Exemplo*: teste que afirme que a gramática pt-BR recusa dígito Unicode sem a ajuda de `para_decimal`; o mutante MM morre. |
| BL-133 | **A9: gramática de data ausente em `apps/empresas` — reinterpretação silenciosa e um 500.** `"2026-W01-1"` é gravado como `2025-12-29`; `20260101` como número JSON devolve **500**. É o R3-3 inteiro, com "número JSON" e tudo, num campo de data — a contabilidade resolveu isso na rodada 1 e a regra nunca atravessou para `empresas`. | `desenvolvedor-pleno` | DE-030 estendida (BL-135) | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhum dado tipado recebido de cliente é interpretado sem gramática declarada, e nenhum produz 5xx. *Exemplo*: padrão estrito antes de `fromisoformat`, capturando `ValueError` **e** `TypeError`; os quatro casos medidos devolvem 400 ou o valor exato. |
| BL-134 | **A10: a BL-121 fechou o caso; a classe "nenhuma `APIView` depende do padrão global" não tem verificação.** Hoje as 14 do repositório declaram permissão; a décima quinta não será detectada. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 5 | **A classe é:** nenhuma rota fica autorizada por omissão. *Exemplo*: varredura de subclasses de `APIView` exigindo `permission_classes` no `__dict__` de cada uma. |
| BL-135 | **Estender a DE-030 a dado tipado, não só a valor monetário.** A DE-031 nomeou o buraco da data e o **adiou** ("se o Fred relatar confusão real"). O A9 mostra que já existe caminho gravando data reinterpretada hoje — não é questão de rótulo de tela. | `arquiteto-senior` | — | planejada | Decisão reescrita cobrindo **todo dado tipado** de entrada (data, inteiro, booleano), com a regra de que cada caminho declara sua gramática antes de existir código — inclusive os da DL-010. |
| BL-136 | **A revisão e a árvore que eu publico saem de `git rev-parse` DEPOIS do commit.** Declarei `b271e9bf` para `d046baf`, cuja árvore é `9e2cf35a` — **segunda ocorrência idêntica**, mesma causa (medir antes do commit final de documentação). O auditor conferiu que a diferença era só documentação e que a medição valia, mas isso é sorte, não método. | `arquiteto-senior` | — | **em vigor** | Nenhum relatório meu cita revisão ou árvore que não tenha saído de `git rev-parse HEAD` / `HEAD^{tree}` executados **após** o commit que está sendo declarado. |
| BL-137 | **A7: "a sequência inteira da CI está limpa" não era verdade.** Rodei a sequência **local** — que inclui `makemigrations --check`, ausente do workflow — e não li os **checks do commit**, onde "Regras do projeto" estava vermelho. Foi lendo o log real que o auditor obteve a resposta da BL-119, que eu tinha deixado em aberto por falta desse dado. | `arquiteto-senior` | — | **em vigor** | Antes de declarar verificação, **ler os checks da revisão no GitHub**, não só rodar a sequência local. E o corpo do PR precisa do atestado de leitura, da caixa de estado e da referência `DL-017`. |

### Dois gêmeos que a auditoria não achou, e como apareceram

A **DE-032** (classe escrita pelo efeito proibido) foi aplicada pela primeira
vez ao escrever BL-126 a BL-137. O resultado é o argumento mais forte a favor
dela: procurando **o efeito** em vez da linha apontada, o `desenvolvedor-pleno`
encontrou dois defeitos da mesma classe que **quatro rodadas de auditoria não
tinham encontrado**.

| ID | O que era | Gravidade real |
| --- | --- | --- |
| BL-138 | `EscritorioAtivoView.post` — a porta da **API**, mesmo arquivo do A2 — mandava `escritorio_id` direto ao ORM sem checagem. Um id de 6000 dígitos como texto JSON derruba com `ValueError` dentro do ORM, **500 cru**. | Igual ao A2 |
| BL-139 | `LancamentoListCreateView.post` — `date.fromisoformat(dados["data"])` **sem a gramática estrita que `_periodo_obrigatorio`, no mesmo módulo, já aplicava** a `inicio`/`fim`. Medido: `"data": "2026-W01-1"` gravava um **lançamento contábil com a data errada**, em silêncio. | **Maior que os achados do relatório**: não é 500, é escrituração com data que ninguém escreveu, e nenhuma conferência apontaria |

Os dois estão **corrigidos na branch**, pelos módulos julgadores novos
(`apps/core/identificadores.py`, `apps/core/datas.py`), com mutação aplicada,
medida e desfeita.

**BL-139 merece nota de método.** Ele existia porque a lição de gramática de
data foi aplicada, na rodada 1, **ao campo que o relatório nomeou** (`inicio`,
`fim`) e a nenhum outro — inclusive não ao campo de data do próprio lançamento,
dez linhas abaixo, no mesmo arquivo. É o padrão que a DE-032 descreve, visto
retroativamente: a correção de 2026-09-11 fechou o caso e não a classe, e
passou por quatro auditorias sem ser notada.

### A duplicação de julgador, e por que ela NÃO foi unificada até o fim

O `especialista-frontend` resolveu o `conta_id` com um julgador local e depois
o fez **delegar** a `para_id`, como eu ia pedir. Mas parou num ponto, e a razão
é boa: `_inteiro_de_cliente`, usada para **quantidade de negócio**
(`num_linhas`, `nivel`, índices de linha), **não** delega — porque BL-115
depende de conhecer a **magnitude real** de um texto de até 4300 dígitos para
aplicar a regra "no máximo 20 partidas", e `para_id` recusa qualquer coisa
acima de 19 dígitos sem distinguir 20 de 4000.

Ele descobriu isso **porque um teste da rodada 3 quebrou** na primeira tentativa
de delegação total, e reverteu antes de entregar. Aceito o desenho: são duas
invariantes diferentes — **identificador** e **quantidade** — e nomear a
diferença no nome da função é mais honesto que um parâmetro que só quem lê o
corpo entende.

## P0 — achados da rodada 3 da DL-017

Relatório integral em
[docs/auditorias/2026-09-14-dl-017-rodada-3.md](../auditorias/2026-09-14-dl-017-rodada-3.md).
O bloqueador da rodada 2 **fechou** — 55 textos medidos, valor gravado igual ao
significado pt-BR ou 400, nunca 302 com outro número — e dez das onze correções
estão fechadas por medição do auditor. O que reprova é um achado **novo, criado
pela própria correção da rodada 2**.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-115 | **ALTA — um POST prende a requisição indefinidamente.** A correção do R2-10 (repetir ao contador os valores que não couberam) passou a chamar a leitura de linhas **antes** de recusar, com um contador vindo do cliente e **sem teto**. Medido pelo auditor: `num_linhas=1000000` → 2,6 s; `10000000` → 26 s; `10**12` → **não volta** (nada em 45 s). Confirmei por medição própria: 1 milhão de iterações em 0,85 s, linear, sem teto — o único limite é o do `int()` do Python, 4300 dígitos. `num_linhas` é **campo oculto do próprio formulário**. O `CMD` do `Dockerfile` é `gunicorn` **sem `--workers`**: um worker síncrono, e é o mesmo comando do `docker-compose.yml`, o caminho pelo qual o Fred sobe o sistema. Não corrompe dado: **nega o serviço**. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 4 | **A classe é:** nenhum número vindo do cliente dimensiona laço, alocação ou repetição — em nenhum ramo desta view. *Exemplo* (não definição): `10**12` e `"9"*4000` devolvem 400 em menos de um segundo, nos ramos `gravar` **e** `adicionar_linha`, com o teste **cronometrando**. Recusa antes de qualquer leitura, coerente com "recusa, nunca ajusta". Revisar todo `range()` dimensionado por entrada. |
| BL-116 | **A classe do achado 5 continua aberta: índice de linha fora do canônico é descartado em silêncio, com 302 de sucesso.** Três mecanismos, o mesmo dano: índice com 5+ dígitos não casa `[0-9]{1,4}`; `01`/`0001` casa mas `int()` normaliza para outra chave; `0` fica fora do `range`. Medido: par completo de 77,00/77,00 em `conta_10000`, `conta_0`, `conta_01`, `conta_0001` → **302 "gravado com sucesso", 2 partidas, 10,00**. Na conferência é pior: o rodapé mostra os dois lados batendo, o aviso do R2-5 **não dispara** (a linha não é incompleta, é **invisível**) e os valores somem da tela. **E o docstring afirma o contrário do que o código faz** — terceira ocorrência nesta etapa. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 4 | **A classe é:** nenhuma linha enviada no POST deixa de ser lida, e o que não for entendido é **recusado**, nunca ignorado. *Exemplo*: qualquer chave `conta_*`/`tipo_*`/`valor_*` fora do índice canônico devolve 400 **nomeando a chave**; teste com `0`, `01`, `0001`, `10000`, `99999` e sufixo não numérico — 4 partidas gravadas **ou** 400, nunca 302 com 2. Docstring corrigido. |
| BL-117 | **A API grava valor diferente do enviado quando `valor` vem como número JSON** (R3-3). `99999999999999.99` → gravado `99999999999999.98`, HTTP 201. E `1e3` como **texto** é recusado, como **número** é aceito e vira 1.000,00 — a recusa que o comentário anuncia é contornada trocando aspas por número. A API **não chama `para_decimal`**: reimplementa a checagem e constrói o `Decimal` sozinha. | `desenvolvedor-pleno` | **DE-030** | **corrigida na branch de trabalho**, aguardando rodada 4 | **A classe é:** nenhuma camada constrói `Decimal` a partir de entrada de cliente, e valor monetário que chegue como número (não texto) é recusado na fronteira. *Exemplo*: os quatro valores medidos devolvem 400, e uma verificação de que `views.py` não constrói `Decimal` a partir de entrada de cliente. |
| BL-118 | **A tela não compila em Python 3.12 nem 3.13, e o `README.md` promete "Python 3.12+"** (R3-4). `except TypeError, ValueError:` é PEP 758, exclusiva do 3.14. Confirmei por medição própria: `python3.12` e `python3.13` recusam o arquivo com `SyntaxError`. Quem seguir o README com 3.13 não recebe erro compreensível — **o site inteiro não sobe**, não só a contabilidade. Nada detecta: a CI roda 3.14, o `Dockerfile` é 3.14, e o `pyproject.toml` **não declara `requires-python`**. Está na `main` desde `9b22b03`. | `desenvolvedor-pleno` (código) + `arquiteto-senior` (declaração) | — | **corrigida na branch de trabalho**, aguardando rodada 4 | **A classe é:** versão mínima declarada e **verificada**, nunca só prometida. *Exemplo*: ou `requires-python = ">=3.14"` com README e `decisoes.md` alinhados, ou `except (TypeError, ValueError):` mantendo 3.12+; e verificação na CI que compile todos os `.py` na versão mínima declarada. |
| BL-119 | **Chromium na integração contínua** (R3-5). Minha decisão, registrada na rodada 2 como "em aberto" e agora com medição: a defesa textual da BL-114 detecta **a forma do ME2**, não o efeito. O auditor quebrou o efeito por outra via (`!important` numa regra posterior): com navegador, 1 teste morre; **sem navegador, zero em 559**. A hierarquia já sumiu **duas vezes** nesta entrega, por formas diferentes. | `arquiteto-senior` | correção da CI pelo `especialista-frontend` | **aguardando evidência** | Chromium **funcionando** na CI e os testes de efeito **rodando lá**, não pulados. Até lá, **BL-114 é "estreitada", não "fechada"** — o vocabulário faz parte do critério. **Atualização de 2026-09-14, e ela muda o caminho:** a correção do vermelho da CI endureceu a invocação do navegador (`--no-sandbox`, `--disable-dev-shm-usage`, `--user-data-dir` próprio) e trocou a condição de pulo de *presença de binário* para *capacidade medida*. O runner do GitHub **já tem** `/usr/bin/chromium` — o que faltava não era instalar, era fazer subir. Então é possível que esta BL feche sozinha, sem nenhuma mudança em `.github/workflows/`. **Decidir por medição, não por suposição:** na próxima execução da CI, ler se os dois testes de efeito aparecem como `passed` ou como `skipped`. `passed` → fecha sem tocar no workflow. `skipped` → aí sim entra a instalação, e com o motivo do pulo em mãos, que é o que faltava para saber o que instalar. |
| BL-120 | **O teto de segurança de 200 só é seguro porque o teto de negócio é 20** (R3-9). `min(maior, 200)` descarta índices acima de 200 **em silêncio**; hoje nada se perde porque 200 > 20 faz a recusa de negócio disparar antes. Se o Fred responder PE-42 com um teto de 200 ou mais — resposta plausível —, a perda silenciosa volta **sem que nenhuma linha mude**. Acoplamento invisível entre duas constantes. | `especialista-frontend` | BL-116 | **corrigida na branch de trabalho**, aguardando rodada 4 | Recusar índice acima do teto em vez de capar, e uma verificação que **falhe** se `LINHAS_MAXIMAS_LANCAMENTO >= LINHAS_LEITURA_TETO_DE_SEGURANCA`. |
| BL-121 | **`permission_classes` explícito nas duas `APIView` de `tenancy`** (R3-10). São as únicas do repositório apoiadas no padrão global. Não há vazamento hoje — as duas consultam por `request.user` —, mas relaxar o padrão global para acrescentar uma rota pública tiraria a autenticação das duas sem que nenhuma linha delas mude. Classificado pelo auditor como **inspecionado, não testado**. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 4 | Permissão declarada em cada uma, com teste que prove a recusa anônima independentemente do padrão global. |
| BL-122 | **R3-6, meu:** a DE-029 publicava a gramática com `\d` enquanto o código usa `[0-9]`. Quem implementasse pelo documento reabriria o R2-7, e o mutante que faz isso **sobrevive a 559 testes**. | `arquiteto-senior`; teste com `especialista-frontend` | — | **texto corrigido** em DE-029 e BL-103; teste planejado | Falta o **teste da primeira camada**: hoje a gramática é defendida só por `para_decimal`, a segunda camada. Um teste que afirme que `_GRAMATICA_VALOR_PTBR` recusa dígito Unicode **sozinha**. |
| BL-123 | **R3-7, meu:** o `README.md` ainda descrevia estado na linha 39 — "auditada em 4 rodadas" ao lado do link para uma etapa reprovada duas vezes, com bloqueador vivo. | `arquiteto-senior` | — | **corrigida** | A coluna passa a dizer se a **capacidade** existe, em traço grosso, com nota explícita de que o estado de cada etapa vive só em `estado.md`. |
| BL-124 | **Processo, e é o achado mais incômodo da rodada.** A DE-029 diz, escrita por mim: *"o critério de aceite de uma correção cita a classe do defeito, nunca só a reprodução do relatório"*. **No mesmo commit**, escrevi o critério da BL-106 como *"a tabela de 8 valores devolve 6 partidas ou 400"* — a tabela do auditor, os oito valores dele. A correção passou nos oito e falhou em nove que ele não tinha medido (R3-2/BL-116). A regra certa não chegou ao backlog **na mesma sessão em que foi escrita**. | `arquiteto-senior` | — | **em vigor a partir de BL-115** | Nenhum item de correção entra no backlog sem uma frase começando por **"A classe é:"**, com a reprodução do relatório marcada como *exemplo*, nunca como definição. BL-106 fica guardada nominalmente como contraexemplo. Terceira vez que esta lição é escrita — lembrete já se provou insuficiente, por isso virou forma obrigatória do campo. |

## P1 — demais achados da rodada 2 da DL-017

O relatório integral está em
[docs/auditorias/2026-09-14-dl-017-rodada-2.md](../auditorias/2026-09-14-dl-017-rodada-2.md).
Dos 15 achados da rodada 1, **14 foram fechados** por medição do auditor e 21 de
22 mutantes morrem. Três fecharam **o caso descrito, não a classe nomeada** — e
é daí que vêm R2-3, R2-5 e R2-6.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-105 | **R2-2: `?nivel=` com mais de 4300 dígitos derruba o Balancete com 500**, por uma URL — que pode ser colada, favoritada ou compartilhada. E `nivel=٢` (dígito índico-arábico) é aceito como 2, quando a API recusa. A API **já documenta a lição** (`views.py:77-83`: usa `[0-9]`, não `\d`, e envolve o `int()` em `try/except`); a tela não copiou nenhuma das duas. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Mesmo padrão da API, **importado** e não duplicado; `int()` protegido. Os seis valores medidos pelo auditor devolvem o **mesmo** status na tela e na API. |
| BL-106 | **R2-3: o achado 5 só foi fechado por cima.** `num_linhas` malformado (`abc`, vazio, `2.5`, `1e1`, `None`) faz a view ler **4 de 6 linhas** e gravar com sucesso, descartando 77,00 de débito e 77,00 de crédito — o cenário exato do achado 5, com o mesmo dano. A causa não era o teto: **é a view confiar num contador enviado pelo cliente para decidir quantos campos ler.** Junto: o comentário de `views_web.py:638-641` afirma o contrário do que o código faz, e é ele que justifica a correção do achado 5. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Quantidade de linhas derivada do **próprio POST**; `num_linhas` só para exibição; recusa acima do teto mantida. A tabela de 8 valores devolve 6 partidas gravadas ou 400 — nunca 302 com 4. |
| BL-107 | **R2-4: byte `NUL` em `historico` ou `chave_idempotencia` chega ao INSERT e derruba com 500 — na tela E na API.** Não é regressão da DL-017: é buraco anterior que a varredura expôs. O formulário de conta está protegido porque é `ModelForm`; de novo o escrito à mão é o desprotegido. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | **Uma correção só** para as duas portas, numa camada que cubra ambas (validador de modelo ou `services.py`). 400 com mensagem útil, nunca 500 nem `IntegrityError` traduzido. Teste campo a campo, nas duas portas. |
| BL-108 | **R2-5: a conferência ainda exclui em silêncio uma linha incompleta do total.** Antes mostrava `0,00`, evidentemente errado; agora mostra um total **plausível e balanceado** que ignora 500,00 preenchidos logo acima — e "batendo" é o sinal que convida a gravar. Nada errado é gravado (a gravação recusa), mas a tela que existe para dar confiança dá confiança no número errado. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Soma parcial mantida **e a exclusão anunciada**: "N linha(s) ainda não entram neste total", ou marcação na própria linha. |
| BL-109 | **R2-6: a correção da indentação não tem teste que a defenda.** O mutante que reduz a especificidade do seletor — **a primeira tentativa, a que não corrigia nada** — sobrevive a 487 testes. O teste que existe verifica a ausência de `style=` inline, isto é, a **forma** da correção anterior, não o **efeito** desta. A hierarquia já sumiu duas vezes nesta mesma entrega, por motivos diferentes, com a suíte verde. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Teste que afirme o **efeito**: cada `nivel-N` com regra mais específica que `.tabela-dados td` e `padding-left` crescente, ou medição de `getComputedStyle` no Chromium. A mutação de especificidade passa a **morrer**. |
| BL-110 | **R2-7: `para_decimal` aceita dígito Unicode não latino como dinheiro** (`\d` em vez de `[0-9]`). `'０１０,00'` grava 10,00; `'١٢٣.٤٥'` é aceito como 123,45. Pesa mais do que parece: a DE-027 acabou de apontar **todo** caminho de entrada futuro para este módulo — tela, API, NFS-e da DL-010, carga de planilha. E a lição já está escrita no repositório, no guarda irmão `_PADRAO_NIVEL_SIMPLES`, com o comentário explicando o porquê. | `desenvolvedor-pleno` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | `^[+-]?[0-9]+(\.[0-9]+)?$`; os quatro textos medidos levantam `ValorMonetarioInvalido`. `+10.00` **continua aceito** — é contrato testado e a DE-027 depende dele. |
| BL-111 | **R2-8: a evidência do critério 16 não mostra o software entregue.** As três capturas são de `9b22b03`, o commit reprovado, e não têm nem os "—" das colunas consolidadas nem a indentação hierárquica. Continua faltando captura de "criar conta" e "lançar", os dois passos que o critério nomeia. | `especialista-frontend` | BL-103 a BL-109 | **corrigida na branch de trabalho**, aguardando rodada 3 | Capturas refeitas na revisão entregue, incluindo criar conta e lançar. Junto: texto de apoio no rótulo do campo de data — o `<input type="date">` mostra o formato do navegador, e na captura aparece `09/01/2026` logo abaixo de um cabeçalho dizendo `01/09/2026`. Não é defeito de código; é ambiguidade real para quem usa navegador fora de pt-BR. |
| BL-112 | **R2-9: a raiz do plano de contas fica 12 px à esquerda do próprio cabeçalho.** `nivel-0` e `nivel-1` zeram o recuo padrão da célula em vez de somar a partir dele; a escada fica −12, +8, +28, +48, +68 px, e o primeiro degrau mede 8 px em vez de 20. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Indentação **aditiva** sobre o recuo padrão da célula. Medido no Chromium. |
| BL-113 | **R2-10: a recusa por teto apaga as partidas digitadas.** A mensagem manda "grave em dois lançamentos separados" — e os dados do segundo acabaram de ser jogados fora pela mesma resposta. Uma linha acima, o código declara a intenção oposta. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 3 | Todas as linhas enviadas re-exibidas (marcando as excedentes), ou os valores que não couberam repetidos na mensagem. |

### BL-114 — a defesa da indentação era pulada justamente na integração contínua

Encontrado por mim, `arquiteto-senior`, ao revisar a entrega da rodada 2, e
devolvido ao responsável antes de integrar.

A correção do R2-6 veio com dois testes que medem o efeito real no navegador
(`getComputedStyle` no Chromium) — e é exatamente a medição que descobriu os
**dois** defeitos de indentação desta etapa. Só que os dois estavam marcados
para **pular quando não há navegador**, e `.github/workflows/` não instala
nenhum. Na integração contínua, os dois eram pulados e o mutante ME2 voltava a
sobreviver **no único lugar que decide se uma alteração entra**.

É o R2-6 de novo, um nível acima: *controle correto, sem teste onde importa*.
Honestidade sobre uma verificação ausente (o teste que garante que o pulo é
declarado, e não aprovação por omissão) não substitui a verificação.

Fechado com uma segunda rede, **sem navegador**: a folha de estilo é lida como
texto e o teste exige que toda regra `.nivel-N` tenha o prefixo de
especificidade, com passo aditivo e estritamente crescente. Medido por mim em
árvore limpa, com o `PATH` sem Chromium: sob ME2, **os três testes novos
falham**; desfeito o mutante, `sha256` idêntico e 559 aprovados. Os testes com
navegador continuam, porque medem o efeito e não a forma.

**Fica em aberto, e é decisão minha, não do implementador:** instalar Chromium
na integração contínua, para que a medição real também rode lá. Hoje o que roda
na CI é a defesa textual. Registrado para não passar como resolvido.

### R2-11, e por que o README parou de descrever estado

O auditor encontrou o `README.md` dizendo *"telas integradas, em correção de
auditoria"* contra o `estado.md` dizendo *"aguardando a rodada 2"* — divergência
**no primeiro commit depois** de o achado 7 ter sido corrigido. A causa é a mesma
que o Fred nomeou em 2026-09-13: **duplicação**. O roadmap do README passou a
declarar explicitamente que lista o que existe, nunca o estado, e aponta para a
fonte única. Feito pelo `arquiteto-senior`.

## P0 — o caminho documentado de subir o sistema não funcionava

Reproduzido **pelo Fred**, na máquina dele, em 2026-09-14, seguindo literalmente
o que o README manda. Não veio de auditoria: veio de uso.

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-100 | **`docker compose up --build` falhava com "container dataledger-db-1 is unhealthy"** num volume novo, com o banco perfeitamente saudável. Duas causas somadas, as duas no `docker-compose.yml`: (a) a verificação de saúde do PostgreSQL **não tinha `start_period`**, então as 5 tentativas de 5 s se esgotavam em ~25 s enquanto o `initdb` ainda rodava — levou **22 s** na máquina do Fred, contra pouco mais de 1 s na integração contínua, e por isso a CI nunca viu; (b) `pg_isready` sem `-h` fala pelo socket Unix, onde o `initdb` sobe um servidor **temporário** que é derrubado em seguida — podia aprovar o servidor errado. Junto, um terceiro defeito do mesmo caminho: o `CMD` da imagem é só o gunicorn, então **nenhuma migração rodava** e o banco subia sem tabela; a primeira tela devolveria erro de relação inexistente. | `arquiteto-senior` | — | **corrigida na branch de trabalho, NÃO TESTADA aqui** | `docker compose up --build` num volume novo, em máquina lenta, chega a `http://localhost:8000/login/` sem intervenção. **Quem verifica é o Fred**, no Windows dele: não existe daemon Docker neste ambiente de desenvolvimento, então a correção foi validada só por `docker compose config` (sintaxe e interpolação) e por leitura. Enquanto ele não confirmar, o item continua aberto. |

### Por que a integração contínua não pegou

Ela nunca sobe o `docker-compose.yml`. Constrói a imagem e roda a suíte contra um
PostgreSQL de serviço do próprio GitHub Actions — que já nasce pronto. O arquivo
que o Fred usa para abrir o sistema **não é exercitado por nenhuma verificação
automática**, e o defeito era de tempo: só aparece em disco lento, em volume
novo. Entra como item de verificação a decidir (não basta "tomar cuidado": ou
existe um passo de CI que suba a composição de verdade, ou a limitação fica
declarada).

## P0 — achados da auditoria da DL-017 ([rodada 1](../auditorias/2026-09-14-dl-017-rodada-1.md))

A etapa foi **REPROVADA** com 2 achados de gravidade alta. O relatório integral
está em [docs/auditorias/2026-09-14-dl-017-rodada-1.md](../auditorias/2026-09-14-dl-017-rodada-1.md);
a numeração de achado citada abaixo é a dele. **A aritmética passou em tudo** — o
que reprova é a camada de apresentação. Os itens BL-87 a BL-94 são condição para
a rodada 2 começar.

**Atualização de 2026-09-14, depois da correção:** BL-87 a BL-92, BL-94 e BL-96
a BL-99 estão corrigidos na branch de trabalho e verificados **em árvore limpa**
— 487 testes passando (eram 446 na revisão auditada), `ruff check`,
`ruff format --check`, `manage.py check` e `makemigrations --check` limpos. BL-95
foi integrado antes, pelo `desenvolvedor-pleno`. O `arquiteto-senior` reaplicou
por conta própria os dois defeitos de gravidade alta na cópia isolada e **mediu
a morte** de cada um: devolver `Decimal(bruto)` a `_decimal_do_formulario` derruba
9 testes; tirar o cálculo de totais de `adicionar_linha` derruba 1. Desfeitos os
dois, 296 aprovados em `apps/contabilidade`. **Nada disso é aprovação** — quem
aprova é a rodada 2 da auditoria, sobre a versão integrada.

**Dois defeitos da MESMA classe foram encontrados pela varredura, e não estavam
no relatório** (o auditor havia dito que achou os dele porque procurou, e que a
classe podia existir em caminhos não percorridos — estava certo):

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-101 | **Valor de magnitude absurda derrubava a tela com 500.** Um valor só com dígitos — formato textual perfeitamente válido — mas acima de `LIMITE_MAGNITUDE_VALOR` (10¹⁶) passava por toda a validação de domínio e só falhava no INSERT do Postgres (`DataError: numeric field overflow`). `criar_lancamento` verifica sinal e **escala**, nunca **magnitude**; a API já checava na fronteira, a tela não. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Valor acima do limite devolve 400 com erro de campo; teste com valor de 30 dígitos. **E a mensagem de erro não pode formatar o valor recusado** — `_valor_ptbr` faz `.quantize()`, que estoura a precisão do contexto decimal e criaria um 500 novo ao tentar contar que recusou. |
| BL-102 | **`chave_idempotencia` longa demais derrubava a tela com 500.** Campo oculto (o navegador nunca o alonga sozinho), mas um POST direto com mais de 255 caracteres reproduzia `DataError: value too long for type character varying(255)`. Reproduzido antes da correção. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | POST com chave acima do limite devolve 400, nunca 500, reaproveitando `TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA` da API em vez de duplicar o número. |

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-87 | **ALTA — `NaN`, `nan`, `-NaN`, `sNaN`, `Infinity`, `inf`, `-Infinity` e `1e500` digitados no campo de valor derrubam a tela com 500** (achado 1). `_valor_ptbr` faz `texto.split(".")` sem checar finitude; alcançado tanto pela mensagem de recusa quanto pela reexibição do formulário. A API recusa os 17 textos com 400. Nada é gravado em nenhum dos 8 casos — **mas a tela não diz isso**, e o contador que colou um valor de célula com erro não sabe se o lançamento entrou. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Teste parametrizado com os 8 textos exigindo **400 com erro de campo**, nunca 500; contagem de lançamentos inalterada; a mesma lista recebe o **mesmo veredito** na tela e na API. |
| BL-88 | **ALTA — o rodapé de conferência mostra `0,00 / 0,00` com as linhas preenchidas na mesma página, com HTTP 200** (achado 3). O ramo `acao=adicionar_linha` chama `_contexto_form_lancamento` sem os totais, e o template cai no `default:"0,00"`. É a única tela cuja função declarada é conferir o total antes de gravar, e — sem JavaScript, por decisão — o único caminho sem erro em que o total aparece. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | POST `acao=adicionar_linha` com linhas preenchidas: o total do rodapé é igual à soma dos `value` dos campos de valor exibidos na mesma página. Teste que extrai os dois do HTML e compara. Quando não houver total, a tela diz "não conferido" — nunca `0,00`. |
| BL-89 | **A tela grava quatro formatos de valor que a API recusa de propósito** (achado 2): `1e3`, `1_000`, `+10,00` e `10,00 ` com espaço. Medido: a tela gravou `1e3` como **1.000,00**. Ao construir o `Decimal` dentro da view, `_decimal_do_formulario` retira de `para_decimal` a única coisa que só ele podia julgar — o **formato textual**. Não é regra duplicada, é guarda **contornado**: a tela virou a porta mais frouxa da mesma invariante. Desenho em **DE-027**. | `especialista-frontend` | DE-027 | **corrigida na branch de trabalho**, aguardando rodada 2 | O texto (já com a vírgula convertida) desce para `apps.contabilidade.monetario.para_decimal`, e a exceção vira erro de formulário. Teste que afirme, para a **mesma lista de textos**, veredito idêntico na tela e na API. |
| BL-90 | **Histórico acima de 300 caracteres derruba a tela com 500** (achado 4). O único guarda é `maxlength` no HTML — proteção de navegador, não de servidor. É o único formulário escrito à mão da entrega; o de conta é `ModelForm` e por isso está protegido. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | POST com 301 caracteres devolve **400** com erro de campo e a mesma mensagem da API; teste no caminho HTTP. |
| BL-91 | **Partidas além da vigésima são descartadas em silêncio e o lançamento é gravado como sucesso** (achado 5). Medido com `num_linhas=22`: 20 partidas gravadas, **77,00 de débito e 77,00 de crédito desaparecem**, o lote fecha balanceado e nenhuma conferência acusa. É perda silenciosa de fato contábil — a corrupção por omissão que o próprio `services.py` chama de pior que a duplicidade. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | `num_linhas` acima do teto **recusa o POST** ou processa todas as linhas presentes e recusa com mensagem. Nunca truncar em silêncio. Teste exigindo 400 ou 22 partidas — nunca 20 com sucesso. |
| BL-92 | **A indentação hierárquica nunca é aplicada: `float` localizado gera CSS inválido** (achado 6). `(nivel - 1) * 1.25` é `float`; com `LANGUAGE_CODE="pt-br"` o template entrega `padding-left: 1,25rem`. Medido no Chromium: **1px nos três níveis** contra 40px no controle. Plano de contas e balancete são listas hierárquicas sem hierarquia visível, e desmente a afirmação "nenhum `float` em nenhum ponto" que o plano DL-017 faz. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Indentação por **classe CSS** (`nivel-N`), sem estilo inline. Teste que extraia todo `style="padding-left: …"` do HTML e recuse vírgula; medição de `getComputedStyle` mostrando indentação crescente por nível. |
| BL-93 | **`estado.md` e `README.md` afirmavam um estado que o commit auditado desmentia** (achado 7, **do `arquiteto-senior`**). Corrigido na entrega que registra esta auditoria. Resta a parte de mecanismo: `test_documentacao_do_estado.py` **passou** com a divergência, porque verifica que todo `DL-xxx` aparece nos dois arquivos, não que a descrição esteja correta. | `arquiteto-senior` | — | **texto corrigido**; guarda ainda planejada | Avaliar se o teste pode reprovar "não iniciada"/"não começou"/"em execução" quando o plano correspondente já tem commit de implementação no histórico. Se for decidido não implementar, registrar a decisão e o porquê. |
| BL-94 | **Mutante sobrevivente: nada testa o isolamento do combo de conta-pai** (achado 8). Trocar `Conta.objects.filter(empresa=empresa)` por `Conta.objects.all()` em `ContaCriarForm.__init__` sobrevive à suíte inteira — **0 falhas em 446**. O controle funciona hoje (medido), mas não tem teste. Se cair numa refatoração, "Nova conta" passa a exibir o plano de contas inteiro de todos os clientes de todos os escritórios — estrutura societária, bancos e litígios. Mesmo padrão que na DL-015 levou duas rodadas para aparecer. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Teste com duas empresas do mesmo escritório e uma de outro, afirmando que código e nome de conta alheia **não aparecem** no HTML de `conta_nova`; a mutação acima passa a **morrer**. |
| BL-95 | **Nenhum teste exercita o `config/urls.py` real** (achado 9). Os testes da DL-017 declaram o próprio urlconf com `@pytest.mark.urls`. O auditor verificou o urlconf real e **está correto**, mas se alguém unificar os prefixos `contabilidade/` e `contabilidade/painel/`, um dos dois conjuntos desaparece em silêncio — sem erro e sem build vermelho. O único guarda é um comentário. | `desenvolvedor-pleno` | — | **integrada** na branch de trabalho | Teste **sem** `pytest.mark.urls` afirmando `application/json` sob `contabilidade/` e `text/html` sob `contabilidade/painel/`, para a mesma rota lógica. **Feito** em `apps/contabilidade/tests/test_dl017_urlconf_integrado.py`: o levantamento encontrou **três** rotas que colidem literalmente, não duas — `razao/<int:conta_id>/` também colide e não estava nomeada no achado 9. Mutação aplicada e medida: unificar os prefixos numa cópia isolada faz os 4 testes falharem, inclusive na asserção de que os dois `reverse()` produzem caminhos diferentes. |
| BL-96 | **As colunas consolidadas do balancete ficam sem total, ao lado de um rodapé que totaliza outras duas** (achado 10). Medido: a coluna "Débitos" soma 3.000,00 e o rodapé diz 1.000,00 — os números estão certos e conciliam (a consolidada conta cada lançamento uma vez por nível), mas a coluna que o contador soma com o dedo não é somável e não avisa. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | As duas colunas consolidadas marcadas como **não somáveis**: `—` no rodapé sob elas, com texto acessível explicando, e separação visual. Teste que verifique a presença da marcação. |
| BL-97 | **`aria-describedby` aponta para um `id` que não existe** (achado 11), em `conta_form.html`. Quem usa leitor de tela não recebe a instrução que evita criar conta sintética aceitando lançamento. O texto continua visível, e por isso passa em inspeção visual. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | `id="{{ campo.auto_id }}_helptext"` no `<p>`, como já se faz no bloco de erro; teste que verifique que todo `aria-describedby` do HTML entregue referencia `id` existente, em **todas** as telas. |
| BL-98 | **O rótulo acessível do campo mais importante da linha de lançamento é "Linha N", não "Conta"** (achado 12). Os dois campos vizinhos dizem "Tipo da linha N" e "Valor da linha N" — a assimetria é a evidência. O leitor de tela anuncia "Linha 1, caixa de combinação" no campo em que se escolhe **qual conta debitar**. | `especialista-frontend` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Rótulo "Conta da linha N"; teste que compare os três rótulos da mesma linha. |
| BL-99 | **O teto de 20 partidas desaparece sem explicação** (achado 14): ao chegar a 20 linhas o botão "Adicionar linha" simplesmente não aparece mais. Uma contabilização de folha passa de 20 partidas com facilidade. Junto: comentários e docstrings obsoletos (achado 13), incluindo referência a uma seção *"Onde é fácil errar"* que **não existe** no plano DL-017 — a seção passa a existir, escrita pelo `arquiteto-senior`. | `especialista-frontend`; a seção do plano é do `arquiteto-senior` | — | **corrigida na branch de trabalho**, aguardando rodada 2 | Mensagem visível ao atingir o teto, dizendo o limite e o caminho (dois lançamentos, ou pedir aumento do teto). Nenhum comentário afirmando "ainda não escrita" sobre código já escrito; nenhuma referência a seção inexistente. |

## P1 — interface

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-20 | Criar **template base** com bloco de conteúdo, navegação e área de mensagens. Hoje os 5 templates repetem `<!DOCTYPE>`, `<head>` e `<title>`, sem `{% extends %}`. | `especialista-frontend` | — | planejada | Todos os templates estendem a base; nenhuma duplicação de cabeçalho; navegação consistente. |
| BL-21 | Renderizar `django.contrib.messages`. O framework está instalado e o middleware ativo, mas **nenhum template exibe mensagens** — cadastro bem-sucedido redireciona sem confirmação. | `especialista-frontend` | BL-20 | planejada | Sucesso, erro e aviso aparecem na tela. Teste do fluxo de criação de empresa mostrando a confirmação. |
| BL-22 | Tratar os estados ausentes: erro, sucesso e falta de permissão. Falta de permissão hoje devolve texto cru `HttpResponseForbidden`, sem template nem caminho de volta. | `especialista-frontend` | BL-20 | planejada | Cada tela trata carregamento, vazio, erro, sucesso e sem permissão, com saída navegável. |
| BL-23 | Formatação **pt-BR** de valores e datas. Hoje a única formatação monetária devolve `"1000.00"`: sem separador de milhar, sem `R$`, formato US. CNPJ é exibido sem máscara. | `especialista-frontend` com `desenvolvedor-pleno` | BL-01 (PE-02) | planejada | Valores com separador de milhar e duas casas, alinhados à direita; datas em pt-BR; CNPJ com máscara; total exibido concilia com a soma das linhas. |
| BL-24 | Corrigir acessibilidade: `<select>` sem rótulo no painel, `<form>` aninhado dentro de `<p>` (HTML inválido), ausência de landmarks, erro de login sem `role="alert"`. | `especialista-frontend` | BL-20 | planejada | Rótulo ou `aria-label` em todo controle; HTML válido; landmarks presentes; erro anunciado; navegação completa por teclado com foco visível. |
| BL-25 | Exibir **contexto de operação**: escritório, empresa, estabelecimento e competência visíveis nas telas que operam dados. | `especialista-frontend` | BL-15 | planejada | O usuário identifica, em qualquer tela de dados, em qual empresa e competência está operando. |
| BL-26 | Decidir e registrar a estratégia de CSS. Hoje **não há CSS nem JS**: `STATIC_URL`/`STATIC_ROOT` e WhiteNoise estão configurados, mas não existe diretório `static/`. | `especialista-frontend` propõe; `arquiteto-senior` decide | — | planejada | Decisão registrada em [decisoes.md](decisoes.md) antes de qualquer investimento em interface. Não introduzir biblioteca visual sem essa decisão. |

## P2 — infraestrutura de verificação

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-30 | Documentar no README o pré-requisito **Python 3.12+** e o procedimento de ambiente local. Verificado: `Django==6.1.1` exige 3.12+, e a instalação falha em 3.11. | `arquiteto-senior` | — | planejada | README indica a versão mínima e o passo a passo que funciona em ambiente limpo. |
| BL-31 | Alinhar o banco de desenvolvimento ao da CI. O padrão local cai em SQLite enquanto a CI usa PostgreSQL 16 — divergência real de comportamento em `Sum` sobre `DecimalField`, já contornada em código. | `desenvolvedor-pleno` | — | planejada | Procedimento documentado para subir PostgreSQL local; ou decisão registrada de manter a divergência com a justificativa. |
| BL-32 | Acrescentar à CI as verificações que o [AGENTS.md](../../AGENTS.md) §13 exige e que hoje não existem (achado 5): detecção de segredos, verificação de tipos, `makemigrations --check --dry-run` e `check --deploy`. | `desenvolvedor-pleno` | — | planejada | Workflow falha ao detectar segredo introduzido em teste controlado e ao detectar deriva entre modelo e migração. |
| BL-35 | Introduzir paginação e limites nas APIs (achado 7, gravidade média). Não há `DEFAULT_PAGINATION_CLASS` nem throttle, e o balancete faz duas consultas por conta (N+1). | `desenvolvedor-pleno` | — | planejada | Listagens paginadas; balancete sem N+1; limite de requisições aplicado. |
| BL-36 | Tratar `int(escritorio_id)` inválido (achado 10, gravidade baixa): hoje um valor não numérico gera 500 em vez de 400. | `desenvolvedor-pleno` | — | planejada | Requisição com valor não numérico retorna 400, com teste. |
| BL-45 | Voltar a usar `{% static %}` com *cache busting*, quando houver mais de um arquivo estático ou público real em produção. Hoje o CSS é referenciado por caminho fixo (DE-012), o que funciona mas não invalida cache do navegador após deploy. | `especialista-frontend` | mais de um estático, ou deploy real | planejada | Template usa `{% static %}`; suíte e CI passam com o manifesto gerado; nome do arquivo servido muda quando o conteúdo muda. |
| BL-44 | Validar o **corpo** da requisição de lançamento nos limites do banco (achado N3 da [auditoria DL-007 rodada 2](../auditorias/2026-09-12-dl-007-rodada-2.md), gravidade média, **pré-existente**). Hoje `historico` com 5000 caracteres, `valor` com 25 dígitos e `"Infinity"` viram **500**. A DL-007 blindou apenas o cabeçalho `Idempotency-Key`. | `desenvolvedor-pleno` | BL-17 (mesma família; depende de PE-02 para a política de escala) | planejada | Entrada acima do limite retorna 400 com mensagem útil, nunca 500. Testes de limite para `historico`, `valor` e valores não finitos. |
| BL-34 | Cobrir as lacunas de teste apontadas no diagnóstico: idempotência, concorrência, arredondamento, migração sobre base preexistente. | `desenvolvedor-pleno` | BL-12 | planejada | Cada lacuna tem teste que falha antes da correção e passa depois. |

## Fora do escopo por enquanto

Registrado para não ser confundido com esquecimento:

- Módulos Fiscal, Folha, Honorários e Processos/Paralegal: previstos em
  [escopo.md](../escopo.md), sem etapa aberta. Dependem de BL-01.
- Servidor MCP e assistente de IA: previstos no escopo, sem etapa aberta.
- Portal do cliente.
- Conciliação bancária, centros de custo, Balanço Patrimonial, DRE, ECD e ECF —
  explicitamente adiados no plano da DL-006.

## Observação sobre o estado do repositório

Os PRs #7, #8 e #9 **já foram mesclados**: a `main` contém DL-002 a DL-006. O
PR #10, aberto, atualiza a seção "Estado atual e continuidade" do README, que
ainda descreve esses PRs como pendentes. Por isso o README **não foi alterado
nesta configuração da equipe** — a correção já está encaminhada nesse PR. Ver
[docs/agents/estado.md](../agents/estado.md).
