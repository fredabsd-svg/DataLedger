"""DL-077, reconferência da fatia 1 (2026-10-08): leitor Excel endurecido.

Cobre os testes que a auditoria propôs na seção 11 do relatório, e as lacunas do leitor:
- T-R2: 16 formas de XML malformado na aba (o relatório fala em 14; a lista da seção 3 traz
  16 formas distintas, e todas são cobertas). Esperado: `IntercambioRecusado` com a mensagem
  "planilha com XML inválido", na leitura, pela API (400) e pela tela (400). Nunca 500.
- T-R3a: colunas esparsas (`XFD`) sem `dimension`, ou com ela forjada, recusadas em menos de 2 s.
- T-R3b: 3 milhões de `<a/>` no `sheetData` recusados em menos de 3 s.
- T-R3c: `styles.xml` com 3 milhões de `<xf/>` recusado em menos de 2 s; e a mesma contagem
  numa parte de apoio renomeada e apontada pela relação do workbook.
- T-R3d (orçamento de células): 60 mil células passam, 60.001 são recusadas.
- Fronteira de colunas: `AX` (50) passa, `AY` (51) é recusada.
- N07: aba `plano` fora de `xl/worksheets/` é recusada com mensagem nomeada.
- Legítimos: planilha de 2.000 contas lida sem erro; planilha regravada pelo LibreOffice,
  quando `soffice` está instalado (senão o teste é pulado, e isso aparece no relatório).

Dados sintéticos. Nenhum arquivo de cliente real.
"""

import io
import shutil
import subprocess
import time
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from openpyxl import Workbook

from apps.contabilidade.intercambio.canonico import NIVEL_ERRO, IntercambioRecusado
from apps.contabilidade.intercambio.formatos.excel import ler
from apps.contabilidade.intercambio.formatos.proprio import CABECALHO
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

CAB = list(CABECALHO)
SENHA = "senha-forte-123"
LIMITE_DE_TEMPO_RECUSA_S = 2.0  # T-R3a e T-R3c: a recusa tem de sair em menos de 2 s
LIMITE_DE_TEMPO_ELEMENTOS_S = 3.0  # T-R3b


# -----------------------------------------------------------------------------
# Montagem de pacotes .xlsx (sintéticos)
# -----------------------------------------------------------------------------


def _base():
    """Um .xlsx válido de openpyxl com a aba `plano`, o cabeçalho e uma conta."""
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


def _renomear_parte(conteudo, antigo, novo):
    """Renomeia uma parte do pacote e ajusta a relação do workbook e o [Content_Types].xml.

    `antigo` e `novo` são caminhos completos (ex.: `xl/styles.xml`). Na relação do workbook o
    alvo pode estar em forma absoluta (`/xl/...`) ou relativa a `xl/` (`styles.xml`): as duas
    formas são trocadas, e a troca tem de achar pelo menos uma, para não passar em silêncio.
    """
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    relativo_antigo = antigo.removeprefix("xl/")
    relativo_novo = novo.removeprefix("xl/")
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for parte in origem.infolist():
            dados = origem.read(parte.filename)
            nome = novo if parte.filename == antigo else parte.filename
            if parte.filename == "xl/_rels/workbook.xml.rels":
                trocado = dados.replace(
                    f'Target="/{antigo}"'.encode(), f'Target="/{novo}"'.encode()
                ).replace(
                    f'Target="{relativo_antigo}"'.encode(), f'Target="{relativo_novo}"'.encode()
                )
                assert trocado != dados, "a relação do workbook não aponta a parte renomeada"
                dados = trocado
            if parte.filename == "[Content_Types].xml":
                dados = dados.replace(f"/{antigo}".encode(), f"/{novo}".encode())
            destino.writestr(nome, dados)
    return saida.getvalue()


def _com_tabela_de_textos(conteudo, xml):
    """Acrescenta `xl/sharedStrings.xml` e a relação que a aponta. O `.xlsx` base deste
    ambiente não grava a tabela, e o openpyxl só lê o que a relação do workbook aponta."""
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


def _folha(corpo, *, cabeca="", cauda=""):
    """Aba `plano` com o `corpo` dentro de `sheetData`; `cabeca` vai antes e `cauda`, depois."""
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{cabeca}<sheetData>{corpo}</sheetData>{cauda}</worksheet>"
    ).encode("utf-8")


def _linha_de_cabecalho():
    return (
        '<row r="1">'
        + "".join(
            f'<c r="{coluna}1" t="inlineStr"><is><t>{texto}</t></is></c>'
            for coluna, texto in zip("ABCDEF", CAB, strict=True)
        )
        + "</row>"
    )


