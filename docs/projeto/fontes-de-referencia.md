# Fontes de referência do domínio

Onde buscar informação de domínio contábil-fiscal ao planejar ou implementar,
e como usá-la sem copiar.

Registrado a pedido do Fred em 2026-09-12, para que sessões futuras não
precisem redescobrir.

## Regra de uso, antes de tudo

Estas fontes servem para entender **o que** o escritório precisa e **como o
domínio funciona**. Não servem para copiar texto, telas, nomenclatura de menu
ou estrutura de interface.

- **Nada de material de terceiros entra neste repositório**, nem em trechos.
- O que entra é **requisito escrito por nós**, em nossas palavras.
- Formato de intercâmbio documentado é caso à parte: ler um formato publicado
  para interoperar é diferente de copiar produto. Ainda assim, ver a decisão
  pendente no [mapa funcional](mapa-funcional-fiscal.md).

Orientação do Fred: *"não faça igual"*. É também o que o
[README](../../README.md) já registrava.

## Regra do Fred, de 2026-09-20: consulte ANTES de perguntar

> *"Esse tipo de dúvida você poderia tirar aqueles manuais que eu te passei"*

Dito depois de eu levar a ele uma pergunta sobre **rotina do sistema de
referência** — como o código reduzido da conta é atribuído — que o manual
responde em uma frase.

**A regra que fica:** antes de abrir pendência para o Fred, verificar se a
dúvida é de **rotina do domínio** ou de **decisão dele**.

| Tipo de dúvida | Onde se resolve |
| --- | --- |
| Como o sistema de referência se comporta; o que significa um campo; qual é a rotina usual do escritório | **Manual**, e depois pesquisa na internet — nunca o Fred primeiro |
| Regra contábil ou exigência normativa | **Fonte oficial** (CFC, Receita), com item e vigência citados |
| O que o escritório **dele** faz; o que ele quer que o produto faça; trade-off de produto | **Só o Fred** |

⚠️ **E o manual pode CORRIGIR a hipótese, não só confirmá-la** — foi o que
aconteceu: eu presumira que o usuário não escolhe o código reduzido, e o manual
diz que ele pode alterá-lo (HI-15). Perguntar ao Fred teria gasto uma rodada
dele para chegar a uma resposta que estava escrita.

## 1. Manuais dos módulos do sistema de referência

Diretório público indicado pelo Fred:

```
https://ftpdownload.dominiosistemas.com.br/manuais/
https://download.dominiosistemas.com.br/manuais/
```

⚠️ **Dois hosts, o mesmo diretório.** O segundo foi indicado pelo Fred em
2026-09-25; **medi os dois e ambos responderam `200`**. Registro os dois porque
endereço que cai é o motivo mais bobo de uma consulta obrigatória ser pulada.

Contém manual de **cada módulo**, útil como mapa de capacidades quando formos
planejar o módulo correspondente:

| Arquivo | Serve para planejar |
| --- | --- |
| `Domínio Escrita Fiscal.pdf` | Fiscal — **já analisado**, ver [mapa funcional](mapa-funcional-fiscal.md) |
| `Domínio Contabilidade.pdf` | Contabilidade — **já analisado**, ver [mapa funcional contábil](mapa-funcional-contabil.md) |
| `Domínio Folha.pdf` | Folha de pagamento |
| `Domínio Honorários.pdf` | Honorários |
| `Domínio Processos.pdf` | Processos e paralegal |
| `Domínio Patrimônio.pdf` | Ativo imobilizado e depreciação |
| `Domínio Lalur.pdf` | Apuração do lucro real |
| `Domínio Ponto Eletrônico.pdf` | Ponto, ligado a Folha |
| `Domínio Registro.pdf`, `Domínio Protocolo.pdf` | Documentos e protocolo |
| `Domínio Auditoria.pdf` | Auditoria interna |
| **`Importação Padrão.pdf`** | **Formato de intercâmbio** — o mais relevante hoje |
| **`leiautes.zip`** | Leiautes de importação: produtos, notas de entrada e de saída |

**Atenção à data.** O manual fiscal analisado é de **2018**. Os demais
provavelmente também. Serve como mapa de **capacidades**, nunca como fonte de
**regra tributária vigente**.

## 1.1 Catálogo de 120 relatórios contábeis, entregue pelo Fred em 2026-09-20

Manual técnico-funcional, edição de **20/09/2026**, com 120 tipos de relatório
em 10 grupos. **Não está no repositório** e não deve entrar, como todo material
de terceiro. A análise dele contra o nosso código está em
[catalogo-de-relatorios.md](catalogo-de-relatorios.md).

