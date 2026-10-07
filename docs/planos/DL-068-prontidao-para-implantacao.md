# DL-068 — Prontidão para implantação: cinco travas de segurança

**Demanda:** ordem direta do Fred, de 07/10/2026 (*"Autorizado fazer as 5
alterações"*), sobre a análise do repositório da mesma data (RC-157).
**Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-9e799dfb-48okf5` → `main`. **Risco:** nível 1. É defesa de acesso e
da trilha de auditoria antes do primeiro cliente real, por isso tem
auditoria independente com uma rodada, uma correção e uma reconferência
(§3.1).

**Fora do escopo:**
- backup e restauração (PE-07), que dependem de onde o sistema vai rodar;
- residência do dado (PE-25);
- os demais achados da análise: escritório inativo acessível, trilha de
  login sem escritório, 500 ao excluir escritório, `X-Forwarded-Proto` sem
  proxy, teto global de upload, sessão e 2FA, cadeia de suprimentos. Ficam
  registrados no backlog (BL-635 a BL-641). Os itens desta etapa sem número
  anterior viram BL-632 (login do admin), BL-633 (`.dockerignore`) e BL-634
  (Django 6.1.2).

## Problema

A análise de 07/10/2026 mediu cinco pontos que deixam a implantação insegura
mesmo com o produto correto.

| # | Ponto | Medição |
| --- | --- | --- |
| 1 | O Django está fixado em 6.1.1. O 6.1.2, de 06/10/2026, corrige 4 CVEs; o CVE-2026-84429 é uma negação de serviço moderada no leitor de cabeçalhos, alcançável sem login | `requirements/base.txt`; notas oficiais do 6.1.2 |
| 2 | `/admin/login/` não tem limite de tentativas. O limite da DL-056 vale só para `/login/` | Reproduzido: 30 senhas erradas e depois a correta entrou |
| 3 | Não há `.dockerignore`, e o `Dockerfile` faz `COPY . .`. O `.env` real e o `.git` entram na imagem | Inspecionado |
| 4 | Nada recusa `DEBUG=True` fora de desenvolvimento (BL-82). Quem copia o `.env.example` sobe a imagem com `DEBUG=True` | Inspecionado; `settings.py` já admite isso em comentário |
| 5 | `DJANGO_PROXIES_CONFIAVEIS` aceita `0.0.0.0/0` e `::/0`, e aí qualquer cliente forja o IP gravado na trilha (BL-577) | Reconfirmado na análise |

## Decisão (`arquiteto-senior`, reversível)

- **Item 1:** fixar `Django==6.1.2`. Sem outra mudança de dependência.
- **Item 2:** o admin usa um formulário de login que herda o limite do
  `LoginForm` da DL-056: mesma contagem por usuário e por IP, mesma reserva
  antes de verificar a senha, mesma mensagem do login inválido e o mesmo
  evento `login.bloqueado` na trilha. A contagem é **compartilhada** com
  `/login/`, porque são as mesmas credenciais e trocar de porta não pode
  zerar o limite. A exigência de `is_staff` do admin continua valendo.
- **Item 3:** criar um `.dockerignore` que exclua no mínimo:
  - segredos: `.env` e variantes;
  - histórico: `.git`;
  - ambiente local: `.venv`, caches e `staticfiles/`;
  - pastas de ferramenta de IA: `.claude/`, `.codex/` e `.agents/`.
  - O `.env.example` pode entrar.
- **Item 4 (BL-82):** o sinal de "fora de desenvolvimento" é uma variável
  **explícita**, `DJANGO_AMBIENTE`, com três valores: `desenvolvimento`,
  `homologacao` e `producao`. Não é inferido de nenhum outro valor.
  - Sem a variável, vale `desenvolvimento`, que é o comportamento atual
    (suíte, CI e a máquina do desenvolvedor).
  - Valor fora da lista: a aplicação recusa subir.
  - `homologacao` ou `producao` com `DEBUG=True`: a aplicação recusa subir,
    com mensagem que diz o que configurar.
  - A **imagem Docker declara `DJANGO_AMBIENTE=producao`**. Quem roda a
    imagem é produção até dizer o contrário: para usar o compose de
    desenvolvimento é preciso declarar `desenvolvimento` no `.env`, e o
    `.env.example` passa a trazer isso.
- **Item 5 (BL-577):**
  - Uma rede com prefixo `/0` (IPv4 ou IPv6) faz a aplicação **recusar
    subir**.
  - Rede larga que contém endereço público gera **aviso do `manage.py
    check`**: prefixo menor que `/24` em IPv4 ou menor que `/64` em IPv6. O
    aviso não impede a subida, porque há implantação legítima atrás de CDN
    com faixas públicas largas.
  - Rede privada larga, como `10.0.0.0/8`, não gera aviso.
  - Os limites `/24` e `/64` são **hipótese** (HI-51).

## Critérios de aceite

1. `requirements/base.txt` fixa `Django==6.1.2`, e a suíte roda com essa
   versão instalada.
2. Em `/admin/login/`, depois de N falhas na janela para o mesmo usuário, a
   tentativa seguinte é recusada **mesmo com a senha correta** de um
   superusuário, com a mesma resposta do login inválido. Depois da janela
   (relógio controlado), a senha correta entra.
3. As falhas em `/login/` contam para `/admin/login/` e vice-versa.
4. O limite por IP vale no admin entre usuários diferentes.
5. O bloqueio no admin gera `login.bloqueado` na trilha só com o resumo do
   usuário, nunca o texto digitado nem a senha.
6. Usuário sem `is_staff` continua recusado no admin, com a senha correta e
   abaixo do limite.
7. O `.dockerignore` exclui `.env`, `.env.*` (menos `.env.example`), `.git`
   e `.venv`. Um teste confere isso pelas regras de correspondência do
   arquivo, não por busca de texto.
8. `DJANGO_AMBIENTE=producao` com `DEBUG=True` recusa subir, em processo
   separado, com `ImproperlyConfigured` e mensagem que nomeia
   `DJANGO_AMBIENTE` e `DEBUG`. O mesmo vale para `homologacao`.
9. `DJANGO_AMBIENTE=producao` com `DEBUG=False` e PostgreSQL sobe, e `check
   --deploy` não dá aviso. Sem a variável e com `DEBUG=True`, sobe como
   hoje.
10. `DJANGO_AMBIENTE` com valor fora da lista recusa subir.
11. A imagem declara `DJANGO_AMBIENTE=producao`, e o `.env.example` declara
    `desenvolvimento`.
12. `DJANGO_PROXIES_CONFIAVEIS` contendo `0.0.0.0/0`, `::/0` ou
    `0.0.0.0/0` em meio a outros valores recusa subir.
13. Rede pública larga gera aviso no `check`. Rede privada larga, um IP
    único público e as redes `/24` e `/64` não geram aviso.
14. A suíte completa não regride em relação à linha de base de 07/10/2026:
    4.744 aprovados, 1 reprovado por ambiente (Python 3.13) e 53 pulados.

## Cenários de teste

- **Sucesso:** produção bem configurada sobe; desenvolvimento sem a variável
  sobe; admin com a senha correta abaixo do limite entra.
- **Erro:**
  - `DEBUG=True` em produção e em homologação;
  - valor inválido de ambiente;
  - `/0` em IPv4 e em IPv6;
  - bloqueio no admin;
  - não staff no admin.
- **Limite:**
  - exatamente N falhas, e depois N+1;
  - a janela vencida;
  - `/24` contra `/23`;
  - `/64` contra `/63`;
  - `/0` entre outros valores;
  - espaços e caixa no valor de `DJANGO_AMBIENTE`.

## Impacto e reversão

- **Segurança:** só aperta; nenhuma rota nova.
- **Dados:** nenhuma migração. A tabela `TentativaDeAcesso` já existe
  (DL-056).
- **Operação:** quem sobe a imagem com `DEBUG=True` precisa declarar
  `DJANGO_AMBIENTE=desenvolvimento`. Isso é intencional.
- **Reversão:** reverter o commit. Não há estado persistido novo.

## Distribuição

| Responsável | Itens | Arquivos que pode modificar |
| --- | --- | --- |
| `arquiteto-senior` | 1, plano, integração e documentação | `requirements/base.txt`, `docs/` |
| `desenvolvedor-pleno` (A) | 3, 4 e 5 | `config/settings.py`, `.env.example`, `Dockerfile`, `.dockerignore`, `apps/auditoria/checks.py`, `apps/auditoria/apps.py`, testes novos em `apps/core/tests/` e `apps/auditoria/tests/` |
| `desenvolvedor-pleno` (B) | 2 | `apps/accounts/forms.py`, `apps/accounts/admin.py`, `apps/accounts/apps.py`, testes novos em `apps/accounts/tests/` |
| `auditor-qa` | auditoria da versão integrada | nenhum, só leitura |

## Evidências

Ver a seção desta etapa no [estado](../agents/estado.md) e o relatório em
`docs/auditorias/`.
