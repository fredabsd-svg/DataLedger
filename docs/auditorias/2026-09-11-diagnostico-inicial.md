# Diagnóstico inicial — 2026-09-11

Relatório do diagnóstico distribuído durante a configuração da equipe de
agentes. Registrado pelo `arquiteto-senior`, que **preserva integralmente os
achados** de quem os produziu.

## Escopo e método

| Item | Valor |
| --- | --- |
| Revisão auditada | `279e7bc` (`main`; a branch de trabalho estava idêntica à `main`) |
| Data | 2026-09-11 |
| Método | Análise estática dos arquivos do repositório, por três agentes independentes, em paralelo, **somente leitura** |
| Execução de testes | Feita **pelo `arquiteto-senior`**, em ambiente separado, não pelos agentes de diagnóstico |

**Limitação declarada:** os três diagnósticos foram estáticos. Nenhum deles
executou a suíte de testes, inspecionou o banco em execução nem verificou as
proteções de branch do GitHub. Isso limita o que pode ser afirmado e está
refletido no parecer.

## Verificações executadas nesta sessão

Executadas pelo `arquiteto-senior` em ambiente descartável (Python 3.13,
PostgreSQL 16 local efêmero), contra a revisão `279e7bc`:

| Verificação | Comando | Resultado |
| --- | --- | --- |
| Lint | `ruff check .` | **Aprovado** — "All checks passed!" |
| Formatação | `ruff format --check .` | **Aprovado** — 88 arquivos já formatados |
| Django | `python manage.py check` | **Aprovado** — nenhum problema |
| Migrações em banco vazio | `python manage.py migrate` | **Aprovado** — todas aplicadas |
| Testes | `pytest` | **Aprovado** — 55 passaram, 26 avisos, em 58,70 s |
| Documentação | `scripts/validate-docs.ps1` | **Não executado** — PowerShell não está instalado neste contêiner. Substituído por uma reimplementação equivalente em Python, que aprovou os arquivos. A execução oficial ocorre na integração contínua. |

Achado de ambiente, verificado: **o projeto não instala em Python 3.11.**
`requirements/base.txt` fixa `Django==6.1.1`, que exige `Requires-Python
>=3.12`; o `python3` padrão do contêiner é 3.11.15 e a instalação falha com
"No matching distribution found for Django==6.1.1". Com `python3.13` a
instalação conclui e a suíte roda. Registrado como DE-007 em
[docs/projeto/decisoes.md](../projeto/decisoes.md) e como BL-30 no
[backlog](../projeto/backlog.md).

## Parte 1 — Estrutura, backend, banco e testes

Produzido pelo agente com o papel de desenvolvedor pleno. Somente leitura.

### Modelos e cadeia de isolamento

- `core`: nenhum modelo (`apps/core/models.py:1`). Só `health_check`
  (`apps/core/views.py:9`).
- `accounts`: `Usuario` (AbstractUser, e-mail único) —
  `apps/accounts/models.py:5,15`.
- `tenancy`: `Escritorio` (`apps/tenancy/models.py:5`), `Papel` (TextChoices, 6
  papéis, `:27`), `VinculoUsuarioEscritorio` com UniqueConstraint
  usuário+escritório (`:43`, `:72`).
- `empresas`: `Empresa` (FK escritorio PROTECT — `apps/empresas/models.py:40,48`),
  `HistoricoRegimeTributario` (`:72`), `Estabelecimento` (`:103`) com constraint
  "uma matriz por empresa" (`:126`).
- `auditoria`: `RegistroAuditoria` (`apps/auditoria/models.py:7`).
- `contabilidade`: `Conta` (`apps/contabilidade/models.py:28`),
  `LancamentoContabil` (`:68`), `ItemLancamento` (`:120`), além dos enums
  `TipoConta`, `NaturezaConta` e `TipoPartida`.

