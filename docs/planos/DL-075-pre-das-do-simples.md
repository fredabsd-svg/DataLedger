# DL-075 — Fiscal: pré-DAS do Simples Nacional para prestadores de serviço

**Demanda:** ordem do Fred de 08/10/2026 (RC-164); etapa 3 do roteiro de
execução do [DL-067](DL-067-plano-do-modulo-fiscal.md). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) — é o valor do DAS que o contador confere e
paga. Auditoria independente: uma rodada, uma correção, uma reconferência.

**Pré-apuração, nunca transmissão:** o produto calcula para o contador
**conferir contra o PGDAS-D**; não gera DAS, não transmite, não substitui o
aplicativo oficial (HI-55).

## Base

- Tabelas: [tabelas oficiais de 2026](../projeto/consultas/2026-10-08-tabelas-simples-2026.md)
  — LC 123/2006, Anexos I a V na redação da LC 155/2016, lidos no Planalto,
  vigentes de 01/01/2018 a 31/12/2026; repartição por tributo; notas do teto
  de 5% do ISS; §§ 1º-A, 1º-B, 5º-C a 5º-M e 24 do art. 18.
- Rotina e exemplos: Manual do PGDAS-D (versão 17/06/2025), exemplos 2, 4, 5
  e 8 e item 8.1 — **casos de referência dos testes**.
- Hipóteses: HI-64 a HI-71 (receita, mercado, fator r, arredondamento), HI-68
  (primeiro corte), HI-69 (folha informada), HI-71 (arredondar só o valor de
  cada tributo).

## Depende de

[DL-074](DL-074-receita-e-rbt12-do-simples.md): receita do mês por mercado,
confirmação e RBT12 por mercado.

## Escopo

1. **Tabelas como dado com vigência e fonte:** Anexos I a V (faixas, alíquota
   nominal, parcela a deduzir, repartição por tributo), cada linha com
   dispositivo, fonte e vigência 01/01/2018 a 31/12/2026. Nada de 2027
   (Res. CGSN 190/2026 e LC 214/2025, arts. 519 a 534 — só registrado).
2. **Atividades da empresa** (HI-68): cadastro, com vigência, das atividades
   que a empresa presta e do **enquadramento** de cada uma — Anexo III; Anexo
   III ou V pelo fator r (§§ 5º-I, 5º-J, 5º-M); Anexo IV (§ 5º-C, CPP fora do
   DAS). A escrituração ganha a atividade da receita (por nota ou padrão da
   empresa). Sem atividade enquadrada, o pré-DAS **recusa** e nomeia.
3. **Folha para o fator r** (HI-69): lançamento mensal informado, por
   componente (remuneração base INSS, pró-labore e autônomos, 13º, CPP
   recolhida, FGTS recolhido), confirmado como a receita; FS12 dos 12 meses
   anteriores (regra do art. 22 no ano de início); fator r **truncado** em 2
   casas; regras de zero do Manual 8.2.1 marcadas como rotina do PGDAS-D.
4. **Alíquota efetiva** (§ 1º-A): `(RBT12 × Aliq − PD) / RBT12`, RBT12 = 0 →
   1; por mercado; **precisão total**, sem arredondar.
5. **Repartição por tributo** (§ 1º-B): alíquota efetiva × percentual da
   faixa; **teto de 5% do ISS** com redistribuição proporcional aos federais
   (notas dos Anexos III e IV); diferença centesimal ao tributo de maior
   percentual (§ 1º-B, II).
6. **Segregação** do primeiro corte (HI-68): ISS retido → percentual do ISS
   desconsiderado; ISS devido a outro município → ISS por município;
   exportação → desconsidera PIS, Cofins e ISS (Res. 140 art. 25 § 3º); Anexo
   IV → sem CPP. Fora do corte, com **recusa nomeada**: ISS fixo, imunidade ou
   isenção municipal, construção com dedução de materiais, comunicação e
   transporte interestadual, IPI+ISS, RBT12 acima do sublimite (faixa 6 e
   excesso — exemplo 8 do Manual fica como caso de referência futuro).
