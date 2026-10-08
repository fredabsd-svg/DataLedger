"""Exportação de lançamentos no leiaute com separador do sistema de referência (DL-077, fatia 2).

FONTE. Manual público "Importação Padrão", edição de 10/12/2018, capítulo 13: regras
gerais e definição dos campos (pp. 1224-1225), registro 0000 (p. 1225), e os lançamentos
em lote 6000 (pp. 1449-1450), 6100 (p. 1450) e 6110 (p. 1451). O manual foi lido para
construir este escritor. O texto dele NÃO é copiado para cá (RC-167): cita-se registro,
campo e página.

NUMERAÇÃO. Campo N do registro é o campo N do manual, começando em 1 (o campo 1 é o
identificador do registro).

O QUE O MANUAL DEFINE, e o que este escritor aplica:
- separador `|`; campo numérico sem vírgula (p. 1225);
- registro 0000, campo 2: CNPJ ou CPF da empresa, só com dígitos (p. 1225);
- registro 6000, campo 2: TIPO DO LANÇAMENTO. D = um débito p/ vários créditos;
  C = um crédito p/ vários débitos; X = um débito p/ um crédito; V = vários débitos
  p/ vários créditos (pp. 1449-1450). Este escritor usa D, C e X para os lançamentos que
  cabem, e não escreve V (ver N×M abaixo);
- registro 6100, filho do 6000: cada linha traz UMA conta a débito e UMA conta a crédito,
  pelo CÓDIGO REDUZIDO (campos 3 e 4, p. 1450), a data do lançamento (campo 2), o valor
  (campo 5), o código do histórico (campo 6) e a descrição do histórico (campo 7).

COMO UM LANÇAMENTO VIRA LINHAS 6100 (decomposição única, sem palpite):
- X (1 débito, 1 crédito): uma linha 6100.
- D (1 débito, N créditos): N linhas 6100, todas com o mesmo débito e um crédito cada.
- C (N débitos, 1 crédito): N linhas 6100, todas com o mesmo crédito e um débito cada.
- V (N débitos, M créditos): NÃO representável sem escolher quem se liga a quem. Recusado.

O QUE O MANUAL NÃO DEFINE, e como este escritor trata. Nada disto é apresentado como
regra do manual:
- TIPO e CASAS DECIMAIS do valor do 6100 (campo 5): na tabela da p. 1450 o tipo e as
  casas decimais estão EM BRANCO. A p. 1225 diz que o campo numérico tem casas declaradas.
  Sem casas declaradas, o valor não é escrito. Por isso `casas_decimais_do_valor` é
  obrigatório para escrever lançamento, e a exportação do produto passa `None`, que a
  recusa com o motivo. Quem testa informa o número explicitamente, e isso é teste do
  mecanismo, não afirmação sobre o manual.
- DATA do 6100 (campo 2): o campo se chama "data" e a p. 1225 define o tipo data como
  dd/mm/aaaa. Usa-se dd/mm/aaaa. É inferência, e fica registrada.
- CÓDIGO REDUZIDO (campos 3 e 4): o DataLedger não tem código reduzido. Usa-se a mesma
  regra do escritor do plano da fatia 1 (sequencial pela ordem do código, sobre o plano
  inteiro). Ver `codigos_reduzidos`.
- CÓDIGO DO HISTÓRICO (campo 6, tabela 0220): o DataLedger não tem. O código fica vazio e
  a descrição sai no campo 7.
- Campos vazios e opcionais de 6000 e 6100 (lançamento padrão, localizador, RTT, usuário,
  filial, SCP): saem vazios. O manual diz que o usuário em branco vale o usuário da
  importação, e que a filial só se informa para empresa filial (p. 1451).

N×M. Lançamento com mais de um débito e mais de um crédito não tem decomposição única,
porque o manual não diz qual débito se liga a qual crédito. Escolher um pareamento
inventa uma ligação entre contas que não existe no lançamento. Por isso é RECUSADO por
padrão. Com `omitir_nao_representaveis=True`, sai sem ele, e ele é devolvido na lista
de omitidos, para o relatório de conferência dizer quais ficaram de fora.

CÓDIGO REDUZIDO E ESTABILIDADE. Quem produz a lista de lançamentos precisa passar o
mapa de códigos sobre o plano INTEIRO da empresa. Incluir ou remover uma conta muda
os números das seguintes. O relatório de conferência traz o mapa das contas usadas.

FORMATO DO ARQUIVO. ISO-8859-1, CRLF, sem `|` nas pontas (como o escritor do plano da
fatia 1). Histórico com `|`, caractere de controle ou fora de ISO-8859-1 é recusado.
"""