Cadeia: `Usuario -(VinculoUsuarioEscritorio)-> Escritorio -> Empresa ->
Estabelecimento`. O escritório ativo é resolvido e **revalidado a cada
requisição** contra vínculos ativos em `apps/tenancy/middleware.py:18-32`; a
empresa da URL é sempre resolvida com filtro pelo escritório ativo em
`apps/empresas/mixins.py:15-18` (devolve 404, não 403).

**Inferido:** o elo `estabelecimento` **não participa** do isolamento contábil.
`LancamentoContabil.empresa` (`models.py:79`) não referencia estabelecimento, e
não existe seletor ou escopo de estabelecimento em nenhuma view. Na prática a
cadeia é escritório -> empresa.

### Valores monetários

Único campo monetário: `ItemLancamento.valor = DecimalField(max_digits=18,
decimal_places=2, MinValueValidator(0.01))` — `apps/contabilidade/models.py:128-130`.
Nenhum `float(`, `FloatField` ou `round(` em `apps/` e `config/` (busca sem
resultado). Conversão de entrada por `Decimal(str(...))` em
`apps/contabilidade/views.py:76`. Saída formatada como string com
`quantize(Decimal("0.01"))` em `views.py:26-34`, justamente para não passar por
float no encoder do DRF (comentário em `views.py:181-184`). Saldos calculados
em `Decimal` (`views.py:168-174`, `:202-212`).

### Débito igual a crédito; rascunho x efetivado

A igualdade é validada **antes de qualquer gravação** em
`apps/contabilidade/services.py:22-36` (soma por tipo, comparação exata de
Decimal, exige total maior que zero e ao menos duas partidas), dentro de
`@transaction.atomic` (`services.py:11`). A imutabilidade é imposta no modelo:
`save()` com `pk` existente levanta `LancamentoImutavelError`
(`models.py:102-112` e `:139-149`). Correção apenas por estorno
(`services.py:59-84`).

**Lacuna real: não existe estado "rascunho".** Busca por
`rascunho|efetivado|situacao|status` não retorna nenhum campo de modelo — só
documentação. Na prática todo lançamento nasce efetivado e imutável; o
requisito RC-12 está **não implementado**. Também não há controle de período
fechado (RC-16), nem constraint de banco garantindo débito igual a crédito: a
invariante vive só na camada de serviço, e `LancamentoContabil.objects.create`
direto a contorna.

### Autorização

Autorização é do servidor. `TemEscritorioAtivo` e a fábrica `papel_permitido`
leem `request.papel` do middleware, nunca do cliente
(`apps/tenancy/permissions.py:4-36`). Aplicadas em
`apps/contabilidade/views.py:40-53,91-98,132`,
`apps/empresas/views.py:26,41-45,55-59,66-70,84-88` e
`apps/auditoria/views.py:17`. Default global `IsAuthenticated`
(`config/settings.py:134-138`). As views HTML também verificam no servidor:
`apps/empresas/views.py:132-133` (403) e `apps/tenancy/views.py:45-47,82`.

Ponto de atenção, que **não** é falha de servidor:
`templates/empresas/lista.html:10` exibe "Nova empresa" a todos os papéis — a
interface não esconde o que o servidor bloqueia. É ruído de usabilidade, não
brecha. Não foi encontrado nenhum ponto com verificação apenas na interface.

### Cobertura de testes

17 arquivos, 1097 linhas, 55 testes executados e aprovados nesta sessão.

- `core/tests/test_health.py` — healthcheck e conexão com banco.
- `accounts/tests/` — e-mail único e `__str__`; login válido e inválido.
- `tenancy/tests/` — unicidade do vínculo; autenticação exigida, só vê o
  próprio escritório, seleção automática, não ativa escritório de terceiros,
  auditoria da troca.
- `empresas/tests/` — CNPJ (5 casos); papel cliente x gestor no POST; sem
  escritório, listagem, 404 cruzado, escritório do cliente ignorado; matriz
  única e filiais; vigência de regime.
- `auditoria/tests/` — `registrar` grava e infere dados, persistência, sinais
  de login (sem senha), listagem restrita por papel e escritório.
