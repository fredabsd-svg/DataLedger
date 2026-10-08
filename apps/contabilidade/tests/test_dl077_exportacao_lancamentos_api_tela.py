"""DL-077, fatia 2: API e tela da exportação de lançamentos e saldos.

Chamadas reais pelo cliente HTTP, com sessão autenticada (o mesmo caminho do usuário). Dados
sintéticos. Cobre: permissão no servidor (leitura da contabilidade), isolamento entre escritórios
e empresas, livro-caixa recusado, parâmetros inválidos, recusa do N×M e das casas não declaradas,
o SHA-256 conferido (409 quando o arquivo mudou), a trilha `lancamentos.exportados` (só quando o
arquivo sai) e a moldura de acessibilidade da conferência.
"""

import re
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.intercambio.lancamentos import exportar_lancamentos
from apps.contabilidade.models import LancamentoContabil
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    CNPJ_DA_OUTRA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
    montar_cenario_de_referencia,
)
from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_pagina_acessivel
from apps.empresas.models import ModoEscrituracao
from apps.empresas.services import MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
INICIO = date(2026, 1, 1)
FIM = date(2026, 3, 31)
D = Decimal

pytestmark = pytest.mark.django_db


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


@pytest.fixture
def cenario(client):
    escritorio_a = criar_escritorio("Escritório Exp A", "33333333000133")
    escritorio_b = criar_escritorio("Escritório Exp B", "44444444000144")
    empresa = criar_empresa(
        escritorio=escritorio_a, razao_social="Empresa Exp Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    lancamentos = montar_cenario_de_referencia(empresa, contas)
    outra_do_b = criar_empresa(
        escritorio=escritorio_b,
        razao_social="Empresa de Outro Escritório",
        cnpj=CNPJ_DA_OUTRA_EMPRESA,
    )
    livro_caixa = criar_empresa(
        escritorio=escritorio_a, razao_social="Livro-caixa Ltda", cnpj="55555555000155"
    )
    livro_caixa.modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA
    livro_caixa.save()
    _usuario("gestor-exp", escritorio_a, Papel.GESTOR)
    _usuario("paralegal-exp", escritorio_a, Papel.PARALEGAL)
    _usuario("cliente-exp", escritorio_a, Papel.CLIENTE)
    _usuario("gestor-exp-b", escritorio_b, Papel.GESTOR)
    return {
        "empresa": empresa,
        "outra": outra_do_b,
        "livro_caixa": livro_caixa,
        "contas": contas,
        **lancamentos,
    }


def _api(empresa, **parametros):
    url = reverse("contabilidade:lancamentos-exportacao", args=[empresa.id])
    return url + ("?" + urlencode(parametros) if parametros else "")


def _tela(nome, empresa, **parametros):
    url = reverse(f"contabilidade_web:{nome}", args=[empresa.id])
    return url + ("?" + urlencode(parametros) if parametros else "")


def _parametros_padrao(**extra):
    return {"formato": "proprio", "inicio": "2026-01-01", "fim": "2026-03-31", **extra}


def _sha_direto(empresa, formato="proprio", **extra):
    return exportar_lancamentos(
        empresa=empresa,
        formato=formato,
        data_inicial=INICIO,
        data_final=FIM,
        **extra,
    ).sha256


# -----------------------------------------------------------------------------
# API
# -----------------------------------------------------------------------------


def test_api_entrega_o_arquivo_com_o_relatorio_nos_cabecalhos_e_grava_a_trilha(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_api(cenario["empresa"], **_parametros_padrao()))

    assert resposta.status_code == 200, resposta.content
    assert resposta["Content-Type"] == "text/plain; charset=utf-8"
    assert resposta["Content-Disposition"].startswith('attachment; filename="lancamentos-')
    assert resposta["X-DataLedger-Sha256"] == _sha_direto(cenario["empresa"])
    assert resposta["X-DataLedger-Lancamentos"] == "7"
    assert resposta["X-DataLedger-Partidas"] == "19"
    assert resposta["X-DataLedger-Soma-Debitos"] == "2880.00"
    assert resposta["X-DataLedger-Soma-Creditos"] == "2880.00"
    assert resposta["X-DataLedger-Omitidos"] == "0"
    assert "X-DataLedger-Avisos" not in resposta  # o formato próprio não tem aviso
    trilha = RegistroAuditoria.objects.get(acao="lancamentos.exportados")
    assert trilha.detalhes["sha256"] == resposta["X-DataLedger-Sha256"]
    assert trilha.detalhes["inicio"] == "2026-01-01" and trilha.detalhes["fim"] == "2026-03-31"
    assert trilha.detalhes["quantidade_lancamentos"] == 7
    assert trilha.usuario is not None and trilha.usuario.username == "gestor-exp"


def test_api_ecd_com_saldos_sai_em_latin_1_com_o_aviso_que_nao_e_a_ecd(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _api(
            cenario["empresa"],
            formato="ecd",
            inicio="2026-01-01",
            fim="2026-03-31",
            incluir_saldos="true",
        )
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta["Content-Type"] == "text/plain; charset=iso-8859-1"
    assert "nao e a ECD" in resposta["X-DataLedger-Avisos"]
    assert "registros-I200-I150-I155" in resposta["Content-Disposition"]
    assert resposta.content.decode("iso-8859-1").startswith("|I150|01012026|31012026|")


def test_api_com_sha_conferido_diferente_responde_409_e_nao_grava_trilha(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_api(cenario["empresa"], **_parametros_padrao(sha256="0" * 64)))

    assert resposta.status_code == 409, resposta.content
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_api_com_sha_conferido_igual_entrega_o_arquivo(client, cenario):
    _entrar(client, "gestor-exp")
    sha = _sha_direto(cenario["empresa"])

    resposta = client.get(_api(cenario["empresa"], **_parametros_padrao(sha256=sha)))

    assert resposta.status_code == 200
    assert resposta["X-DataLedger-Sha256"] == sha


@pytest.mark.parametrize(
    "parametros, mensagem",
    [
        ({"formato": "proprio", "fim": "2026-03-31"}, "intervalo é obrigatório"),
        ({"formato": "proprio", "inicio": "2026-03-31", "fim": "2026-01-01"}, "posterior"),
        ({"formato": "proprio", "inicio": "2026-01-01", "fim": "2027-02-01"}, "366"),
        ({"formato": "proprio", "inicio": "31/03/2026", "fim": "2026-03-31"}, "data"),
        (
            {
                "formato": "proprio",
                "inicio": "2026-01-01",
                "fim": "2026-03-31",
                "incluir_saldos": "talvez",
            },
            "true ou false",
        ),
        (
            {
                "formato": "proprio",
                "inicio": "2026-01-01",
                "fim": "2026-03-31",
                "incluir_saldos": "true",
            },
            "existem só no leiaute da ECD",
        ),
        ({"formato": "excel", "inicio": "2026-01-01", "fim": "2026-03-31"}, "não existe"),
        (
            {"formato": "proprio", "inicio": "2026-01-01", "fim": "2026-03-31", "campo_solto": "1"},
            "campo_solto",
        ),
    ],
)
def test_api_recusa_parametros_invalidos_com_400(client, cenario, parametros, mensagem):
    _entrar(client, "gestor-exp")

    resposta = client.get(_api(cenario["empresa"], **parametros))

    assert resposta.status_code == 400, resposta.content
    assert mensagem in resposta.content.decode()
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_api_referencia_com_nm_recusa_400_listando_o_lancamento(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _api(cenario["empresa"], formato="referencia", inicio="2026-01-01", fim="2026-03-31")
    )

    assert resposta.status_code == 400
    assert f"lançamento {cenario['l5'].pk} (15/03/2026" in resposta.content.decode()


def test_api_referencia_com_casas_declaradas_sai_200_com_valor_em_virgula(client, cenario):
    """DL-077 fatia 3: `CASAS_DECIMAIS_DO_VALOR_6100` = 2, decidido pelo arquiteto. Antes, a
    API recusava (400) por falta de casas. Agora o arquivo sai, com o valor em vírgula."""
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _api(
            cenario["empresa"],
            formato="referencia",
            inicio="2026-01-01",
            fim="2026-03-31",
            omitir_nao_representaveis="true",
        )
    )

    assert resposta.status_code == 200
    conteudo = resposta.content.decode("iso-8859-1")
    assert conteudo.startswith("|0000|77777777000177|\r\n")
    assert "|6100|10/01/2026|3|12|1000,00||Aporte de capital||||" in conteudo
    assert RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_api_paralegal_le_e_cliente_nao_passa(client, cenario):
    _entrar(client, "paralegal-exp")
    assert client.get(_api(cenario["empresa"], **_parametros_padrao())).status_code == 200

    client.logout()
    _entrar(client, "cliente-exp")
    assert client.get(_api(cenario["empresa"], **_parametros_padrao())).status_code == 403


def test_api_outro_escritorio_nao_ve_a_empresa(client, cenario):
    _entrar(client, "gestor-exp-b")

    resposta = client.get(_api(cenario["empresa"], **_parametros_padrao()))

    assert resposta.status_code == 404
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_api_livro_caixa_recusada_com_a_mensagem_do_dl038(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_api(cenario["livro_caixa"], **_parametros_padrao()))

    assert resposta.status_code == 400
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()


def test_api_nao_grava_lancamento_nem_altera_o_banco(client, cenario):
    _entrar(client, "gestor-exp")
    antes = LancamentoContabil.objects.count()

    client.get(_api(cenario["empresa"], **_parametros_padrao()))

    assert LancamentoContabil.objects.count() == antes


# -----------------------------------------------------------------------------
# Tela
# -----------------------------------------------------------------------------


def test_tela_formulario_sem_formato_nao_gera_nada_nem_trilha(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_tela("lancamentos_exportar", cenario["empresa"]))

    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Exportar lançamentos" in html
    assert "Conferência do arquivo" not in html
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_tela_mostra_o_aviso_que_nao_e_a_ecd_em_qualquer_escolha(client, cenario):
    _entrar(client, "gestor-exp")

    html = client.get(_tela("lancamentos_exportar", cenario["empresa"])).content.decode()

    assert "Este arquivo não é a ECD" in html
    assert "Não substitui a escrituração contábil digital" in html


def test_tela_conferencia_mostra_relatorio_com_sha_somas_e_link_do_download(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_tela("lancamentos_exportar", cenario["empresa"], **_parametros_padrao()))

    assert resposta.status_code == 200, resposta.content
    html = resposta.content.decode()
    sha = _sha_direto(cenario["empresa"])
    assert "Conferência do arquivo" in html
    assert sha in html
    assert "2.880,00" in html  # soma dos débitos e dos créditos, em pt-BR
    assert "Débitos e créditos conferem" in html
    assert "gestor-exp" in html  # autor do relatório: o nome de usuário, sem o e-mail
    assert "Baixar o arquivo" in html
    assert f"sha256={sha}" in html
    assert_pagina_acessivel(html)
    # A conferência não grava: nada entra na trilha antes do download.
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_tela_conferencia_de_referencia_com_nm_mostra_o_erro_e_nao_o_download(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _tela(
            "lancamentos_exportar",
            cenario["empresa"],
            formato="referencia",
            inicio="2026-01-01",
            fim="2026-03-31",
        )
    )

    assert resposta.status_code == 400
    html = resposta.content.decode()
    assert f"lançamento {cenario['l5'].pk}" in html
    # Sem conferência, não há link de download: o texto "Baixar o arquivo" só aparece no
    # bloco da conferência, e o link para a rota de arquivo não existe na página.
    assert "/lancamentos/exportar/arquivo/" not in html
    assert "Conferência do arquivo" not in html


def test_tela_download_com_sha_conferido_entrega_o_arquivo_e_grava_a_trilha(client, cenario):
    _entrar(client, "gestor-exp")
    sha = _sha_direto(cenario["empresa"])

    resposta = client.get(
        _tela("lancamentos_exportar_arquivo", cenario["empresa"], **_parametros_padrao(sha256=sha))
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta["Content-Type"] == "text/plain; charset=utf-8"
    assert resposta["Content-Disposition"].startswith('attachment; filename="lancamentos-')
    assert resposta.content.decode("utf-8").startswith("numero;data;historico;conta;lado;valor\r\n")
    trilha = RegistroAuditoria.objects.get(acao="lancamentos.exportados")
    assert trilha.detalhes["sha256"] == sha


def test_tela_download_com_sha_desatualizado_responde_409_com_a_mensagem(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _tela(
            "lancamentos_exportar_arquivo",
            cenario["empresa"],
            **_parametros_padrao(sha256="f" * 64),
        )
    )

    assert resposta.status_code == 409
    assert "mudaram desde a conferência" in resposta.content.decode()
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_tela_download_sem_formato_pede_a_escolha(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(_tela("lancamentos_exportar_arquivo", cenario["empresa"]))

    assert resposta.status_code == 400
    assert "Escolha o formato" in resposta.content.decode()


def test_tela_parametro_que_nao_e_do_formulario_e_recusado(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _tela("lancamentos_exportar", cenario["empresa"], **_parametros_padrao(campo_inventado="x"))
    )

    assert resposta.status_code == 400


def test_tela_saldos_so_na_ecd(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _tela(
            "lancamentos_exportar",
            cenario["empresa"],
            **_parametros_padrao(incluir_saldos="true"),
        )
    )

    assert resposta.status_code == 400
    assert "existem só no leiaute da ECD" in resposta.content.decode()


def test_tela_cliente_e_outro_escritorio_sao_recusados(client, cenario):
    _entrar(client, "cliente-exp")
    assert client.get(_tela("lancamentos_exportar", cenario["empresa"])).status_code == 403

    client.logout()
    _entrar(client, "gestor-exp-b")
    assert client.get(_tela("lancamentos_exportar", cenario["empresa"])).status_code == 404
    assert (
        client.get(
            _tela("lancamentos_exportar_arquivo", cenario["empresa"], **_parametros_padrao())
        ).status_code
        == 404
    )


def test_tela_livro_caixa_e_recusada(client, cenario):
    _entrar(client, "gestor-exp")

    resposta = client.get(
        _tela("lancamentos_exportar", cenario["livro_caixa"], **_parametros_padrao())
    )

    assert resposta.status_code != 200
    assert MENSAGEM_RECUSA_CONTABILIDADE_LIVRO_CAIXA in resposta.content.decode()
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.exportados").exists()


def test_diario_tem_o_link_para_exportar_lancamentos(client, cenario):
    _entrar(client, "gestor-exp")

    html = client.get(
        reverse("contabilidade_web:diario", args=[cenario["empresa"].id])
    ).content.decode()

    assert reverse("contabilidade_web:lancamentos_exportar", args=[cenario["empresa"].id]) in html
    assert "Exportar lançamentos" in html


def test_tela_conferencia_tem_a_moldura_de_acessibilidade(client, cenario):
    _entrar(client, "gestor-exp")

    html = client.get(
        _tela("lancamentos_exportar", cenario["empresa"], **_parametros_padrao())
    ).content.decode()

    assert_pagina_acessivel(html)
    assert re.search(r"<h2[^>]*>Conferência do arquivo</h2>", html)
