# DL-033 — Circulante e não circulante

**Demanda:** autorização do Fred em 2026-09-21 — *"pode seguir com circulante e
não circulante"*.
**Depende de:** [DL-032](DL-032-a-camada-de-saldos.md), entregue.
**Nível de risco: 1** (§3.1 do [AGENTS.md](../../AGENTS.md)) — muda o **modelo** e
é o que falta para existir Balanço. Erro aqui vira documento errado na mão do
cliente.

## Por que agora

É o **único** dado que falta para o Balanço Patrimonial existir. A camada de
saldos já entrega os cinco totais; o que ela não sabe é separar o que é
**circulante** do que é **não circulante** — e sem isso não há BP apresentável,
só um resumo de grupos.

## ⚠️ A norma, levantada em fonte oficial ANTES de desenhar

Está no **RC-106**, com texto literal e data de consulta. O resumo do que decide
o desenho:

| Fonte | O que fixa |
| --- | --- |
| **Lei 6.404/76, art. 178 §1º/§2º** (red. Lei 11.941/2009) | Ativo tem **dois** grupos; passivo tem **três** (incluindo o PL). O **não circulante do ativo** se subdivide em realizável a longo prazo, investimentos, imobilizado e intangível |
| **Art. 179, I e II** | Circulante = realizável **no curso do exercício seguinte** |
| **Art. 180** | Obrigação é circulante **quando vencer no exercício seguinte** |
| **NBC TG 26 (R5), item 60** | Os grupos são **separados no balanço**; ordem de liquidez é **exceção**, não alternativa livre |
| **Itens 66 e 69** | Quatro critérios para ativo e quatro para passivo — **qualquer um** basta |

⚠️ **Três consequências que a norma impõe e que eu não podia adivinhar sem
lê-la:**

1. **O critério é relativo à DATA**, não é propriedade eterna do direito: *"até
   doze meses após a data do balanço"*. O mesmo direito muda de grupo de um ano
   para o outro.
2. **O ciclo operacional pode alargar o corte** (art. 179, parágrafo único). Só
   quando ele **não é claramente identificável** é que se presume doze meses
   (NBC TG 26, item 68).
3. **O ativo não circulante tem QUATRO subgrupos nomeados por lei.** Não são
   dois níveis, são dois grupos e quatro subdivisões — e isso muda o que a
   camada de saldos precisa devolver.

## A decisão de modelagem, e ela é minha

**A classificação é campo da CONTA, não cálculo por data.** E a passagem de
longo prazo para curto prazo se faz por **lançamento de reclassificação**, não
editando a conta.

**Por que, e é a única razão que importa:** o modelo **já recusa** mudar
natureza ou tipo de conta com movimento (`Conta.clean()`, BL-83 / BL-245 /
BL-261), porque a troca **reescreveria o histórico** — o Balancete de um período
já emitido passaria a mostrar outro número. Classificação editável sem vigência
tem exatamente esse defeito, e pior: mudaria **Balanços já entregues ao
cliente**, em silêncio.

⚠️ **Isto é HIPÓTESE sobre a rotina do escritório, marcada como HI-18, e a
pergunta é a PE-64.** A norma diz **o que** classificar; ela **não** diz como o
escritório opera. Se o Fred responder que lá se troca a classificação da conta
em vez de lançar a reclassificação, o campo continua e **só a guarda muda** — de
"recusa" para "versiona". **Sigo pela conservadora porque o erro dela é barato e
o erro da outra é caro.**

## Escopo da fatia 1

1. **Campo de classificação na `Conta`**, cobrindo o que a lei nomeia:
   circulante; e, no não circulante do ativo, os **quatro subgrupos** do art.
   178 §1º II. ⚠️ **Derivado de uma fonte única no código, nunca uma tupla
   escrita à mão** (DE-056).
2. **Guarda no modelo**, no mesmo molde do BL-83: mudar a classificação de conta
   **com movimento próprio ou de descendente** é **recusado**, com mensagem que
   orienta o caminho certo (conta nova + lançamento de reclassificação).
3. **A camada de saldos passa a devolver os grupos da lei**, além dos cinco
   tipos que já devolve.
4. **Migração sobre base com dados**: nenhuma conta existente nasce
   classificada por adivinhação. ⚠️ **Ver "o que NÃO fazemos" abaixo.**

**Fora do escopo:** tela do Balanço, tela de cadastro da classificação,
demonstrações, ciclo operacional maior que doze meses, e a exceção de ordem de
liquidez do item 60.

## ⚠️ O que esta etapa NÃO faz, e é deliberado

**NÃO adivinha a classificação das contas que já existem.** A tentação é ler o
código (`1.1` = circulante) ou o nome (`"Caixa"`) e preencher sozinho. **Isso é
inferir semântica da nomenclatura do contador** — exatamente a classe do achado
**BL-475**, que custou uma reprovação nesta semana: o sistema decidiu por
posição na árvore e afirmou que tinha fechado.

