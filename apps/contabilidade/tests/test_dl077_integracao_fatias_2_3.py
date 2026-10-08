"""DL-077, integração das fatias 2 e 3 sobre a correção da fatia 1.

Cobre, com expectativas escritas à mão e dados sintéticos:
- item 2: exportar lançamentos no leiaute de referência de empresa com CNPJ alfanumérico recusa
  com MENSAGEM_CNPJ_ALFANUMERICO (núcleo e API 400); ECD e formato próprio continuam saindo.
- item 3: o 0000 alfanumérico no leitor de lançamentos do leiaute de referência é ERRO nomeado.
- item 5: a planilha de lançamentos passa pelo orçamento de células e colunas (A4) ANTES do
  openpyxl, e a dimensão declarada não descarta conteúdo.
- item 6 (A9): 0000 repetido é erro e o primeiro vale; 0000 sem CNPJ é aviso; arquivo sem 0000
  é aviso; CNPJ em minúsculas é comparado na forma canônica.

Dados sintéticos. CNPJ alfanumérico fictício (RC-46).
"""

import io
import re
import time
import zipfile
from datetime import date
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from openpyxl import Workbook

from apps.contabilidade.intercambio.canonico import NIVEL_AVISO, NIVEL_ERRO, IntercambioRecusado
from apps.contabilidade.intercambio.formatos import (
    ecd_lancamentos_leitura,
    excel_lancamentos,
    referencia_lancamentos_leitura,
)
from apps.contabilidade.intercambio.formatos.referencia import MENSAGEM_CNPJ_ALFANUMERICO
from apps.contabilidade.intercambio.lancamentos import exportar_lancamentos
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
INICIO = date(2026, 1, 1)
FIM = date(2026, 3, 31)
CNPJ_ALFA = "12ABC34501DE35"  # sintético (RC-46)
CNPJ_ALFA_DE_OUTRA = "98XYZ76543WX21"  # sintético (RC-46)
CNPJ_NUMERICO = "22233344000138"  # sintético
LIMITE_DE_TEMPO_S = 2.0  # item 5: a recusa tem de sair em menos de 2 s


@pytest.fixture
def empresa_alfa():
    escritorio = criar_escritorio("Escritório DL077 Integração", "66666666000166")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Alfanumérica Ltda", cnpj=CNPJ_ALFA
    )
    criar_plano(empresa)
    return empresa


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _api(empresa, **parametros):
    url = reverse("contabilidade:lancamentos-exportacao", args=[empresa.id])
    return url + "?" + urlencode(parametros)


# -----------------------------------------------------------------------------
# Item 2: exportação no leiaute de referência com CNPJ alfanumérico
# -----------------------------------------------------------------------------


def test_referencia_de_empresa_com_cnpj_alfanumerico_recusa_com_mensagem_nomeada(empresa_alfa):
    with pytest.raises(IntercambioRecusado) as excinfo:
        exportar_lancamentos(
            empresa=empresa_alfa, formato="referencia", data_inicial=INICIO, data_final=FIM
        )

    assert excinfo.value.mensagem == MENSAGEM_CNPJ_ALFANUMERICO


def test_api_referencia_de_empresa_com_cnpj_alfanumerico_responde_400_com_a_mensagem(
    client, empresa_alfa
):
    escritorio = empresa_alfa.escritorio
    _usuario("gestor-integracao", escritorio, Papel.GESTOR)
    assert client.login(username="gestor-integracao", password=SENHA)

    resposta = client.get(
        _api(empresa_alfa, formato="referencia", inicio="2026-01-01", fim="2026-03-31")
    )

    assert resposta.status_code == 400
    assert MENSAGEM_CNPJ_ALFANUMERICO in resposta.content.decode()


def test_api_ecd_e_proprio_de_empresa_com_cnpj_alfanumerico_seguem(client, empresa_alfa):
    escritorio = empresa_alfa.escritorio
    _usuario("gestor-integracao-2", escritorio, Papel.GESTOR)
    assert client.login(username="gestor-integracao-2", password=SENHA)

    for formato in ("ecd", "proprio"):
        resposta = client.get(
            _api(empresa_alfa, formato=formato, inicio="2026-01-01", fim="2026-03-31")
        )
        assert resposta.status_code == 200, (formato, resposta.content)


