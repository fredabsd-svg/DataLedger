"""Plano de contas em planilha Excel `.xlsx` (DL-077, fatia 1, frente B, critério 6).

As colunas são as MESMAS do formato próprio (`codigo;nome;codigo_pai;analitica;
tipo;natureza`, cabeçalho na linha 1 da aba `plano`). Quem decide a regra de cada
campo é `formatos/proprio.py` (`_ler_linha`); este módulo cuida só do que é próprio
da planilha: o pacote, a aba, a célula e a fórmula.

RECUSAS (critério 6 da DL-077). Todas são `IntercambioRecusado` (400), exceto o
tamanho, que é `ArquivoGrandeDemais` (413):
- `.xls` (formato binário antigo), CSV renomeado, pacote ZIP danificado ou protegido;
- macros: pasta de trabalho `.xlsm`, ou qualquer parte `vbaProject.bin`;
- pacote que não é pasta de trabalho `.xlsx` (ex.: modelo `.xltx`);
- descompactado acima de `TAMANHO_MAXIMO_DESCOMPACTADO_BYTES` (proteção contra
  bomba de compressão: o tamanho é MEDIDO lendo as partes, não lido do cabeçalho);
- mais de `MAXIMO_DE_LINHAS` linhas;
- planilha acima de 64 MB descompactados, ou outra parte acima de 16 MB (A4: sharedStrings
  e tabela de estilos têm teto menor);
- mais de 500 mil células lidas, ou mais de 50 células numa mesma linha, contadas DURANTE a
  leitura do XML e ANTES de o openpyxl abrir a aba (ele lê a aba inteira ao abrir);
- DTD ou entidade no XML (defusedxml); aba `plano` fora de `xl/worksheets/`.
- aba `plano` ausente.

ERROS DE CÉLULA (nível erro, com a linha da planilha):
- fórmula sem valor calculado: sem o valor salvo, o importador não sabe o que ela
  daria, e não calcula;
- célula com erro de fórmula (ex.: `#DIV/0!`);
- valor que não é texto nas colunas `codigo`, `nome`, `codigo_pai`: número, data ou
  booleano. Em particular, o Excel transforma `1.1` em `1,1`; o importador NÃO
  converte, recusa a célula e pede que a coluna seja formatada como Texto;
- conteúdo além da sexta coluna.

AVISO: abas que não são `plano` são ignoradas e listadas.

Linhas totalmente vazias são ignoradas. `linha` da ocorrência é o número da linha
na planilha. O modelo para baixar (`gerar_modelo`) já vem com a coluna de código
formatada como Texto.
"""

import io
import zipfile
import zlib
from datetime import date, datetime

from defusedxml import ElementTree
from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.datavalidation import DataValidation

from apps.contabilidade.intercambio.canonico import (
    NIVEL_AVISO,
    NIVEL_ERRO,
    IntercambioRecusado,
    Ocorrencia,
    ResultadoLeitura,
)
from apps.contabilidade.intercambio.formatos.proprio import CABECALHO, _ler_linha
from apps.contabilidade.models import NaturezaConta, TipoConta

FORMATO = "excel"

NOME_DA_ABA = "plano"
ABA_DE_INSTRUCOES = "instrucoes"

# Limite do DESCOMPACTADO. Um plano de 200 mil linhas em XML cabe folgado; o
# limite existe para recusar um pacote que se expande além disso (bomba de
# compressão), não para restringir o uso normal.
TAMANHO_MAXIMO_DESCOMPACTADO_BYTES = 200 * 1024 * 1024
MAXIMO_DE_ENTRADAS_NO_PACOTE = 1_000
_TAMANHO_DO_BLOCO = 64 * 1024

