# Casas decimais do valor no registro 6100 do leiaute de importação com separador do sistema de referência — 08/10/2026

Pesquisa do `arquiteto-senior` (Fable) durante a
[DL-077](../../planos/DL-077-importacao-e-exportacao-contabil-em-txt.md), para
desbloquear a exportação e a importação de lançamentos no leiaute do sistema de
referência. Registro da resposta, sem trechos do material do fornecedor (RC-167).

## Resumo

- **Casas decimais: 2** (inferência forte por analogia com os registros irmãos 1300/2300/3300/5530/6110/6130, que declaram `Decimal` + `2`; a tabela do 6100 está em branco tanto no PDF de 12/2018 quanto na página web atual do fornecedor).
- **Forma de escrita: com vírgula como separador decimal** (`5571,24`), **sem** separador de milhar, **sem** zeros à esquerda. Isso está **comprovado** pelo arquivo de exemplo publicado pelo próprio fornecedor — e **contradiz** a leitura de que "valor vai sem vírgula": a regra do `10099` vale para o tipo **Numérico** (inteiros), não para o tipo **Decimal**.
- Grau de segurança: **alto** para a escrita com vírgula; **médio-alto** para 2 casas.

## 1. O que o manual diz (verificado)

PDF baixado de `https://ftpdownload.dominiosistemas.com.br/manuais/Importa%e7%e3o%20Padr%e3o.pdf` (1495 páginas, metadados: Word 2016, criado em 10/12/2018). Extraído com `pdftotext -layout` e `-raw`; os dois concordam.

**Regras gerais (pp. 1224–1225, seção 13.2 do capítulo "Importação Padrão – Leiaute Domínio Sistemas com Separador")**, em minhas palavras:

- A tabela de cada registro tem colunas Campo, Nº, Tipo (Caractere, Numérico ou Data), Casas Decimais (um inteiro), Formato (data `dd/mm/aaaa`), Valor e Comentário.
- Separador: pipe `|`.
- **Numérico**: só inteiros; o exemplo é um valor `100,99` que, por não poder conter vírgula, tem a vírgula cortada e vira `10099`.
- **Casas Decimais**: definido como "tipo de dado Numérico", com o exemplo `Decimal (3)` ilustrado por `150,895` — ou seja, **o próprio exemplo de campo decimal é escrito com vírgula**.
- Observação minha: a lista de tipos enumera Caractere/Numérico/Data, mas as tabelas usam um quarto rótulo, `Decimal`, que a seção só define indiretamente pelo exemplo acima. Essa é a origem da ambiguidade.

**Registro 6100 (pp. 1450–1451)**: o título é "Lançamentos em Lote – Lançamentos – C. de Custos" (título aparentemente copiado do 6110; na web é só "Lançamentos em Lote – Lançamentos"). Campos 2 a 7 — Data do lançamento, Conta a débito, Conta a crédito, **Valor do lançamento (campo 5)**, Código do histórico, Descrição do histórico — estão **sem Tipo e sem Casas Decimais**, tanto em `-layout` quanto em `-raw`. Campos 1, 8, 9 e 10 têm tipo (Caractere/Numérico). Confirmei o mesmo vazio na página web atual do fornecedor (solução 672), portanto não é perda de coluna na extração: a lacuna é do documento.

**Registros análogos no mesmo capítulo (verificado no PDF e na web)** — todos com a mesma estrutura de 9 campos do 6100 (data, débito, crédito, valor, histórico, descrição, usuário, filial):

| Registro | Campo 5 "Valor do lançamento" | Casas |
| --- | --- | --- |
| 1300 (NF entrada – lançamentos) | Decimal | 2 |
| 2300 (NF saída – lançamentos) | Decimal | 2 |
| 3300 (NF serviço – lançamentos) | Decimal | 2 |
| 5530 (cupom – DFC) campo "Valor" | Decimal | 2 |
| 6110 (filho do 6100, rateio C. Custos) "Valor do rateio" | Decimal | 2 |
| 6130 (filho do 6100, DFC) "Valor" | Decimal | 2 |

No capítulo inteiro, contei 467 ocorrências de `Decimal` seguido de número de casas e 35 sem número (p.ex. 5700 e 7100, também em branco). Não há nenhuma linha de exemplo de arquivo (com `|`) no PDF.

## 2. Fontes externas

**Primária (fornecedor) — decisiva.** A página oficial do Portal do Cliente "Leiaute: Domínio Sistemas com Separador" (solução 672) reproduz a mesma tabela e oferece `arquivos_exemplos.zip` (dois `.txt`, datados de 27/10/2015). Baixei e li. O arquivo `exemplo_arquivo__lancamento_lote.txt` tem exatamente três linhas, CRLF, ASCII, **começando com pipe**; a linha do 6100 é, com valores de exemplo do fornecedor (CNPJ fictício `33333333000191`):

_(linha do exemplo do fornecedor omitida deste registro, pela regra RC-167: texto de terceiro não vai para o repositório. Forma, descrita: registro 6100 com barra no início e no fim, data, conta a débito e a crédito por código reduzido, valor com vírgula e duas casas, código e descrição do histórico, usuário, filial e SCP vazios.)_

Campo 5 = `5571,24`: duas casas, vírgula, sem ponto de milhar. Os 10 campos batem com a tabela (9 = filial, 10 = SCP, ambos vazios), e o 6000-pai é `|6000|X||||`. O arquivo de nota de entrada mostra o mesmo padrão em todos os campos `Decimal`: `5571,24`, `17,00`, `0,00`, e também `1,000`, `544,950`, `0,0000` — quantidades de casas diferentes (2, 3, 4) na mesma linha, o que só é possível se a vírgula for literal (num esquema "sem vírgula, casas implícitas", `1,000` e `1,00` seriam indistinguíveis). O registro 1300 do mesmo exemplo (declarado `Decimal 2`) traz `5571,24` idêntico ao 6100.