def _planilha_com_linha_2(linha_2, *, cabeca="", cauda=""):
    """Cabeçalho válido na linha 1 e a `linha_2` (a malformada) logo depois."""
    return _folha(_linha_de_cabecalho() + linha_2, cabeca=cabeca, cauda=cauda)


def _estilos(quantidade_de_xf):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cellXfs count="{quantidade_de_xf}">' + "<xf/>" * quantidade_de_xf + "</cellXfs>"
        "</styleSheet>"
    ).encode("utf-8")


def _erros(resultado):
    return [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]


# -----------------------------------------------------------------------------
# T-R2: XML malformado na aba
# -----------------------------------------------------------------------------

# (cabeça, linha 2, cauda). As formas são as da seção 3, R2, do relatório da auditoria.
FORMAS_MALFORMADAS = [
    pytest.param(
        "", '<row r="2"><c r="A2" t="s"><v>99999</v></c></row>', "", id="indice_de_textos_fora"
    ),
    pytest.param("", '<row r="2"><c r="A2" t="n"><v>abc</v></c></row>', "", id="numero_lixo"),
    pytest.param("", '<row r="2"><c r="A2" t="d"><v>garbage</v></c></row>', "", id="data_lixo"),
    pytest.param("", '<row r="2"><c r="A2" t="b"><v>x</v></c></row>', "", id="booleano_lixo"),
    pytest.param("", '<row r="2"><c r="A2"><v>inf</v></c></row>', "", id="numero_inf"),
    pytest.param("", '<row r="2"><c r="A2"><v>nan</v></c></row>', "", id="numero_nan"),
    pytest.param(
        "",
        '<row r="x"><c r="A2" t="inlineStr"><is><t>1</t></is></c></row>',
        "",
        id="linha_r_nao_numero",
    ),
    pytest.param(
        "",
        '<row r="2"><c r="1A" t="inlineStr"><is><t>1</t></is></c></row>',
        "",
        id="referencia_1A",
    ),
    pytest.param(
        "",
        '<row r="2"><c r="ZZZZ2" t="inlineStr"><is><t>1</t></is></c></row>',
        "",
        id="referencia_ZZZZ2",
    ),
    pytest.param("", "", "<extLst><ext>x</ext></extLst>", id="extlst_sem_uri"),
    pytest.param(
        "", "", '<mergeCells count="x"><mergeCell ref="zz"/></mergeCells>', id="merge_count_x"
    ),
    pytest.param("", "", "<hyperlinks><hyperlink/></hyperlinks>", id="hyperlink_sem_ref"),
    pytest.param(
        '<sheetViews><sheetView zoomScale="abc"/></sheetViews>',
        "",
        "",
        id="sheetviews_zoom_abc",
    ),
    pytest.param('<sheetFormatPr defaultRowHeight="abc"/>', "", "", id="sheetformatpr_altura_abc"),
    pytest.param('<cols><col min="x" max="y"/></cols>', "", "", id="cols_min_x"),
    pytest.param('<sheetPr><tabColor rgb="zz"/></sheetPr>', "", "", id="tabcolor_zz"),
]


@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_e_recusado_com_mensagem_nomeada_na_leitura(cabeca, linha_2, cauda):
    conteudo = _com_partes(
        _base(),
        {"xl/worksheets/sheet1.xml": _planilha_com_linha_2(linha_2, cabeca=cabeca, cauda=cauda)},
    )

    with pytest.raises(IntercambioRecusado, match="planilha com XML inválido"):
        ler(conteudo)


def test_erro_de_celula_numerica_informa_a_linha_da_planilha():
    """R2: o diagnóstico tem a linha quando ela é conhecida. A célula malformada está na 2."""
    conteudo = _com_partes(
        _base(),
        {
            "xl/worksheets/sheet1.xml": _planilha_com_linha_2(
                '<row r="2"><c r="A2" t="n"><v>abc</v></c></row>'
            )
        },
    )

    with pytest.raises(IntercambioRecusado, match="planilha com XML inválido") as excinfo:
        ler(conteudo)

    assert "linha 2" in excinfo.value.mensagem


@pytest.mark.django_db
@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_responde_400_pela_api_sem_500(
    cabeca, linha_2, cauda, client: Client
):
    empresa = _empresa_com_analista("analista-leitor-api")
    conteudo = _com_partes(
        _base(),
        {"xl/worksheets/sheet1.xml": _planilha_com_linha_2(linha_2, cabeca=cabeca, cauda=cauda)},
    )
    _entrar(client, "analista-leitor-api")

    resposta = client.post(
        reverse("contabilidade:plano-importacao-previa", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile(
                "plano.xlsx", conteudo, content_type="application/octet-stream"
            ),
            "formato": "excel",
        },
    )

    assert resposta.status_code == 400, resposta.content[:300]
    assert "planilha com XML inválido" in str(resposta.json())


