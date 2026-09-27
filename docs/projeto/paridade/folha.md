# Plano de paridade — Folha e Ponto

## Introdução

### Escopo

Este documento lista, **item por item**, tudo o que os manuais de referência do
sistema de mercado (Domínio Folha, versão 10.1A-12, 1.433 páginas, 2018; e
Domínio Ponto Eletrônico, 128 páginas, 2012) descrevem como capacidade dos
módulos de **Folha de Pagamento** e **Ponto Eletrônico**, cruzado com o que o
DataLedger tem **hoje**, medido em código. É o plano detalhado que a
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md) pediu para este
par de módulos, no mesmo padrão do plano já escrito para
[Contabilidade](contabilidade.md). Cobre relatórios e funções — cadastros,
regras de cálculo, eventos do contrato de trabalho, integração contábil,
eSocial e ponto — com dependência, dado, regra, tela e critério de aceite
para cada um.

Não é plano de etapa. Cada item vira um plano `DL-xxx` próprio quando for
priorizado; este documento é o mapa que evita que esse plano comece do zero
ou esqueça uma dependência, no espírito do pedido do Fred: *"caso outro dev
comece a codar, ele não se perca"*.

### Fontes

- [mapa-funcional-folha.md](../mapa-funcional-folha.md) — inventário de
  relatórios e funções dos dois manuais, com páginas, feito pelo auxiliar de
  pesquisa da DL-047, e a cadeia de dependências e ondas recomendadas.
- [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) — as
  três classes de documento (conferência, demonstração, livro), estendidas
  aqui a uma quarta que a Folha exige e a Contabilidade não tinha: o
  **documento de forma prescrita** por norma trabalhista (recibo, TRCT,
  aviso), e o **arquivo de obrigação**. Ver "Convenções" abaixo.
- [requisitos.md](../requisitos.md), [backlog.md](../backlog.md) e
  [decisoes.md](../decisoes.md) — RC, HI, PE, BL e DE já existentes são
  **reaproveitados e citados**, nunca duplicados. Em especial: **RC-129**
  (relação entre o carnê-leão do módulo de livro-caixa e o carnê-leão
  calculado a partir da folha do empregador — ver FOL-48), **DE-010**
  (arredondamento por regra, com **truncamento** documentado para folha e
  eSocial, fonte: Manual de Orientação do eSocial), **RC-79/PE-42** (teto de
  200 partidas por lançamento contábil, achado originalmente motivado por
  contabilização de folha).
- [escopo.md](../../escopo.md), seção "Folha de Pagamento" e "Integrações e
  arquitetura" — orientação inicial de produto; a seção de integrações fixa
  que conectores oficiais exigem credenciamento e homologação verificados
  antes de existir, o que se aplica a toda transmissão ao eSocial, à
  DCTFWeb e ao FGTS Digital.
- Código de `apps/` (`empresas`, `contabilidade`, `livro_caixa`), lido nesta
  sessão para confirmar que **não existe** app de folha e para descrever com
  precisão o único módulo adjacente hoje em produção, o livro-caixa/carnê-leão
  ([DL-046](../../planos/DL-046-livro-caixa-e-carne-leao.md)).

Os manuais do sistema de referência **não estão e nunca estarão neste
repositório**. Nada do texto deles foi copiado; o que está aqui é
entendimento nosso, em nossas palavras, com a página citada para quem quiser
conferir a rotina.

### O aviso central: o manual é de 2018, e a folha mudou muito desde então

O manual de Folha traz, como capacidades vivas, um conjunto de recolhimentos e
declarações que a legislação **substituiu ou alterou** depois de 2018:
GFIP/SEFIP, GRRF, GRFC, GRCSU, DIRF, RAIS, CAGED como arquivo próprio,
Homolognet. O eSocial, a DCTFWeb, o FGTS Digital e a EFD-Reinf tomaram, no
todo ou em parte, o lugar dessas obrigações. O manual de Ponto Eletrônico é
de 2012 e descreve o AFDT e o ACJEF, arquivos da Portaria MTE 1.510/2009, que
a Portaria MTP 671/2021 substituiu.

**Cada uma dessas obrigações tem um item próprio na seção "Fora de escopo,
obsoleto ou dependente de confirmação"**, com o sucessor **provável** e a
fonte oficial que decide — nunca com data de extinção afirmada como fato.
Nenhuma delas entra em código a partir deste documento sem confirmação na
fonte oficial vigente e validação do Fred (AGENTS.md §10).

### Estado atual no DataLedger (2026-09-27)

**O módulo não existe.** `apps/` contém `accounts`, `auditoria`,
`contabilidade`, `core`, `documentos`, `empresas`, `fiscal`, `livro_caixa` e
`tenancy` — não há `apps/folha` nem `apps/ponto`. Não existe empregado,
rubrica, cálculo de folha, evento de eSocial nem relógio de ponto no código.
O único módulo adjacente é `apps/livro_caixa/` (carnê-leão e livro-caixa de
pessoa física, [DL-046](../../planos/DL-046-livro-caixa-e-carne-leao.md)),
regime de caixa — sua relação com a Folha está isolada e explicada no
FOL-48, porque os dois módulos calculam um "carnê-leão" com sentido
**diferente**: o de `livro_caixa` é o do **profissional autônomo** que
escritura sua própria renda; o da Folha (RPA/Outros/Carnê-Leão, páginas
795-820 do manual) é o do **tomador de serviço** apurando a retenção de
quem ele paga.

**Transmissão está fora deste plano.** Gerar e conferir eventos do eSocial,
declarar na DCTFWeb ou operar o FGTS Digital é preparação; **enviar** essas
informações ao órgão exige certificado digital e canal homologado
([escopo.md](../../escopo.md), "Integrações e arquitetura": *"criar
conectores... após verificar documentação, disponibilidade, credenciamento e
homologação... diferenciar importação, exportação, simulação e transmissão
efetiva"*). A Onda 3 deste plano cobre a **preparação**; a transmissão em si
é decisão separada, registrada como FOL-80.

### Convenções

- **ID:** `FOL-NN`, sequencial, sem reuso, cobrindo Folha e Ponto (mesmo
  prefixo — são um par de módulos que só funcionam integrados, como o
  [README](README.md) já lista).
- **Classe de documento**, ampliando as quatro de
  [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) para o
  vocabulário trabalhista:
  - **C** — relatório de **conferência** (resumo, extrato, movimentos):
    forma livre, decisão do escritório.
  - **F** — documento de **forma prescrita por norma trabalhista** (recibo
    de folha/férias, TRCT, aviso prévio, termo de quitação): o mesmo
    princípio da classe **livro** da Contabilidade — a forma é quase
    totalmente fixada pela norma, a personalização é marginal. Qual norma
    fixa qual campo é, item a item, **a confirmar**.
  - **A** — **arquivo de obrigação** ou de banco (GPS, DARF, arquivo de
    crédito em conta, evento do eSocial): leiaute oficial ou do
    destinatário, sem margem de personalização.
- **Fonte normativa "a confirmar":** esta sessão **não conferiu** o
  dispositivo na fonte oficial vigente para nenhum item deste plano — nem
  alíquota, nem prazo, nem leiaute. É citação preliminar, baseada no
  conhecimento geral do domínio e no que o próprio
  [mapa-funcional-folha.md](../mapa-funcional-folha.md) já registrou como
  fontes a consultar. **Nenhum valor de tabela (IRRF, INSS, salário mínimo,
  FAP, salário-família) aparece neste documento como fato** — todo exemplo
  numérico é sintético e nomeia a alíquota como "da tabela vigente, a
  confirmar". Antes de qualquer linha de código que implemente cálculo,
  tabela ou leiaute, a fonte precisa ser lida na íntegra e validada pelo
  Fred (AGENTS.md §10).
- **"Existe"** significaria que há código de produção — não se aplica a
  quase nenhum item deste plano, porque o módulo não existe; quando um item
  depende de algo que **já existe** em outro módulo (ex.: a contabilidade
  que recebe a integração), isso está dito explicitamente.
- Todo valor monetário de exemplo é sintético, sem relação com cliente real
  (AGENTS.md §7). Os exemplos deste documento usam, por pedido do Fred,
  salário-base de R$ 3.000,00, 10 horas extras a 50% e as demais variações
  descritas item a item.

### Como ler

1. Comece pela seção "Mapa de dependências e ondas" para saber a ordem.
2. Cada item é autossuficiente: um desenvolvedor pode abrir só o item que lhe
   foi atribuído e encontrar tudo que precisa, inclusive o que ele depende e
   o que ele destrava.
3. Onde a fonte normativa não foi conferida, **isso está escrito
   explicitamente** — não implemente cálculo, alíquota ou leiaute a partir
   deste documento sem antes ler a fonte oficial vigente e obter validação
   do Fred.
4. A seção final "Fora de escopo, obsoleto ou dependente de confirmação" não
   é lista de itens a ignorar para sempre: é lista de itens que **precisam
   de uma decisão do Fred antes** de virar código, porque a norma mudou
   desde 2018 ou porque a decisão de produto é "não agora".

## Mapa de dependências e ondas

A ordem segue a recomendação da
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md) e do
[mapa-funcional-folha.md](../mapa-funcional-folha.md): primeiro a fundação e
o cálculo mensal **sem** nenhuma transmissão, porque é o que entrega valor
sozinho (o escritório já roda a folha do mês e emite o holerite) e é a base
de que tudo o resto depende; depois o ciclo anual e a integração contábil;
depois o eSocial **como preparação**; depois pró-labore, autônomos e ponto;
por fim os anuais e utilitários. Transmissão fica no fim de tudo, como
decisão separada.

```
ONDA 1 — fundação e cálculo mensal, sem transmissão
  FOL-04 Rubricas (proventos/descontos, incidências)
    ├─> FOL-05 Bases de cálculo
    ├─> FOL-06 Tabela de IRRF          ─┐
    ├─> FOL-07 Tabela de INSS/salário-família/RAT ├─ tabelas por vigência
    ├─> FOL-08 FAP                      │
    ├─> FOL-09 Salário mínimo          ─┘
    └─> FOL-10 Contribuição sindical patronal e índices de correção de médias
  FOL-11 Cargos, funções e CBO
  FOL-12 Horários e jornadas
  FOL-13 Filiais, departamentos e centros de custo
  FOL-04 + FOL-06..10 ──> FOL-14 Sindicatos dos empregados (motor de regras)
    └─> FOL-15 Convenção coletiva e alteração salarial retroativa
  FOL-16 Sindicatos patronais (independente, alimenta FOL-10)
  FOL-01 Empregados ──┐
  FOL-02 Estagiários  ├─ (dependem de FOL-11, FOL-12, FOL-13, FOL-14)
  FOL-03 Contribuintes individuais ─┘
  FOL-01..03 + FOL-04..15 ──> FOL-17 Cálculo mensal da folha e tipos de folha
    ├─> FOL-18 Adiantamento salarial e do 13º
    ├─> FOL-19 Apuração previdenciária
    ├─> FOL-20 Lançamentos (por empregado, rubrica, grupo, automáticos)
    ├─> FOL-21 Holerite (recibo de pagamento)
    ├─> FOL-22 Resumo, extrato e relação de líquidos da folha
    ├─> FOL-23 Exportação de crédito em conta e cadastro para bancos
    └─> FOL-24 Rascunho × folha efetivada (invariante do projeto)

ONDA 2 — ciclo anual e integração contábil
  FOL-01 + FOL-14 ──> FOL-25 Períodos aquisitivos de férias
    ├─> FOL-26 Férias individuais (programação, aviso, gozo, recibo)
    └─> FOL-27 Férias coletivas
  FOL-01 + FOL-14 ──> FOL-28 13º salário (adiantamento e integral)
  FOL-25..28 ──> FOL-29 Provisão de férias e 13º
  FOL-01 + FOL-14 ──> FOL-30 Aviso prévio de rescisão (Lei 12.506/2011)
    └─> FOL-31 Rescisão individual e TRCT
          └─> FOL-32 Rescisão em grupo e complementar
  FOL-33 Afastamentos (INSS, maternidade, ausência justificada, mandato sindical)
    ├─> FOL-25 (afastamento consome/preserva período aquisitivo)
    ├─> FOL-34 Licença-prêmio
    ├─> FOL-35 Estabilidades
    └─> FOL-36 Aposentadoria (com rescisão ou por afastamento)
  FOL-37 CAT — Comunicação de Acidente de Trabalho (alimenta FOL-33)
  FOL-38 Trabalho intermitente (Lei 13.467/2017) — cálculo próprio, paralelo
  FOL-17 + FOL-26..32 ──> FOL-39 Integração contábil (folha, férias,
    rescisão, provisões, pagamentos) — destino já existe: apps/contabilidade

ONDA 3 — eSocial como preparação (sem transmissão)
  FOL-01..03 + FOL-11..17 ──> FOL-40 Parâmetros do eSocial da empresa
    ├─> FOL-41 Eventos de tabela (S-1000 a S-1080)
    ├─> FOL-42 Eventos não periódicos (admissão, afastamento, rescisão)
    ├─> FOL-43 Eventos periódicos (folha de pagamento)
    ├─> FOL-44 Painel de pendências e controle de eventos
    └─> FOL-45 Qualificação cadastral e manutenção de matrícula

ONDA 4 — pró-labore, autônomos (RPA) e ponto
  FOL-46 Pró-labore de sócios (depende de FOL-06, FOL-07, FOL-17)
  FOL-03 ──> FOL-47 RPA — recibo de pagamento a autônomo
    └─> FOL-48 Carnê-leão do tomador de serviço (retenção sobre RPA)
  FOL-49 Empréstimo consignado (depende de FOL-01, FOL-17)
  FOL-50 Vale-transporte
  FOL-51 Vale-alimentação
  FOL-52 Benefícios (plano de saúde, EPI, previdência complementar)
  FOL-53 Advertência e suspensão
  FOL-54 Ponto — horários, relógios e importação de marcações
    ├─> FOL-55 Ponto — abonos, acertos e reapuração
    ├─> FOL-56 Ponto — trocas de horário/período e saldos (banco de horas)
    ├─> FOL-57 Ponto — relatórios de presença, absenteísmo e inconsistências
    └─> FOL-58 Integração do ponto com a folha (rubricas de horas, alimenta FOL-04/FOL-17)

ONDA 5 — anuais e utilitários
  FOL-59 Alteração salarial individual e em grupo (depende de FOL-01, FOL-15)
    └─> FOL-60 Alteração retroativa de rubricas e diferenças salariais
  FOL-17 ──> FOL-61 Comprovante de rendimentos (informe de rendimentos)
  FOL-33 + FOL-37 ──> FOL-62 PPP — Perfil Profissiográfico Previdenciário
  FOL-17 + FOL-39 ──> FOL-63 Pagamentos (folha e encargos) e parcelamento
  FOL-31 ──> FOL-64 Termo de quitação anual de obrigações trabalhistas
  FOL-25 ──> FOL-65 Programação de férias e avisos de vencimento
  FOL-26 + FOL-31 ──> FOL-66 Simuladores de férias e rescisão
  FOL-67 Importação (cadastros, tabelas, RPA, sistemas concorrentes)
  FOL-68 Processos administrativos ou judiciais (suspensão de exigibilidade)

DEPOIS — transmissão (decisão separada, ver escopo.md)
  FOL-80 Transmissão ao eSocial, à DCTFWeb e ao FGTS Digital

FORA DE ESCOPO, OBSOLETO OU DEPENDENTE DE CONFIRMAÇÃO
  FOL-69 a FOL-79 — ver seção final
```

Consequência prática, no mesmo espírito da recomendação da DL-047: quem só
tem tempo para uma fatia deve fechar a **Onda 1** primeiro. Ela sozinha já
entrega o que um escritório faz todo mês — folha calculada, holerite,
resumo — sem tocar em nenhuma obrigação que a legislação alterou depois de
2018. A Onda 2 é o que o escritório faz **todo ano** (férias, 13º, rescisão)
e fecha o ciclo com a contabilidade. A Onda 3 é a que mais exige cautela
normativa: cada evento do eSocial listado aqui vem do manual de 2018 e
precisa ser conferido contra o leiaute (MOS) vigente antes de qualquer
código.

## Onda 1 — Fundação e cálculo mensal, sem transmissão

### FOL-01 — Empregados

**O que é.** O cadastro central de quem trabalha para a empresa com vínculo
empregatício (CLT): dados pessoais, contratuais (cargo, função, salário,
jornada, sindicato), documentos (CTPS, PIS/NIS), dependentes e o histórico de
tudo isso ao longo do contrato.

**Exemplo.** Empregada Maria, admitida em 03/01/2024, cargo "Analista
Administrativo" (CBO a confirmar), salário contratual R$ 3.000,00, jornada
44h semanais, sindicato "Sindicato dos Empregados no Comércio", dois
dependentes para IRRF.

**Referência de rotina.** Manual, "Empregados", páginas 180-256 (dados
gerais, salário professor, guia profissionais, documentos pessoais,
lançamentos fixos, campos livres, histórico do empregado).

**Fonte normativa.** CLT (Decreto-Lei 5.452/1943), registro do empregado —
hoje via eSocial (registro eletrônico); dispositivo exato **a confirmar**.

**Situação no DataLedger.** **Não existe.** Não há modelo de empregado em
nenhum app.

**Depende de.** FOL-11 (cargo), FOL-12 (jornada/horário), FOL-13
(departamento/centro de custo/filial), FOL-14 (sindicato) — um empregado só
se cadastra por completo depois que essas quatro estruturas existem, embora
o cadastro básico (nome, CPF, data de admissão) possa nascer antes.

**Dados.** Empresa (isolamento — RC de plataforma), nome, CPF, data de
nascimento, PIS/NIS, CTPS (número/série), data de admissão, cargo, função,
departamento, centro de custo, filial, sindicato, salário contratual (tipo
mensalista/horista/comissionado/professor), jornada/horário, forma de
pagamento (banco/conta), dependentes (para IRRF e salário-família,
distintos), situação (ativo/afastado/demitido), histórico de alterações
cadastrais e contratuais por data.

**Regras.**
- CPF único por empregado dentro da empresa; formato validado (mesmo
  validador de `apps.empresas.validators`, reaproveitado).
- Data de admissão não pode ser futura além de um limite razoável nem
  anterior à fundação da empresa — limite exato **a confirmar** com o Fred.