def test_referencia_de_empresa_com_cnpj_numerico_continua_com_0000_canonico():
    escritorio = criar_escritorio("Escritório DL077 Numérico", "77777777000177")
    empresa = criar_empresa(escritorio=escritorio, razao_social="Numérica Ltda", cnpj=CNPJ_NUMERICO)
    criar_plano(empresa)

    arquivo = exportar_lancamentos(
        empresa=empresa, formato="referencia", data_inicial=INICIO, data_final=FIM
    )

    assert arquivo.conteudo.startswith(f"|0000|{CNPJ_NUMERICO}|\r\n".encode("iso-8859-1"))


# -----------------------------------------------------------------------------
# Item 3: leitor de lançamentos do leiaute de referência, 0000 alfanumérico
# -----------------------------------------------------------------------------


def test_leitor_de_lancamentos_referencia_0000_alfanumerico_e_erro_nomeado():
    conteudo = f"|0000|{CNPJ_ALFA}|\r\n".encode("iso-8859-1")

    resultado = referencia_lancamentos_leitura.ler(conteudo)

    erro = next(o for o in resultado.ocorrencias if o.campo == "0000.2")
    assert erro.nivel == NIVEL_ERRO
    assert erro.mensagem == MENSAGEM_CNPJ_ALFANUMERICO
    assert resultado.documento_declarado is None


def test_leitor_de_lancamentos_referencia_0000_com_formato_ruim_ainda_tem_mensagem_generica():
    resultado = referencia_lancamentos_leitura.ler("|0000|1234|\r\n".encode("iso-8859-1"))

    erro = next(o for o in resultado.ocorrencias if o.campo == "0000.2")
    assert erro.nivel == NIVEL_ERRO
    assert erro.mensagem != MENSAGEM_CNPJ_ALFANUMERICO
    assert resultado.documento_declarado is None


# -----------------------------------------------------------------------------
# Item 5: planilha de lançamentos sob o orçamento de células (A4)
# -----------------------------------------------------------------------------


def _xlsx_de_lancamentos(linhas=(), ajustar=None):
    """Planilha de lançamentos com a aba `lancamentos` e o cabeçalho do modelo."""
    pasta = Workbook()
    aba = pasta.active
    aba.title = "lancamentos"
    aba.append(["numero", "data", "historico", "conta", "lado", "valor"])
    for linha in linhas:
        aba.append(linha)
    if ajustar is not None:
        ajustar(aba)
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _com_partes(conteudo, trocar):
    """Copia o pacote trocando partes pelos bytes dados (ou por uma função que os recebe)."""
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for parte in origem.infolist():
            dados = origem.read(parte.filename)
            if parte.filename in trocar:
                dados = trocar[parte.filename](dados)
            destino.writestr(parte.filename, dados)
    return saida.getvalue()


def _folha(corpo):
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{corpo}</sheetData></worksheet>"
    ).encode("utf-8")


def test_planilha_de_lancamentos_com_linha_de_16_mil_celulas_e_recusada_em_menos_de_2s():
    """O ataque da auditoria, agora também no leitor de lançamentos: `<c/>` sem fim numa linha."""
    linha = '<row r="2">' + "<c/>" * 16384 + "</row>"
    conteudo = _com_partes(
        _xlsx_de_lancamentos(), {"xl/worksheets/sheet1.xml": lambda _: _folha(linha)}
    )

    inicio = time.perf_counter()
    with pytest.raises(IntercambioRecusado, match="mais de 50 células") as excinfo:
        excel_lancamentos.ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert "linha 2" in excinfo.value.mensagem
    assert decorrido < LIMITE_DE_TEMPO_S


def test_planilha_de_lancamentos_com_total_acima_do_orcamento_recusa_em_menos_de_2s():
    """12 mil linhas de 50 células (600 mil) estouram o orçamento de 500 mil antes do openpyxl."""
    linha = "<row>" + "<c/>" * 50 + "</row>"
    corpo = "".join(linha for _ in range(12_000))
    conteudo = _com_partes(
        _xlsx_de_lancamentos(), {"xl/worksheets/sheet1.xml": lambda _: _folha(corpo)}
    )

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="células"):
        excel_lancamentos.ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_S


