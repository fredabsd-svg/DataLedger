# Consulta ao contador-senior sobre importação e exportação de plano de contas e lançamentos em TXT — 08/10/2026

Sexta consulta do `arquiteto-senior` ao `contador-senior` (Fable), depois do pedido
do Fred de 08/10/2026 (RC-166), antes de planejar a
[DL-077](../../planos/DL-077-importacao-e-exportacao-contabil-em-txt.md). Registro
integral da resposta. A escolha do leiaute está com o Fred (PE-80, em
[requisitos.md](../requisitos.md)).

Nota de método: a skill `anthropic-skills:contador-senior` não está disponível neste ambiente; segui o método do projeto (manual responde rotina, fonte oficial responde norma, decisão de produto é do Fred). Nenhum arquivo foi escrito no repositório; o material de terceiros foi baixado em área temporária e é descrito aqui com palavras minhas.

Legenda de fonte: **lido** = documento oficial/aberto baixado e lido hoje; **cópia** = texto reproduzido por terceiro; **secundário** = notícia/fornecedor; **não conferido**. Grau de segurança: alto / médio / baixo.

## 0. O que existe hoje no código (verificado)

Tudo em `apps/contabilidade/models.py`, salvo indicação.

| Elemento | Onde | O que há de fato |
| --- | --- | --- |
| `Conta` | l. 1026-1180 | `empresa`, `conta_pai` (self, PROTECT), `codigo` (20 chars, único por empresa — l. 1180), `nome`, `tipo` (ativo/passivo/PL/receita/despesa — l. 218-223), `natureza` (devedora/credora — l. 226-228), `classificacao_patrimonial`, `classificacao_dre`, `classificacao_dlpa`, `classificacao_dmpl`, `caixa_e_equivalentes`, `classificacao_dfc`, `aceita_lancamento` (é o que distingue sintética de analítica — l. 1088-1092), `ativo`, `criado_em`. |
| Não existe em `Conta` | grep em todo o arquivo | código reduzido, nível explícito (só derivável pela cadeia de `conta_pai`), vínculo ao plano referencial, histórico padrão, centro de custo, participante. O mapa confirma: `docs/projeto/mapa-funcional-contabil.md` l. 570 (históricos padronizados: não existe), l. 573 (centros de custo: não existe, RC-54, BL-67 a BL-69), l. 589 (referencial: não existe). |
| `LancamentoContabil` | l. 2257-2433 | `empresa`, `data`, `historico` (300 chars, **um por lançamento**), `estorno_de`, `criado_por`, `criado_em`, `chave_idempotencia` (255) + `chave_idempotencia_fingerprint` (SHA-256 do conteúdo), `competencia` FK. Imutável em `save`/`delete` e por gatilho no banco (migração 0013); INSERT em competência não aberta é recusado pelo banco (DL-069, migração 0023) — docstring l. 2267-2277. |
| `ItemLancamento` | l. 2441-2521 | `conta`, `tipo` (debito/credito), `valor` Decimal(18,2) > 0. Imutável. |
| **Rascunho** | grep `rascunho` no models.py | **Não existe estado de rascunho.** O que existe é "lançamento efetivado e imutável". |
| `criar_lancamento` | `apps/contabilidade/services.py` l. 711-721 | Parâmetros: `empresa, data, historico, itens, criado_por, estorno_de, chave_idempotencia, permitir_prefixo_reservado`. Idempotência por chave + conteúdo; prefixo `zeramento:` reservado (l. 750-754). |
| Competência | l. 33-59 | Estados `aberta`, `em_encerramento` (reservado, inalcançável), `encerrada`. |
| Precedente de exportação TXT | `apps/livro_caixa/carne_leao_arquivos.py` | Arquivo do Carnê-Leão Web em ISO-8859-1 com CRLF (HI-41, `docs/projeto/requisitos.md` l. 375). |
| Pedido do Fred | `docs/projeto/requisitos.md` l. 104 (RC-166) | Importar e exportar plano e lançamentos em TXT; leiaute em aberto. |
| Pendência relacionada | `docs/projeto/requisitos.md` l. 437 (PE-18) | **Ler o formato de intercâmbio do sistema de referência ainda é decisão pendente do Fred** (dimensão jurídica). Isso pesa na alternativa (b) da pergunta 4. |
| Critério já fixado | `docs/projeto/mapa-funcional-contabil.md` l. 450-451 | Critério 14: importação não grava registro com erro; reimportar não duplica. |

