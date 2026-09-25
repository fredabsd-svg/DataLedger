# Mapa funcional — Escrita Fiscal

Levantamento das **capacidades** que um módulo de escrita fiscal precisa ter,
derivado da análise de um manual de referência de sistema comercial fornecido
pelo Fred em 2026-09-12.

## O que este documento é, e o que não é

**É** um mapa de capacidades do domínio: quais rotinas um escritório executa,
quais cadastros sustentam o cálculo, quais obrigações existem e como as peças se
conectam. Isso é conhecimento do domínio contábil-fiscal brasileiro.

**Não é** cópia de sistema algum. Não foram transcritos texto, telas,
nomenclatura de menus nem estrutura de interface do material de referência. O
material é protegido por direito autoral e **não está versionado neste
repositório**, nem em trechos. A orientação do Fred foi explícita: *"não faça
igual"*. É também a posição que o [README](../../README.md) já registrava —
abrangência funcional como referência, identidade e implementação próprias.

O material de referência é de **2018**. Ver a seção de obsolescência: a lista de
obrigações **não pode ser usada como requisito** sem conferência de vigência.

## Descoberta que muda o planejamento

O material cobre **apenas a escrita fiscal** — um dos cinco módulos previstos no
nosso [escopo](../escopo.md). Fiscal, Folha, Contabilidade, Honorários e
Processos/Paralegal são cinco domínios desse porte.

Isso não é motivo para desanimar; é motivo para **fatiar com honestidade**.
Nenhuma equipe entrega um módulo desses "em algumas etapas". O caminho viável é
escolher a fatia que resolve uma dor real do escritório e entregá-la completa,
com apuração conferível, em vez de entregar cinco módulos pela metade.

## A ideia central do motor fiscal: classificação dirige cálculo

A observação mais importante do levantamento não é uma funcionalidade, é uma
**decisão de arquitetura** que o sistema de referência tomou e que merece ser
adotada em espírito:

> Existe um cadastro de **classificação** — no sistema de referência chamado
> *acumulador* — que fica **entre o documento e o resultado fiscal**. Cada
> lançamento recebe uma classificação, e é ela que carrega o tratamento
> tributário: o que entra em qual base, o que gera crédito, o que é isento, o
> que totaliza onde.

Por que isso importa para nós: significa que o motor fiscal **não** é uma
sequência de `if` por imposto. É uma **tabela de regras versionada por
vigência**, e o cálculo é a aplicação dessas regras a documentos classificados.
Essa é a diferença entre um sistema que aceita uma mudança de legislação como
dado e um que exige alteração de código a cada norma nova.

Casa exatamente com o que o [AGENTS.md](../../AGENTS.md) §10 já exige: versionar
parâmetros legais e regras por vigência, com fonte verificável.

## Capacidades mapeadas

### 1. Cadastros que sustentam o cálculo

| Capacidade | Observação |
| --- | --- |
| Participantes (fornecedores, clientes, remetentes/destinatários) | Base de qualquer documento fiscal |
| Produtos e serviços, com NCM | Tributação por NCM é cadastro próprio, não campo do produto |
| Unidades e grupos | Conversão e agrupamento |
| **Classificação fiscal (acumuladores)** | O coração do motor. Define totalização e tratamento |
| Impostos e suas tabelas | Alíquotas e regras por vigência |
| Configuração de históricos | Texto do lançamento montado por variáveis |
| Convênios e protocolos de substituição tributária | ICMS-ST entre estados |
| Tabelas de crédito presumido | Benefício por regime/atividade |
| Contas e agências bancárias | Para guias e pagamentos |

### 2. Movimentos — a escrituração

