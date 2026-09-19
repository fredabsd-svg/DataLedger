# DL-027 — O documento emitido: identificação obrigatória e personalização

**Estado:** **planejada.** Aberta em 2026-09-19, a pedido do Fred.
Situação atual em [docs/agents/estado.md](../agents/estado.md).

> **Autorização.** Fred, em 2026-09-19, depois de ler o levantamento:
> *"pode seguir com sua recomendação e escreve o plano da etapa"*. O pedido
> original é dele e está literal em **RC-91**: *"na hora de fazer a impressão
> do relatório podemos criar personalizações … incluindo o logo da empresa …
> pode deixar marcado a impressão do logo do escritório ou não"*.

## Objetivo

Fazer o **documento que sai do sistema** ser do escritório e do cliente — não do
fornecedor —, identificado conforme a **classe** do documento, e personalizável
no que é legítimo personalizar.

Vale para **todos os relatórios do sistema, inclusive de outros módulos**
(**RC-94**), o que torna isto **mecanismo de plataforma** e não recurso da
Contabilidade.

## Por que agora, e qual é o problema real

Três problemas medidos, não supostos:

1. **O relatório impresso ainda sai com a marca do fornecedor.** Medido em PDF
   real na auditoria da rodada 5 da DL-026 (**BL-332**): com as opções **padrão**
   do navegador, o cabeçalho de **toda folha** traz o `<title>`, que termina em
   "DataLedger", mais a URL interna no rodapé. É o vício nacional que a própria
   pesquisa do projeto nomeou.
2. **A identificação obrigatória não é atendível com os dados que existem**
   (**BL-340**): o cadastro de empresa tem `razao_social`, `nome_fantasia`,
   `cnpj`, `ativo` — e mais nada. **Não tem NIRE**, nem endereço. O **RC-93**
   exige NIRE no relatório; e a NBC TG 26 exige **nível de arredondamento**
   (**RC-95**), que também não existe.
3. **Relatório que não declara o critério não se reproduz.** Opções como "com
   saldo ou movimento" mudam o valor; dois documentos do mesmo período podem
   divergir e ambos se chamam "Balancete". O projeto exige conciliação com os
   lançamentos de origem (**RC-19**).

O mapa completo do domínio, com norma citada e fonte datada, está em
[`docs/projeto/personalizacao-de-relatorio.md`](../projeto/personalizacao-de-relatorio.md).
**Leitura obrigatória antes de implementar qualquer fatia desta etapa.**

## A decisão estruturante: três classes de documento

| Classe | Exemplos | Forma fixada por | Personalização |
| --- | --- | --- | --- |
| **1 — Conferência** | Balancete de verificação, razão de conferência | Nada. Regra é do escritório | Ampla |
| **2 — Demonstração** | Balanço, DRE, DMPL, DFC, notas | NBC TG 26 (R5), item 51, **em cada página** (item 52) | Só fora do bloco obrigatório |
| **3 — Livro** | Diário e Razão **na forma de livro** | NBC ITG 2000 (R1), itens 5, 9, 10, 13 | Quase nenhuma |

**Todo documento imprimível declara a sua classe, e quem não declarar reprova a
integração contínua.** É o mesmo mecanismo que a DL-026 já provou funcionar com
o "momento da verdade": módulo novo que aparece sem a sua linha **falha o
build**. Reusar o padrão é deliberado — ele sobreviveu a sabotagem de auditor.

⚠️ **Esta etapa NÃO emite documento de classe 3.** Livro contábil depende de
**PE-52** (qual legislação exige autenticação do livro digital), que ainda não
foi levantada em fonte oficial. A classe existe no modelo **para poder ser
proibida**: a guarda recusa personalização em documento declarado como livro.
Desenhar a fronteira agora é barato; descobrir que a personalização já estava
ligada lá dentro, depois, não é.

## Duas decisões que eu tomei sob a autorização do Fred, e que ele pode reverter

Estavam esperando resposta dele e destravam a DL-026. Ele autorizou seguir com
a minha recomendação, então decido e registro:

1. **BL-332 — o `<title>` perde o nome do fornecedor.** Passa a ser
   `<nome do relatório> — <razão social do cliente>`, sem sufixo. É o único
   canal daquela faixa que o projeto controla; data e URL são do navegador e
   ficam **declaradas como limite**, não escondidas.
