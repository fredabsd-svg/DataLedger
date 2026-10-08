"""Exportação de lançamentos e saldos no leiaute da ECD: I150, I155, I200 e I250 (DL-077, fatia 2).

FONTE. Manual de Orientação do Leiaute 9 da ECD, Anexo ao Ato Declaratório Executivo
Cofis nº 01/2026, atualização de maio de 2026, lido na fonte oficial
(http://sped.rfb.gov.br/arquivo/download/7990) em 08/10/2026. O texto do manual NÃO é
copiado para cá (RC-167): cita-se o registro, o campo e a página IMPRESSA no rodapé.

ESCOPO. Escreve I150 e I155 (só quando `incluir_saldos`), I200 e I250. Não escreve
0000, I001, I010, I050, bloco J, I990, 9999 nem assinatura. Um arquivo assim NÃO é a ECD.
O nome do arquivo e a tela dizem isso. O plano de contas (I050) é exportado à parte,
pela fatia 1, e os códigos de conta destes registros dependem dele.

REGRAS DO LEIAUTE QUE ESTE ESCRITOR APLICA (e que os testes verificam no arquivo):
- I150 por mês: DT_INI e DT_FIN no mesmo mês, sem fração (p. 132, REGRA_DATA_MES;
  p. 133, REGRA_DT_INI_INICIO_MES e REGRA_DT_FIN_FIM_MES).
- I155 por conta analítica com saldo ou movimento no mês (pp. 134-135). Valor com vírgula
  decimal, duas casas, sem separador de milhar (p. 53). Zero sai como `0,00`, e o
  indicador D/C é obrigatório mesmo em zero (p. 135, observações dos campos 04 e 05).
  O manual exige D ou C para o zero e NÃO escolhe qual; este escritor usa `D`. É uma
  convenção nossa, e não está no manual.
- Soma do saldo inicial = 0, soma do saldo final = 0, soma de débitos = soma de créditos,
  por período (REGRA_VALIDACAO_SOMA_SALDO_INICIAL, _SOMA_SALDO_FINAL, _DEB_DIF_CRED,
  p. 136). Final = inicial + débitos − créditos, por conta (REGRA_VALIDACAO_SALDO_FINAL,
  p. 136). Inicial de um mês = final do mês anterior (REGRA_VALIDACAO_SALDO_INI_DIF_FIN,
  p. 137). Conta sem repetição no período (REGRA_DUPLICIDADE_CONTA_SALDO_PERIODICO, p. 137).
- I200: NUM_LCTO único (REGRA_REGISTRO_DUPLICADO, p. 146); VL_LCTO = soma das partidas
  de um mesmo lado (campo 04, p. 144; REGRA_VALIDACAO_VL_LCTO_DEB/CRED, p. 146). IND_LCTO
  N = lançamento normal, E = encerramento de conta de resultado (campo 05, p. 143).
- I250: uma linha por partida (pp. 148-149). COD_CTA é conta analítica do plano
  (REGRA_CONTA_PARA_LANCAMENTO, p. 151). HIST é obrigatório (REGRA_HISTORICO_OBRIGATORIO,
  p. 150). HIST tem até 65.535 caracteres (campo 08, p. 149). O lançamento de quarta fórmula
  (mais de um débito e mais de um crédito) não é erro: o PGE emite um aviso para conferência
  (p. 148, item 4; REGRA_LCTO_4_FORMULA, p. 145). Este escritor o escreve como qualquer outro.

FORMATO (pp. 52-53). ISO-8859-1, CRLF, cada registro começa e termina com `|`, campo
vazio é `||`, campo C sem `|` e sem caractere de controle, data `ddmmaaaa`.

RECUSA. Nada é escrito parcialmente. Tudo o que não cabe no leiaute vira
`IntercambioRecusado` com a lista de ocorrências. A exportação nunca troca caractere
em silêncio.
"""

from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_ERRO,
    IntercambioRecusado,
    Ocorrencia,
)

TAMANHO_MAXIMO_COD_CTA = 255  # campo C sem tamanho próprio no manual: padrão de 255 (p. 53)
TAMANHO_MAXIMO_HISTORICO = 65535  # I250, campo 08 (p. 149)
IND_LCTO_NORMAL = "N"  # I200, campo 05 (p. 143)
IND_LCTO_ENCERRAMENTO = "E"  # I200, campo 05 (p. 143)
_CENTAVO = Decimal("0.01")


def _data(data):
    """ddmmaaaa, sem separador (p. 53)."""
    return data.strftime("%d%m%Y")


def _valor(valor):
    """N com vírgula decimal e duas casas, sem separador de milhar (p. 53).

    Quem chama já conferiu a escala e o sinal. Aqui um valor fora disso é erro de
    programação, e falha alto em vez de arredondar em silêncio.
    """
    if valor < 0 or valor != valor.quantize(_CENTAVO):
        raise ValueError(f"valor {valor!r} fora de 2 casas ou negativo: erro de programação.")
    return f"{valor:.2f}".replace(".", ",")


