# DL-036 — Página inicial e cadastro de uma nova empresa

**Estado:** em desenvolvimento. **Demanda:** Fred, 25/09/2026: primeira tela
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

Resultados finais, auditoria e PR serão registrados após execução. Merge e
implantação não autorizados nesta demanda. Abertura do PR integra o escopo.