Inferência (não comprovada): a ausência de rascunho e a imutabilidade no banco significam que "importar como rascunho" **não pode ser um flag em `LancamentoContabil`**; precisa ser uma área de preparação separada (ver pergunta 5).

## 1. Rotina de importação/exportação no manual do sistema de referência

**Resposta curta.** O manual descreve cinco famílias de importação e três de exportação. O que importa para nós: validação em camadas com três desfechos (grava / grava só se o usuário aceitar / nunca grava), política explícita de duplicidade escolhida pelo usuário antes de importar, e checagem de que a empresa do arquivo é a empresa ativa. Ele **não** descreve qual chave identifica um lançamento "já existente".

**Fonte:** lido — `Domínio Contabilidade.pdf`, diretório público indicado pelo Fred, edição de 06/12/2018, 856 páginas, seções 6.24 (pp. 782-828) e 6.25 (pp. 829-832). Rotina de concorrente, de 2018; nunca norma. **Grau: alto** quanto ao que o manual diz; **baixo** quanto a refletir o produto atual do fornecedor.

Com minhas palavras:

- **De outra empresa do mesmo escritório** (pp. 783-785): copia lançamentos (simples ou em lote) filtrando por intervalo de datas, de números/lotes, por conta ou por valor; e copia cadastros/configurações, inclusive por "perfil de empresa". É a rotina de "abrir empresa nova a partir de um modelo", não de migração externa.
- **Importação padrão em leiaute com separador** (pp. 786-789): escolhe um ou vários `.txt`; mostra nome e CNPJ da empresa destino; o usuário escolhe, separadamente para cadastros e para movimentos, entre **sobrescrever o que já existe** ou **importar só o que não existe**; e escolhe de onde vem o histórico (do lançamento padrão, do arquivo, ou ambos).
- **Importador genérico configurável** (pp. 789-819): o usuário descreve o leiaute (texto ou XML; com ou sem separador de campos; delimitador de texto; separador decimal; registros agrupados ou hierárquicos), mapeia campo do arquivo para campo do sistema, define **equivalências de-para** por leiaute, **tabelas de consulta** (ex.: achar o código interno a partir do CNPJ do arquivo), regras condicionais e cálculos. Pode exigir que o arquivo identifique a empresa; se a empresa identificada não for a ativa, a importação é abortada (p. 800).
- **Resultado em quatro abas** (pp. 795-799): (1) registros que passaram e serão gravados; (2) **advertências** — só gravam se o usuário marcar cada registro ou o grupo; (3) **erros** — nunca gravam; (4) **críticas de estrutura** — linha ilegível não é processada; campo com problema de advertência vira nulo. "Gravar" grava os válidos mais as advertências aceitas e mostra contagem por cadastro.
- **Leiautes antigos, extrato bancário, tabelas e "outros"** (pp. 820-828): importação de lançamentos de outros sistemas e de empresas por leiaute pré-definido; extrato bancário (OFX/Febraban 240) por competência e conta do banco com geração de lançamentos; importação de tabelas com leiaute padrão protegido ("salvar como" para criar o próprio; tamanho fixo ou separador; campo vazio escrito como `NULO`); e um TXT simples para históricos padrões e contas com separador ASCII configurável e mapeamento campo a campo.
- **Exportação** (pp. 829-832): lançamentos por intervalo de data **ou** de lote para um arquivo; plano de contas com seleção de contas, ordem (código reduzido, classificação ou nome) e filtro todas/analíticas/sintéticas, com contador de exportadas; e um pacote para o módulo do cliente, com envio por e-mail.
- **Dado colateral relevante** (pp. 779-780): o sistema de referência **tolera lote gravado com débito ≠ crédito** e avisa ao entrar. O DataLedger recusa isso no banco. Nossa importação, portanto, vai reprovar arquivos que o sistema de referência aceitaria — é correto, mas precisa estar escrito na tela.

**Não determinado no manual:** a chave de "registro existente" para movimentos (número do lote? data+contas+valor?); se a importação é atômica por arquivo; o que acontece com lançamento em período já encerrado.

