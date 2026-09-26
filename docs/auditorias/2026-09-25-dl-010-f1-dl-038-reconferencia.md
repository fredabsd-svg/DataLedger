# Reconferência da auditoria DL-010 F1 e DL-038

**Auditor:** `auditor-qa`. Esta é a única reconferência prevista pelo §3.1 do AGENTS.md para o nível 1.
**Data:** 2026-09-26
**Relatório conferido:** [rodada 1](2026-09-25-dl-010-f1-dl-038-rodada-1.md)
**Branch:** `claude/vigilant-bardeen-jo12l4`
**Revisão:** `88e7ac594c00d21b3d009ab97766f0332be713b3`. Conferi com `git rev-parse HEAD`; `git status` estava limpo antes e continuou limpo depois.
**Correções conferidas:** `38fff18` (`especialista-frontend`: A6 F11/F14, A7, A12, só testes) e `88e7ac5` (`desenvolvedor-pleno`). As decisões estão na DE-076.

**Ambiente:**
- Python 3.13 (a integração contínua usa 3.14) e PostgreSQL 16 local.
- Experimentos e mutações rodaram em três worktrees descartáveis desta revisão, cada uma com banco de teste próprio.
- Worktrees e bancos criados por mim foram removidos ao final.

Auditoria de software não substitui validação profissional das regras contábeis e fiscais. Este relatório não declara ausência de defeitos.

## Comandos executados

| Comando (na revisão `88e7ac5`) | Resultado |
| --- | --- |
| `pytest --create-db` (suíte completa; aplica todas as migrações, inclusive a 0009, em banco vazio) | `1 failed, 2582 passed, 45 skipped, 2 warnings, 4 subtests passed in 124.14s`. A falha é a preexistente de ambiente `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` |
| `ruff check .` | `All checks passed!` |
| `ruff format --check .` | `265 files already formatted` |
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `pwsh ./scripts/validate-docs.ps1` | **Não executado**: não há `pwsh` neste ambiente |

## Situação de cada achado da rodada 1