def _indicador(saldo):
    """D para saldo devedor, C para credor. Zero sai como D (convenção; ver o docstring)."""
    return "C" if saldo < 0 else "D"


def _linha(*campos):
    """Registro com `|` no início e no fim, e cada campo separado por `|`."""
    return "|" + "|".join(campos) + "|"


def _campo_texto(valor, rotulo, numero, ocorrencias, *, maximo):
    """Confere um campo C antes da escrita. Acrescenta erros; devolve True se cabe.

    `numero` é o identificador do lançamento (ou 0, nos saldos, onde não há).
    """

    def recusar(mensagem):
        ocorrencias.append(Ocorrencia(numero, rotulo, NIVEL_ERRO, mensagem))

    if not valor:
        recusar(f"{rotulo} não pode ficar vazio (p. 150 para o HIST; p. 151 para COD_CTA).")
        return False
    if "|" in valor:
        recusar(f"{rotulo} contém '|', que é o separador do leiaute (p. 52).")
        return False
    if any(ord(caractere) < 32 for caractere in valor):
        recusar(f"{rotulo} contém caractere de controle (00 a 31), não permitido (p. 53).")
        return False
    if len(valor) > maximo:
        recusar(f"{rotulo} tem {len(valor)} caracteres; o máximo é {maximo} (p. 53).")
        return False
    for caractere in valor:
        try:
            caractere.encode("iso-8859-1")
        except UnicodeEncodeError:
            recusar(
                f"{rotulo} contém o caractere '{caractere}', que não existe em ISO-8859-1 "
                "(p. 52). A exportação foi recusada; troque o caractere no cadastro ou no "
                "histórico."
            )
            return False
    return True


def _conferir_periodos(periodos, ocorrencias):
    """Regras de validação do I155 entre contas e entre meses (pp. 136-137).

    Não mexe em valor: só confere o que o escritor vai escrever. Quem produziu os
    saldos (`lancamentos.py`) já os tirou do balancete; aqui é a segunda leitura, a
    do leiaute.
    """

    def recusar(periodo, campo, regra, detalhe):
        ocorrencias.append(
            Ocorrencia(
                0,
                campo,
                NIVEL_ERRO,
                f"mês {periodo.inicio:%m/%Y}: {detalhe} ({regra}).",
            )
        )

    anterior = None
    for periodo in periodos:
        codigos = [conta.codigo_conta for conta in periodo.contas]
        if len(set(codigos)) != len(codigos):
            recusar(
                periodo,
                "COD_CTA",
                "REGRA_DUPLICIDADE_CONTA_SALDO_PERIODICO, p. 137",
                "uma conta aparece mais de uma vez no mesmo mês",
            )
        soma_inicial = sum((c.saldo_inicial for c in periodo.contas), Decimal("0"))
        soma_final = sum((c.saldo_final for c in periodo.contas), Decimal("0"))
        soma_debitos = sum((c.debitos for c in periodo.contas), Decimal("0"))
        soma_creditos = sum((c.creditos for c in periodo.contas), Decimal("0"))
        if soma_inicial != 0:
            recusar(
                periodo,
                "VL_SLD_INI",
                "REGRA_VALIDACAO_SOMA_SALDO_INICIAL, p. 136",
                f"a soma dos saldos iniciais é {soma_inicial}, e deveria ser zero",
            )
        if soma_final != 0:
            recusar(
                periodo,
                "VL_SLD_FIN",
                "REGRA_VALIDACAO_SOMA_SALDO_FINAL, p. 136",
                f"a soma dos saldos finais é {soma_final}, e deveria ser zero",
            )
        if soma_debitos != soma_creditos:
            recusar(
                periodo,
                "VL_DEB",
                "REGRA_VALIDACAO_DEB_DIF_CRED, p. 136",
                f"débitos {soma_debitos} diferentes de créditos {soma_creditos}",
            )
        for conta in periodo.contas:
            if conta.saldo_final != conta.saldo_inicial + conta.debitos - conta.creditos:
                recusar(
                    periodo,
                    "VL_SLD_FIN",
                    "REGRA_VALIDACAO_SALDO_FINAL, p. 136",
                    f"conta {conta.codigo_conta}: o saldo final não é inicial mais débitos "
                    "menos créditos",
                )
        if anterior is not None:
            final_anterior = {c.codigo_conta: c.saldo_final for c in anterior.contas}
            inicial_atual = {c.codigo_conta: c.saldo_inicial for c in periodo.contas}
            for codigo in set(final_anterior) | set(inicial_atual):
                if final_anterior.get(codigo, Decimal("0")) != inicial_atual.get(
                    codigo, Decimal("0")
                ):
                    recusar(
                        periodo,
                        "VL_SLD_INI",
                        "REGRA_VALIDACAO_SALDO_INI_DIF_FIN, p. 137",
                        f"conta {codigo}: o saldo inicial não é o final do mês anterior",
                    )
        anterior = periodo


