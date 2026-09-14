# Decisões do DataLedger

Registro das decisões arquiteturais e de processo, com a justificativa e o que
foi descartado. Uma decisão só entra aqui depois de tomada; alternativa ainda
em estudo pertence a [requisitos.md](requisitos.md) como hipótese ou pendência.

Formato: identificador, data, decisão, motivo, alternativas descartadas e
consequência.

## DE-001 — Sessão principal roda como `arquiteto-senior`

**Data:** 2026-09-11

**Decisão:** a chave `agent` em `.claude/settings.json` aponta para
`arquiteto-senior`. Não existe um quinto papel de líder.

**Motivo:** o Fred quer conversar principalmente com o líder técnico. Fazer da
sessão principal o próprio arquiteto elimina uma camada de intermediação e
garante que quem responde ao Fred é quem detém o contexto de arquitetura.

**Alternativas descartadas:** um agente coordenador separado acima dos quatro
papéis — acrescentaria repasse de contexto sem ganho, e o Fred pediu
explicitamente que não houvesse um quinto líder.

**Consequência:** a sessão precisa ser reiniciada para que a chave `agent`
tenha efeito. Ver [docs/agents/estado.md](../agents/estado.md).

## DE-002 — Modo de exibição dos integrantes: `in-process`

**Data:** 2026-09-11

**Decisão:** `teammateMode` igual a `in-process`.

**Motivo:** funciona em qualquer terminal, sem depender de tmux ou iTerm2, e é
o padrão da plataforma desde a versão 2.1.179. O ambiente remoto deste projeto
não garante um terminal com painéis divididos.

**Alternativas descartadas:** `auto` e `tmux`, que abrem painéis divididos —
exigem tmux ou iTerm2 com o utilitário `it2`, e falham silenciosamente para
`in-process` quando indisponíveis.

**Consequência:** integrantes aparecem no painel abaixo do campo de entrada da
sessão principal. Subagente de integrante roda em primeiro plano.

## DE-003 — Profundidade de aninhamento de subagentes igual a 2

**Data:** 2026-09-11

**Decisão:** `CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH` igual a `"2"`.

**Motivo:** permite que os quatro papéis acionem um auxiliar, e impede que o
auxiliar acione outro. É a camada de profundidade exatamente necessária ao
desenho da equipe.

**Alternativas descartadas:** `1` desligaria o aninhamento e impediria os
papéis de delegar; `3` ou mais abriria cadeias longas de delegação, difíceis de
auditar e de custo imprevisível.

**Consequência:** combinada com a ausência da ferramenta `Agent` nos três
auxiliares, há **duas** barreiras contra delegação em cadeia: uma por
profundidade e outra por ferramenta.

## DE-004 — Independência do auditor por ferramenta, não por promessa

**Data:** 2026-09-11

**Decisão:** `auditor-qa` não recebe `Write`, `Edit` nem `NotebookEdit`, e não
recebe memória automática de projeto. Os relatórios são registrados em
`docs/auditorias/` pelo `arquiteto-senior`.

**Motivo:** a independência da auditoria precisa de barreira técnica, não
apenas de instrução. Memória automática criaria um diretório persistente de
escrita para o auditor, ampliando indevidamente seu alcance.

**Alternativas descartadas:** dar `Write` ao auditor restrito a
`docs/auditorias/` — a plataforma não restringe `Write` por caminho na
definição do agente, então a restrição seria apenas verbal.

**Consequência conhecida e assumida:** o auditor mantém `Bash`, porque precisa
executar testes. **Terminal permite escrita mesmo sem `Write`/`Edit`.** Logo, a
independência do auditor é **parcialmente técnica e parcialmente
comportamental**, e isso está documentado como tal em
[docs/agents/equipe.md](../agents/equipe.md). Mitigação: inspecionar scripts
antes de executar, evitar comandos que reescrevem arquivos, e conferir
`git status` e `git diff --stat` após os testes.

## DE-005 — Restrição de delegação do auditor é comportamental

**Data:** 2026-09-11

**Decisão:** a regra "o auditor delega apenas a `auxiliar-pesquisa` e
`auxiliar-verificacao`" fica registrada como instrução de comportamento no
prompt do agente e em [docs/agents/equipe.md](../agents/equipe.md).

**Motivo:** a sintaxe `Agent(tipo)` só funciona como lista de permissão para um
agente rodando como **thread principal**. Dentro de uma definição de subagente,
listar `Agent` permite delegar e a lista entre parênteses é **ignorada** pela
plataforma.

**Alternativas descartadas:** usar `permissions.deny` com
`Agent(auxiliar-implementacao)` — a regra valeria para a sessão inteira e
bloquearia também o `desenvolvedor-pleno` e o `especialista-frontend`, que
legitimamente precisam desse auxiliar.

**Consequência:** a restrição é real como instrução e frágil como garantia.
Está declarada honestamente em vez de apresentada como isolamento de segurança.

## DE-006 — CLAUDE.md enxuto, AGENTS.md como fonte das regras

**Data:** 2026-09-11

**Decisão:** o `AGENTS.md` já existente continua sendo a regra obrigatória de
desenvolvimento. O `CLAUDE.md` criado é um resumo operacional que aponta para
ele e prevalece o `AGENTS.md` em caso de conflito.

**Motivo:** o repositório já tinha um documento de regras maduro, de 285
linhas, citado pelo README e pelo modelo de pull request. Duplicá-lo criaria
duas fontes divergentes.

**Alternativas descartadas:** mover as regras para `CLAUDE.md` — quebraria
referências existentes e o hábito já estabelecido no projeto.

**Consequência:** agentes leem `CLAUDE.md` automaticamente e são direcionados
ao `AGENTS.md` antes de qualquer edição.

## DE-012 — Caminho fixo para o CSS, e `collectstatic` na integração contínua

**Data:** 2026-09-12

**Quem decidiu:** `arquiteto-senior`, a partir de achado do
`especialista-frontend` na DL-009.

**O problema encontrado:** `STORAGES["staticfiles"]` usa
`whitenoise.storage.CompressedManifestStaticFilesStorage` — decisão anterior ao
trabalho desta etapa. Esse backend **exige o manifesto** gerado por
`collectstatic`. Usar `{% static %}` em template **quebrava a suíte inteira**,
porque nem o `pytest` nem a integração contínua executavam `collectstatic`.

Ou seja: o projeto configurou um pipeline de estáticos que **nunca foi
exercido**. A falha só apareceria no deploy.

**Decisão, em três partes:**

1. **`collectstatic --noinput` roda na integração contínua**, **depois** do
   `pytest`. A ordem é deliberada: se rodasse antes, o manifesto existiria
   durante os testes e a CI passaria com `{% static %}` enquanto o `pytest`
   local (sem manifesto) falharia. CI mais permissiva que o ambiente local
   mascara defeito em vez de revelar.
2. **`collectstatic` roda também no `Dockerfile`**, antes de trocar de usuário.
   Ver a correção abaixo — esta parte **faltava** na primeira versão desta
   decisão.
3. **O `base.html` referencia o CSS por caminho fixo** (`/static/css/base.css`),
   não por `{% static %}`, para que a suíte de testes não dependa do manifesto.

### Correção desta decisão — a limitação declarada estava errada

A primeira versão desta decisão afirmava que o caminho fixo "funciona em
produção" e declarava como **única** limitação a perda de *cache busting*.
**Estava errado, e o erro era do `arquiteto-senior`.**

A auditoria da DL-009 verificou o caminho de deploy real e encontrou o seguinte:
o `Dockerfile` copiava o código e chamava `gunicorn` **direto**, e
`staticfiles/` está no `.gitignore` — logo **não vinha pelo `COPY` e não era
gerada na imagem**. Com `DEBUG=False`:

- `/static/css/base.css` devolveria **404**;
- o **admin do Django quebraria**, porque ele usa `{% static %}` e levantaria
  `ValueError: Missing staticfiles manifest entry`.

Ou seja: acrescentar o passo só à integração contínua verificava o pipeline e
**não corrigia o deploy**. A imagem subiria e falharia em uso real. A perda de
*cache busting* era, de longe, a menor das limitações — e o WhiteNoise ainda
aplica `max-age=60` a arquivo sem hash, o que reduz mais o peso dela.

Corrigido: `collectstatic` passa a rodar no `Dockerfile`. Verificação exigida
antes de considerar fechado: `docker build` seguido de `GET
/static/css/base.css` com `DEBUG=False` devolvendo **200**.

**Limitação que permanece, agora declarada corretamente:** o caminho fixo perde
o *cache busting* — o nome do arquivo não muda quando o conteúdo muda, então um
navegador pode servir CSS velho por até o tempo de cache após um deploy. Hoje
existe um único arquivo CSS e nenhum público em produção. **Não é a solução
final**; ver BL-45.

**Alternativas descartadas:**

- *Trocar para um backend de estáticos sem manifesto*: perderia compressão e
  versionamento em produção para resolver um problema de ambiente de teste.
  Consertar o teste é mais barato que rebaixar a produção.
- *Rodar `collectstatic` antes do `pytest` também localmente*: acrescenta passo
  obrigatório e lento a cada execução de teste, para um ganho que hoje é nulo.

**Encaminhamento:** quando houver mais de um arquivo estático, ou público real
em produção, voltar a `{% static %}` com `collectstatic` também no caminho de
teste. Registrado no backlog como BL-45.

## DE-011 — CSS próprio e mínimo; nenhuma biblioteca visual externa

**Data:** 2026-09-12

**Quem decidiu:** `arquiteto-senior`, fechando o item BL-26.

**Decisão:** a interface recebe **um arquivo CSS próprio e enxuto**, servido pelo
`staticfiles` que já está configurado. **Nenhuma** biblioteca ou framework visual
externo entra no projeto nesta etapa.

**Motivo:**

1. O projeto já decidiu templates renderizados no servidor, sem framework de
   JavaScript — decisão documentada no próprio código
   (`apps/tenancy/views.py`), que registra que HTMX ou Alpine entram "quando
   houver necessidade real de atualização parcial". Um framework CSS pesado
   contradiria essa escolha sem necessidade demonstrada.
2. O usuário é contador em rotina de produção: precisa de **densidade,
   legibilidade e previsibilidade**. Tabela legível, valor alinhado à direita e
   foco visível resolvem mais que um sistema de design completo.
3. O [AGENTS.md](../../AGENTS.md) §8 exige avaliar manutenção, licença,
   segurança e **necessidade** de cada nova dependência. Hoje não existe uma
   única tela de negócio consolidada — não há evidência que justifique a
   dependência.
