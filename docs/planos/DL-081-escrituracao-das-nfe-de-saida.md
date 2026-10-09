# DL-081 — Fiscal: escrituração das NF-e de saída e devolução de venda

**Demanda:** ordem do Fred de 08/10/2026 (RC-164, reiterada na RC-170);
continuação do roteiro do [DL-067](DL-067-plano-do-modulo-fiscal.md) depois
da recepção ([DL-080](DL-080-recepcao-de-nfe.md)). **Estado:**
[fonte única](../agents/estado.md). **Branch:** `ccr-bf4b4a55-hpqgbp` →
`main`. **Risco:** nível 1 (§3.1): a NF-e escriturada passa a compor a receita
bruta do Simples e o RBT12. Auditoria independente: uma rodada, uma correção
e uma reconferência.

**Escriturar e conferir, nunca apurar ICMS nem gerar guia.** A NF-e de saída
escriturada entra na receita do mês. O ICMS, o pré-DAS de comércio e a
integração com o Presumido ficam para as etapas seguintes. Até lá, esses
cálculos **avisam** que há receita de NF-e e não a ignoram em silêncio.

## Base

[Consulta ao contador-senior sobre a escrituração das NF-e](../projeto/consultas/2026-10-09-contador-senior-escrituracao-nfe.md),
de 09/10/2026. Foram lidos no Planalto a LC 123, a Lei 9.430, o DL 1.598, as
Leis 9.249, 9.718 e 10.147 e a LC 214. A Res. CGSN 140 foi lida em cópia
íntegra, e o XSD do PL 010f e o MOC 7.0 foram lidos na fonte oficial. A
**tabela de CFOP** vem do Portal Nacional da NF-e: é a tabela de apoio do
Informe Técnico 2023.002 v2.10, publicada em 04/09/2026, com 619 códigos e os
indicadores `indNFe` e `indDevol`. Baixei a planilha em 09/10/2026 de
`https://www.nfe.fazenda.gov.br/portal/exibirArquivo.aspx?conteudo=74KmX8poGpM=`;
o sha256 é
`577e05eec452294945d0e9df1f9bb9b21a4af115938e75ec74cf6a541ae4dacf`. O
próprio informe ressalva que o Convênio s/nº de 1970 prevalece em caso de
divergência. A tabela entra como dado com fonte. Cada faixa de CFOP mistura
usos diferentes (venda, devolução, anulação), por isso a devolução é
identificada pelo indicador `indDevol` da tabela, nunca pela faixa. Hipóteses
HI-117 a HI-124 e pendência PE-85.

## Escopo (primeiro corte)

1. **Quais notas.**
   - Saídas próprias: a empresa é emitente, `tpNF` 1, `finNFe` 1, modelos 55
     e 65. São 611 das 618 notas do acervo.
   - Devolução de venda recebida (`finNFe` 4): nota de terceiro em que a
     empresa é destinatária, ou nota própria de entrada.
   - Notas com `finNFe` 2, 3, 5 ou 6 são marcadas como "ajuste" e ficam fora
     da receita, com pendência nomeada.
2. **Itens lidos do XML guardado.**
   - Tabela própria de itens da NF-e, com os campos tipados em `Decimal`:
     CFOP, NCM, CEST, origem, CST ou CSOSN e os grupos de ICMS, ICMS-ST,
     FCP, DIFAL, IPI, PIS, Cofins, ISSQN e IBS/CBS (este último bruto).
   - O produto lê esses campos, mas não os interpreta. Eles ficam guardados
     para a apuração futura do ICMS.
   - Os caminhos vêm do XSD do PL 010f, com arquivo e linha.
3. **Natureza por item.**
   - Catálogo fechado das quatorze naturezas da consulta (item 2), mais a
     natureza "ajuste".
   - A natureza é **sugerida** pela combinação `finNFe` → CFOP → CST/CSOSN →
     NCM. Quando os sinais conflitam, a sugestão fica em branco.
   - O contador **confirma em bloco** os itens de mesmo sinal.
   - Comercial exportadora, monofásico e bonificação incondicional não têm
     sugestão: dependem de fato que está fora da nota.
