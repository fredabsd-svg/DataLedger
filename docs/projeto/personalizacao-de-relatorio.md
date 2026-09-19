# Personalização de relatório — mapa do domínio

Levantamento feito em **2026-09-19**, a pedido do Fred, para ampliar o conjunto
de personalizações de relatório do DataLedger.

## O que este documento é, e o que não é

**É** o mapa do que o domínio exige e do que o mercado oferece, com fonte e
data de cada item, para que a escolha do que implementar seja feita com
evidência e não com memória.

**Não é** o plano da etapa. O plano nasce depois que o Fred cortar desta lista.
O estado do trabalho mora em [docs/agents/estado.md](../agents/estado.md), como
sempre; os requisitos confirmados, as hipóteses e as pendências moram em
[requisitos.md](requisitos.md). Este arquivo não repete nenhum dos dois.

⚠️ **Regra que governou o levantamento**
([fontes-de-referencia.md](fontes-de-referencia.md)): material de terceiros não
entra no repositório. As capturas de tela consultadas ficaram em área
temporária, fora do projeto, e o que está escrito aqui é **entendimento nosso,
em nossas palavras**. A orientação do Fred continua valendo: ***"não faça
igual"***.

## 1. A descoberta que reorganiza o problema: são três classes de documento

O pedido original era "o que mais dá para personalizar". A pergunta certa
acabou sendo **outra**: *em que documento?* Porque a resposta muda por completo.

| Classe | Exemplos | O que fixa a forma | Quanto a personalização pode mexer |
| --- | --- | --- | --- |
| **1. Relatório de conferência** | Balancete de verificação, razão de conferência, listagens de apoio | **Nada.** Nenhuma norma contábil fixa o cabeçalho de um balancete de verificação | Muito — a regra aqui é do escritório |
| **2. Demonstração contábil** | Balanço, DRE, DMPL, DFC e notas | NBC TG 26 (R5), item 51, e o item 52 diz **como** se cumpre | Só fora do bloco obrigatório, que sai **em cada página** |
| **3. Livro contábil** | Diário e Razão **na forma de livro** | NBC ITG 2000 (R1), itens 5, 9, 10, 13 | Quase nada — forma, numeração, termos e assinaturas são prescritos |

O detalhe normativo de cada uma, com item citado e data de consulta, está em
**RC-95** e **RC-96** de [requisitos.md](requisitos.md). Não repito aqui.

**Por que a separação importa mais que qualquer item de catálogo:** uma lista
única de personalizações produz um de dois estragos. Ou o balancete do dia a
dia passa a carregar exigência de livro — ruído diário —, ou **o livro herda a
liberdade do balancete**, e aí a personalização pode descaracterizar um
documento que tem forma prescrita. A segunda é a grave, e é silenciosa.

**Confirmação independente, e ela vale registro:** um fornecedor grande do
mercado brasileiro declara que os relatórios contábeis legais (Balancete,
Diário, Balanço, DRE, DMPL, DFC, Razão) **não podem** ser customizados além da
margem esquerda, para encadernação, *"devido a exigências legais"*. Chegou à
mesma conclusão por outro caminho. ⚠️ **A alegação é do fornecedor, não de
fonte oficial** — está registrada como pendência a confirmar, e **não** deve ser
usada por nós como fundamento normativo (TOTVS Protheus, documentação pública,
consultado em 2026-09-19).

## 2. Catálogo de capacidades

Classificação de confiança: **Visto** (li a documentação do fornecedor ou
examinei a captura de tela), **Relatado** (alguém diz que existe, não
confirmei), **Presumido** (inferência nossa, marcada como tal).

### 2.1 Adotar — resolvem problema real e são baratas