**Conta existente nasce SEM classificação, e a camada declara quais são.** É o
mesmo padrão que a DL-032 já usa para tipo divergente: **nomear, nunca
presumir**. O contador classifica, e o produto mostra o que falta.

## Critérios de aceite

1. **Os grupos vêm da LEI, derivados de fonte única** — nenhuma tupla de strings
   à mão. Teste derivado que **reprova** se um grupo novo aparecer sem
   tratamento (DE-056), no molde do que a DL-032 já tem.
2. **Mudar a classificação de conta COM movimento é recusado**, no modelo, com
   mensagem que nomeia o caminho certo. Teste para conta com movimento **próprio**
   e para conta com movimento **só de descendente** — foi essa segunda forma que
   escapou na BL-83.
3. **Conta SEM movimento pode ser classificada e reclassificada** livremente.
   Controle positivo: sem ele, a guarda pode estar recusando tudo.
4. ⚠️ **CORRIGIDO em 2026-09-21, e a correção é de OMISSÃO MINHA** — a
   redação original dizia só *"a camada devolve os grupos, e a soma deles bate
   com os totais por tipo"*. Ela dizia **o que** tinha de bater e **não** de
   onde o valor sai, nem **em que nível da árvore** a classificação pode ser
   declarada. **Era a decisão mais difícil da fatia, e caiu no implementador sem
   enunciado** — foi exatamente ali que o bloqueador **A1** nasceu
   ([auditoria rodada 1](../auditorias/2026-09-21-dl-033-rodada-1.md)).

   **A redação que vale, e é uma INVARIANTE, não um mecanismo:**

   > **`Σ(grupos de um tipo) + resíduo declarado == totais_por_tipo[tipo]`,
   > SEMPRE** — qualquer que seja o nível em que o contador declarou a
   > classificação, com retificadora entre irmãs, com nó intermediário
   > movimentado e sem classificação, e com cobertura parcial.

   **O resíduo é CALCULADO e DEVOLVIDO**, nunca zero por construção: qualquer
   valor diferente de zero significa que há dinheiro fora dos grupos, e a fatia
   que emitir o Balanço **recusa emitir** enquanto ele não for zero.

   ⚠️ **Por que invariante e não lista:** lista é catálogo de casos que alguém
   pensou; **identidade aritmética fecha também o caso que ninguém pensou**. Foi
   a recomendação do auditor e eu a adoto inteira — ela fecha A1, A2 e A6 de uma
   vez.

   ⚠️ **E a lição de enunciado, que passa a valer para todo plano meu:** eu
   escrevi o critério descrevendo o **mecanismo que eu suspeitava** (dupla
   contagem) em vez da **propriedade que tem de valer**. A suspeita estava
   errada — não havia duplicação nenhuma — e o defeito real era o oposto: somar
   com **sinal trocado** e **deixar de somar**. **Enunciado por invariante teria
   pego os dois; enunciado por suspeita não pegou nenhum.**
5. **Conta sem classificação é DECLARADA, nunca presumida** — lista própria na
   resposta, vazia quando todas estão classificadas. Controle positivo
   obrigatório.
6. **Migração sobre base COM dados**: nenhuma conta existente é classificada
   automaticamente, e nenhum saldo muda. Teste com `MigrationExecutor`.
7. **Isolamento e leitura pura** não regridem: a camada continua sem gravar nada,
   e conta de outra empresa não entra.
8. **Sem regressão**: suíte, `ruff check`, `ruff format --check`,
   `manage.py check`, e migrações em banco vazio. ⚠️ **Esta etapa TEM migração**
   — ao contrário da DL-032 —, então `makemigrations --check` deve ficar limpo
   **depois** dela.

## Riscos declarados

- **Migração de modelo em base com dados.** É a primeira desde a DL-016. Nenhum
  `RunPython` que classifique conta.
- **O campo novo entra na resposta do Balancete**, como `tipo` e `raiz` entraram
  na DL-032. Mesma checagem: aditivo, nenhum consumidor quebrado.
- **A guarda pode ser larga demais.** Se recusar reclassificação de conta sem
  movimento, trava o trabalho normal do contador. Daí o critério 3.

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Modelo, migração, guarda e camada | `desenvolvedor-pleno` | `apps/contabilidade/models.py`, `services.py`, `migrations/`, testes |
| Ressalvas abertas da DL-032 | `desenvolvedor-pleno`, na mesma janela | **BL-483**, **BL-484**, **BL-485** |
| Documentação | `arquiteto-senior` | `docs/**` |

**Proibido:** `templates/**`, `static/**`, `views_web.py`, `urls_web.py` — não há
tela nesta fatia.

## Verificação

**Nível 1: auditoria independente da versão integrada.** Regra de parada da
§3.1: uma auditoria, uma correção, uma reconferência — **sem terceira**.

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
