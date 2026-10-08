# Reconferência da DL-076 — 08/10/2026

**Parecer: APROVADA COM RESSALVAS.** Nenhum bloqueador nem achado de gravidade média ou alta. Os achados A1 a A11 estão fechados por execução, e A12 está registrada em HI-90. Sobraram seis achados de gravidade baixa (R1 a R6, seção 5). Cinco são lacunas de teste ou de redação sem efeito no cálculo, e o sexto é documental. Nenhum impede o merge, mas devem entrar no backlog, e os testes propostos estão na seção 6. Auditoria de software não substitui a validação profissional do Fred. Não declaro ausência de defeitos nem conformidade legal.

## 1. Revisão e ambiente

- **Cópia:** `/home/user/wt-audit076b`, HEAD destacado em `6f2af8c91150d6cc0c501206986ca5690bb5a83b`. O SHA confere.
- **Ambiente:** Linux, Python 3.13.16, PostgreSQL 16, ruff 0.16.7, 4 núcleos.
- **Árvore:** `git status --short` e `git diff --stat` terminaram vazios. Nada foi escrito em `/home/user/DataLedger` nem em `/home/user/wt-dl077`. Não houve commit, push nem acesso ao GitHub.
- **Escopo do diff:** `c5cbc6a..a8c8def` (14 arquivos, +1.303/−81) e `a8c8def..6f2af8c` (só `estado.md`).
- **Mutantes e experimentos:** rodaram em cópias fora do repositório, em `.../scratchpad/b2/{base,clean,prop}`. Cada arquivo mutado foi restaurado ao fim. Um `pkill` mal escrito interrompeu um dos corredores no meio de um mutante. Comparei o que sobrou com o `wt` e restaurei o arquivo afetado na cópia `base`, nunca no `wt`.
- **Bancos:** usei `audit_dl076b` (mantido) e `audit_dl076bm`, `bx`, `bz`, `bc` mais seus `test_*`, que já descartei.
- **Fontes:** o pacote XSD é o de 08/10 (`nfse-esquemas_xsd-v1-01-20260209.zip`, sha256 `e7935cbd…8072`, o mesmo da rodada 1). Reconferi os três caminhos novos do A10 (seção 2).

## 2. Fechamento de A1 a A12

