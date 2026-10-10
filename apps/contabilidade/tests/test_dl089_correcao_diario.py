"""DL-089, correção da rodada 1 (A5, T7): o Diário filtrado diz qual origem listou.

- A mensagem de período vazio cita a origem filtrada.
- O cabeçalho, que é o que se imprime, declara o filtro de origem.
- A opção `escrita_fiscal` do seletor só aparece quando a empresa tem lançamento dessa origem
  (ou quando ela já é o filtro pedido), e o rótulo é "Escrita fiscal", sem "(reservado)".

O Razão NÃO recebe filtro de origem: o saldo anterior soma todas as origens e tem de bater com
o Balancete. Isso é decisão do arquiteto, que a registra em `decisoes.md`; não há teste
aqui porque não há funcionalidade a testar. Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.contabilidade.models import (
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
PERIODO_DE_MARCO = {"inicio": "2026-03-01", "fim": "2026-03-31"}
PERIODO_VAZIO = {"inicio": "2026-04-01", "fim": "2026-04-30"}
CHAVE_NFE = "35261099999999999999550010000000011000000011"


@pytest.fixture
def cenario(client):
    escritorio = criar_escritorio("Escritório DL-089 diário", "89893000000189")
    empresa = criar_empresa(
        escritorio=escritorio, razao_social="Empresa DL-089 Diário Ltda", cnpj=CNPJ_DA_EMPRESA
    )
    usuario = get_user_model().objects.create_user(
        username="analista-diario-dl089",
        email="analista-diario-dl089@escritorio.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.ANALISTA
    )
    assert client.login(username="analista-diario-dl089", password=SENHA)
    return {"escritorio": escritorio, "empresa": empresa, "contas": criar_plano(empresa)}


def _itens(cenario):
    contas = cenario["contas"]
    return [
        {"conta": contas["1.1.1"], "tipo": TipoPartida.DEBITO, "valor": Decimal("100.00")},
        {"conta": contas["5.1"], "tipo": TipoPartida.CREDITO, "valor": Decimal("100.00")},
    ]


def _manual(cenario):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 10),
        historico="Digitado (sintético)",
        itens=_itens(cenario),
    )


def _importado(cenario):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 11),
        historico="Importado (sintético)",
        itens=_itens(cenario),
        origem=OrigemLancamento.IMPORTACAO,
        documento_origem=(TipoDocumentoOrigem.IMPORTACAO_LANCAMENTOS, 1),
    )


def _escrita_fiscal(cenario):
    return criar_lancamento(
        empresa=cenario["empresa"],
        data=date(2026, 3, 12),
        historico="Escrita fiscal (sintética)",
        itens=_itens(cenario),
        origem=OrigemLancamento.ESCRITA_FISCAL,
        documento_origem=(TipoDocumentoOrigem.ESCRITURACAO_NFE, CHAVE_NFE),
    )


def _url(cenario):
    return reverse("contabilidade_web:diario", args=[cenario["empresa"].id])


def _seletor(conteudo):
    """O trecho do `<select>` da origem, para o teste não confundir outro texto da página."""
    return conteudo.split('<select id="id_origem"', 1)[1].split("</select>", 1)[0]


def test_a5_sem_filtro_o_seletor_nao_oferece_escrita_fiscal_sem_lancamento_dessa_origem(
    client, cenario
):
    _manual(cenario)

    conteudo = client.get(_url(cenario), PERIODO_DE_MARCO).content.decode("utf-8")

    seletor = _seletor(conteudo)
    assert 'value="escrita_fiscal"' not in seletor
    assert 'value="importacao"' in seletor
    assert "Todas as origens" in seletor
    assert "reservado" not in seletor


def test_a5_seletor_oferece_escrita_fiscal_com_rotulo_limpo_quando_a_empresa_tem_essa_origem(
    client, cenario
):
    _escrita_fiscal(cenario)

    conteudo = client.get(_url(cenario), PERIODO_DE_MARCO).content.decode("utf-8")

    seletor = _seletor(conteudo)
    assert 'value="escrita_fiscal"' in seletor
    assert ">Escrita fiscal</option>" in seletor
    assert "reservado" not in seletor


def test_a5_filtro_de_origem_sem_lancamento_cita_a_origem_na_mensagem_de_vazio(client, cenario):
    """T7: a mensagem de vazio diz qual origem foi filtrada (o papel não lê como o Diário todo)."""
    _manual(cenario)

    response = client.get(
        _url(cenario), {**PERIODO_DE_MARCO, "origem": OrigemLancamento.ESCRITA_FISCAL}
    )

    assert response.status_code == 200
    conteudo = response.content.decode("utf-8")
    assert (
        "Nenhum lançamento no período de 01/03/2026 a 31/03/2026 com a origem “Escrita fiscal”."
        in conteudo
    )
    # O filtro pedido continua selecionado mesmo sem lançamento dessa origem.
    assert 'value="escrita_fiscal" selected' in _seletor(conteudo)


def test_a5_vazio_sem_filtro_nao_cita_origem(client, cenario):
    _manual(cenario)

    conteudo = client.get(_url(cenario), PERIODO_VAZIO).content.decode("utf-8")

    assert "Nenhum lançamento no período de 01/04/2026 a 30/04/2026." in conteudo
    assert "com a origem" not in conteudo


def test_a5_cabecalho_impresso_declara_a_origem_filtrada(client, cenario):
    _manual(cenario)
    _importado(cenario)

    filtrado = client.get(
        _url(cenario), {**PERIODO_DE_MARCO, "origem": OrigemLancamento.IMPORTACAO}
    )
    sem_filtro = client.get(_url(cenario), PERIODO_DE_MARCO)

    conteudo_filtrado = filtrado.content.decode("utf-8")
    assert (
        '<span class="contexto-rotulo">Origem</span>\n'
        "            <strong>Importação de lançamentos</strong>" in conteudo_filtrado
    )
    assert "Total do período (somente a origem filtrada)" in conteudo_filtrado
    # Sem filtro, o cabeçalho não declara origem alguma.
    assert '<span class="contexto-rotulo">Origem</span>' not in sem_filtro.content.decode("utf-8")


def test_a5_filtro_de_importacao_sem_lancamento_no_periodo_cita_a_origem(client, cenario):
    _importado(cenario)

    conteudo = client.get(
        _url(cenario), {**PERIODO_VAZIO, "origem": OrigemLancamento.IMPORTACAO}
    ).content.decode("utf-8")

    assert (
        "Nenhum lançamento no período de 01/04/2026 a 30/04/2026 "
        "com a origem “Importação de lançamentos”." in conteudo
    )
