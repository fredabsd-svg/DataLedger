"""DL-085, leitura em partes: a prévia não lê XML, e a leitura de um mês roda em partes.

Cobre o que o arquiteto pediu: a prévia com nota nunca lida não lê XML (monkeypatch que falha se
`ler_itens` for chamado); leitura em partes com limite pequeno; interrupção no meio e repetição sem
duplicar; ilegível e falha de banco que não derrubam as outras; isolamento entre empresas; a
confirmação que só trata as notas lidas; e a API (papéis, isolamento, entrada).
"""

import json
from types import SimpleNamespace

import pytest
from django.db import DatabaseError
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import EscrituracaoNFe, ItemNFe, LeituraItensNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.fiscal.tests.suporte_dl085 import (
    CNPJ_SEGUNDA_EMPRESA,
    nfce,
    previa_lida,
    usuario_gestor,
)
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-leitura-dl085")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Leitura DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Outra leitura DL085 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )


def _cinco(escritorio, usuario, emitente=CNPJ_EMITENTE_A):
    for numero in range(1, 6):
        nfce(escritorio, usuario, numero=numero, valor=f"{numero * 10}.00", emitente=emitente)


def _proibido_ler(*_args, **_kwargs):
    raise AssertionError("a prévia leu XML: a leitura tem de ser só pelo endpoint de leitura")


def test_previa_nao_le_xml_de_nota_nunca_lida(escritorio_a, gestor, empresa, monkeypatch):
    """Nota nunca lida: a prévia a põe em `a_ler`, sem chamar `ler_itens` (que aqui falharia)."""
    _cinco(escritorio_a, gestor)
    monkeypatch.setattr(lote, "ler_itens", _proibido_ler)

    previa = lote.previa_do_lote(empresa, 2026, 3)

    assert len(previa.a_ler) == 5
    assert previa.grupos == () and previa.fora == ()
    assert not LeituraItensNFe.objects.filter(documento__escritorio=escritorio_a).exists()


def test_leitura_em_partes_com_limite_pequeno_informa_o_que_resta(escritorio_a, gestor, empresa):
    _cinco(escritorio_a, gestor)

    primeira = lote.ler_notas_do_mes(empresa, 2026, 3, limite=2)
    segunda = lote.ler_notas_do_mes(empresa, 2026, 3, limite=2)
    terceira = lote.ler_notas_do_mes(empresa, 2026, 3, limite=2)

    assert (primeira.lidas_nesta_chamada, primeira.restam, primeira.terminou) == (2, 3, False)
    assert (segunda.lidas_nesta_chamada, segunda.restam) == (2, 1)
    assert (terceira.lidas_nesta_chamada, terceira.restam, terceira.terminou) == (1, 0, True)
    previa = lote.previa_do_lote(empresa, 2026, 3)
    assert previa.a_ler == ()
    assert sum(g.quantidade_notas for g in previa.grupos) == 5


def test_leitura_repetida_nao_reler_nem_duplica_itens(escritorio_a, gestor, empresa):
    _cinco(escritorio_a, gestor)
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=50)
    itens_antes = ItemNFe.objects.count()

    repetida = lote.ler_notas_do_mes(empresa, 2026, 3, limite=50)

    assert (repetida.lidas_nesta_chamada, repetida.restam) == (0, 0)
    assert ItemNFe.objects.count() == itens_antes == 5
    assert LeituraItensNFe.objects.count() == 5


def test_interrupcao_no_meio_da_leitura_e_repeticao_completa_sem_duplicar(
    escritorio_a, gestor, empresa, monkeypatch
):
    """A terceira leitura cai (RuntimeError, como uma queda do processo). As duas primeiras
    ficam gravadas, a terceira não deixa nada para trás, e a repetição lê as três restantes."""
    _cinco(escritorio_a, gestor)
    original = lote.ler_itens
    chamadas = {"n": 0}

    def cai_na_terceira(documento):
        chamadas["n"] += 1
        if chamadas["n"] == 3:
            raise RuntimeError("queda simulada no meio da leitura")
        return original(documento)

    monkeypatch.setattr(lote, "ler_itens", cai_na_terceira)
    with pytest.raises(RuntimeError):
        lote.ler_notas_do_mes(empresa, 2026, 3, limite=5)
    assert LeituraItensNFe.objects.count() == 2
    monkeypatch.setattr(lote, "ler_itens", original)

    repetida = lote.ler_notas_do_mes(empresa, 2026, 3, limite=5)

    assert (repetida.lidas_nesta_chamada, repetida.restam) == (3, 0)
    assert LeituraItensNFe.objects.count() == 5
    assert ItemNFe.objects.count() == 5


