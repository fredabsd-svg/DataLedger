# DL-044 — telas de trabalho, antes e depois (3ª iteração)

Capturas para o Fred aprovar a DL-044 antes de espalhar a mudança para o
resto do produto (fase B). Três rodadas de retorno, cada uma incorporada
antes da próxima captura — o "depois" abaixo é sempre o estado MAIS
recente, não uma pilha de versões:

1. **Reprovação original** (fase A): *"o layout da tela de trabalho tá com
   aspecto de vazio e os botões de clicar [...] tá parecendo um botão de
   link, tá muito amador, muito cara de sistema mal feito"* — tipografia,
   sombra de superfície, abas, botões com quatro estados (DE-079).
2. **2ª rodada**: *"ainda tá parecendo um sistema arcaico [...] tudo junto
   no lugar só [...] botões para abrir os relatórios [...] esquisito"* —
   barra lateral ESCURA com item de menu de verdade (sem sublinhado, alvo
   ≥36px), Início com indicadores/ações rápidas/carteira, hierarquia de
   botão (um primário por tela), formulário do lançamento como cartão
   único, coluna numérica alinhada à direita inclusive o cabeçalho, D/C
   como selo.
3. **3ª rodada, esta captura**: Fred nomeou uma referência concreta —
   *"Gosto do visual do Conta Azul [...] não é para fazer igual, apenas um
   modelo"* — azul de aplicativo PRÓPRIO (não o hex do Conta Azul) em vez
   da barra escura da 2ª rodada, fundo cinza-azulado com cartões brancos,
   hub de relatórios em cartões (`contabilidade_web:relatorios`, tela
   NOVA), tiles de módulo no Início, chip/pílula na identificação do
   topo, dica de atalho de teclado ("Alt+C") fora da tela (nunca do
   produto — `accesskey`/`aria-keyshortcuts` continuam intactos). Decisão
   completa: [decisoes.md, DE-080](../../../projeto/decisoes.md). A
   landing pública **continua aprovada** e não muda em nenhuma das três
   rodadas.

Dados 100% sintéticos: `scripts/semear_base_de_medicao.py` (73 contas, 60
lançamentos em 03/2026) mais um pequeno movimento sintético em 02/2026 e um
parâmetro contábil mensal, por um script de apoio local (mesmo espírito de
`apps/fiscal/tests/xml_sinteticos.py`), e alguns documentos fiscais sintéticos
para o Início não ficar artificialmente pobre de categoria. Chromium, locale
`pt-BR` explícito no contexto do navegador (`navigator.language`/
`navigator.languages` conferidos = `pt-BR`), 26/09/2026.

**Antes** continua o estado já integrado ANTES de qualquer rodada desta
etapa (nenhuma captura "antes" foi trocada nas rodadas 2/3 — é o "antes"
de verdade): Início/Balancete/Novo lançamento saem das capturas da DL-042
(`docs/assets/telas/dl042/depois_*`, main tree); Zerar resultado (prévia)
sai da captura da DL-043
(`wt-dl043/docs/assets/telas/dl043/zerar_resultado_previa_*`).

**Relatórios (hub em cartões) é tela NOVA** — não existia antes desta
etapa, então não tem par "antes"; a captura "depois" é a ÚNICA.

## Início (painel)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_1440x900.png) | ![Depois](depois_painel_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_390x844.png) | ![Depois](depois_painel_390x844.png) |

**O que mudou desde a 1ª captura desta tela:** deixou de ser só a fila de
atenção — ganhou faixa de indicadores, ações rápidas, tiles de módulo e a
tabela "Empresas da carteira", nesta ordem, todos filtrados pelo
escritório ATIVO e pela mesma permissão por papel que a fila já usava
(DE-080). O título virou sempre "Início", com o escritório como subtítulo
(antes repetia "Escritório ativo: ..." como título, igual à faixa de
identificação do topo).