2. **BL-338 — o documento identifica o escritório e o profissional responsável,
   não o usuário operador.** Hoje o papel começa por "USUÁRIO fulano", acima do
   timbre. O fundamento não é estético: a NBC ITG 2000, item 12, atribui a
   emissão de relatórios à **responsabilidade exclusiva do profissional da
   contabilidade habilitado** — é ele que identifica o documento. Quem operou a
   tela é **trilha de auditoria**, não identificação do documento, e a trilha já
   existe em `apps/auditoria/`.

## Fatias, e a ordem tem motivo

| Fatia | Entrega | Por que nesta ordem |
| --- | --- | --- |
| **A — Identificação** | Classe do documento; bloco obrigatório por classe; campos que faltam (**NIRE**, **nível de arredondamento**); regra do vazio; guarda que reprova classe não declarada e bloco incompleto | **Pré-requisito de correção.** O RC-93 não é atendível sem os campos (BL-340). Sem isto, tudo o mais é enfeite sobre base incompleta |
| **B — Preferências sem imagem** | Carimbo de emissão; **critério de apuração impresso**; ocultar contas sem movimento; via de conferência × oficial com marca d'água; **bloquear emissão quando não fecha**; dispensar coluna de exercício anterior | Valor visível cedo, risco baixo, nenhuma dependência de arquivo enviado por usuário |
| **C — Logotipo** | Envio no cadastro da empresa e no do escritório; escolha na emissão entre escritório, cliente ou nenhum (**RC-92**) | É o pedido original do Fred, e é a fatia de **maior risco de segurança** — merece entrar com a fundação pronta e atenção inteira |
| **D — Pré-visualização** | A folha se redesenhando ao lado dos controles, **sem JavaScript obrigatório** | É o que impede esta etapa de virar a janela de quarenta caixinhas que o levantamento registrou como anti-padrão |

**Se o Fred preferir o logotipo primeiro, a ordem muda** — é decisão dele. O
custo de inverter é que a fatia C entra antes de existir bloco de identificação
correto, e o logotipo vai decorar um cabeçalho que ainda não cumpre o RC-93.

## O que entra, com o motivo

Retirado do catálogo do mapa do domínio, faixa "adotar":

1. **Carimbo de data e hora da emissão.**
2. **Critério de apuração impresso no documento** — princípio nosso, não visto
   em nenhum sistema examinado.
3. **Bloquear a emissão quando débito ≠ crédito** — o produto já calcula "Fecha
   / Não fecha"; falta transformar em trava.
4. **Marca d'água** ("RASCUNHO", "CONFIDENCIAL", texto livre).
5. **Ocultar contas sem movimento.**
6. **Dispensar a coluna do exercício anterior** quando não existe.
7. **Logotipo do escritório ou do cliente, ou nenhum, escolhido na emissão.**
8. **Via de conferência × via oficial.**

## O que NÃO entra, e por quê

| Fora | Motivo |
| --- | --- |
| **Matriz de caixinhas por relatório × por campo** | Permitiria o CNPJ sair no Balancete e não no Razão, da mesma empresa, no mesmo mês. Contraria a direção de arte e o próprio **RC-93**: identificação é obrigação, não escolha |
| **Escolher colunas, ordem e largura** | Capacidade boa, mas esconder coluna **muda a conferência** — sem a coluna de movimento próprio não se refaz a soma que bate com o rodapé. Precisa de desenho próprio e entra depois, com a regra de quais colunas sustentam conciliação |
| **Emissão de livro contábil (classe 3)** | Depende de **PE-52**. A classe entra só para ser **proibida** |
| **Assinatura com certificado digital** | Etapa própria, grande, com dimensão normativa |
| **Legenda de nível de *assurance*** | Regime profissional dos EUA. Copiar sem base normativa brasileira seria inventar exigência |
| **Temas de marca salvos, idioma, conversão de moeda** | Complexidade sem problema correspondente hoje |

## Restrições que eliminam

