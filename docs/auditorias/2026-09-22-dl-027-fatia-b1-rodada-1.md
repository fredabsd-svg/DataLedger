# Auditoria DL-027 Fatia B.1 — bloqueia emissão do Balancete quando débito ≠ crédito

- **Data:** 2026-09-22
- **Revisão auditada:** `a328a0c` (merge do PR #40 na `main`)
- **Auditor:** arquiteto-senior, mesma sessão que opera o projeto (sessão opencode).
  Fred autorizou a quebra da §3.1 por ser ele próprio o autor do commit
  (`fred <fredabsd@gmail.com>` no commit `6c46630`, `fredabsd-svg` no PR).
  Sem independência, este parecer vale apenas como **autoinspeção
  registrada com disciplina de auditor** (mutação, leitura isolada, suíte
  em cópia separada), não como aprovação independente. A próxima etapa que
  exigir §3.1 pura precisa voltar a ser rodada por outro agente, em sessão
  Claude Code interativa, com `disallowedTools: Write, Edit, NotebookEdit`
  técnico.

## Resumo

A trava de emissão do Balancete quando débitos e créditos divergem (item 3 da
Fatia B do plano DL-027) está **implementada e coberta por testes** — quatro
dos cinco mutantes testados morrem, o que prova que a edição 200→409 dos
testes pré-existentes não cegou as guardas. A estrutura reutiliza o padrão de
`avaliar_emissao_do_balanco` (DL-034), com divergências localizadas que estão
registradas abaixo como ressalvas.

**Parecer: APROVADO COM RESSALVAS.**

## Medições executadas

| Verificação | Resultado |
| --- | --- |
| Cópia isolada da revisão `a328a0c` (clone em `/tmp/opencode/audit-dl027/dataledger`) | `git status` vazio, `git log -1` = `a328a0c` |
| Suíte direcionada (escopo da fatia) | **318 passed em 67 s** |
| Suíte visual (test_dl024_veredito_no_html_renderizado.py) | **18 passed em 7,78 s** |
| Suíte completa `apps/` (rodada 1) | **2002 passed, 14 skipped, 1 falha preexistente** em 9 min 37 s |
| Suíte completa `apps/` (rodada 2) | **2002 passed, 14 skipped, 1 falha preexistente** em 8 min 15 s |
| Falha preexistente (não relacionada à DL-027) | `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` — o teste foi escrito para Python 3.14 e a linha `ast.parse(codigo, feature_version=(3, 14))` falha em Python 3.12 porque o parser 3.12 não conhece a sintaxe `except A, B:` em nenhuma versão declarada. Medido: **flakiness na suíte completa**, passa isolado às vezes. Preexistente, não bloqueador. |
| Flakiness na suíte completa | `test_dl016_fatia1_fechamento_reabertura_entrega.py::test_bl463_varredura_rc58_nao_bloqueia_lancamento_concorrente` — falhou 1 vez em 2, passa isolado. Concorrência PostgreSQL com timing dependente. **Não é regressão da DL-027.** |
| `ruff check` no escopo | All checks passed |
| `manage.py check` | System check identified no issues (0 silenced) |
| Prova de mutação (4 mutantes principais) | **4 de 5 matam os 3 testes pré-existentes editados** (M1, M2 cirúrgico, M3, M4) |
| Prova de mutação (1 mutante exploratório) | M5 (mensagem some) **não mata** — lacuna confirmada, registrada |

## Prova de mutação (lição da §3.1 do estado.md da DL-031, registrada em 2026-09-20)

Cinco mutantes, em arquivo fonte revertido por `git checkout -- .` antes de
cada rodada e ao final, aplicados em cópia isolada (`/tmp/opencode/audit-dl027/dataledger`,
clone em `a328a0c`):

| # | Defeito reintroduzido | Esperado | Resultado |
| --- | --- | --- | --- |
| **M1** | `avaliar_emissao_do_balancete` devolve `pode_emitir=True` em todos os ramos (anula o veto) | 3 FAILED | **3 FAILED** — primeiro `assert 200 == 409` em `test_bl290_veredito_balancete.py:159` |
| **M2** (cirúrgico, só no balancete) | view substitui `status=409` por `status=200` no caminho do veto do Balancete | 3 FAILED | **3 FAILED** — primeiro `assert 200 == 409` em `test_bl290_veredito_balancete.py:159` |
| **M3** | view ignora o avaliador (`avaliacao = {"pode_emitir": True, ...}` em vez de chamar a função) | 3 FAILED | **3 FAILED** — primeiro `assert 200 == 409` em `test_bl290_veredito_balancete.py:159` |
| **M4** | flag `emissao_recusada=False` no contexto do veto (a tela deixa de marcar o estado vetado) | 3 FAILED | **3 FAILED** — primeiro `assert False is True` em `test_bl290_veredito_balancete.py:162` |
| **M5** (exploratório) | `if False: messages.error(...)` — a frase de orientação do veto some | ? (testes não assertam) | **3 passed** — **LACUNHA CONFIRMADA**: nenhum dos 3 testes pré-existentes valida o TEXTO da mensagem |

**Conclusão da mutação:** a edição 200→409 dos três testes pré-existentes
NÃO cegou as guardas. As 4 mutações de comportamento (veto cancelado, status
errado, avaliador desligado, flag de estado errada) são detectadas. **A 5ª
mutação (texto da mensagem) é a lacuna, e o mutante M5 sobrevive — esse
achado entra como A4 abaixo.**

⚠️ **Observação sobre M2 global:** uma primeira tentativa substituiu TODOS
os `status=409` do arquivo, e quebrou a compilação porque a view do Razão
também usa `status=409` (em outro caminho, para `HierarquiaInconsistente`).
Refeito com regex restringido ao `return render(... "contabilidade/balancete.html", contexto, status=409)`
que vem depois de `avaliacao = avaliar_emissao_do_balancete(apuracao)` — só
o veto do Balancete. **A substituição global não é confiável quando há
múltiplas ocorrências do mesmo literal em funções diferentes**, e isso é uma
lição do próprio instrumento: a busca cirúrgica (ancor + trecho vizinho) é o
caminho seguro.

## Achados

### A1 — Formato divergente entre os dois avaliadores (média)

| Campo | `avaliar_emissao_do_balancete` (DL-027 B.1) | `avaliar_emissao_do_balanco` (DL-034) |
| --- | --- | --- |
| Entrada | `apuracao` (dict) | `saldos` (dict) |
| Saída | `{pode_emitir, veredito, diferenca_ptbr}` | `{pode_emitir, residuo_pendente, listas_pendentes, listas_informativas}` |
| Decide em `Decimal` | sim | sim |
| Função pura | sim | sim |

**Impacto:** a promessa do docstring de B.1 — *"Diário e Razão vão reusar a
mesma estrutura quando entrarem na mesma etapa"* — não é cumprível como
está: o `diferenca_ptbr` é uma string pronta para display, enquanto o
Balanço devolve listas. O Diário/Razão que herdar a estrutura terá que
escolher um lado, e os dois lados são justificáveis.

**Correção recomendada:** quando entrar a próxima fatia que reutilizar o
avaliador (Diário/Razão), **unificar o contrato**. O lado a ser o canônico é
o do Balanço (`{pode_emitir, ...listas}`), porque é mais informativo e
permite à view construir a mensagem sem acoplar formatação no services.

**Forma de verificar:** depois da unificação, rodar a suíte inteira (Diário
+ Razão + Balancete + Balanço) com pelo menos 2 mutantes por avaliador
(reintroduzir `pode_emitir=True` constante, e reintroduzir a omissão de uma
lista de veto).

### A2 — String `diferenca_ptbr` dentro de services (baixa)

`avaliar_emissao_do_balancete` devolve `diferenca_ptbr` já formatado em
pt-BR (`"0,01"`), gerado por uma função local `_formatar_diferenca_ptbr` que
replica a lógica de `_valor_ptbr` em `views_web.py`. O services não tem
mais como devolver um `Decimal` puro sem quebrar o consumidor atual
(view), mas a duplicação da regra de formatação está documentada no
docstring como simetria consciente com `_valor_ptbr`.

**Impacto:** se a regra de arredondamento pt-BR mudar, dois lugares precisam
ser editados. O comentário da função declara isso; o BL-310/A2 da DL-026
validou que comparar `Decimal` (não texto) é o que importa.

**Correção recomendada:** quando A1 for resolvido, devolver `Decimal` puro
e mover a formatação para a view (mesmo lugar que `_valor_ptbr`). Até lá,
manter o comentário.

### A3 — Flag `emissao_recusada` setada mas não usada pelo template (baixa)

A view adiciona `"emissao_recusada": True` ao contexto do veto, e o teste
novo (`test_dl027_fatia_b1_bloqueia_emissao_balancete.py:194`) asserta a
flag. Mas `templates/contabilidade/balancete.html` **não consulta essa
flag** — a faixa exibida é a mesma do ramo `nao_fecha` que aparecia ANTES
do veto. O 409 é a única diferença visível para o cliente HTTP; na tela, a
visualmente exibido é idêntico.

**Impacto:** baixo — a orientação textual está visível via `messages.error`
(renderizada por `templates/base.html` como `Erro: O Balancete NÃO pode ser
emitido: ...`), e o status 409 já diferencia para o programa. A flag é
**código morto em runtime** que sobreviveu ao template.

**Correção recomendada:** remover a flag do contexto (e do teste) ou usá-la
no template (ex.: adicionar uma classe `faixa-fechamento--vetada` que escurece
a faixa quando `emissao_recusada=True`). A segunda opção é a mais útil para
o contador que está olhando a tela e precisa saber "o servidor vetou" vs
"o sistema está mostrando em modo de conferência". Decisão do `especialista-frontend`.

**Forma de verificar:** depois da correção, mutante que retire a flag do
contexto (ou do template) deve matar pelo menos um teste visual.

### A4 — Texto da mensagem de orientação do veto não assertado (média)

M5 sobreviveu: se a `messages.error(...)` da view for removida ou tiver o
texto editado, **nenhum dos 5 testes da fatia cai**. O critério 9 do plano
DL-027 exige "dizer o que fazer, não só que falhou" — uma frase de
orientação que muda sem teste é o tipo de regressão silenciosa que a §3.1
existe para impedir.

**Impacto:** médio — o usuário vê HTTP 409 e a faixa "Não fecha — diferença
de R$ X..." no template, então a orientação visual existe pela via da
faixa. Mas a `messages.error(...)` é o canal que aparece acima de tudo, em
qualquer estado da tela, e a frase dela é a única coisa que nomeia "o que
fazer" em texto corrido.

**Correção recomendada:** um teste que capture a mensagem e assertar:
1. Que `messages.error` foi chamado.
2. Que a string contém a diferença em pt-BR.
3. Que a string contém uma orientação textual (ex.: contém a palavra
   "Verifique" ou "Reabra").

**Forma de verificar:** o teste mata o M5 e o M5b (mensagem com a diferença
removida) e o M5c (orientação removida).

### A5 — Concorrência da apuração sem `REPEATABLE READ` (média, játem dono)

`apurar_balancete` é chamado pela view em `READ COMMITTED`, sem snapshot.
A auditoria da DL-032 (achado A6, [DE-067](../projeto/decisoes.md)) já
mediu que essa leitura pode produzir uma "diferença fantasma" transitória
sob escrita concorrente. O veto de B.1 transforma essa diferença em HTTP
409, e isso é **melhor que nada** (o usuário vê a divergência em vez de um
número mentiroso), mas é **pior** que o `REPEATABLE READ` que a
`apurar_balanco_patrimonial` (DL-034) já paga.

**Impacto:** em uso normal do produto, o veto dispara só em corrupção de
dado, e a janela de corrida do `apurar_balancete` é a mesma — não há
regressão de segurança da DL-032 para cá.

**Correção recomendada:** quando o caminho do Balancete virar documento
imprimível (próxima iteração da Fatia B — pré-visualização, impressão),
adotar o mesmo padrão de `apurar_balanco_patrimonial`:
`SET TRANSACTION ISOLATION LEVEL REPEATABLE READ` como primeira instrução
da transação de leitura do documento.

**Forma de verificar:** mutante que inverta o sinal de um `total_debitos`
entre duas chamadas consecutivas de `apurar_balancete` (sob `READ
COMMITTED`) deve produzir um veto incorreto que o `REPEATABLE READ`
eliminaria.

**Dono declarado:** a DE-067 lista a dívida; a DL-035 (guardas da
demonstração) é o lugar onde a dívida é paga para o Balanço. Para o
Balancete, **fica nomeada, não resolvida** — entra na próxima fatia B que
gerar documento imprimível.

### A6 — Lacuna visual do template (média, depende do `especialista-frontend`)

O template `balancete.html` mostra a mesma faixa "Não fecha — diferença de
R$ X..." no ramo `veredito_balancete == "nao_fecha"`, **independentemente
do veto**. A diferenciação visual entre "está mostrando o resultado" e
"está vetando o documento" não existe no template. O `messages.error(...)`
faz esse trabalho no topo, mas é separado da faixa e pode ser
dispensável em telas renderizadas de outras formas (ex.: impressão via
PDF direto).

**Impacto:** médio. O usuário navegador recebe o 409 e a mensagem. Mas se a
tela for renderizada em outro formato (PDF direto, API), a faixa de
diferença pode aparecer sem a mensagem de veto.

**Correção recomendada:** mesma do A3 — usar a flag `emissao_recusada`
para mudar a classe CSS da faixa no template, tornando visualmente
distinguível "diferença detectada" vs "emissão vetada".

**Forma de verificar:** mutante que retire o `if emissao_recusada` da
condição do template deve matar um teste visual que afirme que a classe
aparece quando o documento está vetado.

### A7 — Reuso prometido no docstring, sem cobertura (baixa)

O docstring de `avaliar_emissao_do_balancete` promete reuso para
Diário/Razão, mas o `avaliar_emissao_do_balanco` (DL-034) já usa um
formato diferente (A1) e nenhum dos dois tem teste de que "outro relatório
que herdar a estrutura funciona". A promessa é arquitetural, não testada.

**Impacto:** baixo — promete reuso futuro, e o reuso ainda não aconteceu.

**Correção recomendada:** quando entrar Diário/Razão na mesma etapa,
transformar a estrutura em um mixin ou dataclass comum, com testes para
as duas direções (Balancete e Diário compartilham o contrato, e cada um
mantém suas especificidades).

### A8 — `avaliar_emissao_do_balancete` expõe `veredito` como string livre (baixa)

`veredito` é uma `Literal["fecha", "nao_fecha", "nada_a_conferir"]` segundo
o docstring, mas o Python não enforce — a função retorna strings literais,
e nada impede um consumidor futuro de comparar `veredito == "Fecha"`
(com capitalização). O `_veredito_balancete` ANTIGO em `views_web.py`
também estava nesse formato, então é consistente com o passado.

**Impacto:** baixo — só há UM consumidor (`views_web.py:balancete`), e ele
compara em lowercase. Se um novo consumidor entrar com capitalização
errada, o `if` cai no ramo errado silenciosamente.

**Correção recomendada:** usar `enum.Enum` (`class VereditoBalancete(str, Enum): FECHA = "fecha"; NAO_FECHA = "nao_fecha"; NADA_A_CONFERIR = "nada_a_conferir"`).
Mesmo formato que `ClasseDocumento` (DL-027 Fatia A) já usa.

## O que NÃO foi achado

- **Autorização quebrada.** `balancete(request, empresa_id)` continua com
  `@login_required`, `@require_safe`, `_empresa_do_escritorio_ativo` e
  `_pode_ler`. A linha que adiciona o avaliador (services.py:2497) está
  depois dessas verificações.
- **Isolamento entre escritórios quebrado.** O avaliador é puro, não toca
  em banco nem em `request`. O filtro que antecede `apurar_balancete`
  continua sendo o portão. Nenhum teste novo precisou de setup de
  escritório porque o fixture existente já o cobre.
- **Duplicação de regra entre tela, API e services.** O avaliador decide
  em `Decimal`, e a view formata em pt-BR para o display — única exceção
  é o `_formatar_diferenca_ptbr` em services, declarado como simetria
  consciente (A2).
- **Cálculo de arredondamento novo.** O avaliador não introduz arredondamento;
  a subtração é em `Decimal` puro (mesma lição do BL-290).
- **Idempotência.** O veto é de leitura, não de escrita. Não há nova
  superfície de corrida além da que a DL-032 já documentou (A5).

## Riscos declarados residuais (não da auditoria, do ambiente)

1. **Sem §3.1 independente.** Este parecer foi feito pelo mesmo agente
   que opera o projeto e pelo autor do commit. Vale como autoinspeção
   com disciplina de auditor; não vale como aprovação independente. A
   próxima etapa NÍVEL 1 precisa de sessão Claude Code interativa.
2. **Flakiness preexistente na suíte completa.** Dois testes podem falhar
   por timing (PostgreSQL concorrência, parser Python 3.12 vs 3.14) sem
   que isso seja regressão da DL-027. Medido: a falha `test_bl463_*`
   falhou 1 de 2 vezes na suíte completa, passou isolada. Preexistente.
3. **`_valor_ptbr` em `views_web.py` e `_formatar_diferenca_ptbr` em
   `services.py`** são duas implementações da mesma formatação. A2
   registra. A unificação fica para a próxima iteração da Fatia B que
   precisar do reuso.

## Forma de verificar a correção dos achados (resumo)

| Achado | Forma de verificar |
| --- | --- |
| A1 | Rodar suíte com 2 mutantes por avaliador depois da unificação |
| A2 | Mesmo de A1 |
| A3 | Mutante que retire a flag mata um teste visual |
| A4 | M5 mata o novo teste; M5b (mensagem sem diferença) mata; M5c (orientação removida) mata |
| A5 | Mutante que inverta sinal entre duas chamadas de `apurar_balancete` |
| A6 | Mutante que retire `if emissao_recusada` da condição do template |
| A7 | Teste de reuso entra com Diário/Razão |
| A8 | `enum.Enum` faz comparações `==` typo-seguras |

## Decisão

**APROVADO COM RESSALVAS.** A trava está implementada, testada e as
guardas principais estão vivas (4 de 5 mutantes principais morrem). Os
ressalvas A1–A8 entram na próxima fatia B ou na DL-035 — nenhuma delas
impede o prosseguimento da Fatia B.2 (critério de apuração impresso),
desde que A4 (mensagem não assertada) seja resolvido **junto** com a
próxima fatia, porque é o tipo de regressão silenciosa que a §3.1 existe
para impedir.

**Não é aprovação independente (§3.1).** Esta auditoria foi feita pelo
mesmo agente que opera o projeto, com autorização explícita do Fred. A
próxima etapa NÍVEL 1 (e qualquer auditoria que se preze) precisa de sessão
Claude Code interativa no terminal, com o `auditor-qa` carregado.