**Achado próprio, corrigido antes de capturar (não é regressão visível
nesta captura):** a tabela "Empresas da carteira" tinha vazado razão
social e pendência para um papel CLIENTE, que a fila de atenção já
escondia corretamente — mesma classe de fuga de informação que a fila
existia para impedir, por uma porta que esta iteração tinha aberto. Preso
por `apps/tenancy/tests/test_dl042_fila_de_atencao.py::test_papel_
cliente_nao_ve_a_fila_de_atencao` (teste já existente, não escrito para
isto) antes de qualquer captura ou entrega; corrigido com um `if
papel_pode_ler_contabilidade(papel)` — mesmo teste, mesma suíte completa,
verdes depois. Prova de isolamento e de consulta CONSTANTE (mede
igualdade entre 1 e 10 empresas, não um teto) em teste novo,
`apps/tenancy/tests/test_dl044_painel_carteira_e_indicadores.py`.

**Overflow horizontal em 390px, na tabela "Empresas da carteira":** a
mesma classe de comportamento que o Balancete já tinha ANTES desta etapa
(a captura "antes" do Balancete, abaixo, já mede 950px de largura de
rolagem contra um viewport de 390px — medido nesta rodada, não
introduzido por ela). Não há wrapper `overflow-x` em NENHUMA tabela do
produto hoje — decisão de produto pré-existente (AGENTS.md: nunca esconder
informação contábil em favor da estética), não um defeito desta etapa. A
VISÃO INICIAL do celular (sem rolar) está correta — capturada à parte,
sem o efeito de `full_page=True` somando a largura rolável:
`/tmp/.../scratchpad/mobile_viewport_only.png` (não versionado, é só
evidência de trabalho).

## Novo lançamento

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_1440x900.png) | ![Depois](depois_lancamento_novo_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_390x844.png) | ![Depois](depois_lancamento_novo_390x844.png) |

**O que mudou desde a 1ª captura desta tela:** cabeçalho (Data/Histórico)
e tabela de partidas viraram UM cartão só (antes o cabeçalho tinha moldura
própria, mais estreita que a tabela, sobrando vazio ao lado). "Adicionar
linha" é secundário com ícone "+"; "Gravar lançamento" é o único primário
da tela, os dois alinhados à direita no rodapé do cartão. Cabeçalho da
coluna "Valor" alinhado à direita, como o dado abaixo dele — achado
PRÓPRIO desta rodada: a classe `.cabecalho-numerico` não tinha
especificidade suficiente para vencer `.tabela-dados th` (que já fixa
`text-align: left`), medido por captura ANTES de aceitar como pronta,
corrigido para `.tabela-dados th.cabecalho-numerico`.

**Campo de data em mm/dd/aaaa nas duas versões** (visível no "Depois"
também): limitação JÁ CONHECIDA e já documentada do produto (DE-031) — o
`<input type="date">` usa o formato NATIVO do NAVEGADOR/sistema
operacional, que este ambiente de captura não tem localizado em pt-BR (nem
`locale="pt-BR"` do Playwright nem `--lang=pt-BR` no lançamento do
Chromium mudam o widget nativo — testado na 1ª rodada). O produto já
resolve isso do jeito que pode sem JavaScript: o rótulo não promete um
formato que não controla, e o texto de apoio abaixo do campo diz "toda
data EXIBIDA pelo sistema é dd/mm/aaaa" — o que é verdade em toda a
interface, exceto neste widget nativo específico.

**Overflow horizontal em 390px, na tabela de partidas (coluna "Conta"
visualmente espremida):** mesma classe de comportamento já presente na
1ª captura desta tela (comparar as duas larguras de rolagem medidas —
691px então, 716px agora, mesma ordem de grandeza) — não é regressão
desta rodada.

## Relatórios (hub em cartões) — tela NOVA

Computador (1440 × 900):

![Relatórios, 1440×900](depois_relatorios_1440x900.png)

Celular (390 × 844):

![Relatórios, 390×844](depois_relatorios_390x844.png)