- `contabilidade/tests/` — balanceado, desbalanceado, menos de 2 partidas,
  conta de outra empresa, conta sintética, estorno, estorno de estorno; 4 casos
  de imutabilidade; código único e conta pai da mesma empresa; permissão,
  criação, 400, 404 cruzado, razão, balancete.

**Lacunas frente à seção 10 do AGENTS.md:** (a) nenhum teste de rascunho x
efetivado, porque a funcionalidade não existe; (b) nenhum teste de período
fechado ou reabertura; (c) nenhum teste de idempotência ou duplicidade em POST
repetido (RC-14), nem de concorrência; (d) nenhum teste de arredondamento,
escala ou caso de referência de cálculo; (e) nenhum teste de migração sobre
base preexistente; (f) sem `conftest.py` na raiz; a integração contínua roda em
PostgreSQL (`.github/workflows/backend.yml:14,58-62`), mas o padrão local cai
em SQLite (`config/settings.py:84`) — divergência que o próprio `_como_moeda`
contorna.

### Atomicidade e idempotência

Atômico onde importa hoje: `apps/contabilidade/services.py:11` (lançamento e
itens) e `apps/empresas/services.py:8` com `select_for_update()` no período
vigente (`services.py:18`). Unicidades no banco: `empresa+codigo`
(`contabilidade/models.py:57`), `usuario+escritorio` (`tenancy/models.py:72`),
matriz única (`empresas/models.py:126`).

**Lacunas:** nenhuma idempotência — busca por `idempot` e `get_or_create` não
retorna nada. `POST /contabilidade/empresas/<id>/lancamentos/`
(`views.py:105-128`) repetido cria lançamentos duplicados, sem chave de
idempotência nem unicidade natural. O mesmo vale para `EstornarLancamentoView`
(`views.py:134-150`), que permite vários estornos do mesmo lançamento — só
bloqueia estornar um estorno (`services.py:65`). O `registrar` de auditoria em
`views.py:126,143` fica **fora** da transação do serviço.

**Não determinado:** se há aprovação explícita para operações críticas (seção
11 do AGENTS.md). Nenhum mecanismo de aprovação foi encontrado no código.

## Parte 2 — Interface, componentes e usabilidade

Produzido pelo agente com o papel de especialista em frontend. Somente leitura.

### Telas e navegação

Existem **5 templates**: `registration/login.html`, `tenancy/painel.html`,
`empresas/lista.html`, `empresas/form.html`, `empresas/sem_escritorio.html`.

Fluxo: login -> painel (`config/settings.py:126`, `LOGIN_REDIRECT_URL`) ->
"Empresas" (`templates/tenancy/painel.html:18`) -> "Nova empresa"
(`templates/empresas/lista.html:10`) -> POST válido redireciona para a lista
(`apps/empresas/views.py:142`). O retorno é por links manuais
(`form.html:8`, `lista.html:8`, `sem_escritorio.html:8`).

**Não existe template base.** Cada arquivo repete `<!DOCTYPE>`, `<head>` e
`<title>` por conta própria (`form.html:1-6`, `lista.html:1-6`,
`sem_escritorio.html:1-6`, `login.html:1-6`, `painel.html:1-6`). Não há
`{% extends %}`, `{% block %}` nem `{% include %}` em nenhum arquivo. Não há
barra de navegação, trilha nem menu — só links soltos.

Contabilidade (diário, razão, balancete, estorno) e auditoria **não têm tela
alguma**: são apenas endpoints DRF (`apps/contabilidade/urls.py:42-59`,
`apps/auditoria/urls.py`).

### Estados por template

| Template | Carregando | Vazio | Erro | Sucesso | Sem permissão |
| --- | --- | --- | --- | --- | --- |
| `login.html` | ausente | não se aplica | `login.html:9-11` (genérica) | ausente | não se aplica |
| `painel.html` | ausente | `painel.html:20` | ausente | ausente | ausente |
| `empresas/lista.html` | ausente | `lista.html:14-15` (`{% empty %}`) | ausente | ausente | ausente |
| `empresas/form.html` | ausente | não se aplica | implícito em `{{ form.as_p }}` (`form.html:12`) | ausente | ausente |
| `sem_escritorio.html` | não se aplica | não se aplica | não se aplica | não se aplica | `sem_escritorio.html:9` |

