# DL-037 — Entrada pública com hierarquia e primeiro acesso claros

**Estado:** integrada (PR #46, 25/09/2026). **Demanda:** Fred rejeitou visualmente a tela de login
após a integração da DL-036 e enviou captura em 25/09/2026. **Risco:** nível 2
(interface). **Branch:** `fix/dl-037-entrada-visual` → `main`.

## Problema, objetivo e escopo

A captura de 1911×905 mostrava o login ocupando uma faixa central pequena:
tipografia diminuta, metade da tela sem função e cadastro escondido como texto
secundário. O primeiro contato também precisava comunicar o papel central da IA
sem prometer integração já disponível. Redesenhar landing, login e cadastro com
um sistema visual coerente, ampliando leitura e colocando o caminho do novo
escritório em evidência. Preservar rotas, formulários, permissões e dados.

## Critérios e execução

1. Landing mostra em primeiro plano a concepção IA → serviços determinísticos →
   decisão humana e oferece ações distinguíveis de criar ambiente e entrar.
   Assistente, provedores e MCP continuam declarados como planejados.
2. Login apresenta campos e ação principal com hierarquia legível; novo
   escritório encontra o cadastro sem precisar procurar no rodapé. Cadastro
   explica que cria administrador e escritório, não uma empresa cliente.
3. Desktop e celular não têm overflow; o formulário funciona sem JavaScript,
   preserva foco, rótulos, erros, valores não sensíveis e resposta do servidor.
4. Estilo usa tokens em `base.css`, sem dependência externa ou alteração do
   visual interno. Testar navegação, erro de autenticação e validação do cadastro,
   lint, varredura, coleta de estáticos e captura Chromium das três telas.

Não há API, migração, cálculo ou contrato de dados alterado. Reversão por
revert do commit visual, sem tocar nos registros criados. Docker não está
disponível neste ambiente; `collectstatic` verifica o empacotamento CSS,
mas não substitui executar o contêiner.

## Evidência

Captura de referência enviada pelo Fred: login anterior com formulário estreito,
texto pequeno e CTA de cadastro pouco evidente. Após mudança: inspeção das
capturas em 1440×900, 1911×905 (medida da crítica) e 390×844, de landing,
login e cadastro, com HTTP 200 e sem overflow. O CTA do login chegou ao
cadastro e o envio vazio exibiu alerta e seis campos inválidos, sem JavaScript.

Validação local: 241 testes direcionados aprovados (26 avisos de SQLite),
`ruff check .` e `ruff format --check .` aprovados, `manage.py check` sem
problemas; `collectstatic --noinput`: 159 arquivos copiados, 5 inalterados,
424 pós-processados. A suíte PostgreSQL e os checks do commit final serão
conferidos no PR.