@pytest.mark.django_db
@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_responde_400_na_tela_sem_500(cabeca, linha_2, cauda, client: Client):
    empresa = _empresa_com_gestor("gestor-leitor-tela")
    conteudo = _com_partes(
        _base(),
        {"xl/worksheets/sheet1.xml": _planilha_com_linha_2(linha_2, cabeca=cabeca, cauda=cauda)},
    )
    _entrar(client, "gestor-leitor-tela")

    resposta = client.post(
        reverse("contabilidade_web:plano_importar", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile(
                "plano.xlsx", conteudo, content_type="application/octet-stream"
            ),
            "formato": "excel",
            "politica": "so_acrescentar",
        },
    )

    assert resposta.status_code == 400, resposta.content.decode()[:300]
    assert "planilha com XML inválido" in resposta.content.decode()


# -----------------------------------------------------------------------------
# T-R3a, T-R3b, T-R3c: custo do XML contado antes do openpyxl
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cabeca",
    [
        pytest.param("", id="sem_dimension"),
        pytest.param('<dimension ref="A1:A2"/>', id="dimension_forjada"),
    ],
)
def test_colunas_esparsas_sem_dimension_sao_recusadas_em_menos_de_2s(cabeca):
    """T-R3a: 3.000 linhas com uma célula em XFD. O openpyxl preenchia 16 mil células por linha
    (medido: 9,9 s para 2.000 linhas). A referência `r` é lida, com ou sem `dimension`."""
    corpo = _linha_de_cabecalho() + "".join(
        f'<row r="{n}"><c r="XFD{n}"/></row>' for n in range(2, 3001)
    )
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(corpo, cabeca=cabeca)})

    inicio = time.perf_counter()
    with pytest.raises(IntercambioRecusado, match="coluna"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_RECUSA_S, f"recusa levou {decorrido:.2f} s"


def test_tres_milhoes_de_elementos_no_sheetdata_sao_recusados_em_menos_de_3s():
    """T-R3b: `<a/>` é elemento desconhecido e custava 65 s no relatório. Conta-se todo elemento,
    e o teto por planilha (1 milhão) recusa antes de o openpyxl tocar na aba."""
    corpo = "<a/>" * 3_000_000
    conteudo = _com_partes(_base(), {"xl/worksheets/sheet1.xml": _folha(corpo)})

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="elementos XML"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_ELEMENTOS_S, f"recusa levou {decorrido:.2f} s"


def test_styles_com_tres_milhoes_de_xf_e_recusado_em_menos_de_2s():
    """T-R3c: 18 MB de estilos. Passa do teto de 4 MB da parte de apoio, e a medição das partes
    recusa antes de qualquer parse."""
    conteudo = _com_partes(_base(), {"xl/styles.xml": _estilos(3_000_000)})

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="xl/styles.xml"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_RECUSA_S, f"recusa levou {decorrido:.2f} s"


def test_styles_pequeno_com_muitos_elementos_e_recusado_pela_contagem():
    """Mesma classe de custo, em tamanho dentro do teto de bytes: 300 mil `<xf/>` (1,5 MB).
    Só a contagem de elementos da parte de apoio (200 mil) recusa."""
    conteudo = _com_partes(_base(), {"xl/styles.xml": _estilos(300_000)})

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="elementos XML"):
        ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_RECUSA_S, f"recusa levou {decorrido:.2f} s"


def test_styles_renomeado_e_apontado_pela_relacao_tambem_e_contado():
    """O openpyxl abre a parte de estilos pela relação do workbook, então o nome não protege.
    Renomeada para `xl/estilos.xml` e apontada pela relação, ela é contada do mesmo jeito."""
    base = _com_partes(_base(), {"xl/styles.xml": _estilos(300_000)})
    conteudo = _renomear_parte(base, "xl/styles.xml", "xl/estilos.xml")

    with pytest.raises(ArquivoGrandeDemais, match="elementos XML"):
        ler(conteudo)


def test_sharedstrings_de_5_mb_e_recusada_pelo_teto_de_4_mb_da_parte_de_apoio():
    """A tabela de textos tem teto de 4 MB (antes eram 16 MB). Uma entrada só com 5 MB de texto:
    poucos elementos, então quem recusa é o TETO DE BYTES, e não a contagem de elementos."""
    tabela = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        b"<si><t>" + b"x" * (5 * 1024 * 1024) + b"</t></si></sst>"
    )
    conteudo = _com_tabela_de_textos(_base(), tabela)

    with pytest.raises(ArquivoGrandeDemais, match="passa de 4 MB"):
        ler(conteudo)


# -----------------------------------------------------------------------------
# Orçamento de células e fronteira de colunas
# -----------------------------------------------------------------------------


