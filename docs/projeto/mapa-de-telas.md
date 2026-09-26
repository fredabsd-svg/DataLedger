# Mapa de telas do DataLedger

Levantamento da DL-040, a pedido do Fred: quantas telas de navegação existem
hoje, onde há duplicação e como reorganizar a arquitetura de informação.
Medido em 2026-09-26 na urlconf real (`config/urls.py`) e por
`grep` dos `{% url %}` em `templates/**` — não copiado de memória.

**Método de contagem.** Conto rotas nomeadas fora de `api/` e `admin/`
(essas duas ficam de fora deste mapa — são 15 rotas REST e ~65 rotas do
admin do Django, medidas à parte, nunca telas do produto). Quando a MESMA
rota renderiza **experiências distintas** conforme estado ou papel (a
raiz `/` mostra a entrada pública para quem não está autenticado e o
painel para quem está; o Balancete tem um template alternativo quando a
emissão é recusada), conto cada uma como uma linha própria da tabela,
com a rota repetida e anotada — é o que "toda tela" pede, e "toda rota"
sozinho escondia a duplicidade de experiência atrás de uma URL só.

## Totais

| | Quantidade |
| --- | --- |
| Rotas web nomeadas (fora de `api/` e `admin/`) | **30** |
| — das quais sem nenhuma tela (só 405/ação) | 1 (`tenancy:emitir-convite`) |
| Telas distintas (rota + estado/experiência) | **33** |
| — **Ativas** (destino de navegação) | **14** |
| — **Secundárias** (confirmação, detalhe, ação, erro, download) | **19** |
| Rotas de API (DRF, JSON) | 15 (empresas 5, contabilidade 10) |
| Rotas do admin do Django | ~65 (geradas por modelo registrado) |

## Tabela completa

Colunas: **Rota** (nome completo, `namespace:nome`); **Tela**; **Template**;
**Arquétipo** (A–E, direção de arte §2); **Classe** (Ativa/Secundária);
**Quem acessa** (papel, verificado no servidor — a coluna descreve o
convite, nunca substitui a recusa real); **De onde se chega** (medido por
grep dos `{% url %}` existentes em `templates/**`, antes desta etapa — os
links que a DL-040 acrescentou estão marcados).

### Entrada pública e autenticação

| Rota | Tela | Template | Arquétipo | Classe | Quem acessa | De onde se chega |
| --- | --- | --- | --- | --- | --- | --- |
| `tenancy:painel` (`/`), anônimo | Entrada pública | `registration/landing.html` (via `registration/public_base.html`) | — (marketing) | Ativa | Qualquer visitante | URL direta; link "DataLedger." em qualquer tela pública |
| `cadastro` | Criar ambiente | `registration/signup.html` | B | Ativa | Visitante anônimo | Landing, `login.html`, `public_base.html` (nav) |
| `login` | Entrar | `registration/login.html` | B | Ativa | Visitante anônimo | Landing, `signup.html`, `public_base.html` (nav) |
| `logout` | — | nenhum (só POST, 302) | — | Secundária (ação) | Qualquer autenticado | Botão "Sair", `base.html`, toda tela autenticada |

### Tenancy (escritório e vínculo)

| Rota | Tela | Template | Arquétipo | Classe | Quem acessa | De onde se chega |
| --- | --- | --- | --- | --- | --- | --- |
| `tenancy:painel` (`/`), autenticado | Painel | `tenancy/painel.html` | D | Ativa | Qualquer autenticado | Home pós-login; link "Início"/"DataLedger." em toda tela (DL-040: `Início` no menu, com `aria-current`) |
| `tenancy:ativar` | — | nenhum (sempre 302 para o painel) | — | Secundária (ação) | Qualquer autenticado, com vínculo na empresa pedida | Formulário "Trocar de escritório" dentro do próprio `painel.html` |
| `tenancy:bootstrap-primeiro-acesso` | Criar o primeiro escritório | `tenancy/primeiro_acesso.html` | B | Secundária (ação única) | Autenticado sem nenhum vínculo ativo | `painel.html`, só quando `escritorios` está vazio |
| `tenancy:emitir-convite` | **— sem tela** | nenhum (só POST, 405 em GET) | — | **Não é tela** | ADMINISTRADOR do escritório (verificado no servidor) | **Nenhum link em `templates/**` aponta para cá** — ver "Achados", item 1 |
| `tenancy:aceitar-convite` | Aceitar convite | `tenancy/aceitar_convite.html` | B | Secundária (confirmação) | Autenticado, com token válido | Só por link direto (token no canal externo — e-mail, quando existir); **nenhum link em `templates/**`** aponta para cá a partir de outra tela do produto |

