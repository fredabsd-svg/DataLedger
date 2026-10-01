# DL-062 — DMPL: dividendo adicional proposto, veto dos lançamentos mistos e saída pelo estorno

**Demanda:** continuação da [DL-061](DL-061-dmpl.md), com as decisões do Fred de
01/10/2026: RC-153 (há cliente com dividendo adicional proposto no PL) e RC-155 (a M2
vira veto). Inclui a ressalva M3 da [reconferência](../auditorias/2026-10-01-dl-061-reconferencia.md)
(BL-624) e a M4 (BL-625). **Estado:** [fonte única](../agents/estado.md).
**Branch:** `claude/zealous-goldberg-jr5ggu` → `main`. **Risco:** nível 1.

## Decisões (`arquiteto-senior`, reversíveis salvo indicação)

### G1 — Coluna "Dividendo adicional proposto" (RC-153, BL-603)

- **Enum:** membro novo `dividendo_adicional_proposto` em `ClassificacaoDmpl`, no grupo
  "demais contas exigidas" do item 111A da TG 51 (106B da R5). Fica depois de lucros ou
  prejuízos acumulados.
- **Consistência com a DLPA:** a conta tem `classificacao_dlpa = dividendo` (a DLPA mostra
  a proposta como dividendo, art. 186, III). Essa classificação passa a admitir esta
  coluna, e só ela.
- **Linhas:**
  - **Proposta** (lucros acumulados → coluna nova): linha nova "Dividendo adicional
    proposto", logo depois de "Dividendos" na ordem do E4. A coluna de lucros fica
    negativa, a coluna nova positiva, e o total da linha é zero.
  - **Aprovação** (coluna nova → dividendos a pagar no passivo): linha "Dividendos", com a
    coluna nova negativa. É quando o total do PL diminui.
  - **Volta para lucros acumulados** (coluna nova → lucros): par sem regra, com veto e
    pendência até decisão.
- **Identidade com a DLPA:** a linha "dividendo" da DLPA passa a corresponder, na coluna de
  lucros, à **soma** de "Dividendos" e "Dividendo adicional proposto" da DMPL. A tabela de
  identidade e o teste de identidade mudam para aceitar essa soma, sem afrouxar as demais
  linhas.
- **Norma:** nenhum item da ICPC 08 é citado no código nem no documento enquanto a PE-75
  estiver aberta.

### G2 — Veto do lançamento com eventos opostos na mesma coluna (RC-155, BL-623)

Nas colunas de capital, reservas de capital, ajustes de avaliação e tesouraria, a
emissão é vetada (`lancamentos_ambiguos`) quando o lançamento tem, na mesma coluna,
itens a débito **e** a crédito, e também:

- (a) há contrapartidas de fora das colunas nos dois lados (débito e crédito); ou
- (b) a mesma conta aparece a débito e a crédito.

Exemplos:

| Lançamento | Resultado |
| --- | --- |
| `D Tesouraria 1.500 / D Caixa 1.000 / C Caixa 1.500 / C Tesouraria 1.000` | veto |
| `D Capital 200 / D Caixa 800 / C Capital 1.000` (mesma conta) | veto |
| `D Caixa 500 / D Capital a integralizar 500 / C Capital 1.000` (subscrição com integralização parcial) | aumento de capital 500,00, sem veto |

O veto das reservas de lucros (N7) continua como está.

### G3 — Saída pelo estorno (M3, BL-624)

- **Par lançamento + estorno:** o lançamento L e o estorno E, feito por
  `estornar_lancamento` (`E.estorno_de = L`), quando os dois caem dentro do período
  apurado, saem **juntos** da atribuição de linhas da DMPL. A soma deles é zero em cada
  coluna, por construção. Assim, o procedimento rastreável do projeto (estornar e relançar
  cada evento em lançamento próprio) libera a emissão.
- **Fora do período:** se o estorno cair depois da data final, L conta sozinho e o veto
  continua naquele período.
- **Identidade com a DLPA:** a DLPA soma os dois itens com efeito zero. Se a DLPA mostrar
  linha com valor zero e lançamentos, a identidade compara valores. Teste obrigatório.
- **Mensagens:** as do veto (`lancamentos_ambiguos` e dividendo positivo em reserva) passam
  a dizer a verdade. O lançamento efetivado não se altera; a saída é **estornar e relançar
  cada evento em lançamento separado**. A marcação manual da fatia 2 virá para os casos
  que nem assim se resolvem.

