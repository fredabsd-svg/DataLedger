"""Leitor de LANÇAMENTOS no leiaute com separador do sistema de referência.

(DL-077, fatia 3, frente A).

FONTE. Manual público "Importação Padrão", edição de 10/12/2018, capítulo 13: regras gerais
(p. 1224, item 2: `|` como separador, Numérico sem vírgula, Decimal com vírgula, exemplo
"Decimal (3) 150,895"; data dd/mm/aaaa), registro 0000 (p. 1225, campo 2, só números), lote
6000 (pp. 1449-1450, campo 2: D, C, X ou V), registro 6100 (p. 1450) e registros filhos 6110
e 6130 (p. 1451). O manual foi lido para construir este leitor. O texto NÃO é copiado para cá
(RC-167): cita-se registro, campo e página. Os arquivos de exemplo do fornecedor não entram
no repositório; os testes usam arquivos montados à mão.

REGISTROS E CAMPOS QUE O LEITOR USA (numeração do manual, começando em 1 = o identificador).
- 0000: campo 2, CNPJ ou CPF da empresa, só números (p. 1225). CNPJ alfanumérico (RC-46) é
  ERRO nomeado (`MENSAGEM_CNPJ_ALFANUMERICO`, a mesma do leiaute do plano): a edição de 2018
  só define inscrição numérica, e a empresa não pode ser conferida.
- 6000: campo 2, tipo do lote: D, C, X ou V (pp. 1449-1450). Tem 5 campos no total.
- 6100: 10 campos no total (p. 1450): 2 data (dd/mm/aaaa); 3 conta a débito (código
  reduzido); 4 conta a crédito (código reduzido); 5 valor (Decimal, vírgula e 2 casas, ex.:
  `1234,56`, sem milhar nem sinal); 6 código do histórico (0220, não lido); 7 descrição do
  histórico; 8 usuário; 9 filial; 10 SCP. Filho do 6000 (p. 1450).
- 6110 (rateio por centro de custo) e 6130 (marcação de DFC) são filhos do 6100 (p. 1451): não
  são guardados pelo DataLedger e geram AVISO no lançamento do 6100 pai.

DECISÕES DE LEITURA QUE O MANUAL NÃO FECHA (declaradas, não escondidas):
- NÚMERO DO LANÇAMENTO. O leiaute não tem número de lançamento. O número usado é a LINHA do
  arquivo: a do 6000 nos lotes D e C (um lançamento por lote) e a do 6100 nos lotes X e V (um
  lançamento por 6100). A linha é única no arquivo, e a idempotência usa o SHA-256 do arquivo
  junto com ela.
- AGRUPAMENTO. Lote X: cada 6100 é um lançamento (um débito, um crédito). Lote V (vários
  débitos para vários créditos): o manual não diz qual débito se liga a qual crédito, então
  cada 6100 vira um lançamento, sem palpite. Lote D (um débito para vários créditos) e lote C
  (vários débitos para um crédito): os 6100 do lote viram UM lançamento, desde que tenham a
  mesma data e a mesma conta do lado único (o débito no lote D, o crédito no lote C). Se não
  tiverem, o lote é recusado com o motivo.
- CONTA. Campos 3 e 4 são códigos reduzidos (o DataLedger não tem código reduzido). O leitor
  só confere que são números; a resolução para a conta é feita pelo de-para, no núcleo.
- CODIFICAÇÃO. O manual lido não declara a codificação do arquivo. Aceita-se UTF-8 (com BOM)
  e, na falta de UTF-8 válido, ISO-8859-1 (a do escritor do produto). UTF-8 sem BOM e com
  acento gera AVISO, porque a detecção pode errar.

LINHA EM BRANCO (R2 da reconferência). Linha em branco dentro de um lote, seguida de outra linha
(de registro ou não, inclusive um 6000 ou 0000 que feche o lote), é ERRO: pode ser um 6100 apagado.
Em branco só no fim do arquivo é formatação e não conta.

REGISTRO DESCONHECIDO (R2 da reconferência). Um registro que o leitor não conhece, dentro de um
lote (depois de um 6000 e antes do próximo 6000, 0000 ou fim do arquivo), é ERRO do arquivo: o lote
pode estar incompleto e a política não pode saber. Fora de lote, é aviso por registro. Pela
definição acima, um registro desconhecido depois do último lote (um trailer, por exemplo) também é
erro: a regra bloqueia em vez de deixar passar, mas um leiaute com trailer exige decisão do arquivo.

Erros de estrutura e de conteúdo viram `Ocorrencia` com linha e campo (`6100.5`, por exemplo),
e um lançamento com erro não entra no resultado. Nada é levantado por conteúdo ruim.
"""

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.contabilidade.intercambio.canonico import (
    LADO_CREDITO,
    LADO_DEBITO,
    NIVEL_AVISO,
    NIVEL_ERRO,
    LancamentoLido,
    Ocorrencia,
    PartidaLida,
    ResultadoLeitura,
)

