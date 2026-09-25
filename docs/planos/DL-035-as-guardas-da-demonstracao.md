# DL-035 — As guardas da demonstração

**Estado em 2026-09-25:** auditoria independente aprovada após uma correção e
uma reconferência, na branch `feat/dl-035-guardas-demonstracao`, baseada na
`main` `22a0241`. A implementação está no commit local
`38e7a6b2e0dfa4c6dff558d0b48b034c72b0ff43`; a correção documental da primeira
auditoria foi registrada no commit `75a3530b529cd737e884f3442bcdf0ea00198f45`,
cuja árvore foi reconferida limpa. A auditoria inicial reprovou só a declaração
desatualizada de que não havia commit; a reconferência aprovou a correção e
confirmou que os critérios de código BL-514 a BL-519 estavam atendidos. Os dois
pareceres integrais estão em
[`2026-09-25-dl-035-rodada-1.md`](../auditorias/2026-09-25-dl-035-rodada-1.md).
Push, PR e CI continuam pendentes; não declarar integração antes dos quatro
workflows passarem.

**Origem:** as cinco ressalvas da
[reconferência da DL-034](../auditorias/2026-09-21-dl-034-rodada-2.md), que
**aprovou com ressalvas**. Pela §3.1 não havia terceira rodada; as ressalvas
saem daqui, numa etapa própria, **não numa terceira volta disfarçada**.

**Decisão de abrir esta etapa:** minha, em 2026-09-21, e informada ao Fred.

## ⚠️ O que esta etapa é, em uma frase

**Nenhum destes itens é defeito no que o produto entrega hoje.** Todos são
**buracos na GUARDA** — o que passaria despercebido numa mudança futura. O
auditor foi explícito: *"nenhum documento errado sai desta revisão"*.

⚠️ **E é exatamente por isso que ela não pode ser adiada.** Este projeto já
pagou caro, mais de uma vez, pela distância entre **medido** e **guardado**:
medição que só uma pessoa consegue repetir não é medição do projeto (BL-337), e
o bloco de identificação já foi apagado do papel com a suíte verde antes
(PE-61/BL-372). **A DL-034 fechou com essa distância aberta em dois pontos.**

## Nível de risco: 2 — é guarda, não é regra nova

Não há regra contábil nova, nem cálculo novo, nem tela nova. O que muda é **o
que o projeto consegue provar**. Verificação: **auditoria independente da versão
integrada**, com medição **no navegador real** para o BL-514. Regra de parada da
§3.1: uma auditoria, uma correção, uma reconferência — **sem terceira**.

## Escopo — cinco itens, dois de gravidade média

### 1. BL-514 (média) — o bloco normativo tem de ser medido por CONTRASTE, não só por presença

Seis sabotagens reprovam hoje. **Duas passam**: `color: transparent` e
`color: #FFFFFF`. Medido no pixel: na folha 4, o cinza mínimo dentro da caixa da
palavra "CNPJ" vai de **0** (tinta preta) para **255** — zero pixel de tinta —, e
a suíte inteira fica verde.

⚠️ **O oráculo que fecha isto JÁ EXISTE no mesmo arquivo**, escrito e testado,
para o timbre do escritório: `_localizar_linhas_do_timbre_no_documento`, com bbox
por linha e análise de contraste, criado no BL-372/J1 **depois de um ataque
idêntico**. **Não falta capacidade; falta reuso.** Esta é a razão de o item ser
média e não baixa: a correção é barata e a omissão é conhecida.

### 2. BL-515 (média) — uma prova de comportamento por trava, derivada da tupla

Mover, uma por vez, cada uma das seis listas que vetam para a tupla de aviso:
**cinco passam com 1657 testes verdes**, e para a classificação aninhada — a
única que produz **resíduo zero** — **o Balanço passa a emitir** com pendência
declarada. E **dois docstrings prometem o contrário**.

