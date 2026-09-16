# DL-021 — Robustez do gerador de papéis em ambiente Windows

**Estado:** **integrada** pelo PR #22, na `main` em `b8c66a6`. Identificada em
2026-09-15, antes da retomada da DL-020, e executada no mesmo dia.

> **Limitação remanescente, declarada e ainda aberta:** o que esta etapa
> resolveu foi a **quebra de linha** — o gerador grava LF em qualquer sistema
> operacional. Rodar `--verificar` no Windows **continua** reportando
> `permissão 0o666` nos 14 derivados, por um motivo independente, descrito na
> seção "Descoberta durante a execução" mais abaixo e ligado ao achado A3
> (BL-175). Ler este cabeçalho como "compatibilidade Windows comprovada"
> seria errado: a compatibilidade comprovada é a de **finais de linha**. O
> cabeçalho ficou dizendo "planejada, não iniciada" depois da integração, e
> quem mediu a divergência foi o plano mestre — corrigido aqui na
> [DL-022](DL-022-plano-mestre-e-reconciliacao.md).

## Como isto apareceu

Em 2026-09-15, na retomada da DL-020, rodei `python scripts/gerar_agentes.py
--verificar` para conferir os 14 derivados antes do push final. O verificador
reportou:

> Derivados fora de sincronia com `docs/agents/papeis/`:
> - divergente: `.claude/agents/arquiteto-senior.md`
> - divergente: `.claude/agents/auditor-qa.md`
> - … (todos os 14)

Conferi os bytes brutos:

| Origem | Tamanho | Quebras de linha |
|---|---|---|
| `HEAD` no git (`git show`, `core.autocrlf=false`) | 6478 B | 131 LF, 0 CRLF |
| Disco local após `--escrever` no Windows | 6609 B | 131 CRLF, 131 LF |

A diferença (131 bytes) é exatamente os 131 caracteres `\r` que o `write_text`
adicionou. O `git status` segue limpo porque o clone do Fred tem
`core.autocrlf=true`, que normaliza CRLF↔LF no diff. O verificador, **feito para
ser byte-strict** (achado 9 do plano DL-019, registrado em
`scripts/gerar_agentes.py:1134-1140`), está certo por design — mas o gerador
**ele mesmo** produz o problema que ele reclama.

Conclusão registrada pelo Fred em 2026-09-15:

> *Guarda que grita sem motivo é pior que guarda nenhuma, porque quando gritar
> com motivo ninguém olha. E há o cenário pior — numa máquina com outra
> configuração, o CRLF entra no repositório.*

Em outras palavras: **rodar `--escrever` no Windows não converge.** O sintoma já
estava provavelmente presente antes do meu `--escrever` — vindo do próprio
checkout com `autocrlf=true`. A correção certa é no gerador (não no
verificador, que está certo) e uma rede de segurança no repositório.

## A classe do problema, não o caso

> **A classe é:** nenhum gerador de arquivos versionados produz saída diferente
> conforme o sistema operacional de quem o roda, e nenhuma cópia de trabalho fica
> em sincronia falsa com o repositório.

O caso que o Fred encontrou é **exemplo**, não definição. Outros riscos
levantados, a tratar no desenho:

- Um arquivo `.md` de papel gerado com CRLF, commitado por engano num clone
  Windows sem `.gitattributes`, entraria no repositório com CRLF e quebraria a
  comparação byte-a-byte em qualquer clone Linux subsequente.
- Um arquivo `.toml` gerado com CRLF faz o TOML parser de algumas ferramentas
  externas falhar silenciosamente (decodifica BOM ou `\r` no meio de valor de
  string).
- O `--escrever` rodando em CI Linux diverge do `--escrever` rodando em Windows
  do Fred — duas fontes de verdade para o mesmo arquivo.

## Objetivo

O gerador de papéis (`scripts/gerar_agentes.py`) grava os derivados com
**exatamente LF**, independentemente de onde rode. O repositório carrega uma
**rede de segurança** (`.gitattributes`) que neutraliza `core.autocrlf=true` em
qualquer clone. O verificador continua byte-strict — passa a ser aprovável em
qualquer sistema operacional.