def _aba_fora_de_xl_worksheets(conteudo):
    """Move a parte da aba para `xl/outra/` e aponta o workbook para lá. O orçamento de células
    só conta o que está em `xl/worksheets/`, então a aba precisa ser recusada, e não lida."""
    origem = zipfile.ZipFile(io.BytesIO(conteudo))
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        for parte in origem.infolist():
            nome = parte.filename
            dados = origem.read(nome)
            if nome == "xl/worksheets/sheet1.xml":
                nome = "xl/outra/sheet1.xml"
            elif nome == "xl/_rels/workbook.xml.rels":
                dados = dados.replace(b"worksheets/sheet1.xml", b"outra/sheet1.xml")
            elif nome == "[Content_Types].xml":
                dados = dados.replace(b"/xl/worksheets/sheet1.xml", b"/xl/outra/sheet1.xml")
            destino.writestr(nome, dados)
    return saida.getvalue()


def test_aba_de_lancamentos_fora_de_xl_worksheets_e_recusada():
    conteudo = _aba_fora_de_xl_worksheets(_xlsx_de_lancamentos())

    with pytest.raises(IntercambioRecusado, match="não está em xl/worksheets"):
        excel_lancamentos.ler(conteudo)


def test_conteudo_alem_da_dimensao_declarada_nao_e_descartado_em_silencio():
    """A dimensão do XML diz A1:A1, mas a linha 2 tem texto na coluna H. Antes da A4 o
    conteúdo além da dimensão sumia; agora vira erro com a coluna."""

    def declarar_dimensao_pequena(dados):
        trocado, quantos = re.subn(
            rb'<dimension ref="A1:H2"\s*/>', b'<dimension ref="A1:A1"/>', dados
        )
        assert quantos == 1, "o openpyxl deveria ter gravado a dimensão A1:H2"
        return trocado

    conteudo = _xlsx_de_lancamentos(
        linhas=[["1", "2026-01-05", "Histórico", "1.1", "D", "10.00"]],
        ajustar=lambda aba: aba.__setitem__("H2", "lixo além da dimensão"),
    )
    conteudo = _com_partes(conteudo, {"xl/worksheets/sheet1.xml": declarar_dimensao_pequena})

    resultado = excel_lancamentos.ler(conteudo)

    erros = [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert any(o.campo == "coluna 8" for o in erros), [(o.campo, o.mensagem) for o in erros]


# -----------------------------------------------------------------------------
# Item 6 (A9): leitor de lançamentos da ECD segue a regra do 0000 do plano
# -----------------------------------------------------------------------------


def _0000(cnpj):
    return f"|0000|LECD|01012026|31012026|Empresa Sintética Ltda|{cnpj}|SP|||"


def _ecd(*linhas):
    return ("\r\n".join(linhas) + "\r\n").encode("iso-8859-1")


def test_ecd_lancamentos_0000_repetido_e_erro_e_o_primeiro_e_o_que_vale():
    conteudo = _ecd(_0000(CNPJ_ALFA), _0000(CNPJ_ALFA_DE_OUTRA), "|I075|1|Histórico|")

    resultado = ecd_lancamentos_leitura.ler(conteudo)

    erros = [o for o in resultado.ocorrencias if o.nivel == NIVEL_ERRO]
    assert [(o.linha, o.campo) for o in erros] == [(2, "0000")]
    assert resultado.documento_declarado == CNPJ_ALFA


def test_ecd_lancamentos_0000_sem_cnpj_e_aviso_e_nao_erro():
    conteudo = _ecd("|0000|LECD|01012026|31012026|Empresa Sintética Ltda||SP|||")

    resultado = ecd_lancamentos_leitura.ler(conteudo)

    avisos = [o for o in resultado.ocorrencias if o.nivel == NIVEL_AVISO]
    assert any(o.campo == "0000.6" for o in avisos)
    assert not any(o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)
    assert resultado.documento_declarado is None


def test_ecd_lancamentos_sem_0000_e_aviso_na_previa():
    conteudo = _ecd("|I075|1|Histórico|")

    resultado = ecd_lancamentos_leitura.ler(conteudo)

    aviso = next(o for o in resultado.ocorrencias if o.campo == "0000")
    assert aviso.nivel == NIVEL_AVISO
    assert aviso.linha == 0
    assert not any(o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)
    assert resultado.documento_declarado is None


def test_ecd_lancamentos_cnpj_alfanumerico_em_minusculas_e_comparado_na_forma_canonica():
    conteudo = _ecd(_0000(CNPJ_ALFA.lower()))

    resultado = ecd_lancamentos_leitura.ler(conteudo)

    assert not any(o.nivel == NIVEL_ERRO for o in resultado.ocorrencias)
    assert resultado.documento_declarado == CNPJ_ALFA