# Limites POR PARTE descompactada (A4 da auditoria da DL-077). A planilha de um plano de
# 5.000 contas tem poucos MB; um XML de 64 MB já é absurdo. Partes que não são planilha
# (sharedStrings, estilos, tema) têm teto menor: a tabela de textos compartilhados é a que
# mais cresce num arquivo hostil, e o limite vale para ela mesmo que ela seja renomeada.
TAMANHO_MAXIMO_PLANILHA_BYTES = 64 * 1024 * 1024
TAMANHO_MAXIMO_PARTE_DE_APOIO_BYTES = 16 * 1024 * 1024
_PREFIXO_DAS_PLANILHAS = "xl/worksheets/"

# Orçamento de células e colunas, contado DURANTE a leitura do XML da aba `plano`, antes de
# o openpyxl montar a planilha. O orçamento de células é o que limita o custo total: o openpyxl
# leva ~7 s por 2 milhões de células, nos dois passes. O de colunas por linha recusa a linha
# com 16 mil `<c/>` no primeiro elemento que passa do limite, sem ler o resto.
MAXIMO_DE_CELULAS_LIDAS = 500_000
MAXIMO_DE_COLUNAS_POR_LINHA = 50

_ASSINATURA_ZIP = b"PK\x03\x04"
# Cabeçalho do formato binário antigo (.xls, OLE2). Recusado com mensagem própria.
_ASSINATURA_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

_TIPO_PASTA_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
_TIPO_PASTA_XLSM = "application/vnd.ms-excel.sheet.macroEnabled.main+xml"
_NS_CONTENT_TYPES = "{http://schemas.openxmlformats.org/package/2006/content-types}"

# Colunas que são código: o Excel as transforma em número se não estiverem como Texto.
COLUNAS_DE_CODIGO = ("codigo", "codigo_pai")
_TIPOS_DE_CELULA_DE_FORMULA = "f"
_TIPO_DE_CELULA_DE_ERRO = "e"


def _verificar_pacote(conteudo):
    """Recusa o que não é `.xlsx` sem macro e dentro do limite. Não abre a planilha."""
    if conteudo.startswith(_ASSINATURA_OLE):
        raise IntercambioRecusado(
            "arquivo .xls (formato binário antigo) não é aceito. Salve de novo no Excel como "
            "'Pasta de Trabalho do Excel (.xlsx)'."
        )
    if not conteudo.startswith(_ASSINATURA_ZIP):
        raise IntercambioRecusado(
            "o arquivo não é uma planilha .xlsx. Arquivo CSV renomeado não é aceito: baixe o "
            "modelo e preencha a aba 'plano'."
        )
    try:
        pacote = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as exc:
        raise IntercambioRecusado("o .xlsx está danificado: não é possível abri-lo.") from exc

    with pacote:
        partes = pacote.infolist()
        if len(partes) > MAXIMO_DE_ENTRADAS_NO_PACOTE:
            raise IntercambioRecusado(
                f"o .xlsx tem {len(partes)} partes internas; o máximo é "
                f"{MAXIMO_DE_ENTRADAS_NO_PACOTE}. Não é uma planilha de plano de contas."
            )
        nomes = {parte.filename for parte in partes}
        # Macro é recusada pelo NOME da parte e pelo tipo da pasta, porque um .xlsm
        # renomeado para .xlsx ainda carrega a parte de VBA.
        if any(nome.lower().endswith("vbaproject.bin") for nome in nomes):
            raise IntercambioRecusado(
                "a planilha contém macros (VBA). Macros não são aceitas: salve como .xlsx sem "
                "macros."
            )
        if "[Content_Types].xml" not in nomes:
            raise IntercambioRecusado(
                "o .xlsx não tem [Content_Types].xml: não é uma pasta de trabalho do Excel."
            )
        tipo = _tipo_da_pasta_de_trabalho(pacote)
        if tipo == _TIPO_PASTA_XLSM:
            raise IntercambioRecusado(
                "a planilha é .xlsm (com macros). Não é aceita: salve como .xlsx sem macros."
            )
        if tipo != _TIPO_PASTA_XLSX:
            raise IntercambioRecusado(
                "o arquivo não é uma pasta de trabalho .xlsx comum (modelo ou outro tipo de "
                "documento do Office). Salve como 'Pasta de Trabalho do Excel (.xlsx)'."
            )
        _medir_descompactado(pacote, partes)