- Alteração de dado contratual relevante (cargo, salário, jornada, sindicato)
  gera **histórico com data de vigência**, nunca sobrescreve em silêncio —
  mesma regra que o manual já implementa (botão Histórico, página 242) e que
  o DataLedger já aplica em outros cadastros (ex.: `ParametroContabilEmpresa`
  por vigência).
- Isolamento por empresa: consulta de empregado nunca atravessa empresas
  diferentes do mesmo escritório sem autorização explícita por empresa
  (AGENTS.md §11).

**Telas e documentos.** Cadastro de empregado, ficha do empregado (relatório
cadastral, classe **C**), etiqueta de CTPS. Sem norma de forma para o
cadastro em si.

**Critérios de aceite.** Cadastro completo recusa CPF duplicado na mesma
empresa; alteração de salário sem data de vigência é recusada; consulta de
empregado de uma empresa nunca retorna registro de outra.

**Não copiar / riscos.** O manual permite **excluir cadastros não
utilizados** em lote (Utilitários, página 1359) — decisão a tomar com
cautela: exclusão definitiva de empregado com histórico de folha apagaria
rastro trabalhista; o padrão do projeto é inativar, não apagar (mesmo
princípio de `Conta` com `on_delete=PROTECT`).

**Perguntas.** Quantos empregados tem a carteira típica de cliente do
escritório — dezenas ou centenas por empresa? Isso muda o desenho de
importação em lote (FOL-67).

### FOL-02 — Estagiários

**O que é.** O cadastro de quem trabalha sob contrato de estágio — vínculo
diferente do empregatício, com instituição de ensino, agente de integração,
supervisor e bolsa-auxílio em vez de salário.

**Exemplo.** Estagiário João, curso de Administração, instituição de ensino
"Universidade X", agente de integração "CIEE" (ou direto), bolsa-auxílio R$
800,00, carga horária 20h semanais.

**Referência de rotina.** Manual, "Estagiários", páginas 256-313 (dados,
estágio, instituição de ensino, agente de integração, coordenador e
supervisor de estágio, histórico).

**Fonte normativa.** Lei 11.788/2008 (Lei do Estágio) — dispositivos
específicos (carga horária máxima, recesso remunerado, ausência de vínculo
empregatício) **a confirmar**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-11, FOL-12, FOL-13 (mesma base estrutural do empregado,
com campos próprios de estágio).

**Dados.** Empresa, nome, CPF, instituição de ensino, curso, agente de
integração, coordenador/supervisor de estágio, data de início/fim do
contrato de estágio, bolsa-auxílio, carga horária, seguro contra acidentes
pessoais (exigido em lei).

**Regras.** Estagiário não recebe rubricas de encargos trabalhistas
(FGTS, férias na forma da CLT) — recebe as específicas da Lei 11.788/2008
(recesso remunerado proporcional); a distinção de regime **não pode se
confundir** com a de empregado no motor de cálculo (FOL-17).

**Telas e documentos.** Cadastro de estagiário, ficha; sem norma de forma.

**Critérios de aceite.** Cálculo de "férias"/recesso de estagiário usa a
regra de estágio, nunca a de empregado CLT, mesmo que o motor de cálculo
seja compartilhado.

**Perguntas.** O escritório atende empresa com programa de estágio ativo
hoje, com que volume?

### FOL-03 — Contribuintes individuais (autônomos)

**O que é.** O cadastro de quem presta serviço sem vínculo empregatício —
autônomo, produtor rural pessoa física — para quem a empresa paga via RPA
(Recibo de Pagamento a Autônomo) e retém INSS e, quando aplicável, IRRF.

**Exemplo.** Contribuinte Pedro, autônomo, presta serviço de consultoria
esporádico para a empresa, recebe por RPA competência a competência, sem
salário fixo nem jornada.

**Referência de rotina.** Manual, "Contribuintes", páginas 313-351.

**Fonte normativa.** Lei 8.212/1991 (custeio da Previdência Social),
contribuinte individual, art. 12, V; retenção de 11% sobre a nota/RPA
(art. 4º da Lei 10.666/2003) — dispositivos **a confirmar** por vigência.

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (cadastro relativamente independente; usa cargo/serviço
como classificação, não jornada).

**Dados.** Empresa, nome, CPF, tipo de serviço prestado, dados bancários,
NIT/PIS (para INSS), dependentes (se IRRF incidir).

**Regras.** Contribuinte individual **não** é empregado: nunca gera rubrica
de FGTS, férias ou 13º pela regra CLT — o "13º" e "férias" que a folha
eventualmente lhe atribui (caso de RPA de sócio ou situação equiparada) é
regra **distinta**, a confirmar caso a caso.

**Telas e documentos.** Cadastro; ficha do contribuinte; recibo de RPA
(FOL-47), classe **F**.

**Perguntas.** A carteira do escritório tem produtor rural pessoa física
entre os clientes com folha? O manual reserva rotinas específicas
(aquisição/comercialização de produção rural, páginas 409-415) que só fazem
sentido se houver esse perfil de cliente.

### FOL-04 — Rubricas (proventos e descontos, incidências)

**O que é.** O vocabulário fechado de tudo o que pode compor um holerite:
cada rubrica é um provento (soma) ou desconto (subtrai), com uma forma de
cálculo (automática ou lançada pelo usuário), uma unidade (valor, horas,
dias, percentual) e um conjunto de **incidências** — sobre que outras
rubricas ou bases ela entra (aviso prévio, 13º/férias, afastamentos) e o que
incide sobre ela (INSS, FGTS, IRRF). É a peça central de todo o domínio:
como o modelo `Conta` é o vocabulário da Contabilidade, a rubrica é o
vocabulário da Folha.

**Exemplo.** Rubrica "Salário Base" (provento, unidade valor, base de
cálculo = salário contratual, incide INSS/FGTS/IRRF/base de férias e 13º).
Rubrica "Horas Extras 50%" (provento, unidade horas, taxa 1,5 × valor da
hora normal, soma na base de aviso prévio e faz média para férias/13º
conforme o sindicato). Rubrica "Vale-Transporte" (desconto, até 6% do
salário base, não incide INSS/IRRF por ser desconto de benefício).

**Referência de rotina.** Manual, "Rubricas", páginas 351-373 (tipo,
cálculo, unidade, base de cálculo, classificação, taxa; quadros Adicional e
Médias — aviso prévio, 13º/férias, afastamentos; quadro Relatórios — ficha
financeira, comprovante de rendimentos/DIRF, RAIS; código eSocial).

**Fonte normativa.** Incidência de INSS sobre rubricas — Lei 8.212/1991,
art. 28, e o Regulamento da Previdência Social (Decreto 3.048/1999), que
lista o que compõe e o que **não** compõe o salário de contribuição
(parcelas do art. 28, §9º); incidência de FGTS — Lei 8.036/1990, art. 15;
incidência de IRRF — Lei 7.713/1988 e IN RFB vigente. Todos **a confirmar**
por rubrica, um a um — é a parte mais sensível de todo o módulo, porque
classificar uma rubrica errado (ex.: tratar ajuda de custo eventual como
salário) tem efeito cascata em INSS, FGTS, IRRF, férias e 13º ao mesmo
tempo.

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (é a base, como CTB-01 é a base da Contabilidade).

**Dados.** Empresa (ou rubrica compartilhada por template do escritório —
decisão de produto a confirmar), código, nome, tipo (provento/desconto),
forma de cálculo, unidade, base de cálculo, classificação, taxa, incidências
(lista de "soma em": aviso prévio, 13º/férias, afastamentos; lista de
"média para": aviso prévio, 13º, férias, afastamentos, saldo de salário),
vigência (início/fim de uso), código eSocial correspondente, indicador de
uso em relatório (ficha financeira, comprovante de rendimentos).

**Regras.**
- Toda rubrica declara, de forma explícita e não ambígua, cada incidência —
  nunca incidência implícita deduzida do nome. É a regra de engenharia que
  evita o erro mais caro do domínio.
- Rubrica usada em cálculo já efetivado **não é apagada nem tem sua
  incidência alterada retroativamente**; mudança de regra gera nova
  vigência, preservando o cálculo histórico reproduzível (AGENTS.md §10,
  mesmo princípio de `DE-010` para vigência de parâmetro legal).
- Cálculo monetário de rubrica usa `Decimal`, nunca ponto flutuante binário
  (AGENTS.md §10); a política de arredondamento de folha é **truncamento na
  segunda casa**, conforme `DE-010`, salvo indicação contrária confirmada em
  fonte oficial para o caso específico.

**Telas e documentos.** Cadastro de rubrica; relatórios "Rubricas (Proventos
e Descontos)" na consulta de arquivos (classe **C**).

**Critérios de aceite.** Toda rubrica tem pelo menos um tipo de incidência
declarado antes de poder ser usada em cálculo; teste de referência com
rubrica de hora extra que soma corretamente em 13º e não soma em FGTS
indevidamente (exemplo negativo, verificável).

**Não copiar / riscos.** O manual permite editar/excluir as "rubricas
básicas" do sistema apenas com orientação do suporte do fornecedor (página
351) — sinal de que a mutação de rubrica em uso é perigosa por natureza; o
DataLedger deve tornar essa cautela **regra do sistema**, não recomendação
em texto de ajuda.

**Perguntas.** O escritório usa um conjunto de rubricas **padrão** comum a
todos os clientes, ou cada empresa tem seu próprio plano de rubricas
(equivalente à pergunta já feita para plano de contas referencial na
Contabilidade)?

### FOL-05 — Bases de cálculo

