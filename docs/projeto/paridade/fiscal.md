# Plano de paridade — Fiscal

Plano detalhado, item por item, do que falta ao módulo Fiscal do DataLedger
para cobrir as capacidades de um sistema de escrita fiscal completo,
seguindo o pedido do Fred em 2026-09-27: *"separado por módulos [...] deve
contemplar todas as funções que você mapeou e descobriu nos manuais [...]
ser claro e minucioso. E exemplificar e referenciar e explicar item por
item. Não tenha medo de fazer um plano grande. O que não podemos é deixar
lacunas. Pois caso outro dev comece a codar, ele não se perca."*

Modelo de item, regras de uso do manual e convenções gerais:
[README.md](README.md). Etapa que originou este documento:
[DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md).

## Escopo

Este documento cobre **toda** a Escrita Fiscal: cadastros que sustentam o
cálculo, movimentos (entradas, saídas, serviços, cupom fiscal), apuração,
parcelamento e pagamento de impostos, integração contábil e de honorários,
livros fiscais, demonstrativos de apuração, relatórios de acompanhamento e
conferência, guias de recolhimento, relatórios cadastrais/estoque/contas a
pagar e receber, obrigações acessórias e as rotinas de operação (backup,
conferência de lançamentos, alteração em massa, importação por formato).
Inclui uma seção dedicada ao fluxo da **EFD Contribuições no Lucro
Presumido** ("mapa do Lucro Presumido"), por pedido explícito do Fred.

Fora deste documento: Contabilidade, Folha, Patrimônio, Lalur e Honorários
têm planos próprios (ver [README.md](README.md)) — aqui eles só aparecem
como **dependência** ou **destino de integração**, nunca detalhados.

## Fontes

- [mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md) — levantamento
  original de capacidades, o acervo real do escritório (RC-65 a RC-76) e o
  inventário completo com página do manual, inclusive o resumo do fluxo da
  EFD Contribuições.
- [mapa-funcional-contabil.md](../mapa-funcional-contabil.md), seção
  "Integração fiscal → contábil" — como a nota vira lançamento, a amarração
  de contas pelo acumulador e pelo cadastro de imposto, e a regeração.
- [personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md) — as
  três classes de documento (conferência, demonstração, livro) que
  determinam o que cada relatório fiscal pode e não pode personalizar.
- [requisitos.md](../requisitos.md), [backlog.md](../backlog.md),
  [decisoes.md](../decisoes.md) — RC, BL e DE já confirmados que este plano
  reaproveita, citados item a item.
- [DL-010-recepcao-de-documentos-fiscais.md](../../planos/DL-010-recepcao-de-documentos-fiscais.md)
  e [DL-010-F1-recepcao-nfse.md](../../planos/DL-010-F1-recepcao-nfse.md) —
  o plano e a fatia já implementada, ponto de partida deste documento.
- Manual de rotina do sistema de referência (Domínio Escrita Fiscal, 2018,
  2.324 páginas) e o manual de 22 páginas "EFD Lucro Presumido" — **apenas
  como referência de rotina**, nunca como fonte normativa. Nenhum trecho
  copiado; nenhum arquivo do manual entra neste repositório
  ([fontes-de-referencia.md](../fontes-de-referencia.md)).
- Código real em `apps/fiscal/` (`models.py`, `services.py`, `leitor.py`,
  `permissoes.py`, `views_web.py`, `urls_web.py`), lido para descrever com
  exatidão o que **já existe**, não o que o README presume.

## Convenções deste documento

- IDs `FIS-01`, `FIS-02`... em ordem de onda, não de importância. Um item
  de onda 9 pode ser tecnicamente simples; ele só entra depois porque
  depende de fundação que ainda não existe.
- Cada item segue **exatamente** o modelo do [README.md](README.md):
  O que é, Exemplo, Referência de rotina, Fonte normativa, Situação no
  DataLedger, Depende de, Dados, Regras, Telas e documentos, Critérios de
  aceite, Não copiar/riscos, Perguntas.
- Valor monetário sempre em `Decimal`, nunca `float` (AGENTS.md §10,
  DE-010). Exemplos usam números **sintéticos**, nunca dado real de
  cliente.
- Alíquota, prazo, fórmula ou leiaute que este documento não confirmou em
  fonte oficial aparece marcado **"a confirmar"** — nunca vira valor fixo
  no exemplo sem essa marcação.
- "Referência de rotina" cita **página do manual**, nunca texto dele. O
  manual é material de terceiro, de 2018, e **não está neste repositório**.

## Aviso sobre o material de referência

O manual da Escrita Fiscal é de **2018**. Muitas das obrigações que ele
descreve foram extintas, substituídas ou renomeadas desde então — o
Simples Nacional, o Bloco K, o eSocial/EFD-Reinf e a própria EFD
Contribuições tiveram mudanças relevantes de leiaute e de vigência entre
2018 e 2026. **Nenhuma obrigação, alíquota ou prazo deste documento é
requisito só por estar no manual.** Cada item de obrigação traz a fonte
oficial que precisa ser consultada antes de qualquer linha de código, e a
seção final lista as obrigações **que o manual cita e que este documento
explicitamente não assume como vigentes**.

Soma-se a isso a **Reforma Tributária do Consumo** (Emenda Constitucional
132/2023, regulamentada pela LC 214/2025): IBS e CBS não são "assunto
futuro" para este projeto — o achado RC-76 mediu o bloco IBS/CBS presente
em **12% das NFS-e reais do acervo do Fred** (583 de 4.979 documentos, em
22 de 52 municípios), o que este mesmo documento recebe e guarda
(DE-074), mas ainda não interpreta (pendência PE-39). Qualquer item deste
plano que toque ICMS, ISS, PIS ou COFINS precisa, quando for implementado,
reconferir se a regra ainda está vigente para o período tratado ou se já
foi substituída/coexiste com IBS/CBS pelo cronograma de transição da
LC 214/2025.

## Estado atual medido no código (2026-09-27)

`apps/fiscal/` existe e contém **só a recepção de NFS-e nacional**
(DL-010, fatia 1; DE-074). Medido por leitura de `models.py`,
`services.py`, `leitor.py`, `permissoes.py`, `views_web.py`:

| Capacidade | Situação real |
| --- | --- |
| Recepção de NFS-e nacional (XML solto, ZIP), leiautes 1.00 e 1.01 | **Pronta e auditada** — `DocumentoFiscal`, `receber_envio` |
| Deduplicação por `(escritório, identificador)`, evento órfão, isolamento | **Pronto e auditado** — DE-074, DE-076, DE-077 |
| Situação (válida/cancelada) derivada de evento, nunca gravada | **Pronto** — `situacao_do_documento` |
| Consulta e filtro de documentos recebidos, exibição do XML original | **Pronto** — `documentos_lista`, `documento_detalhe` |
| Retenção do ISSQN (`tpRetISSQN`) | **Lida e exibida, não interpretada** (RC-110) |
| Reconhecimento de NF-e no leitor | **Detecta o namespace e recusa explicitamente** — `"tipo ainda não suportado: NF-e"` (`leitor.py`); é fatia 2 da DL-010, não implementada |
| Parâmetros fiscais da empresa, participantes fornecedor/cliente | **Não existe** |
| Produtos, NCM, unidades, acumuladores | **Não existe** |
| Qualquer lançamento fiscal (nota vira movimento) | **Não existe** — a recepção grava o documento, não o lançamento |
| Apuração de qualquer imposto | **Não existe** |
| Integração contábil a partir do Fiscal | **Não existe** |
| Livros, demonstrativos, guias, obrigações acessórias | **Não existe** |

Conclusão medida, não presumida: a base de recepção está sólida — é a
"onda 0" deste plano — e **tudo o que transforma um documento recebido em
resultado fiscal está por fazer**, da fundação (parâmetros e acumuladores)
até o último relatório.

## Mapa de dependências e ordem (ondas)

A cadeia de dependência real, medida no manual e no código, é linear na
fundação e se ramifica depois:

```
Parâmetros fiscais da empresa
  → Participantes, Produtos/NCM, Impostos por vigência
    → Acumuladores (classificação fiscal — o centro do motor)
      → Lançamento fiscal a partir do documento recebido (NFS-e primeiro)
        → Integração contábil
          → Apuração
            ├─ Simples Nacional (RBT12, DAS)
            ├─ Lucro Presumido / EFD Contribuições (ramo "simplificado por nota" primeiro)
            └─ (Lucro Real fica fora — não há evidência de cliente nesse regime)
        → NF-e de entrada e saída (produto/estoque entram aqui)
          → Livros fiscais, demonstrativos, guias, obrigações acessórias
```