| Achado | Situação | Evidência (reexecutada nesta revisão) |
| --- | --- | --- |
| **A1** — arquivo ruim derruba o envio (alta) | **Fechado com ressalva** | Pela tela, os casos que davam 500 agora dão **302**: `xNome` 301, `nNFSe` 14, NIF 41, namespace 600, `versao` 600, nome de entrada 600. ZIP com uma nota boa e uma ruim dá 302 com **1 documento e 1 lote**. `encoding` desconhecido é recusado. Mutações que removem `_truncar` e o tratamento de `LookupError` morrem. **Ressalva:** a última defesa introduziu um mascaramento de erro de sistema, ver **N1** |
| **A2** — ZIP corrompido dá 500 (média) | **Fechado** | Deflate corrompido, CRC trocado e método 9 dão **400**, sem lote. A mutação que restringe o `except` a `BadZipFile` morre |
| **A3** — espera de lock e deadlock dão 500 (alta) | **Fechado com ressalva** | Ver o detalhamento logo abaixo da tabela. **Ressalva:** N04, N05 e N06 sobrevivem, ver **N2** |
| **A4** — envio passa do tempo-limite (alta) | **Fechado com ressalva** | Pela tela: 2.000 notas em **7,3 s**; reenvio das mesmas 2.000 em **9,1 s**; 2.001 dão **400** em 0,0 s; 2.000 eventos em 4,2 s. **Ressalva:** pior caso sintético dentro dos limites (2.000 notas com cerca de 100 KB cada, ZIP de 1,3 MB) levou **14,4 s**, medido com outra carga concorrente na máquina. Fica abaixo dos 30 s, mas no limite da folga que a DE-076 pede (metade do tempo-limite). Medido com o cliente de teste, não com gunicorn nem com o hardware de produção |
| **A5** — reenvio não acrescenta vínculo (média) | **Fechado** | O cenário da rodada 1 agora dá `duplicado` com **2 vínculos**. N07 morta |
| **A6** — portas de isolamento sem teste (média) | **Fechado com ressalva** | F04, F11 e F14 morrem na suíte completa. F02 **sobrevive**, mas só porque o envio agora identifica a empresa por um dicionário (`_mapa_de_inscricoes_do_escritorio`) e F02 muta o caminho antigo, sem dicionário, que produção não usa mais. As mutações equivalentes no caminho real morrem: M1 (dicionário de estabelecimentos sem filtro de escritório) e M2 (dicionário de empresas sem filtro). **Ressalva:** ver **N3** |
| **A7** — PARALEGAL sem teste (baixa) | **Fechado** | F15 e F16 morrem (`test_paralegal_nao_envia_documentos_get`, `test_paralegal_nao_ve_relatorio_do_envio`) |
| **A8** — ZIP com muitas entradas consome memória (baixa) | **Fechado com ressalva** | ZIP honesto com 601.184 entradas é recusado pelo registro de fim de diretório (EOCD) em **0,0 s, +0 MB**. N11 morta. **Ressalva:** com o EOCD forjado para declarar 1 entrada, a checagem antecipada não pega, e o `infolist()` volta a custar **+317,8 MB e 3,9 s** antes da recusa. O código admite isso no comentário |
| **A9** — limites e formatos sem teste (baixa) | **Fechado** | F18, F21, F30, F35 e F36 morrem |
| **A10** — upload grande gravado em disco (baixa) | **Fechado com ressalva** | O disco agora é protegido (`LimiteDeTamanhoUploadHandler`). CSRF conferido com `enforce_csrf_checks=True`: sem token dá **403** e 0 lotes; o GET traz token e cookie; com token dá **302**; arquivo grande com token dá **400** com mensagem; grande sem token dá **403**. N15 morta. **Ressalva:** `StopUpload(connection_reset=False)` ainda **lê e descarta** o resto do corpo, então a banda continua sendo consumida. O limite no proxy segue recomendado |
| **A11** — conteúdo não conferido (baixa) | **Fechado** | Os três casos da rodada 1 agora são `recusado`: chave do `Id` diferente do `chNFSe`, código do `Id` diferente do elemento, e dois códigos. Nota de homologação é recusada. N08, N09 e N10 morrem |
| **A12** — telas fiscais fora da suíte de acessibilidade (baixa) | **Fechado** | Quatro telas fiscais entraram em `test_dl024_atalhos_e_acessibilidade.py` com `test_tela_fiscal_*`, incluindo o estado de erro da lista |
| **B1** — admin dá 500 (média) | **Fechado** | Pelo admin, CNPJ duplicado dá **200** com "empresa com este CNPJ já existe."; tipo CPF com CNPJ preenchido dá **200** sem gravar. N23 morta |
| **B2** — estabelecimento para empresa CPF (média) | **Fechado com ressalva** | Pela API, criar estabelecimento para empresa CPF dá **400** com mensagem. PATCH de PJ com filial para CPF dá **400**. N16, N17 e N19 morrem. **Ressalvas:** (1) N18 sobrevive: a checagem de transição em `Empresa.clean` não tem teste. Hoje ela é inalcançável pelo admin, que exige CNPJ (ver **N4**). (2) Não há restrição de banco: um estabelecimento criado por ORM direto para empresa CPF ainda faz a recepção vincular a nota à pessoa física (medido: `recebido`, `('CPF', 'prestador')`) |
| **B3** — varredura não exercita POST (média) | **Fechado** | C05 morre na suíte completa (`...em_todo_metodo_aceito[contabilidade:lancamentos]`). A varredura deriva os métodos aceitos do cabeçalho `Allow` |
| **B4** — recusa ausente no admin e nos serviços (baixa) | **Fechado** | N21 (`Conta.clean`) e N22 (`criar_lancamento`) morrem |
| **B5** — HI-23 diverge entre tela e API (média) | **Fechado** | Pela API, CPF sem modo dá `livro_caixa`; CNPJ sem modo dá `contabilidade`; PUT sem modo **preserva** o `livro_caixa` já gravado. N20 morta |
| **B6** — unicidade global do CPF revela cliente de outro escritório (média, decisão do Fred) | **Aberto, fora da correção (PE-68)** | **Continua valendo:** o gestor do escritório A cadastra CPF já existente no escritório B e recebe `400 {"cpf":["empresa com este CPF já existe."]}`; CPF livre dá 201 |
| **B7** — ordem do decorador (baixa) | **Fechado** | CLIENTE em empresa livro-caixa recebe 403 **sem** a mensagem de livro-caixa. Usuário sem escritório vê `empresas/sem_escritorio.html` (200). A troca do decorador por função nas 13 views foi conferida por mutação: retirar a recusa de `razao` (N01), `competencia_entregar` (N02) ou `conta_nova` (N02b) é detectado pela varredura |
| **B8** — `modo_escrituracao` sem restrição de banco (baixa) | **Fechado** | `Empresa.objects.create(modo_escrituracao="qualquer")` agora levanta `IntegrityError ... "empresa_modo_escrituracao_valido"`. N24 morta. A reversão isolada da 0009 não foi medida |