| Achado | Situação | Evidência executada |
| --- | --- | --- |
| **A1** (500 com percentual mal digitado) | **Fechado** | Testei 32 valores no cadastro e na edição (`5,00,0`, `1.23,4`, `2,,5`, `1,2,3`, `5.00,00`, `,,`, `5,,`, `,5,`, `1E+3`, `NaN`, algarismos árabes e largos, entre outros). Todos recusados com HTTP 200 e mensagem, sem 500. A alíquota gravada não mudou. `5,`, `5,00 ` e `5,0000` continuam aceitos. |
| **A2** (nota não escriturada some sem aviso) | **Fechado** | Serviço, API e tela trazem o aviso `notas_nao_escrituradas`, com contagem e número da nota. Cenário: 50,00 efetivada e 100,00 pendente dão total 50,00 mais o aviso. O aviso cobre rascunho e nota estornada. Não cobre nota cancelada antes de escriturar, nota de outra competência, outra empresa ou nota tomada. Só pendentes dá total 0,00 mais o aviso. A tela destaca o bloco, com link para `/fiscal/escrituracao/?empresa=…&ano=2026&mes=10`. Com apuração bloqueada o aviso não aparece, e nesse caso não há total. |
| **A3** (natureza "outro município" com cLocIncid do próprio município) | **Fechado** | Nota com `cLocIncid`=1721000 gera `natureza_incompativel_com_incidencia` na apuração e no relatório, na API e na tela. Local de outro município, local ausente e nota cancelada não geram aviso. |
| **A4** (isolamento sem teste) | **Fechado** | M24b, M51, M55, M87 e M88 estão mortos, cada um pelo teste T correspondente. Varredura própria de rotas: CLIENTE 403 em todas as rotas web e de API. PARALEGAL 200 na leitura e 403 na escrita. Gestor de B recebe 404 nas rotas de A e 404 nos PATCH, e o regime e a alíquota de A ficaram intactos. Anônimo recebe 302 na web e 403 na API. |
| **A5** (lacunas de teste) | **Fechado** | M42b, M62, M63, M64, M74, M77, M80, M82, M29, M40 e M66 a M69 estão mortos. Só o M90 segue vivo (seção 4). |
| **A6** (N+1 na apuração) | **Fechado** | Consultas por rota: serviço 207→**11**, tela 216→**16**, API 212→**16**. Com 1.000 notas, a tela levou 2,32 s e 1.016 consultas na rodada 1, e agora leva **0,51 s** e **16** consultas. As consultas não crescem entre 10, 200 e 1.000 notas. Os relatórios de retido e de outros municípios fazem 4 e 3 consultas com 200 notas. O total conferiu à mão com subitens 17.01 e 07.02 misturados. |
| **A6, regressão** (alíquota indexada) | **Fechado** | Sem uso de alíquota de outro escritório, vencida, futura, parcial no mês, de outro município ou de outro subitem. Com duas alíquotas do mesmo subitem em escritórios diferentes, vale a do próprio. Dez casos à mão passaram. O corte por município só foi coberto pelos meus testes: o mutante N15 sobreviveu à suíte, ver R1. |
| **A7** (vencimento sem dia da semana) | **Fechado** | A tela mostra "15/11/2026 (domingo)" e "10/11/2026" sem sufixo, em apuração e retido, além do rótulo "Vencimento nominal". A API segue em ISO. A função devolve "(sábado)" e "(domingo)" corretamente. A cobertura do `<dd>` ficou fraca (R3). |
| **A8** (textos contraditórios) | **Parcial** | A ajuda e o exemplo agora dizem `07.02`, e o aviso de percentual ambíguo não fala mais em "reais". Restam dois textos com "7.02", o que é só de redação (R4). |
| **A9** (CHECK de piso e datas de vigência) | **Fechado** | A migração 0007 gera `CHECK (percentual >= 2 OR subitem IN ('07.02','07.05','16.01'))`. Por ORM `create`, `update()`, `bulk_create` e SQL cru, 1,9999 em 17.01 é recusado, 2,0000 é aceito, e 1,5/0,0001 em 07.02, 07.05 e 16.01 é aceito. Trocar o subitem de exceção para 17.01 com 1,5 é recusado. A vigência fora de 2000–2100 volta 400 na API e na tela. Os limites 2000-01-01 e 2100-12-31 são aceitos. |
| **A10** (fórmula do vBC) | **Fechado** | Caminhos resolvidos por script no XSD oficial: `vCalcBM`, `vRedBCBM` e `vCalcReeRepRes` existem na 1.01. Na 1.00 só `vCalcReeRepRes` não existe, como o código declara. Linhas conferidas: :239, :338, :1948, :230 e :1562. Nota com benefício municipal coerente, em `vCalcBM` ou em `vRedBCBM`, não gera aviso. Nota com benefício incoerente avisa com o valor recomposto. Dois efeitos sem aviso: `vDescIncond` ausente conta como zero só no aviso, e o total e a conferência não mudam. |
| **A11** (ruído de campos ausentes) | **Fechado** | Opcional ausente não alerta. `vISSQN` ausente alerta. Opcional presente e ilegível alerta, mas só o meu teste R9 prova isso (R2). |
| **A12** (documental) | **Fechado** | HI-90 tem os quatro itens: vigência de 2019, mapeamento XII→7.16 e inciso I fora da tabela, art. 8º-B de 2029 a 2032 não tratado, e vencimento nominal com dia da semana. Falta atualizar o plano (R6). |

## 3. Regressões, migração 0007 e verificações com números

### Regressões

- **Total = soma do `vISSQN`:** o cenário de outubro dá **237,70** (previsto à mão: 50 + 6 + 16,67 + 40 + 50,01 + 50,02 + 25). Pendências: 1004 e 1006. Aviso presente: `incidencia_em_outro_municipio`.
- **Tolerância 0,01:** 1000,22/50,00 é pendência, 1000,20/50,00 é conferida, 999,78/50,00 é pendência, 999,80/50,00 é conferida. Resultado como na rodada 1.
- **Vencimentos:** 10/2026 dá 10/11/2026 e 15/11/2026. 12/2026 dá 10/01/2027 e 15/01/2027.
- **Isolamento e permissões:** ver A4.

