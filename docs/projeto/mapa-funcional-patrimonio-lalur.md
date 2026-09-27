# Mapa funcional — Patrimônio e Lalur

## O que este documento é

Inventário das funções e dos relatórios dos módulos **Patrimônio** (ativo
imobilizado) e **Lalur** (apuração do lucro real) do sistema de referência,
para o DataLedger chegar a cobertura equivalente (pedido do Fred em
2026-09-27, [DL-047](../planos/DL-047-mapa-de-paridade-funcional.md)).

- **Fonte:** manuais do sistema de referência entregues pelo Fred em
  2026-09-27 (Patrimônio, 389 páginas; Lalur, 291 páginas). As páginas
  citadas são desses manuais. O texto aqui é nosso; o manual **não** entra
  no repositório ([fontes-de-referencia.md](fontes-de-referencia.md)).
- **Manual responde rotina, nunca norma.** Taxa de depreciação, CIAP,
  adição e exclusão do lucro real, leiaute da ECF: tudo isso vem de fonte
  oficial, citada na seção de pontos normativos, antes de virar código.
- **Situação no DataLedger em 2026-09-27:** os dois módulos **não existem**.
  Não há cadastro de bem, depreciação, centro de custo nem Lalur no código.

## Patrimônio

### Relatórios

| Relatório | Para que serve | Classe | Página |
| --- | --- | --- | --- |
| Depreciação fiscal | Memória do cálculo fiscal do período, bem a bem | Conferência (livro, se numerado) | 254-256 |
| Depreciação societária | O mesmo pelo critério contábil, quando diverge do fiscal | Conferência | 256-259 |
| Comparativo da depreciação | Fiscal ao lado da societária — a diferença que vira ajuste no Lalur | Conferência | 259-261 |
| Resumos da depreciação fiscal e societária | Versão sintética por conta patrimonial | Conferência | 261-263 |
| Ficha do bem | Histórico individual: aquisição, depreciações, eventos | Conferência | 263-265 |
| Acompanhamento patrimonial fiscal e societário | Custo, depreciação acumulada e saldo por conta ao longo das competências; concilia com o Balanço | Demonstração de apoio | 265-267 |
| Depreciação sobre custo atribuído | Cálculo sobre o custo atribuído na adoção inicial | Conferência | 268-269 |
| Baixas | Bens baixados no período, com ganho ou perda | Conferência | 269-271 |
| Transferências (conta patrimonial, centro de custo, estabelecimento) | Movimentação do bem entre classificações e locais | Conferência | 271-275 |
| Avaliação a valor justo | Reavaliação e perda por não recuperabilidade | Conferência | 275-276 |
| Ficha CIAP e termos | Controle do crédito de ICMS do ativo; forma dada pela legislação estadual | Livro fiscal | 277-280 |
| ICMS creditado e resumo | Crédito já apropriado, a apropriar e do período | Conferência | 280-282 |
| Débito de ICMS (importação, diferencial de alíquotas) | Regras estaduais específicas | Conferência | 282-285 |
| Crédito de PIS e COFINS do imobilizado | Sobre aquisição ou sobre depreciação | Conferência | 285-287 |
| Razão auxiliar para a ECD | Escrituração auxiliar do imobilizado no SPED Contábil | Livro (digital) | 287-294 |
| Cadastrais | Listagens dos cadastros do módulo | Conferência | 294-320 |

### Funções

| Função | O que faz | Página |
| --- | --- | --- |
| Cadastro do bem | Identificação, tipo, classificação, conta patrimonial, centro de custo, bem componente de outro | 84-107 |
| Parâmetros de crédito do bem | PIS/COFINS e ICMS (CIAP) por bem | 86-96 |
| Parâmetros de depreciação do bem | Deprecia ou não, taxa, início, acumulada informada, critério societário | 96-100 |
| Documento de origem | Vínculo do bem à nota de aquisição | 100-102 |
| Conta patrimonial | Agrupa bens, com taxa fiscal por vigência e amarração às contas contábeis (aquisição, depreciação, avaliação, baixa, crédito de ICMS) | 108-118 |
| Integração por centro de custo | Contabilização agrupada por centro de custo | 119-124 |
| Cálculo periódico | Depreciação fiscal e societária de todos os bens | 209-220 |
| Baixa total ou parcial | Com ganho ou perda de capital e vínculo à nota de saída | 224-231 |
| Transferências | Entre contas patrimoniais, centros de custo e estabelecimentos | 231-241 |
| Avaliação a valor justo | Ganho ou perda, em subconta | 241-246 |
| Integração contábil | Lançamentos do período para a Contabilidade | 246-248 |
| Integração fiscal | Crédito e débito de ICMS, créditos de PIS/COFINS, ganho de capital | 248-253 |

### Dependências

Cadastro do bem → conta patrimonial (com amarração contábil) → centro de
custo, que ainda não existe no DataLedger → cálculo → baixa, transferência e
avaliação → integração contábil → relatórios. A integração **fiscal** depende
de apuração de ICMS e PIS/COFINS, que o DataLedger também não tem: fica para
depois do Fiscal.

