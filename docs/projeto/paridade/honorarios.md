# Plano de paridade — Honorários

Plano detalhado, item por item, do que falta ao módulo Honorários do
DataLedger para cobrir a gestão e a cobrança dos honorários de um escritório
de contabilidade junto aos seus clientes, seguindo o pedido do Fred em
2026-09-27: *"separado por módulos [...] deve contemplar todas as funções que
você mapeou e descobriu nos manuais [...] ser claro e minucioso. E
exemplificar e referenciar e explicar item por item. Não tenha medo de fazer
um plano grande. O que não podemos é deixar lacunas. Pois caso outro dev
comece a codar, ele não se perca."*

Modelo de item, regras de uso do manual e convenções gerais:
[README.md](README.md). Etapa que originou este documento:
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md) — a DL-047
original deixou Honorários explicitamente fora ("que o Fred não pediu
agora"); este documento cumpre o pedido posterior, do mesmo dia, de estender
o mapa de paridade a Honorários.

## O que é o módulo, na rotina de um escritório

Honorários é o **financeiro do escritório em relação aos seus próprios
clientes** — distinto do financeiro *das empresas clientes*, que mora na
Contabilidade/Fiscal/Folha de cada uma delas (AGENTS.md §10: *"diferenciar o
financeiro do escritório do financeiro das empresas clientes"*). Cobre, em
sequência natural de uso:

1. **Cadastro do que se cobra** — o catálogo de serviços (eventos) e os tipos
   de contrato que o escritório oferece.
2. **Contrato por cliente** — valor mensal, vencimento, forma de reajuste, e
   regras de cobrança adicional quando o cliente ultrapassa um volume
   combinado (número de lançamentos, de funcionários na folha, de notas
   fiscais, faturamento do cliente).
3. **Cálculo mensal (faturamento)** — todo mês, o sistema soma o contrato, os
   eventos avulsos e fixos, os excedentes e os descontos, e gera as parcelas
   a receber de cada cliente.
4. **Cobrança** — emissão de boleto, documento de cobrança avulso ou remessa
   bancária (CNAB) para cobrança registrada; acompanhamento de inadimplência
   numa central de cobrança.
5. **Recebimento e baixa** — dar baixa na parcela, com juros, multa e
   desconto; adiantamento do cliente; renegociação de parcela em atraso.
6. **Nota fiscal de serviço do próprio escritório** — o escritório presta
   serviço de contabilidade e precisa emitir sua própria NFS-e (ou nota
   impressa) para os honorários recebidos, com as mesmas obrigações fiscais
   de qualquer prestador de serviço.
7. **Financeiro do escritório** — contas a pagar a fornecedores, pagamento de
   impostos do próprio escritório *e* dos clientes (quando o escritório paga
   adiantado e cobra de volta), conta corrente, conciliação bancária, fluxo
   de caixa.
8. **Integração com outros módulos** — a nota de honorários vira lançamento
   contábil (**em dois livros**: o do escritório e o do cliente, porque o
   escritório também escritura a contabilidade do cliente) e pode virar nota
   de entrada na Escrita Fiscal do cliente; o volume apurado em Fiscal e
   Folha pode gerar cobrança adicional (a integração citada em
   [fiscal.md, FIS-22](fiscal.md) é a mesma amarração, vista do lado Fiscal).
9. **Relatórios gerenciais** — faturamento, contas a receber e a pagar,
   inadimplência, fluxo de caixa, rentabilidade por contrato/cliente.

## Escopo

Este documento cobre **todo** o Honorários: parâmetros, cadastros de apoio
(cliente, fornecedor, evento, tipo de contrato, banco/agência/conta
financeira, categorias, históricos), contrato e cálculo mensal, faturamento,
cobrança (documento de cobrança, boleto, remessa/retorno CNAB, cheque),
recebimento, adiantamento, renegociação, central de cobrança, bloqueio de
inadimplente, financeiro do escritório (contas a pagar, pagamento de
impostos, conta corrente, conciliação, fluxo de caixa), integração contábil
dupla, nota fiscal de serviço do próprio escritório, integração com Escrita
Fiscal, integração com o volume de outros módulos, e os relatórios
gerenciais e documentos (contrato, carta de responsabilidade, carta de
cobrança).

Fora deste documento: Contabilidade, Fiscal, Folha, Patrimônio e Lalur têm
planos próprios (ver [README.md](README.md)) — aqui eles só aparecem como
**dependência** ou **destino de integração**, nunca detalhados. Processos/
Paralegal também tem plano próprio (ainda não escrito); os pontos em que o
manual de Honorários toca "Domínio Processos" (conclusão de atividade,
protocolos) aparecem só como dependência externa.

## Fontes

- Manual de rotina do sistema de referência (Domínio Honorários, versão
  10.1A-12, 751 páginas) — **apenas como referência de rotina**, nunca como
  fonte normativa. Nenhum trecho copiado; nenhum arquivo do manual entra
  neste repositório ([fontes-de-referencia.md](../fontes-de-referencia.md)).
  As páginas citadas em cada item correspondem exatamente ao marcador
  `PAGINA N/751` do arquivo de referência (conferido: o rodapé impresso do
  manual usa a mesma numeração).
- [mapa-funcional-contabil.md](../mapa-funcional-contabil.md) — em especial a
  seção "O histórico é modelo, não texto" e "Dois momentos, não um" (prévia
  de lançamento antes de efetivar), reaproveitadas aqui porque Honorários
  repete exatamente os dois padrões, em dobro (escritório e cliente).
- [fiscal.md](fiscal.md), item FIS-22 "Integração com Honorários" — o lado
  Fiscal da integração de cobrança por volume/valor apurado, detalhada aqui
  do lado Honorários (HON-38).
- [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) — as
  três classes de documento (conferência, demonstração, livro); nenhum
  relatório de Honorários é livro ou demonstração contábil — mas o
  **contrato**, o **boleto** e a **NFS-e** são "o documento entregue ao
  cliente", que o AGENTS.md §3.1 classifica como **nível 1 de risco** (o
  dinheiro e o livro), mesmo não sendo demonstração contábil.
- [requisitos.md](../requisitos.md), [backlog.md](../backlog.md),
  [decisoes.md](../decisoes.md) — RC, BL e DE já confirmados que este plano
  reaproveita, citados item a item (destaque para DE-009, idempotência por
  chave explícita, e DE-010, arredondamento nunca silencioso).
- [DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md) — etapa que
  originou a série de planos de paridade.
- Código real em `apps/empresas/`, `apps/tenancy/` e `apps/contabilidade/`,
  lido para confirmar que **não existe** app de Honorários, e para descrever
  com exatidão as peças que este módulo precisa reaproveitar (`Empresa` como
  cliente do escritório, `Escritorio` como tenant, `criar_lancamento` e o
  fechamento de competência da Contabilidade).

## Convenções deste documento

- IDs `HON-01`, `HON-02`... em ordem de onda, não de importância.
- Cada item segue **exatamente** o modelo do [README.md](README.md): O que
  é, Exemplo, Referência de rotina, Fonte normativa, Situação no DataLedger,
  Depende de, Dados, Regras, Telas e documentos, Critérios de aceite, Não
  copiar/riscos, Perguntas.
- Valor monetário sempre em `Decimal`, nunca `float` (AGENTS.md §10). Todos
  os exemplos usam números **sintéticos**: um cliente fictício "Comércio
  Exemplo Ltda.", um contrato de R$ 1.200,00/mês, nunca dado real de cliente
  do Fred.
- Alíquota, índice, prazo, fórmula ou leiaute que este documento não
  confirmou em fonte oficial aparece marcado **"a confirmar"** — nunca vira
  valor fixo no exemplo sem essa marcação. Isso vale sobretudo para: juros e
  multa de mora (o exemplo usa um percentual ilustrativo, a confirmar no
  contrato e no Código Civil), índice de reajuste (a confirmar qual índice o
  escritório usa), retenção na fonte sobre a nota de honorários (a confirmar
  alíquota e enquadramento).
- "Referência de rotina" cita **página do manual**, nunca texto dele. O
  manual é material de terceiro, de versão 10.1A-12, e **não está neste
  repositório**.
- "O cliente do escritório é a `Empresa`, o escritório é o `Escritorio`
  (tenant)" — confirmado em `apps/empresas` e `apps/tenancy`. Honorários
  **não** cria um segundo cadastro de empresa: o "Cliente" deste módulo é
  sempre uma referência a `Empresa` (cliente fixo) ou, quando não houver
  cadastro completo, um registro leve de cliente "eventual" (ver HON-02).

## Estado atual medido no código (2026-09-27)

Não existe `apps/honorarios/` nem qualquer modelo, serviço, tela ou rota
relacionada a contrato, evento, faturamento, cobrança, boleto, NFS-e do
escritório ou financeiro do escritório. Confirmado por `ls apps/` (apenas
`accounts`, `auditoria`, `contabilidade`, `core`, `documentos`, `empresas`,
`fiscal`, `livro_caixa`, `tenancy`) e pela busca por "honor" nos módulos
existentes, que não retorna nenhum resultado de código, só menções em
comentário e documentação apontando para este módulo como trabalho futuro
(`apps/tenancy/models.py`, docstring de `Escritorio`; `apps/empresas/`
inexistente referência a honorários). `docs/agents/estado.md` já lista
Honorários entre os módulos "não existe".

O que **já existe** e que este módulo deve reaproveitar, não duplicar:

| Peça | Onde está | O que Honorários reaproveita |
| --- | --- | --- |
| `Escritorio` (tenant, isolamento) | `apps/tenancy/models.py` | Todo dado de Honorários pertence a um `Escritorio`, nunca cruza entre escritórios |
| `Empresa` (cliente do escritório) | `apps/empresas/models.py` | O "Cliente" fixo de Honorários é uma `Empresa`; nenhum cadastro de empresa duplicado |
| `Lancamento`, `criar_lancamento`, fechamento/reabertura de competência | `apps/contabilidade/services.py`, `models.py` | A integração contábil (HON-33) grava lançamento pela mesma API, nunca grava direto na tabela |
| Modelo de histórico contábil com variáveis (decisão registrada em [mapa-funcional-contabil.md](../mapa-funcional-contabil.md#o-histórico-é-modelo-não-texto)) | ainda não implementado, mas já é decisão do projeto | HON-08 reaproveita o **mesmo desenho**, não inventa um segundo |
| Identificação do emitente / timbre em documento impresso | `apps/tenancy/models.py` (`linhas_do_timbre`) | Contrato, boleto e recibo de Honorários usam o mesmo timbre do escritório |

Conclusão medida, não presumida: **o módulo inteiro está por fazer**, mas a
fundação de isolamento, cadastro de empresa e motor contábil já existe e deve
ser reaproveitada — nenhum destes cinco itens nasce dentro de Honorários.

## Inventário completo

### Funções, por área

| Área | Função | Páginas do manual | ID |
| --- | --- | --- | --- |
| Parâmetros | Geral, avisos de vencimento, faturamento, recebimento, renegociação, impostos retidos, contabilidade, fluxo de caixa, notas fiscais/NFS-e, escrita fiscal, categorias, bloqueio | 68-115 | HON-01 |
| Cadastro | Cliente (fixo/eventual), guias Geral/Contabilidade/Escrita Fiscal/Cobrança/Opção | 128-154 | HON-02 |
| Cadastro | Fornecedor | 154-161 | HON-03 |
| Cadastro | Evento (catálogo de serviços/itens cobráveis, unidade, base de impostos) | 161-168 | HON-04 |
| Cadastro | Tipo de contrato (periodicidade, forma de reajuste) | 168-170 | HON-05 |
| Cadastro | Banco, Agência, Conta Financeira (dados de boleto/CNAB) | 194-204 | HON-06 |
| Cadastro | Categorias de contas a receber e a pagar | 112-113, 205-209 | HON-07 |
| Cadastro | Históricos e Históricos Contábeis (modelo com variáveis) | 204, 214-227 | HON-08 |
| Controle | Fechamento de período | 115-116 | HON-09 |
| Cadastro | Contrato (dados gerais, vigência, valor) | 170-173, 185-193 | HON-10 |
| Cadastro | Eventos Fixos e Adicional Anual do contrato | 180-185 | HON-11 |
| Cadastro | Excedentes de Contrato (avisos e cálculo por volume) | 173-180 | HON-12 |
| Movimento | Lançamento Mensal de eventos | 299-306 | HON-13 |
| Movimento | Lançamento Fixo de eventos | 306-309 | HON-14 |
| Movimento | Lançamentos em Grupo e de Descontos | 309-318 | HON-15 |
| Processo | Faturamento (motor de cálculo mensal) | 286-298 | HON-16 |
| Utilitário | Reajuste de Contratos (individual e em grupo) | 692-699 | HON-17 |
| Utilitário | Reajuste de Evento Fixo | 700-703 | HON-18 |
| Processo | Documentos de Cobrança (emissão/reemissão) | 455-462 | HON-19 |
| Processo | Boletos (emissão/reemissão), cadastro Dados Boletos | 198-202, 445-455 | HON-20 |
| Utilitário | Cobrança Registrada (remessa CNAB), Importação de Boletos Recebidos (retorno) | 202-204, 704-717 | HON-21 |
| Movimento | Recebimentos (individual e em grupo), Histórico de Parcelas | 325-395 | HON-22 |
| Processo | Manutenção de Cheques Recebidos | 430-432 | HON-23 |
| Movimento | Adiantamentos | 357-363 | HON-24 |
| Movimento | Renegociações, Alteração de Vencimento | 363-395 | HON-25 |
| Utilitário | Central de Cobrança (ocorrências, retorno) | 263, 649-652 | HON-26 |
| Controle/Utilitário | Bloqueio de Clientes (parâmetro) e Desbloquear Clientes Inadimplentes | 113-115, 718-721 | HON-27 |
| Movimento | Contas a Pagar (à vista e a prazo), Central de Pagamentos | 396-430, 652-661 | HON-28 |
| Processo | Pagamento de Impostos (do escritório e do cliente) | 471-484 | HON-29 |
| Consulta | Conta Corrente Escritório e Conta Corrente Cliente | 462-467 | HON-30 |
| Processo | Lançamentos de Extrato Bancário, Conciliação de Extrato Bancário, Configuração de Importação de Extrato | 227-230, 467-471, 707-709 | HON-31 |
| Consulta/Relatório | Fluxo de Caixa (projetado/realizado), Lançamentos Orçados | 95-97, 299-325, 556-565 | HON-32 |
| Processo | Integração Contábil (escritório e cliente) | 486-489 | HON-33 |
| Utilitário | Regerar Lançamentos Contábeis | 709-710 | HON-34 |
| Processo | NFS-e: Gerar RPS, Consulta de RPS, Consulta de Situação de Lote, Consulta de NFS-e | 438-445 | HON-35 |
| Processo | Notas Fiscais: Emissão, Reemissão, Cancelamento | 432-437, 682-688 | HON-36 |
| Processo | Integração Escrita Fiscal (notas de saída do escritório / entrada no cliente) | 490-498 | HON-37 |
| Integração | Evento vinculado a valor/volume apurado em Fiscal e Folha | 81-84, 161-163 (Honorários) + ref. [fiscal.md](fiscal.md) FIS-22 | HON-38 |
| Utilitário | Consulta de Faturamento (F5), Consulta de Cliente (F6) | 641-648 | consultas, sem ID próprio (ver HON-13/HON-22) |
| Cadastro | Modelos de Documentos (motor de mala direta) | 721-727 | HON-47 |

### Relatórios, por grupo

| Grupo | Conteúdo | Classe | Páginas | ID |
| --- | --- | --- | --- | --- |
| Faturamento | Relação, Extrato, Resumo, Por Período, Pendências, Avisos de Excedentes | Conferência | 503-513 | HON-39 |
| Contas a Receber | Relação, Por Período, Extrato por Cliente, Previsão de Recebimento, Relação de Recebimentos, Adiantamentos, Renegociações, Lançamentos de Eventos, Notas Fiscais Emitidas, RPS Emitidos, Boletos Emitidos, Cheques Recebidos, Documentos de Cobrança Emitidos | Conferência | 514-544 | HON-40 |
| Contas a Pagar | Relação, Por Período, Relação de Pagamentos, Cheques Pagos | Conferência | 545-554 | HON-41 |
| Gráficos | Evolução e Composição de Faturamento/Contas a Receber/Contas a Pagar | Conferência | 588-597 | HON-42 |
| Contratos | Emissão (documento a partir de modelo), Relação, Distrato | Documento ao cliente / Conferência | 597-603 | HON-43 |
| Carta de Responsabilidade da Administração | Documento anual assinado pelo cliente e pelo contador | Documento ao cliente | 603-605 | HON-44 |
| Outros | Carta de Cobrança, Correspondência, Etiqueta, Declaração Anual de Quitação de Débitos, Clientes Bloqueados | Documento ao cliente / Conferência | 608-615 | HON-45 |
| Reajustes e Cadastrais | Reajuste de Contratos, Reajuste de Eventos Fixos, e a relação de cada cadastro (empresas, clientes, fornecedores, eventos, tipos de contrato, bancos, agências, contas financeiras, históricos, categorias, contas contábeis, ocorrências, feriados, índices) | Conferência | 606-608, 615-637 | HON-46 |

## Mapa de dependências e ordem (ondas)

A cadeia de dependência é quase linear: sem catálogo de serviço não há
contrato; sem contrato não há cálculo mensal; sem cálculo mensal não há
cobrança nem recebimento; sem recebimento não há integração contábil nem
fluxo de caixa correto. A emissão de nota fiscal e a integração de volume com
outros módulos dependem de tudo isso já funcionando.

```
Parâmetros do módulo + cadastros de apoio (cliente, fornecedor, evento,
tipo de contrato, banco/agência/conta, categorias, históricos)
  → Contrato por cliente (com eventos fixos, adicional anual, excedente)
    → Cálculo mensal (faturamento) — o motor central
      → Cobrança (documento, boleto, remessa CNAB)
        → Recebimento, baixa, adiantamento, renegociação
          → Central de cobrança e bloqueio de inadimplente
      → Financeiro do escritório (contas a pagar, pagamento de impostos,
        conta corrente, conciliação, fluxo de caixa) — em paralelo,
        mesma fundação de conta financeira
        → Integração contábil (dupla: escritório e cliente)
          → Nota fiscal de serviço do escritório
            → Integração com Escrita Fiscal (nota de saída/entrada)
      → Integração com volume de Fiscal/Folha (cobrança por apuração)
        → Relatórios gerenciais e documentos
```

| Onda | Conteúdo | Itens | Por que nesta ordem |
| --- | --- | --- | --- |
| 1 | Fundação: parâmetros e cadastros de apoio | HON-01–HON-09 | Nada em Honorários calcula sem parâmetro, cliente, evento, tipo de contrato e conta financeira cadastrados |
| 2 | Contrato e cálculo mensal | HON-10–HON-15 | O contrato é o que o escritório vende; sem ele não há o que faturar |
| 3 | Faturamento | HON-16–HON-18 | O motor que transforma contrato + lançamentos em parcela a receber — o coração do módulo |
| 4 | Cobrança e recebimento | HON-19–HON-27 | É o que dá valor prático ao faturamento: cobrar e receber, e tratar quem não paga |
| 5 | Financeiro do escritório | HON-28–HON-32 | Roda em paralelo à cobrança, sobre a mesma fundação de conta financeira e conciliação |
| 6 | Integração contábil | HON-33–HON-34 | Só faz sentido depois de haver faturamento e recebimento reais para contabilizar |
| 7 | Nota fiscal de serviço do escritório | HON-35–HON-37 | Depende do faturamento definido (valor e cliente) para saber o que faturar em nota |
| 8 | Integração com volume de outros módulos | HON-38 | Depende de Fiscal e Folha terem apuração pronta (planos próprios) — é a peça que só fecha quando os dois lados existirem |
| 9 | Relatórios gerenciais e documentos | HON-39–HON-46 | Relatórios de conferência, dependem dos dados já existirem |
| 10 | Plataforma de documentos | HON-47 | Usado por HON-43/HON-44/HON-45, mas é uma peça de infraestrutura maior — pode ser adiada para um gerador mais simples na primeira entrega |

Total: **47 itens de escopo ativo** (HON-01 a HON-47) e **12 itens fora de
escopo ou dependentes de confirmação** (HON-80 a HON-91).

## Onda 1 — Fundação: parâmetros e cadastros de apoio

### HON-01 — Parâmetros do módulo Honorários

**O que é.** O cadastro único, por escritório, que liga tudo o mais: dias de
vencimento permitidos, se calcula juros/multa automaticamente no
recebimento, quais impostos o escritório retém nas próprias notas (IRRF,
INSS Retido, ISS Retido, CRF — a retenção combinada de PIS/COFINS/CSLL),
como a integração contábil se comporta, e se o escritório bloqueia o acesso
de cliente inadimplente aos demais módulos.
**Exemplo.** O escritório "Fred Assessoria Contábil" configura: dias de
vencimento permitidos = {5, 10, 15, 20}; calcular juros de mora de 1% ao mês
e multa de 2% no recebimento em atraso (**percentuais ilustrativos, a
confirmar no contrato-padrão do escritório e no Código Civil**); reter CRF
(4,65%) e ISS retido nas próprias notas quando o cliente for optante pelo
regime de retenção; bloquear acesso do cliente com 2 parcelas em aberto.
**Referência de rotina.** Manual Domínio Honorários, menu Controle, janela
Parâmetros: guia Geral e Avisos de Vencimento (p. 68-76), guia Faturamento
(p. 76-78), guia Recebimento (p. 78-80), guia Renegociação (p. 80-81), guia
Impostos (p. 81-84), guia Contabilidade (p. 84-95), guia Fluxo de Caixa
(p. 95-97), guia Notas Fiscais/NFS-e (p. 97-108), guia Escrita Fiscal
(p. 108-112), guia Categorias (p. 112-113), guia Bloqueio (p. 113-115).
**Fonte normativa.** Não há norma para o cadastro de parâmetro em si. As
retenções que ele liga/desliga têm fonte própria, citada nos itens que as
implementam (HON-19, HON-29, HON-35): IRRF sobre serviço profissional
(Decreto 9.580/2018, arts. 714-716 — **a confirmar dispositivo e valor
mínimo de retenção**); CRF — retenção combinada de CSLL/COFINS/PIS —
(Lei 10.833/2003, art. 30 — **a confirmar se o serviço de contabilidade do
próprio escritório se enquadra e qual o valor mínimo vigente, hoje citado
pelo mercado como R$ 215,05, não confirmado em fonte oficial por este
documento**); ISS retido (LC 116/2003, art. 6º, e legislação municipal — **a
confirmar por município**); juros e multa de mora (Código Civil, arts. 406 e
407, e o que o contrato do escritório fixar).
**Situação no DataLedger.** **Não existe.**
**Depende de.** `Escritorio` (`apps/tenancy`) como dono do parâmetro.
**Dados.** Dias de vencimento permitidos; flags de cálculo automático de
juros/multa; percentuais de juros/multa padrão; flags de retenção (IRRF,
INSS Retido, ISS Retido, CRF/PIS/COFINS/CSLL) com valor mínimo de retenção
por imposto; fato gerador de cada retenção (emissão ou recebimento); conta e
histórico contábil padrão por tipo de lançamento (recebimento, pagamento,
adiantamento, desconto, cada retenção); flags de bloqueio de inadimplente
com limite (nº de parcelas ou nº de dias).
**Regras.** Parâmetro é **por escritório**, nunca compartilhado entre
tenants; alterar percentual padrão de juros/multa não recalcula recebimento
já baixado (imutabilidade de cobrança efetivada); toda alíquota de retenção
usada em cálculo carrega, na memória de cálculo, a fonte e vigência aplicada
(AGENTS.md §10) — nunca cálculo com valor implícito sem essa referência.
**Telas e documentos.** Tela de cadastro de parâmetros (classe
conferência/cadastro), não impressa isoladamente.
**Critérios de aceite.** Escritório sem parâmetro cadastrado não consegue
gerar faturamento com juros/multa/retenção automáticos (recusa explícita,
nunca cálculo com valor padrão inventado); mudar o percentual de juros não
altera recebimento já gravado.
**Não copiar/riscos.** O manual lista dezenas de sub-guias por banco e por
código de retenção específico de nicho (agropecuário, SCP) — implementar só
o que a carteira real do Fred usa (ver Perguntas).
**Perguntas.** O escritório do Fred hoje retém algum imposto nas próprias
notas de honorários (IRRF, ISS retido, CRF)? Cobra juros/multa de clientes
em atraso, e com que percentual? Bloqueia acesso de cliente inadimplente a
alguma coisa hoje (mesmo que manualmente)?

### HON-02 — Cliente do escritório (fixo e eventual)

**O que é.** Quem paga honorários ao escritório. Um cliente **fixo** é
sempre uma `Empresa` já cadastrada (a mesma que aparece em Fiscal/Folha/
Contabilidade); um cliente **eventual** é alguém que usa o escritório
esporadicamente (ex.: uma pessoa física pedindo uma declaração avulsa) e
pode não ter `Empresa` cadastrada. É este cadastro que carrega o endereço de
cobrança (quando diferente do cadastral), avalista, tipo de cobrança
preferido (documento avulso, boleto, cobrança registrada) e a configuração
de integração contábil por cliente.
**Exemplo.** "Comércio Exemplo Ltda." (CNPJ sintético 11.222.333/0001-44) é
cliente fixo, vinculado à `Empresa` já cadastrada em `apps/empresas`; tipo de
cobrança = boleto; endereço de cobrança = mesmo da empresa.
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Clientes: guia Geral (p. 128-131), guia Observações (p. 131), guia
Contabilidade (Escritório/Cliente, p. 131-145), guia Escrita Fiscal
(p. 145-147), guia Cobrança (p. 148-153), guia Opção (p. 153-154).
**Fonte normativa.** Não há norma para o cadastro em si. O CNPJ/CPF em si já
é tratado pelo cadastro de `Empresa` (DL-011/DL-038).
**Situação no DataLedger.** **Não existe.** `Empresa` (`apps/empresas`)
existe e é o que este cadastro referencia para cliente fixo.
**Depende de.** `Empresa`, `Escritorio`.
**Dados.** Tipo (fixo/eventual); referência a `Empresa` (fixo) ou dados
mínimos digitados (eventual: nome, documento, endereço); endereço de
cobrança (próprio ou "mesmo da empresa"); avalista; tipo de cobrança
preferido; conta financeira sugerida para recebimento; autorização de débito
em conta; configuração de desconto por pontualidade (ver HON-15); conta
contábil do cliente no plano de contas do escritório (para a integração
dupla, HON-33); conta e histórico de honorários a pagar, pagamento,
adiantamento e cada retenção **no plano de contas do próprio cliente**
(porque o escritório também escritura a contabilidade dele).
**Regras.** Um cliente eventual nunca é confundido com um cliente fixo de
outra empresa; alteração de dados cadastrais (documento, endereço) é
rastreável (trilha), nunca sobrescrita silenciosa (mesmo padrão de FIS-04);
isolamento por escritório verificado no servidor.
**Telas e documentos.** Cadastro de cliente (classe conferência/cadastro).
**Critérios de aceite.** Um contrato só pode ser cadastrado para cliente
fixo (regra explícita do manual, p. 170: *"o sistema permitirá cadastrar
contratos apenas para clientes fixos"*, reproduzida aqui como regra de
domínio, não como texto do manual); cliente eventual pode receber
lançamento avulso, nunca contrato.
**Não copiar/riscos.** Nenhum copiado.
**Perguntas.** O Fred atende clientes "eventuais" (pessoa física ou serviço
avulso sem contrato mensal), ou toda a carteira é cliente fixo com
contrato?

### HON-03 — Fornecedor do escritório

**O que é.** Cadastro de quem o escritório **paga** — distinto do cliente,
que é quem **paga o escritório**. Usado nos lançamentos de contas a pagar
(HON-28).
**Exemplo.** Fornecedor "Papelaria Exemplo Ltda." (CNPJ sintético), usado em
um lançamento de contas a pagar de material de expediente.
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Fornecedores (p. 154-161), incluindo o botão Alterações (trilha de mudança
cadastral, p. 160-161).
**Fonte normativa.** Não há norma para o cadastro em si.
**Situação no DataLedger.** **Não existe.**
**Depende de.** `Escritorio`.
**Dados.** Nome, tipo de inscrição (CNPJ/CPF/CEI/outros), número, endereço,
inscrições estadual/municipal, conta contábil, dados de agropecuário/
contribuinte ICMS (só relevante se o fornecedor emitir NF-e, caso raro para
um escritório de contabilidade).
**Regras.** Alteração de CNPJ/razão social/endereço gera registro de trilha
com a data da alteração, nunca sobrescrita silenciosa (mesmo padrão de
FIS-04); isolamento por escritório.
**Telas e documentos.** Cadastro (classe conferência/cadastro).
**Critérios de aceite.** Alterar CNPJ de um fornecedor gera um registro de
trilha consultável, com valor anterior e novo.
**Não copiar/riscos.** O cadastro do manual tem campos de ICMS/SPED
Fiscal (contribuinte, agropecuário) pensados para fornecedor que emite NF-e
de mercadoria — pouco provável para o fornecedor típico de um escritório de
contabilidade (papelaria, limpeza, TI). Implementar o mínimo necessário
primeiro.
**Perguntas.** Nenhuma bloqueante.

### HON-04 — Evento: catálogo de serviços e itens cobráveis

**O que é.** O cadastro mais importante da fundação — cada linha cobrável
que pode aparecer numa parcela: os honorários do contrato em si, uma
despesa reembolsável, uma taxa, um imposto pago pelo escritório e repassado.
Cada evento define **como** o valor é calculado (valor fixo, quantidade ×
referência, percentual sobre o contrato, ou fórmula) e **se** ele soma na
base de algum imposto retido (IRRF, ISS, CRF, INSS Retido, ISS Retido).
**Exemplo.** Evento "Honorários Contábeis Mensais" (unidade = Valor,
categoria = Receitas, soma na base do ISS com alíquota **a confirmar por
município** e na base do CRF quando aplicável). Evento "Taxa por funcionário
excedente" (unidade = Quantidade, referência = R$ 15,00/funcionário — **valor
sintético, decisão de produto do escritório, não norma**).
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Eventos: guia Geral (p. 161-163), guia Lançamentos Mensais (p. 163-166), guia
Contabilidade (p. 166-167), guia Escrita Fiscal (p. 167-168).
**Fonte normativa.** Não há norma para o cadastro em si. As alíquotas que ele
referencia (ISS, IRRF, CRF) têm fonte própria — ver HON-01.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-01 (parâmetros de retenção que o evento referencia),
HON-07 (categoria).
**Dados.** Código, descrição, unidade (valor/quantidade/percentual sobre
contrato/fórmula), referência (valor unitário ou percentual), categoria
(a receber ou a pagar), flags "soma na base" por imposto retido com
alíquota, configuração de lançamento mensal padrão (vencimento fixo ou
conforme contrato, se fatura com o contrato ou separado), configuração
contábil (conta de receita do escritório, conta de pagamento antecipado a
terceiros).
**Regras.** Evento de categoria "Impostos/Taxas/Outros" só habilita "pago
pelo escritório" quando esse for o seu propósito (repasse); mudar a
configuração de um evento não altera lançamento de competência já
faturada (efetivado é imutável, corrige-se por evento de ajuste rastreável).
**Telas e documentos.** Cadastro (classe conferência/cadastro), usado em
todo lançamento e contrato.
**Critérios de aceite.** Um lançamento sem evento é recusado; a base de cada
imposto retido bate com a soma dos eventos marcados para aquele imposto.
**Não copiar/riscos.** Nenhum copiado; não inventar alíquota de nenhum
imposto retido citado no cadastro do evento — vem de HON-01/fonte oficial.
**Perguntas.** Quais eventos o escritório do Fred realmente cobra hoje, além
dos honorários mensais (reembolso de despesa, taxa por CT-e emitido, taxa
por funcionário)? Sem essa lista, o catálogo nasce vazio ou especulativo.

### HON-05 — Tipo de contrato

**O que é.** O cadastro que define a **periodicidade de faturamento** (ex.:
mensal) e a **forma de reajuste** (percentual anual fixo, por índice, em
data-base) que um contrato vai seguir. É escolhido uma vez, no cadastro do
contrato (HON-10).
**Exemplo.** Tipo "Honorários Contábeis PJ Mensal" — periodicidade mensal,
reajuste anual, indexador = índice (ex.: IPCA, **a confirmar qual índice o
escritório usa — não presumir**), mês-base = janeiro.
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Tipos de Contrato (p. 168-170).
**Fonte normativa.** Não há norma sobre o tipo de contrato em si. O
**índice** de reajuste, quando usado, tem fonte oficial própria por índice
(ex.: IPCA é do IBGE; IGP-M é da FGV) — **a confirmar qual índice o
escritório do Fred usa antes de implementar cálculo por índice**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** Nada dentro de Honorários.
**Dados.** Nome, periodicidade de faturamento, tipo de reajuste (percentual/
valor fixo/índice), mês-base (quando "data-base"), indexador e índice
específico (quando "índice"), flag de proporcionalidade à data de início do
contrato.
**Regras.** O sistema recusa gravar um tipo de contrato cuja periodicidade
de reajuste seja **menor** que a periodicidade de faturamento (ex.: reajuste
mensal com faturamento anual não faz sentido) — regra de consistência
citada no manual (p. 170) e reproduzida aqui como validação de domínio.
**Telas e documentos.** Cadastro (classe conferência/cadastro).
**Critérios de aceite.** Tentar gravar reajuste mais frequente que o
faturamento é recusado com mensagem explícita.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Ver HON-10 — a pergunta real (qual índice, qual
periodicidade) é do contrato, não do tipo.

### HON-06 — Banco, Agência e Conta Financeira do escritório

**O que é.** Os três cadastros de apoio bancário: o banco (tabela de códigos
da câmara de compensação do Banco Central), a agência com a qual o
escritório mantém conta, e a conta financeira em si — com os dados
específicos de emissão de boleto (carteira, convênio, cedente, faixa de
"nosso número") que HON-20 e HON-21 vão usar.
**Exemplo.** Banco "001 - Banco do Brasil" (código oficial da câmara de
compensação — **confirmado**, é tabela pública do Banco Central, não
inventada); Agência "1234-5"; Conta Financeira "Conta Honorários", tipo
Bancária, carteira e cedente conforme contrato do escritório com o banco.
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Bancos (p. 194-195), Agências (p. 195-196), Contas Financeiras: guia Geral
(p. 196-198), guia Dados Boletos (p. 198-202), guia Nosso Número (p. 201-202),
guia Cobrança Registrada (p. 202-204).
**Fonte normativa.** O código do banco é o número oficial da câmara de
compensação do Banco Central do Brasil (**confirmado**, é tabela pública).
Os campos específicos de emissão de boleto (carteira, convênio, tipo de
remessa CNAB 240/400) seguem o **leiaute FEBRABAN de cobrança bancária**,
confirmado como padrão existente na praça, mas **a versão exata e os campos
específicos por banco precisam ser confirmados com o banco do escritório
antes de qualquer implementação de arquivo de remessa** (ver HON-21).
**Situação no DataLedger.** **Não existe.**
**Depende de.** Nada dentro de Honorários (pode reaproveitar cadastro
bancário genérico do escritório, se um existir — mesma pergunta de FIS-12).
**Dados.** Banco (código, nome); Agência (código, dígito, dados de
cooperativa de crédito quando aplicável); Conta Financeira (tipo bancária/
caixa/cheque, banco, agência, conta, dígito, conta contábil vinculada,
carteira, cedente, dígito do cedente, espécie de documento, faixa de "nosso
número", flags de cobrança registrada).
**Regras.** Conta financeira é dado sensível (financeiro do escritório),
mesma proteção do AGENTS.md §11; a faixa de "nosso número" nunca gera
duplicidade entre dois boletos (controle de numeração sequencial por
conta).
**Telas e documentos.** Cadastro (classe conferência/cadastro).
**Critérios de aceite.** Dois boletos da mesma conta financeira nunca saem
com o mesmo "nosso número".
**Não copiar/riscos.** O manual tem dezenas de campos condicionais
específicos por banco (cada banco com sua própria regra de carteira, tipo
de remessa, aceite) — implementar primeiro só o banco que o escritório do
Fred realmente usa (ver Perguntas de HON-20/HON-21); não replicar a matriz
inteira de bancos sem demanda medida.
**Perguntas.** Qual banco o escritório do Fred usa hoje (ou pretende usar)
para emitir boleto e enviar remessa? Sem essa resposta, os campos
condicionais por banco não podem ser priorizados.

### HON-07 — Categorias de contas a receber e a pagar

**O que é.** Um agrupamento gerencial (não contábil) de eventos e
lançamentos financeiros, usado para relatório e para o fluxo de caixa —
ex.: "Receitas", "Outras Receitas", "Impostos/Taxas/Outros" no lado a
receber; "Despesas Administrativas", "Impostos e Encargos", "Funcionários"
no lado a pagar.
**Exemplo.** Categoria a receber "Honorários Contábeis" (classificação
"Receitas", não totalizadora); categoria a pagar "Impostos e Encargos".
**Referência de rotina.** Manual Domínio Honorários, guia Categorias dos
Parâmetros (p. 112-113); menu Arquivos, Categorias de Contas a Receber
(p. 205-207) e Categorias de Contas a Pagar (p. 207-209).
**Fonte normativa.** Não há norma — é organização gerencial interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** Nada dentro de Honorários.
**Dados.** Código, nome, classificação (receitas/outras receitas/impostos-
taxas-outros para a receber; despesa/imposto-encargo/funcionário para a
pagar), flag totalizadora/não totalizadora.
**Regras.** Um evento (HON-04) só referencia categoria "não totalizadora"
(regra citada no manual, p. 162, reproduzida como validação de domínio).
**Telas e documentos.** Cadastro (classe conferência/cadastro).
**Critérios de aceite.** Tentar vincular evento a categoria totalizadora é
recusado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-08 — Histórico e histórico contábil (modelo com variáveis)

**O que é.** O mesmo padrão já decidido para a Contabilidade — histórico não
é texto fixo, é um **modelo com variáveis** que o sistema resolve no
momento do lançamento (competência, nome do cliente, número do documento).
Honorários tem **dois** tipos: o histórico "comercial" (usado em recibo,
carta) e o histórico contábil (usado na integração dupla, HON-33).
**Exemplo.** Modelo "Recebimento de honorários referente à competência
{competencia}, cliente {nome_cliente}", resolvido para "Recebimento de
honorários referente à competência 09/2026, cliente Comércio Exemplo Ltda.".
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos,
Históricos (p. 204) e Históricos Contábeis com Complemento por variável
(p. 214-227).
**Fonte normativa.** Não há norma para o texto do histórico.
**Situação no DataLedger.** **Não existe** — decisão de arquitetura já
registrada para a Contabilidade
([mapa-funcional-contabil.md](../mapa-funcional-contabil.md#o-histórico-é-modelo-não-texto)),
reaproveitada aqui, não reinventada.
**Depende de.** Nada dentro de Honorários; compartilha o desenho com
Contabilidade e Fiscal (FIS-09).
**Dados.** Modelo de texto com placeholders; lista de variáveis disponíveis
por tipo de movimento (recebimento, pagamento, adiantamento, renegociação,
cada retenção).
**Regras.** Resolução de modelo nunca falha silenciosamente — variável sem
valor disponível vira texto explícito, nunca campo vazio sem explicação
(mesma regra de FIS-09).
**Telas e documentos.** Cadastro de modelo (classe cadastro), usado em toda
prévia de lançamento e em documento impresso.
**Critérios de aceite.** O mesmo modelo aplicado a dois clientes diferentes
produz dois textos coerentes e diferentes, cada um rastreável até os dados
de origem.
**Não copiar/riscos.** Nenhum — é decisão de arquitetura já tomada pelo
projeto, não texto do manual.
**Perguntas.** Nenhuma bloqueante.

### HON-09 — Fechamento de período do Honorários

**O que é.** O controle que impede lançamento de faturamento, recebimento ou
pagamento num período já fechado — o mesmo conceito que a Contabilidade já
implementa para competência, aplicado ao calendário de Honorários.
**Exemplo.** Setembro/2026 é fechado em 05/10/2026; uma tentativa de gerar
faturamento retroativo para setembro depois disso é recusada, exigindo
reabertura explícita.
**Referência de rotina.** Manual Domínio Honorários, menu Controle,
Fechamento (p. 115-116).
**Fonte normativa.** Não há norma específica para o fechamento do módulo de
honorários; é controle operacional que apoia a integridade da escrituração,
mesmo espírito do AGENTS.md §10 ("período encerrado exige controle explícito
para alteração ou reabertura").
**Situação no DataLedger.** **Não existe.** O padrão já existe na
Contabilidade (fechamento/reabertura de competência, `apps/contabilidade`) e
deve ser reaproveitado no desenho, não reinventado.
**Depende de.** Nada dentro de Honorários; mesmo padrão de Contabilidade.
**Dados.** Competência do fechamento atual, por escritório; histórico de
fechamentos e reaberturas com usuário e data (trilha).
**Regras.** Fechar um período não apaga nem recalcula lançamento existente,
só impede novo lançamento retroativo sem reabertura explícita; reabertura é
sempre rastreável (quem, quando, por quê).
**Telas e documentos.** Tela de controle (classe conferência).
**Critérios de aceite.** Faturamento de período fechado é recusado com
mensagem explícita; reabertura registra ator e motivo.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

## Onda 2 — Contrato e cálculo mensal

### HON-10 — Contrato de honorários

**O que é.** O acordo comercial entre escritório e cliente fixo: valor
mensal, dia de vencimento, vigência, tipo de contrato (periodicidade e forma
de reajuste). É o dado central que todo o restante do módulo lê.
**Exemplo.** Contrato da "Comércio Exemplo Ltda.": tipo "Honorários
Contábeis PJ Mensal" (HON-05); evento de honorários = "Honorários Contábeis
Mensais" (HON-04); início do contrato 02/2024; início do faturamento
09/2026; dia de vencimento = 10; valor do contrato = R$ 1.200,00 (**valor
sintético**); desconto por adimplência = 5% quando os últimos 3 meses foram
pagos em dia (**percentual e regra sintéticos, decisão de produto**).
**Referência de rotina.** Manual Domínio Honorários, menu Arquivos, opção
Contratos: guia Geral (p. 170-173), guia Contrato — modelo/emissão
(p. 185-190), guia Distrato (p. 190-192), Histórico de Contratos e Alterações
(p. 192-194).
**Fonte normativa.** Não há norma sobre o formato do contrato de prestação
de serviços contábeis em si — é livre pactuação entre as partes (Código
Civil, princípio da autonomia contratual). A profissão contábil em si é
regulada pelo Conselho Federal de Contabilidade, mas **não há norma
confirmada** que fixe cláusula obrigatória de contrato de honorários — **a
confirmar se o CFC exige alguma cláusula mínima antes de considerar isso
fechado**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-02 (cliente fixo — contrato só existe para cliente
fixo, regra do manual reproduzida aqui), HON-04 (evento de honorários),
HON-05 (tipo de contrato), HON-47 (modelo de documento, para emitir o
contrato impresso).
**Dados.** Cliente, tipo de contrato, evento de honorários, data de
emissão, início do contrato, dia de vencimento, início do faturamento, mês
de vencimento (no mesmo/após/no segundo mês), data de término (quando
determinado), valor do contrato e valor original (histórico de reajuste),
desconto por adimplência (percentual, meses considerados), situação
(ativo/inativo) com histórico de ativação/inativação.
**Regras.** Contrato só é cadastrado para cliente **fixo** (nunca eventual);
alterar o valor do contrato fora de um reajuste registrado (HON-17) precisa
do mesmo procedimento rastreável de correção do AGENTS.md §10, nunca edição
silenciosa; inativar contrato não apaga histórico de faturamento anterior;
o campo "valor original" nunca é sobrescrito por um reajuste — só o "valor
atual" muda, o original fica como prova.
**Telas e documentos.** Cadastro de contrato (classe conferência/cadastro);
documento impresso do contrato é HON-43 (classe documento entregue ao
cliente, nível 1 de risco).
**Critérios de aceite.** Contrato para cliente eventual é recusado; reajuste
altera "valor atual" e preserva "valor original"; contrato inativado não
gera faturamento novo, mas preserva o histórico de faturamento já feito.
**Não copiar/riscos.** O manual condiciona a mensagem de aviso de reajuste
a uma combinação específica de "início do contrato" + "início do
faturamento" + tipo de reajuste (exemplo do manual, p. 172) — reproduzir a
**lógica**, não o texto da mensagem.
**Perguntas.** O Fred usa contrato por tempo determinado ou indeterminado,
hoje? Usa desconto por adimplência? Qual o dia de vencimento padrão que ele
pratica?

### HON-11 — Eventos fixos e adicional anual do contrato

**O que é.** Duas formas de cobrar algo **além** do valor base do contrato,
de forma recorrente e programada: um "evento fixo" (ex.: uma taxa mensal de
sistema, cobrada junto com o contrato ou separada) e um "adicional anual"
(ex.: 13º de honorários, cobrado uma vez por ano, proporcional ou não à data
de início do contrato).
**Exemplo.** Evento fixo "Taxa de Sistema" de R$ 50,00/mês (**valor
sintético**), cobrado junto com o contrato, todos os meses. Adicional anual
"13º de Honorários" = 100% do valor do último faturamento, cobrado em
dezembro (**regra sintética, decisão comercial do escritório**).
**Referência de rotina.** Manual Domínio Honorários, guia Eventos Fixos
(p. 180-181) e guia Adicional Anual (p. 182-185) do cadastro de Contratos.
**Fonte normativa.** Não há norma — é decisão comercial do escritório com
cada cliente.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-10 (contrato), HON-04 (evento).
**Dados.** Evento vinculado, quantidade/valor, competência inicial e final
(quando encerrado), meses de faturamento, forma de cálculo do adicional
anual (percentual sobre contrato/valor informado/proporcional à data de
início), forma de considerar o valor de eventos fixos (último faturamento
ou média dos últimos N meses).
**Regras.** Um evento fixo encerrado não é faturado depois da competência
de encerramento; o adicional anual dividido entre vários meses soma
exatamente o valor total configurado, sem sobra nem falta de centavo
(arredondamento explícito, nunca silencioso, AGENTS.md §10).
**Telas e documentos.** Parte do cadastro de contrato (classe cadastro).
**Critérios de aceite.** Somar as parcelas do adicional anual dividido em
N meses bate exatamente com o valor configurado, para qualquer N.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O escritório do Fred cobra 13º de honorários ou taxa fixa
adicional (sistema, certificado digital) separada do valor-base do
contrato?

### HON-12 — Excedente de contrato: cobrança por volume

**O que é.** A regra que cobra um valor adicional quando o cliente
**ultrapassa** um volume combinado no contrato — é a peça que responde
diretamente ao exemplo do Fred: "cobrança adicional por número de
empregados na folha acima de 10". O manual permite configurar excedente por
número de lançamentos contábeis, número de lançamentos fiscais, horas
trabalhadas (por módulo), número de funcionários (ativos/demitidos/
contribuintes) e faturamento do cliente.
**Exemplo.** O contrato da "Comércio Exemplo Ltda." prevê até 10
funcionários ativos na folha; a partir do 11º, cobra-se um evento "Taxa por
Funcionário Excedente" de R$ 15,00 por funcionário além do limite (**valor
sintético, decisão comercial**). Em setembro/2026 a empresa tem 13
funcionários ativos: o faturamento gera automaticamente um aviso e um
lançamento adicional de R$ 45,00 (3 × R$ 15,00), vinculado ao evento
correspondente.
**Referência de rotina.** Manual Domínio Honorários, guia Excedentes de
Contrato: Avisos (p. 173-174), Número de Lançamentos (contábeis e fiscais,
p. 174-175), Horas Trabalhadas por módulo (p. 175-176), Funcionários
(p. 176-177), Faturamento do Cliente (p. 177-178), guia Cálculo
(p. 178-180).
**Fonte normativa.** Não há norma — é modelo de precificação do escritório
com seu cliente, decisão de produto (AGENTS.md: "não há — decisão de
produto").
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-10 (contrato), HON-04 (evento de excedente); a **fonte
da contagem** depende dos módulos de origem — número de funcionários da
Folha (plano próprio, ainda não escrito), número de lançamentos da
Contabilidade (já existe), número de lançamentos fiscais do Fiscal (plano
próprio, `fiscal.md`).
**Dados.** Limite contratado por critério (nº de lançamentos contábeis/
fiscais, horas por módulo, nº de funcionários, faturamento do cliente);
evento a lançar quando exceder; valor do excedente; competência de início
e de encerramento do cálculo de excedente; forma de contagem (ex.:
funcionários ativos do mês, demitidos do mês, ou contribuintes).
**Regras.** O cálculo de excedente nunca conta duas vezes a mesma origem
(ex.: um lançamento contábil não conta como "manual" e "gerado por outro
módulo" ao mesmo tempo); o aviso de excedente é gerado **antes** de
efetivar o faturamento, para conferência (mesmo princípio de "prévia antes
de efetivar" do AGENTS.md e de FIS-18).
**Telas e documentos.** Parte do cadastro de contrato (classe cadastro);
aparece no relatório de "Avisos de Excedentes" (HON-39).
**Critérios de aceite.** Um cliente com 13 funcionários e limite de 10 gera
exatamente 3 unidades de excedente, nem mais nem menos, de forma
determinística e reproduzível a partir da mesma contagem de origem.
**Não copiar/riscos.** O manual conta "lançamentos gerados por outro
módulo" e "lançamentos importados via arquivo" como categorias distintas —
replicar essa distinção só quando o DataLedger tiver, de fato, importação de
arquivo de lançamento contábil (hoje não tem, ver `contabilidade.md`).
**Perguntas.** O escritório do Fred usa cobrança por volume hoje (por
funcionário, por lançamento, por nota fiscal)? Se sim, com quais limites e
valores? **Esta é a pergunta central deste item**, citada explicitamente
pelo Fred como exemplo — sem ela, o desenho fica especulativo.

### HON-13 — Lançamento mensal de eventos (avulso)

**O que é.** O lançamento manual de um evento para um cliente numa
competência específica — usado para cobrar algo que não está no contrato
recorrente (ex.: uma consultoria avulsa, um reembolso pontual).
**Exemplo.** Em setembro/2026, lança-se para "Comércio Exemplo Ltda." o
evento "Reembolso de Despesa Cartorial" no valor de R$ 87,50 (**valor
sintético**), com a opção "não faturar com o contrato" (vencimento próprio).
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Receber, Lançamentos, Mensal (p. 299-306), incluindo a janela "Pagamento
de Imposto do Cliente pelo Escritório" (p. 302-306, ver HON-38).
**Fonte normativa.** Não aplicável — lançamento comercial interno.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-02 (cliente), HON-04 (evento), HON-10 (contrato, quando
"faturar com o contrato").
**Dados.** Cliente, evento, competência, data de lançamento, se fatura com
o contrato (e qual contrato) ou tem vencimento próprio, quantidade/valor,
se foi pago pelo escritório antecipadamente (repasse — HON-38), complemento
de texto.
**Regras.** Lançamento em competência já faturada é recusado, salvo
correção explícita rastreável (mesma regra geral de HON-09); o mesmo evento
pode ser lançado mais de uma vez na mesma competência para o mesmo cliente
(regra do manual, reproduzida — não é erro, pode ser legítimo, mesmo
raciocínio de DE-009 para lançamento contábil).
**Telas e documentos.** Tela de lançamento (classe conferência), com a
consulta rápida F5 "Consulta de Faturamento" (p. 641-643) e F6 "Consulta de
Cliente" (p. 643-648) como telas de apoio, sem ID próprio.
**Critérios de aceite.** Dois lançamentos do mesmo evento na mesma
competência para o mesmo cliente são aceitos e aparecem separadamente no
faturamento.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-14 — Lançamento fixo de eventos (recorrente)

**O que é.** Diferente do mensal (lançado mês a mês), o lançamento fixo é
configurado **uma vez** e se repete automaticamente em todas as competências
seguintes (ou em meses selecionados) até ser encerrado — usado para um
evento recorrente que não está dentro do contrato em si (ex.: uma
mensalidade de certificado digital cobrada à parte).
**Exemplo.** Lançamento fixo do evento "Certificado Digital" para "Comércio
Exemplo Ltda.", R$ 25,00/mês (**valor sintético**), a partir de 09/2026,
todos os meses, sem data de encerramento definida.
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Receber, Lançamentos, Fixo (p. 306-309).
**Fonte normativa.** Não aplicável — lançamento comercial interno.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-02, HON-04.
**Dados.** Cliente, evento, competência inicial, competência de
encerramento (opcional), meses de faturamento (todos ou selecionados),
quantidade/valor.
**Regras.** Um lançamento fixo encerrado não gera faturamento depois da
competência de encerramento (mesma regra de HON-11); alterar valor de um
lançamento fixo segue o mesmo procedimento de reajuste rastreável de
HON-17/HON-18, não edição livre.
**Telas e documentos.** Tela de lançamento (classe conferência).
**Critérios de aceite.** Um lançamento fixo encerrado em 12/2026 não
aparece no faturamento de 01/2027.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-15 — Desconto por pontualidade e adimplência

**O que é.** Um desconto automático concedido a clientes que pagam em dia,
aplicado no contrato (HON-10, "desconto por adimplência") ou em nível de
lançamento avulso ("lançamentos de descontos" do manual). É diferente do
desconto dado **no momento do recebimento** (HON-22), que é manual e
pontual.
**Exemplo.** "Comércio Exemplo Ltda." tem desconto de 5% se os últimos 3
meses foram pagos em dia (**percentual e regra sintéticos, decisão de
produto do escritório**); em outubro/2026, com os 3 meses anteriores em dia,
o faturamento aplica o desconto automaticamente e mostra o valor descontado
na prévia.
**Referência de rotina.** Manual Domínio Honorários, parâmetro de
Faturamento (p. 76-77, "Calcular desconto no contrato para clientes
adimplentes"), guia "De Descontos Mensal" (p. 315-316) e "De Descontos por
Período" (p. 316-318) do menu de Lançamentos.
**Fonte normativa.** Não há norma — é política comercial do escritório.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-01 (parâmetro geral), HON-10 (contrato).
**Dados.** Percentual de desconto, número de meses considerados, critério
de "considerar para" (por contrato/geral).
**Regras.** O desconto é calculado **antes** de efetivar o faturamento
(aparece na prévia) e nunca aplicado retroativamente a parcela já faturada
sem o procedimento de correção rastreável.
**Telas e documentos.** Parte da prévia de faturamento (classe
conferência).
**Critérios de aceite.** Um cliente com 1 mês em atraso nos últimos 3 não
recebe o desconto no mês seguinte, e a prévia mostra por que não recebeu.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O escritório do Fred pratica algum desconto por pontualidade
hoje? Com que regra?

## Onda 3 — Faturamento

### HON-16 — Motor de faturamento mensal

**O que é.** O processo central do módulo: para uma competência, soma o
contrato de cada cliente ativo, os eventos fixos e avulsos lançados, os
excedentes calculados (HON-12) e os descontos (HON-15), gera as parcelas a
receber com data de vencimento, e registra os avisos de quem não pôde ser
faturado (cliente sem contrato e sem lançamento, contrato vencido sem
reajuste, contrato encerrado). É rodado **uma vez por competência**, mas
pode ser rodado de novo (com exclusão e regeração) se algo precisar de
correção antes do envio da cobrança.
**Exemplo.** Em 05/10/2026, o Fred roda o faturamento de setembro/2026 para
todos os clientes ativos. 48 clientes são faturados; 2 não são faturados
("cliente sem contrato e sem lançamento de eventos"), e o Fred confere os 2
antes de prosseguir.
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Faturamento (p. 286-288), Aviso Faturamento (p. 288-289), Excluir
Faturamento (p. 289-291).
**Fonte normativa.** Não aplicável — processo comercial interno, sujeito às
regras gerais de idempotência e imutabilidade do AGENTS.md.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-09 (fechamento — recusa faturar período fechado sem
reabertura), HON-10, HON-11, HON-12, HON-13, HON-14, HON-15.
**Dados.** Competência inicial/final, data do faturamento, filtro de
clientes/tipo de lançamento, parcelamento (quantidade de parcelas e
intervalo de dias, quando o faturamento é dividido).
**Regras.** Rodar o faturamento **duas vezes para a mesma competência e o
mesmo cliente nunca duplica a cobrança** — a segunda execução, se
autorizada, exclui e regera de forma rastreável, nunca soma por cima
(idempotência, AGENTS.md §8, DE-009 adaptado: aqui a chave natural é
cliente + competência, e a duplicidade **é** o risco a evitar, ao contrário
do lançamento contábil manual onde repetição pode ser legítima — a diferença
é que o faturamento é **derivado** de contrato e lançamentos, não um
registro independente); uma parcela **já cobrada** (com boleto emitido) ou
**já recebida** não pode ser silenciosamente excluída/regerada — exige
confirmação explícita, com os motivos listados (o manual já lista os casos
que impedem exclusão, p. 290); débitos de dinheiro em `Decimal`, sem
ponto flutuante binário.
**Telas e documentos.** Tela de processo, com prévia de faturamento e
relatório de avisos (classe conferência).
**Critérios de aceite.** Rodar o faturamento duas vezes seguidas para o
mesmo período, sem excluir a primeira geração, não duplica nenhuma parcela;
todo cliente ativo aparece como "faturado" ou "com aviso", nunca
"desconhecido" (mesmo princípio de FIS-17).
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — a regra de idempotência é decisão
nossa, não depende de confirmação externa.

### HON-17 — Reajuste de contrato

**O que é.** A rotina que atualiza o valor do contrato — individualmente ou
em grupo — por percentual, valor fixo somado, novo valor informado, ou
conforme um índice (quando o tipo de contrato usa indexador em índice). Mantém
histórico completo de cada reajuste.
**Exemplo.** Reajuste anual da "Comércio Exemplo Ltda." em 02/2027: valor
anterior R$ 1.200,00, reajuste de 5% (**percentual sintético, a confirmar
com o índice real usado pelo escritório — ex.: IPCA acumulado dos últimos 12
meses, fonte IBGE**), novo valor R$ 1.260,00.
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Reajuste de Contratos: Individual (p. 692-694), Em Grupo (p. 695-698),
Histórico (p. 698-699).
**Fonte normativa.** Quando o reajuste usa índice, a fonte é a do índice em
si (ex.: IPCA — IBGE; IGP-M — FGV) — **a confirmar qual índice o contrato do
escritório usa, nunca presumir**. Quando é percentual livre pactuado, não há
norma, é acordo entre as partes.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-10, HON-05 (tipo de contrato define se reajuste por
índice está disponível).
**Dados.** Competência do reajuste, histórico (texto), forma de reajuste
(percentual/adicionar valor/novo valor/conforme índice), valor anterior,
valor após reajuste.
**Regras.** O reajuste **nunca** altera faturamento de competência já
gerada — só o valor do contrato **a partir** da competência do reajuste;
todo reajuste é registrado em histórico completo, sem sobrescrever o
anterior; excluir um reajuste do histórico não apaga o faturamento que já
usou aquele valor (efetivado é imutável).
**Telas e documentos.** Tela de processo (classe conferência), com relatório
de reajustes (HON-46).
**Critérios de aceite.** Reajustar 40 contratos em grupo gera 40 registros
de histórico individuais, cada um com valor anterior e novo, nunca um
registro agregado que esconda o antes/depois de cada contrato.
**Não copiar/riscos.** Nenhum valor de índice deve ser codificado sem fonte
oficial confirmada.
**Perguntas.** Qual índice (se algum) o escritório do Fred usa para
reajustar contrato? Qual a periodicidade real (anual é a mais comum, mas
precisa confirmação)?

### HON-18 — Reajuste de evento fixo

**O que é.** O mesmo mecanismo de HON-17, aplicado a um evento fixo (HON-14)
em vez de ao valor total do contrato — útil quando só uma taxa específica
precisa de correção, não o honorário inteiro.
**Exemplo.** Reajuste do evento fixo "Certificado Digital" de todos os
clientes que o têm contratado, de R$ 25,00 para R$ 27,50 (**valores
sintéticos**), a partir de 01/2027.
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Reajuste de Evento Fixo (p. 700-703).
**Fonte normativa.** Não há norma — decisão comercial do escritório.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-14.
**Dados.** Evento, competência, forma de reajuste, filtro (fatura ou não
com o contrato), histórico com valor anterior/atual por lançamento fixo.
**Regras.** Idêntico a HON-17, aplicado ao evento fixo em vez do contrato.
**Telas e documentos.** Tela de processo (classe conferência).
**Critérios de aceite.** Idêntico a HON-17.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

## Onda 4 — Cobrança e recebimento

### HON-19 — Documento de cobrança

**O que é.** Um documento de cobrança **sem** registro bancário — mais
simples que boleto, usado quando o escritório não quer (ou o cliente não
paga via boleto) mandar o arquivo de remessa ao banco. Mostra os eventos que
compõem a parcela, valor total, vencimento.
**Exemplo.** Documento de cobrança nº 001234 para "Comércio Exemplo Ltda.",
competência 09/2026, vencimento 10/10/2026, R$ 1.200,00, discriminando o
evento "Honorários Contábeis Mensais".
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Documentos de Cobrança: Emissão (p. 455-458), Reemissão (p. 458-462).
**Fonte normativa.** Não há leiaute oficial para documento de cobrança sem
registro — é documento interno do credor, sem envolvimento bancário. É,
ainda assim, **o documento entregue ao cliente** (nível 1 de risco,
AGENTS.md §3.1): o valor cobrado precisa bater exatamente com a parcela
gerada pelo faturamento.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-16 (faturamento — a parcela já precisa existir).
**Dados.** Número do documento (sequencial, sem duplicidade), parcela de
origem, data de emissão, eventos discriminados, valor total.
**Regras.** Documento de cobrança **emitido é imutável** — corrigir um erro
depois da emissão exige reemissão ou cancelamento rastreável, nunca edição
do documento já gerado (mesmo princípio de nota fiscal, AGENTS.md §10:
"impedir alterações silenciosas em registros efetivados"); número do
documento nunca se repete para o mesmo escritório.
**Telas e documentos.** Documento de cobrança impresso (classe: documento
entregue ao cliente, nível 1 de risco) — não é conferência interna, é o
papel que o cliente recebe.
**Critérios de aceite.** Reemitir um documento de cobrança gera o mesmo
número e o mesmo valor da emissão original, sempre — nunca um valor
recalculado silenciosamente.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O escritório do Fred usa documento de cobrança sem registro
hoje, ou só boleto?

### HON-20 — Boleto bancário

**O que é.** A cobrança com código de barras/linha digitável, vinculada a
uma conta financeira do escritório (HON-06). Pode ser "sem registro"
(controle só no banco em si do boleto impresso) ou "com registro" (o banco
recebe a informação previamente, via remessa — ver HON-21).
**Exemplo.** Boleto "nosso número" 00012345 para "Comércio Exemplo Ltda.",
R$ 1.200,00, vencimento 10/10/2026, carteira/cedente conforme a conta
financeira cadastrada em HON-06.
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Boletos: Emissão (p. 445-450), Reemissão (p. 450-455).
**Fonte normativa.** O **leiaute do boleto de cobrança** (código de barras,
linha digitável, campos obrigatórios) segue o padrão **FEBRABAN**, confirmado
como existente na praça bancária brasileira — **a versão exata e as regras
específicas do banco do escritório precisam ser confirmadas com o banco
antes de qualquer implementação de geração de código de barras**, nunca
inventadas por este documento.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-16, HON-06.
**Dados.** "Nosso número" (sequencial por conta financeira, sem
duplicidade), parcela de origem, código de barras/linha digitável, dados
de juros/multa/desconto para exibição no boleto.
**Regras.** Idêntico a HON-19 quanto à imutabilidade após emissão; "nosso
número" nunca duplica dentro da mesma conta financeira; boleto gerado a
partir de parcela já cancelada (nota fiscal cancelada, por exemplo) é
sinalizado explicitamente, nunca emitido silenciosamente como se fosse
válido.
**Telas e documentos.** Boleto impresso (classe: documento entregue ao
cliente, nível 1 de risco — é dinheiro).
**Critérios de aceite.** Reemissão de boleto preserva o mesmo "nosso
número" e valor da emissão original, salvo alteração explícita e
rastreável de vencimento (opção que o próprio manual prevê,
p. 452-453, "Alterar a data de vencimento").
**Não copiar/riscos.** Risco de gerar código de barras incorreto por
leiaute não confirmado — **nunca implementar geração de código de barras
sem confirmar o leiaute exato do banco escolhido**, isso é dinheiro do
cliente do escritório sendo cobrado com dado errado.
**Perguntas.** Qual banco, qual carteira, com ou sem registro — repete a
pergunta central de HON-06.

### HON-21 — Remessa e retorno bancário (CNAB)

**O que é.** O arquivo que o escritório envia ao banco com os boletos
emitidos para registro ("cobrança registrada", que habilita o banco a
protestar título inadimplente), e o arquivo de retorno que o banco manda de
volta informando o que foi pago, o que foi rejeitado, o que teve baixa.
**Exemplo.** Remessa de 480 boletos de setembro/2026 gerada em formato CNAB
(**240 ou 400 posições, a confirmar conforme o banco escolhido**), enviada
ao banco; retorno de 3 dias depois traz 470 boletos pagos e 10 pendentes.
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Cobrança Registrada (remessa, p. 710-717) e Importação de Boletos Recebidos
(retorno, p. 704-707); cadastro Dados Boletos/Cobrança Registrada
(p. 202-204).
**Fonte normativa.** **Leiaute CNAB (Centro Nacional de Automação
Bancária), padrão FEBRABAN**, 240 ou 400 posições conforme o banco — padrão
**confirmado como existente e público**, mas **a versão exata, os campos
obrigatórios e as particularidades por banco (a matriz do manual lista
regras específicas para cada um dos ~20 bancos suportados) precisam ser
confirmados um a um, com o manual técnico oficial do banco escolhido, antes
de qualquer implementação** — este é o item de maior risco normativo do
módulo, junto com HON-35 (NFS-e).
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-20, HON-06.
**Dados.** Arquivo de remessa (sequência, dados do boleto, instruções de
multa/juros/desconto/protesto/baixa conforme o banco); arquivo de retorno
(status por título: pago, rejeitado, baixado); log de importação com
resultado por linha.
**Regras.** Reimportar o mesmo arquivo de retorno **nunca** duplica a baixa
de um título já processado (idempotência, chave = identificador do título +
banco); todo erro de importação é listado por linha, nunca "engolido"
silenciosamente (mesmo padrão de FIS-01 para o envio de documentos
fiscais).
**Telas e documentos.** Tela de geração de remessa e importação de retorno
(classe conferência); o arquivo em si não é "documento ao cliente", é
arquivo técnico ao banco.
**Critérios de aceite.** Importar o mesmo arquivo de retorno duas vezes não
duplica nenhuma baixa; um título rejeitado pelo banco aparece explicitamente
como rejeitado, nunca como pago.
**Não copiar/riscos.** **Não implementar suporte a um banco sem o manual
técnico oficial daquele banco confirmado** — o risco de gerar remessa
tecnicamente errada é operacional (o banco rejeita o arquivo inteiro) e
financeiro (cobrança não registrada = sem proteção legal de protesto).
**Perguntas.** Repete a de HON-06/HON-20: qual banco. Sem essa resposta,
este item não pode nem começar a ser especificado com segurança.

### HON-22 — Recebimento de parcela

**O que é.** A baixa de uma parcela em aberto — individual ou em grupo —
com cálculo de juros/multa/desconto, e a possibilidade de repartir o
recebimento entre os eventos que compõem a parcela. É o momento em que o
dinheiro efetivamente entra.
**Exemplo.** Recebimento da parcela de "Comércio Exemplo Ltda." vencida em
10/09/2026, paga em 15/09/2026: valor da parcela R$ 1.200,00, juros de 5
dias a 1% a.m. = R$ 2,00 (**cálculo ilustrativo, percentual a confirmar no
contrato**), multa de 2% = R$ 24,00, valor recebido R$ 1.226,00.
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Receber, Recebimentos: Individual (p. 325-336), Em Grupo (p. 340-357),
Histórico de Parcelas (p. 393-395).
**Fonte normativa.** Juros e multa de mora: Código Civil, arts. 406-407, e
o que o contrato fixar — **a confirmar percentual real praticado**; não há
leiaute oficial para o recibo de recebimento em si.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-16 (parcela gerada pelo faturamento), HON-06 (conta
financeira).
**Dados.** Parcela, data de recebimento, conta financeira, juros, multa,
desconto, retenções (CRF/IRRF quando o fato gerador é recebimento),
valor recebido, valor recebido a maior (vira adiantamento — HON-24),
histórico do recebimento, repartição entre eventos da parcela.
**Regras.** Recebimento **efetivado é imutável** — corrigir exige estorno
rastreável, nunca edição do valor recebido; recebimento parcial preserva o
saldo em aberto corretamente, nunca "some" o restante; dinheiro em
`Decimal`, arredondamento de juros/multa/desconto explícito, nunca
silencioso (mesma regra do achado que originou DE-010 na Contabilidade).
**Telas e documentos.** Tela de recebimento com recibo (classe: documento
entregue ao cliente para o recibo, nível 1 de risco; a tela de busca é
conferência).
**Critérios de aceite.** A soma de juros + multa - desconto - retenções
aplicada ao valor da parcela sempre bate exatamente com o "valor recebido"
mostrado, sem diferença de centavo por arredondamento.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Já respondida em HON-01 (percentual de juros/multa
praticado).

### HON-23 — Gestão de cheques recebidos e pagos

**O que é.** O controle de cheque como forma de pagamento — ainda usado por
parte da praça brasileira, embora em declínio: registrar o cheque recebido,
acompanhar sua situação (a compensar, compensado, depositado, descontado,
devolvido, inadimplente) e permitir usá-lo depois para pagar um fornecedor.
**Exemplo.** Cheque recebido de "Comércio Exemplo Ltda." no valor de
R$ 1.200,00, "bom para" 20/10/2026; depositado em 20/10/2026; compensado em
22/10/2026.
**Referência de rotina.** Manual Domínio Honorários, guia Dados Cheque do
recebimento (p. 330), menu Processos, Manutenção de Cheques Recebidos
(p. 430-432).
**Fonte normativa.** Cheque é título de crédito regulado pela Lei
7.357/1985 (Lei do Cheque) — o **prazo de apresentação e a forma do título
em si** têm fonte oficial, mas o **controle interno de situação** (a
compensar, depositado etc.) é organização própria do sistema, sem norma.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22 (recebimento com cheque), HON-28 (pagamento com
cheque recebido de cliente, repassado a fornecedor).
**Dados.** Banco, número, emissão, "bom para", valor, tipo/número de
inscrição do emitente, correntista, situação (a compensar/compensado/
depositado/descontado/devolvido/inadimplente/excluído/pago a fornecedor),
histórico de mudança de situação.
**Regras.** Mudança de situação de cheque é sempre rastreável (quem, quando,
de qual situação para qual); cheque usado para pagar um fornecedor não pode
ser usado duas vezes (mesma regra de não duplicar valor).
**Telas e documentos.** Tela de manutenção (classe conferência).
**Critérios de aceite.** Um cheque não aparece simultaneamente como
"compensado" e "devolvido" — a máquina de estados é exclusiva.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O escritório do Fred ainda recebe pagamento por cheque? Se
não, este item pode ficar adiado (ver HON-91 não — este fica na onda 4
mesmo, mas de baixa prioridade dentro dela).

### HON-24 — Adiantamento de cliente

**O que é.** Um valor que o cliente paga **antes** de haver parcela gerada
— o sistema guarda o saldo e o aproveita automaticamente nos próximos
faturamentos, na ordem de eventos configurada.
**Exemplo.** "Comércio Exemplo Ltda." adianta R$ 3.600,00 em 01/2026, para
cobrir 3 meses de honorários; o faturamento de fevereiro, março e abril
consome R$ 1.200,00 do adiantamento a cada mês, automaticamente, até
zerar o saldo.
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Receber, Adiantamentos (p. 357-363).
**Fonte normativa.** Não há norma — é operação financeira interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-16 (o aproveitamento acontece no faturamento), HON-06.
**Dados.** Cliente, data, valor, conta financeira, ordem de aproveitamento
por evento, saldo atual, histórico de aproveitamento (competência, evento,
valor consumido).
**Regras.** O saldo do adiantamento nunca fica negativo; um recebimento
maior que o devido só vira adiantamento com confirmação explícita (o manual
já exige clicar em "Reticências" para confirmar, p. 330 — reproduzido como
confirmação explícita de domínio, não como texto do manual).
**Telas e documentos.** Tela de adiantamento (classe conferência).
**Critérios de aceite.** A soma do "valor aproveitado" mais o "saldo atual"
bate exatamente com o "valor original" do adiantamento, sempre.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-25 — Renegociação de parcelas

**O que é.** Reorganizar parcelas em aberto de um cliente inadimplente:
gerar novo faturamento com nova data, reparcelar o saldo, quitar sem receber
(remissão), ou só alterar a data de vencimento — sempre preservando o
histórico da dívida original.
**Exemplo.** "Comércio Exemplo Ltda." tem 2 parcelas em aberto somando
R$ 2.400,00; renegocia em 3 parcelas de R$ 800,00 com vencimentos
mensais a partir de 11/2026, com juros de renegociação de R$ 50,00
(**valor sintético**) incluídos na primeira parcela.
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Receber, Renegociações: Renegociar (p. 363-377), Consultar Renegociação
(p. 377-386), Alterar Vencimento (p. 386-393).
**Fonte normativa.** Não há norma específica sobre renegociação de dívida
comercial privada — é livre acordo entre as partes, sujeito às regras
gerais de juros do Código Civil quando aplicável.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22 (parcela em aberto), HON-16.
**Dados.** Parcelas de origem (uma ou várias), nova(s) parcela(s), juros/
multa da renegociação, histórico completo com rastreabilidade até a(s)
parcela(s) original(is).
**Regras.** Renegociar **nunca apaga** a parcela original — ela fica
marcada como renegociada, com link para a(s) nova(s), preservando a trilha
completa da dívida (correção rastreável, nunca silenciosa); a soma das
novas parcelas geradas bate com o valor renegociado (saldo + juros/multa
configurados), sem perda nem sobra de centavo.
**Telas e documentos.** Tela de renegociação, com recibo (classe: documento
entregue ao cliente para o recibo).
**Critérios de aceite.** Consultar a parcela original sempre mostra para
qual(is) parcela(s) ela foi renegociada, e vice-versa.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-26 — Central de cobrança

**O que é.** O painel de trabalho de cobrança de inadimplência: lista
parcelas por situação (em aberto, parcial, recebida), registra
ocorrências de contato (ligação, e-mail, promessa de pagamento) com data
prevista de recebimento e próximo retorno, e permite, a partir da mesma
tela, reemitir boleto/documento de cobrança, renegociar ou gerar carta de
cobrança.
**Exemplo.** O Fred filtra clientes com parcela vencida há mais de 15 dias;
liga para "Comércio Exemplo Ltda."; registra a ocorrência "Cliente prometeu
pagar até 20/10" com próximo retorno em 21/10/2026.
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Central de Cobrança (p. 649-652); cadastro Ocorrências da Central de
Cobrança (p. 263, TOC).
**Fonte normativa.** Não aplicável — ferramenta de gestão interna, sujeita
à LGPD quanto aos dados de contato do cliente tratados (telefone, e-mail) —
**marcar como a confirmar** o tratamento de dados pessoais envolvido
(contato de pessoa física responsável pela empresa cliente).
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22, HON-02 (dados de contato do cliente).
**Dados.** Ocorrência (tipo, data, descrição), data prevista de recebimento,
data de próximo retorno, histórico por cliente/parcela.
**Regras.** Toda ocorrência é rastreável (quem registrou, quando); a
central nunca decide sozinha uma ação financeira (bloqueio, renegociação)
sem confirmação explícita do usuário.
**Telas e documentos.** Painel de trabalho (classe conferência).
**Critérios de aceite.** O histórico de ocorrências de um cliente é
completo e ordenado por data, sem perda de registro.
**Não copiar/riscos.** Cadastro de "Ocorrências da Central de Cobrança" do
manual traz textos-padrão do fornecedor — não copiar a lista, criar
catálogo próprio, editável pelo escritório.
**Perguntas.** O Fred usa algum processo de cobrança de inadimplência hoje
(mesmo informal)? Que tipo de registro seria útil (ligação, e-mail,
WhatsApp)?

### HON-27 — Bloqueio e desbloqueio de cliente inadimplente

**O que é.** O mecanismo que, quando configurado (HON-01), impede o acesso
de um cliente inadimplente **aos demais módulos** do sistema (Fiscal,
Folha, Contabilidade) até a situação se regularizar — ou até um desbloqueio
manual temporário.
**Exemplo.** "Comércio Exemplo Ltda." atinge 2 parcelas em aberto (limite
configurado); o sistema bloqueia o acesso das telas de outros módulos para
aquela empresa; o Fred desbloqueia manualmente por 5 dias para permitir o
fechamento de uma obrigação urgente, com registro do motivo.
**Referência de rotina.** Manual Domínio Honorários, guia Bloqueio dos
Parâmetros (p. 113-115), menu Utilitários, Desbloquear Clientes
Inadimplentes (p. 718-721).
**Fonte normativa.** Não há norma — é decisão de produto/negócio do
escritório. **Atenção:** bloquear acesso a dados fiscais/contábeis de uma
empresa por inadimplência tem implicação de **guarda de dados e de
continuidade do serviço contábil obrigatório** (a empresa continua tendo
obrigações fiscais correntes independente de estar em dia com o
escritório) — **decisão sensível, a confirmar com o Fred se e como deseja
usar este bloqueio**, para não impedir o cumprimento de uma obrigação legal
da empresa cliente por uma questão comercial.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-01, HON-22 (situação de inadimplência).
**Dados.** Situação de bloqueio por empresa, data, motivo, usuário, lista
de exceções (empresas nunca bloqueadas), histórico de bloqueio/desbloqueio
com dias de desbloqueio manual concedidos.
**Regras.** Bloqueio e desbloqueio são sempre rastreáveis (AGENTS.md §11:
autorização verificada no servidor, ator e contexto registrados); desbloqueio
manual tem prazo explícito, nunca "para sempre" sem nova decisão.
**Telas e documentos.** Tela de controle (classe conferência).
**Critérios de aceite.** Empresa bloqueada não acessa tela de outro módulo
sem passar pelo desbloqueio explícito; toda mudança de bloqueio gera
registro de trilha.
**Não copiar/riscos.** **Risco real, não só de engenharia:** bloquear
indiscriminadamente pode impedir o cliente de cumprir obrigação legal
própria (ex.: emitir uma nota fiscal obrigatória) por atraso no pagamento
do escritório — desenhar com exceção clara e nunca como padrão automático
sem confirmação do Fred.
**Perguntas.** O Fred quer usar bloqueio de módulo por inadimplência? Se
sim, bloquear o quê exatamente (consulta, emissão de documento, tudo)?

## Onda 5 — Financeiro do escritório

### HON-28 — Contas a pagar do escritório

**O que é.** O lançamento e pagamento das próprias contas do escritório —
fornecedores, à vista ou a prazo, com ou sem cheque — e a central de
pagamentos que reúne fornecedores, impostos/encargos e folha do próprio
escritório num só painel.
**Exemplo.** Lançamento a prazo de R$ 500,00 (**valor sintético**) para
"Papelaria Exemplo Ltda.", em 3 parcelas mensais de R$ 166,67 (com
arredondamento explícito da diferença de centavo na última parcela).
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Contas
a Pagar: À Vista (p. 396-400), A Prazo (p. 400-404), Lançamentos Orçados
(p. 404-410); Pagamentos: Individual (p. 411-419), Em Grupo (p. 419-430);
Central de Pagamentos — F11 (p. 652-661).
**Fonte normativa.** Não aplicável — financeiro interno do escritório.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-03 (fornecedor), HON-07 (categoria), HON-06 (conta
financeira).
**Dados.** Categoria, fornecedor, documento, série, data de emissão, valor,
desconto, retenções (quando o escritório retém do próprio fornecedor: IRRF,
INSS Retido, ISS Retido, CRF), parcelas (quando a prazo), data de
pagamento, conta financeira.
**Regras.** Lançamento com fornecedor + documento + série + data de
emissão + valor **idênticos** a um já gravado gera aviso de possível
duplicidade (o manual emite mensagem específica, p. 400) — reproduzido como
**aviso**, não bloqueio automático, seguindo o mesmo raciocínio de DE-009
(duplicidade pode ser legítima); dinheiro em `Decimal`.
**Telas e documentos.** Tela de lançamento e pagamento (classe
conferência).
**Critérios de aceite.** Duas contas idênticas geram aviso, não bloqueio;
usuário decide se confirma a duplicata.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-29 — Pagamento de impostos e encargos (do escritório e do cliente)

**O que é.** Uma tela consolidada para pagar os impostos e encargos que o
sistema calculou em **outros módulos** (Fiscal, para a empresa escritório
em si e para os clientes; Folha, para os funcionários do escritório) — e o
mecanismo, já visto em HON-13, de o escritório **pagar adiantado um imposto
do cliente e cobrar de volta como evento de honorários** (repasse).
**Exemplo.** O ISS do escritório referente a setembro/2026, calculado pelo
Fiscal (plano próprio), é pago aqui, com lançamento contábil automático; em
paralelo, o escritório paga o Simples Nacional de um cliente adiantado, e o
valor pago vira um evento "Repasse de Imposto" faturado ao cliente no mês
seguinte, rastreável até o pagamento de origem.
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Pagamento de Impostos (p. 471-478), botão Atualizar/Importar (p. 478-481),
Consultar (p. 482-484); Pagamento de Impostos via e-CAC (p. 484-486, **ver
HON-84, fora de escopo por ora**).
**Fonte normativa.** Não aplicável ao mecanismo de pagamento em si; a
norma incide sobre **cada imposto** pago (ISS, Simples Nacional/DAS,
tributos federais) — já tratada nos planos próprios de Fiscal e Folha
(`fiscal.md`).
**Situação no DataLedger.** **Não existe.**
**Depende de.** Apuração calculada em Fiscal e Folha (planos próprios, fora
deste documento); HON-38 (o repasse é a mesma amarração de cobrança por
valor apurado).
**Dados.** Imposto/encargo, competência, valor original, data de
vencimento, data de pagamento, juros/multa, conta financeira, se foi pago
pelo escritório em nome do cliente (repasse).
**Regras.** Pagar um imposto **nunca** duplica o pagamento se rodado duas
vezes (idempotência por chave = imposto + competência + parcela); repasse
ao cliente é sempre rastreável até o pagamento de origem, nunca um evento
"solto" sem referência.
**Telas e documentos.** Tela de pagamento consolidada (classe conferência).
**Critérios de aceite.** O mesmo imposto não pode ser pago duas vezes sem
aviso explícito; todo repasse cobrado do cliente mostra o pagamento de
origem que o gerou.
**Não copiar/riscos.** Nenhum copiado.
**Perguntas.** O escritório do Fred paga algum imposto de cliente
adiantado e cobra de volta? Se sim, quais (Simples Nacional/DAS é o mais
comum no mercado, mas precisa confirmação)?

### HON-30 — Conta corrente (escritório e cliente)

**O que é.** Um extrato de movimentação financeira: "Conta Corrente
Escritório" mostra entradas e saídas de uma conta financeira do escritório
(recebimentos, pagamentos, adiantamentos); "Conta Corrente Cliente" mostra,
para cada cliente, o que ele deve entrar (faturamento) e o que já saiu
(pagamento) — como um "extrato" da relação comercial.
**Exemplo.** Conta corrente de "Comércio Exemplo Ltda." em setembro/2026:
entrada de R$ 1.200,00 (faturamento), saída de R$ 1.200,00 (recebimento),
saldo zero.
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Conta
Corrente Escritório (p. 462-466), Conta Corrente Cliente (p. 466-467).
**Fonte normativa.** Não aplicável — consulta interna derivada de dados já
lançados.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22, HON-24, HON-28, HON-06.
**Dados.** Nenhum dado novo — é agregação de recebimento, pagamento,
adiantamento e movimentação manual, por conta financeira ou por cliente.
**Regras.** O saldo mostrado sempre bate com a soma de entradas menos
saídas do período, sem diferença — é relatório derivado, nunca fonte
primária de dado.
**Telas e documentos.** Consulta (classe conferência).
**Critérios de aceite.** Soma das movimentações do extrato bate exatamente
com o saldo final mostrado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-31 — Extrato bancário e conciliação

**O que é.** A importação do extrato real do banco (arquivo do próprio
banco, formato a confirmar) e a conciliação — automática (por critério de
data/valor) ou manual — entre o extrato bancário e os lançamentos internos
de conta corrente do escritório.
**Exemplo.** O extrato de setembro/2026 do banco mostra 480 créditos; a
conciliação automática casa 470 deles com os recebimentos já lançados,
deixando 10 para conferência manual (podem ser recebimentos ainda não
lançados no Honorários, ou movimentos de outra origem).
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Lançamentos de Extrato Bancário (p. 467-468), Conciliação de Extrato
Bancário: Automática (p. 468-469), Manual (p. 470), Desconciliação (p. 470),
um-para-vários e um-para-nenhum (p. 470-471); Configuração de Importação de
Extrato Bancário (p. 227-230); Importação de Extrato Bancário — utilitário
(p. 707-709).
**Fonte normativa.** Não há leiaute único oficial de extrato bancário — cada
banco tem o seu formato de exportação (geralmente `.OFX`, `.CSV` ou
proprietário) — **a confirmar formato exato por banco antes de implementar
o importador**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-06, HON-30.
**Dados.** Lançamento de extrato (data, histórico, documento, valor, tipo
soma/subtrai, origem manual/importação, flag conciliado), vínculo de
conciliação (um extrato para um ou vários lançamentos de conta corrente, e
vice-versa).
**Regras.** Reimportar o mesmo arquivo de extrato **nunca duplica** o
lançamento (idempotência por chave natural do banco, quando disponível, ou
por hash do arquivo); desconciliar não apaga o lançamento de extrato nem o
de conta corrente, só desfaz o vínculo.
**Telas e documentos.** Tela de conciliação (classe conferência).
**Critérios de aceite.** Importar o mesmo extrato duas vezes não duplica
nenhum lançamento; toda conciliação é reversível sem perda de dado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Que banco(s) e em que formato o escritório do Fred consegue
exportar extrato hoje?

### HON-32 — Fluxo de caixa e orçamento

**O que é.** Duas visões complementares: o **fluxo de caixa projetado**
(o que entra e sai, com estimativas configuráveis de inadimplência média,
reajuste médio e desconto médio) e o **realizado** (o que efetivamente
entrou/saiu); e o **orçamento** (lançamentos orçados de contas a receber e
a pagar, comparados ao realizado).
**Exemplo.** Fluxo de caixa projetado de outubro/2026 estima R$ 58.000,00
de entrada (soma dos contratos ativos), descontando 3% de inadimplência
média (**percentual sintético configurável**) = R$ 56.260,00 esperado.
**Referência de rotina.** Manual Domínio Honorários, guia Fluxo de Caixa
dos Parâmetros (p. 95-97); menu Processos, Contas a Receber/Pagar,
Lançamentos Orçados (individual/grupo/consulta, p. 320-325, 404-410); menu
Relatórios, Fluxo de Caixa (Projetado p. 559-562, Realizado p. 562-565) e
Orçamentário (Acompanhamento Mensal p. 556-557, Posição p. 557-559).
**Fonte normativa.** Não aplicável — ferramenta gerencial interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-01, HON-16, HON-22, HON-28.
**Dados.** Percentuais de estimativa (inadimplência média, reajuste médio,
desconto de adimplência média), lançamentos orçados (categoria, valor,
competência), meses de referência para cálculo de média.
**Regras.** O relatório projetado é sempre identificado como **estimativa**,
nunca apresentado como fato consumado (rótulo explícito na tela/impressão);
o realizado nunca mistura dado projetado sem indicação clara.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Um relatório projetado sempre traz, visível, os
parâmetros de estimativa usados (percentuais, meses de referência) — nunca
um número "mágico" sem explicação de como chegou lá.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — é ferramenta de gestão, parâmetros
ficam a critério do escritório.

## Onda 6 — Integração contábil

### HON-33 — Integração contábil dupla (escritório e cliente)

**O que é.** A peça que faz de Honorários um caso **duplicado** do padrão já
descrito em [mapa-funcional-contabil.md](../mapa-funcional-contabil.md#dois-momentos-não-um):
para cada evento faturado, recebido, pago ou adiantado, o sistema monta
**dois** lançamentos contábeis em rascunho — um na contabilidade do
**escritório** (a receita de honorários) e um na contabilidade do
**cliente** (a despesa de honorários a pagar, se o escritório também
escritura aquele cliente) — e só depois efetiva os dois, em lote, por
competência.
**Exemplo.** O recebimento de R$ 1.200,00 de "Comércio Exemplo Ltda." gera,
na contabilidade do escritório: débito "Caixa/Bancos", crédito "Receita de
Honorários"; e na contabilidade do cliente (se ele também é cliente da
Contabilidade do DataLedger): débito "Honorários a Pagar", crédito
"Caixa/Bancos" — dois lançamentos, duas empresas, mesma origem.
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Integração Contábil: janela principal (p. 486-488), Advertências
(p. 488-489), janela de Lançamentos contábeis com as duas guias, "do
escritório" e "do cliente" (p. 489).
**Fonte normativa.** Não aplicável ao mecanismo; a norma incide sobre o
**lançamento contábil final** gerado em cada um dos dois livros (mesma base
do módulo Contabilidade, partidas dobradas, NBC TG estrutura conceitual).
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-08 (histórico modelo), HON-16, HON-22, HON-24, HON-28,
HON-29, e o módulo Contabilidade (`criar_lancamento`, já pronto e
auditado).
**Dados.** Lançamento contábil em rascunho, vinculado ao movimento de
Honorários de origem, com dois destinos possíveis (escritório e cliente,
cada um sua própria competência e período de fechamento).
**Regras.** A integração **nunca escreve direto na contabilidade
efetivada** — é sempre prévia, revisável, até a gravação em lote; período
contábil **encerrado, do escritório ou do cliente, recusa** a integração
daquele lançamento especificamente, nunca só avisa (mesma regra de FIS-19,
RC-57); um lançamento gerado duas vezes para a mesma origem não duplica
(chave natural = movimento de Honorários de origem + destino
escritório/cliente); regeração (HON-34) preserva por padrão lançamento
alterado à mão e lançamento já conciliado, como decisão deliberada — igual
à divergência já registrada em `fiscal.md` (FIS-19) para a integração
Fiscal → Contábil.
**Telas e documentos.** Tela de integração com prévia (classe conferência).
**Critérios de aceite.** Cada movimento gera exatamente até dois
lançamentos contábeis (escritório e/ou cliente, conforme configuração);
rodar duas vezes o mesmo período não duplica; débito = crédito em cada um
dos dois lançamentos, sempre.
**Não copiar/riscos.** É o item de maior complexidade de engenharia do
módulo inteiro — a duplicação de livro contábil (escritório + cliente) não
tem equivalente em nenhum outro módulo já planejado; **priorizar primeiro
só o lado escritório**, e tratar o lado cliente como incremento posterior,
condicionado à confirmação de que o Fred realmente usa o DataLedger para
escriturar a contabilidade dos próprios clientes (pergunta abaixo).
**Perguntas.** O Fred pretende usar o DataLedger para escriturar a
contabilidade **dos clientes** também (não só do escritório)? Se a resposta
for não, por ora, o "lado cliente" desta integração fica adiado
indefinidamente, e HON-33 se torna bem mais simples.

### HON-34 — Regeração de lançamentos contábeis

**O que é.** A rotina que refaz, em lote, os lançamentos contábeis já
gerados por HON-33 — útil depois de corrigir uma configuração contábil
errada (conta, histórico) sem precisar editar lançamento por lançamento.
**Exemplo.** O Fred percebe que a conta contábil de "Receita de Honorários"
estava errada desde agosto; corrige a configuração (HON-08) e regera os
lançamentos de agosto e setembro do escritório, preservando os que já foram
alterados manualmente ou conciliados.
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Regerar Lançamentos Contábeis (p. 709-710).
**Fonte normativa.** Não aplicável ao mecanismo; a norma incide sobre o
lançamento contábil gerado.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-33.
**Dados.** Período, origem (escritório/cliente), tipos de lançamento a
regerar (recebimento, pagamento, adiantamento, transferência), flags "não
regerar alterado manualmente" e "não regerar conciliado".
**Regras.** Idêntico a HON-33: as duas flags de proteção (alterado à mão,
conciliado) são **padrão ligado**, não opção — divergência deliberada do
sistema de referência, mesma decisão já registrada em `fiscal.md` (FIS-19).
**Telas e documentos.** Tela de processo, com relatório de inconsistências
(classe conferência).
**Critérios de aceite.** Regerar um período nunca sobrescreve lançamento
conciliado sem desligar explicitamente a proteção.
**Não copiar/riscos.** Nenhum — é onde deliberadamente divergimos do
sistema de referência (proteção como padrão, não opção).
**Perguntas.** Nenhuma bloqueante.

## Onda 7 — Nota fiscal de serviço do escritório

### HON-35 — Emissão de NFS-e do escritório

**O que é.** O próprio escritório de contabilidade é prestador de serviço e
precisa emitir sua nota fiscal de serviço eletrônica para os honorários
faturados — o mesmo tipo de documento que o Fiscal (plano próprio,
`fiscal.md`) hoje só **recebe** de terceiros (FIS-01). Aqui é o lado
**emissor**.
**Exemplo.** NFS-e do escritório para "Comércio Exemplo Ltda.", competência
09/2026, valor R$ 1.200,00, código de serviço de contabilidade conforme a
lista de serviços do município (**a confirmar por município — não é
universal**), ISS calculado pela alíquota municipal vigente (**a confirmar
por município, LC 116/2003 fixa só piso 2% e teto 5%, art. 8º-A**).
**Referência de rotina.** Manual Domínio Honorários, menu Processos, NFS-e:
Gerar RPS (p. 438-441), Consulta de RPS (p. 441-442), Consulta Situação de
Lote de RPS (p. 442-443), Consulta de NFS-e (p. 443-445); Cancelar Notas
Fiscais → NFS-e (p. 684-688, ver HON-36); Exportar XML de RPS (p. 688-690).
**Fonte normativa.** **LC 116/2003** (ISS, fato gerador, lista de serviços —
serviços de contabilidade e assessoria contábil constam da lista anexa,
item 17.19 aproximadamente — **a confirmar item exato e vigência**) e
legislação municipal para alíquota, código de serviço e leiaute de
transmissão — **a confirmar por município do escritório**. O leiaute de
transmissão em si: o manual (versão 10.1A-12) descreve o modelo antigo
**RPS → conversão em NFS-e por webservice municipal**, que é **anterior** ao
padrão nacional unificado (ADN) já usado por FIS-01 na recepção — **este é
um ponto de arquitetura a decidir, não a copiar do manual**: a emissão
própria do escritório deveria, preferencialmente, usar o **mesmo padrão
nacional (ADN, esquemas XSD do Portal Nacional da NFS-e)** que a recepção já
usa, em vez do modelo RPS por município que o manual de 2018 descreve —
**decisão do `arquiteto-senior`, não deste documento**.
**Situação no DataLedger.** **Não existe.** `apps/fiscal` hoje só **recebe**
NFS-e (FIS-01), nunca emite.
**Depende de.** HON-22 (recebimento, quando a nota é gerada por
recebimento) ou HON-16 (quando por competência de faturamento); a fundação
fiscal de emissão (certificado digital, parâmetros municipais) — **a
confirmar se nasce em Honorários, em Fiscal, ou como capacidade de
plataforma compartilhada entre os dois**, porque ambos vão precisar emitir
documento fiscal eventualmente.
**Dados.** Número/série da nota (ou RPS, no modelo antigo), competência,
data de emissão, cliente, valor, código de serviço, alíquota de ISS,
retenções (ISS retido quando o tomador retém, IRRF, CRF), situação
(pendente/emitida/cancelada), XML/protocolo de transmissão.
**Regras.** Nota fiscal **emitida é imutável** — corrige-se por
cancelamento (dentro do prazo municipal, quando houver) e nova emissão,
nunca por edição (mesmo padrão de `DocumentoFiscal` em FIS-01, espelhado
aqui do lado emissor); numeração nunca se repete para o mesmo escritório/
município; reimportar/reprocessar a mesma competência não duplica a
emissão (idempotência).
**Telas e documentos.** Tela de emissão com prévia (classe conferência
antes de emitir); a **nota fiscal em si é documento entregue ao cliente,
nível 1 de risco** — mesmo tratamento de qualquer documento fiscal.
**Critérios de aceite.** Duas execuções da rotina de emissão para a mesma
competência e cliente não geram duas notas; uma nota cancelada nunca
reaparece como válida em relatório.
**Não copiar/riscos.** **Não copiar o modelo RPS por município do manual**
sem decisão explícita do arquiteto — o padrão nacional já em uso na
recepção (FIS-01) é a direção tecnicamente mais nova e mais coerente com o
que o DataLedger já construiu.
**Perguntas.** O escritório do Fred emite NFS-e hoje? Em qual município
(ou municípios, se atende clientes de vários lugares, mas está sediado em
um só)? Qual o código de serviço e a alíquota que ele usa? Existe
certificado digital já disponível para transmissão?

### HON-36 — Reemissão e cancelamento de nota fiscal

**O que é.** Reemitir uma nota já gerada (segunda via, sem alterar dado) e
cancelar uma nota emitida por engano — dois processos distintos, cada um
com sua regra própria de prazo e efeito.
**Exemplo.** Reemissão da NFS-e nº 000123 (segunda via idêntica);
cancelamento da NFS-e nº 000124, emitida com cliente errado, dentro do
prazo municipal de cancelamento (**a confirmar prazo por município**).
**Referência de rotina.** Manual Domínio Honorários, menu Processos, Notas
Fiscais, Reemissão (p. 435-437); menu Utilitários, Cancelar Notas Fiscais:
Nota fiscal impressa (p. 682-684), NFS-e (p. 684-688).
**Fonte normativa.** O **prazo e a forma de cancelamento de NFS-e** são
definidos pela legislação municipal e pelo padrão nacional de eventos de
cancelamento (o mesmo esquema `EventoFiscal`/cancelamento que FIS-01 já lê
do lado recepção, aqui espelhado do lado emissão) — **a confirmar prazo por
município antes de implementar bloqueio de cancelamento fora do prazo**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-35.
**Dados.** Nota de origem, motivo do cancelamento, data, protocolo de
cancelamento (quando transmitido).
**Regras.** Cancelamento **nunca apaga** a nota original — fica marcada
como cancelada, com o evento de cancelamento anexado, igual ao padrão já
confirmado do lado recepção (FIS-02, "situação sempre derivada do evento,
nunca gravada").
**Telas e documentos.** Tela de processo (classe conferência); a segunda
via reemitida é documento entregue ao cliente.
**Critérios de aceite.** Uma nota cancelada nunca aparece como válida em
nenhum relatório ou soma de faturamento.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma além das já feitas em HON-35.

### HON-37 — Integração com Escrita Fiscal (nota de saída do escritório / entrada no cliente)

**O que é.** Depois de emitir a própria NFS-e (HON-35), o escritório precisa
que ela **também** apareça na sua Escrita Fiscal (como nota de saída, para
apuração de ISS/PIS/COFINS do próprio escritório) e, quando o cliente
também usa o Fiscal do DataLedger, como nota de **entrada** na empresa do
cliente (a despesa de honorários entrando na escrituração fiscal dele).
**Exemplo.** A NFS-e emitida para "Comércio Exemplo Ltda." gera, na Escrita
Fiscal do escritório, um lançamento de saída com o acumulador "Venda de
Serviço de Honorários Contábeis" (mesmo conceito de acumulador de
[fiscal.md, FIS-07](fiscal.md)); e, se "Comércio Exemplo Ltda." também é
cliente do Fiscal do DataLedger, gera um lançamento de entrada na
escrituração dela, com o acumulador de despesa correspondente.
**Referência de rotina.** Manual Domínio Honorários, menu Processos,
Integração Escrita Fiscal (p. 490-498): janela principal, guias Escritório
(Notas Fiscais/Recebimentos) e Cliente (Notas Fiscais/Pagamentos).
**Fonte normativa.** Não aplicável ao mecanismo; a norma incide sobre o
lançamento fiscal gerado em cada lado, já tratada em `fiscal.md`.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-35, e o módulo Fiscal do escritório e do cliente
(planos próprios, `fiscal.md` — em especial FIS-07 acumulador e FIS-13
lançamento de serviço).
**Dados.** Nenhum dado novo — referência à `DocumentoFiscal`/lançamento
fiscal gerado a partir da nota de honorários, em cada lado (escritório e
cliente).
**Regras.** Rodar a integração duas vezes não duplica o lançamento fiscal
(mesma chave natural: nota de origem + destino); inconsistência (ex.:
acumulador sem configuração) interrompe a geração daquele item específico
com aviso explícito, nunca gera lançamento incompleto silenciosamente.
**Telas e documentos.** Tela de integração com prévia por lado
(escritório/cliente) (classe conferência).
**Critérios de aceite.** Cada nota gera no máximo dois lançamentos fiscais
(escritório e/ou cliente); nenhum lançamento fiscal nasce sem nota de
origem rastreável.
**Não copiar/riscos.** Mesma ressalva de HON-33: **priorizar o lado
escritório**; o lado cliente depende da mesma resposta sobre se o Fred vai
usar o DataLedger para escriturar o Fiscal dos clientes também.
**Perguntas.** Idêntica à de HON-33, agora para o Fiscal em vez da
Contabilidade.

## Onda 8 — Integração com o volume de outros módulos

### HON-38 — Cobrança vinculada a valor/volume apurado em outro módulo

**O que é.** A contraparte, do lado Honorários, da integração já registrada
em [fiscal.md, item FIS-22](fiscal.md) ("Integração com Honorários"): o
Fiscal (e, futuramente, a Folha) apura um valor — imposto a recolher, taxa
de parcelamento, número de guias — e esse valor vira, aqui, um **evento de
cobrança** faturado ao cliente, sempre rastreável até o dado de origem que
o gerou.
**Exemplo.** A apuração de setembro/2026 no Fiscal calcula ISS a recolher
de R$ 2.000,00 (valor sintético, citado também em FIS-22); a integração
gera, em Honorários, um lançamento do evento "Taxa de Apuração Fiscal"
vinculado a esse valor, conforme a regra de cobrança configurada no evento
(percentual sobre o imposto apurado, ou valor fixo por apuração — **a
definir com o Fred**).
**Referência de rotina.** Do lado Honorários: cadastro de Evento com
"soma na base" e retenção configuráveis (p. 161-163, HON-04) e o parâmetro
de retenção CRF/PIS/COFINS/CSLL (p. 81-84, HON-01). Do lado Fiscal: manual
Domínio Escrita Fiscal, menu Movimentos, "Integração Honorários" (citado em
[fiscal.md, FIS-22](fiscal.md), p. 1553-1554 daquele manual, não deste).
**Fonte normativa.** Não aplicável — é regra de negócio do próprio
escritório (mesma classificação de FIS-22).
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-04, HON-13; e, do lado Fiscal, a apuração calculada
(plano próprio, `fiscal.md`, ondas de apuração).
**Dados.** Evento de cobrança, valor de origem (referência ao imposto/
volume apurado no módulo de origem), competência, módulo de origem.
**Regras.** **Nunca duplica** cobrança ao rodar duas vezes para o mesmo
período (idempotência, mesma regra citada em FIS-22); a variável de
cobrança é sempre rastreável até o dado apurado que a originou — nunca um
valor "solto" sem link para a apuração de origem.
**Telas e documentos.** Tela de integração (classe conferência), lado
Honorários; o lado Fiscal pertence a `fiscal.md`.
**Critérios de aceite.** Rodar a integração duas vezes no mesmo período não
duplica o evento de cobrança; todo evento gerado por esta integração mostra,
na consulta, de onde veio o valor.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Idêntica à de FIS-22, e é a mesma pergunta central de
HON-12: o modelo de cobrança por volume/valor apurado (fixo, percentual
sobre imposto, por evento) já está definido? Este item **depende
diretamente** da resposta, e depende também de Fiscal e Folha terem
apuração pronta (planos próprios) — é por isso que fica na última onda.

## Onda 9 — Relatórios gerenciais e documentos

### HON-39 — Relatórios de faturamento

**O que é.** Cinco relatórios de conferência do que já foi faturado:
Relação (lista simples por competência), Extrato (detalhado por cliente,
com eventos e resumo), Resumo (totais por evento, várias competências),
Por Período (intervalo de competências, vários critérios de agrupamento) e
Pendências/Avisos de Excedentes (o que não pôde ser faturado ou gerou
aviso — ver HON-12 e HON-16).
**Exemplo.** Resumo de faturamento de julho a setembro/2026, agrupado por
evento, mostrando "Honorários Contábeis Mensais: R$ 57.600,00" e "Taxa por
Funcionário Excedente: R$ 630,00".
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Faturamento: Relação (p. 503-504), Extrato (p. 504-506), Resumo
(p. 506-509), Por Período (p. 509-511), Pendências (p. 511-513), Avisos de
Excedentes (p. 513-514).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-16, HON-12.
**Dados.** Nenhum novo — agregação sobre o faturamento já gerado.
**Regras.** Todo cliente faturado no período aparece uma única vez por
relatório, nunca omitido nem duplicado; a soma de qualquer relatório bate
com a soma dos lançamentos de origem (conciliável, AGENTS.md §10).
**Telas e documentos.** Relatórios (classe conferência).
**Critérios de aceite.** Soma do Resumo de um trimestre bate exatamente com
a soma dos três Resumos mensais equivalentes.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-40 — Relatórios de contas a receber

**O que é.** O conjunto de relatórios de acompanhamento do que há a
receber: Relação, Por Período, Extrato por Cliente, Previsão de
Recebimento, Relação de Recebimentos (com seleção por conta financeira),
Adiantamentos, Renegociações, Lançamentos de Eventos (com seleção de
categorias), e as relações de documentos emitidos (Notas Fiscais, RPS,
Boletos, Cheques Recebidos, Documentos de Cobrança).
**Exemplo.** Relatório de Previsão de Recebimento de outubro/2026, somando
todas as parcelas com vencimento naquele mês, por cliente.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Contas a Receber: Relação (p. 514-518), Por Período (p. 518-520), Extrato
por Cliente (p. 520-522), Previsão de Recebimento (p. 522-525), Relação de
Recebimentos (p. 525-528), Adiantamentos (p. 530-532), Renegociações
(p. 532-533), Lançamentos de Eventos (p. 533-537), Notas Fiscais Emitidas
(p. 537-538), RPS Emitidos (p. 538-540), Boletos Emitidos (p. 540-542),
Cheques Recebidos (p. 542-544), Documentos de Cobrança Emitidos (p. 544).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22, HON-24, HON-25, HON-19, HON-20, HON-23, HON-35.
**Dados.** Nenhum novo — agregação sobre dados já cadastrados.
**Regras.** Mesma de HON-39: nenhuma omissão nem duplicidade, soma
conciliável.
**Telas e documentos.** Relatórios (classe conferência).
**Critérios de aceite.** A soma de "Boletos Emitidos" de um período bate com
a soma de parcelas com boleto gerado naquele período.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-41 — Relatórios de contas a pagar

**O que é.** O conjunto equivalente a HON-40, para o lado a pagar do
escritório: Relação, Por Período, Relação de Pagamentos, Cheques Pagos.
**Exemplo.** Relação de Pagamentos de setembro/2026, mostrando todos os
fornecedores pagos e o total do mês.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Contas a Pagar: Relação (p. 545-549), Por Período (p. 549-551), Relação de
Pagamentos (p. 551-554), Cheques Pagos (p. 554-556).
**Fonte normativa.** Não aplicável.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-28, HON-23.
**Dados.** Nenhum novo.
**Regras.** Idêntica a HON-40.
**Telas e documentos.** Relatórios (classe conferência).
**Critérios de aceite.** Idêntico a HON-40.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### HON-42 — Gráficos gerenciais

**O que é.** Visualização gráfica (evolução mensal e composição) de
faturamento, contas a receber e contas a pagar — o mesmo dado de HON-39/
HON-40/HON-41, em forma de gráfico em vez de tabela.
**Exemplo.** Gráfico de evolução do faturamento dos últimos 12 meses.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Gráficos: Evolução (Faturamento p. 588-589, Contas a Receber p. 589-591,
Contas a Pagar p. 591-592), Composição (Faturamento p. 592-593, Contas a
Receber p. 593-595, Contas a Pagar p. 595-597).
**Fonte normativa.** Não aplicável.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-39, HON-40, HON-41.
**Dados.** Nenhum novo — mesma agregação, apresentação diferente.
**Regras.** O gráfico nunca mostra número diferente do relatório tabular
equivalente para o mesmo filtro — é a mesma fonte de verdade.
**Telas e documentos.** Gráfico (classe conferência).
**Critérios de aceite.** O total do gráfico de composição de um mês bate
com o total da Relação equivalente.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — item de baixa prioridade, mais
apresentação que dado novo.

### HON-43 — Emissão de contrato e distrato a partir de modelo

**O que é.** O documento impresso do contrato (HON-10) e do distrato,
gerado a partir de um modelo com variáveis (HON-47), mais a relação de
contratos/distratos cadastrados.
**Exemplo.** Emissão do contrato da "Comércio Exemplo Ltda." em PDF, com
timbre do escritório (reaproveitando `linhas_do_timbre` de
`apps/tenancy`), valor, vigência e cláusulas do modelo preenchidas.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Contratos: Emissão (p. 597-599), Relação (p. 599-600); Distrato: Emissão
(p. 601-602), Relação (p. 602-603).
**Fonte normativa.** Não há norma sobre o formato do contrato em si (ver
HON-10). O **timbre/identificação do emitente** já é regra de plataforma
confirmada (RC-94, `apps/tenancy`), reaproveitada aqui.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-10, HON-47.
**Dados.** Nenhum novo além do contrato e do modelo.
**Regras.** O contrato impresso é **o documento entregue ao cliente**
(nível 1 de risco, AGENTS.md §3.1) — precisa de identificação do emitente
(mesma medição já feita para outros documentos, DL-028) e de exatidão total
em relação ao valor e vigência realmente cadastrados.
**Telas e documentos.** Documento impresso (classe: documento entregue ao
cliente).
**Critérios de aceite.** O valor e a vigência impressos no contrato sempre
batem exatamente com os dados cadastrados no momento da emissão.
**Não copiar/riscos.** Não copiar cláusula jurídica do modelo do
fornecedor — cláusula contratual é texto do escritório/seu advogado, não
do sistema.
**Perguntas.** O escritório do Fred tem modelo de contrato próprio já
pronto (Word/PDF) para servir de base?

### HON-44 — Carta de responsabilidade da administração

**O que é.** Um documento anual, assinado pelo representante legal da
empresa cliente, declarando responsabilidade pela veracidade das
informações fornecidas ao escritório — prática comum de segurança
profissional do contador, não é uma obrigação fiscal em si.
**Exemplo.** Carta de responsabilidade de "Comércio Exemplo Ltda." para o
exercício de 2026, com o número de inscrição no CRC do contador
responsável.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios, Carta
de Responsabilidade da Administração (p. 603-605).
**Fonte normativa.** Não há norma que **exija** este documento — é prática
profissional recomendada, próxima ao conceito de "carta de representação"
usado em auditoria (NBC TA 580, que trata de auditoria, não de serviços
contábeis em geral — **a confirmar se há orientação específica do CFC para
escritórios de contabilidade fora de auditoria, antes de apresentar isso
como exigência normativa**).
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-02, HON-47.
**Dados.** Cliente, período-base, número de inscrição do CRC do contador
responsável, texto do modelo.
**Regras.** Mesma de HON-43: documento entregue ao cliente, precisa de
identificação do emitente e exatidão dos dados.
**Telas e documentos.** Documento impresso (classe: documento entregue ao
cliente).
**Critérios de aceite.** O número de CRC impresso é sempre o do profissional
efetivamente responsável pelo cliente naquele período (não um valor
padrão fixo).
**Não copiar/riscos.** Não copiar o texto da carta do fornecedor — é
declaração profissional, o texto precisa ser do escritório/seu advogado.
**Perguntas.** O Fred usa este tipo de carta hoje com seus clientes?

### HON-45 — Outros documentos de cobrança e relacionamento

**O que é.** Um grupo de documentos de apoio: Carta de Cobrança (para
inadimplente, ligada à Central de Cobrança — HON-26), Correspondência
genérica, Etiqueta (endereçamento em massa), Declaração Anual de Quitação
de Débitos (atesta que o cliente está em dia num período), e a relação de
Clientes Bloqueados (ver HON-27).
**Exemplo.** Declaração Anual de Quitação de Débitos de "Comércio Exemplo
Ltda." para 2025, emitida em janeiro/2026, confirmando que todas as
parcelas com vencimento em 2025 foram quitadas.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Outros: Carta de Cobrança (p. 608-611), Correspondência (p. 611), Etiqueta
(p. 612-613), Declaração Anual de Quitação de Débitos (p. 613-614),
Clientes Bloqueados (p. 614-615).
**Fonte normativa.** Não aplicável a nenhum dos cinco — são documentos de
relacionamento comercial, não obrigação legal.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-22, HON-26, HON-27, HON-47 (para carta/correspondência
via modelo).
**Dados.** Nenhum novo além do já cadastrado em HON-22/HON-26/HON-27.
**Regras.** A Declaração de Quitação **nunca** afirma quitação de parcela
que na verdade está em aberto — é derivada exatamente da situação real das
parcelas, nunca um texto solto.
**Telas e documentos.** Documentos impressos (classe: documento entregue ao
cliente, para carta/declaração/etiqueta; a relação de bloqueados é
conferência interna).
**Critérios de aceite.** Uma Declaração de Quitação só é emitida sem
ressalva quando **todas** as parcelas do período estão efetivamente
quitadas — checagem automática, não confiança na memória do usuário.
**Não copiar/riscos.** Não copiar texto de carta/declaração do fornecedor.
**Perguntas.** Nenhuma bloqueante — baixa prioridade dentro da onda.

### HON-46 — Relatórios de reajuste e cadastrais

**O que é.** Os relatórios de conferência dos reajustes já feitos (HON-17,
HON-18) e as relações simples de cada cadastro de apoio (empresas,
clientes, fornecedores, eventos, tipos de contrato, bancos, agências,
contas financeiras, históricos, categorias, contas contábeis, ocorrências
da central de cobrança, feriados, índices) — baixa complexidade, mas
completude exigida para não faltar nenhum cadastro sem sua relação.
**Exemplo.** Relação de reajustes de contratos de 01/2026 a 12/2026, todos
os clientes.
**Referência de rotina.** Manual Domínio Honorários, menu Relatórios,
Reajustes: Contratos (p. 606-607), Eventos Fixos (p. 607-608); Cadastrais:
Empresas (p. 615-618), Clientes (p. 618-620), Fornecedores (p. 620-621),
Eventos (p. 621-622), Tipos de Contrato (p. 622-623), Bancos (p. 623-624),
Agências (p. 624), Contas Financeiras (p. 624-625), Históricos (p. 625),
Ocorrências da Central de Cobrança (p. 626-627), Categorias de Contas a
Receber (p. 627-628), Categorias de Contas a Pagar (p. 628-629), Contas
Contábeis (p. 629-632), Históricos Contábeis (p. 632-633), Complementos de
Históricos Contábeis (p. 633-634), Observações (p. 634), Classificações
(p. 635), Testemunhas (p. 635-636), Feriados (p. 636-637), Índices
(p. 637).
**Fonte normativa.** Não aplicável — relatórios cadastrais de conferência
interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** HON-01 a HON-09, HON-17, HON-18.
**Dados.** Nenhum novo — listagem simples de cada cadastro.
**Regras.** Toda relação lista 100% dos registros do filtro aplicado, sem
omissão.
**Telas e documentos.** Relatórios (classe conferência).
**Critérios de aceite.** A contagem de linhas de cada relação bate com a
contagem de registros do cadastro correspondente, para o mesmo filtro.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — implementar junto de cada cadastro
correspondente, não como entrega isolada.

## Onda 10 — Plataforma de documentos

### HON-47 — Motor de modelos de documento com variáveis (mala direta)

**O que é.** A peça de infraestrutura que sustenta HON-43, HON-44 e parte
de HON-45: um editor de modelo de documento (contrato, distrato, carta de
responsabilidade, carta de cobrança, correspondência) com variáveis que o
sistema resolve a partir do cadastro (nome do cliente, valor do contrato,
data, etc.), permitindo criar modelo novo, editar existente ou importar um
arquivo pronto.
**Exemplo.** Modelo de contrato com o texto "Pelo presente instrumento, o
CONTRATANTE {razao_social_cliente} contrata os serviços de {razao_social_
escritorio} pelo valor mensal de {valor_contrato}...", resolvido para cada
cliente no momento da emissão (HON-43).
**Referência de rotina.** Manual Domínio Honorários, menu Utilitários,
Modelos de Documentos: Criar um Novo Modelo (p. 721-726), Editar um Modelo
já Existente (p. 726-727).
**Fonte normativa.** Não aplicável ao mecanismo. O **conteúdo jurídico** de
cada modelo (cláusula de contrato, texto de carta) não é normado por este
documento — é texto do escritório, com seu próprio assessoramento jurídico.
**Situação no DataLedger.** **Não existe.** É desenho de arquitetura novo,
não um port do editor do manual (que depende de Microsoft Word/OpenOffice
instalado localmente — **incompatível com uma aplicação web**, precisa de
um mecanismo próprio, provavelmente baseado em texto/HTML com
placeholders, na mesma linha do padrão já decidido para histórico com
variáveis, HON-08).
**Depende de.** HON-08 (mesmo padrão de resolução de variável, em escala
maior — documento inteiro, não só uma linha de histórico).
**Dados.** Modelo (texto/HTML), lista de variáveis disponíveis por tipo de
documento, vínculo entre modelo e documento gerado (contrato, distrato,
carta).
**Regras.** Resolução de variável nunca falha silenciosamente (mesma regra
de HON-08); um documento já emitido a partir de um modelo **não** muda
retroativamente se o modelo for editado depois — o texto gerado é
congelado no momento da emissão (imutabilidade do documento entregue ao
cliente).
**Telas e documentos.** Editor de modelo (classe cadastro); os documentos
gerados são HON-43/HON-44/HON-45.
**Critérios de aceite.** Editar um modelo depois de um documento já emitido
não altera o texto do documento já emitido, só as emissões futuras.
**Não copiar/riscos.** **Não portar a integração com Microsoft Word/
OpenOffice do manual** — é arquitetura de aplicação desktop, incompatível
com o produto web do DataLedger; desenhar um editor próprio, mais simples,
na primeira entrega (mesmo texto com placeholders, sem editor visual
completo).
**Perguntas.** Qual é o nível de sofisticação de editor que o Fred
realmente precisa na primeira entrega — texto simples com variáveis, ou
formatação rica (negrito, tabela, quebra de página)? Isso muda bastante o
esforço de HON-47.

## Fora de escopo ou dependente de confirmação

Cada um segue o formato reduzido do README: ID, motivo, fonte que decide (ou
o que falta decidir).

### HON-80 — Cadastro completo de empresa, sócios e contador responsável (Controle > Empresas)

**Motivo.** O manual dedica um cadastro extenso (guias Empresa, Atividades,
Responsável Legal, Registro, Quadro Societário, Observações, Certificado
Digital) a informações que **já existem** em `apps/empresas.Empresa` no
DataLedger. Duplicar esse cadastro dentro de Honorários fragmentaria a
fonte única de verdade sobre a empresa cliente.
**Fonte que decide.** Não é pendência normativa — é decisão de arquitetura
do `arquiteto-senior`: qualquer campo que falte em `apps/empresas.Empresa`
para atender Honorários deve ser pedido de evolução **daquele** app, nunca
duplicação aqui.

### HON-81 — Permissões, usuários e grupos de módulos/empresas

**Motivo.** O manual tem seu próprio sistema de permissão por usuário, por
módulo e por empresa (Controle > Permissões). O DataLedger já tem
autenticação e autorização em `apps/accounts`/`apps/tenancy`, aplicada a
todo o produto — Honorários usa a mesma camada, não cria uma paralela
(AGENTS.md §11: autorização verificada no servidor, uma vez, para toda a
plataforma).
**Fonte que decide.** Não é pendência normativa — decisão de arquitetura já
implícita na plataforma existente.

### HON-82 — Troca de empresa (F8) e seleção de clientes (Ctrl+F) como telas dedicadas

**Motivo.** São atalhos de navegação de uma aplicação desktop antiga. O
DataLedger já resolve troca de contexto de empresa/cliente por seleção
dentro do fluxo web normal (cada tela já filtra por escritório/empresa no
servidor) — não precisa de uma tela dedicada equivalente.
**Fonte que decide.** Não é pendência normativa — decisão de UX da
plataforma, cabe ao `especialista-frontend` quando desenhar as telas.

### HON-83 — Configuração de Conteúdo Contábil Tributário (Thomson Reuters Integra)

**Motivo.** Integração proprietária com um parceiro comercial específico do
fornecedor do sistema de referência — não é capacidade genérica do domínio
contábil, é um contrato comercial entre a Domínio e a Thomson Reuters.
**Fonte que decide.** Não aplicável — não copiar integração de parceiro de
terceiro.

### HON-84 — Pagamento de impostos via e-CAC

**Motivo.** O manual descreve importação automática de baixa de impostos
direto do portal e-CAC da Receita Federal. Não há API pública e estável
documentada para isso — a prática usual é acesso via certificado digital
simulando navegação (scraping), frágil e sujeita a mudança sem aviso do
portal oficial, além de risco de violar termos de uso. **Risco declarado,
não implementar sem uma via oficial confirmada.**
**Fonte que decide.** Receita Federal — portal e-CAC; **pendência de
pesquisa** sobre a existência de integração oficial (ex.: via
Serviços Web do governo) antes de qualquer decisão.

### HON-85 — Nota fiscal modelo 1 / nota fiscal de serviço impressa (papel)

**Motivo.** Formato de nota fiscal impressa em papel numerado, anterior à
NFS-e eletrônica — a lista de municípios do próprio manual (p. 98-99) já
mostra que, mesmo em 2018, a maioria das praças relevantes já usava NFS-e
eletrônica. Forte indício de obsolescência para uso corrente em 2026.
**Fonte que decide.** Legislação municipal específica — só relevante se o
município do escritório do Fred ainda não tiver adotado NFS-e eletrônica,
o que precisa ser confirmado antes de priorizar.

### HON-86 — Menu Favoritos

**Motivo.** Atalho de navegação de aplicação desktop (favoritar opção de
menu, sistema externo ou página web). Sem equivalente necessário numa
aplicação web com navegação direta por URL.
**Fonte que decide.** Não aplicável — decisão de UX, não de domínio.

### HON-87 — Backup, Configurar Backup, Backup em Nuvem

**Motivo.** Backup e restauração são responsabilidade de infraestrutura da
plataforma inteira (AGENTS.md §12: "backup e restauração planejados e
verificados"), não uma tela dentro do módulo Honorários.
**Fonte que decide.** Não aplicável — infraestrutura de operação, fora do
escopo de um módulo de negócio.

### HON-88 — Calculadora, Registro de Atividades, Conexões com banco de dados, Configurar conexão internet, Configurar envio de e-mail, Acessar versão anterior, Menu Ajuda

**Motivo.** Conjunto de utilitários de aplicativo desktop (calculadora
embutida, log de atividade de sessão, configuração de rede/e-mail/versão)
sem equivalente de produto em uma aplicação web multiempresa — o registro
de atividade relevante já é coberto por `apps/auditoria`; envio de e-mail é
capacidade de plataforma, não de Honorários especificamente.
**Fonte que decide.** Não aplicável — chrome de aplicativo desktop ou
infraestrutura de plataforma, não domínio de Honorários.

### HON-89 — Concluir Atividades (integração com Domínio Processos)

**Motivo.** O manual permite concluir, a partir de Honorários, atividades
cadastradas no módulo de processos/paralegal (Domínio Processos) —
funcionalidade que pertence ao **plano de Processos/Paralegal**, ainda não
escrito, não a este documento. Aqui só entra como dependência de
integração futura, quando aquele plano existir.
**Fonte que decide.** Não aplicável a este documento — remissão de escopo.

### HON-90 — Índices diários e médios (cadastro de tabela de índice)

**Motivo.** O cadastro de índices (Diários/Médios, com botão Duplicar,
p. 270-273) é a fonte de valor que HON-17 (reajuste por índice) consome.
Fica **dependente de confirmação** porque a fonte oficial de cada índice
(IPCA/IGP-M/INPC, cada um do seu órgão) e a forma de atualização (manual ou
importação automática de fonte pública) ainda não foram decididas — **não
implementar cadastro de índice com valor "chutado"**.
**Fonte que decide.** Fonte oficial do índice que o escritório do Fred
efetivamente usa (IBGE para IPCA/INPC, FGV para IGP-M) — a confirmar antes
de qualquer implementação de HON-17 por índice.

### HON-91 — Rotinas automáticas agendadas (execução periódica com aviso por e-mail)

**Motivo.** Agendar a execução periódica de faturamento/relatório com envio
de e-mail é uma capacidade que depende de infraestrutura de tarefas em
segundo plano (fila, agendador) — decisão de arquitetura da **plataforma**,
não exclusiva de Honorários. Nível 3 de risco (andaime, AGENTS.md §3.1):
sem plano nem auditoria dedicados, entra quando a infraestrutura de tarefas
em segundo plano existir no projeto.
**Fonte que decide.** Não aplicável — decisão de arquitetura de
plataforma, a revisar quando a infraestrutura correspondente existir.

## Glossário

Termos usados neste documento sem explicação no corpo do texto.

- **Adiantamento.** Valor pago pelo cliente antes de existir parcela
  gerada, consumido automaticamente em faturamentos futuros — ver HON-24.
- **Boleto com/sem registro.** "Com registro" significa que o banco recebeu
  previamente a informação do título via arquivo de remessa (permite
  protesto de inadimplente); "sem registro" é controlado só pelo emissor.
- **Carteira (bancária).** Código que identifica, junto ao banco, a
  modalidade de cobrança contratada (ex.: cobrança simples, registrada).
- **Cedente.** Quem emite o boleto/título junto ao banco — aqui, o
  escritório.
- **CNAB (Centro Nacional de Automação Bancária).** Padrão de arquivo,
  definido pela FEBRABAN, para troca de arquivos de remessa e retorno entre
  empresa e banco — usado em cobrança registrada (HON-21).
- **Cobrança registrada.** Modalidade de boleto em que o banco recebe
  previamente os dados do título (via remessa CNAB), habilitando serviços
  como protesto de inadimplente.
- **Competência.** O período (mês/ano) ao qual um faturamento, recebimento
  ou lançamento pertence.
- **Evento.** O item cobrável mais elementar de Honorários — honorário em
  si, despesa reembolsável, taxa, imposto repassado (HON-04).
- **Excedente de contrato.** Cobrança adicional quando o cliente ultrapassa
  um volume combinado (funcionários, lançamentos, faturamento) — HON-12.
- **Nosso número.** Identificador único do boleto, atribuído pelo cedente
  dentro de uma faixa controlada por conta financeira.
- **RPS (Recibo Provisório de Serviços).** Documento intermediário emitido
  antes da conversão em NFS-e, no modelo municipal anterior ao padrão
  nacional (ver HON-35).
- **Renegociação.** Reorganização de parcela em aberto (novo vencimento,
  reparcelamento, quitação sem receber) preservando a trilha até a dívida
  original — HON-25.
- **Retenção na fonte (IRRF, ISS Retido, INSS Retido, CRF).** Parcela do
  valor da nota que o tomador do serviço deduz e recolhe diretamente ao
  fisco, em vez de pagar ao prestador — pode incidir tanto sobre as notas
  que o escritório **emite** (HON-35) quanto sobre as que ele **recebe** de
  fornecedores (HON-28). CRF é a sigla usada pelo sistema de referência para
  a retenção combinada de CSLL/COFINS/PIS (também chamada de CSRF no mercado).
- **Sacado.** Quem paga o título — aqui, o cliente do escritório.

## Perguntas abertas consolidadas

Todas já aparecem dentro do item correspondente; esta lista reúne só as que
dependem diretamente do Fred (prática real do escritório), para que ele não
precise garimpar item por item.

1. **(HON-01)** O escritório retém algum imposto nas próprias notas de
   honorários hoje (IRRF, ISS retido, CRF)? Cobra juros/multa de atraso, com
   que percentual?
2. **(HON-02)** O Fred atende cliente "eventual" (sem contrato mensal), ou
   toda a carteira é cliente fixo com contrato?
3. **(HON-04)** Quais eventos o escritório realmente cobra hoje, além do
   honorário mensal (reembolso, taxa por documento, taxa por funcionário)?
4. **(HON-06, HON-20, HON-21)** Qual banco o escritório usa (ou pretende
   usar) para boleto e remessa CNAB? Com ou sem registro?
5. **(HON-10)** Contrato por tempo determinado ou indeterminado? Desconto
   por adimplência? Dia de vencimento padrão?
6. **(HON-12, HON-38) — a pergunta mais central deste documento.** O
   escritório cobra por volume/valor apurado hoje (por funcionário, por
   lançamento, por nota fiscal, percentual sobre imposto apurado)? Com quais
   limites e valores? Sem essa resposta, o mecanismo de cobrança por volume
   citado pelo próprio Fred como exemplo fica com desenho especulativo.
7. **(HON-17, HON-90)** Qual índice de reajuste o escritório usa (IPCA,
   IGP-M, outro)? Com que periodicidade real?
8. **(HON-23)** O escritório ainda recebe pagamento por cheque?
9. **(HON-26)** Existe processo de cobrança de inadimplência hoje, mesmo
   informal? Que canal (ligação, e-mail, WhatsApp)?
10. **(HON-27)** O Fred quer bloquear acesso de cliente inadimplente a
    outros módulos? Bloquear o quê exatamente?
11. **(HON-29)** O escritório paga imposto de cliente adiantado e cobra de
    volta? Quais impostos (Simples Nacional/DAS é o mais comum no mercado,
    mas precisa confirmação)?
12. **(HON-31)** Em que banco(s) e formato o escritório consegue exportar
    extrato bancário hoje?
13. **(HON-33, HON-37)** O Fred pretende usar o DataLedger para escriturar a
    Contabilidade e o Fiscal **dos clientes** também, não só do escritório?
    Esta resposta muda o tamanho de dois dos itens mais complexos do
    documento (a integração contábil e fiscal "em dobro").
14. **(HON-35)** O escritório emite NFS-e hoje? Em qual município? Qual o
    código de serviço e a alíquota de ISS praticada? Há certificado digital
    disponível para transmissão?
15. **(HON-44)** O Fred usa carta de responsabilidade da administração com
    seus clientes hoje?
16. **(HON-47)** Qual o nível de sofisticação de editor de modelo de
    documento necessário na primeira entrega — texto simples com variáveis,
    ou formatação rica?
