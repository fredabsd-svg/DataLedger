# Mapa funcional — Folha de pagamento e Ponto

## O que este documento é

Inventário das funções e dos relatórios dos módulos **Folha** e **Ponto
Eletrônico** do sistema de referência, para o DataLedger chegar a cobertura
equivalente (pedido do Fred em 2026-09-27,
[DL-047](../planos/DL-047-mapa-de-paridade-funcional.md)).

- **Fonte:** manuais do sistema de referência entregues pelo Fred em
  2026-09-27 (Folha, versão 10.1A-12, 1.433 páginas; Ponto, 128 páginas).
  O sumário foi percorrido inteiro e o conteúdo, por amostras. As páginas
  citadas são desses manuais; o texto é nosso, e o manual **não** entra no
  repositório ([fontes-de-referencia.md](fontes-de-referencia.md)).
- **O manual é de 2018 e a folha mudou muito desde então.** Recolhimentos e
  declarações que ele descreve (GFIP/SEFIP, GRRF, DIRF, RAIS, CAGED como
  arquivos próprios) foram substituídos, no todo ou em parte, pelo eSocial,
  pela DCTFWeb, pelo FGTS Digital e pela EFD-Reinf. **Nada disso vira
  requisito sem conferência de vigência em fonte oficial.**
- **Situação no DataLedger em 2026-09-27:** o módulo **não existe** — não há
  empregado, rubrica, cálculo nem eSocial no código.

## Relatórios

Classes: C = conferência; F = forma prescrita por norma trabalhista
(recibo, TRCT, aviso — o mesmo princípio da classe livro de
[personalizacao-de-relatorio.md](personalizacao-de-relatorio.md): forma
fixada, personalização quase nula); A = arquivo de obrigação ou de banco.

| Grupo | Relatórios | Classe | Páginas |
| --- | --- | --- | --- |
| Folha | Resumo, extrato por empregado, líquidos, cheques, crédito em conta, cadastro para banco, relações de férias, rescisões e folha, movimentos, conciliação do INSS da folha com o do eSocial | C, A | 998-1031 |
| Encargos | INSS, INSS sobre receita bruta, IRRF, carnê-leão do tomador de autônomo, PIS sobre folha, encargos da empresa, analítico da guia, doméstico | C | 1031-1046 |
| Informativos | Arquivos de recolhimento e de declaração (vários obsoletos), ficha financeira, comprovante de rendimentos, PPP, CAT, painel de pendências e controle de eventos do eSocial, eventos iniciais e periódicos | A, F, C | 1047-1115 |
| Guias | Previdência, DARF, IRRF, carnê-leão, PIS, FGTS rescisório, contribuição sindical | A | 1115-1147 |
| Recibos | Holerite, recibo de férias, TRCT e termos, RPA | F | 1148-1174 |
| Benefícios e avisos | Vale-transporte, vale-alimentação, aviso prévio | C, F | 1166-1178 |
| **Provisões** | Férias e 13º (analítica, sintética, com encargos) | C | 1180-1186 |
| Cadastrais e outros | Ficha do empregado, tabelas, cargos, sindicatos, médias, diferenças salariais, estabilidades, vencimento de férias, alterações salariais, FGTS, pagamentos, seguro-desemprego, programação de férias, termo de quitação anual | C, F | 1186-1316 |

## Funções

