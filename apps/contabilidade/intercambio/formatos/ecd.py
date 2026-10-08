"""Plano de contas no leiaute 9 da ECD: registros I050 e I051 (DL-077, fatia 1).

FONTE. Manual de Orientação do Leiaute 9 da ECD, Anexo ao Ato Declaratório
Executivo Cofis nº 01/2026, atualização de maio de 2026, 236 páginas, lido na
fonte oficial (http://sped.rfb.gov.br/arquivo/download/7990) em 08/10/2026.
O texto do manual NÃO é copiado para cá (RC-167): cita-se o registro, o campo
e a página IMPRESSA no rodapé ("Página N de 236").

ESCOPO DESTA FATIA.
- Lê e escreve somente I050 (plano de contas) e I051 (plano referencial).
  Os demais registros do leiaute são CONTADOS como ignorados na leitura, e não
  são escritos.
- Um arquivo escrito aqui NÃO é a ECD: não traz 0000, I001, I010, I990, bloco
  J, 9999 nem assinatura. É um trecho do bloco I, com o plano. O nome do
  arquivo e a tela dizem isso.
- A ECD NÃO traz natureza devedora/credora (HI-88): na leitura, natureza é
  `None`; na escrita, não sai.
- COD_NAT 04 (resultado) não separa receita de despesa (HI-87): na leitura,
  tipo é `None`; na escrita, receita e despesa saem como 04.
- COD_NAT 05 (compensação) e 09 (outras) são RECUSADAS na leitura com erro
  nomeado: o produto não cadastra essas contas nesta fatia.

FORMATO DO ARQUIVO (pp. 52-53).
- Texto ISO-8859-1 (Latin-1), sem campos compactados (p. 52).
- Cada registro começa e termina com "|"; "|" não pode fazer parte de um campo
  (p. 52). Campo vazio é "||" (p. 53).
- Fim de linha CR LF (p. 52).
- Campo C: caracteres imprimíveis, sem "|"; caracteres 00 a 31 não são
  permitidos; tamanho máximo padrão de 255 (p. 53).
- Campo N: só dígitos; vírgula é o separador decimal (p. 53).
- Data: ddmmaaaa, sem separador (p. 53).

Na leitura, espaços nas extremidades de cada campo são descartados. A leitura
também aceita UTF-8, com DETECÇÃO e AVISO (ver `_decodificar`), porque arquivo
gerado por ferramenta moderna costuma vir em UTF-8.
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date

from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    ContaLida,
    IntercambioRecusado,
    Ocorrencia,
    ResultadoLeitura,
)
from apps.contabilidade.models import TipoConta

FORMATO = "ecd"

# Registros válidos no leiaute 9. Fonte: Tabela de Registros (pp. 57-58) e os
# registros do bloco 9 (9001 na p. 230, 9900 na p. 231, 9990 na p. 232 e 9999
# na p. 233). Um REG fora desta lista é "registro desconhecido": não é ruído de
# outro leiaute, é erro.
REGISTROS_DO_LEIAUTE_9 = frozenset(
    {
        # Bloco 0 (pp. 57-58)
        "0000",
        "0001",
        "0007",
        "0020",
        "0035",
        "0150",
        "0180",
        "0990",
        # Bloco C (pp. 57-58; C052 na p. 95)
        "C001",
        "C040",
        "C050",
        "C051",
        "C052",
        "C150",
        "C155",
        "C600",
        "C650",
        "C990",
        # Bloco I (pp. 57-58)
        "I001",
        "I010",
        "I012",
        "I015",
        "I020",
        "I030",
        "I050",
        "I051",
        "I052",
        "I053",
        "I075",
        "I100",
        "I150",
        "I155",
        "I157",
        "I200",
        "I250",
        "I300",
        "I310",
        "I350",
        "I355",
        "I500",
        "I510",
        "I550",
        "I555",
        "I990",
        # Bloco J (pp. 57-58)
        "J001",
        "J005",
        "J100",
        "J150",
        "J210",
        "J215",
        "J800",
        "J801",
        "J900",
        "J930",
        "J932",
        "J935",
        "J990",
        # Bloco K (pp. 57-58)
        "K001",
        "K030",
        "K100",
        "K110",
        "K115",
        "K200",
        "K210",
        "K300",
        "K310",
        "K315",
        "K990",
        # Bloco 9 (pp. 230-233)
        "9001",
        "9900",
        "9990",
        "9999",
    }
)

# Os únicos registros que este módulo LÊ.
REGISTROS_USADOS = frozenset({"I050", "I051"})

# Registro 0000 (abertura e identificação). Traz o CNPJ da empresa (campo 06, p. 64),
# e é o único campo dele que o DataLedger lê, só para a conferência com a empresa.
REGISTRO_DE_IDENTIFICACAO = "0000"
_INDICE_DO_CNPJ_NO_0000 = 5  # campos[0] é o REG; o campo 06 do manual fica no índice 5
_PADRAO_CNPJ_DIGITOS = re.compile(r"[0-9]{14}")

# Registros que, pela tabela de níveis (pp. 57-58), são filhos do I050 (nível 4)
# ou o próprio I050. Eles não encerram a associação entre um I051 e o I050 acima.
# Qualquer outro registro encerra essa associação.
REGISTROS_FILHOS_DO_I050 = frozenset({"I050", "I051", "I052", "I053"})

# Tabela de natureza das contas/grupos (p. 119). 04 é "contas de resultado":
# receita e despesa, que a ECD não separa (HI-87) -> tipo None na leitura.
COD_NAT_PARA_TIPO = {
    "01": TipoConta.ATIVO,
    "02": TipoConta.PASSIVO,
    "03": TipoConta.PATRIMONIO_LIQUIDO,
    "04": None,
}
# 05 e 09 existem no leiaute (p. 119), mas o DataLedger não cadastra essas
# contas nesta fatia. A recusa é nomeada, não um "código inválido" genérico.
COD_NAT_NAO_TRATADOS = {
    "05": "contas de compensação",
    "09": "outras contas",
}
# Escrita: o tipo do DataLedger vira o código da tabela da p. 119. Receita e
# despesa saem ambos como 04, porque a ECD não as separa.
COD_NAT_DO_TIPO = {
    TipoConta.ATIVO: "01",
    TipoConta.PASSIVO: "02",
    TipoConta.PATRIMONIO_LIQUIDO: "03",
    TipoConta.RECEITA: "04",
    TipoConta.DESPESA: "04",
}

TAMANHO_MAXIMO_CAMPO_C = 255  # p. 53

_PADRAO_NUMERO = re.compile(r"[0-9]+")
_PADRAO_DATA_DDMMAAAA = re.compile(r"[0-9]{8}")


# -----------------------------------------------------------------------------
# Leitura
# -----------------------------------------------------------------------------


def _decodificar(conteudo):
    """Devolve (texto, codificação, ocorrências). Nunca levanta exceção.

    A ECD exige ISO-8859-1 (p. 52). Como ISO-8859-1 decodifica qualquer byte,
    não há "Latin-1 inválido" para detectar. O que se detecta é UTF-8: se o
    arquivo é UTF-8 válido e tem caractere não ASCII, lemos como UTF-8 e
    avisamos. Um arquivo em Latin-1 que, por acaso, seja UTF-8 válido é raro;
    o aviso existe para o caso de o contador ter recebido UTF-8 de verdade.
    """
    if conteudo.isascii():
        # ASCII é subconjunto de ISO-8859-1 (p. 52): nada a avisar.
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
            "O arquivo está em UTF-8, e o leiaute da ECD pede ISO-8859-1 (p. 52). "
            "Foi lido como UTF-8 por detecção. Confira os acentos antes de aplicar."
        ),
    )
    return texto, "utf-8", [aviso]


def _data_ddmmaaaa_valida(texto):
    """True se `texto` for ddmmaaaa e uma data real (p. 53)."""
    if not _PADRAO_DATA_DDMMAAAA.fullmatch(texto):
        return False
    try:
        date(int(texto[4:]), int(texto[2:4]), int(texto[:2]))
    except ValueError:
        return False
    return True


def _tem_controle(texto):
    """Caractere 00 a 31 num campo C não é permitido (p. 53)."""
    return any(ord(caractere) < 32 for caractere in texto)


@dataclass
class _I050:
    """I050 aceito na leitura, ainda sujeito às checagens entre registros."""

    linha: int
    codigo: str
    nome: str
    codigo_pai: str | None
    analitica: bool
    cod_nat: str
    nivel: int
    tipo: TipoConta | None
    referencial: str | None = None


_I050_RECUSADO = object()


def _interpretar_i050(numero, campos):
    """(_I050 ou None, ocorrências) a partir dos campos do I050.

    `campos` são os 8 campos já separados, o REG (campo 01) primeiro (p. 118).
    """
    erros = []

    def recusar(campo, mensagem):
        erros.append(Ocorrencia(linha=numero, campo=campo, nivel=NIVEL_ERRO, mensagem=mensagem))

    if len(campos) != 8:
        recusar("REG", f"I050 tem 8 campos (pp. 118-119); o registro traz {len(campos)}.")
        return None, erros

    _reg, dt_alt, cod_nat, ind_cta, nivel_txt, cod_cta, cod_cta_sup, cta = (
        valor.strip() for valor in campos
    )

    # Campo 02, DT_ALT, obrigatório, data ddmmaaaa (p. 118; formato p. 53).
    if not _data_ddmmaaaa_valida(dt_alt):
        recusar("DT_ALT", f"data '{dt_alt}' não é ddmmaaaa válida (p. 53).")

    # Campo 03, COD_NAT, obrigatório, tabela p. 119; REGRA_TABELA_NATUREZA, p. 120.
    if cod_nat in COD_NAT_NAO_TRATADOS:
        recusar(
            "COD_NAT",
            f"natureza '{cod_nat}' ({COD_NAT_NAO_TRATADOS[cod_nat]}) não é cadastrada "
            "pelo DataLedger nesta fatia (tabela da p. 119).",
        )
    elif cod_nat not in COD_NAT_PARA_TIPO:
        recusar(
            "COD_NAT",
            f"código de natureza '{cod_nat}' não existe na tabela da p. 119 "
            "(REGRA_TABELA_NATUREZA, p. 120).",
        )

    # Campo 04, IND_CTA: S (sintética) ou A (analítica), p. 118.
    if ind_cta not in ("S", "A"):
        recusar(
            "IND_CTA", f"indicador '{ind_cta}' deve ser S (sintética) ou A (analítica), p. 118."
        )

    # Campo 05, NIVEL, numérico, maior ou igual a 1 (p. 119; REGRA_MAIOR_QUE_UM, p. 120).
    nivel = None
    if not _PADRAO_NUMERO.fullmatch(nivel_txt) or int(nivel_txt) < 1:
        recusar("NIVEL", f"nível '{nivel_txt}' deve ser um número inteiro maior ou igual a 1.")
    else:
        nivel = int(nivel_txt)

    # Campo 06, COD_CTA, obrigatório (p. 118; REGRA_CAMPO_OBRIGATORIO, p. 120).
    if not cod_cta:
        recusar("COD_CTA", "código da conta é obrigatório (p. 118).")
    elif len(cod_cta) > TAMANHO_MAXIMO_CAMPO_C or _tem_controle(cod_cta):
        recusar("COD_CTA", "código com caractere de controle ou acima de 255 caracteres (p. 53).")

    # Campo 07, COD_CTA_SUP: obrigatório só se NIVEL > 1; vazio se NIVEL = 1 (pp. 118-121).
    if nivel is not None:
        if nivel == 1 and cod_cta_sup:
            recusar(
                "COD_CTA_SUP",
                "conta de nível 1 não tem conta superior: o campo fica vazio "
                "(REGRA_CONTA_SUPERIOR_NAO_SE_APLICA, p. 121).",
            )
        if nivel > 1 and not cod_cta_sup:
            recusar(
                "COD_CTA_SUP",
                f"conta de nível {nivel} exige a conta superior "
                "(REGRA_COD_CTA_SUP_OBRIGATORIO, p. 120).",
            )
    if cod_cta and cod_cta_sup == cod_cta:
        recusar(
            "COD_CTA_SUP",
            "a conta não pode ser superior de si mesma (REGRA_COD_CTA_IGUAL_COD_CTA_SUP, p. 120).",
        )
    if cod_cta_sup and (len(cod_cta_sup) > TAMANHO_MAXIMO_CAMPO_C or _tem_controle(cod_cta_sup)):
        recusar("COD_CTA_SUP", "código superior com caractere de controle ou acima de 255 (p. 53).")

    # Campo 08, CTA, nome obrigatório, C até 255 (p. 118; p. 53).
    if not cta:
        recusar("CTA", "nome da conta é obrigatório (p. 118).")
    elif len(cta) > TAMANHO_MAXIMO_CAMPO_C or _tem_controle(cta):
        recusar("CTA", "nome com caractere de controle ou acima de 255 caracteres (p. 53).")

    if erros:
        return None, erros

    return (
        _I050(
            linha=numero,
            codigo=cod_cta,
            nome=cta,
            codigo_pai=cod_cta_sup or None,
            analitica=ind_cta == "A",
            cod_nat=cod_nat,
            nivel=nivel,
            tipo=COD_NAT_PARA_TIPO[cod_nat],
        ),
        [],
    )


def _interpretar_i051(numero, campos, i050):
    """Processa um I051 ligado ao I050 `i050` (que é alterado: recebe o referencial).

    Devolve as ocorrências do registro.
    """
    erros = []

    def recusar(campo, mensagem, nivel=NIVEL_ERRO):
        erros.append(Ocorrencia(linha=numero, campo=campo, nivel=nivel, mensagem=mensagem))

    if len(campos) != 3:
        recusar("REG", f"I051 tem 3 campos (p. 123); o registro traz {len(campos)}.")
        return erros

    _reg, cod_ccus, cod_cta_ref = (valor.strip() for valor in campos)

    # I051 é facultativo e só existe para conta analítica (p. 123-124,
    # REGRA_REGISTRO_PARA_CONTA_ANALITICA).
    if not i050.analitica:
        recusar(
            "REG",
            f"I051 só existe para conta analítica, e a conta {i050.codigo} é sintética "
            "(REGRA_REGISTRO_PARA_CONTA_ANALITICA, p. 124).",
        )
        return erros

    # Campo 02, COD_CCUS: o DataLedger não tem centro de custo nesta fatia. O
    # mapeamento por centro de custo não é guardado, e isso é dito, não omitido.
    if cod_ccus:
        recusar(
            "COD_CCUS",
            "mapeamento por centro de custo não é guardado pelo DataLedger nesta fatia: "
            "este I051 foi ignorado (p. 123).",
            nivel=NIVEL_AVISO,
        )
        return erros

    # Campo 03, COD_CTA_REF, obrigatório (p. 123).
    if not cod_cta_ref:
        recusar("COD_CTA_REF", "código da conta no plano referencial é obrigatório (p. 123).")
        return erros
    if len(cod_cta_ref) > TAMANHO_MAXIMO_CAMPO_C or _tem_controle(cod_cta_ref):
        recusar("COD_CTA_REF", "código referencial com caractere de controle ou acima de 255.")
        return erros
    if i050.referencial is not None:
        recusar(
            "COD_CTA_REF",
            f"segundo I051 sem centro de custo para a conta {i050.codigo}: a chave do "
            "registro é COD_CCUS (p. 123).",
        )
        return erros
    i050.referencial = cod_cta_ref
    return erros


def _ler_documento_do_0000(numero, campos, resultado, ocorrencias):
    """Guarda em `documento_declarado` o CNPJ do 0000 (campo 06, p. 64), se houver.

    O manual torna o campo obrigatório, mas um trecho de ECD sem ele não é recusado
    aqui: sem CNPJ não há conferência, e o núcleo diz isso pelo `documento_declarado`
    vazio. O CNPJ é 14 dígitos (tamanho do campo, p. 64); nada é aceito com máscara,
    porque o manual não a prevê, e uma máscara seria palpite sobre o formato.
    Só o primeiro 0000 conta: o manual limita o registro a uma ocorrência.
    """
    if len(campos) <= _INDICE_DO_CNPJ_NO_0000 or resultado.documento_declarado is not None:
        return
    cnpj = campos[_INDICE_DO_CNPJ_NO_0000].strip()
    if not cnpj:
        return
    if not _PADRAO_CNPJ_DIGITOS.fullmatch(cnpj):
        ocorrencias.append(
            Ocorrencia(
                numero,
                "0000.06",
                NIVEL_ERRO,
                "CNPJ do registro 0000 (campo 06, p. 64) deve ter 14 dígitos, sem máscara. "
                "Não é possível conferir a empresa.",
            )
        )
        return
    resultado.documento_declarado = cnpj


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê um trecho de ECD e devolve o plano de contas (I050 e I051).

    Não levanta exceção por conteúdo ruim: cada problema vira `Ocorrencia` com
    linha e campo. Um registro com erro não entra em `contas`, e a conta que
    depende de uma conta superior recusada também não entra: o erro aponta a
    origem, não a consequência.
    """
    texto, codificacao, ocorrencias = _decodificar(conteudo)
    resultado = ResultadoLeitura(formato=FORMATO, codificacao=codificacao)
    ignorados = Counter()

    i050s = []  # I050 aceitos, em ordem de arquivo
    recusados = {}  # código -> linha, de I050 recusado (para a cascata abaixo)
    ultimo = None  # _I050 aceito, _I050_RECUSADO, ou None (sem I050 acima)

    for numero, bruta in enumerate(texto.split("\n"), start=1):
        linha = bruta.rstrip("\r")
        if not linha.strip():
            continue
        if not (len(linha) >= 2 and linha.startswith("|") and linha.endswith("|")):
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "linha",
                    NIVEL_ERRO,
                    "linha fora do leiaute: cada registro começa e termina com '|' (p. 52).",
                )
            )
            continue

        campos = linha[1:-1].split("|")
        reg = campos[0].strip()

        if reg not in REGISTROS_DO_LEIAUTE_9:
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "REG",
                    NIVEL_ERRO,
                    f"registro desconhecido '{reg}': não consta da tabela de registros do "
                    "leiaute 9 (pp. 57-58 e 230-233).",
                )
            )
            continue

        if reg == REGISTRO_DE_IDENTIFICACAO:
            # O 0000 não entra no plano, mas traz o CNPJ que o núcleo confere com a
            # empresa (ver `_ler_documento_do_0000`). Continua contado como ignorado.
            _ler_documento_do_0000(numero, campos, resultado, ocorrencias)

        if reg not in REGISTROS_FILHOS_DO_I050:
            # Outro registro encerra a associação com o I050 anterior.
            ultimo = None

        if reg not in REGISTROS_USADOS:
            ignorados[reg] += 1
            continue

        if reg == "I050":
            i050, erros = _interpretar_i050(numero, campos)
            ocorrencias.extend(erros)
            if i050 is None:
                ultimo = _I050_RECUSADO
                if len(campos) == 8 and campos[5].strip():
                    recusados.setdefault(campos[5].strip(), numero)
            else:
                ultimo = i050
                i050s.append(i050)
            continue

        # I051, ligado ao I050 imediatamente acima.
        if ultimo is None:
            ocorrencias.append(
                Ocorrencia(
                    numero,
                    "REG",
                    NIVEL_ERRO,
                    "I051 sem I050 analítica imediatamente acima (p. 124).",
                )
            )
        elif ultimo is not _I050_RECUSADO:
            # Se o I050 acima foi recusado, o erro já está registrado nele.
            ocorrencias.extend(_interpretar_i051(numero, campos, ultimo))

    # Checagens que dependem de dois I050 (pp. 119-121). Feitas depois da leitura
    # inteira, porque a conta superior pode vir depois da filha no arquivo.
    aceitos = {}
    validos = []
    for i050 in i050s:
        if i050.codigo in aceitos:
            ocorrencias.append(
                Ocorrencia(
                    i050.linha,
                    "COD_CTA",
                    NIVEL_ERRO,
                    f"código '{i050.codigo}' repetido no arquivo (REGRA_COD_CTA_DUPLICADO, "
                    f"p. 119); a primeira ocorrência é a da linha {aceitos[i050.codigo].linha}.",
                )
            )
            recusados.setdefault(i050.codigo, i050.linha)
            continue
        aceitos[i050.codigo] = i050
        validos.append(i050)

    # Passo A: regras da conta superior, para quem tem a superior no arquivo.
    descartados = set()
    for i050 in validos:
        if i050.codigo_pai is None or i050.codigo_pai not in aceitos:
            continue
        pai = aceitos[i050.codigo_pai]
        erro = None
        if pai.analitica:
            erro = (
                "COD_CTA_SUP",
                f"a conta superior {pai.codigo} é analítica (IND_CTA=A) e não pode ter filhas "
                "(REGRA_CONTA_NIVEL_SUPERIOR_NAO_SINTETICA, p. 120).",
            )
        elif i050.nivel <= pai.nivel:
            erro = (
                "NIVEL",
                f"nível {i050.nivel} não é maior que o da conta superior ({pai.nivel}) "
                "(REGRA_NIVEL_DE_CONTA_NIVEL_SUPERIOR_INVALIDO, p. 120).",
            )
        elif i050.nivel > 2 and i050.cod_nat != pai.cod_nat:
            erro = (
                "COD_NAT",
                f"natureza '{i050.cod_nat}' difere da conta superior ('{pai.cod_nat}') "
                "(REGRA_NATUREZA_CONTA, p. 121).",
            )
        if erro is not None:
            ocorrencias.append(Ocorrencia(i050.linha, erro[0], NIVEL_ERRO, erro[1]))
            descartados.add(i050.codigo)
            recusados.setdefault(i050.codigo, i050.linha)
        elif i050.nivel != pai.nivel + 1:
            ocorrencias.append(
                Ocorrencia(
                    i050.linha,
                    "NIVEL",
                    NIVEL_AVISO,
                    f"nível {i050.nivel} não é o da conta superior ({pai.nivel}) acrescido de 1, "
                    "que é a convenção do leiaute (p. 119).",
                )
            )

    # Passo B: quem tem conta superior recusada também é recusado (em cascata).
    mudou = True
    while mudou:
        mudou = False
        for i050 in validos:
            if i050.codigo in descartados or i050.codigo_pai not in recusados:
                continue
            ocorrencias.append(
                Ocorrencia(
                    i050.linha,
                    "COD_CTA_SUP",
                    NIVEL_ERRO,
                    f"a conta superior {i050.codigo_pai} foi recusada nesta leitura "
                    f"(linha {recusados[i050.codigo_pai]}). Corrija-a antes.",
                )
            )
            descartados.add(i050.codigo)
            recusados.setdefault(i050.codigo, i050.linha)
            mudou = True

    for i050 in validos:
        if i050.codigo in descartados:
            continue
        resultado.contas.append(
            ContaLida(
                linha=i050.linha,
                codigo=i050.codigo,
                nome=i050.nome,
                codigo_pai=i050.codigo_pai,
                analitica=i050.analitica,
                tipo=i050.tipo.value if i050.tipo is not None else None,
                natureza=None,  # HI-88: a ECD não traz natureza.
                codigo_origem=None,
                referencial=i050.referencial,
            )
        )

    resultado.ocorrencias = sorted(ocorrencias, key=lambda o: (o.linha, o.campo))
    resultado.registros_ignorados = dict(sorted(ignorados.items()))
    return resultado