## Restrição real

- **Não posso tocar no `verificar()`.** Ele é o guarda que detectou o problema,
  e amolecê-lo destrói o achado 9 inteiro.
- **Não posso tocar em nenhum arquivo já versionado** sem ter gerado antes pelo
  próprio gerador, para que o `git diff` mostre mudança só de bytes finais.
- O `chmod(0o644)` que o gerador aplica (`scripts/gerar_agentes.py:1043`)
  continua valendo — é parte do achado A3 (BL-175) e não tem relação com a
  classe aqui.

## Escopo

1. **Forçar LF na escrita do gerador.** Trocar `temporario.write_text(...)` por
   `temporario.write_bytes(arquivo.conteudo.encode("utf-8"))` ou abrir em modo
   binário com `newline=""`. Uma das duas formas é a fix; a escolha entre elas
   é decisão técnica, não de produto.
2. **Teste próprio do fix.** Teste que rode o `--escrever` em ambiente onde
   `os.linesep` é `\r\n` (Windows) e verifique que os arquivos resultantes têm
   apenas LF. Sem isso, o bug volta no primeiro clone Windows.
3. **Adicionar `.gitattributes` no repositório** com:
   ```
   *.md text eol=lf
   *.toml text eol=lf
   *.py text eol=lf
   ```
   A entrada `*.py` é rede de segurança para qualquer outro arquivo Python que
   seja gerado por ferramenta no futuro; não toca no que já está versionado.
4. **Validar que o verificador continua reprovando CRLF proposital.**
   Adicionar um teste que gere um derivado com CRLF propositalmente (via
   `write_bytes` malicioso num teste isolado) e confirme que o verificador o
   recusa. Este é o **mecanismo** que protege a integridade.

## Hipóteses de trabalho, marcadas como tal

- **HI:** o fix em `write_bytes` é suficiente — não precisa também alterar
  `Path.read_bytes()` nem o `open()` do `verificar()`. Confirmado pelo
  `scripts/gerar_agentes.py:1035` ser a única escrita com `write_text` que
  produz texto versionado. **A confirmar:** se houver outra chamada de escrita
  de texto no script, todas têm de virar `write_bytes` no mesmo diff.
- **HI:** `.gitattributes` com `eol=lf` é respeitado pelo `core.autocrlf=true`
  no clone do Fred. Confirmado pela documentação do Git e pelo comportamento
  padrão desde o Git 2.10. **A confirmar:** rodando `git status` em árvore
  limpa, nenhum arquivo versionado deve aparecer modificado depois do fix.
- **HI:** nenhum arquivo já versionado precisa de migração de bytes. Confirmado
  pelo snapshot local — os arquivos no disco estão com CRLF mas o HEAD está
  com LF; o `core.autocrlf=true` está normalizando. **A confirmar:** depois do
  `.gitattributes`, rodar `git checkout HEAD -- .claude/agents .codex/agents`
  num clone Windows sem autocrlf, e verificar que tudo fica em LF.

## Critérios de aceite

1. **O gerador grava LF em qualquer sistema operacional.** Teste roda
   `--escrever` em ambiente com `os.linesep == "\r\n"` e exige que os 14
   arquivos resultantes terminem com bytes `0x0A` apenas (sem `0x0D` no
   conteúdo, exceto dentro de string UTF-8 multibyte que porventura carregue
   `\r` legítimo — o que não é o caso desses derivados).
2. **O verificador continua byte-strict.** Teste escreve um derivado com CRLF
   propositalmente num diretório temporário isolado e exige que o verificador o
   recuse como divergente.
3. **`.gitattributes` neutraliza o `core.autocrlf=true`.** Depois do fix,
   rodar `git status` em árvore limpa retorna vazio, em Windows e em Linux.
4. **Nenhum arquivo já versionado muda de bytes por causa desta etapa.** O
   `git diff` da etapa inclui apenas: `scripts/gerar_agentes.py`, novos testes,
   `.gitattributes`. Não há mudança em `.claude/agents/*`, `.codex/agents/*`
   nem `docs/agents/papeis/*`.
