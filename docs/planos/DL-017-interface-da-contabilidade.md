# DL-017 — Interface da contabilidade

**Estado:** fases A e B implementadas em 2026-09-14; **aguardando auditoria**.

## Critério 16 — o percurso feito pelo navegador

A prova de que a etapa saiu do papel. Servidor de desenvolvimento no ar, dados
**inteiramente fictícios** (Empresa Modelo Ltda, CNPJ de exemplo), percurso
feito por mim, `arquiteto-senior`, pelas telas:

1. Entrar no sistema.
2. Criar duas contas pelo formulário: `1.1.1 Caixa` (devedora) e
   `3.1.1 Receita de serviços` (credora).
3. Lançar **1.500,00** — débito em Caixa, crédito em Receita. Resposta da tela:
   *"Lançamento gravado com sucesso. Lançamento nº 1"*.
4. Conferir o mesmo valor nas três saídas, no mesmo período.

| Tela | O que mostrou |
| --- | --- |
| [Balancete](../assets/telas/balancete.png) | Caixa `1.500,00 D`, Receita `1.500,00 C`, total do período 1.500,00 / 1.500,00 |
| [Razão](../assets/telas/razao.png) | Saldo anterior 0,00, a partida, e saldo `1.500,00 D` |
| [Diário](../assets/telas/diario.png) | O lote com os totais |

As capturas foram feitas em Chromium, com a marcação e a folha de estilo que o
servidor entrega.

**Dois achados do percurso, registrados porque são de método:**

- **A tela recusou um envio meu, com mensagem precisa.** Preenchi parcialmente
  as linhas vazias do formulário e recebi *"Linha 3: preencha conta, tipo e
  valor, ou deixe a linha em branco"*. É a validação agindo no caminho real, não
  em teste.
- **Quase relatei um defeito que não existe.** Criei contas por requisição
  direta sem enviar `aceita_lancamento`; elas nasceram sem aceitar lançamento, e
  a tela seguinte disse, corretamente, que não havia conta disponível. Fui
  conferir o formulário: **a caixa vem marcada por padrão**. O defeito era do meu
  roteiro, que reproduziu alguém desmarcando a opção. Fica registrado porque a
  lição vale mais que o episódio: **reproduzir "pelo caminho de verdade" exige
  reproduzir o que o navegador envia**, não o que parece equivalente a ele.

## Por que esta etapa existe

A contabilidade funciona e está auditada, e **ninguém no escritório consegue
usá-la**: só responde por API. O Fred não consegue sequer testar o sistema com
uma empresa real sem programar.

É a onda 2 prevista na [DL-015](DL-015-contabilidade-utilizavel.md), agora com o
contrato das saídas estável e aprovado — que era a condição que eu mesmo pus
para começar. Fecha **BL-62**, e junto **BL-23** (formatação pt-BR), **BL-25**
(contexto de operação visível) e **BL-77** (saldo com indicador `D`/`C`).

## O que já existe, e não se refaz

A DL-009 entregou a fundação: `templates/base.html` com navegação, área de
mensagens e acessibilidade; `static/css/base.css`; templates de erro e de falta
de permissão; e o padrão de view que `apps/empresas` já segue. Esta etapa
**estende** isso, não recomeça.

## Decisão de arquitetura

**DE-026:** as telas são views Django chamando os serviços **diretamente**.
Nenhum JavaScript busca a própria API. O motivo é sigilo: a regra de quem lê
contabilidade passa a viver num módulo só, usado pela API e pela tela — não por
disciplina, por impossibilidade de divergir.

## Fases

### Fase A — backend de apoio (`desenvolvedor-pleno`)

Pequena, e vem antes porque a tela depende dela.

1. **Extrair a autorização de leitura de contabilidade** para um único lugar,
   usado pela API e pelas views web. Nenhuma regra de papel duplicada.
2. **BL-77 / RC-61:** a saída passa a trazer o saldo em **valor absoluto** com a
   **natureza** apurada (`D` ou `C`), em vez de número que pode vir negativo.
   Vale para `saldo_anterior`, `saldo_final` e a coluna `saldo` do Razão.

### Fase B — telas (`especialista-frontend`)

| Tela | O que faz |
| --- | --- |
| **Plano de contas** | Lista hierárquica, com criação de conta |
| **Lançamento** | Digitar partidas, **conferir o total antes de gravar**, gravar |
| **Diário** | Período, lotes com totais |
| **Razão** | Conta e período, com saldo anterior e coluna de saldo |
| **Balancete** | Período, nível opcional, quatro colunas mais o movimento próprio |
| **Conferência** | As categorias de inconsistência, em linguagem de contador |

## Critérios de aceite

Numerados para a auditoria conferir um a um.