### G4 — Dica da diferença com o Balanço (M4, BL-625)

Quando há `contas_do_patrimonio_liquido_sem_coluna`, o texto da `diferenca_de_fechamento`
diz que a diferença provavelmente vem da conta listada acima. A dica da retificadora fora
do grupo só aparece quando a diferença é a única pendência.

## Critérios de aceite

1. **G1:**
   - DMPL com dividendo adicional proposto emite: proposta em dezembro e aprovação em abril
     do ano seguinte, valores calculados à mão nos dois exercícios.
   - Identidade com a DLPA pela soma.
   - Conta de dividendo no PL classificável na coluna nova.
   - Pendência N4 ajustada.
   - Par de volta para lucros vetado.
2. **G2:** os três exemplos acima, com mutantes que derrubem cada condição.
3. **G3:**
   - Lançamento vetado, depois estornado e relançado em dois lançamentos: a emissão é
     liberada, com os valores certos.
   - Estorno depois da data final: o veto persiste.
   - Identidade com a DLPA.
   - Mensagens novas sem "divida o lançamento".
4. **G4:** teste de tela com as duas pendências juntas.
5. Propriedades P4 e diferencial DLPA × DMPL continuam verdes. Casos A e B intactos.
6. Suíte completa, `ruff`, `check` e `makemigrations --check` limpos; migração da escolha
   nova, se o Django exigir.

## Equipe e arquivos

- **`desenvolvedor-pleno`** — G1, G2, G3 e mensagens. Arquivos:
  - `apps/contabilidade/models.py`;
  - migração;
  - `apps/contabilidade/services.py`;
  - testes de serviço.
- **`especialista-frontend`** — G4 e o que a tela precisar para a coluna e a linha novas.
  Arquivos:
  - `apps/contabilidade/views_web.py`;
  - templates;
  - testes de tela.
- **`auditor-qa`** — auditoria nível 1 da versão integrada.

## Fora do escopo

- Marcação manual por lançamento e API: fatia 2, BL-605.
- Linhas fabricadas na DLPA (M1, BL-622).
- Validação contábil do Fred: BL-626.

## Evidências e integração (01/10/2026)

- **Tela** (`especialista-frontend`, cópia isolada; commit integrado `a6e7f39`):
  - G4 com mutantes mortos;
  - testes provando que a tela segue o contrato (coluna, grupo e linha novos, sem lista fixa);
  - DMPL de 13 colunas em 1 folha A4 paisagem, xMax 813 pt de 842 pt (10 mm de margem), letra mantida em 11 px;
  - a ação de `lancamentos_ambiguos` não manda mais dividir lançamento efetivado.
- **Servidor** (`desenvolvedor-pleno`, cópia isolada; commits integrados `7e5684f` e `36168d1`):
  - G1: coluna e linha novas;
  - identidade com a DLPA pela soma (`linhas_da_dmpl_que_somam_a_linha_da_dlpa`);
  - migração 0019, só de escolhas;
  - G2: condições (a) e (b) nas cinco colunas, mantendo a exceção da subscrição;
  - G3: par lançamento + estorno, com `_e_o_estorno_exato` e mensagens novas;
  - mutantes mortos em todas as regras.
- **Desvio aceito pelo `arquiteto-senior`, G3 (iii):** o par só sai da atribuição de
  linhas quando a regra **não** decide um dos dois lançamentos. Tirar todo par
  quebraria a identidade linha a linha com a DLPA em pares que ela detalha (ex.:
  constituição de reserva estornada) e um teste existente. Par decidido mantém as duas
  pontas, como antes.
- **Limite declarado:** quando o par neutralizado é um lançamento vetado que mexe em
  lucros e reservas, a DLPA ainda mostra duas linhas opostas de reserva (líquido zero),
  que a DMPL não mostra. Saldos e somas são iguais; só o detalhe por linha difere. É a
  mesma causa da M1 (BL-622, defeito da DLPA). O caso tem teste dedicado.
- **Verificação na integração (`36168d1`, Python 3.13 local):**
  - `ruff` limpo, `makemigrations --check` sem mudanças;
  - suíte completa com 4.596 aprovados;
  - 2 falhas conhecidas desta máquina: a de Python 3.13 e a soma de AGENTS.md das
    cópias de trabalho dos agentes.
- **Auditoria:** **pendente** (nível 1), sobre o commit integrado.

