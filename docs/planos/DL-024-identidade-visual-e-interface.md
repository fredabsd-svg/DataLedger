# DL-024 — Identidade visual e redesenho da interface

**Estado:** **em desenvolvimento.** Aberta em 2026-09-18, a partir da `main`.
Situação atual em [docs/agents/estado.md](../agents/estado.md).

> ⚠️ **Esta etapa não estava na fila aprovada, e isso fica registrado.** O
> **RC-88** fixou a ordem do plano mestre, cujo pacote 3 seria a trilha íntegra
> (BL-14/16/57). Em 2026-09-18 o **Fred redirecionou**: *"vamos trabalhar na
> interface do app"*. É prerrogativa dele — mas a fila não some por isso; ela
> continua valendo para o que vier depois, e o pacote 3 volta a ser o próximo
> quando esta etapa fechar. Registrar o desvio é o que impede a fila de virar
> ficção.

## Objetivo

Dar ao DataLedger uma **identidade visual própria** e uma interface que o
analista contábil aguente olhar oito horas por dia — sem copiar nenhum
concorrente e sem perder nada do que já foi auditado.

O pedido do Fred, literal: *"não faça igual, quero algo único, lindo e
profissional"*.

## Por que agora, e qual é o problema real

O estado atual (capturas em [`docs/assets/telas/`](../assets/telas/)) é
**funcional e acessível, e não tem identidade nenhuma**. Diagnóstico medido nas
próprias capturas:

- Azul de link padrão, `Segoe UI`, tudo numa coluna à esquerda. Parece o admin
  do Django, não um produto.
- **Desperdício vertical**: no balancete, o filtro de período ocupa mais altura
  que o dado; campo de data com ~580px para caber 10 caracteres.
- **Número tratado como texto**: sem tabulação de algarismos, sem hierarquia
  entre saldo anterior e saldo final.
- **Hierarquia do plano de contas invisível**: nível 1, 2 e 3 com o mesmo peso
  visual; só uma coluna "Nível" com um número avisa.

O que está **certo e não se perde**: contraste medido, foco visível, `D`/`C`
explícito, totalizador, mensagens de erro com texto de verdade. Isso custou
auditoria na DL-009 e na DL-017.

## O método: gauntlet

Não é "gerar três telas e escolher a mais bonita". O gauntlet é:

| Rodada | O que acontece |
| --- | --- |
| **0 — Brief e régua** | Persona, jornada, restrições eliminatórias e pontuação com pesos, escritos **antes** de qualquer pixel |
| **1 — Variantes cegas** | Três direções **deliberadamente diferentes**, produzidas em paralelo e **sem contato entre si**, cada uma com as mesmas três telas |
| **2 — Juiz mecânico** | Um programa mede o que é objetivo: contraste calculado par a par, tabulação de algarismos, rolagem horizontal, dependência externa, linhas visíveis por tela, foco que muda de estilo de verdade |
| **3 — Julgamento e eliminação** | O que sobrevive ao mecânico é julgado na régua com peso; quem fica abaixo do corte sai |
| **4 — Enxerto e campeã** | A campeã absorve o que as eliminadas tiverem de melhor, nomeadamente |
| **5 — Implementação** | Vira `templates/` e `static/css/` de verdade, com auditoria independente |

**Por que variantes cegas:** se elas conversarem, convergem para a média — e
média é exatamente o que o Fred não pediu. A divergência é o produto da rodada 1.

**Por que juiz mecânico antes do gosto:** este projeto já reprovou etapa por
declarar o que não mediu. Contraste se calcula, não se olha.

### As três direções da rodada 1

| Variante | Tese | Risco declarado da direção |
| --- | --- | --- |
| **A — Papel e tinta** | Contabilidade é a disciplina do registro; a autoridade vem do impresso bem diagramado. Tipografia como estrutura, cor quase ausente | Virar bonito e pouco denso |
| **B — Instrumento de precisão** | Ferramenta profissional de alta frequência: densidade, previsibilidade e teclado. A beleza vem do rigor | Virar frio e hostil para quem não é técnico |
| **C — Confiança de banco** | O sistema guarda patrimônio de terceiros e às vezes é mostrado ao cliente: calma, ordem, solidez | Virar painel corporativo genérico de caixinhas |

## O que a pesquisa trouxe, e o que ela não prova

Duas frentes de pesquisa (mercado brasileiro e padrões de interface densa).
**Nenhuma das duas viu captura de tela real dos concorrentes** — é relato,
documentação e fórum. Está declarado assim de propósito.

**Achados que viraram regra do brief:**

1. **Parênteses para negativo** é convenção contábil mais antiga que a cor
   vermelha e mais resistente a adulteração: um traço transforma `-` em `+`,
   um parêntese não se desfaz.