**Detalhamento do A3**, com threads e conexões reais (`transaction=True`):

- **Ordem inversa**, ZIP `[A,B]` e ZIP `[B,A]` simultâneos: um processa (2 recebidos); o outro recebe `EnvioInvalido` "Já há um envio em processamento neste escritório". Zero exceções.
- **A trava é liberada ao fim da transação:** o envio seguinte passa (0 recebidos, 2 duplicados).
- **Espera de lock:** um envio de 1.501 notas no escritório A (4,75 s) mais a mesma nota solta no A 0,5 s depois resulta em `EnvioInvalido` **em 0,03 s**.
- **Sem falso positivo entre escritórios:** a mesma nota, com tomador cliente do escritório B, entra **no B em 0,06 s**, durante o envio do A.
- **Pela tela:** o segundo envio dá **400** com a mensagem legível.
- N03 (retirar a trava) morre.

## Achados novos

### N1 — O `except` de erro de banco por arquivo transforma erro de sistema em "recusado" e aparenta sucesso

- **Gravidade:** média.
- **Requisito:** AGENTS.md §8 (falha não pode virar sucesso aparente); critérios 7, 8 e 31; o próprio pedido da DE-076 ("não mascarar erro de sistema").
- **Onde:** `apps/fiscal/services.py:524-542`. O `except DjangoDBError` só devolve `OperationalError` ao chamador. `ProgrammingError`, `InternalError` e `NotSupportedError`, que indicam defeito de sistema e não arquivo ruim, viram `RECUSADO`.
- **Evidência:**
  - **Erro real de esquema:** renomeei a coluna `fiscal_documentofiscal.numero` num banco descartável e enviei uma nota válida pela tela. Resultado: **302**, lote com `(0 recebidos, 1 recusado)`, motivo `Arquivo recusado pelo banco de dados: column "numero" of relation "fiscal_documentofiscal" does not exist`.
  - **Simulado:** com `ProgrammingError` e com `InternalError` levantados na criação do documento, um ZIP de 3 notas dá **302**, `(0, 3)`, e **1 registro de trilha** `fiscal.envio_recebido`.
- **Impacto:**
  - Uma falha de implantação, como migração não aplicada, aparece ao contador como três notas recusadas, com lote e trilha de envio concluído.
  - O motivo exibe na tela texto interno do banco (nome de tabela e coluna).
  - Não há gravação de documento errado, mas o sistema quebrado passa por funcionando.
- **Correção recomendada:**
  - Capturar só `DataError`, ou `DataError` e `IntegrityError` de restrições conhecidas. Deixar `ProgrammingError`, `InternalError`, `InterfaceError` e `NotSupportedError` subirem como 500, desfazendo o envio inteiro.
  - Não ecoar `str(exc)` do banco no motivo; usar uma mensagem neutra e registrar o detalhe no log.
- **Como verificar:** o experimento acima deve dar 500 (ou erro de sistema), sem lote e sem trilha. Um teste com `ProgrammingError` simulado deve reprovar se a exceção for engolida.
- **Responsável:** `desenvolvedor-pleno`.

### N2 — Três comportamentos da trava e do tratamento de erro sem teste capaz de falhar

- **Gravidade:** baixa. O comportamento atual está correto e foi medido em A3.
- **Evidência:** mutações que sobrevivem à suíte completa (`2582 passed`):
  - **N04:** chave da trava `[_NAMESPACE, 0]` em vez de `escritorio.pk`. Isso cria **falso positivo entre escritórios**: o envio do escritório B seria recusado enquanto o A processa.
  - **N05:** `_e_erro_de_lock_ou_deadlock` sempre `True`, fazendo todo `OperationalError` virar "conflito, tente novamente". Mascara erro de sistema.
  - **N06:** retirar o `raise` de `OperationalError` no `except` por arquivo, fazendo lock ou deadlock virar "recusado" por arquivo.
- **Correção:** três testes.
  - Envio do escritório B aceito enquanto o A segura a trava.
  - `OperationalError` que não é de lock propaga.
  - `OperationalError` por arquivo propaga até `receber_envio`.
- **Responsável:** `desenvolvedor-pleno`.

