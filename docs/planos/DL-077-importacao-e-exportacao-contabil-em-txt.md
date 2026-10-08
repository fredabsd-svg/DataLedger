# DL-077 — Contabilidade: importar e exportar plano de contas e lançamentos em TXT e Excel

**Demanda:** pedido do Fred de 08/10/2026 (RC-166) e a resposta dele à PE-80
(RC-167): *"quero as três opções e também importação via Excel"*. **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) na importação de lançamentos (grava no
Diário); nível 2 no plano de contas e na exportação. Auditoria independente
em cada fatia.

## Base

[Consulta ao contador-senior](../projeto/consultas/2026-10-08-contador-senior-txt-contabil.md):
rotina do sistema de referência (manual, pp. 782 a 832), leiaute de
importação com separador do sistema de referência (público, edição de
12/2018) e o **Manual de Orientação do Leiaute 9 da ECD** (ADE Cofis nº
01/2026, maio de 2026), lido na fonte oficial.

## Os formatos

| Formato | Plano de contas | Lançamentos | Saldos |
| --- | --- | --- | --- |
| **ECD** — registros do bloco I, leiaute 9 (ISO-8859-1, `\|`, CRLF, `ddmmaaaa`, vírgula decimal) | I050 (+ I051) — importar e exportar | I200/I250 — importar e exportar | I150/I155 — exportar |
| **Sistema de referência** — leiaute de importação com separador (`\|`, `dd/mm/aaaa`, decimal implícito) | 0200 (+ 0250) — importar e exportar | 6000/6100 — importar; exportar só o que o leiaute representa sem ambiguidade | — |
| **DataLedger** — TXT próprio, UTF-8, `;`, cabeçalho com nome das colunas, especificado em documento nosso | importar e exportar | importar e exportar | — |
| **Excel** (`.xlsx`) — mesmas colunas do formato próprio, uma aba por tipo, com modelo para baixar | importar | importar | — |

Regras que valem para todos:

- **Leiaute de terceiro é lido para construir o importador; o texto do
  documento não é copiado para o repositório** (RC-167). O código cita
  registro e campo, nunca transcreve páginas.
- **Nenhum leiaute é inventado.** Campo que o manual oficial não define não
  vira suposição: vira recusa nomeada ou pergunta.
- Arquivo exportado no leiaute da ECD **não é a ECD**: sem bloco J, termos,
  assinatura nem validação do programa da Receita; o nome do arquivo e a
  tela dizem isso.

## Arquitetura

Um **núcleo comum** (`apps/contabilidade/intercambio/`): cada formato só lê e
escreve; a validação, a conferência e a gravação são uma só.

- `canonico.py` — registros neutros: `ContaLida` (linha de origem, código,
  nome, código do pai, analítica ou sintética, tipo se o formato disser,
  natureza se o formato disser, código de origem alternativo — p.ex. o código
  reduzido do sistema de referência —, referencial), `LancamentoLido` (linha,
  número, data, histórico, partidas), `PartidaLida` (conta, débito ou crédito,
  valor `Decimal`, histórico da partida, centro de custo, participante) e
  `Ocorrencia` (linha, campo, nível **erro** ou **aviso**, mensagem).
- `formatos/ecd.py`, `formatos/referencia.py`, `formatos/proprio.py`,
  `formatos/excel.py` — leitores (arquivo → registros neutros + ocorrências
  de estrutura) e escritores (dados → arquivo).
- `plano.py` — conferência e aplicação do plano importado; exportação.
- `lancamentos.py` — área de conferência, efetivação e exportação.

## Fatias