**O que é.** Uma base de cálculo é a fórmula ou soma de rubricas sobre a qual
outra rubrica é calculada (ex.: "Salário Contratual", "Soma de rubricas X +
Y", "Valor Hora-Aula", "Fórmula").

**Exemplo.** Base "Salário + Adicional de Insalubridade", usada para
calcular o desconto de INSS sobre o total, não só sobre o salário-base.

**Referência de rotina.** Manual, "Bases de Cálculo", página 373 (tipos:
soma de rubricas, salário contratual, salário grade professor, fórmula).

**Fonte normativa.** Decorre da definição de salário de contribuição/base de
cálculo de cada tributo — mesma fonte de FOL-04, **a confirmar** por caso.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-04 (as rubricas que a base soma).

**Dados.** Empresa, código, nome, tipo (soma de rubricas / salário
contratual / fórmula), lista de rubricas somadas (quando aplicável),
expressão de fórmula (quando aplicável).

**Regras.** Base de cálculo por fórmula é auditável — a expressão fica
registrada e reproduzível na memória de cálculo, nunca "caixa preta"
(AGENTS.md §10).

**Telas e documentos.** Cadastro de base de cálculo; classe **C**.

**Perguntas.** O escritório usa bases por fórmula livre hoje, ou só soma de
rubricas simples? Determina se a Onda 1 precisa de um mini-interpretador de
fórmula desde o início ou se pode nascer só com soma de rubricas.

### FOL-06 — Tabela de IRRF (progressiva, PLR, residentes no exterior)

**O que é.** A tabela de faixas e alíquotas do Imposto de Renda Retido na
Fonte sobre a folha, com desconto simplificado ou por dependente, e as
tabelas irmãs de IRRF sobre PLR (progressiva própria, sem dedução por
dependente) e sobre rendimentos de residentes no exterior. Cada tabela tem
**vigência por competência** — a cada mudança de faixa, uma nova versão
entra, sem apagar a anterior.

**Exemplo (mecânica, sem valor de tabela).** Empregada Maria, base de
cálculo do IRRF do mês (salário + horas extras − INSS − dependentes, "regra
exata a confirmar") = R$ X. O sistema localiza a faixa em que X se enquadra
na tabela vigente na competência do cálculo, aplica a alíquota da faixa e
subtrai a parcela a deduzir da própria faixa — **alíquota e parcela a
deduzir são as da tabela vigente, a confirmar em fonte oficial**, nunca
valor fixado neste documento.

**Referência de rotina.** Manual, "Tabelas — IRRF", páginas 375-379
(Progressiva, Participação de Lucros, Rendimentos de Residentes no
Exterior); atualização automática de tabelas, páginas 374-375.

**Fonte normativa.** Lei 9.250/1995 (tabela progressiva do IRRF) e
atualizações por lei/IN a cada mudança de faixa; IRRF sobre PLR — Lei
12.832/2013, art. 3º. **Vigência exata a confirmar em cada competência.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (tabela de referência, usada por FOL-17, FOL-31, FOL-46,
FOL-47).

**Dados.** Competência de vigência, faixas (limite superior, alíquota,
parcela a deduzir), valor de dedução por dependente, valor mínimo para
retenção. Tabela **imutável após uso em cálculo efetivado** — nova
competência é nova versão, nunca edição da anterior.

**Regras.**
- Cálculo de IRRF de uma competência sempre usa a tabela **vigente naquela
  competência**, mesmo que recalculado meses depois — reprodutibilidade
  histórica (AGENTS.md §10).
- Arredondamento: **truncamento na segunda casa**, conforme `DE-010` — a
  confirmar se o Manual de Orientação do eSocial (fonte de `DE-010`) cobre
  especificamente o IRRF ou só INSS/FGTS; se não cobrir, a política do IRRF
  precisa de fonte própria antes de codificar.

**Telas e documentos.** Cadastro de tabela por vigência; classe **A**
(segue leiaute oficial de tabela, sem personalização visual relevante).

**Critérios de aceite.** Cálculo de referência com tabela sintética (não a
oficial) prova a mecânica de faixa + parcela a deduzir; troca de vigência
não altera cálculo de competência anterior já efetivada.

**Não copiar / riscos.** O botão "Atualizar" busca a tabela automaticamente
de um serviço do fornecedor (SGSUN) — o DataLedger não tem (e não deveria
presumir) acesso a um serviço equivalente; atualização de tabela é, por ora,
manual e revisada por humano, com fonte citada.

### FOL-07 — Tabela de INSS, salário-família e RAT

**O que é.** A tabela de faixas e alíquotas do INSS descontado do
empregado, os valores de salário-família por faixa de remuneração, e os
percentuais de RAT (Risco Ambiental do Trabalho — GILRAT) por atividade,
antes do ajuste pelo FAP (FOL-08).

**Exemplo (mecânica, sem valor de tabela).** Sobre a base de cálculo do INSS
do mês (soma das rubricas com incidência INSS, "regra exata a confirmar"),
o sistema aplica o cálculo progressivo por faixas da tabela vigente — cada
faixa da remuneração paga a alíquota da sua própria faixa, resultado somado
— **alíquotas e faixas são as da tabela vigente, a confirmar em fonte
oficial**.

**Referência de rotina.** Manual, "Tabelas — INSS", páginas 379-381 (guias
INSS, Salário Família, Acréscimo RAT).

**Fonte normativa.** Lei 8.212/1991, arts. 20 e 22 (alíquotas de empregado e
de empresa) e Lei 8.213/1991 (salário-família, art. 65 e seguintes); RAT —
Decreto 3.048/1999, Anexo V. **Todas a confirmar por vigência.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (tabela de referência, mesma posição de FOL-06).

**Dados.** Competência de vigência, faixas de INSS (limite, alíquota),
valor mínimo de recolhimento, faixas de salário-família (limite de
remuneração, valor do benefício), percentuais de RAT (1%, 2% ou 3% conforme
grau de risco da atividade — **a confirmar**).

**Regras.** Mesma regra de vigência e imutabilidade histórica de FOL-06;
mesma dúvida de arredondamento (truncamento por `DE-010`, fonte a confirmar
para o caso específico do desconto do empregado versus a contribuição
patronal).

**Telas e documentos.** Cadastro de tabela por vigência; classe **A**.

**Perguntas.** O cálculo previdenciário do escritório, hoje, segue a
apuração mensal simples ou já opera pela lógica da DCTFWeb (compensação,
FOL-19)? O manual trata isso como opção de parâmetro por competência.

### FOL-08 — FAP (Fator Acidentário de Prevenção)

**O que é.** Um multiplicador (entre 0,5 e 2,0, tipicamente) que ajusta o
percentual de RAT da empresa conforme seu histórico de acidentalidade —
empresa com mais acidentes paga RAT maior; com menos, RAT menor.

**Exemplo (mecânica).** RAT da atividade = 2% ("a confirmar"); FAP da
empresa = 1,3000 ("a confirmar, é dado publicado pelo INSS por CNPJ/ano");
RAT ajustado = 2% × 1,3000 = 2,6%, usado na apuração da contribuição
patronal (FOL-19).

**Referência de rotina.** Manual, "FAP", páginas 381-382 (inclui
possibilidade de processo administrativo ou judicial que modifica o fator).

**Fonte normativa.** Lei 10.666/2003, art. 10, e Decreto 6.957/2009. Fonte
do valor do FAP por empresa: divulgação anual do INSS/Receita Federal.
**A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-07 (ajusta o RAT).

**Dados.** Competência de vigência, fator (decimal com 4 casas, conforme
padrão do FAP), indicador de processo administrativo/judicial que modifica o
fator, vínculo ao processo (FOL-68).

**Regras.** Fator publicado anualmente — mudança de vigência não altera
apuração de competência anterior já efetivada.

**Telas e documentos.** Cadastro de FAP por empresa/vigência; classe **A**.

**Perguntas.** O escritório importa o FAP publicado pelo INSS manualmente
hoje, ou tem acesso a algum serviço de consulta? Determina se FOL-67
(importação) precisa cobrir este dado desde já.

### FOL-09 — Salário mínimo federal e estadual

**O que é.** O valor do salário mínimo nacional, e — nos estados que
adotam — o piso estadual por categoria profissional, ambos usados como
referência em várias regras (salário mínimo por hora/dia, limite mínimo de
algumas rubricas, cálculo de benefícios).

**Exemplo.** Salário mínimo federal vigente na competência ("valor da
tabela oficial, a confirmar"); categoria estadual "Trabalhadores no
Comércio", piso estadual vigente ("a confirmar").

**Referência de rotina.** Manual, "Salário-Mínimo", páginas 382-385
(Federal; Estadual — categorias e tabela por UF e vigência).

**Fonte normativa.** Decreto federal de reajuste anual do salário mínimo;
leis estaduais de piso salarial (onde existirem — nem todo estado tem lei
própria). **A confirmar por estado e vigência.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (tabela de referência).

**Dados.** Competência de vigência, valor (federal); UF, categoria,
competência de vigência, valor (estadual).

**Regras.** Mesma regra de vigência e imutabilidade histórica das demais
tabelas.

**Telas e documentos.** Cadastro por vigência; classe **A**.

**Perguntas.** Algum cliente da carteira está em estado com piso salarial
próprio (ex.: SP, RJ, PR)? Sem isso, a tabela estadual pode ficar fora da
Onda 1.

### FOL-10 — Contribuição sindical patronal e índices de correção de médias

**O que é.** Duas tabelas auxiliares: a de cálculo da contribuição sindical
**patronal** (paga pela empresa ao sindicato patronal, por faixa de capital
social ou de receita/número de alunos), e a de índices para corrigir médias
salariais (ex.: média de comissão) ao longo do tempo.

**Referência de rotina.** Manual, páginas 385-387 (Contribuição Sindical
Patronal — atividade de ensino, receita bruta, vigência por ano; Índices
para Correção de Médias — acumulado ou mensal, vinculado ao sindicato).

**Fonte normativa.** Contribuição sindical patronal — CLT, arts. 578 a 610,
**com o status de compulsoriedade alterado pela Lei 13.467/2017** (ver
FOL-78 na seção "a confirmar", que trata da mesma mudança para a
contribuição do empregado). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-16 (vinculada ao sindicato patronal).

**Dados.** Nome da tabela, indicador de atividade de ensino, indicador de
uso de receita bruta, faixas por vigência anual, valores; índice de
correção — competência, valor (acumulado/mensal).

**Telas e documentos.** Cadastro por vigência; classe **A**.

### FOL-11 — Cargos, funções e CBO

**O que é.** O cadastro de cargos (o "título" contratual do empregado, com
descrição de atividades e exposição a fatores de risco para fins de
PPP/CAT) e de funções (mais granular, ligada ao CBO — Classificação
Brasileira de Ocupações), que alimentam o eSocial e o PPP.

**Exemplo.** Cargo "Analista Administrativo Pleno", CBO 4110-05 ("a
confirmar código exato"), sem exposição relevante a fatores de risco.

**Referência de rotina.** Manual, "Cargos", páginas 593-605 (descrição das
atividades, exposição a fatores de risco I e II, histórico, eSocial);
"Funções", páginas 607-616 (ligada ao CBO).

**Fonte normativa.** CBO — Classificação Brasileira de Ocupações,
Ministério do Trabalho; exigência de informar fatores de risco — NR-9 e a
tabela de agentes nocivos da Previdência (para PPP/aposentadoria especial).
**A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (estrutura, junto de FOL-12/FOL-13).

**Dados.** Empresa (ou escritório, se compartilhado), código, nome,
descrição de atividades, CBO, indicadores de exposição a fatores de risco,
histórico de alterações por data.

**Regras.** Cargo com empregado vinculado não é apagado (mesmo princípio de
`Conta`/`on_delete=PROTECT`); alteração de CBO gera histórico.

**Telas e documentos.** Cadastro de cargo e de função; classe **C**.

**Perguntas.** Algum cliente da carteira tem atividade insalubre/perigosa
que exija PPP de fato hoje?

### FOL-12 — Horários e jornadas

**O que é.** O cadastro dos horários de trabalho (entrada, saída, intervalo)
e das jornadas (o "pacote" de horários que um empregado segue, incluindo
escalas), base tanto do cálculo de horas extras na folha quanto do módulo de
Ponto.

**Exemplo.** Horário "Comercial", 08h-12h/13h30-17h30, 44h semanais,
intervalo de 1h30. Empregada Maria segue essa jornada de segunda a
sexta-feira.

**Referência de rotina.** Manual Folha, "Horários", páginas 616-625, e
"Jornadas", páginas 625-628; Manual Ponto, "Cadastro Horários" (guias
Horários, Marcações, Limites, Cartão Ponto), páginas 34-37.

**Fonte normativa.** CLT, arts. 58 a 65 (duração do trabalho); intervalo
intrajornada, art. 71. **A confirmar** dispositivo e eventual convenção
coletiva que altere limites (FOL-15).

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (estrutura, compartilhada entre Folha e Ponto — ver
FOL-54 a FOL-58).

**Dados.** Empresa, código, nome, horários de entrada/saída/intervalo por
dia da semana, tolerância de marcação, carga horária semanal/mensal.

**Regras.** Jornada com empregado vinculado não é apagada; alteração gera
histórico com vigência — relevante para reapuração retroativa de ponto
(FOL-55).

**Telas e documentos.** Cadastro de horário e de jornada; classe **C**.

### FOL-13 — Filiais, departamentos e centros de custo

**O que é.** A estrutura organizacional interna da empresa cliente, usada
para segmentar folha, ponto e relatórios: filial (estabelecimento),
departamento e centro de custo.

**Referência de rotina.** Manual, "Filiais", páginas 416-423 (inclui FAP por
filial e centralização de eventos do eSocial); "Centros de Custos", páginas
423-426; "Departamentos", páginas 426-428.

**Fonte normativa.** Não há leiaute oficial de estrutura organizacional
interna — decisão do escritório/cliente, como o plano de contas da
Contabilidade.

**Situação no DataLedger.** **Não existe.** Observação: `apps/empresas` já
tem o conceito de estabelecimento em outro contexto (escrita fiscal); a
modelagem de "filial" da Folha precisa **reaproveitar** essa estrutura, não
duplicá-la — mesma cautela de FOL-58 quanto a não criar dois vocabulários
para a mesma ideia de "onde a empresa opera".

**Depende de.** — (estrutura).

**Dados.** Empresa, filial (vínculo ao estabelecimento de `apps.empresas`,
a confirmar viabilidade), departamento, centro de custo — cada um com
código, nome, e no caso de filial, FAP próprio e indicador de centralização
de eventos do eSocial (uma filial pode ser "centralizadora" das obrigações
de todas as outras).

**Regras.** Isolamento por empresa; filial/departamento/centro de custo com
empregado vinculado não é apagado.

**Telas e documentos.** Cadastros; classe **C**.

**Perguntas.** A modelagem de "filial" da Folha deve reaproveitar
`Estabelecimento` de `apps.empresas`, ou são conceitos distintos o
suficiente para exigir modelo próprio? Decisão de arquitetura, não deste
plano — registrar para o `arquiteto-senior`.

### FOL-14 — Sindicatos dos empregados (motor de regras)

**O que é.** O cadastro mais complexo de todo o módulo: para cada sindicato,
um **conjunto de regras condicionais** que determinam como a empresa calcula
férias, 13º, aviso prévio, garantia semestral, licença-prêmio, comissionado,
médias, estabilidade, indenização especial e PLR para os empregados
vinculados a ele. Cada regra é montada como uma condição (campo, operador,
valor) que produz um resultado (dias, valor, percentual), combinável com "E"
/"OU" e por faixa salarial, por CBO, por idade, por tempo de casa e por
motivo de rescisão.

**Exemplo.** Sindicato "X", convenção vigente define: 30 dias de aviso
prévio até 1 ano de casa, mais 3 dias por ano trabalhado (Lei 12.506/2011);
adicional de 1/3 sobre férias no padrão constitucional (sem regra especial);
PLR paga em duas parcelas, proporcional a meses trabalhados na vigência,
apenas para quem trabalhou 15 dias ou mais no mês.

**Referência de rotina.** Manual, "Sindicatos dos Empregados", páginas
429-591 — a seção mais extensa do manual inteiro. Achado relevante para
quem for desenhar o motor: a engine de condições (campo × regra × valor ×
condição E/OU/Resultado) se repete, quase idêntica, em pelo menos sete
subtelas diferentes (férias, aviso prévio, aviso prévio especial, PLR,
indenização especial, alteração salarial por convenção) — é candidata forte
a um **componente único de "regra condicional por sindicato"**, reutilizado,
em vez de sete implementações paralelas. Subseções relevantes: Guia Cálculo
> Férias (páginas 449-465), 13º Salário (465-466), Aviso Prévio
(466-480, com subguia específica "Lei 12.506/2011", página 478-480),
Garantia Semestral (480-482), Licença Prêmio (482-484), Comissionado
(484-488), Médias (488-548), Estabilidade (548-555), Indenização Especial
(555-561), PLR (561-568), Piso Salarial (568-570), Convenção Coletiva
(570-591, tratada em FOL-15).

**Fonte normativa.** Férias — CLT, arts. 129 a 153; 13º — Lei 4.090/1962 e
Lei 4.749/1964; aviso prévio — CLT, arts. 487 a 491, e Lei 12.506/2011
(acréscimo de 3 dias por ano de serviço, até 60 dias adicionais, total
máximo 90); PLR — Lei 10.101/2000; estabilidade — várias fontes conforme o
motivo (gestante: ADCT art. 10, II, "b"; acidente de trabalho: Lei
8.213/1991, art. 118; CIPA: CLT art. 165; entre outras). **Todas a
confirmar**, dispositivo a dispositivo, antes de qualquer regra virar
código — é o item de maior risco normativo de todo o plano, porque a lógica
condicional do manual mistura, na mesma tela, regra de lei (aviso prévio
proporcional) com regra de convenção coletiva do sindicato específico
(percentuais e prazos que **só valem para aquele sindicato**, nunca
generalizáveis).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-04 (rubricas afetadas pelas regras), FOL-06/07/09
(tabelas usadas nas condições e resultados).

**Dados.** Sindicato (nome, CNPJ, endereço, código de entidade na Caixa),
conjunto de regras por área (férias, 13º, aviso prévio, PLR, estabilidade,
indenização especial, comissionado, médias) — cada regra com campo testado,
operador, valor/faixa, condição de combinação, resultado (dias, valor,
percentual, com base de cálculo e limite quando aplicável) e vigência; piso
salarial por categoria e vigência, com competência de reajuste **e**
competência retroativa (ver FOL-15); vínculo a quais empresas usam o
sindicato.

**Regras.**
- Toda regra do motor é **vigente por competência**: mudar uma regra não
  altera cálculo já efetivado em competência anterior (mesmo princípio de
  DE-010 para vigência de parâmetro legal).
- Regra de convenção coletiva **nunca vira lei genérica do sistema** — fica
  amarrada ao sindicato e à vigência específicos; nada aqui é reaproveitável
  como regra "padrão" do DataLedger sem confirmação de que é regra legal e
  não cláusula de uma convenção particular.
- Exclusão ou alteração de sindicato vinculado a alteração salarial ativa é
  recusada, com mensagem (mesmo padrão do manual, página 571) — evita
  quebrar um cálculo retroativo em andamento.

**Telas e documentos.** Cadastro de sindicato (o mais extenso do módulo);
classe **C** internamente, mas seus **resultados** (dias de aviso, valor de
PLR) aparecem em documentos de classe **F** (FOL-30, FOL-31, FOL-47/FOL-49).

**Critérios de aceite.** Regra de aviso prévio por Lei 12.506/2011 calculada
corretamente para 3 tempos de casa de referência sintéticos (ex.: 6 meses =
30 dias; 2 anos completos = 30 + 6 = 36 dias; 20 anos = 30 + 60 = 90 dias,
"mecânica a confirmar contra o texto da lei e eventual convenção que
substitua a proporcionalidade").

**Não copiar / riscos.** A complexidade do motor é real e legítima — não é
excesso de engenharia do fornecedor, é reflexo de a legislação trabalhista
brasileira delegar boa parte da regra à negociação coletiva. O risco a
evitar é o oposto: **simplificar demais** e tratar cláusula de convenção
como se fosse lei, ou vice-versa — a distinção precisa estar explícita em
cada regra cadastrada.

**Perguntas.** Quantos sindicatos distintos aparecem na carteira de clientes
do escritório hoje? Um motor de regras condicionais completo (Onda 1) só se
justifica se houver diversidade real de convenções; se a carteira for
homogênea, uma versão inicial mais simples (parâmetros fixos por empresa,
sem o motor condicional completo) pode bastar para a primeira entrega.

### FOL-15 — Convenção coletiva e alteração salarial retroativa

**O que é.** O registro formal de cada convenção coletiva de trabalho (CCT)
— vigência, percentual de reajuste, forma de aplicação — e, separadamente,
a capacidade de aplicar um reajuste **retroativo**: a convenção é assinada
meses depois da data-base, e o sistema precisa recalcular e pagar a
diferença dos meses já processados, com controle de como essa diferença
chega ao empregado (parcelada, na folha complementar do mês, de uma vez).

**Exemplo.** Convenção coletiva assinada em 15/06/2026, com vigência
retroativa a 01/05/2026, reajuste fixo de 5% ("percentual sintético, sem
relação com convenção real"). Empregada Maria, salário R$ 3.000,00 em
maio, passa a R$ 3.150,00 a partir de maio; a diferença de maio e junho já
pagos (R$ 150,00 × 2 meses, antes de qualquer incidência) é calculada e paga
como **diferença salarial retroativa**, rastreável até a convenção que a
originou — nunca como reedição do holerite já pago.

**Referência de rotina.** Manual, "Convenção Coletiva", páginas 570-591
(dados da convenção, alteração retroativa — forma de alteração:
complementar mês a mês, folha mensal do mês do aumento, folha complementar
do mês do aumento, ou conforme parcelamento; dados do reajuste — fixo,
conforme cargo, variável; termo aditivo).

**Fonte normativa.** CLT, art. 611 (convenção e acordo coletivo); eficácia
temporal da norma coletiva — **a confirmar**, inclusive à luz da Lei
13.467/2017 (ultratividade de convenção coletiva).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-14 (sindicato ao qual a convenção pertence).

**Dados.** Sindicato, descrição, tipo de acordo, número de processo, data de
registro, vigência (início/fim), tipo de percentual de reajuste
(fixo/conforme cargo/variável/misto), percentual, termo aditivo (quando
houver), documento anexado; para a alteração retroativa — data da alteração,
competência retroativa, forma de alteração, indicador de gerar folha
complementar específica.

**Regras.**
- **Folha efetivada é imutável** (AGENTS.md §10): a diferença retroativa
  nunca reabre nem sobrescreve a folha já paga do mês de origem — ela gera
  um **lançamento de diferença**, rastreável até a convenção/termo aditivo
  que a originou, no mesmo espírito da correção por diferença que o
  DataLedger já aplica em outros domínios (ex.: estorno em Contabilidade).
- Convenção com o mesmo número de processo ou mesmo período de vigência do
  mesmo sindicato é recusada como duplicidade (mesmo padrão do manual,
  página 572).

**Telas e documentos.** Cadastro de convenção coletiva; relatório "Diferenças
Referentes a Alteração Retroativa de Piso Salarial" (classe **C**), FOL-60.

**Critérios de aceite.** Diferença retroativa calculada sobre competência já
efetivada nunca altera o holerite original; o total da diferença bate com
(salário novo − salário antigo) × meses afetados, antes de incidências —
caso de referência sintético testável.

**Perguntas.** Qual é a forma de alteração retroativa que o escritório usa
na prática — complementar mês a mês, ou tudo de uma vez na folha do mês do
aumento? Determina a prioridade dentro do item.

### FOL-16 — Sindicatos patronais

**O que é.** O cadastro dos sindicatos patronais (representam a empresa, não
o empregado), usado para calcular a contribuição sindical patronal (FOL-10).

**Referência de rotina.** Manual, "Sindicatos Patronais", páginas 591-593.

**Fonte normativa.** Mesma de FOL-10.

**Situação no DataLedger.** **Não existe.**

**Depende de.** — (cadastro simples, alimenta FOL-10).

**Dados.** CNPJ, nome, tipo de entidade, endereço, código de entidade na
Caixa Econômica Federal, tabela de contribuição sindical patronal vinculada.

**Telas e documentos.** Cadastro; classe **C**.

### FOL-17 — Cálculo mensal da folha e tipos de folha

**O que é.** O processo central do módulo: pega todos os lançamentos do mês
(salário, horas, faltas, benefícios) e todas as regras (rubricas, tabelas,
sindicato) e produz o resultado — quanto cada empregado recebe líquido,
quanto a empresa recolhe de encargos. O sistema de referência distingue
vários **tipos de folha** na mesma competência: Mensal, Adiantamento, 13º
Adiantamento, 13º Integral, Complementar (para lançamentos posteriores ao
fechamento original).

**Exemplo — a mecânica pedida pelo Fred, com números sintéticos.** Empregada
Maria, salário contratual R$ 3.000,00, jornada de 220h/mês ("divisor
sintético, a confirmar se o divisor correto é 220, 200 ou outro conforme a
jornada e a convenção"), 10 horas extras no mês a 50% de adicional.

1. Valor da hora normal = R$ 3.000,00 ÷ 220 = R$ 13,6363... (arredondamento
   conforme regra a confirmar).
2. Valor das horas extras = 10h × R$ 13,6363... × 1,50 = R$ 204,54
   ("truncamento na 2ª casa, conforme DE-010, a confirmar para este caso
   específico").
3. DSR sobre horas extras (Lei 605/1949 e Súmula 172 do TST, **mecânica**,
   não valor): (total de horas extras do mês ÷ dias úteis do mês) × número
   de domingos e feriados do mês. Com 22 dias úteis e 5 domingos/feriados no
   mês sintético: (R$ 204,54 ÷ 22) × 5 = R$ 46,49 (arredondamento a
   confirmar).
4. Base de INSS = R$ 3.000,00 + R$ 204,54 + R$ 46,49 = R$ 3.251,03. INSS
   descontado = **valor calculado pela tabela vigente na competência,
   aplicando as faixas progressivas — alíquotas e faixas a confirmar em
   fonte oficial (FOL-07); não afirmado aqui**.
5. Base de IRRF = base de INSS − INSS descontado − dedução por dependente
   ("fórmula exata a confirmar", 2 dependentes no exemplo). IRRF descontado
   = **valor calculado pela tabela vigente, faixa e parcela a deduzir a
   confirmar (FOL-06); não afirmado aqui**.
6. Líquido = R$ 3.251,03 − INSS − IRRF − outros descontos (ex.: vale-
   transporte, consignado) — todos "a confirmar em valor", com a mecânica de
   subtração explícita e rastreável na memória de cálculo.

**Referência de rotina.** Manual, "Cálculo", páginas 691-707 (tipo de folha,
complemento, adiantamento, 13º adiantamento/integral, seleção de empresas,
data de pagamento por sindicato).

**Fonte normativa.** CLT, arts. 457-467 (salário e formas de pagamento); Lei
605/1949 e Súmula 172 do TST (DSR sobre horas extras); Lei 8.212/1991
(INSS); Lei 7.713/1988 (IRRF). **Todas a confirmar** por dispositivo e
vigência — este item é o ponto de maior exposição normativa de todo o
plano, e nenhum valor dele deve virar constante de código sem validação
profissional (AGENTS.md §10).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01/02/03, FOL-04 a FOL-15 (toda a fundação).

**Dados.** Competência, tipo de folha, empresa(s) selecionada(s) — **cada
processamento de múltiplas empresas exige autorização conferida
empresa por empresa no servidor**, nunca em lote sem checagem individual
(mesma regra que o mapa funcional já registrou como "o que não copiar" —
AGENTS.md §11); resultado por empregado (itens de holerite, com valor e
rubrica), memória de cálculo.

**Regras.**
- Débitos e créditos do lançamento contábil derivado (FOL-39) fecham em
  zero — mesma invariante da Contabilidade.
- Cálculo é **reprodutível**: mesma competência, mesmos dados, mesmo
  resultado — a memória de cálculo registra rubrica, base, alíquota/tabela
  usada e resultado, rastreável (AGENTS.md §10).
- Recálculo de folha **já efetivada** não sobrescreve em silêncio: gera
  diferença rastreável, com motivo (mesmo princípio de FOL-15 e FOL-24).
- Arredondamento: truncamento na 2ª casa por regra (`DE-010`), a confirmar
  se aplicável a **todas** as parcelas do cálculo mensal ou só a algumas.

**Telas e documentos.** Tela de cálculo; nenhum documento impresso próprio
(gera os de FOL-21/22/23); nível de risco 1 (AGENTS.md §3.1) — é dinheiro do
cliente, exige plano completo, testes de sucesso/erro/limite e auditoria
independente quando for implementado.

**Critérios de aceite.** Caso de referência sintético completo (salário +
horas extras + DSR + INSS + IRRF, com tabelas de teste, não oficiais)
reproduz a mecânica acima; recálculo de competência fechada é recusado sem
procedimento explícito.

**Não copiar / riscos.** O manual permite excluir cálculo já efetuado
diretamente (página 695) — o DataLedger **não copia** essa operação: folha
efetivada é imutável; a correção é sempre por diferença rastreável.

**Perguntas.** Qual é o divisor de hora usado pelas convenções da carteira
do escritório — 220h é universal ou varia por sindicato? Determina se
FOL-14 precisa carregar esse parâmetro por sindicato desde a Onda 1.

### FOL-18 — Adiantamento salarial e do 13º

**O que é.** O pagamento antecipado de parte do salário do mês (quinzena) ou
da primeira parcela do 13º, processado como um tipo de folha próprio,
compensado no fechamento do mês.

**Referência de rotina.** Manual, páginas 692-693 (Adiantamento salarial
conforme percentual do empregado; 13º Adiantamento, diferença de
adiantamento, avos de direito).

**Fonte normativa.** Adiantamento quinzenal — prática do mercado, sem
obrigatoriedade legal geral (a confirmar exceção por convenção); 1ª parcela
do 13º — Lei 4.749/1964, art. 2º (paga entre fevereiro e novembro).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17.

**Dados.** Competência, tipo (adiantamento salarial / 13º adiantamento),
percentual ou valor, empregados selecionados.

**Regras.** Valor do adiantamento é **descontado** na folha mensal/13º
integral do mesmo período — nunca duplicado nem perdido; rastreável na
memória de cálculo do fechamento.

**Telas e documentos.** Tela de cálculo (parte de FOL-17); recibo próprio
opcional.

### FOL-19 — Apuração previdenciária

**O que é.** O fechamento mensal do que a empresa deve de INSS — soma o
desconto dos empregados com a contribuição patronal, aplica compensações
(salário-família, salário-maternidade, retenções sofridas, saldo de
DCOMP) e chega ao valor líquido a recolher.

**Referência de rotina.** Manual, "Apuração Previdenciária", páginas
705-707.

**Fonte normativa.** Lei 8.212/1991; compensação de salário-família e
salário-maternidade — art. 68 e correlatos; DCTFWeb, IN RFB vigente para o
procedimento de apuração e declaração. **A confirmar** — este item é
"apuração" (cálculo), distinto de "declaração/transmissão" (FOL-80).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-07, FOL-08.

**Dados.** Competência, tipo de folha apurado, valores de compensação
(DCOMP, salário-família, salário-maternidade, retenções), saldo a recolher.

**Regras.** Apuração de uma competência não se altera silenciosamente depois
de declarada — correção segue procedimento próprio (retificação),
rastreável.

**Telas e documentos.** Tela de apuração; guia GPS (FOL-63), classe **A**.

**Perguntas.** O escritório apura o INSS pela lógica clássica (GPS mensal
simples) ou já pela DCTFWeb com compensação cruzada? Isso muda a prioridade
relativa deste item frente à Onda 3.

### FOL-20 — Lançamentos (por empregado, rubrica, grupo, automáticos)

**O que é.** A forma de alimentar o cálculo mensal com valores variáveis do
mês: horas extras, faltas, comissões, descontos avulsos — lançados um a um
por empregado, em lote por rubrica (a mesma rubrica para vários empregados),
em grupo (várias rubricas para um filtro de empregados), ou gerados
automaticamente por outra regra (ex.: rubrica fixa recorrente).

**Referência de rotina.** Manual, "Lançamentos", páginas 822-859 (por
empregado, por rubrica, em grupo, automáticos, por serviço, consulta).

**Fonte normativa.** Não há norma de leiaute — é mecanismo de captura de
dado variável do próprio escritório.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01/02/03, FOL-04.

**Dados.** Empresa, empregado, rubrica, competência, quantidade/valor,
origem do lançamento (manual, automático, importado).

**Regras.** Lançamento em competência já fechada é recusado sem
procedimento explícito de reabertura (AGENTS.md §10, mesmo princípio de
período fechado na Contabilidade); repetição do mesmo lançamento
(reimportação, duplo clique) não duplica silenciosamente — idempotência.

**Telas e documentos.** Telas de lançamento; consulta de lançamentos, classe
**C**.

**Critérios de aceite.** Lançamento repetido com a mesma chave não gera
segunda rubrica no holerite; lançamento em competência fechada é recusado
com mensagem clara.

### FOL-21 — Holerite (recibo de pagamento)

**O que é.** O documento que o empregado recebe todo mês, com proventos,
descontos e líquido — a peça mais visível de todo o módulo.

**Exemplo.** Holerite de Maria, competência do exemplo de FOL-17: Salário
Base R$ 3.000,00, Horas Extras 50% R$ 204,54, DSR sobre extras R$ 46,49,
INSS "valor da tabela, a confirmar", IRRF "valor da tabela, a confirmar",
Líquido "resultado da subtração, a confirmar em valor final".

**Referência de rotina.** Manual, "Recibos — Folha", páginas 1148-1152.

**Fonte normativa.** CLT, art. 464, parágrafo único (comprovante do
pagamento com discriminação de verbas); conteúdo mínimo do recibo —
usualmente identificação do empregador e do empregado, competência,
proventos, descontos, base de FGTS, base de INSS. **A confirmar** a lista
completa e obrigatória.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17.

**Dados.** Todos os itens do cálculo do mês do empregado; identificação do
empregador (mesmo mecanismo de identificação obrigatória de plataforma que
já serve a Contabilidade, RC-94 — reaproveitado, não reimplementado por
módulo).

**Regras.** Documento de **classe F** (forma prescrita) — a lista de campos
obrigatórios, uma vez confirmada em fonte oficial, não é opcional de
personalização, no mesmo espírito do que
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) já
registrou para demonstração e livro contábil.

**Telas e documentos.** Holerite impresso/PDF; classe **F**.

**Critérios de aceite.** Holerite de competência efetivada é sempre
reproduzível byte a byte a partir da memória de cálculo (mesmo dado, mesmo
documento).

**Não copiar / riscos.** RC-94 (identificação obrigatória vale para
**todos** os módulos) já decide que o mecanismo de timbre/identificação não
nasce dentro de `apps/folha` — é de plataforma, reaproveitado.

### FOL-22 — Resumo, extrato e relação de líquidos da folha

**O que é.** Três relatórios de conferência complementares ao holerite: o
**Resumo** (totais da folha por rubrica, visão gerencial), o **Extrato**
(detalhe por empregado, mais compacto que o holerite) e a **relação de
Líquidos** (só o valor a pagar por empregado, para conferência do
pagamento).

**Referência de rotina.** Manual, páginas 998-1009 (Resumo, Extrato,
Líquidos); relação da folha (1024-1026); movimentos (1026-1029);
demonstrativo de INSS folha e INSS eSocial (1029-1031, conferência entre os
dois valores — achado relevante para um critério de aceite: os dois **têm**
que bater).

**Fonte normativa.** Sem forma prescrita — classe **C**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17.

**Dados.** Mesmos de FOL-17, agregados por rubrica/empregado/total.

**Regras.** O total do Resumo por rubrica bate com a soma dos holerites
individuais da mesma competência — mesma origem, agregações diferentes
(mesmo princípio já usado em Diário × Balancete na Contabilidade). O INSS
apurado na folha bate com o INSS declarado (quando FOL-43/eSocial existir)
— conferência explícita, não coincidência.

**Telas e documentos.** Telas/relatórios de resumo, extrato, líquidos;
classe **C**.

**Critérios de aceite.** Teste que soma os holerites individuais e compara
com o total do Resumo da mesma competência.

### FOL-23 — Exportação de crédito em conta e cadastro para bancos

**O que é.** O arquivo no leiaute de cada banco (CNAB ou proprietário) com
os créditos de salário a fazer, e o arquivo de cadastro de empregados para
abertura de conta-salário.

**Referência de rotina.** Manual, páginas 1012-1021 (Crédito em Conta;
Exportação de Cadastro para Bancos).

**Fonte normativa.** Leiaute CNAB (Febraban) ou específico de cada banco.
**A confirmar por banco** — não é norma trabalhista, é padrão de mercado
financeiro, e cada convênio bancário do escritório/cliente pode variar.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-01 (dados bancários do empregado).

**Dados.** Banco, agência, conta, valor líquido por empregado, competência,
data de pagamento.

**Regras.** Reenvio do mesmo arquivo de crédito não duplica pagamento
silenciosamente — mesma regra de idempotência de importação/exportação do
projeto.

**Telas e documentos.** Exportação; classe **A** (leiaute do banco).

**Perguntas.** Com quais bancos o escritório opera hoje para crédito de
salário? Determina qual leiaute priorizar.

### FOL-24 — Rascunho × folha efetivada (invariante do projeto)

**O que é.** Não é um item do manual — é uma invariante do próprio
DataLedger (AGENTS.md §10, mesmo princípio já registrado como pendente na
Contabilidade, BL-10) que a Folha precisa desde o primeiro cálculo: um
cálculo em elaboração é **distinguível** de um cálculo **efetivado**
(pago), e só o efetivado é imutável.

**Exemplo.** O cálculo de FOL-17 nasce como rascunho — pode ser recalculado
livremente enquanto o escritório ainda está conferindo horas e faltas do
mês. Ao confirmar o pagamento, o cálculo vira efetivado: qualquer correção
depois disso é diferença rastreável (FOL-15), nunca reescrita do valor
original.

**Referência de rotina.** Não é rotina do manual — é decisão de arquitetura
do DataLedger, ainda que o manual **pressuponha** informalmente essa
distinção em vários pontos (ex.: "Folha deste mês já foi paga", página
692), sem implementá-la como estado explícito e protegido.

**Fonte normativa.** Não se aplica — é regra de engenharia do projeto.

**Situação no DataLedger.** **Não existe**, porque o módulo inteiro não
existe; registrado aqui para que **nasça já correto**, ao contrário da
Contabilidade, onde a distinção é pendência retroativa (BL-10).

**Depende de.** FOL-17.

**Dados.** Estado do cálculo (rascunho/efetivado), data de efetivação, ator
responsável.

**Regras.** Cálculo efetivado nunca é sobrescrito por `.save()`/`.delete()`
diretos — mesmo padrão de `LancamentoImutavelError` da Contabilidade,
reaproveitado ou espelhado no novo app.

**Critérios de aceite.** Tentativa de editar item de cálculo efetivado é
recusada no nível do modelo, não só da tela ou da API.

## Onda 2 — Ciclo anual e integração contábil

### FOL-25 — Períodos aquisitivos de férias

**O que é.** O controle, por empregado, de cada período de 12 meses que gera
direito a férias — com sua situação (em aberto, parcialmente gozado, gozado,
perda por afastamento, perda por falta) e o efeito de faltas e afastamentos
sobre os dias de direito.

**Exemplo.** Maria, admitida 03/01/2024: 1º período aquisitivo
03/01/2024-02/01/2025, sem faltas relevantes, 30 dias de direito. Se tivesse
7 faltas injustificadas no período, o direito cairia para 24 dias (CLT, art.
130, "faixas exatas a confirmar em fonte oficial — não afirmadas aqui como
regra pronta").

**Referência de rotina.** Manual, "Períodos Aquisitivos", páginas 753-760.

**Fonte normativa.** CLT, arts. 130 (faltas × dias de direito) e 133
(perda do direito, incluindo mais de 180 dias de afastamento pela
previdência dentro do período). **A confirmar** as faixas exatas.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-33 (afastamentos afetam o período).

**Dados.** Empregado, início/fim do período aquisitivo, situação, faltas
justificadas/injustificadas, dias afastados (previdência/sem
remuneração/com remuneração), dias de direito, dias de abono, dias gozados,
dias restantes.

**Regras.** Dias de direito é **sempre derivado** das faltas e afastamentos
do período, nunca digitado livremente sem justificativa auditável — quando
o escritório precisar de ajuste manual, o motivo fica registrado.

**Telas e documentos.** Tela de período aquisitivo; relatório "Vencimento
das Férias" (classe **C**), FOL-65.

**Critérios de aceite.** Caso de referência sintético com faltas dentro de
uma faixa de exemplo reproduz o desconto de dias de direito conforme a regra
confirmada (não implementar antes da confirmação).

### FOL-26 — Férias individuais (programação, aviso, gozo, recibo)

**O que é.** O processo de conceder férias a um empregado: programar a data,
avisar com antecedência mínima, calcular o valor (salário do período + 1/3
constitucional, mais eventual adiantamento de 13º), e emitir o recibo.

**Exemplo — pedido do Fred, 1/3 constitucional.** Maria tira 30 dias de
férias; salário-base R$ 3.000,00 (sem variação no período, "hipótese
simplificadora"); valor das férias = R$ 3.000,00 (proporcional aos dias
gozados, "regra exata de dias corridos × dias úteis a confirmar") + 1/3 de
R$ 3.000,00 = R$ 1.000,00 → total bruto R$ 4.000,00, sujeito a INSS e IRRF
**pela tabela vigente, a confirmar** (a base de INSS e IRRF das férias tem
regra própria, distinta da folha mensal — a confirmar).

**Referência de rotina.** Manual, "Férias — Individual", páginas 735-747
(programação, aviso prévio de férias, cálculo individual, consulta,
recálculo, exclusão, recibo).

**Fonte normativa.** CLT, arts. 129-145; aviso de férias com antecedência
mínima de 30 dias, art. 135; adicional de 1/3, Constituição Federal, art. 7º,
XVII. **A confirmar** dispositivo a dispositivo.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-25, FOL-14 (regras do sindicato), FOL-17.

**Dados.** Empregado, período aquisitivo, data de início/fim do gozo, dias
gozados/abonados/vendidos (abono pecuniário), valor calculado, indicador de
adiantamento de 13º.

**Regras.** Férias calculadas e pagas (efetivadas) seguem a mesma
imutabilidade de FOL-24; recálculo gera diferença rastreável.

**Telas e documentos.** Telas de programação, aviso e cálculo; **recibo de
férias**, classe **F** — forma prescrita a confirmar.

**Critérios de aceite.** Caso de referência sintético com 1/3 constitucional
reproduz a mecânica de FOL-26 acima.

### FOL-27 — Férias coletivas

**O que é.** A concessão de férias a um grupo de empregados ao mesmo tempo
(ex.: parada de fábrica), com regras próprias de início de novo período
aquisitivo.

**Referência de rotina.** Manual, páginas 747-753 (aviso prévio em grupo,
férias coletivas, período de retorno, data de pagamento conforme
parâmetros/sindicato).

**Fonte normativa.** CLT, arts. 139-141 (férias coletivas, comunicação prévia
ao Ministério do Trabalho e ao sindicato). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-25, FOL-26.

**Dados.** Empresa/filial/departamento, período de férias coletivas,
empregados afetados, data de retorno.

**Regras.** Mesma imutabilidade e rastreabilidade de FOL-26; empregado com
menos de 12 meses trabalhados pode ou não iniciar novo período aquisitivo
conforme parâmetro do sindicato (FOL-14) — regra explícita, não implícita.

**Telas e documentos.** Tela de férias coletivas; recibo, classe **F**.

**Perguntas.** Algum cliente da carteira decreta férias coletivas na
prática?

### FOL-28 — 13º salário (adiantamento e integral)

**O que é.** O décimo terceiro salário: uma parcela adiantada (geralmente
até 30/11) e a parcela final (até 20/12), proporcional aos meses trabalhados
no ano.

**Exemplo — pedido do Fred, 13º proporcional 7/12.** Empregado admitido em
junho, trabalhou 7 meses completos do ano até dezembro (jun-dez, "contagem
exata de fração de mês a confirmar — regra do dia 15"). Salário R$ 3.000,00
sem variação no ano ("hipótese simplificadora"). 13º proporcional = R$
3.000,00 × 7/12 = R$ 1.750,00 bruto, sujeito a INSS e IRRF **pela tabela
vigente, com regra de cálculo própria do 13º integral — a confirmar, não
afirmada aqui**; a 1ª parcela (adiantamento) não sofre desconto (regra
geral, **a confirmar**), a 2ª parcela concentra os descontos sobre o total.

**Referência de rotina.** Manual, seção 13º Salário no cálculo (páginas
692-693) e Sindicato > Guia 13º Salário (páginas 465-466).

**Fonte normativa.** Lei 4.090/1962 (institui a gratificação de Natal) e Lei
4.749/1964 (regulamenta o pagamento); proporcionalidade por fração de mês
(regra do 15º dia) — Lei 4.090/1962, art. 1º, §2º. **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-18 (adiantamento), FOL-14 (regras do sindicato
sobre avos de afastamento).

**Dados.** Empregado, competência, tipo (adiantamento/integral), avos de
direito, valor bruto, descontos, líquido.

**Regras.** Mesma imutabilidade e rastreabilidade de FOL-24; avos de direito
com afastamento seguem regra do sindicato (limitação a 6 avos, ou conforme
dias — FOL-14), nunca cálculo linear ingênuo.

**Telas e documentos.** Tela de cálculo; recibo integrado ao holerite ou
próprio, classe **F**.

**Critérios de aceite.** Caso de referência sintético com 7/12 reproduz a
mecânica acima.

### FOL-29 — Provisão de férias e 13º

**O que é.** O cálculo mensal do valor que a empresa deveria estar
"guardando" (provisionando) para pagar férias e 13º no futuro, incluindo os
encargos que incidirão (INSS patronal, FGTS) — usado sobretudo para a
integração contábil.

**Referência de rotina.** Manual, "Provisão Férias e 13º", páginas 760-762;
relatórios de provisão (analítica, sintética, com encargos), páginas
1180-1186.

**Fonte normativa.** NBC TG 25 (Provisões, Passivos Contingentes e Ativos
Contingentes) — provisão de férias e 13º é obrigação contábil, não
trabalhista; **a confirmar** o item exato da norma.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-25, FOL-28.

**Dados.** Empresa, competência inicial/final, empregados selecionados,
valor provisionado por empregado/rubrica, encargos projetados.

**Regras.** Provisão é **estimativa contábil**, não pagamento — nunca se
confunde com o valor efetivamente pago em FOL-26/FOL-28; a integração
contábil (FOL-39) lança a provisão em conta própria, distinta da conta de
despesa efetiva.

**Telas e documentos.** Tela de cálculo de provisão; relatórios analítico e
sintético, classe **C**.

**Critérios de aceite.** Provisão de um mês não se soma indevidamente à
provisão de outro (cada competência com seu próprio saldo, salvo acumulação
explícita).

### FOL-30 — Aviso prévio de rescisão (Lei 12.506/2011)

**O que é.** A comunicação formal do fim do contrato com antecedência,
trabalhado ou indenizado, com a contagem de dias ampliada pelo tempo de
casa.

**Exemplo — pedido do Fred, aviso proporcional.** Empregado com 3 anos
completos de casa, demitido sem justa causa: aviso prévio = 30 dias (base) +
3 dias por ano completo × 3 anos = 39 dias ("mecânica conforme Lei
12.506/2011, art. 1º, parágrafo único — texto a confirmar na fonte oficial,
não afirmado aqui como cálculo definitivo, porque pode haver regra de
sindicato que substitua a proporcionalidade padrão — FOL-14").

**Referência de rotina.** Manual, "Aviso Prévio", páginas 707-714
(individual, botão novo, cancelar aviso, em grupo).

**Fonte normativa.** CLT, arts. 487-491; Lei 12.506/2011. **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-14.

**Dados.** Empregado, motivo da rescisão, concedido por (empregador/
empregado), tipo (trabalhado/indenizado/misto), data do aviso, dias de
aviso, data de demissão calculada, dados de cancelamento (quando houver).

**Regras.** Dias de aviso são **sempre calculados**, nunca digitados livres
sem cálculo de referência — mesmo quando o resultado é ajustado
manualmente, o cálculo original fica registrado; cancelamento de aviso é
operação própria, rastreável, não exclusão silenciosa.

**Telas e documentos.** Tela de aviso prévio; recibo/comunicado de aviso
prévio, classe **F**.

**Critérios de aceite.** Caso de referência sintético (3 anos completos = 39
dias, mecânica de soma) testável antes de qualquer valor de tabela.

### FOL-31 — Rescisão individual e TRCT

**O que é.** O fechamento de contas do fim do contrato: saldo de salário,
férias vencidas/proporcionais + 1/3, 13º proporcional, aviso prévio, multa
de FGTS quando cabível — tudo reunido no TRCT (Termo de Rescisão do Contrato
de Trabalho).

**Exemplo — pedido do Fred, rescisão sem justa causa com aviso
proporcional.** Empregado com salário R$ 3.000,00, demitido sem justa
causa, aviso prévio indenizado de 39 dias (FOL-30). Verbas, em mecânica
(sem valores de tabela de INSS/IRRF/FGTS):
- Saldo de salário: dias trabalhados no mês da rescisão × valor do dia.
- Aviso prévio indenizado: 39/30 × R$ 3.000,00 = R$ 3.900,00 ("fórmula de
  conversão a confirmar — dias corridos versus fração de salário").
- Férias vencidas (se houver período vencido) + 1/3.
- Férias proporcionais do período em curso + 1/3 (avos calculados conforme
  FOL-25, projetados pelo aviso prévio quando indenizado — regra a
  confirmar).
- 13º proporcional do ano (avos conforme FOL-28, também projetado pelo aviso
  quando indenizado — a confirmar).
- Multa de 40% sobre o FGTS depositado durante o contrato, para rescisão sem
  justa causa (Lei 8.036/1990, art. 18, §1º, **percentual e base a
  confirmar**, não afirmado como cálculo pronto).

**Referência de rotina.** Manual, "Rescisões — Individual", páginas
714-729 (guia geral, médias, outros dados, recalcular, consultar, excluir,
emitir TRCT).

**Fonte normativa.** CLT, arts. 477-486 (rescisão); Lei 8.036/1990 (FGTS,
multa rescisória); prazo de pagamento das verbas — CLT, art. 477, §6º (Lei
13.467/2017 alterou o prazo para 10 dias corridos, **a confirmar** redação
vigente). **Todas a confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-25, FOL-28, FOL-30, FOL-14.

**Dados.** Empregado, motivo da rescisão, data de demissão, aviso prévio
vinculado, cada verba calculada (com sua própria memória de cálculo),
total, dados de FGTS.

**Regras.** Rescisão calculada e **paga** (efetivada) é imutável — correção
por diferença rastreável (AGENTS.md §10); prazo de pagamento das verbas é
regra verificável (a confirmar), com alerta se ultrapassado.

**Telas e documentos.** Tela de rescisão; **TRCT**, classe **F** — a norma
tem modelo oficial de termo (a confirmar leiaute vigente, inclusive se
substituído por evento do eSocial no lugar do formulário físico).

**Critérios de aceite.** Caso de referência sintético reproduz a mecânica
acima, com cada verba rastreável separadamente na memória de cálculo.

**Não copiar / riscos.** O manual permite "Recalcular Rescisão" e "Excluir
Rescisão" diretamente (páginas 725-727) sobre rescisão já gravada — o
DataLedger **não copia**: rescisão paga é imutável, correção é diferença
rastreável, exatamente o "não copiar" que o
[mapa-funcional-folha.md](../mapa-funcional-folha.md) já registrou.

### FOL-32 — Rescisão em grupo e complementar

**O que é.** Rescisão processada para vários empregados de uma vez (ex.:
encerramento de um contrato de obra), e rescisão complementar (ajuste
posterior à rescisão original, quando surge verba pendente).

**Referência de rotina.** Manual, páginas 729-735 (em grupo, complementar).

**Fonte normativa.** Mesma de FOL-31.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-31.

**Regras.** Processamento em grupo exige autorização confirmada empresa por
empresa e empregado por empregado — nunca "todos de uma vez" sem checagem
individual (mesmo "não copiar" do mapa funcional). Rescisão complementar é
sempre vinculada à rescisão original, nunca solta.

**Telas e documentos.** Telas próprias; TRCT complementar, classe **F**.

### FOL-33 — Afastamentos (INSS, maternidade, ausência justificada, mandato sindical)

**O que é.** O registro de qualquer período em que o empregado não trabalha
mas mantém o vínculo: doença (com ou sem afastamento pelo INSS), licença-
maternidade, mandato sindical, ausência justificada por lei (ex.: óbito,
casamento), entre outros — cada motivo com efeito próprio sobre férias,
13º e folha do período.

**Referência de rotina.** Manual, "Afastamentos", páginas 762-772 (guia
geral, outros dados, mandato sindical, licença maternidade, ausência
justificada, afastamento INSS).

**Fonte normativa.** CLT, arts. 471-476 (afastamentos em geral); Lei
8.213/1991, arts. 59-63 (auxílio por incapacidade/afastamento pelo INSS);
licença-maternidade — CLT, art. 392, e Lei 11.770/2008 (prorrogação).
**Todas a confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, motivo do afastamento (tabela de motivos — a
confirmar contra a tabela oficial do eSocial), data de início/fim,
indicador de remuneração pela empresa/INSS, CAT vinculada (quando acidente
de trabalho, FOL-37).

**Regras.** Afastamento além de 15 dias por doença transfere o pagamento ao
INSS (regra geral, **a confirmar prazo vigente**); afastamento por mais de
180 dias pela previdência afeta o período aquisitivo de férias (FOL-25) —
efeito explícito, não implícito.

**Telas e documentos.** Tela de afastamento; relatório de afastamentos,
classe **C**.

**Critérios de aceite.** Afastamento por motivo que zera o período
aquisitivo altera corretamente a situação em FOL-25, com rastro do motivo.

### FOL-34 — Licença-prêmio

**O que é.** Um benefício de alguns sindicatos/estatutos: período de
descanso remunerado adicional após um tempo de casa (comum em categorias
específicas, ex.: bancários de estatais, servidores).

**Referência de rotina.** Manual, "Licença Prêmio", páginas 772-775
(períodos aquisitivos, individual); regras no sindicato, páginas 482-484.

**Fonte normativa.** Depende de convenção coletiva ou estatuto específico —
não é direito CLT geral. **A confirmar se algum cliente da carteira tem
essa cláusula.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-14, FOL-25 (mesma lógica de período aquisitivo).

**Perguntas.** Algum cliente da carteira tem licença-prêmio prevista em
convenção ou estatuto? Sem confirmação, este item fica de baixa prioridade
dentro da Onda 2.

### FOL-35 — Estabilidades

**O que é.** O controle de períodos em que o empregado tem garantia legal ou
convencional contra demissão sem justa causa (gestante, acidentado, membro
de CIPA, dirigente sindical, pré-aposentadoria conforme convenção).

**Referência de rotina.** Manual, "Estabilidades", página 775; regras no
sindicato, páginas 548-555 (afastamentos, dissídios, demais estabilidades).

**Fonte normativa.** Gestante — ADCT, art. 10, II, "b"; acidente de trabalho
— Lei 8.213/1991, art. 118; CIPA — CLT, art. 165; dirigente sindical — CLT,
art. 543, §3º. **Todas a confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-33 (vários motivos de estabilidade nascem de um
afastamento).

**Dados.** Empregado, tipo de estabilidade, data de início/fim da garantia.

**Regras.** Rescisão de empregado com estabilidade ativa gera **alerta
obrigatório**, não bloqueio silencioso — decisão de negócio final é do
escritório/cliente, mas o sistema não pode deixar passar despercebido.

**Telas e documentos.** Cadastro/relatório de estabilidades, classe **C**.

### FOL-36 — Aposentadoria (com rescisão ou por afastamento)

**O que é.** O tratamento da aposentadoria do empregado: pode gerar rescisão
do contrato (se o empregado se desliga) ou ser apenas informativa (se
continua trabalhando).

**Referência de rotina.** Manual, "Aposentadoria", páginas 776-783 (com
rescisão, por afastamento, somente informação).

**Fonte normativa.** Lei 8.213/1991; a aposentadoria, por si, **não**
extingue automaticamente o contrato de trabalho (entendimento consolidado
após a CF/1988, ADI 1.721) — **a confirmar** o estado atual do entendimento.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-31 (quando gera rescisão), FOL-33 (quando é
informativa/por afastamento).

**Dados.** Empregado, tipo de aposentadoria, data, indicador de rescisão
vinculada.

### FOL-37 — CAT — Comunicação de Acidente de Trabalho

**O que é.** O registro formal de um acidente de trabalho ou doença
ocupacional, com os dados do acidente, testemunhas e atestado médico —
alimenta o afastamento (FOL-33) e o PPP (FOL-62).

**Referência de rotina.** Manual, páginas 783-792 (guia CAT, informações da
emissão, do acidente/doença, testemunhas, atestado médico).

**Fonte normativa.** Lei 8.213/1991, art. 22 (obrigatoriedade de comunicar
até o 1º dia útil seguinte); leiaute oficial da CAT — INSS/eSocial (evento
S-2210). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, data/hora do acidente, tipo (típico, trajeto, doença
ocupacional), parte do corpo atingida, agente causador, situação geradora,
testemunhas, atestado médico.

**Regras.** Prazo de comunicação é verificável (regra a confirmar), com
alerta de atraso.

**Telas e documentos.** Formulário CAT, classe **F** (leiaute oficial, a
confirmar se via formulário próprio ou só via evento do eSocial hoje).

### FOL-38 — Trabalho intermitente

**O que é.** O regime de contrato em que o empregador convoca o empregado
para prestações eventuais, com pagamento por período trabalhado — criado
pela Reforma Trabalhista.

**Referência de rotina.** Manual, "Convocação Trabalho Intermitente",
páginas 793-795.

**Fonte normativa.** CLT, art. 452-A (incluído pela Lei 13.467/2017).
**A confirmar** redação vigente e eventuais alterações posteriores.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-04 (rubricas próprias do intermitente — o
cálculo de férias, 13º e FGTS proporcionais a cada período trabalhado segue
regra distinta da CLT tradicional).

**Dados.** Empregado, convocação (data, prazo de resposta — mínimo 3 dias
corridos de antecedência, **a confirmar**), período efetivamente trabalhado,
valores calculados por período.

**Perguntas.** Algum cliente da carteira usa contrato intermitente hoje?
Sem confirmação, item de baixa prioridade dentro da Onda 2.

### FOL-39 — Integração contábil (folha, provisões, rescisão, pagamentos)

**O que é.** A geração automática do lançamento contábil a partir do
resultado da folha: débito na despesa de salários/encargos, crédito nas
contas de líquido a pagar, INSS a recolher, IRRF a recolher, FGTS a
recolher, e assim por diante para férias, 13º, provisões e rescisões —
configurável por conta débito/crédito e histórico, por grupo de rubricas.

**Exemplo.** Folha mensal de uma empresa com 5 empregados sintéticos: débito
único em "Despesas com Salários" pelo bruto total, créditos em "Salários a
Pagar" (líquido), "INSS a Recolher", "IRRF a Recolher", "FGTS a Recolher",
"Vale-Transporte a Recolher" — um lançamento **multi-partida**, exatamente o
caso que motivou o teto de 200 partidas por lançamento já registrado em
`RC-79`/`PE-42` da Contabilidade (*"uma contabilização de folha passa disso
com facilidade"*).

**Referência de rotina.** Manual, "Contabilidade — Configurar Integração",
páginas 647-667 (guias Folha, Férias, Rescisão, Empresa, Parcelamento,
Provisão de Férias, Provisão de 13º, Pagto. Encargos, Pagto. Folha); segunda
ocorrência do mesmo tema em "Integração Contábil" no menu Processos,
páginas 988-991.

**Fonte normativa.** Débito = crédito é invariante de engenharia do projeto
(AGENTS.md §10), não norma trabalhista; a classificação contábil de cada
rubrica (despesa, passivo) segue a estrutura de plano de contas já existente
em `apps/contabilidade` (CTB-01).

**Situação no DataLedger.** **Não existe no lado Folha.** O **destino**
já existe: `apps/contabilidade` tem `criar_lancamento`
(`apps/contabilidade/services.py:583`), que valida igualdade de débitos e
créditos, aplica o teto de 200 partidas com recusa explícita, e é
idempotente por chave — a integração da Folha **reaproveita** esse serviço,
não reimplementa lançamento contábil dentro de `apps/folha`.

**Depende de.** FOL-17, FOL-26 a FOL-32, FOL-29; CTB-02 (lançamento por
partidas dobradas, já existente).

**Dados.** Configuração por empresa: conta débito/conta crédito/histórico
por grupo de rubricas, para cada evento (folha, férias, rescisão, provisão
de férias, provisão de 13º, pagamento de encargos, pagamento de folha).

**Regras.**
- O lançamento gerado sempre fecha em débito = crédito (reaproveitando a
  validação já existente da Contabilidade).
- Quando a folha de uma competência excede o teto de partidas por
  lançamento (RC-79, hoje 200), o sistema **recusa com mensagem clara**,
  nunca trunca — mesma regra da Contabilidade; a consequência de produto
  (agrupar por rubrica em vez de por empregado, por exemplo) é decisão a
  tomar quando o caso real aparecer.
- Origem e documento de origem do lançamento (CTB-32, já pendente na
  Contabilidade) precisam apontar de volta para a competência/tipo de folha
  exata que o gerou — sem isso, a integração não é auditável.

**Telas e documentos.** Tela de configuração de integração; o lançamento
gerado usa as telas já existentes da Contabilidade (Diário, Razão,
Balancete).

**Critérios de aceite.** Lançamento gerado a partir de folha sintética fecha
em débito = crédito; teste que soma o líquido + INSS + IRRF + FGTS dos
créditos e confere com o bruto debitado.

**Não copiar / riscos.** O manual grava lançamento contábil derivado direto
como registro "definitivo" sem menção a estorno — o DataLedger usa o
mecanismo de **estorno** já existente na Contabilidade (`estornar_lancamento`)
para qualquer correção, nunca edição do lançamento gerado.

**Perguntas.** O escritório integra a folha à contabilidade automaticamente
hoje (no sistema de referência ou de outra forma), ou lança manualmente a
partir do resumo? Determina a urgência relativa deste item.

## Onda 3 — eSocial como preparação (sem transmissão)

### FOL-40 — Parâmetros do eSocial da empresa

**O que é.** A configuração, por empresa, do que o eSocial precisa saber
sobre ela: classificação tributária, se é cooperativa, construtora,
entidade sem fins lucrativos, entidade beneficente, contratações de pessoas
com deficiência, ambiente de envio (teste/oficial), faseamento,
centralização de eventos entre filiais.

**Referência de rotina.** Manual, "Parâmetros > Guia e-Social", páginas
82-119 (configurações de envio, geral, entidade beneficente, contratações).

**Fonte normativa.** Manual de Orientação do eSocial (MOS), versão vigente —
leiaute e regras de preenchimento de cada campo. **A confirmar a versão
vigente na data de implementação**, porque o MOS muda de versão (S-1.0,
S-1.1, S-1.2, S-1.3...) com efeito direto sobre estrutura de XML.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01 a FOL-17 (a base cadastral que os eventos vão
descrever).

**Dados.** Empresa, classificação tributária, indicadores (cooperativa,
construtora, entidade sem fins lucrativos, empresa de trabalho temporário),
ambiente (teste/oficial), tipo de centralização, empresa centralizadora.

**Regras.** Parâmetro de ambiente **teste** nunca pode ser confundido, na
tela ou no dado, com **oficial** — mesma regra de "identificar claramente
simulação, homologação e produção" do AGENTS.md §11.

**Telas e documentos.** Tela de parâmetros; sem impressão própria.

**Perguntas.** O escritório transmite eSocial hoje pelo sistema de
referência ou por outro meio? Essencial para dimensionar a Onda 3 —
independente da resposta, a preparação (Onda 3) tem valor por si (conferir
antes de enviar por qualquer canal), mas a resposta muda a prioridade.

### FOL-41 — Eventos de tabela (S-1000 a S-1080)

**O que é.** Os eventos "estáticos" do eSocial — cadastro do empregador, das
tabelas de rubricas, cargos, funções, horários, lotações tributárias — que
mudam pouco e servem de referência para os eventos periódicos e não
periódicos.

**Referência de rotina.** Manual, código eSocial em cada cadastro (rubricas,
página 365; cargos, página 600; funções, página 611; horários, página 620) e
o "Controle de Validados > Guia Tabelas", página 1106.

**Fonte normativa.** MOS vigente, eventos da série S-1000. **A confirmar
código de cada evento e sua versão de leiaute vigente** — nenhum código de
evento deste documento deve ser tratado como definitivo sem conferência.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-04, FOL-11, FOL-12, FOL-40.

**Dados.** Código eSocial de cada rubrica/cargo/função/horário; XML gerado
(estrutura, não transmissão); status de validação.

**Regras.** Geração do XML de tabela é determinística e reprodutível a
partir do cadastro — nunca "clique e adivinhe"; alteração no cadastro de
origem depois de o evento gerado exige nova versão do evento, rastreável.

**Telas e documentos.** Geração de XML; classe **A** (leiaute oficial).

### FOL-42 — Eventos não periódicos (admissão, afastamento, rescisão)

**O que é.** Os eventos disparados por um fato específico do contrato:
admissão (S-2200), alteração cadastral/contratual, afastamento temporário
(S-2230), aviso prévio, rescisão (S-2299), CAT (S-2210), entre outros.

**Referência de rotina.** Manual, botão eSocial em cada processo (rescisão,
página 727; aviso, página 711; afastamento — implícito na estrutura da guia
Afastamentos); Painel de Pendências lista os eventos S-2200, S-2230,
S-2250, S-2299, S-2300, S-2399 entre os que podem ser excluídos quando
gerados indevidamente (página 1093).

**Fonte normativa.** MOS vigente. **A confirmar código e leiaute exato de
cada evento**, e se algum desses códigos mudou de número em versão mais
recente do MOS do que a de 2018 usada pelo manual.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-30, FOL-31, FOL-33, FOL-37.

**Dados.** Tipo de evento, dados do fato de origem (admissão, afastamento,
rescisão, CAT), XML gerado, status.

**Regras.** Evento não periódico é gerado **a partir** do fato já registrado
no domínio (rescisão, afastamento) — nunca digitado paralelamente, sob risco
de divergência entre o que o sistema calculou e o que foi declarado.

**Telas e documentos.** Geração por processo; classe **A**.

### FOL-43 — Eventos periódicos (folha de pagamento)

**O que é.** O evento que consolida a folha do mês para o eSocial (folha de
pagamento, S-1200 e correlatos) e fecha o período (S-1299).

**Referência de rotina.** Manual, "Controle de Validados > Guia
Periódicos", página 1107; "Eventos Periódicos", página 1112.

**Fonte normativa.** MOS vigente, eventos da série S-1200/S-1299.
**A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-41, FOL-42.

**Dados.** Competência, empregados, rubricas calculadas mapeadas para código
eSocial, XML gerado, status.

**Regras.** Evento periódico só é gerado sobre folha **efetivada**
(FOL-24), nunca sobre rascunho — coerência com a invariante do domínio.

**Telas e documentos.** Geração; classe **A**.

### FOL-44 — Painel de pendências e controle de eventos do eSocial

**O que é.** O painel que reúne os problemas de cada lote de eventos
gerados: inválidos, duplicados, com erro de preenchimento, com erro de lote,
aguardando certificado, aguardando envio de múltiplos vínculos — tudo
**sem** transmitir, no escopo deste plano.

**Referência de rotina.** Manual, "Painel de Pendências", páginas 1092-1105
(guias Invalidados, Duplicados, Erros de Preenchimento, Erros Lote,
Aguardando Certificado A3, Aguardando Envio Múltiplos Vínculos, Em
Processamento); "Controle de Validados", páginas 1105-1110.

**Fonte normativa.** MOS vigente (regras de validação de leiaute) — o painel
em si é ferramenta de conferência, não tem forma normativa própria.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-41, FOL-42, FOL-43.

**Dados.** Lote, empresa, evento, código eSocial de origem, tipo de erro,
XML gerado, XML alterado (indicador), status.

**Regras.** O painel é de **conferência antes do envio** — no escopo deste
plano, "validado" significa "passou nas checagens de estrutura que o
DataLedger consegue fazer localmente", nunca "aceito pelo eSocial", porque
não há transmissão (FOL-80). Essa distinção precisa estar **visível na
tela**, não presumida.

**Telas e documentos.** Painel; classe **C** (ferramenta interna de
conferência).

**Critérios de aceite.** Evento com erro de estrutura sintético (campo
obrigatório ausente, no leiaute de teste) aparece no painel antes de
qualquer tentativa de envio.

### FOL-45 — Qualificação cadastral e manutenção de matrícula

**O que é.** A conferência de CPF/PIS/NIS do empregado contra a base do
eSocial antes de gerar eventos (evita rejeição por divergência cadastral), e
o ajuste de matrícula quando necessário.

**Referência de rotina.** Manual, "Qualificação Cadastral", páginas
1378-1382 (realizar qualificação, importar arquivo de retorno); "Manutenção
Matrícula eSocial Empregados", páginas 1375-1377.

**Fonte normativa.** MOS vigente, evento S-2190/S-2200 e regras de
qualificação cadastral do eSocial. **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Regras.** Qualificação é **consulta**, não transmissão de evento de
folha — mas se depender de serviço externo do eSocial para validar
CPF/PIS/NIS, entra na mesma cautela de credenciamento/homologação de
`escopo.md`, mesmo sendo consulta.

**Perguntas.** A consulta de qualificação cadastral do eSocial está
disponível sem certificado digital, ou exige o mesmo canal homologado da
transmissão? Determina se este item cabe na Onda 3 (preparação) ou se
desliza para perto de FOL-80 (transmissão).

## Onda 4 — Pró-labore, autônomos (RPA) e ponto

### FOL-46 — Pró-labore de sócios

**O que é.** A remuneração paga a sócio/administrador pelo seu trabalho na
empresa — regime previdenciário e fiscal próprio, distinto do empregado CLT
(sem FGTS, sem férias/13º por lei, com INSS de contribuinte individual).

**Referência de rotina.** O manual não isola "pró-labore" como processo
próprio — trata o sócio como um contribuinte individual (FOL-03) com
rubricas específicas; achado a registrar, não lacuna do inventário.

**Fonte normativa.** Lei 8.212/1991, art. 12, V, "f" (sócio administrador
como contribuinte individual); alíquota de INSS do contribuinte individual
sobre pró-labore — a confirmar; sem incidência de FGTS (não é empregado).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-03, FOL-06, FOL-07, FOL-17.

**Dados.** Sócio, empresa, valor do pró-labore, competência, INSS retido,
IRRF retido (quando aplicável).

**Regras.** Pró-labore nunca gera rubrica de FGTS, férias ou 13º pela regra
CLT — mesma distinção de regime já registrada em FOL-03.

**Telas e documentos.** Lançamento de pró-labore; recibo, classe **F**
(a confirmar forma).

### FOL-47 — RPA — recibo de pagamento a autônomo

**O que é.** O documento e o processo de pagar um contribuinte individual
(autônomo) pela prestação de um serviço específico, com retenção de INSS e,
quando aplicável, IRRF e ISS.

**Referência de rotina.** Manual, "RPA", páginas 795-799 (novo, alterar,
excluir — rendimento bruto, ISS, base INSS, INSS Frete SEST/SENAT, valor
INSS, pensão alimentícia, base IRRF, valor IRRF).

**Fonte normativa.** Lei 8.212/1991, art. 4º da Lei 10.666/2003 (retenção de
11% sobre a nota/RPA pela empresa tomadora, **percentual a confirmar**);
IRRF sobre serviço autônomo — Lei 7.713/1988, tabela progressiva mensal
(mesma tabela de FOL-06, com dedução de dependentes e de previdência
oficial). ISS — legislação municipal do prestador/tomador, **a confirmar
por município**.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-03, FOL-06, FOL-07.

**Dados.** Contribuinte, competência, descrição do serviço, rendimento
bruto, percentual/valor de ISS, base e valor de INSS, INSS Frete
SEST/SENAT (transportador autônomo), pensão alimentícia, base e valor de
IRRF, número de dependentes, data de pagamento.

**Regras.** RPA emitido e pago é imutável — correção por diferença
rastreável, mesmo padrão de FOL-24; retenção de INSS sobre RPA é distinta
da retenção sobre folha de empregado (base e regra próprias).

**Telas e documentos.** Tela de RPA; **recibo de RPA**, classe **F**.

**Critérios de aceite.** Caso de referência sintético (rendimento bruto,
percentual de retenção "a confirmar") reproduz a mecânica de base e valor
de INSS retido.

### FOL-48 — Carnê-leão do tomador de serviço (retenção sobre RPA)

**O que é.** O cálculo, feito pela empresa **tomadora** do serviço, da base
e do valor de IRRF a reter na fonte sobre o pagamento de um autônomo,
usando a lógica do carnê-leão (deduções, livro-caixa do prestador quando
informado) para chegar à base tributável do mês.

**Por que este item é diferente do `apps/livro_caixa` já existente.**
`apps/livro_caixa` ([DL-046](../../planos/DL-046-livro-caixa-e-carne-leao.md))
implementa o carnê-leão da **perspectiva do próprio profissional autônomo**,
que escritura sua renda mensal para recolher o carnê-leão. Este item, FOL-48,
é a perspectiva **oposta**: a empresa que **contrata** o autônomo (o
"tomador") retendo o imposto na fonte sobre o RPA que ela paga —
**RC-129** já registrou essa fronteira: *"o carnê-leão calculado a partir da
folha do empregador fica para o módulo de Folha"*. São dois cálculos
distintos, sobre a mesma figura tributária, vistos de lados opostos da
relação — nenhum reaproveita modelo de dados do outro, mas ambos devem usar
a **mesma tabela de IRRF** (FOL-06) e, quando cabível, o mesmo entendimento
sobre a base de cálculo (rendimento bruto antes de deduções, conforme a
Lei 15.270/2025 já estudada em `RC-133` do livro-caixa — a confirmar se essa
mesma leitura vale para o carnê-leão do tomador).

**Referência de rotina.** Manual, "Cálculo Carnê-Leão", páginas 799-801
(rendimentos — trabalho não assalariado, aluguéis, outros, exterior;
deduções — dependentes, previdência oficial, pensão alimentícia, livro-caixa
no mês).

**Fonte normativa.** Lei 7.713/1988, art. 8º (deduções do carnê-leão); IN
RFB vigente sobre carnê-leão (programa Carnê-Leão Web). **A confirmar**,
inclusive a leitura já registrada em `RC-133` (redução da Lei 15.270/2025
incide sobre o rendimento bruto, antes de deduções) — **a confirmar se
aplicável também nesta perspectiva do tomador**, não presumido igual sem
checagem.

**Situação no DataLedger.** **Não existe.** Não reaproveita `ContaLivroCaixa`
nem `LancamentoCaixa` de `apps/livro_caixa` — são modelos de outra
perspectiva (RC-129); pode, no entanto, reaproveitar a **tabela de IRRF**
(FOL-06) e o validador de código/formato já usados no carnê-leão do
livro-caixa, quando aplicável.

**Depende de.** FOL-03, FOL-06, FOL-47.

**Dados.** Contribuinte, competência, rendimentos (trabalho não assalariado,
aluguéis, outros, exterior), deduções (dependentes, previdência oficial,
pensão alimentícia, livro-caixa do prestador quando informado), base de
cálculo, IRRF retido.

**Regras.** Mesma imutabilidade e rastreabilidade de FOL-47; a leitura sobre
o que compõe a base (bruto × líquido de deduções) segue a mesma disciplina
de fonte oficial já exigida no livro-caixa — nenhuma presunção de igualdade
entre os dois módulos sem conferência específica.

**Telas e documentos.** Tela de cálculo; guia de recolhimento (carnê-leão),
classe **A**.

**Perguntas.** O escritório calcula esse carnê-leão do tomador na prática
hoje (folha de algum cliente que paga autônomos com regularidade), ou é caso
raro? Determina a prioridade real dentro da Onda 4.

### FOL-49 — Empréstimo consignado

**O que é.** O desconto parcelado em folha de um empréstimo tomado pelo
empregado junto a um banco ou financeira conveniada.

**Referência de rotina.** Manual, "Empréstimo Consignado", páginas 869-872
(configurações gerais, configurações do desconto).

**Fonte normativa.** Lei 10.820/2003 (consignação em folha de empregados
celetistas) — limite de percentual do salário descontável. **A confirmar
percentual vigente.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-04.

**Dados.** Empregado, credor consignado, valor total, número de parcelas,
valor da parcela, competência de início/fim.

**Regras.** Desconto consignado nunca ultrapassa o limite legal de margem
consignável sobre o salário — regra verificável, com recusa explícita se
extrapolar (percentual **a confirmar**).

**Telas e documentos.** Cadastro/lançamento; sem forma prescrita própria
(aparece no holerite).

### FOL-50 — Vale-transporte

**O que é.** O benefício de transporte, com desconto de até um percentual do
salário do empregado e o cálculo da quantidade de vales necessários por
itinerário.

**Referência de rotina.** Manual, páginas 859-865 (lançamentos, quantidade
de vales, quantidade em grupo); relatórios "Relação para compra" e "Recibo
de Vale Transporte", páginas 1166-1170.

**Fonte normativa.** Lei 7.418/1985 e Decreto 95.247/1987; desconto máximo
de 6% do salário básico do empregado. **A confirmar percentual vigente.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, itinerário, quantidade de vales por dia, valor
unitário, desconto calculado (limitado ao percentual legal).

**Regras.** Desconto nunca ultrapassa o percentual legal do salário —
recusa/ajuste explícito se o cálculo linear extrapolar.

**Telas e documentos.** Lançamento; relação de compra e recibo, classe **F**
(a confirmar).

### FOL-51 — Vale-alimentação

**O que é.** O benefício de alimentação/refeição, com participação opcional
do colaborador no custo.

**Referência de rotina.** Manual, páginas 865-869 (quantidade de vales,
quantidade em grupo, fornecimento, participação do colaborador); relatórios,
páginas 1170-1172.

**Fonte normativa.** Programa de Alimentação do Trabalhador (PAT) — Lei
6.321/1976 e regulamento; regras específicas de dedução fiscal para a
empresa não fazem parte deste módulo (é benefício fiscal da empresa, tema de
Contabilidade/Fiscal). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, valor do benefício, participação do colaborador
(desconto), competência.

**Telas e documentos.** Lançamento; relação e recibo, classe **F**
(a confirmar).

### FOL-52 — Benefícios (plano de saúde, EPI, previdência complementar)

**O que é.** Um conjunto de benefícios com regras próprias de custeio
compartilhado empresa/empregado, controle de entrega (EPI) ou contribuição
(previdência complementar).

**Referência de rotina.** Manual, páginas 633-647 (bancos, vale-transporte,
vale-alimentação, EPI, plano de saúde, previdência complementar); Ficha de
Controle de Entrega de EPI, página 1261 (NR-6).

**Fonte normativa.** Plano de saúde — regra contratual da operadora, sem
leiaute trabalhista próprio; EPI — NR-6 (obrigatoriedade de fornecimento e
registro de entrega); previdência complementar — Lei Complementar 109/2001.
**A confirmar por benefício.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, tipo de benefício, operadora/entidade, valor da
contribuição empresa/empregado, data de entrega (EPI).

**Regras.** Controle de entrega de EPI é **trilha obrigatória** (NR-6), não
apenas cadastro informativo — cada entrega registrada com data e item, sem
edição silenciosa depois de registrada.

**Telas e documentos.** Cadastros; ficha de entrega de EPI, classe **F**
(a confirmar se há leiaute oficial de ficha ou é livre, desde que
comprobatória).

### FOL-53 — Advertência e suspensão

**O que é.** O registro formal de medidas disciplinares aplicadas ao
empregado.

**Referência de rotina.** Manual, páginas 872-874; relatórios "Aviso de
Advertência/Suspensão" e "Relação de Advertências e Suspensões", páginas
1266-1269.

**Fonte normativa.** CLT não detalha procedimento de advertência/suspensão
como leiaute formal — é prática de gestão de pessoal, com efeito em outros
cálculos (ex.: descontos de PLR por advertência, já visto em FOL-14).
**A confirmar se há exigência formal específica além do registro em si.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, tipo (advertência/suspensão), data, motivo, dias de
suspensão (quando aplicável).

**Telas e documentos.** Cadastro; aviso ao empregado, classe **C**/**F**
a confirmar.

### FOL-54 — Ponto — horários, relógios e importação de marcações

**O que é.** A base do módulo de Ponto: os relógios físicos (ou apps) que
capturam entrada/saída, e o processo de importar essas marcações para o
sistema, com apuração automática (comparação da marcação contra o horário
esperado).

**Referência de rotina.** Manual Ponto, "Cadastrando Relógios", página 47;
"Cadastrando Funções dos Relógios", página 48; "Importação do Relógio
Eletrônico", páginas 60-61 (relógio identifica o leiaute do arquivo,
período de importação, importação e apuração juntas ou separadas).

**Fonte normativa.** Portaria MTP 671/2021 (regulamenta o registro
eletrônico de ponto) — requisitos do arquivo-fonte de dados e do sistema.
**A confirmar** o texto vigente e se substituiu integralmente a Portaria
1.510/2009 que o manual (de 2012) usa como base.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-12 (horário/jornada esperada), FOL-13.

**Dados.** Relógio (código, leiaute), arquivo importado, período,
marcações (empregado, data, hora, tipo entrada/saída, origem — relógio,
manual, automática, pré-assinalada).

**Regras.** Reimportação do mesmo arquivo/período **não duplica
silenciosamente** as marcações — é a regra que o próprio mapa funcional já
registrou como "o que não copiar": *"reimportação de ponto é operação
explícita, nunca atualização silenciosa"*; marcação de origem "relógio" é
distinguível de marcação incluída manualmente (regra do próprio manual,
página 66 — E/S/G/M/A/P) e essa distinção **nunca se perde**, porque é
exatamente o que separa fato registrado por equipamento de ajuste humano.

**Telas e documentos.** Tela de importação; sem forma prescrita própria (o
efeito registrado é o que importa).

**Critérios de aceite.** Reimportar o mesmo arquivo duas vezes não duplica
marcação; marcação importada é sempre distinguível de marcação manual na
consulta.

### FOL-55 — Ponto — abonos, acertos e reapuração

**O que é.** A correção humana das marcações e ocorrências: desconsiderar
uma marcação capturada por engano, incluir uma marcação esquecida, abonar
uma ausência, e a **reapuração** (recálculo das horas trabalhadas depois de
qualquer correção de horário ou marcação).

**Referência de rotina.** Manual Ponto, "Abonos e Acertos das Marcações",
páginas 61-70 (desconsiderar marcações, acerto individual e em grupo,
abonos individual e em grupo, consulta de horário, reapuração,
conferência).

**Fonte normativa.** Portaria MTP 671/2021 — exige que toda alteração de
marcação original fique registrada, sem apagar o dado bruto (princípio de
"pré-assinalação" e "marcação original preservada" já embutido na estrutura
do manual, página 65: "a exclusão de marcações somente será possível para
marcações que foram inseridas manualmente [...] marcação importada pelo
relógio não permitirá a exclusão"). **A confirmar dispositivo exato.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-54.

**Dados.** Marcação (original, preservada), ajuste (tipo, motivo, ator,
data/hora do ajuste), ocorrência apurada (código, quantidade de horas),
indicador de conferência (dia fechado para reapuração automática).

**Regras.**
- **Marcação original importada do relógio nunca é apagada** — só
  "desconsiderada" (com motivo registrado), preservando o dado bruto para
  auditoria. Mesmo o manual já protege essa regra (página 66); o
  DataLedger a torna **impossível de contornar**, não apenas desencorajada
  pela tela.
- Todo ajuste manual (inclusão, alteração, desconsideração) registra motivo
  e ator — trilha de auditoria (AGENTS.md §11).
- Reapuração recalcula **apenas** os dias não conferidos — dia já conferido
  exige reabertura explícita, mesmo espírito de período fechado na
  Contabilidade.

**Telas e documentos.** Tela de abonos e acertos; classe **C**.

**Critérios de aceite.** Tentativa de excluir marcação de origem "relógio"
é recusada (só desconsiderar, com motivo); dia conferido não é alterado por
reapuração em lote sem reabertura explícita.

### FOL-56 — Ponto — trocas de horário/período e saldos (banco de horas)

**O que é.** A troca do horário ou período de trabalho de um empregado (ex.:
mudança de turno), e o controle de saldo acumulado de horas (banco de
horas) — crédito de horas extras não pagas, débito de horas devidas.

**Referência de rotina.** Manual Ponto, "Troca de Horários", páginas 76-79
(individual, em grupo, de um dia por outro); "Troca de Período", páginas
80-81; "Cadastrando Saldos", página 52; "Consulta de Saldos", página 113;
"Relação de Saldos" (relatório), página 95.

**Fonte normativa.** Banco de horas — CLT, art. 59, §§2º-6º (redação da Lei
13.467/2017, compensação em até 6 meses por acordo individual, ou 1 ano por
acordo/convenção coletiva). **A confirmar** prazos vigentes.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-12, FOL-54, FOL-55.

**Dados.** Empregado, tipo de saldo (banco de horas, outro), competência,
crédito, débito, saldo acumulado, prazo de compensação/vencimento.

**Regras.** Saldo vencido sem compensação vira rubrica de pagamento em
folha (regra a confirmar contra convenção/lei vigente) — nunca "some" do
saldo sem virar efeito financeiro rastreável.

**Telas e documentos.** Telas de troca e de saldo; relação de saldos,
classe **C**.

**Critérios de aceite.** Saldo de banco de horas nunca fica negativo sem
indicação explícita de "a compensar" (empresa devendo horas ao empregado, ou
o inverso, sempre nomeado).

### FOL-57 — Ponto — relatórios de presença, absenteísmo e inconsistências

**O que é.** O conjunto de relatórios de conferência do ponto: cartão ponto
(espelho das marcações), presentes/ausentes do dia, absenteísmo (percentual
de horas extras/faltas sobre o total trabalhado), relação de inconsistências
da última importação.

**Referência de rotina.** Manual Ponto, "Menu Relatórios", páginas 84-96
(Cartão Ponto — inclusive modelo "Oficial cfe. Port. 1510", achado que já
sinaliza a obsolescência do leiaute citado, ver FOL-75; Resumo das
Ocorrências; Presentes/Ausentes; Relação das Marcações; Absenteísmo;
Afastamentos; Relação de Inconsistências; Relação de Saldos).

**Fonte normativa.** Cartão ponto — Portaria MTP 671/2021 (sucessora da
Portaria 1.510/2009 citada pelo manual). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-54, FOL-55, FOL-56.

**Dados.** Mesmos de FOL-54/55/56, agregados por relatório.

**Regras.** Relação de inconsistências reflete **exatamente** a última
importação — não acumula de importações antigas já corrigidas, para não
confundir o que ainda está pendente com o que já foi resolvido.

**Telas e documentos.** Relatórios; cartão ponto classe **F** (forma
prescrita, a confirmar); os demais, classe **C**.

**Critérios de aceite.** Relatório de absenteísmo bate com a soma das
ocorrências do período (mesma checagem cruzada já usada em outros módulos).

### FOL-58 — Integração do ponto com a folha (rubricas de horas)

**O que é.** Não é seção própria do manual — é a ponte que faz o saldo
apurado no Ponto (horas extras, faltas, banco de horas) virar rubrica
lançada na Folha (FOL-04/FOL-20), fechando o ciclo marcação → apuração →
rubrica → holerite.

**Exemplo.** As 10 horas extras a 50% do exemplo de FOL-17 vêm, na prática,
de uma apuração do Ponto: marcações do mês geraram ocorrência "Hora Extra
50%" com 10h de saldo, que a integração lança automaticamente como rubrica
na folha do empregado — sem digitação dupla.

**Referência de rotina.** Inferido da estrutura dos dois manuais (não há
seção "integração" nomeada no manual de Ponto de 2012, mas a Guia Cartão
Ponto e as ocorrências apuradas são desenhadas para alimentar rubricas da
Folha; achado do auxiliar de pesquisa).

**Fonte normativa.** Não é norma própria — é decorrência de FOL-04 e FOL-54.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-04, FOL-20, FOL-54, FOL-55, FOL-56.

**Dados.** Mapeamento ocorrência de ponto → rubrica de folha, por empresa.

**Regras.** A mesma hora apurada no Ponto nunca gera duas rubricas na Folha
por reprocessamento (idempotência); alteração retroativa de uma apuração já
integrada gera diferença rastreável, nunca sobrescreve rubrica já paga.

**Telas e documentos.** Configuração de mapeamento; sem impressão própria.

**Critérios de aceite.** Reprocessar a integração da mesma competência não
duplica rubrica de horas no holerite.

## Onda 5 — Anuais e utilitários

### FOL-59 — Alteração salarial individual e em grupo

**O que é.** O registro formal de mudança de salário de um empregado (mérito,
promoção, dissídio individual), distinto da alteração por convenção coletiva
(FOL-15), que também gera histórico e, quando aplicável, diferença
retroativa.

**Referência de rotina.** Manual, "Alteração Salarial", páginas 923-943
(individual, em grupo, professor individual/em grupo, grade salarial,
consulta).

**Fonte normativa.** Não há leiaute oficial — decorre do princípio geral de
alteração contratual (CLT, art. 468, vedação a alteração unilateral
prejudicial). **A confirmar** aplicabilidade a cada caso.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01.

**Dados.** Empregado, data da alteração, motivo, salário anterior, salário
novo, competência de vigência.

**Regras.** Alteração salarial gera histórico com vigência — nunca
sobrescreve o valor anterior sem preservar o registro (mesma regra de
FOL-01).

**Telas e documentos.** Tela de alteração; relatório "Alterações Salariais",
classe **C**.

### FOL-60 — Alteração retroativa de rubricas e diferenças salariais

**O que é.** O cálculo da diferença devida quando uma rubrica muda de valor
retroativamente (não só o salário-base — qualquer rubrica fixa), e o
relatório de conferência das diferenças pendentes de pagamento.

**Referência de rotina.** Manual, "Alteração Retroativa de Rubricas",
páginas 943-945; "Diferenças Referentes a Alteração Retroativa de Piso
Salarial", página 967; "Salário Família Retroativo", página 969; relatório
"Alterações Retroativas de Rubricas", página 1287.

**Fonte normativa.** Mesma base de FOL-15.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-04, FOL-15, FOL-59.

**Dados.** Rubrica, empregado, competência de origem, competência de
pagamento, valor da diferença, motivo/origem (convenção, alteração
individual, salário-família retroativo).

**Regras.** Mesma imutabilidade e rastreabilidade de FOL-15 — toda diferença
aponta para a origem que a gerou.

**Telas e documentos.** Relatório de conferência de diferenças, classe **C**.

### FOL-61 — Comprovante de rendimentos (informe de rendimentos)

**O que é.** O documento anual que resume, por empregado, tudo o que
recebeu e foi retido no ano — hoje a base para a declaração de Imposto de
Renda da pessoa física, sucessor do que o manual descreve integrado à
antiga DIRF (ver FOL-71).

**Referência de rotina.** Manual, "Comprovante de Rendimentos", página 1062;
"Manutenção para DIRF > Individualizar Valores", página 1368.

**Fonte normativa.** IN RFB vigente sobre comprovante de rendimentos pagos a
pessoa física — **a confirmar se ainda existe obrigação de emitir
comprovante em separado após a extinção/absorção da DIRF pelo eSocial**
(ver FOL-71).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-04 (rubricas marcadas para compor o
comprovante).

**Dados.** Empregado, ano-calendário, totais por tipo de rendimento
(tributável, isento, retenção na fonte), previdência oficial e privada,
pensão alimentícia deduzida, dependentes.

**Telas e documentos.** Emissão anual; classe **F** (a confirmar se ainda
segue leiaute próprio ou virou apenas extrato do que já foi declarado por
evento do eSocial).

### FOL-62 — PPP — Perfil Profissiográfico Previdenciário

**O que é.** O documento histórico das condições de trabalho de um
empregado, especialmente exposição a agentes nocivos — usado para comprovar
direito a aposentadoria especial.

**Referência de rotina.** Manual, "Histórico – PPP", páginas 918-922
(registro de CAT, atividades, exposição a fatores de risco I e II, exames
médicos); relatório "Responsáveis – PPP", página 683.

**Fonte normativa.** Instrução Normativa do INSS vigente sobre PPP; hoje
gerado a partir de eventos do eSocial (S-2240 e correlatos, exposição a
agentes nocivos). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-11 (fatores de risco do cargo), FOL-33, FOL-37.

**Dados.** Empregado, período, cargo/função, fatores de risco, exames
médicos, responsável técnico (engenheiro de segurança/médico do trabalho).

**Telas e documentos.** Emissão; classe **F**.

**Perguntas.** Algum cliente da carteira tem atividade que gere PPP de fato?

### FOL-63 — Pagamentos (folha e encargos) e parcelamento de encargos

**O que é.** O controle de quando e como a empresa efetivamente pagou a
folha e recolheu os encargos (INSS, FGTS, IRRF), e o parcelamento de
encargos em atraso.

**Referência de rotina.** Manual, "Pagamentos", páginas 974-981 (guia
Encargos, guia Folha); "Parcelamento de Encargos", páginas 983-988.

**Fonte normativa.** Não há leiaute oficial para o registro do pagamento em
si — decorre de FOL-19/FOL-39; parcelamento de débito previdenciário segue
normativa própria da Receita Federal/PGFN. **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-17, FOL-19, FOL-39.

**Dados.** Competência, tipo (folha/encargo), data de pagamento, valor,
parcelamento (número de parcelas, vencimentos).

**Regras.** Registro de pagamento efetivado é imutável, correção por
estorno/ajuste rastreável.

**Telas e documentos.** Tela de pagamentos; classe **C**.

### FOL-64 — Termo de quitação anual de obrigações trabalhistas

**O que é.** Um documento anual, facultativo, em que empregado e empregador
firmam a quitação das obrigações do período, perante o sindicato.

**Referência de rotina.** Manual, "Termo de Quitação Anual de Obrigações
Trabalhistas", páginas 1313-1315.

**Fonte normativa.** CLT, art. 507-B (incluído pela Lei 13.467/2017).
**A confirmar** dispositivo e uso prático.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-14, FOL-17.

**Perguntas.** O escritório usa este termo na prática, para algum cliente?
Sem confirmação, item de baixa prioridade.

### FOL-65 — Programação de férias e avisos de vencimento

**O que é.** O planejamento antecipado de quando cada empregado tirará
férias (programação), e o alerta de períodos aquisitivos próximos do prazo
legal de concessão (vencimento).

**Referência de rotina.** Manual, "Programação de Férias", páginas
1311-1313; "Avisos de Vencimento", página 166 (parâmetro) e 1283-1284
(relatório de vencimento das férias).

**Fonte normativa.** CLT, art. 134 (férias concedidas nos 12 meses
seguintes ao período aquisitivo). **A confirmar.**

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-25.

**Regras.** Período aquisitivo próximo do vencimento gera alerta —
ferramenta de conferência, não bloqueio automático de operação (decisão
final é do escritório).

**Telas e documentos.** Tela de programação; relatório de vencimento,
classe **C**.

### FOL-66 — Simuladores de férias e rescisão

**O que é.** O cálculo de "e se" — simular o valor de férias ou rescisão
sem gerar o registro definitivo, para o escritório orientar o cliente antes
de decidir.

**Referência de rotina.** Manual, "Simuladores", páginas 1344-1348 (férias,
rescisão, relatório de simulações).

**Fonte normativa.** Mesma de FOL-26/FOL-31 — o simulador usa exatamente a
mesma regra de cálculo, só não efetiva o resultado.

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-26, FOL-31.

**Regras.** Simulação **nunca** gera efeito em folha, contabilidade ou
eSocial — é cálculo isolado, claramente identificado como simulação na
tela e em qualquer documento gerado a partir dele (AGENTS.md §11,
"identificar claramente simulação, homologação e produção").

**Telas e documentos.** Tela de simulação; documento de simulação marcado
como tal, classe **C**.

**Critérios de aceite.** Simulação de rescisão não cria registro de
rescisão real, nem afeta período aquisitivo de férias ou saldo de qualquer
tipo.

### FOL-67 — Importação (cadastros, tabelas, RPA, sistemas concorrentes)

**O que é.** A entrada em lote de dados vindos de fora: empregados de outra
empresa (migração entre clientes do mesmo escritório), arquivo de texto de
lançamentos/tabelas/contribuintes/RPA, ou de um sistema concorrente na
migração de cliente novo.

**Referência de rotina.** Manual, "Importação", páginas 1392-1399 (de outra
empresa; de arquivo texto — lançamentos, empresas, pagamentos PIS, tabelas,
contribuintes, RPA; de sistemas concorrentes).

**Fonte normativa.** Não há leiaute oficial — formato próprio de cada
origem. A importação de "sistemas concorrentes" citada pelo manual não
autoriza presumir formato do sistema de referência sem exportação legítima
do cliente ([escopo.md](../../escopo.md): *"não presumir API pública... a
eventual migração depende de exportações legítimas ou interfaces
oficiais"*).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01 a FOL-17 (o que está sendo importado).

**Regras.** Importação repetida do mesmo arquivo **não duplica
silenciosamente** — idempotência (AGENTS.md §7, §8); toda importação
registra origem, data e ator, e é auditável linha a linha.

**Telas e documentos.** Tela de importação; classe **C**.

**Critérios de aceite.** Importar o mesmo arquivo duas vezes não cria
empregado/rubrica/lançamento duplicado.

### FOL-68 — Processos administrativos ou judiciais (suspensão de exigibilidade)

**O que é.** O registro de processos que afetam o cálculo da folha — por
exemplo, uma liminar que suspende a exigibilidade de uma contribuição para
um empregado ou para a empresa toda (referenciado também em FOL-08, FAP com
processo).

**Referência de rotina.** Manual, "Processos Administrativos ou judiciais",
páginas 639-647 (dados do processo, suspensão de exigibilidade, eSocial).

**Fonte normativa.** Depende do processo específico — sem leiaute geral;
efeito no eSocial via evento próprio (a confirmar código).

**Situação no DataLedger.** **Não existe.**

**Depende de.** FOL-01, FOL-08.

**Dados.** Número do processo, tipo, empresa/empregado afetado, escopo da
suspensão, vigência.

**Regras.** Processo vinculado a um cálculo precisa estar **vigente** na
competência do cálculo — cálculo de competência fora da vigência do
processo não aplica a suspensão automaticamente.

**Telas e documentos.** Cadastro de processo; classe **C**.

## Fora de escopo, obsoleto ou dependente de confirmação

Estes itens vêm do manual de 2018 (Folha) e de 2012 (Ponto) e descrevem
obrigações que a legislação brasileira **alterou ou substituiu** depois
dessas datas — nenhum deles vira código a partir deste documento sem
confirmação em fonte oficial vigente e validação do Fred. O formato é mais
curto de propósito: o objetivo aqui não é desenhar a implementação (que
seria prematura), é registrar que o item existe no manual, qual é o sucessor
**provável**, e onde a resposta definitiva mora.

### FOL-69 — GFIP/SEFIP

**O que é.** O arquivo mensal que declarava ao INSS e ao FGTS, ao mesmo
tempo, os dados da folha (Guia de Recolhimento do FGTS e Informações à
Previdência Social).

**Referência de rotina.** Manual, páginas 1048-1054.

**Sucessor provável.** eSocial (eventos periódicos, FOL-43) e DCTFWeb
(declaração de tributos, FOL-19/FOL-80), com o FGTS passando ao FGTS
Digital. **A confirmar em fonte oficial** — não afirmar aqui que a GFIP
está extinta como fato consumado sem checar a vigência exata e eventuais
exceções (ex.: competências residuais, situações de transição).

**Situação no DataLedger.** Não existe, e não deve ser implementada como o
manual descreve sem essa confirmação.

### FOL-70 — CAGED como arquivo próprio

**O que é.** A declaração mensal de admissões e desligamentos ao Cadastro
Geral de Empregados e Desempregados, como arquivo separado.

**Referência de rotina.** Manual, páginas 1054-1057.

**Sucessor provável.** Absorvido pelos eventos não periódicos do eSocial
(admissão S-2200, desligamento S-2299 — FOL-42), que passaram a alimentar o
CAGED automaticamente. **A confirmar em fonte oficial** a partir de quando e
se há hipótese residual de declaração em separado.

### FOL-71 — DIRF

**O que é.** A Declaração do Imposto de Renda Retido na Fonte, anual.

**Referência de rotina.** Manual, páginas 1069-1078; "Manutenção para
DIRF", páginas 1368-1373.

**Sucessor provável.** Absorvida pelo eSocial (eventos periódicos com dados
de retenção) — a Receita Federal anunciou o fim da obrigatoriedade da DIRF
para retenções sobre rendimentos do trabalho a partir de determinado
ano-calendário, substituída pelas informações prestadas ao eSocial e à
EFD-Reinf. **A confirmar o ano-calendário exato e se há exceção residual**
(ex.: retenções que continuam exigindo DIRF por não estarem no escopo do
eSocial/EFD-Reinf). Ver também FOL-61 (comprovante de rendimentos), que
pode continuar existindo mesmo com a DIRF extinta.

### FOL-72 — RAIS

**O que é.** A Relação Anual de Informações Sociais.

**Referência de rotina.** Manual, páginas 1065-1069.

**Sucessor provável.** Absorvida pelo eSocial (a Portaria que instituiu essa
absorção é do Ministério do Trabalho/Secretaria de Previdência) — a partir
de determinado ano-base, empresas que declaram pelo eSocial ficaram
dispensadas da RAIS em separado. **A confirmar o ano-base exato e se há
categoria de empregador ainda obrigada à RAIS tradicional.**

### FOL-73 — GRRF, GRFC e GRCSU (guias antigas do FGTS e da contribuição sindical)

**O que é.** Três guias de recolhimento específicas do sistema de referência
de 2018: GRRF (Guia de Recolhimento Rescisório do FGTS), GRFC (Guia de
Recolhimento do FGTS e Contribuição Social), GRCSU (Guia de Recolhimento da
Contribuição Sindical Urbana, para empregados e patronal).

**Referência de rotina.** Manual, páginas 1134-1147.

**Sucessor provável.** FGTS Digital substitui a lógica de guias avulsas do
FGTS (GRRF, GRFC) por um sistema unificado de apuração e cobrança
(Caixa/MTE); a GRCSU depende da vigência atual da própria contribuição
sindical, que a Lei 13.467/2017 tornou facultativa (ver FOL-78).
**A confirmar** cronograma de transição do FGTS Digital e se essas guias
ainda existem em algum caso de transição.

### FOL-74 — Homolognet / homologação sindical de rescisão

**O que é.** O procedimento, descrito pelo manual como parte do fluxo de
rescisão (página 1083), de homologação da rescisão perante o sindicato ou o
Ministério do Trabalho para empregados com mais de 1 ano de casa.

**Referência de rotina.** Manual, "Homolognet", páginas 1083-1085.

**Sucessor provável.** A **Lei 13.467/2017 extinguiu a obrigatoriedade** de
homologação da rescisão por sindicato/Ministério do Trabalho (revogou o
§1º do art. 477 da CLT) — o procedimento descrito pelo manual de 2018
provavelmente já refletia essa mudança de forma incompleta ou em
transição. **A confirmar o texto vigente do art. 477 da CLT** antes de
tratar homologação como etapa obrigatória de qualquer rescisão no
DataLedger.

### FOL-75 — AFDT/ACJEF e leiaute do ponto conforme Portaria 1.510/2009

**O que é.** Dois arquivos do módulo de Ponto: AFDT (Arquivo de Fonte de
Dados Tratado) e ACJEF (Arquivo de Controle de Jornada para Efeitos
Fiscais), e o modelo de cartão ponto identificado no manual como "Oficial
cfe. Port. 1510".

**Referência de rotina.** Manual Ponto, páginas 84-86 (AFDT, ACJEF); página
86 (modelo de cartão ponto "Oficial cfe. Port. 1510").

**Sucessor provável.** A **Portaria MTP 671/2021** substituiu a Portaria
1.510/2009 na regulamentação do registro eletrônico de ponto — os arquivos
e leiautes exigidos hoje (Arquivo Fonte de Dados — AFD, e demais exigências)
**precisam ser conferidos contra o texto vigente da Portaria 671/2021**,
porque nomenclatura e estrutura podem ter mudado, não só o número da
portaria de referência. **Nada deste item vira leiaute de código sem essa
conferência.**

### FOL-76 — SIRETT

**O que é.** Um informativo mensal citado pelo manual (página 1057) sem
detalhamento suficiente nesta leitura para descrever sua finalidade com
segurança.

**Referência de rotina.** Manual, página 1057.

**Situação.** **A confirmar o que é e se ainda existe** — não foi possível,
nesta sessão, identificar a finalidade exata nem a vigência a partir apenas
do sumário e da leitura por amostragem; registrado para não desaparecer do
inventário, não para ser implementado sem essa pesquisa adicional.

### FOL-77 — DCTF (antiga, distinta da DCTFWeb)

**O que é.** O manual cita "DCTF" como informativo mensal próprio (página
1058), anterior à DCTFWeb.

**Referência de rotina.** Manual, página 1058.

**Sucessor provável.** DCTFWeb (Declaração de Débitos e Créditos Tributários
Federais Previdenciários e de Outras Entidades e Fundos, via eSocial/EFD-
Reinf), já citada em FOL-19 e FOL-80. **A confirmar** se a DCTF "antiga"
citada pelo manual tem algum resíduo de uso para tributos da folha
específicos, fora do escopo da DCTFWeb.

### FOL-78 — Contribuição sindical dos empregados (vigência do desconto)

**O que é.** O desconto anual de um dia de salário do empregado, destinado
ao sindicato — que o manual trata como cálculo automático de rotina (datas
de vencimento por tipo de contribuição, páginas 438-446).

**Fonte normativa.** CLT, arts. 578-610 — a **Lei 13.467/2017** alterou o
art. 578 para condicionar o desconto à **autorização prévia e expressa** do
empregado, tornando-o **facultativo**, não mais compulsório como o manual
de 2018 pressupõe implicitamente em parte da sua estrutura de cálculo
automático. **A confirmar** a redação vigente e como o consentimento deve
ficar registrado e auditável antes de qualquer cálculo automático de
desconto sindical no DataLedger — este é o item que
[mapa-funcional-folha.md](../mapa-funcional-folha.md) já sinalizava como
"CLT após a Lei 13.467/2017".

**Situação no DataLedger.** Não existe; quando FOL-14/FOL-15 forem
implementados, a captura da autorização individual do empregado precisa
nascer junto, não depois.

### FOL-79 — Simples Doméstico (eSocial doméstico)

**O que é.** O regime de empregador doméstico (pessoa física), com folha,
encargos e eSocial próprios, simplificados (relatório "Simples Doméstico",
página 1046).

**Fonte normativa.** Lei Complementar 150/2015 (regula o trabalho
doméstico) e o eSocial doméstico (módulo simplificado, distinto do eSocial
empresarial). **A confirmar.**

**Situação no DataLedger.** Não existe. **Fora de escopo por ora** — decisão
de produto, não achado normativo: é um regime distinto o suficiente
(empregador pessoa física, sem CNPJ, processo de adesão próprio) para
merecer avaliação separada de prioridade, não incluído nas ondas 1-5 deste
plano.

**Perguntas.** O escritório atende empregador doméstico (cliente pessoa
física com empregada doméstica, por exemplo) como parte da carteira?

## FOL-80 — Transmissão ao eSocial, à DCTFWeb e ao FGTS Digital

**O que é.** O envio efetivo — não a preparação — dos eventos gerados nas
Ondas 3 e no restante do plano aos órgãos oficiais: eSocial (eventos),
DCTFWeb (declaração de tributos) e FGTS Digital (FGTS).

**Por que está separado de tudo o mais.** Diferente de todos os itens
anteriores, este não é "o que falta implementar depois" — é uma **decisão
de produto e de arquitetura de integração** que
[escopo.md](../../escopo.md) já reserva para depois de "verificar
documentação, disponibilidade, credenciamento e homologação", e que exige
**certificado digital e canal homologado**
([mapa-funcional-folha.md](../mapa-funcional-folha.md), Onda 3). Nenhum item
deste plano, sozinho, autoriza construir o conector de transmissão.

**Fonte normativa.** MOS do eSocial (protocolo de comunicação, assinatura
digital do lote), IN RFB vigente para a DCTFWeb, normativo do FGTS Digital
(Caixa/MTE) — **todos a confirmar**, e todos exigem ambiente de homologação
testado antes de qualquer transmissão em produção (AGENTS.md §7:
*"integrações oficiais exigem evidência em homologação antes de serem
apresentadas como homologadas"*).

**Situação no DataLedger.** Não existe, e não deve ser iniciado antes de
FOL-40 a FOL-45 estarem maduros e de uma decisão explícita do Fred sobre
credenciamento, certificado e canal.

**Depende de.** FOL-40 a FOL-45 (toda a Onda 3), decisão de produto do Fred.

**Regras.** Transmissão exige aprovação explícita de usuário autorizado,
vinculada à operação e aos dados exatos enviados (AGENTS.md §11); mudança
nos dados depois da aprovação invalida a aprovação anterior; protocolo de
envio e retorno fica registrado e auditável, com distinção clara entre
ambiente de teste e oficial (FOL-40).

**Perguntas.** O escritório já tem certificado digital e credenciamento
para transmitir eSocial/DCTFWeb/FGTS Digital hoje, por qualquer canal? Esta
é a pergunta que decide se FOL-80 é a próxima etapa depois da Onda 3, ou se
fica indefinidamente em preparação.

## Glossário

| Termo | Significado |
| --- | --- |
| **Rubrica** | Cada provento ou desconto que compõe o holerite, com forma de cálculo e incidências próprias (FOL-04). |
| **Incidência** | O efeito de uma rubrica sobre outra base (ex.: "soma no 13º", "sofre INSS") ou vice-versa. |
| **Base de cálculo** | A soma de rubricas ou fórmula sobre a qual uma rubrica é calculada (FOL-05). |
| **DSR** | Descanso Semanal Remunerado — o reflexo de horas extras e comissões sobre domingos e feriados (Lei 605/1949). |
| **FAP** | Fator Acidentário de Prevenção — multiplicador que ajusta o RAT conforme o histórico de acidentalidade da empresa (FOL-08). |
| **RAT** | Risco Ambiental do Trabalho (também chamado GILRAT) — alíquota adicional de INSS patronal conforme o grau de risco da atividade (FOL-07). |
| **Avos** | Frações de um direito proporcional ao tempo trabalhado (ex.: "7/12 avos de 13º" — FOL-28). |
| **Período aquisitivo** | O intervalo de 12 meses de trabalho que gera direito a férias (FOL-25). |
| **Período concessivo** | Os 12 meses seguintes ao período aquisitivo, dentro dos quais as férias devem ser concedidas (FOL-65). |
| **TRCT** | Termo de Rescisão do Contrato de Trabalho — o documento que consolida as verbas da rescisão (FOL-31). |
| **RPA** | Recibo de Pagamento a Autônomo — documento e processo de pagamento a contribuinte individual (FOL-47). |
| **Carnê-leão** | Recolhimento mensal obrigatório de IRRF por pessoa física que recebe de outra pessoa física ou do exterior; neste plano, tratado na perspectiva do **tomador** de serviço (FOL-48), distinta da perspectiva do **prestador** já coberta por `apps/livro_caixa` (RC-129). |
| **eSocial** | Sistema de escrituração digital das obrigações fiscais, previdenciárias e trabalhistas, por eventos em XML. |
| **MOS** | Manual de Orientação do eSocial — documento oficial que define leiaute e regras de cada evento, versionado (S-1.x). |
| **DCTFWeb** | Declaração de Débitos e Créditos Tributários Federais Previdenciários e de Outras Entidades e Fundos — sucessora, em parte, da GFIP/SEFIP. |
| **EFD-Reinf** | Escrituração Fiscal Digital de Retenções e Outras Informações Fiscais — retenções não relacionadas ao trabalho e algumas relacionadas. |
| **FGTS Digital** | Sistema que substitui a lógica de guias avulsas de recolhimento do FGTS por apuração unificada. |
| **Classe de documento (Folha/Ponto)** | C (conferência), F (forma prescrita por norma trabalhista), A (arquivo de obrigação ou de banco) — extensão, para este módulo, das classes já definidas em [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md). |
| **Rascunho × efetivado** | Distinção que a Folha precisa ter desde o nascimento (FOL-24), ao contrário da Contabilidade, onde é pendência retroativa (BL-10, ver [contabilidade.md](contabilidade.md)). |
| **Tipo de folha** | Classificação do processamento mensal — Mensal, Adiantamento, 13º Adiantamento, 13º Integral, Complementar (FOL-17). |
| **Banco de horas** | Controle de saldo acumulado de horas extras/faltas, compensável em prazo legal ou convencional (FOL-56). |
| **AFD/AFDT/ACJEF** | Arquivos do registro eletrônico de ponto; AFDT e ACJEF são da Portaria 1.510/2009, com sucessor a confirmar na Portaria MTP 671/2021 (FOL-75). |

## Perguntas abertas ao Fred, consolidadas

Todas já citadas no item correspondente; reunidas aqui para facilitar a
conversa com o Fred sem precisar reabrir os oitenta itens.

1. **FOL-01:** quantos empregados tem a carteira típica de cliente do
   escritório — dezenas ou centenas por empresa?
2. **FOL-02:** o escritório atende empresa com programa de estágio ativo
   hoje, com que volume?
3. **FOL-03:** a carteira do escritório tem produtor rural pessoa física
   entre os clientes com folha?
4. **FOL-04:** o escritório usa um conjunto de rubricas padrão comum a
   todos os clientes, ou cada empresa tem seu próprio plano de rubricas?
5. **FOL-05:** o escritório usa bases de cálculo por fórmula livre hoje, ou
   só soma de rubricas simples?
6. **FOL-08:** o escritório importa o FAP publicado pelo INSS manualmente
   hoje, ou tem acesso a algum serviço de consulta?
7. **FOL-09:** algum cliente da carteira está em estado com piso salarial
   próprio (ex.: SP, RJ, PR)?
8. **FOL-13:** a modelagem de "filial" da Folha deve reaproveitar
   `Estabelecimento` de `apps.empresas`, ou são conceitos distintos o
   suficiente para exigir modelo próprio? (decisão do `arquiteto-senior`,
   registrada aqui para não se perder)
9. **FOL-14:** quantos sindicatos distintos aparecem na carteira de
   clientes do escritório hoje? Um motor de regras condicionais completo
   só se justifica com diversidade real de convenções.
10. **FOL-15:** qual é a forma de alteração retroativa que o escritório usa
    na prática — complementar mês a mês, ou tudo de uma vez na folha do mês
    do aumento?
11. **FOL-17:** qual é o divisor de hora usado pelas convenções da carteira
    do escritório — 220h é universal ou varia por sindicato?
12. **FOL-19:** o escritório apura o INSS pela lógica clássica (GPS mensal
    simples) ou já pela DCTFWeb com compensação cruzada?
13. **FOL-23:** com quais bancos o escritório opera hoje para crédito de
    salário?
14. **FOL-27:** algum cliente da carteira decreta férias coletivas na
    prática?
15. **FOL-34:** algum cliente da carteira tem licença-prêmio prevista em
    convenção ou estatuto?
16. **FOL-38:** algum cliente da carteira usa contrato de trabalho
    intermitente hoje?
17. **FOL-39:** o escritório integra a folha à contabilidade
    automaticamente hoje (no sistema de referência ou de outra forma), ou
    lança manualmente a partir do resumo?
18. **FOL-40/FOL-80:** o escritório transmite eSocial hoje pelo sistema de
    referência ou por outro meio? O escritório já tem certificado digital e
    credenciamento para transmitir eSocial/DCTFWeb/FGTS Digital hoje, por
    qualquer canal?
19. **FOL-45:** a consulta de qualificação cadastral do eSocial está
    disponível sem certificado digital, ou exige o mesmo canal homologado
    da transmissão?
20. **FOL-48:** o escritório calcula o carnê-leão do tomador na prática
    hoje (folha de algum cliente que paga autônomos com regularidade), ou é
    caso raro?
21. **FOL-62:** algum cliente da carteira tem atividade que gere PPP de
    fato?
22. **FOL-64:** o escritório usa o termo de quitação anual na prática, para
    algum cliente?
23. **FOL-69 a FOL-77:** confirmação, em fonte oficial, de cada
    substituição apontada (GFIP/SEFIP, CAGED, DIRF, RAIS, GRRF/GRFC/GRCSU,
    Homolognet, AFDT/ACJEF, SIRETT, DCTF antiga) — vigência exata, ano de
    transição e eventuais exceções residuais.
24. **FOL-78:** como a autorização individual do empregado para o desconto
    da contribuição sindical (Lei 13.467/2017) deve ficar registrada e
    auditável no DataLedger?
25. **FOL-79:** o escritório atende empregador doméstico (cliente pessoa
    física com empregado doméstico) como parte da carteira?

> Auditoria de software não substitui a validação profissional das regras
> contábeis e legais (AGENTS.md §10). Todo item marcado "a confirmar" neste
> plano precisa de leitura da fonte oficial vigente, com item e data de
> consulta citados, e validação do Fred como responsável técnico, antes de
> qualquer linha de código de cálculo, tabela, evento ou leiaute.
