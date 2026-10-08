"""DL-077, fatia 1: correção única da auditoria (rodada 1), parte do EXCEL (A4).

Cobre, com expectativas escritas à mão:
- T4 (A4): planilha que estoura células, colunas ou partes é recusada EM MENOS DE 2 s. A
  auditoria mediu 96 s e 60 s para essas entradas. A recusa é nomeada.
- Limites por parte descompactada: planilha até 64 MB, parte de apoio (sharedStrings) até 16 MB.
- XXE e entidade em `.xlsx` são recusados; cabeçalho ZIP forjado é recusado.
- Conteúdo além da `dimension` com valor é ERRO (o docstring prometia; o openpyxl descartava).
- Linha com células finais omitidas é lida como vazia nelas, e não como "a linha tem 5 campos".

Planilhas e pacotes hostis montados BYTE A BYTE aqui, a partir de um .xlsx válido de
openpyxl. Dados sintéticos.
"""

import io
import struct
import time
import zipfile

import pytest

from apps.contabilidade.intercambio import formatos
from apps.contabilidade.intercambio.canonico import NIVEL_ERRO, IntercambioRecusado
from apps.contabilidade.intercambio.formatos import excel
from apps.contabilidade.intercambio.formatos.excel import ler
from apps.contabilidade.intercambio.formatos.proprio import CABECALHO
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais

CAB = list(CABECALHO)
LIMITE_DE_TEMPO_S = 2.0  # T4: a recusa tem de sair em menos de 2 s


def _base():
    """Um .xlsx válido de openpyxl com a aba `plano` e o cabeçalho do modelo."""
    from openpyxl import Workbook

    pasta = Workbook()
    aba = pasta.active
    aba.title = "plano"
    aba.append(CAB)
    aba.append(["1", "Ativo", "", "N", "ativo", "devedora"])
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _com_partes(conteudo, trocar):
    """Copia o pacote trocando partes pelos bytes dados."""
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for parte in origem.infolist():
            dados = trocar.get(parte.filename, origem.read(parte.filename))
            destino.writestr(parte.filename, dados)
    return saida.getvalue()


def _com_tabela_de_textos(conteudo, xml):
    """Acrescenta `xl/sharedStrings.xml` e a relação que a aponta (o openpyxl só lê o que está
    no relacionamento do workbook, e o modelo deste ambiente não grava a tabela)."""
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for parte in origem.infolist():
            dados = origem.read(parte.filename)
            if parte.filename == "xl/_rels/workbook.xml.rels":
                dados = dados.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdTextos" Type="http://schemas.openxmlformats.org/'
                    b'officeDocument/2006/relationships/sharedStrings" '
                    b'Target="sharedStrings.xml"/></Relationships>',
                )
            if parte.filename == "[Content_Types].xml":
                dados = dados.replace(
                    b"</Types>",
                    b'<Override PartName="/xl/sharedStrings.xml" ContentType="application/'
                    b'vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
                    b"</Types>",
                )
            destino.writestr(parte.filename, dados)
        destino.writestr("xl/sharedStrings.xml", xml)
    return saida.getvalue()


def _folha(corpo):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{corpo}</sheetData></worksheet>"
    ).encode("utf-8")


def _celula_texto(referencia, texto):
    return f'<c r="{referencia}" t="inlineStr"><is><t>{texto}</t></is></c>'


def _erros(resultado):
    return [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]


# -----------------------------------------------------------------------------
# T4 (A4): orçamento de células e colunas, contado durante a leitura
# -----------------------------------------------------------------------------


def test_linha_com_mais_de_50_celulas_e_recusada_no_primeiro_excesso_em_menos_de_2s():
    """O ataque da auditoria: 16 mil `<c/>` numa linha. Recusa no 51º elemento."""
    linha = '<row r="2">' + "<c/>" * 16384 + "</row>"
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(linha)})

    inicio = time.perf_counter()
    with pytest.raises(IntercambioRecusado, match="mais de 50 células") as excinfo:
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert "linha 2" in excinfo.value.mensagem
    assert decorrido < LIMITE_DE_TEMPO_S


