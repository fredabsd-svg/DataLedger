# DL-038 — Cliente pessoa física no cadastro de empresas

**Demanda:** Fred, 25/09/2026. O escritório atende pessoa física que emite NFS-e
com CPF (RC-112) e faz para ela carnê-leão e livro-caixa (RC-113). Ele escolheu a
**opção A** da PE-67: o mesmo cadastro de empresas passa a aceitar CPF, com modo de
escrituração por empresa (RC-114, DE-075).
**Estado:** o estado desta etapa mora em [estado.md](../agents/estado.md).
**Nível de risco: 1** — cadastro central, isolamento entre empresas e migração de
dados. **Branch:** `claude/vigilant-bardeen-jo12l4` → `main`.
**Depende de:** servidor da [DL-010 F1](DL-010-F1-recepcao-nfse.md) concluído
(os dois trabalhos alteram `apps/empresas/models.py`; execução em sequência).

## Objetivo

Cadastrar o cliente pessoa física no **mesmo** cadastro de empresas, para que:

1. as NFS-e com CPF no prestador ou no tomador passem a ser recebidas pela DL-010;
2. exista o lugar onde o livro-caixa e o carnê-leão vão se apoiar, em etapa futura;
3. a contabilidade por partidas dobradas **não** seja aplicada por engano a quem
   escritura livro-caixa.

**Fora desta etapa:** livro-caixa, carnê-leão, CAEPF e qualquer cálculo de imposto
de pessoa física. Esses exigem fonte oficial da Receita Federal e serão um módulo
próprio, planejado depois.

## Requisitos

| # | Requisito |
| --- | --- |
| R1 | A empresa tem **tipo de inscrição**: CNPJ ou CPF. As existentes migram como CNPJ, sem alteração de dado |
| R2 | CPF é validado pelo dígito verificador com **fonte oficial citada no código**; guardado como texto de 11 dígitos, sem máscara, preservando zero à esquerda |
| R3 | Unicidade do CPF segue a política atual do CNPJ, global (a PE-21 continua aberta e vale para os dois) |
| R4 | A empresa tem **modo de escrituração**: contabilidade ou livro-caixa. Existentes migram como contabilidade. Nova empresa com CPF sugere livro-caixa (HI-23) |
| R5 | A contabilidade por partidas dobradas **recusa no servidor**, com mensagem clara, toda operação e toda tela para empresa em modo livro-caixa — em **um ponto só** do código |
| R6 | Não é possível passar para livro-caixa uma empresa que já tem plano de contas ou lançamento; a recusa diz por quê |
| R7 | Campos próprios de pessoa jurídica (NIRE e estabelecimentos) não são exigidos nem oferecidos para CPF |
| R8 | A identificação da DL-010 passa a casar CPF com empresa do escritório, pelo mesmo ponto único; a recusa específica de pessoa física passa a valer só quando o CPF não está cadastrado |
| R9 | Cadastro pela tela e pela API, com os mesmos papéis e o mesmo isolamento de hoje; a trilha registra criação e alteração como hoje |

## Critérios de aceite

1. Migração em banco vazio e em base com empresas existentes: todas ficam CNPJ e
   contabilidade; nenhum dado muda; a migração reverte.
2. CPF válido é aceito; DV errado, sequência repetida, tamanho errado e letras são
   recusados com mensagem; CPF com zero à esquerda é preservado.
3. CPF duplicado é recusado com 400, nunca 500, pela tela e pela API.
4. Empresa CPF em modo livro-caixa: todas as rotas da contabilidade (tela e API)
   recusam com a mesma mensagem, testado por varredura **derivada** das rotas
   existentes, não por lista escrita à mão.
5. Tentar mudar para livro-caixa com plano de contas ou lançamento existente é
   recusado; sem movimento, é permitido e fica na trilha.
6. NFS-e com prestador CPF cadastrado entra, vinculada à empresa certa; CPF de
   outro escritório continua recusado com a mesma mensagem de "não pertence"
   (critério 27 da DL-010 F1).
7. Nenhuma tela ou documento quebra com empresa CPF (lista, seletor, cabeçalho de
   identificação); onde se imprime a inscrição, o rótulo é "CPF", não "CNPJ".
8. Sem regressão; suíte completa, lint, formatação, `manage.py check` e
   `makemigrations --check`.

## Responsáveis e arquivos

| Ordem | Quem | Entrega | Arquivos |
| --- | --- | --- | --- |
| 1 | `desenvolvedor-pleno` | Modelo, migração, validação de CPF, serviços, API, recusa na contabilidade, identificação fiscal, documento emitido | `apps/empresas/**` exceto templates e formulários de tela; `apps/contabilidade/` (só o ponto único de recusa e seus testes); `apps/fiscal/` (identificação); `apps/documentos/` |
| 2 | `especialista-frontend` | Formulário e lista de empresas com tipo de inscrição e modo; estado de recusa da contabilidade | `apps/empresas/forms.py`, `templates/empresas/**`, `templates/contabilidade/**` (só a tela de recusa), testes de tela |
| 3 | `auditor-qa` | Auditoria independente da versão integrada | nenhum |

## Riscos e reversão

- **Migração no cadastro central:** aditiva (dois campos com padrão) e reversível.
  O campo do CNPJ passa a admitir vazio para CPF; as restrições do BL-54 continuam
  valendo sempre que o tipo for CNPJ.
- **Dado pessoal:** CPF é dado pessoal (LGPD). Não aparece em log nem na trilha
  além do que já aparece para o CNPJ; exibido só a quem já vê o cadastro.
- **Reversão:** reverter a migração só é segura sem empresa CPF cadastrada; com
  dado real, a correção é progressiva (nova migração), nunca apagar.

## Rodada 1 da auditoria

[Relatório integral](../auditorias/2026-09-25-dl-010-f1-dl-038-rodada-1.md):
**REPROVADA**, sem achado alto: B1 (admin com 500), B2 (estabelecimento
oferecido a empresa CPF, e a recepção vinculando por ele), B3 (varredura da
recusa sem exercitar escrita), B5 (tela e API decidem o modo de forma
diferente), mais B4, B7 e B8 de gravidade baixa. Todos com o
`desenvolvedor-pleno`. **B6** — a unicidade global revela a um escritório que o
CPF é cliente de outro — depende de decisão do Fred (PE-21 agravada).