4. A decisão é **reversível**: um CSS próprio pequeno não impede adotar
   biblioteca depois, quando houver telas suficientes para saber o que se
   precisa.

**Alternativas descartadas:** Bootstrap, Tailwind ou similar. Não por demérito
técnico, mas por **prematuridade**: escolher sistema visual antes de existirem
telas reais é decidir sem informação, e o custo de trocar depois recai sobre
marcação já escrita.

**Consequência:** a interface fica sóbria e propositalmente simples. Quando
houver telas de escrituração e relatório de verdade, a decisão será reavaliada
com evidência, em decisão própria.

## DE-010 — Arredondamento é explícito por regra; não existe padrão global

**Data:** 2026-09-12

**Quem decidiu:** `arquiteto-senior`, por delegação expressa do Fred, após
pesquisa em fontes normativas brasileiras.

**Decisão:** o DataLedger **não terá** uma política global de arredondamento.
Toda operação que reduza casas decimais **DEVE** declarar explicitamente a
política aplicada, e o motor de cálculo **DEVE** registrar qual política usou na
memória de cálculo.

### Por que não existe resposta única

A pesquisa mostrou que a legislação brasileira exige **métodos diferentes para
obrigações diferentes**. Uma política global estaria errada em algum tributo,
necessariamente:

| Obrigação | Método exigido | Fonte |
| --- | --- | --- |
| ICMS, casos gerais | **Arredondamento** a 2 casas pela ABNT NBR 5891 | Convênio ICMS 85/2001, cláusula 27, X, "b" |
| Combustíveis | **Truncamento** na 2ª casa | Convênio ICMS 85/2001, cláusula 27, X, "a"; Portaria DNC 30/1994; Resolução ANP 41/2013 |
| Retenções na EFD-Reinf | **Truncamento** na 2ª casa, sem arredondar; tolera arredondamento para maior até 1 centavo | Nota Orientativa RFB 01/2018 (eventos R-2010 a R-3010) |
| Folha e eSocial | **Truncamento** na 2ª casa, sem arredondamento | Manual de Orientação do eSocial |
| INSS | Lei não prevê arredondamento; duas casas mantidas | Orientação SEFIP |

E o risco de escolher errado **não é estético**: o **STJ** decidiu que cortar
casas decimais no cálculo do ICMS **caracteriza sonegação fiscal**, por ausência
de amparo legal para desconsiderar as decimais além da segunda (relator ministro
Humberto Martins). Ou seja, truncar onde a norma manda arredondar é infração —
e arredondar onde a norma manda truncar gera divergência com o validador
oficial.

### Política adotada

1. **Nunca `float`.** Somente `Decimal`, em toda cadeia de cálculo. Já era regra
   do [AGENTS.md](../../AGENTS.md) §10; fica reafirmada.
2. **Sem padrão implícito.** A função de quantização **exige** a política como
   argumento obrigatório. Não existe valor por omissão, justamente para que
   ninguém arredonde por acidente.
