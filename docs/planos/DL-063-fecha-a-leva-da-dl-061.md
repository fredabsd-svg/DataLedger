# DL-063 — Fecha a leva da DL-061: o campo da coluna da DMPL, o teste do snapshot e a dica da divergência

**Estado:** em desenvolvimento
**Nível de risco (§3.1 do [AGENTS.md](../../AGENTS.md)):** **1 — o dinheiro e
o livro.** A peça central (BL-606) decide em que coluna da DMPL a conta entra
— campo que o contador preenche e que a apuração lê. O BL-606 sozinho seria
nível 1; o BL-625, texto de tela, é nível 2 e entra porque é a **mesma
pendência** que a DL-061 deixou aberta.
**Branch de trabalho:** `feat/dl-063-fecha-a-leva-da-dl-061`
**Branch de destino:** `main`
**Origem:** BL-606, BL-607 e BL-625, medidos e abertos na
[DL-062](DL-062-sinal-da-raiz-retificadora.md) §5 e no backlog.
**Escolha do Fred em 04/10/2026:** os três nesta etapa, e o campo da DMPL
**aceito pela API como a DLPA e a DRE** — a assimetria de ficar gravável só
pela web não é desejada.

---

## 1. Os três problemas, medidos

### 1.1 BL-606 — o campo existe no modelo e não existe na tela nem na API

`Conta.classificacao_dmpl` (NBC TG 51, item 111A) está no modelo
(`models.py:993`) e é lido pela apuração, mas **não é gravável** pelos dois
caminhos que cadastram conta:

| Onde | `classificacao_dre` | `classificacao_dlpa` | `classificacao_dmpl` |
| --- | --- | --- | --- |
| Formulário web (`ContaCriarForm.Meta.fields`) | sim | sim | **não** |
| Contrato do POST web | sim | sim | **não** |
| `ContaSerializer.Meta.fields` | sim | sim | sim (só leitura) |
| Contrato do POST da API | sim | sim | **não** |

Duas consequências, e a segunda é a que dói:

1. Quem cria conta pela tela **não consegue** dizer em que coluna da DMPL ela
   entra — precisa criar e depois classificar por outra rota.
2. Quem integra por API **não tem porta nenhuma**: o campo é `read_only`, e o
   POST o recusa por contrato com "dado não contratado", sem nem nomear o
   campo. A classificação da DMPL tem porta própria (`ContaClassificacaoDmplView`),
   mas ela classifica uma conta **existente** — quem está criando a conta não
   tem por onde passar.

O `Conta.clean()` **já** valida a compatibilidade da coluna com o tipo da
conta (`models.py:1263-1274`) e a coerência DLPA×DMPL (`models.py:1280-1284`).
A regra existe; o que falta é a **porta**.

### 1.2 BL-607 — o snapshot `REPEATABLE READ` da DMPL não tem teste

A apuração da DMPL roda em isolamento `REPEATABLE READ` para que o número
impresso não mude no meio da leitura. A DRE e o Balanço têm um **par** de
testes que prova isso desligando e ligando o snapshot. A DMPL não tem — e a
DLPA também não (a lacuna é maior que a descrição do backlog).

**Nada de produção muda nesta peça:** o snapshot já está implementado. É
arquivo de teste.

### 1.3 BL-625 — a dica da divergência aponta uma causa que não é a causa

A dica de `diferenca_de_fechamento` é um **dicionário estático de módulo**: a
mesma frase para todo caso. Depois da DL-062 o texto já não nomeia a retificadora
(correção de texto feita naquela etapa), mas ele continua **não condicionando**:
ele diz o que conferir sem dizer **qual** das causas está em jogo.

Existem duas causas reais e distintas para a mesma pendência:

1. A conta da coluna **não classifica** o movimento que de fato teve.
2. A conta **mudou de coluna** depois do período apurado.

O texto estático não distingue as duas, e o contador recebe a mesma instrução
nos dois casos — na segunda, ela não serve.

## 2. Decisões de desenho (`arquiteto-senior`, reversíveis)

**D1 — Um campo, três portas, uma regra só.** O campo entra no formulário
web **e** no POST da API, com a mesma autorização e a mesma validação de
compatibilidade com `tipo` que a DLPA e a DRE já têm. A regra de
compatibilidade continua morando em `TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL` e
continua sendo replicada no serializer **pelo mesmo motivo já documentado**:
o DRF nunca chama `full_clean()` (BL-40/DE-008).

**D2 — A porta própria de classificação continua.** `ContaClassificacaoDmplView`
não sai: ela grava **com trilha antes/depois na mesma transação**, que é o
que a reclassificação de conta com movimento exige. O POST de criação é
cadastro inicial, não reclassificação — são operações diferentes e continuam
com contratos diferentes.

**D3 — `""` normaliza para `None`, como nas outras duas.**
`validate_classificacao_dmpl` faz `value or None`, pelo mesmo motivo do achado
A4 da DL-045: o `ChoiceField` aceita `""` e a guarda de transição de
`Conta.clean()` o trataria como "já classificada", travando a conta para uma
classificação real posterior.