### N3 — Duas implementações da identificação de empresa; a que produção não usa não tem teste

- **Gravidade:** baixa.
- **Requisito:** critério 13 (identificação num ponto só).
- **Onde:** `apps/fiscal/services.py:240-281`. `_localizar_empresa_por_cnpj` e `_localizar_empresa_por_cpf` têm um ramo com o dicionário, usado em produção, e outro com consulta ao banco (`mapa=None`), que nenhum código de produção chama. O filtro por escritório está escrito duas vezes: no dicionário (`:193`, `:198`) e nas consultas (`:252`, `:256`, `:279`).
- **Evidência:** F01 e F02, que retiram o filtro de escritório do ramo com consulta, **sobrevivem à suíte completa**. M1 e M2, no dicionário, morrem.
- **Impacto:** um chamador futuro que use `localizar_empresa_do_escritorio` sem o dicionário (por exemplo, a futura API REST) herda um caminho de isolamento que nunca foi exercitado.
- **Correção:** eliminar o ramo com consulta (sempre montar o dicionário) ou cobri-lo com o mesmo teste de dois escritórios.
- **Responsável:** `desenvolvedor-pleno`.

### N4 — O admin não cria nem edita empresa CPF

- **Gravidade:** baixa. Preexistente desde `3bf2d89`; não foi introduzido pela correção.
- **Evidência:** POST de alteração no admin de uma empresa CPF, sem mexer no tipo, dá **200** com `cnpj: Este campo é obrigatório.`, e nada é salvo. O limite declarado em `3bf2d89` falava só em "não cria".
- **Efeito colateral:** torna inalcançável pelo admin a regra de transição que N18 testaria.
- **Correção:** o formulário do admin tornar `cnpj` e `cpf` condicionais ao tipo, como `EmpresaForm` já faz; ou declarar o admin como não suportado para CPF.
- **Responsável:** `desenvolvedor-pleno`.

## Mutações da reconferência

Todas contra a **suíte completa**, com a falha preexistente deselecionada. Arquivos restaurados depois de cada execução; as worktrees terminaram limpas.

- **Sobreviventes da rodada 1 reaplicadas:** F04, F11, F14, F15, F16, F18, F21, F30, F35, F36 e C05 agora **morrem**. F02 sobrevive por atingir o caminho sem dicionário (N3); suas equivalentes no dicionário, M1 e M2, morrem.
- **Mutações novas nas correções:**
  - **Mortas:** N01, N02, N02b, N03, N07, N08, N09, N10, N11, N12, N13, N14, N15, N16, N17, N19, N20, N21, N22, N23, N24, M1, M2.
  - **Sobreviventes:** N04, N05, N06 (N2); N18 (ressalva de B2); F01 no caminho sem dicionário (N3).

## O que NÃO foi verificado

- `validate-docs.ps1`: sem `pwsh` no ambiente.
- Python 3.14.
- Tempo real sob gunicorn e no hardware de produção. A4 foi medido com o cliente de teste, localmente.
- Reversão isolada da migração 0009. A aplicação em banco vazio foi coberta pelo `--create-db`.
- PDF no navegador, teclado ao vivo e leitor de tela.
- Acervo real do escritório.
- Upload real acima de 50 MB por HTTP, para medir o consumo de banda da ressalva de A10: só inspecionado e testado pelo cliente de teste.
- Corrida entre criar estabelecimento e trocar a empresa para CPF, que não tem restrição de banco.

## Parecer por etapa

- **DL-010 fatia 1: APROVADA COM RESSALVAS.** Os três achados altos da rodada 1 (A1, A3 e A4) estão fechados e verificados por experimento. Ressalvas explícitas, que devem ir ao backlog porque não há terceira rodada:
  - **N1 (média):** erro de sistema do banco vira "recusado" com lote e trilha de sucesso aparente. Deve ser corrigido antes do primeiro uso real.
  - **N2 e N3 (baixas).**
  - Ressalvas de A4 (folga de tempo medida só localmente), A8 (EOCD forjado) e A10 (banda).
- **DL-038: APROVADA COM RESSALVAS.** B1 a B5, B7 e B8 estão fechados e verificados. Ressalvas:
  - **B6** continua valendo e aguarda o Fred (PE-68).
  - A regra de B2 não tem restrição de banco, e a checagem de transição em `Empresa.clean` não tem teste (N18).
  - **N4 (baixa):** o admin não edita empresa CPF.

**Parecer: APROVADO COM RESSALVAS**
