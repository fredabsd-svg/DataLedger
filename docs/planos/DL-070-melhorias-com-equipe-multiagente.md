# DL-070 — Melhorias do repositório com equipe multiagente

**Demanda:** ordem direta do Fred, de 08/10/2026 (RC-160): *"Atue como uma
equipe multi-agente para analisar e melhorar o meu repositório"*, com
orquestrador em Opus, desenvolvedores em Haiku em paralelo e auditor em
Sonnet. **Estado:** [fonte única](../agents/estado.md). **Branch:**
`ccr-bf4b4a55-hpqgbp` → `main`. **Risco:** nível 2 (§3.1): telas, API e
testes; **nenhuma regra de cálculo, saldo ou lançamento muda**.

## Por que o escopo é este

A ordem fixa o modelo dos desenvolvedores em Haiku, o que diverge da RC-143
("implementação nunca em Haiku"). A ordem mais recente prevalece (AGENTS.md
§0, regra 2), e o arquiteto a cumpre **restringindo o escopo** ao que um
modelo menor executa com segurança: correções de entrada, consultas, textos e
testes. Código de nível 1 de produção (lançamento, saldo, competência,
demonstração, gatilho) fica **fora** desta etapa. Toda a entrega passa pelo
auditor em Sonnet antes de ser dada como pronta.

⚠️ **Correção da classificação (achado A7 da auditoria, 08/10/2026):** a
frase "nível 1 fica fora" afirmava mais do que ocorreu. Dois itens **tocam**
nível 1 do §3.1: o BL-651 (oráculo de existência de escritório, isolamento) e
o BL-649 (consulta da trilha de auditoria). Nenhum dos dois muda regra
contábil, mas foram implementados por Haiku — e o controle que vale para
eles é a **auditoria independente**, que os cobriu com mutação.

Origem dos itens: análise do repositório de 08/10/2026 feita por dois
`auxiliar-pesquisa` (triagem do backlog aberto e varredura independente de
defeitos), com reprodução executada em PostgreSQL 16.

## Frentes de trabalho (arquivos disjuntos)

| Frente | Itens | Arquivos permitidos |
| --- | --- | --- |
| A — entradas do acesso | BL-645, BL-646, BL-647, BL-651 | `apps/tenancy/views.py`, `apps/tenancy/services/primeiro_acesso.py`, `apps/tenancy/services/convites.py` (se existir), `apps/tenancy/forms.py` (novo ou existente), `apps/tenancy/tests/test_dl070_entradas_do_acesso.py` (novo), `apps/tenancy/tests/test_dl018_primeiro_acesso.py` (só para trocar CNPJ inválido por válido) |
| B — consultas por linha (N+1) | BL-648, BL-649 | `apps/empresas/views.py`, `apps/empresas/serializers.py`, `apps/auditoria/views.py`, `apps/auditoria/serializers.py`, `apps/empresas/tests/test_dl070_consultas_da_lista.py` (novo), `apps/auditoria/tests/test_dl070_consultas_da_trilha.py` (novo) |
| C — testes que faltavam e texto do convite | BL-600, BL-602, BL-619 | `templates/tenancy/aceitar_convite.html`, `apps/tenancy/tests/test_dl059_trilha_do_convite.py`, `apps/livro_caixa/tests/test_dl060_confirmacao_da_cascata.py`, `apps/contabilidade/tests/test_dl070_admin_da_conta_na_trilha.py` (novo) |
| D — comentários (nível 3) | BL-575, BL-591 | `apps/livro_caixa/models.py` (só comentário), `config/settings.py` (só comentário) |
| Arquiteto | registro | este plano, `docs/agents/estado.md`, `docs/projeto/backlog.md`, `docs/projeto/requisitos.md`, `docs/planos/DL-069-travas-no-banco.md`, `docs/auditorias/` |

## Critérios de aceite

1. **BL-645.** `POST /bootstrap/` com CNPJ malformado (`abc`), com máscara
   que não cabe na coluna ou já cadastrado responde com mensagem de erro na
   própria tela (nunca 500) e **não cria** `Escritorio`. A validação é a
   **mesma** do cadastro público (`normalizar_cnpj`/`validar_cnpj`), sem regra
   nova de CNPJ. CNPJ válido com máscara é normalizado e aceito.
2. **BL-646.** `nome` com mais de 200 caracteres no `/bootstrap/` é recusado
   com mensagem, sem 500 e sem gravar.
3. **BL-647.** `POST /convites/emitir/` com e-mail malformado ou acima de 254
   caracteres é recusado com mensagem, sem 500 e sem criar convite.
4. **BL-651.** `POST /convites/emitir/` com `escritorio_id` de escritório em
   que o usuário não tem vínculo responde **igual** a id inexistente (não
   revela existência). A autorização continua no servidor.
5. **BL-648.** `GET /empresas/api/empresas/` faz número de consultas
   **constante** em relação à quantidade de empresas (medido com 2 e 20), e o
   `regime_atual` devolvido é o mesmo de antes.
6. **BL-649.** `GET /api/auditoria/` faz número de consultas constante em
   relação à quantidade de registros com usuários distintos, e o conteúdo do
   campo `usuario` é o mesmo de antes. **Sem paginação nesta etapa** —
   paginar muda o contrato da API (BL-35).
7. **BL-600.** Token de convite inexistente mostra "inexistente ou inválido",
   sem "consumido" e sem o botão de aceitar.
8. **BL-602.** A parametrização ganha o caso `(1, _meses(1, 2, 3))`, que passa
   no código atual.
9. **BL-619.** Teste que altera a coluna da DMPL de uma conta **pelo admin** e
   exige o registro `contabilidade.conta.admin_atualizado` com a chave no
   antes/depois. Se passar, o BL-619 fecha com a evidência; se falhar, é
   defeito e volta ao arquiteto.
10. **BL-575 e BL-591.** Comentários corrigidos, sem mudança de código.
11. **Não regressão:** `ruff check`, `ruff format --check`, `manage.py check`,
    `makemigrations --check` limpos; `pytest` completo sem reprovação nova em
    relação à linha de base medida no início da sessão.

## Fora do escopo, registrado

- BL-650 (novo): histórico começando com `=`, `+`, `-` ou `@` no CSV do
  carnê-leão pode virar fórmula ao abrir na planilha. Escapar altera dado
  dentro de leiaute oficial: **decisão do Fred**.
- BL-593, BL-622, BL-636, BL-637, BL-641 (lock com hashes): nível 1 ou
  dependentes de decisão/etapa bloqueada (ver triagem no estado).

## Segurança, dados e reversão

Nenhuma migração. Nenhum dado gravado muda. As frentes A e B mudam
validação de entrada e forma de consulta; reverter é reverter o commit.

## Equipe

| Papel | Modelo | Função |
| --- | --- | --- |
| `arquiteto-senior` | Opus | plano, distribuição, integração, registro |
| `auxiliar-pesquisa` ×2 | Sonnet | triagem e varredura (somente leitura) |
| `auxiliar-implementacao` ×4 | Haiku | frentes A a D, cada uma em cópia isolada (worktree), sem envio ao GitHub |
| `auditor-qa` | Sonnet | auditoria da versão integrada, sem escrita |

## Evidências

Ver a seção desta etapa no [estado](../agents/estado.md) e o relatório em
`docs/auditorias/`.
