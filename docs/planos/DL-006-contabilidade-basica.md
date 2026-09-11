# DL-006 — Contabilidade básica

## Objetivo e diagnóstico

Implementar o primeiro módulo de negócio do DataLedger, iniciando a etapa 4
("Primeiros fluxos") do [README](../../README.md). Entre as opções dessa
etapa (Paralegal, Honorários, Contabilidade básica, XML de NF-e, cadastros
de folha), a Contabilidade foi escolhida por decisão do responsável pelo
produto, por ser a base para a qual Fiscal, Folha e Honorários vão integrar
depois — construí-la primeiro evita retrabalho de integração.

Na inspeção inicial desta demanda, a "Fundação" (DL-003 a DL-005) já
entregava autenticação, isolamento entre escritórios, cadastro de empresas
e permissões básicas por papel, mas nenhum dado contábil existia.

**Dependência entre PRs:** a branch `feat/dl-006-contabilidade-basica` parte
de `feat/dl-005-permissoes-auditoria` (PR #5, que depende dos PRs #2, #3 e
#4, todos ainda não integrados). O PR desta etapa precisa ser reapontado
para `main` conforme os PRs anteriores forem integrados, na ordem correta.

## Decisões desta etapa

| Decisão | Escolha | Motivo |
| --- | --- | --- |
| Escopo do recorte | Plano de contas, lançamentos manuais por partidas dobradas, Diário, Razão e Balancete | É o núcleo mínimo utilizável de um módulo contábil. Conciliação bancária, centros de custo, regras de contabilização automática (que dependem de Fiscal/Folha/Honorários existirem), Balanço Patrimonial, DRE, ECD/ECF e encerramento formal de período ficam para incrementos futuros. |
| Igualdade entre débito e crédito | Validada em `services.criar_lancamento` antes de qualquer gravação; lançamento com menos de duas partidas ou com débito ≠ crédito é rejeitado | Requisito direto do AGENTS.md, seção 10 ("Garantir igualdade entre débitos e créditos em lançamentos efetivados"). |
| Precisão decimal | `DecimalField(max_digits=18, decimal_places=2)` em todos os valores monetários; qualquer valor monetário exposto em uma resposta que não passe por um `DecimalField` de serializer é formatado explicitamente como string com duas casas | Ponto flutuante binário é proibido para cálculos financeiros (AGENTS.md, seção 10). Durante a validação desta etapa, um teste automatizado pegou o encoder JSON padrão do DRF convertendo `Decimal` para `float` fora de um serializer — corrigido antes de seguir (ver "Validação reproduzível"). |
| Imutabilidade de lançamentos efetivados | `LancamentoContabil.save()`/`.delete()` e `ItemLancamento.save()`/`.delete()` levantam `LancamentoImutavelError` quando o registro já existe | "Impedir alterações silenciosas em registros efetivados" (AGENTS.md, seção 10) é aplicado no nível do modelo, não só por não expor endpoint de edição — nem o Django admin consegue burlar essa regra. |
| Correção de lançamento | Só por estorno (`services.estornar_lancamento`): cria um novo lançamento com débito/crédito invertidos, referenciando o original em `estorno_de`; um estorno não pode ser estornado | Preserva a trilha contábil completa em vez de apagar o erro original. |
| Quem pode escriturar | `administrador`, `gestor`, `analista` e `financeiro` (`ContabilidadePermissions.PodeEscriturar`); qualquer papel vinculado ao escritório ativo pode consultar | A escrituração contábil normalmente é tarefa do analista/financeiro do escritório, não só de quem administra o cadastro (diferente da regra de empresas, restrita a administrador/gestor). |
| Reaproveitamento de código | `EmpresaEscopadaMixin` foi extraído de `apps.empresas.views` para `apps.empresas.mixins`, reaproveitado por `apps.contabilidade` e pelas próprias views de empresas | Evita duplicar a lógica de "resolver a empresa restrita ao escritório ativo, 404 se for de outro escritório" em cada módulo de negócio futuro. |

## Etapa e entregáveis

- Estado deste registro: `em validação`.
- Branch de trabalho: `feat/dl-006-contabilidade-basica` (baseada em
  `feat/dl-005-permissoes-auditoria`).
- Destino: `feat/dl-005-permissoes-auditoria` (temporário, até a cadeia de
  PRs anteriores ser integrada; depois, `main`).
- Entregáveis:
  - App `apps/contabilidade`: modelos `Conta`, `LancamentoContabil`,
    `ItemLancamento` e os choices `TipoConta`, `NaturezaConta`,
    `TipoPartida`.
  - `apps/contabilidade/services.py`: `criar_lancamento` e
    `estornar_lancamento`, com todas as validações de partidas dobradas.
  - Endpoints DRF: plano de contas (listar/criar), Diário (listar/criar
    lançamento), estorno, Razão por conta, Balancete.
  - `apps/empresas/mixins.py`: extração de `EmpresaEscopadaMixin` para
    reuso entre apps.
  - Admin do Django para `Conta` e `LancamentoContabil` (lançamento sem
    tela de edição, coerente com a imutabilidade do modelo).
  - Migração inicial do app `contabilidade`.
- Dependências: PRs #2 a #5 integrados antes do merge final deste PR.
- Fora do escopo: lançamentos automáticos vindos de outros módulos,
  conciliação bancária, centros de custo, regras de contabilização
  configuráveis, Balanço Patrimonial, DRE, ECD/ECF, consolidação,
  encerramento/bloqueio formal de período (além da imutabilidade básica já
  implementada), interface server-rendered (só API e admin nesta etapa).

## Critérios de aceite

- Um lançamento só é criado se a soma dos débitos for igual à soma dos
  créditos e houver ao menos duas partidas.
- Uma conta de outra empresa, ou uma conta que não aceita lançamento
  direto (sintética), não pode receber um item de lançamento.
- Um lançamento contábil e seus itens não podem ser alterados nem
  excluídos depois de criados — nem via serviço, nem via admin, nem
  chamando `.save()`/`.delete()` diretamente no modelo.
- Estornar um lançamento cria um novo lançamento com as partidas
  invertidas, referenciando o original; um estorno não pode ser estornado.
- Consultas de plano de contas, Diário, Razão e Balancete são sempre
  restritas à empresa e ao escritório ativo da requisição; uma empresa de
  outro escritório resulta em 404.
- Escrever (criar conta, lançar, estornar) exige papel administrador,
  gestor, analista ou financeiro; os demais papéis (paralegal, cliente)
  continuam podendo consultar.
- Todo valor monetário nas respostas da API mantém duas casas decimais
  exatas, independentemente do banco de dados usado.
- `manage.py check`, `manage.py migrate` em banco vazio, `pytest`,
  `ruff check` e `ruff format --check` passam.

## Cenários de teste

| Cenário | Resultado esperado | Cobertura |
| --- | --- | --- |
| Código de conta duplicado na mesma empresa | Erro de integridade | `apps/contabilidade/tests/test_models.py` |
| Conta pai de empresa diferente | `ValidationError` | `apps/contabilidade/tests/test_models.py` |
| Editar/excluir um `LancamentoContabil` existente | `LancamentoImutavelError` | `apps/contabilidade/tests/test_imutabilidade.py` |
| Editar/excluir um `ItemLancamento` existente | `LancamentoImutavelError` | `apps/contabilidade/tests/test_imutabilidade.py` |
| Lançamento com débito = crédito | Criado com sucesso | `apps/contabilidade/tests/test_services.py` |
| Lançamento com débito ≠ crédito | `LancamentoInvalido` | `apps/contabilidade/tests/test_services.py` |
| Lançamento com menos de duas partidas | `LancamentoInvalido` | `apps/contabilidade/tests/test_services.py` |
| Partida em conta de outra empresa | `LancamentoInvalido` | `apps/contabilidade/tests/test_services.py` |
| Partida em conta sintética (`aceita_lancamento=False`) | `LancamentoInvalido` | `apps/contabilidade/tests/test_services.py` |
| Estorno de um lançamento | Cria lançamento reverso referenciando o original | `apps/contabilidade/tests/test_services.py` |
| Estorno de um estorno | `LancamentoInvalido` | `apps/contabilidade/tests/test_services.py` |
| Papel cliente tenta criar lançamento | 403 (via API) | `apps/contabilidade/tests/test_api.py` |
| Papel gestor cria lançamento balanceado | 201 | `apps/contabilidade/tests/test_api.py` |
| Lançamento desbalanceado via API | 400 | `apps/contabilidade/tests/test_api.py` |
| Empresa de outro escritório em `/contas/` | 404 | `apps/contabilidade/tests/test_api.py` |
| Razão de uma conta após dois lançamentos | Saldo acumulado correto a cada linha | `apps/contabilidade/tests/test_api.py` |
| Balancete após um lançamento | Saldo de cada conta reflete sua natureza | `apps/contabilidade/tests/test_api.py` |

Fluxo completo também validado manualmente via HTTP real (`manage.py
runserver` + `curl`, com sessão e CSRF): criação de plano de contas mínimo,
lançamento de integralização de capital, consulta de Diário/Razão/
Balancete, estorno e verificação de que o balancete zera após o estorno —
ver "Validação reproduzível".

## Impacto em segurança, dados, cálculos, contatos e desempenho

- **Segurança:** escrita restrita por papel (`PodeEscriturar`); toda
  consulta/gravação é escopada à empresa do escritório ativo via
  `EmpresaEscopadaMixin`, nunca por ID de empresa recebido sem validação.
  Criação de conta e de lançamento geram registro de auditoria
  (`conta.criada`, `lancamento.criado`, `lancamento.estornado`).
- **Dados:** três novos modelos (`Conta`, `LancamentoContabil`,
  `ItemLancamento`). `Empresa`/`Conta` usam `on_delete=PROTECT` nas FKs
  correspondentes, para nunca perder rastreabilidade silenciosamente.
- **Cálculos:** nenhuma regra fiscal ou trabalhista; apenas a mecânica
  contábil de partidas dobradas, sem inventar alíquotas ou fórmulas.
- **Contratos:** novos endpoints, todos sob `/contabilidade/empresas/<id>/`:
  `contas/` (GET/POST), `lancamentos/` (GET/POST),
  `lancamentos/<id>/estornar/` (POST), `razao/<conta_id>/` (GET),
  `balancete/` (GET).
- **Desempenho:** Razão e Balancete recalculam saldo a partir dos itens a
  cada consulta (sem saldo pré-calculado). Aceitável para o volume desta
  etapa; se o volume crescer, uma etapa futura pode introduzir saldo
  acumulado por período, mantendo os itens como fonte da verdade.

## Estratégia de reversão

Nenhum dado de produção existe ainda. Reversão: fechar o PR antes do merge
ou propor um commit de reversão em novo PR após integração.

## Validação reproduzível

Executado localmente em ambiente Windows, Python 3.14, no mesmo ambiente
virtual das etapas anteriores:

```sh
python manage.py makemigrations contabilidade
python manage.py check
python manage.py migrate
pytest
ruff check .
ruff format --check .
```

Resultados obtidos em 11/09/2026:

- `manage.py check`: nenhum problema encontrado.
- `manage.py migrate` em banco vazio: `contabilidade.0001_initial` aplicou
  sem erro, junto com as migrações das etapas anteriores.
- `pytest`: 55 testes executados, 55 aprovados (36 herdados das etapas
  DL-002 a DL-005 + 19 novos desta etapa).
- `ruff check .` e `ruff format --check .`: sem apontamentos, após ajustar
  linhas longas nos testes e extrair um helper `_item()` para reduzir
  repetição.

**Bug encontrado e corrigido durante a própria validação:** os testes de
Razão e Balancete inicialmente falhavam porque o encoder JSON padrão do
Django REST Framework converte `Decimal` para `float` quando o valor não
passa por um `DecimalField` de serializer (as views de Razão e Balancete
retornam dicionários simples, não um `ModelSerializer`). Isso violaria a
exigência de precisão decimal para valores monetários. Corrigido formatando
explicitamente cada valor monetário com `_como_moeda()` (quantiza para duas
casas e converte para string) antes de colocá-lo na resposta. Esse mesmo
ajuste também revelou uma diferença de comportamento entre SQLite e
PostgreSQL: agregações (`Sum`) sobre `DecimalField` no SQLite local não
preservam a escala de duas casas da forma como o PostgreSQL preserva —
`_como_moeda()` normaliza isso com `.quantize(Decimal("0.01"))`,
independentemente do banco.

Teste manual de ponta a ponta via HTTP real (`manage.py runserver` na porta
8005, usuário `gestor` vinculado a um escritório de teste):

1. Criadas as contas "Caixa" (1.1, ativo/devedora) e "Capital Social" (2.1,
   patrimônio líquido/credora) via API.
2. Lançamento de integralização de capital (débito Caixa 1000,00 / crédito
   Capital Social 1000,00): `201`.
3. Diário lista o lançamento; Razão da conta Caixa mostra saldo final
   "1000.00"; Balancete mostra "1000.00" para ambas as contas.
4. Estorno do lançamento: `201`, com débito e crédito invertidos.
5. Balancete após o estorno: "0.00" para ambas as contas.
6. Tentativa de estornar o próprio estorno: `400`.

**Limitação registrada:** validado apenas com SQLite local, sem Docker. O
caminho com PostgreSQL real é responsabilidade do workflow
`.github/workflows/backend.yml` (herdado da DL-002); o resultado deve ser
conferido no PR — é especialmente relevante aqui, dada a diferença de
comportamento do SQLite com `Sum` sobre `DecimalField` observada durante a
validação.

## Riscos, limitações e próximos passos

- **Rebase pendente:** este PR precisa ser reapontado conforme os PRs
  anteriores (#2 a #5) forem integrados, na ordem correta.
- **Sem lançamento automático:** os módulos futuros (Fiscal, Folha,
  Honorários) precisarão gerar lançamentos chamando
  `apps.contabilidade.services.criar_lancamento` a partir de suas próprias
  regras — nenhuma integração automática existe ainda.
- **Sem Balanço Patrimonial nem DRE:** o Balancete atual é a base para
  esses relatórios, mas a classificação e apresentação formais ficam para
  quando houver demanda real por eles.
- **Sem bloqueio formal de período:** a imutabilidade do lançamento já
  impede alteração silenciosa, mas o fechamento/reabertura de competência
  descrito no escopo ainda não existe como conceito.
- **Sem interface server-rendered:** módulo disponível só via API e admin
  nesta etapa.
- **Próxima etapa sugerida:** de acordo com a decisão do responsável pelo
  produto, escolher o próximo fluxo entre Honorários, Processos/Paralegal
  ou Fiscal (XML de NF-e), em PR independente.

Hash do commit, link do PR, resultado da CI e eventuais ajustes serão
registrados na descrição do PR e no relatório de entrega; não inserir
identificadores fictícios neste documento.