| Capacidade | O que o contador decide | Por que | Confiança |
| --- | --- | --- | --- |
| **Carimbo de emissão** | Se o relatório traz data e hora de geração | Dois balancetes do mesmo período divergem se houve lançamento entre as emissões. Sem carimbo, não se sabe qual é qual | **Visto** (Alterdata, 2026-09-19) |
| **Bloquear emissão quando débito ≠ crédito** | Impedir que saia relatório de período que não fecha | O DataLedger **já** calcula "Fecha / Não fecha". Isto transforma a conferência em pré-condição da emissão, em vez de aviso que se ignora | **Visto** (Alterdata, 2026-09-19) |
| **Marca d'água** | "RASCUNHO", "CONFIDENCIAL", texto livre; em todas as páginas ou só na primeira | Balancete provisório circula antes do fechamento; documento sai do escritório para banco ou sócio. É o sinal que não se apaga por engano na impressão | **Visto** (MYOB, 2026-09-19) |
| **Ocultar linhas sem movimento** | Não imprimir conta que não teve lançamento no período | Plano de contas brasileiro é extenso; a conta continua existindo, só não ocupa papel zerada | **Visto** (QuickBooks, 2026-09-19) |
| **Dispensar a coluna do exercício anterior** | Quando não existe ou não se aplica | Empresa recém-aberta não tem comparativo, e coluna vazia é pior que coluna ausente | **Visto** (CaseWare, 2026-09-19) |
| **Casas decimais e forma do negativo** | Quantas casas; parênteses, sinal ou cor | ⚠️ Com um limite nosso: **RC-90 fixou parênteses** como convenção do produto, e por um motivo que não é estético — um traço vira "+" com um toque de caneta, um parêntese não se desfaz. Se virar opção, o padrão continua parênteses, e a exportação para planilha é o caso que justifica o sinal | **Visto** (QuickBooks e Xero, 2026-09-19) |

### 2.2 Adotar com cuidado — úteis, mas mexem em mais do que parece

| Capacidade | O que o contador decide | O cuidado | Confiança |
| --- | --- | --- | --- |
| **Escolher colunas, ordem e largura** | Quais colunas do balancete saem impressas, em que ordem, com que largura | É a capacidade que mais amplia o que já temos, porque separa *quais dados existem* de *quais aparecem*. O cuidado: esconder coluna muda a **conferência** — um balancete sem a coluna de movimento próprio não permite refazer a soma que concilia com o rodapé. Coluna que sustenta conciliação não deveria ser removível, ou o documento tem que dizer que foi removida | **Visto** — examinei a tela (TOTVS Linha RM, 2026-09-19) |
| **Bloco de assinatura composto por variáveis** | Monta o texto de assinatura do sócio e do contador a partir de campos (nome, CPF, vínculo, CRC), em vez de texto fixo | Resolve dor real de escritório com muitos clientes de composição societária diferente. O cuidado: isto é **classe 3** — assinatura de titular e de contabilista habilitado é forma de livro (ITG 2000, itens 9 e 13), não enfeite | **Visto** (Alterdata, 2026-09-19) |
| **Escolher o contador assinante por emissão** | Qual profissional, entre os cadastrados, assina aquela emissão | Escritório com vários responsáveis técnicos, ou troca de responsável no tempo. O cuidado: quem assina é **responsabilidade profissional**, então a escolha precisa de trilha — quem escolheu, quando | **Visto** (Omie, 2026-09-19) |
| **Via de conferência x via oficial** | Emitir rascunho de trabalho ou a via definitiva | Espelha no **relatório** a distinção rascunho/efetivado que o domínio já exige do lançamento. Combina naturalmente com marca d'água | **Visto** (Omie, 2026-09-19) |
| **Título e observação livre** | Trocar o título e acrescentar um texto curto de contexto | Barato e útil. O cuidado: texto livre num documento contábil é superfície de abuso — não pode substituir nem contradizer a identificação obrigatória, e tem que ser distinguível dela | **Visto** (TOTVS Linha RM, 2026-09-19) |

### 2.3 Não adotar — ou não agora, com o motivo escrito

| Capacidade | Por que não |
| --- | --- |
| **Matriz de caixinhas por relatório × por campo** (imprimir CNPJ no Diário? no Balanço? no Razão?) | Permite que o CNPJ saia no Balancete e não saia no Razão, **da mesma empresa, no mesmo mês**. A direção de arte proíbe o sistema mudar de cara entre telas do mesmo módulo; e o RC-93 já decidiu que identificação é **obrigação, não escolha** — se é obrigação, não há caixinha |
| **Legenda de nível de *assurance* por página** | É regime profissional dos Estados Unidos (SSARS/AICPA). Copiar a mecânica sem base normativa brasileira equivalente seria **inventar exigência**, o que o AGENTS.md proíbe |
| **Biblioteca ampla de notas explicativas com visibilidade nota a nota** | Pressupõe rotina de demonstração formal com notas extensas. Fora do que o escritório emite no dia a dia; vira ruído |
| **Temas de marca salvos por cliente** | O RC-92 já resolve o caso central com três estados na emissão. Acrescentar temas salvos é complexidade sem problema correspondente **hoje** |
| **Idioma do relatório e conversão de moeda** | Servem a subsidiária de grupo estrangeiro. Público pequeno para o custo, **agora** |