## 2. Leiaute TXT público do sistema de referência (plano e lançamentos)

**Resposta curta.** Existe, é público (sem autenticação) e está no mesmo diretório: `Importação Padrão.pdf`, capítulo 13 "Importação Padrão – Leiaute com Separador" (pp. 1217-1470). Cobre plano de contas (registros 0200/0250), históricos (0220), departamentos e centros de custo (0230/0240) e **lançamentos em lote avulsos (6000/6100/6110/6130)**, além dos lançamentos embutidos em documentos fiscais (1300, 2300, 3300 etc.). Mas o documento traz aviso de que **não pode ser reproduzido sem permissão escrita**, e PE-18 continua pendente.

**Fonte:** lido — `Importação Padrão.pdf`, edição de 10/12/2018, 1.495 páginas; regras gerais na p. 1224; registros 0200-0250 nas pp. 1275-1277; 6000-6130 nas pp. 1449-1451; aviso de direitos autorais na página de rosto. **Grau: médio-alto** quanto à estrutura; **baixo** quanto a estar vigente em 2026.

Estrutura, com minhas palavras:

- **Regras gerais** (p. 1224): separador `|`; tipos caractere, numérico e data; data em `dd/mm/aaaa`; **numérico sem vírgula** (o exemplo converte 100,99 em 10099 — decimal implícito), e campos "decimal" com número de casas declarado. Registro `0000` traz só o CNPJ/CPF da empresa. Diferente da ECD, portanto, em data e em decimal.
- **0200 – contas** (11 campos): código reduzido, classificação (o código estruturado), tipo analítica/sintética, descrição, data de cadastro, situação ativa/inativa, data de inativação, e três códigos de vínculo a estruturas de demonstração (DLPA, DOAR, DRE). **Não traz natureza nem conta pai** — a hierarquia é inferida da classificação.
- **0250 – referencial**, filho do 0200: classificação referencial e indicador do órgão (Receita ou Banco Central).
- **0220 – históricos**: código e descrição. **0240 – centro de custo**: código, descrição, departamento, data.
- **6000 – lançamento em lote**: tipo (um débito para vários créditos, um crédito para vários débitos, um para um, vários para vários), código de lançamento padrão, localizador, campo de RTT.
- **6100 – partidas**, filho do 6000: data, **conta a débito e conta a crédito na mesma linha (por código reduzido)**, valor, código do histórico (0220), complemento do histórico, usuário, filial, SCP. **6110** rateia por centro de custo; **6130** marca DFC.

Observações minhas (inferência):

- O 6100 é formato de **par débito-crédito por linha**. Importar para o nosso modelo é direto (cada linha vira dois `ItemLancamento`). **Exportar** o nosso lançamento com, por exemplo, 3 débitos e 2 créditos exigiria decompor em pares — não existe pareamento único; isso é motivo técnico para **não** adotar esse leiaute como formato de saída.
- O leiaute depende de **código reduzido**, que o DataLedger não tem.
- Não encontrei, no capítulo contábil, registro de **saldos** (os registros de saldo que aparecem são de produtos).

**Não determinado:** tipo e formato dos campos 2 a 7 do registro 6100 (a extração do PDF perdeu as colunas); a chave de duplicidade usada na opção "importar somente inexistentes"; se o fornecedor alterou o leiaute após 2018.

## 3. Leiaute oficial da ECD (registros I050, I051, I052, I075, I100, I150, I155, I200, I250)

**Resposta curta.** Confirmado na fonte oficial, versão vigente: *Manual de Orientação do Leiaute 9 da ECD*, anexo ao **ADE Cofis nº 01/2026, atualização de maio de 2026**, 236 páginas; a página oficial informa que não houve alteração de leiaute no ano-calendário 2025. Código de versão `9.00` desde o ano-calendário 2020 (I010, p. 103). Arquivo texto **ISO-8859-1**, `|` no início e após cada campo, **CRLF** no fim da linha, datas `ddmmaaaa`, números só com dígitos e **vírgula decimal** (pp. 51-53). Campos e regras abaixo conferem com o que o arquiteto listou, com duas ressalvas importantes para migração.

**Fonte:** lido — `http://sped.rfb.gov.br/pasta/show/1569` → item 7990 → `/arquivo/download/7990` (PDF, 236 p.). **Grau: alto.**

