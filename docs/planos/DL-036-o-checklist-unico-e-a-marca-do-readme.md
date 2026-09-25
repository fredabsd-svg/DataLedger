# DL-036 — O checklist único, e a marca do README que mentiu

**Demanda:** ordem direta do Fred em 2026-09-25, em duas falas — *"pode fazer a
varredura de reconciliação do README"* e *"faça um check-list para colocar no
processo"*. Pela [DL-025](DL-025-ordens-diretas-do-responsavel.md), solicitação
do responsável pelo produto é **demanda formal** e autoriza a execução do escopo
pedido.

## O que aconteceu, e é medido

Ao responder a pergunta dele *"quais módulos já temos prontos?"*, eu medi o
código em vez de ler a documentação — e o checklist de etapas do `README.md`
**afirmava que duas etapas integradas na `main` não tinham sido feitas**: a
**DL-027** (o documento emitido, integrada pelo **PR #42**) e a **DL-030** (a
trilha cobrindo o admin, `8de86a7`). A varredura subsequente achou uma terceira,
maior: a **DL-016** — competência e fechamento — está marcada como não feita e
**o produto já fecha o mês**, nas duas fatias, com auditoria aprovada em cada uma.

⚠️ **A parte incômoda não é a divergência: é COMO ela sobreviveu.** Já existiam
**dois** checklists — `AGENTS.md` §14 e o modelo de pull request — e a divergência
atravessou vários PRs **com os dois marcados como cumpridos**. O item dizia
*"documentação e evidências atualizadas"*. **Item vago é item que se marca sem
fazer.**

É a reincidência literal da instrução permanente de 2026-09-13: *"a causa do
problema não foi distração, foi **duplicação**. Texto repetido em quatro lugares
diverge assim que alguém atualiza um."*

## Escopo

1. **Varredura de reconciliação** de todo o checklist do `README.md` — DL-001 a
   DL-035 mais os cinco módulos —, medida contra **código e histórico do Git**,
   nunca contra a documentação, que é o que divergiu. Duas frentes de leitura,
   somente leitura.
2. **Correção do `README.md`** conforme a medição.
3. **Checklist ÚNICO**, em `AGENTS.md` §14: itens **específicos** em vez de
   genéricos, organizados em cinco fases, e **coluna dizendo quem impõe cada um**
   — `teste`, `workflow`, `gancho` ou `honra`.
4. **O modelo de pull request para de repetir a lista** e passa a apontar para o
   §14, guardando só as caixas que a integração contínua lê.
5. **Caixa NOMEADA para o item que falhou**, exigida pelo workflow
   `Regras do projeto`, para que marcá-la sem conferir seja **afirmação
   específica e falsa** em vez de um genérico que qualquer coisa satisfaz.

**Fora do escopo, e declarado:** o **mecanismo de fundo** — teste que compare a
marca do README com a branch padrão, ou README **gerado** no molde da
[DL-019](DL-019-portabilidade-entre-ferramentas-de-ia.md). Fica registrado como
**BL-526**, com o motivo: exige uma fonte legível por máquina do que está
entregue, e essa decisão de formato merece etapa própria.

## ⚠️ O limite desta etapa, escrito para ela não cometer o defeito que denuncia

**O workflow confere o ATESTADO, não o FATO.** Ninguém compara a marca do README
com a branch padrão; o `test_documentacao_do_estado.py` verifica que a etapa
**apareça** nos dois arquivos, não que o `[x]` corresponda à realidade.

Isto é a [DE-058](../projeto/decisoes.md#de-058) aplicada a mim mesmo: **limite
declarado não é limite medido**, e uma caixa obrigatória não é uma verificação.
Depois desta etapa a divergência continua **possível** — fica mais **difícil de
marcar sem mentir**, e isso é menos do que uma trava.

## Critérios de aceite

1. **Todo item do checklist do README tem veredito medido**, com evidência
   (caminho de arquivo, rota, SHA ou número de PR). Item que não se consiga
   determinar é declarado **como tal**, não arredondado.
2. ⚠️ **Entrega parcial é nomeada como parcial**, com o que entrou e o que não
   entrou. **Não arredondar para cima** é o critério, não o desejo.
3. **O `README.md` reflete a medição**: `[x]` só para o que está na branch
   padrão.
4. **`AGENTS.md` §14 é o único checklist do projeto**, e o modelo de pull request
   **não repete** nenhum item que não seja lido pela CI.
5. **As três caixas que o workflow lê continuam casando**, medido por simulação
   da checagem: modelo preenchido passa nas três; modelo em branco **reprova nas
   três**; corpo de PR escrito com o modelo **antigo** fica **vermelho** na caixa
   nova. YAML do workflow válido.
6. **Sem regressão** na validação de documentação: todo `.md` com título, UTF-8,
   sem espaço no fim de linha, nova linha final e links relativos existentes.

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Medição (somente leitura) | dois `auxiliar-pesquisa` | **nada** — só leem |
| `AGENTS.md`, modelo de PR, workflow, `README.md`, `docs/**` | `arquiteto-senior` | os citados |

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
