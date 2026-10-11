# DL-086 — Revisão de layout, botões, páginas e acessos

**Demanda:** ordem direta do Fred de 11/10/2026 — *"revise e melhore o layout,
botões e páginas do sistema, bem como acessos e demais"* (§0 do AGENTS.md:
demanda formal, verbo "melhorar" = autorização para alterar). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `feat/dl-086-revisao-layout-e-acessos`
→ `main`. **Risco:** nível 2 (§3.1 — telas e fluxos), com UM item nível 1
(motivo obrigatório no estorno do livro-caixa, que toca trilha de operação do
livro) sujeito ao ciclo de auditoria independente do §3.1.

## Método

Três auditorias SOMENTE-LEITURA independentes, em paralelo (equipe multiagente
na esteira da DL-070): (1) design de `templates/fiscal/` + `templates/livro_caixa/`
contra o [contrato visual](../projeto/direcao-de-arte.md); (2) design da fundação
(`base.html`, `base.css`, telas públicas) + contabilidade/core/empresas/tenancy;
(3) acesso ponta a ponta (rotas públicas, sessão, login, cadastro, convites,
papéis, isolamento/IDOR em 22 views amostradas, trilha). Achados consolidados
pelo arquiteto, verificados no terreno antes de entrar no escopo (arquivo:linha
conferido por leitura direta; cálculos de contraste pela fórmula WCAG de
luminância relativa). A implementação foi particionada por módulo — nenhum
arquivo tem dois donos.

## Escopo implementado

Achados citados pelo id do relatório de auditoria (A-nn fiscal/livro-caixa,
C/D/E/F/G/H-nn fundação, C-nn acesso — o relatório consolidado mora no PR).

**Casca e fundação (base.html, base.css, public.css, module-home.css):**
gaveta móvel ganha controle "Fechar menu" interno e o interruptor de recolher
some do tab order em ≤48rem (C-01 alta, C-02); dropdown "Cadastros" com `open`
condicional como os demais módulos (C-03); rótulo do alternador reflete o
estado recolhido/expandido (C-04); `--tinta-media` escurecido para ≥4,5:1
sobre `--app-fundo` — o token foi calculado para o canvas bege antigo (A-01);
contagens/totais do Início migram de `--acento` para `--app-acento` — uma tinta
por superfície, DE-080 (A-02); a regra de link de prosa para de vencer a tinta
declarada de cartões/KPIs, mesma classe de defeito do §8.3 (F-01); remoção de
~150 linhas de CSS morto (`.navegacao-empresa`, `.sessao-usuario`,
`.contexto-operacao`, família `.cabecalho-pagina`), token órfão
`--acento-suave` e comentários que descrevem mecanismo que não existe mais
(A-03); botão: foco não duplicado por componente, `:active` sem depender de JS,
`<a>` e `<button>` com a mesma altura, `[aria-disabled]` coberto (B-01);
`.public-button` ganha `:active`/`:disabled` (E-02); tokens `--mh-*` com
governança registrada (A-04 — promoção ao `:root` fica no BL-696).

