# DL-003 — Fundação: autenticação e multiempresa

## Objetivo e diagnóstico

Implementar a base de autenticação e de isolamento entre escritórios que
todos os módulos de negócio (Fiscal, Folha, Contabilidade, Honorários,
Processos/Paralegal) vão depender. Esta é uma fatia da etapa "Fundação"
prevista no [README](../../README.md) — o cadastro central de empresas e
estabelecimentos, a matriz fina de permissões por módulo/operação e a
auditoria completa ficam para incrementos seguintes (DL-004, DL-005), para
não concentrar mudanças sem relação direta em um único PR, conforme a seção
6 do [AGENTS.md](../../AGENTS.md).

Na inspeção inicial desta demanda, o projeto Django criado na DL-002 tinha
apenas o app `core` com um endpoint de verificação de saúde; não existia
usuário customizado, login, nem qualquer modelo de negócio.

**Dependência entre PRs:** o PR desta etapa é encadeado ao PR #2 (DL-002,
ainda não integrado). A branch `feat/dl-003-fundacao-multiempresa` parte de
`feat/dl-002-arquitetura-fundacao` e o PR desta etapa deve ter como base
essa branch, não a `main`. Depois que o PR #2 for integrado, este PR precisa
ser reapontado (rebase/retarget) para `main` antes do merge.

## Decisões desta etapa

| Decisão | Escolha | Motivo |
| --- | --- | --- |
| Modelo de usuário | `apps.accounts.Usuario`, estendendo `AbstractUser` com e-mail único e obrigatório | Necessário definir o `AUTH_USER_MODEL` antes de qualquer migração real ser aplicada em ambiente compartilhado; e-mail único é pré-requisito para recuperação de senha e notificações futuras. Login continua por `username` (padrão do Django) nesta etapa; migrar para login por e-mail é uma decisão reversível, avaliável depois se houver necessidade real. |
| Isolamento entre escritórios | Modelo `Escritorio` + `VinculoUsuarioEscritorio` (usuário, escritório, papel), com `UniqueConstraint` por par usuário/escritório | Corresponde ao princípio "Isolamento entre escritórios e controle de acesso por empresa e operação" do escopo funcional. Um usuário pode ter vínculo com mais de um escritório, cada um com papel próprio. |
| Papéis | `Papel` (choices): administrador, gestor, analista, financeiro, paralegal, cliente | Lista de perfis já definida em `docs/escopo.md`. A matriz fina de permissão por módulo/operação é tratada em incremento futuro; aqui só a informação mínima de papel já é persistida. |
| Escritório ativo | Middleware `EscritorioAtivoMiddleware`, guardando o ID na sessão e **revalidando contra o vínculo do usuário a cada requisição** | Implementa o "seletor visível" previsto no escopo sem confiar apenas no valor armazenado na sessão — o vínculo é sempre reconferido no banco. Seleção automática quando o usuário tem só um escritório. |
| Autenticação | Views padrão do Django (`LoginView`/`LogoutView`), sessão compartilhada com a API DRF | Coerente com a escolha de frontend server-rendered; evita implementar um esquema de token separado sem necessidade concreta ainda. |
| Frontend desta etapa | HTML simples com formulário padrão, sem HTMX/Alpine | Não há ainda atualização parcial de página que justifique JavaScript; HTMX/Alpine entram quando uma tela realmente precisar, evitando complexidade prematura. |

## Etapa e entregáveis

- Estado deste registro: `em validação`.
- Branch de trabalho: `feat/dl-003-fundacao-multiempresa` (baseada em
  `feat/dl-002-arquitetura-fundacao`).
- Destino: `feat/dl-002-arquitetura-fundacao` (temporário, até a DL-002 ser
  integrada; depois, `main`).
- Entregáveis:
  - App `apps/accounts`: modelo `Usuario`, admin, testes.
  - App `apps/tenancy`: modelos `Escritorio` e `VinculoUsuarioEscritorio`,
    admin, middleware de escritório ativo, views (API e server-rendered),
    templates de login e painel, testes.
  - `AUTH_USER_MODEL`, `LOGIN_URL`, `LOGIN_REDIRECT_URL`,
    `LOGOUT_REDIRECT_URL` configurados em `config/settings.py`.
  - Migrações iniciais dos dois novos apps.
  - Exclusão de `*/migrations/*` do lint/formatação do Ruff (arquivos
    gerados automaticamente, com linhas longas inerentes ao Django).