def test_ataque_de_1001_linhas_de_16_mil_celulas_nao_passa_do_limite_de_50_colunas():
    """A forma do ataque da auditoria (1.001 linhas de 16 mil `<c/>`) é barrada pelo teto
    de colunas por linha. Usa 200 linhas para a parte caber no teto de 16 MB (R3c): a regra
    que dispara é a de colunas, e não a de tamanho."""
    linha = "<row>" + "<c/>" * 16384 + "</row>"
    corpo = "".join(linha for _ in range(200))
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(corpo)})

    inicio = time.perf_counter()
    with pytest.raises(IntercambioRecusado, match="mais de 50 células"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_S


def test_orcamento_de_celulas_lidas_recusa_com_nome_do_limite_em_menos_de_2s():
    """12 mil linhas de 50 células (600 mil no total) estouram o orçamento de 60 mil. Cada
    linha respeita o teto de colunas: o que recusa é o TOTAL de células lidas."""
    linha = "<row>" + "<c/>" * 50 + "</row>"
    corpo = "".join(linha for _ in range(12_000))
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(corpo)})
    assert excel.MAXIMO_DE_CELULAS_LIDAS == 60_000

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="células"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_S


def test_sharedstrings_acima_de_16_mb_e_recusada_antes_de_ser_lida_em_menos_de_2s():
    """sharedStrings de 40 MB descompactados (o ataque de 138 MB da auditoria, em escala de
    teste). A recusa acontece na medição das partes, antes do openpyxl montar a tabela."""
    entrada = b"<si><t>x</t></si>"
    tabela = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        + entrada * (40 * 1024 * 1024 // len(entrada))
        + b"</sst>"
    )
    conteudo = _com_tabela_de_textos(_base(), tabela)

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="xl/sharedStrings.xml"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_S


def test_limite_de_planilha_por_parte_e_16_mb_e_de_apoio_4_mb(monkeypatch):
    """A aba não pode passar de 16 MB descompactados, e as partes de apoio de 4 MB (R3c).
    O limite é por PARTE, não só o total."""
    assert excel.TAMANHO_MAXIMO_PLANILHA_BYTES == 16 * 1024 * 1024
    assert excel.TAMANHO_MAXIMO_PARTE_DE_APOIO_BYTES == 4 * 1024 * 1024
    assert excel._limite_da_parte("xl/worksheets/sheet1.xml") == 16 * 1024 * 1024
    assert excel._limite_da_parte("xl/sharedStrings.xml") == 4 * 1024 * 1024


# -----------------------------------------------------------------------------
# Dimensão declarada, linhas curtas
# -----------------------------------------------------------------------------


def test_coluna_alem_da_dimension_com_conteudo_e_erro_na_linha_certa():
    """A `dimension` diz A1:F2, mas a linha 2 tem conteúdo na coluna G. Antes, o openpyxl
    descartava a G em silêncio. Agora é erro com linha e coluna."""
    corpo = (
        '<row r="1">'
        + "".join(_celula_texto(f"{c}1", t) for c, t in zip("ABCDEF", CAB, strict=True))
        + "</row>"
        '<row r="2">'
        + "".join(
            _celula_texto(f"{c}2", t)
            for c, t in zip(
                "ABCDEFG", ["1", "Ativo", "", "N", "ativo", "devedora", "sobra"], strict=True
            )
        )
        + "</row>"
    )
    folha = _folha(corpo).replace(b"<sheetData>", b'<dimension ref="A1:F2"/><sheetData>')
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": folha})

    resultado = ler(conteudo)

    assert resultado.contas == []
    assert any(o.linha == 2 and o.campo == "coluna 7" for o in _erros(resultado))