def _tipo_da_pasta_de_trabalho(pacote):
    """Tipo de conteúdo declarado para `xl/workbook.xml` em [Content_Types].xml."""
    try:
        with pacote.open("[Content_Types].xml") as parte:
            raiz = ElementTree.fromstring(parte.read())
    except Exception as exc:  # XML malformado ou com DTD: recusa, não ignora.
        raise IntercambioRecusado(
            f"o [Content_Types].xml do .xlsx não pôde ser lido ({type(exc).__name__})."
        ) from exc
    for elemento in raiz.iter():
        if elemento.tag == f"{_NS_CONTENT_TYPES}Override" and (
            elemento.get("PartName") == "/xl/workbook.xml"
        ):
            return elemento.get("ContentType")
    raise IntercambioRecusado("o .xlsx não declara a pasta de trabalho (xl/workbook.xml).")


def _limite_da_parte(nome):
    """Teto de bytes descompactados de UMA parte. Planilha tem o teto maior; o resto, o menor."""
    if nome.startswith(_PREFIXO_DAS_PLANILHAS):
        return TAMANHO_MAXIMO_PLANILHA_BYTES
    return TAMANHO_MAXIMO_PARTE_DE_APOIO_BYTES


def _caminho_da_aba(formulas):
    """Caminho da parte XML da aba `plano`. Recusa se ela não está em `xl/worksheets/`.

    O limite por planilha vale pelo prefixo do caminho. Uma aba apontada para fora dele
    escaparia do orçamento de células, então a recusa é nomeada e não a leitura.
    """
    caminho = getattr(formulas[NOME_DA_ABA], "_worksheet_path", None)
    if not isinstance(caminho, str) or not caminho.startswith(_PREFIXO_DAS_PLANILHAS):
        raise IntercambioRecusado(
            "a aba 'plano' não está em xl/worksheets/: estrutura de .xlsx não reconhecida. "
            "Salve de novo no Excel como 'Pasta de Trabalho do Excel (.xlsx)'."
        )
    return caminho