- Dependências: PR #2 (DL-002) integrado antes do merge final deste PR.
- Fora do escopo: cadastro de empresas/estabelecimentos, matriz fina de
  permissões por módulo e operação, auditoria, recuperação de senha,
  MFA, portal do cliente.

## Critérios de aceite

- Login com credenciais válidas autentica e redireciona ao painel; com
  credenciais inválidas, mostra erro sem autenticar.
- Usuário com vínculo a um único escritório tem esse escritório selecionado
  automaticamente como ativo.
- Endpoint `GET /api/escritorios/` retorna somente os escritórios aos quais
  o usuário autenticado tem vínculo ativo — nunca os de outro escritório.
- `POST /api/escritorio-ativo/` rejeita (403) tentativa de ativar um
  escritório ao qual o usuário não tem vínculo ativo.
- Endpoints protegidos exigem autenticação (401/403 para requisição
  anônima).
- Logout funciona via POST (exigência do Django 5+ por segurança) e
  invalida a sessão — acesso a página protegida depois do logout volta a
  exigir login.
- `VinculoUsuarioEscritorio` impede dois vínculos para o mesmo par
  usuário/escritório.
- `manage.py check`, `manage.py migrate` em banco vazio, `pytest`,
  `ruff check` e `ruff format --check` passam.

## Cenários de teste

| Cenário | Resultado esperado | Cobertura |
| --- | --- | --- |
| E-mail duplicado ao criar usuário | Erro de integridade | `apps/accounts/tests/test_models.py` |
| `__str__` do usuário sem/com nome completo | Usa `username` ou nome completo | `apps/accounts/tests/test_models.py` |
| Dois vínculos para o mesmo par usuário/escritório | Erro de integridade | `apps/tenancy/tests/test_models.py` |
| Login válido / inválido | Redireciona / mostra erro | `apps/accounts/tests/test_login.py` |
| Endpoint de escritórios sem autenticação | 401/403 | `apps/tenancy/tests/test_isolamento.py` |
| Usuário A consulta `/api/escritorios/` | Só retorna o escritório do usuário A, nunca o do usuário B | `apps/tenancy/tests/test_isolamento.py` |
| Usuário com um único vínculo acessa a API de escritório ativo | Escritório correto já aparece selecionado | `apps/tenancy/tests/test_isolamento.py` |
| Usuário A tenta ativar o escritório do usuário B | 403 | `apps/tenancy/tests/test_isolamento.py` |
| Acesso ao painel sem login | Redireciona para o login | `apps/tenancy/tests/test_isolamento.py` |

Além da suíte automatizada, o fluxo completo foi exercitado manualmente via
HTTP real (`manage.py runserver` + `curl`, com sessão e CSRF), incluindo
login, consulta da API autenticada, acesso anônimo negado e logout — ver
"Validação reproduzível".

## Impacto em segurança, dados, cálculos, contratos e desempenho

- **Segurança:** todo endpoint de negócio agora exige autenticação por
  padrão (`DEFAULT_PERMISSION_CLASSES = IsAuthenticated`, já configurado na
  DL-002). O isolamento entre escritórios é aplicado no servidor (view e
  middleware), nunca apenas na interface. Um identificador de escritório
  recebido do cliente (sessão ou corpo da requisição) nunca é aceito sem
  revalidar o vínculo do usuário autenticado no banco.
- **Dados:** dois novos modelos persistidos (`Usuario`, `Escritorio`,
  `VinculoUsuarioEscritorio`); nenhum dado de negócio dos módulos ainda.
- **Cálculos:** não aplicável.
- **Contratos:** novos endpoints:
  - `GET /api/escritorios/` — lista escritórios do usuário autenticado.
  - `GET /api/escritorio-ativo/` — consulta o escritório ativo na sessão.
  - `POST /api/escritorio-ativo/` — define o escritório ativo (valida
    vínculo).
  - `GET|POST /login/`, `POST /logout/` — autenticação padrão do Django.