**D4 — A dica da divergência vira função do `emissao`, não constante.** O texto
passa a ser escolhido a partir do que a apuração **realmente** encontrou, e não
a大变é de um dicionário fixo. A fonte já existe sem mudar contrato de serviço:
`emissao["listas_pendentes"]["contas_do_patrimonio_liquido_sem_coluna"]`, que
`services.py` já monta.

**D5 — O teste do snapshot é o par "sem o wrapper"/"com o wrapper",** espelhado
da DRE, e fica em arquivo novo, sem tocar produção.

## 3. Critérios de aceite

1. O formulário de conta nova **oferece** "Coluna da DMPL", com rótulo e
   ajuda no mesmo tom dos outros dois.
2. O POST web grava a coluna escolhida, e recusa (200 + mensagem, nada
   gravado) quando a coluna é incompatível com o tipo da conta.
3. O POST da API **aceita** `classificacao_dmpl`, grava, e recusa com
   mensagem **nomeando o campo** quando a coluna é incompatível com `tipo`.
4. A API continua **recusando** chave fora do contrato, com "dado não
   contratado" — o contrato segue sendo o filtro.
5. `""` na API e no formulário gravam `None` (não travam a conta).
6. `read_only_fields` sai do serializer; a porta própria de classificação
   **continua funcionando** e continua gravando com trilha.
7. A dica da divergência **para de ser constante**: com conta de PL sem coluna
   preenchida, ela aponta essa causa; sem essa pendência, mantém o texto
   genérico. Os dois casos têm teste de tela.
8. O par de testes do snapshot da DMPL existe, espelhado da DRE, com espera de
   thread **com timeout e asserção de conclusão**.
9. A suíte da DMPL, da DLPA, do plano de contas e da API de contas passa sem
   mudar nenhuma expectativa.

## 4. Cenários de teste obrigatórios

| # | Cenário | O que prova |
| --- | --- | --- |
| 1 | Formulário web grava coluna válida | critério 1 e 2 |
| 2 | Formulário web recusa coluna em conta de tipo não-PL, nada gravado | critério 2 |
| 3 | POST da API grava coluna válida e devolve a conta com ela | critério 3 |
| 4 | POST da API recusa coluna incompatível **nomeando o campo** | critério 3 |
| 5 | POST da API com `""` grava `None` | critério 5 |
| 6 | POST da API com chave desconhecida continua recusado por contrato | critério 4 |
| 7 | A porta própria de classificação continua gravando com trilha | critério 6 |
| 8 | Dica da divergência com conta de PL sem coluna | critério 7 |
| 9 | Dica da divergência sem essa pendência mantém o texto genérico | critério 7 |
| 10 | Par do snapshot da DMPL (sem wrapper / com wrapper) | critério 8 |

## 5. Fora do escopo

- **BL-622** — a DLPA fabricar linhas opostas. Nível 1, defeito próprio,
  **não entra** aqui: misturá-lo numa etapa que já muda contrato de API
  tornaria a revisão mais difícil do que a própria mudança.
- **DL-016 F3** — encerramento de competência. Capacidade nova, plano de 754
  linhas ainda não integrado.
- **BL-626 e BL-627** — validação do Fred.
- A **dedicated PATCH** de classificação não muda de contrato; só ganha
  convive com o POST.

## 6. Reversão

`git revert` dos commits desta etapa. **Nenhuma migração**: nenhum schema
muda, nenhum dado é gravado por migração. O que muda é **quais portas
aceitam** um campo que já existia no modelo — reverter devolve exatamente o
comportamento anterior, sem tocar em dado de cliente.

## 7. Riscos declarados

| Risco | Mitigação |
| --- | --- |
| Regra duplicada em três portas (form, serializer, `clean()`) | Já é assim para DRE e DLPA; a fonte única é `TIPOS_ACEITOS_DA_CLASSIFICACAO_DMPL` e o teste derivado continua valendo |
| Aceitar o campo no POST enfraquece a trilha da porta própria | Portas são operações diferentes: **criação** (sem histórico a preservar) × **reclassificação** (com antes/depois obrigatório) |
| Dica condicionada virar `if` escrito à mão | A condição vem da **lista de pendência real** que a apuração já monta, não de um teste adivinhado |
| Snapshot só verificável na CI | Declarado em §8; a evidência de execução é a CI com PostgreSQL 16 |

## 8. Evidências e integração

- Diagnóstico: §1, com as tabelas de `arquivo:linha`.
- Verificação local: pendente.
- **O teste do snapshot (BL-607) não é executável localmente** — não há
  PostgreSQL nem Docker nesta máquina, e o `SET TRANSACTION ISOLATION LEVEL
  REPEATABLE READ` não existe no SQLite. A evidência dele é a CI, e isso
  fica declarado, não escondido.
- Auditoria independente: pendente (obrigatória — a peça BL-606 é nível 1).
- PR: pendente.
