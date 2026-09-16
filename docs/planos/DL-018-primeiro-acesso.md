# DL-018 — Primeiro acesso de uma instalação nova

**Estado:** **integrada em 2026-09-16** pelo PR #27, merge commit
`1b828e7`, com 5/5 checks verdes no GitHub. Respostas das três perguntas
ao Fred registradas em
[DE-042](../projeto/decisoes.md#de-042--dl-018-primeiro-acesso-via-produto-as-três-perguntas-respondidas)
(2026-09-16). Dependências anteriores resolvidas: a DL-017 fechou e a
DL-023 entrou na main pela rodada 3.

## Como isto apareceu

Não veio de auditoria. Veio de uso: o **Fred subiu o sistema pelo Docker em
2026-09-14**, criou o usuário com `createsuperuser`, entrou, e recebeu:

> **Nenhum escritório ativo**
> Seu usuário não tem vínculo ativo com nenhum escritório de contabilidade.
> Contate quem administra o cadastro para receber acesso.

A tela está **certa**. Ela explica, não quebra, e na variação de empresas
oferece o caminho de volta — é o tratamento de estado vazio da DL-009
funcionando como foi desenhado. O problema é outro: **não há para onde ir.**

A única saída é o admin do Django: criar `Escritorio`, criar
`VinculoUsuarioEscritorio` com papel `ADMINISTRADOR`, e só então cadastrar
empresa. Admin do Django é ferramenta técnica — o mesmo admin que a
[BL-83](../projeto/backlog.md) aponta como bloqueador de implantação por
permitir mover conta com movimento entre empresas.

Um contador que instalasse o DataLedger sozinho travaria exatamente aí.

## Por que três auditorias não pegaram

As três rodadas da DL-017 verificaram a interface com **cenário já montado** —
escritório, empresa e vínculo criados pela `fixture` de teste. O estado "banco
recém-criado, um usuário, nada mais" **não é cenário de teste de nenhuma
delas**.

O critério 13 da DL-017 pede vazio, erro, sucesso e sem permissão "com saída
navegável". Aqui a saída existe e é navegável — e leva ao admin técnico. O
critério foi atendido pela letra e falhou pelo propósito.

**A lição, e ela vale para toda etapa futura:** *estado inicial de instalação é
um estado da interface*, e precisa entrar nos critérios de aceite como os
outros quatro.

## Objetivo

Uma instalação limpa chega a **um lançamento contábil gravado** sem ninguém
abrir `/admin/` e sem comando além de subir o sistema.

## A classe do problema, não o caso

Escrito nesta forma por obrigação do backlog (BL-124, a lição que custou três
rodadas):

> **A classe é:** todo estado inicial alcançável por instalação limpa tem saída
> **pelo produto**. Nenhum fluxo de primeiro uso depende de ferramenta de
> administração técnica nem de linha de comando.

O caso que o Fred encontrou — usuário sem vínculo — é **exemplo**, não
definição. Outros estados da mesma classe, a levantar no desenho: escritório
existente sem nenhuma empresa; empresa sem plano de contas; plano de contas sem
conta que aceite lançamento.

## Perguntas ao Fred, antes de desenhar

Nenhuma destas é presumível, e duas são de sigilo — a resposta muda o desenho.

1. **Quem cria o escritório no mundo real?** No seu caso você mesmo. Num
   DataLedger que atenda mais de um escritório, quem cadastra o segundo — o
   próprio dono dele, ou alguém do DataLedger? A resposta define se existe
   autocadastro ou convite.
2. **O primeiro usuário vira administrador do escritório que criou?** É o
   caminho óbvio, e tem consequência: qualquer um que consiga criar conta passa
   a poder criar escritório. Aceitável numa instalação do escritório; perigoso
   numa instalação compartilhada.
3. **Como entra o segundo funcionário?** Convite por e-mail, cadastro por
   administrador, ou vínculo manual? Isso já roça a **PE-36** (quem lê
   contabilidade e se há vínculo usuário-empresa), que está aberta com você.

**Respostas registradas em [DE-042](../projeto/decisoes.md#de-042--dl-018-primeiro-acesso-via-produto-as-três-perguntas-respondidas)
(2026-09-16):** autocadastro assistido (o próprio usuário sem vínculo cria
o primeiro escritório) + primeiro usuário vira ADMINISTRADOR + convite
por e-mail para o segundo funcionário (papel inicial ANALISTA). Veja o
texto da DE-042 para os limites e a reversibilidade por bandeira
futura, se a auditoria da rodada 1 reprovar a hipótese.

## Hipóteses de trabalho, marcadas como tal

- **HI-1** ✅ **confirmada por DE-042:** a instalação típica é de **um
  escritório por instalação**, e quem instala é quem vai administrar. O
  caminho mais simples serve — usuário sem vínculo cria o primeiro
  escritório e torna-se seu administrador.
- **HI-2** ✅ **confirmada por DE-042:** a criação de escritório é
  ação **rara** — uma vez por instalação, ou uma por cliente do
  DataLedger. Não precisa ser cômoda; precisa existir e ser auditada.

Ambas confirmadas em 2026-09-16. A DE-042 registra os limites (papel
GESTOR/FINANCEIRO/PARALEGAL/CLIENTE não entram agora; SMTP real para
envio do convite fica para etapa posterior; PE-36 fica em aberto) e a
reversibilidade (se a auditoria reprovar o autocadastro, a DE-042 é
revogada e voltamos para convite obrigatório antes do primeiro
escritório).

## Critérios de aceite (rascunho, a fechar depois das respostas)

1. Instalação limpa → primeiro escritório → primeira empresa → primeiro
   lançamento, **sem tocar em `/admin/`** e sem comando além de subir o sistema.
   Teste que percorra isso de ponta a ponta.
2. A criação do primeiro escritório é **registrada na trilha de auditoria**, com
   quem criou e quando. Criar escritório é ato de sigilo: passa a existir uma
   fronteira de isolamento nova.
3. **Autorização verificada no servidor**, nunca só na tela: quem já tem vínculo
   não ganha poder de criar escritório por acidente, e quem não tem vínculo não
   enxerga dado de escritório nenhum enquanto não criar o seu.
4. O isolamento entre escritórios continua provado por teste depois do fluxo
   novo — **nenhuma rota nova consulta por `pk` sem amarrar ao escopo**.
5. Estados tratados: sem escritório, com escritório e sem empresa, com empresa e
   sem plano de contas, com plano e sem conta que aceite lançamento. Cada um com
   explicação e próximo passo.
6. Acessibilidade e uso **sem JavaScript**, como o resto da interface (DE-026,
   critério 15 da DL-017).

## Fora do escopo

Convite por e-mail, recuperação de senha, autocadastro público, e a decisão de
PE-36 sobre vínculo usuário-empresa. Se alguma delas se mostrar necessária para
o fluxo mínimo, **vira pergunta ao Fred**, não decisão minha.

## Risco principal

**Criar escritório é criar uma fronteira de sigilo.** É a operação mais sensível
do produto em termos de isolamento — e vai ser exposta na tela, para usuário sem
vínculo nenhum, que é o estado de menor privilégio que existe no sistema. Todo
cuidado que a DL-017 teve com "a regra de autorização mora num lugar só" vale
aqui em dobro.

## Git

- **Branch de trabalho:** `claude/dl-018-primeiro-acesso`, aberta a partir
  de `bfe9814` (cabeçalho pós-DL-023).
- **Branch de destino:** `main`.
- **PR:** #27, merge commit `1b828e7`, 5/5 checks verdes.
- **Commits notáveis:** `6321bc3` feat, `8bca8f2` style, `926c243`
  fix (varredura de contratos e de restrições), `4543873` test (view-por-POST
  para a BL-218).
