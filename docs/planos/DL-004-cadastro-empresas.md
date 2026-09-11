# DL-004 — Cadastro central de empresas e estabelecimentos

## Objetivo e diagnóstico

Implementar o cadastro central de empresas e estabelecimentos vinculados a
um escritório, incluindo o histórico de regime tributário por vigência,
conforme a seção "Plataforma compartilhada" do
[escopo funcional](../escopo.md). Esta é a segunda fatia da etapa
"Fundação" do [README](../../README.md) — a primeira (autenticação e
isolamento entre escritórios) foi entregue na DL-003. A matriz fina de
permissões por módulo/operação e a auditoria completa continuam fora do
escopo, reservadas para a DL-005.

Na inspeção inicial desta demanda, a DL-003 já entregava usuário
customizado, escritórios e vínculos com papel, mas nenhum cadastro de
negócio existia — apenas o próprio escritório.

**Dependência entre PRs:** a branch `feat/dl-004-cadastro-empresas` parte de
`feat/dl-003-fundacao-multiempresa` (PR #3, ainda não integrado, que por sua
vez depende do PR #2). O PR desta etapa precisa ser reapontado
(retarget) para `main` na ordem em que os PRs anteriores forem integrados.

## Decisões desta etapa

| Decisão | Escolha | Motivo |
| --- | --- | --- |
| Validação de CNPJ | Algoritmo público de dígitos verificadores da Receita Federal, aplicado a `Empresa.cnpj` e `Estabelecimento.cnpj` | Reduz erro de cadastro sem inventar nenhuma regra fiscal — é um algoritmo determinístico e público, não uma alíquota ou leiaute. |
| Histórico de regime tributário | Modelo `HistoricoRegimeTributario` com `vigencia_inicio`/`vigencia_fim`, nunca editado após fechado; `services.registrar_regime_tributario` fecha o período anterior automaticamente | Atende à regra "versionar parâmetros legais e regras por vigência" e "preservar dados necessários para reproduzir cálculos históricos" (AGENTS.md, seção 10). Sem essa preservação, uma apuração fiscal de um mês passado não seria reproduzível se a empresa mudasse de regime depois. |
| Matriz e filiais | `Estabelecimento` com `tipo` (matriz/filial) e `UniqueConstraint` condicional garantindo no máximo uma matriz por empresa | Corresponde à estrutura real de uma empresa brasileira (uma matriz, zero ou mais filiais), sem impor limite artificial às filiais. |
| Isolamento das operações de negócio | Toda consulta/gravação de `Empresa`/`Estabelecimento`/histórico é filtrada por `request.escritorio` (escritório **ativo**, resolvido pelo middleware da DL-003), nunca apenas pelo vínculo do usuário | Um usuário com vínculo a dois escritórios não pode ver empresas do escritório B enquanto o escritório A está ativo — testado explicitamente (ver "Cenários de teste"). |
| Interface desta etapa | Lista e criação de empresa via formulário HTML simples; edição de estabelecimento e regime tributário só via API e Django admin por enquanto | Mantém o incremento focado no modelo de dados e no isolamento; a UI completa de estabelecimentos/regime é adiável sem bloquear os módulos de negócio que virão a seguir. |

## Etapa e entregáveis

- Estado deste registro: `em validação`.
- Branch de trabalho: `feat/dl-004-cadastro-empresas` (baseada em
  `feat/dl-003-fundacao-multiempresa`).
- Destino: `feat/dl-003-fundacao-multiempresa` (temporário, até a cadeia de
  PRs anteriores ser integrada; depois, `main`).
- Entregáveis:
  - App `apps/empresas`: modelos `Empresa`, `RegimeTributario` (choices),
    `HistoricoRegimeTributario`, `TipoEstabelecimento` (choices) e
    `Estabelecimento`.
  - `apps/empresas/validators.py`: validação de CNPJ por dígito
    verificador.
  - `apps/empresas/services.py`: `registrar_regime_tributario`, que fecha o
    período vigente anterior de forma atômica.
  - `apps/tenancy/permissions.py`: permissão `TemEscritorioAtivo`,
    reutilizável por qualquer módulo de negócio futuro.
  - Endpoints DRF: listar/criar/consultar/atualizar empresa, listar/criar
    estabelecimentos de uma empresa, listar/registrar regime tributário.
  - Páginas server-rendered: lista de empresas do escritório ativo e
    formulário de criação.
  - Admin do Django para os três modelos, com inlines.
  - Migração inicial do app `empresas`.
- Dependências: PRs #2 e #3 integrados antes do merge final deste PR.
- Fora do escopo: matriz de permissões por módulo/operação, auditoria,
  edição/exclusão de empresa, UI de estabelecimentos e regime tributário,
  importação de dados cadastrais de fontes externas (Receita Federal,
  Juntas Comerciais).

## Critérios de aceite

- `Empresa`/`Estabelecimento` rejeitam CNPJ com tamanho, formato ou dígito
  verificador inválido, tanto pelo formulário quanto pela API.
- Um usuário só vê, cria ou edita empresas do escritório **ativo** da
  sessão, mesmo tendo vínculo com outros escritórios.
- Consultar a empresa de outro escritório (mesmo por ID direto) resulta em
  404, não em dado vazio nem erro genérico.
- Criar uma empresa ignora qualquer escritório enviado pelo cliente; usa
  sempre `request.escritorio`.
- Uma empresa não pode ter duas matrizes cadastradas.
- Registrar um novo regime tributário fecha automaticamente o período
  vigente anterior, sem apagar o registro antigo.
- `manage.py check`, `manage.py migrate` em banco vazio, `pytest`,
  `ruff check` e `ruff format --check` passam.

## Cenários de teste

| Cenário | Resultado esperado | Cobertura |
| --- | --- | --- |
| CNPJ válido (com e sem máscara) | Aceito | `apps/empresas/tests/test_validators.py` |
| CNPJ com tamanho errado, dígitos repetidos ou dígito verificador incorreto | `ValidationError` | `apps/empresas/tests/test_validators.py` |
| Requisição sem escritório ativo | 403 (`TemEscritorioAtivo`) | `apps/empresas/tests/test_isolamento.py` |
| Usuário com vínculo a dois escritórios lista empresas com cada um ativo | Só retorna as empresas do escritório ativo no momento | `apps/empresas/tests/test_isolamento.py` |
| Consulta a empresa de outro escritório | 404 | `apps/empresas/tests/test_isolamento.py` |
| Criação de empresa | Sempre associada ao escritório ativo, mesmo se o corpo da requisição sugerir outro | `apps/empresas/tests/test_isolamento.py` |
| Duas matrizes para a mesma empresa | Erro de integridade | `apps/empresas/tests/test_estabelecimento.py` |
| Várias filiais para a mesma empresa | Permitido | `apps/empresas/tests/test_estabelecimento.py` |
| Novo regime tributário | Fecha o período vigente anterior (`vigencia_fim` preenchido) e abre o novo (`vigencia_fim` nulo) | `apps/empresas/tests/test_services.py` |
| Nova vigência anterior ou igual ao início do período vigente | `ValueError` | `apps/empresas/tests/test_services.py` |

Fluxo completo também validado manualmente via HTTP real (`manage.py
runserver` + `curl`): login, painel com escritório ativo, lista de
empresas vazia, criação via formulário, empresa aparecendo na lista, e
rejeição de CNPJ inválido pelo mesmo formulário — ver "Validação
reproduzível".

## Impacto em segurança, dados, cálculos, contratos e desempenho

- **Segurança:** todas as views de negócio exigem `TemEscritorioAtivo`
  (autenticado **e** com escritório ativo resolvido pelo middleware). Uma
  empresa de outro escritório nunca é revelada nem por 403 nem por payload
  vazio — o padrão é 404, evitando confirmar a existência do registro.
- **Dados:** três novos modelos persistidos, todos com `escritorio`
  (direto ou pela empresa) como chave de isolamento. `Empresa.escritorio`
  usa `on_delete=PROTECT`: um escritório com empresas cadastradas não pode
  ser removido sem decisão explícita, evitando perda de rastreabilidade.
- **Cálculos:** nenhuma regra fiscal, trabalhista ou contábil foi
  implementada; o regime tributário é apenas cadastral nesta etapa.
- **Contratos:** novos endpoints (todos exigindo escritório ativo):
  - `GET|POST /empresas/api/empresas/`
  - `GET|PATCH /empresas/api/empresas/<id>/`
  - `GET|POST /empresas/api/empresas/<id>/estabelecimentos/`
  - `GET|POST /empresas/api/empresas/<id>/regime-tributario/`
  - `GET /empresas/`, `GET|POST /empresas/nova/` (server-rendered).
- **Desempenho:** volume de dados ainda pequeno; consultas usam índices de
  chave estrangeira padrão do Django. Sem impacto mensurável nesta etapa.

## Estratégia de reversão

Nenhum dado de produção existe ainda. Reversão: fechar o PR antes do merge
ou propor um commit de reversão em novo PR após integração. Como não há
dados reais, não há necessidade de migração de dados para reverter.

## Validação reproduzível

Executado localmente em ambiente Windows, Python 3.14, no mesmo ambiente
virtual das etapas anteriores:

```sh
python manage.py makemigrations empresas
python manage.py check
python manage.py migrate
pytest
ruff check .
ruff format --check .
```

Resultados obtidos em 11/09/2026:

- `manage.py check`: nenhum problema encontrado.
- `manage.py migrate` em banco vazio: `empresas.0001_initial` aplicou sem
  erro, junto com as migrações das etapas anteriores.
- `pytest`: 24 testes executados, 24 aprovados (11 herdados das etapas
  DL-002/DL-003 + 13 novos desta etapa).
- `ruff check .` e `ruff format --check .`: sem apontamentos (um uso de
  `zip()` sem `strict=` foi identificado pelo lint e corrigido no próprio
  validador de CNPJ).

Teste manual de ponta a ponta via HTTP real (`manage.py runserver` na porta
8003, usuário e escritório de teste criados via `manage.py shell`):

1. Login válido → painel exibe o escritório ativo (seleção automática,
   herdada da DL-003).
2. `GET /empresas/`: lista vazia ("Nenhuma empresa cadastrada").
3. `POST /empresas/nova/` com CNPJ válido: redireciona e a empresa aparece
   na lista seguinte.
4. `POST /empresas/nova/` com CNPJ inválido (`00000000000000`): permanece
   na página com a mensagem "CNPJ inválido.", sem criar registro.

**Limitação registrada:** validado apenas com SQLite local, sem Docker. O
caminho com PostgreSQL real é responsabilidade do workflow
`.github/workflows/backend.yml` (herdado da DL-002); o resultado deve ser
conferido no PR.

## Riscos, limitações e próximos passos

- **Rebase pendente:** este PR precisa ser reapontado conforme os PRs
  anteriores (#2 e #3) forem integrados, na ordem correta.
- **Sem edição/exclusão de empresa pela UI:** apenas criação e listagem;
  ajustes cadastrais dependem do Django admin por enquanto.
- **Sem UI de estabelecimentos e regime tributário:** disponíveis só via
  API/admin nesta etapa.
- **Sem importação de dados oficiais:** cadastro é manual; integração com
  fontes externas (Receita Federal, Juntas Comerciais) é trabalho futuro,
  fora do escopo desta fundação.
- **Próxima etapa sugerida:** matriz de permissões por módulo/operação e
  auditoria (DL-005), antes de iniciar o primeiro módulo de negócio (Fiscal
  ou Paralegal) previsto na etapa 4 do roadmap do README.

Hash do commit, link do PR, resultado da CI e eventuais ajustes serão
registrados na descrição do PR e no relatório de entrega; não inserir
identificadores fictícios neste documento.