### Cadastros (empresas)

| Rota | Tela | Template | Arquétipo | Classe | Quem acessa | De onde se chega |
| --- | --- | --- | --- | --- | --- | --- |
| `empresas:lista` | Empresas | `empresas/lista.html` (ou `empresas/sem_escritorio.html`) | A | Ativa | Qualquer papel vinculado ao escritório ativo (a criação exige ADMINISTRADOR/GESTOR) | `painel.html`; DL-040: menu "Cadastros" (`Alt+M`) e "Contabilidade → Trocar de empresa`, em toda tela |
| `empresas:criar` | Nova empresa | `empresas/form.html` (ou `erros/sem_permissao.html`) | B | Secundária (ação) | ADMINISTRADOR, GESTOR | `empresas/lista.html`, botão "Nova empresa" |
| `empresas:trocar-secao` **(nova, DL-040)** | — | nenhum (sempre 302, ou `empresas/sem_escritorio.html`) | — | Secundária (ação) | Qualquer autenticado (a seção de destino recusa por conta própria) | DL-040: menu "Contabilidade → Trocar de empresa" (em toda tela de uma empresa) e `empresas/lista.html` ("Continuar aqui", quando chega com `?secao=`) |

### Contabilidade (por empresa — `contabilidade_web`, prefixo `contabilidade/painel/`)

| Rota | Tela | Template | Arquétipo | Classe | Quem acessa | De onde se chega |
| --- | --- | --- | --- | --- | --- | --- |
| `contabilidade_web:plano_de_contas` | Plano de contas | `contabilidade/plano_de_contas.html` | A | Ativa | Lê: ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO, PARALEGAL | `empresas/lista.html`, `_navegacao_empresa.html` (em toda tela de contabilidade), DL-040: menu "Contabilidade" |
| `contabilidade_web:conta_nova` | Nova conta | `contabilidade/conta_form.html` | B | Secundária (ação) | Escreve: ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO | `plano_de_contas.html`, `lancamento_form.html` (quando não há conta) |
| `contabilidade_web:lancamento_novo` | Novo lançamento | `contabilidade/lancamento_form.html` | B | Ativa | Escreve (mesmos papéis) | `empresas/lista.html`, `_navegacao_empresa.html` (item fixo) |
| `contabilidade_web:lancamento_detalhe` | Detalhe do lançamento | `contabilidade/lancamento_detalhe.html` | B (detalhe) | Secundária (detalhe) | Lê (mesmos papéis do Plano de contas) | Uma linha do Diário, do Razão ou da Conferência |
| `contabilidade_web:diario` | Diário | `contabilidade/diario.html` | A | Ativa | Lê | `_navegacao_empresa.html` (item fixo) |
| `contabilidade_web:razao` | Razão de uma conta | `contabilidade/razao.html` | A (recorte) | Secundária (detalhe de uma conta) | Lê | Uma linha/código do Balancete |
| `contabilidade_web:balancete` | Balancete de verificação | `contabilidade/balancete.html` | A | Ativa | Lê | `empresas/lista.html`, `_navegacao_empresa.html` (item fixo) |
| `contabilidade_web:balancete` (recusa 409) | Emissão do Balancete recusada | `contabilidade/balancete_emissao_recusada.html` | E (veto) | Secundária (erro de negócio) | Lê | Mesma rota do Balancete, quando débito ≠ crédito |
| `contabilidade_web:balanco` | Balanço Patrimonial | `contabilidade/balanco.html` | A | Ativa | Lê | `_navegacao_empresa.html` (item fixo) |
| `contabilidade_web:conferencia` | Conferência | `contabilidade/conferencia.html` | C | Ativa | Lê | `_navegacao_empresa.html` (item fixo), `fechamento.html`, `competencia_fechar.html` (quando há lote desbalanceado) |
| `contabilidade_web:fechamento` | Painel de fechamento | `contabilidade/fechamento.html` | D | Ativa | PodeFecharCompetencia: ADMINISTRADOR, GESTOR (leitura do painel: mesmos papéis que leem contabilidade) | `_navegacao_empresa.html` (item fixo) |
| `contabilidade_web:competencia_fechar` | Fechar competência | `contabilidade/competencia_fechar.html` | E | Secundária (confirmação) | ADMINISTRADOR, GESTOR | `fechamento.html` |
| `contabilidade_web:competencia_reabrir` | Reabrir competência | `contabilidade/competencia_reabrir.html` | E | Secundária (confirmação, ação sensível) | ADMINISTRADOR, GESTOR | `fechamento.html` |
| `contabilidade_web:competencia_entregar` | Marcar como entregue | `contabilidade/competencia_entregar.html` | E | Secundária (confirmação, **sem volta pelo produto** — RC-101) | ADMINISTRADOR, GESTOR | `fechamento.html` |