def test_ilegivel_nao_derruba_as_outras_notas(escritorio_a, gestor, empresa):
    """Uma nota com vDesc 0,00 é ilegível (XSD). As outras duas são lidas normalmente."""
    nfce(escritorio_a, gestor, numero=1, valor="10.00")
    nfce(
        escritorio_a,
        gestor,
        numero=2,
        dets=[
            xml.det(1, cfop="5102", vprod="100.00", vdesc="0.00", icms_xml=xml.icms(csosn="102"))
        ],
        vnf="100.00",
    )
    nfce(escritorio_a, gestor, numero=3, valor="30.00")

    leitura = lote.ler_notas_do_mes(empresa, 2026, 3, limite=10)

    assert (leitura.lidas_nesta_chamada, leitura.ilegiveis_nesta_chamada) == (2, 1)
    assert leitura.restam == 0 and leitura.falhas_nesta_chamada == ()
    previa = previa_lida(empresa, 2026, 3)
    assert [r.codigo for r in previa.fora] == [lote.CODIGO_ILEGIVEL]
    assert sum(g.quantidade_notas for g in previa.grupos) == 2


def test_falha_de_banco_numa_nota_fica_em_falhas_e_as_outras_seguem(
    escritorio_a, gestor, empresa, monkeypatch
):
    _cinco(escritorio_a, gestor)
    original = lote.ler_itens
    primeira_nota = {"pk": None}

    def falha_na_primeira(documento):
        if primeira_nota["pk"] is None:
            primeira_nota["pk"] = documento.pk
        if documento.pk == primeira_nota["pk"]:
            raise DatabaseError("falha simulada de banco")
        return original(documento)

    monkeypatch.setattr(lote, "ler_itens", falha_na_primeira)
    leitura = lote.ler_notas_do_mes(empresa, 2026, 3, limite=10)

    assert leitura.lidas_nesta_chamada == 4
    assert len(leitura.falhas_nesta_chamada) == 1
    assert "erro de banco" in leitura.falhas_nesta_chamada[0].motivo
    assert leitura.restam == 1

    monkeypatch.setattr(lote, "ler_itens", original)
    depois = lote.ler_notas_do_mes(empresa, 2026, 3, limite=10)
    assert (depois.lidas_nesta_chamada, depois.restam) == (1, 0)


def test_leitura_de_versao_anterior_que_nao_pode_ser_refeita_vira_falha(
    escritorio_a, gestor, empresa, monkeypatch
):
    """Se `ler_itens` devolver uma leitura de versão anterior, a nota não conta como lida."""
    _cinco(escritorio_a, gestor)
    monkeypatch.setattr(
        lote,
        "ler_itens",
        lambda documento: SimpleNamespace(versao_leitor=1, estado=LeituraItensNFe.ESTADO_LIDA),
    )

    leitura = lote.ler_notas_do_mes(empresa, 2026, 3, limite=10)

    assert leitura.lidas_nesta_chamada == 0
    assert len(leitura.falhas_nesta_chamada) == 5
    assert (
        leitura.falhas_nesta_chamada[0].motivo == "leitura de versão anterior não pôde ser refeita"
    )
    assert leitura.restam == 5


def test_leitura_so_toca_notas_da_empresa_e_nao_cria_escrituracao(
    escritorio_a, gestor, empresa, outra
):
    """Isolamento: a leitura de uma empresa não lê nem grava nada das notas da outra."""
    _cinco(escritorio_a, gestor, emitente=CNPJ_EMITENTE_A)
    _cinco(escritorio_a, gestor, emitente=CNPJ_SEGUNDA_EMPRESA)

    lote.ler_notas_do_mes(empresa, 2026, 3, limite=50)

    assert LeituraItensNFe.objects.count() == 5
    assert not LeituraItensNFe.objects.filter(documento__vinculos__empresa=outra).exists()
    assert lote.previa_do_lote(outra, 2026, 3).a_ler != ()
    assert not EscrituracaoNFe.objects.exists()


def test_confirmacao_so_trata_notas_lidas_e_as_nao_lidas_ficam_de_fora(
    escritorio_a, gestor, empresa
):
    """Três de cinco lidas. A confirmação do que foi lido grava 3 notas; as 2 não lidas continuam
    pendentes, em `a_ler`, sem entrar em grupo nem em "fora do lote"."""
    _cinco(escritorio_a, gestor)
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=3)
    previa = lote.previa_do_lote(empresa, 2026, 3)
    assert len(previa.a_ler) == 2

    progresso = lote.confirmar_lote(empresa, 2026, 3, previa.assinatura, {}, gestor, limite=10)

    assert progresso.terminou and progresso.efetivadas_total == 3
    assert EscrituracaoNFe.objects.filter(empresa=empresa).count() == 3
    depois = lote.previa_do_lote(empresa, 2026, 3)
    assert len(depois.a_ler) == 2
    assert depois.fora == ()


def test_assinatura_antes_da_leitura_nao_vale_depois_dela(escritorio_a, gestor, empresa):
    """A prévia de antes da leitura tem as notas em `a_ler`. Lidas, a assinatura muda: a confirmação
    com a assinatura antiga recusa (409), e nada é efetivado."""
    _cinco(escritorio_a, gestor)
    antes = lote.previa_do_lote(empresa, 2026, 3)
    lote.ler_notas_do_mes(empresa, 2026, 3, limite=50)

    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(empresa, 2026, 3, antes.assinatura, {}, gestor)
    assert not EscrituracaoNFe.objects.exists()


