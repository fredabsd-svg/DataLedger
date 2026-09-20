# DL-030 — A trilha cobre o admin

**Demanda:** autorização do Fred em 2026-09-20 — *"pode encaminhar o remendo da
trilha"* —, depois de eu medir que a razão social de uma empresa é **apagada no
ato** quando alguém a edita (**BL-435**), e que isso torna impossível o que o
**BL-396** exige do termo do livro.

**Responsável pelo produto:** Fred.
**Arquiteto:** `arquiteto-senior`.
**Fecha:** BL-435 **parcialmente** — e isso está no nome. Ver "O que esta etapa
NÃO é".

## Objetivo

**Parar a sangria.** Hoje, uma alteração contratual que muda a razão social
sobrescreve o valor anterior e ele **não fica em lugar nenhum**. Esta etapa faz
a trilha de auditoria do produto registrar o que muda pelo **admin do Django**,
com **valor antigo e valor novo**, para que o dado deixe de desaparecer.

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

**R1 — a cobertura é DERIVADA do registro do admin, não de uma lista nossa.**
Toda `ModelAdmin` registrada passa a gravar trilha em criação, alteração e
exclusão. Enumerar os modelos seria a décima sétima ocorrência da classe desta
semana ([DE-056](../projeto/decisoes.md)): a guarda tem de sair do **registro do
próprio framework**.

**R2 — a guarda da cobertura também é derivada.** Um teste anda por
`admin.site._registry` e **reprova** se qualquer `ModelAdmin` registrada não
estiver coberta. Modelo novo registrado amanhã entra **sozinho**, ou o build
fica vermelho — não há caminho em que alguém "esqueça".

**R3 — valor antigo e valor novo, por campo alterado.** Em alteração, gravar
**quais campos mudaram** e, para cada um, o valor **antes** e **depois**. O
`ModelForm` do admin já entrega isso (`form.changed_data`, `form.initial`,
`form.cleaned_data`) — não reimplemente comparação de objetos.

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

1. `POST` no `change` de `Empresa` alterando `razao_social` grava
   `RegistroAuditoria` com o valor **antigo** e o **novo**, e com o usuário que
   fez.
2. `POST` no `add` e no `delete` de `Empresa` gravam trilha.
3. **A prova do R2:** registrar uma `ModelAdmin` nova de mentira dentro do teste
   **sem** a cobertura faz o teste de varredura **reprovar**, nomeando-a.
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