import re
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_ERRO,
    IntercambioRecusado,
    Ocorrencia,
)

FORMATO = "referencia"

REG_DOCUMENTO = "0000"
REG_LOTE = "6000"
REG_PARTIDA = "6100"
SEPARADOR = "|"

TIPO_DEBITO_PARA_VARIOS_CREDITOS = "D"  # 6000, campo 2 (pp. 1449-1450)
TIPO_CREDITO_PARA_VARIOS_DEBITOS = "C"  # 6000, campo 2 (pp. 1449-1450)
TIPO_UM_PARA_UM = "X"  # 6000, campo 2 (p. 1450)
TIPO_VARIOS_PARA_VARIOS = "V"  # 6000, campo 2 (p. 1450): NÃO escrito, ver N×M

_PADRAO_DOCUMENTO = re.compile(r"[0-9]{11}|[0-9]{14}")


def tipo_do_lote(lancamento):
    """`X`, `D` ou `C`, pela quantidade de débitos e de créditos. `None` para N×M.

    O tipo vem da própria contagem de partidas, e não de um campo guardado: o
    lançamento não tem "tipo" no DataLedger.
    """
    debitos = sum(1 for p in lancamento.partidas if p.lado == LADO_DEBITO)
    creditos = sum(1 for p in lancamento.partidas if p.lado == LADO_CREDITO)
    if debitos == 1 and creditos == 1:
        return TIPO_UM_PARA_UM
    if debitos == 1 and creditos >= 2:
        return TIPO_DEBITO_PARA_VARIOS_CREDITOS
    if debitos >= 2 and creditos == 1:
        return TIPO_CREDITO_PARA_VARIOS_DEBITOS
    return None


def codigos_reduzidos(codigos):
    """Código reduzido sequencial pela ordem do código, igual ao escritor do 0200 da fatia 1.

    Vale para o plano INTEIRO da empresa (o `exportar_plano` com filtro `todas`). O
    DataLedger não tem código reduzido próprio, e a estabilidade é a do plano.
    """
    return {codigo: numero for numero, codigo in enumerate(sorted(set(codigos)), start=1)}


def _pares(lancamento, tipo):
    """(código a débito, código a crédito, valor) de cada linha 6100 do lançamento."""
    debitos = [p for p in lancamento.partidas if p.lado == LADO_DEBITO]
    creditos = [p for p in lancamento.partidas if p.lado == LADO_CREDITO]
    if tipo == TIPO_UM_PARA_UM:
        return [(debitos[0].codigo_conta, creditos[0].codigo_conta, debitos[0].valor)]
    if tipo == TIPO_DEBITO_PARA_VARIOS_CREDITOS:
        return [(debitos[0].codigo_conta, c.codigo_conta, c.valor) for c in creditos]
    return [(d.codigo_conta, creditos[0].codigo_conta, d.valor) for d in debitos]


def _valor_implicito(valor, casas):
    """Valor sem vírgula, com `casas` decimais implícitos (p. 1225).

    Recusa, em vez de arredondar, um valor que tenha mais casas do que o declarado.
    """
    inteiro = valor * (Decimal(10) ** casas)
    if inteiro != inteiro.to_integral_value():
        raise IntercambioRecusado(
            f"o valor {valor} tem mais casas decimais que as {casas} declaradas; a exportação "
            "não arredonda em silêncio."
        )
    return str(int(inteiro))


def _campo_escrevivel(valor, rotulo, numero, ocorrencias):
    """Confere um campo de texto antes da escrita. Acrescenta erro se não cabe."""

    def recusar(mensagem):
        ocorrencias.append(Ocorrencia(numero, rotulo, NIVEL_ERRO, mensagem))

    if not valor:
        recusar(f"{rotulo} vazio.")
        return False
    if SEPARADOR in valor:
        recusar(f"{rotulo} contém '|', que é o separador do leiaute.")
        return False
    if any(ord(caractere) < 32 for caractere in valor):
        recusar(f"{rotulo} contém caractere de controle.")
        return False
    try:
        valor.encode("iso-8859-1")
    except UnicodeEncodeError:
        recusar(f"{rotulo} contém caractere fora de ISO-8859-1. A exportação foi recusada.")
        return False
    return True