# -----------------------------------------------------------------------------
# Escrita
# -----------------------------------------------------------------------------


def _campo_de_texto_recusavel(valor, rotulo, linha, ocorrencias):
    """Confere um campo C antes da escrita. Acrescenta erros; devolve True se ok."""

    def recusar(mensagem):
        ocorrencias.append(Ocorrencia(linha, rotulo, NIVEL_ERRO, mensagem))

    if not valor:
        recusar(f"{rotulo} não pode ficar vazio (p. 118).")
        return False
    if "|" in valor:
        recusar(f"{rotulo} contém '|', que é o separador do leiaute (p. 52).")
        return False
    if _tem_controle(valor):
        recusar(f"{rotulo} contém caractere de controle (00 a 31), não permitido (p. 53).")
        return False
    if len(valor) > TAMANHO_MAXIMO_CAMPO_C:
        recusar(
            f"{rotulo} tem {len(valor)} caracteres; o máximo é {TAMANHO_MAXIMO_CAMPO_C} (p. 53)."
        )
        return False
    for caractere in valor:
        try:
            caractere.encode("iso-8859-1")
        except UnicodeEncodeError:
            # Recusa explícita: a exportação nunca substitui caractere em silêncio.
            recusar(
                f"{rotulo} contém o caractere '{caractere}', que não existe em ISO-8859-1 "
                "(Latin-1), exigido pelo leiaute (p. 52). A exportação foi recusada; "
                "troque o caractere no cadastro."
            )
            return False
    return True