| # | Restrição | Origem |
| --- | --- | --- |
| R1 | Django renderizado no servidor, sem SPA | HI-04, RC-34 |
| R2 | CSS próprio, nenhuma biblioteca visual externa | **DE-011** |
| R3 | Sem etapa de build | Realidade do projeto |
| R4 | **JavaScript é enfeite** — a pré-visualização funciona sem ele | Critério 6 da DL-026, acessibilidade |
| R5 | Nada de dependência nova em `requirements/` por ferramenta de bancada | Padrão de `scripts/medir_impressao.py` |
| R6 | **Isolamento entre escritórios vale para arquivo também** | Regra permanente; e é a razão de eu ter adiado o logotipo antes |
| R7 | Autorização verificada **no servidor** | RC-17 |
| R8 | Parênteses continuam o padrão para saldo invertido | **RC-90** — um traço vira "+" com um toque de caneta; um parêntese não se desfaz |

## Critérios de aceite

1. **Todo documento imprimível declara a sua classe**, e documento sem classe
   declarada **reprova a integração contínua** — com controle positivo provando
   a reprovação.
2. **O bloco de identificação obrigatório sai completo, por classe**, e a guarda
   deriva a lista **do requisito** (RC-93, RC-95), não do template. Campo
   obrigatório que sumir do template reprova.
3. **Classe 2 repete a identificação em cada página**, que é a forma prescrita
   pelo item 52 da NBC TG 26 — medido em PDF real, não inspecionado.
4. **Personalização não alcança documento de classe 3.** Sabotagem que tente
   aplicar personalização a um documento declarado como livro **falha**.
5. **NIRE e nível de arredondamento existem no cadastro**, com a **regra do
   vazio escrita** — empresa sem NIRE imprime exatamente o que a regra disser,
   e a regra é do Fred, não minha.
6. **O critério de apuração escolhido sai impresso no documento.** Dois
   documentos gerados com critérios diferentes são distinguíveis **pelo papel**,
   sem consultar o sistema.
7. **O logotipo de um escritório nunca aparece no documento de outro.** Teste de
   isolamento no caminho HTTP, com dois escritórios, e o arquivo servido por
   view que verifica o vínculo — **nunca** por URL estática adivinhável.
8. **Arquivo enviado é validado pelo conteúdo, não pela extensão**, com tamanho
   máximo, e um arquivo que se diz imagem e não é **é recusado** — com teste.
9. **A trava de emissão quando não fecha funciona**, e a mensagem diz o que
   fazer, não só que falhou.
10. **A pré-visualização funciona com JavaScript desligado.**
11. **Nada do que DL-009, DL-017 e DL-026 conquistaram regride** — contraste
    medido, foco visível, `D`/`C` explícito, totalizador, densidade, e a
    varredura de interface continua verde.
12. **A medição de impressão usa o instrumento versionado**
    (`scripts/medir_impressao.py`), e os números vão para o contrato — não só
    para o relatório da tarefa. Foi o achado **M4** da rodada 5.
13. **Auditoria independente da versão integrada.**

## Riscos declarados

1. **Arquivo enviado por usuário é a superfície de ataque mais comum de um
   sistema web.** Mitigação: validação por conteúdo, tamanho máximo, servir por
   view autorizada, nome de arquivo não adivinhável. Se algo aqui ficar em
   dúvida, a fatia C **para** e vira pergunta.
2. **A etapa pode inchar.** O catálogo levantado tem mais de vinte capacidades
   e este plano adota oito. A lista do que ficou fora, com motivo, está acima
   justamente para que "mais uma opçãozinha" seja uma **decisão registrada**,
   não um acréscimo silencioso.
3. **Personalização que muda número.** Tratada pelo critério 6. É o risco que
   nenhum sistema examinado trata.
4. **Fronteira normativa.** PE-48, PE-51, PE-52 e HI-11 seguem abertas. A etapa
   anda no recorte estreito — e a guarda do critério 4 existe para que o dia em
   que o recorte alargar seja uma **decisão**, não um descuido.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` | `apps/documentos/**` (novo), `apps/empresas/**`, `apps/tenancy/**`, migrações, serviços |
| `especialista-frontend` | `templates/**`, `static/**`, testes de interface, `docs/assets/design/gauntlet/juiz.py` |
| `arquiteto-senior` | `docs/**`, contratos, integração |
| `auditor-qa` | Nada — audita a versão integrada |

## Git

- **Branch de trabalho:** a definir na abertura da fatia A.
- **Branch de destino:** `main`, por PR.
- **Pré-requisito:** a DL-026 fecha antes. Esta etapa depende do timbre de texto
  que ela entregou, e duas decisões desta etapa (BL-332 e BL-338) **destravam**
  o fechamento dela.
