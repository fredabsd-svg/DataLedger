# Auditoria da DL-070, reconferência (rodada final)

## 1. Identificação

| Item | Valor |
| --- | --- |
| Revisão auditada | `25fe182fae27f1dc43ca89a0b7f7377034104358`, branch `ccr-bf4b4a55-hpqgbp` |
| Revisão da rodada 1 | `e6d3bef`. Commits desde então: `953bfac`, `73afde1`, `8f976ca`, `25fe182`. |
| Árvore no início | SHA igual ao pedido. `git status --porcelain` vazio. Uma única worktree. |
| Árvore no fim | SHA `25fe182…` (igual). `git status --porcelain` e `git diff --stat` vazios. Só a worktree principal. Worktrees e bancos descartáveis removidos. |
| Ambiente | Python 3.13 (a CI usa 3.14). PostgreSQL 16 local. |
| Como executei | Duas worktrees descartáveis em `25fe182`, cada uma com banco próprio: uma para a suíte completa, outra para mutações e sondas. As duas foram removidas. |
| Auditor | `auditor-qa`. Não corrigi nada e não deleguei. |

## 2. Parecer: **APROVADO COM RESSALVAS**

Os achados A1, A2, A3, A5, A6 e A7 estão fechados, cada um por execução minha. O A4 e a observação 3 estão abertos por decisão do arquiteto, registrados com honestidade no backlog como BL-652 e BL-653. A correção não introduziu defeito novo que eu tenha encontrado. Não há achado bloqueador nem de alta gravidade.

As ressalvas que seguem valendo:

- **A4 (BL-652):** risco aceito e aberto.
- **BL-653:** aberto, preexistente e só inspecionado.
- **R1 e R3 desta rodada:** ambos baixos e de documentação ou informativos.
- **Itens não verificados:** a seção 6 lista o que ficou de fora.

Isto não declara ausência de bugs nem conformidade legal. A etapa não toca regra contábil.

## 3. Achados da rodada 1 × situação

