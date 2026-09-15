# DL-019 — Consolidação pós-auditoria e as quatro regras confirmadas

**Estado:** planejada em 2026-09-15, logo após a integração da
[DL-017](DL-017-interface-da-contabilidade.md) na `main` (PR #19, `60cbcff`).

## Por que esta etapa existe, e por que ela vem antes da DL-010

A DL-017 foi **aprovada com ressalvas** na sexta rodada. Dez ressalvas ficaram
nomeadas, e o Fred confirmou quatro regras contábeis que ainda não viraram
código. São catorze itens pequenos.

A razão de consolidar antes de começar a importação fiscal é **uma só**, e não é
perfeccionismo:

> **BL-151: um lançamento com a data errada não aparece em nenhuma tela de
> operação normal.** Nem Diário, nem Razão, nem Balancete, nem Conferência. O
> balancete do período **concilia**, então nenhuma conferência acusa. Para
> encontrar, o contador precisa suspeitar e alargar o período até o ano 9999.

É o único item aberto com essa característica: **o usuário não consegue conferir
o que não aparece**. Os outros treze são visíveis quando acontecem.

A segunda razão é de custo: o contexto está quente nos dois implementadores, e a
alternativa é reabrir estes arquivos no meio da DL-010. **Foi exatamente esse
padrão — mexer adiante deixando o vizinho aberto — que custou seis rodadas.**

E há um aviso concreto do auditor: as duas `CheckConstraint` de canonização de
CNPJ (BL-157) vazam `IntegrityError` cru por `bulk_create` — que é o caminho
natural de uma importação em lote. **A armadilha já está apontada para a
DL-010.**

## Objetivo

Fechar as catorze pendências sem abrir nenhuma nova, e deixar o sistema pronto
para a etapa fiscal começar em terreno limpo.

## ⚠️ Ordem obrigatória no BL-148 — leia antes de tocar no instrumento

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
nenhuma rodada**. Fechar o BL-148 é o que finalmente as faz rodar.

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

**O ponto de encontro é o BL-149**, que atravessa as duas listas: a política dos
cinco dicionários precisa morar **num lugar só**. O `desenvolvedor-pleno` cria o
módulo em `apps/core/`; o `especialista-frontend` o aplica às duas telas.
Combinem a assinatura antes — vocês já fizeram isso duas vezes com bom
resultado.

## Uma armadilha conhecida no BL-160

Subir o teto de partidas para 200 **exige subir junto** o teto de segurança de
leitura. As duas constantes estão amarradas por uma verificação que reprova se
`LINHAS_MAXIMAS_LANCAMENTO >= LINHAS_LEITURA_TETO_DE_SEGURANCA` — instituída
pela BL-120 justamente para impedir que a perda silenciosa voltasse quando o
teto de negócio mudasse. **Ela vai reprovar, e isso é o mecanismo funcionando.**

## Critérios de aceite

Os critérios de cada item estão no
[backlog](../projeto/backlog.md), **BL-148 a BL-161**, escritos pelo **efeito
proibido** (DE-032) e cobrindo as outras superfícies (DE-034). Não os repito
aqui — repetir é como o `estado.md` divergiu três vezes.

Acrescento três que valem para a etapa inteira:

1. **Nenhum fato gravado fica invisível em todas as saídas de uso normal.** É o
   BL-151, e é a razão de a etapa existir.
2. **A DE-034 é percorrida item por item, por escrito, no relatório de entrega.**
   Ela tem três itens numerados; a rodada 6 executou dois, e o não executado foi
   onde ficou o maior resíduo. *Regra numerada que se cumpre por leitura vira
   regra cumprida em dois terços* — frase do auditor.
3. **As duas medições de CSS por efeito rodam na CI**, ou pulam com motivo
   declarado. Nunca falham.

## Riscos

- **BL-148 é o único item com ordem obrigatória**, e errar a ordem reabre um
  bloqueador já fechado. Está em letras grandes acima e no backlog.
- **BL-149 atravessa os dois responsáveis.** Duas implementações da mesma
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