3. **Políticas nomeadas**, cada uma amarrada à sua fonte:
   - `ABNT_NBR_5891` — meio para o par (*banker's rounding*). Corresponde
     exatamente a `ROUND_HALF_EVEN` do `decimal` do Python: quando o dígito
     seguinte é 5 seguido só de zeros, vai para o par mais próximo; quando é 5
     seguido de algarismo diferente de zero, sobe.
   - `MEIO_PARA_CIMA` — `ROUND_HALF_UP`. Para regras que exijam
     explicitamente esse comportamento.
   - `TRUNCAR` — descarta as casas excedentes, sem olhar o valor
     (`ROUND_DOWN`, em direção a zero).
4. **Não arredondar intermediários.** O cálculo corre em precisão alta e
   arredonda **apenas na fronteira declarada** pela regra. Arredondar etapa a
   etapa acumula erro e é o caminho mais comum para relatório que não concilia.
5. **Rastreabilidade.** A memória de cálculo registra política, escala e valor
   antes e depois. Sem isso o resultado não é reproduzível, o que contraria o
   §10 do AGENTS.md.

### Refinamento: o critério é perda de informação, não contagem de dígitos

Acrescentado em 2026-09-12, durante a implementação da DL-008, a partir de uma
dúvida levantada pelo `desenvolvedor-pleno` e decidida pelo `arquiteto-senior`.

A pergunta prática: `100,000` tem três casas decimais ou nenhuma?

**Decisão:** a validação de escala mede **casas decimais significativas**, não
dígitos escritos. O critério é se reduzir a escala **perde informação**:

- `Decimal("100.000")` reduzido a 2 casas resulta em `100,00` — **perda zero**.
  O zero à direita é forma de escrever, não precisão. É **aceito**.
- `Decimal("100.004")` reduzido a 2 casas perde o `4` — **informação real
  destruída**. É o mecanismo exato do achado 4. É **recusado**.

Recusar `100,000` seria rigor tipográfico, não proteção contábil, e produziria
falso positivo contra um cliente que não errou nada. Na prática a contagem
normaliza o valor (remove zeros à direita, sem alterar o valor numérico) antes
de medir o expoente — o que também resolve notação científica, onde contagens
baseadas em texto erram nas duas direções.

Consequência: `"100"`, `"100.0"` e `"100.000"` são o mesmo valor para todos os
efeitos, inclusive para a comparação de impressão digital da idempotência
(DE-009). Isso foi descoberto porque a primeira implementação, com contagem
literal, quebrou um teste de idempotência já existente da DL-007 — e o teste
estava certo.

### Escrituração manual: recusar, não arredondar

Decisão específica e deliberada para o módulo de Contabilidade, que é o único
implementado: ao receber um lançamento com **mais casas decimais do que a escala
da conta**, o sistema **recusa** a requisição (400). Ele **não** arredonda em
silêncio.

Motivo: o arredondamento silencioso é exactamente o que rompe a invariante
`débito = crédito`. O achado 4 da auditoria de 2026-09-11 mostrou o mecanismo —
a igualdade era conferida **antes** do arredondamento do banco, então
`100,004 + 100,004` contra `200,00` passava na checagem e gravava desbalanceado.
Arredondar na entrada apenas moveria o problema; recusar resolve.

Arredondamento é atribuição dos **motores de cálculo** (fiscal, folha,
honorários), onde existe uma regra legal que diz qual método usar. Não é
atribuição do lançamento manual, onde quem digita já deveria ter o valor final.

### Alternativas descartadas

- *Padrão global `ROUND_HALF_UP` em duas casas*: simples e errado. Divergiria do
  validador oficial em folha, eSocial e EFD-Reinf, que truncam.
- *Padrão global de truncamento*: divergiria do ICMS e, pelo entendimento do
  STJ, poderia caracterizar sonegação.
- *Arredondar a entrada do lançamento manual*: romperia `débito = crédito`, como
  o achado 4 demonstrou.

### Limites desta decisão, declarados

Esta decisão define **engenharia**: como o sistema representa, arredonda e
rastreia valores. Ela **não** homologa o tratamento tributário de nenhuma
obrigação específica.

A tabela acima foi levantada em fontes secundárias e no comunicado oficial da
EFD-Reinf; a edição vigente da ABNT NBR 5891 aparece como `:1977` no Convênio
ICMS 85/2001 e como `:2014` em fontes técnicas. **Antes de qualquer cálculo
fiscal destinado a uso real**, a regra aplicável e a edição da norma devem ser
conferidas no texto oficial e validadas pelo Fred, como responsável técnico —
conforme o §10 do AGENTS.md, que exige casos de referência e validação
profissional. Nenhuma alíquota, prazo ou leiaute foi inventado aqui.

## DE-008 — Invariante contábil nunca mora só em `Model.clean()`

**Data:** 2026-09-12

**Decisão:** toda invariante contábil deve ser imposta em **pelo menos um**
destes lugares, nesta ordem de preferência:

1. **Restrição de banco** — a mais forte: sobrevive a shell, ORM, admin e
   corrida entre requisições.
2. **Camada de serviço** (`services.py`) — para regra que envolve várias linhas
   ou exige bloqueio transacional.
3. **Serializer** — na fronteira da API, para validar o que o cliente enviou.

`Model.clean()` continua existindo, mas **apenas como conveniência para o Django
admin e formulários**. Nunca como única defesa.

**Motivo:** é a causa raiz comum dos dois achados bloqueadores da auditoria de
2026-09-11. **O Django REST Framework não executa `full_clean()`**, e
`Model.objects.create()` também não. Logo, regra escrita apenas em
`Model.clean()` ou em validador de campo é **decorativa** no caminho da API —
exatamente o caminho que o produto usa. Foi assim que `conta_pai` pôde apontar
para conta de outra empresa apesar de existir um `clean()` proibindo isso.

**Alternativas descartadas:**

- *Chamar `full_clean()` dentro de `Model.save()`*: resolveria de forma ampla,
  mas altera o comportamento de todo o projeto de uma vez, inclusive de código
  e testes já validados, com risco desproporcional a esta etapa. Pode ser
  reconsiderado depois, como decisão própria e com regressão completa.
- *Confiar apenas em `CheckConstraint`*: não expressa a regra de `conta_pai`,
  porque a condição compara empresa da conta com empresa da conta pai — a
  verificação atravessa linhas, e o PostgreSQL exigiria um gatilho.

**Consequência:** a regra de `conta_pai` fica na camada 3 (serializer), e o
`clean()` é mantido para o admin. A unicidade do estorno fica na camada 1
(restrição de banco), reforçada na camada 2 (serviço, com bloqueio). Aceita-se
que o acesso por shell consegue contornar a camada 3 — posição já adotada pelo
projeto e registrada como tal.

## DE-009 — Idempotência por chave explícita, nunca por semelhança

**Data:** 2026-09-12

**Decisão:** a proteção contra duplicidade na criação de lançamento usa uma
chave enviada pelo cliente (cabeçalho `Idempotency-Key`), **opcional**. Não há
dedução automática de duplicidade por chave natural.

**Motivo — e este é um motivo contábil, não técnico:** em contabilidade, **dois
lançamentos idênticos no mesmo dia podem ser inteiramente legítimos**. Duas
taxas de mesmo valor, dois recebimentos iguais, dois honorários do mesmo
contrato. Recusar o segundo por parecer duplicado corromperia a escrituração
**por omissão** — e falta de lançamento é pior que lançamento duplicado, porque
o duplicado aparece na conciliação e o ausente não.

**Alternativas descartadas:** deduzir duplicidade por empresa + data +
histórico + itens. Rejeitada pelo motivo acima. Também rejeitada a chave
obrigatória, que quebraria o contrato atual sem necessidade.

**Consequência:** a garantia só existe quando o cliente envia a chave. A
interface, quando tiver tela de lançamento, **deverá** enviá-la. Registrado no
backlog. Até então, a proteção fica disponível e não imposta — e isso está
declarado, não escondido.

## DE-007 — Ambiente de desenvolvimento exige Python 3.12 ou superior

**Data:** 2026-09-11

**Decisão:** registrar que o projeto não instala em Python 3.11.

**Motivo:** verificado nesta máquina. `requirements/base.txt` fixa
`Django==6.1.1`, que exige `Requires-Python >=3.12`. O `python3` padrão do
contêiner é 3.11.15, e a instalação falha com "No matching distribution found
for Django==6.1.1". Com `python3.13` a instalação conclui e a suíte roda.

**Alternativas descartadas:** rebaixar o Django para uma versão compatível com
3.11 — contraria o `pyproject.toml`, que já define `target-version = "py314"`,
e a integração contínua, que usa Python 3.14.

**Consequência:** quem for rodar o projeto localmente precisa de Python 3.12+.
Isso deve ser documentado no README como pré-requisito — pendência registrada
no [backlog](backlog.md).

## DE-013 — Máscara de CNPJ é aceita só no leiaute exato

**Data:** 2026-09-12

**Decisão:** `normalizar_cnpj` reconhece a máscara **apenas** no formato
`XX.XXX.XXX/XXXX-XX`. Qualquer outra combinação de `.`, `/` ou `-` é caractere
inválido, não separador a descartar.

**Motivo:** a primeira implementação removia esses três caracteres **de
qualquer posição**. A auditoria da DL-011 (achado 6 da rodada 1) mostrou o
efeito: `"../-11222333000181"` e `"11222333000181."` eram **aceitos**, porque
depois da remoção cega sobravam 14 caracteres por coincidência. Remoção cega é
tolerância que não distingue erro de digitação de entrada absurda.

**Alternativas descartadas:**

- **Manter a remoção cega.** Aceita entrada sem sentido e, pior, aceita-a em
  silêncio — o usuário nunca descobre que digitou errado.
- **Recusar máscara por completo**, exigindo só os 14 caracteres. Contraria o
  hábito universal de digitar CNPJ mascarado no Brasil e contraria o critério 7
  do plano.

**Consequência, e é a parte que importa:** a regra é mais restritiva do que a
letra da NT 2025.001, que fala em "remover os caracteres de máscara". Para
**digitação humana** isso é acerto. Para **entrada automatizada** é risco
declarado:

> Arquivo de terceiro que traga CNPJ com separação parcial — por exemplo
> `11222333/0001-81` — **será recusado** na importação da
> [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md).

A DL-010 **não deve** presumir que o validador aceita qualquer pontuação. Se um
formato de origem real usar separação parcial, a decisão é nova: normalizar na
borda do importador, ou ampliar esta regra com justificativa. O que não pode é
ser resolvido em silêncio dentro do validador.

**Fonte:** NT Conjunta 2025.001 v1.00, de 25/04/2025 (ENCAT); IN RFB nº 2.229,
de 15/10/2024. Vigência do CNPJ alfanumérico: desde 31/07/2026.

## DE-014 — Implantação em nuvem, servidor único, banco compartilhado

**Data:** 2026-09-12

**Decisão do Fred**, registrada pelo `arquiteto-senior`: o DataLedger roda **na
nuvem**, em servidor único, acessado por navegador. Dimensionamento alvo: **cerca
de 50 usuários simultâneos** (RC-48 e RC-49).

Complementa o que a arquitetura já havia fixado, e que agora fica explícito:
**um banco de dados compartilhado**, com isolamento por `Escritorio` dentro
dele — não um banco por cliente.

**Motivo da nuvem, e é contábil antes de ser técnico:** prazo de obrigação
acessória não perdoa. Com servidor no escritório, falha de máquina no dia 15 é
problema do escritório, e o prazo não muda. Na nuvem, disponibilidade e cópia de
segurança são responsabilidade contratada de quem faz isso em escala. Soma-se o
acesso remoto, que deixou de ser conveniência.

**Motivo do banco compartilhado:** com um banco por empresa cliente, cada
atualização, cada cópia de segurança e cada conferência se multiplicariam pelo
número de clientes, e qualquer relatório de carteira exigiria consultar dezenas
de bancos. O custo dessa escolha é que **o isolamento passa a ser
responsabilidade do software**, não do sistema de arquivos — por isso é o ponto
mais auditado do projeto, a cada etapa, por execução e não por promessa.

**Alternativas descartadas:**

- **Servidor no escritório.** Funciona sem internet e tem custo previsível, mas
  transfere ao escritório a responsabilidade por energia, cópia de segurança,
  segurança e recuperação, e impede acesso remoto. Seria a escolha correta se a
  internet do escritório fosse instável — o Fred confirmou que não é o caso.
- **Nuvem com contingência local.** Mais caro e mais complexo. Só se justifica
  se parar uma tarde for inaceitável.
- **Um banco por cliente.** Ver acima.

## Consequências de engenharia, que não são opcionais

Esta decisão **cria obrigações**. Registradas aqui para não virarem descoberta
tardia:

| # | Obrigação | Backlog |
| --- | --- | --- |
| 1 | **Cópia de segurança com restauração testada.** Banco único significa que o escritório inteiro para junto se ele se perder. Cópia nunca restaurada em teste não é cópia, é esperança. | BL-33, elevado a P0 |
| 2 | **Tornar impossível subir sem PostgreSQL.** Hoje, sem `DATABASE_URL` configurada, o sistema cai silenciosamente em SQLite, que não suporta escrita concorrente de 50 pessoas. Falharia em uso, não na instalação. | BL-50 |
| 3 | **Tráfego cifrado (HTTPS) e cabeçalhos de segurança.** Com acesso pela internet, senha e dado de cliente em claro é inaceitável. | BL-51 |
| 4 | **Processamento em segundo plano.** Importar milhares de XMLs não pode acontecer dentro de uma requisição web: estoura tempo limite, prende trabalhador do servidor e derruba a experiência dos outros 49 usuários. | BL-52 |

A quarta é a que mais muda projeto: **a [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) deixa de ser só um leitor de arquivo e passa a exigir fila de tarefas**, com acompanhamento de progresso e resultado consultável depois.

**Sobre dimensionamento, com honestidade:** 50 usuários simultâneos é carga
modesta para Django com PostgreSQL, e não é o que preocupa. O que preocupa é a
importação em lote, e **isso só se dimensiona medindo**, com um lote real do
escritório (PE-17). Não afirmo desempenho que não medi.

**Pendência que esta decisão abre:** dado de cliente em nuvem envolve
**residência do dado e LGPD**. Registrado como PE-25, para decisão do Fred junto
ao provedor.

## DE-015 — Tarefas em segundo plano: contrato do Django, banco como armazenamento

**Data:** 2026-09-13

**Decisão:** programar contra **`django.tasks`**, o contrato oficial do Django
desde a 6.0 (DEP 0014), e adotar **`django-tasks-db`** como backend, que
armazena a fila no **PostgreSQL que já temos**. Fecha o **BL-52**.

Nenhuma peça nova de infraestrutura: sem Redis, sem RabbitMQ.

### O que foi medido, e não suposto

A pesquisa levantou os candidatos; a verificação **executou** os dois finalistas
em ambientes descartáveis, com Django 6.1.1 e PostgreSQL 16. Três resultados
mudaram a decisão:

**1. O argumento que eu considerava decisivo não distingue os candidatos.**

Eu havia escrito que a vantagem de uma fila no PostgreSQL seria enfileirar a
tarefa **na mesma transação** que grava o lote, eliminando a classe de defeito
"lote gravado sem tarefa" e "tarefa sem lote". A verificação mostrou que
**`procrastinate` e `django-tasks-db` se comportam de forma idêntica** nisso —
os dois gravam a fila na mesma conexão, e o `rollback` desfaz os dois juntos.
Testado com transação e exceção proposital: zero linhas em ambos.

É o comportamento correto, e é bom que exista. Mas **não serve para escolher**,
e usá-lo como critério teria sido decidir por um argumento que não discrimina.

**2. Nenhum dos dois se recupera sozinho da queda do trabalhador.**

Com `kill -9` no meio do processamento, os dois deixam a tarefa **presa para
sempre** — `doing` num, `RUNNING` no outro. Subir um trabalhador novo **não**
retoma nenhuma das duas.

Isso é o achado mais importante da verificação, e **elimina a ilusão de que a
escolha da biblioteca resolveria o problema**. Não resolve. Ver a consequência
de projeto abaixo.

**3. O custo em dependências é muito diferente.**

| | `django-tasks-db` | `procrastinate` |
| --- | --- | --- |
| Versão | 0.13.0 | 3.9.0 |
| Dependências novas | **2** | **7** |
| API | Contrato **oficial** do Django | Própria |
| Admin | Somente leitura | Com ações de repetir, cancelar e abortar |
| Recuperação manual de tarefa presa | **Nenhum caminho** além de SQL | Documentada (`shell`, admin) |

### Por que escolhi o menos capaz dos dois

Porque o critério não é "qual faz mais hoje", e sim **quanto custa estar
errado**.

- Se `django-tasks-db` (0.13.0, jovem) se mostrar imaturo, **trocamos o
  backend** e o nosso código **não muda** — ele fala `django.tasks`, que é o
  contrato do Django. Inclusive dá para migrar para um backend baseado em
  Celery ou Redis sem reescrever uma chamada.
- Se adotássemos `procrastinate` e precisássemos sair, seria **reescrever cada
  ponto de chamada**.

Essa assimetria decide. Amarrar-se ao contrato do framework, e não à
biblioteca, é o que mantém a decisão reversível.

As duas vantagens reais do `procrastinate` — admin com ação de repetir e
caminho de recuperação — **perdem peso** porque, pelo motivo da seção seguinte,
teremos tela e modelo próprios de lote de qualquer maneira. A recuperação que
importa ao contador não é "repetir a tarefa": é **retomar o lote do documento
3.412**, e isso nenhuma das duas entrega.

### Consequência de projeto, que é obrigatória e não opcional

> **A resiliência é nossa, não da fila.**

A [DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) precisa de um
modelo próprio de **lote de importação**, com:

1. **Progresso por documento**, para responder "3.412 de 5.000" e para retomar
   de onde parou.
2. **Sinal de vida** (o instante da última atividade), para que lote sem
   progresso há muito tempo seja **detectado**, não descoberto por acaso.
3. **Estado visível ao operador**, com motivo de recusa por documento.
4. **Idempotência pela chave de acesso**, que já é decisão da etapa e é o que
   torna **seguro reprocessar** um lote interrompido.

Com esses quatro itens, reprocessar um lote travado é uma operação inofensiva —
e é por isso que a fraqueza dos dois candidatos deixa de ser bloqueante.

**Sem eles, a etapa não pode ser dada como concluída**, por mais que a fila
funcione.

### Verificação que falta antes de fixar a dependência

Condição para entrar em `requirements/`:

- O ambiente de teste tinha apenas **Python 3.14.0rc2**; a integração contínua
  usa **3.14 final**. A instalação foi conferida na rc2, não no GA.
- Nenhum dos pacotes declara compatibilidade com **Django 6.1** nos
  classificadores — funcionou porque não há teto de versão, o que é diferente
  de suporte declarado.

**A própria CI fecha essa lacuna**: ao acrescentar a dependência, o *build* em
Python 3.14 passa ou não passa. Se não passar, esta decisão volta à mesa, e
`procrastinate` é o substituto imediato — trocar o backend não muda o código de
chamada, que é exatamente a propriedade pela qual escolhi assim.

### Alternativas descartadas

- **Celery.** Escolha óbvia de mercado, e a descarto com justificativa, não por
  hábito: exige Redis ou RabbitMQ, ou seja, mais uma peça para manter, cifrar e
  **fazer cópia de segurança à parte**. Pior, o documento fiscal passaria a
  existir, em trânsito, **fora do banco** que concentra o backup (BL-33) e a
  trilha de auditoria.
- **RQ e Dramatiq.** Mesma objeção: exigem Redis ou RabbitMQ.
- **`django-q2`.** Funciona sobre o ORM e evitaria infraestrutura nova, mas usa
  API própria, sem a reversibilidade do contrato oficial.
- **Rodar dentro da requisição.** É o que a DE-014 proíbe explicitamente.

### Custo que assumo, declarado

Um **processo trabalhador separado** ao lado do servidor web, supervisionado.
Isso é inerente ao problema, não da ferramenta: toda opção exige. Entra como
requisito do **BL-53**, o procedimento de implantação.

## DE-016 — Saída contábil exige período, e o contrato atual quebra

**Data:** 2026-09-13

**Decisão:** Razão e Balancete passam a **exigir** `inicio` e `fim`. Requisição
sem os dois recebe 400. É quebra deliberada do contrato que existe hoje.

### Por quê

Uma saída contábil sem período não é uma saída "geral": é uma resposta errada
com aparência de certa. O contador emite balancete de um mês, de um trimestre,
de um exercício — e o que o sistema devolve hoje é o acumulado desde o primeiro
lançamento da base, em uma coluna só. Quem não conferir contra o Diário não
percebe.

### Por que quebrar em vez de manter compatível

Um padrão opcional com valor-padrão "tudo" preserva exatamente o erro que
estamos corrigindo, e preserva-o no caminho mais fácil — o de quem não passa
parâmetro. Manter os dois comportamentos custaria testes dobrados para sustentar
o comportamento que não queremos.

O custo de quebrar é, hoje, **zero medido**: o sistema não está implantado, não
há cliente consumindo a API e a única consumidora seria a interface, que ainda
não existe (BL-62). Essa janela fecha assim que houver implantação real — e é
justamente por isso que a quebra é agora.

### Consequência

Registrada no contrato da [DL-015](../planos/DL-015-contabilidade-utilizavel.md),
com critério de aceite próprio: período ausente, malformado ou invertido devolve
400 com mensagem útil, nunca 500 nem período implícito.

## DE-017 — Alteração em massa: o Fred pediu, e ela preserva o original

**Data:** 2026-09-13

**Decisão:** implementar alteração em massa de lançamentos (RC-51). O
comportamento **depende do estado do período**:

| Situação do período | O que a alteração em massa faz |
| --- | --- |
| **Aberto** | Altera os lançamentos e grava a **versão anterior completa** numa trilha imutável. O Diário mostra só o lançamento corrigido. |
| **Encerrado** | Não altera. Gera **lançamento de ajuste** (estorno e relançamento) vinculado ao original, com motivo. |

### Por que não escolhi só um dos dois

Minha recomendação inicial, no [mapa funcional
contábil](mapa-funcional-contabil.md), era fazer **tudo** por estorno e
relançamento. Estava errada por excesso, e o pedido do Fred me obrigou a
examinar melhor.

Corrigir a classificação de 300 notas **antes de fechar o mês** não é um fato
contábil novo: é a correção de um erro de digitação. Transformar isso em 600
lançamentos a mais polui o Diário, e o livro passa a contar uma história que não
aconteceu. O contador que confere o razão vê três linhas onde houve um fato.

Já alterar lançamento de período **encerrado** é outra coisa: o balancete
daquele mês já foi entregue, a demonstração já foi assinada, e mudar o passado em
silêncio é exatamente o que a trilha de auditoria existe para impedir.

A regra do [AGENTS.md](../../AGENTS.md) §10 exige que a correção seja
**rastreável** — não exige que seja por estorno. Guardar a versão anterior
integralmente satisfaz a exigência e preserva a legibilidade do livro.

### O que isso exige, e por que não é a próxima tarefa

1. **Fechamento de período** (BL-11). Sem saber o que está encerrado, a regra
   acima não tem como ser aplicada — e a versão permissiva seria a que vale
   sempre. É pré-requisito, não detalhe.
2. **Versionamento do lançamento**: a versão anterior precisa ser guardada
   inteira (cabeçalho e partidas), com autor, data, motivo e o identificador da
   operação em lote que a originou.
3. A imutabilidade atual (`save()` levanta exceção) **não é removida**. A
   alteração passa a existir por um serviço explícito, que grava a versão
   anterior na mesma transação. Quem chamar `save()` direto continua sendo
   recusado — a proteção que a auditoria validou permanece.
4. A operação é **atômica e idempotente**: falha no meio não deixa metade dos
   lançamentos alterados, e repetir a mesma requisição não aplica duas vezes.

Alcance dos campos alteráveis: pendente de PE-35.

## DE-018 — Duas operações diferentes: regerar o derivado e apagar o original

**Data:** 2026-09-13. **Reescrita no mesmo dia**, depois de o Fred explicar o
caso de uso real (RC-59). A versão anterior tratava as duas como uma só e
partia de um receio que não se aplicava.

### O que eu tinha entendido errado

Eu li "eliminação de período" como apagar escrituração para reduzir volume, e
montei salvaguardas pesadas em cima disso: exportação verificada, inventário
permanente, dependência de restauração testada.

O que o Fred quer é outra coisa. As notas escrituradas no fiscal **geram** os
lançamentos da contabilidade. Se o plano de contas mudar no meio do ano, ele
precisa **apagar os lançamentos gerados e refazê-los** a partir das notas — que
continuam intactas. Não é destruição de dado: é **reconstrução de dado
derivado**, e a origem permanece.

A diferença é a mesma entre apagar um relatório e apagar os lançamentos que o
originaram. Um se refaz; o outro, não.

### Decisão: duas operações, com regras distintas

**1. Regeração de lançamentos derivados** — o que o Fred pediu.

| Regra | Motivo |
| --- | --- |
| Só alcança lançamento cuja **origem** seja um processo do sistema (escrita fiscal, folha), nunca lançamento manual | Lançamento manual não tem de onde ser refeito. Apagá-lo é perda definitiva |
| Só em **período aberto** (RC-57) | Período fechado não se mexe sem reabrir |
| **Não** alcança lançamento conciliado ou ajustado à mão, salvo autorização explícita | Levantado no mapa funcional: conciliação trava regeração |
| Apaga e refaz na **mesma transação** | Falha no meio não pode deixar o período sem lançamento nenhum |
| Registra na trilha: quem, quando, que período, quantos lançamentos saíram e quantos entraram | Rastro do que aconteceu, mesmo o resultado sendo equivalente |
| Idempotente | Rodar duas vezes produz o mesmo resultado, não o dobro |

**2. Eliminação de escrituração** — apagar dado sem origem de onde refazer.

Continua valendo tudo que a versão anterior exigia: só período encerrado,
exportação verificada antes de apagar com aborto em caso de falha, papel
autorizado com contagem e totais, inventário permanente, e **depois** de BL-33
(restauração testada). Não há demanda para isso hoje — fica registrado para não
ser confundido com a operação acima.

### Pré-requisito que isso revela, e que não existe hoje

O lançamento contábil precisa saber **de onde veio**: a origem (manual, escrita
fiscal, folha) e o **documento que o originou**. Sem isso, não há como
distinguir o que pode ser regerado do que é insubstituível — e uma regeração
apagaria lançamento manual junto.

Hoje `LancamentoContabil` não tem nenhum dos dois. Vira **BL-72**, e entra junto
da [DL-016](../planos/DL-016-competencia-e-fechamento.md), que já altera o
modelo — uma migração em vez de duas.

## DE-019 — Competência é o mês da data do lançamento

**Data:** 2026-09-13

**Decisão:** a competência **não** é campo próprio do lançamento: é o mês da
`data` dele. O fechamento se dá por empresa e competência, e o que ele controla
é a `data` dos lançamentos novos.

Decisão **operacional e reversível**, tomada por mim para não paralisar a
[DL-016](../planos/DL-016-competencia-e-fechamento.md). Comunicada ao Fred com
o caso concreto que a derrubaria, e revisável enquanto não houver dado real.

### Por quê

Um fato contábil tem uma data. Ter dois campos — a data e um "mês a que isso
pertence" — cria a possibilidade de eles discordarem, e nenhum sistema impede
que um lançamento datado de 10/01 declare competência de dezembro por engano.
A partir daí, Diário e Balancete podem contar histórias diferentes, e é preciso
escolher qual dos dois campos manda em cada saída. Esse tipo de ambiguidade é
exatamente o que produz relatório que não concilia.

### O caso que exigiria o contrário, e por que ele não exige

"Lançamento de dezembro digitado em janeiro." Isso não é um lançamento com
competência diferente da data: é um lançamento **com data de dezembro**,
digitado depois. Enquanto dezembro estiver aberto, grava-se normalmente. Depois
de fechado, vale RC-57: reabre, lança, fecha de novo — com rastro, que é
justamente o que se quer quando se mexe em mês entregue.

### Custo de reverter, se for preciso

Baixo enquanto não houver dado real: acrescentar um campo de competência com
valor derivado da data para as linhas existentes é uma migração simples e sem
perda. O custo sobe assim que houver escrituração de cliente, porque aí as duas
informações passam a ter de ser conferidas uma a uma. Por isso a decisão está
registrada agora, e não depois.

## DE-020 — Respostas às quatro decisões que a auditoria da DL-015 encaminhou

**Data:** 2026-09-13. Origem:
[auditoria DL-015 rodada 1](../auditorias/2026-09-13-dl-015-rodada-1.md),
parecer **reprovado**, achados 2, 3, 7, 8, 11 e 13.

### 1. Saldo de conta no Balancete: uma regra só, para toda conta

Os achados 2 e 7 são o mesmo defeito por dois caminhos: o código decide se lê os
itens próprios **ou** soma as filhas, olhando `aceita_lancamento`. Quando o
estado do dado foge da hipótese (conta com movimento marcada como sintética;
conta analítica com filhas), some valor.

**Decisão:** a regra passa a ser única e não depende de classificação —
**o saldo de qualquer conta é o movimento próprio dela mais o das descendentes**.
Conta folha soma só o próprio; grupo sem movimento próprio soma só as filhas; o
caso híbrido deixa de ser caso.

E os totais do Balancete deixam de ser a soma das linhas: passam a ser a
**soma de todos os itens do período da empresa**, numa agregação própria. Assim
`total_debitos == total_creditos` deixa de depender de a árvore estar bem
formada — nenhum arranjo de hierarquia faz valor sumir do rodapé.

Continuam valendo as guardas de dado: recusar marcar como sintética uma conta
com movimento, e apontar na conferência as inconsistências que já existirem.
Elas evitam o estado; a regra acima garante que, existindo, nada desapareça.

### 2. Grupo com conta retificadora (achado 3)

**Decisão:** o ramo do grupo acumula **débitos e créditos brutos** das
descendentes e aplica a natureza **do próprio grupo uma única vez**. Com isso,
`saldo_final = saldo_anterior ± (debitos − creditos)` vale em **toda** linha do
balancete, analítica ou sintética — e a linha deixa de se contradizer.

A aritmética atual está errada sob qualquer convenção: um imobilizado de 100 com
depreciação acumulada de 30 aparece como 130. A **apresentação** (como exibir a
retificadora dentro do grupo) é decisão profissional do Fred e foi levada a ele.

### 3. Razão de conta sintética (achado 8)

**Decisão:** consolida — opção (a) do auditor. O Razão de um grupo devolve os
itens das descendentes, em ordem cronológica, com a resposta declarando que a
conta é sintética e que o extrato é consolidado.

Motivo: a regra central desta etapa é "Razão e Balancete contam a mesma
história". Recusar com 409 (opção b) seria mais barato e abriria uma exceção
justamente na conta onde o contador mais olha ao conferir um grupo. Custo aceito:
extrato de grupo pode ser longo — tratado com a paginação de BL-76.

### 4. Quem pode ler contabilidade (achado 11)

**Decisão imediata e conservadora:** o papel **cliente deixa de ler
contabilidade** — **toda** leitura de contabilidade, e não uma lista de rotas.
Os demais papéis vinculados ao escritório seguem lendo, até decisão do Fred.

> **Correção de 2026-09-14, achado novo 2 da [rodada
> 2](../auditorias/2026-09-14-dl-015-rodada-2.md).** A redação original desta
> decisão dizia "deixa de ler Diário, Razão, Balancete e conferência" — a lista
> das quatro rotas que a etapa criou. Foi implementada exatamente assim, e o
> cliente continuou lendo a escrituração inteira por `lancamentos/` e o plano de
> contas por `contas/`, com histórico, valores e partidas. O problema que esta
> decisão existe para resolver continuou aberto, e o texto afirmava o contrário.
>
> Erro meu de redação, e de um tipo que vale nomear: **descrevi o remédio pela
> lista do que eu tinha acabado de tocar, em vez de pelo problema que queria
> fechar.** Eu conhecia a rota `lancamentos/` — ela estava na observação 3 do
> relatório da rodada 1, que li e classifiquei como assunto de contrato, não de
> sigilo.
>
> O critério correto, e que vale daqui em diante: **nenhuma rota devolve
> escrituração, plano de contas ou saldo a quem não pode ler contabilidade** —
> independentemente de quando a rota foi criada.

Motivo: hoje um cliente com login lê a contabilidade completa de **todos os
outros clientes** do mesmo escritório. Num escritório de contabilidade isso é
sigilo de cliente contra cliente. A política é anterior à DL-015, mas as quatro
saídas novas mudam a consequência: antes era uma listagem crua de lançamentos,
agora é o livro inteiro numa requisição.

O desenho definitivo depende de **PE-36**: quais papéis leem contabilidade, e se
passa a existir vínculo usuário↔empresa — hoje o vínculo é só com o escritório,
então não há como dizer "este usuário vê só estes clientes".

### 5. SQLite não é ambiente de conferência monetária (achado 13)

**Decisão:** declarar o limite, não perseguir a paridade. Em SQLite, as três
saídas divergem entre si em valores muito altos, porque os agregados passam por
ponto flutuante. Em PostgreSQL — produção e integração contínua — não há
divergência.

Fazer o SQLite somar exato custaria carregar os itens em memória e somar em
Python, penalizando o banco que realmente usamos para servir o que só existe em
desenvolvimento. O aviso de SQLite já existente em `config/settings.py` passa a
dizer que conferência de valor não vale nesse ambiente.

## DE-021 — A constraint que amarra item, conta e lançamento à mesma empresa entra na DL-016

**Data:** 2026-09-14

**Contexto:** o achado 10 da auditoria mostrou que um `ItemLancamento` pode
apontar para uma conta de uma empresa e um lançamento de **outra**. Quando isso
existe, o histórico de um cliente aparece na tela de outro escritório.

> **Correção de 2026-09-14, achado novo 6 da [rodada
> 2](../auditorias/2026-09-14-dl-015-rodada-2.md).** Esta decisão dizia, aqui,
> que o estado "só nasce por gravação direta no ORM — a API não permite". **Eu
> não verifiquei isso antes de escrever.** O auditor verificou: o **Django
> admin** grava o item com conta de outra empresa, grava lote desbalanceado e
> grava lote sem nenhuma partida — três violações da partida dobrada, por uma
> tela que existe e que é justamente o caminho de quem quer "ajustar uma
> coisinha".
>
> O adiamento da garantia de banco **continua valendo**, pelo motivo de
> migração explicado abaixo, mas o risco era maior do que declarei. Em
> compensação, entra agora o que não depende de migração: validação no próprio
> `ItemLancamento` e restrição do que o admin oferece — **BL-79**.

**Decisão:** a defesa em profundidade em código **já entrou** na rodada 2 (Razão
e Balancete passaram a filtrar também pela empresa do lançamento, com teste). A
**garantia de banco** fica para a [DL-016](../planos/DL-016-competencia-e-fechamento.md).

### Por que não agora

A garantia não cabe numa `CheckConstraint`: ela atravessa três tabelas. A forma
correta em PostgreSQL é desnormalizar a empresa para o item e amarrar as chaves
estrangeiras compostas — o que exige **migração de esquema**.

A DL-016 já vai migrar esse mesmo modelo para acrescentar origem e documento de
origem (BL-72). Fazer as duas na mesma migração é uma mudança de esquema em vez
de duas sobre a mesma tabela, e migração é a operação mais cara de reverter num
sistema com dado de cliente.

**Risco de esperar, declarado:** enquanto isso, a proteção é o código — que a
rodada 2 cobriu com teste em ambas as saídas — e o fato de que a API não cria o
estado. Não há dado real no sistema. Vira **BL-78**, com dependência declarada.

## DE-022 — "Analítica" passa a significar folha da árvore

**Data:** 2026-09-14. Origem: achado novo 1 da
[auditoria rodada 2](../auditorias/2026-09-14-dl-015-rodada-2.md), gravidade
alta.

**Decisão:** a palavra **analítica**, nas saídas contábeis, passa a significar
**conta sem descendentes** — folha da árvore. O campo que autoriza lançamento
deixa de ser o critério de apresentação e volta a ser o que o nome dele diz:
permissão de escriturar.

Em consequência:

- O **Razão consolida** sempre que a conta **tiver descendentes**, não quando
  estiver marcada como sintética.
- O Balancete marca como analítica a conta **sem filhas**, seja qual for a
  permissão de lançamento dela.

> **Correção de 2026-09-14, achado novo 3 da [rodada
> 3](../auditorias/2026-09-14-dl-015-rodada-3.md).** A frase continuava com "é o
> que um consumidor precisa para saber quais linhas somar sem contar duas
> vezes". **Não é**, quando existe conta com movimento próprio *e* filhas: a
> soma das folhas fica menor que o rodapé, porque o que foi lançado direto no
> grupo não aparece em folha nenhuma. O auditor mediu a divergência em 11 de 12
> planos gerados ao acaso.
>
> Resolvido em **DE-024 §2**: cada linha passa a declarar o **movimento
> próprio**, e a regra somável vira "a soma dos próprios de todas as linhas é o
> total" — verdadeira em qualquer arranjo, porque todo lançamento é próprio de
> exatamente uma conta.
- A **conferência ganha a quarta categoria**: conta que aceita lançamento e tem
  contas subordinadas.

### Por que o defeito existia

A DE-020 §1 já dizia que a regra de saldo "não depende de classificação". Isso
foi aplicado ao Balancete e **não** ao Razão, que continuou decidindo por
`aceita_lancamento`. Sobraram dois critérios para a mesma pergunta, e o
resultado é o pior defeito possível nesta etapa: a mesma conta, no mesmo
período, com números diferentes em duas saídas — e com a soma das linhas
"analíticas" dando o dobro do rodapé.

O estado que expõe isso **nasce pela API documentada**, não por corrupção: o
campo que autoriza lançamento tem valor padrão verdadeiro, então quem cadastra
um grupo e depois pendura contas nele cria exatamente esse caso, sem aviso.

### Por que não proibir o estado em vez de tratá-lo

Proibir "conta com filhas aceita lançamento" seria mais simples, e foi a
alternativa que o auditor ofereceu. Recusei por duas razões:

1. **Planos de contas reais chegam assim.** Vamos importar plano de contas de
   escritórios anteriores (RC-62), e não temos como exigir que estejam
   coerentes antes de o sistema conseguir emitir um balancete. Um sistema que
   recusa o plano do cliente novo não é usável.
2. **Proibir não conserta o que já existe.** A conferência precisa apontar o
   caso de qualquer forma; e se ela aponta, o cálculo tem de estar certo
   enquanto o contador não arruma.

A regra continua sendo a da DE-020 §1: **nenhum arranjo de plano de contas pode
fazer valor sumir nem aparecer duas vezes.** Proibição é conveniência; a
aritmética correta é obrigação.

## DE-023 — O admin do Django não cria lançamento contábil

**Data:** 2026-09-14. Origem: achado novo 6 da
[auditoria rodada 2](../auditorias/2026-09-14-dl-015-rodada-2.md). Decisão
tomada pelo `desenvolvedor-pleno` sob delegação explícita e **ratificada por
mim**, com o registro formal aqui, como ele pediu no relatório.

**Decisão:** `LancamentoContabilAdmin` deixa de oferecer inclusão. O lançamento
contábil só nasce por `criar_lancamento`.

### Por quê

O auditor gravou, pela tela de administração, três coisas que a regra do projeto
proíbe: item com conta de outra empresa, lote com débito diferente de crédito, e
lote sem nenhuma partida. Nenhum passava por `criar_lancamento`, que é onde as
invariantes contábeis vivem.

A alternativa seria reimplementar as validações no formulário do admin. Recusada:
teríamos **duas** implementações da mesma regra contábil, e a segunda existiria
só para atender a uma tela de manutenção que ninguém usa para escriturar. Duas
implementações da mesma regra divergem — é o mesmo argumento que motivou a fonte
única do estado.

### O que isso não resolve, e fica declarado

> **Correção de 2026-09-14, achado novo 2 da [rodada
> 3](../auditorias/2026-09-14-dl-015-rodada-3.md).** A frase que estava aqui
> tinha as **duas metades erradas**, e eu a escrevi de cabeça sobre um arquivo
> de 70 linhas que poderia ter lido:
>
> - dizia que o admin "continua permitindo alterar" — **não permite**:
>   `has_change_permission` é falso, a ficha abre em modo leitura e o `POST`
>   devolve 403;
> - não mencionava **excluir**, que era o que estava de fato aberto — e é o
>   pior dos dois, porque `QuerySet.delete()` **não** passa pelo `delete()` do
>   modelo, então a ação em lote da listagem apagava lançamento e partidas sem
>   estorno, sem versão anterior e sem trilha.
>
> Corrigido no código junto desta rodada: `has_delete_permission` também é
> falso. O admin, para lançamento contábil, é **somente leitura**.

O que permanece aberto é a gravação por **`QuerySet.update()` / `objects.create()`
direto no ORM**, que nenhum `clean()` ou `save()` alcança. `ItemLancamento` ganhou `clean()` exigindo que conta e lançamento
sejam da mesma empresa — o que fecha o caminho pelo formulário, mas não pelo
`QuerySet.update()`. A garantia de banco continua sendo **BL-78**, na DL-016.

### Consequência operacional

Se um dia for preciso gravar lançamento fora do fluxo normal — uma migração de
dados, uma correção excepcional —, o caminho é um comando de gestão que chama
`criar_lancamento`, não a tela de administração. Isso mantém a trilha e as
invariantes, e deixa rastro do que foi feito.


## DE-024 — Respostas à rodada 3: o que o balancete promete somar, e onde eu meço

**Data:** 2026-09-14. Origem:
[auditoria rodada 3](../auditorias/2026-09-14-dl-015-rodada-3.md), parecer
**reprovado**, achados novos 1 a 4.

### 1. O teste do admin não renderiza página (achado novo 1)

**Decisão:** opção (a) do auditor. O teste passa a verificar o **contrato**
(`has_add_permission` e `has_delete_permission` são falsos, e a ação de exclusão
em lote é recusada), sem renderizar HTML.

A ordem da integração contínua **não muda**. Ela roda `collectstatic` depois do
`pytest` de propósito, e o motivo está escrito no workflow: se rodasse antes, a
CI passaria com um `{% static %}` que falharia na máquina de quem desenvolve —
integração contínua mais permissiva que o ambiente local mascara defeito. Trocar
essa ordem para acomodar um teste seria enfraquecer uma guarda boa para atender
a um caso particular.

**Guarda de processo que passa a valer para mim**, e é a parte que importa: a
contagem de testes que eu declarar num commit tem de vir de **árvore limpa**.
Rodei na árvore de trabalho, que carregava um `staticfiles/` de dois dias antes,
e anunciei "392 passed" — número que não existia num `checkout` novo. O comando
é `git archive <hash> | tar -x -C <dir vazio>` e rodar lá. Vira **BL-81**, para
não depender da minha memória.

### 2. O balancete passa a declarar o movimento próprio de cada conta (achado novo 3)

**Decisão:** cada linha do Balancete ganha **débitos e créditos próprios** —
o que foi lançado **diretamente** naquela conta —, ao lado dos valores
consolidados que ela já traz.

Com isso existe um conjunto de linhas que soma o rodapé, e ele é simples de
enunciar: **a soma dos valores próprios de todas as linhas é igual ao total**.
Sempre, em qualquer arranjo de plano de contas, porque todo lançamento é próprio
de exatamente uma conta.

Descartei as duas alternativas do auditor:

- **Criar uma linha extra** para o movimento próprio do grupo inventaria, no
  balancete, uma conta que não existe no plano do cliente. Balancete é documento
  de conferência; linha que não corresponde a conta cadastrada confunde mais do
  que resolve.
- **Declarar que só o rodapé vale** seria honesto e inútil: o contador soma as
  linhas, é isso que ele faz com um balancete na frente. Um sistema que responde
  "não some" está entregando um documento que não serve para conferir.

A DE-022 dizia que marcar a folha resolvia a soma. **Não resolvia**, quando a
conta tem movimento próprio *e* filhas. Corrigido lá.

### 3. Onde a senha fraca é decidida precisa de teste (achado novo 4)

**Decisão:** a dupla condição fica, ganha teste nas quatro combinações, e o
comentário é corrigido.

O comentário afirmava que a validação de banco "exige `DEBUG=False` em
produção". Não exige: ela recusa SQLite quando `DEBUG=False`. Um servidor com
`DEBUG=True` e PostgreSQL sobe normalmente — o auditor verificou. Escrever uma
justificativa apoiada em garantia inexistente é pior que não justificar, porque
o próximo leitor conclui que a outra metade da condição é redundante e a remove.

Fica registrado como **BL-82** avaliar uma guarda que recuse subir com
`DEBUG=True` fora de desenvolvimento. Hoje não existe, e vários raciocínios de
segurança do projeto já se apoiam nela como se existisse.


## DE-025 — Declaração de risco residual enumera os caminhos verificados

**Data:** 2026-09-14. Origem: o padrão que três auditorias seguidas apontaram
nos **meus** textos, não no código da equipe.

**Decisão:** toda decisão que declare risco residual — "o que isto não resolve",
"o que fica aberto", "o risco aceito é" — precisa **enumerar os caminhos
verificados, um a um**, ou dizer explicitamente que não foram verificados.

### O padrão que motiva a regra

| Rodada | O que eu escrevi | O que era verdade |
| --- | --- | --- |
| 2 | "o cliente deixa de ler Diário, Razão, Balancete e conferência" | Ele continuava lendo tudo por `lancamentos/` |
| 3 | "o admin continua permitindo alterar, protegido pelo `save()`" | Alterar estava recusado; **excluir** é que estava aberto, e apagava em lote sem trilha |
| 4 | docstring do `ContaAdmin`: risco residual é "apagar conta sem movimento" | Verdade, mas incompleto: **alterar** a empresa de uma conta com movimento quebra o balancete |

Três vezes o mesmo movimento: **descrevi o que eu tinha acabado de fechar e
apresentei isso como o inventário do que está aberto.** O leitor seguinte — que
pode ser o Fred decidindo implantar — lê a declaração como levantamento e
conclui que o resto foi examinado.

### O que a regra exige, na prática

Ao escrever "o risco que sobra é X", antes de publicar:

1. **Listar as portas** do componente. Para um `ModelAdmin`, são quatro:
   incluir, alterar, excluir individualmente e excluir em lote — e a última não
   passa pelo `delete()` do modelo.
2. **Exercitar cada uma**, não deduzir da leitura. Foi exercitando que o auditor
   achou as três.
3. **Escrever o resultado de cada uma**, inclusive as que estão fechadas.
4. Onde não der para exercitar, escrever **"não verificado"** — que é
   informação honesta, ao contrário de um silêncio que parece cobertura.

Custa minutos e teria evitado três achados. Não é sobre atenção: é sobre
enumerar antes de afirmar.

## DE-026 — A tela da contabilidade não chama a própria API

**Data:** 2026-09-14. Contexto: início da interface da contabilidade
([DL-017](../planos/DL-017-interface-da-contabilidade.md), BL-62).

**Decisão:** as telas são **views Django que chamam os serviços diretamente**
(`listar_diario`, `apurar_razao`, `apurar_balancete`, `criar_lancamento`) e
renderizam HTML no servidor. **Não** há JavaScript buscando a própria API.

### Por quê

1. **A autorização não pode existir em dois lugares.** A API já decide quem lê
   contabilidade. Se a tela chamasse a API, teríamos duas camadas de
   autenticação (sessão e a da API) no mesmo pedido; se a tela reimplementasse a
   regra, teríamos duas cópias da mesma decisão de sigilo. As duas opções são
   ruins, e a segunda é a que produz vazamento — foi exatamente assim que o
   papel cliente continuou lendo a escrituração por outra rota.
2. **O projeto já é assim.** `apps/empresas` e `apps/tenancy` renderizam no
   servidor, com a fundação da DL-009 (template base, mensagens, estados,
   acessibilidade). Introduzir um consumidor JavaScript agora criaria dois
   modelos de tela no mesmo produto, sem demanda que justifique.
3. **Um contador conferindo um balancete não precisa de aplicação de página
   única.** Precisa de página que carrega, imprime bem e funciona com teclado.

### O que isso exige, e é a parte que importa

A regra de quem pode ler contabilidade passa a viver **num módulo só**, usado
pela API e pela tela. Não é "cuidado ao copiar": é impossibilitar a cópia.
Entra como fase A da DL-017, **antes** de qualquer template.

### O que esta decisão não fecha

A API continua existindo e sendo o contrato público — ela é o que um dia
alimenta integração, aplicativo ou o servidor MCP previsto no escopo. O que se
decide aqui é que **a nossa tela não é cliente dela**.

## DE-027 — Quem julga o texto de um valor monetário é o módulo monetário, não a view

**Data:** 2026-09-14. Contexto: achado 2 da [auditoria da DL-017, rodada
1](../auditorias/2026-09-14-dl-017-rodada-1.md). Medido: a tela de lançamento
gravou `1e3` como **1.000,00**, e ainda aceitou `1_000`, `+10,00` e `10,00 ` com
espaço — quatro formatos que a API recusa com 400 de propósito.

**Decisão:** a view de tela **não constrói `Decimal`**. Ela faz uma única coisa
com o texto digitado: troca a vírgula decimal pelo ponto e entrega o **texto**
para `apps.contabilidade.monetario.para_decimal`, traduzindo
`ValorMonetarioInvalido` em erro de campo do formulário. A partir daqui, todo
caminho de entrada de valor monetário — tela, API, importação de XML, carga de
planilha — passa pelo mesmo julgador de formato textual.

### Por que isso é decisão de arquitetura e não conserto local

A DE-026 fechou o risco que eu havia nomeado: **duplicar** a regra. O que
escapou foi o simétrico, e é mais difícil de ver, porque não há cópia nenhuma
para comparar: a tela **contornou** o guarda. `_decimal_do_formulario`
documentava corretamente que a validação de domínio (sinal, escala — DE-010)
continua em `criar_lancamento`; e estava certo. Só que, ao fazer
`Decimal(texto)` dentro da view, tirou de `para_decimal` a única coisa que só
ele podia julgar: **se aquele texto é uma representação aceitável de dinheiro**.
`criar_lancamento` recebe um `Decimal` já pronto e não tem mais o que recusar.

O efeito prático é o oposto do esperado de uma interface: a tela ficou a porta
**mais frouxa** da mesma invariante. `1e3` virar mil reais não é erro de
arredondamento nem de apresentação — é reinterpretar em mil vezes o que está
escrito na tela do contador.

### A regra que fica, em uma frase

**Validação de formato pertence a quem define o formato.** Se uma camada precisa
do valor tipado, ela pede o valor tipado a esse dono — nunca o constrói por
conta própria a partir do texto do usuário.

### Como isso passa a ser verificado

Não por revisão: por teste de equivalência. Uma lista de textos aceitáveis e
inaceitáveis é percorrida pelos **dois** caminhos (tela e API) exigindo o
**mesmo** veredito em cada um. Quando entrar um terceiro caminho de entrada
(importação de NFS-e, DL-010), ele entra na mesma lista. O achado 1 (não-finitos
derrubando a tela com 500) é corrigido pelo mesmo movimento, e é a razão de os
dois andarem juntos.

### Atenção: a cláusula de tradução desta decisão estava ERRADA

Acrescentado em 2026-09-14, depois da rodada 2 da auditoria. A frase abaixo que
descreve a tradução como *"vírgula decimal vira ponto, separador de milhar
sai"* **não corresponde ao que o código fazia nem ao que ele deve fazer**, e
por trás dela passou um defeito **bloqueador**: a tela gravava `1.000` como
1,00. Ver **DE-029**, que substitui a cláusula de tradução e institui o teste
que faltava.

O resto desta decisão continua valendo: quem julga o texto de um valor
monetário é o módulo monetário, nunca a view.

### O que "mesmo veredito" quer dizer, exatamente

Acrescentado em 2026-09-14, porque o `especialista-frontend` levantou o caso na
implementação e a redação acima não respondia: `"+10,00"` digitado na tela é
aceito; o **mesmo texto literal** enviado à API é recusado. Isso contradiz a
decisão?

**Não, e a distinção é o ponto.** A tela faz — e só ela faz — **uma** tradução
declarada: vírgula decimal vira ponto, separador de milhar sai. É tradução de
*locale*, não julgamento de valor. O contrato é:

> Depois da tradução de *locale* da tela, o texto resultante recebe de
> `para_decimal` **exatamente** o mesmo veredito que receberia se tivesse
> chegado pela API.

Ou seja, a equivalência é **a jusante da tradução**, nunca byte a byte na
entrada — exigir texto idêntico nos dois canais seria exigir que o contador
digitasse ponto decimal, que é o oposto do critério 4 do plano
[DL-017](../planos/DL-017-interface-da-contabilidade.md) e de BL-23. No caso
levantado:
`"+10,00"` → `"+10.00"`, e `para_decimal("+10.00")` é aceito **pelos dois
caminhos**, com contrato já testado em `apps/core/tests/test_dinheiro.py`. O
sinal `+` não é a diferença; a vírgula é. O valor numérico concorda.

O que a decisão proíbe continua valendo inteiro: a tela **não** pode aceitar
nada que `para_decimal` recuse, nem recusar nada que ele aceite. Quem verifica
isso é o teste de equivalência, e a tradução de *locale* é a **única** etapa
autorizada entre o que o usuário digita e o que o julgador vê. Qualquer segunda
transformação — `.strip()`, troca de sinal, corte de zeros — é reinterpretação
silenciosa, e está proibida pelo mesmo motivo que originou esta decisão.

## DE-028 — Migração automática ao subir é conveniência de desenvolvimento, nunca de produção

**Data:** 2026-09-14. Contexto: o Fred tentou abrir o sistema pelo Docker no
Windows seguindo **exatamente** o que o README manda, e não conseguiu (BL-100).

**Decisão:** o `command` do serviço `web` no `docker-compose.yml` roda
`manage.py migrate --noinput` antes do gunicorn. O `CMD` do `Dockerfile`
**continua sendo só o gunicorn**, e essa diferença é proposital.

### Por que os dois não são iguais

Em desenvolvimento sobe **uma** instância, contra um volume que pode ter
acabado de nascer vazio. Sem migração automática, a primeira tela devolve erro
de relação inexistente — e quem está avaliando o produto conclui, com razão, que
ele não funciona. Foi o que aconteceu: o caminho documentado no README não
levava a um sistema utilizável.

Em produção sobe **mais de uma** instância da aplicação. Se cada uma migrasse ao
iniciar, várias executariam o mesmo `migrate` em paralelo na mesma base. Pior:
uma migração longa passaria a bloquear o start, e um `restart: unless-stopped`
transformaria falha de migração em laço de reinício. **Migração é passo
deliberado de implantação** — alguém decide, executa, confere e só então as
instâncias sobem.

### O limite honesto desta decisão

Ela resolve o ambiente de avaliação e desenvolvimento. **Não** define como a
migração acontece na implantação em nuvem — isso é do P0 de implantação
(DE-014), junto com cópia de segurança e restauração testada (BL-33), e continua
em aberto.

## DE-029 — A gramática pt-BR do campo de valor, e a regra de que texto ambíguo se recusa

**Data:** 2026-09-14. **Substitui a cláusula de tradução da DE-027**, que estava
errada. Contexto: achado R2-1 da
[auditoria DL-017 rodada 2](../auditorias/2026-09-14-dl-017-rodada-2.md), de
gravidade **bloqueador**.

### O defeito que originou a decisão

A tela gravava `1.000` como **1,00**. O contador digita mil reais como todo
brasileiro escreve mil reais, a tela responde *"Lançamento gravado com
sucesso"*, e o livro fica com um real. O lançamento fecha (os dois lados
sofreram a mesma divisão), o balancete concilia, e a tela de conferência diz que
não há inconsistência. Medido em 9 de 12 valores de milhar comuns.

