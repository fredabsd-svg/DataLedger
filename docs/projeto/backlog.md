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