| Registro | Campos (tipo/tamanho/decimais), na ordem | Regras que importam para nós |
| --- | --- | --- |
| **I050** plano (pp. 118-122) | REG; DT_ALT N8; COD_NAT C2 (01 ativo, 02 passivo, 03 PL, 04 resultado, 05 compensação, 09 outras); IND_CTA S/A; NIVEL N; COD_CTA C (chave); COD_CTA_SUP C (obrigatório se nível > 1, vazio se nível 1); CTA C | Pai deve existir e ser sintética; natureza igual à do pai a partir do nível 3; analítica de ativo/passivo/PL em livro G/R/B precisa de nível ≥ 4 (CTG 2001 (R3), item 8: mínimo 4 níveis). **Só entram contas com saldo ou movimento no período** (p. 118) — a ECD **não carrega o plano inteiro**. |
| **I051** referencial (pp. 123-124) | REG; COD_CCUS C; COD_CTA_REF C | Facultativo; só para analíticas; obrigatório quando 0000.COD_PLAN_REF (campo 23, valores 1-11: 1 PJ Lucro Real, 2 PJ Lucro Presumido, 3 Financeiras…) está preenchido. É o **de-para** oficial. |
| **I052** aglutinação (pp. 125-126) | REG; COD_CCUS C; COD_AGL C | Só analíticas; chave CCUS+AGL; alimenta o bloco J. |
| **I075** histórico padronizado (p. 130) | REG; COD_HIST C (chave); DESCR_HIST C | Facultativo. |
| **I100** centro de custos (p. 131) | REG; DT_ALT N8; COD_CCUS C; CCUS C | Obrigatório para quem usa centro de custo. |
| **I150** período de saldos (pp. 132-133) | REG; DT_INI N8; DT_FIN N8 | Um por mês; sem buraco de meses no intervalo do arquivo. |
| **I155** saldos (pp. 134-136) | REG; COD_CTA; COD_CCUS; VL_SLD_INI N19,2; IND_DC_INI D/C; VL_DEB N19,2; VL_CRED N19,2; VL_SLD_FIN N19,2; IND_DC_FIN D/C | Soma dos saldos iniciais e dos finais = 0 por período; soma D = soma C por período; final = inicial ± movimento; zero escrito `0` ou `0,00` e indicador D/C obrigatório mesmo em zero. |
| **I200** lançamento (pp. 143-147) | REG; NUM_LCTO C (chave, único no arquivo); DT_LCTO N8; VL_LCTO N19,2 (= soma das partidas de um mesmo lado); IND_LCTO N/E/X; DT_LCTO_EXT N8 (só em X) | Data dentro do intervalo do 0000; mais de um D e mais de um C no mesmo lançamento gera **aviso** (4ª fórmula), não erro. |
| **I250** partidas (pp. 148-151) | REG; COD_CTA C; COD_CCUS C; VL_DC N19,2; IND_DC D/C; NUM_ARQ C; COD_HIST_PAD C; HIST C até 65.535; COD_PART C | Conta deve existir no I050 e ser analítica; **HIST ou COD_HIST_PAD obrigatório em cada partida** (o histórico é **por partida**, não por lançamento); soma de D e de C por conta e período tem de bater com o I155. |

Sobre a afirmação "todos os sistemas geram esse formato": o manual diz que a empresa gera o arquivo com recursos próprios e o submete ao PGE (p. 51). Logo, **qualquer sistema que entrega ECD emite esses registros** — isso é inferência razoável, não frase da fonte. Duas ressalvas de contador:

1. **A ECD do ano anterior não é a migração completa.** Traz só contas com saldo/movimento, lançamentos daquele ano-calendário e saldos mensais. Para abrir o ano corrente no DataLedger o que se precisa de fato é o **saldo final de dezembro (I155) como saldo de abertura** mais o plano; os lançamentos do ano anterior entram como histórico, não como escrituração a refazer. Isso muda o desenho: importar **saldos** é tão importante quanto importar lançamentos.
2. Lançamentos **tipo E** (encerramento) vêm no arquivo; o DataLedger já tem zeramento próprio (DL-043). Importar E sem tratamento duplica o encerramento. E livro tipo **B** (balancetes diários) não tem I200/I250 — não há lançamentos para importar.