1. **Plano de contas** — importar nos quatro formatos e exportar nos três TXT.
   Prévia antes de gravar, com as ocorrências por linha. Políticas escolhidas
   antes: **só acrescentar** (padrão) ou **acrescentar e atualizar nome**.
   Nunca apaga conta, nunca muda tipo ou natureza de conta com movimento;
   pai precisa existir (no arquivo ou no plano) e ser sintética. **Tipo** (ativo,
   passivo, PL, receita, despesa): do arquivo quando ele diz (ECD 01, 02,
   03); herdado do pai quando o pai já tem tipo; senão, o contador informa
   por **prefixo** na prévia (ex.: "3" → receita, "4" → despesa) — sem tipo,
   erro (HI-87). **Natureza** devedora ou credora: do arquivo quando ele diz;
   senão, presumida pelo tipo **com aviso listando cada conta**, para o
   contador conferir as redutoras (HI-88). ECD 05 e 09 recusadas.
2. **Exportar lançamentos e saldos** por intervalo, com relatório de
   conferência (quantidade, soma de débitos e créditos, SHA-256, autor e data).
3. **Importar lançamentos** numa **área de conferência** separada (o
   lançamento efetivado é imutável): erro nunca grava; aviso grava só se
   aceito; efetivação explícita por papel autorizado, via `criar_lancamento`.
   Recusas: débito diferente de crédito, competência encerrada, conta
   inexistente, sintética ou inativa, empresa do arquivo diferente. Tipo E da
   ECD não entra. Reimportar não duplica: chave (empresa, SHA-256 do
   arquivo, número do lançamento) na idempotência existente, com prefixo
   reservado. Histórico por partida vira histórico do lançamento sem truncar
   em silêncio. De-para de contas por empresa, reutilizável.

## Decisões tomadas na fatia 1 (auditoria e correção)

[Rodada 1](../auditorias/2026-10-08-dl-077-fatia-1-rodada-1.md) reprovada,
correção única e [reconferência](../auditorias/2026-10-08-dl-077-fatia-1-reconferencia.md)
reprovada só pelo leitor Excel. Pela regra de parada do §3.1 não houve
terceira rodada: as correções do Excel foram aceitas pelos **testes escritos
pelo próprio auditor** na reconferência.

- **Conta de resultado da ECD** (COD_NAT 04) só aceita receita ou despesa;
  herdar outro tipo do pai ou do prefixo é erro.
- **Conta pai** é o maior prefixo existente no arquivo **ou** no cadastro,
  respeitando a fronteira de nível; aviso quando não é o prefixo imediato.
- **Limites:** até 2.500 contas por importação (a aplicação de 5.000 levou
  cerca de 28 s, perto do limite de tempo do servidor); até 50 níveis de
  conta superior, contando arquivo e cadastro; caractere de controle em
  código ou nome é recusado.
- **Excel:** só `.xlsx`; varredura do pacote antes da biblioteca de
  planilha, com teto de tamanho por parte, de elementos, de células e de 50
  colunas; XML inválido vira recusa com mensagem. A troca da biblioteca por
  um leitor próprio fica para o BL-674.
- **CNPJ alfanumérico** (RC-46): aceito na ECD; recusado com mensagem no
  leiaute do sistema de referência, que só define inscrição numérica
  (PE-81).
- **Leiaute do sistema de referência:** linha com barra no início e no fim é
  a forma canônica (HI-91).
- **Formato próprio do DataLedger (plano):** TXT UTF-8 (BOM aceito na
  leitura), CRLF na escrita, separador `;`, cabeçalho
  `codigo;nome;codigo_pai;analitica;tipo;natureza`, `analitica` S ou N, tipo
  e natureza vazios ou nos valores do cadastro, aspas no padrão RFC 4180.

## Decisões tomadas nas fatias 2 e 3 (lançamentos)

[Rodada 1](../auditorias/2026-10-08-dl-077-fatias-2-3-rodada-1.md) reprovada;
correção única com as decisões abaixo; reconferência a seguir.

- **Exportação:** registros I200/I250 (e I150/I155 com meses inteiros) no
  leiaute da ECD, formato próprio e 6000/6100 do sistema de referência (valor
  com vírgula e 2 casas, HI-91; lançamento com vários débitos e vários
  créditos não cabe nesse leiaute e é recusado ou omitido com lista);
  intervalo de até 366 dias; o zeramento sai marcado `E` na ECD; saldos
  conferidos contra o balancete do produto. Histórico com caractere fora do
  padrão só sai com a opção explícita de normalizar o texto, que lista cada
  lançamento alterado — o lançamento efetivado não muda.
