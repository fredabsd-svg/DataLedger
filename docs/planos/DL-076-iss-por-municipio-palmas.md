# DL-076 — Fiscal: ISS por município, começando por Palmas

**Demanda:** ordem do Fred de 08/10/2026 (RC-164); etapa 5 do roteiro de
execução do [DL-067](DL-067-plano-do-modulo-fiscal.md), na ordem da HI-60
(Simples → ISS por município → Presumido). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1) — é o valor da guia de ISS que o contador
confere. Auditoria independente: uma rodada, uma correção, uma reconferência.

**Conferência, nunca transmissão:** o produto apura e confere para o
contador emitir a guia no portal do município; não gera guia, não transmite
e não substitui o sistema municipal (HI-55).

## Base

[Consulta ao contador-senior sobre o ISS de Palmas](../projeto/consultas/2026-10-08-contador-senior-iss-palmas.md)
(LC 116/2003 e DL 406/1968 lidos no Planalto; LC 285/2013 e Decreto
1.667/2018 de Palmas em cópia íntegra; planilha oficial de adesão à NFS-e
nacional). Hipóteses HI-82 a HI-86; pendência PE-79 para o Fred.

O achado que define o desenho: **a tabela de alíquotas vigente de Palmas não
foi encontrada** (art. 57 da LC 285/2013 revogado pela LC 300/2014, cujo
texto não está acessível). Por isso a alíquota é **dado informado pelo
escritório**, com vigência e fonte, e o produto **confere** o ISS destacado
em cada nota — não o recalcula para a guia, que em Palmas sai das próprias
notas (RCTM art. 214).

## Depende de

[DL-072](DL-072-escrituracao-das-nfse-prestadas.md): escrituração das NFS-e
prestadas por natureza, com competência pelo `dCompet`.

## Escopo

1. **Campos de ISS da nota**, lidos do XML guardado e conferidos contra o
   esquema oficial da NFS-e nacional (versões 1.00 e 1.01): município de
   incidência (`cLocIncid`), código de tributação nacional (`cTribNac`, de
   onde sai o subitem da LC 116), base de cálculo, alíquota aplicada, valor
   do ISS, desconto incondicional, deduções e `tpRetISSQN`. Campo ausente
   fica ausente e é nomeado — nunca vira zero (notas de Palmas chegam ao
   Ambiente Nacional convertidas do WebISS).
2. **Regra do município com vigência e fonte** (HI-83): código IBGE,
   vencimento do ISS próprio e do retido (dia do mês seguinte), regra do dia
   não útil e dispositivo. Palmas entra cadastrada: dia 10 e dia 15,
   Decreto 1.667/2018, Anexo I e art. 86 § 3º.
3. **Alíquota por município e subitem** (HI-82): cadastro com vigência,
   fonte e autor, informado pelo escritório; percentual fora de 2% a 5% é
   recusado (LC 116 arts. 8º, II, e 8º-A), com as exceções do § 1º do art.
   8º-A tratadas como aviso; sobreposição de vigência recusada; trilha.
4. **Regime do ISS da empresa por exercício** (HI-84): por alíquota, fixo
   de autônomo ou fixo de sociedade de profissionais. Empresa do Simples não
   tem apuração aqui (o ISS dela está no pré-DAS, DL-075).
5. **Apuração mensal do ISS próprio** de empresa fora do Simples com
   estabelecimento no município: notas efetivadas da competência com
   natureza "ISS devido pelo prestador" e incidência no município; **total a
   recolher = soma do `vISSQN`**; conferência nota a nota contra a alíquota
   cadastrada (tolerância R$ 0,01); vencimento nominal com a regra do dia
   útil. **Bloqueios nomeados**: regime fixo; subitem sem alíquota vigente;
   nota sem campo de ISS necessário; regra do município ausente. Divergência
   da conferência é **pendência** listada, não bloqueio do total.
6. **Relatório de ISS retido sofrido** (HI-86), para empresas de qualquer
   regime: por competência, tomador, município, subitem, nota, base,
   alíquota e valor retido, com total por município.