## 4. Recomendação ao Fred

**Resposta curta.** Adotar os **registros da ECD (c) como leiaute-base de importação e exportação**, com uma camada mínima nossa documentada (a) para o que a ECD não cobre no nosso modelo; deixar o leiaute do sistema de referência (b) como **importador adicional, só de entrada**, e só depois de o Fred resolver PE-18. Começar pelo **plano de contas (importar e exportar)**, depois **exportar lançamentos e saldos**, depois **importar lançamentos**.

**Fonte:** análise minha sobre o lido acima. **Grau: médio** (é trade-off de produto; a palavra final é do Fred).

| Critério | (a) Leiaute próprio | (b) Leiaute do sistema de referência | (c) Registros da ECD |
| --- | --- | --- | --- |
| Migrar cliente novo vindo de **qualquer** sistema | Ninguém gera o nosso formato; exige conversor por origem | Só cobre quem vem do sistema de referência ou de ERP que exporta nele | Qualquer sistema obrigado à ECD já gera; o arquivo do ano anterior **já está no escritório** |
| Receber lançamentos do **ERP do cliente** | ERP precisaria programar o nosso formato | Alguns ERPs exportam nele (hipótese; não conferi) | ERPs que geram ECD ou "I200/I250" conseguem; outros não (hipótese) |
| **Levar dados para outro sistema** (saída do cliente, troca de escritório) | Destino não lê | Pareamento D/C ambíguo na exportação (ver §2); 2018 | Destino que importa ECD lê; é também o formato que o auditor e a Receita conhecem |
| Aderência normativa | Nenhuma exigida | Nenhuma | Fonte oficial, versionada, com regras de validação publicadas que podemos reproduzir em testes |
| Risco jurídico | Zero | **PE-18 pendente**; manual proíbe reprodução | Zero (leiaute público de governo) |
| Lacunas frente ao nosso modelo | Nenhuma por definição | Código reduzido não existe no DataLedger | Histórico por partida vs. por lançamento; centro de custo, participante, NUM_ARQ sem destino hoje |
| Custo | Baixo, mas valor baixo | Médio; parser + de-para + código reduzido | Médio; parser hierárquico + regras I050/I155/I200/I250 |
| Reaproveitamento futuro | Nenhum | Nenhum | É metade do caminho para **gerar a ECD** (mapa l. 168 e critério 9, l. 442-443) |

O que cobre melhor a rotina real do escritório é (c): migração de entrada e saída, conferência com o PGE do lado de quem recebe, e prepara a ECD. A camada (a) deve ser **mínima e escrita**: aceitar arquivo ECD completo **ou** arquivo parcial só com os registros do bloco I que usamos (parser ignora o resto); tolerar UTF-8 além de ISO-8859-1 na entrada; definir como o histórico por partida vira o nosso histórico por lançamento. Não inventar registro novo.

Ordem sugerida, e por quê:

1. **Plano de contas: importar e exportar (I050 + I051 opcional).** Menor risco (sem valor monetário), destrava tudo o resto, e a exportação é o teste de ida e volta.
2. **Exportar lançamentos e saldos (I200/I250 + I150/I155).** Só leitura, baixo risco, já entrega "levar dados para fora" e serve de fixture para o item 3.
3. **Importar lançamentos**, na área de preparação da pergunta 5. É o item de maior risco contábil e deve vir por último, com teste contra os arquivos do item 2.
4. **Importador (b)**, somente se o Fred decidir PE-18 e confirmar que há clientes/ERPs que de fato entregam nesse leiaute.

## 5. Regras de importação que o produto deve seguir

**Fonte:** regras do projeto (`CLAUDE.md`, `AGENTS.md` §10, critérios 1-15 do mapa contábil l. 429-453), código verificado no §0, e regras de validação da ECD lidas. Cada item marcado como **confirmado** (já é regra do projeto ou do código), **hipótese** (minha proposta) ou **decisão do Fred**.

