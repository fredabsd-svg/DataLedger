"""BL-149 / achado R6-2 da auditoria DL-017 rodada 6: a política dos cinco
dicionários mora num lugar só (`apps.core.requisicao`), e este arquivo é o
teste do JULGADOR — não das superfícies.

Cada superfície tem o seu próprio teste, porque cada uma responde de um jeito
diferente ao MESMO veredito (a tela re-renderiza o formulário com 400, a API
devolve 400 em JSON): `apps/contabilidade/tests/test_dl019_politica_api.py`,
`apps/empresas/tests/test_dl019_politica_api.py`,
`apps/tenancy/tests/test_dl019_politica.py`.

Os testes usam `RequestFactory` — `HttpRequest` de verdade, com `GET`,
`POST`, `FILES`, `META` e `headers` reais — e não um objeto de mentira com os
atributos que o módulo espera: um dublê concordaria com a implementação por
construção, inclusive quando ela estivesse errada sobre onde o Django guarda
cada coisa.
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

from apps.core.requisicao import (
    DICIONARIO_ARQUIVO,
    DICIONARIO_CABECALHO,
    DICIONARIO_CORPO,
    DICIONARIO_QUERYSTRING,
    ORDEM_DE_AVALIACAO,
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_campos_nao_contratados,
    recusar_dado_nao_contratado,
)

CONTRATO_DA_TELA = ContratoDeRequisicao(
    campos={"codigo", "nome"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta",
)


@pytest.fixture
def fabrica():
    return RequestFactory()


def test_requisicao_dentro_do_contrato_nao_levanta(fabrica):
    requisicao = fabrica.post("/qualquer/", {"codigo": "1", "nome": "Caixa"})

    assert recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA) is None


def test_arquivo_e_recusado_nomeando_a_chave(fabrica):
    """O caso medido pelo auditor: `conta_pai` enviado como ARQUIVO gravava a
    conta na RAIZ do plano, com 302 de sucesso e sem uma palavra."""
    requisicao = fabrica.post(
        "/qualquer/",
        {
            "codigo": "1",
            "nome": "Caixa",
            "conta_pai": SimpleUploadedFile("pai.txt", b"1"),
        },
    )

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_ARQUIVO
    assert erro.value.chaves == ("conta_pai",)
    assert "conta_pai" in erro.value.mensagem
    # A razão é a frase SEM as chaves: é o que permite à tela montar a
    # própria mensagem sem repetir a redação deste módulo.
    assert "conta_pai" not in erro.value.razao


def test_querystring_em_post_e_recusada_nomeando_os_parametros(fabrica):
    requisicao = fabrica.post(
        "/qualquer/?utm_source=nada&xpto=1", {"codigo": "1", "nome": "Caixa"}
    )

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_QUERYSTRING
    # Ordenadas: mensagem determinística entre execuções.
    assert erro.value.chaves == ("utm_source", "xpto")


def test_cabecalho_declarado_como_ignorado_e_recusado(fabrica):
    requisicao = fabrica.post(
        "/qualquer/", {"codigo": "1", "nome": "Caixa"}, headers={"idempotency-key": "abc"}
    )

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_CABECALHO
    assert erro.value.chaves == ("Idempotency-Key",)


def test_cabecalho_nao_declarado_continua_passando(fabrica):
    """Controle que impede a correção óbvia e errada: recusar "todo cabeçalho
    não contratado" quebraria qualquer navegador — `Cookie`, `Accept` e
    `User-Agent` chegam sempre e são legítimos. A recusa é por lista
    NOMEADA."""
    requisicao = fabrica.post(
        "/qualquer/",
        {"codigo": "1", "nome": "Caixa"},
        headers={"user-agent": "navegador", "accept-language": "pt-BR"},
    )

    assert recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA) is None


def test_campo_desconhecido_no_corpo_e_recusado_com_os_campos_aceitos(fabrica):
    requisicao = fabrica.post(
        "/qualquer/", {"codigo": "1", "nome": "Caixa", "zzz": "1", "empresa": "999"}
    )

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_CORPO
    assert erro.value.chaves == ("empresa", "zzz")
    assert "no cadastro de conta" in erro.value.mensagem
    assert "codigo, nome" in erro.value.mensagem


def test_ordem_de_avaliacao_e_a_declarada(fabrica):
    """A mensagem que o usuário vê depende de QUAL violação vem primeiro, e a
    tela tem teste em cima desse texto: com os quatro dicionários violados ao
    mesmo tempo, o veredito é o do arquivo — o primeiro de
    `ORDEM_DE_AVALIACAO`."""
    assert ORDEM_DE_AVALIACAO == (
        DICIONARIO_ARQUIVO,
        DICIONARIO_QUERYSTRING,
        DICIONARIO_CABECALHO,
        DICIONARIO_CORPO,
    )

    requisicao = fabrica.post(
        "/qualquer/?xpto=1",
        {"codigo": "1", "nome": "Caixa", "zzz": "1", "arq": SimpleUploadedFile("a.txt", b"1")},
        headers={"idempotency-key": "abc"},
    )

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_ARQUIVO


def test_contrato_que_aceita_arquivo_e_querystring_nao_recusa_nenhum_dos_dois(fabrica):
    contrato = ContratoDeRequisicao(
        campos={"codigo"}, aceita_arquivo=True, aceita_querystring=True
    )
    requisicao = fabrica.post(
        "/qualquer/?pagina=2", {"codigo": "1", "anexo": SimpleUploadedFile("a.txt", b"1")}
    )

    # `anexo` chega em `FILES` e NÃO em `POST` num `HttpRequest`, então um
    # contrato que aceita arquivo não precisa declará-lo como campo.
    assert recusar_dado_nao_contratado(requisicao, contrato) is None


def test_contrato_sem_campos_declarados_nao_julga_o_corpo(fabrica):
    """`campos=None` é "este contrato não julga o corpo" — diferente de
    `frozenset()`, que é "nenhum campo é aceito". A distinção existe porque
    uma rota de ação (o estorno) precisa da segunda, e não da primeira."""
    requisicao = fabrica.post("/qualquer/", {"qualquer_coisa": "1"})

    assert recusar_dado_nao_contratado(requisicao, ContratoDeRequisicao()) is None

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(
            requisicao, ContratoDeRequisicao(campos=frozenset(), contexto="nesta ação")
        )
    assert erro.value.chaves == ("qualquer_coisa",)
    assert "nenhum" in erro.value.mensagem


def test_corpo_que_nao_e_dicionario_nao_levanta_aqui():
    """Uma lista no topo do JSON não é "campo desconhecido": outra checagem,
    mais adiante, recusa estrutura errada com mensagem melhor. Este módulo
    não pode transformar isso num erro de chave sem sentido."""
    recusar_campos_nao_contratados(["a", "b"], {"data"}, contexto="no lançamento")
    recusar_campos_nao_contratados(None, {"data"})


def test_chaves_sao_tupla_ordenada_e_acessiveis_sem_ler_a_mensagem():
    """Contrato acordado com o `especialista-frontend`: as chaves ficam
    acessíveis SEPARADAMENTE da mensagem, porque cada superfície monta a sua
    própria frase."""
    with pytest.raises(DadoNaoContratado) as erro:
        recusar_campos_nao_contratados({"c": 1, "a": 1, "b": 1}, {"a"})

    assert erro.value.chaves == ("b", "c")
    assert isinstance(erro.value.chaves, tuple)
    assert str(erro.value) == erro.value.mensagem


def test_arquivo_em_requisicao_multipart_com_stream_real(fabrica):
    """Mesma recusa quando o arquivo chega por `multipart/form-data` montado
    à mão (o caminho do auditor), não só pelo atalho do `RequestFactory`."""
    arquivo = io.BytesIO(b"conteudo")
    arquivo.name = "pai.txt"
    requisicao = fabrica.post("/qualquer/", {"codigo": "1", "nome": "C", "conta_pai": arquivo})

    with pytest.raises(DadoNaoContratado) as erro:
        recusar_dado_nao_contratado(requisicao, CONTRATO_DA_TELA)

    assert erro.value.dicionario == DICIONARIO_ARQUIVO