### Fiscal (`fiscal_web`, prefixo `fiscal/` — escopo do escritório, não de uma empresa só)

| Rota | Tela | Template | Arquétipo | Classe | Quem acessa | De onde se chega |
| --- | --- | --- | --- | --- | --- | --- |
| `fiscal_web:recepcao` | Recepção de documentos | `fiscal/recepcao.html` | C | Ativa | ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO | `_navegacao.html` (fiscal), DL-040: menu "Fiscal" |
| `fiscal_web:relatorio_envio` | Relatório do envio | `fiscal/relatorio_envio.html` | C | Secundária (relatório de uma ação) | Mesmos papéis da Recepção | `recepcao.html`, após um envio (PRG) |
| `fiscal_web:documentos_lista` | Documentos fiscais | `fiscal/documentos_lista.html` | A | Ativa | ADMINISTRADOR, GESTOR, ANALISTA, FINANCEIRO, PARALEGAL | `_navegacao.html` (fiscal), DL-040: menu "Fiscal" |
| `fiscal_web:documento_detalhe` | Detalhe do documento | `fiscal/documento_detalhe.html` | A (detalhe) | Secundária (detalhe) | Mesmos papéis da lista | `documentos_lista.html`, `relatorio_envio.html` |
| `fiscal_web:documento_xml` | Download do XML | — (anexo `application/xml`) | — | Secundária (download) | Mesmos papéis da lista | `documento_detalhe.html` |
| `fiscal_web:evento_xml` | Download do XML do evento | — (anexo `application/xml`) | — | Secundária (download) | Mesmos papéis da lista | `documento_detalhe.html` |

### Estados compartilhados (sem rota própria — respondidos por várias rotas)

| "Rota" | Tela | Template | Arquétipo | Classe | Quando aparece |
| --- | --- | --- | --- | --- | --- |
| (múltiplas — 403) | Sem permissão | `erros/sem_permissao.html` | B (estado) | Secundária (erro) | Qualquer rota de escrita/gestão quando o papel não autoriza (`empresas:criar`, `conta_nova`, `lancamento_novo`, as três ações do fechamento...) |
| (múltiplas — sem escritório) | Sem escritório ativo | `empresas/sem_escritorio.html` | D (estado vazio) | Secundária (estado vazio) | Qualquer rota de `empresas`/`contabilidade_web`/`fiscal_web` quando `request.escritorio` é `None` |

## Telas órfãs ou alcançáveis só digitando a URL

1. **`tenancy:emitir-convite` não tem tela nenhuma.** É `POST`-only
   (`require_http_methods(["POST"])`), sem template — um `GET` responde
   405. Nenhum `{% include %}`/`{% url %}` de `templates/**` aponta para
   cá: a capacidade existe no servidor (emitir convite para o segundo
   funcionário), mas **não há formulário nenhum na interface** para usá-la
   hoje. Achado, não conserto desta etapa — ver "Duplicadas, obsoletas ou
   unificáveis", item 4.
2. **`tenancy:aceitar-convite`** só é alcançável pelo token, por fora do
   produto (e-mail, quando existir — hoje o token só é devolvido na
   resposta HTTP de quem emite o convite, critério fora do escopo desta
   etapa). Esperado — é o padrão de convite por token —, mas registrado
   porque a pergunta "de onde se chega" precisa da resposta honesta:
   nenhum lugar dentro do produto linka para cá.

## Duplicadas, obsoletas ou unificáveis

Recomendações — **nenhuma rota nem fluxo foi removido nesta etapa**; a
decisão de remover é do arquiteto-senior/Fred.

