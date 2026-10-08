# DL-074 — Fiscal: receita mensal, confirmação e RBT12 do Simples Nacional

**Demanda:** ordem do Fred de 08/10/2026 (RC-164); etapa 2 do roteiro de
execução do [DL-067](DL-067-plano-do-modulo-fiscal.md). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) — o RBT12 decide a faixa e a alíquota do
DAS que o contador entrega. Auditoria independente: uma rodada, uma
correção, uma reconferência.

## Base

[Consulta RBT12 ao contador-senior](../projeto/consultas/2026-10-08-contador-senior-rbt12.md)
(Res. CGSN 140/2018 consolidada e Manual do PGDAS-D lidos na íntegra; SC
Cosit 102/2026; Portaria CGSN 54/2025). Hipóteses usadas: HI-64 a HI-67 e
HI-70. **Nada aqui é transmissão** — é pré-apuração para o contador conferir
contra o PGDAS-D.

## Depende de

[DL-072](DL-072-escrituracao-das-nfse-prestadas.md) **com a natureza
desdobrada** (HI-67): exportação de serviço; ISS imune, isento ou reduzido
por lei do ente; fora da lista da LC 116. Cada natureza diz o **mercado**
(interno ou externo).

## Escopo

1. **Cadastro:** `data de abertura no CNPJ` na empresa (HI-65), opcional no
   banco e **obrigatória para apurar**; e a opção pelo **regime de caixa** no
   Simples por ano-calendário (só até 2026 — HI-66).
2. **Receita informada** (HI-64) por empresa, competência e mercado, com
   origem em catálogo fechado — histórico anterior ao uso do sistema; venda de
   mercadoria ainda não escriturada; serviço com documento de município não
   integrado; outras receitas da atividade (Res. 140 art. 2º § 4º); ajuste —
   motivo e documento de suporte obrigatórios, autor, trilha; **rascunho →
   confirmada → estornada**, como a escrituração. Origem "histórico" só em
   meses anteriores ao início de uso do sistema pela empresa.
3. **Receita do mês por mercado** = escriturações efetivadas + receitas
   informadas confirmadas, com a composição visível (quanto veio de documento
   e quanto foi informado).
4. **Confirmação mensal** "receita de MM/AAAA completa", por empresa e mês
   (vale para os dois mercados); ato com autor e trilha; **reabrir** a confirmação exige
   motivo. Estornar uma escrituração ou receita informada de mês confirmado
   **reabre** a confirmação daquele mês e o marca "a retificar" (Res. 140 art.
   18: cancelamento deduz no período de origem) — nunca abate o mês corrente.
5. **RBT12 por mercado** (Res. 140 art. 22): § 1º regra geral (12 meses
   anteriores ao período de apuração); § 2º primeiro mês de atividade
   (receita do próprio mês × 12); § 3º meses seguintes do ano de início
   (média dos meses anteriores × 12, mês sem receita = zero); § 4º abertura no
   ano anterior ao da opção; § 5º RBT12 acima do limite com ano dentro.
   Fração de mês conta como mês inteiro. Só com todos os meses da janela
   **confirmados**; senão a resposta é "não apurável" com a lista dos meses.
6. **Limites como dado com vigência e fonte** (HI-70): limite, sublimite,
   proporcionais do ano de início, por mercado. Avisos: receita acumulada no
   ano acima do sublimite ou do limite, e se o excesso passou de 20% (Res.
   140 art. 81), com o dispositivo citado. Valores de 2027 **não** entram.
7. Telas: receita informada (lançar, confirmar, estornar), painel do mês por
   empresa (composição, confirmação, RBT12 por mercado, avisos de limite) e o
   cadastro da data de abertura. API equivalente.

**Fica fora:** alíquota, anexos, fator r, pré-DAS (etapa seguinte); importar
o extrato do PGDAS-D (etapa própria); regime de caixa além do bloqueio
explicado; receitas de 2027 em diante com as regras da Res. CGSN 190/2026.

## Decisões tomadas na implementação

- **Início de uso do sistema** = mês do cadastro da empresa (HI-73).
- **Receita das notas** = `vServ` (HI-74).
- **Efetivar em mês confirmado** reabre a confirmação com trilha, como o
  estorno (HI-75); o total guardado no ato é a segunda camada.
- **Regime de caixa** é uma tabela própria por ano (`OpcaoRegimeCaixaSimples`),
  recusada a partir de 2027 no serviço e no banco.
- **Limites** são dado com valor, dispositivo, fonte, início e fim de vigência
  (`apps/fiscal/rbt12.py`), só os de 2026; apurar 2027 é recusado citando a
  Res. CGSN 190/2026.
- **RBT12** com média não exata guarda a precisão (sem arredondar a centavos);
  a tela mostra duas casas e avisa quando há casas escondidas.
- **Não modelados:** teto de ME (R$ 360 mil); art. 3º § 3º (limite
  proporcional para a opção com abertura no ano anterior); UF do sublimite
  (a Portaria 54/2025 vale para todas em 2026); a faixa de 20% do sublimite
  cita o art. 81 por analogia (hipótese).
- **Tela de edição de empresa não existe** (BL-666): a data de abertura de
  empresa já cadastrada só entra pela API.

## Regras de engenharia

`Decimal` sem arredondar RBT12; confirmação e receita informada imutáveis
depois de confirmadas (estorno ou reabertura com motivo); isolamento por
escritório e empresa em toda porta; permissão de quem escritura; nenhuma
constante de valor legal sem fonte e vigência no próprio dado.

## Critérios de aceite

1. Receita do mês = soma das escriturações efetivadas + informadas
   confirmadas, por mercado; exportação nunca soma no interno.
2. RBT12 regra geral confere com cálculo independente em 3 casos de
   referência (escritos à mão no teste, não derivados do código).
3. Ano de início: os exemplos do Manual do PGDAS-D (abertura 02/2018) e da
   consulta (abertura 10/03/2026: RBT12 240.000; 240.000; 300.000; 300.000)
   batem exatamente.
4. Abertura no ano anterior à opção usa o § 4º até o 12º mês e a regra geral
   do 13º em diante.
5. Mês da janela sem confirmação → "não apurável" listando os meses; sem
   data de abertura → recusa nomeada.
6. Estornar escrituração ou receita de mês confirmado reabre a confirmação e
   marca o mês "a retificar"; o RBT12 dos meses seguintes volta a "não
   apurável" até reconfirmar.
7. Origem "histórico" recusada em mês a partir do início de uso do sistema.
8. Avisos de sublimite, limite e excesso de 20%, com o dispositivo; limite
   proporcional no ano de início (fração de mês = mês inteiro).
9. Empresa no regime de caixa em 2026: RBT12 apurado pela competência e aviso
   de que o pré-DAS ficará bloqueado.
10. Isolamento e permissões como na DL-072, na tela e na API.
11. Mutação: trocar § 3º por § 1º, contar exportação no interno, ou ignorar a
    confirmação derruba testes.
12. Não regressão: suíte completa, `ruff`, `check`, `makemigrations --check`,
    migração em banco vazio.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — cadastro, receita informada, confirmação, RBT12, limites, API | `auxiliar-implementacao` (Haiku, RC-164) em cópia isolada | `apps/empresas/` (data de abertura, migração), `apps/fiscal/` (modelos, migração, `receita.py`, `rbt12.py`, API), testes `test_dl074_*` |
| B — telas | `auxiliar-implementacao` (Haiku) | `apps/fiscal/views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Migrações aditivas (campo novo na empresa, tabelas novas no fiscal). Reverter
é reverter as migrações e o commit; nenhum dado existente muda.