def test_orcamento_de_celulas_aceita_60_mil_e_recusa_60_mil_e_uma():
    """T-R3d (fronteira): 1.200 linhas de 50 células são exatamente 60 mil. Uma a mais recusa."""
    linha = "<row>" + "<c/>" * 50 + "</row>"
    no_limite = _com_partes(
        _base(), {"xl/worksheets/sheet1.xml": _folha("".join(linha for _ in range(1200)))}
    )
    # A célula extra fica numa linha própria: dentro da linha 1.200 ela estouraria o limite de
    # 50 por linha, e o teste mediria outra regra.
    passou_do_limite = _com_partes(
        _base(),
        {
            "xl/worksheets/sheet1.xml": _folha(
                "".join(linha for _ in range(1200)) + "<row><c/></row>"
            )
        },
    )

    ler(no_limite)
    with pytest.raises(ArquivoGrandeDemais, match="60000 células"):
        ler(passou_do_limite)


def test_coluna_ax_passa_e_coluna_ay_e_recusada():
    """Fronteira de colunas: AX é a 50ª e passa. AY é a 51ª e a referência é recusada."""
    ax = _com_partes(
        _base(),
        {"xl/worksheets/sheet1.xml": _planilha_com_linha_2('<row r="2"><c r="AX2"/></row>')},
    )
    ay = _com_partes(
        _base(),
        {"xl/worksheets/sheet1.xml": _planilha_com_linha_2('<row r="2"><c r="AY2"/></row>')},
    )

    resultado = ler(ax)
    assert not _erros(resultado)
    with pytest.raises(IntercambioRecusado, match="coluna 50"):
        ler(ay)


# -----------------------------------------------------------------------------
# N07: aba `plano` fora de xl/worksheets/
# -----------------------------------------------------------------------------


def test_aba_plano_fora_de_xl_worksheets_e_recusada_com_mensagem_nomeada():
    """N07: a aba apontada para `xl/plano.xml` escaparia do orçamento medido em
    `xl/worksheets/`. A recusa é nomeada, e não a leitura."""
    conteudo = _renomear_parte(_base(), "xl/worksheets/sheet1.xml", "xl/plano.xml")

    with pytest.raises(IntercambioRecusado, match="xl/worksheets"):
        ler(conteudo)


# -----------------------------------------------------------------------------
# Legítimos: o que precisa continuar lendo
# -----------------------------------------------------------------------------


def test_planilha_legitima_com_2000_contas_e_lida_sem_erro():
    pasta = Workbook()
    aba = pasta.active
    aba.title = "plano"
    aba.append(CAB)
    aba.append(["1", "Ativo", None, "N", "ativo", "devedora"])
    for numero in range(1, 2000):
        aba.append([f"1.{numero}", f"Conta {numero}", "1", "S", None, None])
    saida = io.BytesIO()
    pasta.save(saida)

    resultado = ler(saida.getvalue())

    assert not _erros(resultado), [o.mensagem for o in _erros(resultado)][:3]
    assert len(resultado.contas) == 2000


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice (soffice) não instalado")
def test_planilha_regravada_pelo_libreoffice_e_lida(tmp_path):
    """Arquivo que o LibreOffice real regrava: sharedStrings, estilos e docProps próprios."""
    origem = tmp_path / "origem.xlsx"
    origem.write_bytes(_base())
    subprocess.run(
        [
            "soffice",
            "--headless",
            "--norestore",
            f"-env:UserInstallation=file://{tmp_path / 'perfil'}",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(tmp_path / "saida"),
            str(origem),
        ],
        check=True,
        timeout=180,
        capture_output=True,
    )

    resultado = ler((tmp_path / "saida" / "origem.xlsx").read_bytes())

    assert not _erros(resultado), [o.mensagem for o in _erros(resultado)][:3]
    assert [c.codigo for c in resultado.contas] == ["1"]


# -----------------------------------------------------------------------------
# Apoio de API e tela
# -----------------------------------------------------------------------------


def _entrar(client, usuario):
    assert client.login(username=usuario, password=SENHA)


def _empresa_com_papel(usuario, papel):
    escritorio = Escritorio.objects.create(nome=f"Escritório {usuario}", cnpj="55555555000155")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social=f"Empresa {usuario} Ltda", cnpj="77777777000177"
    )
    criado = get_user_model().objects.create_user(
        username=usuario, email=f"{usuario}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=criado, escritorio=escritorio, papel=papel)
    return empresa


def _empresa_com_analista(usuario):
    return _empresa_com_papel(usuario, Papel.ANALISTA)


def _empresa_com_gestor(usuario):
    return _empresa_com_papel(usuario, Papel.GESTOR)