def test_nota_de_2027_e_lida_e_depois_sai_como_recusa_de_data(escritorio_a, gestor, empresa):
    """A leitura percorre a nota de 2027 (é "a ler" como as outras), e depois a prévia a recusa."""
    nfce(escritorio_a, gestor, numero=1, dh_emi="2027-01-05T10:00:00-03:00")
    assert len(lote.previa_do_lote(empresa, 2027, 1).a_ler) == 1

    lote.ler_notas_do_mes(empresa, 2027, 1, limite=10)

    previa = lote.previa_do_lote(empresa, 2027, 1)
    assert previa.a_ler == ()
    assert [r.codigo for r in previa.fora] == [lote.CODIGO_2027]


@pytest.mark.parametrize("limite", [0, lote.LIMITE_MAXIMO_DA_LEITURA + 1])
def test_limite_fora_da_faixa_e_entrada_invalida(escritorio_a, gestor, empresa, limite):
    _cinco(escritorio_a, gestor)
    with pytest.raises(servico.EntradaInvalidaNFe):
        lote.ler_notas_do_mes(empresa, 2026, 3, limite=limite)
    assert LeituraItensNFe.objects.count() == 0


def test_limite_padrao_da_leitura_cabe_no_orcamento_de_cinco_segundos():
    """Pela medida (~11 ms por nota), 400 notas dão cerca de 4,5 s. Trocar o padrão sem medir é
    trocar um número que o contador não pode ver quebrar."""
    assert lote.LIMITE_PADRAO_DA_LEITURA == 400
    assert lote.LIMITE_MAXIMO_DA_LEITURA == 800


# ---------------------------------------------------------------------------
# API: POST /lote/ler/ e a prévia com o bloco "a ler"
# ---------------------------------------------------------------------------


def _url(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-leitura-dl085")


def test_api_leitura_devolve_lidas_e_restam(escritorio_a, gestor, empresa, client):
    _cinco(escritorio_a, gestor)
    client.force_login(gestor)

    resposta = _post(client, _url("nfe_lote_ler", empresa.pk), {"ano": 2026, "mes": 3, "limite": 2})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert (corpo["lidas_nesta_chamada"], corpo["restam"], corpo["terminou"]) == (2, 3, False)
    assert corpo["falhas_nesta_chamada"] == []


def test_api_previa_mostra_a_ler_e_depois_zero(escritorio_a, gestor, empresa, client):
    _cinco(escritorio_a, gestor)
    client.force_login(gestor)

    antes = client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3").json()
    assert antes["a_ler"] == {"notas": 5}
    assert antes["grupos"] == []

    _post(client, _url("nfe_lote_ler", empresa.pk), {"ano": 2026, "mes": 3, "limite": 50})
    depois = client.get(_url("nfe_lote_previa", empresa.pk) + "?ano=2026&mes=3").json()
    assert depois["a_ler"] == {"notas": 0}
    assert sum(g["notas"] for g in depois["grupos"]) == 5


def test_api_leitura_so_para_quem_escritura(
    escritorio_a, gestor, paralegal, usuario_cliente_a, empresa, client
):
    _cinco(escritorio_a, gestor)
    corpo = {"ano": 2026, "mes": 3, "limite": 5}

    client.force_login(paralegal)
    assert _post(client, _url("nfe_lote_ler", empresa.pk), corpo).status_code == 403
    client.force_login(usuario_cliente_a)
    assert _post(client, _url("nfe_lote_ler", empresa.pk), corpo).status_code == 403
    assert LeituraItensNFe.objects.count() == 0


def test_api_leitura_de_empresa_de_outro_escritorio_responde_404(
    escritorio_a, gestor, escritorio_b, empresa, client
):
    gestor_b = usuario_com_papel(escritorio_b, Papel.GESTOR, "gestor-b-leitura-dl085")
    client.force_login(gestor_b)

    assert (
        _post(client, _url("nfe_lote_ler", empresa.pk), {"ano": 2026, "mes": 3}).status_code == 404
    )


@pytest.mark.parametrize(
    "corpo",
    [
        pytest.param({"ano": 2026}, id="sem-mes"),
        pytest.param({"ano": 2026, "mes": 3, "limite": 0}, id="limite-zero"),
        pytest.param({"ano": 2026, "mes": 3, "limite": 801}, id="limite-acima-do-teto"),
        pytest.param({"ano": 2026, "mes": 3, "campo_novo": 1}, id="campo-fora-do-contrato"),
    ],
)
def test_api_leitura_entrada_invalida_responde_400(escritorio_a, gestor, empresa, client, corpo):
    client.force_login(gestor)
    assert _post(client, _url("nfe_lote_ler", empresa.pk), corpo).status_code == 400