# `_e_cnpj_alfanumerico` é privado do módulo do plano (fatia 1): usado só para escolher a
# mensagem nomeada do 0000, sem mudar a regra de aceite (que é só numérica).
from apps.contabilidade.intercambio.formatos.referencia import (
    MENSAGEM_CNPJ_ALFANUMERICO,
    _e_cnpj_alfanumerico,
)

FORMATO = "referencia"

REG_DOCUMENTO = "0000"
REG_LOTE = "6000"
REG_PARTIDA = "6100"
REGISTROS_FILHOS_DO_6100 = frozenset({"6110", "6130"})  # p. 1451

TIPOS_DE_LOTE = frozenset({"D", "C", "X", "V"})  # 6000, campo 2 (pp. 1449-1450)
CAMPOS_DO_6000 = 5  # p. 1449
CAMPOS_DO_6100 = 10  # p. 1450

_PADRAO_DATA = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})")
_PADRAO_VALOR = re.compile(r"[0-9]+,[0-9]{2}")
_PADRAO_CODIGO_REDUZIDO = re.compile(r"[0-9]{1,20}")
# CPF (11) ou CNPJ (14), só dígitos (p. 1225). O CNPJ alfanumérico (RC-46) fica FORA: é erro
# nomeado em `_ler_0000`, porque o leiaute de 2018 não o define.
_PADRAO_DOCUMENTO = re.compile(r"[0-9]{11}|[0-9]{14}")


@dataclass
class _Linha:
    """Um 6100 lido. `valida` = False quando algum campo dele foi recusado (erro já registrado)."""

    linha: int
    data: date | None = None
    debito: str | None = None
    credito: str | None = None
    valor: Decimal | None = None
    historico: str | None = None
    valida: bool = False


@dataclass
class _Lote:
    """Um 6000 e os 6100 que vêm depois dele, até outro registro que não seja filho."""

    linha: int
    tipo: str | None = None
    valido: bool = True
    linhas: list = field(default_factory=list)


def _decodificar(conteudo):
    """(texto, codificação, ocorrências). Nunca levanta exceção."""
    if conteudo.isascii():
        return conteudo.decode("ascii"), "ascii", []
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        return conteudo.decode("iso-8859-1"), "iso-8859-1", []
    aviso = Ocorrencia(
        linha=0,
        campo="codificacao",
        nivel=NIVEL_AVISO,
        mensagem=(
            "O arquivo está em UTF-8. O manual lido não declara a codificação deste leiaute; "
            "o arquivo foi lido como UTF-8. Confira os acentos antes de importar."
        ),
    )
    return texto, "utf-8", [aviso]


def _data_ddmmaaaa_barras(texto):
    """`dd/mm/aaaa` válida, ou None (p. 1224, item 2: formato da data)."""
    casa = _PADRAO_DATA.fullmatch(texto)
    if casa is None:
        return None
    dia, mes, ano = (int(grupo) for grupo in casa.groups())
    try:
        return date(ano, mes, dia)
    except ValueError:
        return None


def _ler_0000(numero, campos, resultado, ocorrencias):
    """Guarda o CNPJ/CPF do 0000 (campo 2, p. 1225). Só o primeiro 0000 conta."""
    if resultado.documento_declarado is not None:
        return
    if len(campos) != 2:
        ocorrencias.append(
            Ocorrencia(numero, "0000", NIVEL_ERRO, "0000 tem 2 campos (p. 1225): REG e o CNPJ/CPF.")
        )
        return
    documento = campos[1].strip()
    if _PADRAO_DOCUMENTO.fullmatch(documento):
        resultado.documento_declarado = documento
        return
    # A mensagem própria do CNPJ alfanumérico é a mesma do leiaute do plano (A5/RC-46).
    mensagem = (
        MENSAGEM_CNPJ_ALFANUMERICO
        if _e_cnpj_alfanumerico(documento)
        else "CNPJ/CPF do registro 0000 (campo 2, p. 1225) deve ter só números (11 ou 14 "
        "dígitos). Não é possível conferir a empresa."
    )
    ocorrencias.append(Ocorrencia(numero, "0000.2", NIVEL_ERRO, mensagem))