5. **`--verificar` retorna zero** depois do fix, sem `core.autocrlf` precisar
   ser desligado manualmente.
6. **`--escrever` é idempotente** em qualquer SO: rodar duas vezes seguidas
   produz os mesmos bytes.
7. **A CI do PR que integrar este fix roda verde.** O job `Lint e testes` e o
   job `Validar documentação` passam no head novo. `pytest` cobre o teste
   novo.

## Descoberta durante a execução (2026-09-15)

Conferindo o `--verificar` na `main 0dd07b4` (antes do fix desta etapa), o
verificador reporta **`permissão 0o666 deixa o arquivo gravável por qualquer
usuário da máquina`** em todos os 14 derivados. A causa é o `chmod(0o644)` que
o gerador aplica (linha 1043): em Windows, `Path.chmod` não consegue zerar os
bits que o sistema não reconhece, e o `stat()` devolve `0o666` independentemente
da intenção do código.

**Fora do escopo desta etapa** por três motivos registrados:

1. **Já estava lá** antes do meu `--escrever`. `git stash` e `--verificar` na
   `main` antes do fix da DL-021 acusava o mesmo conjunto de 14 mensagens de
   permissão. **Não foi causado pela troca `write_text → write_bytes`.**
2. **A correção é diferente** da CRLF. O caminho certo é fazer o gerador
   **não** chamar `chmod` em Windows (porque ele não tem efeito), ou fazer o
   verificador **não** exigir bits que o sistema não reconhece. As duas
   opções mexem no achado A3 (BL-175) — fora do escopo da DL-021.
3. **A DL-021 não introduziu nem agravou** o sintoma. O `0o666` em clone
   Windows é independente da normalização de final de linha.

**Como fica agora:** rodar `--verificar` em Windows passa a reportar **só** o
problema de permissão, e o problema de CRLF desaparece. O sintoma de permissão
fica visível até alguém abrir uma etapa própria para o A3 em ambiente
Windows — registrada como **pendência declarada**, não como falha da DL-021.

## Fora do escopo

- Mudar o `chmod(0o644)` (já é o certo, achado A3/BL-175).
- Mudar o verificador para ser mais tolerante (achado 9 está bom).
- Qualquer alteração em `apps/**` ou em `docs/agents/papeis/**`.
- Forçar LF em arquivos não gerados (template, scripts Python existentes). A
  remediação via `.gitattributes` cobre todos, mas a verificação atesta só os
  derivados do gerador.
- Decisão sobre `core.autocrlf` recomendada para clones do projeto. Pode
  ficar como decisão documental do `AGENTS.md` em etapa futura.

## Divisão de arquivos

| Responsável | Pode editar |
| --- | --- |
| `desenvolvedor-pleno` | `scripts/gerar_agentes.py` (apenas a chamada `write_text` → `write_bytes`), testes novos em `scripts/tests/`, `.gitattributes` |
| `arquiteto-senior` | `docs/planos/DL-021-robustez-do-gerador-no-windows.md` (este arquivo), `docs/projeto/decisoes.md` (nova DE- se houver decisão de modelagem), `docs/agents/estado.md` |

## Risco principal

**A CI do PR #21 (DL-020) já está rodando** no commit `1c917d6` no momento da
abertura desta etapa. Se a DL-021 nascer de branch própria e o Fred preferir
integrá-la antes do merge da DL-020, ela vira pré-condição do Passo 0. Caso
contrário, ela entra depois do merge, e o `--verificar` segue vermelho até
então — o que é o próprio sintoma que a etapa existe para fechar. **Decisão do
Fred: antes ou depois do merge da DL-020.**

## Git

- **Branch de trabalho:** a definir. Se antes do merge da DL-020, abrir nova
  branch a partir de `7e9dc56`. Se depois, abrir nova branch a partir de
  `main` com a DL-020 já integrada.
- **Branch de destino:** `main`.
