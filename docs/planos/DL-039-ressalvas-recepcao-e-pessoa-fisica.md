# DL-039 — Ressalvas da recepção de NFS-e e do cliente pessoa física

**Demanda:** ordem do Fred de prosseguir (25/09/2026), aplicada às ressalvas da
[reconferência](../auditorias/2026-09-25-dl-010-f1-dl-038-reconferencia.md) da
[DL-010 F1](DL-010-F1-recepcao-nfse.md) e da [DL-038](DL-038-cliente-pessoa-fisica.md).
Etapa própria, e não terceira rodada daquelas (§3.1 do AGENTS.md; mesmo caminho
da DL-035).
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — a BL-526 faz um sistema quebrado parecer funcionando na
recepção de documento do cliente. Auditoria independente, uma rodada.
**Branch:** `claude/vigilant-bardeen-jo12l4` → `main`.

## Escopo

| Item | Critério de aceite |
| --- | --- |
| [BL-526](../projeto/backlog.md) | Só `DataError` e restrições conhecidas viram recusa por arquivo, com mensagem neutra, sem texto interno do banco; `ProgrammingError`, `InternalError`, `InterfaceError` e `NotSupportedError` desfazem o envio inteiro (sem lote e sem trilha) e chegam como erro de sistema. Teste com erro simulado que reprova se a exceção for engolida; experimento do auditor (coluna renomeada) reproduzido |
| [BL-527](../projeto/backlog.md) | Testes que matam N04, N05 e N06 |
| [BL-528](../projeto/backlog.md) | Um só caminho de identificação de empresa, sempre filtrado pelo escritório; F01 e F02 mortas |
| [BL-529](../projeto/backlog.md) | Estabelecimento de empresa CPF recusado também no banco (gatilho ou alternativa medida, com a decisão registrada no código); N18 morta; admin cria e edita empresa CPF, com CNPJ e CPF condicionais ao tipo |

**Fora:** BL-530 a BL-532 (dependem de implantação ou são de baixo impacto) e
PE-68 (decisão do Fred).

## Responsáveis e verificação

`desenvolvedor-pleno` implementa, em `apps/fiscal/**` e `apps/empresas/**`, com
migração nova se houver restrição de banco. Verificação: suíte completa, lint,
formatação, `manage.py check`, `makemigrations --check`, e cada mutação citada
reaplicada em worktree descartável. Depois, `auditor-qa` confere a versão
integrada. Reversão: revert do commit; a migração, se houver, é reversível.

## Auditoria

[Rodada 1](../auditorias/2026-09-26-dl-039-rodada-1.md) em `c1aedd6`: **APROVADA COM
RESSALVAS**. BL-526 a BL-528 fechados, sem mutação sobrevivente. Ressalvas médias
BL-533 (gatilho vira 500 no admin e na API) e BL-534 (corrida entre os dois
gatilhos) na correção única da etapa, seguida de uma reconferência; BL-535 aceita
como limite de desenvolvimento.

[Reconferência](../auditorias/2026-09-26-dl-039-reconferencia.md) em `0680273`:
**APROVADA COM RESSALVAS**, todas baixas (BL-536 a BL-538). BL-533 e BL-534
fechados; corrida real sem sobra de empresa CPF com estabelecimento nas duas
ordens. **Etapa encerrada**; falta só a integração à `main` por PR.