def _conferir_lancamento(lancamento, ocorrencias):
    """Regras de I200 e I250 que o escritor não pode deixar passar (pp. 145-151)."""
    numero = lancamento.numero
    _campo_texto(lancamento.historico, "HIST", numero, ocorrencias, maximo=TAMANHO_MAXIMO_HISTORICO)
    if not lancamento.partidas:
        ocorrencias.append(
            Ocorrencia(numero, "I250", NIVEL_ERRO, "lançamento sem partidas (pp. 148-151).")
        )
        return
    lados = {partida.lado for partida in lancamento.partidas}
    if lados != {LADO_DEBITO, LADO_CREDITO}:
        ocorrencias.append(
            Ocorrencia(
                numero,
                "I250",
                NIVEL_ERRO,
                "lançamento sem débito ou sem crédito: o leiaute exige os dois lados (p. 148).",
            )
        )
    if lancamento.total_debito != lancamento.total_credito:
        ocorrencias.append(
            Ocorrencia(
                numero,
                "VL_LCTO",
                NIVEL_ERRO,
                "débitos e créditos do lançamento não são iguais (REGRA_VALIDACAO_VL_LCTO_DEB "
                "e _CRED, p. 146).",
            )
        )
    for partida in lancamento.partidas:
        _campo_texto(
            partida.codigo_conta, "COD_CTA", numero, ocorrencias, maximo=TAMANHO_MAXIMO_COD_CTA
        )
        if partida.valor <= 0:
            ocorrencias.append(
                Ocorrencia(numero, "VL_DC", NIVEL_ERRO, "partida com valor não positivo (p. 148).")
            )


def _descrever(ocorrencia):
    origem = f"lançamento {ocorrencia.linha}" if ocorrencia.linha else "saldos"
    return f"{origem}, {ocorrencia.campo}: {ocorrencia.mensagem}"


def escrever(lancamentos, periodos=(), *, incluir_saldos=False):
    """Escreve I150/I155 (se `incluir_saldos`) e I200/I250 em ISO-8859-1 com CRLF.

    `lancamentos` vem na ordem em que deve sair (data, depois número). `periodos` é a
    lista de meses completos, na ordem, e só é usada com `incluir_saldos=True`. Sem
    lançamento nem saldo, o resultado é `b""`.

    Levanta `IntercambioRecusado` com todas as ocorrências. Nada é escrito parcialmente.
    """
    lancamentos = list(lancamentos)
    periodos = list(periodos) if incluir_saldos else []
    ocorrencias = []
    _conferir_periodos(periodos, ocorrencias)

    linhas = []
    for periodo in periodos:
        linhas.append(_linha("I150", _data(periodo.inicio), _data(periodo.fim)))
        for conta in periodo.contas:
            antes = len(ocorrencias)
            _campo_texto(
                conta.codigo_conta, "COD_CTA", 0, ocorrencias, maximo=TAMANHO_MAXIMO_COD_CTA
            )
            if len(ocorrencias) != antes:
                continue
            linhas.append(
                _linha(
                    "I155",
                    conta.codigo_conta,
                    "",
                    _valor(abs(conta.saldo_inicial)),
                    _indicador(conta.saldo_inicial),
                    _valor(conta.debitos),
                    _valor(conta.creditos),
                    _valor(abs(conta.saldo_final)),
                    _indicador(conta.saldo_final),
                )
            )

    for lancamento in lancamentos:
        antes = len(ocorrencias)
        _conferir_lancamento(lancamento, ocorrencias)
        if len(ocorrencias) != antes:
            continue
        indicador = IND_LCTO_ENCERRAMENTO if lancamento.zeramento else IND_LCTO_NORMAL
        linhas.append(
            _linha(
                "I200",
                str(lancamento.numero),
                _data(lancamento.data),
                _valor(lancamento.total_debito),
                indicador,
                "",  # DT_LCTO_EXT: só no lançamento extemporâneo (tipo X), que não sai aqui
            )
        )
        for partida in lancamento.partidas:
            linhas.append(
                _linha(
                    "I250",
                    partida.codigo_conta,
                    "",  # COD_CCUS: o DataLedger não tem centro de custo
                    _valor(partida.valor),
                    "D" if partida.lado == LADO_DEBITO else "C",
                    "",  # NUM_ARQ: o DataLedger não guarda arquivo anexo
                    "",  # COD_HIST_PAD: o DataLedger não tem histórico padronizado (I075)
                    lancamento.historico,
                    "",  # COD_PART: o DataLedger não tem participante
                )
            )

    if ocorrencias:
        raise IntercambioRecusado(
            "A exportação não cabe no leiaute da ECD: "
            + "; ".join(_descrever(o) for o in ocorrencias),
            ocorrencias,
        )
    if not linhas:
        return b""
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