Estava na `main` desde a integração do PR #18.

### Por que a DE-027 não podia pegar isso

A DE-027 acertou em *quem julga* o texto (o módulo monetário, nunca a view) e a
implementação obedece. O erro está na frase que **define a tradução**:
*"vírgula decimal vira ponto, separador de milhar sai"*. O código só tirava o
separador quando havia vírgula — e **corrigir o código para bater com o texto
seria pior**, porque tiraria o ponto de `10.00` e transformaria dez reais em mil.

A verdade que faltava enxergar: **`1.000` é ambíguo.** Em pt-BR é mil; no formato
canônico da API é um. Não existe função de tradução bem definida sobre esse
texto, logo não existe conserto que preserve as duas leituras.

### A decisão

**1. O campo de valor da tela aceita uma gramática pt-BR explícita, escrita como
padrão e não como prosa:**

```
^[+-]?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]{1,2})?$
```

Em português: dígitos sem separador algum, **ou** dígitos agrupados de três em
três por ponto, com centavos opcionais depois da vírgula.

**`[0-9]`, nunca `\d` — e isto é normativo, não detalhe de escrita.** Em Python,
`\d` casa **qualquer** dígito decimal Unicode: `０１０` (fullwidth), `١٢٣`
(índico-arábico), `๑๐` (tailandês). Esta decisão foi publicada, em 2026-09-14,
com `\d` no texto enquanto o código usava `[0-9]` — quem implementasse seguindo
o documento reabriria o R2-7, **e nenhum teste reclamaria** (medido: o mutante
que troca `[0-9]` por `\d` na gramática sobrevive a 559 testes). Corrigido no
mesmo dia, pelo achado R3-6 da
[rodada 3](../auditorias/2026-09-14-dl-017-rodada-3.md).