É a [DE-071](../projeto/decisoes.md#de-071) sendo paga onde ela nasceu.

### 3. BL-516 (baixa) — a detecção que estreitou, e a frase que a causou

Duas raízes do mesmo tipo com natureza divergente deixaram de ser nomeadas.
⚠️ **DECIDIDO: opção (i)** — remover a exclusão de raiz, manter a chave
`(conta_pai, tipo)` e **reescrever o rótulo**. O auditor mediu que o `tipo` na
chave, **sozinho**, já fecha o A1. O implementador ajustou o **dado** para a
**frase** continuar verdadeira; o certo é o contrário.

### 4. BL-517 (baixa) + BL-519 — a nota sai de DENTRO do bloco normativo

`personalizacao-de-relatorio.md` §1, classe 2: *"só **fora** do bloco
obrigatório"*. Um segundo `<div class="nota-de-reconciliacao">` **irmão**, no
mesmo `<th>` do `<thead>` — a repetição por folha é do `<thead>`, não da `div`.
Fecha junto o **BL-519** (o padrão não-guloso que trunca em silêncio quando há
`<div>` aninhado).

### 5. BL-518 (baixa) — guarda DERIVADA para `--somente-tela`

Apagar duas regras de CSS devolve texto de bancada ao papel do cliente com tudo
verde. E já são **três** modificadores `--somente-tela`, cada um com a mesma
regra copiada — **lista crescendo onde cabia propriedade** (AGENTS.md §8). A
guarda tem de varrer os templates e exigir a regra correspondente, para o
**quarto modificador nascer guardado**.

**Fora do escopo:** BL-507, BL-520, BL-521, BL-522, BL-523, BL-525 e BL-506
seguem abertos e declarados. O **BL-524** (bancos de teste órfãos) é higiene e
pode ser feito por quem passar por ali.

## Critérios de aceite

1. **BL-514:** `color: transparent` e `color: #FFFFFF` no seletor do bloco
   devolvem **código 1**, com mensagem que nomeie **CONTRASTE** — não "ausente do
   texto". As **seis** sabotagens da tabela do relatório continuam reprovando. O
   controle positivo (6 folhas, `folhas_sem_bloco_do_item_51 == []`) continua em
   **código 0**. ⚠️ **Reuso de `_localizar_linhas_do_timbre_no_documento`**, não
   uma segunda implementação de contraste (AGENTS.md §8).
2. **BL-515:** um cenário **por lista que veta**, derivado com
   `pytest.mark.parametrize(_LISTAS_QUE_IMPEDEM_A_EMISSAO)` — só aquela lista não
   vazia, resíduo zero, exigindo `pode_emitir is False`. **As seis mutações
   reprovam, nomeando a lista movida.** E os **dois docstrings** corrigidos:
   ⚠️ **a [DE-058](../projeto/decisoes.md#de-058) alcança o docstring**, não só o
   comentário de justificativa.
3. **BL-516:** o cenário L4 do relatório aparece em `listas_informativas` com
   `['1','2']`; L1 e L2 continuam emitindo; e o rótulo **não** afirma "sob o mesmo
   ancestral não classificado" quando não há ancestral.
4. **BL-517 + BL-519:** a nota continua nas **6 folhas** do PDF real, e o texto
   derivado de `.identificacao-do-documento` **deixa de conter** "não transferido
   ao Patrimônio Líquido". O padrão de extração passa a **recusar extração
   parcial**, não só vazia.
5. **BL-518:** apagar **qualquer uma** das três regras `@media print` reprova,
   **nomeando a classe órfã**. A guarda é **derivada de varredura**, nunca uma
   lista de três asserções.
6. **Sem regressão**, confirmado pelo workflow integral `Lint e testes` em
   Python 3.14 para o commit mais recente do PR. Base medida na cabeça final
   do PR #42 (`6fb5fd6`): **2148 passed, 37 skipped**. Nesta branch,
   `pytest --collect-only -q` reportou **2210 testes coletados**, mas encerrou
   com código 1 porque a conferência BL-218 exige requisições realmente
   executadas e reprova uma sessão de coleta sem execução; esse comportamento
   preexistente está registrado na verificação dirigida da DL-031. O número
   coletado serve para conferência de inventário, não como resultado da suíte.

## Divisão de arquivos

⚠️ **Escrevo isto com a colisão da DL-034 na memória, e ela foi culpa minha:**
um terceiro agente entrou nos mesmos arquivos e só não houve dano porque o
auditor mediu o herdado ([DE-073](../projeto/decisoes.md#de-073)).

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Instrumento, template, CSS e rótulo da tela BL-516 | `especialista-frontend` | `scripts/medir_identificacao_do_emitente.py`, `templates/**`, `static/css/**`, `scripts/test_medir_identificacao_do_emitente.py`, `apps/contabilidade/views_web.py` e, apenas para a asserção de tela do BL-516 com raízes, `apps/contabilidade/tests/test_dl034_tela_do_balanco.py` |
| Guardas do servidor | `desenvolvedor-pleno` | `apps/contabilidade/services.py`, `apps/contabilidade/tests/test_dl034_balanco_patrimonial.py` |
| Documentação | `arquiteto-senior` | `docs/**` |

⚠️ **`apps/contabilidade/views_web.py` fica com a frente da TELA.** No BL-516,
o `desenvolvedor-pleno` altera `services.py` e a frente da tela ajusta o rótulo
em `views_web.py`. Como a correção depende das duas frentes, **executar em
sequência**, nunca em paralelo.

O teste de tela do rótulo BL-516 também pertence à frente da TELA. Depois que o
`desenvolvedor-pleno` terminar as alterações de serviço e teste de backend, a
frente da TELA acrescenta em `test_dl034_tela_do_balanco.py` o cenário de duas
raízes divergentes; a sequência evita edição simultânea e mede o aviso real
renderizado pela view sem ancestral comum.

⚠️ **E o BL-507 destrava aqui, se houver folga:** ele ficou fora da DL-034
porque cruzava as duas frentes no mesmo passo. Nesta etapa o `desenvolvedor-pleno`
pode acrescentar a entrada de PL em `NATUREZA_NATURAL_DO_TIPO` **primeiro**, e a
frente da tela consome **depois** — em sequência declarada, não em paralelo.

## Git

Branch `feat/dl-035-guardas-demonstracao`, destino `main`. O PR cita este
plano.

## Evidências da validação local — 2026-09-24

- Migrações em PostgreSQL 16 descartável e testes integrados das duas frentes
  de contabilidade: **42 passed in 38.10s**.
- Instrumento, incluindo Chromium real, exportação de PDF e testes ponta a
  ponta/sabotagens: **135 passed in 214.16s**. O controle positivo confirma
  seis páginas, o bloco do item 51 em todas elas e a nota de reconciliação em
  todas; as mutações `color: transparent` e `#FFFFFF` devolvem código 1 e
  mencionam contraste.
- Prova backend em cópia descartável: seis cenários comportamentais e seis
  probes de mutação BL-515: **12 passed**; cada lista movida é nomeada.
- `ruff check .`, `ruff format --check .` (**225 arquivos**) e
  `manage.py check`: aprovados.
- `pwsh` não está instalado localmente. O substituto Python aplicou as mesmas
  regras de `scripts/validate-docs.ps1` em **139 arquivos Markdown**, sem
  problemas; o workflow oficial de documentação ainda precisa rodar no PR.
- A suíte ampla `apps/contabilidade apps/core` executada pelo
  `desenvolvedor-pleno` no Python 3.12.3 teve **1668 passed, 34 skipped, 1
  failed e 4 subtests passed**. A única falha foi
  `apps/core/tests/test_versao_minima_python.py::test_o_proprio_mecanismo_recusa_sintaxe_exclusiva_de_versao_posterior`,
  que valida sintaxe PEP 758 não reconhecida pelo Python 3.12 local; a CI usa
  Python 3.14 e precisa confirmar a suíte integral.
- `pytest --collect-only -q` imprimiu `2210 tests collected` e encerrou com
  código 1 pela conferência BL-218 em sessão sem execução. A suíte real e o
  workflow completo são a prova de regressão; não declarar a coleta como teste
  aprovado.

A primeira auditoria foi **reprovada apenas** porque o estado do commit não
acompanhou a criação de `38e7a6b`; os critérios de código BL-514 a BL-519 foram
aprovados. A correção única e a reconferência previstas pela §3.1 do `AGENTS.md`
foram concluídas, e a reconferência aprovou. Push, PR e os quatro workflows da
CI ainda são pendentes; o aceite de integração só será declarado depois desses
resultados.