`django.contrib.messages` está no `INSTALLED_APPS` (`settings.py:35`) e o
middleware está ativo (`settings.py:54`), mas **nenhum template renderiza
mensagens**: cadastro bem-sucedido redireciona sem qualquer confirmação
(`views.py:142`). Falta de permissão devolve
`HttpResponseForbidden("Seu papel não permite cadastrar empresas.")`
(`apps/empresas/views.py:133`) — texto cru, sem template nem link de saída.
Erro de troca de escritório é engolido silenciosamente:
`apps/tenancy/views.py:80-90` redireciona ao painel mesmo quando o vínculo não
existe, sem avisar nada.

### Contexto de operação

Visível apenas o **escritório ativo**, em `templates/tenancy/painel.html:17`. A
lista mostra razão social e CNPJ por linha (`lista.html:13`), mas não há
indicação de empresa ou estabelecimento selecionado em nenhuma outra tela —
`form.html` e `lista.html` não exibem sequer qual escritório está ativo.
**Competência não existe no sistema:** nenhuma ocorrência de `competencia` em
`apps/`, `config/` ou `templates/`. Estabelecimento tem modelo
(`apps/empresas/models.py:107-116`) mas nenhuma tela.

### Moeda e datas

**Nenhum template exibe valor monetário ou data.** A única formatação
monetária é do servidor, em `apps/contabilidade/views.py:26-34`
(`_como_moeda`), que devolve `"1000.00"` — ponto decimal, sem separador de
milhar, sem `R$`: formato americano, não pt-BR. `LANGUAGE_CODE = "pt-br"` está
definido (`settings.py:100`), mas `USE_THOUSAND_SEPARATOR` não está, e
`django.contrib.humanize` não está no `INSTALLED_APPS` (`settings.py:30-44`).
Nenhum `{% load l10n %}`, `|floatformat`, `|date` ou `|intcomma` em nenhum
template. Não há alinhamento à direita nem tabela — `lista.html:11-17` usa
`<ul>`/`<li>`. CNPJ é armazenado com 14 dígitos sem máscara (`models.py:53`) e
impresso cru em `lista.html:13`.

### Acessibilidade

Existe: `lang="pt-br"` e `charset` nos 5 templates; rótulos associados vindos
de `{{ form.as_p }}` (`login.html:14`, `form.html:12`), que gera
`<label for>`; `verbose_name` em português (`models.py:51-53`).

Falta: `<select name="escritorio_id">` sem `<label>` nem `aria-label`
(`painel.html:27`); nenhum `<main>`, `<nav>` ou `<header>`; nenhum atalho para
o conteúdo; nenhum `aria-live` para erros; erro de login não associado ao campo
e sem `role="alert"` (`login.html:10`); zero CSS, portanto **foco visível é
apenas o padrão do navegador** e não há controle de contraste; `<form>`
aninhado dentro de `<p>` em `painel.html:10-13` é HTML inválido e prejudica
leitores de tela. Cor não é usada como indicador único — porque não há cor
nenhuma.

### Ações sensíveis

Na interface web não há nenhuma: não existe tela de efetivar, estornar,
excluir ou fechar período. Estorno existe só como POST de API
(`apps/contabilidade/urls.py:49-53`, `views.py:131-150`), sem confirmação de
interface. As proteções são todas de backend
(`apps/contabilidade/models.py:105,109-111`; `services.py:65-66`). Nos
formulários existentes, "Salvar" (`form.html:13`) e "Ativar"
(`painel.html:32`) não têm confirmação, texto de consequência nem proteção
contra duplo clique. "Sair" é POST com CSRF (`painel.html:10-12`) — correto,
mas sem confirmação.

### CSS, JS e componentes

