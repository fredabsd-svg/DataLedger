# Reconferência da DL-068 (nível 1, AGENTS.md §3.1)

**Registro do arquiteto:** relatório transcrito **integralmente**, sem edição,
supressão nem suavização de achado. A única intervenção é tipográfica: o sinal
`>=` voltou à forma literal. Rodada anterior:
[rodada 1](2026-10-07-dl-068-rodada-1.md). Plano:
[DL-068](../planos/DL-068-prontidao-para-implantacao.md). Pelo §3.1 **não há
terceira rodada**. O tratamento dos achados novos está no fim, separado do
texto do auditor.

---

**Parecer: APROVADA COM RESSALVAS.**

**Versão auditada:** `/home/user/DataLedger`, branch `ccr-9e799dfb-48okf5`,
commit `41492df`.
**Auditor:** `auditor-qa`. Nada foi delegado.
**Método:**
- Execução no repositório, com banco próprio `dataledger_auditor`.
- Comparação do `.dockerignore` com o `moby/patternmatcher`, o código do Docker.
- Mutação do pin em cópia fora do repositório.

**Efeitos colaterais:** `git status` e `git diff --stat` ficaram limpos depois
de tudo. Nada foi gravado em `docs/auditorias/`.

Os achados da rodada 1 estão fechados ou aceitos. A correção do N2 fecha só a
soma exata de uma família: tirar um pedaço que nenhum cliente ocupa ainda passa
(R1). Sobram dois achados baixos, R1 e R2, e uma observação (R3).

## Achado da rodada 1 → situação

| Id | Situação | Evidência |
| --- | --- | --- |
| N1 | **Fechado** | `grep DL-068 docs/agents/estado.md` agora acha a linha 136 da tabela e o Próximo passo (linha 147). Conferi as afirmações dele: a rodada 1 está registrada e os números batem com o meu relatório (14 critérios, 4.858, 1 falha de Python 3.13, 53 pulados). Os destinos de N3, N4 e N6 existem no `backlog.md` (BL-53, BL-580, BL-632), assim como BL-635 a BL-641, PE-07 e PE-25. O "Falta: reconferência, PR com os quatro checks, merge" é verdade: não há PR (`gh` só tem GraphQL bloqueado) e o remoto tem só `main` e a branch de sessão. O plano traz a decisão do item 5 e o critério 12 com a soma. `test_documentacao_do_estado.py`: 19 passaram. Links e formatação dos 4 `.md` alterados: sem problema, por script próprio (sem `pwsh`). |
| N2 | **Fechado para a soma exata. Contorno restante: R1** | Ver seção N2 abaixo. |
| N3 | Registrado | BL-53 exige `check --deploy`. Aceito como registro. |
| N4 | Registrado | BL-580. `::ffff:0:0/96` continua passando em silêncio (rc=0, sem aviso), como no BL-580. |
| N5 | **Fechado, com R2** | Ver seção N5 abaixo. |
| N6 | Aceito | BL-632 descreve a consequência para o suporte. |
| N7 | **Fechado** | Ver seção N7 abaixo. |
| N8 | Ambiente | Continua Python 3.13. A prova em 3.14 é a CI do PR. |

## N2: somas testadas

Rodei `manage.py check` num processo novo para cada valor, com `DEBUG=False` e
PostgreSQL.

**Recusadas (rc=1, mensagem "a soma das redes IPvN … trilha"):**
- `0.0.0.0/1,128.0.0.0/1` e `::/1,8000::/1`.
- Quatro `/2` em IPv4, e `::/2,4000::/2,8000::/2,c000::/2` em IPv6.
- `/1` mais dois `/2`.
- Redes sobrepostas com `10.0.0.0/8` no meio.
- Bits de host: `0.0.0.1/1,128.0.0.7/1`.
- 256 redes `/8`.
- Escada `0/1,128/2,192/3 … 254/8,255/8` mais um IP único.
- IPv4 completo somado a IPv6 parcial.
- `0.0.0.0/0.0.0.0`, que cai na recusa por entrada.

**Sobem sem aviso (rc=0, sem `W001`), como deve ser:**
- Lista vazia.
- Um IP único.
- Privadas: `10/8`, `192.168/16`, `172.16/12` e `fd00::/8`.
- `0.0.0.0/1` sozinho, porque só avisa.