| Tema | Regra proposta | Classificação |
| --- | --- | --- |
| Rascunho ou efetivado | Importação grava numa **área de preparação própria** (lote importado + linhas), nunca direto em `LancamentoContabil`. Validação completa no lote; só a **efetivação explícita**, por papel autorizado, chama `criar_lancamento` para cada lançamento. Motivo: `LancamentoContabil` é imutável no banco (§0); corrigir depois seria estorno, o que poluiria o Diário com erro de importação. | Hipótese forte; o modelo não tem rascunho (verificado). Decisão do Fred se o lote pendente deve aparecer em relatórios "com itens pendentes" ou ficar invisível. |
| Partida dobrada | Por **lançamento** (soma D = soma C = VL_LCTO), que é a nossa invariante e a regra da ECD (I200). Por lote: **tudo ou nada** por padrão (critério 14 l. 450). Efetivar só os válidos, deixando erros de fora, só com confirmação explícita e relatório — equivalente da aba de advertências do sistema de referência. | Confirmado (invariante) + hipótese (política do lote). |
| Período encerrado | Linha com data em competência `encerrada` é **erro na pré-validação**; nunca reabrir automaticamente. O banco já recusa o INSERT (DL-069), mas o usuário precisa ver a lista antes, não um erro na efetivação. Mesma regra para toda porta de escrita (RC-146, requisitos l. 47). | Confirmado. |
| Conta inexistente | Erro. Não criar conta a partir de I250 (não traz nome, natureza nem pai). Criar automaticamente só se o I050 correspondente estiver no mesmo arquivo e a opção "criar contas do arquivo" estiver ligada. | Hipótese. |
| Conta sintética | Erro (`aceita_lancamento=False`), igual à REGRA_CONTA_ANALITICA da ECD e ao critério 2 (l. 430). Conta inativa (`ativo=False`): erro. | Confirmado / hipótese (inativa). |
| Reimportação sem duplicar | Chave natural = **(empresa, identidade do arquivo, NUM_LCTO)**. Identidade do arquivo = SHA-256 do conteúdo. Na efetivação, `chave_idempotencia = "importacao:<hash>:<NUM_LCTO>"` com prefixo reservado (mesmo padrão de `zeramento:`, services l. 750-754), o que reaproveita a defesa de banco `chave_idempotencia_unica_por_empresa` (models l. 2388-2392) e o fingerprint que recusa mesma chave com conteúdo diferente. NUM_LCTO sozinho **não** serve: é único só dentro de um arquivo/ano. Arquivo sem NUM_LCTO: recusar, não inventar. | Hipótese alinhada ao código existente. |
| Plano importado sobre plano existente | Duas políticas escolhidas antes de importar: **só acrescentar** (padrão) ou **acrescentar e atualizar nome/classificações** das contas já existentes. **Nunca** apagar, desativar ou mudar `tipo`/`natureza` de conta com movimento (critério 10, l. 444; teste `test_dl023_conta_nao_muda_de_empresa_ou_natureza.py` já protege natureza). Conta pai deve existir (no arquivo ou no banco) e ser sintética; `NIVEL` informado divergente da cadeia de `conta_pai` = advertência. COD_NAT → `tipo`: 01→ativo, 02→passivo, 03→PL, 04→resultado **exige decidir receita × despesa** (a ECD não distingue): propor pela `natureza` informada no de-para ou perguntar na tela; 05 e 09 → recusar ou exigir mapeamento manual. | Hipótese; a regra 04→receita/despesa é **decisão do Fred**. |
| De-para de contas | Tabela de mapeamento **por empresa**, persistida e reutilizável: código de origem → `Conta`. Linha sem mapeamento = erro. Sugerir automaticamente quando o código coincide. O sistema de referência resolve isso com "equivalências" e "tabela estrangeira" (pp. 806-817): a rotina do escritório precisa disso. | Hipótese. |
| Histórico | Não há histórico padrão no modelo (mapa l. 570). Regra de montagem a partir da ECD: `DESCR_HIST + " " + HIST` (fórmula da p. 149) de cada partida; se todas as partidas tiverem o mesmo histórico, vira o histórico do lançamento; se diferirem, concatenar com separador e **advertir**; resultado > 300 chars = **erro**, nunca truncar em silêncio. Alternativa: ampliar o campo ou criar histórico por item. | Hipótese; ampliar o campo é **decisão do Fred**. |
| Centro de custo, participante, NUM_ARQ | Não existem no modelo (mapa l. 573). Campo preenchido no arquivo → **advertência "ignorado"** registrada na trilha; nunca descartar em silêncio. Rateios (6110/I155 por CCUS) idem. | Hipótese. |
| Lançamentos tipo E e X | **E** (encerramento): não importar por padrão — o zeramento é nosso (DL-043); opção explícita para importar como histórico. **X** (extemporâneo): importar; o histórico já deve conter motivo, data e número do lançamento de origem (ITG 2000 (R1), item 32, citado no manual p. 149). | Hipótese (E); confirmado (X, norma CFC via manual oficial). |
| Empresa | CNPJ do registro 0000 deve ser o da empresa destino; divergência aborta (o sistema de referência faz o mesmo, p. 800; a nossa regra de isolamento exige). | Confirmado. |
| Valores | `Decimal`, exatamente 2 casas; mais casas = erro (`ESCALA_MAXIMA_LANCAMENTO_MANUAL`, services l. 729-731); nunca float. Vírgula decimal e ausência de separador de milhar conforme ECD. | Confirmado. |
| Trilha e autorização | Quem importou, quando, arquivo (hash), quantidades por desfecho; efetivação restrita a papel autorizado no servidor (critério 15, l. 452-453). | Confirmado. |

