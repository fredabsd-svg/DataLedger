# DL-010 fatia 1 — Recepção e conferência de NFS-e nacional

**Demanda:** ordem do Fred em 25/09/2026 (*"concordo com você, pode
prosseguir"*), depois da análise que recomendou a recepção de notas como próxima
entrega. Plano-mãe: [DL-010](DL-010-recepcao-de-documentos-fiscais.md), cujos
critérios 1 a 22 continuam valendo e são reproduzidos aqui por número.
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** (§3.1 do [AGENTS.md](../../AGENTS.md)) — isolamento
entre empresas e dado do cliente. Plano completo, testes de sucesso, erro e
limite, e **auditoria independente** da versão integrada.
**Branch:** `claude/vigilant-bardeen-jo12l4` (branch designada pela sessão),
destino `main`.

## Objetivo

O escritório envia o ZIP (ou os XMLs) que já exporta hoje da ferramenta de
gestão de XML (RC-41, RC-47) e o DataLedger:

1. reconhece cada NFS-e nacional **pelo conteúdo** (RC-71);
2. associa a nota à empresa do escritório que é **prestadora ou tomadora**;
3. não duplica o que já recebeu (RC-69, RC-74);
4. guarda os eventos, inclusive os que chegam sem a nota (RC-70), e nunca
   apresenta nota cancelada como válida;
5. mostra, por envio, o que entrou, o que já existia e o que foi recusado e
   por quê.

**Fora desta fatia, declarado:** NF-e, NFC-e, NFCom, CT-e e GTVe (reconhecidas
e recusadas com o motivo "tipo ainda não suportado"); SPED; classificação
fiscal; apuração; contabilização; interpretação do bloco IBS/CBS (PE-39 — o XML
original é guardado inteiro, então nada se perde); API REST e MCP (as regras
ficam na camada de serviço e serão reusadas); processamento em segundo plano;
admin do Django para os novos modelos (o admin não isola por escritório,
BL-262).

## Fonte oficial do leiaute

Esquemas XSD oficiais do Portal Nacional da NFS-e, pacote
`NFSe-ESQUEMAS_XSD-v1.01-20260209` (SE/CGNFS-e), consultados em 25/09/2026.
Fatos usados neste plano (RC-111):

| Item | Onde |
| --- | --- |
| Raiz e versão | `NFSe/infNFSe`, atributo `versao` restrito a `1.00` e `1.01` |
| Identificador | `infNFSe/@Id` = `NFS` + 50 dígitos; os 50 dígitos são: município (7), ambiente (1), tipo de inscrição (1), inscrição federal (14), número (13), ano e mês (4), código numérico (9) e DV (1) |
| Número | `infNFSe/nNFSe` — **não** é chave (RC-74) |
| Emissão e competência | `infNFSe/DPS/infDPS/dhEmi` e `infNFSe/DPS/infDPS/dCompet`; `infNFSe/dhProc` é o processamento, não a emissão |
| Prestador | `infNFSe/emit` (CNPJ ou CPF) |
| Tomador | `infNFSe/DPS/infDPS/toma`, **opcional**; CNPJ, CPF, NIF ou `cNaoNIF` |
| Valores | `vServ` dentro de `DPS/infDPS/valores`; `vLiq` em `infNFSe/valores/vLiq`; decimal com ponto e duas casas |
| Retenção de ISS | `DPS/infDPS/valores/trib/tribMun/tpRetISSQN`: 1 não retido, 2 retido pelo tomador, 3 retido pelo intermediário (RC-110) |
| Evento | Raiz `evento/infEvento`, com `pedRegEvento/infPedReg/chNFSe` aninhado; código do evento como elemento `e` + seis dígitos |
| IBS/CBS | `infNFSe/IBSCBS` e `DPS/infDPS/IBSCBS`, **só na 1.01** |

⚠️ **Limite declarado:** no XSD vigente o `Id` só admite dígitos. O efeito do
CNPJ alfanumérico sobre a chave da NFS-e **não foi confirmado em fonte
oficial**. O leitor confere o **formato** do `Id` pelo XSD e **não confere o
DV**, até haver fonte.

## Decisões desta fatia (DE-074)

1. **App novo `apps/fiscal`.** Entra em `INSTALLED_APPS` **antes** de
   `apps.documentos`, que precisa continuar o último (comentário em
   `config/settings.py`).
2. **O XML original é guardado byte a byte** no banco, com SHA-256. É a fonte da
   verdade para o que ainda não se extrai (IBS/CBS). O volume do acervo medido
   (5.850 arquivos) cabe no PostgreSQL sem armazenamento externo.
3. **Leitura segura:** `defusedxml`, com DTD proibido. É a única dependência
   nova, justificada: o arquivo vem de terceiro, e XML com entidade externa ou
   expansão exponencial é o ataque clássico a importador.
4. **Deduplicação por escritório e identificador:** restrição única
   `(escritorio, identificador)`. A mesma nota em duas pastas de clientes do
   mesmo escritório (RC-69) é **um** documento com **dois vínculos**, um por
   empresa e papel (prestador/tomador). Escritórios diferentes nunca
   compartilham registro nem ficam sabendo um do outro.
5. **Situação derivada, não gravada:** "cancelada" é consultada nos eventos do
   mesmo escritório cuja chave referencia a nota. Assim a ordem de chegada (nota
   antes ou depois do evento) não importa e não há estado para envelhecer.
6. **Processamento síncrono com limites** (HI-22), cada arquivo no seu
   `savepoint`: arquivo ruim não derruba o envio (critério 8), e duas
   importações simultâneas da mesma nota resultam em **um** documento.
7. **Identificação da empresa em um ponto só** (critério 13): uma função que
   recebe o escritório e as inscrições e procura em `Empresa.cnpj` e
   `Estabelecimento.cnpj`, **sempre filtrando pelo escritório** — o CNPJ é
   único no sistema inteiro (PE-21) e a busca sem filtro acharia empresa de
   outro escritório.

## Etapas e responsáveis

Execução **em sequência**, com arquivos disjuntos.

| Ordem | Responsável | Entrega | Arquivos permitidos |
| --- | --- | --- | --- |
| 0 | `desenvolvedor-pleno` | **BL-54**: restrição de banco do CNPJ passa a exigir formato `^[A-Z0-9]{12}[0-9]{2}$` em `Empresa` e `Estabelecimento` (pré-requisito declarado no backlog para importar em lote) | `apps/empresas/models.py`, nova migração em `apps/empresas/migrations/`, testes em `apps/empresas/tests/` |
| 1 | `desenvolvedor-pleno` | Modelos, leitor, recepção, identificação, permissões, trilha e testes de servidor | `apps/fiscal/**` exceto telas; `config/settings.py` (só `INSTALLED_APPS`); `requirements/base.txt` (só `defusedxml`); listas de guarda que a suíte exigir, sem enfraquecer nenhuma |
| 2 | `especialista-frontend` | Telas de envio, relatório do envio, lista e detalhe de documentos, com testes de tela | `apps/fiscal/views_web.py`, `apps/fiscal/urls_web.py`, `config/urls.py` (só o `include`), `templates/fiscal/**`, `static/` se necessário, `apps/fiscal/tests/test_telas_*.py`, listas de guarda de interface e acessibilidade |
| 3 | `auditor-qa` | Auditoria independente da versão integrada | nenhum (somente leitura) |
| — | `arquiteto-senior` | Plano, requisitos, decisões, estado, revisão e integração | `docs/**` |

## Contrato entre servidor e tela

A camada de serviço (etapa 1) expõe, em `apps/fiscal/services.py`:

- `receber_envio(*, escritorio, usuario, arquivo, nome_arquivo) -> LoteDeRecepcao`
  — processa XML solto ou ZIP; nunca levanta exceção por arquivo ruim; levanta
  erro de validação só para o envio inteiro inválido (vazio, grande demais, ZIP
  corrompido).
- `documentos_do_escritorio(escritorio, *, empresa=None, competencia=None, situacao=None)`
  — consulta sempre filtrada pelo escritório.
- `situacao_do_documento(documento) -> str` — `valida` ou `cancelada`, derivada
  dos eventos.
- As permissões ficam em `apps/fiscal/permissoes.py`, como fonte única, no molde
  de `apps/contabilidade/permissoes.py`: `papel_pode_receber_documentos(papel)` e
  `papel_pode_consultar_documentos(papel)` (HI-21).

Modelos mínimos: `LoteDeRecepcao` (envio: escritório, usuário, data, nome e
SHA-256 do arquivo enviado, contagens), `ResultadoDoArquivo` (uma linha por
arquivo do envio: caminho dentro do ZIP só para exibição, resultado, motivo,
documento ou evento), `DocumentoFiscal`, `VinculoDocumentoEmpresa` e
`EventoFiscal` (identificador próprio do evento, chave da nota referenciada,
código, data, XML original). Nomes finais são do implementador; o contrato acima
não.

## Critérios de aceite

Os do plano-mãe, **1 a 8 e 10 a 22**, valem integralmente para a NFS-e
(o 9 foi retirado lá). Acrescentam-se:

| # | Critério |
| --- | --- |
| 23 | **BL-54 fechado:** `bulk_create` de `Empresa` e de `Estabelecimento` com `''`, `'ABC'` e `'AB123CDE0001AA'` levanta `IntegrityError`; a migração aplica em banco vazio e em base com CNPJs válidos |
| 24 | **XML hostil é recusado com motivo, sem efeito colateral:** DTD, entidade externa e expansão de entidades; o envio continua para os demais arquivos |
| 25 | **ZIP hostil é recusado:** acima do limite de tamanho, de quantidade de arquivos ou de tamanho descompactado (HI-22), ZIP dentro de ZIP e ZIP cifrado — com motivo, e sem consumir memória proporcional ao conteúdo descompactado |
| 26 | **Autorização no servidor:** papel sem permissão recebe 403 ao enviar e ao consultar, testado por requisição; sem sessão, redireciona ao login; `CLIENTE` não envia nem consulta |
| 27 | **Isolamento em todas as portas:** documento, envio, evento e download do XML de outro escritório devolvem **404**, nunca 403, e a mensagem de recusa do critério 5 é **idêntica** exista ou não a empresa em outro escritório |
| 28 | **Concorrência:** duas recepções simultâneas da mesma nota, em PostgreSQL, resultam em um documento e um resultado "duplicado"; nenhuma falha 500 |
| 29 | **XML original preservado:** o download devolve exatamente os bytes recebidos (mesmo SHA-256), como anexo e com tipo XML — nunca renderizado como HTML |
| 30 | **Situação:** nota com evento de cancelamento aparece como cancelada nas duas ordens de chegada; os códigos que cancelam seguem a HI-20; evento de outro tipo não cancela |
| 31 | **Trilha:** cada envio gera registro de auditoria na mesma transação, com contagens e SHA-256 do arquivo, **sem** conteúdo do XML nem dado de terceiro |
| 32 | **Valores:** `vServ` e `vLiq` entram por `Decimal` a partir do texto; valor com vírgula, negativo, com mais de duas casas ou não numérico recusa o arquivo com motivo |
| 33 | **Telas:** envio, relatório do envio, lista e detalhe funcionam **sem JavaScript**, com os estados vazio, erro, sucesso e sem permissão, e entram na suíte de acessibilidade existente |
| 34 | Sem regressão: suíte completa, `ruff check`, `ruff format --check`, `manage.py check`, `makemigrations --check`, `migrate` em banco vazio |

## Cenários de teste obrigatórios

Com XMLs **sintéticos**, montados nos testes a partir do leiaute oficial — nenhum
arquivo do acervo do Fred entra no repositório.

- Sucesso: 1.00 e 1.01; prestador cliente; tomador cliente; os dois clientes
  (um documento, dois vínculos); ZIP com várias notas; XML solto.
- Duplicidade: mesmo arquivo reenviado; mesmo XML em outro ZIP; mesma nota em
  duas pastas; mesma nota com nome de arquivo diferente; notas diferentes com o
  mesmo número de emitentes distintos coexistindo.
- Evento: evento antes da nota; nota antes do evento; evento órfão sem nota;
  evento duplicado; evento de tipo que não cancela.
- Recusa: prestador e tomador fora do escritório; tomador ausente e prestador
  fora; versão não suportada; `Id` fora do formato; XML malformado, truncado,
  vazio; NF-e e outros tipos; nome de arquivo enganoso (RC-71).
- Variação de arquivo (RC-75): sem declaração de codificação, `UTF-8` maiúsculo e
  minúsculo, CRLF, minificado e indentado, acento em razão social, CNPJ com zero
  à esquerda.
- Limites: envio vazio; no limite e acima do limite de tamanho e de quantidade.

## Impacto, riscos e reversão

- **Dados:** tabelas novas, migração aditiva; a migração do BL-54 só **restringe**
  o CNPJ e pode falhar se houver dado fora do formato — o teste de migração em
  base representativa cobre isso.
- **Segurança:** arquivo de terceiro é a principal superfície de ataque; tratada
  pelos critérios 24, 25 e 29.
- **Desempenho:** 10.000 arquivos por envio em uma requisição é o teto aceito
  nesta fatia (HI-22). Se a rotina real exigir mais, o próximo passo é
  processamento em segundo plano, e não aumentar o limite.
- **Reversão:** reverter o merge e a migração do `apps/fiscal` (sem dado contábil
  envolvido). A migração do BL-54 é reversível.

## Limites declarados

- Cliente **pessoa física** (prestador com CPF) não tem onde ser cadastrado hoje:
  `Empresa` só aceita CNPJ. Essas notas serão recusadas com motivo (PE-66).
- A recepção **não** foi rodada contra o lote real do escritório; os testes usam
  arquivos sintéticos. Rodar contra o acervo é o primeiro uso real e fica
  pendente até o Fred fazê-lo.
- A retenção de ISS é **lida e exibida**, não interpretada nem calculada.

## Evidências

Preenchidas ao fim de cada etapa: comandos executados e saída, commits, PR e
parecer da auditoria.
