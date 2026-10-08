"""Registro dos formatos de intercâmbio (DL-077, fatia 1).

Ponto de extensão: um formato novo entra aqui, em `LEITORES` e (se escreve)
em `ESCRITORES`. A API aceita só o que está registrado, então acrescentar uma
chave é o único passo para um formato aparecer na importação e na exportação.

Assinatura de um leitor:  leitor(conteudo: bytes) -> ResultadoLeitura
Assinatura de um escritor: escritor(contas, *, data_alteracao=None) -> bytes

Frente B: `referencia` (leitor e escritor, leiaute com separador do sistema de
referência) e `excel` (só leitor: a planilha entra, a exportação não sai nela).
O escritor do `referencia` recebe o CNPJ/CPF da empresa (registro 0000); o núcleo
passa esse documento só aos formatos de `FORMATOS_QUE_PRECISAM_DO_DOCUMENTO`.
"""

from apps.contabilidade.intercambio.formatos import ecd, excel, proprio, referencia

LEITORES = {
    ecd.FORMATO: ecd.ler,
    proprio.FORMATO: proprio.ler,
    referencia.FORMATO: referencia.ler,
    excel.FORMATO: excel.ler,
}

ESCRITORES = {
    ecd.FORMATO: ecd.escrever,
    proprio.FORMATO: proprio.escrever,
    referencia.FORMATO: referencia.escrever,
}

# Escritores que recebem o documento da empresa (registro 0000). Os demais não
# aceitam esse argumento, e o núcleo não o passa a eles.
FORMATOS_QUE_PRECISAM_DO_DOCUMENTO = frozenset({referencia.FORMATO})

# Avisos que a exportação de cada formato leva ao contador (ASCII: vão em cabeçalho).
AVISOS_DE_EXPORTACAO = {
    referencia.FORMATO: referencia.AVISOS_DE_EXPORTACAO,
}