## 6. Exportação

**Resposta curta.** O escritório espera três coisas: levar o cliente para outro sistema (ou receber de volta), entregar dados a cliente/auditor, e ter uma cópia legível. Exportar **no mesmo leiaute da importação** (registros da ECD) atende as três e permite teste de ida e volta. Exportação **não é backup** (PE-07, mapa l. 594) e **não é a ECD** — o produto precisa dizer isso na tela, no nome do arquivo e no relatório de conferência.

**Fonte:** ECD lida (formato, pp. 51-53); regras do projeto; `docs/projeto/personalizacao-de-relatorio.md` (classe "documento de conferência"); precedente `carne_leao_arquivos.py`. **Grau: médio.**

- **Conteúdo:** plano (I050; I051 se houver vínculo), lançamentos (I200/I250) por intervalo de datas e/ou faixa de números, saldos mensais (I150/I155) do intervalo, opcional. Filtros do plano: todas / só analíticas / só com movimento no período. Codificação ISO-8859-1 com CRLF, como a ECD manda (p. 51); caractere fora do Latin-1 no histórico = erro explícito, nunca substituição silenciosa.
- **Documento de conferência junto do arquivo:** total de lançamentos, soma de débitos e de créditos, intervalo, contagem de contas, SHA-256 do arquivo, quem gerou e quando. É o que permite ao destino conciliar e é a regra "relatório conciliável com os lançamentos de origem".
- **Como evitar confusão com a ECD:** nome na interface "Exportação contábil (registros no leiaute da ECD)", nunca "ECD" ou "SPED"; nome de arquivo sem `SPED`/`ECD` (ex.: `contabil-<cnpj>-<aaaamm>-<aaaamm>.txt`); **não emitir** bloco J, termos (I030), assinaturas nem registros de fechamento (9999) por padrão; aviso fixo na tela e no relatório: "este arquivo não substitui a ECD, não foi validado nem assinado pelo PGE". Incluir 0000/I010 só como opção ("cabeçalho para sistemas que exigem"), desligada por padrão — **decisão do Fred**.
- **Exportar o leiaute do sistema de referência:** não recomendo (pareamento D/C ambíguo, 2018, PE-18).

## Tabela-resumo

