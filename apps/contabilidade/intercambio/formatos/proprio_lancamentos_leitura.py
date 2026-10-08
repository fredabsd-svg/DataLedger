"""Leitor de LANÇAMENTOS no formato próprio do DataLedger (DL-077, fatia 3, frente A).

A ESPECIFICAÇÃO do formato é o docstring de `proprio_lancamentos.py` (fatia 2): UTF-8,
`;`, cabeçalho `numero;data;historico;conta;lado;valor`, uma linha por partida, partidas do
mesmo número em sequência. Este módulo LÊ esse formato e é o contrato de volta da exportação.

REGRAS DA LEITURA (além da estrutura):
- `numero` é inteiro de 1 a 18 dígitos. O número repetido em blocos NÃO consecutivos é erro:
  os dois blocos são recusados, porque o arquivo não diz qual é o lançamento (ver o núcleo,
  que confere o número de novo).
- `data` é aaaa-mm-dd válida. Partidas do mesmo número com data diferente: erro.
- `historico` é o texto do lançamento. Vem repetido em cada partida, e o texto é preservado
  como está (sem aparar espaços), para que a ida e a volta devolvam o mesmo histórico.
- `conta` é o código da conta no DataLedger (até 255 caracteres, sem caractere de controle).
- `lado` é `D` ou `C`, em maiúsculas.
- `valor` tem PONTO decimal e exatamente DUAS casas, maior que zero (ex.: `1250.00`).

Um lançamento com qualquer erro em qualquer de suas linhas NÃO entra no resultado: as linhas
boas do mesmo número também saem, porque a partida sozinha não fecha o lançamento.

LINHA EM BRANCO (R2 da reconferência). Linha em branco que vem antes de outra linha do arquivo é
ERRO do arquivo: pode ser uma partida apagada, e o formato não tem total declarado para denunciar a
falta. Em branco só no fim do arquivo é formatação e não conta.

`montar_lancamentos` é a parte que o leitor do Excel também usa: recebe as linhas já lidas
(`LinhaLida`) e agrupa, confere número e data e devolve os lançamentos. Assim o formato
próprio e a planilha seguem a mesma regra de agrupamento, sem duplicação.
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_ERRO,
    LancamentoLido,
    Ocorrencia,
    PartidaLida,
    ResultadoLeitura,
)
from apps.contabilidade.intercambio.formatos.proprio import _ErroDeEstrutura, _registros

FORMATO = "proprio"
CABECALHO_LANCAMENTOS = ("numero", "data", "historico", "conta", "lado", "valor")
TAMANHO_MAXIMO_CONTA = 255

_PADRAO_NUMERO = re.compile(r"[0-9]{1,18}")
_PADRAO_DATA_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_PADRAO_VALOR = re.compile(r"[0-9]+\.[0-9]{2}")


@dataclass(frozen=True)
class LinhaLida:
    """Uma partida lida de um arquivo (ou de uma planilha). `numero` None = não deu para ler."""

    linha: int
    numero: str | None
    data: date | None
    historico: str | None
    conta: str | None
    lado: str | None
    valor: Decimal | None
    valida: bool


def _tem_controle(texto):
    """Caractere 00 a 31 não é permitido em campo de texto (mesma regra da ECD, p. 53)."""
    return any(ord(caractere) < 32 for caractere in texto)


def _data_iso(texto):
    casa = _PADRAO_DATA_ISO.fullmatch(texto)
    if casa is None:
        return None
    try:
        return date(*(int(grupo) for grupo in casa.groups()))
    except ValueError:
        return None


def _interpretar(numero, campos, ocorrencias):
    """Uma linha de dados do formato próprio. Erros vão para `ocorrencias`."""
    if len(campos) != len(CABECALHO_LANCAMENTOS):
        ocorrencias.append(
            Ocorrencia(
                numero,
                "estrutura",
                NIVEL_ERRO,
                f"a linha tem {len(campos)} campos; o formato exige {len(CABECALHO_LANCAMENTOS)} "
                "(numero;data;historico;conta;lado;valor).",
            )
        )
        return LinhaLida(numero, None, None, None, None, None, None, False)

    num, dt, historico, conta, lado, valor_texto = (
        campos[0].strip(),
        campos[1].strip(),
        campos[2],
        campos[3].strip(),
        campos[4].strip(),
        campos[5].strip(),
    )
    valida = True

    def recusar(campo, mensagem):
        nonlocal valida
        ocorrencias.append(Ocorrencia(numero, campo, NIVEL_ERRO, mensagem))
        valida = False

    if not _PADRAO_NUMERO.fullmatch(num):
        recusar("numero", f"número '{num}': use um inteiro de 1 a 18 dígitos.")
    data = _data_iso(dt)
    if data is None:
        recusar("data", f"data '{dt}' não é aaaa-mm-dd válida.")
    if not historico.strip():
        recusar("historico", "histórico obrigatório.")
    if not conta or len(conta) > TAMANHO_MAXIMO_CONTA or _tem_controle(conta):
        recusar("conta", "conta obrigatória, até 255 caracteres, sem caractere de controle.")
    if lado not in ("D", "C"):
        recusar("lado", f"lado '{lado}': use D (débito) ou C (crédito).")
    valor = None
    if _PADRAO_VALOR.fullmatch(valor_texto) and Decimal(valor_texto) > 0:
        valor = Decimal(valor_texto)
    else:
        recusar(
            "valor",
            f"valor '{valor_texto}': use ponto decimal, duas casas e valor maior que zero "
            "(ex.: 1250.00).",
        )

    return LinhaLida(
        linha=numero,
        numero=num if _PADRAO_NUMERO.fullmatch(num) else None,
        data=data,
        historico=historico,
        conta=conta,
        lado=lado if lado in ("D", "C") else None,
        valor=valor,
        valida=valida,
    )


def montar_lancamentos(linhas, resultado):
    """Agrupa as partidas por número e acrescenta a `resultado` os lançamentos válidos.

    Regras: número repetido em blocos não consecutivos recusa todos os blocos desse número;
    linha sem número legível quebra o bloco (não pertence a nenhum); bloco com linha inválida
    ou com data diferente da primeira partida é recusado inteiro.
    """
    grupos = []  # [numero, [LinhaLida]] ou None quando uma linha sem número quebra o bloco
    for linha in linhas:
        if linha.numero is None:
            grupos.append(None)
            continue
        if grupos and grupos[-1] is not None and grupos[-1][0] == linha.numero:
            grupos[-1][1].append(linha)
        else:
            grupos.append([linha.numero, [linha]])

    contagem = {}
    for grupo in grupos:
        if grupo is not None:
            contagem[grupo[0]] = contagem.get(grupo[0], 0) + 1

    repetidos = set()
    primeiro_bloco = {}
    for grupo in grupos:
        if grupo is None:
            continue
        numero, partidas = grupo
        if contagem[numero] > 1:
            repetidos.add(numero)
            if numero in primeiro_bloco:
                resultado.ocorrencias.append(
                    Ocorrencia(
                        partidas[0].linha,
                        "numero",
                        NIVEL_ERRO,
                        f"número '{numero}' repetido em blocos separados (primeira ocorrência na "
                        f"linha {primeiro_bloco[numero]}). Os dois blocos são recusados.",
                    )
                )
            else:
                primeiro_bloco[numero] = partidas[0].linha

    for grupo in grupos:
        if grupo is None:
            continue
        numero, partidas = grupo
        if numero in repetidos:
            continue
        if any(not linha.valida for linha in partidas):
            continue  # os erros de cada linha já estão em `resultado.ocorrencias`
        primeira = partidas[0]
        bloco_valido = True
        for linha in partidas[1:]:
            if linha.data != primeira.data:
                resultado.ocorrencias.append(
                    Ocorrencia(
                        linha.linha,
                        "data",
                        NIVEL_ERRO,
                        f"data {linha.data:%d/%m/%Y} diferente da primeira partida do lançamento "
                        f"{numero} (linha {primeira.linha}, {primeira.data:%d/%m/%Y}). "
                        "O lançamento "
                        "tem uma data só.",
                    )
                )
                bloco_valido = False
        if not bloco_valido:
            continue
        resultado.lancamentos.append(
            LancamentoLido(
                linha=primeira.linha,
                numero=numero,
                data=primeira.data,
                historico=primeira.historico,
                partidas=tuple(
                    PartidaLida(
                        linha=linha.linha,
                        codigo_conta=linha.conta,
                        lado=LADO_DEBITO if linha.lado == "D" else LADO_CREDITO,
                        valor=linha.valor,
                        historico=linha.historico,
                    )
                    for linha in partidas
                ),
            )
        )


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê os lançamentos do formato próprio. Não levanta exceção por conteúdo ruim."""
    resultado = ResultadoLeitura(formato=FORMATO, codificacao="utf-8")
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        resultado.ocorrencias.append(
            Ocorrencia(0, "codificacao", NIVEL_ERRO, "o arquivo não está em UTF-8 válido.")
        )
        resultado.codificacao = ""
        return resultado

    linhas = []
    cabecalho_visto = False
    linha_em_branco = (
        None  # R2 (reconferência): a primeira linha em branco, até a próxima linha lida
    )
    try:
        for numero, campos in _registros(texto):
            if not cabecalho_visto:
                cabecalho_visto = True
                cabecalho = tuple(valor.strip() for valor in campos)
                if cabecalho != CABECALHO_LANCAMENTOS:
                    resultado.ocorrencias.append(
                        Ocorrencia(
                            numero,
                            "cabecalho",
                            NIVEL_ERRO,
                            "o cabeçalho deve ser exatamente "
                            f"{';'.join(CABECALHO_LANCAMENTOS)}; veio {';'.join(cabecalho)}.",
                        )
                    )
                    return resultado
                continue
            if campos == [""]:
                # Linha em branco pode ser uma partida apagada: o leitor não a pula em silêncio, e
                # sem ela um lançamento poderia sair incompleto e equilibrado (R2). Só o fim do
                # arquivo, depois de tudo, é formatação.
                if linha_em_branco is None:
                    linha_em_branco = numero
                continue
            if linha_em_branco is not None:
                resultado.ocorrencias.append(
                    Ocorrencia(
                        linha_em_branco,
                        "linha",
                        NIVEL_ERRO,
                        "linha em branco no meio do arquivo: pode ser uma partida apagada. "
                        "Corrija o arquivo; a leitura não aceita linha em branco antes de outra "
                        "linha.",
                    )
                )
                linha_em_branco = None
            linhas.append(_interpretar(numero, campos, resultado.ocorrencias))
    except _ErroDeEstrutura as exc:
        resultado.ocorrencias.append(
            Ocorrencia(exc.linha, "estrutura", NIVEL_ERRO, f"{exc.mensagem}. A leitura parou aqui.")
        )

    if not cabecalho_visto:
        resultado.ocorrencias.append(
            Ocorrencia(1, "cabecalho", NIVEL_ERRO, "arquivo vazio: falta o cabeçalho.")
        )
        return resultado
    montar_lancamentos(linhas, resultado)
    resultado.ocorrencias.sort(key=lambda o: (o.linha, o.campo))
    return resultado
