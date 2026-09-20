# DL-030 — A trilha cobre o admin

**Demanda:** autorização do Fred em 2026-09-20 — *"pode encaminhar o remendo da
trilha"*. ⚠️ **A justificativa que eu dei a ele estava ERRADA**, e a correção
está na seção seguinte. A etapa sobrevive à correção, com escopo revisto.

**Responsável pelo produto:** Fred.
**Arquiteto:** `arquiteto-senior`.
**Fecha:** os sete gaps medidos na tabela abaixo. **Não** fecha BL-396 nem
PE-60. **BL-435 deixou de ser achado e virou o registro do meu erro.**

## ⚠️ A premissa original deste plano estava ERRADA, e o erro era meu

**Escrito na primeira versão:** *"a razão social é apagada no ato e não fica em
lugar nenhum"*. **É falso.** A trilha **cobre** o admin desde a **DL-024/BL-244**
(`apps/auditoria/signals.py`, já mesclado), por **signal genérico**, e
`apps/core/tests/test_dl024_trilha_admin.py` prova exatamente o cenário que eu
disse não existir.

**A classe é a [DE-060](../projeto/decisoes.md), aplicada a mim:** rodei
`grep "registrar(" apps/empresas/admin.py`, não achei, e conclui *"a trilha não
cobre o admin"*. A **medição era literalmente verdadeira; a conclusão era
falsa** — medi um **substituto** no lugar da **propriedade**, sem declarar.
Registro em **BL-435**.

**O `desenvolvedor-pleno` achou isso medindo ANTES de escrever código**, porque
este plano mandava parar se a premissa não batesse. A regra pagou.

## Objetivo (revisto)

**A trilha existe. Fechar a lista, fechar os buracos, e provar o que está
apenas afirmado.** Sete gaps medidos contra os requisitos originais, em ordem de
gravidade:

| # | Gap medido | Por que importa |
| --- | --- | --- |
| 1 | **`escritorio` vem da SESSÃO, não do objeto** | Superusuário sem `VinculoUsuarioEscritorio` editando empresa do Escritório X grava `escritorio = None`. **A trilha perde o isolamento no perfil que mais usa o admin** |
| 2 | **`Usuario` sem cobertura nenhuma** | Alteração de senha pelo admin não deixa rastro |
| 3 | **`MODELOS_DA_TRILHA_DO_ADMIN` é uma tupla de seis** | O anti-padrão, na forma exata que a DE-056 descreve |
| 4 | **Atomicidade do admin afirmada em comentário, não medida** | DE-058, no arquivo que guarda a prova de quem alterou o quê |
| 5 | Inlines não provados pela mesma superfície | BL-211 |
| 6 | Nenhuma declaração DE-060 nas medições | — |
| 7 | O teste da cobertura é **retrato**, não propriedade | Vira o item 3 |

## Duas decisões minhas, e as duas são RETRATAÇÕES

**1. Fica o signal; NÃO se troca por `save_model`.** O signal cobre **qualquer
caminho de escrita** — admin, API, shell, comando de gerência, migração. O
`save_model` cobre **só o admin**. Trocar estreitaria a garantia em troca de um
diff mais limpo, e este projeto erra para o lado seguro.

**2. O requisito R3 está RETIRADO, e era meu erro.** Eu havia escrito *"não
reimplemente comparação de objetos; use `form.changed_data`"*. **O inverso é que
é verdade:** a linha do banco **antes e depois** é o **estado realmente
persistido** — a propriedade. O `form.initial` é a **visão que o formulário tem**
dela, e diverge quando um campo está fora do formulário, quando há edição
concorrente entre o `GET` e o `POST`, ou quando o `save()` do modelo altera
valor. **Quem media o substituto era o meu requisito, não o código.**

⚠️ **E o R1 muda junto:** eu havia mandado derivar a cobertura de
`admin.site._registry`. **Estreito demais**, pelo mesmo motivo — o mecanismo
cobre caminhos que não passam pelo admin. **Inverta para o lado seguro**, como no
BL-415: cobrir **todo modelo concreto dos apps do projeto**, com uma lista
**pequena** do que fica de fora, motivo escrito por item, e o `RegistroAuditoria`
como o primeiro dela (senão a trilha audita a si mesma em laço).

## O que esta etapa NÃO é

Escrevo isto primeiro porque a honestidade do escopo é metade da entrega.

1. **NÃO é o histórico com vigência que o BL-396 vai precisar.** Para imprimir o
   termo do livro com o cadastro **como era na data**, o certo é um
   `HistoricoCadastralEmpresa` no molde do `HistoricoRegimeTributario` — modelo
   próprio, consultável **por data**. Isso depende da **PE-60**, que tem uma
   metade normativa que eu ainda **não levantei** em fonte oficial.
2. **NÃO fecha o BL-244, o BL-14, o BL-16 nem o BL-57.** A trilha completa —
   atomicidade garantida em toda porta, resistência a adulteração, cobertura dos
   caminhos que não passam pelo admin — continua sendo o **pacote 3** da fila.
3. **NÃO promete que o dado antigo é recuperável em forma de cadastro.** Ele fica
   em `detalhes`, num registro de auditoria: é **prova de que existiu e qual
   era**, não um campo de onde o produto lê.

⚠️ **O valor desta etapa é exatamente esse, e é grande:** depois dela, a
informação **existe**. Antes dela, não existia.

## Requisitos