## Lalur

### Relatórios

| Relatório | Para que serve | Classe | Página |
| --- | --- | --- | --- |
| Livro Lalur (Parte A, Parte B, apuração e base negativa da CSLL) | O livro fiscal; hoje é bloco da ECF | Livro (digital) | 224-227 |
| Demonstrativos de CSLL, IRPJ e base negativa | Memória de cálculo do período | Demonstração | 228-231 |
| Lucro da exploração | Benefício de incentivo regional | Demonstração | 231-232 |
| Comparativo real × estimado | Apoio à escolha do regime | Conferência | 232-233 |
| Acompanhamentos (adições, exclusões, pagamentos, incentivos) | Conferência do período | Conferência | 233-239 |
| Guias DARF (normal, quotas, ajuste anual) | Recolhimento | Guia | 239-244 |
| Cadastrais | Listagens | Conferência | 244-256 |

### Funções

| Função | O que faz | Página |
| --- | --- | --- |
| Cadastro de adições e exclusões | Regra ligada às contas de origem, por tributo | 101-111 |
| Operações de receita e ganhos | Base da estimativa | 111-114 |
| SCP | Apuração separada da sociedade em conta de participação | 114-119 |
| Incentivos fiscais | Limite e aproveitamento | 119-120 |
| Parte B e base negativa | Controle dos saldos que afetam períodos futuros | 120-121 |
| Apuração trimestral ou anual e ajuste anual | Cálculo de IRPJ e CSLL | 135-137 |
| Lançamentos de CSLL e IRPJ | Adições, exclusões, deduções, compensações, Parte B | 137-194 |
| Lucro antes do IRPJ e da CSLL | Ponto de partida, importado das contas de resultado | 201-204 |
| Compensação, parcelamento e pagamento | DComp, quotas, baixa de pagamento | 207-217 |
| Eventos societários | Cisão e incorporação sobre a Parte B | 219-221 |
| Integração contábil | Provisão de IRPJ e CSLL | 221-223 |

### Dependências

O "lucro antes do IRPJ e da CSLL" sai do resultado contábil — a DRE já existe
([DL-045](../planos/DL-045-demonstracao-do-resultado.md)). Ganho de capital
vem do Patrimônio. Retenções e receita bruta vêm do Fiscal. O Livro Lalur
digital é bloco da ECF, que depende da ECD e do plano referencial.

## Pontos normativos que exigem fonte oficial antes de implementar

| Assunto | Fonte a consultar |
| --- | --- |
| Taxas de depreciação fiscal | IN RFB 1.700/2017, Anexo III, e atualizações |
| Diferença fiscal × societária e subcontas | Lei 12.973/2014 |
| Vida útil, valor residual, redução ao valor recuperável | NBC TG 27 e NBC TG 01 (CFC) |
| CIAP (1/48) e modelos | LC 87/1996, art. 20, § 5º; legislação de cada UF |
| Créditos de PIS/COFINS sobre o imobilizado | Leis 10.637/2002 e 10.833/2003, vigência atual |
| Adições, exclusões, compensação de prejuízo (30%) | RIR/2018; IN RFB 1.700/2017; Lei 9.065/1995 |
| Leiaute da ECF (blocos do Lalur e do cálculo) | Manual de Orientação da ECF vigente (Sped) |
| Alíquotas de IRPJ, adicional e CSLL | Legislação vigente — o manual traz exemplos históricos |

## O que não copiar

- **"Regerar" que apaga e refaz lote de lançamentos:** no DataLedger só vale
  para rascunho; lançamento efetivado se corrige por estorno rastreável.
- **Processamento de várias empresas de uma vez:** útil, mas a autorização é
  conferida no servidor **empresa por empresa**, nunca pela seleção da tela.
- **Período encerrado:** as operações do Patrimônio e do Lalur obedecem à
  mesma trava de competência da Contabilidade (DL-016).

## Ondas recomendadas

1. **Patrimônio, núcleo:** cadastro do bem e da conta patrimonial,
   depreciação fiscal linear com taxa por vigência, Ficha do bem e
   Depreciação fiscal.
2. **Ciclo do bem e integração contábil:** baixa com ganho ou perda,
   transferências, lançamentos no Diário, acompanhamento patrimonial
   conciliado com o Balanço. Pede centro de custo, se o cliente usar (RC-54).
3. **Critério societário e comparativo** (Lei 12.973/2014), que alimenta o
   Lalur.
4. **CIAP e créditos de PIS/COFINS:** depois do Fiscal e da confirmação das
   UFs atendidas pelo escritório.
5. **Lalur, Parte A e apuração**, sobre a DRE existente.
6. **Lalur, Parte B e guias.**
7. **Livro Lalur digital dentro da ECF**, junto da estratégia de ECD/ECF.
