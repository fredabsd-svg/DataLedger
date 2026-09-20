# DL-031 — Fatia 2 da DL-016: a tela do fechamento

**Demanda:** autorização do Fred em 2026-09-20 — *"pode abrir a fatia 2"*.
**Depende de:** [DL-016 fatia 1](DL-016-competencia-e-fechamento.md), fechada e
auditada em duas rodadas
([rodada 2](../auditorias/2026-09-20-dl-016-fatia-1-rodada-2.md)).
**Nível de risco: 2** (§3.1 do [AGENTS.md](../../AGENTS.md)) — é o que o
contador usa, e **a garantia contábil já está no servidor**. Por isso este plano
cabe em uma página, e não há auditoria completa de etapa.

⚠️ **O que torna o nível 2 legítimo aqui, e não conveniência:** fechar, reabrir,
entregar e recusar lançamento em mês encerrado são decididos e verificados **no
serviço**, já medidos sob concorrência real. Nenhuma regra contábil desta fatia
mora na tela. Se a tela estiver errada, o contador não consegue operar — **não**
perde dinheiro nem grava livro errado.

## O problema que ela resolve, em uma frase

**Hoje o contador não consegue fechar o mês.** A trava existe e não há porta:
só requisição direta à API, que não é o que o escritório usa. É a dívida que a
ordem "trava antes do botão" criou de propósito, e a
[DE-065](../projeto/decisoes.md) mandou pagá-la agora, antes de qualquer módulo
novo.

## Arquétipos e o momento da verdade

Pela [direção de arte](../projeto/direcao-de-arte.md), §2: a tela é **D (painel
de período)** com **E (assistente com etapas)** nas três ações. Não é tabela de
consulta e não é formulário de documento.

**O momento da verdade desta tela, que eu escrevo aqui porque o §3 exige antes
de desenhar:**

> **"O que eu estou prestes a congelar está conferido, e eu sei o que deixo de
> poder fazer depois."**

Consequência de desenho, não decoração: **antes** de fechar, a tela mostra o que
está sendo fechado (empresa, competência, se a conferência passa) e **o que
deixa de ser possível**. Antes de **entregar**, mostra o aviso mais forte da
tela — entrega é a única ação desta fatia **sem volta pelo produto** (RC-101:
competência entregue não reabre).

## Escopo

1. **Painel de competências da empresa**: lista os meses com estado, quem
   fechou, quando, e se foi entregue.
2. **Fechar** — com a conferência (RC-58) mostrada **antes** do botão, não como
   erro depois.
3. **Reabrir** — campo de motivo obrigatório, com o aviso de que fica na trilha.
4. **Marcar como entregue** — com confirmação explícita de que não reabre mais.
5. **Os cinco estados** antes do caminho feliz: vazio, carregando, erro,
   sucesso, **sem permissão**.

**Fora do escopo, e não deve aparecer no diff:** filtro de competência nas saídas
da DL-015, política de período de trabalho, origem do lançamento (BL-72),
qualquer mudança em regra de serviço.

## Critérios de aceite

1. **Sem permissão é ESTADO, não erro.** O analista **vê** o painel e **não vê**
   os botões — e, se forçar a requisição, o servidor recusa com 403 (RC-102, já
   garantido). A tela explica **por que** não pode, em vez de sumir com a opção
   em silêncio.
2. **A conferência (RC-58) aparece ANTES de fechar.** Havendo lote
   desbalanceado, o botão de fechar não é o caminho: a tela aponta para a
   Conferência da DL-015, nomeando o que falta.
3. **Reabrir exige motivo** na tela, e a tela diz que o motivo **fica
   registrado**. Motivo vazio não chega ao servidor — e, se chegar, é recusado.
4. **Entregar avisa que não tem volta**, com o texto do RC-101: depois da
   entrega, o ajuste vai no mês aberto.
5. **Toda recusa do servidor vira mensagem em português na tela** — nunca 500,
   nunca página em branco. É a lição do **BL-457**, e o teste leva **controle
   positivo** no mesmo caso.
6. **Mês entregue não oferece reabertura** (**BL-468**): a mensagem nomeia o
   caminho certo, que é o ajuste no mês aberto.
7. **Densidade e legibilidade**, pela direção de arte: algarismo tabulado
   (`111111` e `888888` com a **mesma largura**, medido), contraste 4,5:1 em
   texto e 3:1 em borda e foco, **cor nunca sozinha**, e **nenhuma dependência
   externa** (DE-011).
8. **Sem regressão**: suíte, `ruff check`, `ruff format --check`,
   `manage.py check` e `makemigrations --check` limpos, com os números
   declarados e conferidos por `pytest --collect-only -q` (**BL-466**).

## As ressalvas da fatia 1 entram nesta janela

Frente paralela, arquivos disjuntos: **BL-463** (rodar a conferência RC-58
**antes** de adquirir o lock, e definir `lock_timeout`), **BL-464** (aviso ao
degradar fora do PostgreSQL), **BL-465** (comentário que cita migração
inexistente), **BL-466** (número de relatório conferido), **BL-467** (renomear o
teste que não mata o mutante, declarando o que ele **não** detecta) e
**BL-468** (a mensagem quando a competência já foi entregue).

## Divisão de arquivos — disjunta, e é o que permite as duas frentes juntas

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Tela | `especialista-frontend` | `templates/contabilidade/**`, `static/css/**`, `apps/contabilidade/views_web.py`, `apps/contabilidade/urls_web.py`, testes de tela |
| Ressalvas da fatia 1 | `desenvolvedor-pleno` | `apps/contabilidade/services.py`, `apps/contabilidade/models.py`, `config/settings.py`, `apps/contabilidade/tests/test_dl016_fatia1_*.py` |
| Documentação | `arquiteto-senior` | `docs/**` |

⚠️ **`views_web.py` é do frontend nesta etapa; `services.py` é do
desenvolvedor.** Ninguém cruza.

## Verificação — proporcional ao nível 2

**Não há auditoria completa de etapa.** A verificação é dirigida aos oito
critérios, por `auxiliar-verificacao`, sobre a **versão integrada**. A regra de
parada da §3.1 continua valendo: uma verificação, uma correção, uma
reconferência.

⚠️ **O que continua exigindo medida, e não inspeção:** o critério 7 (tabulação e
contraste **calculados**, não julgados a olho) e o critério 5 (**com controle
positivo**, senão o código certo passa pelo motivo errado).

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