Ressalva: alguns campos do exemplo 1030 têm mais casas do que a tabela web atual declara (ex.: Quantidade declarada com 2, exemplo com 3) — o exemplo é de 2015 e a tabela web é a vigente; isso não afeta a conclusão sobre a vírgula, mas mostra que o importador parece tolerar casas a mais no texto.

**Secundárias** (nenhuma traz linha 6100 com valor):

- *Secundário* — Omie, "Importando os Lançamentos Contábeis no Sistema Domínio: Leiaute com Separador": só descreve o caminho de menu e nomes dos arquivos gerados (`Dominio_Layout_Padrao_apenas_Registro_6000.txt` etc.); sem exemplo de linha nem regra de formato.
- *Secundário* — Fórum Contábeis, "Layout de Importação para o Domínio Contábil Plus": usuários montam planilhas separadas para 000/6000/6100 e exportam como texto; sem conteúdo de linha; planilhas em Google Drive não acessíveis.
- *Secundário* — GitHub `CaioBaldassaune/conta_giro`: a descrição indexada diz ter exportador no leiaute com separador (0000/6000/6100) com "separadores e casas decimais conferidos no arquivo de exemplo do fornecedor", ainda sem homologação. O repositório devolveu 404/acesso bloqueado nesta sessão; não li o código.
- Páginas do fornecedor 7584 ("importar lançamentos exportados...") e 8814 ("Importação Arquivo Texto", leiaute posicional) foram baixadas mas não analisadas em detalhe por serem outro leiaute; não pesam na conclusão.

## 3. Conclusão

| Item | Resposta | Segurança | Base |
| --- | --- | --- | --- |
| Separador decimal do valor no 6100 | **Vírgula** (`5571,24`); não é "sem vírgula", não é ponto | **Alta** | Arquivo de exemplo oficial do fornecedor; exemplo `150,895` da seção de regras; padrão uniforme em todos os campos Decimal do exemplo de NF |
| Casas decimais | **2** | **Média-alta** | Tabela do 6100 em branco (PDF e web); todos os registros irmãos de lançamento contábil (1300/2300/3300) e filhos (6110/6130) declaram `Decimal 2`; exemplo oficial usa 2 casas |
| Separador de milhar | Nenhum | Alta | Exemplo `5571,24` |
| Sinal / zeros à esquerda | Não observado; exemplo só tem positivo sem padding | — | Não há base; não presumir |

**Reinterpretação da regra "100,99 → 10099":** ela se aplica ao tipo **Numérico** (códigos, quantidades inteiras), que não admite vírgula. Campos `Decimal` são, na prática do fornecedor, escritos com vírgula e com o número de casas indicado na coluna. Quem lê "numérico vai sem vírgula" e aplica ao valor do 6100 gerará `557124`, que o importador leria como R$ 557.124,00 — erro de 100x. Essa era a hipótese implícita na pergunta e **ela está errada** segundo o exemplo oficial.

**O que falta para certeza total:** (a) uma importação real de um arquivo-teste no sistema de referência (não tenho acesso); (b) confirmação se o importador também aceita `5571.24` ou `557124` (não há base para supor que aceite); (c) a tabela do 6100 preenchida pelo fornecedor — a lacuna existe desde 2018 e persiste na web. Não encontrei fonte alguma que afirme "sem vírgula" para o 6100; a única leitura nesse sentido vem da regra geral do tipo Numérico.

**Não determinado:** tratamento de valor negativo ou zero no 6100; limite de dígitos; se o pipe inicial da linha é obrigatório (o exemplo usa; a tabela não diz).

Arquivos de trabalho (somente leitura, fora do repositório): `(área temporária da sessão, fora do repositório)` (`imp.pdf`, `r6100_layout.txt`, `regras_layout.txt`, `sup_672.html`, `exemplos/extr/exemplo_arquivo__lancamento_lote.txt`).

Sources:
- [Manual Importação Padrão (PDF, 12/2018) — Domínio Sistemas](https://ftpdownload.dominiosistemas.com.br/manuais/Importa%e7%e3o%20Padr%e3o.pdf)
- [Leiaute: Domínio Sistemas com Separador — Portal do Cliente (solução 672)](https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=672)
- [arquivos_exemplos.zip — anexo da solução 672](https://sgd.dominiosistemas.com.br/ctsfiles/arquivos_exemplos.zip?id=9429237&ds=centralSolucao&anexosKey=18093aa78d1bb9ecc9a0bf4e3bcf5afe)
- [Omie — Importando os Lançamentos Contábeis no Sistema Domínio: Leiaute com Separador (secundário)](https://ajuda.omie.com.br/pt-BR/articles/9009287-importando-os-lancamentos-contabeis-no-sistema-dominio-leiaute-com-separador)
- [Fórum Contábeis — Layout de Importação para o Domínio Contábil Plus (secundário)](https://www.contabeis.com.br/forum/tecnologia-contabil/251385/layout-de-importacao-para-o-dominio-contabil-plus/)
- [GitHub — CaioBaldassaune/conta_giro (secundário, não acessado)](https://github.com/CaioBaldassaune/conta_giro)
- [Portal do Cliente — solução 7584 (secundário, não analisado)](https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=7584)
- [Portal do Cliente — solução 8814, leiaute posicional (secundário, não analisado)](https://suporte.dominioatendimento.com/central/faces/solucao.html?codigo=8814)