### Autorização e sigilo

1. A regra de quem lê contabilidade existe **em um só lugar**. Teste que prove
   que API e tela decidem igual: o papel cliente recebe negativa nas duas, e os
   papéis operacionais, acesso nas duas. Mutar a regra no módulo compartilhado
   tem de derrubar teste **dos dois lados**.
2. Toda tela revalida no **servidor** a empresa pedida contra o escritório
   ativo. Pedir empresa de outro escritório não devolve dado, em nenhuma tela.
3. Falta de permissão usa o template próprio, com explicação e caminho de volta
   — nunca texto cru, nunca 500.

### Apresentação contábil

4. **Valores em pt-BR:** separador de milhar, vírgula decimal, duas casas,
   alinhados à direita. `1234567.89` aparece como `1.234.567,89`.
5. **Saldo com indicador `D`/`C`** (RC-61), em valor absoluto, nunca negativo.
   Conta retificadora aparece com o prefixo do nome preservado.
6. **O total exibido concilia com a soma das linhas exibidas.** Teste que soma o
   que está no HTML e compara com o rodapé — é a regra da DE-024 §2 chegando à
   tela, e é o que um contador faz com um balancete na frente.
7. Datas em pt-BR (`dd/mm/aaaa`) na exibição; o formulário aceita o que o
   navegador oferece e o servidor continua exigindo o formato do contrato.

### Operação

8. **Contexto visível** (BL-25): em toda tela de dados, o usuário identifica
   escritório, empresa e período em que está operando.
9. **Período obrigatório** nas três saídas, com valor inicial sugerido (mês
   corrente) e mensagem útil quando inválido — a tela não pode ser o caminho
   fácil que a DE-016 fechou na API.
10. **Conferência antes de gravar** o lançamento: a tela mostra o total de
    débitos e o de créditos e **impede o envio** enquanto forem diferentes. A
    validação do servidor continua sendo a que vale — a da tela é conveniência,
    e o teste tem de provar que o servidor recusa mesmo se a tela for burlada.
11. Duplo clique no botão de gravar **não** cria dois lançamentos (BL-43: a tela
    envia chave de idempotência por tentativa).
12. Do Balancete, clicar numa conta abre o **Razão dela no mesmo período**. Do
    Razão, chegar ao lançamento. É o caminho de conferência que um contador
    percorre, e hoje não existe.

### Estados e acessibilidade

13. Cada tela trata **vazio, erro, sucesso e sem permissão**, com saída
    navegável. Empresa sem lançamento no período mostra mensagem, não tabela
    vazia sem explicação.
14. **Acessibilidade:** todo controle com rótulo, HTML válido, navegação
    completa por teclado com foco visível, tabela com cabeçalho associado,
    mensagens anunciadas. Nenhuma informação transmitida só por cor.
15. A tela é **utilizável sem JavaScript**. Se houver JS, é melhoria; a página
    funciona sem ele.

### Verificação

16. Um lançamento é feito **pelo navegador**, do zero: criar conta, lançar,
    conferir no Diário, no Razão e no Balancete — com evidência registrada.
17. Suíte, `ruff check`, `ruff format --check`, `manage.py check` e migrações em
    banco vazio limpos, **verificados em árvore limpa** (`git archive` em
    diretório vazio, BL-81). Nenhuma regressão nos 402 testes.

## Fora do escopo

Competência e fechamento (DL-016), centro de custo, Balanço, DRE, impressão em
PDF, paginação (BL-76 — entra quando houver volume real), e os itens BL-83 a
BL-86 da auditoria anterior.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` (fase A) | `apps/contabilidade/views.py`, `services.py`, `permissoes.py` (novo), `apps/contabilidade/tests/**` |
| `especialista-frontend` (fase B) | `apps/contabilidade/views_web.py` e `urls_web.py` (novos), `templates/contabilidade/**`, `static/css/**`, `apps/contabilidade/tests/test_dl017_*.py` |
| `arquiteto-senior` | documentação, `config/urls.py` e a costura entre as fases |

A fase B só começa com a fase A integrada.

## Riscos

- **Duplicar a regra de sigilo** é o risco central, e é o motivo de a fase A vir
  primeiro. Já aconteceu uma vez neste projeto, e a auditoria levou duas rodadas
  para encontrar.
- **Formatar valor na camada errada.** Formatação é apresentação; o valor
  continua `Decimal` até o template. Nenhum `float` em nenhum ponto.
- **Volume:** um Diário anual sem paginação é uma página enorme. Declarado fora
  do escopo, com BL-76 registrado.

## Git

- **Branch de trabalho:** `claude/accounting-agent-team-setup-mn6lyf`
- **Branch de destino:** `main`