**Sobem e avisam, como deve ser:**
- Faixa de CDN: `173.245.48.0/20`, `103.21.244.0/22` e `2400:cb00::/32`.

**Não pegos:**
- `::ffff:0:0/96`, por ser inerte (N4).
- O contorno de R1.

## N5: `.dockerignore` contra o `patternmatcher`

Comparei 10.559 caminhos: os do repositório mais 30 casos escolhidos. Houve 0
divergências entre o interpretador do teste e o Docker.

**Ficam FORA da imagem:**
- `config/.env`
- `apps/x/.env`
- `prod.env`
- `config/.env.local`
- `ENV.env`
- `.env`
- `.env.producao`
- `a/b/chave.pem`, `a/b/chave.pfx`, `a/b/c.p12` e `a/b/c.key`

**Entra na imagem:** `.env.example` da raiz.

**Fica fora:** `x/.env.example` e `docs/.env.example`. Isso é intencional, e
nenhum arquivo versionado tem esse nome.

**Arquivos versionados:**
- Dos 1.002 arquivos versionados, 25 ficam fora da imagem.
- Todos estão em `.claude`, `.codex`, `.github` ou `.agents`.
- O `Dockerfile` não depende deles, e o teste de arquivos copiados passa.

**Efeito no `.gitignore`:**
- `git ls-files -ci --exclude-standard` não devolve nada, então nenhum arquivo
  versionado passou a ser ignorado.
- `git ls-files` por extensão sensível devolve só `.env.example`.
- `git check-ignore` confirma que `.env.example` e `docs/.env.example`
  continuam fora do ignore. Também confirma que `config/x.env`, `a/cert.pfx` e
  `.env.local` entram.

## N7: mutação do pin

Copiei o teste e o `requirements/base.txt` para o scratchpad, variando o pin.

| Mutação | Resultado |
| --- | --- |
| `Django==6.1.1` | **Morre**: 2 testes falham |
| `Django==6.1.3` (instalado 6.1.2) | **Morre**: o teste "instalado é o fixado" falha |
| `Django>=6.1.2` | **Morre**: 2 testes falham |
| `Django==6.1.2` (controle) | 10 passam |

## Regressão

| Verificação | Resultado |
| --- | --- |
| `pytest` completo, banco `dataledger_auditor` | **4.887 aprovados, 1 reprovado, 53 pulados** em 8m28s |
| Diferença para a rodada 1 | 4.858 → 4.887 aprovados (+29 testes novos). A falha e os pulados são os mesmos. |
| A falha | `test_versao_minima_python::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`: `SyntaxError: multiple exception types must be parenthesized` em `/usr/lib/python3.13/ast.py`. É Python 3.13, a mesma da linha de base. |
| `ruff check .` | Limpo |
| `ruff format --check .` | 370 arquivos já formatados |
| `manage.py check` | Sem problemas |
| `makemigrations --check --dry-run` | "No changes detected". Aviso de que o banco `dataledger_auditor` não existe; só o `test_` existe. |
| `gerar_agentes.py --verificar` | OK, 7 papéis |

## Achados novos

