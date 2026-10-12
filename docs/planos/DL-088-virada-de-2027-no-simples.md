# DL-088 — Fiscal: virada de 2027 no Simples Nacional

**Demanda:** ordem do Fred de 09/10/2026 (RC-175). Hoje o produto **recusa
de propósito** o Simples de 2027 (`rbt12.py`, `pre_das.py`). Sem esta etapa,
em 01/01/2027 nenhum cliente do Simples é apurado. A recomendação do
`contador-senior` é dar a esta etapa prioridade sobre o ICMS-TO (HI-145,
PE-90). **Executa depois da integração da
[DL-082](DL-082-pre-das-de-comercio-e-industria.md)**, porque as duas mexem
em `pre_das.py` e `receita.py`.
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 1 (§3.1). A auditoria
faz uma rodada, uma correção e uma reconferência.

**É pré-apuração para conferência.** O produto não transmite nem gera DAS
(HI-55).

## Base

[Consulta ao contador-senior sobre a leitura oficial da virada de 2027](../projeto/consultas/2026-10-09-contador-senior-virada-2027-simples.md),
de 09/10/2026. Foram lidos:

- a Res. CGSN 190/2026 no DOU, com os cinco Anexos novos;
- as Res. 186, 191 a 194;
- a LC 123 na redação da LC 214 (art. 517 e Anexos XVIII a XXII) e da LC
  227, no Planalto;
- a NT 2026.008 da NF-e, em cópia local.

Hipóteses HI-146 a HI-149; pendência PE-92 com o Fred.

## Escopo

1. **Tabelas 2027-2028** em `simples_tabelas.py`, como dado com vigência de
   01/01/2027 a 31/12/2028:
   - os cinco Anexos, com CBS e IBS;
   - os tetos do ISS dos Anexos III e IV, com o IBS na redistribuição;
   - as fórmulas do sublimite — **saíram desta etapa** (ver "Fica fora"):
     a do Anexo II para o ICMS usa parâmetros do Anexo III na consulta e
     precisa de confirmação do domínio antes de virar código (BL-704);
   - a fonte (DOU, edição, URL e data da leitura).

   A escolha da tabela passa a ser pela data do período. 2029 em diante
   continua recusado (divergência entre a lei e a Resolução, HI-146).
2. **RBT12 de 2027** em `rbt12.py` (HI-147):
   - a janela passa a ser a dos 12 meses antecedentes ao mês anterior;
   - início de atividade:
     - 1º e 2º meses: "primeira faixa" (um estado próprio, sem RBT12
       numérico);
     - do 3º ao 13º: a média dos meses antecedentes ao mês anterior × 12;
     - do 14º em diante: a regra geral;
   - os limites passam a ter vigência;
   - a mesma defasagem vale para o FS12 do fator r;
   - 2026 e anteriores **não mudam**.
3. **Pré-DAS de 2027** em `pre_das.py` (HI-148):
   - sai a recusa de 2027;
   - CBS e IBS entram no lugar de PIS e Cofins;
   - na exportação, ficam desconsiderados IBS, CBS, IPI, ICMS e ISS;
   - segmento novo de tributação concentrada ou ST de IBS e CBS;
   - opção pelo regime regular por semestre, como dado da empresa com
     vigência, com a dedução das parcelas de CBS e IBS (art. 22-A);
   - em 2027, o Anexo II fica só para a indústria com IPI mantido (Zona
     Franca); a produção própria fora dela vai para o Anexo I. A regra do
     anexo pela natureza e pelo CFOP da DL-082 ganha essa vigência.
4. **Receita de NF-e de 2027** (HI-149):
   - para empresa do Simples no regime único, a efetivação de nota de 2027
     passa a ser aceita, com receita igual ao `vProd` e o `vProdLiq`
     guardado como memória, quando o leitor tiver o campo (BL-687);
   - para o Presumido e para quem optou pelo regime regular, a recusa
     continua, com o motivo nomeado.
5. **Calendário de prazos da virada** na tela do Simples: avisos com fonte,
   sem transmitir nada (PE-92).
   - opção pelo Simples até 15/10/2026;
   - opção pelo regime regular até 30/10/2026;
   - receitas anteriores à opção até 20/12/2026 e 20/01/2027;
   - DEFIS no PGDAS-D de janeiro a março.
6. **Telas e API:** o pré-DAS de 2027 mostra CBS e IBS por segmento, o
   estado "primeira faixa" e a opção pelo regime regular.

**Fica fora:**
- 6ª faixa e excesso de sublimite;
- as fórmulas do sublimite (eram do escopo 1; saíram na correção da rodada 1
  — BL-704 — porque a do Anexo II para o ICMS usa parâmetros do Anexo III na
  consulta e não está confirmada pelo domínio);
