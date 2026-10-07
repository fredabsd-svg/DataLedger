# Análise de segurança e isolamento entre escritórios — 07/10/2026

**Auditor:** `auditor-qa` (subagente em modelo `sonnet`, acionado pelo
`arquiteto-senior`). **Revisão:** `d5cc6bf` (igual à `origin/main` na data).
**Origem:** ordem do Fred de 07/10/2026, *"Analise meu repositório"*. Foi uma
análise, não auditoria de uma etapa `DL`. **Modo:** somente leitura. As
reproduções rodaram em banco próprio (`dataledger_auditor`), apagado ao
final, e `git status` ficou limpo.

**Registro do arquiteto:** o parecer abaixo foi transcrito **integralmente**,
sem edição, supressão nem suavização de achado. Há duas intervenções, e
nenhuma altera achado: os sinais de menor e maior dentro de código voltaram
à forma literal, e o **endereço** de e-mail pessoal citado no A13 foi
omitido, porque transcrevê-lo criaria uma terceira cópia de dado pessoal num
repositório público. O achado A13 permanece inteiro. O desdobramento de cada achado está no
[backlog](../projeto/backlog.md) (BL-632 a BL-641). Os itens A1, A2, A3(b),
BL-82 e BL-577 entraram na [DL-068](../planos/DL-068-prontidao-para-implantacao.md).

