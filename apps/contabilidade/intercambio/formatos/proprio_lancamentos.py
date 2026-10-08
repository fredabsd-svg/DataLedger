"""Formato próprio do DataLedger para lançamentos (DL-077, fatia 2).

Este docstring é a ESPECIFICAÇÃO do formato. O arquiteto copia o texto para a
documentação do projeto (`docs/`); o código não grava documento fora de si.

ESPECIFICAÇÃO DOS LANÇAMENTOS — versão 1
----------------------------------------

Codificação
    UTF-8, sem BOM na escrita.

Fim de linha
    CRLF (RFC 4180).

Separador
    Ponto e vírgula (`;`).

Cabeçalho
    A primeira linha é SEMPRE esta, com estes nomes e nesta ordem:

        numero;data;historico;conta;lado;valor

Linhas de dados
    UMA LINHA POR PARTIDA. As partidas de um mesmo lançamento saem em sequência,
    com o mesmo `numero`. Lançamentos saem ordenados por data e depois por número.

Campos
    numero    identificador estável do lançamento no DataLedger (inteiro). Repetido
              em todas as partidas do mesmo lançamento. Estorno e zeramento saem como
              qualquer outro lançamento.
    data      data do lançamento, no formato aaaa-mm-dd.
    historico histórico do lançamento (um só por lançamento; repetido em cada partida).
    conta     código da conta no DataLedger (`Conta.codigo`).
    lado      `D` para débito, `C` para crédito.
    valor     valor da partida, com PONTO decimal e exatamente DUAS casas
              (ex.: `1250.00`, `0.50`). Sem separador de milhar e sem sinal.

Escape (RFC 4180, com `;` como separador)
    Campo que contenha `;`, aspas duplas, CR ou LF vai entre aspas duplas. Aspas
    duplas dentro de um campo entre aspas são escritas duas vezes (`""`).

Saldos
    NÃO entram neste formato. Saldo e movimento por conta e mês existem só no leiaute
    da ECD (I150/I155).

Zeramento e estorno
    Não há coluna própria. Um lançamento de zeramento sai como qualquer outro. Quem
    precisa separá-lo usa o número do lançamento e a trilha.

Exemplo
    numero;data;historico;conta;lado;valor
    7;2026-03-10;Compra à vista;1.1.1;D;100.00
    7;2026-03-10;Compra à vista;2.1;C;100.00
    8;2026-03-12;"Pagamento; fornecedor X";2.1;D;40.00
    8;2026-03-12;"Pagamento; fornecedor X";1.1.1;C;40.00

Erros de estrutura na leitura (fora desta fatia: a leitura de lançamentos é da
fatia 3, e não existe nesta).

ESCRITA
-------
`escrever(lancamentos)` levanta `IntercambioRecusado` se alguma partida não cabe.
Não existe troca de caractere em silêncio: no formato próprio todo caractere é
válido, então a recusa só acontece para campo vazio ou partida com valor não positivo.
"""

import csv
import io
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_DEBITO,
    NIVEL_ERRO,
    IntercambioRecusado,
    Ocorrencia,
)

FORMATO = "proprio"
CABECALHO = ("numero", "data", "historico", "conta", "lado", "valor")
_CENTAVO = Decimal("0.01")


def _valor_com_ponto(valor):
    """Valor com ponto e exatamente duas casas (ver a especificação acima)."""
    if valor <= 0 or valor != valor.quantize(_CENTAVO):
        raise ValueError(f"valor {valor!r} fora de 2 casas ou não positivo: erro de programação.")
    return f"{valor:.2f}"


def escrever(lancamentos):
    """Escreve o formato próprio de lançamentos: UTF-8, CRLF, cabeçalho, uma linha por partida.

    Levanta `IntercambioRecusado` com as ocorrências se algum lançamento tem campo
    vazio ou partida fora da regra. Nada é escrito parcialmente.
    """
    ocorrencias = []
    saida = io.StringIO(newline="")
    escritor = csv.writer(saida, lineterminator="\r\n", delimiter=";", quotechar='"')
    escritor.writerow(CABECALHO)
    for lancamento in lancamentos:
        if not lancamento.historico:
            ocorrencias.append(
                Ocorrencia(lancamento.numero, "historico", NIVEL_ERRO, "histórico vazio.")
            )
            continue
        if not lancamento.partidas:
            ocorrencias.append(
                Ocorrencia(lancamento.numero, "partidas", NIVEL_ERRO, "lançamento sem partidas.")
            )
            continue
        for partida in lancamento.partidas:
            if not partida.codigo_conta:
                ocorrencias.append(
                    Ocorrencia(lancamento.numero, "conta", NIVEL_ERRO, "conta sem código.")
                )
                break
            if partida.valor <= 0 or partida.valor != partida.valor.quantize(_CENTAVO):
                ocorrencias.append(
                    Ocorrencia(
                        lancamento.numero,
                        "valor",
                        NIVEL_ERRO,
                        f"partida de {partida.codigo_conta} com valor fora de 2 casas "
                        "ou não positivo.",
                    )
                )
                break
        else:
            for partida in lancamento.partidas:
                escritor.writerow(
                    [
                        str(lancamento.numero),
                        lancamento.data.isoformat(),
                        lancamento.historico,
                        partida.codigo_conta,
                        "D" if partida.lado == LADO_DEBITO else "C",
                        _valor_com_ponto(partida.valor),
                    ]
                )
    if ocorrencias:
        raise IntercambioRecusado(
            "A exportação não cabe no formato próprio: "
            + "; ".join(f"lançamento {o.linha}, {o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )
    return saida.getvalue().encode("utf-8")