- 2029 em diante;
- a CBS e o IBS do regime regular em si (alíquota de referência ainda não
  publicada, P4);
- Presumido em 2027 (a CBS no lugar do PIS/Cofins é outra etapa);
- MEI.

## Critérios de aceite

1. As tabelas de 2027-2028 batem com o DOU, número a número; cada linha de
   repartição soma 100%. Os valores esperados são escritos à mão.
2. A janela do RBT12 em 2027 é a defasada, e o início de atividade segue as
   três fases. Períodos de 2026 e anteriores ficam idênticos a antes.
3. O pré-DAS de 2027 bate ao centavo, por tributo, em cenários escritos à
   mão (comércio, serviço com teto do ISS, exportação, regime regular com
   dedução). Os testes da DL-075 e da DL-082 passam sem mudar a
   expectativa.
4. A receita de NF-e de 2027 é aceita só no regime único e recusada nos
   demais casos, com o motivo.
5. Isolamento e permissões no servidor.
6. **Mutação:** cada um destes defeitos derruba teste:
   - janela sem defasagem;
   - PIS e Cofins em 2027;
   - IPI fora da exportação;
   - ignorar o art. 22-A;
   - tabela de 2026 usada em 2027.
7. Regressão completa numa única invocação. Migração aditiva e reversível,
   se houver.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — tabelas, RBT12, pré-DAS, opção pelo regime regular, receita de NF-e, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `simples_tabelas.py`, `rbt12.py`, `pre_das.py`, `receita.py`, `escrituracao_nfe.py`, `models.py` e migração, se for preciso; APIs; testes `test_dl088_*` |
| B — telas e calendário | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `templates/fiscal/` |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

### Ajuste da divisão (arquiteto, 10/10/2026)

A DL-084 está em desenvolvimento em paralelo e mexe em `models.py`,
`escrituracao_nfe.py` e na migração `fiscal 0015`. Para que os conjuntos de
arquivos fiquem disjuntos, a frente A foi dividida:

- **A1 (agora):** tabelas de 2027-2028, RBT12 defasado e início de atividade,
  motor do pré-DAS de 2027 (CBS e IBS, exportação, ST de IBS-CBS, art. 22-A
  recebido como parâmetro, Anexo II só com IPI mantido). Arquivos:
  `simples_tabelas.py`, `rbt12.py`, `pre_das.py`, `receita.py`, testes
  `test_dl088_*`. **Sem** `models.py`, migração ou `escrituracao_nfe.py`. O
  caminho público do pré-DAS de 2027 **continua recusado**, com o motivo
  "falta a opção pelo regime regular": calcular sem saber da opção poria CBS
  e IBS no DAS de quem optou pelo regime regular.
- **A2 (depois da integração da DL-084):** a opção pelo regime regular como
  dado da empresa com vigência por semestre (migração nova), a liberação do
  pré-DAS de 2027, a receita de NF-e de 2027 (HI-149) e a API.

Não há urgência de calendário: o primeiro pré-DAS de 2027 é o de janeiro,
apurado em fevereiro de 2027.

## Entrega da frente A1 (10/10/2026)

Integrada na branch. Medido pelo desenvolvedor, num banco próprio: suíte
completa 9.374/1/55 (a falha é a de ambiente, Python 3.13 local); 49 testes
novos.

- **Tabelas de 2027-2028** com CBS e IBS, tetos do ISS e fonte do DOU; a
  tabela é escolhida pela data do período.
- **RBT12 defasado** a partir de 01/2027, início de atividade em três fases,
  FS12 com a mesma janela; 2029 recusado com a divergência da 6ª faixa.
- **Motor do pré-DAS de 2027:** CBS e IBS no lugar de PIS e Cofins;
  exportação sem IBS, CBS, IPI, ICMS e ISS; art. 22-A como dedução; produção
  própria no Anexo I. O caminho público **recusa 2027** com o motivo
  `opcao_regime_regular_nao_informada`.
- **Mutantes** do critério 6: os cinco derrubam testes.
- Cinco testes antigos que testavam a recusa de 2027 passaram a testar a de
  2029, com a mesma asserção.
- Hipóteses novas: HI-152 (monofasia lida como tributação concentrada; sem
  dado de Zona Franca; limites anuais sem releitura).

Pendências para a A2 e a frente B:
- a opção pelo regime regular e o dado de IPI mantido (Zona Franca);
- a NF-e de 2027, que `escrituracao_nfe.py` ainda recusa (HI-133, HI-149);
- a tela do RBT12 mostra "há meses da janela sem confirmação" quando o
  motivo real é "primeira faixa" (início de atividade);
- as fórmulas de sublimite não existem no módulo; a do Anexo II para o ICMS
  usa parâmetros do Anexo III na consulta, e isso deve ser conferido antes
  de implementar.

