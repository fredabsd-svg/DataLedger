"""Correção única da auditoria das fatias 2 e 3 (DL-077, rodada 1): EXPORTAÇÃO de lançamentos.

A6 (texto fora de ISO-8859-1 com a opção `normalizar_texto`, na API, na tela e no núcleo), M46
(conciliação de saldos com lançamentos) e M49 (download da tela recusado ao cliente). Dados
SINTÉTICOS: CNPJ de exemplo, plano do cenário de exportação, históricos de teste.
"""

from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.intercambio import lancamentos as nucleo
from apps.contabilidade.intercambio.canonico import IntercambioRecusado
from apps.contabilidade.intercambio.lancamentos import ExportacaoRecusada, exportar_lancamentos
from apps.contabilidade.models import LancamentoContabil, TipoPartida
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db

INICIO = date(2026, 3, 1)
FIM = date(2026, 3, 31)
HISTORICO_COM_TRAVESSAO = "Pagamento – parcela 1"


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _lancar(empresa, contas, dia, historico, valor="100.00"):
    return criar_lancamento(
        empresa=empresa,
        data=date(2026, 3, dia),
        historico=historico,
        itens=[
            {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
            {"conta": contas["2.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
        ],
    )


@pytest.fixture
def cenario(client):
    escritorio = criar_escritorio("Escritório Normalização", "11111111000111")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa Normalização", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    _lancar(empresa, contas, 2, HISTORICO_COM_TRAVESSAO)
    _lancar(empresa, contas, 3, "linha1\nlinha2")
    _lancar(empresa, contas, 4, "com\ttab")
    _lancar(empresa, contas, 5, "“citado” e ‘x’")
    _lancar(empresa, contas, 6, "fim…")
    _lancar(empresa, contas, 7, "a|b")
    _lancar(empresa, contas, 8, "Compra à vista")
    _usuario("gestor-norm", escritorio, Papel.GESTOR)
    _usuario("cliente-norm", escritorio, Papel.CLIENTE)
    return {"empresa": empresa, "contas": contas, "escritorio": escritorio}


# --- A6: núcleo da exportação -------------------------------------------------------------------


def test_t_a6_ecd_sem_a_opcao_recusa_e_nao_manda_editar_o_lancamento(cenario):
    """A6: sem a opção a recusa continua, com a mensagem certa: o efetivado não muda."""
    with pytest.raises(IntercambioRecusado) as excinfo:
        exportar_lancamentos(
            empresa=cenario["empresa"], formato="ecd", data_inicial=INICIO, data_final=FIM
        )

    mensagem = excinfo.value.mensagem
    assert "normalizar" in mensagem
    assert "lançamento efetivado não muda" in mensagem
    assert "troque o caractere" not in mensagem
    assert "no cadastro ou no histórico" not in mensagem


@pytest.mark.parametrize("formato", ["ecd", "referencia"])
def test_t_a6_com_a_opcao_o_arquivo_sai_em_latin1_e_lista_cada_troca(cenario, formato):
    """A6: com a opção o arquivo sai, e cada lançamento trocado aparece no relatório."""
    arquivo = exportar_lancamentos(
        empresa=cenario["empresa"],
        formato=formato,
        data_inicial=INICIO,
        data_final=FIM,
        normalizar_texto=True,
    )

    texto = arquivo.conteudo.decode("iso-8859-1")
    assert "Pagamento - parcela 1" in texto
    assert "linha1 linha2" in texto
    assert "com tab" in texto
    assert "\"citado\" e 'x'" in texto
    assert "fim..." in texto
    assert "a?b" in texto
    assert "Compra à vista" in texto, "texto que já cabe em Latin-1 não pode mudar"

    trocados = {t.antes: t.depois for t in arquivo.relatorio.textos_normalizados}
    assert trocados[HISTORICO_COM_TRAVESSAO] == "Pagamento - parcela 1"
    assert trocados["fim…"] == "fim..."
    assert "Compra à vista" not in trocados
    assert arquivo.relatorio.normalizar_texto is True
    assert arquivo.relatorio.para_trilha()["quantidade_textos_normalizados"] == len(trocados)


def test_t_a6_a_normalizacao_nao_muda_o_diario(cenario):
    """A6: o lançamento efetivado é o mesmo. A troca é só no arquivo."""
    exportar_lancamentos(
        empresa=cenario["empresa"],
        formato="ecd",
        data_inicial=INICIO,
        data_final=FIM,
        normalizar_texto=True,
    )

    assert LancamentoContabil.objects.filter(
        empresa=cenario["empresa"], historico=HISTORICO_COM_TRAVESSAO
    ).exists()


def test_t_a6_o_sha_do_arquivo_normalizado_e_estavel(cenario):
    """A6: com a opção, o SHA-256 vale para o arquivo que sai: repetir a exportação dá o mesmo."""
    primeira = exportar_lancamentos(
        empresa=cenario["empresa"],
        formato="ecd",
        data_inicial=INICIO,
        data_final=FIM,
        normalizar_texto=True,
    )
    segunda = exportar_lancamentos(
        empresa=cenario["empresa"],
        formato="ecd",
        data_inicial=INICIO,
        data_final=FIM,
        normalizar_texto=True,
    )

    assert primeira.sha256 == segunda.sha256
    assert primeira.relatorio.sha256 == primeira.sha256


def test_t_a6_formato_proprio_recusa_a_opcao_por_ser_utf8(cenario):
    """A6: o formato próprio é UTF-8: a opção é recusada, com o motivo."""
    with pytest.raises(nucleo.ParametroInvalido, match="ISO-8859-1"):
        exportar_lancamentos(
            empresa=cenario["empresa"],
            formato="proprio",
            data_inicial=INICIO,
            data_final=FIM,
            normalizar_texto=True,
        )


# --- A6: API e tela ------------------------------------------------------------------------------


def _url_api(empresa, **parametros):
    return (
        reverse("contabilidade:lancamentos-exportacao", args=[empresa.id])
        + "?"
        + urlencode({"inicio": "2026-03-01", "fim": "2026-03-31", **parametros})
    )


def _url_tela(nome, empresa, **parametros):
    return (
        reverse(f"contabilidade_web:{nome}", args=[empresa.id])
        + "?"
        + urlencode({"inicio": "2026-03-01", "fim": "2026-03-31", **parametros})
    )


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


def test_t_a6_api_sem_a_opcao_responde_400_com_a_mensagem_nova(client, cenario):
    _entrar(client, "gestor-norm")

    resposta = client.get(_url_api(cenario["empresa"], formato="ecd"))

    assert resposta.status_code == 400
    assert "normalizar" in str(resposta.json())
    assert "troque o caractere" not in str(resposta.json())


def test_t_a6_api_com_a_opcao_responde_200_e_informa_as_trocas(client, cenario):
    _entrar(client, "gestor-norm")

    resposta = client.get(_url_api(cenario["empresa"], formato="ecd", normalizar_texto="true"))

    assert resposta.status_code == 200
    assert resposta["X-DataLedger-Textos-Normalizados"] == "6"


def test_t_a6_tela_sem_a_opcao_recusa_com_a_mensagem_nova(client, cenario):
    _entrar(client, "gestor-norm")

    resposta = client.get(_url_tela("lancamentos_exportar", cenario["empresa"], formato="ecd"))

    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert "normalizar" in html
    assert "troque o caractere" not in html


def test_t_a6_tela_com_a_opcao_lista_cada_historico_trocado(client, cenario):
    _entrar(client, "gestor-norm")

    resposta = client.get(
        _url_tela(
            "lancamentos_exportar", cenario["empresa"], formato="ecd", normalizar_texto="true"
        )
    )

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Históricos trocados no arquivo" in html
    assert HISTORICO_COM_TRAVESSAO in html
    assert "Pagamento - parcela 1" in html


# --- M46: conciliação de saldos com lançamentos -------------------------------------------------


def test_m46_saldo_inflado_no_balancete_e_recusado_pela_conciliacao(cenario, monkeypatch):
    """M46: um balancete que infla débitos (e o saldo, para passar a conta por conta) não concilia.

    A exportação recusa com 'não conciliam', e nada é gerado. Sem a conciliação, o arquivo sairia.
    """
    original = nucleo.apurar_balancete

    def balancete_inflado(**kwargs):
        resultado = original(**kwargs)
        for linha in resultado["contas"]:
            if linha["analitica"] and linha["debitos"] != 0:
                ajuste = Decimal("1000.00")
                linha["debitos"] = linha["debitos"] + ajuste
                if linha["natureza"] == "devedora":
                    linha["saldo_final"] = linha["saldo_final"] + ajuste
                else:
                    linha["saldo_final"] = linha["saldo_final"] - ajuste
                break
        return resultado

    monkeypatch.setattr(nucleo, "apurar_balancete", balancete_inflado)

    with pytest.raises(ExportacaoRecusada, match="não conciliam"):
        exportar_lancamentos(
            empresa=cenario["empresa"],
            formato="ecd",
            data_inicial=INICIO,
            data_final=FIM,
            incluir_saldos=True,
            normalizar_texto=True,
        )


# --- M49: o download da tela recusa o cliente ----------------------------------------------------


def test_m49_cliente_nao_baixa_o_arquivo_de_lancamentos_pela_tela(client, cenario):
    """M49: o download da tela exige o papel que lê a contabilidade; o cliente recebe 403."""
    _entrar(client, "cliente-norm")

    resposta = client.get(
        _url_tela("lancamentos_exportar_arquivo", cenario["empresa"], formato="proprio")
    )

    assert resposta.status_code == 403
    assert resposta.get("Content-Disposition") is None


def test_m49_gestor_baixa_o_arquivo_pela_tela(client, cenario):
    """M49, controle: quem lê a contabilidade baixa o arquivo, com a disposição de anexo."""
    _entrar(client, "gestor-norm")

    resposta = client.get(
        _url_tela("lancamentos_exportar_arquivo", cenario["empresa"], formato="proprio")
    )

    assert resposta.status_code == 200
    assert "attachment" in resposta["Content-Disposition"]