1. **`tenancy:bootstrap-primeiro-acesso` (DL-018) × `cadastro` (DL-036).**
   As duas terminam no MESMO serviço,
   `apps.tenancy.services.primeiro_acesso.
   criar_primeiro_escritorio_e_vinculo_admin` — `cadastro` cria usuário
   **e** escritório num só formulário (visitante anônimo);
   `bootstrap-primeiro-acesso` cria só o escritório, para quem **já está
   autenticado** e ainda não tem vínculo algum (por exemplo, criado
   direto pelo admin do Django). Não é uma duplicata pura — as
   pré-condições são diferentes —, mas os dois formulários pedem
   `nome`/`cnpj` do escritório com campos e cópia quase idênticos, em
   dois lugares. **Recomendação:** o `bootstrap` poderia reaproveitar o
   MESMO formulário/parcial que `cadastro` usa para os campos do
   escritório (`CadastroForm` hoje mistura usuário + escritório num só
   form; extrair a parte do escritório serviria aos dois). Risco de
   manter como está: baixo — o caminho de `bootstrap` é raro (a rotina
   normal passa por `cadastro`), mas o texto pode divergir com o tempo se
   alguém editar um sem lembrar do outro.
2. **`tenancy:painel` × `empresas:lista`.** O painel, para quem já tem
   escritório ativo, mostra só o nome do escritório e um link para
   `empresas:lista` — nenhum conteúdo próprio além do seletor de
   escritório (relevante só para quem tem mais de um vínculo, minoria).
   **Recomendação:** não é urgente unificar (o painel continua sendo o
   destino de "Início" no menu, um ponto fixo e prático), mas a DL-040 já
   aproveitou o padrão de cabeçalho de página para dar a ele uma ação
   primária clara ("Ver empresas deste escritório"), reduzindo a sensação
   de tela vazia. Se o escritório tiver só uma empresa (caso comum),
   avaliar redirecionar direto para o Plano de contas dela seria um
   ganho de clique — decisão de produto, não tomada aqui.
3. **As três telas de confirmação do fechamento (`competencia_fechar`,
   `competencia_reabrir`, `competencia_entregar`) × o painel de
   `fechamento`.** **Não são duplicatas** — cada uma confirma uma ação
   DIFERENTE, e a maior (`competencia_entregar`) é a única sem volta pelo
   produto (RC-101): o arquétipo E ("assistente com etapas") pede
   exatamente essa separação, para a pessoa ver "o que vai acontecer"
   antes de confirmar, sem disputar espaço com o painel de status. **Não
   recomendo unificar** — juntar as três confirmações numa única tela ou
   modal aumentaria o risco de clique errado numa ação irreversível
   (`competencia_entregar`), o oposto do que a cerimônia proporcional ao
   risco (AGENTS.md §3.1) pede.
4. **"Ativar escritório" (`tenancy:ativar`) não tem tela própria** — é a
   `action` do formulário embutido em `painel.html`. Não há duplicação de
   INTERFACE aqui (é a mesma capacidade que `POST /api/escritorio-ativo/`
   expõe para a API — duas SUPERFÍCIES esperadas da mesma operação, não
   duas telas). Sinalizado só para constar que a pergunta foi verificada.

## Arquitetura de informação proposta

Árvore com o que **existe hoje** — nenhum módulo sem tela aparece nela
(Folha, Honorários, Paralegal e Financeiro **não existem** no produto e
não entram no menu, nem como "em breve": a direção de arte prefere não
mostrar a inventar um item desabilitado sem tela por trás).

```
Início (painel — "/" autenticado)
├── Cadastros
│   └── Empresas (lista, nova)
├── Contabilidade  — só aparece a quem lê contabilidade (papel ≠ CLIENTE)
│   └── [dropdown do menu, revisado na 2ª passada — lista TODAS as telas
│        ativas do módulo, agrupadas; sem empresa em contexto, mostra
│        "Escolha uma empresa" em vez de item quebrado]
│       Movimento     → Novo lançamento
│       Cadastros     → Plano de contas
│       Relatórios    → Diário · Balancete · Balanço
│       Rotinas       → Conferência · Fechamento
│                        Trocar de empresa (rodapé do dropdown)
│       (Razão e o detalhe de um lançamento continuam por DRILL-DOWN a
│       partir dessas telas, nunca por item fixo — exigem uma conta ou um
│       lançamento escolhidos, não são destino direto)
└── Fiscal  — só aparece a quem consulta documentos fiscais
    └── Recepção (Enviar notas · Envios anteriores) · Consulta (Documentos)

Conta (canto direito, não é módulo de navegação — ação de sessão)
└── Usuário (identificação) · Sair
    (Escritório ativo permanece na faixa de contexto, fora deste menu —
    ver direção de arte §8.4a)
```

