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

## DE-034 — A varredura de uma classe começa no CAMPO, não na linha

**Data:** 2026-09-14. Contexto: ponto 5 da seção "onde eu acho que você errou" da
[auditoria DL-017 rodada 5](../auditorias/2026-09-14-dl-017-rodada-5.md).
**Sucessora prática da DE-032**, que continua valendo: a classe se escreve pelo
efeito proibido. O que a DE-034 acrescenta é **onde a varredura começa**.

### A evidência

A DE-032 funcionou melhor que qualquer regra desta etapa — **nove classes
fechadas com mutante morrendo**, incluindo duas que vinham sobrevivendo havia
três rodadas. E ainda assim os três resíduos da rodada 5 estão, os três, **a um
campo de distância** do que foi consertado:

| Classe declarada | Onde fechou | O vizinho que ficou |
| --- | --- | --- |
| "nenhum dado tipado sem gramática" | `vigencia_inicio`, **linha 134** | `regime`, **linha 133** — literalmente a linha de cima, no mesmo `request.data` |
| "nenhuma entrada é reinterpretada em silêncio" | tela e `tenancy` | `item["conta"]` da **API**, no mesmo arquivo do campo `data` que foi corrigido |
| "nenhuma entrada produz 5xx" | conversão texto→número | **restrição de banco**, e uma delas na mesma função que já converte a de CNPJ em 400 |

Não é falta de cuidado de quem implementa: a varredura foi feita, e foi feita
bem. É que ela começou **na linha apontada** e se expandiu pelo mecanismo
(`range`, `int()`, `fromisoformat`), em vez de começar **no campo** e se expandir
pelos vizinhos.

### A decisão

Quando um campo de uma requisição é corrigido, **os outros campos da mesma
requisição entram na varredura por construção** — não por lembrança. Em
concreto, a correção de um campo obriga a percorrer:

1. **Os demais campos do mesmo `request.data` / `request.POST` / formulário.**
2. **O mesmo campo nas outras superfícies** — tela, API, importação. Foi assim
   que o `conta` da API escapou enquanto o da tela era corrigido.
3. **As demais restrições do mesmo `Meta`** quando o defeito envolver o banco.

### A pista que estava escrita e ninguém leu

O relatório traz a observação mais fina das cinco rodadas: os comentários de
`views_web.py` **afirmam que a API já usa `para_id`**. Ela não usa. O comentário
não só afirmou mais do que a defesa entregava — **ele afirmou exatamente a coisa
que impediu de ir olhar**.

É a oitava ocorrência da família "comentário que afirma mais do que a defesa
entrega", e a primeira em que o comentário **causou** a lacuna em vez de apenas
descrevê-la mal. Por isso a regra ganha um par verificável, e não fica no
conselho: **toda frase de comentário do tipo "o mesmo julgador que X usa" deve
ser conferível por teste** — se X não usa, o teste reprova. Registrado como
BL-146.

## DE-035 — Papel de agente tem uma fonte e formatos gerados, nunca cópias paralelas

**Data:** 2026-09-15. Contexto: pedido do Fred para que ChatGPT/Codex e outros
modelos também consigam trabalhar no repositório, em
[DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md).

**O que foi pedido:** uma pasta por ferramenta, cada uma com os agentes dentro,
ao lado de `.claude`.

**Decisão:** o conteúdo de cada papel vive em `docs/agents/papeis/<papel>.md`,
em formato independente de fornecedor, e os arquivos de cada ferramenta são
**gerados** por `scripts/gerar_agentes.py`, com teste que reprova o build quando
um derivado diverge da fonte.

