# DL-020 — Consolidação pós-auditoria e as quatro regras confirmadas

**Estado:** planejada em 2026-09-15, logo após a integração da
[DL-017](DL-017-interface-da-contabilidade.md) na `main` (PR #19, `60cbcff`).

## Por que esta etapa existe, e por que ela vem antes da DL-010

A DL-017 foi **aprovada com ressalvas** na sexta rodada. Dez ressalvas ficaram
nomeadas, e o Fred confirmou quatro regras contábeis que ainda não viraram
código. São catorze itens pequenos.

A razão de consolidar antes de começar a importação fiscal é **uma só**, e não é
perfeccionismo:

> **BL-198: um lançamento com a data errada não aparece em nenhuma tela de
> operação normal.** Nem Diário, nem Razão, nem Balancete, nem Conferência. O
> balancete do período **concilia**, então nenhuma conferência acusa. Para
> encontrar, o contador precisa suspeitar e alargar o período até o ano 9999.

É o único item aberto com essa característica: **o usuário não consegue conferir
o que não aparece**. Os outros treze são visíveis quando acontecem.

A segunda razão é de custo: o contexto está quente nos dois implementadores, e a
alternativa é reabrir estes arquivos no meio da DL-010. **Foi exatamente esse
padrão — mexer adiante deixando o vizinho aberto — que custou seis rodadas.**

E há um aviso concreto do auditor: as duas `CheckConstraint` de canonização de
CNPJ (BL-204) vazam `IntegrityError` cru por `bulk_create` — que é o caminho
natural de uma importação em lote. **A armadilha já está apontada para a
DL-010.**

## Objetivo

Fechar as catorze pendências sem abrir nenhuma nova, e deixar o sistema pronto
para a etapa fiscal começar em terreno limpo.

## ⚠️ Ordem obrigatória no BL-195 — leia antes de tocar no instrumento

O auditor mediu, 3 de 3, que **a correção óbvia reabre o bloqueador da rodada
5**:

1. Tirar o descarte do `--user-data-dir` da região julgada, nas **duas** funções.
2. Teste que force falha de limpeza e exija **pulo**, nunca `OSError`.
3. **Só então** rever o timeout de 10 s.

**Nunca (3) sem (1) e (2).** Subir o timeout sozinho faz a medição rodar, e a
mesma `ENOTEMPTY` estoura em `_renderizar_e_medir` **fora** do `except` dele.

## O que o dado já disse, e contraria o que todos nós supúnhamos

O `_DIAGNOSTICO_CHROMIUM` — acrescentado sem ninguém pedir — mostrou que **o
navegador do runner funciona**. `OSError(39, ENOTEMPTY)` não pode vir de
`subprocess.run`: vem do descarte do perfil, **depois** de o navegador rodar. O
outro job do mesmo commit acusa `timeout de 10s`, contra os **30 s** da medição
real.

Consequência: as duas medições de CSS por efeito **nunca rodaram na CI, em
nenhuma rodada**. Fechar o BL-195 é o que finalmente as faz rodar.

## As quatro regras confirmadas pelo Fred em 2026-09-15

| Requisito | Regra |
| --- | --- |
| **RC-77** | Data de lançamento entre **01/01/2000** e **hoje + 30 dias** |
| **RC-78** | Estorno **nunca** anterior ao lançamento que reverte — recusar |
| **RC-79** | Teto de **200** partidas, com recusa explícita e nunca truncamento |
| **RC-80** | Conta sem as contas-mãe: **avisar e deixar criar** |

Nenhuma é hipótese. As três que não eram de sim ou não foram reescritas como
proposta concreta antes de perguntar — presumir regra contábil é o que o
`AGENTS.md` proíbe.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` | `apps/core/**`, `apps/contabilidade/views.py`, `serializers.py`, `services.py`, `models.py` e migração, `apps/tenancy/**`, `apps/empresas/**`, e testes que **não** sejam `test_dl017_*`/`test_dl019_frontend*` |
| `especialista-frontend` | `apps/contabilidade/views_web.py`, `urls_web.py`, `templates/**`, `static/**`, `test_dl017_*`, `test_dl019_frontend*`, `docs/assets/telas/*.png` |
| `arquiteto-senior` | documentação, `.github/workflows/**`, e a costura |

**O ponto de encontro é o BL-196**, que atravessa as duas listas: a política dos
cinco dicionários precisa morar **num lugar só**. O `desenvolvedor-pleno` cria o
módulo em `apps/core/`; o `especialista-frontend` o aplica às duas telas.
Combinem a assinatura antes — vocês já fizeram isso duas vezes com bom
resultado.

## Uma armadilha conhecida no BL-207

Subir o teto de partidas para 200 **exige subir junto** o teto de segurança de
leitura. As duas constantes estão amarradas por uma verificação que reprova se
`LINHAS_MAXIMAS_LANCAMENTO >= LINHAS_LEITURA_TETO_DE_SEGURANCA` — instituída
pela BL-120 justamente para impedir que a perda silenciosa voltasse quando o
teto de negócio mudasse. **Ela vai reprovar, e isso é o mecanismo funcionando.**

## Critérios de aceite

Os critérios de cada item estão no
[backlog](../projeto/backlog.md), **BL-195 a BL-208**, escritos pelo **efeito
proibido** (DE-032) e cobrindo as outras superfícies (DE-034). Não os repito
aqui — repetir é como o `estado.md` divergiu três vezes.

Acrescento três que valem para a etapa inteira:

1. **Nenhum fato gravado fica invisível em todas as saídas de uso normal.** É o
   BL-198, e é a razão de a etapa existir.
2. **A DE-034 é percorrida item por item, por escrito, no relatório de entrega.**
   Ela tem três itens numerados; a rodada 6 executou dois, e o não executado foi
   onde ficou o maior resíduo. *Regra numerada que se cumpre por leitura vira
   regra cumprida em dois terços* — frase do auditor.
3. **As duas medições de CSS por efeito rodam na CI**, ou pulam com motivo
   declarado. Nunca falham.

## Riscos

- **BL-195 é o único item com ordem obrigatória**, e errar a ordem reabre um
  bloqueador já fechado. Está em letras grandes acima e no backlog.
- **BL-196 atravessa os dois responsáveis.** Duas implementações da mesma
  política é o risco que a DE-026 existe para impedir.
- **A tentação de aproveitar e mexer noutra coisa.** Esta etapa é consolidação:
  o escopo é fechar catorze itens, não melhorar o que já passou.

## Fora do escopo

DL-010 (importação fiscal), DL-016 (competência e fechamento), DL-018 (primeiro
acesso), BL-83 a BL-86, BL-02 (proteção da `main`, ação administrativa do Fred)
e o reparo de dado já gravado — se algum banco tiver `regime` fora do domínio ou
lançamento com data absurda, **validar a entrada não conserta o passado**, e a
migração de reparo não foi avaliada.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`, reiniciada
  a partir da `main` depois do PR #19.
- **Branch de destino:** `main`.

## ⚠️ Esta etapa se chamava DL-019, e foi renumerada — tabela de correspondência

**Duas sessões trabalharam em paralelo sem saber uma da outra**, e as duas
partiram do mesmo commit (`60cbcff`) usando o identificador **DL-019**: esta, de
consolidação da contabilidade, e a de portabilidade dos papéis de agente entre
ferramentas de IA, que entrou na `main` primeiro (PR #20, 2026-09-15 11:32Z).

A colisão foi detectada por duas vias independentes: pelo `arquiteto-senior`, ao
ensaiar a renumeração, e — **sem ter sido informado** — pelo `auditor-qa`, que a
mediu por `git ls-tree` e pela API de pedidos de integração e a registrou como
**achado D4** da [rodada 4](../auditorias/2026-09-15-dl-020-rodada-4.md).

O Fred autorizou renumerar **esta**, por ser a que ainda não estava integrada.

### O que mudou

| Antes | Agora |
| --- | --- |
| `DL-019` (consolidação pós-auditoria) | **`DL-020`** |
| `docs/auditorias/2026-09-15-dl-019-rodada-{1,2,3,4}.md` | `…-dl-020-rodada-{1,2,3,4}.md` |
| `BL-148` a `BL-193` | **`BL-195` a `BL-240`** (deslocamento de **+47**) |
| `DE-035` (regime errado se corrige apagando) | **`DE-039`** |

Para converter qualquer número citado nos relatórios: **some 47**. `BL-148` virou
`BL-195`; `BL-183` virou `BL-230`; `BL-193` virou `BL-240`.

### O que **não** mudou, e por quê

1. **O conteúdo dos quatro relatórios de auditoria.** Eles foram **renomeados**,
   nunca editados: seguem citando `BL-148` a `BL-193` e `DL-019`, que era a
   numeração vigente quando foram escritos. **Relatório de auditoria não se
   reescreve para caber em decisão posterior** — é para isso que esta tabela
   existe. Nenhum relatório, de nenhuma das duas etapas, foi descartado.
2. **O prefixo `test_dl019_*` dos arquivos de teste.** Renomeá-los faria os
   relatórios preservados apontarem para arquivos inexistentes, o que é pior que
   um prefixo desatualizado. Os arquivos `test_dl019_*` pertencem à etapa hoje
   chamada DL-020.

### ⚠️ Um QUINTO relatório foi editado, e eu havia declarado que nenhum fora

A seção acima diz que os quatro relatórios **desta** etapa foram renomeados e não
editados. **É verdade — e é incompleto.** A conferência de encerramento mediu que
o commit da renumeração (`e5d6db2`) também alterou **uma linha** de
`docs/auditorias/2026-09-15-dl-017-rodada-6.md`, que é relatório de auditoria de
**outra** etapa:

```
-Entram como **BL-148 a BL-157**.
+Entram como **BL-195 a BL-204**.
```

O script renumerava todo arquivo versionado fora da lista de intocáveis, e a
lista tinha só os quatro daqui. **A regra que eu mesmo escrevi — "relatório de
auditoria não se reescreve para caber em decisão posterior" — foi quebrada pelo
meu próprio mecanismo, e eu declarei o contrário sem conferir.**

**Por que o número novo fica**, em vez de eu reverter: aquele parágrafo é
encaminhamento operacional, e apontar para itens que já não existem com aquele
nome seria pior para quem for procurá-los. O que estava errado não era o número —
era **eu não ter declarado a edição**. Está declarado aqui.

A consequência mais séria estava no `backlog.md`, e foi corrigida: a frase levou o
mesmo deslocamento e passou a afirmar que **o corpo do PR #19 citava
`BL-195 a BL-204`**. Ele cita `BL-148 a BL-157`, e o corpo de um pedido de
integração já mesclado é **histórico público imutável** — o repositório afirmava
algo falso sobre ele. O auditor foi ler o PR pela API antes de me dizer isso.

**E havia mais duas, que eu encontrei ao corrigir estas:** o item que *descreve a
colisão* dizia "duas demandas **DL-020**" e "também chamada **DL-020**". As duas
se chamavam **DL-019**; foi esta que se moveu. A renumeração mecânica não
distingue **o que usa** um identificador do **que narra a história** dele, e o
segundo caso precisa de leitura humana. Fica como limite conhecido do método.

### A metade que o auditor viu e o arquiteto não

Os identificadores `BL-xxx` são citados **dentro do código de teste**, como
justificativa escrita de cada defesa, em dezenas de pontos. Sem renumerá-los
junto, eles passariam a apontar para itens de outra demanda — e, nas palavras
dele, *"essa metade é silenciosa: o Git não avisa"*. Os arquivos brigariam alto;
as citações, não. **A renumeração do código foi feita no mesmo passo**, por
substituição em duas fases com marcador intermediário, para nenhuma troca
reescrever outra.