**Contabilidade, core, empresas, tenancy, telas públicas:** trilha padrão volta
a nomear a tela atual em DRE, DLPA, DMPL, DFC, Relatórios e Parâmetros
contábeis — 6 entradas em `ROTULOS_DE_TELA` (D-01, §8.2); `<th scope="row">`
das partidas com `.cabecalho-de-linha` (F-02); conferência da exportação
migrada para os componentes existentes — `.relatorio-conferencia` não existe
em CSS nenhum (F-03); estados vazios da fundação migram para `.estado-vazio`
com CTA permitida pelo papel (F-04); grupo de radios do balancete com
`.campo-radio`/fieldset (F-05); checkboxes de confirmação com `.campo--caixa`
(F-06); linhas do plano de contas com 3+ ações agrupadas em `.menu-acoes`
(F-07, §8.4b/DE-084); "Salvar" genérico vira rótulo que nomeia a consequência
e a tela volta a ter UM primário (F-08); help_text visível padronizado (F-09);
mensagem pós-cadastro para de prometer a tela de convite que não existe
(F-10); handlers 404/403/500 com a cara do produto — 403 reaproveita
`erros/sem_permissao.html` (H-01); 403 diz o próximo passo ("fale com um
administrador ou gestor") (H-02); cartão de login ganha o caminho honesto de
recuperação de senha enquanto o fluxo completo (BL-640) não existe (E-01);
"Buscar empresa" sinaliza que precisa de JS (G-01); início usa
`papel_pode_ler_carteira` onde o dado é carteira (BL-585).

**Fiscal:** confirmação sensível de retenção com `--perigoso` e rótulo que
nomeia a nota (A-01); "Estornar escrituração" unificado em `--perigoso`
(A-07); ações que SOMIAM para quem não tem permissão viram botão desabilitado
COM MOTIVO (A-03, A-04 — §2B); ações de linha ganham alvo oculto — nunca só
"Confirmar" (A-06, §8.4); estados vazios completam a anatomia de
`.estado-vazio` (A-12, A-13); "Limpar filtros" nas 4 parciais de filtro, uma
mudança que atinge 17 telas (A-14); link solto em célula de ação vira botão
pequeno (A-18); `role="alert"` faltante (A-20).

**Livro-caixa:** estorno de lançamento passa a exigir MOTIVO obrigatório,
gravado na trilha — nível 1, mesmo contrato dos cinco estornos fiscais
(A-02); ação primária que some para leitor vira desabilitado com motivo
(A-05); erros de formulário falam a língua do contador, não o nome técnico do
campo (A-09); `scope="rowgroup"` nas linhas de seção do tbody (A-10); grupo de
radios "Recebido de" com nome acessível (A-11); estados vazios no componente
(A-12, A-24); lista de lançamentos paginada (A-15); "Salvar" nomeia a
consequência (A-19); texto-apoio de formato monetário como no fiscal (A-21).

**Decisão de design registrada (DE-101):** encerrar/fechar período ou
vigência é ação sensível — tom `--perigoso` em todo o produto (livro-caixa
A-08, contabilidade `competencia_fechar`, fiscal já era); o §8.4 do contrato é
atualizado. Reabrir/entregar já eram sensíveis; encerrar bloqueia período e
entra na mesma família.

**Acessos (servidor):** cadastro público reserva a tentativa ANTES de validar
e, bloqueado, responde só com a mensagem de limite — hoje a enumeração de
e-mail/CNPJ pelas mensagens de validação é ilimitada porque o limite DL-056 só
conta formulário válido (C-01 acesso, nova); trilha `login.falha` e
`login.bloqueado` com a MESMA chave de detalhes — a correlação prometida pela
`resumo_do_usuario` existia só no docstring (BL-593); papel sem leitura recebe
403 idêntico para empresa existente e inexistente — o papel é checado ANTES de
resolver o id, nos dois módulos; o 403 uniforme preserva o B7 da DL-038
(nenhum regime de escrituração é revelado a quem não lê) (BL-584);
`SECURE_REFERRER_POLICY = same-origin` — reduz o vazamento do token de
convite na URL via Referer (parte do C-07 acesso; CSP inteira fica no BL-689).

**Portabilidade Windows (nível 3, feita e verificada antes do plano):** três
controles positivos da varredura de interface comparavam caminho nativo
(`static\css\...`) com literal POSIX — `as_posix()`; `.gitattributes` ganha
`apps/fiscal/dados/*.csv -text` (o sha256 da tabela CFOP da DL-081 não batia
em clone com `core.autocrlf=true`) e `apps/livro_caixa/tests/fixtures/**/*.csv
-text` (as fixtures são cópia byte a byte dos modelos da RFB, ISO-8859-1 +
CRLF — conversão as desfiguraria em silêncio).

## Fora do escopo, registrado

Viram itens novos no [backlog](../projeto/backlog.md): BL-689 (CSP), BL-690
(token de convite em claro no banco → hash), BL-691 (tela de emissão de
convite + canal de entrega), BL-692 (erro por campo nos formulários
multicampo — três mecanismos convivem), BL-693 (etapa de confirmação para
confirmar folha/receita do mês — hoje POST direto na linha), BL-694 (estado
"enviando" no upload de XML/ZIP), BL-695 (dois mecanismos de entrada de
período entre módulos — decisão do Fred), BL-696 (governança dos tokens
`--mh-*`). Seguem abertos, citados no relatório do PR: BL-18, BL-35, BL-547,
BL-548, BL-552, BL-580/581/642, BL-598, BL-599, BL-640, BL-652, BL-653.
Recuperação de senha completa e 2FA permanecem decisão do Fred (BL-640).

## Critérios de aceite

1. Varredura de interface e suíte completa sem reprovação nova contra a linha
   de base medida em 10/10/2026 na `main` (Windows/PostgreSQL 16.15: 8.740
   aprovados, 29 reprovados — 4 de portabilidade, corrigidos nesta etapa; 25
   de ambiente: umask/POSIX, Chromium e poppler); `ruff check`,
   `ruff format --check`, `manage.py check`, `makemigrations --check` limpos.
2. Gaveta móvel: aberta a 390×844, fecha por controle interno visível; sem
   parada de teclado invisível (medido em Chromium real, não alegado).
3. Contraste calculado: `--tinta-media` ≥4,5:1 sobre `--papel`, `--papel-alt`
   e `--app-fundo`; cor COMPUTADA de cartão/KPI/tile = `--tinta`
   (getComputedStyle).
4. Trilha das 6 telas termina no nome da tela atual, em texto, com
   `aria-current="page"`.
5. Papel sem leitura: mesma resposta (status e corpo) para `empresa_id`
   existente e inexistente em toda rota com `empresa_id` dos dois módulos —
   teste derivado do urlconf, não de lista escrita à mão.
6. POST `/cadastro/` inválido consome cota do limite por IP; acima do limite,
   a resposta não revela qual campo colidiu.
7. `login.falha` e `login.bloqueado` do mesmo usuário digitado compartilham a
   mesma chave e o mesmo valor de resumo na trilha (teste de correlação).
8. Estorno no livro-caixa sem motivo é recusado (400/tela com erro); com
   motivo, o lançamento é estornado uma vez e o motivo sai na trilha; mês
   encerrado continua recusando (regressão DL-053/054 verde).
9. 404/403/500 renderizam a moldura do produto (500 sem depender de banco).
10. Botões: nenhuma ação sensível de encerrar/estornar/reabrir/entregar fora
    do tom `--perigoso`; nenhuma ação de linha sem alvo no nome acessível;
    nenhum submit genérico "Salvar" nas telas tocadas.

## Testes e validação

Por módulo: `pytest apps/<app> -q` com banco de teste próprio por agente
(nome trocado no `DATABASE_URL`, padrão do [estado](../agents/estado.md));
guardas estáticas (`test_dl024_varredura_de_interface.py`,
`test_dl024_atalhos_e_acessibilidade.py`) a cada alteração de template; suíte
completa ao final; medição em Chromium (Playwright local) para os critérios 2
e 3; `pwsh ./scripts/validate-docs.ps1` para a documentação. Item nível 1
(A-02): testes de sucesso/erro/limite + auditoria independente com uma
rodada, uma correção e uma reconferência (§3.1 — regra de parada respeitada).

## Segurança, dados e reversão

Sem mudança de autorização: quem podia continua podendo; o que muda é a
uniformidade da recusa (BL-584) e a taxa do cadastro (C-01). Migração só se o
motivo do estorno exigir campo próprio (decide a implementação, espelhando o
padrão dos estornos fiscais — se a trilha carrega o motivo, sem migração);
havendo migração, teste em banco vazio. Reversão: reverter o commit; dados
gravados não mudam de forma.

## Equipe

| Papel | Função |
| --- | --- |
| arquiteto (sessão principal) | consolidação, casca/CSS/fundação, acessos, BL-584 contabilidade, docs, integração |
| 3 implementadores (subagentes) | fiscal; livro-caixa (inclui o item nível 1); contabilidade/core/tenancy/registration |
| auditor independente (subagente fork) | auditoria do item nível 1 e verificação adversarial da consolidação |

## Evidências

Ver a seção desta etapa no [estado](../agents/estado.md), o diff do PR e a
saída dos comandos acima, registrada no relatório de entrega.
