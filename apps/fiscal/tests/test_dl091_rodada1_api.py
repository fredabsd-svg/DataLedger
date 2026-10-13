"""DL-091, correção da rodada 1, API e trilha da escrituração de compra.

- T5 (A5, M20): a troca de data de entrada pela API recusa quem não escritura (403), recusa outro
  escritório (404) e recusa escrituração efetivada (409), sem mudar a data.
- T6 (A5, N06/N07/N08): a troca de data e a de natureza deixam trilha com `antes` e `depois`, e a
  troca
  recusada não deixa trilha.
- T10 (A8, N31): o detalhe da API de uma compra de 2027 não mostra o bloqueio da regra de receita.
- T12 (A8, N17): a API recusa `cfop_entrada` em escrituração de saída, sem mudar nada.

Dados sintéticos. Plano: docs/planos/DL-091-nfe-de-entrada.md, seção "Decisões para a correção".
"""

import json
from datetime import date

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import EscrituracaoNFe, EstadoEscrituracao, NaturezaItemNFe
from apps.fiscal.models import NaturezaOperacaoNFe as N
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl091_entradas import _confirmar, _nota
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

DH_2027 = "2027-02-10T10:00:00-03:00"


@pytest.fixture
def empresa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="API rodada 1 Ltda", cnpj=CNPJ_DESTINATARIO_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa, regime=RegimeTributario.LUCRO_PRESUMIDO, vigencia_inicio=date(2026, 1, 1)
    )
    return empresa


@pytest.fixture
def gestor_b(escritorio_b):
    return usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-api-rodada1")


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _json(resposta):
    return json.loads(resposta.content)


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _rascunho(escritorio, usuario, empresa, numero="1"):
    documento = _nota(escritorio, usuario, empresa, numero=numero)
    return servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)


def _rascunho_e_efetivada(escritorio, usuario, empresa, numero="1"):
    esc = _rascunho(escritorio, usuario, empresa, numero)
    _confirmar(esc, N.ENTRADA_COMERCIALIZACAO, "1102", usuario)
    return servico.efetivar(esc, usuario=usuario)


def _venda(escritorio, usuario, empresa, numero="1", cfop="5102"):
    """Saída própria: a empresa emite (tpNF 1, finNFe 1) para um destinatário sintético."""
    return _nota(
        escritorio,
        usuario,
        empresa,
        numero=numero,
        cfop=cfop,
        tp_nf="1",
        fin_nfe="1",
        emitente=("CNPJ", CNPJ_DESTINATARIO_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )


# ---------------------------------------------------------------------------
# T5: permissão, isolamento e estado na troca de data de entrada pela API
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("papel", [Papel.PARALEGAL, Papel.CLIENTE])
def test_troca_de_data_de_entrada_recusa_quem_so_consulta_com_403(
    client, escritorio_a, usuario_gestor_a, empresa, papel
):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    leitor = usuario_com_papel(escritorio_a, papel, f"leitor-{papel.name.lower()}-rodada1")
    client.force_login(leitor)

    resposta = _post(
        client,
        _url("nfe_escrituracao_data_entrada", empresa.pk, esc.pk),
        {"data_entrada": "2026-03-20"},
    )

    assert resposta.status_code == 403
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 15)


def test_troca_de_data_de_entrada_de_outro_escritorio_responde_404(
    client, escritorio_a, usuario_gestor_a, empresa, gestor_b
):
    esc = _rascunho(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(gestor_b)

    resposta = _post(
        client,
        _url("nfe_escrituracao_data_entrada", empresa.pk, esc.pk),
        {"data_entrada": "2026-03-20"},
    )

    assert resposta.status_code == 404
    esc.refresh_from_db()
    assert esc.data_entrada == date(2026, 3, 15)


def test_troca_de_data_em_escrituracao_efetivada_responde_409_e_nao_muda_a_data(
    client, escritorio_a, usuario_gestor_a, empresa
):
    efetivada = _rascunho_e_efetivada(escritorio_a, usuario_gestor_a, empresa)
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        _url("nfe_escrituracao_data_entrada", empresa.pk, efetivada.pk),
        {"data_entrada": "2026-03-20"},
    )

    assert resposta.status_code == 409
    efetivada.refresh_from_db()
    assert efetivada.estado == EstadoEscrituracao.EFETIVADA
    assert efetivada.data_entrada == date(2026, 3, 15)