## 3. Anti-padrões medidos

Valem tanto quanto a lista de boas ideias — o plano da DL-026 já registrou um
anti-padrão de concorrente como achado útil.

1. **Quarenta decisões numa janela só.** A tela de opções de balancete de um
   concorrente reúne, numa caixa cinza, opções de cálculo, de conteúdo, de
   layout, de assinatura e de paginação — e o usuário só descobre o resultado
   depois de imprimir. **A resposta para quarenta opções não é quarenta opções
   com nome melhor: é ver o papel enquanto se mexe.** Um produto internacional
   resolve exatamente assim, com a folha se redesenhando ao lado dos controles
   (examinei a tela; QuickBooks Online, 2026-09-19).

2. **Opção de aparência e opção de cálculo na mesma lista.** Numa tela
   examinada, campos que só mudam o que aparece convivem, numa lista plana de
   caixinhas, com um seletor que **muda a data de referência do cálculo**. É
   assim que alguém altera o resultado achando que mexeu na apresentação
   (Xero, 2026-09-19).

3. **"Exporte e resolva fora do sistema."** A saída oficial recomendada por um
   fornecedor para colocar marca d'água é exportar para planilha e editar lá.
   Isso tira do sistema a rastreabilidade do documento emitido — e é a mesma
   classe de problema que o projeto já combate na escrituração.

## 4. O princípio que eu proponho, e que não veio de concorrente nenhum

**O documento diz com que critérios foi gerado.**

Opções como *"com saldo ou movimento"*, *"desconsidera o encerramento do
exercício"* ou *"aglutina contas de clientes"* **mudam o que o número
significa**. Dois balancetes do mesmo período, da mesma empresa, com marcações
diferentes, mostram valores diferentes — e os dois se chamam "Balancete".

O projeto exige que relatório concilie com os lançamentos de origem (**RC-19**).
Relatório que não declara o critério **não se reproduz**, e o que não se
reproduz não concilia.

Então: critério escolhido é **impresso no documento**, não fica só na cabeça de
quem clicou. Nenhum dos sistemas examinados faz isso.

## 5. O que falta decidir

Em [requisitos.md](requisitos.md), e é do Fred:

- **HI-11** — a separação em três classes corresponde à prática do escritório?
- **HI-12** — a lista de identificação do relatório de conferência, item a item.
- **PE-50** — formato, tamanho e proporção do logotipo.
- **PE-52** — qual legislação exige autenticação de livro digital.
- **BL-340** — NIRE e nível de arredondamento **não existem** no cadastro, e a
  obrigação do RC-93 depende deles.

## 6. Fontes

Todas consultadas em **2026-09-19**. Normas em fonte oficial; produtos em
documentação pública do próprio fornecedor.

- [NBC TG 26 (R5)](https://www1.cfc.org.br/sisweb/SRE/docs/NBCTG26(R5).pdf) — CFC, itens 49 a 53.
- [NBC ITG 2000 (R1)](https://www1.cfc.org.br/sisweb/SRE/docs/ITG2000(R1).pdf) — CFC, itens 5, 9, 10, 12, 13, 14.
- Documentação pública de Alterdata, Omie, TOTVS (Linha RM e Protheus), QuickBooks Online, Xero, MYOB e CaseWare.

⚠️ **Fontes que não abriram**, registradas para ninguém repetir a tentativa: a
base de soluções do fornecedor de referência continua ilegível por agente (o
limite já estava documentado na
[fontes-de-referencia.md](fontes-de-referencia.md) desde 2026-09-13); artigos
específicos de TOTVS e Sankhya responderam **403**; e um artigo da Consistem é
montado por JavaScript, com só o menu legível.

**Auditoria de software não substitui a validação profissional das regras
contábeis e legais.** Os itens normativos deste documento foram lidos na fonte,
mas a leitura profissional é do Fred.