| # | Pergunta | Resposta curta | Fonte | Grau |
| --- | --- | --- | --- | --- |
| 1 | Rotina do sistema de referência | Importação em camadas com 3 desfechos (grava / grava se aceito / nunca grava); política sobrescrever × só inexistentes; aborta se empresa do arquivo ≠ ativa; exportação de lançamentos por data/lote e de contas com filtro. Tolera lote desbalanceado — nós não. | Lido (PDF público, 2018) | Alto (texto) / baixo (vigência) |
| 2 | Leiaute TXT público do sistema de referência | Existe (cap. 13 de `Importação Padrão.pdf`): `\|`, `dd/mm/aaaa`, numérico sem vírgula; 0200/0220/0240/0250 e 6000/6100/6110/6130; depende de código reduzido; exportação exigiria pareamento D/C. Manual proíbe reprodução; PE-18 pendente. | Lido (PDF público, 2018) | Médio-alto / baixo (vigência) |
| 3 | ECD | Leiaute 9, ADE Cofis 01/2026 (maio/2026), versão 9.00; ISO-8859-1, `\|`, CRLF, `ddmmaaaa`, vírgula decimal; campos de I050/I051/I052/I075/I100/I150/I155/I200/I250 confirmados; histórico por partida; só contas com saldo/movimento. | Lido (sped.rfb.gov.br) | Alto |
| 4 | Recomendação | (c) ECD como base; (a) só como camada mínima documentada; (b) depois, só entrada, após PE-18. Ordem: plano → exportar lançamentos e saldos → importar lançamentos. | Análise | Médio |
| 5 | Regras de importação | Área de preparação (sem rascunho no modelo); tudo ou nada por lote; período encerrado = erro antecipado; chave (empresa, hash do arquivo, NUM_LCTO) via `chave_idempotencia` com prefixo reservado; plano só acrescenta por padrão, nunca apaga; de-para por empresa; histórico montado sem truncar; CC/participante advertidos; tipo E não importa por padrão. | Código verificado + ECD + hipóteses | Alto (confirmados) / médio (hipóteses) |
| 6 | Exportação | Mesmo leiaute, com relatório de conferência e hash; ISO-8859-1/CRLF; sem bloco J/termos/9999; nome e aviso deixam claro que não é ECD nem backup. | Análise + ECD | Médio |

## O que não consegui determinar

- Qual chave o sistema de referência usa para considerar um lançamento "já existente" na opção "importar somente inexistentes", e se a importação dele é atômica por arquivo.
- Tipo e formato exatos dos campos 2 a 7 do registro 6100 (colunas perdidas na extração do PDF); se o fornecedor alterou o leiaute depois de 2018.
- Se os ERPs usados pelos clientes do Fred exportam em algum dos dois leiautes — isso é pergunta para o Fred, não para manual.
- Se o Fred decidiu PE-18 (ler formato de terceiro). No repositório segue pendente (`docs/projeto/requisitos.md` l. 437).
- Mapeamento COD_NAT 04 (resultado) para receita × despesa, 05 (compensação) e 09 (outras): a ECD não distingue; precisa de regra nossa.
- Volume esperado de lançamentos por arquivo (PE-04, requisitos l. 423), que dimensiona a área de preparação.

Perguntas que só o Fred responde, para levar junto com este parecer: (1) importação de lançamentos fica invisível até efetivar ou aparece como "pendente" nas conferências; (2) tipo E da ECD: ignorar ou importar; (3) ampliar o histórico para além de 300 caracteres ou aceitar concatenação com advertência; (4) incluir cabeçalho 0000/I010 na exportação; (5) PE-18.

## Sources

- Página oficial do manual da ECD (lista de versões, ADE Cofis 01/2026, "não houve alteração de leiaute no AC 2025"): http://sped.rfb.gov.br/pasta/show/1569
- PDF oficial lido — Manual de Orientação do Leiaute 9 da ECD, atualização maio/2026: http://sped.rfb.gov.br/arquivo/download/7990 (item: http://sped.rfb.gov.br/item/show/7990)
- Diretório público dos manuais do sistema de referência (indicado pelo Fred): https://ftpdownload.dominiosistemas.com.br/manuais/ — arquivos `Domínio Contabilidade.pdf` (06/12/2018) e `Importação Padrão.pdf` (10/12/2018), nomes codificados em ISO-8859-1 no servidor
- Notícia secundária sobre o ADE Cofis 01/2026 (não usada como fonte de regra): https://documentacao.senior.com.br/exigenciaslegais/noticias/federal/2026/2026-01-13-sped-ecd-ato-declaratorio-cofis-n-01-2026-atualizacao-do-manual-da-ecd-leiaute-9-ja-esta-disponivel-para-2026
- Arquivos do repositório citados: `apps/contabilidade/models.py`, `apps/contabilidade/services.py`, `docs/projeto/requisitos.md`, `docs/projeto/mapa-funcional-contabil.md`, `docs/projeto/mapa-funcional-fiscal.md`, `docs/projeto/fontes-de-referencia.md`, `apps/livro_caixa/carne_leao_arquivos.py`
