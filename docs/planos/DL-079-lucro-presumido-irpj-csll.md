# DL-079 — Fiscal: Lucro Presumido, IRPJ e CSLL trimestrais com o acréscimo da LC 224

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170); etapa
7 do roteiro de execução do [DL-067](DL-067-plano-do-modulo-fiscal.md).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1) — é o imposto que o
cliente paga. Auditoria independente: uma rodada, uma correção, uma
reconferência.

**Conferência, nunca guia nem transmissão:** nada de DARF, DCTFWeb, ECF ou
PER/DCOMP. O produto mostra a apuração para o contador conferir, com a memória
de cálculo.

## Base

[Consulta ao contador-senior sobre o Lucro Presumido](../projeto/consultas/2026-10-08-contador-senior-presumido.md):
LC 224/2025, Leis 9.249, 9.430, 7.689, 8.981, 9.718, 10.833, DL 1.598, RIR/2018,
Decreto 12.808/2025 e Constituição **lidos no Planalto** em 08/10/2026;
Perguntas e Respostas da RFB sobre a redução de benefícios (V5, 30/07/2026,
itens 11 a 14) e tabelas de códigos de receita **lidas em gov.br**; IN RFB
2.305/2025 na redação da IN 2.306/2026 e IN 1.700/2017 em **cópia íntegra**
(o portal de normas da Receita só devolve a casca da página). Hipóteses
HI-100 a HI-107; pendência PE-83 com o Fred.

Correções que a consulta fez ao DL-067: o acréscimo **multiplica** o
percentual por 1,10 (exemplo oficial do P&R, item 11); a CSLL tem
percentuais próprios (12, 32, 38,4%) e não reaproveita os do IRPJ; na
segunda quota os juros são só 1%, e a Selic entra a partir da terceira.

## Escopo (primeiro corte)

1. **Tabelas como dado com vigência e fonte**, num módulo próprio no padrão de
   `simples_tabelas.py`: atividades de presunção com os dois percentuais
   (IRPJ e CSLL) — comércio, indústria e transporte de carga 8/12; revenda de
   combustíveis 1,6/12; transporte de passageiros 16/12; serviços em geral
   32/32; intermediação 32/32; administração, locação e cessão de bens 32/32;
   serviços hospitalares 8/12, só com os dois requisitos legais marcados pelo
   contador. Alíquotas: IRPJ 15% mais adicional de 10% sobre o que passar de
   R$ 20.000 × meses; CSLL 9%. LC 224: fator 1,10; limite de R$ 1.250.000
   por trimestre; início em 01/01/2026 para o IRPJ e em 01/04/2026 para a
   CSLL. Códigos 2089 (IRPJ) e 2372 (CSLL), só informativos.
2. **Atividade de presunção por empresa**, com vigência e uma padrão; nota sem
   atividade de presunção recusa a apuração nomeando as notas. Sugestão pelo
   código do serviço é só sugestão; o contador decide (HI-101).
3. **Receita do trimestre:** as NFS-e prestadas efetivadas (DL-072), por
   `dCompet`, pelo `vServ` deduzido do desconto incondicional; receitas
   informadas com atividade de presunção e documento de suporte; e **receitas
   integrais do art. 25, II** (financeiras, ganhos de capital, demais)
   declaradas pelo contador com suporte, ou a declaração explícita "não houve
   receitas integrais no trimestre". Sem a declaração, ou se as receitas
   integrais mudarem depois dela, a apuração sai como **parcial** (HI-104).
   O primeiro corte calcula a apuração na consulta e não grava um estado de
   "conferida"; isso vem com a integração contábil.
4. **Cálculo do trimestre e controle do limite da LC 224** por empresa, ano e
   tributo (IN 2.305, art. 15, na redação da IN 2.306): limite com sobra dos
   trimestres anteriores; excedente rateado por atividade; fechamento no 4º
   trimestre com os casos I, II e III nomeados; dedução do 4º trimestre e
   saldo para PER/DCOMP apenas mostrado; limite proporcional no início ou
   encerramento de atividade. **Três colunas** em toda a memória: sem LC 224,
   com LC 224 e a parcela da LC 224.
