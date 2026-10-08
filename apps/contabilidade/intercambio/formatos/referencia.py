"""Plano de contas no leiaute de importação com separador do sistema de referência
(DL-077, fatia 1, frente B).

FONTE. Manual público "Importação Padrão" (edição de 10/12/2018), capítulo 13,
regras gerais (p. 1224), registro 0000 (p. 1225), registro 0200 (pp. 1275-1276)
e registro 0250 (p. 1277). O manual foi lido para construir este importador. O
texto dele NÃO é copiado para cá (RC-167): cita-se registro, campo e página.

NUMERAÇÃO. `_campo(campos, N)` é o campo N do manual, começando em 1. O campo 1 é
o identificador do registro, e ele é `campos[0]`.

O QUE O MANUAL DEFINE, e o que este módulo aplica:
- separador `|`; data `dd/mm/aaaa`; numérico sem vírgula (p. 1224);
- registro 0000, campo 2: inscrição da empresa, CNPJ ou CPF (p. 1225);
- registro 0200: 11 campos (pp. 1275-1276); registro 0250: 3 campos, filho do 0200
  (p. 1277);
- o 0200 NÃO traz natureza nem conta superior (HI-87, HI-88): a superior sai da
  classificação contábil, e o tipo não vem no arquivo.

O QUE O MANUAL NÃO DEFINE, e como este módulo trata. Nada disto é apresentado como
regra do manual:
- se a linha começa e termina com `|`: a edição de 2018 do manual não diz. A forma
  CANÔNICA deste módulo é a do exemplo oficial do fornecedor (`|REG|campo|...|campo|`,
  com `|` no início e no fim), segundo pesquisa do arquiteto de 08/10/2026. O ESCRITOR
  escreve assim. O LEITOR aceita a forma com barras SEM aviso e a forma sem barras com
  UM aviso por arquivo, dizendo que ela não é a do exemplo oficial. O exemplo do fornecedor
  não foi copiado para o repositório (RC-167).
- codificação e fim de linha: não definidos no capítulo consultado. Adotamos
  ISO-8859-1 e CRLF, como a ECD e o Carnê-Leão (HI-41). É decisão do projeto. A
  leitura aceita UTF-8 com aviso.
- máscara da classificação contábil: não definida. A superior é tomada pelo
  PREFIXO (ver `derivar_pai`), e a derivação por prefixo sem separador gera aviso.
- obrigatoriedade de campos que não são identificador: não definida. Vazio é
  aceito onde o campo não é usado pelo DataLedger, e isso aparece no código.

NO DATALEDGER, o que o arquivo não traz fica `None`: tipo (HI-87) e natureza
(HI-88). A situação do 0200 (campo 7) vai em `ContaLida.ativa`: a conta inativa
no arquivo é criada inativa, com aviso. O código reduzido vai em `codigo_origem`.
O CNPJ/CPF do 0000 vai em `documento_declarado`, e quem confere é o núcleo.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
    Ocorrencia,
    ResultadoLeitura,
)

FORMATO = "referencia"

REG_DOCUMENTO = "0000"
REG_CONTA = "0200"
REG_REFERENCIAL = "0250"

# Campos de cada registro usado, identificador incluído (campo 1).
CAMPOS_POR_REGISTRO = {REG_DOCUMENTO: 2, REG_CONTA: 11, REG_REFERENCIAL: 3}

SEPARADOR = "|"
# O manual não define máscara de classificação. O ponto é a convenção dos planos
# com níveis (ex.: 1.1.01), e vale para o pai derivado. Sem ponto, a derivação é
# por caractere e gera aviso (ver `_prefixos_da_classificacao`).
SEPARADOR_DE_NIVEL = "."

TAMANHOS_DE_DOCUMENTO = (11, 14)  # CPF, CNPJ (campo 2 do 0000, p. 1225)
TAMANHO_MAXIMO_CLASSIFICACAO = 20  # Conta.codigo (max_length)
FORMATO_DATA = "%d/%m/%Y"
_PADRAO_DATA = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4}")
_PADRAO_REGISTRO = re.compile(r"[0-9]{4}")
_PADRAO_NUMERO = re.compile(r"[0-9]+")
_PADRAO_MASCARA_DOCUMENTO = re.compile(r"[0-9./\- ]+")

# 0200, campo 4: analítica (A) ou sintética (S). Campo 7: situação (A ou I).
_TIPO_DO_0200 = {"A": True, "S": False}
_SITUACOES_DO_0200 = ("A", "I")
# 0250, campo 3: R = Receita Federal, C = Banco Central (p. 1277).
_ORGAOS_DO_0250 = frozenset({"R", "C"})
# 0200, campos 9 a 11: relacionamentos com as demonstrações. O DataLedger não os guarda.
_RELACIONAMENTOS_DO_0200 = {9: "DLPA", 10: "DOAR", 11: "DRE"}

# Avisos que a EXPORTAÇÃO leva ao contador (o núcleo os repassa à API e à trilha).
# Só ASCII: vão em cabeçalho HTTP. O código reduzido é sequencial pela ordem do código,
# então muda quando o plano muda; o DataLedger não tem código reduzido próprio.
AVISOS_DE_EXPORTACAO = (
    "codigo reduzido sequencial pela ordem do codigo: nao e estavel entre exportacoes "
    "(o DataLedger nao tem codigo reduzido proprio). Nao e a ECD.",
)


def _campo(campos, numero):
    """Campo `numero` do manual (começa em 1; o campo 1 é o identificador)."""
    return campos[numero - 1]


def _separar_linha(linha):
    """Campos de uma linha, com a barra das pontas tolerada (e não exigida).

    A forma canônica tem `|` no início e no fim de cada registro: `|0200|...|A||||`. A
    contagem é a de campos entre os separadores, com o identificador incluído. Quando a
    linha tem barra nas pontas, ela é tirada; a contagem vale para a forma com barras,
    que é a canônica. A forma sem barras também é lida, e o aviso de "não é a forma do
    exemplo oficial" é dado por quem chama (ver `ler`).

    Entre as opções (com e sem a barra de cada ponta), vale a que dá a contagem do
    registro. Se nenhuma dá, vale a contagem literal, e a diferença é recusada com a linha.
    """
    inicio = linha.startswith(SEPARADOR)
    fim = linha.endswith(SEPARADOR)
    opcoes = []
    # Ordem de preferência: com as DUAS barras tiradas primeiro (a canônica). Tirar só uma
    # barra daria, para `|0200|...|`, um campo a mais que casaria com o registro por engano.
    for tira_inicio in (True, False) if inicio else (False,):
        for tira_fim in (True, False) if fim else (False,):
            nucleo = linha
            if tira_inicio:
                nucleo = nucleo[len(SEPARADOR) :]
            if tira_fim and nucleo.endswith(SEPARADOR):
                nucleo = nucleo[: -len(SEPARADOR)]
            opcoes.append(nucleo.split(SEPARADOR))

    for campos in opcoes:
        registro = campos[0].strip()
        if registro in CAMPOS_POR_REGISTRO and len(campos) == CAMPOS_POR_REGISTRO[registro]:
            return campos
    for campos in opcoes:
        if _PADRAO_REGISTRO.fullmatch(campos[0].strip()):
            return campos  # registro que o produto não usa: contado, não conferido
    return opcoes[0]


def _linha_do_leiaute(campos):
    """Linha escrita na forma canônica: `|` no início, `|` entre os campos e `|` no fim."""
    return SEPARADOR + SEPARADOR.join(campos) + SEPARADOR


def _e_cnpj_alfanumerico(texto):
    """True se `texto` é um CNPJ de 14 caracteres com letras (RC-46), sem contar máscara.

    Recusado NOMEADO neste leiaute: a edição de 2018 do manual só define inscrição numérica.
    """
    canonico = re.sub(r"[./\- ]", "", texto or "").upper()
    return bool(re.fullmatch(r"[A-Z0-9]{14}", canonico)) and bool(re.search(r"[A-Z]", canonico))


MENSAGEM_CNPJ_ALFANUMERICO = (
    "o leiaute do sistema de referência, edição de 2018, só define inscrição numérica; "
    "CNPJ alfanumérico ainda não é suportado nesse formato."
)


# -----------------------------------------------------------------------------
# Codificação e utilitários
# -----------------------------------------------------------------------------


def _decodificar(conteudo):
    """Devolve (texto, codificação, ocorrências). Nunca levanta exceção.

    ISO-8859-1 decodifica qualquer byte, então o que se detecta é UTF-8 real: se o
    arquivo é UTF-8 válido com caractere não ASCII, lê como UTF-8 e avisa.
    """
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
            "O arquivo está em UTF-8. A codificação deste leiaute não está definida no "
            "manual consultado; o padrão do projeto é ISO-8859-1. Foi lido como UTF-8 "
            "por detecção. Confira os acentos antes de aplicar."
        ),
    )
    return texto, "utf-8", [aviso]


def _tem_controle(texto):
    return any(ord(caractere) < 32 for caractere in texto)


def _so_digitos(texto):
    return re.sub(r"\D", "", texto)


def _documento_valido(texto):
    """Campo 2 do 0000 (p. 1225). Aceita máscara, que o importador normaliza.

    Devolve só os dígitos quando são 11 (CPF) ou 14 (CNPJ), senão None.
    """
    if not _PADRAO_MASCARA_DOCUMENTO.fullmatch(texto):
        return None
    digitos = _so_digitos(texto)
    return digitos if len(digitos) in TAMANHOS_DE_DOCUMENTO else None


def _data_valida(texto):
    """Data `dd/mm/aaaa` real (p. 1224), ou None."""
    if not _PADRAO_DATA.fullmatch(texto):
        return None
    try:
        return datetime.strptime(texto, FORMATO_DATA).date()
    except ValueError:
        return None


def _prefixos_da_classificacao(classificacao):
    """Prefixos próprios da classificação, do mais longo para o mais curto.

    Com separador, o corte é no separador: `1.1.01.001` -> `1.1.01`, `1.1`, `1`.
    Sem separador, o corte é por caractere: `1101` -> `110`, `11`, `1`. Isso é
    hipótese (o manual não define máscara), e por isso gera aviso na leitura.
    """
    if SEPARADOR_DE_NIVEL in classificacao:
        niveis = classificacao.split(SEPARADOR_DE_NIVEL)
        return [SEPARADOR_DE_NIVEL.join(niveis[:n]) for n in range(len(niveis) - 1, 0, -1)]
    return [classificacao[:n] for n in range(len(classificacao) - 1, 0, -1)]


def derivar_pai(classificacao, existentes):
    """Código da conta superior de `classificacao`, ou None se ela não tem prefixo.

    Regra: o MAIOR prefixo que é classificação de alguma conta em `existentes`.
    Se nenhum existe, devolve o prefixo IMEDIATO. Esse código não está no arquivo,
    e o núcleo recusa a conta com "não está no arquivo nem no cadastro". Assim o
    erro fica visível, e a conta não cai na raiz em silêncio.
    """
    prefixos = _prefixos_da_classificacao(classificacao)
    if not prefixos:
        return None
    for prefixo in prefixos:
        if prefixo in existentes:
            return prefixo
    return prefixos[0]


# -----------------------------------------------------------------------------
# Leitura
# -----------------------------------------------------------------------------


@dataclass
class _Conta:
    """Um 0200 em montagem, com o 0250 que pode vir logo depois (filho, p. 1277).

    `valido=False` marca o registro com erro. Ele não entra em `contas`, e o 0250
    dele também não, para o erro aparecer uma vez só, na origem.
    """

    linha: int
    valido: bool = False
    classificacao: str = ""
    reduzido: str | None = None
    analitica: bool = False
    nome: str = ""
    referencial: str | None = None
    tem_0250: bool = False
    ativa: bool = True


def _interpretar_0200(numero, campos, ocorrencias):
    """Campos do 0200 (11 com o identificador) -> `_Conta`. Acrescenta erros e avisos."""
    conta = _Conta(linha=numero)
    erros = []

    def recusar(campo, mensagem):
        erros.append(Ocorrencia(numero, f"0200.{campo}", NIVEL_ERRO, mensagem))

    def avisar(campo, mensagem):
        ocorrencias.append(Ocorrencia(numero, f"0200.{campo}", NIVEL_AVISO, mensagem))

    # Campo 2, código reduzido, numérico (p. 1275). Vazio é aceito, porque o manual
    # não torna o campo obrigatório. O DataLedger o guarda só como origem.
    reduzido = _campo(campos, 2)
    if reduzido and not _PADRAO_NUMERO.fullmatch(reduzido):
        recusar(2, f"código reduzido '{reduzido}' não é numérico (registro 0200, campo 2).")
    conta.reduzido = reduzido or None

    # Campo 3, classificação contábil: é a chave da conta no DataLedger. Obrigatória.
    classificacao = _campo(campos, 3)
    if not classificacao:
        recusar(3, "classificação contábil vazia: é a chave da conta (registro 0200, campo 3).")
    elif _tem_controle(classificacao) or len(classificacao) > TAMANHO_MAXIMO_CLASSIFICACAO:
        recusar(3, "classificação com caractere de controle ou acima de 20 caracteres.")
    conta.classificacao = classificacao

    # Campo 4, analítica (A) ou sintética (S).
    tipo = _campo(campos, 4)
    if tipo not in _TIPO_DO_0200:
        recusar(
            4,
            f"tipo '{tipo}' deve ser A (analítica) ou S (sintética) (registro 0200, campo 4).",
        )
    else:
        conta.analitica = _TIPO_DO_0200[tipo]

    # Campo 5, descrição: obrigatória, é o nome da conta.
    descricao = _campo(campos, 5)
    if not descricao:
        recusar(5, "descrição vazia: é o nome da conta (registro 0200, campo 5).")
    elif _tem_controle(descricao):
        recusar(5, "descrição com caractere de controle (registro 0200, campo 5).")
    conta.nome = descricao

    # Campo 6, data do cadastro: validada quando vem. O DataLedger não a usa.
    data_cadastro = _campo(campos, 6)
    if data_cadastro and _data_valida(data_cadastro) is None:
        recusar(6, f"data do cadastro '{data_cadastro}' não é dd/mm/aaaa (registro 0200, campo 6).")

    # Campo 7, situação: A (ativa) ou I (inativa). Inativa é criada inativa no DataLedger,
    # com aviso, e na atualização de conta existente a situação não muda (ver plano.py).
    situacao = _campo(campos, 7)
    if situacao not in _SITUACOES_DO_0200:
        recusar(
            7,
            f"situação '{situacao}' deve ser A (ativa) ou I (inativa) (registro 0200, campo 7).",
        )
    else:
        conta.ativa = situacao == "A"
        if situacao == "I":
            avisar(
                7,
                "conta inativa no arquivo: será criada inativa no DataLedger. Na atualização "
                "de conta que já existe, a situação atual não muda. Confira antes de aplicar.",
            )

    # Campo 8, data de inativação: só faz sentido com situação I.
    data_inativacao = _campo(campos, 8)
    if data_inativacao:
        if _data_valida(data_inativacao) is None:
            recusar(
                8,
                f"data de inativação '{data_inativacao}' não é dd/mm/aaaa "
                "(registro 0200, campo 8).",
            )
        elif situacao != "I":
            avisar(8, "data de inativação informada para conta que não está inativa: ignorada.")

    # Campos 9 a 11: relacionamentos com as demonstrações. O DataLedger não os guarda.
    for numero_do_campo, nome_curto in _RELACIONAMENTOS_DO_0200.items():
        if _campo(campos, numero_do_campo):
            avisar(
                numero_do_campo,
                f"código de relacionamento {nome_curto} não é guardado pelo DataLedger nesta "
                "fatia: ignorado.",
            )

    conta.valido = not erros
    ocorrencias.extend(erros)
    return conta


def _interpretar_0250(numero, campos, conta_acima, ocorrencias):
    """Campos do 0250 (3 com o identificador). Atualiza a conta acima, que é a sua mãe."""
    erros = []

    def recusar(campo, mensagem):
        erros.append(Ocorrencia(numero, f"0250.{campo}", NIVEL_ERRO, mensagem))

    if conta_acima is None:
        recusar(
            1,
            "registro 0250 sem registro 0200 imediatamente acima. É filho do 0200 (registro 0250).",
        )
    else:
        if conta_acima.tem_0250:
            recusar(1, "segundo registro 0250 para o mesmo 0200 (registro 0250).")
        conta_acima.tem_0250 = True
        # Campo 2, classificação referencial (obrigatória); campo 3, órgão R ou C.
        referencial = _campo(campos, 2)
        orgao = _campo(campos, 3)
        if not referencial:
            recusar(2, "classificação referencial vazia (registro 0250, campo 2).")
        if orgao not in _ORGAOS_DO_0250:
            recusar(3, f"órgão '{orgao}' deve ser R (Receita Federal) ou C (Banco Central).")
        if erros:
            conta_acima.valido = False
        elif referencial:
            conta_acima.referencial = referencial
    ocorrencias.extend(erros)


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê o plano do leiaute com separador. Não levanta exceção por conteúdo ruim.

    Registros que o DataLedger não usa são CONTADOS em `registros_ignorados`, não
    descartados em silêncio. Campo que o manual não define vira erro nomeado, não
    palpite. A superior de cada conta sai de `derivar_pai`, com as contas do
    próprio arquivo.
    """
    texto, codificacao, ocorrencias = _decodificar(conteudo)
    resultado = ResultadoLeitura(formato=FORMATO, codificacao=codificacao)
    ignorados = Counter()

    contas_lidas = []  # _Conta de cada 0200, na ordem do arquivo
    conta_acima = None  # o último 0200, enquanto o próximo registro não for outro
    linha_do_documento = None

    sem_barras_nas_pontas = False
    for numero, bruta in enumerate(texto.split("\n"), start=1):
        linha = bruta.rstrip("\r")
        if not linha.strip():
            continue

        # Forma canônica: `|` no início e no fim. A forma sem barras é aceita, com UM aviso
        # por arquivo (ver adiante); a com barras não gera aviso.
        if not (linha.startswith(SEPARADOR) and linha.endswith(SEPARADOR)):
            sem_barras_nas_pontas = True
        brutos = _separar_linha(linha)
        if not any(valor.strip() for valor in brutos):
            conta_acima = None  # linha só com barras: não tem registro
            continue

        registro = brutos[0].strip()
        if not _PADRAO_REGISTRO.fullmatch(registro):
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "REG",
                    NIVEL_ERRO,
                    f"identificador de registro '{registro}' inválido: são 4 dígitos "
                    "(campo 1 de cada registro).",
                )
            )
            conta_acima = None
            continue

        if registro not in CAMPOS_POR_REGISTRO:
            ignorados[registro] += 1
            conta_acima = None
            continue

        campos = [valor.strip() for valor in brutos]
        esperados = CAMPOS_POR_REGISTRO[registro]
        if len(campos) != esperados:
            mensagem = (
                f"o registro {registro} tem {esperados} campos (identificador incluído); "
                f"a linha tem {len(campos)}."
            )
            ocorrencias.append(Ocorrencia(numero, registro, NIVEL_ERRO, mensagem))
            if registro == REG_CONTA:
                # Conta com estrutura errada: não entra. Mesmo assim, o 0250 dela
                # precisa encontrar um 0200 acima, para não gerar erro extra.
                conta_acima = _Conta(linha=numero, valido=False)
                contas_lidas.append(conta_acima)
            elif registro == REG_REFERENCIAL and conta_acima is not None:
                conta_acima.valido = False
            else:
                conta_acima = None
            continue

        if registro == REG_DOCUMENTO:
            conta_acima = None
            if linha_do_documento is not None:
                ocorrencias.append(
                    Ocorrencia(
                        numero,
                        "0000",
                        NIVEL_ERRO,
                        f"registro 0000 repetido (primeiro na linha {linha_do_documento}).",
                    )
                )
                continue
            linha_do_documento = numero
            inscricao = _campo(campos, 2)
            digitos = None
            if not re.search(r"[^0-9./\- ]", inscricao):
                digitos = _documento_valido(inscricao)
            if digitos is None:
                # A6/RC-46: CNPJ com letra tem mensagem própria, e não a genérica de "CNPJ (14)".
                mensagem = (
                    MENSAGEM_CNPJ_ALFANUMERICO
                    if _e_cnpj_alfanumerico(inscricao)
                    else "inscrição da empresa deve ser CNPJ (14) ou CPF (11), com ou sem "
                    "máscara (registro 0000, campo 2)."
                )
                ocorrencias.append(Ocorrencia(numero, "0000.2", NIVEL_ERRO, mensagem))
            else:
                # Máscara é normalizada aqui; o núcleo compara só os dígitos.
                resultado.documento_declarado = digitos
            continue

        if registro == REG_CONTA:
            conta_acima = _interpretar_0200(numero, campos, ocorrencias)
            contas_lidas.append(conta_acima)
            continue

        # REG_REFERENCIAL: o 0250 segue o 0200 (filho). Não encerra a associação,
        # para que um segundo 0250 seguido seja reconhecido como repetido.
        _interpretar_0250(numero, campos, conta_acima, ocorrencias)

    if linha_do_documento is None:
        ocorrencias.append(
            Ocorrencia(
                0,
                "0000",
                NIVEL_ERRO,
                "arquivo sem o registro 0000 (inscrição da empresa). Sem ele, não há como "
                "confirmar que o arquivo é da empresa escolhida.",
            )
        )

    if sem_barras_nas_pontas:
        ocorrencias.append(
            Ocorrencia(
                0,
                "formato",
                NIVEL_AVISO,
                "o arquivo traz linhas sem '|' no início e no fim: não é a forma do exemplo "
                "oficial do fornecedor, que tem '|' nas pontas de cada registro. O importador "
                "aceitou a forma sem barras. Confira o arquivo.",
            )
        )
    _montar_contas(contas_lidas, resultado, ocorrencias)
    resultado.registros_ignorados = dict(sorted(ignorados.items()))
    ocorrencias.sort(key=lambda o: (o.linha, o.campo))
    resultado.ocorrencias = ocorrencias
    return resultado