É o erro da DE-027 com os papéis trocados: lá o texto estava certo e o código
errado; aqui o código estava certo e o texto errado. A lição é a mesma nos dois
casos — **decisão que descreve comportamento precisa de teste que ligue o texto
ao código**, senão ela envelhece sem que ninguém perceba.

| Digitado | Vale | Por quê |
| --- | --- | --- |
| `1000` | 1000,00 | sem separador, sem ambiguidade |
| `1.000` | 1000,00 | grupo de milhar bem formado |
| `1.234.567,89` | 1234567,89 | idem, com centavos |
| `0,50` | 0,50 | centavos |
| `10.00` | **recusado** | `.00` não é grupo de milhar; em pt-BR é malformado |
| `1.00` | **recusado** | idem |
| `1e3`, `1_000`, `NaN` | **recusado** | não é a gramática |

**2. Texto fora da gramática é recusado pela tela, com mensagem que ensina o
formato** — nunca reinterpretado, nunca "corrigido" em silêncio. `10.00` passa a
ser recusado, **e isso é correto**: é o formato canônico da API, não o da tela
de um contador brasileiro.

**3. Depois da tradução, `para_decimal` continua julgando.** A gramática não o
substitui: ele é a segunda camada, que apanha sinal, escala e não-finito. A
DE-027 continua valendo inteira nesse ponto.

