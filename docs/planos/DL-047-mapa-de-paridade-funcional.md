# DL-047 — Mapa de paridade funcional com o sistema de referência

**Demanda:** ordem do Fred em 2026-09-27: *"eu quero que o nosso sistema
tenha todas as funções"* do sistema de referência, nos módulos Contabilidade,
Fiscal (com o mapa do Lucro Presumido), Folha e Patrimônio, usando os
manuais só como referência.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 3** — só documentação e planejamento; nenhum código muda.

## Problema

O produto tem poucos relatórios e módulos frente ao que um escritório usa.
Faltava o inventário completo do que construir, na ordem certa.

## O que foi feito

Os manuais entregues pelo Fred (convertidos para texto, 34 arquivos) foram
lidos por quatro auxiliares de pesquisa, um por módulo, sem permissão de
escrita. Cada um devolveu o inventário de relatórios e funções com a página
do manual, o que o DataLedger já tem, as dependências e as ondas. O
`arquiteto-senior` conferiu a situação no código e corrigiu o que estava
errado (o Razão já filtra período; a camada de saldos já existe), e conferiu
as páginas do fluxo da EFD Contribuições no Lucro Presumido.

Resultado, em documentos próprios:

| Módulo | Documento |
| --- | --- |
| Contabilidade | [mapa-funcional-contabil.md](../projeto/mapa-funcional-contabil.md), seção "Inventário completo — manual 10.1A-12" |
| Fiscal e EFD Contribuições no Lucro Presumido | [mapa-funcional-fiscal.md](../projeto/mapa-funcional-fiscal.md), seção "Inventário completo e o fluxo da EFD Contribuições" |
| Folha e Ponto | [mapa-funcional-folha.md](../projeto/mapa-funcional-folha.md) |
| Patrimônio e Lalur | [mapa-funcional-patrimonio-lalur.md](../projeto/mapa-funcional-patrimonio-lalur.md) |

Regras de uso dos manuais em
[fontes-de-referencia.md](../projeto/fontes-de-referencia.md): nunca no
repositório (que é público), consulta com página citada, texto nosso.

## O que o inventário mostra

1. **A maior parte do que falta não é "mais um relatório": é uma base que
   falta.** Uma base destrava vários relatórios de uma vez:
   - a estrutura de demonstração ligada à conta (hoje só a DRE) destrava
     DLPA, DMPL, DFC, DRA, DVA e notas explicativas;
   - o encerramento do exercício destrava os termos e o livro Diário;
   - os **acumuladores** do Fiscal destravam a escrituração, a apuração e a
     integração contábil;
   - as rubricas e tabelas por vigência destravam a folha inteira.
2. **Os manuais são de 2018.** Muitas obrigações listadas foram extintas ou
   substituídas (no Fiscal e sobretudo na Folha: eSocial, DCTFWeb, FGTS
   Digital, EFD-Reinf). Cada obrigação só entra depois de conferida na fonte
   oficial.
3. **Há práticas do sistema de referência que não copiamos:** sobrescrever
   ou apagar lançamento efetivado, recalcular folha paga sem rastro,
   processar várias empresas sem autorizar cada uma no servidor.

## Planos detalhados por módulo

A pedido do Fred (2026-09-27: *"separado por módulos [...] item por item
[...] não podemos deixar lacunas"*), cada módulo ganhou um plano item por
item em [docs/projeto/paridade/](../projeto/paridade/README.md): Contabilidade
(74 itens), Fiscal (91), Folha e Ponto (80), Honorários (59, mapeado nesta
etapa a partir do manual de 751 páginas), Patrimônio (26) e Lalur (26) — 356
ao todo. Cada item traz o que é, exemplo com números, página do manual,
fonte normativa (marcada **a confirmar** quando não conferida), situação no
código, dependências, dados, regras, telas, critérios de aceite e o que não
copiar. Foram escritos por auxiliares de implementação, um por arquivo, e
conferidos por amostra pelo `arquiteto-senior` (contas dos exemplos, número
de itens, validação da documentação).

**Achado de Honorários que muda o desenho:** a integração contábil e fiscal
é dupla — a cobrança entra na contabilidade do escritório e também na do
cliente, que o escritório escritura. Pergunta ao Fred no plano (HON-33,
HON-37).

## Ondas por módulo

| Módulo | Onda 1 | Onda 2 | Depois |
| --- | --- | --- | --- |
| Contabilidade | Estrutura de demonstração ligada à conta: DLPA, DMPL, DFC; análise vertical e horizontal | Encerramento do exercício, termos, livro Diário encadernável; sócios e contador responsável | Centro de custo; histórico e lançamento padrão; participantes; extrato e conciliação; ECD e ECF |
| Fiscal | Parâmetros fiscais da empresa, participantes e acumuladores | NFS-e recebida vira lançamento fiscal; integração contábil | Simples Nacional com DAS; Lucro Presumido simplificado por nota com a EFD Contribuições; NF-e; livros e obrigações |
| Folha | Rubricas, tabelas por vigência, sindicato, empregados; cálculo mensal e holerite | Férias, 13º, provisões, rescisão, integração contábil | eSocial como preparação; pró-labore, RPA, ponto |
| Patrimônio | Bem, conta patrimonial, depreciação fiscal, ficha do bem | Baixa, transferências, integração contábil | Societário, CIAP e créditos |
| Lalur | — | — | Depois de Patrimônio e com a DRE: Parte A, Parte B, dentro da ECF |
| Honorários | Serviços, contratos por cliente com vigência e reajuste, cálculo mensal | Cobrança, recebimento e baixa | Integração contábil (dupla), NFS-e do escritório, boletos e remessa, relatórios gerenciais |

## Recomendação ao Fred

Pela cadeia, o ganho maior por esforço está em dois lugares, e a escolha
entre eles é dele:

- **A — fechar a Contabilidade anual:** DLPA, DMPL e DFC, depois o
  encerramento do exercício e o livro Diário com termos. Usa bases que já
  existem (saldos, DRE, Balanço) e entrega o pacote de demonstrações que o
  escritório emite todo ano.
- **B — o Fiscal alimentar a Contabilidade:** acumuladores, NFS-e virando
  lançamento fiscal e integração contábil. É o que tira a digitação do
  escritório, porque o acervo real é quase todo NFS-e.

Recomendação do `arquiteto-senior`: **A primeiro, porque é menor e fecha um
módulo inteiro; B logo em seguida.** Folha é o maior módulo e o de mais
norma nova; entra depois, com a mesma disciplina de fonte oficial.
Honorários é independente dos demais (usa o cadastro de empresas que já
existe) e pode andar em paralelo quando houver quem o faça. Patrimônio vem
antes do Lalur, que usa o ganho de capital e a depreciação dele.

## Critérios de aceite desta etapa

1. Um inventário por módulo, com página do manual, situação no DataLedger e
   dependências.
2. Nenhum trecho do manual copiado; nenhum arquivo do manual no repositório.
3. Toda regra legal apontada para a fonte oficial a consultar, sem valor
   inventado.
4. Documentação válida e o estado atualizado.

## Fora desta etapa

Implementação de qualquer item; Honorários, Processos e Registro, que o Fred
não pediu agora (os manuais estão no conjunto para quando forem planejados).