def _montar_contas(contas_lidas, resultado, ocorrencias):
    """Converte os `_Conta` válidos em `ContaLida`, com as superiores POSSÍVEIS.

    O leitor não escolhe a superior contra o cadastro: não o conhece. Entrega o imediato
    (`codigo_pai`) e a lista de prefixos (`superiores_candidatas`), e o núcleo escolhe o
    maior que existe no arquivo OU no cadastro (A3).
    """
    vistos = {}
    for conta in contas_lidas:
        if not conta.valido:
            continue
        if conta.classificacao in vistos:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "0200.3",
                    NIVEL_ERRO,
                    f"classificação '{conta.classificacao}' repetida (primeira na linha "
                    f"{vistos[conta.classificacao]}).",
                )
            )
            continue
        vistos[conta.classificacao] = conta.linha

        candidatas = _prefixos_da_classificacao(conta.classificacao)
        imediato = candidatas[0] if candidatas else None
        if imediato is not None and SEPARADOR_DE_NIVEL not in conta.classificacao:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "0200.3",
                    NIVEL_AVISO,
                    f"superior '{imediato}' tomada pelo prefixo da classificação, sem separador "
                    "de nível (o manual não define máscara). Confira a hierarquia.",
                )
            )
        resultado.contas.append(
            ContaLida(
                linha=conta.linha,
                codigo=conta.classificacao,
                nome=conta.nome,
                codigo_pai=imediato,
                analitica=conta.analitica,
                tipo=None,  # HI-87: o arquivo não traz tipo.
                natureza=None,  # HI-88: o arquivo não traz natureza.
                codigo_origem=conta.reduzido,
                referencial=conta.referencial,
                ativa=conta.ativa,
                superiores_candidatas=tuple(candidatas),
            )
        )


