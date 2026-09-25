# DL-036 — Página inicial e cadastro de uma nova empresa

**Estado:** em revisão. **Demanda:** Fred, 25/09/2026: primeira tela
com cadastro para empresa nova e apresentação profissional do DataLedger.
**Branch:** `feat/dl-036-entrada-e-cadastro`, destino `main`.

## Objetivo e escopo

Completar a entrada que a DL-018 deixou dependente de usuário criado por terminal.
Visitante acessa apresentação pública, escolhe cadastrar empresa ou entrar; cadastro
cria usuário comum, escritório e vínculo administrador em uma transação auditada.
O escritório é o espaço de trabalho; empresas clientes continuam no cadastro interno.
Não alterar cálculos, relatórios, permissões existentes nem publicar em produção.

## Entregáveis e critérios de aceite

1. `/` pública, responsiva, com ações claras de cadastro e login; sessão existente
   mantém o painel. Landing, login e cadastro compartilham identidade visual e
   funcionam sem JavaScript, com foco, rótulos e mensagens acessíveis.
2. Cadastro valida nome, e-mail, CNPJ e senha; mantém entradas não sensíveis no erro.
   Sucesso abre o painel com escritório ativo, sem terminal nem `/admin/`.
3. Duplicidade, entrada inválida e falha na gravação não deixam usuário/escritório
   órfão. Cadastro não aceita papel, privilégio ou escritório de terceiros.
4. Contas antigas continuam entrando por usuário; novas entram pelo e-mail.
   Nenhum dado de cliente, convite ou token aparece nas páginas públicas.
5. Recursos em apresentação correspondem ao produto; exemplos são identificados.

## Validação e riscos

Nível 1 para criação da fronteira de isolamento; nível 2 para apresentação.
Testar navegação, cadastro real, erro, duplicidade, CSRF, rollback e isolamento;
regressão de login/tenancy, suíte, lint, Django check, migrações e collectstatic.
Inspeção Chromium desktop/mobile e auditoria independente da versão integrada.
Baseline antes da alteração: `pytest apps/accounts/tests apps/tenancy/tests -q`:
**68 passed, 1 warning in 2.22s**, SQLite local. Aviso preexistente de locks
contábeis indisponíveis em SQLite; CI usa PostgreSQL. Suíte completa em levantamento.

Sem migração prevista. Não há confirmação de e-mail/SMTP nesta etapa; cadastrar
conta não prova titularidade jurídica do CNPJ e não concede acesso a outro espaço.
Reversão: reverter o commit de aplicação; preservar contas e escritórios criados.
Docker e produção só serão declarados testados com execução comprovada.

## Evidências e entrega

PR [#45](https://github.com/fredabsd-svg/DataLedger/pull/45), publicado pela conexão
GitHub. Código local `353c9ed` e remoto `279707f` têm a mesma árvore `3a7b0f7`.

Evidências executadas (Python 3.12, dependências fixadas do projeto):

```text
pytest accounts + tenancy + interface + documentação + contratos:
352 passed, 1 warning in 3.56s
ruff check .: All checks passed!
ruff format --check .: 228 files already formatted
manage.py check: System check identified no issues (0 silenced).
manage.py makemigrations --check --dry-run: No changes detected
manage.py collectstatic --noinput: 164 static files copied, 474 post-processed
```

Chromium 153: landing/login/cadastro em 1440×1000 e 390×844, sem overflow;
inspeção das capturas desktop/mobile. E2E mobile sem JavaScript, SQLite migrado:

```text
Cadastro mobile sem JavaScript: erro acessível, sucesso e escritório ativo confirmados
Logout e novo login com caixa original do e-mail: aprovados
```

Auditoria independente do cadastro: **APROVADO**, 30 testes e experimento SQL
real de colisão/rollback, escape, isolamento e recusa de redirecionamento externo.
Relatório em [auditoria DL-036](../auditorias/2026-09-25-dl-036.md).

A suíte completa local para no teste contábil
`test_codigo_repetido_na_mesma_empresa_retorna_400_nao_500`:
`1 failed, 69 passed, 5 warnings in 3.73s`. Reproduzido na main intacta
`4c19715` com SQLite: `1 failed in 1.39s`. Não é alteração desta demanda.
CI com PostgreSQL em acompanhamento no PR; não declarada aprovada antecipadamente.

Correção operacional adicional: removido apenas o volume de estáticos do serviço
web. WhiteNoise passa a usar o CSS coletado na imagem; volume antigo mascarava
estáticos novos após rebuild. Volume PostgreSQL preservado. Docker não está
disponível neste ambiente: mudança inspecionada, contêiner não executado. Merge e
implantação não autorizados nesta demanda. Abertura do PR integra o escopo.


## Integração e correção da cobertura

A primeira execução PostgreSQL no GitHub encontrou **2 failed, 2187 passed,
45 skipped**: o espelho de URLs da suíte de acessibilidade não conhecia `cadastro`
e a lista de cobertura não classificava a nova tela. Foram atualizados o espelho
e o universo de telas, com testes reais de acessibilidade do cadastro e da landing.
Nenhuma regra de produção ou expectativa de segurança foi enfraquecida.

Validação local após correção: `390 passed, 26 warnings in 4.15s`; lint e formatação
aprovados. Os avisos são de locks contábeis indisponíveis no SQLite local.
Reconferência independente do delta Docker: **APROVADO**, YAML analisado,
volume PostgreSQL preservado e estáticos coletados na imagem confirmados.

A evidência vigente da CI pertence ao commit mais recente do PR #45; não se
transporta aprovação entre hashes. Verificar os checks do PR antes de integrar.


## Correção de posicionamento solicitada pelo Fred — 25/09/2026

A primeira apresentação adotou linguagem de SaaS convencional e omitiu o papel
central dos modelos de IA na concepção do DataLedger. Fred rejeitou esse
posicionamento e solicitou correção no mesmo PR. Referências relidas:
`docs/escopo.md` (Assistente de IA, MCP e arquitetura), plano mestre §14,
DL-002 e decisões DE-014/DE-042 (implantação e primeiro acesso).

Critérios da revisão (nível 2, interface e texto): apresentar o sistema de Fiscal,
Folha e Contabilidade concebido para trabalhar com IA; explicitar assistente,
provedores e MCP como planejados; substituir a vitrine de lançamentos por visão
de arquitetura; orientar a entrada por **Configurar meu ambiente** e **Entrar no
sistema**. Cadastro cria o administrador do próprio escritório, não superusuário
da plataforma. Preservar a arquitetura multiempresa autorizada e as regras de
isolamento existentes; esta revisão não cria bloqueio global de instalação nem
implementa integrações de IA.

README e escopo alinhados à correção. Verificação: páginas públicas, acesso aos
formulários, validação/isolamento já cobertos, acessibilidade e inspeção visual
responsiva. Evidência da nova revisão será publicada no PR #45; resultados dos
commits anteriores acima são históricos, não aprovação antecipada desta revisão.

Validação executada desta correção: `390 passed, 26 warnings in 2.24s`;
`ruff check .`: `All checks passed!`; `ruff format --check .`:
`228 files already formatted`. Chromium: três páginas em 1440 e 390 pixels,
HTTP 200 e sem overflow; CTA de configuração abre formulário e erros de campos
são exibidos sem JavaScript. Capturas desktop/mobile inspecionadas. Apenas texto,
rótulos e apresentação alterados; regras de cadastro e permissões preservadas.