def _conferir_orcamento_das_planilhas(conteudo):
    """Conta células e linhas de TODAS as partes de planilha, DURANTE a leitura do XML.

    Roda ANTES de o openpyxl abrir o pacote: o `parse_dimensions` dele usa `iterparse` com
    evento de fim, e por isso lê a aba inteira antes de chegar ao `sheetData`. Medido: um
    XML de 59 MB levava 36 s só para ser aberto. Com esta varredura antes, a recusa sai no
    primeiro excesso, sem o openpyxl tocar na aba.

    Stream SAX com defusedxml (DTD e entidades proibidos). O orçamento de células é
    acumulado entre as partes; o de linhas vale por parte. A recusa é `IntercambioRecusado`
    (formato) ou `ArquivoGrandeDemais` (tamanho), conforme o motivo.
    """
    from xml.sax.handler import ContentHandler, feature_namespaces

    from defusedxml import sax

    from apps.contabilidade.intercambio.leitura import MAXIMO_DE_LINHAS, ArquivoGrandeDemais

    class _Orcamento(ContentHandler):
        def __init__(self):
            super().__init__()
            self.celulas = 0
            self.linhas = 0
            self.celulas_na_linha = 0
            self.linha_atual = 0

        def startElementNS(self, nome, _qname, attrs):  # noqa: N802 (nome da API do SAX)
            _uri, local = nome
            if local == "row":
                self.linhas += 1
                self.celulas_na_linha = 0
                referencia = attrs.get((None, "r"))
                if referencia and referencia.isdigit():
                    self.linha_atual = int(referencia)
                else:
                    self.linha_atual = self.linhas
                if self.linhas > MAXIMO_DE_LINHAS or self.linha_atual > MAXIMO_DE_LINHAS:
                    raise ArquivoGrandeDemais(
                        f"a planilha passa de {MAXIMO_DE_LINHAS} linhas. O limite é esse."
                    )
            elif local == "c":
                self.celulas += 1
                self.celulas_na_linha += 1
                if self.celulas_na_linha > MAXIMO_DE_COLUNAS_POR_LINHA:
                    raise IntercambioRecusado(
                        f"a linha {self.linha_atual} da planilha tem mais de "
                        f"{MAXIMO_DE_COLUNAS_POR_LINHA} células. O plano tem seis colunas: "
                        "não é uma planilha de plano de contas."
                    )
                if self.celulas > MAXIMO_DE_CELULAS_LIDAS:
                    raise ArquivoGrandeDemais(
                        f"a planilha tem mais de {MAXIMO_DE_CELULAS_LIDAS} células. O limite é "
                        "esse, e a planilha é grande demais para um plano de contas."
                    )

    manipulador = _Orcamento()
    with zipfile.ZipFile(io.BytesIO(conteudo)) as pacote:
        caminhos = [
            parte.filename
            for parte in pacote.infolist()
            if parte.filename.startswith(_PREFIXO_DAS_PLANILHAS)
        ]
        for caminho in caminhos:
            manipulador.linhas = 0
            leitor = sax.make_parser()
            leitor.setFeature(feature_namespaces, True)
            leitor.setContentHandler(manipulador)
            try:
                with pacote.open(caminho) as parte:
                    leitor.parse(parte)
            except (IntercambioRecusado, ArquivoGrandeDemais):
                raise
            except Exception as exc:  # XML malformado, DTD ou entidade: recusa, nunca ignora.
                raise IntercambioRecusado(
                    f"a planilha tem XML inválido ou com DTD/entidades ({type(exc).__name__})."
                ) from exc


def _medir_descompactado(pacote, partes):
    """Soma o tamanho REAL descompactado de cada parte, sem confiar no cabeçalho.

    O cabeçalho do ZIP declara `file_size`, mas quem o escreve é o arquivo, e um
    pacote hostil pode declarar pouco e expandir muito. Por isso a parte é lida em
    blocos e contada.
    """
    from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais

    total = 0
    for parte in partes:
        limite_da_parte = _limite_da_parte(parte.filename)
        lido = 0
        try:
            with pacote.open(parte) as conteudo:
                while bloco := conteudo.read(_TAMANHO_DO_BLOCO):
                    total += len(bloco)
                    lido += len(bloco)
                    if lido > limite_da_parte:
                        raise ArquivoGrandeDemais(
                            f"a parte '{parte.filename}' da planilha, descompactada, passa de "
                            f"{limite_da_parte // (1024 * 1024)} MB. Não é aceita."
                        )
                    if total > TAMANHO_MAXIMO_DESCOMPACTADO_BYTES:
                        raise ArquivoGrandeDemais(
                            "a planilha, descompactada, passa de "
                            f"{TAMANHO_MAXIMO_DESCOMPACTADO_BYTES // (1024 * 1024)} MB. "
                            "Não é aceita."
                        )
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error) as exc:
            raise IntercambioRecusado(
                "o .xlsx está danificado ou protegido por senha: não é possível lê-lo."
            ) from exc


def _abrir(conteudo):
    """Abre a planilha DUAS vezes: uma com as fórmulas, outra com os valores salvos.

    O modo `data_only` devolve `None` tanto para célula vazia quanto para fórmula
    sem valor calculado. Só a visão com fórmulas distingue as duas coisas.
    """
    try:
        formulas = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=False)
        valores = load_workbook(io.BytesIO(conteudo), read_only=True, data_only=True)
    except Exception as exc:  # parser de arquivo hostil: recusa, nunca ignora.
        raise IntercambioRecusado(
            f"não foi possível abrir a planilha ({type(exc).__name__}). Confira se é um .xlsx."
        ) from exc
    return formulas, valores


