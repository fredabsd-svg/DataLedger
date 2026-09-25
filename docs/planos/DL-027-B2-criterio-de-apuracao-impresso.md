# DL-027 — Fatia B.2: critério de apuração impresso no documento (com A4)

**Estado:** **em correção única após auditoria independente reprovada** em
2026-09-24. B.2 e B.3 foram integradas no PR #41 (`03984ab`); o relatório
integral da rodada 1 está em
[`2026-09-24-dl-027-b2-b3-rodada-1.md`](../auditorias/2026-09-24-dl-027-b2-b3-rodada-1.md).
Esta correção trata os dois achados antes de uma reconferência independente.

> **Autorização.** Fred ordenou, na conversa de 2026-09-22: *"Abrir B.2
> (critério impresso + A4)"*. Esta é a segunda sub-etapa da **Fatia B**
> do plano da DL-027, e inclui o achado A4 da auditoria da B.1
> (mensagem de orientação do veto não assertada por teste, com M5 da
> prova de mutação sobrevivendo).

## Objetivo

1. Permitir que o usuário do Balancete escolha o **critério de apuração**
   entre "Todas as contas" e "Movimento no período ou saldo anterior
   diferente de zero".
2. **Imprimir o critério escolhido no documento**, de modo que dois
   Balancetes com critérios diferentes sejam **distinguíveis pelo papel**
   sem consultar o sistema (critério 6 do plano DL-027).
3. **Fechar o achado A4 da auditoria da B.1:** o texto da
   `messages.error(...)` do veto (quando débitos ≠ créditos) passa a
   ser **assertado por teste**, matando o mutante M5 que sobreviveu na
   prova de mutação de 2026-09-22.

## Escopo

- **Sim**:
  - Filtro `criterio_de_apuracao` no formulário do Balancete.
  - Filtro aplicado em `apurar_balancete` (função pura, em
    `apps.contabilidade.services`).
  - Texto do critério visível na página do Balancete, próximo à faixa
    de veredito (`Fecha`/`Não fecha`/`Nada a conferir`).
  - Novo teste para `avaliar_emissao_do_balancete` cobrindo a
    `messages.error(...)` da view, com asserts de presença da diferença
    em pt-BR e de uma orientação textual.