5. **Retenções sofridas** (IRRF e CSLL das NFS-e prestadas) **propostas**, e
   deduzidas só depois de confirmadas pelo contador, com trilha. CSLL: exata
   com `tpRetPisCofins` 8; **estimada** por 1/4,65 com código 3, marcada
   "estimada — conferir no comprovante"; nos demais casos, "a classificar",
   sem valor. A dedução vale no trimestre em que a receita entrou na base
   (HI-102, HI-103). Saldo negativo é só mostrado.
6. **Quotas:** quota única ou até 3; nenhuma abaixo de R$ 1.000; imposto
   abaixo de R$ 2.000 em quota única; a 2ª quota com 1% e a 3ª com "Selic de
   [mês] + 1%", sem embutir taxa. Vencimento no último dia útil do mês, sem
   sábado, domingo nem feriado nacional fixo em lei, e com aviso "calendário
   a conferir" quando cair na Sexta-feira Santa ou no Carnaval (HI-105).
7. **Medida judicial contra o acréscimo** (ADI 7936 e 7944, liminares):
   cadastro por empresa, tributo e período, com processo, órgão, data,
   depósito e suporte. Com medida ativa, "a recolher" usa a coluna sem LC 224
   e a parcela aparece como **suspensa** (ou "depositar"). Nunca é o padrão.
   Aviso fixo com a data da última conferência das ADIs (HI-106).
8. **Recusas nomeadas:** regime diferente de Presumido no trimestre; regime
   de caixa (IN 1.700, art. 223); alíquota majorada de CSLL; atividade
   imobiliária; trimestre com mudança de regime.
9. Telas e API: atividades de presunção, receitas e declarações do
   trimestre, apuração do trimestre com memória, controle do limite do ano,
   confirmação das retenções, medidas judiciais. Isolamento e permissões como
   na DL-075.

**Fica fora** (pendência nomeada na tela quando cabível): receita de
mercadorias por NF-e; cálculo de ganho de capital; regime de caixa;
atividade imobiliária; SCP; alíquota majorada; obrigatoriedade do Lucro Real
e mudança de regime no ano; PER/DCOMP; DARF, DCTFWeb e ECF; Selic automática;
filiais com regra própria (o limite é por empresa, HI-107); Lucro Arbitrado;
incorporação, fusão, cisão e extinção; retenção de órgão público federal com
cálculo próprio; feriados estaduais e municipais.

## Fórmula

Para o tributo `k` (IRPJ ou CSLL) e o trimestre `t`, a partir do primeiro
trimestre do acréscimo (`t0`: 1 no IRPJ; 2 na CSLL em 2026):

```
R_t     = soma das receitas sujeitas a presunção do trimestre (sem as do art. 25, II)
L_t     = 1.250.000,00 + sobra_(t-1)        (sobra_(t0-1) = 0)
E_t     = max(0; R_t - L_t)                 sobra_t = max(0; L_t - R_t)
E_t,i   = E_t × R_t,i / R_t                 (resíduo de centavos na última atividade)
base    = Σ_i [(R_t,i - E_t,i) × p_k,i + E_t,i × p_k,i × 1,10] + receitas integrais
IRPJ    = 15% × base + 10% × max(0; base - 20.000 × meses)
CSLL    = 9% × base_CSLL
```

No último trimestre, com `N` trimestres sujeitos ao acréscimo,
`ExcAnual = max(0; Σ R_t - 1.250.000 × N)` e `S = Σ E_t` dos anteriores:
caso III (`ExcAnual ≥ S`) mantém a sobra; caso II (`0 < ExcAnual < S`) zera
o excedente do último trimestre, recalcula os anteriores com o excedente
rateado e deduz a diferença no último; caso I (`ExcAnual = 0`) recalcula sem
acréscimo e deduz a diferença no último. Cada linha da memória é arredondada
a centavos (`ROUND_HALF_UP`) (HI-100).

