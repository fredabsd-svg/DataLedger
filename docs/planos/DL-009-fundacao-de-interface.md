# DL-009 — Fundação de interface

Fecha os itens **BL-20**, **BL-21**, **BL-22**, **BL-23**, **BL-24** e **BL-26**
do [backlog](../projeto/backlog.md), decorrentes da parte 2 do
[diagnóstico inicial](../auditorias/2026-09-11-diagnostico-inicial.md).

Implementa a decisão **DE-011** ([decisoes.md](../projeto/decisoes.md)).

**Estado:** em desenvolvimento.

## Objetivo

Dar à interface uma base utilizável por quem trabalha com contabilidade o dia
inteiro. Hoje os cinco templates existentes repetem cabeçalho, não têm
navegação, não exibem mensagem de sucesso alguma, e a falta de permissão devolve
texto cru sem caminho de volta.

## Problema, medido

Do diagnóstico, com arquivo e linha:

- **Nenhum template base.** Os 5 templates repetem `<!DOCTYPE>`, `<head>` e
  `<title>`. Nenhum `{% extends %}`, `{% block %}` ou `{% include %}`.
- **`django.contrib.messages` instalado e middleware ativo, e nenhum template
  renderiza mensagem.** Cadastro bem-sucedido redireciona sem qualquer
  confirmação.
- **Falta de permissão** devolve `HttpResponseForbidden` com texto cru, sem
  template nem link de saída.
- **Erro de troca de escritório é engolido em silêncio**: redireciona ao painel
  mesmo quando o vínculo não existe, sem avisar nada.
- **Zero CSS e zero JS.** Não existe diretório `static/`, embora `STATIC_URL`,
  `STATIC_ROOT` e WhiteNoise estejam configurados.
- **Acessibilidade:** `<select>` sem rótulo no painel; `<form>` aninhado dentro
  de `<p>` (HTML inválido); nenhum landmark (`<main>`, `<nav>`, `<header>`);
  erro de login sem `role="alert"`; foco visível apenas o padrão do navegador.
- **CNPJ exibido cru**, 14 dígitos sem máscara.

## Escopo delimitado

**Dentro:** template base, renderização de mensagens, estados faltantes,
acessibilidade, CSS próprio mínimo, formatação pt-BR de valores e datas, e
exibição do contexto de operação (escritório e empresa).

**Fora, declarado:**

- **Competência não entra.** O conceito **não existe** no código — nenhuma
  ocorrência em `apps/`, `config/` ou `templates/`. Modelá-lo é BL-15 e depende
  de decisão do Fred (PE-01, PE-05). Exibir um seletor de competência que não
  corresponde a nada seria tela demonstrativa, proibida pelo escopo do produto.
- **Telas de escrituração** (lançamento, diário, razão, balancete) não entram.
  Contabilidade só tem endpoints de API hoje; criar essas telas é etapa própria.
- Nenhuma biblioteca visual externa (DE-011).

## Critérios de aceite

| # | Critério |
| --- | --- |
| 1 | Existe `templates/base.html` com blocos de título, conteúdo e área de mensagens; os 5 templates existentes passam a estendê-lo, sem duplicar `<head>` |
| 2 | Navegação consistente presente na base, com link para painel e empresas |
| 3 | `messages` é renderizado na base; criar empresa com sucesso exibe confirmação |
| 4 | Troca de escritório inválida exibe mensagem de erro, em vez de redirecionar em silêncio |
| 5 | Falta de permissão usa template próprio, com explicação e link de volta — não texto cru |
| 6 | Cada template trata os estados aplicáveis: vazio, erro, sucesso e sem permissão |
| 7 | `<select>` do painel tem rótulo associado; nenhum `<form>` aninhado em `<p>`; HTML válido |
| 8 | Landmarks presentes (`<header>`, `<nav>`, `<main>`); atalho para o conteúdo |
| 9 | Erro de login associado ao campo e anunciado (`role="alert"`) |
| 10 | Foco visível explícito no CSS, com contraste suficiente; navegação completa por teclado |
| 11 | Existe `static/css/` com um arquivo próprio; nenhuma dependência externa adicionada |
| 12 | Valores monetários alinhados à direita, com separador de milhar e duas casas, em pt-BR |
| 13 | Datas em pt-BR; CNPJ exibido com máscara |
| 14 | Um total exibido **nunca** difere da soma das linhas exibidas; se houver diferença de arredondamento, ela é mostrada, não escondida |
| 15 | Escritório ativo visível em todas as telas de dados, e a empresa onde houver |
| 16 | Sem regressão: a suíte inteira continua passando |
| 17 | `ruff check`, `ruff format --check`, `manage.py check` aprovados |

## Regra de apresentação que não se negocia

**Não esconder informação contábil em favor da estética.** Se um valor não couber
na coluna, a solução é a coluna, não truncar o número. Débito e crédito devem
ser distinguíveis **sem depender apenas de cor** — quem não distingue vermelho de
verde precisa enxergar a diferença.

## Impacto

- **Contratos:** nenhum. Mudança de apresentação.
- **Dados:** nenhum.
- **Migração:** nenhuma.
- **Desempenho:** desprezível; um arquivo CSS estático.

## Reversão

Reverter o commit. Sem alteração de esquema nem de dado.

## Divisão de responsabilidade

| Agente | Arquivos |
| --- | --- |
| `arquiteto-senior` | `docs/**` |
| `especialista-frontend` | `templates/**`, `static/**`, `config/settings.py`, `apps/empresas/views.py`, `apps/tenancy/views.py`, `apps/accounts/**` |
| `desenvolvedor-pleno` | **não participa** — está em `apps/core/**` e `apps/contabilidade/**` na DL-008 |
| `auditor-qa` | nenhum (somente leitura) |

Divisão de arquivos disjunta, para que os dois trabalhem em paralelo sem
conflito. `apps/contabilidade/**` e `apps/core/**` estão **proibidos** nesta
etapa.
