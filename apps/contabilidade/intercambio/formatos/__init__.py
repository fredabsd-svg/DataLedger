"""Registro dos formatos de intercâmbio (DL-077, fatia 1).

Ponto de extensão: um formato novo entra aqui, em `LEITORES` e (se escreve)
em `ESCRITORES`. A API aceita só o que está registrado, então acrescentar uma
chave é o único passo para um formato aparecer na importação e na exportação.

Assinatura de um leitor:  leitor(conteudo: bytes) -> ResultadoLeitura
Assinatura de um escritor: escritor(contas, *, data_alteracao=None) -> bytes

A frente B acrescenta `referencia` e `excel` aqui, quando os módulos existirem.
Nesta fatia, só ECD e formato próprio.
"""

from apps.contabilidade.intercambio.formatos import ecd, proprio

LEITORES = {
    ecd.FORMATO: ecd.ler,
    proprio.FORMATO: proprio.ler,
}

ESCRITORES = {
    ecd.FORMATO: ecd.escrever,
    proprio.FORMATO: proprio.escrever,
}
