# DL-048 — Fatia D8: paridade de API da DLPA

**Nível de risco:** 2 — "o contador usa" (API, telas de conferência). Pelos §3.1 do
`AGENTS.md`, a cerimônia é **plano de uma página** e **testes do comportamento**;
auditoria independente **só na primeira entrega do módulo**, que já aconteceu na fatia
CTB-12/CTB-13 (rodada 1 de 29/09). **Esta fatia não abre auditoria nova.**

**Origem:** decisão **D8** do [plano da DL-048](DL-048-contabilidade-anual-demonstracoes.md)
— *"Tela primeiro, API depois"*. A tela da DLPA e a de classificação já existem e
estão na `main` (PR #59); falta a **porta de API**.

**Branch:** `feat/dl-048-d8-api` → `main`.

## Objetivo e escopo

Entregar as três peças que a decisão D8 listou, e **nada além delas**:

1. `DlpaView` — `GET` da DLPA por empresa/ano/mês.
2. `ContaClassificacaoDlpaView` — `PATCH` da `classificacao_dlpa` de uma conta.
3. `ContaSerializer.classificacao_dlpa` — o campo passa a ser exposto e aceito pela
   porta de contas, com a mesma compatibilidade de tipo que `classificacao_dre` já tem.

**Fora do escopo:** nenhuma regra de apuração muda. A D8 **revela** o que
`apurar_dlpa`/`avaliar_emissao_da_dlpa` já decidem; não duplica nem recalcula nada.
Nenhuma tela, nenhum template, nenhuma migração, nenhum enum.

## O desenho que o Fred pediu: a DLPA embutida na DMPL (art. 186, §2º)

> *"D8 (API da DLPA): projete prevendo que a DLPA pode estar embutida na DMPL
> (art. 186, §2º), e não só como peça autônoma."*

A Lei 6.404/76, art. 186, §2º, diz que a DLPA *"poderá ser incluída na demonstração das
mutações do patrimônio líquido, se elaborada e publicada pela companhia"*. É
**faculdade da lei**, não dever — e a DMPL é a CTB-14, que vem depois.

Isso vira **duas decisões concretas** na API, e não uma frase no docstring:

**1. O §2º é declarado, nunca omitido.** O achado 11 da auditoria de 29/09 registrou que
*"o § 2º (dividendo por ação) não existe no enum"* e que *"a base de cálculo é do DMPL
(CTB-14)"*. Uma API que devolvesse só as linhas da DLPA **esconderia** essa pendência de
quem consome. Por isso a resposta traz um bloco `paragrafo_2` que **sempre existe**, com
`dividendo_por_acao: null` e o motivo. Cliente que só a veja quando há valor não tem como
distinguir "não há" de "o servidor não responde isso" — o mesmo raciocínio de
`_aviso_de_movimento_fora_do_periodo` (BL-198).

**2. A `chave` de cada linha é o contrato com a DMPL.** A RC-137 fixa que a linha da
DLPA é a **destinação** e a coluna da DMPL é a **contrapartida** — *"o mesmo fato visto
por dois lados"*. Por isso a apuração **não** emite uma coluna de DMPL: emite a
**leitura estruturada do evento**, e a linha carrega a `chave` que é a identidade do
evento. A CTB-14 consome essas chaves como movimentos de coluna, sem segunda lógica.
A regra de direção (D4 — reduzir é destinação, aumentar é reversão) já está embutida na
`chave` (`transferencia:<reserva>` × `reversao:<reserva>`), então a DMPL não precisa
recalcular isso.

⚠️ **O que a API NÃO faz, por decisão:** não calcula dividendo por ação, não emite
coluna de DMPL, e não escolhe entre "autônoma" e "embutida" — essa escolha é da
**emissão**, não da leitura. A API entrega a mesma apuração nos dois casos.

## Regras que viram teste

| # | Regra | Teste |
| --- | --- | --- |
| R1 | `GET` exige `PodeLerContabilidade`; 403 para quem não pode ler | anônimo e papel sem acesso |
| R2 | `GET` 404 para empresa de **outro** escritório (isolamento) | empresa alheia |
| R3 | `409` quando `pode_emitir` é falso — **e o corpo traz o número assim mesmo** | movimento sem classificação |
| R4 | Valores monetários como **string de duas casas** (`_como_moeda`), nunca float | saldo 13.750,00 |
| R5 | `paragrafo_2` **sempre presente**, com `dividendo_por_acao: null` e a fonte | sem movimento e com movimento |
| R6 | `PATCH` exige `PodeEscriturar`; 403 sem permissão | analista/visitante |
| R7 | `PATCH` 404 para conta de outra empresa | conta alheia |
| R8 | `PATCH` de corpo não-dicionário ou valor não-`str` → **400**, nunca 500 | corpo lista, valor `dict` |
| R9 | `PATCH` grava e devolve a `Conta` com `classificacao_dlpa` | classificar e reclassificar |
| R10 | `PATCH` registra **trilha** com o valor antes e o de depois | `conta.classificacao_dlpa_alterada` |
| R11 | Incompatibilidade de **tipo** é 400 nomeando a linha e o tipo aceito | receita classificada como reserva |
| R12 | `""` e `null` **removem** a classificação, sem erro | normalização (mesma regra do achado A4) |

## Impacto

- **Permissões:** nenhuma nova. Reaproveita `TemEscritorioAtivo` + `PodeLerContabilidade`
  (GET) e `PodeEscriturar` (PATCH) — a mesma divisão de `DreView` e
  `ContaClassificacaoDreView`. A classificação é escrita, logo pede quem escreve.
- **Dados:** nenhum modelo novo, nenhuma migração. `classificacao_dlpa` já existe
  (migração 0012).
- **Cálculo:** nenhum. `Decimal` em toda a resposta, via `_como_moeda`.
- **Contratos:** a API é nova; nenhum contrato existente muda. O bloco `paragrafo_2` é
  aditivo.
- **Desempenho:** o mesmo custo de `apurar_dlpa` — já declarado constante em relação a
  lançamentos e contas (5 consultas + `apurar_saldos`).

## Reversão

`git revert` do commit. Sem migração, sem dado gravado em ambiente compartilhado: a
D8 só lê; a única escrita é a classificação, que já era gravável pela tela.

## Critérios de aceite

1. As três peças existem, com os doze testes acima verdes.
2. `paragrafo_2` presente em **toda** resposta, com a pendência nomeada.
3. Isolamento testado nos dois sentidos (empresa e conta).
4. Nenhuma linha de `services.py`, `models.py` ou template alterada.
5. `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check` e
   `validate-docs.ps1` limpos.
6. `docs/agents/estado.md` atualizado.