# ---------------------------------------------------------------------------
# T6: trilha da data de entrada e da natureza
# ---------------------------------------------------------------------------


def test_troca_de_data_e_de_natureza_deixam_trilha_com_antes_e_depois(
    escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="61")
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    antes_da_natureza = {
        r.item_id: {"natureza": r.natureza, "cfop_entrada": r.cfop_entrada}
        for r in NaturezaItemNFe.objects.filter(escrituracao=esc)
    }

    entradas.definir_data_de_entrada(esc, date(2026, 3, 20), usuario=usuario_gestor_a)
    entradas.definir_natureza_de_entrada(
        esc, N.ENTRADA_COMERCIALIZACAO, "1102", ids, usuario=usuario_gestor_a
    )

    trilha_data = RegistroAuditoria.objects.get(acao="escrituracao_nfe.data_entrada_definida")
    assert trilha_data.detalhes["antes"] == "2026-03-15"
    assert trilha_data.detalhes["depois"] == "2026-03-20"
    trilha_natureza = RegistroAuditoria.objects.get(
        acao="escrituracao_nfe.entrada_natureza_definida"
    )
    assert trilha_natureza.detalhes["natureza"] == N.ENTRADA_COMERCIALIZACAO
    for item_id in ids:
        assert trilha_natureza.detalhes["itens"][str(item_id)] == {
            "antes": antes_da_natureza[item_id],
            "depois": {"natureza": N.ENTRADA_COMERCIALIZACAO, "cfop_entrada": "1102"},
        }


def test_troca_de_data_recusada_por_estar_efetivada_nao_deixa_trilha(
    escritorio_a, usuario_gestor_a, empresa
):
    efetivada = _rascunho_e_efetivada(escritorio_a, usuario_gestor_a, empresa, numero="62")
    trilhas_antes = RegistroAuditoria.objects.filter(
        acao="escrituracao_nfe.data_entrada_definida"
    ).count()

    with pytest.raises(servico.EscrituracaoNFeErro):
        entradas.definir_data_de_entrada(efetivada, date(2026, 3, 20), usuario=usuario_gestor_a)

    assert (
        RegistroAuditoria.objects.filter(acao="escrituracao_nfe.data_entrada_definida").count()
        == trilhas_antes
    )
    efetivada.refresh_from_db()
    assert efetivada.data_entrada == date(2026, 3, 15)


# ---------------------------------------------------------------------------
# T10 (API): compra de 2027 não mostra bloqueio da regra de receita
# ---------------------------------------------------------------------------


def test_detalhe_da_compra_de_2027_nao_mostra_bloqueio_da_regra_de_receita(
    client, escritorio_a, usuario_gestor_a, empresa
):
    documento = _nota(escritorio_a, usuario_gestor_a, empresa, numero="71", dh_emi=DH_2027)
    esc = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario_gestor_a)
    client.force_login(usuario_gestor_a)

    detalhe = _json(client.get(_url("nfe_escrituracao_detalhe", empresa.pk, esc.pk)))

    assert detalhe["tipo"] == "entrada"
    assert detalhe["motivo_bloqueio_efetivacao"] is None


# ---------------------------------------------------------------------------
# T12 (API): CFOP de entrada recusado em escrituração de saída
# ---------------------------------------------------------------------------


def test_api_recusa_cfop_de_entrada_em_escrituracao_de_saida(
    client, escritorio_a, usuario_gestor_a, empresa
):
    venda = _venda(escritorio_a, usuario_gestor_a, empresa, numero="72")
    esc = servico.criar_rascunho(vinculo(venda, empresa), usuario=usuario_gestor_a)
    ids = list(NaturezaItemNFe.objects.filter(escrituracao=esc).values_list("item_id", flat=True))
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        _url("nfe_escrituracao_naturezas", empresa.pk, esc.pk),
        {"natureza": N.REVENDA, "itens": ids, "cfop_entrada": "1102"},
    )

    assert resposta.status_code == 400
    assert "CFOP de entrada só existe na escrituração de entrada" in resposta.content.decode(
        "utf-8"
    )
    assert not NaturezaItemNFe.objects.filter(escrituracao=esc).exclude(natureza="").exists()
    assert EscrituracaoNFe.objects.get(pk=esc.pk).estado == EstadoEscrituracao.RASCUNHO