### O teste que faltava, e que é o coração desta decisão

A DE-027 instituiu um teste de **equivalência entre tela e API**. Ele não podia
pegar o R2-1 **por construção**: compara os dois lados *depois* da tradução, e o
defeito estava *na* tradução. Passa a ser obrigatório um segundo teste, de outra
natureza:

> **Texto digitado → valor gravado.** Para uma tabela de textos em pt-BR, o valor
> que fica no banco é exatamente o que o texto significa em pt-BR, ou a
> requisição é recusada com 400. **Nunca 302 com outro número.**

Esse teste teria pego o defeito na primeira execução. Os dois testes convivem: o
de equivalência protege a fronteira entre as portas; este protege o significado
do que o contador digitou.

### A lição de processo, que vale além deste campo

O auditor nomeou o padrão das três correções incompletas desta rodada, e ele é
meu: **a correção fechou o caso que o relatório descrevia, não a classe que ele
nomeava.** O achado 5 dizia *"nunca truncar em silêncio"* e a tarefa que escrevi
virou *"recusar acima de 20"* — o defeito voltou por `num_linhas` malformado
(R2-3). O achado 6 dizia *"medir CSS"* e virou *"proibir `style=` inline"* — a
indentação segue sem teste que a defenda (R2-6).

Passa a valer: **o critério de aceite de uma correção cita a classe do defeito,
nunca só a reprodução do relatório.** Quem escreve a tarefa é o
`arquiteto-senior`, e o erro de escrevê-la estreita é dele.

