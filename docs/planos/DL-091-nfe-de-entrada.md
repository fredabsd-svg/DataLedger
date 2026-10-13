# DL-091 — Fiscal: escrituração das NF-e de entrada (compras), corte 1

**Demanda:** roteiro do fiscal, linha 18 do
[DL-067](DL-067-plano-do-modulo-fiscal.md) ("NF-e de entrada, compras e
créditos"), sob a ordem permanente do Fred (RC-164, RC-175, RC-178).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1), porque a
classificação da entrada não pode contaminar receita, RBT12, pré-DAS nem
Presumido. A auditoria faz uma rodada, uma correção e uma reconferência.

## Base

- [Mapa do que o código faz com a NF-e de entrada](../projeto/mapa-nfe-de-entrada-2026-10-13.md),
  de 13/10/2026. A compra já é recebida, vinculada à empresa destinatária e
  tem os itens lidos; a escrituração a recusa de propósito (HI-117).
- [Consulta ao contador-senior sobre a NF-e de entrada](../projeto/consultas/2026-10-13-contador-senior-nfe-de-entrada.md),
  de 13/10/2026.
  - Leu no Planalto a LC 87 (arts. 20, 23 e 33), a LC 123 (art. 13, § 1º,
    XIII, e art. 23) e a LC 192.
  - **Não** conseguiu ler a legislação do Tocantins: o site da SEFAZ-TO
    estava fora do ar, e a única cópia alcançada é de 2013.
  - Hipóteses HI-154 a HI-158; perguntas ao Fred na PE-93, que não bloqueia.

## O problema

O escritório recebe as notas de compra dos clientes e não consegue
escriturá-las. Sem a entrada classificada, nada do que vem depois existe:
crédito de ICMS, ST, DIFAL, livro de entradas, custo e integração contábil.
Para o optante do Simples, a compra de outro estado pode gerar antecipação ou
DIFAL fora do DAS, que vence no mês, e hoje ninguém vê isso no produto.

## Escopo do corte 1

**Regra de ouro:** nada de ICMS estadual calculado. O produto classifica,
guarda o que a nota destaca e **avisa**; não apura, não usa alíquota do
Tocantins e não gera guia (HI-54, HI-55).

1. **Elegibilidade.**
   - Tipo novo de escrituração `ENTRADA` para a empresa **destinatária** de
     NF-e modelo 55 com `finNFe` 1.
   - `finNFe` 4 continua `DEVOLUCAO` (devolução de venda, DL-081). A mesma
     nota nunca tem duas escriturações ativas.
   - **Recusas com nome:**
     - NFC-e (modelo 65) em que a empresa é destinatária;
     - `tpNF` 0 emitida por terceiro em que a empresa é destinatária e
       `finNFe` diferente de 4;
     - ~~`finNFe` 4 em saída própria com CFOP de devolução de compra~~:
     **retirada em 13/10/2026** (ver "Correção do contrato" abaixo).
   - `finNFe` 2 e 3 de terceiro ficam como hoje (fora), com o motivo.
2. **Competência pela data de entrada.**
   - A escrituração de entrada tem **data de entrada**, obrigatória,
     sugerida igual à data de emissão.
   - A competência é o mês da data de entrada. Data de entrada anterior à
     emissão é recusada.
   - É rotina do sistema de referência e hipótese até o Fred confirmar
     (HI-158, PE-93).
3. **Naturezas de entrada por item** (catálogo fechado, todas fora da
   receita):

   | Natureza | Exemplos de CFOP de entrada |
   | --- | --- |
   | E1 compra para comercialização | 1.102, 2.102, 3.102 |
   | E2 compra para industrialização | 1.101, 2.101 |
   | E3 compra com ICMS-ST | 1.403, 2.403, 1.401 |
   | E4 uso ou consumo | 1.556, 2.556, 1.407 |
   | E5 ativo imobilizado | 1.551, 2.551, 1.406 |
   | E6 combustível ou lubrificante para revenda | 1.652, 2.652 |
   | E7 combustível para consumo próprio | 1.653, 2.653 |
   | E8 transferência recebida | 1.151, 1.152, 2.152 |
   | E9 bonificação, doação ou amostra | 1.910, 1.911 |
   | E10 remessa, retorno, consignação, conserto | 1.901 a 1.926; 1.949 só manual |
   | E11 compra para prestação de serviço | 1.126, 1.128, 1.933 |

   Cada natureza declara quatro efeitos, publicados como dado no código com
   a fonte:
   - estoque, custo, despesa ou imobilizado;
   - crédito de ICMS no regime normal (sim, limitado ao informado pelo
     fornecedor do Simples, vedado até 31/12/2032, 1/48 do ativo,
     monofásico, não);
   - marca de ST;
   - DIFAL possível.

   "A classificar" continua sendo a fila, nunca padrão silencioso. **Nenhuma
   natureza de entrada compõe receita bruta**, no Simples ou no Presumido.
4. **Dois CFOPs no item.**
   - O do emitente, que vem do XML, nunca muda.
   - O **de entrada**, confirmado na escrituração, fica na linha da natureza
     do item.
   - O primeiro dígito é fixo: 5 vira 1, 6 vira 2, 7 vira 3.
   - O grupo vem da natureza: o mesmo 5.102 do fornecedor vira 1.102, 1.556
     ou 1.551 conforme a compra seja para revenda, consumo ou ativo.
   - A sugestão do par (natureza, CFOP de entrada) usa o CFOP do emitente, o
     CST/CSOSN, o NCM e o CRT do emitente.
   - CFOP de entrada fora da tabela oficial é recusado; 1.949 só por escolha
     manual.
5. **Memória por item, gravada na efetivação e imutável.**
   - Guarda o ICMS destacado com a marca de crédito, pelas regras federais
     lidas (LC 87, arts. 20 e 33; LC 123, art. 23).
   - Fornecedor do Simples: crédito limitado ao `vCredICMSSN`; sem
     `pCredSN`, "sem crédito".
   - Também guarda o ST retido ("sem crédito, compõe o custo") e o
     combustível da LC 192 ("monofásico, sem crédito nem débito").
   - FCP, IPI e PIS/Cofins entram com CST e valor, só como memória.
   - A memória **repete** o que a nota destaca: nenhuma alíquota do Tocantins
     em código.
6. **Avisos nomeados**, sem valor:
   - compra de outro estado por optante do Simples: possível antecipação ou
     DIFAL fora do DAS (LC 123, art. 13, § 1º, XIII, "g" e "h"), regra do
     Tocantins não lida;
   - compra de outro estado para uso, consumo ou ativo no regime normal:
     possível DIFAL;
   - CST sem crédito pleno em natureza com crédito;
   - fornecedor do Simples sem `pCredSN`;
   - lubrificante ou etanol hidratado em E6;
   - UF do emitente incoerente com o CFOP.
7. **Devolução de compra:** natureza nova de **saída**, `devolucao_compra`,
   fora da receita e fora do saldo de devolução do Simples (art. 17).
   - É sugerida para saída própria com CFOP de `indDevol` 1 cuja descrição
     oficial comece por "Devolução de compra", "Devolução de mercadoria
     recebida em transferência", "Devolução de bem do ativo", "Devolução de
     mercadoria destinada para uso ou consumo" ou "Devolução de embalagens".
   - Vem com o aviso "estorno do crédito de ICMS: etapa do ICMS".
8. **Regras da DL-087 e lote da DL-085 para entradas.**
   - As regras de classificação aceitam o tipo `ENTRADA` e os critérios CRT
     do emitente e UF do emitente.
   - A fila "a classificar" e o lote em volume servem às entradas.
9. **Conferência de entradas do mês** (classe "conferência", sem impressão
   oficial). Mostra:
   - notas recebidas, escrituradas e fora, com o motivo;
   - totais por natureza e por CFOP de entrada;
   - soma do crédito destacado elegível e do ST retido;
   - a lista das notas com aviso de outro estado.
10. **API e telas:** escriturar entrada (data de entrada, natureza e CFOP de
    entrada por item, memória e avisos), conferência de entradas, e as
    entradas na lista "NF-e a escriturar" e no lote.

**Fica fora do corte 1** (pendências com nome, consulta seção 6):
- apuração de ICMS, ST, antecipação, DIFAL com valor, FECOEP e CIAP
  (etapas do ICMS-TO);
- livro registro de entradas;
- lançamento contábil da compra (integração);
- cadastro de fornecedor e de produto;
- CT-e e NFCom;
- vínculo da devolução de compra pela `NFref`;
- nova versão do leitor de itens: grupos de ICMS monofásico, `pRedBC`,
  `pMVAST`, partilha completa, IE e UF do destinatário;
- lado de entrada da transferência entre estabelecimentos (HI-111);
- importação de SPED Fiscal (RC-44);
- PIS/Cofins não cumulativo;
- regime de caixa.

## Correção do contrato (13/10/2026, arquiteto)

A frente A1 levantou uma dúvida, e ela procede. O leiaute oficial da NF-e
(`leiauteNFe_v4.00.xsd` do pacote PL_010f, campo `finNFe`, lido em cópia
local em 13/10/2026) define o `finNFe` 4 como **"Devolução/Retorno"**, de
forma genérica. A consulta partiu da premissa de que o 4 seria só devolução
de venda, e isso não vale. A devolução de compra que o cliente emite sai
normalmente com `tpNF` 1 e `finNFe` 4.

**Decisão:**
- Tipo novo `DEVOLUCAO_COMPRA` para a nota emitida pela empresa com `tpNF` 1
  e `finNFe` 4. Esse tipo aceita **só** a natureza `devolucao_compra`, e
  isso protege a receita: uma nota de devolução nunca recebe natureza de
  venda.
- O item de retorno (conserto, remessa) numa nota com `finNFe` 4 fica sem
  sugestão, com o motivo, e a nota não efetiva enquanto houver item sem
  natureza.
- A recusa que o plano previa sai.

Também foi decidido: a marca "monofásico" vale só para os combustíveis do
art. 2º da LC 192 (gasolina e etanol anidro, diesel e biodiesel, GLP). Fora
deles, "conferir NCM".

## Entrega da frente A1 (13/10/2026)

Integrada na branch, com a correção do `finNFe` 4. Migração `fiscal 0021`.
Medido pelo desenvolvedor, num banco próprio: suíte completa 10.230/1/56 (a
falha é a de ambiente). Os nove mutantes derrubam testes.

**O que a A1 entrega:**
- elegibilidade da compra;
- data de entrada e competência;
- naturezas E1 a E11 com os efeitos;
- dois CFOPs no item;
- memória por item, gravada na efetivação e imutável no banco;
- avisos de outro estado;
- tipo `DEVOLUCAO_COMPRA`.

**Decisões e limites registrados:**
- **Sugestões por CFOP do emitente:**
  - 5.656 sugere E7 (consumo, 1.653), porque é venda a consumidor final;
  - 5.655 sugere E6 (revenda, 1.652);
  - 5.405 sugere E3 (compra com ST, 1.403).
- **Monofásico só no art. 2º da LC 192, pelo NCM:**
  - diesel e GLP são marcados "monofásico";
  - querosene de aviação, óleos combustíveis e gás natural, "a conferir";
  - gasolina (2710.12.59) e diesel com biodiesel (2710.20.00), "conferir
    NCM", porque a descrição da tabela de NCM não os separa com segurança.

  Em todos os casos é tratamento conservador: nenhum crédito é afirmado. O
  refinamento vem depois da leitura item a item da tabela de NCM.
- **Posto:** os grupos de ICMS monofásico do XML são lidos sem erro, com o
  CST, mas o valor monofásico (`vICMSMono`) não é guardado. Isso é da nova
  versão do leitor, fora do corte 1.
- A conferência de saída (identidade W16) não se aplica à entrada.
- A devolução de compra em mês já confirmado reabre a confirmação, pelo
  gatilho existente de saída. É conservador e não mexe em receita.

## Critérios de aceite

1. **Nenhuma entrada mexe em receita, RBT12, pré-DAS ou Presumido.** Teste
   escrito à mão: empresa com vendas e com compras escrituradas tem receita,
   RBT12, pré-DAS e IRPJ/CSLL idênticos aos da mesma empresa sem as compras.
   A devolução de compra também não entra no saldo de devolução do Simples.
2. A suíte inteira passa sem mudar expectativa de saída, devolução de venda,
   pré-DAS ou Presumido.
3. **Elegibilidade e recusas:**
   - compra NF-e com `finNFe` 1 é escriturável;
   - NFC-e destinatária, `tpNF` 0 de terceiro e devolução de venda como
     entrada são recusadas com o motivo nomeado;
   - a mesma nota não tem duas escriturações ativas.
4. **CFOP de entrada:**
   - conversão do primeiro dígito testada nos três casos;
   - o grupo segue a natureza;
   - CFOP de entrada fora da tabela é recusado;
   - o CFOP do emitente nunca muda.
5. **Memória de crédito**, escrita à mão:
   - E4 com `vICMS` nunca vira "elegível";
   - fornecedor CRT 1 sem `pCredSN` nunca vira "elegível";
   - CRT 1 com `vCredICMSSN` limita ao valor informado;
   - CST 60 marca "ST retido";
   - NCM da LC 192 marca "monofásico".
6. A data de entrada define a competência e é recusada se for anterior à
   emissão.
7. Os avisos de outro estado aparecem só nos casos descritos, e o produto
   não tem nenhuma alíquota do Tocantins em código.
8. Regras da DL-087 com tipo `ENTRADA` e critérios de CRT e UF mudam a
   sugestão de entrada e nunca a de saída. O lote é equivalente ao
   individual para entradas.
9. Isolamento entre escritórios e empresas, permissão no servidor e trilha
   (403 e 404 testados).
10. **Mutação:** cada um destes defeitos derruba teste:
    - entrada somando receita;
    - devolução de compra no saldo do art. 17;
    - crédito "elegível" em uso e consumo;
    - fornecedor do Simples sem `pCredSN` com crédito;
    - primeiro dígito do CFOP de entrada errado;
    - competência pela emissão e não pela entrada.
11. Regressão completa numa única invocação, em banco próprio. Migração
    aditiva e reversível; a reversão recusa se houver escrituração de
    entrada.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A1 — elegibilidade, tipo `ENTRADA`, data de entrada, naturezas de entrada e `devolucao_compra` com efeitos, CFOP de entrada, memória e avisos, efetivação e estorno, migração, API da escrituração | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/models.py`, migração nova, `escrituracao_nfe.py`, módulo novo `entradas.py`, `receita.py` e `pre_das.py` só se for preciso garantir o critério 1, `api_escrituracao_nfe.py`, `urls_api.py`, `apps/core/restricoes.py`; testes `test_dl091_*` |
| A2 — regras da DL-087 para entradas, lote, conferência de entradas (serviço e API) | `auxiliar-implementacao` (Haiku), depois da A1 | `classificacao.py`, `api_classificacao.py`, `escrituracao_nfe_lote.py`, módulo de conferência; testes `test_dl091_*` |
| B — telas | `auxiliar-implementacao` (Haiku), depois da A2 | `views_web.py`, `urls_web.py`, `templates/fiscal/`; testes `test_dl091_telas*` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Reverter o merge volta a recusar a compra na escrituração. A migração da
etapa recusa a reversão se houver escrituração de entrada ou natureza de
devolução de compra gravada.
