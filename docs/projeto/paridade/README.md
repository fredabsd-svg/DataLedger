# Plano de paridade funcional — índice e modelo

Planos detalhados, **um por módulo**, de tudo o que o sistema de referência
faz e o DataLedger ainda não faz, item por item. Pedido do Fred em
2026-09-27: *"ser claro e minucioso [...] exemplificar e referenciar e
explicar item por item [...] não podemos deixar lacunas, pois caso outro dev
comece a codar, ele não se perca"*. Etapa:
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md).

| Módulo | Plano | Itens |
| --- | --- | --- |
| Contabilidade | [contabilidade.md](contabilidade.md) | 74 (CTB-01 a CTB-74) |
| Fiscal, com a EFD Contribuições no Lucro Presumido | [fiscal.md](fiscal.md) | 91 (18 obsoletos ou fora de escopo) — ⚠️ **furo na série: FIS-74 a FIS-79 não existem**; a numeração salta de FIS-73 para FIS-80 |
| Folha e Ponto | [folha.md](folha.md) | **79** (FOL-01 a FOL-79) |
| Honorários | [honorarios.md](honorarios.md) | 59 (47 de escopo ativo + 12 fora de escopo) |
| Patrimônio | [patrimonio.md](patrimonio.md) | 26 (PAT-01 a PAT-26) |
| Lalur | [lalur.md](lalur.md) | 26 (LAL-01 a LAL-26) |

Total medido em 04/10/2026 por varredura dos arquivos: **355 itens**, não 356
— a folha tem 79, e não 80 como dizia a versão anterior deste índice. ⚠️
Corrigido na DL-064; a contagem anterior (356, Folha 80) **não fechava com
os arquivos** e foi medida como erro, não estimada.

⚠️ **Estes mapas envelhecem (DL-064, 04/10/2026).** Foram escritos em
27/09/2026 e **não foram atualizados** depois da leva DL-061/DL-062/DL-063. O
CTB-14 (DMPL) continuava marcado "Não existe" depois de integrado, e todas as
citações `arquivo:linha` dos itens "Existe" estavam deslocadas. **A prova de
existência é o símbolo e o plano, nunca o número da linha**, e a situação
precisa ser reconferida no código antes de planejar contra ela.

**Como usar:** escolha o módulo, leia a introdução e o mapa de ondas, pegue o
primeiro item da onda que ainda não existe, confira as dependências, e abra
um plano de etapa (`DL-xxx`) citando os IDs. Antes de codar qualquer regra
marcada **a confirmar**, confirme a fonte oficial e registre em
[requisitos.md](../requisitos.md).

⚠️ **Antes de confiar na situação de um item (DL-064), confirme no código.**
O estado do item é o que o documento dizia **quando foi escrito**, e estes
mapas envelheceram. Dois casos já medidos: o **CTB-14 (DMPL)** seguia marcado
"Não existe" depois de entregue, e o **FIS-71 (backup)** se declarava
"coberto pela infraestrutura" enquanto o código e o backlog dizem que nunca foi
verificado. Uma planilha gerada destes arquivos descreve **o que o documento
diz** — e é por isso que a situação se corrige **na mesma etapa que entrega o
item**, não depois.

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
