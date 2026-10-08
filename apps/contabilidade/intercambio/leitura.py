"""Entrada comum de qualquer arquivo de intercâmbio (DL-077, fatia 1).

Tudo que vem do arquivo e não depende do formato passa aqui: limite de
tamanho e de linhas (recusa nomeada, antes de qualquer leitura), SHA-256 do
conteúdo (token da prévia e chave da trilha) e nome do arquivo sem caminho.
"""

import hashlib
import os

from apps.contabilidade.intercambio.canonico import IntercambioRecusado
from apps.contabilidade.intercambio.formatos import LEITORES

# Limites da entrada. Um plano de contas real cabe folgado; o limite existe para
# recusar um arquivo absurdo antes de ele consumir memória e tempo, não para
# restringir o uso normal.
TAMANHO_MAXIMO_ARQUIVO_BYTES = 10 * 1024 * 1024
MAXIMO_DE_LINHAS = 200_000

TAMANHO_MAXIMO_NOME = 255


class ArquivoGrandeDemais(IntercambioRecusado):
    """Acima do limite de bytes ou de linhas. A API responde 413."""


class FormatoNaoSuportado(IntercambioRecusado):
    """Formato pedido que não está registrado em `LEITORES`. A API responde 400."""


def ler_arquivo(formato, conteudo, *, nome_arquivo=""):
    """Lê `conteudo` (bytes) com o leitor de `formato`, com as regras comuns.

    Levanta `ArquivoGrandeDemais` e `FormatoNaoSuportado` (ambos
    `IntercambioRecusado`). Conteúdo ruim NÃO levanta: vira ocorrência no
    `ResultadoLeitura`, como manda o contrato de `canonico.py`.
    """
    if formato not in LEITORES:
        raise FormatoNaoSuportado(
            f"formato '{formato}' não suportado nesta versão. "
            f"Use um destes: {', '.join(sorted(LEITORES))}."
        )
    if len(conteudo) > TAMANHO_MAXIMO_ARQUIVO_BYTES:
        raise ArquivoGrandeDemais(
            f"arquivo com {len(conteudo)} bytes; o limite é "
            f"{TAMANHO_MAXIMO_ARQUIVO_BYTES // (1024 * 1024)} MB."
        )
    linhas = conteudo.count(b"\n") + 1
    if linhas > MAXIMO_DE_LINHAS:
        raise ArquivoGrandeDemais(
            f"arquivo com cerca de {linhas} linhas; o limite é {MAXIMO_DE_LINHAS}."
        )

    resultado = LEITORES[formato](conteudo)
    resultado.formato = formato
    resultado.sha256 = hashlib.sha256(conteudo).hexdigest()
    resultado.nome_arquivo = os.path.basename(nome_arquivo or "")[:TAMANHO_MAXIMO_NOME]
    return resultado