# -----------------------------------------------------------------------------
# Escrita
# -----------------------------------------------------------------------------


def _campo_escrevivel(valor, rotulo, linha, ocorrencias):
    """Confere um campo antes da escrita. Acrescenta erro e devolve False se não cabe."""

    def recusar(mensagem):
        ocorrencias.append(Ocorrencia(linha, rotulo, NIVEL_ERRO, mensagem))

    if not valor:
        recusar(f"{rotulo} vazio.")
        return False
    if SEPARADOR in valor:
        recusar(f"{rotulo} contém '|', que é o separador do leiaute.")
        return False
    if _tem_controle(valor):
        recusar(f"{rotulo} contém caractere de controle.")
        return False
    try:
        valor.encode("iso-8859-1")
    except UnicodeEncodeError:
        # Recusa explícita: a exportação nunca troca caractere em silêncio.
        recusar(
            f"{rotulo} contém caractere fora de ISO-8859-1. A exportação foi recusada; troque o "
            "caractere no cadastro."
        )
        return False
    return True


def escrever(contas, *, data_alteracao=None, documento=None):
    """Escreve o plano no leiaute com separador: um 0000 e um 0200 por conta.

    - `documento` é o CNPJ/CPF da empresa, obrigatório para o 0000 (campo 2). Sem
      ele, a escrita é recusada: não há 0000 inventado.
    - `data_alteracao` é ignorada. O campo 6 do 0200 (data do cadastro) sai vazio,
      porque o DataLedger não guarda data de cadastro por conta.
    - Código reduzido (0200, campo 2): o DataLedger não tem. Cada conta recebe um
      número sequencial a partir de 1, pela ordem do código. É estável só enquanto o
      plano não muda: incluir uma conta desloca os números seguintes.
    - Situação (0200, campo 7) sai A ou I, pelo `ativa` de cada conta. Conta sem
      situação informada é recusada: não há palpite de situação.
    - A superior NÃO é escrita: o leiaute não tem campo para ela. Ela é recuperada
      pela classificação na leitura. Por isso a escrita só aceita o plano se a
      classificação reproduz a superior de cada conta (ver `derivar_pai`).
    - Levanta `IntercambioRecusado` com todas as ocorrências, sem escrita parcial.
    - O aviso sobre o código reduzido não sai no arquivo: o núcleo o leva à
      exportação (`AVISOS_DE_EXPORTACAO`).
    """
    if documento is None:
        raise IntercambioRecusado(
            "o leiaute do sistema de referência exige o CNPJ/CPF da empresa no registro 0000."
        )
    if _e_cnpj_alfanumerico(documento):
        raise IntercambioRecusado(MENSAGEM_CNPJ_ALFANUMERICO)
    digitos = _documento_valido(documento)
    if digitos is None:
        raise IntercambioRecusado("o CNPJ/CPF da empresa para o registro 0000 é inválido.")

    contas = list(contas)
    ocorrencias = []
    codigos = set()
    for conta in contas:
        if conta.codigo in codigos:
            ocorrencias.append(
                Ocorrencia(conta.linha, "codigo", NIVEL_ERRO, f"código '{conta.codigo}' repetido.")
            )
        codigos.add(conta.codigo)

    for conta in contas:
        _campo_escrevivel(conta.codigo, "classificação contábil", conta.linha, ocorrencias)
        _campo_escrevivel(conta.nome, "descrição", conta.linha, ocorrencias)
        if conta.referencial is not None:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "referencial",
                    NIVEL_ERRO,
                    "o DataLedger não guarda o órgão do plano referencial (registro 0250, campo "
                    "3), e a exportação não o inventa. O plano referencial não é exportado.",
                )
            )
        if conta.ativa is None:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "ativa",
                    NIVEL_ERRO,
                    f"a situação (ativa ou inativa) de '{conta.codigo}' não foi informada. "
                    "A escrita não a inventa.",
                )
            )
        derivado = derivar_pai(conta.codigo, codigos)
        if derivado != conta.codigo_pai:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "classificacao",
                    NIVEL_ERRO,
                    f"a superior de '{conta.codigo}' é "
                    f"'{conta.codigo_pai or 'raiz'}', e a classificação não a reproduz "
                    f"(seria '{derivado or 'raiz'}'). O leiaute recupera a superior pela "
                    "classificação, então este plano não pode ser exportado nele.",
                )
            )

    if ocorrencias:
        raise IntercambioRecusado(
            "O plano não cabe no leiaute do sistema de referência: "
            + "; ".join(f"linha {o.linha}, {o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )

    reduzidos = {codigo: n for n, codigo in enumerate(sorted(codigos), start=1)}
    # Forma canônica: `|` no início e no fim de cada registro (ver o docstring do módulo).
    linhas = [_linha_do_leiaute([REG_DOCUMENTO, digitos])]
    for conta in sorted(contas, key=lambda c: c.codigo):
        linhas.append(
            _linha_do_leiaute(
                [
                    REG_CONTA,
                    str(reduzidos[conta.codigo]),
                    conta.codigo,
                    "A" if conta.analitica else "S",
                    conta.nome,
                    "",  # campo 6: data do cadastro (não guardada)
                    "A" if conta.ativa else "I",  # campo 7: situação real da conta
                    "",  # campo 8: data de inativação
                    "",  # campo 9: DLPA
                    "",  # campo 10: DOAR
                    "",  # campo 11: DRE
                ]
            )
        )
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
