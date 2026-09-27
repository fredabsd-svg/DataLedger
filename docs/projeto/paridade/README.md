# Plano de paridade funcional — índice e modelo

Planos detalhados, **um por módulo**, de tudo o que o sistema de referência
faz e o DataLedger ainda não faz, item por item. Pedido do Fred em
2026-09-27: *"ser claro e minucioso [...] exemplificar e referenciar e
explicar item por item [...] não podemos deixar lacunas, pois caso outro dev
comece a codar, ele não se perca"*. Etapa:
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md).

| Módulo | Plano | Prefixo dos itens |
| --- | --- | --- |
| Contabilidade | `contabilidade.md` (em escrita) | CTB |
| Fiscal | `fiscal.md` (em escrita) | FIS |
| Folha e Ponto | `folha.md` (em escrita) | FOL |
| Patrimônio | `patrimonio.md` (em escrita) | PAT |
| Lalur | `lalur.md` (em escrita) | LAL |
| Honorários | `honorarios.md` (em escrita) | HON |

## Regras que valem para todos os planos

- **Manual responde rotina; norma vem da fonte oficial.** Cada item traz as
  duas referências separadas: a página do manual do sistema de referência
  (rotina) e a norma a consultar (lei, IN, NBC, leiaute oficial). Valor
  normativo que não foi conferido fica marcado **a confirmar** — nunca vira
  constante no código.
- **Nada copiado do manual.** Texto, tela, rótulo e estrutura de menu são do
  fornecedor. O que está aqui é descrição nossa.
- **As regras do [AGENTS.md](../../../AGENTS.md) valem em todo item:**
  dinheiro em `Decimal`; efetivado é imutável e se corrige por procedimento
  rastreável; período encerrado exige controle; autorização no servidor;
  isolamento por empresa e escritório; trilha de auditoria; idempotência.
- **Um item só vira código com plano de etapa próprio** (`DL-xxx`), que
  aponta para o ID do item aqui.

## Modelo de cada item

```
### PREFIXO-NN — Nome do item

**O que é.** Explicação para quem não é contador.
**Exemplo.** Caso concreto com números sintéticos.
**Referência de rotina.** Manual do sistema de referência, páginas.
**Fonte normativa.** Lei, IN, NBC ou leiaute oficial a consultar; situação
(confirmada, a confirmar, não há — decisão de produto).
**Situação no DataLedger.** Existe / parcial / não existe, com o arquivo.
**Depende de.** IDs de outros itens.
**Dados.** Entidades e campos principais.
**Regras.** Verificáveis, cada uma vira teste.
**Telas e documentos.** Telas, relatórios, classe do documento.
**Critérios de aceite.** Testáveis.
**Não copiar / riscos.** Quando houver.
**Perguntas.** Só o que o manual e a fonte oficial não respondem.
```