## Decisões tomadas na implementação

- **Medida judicial e o ajuste do 4º trimestre:** a dedução dos casos I e II
  só soma os trimestres anteriores **sem** medida judicial ativa para o
  tributo; com medida, a parcela da LC 224 não foi recolhida (ficou suspensa
  ou depositada) e devolvê-la no 4º trimestre seria contá-la duas vezes. A
  memória do fechamento mostra esses trimestres como "fora da dedução".
- **Mês de início de atividade no adicional** (HI-108): o mês da abertura
  conta inteiro em "meses do período". O RIR/2018, art. 624, e a IN 1.700,
  art. 29, § 1º, falam em "número de meses do período de apuração" sem regra
  de fração (lidos em 08/10/2026).
- **CSLL retida com `tpRetPisCofins` 8 e `vPis`/`vCofins` preenchidos**: "a
  classificar", não o `vRetCSLL` — a combinação é ambígua (consulta, item 6).
- **Resíduo do rateio no caso II**: vai para o último trimestre com
  excedente, para a soma fechar ao centavo (escolha de produto, HI-100).
- **Encerramento de atividade** não tem campo no cadastro: o 4º trimestre é
  sempre o fechamento do ano; encerramento fica fora do primeiro corte.
- **Recusa zera o cálculo:** com recusa nomeada, os tributos saem sem número
  parcial.

## Critérios de aceite

1. O exemplo oficial do P&R (receita de R$ 1.500.000 de comércio no
   trimestre: base de R$ 122.000,00) e o exemplo de quatro trimestres da
   consulta (item 4, IRPJ e CSLL) batem ao centavo, calculados por um teste
   que não reaproveita a função de produção.
2. Os três casos do 4º trimestre (I, II e III) têm teste com o valor esperado
   calculado à mão; o caso III dá o mesmo excedente pela sobra e pelo § 5º,
   III.
3. A CSLL não tem acréscimo no 1º trimestre de 2026, e o limite do ano para
   ela é de R$ 3.750.000; o IRPJ tem acréscimo desde o 1º trimestre.
4. Receitas do art. 25, II entram integrais na base e não contam para o
   limite; sem a declaração do trimestre, a apuração é "parcial".
5. Retenção só entra depois de confirmada; CSLL estimada é marcada; código
   ambíguo fica "a classificar"; saldo negativo não passa para o trimestre
   seguinte.
6. Quotas: as regras de R$ 1.000 e R$ 2.000; 2ª com 1%; vencimento no último
   dia útil, com os testes de fim de semana e de Sexta-feira Santa.
7. As três colunas estão em toda a memória; a medida judicial muda só
   "a recolher" e deixa a parcela visível.
8. As recusas do item 8 do escopo, cada uma com mensagem e teste.
9. Rascunho, estornada e cancelada não entram na receita; nota de outra
   empresa nunca entra; isolamento entre escritórios e empresas; permissões
   no servidor.
10. Mutação: somar 10 pontos em vez de multiplicar por 1,10; aplicar o
    acréscimo na CSLL do 1º trimestre de 2026; contar receita integral no
    limite; esquecer a sobra; deduzir retenção não confirmada; aplicar o
    adicional à CSLL; remover o filtro de empresa — cada um derruba testes.
11. Não regressão completa numa única invocação; migração aditiva e
    reversível; nada muda no Simples, no pré-DAS nem no ISS.

## Divisão

Começa **depois** de a DL-078 entrar na branch: o leitor de campos federais
da NFS-e (`tomadas_campos.py`) é reaproveitado para as prestadas.

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — tabelas, modelos, migração, cálculo, limite, retenções, quotas, medida judicial, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/fiscal/` (módulos novos `presumido_tabelas.py`, `presumido.py`), modelos, migração, testes `test_dl079_*` |
| B — telas | `auxiliar-implementacao` (Haiku), depois de A | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Tabelas novas; nada muda nas existentes. Reverter é reverter a migração e o
merge.