## Reversão

Reverter o merge volta a recusar 2027. A opção pelo regime regular, se for
coluna ou tabela nova, sai com a reversão da migração, que recusa se houver
dado.

## Entrega da frente A2 (11/10/2026)

Commit `849d06d`. O dado que libera 2027 existe de ponta a ponta:

- **Opção de regime de IBS/CBS por semestre** (`OpcaoRegimeIbsCbsSimples`,
  chave empresa/ano/semestre, migração `0017`): `regime_unico` deixa CBS e
  IBS no DAS; `regime_regular` deduz as parcelas (art. 22-A); **sem linha =
  opção não informada**, e a recusa `opcao_regime_regular_nao_informada`
  continua exatamente como estava. Insert-only, com trilha.
- **IPI mantido (Zona Franca; HI-152)** (`IpiMantidoZfmEmpresa`, com fonte
  obrigatória): em 2027 o Anexo II vale só para a indústria com IPI mantido;
  **ausente não presume ZFM** — produção própria vai ao Anexo I com aviso
  nomeado na memória (é pré-apuração para conferência; a validação do Fred
  segue na HI-152).
- **Receita de NF-e de 2027 (HI-149):** aceita no regime único, com receita
  igual ao `vProd` e `vProdLiq` guardado como memória quando o leitor o
  trouxer (BL-687); regime regular e Presumido continuam recusados, com o
  motivo nomeado. **W16 não se aplica em 2027** — a composição do `vNF` não
  está publicada (PE-84.4); aplicá-la seria presumir leiaute.
- **API** de leitura e gravação dos dois dados, com o pré-DAS liberado nas
  mesmas condições do serviço.
- 41 testes novos; mutantes mortos: ignorar o IPI mantido, aceitar sem
  checar o regime e usar a receita do MOC no lugar do `vProd`. Guardas
  transversais cobertas na integração (arquiteto): as quatro restrições
  novas registradas em `apps/core/restricoes.py` e os dois modelos na
  cobertura da trilha (DL-030).

## Entrega da frente B (11/10/2026)

Telas e calendário, pelo padrão das telas irmãs da DL-084 (papel checado
antes de resolver a empresa, erros campo a campo, §2B):

- **Opção pelo regime regular** (insert-only em duas etapas, nomeando o alvo
  antes de gravar; a segunda tentativa mostra a recusa nomeada do serviço) e
  **IPI mantido (Zona Franca)** (cadastro corrigível, fonte obrigatória,
  "não informado" dito como não informado).
- **Pré-DAS de 2027 na tela:** CBS e IBS por segmento e no total por
  tributo, a dedução do art. 22-A por linha ("deduzido (valor)"), a opção do
  semestre que valeu e o estado "primeira faixa" (lido de
  `Rbt12.primeira_faixa`).
- **Pendência da A1 corrigida:** a tela do RBT12 passa a dizer "Não
  apurado: 1ª faixa (1º e 2º mês de atividade), sem RBT12 numérico" quando o
  motivo é início de atividade — o texto de mês pendente continua só no caso
  dele.
- **Calendário da virada** (parcial única, no fim das telas de receita do
  mês e do pré-DAS): os quatro prazos do escopo, cada um com o dispositivo
  (Res. CGSN 194/2026; Res. CGSN 190/2026, arts. 144-D, 144-E e 38-B) e a
  fonte com a data da leitura (consulta de 09/10/2026). Informativo: nada é
  registrado nem transmitido (PE-92).
- **Portão de efetivação de NF-e de 2027:** as telas de escrituração passam
  a empresa a `motivo_bloqueio_efetivacao` — o botão fica desabilitado com o
  motivo real (sem opção / regime regular / Presumido) e habilitado no
  regime único.
- 25 testes novos; mutantes mortos: inverter a checagem de permissão de uma
  tela nova e ignorar o regime no botão de efetivar.
- Inventários vivos atualizados (rotas do DL-024, `ROTULOS_DE_TELA` da
  trilha). O `mapa-de-telas.md` é levantamento datado da DL-040 (os totais
  dele já trazem aviso de não recontagem) e não foi recontado.
- **Flutuante pré-existente registrado:** `test_concorrencia.py::
  test_corrida_real_de_documento_produz_um_unico_documento` oscila sob
  carga (1 falha em 3 rodadas isoladas; verde na rodada final) — BL-703.
- **Pendência declarada:** `presumido.py` chama
  `motivo_bloqueio_efetivacao` sem a empresa (o booleano é idêntico para o
  Presumido); o motivo nomeado ali é ajuste de uma linha no domínio do
  Presumido — BL-702.

Próximo: auditoria independente — rodada 1, correção única, reconferência
(§3.1).