2. **Vermelho/verde como único canal é armadilha medida** — deuteranopia atinge
   ~8% dos homens, com caso documentado de produto real corrigindo por isso.
3. **Anti-padrão do concorrente internacional**, reclamado pelos próprios
   usuários: cinco barras de menu deixando **10 linhas** de demonstração
   visíveis. É a régua de densidade ao contrário.
4. **Vício nacional a não herdar:** relatório que sai com a marca **do
   fornecedor** em vez da do escritório contábil; e concorrente que travou o
   cliente em 4 níveis de plano de contas quando a norma pedia 3 — **o layout
   não fixa número de níveis**.
5. **Fontes permitidas** (SIL OFL, auto-hospedadas, sem CDN): Inter, IBM Plex,
   Public Sans, Source Sans 3, JetBrains Mono. **Geist proibida** — licença não
   confirmada na pesquisa.
6. **CSS**: `light-dark()` verificado em fonte primária (~90%). `:has()`,
   `@layer`, container queries e `subgrid` **não** foram confirmados por fonte
   primária — proibidos em caminho crítico até alguém medir.

## Restrições que eliminam

| # | Restrição | Origem |
| --- | --- | --- |
| R1 | Django renderizado no servidor, sem SPA | HI-04, RC-34 |
| R2 | CSS próprio, **nenhuma biblioteca visual externa** | **DE-011** |
| R3 | Sem etapa de build | Realidade do projeto |
| R4 | Fonte auto-hospedada ou pilha do sistema; nada de CDN em runtime | DE-011, LGPD |
| R5 | WCAG 2.2 AA, com contraste **calculado** | DL-009 auditado |
| R6 | JavaScript é enfeite; nenhum dado depende dele | Acessibilidade |
| R7 | pt-BR, `1.234,56`, `dd/mm/aaaa` | Projeto |
| R8 | 1280px sem rolagem horizontal | Contexto de uso |

## Critérios de aceite

1. As três telas (moldura, balancete, lançamento) existem como template Django
   e passam pelo juiz mecânico **sem nenhum critério eliminatório**.
2. **Contraste calculado** de todo par texto/fundo, registrado; nenhum abaixo
   de 4.5:1 (ou 3:1 quando texto grande, pela regra da WCAG).
3. **Densidade medida**: o balancete mostra, em 1280×800 **sem rolar**, pelo
   menos **o dobro** de linhas do estado atual — e o número medido vai no
   relatório, nos dois casos.
4. Totalizador **alcançável sem rolar a tabela inteira**.
5. "Fecha ou não fecha" é respondido no lançamento **antes de gravar**, sem
   depender de JavaScript para a informação existir.
6. Estados desenhados: vazio, carregando, erro, sucesso e **sem permissão**.
7. Navegação completa por teclado, com foco visível medido (o estilo muda de
   fato ao focar, não só existe regra no CSS).
8. Tokens: nenhuma cor ou medida solta fora das variáveis CSS.
9. Impressão: o balancete sai legível em A4, com a identidade do **escritório**.
10. Nada do que a DL-009 e a DL-017 conquistaram regride — a suíte existente
    continua verde, e os testes de interface continuam medindo o que mediam.
11. Auditoria independente da versão integrada, como qualquer etapa.
12. **A direção de arte existe como contrato do projeto, não como memória desta
    etapa** — [`docs/projeto/direcao-de-arte.md`](../projeto/direcao-de-arte.md),
    com os cinco arquétipos de tela, o "momento da verdade" de cada módulo e o
    checklist de módulo novo. O produto vai ter Fiscal, Folha, Honorários,
    Paralegal e Lalur: **um sistema que muda de cara a cada módulo obriga o
    usuário a reaprender a ler**.
13. **A varredura de interface reprova a integração contínua** quando um
    template usa cor, tamanho ou espaçamento fora dos tokens; quando célula de
    valor não tabula; quando tabela não tem `caption` nem `th[scope]`; quando
    tela não estende a moldura comum; ou quando módulo novo aparece sem a sua
    linha na tabela do "momento da verdade". **Enquanto essa varredura não
    existir, a direção de arte é instrução, não garantia** — e é assim que ela
    está escrita, de propósito.

## Fora do escopo

- Módulos que não existem (Fiscal, Folha, Honorários, Paralegal).
- Mudança de arquitetura de front-end.
- A matriz de permissões por papel (**PE-36**, do Fred).
- As ressalvas abertas da DL-023 — seguem com destino próprio.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `especialista-frontend` | `templates/**`, `static/**`, testes de interface |
| `arquiteto-senior` | `docs/**`, brief, régua, juiz mecânico, integração |
| `auditor-qa` | Nada — audita a versão integrada |

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`.
- **Branch de destino:** `main`, por PR.