**Não há CSS nem JS no projeto.** Não existe diretório `static/`;
`STATIC_URL`/`STATIC_ROOT` e WhiteNoise estão configurados
(`settings.py:48,108-117`) mas sem nada para servir. Nenhum `{% load static %}`,
nenhum framework CSS, nenhum HTMX ou Alpine. A marcação é totalmente ad hoc,
sem componentes reutilizáveis. O único estilo do projeto é inline:
`style="display:inline"` (`painel.html:10`).

**Inferido:** a ausência de HTMX/Alpine é decisão consciente e documentada, não
esquecimento — o docstring em `apps/tenancy/views.py:62-67` afirma que entram
"quando houver necessidade real de atualização parcial".

**Não determinado:** se existe intenção registrada de criar `base.html` ou
escolher um framework CSS; como a competência contábil será modelada.

## Parte 3 — Riscos e lacunas de verificação

Produzido pelo agente com o papel de auditor QA, de forma independente, somente
leitura e **sem execução de testes**. Achados reproduzidos integralmente,
ordenados por gravidade.

### Achado 1 — BLOQUEADOR: `conta_pai` aceita conta de outra empresa via API

- **Requisito afetado:** AGENTS.md §11 ("nunca confiar somente nos IDs
  recebidos"); `docs/escopo.md:107`. Requisito RC-18.
- **Arquivo e localização:** `apps/contabilidade/serializers.py:6-18`,
  `apps/contabilidade/views.py:55-60`, `apps/contabilidade/models.py:63-65`.
- **Evidência:** `ContaSerializer` expõe `conta_pai` como campo gravável sem
  `queryset` restrito — o padrão é `Conta.objects.all()`. `perform_create`
  força apenas `empresa=self.get_empresa()`. A única defesa é `Conta.clean()`,
  que o `ModelSerializer` **não** chama (o DRF não executa `full_clean`). O
  teste `apps/contabilidade/tests/test_models.py:39` cobre `clean()` no modelo,
  não o caminho HTTP.
- **Impacto:** usuário do escritório A cria conta cujo pai é conta do escritório
  B. Hierarquia, relatórios futuros e enumeração de identificadores cruzam a
  fronteira entre empresas.
- **Correção recomendada:** `PrimaryKeyRelatedField` com queryset filtrado pela
  empresa em contexto, e/ou `validate_conta_pai`.
- **Como verificar:** teste de API `POST /contabilidade/empresas/<A>/contas/`
  com `conta_pai` de outra empresa deve retornar 400.

> **Conferido pelo `arquiteto-senior`:** achado confirmado por leitura direta.
> `apps/contabilidade/serializers.py:15` declara `conta_pai` em `fields` sem
> restrição de queryset, e `apps/contabilidade/views.py:58` grava forçando
> apenas `empresa`.

### Achado 2 — BLOQUEADOR: estorno duplicável; nenhuma idempotência

- **Requisito afetado:** RC-14, RC-15.
- **Arquivo e localização:** `apps/contabilidade/services.py:59-84`,
  `apps/contabilidade/views.py:131-150`.
- **Evidência:** `estornar_lancamento` só rejeita estornar *um estorno* (linha
  65). Não há verificação de estorno já existente, nem `select_for_update`, nem
  constraint única em `estorno_de`. O mesmo em `criar_lancamento`: sem chave de
  idempotência. Os testes existentes (`test_services.py:129,148`) não cobrem
  repetição.
- **Impacto:** dois POSTs (repetição, duplo clique, corrida) geram dois
  lançamentos reversos, levando a saldos e balancete errados, sem forma
  automática de detectar.
- **Correção recomendada:** `UniqueConstraint(fields=["estorno_de"])` e
  bloqueio da linha original dentro da transação; chave de idempotência no POST
  de lançamento.
- **Como verificar:** teste chamando estorno duas vezes, e teste concorrente,
  devem produzir exatamente um estorno.

### Achado 3 — ALTA: imutabilidade e trilha de auditoria sem proteção real

- **Requisito afetado:** RC-15, e a trilha de auditoria do AGENTS.md §11.
- **Arquivo e localização:** `apps/contabilidade/models.py:102-112,139-148`,
  `apps/auditoria/admin.py:13-18`, `apps/auditoria/models.py:7-46`.
- **Evidência:** a imutabilidade existe só em `save()`/`delete()` de instância —
  `QuerySet.update()` e `QuerySet.delete()` não passam por eles (comportamento
  padrão do Django) e não há teste cobrindo isso. `RegistroAuditoriaAdmin`
  bloqueia adição e alteração, mas **não** define `has_delete_permission`; o
  modelo de auditoria não sobrescreve `save`/`delete`.
- **Impacto:** lançamento efetivado alterável em massa por ORM ou shell;
  registro de auditoria apagável pelo admin — a trilha não sustenta prova.
- **Correção recomendada:** `has_delete_permission = False`; bloquear mutação no
  modelo de auditoria; proteção no nível do banco para ambos.
- **Como verificar:** testes com `objects.filter(...).update()` e `.delete()`
  devem falhar.

> **Conferido pelo `arquiteto-senior`:** a ausência de `has_delete_permission`
> em `apps/auditoria/admin.py` foi confirmada por leitura direta do arquivo.

### Achado 4 — ALTA: validadores monetários não executam na gravação

- **Requisito afetado:** RC-10, RC-11.
- **Arquivo e localização:** `apps/contabilidade/services.py:22-55`,
  `apps/contabilidade/models.py:128-130`.
- **Evidência:** `MinValueValidator(0.01)` e `decimal_places=2` só rodam em
  `full_clean()`, que nunca é chamado. `criar_lancamento` valida apenas os
  totais: itens `{débito 100, débito -50, crédito 50}` passam. Valores com mais
  de duas casas são arredondados pelo banco **depois** da checagem de
  igualdade.
- **Impacto:** partidas negativas gravadas, e débito diferente de crédito após
  o arredondamento — invariante contábil (AGENTS.md §10) rompida.
- **Correção recomendada:** validar sinal e escala explicitamente no serviço,
  com política de arredondamento declarada.
- **Como verificar:** testes de limite com valor negativo e com três casas
  decimais.

### Achado 5 — ALTA: lacunas da integração contínua frente ao AGENTS.md §13

- **Arquivo e localização:** `.github/workflows/backend.yml`.
- **Evidência:** há ruff, `manage.py check`, migrate e pytest. **Não há:**
  detecção de segredos, verificação de tipos, `makemigrations --check
  --dry-run` (deriva entre modelo e migração), `check --deploy`, nem cobertura.
  `DEBUG: 'True'` (linha 12) faz o bloco de segurança de
  `config/settings.py:145-150` nunca ser exercido.
- **Impacto:** as regras do §13 permanecem dependentes de disciplina manual.
- **Não verificável daqui:** proteção da branch `main` (revisão obrigatória,
  verificações obrigatórias) — é configuração do GitHub, fora do repositório.

> **Nota do `arquiteto-senior`:** o relatório original registrou que
> `.github/` conteria apenas `workflows/`. Isso está incorreto:
> `.github/pull_request_template.md` existe. O restante do achado 5 procede e
> foi mantido.

### Achado 6 — MÉDIA: arredondamento implícito

`apps/contabilidade/views.py:26-34`. `quantize(Decimal("0.01"))` sem
`rounding=` explícito (usa `ROUND_HALF_EVEN` do contexto), e `Decimal(valor)`
pode receber float vindo de agregação no SQLite. Contraria o §10 ("sem
presumir... duas casas").

### Achado 7 — MÉDIA: sem paginação e sem limites

`config/settings.py:134-138`; `apps/contabilidade/views.py:100-103,193-215`.
Nenhuma `DEFAULT_PAGINATION_CLASS` nem throttle; o balancete faz duas consultas
por conta (N+1). `docs/escopo.md:107` exige paginação e limites.

### Achado 8 — MÉDIA: auditoria de login invisível, e nome de usuário registrado

`apps/accounts/signals.py:36-43`; `apps/auditoria/services.py:14-17`;
`apps/auditoria/views.py:19-20`. Eventos de login gravam `escritorio=None`, e a
listagem filtra por escritório ativo — então login e falha de login **nunca
aparecem**. O nome de usuário tentado é persistido: uma senha digitada no campo
de usuário vazaria em texto claro.

### Achado 9 — MÉDIA: regime tributário com corrida e valor arbitrário

`apps/empresas/services.py:17-21`; `apps/empresas/views.py:95-106`.
`select_for_update().filter(...).first()` não bloqueia nada quando não há
período vigente, e não há constraint de unicidade — dois regimes vigentes
simultâneos são possíveis. `regime` não é validado contra
`RegimeTributario.choices`.

### Achado 10 — BAIXA: `int(escritorio_id)` sem validação

`apps/tenancy/views.py:41-49,81-84`: valor não numérico gera 500 em vez de 400.

### Pontos sólidos observados

Registrados pelo próprio auditor: o middleware revalida o escritório da sessão
(`apps/tenancy/middleware.py:18-32`); o serializer de empresa ignora o
escritório enviado pelo cliente (`apps/empresas/serializers.py:43-47`); o
`EmpresaEscopadaMixin` devolve 404 em vez de 403; as permissões são aplicadas
no servidor também na view HTML (`apps/empresas/views.py:132`). **Não foi
encontrada autorização existente apenas em template.**

### Parecer

**REPROVADO** para promoção a ambiente com dados reais.

Justificativa do auditor: diagnóstico estático, sem execução de testes nem
inspeção do banco ou das proteções de branch. Não afirma ausência de outros
defeitos, segurança absoluta nem conformidade legal. Os achados 1 e 2 exigem
correção e teste antes de qualquer reavaliação.

## Consolidação do `arquiteto-senior`

**Classificação do que foi feito:**

| Categoria | Conteúdo |
| --- | --- |
| **Inspecionado** | Todo o código de `apps/`, `config/`, `templates/` e `.github/workflows/`, por três agentes independentes. |
| **Testado** | Lint, formatação, `manage.py check`, migrações em banco vazio e 55 testes automatizados — todos aprovados na revisão `279e7bc`. |
| **Não testado** | Nenhum dos 10 achados foi reproduzido por execução: são achados de leitura. Os achados 1, 3 e 5 foram **conferidos por leitura** pelo arquiteto; os demais não. Idempotência, concorrência, arredondamento e migração sobre base preexistente não têm teste no projeto. |
| **Bloqueado** | `scripts/validate-docs.ps1` não pôde rodar (sem PowerShell no contêiner). Proteção da branch `main` não é verificável pelos agentes. |
| **Fora do escopo** | Módulos Fiscal, Folha, Honorários, Processos/Paralegal, MCP e assistente de IA — nenhum foi iniciado. |

**Leitura geral.** A fundação é sólida onde foi construída: o isolamento entre
escritórios é aplicado no servidor e revalidado por requisição, a imutabilidade
de lançamentos foi pensada, e os 55 testes existentes cobrem bem os caminhos
implementados. Os problemas se concentram em duas frentes: (a) requisitos
declarados no AGENTS.md que ainda **não foram implementados** — rascunho,
período fechado, idempotência, competência; e (b) validações que existem no
modelo mas **não são executadas** no caminho real de gravação via DRF —
achados 1 e 4.

Os dois bloqueadores compartilham a mesma causa raiz: **o DRF não chama
`full_clean()`**, então toda regra escrita apenas em `Model.clean()` ou em
validador de campo é decorativa no caminho da API. Isso merece decisão
arquitetural, não correção pontual, e está registrado como tal no
[backlog](../projeto/backlog.md) (BL-40).

**Importante:** nenhum destes achados foi corrigido nesta sessão. A
configuração da equipe não alterou nenhum arquivo de código de negócio.

**Próximo passo:** priorização com o Fred (BL-01) e correção dos bloqueadores
BL-40 e BL-41 antes de qualquer nova funcionalidade.

> Auditoria de software não substitui a validação profissional das regras
> contábeis e legais.