4. **Escrituração** no desenho da DL-072: rascunho, efetivação e estorno com
   motivo, imutável no banco depois de efetivada, e cancelamento posterior
   transformado em pendência. A competência é o mês de `dhEmi`.
5. **Receita bruta por item** (HI-119): `vProd − vDesc + vFrete + vSeg +
   vOutro`. `vST`, `vIPI` e `vII` ficam fora.
   - A soma tem de bater com `vNF − vST − vIPI − vII − vIPIDevol`, com
     tolerância zero. Se não bater, a efetivação é bloqueada, nunca ajustada
     em silêncio.
   - Natureza que não é receita (remessa, transferência, bonificação atestada,
     CFOP 5.929, ajuste) soma zero e aparece à parte.
6. **Receita do Simples e RBT12.** A composição do mês (DL-074) passa a somar
   as NF-e efetivadas, por mercado: interno, ou externo quando há exportação.
   - A devolução de venda deduz no **mês da devolução**, e o saldo que
     exceder a receita do mês passa para os meses seguintes (Res. CGSN 140,
     art. 17; HI-121).
   - O cancelamento continua deduzindo no período de origem (art. 18).
7. **Proteção dos cálculos que ainda não sabem tratar mercadoria:**
   - o **pré-DAS** (DL-075, só serviços) recusa o mês que tiver receita de
     NF-e, com o motivo nomeado;
   - a **apuração do Presumido** (DL-079) fica "parcial" no trimestre com NF-e
     de saída efetivada, avisando que a receita de mercadoria não foi
     integrada.
8. **Avisos de IBS/CBS em 2026** (HI-123):
   - grupo presente em nota de CRT 1, 2 ou 4;
   - grupo ausente em nota de CRT 3 emitida a partir de 03/08/2026;
   - `vNFTot` diferente de `vNF + IBS + CBS + IS`.

   Nada disso entra na receita.
9. **Conferência** (classe "conferência"):
   - receita do mês por natureza e por CFOP;
   - recebidas × escrituradas × pendentes por empresa e mês;
   - canceladas, e escrituradas que foram canceladas depois;
   - itens sem sugestão.
10. **Reclassificação em massa por filtro** (CFOP, CST/CSOSN, NCM e período),
    só em rascunho, com trilha. É a função que o mapa funcional aponta como a
    que mais economiza tempo.
11. Telas e API, com isolamento e permissões como nas DL-072 e DL-080.

**Fica fora**, com pendência nomeada:

- escrituração das entradas (compras e créditos);
- apuração do ICMS-TO, ST, DIFAL e FECOEP;
- pré-DAS de comércio e indústria (Anexos I e II, com ST, monofásico e
  exportação);
- integração da receita de NF-e ao Presumido;
- benefício estadual de ICMS;
- tabela de NCM monofásico;
- regime monofásico de ICMS dos combustíveis;
- notas complementar, de ajuste, de crédito e de débito como ajustes;
- venda para entrega futura e venda à ordem;
- venda de ativo imobilizado;
- serviço em NF-e conjugada no pré-DAS;
- regime de caixa;
- manifestação do destinatário;
- regras de 2027 (IBS e CBS no `vProd`, Res. CGSN 190/2026);
- integração contábil.

## Decisões tomadas na implementação (frente A)

- **Campos opcionais com zero** (`vDesc`, `vFrete`, `vSeg` e `vOutro` iguais
  a `0.00`): a nota é tratada como ilegível. O padrão `TDec_1302Opc` do XSD
  não aceita zero em campo opcional, porque o emissor deve omitir o campo, e
  o autorizador valida o esquema.