### Migração 0007

- **Dependência:** só `("fiscal", "0006_dl076_iss_municipal")`.
- **SQL (`sqlmigrate`):** `ALTER TABLE … ADD CONSTRAINT aliquota_iss_piso_2_salvo_excecao CHECK …`. É aditiva.
- **Reversão e reaplicação:** reverti 0007 e 0006 (até `fiscal 0005`, a tabela some) e reapliquei. A linha de Palmas voltou.
- **Dados existentes com percentual < 2% fora da exceção:** inseri 17.01 a 1,5% e 07.02 a 1,5% em `fiscal 0006`. Ao aplicar a 0007, a migração falha com `check constraint "aliquota_iss_piso_2_salvo_excecao" … is violated by some row` e fica **sem aplicar**, sem efeito parcial. Depois de corrigir o dado, aplica. A mensagem não lista as linhas ofensoras. Como a 0006 não está em `origin/main`, não há dado de produção afetado. O comentário da 0007 declara esse comportamento como desejado.
- **0006:** só comentário mudou, com a referência a HI-90.

### Verificações

| Verificação | Resultado |
| --- | --- |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 439 arquivos já formatados |
| `manage.py check` | 0 problemas |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate` em banco vazio | **84 aplicadas, 0 pendentes** |
| Reverter e reaplicar `fiscal 0007` e `0006` | OK |
| `pytest` completo, invocação única | **6.343 aprovados, 1 reprovado, 53 pulados**, 568,82 s |
| Único reprovado | `test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior` (ambiente, Python 3.13 sem a sintaxe do 3.14) |
| Subconjunto `test_dl076_*` | 300 passaram |
| `scripts/validate-docs.ps1` | **Não testado**: não há `pwsh`. Substituí por script em Python em `estado.md`, `requisitos.md`, o plano e a rodada 1: UTF-8, título, nova linha final, espaço no fim e links. Tudo ok. |

Os números batem com `docs/agents/estado.md` (6.343 / 1 / 53).

## 4. Mutantes

Resultado: **107 mutantes**, **92 mortos** e **15 vivos**. Dos vivos, 3 são equivalentes ou inalcançáveis.

### Rodada 1 reaplicada (53 mutantes)

52 mortos. O único vivo é o M90.

- **Os 19 vivos de lacuna real da rodada 1 agora mortos:** M24 (reescrito como M24b), M42 (reescrito como M42b), M51, M55, M62, M63, M64, M74, M77, M80, M82, M87, M88, M29, M40 e M66 a M69.
- **M90 segue vivo.** `tribISSQN` ausente não é nomeado. Era baixa na rodada 1 e continua baixa (R2).
- **Regressão (33 mortos):** M01, M03, M05, M06, M08, M10, M11, M12, M14, M19, M20, M22, M23, M26, M27, M28, M36, M37, M38, M41, M44, M49, M50, M52, M53, M56, M57, M71, M72, M79, M83, M84 e M86.

### Novos, na lógica corrigida (54 mutantes)

40 mortos e 14 vivos.

| Área | Mortos | Vivos |
| --- | --- | --- |
| A2 (aviso removido, invertido, contagem errada, lista de números vazia, só uma das duas situações, tela duplicada) | N01, N02, N04, N05, N06, N07, N08 | N03 (rascunho não conta), N09 (link sem competência) |
| A3 (aviso removido da apuração e do relatório, invertido) | N10, N11, N12 | N13 (avisa mesmo cancelada) |
| A6 (índice sem município, sem vigência, subitem vizinho, parcial) | N16, N17, N18, N19, N20 | N15 (sem filtro de município), N21 (tomador vazio) |
| A7 (sábado removido, dia deslocado, relatório) | N23, N24, N27 | N25 (retido na tela), N26 (próprio na tela), N28 (memória) |
| A9 (limites de vigência, fim não validado, CHECK da 0007 em 5 variantes) | N29, N30, N31, N32, N50, N51, N52, N53 | N54 |
| A10 (reembolso, benefício, ausência como zero, caminhos, preferência) | N33, N34, N35, N36, N37, N38, N39, N41 | N40 (vCalcDR sobre vDR), N42 (caminho do reembolso) |
| A11 (filtro de opcionais, vISSQN como opcional) | N43, N44, N46 | N45 (ilegível não alerta) |
| A1 e A8 | N47, N48, N49 | — |

N01 a N54 são ids internos meus. As migrações foram testadas com banco recriado a cada mutante.

**Três vivos são equivalentes ou inalcançáveis:**
- **N14:** `None != município` devolve o mesmo resultado.
- **N22:** a ordem da lista não muda o resultado.
- **N54:** a tradução do CHECK só dispara depois que o serviço já recusou, o que dá defesa em profundidade.

**Os outros onze são lacunas de teste (R1 a R5, seção 5).** Os testes propostos matam todos eles: N03, N09, N13, N15, N21, N25, N26, N28, N40, N42, N45 e o M90 (confirmei um a um).

## 5. Achados novos (todos de gravidade baixa)

### R1 — Sem teste do corte por município no índice de alíquotas

- **Requisito:** isolamento e vigência na mudança de A6.
- **Local:** `apps/fiscal/iss_municipal.py`, `_aliquotas_do_municipio`, filtro `municipio_ibge=municipio`, por volta da linha 483.
- **Evidência:** N15 remove esse filtro e a suíte inteira `test_dl076_*` passa.
- **Impacto:** o código atual está correto, como mostram meus testes R2 e R2b. Uma regressão futura faria o ISS de Palmas usar alíquota cadastrada para outro município. Com as duas cadastradas, apareceria falso "sobreposição".
- **Correção:** adicionar R2 e R2b.
- **Verificar:** os dois testes falham em N15 e passam no código atual (confirmado).

### R2 — Lacunas de cobertura nos avisos novos

- **Requisito:** A2, A3, A10 e A11.
- **Local:** testes `test_dl076_correcao_auditoria.py`.
- **Evidência:**
  - **N03:** nota em rascunho não tem teste de aviso.
  - **N13:** o aviso A3 não é testado com a nota cancelada na apuração.
  - **N42:** o `vCalcReeRepRes` só é testado em `CamposIss` montado à mão, nunca lido do XML.
  - **N45:** a ilegibilidade de campo opcional nunca é testada.
  - **N40:** nenhum teste com `vDR` e `vCalcDR` diferentes.
  - **N09:** o link da escrituração só é verificado até o `?`.
  - **N21:** o tomador na tela da apuração não é verificado.
  - **M90:** `tribISSQN` ausente não é nomeado.
- **Impacto:** nenhum efeito hoje; o risco é regredir sem a suíte perceber.
- **Correção:** testes R1, R3, R4, R5, R6, R8, R9, R10 e R11 (seção 6).
- **Verificar:** cada um falha no mutante correspondente e passa no código atual (confirmado).

### R3 — Teste do vencimento na tela não olha o campo certo

- **Requisito:** A7 (dia da semana no vencimento).
- **Local:** `test_dl076_correcao_auditoria.py::test_A7_vencimento_de_fim_de_semana_sai_com_o_dia_sem_afirmar_outra_data`.
- **Evidência:** o teste procura `"15/11/2026 (domingo)" in html`, e a memória de cálculo já repete essa string. N25 (retido sem dia da semana no campo) e N26 (próprio sem dia da semana) sobrevivem. Em outubro/2026 o próprio cai numa terça, então a lacuna do próprio nunca se mostra.
- **Impacto:** o campo "Vencimento nominal do ISS retido" poderia perder o "(domingo)" sem o teste notar. Uma competência cujo próprio caia em fim de semana (por exemplo 12/2026, 10/01/2027 é domingo) não tem teste.
- **Correção:** R7, que exige `<dd>15/11/2026 (domingo)</dd>` em 10/2026 e `<dd>10/01/2027 (domingo)</dd>` em 12/2026.
- **Verificar:** R7 mata N25, N26 e N28 (confirmado).

### R4 — Dois textos ainda dizem "7.02"

- **Requisito:** A8.
- **Local:** `apps/fiscal/iss_municipal.py:94` (`DISP_FAIXA`) e `:1159` ("A exceção vale só para os subitens 7.02, 7.05 e 16.01").
- **Evidência:** o formato aceito é `07.02`, e os outros textos já foram corrigidos.
- **Impacto:** só de redação. Quem digitar `7.02` pela mensagem de exceção seria recusado no formato.
- **Correção:** trocar por `07.02`, `07.05` e `16.01`.
- **Verificar:** teste de mensagem do piso.

### R5 — Fórmula do `vBC`: ambiguidade e mensagem incompleta

- **Requisito:** A10, aviso de base.
- **Local:** `apps/fiscal/iss_nota.py`, `divergencia_de_base`.
- **Evidência:**
  - O XSD (linha 250) escreve `(vDR ou vCalcDR + vCalcReeRepRes)`, que lê como `vDR` ou `vCalcDR + vCalcReeRepRes`. O código subtrai `vDR` e o reembolso quando os dois existem. Com vServ 1000, vDR 100, reembolso 50 e vBC 900, o aviso diz 850.
  - A mensagem cita "vServ − vDescIncond − deduções" e omite o benefício e o reembolso.
- **Impacto:** só aviso; o total e a conferência não mudam. Pode dar falso positivo ou texto confuso para o contador.
- **Correção:** decidir com o contador qual leitura vale e ajustar a mensagem, ou documentar a ambiguidade.
- **Verificar:** teste com `vDR` e reembolso juntos.

### R6 — Plano e requisitos sem as decisões da correção

- **Requisito:** documentação coerente.
- **Local:** `docs/planos/DL-076-iss-por-municipio-palmas.md` (escopo 5, "Decisões tomadas", critério 10) e `docs/projeto/requisitos.md`.
- **Evidência:**
  - O plano não menciona o aviso de HI-89 nem a migração 0007.
  - Diz "Campo ausente… nunca vira zero", mas a decisão do A10 faz o opcional ausente valer zero no aviso de base.
  - Diz que a base avisa quando `vServ − desconto − dedução` difere de `vBC`, e a fórmula agora tem benefício e reembolso.
  - HI-82 diz "Fora de 2% a 5% é aviso forte", mas o código **recusa** (um texto pré-existente, que não nasceu na correção).
- **Impacto:** quem ler só o plano se engana sobre o que o produto faz.
- **Correção:** acrescentar as quatro decisões ao plano e alinhar a HI-82.
- **Verificar:** leitura cruzada do plano com o código e `estado.md`.

### Observações sem achado

- O texto do aviso A2 cita "auditoria DL-076, A2" no campo "Dispositivo". É referência interna, coerente com as outras (HI-82, DL-072).
- Com muitas pendentes, o aviso lista todos os números numa só mensagem.
- Concorrência em regime e em regra do município continua não exercitada (só a de alíquota foi, na rodada 1).

## 6. Testes propostos (entregues como texto)

O arquivo completo, com 12 casos que passam no código atual, está em `.../scratchpad/b2/prop/apps/fiscal/tests/test_dl076_reconferencia_prop.py`. Os mais relevantes:

```python
def test_R2_aliquota_de_outro_municipio_nao_vale_em_palmas(escritorio_a, usuario_gestor_a, empresa_a):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000", municipio=OUTRO_MUNICIPIO)
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 1, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00")
    with pytest.raises(iss.IssRecusado) as e:
        iss.apuracao_iss_proprio(empresa_a, 2026, 10, hoje=date(2026, 10, 20))
    assert {b.codigo for b in e.value.bloqueios} == {"subitem_sem_aliquota_vigente"}