def _ler_6000(numero, campos, ocorrencias):
    """Abre um lote. O tipo (campo 2) tem de ser D, C, X ou V (pp. 1449-1450)."""
    lote = _Lote(linha=numero)
    if len(campos) != CAMPOS_DO_6000:
        ocorrencias.append(
            Ocorrencia(
                numero,
                "6000",
                NIVEL_ERRO,
                f"o registro 6000 tem {CAMPOS_DO_6000} campos (p. 1449); o registro traz "
                f"{len(campos)}. O lote não é lido.",
            )
        )
        lote.valido = False
        return lote
    tipo = campos[1].strip()
    if tipo not in TIPOS_DE_LOTE:
        ocorrencias.append(
            Ocorrencia(
                numero,
                "6000.2",
                NIVEL_ERRO,
                f"tipo do lote '{tipo}' não existe: use D (um débito p/ vários créditos), "
                "C (um crédito p/ vários débitos), X (um p/ um) ou V (vários p/ vários) "
                "(pp. 1449-1450). O lote não é lido.",
            )
        )
        lote.valido = False
        return lote
    lote.tipo = tipo
    if any(campo.strip() for campo in campos[2:]):
        ocorrencias.append(
            Ocorrencia(
                numero,
                "6000",
                NIVEL_AVISO,
                "código de lançamento padrão, localizador e RTT do lote não são guardados "
                "pelo DataLedger (pp. 1449-1450).",
            )
        )
    return lote


def _ler_6100(numero, campos, ocorrencias):
    """Uma partida de lote: data, contas reduzidas, valor, histórico. Pp. 1450-1451."""
    linha = _Linha(linha=numero)

    def recusar(campo, mensagem):
        ocorrencias.append(Ocorrencia(numero, f"6100.{campo}", NIVEL_ERRO, mensagem))

    if len(campos) != CAMPOS_DO_6100:
        recusar(
            "REG",
            f"o registro 6100 tem {CAMPOS_DO_6100} campos (p. 1450); "
            f"o registro traz {len(campos)}.",
        )
        return linha

    valido = True
    data = _data_ddmmaaaa_barras(campos[1].strip())
    if data is None:
        recusar("2", f"data '{campos[1].strip()}' não é dd/mm/aaaa válida (p. 1224, item 2).")
        valido = False
    else:
        linha.data = data

    for indice, rotulo in ((2, "debito"), (3, "credito")):
        codigo = campos[indice].strip()
        if not _PADRAO_CODIGO_REDUZIDO.fullmatch(codigo):
            recusar(
                str(indice + 1),
                f"conta a {'débito' if rotulo == 'debito' else 'crédito'} '{codigo}' não é um "
                "código reduzido numérico (p. 1450).",
            )
            valido = False
        elif rotulo == "debito":
            linha.debito = codigo
        else:
            linha.credito = codigo

    valor_texto = campos[4].strip()
    if not _PADRAO_VALOR.fullmatch(valor_texto) or Decimal(valor_texto.replace(",", ".")) <= 0:
        recusar(
            "5",
            f"valor '{valor_texto}' fora do leiaute: vírgula decimal com exatamente 2 casas e "
            "sem milhar ou sinal, valor positivo (ex.: 1234,56; p. 1224, item 2). Não há "
            "arredondamento.",
        )
        valido = False
    else:
        linha.valor = Decimal(valor_texto.replace(",", "."))

    descricao = campos[6]
    if not descricao.strip():
        recusar(
            "7",
            "descrição do histórico vazia (p. 1450). Sem o código do histórico 0220, que não "
            "é lido, o texto do lançamento sai daqui.",
        )
        valido = False
    elif any(ord(caractere) < 32 for caractere in descricao):
        recusar("7", "descrição do histórico com caractere de controle.")
        valido = False
    else:
        linha.historico = descricao

    if campos[5].strip():
        ocorrencias.append(
            Ocorrencia(
                numero,
                "6100.6",
                NIVEL_AVISO,
                "código do histórico (0220) não é lido: usada só a descrição (p. 1450).",
            )
        )
    for indice, rotulo in ((7, "usuário"), (8, "filial"), (9, "SCP")):
        if campos[indice].strip():
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    f"6100.{indice + 1}",
                    NIVEL_AVISO,
                    f"{rotulo} informado no 6100 não é guardado pelo DataLedger (p. 1450).",
                )
            )

    linha.valida = valido
    return linha