- **ICMS desonerado que reduz o total** (`vICMSDeson` com `indDeduz` 1): a
  conferência com o `vNF` falha e a efetivação é bloqueada. É uma falha
  fechada: a regra de receita nesse caso fica para o Fred (PE-85) e para o
  BL-685.
- **`vNF` ausente** bloqueia, em vez de valer zero, porque o campo é
  obrigatório no XSD.
- **Devolução:** não é ligada à nota de origem (o `NFref` não é lido),
  deduz no mês em que ocorre e entra sempre no mercado interno. A devolução
  de exportação fica no BL-685.
- **Proteção ampliada:** o pré-DAS recusa e o Presumido fica parcial também
  no mês ou trimestre que recebe só devolução ou saldo de devolução.
- **Serviço em NF-e conjugada** (natureza 14) entra no RBT12, que soma toda a
  receita bruta, e continua recusado no pré-DAS e no Presumido.

## Critérios de aceite

1. Os itens e os campos lidos batem com o XSD do PL 010f, com o caminho
   citado. Campo ausente fica ausente, nunca zero.
2. A sugestão de natureza está correta nos sinais da consulta, item 2:
   CSOSN 500, CSOSN 201, `idDest` 3, CFOP 5.929, `finNFe` 4, transferência.
   Conflito deixa a sugestão em branco. O contador troca a natureza, em bloco
   ou por item.
3. Receita bruta por item igual à fórmula, com valores escritos à mão: o
   exemplo do Simples da consulta (receita de 2.880,00 numa nota de
   2.970,00) e o do Presumido (9.900,00 numa nota de 10.700,00). Divergência
   com o `vNF` bloqueia a efetivação.
4. Imutabilidade depois da efetivação em todas as portas, inclusive por SQL
   direto. Estorno exige motivo. Nota cancelada depois de escriturada vira
   pendência e sai da receita.
5. A receita do mês e o RBT12 somam NFS-e e NF-e efetivadas, por mercado. A
   devolução deduz no mês da devolução, com saldo transportado. Rascunho,
   estornada e cancelada não entram. Natureza que não é receita soma zero.
6. O pré-DAS recusa o mês com receita de NF-e, com motivo nomeado. O
   Presumido fica parcial no trimestre com NF-e. Nada muda nos meses e
   trimestres sem NF-e.
7. Os avisos de IBS/CBS disparam no caso que os justifica, e só nele.
8. A reclassificação em massa só altera rascunho, registra trilha e não toca
   nota de outra empresa.
9. Isolamento entre escritórios e empresas, e permissões verificadas no
   servidor.
10. Mutação: cada um destes defeitos derruba testes:
    - somar `vST` na receita;
    - usar `vNF` direto;
    - deduzir a devolução no período de origem;
    - contar remessa como receita;
    - aceitar divergência com o `vNF`;
    - reclassificar nota efetivada;
    - remover o filtro de empresa.
11. Não regressão completa numa única invocação. Migração aditiva e
    reversível.

## Divisão

Começa **depois** de a DL-080 entrar na branch, porque usa as tabelas da
recepção da NF-e.

| Frente | Quem | Arquivos |
| --- | --- | --- |
| A — itens, natureza, escrituração, receita, proteção dos cálculos, avisos, API | `auxiliar-implementacao` (Haiku), em cópia isolada | `apps/fiscal/` (módulos novos `escrituracao_nfe.py` e `itens_nfe.py`; ajustes em `receita.py`, `pre_das.py` e `presumido.py`), modelos, migração, testes `test_dl081_*` |
| B — telas: escriturar, conferência, reclassificação em massa | `auxiliar-implementacao` (Haiku), depois da frente A | `views_web.py`, `urls_web.py`, `templates/fiscal/`, inventários |
| Auditoria | `auditor-qa` (Sonnet) | sem escrita |

## Reversão

As tabelas são novas. A composição da receita volta a ler só NFS-e quando a
migração e o merge são revertidos.