def escrever(contas, *, data_alteracao=None):
    """Escreve I050 (e I051 quando a conta tem `referencial`) em ISO-8859-1, CRLF.

    `contas` vem na ordem em que devem sair (o núcleo ordena em árvore, com a
    conta superior antes das filhas). `data_alteracao` vai em DT_ALT de todos os
    I050 (p. 118) e é obrigatória: o DataLedger não guarda a data da última
    alteração de cada conta, e não inventa uma.

    Levanta `IntercambioRecusado`, com as ocorrências, se alguma conta não cabe
    no leiaute. Nada é escrito parcialmente.
    """
    if not isinstance(data_alteracao, date):
        raise IntercambioRecusado(
            "A data de inclusão/alteração (DT_ALT, p. 118) é obrigatória para o I050."
        )
    dt_alt = data_alteracao.strftime("%d%m%Y")

    ocorrencias = []
    por_codigo = {}
    for conta in contas:
        if conta.codigo in por_codigo:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "COD_CTA",
                    NIVEL_ERRO,
                    f"código '{conta.codigo}' aparece mais de uma vez no plano exportado "
                    "(REGRA_COD_CTA_DUPLICADO, p. 119).",
                )
            )
        por_codigo.setdefault(conta.codigo, conta)

    niveis = {}

    def nivel_de(codigo, cadeia):
        """Nível pela cadeia de conta superior (p. 119). None se há erro."""
        if codigo in niveis:
            return niveis[codigo]
        conta = por_codigo[codigo]
        if conta.codigo_pai is None:
            niveis[codigo] = 1
            return 1
        if conta.codigo_pai in cadeia:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "COD_CTA_SUP",
                    NIVEL_ERRO,
                    f"a hierarquia da conta {codigo} volta sobre si mesma (ciclo).",
                )
            )
            return None
        if conta.codigo_pai not in por_codigo:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "COD_CTA_SUP",
                    NIVEL_ERRO,
                    f"a conta superior '{conta.codigo_pai}' não está no plano exportado.",
                )
            )
            return None
        nivel_pai = nivel_de(conta.codigo_pai, cadeia | {codigo})
        if nivel_pai is None:
            return None
        niveis[codigo] = nivel_pai + 1
        return niveis[codigo]

    for conta in contas:
        if conta.codigo not in niveis:
            nivel_de(conta.codigo, frozenset({conta.codigo}))

    linhas = []
    for conta in contas:
        antes = len(ocorrencias)
        _campo_de_texto_recusavel(conta.codigo, "COD_CTA", conta.linha, ocorrencias)
        _campo_de_texto_recusavel(conta.nome, "CTA", conta.linha, ocorrencias)
        if conta.codigo_pai is not None:
            _campo_de_texto_recusavel(conta.codigo_pai, "COD_CTA_SUP", conta.linha, ocorrencias)
            pai = por_codigo.get(conta.codigo_pai)
            if pai is not None and pai.analitica:
                ocorrencias.append(
                    Ocorrencia(
                        conta.linha,
                        "COD_CTA_SUP",
                        NIVEL_ERRO,
                        f"a conta superior {pai.codigo} é analítica no cadastro, e a ECD "
                        "exige conta superior sintética (REGRA_CONTA_NIVEL_SUPERIOR_NAO_"
                        "SINTETICA, p. 120). Corrija o cadastro antes de exportar.",
                    )
                )
        if conta.tipo is None:
            ocorrencias.append(
                Ocorrencia(
                    conta.linha,
                    "COD_NAT",
                    NIVEL_ERRO,
                    f"a conta {conta.codigo} não tem tipo, e o código de natureza (p. 119) "
                    "não pode ser escrito sem ele.",
                )
            )
        if conta.referencial is not None:
            if not conta.analitica:
                ocorrencias.append(
                    Ocorrencia(
                        conta.linha,
                        "COD_CTA_REF",
                        NIVEL_ERRO,
                        f"a conta {conta.codigo} é sintética e não pode ter I051 (p. 124).",
                    )
                )
            _campo_de_texto_recusavel(conta.referencial, "COD_CTA_REF", conta.linha, ocorrencias)
        # Conta com erro (ou sem nível calculável) não gera linha: o raise abaixo
        # reporta tudo de uma vez, e nenhuma linha parcial sai.
        if len(ocorrencias) != antes or conta.tipo is None or conta.codigo not in niveis:
            continue

        cod_nat = COD_NAT_DO_TIPO[TipoConta(conta.tipo)]
        indicador = "A" if conta.analitica else "S"
        superior = conta.codigo_pai or ""
        linhas.append(
            f"|I050|{dt_alt}|{cod_nat}|{indicador}|{niveis[conta.codigo]}|"
            f"{conta.codigo}|{superior}|{conta.nome}|"
        )
        if conta.referencial is not None:
            # I051 com COD_CCUS vazio (p. 123; exemplo na p. 124).
            linhas.append(f"|I051||{conta.referencial}|")

    if ocorrencias:
        raise IntercambioRecusado(
            "O plano não cabe no leiaute da ECD: "
            + "; ".join(f"linha {o.linha}, {o.campo}: {o.mensagem}" for o in ocorrencias),
            ocorrencias,
        )
    if not linhas:
        return b""
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")