def test_linha_com_celulas_finais_omitidas_e_lida_como_vazia_e_nao_como_erro():
    """Célula final vazia e sem estilo pode não estar no XML. A linha tem 5 células: a sexta
    (natureza) é vazia, e a conta é lida com natureza presumida, não recusada."""
    corpo = (
        '<row r="1">'
        + "".join(_celula_texto(f"{c}1", t) for c, t in zip("ABCDEF", CAB, strict=True))
        + "</row>"
        '<row r="2">'
        + "".join(
            _celula_texto(f"{c}2", t)
            for c, t in zip("ABCDE", ["1", "Ativo", "", "N", "ativo"], strict=True)
        )
        + "</row>"
    )
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(corpo)})

    resultado = ler(conteudo)

    assert not _erros(resultado), resultado.ocorrencias
    assert [c.codigo for c in resultado.contas] == ["1"]
    assert resultado.contas[0].natureza is None


# -----------------------------------------------------------------------------
# XXE e cabeçalho ZIP forjado
# -----------------------------------------------------------------------------


def test_entidade_externa_na_planilha_e_recusada_com_erro_de_xml():
    """XXE: uma entidade que aponta para um arquivo local. Recusado, nunca resolvido."""
    xxe = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE worksheet [<!ENTITY e SYSTEM "file:///etc/hostname">]>'
        b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b'<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>&e;</t></is></c></row>'
        b"</sheetData></worksheet>"
    )
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": xxe})

    with pytest.raises(IntercambioRecusado):
        ler(conteudo)


def test_entidade_em_sharedstrings_e_recusada():
    """A mesma recusa vale para a tabela de textos compartilhados (o openpyxl a lê à parte)."""
    tabela = (
        b'<?xml version="1.0"?>'
        b'<!DOCTYPE sst [<!ENTITY e "boom">]>'
        b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b"<si><t>&e;&e;&e;</t></si></sst>"
    )
    conteudo = _com_tabela_de_textos(_base(), tabela)

    with pytest.raises(IntercambioRecusado):
        ler(conteudo)


def _forjar_tamanho_declarado(pacote, nome, novo_tamanho):
    """Troca o tamanho DESCOMPACTADO declarado de `nome` nos dois cabeçalhos do ZIP.

    Deslocamentos da especificação ZIP: no cabeçalho central, o tamanho fica em 24, o nome em
    46 (e o tamanho do nome em 28) e o deslocamento do cabeçalho local em 42. No cabeçalho
    local, o tamanho fica em 22.
    """
    dados = bytearray(pacote)
    indice = dados.find(b"PK\x01\x02")
    while indice >= 0:
        tamanho_do_nome = struct.unpack_from("<H", dados, indice + 28)[0]
        if bytes(dados[indice + 46 : indice + 46 + tamanho_do_nome]) == nome:
            struct.pack_into("<I", dados, indice + 24, novo_tamanho)
            deslocamento_local = struct.unpack_from("<I", dados, indice + 42)[0]
            struct.pack_into("<I", dados, deslocamento_local + 22, novo_tamanho)
        indice = dados.find(b"PK\x01\x02", indice + 4)
    return bytes(dados)


def test_cabecalho_zip_forjado_com_tamanho_menor_e_recusado_como_danificado():
    """O cabeçalho do ZIP declara 100 bytes para uma aba de ~1 MB. O CRC não confere, e o
    pacote é recusado como danificado, sem seguir a leitura além do declarado."""
    aba = _folha("<!-- " + "x" * (1024 * 1024) + " -->")
    base = _com_partes(_base(), {"xl/worksheets/sheet1.xml": aba})
    forjado = _forjar_tamanho_declarado(base, b"xl/worksheets/sheet1.xml", 100)

    with pytest.raises(IntercambioRecusado, match="danificado"):
        ler(forjado)


def test_formatos_registrados_nao_mudam_com_os_limites():
    """Sanidade: o formato `excel` continua só leitor, e a lista de formatos não mudou."""
    assert set(formatos.LEITORES) == {"ecd", "proprio", "referencia", "excel"}