⚠️ **Classifique-o certo, porque ele é melhor que um manual de concorrente e
ainda assim NÃO é norma.** Ele **cita** as fontes oficiais corretas (Lei
6.404/76, CPC, NBC, SPED, eSocial, FGTS Digital) com endereço, o que o torna um
bom **índice para chegar à fonte**. Mas o próprio documento declara, no fecho,
que **não é leiaute oficial de nenhuma obrigação nem opinião profissional**, e
alerta na abertura que *"não existe uma lista oficial de '120 demonstrações
obrigatórias'"* e que a obrigatoriedade **depende da entidade, do porte, do setor
e do exercício**.

| Serve para | Não serve para |
| --- | --- |
| Escopo: que relatórios existem, e o que cada um mostra | Item, vigência, prazo, alíquota ou leiaute |
| Rotina: de onde vêm os dados, o que se confere | Fundamentar comportamento do produto |
| **Índice** para achar a fonte oficial certa | Substituir a consulta a essa fonte |

**O que eu tirei dele e vale mais que a lista** é uma frase de **arquitetura**:
os 120 relatórios saem de **uma** cadeia (transações → lançamentos e plano de
contas → Diário e Razão → **saldos e conciliações** → demonstrações e
indicadores), e *"não são necessárias 120 bases de dados independentes"*. Isso
mudou a pergunta que eu havia levado ao Fred — ver §1 do
[catalogo-de-relatorios.md](catalogo-de-relatorios.md).

## 2. Pesquisa na internet — técnica indicada pelo Fred

> Para dúvida sobre o sistema de referência ou sobre a rotina do domínio,
> pesquisar **"domínio sistemas" + a dúvida**. A base de conhecimento e os
> materiais de treinamento do fornecedor costumam responder.

Use para entender **conceito e rotina** — o que é um acumulador, como se
concilia uma apuração, o que o contador espera ver numa conferência.

**Não use para obter regra tributária vigente.** Conteúdo de fornecedor
envelhece e não é fonte oficial.

### Limite técnico descoberto em 2026-09-13

A base de soluções do fornecedor (`suporte.dominioatendimento.com`, páginas do
tipo `solucao.html?codigo=N`) **não é legível por agente**. As páginas respondem
200, mas o corpo do artigo é montado por JavaScript com sessão autenticada:
`curl` recebe a casca, o `WebFetch` recebe 403, e mesmo um navegador sem sessão
devolve **exatamente o mesmo HTML para códigos diferentes** — verificado com
três códigos distintos, todos com o mesmo tamanho em bytes.

Consequência prática: quando o Fred indicar uma solução dessa base, ou ele cola
o conteúdo, ou o entendimento vem de outra fonte. **Uma delas funciona**: os
artigos que aparecem nos resultados de busca pública trazem resumo utilizável, e
os **manuais em PDF do diretório público** (seção 1) cobrem o mesmo assunto com
mais profundidade.

## 3. Fontes oficiais — obrigatórias para qualquer cálculo

Para **toda** regra que vire cálculo, alíquota, prazo, leiaute de obrigação ou
validação, a fonte tem de ser oficial e **vigente**:

| Assunto | Fonte |
| --- | --- |
| NF-e, NFC-e: leiaute, notas técnicas, regras de validação | [Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br) e o Manual de Orientação do Contribuinte |
| SPED (Fiscal, Contribuições, ECD, ECF), EFD-Reinf | [Portal do SPED](http://sped.rfb.gov.br) |
| Tributos federais, obrigações, e-CAC | [Receita Federal](https://www.gov.br/receitafederal) |
| ICMS, convênios e protocolos | [CONFAZ](https://www.confaz.fazenda.gov.br) e a SEFAZ do estado |
| ISS | Legislação do **município**, que varia caso a caso |
| Folha, eSocial, FGTS | Manuais oficiais do eSocial e legislação trabalhista |
| Arredondamento | Ver [DE-010](decisoes.md), que já levantou as fontes por obrigação |

Regra do [AGENTS.md](../../AGENTS.md) §10 que vale repetir: **não inventar
alíquota, incidência, prazo, fórmula ou leiaute**. Regra destinada a uso real
exige caso de referência e validação do responsável técnico — o Fred.

## 4. Como registrar o que for pesquisado

Ao usar qualquer destas fontes:

1. Registre **a fonte e a data** da consulta junto do requisito.
2. Classifique como **confirmado**, **hipótese** ou **pendência** em
   [requisitos.md](requisitos.md).
3. Se for regra com vigência, registre **a vigência**, não só o valor.
4. Material de terceiros fica **fora do repositório**. Baixe para área
   temporária, extraia o entendimento, escreva o requisito com suas palavras.

## 5. Sobre validade no tempo

A **Reforma Tributária do Consumo** está em implantação e altera de forma
profunda o cenário de tributos sobre consumo. Qualquer levantamento feito sobre
material antigo carrega esse risco.

Consequência prática de engenharia, já decidida em
[DE-010](decisoes.md): regra tributária é **dado versionado por vigência**,
não código. Um sistema que exige alteração de código a cada norma nova não
sobrevive a uma reforma.