## DE-030 — Todo caminho de entrada de valor monetário declara sua gramática, e nenhum constrói `Decimal` por conta própria

**Data:** 2026-09-14. Contexto: achado **R3-3** e o segundo ponto da seção "onde
eu acho que você errou" da
[auditoria DL-017 rodada 3](../auditorias/2026-09-14-dl-017-rodada-3.md).

### O buraco que nem a DE-027 nem a DE-029 cobriam

As duas decisões legislam sobre **dois** dialetos de entrada: a tela, que fala
pt-BR (DE-029), e a API, que fala o formato canônico com ponto decimal
(DE-027). O sistema tem um **terceiro**, que nenhuma das duas menciona: o
**número JSON**.

Medido pelo auditor, pela API real:

```
enviado 99999999999999.99   -> HTTP 201, gravado 99999999999999.98
enviado 70368744177664.01   -> HTTP 201, gravado 70368744177664.02
enviado 562949953421312.07  -> HTTP 201, gravado 562949953421312.10
enviado "1e3" como TEXTO    -> 400 (correto)
enviado  1e3  como NÚMERO   -> 201, gravado 1.000,00
```

O JSON vira `float` no Python, `apps/contabilidade/views.py` faz `str(valor)` e
depois `Decimal(...)`, e a recusa de notação científica que o próprio comentário
do arquivo anuncia é contornada **trocando aspas por número**. É o R2-1 na outra
porta: 201 de sucesso com número diferente do enviado.

