# DL-035 — As guardas da demonstração

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
6. **Sem regressão**, com os números declarados e conferidos por
   `--collect-only`. Base: **2107 passed, 14 skipped**, `--collect-only 2121`.

## Divisão de arquivos

⚠️ **Escrevo isto com a colisão da DL-034 na memória, e ela foi culpa minha:**
um terceiro agente entrou nos mesmos arquivos e só não houve dano porque o
auditor mediu o herdado ([DE-073](../projeto/decisoes.md#de-073)).

| Frente | Responsável | Pode editar |
| --- | --- | --- |
| Instrumento, template e CSS | `especialista-frontend` | `scripts/medir_identificacao_do_emitente.py`, `templates/**`, `static/css/**`, `scripts/test_medir_identificacao_do_emitente.py` |
| Guardas do servidor | `desenvolvedor-pleno` | `apps/contabilidade/services.py`, `apps/contabilidade/tests/test_dl034_balanco_patrimonial.py` |
| Documentação | `arquiteto-senior` | `docs/**` |

⚠️ **`apps/contabilidade/views_web.py` fica com a frente da TELA**, e o BL-516
**não** o toca — só `services.py` e o rótulo, que é da tela. Se a correção do
rótulo exigir as duas frentes, **executar em sequência**, nunca em paralelo.

⚠️ **E o BL-507 destrava aqui, se houver folga:** ele ficou fora da DL-034
porque cruzava as duas frentes no mesmo passo. Nesta etapa o `desenvolvedor-pleno`
pode acrescentar a entrada de PL em `NATUREZA_NATURAL_DO_TIPO` **primeiro**, e a
frente da tela consome **depois** — em sequência declarada, não em paralelo.

## Git

Branch `claude/accounting-agent-team-setup-mn6lyf`. O PR cita este plano.
