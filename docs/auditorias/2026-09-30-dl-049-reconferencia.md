# Reconferência única — DL-049

**Data:** 30/09/2026
**Auditoria original:** `docs/auditorias/2026-09-30-dl-049-rodada-1.md`
**Escopo:** correções A1, A2 e A3, regressões pertinentes e ajustes de apresentação. Esta é a única reconferência da etapa.

## Identificação da versão

| Objeto | SHA |
| --- | --- |
| Commit local auditado | `ca0943474482a2c5a04df0bd8da717096f5b8b14` |
| Commit publicado no PR | `280873b344d727790069ea688bb17278585ae02d` |
| Merge de teste usado pela CI | `144812b8a5201a3a4ec1ae3abf49b14a03c50d6c` |
| Árvore comum aos três | `f1d759238af5812b560da16a078d6529e56ee247` |
| Base do PR | `ee408019b54f7fdcaf14b84132e9ed74b3194750` |

Os commits são diferentes; seu conteúdo versionado é idêntico. Conferi a árvore local diretamente e inspecionei as respostas da API preservadas em `github-tree-280873b.json` e `github-ci-merge-144812b.json`. O log da CI confirma o checkout do merge de teste acima.

**PR:** [DataLedger #63](https://github.com/fredabsd-svg/DataLedger/pull/63).

Produzi nova cópia por `git archive` em `/workspace/scratch/071b3ceae603/dl049_recheck_ca094347`. Não alterei implementação, testes, documentação ou Git remoto. Usei SQLite próprio em `/tmp/dl049-recheck-ca094347.sqlite3`, com dados sintéticos. Não tentei reutilizar o PostgreSQL local anterior nem solicitar nova escalada.

## Reconferência dos achados

### A1 — ALTA na auditoria original: corrigido e verificado

**Requisitos:** RC-138, HI-45; ocorrências reais, ausência de atribuição inventada, autorização e isolamento.

**Localização da correção:** `apps/core/module_homes.py`, seleção inicial Fiscal em `resolver_escopo` e tratamento `apura_sem_empresas` em `montar_home`.

**Correção inspecionada:** Fiscal sem clientes inicia em `empresa=todas`. A apuração das ocorrências do escritório deixa de depender de uma carteira cadastrada.

**Reprodução independente:** criei dois escritórios fictícios sem empresas. Recebi pelo serviço normal `receber_envio` uma recusa e um evento órfão em cada escritório. Consultei home, listas e destinos reais.

```text
A1 gestor default:
cards={'arquivos-recusados':1,'eventos-sem-nota':1,'notas-canceladas':0}
companies=0
queue=2

A1 gestor todas:
cards={'arquivos-recusados':1,'eventos-sem-nota':1,'notas-canceladas':0}
companies=0
queue=2

A1 paralegal:
queue=1
restricted report=403
restricted state=400
```

Os cards conservaram igualdade com os totais das listas. As ações das linhas autorizadas abriram destinos com HTTP 200. As ocorrências permaneceram sem empresa identificada. Nomes, arquivo e chave do outro escritório não apareceram.

Verifiquei ausência de efeitos de negócio nos GET:

```text
A1 readonly business counts:
antes=[4,4,2,5]
depois=[4,4,2,5]
```

Esses números correspondem a lotes, resultados de arquivos, eventos e registros de auditoria.

**Impacto corrigido:** recusas e eventos existentes agora aparecem mesmo antes do primeiro cliente, mantendo as restrições do perfil e do escritório.

**Verificação:** experimentos próprios aprovados, testes parametrizados executados localmente e os 71 testes de home executados também na CI PostgreSQL.

### A2 — MÉDIA na auditoria original: corrigido e verificado

**Requisitos:** RC-138, HI-44; preferência por escritório e filtros persistentes.

**Localização da correção:** `apps/core/module_homes.py`, helpers `_contextos_da_sessao`, `_preferencia_do_escritorio`, `_memorizar_preferencia`, e seus consumidores.

**Correção inspecionada:** preferências separadas por escritório, com retenção dos 16 usados mais recentemente, compatibilidade com o formato anterior e revalidação dos IDs no escritório ativo.

**Reprodução independente:** selecionei grupo de duas empresas em A, com `2024-02`, e uma empresa em B, com `2022-11`. Voltei a ambos sem parâmetros explícitos.

```text
A2 restored office=1 scope=grupo period=2024-02 ids=[1,2] menu_queries=0
A2 restored office=2 scope=3 period=2022-11 ids=[3] menu_queries=0
A2 legacy session migration=retained company/month
A2 stored cross-office group=404,no foreign name
```

A migração da preferência antiga conservou empresa e competência. Um grupo adulterado na sessão continuou recusado, sem nome alheio. O menu preservou os parâmetros sem consultar o banco.

**Impacto corrigido:** a troca de escritório e o retorno restauram o contexto anterior, sem ampliar o escopo autorizado.

**Verificação:** experimentos próprios aprovados; testes executados cobrem ida e volta, painel/menu, migração, limite de retenção e IDs inválidos ou alheios.

### A3 — BAIXA na auditoria original: corrigido e verificado

**Requisito:** contrato de filtros inválidos, independente da disponibilidade de dados.

**Localização da correção:** `apps/core/module_homes.py`, validação `sem_apuracao` antes dos retornos antecipados de `montar_home`.

**Correção inspecionada:** caminhos sem fonte apurável recusam estado solicitado e páginas inexistentes antes de retornar o estado informativo.

**Reprodução independente:**

```text
estado=nao-existe:
contabilidade → 400
fiscal → 400
livro-caixa → 400
financeiro → 400
folha → 400
vendas → 400
estoque → 400

Escritório vazio, quatro módulos:
pagina=2 → 404
estado=nao-existe → 400
```

**Impacto corrigido:** URLs inválidas deixam de aparentar sucesso nos estados indisponível, vazio ou inaplicável.

**Verificação:** experimentos próprios aprovados; testes executados incluem também páginas malformadas e Fiscal sem clientes.

## Verificações locais executadas

O interpretador foi `/workspace/scratch/071b3ceae603/home_work_tmp/venv314/bin/python`, usando `config.settings`, `DEBUG=True`, a cópia arquivada e a URL SQLite exclusiva.

| Comando/verificação | Resultado |
| --- | --- |
| `python -m pytest -q apps/core/tests/test_module_homes.py --tb=short -x` | **71 passed in 8.30s** |
| Pytest dos arquivos de painel, permissões/consultas fiscais e fechamento contábil | **67 passed, 3 warnings in 4.39s** |
| `python -m ruff check .` | **All checks passed!** |
| `python -m ruff format --check .` | **317 files already formatted** |
| `python manage.py check` | **System check identified no issues (0 silenced).** |
| Comparação dos arquivos rastreados com novo `git archive` | `archive_tracked_file_differences=[]` |
| `git status --porcelain` e `git diff --stat` após a execução | Ambos vazios |

Total local: **138 testes aprovados**, sem skips nessas execuções. Os três avisos das regressões declaram a ausência de locks PostgreSQL no SQLite; não os tratei como prova de concorrência.

As regressões executadas foram:

```text
apps/tenancy/tests/test_dl044_painel_carteira_e_indicadores.py
apps/fiscal/tests/test_permissoes.py
apps/fiscal/tests/test_consultas.py
apps/contabilidade/tests/test_dl031_fechamento_de_competencia.py
```

## Navegador independente

Executei Chromium sobre a nova cópia e o banco exclusivo, com servidor e navegador no mesmo processo de verificação. O servidor foi encerrado ao terminar.

Verifiquei os sete módulos e o cenário adicional Fiscal sem empresas:

```text
browser4KPIlists=passed
browserGroupNoJS=passed
browserFiscalZeroCompanies=2lines,3cards,defaultTodas
browser403=no company data
browserErrors=[]
```

Resultados medidos:

- Primeiro item contábil termina em **898,15625 px** em 1.440 × 900.
- Cards precedem os avisos complementares nos módulos apurados.
- Nenhum overflow horizontal em **1.280 px** ou **390 × 844**.
- Foco de teclado: contorno sólido de **3 px**.
- Movimento reduzido durante pressão: transição **0s**, transformação **none**.
- Grupo sem JavaScript conserva duas empresas e a competência histórica.
- Financeiro, Folha, Vendas e Estoque continuam sem cards ou operações fictícias.
- Nenhum `R$` no conteúdo das homes verificadas.

Inspecionei visualmente as capturas da Contabilidade e do Fiscal sem clientes. As capturas próprias estão em `/tmp/dl049-recheck-browser/`.

## CI inspecionada

Inspecionei os metadados dos quatro jobs em `github-jobs-280873b.json`, o log Backend e o log completo do instrumento de identificação.

| Checagem | Resultado | Evidência |
| --- | --- | --- |
| Lint e testes | **success** | Run `36713882076`, job `109882527378` |
| Validar documentação | **success** | Run `36713881871`, job `109882525641` |
| Regras do projeto | **success** | Run `36713881787`, job `109882530790` |
| Medir identificação do emitente no navegador | **success** | Run `36713881780`, job `109882527790` |

O Backend usou **PostgreSQL 16.15**, proveniente de `postgres:16-alpine`, e registrou:

```text
3563 passed, 50 skipped, 2 warnings in 252.49s
172 static files copied, 496 post-processed
```

Os **71 testes de home foram executados sem skip**. Lint, formatação, check Django, migrações em banco vazio e coleta de estáticos passaram.

Os skips do Backend foram explicitados: dois testes legados de navegador, um controle específico de SQLite, testes do instrumento sem Poppler naquele job e casos de fontes ausentes. O job próprio do instrumento instalou suas dependências e executou:

```text
139 passed in 329.89s
```

A etapa de medição efetiva também terminou com `success`, com resultados `PASSOU` registrados para as telas medidas.

A CI foi **inspecionada**, não executada por mim. Sua árvore corresponde exatamente à versão reconferida localmente.

## Limites e encerramento

A1, A2 e A3 estão corrigidos e verificados. Não identifiquei nova falha bloqueadora ou alta no escopo desta reconferência.

Telefone físico, leitor de tela e teste com operadores continuam **não testados**. Integração bancária, certificado, emissão, folha/eSocial e novos papéis permanecem **fora do escopo**. Nenhuma aprovação de integração foi interpretada como autorização de implantação em produção.

O parecer refere-se à árvore identificada neste relatório. A inclusão posterior deste relatório e dos apontadores documentais deve conservar o código e passar pelas checagens aplicáveis do último HEAD antes do merge. Esta reconferência encerra o ciclo permitido da etapa.

**APROVADO**
