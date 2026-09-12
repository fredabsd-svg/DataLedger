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
| BL-46 | Aceitar **CNPJ alfanumérico** no cadastro, na validação e em tudo que compare CNPJ. Hoje o DataLedger **recusa** qualquer CNPJ alfanumérico. | `desenvolvedor-pleno` | **Documento técnico oficial** do cálculo do dígito verificador | **bloqueada** — aguardando a especificação oficial | CNPJ alfanumérico válido é aceito e persistido; CNPJ numérico existente continua válido; DV conferido pelo algoritmo **oficial**, com casos de referência; nenhum ponto do sistema descarta letras do CNPJ. |

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

### Por que está bloqueada, e não em desenvolvimento

A página oficial confirma o **fato** e a **data**, mas **não publica o algoritmo
do dígito verificador** — ela remete a um documento técnico à parte. Fontes
secundárias descrevem o cálculo como módulo 11 sobre o valor ASCII de cada
caractere menos 48, **mas isso não foi confirmado em fonte oficial**.

Implementar dígito verificador a partir de descrição de blog seria exatamente o
que o [AGENTS.md](../../AGENTS.md) §10 proíbe: inventar fórmula. Um validador
errado recusaria empresa legítima ou aceitaria CNPJ inválido — os dois caros.

**Antes de implementar:** obter o documento técnico oficial do cálculo do DV, no
portal da Receita Federal, e registrar a fonte e a vigência junto do código.

## P1 — lacunas de validação encontradas de passagem

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-47 | Validar o CNPJ do **próprio escritório**. `apps/tenancy/models.py` declara `cnpj = CharField(max_length=14, unique=True)` **sem validador algum** — aceita qualquer texto de até 14 caracteres, inclusive `"abc"`. | `desenvolvedor-pleno` | DL-011 (reaproveitar `validar_cnpj`) | planejada | `Escritorio.cnpj` recusa valor inválido, aceita numérico e alfanumérico, com teste. Avaliar o que fazer com registros existentes que não passem na validação. |

Encontrado pelo `desenvolvedor-pleno` durante a DL-011, **fora do escopo da
etapa**, e reportado em vez de corrigido — a disciplina certa.

Por que não entrou na DL-011: o BL-46 trata do CNPJ das **empresas clientes**;
este é o CNPJ do **escritório contábil**, outro modelo e outro contexto.
Misturar os dois numa etapa faria o diff perder foco.

Cuidado ao implementar: pode haver escritório já cadastrado com CNPJ que não
passe na validação. Acrescentar validador a campo existente **quebra o
salvamento** desses registros. Verificar a base antes e decidir o tratamento —
não é caso de aplicar e ver o que acontece.

## P0 — decisões e bloqueios

| ID | Tarefa | Responsável | Depende de | Estado | Critério de aceite |
| --- | --- | --- | --- | --- | --- |
| BL-01 | Fred responder as pendências PE-01 a PE-08 de [requisitos.md](requisitos.md), com prioridade para PE-01 (prioridade de negócio) e PE-02 (política de arredondamento). | `arquiteto-senior` conduz; decisão é do Fred | — | planejada | Cada pendência vira requisito confirmado ou decisão registrada em [decisoes.md](decisoes.md). |
| BL-02 | Configurar proteção da branch `main`: exigir PR, revisão autorizada e verificações obrigatórias aprovadas. | Fred (ação administrativa no GitHub) | — | bloqueada | Merge direto em `main` recusado; PR sem CI aprovada não mescla. Registrar evidência da configuração. |

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
| BL-33 | Planejar e **verificar** backup e restauração. Não existe procedimento hoje. | `arquiteto-senior` define; `desenvolvedor-pleno` implementa | BL-01 (PE-07) | planejada | Restauração testada em ambiente descartável, com evidência registrada. |
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
