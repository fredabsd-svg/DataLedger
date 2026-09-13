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

**Decisão imediata e conservadora:** o papel **cliente deixa de ler** Diário,
Razão, Balancete e conferência. Os demais papéis vinculados ao escritório
seguem lendo, até decisão do Fred.

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
