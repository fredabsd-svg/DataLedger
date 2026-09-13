# Fontes de referência do domínio

Onde buscar informação de domínio contábil-fiscal ao planejar ou implementar,
e como usá-la sem copiar.

Registrado a pedido do Fred em 2026-09-12, para que sessões futuras não
precisem redescobrir.

## Regra de uso, antes de tudo

Estas fontes servem para entender **o que** o escritório precisa e **como o
domínio funciona**. Não servem para copiar texto, telas, nomenclatura de menu
ou estrutura de interface.

- **Nada de material de terceiros entra neste repositório**, nem em trechos.
- O que entra é **requisito escrito por nós**, em nossas palavras.
- Formato de intercâmbio documentado é caso à parte: ler um formato publicado
  para interoperar é diferente de copiar produto. Ainda assim, ver a decisão
  pendente no [mapa funcional](mapa-funcional-fiscal.md).

Orientação do Fred: *"não faça igual"*. É também o que o
[README](../../README.md) já registrava.

## 1. Manuais dos módulos do sistema de referência

Diretório público indicado pelo Fred:

```
https://ftpdownload.dominiosistemas.com.br/manuais/
```

Contém manual de **cada módulo**, útil como mapa de capacidades quando formos
planejar o módulo correspondente:

| Arquivo | Serve para planejar |
| --- | --- |
| `Domínio Escrita Fiscal.pdf` | Fiscal — **já analisado**, ver [mapa funcional](mapa-funcional-fiscal.md) |
| `Domínio Contabilidade.pdf` | Contabilidade — **já analisado**, ver [mapa funcional contábil](mapa-funcional-contabil.md) |
| `Domínio Folha.pdf` | Folha de pagamento |
| `Domínio Honorários.pdf` | Honorários |
| `Domínio Processos.pdf` | Processos e paralegal |
| `Domínio Patrimônio.pdf` | Ativo imobilizado e depreciação |
| `Domínio Lalur.pdf` | Apuração do lucro real |
| `Domínio Ponto Eletrônico.pdf` | Ponto, ligado a Folha |
| `Domínio Registro.pdf`, `Domínio Protocolo.pdf` | Documentos e protocolo |
| `Domínio Auditoria.pdf` | Auditoria interna |
| **`Importação Padrão.pdf`** | **Formato de intercâmbio** — o mais relevante hoje |
| **`leiautes.zip`** | Leiautes de importação: produtos, notas de entrada e de saída |

**Atenção à data.** O manual fiscal analisado é de **2018**. Os demais
provavelmente também. Serve como mapa de **capacidades**, nunca como fonte de
**regra tributária vigente**.

## 2. Pesquisa na internet — técnica indicada pelo Fred

> Para dúvida sobre o sistema de referência ou sobre a rotina do domínio,
> pesquisar **"domínio sistemas" + a dúvida**. A base de conhecimento e os
> materiais de treinamento do fornecedor costumam responder.

Use para entender **conceito e rotina** — o que é um acumulador, como se
concilia uma apuração, o que o contador espera ver numa conferência.

**Não use para obter regra tributária vigente.** Conteúdo de fornecedor
envelhece e não é fonte oficial.

## 3. Fontes oficiais — obrigatórias para qualquer cálculo

Para **toda** regra que vire cálculo, alíquota, prazo, leiaute de obrigação ou
validação, a fonte tem de ser oficial e **vigente**:

| Assunto | Fonte |
| --- | --- |
| NF-e, NFC-e: leiaute, notas técnicas, regras de validação | [Portal Nacional da NF-e](https://www.nfe.fazenda.gov.br) e o Manual de Orientação do Contribuinte |
| SPED (Fiscal, Contribuições, ECD, ECF), EFD-Reinf | [Portal do SPED](http://sped.rfb.gov.br) |
| Tributos federais, obrigações, e-CAC | [Receita Federal](https://www.gov.br/receitafederal) |
| ICMS, convênios e protocolos | [CONFAZ](https://www.confaz.fazenda.gov.br) e a SEFAZ do estado |
| ISS | Legislação do **município**, que varia caso a caso |
| Folha, eSocial, FGTS | Manuais oficiais do eSocial e legislação trabalhista |
| Arredondamento | Ver [DE-010](decisoes.md), que já levantou as fontes por obrigação |

Regra do [AGENTS.md](../../AGENTS.md) §10 que vale repetir: **não inventar
alíquota, incidência, prazo, fórmula ou leiaute**. Regra destinada a uso real
exige caso de referência e validação do responsável técnico — o Fred.

## 4. Como registrar o que for pesquisado

Ao usar qualquer destas fontes:

1. Registre **a fonte e a data** da consulta junto do requisito.
2. Classifique como **confirmado**, **hipótese** ou **pendência** em
   [requisitos.md](requisitos.md).
3. Se for regra com vigência, registre **a vigência**, não só o valor.
4. Material de terceiros fica **fora do repositório**. Baixe para área
   temporária, extraia o entendimento, escreva o requisito com suas palavras.

## 5. Sobre validade no tempo

A **Reforma Tributária do Consumo** está em implantação e altera de forma
profunda o cenário de tributos sobre consumo. Qualquer levantamento feito sobre
material antigo carrega esse risco.

Consequência prática de engenharia, já decidida em
[DE-010](decisoes.md): regra tributária é **dado versionado por vigência**,
não código. Um sistema que exige alteração de código a cada norma nova não
sobrevive a uma reforma.
