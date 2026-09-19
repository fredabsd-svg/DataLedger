# DL-028 — O juiz aponta para o produto

**Demanda:** decisão do Fred em 2026-09-19, respondendo à pergunta de
instrumento que a oitava auditoria da DL-026 colocou
([relatório integral](../auditorias/2026-09-19-dl-026-rodada-8.md), §7).

**Responsável pelo produto:** Fred.
**Arquiteto:** `arquiteto-senior`.
**Antecede:** a [DL-027](DL-027-documento-emitido-e-personalizacao.md), que cria
tela imprimível em todos os módulos e por isso não pode nascer sobre o
instrumento errado.

## Objetivo

Trocar o instrumento que responde à pergunta *"o documento que o escritório
entrega ao cliente sai identificado?"*. Hoje quem responde é uma imitação do
navegador escrita à mão em Python. Passa a responder **o navegador**, e a
resposta entra na integração contínua **delimitada por caminho**: roda quando
muda o que pode quebrá-la, não em toda alteração.

Este plano **não** apaga o motor simulado. Ele o rebaixa de *única linha* para
*primeira linha barata*.

## Por que agora, e qual é o problema real

A DL-026 teve **oito auditorias e onze rodadas**. As onze percorreram um eixo
só — *o que o motor consegue ler* — e o achado encolhia a cada passo, o que
todos nós, eu inclusive, lemos como convergência. Na oitava auditoria o auditor
olhou o **eixo ao lado** e o achado voltou ao tamanho de bloqueador:
`_PROPRIEDADES_DE_INTERESSE = ("display",)`, uma lista de **um item**, a quinze
linhas de um motor reescrito **três vezes**.

Resultado medido em Chromium e em PDF A4 do produto: **dez construções banais
apagam a identificação do escritório da folha que o contador entrega ao
cliente, com a suíte inteira verde.**

Três fatos decidem este plano, e nenhum deles é estético:

1. **`test_bl329_marca_fora_do_papel.py` tem mais de 1800 linhas** para
   responder a uma pergunta que o navegador responde com uma chamada. E a
   linguagem que ele simula **cresce todo ano** — `content-visibility` é de
   2020, e o próximo é de amanhã.
2. **Todo bloqueador desta etapa foi encontrado abrindo um Chromium e olhando
   o PDF.** Se é assim que se acha, é assim que se deve guardar.
3. **Tamanho de achado mede onde se procurou, não quanto sobrou** — a frase é
   do auditor, corrigindo a si mesmo e a mim.

## A decisão do Fred, e as duas que ela descartou

Levei três caminhos, com o custo de cada um. O Fred escolheu **A**.

| | Caminho | Custo declarado | Escolha |
| --- | --- | --- | --- |
| **A** | Navegador de verdade na integração contínua | Cria dependência que o projeto decidiu, de propósito, não ter | **ESCOLHIDO**, delimitado por caminho |
| B | Conferência de bancada obrigatória, com evidência registrada | É **disciplina** — o que o projeto decidiu não usar como garantia | descartado |
| C | Continuar polindo a imitação | Nunca fica completa | descartado |

**A delimitação por caminho é minha, não do Fred**, e é ela que torna o custo
aceitável: o trabalho novo roda quando muda `static/css/**`, `templates/**` ou
as guardas de impressão. Alteração só de documentação não paga navegador
nenhum. Isso mantém a garantia sendo **mecanismo** — não promessa de alguém
lembrar — que é o princípio do projeto desde a instrução permanente do Fred de
2026-09-13.

Registrada como [DE-057](../projeto/decisoes.md).

## O que já está escrito e pago

Metade do trabalho existe. O plano é **apontar** o que existe, não escrever de
novo:

- **`visivelDeVerdade`** (`docs/assets/design/gauntlet/juiz.py`) já é a
  derivação certa: `Element.checkVisibility({checkOpacity, checkVisibilityCSS})`
  **mais** área do retângulo **mais** alcançabilidade, com os limites medidos e
  **declarados**. São três medições **gerais** — ela cobre **nove** das dez
  construções do BL-362 **sem saber que elas existem**.

  ⚠️ **Correção minha, medida pelo `desenvolvedor-pleno` ao executar a fatia
  1:** a frase original deste plano dizia "as dez", e estava **errada**. A
  décima é `color: transparent`, e ela escapa por **dois** caminhos ao mesmo
  tempo: `checkVisibility` não muda com a tinta, e o `pdftotext` lê o **objeto**
  de texto, não o pixel — o glifo continua no PDF, só pintado invisível. Ele
  mediu (`"veredito": "PASSOU"` com a tinta zerada), fechou o buraco **fora** da
  `visivelDeVerdade` — acrescentando a cor efetiva à sonda e uma checagem de
  alfa zero — e **não** contaminou a função geral que o gauntlet também usa.
  É o limite declarado dela sendo tratado como limite em vez de herdado em
  silêncio: a [DE-056](../projeto/decisoes.md) aplicada sem que ninguém pedisse.