def _partidas_do_lancamento(debitos, creditos):
    """Monta as partidas de um lançamento a partir dos débitos e créditos já conferidos."""
    partidas = [
        PartidaLida(
            linha=lado_linha.linha,
            codigo_conta=codigo,
            lado=lado,
            valor=valor,
            historico=historico,
        )
        for lado, lado_linha, codigo, valor, historico in (debitos + creditos)
    ]
    return tuple(partidas)


def _lancamentos_do_lote(lote, ocorrencias):
    """Converte um lote em lançamentos (ver DECISÕES DE LEITURA no docstring do módulo)."""
    if not lote.valido:
        return []

    if lote.tipo in ("X", "V"):
        lancamentos = []
        for linha in lote.linhas:
            if not linha.valida:
                continue
            lancamentos.append(
                LancamentoLido(
                    linha=linha.linha,
                    numero=str(linha.linha),
                    data=linha.data,
                    historico="",
                    partidas=_partidas_do_lancamento(
                        [(LADO_DEBITO, linha, linha.debito, linha.valor, linha.historico)],
                        [(LADO_CREDITO, linha, linha.credito, linha.valor, linha.historico)],
                    ),
                )
            )
        return lancamentos

    # Lotes D e C: um lançamento por lote. Sem 6100, o lote não tem o que representar.
    if not lote.linhas:
        ocorrencias.append(
            Ocorrencia(
                lote.linha,
                "6000",
                NIVEL_ERRO,
                f"lote tipo {lote.tipo} sem nenhum 6100 (pp. 1449-1450).",
            )
        )
        return []
    if any(not linha.valida for linha in lote.linhas):
        return []  # os erros dos 6100 já estão registrados

    datas = {linha.data for linha in lote.linhas}
    if len(datas) > 1:
        ocorrencias.append(
            Ocorrencia(
                lote.linha,
                "6100.2",
                NIVEL_ERRO,
                "os 6100 de um mesmo lote tipo "
                f"{lote.tipo} trazem datas diferentes: o lote vira um lançamento só, com uma data.",
            )
        )
        return []
    lado_unico = "debito" if lote.tipo == "D" else "credito"
    contas_do_lado_unico = {getattr(linha, lado_unico) for linha in lote.linhas}
    if len(contas_do_lado_unico) > 1:
        ocorrencias.append(
            Ocorrencia(
                lote.linha,
                "6100.3" if lote.tipo == "D" else "6100.4",
                NIVEL_ERRO,
                f"o lote tipo {lote.tipo} precisa de uma só conta "
                f"a {'débito' if lote.tipo == 'D' else 'crédito'}; vieram "
                f"{len(contas_do_lado_unico)} contas diferentes. Não há pareamento sem palpite.",
            )
        )
        return []

    primeira = lote.linhas[0]
    total = sum((linha.valor for linha in lote.linhas), Decimal("0.00"))
    if lote.tipo == "D":
        debitos = [(LADO_DEBITO, primeira, primeira.debito, total, None)]
        creditos = [
            (LADO_CREDITO, linha, linha.credito, linha.valor, linha.historico)
            for linha in lote.linhas
        ]
    else:
        debitos = [
            (LADO_DEBITO, linha, linha.debito, linha.valor, linha.historico)
            for linha in lote.linhas
        ]
        creditos = [(LADO_CREDITO, primeira, primeira.credito, total, None)]
    return [
        LancamentoLido(
            linha=lote.linha,
            numero=str(lote.linha),
            data=primeira.data,
            historico="",
            partidas=_partidas_do_lancamento(debitos, creditos),
        )
    ]


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê os lotes (6000 e 6100) de um arquivo do sistema de referência.

    Não levanta exceção por conteúdo ruim.
    """
    texto, codificacao, ocorrencias = _decodificar(conteudo)
    resultado = ResultadoLeitura(formato=FORMATO, codificacao=codificacao)
    ignorados = Counter()
    lotes = []
    lote_atual = None
    documento_visto = False
    sem_barras_nas_pontas = False
    linha_em_branco = None  # a primeira linha em branco dentro de um lote, até a próxima linha lida

    for numero, bruta in enumerate(texto.split("\n"), start=1):
        linha = bruta.rstrip("\r")
        if not linha.strip():
            # Linha em branco DENTRO de um lote pode ser um 6100 apagado (a partida sumiria sem
            # erro). Só vira erro se outra linha vier depois; em branco no fim do arquivo é
            # formatação.
            if lote_atual is not None and linha_em_branco is None:
                linha_em_branco = numero
            continue
        # A10 (HI-91, item 2): a forma sem barras nas pontas é aceita, com UM aviso por arquivo,
        # como no leitor do plano. A forma com as duas barras é a canônica e não gera aviso. Uma
        # ponta só, ou linha sem nenhum '|', continua sendo erro: não há o que ler com segurança.
        # Sem barra inicial, a linha é lida como está: um '|' no fim é separador de campo vazio
        # (ex.: `6100|...|Compra|||`), não barra de fechamento.
        com_barras = len(linha) >= 2 and linha.startswith("|") and linha.endswith("|")
        sem_barras = "|" in linha and not linha.startswith("|")
        if not (com_barras or sem_barras):
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "linha",
                    NIVEL_ERRO,
                    "linha fora do leiaute: cada registro começa e termina com '|' "
                    "(p. 1224, item 2).",
                )
            )
            lote_atual = None
            continue
        if sem_barras:
            sem_barras_nas_pontas = True

        campos = (linha[1:-1] if com_barras else linha).split("|")
        reg = campos[0].strip()
        if linha_em_branco is not None:
            if lote_atual is not None:
                lote_atual.valido = False
                ocorrencias.append(
                    Ocorrencia(
                        linha_em_branco,
                        "linha",
                        NIVEL_ERRO,
                        f"linha em branco dentro do lote da linha {lote_atual.linha}: um registro "
                        "do lote pode ter sido apagado. O lote não é lido com linha em branco no "
                        "meio; corrija o arquivo.",
                    )
                )
            linha_em_branco = None

        if reg == REG_DOCUMENTO:
            if documento_visto:
                ocorrencias.append(
                    Ocorrencia(numero, "0000", NIVEL_ERRO, "segundo registro 0000 no arquivo.")
                )
            documento_visto = True
            _ler_0000(numero, campos, resultado, ocorrencias)
            lote_atual = None
            continue
        if reg == REG_LOTE:
            lote_atual = _ler_6000(numero, campos, ocorrencias)
            lotes.append(lote_atual)
            continue
        if reg == REG_PARTIDA:
            if lote_atual is None:
                ocorrencias.append(
                    Ocorrencia(
                        numero,
                        "REG",
                        NIVEL_ERRO,
                        "6100 sem lote (6000) acima dele (p. 1450).",
                    )
                )
                continue
            lote_atual.linhas.append(_ler_6100(numero, campos, ocorrencias))
            continue
        if reg in REGISTROS_FILHOS_DO_6100 and lote_atual is not None and lote_atual.linhas:
            # Rateio e marcação de DFC não são guardados: o aviso fica no 6100 pai.
            pai = lote_atual.linhas[-1]
            ocorrencias.append(
                Ocorrencia(
                    pai.linha,
                    reg,
                    NIVEL_AVISO,
                    f"registro {reg} (filho do 6100, p. 1451) não é guardado pelo DataLedger.",
                )
            )
            continue

        # R2 (reconferência): registro que o leitor não conhece. Dentro de um lote, o lote pode
        # estar incompleto (um 6100 com identificador ilegível some sem deixar rastro), então o lote
        # não vira lançamento e o registro é ERRO do arquivo, que bloqueia as duas políticas. O lote
        # continua aberto até o próximo 6000, 0000 ou fim do arquivo. Fora de lote, é só aviso por
        # registro. Em qualquer caso o registro é contado em `registros_ignorados`.
        ignorados[reg] += 1
        identificador = reg[:20] or "(vazio)"
        if lote_atual is not None:
            lote_atual.valido = False
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "REG",
                    NIVEL_ERRO,
                    f"registro '{identificador}' dentro do lote da linha {lote_atual.linha} não é "
                    "lido pelo DataLedger: o lote pode estar incompleto. O arquivo não pode ser "
                    "efetivado enquanto isso não for corrigido.",
                )
            )
        else:
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "registro",
                    NIVEL_AVISO,
                    f"registro '{identificador}' fora de lote não é lido pelo DataLedger: foi "
                    "ignorado (contado em registros ignorados).",
                )
            )

    for lote in lotes:
        resultado.lancamentos.extend(_lancamentos_do_lote(lote, ocorrencias))

    if sem_barras_nas_pontas:
        ocorrencias.append(
            Ocorrencia(
                0,
                "formato",
                NIVEL_AVISO,
                "o arquivo traz linhas sem '|' no início e no fim: o leitor aceitou a forma sem "
                "barras. Confira o arquivo.",
            )
        )
    resultado.ocorrencias = sorted(ocorrencias, key=lambda o: (o.linha, o.campo))
    resultado.registros_ignorados = dict(sorted(ignorados.items()))
    return resultado