Hoje o estrago é limitado por acidente: abaixo de ~7×10¹³ o espaçamento do
`double` é menor que um centavo, e a checagem de escala recusa os casos
problemáticos. **"Protegido por acidente de escala" é exatamente o mecanismo
pelo qual `1.234` escapava antes do R2-1.** Não conta como proteção.

### A decisão

**1. Nenhuma camada constrói `Decimal` a partir de entrada de cliente.** Nem a
tela, nem a API, nem a importação. Todas entregam **texto** a
`apps.core.dinheiro.para_decimal`, que é o único julgador. A API hoje
reimplementa a checagem com a mesma expressão regular e constrói o `Decimal`
sozinha — é duplicação, e é onde este defeito mora.

**2. Valor monetário que chegue como número (não texto) é recusado.** `float`
já é recusado por contrato dentro de `para_decimal`; a recusa passa a valer
**antes**, na fronteira, com mensagem que diga para enviar como texto.

**3. Todo caminho de entrada declara, por escrito e em teste, qual gramática
aceita.** Hoje são três: pt-BR (tela, DE-029), canônica (API, DE-027) e
**nenhuma** (número JSON, que passa a ser recusado). Quando a
[DL-010](../planos/DL-010-recepcao-de-documentos-fiscais.md) trouxer NFS-e e
carga de planilha, cada um desses caminhos responde a pergunta **antes** de
existir código: *qual texto eu aceito, e o que faço com o que não casa?*

### Por que isto não é preciosismo

O auditor formulou melhor do que eu: *"quando a DL-010 trouxer NFS-e e carga de
planilha, a pergunta «qual gramática este caminho usa?» não terá resposta
escrita"*. São quatro caminhos de entrada de dinheiro num sistema contábil. A
DE-027 acertou em dizer que **um** módulo julga; faltava dizer que **todos**
passam por ele.

## DE-031 — O campo de data mantém o seletor do navegador, e o rótulo para de afirmar formato

**Data:** 2026-09-14. Contexto: achado **R3-8** da rodada 3, e o resíduo do
R2-8 da rodada 2.

**O problema, visível na captura entregue:** o `<input type="date">` exibe
`09/14/2026` (mês/dia/ano, *locale* do navegador) logo abaixo de um rótulo que
diz "(dd/mm/aaaa)" e três centímetros acima de um cabeçalho que diz
`14/09/2026`. A mesma data, em duas ordens, na mesma tela. **Não é defeito de
código:** o formato de exibição do seletor nativo vem do navegador, e
`LANGUAGE_CODE` não o altera.

**Decisão: fica o seletor nativo**, e o rótulo **deixa de afirmar** um formato
que ele não controla.

Motivos, nesta ordem:

1. **Acessibilidade e teclado.** O seletor nativo é navegável por teclado,
   anunciado por leitor de tela e conhecido pelo usuário. Um campo de texto
   livre perde isso.
2. **Sem JavaScript** (critério 15). Forçar o formato exigiria JS; trocar por
   texto exigiria leitura pt-BR no servidor e reintroduziria a classe de defeito
   que a DE-029 acabou de fechar para valores — agora para datas.
3. **Na prática, o escritório vê pt-BR.** Navegador em português brasileiro
   exibe `dd/mm/aaaa`. A ambiguidade aparece em ambiente fora de pt-BR — como o
   contêiner onde a captura foi feita.

**O que muda:** o rótulo nomeia o campo sem prometer formato, e o texto de
apoio diz que o campo segue o navegador, enquanto **toda exibição de data do
sistema é `dd/mm/aaaa`**. Prometer menos e cumprir é melhor que prometer
`dd/mm/aaaa` num campo que pode mostrar outra coisa — hoje o rótulo pode mentir,
e mentir com aparência de precisão é pior que não dizer.

**Reversível:** se o Fred relatar confusão real no escritório, a saída é um
campo de texto com leitura pt-BR no servidor, e aí a gramática de data entra na
DE-030 junto com as de valor.

## DE-032 — A classe de um defeito se escreve pelo efeito proibido, nunca pelo mecanismo onde ele foi visto

**Data:** 2026-09-14. Contexto: ponto 4 da seção "onde eu acho que você errou"
da [auditoria DL-017 rodada 4](../auditorias/2026-09-14-dl-017-rodada-4.md).
**Complementa a DE-029**, que instituiu a forma obrigatória "A classe é:"; o que
muda aqui é **o que se escreve depois dela**.

### A evidência que originou a decisão

A forma obrigatória funcionou: todos os itens de BL-115 a BL-125 trazem a frase.
E mesmo assim duas das três correções fecharam o **caso** e não a **classe**. O
auditor mostrou por quê, com a tabela que eu não tinha enxergado:

| Item | Como escrevi a classe | O que aconteceu |
| --- | --- | --- |
| BL-115 | "nenhum número do cliente **dimensiona laço**" | varreram todo `range()` — corretamente — e o `int()` na linha ao lado ficou (A1, A2) |
| BL-116 | "nenhuma linha enviada **no POST** deixa de ser lida" | virou "nenhuma chave de `request.POST`"; `request.FILES` ficou fora (A3) |
| BL-117 | "nenhuma camada **constrói `Decimal`** a partir de entrada de cliente" | **fechou** — o mutante mata 14 |

As duas primeiras nomeiam **a construção de código onde o defeito foi visto**
(`range`, `request.POST`). A terceira nomeia **o efeito que não pode acontecer**.
É a única que fechou.

### A decisão

Todo critério de aceite de correção descreve **o estado que o sistema não pode
alcançar**, em termos observáveis de fora, e nunca o trecho de código onde o
defeito apareceu.

| Em vez de | Escreva |
| --- | --- |
| "nenhum número do cliente dimensiona laço" | "nenhuma entrada de cliente faz o servidor gastar tempo proporcional a ela" |
| "nenhuma chave de `request.POST` é ignorada" | "nenhum dado enviado numa requisição deixa de ser lido ou recusado" |
| "usar `try/except` em volta do `int()`" | "nenhuma entrada de cliente produz resposta 5xx" |

O teste da redação é simples: **se a frase cita um nome de função, de módulo, de
dicionário ou de construção da linguagem, ela está escrita pelo mecanismo.** O
mecanismo entra depois, como *exemplo* — que é onde a DE-029 já o coloca.

### Por que isto não é preciosismo de redação

Quem implementa cumpre o que está escrito, e cumpre bem. Nas duas ocorrências
acima a varredura foi **feita**, com competência, e parou exatamente na fronteira
que a frase desenhou. O limite não foi de cuidado; foi de escopo — e o escopo
fui eu que escrevi. **Quando a classe é estreita, a correção correta é
insuficiente**, e isso não aparece em revisão de código: só aparece quando
alguém ataca por fora, que é o que a auditoria faz.

## DE-033 — Toda decisão que especifique comportamento observável nasce com item de backlog no mesmo commit

**Data:** 2026-09-14. Contexto: achado **A5** da rodada 4.

**O que aconteceu:** a [DE-031](decisoes.md) decidiu que o rótulo do campo de
data deixaria de afirmar um formato que ele não controla. A decisão foi
registrada, argumentada e datada — e **nunca virou tarefa**. Os sete rótulos
continuam dizendo `(dd/mm/aaaa)`, a captura entregue continua mostrando
`09/01/2026` embaixo deles, e nenhum teste cobre o texto do rótulo, então nada
acusou. Uma rodada inteira de auditoria depois, o achado R3-8 continua vivo no
produto.

**Decisão:** uma decisão que especifique comportamento observável — texto de
tela, formato aceito, resposta HTTP, regra de recusa — **só está registrada
quando existe, no mesmo commit, um item de backlog com responsável e critério de
aceite**. Decisão sem tarefa atribuída é intenção, e intenção não chega ao
usuário.

Decisões que descrevem **estrutura** (onde mora uma regra, quem julga o quê,
qual camada faz o quê) não precisam disso quando já estão implementadas no mesmo
commit — o que a regra alcança é a decisão que **projeta** comportamento futuro.

**Verificação:** por enquanto, disciplina de quem escreve — eu. Não é imposta
por mecanismo, e **declaro isso**: a DE-029 e a BL-124 mostraram que lembrete
tem taxa de falha alta neste projeto. Se reincidir, vira teste que cruza
`decisoes.md` com `backlog.md`.
