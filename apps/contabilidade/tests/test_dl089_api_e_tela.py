"""DL-089 (BL-72), API e tela: o lançamento mostra a origem e o link ao documento; o Diário
filtra por origem; a API não aceita origem do cliente.

Critério 1 (os caminhos atuais) e o contrato de superfície: a origem é decidida pelo servidor,
então o POST que a envia é recusado (400), e nada é gravado. Razão NÃO recebe filtro de origem:
ver `listar_diario` e o relatório da etapa. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.intercambio import importacao_lancamentos as servico
from apps.contabilidade.models import (
    LancamentoContabil,
    OrigemLancamento,
    TipoDocumentoOrigem,
    TipoPartida,
)
from apps.contabilidade.services import criar_lancamento
from apps.contabilidade.tests.cenario_dl077_exportacao import (
    CNPJ_DA_EMPRESA,
    criar_empresa,
    criar_escritorio,
    criar_plano,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
LOTE = TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS

CONTEUDO_PROPRIO = (
    "numero;data;historico;conta;lado;valor\r\n"
    "1;2026-03-10;Compra importada sintética;1.1.1;D;100.00\r\n"
    "1;2026-03-10;Compra importada sintética;5.1;C;100.00\r\n"
).encode("utf-8")


@pytest.fixture
def cenario(client):
    escritorio = criar_escritorio("Escritório DL-089 API e tela", "89897000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 API e Tela Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    contas = criar_plano(empresa)
    usuario = get_user_model().objects.create_user(
        username="gestor-dl089-tela", email="gestor-dl089-tela@escritorio.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    assert client.login(username="gestor-dl089-tela", password=SENHA)
    return {"escritorio": escritorio, "empresa": empresa, "contas": contas}


def _itens(cenario, valor="100.00"):
    contas = cenario["contas"]
    return [
        {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal(valor)},
        {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal(valor)},
    ]


def _manual(cenario, historico="Digitado (sintético)", data=date(2026, 3, 10)):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=data,
        historico=historico,
        itens=_itens(cenario, "10.00"),
    )


def _lote_recebido(cenario):
    """Importação recebida de verdade (DL-077), efetivada: gera lançamentos `importacao`."""
    importacao = servico.receber(
        empresa=cenario["empresa"],
        formato="proprio",
        conteudo=CONTEUDO_PROPRIO,
        nome_arquivo="sintetico-dl089-tela.txt",
        usuario=None,
    )
    if importacao.exige_aceite_do_arquivo and not importacao.aceite_do_arquivo:
        servico.aceitar_avisos(importacao, [], aceitar_arquivo=True)
    servico.efetivar(importacao, politica=servico.TUDO_OU_NADA, usuario=None)
    return importacao


def _escrita_fiscal_reservada(cenario):
    """Lançamento com a origem RESERVADA `escrita_fiscal` (sem produtor hoje): para a tela
    mostrar tipo e identificador de documento que ainda não tem tela."""
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 12),
        historico="Escrita fiscal reservada (sintética)",
        itens=_itens(cenario, "30.00"),
        origem=OrigemLancamento.ESCRITA_FISCAL,
        documento_origem=(
            TipoDocumentoOrigem.ESCRITURACAO_NFE,
            "35261099999999999999550010000000011000000011",
        ),
    )


# ---------------------------------------------------------------------------
# API: a saída mostra a origem e o documento
# ---------------------------------------------------------------------------


def test_api_lista_lancamentos_com_origem_e_documento(client, cenario):
    manual = _manual(cenario)
    importacao = _lote_recebido(cenario)
    automatico = LancamentoContabil.objects.get(
        empresa=cenario["empresa"], origem=OrigemLancamento.IMPORTACAO
    )

    response = client.get(reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]))

    assert response.status_code == 200
    por_id = {item["id"]: item for item in response.json()}
    assert por_id[manual.pk]["origem"] == OrigemLancamento.MANUAL
    assert por_id[manual.pk]["documento_de_origem"] is None
    assert por_id[automatico.pk]["origem"] == OrigemLancamento.IMPORTACAO
    assert por_id[automatico.pk]["documento_de_origem"] == {
        "tipo": LOTE,
        "identificador": str(importacao.pk),
    }


def test_post_com_origem_no_corpo_e_recusado_e_nada_e_gravado(client, cenario):
    """O cliente não escolhe a origem: o contrato do POST recusa o campo (400)."""
    antes = LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count()
    contas = cenario["contas"]

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2026-03-10",
            "historico": "Tentativa de origem pelo cliente",
            "origem": "importacao",
            "itens": [
                {"conta": contas["1.1.1"].id, "tipo": "debito", "valor": "10.00"},
                {"conta": contas["5.1"].id, "tipo": "credito", "valor": "10.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 400
    assert LancamentoContabil.objects.filter(empresa=cenario["empresa"]).count() == antes


def test_post_sem_origem_grava_manual(client, cenario):
    contas = cenario["contas"]

    response = client.post(
        reverse("contabilidade:lancamentos", args=[cenario["empresa"].id]),
        data={
            "data": "2026-03-10",
            "historico": "Digitado pela API",
            "itens": [
                {"conta": contas["1.1.1"].id, "tipo": "debito", "valor": "10.00"},
                {"conta": contas["5.1"].id, "tipo": "credito", "valor": "10.00"},
            ],
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    assert response.json()["origem"] == OrigemLancamento.MANUAL
    assert response.json()["documento_de_origem"] is None


# ---------------------------------------------------------------------------
# API: o Diário filtra por origem
# ---------------------------------------------------------------------------


def test_api_diario_filtra_por_origem_e_totais_sao_do_listado(client, cenario):
    _manual(cenario)
    _lote_recebido(cenario)
    url = reverse("contabilidade:diario", args=[cenario["empresa"].id])

    response = client.get(
        url, {"inicio": "2026-03-01", "fim": "2026-03-31", "origem": OrigemLancamento.IMPORTACAO}
    )

    assert response.status_code == 200
    corpo = response.json()
    assert corpo["origem_filtrada"] == OrigemLancamento.IMPORTACAO
    assert [item["origem"] for item in corpo["lancamentos"]] == [OrigemLancamento.IMPORTACAO]
    assert corpo["total_debito"] == "100.00"
    assert corpo["total_credito"] == "100.00"


def test_api_diario_sem_origem_lista_tudo_e_declara_que_nao_filtrou(client, cenario):
    _manual(cenario)
    _lote_recebido(cenario)
    url = reverse("contabilidade:diario", args=[cenario["empresa"].id])

    response = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31"})

    corpo = response.json()
    assert corpo["origem_filtrada"] is None
    assert len(corpo["lancamentos"]) == 2


def test_api_diario_com_origem_desconhecida_e_400(client, cenario):
    url = reverse("contabilidade:diario", args=[cenario["empresa"].id])

    response = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31", "origem": "inventada"})

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Tela: o detalhe mostra a origem e o link; o Diário tem o filtro
# ---------------------------------------------------------------------------


def _url_detalhe(cenario, lancamento):
    return reverse(
        "contabilidade_web:lancamento_detalhe", args=[cenario["empresa"].id, lancamento.pk]
    )


def test_tela_detalhe_de_automatico_mostra_origem_e_link_ao_lote(client, cenario):
    importacao = _lote_recebido(cenario)
    automatico = LancamentoContabil.objects.get(
        empresa=cenario["empresa"], origem=OrigemLancamento.IMPORTACAO
    )

    response = client.get(_url_detalhe(cenario, automatico))

    assert response.status_code == 200
    conteudo = response.content.decode("utf-8")
    assert "Importação de lançamentos" in conteudo
    assert "Lote de importação de lançamentos nº " + str(importacao.pk) in conteudo
    assert (
        reverse(
            "contabilidade_web:lancamentos_importacao",
            args=[cenario["empresa"].id, importacao.pk],
        )
        in conteudo
    )


def test_tela_detalhe_de_manual_mostra_manual_e_nenhum_documento(client, cenario):
    manual = _manual(cenario)

    response = client.get(_url_detalhe(cenario, manual))

    conteudo = response.content.decode("utf-8")
    assert "<strong>Origem:</strong> Manual" in conteudo
    assert "Documento de origem" not in conteudo


def test_tela_detalhe_de_escrita_fiscal_reservada_mostra_tipo_sem_inventar_link(client, cenario):
    lancamento = _escrita_fiscal_reservada(cenario)

    response = client.get(_url_detalhe(cenario, lancamento))

    conteudo = response.content.decode("utf-8")
    assert "Escrituração de NF-e (reservado)" in conteudo
    assert "35261099999999999999550010000000011000000011" in conteudo
    # Não há tela de contabilidade para a escrituração fiscal: nenhum link é inventado.
    trecho_do_documento = conteudo.split("Documento de origem:")[1].split("</p>")[0]
    assert "<a " not in trecho_do_documento


def test_tela_diario_filtra_por_origem(client, cenario):
    _manual(cenario, historico="Digitado filtrado fora")
    _lote_recebido(cenario)
    url = reverse("contabilidade_web:diario", args=[cenario["empresa"].id])

    response = client.get(
        url,
        {"inicio": "2026-03-01", "fim": "2026-03-31", "origem": OrigemLancamento.IMPORTACAO},
    )

    assert response.status_code == 200
    conteudo = response.content.decode("utf-8")
    assert "Compra importada sintética" in conteudo
    assert "Digitado filtrado fora" not in conteudo
    assert f'value="{OrigemLancamento.IMPORTACAO}" selected' in conteudo


def test_tela_diario_com_origem_desconhecida_e_400(client, cenario):
    url = reverse("contabilidade_web:diario", args=[cenario["empresa"].id])

    response = client.get(url, {"inicio": "2026-03-01", "fim": "2026-03-31", "origem": "inventada"})

    assert response.status_code == 400


@pytest.mark.parametrize("identificador", ["²", "0012", "12a"])
def test_tela_detalhe_nao_inventa_link_para_identificador_que_nao_e_o_id_do_lote(
    client, cenario, identificador
):
    """O link só aponta para o lote quando o identificador é EXATAMENTE o id gravado pela
    efetivação. "²" (dígito que `int()` não aceita), "0012" (zero à esquerda) e "12a" não
    são o id de nenhum lote: a tela mostra o identificador e não inventa URL nem quebra."""
    lancamento = criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 13),
        historico="Identificador estranho (sintético)",
        itens=_itens(cenario, "12.00"),
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(LOTE, identificador),
    )

    response = client.get(_url_detalhe(cenario, lancamento))

    assert response.status_code == 200
    trecho = response.content.decode("utf-8").split("Documento de origem:")[1].split("</p>")[0]
    assert "<a " not in trecho
    assert identificador in trecho


def test_tela_diario_com_filtro_diz_que_o_total_e_so_da_origem(client, cenario):
    """O total da tela não pode parecer o do período inteiro quando há filtro de origem."""
    _manual(cenario)
    _lote_recebido(cenario)
    url = reverse("contabilidade_web:diario", args=[cenario["empresa"].id])
    periodo = {"inicio": "2026-03-01", "fim": "2026-03-31"}

    filtrado = client.get(url, {**periodo, "origem": OrigemLancamento.IMPORTACAO})
    sem_filtro = client.get(url, periodo)

    assert "Total do período (somente a origem filtrada)" in filtrado.content.decode("utf-8")
    conteudo_sem_filtro = sem_filtro.content.decode("utf-8")
    assert "Total do período</td>" in conteudo_sem_filtro
    assert "somente a origem filtrada" not in conteudo_sem_filtro