def _texto(valor):
    """Valor de célula como texto para o cabeçalho ('' se vazio)."""
    return "" if valor is None else str(valor).strip()


def _ler_planilha(formulas, valores, resultado):
    from apps.contabilidade.intercambio.leitura import MAXIMO_DE_LINHAS, ArquivoGrandeDemais

    ocorrencias = resultado.ocorrencias
    if NOME_DA_ABA not in formulas.sheetnames:
        ocorrencias.append(
            Ocorrencia(
                0,
                "aba",
                NIVEL_ERRO,
                f"a planilha não tem a aba '{NOME_DA_ABA}'. Baixe o modelo e preencha essa aba.",
            )
        )
        return

    for nome in formulas.sheetnames:
        if nome != NOME_DA_ABA:
            ocorrencias.append(
                Ocorrencia(
                    0,
                    "aba",
                    NIVEL_AVISO,
                    f"aba '{nome}' ignorada: só a aba '{NOME_DA_ABA}' é lida.",
                )
            )

    # As duas visões têm as mesmas linhas, na mesma ordem: o `enumerate` dá o número
    # da linha da planilha (a leitura em modo somente leitura emite toda linha, até
    # as vazias, então o índice não se desloca).
    linhas_com_formula = formulas[NOME_DA_ABA].iter_rows()
    linhas_com_valor = valores[NOME_DA_ABA].iter_rows(values_only=True)
    vistos = {}
    # strict=True: as duas visões têm o mesmo número de linhas. Divergência é bug, e
    # não pode alinhar células de linhas diferentes em silêncio.
    pares = zip(linhas_com_formula, linhas_com_valor, strict=True)
    for numero, (celulas, valor_salvo) in enumerate(pares, 1):
        if numero > MAXIMO_DE_LINHAS:
            raise ArquivoGrandeDemais(
                f"a planilha passa de {MAXIMO_DE_LINHAS} linhas. O limite é esse."
            )
        celulas = list(celulas)
        valor_salvo = list(valor_salvo)

        if numero == 1:
            if not _conferir_cabecalho(valor_salvo, ocorrencias):
                return
            continue

        campos = _campos_da_linha(numero, celulas, valor_salvo, ocorrencias)
        if campos is None:
            continue  # linha vazia, ou com erro de célula já registrado
        ocorrencias.extend(_ler_linha(numero, campos, vistos, resultado))


def _conferir_cabecalho(valor_salvo, ocorrencias):
    """A linha 1 tem de ser o cabeçalho do formato próprio, exatamente, nessa ordem.

    Usa os valores salvos: cabeçalho é texto, e não precisa da visão de fórmulas.
    """
    valores = [_texto(valor) for valor in valor_salvo]
    primeiras = tuple(valores[: len(CABECALHO)])
    alem = [v for v in valores[len(CABECALHO) :] if v]
    if primeiras != CABECALHO or alem:
        ocorrencias.append(
            Ocorrencia(
                1,
                "cabecalho",
                NIVEL_ERRO,
                "a linha 1 deve ser exatamente "
                f"{';'.join(CABECALHO)}, nesta ordem, e sem colunas a mais. "
                "Use o modelo para baixar.",
            )
        )
        return False
    return True