- **Não**:
  - Migração de modelo — sem campo novo em `Empresa`. O critério é da
    **emissão**, não do cadastro. Decisão adiada até existir pressão
    concreta (PE-65 aberta).
  - Diário, Razão, Balanço. O reuso do critério nesses documentos
    entra quando eles ganharem a mesma personalização (achado A1 da
    auditoria — unificar o contrato dos avaliadores).
  - Critérios além dos dois do escopo desta fatia (ex.: "ocultar só
    saldo zero final", "ocultar sintéticas sem movimento"). Lista do
    plano que ainda não entrou.

## Critérios de aceite

1. O formulário do Balancete oferece seleção de **critério de apuração**
   com duas opções visíveis:
   - "Todas as contas" (padrão — comportamento idêntico ao atual).
   - "Movimento no período ou saldo anterior diferente de zero" (novo).
2. A seleção padrão é "Todas as contas". URL sem o parâmetro
   `criterio_de_apuracao` produz o mesmo Balancete que o código atual.
3. Quando `criterio_de_apuracao=com_movimento`, o serviço devolve linhas
   com **movimento consolidado no período** (débitos > 0 OU créditos > 0)
   ou **saldo líquido de abertura diferente de zero**, calculado conforme
   a natureza da conta. Débitos e créditos históricos compensatórios não
   contam como saldo de abertura. Sintéticas continuam visíveis quando
   movimento ou saldo relevante vem de algum filho.
4. O critério escolhido aparece **explicitamente no papel**, próximo à
   faixa de veredito. Texto:
   - "Critério de apuração: **todas as contas**" (padrão)
   - "Critério de apuração: **movimento no período ou saldo anterior
     diferente de zero**" (alternativo)
5. Dois Balancetes, mesmo período, mesma empresa, critérios
   diferentes: as páginas têm **texto de critério distinto** (verificável
   por leitura do HTML renderizado).
6. O critério também é aplicado no modo impressão — texto aparece
   também na impressão (verificável por HTML/CSS de impressão).
7. **A4 (entra junto):** o teste `test_avaliador_quando_totais_divergem_*`
   (ou um novo teste dedicado, em
   `test_dl027_fatia_b1_bloqueia_emissao_balancete.py` ou
   `test_dl027_fatia_b2_criterio_impresso.py`) **asserta**:
   - que `messages.error(...)` foi chamado,
   - que a string da mensagem contém a **diferença em pt-BR** (`0,01`),
   - que a string contém uma **orientação textual** (palavra
     "Verifique", "Reabra" ou "lançamento").
8. **A prova de mutação mata M5** (mensagem some): o novo teste deve
   reprovar quando a `messages.error(...)` é removida, ou quando a
   string perde a diferença ou a orientação.
9. Quando o avaliador veta a emissão, HTTP 409 renderiza uma página de
   erro sem linhas contábeis, tabela, totais, timbre ou carimbo de emissão.
   O erro e sua orientação continuam visíveis, com caminho para voltar ao
   Balancete.
10. Suíte direcionada verde, `ruff check` limpo, `manage.py check` 0
   issues.
11. Suíte completa verde ou com regressões pré-existentes
    **declaradas** (nãointroduzidas por esta entrega).

## Cenários de teste

| Cenário | Esperado |
| --- | --- |
| URL sem `criterio` | Comportamento idêntico ao atual (todas as contas) |
| URL `?criterio=todas` | Idem |
| URL `?criterio=com_movimento`, sem movimento nem saldo anterior não zero | Tabela zerada, faixa "Nada a conferir" |
| URL `?criterio=com_movimento`, movimento em 2 das 5 contas | Mostra as 2 contas e suas sintéticas; outras contas sem saldo anterior não zero somem |
| Sem movimento no período, lançamentos anteriores compensatórios | Contas com saldo líquido de abertura zero somem |
| Sem movimento no período, saldo líquido de abertura diferente de zero | Conta permanece visível |
| URL `?criterio=invalido` | 400 com mensagem orientativa, sem gravar nada |
| Totais divergem e emissão é vetada | 409 sem tabela, linhas, totais ou carimbo; mensagem orientativa visível |
| Mutante M5 (mensagem do veto some) | Teste dedicado reprova |
| Mutante M5b (diferença some da mensagem) | Teste dedicado reprova |
| Mutante M5c (orientação some da mensagem) | Teste dedicado reprova |

## Riscos declarados

1. **R1 — URL antiga quebrada.** Adicionar parâmetro pode invalidar
   bookmarks ou links de e-mail. Mitigação: default = "todas" e
   ausência de parâmetro = comportamento idêntico. Verificação: rodar
   a suíte com URLs explícitas sem o parâmetro.
2. **R2 — Filtro esconde conta com saldo anterior relevante.** Se a
   regra olhar apenas o movimento no período, uma conta com saldo de
   abertura líquido diferente de zero e sem movimento no mês some da
   tabela. Isso pode quebrar a conferência de saldo anterior. Mitigação:
   a regra mantém esse saldo; débitos e créditos anteriores compensatórios
   com saldo líquido zero não mantêm a conta. O critério é explícito no
   papel para o contador conferir.
3. **R3 — Migração de modelo adiada.** Sem persistência por empresa,
   cada emissão precisa carregar o critério na URL. Mitigação:
   aceitação consciente — decisão registrada como PE-65, fica para a
   próxima iteração quando existir pressão concreta.

## Forma de verificação da correção

- Suíte direcionada (escopo da fatia) verde.
- Suíte completa verde ou com regressões pré-existentes declaradas.
- Prova de mutação do M5 mata o teste novo. Prova dos M5b e M5c
  também (substituir a string da mensagem por `""` ou por
  `"diferente"` sem a orientação).
- `ruff check` limpo, `manage.py check` 0 issues.

## Estratégia de reversão

`git revert` do commit da feature. Sem migração de modelo, sem
alteração de contrato de API. O serviço ganha um parâmetro opcional;
ausência do parâmetro = comportamento idêntico.

## Branch e destino

- **Branch de trabalho da correção:** `fix/dl-027-b2-b3-audit`, criada
  a partir do `origin/main` que contém o PR #41.
- **Branch de destino:** `main`, por PR.
- **Pré-requisito:** auditoria da Fatia B.1 feita (mesmo sem §3.1
  independente — registrada em
  [2026-09-22-dl-027-fatia-b1-rodada-1.md](../auditorias/2026-09-22-dl-027-fatia-b1-rodada-1.md)).

## Pendência herdada que esta etapa NÃO resolve

- **A1, A2, A3, A5, A6, A7, A8** da auditoria da B.1. Donos
  declarados, sem bloqueio desta entrega.
- **DE-067** (snapshot `REPEATABLE READ` para `apurar_balancete`) — a
  DL-035 paga para o Balanço; para o Balancete fica nomeada, não
  resolvida.
- **PE-65** — o que decide se o critério vira campo de Empresa.

## Achados da auditoria e correção desta rodada

1. **Alta — o veto de B.1 ainda renderizava o Balancete completo.** A
   resposta 409 continha tabela, linhas e carimbo B.3, podendo ser
   impressa apesar da recusa. Correção: retornar página de erro dedicada
   sem contexto de apuração nem elementos imprimíveis do relatório; os
   testes cobrem ausência desses dados e preservação da orientação.
2. **Média — saldos anteriores brutos mantinham contas sem saldo líquido.**
   A regra corrigida mantém contas por movimento consolidado no período
   ou saldo líquido de abertura diferente de zero. O texto do formulário e
   do documento foi alinhado ao contrato; testes cobrem histórico
   compensado e saldo de abertura não zero.

O plano anterior tinha conflito entre o critério de aceite 3 e R2. O texto
acima é o contrato atualizado. A auditoria de rodada 1 não mediu PDF/A4
real; a correção não afirma essa medição. Uma reconferência independente
deve confirmar os dois achados e os testes correspondentes; pela regra do
AGENTS.md, não haverá terceira rodada.

**Prova de mutação A4, em worktree isolada:** M5 (remover
`messages.error(...)`), M5b (remover a diferença em pt-BR) e M5c (remover a
orientação) foram todos mortos pelo teste
`test_a4_view_balancete_quando_veta_mensagem_contem_diferenca_e_orientacao`.