Esta ordem **é a mesma recomendada em**
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#ondas-recomendadas)
e em [DL-047](../../planos/DL-047-mapa-de-paridade-funcional.md#ondas-por-módulo),
detalhada aqui item a item:

| Onda | Conteúdo | Itens | Por que nesta ordem |
| --- | --- | --- | --- |
| 0 | Já implementado | FIS-01–FIS-02 | Base sobre a qual tudo abaixo se apoia; documentado para não reimplementar |
| 1 | Fundação | FIS-03–FIS-12 | Nada fiscal calcula sem parâmetro, participante, produto e acumulador |
| 2 | Escrituração de serviços | FIS-13–FIS-17 | 85% do acervo real é NFS-e (RC-66) — é o lançamento que mais vale a pena construir primeiro |
| 3 | Integração contábil e honorários | FIS-18–FIS-22 | É o que dá valor à contabilidade já pronta (BL da DL-047) |
| 4 | Apuração, Simples Nacional, Lucro Presumido/EFD Contribuições | FIS-23–FIS-34 | Primeiro regime ponta a ponta, escolhido pela composição real da carteira |
| 5 | NF-e de entrada e saída | FIS-35–FIS-43 | 11% do acervo (RC-65); exige produto/estoque, que os regimes simplificados dispensam |
| 6 | Livros fiscais | FIS-44–FIS-48 | Depende de apuração e de lançamento consolidados por período |
| 7 | Demonstrativos de apuração | FIS-49–FIS-52 | Mesma dependência de livros; é a "prova" impressa da apuração |
| 8 | Acompanhamento e conferência | FIS-53–FIS-58 | Relatórios de conferência — classe 1 de personalização, sem forma prescrita |
| 9 | Guias | FIS-59–FIS-61 | Depende de apuração calculada e de dados bancários (FIS-12) |
| 10 | Cadastrais, estoque, contas a pagar/receber | FIS-62–FIS-64 | Relatórios de apoio, dependem dos cadastros da onda 1 e do estoque da onda 5 |
| 11 | Obrigações acessórias (vigência a confirmar) | FIS-65–FIS-70 | Cada uma exige a apuração correspondente pronta, mais confirmação de vigência |
| 12 | Operação e utilitários | FIS-71–FIS-73 | Atravessam todas as ondas anteriores; entram quando há volume de dados que as justifique |

Total: **73 itens de escopo ativo** (FIS-01 a FIS-73) e **18 itens fora de
escopo, obsoletos ou dependentes de confirmação** (FIS-80 a FIS-97).

## Onda 0 — Já implementado

### FIS-01 — Recepção de documentos fiscais (NFS-e nacional)

**O que é.** A porta de entrada do módulo Fiscal: o escritório envia um
XML solto, vários XMLs ou um ZIP, e o sistema lê, valida, identifica a
empresa dona do documento e grava o original íntegro, sem duplicar.
**Exemplo.** O Fred envia um ZIP com 500 NFS-e de setembro. O sistema
processa cada uma: 480 são gravadas como novas, 15 já existiam (reenvio) e
5 são recusadas (CNPJ de nenhuma empresa do escritório) — o relatório do
envio mostra os três grupos.
**Referência de rotina.** Não aplicável — a recepção de NFS-e nacional no
formato de 2026 não existe no manual de 2018; o desenho é nosso, apoiado
no leiaute oficial (esquemas XSD do Portal Nacional da NFS-e).
**Fonte normativa.** Esquemas XSD oficiais do Portal Nacional da NFS-e,
pacote `NFSe-ESQUEMAS_XSD-v1.01-20260209` (confirmada, usada na
implementação).
**Situação no DataLedger.** **Pronto e auditado** —
`apps/fiscal/models.py` (`DocumentoFiscal`, `LoteDeRecepcao`,
`EventoFiscal`, `VinculoDocumentoEmpresa`), `apps/fiscal/services.py`
(`receber_envio`), `apps/fiscal/leitor.py`. Ver DE-074, DE-076.
**Depende de.** Nada — é a fundação de tudo o mais.
**Dados.** `DocumentoFiscal` (identificador, versão, XML original,
SHA-256, prestador, tomador, valores, `tp_ret_issqn`); `EventoFiscal`;
`LoteDeRecepcao`; `VinculoDocumentoEmpresa`.
**Regras.** Deduplicação por `(escritório, identificador)`; evento órfão
aceito e aplicado depois; classificação pelo conteúdo, nunca pelo nome do
arquivo; isolamento por escritório verificado no servidor; um envio por
vez por escritório (`pg_try_advisory_xact_lock`).
**Telas e documentos.** Tela de recepção e relatório do envio (classe
conferência) — `templates/fiscal/`, `views_web.recepcao`,
`views_web.relatorio_envio`.
**Critérios de aceite.** Os 22 critérios de
[DL-010](../../planos/DL-010-recepcao-de-documentos-fiscais.md#critérios-de-aceite)
— já cumpridos e testados (`apps/fiscal/tests/`).
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma — item fechado.

### FIS-02 — Consulta e conferência de documentos recebidos

**O que é.** A tela e a API que permitem ao escritório ver o que já
chegou: filtrar por empresa, competência e situação (válida/cancelada),
abrir o XML original de um documento ou evento.
**Exemplo.** O Fred filtra por competência 09/2026 e situação "cancelada"
e vê as 3 NFS-e canceladas do mês, cada uma com o evento de cancelamento
associado, mesmo quando o evento chegou antes da nota (RC-70).
**Referência de rotina.** Não aplicável — desenho próprio; não existe
equivalente direto de "recepção de NFS-e nacional" no manual de 2018.
**Fonte normativa.** Não aplicável — é conferência interna, não obrigação
externa.
**Situação no DataLedger.** **Pronto** — `views_web.documentos_lista`,
`documento_detalhe`, `documento_xml`, `evento_xml`;
`services.documentos_do_escritorio`, `situacao_do_documento`.
**Depende de.** FIS-01.
**Dados.** Mesmos de FIS-01, com a anotação `cancelada` calculada no
banco (`Exists`/`OuterRef`, sem N+1).
**Regras.** Situação sempre **derivada** do evento, nunca gravada
(DE-074 item 4); filtro de empresa sempre adicional ao de escritório,
nunca substituto (isolamento).
**Telas e documentos.** Lista e detalhe de documento fiscal (classe
conferência).
**Critérios de aceite.** Cumpridos — `apps/fiscal/tests/test_consultas.py`,
`test_telas_dl010_f1.py`.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma — item fechado.

## Onda 1 — Fundação

### FIS-03 — Parâmetros fiscais da empresa

**O que é.** O cadastro central que diz, por empresa, qual regime
tributário ela segue (Simples Nacional, Lucro Presumido, Lucro Real),
quais impostos ela recolhe, se controla estoque, se controla contas a
pagar/receber, e — para o Lucro Presumido — qual regime de apuração do
PIS/COFINS (competência ou caixa) e qual forma de cálculo (completo,
simplificado por produto, simplificado por nota). É o parâmetro que a
seção "Fluxo da EFD Contribuições" (mais abaixo) usa como primeira
bifurcação.
**Exemplo.** A empresa "Consultoria ABC Ltda." (CNPJ sintético
12.345.678/0001-90) é cadastrada com regime "Lucro Presumido", apuração
PIS/COFINS "competência", forma de cálculo "simplificado por nota", sem
controle de estoque (presta só serviço). Esse conjunto de escolhas é o que
a onda 4 (FIS-30/FIS-31) vai ler para decidir como calcular PIS/COFINS.
**Referência de rotina.** Manual Domínio Escrita Fiscal, menu Controle,
janela Parâmetros (múltiplas guias: Geral, Federal, Estadual, Municipal,
Impostos, Personaliza) — Manual EFD Lucro Presumido, p. 1-2 (a decisão de
regime/apuração é o primeiro passo do fluxograma).
**Fonte normativa.** Regime tributário: LC 123/2006 (Simples Nacional) e
Lei 9.718/1998, arts. 8º-9º, e Decreto 9.580/2018 (Lucro Presumido) — a
confirmar dispositivo exato por regime. Regime de apuração PIS/COFINS
(competência/caixa): Lei 9.718/1998 art. 2º c/c IN RFB vigente sobre
regime de caixa — **a confirmar**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** Nada dentro do Fiscal; depende do cadastro de `Empresa`
já existente em `apps/empresas`.
**Dados.** Regime tributário; apuração PIS/COFINS (competência/caixa);
forma de cálculo (completo/simplificado por produto/simplificado por
nota); flags de controle de estoque e de contas a pagar/receber; lista de
impostos ativos por vigência (liga a FIS-08); UF e município de referência
para ICMS/ISS.
**Regras.** Todo parâmetro tem **vigência** (versionado no tempo,
AGENTS.md §10); mudança de regime não altera cálculo de período já
apurado; forma de cálculo "simplificado por nota" só é oferecida quando o
regime de apuração é "competência" ou "caixa" (o manual mostra que só
"simplificado" existe no regime de caixa — nunca "completo").
**Telas e documentos.** Tela de cadastro de parâmetros (classe
conferência/cadastro), não impressa isoladamente.
**Critérios de aceite.** Empresa sem parâmetro cadastrado não consegue
gerar lançamento fiscal (recusa explícita, nunca cálculo com valor
padrão); alterar regime não reprocessa períodos fechados sem ação
explícita; toda leitura de parâmetro por período resolve pela vigência
correta.
**Não copiar/riscos.** O manual tem dezenas de sub-guias e opções que
cobrem regimes especiais (bares/restaurantes, agropecuário, SCP,
combustíveis) fora da carteira conhecida do Fred — não implementar opção
sem demanda medida (ver FIS-97).
**Perguntas.** Quais regimes tributários (Simples Nacional, Lucro
Presumido, Lucro Real) e quais UFs/municípios existem hoje na carteira do
Fred? Sem essa resposta, o cadastro de parâmetros não sabe quais campos
são realmente necessários no primeiro corte.

### FIS-04 — Participantes: fornecedores, clientes, remetentes/destinatários

**O que é.** O cadastro de quem participa de um documento fiscal do lado
de fora da empresa: fornecedor (compra), cliente (venda/serviço) e
remetente/destinatário (transporte). Hoje a recepção (FIS-01) já
**identifica** empresa do escritório pelo CNPJ/CPF do documento, mas não
tem cadastro de participante **externo** — só sabe dizer "este documento
pertence a esta empresa do escritório".
**Exemplo.** A "Consultoria ABC Ltda." presta serviço para a empresa
"Comércio XYZ Ltda." (cliente, CNPJ sintético 98.765.432/0001-10, não é
cliente do escritório). Hoje a NFS-e é recebida e o tomador fica só como
texto (`tomador_nome`, `tomador_documento`) em `DocumentoFiscal`; não há
uma entidade "Participante" reutilizável entre documentos, com endereço,
inscrição estadual/municipal e histórico de alteração cadastral.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 202-219
(cadastro de Fornecedores, com guias Geral, Opções, Alterações e
Dependentes).
**Fonte normativa.** Não há norma que dite o formato do cadastro
**interno** de participante; o que é normativo é o CNPJ/CPF em si (Lei
Complementar e Instrução Normativa da Receita Federal sobre CNPJ
alfanumérico, já tratado pela DL-011).
**Situação no DataLedger.** **Não existe** como cadastro próprio — a
recepção (FIS-01) grava nome e documento do participante como campo de
texto dentro de `DocumentoFiscal`, sem reaproveitamento entre documentos.
**Depende de.** FIS-01 (fonte inicial de dados de participante, extraídos
das notas já recebidas).
**Dados.** Nome/razão social; tipo de inscrição (CNPJ/CPF/CEI/outros);
número de inscrição; endereço completo; inscrição estadual e municipal;
regime de apuração do participante (quando relevante para retenção);
histórico de alterações cadastrais (o manual guarda cada alteração com
data, RC-nenhum ainda confirmado — desenho a decidir).
**Regras.** Um participante nunca é a mesma linha de duas empresas
diferentes do escritório sem vínculo explícito (mesmo molde de
isolamento de FIS-01); atualização de CNPJ/razão social é rastreável
(trilha), nunca sobrescrita silenciosa.
**Telas e documentos.** Cadastro de participante (classe
conferência/cadastro).
**Critérios de aceite.** Uma NFS-e recebida com tomador desconhecido gera
um participante rascunho que o escritório pode completar depois, sem
perder o vínculo com o documento de origem.
**Não copiar/riscos.** O manual tem campos de "Agente regulado" e
"Interdependência com a empresa" ligados a obrigações específicas
(I-SIMP, EFD-Reinf) que dependem da vigência dessas obrigações — não
implementar sem confirmar necessidade real.
**Perguntas.** O cadastro de participante deve nascer automaticamente da
recepção de documentos (como um "rascunho" a completar) ou deve ser
sempre cadastro manual prévio? Isso muda a ordem de implementação entre
FIS-01 e FIS-04.

### FIS-05 — Produtos e serviços, com tributação por NCM

**O que é.** O cadastro de cada produto ou serviço que a empresa
movimenta, com a classificação fiscal (NCM para produto) e as regras de
tributação **por vigência** — é o cadastro que o ramo "completo" e o ramo
"simplificado por produto" da EFD Contribuições exigem (FIS-32, FIS-31).
No ramo "simplificado por nota" (prioritário pela composição do acervo,
RC-66), este cadastro **não é necessário**.
**Exemplo.** Um produto "Notebook X" com NCM sintético `8471.30.12`, e uma
vigência de tributação a partir de 01/01/2026 com CST de PIS/COFINS "01 -
Operação Tributável com Alíquota Básica".
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 221-284
(cadastro de Produtos, com dados de impostos por NCM).
**Fonte normativa.** Tabela NCM (Nomenclatura Comum do Mercosul, Receita
Federal/Siscomex — vigência a confirmar); tabela de CST de PIS/COFINS (IN
RFB vigente); tabela de CST/CSOSN de ICMS (Ajuste SINIEF 03/1994 e
Confaz) — todas **a confirmar** antes de qualquer implementação de
cálculo.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-03 (regime da empresa determina quais campos de
tributação são exigidos).
**Dados.** Código, descrição, NCM, unidade de medida, vigências de
tributação (CST de ICMS/PIS/COFINS/IPI, alíquotas quando aplicável,
natureza da receita).
**Regras.** Vigência obrigatória e não sobreposta para o mesmo produto
(AGENTS.md §10); alteração de NCM ou CST não reprocessa lançamento já
efetivado.
**Telas e documentos.** Cadastro de produto (classe cadastro/conferência).
**Critérios de aceite.** Um produto sem vigência de tributação vigente na
data do lançamento impede o lançamento com erro explícito, nunca silêncio.
**Não copiar/riscos.** Nenhum copiado; é o cadastro que menos urge pela
composição real do acervo (85% NFS-e, RC-66) — **só necessário quando
formos além do ramo "simplificado por nota"**.
**Perguntas.** A carteira do Fred tem cliente em regime não cumulativo
(Lucro Real) que exija o ramo "completo", ou todos os clientes de
Presumido cabem no "simplificado por nota"? Decide se FIS-05 entra cedo
ou fica adiado.

### FIS-06 — Unidades e grupos de produtos

**O que é.** Cadastros de apoio ao produto: unidade de medida (peça, kg,
hora) com conversão entre unidades diferentes, e agrupamento de produtos
para relatório e apuração por grupo.
**Exemplo.** Unidade "CX" (caixa) convertendo para "UN" (unidade) na
razão de 1 para 12.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2152 (guia
Unidades) e p. 1987 (guia Grupos, seção Cadastrais).
**Fonte normativa.** Não há exigência normativa de unidade; é
organização interna do cadastro.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-05.
**Dados.** Código, descrição, fator de conversão entre unidades.
**Regras.** Conversão sempre por `Decimal`, nunca `float`.
**Telas e documentos.** Cadastro de apoio (classe cadastro), sem
relatório dedicado além de listagem cadastral (FIS-62).
**Critérios de aceite.** Conversão de unidade aplicada corretamente em
relatório de movimento de estoque por grupo.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma — item de baixa complexidade e baixa prioridade,
implementável junto de FIS-05 quando houver demanda.

### FIS-07 — Acumuladores: classificação fiscal versionada por vigência

**O que é.** O cadastro mais importante do módulo Fiscal — a peça que
fica **entre o documento e o resultado tributário**. Cada lançamento
(entrada, saída, serviço) recebe um acumulador, e é o acumulador que diz:
sobre o que a operação incide (faturamento, receita bruta, devolução),
quais impostos ela carrega, se dá direito a crédito, e quais contas
contábeis de débito/crédito a operação gera (FIS-09, FIS-18).
**Exemplo.** Um acumulador "Venda de Serviço de Consultoria" marcado com
"incide sobre Faturamento" e "incide sobre Receita Bruta", contendo os
impostos ISS e PIS/COFINS (quando aplicável ao regime da empresa). Toda
NFS-e de venda de consultoria usa esse acumulador; o sistema soma, no
fim do período, todo o valor lançado com este acumulador para compor a
base do PIS/COFINS "simplificado por nota" (Manual EFD Lucro Presumido,
p. 8-9).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 365-419
(cadastro de Acumuladores: guia Geral com "Incide sobre", guia Notas com
opções de cálculo, vigências) — Manual EFD Lucro Presumido, p. 2, 4, 8,
11 (o acumulador é o mesmo cadastro citado em cada ramo do fluxo).
**Fonte normativa.** Não há leiaute oficial de "acumulador" — é decisão
de arquitetura nossa, inspirada na rotina do manual, para implementar as
normas de PIS/COFINS (Leis 10.637/2002, 10.833/2003, 9.718/1998), ISS (LC
116/2003) e ICMS (legislação estadual, Ajuste SINIEF) de forma
versionada.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-03 (parâmetros da empresa determinam quais opções o
acumulador oferece), FIS-08 (impostos vinculados ao acumulador).
**Dados.** Nome, situação (ativo/inativo) com vigência, quadro "incide
sobre" (faturamento, receita bruta, devolução, retorno de remessa),
impostos vinculados (com suas contas contábeis — FIS-09), configuração de
PIS/COFINS por CST e natureza de receita (guia própria, usada no ramo
"simplificado por nota", Manual EFD Lucro Presumido p. 8).
**Regras.** Vigência obrigatória (AGENTS.md §10) — alterar acumulador
depois do início de uma vigência anterior pede confirmação explícita,
como o manual descreve (mensagem de confronto de período atual x início
de vigência); acumulador de devolução nunca soma na mesma base que
acumulador de venda (evita duplicar receita bruta).
**Telas e documentos.** Cadastro de acumulador (classe cadastro), usado
por todo lançamento e por vários relatórios de resumo (FIS-56).
**Critérios de aceite.** Um lançamento sem acumulador é recusado; a soma
por acumulador de um período bate com a soma dos lançamentos que o usam
(conciliação, RC-19); alterar acumulador não retroage a lançamento já
efetivado.
**Não copiar/riscos.** O cadastro do manual tem dezenas de flags
específicas de regime (Bares/Restaurantes, veículos usados, SCP,
FUNDOSOCIAL) que são **capacidades de nicho** — implementar apenas as
flags necessárias ao ramo "simplificado por nota" na primeira entrega
(FIS-30/31), e as demais só sob demanda medida.
**Perguntas.** Nenhuma bloqueante — a estrutura mínima (nome, incide
sobre, impostos vinculados, contas contábeis, vigência) é suficiente para
destravar FIS-13 e FIS-30. Detalhes de nicho ficam como perguntas
específicas dentro de cada regime (FIS-97).

### FIS-08 — Impostos e tabelas de alíquota por vigência

**O que é.** O cadastro de cada imposto que a empresa recolhe
(ICMS, IPI, ISS, PIS, COFINS, IRPJ, CSLL...), com suas alíquotas e regras
vigentes por período, e as contas contábeis de "a recolher" e "a
recuperar" de cada um — a segunda metade da amarração contábil descrita
em [mapa-funcional-contabil.md](../mapa-funcional-contabil.md#integração-fiscal--contábil-como-a-nota-vira-lançamento).
**Exemplo.** O imposto "PIS" cadastrado com alíquota 0,65% (regime
cumulativo — **valor ilustrativo, a confirmar na Lei 9.718/1998 art. 8º,
inciso I, e sua vigência**) vigente a partir de uma data, com conta
contábil "PIS a Recolher" para débito de apuração.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 419-447 e
1007-1011 (cadastro de Impostos, com vigências, convênios e protocolos).
**Fonte normativa.** Cada imposto tem fonte própria: ICMS (legislação
estadual + Convênio ICMS 85/2001 sobre arredondamento, já mapeado em
DE-010); ISS (LC 116/2003 + legislação municipal); PIS/COFINS (Leis
10.637/2002, 10.833/2003, 9.718/1998); IRPJ/CSLL (Lei 9.430/1996 e
Decreto 9.580/2018) — todas **a confirmar item a item antes de qualquer
alíquota entrar em código**, nunca por memória.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-03.
**Dados.** Código, nome, tipo (lançado/calculado — distinção que o manual
usa: "lançado" vem direto do documento, "calculado" é produto de apuração
como PIS/COFINS do Presumido), alíquota por vigência, conta contábil "a
recolher" e "a recuperar", histórico de lançamento (FIS-09).
**Regras.** Igual a FIS-07: vigência obrigatória, sem sobreposição;
mudança de alíquota nunca reprocessa período fechado sem ato explícito;
toda alíquota usada em cálculo carrega, na memória de cálculo, a fonte e
vigência aplicada (AGENTS.md §10).
**Telas e documentos.** Cadastro de imposto (classe cadastro).
**Critérios de aceite.** Apuração de um período usa **sempre** a alíquota
vigente na data de competência do lançamento, nunca a alíquota atual do
cadastro; teste de referência prova que dois lançamentos em vigências
diferentes usam alíquotas diferentes corretamente.
**Não copiar/riscos.** O manual lista dezenas de códigos de imposto
(1-ICMS, 2-IPI, 3-ISS... até códigos de 3 dígitos como 138, 139, 140,
141) — não é para copiar a numeração do concorrente; o DataLedger define
seu próprio identificador de imposto.
**Perguntas.** Quais impostos, exatamente, a carteira do Fred recolhe
hoje (ISS, PIS/COFINS cumulativo, e mais o quê)? Sem essa resposta, o
cadastro implementaria impostos sem uso real.

### FIS-09 — Configuração de históricos contábeis (modelo com variáveis)

**O que é.** O texto do lançamento contábil gerado pela integração fiscal
não é um texto fixo — é um **modelo com variáveis** (número da nota,
razão social do participante, série) que o sistema resolve no momento de
gerar o lançamento. Já confirmado do lado contábil em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md#o-histórico-é-modelo-não-texto):
*"histórico não é `CharField` copiado, é um serviço que resolve o modelo
no momento da geração"*.
**Exemplo.** Modelo de histórico "Venda de serviço conforme NFS-e nº
{numero_nota}, emitida em {data_emissao} para {nome_participante}"
resolvido, para a nota do exemplo de FIS-13, em "Venda de serviço
conforme NFS-e nº 000123, emitida em 15/09/2026 para Comércio XYZ Ltda.".
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 335-365
(configuração de históricos com variáveis por guia — ex.: guia Pedágio
lista "Nro. Da Nota", "Espécie", "Fornecedor - Razão").
**Fonte normativa.** Não há norma para o texto do histórico; é campo
livre do lançamento contábil, sujeito apenas às regras gerais de
escrituração contábil (a forma do lançamento em si, não o texto).
**Situação no DataLedger.** **Não existe** — `apps/contabilidade` hoje
recebe histórico como texto simples (`CharField`), sem resolução de
modelo.
**Depende de.** Nada dentro do Fiscal; é compartilhado com a
Contabilidade (plano `contabilidade.md`).
**Dados.** Modelo de texto com placeholders; lista de variáveis
disponíveis por tipo de movimento (nota de entrada, saída, serviço).
**Regras.** A resolução do modelo nunca falha silenciosamente — uma
variável sem valor disponível vira texto explícito (ex.: "(sem
participante)"), nunca campo vazio sem explicação.
**Telas e documentos.** Cadastro de modelo de histórico (classe
cadastro); usado dentro da prévia de lançamento (FIS-18).
**Critérios de aceite.** O mesmo modelo aplicado a duas notas diferentes
produz dois textos coerentes e diferentes, cada um rastreável até os
dados de origem (RC-19).
**Não copiar/riscos.** Nenhum — é a decisão de arquitetura, não a lista
de variáveis do concorrente.
**Perguntas.** Nenhuma bloqueante.

### FIS-10 — Convênios e protocolos de substituição tributária (ICMS-ST)

**O que é.** Cadastro dos acordos entre estados que definem quando um
produto tem ICMS retido antecipadamente pelo substituto tributário (ST).
Só é necessário quando a carteira do Fred tiver comércio interestadual de
mercadoria sujeita a ST — não é caso do acervo medido (85% NFS-e,
serviço, sem ICMS-ST).
**Exemplo.** Convênio ICMS sintético entre SP e MG para produto com MVA
(margem de valor agregado) de X% — **valor a confirmar em Convênio/Ajuste
específico do produto, nunca genérico**.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1007-1011.
**Fonte normativa.** Convênios e Protocolos ICMS publicados pelo CONFAZ,
específicos por produto/NCM e par de UFs — **a confirmar caso a caso**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-05 (NCM do produto), FIS-08 (imposto ICMS).
**Dados.** UFs de origem/destino, NCM, MVA, vigência.
**Regras.** Vigência obrigatória; nunca aplicar MVA sem confirmar o
convênio vigente para o par de UFs e o NCM exatos.
**Telas e documentos.** Cadastro (classe cadastro).
**Critérios de aceite.** Não aplicável até haver demanda confirmada.
**Não copiar/riscos.** Risco de inventar MVA — **proibido pelo
AGENTS.md §10**.
**Perguntas.** A carteira do Fred tem cliente com operação interestadual
sujeita a ICMS-ST? Se não, este item fica indefinidamente em espera (ver
FIS-97).

### FIS-11 — Tabelas de crédito presumido

**O que é.** Cadastro de benefícios fiscais que permitem calcular um
crédito de imposto (ICMS ou PIS/COFINS) presumido, sem a apuração
completa item a item — normalmente ligado a regime especial ou atividade
específica.
**Exemplo.** Crédito presumido de PIS/COFINS sobre determinada atividade,
com percentual **a confirmar em ato normativo específico do benefício**
antes de qualquer implementação.
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Acompanhamentos, "Demonstrativos de Créditos Acumulados" e "Demonstrativo
Crédito Presumido ICMS" (ver FIS-61).
**Fonte normativa.** Cada benefício tem ato normativo próprio (federal ou
estadual) — **nenhum valor deste item deve ser implementado sem a norma
específica confirmada**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-08.
**Dados.** Benefício, percentual, base de cálculo, vigência, fonte
normativa.
**Regras.** Igual a FIS-10: nunca aplicar percentual sem confirmar o ato
normativo vigente.
**Telas e documentos.** Cadastro (classe cadastro).
**Critérios de aceite.** Não aplicável até demanda confirmada.
**Não copiar/riscos.** Risco de inventar benefício fiscal — proibido.
**Perguntas.** A carteira do Fred usa algum crédito presumido hoje? Sem
resposta, este item fica fora do primeiro corte (ver FIS-97).

### FIS-12 — Contas e agências bancárias para guias e pagamentos

**O que é.** Cadastro dos dados bancários usados para emitir guias de
recolhimento (linha digitável, código de barras) e para registrar o
pagamento de imposto — a conta de onde sai o dinheiro.
**Exemplo.** Conta corrente sintética no banco X, agência Y, usada como
"conta padrão de pagamento de tributos" da empresa "Consultoria ABC
Ltda.".
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Cadastrais, "Agências" (p. 1921-1985, ver inventário) e as guias de
pagamento de impostos (p. 1542-1550) que referenciam banco/agência/conta.
**Fonte normativa.** Não há norma sobre o cadastro em si; a norma incide
sobre a **guia gerada** (ver FIS-59/60/61), não sobre o cadastro bancário
interno.
**Situação no DataLedger.** **Não existe.**
**Depende de.** Nada dentro do Fiscal — pode reaproveitar cadastro
bancário do escritório se um existir (a confirmar com Financeiro/
Honorários).
**Dados.** Banco, agência, conta, tipo de conta, empresa vinculada.
**Regras.** Dado sensível (não é segredo de autenticação, mas é dado
financeiro da empresa cliente) — mesma proteção de dado pessoal e
financeiro do AGENTS.md §11.
**Telas e documentos.** Cadastro (classe cadastro).
**Critérios de aceite.** Guia de recolhimento gerada referencia a conta
cadastrada corretamente, sem digitação manual repetida.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O DataLedger já tem ou vai ter um módulo financeiro do
escritório com cadastro bancário genérico? Se sim, este item deveria
reaproveitá-lo em vez de duplicar.

## Onda 2 — Escrituração de serviços a partir da NFS-e recebida

### FIS-13 — Lançamento fiscal da nota de serviço

**O que é.** O passo que falta entre "documento recebido" (FIS-01) e
"documento com efeito fiscal": transformar a `DocumentoFiscal` (NFS-e)
recebida em um **movimento de serviço** — vinculado a um acumulador
(FIS-07), com data de escrituração (que pode diferir da data de emissão,
ver regra abaixo) e pronto para entrar em apuração (FIS-23). É a peça
central da onda 2, priorizada porque **85% do acervo real é NFS-e**
(RC-66).
**Exemplo.** A NFS-e recebida na FIS-01 (Consultoria ABC → Comércio XYZ,
valor de serviço R$ 10.000,00, `tpRetISSQN` = "2" retido pelo tomador)
recebe o acumulador "Venda de Serviço de Consultoria" (FIS-07). O
lançamento fiscal registra: valor do serviço R$ 10.000,00; ISS retido
conforme alíquota municipal vigente **a confirmar na legislação do
município específico** (LC 116/2003 fixa só o teto de 5% e o piso de 2%,
art. 8º-A — o valor exato depende do município); data de escrituração
igual à data de emissão (regra do manual, salvo documento extemporâneo).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1049-1284
(menu Movimentos, notas de Entradas/Saídas/Serviços — estrutura de guias
e o campo Acumulador); p. 1051 (regra de que a apuração considera a data
de entrada/escrituração, não a de emissão, salvo documento
extemporâneo).
**Fonte normativa.** LC 116/2003 (ISS, fato gerador e retenção) e
legislação do município específico para alíquota — **a confirmar por
município atendido**.
**Situação no DataLedger.** **Não existe** — a recepção (FIS-01) grava o
documento fiscal, não o lançamento/movimento.
**Depende de.** FIS-01, FIS-03, FIS-04, FIS-07.
**Dados.** Referência ao `DocumentoFiscal` de origem (nunca duplicar
dado, só referenciar); acumulador; data de escrituração; situação
(rascunho/efetivado, distinção obrigatória pelo AGENTS.md §10).
**Regras.** Um `DocumentoFiscal` cancelado (situação "cancelada",
FIS-02) nunca gera lançamento fiscal novo, e um lançamento já gerado a
partir de documento que depois é cancelado precisa de rotina de
estorno rastreável (não apagar); data de escrituração segue a regra do
manual (competência = data de entrada, salvo extemporâneo) **como
hipótese de rotina, não confirmada como norma** — a norma real do
ISS/PIS/COFINS usa competência de fato gerador, que pode ou não
coincidir; reimportar/reprocessar a mesma nota nunca duplica o
lançamento (mesma chave natural de FIS-01).
**Telas e documentos.** Tela de lançamento de serviço, com prévia do
lançamento contábil (FIS-18) — classe conferência antes de efetivar.
**Critérios de aceite.** Uma NFS-e válida com acumulador definido gera
exatamente um lançamento fiscal; uma NFS-e cancelada não gera lançamento
novo; dois lançamentos com débito/crédito de acumuladores diferentes não
se confundem na apuração do período.
**Não copiar/riscos.** Não copiar a estrutura de guias/telas do manual —
usar API e templates próprios (direção de arte do produto).
**Perguntas.** O escritório precisa editar manualmente algum dado do
lançamento antes de efetivar (ex.: corrigir acumulador sugerido
automaticamente), ou o acumulador é sempre escolhido manualmente pelo
usuário no momento do lançamento? Muda a interface de FIS-13.

### FIS-14 — Retenção do ISSQN interpretada no lançamento

**O que é.** Hoje a recepção (FIS-01) **lê e exibe** o código
`tpRetISSQN` (RC-110: `1` não retido, `2` retido pelo tomador, `3` retido
pelo intermediário), mas não o interpreta. Este item fecha essa lacuna:
o lançamento fiscal (FIS-13) usa o código para decidir se o ISS entra
como "a recolher pelo prestador" ou como "retido, já recolhido pelo
tomador" — o que muda a base de apuração e a conta contábil de destino.
**Exemplo.** Retomando o exemplo de FIS-13 (`tpRetISSQN` = "2"): o
lançamento fiscal registra o ISS como retido pelo tomador — não entra no
"ISS a recolher" da Consultoria ABC, mas fica registrado para
conferência (o tomador deveria ter emitido comprovante de retenção,
FIS-93, fora de escopo por ora).
**Referência de rotina.** Não há página específica no manual de 2018
para `tpRetISSQN` — é campo do leiaute nacional de NFS-e, posterior ao
manual. Ver o próprio achado RC-110.
**Fonte normativa.** Esquemas XSD oficiais do Portal Nacional da NFS-e,
`tiposComplexos_v1.01.xsd` (tipo `TSTipoRetISSQN`) — já confirmada
(RC-110); a **consequência contábil** da retenção depende de LC 116/2003
art. 6º (responsabilidade por retenção) — **a confirmar por município**.
**Situação no DataLedger.** **Não existe** — `tp_ret_issqn` é campo
gravado e exibido, nunca interpretado (comentário explícito em
`models.py`).
**Depende de.** FIS-13.
**Dados.** Reaproveita `DocumentoFiscal.tp_ret_issqn`.
**Regras.** `tpRetISSQN = "1"` (não retido) soma ao "ISS a recolher" do
prestador; `"2"` e `"3"` **não** somam (o recolhimento é de terceiro) mas
ficam registrados para conferência.
**Telas e documentos.** Parte da tela de lançamento (FIS-13); aparece no
demonstrativo de retenções (FIS-52).
**Critérios de aceite.** Uma nota com `tpRetISSQN = "2"` não aparece na
guia de ISS a pagar do prestador (FIS-61), mas aparece no relatório de
retenções sofridas.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — a regra dos três códigos já está
confirmada em fonte oficial (RC-110); falta só implementar o efeito.

### FIS-15 — Conferência de lançamentos antes do fechamento do período

**O que é.** Uma tela que reúne, por período, todos os lançamentos
fiscais pendentes de revisão — a etapa que o escritório roda antes de
apurar (FIS-23), para pegar nota sem acumulador, nota com dado
suspeito, nota duplicada por engano de classificação.
**Exemplo.** Antes de apurar setembro, o Fred abre a conferência e vê 3
notas sem acumulador definido e 1 nota marcada "conferida = não" — corrige
as 3 e confirma a 4ª antes de rodar a apuração.
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção Utilitários
(menu 6), "Conferência de Lançamentos" (inventário, faixa 1987-2284);
também o campo "Conferido" no lançamento de entrada (p. 1052).
**Fonte normativa.** Não há norma específica — é controle de qualidade
interno do escritório, mas apoia a obrigação de exatidão da escrituração
(dever geral de escrituração correta).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-13.
**Dados.** Flag "conferido" por lançamento; lista de pendências
(sem acumulador, sem participante identificado, valor zerado).
**Regras.** Lançamento não conferido pode entrar na apuração (a
conferência é conveniência, não bloqueio hoje) — **decisão de produto a
confirmar com o Fred**: se deve ser bloqueio ou aviso.
**Telas e documentos.** Tela de conferência (classe conferência).
**Critérios de aceite.** A tela lista 100% dos lançamentos do período sem
acumulador ou com dado incompleto, sem falso negativo.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Conferência deve **bloquear** a apuração do período
(como a Contabilidade já faz para débito ≠ crédito) ou é só aviso? Decisão
de produto do Fred.

### FIS-16 — Alteração em massa de classificação fiscal

**O que é.** Corrigir o acumulador (ou outro campo) de várias notas de
uma vez, em vez de editar uma a uma — útil quando um lote inteiro foi
lançado com a classificação errada.
**Exemplo.** 40 notas de setembro foram lançadas com o acumulador "Venda
de Mercadoria" por engano, quando deveriam usar "Venda de Serviço de
Consultoria". O escritório filtra as 40 e troca o acumulador de todas de
uma vez, com registro de auditoria de cada alteração.
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Utilitários, "Alterar Notas" (Entradas/Saídas/Serviços, inventário
6.9-6.14) e "Alterar Movimento de Produtos das Notas".
**Fonte normativa.** Não há norma específica; é operação de correção de
escrituração, sujeita à regra geral de correção rastreável (AGENTS.md
§10) — nunca de lançamento **já efetivado** sem procedimento próprio.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-13, FIS-15.
**Dados.** Seleção de lançamentos por filtro; campo(s) a alterar; motivo
da alteração (trilha).
**Regras.** Alteração em massa de lançamento **rascunho** é livre;
alteração de lançamento **efetivado e já integrado à contabilidade**
segue o mesmo procedimento de correção rastreável de FIS-20 — nunca
edição silenciosa; toda alteração em massa gera **um registro de trilha
por lançamento alterado**, não um registro agregado que esconda o
antes/depois individual.
**Telas e documentos.** Tela de alteração em massa (classe conferência).
**Critérios de aceite.** Alterar 40 lançamentos gera 40 registros de
trilha, cada um com valor anterior e novo; lançamento efetivado e
conciliado não é alterado sem o procedimento de FIS-20.
**Não copiar/riscos.** O manual permite alteração em massa sem
diferenciar rascunho de efetivado — **aqui a diferenciação é
obrigatória** (AGENTS.md §10), é onde deliberadamente divergimos.
**Perguntas.** Nenhuma bloqueante.

### FIS-17 — Notas não lançadas (relatório de pendência de escrituração)

**O que é.** Relatório que cruza os documentos **recebidos** (FIS-01) com
os **lançados** (FIS-13) e mostra a diferença: documentos que chegaram
mas ainda não viraram lançamento fiscal — a lista de trabalho pendente do
escritório.
**Exemplo.** Setembro tem 480 NFS-e recebidas; 470 já têm lançamento
fiscal; o relatório mostra as 10 restantes, com motivo provável (sem
participante identificável, sem acumulador escolhido ainda).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1795-1798
aproximadamente (seção Acompanhamentos, "Notas Não Lançadas" — Saídas e
Serviços).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.** O embrião é a consulta de
FIS-02, que já mostra o que foi recebido — falta cruzar com o que foi
lançado.
**Depende de.** FIS-01, FIS-13.
**Dados.** Diferença entre `DocumentoFiscal` recebidos e lançamentos
fiscais criados a partir deles.
**Regras.** O relatório nunca omite documento por erro de junção — antes
de apurar um período, **toda** nota recebida deve aparecer como "lançada"
ou "pendente", nunca "desconhecida".
**Telas e documentos.** Relatório de conferência (classe conferência).
**Critérios de aceite.** Soma de "lançadas" + "pendentes" = total de
documentos recebidos no período, sempre.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

## Onda 3 — Integração contábil e de honorários

### FIS-18 — Prévia do lançamento contábil na nota

**O que é.** No momento de lançar a nota (FIS-13), o sistema monta — mas
não efetiva — o lançamento contábil correspondente, com base nas contas
do acumulador (FIS-07) e do imposto (FIS-08), para que o usuário confira
**antes** de a contabilidade ser tocada. É "a aba Contabilidade da tela do
Fred" descrita em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md#dois-momentos-não-um).
**Exemplo.** Continuando o exemplo de FIS-13/FIS-14: a prévia mostra
débito "Clientes a Receber" R$ 10.000,00 e crédito "Receita de Serviços"
R$ 10.000,00, mais o lançamento de ISS retido (memorando, sem afetar
caixa da Consultoria ABC, já que o tomador reteve).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 335-365
(históricos) e a lógica de "aba Contabilidade" descrita em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md).
**Fonte normativa.** Não aplicável ao mecanismo em si — a norma incide
sobre o **lançamento contábil final** (NBC TG estrutura conceitual e
partidas dobradas, já tratado no módulo Contabilidade).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-07, FIS-09, FIS-13.
**Dados.** Lançamento contábil em rascunho, vinculado ao lançamento
fiscal de origem, editável até a efetivação (FIS-19).
**Regras.** A prévia nunca escreve na contabilidade efetivada
diretamente — é sempre rascunho até a integração em lote (FIS-19); editar
a prévia manualmente marca o lançamento como "alterado à mão", campo
próprio (não inferido, ver a divergência deliberada registrada em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md#o-que-não-foi-possível-confirmar)).
**Telas e documentos.** Aba/seção "Contabilização" dentro da tela de
lançamento fiscal (classe conferência).
**Critérios de aceite.** A prévia soma débito = crédito sempre (mesma
regra de partida dobrada, ainda em rascunho); editar a prévia não afeta
nenhum saldo contábil real até a efetivação.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-19 — Integração contábil em lote por período, com regeração controlada

**O que é.** A rotina que efetiva, em lote, os lançamentos contábeis
represados como prévia (FIS-18) — normalmente rodada uma vez por período,
depois de a escrituração fiscal estar conferida (FIS-15).
**Exemplo.** No dia 5 de outubro, o Fred roda a integração contábil de
setembro: 470 lançamentos fiscais (notas de serviço já lançadas) geram
470 lançamentos contábeis efetivados de uma vez, cada um rastreável até a
`DocumentoFiscal` de origem.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1550-1552
(menu Movimentos, "Integração Contábil": período, opções de
agrupamento, botão Gerar, tela de conferência dos lançamentos antes de
gravar).
**Fonte normativa.** Não aplicável ao mecanismo; a norma incide sobre o
lançamento contábil gerado (mesma base do módulo Contabilidade).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-18, e o módulo Contabilidade (`criar_lancamento`, já
pronto e auditado).
**Dados.** Nada novo — usa `DocumentoFiscal`/lançamento fiscal como
origem e grava em `Lancamento` da Contabilidade.
**Regras.** Regeração de um período **preserva por padrão** lançamento
alterado à mão e lançamento já conciliado — ao contrário do sistema de
referência, em que essas duas proteções são **opção** do usuário, aqui
são **padrão**, e desligar exige ato explícito (divergência deliberada,
já registrada em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md#a-regeração-e-o-que-faremos-diferente));
período contábil encerrado **recusa** integração, nunca só avisa (RC-57);
duplicidade impedida por chave natural (documento de origem + tipo), não
por confiança na rotina não rodar duas vezes.
**Telas e documentos.** Tela de integração contábil por período (classe
conferência) — mostra os lançamentos antes de gravar, igual ao manual (p.
1552, "Lançamentos Gerados").
**Critérios de aceite.** Rodar a integração duas vezes seguidas no mesmo
período não duplica nenhum lançamento contábil; período encerrado recusa
com mensagem clara; lançamento conciliado nunca é regenerado sem ato
explícito.
**Não copiar/riscos.** **Divergência deliberada do manual** (ver acima) —
documentá-la é o próprio propósito deste item, não um risco.
**Perguntas.** Nenhuma bloqueante — a divergência já foi decidida em
[mapa-funcional-contabil.md](../mapa-funcional-contabil.md).

### FIS-20 — Exclusão/estorno de nota já contabilizada

**O que é.** O procedimento para quando uma nota que já gerou lançamento
contábil efetivado precisa ser removida (ex.: cancelamento chegou depois
da integração) — nunca apagar o lançamento contábil em silêncio.
**Exemplo.** A NFS-e do exemplo de FIS-13 é cancelada por evento (RC-70)
depois de já ter sido integrada à contabilidade de setembro. O sistema
oferece, como **escolha explícita**, estornar o lançamento contábil
gerado — sujeito às mesmas regras de período aberto e não conciliado que
qualquer estorno contábil.
**Referência de rotina.** [mapa-funcional-contabil.md](../mapa-funcional-contabil.md#exclusão-de-nota-contabilizada)
já registra a rotina do manual e a decisão de convergência.
**Fonte normativa.** Não aplicável ao mecanismo; a norma incide sobre a
imutabilidade do lançamento contábil efetivado (mesma base do módulo
Contabilidade, já auditada: "estorno único e rastreável").
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-19, e o mecanismo de estorno já pronto na
Contabilidade.
**Dados.** Nada novo — usa o estorno já existente, vinculado ao
lançamento fiscal de origem.
**Regras.** Nunca implícito — excluir a nota **nunca** exclui o
lançamento contábil junto sem confirmação explícita; período fechado e
lançamento conciliado bloqueiam o estorno, como qualquer outro (RC-57).
**Telas e documentos.** Diálogo de confirmação na tela de detalhe da nota
(classe conferência).
**Critérios de aceite.** Cancelar uma nota já integrada nunca apaga o
lançamento contábil sem confirmação explícita do usuário; o estorno,
quando confirmado, é rastreável até a nota cancelada.
**Não copiar/riscos.** Nenhum — já é a divergência deliberada.
**Perguntas.** Nenhuma bloqueante.

### FIS-21 — Mapa/relatório de integração contábil

**O que é.** O relatório de conferência que mostra, para um período, quais
lançamentos fiscais já foram integrados à contabilidade, quais estão
pendentes, e o resumo por conta contábil — a "prova" de que a integração
rodou certo.
**Exemplo.** Relatório de setembro mostra: 470 lançamentos integrados,
somando R$ 10.000.000,00 de débito e R$ 10.000.000,00 de crédito
(conferência de igualdade), 10 pendentes (mesmos da FIS-17).
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Acompanhamentos, "Contábeis" (Lançamentos, Mapa para Integração, Resumo
Contábil — inventário faixa 1619-1675).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-19.
**Dados.** Lançamentos fiscais x lançamentos contábeis gerados, por
período.
**Regras.** Débito = crédito sempre no resumo (é o mesmo "Fecha / Não
fecha" que a Contabilidade já calcula — reaproveitar, não duplicar
lógica).
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** O resumo do período bate exatamente com a soma
dos lançamentos contábeis gerados pela integração daquele período.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-22 — Integração com Honorários

**O que é.** Gera, no módulo Honorários (fora de escopo deste documento),
variáveis de cobrança a partir do valor de impostos apurados no Fiscal —
por exemplo, cobrar um percentual sobre o imposto apurado, ou repassar
taxa de parcelamento.
**Exemplo.** A apuração de setembro calcula ISS a recolher de R$
2.000,00 (valor sintético); a integração gera, no Honorários, um evento
de cobrança "taxa de apuração fiscal" vinculado a esse valor, conforme
regra de cobrança **a definir pelo plano de Honorários**.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1553-1554
(menu Movimentos, "Integração Honorários": evento vinculado, valor,
botão Gerar).
**Fonte normativa.** Não aplicável — é regra de negócio do próprio
escritório, não norma fiscal.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23 (apuração calculada), e o módulo Honorários
(plano próprio, fora deste documento).
**Dados.** Evento de cobrança, valor de origem (referência ao imposto
apurado), competência.
**Regras.** Nunca duplica cobrança ao rodar duas vezes para o mesmo
período (idempotência, AGENTS.md §8); a variável de cobrança é sempre
rastreável até o imposto apurado que a originou.
**Telas e documentos.** Tela de integração (classe conferência), lado
Fiscal; o lançamento de cobrança em si pertence ao plano de Honorários.
**Critérios de aceite.** Rodar a integração duas vezes no mesmo período
não duplica o evento de cobrança.
**Não copiar/riscos.** Nenhum.
**Perguntas.** O modelo de cobrança de honorários (fixo, percentual sobre
imposto, por evento) já está definido em algum lugar? Se não, este item
depende do plano de Honorários definir o contrato primeiro.

## Onda 4 — Apuração, Simples Nacional e Lucro Presumido/EFD Contribuições

### FIS-23 — Apuração de impostos do período

**O que é.** O motor que, para um período (mês), soma todos os
lançamentos fiscais classificados por acumulador e imposto, e produz o
resultado: quanto cada imposto tem de base, débito, crédito e saldo a
recolher — com **memória de cálculo** rastreável até cada lançamento de
origem (AGENTS.md §10).
**Exemplo.** Setembro: acumulador "Venda de Serviço de Consultoria" soma
R$ 500.000,00 de receita bruta. Para PIS (regime cumulativo, ramo
"simplificado por nota" — FIS-31), a base é R$ 500.000,00 e a alíquota é
**a da tabela vigente do art. 8º da Lei 9.718/1998 — a confirmar**
(ilustrativamente, um valor histórico de 0,65% daria R$ 3.250,00 de PIS;
este número **não deve entrar em código sem confirmação**).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1509-1522
(menu Movimentos, "Apuração": período, opções, botão "Processa período",
janela de resultado por imposto, botão "Detalhamento" para abrir a
memória de cálculo por nota).
**Fonte normativa.** Depende do imposto: PIS/COFINS (Leis 10.637/2002,
10.833/2003, 9.718/1998); ISS (LC 116/2003 + município); ICMS (legislação
estadual) — cada apuração implementada precisa confirmar a fonte do
imposto específico antes de codificar a fórmula.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-07, FIS-08, FIS-13, FIS-14.
**Dados.** Resultado por imposto e período: base, débito, crédito,
isentas, outras, saldo; vínculo de cada linha aos lançamentos que a
compõem (memória de cálculo).
**Regras.** Toda apuração é **reprodutível**: rodar duas vezes sobre os
mesmos lançamentos produz o mesmo resultado (determinismo, AGENTS.md
§11: "cálculos oficiais devem vir do motor determinístico"); apuração de
período fechado exige reabertura explícita (RC-57); arredondamento
sempre explícito por regra do imposto (DE-010 — nunca padrão global).
**Telas e documentos.** Tela de apuração com detalhamento por
crédito/débito de entradas e saídas (classe conferência/demonstração,
dependendo do relatório final gerado — ver FIS-49).
**Critérios de aceite.** A soma da base de um imposto no período bate
exatamente com a soma dos lançamentos que usam acumulador vinculado a
esse imposto; reprocessar o mesmo período produz resultado idêntico
byte a byte na memória de cálculo.
**Não copiar/riscos.** Não inventar fórmula de nenhum imposto — cada
imposto implementado precisa de caso de referência e validação
profissional (AGENTS.md §10).
**Perguntas.** Qual é o **primeiro** imposto a implementar de ponta a
ponta — ISS (mais simples, unitário por município do prestador) ou
PIS/COFINS (mais impactante, mas depende de FIS-30/31 primeiro)?

### FIS-24 — Consulta de apuração com rastreio ao documento de origem

**O que é.** Depois de apurado (FIS-23), o escritório precisa conseguir
"entrar" no valor apurado e ver de onde ele veio — clicar em "ISS a
recolher de setembro: R$ 2.000,00" e ver a lista de notas que compõem
esse valor.
**Exemplo.** O Fred clica no ISS apurado de setembro e vê as 470 notas de
serviço, cada uma com seu valor de ISS, batendo no total.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1512-1515
("Detalhamento Apuração", botão "Selecionar" para filtrar por competência
e imposto).
**Fonte normativa.** Não aplicável — é conferência interna; apoia a
exigência geral de que relatório concilie com o lançamento de origem
(RC-19).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23.
**Dados.** Nenhum novo — é consulta sobre a memória de cálculo de
FIS-23.
**Regras.** A soma do detalhamento sempre bate com o total apurado —
qualquer divergência é defeito, nunca "arredondamento esperado" sem
explicação visível.
**Telas e documentos.** Tela de detalhamento (classe conferência).
**Critérios de aceite.** Clicar em qualquer valor apurado sempre abre a
lista de lançamentos de origem, sem exceção.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-25 — Parcelamento de impostos (geral e trimestral)

**O que é.** Registro de parcelamento de um imposto já apurado e não
pago no vencimento — divide o valor em parcelas, com juros e multa, e
gera a guia e o lançamento contábil de cada parcela.
**Exemplo.** IRPJ trimestral apurado em R$ 6.750,00 (valor sintético),
parcelado em 3 quotas de R$ 2.250,00 — **o manual descreve, como regra de
rotina do concorrente, não confirmada como norma nossa, que parcela abaixo
de R$ 2.000,00 é ajustada automaticamente**; qualquer piso de parcela real
precisa vir de norma oficial do parcelamento (Lei 9.430/1996 art. 5º, §1º,
para IRPJ trimestral — **a confirmar**), não do manual.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1526-1541
(menu Movimentos, "Parcelamento de Impostos Trimestrais" e "Parcelamento
de Impostos": seleção de impostos, guia Parcelas, guia Contabilidade com
lançamento do parcelamento).
**Fonte normativa.** Lei 9.430/1996 art. 5º §1º (parcelamento trimestral
de IRPJ/CSLL do Lucro Presumido) — **a confirmar valor mínimo de
parcela vigente**; para outros tributos, cada norma de parcelamento é
própria (ex.: Lei 10.522/2002 para parcelamento ordinário federal).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23, FIS-08.
**Dados.** Imposto parcelado, valor principal, multa, juros, número de
parcelas, vencimentos, lançamento contábil de cada parcela.
**Regras.** Nunca inventar o valor mínimo de parcela ou a fórmula de
juros/multa sem fonte oficial confirmada; cada parcela gera lançamento
contábil rastreável (FIS-19).
**Telas e documentos.** Tela de parcelamento (classe conferência),
gerando guia (FIS-59/60/61).
**Critérios de aceite.** Soma das parcelas geradas bate com o valor
principal + juros + multa informados; nenhuma parcela é gerada com valor
mínimo inventado.
**Não copiar/riscos.** O exemplo de piso de R$ 2.000,00 é rotina do
concorrente, citada só para ilustrar a mecânica — **não deve virar
constante no código sem a norma correspondente confirmada**.
**Perguntas.** A carteira do Fred usa parcelamento de imposto hoje? Se
sim, de quais tributos, para dimensionar a prioridade deste item.

### FIS-26 — Pagamento de impostos com baixa e lançamento contábil

**O que é.** Registrar que um imposto apurado (ou uma parcela) foi pago,
baixando o valor em aberto e gerando o lançamento contábil da saída de
caixa.
**Exemplo.** O ISS de setembro (R$ 2.000,00) é pago em 10/10/2026; o
sistema baixa o valor e gera lançamento contábil: débito "ISS a
Recolher" R$ 2.000,00, crédito "Caixa/Bancos" R$ 2.000,00.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1542-1550
(menu Movimentos, "Pagamento de Impostos": período, quadro de impostos
em aberto, geração do lançamento contábil do pagamento).
**Fonte normativa.** Não aplicável ao mecanismo — norma incide sobre a
guia paga (ver FIS-59/60/61) e sobre a contabilização em si (já tratada
no módulo Contabilidade).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23, FIS-12 (conta de onde sai o pagamento).
**Dados.** Referência ao imposto/parcela apurado; data de pagamento;
valor pago (pode ser parcial); lançamento contábil gerado.
**Regras.** Pagamento parcial não fecha o saldo em aberto; pagamento
nunca duplica lançamento contábil ao ser registrado duas vezes por
engano (idempotência).
**Telas e documentos.** Tela de pagamento (classe conferência).
**Critérios de aceite.** Pagar um imposto integralmente zera o saldo em
aberto; pagar parcialmente reduz o saldo pelo valor exato pago.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-27 — Simples Nacional: receita bruta acumulada (RBT12) e apuração por anexo

**O que é.** Para empresa do Simples Nacional, o cálculo do imposto
depende da **receita bruta acumulada dos últimos 12 meses (RBT12)**, que
define a faixa e, junto com o anexo de atividade, a alíquota efetiva
(fórmula do "Simples Nacional por faixas", desde a LC 155/2016).
**Exemplo.** RBT12 hipotético de R$ 1.200.000,00 (dentro da 2ª faixa do
Anexo III, **a confirmar em qual anexo a atividade real se enquadra**) —
a fórmula geral é `(RBT12 × alíquota nominal da faixa − parcela a
deduzir) / RBT12`, com **alíquota nominal e parcela a deduzir da tabela
vigente do anexo aplicável, a confirmar em fonte oficial antes de
codificar** (LC 123/2006, Anexos I a V, com redação dada pela LC
155/2016).
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Acompanhamentos, "Simples Nacional - Receita Bruta Global Acumulada" (p.
1875 aproximadamente, inventário faixa 1619-1675).
**Fonte normativa.** LC 123/2006, arts. 3º (definição de RBT12) e 18
(tabelas dos Anexos I a V) — **a confirmar redação vigente e anexo
aplicável à atividade de cada cliente antes de implementar a fórmula**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-03 (regime = Simples Nacional), FIS-23 (base é a
receita apurada mês a mês).
**Dados.** Receita bruta mensal, RBT12 (janela móvel de 12 meses), anexo
de enquadramento, faixa resultante, alíquota efetiva calculada.
**Regras.** RBT12 é sempre **janela móvel de 12 meses**, recalculada a
cada mês; troca de faixa não retroage a meses já apurados (regra do
próprio Simples Nacional: alíquota efetiva do mês usa o RBT12 daquele
mês).
**Telas e documentos.** Relatório de RBT12 (classe conferência) e a
apuração em si (classe demonstração, ligada à guia DAS — FIS-28).
**Critérios de aceite.** RBT12 de um mês bate com a soma exata dos 12
meses anteriores; a alíquota efetiva calculada bate com a fórmula da
LC 123/2006 para um caso de referência confirmado com o Fred ou fonte
oficial.
**Não copiar/riscos.** **Proibido** codificar tabela de alíquota nominal
ou parcela a deduzir sem confirmar a redação vigente — a LC 123/2006 já
sofreu alterações relevantes (LC 155/2016) e pode sofrer novas com a
Reforma Tributária (LC 214/2025, regime de transição do Simples).
**Perguntas.** Quais anexos (I a V) e quais atividades a carteira do Fred
realmente usa no Simples Nacional? Sem isso, não dá para saber quantas
tabelas de alíquota o sistema precisa suportar de fato.

### FIS-28 — Simples Nacional: geração e parcelamento da guia DAS

**O que é.** A partir do valor apurado (FIS-27), gerar a guia única do
Simples Nacional (DAS) para pagamento, e permitir parcelar débitos de DAS
em aberto.
**Exemplo.** DAS de setembro gerado com o valor apurado pela alíquota
efetiva de FIS-27, vencimento no dia 20 do mês seguinte (regra de rotina
do Simples Nacional — **prazo a confirmar na Resolução CGSN vigente**).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1875-1909
aproximadamente (menu Relatórios, Guias, Federais, "DAS": guias
Identificação, Período, Receita Bruta Total, Valores Fixos, Segregação de
Receitas, Folha de Salários, Valor Apurado) e "DAS Parcelamento".
**Fonte normativa.** LC 123/2006 e Resolução CGSN vigente sobre prazo de
recolhimento e leiaute do DAS — **a confirmar**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-27, FIS-12.
**Dados.** Valor apurado, vencimento, código de barras/linha digitável
(se gerado localmente ou via integração com o PGDAS-D — **a confirmar se
haverá integração com o serviço oficial ou só cálculo interno de
conferência**).
**Regras.** O DataLedger **não substitui** a transmissão oficial da
declaração do Simples Nacional (PGDAS-D) sem confirmação explícita de
que fará essa integração — por ora, item de **cálculo e conferência**,
não de transmissão oficial (que exigiria aprovação explícita de usuário
autorizado, AGENTS.md §11).
**Telas e documentos.** Guia DAS (classe guia).
**Critérios de aceite.** O valor da guia gerada bate exatamente com o
valor apurado em FIS-27, sem arredondamento inventado.
**Não copiar/riscos.** Não implementar geração de guia com validade
jurídica de recolhimento sem confirmar que o leiaute/algoritmo do
código de barras está correto contra fonte oficial (Banco Central/
Receita Federal) — risco de gerar guia inválida.
**Perguntas.** O DataLedger vai transmitir a declaração ao PGDAS-D via
integração oficial, ou só calcular e exibir para o escritório digitar
manualmente no portal? Decide o escopo real deste item.

### FIS-29 — Lucro Presumido: parâmetros do PIS/COFINS (regime e forma de cálculo)

**O que é.** Os dois parâmetros que abrem o fluxo da EFD Contribuições no
Lucro Presumido (detalhado na seção dedicada, mais abaixo): **regime de
apuração** (competência ou caixa) e **forma de cálculo** (completo,
simplificado por produto, simplificado por nota). Tecnicamente já é parte
de FIS-03 (parâmetros fiscais da empresa) — este item isola a
**validação de combinação válida** entre os dois campos, porque nem toda
combinação existe: regime de caixa só admite forma "simplificado"
(nunca "completo").
**Exemplo.** Tentar salvar parâmetro com regime "caixa" e forma
"completo" é recusado — a combinação não existe no domínio (Manual EFD
Lucro Presumido, p. 11: "no campo Forma de Cálculo, poderá selecionar
somente a opção Simplificado").
**Referência de rotina.** Manual EFD Lucro Presumido, p. 1-2 (fluxograma
completo) e p. 11 (regime de caixa restringe a forma).
**Fonte normativa.** Lei 9.718/1998 art. 2º (regime de caixa opcional
para o Lucro Presumido, remissão à legislação do imposto de renda) — **a
confirmar redação vigente**; Instrução Normativa RFB sobre regime de
caixa — **a confirmar**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-03.
**Dados.** Reaproveita os campos de FIS-03; regra de validação é a
novidade.
**Regras.** Regime "caixa" + forma "completo" é combinação **inválida**,
recusada na gravação do parâmetro, nunca silenciosamente convertida para
outra combinação.
**Telas e documentos.** Parte da tela de parâmetros (FIS-03).
**Critérios de aceite.** As quatro combinações válidas (competência
completo; competência simplificado por produto; competência simplificado
por nota; caixa simplificado por produto; caixa simplificado por nota —
cinco, na verdade, contando os dois sub-tipos do caixa) são aceitas; a
combinação inválida é recusada com mensagem clara.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — a regra já está confirmada no
próprio manual (rotina), suficiente para a validação de combinação (que
não é norma tributária, é regra de forma do cálculo).

### FIS-30 — EFD Contribuições: regime de competência, simplificado por nota

**O que é.** O ramo **prioritário** do fluxo da EFD Contribuições para o
DataLedger (ver seção dedicada abaixo): PIS/COFINS calculados
**diretamente do acumulador** aplicado ao valor da nota, sem exigir
cadastro de produto — o ramo que menos exige e que combina com o acervo
real do escritório (quase todo NFS-e, RC-66).
**Exemplo.** Retomando FIS-13: a nota de R$ 10.000,00, lançada com o
acumulador "Venda de Serviço de Consultoria" — que carrega, na sua
configuração de PIS/COFINS (guia "PIS/COFINS", sub-guia "Saídas"), um CST
e uma alíquota — gera PIS e COFINS calculados sobre R$ 10.000,00 pela
alíquota configurada no **acumulador**, não no produto. Se a alíquota
configurada for a cumulativa clássica (0,65% + 3%, **valores a confirmar
na Lei 9.718/1998 art. 8º e sua vigência**), o resultado ilustrativo
seria PIS R$ 65,00 e COFINS R$ 300,00 — **números só para ilustrar a
mecânica, nunca para codificar sem confirmação**.
**Referência de rotina.** Manual EFD Lucro Presumido, p. 8-10
(Procedimento 1.2.2: parâmetros, configuração do acumulador na guia
"PIS/COFINS" por CST/natureza de receita/alíquota, lançamento de saída/
entrada/serviço/redução Z usando esse acumulador).
**Fonte normativa.** Leis 10.637/2002 e 10.833/2003 (regime não
cumulativo) e Lei 9.718/1998 (regime cumulativo, aplicável à maior parte
do Lucro Presumido) — **a confirmar qual regime de PIS/COFINS (cumulativo
ou não cumulativo) se aplica à atividade de cada cliente**: em geral,
Lucro Presumido é cumulativo, mas há exceções por atividade que exigem
confirmação.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-07 (acumulador com configuração de PIS/COFINS),
FIS-08, FIS-13, FIS-29.
**Dados.** Configuração de PIS/COFINS por acumulador (CST, natureza da
receita, alíquota); resultado por lançamento e por período.
**Regras.** Nunca aplica alíquota sem a configuração explícita do
acumulador (nunca um valor "padrão" do sistema); CST e natureza de
receita seguem tabela oficial (Guia Prático EFD Contribuições) — **a
confirmar tabela vigente**.
**Telas e documentos.** Parte da apuração (FIS-23); relatório específico
é o "espelho do PIS/COFINS" (FIS-51).
**Critérios de aceite.** Uma nota de serviço com acumulador configurado
gera exatamente o PIS e o COFINS esperados para o CST e alíquota
cadastrados, com memória de cálculo até a nota; nota sem acumulador
configurado para PIS/COFINS não entra na base (ou é recusada — **decisão
de produto a confirmar**).
**Não copiar/riscos.** Não copiar tabela de CST/natureza de receita do
manual sem checar contra o Guia Prático EFD Contribuições oficial
vigente — o manual é de 2018 e a tabela pode ter mudado.
**Perguntas.** Confirmar com o Fred: os clientes de Lucro Presumido da
carteira estão todos no regime cumulativo clássico (0,65%/3%), ou há
exceção de atividade com regime não cumulativo mesmo no Presumido?

### FIS-31 — EFD Contribuições: regime de competência, simplificado por produto

**O que é.** Um degrau acima de FIS-30 em exigência: ainda dispensa a
granularidade completa do não cumulativo, mas já usa o **cadastro de
produto** (FIS-05) para definir CST e natureza de receita — necessário
quando a empresa também vende mercadoria (não só presta serviço) e quer
tributar por produto, não por acumulador genérico.
**Exemplo.** Uma empresa de Lucro Presumido que vende mercadoria lança
uma nota de saída com 3 produtos; cada produto tem, no seu cadastro, CST
e alíquota de PIS/COFINS próprios (configurados na guia "PIS/COFINS" do
produto); o sistema soma o PIS/COFINS de cada item da nota.
**Referência de rotina.** Manual EFD Lucro Presumido, p. 4-7 (Procedimento
1.2.1: parâmetros, cadastro de produto com CST/natureza de receita,
acumuladores de venda/devolução/serviço, lançamentos de saída/entrada/
serviço/redução Z com botão "Gerar conforme movimentação de produtos").
**Fonte normativa.** Mesma base de FIS-30 (Leis 10.637/2002, 10.833/2003,
9.718/1998) — a diferença é a granularidade (por produto, não por nota
inteira), não a norma em si.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-05, FIS-07, FIS-13, FIS-29, FIS-39 (movimento de
produto/estoque, já que este ramo lê a guia "Estoque" do lançamento).
**Dados.** Configuração de PIS/COFINS por produto e por vigência
(FIS-05); resultado por item de nota.
**Regras.** Idem FIS-30 quanto a nunca aplicar alíquota sem configuração
explícita; soma dos itens de uma nota bate com o total da nota.
**Telas e documentos.** Parte da apuração (FIS-23) e do lançamento de
entrada/saída (FIS-36/38).
**Critérios de aceite.** Nota com múltiplos produtos calcula PIS/COFINS
item a item corretamente, com memória de cálculo até o item.
**Não copiar/riscos.** Mesmo risco de FIS-30 quanto a tabela de CST.
**Perguntas.** A carteira do Fred tem cliente de Presumido que vende
mercadoria (não só serviço)? Se não, este item fica atrás de FIS-30 e
FIS-36/38 na fila real.

### FIS-32 — EFD Contribuições: completo (regime de competência, por item/estoque)

**O que é.** O ramo mais exigente do regime de competência: cálculo
item a item igual ao do Lucro Real, a partir do cadastro de produto com
tributação por vigência e **exigindo controle de estoque completo**
(Manual EFD Lucro Presumido, p. 2: *"o sistema terá o mesmo comportamento
que é realizado para empresas do Lucro Real"*).
**Exemplo.** Empresa de Presumido com atividade industrial/comercial
robusta, controle de estoque ativo, calcula PIS/COFINS por movimentação
de produto igual a uma empresa de Lucro Real — fora do escopo do acervo
medido hoje (85% NFS-e, sem produto).
**Referência de rotina.** Manual EFD Lucro Presumido, p. 2-3 (Procedimento
1.1: parâmetros exigindo controle de estoque, cadastro de produto com
vínculo entre CST de entrada e saída, lançamentos via guias "Estoque" e
"Itens").
**Fonte normativa.** Mesma base de FIS-30/31, aplicada com a
granularidade máxima — **a confirmar se algum cliente da carteira
realmente precisa deste ramo antes de implementar**, dado o esforço x
demanda.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-05, FIS-39, FIS-40 (todo o controle de estoque
completo), e efetivamente as mesmas bases do Lucro Real (fora do escopo
medido).
**Dados.** Idêntico ao Lucro Real: CST por vigência, vínculo
entrada-saída, base por item.
**Regras.** Mesma disciplina de vigência e não inventar alíquota.
**Telas e documentos.** Parte da apuração; sem relatório distinto de
FIS-32/33.
**Critérios de aceite.** Não aplicável até demanda confirmada.
**Não copiar/riscos.** Maior risco de esforço desperdiçado — implementar
antes de FIS-30/31 seria inverter a ordem de valor por esforço.
**Perguntas.** Existe cliente de Presumido na carteira que exija este
ramo? Se a resposta for não, este item fica **explicitamente adiado**
(não é "fora de escopo": é onda 4, mas último a entrar dentro dela).

### FIS-33 — EFD Contribuições: regime de caixa

**O que é.** No regime de caixa, o fato gerador do PIS/COFINS deixa de
ser a emissão da nota e passa a ser o **recebimento** — exige contas a
receber, uma parcela em toda nota (mesmo à vista), e a base é
**proporcional ao valor efetivamente recebido**, com a informação de
PIS/COFINS "levada" da guia do lançamento para a baixa da parcela.
**Exemplo.** Nota de serviço de R$ 10.000,00 emitida em setembro,
recebida em duas parcelas: R$ 6.000,00 em setembro e R$ 4.000,00 em
outubro. O PIS/COFINS da parcela de setembro é calculado sobre R$
6.000,00 (60% da base), e o da parcela de outubro sobre R$ 4.000,00 —
**nunca sobre o valor total da nota de uma vez**, ao contrário do regime
de competência.
**Referência de rotina.** Manual EFD Lucro Presumido, p. 11-22
(Procedimentos 2.1.1 e 2.1.2: parâmetros exigindo "Controlar Contas a
pagar e receber", acumulador marcando "Gerar Parcelas nas notas",
lançamento com guia "Parcelas", botão "Gerar Parcelas", tela "Base de PIS
e COFINS por Parcela" acessível na baixa de cada parcela).
**Fonte normativa.** Lei 9.718/1998 art. 2º (opção pelo regime de caixa)
e a legislação/IN RFB que disciplina a apuração proporcional ao
recebimento — **a confirmar**.
**Situação no DataLedger.** **Não existe** — depende de "contas a
receber", que também **não existe** no DataLedger hoje
(confirmado em [mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#o-que-isso-diz-ao-dataledger)).
**Depende de.** FIS-29 (parâmetro = regime caixa), FIS-41 (baixas e
parcelas — que por sua vez não existe ainda), e um módulo de contas a
receber que este plano **não** cobre (pertence ao Financeiro/
Contabilidade, fora de escopo direto do Fiscal).
**Dados.** Parcela da nota; valor recebido por parcela; base de
PIS/COFINS por parcela (proporcional ao recebido).
**Regras.** A base de cada parcela é sempre proporcional ao valor
efetivamente recebido, nunca ao valor total da nota; nota sem parcela
lançada não entra na base do regime de caixa (regra do próprio manual:
*"para que a nota seja considerada [...] esta deverá ter as parcelas
lançadas [...], independente do tipo de operação"*).
**Telas e documentos.** Parte do lançamento e da baixa de parcela
(FIS-41); classe conferência.
**Critérios de aceite.** A soma da base de PIS/COFINS de todas as
parcelas de uma nota bate exatamente com o valor total da nota, quando
todas as parcelas forem recebidas.
**Não copiar/riscos.** Risco de subestimar o esforço: este ramo depende
de uma peça inteira (contas a receber) que não existe — **não
implementar antes de FIS-41 e da base de contas a receber estarem
prontas**.
**Perguntas.** A carteira do Fred tem cliente de Presumido no regime de
caixa? Dado que o achado do mapa funcional já apontou o regime de caixa
como o de maior esforço/menor retorno imediato, esta resposta decide se
FIS-33 entra nesta onda ou é adiado para depois de FIS-42.

### FIS-34 — Geração do arquivo digital da EFD Contribuições

**O que é.** Depois de os ramos de cálculo (FIS-30 a FIS-33) estarem
prontos, gerar o arquivo SPED da EFD Contribuições — o formato de
entrega da obrigação à Receita Federal.
**Exemplo.** Arquivo `.txt` de setembro, codificado conforme leiaute
oficial, com os blocos correspondentes ao PIS/COFINS apurado no período.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1791-1856
aproximadamente (seção Informativos, Federais, "EFD Contribuições":
Outros Dados, guias C181/C185, C191/C195, C481/C485, C491/C495,
C870/C880, F100, F500/F510, F550/F560, M115/M515, M225/M625, M400/M800,
M410/M810, Bloco P).
**Fonte normativa.** **Guia Prático da EFD Contribuições**, versão
vigente, publicado no Portal SPED — leiaute, registros e regras de
validação **a obter na versão vigente**, nunca por memória do manual de
2018 (que já está desatualizado em leiaute).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-30, FIS-31 (no mínimo um ramo de cálculo pronto),
FIS-08.
**Dados.** Estrutura de registros do leiaute SPED (blocos 0, A, C, D, F,
M, P, 1, 9 — a confirmar quais são obrigatórios para Lucro Presumido
simplificado).
**Regras.** O arquivo gerado nunca é transmitido automaticamente à
Receita Federal sem aprovação explícita de usuário autorizado
(AGENTS.md §11 — obrigação oficial); a geração é sempre reprodutível a
partir da mesma apuração (mesmo período, mesmo arquivo byte a byte,
salvo campo de data/hora de geração).
**Telas e documentos.** Geração de arquivo (classe arquivo regulatório).
**Critérios de aceite.** O arquivo gerado valida contra o validador
oficial do SPED (PVA — Programa Validador e Assinador) para um caso de
referência **antes de ser oferecido como funcional**.
**Não copiar/riscos.** **Risco maior deste item**: leiaute errado gera
arquivo que a Receita Federal rejeita, ou pior, aceita com dado errado —
exige validação com o PVA oficial antes de qualquer entrega ao Fred como
"pronto".
**Perguntas.** Nenhuma bloqueante para o **cálculo** (FIS-30 a FIS-33);
a **geração do arquivo** em si só deve começar depois de o Fred confirmar
que o escritório efetivamente vai transmitir a EFD Contribuições pelo
DataLedger (e não só usar o cálculo como conferência de outro sistema).

## Onda 5 — NF-e de entrada e saída

### FIS-35 — Importação de XML de NF-e (fatia 2 da DL-010)

**O que é.** A leitura da NF-e (modelo 55), 11% do acervo real (RC-65),
que hoje o leitor **reconhece e recusa explicitamente** (`"tipo ainda não
suportado: NF-e"`) — fatia 2 já planejada em
[DL-010](../../planos/DL-010-recepcao-de-documentos-fiscais.md#leiaute-da-nf-e--levantado-em-fonte-oficial-não-presumida),
com leiaute levantado em fonte oficial (XSD vigente, pacote `PL_010f`).
**Exemplo.** Um ZIP com 611 NF-e de saída (o perfil real medido, RC-65) é
enviado; cada uma é lida pela raiz `nfeProc`, com chave de acesso de 44
posições extraída de `NFe/infNFe/@Id`.
**Referência de rotina.** Não aplicável — leiaute é de fonte oficial, não
do manual (que é de 2018, quando a NF-e já existia mas o pacote XSD
vigente é de 2026).
**Fonte normativa.** Manual de Orientação do Contribuinte versão 7.0 e
esquemas XSD do Portal Nacional da NF-e, pacote vigente `PL_010f`
(31/08/2026) — já confirmados em
[DL-010](../../planos/DL-010-recepcao-de-documentos-fiscais.md#o-que-está-confirmado).
**Situação no DataLedger.** **Não existe** — só recusa explícita e
identificada (`leitor.py`).
**Depende de.** A mesma infraestrutura de FIS-01 (deduplicação, isolamento,
eventos), estendida para o novo tipo de documento.
**Dados.** Chave de acesso (44 posições); emitente/destinatário (CNPJ ou
CPF, desde o leiaute 4.00); número, série, modelo; valor total
(`total/ICMSTot/vNF`); protocolo de autorização.
**Regras.** As cinco armadilhas já documentadas em DL-010 valem
integralmente: `dest` é opcional no esquema (nota sem destinatário
identificado não é malformada); evento (cancelamento, CC-e, manifestação)
compartilha namespace mas tem raiz distinta; leiaute 3.10 ou anterior deve
ser recusado com mensagem específica (não erro genérico); cancelamento
não altera o XML da nota original — só o evento separado revela a
situação real.
**Telas e documentos.** Mesma tela de recepção de FIS-01, estendida
(classe conferência).
**Critérios de aceite.** Mesmos 22 critérios de DL-010, adaptados para
NF-e; teste específico com nota sem `dest` (não deve ser recusada como
malformada).
**Não copiar/riscos.** Idênticos aos já documentados em DL-010 —
reaproveitar, não reescrever.
**Perguntas.** Nenhuma bloqueante — leiaute já levantado e confirmado.

### FIS-36 — Lançamento de nota de entrada

**O que é.** Transformar a NF-e de entrada recebida (FIS-35) em
movimento fiscal — o mesmo papel que FIS-13 cumpre para NFS-e, mas para
compra de mercadoria/insumo, com produto (FIS-05) e estoque (FIS-39).
**Exemplo.** NF-e de compra de mercadoria no valor de R$ 5.000,00,
lançada com acumulador "Compra para Revenda", gerando entrada de estoque
de 100 unidades do produto "Notebook X" a R$ 50,00 cada.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1049-1052
(menu Movimentos, "Notas de Entradas": guia Entradas, campos de
importação da NF-e do portal, regra de competência pela data de
entrada, não de emissão).
**Fonte normativa.** Não aplicável ao mecanismo em si; a norma incide
sobre os impostos calculados a partir da entrada (ICMS, IPI — cada um
com fonte própria, ver FIS-08).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-35, FIS-04, FIS-05, FIS-07.
**Dados.** Referência à NF-e de origem; acumulador; produtos e
quantidades (guia Estoque); data de escrituração (= data de entrada,
salvo documento extemporâneo, mesma regra hipotética de FIS-13).
**Regras.** Mesma disciplina de rascunho/efetivado e idempotência de
FIS-13.
**Telas e documentos.** Tela de lançamento de entrada (classe
conferência).
**Critérios de aceite.** Uma NF-e de entrada com acumulador e produtos
definidos gera exatamente um lançamento fiscal e as movimentações de
estoque correspondentes.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-37 — Lançamento de nota de saída

**O que é.** Equivalente de FIS-36 para venda de mercadoria — a NF-e de
saída (o tipo mais comum de NF-e no acervo real: 611 de 618, RC-65) vira
movimento fiscal.
**Exemplo.** NF-e de venda de mercadoria no valor de R$ 8.000,00, com
acumulador "Venda de Mercadoria", baixando 50 unidades do produto
"Notebook X" do estoque.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1284-1345
aproximadamente (menu Movimentos, "Notas de Saídas": mesma estrutura de
Entradas, com campos de frete/seguro/despesas acessórias).
**Fonte normativa.** Idem FIS-36 — a norma incide sobre os impostos
calculados, não sobre o mecanismo de lançamento.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-35, FIS-04, FIS-05, FIS-07, FIS-39.
**Dados.** Idêntico a FIS-36, no sentido inverso (saída de estoque).
**Regras.** Idêntico a FIS-36.
**Telas e documentos.** Tela de lançamento de saída (classe conferência).
**Critérios de aceite.** Idêntico a FIS-36, adaptado a saída.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-38 — Devolução vinculada à nota de origem

**O que é.** Lançamento de devolução (de compra ou de venda), que
precisa referenciar a nota original para reaproveitar CST, alíquota e
acumulador corretos — nunca recalcular do zero, conforme o próprio
manual descreve para o CST de devolução ("12-Devolução de Vendas Sujeitas
à Incidência Não-Cumulativa").
**Exemplo.** Devolução de R$ 1.000,00 de uma venda de R$ 8.000,00 (FIS-37)
— o CST e a alíquota de PIS/COFINS da devolução são os **mesmos** da nota
de venda original, buscados automaticamente pelo vínculo, nunca
digitados de novo.
**Referência de rotina.** Manual EFD Lucro Presumido, p. 5-6 (a guia
"Estoque" da entrada de devolução traz CST fixo "99" e busca a nota
devolvida pelo produto e CNPJ do fornecedor).
**Fonte normativa.** Mesma base tributária da nota original — a
devolução não é fato gerador novo, é estorno do fato gerador anterior
(regra geral de PIS/COFINS/ICMS, cada um com sua fonte já citada em
FIS-08).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-36, FIS-37.
**Dados.** Referência obrigatória à nota original devolvida; valor e
quantidade devolvidos (nunca maior que o valor/quantidade da nota
original).
**Regras.** Devolução nunca supera o valor/quantidade ainda não devolvido
da nota original (controle cumulativo de devoluções parciais).
**Telas e documentos.** Parte da tela de entrada/saída (classe
conferência).
**Critérios de aceite.** Uma devolução usa exatamente o CST/alíquota da
nota original, sem exigir nova digitação; duas devoluções parciais somadas
nunca superam o total da nota original.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-39 — Controle de estoque e movimentação de produtos

**O que é.** O saldo de cada produto por empresa, atualizado por entrada
(compra) e saída (venda), necessário para os ramos "completo" e
"simplificado por produto" da EFD Contribuições (FIS-31, FIS-32) e para
qualquer relatório de estoque (FIS-63).
**Exemplo.** Produto "Notebook X": saldo inicial 0, +100 unidades
(FIS-36), -50 unidades (FIS-37), saldo final 50 unidades.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1405-1509
aproximadamente (seção Movimento, "Estoque"); e p. 2793-2942 (seção
Relatórios/Estoque: Movimento Individual do Produto, Movimento por Grupo,
Bloco K).
**Fonte normativa.** Bloco K do SPED Fiscal (controle de produção e de
estoque), regulado pelo Ajuste SINIEF e Guia Prático EFD ICMS/IPI vigente
— **a confirmar obrigatoriedade e vigência para o porte/atividade dos
clientes atendidos**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-05, FIS-36, FIS-37, FIS-38.
**Dados.** Saldo por produto/empresa/período; movimentações (entrada,
saída, devolução, ajuste).
**Regras.** Saldo nunca fica negativo sem sinalização explícita (aviso,
não necessariamente bloqueio — **decisão de produto a confirmar**); saldo
de um período fechado não é alterado retroativamente sem procedimento
rastreável.
**Telas e documentos.** Relatórios de movimento de estoque (classe
conferência, ver FIS-63).
**Critérios de aceite.** Saldo final de um produto bate exatamente com
saldo inicial + entradas − saídas − devoluções, sempre.
**Não copiar/riscos.** Nenhum.
**Perguntas.** A carteira do Fred tem cliente comercial/industrial com
controle de estoque relevante, ou é majoritariamente prestador de
serviço (como sugere RC-66)? Decide a prioridade real deste item frente
às ondas de serviço.

### FIS-40 — Cupom fiscal, Redução Z e Resumo de Movimento Diário

**O que é.** Documentos de varejo (cupom fiscal/redução Z, equipamento
ECF ou SAT) e de transporte (Resumo de Movimento Diário) — volumes de
movimento agregados por dia, não documento a documento.
**Exemplo.** Redução Z de um equipamento em determinado dia, totalizando
R$ 3.000,00 em vendas, detalhada por situação tributária de ICMS.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1345-1405
aproximadamente (menu Movimentos, Reduções Z — Modelo 2D) e p. 1660-1663
(Resumo Movimento Diário, seção Acompanhamentos).
**Fonte normativa.** Convênio ICMS/legislação estadual sobre equipamento
emissor de cupom fiscal e SAT — **a confirmar por UF**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-07, FIS-39.
**Dados.** Totais por situação tributária, por equipamento, por dia.
**Regras.** Idêntico em disciplina a FIS-36/37 (rascunho/efetivado,
idempotência).
**Telas e documentos.** Tela de lançamento (classe conferência).
**Critérios de aceite.** Não aplicável até demanda confirmada — **é
capacidade de varejo, fora do perfil medido do acervo (85% serviço)**.
**Não copiar/riscos.** Nenhum.
**Perguntas.** A carteira do Fred tem cliente de varejo com cupom fiscal
ou SAT? Se não, este item fica no fim da fila real de implementação.

### FIS-41 — Baixas e parcelas de contas a pagar/receber vinculadas ao documento

**O que é.** O parcelamento de uma nota (à vista ou a prazo) e a baixa de
cada parcela — necessário tanto para conferência financeira quanto,
criticamente, para o **regime de caixa** da EFD Contribuições (FIS-33),
que usa a data de baixa da parcela como fato gerador.
**Exemplo.** Nota de venda de R$ 10.000,00 dividida em 2 parcelas de R$
5.000,00; a primeira é baixada (recebida) em 30 dias, a segunda em 60.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1509
aproximadamente ("Baixas e parcelas" no inventário de Movimento) e
Manual EFD Lucro Presumido, p. 12-13, 16, 22 (guia "Parcelas", botão
"Gerar Parcelas", baixa por menu Movimentos/Baixas).
**Fonte normativa.** Não aplicável ao mecanismo — norma incide sobre o
efeito tributário da baixa no regime de caixa (já tratado em FIS-33).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-36, FIS-37, um módulo de contas a pagar/receber
(fora de escopo direto deste plano, mas referenciado como dependência
explícita — ver [mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#o-que-isso-diz-ao-dataledger)).
**Dados.** Parcela (número, vencimento, valor); baixa (data, valor
recebido/pago, forma).
**Regras.** Soma das parcelas de uma nota sempre bate com o valor total
da nota; baixa parcial não fecha a parcela.
**Telas e documentos.** Tela de parcelas e baixas (classe conferência).
**Critérios de aceite.** Gerar parcelas de uma nota de R$ 10.000,00 em 2
parcelas produz exatamente 2 parcelas de R$ 5.000,00 cada (ou com
diferença de centavo tratada por regra explícita de arredondamento,
DE-010).
**Não copiar/riscos.** Nenhum.
**Perguntas.** Este módulo de contas a pagar/receber é do Fiscal, do
Financeiro do escritório, ou compartilhado com Honorários? Decisão de
arquitetura que cabe ao `arquiteto-senior`, fora do escopo deste
documento — aqui só se registra a dependência.

### FIS-42 — Importação por formato de documento (NFC-e, CF-e, CT-e, BP-e, NFS-e municipais anteriores)

**O que é.** Cada tipo de documento fiscal eletrônico tem leiaute
próprio, e o manual mostra que o sistema de referência trata cada um com
um fluxo de importação equivalente (resumo dos dados, registros a
gravar, advertências, erros, críticas de estrutura, relacionamento de
produtos) — o mesmo padrão que a DL-010 já aplica à NFS-e nacional.
**Exemplo.** Uma CT-e (conhecimento de transporte) de entrada, 9 no
acervo real (RC-65, todas de entrada), é importada com o mesmo rigor de
deduplicação e isolamento de FIS-01.
**Referência de rotina.** Manual Domínio Escrita Fiscal, seção
Utilitários, "Importação Padrão" (inventário 6.22.2: NF-e, NFC-e, CF-e,
NFS-e ABRASF, NFS-e Paulistana, CT-e/CT-eOS, BP-e — cada um com
sub-fluxo idêntico de resumo/erros/advertências).
**Fonte normativa.** Cada leiaute tem fonte oficial própria: NFC-e
(modelo 65, mesmo esquema NF-e); CT-e (Ajuste SINIEF, manual do
contribuinte do CT-e); BP-e (bilhete de passagem eletrônico, Ajuste
SINIEF específico) — **a confirmar leiaute vigente de cada um antes de
implementar**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** A mesma infraestrutura de FIS-01/FIS-35, estendida por
tipo.
**Dados.** Um leitor por tipo de documento (mesmo padrão de
`apps/fiscal/leitor.py`).
**Regras.** Mesma disciplina de FIS-01: classificação pelo conteúdo
(elemento raiz), nunca pelo nome do arquivo; deduplicação por
identificador emitido por terceiro confiável.
**Telas e documentos.** Mesma tela de recepção, estendida (classe
conferência).
**Critérios de aceite.** Cada novo tipo de documento implementado segue
os mesmos 22 critérios de DL-010, adaptados.
**Não copiar/riscos.** Nenhum copiado — só o **padrão de fluxo**
(resumo/erros/advertências) é reaproveitado como inspiração de UX, nunca
telas ou texto.
**Perguntas.** Pela composição do acervo (RC-65: NFCom 69, CT-e 9, GTVe 1
— juntos 1% do movimento, de poucos emitentes), qual desses tipos
realmente vale a pena implementar antes de outros itens de maior
volume? Este item é explicitamente de **baixa prioridade relativa**.

### FIS-43 — Segmentos especializados (referência, não implementação)

**O que é.** O manual cobre segmentos de negócio muito específicos:
combustíveis (bombas, bicos, tanques), empreendimentos imobiliários,
sociedade em conta de participação (SCP), produção de usina, bilhetes de
passagem. Este item existe só para **registrar a referência e a decisão
de não implementar sem demanda**, evitando que um desenvolvedor tropece
nessas telas do manual e ache que são parte do escopo.
**Exemplo.** Não aplicável — item de referência.
**Referência de rotina.** Manual Domínio Escrita Fiscal, várias seções
espalhadas (cadastro de Bombas/Bicos/Tanques p. 2169-2223; Imóveis p.
2080-2101; SCP em várias telas de parcelamento e guias).
**Fonte normativa.** Cada segmento tem legislação própria e específica
(ANP para combustíveis; legislação de incorporação imobiliária para
empreendimentos) — **não se aplica sem cliente real no segmento**.
**Situação no DataLedger.** **Não existe, e não deve existir sem
demanda medida** — já registrado como decisão em
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#2-movimentos--a-escrituração):
*"Segmentos especializados que o material cobre e que **não** devem
entrar sem demanda real"*.
**Depende de.** Nada — é item de **não fazer**, não de fundação.
**Dados.** Não aplicável.
**Regras.** Não aplicável.
**Telas e documentos.** Não aplicável.
**Critérios de aceite.** Não aplicável.
**Não copiar/riscos.** O risco real é o **oposto** de outros itens:
implementar segmento de nicho sem demanda desperdiça esforço que falta
para o que 85% do acervo precisa (RC-66).
**Perguntas.** A carteira do Fred atende algum desses segmentos hoje? Se
sim, qual, para abrir um item próprio no momento certo.

## Onda 6 — Livros fiscais

Os cinco itens abaixo pertencem à **classe livro** (a mais restrita das
três classes descritas em
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md#1-a-descoberta-que-reorganiza-o-problema-são-três-classes-de-documento)):
forma, numeração, termos e assinaturas são prescritos por norma, não por
escolha do escritório — a personalização de layout fica quase inteira
fora do bloco obrigatório.

### FIS-44 — Livro de Registro de Entradas

**O que é.** O livro fiscal que registra, dia a dia, as notas de entrada
do período — a versão "impressa/formal" do que FIS-36 lançou.
**Exemplo.** Livro de setembro, com cada NF-e de entrada lançada em
ordem cronológica, mostrando CFOP, valor contábil e base/valor de
ICMS/IPI.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1559-1564
(menu Relatórios, Livros, "Livros Fiscais": guia Geral com opção
"Registro de Entradas", quadro "Anexar" com relação de emitentes).
**Fonte normativa.** Convênio SINIEF s/n de 1970 e Ajuste SINIEF vigente
sobre livros fiscais — **a confirmar redação vigente do leiaute do Livro
de Registro de Entradas**, que hoje é majoritariamente substituído pela
EFD ICMS/IPI digital (a impressão em papel pode já não ser obrigatória
para a maioria dos contribuintes — **a confirmar em fonte oficial, não
presumir pelo manual de 2018**).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-36, e a apuração de ICMS (dentro de FIS-23) para o
resumo do período.
**Dados.** Notas de entrada do período, em ordem cronológica, com os
totalizadores exigidos pelo leiaute.
**Regras.** O livro é imutável para o período encerrado — igual à
Contabilidade, reabertura exige controle explícito (RC-57); numeração de
página/folha sequencial e sem furo.
**Telas e documentos.** Livro (classe livro — forma prescrita).
**Critérios de aceite.** Duas emissões do mesmo período e mesmos dados
produzem o mesmo conteúdo, byte a byte no que for determinístico
(excluindo carimbo de emissão).
**Não copiar/riscos.** Não copiar layout do manual — mas a **forma
prescrita por norma** (que não é do manual, é da legislação) precisa ser
seguida à risca, ao contrário de um relatório de conferência.
**Perguntas.** O livro de registro de entradas em papel ainda é exigido
para os regimes/UFs da carteira do Fred, ou a EFD ICMS/IPI digital já o
substitui integralmente? Pergunta que só a fonte oficial (ou o próprio
Fred, por prática do escritório) responde.

### FIS-45 — Livro de Registro de Saídas

**O que é.** Equivalente de FIS-44 para notas de saída.
**Exemplo.** Livro de setembro com as NF-e de saída em ordem
cronológica.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1559-1564
(mesma janela "Livros Fiscais", opção "Registro de Saídas").
**Fonte normativa.** Mesma base de FIS-44.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-37, apuração de ICMS.
**Dados.** Idêntico a FIS-44, para saídas.
**Regras.** Idêntico a FIS-44.
**Telas e documentos.** Livro (classe livro).
**Critérios de aceite.** Idêntico a FIS-44.
**Não copiar/riscos.** Idêntico a FIS-44.
**Perguntas.** Idêntico a FIS-44.

### FIS-46 — Livros de Registro de Apuração (ICMS, IPI, ISS)

**O que é.** Os livros que consolidam, por período, o resultado da
apuração de cada imposto (FIS-23) na forma exigida pela legislação —
agrupados aqui porque compartilham a mesma estrutura e dependência.
**Exemplo.** Livro de Apuração do ISS de setembro, mostrando débito,
crédito (se houver) e saldo a recolher, batendo com a guia gerada
(FIS-61).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1559-1564
(opções "Registro de ICMS", "Registro de IPI", "Registro de ISS" na
mesma janela "Livros Fiscais").
**Fonte normativa.** Legislação estadual (ICMS), Regulamento do IPI
(RIPI, Decreto 7.212/2010) e legislação municipal (ISS) — cada um com
leiaute próprio de livro, **a confirmar por regime/UF/município**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23 (apuração calculada de cada imposto).
**Dados.** Resultado da apuração do imposto no período, formatado
conforme o leiaute legal.
**Regras.** Imutável para período encerrado; bate exatamente com a
apuração de FIS-23 (nunca reprocessa valor diferente).
**Telas e documentos.** Livro (classe livro).
**Critérios de aceite.** O saldo do livro bate exatamente com o saldo
apurado em FIS-23 para o mesmo imposto e período.
**Não copiar/riscos.** Idêntico a FIS-44.
**Perguntas.** Quais desses três livros (ICMS, IPI, ISS) a carteira do
Fred efetivamente precisa? A maioria dos clientes (85% NFS-e, prestador
de serviço) provavelmente só precisa do livro de ISS, se algum.

### FIS-47 — Livro de Registro de Inventário

**O que é.** O livro que registra o estoque físico da empresa ao fim de
cada período/exercício — depende do controle de estoque (FIS-39).
**Exemplo.** Inventário de 31/12, listando cada produto com quantidade e
valor unitário/total.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1559-1564
(opção "Registro de Inventário", com variante para empreendimentos
imobiliários — fora de escopo, ver FIS-43).
**Fonte normativa.** Regulamento do Imposto de Renda (Decreto
9.580/2018) e legislação estadual de ICMS sobre inventário — **a
confirmar vigência e obrigatoriedade por regime**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-39.
**Dados.** Saldo de cada produto na data de referência, com valor.
**Regras.** Reflete exatamente o saldo calculado em FIS-39 na data de
corte, sem ajuste manual não rastreado.
**Telas e documentos.** Livro (classe livro).
**Critérios de aceite.** O total do inventário bate com a soma dos
saldos de FIS-39 na data de corte.
**Não copiar/riscos.** Idêntico a FIS-44.
**Perguntas.** Idêntico a FIS-39 quanto à prioridade real (depende de
haver cliente com estoque relevante).

### FIS-48 — Termos de abertura e encerramento dos livros fiscais

**O que é.** O texto formal, com forma prescrita, que abre e encerra
cada livro fiscal — a mesma exigência de forma que
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md)
já documentou para o livro Diário/Razão da Contabilidade (NBC ITG 2000
(R1)), aqui aplicada aos livros fiscais.
**Exemplo.** Termo de abertura do Livro de Registro de Entradas de 2026,
com identificação da empresa, número de folhas, e assinatura do
responsável.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1562-1564
(guia Termos: seleção de livro, Termo de Abertura com modelo e data,
Termo de Encerramento com data do exercício social).
**Fonte normativa.** Legislação fiscal estadual/municipal sobre
autenticação e forma dos livros — **a confirmar**; para livro contábil
equivalente já se usa NBC ITG 2000 (R1), mas o livro **fiscal** segue
norma tributária própria, não contábil.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-44 a FIS-47 (qualquer um deles, para ter o que
encerrar).
**Dados.** Identificação da empresa, período/exercício, número de
folhas, dados de autenticação (quando exigida pela UF).
**Regras.** Forma quase totalmente prescrita — a personalização
disponível é a mesma "margem para encadernação" já registrada como
capacidade de mercado em
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md#22-adotar-com-cuidado--úteis-mas-mexem-em-mais-do-que-parece).
**Telas e documentos.** Termo (classe livro).
**Critérios de aceite.** O termo gerado contém todos os elementos
obrigatórios da norma aplicável, sem omissão.
**Não copiar/riscos.** Não copiar o modelo textual do manual — mas
seguir a **forma legal**, que não é opção de produto.
**Perguntas.** Qual UF define a exigência de autenticação de livro
fiscal para os clientes atendidos? Cada estado pode ter regra própria.

## Onda 7 — Demonstrativos de apuração

Os quatro itens abaixo pertencem à **classe demonstração** (a
intermediária): têm bloco obrigatório fixado por norma, mas alguma
liberdade fora dele.

### FIS-49 — Demonstrativo de apuração por imposto

**O que é.** O relatório que mostra, para um imposto e período, a
memória de cálculo completa — base, débito, crédito, saldo — de forma
apresentável e imprimível, distinto da tela de consulta interativa
(FIS-24).
**Exemplo.** Demonstrativo de ISS de setembro, mostrando a base de R$
500.000,00, alíquota aplicada (a confirmar por município), valor devido,
retenções deduzidas (FIS-14) e saldo a recolher.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1596-1619
(menu Relatórios, Impostos, "Demonstrativos": opções "Detalhar por
acumulador", "Detalhar por nota", "Detalhar por CFOP").
**Fonte normativa.** Não há leiaute único fixado por norma para este
demonstrativo em si (diferente do livro) — mas o **conteúdo** (base,
alíquota, valor) precisa refletir a norma do imposto específico (ver
FIS-08).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23.
**Dados.** Nenhum novo — é apresentação da memória de cálculo de FIS-23.
**Regras.** Concilia exatamente com FIS-23 e FIS-24 — três telas, um
número, sempre (RC-19).
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** O valor final do demonstrativo bate exatamente
com o valor apurado em FIS-23.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-50 — Demonstrativo do Simples Nacional

**O que é.** Versão do demonstrativo (FIS-49) específica para Simples
Nacional, mostrando RBT12, faixa, alíquota efetiva e valor do DAS — o
"PGDAS-D de conferência" do escritório.
**Exemplo.** Demonstrativo de setembro para a empresa do Simples,
mostrando RBT12 (FIS-27), anexo/faixa, alíquota efetiva calculada e
valor do DAS gerado (FIS-28).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1885-1920
aproximadamente (dentro da janela DAS, botão "Outros Dados", tela
"PGDAS").
**Fonte normativa.** LC 123/2006 — mesma base de FIS-27/FIS-28.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-27, FIS-28.
**Dados.** Nenhum novo.
**Regras.** Concilia exatamente com FIS-27/FIS-28.
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** Bate exatamente com o valor apurado em FIS-27.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-51 — Espelho do PIS/COFINS (EFD Contribuições) por CST/natureza de receita

**O que é.** O relatório que mostra o resultado do PIS/COFINS agrupado
por CST e natureza de receita — o "espelho" do que vai para o arquivo
digital (FIS-34), útil para conferência antes da transmissão.
**Exemplo.** Espelho de setembro mostrando, por CST "01 - Operação
Tributável com Alíquota Básica", base de R$ 500.000,00 e PIS/COFINS
calculados conforme FIS-30/31.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1609-1614
(opções "Detalhar por acumulador"/"Detalhar por nota" para os impostos
PIS/COFINS, no relatório de Demonstrativos).
**Fonte normativa.** Guia Prático da EFD Contribuições, versão vigente —
o agrupamento por CST/natureza de receita é exatamente a estrutura dos
registros M400/M410 (PIS) e M800/M810 (COFINS) do próprio leiaute
digital.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-30, FIS-31 (ou ambos).
**Dados.** Nenhum novo.
**Regras.** Bate exatamente com FIS-30/31 e, quando existir, com o
arquivo gerado em FIS-34.
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** Soma do espelho por CST bate com o total
apurado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-52 — Demonstrativo de retenções a recolher e a compensar

**O que é.** Relatório consolidado de retenções sofridas (como a de
ISS, FIS-14) e retenções feitas pela própria empresa (quando ela é fonte
pagadora) — separando o que é "a recolher" (retenção que a empresa fez
de terceiro) do que é "a compensar" (retenção que a empresa sofreu e
pode abater de imposto próprio).
**Exemplo.** Setembro: a Consultoria ABC sofreu R$ 200,00 de ISS retido
pelo tomador (FIS-14) — este valor não é "a recolher" pela Consultoria,
mas fica registrado como retenção sofrida, disponível para eventual
compensação conforme a legislação municipal aplicável (**a confirmar**).
**Referência de rotina.** Manual Domínio Escrita Fiscal, inventário do
grupo "Demonstrativos de apuração": "retenções a recolher e a compensar"
(faixa 1593-1619).
**Fonte normativa.** LC 116/2003 (retenção de ISS) e legislação
municipal para o mecanismo de compensação — **a confirmar por
município**; para retenções federais (IRRF, PIS/COFINS/CSLL retidos na
fonte), IN RFB vigente.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-14, FIS-23.
**Dados.** Retenções sofridas e feitas, por imposto e período.
**Regras.** Nunca soma retenção sofrida ao "a recolher" da própria
empresa (mesma regra já registrada em FIS-14).
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** A soma de retenções sofridas bate exatamente com
a soma dos lançamentos marcados com `tpRetISSQN` diferente de "1"
(FIS-14) mais eventuais retenções federais, quando implementadas.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante para ISS; retenções federais (IRRF,
CSLL) dependem de FIS-08 cadastrar esses impostos primeiro.

## Onda 8 — Relatórios de acompanhamento e conferência

Os seis itens abaixo pertencem à **classe conferência** (a mais livre das
três — nenhuma norma fixa o formato de um relatório de acompanhamento).
Todos seguem o princípio já registrado em
[personalizacao-de-relatorio.md](../personalizacao-de-relatorio.md#4-o-princípio-que-eu-proponho-e-que-não-veio-de-concorrente-nenhum):
*"o documento diz com que critérios foi gerado"*.

### FIS-53 — Acompanhamento de entradas

**O que é.** Listagem de todas as notas de entrada de um período,
ordenável por fornecedor, CFOP, data, alíquota ou acumulador — a
ferramenta de conferência do dia a dia antes de fechar o período.
**Exemplo.** Lista de setembro ordenada por acumulador, mostrando o
total de cada um, para conferir se bate com o resumo por acumulador
(FIS-56).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1619-1621
(menu Relatórios, Acompanhamentos, "Entradas": ordens por Fornecedor,
CFOP, Estado, Dia, Alíquota, Acumulador, Situação).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-36.
**Dados.** Nenhum novo — é listagem/agregação de FIS-36.
**Regras.** Todo lançamento do período aparece uma única vez, nunca
omitido nem duplicado.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Soma da listagem bate com a soma dos
lançamentos de entrada do período.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-54 — Acompanhamento de saídas

**O que é.** Equivalente de FIS-53 para notas de saída.
**Exemplo.** Lista de setembro ordenada por cliente, com filtro "somente
o CFOP X".
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1621-1623
(mesma seção, opção "Saídas": ordens por CFOP, Cliente, Estado, Dia,
Alíquota, Acumulador, Situação; considerar por data de saída ou de
emissão).
**Fonte normativa.** Não aplicável.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-37.
**Dados.** Idêntico a FIS-53, para saídas.
**Regras.** Idêntico a FIS-53.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Idêntico a FIS-53.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-55 — Acompanhamento de serviços

**O que é.** Equivalente de FIS-53/54 para notas de serviço — **o mais
importante dos três**, dado que 85% do acervo real é NFS-e (RC-66).
**Exemplo.** Lista de setembro ordenada por acumulador, mostrando as 470
NFS-e lançadas (FIS-13), com total por cliente.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1624-1625
(mesma seção, opção "Serviços": ordens por Cliente, Estado, Dia,
Acumulador, Situação; considerar por data de serviço ou de emissão).
**Fonte normativa.** Não aplicável.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-13.
**Dados.** Idêntico a FIS-53, para serviço.
**Regras.** Idêntico a FIS-53.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Idêntico a FIS-53.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — **prioridade alta dentro desta
onda**, pela composição real do acervo.

### FIS-56 — Resumo por acumulador, por CFOP e por alíquota

**O que é.** Três relatórios de agregação (agrupados aqui por
compartilharem a mesma lógica): total de movimento por acumulador, por
CFOP, e por alíquota — a forma mais rápida de conferir se a classificação
fiscal está coerente antes de apurar.
**Exemplo.** Resumo de setembro por acumulador mostra "Venda de Serviço
de Consultoria: R$ 500.000,00" e "Venda de Mercadoria: R$ 80.000,00" —
o Fred confere se os totais fazem sentido antes de rodar a apuração
(FIS-23).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1642-1650
aproximadamente (menu Relatórios, Acompanhamentos, "Resumo por
Acumulador" e "Resumo das Operações por CFOP e Alíquota").
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-13, FIS-36, FIS-37, FIS-07.
**Dados.** Nenhum novo — agregação sobre lançamentos existentes.
**Regras.** Soma do resumo bate com a soma de FIS-53/54/55 para o mesmo
período.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Três relatórios, mesma base de dados, três
agrupamentos diferentes, sempre somando ao mesmo total do período.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante.

### FIS-57 — Créditos acumulados e crédito presumido (demonstrativos)

**O que é.** Relatórios que mostram a evolução de créditos de ICMS
acumulados (quando a empresa gera mais crédito do que débito em um
período, no regime de crédito físico) e o crédito presumido aplicado
(FIS-11) — depende de cliente com esse perfil, que a amostra real ainda
não confirmou.
**Exemplo.** Não aplicável até demanda confirmada.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2278-2340
aproximadamente ("Créditos Acumulados", "Demonstrativos de Créditos
Acumulados", "Demonstrativo Crédito Presumido ICMS").
**Fonte normativa.** Legislação estadual de ICMS sobre crédito
acumulado — **a confirmar por UF**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-11, FIS-23.
**Dados.** Saldo de crédito por período, com origem rastreável.
**Regras.** Nunca aplica percentual de crédito presumido sem confirmação
(mesma regra de FIS-11).
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** Não aplicável até demanda confirmada.
**Não copiar/riscos.** Idêntico a FIS-11.
**Perguntas.** Idêntico a FIS-11 — depende de haver cliente com esse
perfil na carteira.

### FIS-58 — Diferencial de alíquotas e ressarcimento de ICMS-ST

**O que é.** Dois relatórios ligados a operação interestadual: o
diferencial de alíquotas (DIFAL, quando a empresa compra de outro estado
para uso/consumo/ativo, ou vende a consumidor final de outro estado) e o
ressarcimento de ICMS-ST (quando a venda efetiva foi por valor menor que
a base presumida de ST).
**Exemplo.** Não aplicável até demanda confirmada.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2320-2330
aproximadamente ("Diferencial de Alíquotas") e p. 2360-2390
("Demonstrativo do valor/cálculo de Ressarcimento do ICMS e ICMS ST").
**Fonte normativa.** Emenda Constitucional 87/2015 e Convênio ICMS
93/2015 (DIFAL); legislação estadual específica de ressarcimento de ST —
**a confirmar por par de UFs envolvido**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-08, FIS-10 (convênios de ST).
**Dados.** Base de cálculo e alíquota interestadual x interna, por
operação.
**Regras.** Nunca aplica alíquota interestadual sem confirmar a tabela
vigente (que pode variar por ano, dado o cronograma de partilha do
DIFAL entre estados).
**Telas e documentos.** Demonstrativo (classe demonstração).
**Critérios de aceite.** Não aplicável até demanda confirmada.
**Não copiar/riscos.** Risco de inventar alíquota interestadual —
proibido.
**Perguntas.** A carteira do Fred tem cliente com venda interestadual a
consumidor final, ou compra interestadual para uso/consumo? Sem isso,
este item fica indefinidamente adiado.

## Onda 9 — Guias

Guias são a ponte entre a apuração (FIS-23 em diante) e o pagamento
(FIS-26) — cada uma tem leiaute oficial próprio (linha digitável, código
de barras), então o risco de "guia errada" é concreto e grave: o
contribuinte pode pagar código de recolhimento errado ou banco recusar a
guia.

### FIS-59 — Guias federais (DARF, GPS)

**O que é.** Emissão da guia de recolhimento federal — DARF para a
maioria dos tributos federais (IRPJ, CSLL, PIS, COFINS, IRRF), GPS para
contribuição previdenciária quando não migrada ao eSocial/DCTFWeb.
**Exemplo.** DARF de IRPJ trimestral, código de receita **a confirmar na
tabela vigente da Receita Federal** (nunca inventado), valor apurado em
FIS-23, vencimento conforme Lei 9.430/1996.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1859-1935
aproximadamente (menu Relatórios, Guias, Federais: DARF Normal, DARF
PIS/COFINS Importação, DARF Quotas, DARF IPI, DARF IRRF (várias
variantes), DARF Avulso, GRU, GPS).
**Fonte normativa.** Instrução Normativa RFB vigente sobre código de
receita do DARF e leiaute do documento de arrecadação — **a confirmar
por tributo**; a maior parte da folha de contribuição previdenciária hoje
passa pelo DCTFWeb/eSocial, não mais GPS avulsa — **a confirmar
vigência**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23, FIS-08, FIS-12.
**Dados.** Código de receita, período de apuração, valor principal,
multa, juros, vencimento.
**Regras.** Nunca gera guia com código de receita ou algoritmo de código
de barras inventado — a validade da guia depende de ambos estarem
corretos contra fonte oficial.
**Telas e documentos.** Guia (classe guia).
**Critérios de aceite.** A guia gerada é validada, para um caso de
referência, contra o formato oficial (código de barras/linha digitável
íntegros, campo a campo).
**Não copiar/riscos.** **Risco alto de guia inválida** se implementado
sem validação contra fonte oficial — este item exige validação
profissional antes de qualquer entrega como "pronto para uso real"
(AGENTS.md §10).
**Perguntas.** Quais tributos federais a carteira do Fred efetivamente
recolhe por DARF hoje? Define a ordem real dentro deste item.

### FIS-60 — Guias estaduais (DARE, GNRE)

**O que é.** Guia de recolhimento estadual (ICMS) — DARE para
recolhimento dentro do próprio estado, GNRE para recolhimento a outro
estado (ex.: ICMS-ST, DIFAL).
**Exemplo.** Não aplicável até demanda confirmada — depende de FIS-58 ou
apuração de ICMS.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1935-1959
aproximadamente (menu Relatórios, Guias, Estaduais: DARE, DAR 19 Avulso,
DAR 27 Avulso, DARE variantes, GNRE Avulsa).
**Fonte normativa.** Legislação tributária estadual específica —
**a confirmar por UF**; GNRE tem leiaute nacional único (Convênio/Ajuste
SINIEF sobre a GNRE) — **a confirmar versão vigente**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23 (apuração de ICMS), FIS-08, FIS-12.
**Dados.** Idêntico a FIS-59, adaptado ao imposto estadual.
**Regras.** Idêntico a FIS-59.
**Telas e documentos.** Guia (classe guia).
**Critérios de aceite.** Idêntico a FIS-59.
**Não copiar/riscos.** Idêntico a FIS-59.
**Perguntas.** A carteira do Fred tem cliente que recolhe ICMS por guia
avulsa (fora da apuração normal, tipo ST ou DIFAL)? Define a prioridade
real.

### FIS-61 — Guias municipais (DARM)

**O que é.** Guia de recolhimento do ISS (DARM ou nome equivalente por
município) — a guia de **maior prioridade relativa** desta onda, pela
composição do acervo real (prestação de serviço, RC-66).
**Exemplo.** DARM de ISS de setembro, valor calculado em FIS-49/FIS-23,
código de município e alíquota conforme legislação do município
específico — **a confirmar por município atendido**.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1959-1985
aproximadamente (menu Relatórios, Guias, Municipais: DARM Municipal,
DARM ISS Retido).
**Fonte normativa.** LC 116/2003 (regras gerais do ISS) e legislação de
cada município (alíquota entre 2% e 5%, art. 8º-A) — **cada município
atendido precisa de confirmação própria antes de qualquer alíquota
entrar em código**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23, FIS-08, FIS-12, FIS-14 (retenção — a DARM ISS
Retido é distinta da normal).
**Dados.** Idêntico a FIS-59, adaptado ao ISS.
**Regras.** Idêntico a FIS-59; adicionalmente, uma guia de ISS Retido
nunca inclui valor já retido por terceiro (mesma regra de FIS-14/52).
**Telas e documentos.** Guia (classe guia).
**Critérios de aceite.** Idêntico a FIS-59; adicionalmente, ISS retido e
ISS próprio nunca se confundem na mesma guia.
**Não copiar/riscos.** Idêntico a FIS-59 — **risco alto**, dado o volume
real de NFS-e no acervo.
**Perguntas.** Confirmado pela leitura da RC-71 do
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#a-ressalva-que-o-próprio-levantamento-fez-e-que-mantenho):
82% das notas de serviço do acervo amostrado são de **um único
município** — qual é esse município, e sua legislação de ISS específica,
para que a primeira guia municipal implementada resolva o caso real
dominante?

## Onda 10 — Cadastrais, estoque e contas a pagar/receber (relatórios)

### FIS-62 — Relatórios cadastrais

**O que é.** Listagens simples dos cadastros de apoio: fornecedores,
clientes, produtos, acumuladores, impostos, CFOP, CFPS, contas, grupos,
unidades — todos de baixo risco (classe conferência, sem forma
prescrita), úteis para auditoria do próprio cadastro.
**Exemplo.** Listagem de todos os acumuladores ativos, com a
configuração de PIS/COFINS de cada um — usada para revisar a fundação
(FIS-07) antes de uma apuração importante.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1921-1985
(menu Relatórios, Cadastrais: Empresas, Sócios, Fornecedores, Emitentes,
Clientes, Acumuladores, Impostos, Grupos, Produtos, Contas, Históricos,
CFOP, CFPS, Simples Nacional).
**Fonte normativa.** Não aplicável.
**Situação no DataLedger.** **Não existe** — depende de FIS-03 a FIS-12
existirem primeiro.
**Depende de.** FIS-03 a FIS-12 (cada listagem depende do cadastro
correspondente).
**Dados.** Nenhum novo — é apresentação dos cadastros da onda 1.
**Regras.** Lista 100% dos registros do filtro, sem omissão.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** A contagem do relatório bate com a contagem
real do cadastro filtrado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma bloqueante — item de baixo esforço, implementável
junto de cada cadastro correspondente, em vez de esperar toda a onda 1.

### FIS-63 — Relatórios de estoque

**O que é.** Movimento individual do produto, movimento por grupo, Bloco
K, ICMS recuperável por produto — relatórios de apoio ao controle de
estoque (FIS-39).
**Exemplo.** Movimento do produto "Notebook X" em setembro: entrada 100,
saída 50, saldo final 50 (mesmo exemplo de FIS-39, em formato de
relatório).
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2793-2942
(menu Relatórios, Estoque: Movimento Individual, Movimento por Grupo,
Movimento de Produtos Bloco K, Movimento do ICMS Recuperável por
Produto).
**Fonte normativa.** O Bloco K em si é obrigação do SPED (ver FIS-69);
este item é só a **visualização interna**, não a geração do arquivo.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-39.
**Dados.** Nenhum novo — apresentação de FIS-39.
**Regras.** Bate exatamente com o saldo de FIS-39.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Idêntico a FIS-39.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Idêntico a FIS-39 quanto à prioridade real.

### FIS-64 — Relatórios de contas a pagar e a receber

**O que é.** Listagem de parcelas em aberto, pagas e vencidas — apoio
tanto à conferência financeira quanto ao regime de caixa da EFD
Contribuições (FIS-33).
**Exemplo.** Lista de contas a receber em aberto em 30/09/2026,
mostrando a parcela de R$ 4.000,00 do exemplo de FIS-33 ainda não
recebida.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 3084-3184
aproximadamente (menu Relatórios, "Contas a Pagar e Receber": A Pagar, A
Receber).
**Fonte normativa.** Não aplicável — relatório de conferência interna.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-41.
**Dados.** Nenhum novo — apresentação de FIS-41.
**Regras.** Bate exatamente com o saldo de parcelas de FIS-41.
**Telas e documentos.** Relatório (classe conferência).
**Critérios de aceite.** Soma de "em aberto" + "pago" = soma de todas as
parcelas geradas.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Idêntico a FIS-41 quanto à decisão de arquitetura do
módulo de contas a pagar/receber.

## Onda 11 — Obrigações acessórias (vigência a confirmar)

Cada item abaixo é uma obrigação que o manual cita e que, ao contrário
das listadas em "Fora de escopo" (mais abaixo), **tem indício razoável de
vigência em 2026** — mas nenhuma delas deve virar código sem a
confirmação explícita descrita em cada item. A diferença entre esta onda
e a seção "Fora de escopo" é justamente essa: aqui a obrigação
provavelmente continua existindo (mudou de leiaute, não desapareceu);
lá, o indício é de extinção ou substituição.

### FIS-65 — EFD ICMS/IPI (SPED Fiscal)

**O que é.** O arquivo digital que substitui os livros de ICMS/IPI em
papel — já parcialmente mapeado em
[DL-010](../../planos/DL-010-recepcao-de-documentos-fiscais.md#leiaute-do-sped-fiscal--levantado-em-fonte-oficial)
do lado da **importação** (migração/conferência); este item é o lado da
**geração** (transmissão da obrigação em si).
**Exemplo.** Arquivo de setembro com bloco C (documentos), bloco E
(apuração de ICMS/IPI), gerado a partir de FIS-36/37/23.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1740-1802
aproximadamente (seção Informativos, Federais, "SPED Fiscal": botões
Inventário, Valores Agregados, Convênio 115/2003, Vendas com Cartões).
**Fonte normativa.** **Guia Prático EFD-ICMS/IPI**, versão vigente
(3.2.3 confirmada na DL-010, atualização 06/05/2026), Ato COTEPE/ICMS
44/2018 e alterações — já parcialmente confirmado em DL-010.
**Situação no DataLedger.** **Não existe** a geração (a leitura/
importação está planejada, não implementada).
**Depende de.** FIS-36, FIS-37, FIS-23 (apuração de ICMS/IPI), FIS-39.
**Dados.** Estrutura de blocos do leiaute oficial.
**Regras.** Mesma disciplina de FIS-34 (arquivo determinístico, validado
contra o PVA oficial, nunca transmitido sem aprovação explícita).
**Telas e documentos.** Geração de arquivo (classe arquivo regulatório).
**Critérios de aceite.** Idêntico a FIS-34, adaptado ao PVA da EFD
ICMS/IPI.
**Não copiar/riscos.** Idêntico a FIS-34 — risco de leiaute desatualizado
(manual de 2018 x leiaute vigente confirmado em 2026 na DL-010).
**Perguntas.** O escritório do Fred transmite EFD ICMS/IPI hoje, ou só
EFD Contribuições (dado que 85% do acervo é serviço, sem ICMS)? Se a
resposta for "não transmite", este item fica atrás de FIS-34 na fila
real.

### FIS-66 — EFD-Reinf

**O que é.** Obrigação digital que substituiu parte do que antes ia na
DIRF/GFIP — retenções, recursos repassados a terceiros, contribuição
previdenciária sobre receita bruta (CPRB) — hoje integrada ao eSocial.
**Exemplo.** Não aplicável sem confirmação de vigência para o caso
específico.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1802-1814
aproximadamente (seção Informativos, "EFD-Reinf": Enviar Arquivos,
Eventos, Boletim Financeiro, INSS-RET Construção Civil).
**Fonte normativa.** Manual de Orientação do Contribuinte da EFD-Reinf,
versão vigente, Portal SPED/eSocial — **a confirmar versão e escopo de
eventos aplicável (R-1000 a R-9000)**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-08 (impostos/contribuições retidos), e
potencialmente do módulo Folha (fora de escopo deste documento) para os
eventos relacionados a mão de obra.
**Dados.** Eventos periódicos e não periódicos do leiaute EFD-Reinf.
**Regras.** Idêntico a FIS-34/65.
**Telas e documentos.** Geração de arquivo (classe arquivo regulatório).
**Critérios de aceite.** Idêntico a FIS-34.
**Não copiar/riscos.** Idêntico a FIS-34/65.
**Perguntas.** A carteira do Fred tem cliente sujeito a EFD-Reinf (retém
serviço de terceiro, ou recolhe CPRB)? Sem confirmação, este item fica
adiado.

### FIS-67 — DCTF / DCTFWeb

**O que é.** Declaração que consolida os débitos e créditos de tributos
federais apurados — a DCTF clássica foi parcialmente substituída pela
DCTFWeb, que já integra dados do eSocial/EFD-Reinf para contribuições
previdenciárias.
**Exemplo.** Não aplicável sem confirmação.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2172-2230
aproximadamente (seção Informativos, "DCTF": Mensal, Trimestral,
Semestral).
**Fonte normativa.** Instrução Normativa RFB vigente sobre DCTF/DCTFWeb
— **a confirmar qual delas se aplica hoje, e para qual tributo**: a
migração para DCTFWeb já é regra geral desde 2021/2022 para a maior
parte dos contribuintes — **a confirmar vigência exata e leiaute**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23 (todos os impostos federais apurados).
**Dados.** Consolidação por tributo/período dos valores apurados.
**Regras.** Idêntico a FIS-34.
**Telas e documentos.** Geração de arquivo/declaração (classe arquivo
regulatório).
**Critérios de aceite.** Idêntico a FIS-34.
**Não copiar/riscos.** Risco de implementar a DCTF clássica quando a
obrigação real já migrou para DCTFWeb — **confirmar antes de escolher
qual das duas implementar**.
**Perguntas.** Nenhuma bloqueante para adiar — mas obrigatória antes de
implementar: qual das duas (DCTF ou DCTFWeb) é a exigida hoje para os
tributos da carteira do Fred?

### FIS-68 — DeSTDA

**O que é.** Declaração de Substituição Tributária, Diferencial de
Alíquota e Antecipação — obrigação estadual do Simples Nacional para
operações interestaduais sujeitas a ICMS-ST/DIFAL.
**Exemplo.** Não aplicável sem confirmação.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2265-2278
aproximadamente (seção Informativos, "DeSTDA").
**Fonte normativa.** Ajuste SINIEF 12/2015 e alterações — **a
confirmar vigência**.
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-27 (regime Simples Nacional), FIS-58 (DIFAL/ST).
**Dados.** Consolidação de ICMS-ST/DIFAL por UF e período.
**Regras.** Idêntico a FIS-34.
**Telas e documentos.** Geração de arquivo (classe arquivo regulatório).
**Critérios de aceite.** Idêntico a FIS-34.
**Não copiar/riscos.** Idêntico a FIS-34.
**Perguntas.** A carteira do Fred tem cliente do Simples Nacional com
operação interestadual sujeita a ST/DIFAL? Mesma pergunta de FIS-58.

### FIS-69 — DEFIS / DASN (declaração anual do Simples Nacional)

**O que é.** Declaração anual de informações socioeconômicas e fiscais
do Simples Nacional — a DASN foi substituída pela DEFIS há alguns anos;
o manual lista as duas separadamente porque cobre ambas as épocas.
**Exemplo.** Não aplicável sem confirmação.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 2270-2320
aproximadamente (seção Informativos: "DASN" e "DEFIS", cada uma com
guias Geral, Doações Eleitorais, Econômicas e Fiscais, Mudança de
Município).
**Fonte normativa.** Resolução CGSN vigente sobre a DEFIS — **a
confirmar se a DASN ainda tem alguma vigência residual ou se foi
totalmente substituída** (indício forte de substituição integral, a
confirmar).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-27 (todo o ano-calendário apurado pelo Simples
Nacional).
**Dados.** Consolidação anual de receita, sócios, informações
econômico-fiscais.
**Regras.** Idêntico a FIS-34.
**Telas e documentos.** Geração de declaração (classe arquivo
regulatório).
**Critérios de aceite.** Idêntico a FIS-34.
**Não copiar/riscos.** **Implementar só a DEFIS**, salvo confirmação
explícita de que algum cliente ainda usa DASN (indício de obsolescência
forte, mas não afirmado como certeza — ver a diferença desta onda para
"Fora de escopo").
**Perguntas.** Nenhuma bloqueante para adiar; confirmar vigência antes de
implementar.

### FIS-70 — GIA / declarações estaduais de substituição tributária

**O que é.** Guia de Informação e Apuração do ICMS (GIA) — obrigação
estadual (não federal), com leiaute próprio por UF, hoje em processo de
substituição pela própria EFD ICMS/IPI em vários estados.
**Exemplo.** Não aplicável sem confirmação.
**Referência de rotina.** Manual Domínio Escrita Fiscal, inventário do
grupo "Guias Substituição Tributária" e declarações estaduais (faixa
1675-1859, seção "Estaduais": DIME, DCIP, "Gia Substituição
Tributária").
**Fonte normativa.** Legislação tributária de cada UF — **a confirmar
por estado**; muitos estados já extinguiram a GIA em favor da EFD
ICMS/IPI (indício, não certeza).
**Situação no DataLedger.** **Não existe.**
**Depende de.** FIS-23 (apuração de ICMS-ST), FIS-65 (EFD ICMS/IPI, que
pode já substituir esta obrigação).
**Dados.** Dependente do leiaute de cada UF.
**Regras.** Idêntico a FIS-34.
**Telas e documentos.** Geração de arquivo/declaração (classe arquivo
regulatório).
**Critérios de aceite.** Idêntico a FIS-34.
**Não copiar/riscos.** Idêntico a FIS-34.
**Perguntas.** Quais UFs a carteira do Fred atende, e cada uma delas
ainda exige GIA (ou já extinguiu em favor da EFD ICMS/IPI)? Sem essa
resposta por UF, este item não pode ser dimensionado.

## Onda 12 — Operação e utilitários

### FIS-71 — Backup e restauração

**O que é.** Rotina de salvaguarda e recuperação de dados do módulo
Fiscal — capacidade transversal que o manual trata como parte do "menu
Utilitários", mas que no DataLedger é responsabilidade de infraestrutura
(banco de dados PostgreSQL), não de uma tela do módulo.
**Exemplo.** Backup diário do banco de dados, incluindo `DocumentoFiscal`
e todo o restante do esquema — já coberto pela infraestrutura geral do
projeto, não é capacidade específica do Fiscal.
**Referência de rotina.** Manual Domínio Escrita Fiscal, p. 1987-2020
aproximadamente (menu Utilitários: Backup, Configurar Backup, Backup em
Nuvem).
**Fonte normativa.** Não aplicável — é prática de operação, não
obrigação fiscal (embora backup e restauração verificados sejam exigidos
pelo AGENTS.md §12).
**Situação no DataLedger.** **Coberto pela infraestrutura geral do
projeto** (backup de banco de dados), não por uma tela do módulo Fiscal.
**Depende de.** Nada específico do Fiscal.
**Dados.** Não aplicável — é infraestrutura, não dado de domínio.
**Regras.** AGENTS.md §12: backup e restauração planejados e
**verificados** (não basta existir, precisa ter sido testado).
**Telas e documentos.** Não aplicável a este módulo especificamente.
**Critérios de aceite.** Não aplicável a este documento — pertence ao
plano de infraestrutura do projeto.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma — este item é só uma **nota de que não é capacidade
do módulo**, para que ninguém tente implementar "backup do Fiscal" como
se fosse separado do backup do sistema inteiro.

### FIS-72 — Registro de atividades do usuário (trilha de auditoria fiscal)

**O que é.** Quem fez o quê, quando, dentro do módulo Fiscal — já
parcialmente coberto pela trilha de auditoria geral do projeto
(`apps/auditoria`), usada por FIS-01 (`registrar(acao="fiscal.envio_recebido"`,
...)). Este item estende a mesma trilha para as demais ações do módulo
(lançamento, apuração, integração contábil, geração de guia).
**Exemplo.** Toda vez que a apuração de um período é rodada (FIS-23), um
registro de trilha guarda quem rodou, quando, e o resumo (nunca dado
sensível de terceiro).
**Referência de rotina.** Manual Domínio Escrita Fiscal, referência
indireta em vários pontos (usuário que fez lançamento, campo
"Conferido" com usuário).
**Fonte normativa.** Não aplicável diretamente — apoia a exigência geral
de trilha de auditoria protegida (AGENTS.md §11).
**Situação no DataLedger.** **Parcial** — o padrão já existe e está
auditado para a recepção (FIS-01); falta estendê-lo a cada novo item
implementado.
**Depende de.** Cada item novo herda esta regra, não é uma dependência
única.
**Dados.** Reaproveita `apps.auditoria.services.registrar`.
**Regras.** Toda ação relevante do Fiscal registra ator, contexto,
operação e resultado, sem expor segredo ou dado desnecessário
(AGENTS.md §11) — a mesma disciplina já aplicada em FIS-01.
**Telas e documentos.** Consulta de trilha (fora do escopo deste
documento — pertence a `apps/auditoria`).
**Critérios de aceite.** Cada novo item de escrita (FIS-13, FIS-19,
FIS-23, FIS-26...) gera registro de trilha ao ser implementado — critério
de aceite **de cada item**, não deste item isolado.
**Não copiar/riscos.** Nenhum.
**Perguntas.** Nenhuma — é regra transversal, não item a decidir
isoladamente.

### FIS-73 — Importador genérico / formato de intercâmbio de terceiros

**O que é.** O achado estratégico já registrado em
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#achado-de-estratégia-existe-um-formato-de-intercâmbio-documentado-e-público):
o sistema de gestão de XML que o escritório **já usa** (RC-41) exporta um
formato de intercâmbio texto, público, com 65 tipos de registro,
cobrindo cadastros, produtos, contas contábeis, notas de entrada/saída/
serviço e parcelas. Ler esse formato permitiria ao DataLedger virar
"mais um destino" do que o escritório já produz, sem trocar a ferramenta
de captura.
**Exemplo.** Um arquivo de intercâmbio com registros `3000`-`3500`
(notas de serviço) é lido e gera os mesmos `DocumentoFiscal`/lançamentos
que a leitura de XML nativo geraria — **caminho alternativo**, nunca
substituto do XML oficial.
**Referência de rotina.** Manual "Importação Padrão" (faixas de registro
já mapeadas em
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#achado-de-estratégia-existe-um-formato-de-intercâmbio-documentado-e-público)).
**Fonte normativa.** Não é norma tributária — é formato proprietário de
terceiro, publicado em diretório aberto. Ler um formato documentado e
público é **interoperabilidade**, categoria diferente de copiar
interface ou funcionalidade — mas é decisão de produto com dimensão
jurídica, que **não cabe a um agente decidir sozinho** (o próprio mapa
funcional já registrou isso).
**Situação no DataLedger.** **Não existe.**
**Depende de.** Toda a fundação (FIS-01 a FIS-12) e os lançamentos
correspondentes (FIS-13, FIS-36, FIS-37) — o formato de intercâmbio
alimenta as mesmas estruturas, não cria estruturas paralelas.
**Dados.** Um leitor por faixa de registro do formato de intercâmbio,
convertendo para as mesmas entidades já definidas nos itens acima.
**Regras.** Nunca cria estrutura de dados paralela à já definida pelos
itens de fundação — o formato de intercâmbio é só mais uma **porta de
entrada**, os dados internos são os mesmos.
**Telas e documentos.** Mesma tela de recepção, estendida (classe
conferência).
**Critérios de aceite.** Uma nota de serviço lida pelo formato de
intercâmbio e a mesma nota lida por XML nativo produzem o mesmo
`DocumentoFiscal`/lançamento (mesmo resultado, fontes diferentes).
**Não copiar/riscos.** **Decisão de produto pendente do Fred**, com
dimensão jurídica — não implementar sem essa decisão explícita, mesmo
que o leiaute esteja publicamente documentado.
**Perguntas.** O Fred autoriza o DataLedger a ler o formato de
intercâmbio do sistema de gestão de XML que o escritório já usa? Pergunta
já registrada como pendente em
[mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#decisão-que-cabe-ao-fred)
e reafirmada aqui porque este item não deve avançar sem resposta.

## Fora de escopo, obsoleto ou dependente de confirmação

Estes itens aparecem no manual de 2018, mas têm **indício de extinção,
substituição ou renomeação** forte o suficiente para não entrar na onda
11 (que reúne obrigações prováveis de estarem vigentes). Nenhum deles é
implementado sem que a fonte oficial indicada confirme vigência — a
inclusão aqui é justamente o registro de que **não presumimos vigência**,
nem em um sentido nem no outro. Cada um segue o formato reduzido pedido:
ID, motivo, fonte oficial que decide.

### FIS-80 — DACON

**Motivo.** Demonstrativo de Apuração de Contribuições Sociais, obrigação
que a própria EFD Contribuições (FIS-30 a FIS-35) foi desenhada para
substituir. Forte indício de extinção.
**Fonte que decide.** Portal SPED / Receita Federal — ato de extinção do
DACON, a localizar e citar antes de qualquer decisão definitiva.

### FIS-81 — DIPJ

**Motivo.** Declaração de Informações Econômico-Fiscais da Pessoa
Jurídica, substituída pela ECF (Escrituração Contábil Fiscal) desde o
ano-calendário 2014. Indício de extinção forte.
**Fonte que decide.** Instrução Normativa RFB que instituiu a ECF e
extinguiu a DIPJ — a confirmar número e data exatos.

### FIS-82 — DNF

**Motivo.** Demonstrativo das Notas Fiscais — obrigação pouco
documentada fora do manual de 2018; sem evidência de uso corrente.
**Fonte que decide.** Não localizada fonte oficial vigente até o
momento — **pendência de pesquisa**, não afirmação de extinção.

### FIS-83 — CFEM

**Motivo.** Compensação Financeira pela Exploração de Recursos Minerais —
obrigação de setor mineral, sem qualquer indício de que a carteira do
Fred atenda esse setor.
**Fonte que decide.** Agência Nacional de Mineração (ANM) — só relevante
se houver cliente do setor mineral confirmado.

### FIS-84 — I-SIMP

**Motivo.** Informativo específico de agentes regulados (ver referência a
"Agente regulado" em FIS-04) — setor muito específico (ex.: distribuição
de combustíveis), sem indício de uso na carteira do Fred.
**Fonte que decide.** Órgão regulador do setor específico — a confirmar
qual, se houver demanda.

### FIS-85 — PJSI

**Motivo.** Obrigação citada no manual sem contexto suficiente para
identificar sua vigência atual; nome sugere programa/regime específico já
superado por reformas posteriores.
**Fonte que decide.** Não localizada — **pendência de pesquisa**.

### FIS-86 — SINCO Simplificado

**Motivo.** Obrigação sem evidência de vigência corrente; nome sugere
sistema de informação de outra geração do SPED.
**Fonte que decide.** Portal SPED — a confirmar se ainda existe sob esse
nome ou outro.

### FIS-87 — SVA

**Motivo.** Obrigação sem contexto suficiente no manual para identificar
o órgão responsável ou vigência.
**Fonte que decide.** Não localizada — **pendência de pesquisa**.

### FIS-88 — DIMOB

**Motivo.** Declaração de Informações sobre Atividades Imobiliárias —
só relevante para empresas do ramo imobiliário, que este plano já
registrou como segmento especializado fora de escopo (FIS-43), salvo
demanda confirmada.
**Fonte que decide.** Instrução Normativa RFB vigente sobre DIMOB — a
confirmar se ainda é exigida e para quem, caso surja demanda.

### FIS-89 — DCIP

**Motivo.** Obrigação estadual sem contexto suficiente no manual para
identificar UF e vigência específicas.
**Fonte que decide.** Legislação da UF específica — a confirmar caso
surja demanda de cliente na UF correspondente.

### FIS-90 — SCANC-CTB

**Motivo.** Nome sugere um sistema estadual de conciliação
contábil-fiscal de geração anterior ao SPED atual; sem evidência de uso
corrente.
**Fonte que decide.** Legislação estadual específica — a confirmar.

### FIS-91 — Convênio ICMS 115/2003

**Motivo.** Regulamenta emissão de documento fiscal para empresas de
comunicação e telecomunicação/energia elétrica (ver referência ao "Botão
Convênio 115/2003" dentro do SPED Fiscal no manual) — só relevante se a
carteira do Fred atender esse setor específico.
**Fonte que decide.** Confaz — Convênio ICMS 115/2003 e alterações
posteriores, a confirmar vigência para o setor específico.

### FIS-92 — Sintegra

**Motivo.** Sistema Integrado de Informações sobre Operações
Interestaduais, de geração anterior à Nota Fiscal Eletrônica e à EFD
ICMS/IPI — forte indício de obsolescência, já com a própria NF-e e o
SPED Fiscal cumprindo o papel de informação interestadual.
**Fonte que decide.** Convênio ICMS 57/1995 e atos posteriores de
substituição — a confirmar se ainda subsiste em algum estado específico.

### FIS-93 — DIRF e comprovantes de retenção

**Motivo.** Declaração do Imposto de Renda Retido na Fonte — a DIRF
está em processo de extinção, com as informações de retenção migrando
para o eSocial e a EFD-Reinf (que já é a onda 11, FIS-66). Comprovantes
de retenção (mensal, anual, eletrônico) são consequência direta da DIRF
e seguem a mesma incerteza de vigência.
**Fonte que decide.** Instrução Normativa RFB sobre a extinção
progressiva da DIRF em favor do eSocial/EFD-Reinf — a confirmar
cronograma e se já se aplica ao perfil de retenção da carteira do Fred.

### FIS-94 — DMED

**Motivo.** Declaração de Serviços Médicos e de Saúde — só relevante se
a carteira do Fred atender clínicas, hospitais, operadoras de plano de
saúde ou profissionais de saúde. Sem evidência de que este seja o perfil
medido (85% do acervo é serviço genérico, sem indicação de área médica).
**Fonte que decide.** Instrução Normativa RFB vigente sobre a DMED — a
confirmar se ainda é exigida, caso surja demanda de cliente da área.

### FIS-95 — Receitas MEI

**Motivo.** Relatório mensal de receitas do Microempreendedor Individual
— só relevante se a carteira do Fred atender MEI, o que não foi
confirmado (o acervo medido é de empresas com movimento relevante de
NFS-e/NF-e, perfil normalmente acima do teto de faturamento do MEI).
**Fonte que decide.** Resolução CGSN vigente sobre MEI — a confirmar
perfil de cliente antes de decidir.

### FIS-96 — PER/DCOMP

**Motivo.** Pedido Eletrônico de Restituição, Ressarcimento ou
Reembolso e Declaração de Compensação — obrigação federal que pressupõe
crédito tributário a compensar, cenário não confirmado na carteira do
Fred hoje.
**Fonte que decide.** Instrução Normativa RFB vigente sobre PER/DCOMP —
a confirmar se há crédito a compensar em algum cliente antes de
priorizar.

### FIS-97 — SPED Contábil

**Motivo.** A Escrituração Contábil Digital (ECD) **pertence ao módulo
Contabilidade**, não ao Fiscal — citada aqui só para que nenhum
desenvolvedor confunda com a EFD ICMS/IPI ou a EFD Contribuições
(FIS-65, FIS-30 a FIS-35), que são as obrigações digitais próprias do
Fiscal. Ver o plano `contabilidade.md` (quando escrito) para o item
correspondente.
**Fonte que decide.** Não aplicável a este documento — remissão de
escopo, não pendência normativa.

## O fluxo da EFD Contribuições no Lucro Presumido ("mapa do Lucro Presumido")

Seção dedicada, por pedido explícito do Fred. Reúne, num único lugar, a
decisão em árvore que o Manual EFD Lucro Presumido (22 páginas) descreve,
ligando cada ramo aos itens FIS correspondentes definidos acima — para
que um desenvolvedor não precise reconstruir a árvore a partir de itens
espalhados.

### A árvore de decisão

```
Empresa parametrizada como Lucro Presumido (FIS-03)
│
├─ 1. Regime de apuração do PIS/COFINS: COMPETÊNCIA
│    │
│    ├─ 1.1. Forma de cálculo: COMPLETO (FIS-32)
│    │        Exige: cadastro de produto com tributação por vigência
│    │        (FIS-05) + controle de estoque (FIS-39) + guias
│    │        "Estoque"/"Itens" nos lançamentos (FIS-36/37/13).
│    │        Mesmo comportamento do Lucro Real.
│    │
│    ├─ 1.2. Forma de cálculo: SIMPLIFICADO
│    │        │
│    │        ├─ 1.2.1. Lançamento POR PRODUTO (FIS-31)
│    │        │          Exige: cadastro de produto (FIS-05, sem a
│    │        │          granularidade do não cumulativo) + guia
│    │        │          "Estoque"/"Itens" nos lançamentos.
│    │        │
│    │        └─ 1.2.2. Lançamento POR NOTA (FIS-30) ← RAMO PRIORITÁRIO
│    │                   Dispensa produto: o cálculo nasce do
│    │                   ACUMULADOR (FIS-07) aplicado ao valor da nota
│    │                   inteira. Combina com o acervo real (85% NFS-e,
│    │                   RC-66).
│    │
├─ 2. Regime de apuração do PIS/COFINS: CAIXA (FIS-33)
     │    Só existe SIMPLIFICADO (nunca "completo" no regime de caixa,
     │    regra confirmada no próprio manual, p. 11).
     │    Exige: controle de contas a receber (FIS-41, que por sua vez
     │    depende de um módulo de contas a receber ainda inexistente) +
     │    parcela em toda nota + base proporcional ao valor RECEBIDO,
     │    nunca ao valor total da nota.
     │
     ├─ 2.1. Lançamento POR PRODUTO — mesma exigência de cadastro de
     │        FIS-31, mais a proporcionalidade da baixa de parcela.
     │
     └─ 2.2. Lançamento POR NOTA — mesma exigência de FIS-30, mais a
              proporcionalidade da baixa de parcela.

              → Ao final de qualquer ramo: FIS-34, geração do arquivo
                digital da EFD Contribuições.
```

### Por que o ramo 1.2.2 (competência, simplificado por nota) é prioritário

Três fatos medidos, não presumidos, convergem para esta escolha:

1. **85% do acervo real é NFS-e** (RC-66) — nota de serviço, sem
   produto associado.
2. O ramo 1.2.2 é o **único** que dispensa completamente o cadastro de
   produto (FIS-05) — o cálculo nasce inteiramente do acumulador
   (FIS-07), que já é fundação obrigatória de qualquer lançamento
   fiscal (FIS-13).
3. O regime de caixa (ramo 2) depende de contas a receber, que **não
   existe** no DataLedger hoje — confirmado tanto no mapa funcional
   quanto neste documento (FIS-33, FIS-41).

Portanto, a ordem de implementação real dentro da onda 4 é: FIS-29
(parâmetros) → FIS-07/FIS-08 (se ainda não prontos da onda 1) → **FIS-30**
(ramo 1.2.2) → FIS-51 (espelho) → FIS-34 (arquivo digital) — só depois
disso, se houver demanda medida (produto/estoque relevante ou cliente em
regime de caixa), os ramos FIS-31, FIS-32 e FIS-33 entram.

### O que cada ramo exige, em uma tabela

| Ramo | Item FIS | Exige produto? | Exige estoque? | Exige contas a receber? | Fato gerador |
| --- | --- | --- | --- | --- | --- |
| 1.1 Competência, completo | FIS-32 | Sim, com tributação por vigência | Sim | Não | Emissão da nota |
| 1.2.1 Competência, simplificado por produto | FIS-31 | Sim, tributação simples | Sim (para a guia "Estoque") | Não | Emissão da nota |
| 1.2.2 Competência, simplificado por nota | FIS-30 | **Não** | **Não** | Não | Emissão da nota |
| 2.1 Caixa, simplificado por produto | FIS-33 (aplicado sobre a base de FIS-31) | Sim | Sim | **Sim** | Recebimento (proporcional) |
| 2.2 Caixa, simplificado por nota | FIS-33 (aplicado sobre a base de FIS-30) | **Não** | **Não** | **Sim** | Recebimento (proporcional) |

### Exemplo numérico consolidado (sintético, ilustrativo)

Nota de serviço de R$ 10.000,00, prestada pela "Consultoria ABC Ltda."
(Lucro Presumido) para "Comércio XYZ Ltda.", `tpRetISSQN = "2"` (ISS
retido pelo tomador).

- **Ramo 1.2.2 (competência, por nota — FIS-30):** todo o valor de R$
  10.000,00 entra na base de PIS/COFINS no mês da emissão, usando o CST e
  alíquota configurados no acumulador "Venda de Serviço de Consultoria".
  Com alíquotas ilustrativas de PIS 0,65% e COFINS 3% (regime cumulativo
  — **a confirmar na Lei 9.718/1998 art. 8º e sua vigência antes de
  codificar**), o resultado ilustrativo seria PIS R$ 65,00 e COFINS
  R$ 300,00.
- **Ramo 2.2 (caixa, por nota):** se a nota for recebida em duas
  parcelas (R$ 6.000,00 em setembro, R$ 4.000,00 em outubro), a base de
  setembro é R$ 6.000,00 (PIS R$ 39,00, COFINS R$ 180,00 — mesma alíquota
  ilustrativa) e a de outubro é R$ 4.000,00 (PIS R$ 26,00, COFINS R$
  120,00) — a soma das duas parcelas bate com o resultado do ramo 1.2.2
  (R$ 65,00 e R$ 300,00), só distribuída no tempo pelo recebimento.

**Nenhum desses números deve entrar em código sem a alíquota vigente
confirmada em fonte oficial** — o exemplo serve só para mostrar a
mecânica de distribuição temporal entre os dois regimes.

## Glossário

Termos usados neste documento sem explicação no corpo do texto, para que
quem não é contador acompanhe sem precisar perguntar a cada linha.

- **Acumulador.** Cadastro que classifica uma operação fiscal (venda,
  compra, devolução, serviço) e determina, de uma vez, sobre o que ela
  incide, quais impostos carrega e quais contas contábeis usa — ver
  FIS-07. É a peça central do motor fiscal deste plano.
- **Base de cálculo.** O valor sobre o qual uma alíquota é aplicada para
  chegar ao valor do imposto (ex.: base R$ 10.000,00 × alíquota 3% =
  imposto R$ 300,00).
- **CFOP (Código Fiscal de Operações e Prestações).** Código de 4
  dígitos que classifica a natureza de uma operação (venda dentro do
  estado, compra para revenda, devolução...), padronizado nacionalmente
  (Ajuste SINIEF).
- **CFPS.** Código Fiscal de Prestação de Serviço — equivalente ao CFOP,
  para operações de serviço.
- **Competência (fiscal).** O período (mês/ano) ao qual um documento ou
  apuração pertence, que pode divergir da data de emissão do documento
  (ex.: nota emitida no fim do mês, escriturada no mês seguinte).
- **CSOSN (Código de Situação da Operação no Simples Nacional).**
  Equivalente ao CST, usado por empresas do Simples Nacional em vez do
  CST clássico.
- **CST (Código de Situação Tributária).** Código que descreve o
  tratamento tributário de um item de operação para um imposto
  específico (ICMS, IPI, PIS, COFINS) — cada imposto tem sua própria
  tabela de CST.
- **DARF (Documento de Arrecadação de Receitas Federais).** Guia de
  recolhimento da maioria dos tributos federais.
- **DARM.** Guia de recolhimento municipal (nome pode variar por
  município), usada principalmente para ISS.
- **DARE.** Guia de recolhimento estadual (ICMS), nome que pode variar
  por UF.
- **DAS (Documento de Arrecadação do Simples Nacional).** Guia única de
  recolhimento de todos os tributos do Simples Nacional.
- **DCTFWeb.** Declaração que consolida débitos e créditos de tributos
  federais, hoje integrada ao eSocial/EFD-Reinf para contribuições
  previdenciárias — sucessora, para a maior parte dos casos, da DCTF
  clássica.
- **DIFAL (Diferencial de Alíquotas).** Valor de ICMS devido quando uma
  operação interestadual tem alíquota interna do estado de destino maior
  que a alíquota interestadual, dividido entre origem e destino conforme
  cronograma legal.
- **EFD Contribuições.** Escrituração Fiscal Digital do PIS/COFINS (e da
  Contribuição Previdenciária sobre a Receita Bruta, quando aplicável) —
  o arquivo digital que consolida a apuração dessas contribuições
  (FIS-30 a FIS-35).
- **EFD ICMS/IPI (SPED Fiscal).** Escrituração Fiscal Digital do ICMS e
  do IPI, que substitui os livros fiscais em papel (FIS-65).
- **EFD-Reinf.** Escrituração Fiscal Digital de Retenções e Outras
  Informações Fiscais — retenções, recursos repassados a terceiros,
  CPRB, hoje integrada ao eSocial (FIS-66).
- **Fato gerador.** O evento que faz nascer a obrigação de pagar um
  tributo (ex.: emissão da nota, no regime de competência; recebimento
  do valor, no regime de caixa).
- **GNRE (Guia Nacional de Recolhimento de Tributos Estaduais).** Guia
  usada para recolher tributo estadual a um estado diferente do que
  emitiu a guia (ex.: ICMS-ST de operação interestadual).
- **ICMS-ST (Substituição Tributária do ICMS).** Mecanismo em que um
  contribuinte (normalmente o fabricante ou importador) recolhe
  antecipadamente o ICMS de toda a cadeia até o consumidor final.
- **Memória de cálculo.** O registro detalhado de como um valor apurado
  foi calculado, rastreável até os dados de origem — exigência do
  AGENTS.md §10.
- **NCM (Nomenclatura Comum do Mercosul).** Código que classifica um
  produto para fins de tributação e comércio exterior, usado como base
  para determinar alíquotas de ICMS, IPI e, por vezes, PIS/COFINS.
- **NFS-e nacional.** Nota Fiscal de Serviço eletrônica no padrão
  nacional unificado (ADN — Ambiente de Dados Nacional), diferente das
  NFS-e municipais anteriores à unificação.
- **RBT12 (Receita Bruta dos últimos 12 meses).** Base usada pelo
  Simples Nacional para determinar a faixa e a alíquota efetiva de cada
  mês — recalculada mensalmente como janela móvel (FIS-27).
- **Regime cumulativo (PIS/COFINS).** Regime em que a alíquota incide
  sobre a receita bruta sem direito a desconto de créditos das etapas
  anteriores — regra geral do Lucro Presumido (Lei 9.718/1998).
- **Regime de caixa.** Regime de apuração em que o fato gerador do
  tributo é o recebimento efetivo do valor, não a emissão do documento
  (FIS-33).
- **Regime não cumulativo (PIS/COFINS).** Regime em que a empresa pode
  descontar créditos de etapas anteriores da cadeia — regra geral do
  Lucro Real, exceção no Presumido.
- **SPED (Sistema Público de Escrituração Digital).** Conjunto de
  obrigações digitais da Receita Federal e dos fiscos estaduais/
  municipais que substituiu, progressivamente, livros e declarações em
  papel — engloba a EFD ICMS/IPI, a EFD Contribuições, a EFD-Reinf e a
  ECD (esta última, do módulo Contabilidade).

## Perguntas abertas consolidadas

Todas as perguntas já aparecem dentro do item correspondente; esta lista
reúne só as que dependem diretamente do Fred (prática do escritório ou
composição da carteira), para que ele não precise garimpar item por
item.

1. **(FIS-03)** Quais regimes tributários (Simples Nacional, Lucro
   Presumido, Lucro Real) e quais UFs/municípios existem hoje na
   carteira do Fred?
2. **(FIS-04)** O cadastro de participante deve nascer automaticamente
   da recepção de documentos, ou é sempre cadastro manual prévio?
3. **(FIS-05, FIS-30/31)** Os clientes de Lucro Presumido da carteira
   estão todos no regime cumulativo clássico de PIS/COFINS, ou há
   exceção por atividade?
4. **(FIS-10, FIS-58)** A carteira do Fred tem cliente com operação
   interestadual sujeita a ICMS-ST ou DIFAL?
5. **(FIS-11, FIS-57)** A carteira do Fred usa algum crédito presumido
   (ICMS ou PIS/COFINS) hoje?
6. **(FIS-12)** O DataLedger já tem ou vai ter um módulo financeiro do
   escritório com cadastro bancário genérico, para FIS-12 reaproveitar
   em vez de duplicar?
7. **(FIS-15)** A conferência de lançamentos deve **bloquear** a
   apuração do período ou é só aviso?
8. **(FIS-22)** O modelo de cobrança de honorários (fixo, percentual
   sobre imposto, por evento) já está definido em algum lugar?
9. **(FIS-25)** A carteira do Fred usa parcelamento de imposto hoje? De
   quais tributos?
10. **(FIS-27)** Quais anexos (I a V) da LC 123/2006 e quais atividades
    a carteira do Fred realmente usa no Simples Nacional?
11. **(FIS-28)** O DataLedger vai transmitir a declaração ao PGDAS-D via
    integração oficial, ou só calcular e exibir para digitação manual?
12. **(FIS-31/32)** A carteira do Fred tem cliente de Presumido que
    vende mercadoria (não só presta serviço), a ponto de exigir os
    ramos "simplificado por produto" ou "completo" da EFD Contribuições?
13. **(FIS-33)** A carteira do Fred tem cliente de Presumido no regime
    de caixa? (Depende também de contas a receber existir, fora deste
    plano.)
14. **(FIS-34, FIS-65 a FIS-70)** O escritório vai efetivamente
    **transmitir** as obrigações digitais pelo DataLedger, ou só usar o
    cálculo como conferência de outro sistema? Muda o escopo de cada
    item de geração de arquivo.
15. **(FIS-39, FIS-40, FIS-63)** A carteira do Fred tem cliente
    comercial/industrial com estoque relevante, ou é majoritariamente
    prestador de serviço (como sugere RC-66)?
16. **(FIS-41, FIS-64)** O módulo de contas a pagar/receber é do
    Fiscal, do Financeiro do escritório, ou compartilhado com
    Honorários? (Decisão do `arquiteto-senior`, registrada aqui como
    dependência externa.)
17. **(FIS-42)** Entre NFCom, CT-e, GTVe e BP-e (juntos 1% do acervo,
    RC-65), qual vale a pena implementar primeiro, se algum?
18. **(FIS-43, FIS-88, FIS-91)** A carteira do Fred atende algum
    segmento especializado (combustíveis, imobiliário, comunicação/
    energia, saúde)?
19. **(FIS-59 a FIS-70)** Para cada obrigação da onda 11 e das guias da
    onda 9: quais UFs e municípios a carteira do Fred atende hoje, e
    quais obrigações são efetivamente exigidas para cada um? **Esta é a
    pergunta mais recorrente do documento** — sem ela, nenhuma alíquota
    ou leiaute municipal/estadual pode ser confirmado.
20. **(FIS-61)** Qual é o único município que concentra 82% das notas de
    serviço do acervo amostrado (RC-71 do
    [mapa-funcional-fiscal.md](../mapa-funcional-fiscal.md#a-ressalva-que-o-próprio-levantamento-fez-e-que-mantenho)),
    e qual sua legislação de ISS específica?
21. **(FIS-73)** O Fred autoriza o DataLedger a ler o formato de
    intercâmbio do sistema de gestão de XML que o escritório já usa?

