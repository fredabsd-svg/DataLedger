# Auditoria e reconferência — DL-061 fatia 2 (BL-605): marcação manual e API da DMPL

**Auditor:** `auditor-qa` — auditoria independente, somente leitura (as sondas de
quebra rodaram de arquivos fora do repositório, em `%TEMP%`). Este documento
consolida os dois relatórios do auditor (auditoria e reconferência), na ordem
em que foram emitidos em 03/10/2026, sobre a árvore de trabalho da branch
`feat/dl-061-fatia-2`. **Escopo auditado:** o SERVIDOR da fatia 2 (modelo
`MarcacaoDmpl`, serviços E15–E17, gancho em `apurar_dmpl`, API E18, testes). A
tela (E19) ficou fora do escopo — nível 2 pelo §3.1 do AGENTS.md, com testes de
comportamento próprios.

---

## 1. Veredito da auditoria (rodada única)

**APROVADO COM RESSALVAS** — E15–E18 implementados e testados por comportamento
(30 testes novos verdes, guardas ajustadas legítimas, sem regressão), com quatro
achados:

| Achado | Severidade | O que era | Correção |
| --- | --- | --- | --- |
| **A1** | média | O contrato E16 por coluna aceitava e **publicava** evento inexistente no livro: par líquido zero (+500 "Aumento de capital" / −500 "Redução de capital") em coluna que o lançamento **não move** fecha o Σ (=0=efeito), passa no E17 e sai na DMPL emitível. Saldo e conciliação fecham (o par some), por isso nenhum teste anterior pegava | Exigir que toda coluna citada seja movimentada pelo lançamento (≥1 item), **derivado dos itens** — nunca "efeito ≠ 0", porque o gêmeo legítimo (compra e venda de tesouraria de valores iguais, efeito zero com itens reais) depende desse formato |
| **A2** | baixa | `_instancias_de_marcacao` aceitava chave extra em silêncio, contradizendo a própria mensagem ("nada além disso") e a BL-196 | Recusa estrita: `set(entrada) != {"linha","coluna","valor"}` |
| **A3** | baixa | A defesa de leitura não reaplica o E17: marcação gravada por ORM/SQL direto em lançamento que a regra decide é honrada na leitura | Decisão do responsável: **registrar o residual** (classe "só ORM/SQL direto", como as constraints) — sem mudança de código |
| **A4** | baixa (processo) | O plano exigia a tela (critério 5/E19) sem registrar o que ficava para depois | Registrar no plano as duas fatias internas da etapa (servidor auditado; tela na mesma etapa) e o critério 5 verificado na integração da tela |

**Pré-existente (não desta etapa):** suíte completa com 160–165 falhas
ambientais (faixa medida; concorrência com threads/SQLite, gatilhos de
PostgreSQL não exercitáveis fora dele, symlinks/umask no Windows, navegador e
poppler ausentes) — **zero** falhas nos arquivos do escopo auditado.

### Sondas de quebra executadas (15, saída real)

Par inventado em coluna intocada (ACEITO — A1); item com chave extra (ACEITO —
A2); `Decimal` quebrado/escala/formato (recusas corretas, inclusive `"1e3"`,
`"banana"`, `"-0.00"`); marcação parcial (recusada nomeando coluna e os dois
valores); linha/coluna fora do enum (recusa + 400); valor zero (recusa + 400 +
`IntegrityError` da constraint); empresa alheia (404, nada gravado; modelo
recusa empresa ≠ do lançamento); lançamento decidido pela regra (E17 recusa —
a marcação é a EXCEÇÃO da RC-151); duplicata de linha×coluna (recusa + 400 +
`UniqueConstraint`); linhas de saldo (recusadas); coluna não renderizável
(recusa e, gravada à força, não vira célula fantasma); substituição atômica
(três saves iguais = 1 conjunto; lista vazia limpa; segundo PUT substitui);
corpos hostis da API (chave extra, item não-dict, lista errada, corpo sem chave
— todos 400, nenhum 500); imutabilidade (nenhum campo do lançamento muda;
`save()`/`delete()` levantam `LancamentoImutavelError`); trilha (3 operações →
3 `RegistroAuditoria` com ator e antes/depois na mesma transação; recusa não
grava nada); desmarcar (o veto volta exatamente); defesa de leitura (Σ
desatualizado volta para a regra e o veto acende); identidade DLPA × DMPL com
marcação em lucros (confere).