- **Importação em área de conferência:** nada entra no Diário sem
  efetivação explícita. A conferência repete as recusas de
  `criar_lancamento` (até 200 partidas, débito igual a crédito, valor e
  escala, competência aberta, conta analítica da empresa) e recusa conta
  inativa. De-para de contas por empresa e formato.
- **Erro do arquivo inteiro** (empresa não conferida ou leitura
  interrompida) bloqueia as duas políticas; "só os válidos" deixa de fora só
  lançamentos com erro próprio.
- **Avisos que exigem aceite:** lançamento igual a um já existente no Diário
  (data, histórico e partidas); arquivo que não declara a empresa (ECD sem
  0000, formato próprio, Excel); o aceite cai se os avisos mudarem.
- **Limites:** 2.000 lançamentos e 4.000 partidas por arquivo (efetivar
  2.000 × 2 mediu ~17 s; o servidor padrão corta em 30 s, BL-675); 500
  ocorrências do arquivo guardadas, com a contagem total.
- **Idempotência:** chave `importacao:<SHA-256 do arquivo>:<número>`, prefixo
  reservado (o lançamento manual recusa, em qualquer caixa).

### Formato próprio do DataLedger — lançamentos (versão 1)

UTF-8 (sem BOM na escrita), CRLF, separador `;`, aspas no padrão RFC 4180.
Cabeçalho fixo `numero;data;historico;conta;lado;valor`. Uma linha por
partida; as partidas de um lançamento saem em sequência com o mesmo
`numero`. `data` em `aaaa-mm-dd`; `conta` é o código da conta no DataLedger;
`lado` é `D` ou `C`; `valor` com ponto decimal e exatamente duas casas, sem
milhar nem sinal. Saldos não entram neste formato. Na planilha Excel, a aba
`lancamentos` usa as mesmas colunas.

## Critérios de aceite da fatia 1

1. Os quatro leitores aceitam arquivos sintéticos montados à mão segundo o
   leiaute (registro e campo citados nos testes) e recusam, com linha e campo,
   o que foge dele (data, número, campo obrigatório, registro desconhecido,
   codificação).
2. Ida e volta: exportar o plano em cada formato TXT e reimportar na mesma
   empresa com "só acrescentar" não cria nada; em empresa vazia, recria o
   mesmo plano (código, nome, pai, analítica, tipo, natureza).
3. Nada é gravado enquanto houver erro; a prévia lista cada linha com o
   motivo; aplicar é atômico.
4. Conta com movimento nunca muda de tipo ou natureza; nenhuma conta é
   apagada.
5. Tipo por prefixo e natureza presumida com aviso funcionam como descrito.
6. Excel: só `.xlsx`; macro (`.xlsm`), fórmula sem valor, arquivo acima do
   limite ou planilha fora do modelo são recusados com mensagem.
7. Isolamento entre escritórios e empresas, permissão no servidor, trilha de
   quem importou e exportou (arquivo por SHA-256 e contagens).
8. Mutação nas regras de recusa derruba testes.

## Divisão da fatia 1

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — núcleo, leitores e escritores ECD e próprio, conferência e aplicação do plano, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/contabilidade/intercambio/` (exceto `formatos/referencia.py` e `formatos/excel.py`), modelos e migração se precisar, testes `test_dl077_*` |
| B — leitores do sistema de referência e do Excel, escritor do sistema de referência, modelo de planilha, dependência `openpyxl` | `auxiliar-implementacao` (Haiku), depois de A | `formatos/referencia.py`, `formatos/excel.py`, `requirements/`, testes próprios |
| C — telas (importar com prévia, exportar, baixar modelo) | `auxiliar-implementacao` (Haiku) | `views_web.py`, `urls_web.py`, `templates/contabilidade/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Pacote novo e, se houver, tabelas novas (registro da importação, de-para);
nada muda nas contas e lançamentos existentes além do que a importação
aplicada criar, com trilha.