| Área | Funções | Páginas |
| --- | --- | --- |
| Cadastros de pessoas | Empregados, estagiários (com instituição e agente), contribuintes individuais | 180-351 |
| Regras de cálculo | **Rubricas** com incidências, bases de cálculo, **tabelas** de IRRF, INSS, salário-família, FAP e salário mínimo | 351-387 |
| Estrutura | Filiais, centros de custo, departamentos, cargos, funções, **horários e jornadas** | 416-428, 593-628 |
| **Sindicatos e convenções** | Regras de férias, 13º, aviso prévio, médias, estabilidade, piso, PLR, alteração retroativa por aditivo | 428-593 |
| Benefícios e outros | Bancos, vale-transporte, vale-alimentação, EPI, plano de saúde, previdência complementar, processos judiciais | 628-647 |
| Integração contábil | Contas e históricos por evento (folha, férias, rescisão, provisões, pagamentos) | 647-667 |
| **Cálculo** | Mensal, adiantamento, apuração previdenciária | 691-707 |
| Eventos do contrato | **Rescisão** (individual, em grupo, complementar, TRCT), **férias** (individuais, coletivas, períodos aquisitivos), provisões, afastamentos, licenças, estabilidade, aposentadoria, CAT, intermitente | 707-795 |
| Autônomos | RPA e carnê-leão do tomador | 795-820 |
| Movimento | Lançamentos por empregado, rubrica e grupo; benefícios; consignado; advertências; bases e retenções de INSS | 822-918 |
| Salários | Alteração individual, em grupo e **retroativa**, com diferenças | 923-974 |
| Pagamento | Pagamentos, parcelamento de encargos | 974-988 |
| **Integração contábil** | Folha, provisões de férias e 13º, pagamentos | 988-991 |
| eSocial | Parâmetros, dados por cadastro, qualificação cadastral, manutenção de matrícula | 82-88, 1375-1382 |
| Utilitários | Simuladores de férias e rescisão, consultas de recibos e médias, importações, backup | 1323-1427 |
| **Ponto** | Horários, relógios, importação de marcações, abonos e acertos, reapuração, trocas de horário, saldos (banco de horas), relatórios de presença, absenteísmo e inconsistências, arquivos fiscais do ponto | Ponto, 17-124 |

## Cadeia de dependências

Rubricas e incidências → tabelas por vigência (INSS, IRRF, salário-família,
salário mínimo) → sindicato e convenção com vigência → empregado com cargo,
jornada e salário → (ponto: marcações → apuração → saldos → rubricas de
horas) → **cálculo** (mensal, férias, 13º, rescisão, com médias) →
recibos, provisões, guias, eventos do eSocial e **integração contábil**
(que já tem destino: a contabilidade existe).

## Fontes oficiais a consultar antes de implementar

| Assunto | Fonte |
| --- | --- |
| Tabelas de INSS e de IRRF (faixas, dependente, desconto simplificado) | Receita Federal e legislação vigente na competência |
| FGTS e guias | FGTS Digital (Caixa e MTE), normativo vigente |
| Eventos e leiaute | Manual de Orientação e leiautes do eSocial (versão S-1.x vigente) |
| Declaração de tributos da folha | DCTFWeb, IN RFB vigente |
| Retenções | EFD-Reinf, leiaute vigente |
| DIRF, RAIS, CAGED, GFIP | Confirmar se foram extintas ou absorvidas pelo eSocial, DCTFWeb e EFD-Reinf, e desde quando |
| Rescisão, aviso, férias, 13º, TRCT | CLT, Lei 12.506/2011, portarias do MTE vigentes, convenção coletiva do cliente |
| Contribuição sindical | CLT após a Lei 13.467/2017 |
| Ponto eletrônico | Portaria MTP 671/2021 e alterações |
| Desoneração (INSS sobre receita bruta) | Lei 12.546/2011 e a vigência atual |

## O que não copiar

- **Recalcular e excluir** férias, rescisão ou cálculo já pago como operação
  direta: no DataLedger, folha efetivada é imutável; correção gera
  **diferença rastreável** com motivo, como o próprio sistema de referência
  já faz na alteração retroativa de piso.
- **Processamento de várias empresas de uma vez** só com autorização
  conferida no servidor, empresa por empresa.
- **Telas de obrigações extintas:** copiar a configuração de uma declaração
  que não existe mais seria inventar leiaute.
- **Reimportação de ponto** é operação explícita, nunca atualização
  silenciosa (regra de não duplicar em silêncio).

## Ondas recomendadas

1. **Fundação e cálculo mensal, sem transmissão:** rubricas, tabelas por
   vigência, sindicato, empregados, cargos e jornadas; cálculo mensal e
   adiantamento com memória de cálculo; rascunho distinguível de efetivado;
   holerite; resumo, extrato e líquidos.
2. **Ciclo anual e integração contábil:** férias, 13º, provisões, rescisão
   com TRCT (forma a confirmar na norma vigente) e integração contábil.
3. **eSocial como preparação:** geração e conferência dos eventos, sem
   transmissão. Transmissão ao eSocial, à DCTFWeb e ao FGTS Digital exige
   certificado digital e canal homologado — decisão separada, com o Fred
   ([escopo.md](../escopo.md), integrações).
4. **Pró-labore, autônomos (RPA) e ponto.**
5. **Anuais e utilitários:** comprovante de rendimentos, PPP, simuladores.
