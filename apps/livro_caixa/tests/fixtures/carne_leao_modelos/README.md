# Arquivos-modelo oficiais do Carnê-Leão Web (fixture de teste)

Estes seis arquivos são cópia byte a byte dos modelos que a Receita Federal
publica para download em "Escrituração" → "Baixe o modelo", no Carnê-Leão
Web — arquivos-modelo de uso público, distribuídos exatamente para que o
contribuinte construa o próprio arquivo de importação a partir deles.
Fonte: "Instruções para Utilização dos Arquivos de Modelos para Importação
da Escrituração no Carnê Leão Web 2025" (Receita Federal), consultada em
2026-09-26/2026-09-27, junto com a página oficial "Formato do arquivo de
Escrituração" (publicada em 10/07/2023, atualizada em 21/10/2025).

Preservados **sem nenhuma alteração de conteúdo** — mesma codificação
(ISO-8859-1), mesma quebra de linha (CRLF) e mesmos campos de cada arquivo
original. Só o **nome do arquivo** foi normalizado (sem espaço nem acento),
para portabilidade entre sistemas de arquivo; o mapeamento é:

| Arquivo aqui | Nome original |
| --- | --- |
| `trabalho_nao_assalariado.csv` | Modelo de arquivo para rendimentos do Trabalho não Assalariado.csv |
| `servicos_notariais_e_registro.csv` | Modelo de arquivo para rendimentos de Serviços Notariais e de Registro.csv |
| `aluguel_e_outros_rendimentos.csv` | Modelo de Arquivo para Aluguel e Outros rendimentos.csv |
| `recibos_receita_saude.csv` | Modelo de arquivo para recibos do Receita Saúde.csv |
| `pagamentos_gerais.csv` | Modelos de Arquivo para Pagamentos.csv |
| `pagamentos_plano_de_contas_padrao.csv` | Modelos de Arquivo para Pagamentos do Plano de Contas padrão.csv |

## Para que servem

São o **oráculo** dos testes de `apps/livro_caixa/tests/test_dl046_fatia3_*`:
os testes leem cada arquivo em bytes, trocam os placeholders do modelo
(`99/99/9999`, `999999999,99`, `999`, "Modelo de linha para...") pelos
valores de um lançamento sintético do teste, e comparam campo a campo — em
posição, contagem e formato — com a linha gerada pelo serviço
`apps.livro_caixa.carne_leao_arquivos.gerar_arquivos_carne_leao`. Isso
prova que o gerador reproduz o leiaute oficial, sem depender de uma
transcrição manual do formato que poderia divergir do arquivo real.

## O que NÃO está nesta fatia

`recibos_receita_saude.csv` está aqui pela mesma razão de completude (os
seis modelos formam um conjunto), mas **não é usado como oráculo de
geração**: recibos do Receita Saúde estão fora do escopo da fatia 3 do
plano [DL-046](../../../../../docs/planos/DL-046-livro-caixa-e-carne-leao.md)
— o sistema não tem, hoje, um indicador de "recibo emitido" no lançamento,
e o leiaute desse arquivo (16 campos, com CPF do profissional e registro
profissional) é diferente do modelo comum de trabalho não assalariado.

## Dados sintéticos, nunca reais

Os PLACEHOLDERS destes arquivos (`99999999999`, `99999999999999`, datas
`99/99/9999`) nunca foram substituídos por CPF, CNPJ ou dado de cliente
real — nem aqui, nem nos testes que os leem. Os valores usados nos testes
são sintéticos (mesmos CPF/CNPJ de teste já usados no resto da suíte deste
módulo).