| Capacidade | Observação |
| --- | --- |
| Notas de entrada | Volume principal |
| Notas de saída | Volume principal |
| Serviços | ISS, retenções |
| Documentos de cupom fiscal (redução Z) | Varejo |
| Resumo de movimento diário | Transporte |
| Estoque | Inventário e movimentação |
| Baixas e parcelas | Contas a pagar/receber vinculadas ao documento |
| **Apuração** | Onde o motor produz o resultado do período |
| Parcelamento de impostos | Inclusive Simples Nacional |
| Pagamento de impostos | Geração e baixa |
| **Integração contábil** | Fiscal gera lançamento na contabilidade |
| **Integração com honorários** | Fiscal alimenta cobrança |

Segmentos especializados que o material cobre e que **não** devem entrar sem
demanda real: combustíveis (bombas, bicos, tanques), empreendimentos
imobiliários, sociedade em conta de participação, produção de usina, bilhetes de
passagem.

### 3. Saídas — livros, relatórios e obrigações

- **Livros fiscais** e termo de abertura/encerramento.
- **Demonstrativos de apuração** por imposto.
- **Guias** federais, estaduais e municipais.
- **Obrigações acessórias** — ver ressalva de vigência abaixo.
- Relatórios de acompanhamento e conferência.

### 4. Operação e conferência

Capacidades que não aparecem em folheto e são as que mais economizam tempo de
escritório:

- **Importação** de documentos (XML e arquivos de terceiros) — é o que evita
  digitação.
- **Conferência de lançamentos** antes de fechar o período.
- **Alterações em massa** com critério (corrigir classificação de muitas notas).
- **Consulta de apuração** com rastreio até o documento de origem.
- **Backup e restauração**.
- Registro de atividades do usuário.

Essas rotinas são o que diferencia um sistema usável de um sistema que só
"tem os campos". Merecem peso no nosso backlog.

## Ressalva crítica: obsolescência do material de referência

O material é de **2018**. Várias obrigações que ele cobre **provavelmente foram
extintas, substituídas ou alteradas** desde então, e há ainda a **Reforma
Tributária do Consumo** em implantação, que altera o cenário de forma profunda.

**Nenhum item da lista abaixo deve virar requisito sem que o Fred confirme a
vigência.** Registrado como pendência, não como requisito:

Obrigações citadas pelo material: SPED Fiscal, SPED Contábil, EFD
Contribuições, Sintegra, DCTF, DACON, DNF, CFEM, DIRF, DIPJ, PJSI, DASN, DeSTDA,
DEFIS, DMED, Receitas MEI, comprovantes de retenção, PER/DCOMP, SINCO, SV A,
I-SIMP, DIMOB, DIME, DCIP, SCANC-CTB, Convênio ICMS 115/2003.

Sinais de que a lista está desatualizada, a conferir: algumas dessas declarações
são notoriamente de gerações anteriores do SPED, e outras foram absorvidas por
obrigações mais novas. **Não afirmo quais, porque isso exige conferência em
fonte oficial vigente — e essa conferência é do responsável técnico.**

> Este documento não constitui homologação fiscal. A implementação de qualquer
> cálculo ou obrigação exige regra confirmada em texto oficial vigente, casos de
> referência e validação profissional, conforme AGENTS.md §10.

## O acervo real do escritório, medido em 2026-09-14

O Fred enviou **5.850 XMLs** do acervo. É a primeira vez que este projeto tem
dado real, e ele **desmentiu a ordem de trabalho que eu havia planejado**.

| Documento | Quantidade | Participação |
| --- | --- | --- |
| **NFS-e nacional** (serviço prestado) | 4.979 | **85%** |
| NF-e modelo 55 | 618 — **611 de saída**, 7 de entrada | 11% |
| NFCom modelo 62 | 69, de **um único emitente** | 1% |
| CT-e modelo 57 | 9, todos de entrada | — |
| GTVe modelo 64 | 1 | — |
| Eventos | 186, dos quais 29 são cancelamento | — |

**A consequência é direta:** a DL-010 foi escrita para NF-e e SPED. Na carteira
do Fred, NF-e é 11% do movimento e **nota de serviço prestado é 85%** (RC-66).
Seguir o plano original seria construir primeiro justamente a parte que menos
aparece no trabalho dele.

