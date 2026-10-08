"""API da importação de lançamentos com área de conferência (DL-077, fatia 3, frente A).

Chamadas reais pelo cliente HTTP, com sessão autenticada. Dados sintéticos. Cobre: permissão no
servidor (escriturar, ler, cliente recusado), isolamento de empresa (404), o envio do arquivo, as
respostas de conflito (409) e de erro (400), o aceite de avisos, a efetivação por política, o
descarte com motivo, o de-para por empresa, o limite de tamanho (413) e a recusa do prefixo
`importacao:` na rota de lançamento manual.
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade import views as contabilidade_views
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
from apps.empresas.models import ModoEscrituracao
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

SENHA = "senha-forte-123"
pytestmark = pytest.mark.django_db

CABECALHO = "numero;data;historico;conta;lado;valor\r\n"


def _arquivo(*linhas):
    return (CABECALHO + "".join(linha + "\r\n" for linha in linhas)).encode("utf-8")


def _lancamento(numero, data="2026-03-10", valor_c="100.00"):
    return [
        f"{numero};{data};Compra;1.1.1;D;100.00",
        f"{numero};{data};Compra;2.1;C;{valor_c}",
    ]


def _usuario(username, escritorio, papel):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _entrar(client, username):
    assert client.login(username=username, password=SENHA)


def _url(nome, empresa, *args):
    return reverse(f"contabilidade:{nome}", args=[empresa.id, *args])


def _enviar(client, empresa, *linhas, formato="proprio", nome="lanc.txt"):
    return client.post(
        _url("lancamentos-importacao", empresa),
        {
            "arquivo": SimpleUploadedFile(nome, _arquivo(*linhas), content_type="text/plain"),
            "formato": formato,
        },
    )


@pytest.fixture
def cenario(client):
    escritorio_a = criar_escritorio("Escritório Imp A", "66666666000166")
    escritorio_b = criar_escritorio("Escritório Imp B", "77777777000177")
    empresa = criar_empresa(
        escritorio=escritorio_a, razao_social="Empresa Imp Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    outra = criar_empresa(
        escritorio=escritorio_b, razao_social="Outra Imp Ltda", cnpj="88888888000188"
    )
    contas_outra = criar_plano(outra)
    _usuario("analista-imp", escritorio_a, Papel.ANALISTA)
    _usuario("gestor-imp", escritorio_a, Papel.GESTOR)
    _usuario("paralegal-imp", escritorio_a, Papel.PARALEGAL)
    _usuario("cliente-imp", escritorio_a, Papel.CLIENTE)
    _usuario("gestor-b-imp", escritorio_b, Papel.GESTOR)
    return {
        "empresa": empresa,
        "contas": contas,
        "outra": outra,
        "contas_outra": contas_outra,
    }


# ---------------------------------------------------------------------------
# Permissões no servidor
# ---------------------------------------------------------------------------


def test_analista_envia_arquivo_e_fica_em_conferencia_sem_lancamento(client, cenario):
    _entrar(client, "analista-imp")

    resposta = _enviar(client, cenario["empresa"], *_lancamento(7))

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["estado"] == "em_conferencia"
    assert corpo["quantidade_lancamentos"] == 1
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_paralegal_le_mas_nao_envia_nem_efetiva(client, cenario):
    _entrar(client, "analista-imp")
    importacao_id = _enviar(client, cenario["empresa"], *_lancamento(7)).json()["id"]
    client.logout()

    _entrar(client, "paralegal-imp")
    assert client.get(_url("lancamentos-importacao", cenario["empresa"])).status_code == 200
    assert (
        client.get(
            _url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id)
        ).status_code
        == 200
    )
    assert _enviar(client, cenario["empresa"], *_lancamento(8)).status_code == 403
    assert (
        client.post(
            _url("lancamentos-importacao-efetivar", cenario["empresa"], importacao_id),
            {},
            content_type="application/json",
        ).status_code
        == 403
    )
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0


def test_cliente_nao_le_nem_envia(client, cenario):
    _entrar(client, "cliente-imp")

    assert client.get(_url("lancamentos-importacao", cenario["empresa"])).status_code == 403
    assert _enviar(client, cenario["empresa"], *_lancamento(7)).status_code == 403


def test_empresa_de_outro_escritorio_responde_404_e_nao_vaza_a_importacao(client, cenario):
    _entrar(client, "analista-imp")
    importacao_id = _enviar(client, cenario["empresa"], *_lancamento(7)).json()["id"]
    client.logout()

    _entrar(client, "gestor-b-imp")
    assert client.get(_url("lancamentos-importacao", cenario["empresa"])).status_code == 404
    assert (
        client.get(
            _url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id)
        ).status_code
        == 404
    )


def test_importacao_de_outra_empresa_do_mesmo_escritorio_responde_404(client, cenario):
    """Mesmo escritório, outra empresa: o id de uma não abre pela URL da outra."""
    irma = criar_empresa(
        escritorio=cenario["empresa"].escritorio,
        razao_social="Irmã Imp Ltda",
        cnpj="99999999000199",
    )
    criar_plano(irma)
    _entrar(client, "analista-imp")
    importacao_id = _enviar(client, irma, *_lancamento(7)).json()["id"]

    resposta = client.get(_url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id))

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Envio, conflito e limite
# ---------------------------------------------------------------------------


def test_arquivo_repetido_responde_409_citando_a_importacao_existente(client, cenario):
    _entrar(client, "analista-imp")
    primeira = _enviar(client, cenario["empresa"], *_lancamento(7)).json()

    resposta = _enviar(client, cenario["empresa"], *_lancamento(7))

    assert resposta.status_code == 409
    assert resposta.json()["importacao_id"] == primeira["id"]


def test_arquivo_sem_campo_arquivo_responde_400_no_campo_arquivo(client, cenario):
    _entrar(client, "analista-imp")

    resposta = client.post(
        _url("lancamentos-importacao", cenario["empresa"]), {"formato": "proprio"}
    )

    assert resposta.status_code == 400
    assert "arquivo" in resposta.json()


def test_campo_que_a_rota_nao_le_e_recusado(client, cenario):
    _entrar(client, "analista-imp")

    resposta = client.post(
        _url("lancamentos-importacao", cenario["empresa"]) + "?sobra=1",
        {
            "arquivo": SimpleUploadedFile("x.txt", _arquivo(*_lancamento(7))),
            "formato": "proprio",
        },
    )

    assert resposta.status_code == 400


def test_arquivo_acima_do_limite_responde_413(client, cenario, monkeypatch):
    monkeypatch.setattr(contabilidade_views, "TAMANHO_MAXIMO_ARQUIVO_BYTES", 10)
    _entrar(client, "analista-imp")

    resposta = _enviar(client, cenario["empresa"], *_lancamento(7))

    assert resposta.status_code == 413


def test_formato_do_sistema_de_referencia_entra_na_conferencia(client, cenario):
    _entrar(client, "analista-imp")
    arquivo = (
        "|0000|"
        + CNPJ_DA_EMPRESA
        + "|\r\n|6000|X||||\r\n|6100|10/03/2026|3|12|100,00||Compra||||\r\n"
    )

    resposta = client.post(
        _url("lancamentos-importacao", cenario["empresa"]),
        {
            "arquivo": SimpleUploadedFile("r.txt", arquivo.encode("iso-8859-1")),
            "formato": "referencia",
        },
    )

    assert resposta.status_code == 201
    assert resposta.json()["quantidade_com_erro"] == 1  # as contas 3 e 12 não têm de-para ainda


# ---------------------------------------------------------------------------
# Detalhe, filtros e paginação
# ---------------------------------------------------------------------------


def test_detalhe_pagina_e_filtra_por_erros(client, cenario):
    _entrar(client, "analista-imp")
    arquivo = [
        *_lancamento(1, data="2026-03-10"),
        "2;2026-03-11;Ruim;1.1.1;D;100.00",
        "2;2026-03-11;Ruim;2.1;C;90.00",
        *_lancamento(3, data="2026-03-12"),
    ]
    importacao_id = _enviar(client, cenario["empresa"], *arquivo).json()["id"]

    tudo = client.get(
        _url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id) + "?tamanho=2"
    ).json()
    erros = client.get(
        _url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id) + "?filtro=erros"
    ).json()

    assert tudo["paginacao"]["total"] == 3
    assert len(tudo["lancamentos"]) == 2
    assert [linha_["numero_origem"] for linha_ in erros["lancamentos"]] == ["2"]


def test_detalhe_recusa_filtro_desconhecido(client, cenario):
    _entrar(client, "analista-imp")
    importacao_id = _enviar(client, cenario["empresa"], *_lancamento(1)).json()["id"]

    resposta = client.get(
        _url("lancamentos-importacao-detalhe", cenario["empresa"], importacao_id)
        + "?filtro=tudo_junto"
    )

    assert resposta.status_code == 400


# ---------------------------------------------------------------------------
# Ações: efetivar, avisos, descarte, reconferir
# ---------------------------------------------------------------------------


def test_efetivar_tudo_ou_nada_com_erro_responde_400_com_ocorrencias_e_nada_grava(client, cenario):
    _entrar(client, "analista-imp")
    importacao_id = _enviar(
        client,
        cenario["empresa"],
        *_lancamento(1),
        "2;2026-03-11;Ruim;1.1.1;D;100.00",
        "2;2026-03-11;Ruim;2.1;C;90.00",
    ).json()["id"]

    resposta = client.post(
        _url("lancamentos-importacao-efetivar", cenario["empresa"], importacao_id),
        data=json.dumps({"politica": "tudo_ou_nada"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert resposta.json()["ocorrencias"]
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0


def _aceitar_o_arquivo(client, empresa, importacao_id):
    """A11: o arquivo sem empresa declarada só é efetivado depois do aceite do aviso do arquivo."""
    resposta = client.post(
        _url("lancamentos-importacao-avisos", empresa, importacao_id),
        data=json.dumps({"numeros": [], "aceitar_arquivo": True}),
        content_type="application/json",
    )
    assert resposta.status_code == 200, resposta.content


def test_efetivar_so_validos_e_recusado_pela_suspensao_e_nada_e_gravado(client, cenario):
    """Antes (DL-077 fatia 3) a política gravava o lançamento 1. Agora está suspensa (BL-676)."""
    _entrar(client, "analista-imp")
    importacao_id = _enviar(
        client,
        cenario["empresa"],
        *_lancamento(1),
        "2;2026-03-11;Ruim;1.1.1;D;100.00",
        "2;2026-03-11;Ruim;2.1;C;90.00",
    ).json()["id"]

    _aceitar_o_arquivo(client, cenario["empresa"], importacao_id)
    resposta = client.post(
        _url("lancamentos-importacao-efetivar", cenario["empresa"], importacao_id),
        data=json.dumps({"politica": "so_validos"}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert "suspensa" in resposta.json()["detail"]
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 0
    assert not RegistroAuditoria.objects.filter(acao="lancamentos.importacao.efetivada").exists()


def test_efetivar_duas_vezes_responde_409_e_nao_duplica(client, cenario):
    _entrar(client, "analista-imp")
    importacao_id = _enviar(client, cenario["empresa"], *_lancamento(1)).json()["id"]
    url = _url("lancamentos-importacao-efetivar", cenario["empresa"], importacao_id)
    _aceitar_o_arquivo(client, cenario["empresa"], importacao_id)

    primeira = client.post(url, data="{}", content_type="application/json")
    segunda = client.post(url, data="{}", content_type="application/json")

    assert primeira.status_code == 200
    assert segunda.status_code == 409
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == 1


def test_aceitar_avisos_e_descartar_com_motivo(client, cenario):
    _entrar(client, "analista-imp")
    arquivo = [
        "7;2026-03-10;Compra A;1.1.1;D;100.00",
        "7;2026-03-10;Compra B;2.1;C;100.00",
    ]
    importacao_id = _enviar(client, cenario["empresa"], *arquivo).json()["id"]

    semaviso = client.post(
        _url("lancamentos-importacao-avisos", cenario["empresa"], importacao_id),
        data=json.dumps({"numeros": ["9"]}),
        content_type="application/json",
    )
    aceito = client.post(
        _url("lancamentos-importacao-avisos", cenario["empresa"], importacao_id),
        data=json.dumps({"numeros": ["7"]}),
        content_type="application/json",
    )
    sem_motivo = client.post(
        _url("lancamentos-importacao-descartar", cenario["empresa"], importacao_id),
        data=json.dumps({"motivo": "  "}),
        content_type="application/json",
    )
    descartada = client.post(
        _url("lancamentos-importacao-descartar", cenario["empresa"], importacao_id),
        data=json.dumps({"motivo": "arquivo de teste"}),
        content_type="application/json",
    )

    assert semaviso.status_code == 400
    assert aceito.status_code == 200 and aceito.json() == {"aceitos": 1}
    assert sem_motivo.status_code == 400
    assert descartada.status_code == 200
    assert descartada.json()["estado"] == EstadoImportacaoLancamentos.DESCARTADA


def test_reconferir_depois_de_definir_de_para_libera_a_conta(client, cenario):
    _entrar(client, "analista-imp")
    arquivo = (
        "|0000|"
        + CNPJ_DA_EMPRESA
        + "|\r\n|6000|X||||\r\n|6100|10/03/2026|3|12|100,00||Compra||||\r\n"
    )
    importacao_id = client.post(
        _url("lancamentos-importacao", cenario["empresa"]),
        {
            "arquivo": SimpleUploadedFile("r.txt", arquivo.encode("iso-8859-1")),
            "formato": "referencia",
        },
    ).json()["id"]
    contas = cenario["contas"]

    depara = client.post(
        _url("lancamentos-importacao-de-para", cenario["empresa"]),
        data=json.dumps(
            {"formato": "referencia", "codigo_origem": "3", "conta": contas["1.1.1"].id}
        ),
        content_type="application/json",
    )
    client.post(
        _url("lancamentos-importacao-de-para", cenario["empresa"]),
        data=json.dumps(
            {"formato": "referencia", "codigo_origem": "12", "conta": contas["2.1"].id}
        ),
        content_type="application/json",
    )
    reconferida = client.post(
        _url("lancamentos-importacao-reconferir", cenario["empresa"], importacao_id),
        data="{}",
        content_type="application/json",
    )

    assert depara.status_code == 201 or depara.status_code == 200
    assert reconferida.status_code == 200
    assert reconferida.json()["quantidade_com_erro"] == 0


def test_de_para_lista_so_a_empresa_pedida_e_nao_aceita_conta_alheia(client, cenario):
    _entrar(client, "analista-imp")
    contas_outra = cenario["contas_outra"]

    alheia = client.post(
        _url("lancamentos-importacao-de-para", cenario["empresa"]),
        data=json.dumps(
            {"formato": "referencia", "codigo_origem": "3", "conta": contas_outra["1.1.1"].id}
        ),
        content_type="application/json",
    )

    assert alheia.status_code == 404
    assert not DeParaConta.objects.filter(empresa=cenario["empresa"]).exists()
    listagem = client.get(_url("lancamentos-importacao-de-para", cenario["empresa"]))
    assert listagem.status_code == 200
    assert listagem.json() == {"de_para": []}


# ---------------------------------------------------------------------------
# Prefixo reservado na rota de lançamento MANUAL (a mesma porta de criar_lancamento)
# ---------------------------------------------------------------------------


def test_rota_de_lancamento_manual_recusa_a_chave_com_prefixo_da_importacao(client, cenario):
    _entrar(client, "gestor-imp")
    contas = cenario["contas"]

    resposta = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2026-03-10",
            "historico": "Forjado pela API",
            "itens": [
                {"conta": contas["1.1.1"].id, "tipo": "debito", "valor": "10.00"},
                {"conta": contas["2.1"].id, "tipo": "credito", "valor": "10.00"},
            ],
        },
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="importacao:0000:7",
    )

    assert resposta.status_code == 400
    assert (
        "importacao:" in resposta.json()[0]
        if isinstance(resposta.json(), list)
        else "importacao:" in str(resposta.json())
    )
    assert not LancamentoContabil.objects.filter(empresa=cenario["empresa"]).exists()


def test_importacao_de_empresa_em_livro_caixa_e_recusada(client, cenario):
    _entrar(client, "analista-imp")
    cenario["empresa"].modo_escrituracao = ModoEscrituracao.LIVRO_CAIXA
    cenario["empresa"].save(update_fields=["modo_escrituracao"])

    resposta = _enviar(client, cenario["empresa"], *_lancamento(7))

    assert resposta.status_code == 400
    assert not ImportacaoLancamentos.objects.filter(empresa=cenario["empresa"]).exists()