def test_R2b_duas_cidades_com_o_mesmo_subitem_usam_a_de_palmas(...):
    # 17.01 a 3% em OUTRO_MUNICIPIO e a 5% em PALMAS; a nota usa 5% e fica conferida

def test_R1_nota_em_rascunho_tambem_conta_como_nao_escriturada(...):
    # esc.salvar_rascunho(vinculo, DEVIDO, usuario); total 50,00; aviso com "1 nota(s)" e o número 2

def test_R3_nota_outro_municipio_cancelada_nao_gera_aviso_de_natureza(...):
    # OUTRO + cLocIncid=Palmas, cancelada pelo evento e101101: sem aviso na apuração

def test_R7_vencimentos_da_tela_levam_o_dia_da_semana_no_proprio_campo(...):
    # 10/2026: "<dd>15/11/2026 (domingo)</dd>" e "<dd>10/11/2026</dd>"
    # 12/2026: "<dd>10/01/2027 (domingo)</dd>" e "<dd>15/01/2027</dd>"
```

Também há R4 (sem aviso A3 sem `cLocIncid`), R5 (tomador na tela), R6 (`tribISSQN` ausente nomeado), R8 (reembolso lido do XML), R9 (campo presente e ilegível alerta), R10 (link da escrituração com empresa e competência) e R11 (`vDR` prevalece sobre `vCalcDR`).

## 7. Implementado, inspecionado, testado, não testado

- **Implementado (pelo desenvolvedor):** a correção `a8c8def`, conforme o relato dele. Eu não implementei nada.
- **Inspecionado:** o diff `c5cbc6a..HEAD`, as migrações 0006 (comentário) e 0007, as funções novas de `iss_municipal.py` e `iss_nota.py`, as mudanças em `views_web.py` e nos templates, o arquivo de testes novo, `estado.md`, `requisitos.md` (HI-82 a HI-90) e o plano.
- **Testado (executado):**
  - A1 a A11 por caso;
  - A6 com 10, 200 e 1.000 notas;
  - os dez casos de índice de alíquotas;
  - o CHECK por ORM, SQL cru, `update()` e `bulk_create`;
  - a migração 0007 com e sem dado ofensor, a reversão e a reaplicação;
  - o isolamento e as permissões em 10 rotas web e 6 de API;
  - a suíte completa;
  - 107 mutantes;
  - os testes propostos contra os mutantes vivos.
- **Não testado:**
  - `scripts/validate-docs.ps1` (sem `pwsh`; substituí, ver seção 3);
  - aparência e acessibilidade no navegador real;
  - XML real de Palmas;
  - concorrência em regime e em regra do município;
  - carga acima de 1.000 notas;
  - multa e juros (fora do escopo);
  - a correção das exceções do art. 3º pelo contador (continua com o Fred).
- **Fora do escopo:** guia, transmissão, ISS fixo em reais e os outros 51 municípios.

## 8. Parecer

**APROVADA COM RESSALVAS.** A1 a A11 e A12 estão fechadas por execução. A suíte completa tem o único reprovado conhecido de ambiente, e os 19 mutantes da rodada 1 morreram, exceto o M90. A migração 0007 é aditiva, reversível e depende só de `fiscal 0006`. A mudança de A6 não usa alíquota de outro escritório, de outro município, vencida, futura nem parcial no mês, o que confirmei por execução.

**Ressalvas** (todas de gravidade baixa, para o backlog): R1 a R6. Nenhuma altera valor de ISS, isolamento ou permissão.

Arquivos de referência:
- `/home/user/wt-audit076b/apps/fiscal/iss_municipal.py`
- `/home/user/wt-audit076b/apps/fiscal/iss_nota.py`
- `/home/user/wt-audit076b/apps/fiscal/views_web.py`
- `/home/user/wt-audit076b/apps/fiscal/migrations/0007_dl076_piso_aliquota_iss.py`
- `/home/user/wt-audit076b/apps/fiscal/tests/test_dl076_correcao_auditoria.py`
- `/home/user/wt-audit076b/docs/planos/DL-076-iss-por-municipio-palmas.md`
- `/home/user/wt-audit076b/docs/projeto/requisitos.md`
- Testes propostos: `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/b2/prop/apps/fiscal/tests/test_dl076_reconferencia_prop.py`
- Corredor de mutação: `/tmp/claude-0/-home-user-DataLedger/8408632f-332c-5008-8b6a-20ea297e22a1/scratchpad/b2/mutar_r2.py`