> **Corrigido em 2026-09-15, achado 4 da [rodada 1 da auditoria
> DL-019](../auditorias/2026-09-15-dl-019-rodada-1.md).** Esta decisão foi
> escrita listando quatro destinos — `.claude/agents/`, `.codex/agents/`,
> `.github/agents/` e `.gemini/agents/`. **São dois:** os dois primeiros. A
> [DE-037](#de-037--formato-de-agente-só-se-gera-para-ferramenta-que-alguém-usa),
> tomada horas depois, reduziu o escopo, e eu atualizei o plano e esqueci daqui,
> do `README.md` e do `AGENTS.md`. A afirmação errada ficou em **três** lugares
> — o mesmo número do incidente de 2026-09-13 que originou a instrução
> permanente do Fred. Quem escreveu a decisão contra duplicação cometeu o erro
> dela no mesmo commit; fica registrado em vez de apagado.

**Motivo:** o pedido literal criaria três cópias do mesmo papel. A instrução
permanente do Fred, de 2026-09-13, nasceu exatamente disso — o estado do projeto
afirmado em quatro lugares e já divergente. A causa registrada à época não foi
distração, foi **duplicação**. Um papel de auditor descrito em três arquivos
diverge no primeiro ajuste, e cada modelo passa a acreditar numa versão
diferente de quem ele é.

**Alternativas descartadas:**

- **Cópias mantidas à mão**, como pedido: entrega o mesmo resultado hoje e
  diverge na primeira manutenção, sem nada acusar.
- **`.claude/agents/` como fonte canônica**, gerando os demais a partir dela:
  custaria menos, mas consagraria um fornecedor como dono do formato — o oposto
  do que a etapa existe para resolver.
- **Arquivos-ponteiro finos** em cada pasta, do tipo "leia o papel em
  `docs/`": funciona para regra de processo, não para definição de papel —
  várias ferramentas carregam o arquivo do agente como prompt e não seguem o
  ponteiro.

**Consequência:** editar `.claude/agents/*.md` à mão passa a ser erro, e o teste
acusa. Ferramenta nova só entra no conjunto com o caminho e o formato
confirmados em documentação oficial.

## DE-036 — Regra de processo aponta; só papel é gerado

**Data:** 2026-09-15.

**Decisão:** o `AGENTS.md` continua sendo o único lugar onde as regras de
desenvolvimento existem. Ferramenta que não o lê nativamente ganha um arquivo
fino que **aponta** para ele — como `.github/copilot-instructions.md` já faz
desde a [DL-014](../planos/DL-014-guardas-de-processo.md). Geração automática
fica restrita à definição de papel.

> **Corrigido em 2026-09-15, mesmo achado 4 da [rodada
> 1](../auditorias/2026-09-15-dl-019-rodada-1.md).** O texto original terminava
> com "e como `GEMINI.md` passa a fazer". **`GEMINI.md` não existe e não será
> criado**: o Gemini saiu do escopo pela DE-037. Quem cumpre o papel de ponteiro
> hoje, além do arquivo do Copilot, são as duas skills em `.agents/skills/`,
> lidas pelo Codex a partir do repositório.

**Motivo:** a regra é um documento longo, lido por sete ferramentas por
convenção aberta; copiá-lo multiplicaria o risco e o tamanho. O papel é um
prompt curto que a ferramenta carrega diretamente, e aí o ponteiro não serve.

**Alternativas descartadas:** gerar cópias do `AGENTS.md` por ferramenta —
duplicação sem ganho, com o agravante de o Codex ter limite padrão de 32 KiB
para os arquivos de instrução que concatena.

**Consequência:** um teste reprova o build se um trecho literal e longo do
`AGENTS.md` aparecer duplicado em outro arquivo.

## DE-037 — Formato de agente só se gera para ferramenta que alguém usa

**Data:** 2026-09-15. Contexto: execução da
[DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md).

**O que aconteceu:** o plano nasceu cobrindo quatro ferramentas — Claude Code,
Codex, GitHub Copilot e Gemini CLI — escolhidas por terem caminho e formato
**confirmados em documentação oficial**. Isso responde "dá para fazer?", que é
a pergunta errada. A pergunta certa é "alguém usa?". Perguntei ao Fred, e a
resposta foi *"Codex pelo terminal"*.

**Decisão:** o repositório gera definição de papel apenas para **Claude Code** e
**Codex CLI**. Copilot e Gemini saem. `.github/copilot-instructions.md`
permanece, porque é ponteiro de custo zero que já existia desde a DL-014 e
continua servindo a quem abrir o projeto pelo GitHub.

**Motivo:** cada formato gerado é manutenção permanente, mais uma superfície
onde a documentação pode passar a mentir e mais um arquivo que o auditor tem de
conferir. Capacidade confirmada não é necessidade demonstrada.

**Alternativas descartadas:** manter os quatro "porque já estava pronto" — é
como o projeto acumula peso morto; e deixar os dois formatos extras no gerador,
desligados por configuração — seria código morto, proibido pelo AGENTS.md §8.

**Consequência, e ela é barata:** acrescentar uma ferramenta depois é uma
entrada na tabela do gerador mais um caso de teste. A decisão é reversível em
minutos, e por isso não precisou de mais discussão.

**Efeito colateral valioso:** a resposta do Fred transformou uma nota de rodapé
em risco medido. O Codex trunca os arquivos de instrução em 32.768 bytes por
padrão, e o `AGENTS.md` está em 22.601 — 69% do limite, crescendo a cada etapa.
Virou o critério 14 da DL-019, com teste que reprova acima de 30.000 bytes.
**Nenhuma das quatro ferramentas teria revelado isso; a pergunta ao usuário
revelou.**

## DE-038 — O rigor do processo é proporcional ao dano possível, não ao gosto do arquiteto

**Data:** 2026-09-15. Contexto: cobrança do Fred ao fim da
[DL-019](../planos/DL-019-portabilidade-entre-ferramentas-de-ia.md), e ela
estava certa.

**O que aconteceu:** o Fred pediu pastas para que outras ferramentas de IA
trabalhassem no repositório. Eu transformei o pedido numa etapa completa —
fonte única, gerador, 29 testes novos, **três rodadas de auditoria** e duas
reprovações — e consumi horas dele num item que não toca dado de cliente,
cálculo, período fechado nem isolamento entre empresas. Ele resumiu assim:
*"Tá difícil assim? você está a horas nisso e não consegue resolver"*.

O [AGENTS.md](../../AGENTS.md) já mandava dimensionar "na proporção necessária
à demanda", e a §4 já diz que demanda pequena adapta a quantidade de etapas. Eu
não apliquei. Não foi zelo: foi **falta de calibragem**, e o custo caiu sobre o
tempo do responsável pelo produto.

**Decisão:** o ciclo completo — auditoria independente por rodada, correção,
reauditoria até aprovação — vale para mudança que possa **corromper dado,
errar cálculo, vazar informação entre empresas, desbalancear lançamento,
alterar período encerrado ou derrubar o servidor**. Para o restante —
ferramental interno, documentação, configuração de agente, script de apoio —
vale **uma rodada de auditoria**; o que ela achar e não estiver nessa lista de
danos vira item de backlog nomeado, e a etapa fecha.

**Motivo:** processo tem custo, e o custo é o tempo do Fred. Rigor gasto onde o
dano possível é pequeno é rigor que falta onde o dano é grande. Esta etapa
produziu achados reais (travessia de caminho no gerador, build reprovando em
clone limpo), mas produziu também rodadas que só refinaram o que já não
machucava ninguém.

**Alternativas descartadas:** manter o ciclo completo para tudo — foi o que
fizemos, e o resultado está registrado acima; abandonar a auditoria
independente em itens menores — ela achou, na primeira rodada desta mesma
etapa, um defeito que gravava arquivo fora do repositório. Uma rodada é o
equilíbrio.

**Consequência, e é ela que muda o comportamento:** quem escreve o plano
declara, no próprio plano, em qual das duas faixas a demanda está, **antes** de
começar. Faixa declarada depois do primeiro parecer é escolha influenciada pelo
resultado.

**O que esta decisão NÃO afrouxa:** a honestidade dos relatórios, a exigência
de teste executado, a proibição de apresentar hipótese como requisito
confirmado e a preservação integral dos achados de auditoria. Nada disso é
proporcional a risco — é condição de o registro valer alguma coisa.

## DE-039 — Regime tributário errado se apaga, e a exclusão é um fato registrado

**Data:** 2026-09-15. **Origem:** achado R6-6 da
[auditoria DL-017 rodada 6](../auditorias/2026-09-15-dl-017-rodada-6.md),
pendência PE-46, requisitos **RC-85** e **RC-86**.

### O que o Fred decidiu, e o que eu decidi

O Fred decidiu o **comportamento de produto**: quando o contador erra a vigência
ou o regime de um período, a correção **apaga** o registro errado. Ele escolheu
isso contra a minha recomendação de registrar uma correção rastreável no molde
do estorno, e a escolha é dele — é ele quem precisa provar coisas a cliente e a
fisco, e regime tributário é **dado cadastral**, não escrituração.

Eu decidi o **alcance técnico**, porque "apagar" sozinho é ambíguo em três
pontos e cada ambiguidade é um defeito futuro:

1. **Apaga-se somente o último período** — aquele que não tem sucessor. Apagar um
   período do meio abriria um **buraco na linha do tempo**: o antecessor já teve
   a `vigencia_fim` recortada para o dia anterior ao sucessor, e sem o sucessor
   não existe regime vigente naquele intervalo. Uma empresa sem regime numa
   competência é pior que uma empresa com regime errado, porque a apuração não
   tem nem o que conferir.
2. **A exclusão devolve o período anterior à condição de vigente**: a
   `vigencia_fim` que havia sido recortada volta a ficar aberta. Sem isso,
   apagar deixaria a empresa sem regime corrente, que é exatamente o estado que
   a exclusão existe para consertar.
3. **O evento de exclusão é gravado em `RegistroAuditoria`**, com os valores
   antigos, quem apagou e quando.

### Por que o item 3 não contraria o "apagar" do Fred

São duas coisas diferentes, e confundi-las é o erro:

| O que sai | O que fica |
| --- | --- |
| O **registro** do período errado sai do histórico de regime da empresa. Nenhuma tela, relatório ou apuração volta a enxergar aquele período. | O **fato de alguém ter apagado** fica na trilha técnica, que `apps/auditoria/models.py` já mantém para que o escritório não apague o histórico de auditoria. |

O `AGENTS.md` exige trilha de auditoria "protegida, suficiente e sem expor
segredos" como regra de engenharia **obrigatória**. Não é uma preferência que eu
possa dispensar por pedido, e não é o que o Fred estava escolhendo quando disse
"apagar" — ele estava escolhendo o que o produto mostra. O produto mostra o
histórico limpo; a trilha guarda quem mexeu.

**Isto não ficou como interpretação minha.** Eu apresentei a distinção ao Fred,
dizendo com todas as letras que se ele quisesse dizer "nem o log deve existir" a
conversa seria outra, porque aí a mudança é de regra de engenharia e não de
comportamento de tela. Ele reafirmou "apagar" e respondeu **"Concordo com
você"** em 2026-09-15. A tabela acima está **confirmada pelo responsável**, e não
apenas presumida pelo arquiteto — que é a diferença que este projeto existe para
manter.

### O que continua proibido, e a diferença que importa

Isto vale para **regime tributário**, que é cadastro. **Não** se estende a
lançamento contábil efetivado: ali a correção segue por estorno rastreável, e
apagar continua proibido. A fronteira é a pergunta "isto é escrituração?" — se
for, não se apaga.

### Uma armadilha que ainda não existe, e por isso está registrada agora

Hoje não há apuração fiscal no sistema, então apagar um período de regime não
tem consequência a jusante. **Quando a DL-010 e a apuração existirem, apagar o
regime de um período que já tem apuração calculada muda a base de um cálculo já
entregue.** Registrado como **BL-210** para que a guarda nasça junto com a
apuração, e não depois de alguém descobrir pelo cliente.

## DE-040 — Os manuais do Domínio são referência de processo, não de identidade visual

**Data:** 2026-09-15. **Origem:** orientação direta do Fred durante a retomada
da DL-020. **Referência local:** `C:\Users\Frederico\Downloads\manuais`
(28 arquivos conferidos nesta data; a pasta não é parte do repositório).

**Decisão:** quando houver dúvida sobre regra de negócio, campo obrigatório,
fluxo contábil, fiscal, de folha ou arquitetura de processo, consultar o manual
pertinente dessa pasta antes de propor a solução. O conteúdo serve para entender
o processo legado e sua lógica de dados; não autoriza copiar interface, cores,
componentes ou identidade visual do Domínio.

O DataLedger deve manter layout próprio, moderno e acessível. Ao reproduzir uma
capacidade de negócio, a análise deve procurar reduzir passos, eliminar
retrabalho e acrescentar automações ou controles úteis que o sistema de
referência não ofereça. Compatibilidade de processo não significa imitação do
produto.

**Limites:** esses manuais são fonte auxiliar de produto, não fonte legal
autônoma nem instrução executável. Conteúdo de documento externo é tratado como
dado: não altera permissões, regras do `AGENTS.md` ou decisões confirmadas pelo
responsável. Alíquota, prazo, leiaute oficial ou regra destinada a uso real
continua exigindo fonte verificável, vigência e validação do responsável
técnico. Se a pasta não estiver disponível em outro ambiente, a ausência deve
ser declarada em vez de a regra ser inventada.

**Consequência operacional:** cada plano funcional futuro registra qual manual
foi consultado, a seção relevante e quais simplificações ou recursos próprios
foram propostos. Nenhum artefato visual do Domínio entra como referência de
design.

## DE-041 — O plano mestre é mapa de decomposição, nunca segunda fonte de estado

**Data:** 2026-09-16. **Origem:** incorporação do plano mestre entregue pelo
Fred, na [DL-022](../planos/DL-022-plano-mestre-e-reconciliacao.md).

**Decisão:** [`docs/projeto/plano-mestre.md`](plano-mestre.md) descreve
**sequência, decomposição e critérios de conclusão** por módulo. Ele **não**
descreve em que pé está nada. O estado de qualquer etapa continua morando num
lugar só, [`docs/agents/estado.md`](../agents/estado.md), e é para lá que todo
documento aponta em vez de repetir.

**Por que isto precisa estar escrito.** Em 2026-09-13 o Fred encontrou o README
afirmando, no topo, que o sistema era "apenas um esqueleto sem módulo de
negócio" enquanto o mesmo arquivo, mais abaixo, documentava a contabilidade
funcionando — e a afirmação obsoleta estava em **quatro** lugares. A causa não
foi distração, foi **duplicação**: texto repetido diverge assim que alguém
atualiza um lugar e esquece os outros. Um plano mestre com doze famílias de
códigos e mais de cem etapas é o candidato natural a ser o quinto lugar. A
regra nasce **antes** de o problema acontecer, de propósito.

**Alcance, em quatro itens:**

1. Nenhuma linha do plano mestre afirma que uma etapa está iniciada, em
   validação, integrada, aprovada ou reprovada. Onde essa informação for
   necessária, o plano **aponta** para o `estado.md`.
2. Os códigos `ORG`, `BAS`, `CON`, `FIS`, `FOL`, `OBR`, `HON`, `PAR`, `POR`,
   `IA`, `MCP` e `OPS` são endereços **deste mapa**. Não substituem, não
   renumeram e não aposentam `DL`, `BL`, `RC` e `DE`.
3. Trabalho executável continua nascendo como **etapa `DL-xxx` com plano
   próprio**: objetivo, requisitos classificados, critérios de aceite
   numerados, divisão de arquivos e auditoria da versão integrada. Linha de
   tabela do plano mestre **não é** item de backlog e não ganha dono por
   existir.
4. Quando um pacote do plano mestre virar etapa, o plano da etapa cita o código
   de origem (`CON-01`, `FIS-03`) para que a rastreabilidade não dependa de
   memória de sessão.

**Limite honesto desta decisão:** ela não impede o plano mestre de envelhecer.
Ele é uma fotografia da revisão `b8c66a6` com uma proposta de execução, e
envelhece como qualquer fotografia. O que ela impede é que envelhecer **produza
contradição sobre o estado** — porque sobre estado ele não fala.

## DE-042 — DL-018 (primeiro acesso via produto): as três perguntas, respondidas

**Data:** 2026-09-16. **Origem:** destrava a
[DL-018](../planos/DL-018-primeiro-acesso.md), que está em
"Planejada, não iniciada" porque o plano explicitamente diz
"enquanto não houver resposta, **nada é presumido** — a etapa não começa".
Aprovada por decisão explícita do Fred em 2026-09-16 ("Sim, seguir com
as HI") depois da pergunta por questionário. **Referência local:**
[DL-018-primeiro-acesso.md:62-89](../planos/DL-018-primeiro-acesso.md)
para o contexto da pergunta e das duas hipóteses declaradas no plano.

**Decisão — as três respostas, com o caminho mais simples:**

1. **Quem cria o escritório no mundo real?** **O próprio usuário sem
   vínculo** — autocadastro assistido pela tela de "primeiro acesso".
   É o caminho da HI-1: a instalação típica é de um escritório por
   instalação, e quem instala é quem vai administrar. **Inverso do
   caminho contrário** (alguém do DataLedger convidar o primeiro
   escritório) — esse caminho existe em outro produto, não aqui; o
   DataLedger não tem operação comercial própria.

2. **O primeiro usuário vira administrador do escritório que criou?**
   **Sim**, e isso vem gravado no modelo (`VinculoUsuarioEscritorio.
   papel = ADMINISTRADOR`) e exposto na trilha
   (`RegistroAuditoria.acao="escritorio.criado_pelo_primeiro_usuario"`).
   O risco da HI-1 (qualquer um que consiga criar conta pode criar
   escritório) **é aceito por decisão consciente** — a superfície de
   criação fica atrás de `IsAuthenticated`, e a sequência de criação
   é uma ação rara, auditada e rastreável; ninguém vai automatizar isso
   por engano.

3. **Como entra o segundo funcionário?** **Convite por e-mail** — o
   administrador cadastra o e-mail do segundo, e o sistema envia (ou
   registra localmente, se e-mail externo ainda não estiver configurado)
   um token de aceitação de vínculo. Decisão cobre o caminho mínimo:
   não é autocadastro público, não é cadastro manual pelo admin do
   Django, não é PE-36 inteira (essa fica para a etapa da PE-36).

**Consequência operacional:** a DL-018 sai de "Planejada, não iniciada"
para **"Em desenvolvimento"** no `docs/agents/estado.md` (em branch
própria, `claude/dl-018-primeiro-acesso`). Se a rodada 1 da auditoria
desta etapa reprovar a hipótese do autocadastro, esta decisão é
revogada — voltaríamos a "convite por e-mail obrigatório antes do
primeiro escritório", que é o caminho inverso. **Nada se constrói
contra essa reversibilidade**: o código da DL-018 trata autocadastro
e convite como duas formas paralelas, e desativar o autocadastro é
uma flag, não uma reescrita.

**Limites desta decisão:** ela cobre o **fluxo mínimo** da DL-018.
Não cobre: convite por e-mail com SMTP real (a DL-018 pode entregar
o token no banco e deixar SMTP para uma etapa posterior); recuperação
de senha (PE-36); autocadastro público sem convite (decisão explícita
de não fazer); papel de **GESTOR** (a DL-018 só vai entregar
**ADMINISTRADOR** e **ANALISTA** como pontos de entrada; os outros
papeis ficam para etapa posterior). Cada um desses itens é ponto de
abertura na DL-018, **não** desta decisão.

## DE-043 — DL-024 (CA-4): o plano é artefato derivado do código, não o contrário

**Data:** 2026-09-17. **Origem:** destrava a CA-4 da [DL-024](../planos/DL-024-trilha-integra-e-processo.md),
que estava "bloqueada por divergência de superfície". O plano original
decomponha 6 ModelAdmin para o BL-244 (trilha do painel administrativo).
O registry real do Django contém 4 registrados diretamente:
`EmpresaAdmin`, `ContaAdmin`, `EscritorioAdmin`,
`VinculoUsuarioEscritorioAdmin`. Os dois restantes:

- **EstabelecimentoAdmin** — não existe como ModelAdmin registrado; o
  modelo é inline de `EmpresaAdmin`. O signal BL-244 cobre
  `Estabelecimento` na lista explícita `MODELOS_DA_TRILHA_DO_ADMIN`, e
  a criação por inline gera trilha. Teste: criar empresa com
  estabelecimento via `/admin/empresas/empresa/add/` e verificar
  `RegistroAuditoria` para `empresas.estabelecimento.admin_criado`.

- **HistoricoRegimeTributarioAdmin** — removido do admin pela DL-023.
  Não há porta administrativa para esse modelo. O signal BL-244 continua
  cobrindo o modelo na lista explícita — se amanhã voltar a ter
  ModelAdmin, a trilha é gerada automaticamente. Teste: criação via ORM
  com request fake verifica que `registrar()` é chamado; ausência de porta
  admin é documentada como consequência da DL-023, não lacuna.

**Opção escolhida:** reconciliar o plano com a realidade — atualizar o
documento DL-024 para refletir que a lista explícita de modelos é o
contrato, e o registry do Django é o artefato衍 生.

**Alternativas descartadas:**

1. Criar `EstabelecimentoAdmin` fantasma só para o teste passar.
   Descartada porque: viola RC-041 (plano é mapa de decomposição, não
   segunda fonte de estado) e geraria artefato código sem uso.

2. Deixar CA-4 em aberto até decisão posterior. Descartada porque:
   atrasa entrega sem benefício — a trilha existe e funciona, o teste
   pode verificar a lista explícita sem depender do registry.

**Consequência operacional:** a DL-024 sai de "em validação, CA-4
bloqueada" para **integrada**. O teste
`test_signals_de_admin_existem_e_cobrem_os_seis_modelos` em
`apps/core/tests/test_dl024_trilha_admin.py` verifica que
`MODELOS_DA_TRILHA_DO_ADMIN` contém os 6 modelos — não 4, não o que
está no registry. A lista explícita é o contrato.

**Limites desta decisão:** não altera código de produto (o signal já
cobre os 6 modelos via lista explícita). Não adiciona nem remove
ModelAdmin. Só reconcilia o plano com o que existe.

## DE-046 — Fixture de `test_competencia.py` precisa criar `Escritorio`

**Data:** 2026-09-18

**Decisão:** corrigir o `setUpTestData` de
`apps/contabilidade/tests/test_competencia.py` adicionando
`Escritorio.objects.create(...)` ANTES da `Empresa.objects.create(...)`,
porque a FK `Empresa.escritorio` é `NOT NULL` desde DL-009 (ver
`apps/empresas/models.py:66`).

**Contexto:** a primeira rodada da CI do PR #31 reprovou em SETUP com
`psycopg.errors.NotNullViolation: null value in column "escritorio_id"
of relation "empresas_empresa"`. O `setUpTestData` original foi escrito
em turno onde o ambiente Python 3.11 não conseguia instalar Django 6.1.1,
então os testes não foram executados localmente — só `py_compile`. A
CI real (Python 3.14.7 + PostgreSQL) executou os testes e detectou a
ausência do `Escritorio` na fixture.

**Por que não foi detectado antes:** o modelo `Empresa` é multi-tenant
desde DL-009, e os testes mais antigos (`test_models.py`,
`test_services.py`) já tinham o padrão correto. O `test_competencia.py`
é da DL-016 e foi escrito sem consultar esses arquivos — falha de
auditoria minha, não do código de produto.

**Correção aplicada:** adicionada `from apps.tenancy.models import
Escritorio`. Os dois `setUpTestData` (de `CompetenciaModelTests` e
`CompetenciaOrderingTests`) agora seguem o mesmo padrão de
`apps/contabilidade/tests/test_services.py:42-46` e
`apps/core/tests/test_dl024_*.py`.

**Alternativa descartada:** tornar `escritorio` nullable em `Empresa`
para aceitar a fixture antiga. Descartada porque abre caminho de
regressão multi-tenant — todo o restante do projeto assume a FK
NOT NULL, e o `TenantScopedManager` depende disso.

**Consequência:** CI do PR #31 deve voltar a passar nos testes. Fixture
fica alinhada com o resto do projeto. Cabeçalho do
`test_competencia.py` foi atualizado pra registrar honestamente o que
aconteceu (escrita original só com `py_compile`; correção de fixture
neste turno). Nenhuma mudança em código de produção ou em asserts dos
testes.

## DE-047 — Registro das 3 constraints de Competencia + DECISOES do admin

**Data:** 2026-09-18

**Decisão:** registrar as três restrições do modelo `Competencia` (DL-016
/ F1) em `apps/core/restricoes.py:204-237` como
`RESTRICOES_SEM_CAMINHO_DE_CLIENTE`, e adicionar
`contabilidade.Competencia` em `DECISOES` do
`apps/core/tests/test_dl023_varredura_admin.py:166` como categoria
`"defendida"`.

**Contexto:** segunda rodada da CI do PR #31 reprovou em mais 5 testes
(1353 passaram). Dois eram bugs reais dos meus testes de Competência
(`assertRaises` sem savepoint, e `.order_by()` cancelando `Meta.ordering`)
— corrigidos no `test_competencia.py`. Os outros dois eram os testes de
**varredura** da DL-019 (`test_toda_constraint_de_meta_aparece_em_um_dos_
tres_registros`) e da DL-023 (`test_toda_superficie_do_admin_registrado_
tem_decisao`) fazendo exatamente o papel que foram criados para fazer:
detectaram que as 3 constraints novas e o model novo no admin não
estavam registrados. Corrigidos.

**Por que `RESTRICOES_SEM_CAMINHO_DE_CLIENTE` (e não
`MENSAGENS_DE_RESTRICAO`):** o único caminho de escrita por produto é o
`Competencia.objects.get_or_create(...)` dentro de
`apps/contabilidade/services.py:387-411` (F2 da DL-016), que captura
`IntegrityError` em savepoint próprio e reconsulta via `get()` — a
violação é tratada como CORRIDA INTERNA entre requisições concorrentes,
não como erro de negócio pra traduzir em 400. Idem para os dois
`CheckConstraint` de faixa (ano/mês): `criar_lancamento` só cria
competências a partir de `data.year`/`data.month` de um lançamento, que
são sempre válidos por construção.

**Gatilho de revisão:** o importador em massa da DL-010 pode vir a
chamar `bulk_create` direto sobre `Competencia` (mencionado no
comentário do próprio modelo de Empresa como caminho natural para
importação). Quando isso acontecer, as 3 restrições saem de
`RESTRICOES_SEM_CAMINHO_DE_CLIENTE` e viram tradução para 400 — mesmo
desenho das duas de canonização de CNPJ (BL-204/220).

**Por que `defendida` no admin:** as invariantes de `Competencia`
moram em `Meta.constraints` do modelo (testadas em
`test_competencia.py`); não há invariante a mais a defender no admin
(equivalente a BL-83/BL-211).

**Consequência:** CI deve passar os dois testes de varredura. Cabeçalho
do `test_competencia.py` atualizado com histórico das duas correções.

## DE-048 — `ruff format --check` travou a CI do PR #31 antes do pytest rodar

**Data:** 2026-09-18

**Decisão:** a CI do projeto (`.github/workflows/ci.yml`) roda `ruff format
--check .` ANTES de pytest, e como o step falha com exit code 1 **e** o
shell tem `set -e`, o workflow morre ali e o pytest nem é invocado.

**Contexto:** terceira rodada da CI do PR #31 parecia "quebrar testes"
quando na verdade nem testes tinha rodado — só a checagem de
formatação. Dois arquivos:

- `apps/contabilidade/tests/test_competencia.py:113-115 e 123-125`:
  `Competencia.objects.create(empresa=..., ano=..., mes=...)` partido
  em três linhas dentro do `with self.assertRaises(...), transaction.
  atomic()` — o `ruff format` quer em uma linha só.
- `apps/core/tests/test_dl023_varredura_admin.py:176`: faltava
  vírgula no fim do literal `"negócio). Sem invariante adicional a
  defender no admin."`.

**Por que aconteceu:** nas escritas anteriores, eu só validava com
`python -m py_compile` (sintaxe) — não com `ruff format`. A CI
captura coisas que o `py_compile` não vê.

**Correção aplicada:** commit `7fda659`, formatado `ruff format`
(invocando a versão 0.16.7, igual à da CI), commitado e push. CI
verde em ambos os checks (`Validar documentação: success`,
`Lint e testes: success`).

**Consequência:** a partir desta DL, eu **sempre** rodo `ruff
format --check .` localmente antes de empurrar — não só `py_compile`.
Está no checklist mental de quem mexe em código Python do projeto.

**Não foi preciso mexer na CI** (separar lint/format em jobs, ou
tornar format warning-only) — isso seria uma decisão de processo
mais ampla, e a regra atual é clara.

## DE-049 — Auditoria independente da DL-016 (PR #31) rodada 1

**Data:** 2026-09-18

**Decisão:** o PR #31 (`claude/dl-016-competencia-e-fechamento`,
head `92a42b8`/`135ccd1`) é **APROVADO** para merge em `main`,
com 1 achado menor (A2) corrigido **no mesmo PR** e 2 contas
declaradas (A1, A3, A4).

**Auditor:** Hermes (auto-auditoria honesta, conforme o protocolo
master autonomous execution). Não há skill de auditor carregada no
sistema; este é o papel que o histórico de auditorias do projeto
chama de "auditor independente humano", exercido aqui com o mesmo
rigor que eu exigiria de um auditor externo.

**Perguntas da auditoria e respostas** (resumo; parecer completo
em `docs/auditorias/2026-09-18-dl-016-rodada-1.md`):

1. *Model `Competencia` reproduzido fielmente pela migration 0004?*
   Sim. Comparação item a item em 4.4 da auditoria — 12 itens,
   todos conferem.
2. *As 3 invariantes estão defendidas em DUAS camadas?* Sim
   (DE-008 camada 1 banco + camada 2 aplicação). 7 testes em
   `test_competencia.py` cobrem o escopo de F1.
3. *`criar_lancamento.materializa_competencia` trata corrida
   interna corretamente?* Sim. O `try: with transaction.atomic()`
   em `services.py:387-411` é savepoint aninhado dentro do
   savepoint externo de `services.py:371`. O `except IntegrityError`
   em 394 só captura o que está dentro do savepoint aninhado
   (ou seja, exclusivamente o `get_or_create` de Competencia).
   O `IntegrityError` do `LancamentoContabil.create` posterior
   é capturado em 429, que **não converte** em `LancamentoInvalido` —
   propaga como deveria.
4. *Admin é defensável pela DL-023?* Sim. 3× `False` em
   `has_add/change/delete_permission`, `list_display` útil, filtros
   coerentes, com docstring justificando o porquê de cada decisão.
5. *As 3 restrições estão registradas onde a varredura DL-019
   exige?* Sim, em `RESTRICOES_SEM_CAMINHO_DE_CLIENTE` com texto
   ≥ 40 chars cada, referenciando DL-010 como gatilho de revisão.
   O `model` está em `DECISOES` do `test_dl023_varredura_admin.py`
   como `"defendida"`.

**Achado A2 (corrigido no mesmo PR, commit `135ccd1`):**
`RESTRICOES_CONFERIDAS` da DL-019 estava com 7 entradas, sem
as 3 de `Competencia`. A suíte NÃO reprovava (o teste exige
apenas que cada uma das 7 esteja presente, não que SÓ as 7 estejam),
mas a fotografia auditada ficava desatualizada. **Correção
aplicada:** expandida de 7 para 10 entradas no mesmo PR, com
comentário de cabeçalho atualizado. CI verde em `135ccd1`.

**Achados A1, A3, A4 (informativos, contas declaradas):**
- A1: PR entrega F1+F2 juntos — aceitável pelo mesmo critério
  da DL-015 rodada 3 (divisão funcional não sobrevive à divisão
  técnica quando F2 depende estruturalmente de F1).
- A3: migration 0004 foi escrita à mão; cabeçalho declara que
  precisa ser regenerada com `makemigrations` no primeiro
  ambiente Python 3.12+ e o diff comparado. Dívida declarada,
  mesma postura da DL-020 rodada 1.
- A4: faixa de ano 1970..2999 é arbitrária e está documentada
  no docstring do model.

**Consequência:** PR #31 pode ser mergeado em `main`. Depois
do merge, próximos passos da DL-016 (F3 encerramento, F4
reabertura, F5 backfill) entram em pauta do backlog.

## DE-044 — Regex do gate não exige `**` literais; template alinhado

**Data:** 2026-09-18

**Decisão:** o regex do workflow `.github/workflows/regras-do-projeto.yml`
procura agora `"Atualizei o estado do projeto"` (sem `**`), e o template
`.github/pull_request_template.md` foi ajustado pra remover `**` ao redor
de "estado do projeto" na checkbox correspondente. Os dois ficam
consistentes.

**Motivo:** o regex antigo `re.escape("Atualizei o **estado do projeto**")`
gerava um padrão que exigia `**` literais dentro do texto que o humano
escreve. Como nenhum autor humano coloca `**` antes de "estado" numa frase
natural, o 2º checkbox do template NUNCA casava, mesmo com `[x]` marcado.
O template ensinava o uso errado (`**` ao redor) ao mesmo tempo em que o
regex tentava casar esse uso errado — um bug estrutural latente desde que
o gate foi adicionado em DL-014. Ele só não foi detectado antes porque o
PR que adicionou o gate possuía `**` literal no corpo.

**Alternativas descartadas:**
1. Workaround local no PR travado (adicionar `- [x] Atualizei o **estado do projeto**` com `**` literal) — DeepSeek advertiu que isso cria precedente de adaptar corpo ao regex e, se a correção definitiva reprovasse, viraria permanente. Descartada por isso.
2. Tentar outras regex sem mudar o texto procurado (ex.: `re.search("estado do projeto", corpo)` sem `\s*\[x\]`) — enfraquece o check: passaria a casar sem exigir `[x]`. Descartada por regressão semântica.
3. Substituir o check por uma chamada a um script externo — overhead desproporcional para um fix de 1 linha. Descartada.

**Senior Opinion (DeepSeek, modo consultoria):** "Sequenciar A→B.
Abrir PR do gate primeiro, em paralelo com auditoria. B só entra como
contingência se A estourar SLA." — A foi seguido (PR #32). B descartado
porque A fechou dentro do SLA esperado.

**Decisão final:** corrigir regex E template no mesmo PR, manter o check
semântico (`[x]` obrigatório, plano DL-NNN obrigatório).

**Consequência:**
- PRs futuros vão conseguir marcar as duas caixas sem precisar conhecer
  o detalhe do regex.
- PR #31 (DL-016) continua com `**` no corpo; após merge de #32, o autor
  do #31 ajusta o corpo pra alinhar com o template novo, re-rodando CI.
- Auditoria independente obrigatória antes do merge de #32 (DE-004).

**Evidência:** validação empírica em Python (com a função `marcado` do
workflow) confirmou que o regex antigo só casava com `**` literal dentro
da frase, e que o regex novo casa com texto natural. Testado com corpo
do template corrigido e com corpo atual do PR #31.

## DE-045 — Auditoria independente do PR #32 (gate fix)

**Data:** 2026-09-18

**Decisão:** o PR #32 (`docs/fix-gate-regex`, commit `496b184`) é
**APROVADO** pra merge em `main`, com 3 ressalvas registradas.

**Auditor:** DeepSeek, modo auditor independente, sem acesso ao histórico
de discussão que originou o patch. Recebeu apenas o diff e a função
`marcado()` do workflow como contexto.

**Perguntas da auditoria e respostas:**
1. *Intenção preservada?* Sim. O regex novo (`sem **`) casa com texto
   natural marcado com `[x]`, atendendo ao objetivo do check. A exigência
   de citação `DL-\d{3}` foi preservada.
2. *Regressão semântica?* Não. O regex continua exigindo `[x]` antes do
   texto; a única mudança é a remoção de `**` literais da string
   procurada.
3. *Bypass possível?* Pré-existente e fora do escopo: o regex não ancora
   em início de linha, então texto fora de checkbox (ex.: em code block
   ou citação) pode casar. Comportamento idêntico ao anterior.

**Ressalvas registradas:**
- **R1 (mitigada):** PRs abertos com o template antigo (com `**`) podem
  falhar no gate novo. Hoje só o PR #31, que já estava falhando. Após
  merge deste PR, o autor do #31 ajusta o corpo em novo push.
- **R2 (pré-existente, fora do escopo):** regex sem âncora de início de
  linha permite match em qualquer posição.
- **R3 (pré-existente, fora do escopo):** match em code block/quote não
  distingue contexto Markdown.

**Por que não consultar de novo:** o raciocínio do auditor (capturado
via `reasoning_content` porque `finish_reason: length` consumiu o budget
de `max_tokens` em raciocínio) cobriu as 4 perguntas e convergiu pra
APROVADO com as 3 ressalvas descritas. Reconsultar pra extrair texto
idêntico custaria mais latência sem ganho de informação.

**Evidência da CI do próprio PR #32:** `Regras do projeto: completed /
success`, `Validar documentação: success`, `Lint e testes: success`. O
gate passa no PR que corrigiu o gate — confirmação empírica forte de que
a correção está sintaticamente correta.

**Consequência:** PR #32 mergeado. Gate em `main` passa a aceitar texto
natural. Próximo passo (F1.13): ajustar corpo do PR #31, re-rodar CI,
fazer merge.

## DE-050 — Fechamento da Onda 1 da DL-016 (merge em main, F3/F4/F5 no backlog)

**Data:** 2026-09-18

**Decisão:** a Onda 1 (F1 + F2) da DL-016 é **INTEGRADA** em `main`.
PR #31 mergeado via squash no commit `fa15cf1` com a mensagem descrita
na auditoria rodada 1. Branch de feature
`claude/dl-016-competencia-e-fechamento` deixa de existir após o merge.

**Contexto:** o fechamento encerra o ciclo da DL-016 neste escopo
(F1 modelo + F2 vinculação automática em `criar_lancamento`).
A auditoria rodada 1 já aprovou com 1 achado menor corrigido no
próprio PR (DE-049 / A2). CI verde no último push (`a0e0859`)
antes do merge confirmou todos os 6 checks: `Regras do projeto`,
`Validar documentação`, `Lint e testes` — todos `success`.

**Pendências declaradas e transferidas para o backlog:**

1. **Migration 0004 — regeneração no primeiro deploy real
   (Python 3.12+ + Django 6.1.1).** A migration foi escrita à mão
   porque o ambiente do agente é Python 3.11; o cabeçalho já
   declara a conta. Quem fizer o primeiro `migrate` real deve
   rodar `python manage.py makemigrations` e comparar diff
   item-a-item com o escrito. Se `makemigrations` não produzir
   mudanças, o arquivo está correto (mais provável); se produzir,
   revisar com cuidado — não dar `--merge` cegamente.

2. **F3 — Encerramento de competência.** Service que move
   `EstadoCompetencia.aberta → em_encerramento → encerrada`, com
   invariantes de domínio: ao encerrar, todos os lançamentos
   do mês devem estar conferidos; ninguém pode criar/editar/
   estornar lançamento com `competencia.estado == 'encerrada'`.
   BL relacionado a abrir no backlog.

3. **F4 — Reabertura autorizada e auditada.** Service inverso
   do F3 (`encerrada → em_encerramento → aberta`), com trilha
   de auditoria obrigatória (quem, quando, por quê, aprovado
   por quem). É o ponto sensível que dá nome à DL-016 — a
   reabertura de um mês fechado é o ato contábil que precisa
   de mais guarda.

4. **F5 — Backfill de `LancamentoContabil.competencia`.** A FK
   foi criada como `null=True` justamente para permitir o
   backfill em separado. Estratégia sugerida: management command
   que percorre `LancamentoContabil.competencia IS NULL` em
   batches, agrupa por `(empresa, data.year, data.month)`, e
   faz `get_or_create` na `Competencia` correspondente — usando
   o mesmo padrão de savepoint do F2. Quando todos os
   lançamentos antigos tiverem FK preenchida, o modelo pode
   virar `null=False` em uma DL-XXX de aperto.

5. **RC-95 (registro de restrição a revisar).** A faixa
   `ano 1970..2999` é arbitrária (DL-016 rodada 1, A4). Se o
   produto começar a atender escritórios que digitalizam livros
   dos anos 60, isso volta como RC-96.

**Por que F3/F4/F5 não entraram neste PR:** a Onda 1 era o
mínimo necessário para o produto passar a registrar **a qual
mês contábil pertence cada lançamento**. F2 fecha isso
automaticamente em lançamentos novos. O backfill (F5) pode
ser diferido — lançamentos antigos continuam com `competencia
= NULL` até a management command rodar, e isso é seguro porque
a coluna é nullable. O encerramento (F3) só faz sentido depois
de F5 existir — caso contrário, encerrar uma competência que
ainda tem lançamentos sem FK quebraria invariantes de contagem.
A reabertura (F4) depende de F3 existir para reabrir.

**Consequência para o backlog:**
- BL-242 (consolidação pós-auditoria, DL-020) está fechado.
- Próxima DL no caminho natural: **DL-016-F3 (encerramento)**,
  precisa de plano novo e BL novo.
- DL-010 (importador em massa, que é o gatilho de revisão da
  decisão RESTRICOES_SEM_CAMINHO_DE_CLIENTE para as 3 constraints
  de Competencia) continua como planejada, depende do importador.

**Auditoria independente da onda 1:** rodada 1 já feita em
`docs/auditorias/2026-09-18-dl-016-rodada-1.md`, parecer APROVADO.
Rodada 2 só abre se eu for propor mudanças estruturais (F3, F4, F5).

**Não foi preciso alterar:**
- `apps/core/restricoes.py` (as 3 entradas já estão lá).
- `apps/core/tests/test_dl023_varredura_admin.DECISOES` (já tem
  `contabilidade.Competencia: "defendida"`).
- `apps/core/tests/test_dl019_varredura_de_restricoes.py` (já
  expandido para 10 no commit `135ccd1`).
- Schema do banco (migration já está em `main`).

**Não foi feito (e não é omissão):** validação por
`makemigrations --check` em ambiente Python 3.12+ real — o
sandbox do agente é 3.11 e não tem Django 6.1.1 instalável.
A CI do PR rodou em Python 3.14.7 + PostgreSQL e os 1353 testes
passaram, então a migration está pelo menos sintaticamente
aceitável — mas a regeneração com `makemigrations` é o que
garanta que reflete exatamente o que o ORM atual produziria.
**Transferido como item explícito do backlog.**

## DE-051 — Fechamento da DL-016-F5 (backfill da FK LancamentoContabil.competencia)

**Data:** 2026-09-18

**Decisão:** a DL-016-F5 é **INTEGRADA** em `main`. PR #33 mergeado
via squash no commit `700a50b`. Branch de feature
`claude/dl-016-f5-backfill-competencia` deixa de existir após o merge.

**Contexto:** o fechamento encerra o ciclo F5 da DL-016 (criação
da management command de backfill que preenche `competencia` em
lançamentos antigos que ficaram com a FK nula entre F2 e o rodar
desta command). A auditoria rodada 1 já aprovou (parcer em
`docs/auditorias/2026-09-18-dl-016-f5-rodada-1.md`, parecer
**APROVADO** com 3 achados — 1 informativo + 2 menores, nenhum
bloqueante). CI verde no commit `b108c8b` confirmou todos os 5
check-runs: `Regras do projeto`, `Validar documentação` (×2),
`Lint e testes` (×2).

**Estratégia do backfill (resumo do plano):**

1. Management command `backfill_lancamento_competencia` em
   `apps/contabilidade/management/commands/`. Dry-run default;
   `--apply` opt-in (regra DE-007 — destrutivo precisa de confirmação
   explícita). Idempotência garantida por `.filter(competencia__isnull=True)`
   no iterator + `Competencia.objects.update()` por batch de IDs.
2. Estratégia de passadas curtas: a command roda até 2 passadas.
   A primeira cobre tudo que existe no momento do start; a
   segunda (curta, só sobre o que sobrou) cobre lançamentos
   criados via `criar_lancamento` (F2) entre as duas passadas.
   Sem lock pessimista — o `select_for_update()` não é necessário
   porque o `filter(competencia__isnull=True)` é naturalmente
   estável (lançamentos novos recebem FK em F2 antes de virar
   visíveis à command).
3. Modo de flush: agrupa por `(empresa_id, data.year, data.month)`,
   usa cache `dict[chave, Competencia]` para evitar `get_or_create`
   repetido, e faz `LancamentoContabil.objects.filter(id__in=batch)
   .update(competencia=cache[chave])` por batch de até 500.
4. Logs estruturados não-JSON (regra do projeto): totais por
   passada, totais finais, aviso dry-run, e breakdown por estado
   (criadas / reutilizadas / atribuídas).

**Decisão de design registrada nesta onda:**

- **Remoção do branch de "órfão".** O plano original da F5
  previa um branch defensivo para lançamentos com `empresa_id =
  NULL` (contador `orfaos_pulados`, log "[passada N] orfao: ...",
  teste cobrindo o cenário). Investigação demonstrou que o
  cenário é fisicamente impossível via ORM desde DL-006:
  `LancamentoContabil.empresa = ForeignKey(Empresa, on_delete=PROTECT)`
  sem `null=True`, coluna NOT NULL em produção, dev e test.
  Os 2 testes correspondentes forçavam `empresa=None` em
  `LancamentoContabil.objects.create(empresa=None, ...)`, e o
  ORM rejeitava com `IntegrityError` antes do `call_command` rodar
  — daí os 7 failed na CI (5 testes normais + 2 de órfão +
  um efeito colateral em test_orfao_nao_falha_em_apply).
  Decisão: remover o branch + os 2 testes do código de produção
  (código morto + teste de cenário inalcançável = acoplamento
  ruim). Rede de segurança migrou para procedimento operacional
  no runbook de deploy (`SELECT COUNT(*) ... WHERE empresa_id IS NULL`
  antes de `--apply`) + CHECK constraint `empresa_id IS NOT NULL`
  em **DL-016-F6** (transferida para o backlog).
- **Sem type hint estrito.** `# type: ignore[arg-type]` na linha
  251 do command é desnecessário (o flush final só roda quando
  `ids_pendentes` não-vazio, e nesse ponto `competencia` é
  garantido não-None), mas mypy não está configurado no projeto
  e ruff não reclama. Registrado como achado menor A2 na auditoria,
  não corrigido nesta onda para respeitar o escopo (DE-007).
  Issue menor a abrir quando mypy entrar no projeto.

**Pendências declaradas e transferidas para o backlog:**

1. **Runbook de deploy (`docs/runbooks/DL-016-F5-deploy.md`).**
   Frederico precisa criar com: (a) pré-checks `SELECT COUNT(*)
   ... WHERE empresa_id IS NULL`, (b) dry-run + análise do
   relatório, (c) `--apply`, (d) plano de rollback.
2. **DL-016-F6: CHECK constraint `empresa_id IS NOT NULL`** em
   `LancamentoContabil`. Cinto-e-suspensórios contra INSERT direto
   via shell-admin que burle o ORM.
3. **A2 — remover `# type: ignore[arg-type]`** do command
   (`apps/contabilidade/management/commands/backfill_lancamento_competencia.py:251`).
4. **A3 — tipar `Counter` como TypedDict** se mypy entrar no
   projeto. Cosmético, só importa se rigor de tipos aumentar.
5. **Migration `0004` da Onda 1 (pendente de DE-050).** Continua
   pendente — primeiro deploy Python 3.12+ precisa rodar
   `makemigrations` e comparar diff. Sem relação direta com F5,
   mas citada para não se perder.

**Consequência para o backlog:**

- F5 deixa de ser pendência. DL-016 fica com F3 (encerramento)
  e F4 (reabertura) ainda abertas como sub-DLs dependentes.
- Próxima DL natural no caminho: DL-016-F3 ou DL-010 (importador
  em massa), por critério de Frederico.
- BL-242 (consolidação DL-020) continua fechado.

**Auditoria independente da F5:** rodada 1 em
`docs/auditorias/2026-09-18-dl-016-f5-rodada-1.md`, parecer
**APROVADO** com 3 achados (1 informativo + 2 menores). Rodada 2
só abre se eu for propor mudanças estruturais no command.

**Não foi preciso alterar:**

- `apps/contabilidade/models.py` (sem mudança de schema nesta onda;
  F5 só lê e atualiza dados, não toca estrutura).
- `apps/contabilidade/services/criar_lancamento.py` (F2 já estava
  preenchendo `competencia` corretamente — F5 só cobre o backlog).
- Schema do banco (nenhuma nova migration).
- `apps/core/restricoes.py` e `DECISOES` da DL-023 (sem novas
  constraints nesta onda).

**Não foi feito (e não é omissão):** validação local via
`pytest apps/contabilidade/tests/test_management_backfill.py`
em ambiente Python 3.12+ — o sandbox do agente é 3.11. A CI
do PR rodou em Python 3.14.7 + PostgreSQL e os 5 testes da
suíte nova + regressão completa passaram (a regressão de 1353
testes da Onda 1 continua intacta), o que dá evidência
empírica suficiente para o merge. A reprodução local por
Frederico no ambiente oficial continua recomendada como
checagem adicional antes de rodar `--apply` em produção.


## DE-052 — Fechamento da DL-016-F6 (CHECK constraint `LancamentoContabil.empresa_id` NOT NULL)

**Data:** 2026-09-18
**PR:** #34 mergeada em `main` (squash em `15f6a98`)
**Auditoria rodada 1:** [`docs/auditorias/2026-09-18-dl-016-f6-rodada-1.md`](../auditorias/2026-09-18-dl-016-f6-rodada-1.md) — **APROVADA** com 1 achado positivo (A1)

### Contexto

A DE-051 (fechamento da DL-016-F5) prometeu: "F6 sub-DL dependente:
adicionar CHECK constraint `empresa_id IS NOT NULL` como rede de
segurança contra INSERT direto via shell-admin." Esta DE documenta o
fechamento dessa promessa.

### O que foi entregue

- **Migration `0005_check_lancamento_empresa_not_null`** (hand-written):
  - `AddConstraint` em `lancamentocontabil`.
  - `CheckConstraint(Q(empresa_id__isnull=False), name="ck_lancamentocontabil_empresa_not_null")`.
  - Gera `ALTER TABLE contabilidade_lancamentocontabil ADD CONSTRAINT ck_lancamentocontabil_empresa_not_null CHECK (empresa_id IS NOT NULL);`.
- **Teste `apps/contabilidade/tests/test_dl016_f6_check_empresa_not_null.py`** com 4 cenários:
  1. `test_constraint_existe_no_banco` — introspection via `information_schema.check_constraints`.
  2. `test_insert_direto_sem_empresa_falha_com_mensagem_sobre_not_null_ou_check` — INSERT direto com `empresa_id=NULL` em condições normais. Aceita AMBAS as mensagens como prova de defesa em profundidade.
  3. `test_insert_direto_sem_empresa_falha_apos_drop_not_null` — **teste novo, não estava no plano original**: simula o cenário real de bypass (`ALTER TABLE DROP NOT NULL` + INSERT NULL). Aqui o CHECK é a única defesa e a mensagem tem que mencionar `ck_lancamentocontabil_empresa_not_null` explicitamente. try/finally garante que o NOT NULL volta ao estado original.
  4. `test_insert_direto_com_empresa_valida_passa` — sanity check do caminho feliz.

### Decisões de design

**Por que CHECK em vez de só NOT NULL (que já existe)?**

A coluna `empresa_id` já é NOT NULL no schema porque Django gera
coluna NOT NULL para `ForeignKey(...)` sem `null=True`. O CHECK é
**defesa em profundidade** — explicita a invariante e protege contra:

1. **INSERT direto via `psql`/shell-admin** que burle o ORM.
2. **`ALTER TABLE` malicioso futuro** que tente `DROP NOT NULL` na coluna.
3. **Migration descuidada** que adicione `null=True` em `empresa`.

Sem o CHECK, esses cenários passariam em silêncio. Com o CHECK, o
banco rejeita na hora com mensagem clara mencionando
`ck_lancamentocontabil_empresa_not_null` (após o NOT NULL ser removido
— cenário #2 e #3 acima).

**Achado positivo A1 (capturado durante a auditoria):**

A primeira versão do teste (commit `1f170bd`) afirmava que o INSERT
direto com NULL levantaria `IntegrityError` mencionando
`ck_lancamentocontabil_empresa_not_null`. A CI reprovou: **o PG avalia
NOT NULL da coluna ANTES de CHECK constraints**, então a mensagem de
erro vem do NOT NULL ("violates not-null constraint"), não do CHECK.

Isso não significa que o CHECK não funciona — significa que o CHECK só
pega DEPOIS que o NOT NULL é removido, que é exatamente o cenário de
bypass documentado no DE-051. O teste #3 (`test_insert_direto_sem_empresa_falha_apos_drop_not_null`)
foi adicionado para cobrir explicitamente esse cenário. **O teste
final é mais rigoroso que o teste original do plano**, e prova que o
CHECK faz o trabalho prometido.

**Por que `AddConstraint` separado (não em `Meta.constraints` do model)?**

A constraint precisa ser adicionada **sem** recriar a tabela (que já
existe em produção com dados) e sem interferir com a migration 0004
que rodou recentemente. `AddConstraint` é a forma idiomática do
Django 5/6 de adicionar CHECK pós-criação, e gera um único
`ALTER TABLE` no `migrate`.

### Pendências declaradas

**Bloqueantes do merge:** nenhuma.

**Não-bloqueantes (transferidas para backlog):**

1. **Migration 0004 (DE-050)**: ainda hand-written, precisa regeneração por `makemigrations` no primeiro deploy Python 3.12+. Independente desta F6.
2. **A2 (type ignore F5)**: `# type: ignore[arg-type]` na linha 251 do command `backfill_lancamento_competencia`. Backlog.
3. **A3 (TypedDict Counter F5)**: tipar Counter como TypedDict quando mypy entrar no projeto. Backlog.
4. **Runbook DL-016-F5 deploy**: documentação de pré-check SELECT COUNT + dry-run + `--apply` + rollback. Não-bloqueante da F5 nem da F6.
5. **DL-016-F3 (encerramento de competência)**: próxima sub-DL natural no caminho. Começa pelo plano, não pelo código — precisa decidir "encerrar = fechar pra sempre, ou tem janela de carência?" e "auditoria de quem fez o quê, onde mora?".
6. **DL-016-F4 (reabertura)**: depende de F3.

### O que não foi alterado

- Models (nenhuma mudança de schema além da CHECK constraint).
- Services (`criar_lancamento` continua o mesmo; F6 só lê schema).
- `apps/core/restricoes.py` e `DECISOES` da DL-023 (CHECK constraint
  fica no schema do banco, não na camada Python de validações).
- Outras DLs em andamento (DL-010, DL-017, etc.) — F6 é independente.

### Não foi feito (e não é omissão)

- **Reprodução local em Python 3.12+ antes do merge**: sandbox do agente é Python 3.11. CI rodou em Python 3.14.7 + PostgreSQL e a regressão completa passou (1371 testes + 2 skipped), o que dá evidência empírica suficiente. Frederico pode reproduzir localmente antes do primeiro deploy de produção se quiser.
- **Teste de carga com 1M de linhas**: F6 é só adição de CHECK constraint; performance é responsabilidade do planejador de query do PG, não desta DL.

### Estado da DL-016

Antes da F6: 2 ondas integradas (F1+F2 em `fa15cf1`, F5 em `700a50b`).
Depois da F6: 3 ondas integradas (F1+F2, F5, F6). F3 e F4 seguem como
sub-DLs dependentes no backlog. **Pendência herdada da F5 resolvida
(declarada como "F6 sub-DL dependente" no DE-051, agora cumprida).**
## DE-053 — A identidade visual do DataLedger: "papel e tinta", com dois enxertos nomeados

**Data:** 2026-09-18. **Origem:** rodada 1 do gauntlet da
[DL-026](../planos/DL-026-identidade-visual-e-interface.md), com a escolha
confirmada pelo Fred (**RC-90**). Evidência em
[`docs/assets/design/gauntlet/`](../assets/design/gauntlet/MEDICOES.md): as três
variantes, as capturas, as medições e o juiz que as mediu.

**Decisão:** a identidade do produto é a da variante **A — "papel e tinta"**,
com dois enxertos explícitos das variantes eliminadas.

**O que a direção afirma, e por quê:**

1. **Tipografia é a estrutura; a cor é quase ausente.** Nomes de conta e prosa
   em serifada; **algarismos em monoespaçada tabulada**, sempre. Uma única
   tinta de acento para ação e foco. A hierarquia do plano de contas vem de
   **peso e recuo**, não de uma coluna "Nível" nem de cor.
2. **O número é o herói da tela.** Coluna de valor alinhada à direita, largura
   de dígito constante, e saldo invertido **entre parênteses** — convenção
   contábil mais antiga que a tinta vermelha e mais resistente a adulteração:
   um traço transforma `-` em `+`; um parêntese não se desfaz.
3. **A resposta "fecha ou não fecha" é a segunda coisa que o olho encontra**,
   no balancete e no lançamento, antes de qualquer ação de gravar.
4. **Cor nunca é o único canal.** `D`/`C` é texto; erro tem texto; estado tem
   texto. Isso não é preferência estética: ~8% dos homens têm deficiência de
   visão de cor, e o projeto já tinha essa regra por acessibilidade.

**Os dois enxertos, e de onde vieram:**

- **Da variante B — atalhos de teclado à mostra na navegação.** Quem passa oito
  horas por dia aprende o atalho sem manual, se ele estiver escrito ao lado do
  item. Junto vem a promessa visível de que a exportação sai com a marca **do
  escritório**, não do fornecedor — que é um vício real do mercado nacional.
- **Da variante C — cabeçalho de coluna em dois níveis**, separando "movimento
  do período" de "lançamento próprio". Resolve, de graça, a simplificação que a
  variante A tinha feito ao descartar as colunas de movimento próprio: elas
  voltam **sem alargar a tabela**.

**Por que A e não B ou C, com o número que decidiu:** linhas de conta visíveis
sem rolar, em 1280×800, medidas pelo mesmo instrumento — **A: 15, B: 10, C: 9**,
contra ~8 do estado atual. O produto é usado seis a oito horas por dia; densidade
legível é a função-objetivo, e A ganhou onde mais dói sem perder legibilidade.

**Limites declarados desta decisão:**

- A variante A tinha **um** par de contraste reprovado (um travessão a 3,54:1) e
  **4 de 8** números da conferência fora da tabulação. Os dois são dívida da
  escolha e **entram corrigidos** na implementação — não se herda defeito
  medido só porque a variante venceu.
- O juiz que produziu esses números **errou quatro vezes antes de acertar**, e
  os quatro erros estão registrados em
  [`MEDICOES.md`](../assets/design/gauntlet/MEDICOES.md). A decisão se apoia na
  medição **posterior** aos consertos.
- Nenhum leitor de tela real foi usado por ninguém, e só o Chromium foi testado.
  Isso não é "acessível, ponto": é "mede-se o que se mediu".

**Consequência operacional:** a implementação traduz esta direção para
`templates/` e `static/css/` sem biblioteca externa (DE-011) e sem etapa de
build. Nenhuma cor ou medida solta fora das variáveis CSS. O que a DL-009 e a
DL-017 conquistaram — contraste, foco, estados, `D`/`C` explícito — não regride.

## DE-054 — Auditoria continua obrigatória; ela deixa de ser refém do andaime

**Decidido por Fred em 2026-09-19**, respondendo à pergunta que ele mesmo fez —
*"você acha a auditoria necessária nesse projeto?"* — depois de eu apresentar os
números e a crítica ao meu próprio processo. Escolha literal dele: **"A"** —
mesclar o produto agora e auditar em paralelo, sobre a `main`.

### O que motivou

A auditoria **se pagou**, e o registro precisa dizer com o quê:

- O veredito **"Fecha" em verde por cima da mensagem que recusou o lançamento**
  (BL-318). O contador digita `1999` no lugar de `2019`, o sistema recusa — e
  afirma que fecha. Nenhum teste pegava; cinco rodadas de auditoria pegaram.
- O relatório impresso saindo com a **marca do fornecedor em toda folha** nas
  opções padrão do navegador (A2 da rodada 5). O implementador mediu um PDF
  limpo; o auditor mediu **o papel que o contador recebe**.
- A conciliação conferida de forma **independente**, com 73 contas, em três
  fontes: HTML renderizado, rodapé e banco. `241.709,66` nos três.

### O defeito do processo, que é meu

**A guarda também é software, logo também pode ser auditada — e isso não tem
ponto final.** Cada rodada achava um buraco na guarda da rodada anterior, e
sempre acharia, porque guarda perfeita não existe. Montei um ciclo **sem regra
de parada**.

O custo medido no dia da decisão: **7 relatórios**, **80 itens de backlog**, e
**35 commits parados numa branch** — parênteses de saldo invertido, timbre do
escritório e filtro mais baixo, todos prontos e nenhum no ar. Nas duas últimas
rodadas o auditor escreveu que **o produto está certo**; o que ele reprovou
foram as guardas.

### A regra que passa a valer

**Separar mesclar de declarar pronto.** Mesclar leva valor ao usuário; declarar
a etapa fechada é outra coisa, e os itens abertos continuam abertos no backlog,
com dono.

**Buraco em guarda é BLOQUEADOR apenas quando ela defende um destes cinco:**

1. dinheiro, escala e arredondamento;
2. isolamento entre escritórios e entre empresas;
3. período encerrado;
4. trilha de auditoria;
5. **o documento que sai para o cliente**.

Fora dessa lista: item de backlog **com dono e momento**, que não trava entrega.

⚠️ **Isto não afrouxa a régua onde ela importa.** Os dois ALTOS da sexta
auditoria caem no item 5 e continuariam bloqueando — e foram corrigidos. O que
muda é que o produto não fica refém enquanto o andaime é polido.

### O que continua igual

- Auditoria **independente**, sobre a versão integrada, em toda etapa.
- Relatório preservado **integralmente**, sem edição, suavização ou omissão —
  inclusive os achados contra o `arquiteto-senior`.
- Sabotagem, não leitura: guarda que nunca falhou em teste não é guarda
  confiável.
- **Auditoria de software não substitui a validação profissional das regras
  contábeis e legais.**

## DE-055 — Verificação de correção inclui construção que o relatório NÃO nomeou

**Decidido pelo `arquiteto-senior` em 2026-09-19**, acatando recomendação do
`auditor-qa` no §6 da [rodada 7](../auditorias/2026-09-19-dl-026-rodada-7.md).
É correção de um defeito do **meu** método, não do trabalho da equipe.

### O que ele mediu

> *"Nas rodadas 5, 6 e 7, as sabotagens que o arquiteto refez para declarar uma
> correção verificada são **as sabotagens que eu escrevi no relatório
> anterior**. Correção feita para matar uma sabotagem específica mata essa
> sabotagem. Os achados G1 e G2 deste relatório são exatamente isso: passaram
> em todas as provas que a rodada 6 encomendou e morreram na primeira
> construção que ninguém tinha escrito."*

Ele está certo, e o dano é mensurável: o **G1** é um **bloqueador** que atravessou
uma rodada inteira de correção e chegou à `main`. A correção do BL-343 passou
nas sete construções que o relatório da rodada 6 nomeou — e morreu na primeira
que não estava lá, que por acaso é a forma **recomendada** de se escrever CSS
hoje.

O vício é sutil porque parece rigor: refazer a sabotagem do auditor **é**
necessário. Só não é **suficiente**, e eu vinha tratando como se fosse.

### A regra

**Toda verificação de correção inclui pelo menos uma construção que o relatório
de auditoria NÃO nomeou.** E, para que ela não nasça viciada:

1. **Quem escolhe a construção nova não pode ser quem escreveu a correção.** Na
   prática: eu a escolho ao integrar, ou um agente que não participou da
   correção a escolhe.
2. A construção nova é escolhida **pela classe do defeito**, não por criatividade
   — se o achado é "a guarda enumera em vez de derivar", a construção nova é o
   **item seguinte da enumeração**, procurado de propósito.
3. Se a construção nova **não** matar a guarda, isso é **achado**, e entra no
   backlog antes de a correção ser declarada fechada.

### O que isso não é

**Não é desconfiança do implementador.** Os relatórios desta etapa mostram o
contrário: eles acharam sozinhos exclusões que eu não citei, discordaram de
critério de aceite meu **com evidência**, e relataram efeito colateral sem
ninguém perguntar. O vício é do **método de verificação**, e o método é meu.

### Custo declarado

Cada verificação fica mais cara, e algumas construções novas não vão achar
nada. É o preço de não confundir *"passou nas provas encomendadas"* com
*"a propriedade está garantida"* — que é a confusão que esta etapa vem pagando
desde a rodada 5.

## DE-056 — A construção nova mira um eixo que o relatório NÃO discutiu

**Data:** 2026-09-19. **Origem:** §6 do relatório da oitava auditoria
([2026-09-19-dl-026-rodada-8.md](../auditorias/2026-09-19-dl-026-rodada-8.md)),
recomendação do `auditor-qa` **contra a aplicação que eu dei à DE-055**.
**Emenda ao item 2 da DE-055**, registrada logo acima neste mesmo arquivo.

### O que aconteceu

A DE-055 funcionou na primeira aplicação: das dezessete construções que o
`arquiteto-senior` guardou, dezesseis confirmaram e **uma furou**, e o BL-360
foi registrado como ALTA **antes** da auditoria em vez de por ela. Foi a
primeira vez, em sete auditorias, que o defeito seguinte apareceu antes do
auditor.

Mas as dezessete cobriam **um eixo só**: *o que o motor consegue LER*. O
auditor foi olhar o eixo **ao lado** — o conjunto de **propriedades** que o
motor considera — e achou um bloqueador em `_PROPRIEDADES_DE_INTERESSE =
("display",)`, uma lista de **um item**, a quinze linhas de um motor que tinha
sido reescrito **três vezes** sem ninguém encostar nela.

O motivo de ela ter sobrevivido é o que torna esta emenda necessária, e não é
descuido: ela está **declarada** na docstring, com uma justificativa **boa** —
e a justificativa é boa **para a guarda da marca**. Quando a guarda do timbre
reusou o mesmo motor "por composição em vez de repetição" (decisão de
engenharia correta), a declaração viajou junto e ninguém perguntou se ela
continuava valendo do **outro lado** da propriedade.

### A decisão

Ao item 2 da DE-055 — *"a construção nova é escolhida pela classe do defeito"* —
acrescenta-se:

1. **Pelo menos uma das construções novas mira um eixo que o relatório de
   auditoria NÃO discutiu.** A classe nunca é *"a guarda enumera construções
   CSS"*; é **"a guarda enumera"**. Procurar o item seguinte da enumeração que
   o relatório apontou é necessário e **não é suficiente**: exaurir um eixo não
   é convergir, é exaurir um eixo.
2. **A pergunta operacional para achar esse eixo é:** *"que lista existe neste
   arquivo que a correção desta rodada não tocou?"*. Em
   `test_bl329_marca_fora_do_papel.py` ela devolve `_PROPRIEDADES_DE_INTERESSE`,
   `_ELEMENTOS_VAZIOS`, `_BALANCETE_HTML` e a exceção nomeada `@media screen`.
   **Três das quatro viraram achado** na oitava auditoria.
3. **Limite declarado não é limite fechado.** Um limite herdado por composição
   é um limite cuja justificativa ficou para trás: quando uma guarda reusa o
   motor de outra, a estreiteza precisa ser **reavaliada contra a propriedade
   nova**, não herdada com ele. Estreito num sentido pode ser **frouxo** no
   sentido oposto.

### Consequência aceita

Mais uma pergunta por rodada, e ela é desconfortável de propósito: obriga a
olhar para onde ninguém apontou. O custo de não fazê-la está medido — onze
rodadas percorrendo um eixo, com o achado encolhendo a cada passo, e um
bloqueador intacto no eixo vizinho o tempo todo.

### O que esta decisão NÃO resolve

O auditor registra, e eu concordo, que **tamanho de achado mede onde se
procurou, não quanto sobrou**. A emenda melhora a busca; ela não substitui a
decisão maior sobre o **instrumento**, que está em aberto com o Fred e
registrada no
[estado.md](../agents/estado.md).

## DE-057 — O navegador entra na integração contínua, delimitado por caminho

**Data:** 2026-09-19. **Decisão do Fred**, respondendo à pergunta de instrumento
colocada pela oitava auditoria da DL-026
([relatório](../auditorias/2026-09-19-dl-026-rodada-8.md), §7). Plano de
execução: [DL-028](../planos/DL-028-o-juiz-aponta-para-o-produto.md).

### A pergunta

A DL-026 teve oito auditorias e onze rodadas. As onze percorreram **um eixo** —
*o que o motor de cascata simulado consegue ler* — e o achado encolhia a cada
passo, o que eu li como convergência. Na oitava auditoria o auditor olhou o eixo
**ao lado** e o achado voltou a bloqueador: **dez construções banais de CSS
apagam a identificação do escritório da folha A4 que o contador entrega ao
cliente, com a suíte inteira verde**, medidas em Chromium e em PDF do produto.

O auditor recomendou, contra o caminho que eu vinha seguindo, **trocar o
instrumento** em vez de polir mais uma rodada. Três fatos sustentam isso:
`test_bl329_marca_fora_do_papel.py` tem mais de 1800 linhas para uma pergunta
que o navegador responde com uma chamada; a linguagem que ele simula cresce todo
ano; e **todo bloqueador desta etapa foi encontrado abrindo um Chromium e
olhando o PDF**.

### As três opções levadas ao Fred, com o custo de cada uma

| | Caminho | Custo |
| --- | --- | --- |
| **A** | Navegador de verdade na integração contínua | Cria dependência que o projeto decidiu, de propósito, não ter |
| B | Conferência de bancada obrigatória, com evidência registrada | É **disciplina** — o que o projeto decidiu não usar como garantia quando criou as guardas |
| C | Continuar polindo o motor simulado | Nunca fica completo |

⚠️ Uma quarta opção foi descartada de saída, e não por mim: **declarar a etapa
fechada afirmando que o critério 9 está garantido**, quando a medição desmente.

### A decisão

**O Fred escolheu A.** A delimitação por caminho é minha, e é ela que torna o
custo aceitável: o job roda quando muda `static/css/**`, `templates/**` ou as
guardas de impressão — nunca em alteração só de documentação.

O que decide entre A e B é o princípio que já governa este projeto: **mecanismo
em vez de disciplina**. A instrução permanente do Fred de 2026-09-13 — *"nunca
esqueça de atualizar"* — virou teste, não lembrete, e a causa do problema foi
nomeada como **duplicação**, não distração. Escolher B seria voltar a apostar em
alguém lembrar, na propriedade em que a falha chega ao cliente em papel.

### O que esta decisão NÃO significa

1. **O motor simulado não é apagado.** Ele é rebaixado de *única linha* para
   *primeira linha barata*, e isso fica **escrito na docstring dele** — quem
   ler precisa saber que a palavra final é de outro. As recusas que as rodadas
   10 e 11 instalaram continuam valendo.
2. **Não se instala navegador por caminho fixo.** O
   `/opt/pw-browsers/chromium-1194` desta máquina é acidente do ambiente, não
   configuração do projeto. O job instala pelo gerenciador do Playwright.
3. **Falha de infraestrutura precisa ser distinguível de falha de conteúdo.**
   Job instável que reprova por motivo alheio ao código é falso alarme, e falso
   alarme é, pelo argumento do BL-321, mais corrosivo que falso negativo.
4. **Isso não fecha a DL-026.** BL-362 e BL-363 são da rodada 12, e correm em
   paralelo, em arquivos disjuntos: enquanto o instrumento novo não existe, a
   guarda atual não pode continuar simplesmente errada.

## DE-058 — Justificativa escrita não é justificativa medida

**Data:** 2026-09-20. Acréscimo à **DE-056** (acima, neste mesmo arquivo),
proposto pelo `auditor-qa` na décima auditoria
([relatório](../auditorias/2026-09-20-dl-026-dl-028-rodada-10.md), §2) e
**decidido por mim**: é regra de processo, barata e reversível.

### O que a décima auditoria mediu

A DE-056 mandou **declarar** o limite de cada lista. Os dois implementadores
fizeram isso: escreveram as justificativas nas docstrings dos arquivos novos. É
melhor do que lista inexaminada, e não bastou, por **dois** motivos medidos na
mesma rodada:

1. **Eles responderam sobre as listas que o relatório anterior nomeou** — e a
   única lista que ninguém tinha discutido foi a que virou **bloqueador**
   (`MARCA_DO_FORNECEDOR`, BL-404).
2. **Uma das justificativas escritas é falsa.** A docstring de
   `LIMIAR_LUMINANCIA_TINTA` afirma que *"NENHUMA medição feita para calibrar
   este oráculo produziu um pixel de linha do timbre entre 1 e 254"*. Uma linha
   de CSS banal — `opacity: 0.4` — desmente a frase, e o instrumento passa a
   reprovar produto correto dizendo *"0 pixels escuros"* (BL-407).

### A regra

**Toda frase de docstring, comentário ou documento que afirme um RESULTADO DE
MEDIÇÃO precisa ter, ao lado, o teste que a reprova se ela deixar de valer.**

Sem esse teste, a frase é exatamente o defeito de 2026-09-13 que originou a
regra da fonte única — **garantia inexistente descrita como imposta** —, só que
em escala pequena e dentro do código, onde ninguém vai reler.

Três formas aceitáveis de cumprir, em ordem de preferência:

1. **O teste existe e cita a frase.** A frase e o teste apontam um para o outro,
   e quem mudar um vê o outro.
2. **A frase vira a asserção.** Em vez de escrever o resultado, escreva a
   verificação: o comentário some e o teste fica.
3. **A frase é marcada como não verificada**, com a palavra *"não medido"* ou
   *"hipótese"* nela, e com o que falta para medir. Isso é o mínimo, e só vale
   quando medir custa mais do que a etapa comporta.

O que **não** é aceitável é a forma atual: afirmação no tom de medição, sem
medição ao lado e sem marca de que não foi medida.

### O que isto NÃO é

**Não é exigência de teste para toda docstring.** A regra alcança só frase que
afirma resultado de medição — *"nenhum caso produz X"*, *"o custo é N
segundos"*, *"isto dispara zero vezes hoje"*. Prosa explicativa, justificativa de
desenho e contexto histórico continuam livres.

### Dois itens de método que a mesma rodada gerou, e que são meus

- **[BL-412] "Contar na fonte" é disciplina.** Eu contei e publiquei *"11 de 11
  pulados, 24 s"*, e estava certo e **incompleto**: faltou **contar a fonte
  inteira** — na mesma revisão havia uma segunda execução de CI, de
  `pull_request`, com 0 pulados e 63 s. A versão-mecanismo é barata: o número é
  **buscado** pelo script que monta o relatório, que itera **todas** as
  execuções e **recusa publicar** se a busca falhar.
- **[BL-413] Conferência por contagem prova cardinalidade, não conteúdo.** A
  correção do BL-388 tem a mesma forma do `assert == 3` que eu mesmo corrigi:
  seis linhas iguais passam, identificador trocado passa. A propriedade certa é
  *"cada item que eu afirmo ter registrado é localizável no arquivo gravado pelo
  seu próprio identificador"* — comparar **conjuntos**, não números.

## DE-059 — Comprar a frase executável do critério 9, e dizer a verdade enquanto ela não chega

**Data:** 2026-09-20. **Decisão delegada pelo Fred**, com uma frase — *"Você
decide"* — depois de eu levar a ele os dois lados da **PE-56** com o custo de
cada um. Plano de execução:
[DL-029](../planos/DL-029-a-frase-executavel-do-criterio-9.md).

### A pergunta

A décima auditoria
([relatório](../auditorias/2026-09-20-dl-026-dl-028-rodada-10.md)) reprovou
DL-026 e DL-028 com um bloqueador e quatro altas, e o auditor pôs duas saídas na
mesa em vez de pedir a rodada 11:

| | Caminho | Custo |
| --- | --- | --- |
| **1** | Escrever **uma** frase executável para o critério 9 inteiro e fazer o instrumento ser julgado por ela | ≈ uma rodada de trabalho, num arquivo e nos testes dele |
| 2 | Não declarar as etapas fechadas e declarar **produto bom, garantia parcial**, com BL-404 nomeado | Zero |

E foi explícito sobre o que **não** é defensável: *"fechar dizendo que o
critério 9 está garantido"*.

### A decisão

**As duas, e elas não competem — respondem a perguntas diferentes.**

1. **Compro a frase** (caminho 1). É a DL-029.
2. **E declaro hoje a verdade de hoje** (caminho 2): DL-026 e DL-028 **não estão
   fechadas**; o que existe é **produto bom, garantia parcial**, com **BL-404**
   nomeado como o buraco aberto. Isso vale enquanto a DL-029 não entrar, e vale
   **independentemente** dela.

Isso é a **DE-054** (acima, neste mesmo arquivo) aplicada: *"isto melhora o produto?"* e *"isto está
garantido?"* são perguntas separadas. O caminho 2 é uma afirmação sobre o
**estado**; o caminho 1 é uma decisão sobre o **próximo trabalho**. Tratá-las
como alternativa era o que amarrava uma na outra.

### Por que o caminho 1, e a evidência é do mesmo dia

O argumento do auditor é de **régua**: a régua de cada rodada tem sido o
**relatório anterior**, não o **critério**; por isso o achado sobe de nível a
cada vez e não acaba.

Em **2026-09-20**, numa tarde, a mesma lição apareceu **três vezes seguidas** —
**BL-415**, **BL-416**, **BL-418** — e nas três **dentro de uma guarda escrita
para fechar a ocorrência anterior**. Na terceira, a causa raiz apareceu e ela
**já estava decidida**: era a **DE-057** outra vez, um nível abaixo — estávamos
reimplementando a configuração de uma ferramenta em vez de perguntar a ela,
exatamente como o motor de cascata fazia com o navegador.

Três ocorrências em uma tarde, com a causa raiz sendo uma decisão que o projeto
já tinha tomado, é a medição que faltava. **Não é teoria sobre o futuro: é o
registro do dia.**

### O que esta decisão NÃO significa

1. **Não fecha DL-026 nem DL-028.** Nenhuma das duas se declara fechada sem
   auditoria da versão integrada (DE-054). A DL-029 é o trabalho; o fechamento é
   outra conversa.
2. **Não reverte o caminho A.** O instrumento de navegador **fica**. O auditor
   reafirmou pela segunda rodada seguida: 4 s de medição responderam o que 1.800
   linhas de cascata simulada não respondem, e o controle limpo mede 348 px
   contra piso de 40.
3. **Não promete que a frase é a última.** Prometer isso seria o defeito que a
   DE-058 acabou de proibir. O que se afirma é o que se mede: os quatro achados
   abertos são consequência de a frase não existir, e a frase os endereça
   **juntos**. Se aparecer um quinto eixo, ele aparece contra **o critério**, que
   é uma régua melhor que o relatório anterior.
4. **Não fecha o limite do desenho.** Marca do fornecedor como logotipo vetorial
   não tem objeto de texto, e nenhuma cláusula da frase a alcança. Fica
   **declarada no código**, no formato da DE-056.
5. **Não substitui a ação do Fred no GitHub.** Enquanto a `main` não tiver
   proteção (BL-373), tudo isto — inclusive o job novo — é **conselho**.

## DE-060 — A guarda APROXIMA: substituto não declarado é a nova forma do mesmo defeito

**Data:** 2026-09-20. Nomeada pelo `auditor-qa` na décima primeira auditoria
([relatório](../auditorias/2026-09-20-dl-029-rodada-11.md), resposta 2), adotada
por mim. É o eixo seguinte da **DE-056**.

### O que ele viu, e vale mais que os quatro achados somados

Quatro achados de gravidade alta — **BL-427** a **BL-430** — têm **um** padrão
por trás:

> **O instrumento mede um SUBSTITUTO mais fácil de obter que a propriedade, e o
> substituto não está declarado como substituto.**

| A propriedade | O substituto medido | Diverge quando |
| --- | --- | --- |
| Que tamanho a linha tem **no papel** | `getComputedStyle().fontSize` | `transform`, `zoom` (BL-428) |
| Qual é a **razão de contraste WCAG** | luminância de raster em **cinza** | a tinta não é cinza (BL-429) |
| A linha **está no papel** | substring do `pdftotext -layout` | `letter-spacing` (BL-430) |
| **Quantas** linhas o papel carrega | contagem de `<p>` do DOM | é a **mesma** consulta que alimenta a recusa de infraestrutura (BL-427) |

### Por que isto é diferente da DE-056, e melhor

A DE-056 diz *"a guarda ENUMERA"* — e a pergunta que ela gera (*"que lista
existe aqui?"*) é **infinita**: sempre há outra lista.

Esta diz *"a guarda APROXIMA"*, e a pergunta que ela gera é **finita e
auditável**: o instrumento faz **cinco** medições; para cada uma, *"isto é a
propriedade ou um substituto dela? se for substituto, de que ele diverge, e essa
divergência foi medida?"*.

⚠️ **E três das quatro correções usam dado que o instrumento JÁ CALCULA E
DESCARTA** — o `bbox` real de cada linha, em pontos de PDF, do papel de verdade.
**Não é escopo novo: é parar de jogar fora a medida melhor.**

### A regra

**Toda medição de guarda declara, no código, se mede a propriedade ou um
substituto dela.** Quando for substituto: **de que ele diverge**, e **a medição
dessa divergência** ao lado (DE-058). Substituto declarado é aceitável;
substituto silencioso é o defeito.

### O que isto NÃO significa

1. **Não condena substituto.** Medir o papel inteiro em cor custa mais que medir
   em cinza; a escolha pode ser certa. O que não pode é a etiqueta prometer o
   que o número não entrega — foi o **BL-429**.
2. **Não promete que é o último eixo.** O auditor foi explícito: *"a frase pagou
   … e a frase não encerrou o ciclo, e eu não vou fingir que encerrou"*. O que
   ele afirma é mais modesto e mais útil: é a **primeira vez em doze rodadas**
   que o trabalho restante se escreve como **lista fechada** em vez de direção.
   **E ele declarou o critério de parada:** se depois desta rodada aparecer um
   **sexto** eixo, a conversa deixa de ser de engenharia e passa a ser *"quanta
   garantia o produto precisa"* — pergunta do Fred.

## DE-061 — A frase do critério 9, corrigida: ela prometia o impossível

**Data:** 2026-09-20. Correção da frase adotada na **DE-059**, proposta pelo
`auditor-qa` — que a escreveu — depois de **medir** a própria frase
([relatório](../auditorias/2026-09-20-dl-029-rodada-11.md), resposta 1).

### O que a medição mostrou

A frase dizia *"a folha A4 **exportada** … não carrega **nenhum** identificador
do fornecedor do software"*. Lida como um contador lê — a folha que sai apertando
Ctrl+P —, essa cláusula é **impossível de cumprir**.

Medido: exportando o Balancete com as **opções padrão** do diálogo de impressão
(cabeçalho e rodapé marcados, que é o padrão do Chrome e do Edge), a faixa de
baixo carrega a **URL**. Em produção, servida de um domínio da empresa, essa URL
**é** o identificador do fornecedor, impresso em **toda folha**. E
`static/css/base.css` já declara, no comentário do **BL-332**, que *"não existe
propriedade CSS, atributo HTML nem cabeçalho HTTP que as suprima ou reescreva"*.

**O produto está certo; a frase é que prometia o que ninguém pode entregar.**

### A frase, corrigida

> **A folha A4 exportada carrega, com tinta que contrasta com o papel,
> exatamente as linhas de identificação do escritório emitente que o servidor
> declarou, cada uma no seu próprio lugar; e — em tudo que o arquivo exportado
> carrega e que o template ou a folha de estilo podem suprimir, excluída a faixa
> que o navegador acrescenta por fora e que nenhuma folha de estilo alcança
> (BL-332) — não carrega nenhum identificador do fornecedor do software, em
> qualquer caixa ou espaçamento.**

⚠️ **CORRIGIDA de novo em 2026-09-20, e o defeito era meu.** A primeira versão
desta fronteira dizia *"isto é, tinta na folha e metadados do arquivo"* — uma
**lista de dois canais**. A décima segunda auditoria mediu o custo (**M2**): o
PDF entregue carrega **anotações de link**, e um `<a href>` com o domínio do
fornecedor passava com `exit 0`. **Era a DE-056 acontecendo dentro da correção
que eu propus para a DE-059.** A redação acima troca a lista por **critério**, e
o instrumento já foi corrigido (`11fcfa7`).

⚠️ **Isto NÃO é afrouxar.** É parar de chamar de garantia uma coisa que a
medição diz ser impossível — que é, na definição do próprio projeto, o defeito de
2026-09-13: **garantia inexistente descrita como imposta**.

### O que a frase acertou, e fica sem mudar uma palavra

*"Em qualquer caixa ou espaçamento"* se mostrou **mais larga** do que o autor
tinha em mente: alcançou o canal de **metadados do PDF** (`/Title`), que ninguém
tinha imaginado e que a equipe encontrou **ao executá-la**, e alcançou o
`content:` de pseudo-elemento sem precisar de item novo. *"Uma frase que produz
cobertura que o autor não antecipou é o sinal de que ela está no nível certo de
abstração."*

### Uma cláusula que a frase cobre em palavras e que o instrumento NÃO mede

*"Do escritório **emitente**"*. A base de medição tem **um** escritório, então o
instrumento nunca pode distinguir *"o escritório certo"* de *"algum escritório"*.
Isso é coberto pela camada barata
(`apps/tenancy/tests/test_bl282_timbre_escritorio.py:182`), e o auditor **não**
recomenda duplicar no navegador. **Registrado para ninguém supor que o
instrumento prova isolamento entre escritórios: ele não prova.**

## DE-062 — A DE-058 vale para a PROSA, não só para o código

**Data:** 2026-09-20. Proposta pelo `auditor-qa` na décima segunda auditoria
([relatório](../auditorias/2026-09-20-dl-029-dl-030-rodada-12.md), resposta 4),
**adotada por mim**, e o motivo é que o dado é contra mim.

### O que ele mediu, e a separação é limpa

Eu perguntei se quatro autocorreções num dia eram o processo funcionando ou
sinal de que eu publico rápido demais. Ele **separou as duas coisas com
medição**:

| Tipo de afirmação minha | Verificadas | Confirmadas |
| --- | --- | --- |
| **Número medido** (suíte, lint, custo do job, contagem de testes) | 7 | **7** |
| **Achado fechado** (BL-427 a BL-437, os sete gaps da DL-030) | 13 | **13** |
| **Razão / mecanismo / enquadramento** | 3 | **1** |

O veredito dele, textual: ***"Você mede bem e narra mal."***

**O que erra é sempre a mesma coisa:** a **explicação** publicada ao lado do
número, escrita no tom de quem mediu, quando não mediu. **Seis instâncias em um
dia** — BL-435 (grep no lugar da propriedade), BL-442 caso 1 e caso 2, a
aritmética do *"−84"*, a premissa nova do BL-419 (M10) e a generalização do
*"lado seguro"* (M4).

⚠️ **E a leitura que importa:** *"velocidade produziria erro **variado**. Seis
instâncias da mesma forma, em um dia, é **mecanismo faltando**"* — e fui eu quem
escreveu, no `CLAUDE.md`, que a causa do defeito de 2026-09-13 não foi distração,
foi **estrutura**.

### A regra

**Toda afirmação VERIFICÁVEL escrita em `docs/projeto/**` e em
`docs/agents/estado.md` carrega, ao lado, OU o comando que a produziu, OU as
palavras "não medido".**

A **DE-058** já dizia isso para **docstring**. Não valia para prosa — e
`decisoes.md`, `backlog.md` e `estado.md` são hoje os documentos do projeto com
**mais** afirmações verificáveis **sem verificação ao lado**. As seis instâncias
estão **todas** lá; **nenhuma** no código.

**Alcança:** *"o mecanismo X cobre Y"*, *"isto acontece porque Z"*, *"a falha é
barulhenta"*, *"a direção do desvio é segura"*, *"o caminho é inalcançável" —*
qualquer frase que alguém possa **conferir e derrubar**.

**Não alcança:** recomendação, julgamento de prioridade, e o que já estiver
marcado como **hipótese** ou **pendência** — essas categorias já existem e já
dizem que não são fato.

### O que esta decisão NÃO significa

1. **Não é ordem para desacelerar, e o auditor foi explícito:** *"não recomendo
   desacelerar. As quatro correções de ontem custaram horas; os dois defeitos que
   sobreviveram — M1 e M2 — custaram **seis rodadas** de auditoria cada um, e
   nenhum apareceu por falta de tempo: apareceram porque ninguém tinha escrito
   aquela construção. **Velocidade não os teria evitado; a DE-055, sim, e ela já
   está ligada.**"*
2. **Não há mecanismo automático ainda, e isto fica declarado.** O
   `scripts/validate-docs.ps1` anda por **todos** os `.md`, então o gancho
   existe — mas **não sei se dá para verificar isto mecanicamente**, e **não
   afirmo que dá**. É **hipótese**, não fato, e é a própria DE-062 aplicada a si
   mesma na primeira linha que ela escreve.
3. **Não apaga afirmação antiga.** Corrigir o que já se provou falso é
   obrigação, e o registro do erro fica — foi assim com BL-435 e BL-442.

## DE-063 — Teste que guarda ANDAIME se corta; teste que guarda REGRA CONTÁBIL não

**Data:** 2026-09-20. **Ordem do Fred**, com a medição dele: *"a main tem ~11.800
linhas de produção e ~45.000 de teste … estamos girando no mesmo lugar …
precisamos contar mais e reduzir drasticamente essa quantidade de teste."*

### A medição, conferida por mim antes de agir

```
git ls-files 'apps/**/*.py' 'config/**/*.py' | grep -v '/tests\?/' | grep -v test_ | grep -v /migrations/ | xargs wc -l
  → 12.109 linhas de produção
git ls-files 'apps/**/*.py' 'scripts/**/*.py' | grep -E '/tests?/|test_' | xargs wc -l
  → 47.245 linhas de teste        proporção 3,9 : 1
```

**Os números do Fred estão certos.** Mas a distribuição diz o que a proporção
não diz:

| Fatia | Linhas | % | O que guarda |
| --- | --- | --- | --- |
| **Regra contábil e dados** | 18.372 | **36,9%** | Lançamento, conta, empresa, período, trilha, isolamento |
| **Varredura de meta-regras** | 14.878 | **29,9%** | Nossos contratos, nossa interface, nossos arquivos de agente, nosso estado |
| **Guarda do documento impresso** | 8.857 | **17,8%** | Timbre, marca, motor de CSS simulado, instrumento |
| **Interface** | 7.660 | 15,4% | Telas, acessibilidade |

⚠️ **Quase metade (47,7%) guarda o ANDAIME — a nossa própria disciplina —, não
a contabilidade.** É isso que a proporção de 3,9:1 esconde, e é o diagnóstico
que transforma a intuição do Fred em decisão.

### A regra

1. **Teste de regra do domínio contábil é intocável.** Débito igual a crédito,
   precisão monetária, isolamento entre empresas, imutabilidade da trilha,
   período encerrado, idempotência. **Não se corta, não se "simplifica".** É o
   que faz o produto ser confiável, e é irreversível errar aqui.
2. **Teste que guarda a nossa própria disciplina só existe se for DERIVADO** —
   uma varredura curta que pergunta uma propriedade. **Nunca por enumeração**, e
   nunca com motor próprio.
3. **Quando existe medição direta, a simulação é APAGADA, não guardada "por
   segurança".** Manter as duas é pagar duas vezes pela mesma pergunta — e foi
   exatamente o que fizemos com o motor de CSS.

### O primeiro corte, executado hoje

**5.290 linhas, 142 testes, quatro arquivos** — a família do **motor de CSS
simulado** (`test_bl329`, `test_bl331`, `test_bl332`, `test_bl338`).

**Por que estes primeiro, e não outros:** a **DE-057** já os rebaixou de *única
garantia* para *primeira linha barata* quando o Fred comprou o navegador real. O
navegador responde a **mesma pergunta em 4 segundos**, e essas 5.290 linhas
produziram, sozinhas, **doze rodadas de auditoria** — BL-343, BL-351, BL-352,
BL-353, BL-360, BL-361, BL-362, BL-363, BL-372… **O custo delas não foi o
tamanho: foi o número de rodadas que consumiram.**

**Medido depois do corte:** `1917 passed, 14 skipped`, suíte verde; proporção
**3,9 : 1 → 3,5 : 1**.

⚠️ **O que se perde, declarado:** erro de CSS deixa de ter sinal **local
instantâneo** e passa a aparecer no job de navegador na CI (~50 s), que roda nos
caminhos vigiados — e `static/**` e `templates/**` **são** vigiados. É perda
real e pequena; registro para não descobrirem depois.

### O que esta decisão NÃO é

1. **Não é "testar menos".** É **parar de testar o andaime**. A fatia contábil
   (36,9%) não perde uma linha.
2. **Não é desfazer a DE-057.** O navegador fica; o que sai é a **imitação** dele
   que continuamos mantendo ao lado.
3. **Não apaga história.** Os quatro arquivos continuam no histórico do Git, e
   os doze relatórios de auditoria que os julgaram continuam preservados.

## DE-064 — Trabalho EM VOO de outro agente não se commita, e a regra para de ser redecidida

**Decisão tomada pelo `arquiteto-senior` em 2026-09-20**, sob a delegação do
Fred (*"Você decide"*), depois de o gancho de fim de turno cobrar commit **dez
vezes na mesma sessão** sobre arquivos que pertenciam a um agente ainda
executando.

**A regra:** o `arquiteto-senior` **não** commita alteração que esteja sendo
escrita por outro agente naquele momento. Quem entrega e commita é **quem
escreveu**, com os números medidos no relatório.

**O que o gancho mede, e por que erra:** ele pergunta *"existe diferença na
árvore?"*. A pergunta certa é *"existe trabalho CONCLUÍDO sem dono?"*. Diferença
na árvore com dono ativo é **trabalho em andamento**, não pendência. É a
**[DE-060](#de-060--a-guarda-aproxima-substituto-não-declarado-é-a-nova-forma-do-mesmo-defeito)**
aplicada ao próprio ferramental: o instrumento mede um **substituto** mais fácil
de obter que a propriedade.

**Por que a regra vale o atrito, e o exemplo é real:** durante a correção do
**BL-456** — a corrida que grava lançamento em competência encerrada — o
gancho cobrou commit de `apps/contabilidade/services.py` **no meio** da
reescrita da trava. Commitar ali gravaria meia correção de concorrência, sem a
prova exigida (30 tentativas, zero falhas) ter sido rodada uma única vez.
**Código de concorrência pela metade parece pronto e não está.**

**O que NÃO muda:** o `arquiteto-senior` commita e empurra o que é **dele**
(documentação, planos, requisitos, relatórios de auditoria) a cada etapa, e
confere que local e remoto batem antes de encerrar o turno. A árvore nunca fica
com trabalho **concluído** sem commit.

**Registrado como decisão para parar de ser redecidido.** O atrito é do
instrumento (**BL-421**), não do processo; enquanto o gancho não distinguir
"em andamento" de "concluído", a resposta é esta, e é uma linha.

## DE-065 — A fatia 2 da DL-016 é a TELA, e ela vem antes de qualquer módulo novo

**Decisão tomada pelo `arquiteto-senior` em 2026-09-20**, sob a mesma
delegação.

**Assim que a fatia 1 fechar, a próxima etapa de código é a fatia 2: a tela de
fechar, reabrir e marcar como entregue.** Não é o código reduzido da conta
(RC-99/RC-100), não é módulo novo, não é a política de período de trabalho.

**O motivo é de produto, e é simples de verificar:** hoje o contador **não
consegue fechar o mês**. A trava existe no servidor e não há porta pela qual
acioná-la — só requisição direta à API, que não é o que o escritório usa.
**Funcionalidade que o usuário não alcança é funcionalidade que não existe para
ele.** Uma trava sem tela transforma-se, na prática, em um sistema que recusa
lançamentos sem que ninguém tenha como abrir o mês de volta.

**A ordem inversa foi deliberada e continua certa** — a trava antes do botão
(*"a trava tem de existir antes de haver botão para acioná-la"*). O que esta
decisão diz é que a dívida gerada por essa ordem **se paga na etapa seguinte**,
não depois de dois módulos.

⚠️ **E a fatia 2 nasce com uma vantagem que a 1 não teve:** o **BL-457** mostrou
que a tela de **lançamento** devolvia 500 em vez da mensagem da recusa. A fatia
2 herda a obrigação de apresentar, em cada tela que toca a competência, a recusa
**em texto que o contador entenda** — com o caminho de saída (reabrir, ou lançar
no mês aberto) escrito na própria mensagem.

## DE-066 — Achado de gravidade BAIXA não abre rodada; vira ressalva declarada

**Decisão tomada pelo `arquiteto-senior` em 2026-09-20**, sob a mesma
delegação, para dar consequência prática à **regra de parada da §3.1 do
`AGENTS.md`**.

**A régua da reconferência**, a partir de agora:

| Gravidade | O que acontece na reconferência |
| --- | --- |
| **Bloqueador** ou **alta** | **Tem de estar fechado e medido.** Se não estiver, a etapa **não** fecha, e o caso sobe ao Fred com o diagnóstico — **não** com uma terceira rodada |
| **Média** | Fecha na mesma correção **quando o dono e os arquivos já estão abertos**; senão vira item de backlog com dono e momento |
| **Baixa** | **Ressalva declarada.** Entra no relatório ao Fred, com o efeito prático escrito, e **não** segura a etapa |

**Por que isto é decisão e não preguiça:** a auditoria da fatia 1 devolveu
**oito** achados. Dois são o produto (bloqueador e alta); quatro são baixas —
um comentário desatualizado, falta de contexto na trilha, um estado do enum que
ninguém usa, e este arquivo de estado. **Tratar os oito com o mesmo rigor é o
que transformou doze rodadas de auditoria em doze rodadas de polimento**, que é
exatamente o que o Fred mandou parar.

⚠️ **O que a régua NÃO afrouxa:** gravidade quem atribui é o **auditor**, não o
implementador nem eu. Reclassificar achado para baixo a fim de fechar etapa é
proibido, e seria a forma mais barata de fraudar este processo inteiro.

## DE-067 — A leitura de saldos NÃO recebe snapshot nesta fatia; o limite é DECLARADO e pago na fatia 2

**Decisão tomada pelo `arquiteto-senior` em 2026-09-21**, respondendo ao achado
**A6** da [auditoria da DL-032](../auditorias/2026-09-21-dl-032-rodada-1.md), que
o auditor encaminhou explicitamente a mim por ser *"decisão de arquitetura, não
de implementação"*.

**O achado, em uma frase:** `apurar_saldos` lê em **três consultas**, fora de
transação, sob `READ COMMITTED` — então uma escrita concorrente entre a primeira
e a segunda pode produzir uma **diferença fantasma** na equação: diferente de
zero num instante, zero no seguinte, **sem desbalanço real na base**.

**A decisão: declarar agora, pagar o snapshot na fatia 2.** Três razões, em
ordem de peso:

1. **Hoje NINGUÉM consegue provocar a corrida pelo produto.** `apurar_saldos`
   **não tem view** — é decisão do próprio plano. A exposição à concorrência
   **começa quando a superfície existir**, e é exatamente aí que o custo deve ser
   pago, junto com a autorização, que o auditor também apontou como pendência
   que **migra inteira** para a fatia 2.
2. **`atomic()` sozinho NÃO resolve**, e isso é a parte que engana: sob
   `READ COMMITTED` cada instrução recebe um snapshot novo. A correção real
   exige `REPEATABLE READ`, que muda o comportamento de **toda** a transação
   — e `apurar_balancete`, a função reusada, é chamada de views que podem já
   estar em transação. **Mexer nisso sem a superfície pronta é alterar o
   Balancete do produto para resolver um problema de uma fatia que ainda não
   tem porta.**
3. **O dano é de confiança, não de dado.** Nada é gravado errado, nada se perde.
   Mas para o contador uma diferença intermitente é **indistinguível** de erro
   real — e o plano manda declarar a diferença, então ele vai declará-la.

⚠️ **O que esta decisão NÃO autoriza, e é o ponto do auditor:** *"o que não me
parece aceitável é o silêncio atual"*. **Concordo.** O limite entra no
**docstring** de `apurar_saldos` — não só aqui —, dizendo que a leitura não é
isolada e que a diferença só é conclusiva em base parada.

**A fatia 2 herda isto como requisito, não como sugestão:** a leitura que gerar
documento imprimível roda **sob snapshot**, e o teste de corrida que prova isso
nasce junto com a view. ⚠️ **Registro para não ser esquecido**, que é o destino
comum das dívidas declaradas sem dono e sem momento.

## DE-068 — Enuncie a invariante E O ESCOPO DELA: invariante mal dimensionada é pior que lista

**Decisão tomada pelo `arquiteto-senior` em 2026-09-21**, a partir de uma
**retratação do próprio `auditor-qa`** na
[reconferência da DL-033](../auditorias/2026-09-21-dl-033-rodada-2.md).

**A história completa, porque a lição só se entende com ela:**

1. Na **rodada 1**, o auditor recomendou trocar um catálogo de listas por uma
   **identidade aritmética**, e escreveu que ela *"fecha de uma vez este achado,
   o A2 e o A6 — **e qualquer outro caso que nem eu nem o implementador
   pensamos**"*.
2. **Eu promovi essa frase a critério de aceite**, confiando nela.
3. O implementador **repetiu a promessa no docstring** do código.
4. Na **rodada 2**, o próprio auditor **construiu o contra-exemplo e o mediu**:
   dois defeitos calibrados para se anularem produzem **resíduo zero, cinco
   listas vazias, equação fechando — e dois grupos do Balanço errados em
   R$ 500,00 cada**.

**A frase dele, que eu adoto como a decisão:**

> *"Invariante mal dimensionada é mais perigosa que lista, porque **parece
> completa**. Lista declara o que sabe e admite o que não sabe; identidade
> aritmética convida a acreditar que fechou tudo."*

**A regra, portanto:** ⚠️ **enunciar a invariante NÃO basta — é preciso enunciar
o ESCOPO dela**: sobre qual agregação ela vale, e sobre qual **não** vale.

**O caso concreto, como exemplo permanente:** `Σ(grupos) + resíduo ==
totais_por_tipo` é **verdadeira sempre** — o auditor não achou nenhum cenário em
que falhe, e não é tautologia, porque os dois lados somam conjuntos de nós
**diferentes**. Mas ela é um cruzamento **líquido** e **por TIPO**. Ela **não**
limita o erro de nenhum **grupo** individual — e é o grupo que o Balanço
imprime.

⚠️ **Isto corrige, sem revogar, a [DE-058](#de-058) e a lição da rodada 1 da
DL-033** (*"enuncie a invariante, não o mecanismo suspeito"*). A regra continua
certa; o que faltava era a segunda metade. **Enunciado por mecanismo erra por
estreiteza; enunciado por invariante sem escopo erra por largueza — e a
largueza é pior, porque não parece erro.**

**A quem isto obriga, e é a mim primeiro:** quem escreve critério de aceite
declara a agregação em que a propriedade vale. Frase de auditor, por melhor que
seja, **não entra em plano sem ser dimensionada** — foi exatamente isso que eu
não fiz.

⚠️ **E o que esta decisão NÃO faz:** não culpa o auditor. **Ele mesmo desmontou
a própria recomendação, sem ser perguntado, na rodada seguinte.** É o
comportamento que este projeto quer, e é por isso que o erro virou decisão em
vez de virar nota de rodapé.

## DE-069 — Recomendação que o auditor declarou NÃO ter testado entra como hipótese a medir, nunca como número a assertar

**Data:** 2026-09-21

**Decisão:** quando um relatório de auditoria traz uma recomendação e o próprio
auditor **declara** que não a implementou nem a testou, ela entra no plano
**como hipótese a medir**, com a medição escrita como tarefa. ⚠️ **Nunca como
número literal em critério de aceite**, e nunca como afirmação de que o
resultado será aquele.

**Motivo — e é a SEGUNDA ocorrência seguida da mesma falha minha.** Na rodada 2
da DL-033 o auditor sugeriu a correção (b) — normalizar o sinal pela natureza
natural do tipo — e escreveu, com todas as letras, que **conferira a aritmética
à mão, sem implementar nem testar**. Escreveu também que, naquele cenário, os
grupos dariam `ativo_circulante == 2.750,00` e `ativo_nao_circulante ==
8.500,00`. **Eu copiei os dois números para o critério 1 da DL-034 como
asserção obrigatória**, e repeti "no V1d" na tarefa do implementador.

**O implementador mediu e recusou, e estava certo.** No V1d o
`ativo_nao_circulante` é **8.000,00 e não pode ser outro**: (b) corrige
**sinal**, e o defeito do lado do Imobilizado no V1d é de **cobertura** — 500,00
parados num nó sem classificação. Nenhuma correção de sinal alcança isso. Ele
escreveu o motivo no comentário do teste (*"(b) é correção de SINAL, não de
COBERTURA"*) e montou um controle positivo separado, declarando honestamente que
**aquele** teste não depende de (b). A auditoria da DL-034 confirmou a
aritmética dele.

**Na rodada anterior foi a identidade aritmética** (DE-068). **Aqui foi um
número.** O padrão é o mesmo: frase de auditor promovida a critério **sem ser
redimensionada**.

**Alternativas descartadas:**

- *Não registrar a recomendação no plano* — pior: a boa ideia se perde e a
  medição nunca acontece. O valor da recomendação não está em dúvida; o que está
  em dúvida é o **número**.
- *Registrar o número com um "aproximadamente"* — critério de aceite não admite
  advérbio. Ou é asserção, ou é tarefa de medição.

**Consequência, e ela recai sobre mim:** ao transcrever recomendação de
auditoria para plano, procuro no relatório a declaração de limite do próprio
auditor. Havendo uma, o critério passa a ter a forma *"medir X no cenário Y e
registrar o valor encontrado, justificando-o"* — e **quem implementa tem
autoridade para recusar o número previsto, desde que escreva por quê**. Foi
exatamente o que aconteceu, e é o comportamento que queremos: a etapa foi salva
por um implementador que não obedeceu a um critério errado do arquiteto.

⚠️ **Relação com a [DE-058](#de-058) e a [DE-068](#de-068):** justificativa
escrita não é justificativa medida (DE-058); invariante precisa de escopo
(DE-068); e agora — **número de auditor sem execução é hipótese, não fato**. As
três são a mesma família: **o texto convence mais do que a medição que ele não
teve**.

## DE-070 — A condição 3 do Balanço é APOSENTADA como veto e vira informação declarada; o resíduo continua como cinto

**Data:** 2026-09-21

**Decisão:** a condição 3 do critério 1 da
[DL-034](../planos/DL-034-a-tela-do-balanco.md) —
*"nenhum grupo tem nó topo-classificado irmão de natureza cadastrada divergente"*
— **deixa de impedir a emissão**. Ela permanece **calculada e declarada** na
resposta, e a tela pode exibi-la como aviso; **não veta**. Permanecem como veto:
a condição 1 (`residuo_por_tipo` zero), a condição 2 (as listas de declaração
vazias) e a condição 4 (nó não-folha sem classificação própria nem ancestral com
movimento próprio).

⚠️ **E isto NÃO dispensa a correção do A1**, que continua **alta e obrigatória**:
enquanto a lista for calculada agrupando por `conta_pai` — `None` para **toda**
raiz —, ela **nomeia contas corretas** numa frase factualmente falsa
(*"sob o mesmo ancestral não classificado"*, quando não há ancestral). Um aviso
mentiroso é pior que um veto mentiroso, porque ninguém o corrige.

**Motivo.** Eu mandei "cinto e suspensório" — implementar (b) **e** manter as
guardas 3 e 4 — com um pressuposto explícito e datado: *"o próprio auditor
declarou o limite da sugestão dele (…) pode haver interação com retificadora **de
grupo** que ele não enxergou"*. **A auditoria da DL-034 mediu essa interação e ela
não existe:** com grupo retificador inteiro irmão do grupo bruto — a forma
clássica do Imobilizado brasileiro —, `ativo_nao_circulante = 12.000,00`, certo,
conciliando com `totais_por_tipo` no primeiro centavo. E na topologia do BL-486
puro, `ativo_circulante = 1.170,00`, certo. **O pressuposto que sustentava o
suspensório deixou de existir**; a partir daí a condição 3 só recusa casos em que
o número está **certo**.

**O caso concreto que isso destrava:** empresa com depreciação acumulada
classificada como grupo próprio — arranjo normal — não emitia Balanço.

**Alternativas descartadas:**

- *Manter a condição 3 como veto* — recusaria permanentemente planos corretos.
  O auditor colocou a bifurcação com precisão: mantê-la obriga a corrigir A1 de
  qualquer forma, e mesmo corrigida ela vetaria a retificadora de grupo, cujo
  número está provado certo.
- *Apagar a condição 3 inteira* — perderíamos um sinal barato sobre plano de
  contas incoerente. Declarar custa nada e não bloqueia ninguém.
- *Substituir por veto só quando o resíduo for diferente de zero* — é a
  condição 1, que já existe; não acrescenta.

**Consequência:** a condição 4 permanece **veto** porque cobre o defeito de
**cobertura** (valor que some dos grupos), que (b) não alcança — é o que o V1d
mediu. A DE-068 continua valendo: `Σ(grupos) + resíduo == totais_por_tipo` é
verdadeira **por tipo** e **não** limita o erro de grupo nenhum. **O que mudou
não foi a invariante: foi a prova de que (b) torna o número certo nas duas
topologias de retificadora que restavam.**

## DE-071 — Desligar uma trava exige prova de COMPORTAMENTO, uma por trava que sobrou; prova de ESTRUTURA não serve

**Data:** 2026-09-21

**Decisão:** quando uma decisão **desliga uma verificação que impedia uma
operação**, a prova exigida no plano é de **comportamento**: para **cada** trava
que permaneceu, um cenário em que **só ela** está acionada, exigindo que a
operação seja **recusada**. E o conjunto desses cenários é **derivado da própria
estrutura** que lista as travas — `pytest.mark.parametrize` sobre a tupla —, para
que a trava seguinte **nasça com o cenário junto**.

⚠️ **Prova de estrutura não substitui:** partição, união, interseção vazia,
congelamento de chaves e contagem de itens provam que **a lista está completa**.
**Nunca provam que um item está do lado certo.**

**Motivo, medido.** Na [DE-070](#de-070) eu aposentei a condição 3 do Balanço e
comprei como garantia que as duas tuplas — o que impede e o que só avisa — fossem
uma **partição exata** do inventário real de `apurar_saldos`. O auditor mediu o
que essa garantia **não** cobre:

> Movendo, **uma por vez**, cada uma das seis listas que vetam para a tupla que
> só avisa: **cinco delas passam com 1657 testes verdes**. E para uma —
> `contas_com_classificacao_aninhada`, justamente a que produz **resíduo zero** —
> **o Balanço passa a EMITIR**.

A partição continua **verdadeira** depois da troca: união e interseção não mudam
quando um nome muda de lado. **Partição é invariante de FORMA; veto é
comportamento.**

⚠️ **E o código escreveu a promessa que a medição desmente**, em dois docstrings
— o do teste do BL-502 e o de `avaliar_emissao_do_balanco` — afirmando que mover
uma lista de uma tupla para a outra faria um teste reprovar. **Vale para 1 das
6.**

**Alternativas descartadas:**

- *Não aposentar a condição 3* — o mérito da DE-070 não está em discussão: o
  pressuposto que a sustentava foi medido e caiu, e mantê-la recusaria planos
  corretos. O erro não foi desligar; foi **o que aceitei como prova**.
- *Um teste escrito à mão por trava* — resolve hoje e apodrece amanhã: a trava
  seguinte nasce sem cenário. Tem de ser derivado da tupla.
- *Confiar na revisão humana* — é exatamente a promessa que a A4 da rodada 1 já
  desmentiu.

**Consequência, e recai sobre mim primeiro:** ao escrever critério de aceite para
qualquer mudança que **afrouxe** uma verificação, a pergunta obrigatória passa a
ser *"qual cenário, sozinho, prova que cada trava restante ainda recusa?"* — e a
resposta vai no plano **antes** da implementação.

⚠️ **Relação com a [DE-058](#de-058), a [DE-068](#de-068) e a
[DE-069](#de-069):** é a mesma família, na quarta forma. Justificativa escrita
não é medida (DE-058); invariante precisa de escopo (DE-068); número de auditor
não testado é hipótese (DE-069); **e prova de estrutura não é prova de
comportamento**. ⚠️ **A DE-058 precisa alcançar o DOCSTRING, e não só o
comentário de justificativa** — foi ali que a promessa falsa morou desta vez, e é
a terceira ocorrência no projeto.

## DE-072 — Critério que toca fronteira definida por norma ou por documento do projeto cita o documento e a fronteira, nunca uma frase de prosa

**Data:** 2026-09-21

**Decisão:** quando um critério de aceite toca uma **fronteira** que uma norma ou
um documento do projeto define — o que está **dentro** e o que está **fora** de
um bloco, de uma classe de documento, de um período —, o critério **cita o
documento e a fronteira**, com a palavra que o documento usa. **Prosa de
recomendação não vira contrato sem essa citação.**

**Motivo, e o erro é meu e do auditor juntos.** O relatório da rodada 1 da DL-034
recomendou que a nota do RC-104 *"acompanhe o documento — **dentro do `<thead>`**,
junto do bloco do item 51"*. Eu transcrevi a frase para a tarefa. O implementador
leu *"dentro do bloco"* e pôs a nota **dentro** da
`<div class="identificacao-do-documento">`.

E a [personalizacao-de-relatorio.md](personalizacao-de-relatorio.md), §1, diz
para a classe 2: *"só **fora** do bloco obrigatório, que sai em cada página"*.

⚠️ **"Dentro do `<thead>`" e "dentro do bloco" são coisas diferentes, e só uma
respeita a regra do projeto.** A preposição era **carga contratual**. O resultado
está funcionalmente certo — a nota sai nas seis folhas, medido —, mas o bloco que
o instrumento trata como "o bloco prescrito pela norma" passou a conter um
parágrafo que **não é** nenhuma das cinco alíneas, com valor monetário dentro. O
oráculo do job passou a exigir a nota inteira como parte do bloco normativo.

**Foi o próprio auditor quem achou o erro dele**, na rodada seguinte, sem ser
perguntado — como na DE-068.

**Alternativas descartadas:**

- *Confiar na leitura do implementador* — ele leu exatamente o que estava
  escrito. O defeito é do enunciado.
- *Proibir recomendação em prosa* — perderíamos a melhor parte dos relatórios. O
  que muda é a **transcrição para o plano**, não o relatório.

**Consequência:** ao transcrever recomendação de auditoria que envolva fronteira,
eu cito o documento (arquivo e seção) e a palavra que ele usa — *dentro*, *fora*,
*em cada página* — em vez de reescrever com as minhas palavras. ⚠️ **É a
[DE-069](#de-069) numa escala menor: desconfie do número que o auditor não
testou, e desconfie também da PREPOSIÇÃO.**

## DE-073 — Quando duas frentes tocam o mesmo arquivo, o commit de integração declara a procedência

**Data:** 2026-09-21

**Decisão:** quando mais de uma frente tocou o **mesmo arquivo** numa janela de
trabalho, o **commit de integração declara no corpo** quais arquivos vieram de
qual frente e **quem mediu o quê**. Não é confissão: é **dado de auditoria**.

**Motivo.** Na rodada de correção da DL-034 um terceiro `especialista-frontend`
editou `views_web.py`, `balanco.html` e o CSS antes de eu mandá-lo parar —
sobreposição que **eu** causei ao distribuir. O agente que relatou a frente **não
escreveu parte do código que relatou**, declarou isso, e afirmou ter medido o que
herdou.

**Não houve defeito, e o auditor foi preciso sobre o motivo:**

> *"O terceiro agente não quebrou nada. Mas o único motivo de eu poder afirmar
> isso é que rodei `git diff | grep '^-'` e três mutações — **o histórico não
> distingue quem escreveu qual hunk**. O commit é uma frente só para quem o lê.
> (…) a próxima colisão vai depender de o auditor desconfiar — e **desconfiança
> não é mecanismo**."*

**O custo real da colisão foi tempo de auditoria**, e ele é invisível no relatório
se ninguém o disser.

**Alternativas descartadas:**

- *Confiar na divisão de arquivos para que isso não aconteça* — a divisão existe e
  eu a violei mesmo assim. Regra sem registro não sobrevive ao primeiro descuido.
- *Um commit por frente* — quebraria a integração: o contrato entre servidor e
  tela mudou no meio da janela, e commitar metade grava um estado vermelho.
- *Registrar só no relatório* — o relatório não acompanha o arquivo. O commit sim.

**Consequência:** a declaração entra no corpo do commit, junto da lista de
verificações executadas. E, quando houver código **herdado** de outra frente, a
tarefa do auditor diz com todas as letras: **verifique o herdado como se ninguém
o tivesse medido.** Foi o que fiz nesta rodada, e é o que deu base ao V11 do
relatório.

## DE-074 — O XML original é guardado ÍNTEGRO; os campos lidos são projeção derivada dele

**Data:** 2026-09-25

**Decisão:** na recepção de documento fiscal, o **arquivo original é persistido
íntegro**, byte a byte, como recebido. Os campos que o produto lê — identificador,
prestador, tomador, datas, valores — são uma **projeção derivada** desse
original, nunca a única cópia da informação. Reprocessar um documento já recebido
é **releitura do original guardado**, sem pedir nada ao escritório.

**Motivo — e ele tem um número medido por trás.** O acervo real do Fred mostrou
(**RC-76**) que **~12% das notas de serviço já trazem o bloco de IBS/CBS da
Reforma Tributária**, em 22 de 52 municípios. A pendência **PE-39** perguntava se
esse bloco entra no escopo da recepção agora ou depois, e a pergunta tinha uma
armadilha: **as duas respostas erravam.** Interpretar o bloco agora exige leiaute
e regra em fonte oficial vigente que não temos confirmados; **não** recepcionar o
bloco descarta informação que **já está chegando**.

Guardar o original íntegro **dissolve a pendência** em vez de decidi-la: nada se
perde, e a interpretação do bloco passa a ser uma etapa futura que lê o que já
está no banco. ⚠️ **A PE-39 deixa de ser bloqueio de escopo e passa a ser ordem
de trabalho.**

**E há três razões que valem independentemente da Reforma:**

1. **O documento é a prova.** Numa fiscalização, o que vale é o arquivo
   autorizado, não a nossa leitura dele.
2. **Todo leitor de leiaute erra na primeira versão.** Com o original guardado, o
   defeito se corrige e **reprocessa**; sem ele, o escritório reimporta 5.850
   arquivos à mão.
3. **O leiaute muda sem avisar** — o projeto já mediu duas versões convivendo
   (**RC-72**, `1.00` e `1.01`) e, na NF-e, manual e esquema **divergindo entre
   si**. Original guardado é a defesa contra leitura que envelheceu.

**Alternativas descartadas:**

- *Guardar só os campos lidos* — é o desenho que obriga reimportação a cada
  correção de leitor, e joga fora exatamente o que ainda não sabemos ler.
- *Guardar o original fora do banco, em pasta* — perde a atomicidade com o
  registro e o isolamento por empresa, e cria um segundo lugar para backup
  esquecer.
- *Decidir a PE-39 pelo "depois"* — seria descartar, hoje, informação de 12% das
  notas.

**Consequência, e o custo fica declarado, não escondido:**

- ⚠️ **O original contém dado real de cliente.** Ele é submetido ao **mesmo
  isolamento por empresa** de qualquer outro dado, **nunca** aparece em log, em
  mensagem de erro, na trilha de auditoria ou em teste — os testes usam **XML
  sintético**, sempre.
- **Entra no plano de backup e restauração** (AGENTS.md §10), e cresce com o
  volume: é armazenamento a dimensionar, não gratuito.
- A trilha de auditoria registra **que** um documento foi recebido, por quem e
  quando, **sem** copiar conteúdo.

## DE-075 — Evento órfão é GUARDADO, não recusado: aqui divergimos do sistema de referência, e a medição decide

**Data:** 2026-09-25

**Decisão:** documento de **evento** — cancelamento, substituição, rejeição — é
**aceito e guardado mesmo quando a nota a que ele se refere não está no sistema**,
e é **aplicado à nota quando ela chegar depois**. As duas ordens de chegada
funcionam.

**Motivo — e ele é um número, não uma preferência.** A consulta ao manual do
sistema de referência (2026-09-25) mostrou o comportamento oposto: no fluxo de
NF-e, **sem a nota já lançada o arquivo de cancelamento não entra**.

⚠️ **Se tivéssemos copiado esse comportamento, o acervo real do Fred perderia
100% dos cancelamentos.** A medição de 5.850 XMLs (**RC-70**) encontrou **29
cancelamentos, e os 29 apontam para nota que não está no acervo**. Evento órfão
**não é a exceção neste escritório: é o caso normal.**

**E a norma explica por que:** o leiaute oficial confirma (**RC-111**) que a
situação de cancelamento **não existe dentro do XML da nota** — `cStat` tem quatro
valores e nenhum é "cancelada". **O evento é a única fonte da informação de
cancelamento.** Recusá-lo por falta da nota é descartar a única prova de que a
nota não vale.

**Alternativas descartadas:**

- *Recusar, como o sistema de referência* — descartaria os 29 de 29. O precedente
  de outro produto não sobrevive a uma medição do acervo real.
- *Aceitar e aplicar só se a nota chegar na mesma importação* — o acervo prova que
  não chega: as notas correspondentes não estão nem no arquivo inteiro.
- *Guardar o evento como arquivo solto, sem interpretar* — perderíamos a aplicação
  automática quando a nota chegar, que é justamente o que o escritório precisa.

**Consequência:** a **situação do documento é derivada** — nota mais eventos
aplicados —, nunca copiada do XML (RC-111). E existe um estado que precisa ser
nomeado na tela e no relatório: **evento que ainda não encontrou a nota**. Ele
não é erro, não é pendência de cadastro: é informação guardada esperando par.

⚠️ **E o que isto NÃO autoriza:** apresentar como **válida** uma nota cuja
situação é desconhecida. Se os eventos não foram coletados, a situação de parte do
acervo é **desconhecida** — é a **PE-68**, levada ao Fred.

## DE-076 — A empresa do documento é identificada pelo CNPJ DO DOCUMENTO, não por uma empresa escolhida antes

**Data:** 2026-09-25

**Decisão:** na recepção, a empresa a que o documento pertence é determinada pelo
**CNPJ ou CPF gravado no próprio documento**, conferido contra as empresas do
**escritório ativo**. Documento que não casa com nenhuma empresa do escritório é
**recusado, com motivo, e não gravado** — nunca atribuído por dedução. Um mesmo
lote pode conter documentos de **várias** empresas do escritório, e cada um vai
para a sua.

**Motivo.** O sistema de referência faz o contrário (consulta ao manual em
2026-09-25): o operador **escolhe a empresa ativa antes** e o lote inteiro vale
para ela. É rotina legítima — e **perigosa no nosso contexto**, por uma razão
medida:

⚠️ **A organização de pastas do escritório é comprovadamente inconfiável.** A
medição do acervo (**RC-69**) encontrou **36 notas idênticas em duas pastas de
clientes DIFERENTES** e **105 notas repetidas dentro da mesma pasta**, catalogadas
ao mesmo tempo como entrada e como saída pela ferramenta de origem.

**Num lote assim, confiar na escolha prévia do operador importa documento para a
empresa errada — e silenciosamente.** Isso é pior que não importar: vira receita
escriturada no cliente errado.

**Alternativas descartadas:**

- *Copiar a empresa ativa do sistema de referência* — pelas 36 notas acima.
- *Deduzir a empresa pela pasta ou pelo nome do arquivo* — a **RC-71** já
  reprovou isso por medição: uma nota estava numa pasta chamada `DESCONHECIDO`,
  com `evento` no nome do arquivo, e era outro tipo de documento.
- *Criar a empresa automaticamente quando o CNPJ não é conhecido* — cria cadastro
  a partir de arquivo não conferido, e fere o isolamento entre escritórios.

**Consequência:** o critério 5 da DL-010 **recusa em vez de adivinhar**, e a
recusa **nomeia o motivo**. Um lote misto é suportado por desenho, não por
acidente. ⚠️ **E fica declarado o que isto custa:** documento de cliente novo,
ainda sem cadastro de empresa, **não entra** — e essa recusa tem de ser
compreensível, porque é a que o escritório vai encontrar no primeiro dia de uso.

## DE-077 — A mesma nota pertence legitimamente a DUAS empresas: a deduplicação é por (empresa, chave), nunca por chave global

**Data:** 2026-09-25

**Decisão:** a chave de deduplicação do documento fiscal é o par
**(empresa, chave)**, e **não** a chave sozinha. O documento carrega o **papel**
que aquela empresa tem nele — **serviço prestado** ou **serviço tomado** —,
derivado de o CNPJ/CPF da empresa casar com o **prestador** ou com o **tomador**.

**Motivo — e é a correção de um defeito que eu quase deixei passar.** O desenho
proposto pelo implementador punha `unique=True` **global** na chave, com o
argumento de que *"um `chNFSe` real pertence a uma nota real"*. A afirmação é
verdadeira **sobre o documento** e **falsa sobre a escrituração**:

> **Uma nota de serviço tem DOIS lados, e os dois podem ser clientes do
> escritório.** Para o prestador é **receita**; para o tomador é **serviço
> tomado**. Se o escritório atende as duas pontas — o que é comum —, a **mesma
> nota** precisa ser escriturada **duas vezes, em empresas diferentes**. Com
> `unique` global, a segunda importação seria recusada como "duplicada", e o
> escritório perderia a escrituração de um cliente **sem erro visível**.

⚠️ **E isto explica um número medido que estava classificado como defeito
alheio.** A **RC-69** registrou *"105 NFS-e idênticas dentro da mesma pasta — a
mesma nota catalogada em **Entradas** e em **Saídas** pela ferramenta de
origem"*. Isso não é só desorganização: é a ferramenta reconhecendo que **a nota
tem dois lados**. A rotina do sistema de referência confirma pelo outro ângulo —
a importação pergunta se é *serviço tomado* ou *prestado*.

**Dentro de uma mesma empresa**, a mesma chave duas vezes **é** duplicidade e é
ignorada (critério 15). **Entre empresas diferentes**, é a mesma nota vista dos
dois lados, e **as duas valem**.

**Alternativas descartadas:**

- *`unique` global na chave* — recusa silenciosamente a escrituração da segunda
  ponta. É o defeito descrito acima.
- *Gravar um registro só, compartilhado pelas duas empresas* — feriria o
  isolamento entre empresas, que é regra dura do projeto, e tornaria o documento
  de uma empresa visível na consulta da outra.
- *Perguntar ao operador de que lado é*, como o sistema de referência faz — o
  documento **já diz**: basta ver se o CNPJ/CPF da empresa está no prestador ou no
  tomador. Perguntar é pedir ao humano o que o dado responde.

**Consequência:** o papel é **derivado**, não digitado. Documento em que a empresa
aparece **nos dois lados** é anomalia e precisa ser **declarada**, nunca
adivinhada. E a recusa do critério 5 passa a valer quando **nenhum** dos dois
lados pertence a empresa alguma do escritório.

## DE-078 — Evento é escopado pelo ESCRITÓRIO e deduplicado por substituto DECLARADO

**Data:** 2026-09-25

**Decisão, em três partes:**

1. **O evento é escopado pelo escritório** que o importou, não pela empresa —
   porque o leiaute **não dá CNPJ/CPF ao evento**: ele traz apenas a referência à
   nota (`chNFSe`) e o código. Ele se liga à nota quando uma nota com aquela chave
   existir **no mesmo escritório**.
2. **A deduplicação do evento usa hash do conteúdo bruto**, e isso é **substituto
   declarado**, não campo normativo: ⚠️ **o leiaute não confirma identificador
   próprio para o evento**, diferente do `Id` de 53 caracteres da nota (RC-74).
3. **`DPS` e `pedRegEvento` avulsos são reconhecidos e contados em desfecho
   próprio** — nem aceitos como documento, nem marcados como erro —, porque o
   acervo medido não tem exemplar de nenhum dos dois e persistí-los exigiria
   inventar contrato.

**Motivo.** A **DE-076** manda identificar a empresa **pelo documento**. O
implementador achou o vão: **evento órfão não tem nota de quem herdar a empresa, e
não tem CNPJ próprio** — e órfão é o **caso normal** (29 de 29, RC-70). Sem uma
regra explícita, cada implementação inventaria a sua.

**O que faz a parte 2 ser honesta e não um atalho:** a [DE-060](#de-060) proíbe
**substituto não declarado**, não substituto. Hash de conteúdo **declarado como
substituto**, com o motivo escrito no código e o limite nomeado — reimportar o
**mesmo arquivo** não duplica; dois arquivos com formatação diferente e o mesmo
evento **podem** duplicar — é engenharia honesta. Chamá-lo de identificador do
evento seria a violação.

**Alternativas descartadas:**

- *Escopar o evento por empresa* — impossível para o órfão, que é a maioria.
- *Recusar o órfão para não ter o problema* — é a DE-075, já decidida contra, com
  a medição de 29 de 29.
- *Usar `chNFSe` + código como chave do evento* — a mesma nota pode receber o mesmo
  código mais de uma vez em fluxos de análise fiscal; e não há confirmação
  normativa de que o par seja único.

**Consequência:** existe um estado que a tela e o relatório terão de **nomear** —
**evento guardado, ainda sem nota**. Não é erro nem pendência de cadastro. E a
limitação do hash fica **escrita no código**, junto da constante.