7. **Valor por tributo** arredondado a 2 casas, `ROUND_HALF_UP` (HI-71); total
   = soma dos tributos.
8. **Bloqueios** do pré-DAS: mês não confirmado; RBT12 não apurável; regime de
   caixa em 2026 (HI-66); atividade sem enquadramento; fator r sem folha
   confirmada quando exigido.
9. Telas e API: pré-DAS do mês por empresa (receita segregada, RBT12, fator r,
   faixa, alíquota nominal e efetiva, tributos, memória de cálculo com o
   dispositivo de cada passo), cadastro de atividades e folha informada.

## Decisões tomadas na implementação

Depois da [consulta do pré-DAS](../projeto/consultas/2026-10-08-contador-senior-pre-das.md)
e da [consulta sobre HI-76 e HI-77](../projeto/consultas/2026-10-08-contador-senior-hi76-hi77.md):

- **ISS retido e exportação** (HI-78): percentual desconsiderado, sem
  redistribuição; na exportação saem só Cofins, PIS e ISS.
- **Teto do ISS antes da desconsideração** (HI-79): na 5ª faixa, aplica-se o
  teto de 5% e redistribui-se; depois sai o ISS (5%) da receita retida ou
  exportada. Inferência textual, sem exemplo oficial.
- **Receita informada exige a situação do ISS** no mercado interno (HI-80):
  próprio município, outro município ou retido; sem ela o pré-DAS recusa e
  nomeia a receita. Exportação não aceita situação. Migração `fiscal 0005`.
- **Sublimite** (HI-81): recusa quando o RBT12 do mercado passa de R$ 3,6 mi
  ou a receita acumulada no ano passa do sublimite.
- **Fator r na empresa nova** (HI-81): folha pelo mesmo critério do RBT12
  (art. 26 § 4º), inclusive atravessando o ano (HI-76); primeiro mês pela
  folha e receita do próprio mês; zeros pelo § 7º.
- **ISS a outro município**: valor certo, mas sem o detalhamento por
  município do extrato do PGDAS-D (BL-668).
- **Alíquota da 6ª faixa no § 5º** fica fora: PE-78.

## Critérios de aceite

1. Os **exemplos 2, 4 e 5** do Manual do PGDAS-D batem **centavo a centavo**
   por tributo e no total (Anexo III 2ª faixa: 8.080,00; Anexo III 3ª faixa
   com r = 0,50: 997,20; Anexo V 3ª faixa com r = 0,20: 1.752,00), e o exemplo
   do item 8.1 (Anexo I: 9,2%) na alíquota efetiva.
2. Fator r 0,2799 → 0,27 → Anexo V; 0,28 → Anexo III.
3. Teto do ISS: na 5ª faixa do Anexo III, alíquota efetiva acima de
   14,92537% fixa o ISS em 5% e redistribui pelos percentuais da nota, com a
   soma igual à alíquota efetiva; idem Anexo IV acima de 12,5%.
4. ISS retido: o ISS daquela receita sai do valor devido; os demais tributos
   não mudam.
5. Exportação: sem PIS, Cofins e ISS; RBT12 e faixa da exportação.
6. Anexo IV: sem CPP no DAS.
7. Cada bloqueio do item 8 recusa com mensagem que nomeia o que falta.
8. Memória de cálculo mostra cada passo com o dispositivo e a fonte.
9. Tabelas fora de vigência (2027) recusadas citando a Res. CGSN 190/2026.
10. Isolamento e permissões como na DL-072 e na DL-074.
11. Mutação: trocar a parcela a deduzir de faixa, arredondar a alíquota
    efetiva, arredondar o fator r em vez de truncar, ignorar o teto do ISS ou
    a retenção derruba testes.
12. Não regressão completa; migrações aditivas em banco vazio e reversão.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — tabelas, atividades, folha, cálculo, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/fiscal/` (modelos, migração, `simples_tabelas.py`, `pre_das.py`, `folha_fator_r.py`, API), testes `test_dl075_*` |
| B — telas | `auxiliar-implementacao` (Haiku) | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Migrações aditivas. Reverter é reverter as migrações e o commit.