Nenhuma leitura de manual revelaria isso. É o argumento mais concreto a favor da
regra do AGENTS.md §7 sobre caso de referência real.

### Os cinco achados que viram regra de importador

1. **Duplicidade é real, e de dois tipos** (RC-69): 36 NF-e idênticas em duas
   pastas de clientes diferentes, e 105 NFS-e idênticas **dentro da mesma
   pasta** — a mesma nota catalogada em "Entradas" e em "Saídas" pela ferramenta
   de origem. Deduplicar **por identificador do documento**, nunca por caminho.
2. **Evento órfão é o caso normal** (RC-70): dos 29 cancelamentos, **os 29**
   apontam para documento que não está no acervo. Guardar o evento mesmo sem a
   nota, e aplicá-lo quando ela chegar.
3. **Classificar pelo conteúdo, nunca pelo nome** (RC-71): uma GTVe modelo 64
   estava com `_evento_` no nome, dentro de pasta chamada `DESCONHECIDO`.
4. **O arquivo varia mais do que o leiaute** (RC-75): codificação ausente,
   maiúscula e minúscula, CRLF, minificado e indentado, e **553 CNPJ com zero à
   esquerda** — que sozinho já obriga tratar o campo como texto.
5. **A Reforma Tributária já chegou aos arquivos** (RC-76): 12% das notas de
   serviço trazem o bloco de IBS/CBS. Não é planejamento futuro; é o que entra
   hoje.

### A ressalva que o próprio levantamento fez, e que mantenho

**A amostra não representa o universo** (PE-41): vem de duas origens e **82% das
notas de serviço são de um único município**. O risco concreto é ajustar o
leitor ao provedor de software de uma prefeitura e descobrir isso no cliente
seguinte. Uma segunda amostra, de outro município, vale mais que qualquer
refinamento sobre esta.

## O que já existe no DataLedger

Cruzamento honesto com o que está implementado hoje:

| Capacidade | Situação |
| --- | --- |
| Multiempresa com isolamento | **Pronto e auditado** |
| Cadastro de empresas e estabelecimentos | **Pronto** |
| Permissões por papel | **Pronto** |
| Trilha de auditoria | **Pronto** (com ressalvas no backlog) |
| Plano de contas e partidas dobradas | **Pronto e auditado** |
| Livros Diário e Razão, Balancete e **Balanço Patrimonial** | **Prontos e auditados** (DL-015, DL-017, DL-032 a DL-035) — acrescentado em 2026-09-25 |
| Precisão monetária e política de arredondamento | **Pronto** (DE-010) |
| Competência | **Pronta e auditada** — o BL-15 fechou na DL-016 (trava no servidor) e na DL-031 (a tela). ⚠️ **Corrigido em 2026-09-25:** esta linha dizia "não existe", e era falso desde 2026-09-21 |
| Cadastro de participantes | Não existe |
| Produtos, NCM | Não existe |
| Classificação fiscal | Não existe |
| Escrituração de documentos | Não existe |
| Apuração | Não existe |
| Importação de XML | Não existe |
| Livros e obrigações | Não existe |

A fundação está sólida e a parte fiscal está **integralmente por fazer**.

## Consequência para o planejamento

A ordem técnica natural, se o Fiscal for escolhido, seria:

1. ~~**Competência** (BL-15) — nada fiscal funciona sem período de referência.~~ **JÁ FEITO** (DL-016 + DL-031): o escritório fecha, reabre com motivo e marca como entregue. O primeiro passo da ordem abaixo passou a ser o segundo.
2. **Participantes** — fornecedores e clientes.
3. **Produtos e NCM**.
4. **Classificação fiscal versionada por vigência** — a decisão estrutural.
5. **Importação de XML de NF-e** — é o que elimina digitação e prova valor cedo.
6. **Escrituração de entradas e saídas**.
7. **Apuração de um imposto, de ponta a ponta, com memória de cálculo.**
8. **Um livro e uma obrigação**, escolhidos pelo Fred.