def _campos_da_linha(numero, celulas, valor_salvo, ocorrencias):
    """Os seis campos de texto da linha, ou None se a linha é vazia ou tem erro.

    Erro de célula vai para `ocorrencias` com a linha e a coluna. Quem chama não
    entrega linha com erro ao formato próprio, para o erro aparecer uma vez só.
    """
    erros = []
    colunas = []
    for indice in range(max(len(celulas), len(valor_salvo))):
        celula = celulas[indice] if indice < len(celulas) else None
        valor = valor_salvo[indice] if indice < len(valor_salvo) else None
        nome = CABECALHO[indice] if indice < len(CABECALHO) else f"coluna {indice + 1}"
        tipo = getattr(celula, "data_type", "n") if celula is not None else "n"

        if tipo == _TIPO_DE_CELULA_DE_ERRO:
            erros.append(
                Ocorrencia(numero, nome, NIVEL_ERRO, "célula com erro de fórmula (ex.: #DIV/0!).")
            )
            colunas.append(None)
            continue
        if tipo == _TIPOS_DE_CELULA_DE_FORMULA and valor is None:
            erros.append(
                Ocorrencia(
                    numero,
                    nome,
                    NIVEL_ERRO,
                    "fórmula sem valor calculado. Sem o valor salvo, o importador não calcula. "
                    "No Excel, copie e cole como valores e salve de novo.",
                )
            )
            colunas.append(None)
            continue

        if indice >= len(CABECALHO):
            if valor not in (None, ""):
                erros.append(
                    Ocorrencia(
                        numero,
                        nome,
                        NIVEL_ERRO,
                        "a coluna está além das seis do modelo e tem conteúdo. Remova-a.",
                    )
                )
            continue

        if valor is None:
            colunas.append("")
        elif isinstance(valor, str):
            colunas.append(valor)
        else:
            colunas.append(None)
            if nome in COLUNAS_DE_CODIGO:
                # Não converte: o valor pode ter perdido zeros ou casas (1.10 -> 1.1).
                # Data também é número no Excel; a mensagem diz qual dos dois foi gravado.
                natureza = "data" if isinstance(valor, (datetime, date)) else "número"
                mensagem = (
                    f"o Excel gravou o código como {natureza} ({valor}). Formate a coluna "
                    f"'{nome}' como Texto e digite de novo: o Excel transforma 1.1 em 1,1, e "
                    "o importador não converte."
                )
            else:
                mensagem = f"o valor não é texto ({type(valor).__name__}). Use texto."
            erros.append(Ocorrencia(numero, nome, NIVEL_ERRO, mensagem))

    ocorrencias.extend(erros)
    if erros:
        return None
    # Célula final vazia e sem estilo pode não estar no XML: a linha vem curta. O plano tem
    # seis colunas, e a falta delas é vazio, não erro.
    campos = colunas[: len(CABECALHO)]
    campos += [""] * (len(CABECALHO) - len(campos))
    if not any(campos):
        return None
    return campos


def ler(conteudo: bytes) -> ResultadoLeitura:
    """Lê o plano de uma planilha `.xlsx`. Recusa o que não é `.xlsx` seguro.

    Recusa de pacote, macro, tamanho e aba levanta exceção (o arquivo não pode seguir).
    Conteúdo de célula vira `Ocorrencia` com linha e campo, como nos outros formatos.
    """
    _verificar_pacote(conteudo)
    resultado = ResultadoLeitura(formato=FORMATO, codificacao="")
    # Orçamento ANTES de o openpyxl abrir o pacote (ver `_conferir_orcamento_das_planilhas`).
    _conferir_orcamento_das_planilhas(conteudo)
    formulas, valores = _abrir(conteudo)
    try:
        if NOME_DA_ABA in formulas.sheetnames:
            # A aba `plano` precisa estar em xl/worksheets/, onde o orçamento foi medido.
            _caminho_da_aba(formulas)
            # A dimensão declarada no XML só serve para o openpyxl montar a aba. Ela descartava,
            # em silêncio, conteúdo além dela (a nota A4). Sem ela, cada célula é lida.
            formulas[NOME_DA_ABA].reset_dimensions()
            valores[NOME_DA_ABA].reset_dimensions()
        _ler_planilha(formulas, valores, resultado)
    finally:
        formulas.close()
        valores.close()
    resultado.ocorrencias.sort(key=lambda o: (o.linha, o.campo))
    return resultado