| Achado | Situação | Evidência executada |
| --- | --- | --- |
| **A1** (relançar `IntegrityError` alheia) | **Fechado** | Mutante M-A: removi o `if not Escritorio.objects.filter(cnpj=…).exists(): raise`. Na rodada 1, 58 testes passavam. Agora `test_integrityerror_sem_cnpj_duplicado_propaga_e_nao_vira_mensagem` reprova (1 failed, 26 passed). Segundo mutante, `raise` incondicional: reprova `test_corrida_de_cnpj_duplicado_responde_com_mensagem_sem_500_e_sem_gravar`. O teste novo também confere que nada fica gravado. |
| **A2** (comentário do BL-575) | **Fechado no código** | O comentário em `apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py` (linhas 1020-1022) agora diz que a tela existe. Conferi os dois nomes citados: a rota `livro_caixa_web:mes_encerrar` está em `apps/livro_caixa/urls_web.py` (linha 117), e `test_tela_livro_caixa_mes_encerrar_e_acessivel` está na linha 1543 do mesmo arquivo, abaixo do comentário. O backlog ainda mostra BL-575 como aberto (R1). |
| **A3** (tela × servidor) | **Fechado** | Renderizei o HTML: `<input … id="id_cnpj" … required maxlength="18" aria-describedby="id_cnpj_ajuda">`, sem `pattern` e sem `inputmode`. O rótulo é `CNPJ`, e há `<p class="texto-apoio" id="id_cnpj_ajuda">Com ou sem pontuação.</p>`. A classe existe em `static/css/base.css`, linha 2390. O comentário Django `{# … #}` não vaza para o HTML. POST com `AB.123.CDE/0001-55` deu 302 e gravou `AB123CDE000155`. Não testei em navegador real (seção 6). |
| **A4** (enumeração de CNPJ) | **Aceito, aberto (BL-652)** | Não houve mudança de código. O BL-652 descreve o risco como "aceito por ora pelo arquiteto (08/10/2026), reversível". Traz o critério de correção (limite do cadastro, com teste de N tentativas) e cita que antes o caso dava 500. Fiel ao que escrevi. |
| **A5** (limites duplicados) | **Fechado** | `LIMITE_NOME_ESCRITORIO` e `LIMITE_EMAIL` agora saem de `_meta.get_field(...).max_length`. Alterei o `max_length` de `Escritorio.nome` para 150 numa cópia: a constante passou a 150, o formulário recusou 151 com "no máximo 150 caracteres" e aceitou 150. Com o e-mail em 100, `LIMITE_EMAIL` foi a 100. O `LIMITE_CNPJ_COM_MASCARA = 18` é declarado não derivado, de propósito (tamanho da máscara, não da coluna). A justificativa confere com `models.py` (CNPJ com `max_length=14`). A docstring do serviço agora diz a verdade: o serviço confia no chamador, e a validação de entrada mora no formulário. Só há um "NA ORIGEM" no repositório, e não é mais enganoso. |
| **A6** (lacunas de teste) | **Fechado** | Ver a tabela de mutantes abaixo. Os quatro casos propostos existem. |
| **A6(c)** (premissa contestada) | **O desenvolvedor tem razão; eu errei** | `validate_email("a"*288 + "@dl070.local")` aceita o e-mail de 300 caracteres. O formulário o recusa só pelo tamanho, com `['E-mail do convidado pode ter no máximo 254 caracteres.']`. Cabe a correção de registro: o e-mail de 300 caracteres não é malformado, e a premissa "deveria afirmar 'inválido'" estava errada. A afirmação de que o trecho `"E-mail do convidado"` casava com qualquer mensagem continua verdadeira. A asserção nova, da mensagem de limite, é a correta. Um mutante que troca a mensagem de limite por "inválido" reprova o caso `300_caracteres` e o `260_caracteres_bem_formado`. |
| **A7** (classificação de risco) | **Fechado** | Nota no plano, em `docs/planos/DL-070-melhorias-com-equipe-multiagente.md` (linhas 20-25). Reconhece que BL-651 e BL-649 tocam o nível 1 do §3.1 e que o controle foi a auditoria independente. Honesta e sem exagero. |
| **Observação 3** | **Aberto (BL-653)** | Registrado no backlog como preexistente e só inspecionado. |

### Mutantes do A6 (arquivo `apps/tenancy/tests/test_dl070_entradas_do_acesso.py`)

| Mutante | Resultado |
| --- | --- |
| (a1) Remover o filtro `vinculos__usuario` | **Morto.** Reprovam o teste do usuário sem vínculo e `test_admin_de_outro_escritorio_responde_igual_a_id_inexistente`. |
| (a2) Quem é administrador em algum escritório enxerga qualquer escritório | **Morto** só pelo teste novo `test_admin_de_outro_escritorio_responde_igual_a_id_inexistente`. Com o arquivo antigo (`e6d3bef`), o mesmo mutante passou nos 21 testes. O caso novo, portanto, fecha uma lacuna real. |
| (b) O filtro da view passa a exigir `vinculos__ativo=True` | **Morto** por `test_vinculo_inativo_recebe_recusa_do_servico_e_nao_cria_convite`. |
| (d2) `.lower()` no e-mail | **Morto** por `test_convite_preserva_maiusculas_e_remove_espacos_das_pontas`. |
| (d3) E-mail cru do POST, sem passar pelo formulário | **Morto** pelo mesmo teste. |
| (d1) `EmailField(strip=False)` | **Não aplicável.** O Django levanta `TypeError`, pois o `EmailField` não aceita o argumento. O strip é padrão, e o mutante d3 cobre o caso. |
| (c) Mensagem de limite trocada por "inválido" | **Morto** (caso `300_caracteres` e `260_caracteres_bem_formado`). |

## 4. Verificações gerais (executadas)