| Id | Gravidade | Achado e evidência | Responsável |
| --- | --- | --- | --- |
| R1 | Baixa | **A recusa do N2 só vale para a cobertura exata de uma família.** `config/settings.py:~118-130` recusa quando `collapse_addresses` chega a `/0`. Mas `0.0.0.0/8` e `255.255.255.255` não são IPs de cliente. Tirar um deles basta para passar. Reproduzi com `ipaddress.ip_network("0.0.0.0/0").address_exclude(...)`. Em **processo**: oito redes (tudo menos `0.0.0.0/8`) sobem em `manage.py check` com rc=0 e só `W001`. Com elas, `REMOTE_ADDR=1.2.3.4` e `X-Forwarded-For: 9.9.9.9` gravam `9.9.9.9`, o mesmo resultado do N2 original. Tudo menos `255.255.255.255/32`, tudo menos um `/8` e `::/0` menos `::1/128` também sobem com aviso. O decisor escreveu "é a propriedade, não uma lista de casos", mas a propriedade real é "o IP do atacante é confiável", e ela só é barrada no caso exato. Exige configuração deliberada, não é acidente. **Recomendação:** o piso do HI-51 (decisão do Fred), isto é, recusar redes menores que um prefixo mínimo, ou recusar quando a união cobre quase tudo. Se o arquiteto mantiver a regra, reescrever o comentário de `settings.py` e o critério 12 para dizer "cobertura exata". **Verificação:** teste parametrizado com `address_exclude` de `0.0.0.0/8`, ou com o piso aprovado. | `desenvolvedor-pleno`; decisão do Fred |
| R2 | Baixa | **Extensões em maiúscula escapam.** `x/y/z/cert.KEY` e `cert.PEM` ficam DENTRO da imagem (`patternmatcher`, com 0 divergências do teste), e o `.gitignore` também não os pega. É o mesmo comportamento do Docker. Certificado exportado no Windows costuma ter `.PFX`. `ENV.env` está coberto, mas `PROD.ENV` não. **Recomendação:** acrescentar `**/*.PEM`, `**/*.PFX`, `**/*.P12`, `**/*.KEY` e `**/*.ENV`, ou exigir a regra no procedimento do módulo fiscal. | `desenvolvedor-pleno` |
| R3 | Observação | `docs/agents/estado.md:133`, a linha da DL-066 na tabela, ainda diz "falta a porta de classificação, a tela, a API e o método indireto". O Próximo passo diz que a fatia 1 está FECHADA. **Já era assim em `2f1ac3a`, não foi introduzido pelas correções.** Também: o docstring de `apps/auditoria/checks.py` fala só de `/0` e não da soma, e o comentário de `settings.py` (3ª linha do trecho BL-577) ficou mais longo que as outras. Todos cosméticos. | `arquiteto-senior` |

Defeito novo introduzido pelas correções: não encontrei nenhum além de R1 e R2,
que são limites das regras novas. Perguntei explicitamente se algum arquivo
versionado saiu da imagem por engano ou passou a ser ignorado: não.

## Não foi possível verificar

- **Build real da imagem Docker.** Sem daemon. A semântica do `.dockerignore`
  foi provada pelo `patternmatcher`, mas `docker build` não rodou.
- **Python 3.14**, o da CI. Aqui é 3.13.
- **`pwsh ./scripts/validate-docs.ps1`.** Substituído por checagem própria.
- **Concorrência real e proxy real em HTTPS.** Herdados da rodada 1, não
  refeitos.
- **PR.** Ainda não existe. Os quatro checks verdes dependem da CI.

## Parecer

**APROVADA COM RESSALVAS.** N1, N5 e N7 estão fechados, e o N2 está fechado
para a soma exata. Sobram R1, R2 e R3, mais os N3, N4 e N6 que já estavam
registrados. A suíte não regrediu. Isto não é garantia de ausência de
defeitos. Pelo §3.1 não há terceira rodada.

---

## Tratamento (arquiteto-senior, 07/10/2026)

O ciclo de auditoria termina aqui. As correções abaixo **não** passaram por
auditoria independente: a verificação delas é a dos testes com mutação e a da
CI do PR.

| Achado | Decisão |
| --- | --- |
| R1 | **Mantida a regra da cobertura exata, com limite declarado.** O comentário de `settings.py`, a docstring de `checks.py` e o critério 12 do plano passam a dizer "cobertura exata". Para explorar o contorno é preciso configurar o servidor de propósito, e quem faz isso já o controla; a guarda existe contra erro de configuração. Fechar o "tudo menos" exige o piso da HI-51: decisão do Fred, registrada no BL-642 |
| R2 | **Corrigido** (BL-643): classes de caracteres (`[pP][fF][xX]` etc.) no `.dockerignore` e no `.gitignore`, que cobrem maiúscula e caixa mista. Oito casos novos no teste. A mutação que volta `.pfx` para minúsculas derruba 2 testes. `git ls-files -ci --exclude-standard` continua vazio |
| R3 | **Corrigido:** linha da DL-066 na tabela do `estado.md`, docstring de `checks.py` e quebra do comentário de `settings.py` |
