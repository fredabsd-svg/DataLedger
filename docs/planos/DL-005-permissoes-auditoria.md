# DL-005 — Permissões por papel e auditoria

## Objetivo e diagnóstico

Fechar a etapa "Fundação" do [README](../../README.md) com duas peças que
faltavam depois da DL-003 (autenticação e isolamento entre escritórios) e
da DL-004 (cadastro central de empresas): restringir operações de escrita
por papel do vínculo, e registrar auditoria das ações relevantes (AGENTS.md,
seção 11: "Registrar ator, contexto, operação e resultado com proteção das
informações sensíveis").

Na inspeção inicial desta demanda, qualquer papel vinculado a um escritório
podia criar empresas e estabelecimentos, e nenhuma ação gerava registro de
auditoria — nem login, nem troca de escritório, nem cadastro.

**Dependência entre PRs:** a branch `feat/dl-005-permissoes-auditoria` parte
de `feat/dl-004-cadastro-empresas` (PR #4, ainda não integrado, que depende
dos PRs #2 e #3). O PR desta etapa precisa ser reapontado para `main`
conforme os PRs anteriores forem integrados, na ordem correta.

## Decisões desta etapa

| Decisão | Escolha | Motivo |
| --- | --- | --- |
| Granularidade da permissão | Por papel do vínculo (`request.papel`, resolvido pelo middleware da DL-003), não por operação individual | Suficiente para o primeiro corte: administrador/gestor podem escrever, os demais papéis (analista, financeiro, paralegal, cliente) só leem. Uma matriz por módulo/operação mais fina é adiável até existir um módulo de negócio real pedindo por ela — evita desenhar permissões para funcionalidades que ainda não existem. |
| Quem pode escrever cadastro de empresa | `administrador` e `gestor` (`apps.tenancy.permissions.papel_permitido`) | Corresponde ao papel dessas duas funções no escopo (gestão do escritório); os demais continuam podendo consultar. |
| Onde a auditoria vive | App dedicado `apps.auditoria`, com um serviço único (`registrar`) chamado pelos outros apps | Evita duplicar a lógica de gravação em cada view; qualquer módulo futuro (Fiscal, Folha etc.) reaproveita o mesmo serviço. |
| O que é auditado nesta etapa | Login (sucesso/falha), logout, ativação de escritório, criação de empresa, criação de estabelecimento, registro de regime tributário | Cobre as ações de escrita e de controle de acesso que já existem no sistema. Módulos futuros deverão chamar `apps.auditoria.services.registrar` em suas próprias operações de escrita. |
| Dados sensíveis em auditoria | `detalhes` (JSON) nunca recebe senha, token ou documento pessoal completo; falha de login grava só o `username` tentado | Aplica diretamente a exigência de proteção de dados sensíveis nos registros de auditoria (AGENTS.md, seção 11). |
| Exclusão de usuário/escritório | `usuario`/`escritorio` em `RegistroAuditoria` usam `SET_NULL` | A auditoria não pode desaparecer se o ator ou o escritório forem removidos depois. |
| Consulta de auditoria | Só administrador/gestor, escopada ao escritório ativo | Auditoria revela informação operacional sobre outros usuários; não deve vazar entre escritórios nem para qualquer papel. |

## Etapa e entregáveis

- Estado deste registro: `em validação`.
- Branch de trabalho: `feat/dl-005-permissoes-auditoria` (baseada em
  `feat/dl-004-cadastro-empresas`).
- Destino: `feat/dl-004-cadastro-empresas` (temporário, até a cadeia de PRs
  anteriores ser integrada; depois, `main`).
- Entregáveis:
  - App `apps/auditoria`: modelo `RegistroAuditoria`, serviço `registrar`,
    endpoint de listagem (`GET /api/auditoria/`), admin somente leitura.
  - `apps/tenancy/permissions.py`: fábrica `papel_permitido(*papeis)`.
  - Sinais de login/logout/falha de login conectados à auditoria
    (`apps/accounts/signals.py`, carregados em `AccountsConfig.ready`).
  - Auditoria conectada a: ativação de escritório (API e server-rendered),
    criação de empresa (API e server-rendered), criação de estabelecimento,
    registro de regime tributário.
  - Restrição de papel (administrador/gestor) em: criação/edição de
    empresa, criação de estabelecimento, registro de regime tributário,
    consulta de auditoria.
  - Migração inicial do app `auditoria`.
- Dependências: PRs #2, #3 e #4 integrados antes do merge final deste PR.
- Fora do escopo: matriz de permissão por operação individual (além do
  corte administrador/gestor vs. demais), interface de consulta de
  auditoria (só API/admin nesta etapa), retenção/expurgo de auditoria
  antiga, auditoria de leitura (só escrita e controle de acesso por
  enquanto).

## Critérios de aceite

- Um usuário com papel diferente de administrador/gestor recebe 403 ao
  tentar criar empresa, estabelecimento ou registrar regime tributário —
  tanto pela API quanto pela tela server-rendered — mas continua
  conseguindo consultar (listar) normalmente.
- Login com sucesso, login com falha, ativação explícita de escritório,
  criação de empresa, criação de estabelecimento e registro de regime
  tributário geram um `RegistroAuditoria` correspondente.
- Nenhum registro de auditoria de falha de login contém a senha
  informada.
- `GET /api/auditoria/` só retorna registros do escritório ativo da
  requisição, e só para administrador/gestor.
- `manage.py check`, `manage.py migrate` em banco vazio, `pytest`,
  `ruff check` e `ruff format --check` passam.

## Cenários de teste

| Cenário | Resultado esperado | Cobertura |
| --- | --- | --- |
| `registrar()` com usuário/escritório explícitos | Grava os campos corretamente | `apps/auditoria/tests/test_services.py` |
| `registrar()` com objeto e detalhes | Grava tipo/ID do objeto e o dicionário de detalhes | `apps/auditoria/tests/test_services.py` |
| `registrar()` a partir de uma `request` | Infere usuário, escritório ativo e IP | `apps/auditoria/tests/test_services.py` |
| Login com sucesso | Cria registro `login.sucesso` vinculado ao usuário | `apps/auditoria/tests/test_login_signals.py` |
| Login com falha | Cria registro `login.falha` com só o username, sem a senha | `apps/auditoria/tests/test_login_signals.py` |
| Ativar escritório explicitamente (usuário com 2+ vínculos) | Cria registro `escritorio.ativado` | `apps/tenancy/tests/test_isolamento.py` |
| Papel cliente tenta criar empresa | 403, nenhuma empresa criada | `apps/empresas/tests/test_permissoes.py` |
| Papel gestor cria empresa | 201 e gera registro `empresa.criada` | `apps/empresas/tests/test_permissoes.py` |
| Papel cliente consulta empresas | Continua permitido (200) | `apps/empresas/tests/test_permissoes.py` |
| Papel cliente consulta auditoria | 403 | `apps/auditoria/tests/test_listagem.py` |
| Administrador consulta auditoria | Só vê registros do próprio escritório | `apps/auditoria/tests/test_listagem.py` |

Fluxo completo também validado manualmente via HTTP real
(`manage.py runserver` + `curl`, dois usuários com papéis diferentes no
mesmo escritório): cliente recebe 403 ao abrir a tela de nova empresa,
gestor consegue abrir e criar, e a auditoria resultante (`empresa.criada`)
aparece para o gestor e é bloqueada (403) para o cliente — ver "Validação
reproduzível".

## Impacto em segurança, dados, cálculos, contratos e desempenho

- **Segurança:** escrita de cadastro agora exige papel administrador ou
  gestor, verificado no servidor (permissão DRF e checagem explícita na
  view server-rendered), nunca só ocultando o botão na tela. Auditoria
  registra ator, ação, objeto e IP, sem gravar segredos.
- **Dados:** um novo modelo (`RegistroAuditoria`), sem alterar os modelos
  de negócio existentes.
- **Cálculos:** não aplicável.
- **Contratos:** novo endpoint `GET /api/auditoria/`; contratos existentes
  de empresa/estabelecimento/regime tributário passam a exigir papel
  administrador/gestor nas operações de escrita (mudança de comportamento,
  mas sem PR anterior integrado em produção — não há contrato quebrado em
  uso real).
- **Desempenho:** `RegistroAuditoria` cresce a cada ação relevante; o
  índice padrão de `escritorio` (chave estrangeira) sustenta o volume
  inicial. Estratégia de retenção/expurgo fica para quando o volume real
  justificar.

## Estratégia de reversão

Nenhum dado de produção existe ainda. Reversão: fechar o PR antes do merge
ou propor um commit de reversão em novo PR após integração.

## Validação reproduzível

Executado localmente em ambiente Windows, Python 3.14, no mesmo ambiente
virtual das etapas anteriores:

```sh
python manage.py makemigrations auditoria
python manage.py check
python manage.py migrate
pytest
ruff check .
ruff format --check .
```

Resultados obtidos em 11/09/2026:

- `manage.py check`: nenhum problema encontrado.
- `manage.py migrate` em banco vazio: `auditoria.0001_initial` aplicou sem
  erro, junto com as migrações das etapas anteriores.
- `pytest`: 36 testes executados, 36 aprovados (24 herdados das etapas
  DL-002 a DL-004 + 12 novos desta etapa).
- `ruff check .` e `ruff format --check .`: sem apontamentos.

Teste manual de ponta a ponta via HTTP real (`manage.py runserver` na porta
8004, dois usuários — `gestor` e `cliente` — vinculados ao mesmo
escritório de teste com papéis diferentes):

1. Login como `cliente` → `GET /empresas/nova/`: `403`.
2. Login como `gestor` → `GET /empresas/nova/`: `200`.
3. `gestor` cria uma empresa pelo formulário: redireciona com sucesso.
4. `gestor` consulta `GET /api/auditoria/`: retorna o registro
   `empresa.criada` correspondente.
5. `cliente` consulta `GET /api/auditoria/`: `403`.

**Observação de design confirmada no teste manual:** o registro
`login.sucesso` não aparece na listagem de auditoria porque, no momento do
login, o middleware ainda não resolveu nenhum escritório ativo (o usuário
acabou de autenticar); a listagem é sempre filtrada pelo escritório ativo
da requisição. Isso é intencional — auditoria de negócio é escopada por
escritório, e o evento de login em si ainda não tem um.

**Limitação registrada:** validado apenas com SQLite local, sem Docker. O
caminho com PostgreSQL real é responsabilidade do workflow
`.github/workflows/backend.yml` (herdado da DL-002); o resultado deve ser
conferido no PR.

## Riscos, limitações e próximos passos

- **Rebase pendente:** este PR precisa ser reapontado conforme os PRs
  anteriores (#2, #3 e #4) forem integrados, na ordem correta.
- **Sem matriz de permissão por operação individual:** o corte atual é
  binário (administrador/gestor vs. demais papéis). Módulos futuros podem
  precisar de papéis intermediários (ex.: financeiro podendo registrar
  cobranças, mas não editar cadastro de empresa) — reavaliar quando esse
  módulo for implementado.
- **Sem UI de consulta de auditoria:** disponível só via API/admin nesta
  etapa.
- **Sem retenção/expurgo de auditoria:** decisão adiada até haver volume
  real que justifique uma política.
- **Próxima etapa sugerida:** com a Fundação completa (autenticação,
  multiempresa, cadastro de empresas, permissões básicas e auditoria), a
  etapa 4 do roadmap do README pode começar — primeiro módulo de negócio
  (Paralegal ou Fiscal, a decidir), sempre em PRs independentes por fluxo.

Hash do commit, link do PR, resultado da CI e eventuais ajustes serão
registrados na descrição do PR e no relatório de entrega; não inserir
identificadores fictícios neste documento.