| Verificação | Resultado |
| --- | --- |
| `pytest` completo | **5.021 aprovados, 1 reprovado, 53 pulados**, em 353,6 s. A rodada 1 deu 5.015/1/53, então a diferença é **+6**, como esperado. |
| Reprovação única | `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`. É de ambiente (Python 3.13). Nenhuma reprovação nova. |
| `pytest apps/tenancy/tests/test_dl070_entradas_do_acesso.py` | 27 aprovados (eram 21). |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 380 files already formatted |
| `manage.py check` | no issues |
| `makemigrations --check --dry-run` | No changes detected |
| Efeitos colaterais | `git status` e `git diff --stat` vazios nas duas worktrees depois da suíte, e no repositório principal no fim. |

## 5. Conferência de documentação e do comentário do arquiteto

- **Comentário de `apps/tenancy/views.py` (~linha 921):** diz a verdade. Li o código:
  - **Formulários:** a view valida a entrada externa com `PrimeiroEscritorioForm` (linhas 964-974) e `ConviteEmailForm`.
  - **Busca restrita:** a busca de escritório é restrita por `vinculos__usuario=request.user`.
  - **Regras no serviço:** um escritório por usuário sem vínculo, quem pode convidar e validade do convite estão em `primeiro_acesso.py`.
- **`backlog.md`:**
  - BL-591, 600, 602 e 619 constam **fechados**, cada um com a nota "auditoria rodada 1 conferiu". Isso é verdade, e o BL-619 diz corretamente "o defeito já não existia".
  - BL-575 segue **aberto** (ver R1).
  - BL-652 e BL-653 existem e conferem com meus achados.
  - BL-645 a 649 e BL-651 seguem "em desenvolvimento — DL-070", coerente com a etapa ainda não integrada.
- **`DL-070-…md`:** a nota A7 está lá. O plano não registra A1 a A6, o que não é exigido.
- **Arquivos `.md` alterados** (backlog, plano, relatório da rodada 1): título, UTF-8, espaço no fim de linha, nova linha final e links relativos conferidos por script meu. Todos ok.
- **Relatório da rodada 1:** não foi editado. Está no repositório com a premissa do A6(c) que agora sei ser equivocada. A correção está nesta seção 3.

## 6. Achados novos

### R1. BL-575 continua "aberta" no backlog, embora as duas metades estejam corrigidas (BAIXA, documentação)

- **Requisito afetado:** CLAUDE.md, "Estado do projeto: um lugar só" (backlog que não contradiz o código).
- **Local:** `docs/projeto/backlog.md`, linha 1970.
- **Reprodução:** `grep -n "BL-575" docs/projeto/backlog.md`. A linha diz `aberta | Referências corrigidas`. O BL-575 tinha duas partes: o `models.py` ("decisão 7"), feito antes, e o comentário do teste de atalhos, corrigido em `8f976ca`. Conferi a segunda (A2 na seção 3).
- **Impacto:** nenhum defeito de código. O backlog fica conservador e defasado, e o arquiteto decidiu isso de propósito até a reconferência. É a pendência óbvia a fechar na integração.
- **Correção recomendada:** ao integrar, marcar o BL-575 como fechado, citando DL-070 e esta reconferência.
- **Verificar:** leitura da linha do BL-575.

### R2. `estado.md` ainda não registra a auditoria da DL-070 (BAIXA, informativa)

- **Requisito afetado:** CLAUDE.md, regra 1 ("ao concluir qualquer etapa, atualize `estado.md`").
- **Local:** `docs/agents/estado.md`, seção "Próximo passo" (linhas 149-166).
- **Evidência:** o arquivo diz "em desenvolvimento" e mantém a linha de base 4.987. Não cita a rodada 1 (APROVADO COM RESSALVAS), a correção única nem esta reconferência. `README.md` também não cita. A etapa não está concluída, então não é violação agora. É lembrete para a integração.
- **Impacto:** nenhum hoje. Depois da integração, a falta divergiria da regra de fonte única.
- **Correção recomendada:** ao integrar, atualizar o `estado.md` com os pareceres, a nova linha de base (**5.021 aprovados, 1 reprovado de ambiente, 53 pulados**, 380 arquivos) e o BL-652/653 como pendências. O teste `test_documentacao_do_estado.py` cobre a existência do plano, não esse conteúdo.
- **Verificar:** leitura do `estado.md` depois da integração. Não rodei `test_documentacao_do_estado.py` isoladamente, mas ele está na suíte, que passou.