O passo 5 merece destaque: **importar XML entrega valor antes de qualquer
apuração existir**, porque substitui digitação manual desde o primeiro dia. É a
fatia com melhor relação entre esforço e alívio de dor.

## Achado de estratégia: existe um formato de intercâmbio documentado e público

Levantado em 2026-09-12, a partir de diretório público indicado pelo Fred.

O sistema de referência publica, em servidor aberto, a especificação de um
**formato de intercâmbio de importação**: arquivo texto, campos separados por
`|`, registros hierárquicos, **65 tipos de registro**. Ele cobre muito além do
fiscal:

| Faixa | Conteúdo |
| --- | --- |
| `0000`–`0020` | Empresa, clientes, fornecedores, com histórico de alteração cadastral |
| `0100`–`0160` | Produtos, vigências, unidades, composição, saldo, grupos |
| `0200`–`0240` | Contas contábeis, históricos, departamentos, centros de custo |
| `0300`–`0420` | Equipamentos ECF, bens e contas patrimoniais |
| `1000`–`1500` | Notas de **entrada**: impostos, estoque, informações municipais e estaduais, **lançamentos contábeis**, parcelas |
| `2000`–`2500` | Notas de **saída**, mesma estrutura |
| `3000`–`3500` | Notas de **serviço**, mesma estrutura |
| `4000`–`4750` | Reduções Z e cupons fiscais |
| `5100`–`5420` | Recebimentos vinculados a cada tipo de documento |

### Por que isso importa mais que qualquer funcionalidade

O escritório **já opera** com um sistema de gestão de XML que alimenta o sistema
atual (RC-41). Se o DataLedger **ler o mesmo formato de intercâmbio**, esse
sistema passa a alimentar o DataLedger **sem nenhuma mudança do lado do
escritório**.

Isso transforma a adoção: em vez de exigir que o escritório troque a ferramenta
de captura, o DataLedger entra como **mais um destino** do que já é produzido
hoje. Dá para rodar os dois em paralelo e comparar resultado — que é a única
forma responsável de migrar um sistema contábil.

Observe ainda que o formato já carrega **lançamentos contábeis** (`1300`,
`2300`, `3300`) e **parcelas** (`1500`, `2500`, `3500`). Ou seja: a integração
fiscal-contábil-financeiro está prevista no próprio intercâmbio.

### Decisão que cabe ao Fred

Ler um formato de intercâmbio documentado e publicado abertamente é
**interoperabilidade**, categoria diferente de copiar interface ou
funcionalidade. Ainda assim, é decisão de produto com dimensão jurídica, e não a
tomo sozinho.

Recomendação técnica: adotar **os dois caminhos**, com prioridades distintas.

1. **XML de NF-e** como formato primário — é padrão público de governo, sem
   ambiguidade de licença, e é a fonte da verdade. O leiaute vigente deve ser
   obtido no [Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br) e no
   Manual de Orientação do Contribuinte, **não de memória**.
2. **Formato de intercâmbio de terceiros** como caminho de adoção, para que a
   ferramenta que o escritório já usa continue servindo.

## Perguntas que dependem do Fred

Registradas em [requisitos.md](requisitos.md) como pendências:

1. Qual módulo primeiro: **Fiscal** ou outro?
2. Se Fiscal: qual **regime** e qual **imposto** atender primeiro?
3. Quais obrigações da lista estão **vigentes** e são as que o escritório
   realmente entrega?
4. Quais **segmentos especializados** (combustíveis, imobiliário, transporte)
   fazem parte da carteira? Se nenhum, ficam fora e o escopo encolhe bastante.
5. Qual a rotina que **mais consome tempo** hoje no escritório?