- **Desempenho:** consultas de vínculo usam `select_related`/`distinct`
  sobre um volume ainda muito pequeno; sem impacto mensurável nesta etapa.

## Estratégia de reversão

Nenhum dado de produção existe ainda. Reversão: fechar o PR antes do merge
ou propor um commit de reversão em novo PR após integração. Como
`AUTH_USER_MODEL` não pode ser trocado depois de existirem migrações
aplicadas em um ambiente compartilhado, qualquer reversão **antes** do
primeiro deploy real é seguro; depois disso, trocar o modelo de usuário
exigiria uma migração de dados dedicada, não uma reversão simples — por
isso este ponto está destacado como comentário no código
(`config/settings.py`).

## Validação reproduzível

Executado localmente em ambiente Windows, Python 3.14, dentro do mesmo
ambiente virtual criado na DL-002:

```sh
python manage.py makemigrations accounts tenancy
python manage.py check
python manage.py migrate
pytest
ruff check .
ruff format --check .
```

Resultados obtidos em 11/09/2026:

- `manage.py check`: nenhum problema encontrado.
- `manage.py migrate` em banco vazio (SQLite local): todas as migrações,
  incluindo `accounts.0001_initial` e `tenancy.0001_initial`, aplicaram sem
  erro.
- `pytest`: 11 testes executados, 11 aprovados.
- `ruff check .` e `ruff format --check .`: sem apontamentos (após excluir
  `*/migrations/*` da checagem, por serem arquivos gerados).

Teste manual de ponta a ponta via HTTP real (`manage.py runserver` na porta
8002 e `curl` com arquivo de cookies e token CSRF extraído da própria
página):

1. Criado usuário `smoke` e um vínculo com o `Escritorio Smoke` via
   `manage.py shell`.
2. `POST /login/` com credenciais válidas: `302` para `/`.
3. `GET /` (painel) autenticado: `200`, exibindo "Escritório ativo:
   Escritorio Smoke" — confirma a seleção automática do middleware.
4. `GET /api/escritorios/` autenticado: retorna só o escritório do usuário
   de teste.
5. `GET /api/escritorios/` sem sessão: `403`.
6. `POST /logout/` (com CSRF, conforme exigido pelo Django 5+): `302` para
   `/login/`.
7. `GET /` após logout: `302` para `/login/` — sessão de fato invalidada.

**Bug encontrado e corrigido durante esta validação:** o template inicial do
painel usava um link (`<a href>`, método GET) para logout. A partir do
Django 5.0, `LogoutView` só aceita `POST` (mudança de segurança contra
logout disparado por terceiros via GET). O template foi corrigido para um
formulário `POST` com token CSRF, e o cenário foi reexecutado com sucesso
(passo 6 acima).

**Limitação registrada:** validado apenas com SQLite local, sem Docker.
O caminho com PostgreSQL real é responsabilidade do workflow
`.github/workflows/backend.yml` (herdado da DL-002); o resultado deve ser
conferido no PR.

## Riscos, limitações e próximos passos

- **Rebase pendente:** este PR precisa ser reapontado para `main` assim que
  o PR #2 (DL-002) for integrado, conforme descrito em "Etapa e
  entregáveis".
- **Sem matriz de permissões fina:** o `papel` de cada vínculo ainda não
  bloqueia operações específicas por módulo; isso é necessário antes de
  qualquer módulo de negócio (Fiscal, Folha etc.) ser implementado.
- **Sem auditoria:** ações de login, troca de escritório e futuras
  operações de escrita ainda não geram registro de auditoria.
- **Sem recuperação de senha nem MFA:** fora do escopo desta etapa.
- **Próxima etapa sugerida:** cadastro central de empresas e
  estabelecimentos vinculados a um escritório (DL-004), seguido da matriz
  de permissões por módulo/operação e auditoria (DL-005).

Hash do commit, link do PR, resultado da CI e eventuais ajustes serão
registrados na descrição do PR e no relatório de entrega; não inserir
identificadores fictícios neste documento.