Conferência independente do arquiteto sobre A2: as notas oficiais do Django
6.1.2 (<https://docs.djangoproject.com/en/dev/releases/6.1.2/>), consultadas em
07/10/2026, confirmam a data de 06/10/2026 e os quatro CVEs citados
(CVE-2026-77050 baixo; CVE-2026-84429, CVE-2026-87890 e CVE-2026-87975
moderados).

---

## Parecer do auditor

**Parecer preliminar para decisão do arquiteto-senior:** não encontrei
BLOQUEADOR nem GRAVE. O isolamento entre escritórios se sustentou em todas as
rotas que consegui exercitar (item 1 abaixo). Sobram 3 achados MÉDIOS e 7
BAIXOS, mais itens informativos.

Este parecer não declara ausência de bugs nem segurança absoluta. A suíte
`pytest` completa não foi executada, porque outro agente a roda em paralelo.

Para as reproduções usei o banco próprio `dataledger_auditor` e scripts na
pasta de rascunho. O banco foi apagado ao fim. `git status` e `git diff`
ficaram limpos, sem efeito colateral na árvore.

### 1. Achados

| # | Sev. | Achado | Evidência | Estado |
|---|---|---|---|---|
| A1 | MÉDIO | **`/admin/login/` não tem limite de tentativas.** O limitador da DL-056 está só no `LoginForm` de `/login/`, e `config/urls.py:11` monta `admin.site.urls` com o formulário padrão. O admin é a superfície mais privilegiada: sem isolamento por escritório (BL-262) e sem 2FA. Cenário: força bruta contra um superusuário sem bloqueio, e a trilha só registra `login.falha`. | `config/urls.py:11,13-20`. Reproduzido: 30 senhas erradas seguidas deram 200, a senha correta em seguida entrou (302 para `/admin/`) e `TentativaDeAcesso` ficou com 0 linhas. Em `/login/`, 8 falhas bloquearam inclusive a senha correta. | Reproduzido. Não é o BL-552 (só cobre `/login/` e cadastro). Relacionado ao BL-596. |
| A2 | MÉDIO | **Django pinado em 6.1.1; o 6.1.2 saiu em 2026-10-06 com 4 CVEs.** Entre eles CVE-2026-84429, DoS moderado no parser de cabeçalhos (`parse_header_parameters`), alcançável sem login em qualquer POST, inclusive `/login/` e `/cadastro/`. CVE-2026-87975 (formsets com PK editável) não afeta o projeto: as PKs são `BigAutoField`. | `requirements/base.txt:5`. Notas de release do 6.1.1 (sem segurança) e do 6.1.2 (4 CVEs), consultadas na documentação do Django. | Inspecionado e consultado na documentação. Versão do pacote conferida com `pip index versions`. |
| A3 | MÉDIO | **Deploy padrão sobe inseguro e a imagem embute segredos.** (a) `.env.example:2` traz `DEBUG=True` e uma chave de exemplo. O `docker-compose.yml` usa `env_file: .env` e publica `8000:8000`, então quem só copia o exemplo sobe com `DEBUG=True` e `SECURE_*` desligados. Nada recusa isso: é o **BL-82** (planejada), e `check --deploy` fica verde com DEBUG falso. (b) Não existe `.dockerignore`, e o `Dockerfile:15` faz `COPY . .`. O `.env` real e o `.git` entram nas camadas da imagem. A senha padrão do banco é `dataledger`. | `.env.example`, `docker-compose.yml`, `Dockerfile:15`. | Inspecionado. Não executei `docker build`. (a) é BL-82 conhecido; (b) não localizei registro. |
| A4 | BAIXO | **`Escritorio.ativo` não tem efeito.** Escritório inativo continua acessível; o middleware só olha o vínculo. | `apps/tenancy/middleware.py:19-31`. Reproduzido: com `ativo=False`, `GET /empresas/` e a API deram 200. Não achei registro disso no backlog. | Reproduzido. |
| A5 | BAIXO | **Trilha de login invisível ao administrador do escritório.** `login.sucesso`, `login.falha` e `login.bloqueado` são gravados com `escritorio=NULL`, porque no login `request.escritorio` ainda é None. A API `/api/auditoria/` filtra por escritório, então o admin não audita o acesso da própria equipe. | `apps/accounts/signals.py:9-37`, `apps/auditoria/services.py:21`, `apps/auditoria/views.py:19-20`. Reproduzido no banco: `escritorio_id=None` em todos os eventos de login. | Reproduzido. |
| A6 | BAIXO | **Excluir escritório pelo admin dá 500.** O `pre_delete` grava `RegistroAuditoria` apontando para o escritório que está sendo apagado, e a FK estoura (`IntegrityError`). Falha fechada, mas contradiz o desenho "a trilha sobrevive". **Latente:** `ConviteEscritorio` está coberto pela trilha e não tem ModelAdmin, então não é redigido. Se a FK for consertada, o `token` do convite entra em claro em `valores_anteriores` (`signals.py:414-420` já reconhece esse limite). | `apps/auditoria/signals.py:529-557`. Reproduzido: `POST /admin/tenancy/escritorio/<id>/delete/` levantou `IntegrityError`, o escritório continuou existindo e não houve token na trilha. | Reproduzido o 500; o vazamento do token é inferido. |
| A7 | BAIXO | **Cadastro fecha `X-Forwarded-Proto` só na premissa do proxy.** `SECURE_PROXY_SSL_HEADER` é fixo quando `DEBUG=False`, mas o compose publica o gunicorn direto, sem proxy. Um cliente pode forjar o cabeçalho e burlar `SECURE_SSL_REDIRECT`. Os cookies seguem `Secure`. Impacto restrito, porém real se alguém implantar usando o compose como está. | `config/settings.py:408`, `docker-compose.yml:ports`. | Inspecionado. |
| A8 | BAIXO | **Upload multipart sem teto global.** O limite de 50 MB (`LimiteDeTamanhoUploadHandler`) só vale em `/fiscal/recepcao/`. O Django grava em disco qualquer multipart (`CsrfViewMiddleware` lê o POST) antes da view, inclusive de anônimo em `/login/`. Mitigação é `client_max_body_size` no proxy, que não está documentada no repositório. | `apps/fiscal/uploads.py`, `config/settings.py` (sem `DATA_UPLOAD_*`). | Inferido, comportamento conhecido do Django. |
| A9 | BAIXO | **Sessões e contas sem endurecimento.** Sessão de 14 dias (padrão), sem expiração por inatividade e sem 2FA, nem para o superusuário. Não existe fluxo de recuperação ou troca de senha no produto. Remover alguém de um escritório exige o admin do Django, sem tela para o administrador do escritório. | `config/settings.py` (sem `SESSION_COOKIE_AGE`), `config/urls.py`. | Inspecionado. |
| A10 | BAIXO | **Cadeia de suprimentos frouxa.** Não há `.lock` com hashes e as dependências transitivas (`asgiref`, `sqlparse`) não são fixadas. As GitHub Actions usam tag (`@v4`), não SHA. A imagem `python:3.14-slim` não tem digest. `psycopg` 3.3.6 e DRF 3.18.3 existem e o pin é 3.3.5 e 3.18.1 (não verifiquei se trazem correção de segurança). | `requirements/*.txt`, `.github/workflows/*.yml`, `Dockerfile:1`. | Inspecionado. |
| A11 | BAIXO | **Token de convite guardado em claro no banco** e trafega no caminho da URL (`/convite/<token>/`), logo vai para logs de acesso. Mitigado: vale 7 dias, uso único e amarrado ao e-mail do usuário. O e-mail não é verificado (**BL-548/HI-47**, conhecido). | `apps/tenancy/models.py:173`, `apps/tenancy/urls.py:17`. | Inspecionado. |
| A12 | BAIXO | **CSV do Carnê-Leão não neutraliza fórmula** (`=`, `+`, `-`, `@` no início do histórico). Só `;` e quebras de linha são recusados. O destino é a Receita, não o Excel, e o autor do texto é interno ao escritório. | `apps/livro_caixa/carne_leao_arquivos.py:130-158`. | Inspecionado. |
| A13 | INFO | O e-mail pessoal do Fred (endereço omitido neste registro — ver nota do arquiteto) está nos metadados dos commits e em dois documentos de um repositório público. | `git log` (autoria), `docs/agents/historico-do-estado.md:557`, `docs/auditorias/2026-09-22-dl-027-fatia-b1-rodada-1.md:7`. | Inspecionado. Decisão do Fred. |
| A14 | INFO | A imutabilidade da trilha existe só na aplicação (signals e queryset). Não há gatilho nem `REVOKE` no banco, então quem usa SQL direto altera a trilha. Mesma família do BL-569. | `apps/auditoria/models.py`, `signals.py`. | Inspecionado. |
| A15 | INFO | O backlog traz BL-51 como "planejada", mas `settings.py:394-433` já implementa HTTPS, cookies Secure e HSTS. O **BL-577** (`/0` em `DJANGO_PROXIES_CONFIAVEIS`) segue aberto, obrigatório antes da implantação, e reconfirmei que a validação ainda aceita `/0`. | `docs/projeto/backlog.md`, `config/settings.py:46-55`. | Inspecionado. |

Conhecidos que reencontrei, sem reportar como novos: BL-262 (admin sem
isolamento por escritório, reconfirmado: staff vê Emp A e Emp B), BL-35 (APIs
sem paginação nem throttle), BL-548 e BL-552 parte 2 (cadastro não prova
e-mail nem CNPJ), BL-82, BL-577.

### 2. Verificado e correto

- **Isolamento web e API (item 1).** Varri todas as rotas de `urls.py` com
  dois escritórios e seis papéis: anônimo, Cliente e Administrador com IDs
  próprios e do outro escritório, e usuário sem vínculo. Cobri contabilidade,
  livro-caixa, empresas, fiscal, módulos e auditoria, com GET, POST, PUT,
  PATCH e DELETE.
  - Todo ID alheio devolveu 404 ou 403. Nenhum 200 com dado do outro
    escritório.
  - POST de estabelecimento, regime e conta de livro-caixa com corpo válido
    na empresa do outro escritório deu 404, sem gravar nada.
  - A validação de corpo que roda antes do escopo (400) é idêntica para ID
    existente, de outro escritório e inexistente, então não há oráculo de
    existência.
- **Contrapartidas (itens 1 e 2).** Contas recebidas no corpo são buscadas
  com `empresa=` (`apps/contabilidade/views.py:733`, `views_web.py:2038`).
  `conta_pai` é restrita à empresa, e há constraint de banco
  `chave_idempotencia_unica_por_empresa`. A idempotência é escopada por
  empresa.
- **Papel Cliente (item 2, DL-055).** Recebeu 403 em toda rota de dado, antes
  de qualquer consulta. A matriz foi aplicada no servidor: Paralegal e
  Cliente não escrituram, e só Administrador e Gestor fecham e reabrem.
- **Convite (item 5, DL-052).** Emitir exige Administrador do escritório alvo
  no serviço. O papel do convite não vem do cliente. O aceite exige e-mail
  igual, prazo de 7 dias e uso único, com trava `select_for_update`.
- **Upload XML e ZIP (item 3).** O parser é `defusedxml` com `forbid_dtd`.
  Reproduzidos e recusados: XXE, billion laughs, ZIP de 300 MB declarados
  (limite de 200 MB), ZIP aninhado e traversal (`../` e `/etc`). Nada é
  gravado por nome de entrada (`/tmp/evil.xml` não existe). Há limite de
  entradas, de tamanho por XML e total. O nome de entrada, mesmo com
  `<script>`, só é exibido com autoescape. O download do XML sai como
  attachment, `application/xml`, `nosniff`, com nome só de dígitos. A CSRF da
  recepção, que é `csrf_exempt` e depois `csrf_protect`, funciona: POST sem
  token deu 403.
- **Configuração (item 4).** `DEBUG` padrão é False e `SECRET_KEY` é
  obrigatória. `ALLOWED_HOSTS` é vazio por padrão. `manage.py check --deploy`
  com `DEBUG=False` passou sem avisos. Cookies de sessão `HttpOnly`/`Lax`,
  `X-Frame-Options: DENY`, `nosniff`, Referrer-Policy e COOP presentes. Não
  há CORS. A sessão cai ao desativar usuário, ao inativar vínculo e ao trocar
  a senha. Não achei `|safe` nem `mark_safe` com dado de usuário e nenhum SQL
  concatenado (só nomes de tabela e coluna do ORM). Todo POST sem token CSRF
  deu 403, inclusive na API de sessão.
- **API (item 5).** Só `SessionAuthentication`, sem Basic. O limitador do
  `/login/` funciona e tem a mesma mensagem para senha errada e bloqueio. Só o
  resumo HMAC do usuário vai para a trilha.
- **Segredos (item 6).** Varredura do repositório inteiro e do histórico (186
  commits) por chaves, tokens, certificados e `.env`: nada. As únicas chaves
  são sintéticas ou de CI. Os CPFs e CNPJs são sintéticos. O `.env` nunca foi
  versionado. O CI não usa secrets e declara permissões mínimas.
- **Trilha (item 7).** Senha e token não aparecem. Reproduzido: senha
  digitada no campo errado não vai à trilha. Campos de senha do admin são
  redigidos por widget. `update`/`delete`/`bulk_update` e instância são
  bloqueados na aplicação.
- **Contêiner (item 9).** O processo roda como usuário não-root, o banco não
  é publicado e a chave do `collectstatic` é descartável.

### 3. Não foi possível verificar

- **Suíte completa** `pytest`, `ruff` e `validate-docs`: não executei, porque
  outro agente roda a suíte.
- **`docker build`/`compose up`:** não construí a imagem, então A3(b) é por
  inspeção.
- **Proxy e implantação reais:** não há proxy no repositório, então não pude
  verificar sanitização de `X-Forwarded-*`, limite de corpo nem TLS.
- **Proteção da branch `main`:** não consultei a API do GitHub, por regra de
  não acessar serviços externos com dados do projeto. O AGENTS.md diz que não
  há proteção.
- **Dependências:** não rodei `pip-audit`. A verificação de CVE foi pelas
  notas de release do Django. Não verifiquei se DRF 3.18.2/3.18.3, psycopg
  3.3.6, gunicorn e WhiteNoise corrigem algo de segurança.
- **Casos não exercitados:**
  - Concorrência e DoS reais (A8, trava de login sob paralelismo).
  - Serialização dos modelos pela API do livro-caixa, além do escopo.
  - Assinatura digital do XML da NFS-e: não vi verificação; por sorte o
    parser não depende dela, mas um usuário do escritório pode enviar XML
    forjado, inclusive evento de cancelamento. Isso é domínio fiscal e eu não
    avaliei se há requisito.
- **Normas contábeis e fiscais:** fora do escopo desta auditoria.

### Propostas de teste (para o responsável implementar)

- **A1:** teste que faz N+1 POSTs em `/admin/login/` com senha errada e exige
  bloqueio, depois exige 200 recusado para a senha correta.
- **A4:** teste com `Escritorio.ativo=False` exigindo 403 em
  `/empresas/api/empresas/` e na web.
- **A5:** teste de que `login.sucesso` aparece na API `/api/auditoria/` do
  administrador do escritório ativo do usuário.
- **A6:** teste de exclusão de escritório pelo admin com convite pendente,
  exigindo que não vá a 500 e que `valores_anteriores` não contenha o token.