**R1 — a cobertura sai de uma PROPRIEDADE, e a propriedade NÃO é o registro do
admin.** `MODELOS_DA_TRILHA_DO_ADMIN` é hoje uma tupla de seis, e isso é o
anti-padrão ([DE-056](../projeto/decisoes.md)). **Inverta para o lado seguro**,
como no BL-415: cobrir **todo modelo concreto dos apps do projeto**, com uma
lista **pequena** do que fica **de fora**, motivo escrito **por item**, e o
`RegistroAuditoria` como o primeiro dela — senão a trilha audita a si mesma em
laço. ⚠️ **`admin.site._registry` foi descartado como fonte**, e o motivo é o
mesmo do R3: o mecanismo é um **signal**, que cobre caminhos que não passam pelo
admin; derivar do registro do admin seria **estreitar** a garantia.

**R2 — a guarda da cobertura também é derivada.** Um teste anda pelos modelos
concretos do projeto e **reprova** se algum ficar sem cobertura e sem exceção
escrita. Modelo novo amanhã entra **sozinho**, ou o build fica vermelho — não há
caminho em que alguém "esqueça".

**R3 — RETIRADO, e o erro era meu.** O texto original dizia *"use
`form.changed_data`/`initial`/`cleaned_data`; não reimplemente comparação de
objetos"*. **O inverso é que é verdade:** a linha do banco **antes e depois** é o
**estado realmente persistido** — a propriedade. O `form.initial` é a **visão que
o formulário tem** dela, e diverge quando o campo está fora do formulário, quando
há edição concorrente entre o `GET` e o `POST`, ou quando o `save()` do modelo
altera valor. **Quem media o substituto era o meu requisito, não o código.** O
mecanismo atual — ler a linha anterior e comparar — **fica**.

**R4 — segredo nunca entra na trilha, e a regra é derivada do widget.** Campo
cujo widget seja de senha tem o valor **redigido** (o nome do campo entra, o
valor não). ⚠️ **Derivado do widget, não de uma lista de nomes de campo** — a
docstring do `RegistroAuditoria` já proíbe senha, token e documento pessoal
completo, e o `AGENTS.md` §11 também. **Declare no código o que a redação por
widget NÃO alcança** ([DE-056](../projeto/decisoes.md)).

**R5 — atomicidade (BL-14).** Gravação e trilha são **atômicas**: se a gravação
falhar, não sobra trilha; se a trilha falhar, não sobra gravação.

**R6 — escritório, para o isolamento valer na própria trilha.** Derivar o
escritório do objeto quando for derivável (`obj.escritorio`, `obj.empresa.
escritorio`, e o que mais existir **por inspeção do modelo**, não por lista).
**Declarar** o que acontece quando não for derivável.

**R7 — inlines contam.** `EstabelecimentoInline` edita estabelecimento pelo
mesmo formulário. `save_formset` entra no escopo.

**R8 — DE-060.** Cada medição declara, no código, se mede **a propriedade** ou um
**substituto** dela; quando for substituto, **de que diverge** e **a medição
dessa divergência** ao lado.

## Critérios de aceite

Todos **por requisição autenticada ao admin**, não por chamada direta de método
— é a lição do **BL-211**, e foi por não fazer isso que a BL-258 existiu.

1. **O gap 1, que é o mais grave:** `POST` no `change` de `Empresa` do
   Escritório X, feito por **superusuário sem `VinculoUsuarioEscritorio`**, grava
   `RegistroAuditoria.escritorio = ` **o escritório do objeto**, não `None`.
   ⚠️ **Hoje grava `None`** — a trilha perde o isolamento no perfil que mais usa
   o admin.
2. `POST` no `add`, no `change` e no `delete` de `Empresa` gravam trilha com
   valor antigo e novo (isto **já passa hoje**: é não-regressão, não construção).
3. **A prova do R2:** um modelo concreto novo, sem cobertura e sem exceção
   escrita, faz o teste de varredura **reprovar**, nomeando-o.
4. **A prova do R4:** alterar a senha de um usuário pelo admin grava o **nome**
   do campo e **não** grava o valor, nem o hash.
5. **A prova do R5:** gravação que falha por validação **não** deixa trilha.
6. Alteração por **inline** (estabelecimento) grava trilha.
7. A trilha continua **imutável**: `RegistroAuditoriaQuerySet` já fecha mutação
   em massa, e isso não regride.
8. Suíte inteira verde, `ruff check`, `ruff format --check`, `manage.py check`
   limpos, com os números declarados.

## Riscos declarados

- **Volume.** Toda edição administrativa passa a gerar registro. Medir quantos
  registros uma sessão típica gera e declarar; se for absurdo, **parar e avisar**
  antes de entregar.
- **Custo por requisição.** Medir o antes e o depois de um `POST` no `change`.
- **Campo grande.** Um `TextField` longo alterado põe duas cópias no JSON.
  Decidir e **escrever** o limite (truncar com marca explícita é aceitável;
  truncar em silêncio não é).

## Divisão de arquivos

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| DL-030 | `desenvolvedor-pleno` | `apps/auditoria/**`, `apps/*/admin.py`, testes correspondentes |
| DL-029 rodada 2 (em curso) | `desenvolvedor-pleno` | `scripts/**` |
| Documentação | `arquiteto-senior` | `docs/**` |
| Auditoria | `auditor-qa` | Nada — audita a versão integrada |

**Proibido:** `scripts/**` (está com outra frente **agora**), `templates/**`,
`static/css/base.css`, e **qualquer migração que apague dado**.

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano. A etapa
não se declara fechada sem auditoria da versão integrada
([DE-054](../projeto/decisoes.md)).
