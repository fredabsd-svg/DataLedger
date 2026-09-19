---
name: direcao-de-arte
description: Direção de arte do DataLedger — carregue ANTES de criar ou alterar qualquer tela, template, folha de estilo ou componente visual, em qualquer módulo (Contábil, Fiscal, Folha, Honorários, Processos/Paralegal, Lalur/ECF, portal). Use também ao revisar interface, ao escolher cor, tipografia, espaçamento ou densidade, e ao desenhar estados de vazio, carregando, erro, sucesso e sem permissão. Contém os cinco arquétipos de tela, as regras que não se negociam e o checklist de módulo novo.
---

# Direção de arte do DataLedger

**A fonte única é [`docs/projeto/direcao-de-arte.md`](../../../docs/projeto/direcao-de-arte.md).**
Leia-o inteiro antes de desenhar. Esta skill existe para te levar até lá e para
lembrar do que mais se esquece — ela **não** repete o conteúdo, porque texto
duplicado diverge, e essa foi a lição mais cara deste projeto.

Os valores (cor, tipografia, espaçamento) moram em
[`static/css/base.css`](../../../static/css/base.css), no `:root`. Não os
copie para lugar nenhum.

## Por que isto existe

O DataLedger vai ter Fiscal, Folha, Honorários, Paralegal e Lalur. **Um sistema
contábil que muda de cara a cada módulo obriga o usuário a reaprender a ler** —
e quem passa oito horas por dia aqui não pode gastar atenção procurando onde
está o total desta vez.

A direção foi escolhida por **medição**, não por gosto, num gauntlet de três
variantes cegas: [DE-053](../../../docs/projeto/decisoes.md), confirmada em
RC-89, com a evidência em
[`docs/assets/design/gauntlet/MEDICOES.md`](../../../docs/assets/design/gauntlet/MEDICOES.md).

## O que você mais vai esquecer

1. **Todo algarismo de valor é tabulado.** E tabulação não se declara, se mede:
   `111111` e `888888` têm de ter a **mesma largura**.
2. **Contraste se calcula.** 4,5:1 em texto, 3:1 em borda e em foco. "Parece
   legível" não é medição.
3. **Cor nunca sozinha.** `D`/`C`, erro e estado são **texto** antes de serem
   cor.
4. **Valor invertido vai entre parênteses**, não em vermelho: convenção mais
   antiga que a tinta e mais difícil de adulterar.
5. **O filtro não come a tela.** Tabela de módulo novo mostra **pelo menos 15
   linhas** em 1280×800 sem rolar — número medido, não estimado.
6. **Nenhuma dependência externa**: sem CDN, sem biblioteca visual, sem fonte
   remota (DE-011).
7. **Os cinco estados antes do caminho feliz**: vazio, carregando, erro,
   sucesso, sem permissão.

## Antes de abrir a primeira tela de um módulo novo

Responda, por escrito, a pergunta do §3 do documento: **qual é o "momento da
verdade" deste módulo** — a pergunta que a tela tem de responder antes de
gravar. No Contábil é "débito é igual a crédito?". No Fiscal, na Folha, em
Honorários, no Paralegal e no Lalur é outra, e ela está na tabela.

Se você não souber responder, **o problema não é de design** — é de
entendimento do domínio, e a hora de descobrir isso é agora, não depois da tela
pronta.

## Portabilidade

Esta skill é específica do Claude Code. O **conteúdo normativo não mora aqui**:
mora em `docs/projeto/direcao-de-arte.md`, que qualquer ferramenta lê — é o
mesmo princípio do RC-81, que proíbe o projeto de depender de uma única
ferramenta de IA.