**Redundância deliberada (2ª passada).** O dropdown de Contabilidade
agora repete os mesmos destinos de `_navegacao_empresa.html` (a barra
de sete atalhos dentro da tela de uma empresa). Isso reabre, de
propósito, a duplicação que a primeira passada desta etapa evitava —
ver a justificativa completa e as garantias que a mantêm segura (mesma
fonte de permissão/URL, atalhos `Alt+` só num lugar, teste de mutação
atualizado) na direção de arte, §8.1.
**Relatórios:** não entra como módulo próprio nesta etapa — os relatórios
existentes (Balancete, Diário, Razão, Balanço) já são o CONTEÚDO dos itens
de Contabilidade acima; um item "Relatórios" que apenas linkasse para as
mesmas quatro telas seria repetir o mesmo destino sob dois rótulos, e é
exatamente a duplicação que a DL-026 já pede para evitar.
**Configurações/Conta:** não existe tela própria de configurações hoje
(preferências de usuário, tema, notificação); o menu "Conta" agrupa
usuário e "Sair" (ação de sessão, não módulo de navegação) — não lista
"Convites" nem "Configurações" porque nenhuma tela existe para eles
(`tenancy:emitir-convite` não tem template — ver achado 1 acima).

## Decisão: barra superior, não lateral

**Escolhida: barra superior com dropdowns** (recomendação de partida do
arquiteto-senior, confirmada nesta etapa).

**Como foi decidido.** Sem alterar nenhuma regra de layout de
`.tabela-dados`/`.conteudo-principal`, a barra superior nova soma altura
no topo, não largura nas laterais. Medido por script Playwright contra o
produto real (`getBoundingClientRect`, não estimativa), no Balancete a
1440×900: o cabeçalho (marca + menu + faixa de contexto) termina a
**99,3px** do topo na versão desta etapa — era **106,4px** na versão
anterior à DL-040 (`92b4503`), ou seja, o cabeçalho em si ficou mais
compacto (menu "Conta" agrupado, 8.4a) apesar de ganhar o menu de módulo
completo. A trilha nova (8.2) soma altura própria ABAIXO do cabeçalho —
com ela e com `_navegacao_empresa.html` (mantida em telas largas, 8.1a),
o `<h1>` do Balancete fica a **204,6px** do topo (era 165,3px antes,
sem trilha). O aumento é esperado e aceito: é o preço de responder
"onde estou" em toda tela, não uma regressão de densidade — a LARGURA
útil da tabela é o que a régua de densidade (§4.8) protege, e essa não
mudou por causa da trilha (ao contrário, cresceu — ver 8.1b da direção
de arte, `--largura-conteudo` 1200px → 1440px). Uma barra lateral fixa,
pela própria régua do brief da DL-026 ("uma lateral fixa tira ~220px" de
LARGURA), reduziria a largura útil das tabelas em ~220px — o oposto do
que a DL-040 entregou. A DL-040 não tem base de medição própria com
contas suficientes para reproduzir o piso de 14/10 linhas da tabela §4.8
(a base de `scripts/semear_base_de_medicao.py` não foi semeada nesta
etapa — ver "Não testado", no relatório de entrega), então a comparação
de densidade EXATA fica **não medida por número de linhas**, mas o
raciocínio da régua (largura importa mais que altura para tabela larga)
já decide a favor da barra superior sem precisar do número exato. **Não**
foi medida uma variante lateral de verdade nesta etapa — a decisão é por
aplicação da régua já existente, não por um segundo protótipo.

## Fora do escopo desta entrega

- Não foi criada tela nova de emissão de convite (`tenancy:emitir-convite`
  continua sem interface) — fica registrado como achado (seção acima),
  não como correção: DL-040 é navegação da interface EXISTENTE, não um
  módulo novo.
- Não foi medida uma variante de menu LATERAL de verdade (só a superior,
  que é a implementada) — a decisão do item anterior se apoia na régua já
  publicada da direção de arte, não num segundo protótipo comparado lado
  a lado.
