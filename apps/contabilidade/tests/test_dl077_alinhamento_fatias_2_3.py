"""DL-077, alinhamento das fatias 2 e 3 à fatia 1 final (2026-10-08).

Cobre, nesta ordem:
1. Leitor Excel de LANÇAMENTOS com as proteções da fatia 1: XML malformado na aba vira recusa
   nomeada na leitura, na API e na tela (400, nunca 500) — T-R2 aplicado à planilha de lançamentos;
   colunas além de 50 (T-R3a) e milhões de elementos (T-R3b) recusados antes do openpyxl.
2. Mensagens compartilhadas de `excel.py` que servem às duas planilhas e não citam o plano.
3. Efetivação com zero lançamento: recusa nomeada no serviço, na API e na tela (sem botão);
   de-para com conta sintética ou inativa recusado no serviço, com mensagem nomeada.
4. Teto de lançamentos por arquivo (2.000, medido), com recusa nomeada acima dele.

Dados SINTÉTICOS: escritório e empresas de teste, plano do cenário de exportação, valores redondos.
Os XMLs malformados e as montagens de pacote vêm de `test_dl077_correcao_leitor_xlsx` (fatia 1),
importados e NÃO copiados.
"""

import io
import json
import time
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.intercambio.canonico import NIVEL_ERRO, IntercambioRecusado
from apps.contabilidade.intercambio.formatos import excel_lancamentos
from apps.contabilidade.intercambio.formatos.proprio_lancamentos_leitura import (
    CABECALHO_LANCAMENTOS,
)
from apps.contabilidade.intercambio.leitura import ArquivoGrandeDemais
from apps.contabilidade.models import (
    DeParaConta,
    EstadoImportacaoLancamentos,
    ImportacaoLancamentos,
    LancamentoContabil,
)
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.contabilidade.tests.test_dl077_correcao_leitor_xlsx import (
    FORMAS_MALFORMADAS,
    _com_partes,
    _estilos,
    _folha,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
LIMITE_DE_TEMPO_RECUSA_S = 2.0  # T-R3a: a recusa sai em menos de 2 s
LIMITE_DE_TEMPO_ELEMENTOS_S = 3.0  # T-R3b

pytestmark = pytest.mark.django_db


# -----------------------------------------------------------------------------
# Montagem de planilhas de LANÇAMENTOS (sintéticas)
# -----------------------------------------------------------------------------


def _base_de_lancamentos():
    """Um .xlsx válido de openpyxl: aba `lancamentos`, cabeçalho e um lançamento de 2 partidas."""
    pasta = Workbook()
    aba = pasta.active
    aba.title = "lancamentos"
    aba.append(list(CABECALHO_LANCAMENTOS))
    aba.append([1, "2026-03-10", "Compra", "1.1.1", "D", "100.00"])
    aba.append([1, "2026-03-10", "Compra", "2.1", "C", "100.00"])
    saida = io.BytesIO()
    pasta.save(saida)
    return saida.getvalue()


def _linha_de_cabecalho_de_lancamentos():
    return (
        '<row r="1">'
        + "".join(
            f'<c r="{coluna}1" t="inlineStr"><is><t>{texto}</t></is></c>'
            for coluna, texto in zip("ABCDEF", CABECALHO_LANCAMENTOS, strict=True)
        )
        + "</row>"
    )


def _planilha_de_lancamentos(linha_2, *, cabeca="", cauda=""):
    """Cabeçalho válido na linha 1 e a `linha_2` (a malformada) logo depois."""
    return _folha(_linha_de_cabecalho_de_lancamentos() + linha_2, cabeca=cabeca, cauda=cauda)


def _com_aba_de_lancamentos(xml):
    return _com_partes(_base_de_lancamentos(), {"xl/worksheets/sheet1.xml": xml})


def _lancamentos_de_proprio(n):
    """Linhas do formato próprio: `n` lançamentos de 2 partidas, sintéticos e equilibrados."""
    linhas = []
    for i in range(1, n + 1):
        linhas.append(f"{i};2026-03-10;Compra {i};1.1.1;D;100.00")
        linhas.append(f"{i};2026-03-10;Compra {i};2.1;C;100.00")
    return linhas


def _arquivo_proprio(*linhas):
    cabecalho = "numero;data;historico;conta;lado;valor\r\n"
    return (cabecalho + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _entrar(client, usuario):
    assert client.login(username=usuario, password=SENHA)


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def cenario():
    escritorio = criar_escritorio("Escritório Alinhamento", "66666666000166")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Alinhamento Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    _usuario("analista-alinhamento", escritorio, Papel.ANALISTA)
    _usuario("gestor-alinhamento", escritorio, Papel.GESTOR)
    return {"empresa": empresa, "contas": contas, "escritorio": escritorio}


def _receber(empresa, *linhas):
    return servico.receber(
        empresa=empresa,
        formato="proprio",
        conteudo=_arquivo_proprio(*linhas),
        nome_arquivo="lanc.txt",
        usuario=None,
    )


def _sem_plano(texto):
    return "plano" not in texto.lower()


# -----------------------------------------------------------------------------
# 1. T-R2 aplicado à planilha de LANÇAMENTOS
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_lancamentos_e_recusado_com_mensagem_nomeada(cabeca, linha_2, cauda):
    conteudo = _com_aba_de_lancamentos(
        _planilha_de_lancamentos(linha_2, cabeca=cabeca, cauda=cauda)
    )

    with pytest.raises(IntercambioRecusado, match="planilha com XML inválido"):
        excel_lancamentos.ler(conteudo)


def test_erro_de_celula_em_lancamentos_informa_a_linha_da_planilha():
    """R2: o diagnóstico tem a linha quando ela é conhecida. A célula malformada está na 2."""
    conteudo = _com_aba_de_lancamentos(
        _planilha_de_lancamentos('<row r="2"><c r="A2" t="n"><v>abc</v></c></row>')
    )

    with pytest.raises(IntercambioRecusado, match="planilha com XML inválido") as excinfo:
        excel_lancamentos.ler(conteudo)

    assert "linha 2" in excinfo.value.mensagem


def test_falha_fora_do_laco_por_linha_tambem_vira_recusa_nomeada(monkeypatch):
    """Guarda externa de `ler` (R2). Nenhum XML real chega depois do laço por linha, então a falha
    é INJETADA em `montar_lancamentos` (um ponto de costura, não um mock de integração). Ela sai
    como recusa nomeada, com o NOME do tipo da exceção e sem o texto dela (que pode trazer conteúdo
    do arquivo)."""

    def falha(*_args, **_kwargs):
        raise ValueError("texto da falha injetada que não pode aparecer na recusa")

    monkeypatch.setattr(excel_lancamentos, "montar_lancamentos", falha)

    with pytest.raises(IntercambioRecusado, match="planilha com XML inválido") as excinfo:
        excel_lancamentos.ler(_base_de_lancamentos())

    assert "ValueError" in excinfo.value.mensagem
    assert "texto da falha injetada" not in excinfo.value.mensagem


@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_lancamentos_responde_400_pela_api(
    client, cenario, cabeca, linha_2, cauda
):
    _entrar(client, "analista-alinhamento")
    conteudo = _com_aba_de_lancamentos(
        _planilha_de_lancamentos(linha_2, cabeca=cabeca, cauda=cauda)
    )

    resposta = client.post(
        reverse("contabilidade:lancamentos-importacao", args=[cenario["empresa"].id]),
        {
            "arquivo": SimpleUploadedFile(
                "lanc.xlsx", conteudo, content_type="application/octet-stream"
            ),
            "formato": "excel",
        },
    )

    assert resposta.status_code == 400, resposta.content[:300]
    assert "planilha com XML inválido" in str(resposta.json())


@pytest.mark.parametrize(("cabeca", "linha_2", "cauda"), FORMAS_MALFORMADAS)
def test_xml_malformado_na_aba_lancamentos_responde_400_na_tela(
    client, cenario, cabeca, linha_2, cauda
):
    _entrar(client, "gestor-alinhamento")
    conteudo = _com_aba_de_lancamentos(
        _planilha_de_lancamentos(linha_2, cabeca=cabeca, cauda=cauda)
    )

    resposta = client.post(
        reverse("contabilidade_web:lancamentos_importar", args=[cenario["empresa"].id]),
        {
            "arquivo": SimpleUploadedFile(
                "lanc.xlsx", conteudo, content_type="application/octet-stream"
            ),
            "formato": "excel",
        },
    )

    assert resposta.status_code == 400, resposta.content.decode()[:300]
    assert "planilha com XML inválido" in resposta.content.decode()


# -----------------------------------------------------------------------------
# 1b. T-R3a e T-R3b aplicados a lançamentos
# -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cabeca",
    [
        pytest.param("", id="sem_dimension"),
        pytest.param('<dimension ref="A1:A2"/>', id="dimension_forjada"),
    ],
)
def test_colunas_esparsas_em_lancamentos_sao_recusadas_em_menos_de_2s(cabeca):
    """T-R3a: uma célula em XFD por linha. A referência `r` é lida antes do openpyxl."""
    corpo = _linha_de_cabecalho_de_lancamentos() + "".join(
        f'<row r="{n}"><c r="XFD{n}"/></row>' for n in range(2, 3001)
    )
    conteudo = _com_aba_de_lancamentos(_folha(corpo, cabeca=cabeca))

    inicio = time.perf_counter()
    with pytest.raises(IntercambioRecusado, match="coluna"):
        excel_lancamentos.ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_RECUSA_S, f"recusa levou {decorrido:.2f} s"


def test_colunas_esparsas_em_lancamentos_respondem_400_pela_api(client, cenario):
    _entrar(client, "analista-alinhamento")
    corpo = _linha_de_cabecalho_de_lancamentos() + '<row r="2"><c r="XFD2"/></row>'
    conteudo = _com_aba_de_lancamentos(_folha(corpo))

    resposta = client.post(
        reverse("contabilidade:lancamentos-importacao", args=[cenario["empresa"].id]),
        {
            "arquivo": SimpleUploadedFile(
                "lanc.xlsx", conteudo, content_type="application/octet-stream"
            ),
            "formato": "excel",
        },
    )

    assert resposta.status_code == 400, resposta.content[:300]
    assert "coluna" in str(resposta.json())


def test_tres_milhoes_de_elementos_em_lancamentos_sao_recusados_em_menos_de_3s():
    """T-R3b: `<a/>` é elemento desconhecido, e o teto por planilha recusa antes do openpyxl."""
    conteudo = _com_aba_de_lancamentos(_folha("<a/>" * 3_000_000))

    inicio = time.perf_counter()
    with pytest.raises(ArquivoGrandeDemais, match="elementos XML"):
        excel_lancamentos.ler(conteudo)
    decorrido = time.perf_counter() - inicio

    assert decorrido < LIMITE_DE_TEMPO_ELEMENTOS_S, f"recusa levou {decorrido:.2f} s"


# -----------------------------------------------------------------------------
# 2. Mensagens compartilhadas: nenhuma cita o plano, nas duas planilhas
# -----------------------------------------------------------------------------


def test_pacote_com_partes_demais_nao_cita_o_plano_na_planilha_de_lancamentos():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as pacote:
        for n in range(1001):
            pacote.writestr(f"parte{n}.xml", "<a/>")

    with pytest.raises(IntercambioRecusado, match="partes internas") as excinfo:
        excel_lancamentos.ler(buffer.getvalue())

    assert "modelo do DataLedger" in excinfo.value.mensagem
    assert _sem_plano(excinfo.value.mensagem)


def test_csv_renomeado_na_planilha_de_lancamentos_orienta_o_modelo_sem_citar_o_plano():
    conteudo = "numero;data;historico;conta;lado;valor\r\n1;2026-03-10;x;1.1.1;D;1\r\n".encode()

    with pytest.raises(IntercambioRecusado, match="não é uma planilha .xlsx") as excinfo:
        excel_lancamentos.ler(conteudo)

    assert "modelo do DataLedger" in excinfo.value.mensagem
    assert _sem_plano(excinfo.value.mensagem)


def test_styles_grande_na_planilha_de_lancamentos_nao_cita_o_plano():
    conteudo = _com_partes(_base_de_lancamentos(), {"xl/styles.xml": _estilos(300_000)})

    with pytest.raises(ArquivoGrandeDemais, match="elementos XML") as excinfo:
        excel_lancamentos.ler(conteudo)

    assert "modelo do DataLedger" in excinfo.value.mensagem
    assert _sem_plano(excinfo.value.mensagem)


def test_orcamento_de_celulas_da_planilha_de_lancamentos_nao_cita_o_plano():
    """60.001 células: a última linha tem uma célula a mais que o orçamento de 60 mil."""
    linha = "<row>" + "<c/>" * 50 + "</row>"
    conteudo = _com_aba_de_lancamentos(_folha(linha * 1200 + "<row><c/></row>"))

    with pytest.raises(ArquivoGrandeDemais, match="60000 células") as excinfo:
        excel_lancamentos.ler(conteudo)

    assert "modelo do DataLedger" in excinfo.value.mensagem
    assert _sem_plano(excinfo.value.mensagem)


# -----------------------------------------------------------------------------
# 3a. Efetivação com zero lançamento: serviço, API e tela
# -----------------------------------------------------------------------------


def test_efetivar_arquivo_sem_lancamento_e_recusado_nomeado_e_nao_efetiva(cenario):
    importacao = _receber(cenario["empresa"])
    assert importacao.quantidade_lancamentos == 0

    with pytest.raises(servico.ImportacaoNaoEfetivada, match="não há lançamento para efetivar"):
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()


def test_so_validos_sem_lancamento_pronto_e_recusado_nomeado_e_nao_efetiva(cenario):
    """Um lançamento só com débito é erro: nenhum está pronto, e a efetivação não pode seguir."""
    importacao = _receber(cenario["empresa"], "7;2026-03-10;Compra;1.1.1;D;100.00")
    assert importacao.quantidade_com_erro == 1

    with pytest.raises(servico.ImportacaoNaoEfetivada, match="não há lançamento para efetivar"):
        servico.efetivar(importacao, politica=servico.SO_VALIDOS, usuario=None)

    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()


def test_tela_nao_oferece_botao_de_efetivar_sem_lancamento(client, cenario):
    empresa = cenario["empresa"]
    importacao = _receber(empresa)
    _entrar(client, "gestor-alinhamento")

    resposta = client.get(
        reverse("contabilidade_web:lancamentos_importacao", args=[empresa.id, importacao.id])
    )

    html = resposta.content.decode()
    url_de_efetivar = reverse(
        "contabilidade_web:lancamentos_importacao_efetivar", args=[empresa.id, importacao.id]
    )
    assert resposta.status_code == 200
    assert "não há lançamento para efetivar" in html
    assert url_de_efetivar not in html, "a tela ofereceu efetivar sem nenhum lançamento"
    assert "(indisponível)" not in html, "botão desabilitado também é oferta: não deve aparecer"


def test_tela_recusa_efetivar_sem_lancamento_com_400_e_nada_grava(client, cenario):
    empresa = cenario["empresa"]
    importacao = _receber(empresa)
    _entrar(client, "gestor-alinhamento")

    resposta = client.post(
        reverse(
            "contabilidade_web:lancamentos_importacao_efetivar", args=[empresa.id, importacao.id]
        ),
        {"politica": servico.TUDO_OU_NADA, "confirmar": "sim"},
    )

    assert resposta.status_code == 400
    assert "não há lançamento para efetivar" in resposta.content.decode()
    importacao.refresh_from_db()
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


def test_api_recusa_efetivar_sem_lancamento_com_400(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "analista-alinhamento")
    envio = client.post(
        reverse("contabilidade:lancamentos-importacao", args=[empresa.id]),
        {
            "arquivo": SimpleUploadedFile(
                "vazio.txt", _arquivo_proprio(), content_type="text/plain"
            ),
            "formato": "proprio",
        },
    )
    assert envio.status_code == 201, envio.content[:300]
    importacao_id = envio.json()["id"]

    resposta = client.post(
        reverse("contabilidade:lancamentos-importacao-efetivar", args=[empresa.id, importacao_id]),
        data=json.dumps({"politica": "tudo_ou_nada"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "não há lançamento para efetivar" in str(resposta.json())
    assert not LancamentoContabil.objects.filter(empresa=empresa).exists()


# -----------------------------------------------------------------------------
# 3b. De-para: conta sintética e inativa recusadas no serviço, com mensagem nomeada
# -----------------------------------------------------------------------------


def test_definir_de_para_com_conta_sintetica_e_recusado_nomeado(cenario):
    with pytest.raises(servico.ImportacaoRecusada, match="é sintética"):
        servico.definir_de_para(
            empresa=cenario["empresa"],
            formato="referencia",
            codigo_origem="3",
            conta=cenario["contas"]["2"],
            usuario=None,
        )

    assert not DeParaConta.objects.filter(empresa=cenario["empresa"]).exists()


def test_definir_de_para_com_conta_inativa_e_recusado_nomeado(cenario):
    from apps.contabilidade.models import Conta

    Conta.objects.filter(pk=cenario["contas"]["2.1"].pk).update(ativo=False)
    conta_inativa = Conta.objects.get(pk=cenario["contas"]["2.1"].pk)

    with pytest.raises(servico.ImportacaoRecusada, match="está inativa"):
        servico.definir_de_para(
            empresa=cenario["empresa"],
            formato="referencia",
            codigo_origem="3",
            conta=conta_inativa,
            usuario=None,
        )

    assert not DeParaConta.objects.filter(empresa=cenario["empresa"]).exists()


def test_api_de_para_com_conta_sintetica_responde_400(client, cenario):
    empresa = cenario["empresa"]
    _entrar(client, "analista-alinhamento")

    resposta = client.post(
        reverse("contabilidade:lancamentos-importacao-de-para", args=[empresa.id]),
        data=json.dumps(
            {"formato": "referencia", "codigo_origem": "3", "conta": cenario["contas"]["2"].id}
        ),
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content[:300]
    assert "é sintética" in str(resposta.json())
    assert not DeParaConta.objects.filter(empresa=empresa).exists()


# -----------------------------------------------------------------------------
# 4. Teto de lançamentos por arquivo: 2.000 (medido)
# -----------------------------------------------------------------------------


def test_teto_de_lancamentos_por_arquivo_e_2000():
    """Medido em 2026-10-08: efetivar ~10,7 ms por lançamento e linear; 20.000 leva ~214 s, acima
    do timeout de 30 s do gunicorn. Ver o comentário de `LIMITE_DE_LANCAMENTOS_POR_ARQUIVO`."""
    assert servico.LIMITE_DE_LANCAMENTOS_POR_ARQUIVO == 2_000


def test_arquivo_com_2001_lancamentos_e_recusado_antes_de_gravar(cenario):
    with pytest.raises(servico.ImportacaoRecusada, match="limite por arquivo é 2000"):
        _receber(cenario["empresa"], *_lancamentos_de_proprio(2001))

    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()


def test_arquivo_com_2000_lancamentos_e_aceito_na_fronteira(cenario):
    importacao = _receber(cenario["empresa"], *_lancamentos_de_proprio(2000))

    assert importacao.quantidade_lancamentos == 2000
    assert importacao.quantidade_com_erro == 0
    assert importacao.estado == EstadoImportacaoLancamentos.EM_CONFERENCIA


def test_erro_do_arquivo_nao_e_confundido_com_zero_lancamento(cenario):
    """Um arquivo sem lançamento mas com erro do arquivo recusa com o erro, e não com o zero."""
    importacao = _receber(cenario["empresa"])
    importacao.ocorrencias_do_arquivo = [
        {
            "linha": 1,
            "campo": "cabecalho",
            "nivel": NIVEL_ERRO,
            "mensagem": "x",
            "origem": "leitura",
        }
    ]
    importacao.save(update_fields=["ocorrencias_do_arquivo"])

    with pytest.raises(servico.ImportacaoNaoEfetivada) as excinfo:
        servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)

    assert "não há lançamento para efetivar" not in excinfo.value.mensagem
    assert "erro" in excinfo.value.mensagem