def escrever(
    lancamentos,
    *,
    documento,
    codigos_reduzidos,
    casas_decimais_do_valor,
    omitir_nao_representaveis=False,
):
    """Escreve 0000, 6000 e 6100 em ISO-8859-1 com CRLF. Devolve (bytes, omitidos).

    - `documento`: CNPJ/CPF da empresa, obrigatório para o 0000 (campo 2, p. 1225).
    - `codigos_reduzidos`: mapa código da conta -> código reduzido, sobre o plano inteiro.
    - `casas_decimais_do_valor`: número de casas do valor do 6100. `None` = o manual não
      declara, e a escrita de lançamento é recusada (ver o docstring do módulo).
    - `omitir_nao_representaveis`: se False, qualquer N×M recusa a exportação inteira,
      listando os lançamentos. Se True, eles saem fora do arquivo e voltam em `omitidos`.

    Nada é escrito parcialmente: qualquer recusa levanta `IntercambioRecusado`.
    """
    digitos = re.sub(r"\D", "", documento or "")
    if not _PADRAO_DOCUMENTO.fullmatch(digitos):
        raise IntercambioRecusado(
            "o leiaute do sistema de referência exige o CNPJ ou CPF da empresa no registro "
            "0000 (campo 2, p. 1225). Sem ele, a exportação não é feita."
        )

    lancamentos = list(lancamentos)
    representaveis = []
    nao_representaveis = []
    for lancamento in lancamentos:
        (representaveis if tipo_do_lote(lancamento) else nao_representaveis).append(lancamento)

    if nao_representaveis and not omitir_nao_representaveis:
        descricoes = []
        ocorrencias = []
        for lancamento in nao_representaveis:
            debitos = sum(1 for p in lancamento.partidas if p.lado == LADO_DEBITO)
            creditos = sum(1 for p in lancamento.partidas if p.lado == LADO_CREDITO)
            descricoes.append(
                f"lançamento {lancamento.numero} ({lancamento.data:%d/%m/%Y}, "
                f"{debitos} débitos × {creditos} créditos)"
            )
            ocorrencias.append(
                Ocorrencia(
                    lancamento.numero,
                    "partidas",
                    NIVEL_ERRO,
                    f"{debitos} débitos × {creditos} créditos: o leiaute não diz qual débito "
                    "se liga a qual crédito (6000, tipo V, p. 1450).",
                )
            )
        raise IntercambioRecusado(
            "lançamentos que o leiaute do sistema de referência não representa sem "
            f"ambiguidade: {'; '.join(descricoes)}. Nenhum arquivo foi gerado. Para gerar "
            "sem eles, marque 'omitir os não representáveis': eles aparecem no relatório "
            "de conferência.",
            ocorrencias,
        )

    ocorrencias = []
    for lancamento in representaveis:
        _campo_escrevivel(lancamento.historico, "histórico", lancamento.numero, ocorrencias)
        for partida in lancamento.partidas:
            if partida.codigo_conta not in codigos_reduzidos:
                ocorrencias.append(
                    Ocorrencia(
                        lancamento.numero,
                        "conta",
                        NIVEL_ERRO,
                        f"conta '{partida.codigo_conta}' não está no plano da empresa: "
                        "sem código reduzido não há como escrever.",
                    )
                )
    if ocorrencias:
        raise IntercambioRecusado(
            "A exportação não cabe no leiaute do sistema de referência: "
            + "; ".join(f"lançamento {o.linha}, {o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )

    if representaveis and casas_decimais_do_valor is None:
        raise IntercambioRecusado(
            "o leiaute do sistema de referência não declara as casas decimais do valor do "
            "registro 6100 (campo 5, p. 1450), e a exportação não supõe esse número. "
            "Lançamentos não podem ser exportados nele até que o número seja confirmado."
        )

    linhas = [SEPARADOR.join([REG_DOCUMENTO, digitos])]
    for lancamento in representaveis:
        tipo = tipo_do_lote(lancamento)
        linhas.append(SEPARADOR.join([REG_LOTE, tipo, "", "", ""]))
        data = lancamento.data.strftime("%d/%m/%Y")
        for debito, credito, valor in _pares(lancamento, tipo):
            linhas.append(
                SEPARADOR.join(
                    [
                        REG_PARTIDA,
                        data,
                        str(codigos_reduzidos[debito]),
                        str(codigos_reduzidos[credito]),
                        _valor_implicito(valor, casas_decimais_do_valor),
                        "",  # campo 6: código do histórico (0220): o DataLedger não tem
                        lancamento.historico,  # campo 7: descrição do histórico
                        "",  # campo 8: usuário, em branco = usuário da importação
                        "",  # campo 9: filial, só para empresa filial
                        "",  # campo 10: SCP
                    ]
                )
            )

    saida = ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
    return saida, tuple(nao_representaveis)