# -----------------------------------------------------------------------------
# Modelo para baixar
# -----------------------------------------------------------------------------

LINHAS_FORMATADAS_NO_MODELO = 1000
_INSTRUCOES = (
    ("Modelo de plano de contas do DataLedger", ""),
    ("", ""),
    (
        "Como usar",
        "Preencha a aba 'plano', a partir da linha 2. A linha 1 é o cabeçalho e não deve "
        "mudar. Só a aba 'plano' é lida; as outras são ignoradas com aviso.",
    ),
    (
        "Não é a ECD",
        "Esta planilha não substitui a ECD nem a Escrituração Contábil Digital.",
    ),
    ("", ""),
    ("Coluna", "Valor aceito"),
    (
        "codigo",
        "Texto, obrigatório, até 20 caracteres, único. Formate a coluna como Texto ANTES de "
        "digitar: o Excel transforma 1.1 em 1,1, e o importador recusa número.",
    ),
    ("nome", "Texto, obrigatório, até 200 caracteres."),
    (
        "codigo_pai",
        "Texto. Vazio = conta de primeiro nível. Senão, o código de outra conta da planilha "
        "ou já cadastrada, que precisa ser sintética (analitica = N).",
    ),
    ("analitica", "S = analítica (recebe lançamento). N = sintética (agrupa outras contas)."),
    (
        "tipo",
        "Um de: " + ", ".join(valor for valor, _rotulo in TipoConta.choices) + ". Pode ficar "
        "vazio se a conta superior ou o prefixo informado na conferência define o tipo.",
    ),
    (
        "natureza",
        "Um de: " + ", ".join(valor for valor, _rotulo in NaturezaConta.choices) + ". Vazio = "
        "presumida pelo tipo, com aviso por conta para conferência.",
    ),
    ("", ""),
    (
        "Linhas totalmente vazias",
        "São ignoradas.",
    ),
    (
        "Fórmulas",
        "Só são aceitas com o valor calculado salvo no arquivo. Ao final, cole como valores.",
    ),
)


def gerar_modelo() -> bytes:
    """Modelo `.xlsx` vazio: aba `plano` com cabeçalho e aba `instrucoes`.

    Só a coluna de código (A e C, que é `codigo_pai`) vem formatada como Texto, para o
    usuário digitar `1.1` sem que o Excel o converta. A aba `plano` sai sem dado
    nenhum: não há conta de exemplo no modelo.
    """
    pasta = Workbook()
    plano = pasta.active
    plano.title = NOME_DA_ABA
    plano.append(list(CABECALHO))
    for linha in range(2, LINHAS_FORMATADAS_NO_MODELO + 1):
        for coluna in (1, 3):
            plano.cell(row=linha, column=coluna).number_format = "@"
    for coluna, largura in zip("ABCDEF", (22, 48, 22, 12, 22, 14), strict=True):
        plano.column_dimensions[coluna].width = largura

    validacoes = (
        ("D", '"S,N"'),
        ("E", '"' + ",".join(valor for valor, _rotulo in TipoConta.choices) + '"'),
        ("F", '"' + ",".join(valor for valor, _rotulo in NaturezaConta.choices) + '"'),
    )
    for coluna, lista in validacoes:
        validacao = DataValidation(type="list", formula1=lista, allow_blank=True)
        plano.add_data_validation(validacao)
        validacao.add(f"{coluna}2:{coluna}{LINHAS_FORMATADAS_NO_MODELO}")

    instrucoes = pasta.create_sheet(ABA_DE_INSTRUCOES)
    for linha, (texto_a, texto_b) in enumerate(_INSTRUCOES, start=1):
        instrucoes.cell(row=linha, column=1, value=texto_a)
        instrucoes.cell(row=linha, column=2, value=texto_b)
    instrucoes.column_dimensions["A"].width = 28
    instrucoes.column_dimensions["B"].width = 100

    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()