7. **Relatório de ISS devido a outros municípios** (HI-85): por município de
   incidência, com os valores da própria nota, sem cálculo; avisos de
   alíquota fora de 2% a 5% e de incidência possivelmente errada.
8. Telas e API dos itens 2 a 7, com isolamento e permissões como na DL-072.

**Fica fora:** guia, transmissão, ISS fixo em reais (UFIP 2026 não achada),
juros e multa calculados (só aviso, LC 285/2013 art. 142), feriados
municipais, os outros 51 municípios além de Palmas (o cadastro aceita, mas
nenhum vem pronto), serviços tomados e ISS retido **pelo cliente tomador**
(etapa 6 do roteiro).

## Decisões tomadas na implementação

- **Caminhos dos campos conferidos no esquema oficial** (pacote de XSD da
  NFS-e nacional, versões 1.00 e 1.01): `vBC`, `pAliqAplic` e `vISSQN` ficam
  em `infNFSe/valores`, não na DPS; o código cita arquivo e linha de cada
  elemento.
- **Regra do município é dado global** (a norma é a mesma para todos os
  escritórios); a **alíquota é por escritório** (HI-82). Palmas entra pela
  migração com vigência desde 01/01/2019 — hipótese: o decreto é de
  06/12/2018 e a data de entrada em vigor não foi conferida no texto.
- **Base da conferência = `vBC` da nota**; quando `vServ − desconto −
  dedução` difere da `vBC`, é aviso.
- **A alíquota precisa cobrir o mês inteiro**; cobertura parcial bloqueia.
- **Bloqueios além do plano**, por segurança: nota cancelada depois de
  escriturada; nota escriturada como "ISS devido pelo prestador" com
  retenção no XML; `cLocIncid` ausente em nota de ISS devido.
- **Exceções do art. 3º da LC 116** transcritas do Planalto por subitem; o
  inciso I (serviço vindo do exterior) não é por subitem e ficou fora, e o
  inciso XII foi associado ao 7.16 — **para revisão do contador**.

## Critérios de aceite

1. Os campos de ISS lidos batem com o esquema oficial nas duas versões, com
   caminho do elemento citado no código; ausência é nomeada, nunca zero.
2. Apuração de Palmas com notas sintéticas: total = soma do `vISSQN` das
   notas de ISS próprio da competência; nota retida, de outro município,
   exportação, imune ou fora da lista não entra.
3. Conferência: nota com `vISSQN` diferente de base × alíquota cadastrada em
   mais de R$ 0,01 aparece como pendência com os dois valores; dentro da
   tolerância, não.
4. Subitem sem alíquota vigente, regime fixo, regra do município ausente ou
   campo de ISS ausente recusam com mensagem que nomeia o que falta.
5. Alíquota fora de 2% a 5% recusada no cadastro, nas três portas;
   sobreposição de vigência recusada.
6. Vencimento: competência 10/2026 → 10/11/2026 (próprio) e 15/11/2026
   (retido), com a regra do dia útil citada.
7. Relatório de retido sofrido e de outros municípios com totais por
   município que conferem com as notas.
8. Isolamento entre escritórios e empresas e permissões (CLIENTE,
   PARALEGAL) na tela e na API.
9. Mutação: somar nota retida, trocar a competência pela emissão, ignorar a
   vigência da alíquota ou tratar campo ausente como zero derruba testes.
10. Não regressão completa; migrações aditivas em banco vazio e reversão.

## Divisão

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — campos de ISS, regra do município, alíquotas, regime, apuração, relatórios, API | `auxiliar-implementacao` (Haiku) em cópia isolada | `apps/fiscal/` (módulo novo `iss_municipal.py`, leitura de campos, modelos, migração, API), testes `test_dl076_*` |
| B — telas | `auxiliar-implementacao` (Haiku) | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

Migrações aditivas (tabelas novas). Reverter é reverter as migrações e o
commit; nenhum dado existente muda.