### R3. `validate_email` aceita parte local acima de 64 caracteres (BAIXA, informativa, comportamento do Django)

- **Requisito afetado:** BL-647 (e-mail válido).
- **Local:** `apps/tenancy/forms.py`, `ConviteEmailForm.email`.
- **Reprodução:** `validate_email("a"*288 + "@dl070.local")` retorna sem erro. O formulário só recusa pelo tamanho total. Um e-mail de 200 caracteres com parte local de 190 passaria e seria gravado como convite, embora o RFC 5321 limite a parte local a 64.
- **Impacto:** nenhum quebra. O convite iria para um endereço que nenhum servidor aceita, e nada é enviado nesta etapa. Esclareço que isso não era critério do plano.
- **Correção recomendada:** nenhuma obrigatória. Se o Fred quiser rigor de RFC, acrescentar um validador do tamanho da parte local, com teste.
- **Verificar:** teste com parte local de 65 caracteres e total abaixo de 254.

## 7. O que NÃO foi verificado, e por quê

| Item | Situação | Motivo |
| --- | --- | --- |
| `pwsh ./scripts/validate-docs.ps1` | **Não testado** | `pwsh` não existe neste ambiente. Fiz a conferência manual equivalente nos três `.md` alterados. |
| Python 3.14 (CI) | **Não testado** | Ambiente local é 3.13. A reprovação preexistente é desse descompasso. |
| A3 em navegador real | **Não testado** | Conferi o HTML renderizado e o POST. Que o navegador deixe digitar `AB.123.CDE/0001-55` com `maxlength=18` e sem `pattern` decorre da especificação HTML, mas eu não abri a tela. |
| Contraste e aparência do `texto-apoio` na tela de primeiro acesso | **Não testado** | Só verifiquei que a classe existe e que `aria-describedby` aponta para o id certo. |
| Enumeração de CNPJ (A4) e corrida do mesmo usuário (BL-653) | **Não testados** | Aceitos e abertos por decisão do arquiteto. O BL-653 já estava só inspecionado na rodada 1. |
| Workflows e proteção de branch no GitHub | **Não testado** | Fora do escopo. |
| Regras contábeis e legais | **Fora do escopo** | A etapa não toca cálculo, saldo nem lançamento. Auditoria de software não substitui validação profissional. |

Itens da rodada 1 que a correção não tocou, como as frentes B, C e D, ficam como estavam: a suíte completa verde e as verificações estáticas não regrediram, mas não repeti as mutações da rodada 1.

## 8. Arquivos relevantes (relativos ao repositório)

- `apps/tenancy/views.py`, linhas 918-930 (comentário), 959-1010 (bootstrap) e 1019-1040 (emissão de convite)
- `apps/tenancy/forms.py`
- `apps/tenancy/services/primeiro_acesso.py`
- `templates/tenancy/primeiro_acesso.html`
- `apps/tenancy/tests/test_dl070_entradas_do_acesso.py`
- `apps/contabilidade/tests/test_dl024_atalhos_e_acessibilidade.py`, linhas 1018-1024
- `docs/projeto/backlog.md`, linhas 1970 (BL-575) e 2204-2208 (BL-652 e BL-653)
- `docs/planos/DL-070-melhorias-com-equipe-multiagente.md`, linhas 20-25
- `docs/agents/estado.md`, linhas 149-166

Esta é a última rodada permitida pelo §3.1: auditoria, uma correção, uma reconferência. Não há terceira.

---

Registrado pelo `arquiteto-senior` em 08/10/2026, sem edição dos achados.
