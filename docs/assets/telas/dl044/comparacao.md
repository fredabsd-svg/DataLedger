# DL-044 fase A — telas de trabalho, antes e depois

Capturas para o Fred aprovar a fase A da DL-044 antes de espalhar a mudança
para o resto do produto (fase B). Reprovação original: *"o layout da tela de
trabalho tá com aspecto de vazio e os botões de clicar [...] tá parecendo um
botão de link, tá muito amador, muito cara de sistema mal feito"* — a landing
pública **foi aprovada** e não muda nesta etapa.

Dados 100% sintéticos: `scripts/semear_base_de_medicao.py` (73 contas, 60
lançamentos em 03/2026) mais um pequeno movimento sintético em 02/2026 e um
parâmetro contábil mensal, por um script de apoio local (mesmo espírito de
`apps/fiscal/tests/xml_sinteticos.py`), e alguns documentos fiscais sintéticos
para o Início não ficar artificialmente pobre de categoria. Chromium, locale
`pt-BR` explícito no contexto do navegador (`navigator.language`/
`navigator.languages` conferidos = `pt-BR`), 26/09/2026.

**Antes** vem de duas fontes, ambas o estado já integrado antes desta etapa
(nenhuma das duas foi recapturada — é o "antes" de verdade, não uma versão
já melhorada): Início/Balancete/Novo lançamento saem das capturas da DL-042
(`docs/assets/telas/dl042/depois_*`, main tree); Zerar resultado (prévia) sai
da captura da DL-043 (`wt-dl043/docs/assets/telas/dl043/zerar_resultado_previa_*`,
ainda não integrada, mas já era a versão anterior a esta etapa).

## O que mudou, em uma frase por tela

1. **Tipografia**: de serifada (IBM Plex Serif, em toda a casca) para
   sem-serifa de trabalho (IBM Plex Sans, auto-hospedada, mesma licença) —
   documento impresso, marca e landing continuam serifados.
2. **Navegação entre relatórios**: de linha de links sublinhados para faixa
   de abas (traço de cor no item atual).
3. **Botões**: sombra rasa em repouso, mais funda no hover, achatados no
   clique (`:active`), opacos quando desabilitados — nos quatro tons.
4. **Tabela**: borda e sombra rasa ao redor (sem mudar altura de linha).
5. **Painel/cartão** (Início, prévia do zeramento, cabeçalho do
   lançamento): fundo `--papel-elevado` + sombra + raio maior, em vez de
   um contorno solto sobre o mesmo fundo da página.
6. **Barra lateral**: fundo cobre a coluna inteira mesmo em página alta e
   em captura de página inteira (achado da DL-043 corrigido — ver
   decisoes.md, DE-078).
7. **`- Select an option -` em inglês**: corrigido para "Selecione a
   conta"/"Nenhuma (conta raiz do plano)" nos três `<select>` de contas do
   parâmetro contábil e no de conta-pai do Plano de contas.

## Início (painel)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_1440x900.png) | ![Depois](depois_painel_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_painel_390x844.png) | ![Depois](depois_painel_390x844.png) |

**O que não mudou nesta fase, registrado, não escondido:** o painel ainda
tem bastante área vazia abaixo dos cartões, em telas largas, quando a fila
de atenção tem só 2-3 categorias — não é um defeito de CSS (a grade já
`auto-fit` para ocupar a largura disponível), é característica do padrão
"fila de atenção" com poucos itens. Resolver de vez exigiria conteúdo NOVO
(mais indicadores, com consulta nova) — fora do meu escopo de arquivo nesta
etapa (só posso mudar `views_web.py` para CONTEXTO de apresentação, e
`apps/tenancy/views.py`, que é quem monta o painel, não é `views_web.py` —
nem está na minha lista de arquivos permitidos). Fica registrado para a
fase B ou para quem tiver permissão de tocar `apps/tenancy/views.py`.

## Novo lançamento

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_1440x900.png) | ![Depois](depois_lancamento_novo_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_lancamento_novo_390x844.png) | ![Depois](depois_lancamento_novo_390x844.png) |

**Campo de data em mm/dd/aaaa nas duas versões** (visível no "Depois"
também): limitação JÁ CONHECIDA e já documentada do produto (DE-031) — o
`<input type="date">` usa o formato NATIVO do NAVEGADOR/sistema
operacional, que este ambiente de captura não tem localizado em pt-BR (nem
`locale="pt-BR"` do Playwright nem `--lang=pt-BR` no lançamento do
Chromium mudam o widget nativo — testado nesta etapa). O produto já
resolve isso do jeito que pode sem JavaScript: o rótulo não promete um
formato que não controla, e o texto de apoio abaixo do campo diz "toda
data EXIBIDA pelo sistema é dd/mm/aaaa" — o que é verdade em toda a
interface, exceto neste widget nativo específico.

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
das outras três) — `templates/contabilidade/balancete.html` tem um
comentário extenso (BL-284) registrando que a área ACIMA da primeira linha
da tabela já foi motivo de uma regressão medida de densidade (9 → 6 linhas
visíveis, §4.8 da direção de arte) numa etapa anterior. Acrescentar
`.cabecalho-pagina` ali (com a borda/padding que acabei de dar a essa
classe) somaria altura nessa mesma área crítica, e eu não tenho, nesta
etapa, o instrumento de medição (`scripts/juiz.py`, que exige Chromium
fora do pytest) rodado para prová-lo seguro. As mudanças que ESTA tela
recebeu (fonte, abas, tabela com moldura, botões) são todas de impacto
ZERO em altura de linha — a tabela em si permanece IDÊNTICA em densidade.

## Zerar resultado (prévia)

Computador (1440 × 900):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_zerar_resultado_previa_1440x900.png) | ![Depois](depois_zerar_resultado_previa_1440x900.png) |

Celular (390 × 844):

| Antes | Depois |
| --- | --- |
| ![Antes](antes_zerar_resultado_previa_390x844.png) | ![Depois](depois_zerar_resultado_previa_390x844.png) |

## Regressão pega ANTES de entregar (não pelo Fred, por mim)

Ao dividir a barra lateral em `<aside class="barra-lateral">` (fundo) +
`<div class="barra-lateral__interior">` (navegação, `position: sticky`) —
correção do achado "a barra lateral termina antes do fim da página" —, o
menu "Conta" (rodapé da barra, empurrado para baixo por `margin-top:
auto`) desapareceu da captura do Início: o elemento novo não tinha altura
própria para o `margin-top: auto` empurrar contra. Medido com
`getBoundingClientRect` antes de aceitar a captura como boa — corrigido com
`min-height: min(100%, var(--altura-viewport))` no elemento interior (o
raciocínio completo está no comentário da regra, `static/css/base.css`).
As capturas deste documento já refletem a correção — nenhuma delas tem o
defeito.