- **`SONDA_IMPRESSAO`** e **`SONDA_IMPRESSAO_TIMBRE`** já fazem a pergunta sob
  `emulate_media("print")`.
- **`scripts/medir_impressao.py`** já sobe o produto real com banco semeado e
  gera PDF A4.

⚠️ **O que falta é o apontamento:** `juiz.py` faz `glob("*.html")` sobre as
pastas das variantes do gauntlet. Ele mede **protótipos**, não
`static/css/base.css` + `templates/**`. A arquitetura declarada da etapa — *"a
CI cobre a metade que dá para provar sem navegador; o juiz de bancada cobre a
que só um motor de layout decide"* — tem a segunda metade apontada para o lugar
errado. Por isso, hoje, para a pergunta do critério 9, **a guarda do `pytest`
não é a primeira de duas camadas: é a única.**

## Fatias, e a ordem tem motivo

**Fatia 1 — o juiz enxerga o produto.** Extrair `visivelDeVerdade` e as sondas
para um módulo reutilizável; criar o ponto de entrada que sobe o produto real
(reaproveitando `scripts/medir_impressao.py`), navega às telas com timbre e
responde, **por medição do navegador**, se cada emitente exigido está
efetivamente visível no papel. Sem CI ainda: a fatia entrega o instrumento e a
prova de que ele pega as dez construções do BL-362.

**Fatia 2 — o instrumento entra no ciclo.** Job de integração contínua
delimitado por `paths:`, instalando Chromium por `playwright install
--with-deps chromium` (nunca caminho fixo — o `/opt/pw-browsers/...` desta
máquina é acidente do ambiente, não configuração do projeto). Reprova o PR
quando um documento sair sem emitente.

**Fatia 3 — o motor simulado é rebaixado, por escrito.** A docstring do
`test_bl329` deixa de se apresentar como a garantia e passa a se apresentar
como a **primeira linha barata**, apontando para quem dá a palavra final. As
recusas continuam; o que muda é a expectativa declarada.

⚠️ **A fatia 1 é independente da rodada 12 da DL-026** (BL-362 e BL-363, o
conserto barato do motor simulado), e as duas correm em paralelo **em arquivos
disjuntos**. A rodada 12 não espera este plano: enquanto o instrumento novo não
existe, a guarda atual não pode continuar simplesmente errada.

## Critérios de aceite

1. **As dez construções do BL-362 são pegas pelo instrumento novo**, medidas
   em Chromium com `emulate_media("print")`, e a prova está em PDF A4 lido com
   `pdftotext` — não só na afirmação do próprio instrumento.
2. **O controle sem sabotagem passa.** Falso alarme na integração contínua é,
   pelo argumento do BL-321, mais corrosivo que falso negativo.
3. **As três telas com timbre** (Balancete, Diário, Razão) são cobertas, e o
   conjunto é **derivado** de quem tem `.timbre-impressao`, nunca de nomes de
   arquivo escritos à mão — é o BL-363 resolvido no instrumento novo também.
4. **Nenhum caminho fixo de navegador** em arquivo versionado.
5. **O job não roda** em alteração que não toque `static/css/**`,
   `templates/**` nem as guardas de impressão — conferido por execução, não por
   leitura do `yaml`.
6. **O tempo do job está medido e declarado.** Se passar de um teto que o Fred
   aceite, a delimitação se aperta em vez de o job ser desligado.
7. **A DE-055 e a DE-056 valem aqui também:** a verificação inclui construção
   escolhida por quem não escreveu a correção, e pelo menos uma mirando eixo que
   este plano não discutiu.

## Riscos declarados

- **O job pode ficar instável** (navegador em integração contínua falha por
  motivo que não é o código). Mitigação: o job reprova só a propriedade que ele
  mede; falha de infraestrutura precisa ser **distinguível** da falha de
  conteúdo, com mensagem própria.
- **Custo de tempo por execução.** Mitigado pela delimitação por caminho, e
  medido no critério 6.
- **O motor simulado continua existindo**, e continua podendo errar. A mudança
  é que ele deixa de ser a única resposta. Quem ler a docstring precisa saber
  disso — é a fatia 3.
- **Este plano não fecha a DL-026 sozinho.** BL-362 e BL-363 são da rodada 12;
  BL-354, BL-355, BL-356, BL-364 e BL-365 seguem como ressalvas declaradas, com
  dono e momento no backlog.

## Divisão de arquivos

Dois agentes nunca editam o mesmo arquivo. Enquanto a rodada 12 da DL-026
estiver em curso:

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| DL-028 fatia 1 e 2 | `desenvolvedor-pleno` | `docs/assets/design/gauntlet/juiz.py`, `scripts/**`, `.github/workflows/**`, `requirements/**` |
| DL-026 rodada 12 | `especialista-frontend` | `apps/contabilidade/tests/**` |

**Proibido a ambos:** `static/css/base.css` e `templates/**` — nenhuma das duas
frentes muda produto. Sabotagem só em cópia (BL-311).

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`, a partir de `7c5b1d4` na
`main`. Um PR por fatia entregue e verificada, nunca por instantâneo de
preservação.