Um cartão por relatório (Diário, Razão, Balancete, Balanço, Conferência) —
ícone, título, descrição de uma linha, "Abrir →". Substitui o "botão que
parece link" que o Fred apontou como esquisito por um segundo caminho, em
cartão, para as MESMAS cinco rotas que o menu "Contabilidade → Relatórios"
já oferece — nenhum link foi removido de lá (DE-080 justifica por quê:
risco de regressão nos testes de navegação/atalho já estabelecidos, por
um ganho que o hub aditivo já entrega sem remover nada).

## Balancete

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balancete_1440x900.png) | ![Depois](depois_balancete_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_balancete_390x844.png) | ![Depois](depois_balancete_390x844.png) |

**Não toquei no `<h1>`/cabeçalho desta tela especificamente** (ao contrário
das outras) — `templates/contabilidade/balancete.html` tem um comentário
extenso (BL-284) registrando que a área ACIMA da primeira linha da tabela
já foi motivo de uma regressão medida de densidade (9 → 6 linhas visíveis,
§4.8 da direção de arte) numa etapa anterior. Acrescentar `.cabecalho-
pagina` ali somaria altura nessa mesma área crítica, e eu não tenho, nesta
etapa, o instrumento de medição (`scripts/juiz.py`, que exige Chromium
fora do pytest) rodado para prová-lo seguro. As mudanças que esta tela
recebeu (fonte, abas, tabela com moldura, botões, cor do sistema, fundo da
página) são todas de impacto ZERO em altura de linha — a tabela em si
permanece IDÊNTICA em densidade nas três rodadas.

## Zerar resultado (prévia)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_zerar_resultado_previa_1440x900.png) | ![Depois](depois_zerar_resultado_previa_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_zerar_resultado_previa_390x844.png) | ![Depois](depois_zerar_resultado_previa_390x844.png) |

**O que mudou desde a 1ª captura desta tela:** cabeçalho "Valor (R$)" das
duas tabelas (etapa 1 e etapa 2) alinhado à direita como o dado abaixo
dele (antes ficava encostado à esquerda, "parecendo desalinhado" —
achado original do Fred nesta MESMA tela); D/C virou selo pequeno (antes,
letra solta); botão "Gerar lançamentos de zeramento" ganhou a classe
`.botao--primario` explícita (antes dependia do estilo padrão do
`<button>` sem classe, que hoje também é azul — mas nomear a classe deixa
a intenção explícita, e é o único botão primário desta tela).

## Regressões pegas ANTES de entregar (não pelo Fred, pelo especialista-frontend)

Registradas por honestidade — nenhuma delas sobrevive nas capturas
"depois" acima, todas corrigidas antes de aceitar a captura como boa:

1. **1ª rodada:** ao dividir a barra lateral em `<aside class="barra-
   lateral">` (fundo) + `<div class="barra-lateral__interior">`
   (navegação, `position: sticky`) — correção do achado "a barra lateral
   termina antes do fim da página" —, o menu "Conta" (rodapé da barra,
   empurrado para baixo por `margin-top: auto`) desapareceu da captura do
   Início: o elemento novo não tinha altura própria para o `margin-top:
   auto` empurrar contra. Corrigido com `min-height: min(100%, var(--
   altura-viewport))`.
2. **2ª rodada:** o anel de foco padrão (`--acento`) media 1,27:1 contra o
   fundo escuro da barra lateral daquela rodada — abaixo do mínimo de
   3:1 de componente não-textual (WCAG 1.4.11). Corrigido com uma
   sobrescrita escopada à barra (`--bl-texto`, 13,40:1).
3. **3ª rodada:** o cabeçalho da coluna "Valor"/"Valor (R$)" continuava à
   esquerda mesmo depois de marcar `class="cabecalho-numerico"` —
   `.tabela-dados th` (especificidade 0-1-1) sempre vencia `.cabecalho-
   numerico` sozinha (0-1-0), em qualquer ordem de arquivo. Corrigido com
   `.tabela-dados th.cabecalho-numerico` (0-2-1).