### Verificações do auditor (saída real)

`test_dl061_bl605_marcacao_manual.py` → 30 passed · guardas e varreduras → 217
passed · `test_dl061_*` + DLPA → 339 passed, 3 skipped · `ruff check .` e
`ruff format --check .` limpos · `manage.py check` sem problemas ·
`makemigrations --check` = "No changes detected" · `validate-docs` = 217
arquivos válidos · suíte completa 2× (163 e 160 falhas ambientais; `grep
'^FAILED'` sem nenhuma linha do escopo) · migração `0020` aplicada em banco
vazio pela criação do banco de teste.

---

## 2. Correção única (AGENTS.md §3.1)

Aplicada pelo `desenvolvedor-pleno`, só em `services.py` e no teste da marcação:

- **A1:** `salvar_marcacoes_da_dmpl` recusa toda coluna sem item do lançamento
  (as chaves de `movimento` vêm dos ITENS), com mensagem nomeando a coluna;
  `_marcacoes_valem_como_celulas` ganhou a terceira condição igual (fora disso,
  volta para a regra automática e o veto acende). Três testes de regressão: o
  par inventado recusado; a marcação forçada por ORM que não vira célula; e o
  **gêmeo legítimo preservado** (efeito zero com itens reais → aceito e
  publicado como os dois brutos).
- **A2:** recusa estrita de chave extra, com teste.

Verificação pós-correção (implementador e orquestrador): 34 passed no arquivo da
marcação; 419 passed nos afetados; `ruff`, `check` e `makemigrations --check`
limpos.

---

## 3. Veredito da reconferência (encerramento do ciclo)

**APROVADO COM RESSALVAS** — A1, A2 e A4 **fechados** com evidência executada
(sondas P1/P2 reproduzidas: antes ACEITO → agora RECUSADO/400; R2: ORM forçado
não vira célula e o veto acende; R3: gêmeo legítimo aceito e publicado; R4:
controle anti-excesso — o caso M2 com brutos reais continua aceito). A3 fechado
como residual declarado.

**Achado novo da reconferência (N1, baixa, texto):** a frase do registro A3 no
plano descrevia mecanismo inexistente ("passa a valer se a regra não decidir
mais na leitura… coberto pela defesa de leitura") — medido pela sonda R6: a
marcação forçada por ORM em lançamento decidido **é honrada** na leitura (o E17
não é reaplicado). Corrigida na integração (texto do plano reescrito para dizer
o que o código faz), sem nova rodada de auditoria, como autorizado pelo §3.1.

**Ciclo encerrado:** uma auditoria, uma correção, uma reconferência. Não há
terceira rodada.

---

## 4. Separação do que é do Fred × técnico

- **Não muda** RC-151 (a marcação continua sendo a exceção: E17 recusa quem a
  regra decide), RC-153 e RC-155 (a marcação entrega os brutos nas duas linhas,
  como a M2 pediu).
- **Para o Fred (critério):** A1 tocou a promessa "a marcação muda AONDE o valor
  aparece, nunca QUANTO existe" — o auditor registrou que, se o critério for
  "nenhuma célula do documento sem lastro no livro", a correção era obrigatória;
  foi o que se fez. O caso-limite aceito continua sendo o conjunto que reproduz
  o Σ por coluna (decisão E16 do plano).
- **Técnico:** A2, A3 (residual), A4/N1 (registro), migração de criação e
  guardas nominais.
