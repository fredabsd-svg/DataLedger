"""DL-087, correção da rodada 1 (auditoria de 12/10/2026): um grupo de testes por achado, A1 a A13.

Plano: docs/planos/DL-087-classificacao-fiscal-versionada.md, seção "Decisões para a correção
(rodada 1)". Dados sintéticos (CNPJs de teste de `xml_nfe_dl080` e `suporte_dl085`). Os testes que
falhariam antes da correção estão marcados no próprio nome do grupo; a prova por mutante está no
relatório da entrega.
"""

import importlib
import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from django.apps import apps as registro_de_apps
from django.db import DatabaseError, connection, transaction
from django.urls import reverse
from django.utils import timezone

from apps.empresas.models import Empresa
from apps.fiscal import cfop as tabela
from apps.fiscal import classificacao as cl
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EscrituracaoNFe,
    EstadoConfirmacaoMes,
    ItemNFe,
    LoteEscrituracaoNFe,
    NaturezaItemNFe,
    OrigemNaturezaItemNFe,
    RegraClassificacaoNFe,
)
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel, vinculo
from apps.fiscal.tests.suporte_dl085 import CNPJ_SEGUNDA_EMPRESA, confirmar_tudo, nfce, previa_lida
from apps.fiscal.tests.test_dl087_telas import formulario, notas_sem_sugestao
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

FUSO = ZoneInfo("America/Sao_Paulo")
ANO, MES = 2026, 3
CFOP_SEM_SINAL = "5949"  # sem sinal na sugestão embutida: vai para a fila
CFOP_REVENDA = "5102"  # sinal de revenda pelo CFOP: a sugestão embutida é "revenda"
NCM_CERVEJA = "22030000"
NCM_QUE_NAO_CASA = "99999999"
DH_MEIO_DE_MARCO = "2026-03-15T10:00:00-03:00"
DH_FUTURO = "2026-12-01T10:00:00-03:00"
M20 = importlib.import_module("apps.fiscal.migrations.0020_dl087_origem_da_natureza_confirmada")
M19 = importlib.import_module("apps.fiscal.migrations.0019_dl087_regra_de_classificacao_nfe")


# ---------------------------------------------------------------------------
# Fixtures e helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-correcao-dl087")


@pytest.fixture
def analista(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.ANALISTA, "analista-correcao-dl087")


@pytest.fixture
def paralegal(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.PARALEGAL, "paralegal-correcao-dl087")


@pytest.fixture
def empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Correção DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def outra_empresa(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Vizinha DL087 Ltda", cnpj=CNPJ_SEGUNDA_EMPRESA
    )


def _regra(escritorio, usuario, empresa=None, **campos):
    base = {
        "tipo": "saida_propria",
        "cfop": CFOP_SEM_SINAL,
        "natureza": "revenda",
        "vigencia_inicio": date(ANO, MES, 1),
    }
    base.update(campos)
    return cl.criar_regra(
        escritorio=escritorio, empresa=empresa, dados=cl.DadosDaRegra(**base), usuario=usuario
    )


def _ler(empresa, ano=ANO, mes=MES):
    leitura = lote.ler_notas_do_mes(empresa, ano, mes, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
    assert leitura.terminou and not leitura.falhas_nesta_chamada, leitura


def _nota(escritorio, usuario, numero, *, cfop=CFOP_SEM_SINAL, dh_emi=DH_MEIO_DE_MARCO):
    return nfce(
        escritorio,
        usuario,
        numero=numero,
        cfop=cfop,
        csosn="102",
        ncm=NCM_CERVEJA,
        dh_emi=dh_emi,
    )


def _sugestao(empresa, documento):
    item = ItemNFe.objects.get(documento=documento)
    return cl.sugerir_natureza_com_regras(
        cl.contexto_da_empresa(empresa), documento, item, "saida_propria"
    )


def _rascunho_com_natureza(empresa, usuario, documento, natureza):
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = list(ItemNFe.objects.filter(documento=documento).values_list("pk", flat=True))
    servico.definir_natureza(escrituracao, natureza, ids, usuario=usuario)
    return escrituracao


def _url_api(nome, *args):
    return reverse(f"fiscal_api:{nome}", args=list(args))


def _corpo_criar(**campos):
    """Corpo do POST de criar regra (sem ano e mês, que são da prévia)."""
    corpo = _corpo_previa(**campos)
    corpo.pop("ano")
    corpo.pop("mes")
    return corpo


def _corpo_previa(**campos):
    base = {
        "escopo": "empresa",
        "tipo": "saida_propria",
        "cfop": CFOP_SEM_SINAL,
        "natureza": "revenda",
        "vigencia_inicio": "2026-03-01",
        "vigencia_fim": None,
        "ncm": "",
        "ncm_modo": "",
        "cst_csosn": "",
        "id_dest": "",
        "ano": ANO,
        "mes": MES,
    }
    base.update(campos)
    return base


# ---------------------------------------------------------------------------
# A1 (alta): desativar é REVOGAR. Nenhuma nota casa, pendente ou futura.
# ---------------------------------------------------------------------------


def test_a1_desativar_muda_a_assinatura_e_a_confirmacao_antiga_recebe_409(
    escritorio_a, gestor, empresa
):
    _nota(escritorio_a, gestor, 1)
    _nota(escritorio_a, gestor, 2)
    _ler(empresa)
    _regra(escritorio_a, gestor, empresa)
    com_regra = lote.previa_do_lote(empresa, ANO, MES)
    assert com_regra.grupos  # a regra sugere natureza: as notas entram no lote

    cl.desativar_regra(
        RegraClassificacaoNFe.objects.get(cfop=CFOP_SEM_SINAL),
        motivo="regra errada",
        usuario=gestor,
    )
    depois = lote.previa_do_lote(empresa, ANO, MES)

    assert depois.assinatura != com_regra.assinatura
    assert depois.grupos == ()
    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(empresa, ANO, MES, com_regra.assinatura, {}, gestor, limite=10)
    assert not EscrituracaoNFe.objects.filter(empresa=empresa).exists()


def test_a1_revogada_nao_casa_nota_pendente_nem_futura(escritorio_a, gestor, empresa):
    no_inicio = _nota(escritorio_a, gestor, 3, dh_emi="2026-03-01T10:00:00-03:00")
    pendente = _nota(escritorio_a, gestor, 1)
    futura = _nota(escritorio_a, gestor, 2, dh_emi=DH_FUTURO)
    _ler(empresa)
    _ler(empresa, 2026, 12)
    _regra(escritorio_a, gestor, empresa, cfop=CFOP_SEM_SINAL)
    assert _sugestao(empresa, no_inicio).natureza == "revenda"
    assert _sugestao(empresa, pendente).natureza == "revenda"
    assert _sugestao(empresa, futura).natureza == "revenda"

    cl.desativar_regra(
        RegraClassificacaoNFe.objects.get(cfop=CFOP_SEM_SINAL), motivo="errada", usuario=gestor
    )

    # Inclusive a nota do dia do início: a véspera do início é o que faz a vigência ficar vazia.
    assert _sugestao(empresa, no_inicio).natureza is None
    assert _sugestao(empresa, pendente).natureza is None
    assert _sugestao(empresa, futura).natureza is None


def test_a1_efetivada_guarda_a_origem_da_regra_que_foi_revogada(escritorio_a, gestor, empresa):
    documento = _nota(escritorio_a, gestor, 1)
    regra = _regra(escritorio_a, gestor, empresa)
    _ler(empresa)
    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))
    efetivada = EscrituracaoNFe.objects.get(vinculo__documento=documento)
    assert efetivada.estado == "efetivada"

    cl.desativar_regra(regra, motivo="errada", usuario=gestor)

    efetivada.refresh_from_db()
    assert efetivada.estado == "efetivada"
    linha = NaturezaItemNFe.objects.get(escrituracao=efetivada)
    assert linha.natureza == "revenda"
    origem = OrigemNaturezaItemNFe.objects.get(natureza_item=linha)
    assert (origem.origem, origem.regra_classificacao_id) == ("regra", regra.pk)


def test_a1_sql_recusa_desativacao_que_nao_e_revogacao(escritorio_a, gestor, empresa):
    regra = _regra(escritorio_a, gestor, empresa)
    agora = timezone.now()
    with pytest.raises(DatabaseError, match="só pode ser desativada por revogação"):
        with transaction.atomic():
            RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(
                vigencia_fim=date(2099, 12, 31),
                desativada_em=agora,
                desativada_por=gestor,
                motivo_desativacao="por SQL",
            )
    regra.refresh_from_db()
    assert regra.ativa

    # A mesma desativação com a véspera do início (a revogação) passa pelo gatilho.
    RegraClassificacaoNFe.objects.filter(pk=regra.pk).update(
        vigencia_fim=date(ANO, MES, 1) - timedelta(days=1),
        desativada_em=agora,
        desativada_por=gestor,
        motivo_desativacao="por SQL",
    )
    regra.refresh_from_db()
    assert not regra.ativa


def test_a1_vigencia_revogada_e_a_vespera_do_inicio_e_na_data_minima():
    assert cl.vigencia_revogada(date(2026, 3, 1)) == date(2026, 2, 28)
    assert cl.vigencia_revogada(date.min) == date.min


def test_a1_regra_que_comeca_na_data_minima_pode_ser_revogada(escritorio_a, gestor, empresa):
    regra = _regra(escritorio_a, gestor, empresa, vigencia_inicio=date.min)
    revogada = cl.desativar_regra(regra, motivo="teste de limite", usuario=gestor)
    assert revogada.vigencia_fim == date.min
    assert not revogada.ativa


# ---------------------------------------------------------------------------
# A2 (média): a prévia de uma regra duplicada responde 409, e não 500.
# ---------------------------------------------------------------------------


def test_a2_previa_de_regra_duplicada_recusa_com_a_regra_existente(escritorio_a, gestor, empresa):
    existente = _regra(escritorio_a, gestor, empresa)
    dados = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop=CFOP_SEM_SINAL,
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
    )
    with pytest.raises(cl.RegraDuplicada, match=f"regra n.º {existente.pk}"):
        cl.previa_de_impacto(empresa, ANO, MES, dados, "empresa")


def test_a2_previa_com_natureza_diferente_no_mesmo_criterio_tambem_recusa(
    escritorio_a, gestor, empresa
):
    _regra(escritorio_a, gestor, empresa, natureza="revenda")
    dados = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop=CFOP_SEM_SINAL,
        natureza="producao_propria",
        vigencia_inicio=date(ANO, MES, 1),
    )
    with pytest.raises(cl.RegraDuplicada):
        cl.previa_de_impacto(empresa, ANO, MES, dados, "empresa")


def test_a2_previa_pela_api_responde_409_e_nao_500(client, gestor, empresa, escritorio_a):
    _regra(escritorio_a, gestor, empresa)
    client.force_login(gestor)

    resposta = client.post(
        _url_api("nfe_classificacao_previa", empresa.pk),
        data=json.dumps(_corpo_previa()),
        content_type="application/json",
    )

    assert resposta.status_code == 409
    assert "Já existe a regra" in resposta.json()["detail"]


def test_a2_previa_pela_tela_responde_409_com_a_mensagem(client, gestor, empresa, escritorio_a):
    from apps.fiscal.tests.test_dl087_telas import url_nova

    _regra(escritorio_a, gestor, empresa, cfop="5102")
    client.force_login(gestor)

    resposta = client.post(
        url_nova(empresa), formulario(acao="previa", cfop="5102", natureza="revenda")
    )

    assert resposta.status_code == 409
    assert "Já existe a regra" in resposta.content.decode("utf-8")


def test_a2_ordenacao_tolera_a_regra_da_previa_sem_pk():
    """A regra virtual da prévia não tem pk. Empatar com uma gravada não pode dar TypeError."""
    dia = datetime(2026, 3, 15, 10, tzinfo=FUSO)
    documento = SimpleNamespace(
        modelo="55",
        tp_nf="1",
        fin_nfe="1",
        id_dest="1",
        transferencia_entre_estabelecimentos=False,
        dh_emissao=dia,
    )
    item = SimpleNamespace(cfop=CFOP_SEM_SINAL, ncm=NCM_CERVEJA, csosn="102", cst=None)
    gravada = _regra_fake(5, natureza="revenda")
    virtual = _regra_fake(None, natureza="revenda")
    contexto = cl.ContextoDeClassificacao(
        escritorio_id=1, empresa_id=7, padrao_combustivel="", regras=(gravada, virtual)
    )

    sugestao = cl.sugerir_natureza_com_regras(contexto, documento, item, "saida_propria")

    assert sugestao.natureza == "revenda"
    assert sugestao.regra_ids == (5,)


def _regra_fake(pk, *, natureza, empresa_id=None):
    return SimpleNamespace(
        pk=pk,
        empresa_id=empresa_id,
        tipo="saida_propria",
        cfop=CFOP_SEM_SINAL,
        ncm="",
        ncm_modo="",
        cst_csosn="",
        id_dest="",
        natureza=natureza,
        vigencia_inicio=date(ANO, MES, 1),
        vigencia_fim=None,
        desativada_em=None,
    )


# ---------------------------------------------------------------------------
# A3 (média): a contagem de itens confirmados é só da empresa da consulta.
# ---------------------------------------------------------------------------


def _confirmar_item_da_regra(escritorio, gestor, empresa):
    """Uma nota da empresa com a natureza confirmada pela regra do escritório (origem gravada)."""
    _regra(escritorio, gestor, None, cfop=CFOP_SEM_SINAL)
    documento = _nota(escritorio, gestor, 1)
    _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    return documento


def test_a3_api_conta_so_os_itens_confirmados_da_empresa_da_url(
    client, gestor, empresa, outra_empresa, escritorio_a
):
    _confirmar_item_da_regra(escritorio_a, gestor, empresa)
    client.force_login(gestor)

    da_empresa = client.get(_url_api("nfe_classificacao_regras", empresa.pk)).json()["regras"]
    da_outra = client.get(_url_api("nfe_classificacao_regras", outra_empresa.pk)).json()["regras"]

    assert [r["itens_confirmados"] for r in da_empresa] == [1]
    assert [r["itens_confirmados"] for r in da_outra] == [0]


def test_a3_contagem_e_da_empresa_nas_funcoes_que_a_tela_usa(
    escritorio_a, gestor, empresa, outra_empresa
):
    _confirmar_item_da_regra(escritorio_a, gestor, empresa)

    da_empresa = cl.regras_da_empresa(empresa).annotate(total=cl.contagem_de_confirmados(empresa))
    da_outra = cl.regras_da_empresa(outra_empresa).annotate(
        total=cl.contagem_de_confirmados(outra_empresa)
    )
    assert [r.total for r in da_empresa] == [1]
    assert [r.total for r in da_outra] == [0]


def test_a3_tela_de_desativar_conta_so_a_empresa_da_url(
    client, gestor, empresa, outra_empresa, escritorio_a
):
    regra_do_escritorio = _regra(escritorio_a, gestor, None, cfop=CFOP_SEM_SINAL)
    documento = _nota(escritorio_a, gestor, 1)
    _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    client.force_login(gestor)

    html = client.get(
        reverse(
            "fiscal_web:classificacao_regra_desativar",
            args=[outra_empresa.pk, regra_do_escritorio.pk],
        )
    ).content.decode("utf-8")

    contagem = re.search(
        r"Itens confirmados a partir desta regra</dt>\s*<dd class=\"valor-monetario\">(\d+)</dd>",
        html,
    )
    assert contagem is not None and contagem.group(1) == "0"


# ---------------------------------------------------------------------------
# A4 (média): identificador de assinatura malformado é 400, nunca 500.
# ---------------------------------------------------------------------------


def test_a4_escolha_com_identificador_malformado_e_400_com_lote_aberto(
    escritorio_a, gestor, empresa
):
    for numero in (1, 2):
        nfce(escritorio_a, gestor, numero=numero, cfop=CFOP_REVENDA, csosn="102", ncm=NCM_CERVEJA)
    _ler(empresa)
    previa = lote.previa_do_lote(empresa, ANO, MES)
    lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, gestor, limite=1)
    assert LoteEscrituracaoNFe.objects.filter(empresa=empresa).exists()

    chave = previa.grupos[0].chave
    with pytest.raises(servico.EntradaInvalidaNFe, match="Identificador de assinatura"):
        lote.confirmar_lote(
            empresa, ANO, MES, previa.assinatura, {chave: {"abc": "revenda"}}, gestor, limite=1
        )


# ---------------------------------------------------------------------------
# A5 (média): NCM só com dígitos ASCII e pontos; o resto é 400 com mensagem.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ncm", ["22AB", "٢٢٠٣", "２２０３", "22 03", "2203-00", "22.0a"])
def test_a5_ncm_com_caractere_que_nao_e_digito_ascii_e_recusado(escritorio_a, gestor, ncm):
    dados = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop=CFOP_REVENDA,
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
        ncm=ncm,
        ncm_modo="prefixo",
    )
    with pytest.raises(servico.EntradaInvalidaNFe, match="NCM aceita só dígitos e pontos"):
        cl.criar_regra(escritorio=escritorio_a, empresa=None, dados=dados, usuario=gestor)
    assert not RegraClassificacaoNFe.objects.exists()


def test_a5_ncm_com_pontos_e_aceito_e_vira_so_digitos(escritorio_a, gestor):
    dados = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop=CFOP_REVENDA,
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
        ncm="2203.00",
        ncm_modo="prefixo",
    )
    regra = cl.criar_regra(escritorio=escritorio_a, empresa=None, dados=dados, usuario=gestor)
    assert regra.ncm == "220300"


def test_a5_api_e_tela_recusam_ncm_com_letra_com_400(client, gestor, empresa):
    from apps.fiscal.tests.test_dl087_telas import url_nova

    client.force_login(gestor)
    api = client.post(
        _url_api("nfe_classificacao_regras", empresa.pk),
        data=json.dumps(_corpo_criar(ncm="22AB", ncm_modo="prefixo")),
        content_type="application/json",
    )
    tela = client.post(url_nova(empresa), formulario(ncm="22AB", ncm_modo="prefixo", acao="criar"))

    assert api.status_code == 400
    assert tela.status_code == 400
    assert "NCM aceita só dígitos e pontos" in tela.content.decode("utf-8")


# ---------------------------------------------------------------------------
# A6 (média): o índice por NCM e a prévia numa passada só.
# ---------------------------------------------------------------------------


def test_a6_candidatas_do_item_nao_incluem_regra_de_ncm_que_nao_casa(escritorio_a, gestor, empresa):
    regras = [
        SimpleNamespace(
            **{
                **_regra_fake(pk, natureza="revenda").__dict__,
                "cfop": "5656",
                "ncm": f"9999{pk:04d}",
                "ncm_modo": "exato",
            }
        )
        for pk in range(1, 51)
    ]
    contexto = cl.ContextoDeClassificacao(
        escritorio_id=1, empresa_id=7, padrao_combustivel="", regras=tuple(regras)
    )

    assert contexto.candidatas_do_item("5656", NCM_CERVEJA) == []
    assert len(contexto.candidatas_do_item("5656", "99990007")) == 1


def test_a6_indice_acha_as_mesmas_candidatas_que_a_busca_completa():
    """Exatas, prefixos de vários tamanhos e sem NCM: o índice devolve exatamente o que `_casa`
    poderia aceitar. Se diverge, a resolução mudou sem querer."""
    base = dict(
        tipo="saida_propria",
        cfop="5102",
        empresa_id=None,
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
        vigencia_fim=None,
        cst_csosn="",
        id_dest="",
        desativada_em=None,
    )
    regras = [
        SimpleNamespace(pk=1, ncm="", ncm_modo="", **base),
        SimpleNamespace(pk=2, ncm="22030000", ncm_modo="exato", **base),
        SimpleNamespace(pk=3, ncm="22", ncm_modo="prefixo", **base),
        SimpleNamespace(pk=4, ncm="2203", ncm_modo="prefixo", **base),
        SimpleNamespace(pk=5, ncm="2203000", ncm_modo="prefixo", **base),
        SimpleNamespace(pk=6, ncm="27101259", ncm_modo="exato", **base),
        SimpleNamespace(pk=7, ncm="2710", ncm_modo="prefixo", **base),
        SimpleNamespace(pk=8, ncm="", ncm_modo="", **{**base, "cfop": "5949"}),
    ]
    contexto = cl.ContextoDeClassificacao(
        escritorio_id=1, empresa_id=7, padrao_combustivel="", regras=tuple(regras)
    )

    for ncm in ("22030000", "22030001", "27101259", "99999999", "", "2203"):
        achadas = {r.pk for r in contexto.candidatas_do_item("5102", ncm)}
        esperadas = {
            r.pk
            for r in regras
            if r.cfop == "5102"
            and (
                not r.ncm
                or (r.ncm_modo == "exato" and ncm == r.ncm)
                or (r.ncm_modo == "prefixo" and ncm.startswith(r.ncm))
            )
        }
        assert achadas == esperadas, (ncm, achadas, esperadas)


def test_a6_previas_numa_passada_sao_iguais_as_avulsas(escritorio_a, gestor, empresa):
    _nota(escritorio_a, gestor, 1)
    _nota(escritorio_a, gestor, 2, cfop=CFOP_REVENDA)
    _ler(empresa)
    completa = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop=CFOP_SEM_SINAL,
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
        ncm=NCM_CERVEJA,
        ncm_modo="exato",
    )
    sem_ncm = replace(completa, ncm="", ncm_modo="")

    em_passada = cl.previas_de_impacto(empresa, ANO, MES, [completa, sem_ncm], "empresa")
    avulsas = [
        cl.previa_de_impacto(empresa, ANO, MES, completa, "empresa"),
        cl.previa_de_impacto(empresa, ANO, MES, sem_ncm, "empresa"),
    ]

    assert em_passada == avulsas


# ---------------------------------------------------------------------------
# A7 (média): o mês confirmado avisa na prévia do lote e na prévia de impacto. Não bloqueia.
# ---------------------------------------------------------------------------


def _confirmar_o_mes(empresa, gestor):
    ConfirmacaoReceitaMensal.objects.create(
        empresa=empresa,
        ano=ANO,
        mes=MES,
        estado=EstadoConfirmacaoMes.CONFIRMADA,
        valor_confirmado_interno=Decimal("0.00"),
        valor_confirmado_externo=Decimal("0.00"),
        confirmada_em=datetime(2026, 4, 2, 10, 0, tzinfo=FUSO),
        confirmada_por=gestor,
    )


def test_a7_previa_do_lote_e_previa_de_impacto_avisam_o_mes_confirmado(
    escritorio_a, gestor, empresa
):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    _confirmar_o_mes(empresa, gestor)

    previa = lote.previa_do_lote(empresa, ANO, MES)
    impacto = cl.previa_de_impacto(
        empresa,
        ANO,
        MES,
        cl.DadosDaRegra(
            tipo="saida_propria",
            cfop=CFOP_SEM_SINAL,
            natureza="revenda",
            vigencia_inicio=date(ANO, MES, 1),
        ),
        "empresa",
    )

    assert previa.mes_confirmado is True
    assert previa.aviso_do_mes == cl.MENSAGEM_MES_CONFIRMADO
    assert impacto.mes_confirmado is True
    assert impacto.aviso_do_mes == cl.MENSAGEM_MES_CONFIRMADO


def test_a7_mes_confirmado_nao_bloqueia_o_lote(escritorio_a, gestor, empresa):
    documento = _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _ler(empresa)
    _confirmar_o_mes(empresa, gestor)

    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))

    assert EscrituracaoNFe.objects.get(vinculo__documento=documento).estado == "efetivada"


def test_a7_tela_do_lote_mostra_o_aviso_do_mes(client, gestor, empresa, escritorio_a):
    notas_sem_sugestao(escritorio_a, gestor, empresa)
    _confirmar_o_mes(empresa, gestor)
    client.force_login(gestor)

    html = client.get(
        reverse("fiscal_web:nfe_lote", args=[empresa.pk]) + f"?ano={ANO}&mes={MES}"
    ).content.decode("utf-8")

    assert "id_aviso_do_mes" in html
    assert "Mês já confirmado" in html


# ---------------------------------------------------------------------------
# A8 (média): origem gravada na escrituração, lista "ver notas", imutabilidade e TRUNCATE.
# ---------------------------------------------------------------------------


def test_a8_nota_efetivada_mostra_a_origem_gravada_e_nao_a_sugestao_de_hoje(
    client, gestor, empresa, escritorio_a
):
    documento = _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _ler(empresa)
    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))
    # Depois da efetivação: uma regra que daria OUTRA natureza à mesma nota.
    _regra(escritorio_a, gestor, empresa, cfop=CFOP_REVENDA, natureza="producao_propria")
    client.force_login(gestor)

    html = client.get(
        reverse(
            "fiscal_web:nfe_escriturar",
            args=[empresa.pk, vinculo(documento, empresa).pk],
        )
    ).content.decode("utf-8")

    assert "Origem gravada: sugestão do produto" in html
    assert "Venda de produção própria" not in html


def test_a8_gatilho_recusa_mudar_origem_de_escrituracao_efetivada(escritorio_a, gestor, empresa):
    documento = _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _ler(empresa)
    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))
    origem = OrigemNaturezaItemNFe.objects.get(
        natureza_item__escrituracao__vinculo__documento=documento
    )

    with pytest.raises(DatabaseError, match="origem da natureza de escrituração"):
        with transaction.atomic():
            OrigemNaturezaItemNFe.objects.filter(pk=origem.pk).update(gravada_em=timezone.now())
    with pytest.raises(DatabaseError, match="origem da natureza de escrituração"):
        with transaction.atomic():
            origem.delete()
    linha = origem.natureza_item
    with pytest.raises(DatabaseError, match="origem da natureza de escrituração"):
        with transaction.atomic():
            OrigemNaturezaItemNFe.objects.create(natureza_item=linha, origem="manual")
    assert OrigemNaturezaItemNFe.objects.filter(pk=origem.pk).exists()


def test_a8_gatilho_deixa_mudar_origem_em_rascunho(escritorio_a, gestor, empresa):
    documento = _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _rascunho_com_natureza(empresa, gestor, documento, "revenda")

    trocadas = OrigemNaturezaItemNFe.objects.filter(
        natureza_item__escrituracao__vinculo__documento=documento
    ).update(origem="produto", regra_classificacao=None)

    assert trocadas == 1


def test_a8_truncate_da_regra_recusa_com_linha(escritorio_a, gestor, empresa):
    _regra(escritorio_a, gestor, empresa)
    with pytest.raises(DatabaseError, match="não podem ser truncadas"):
        with transaction.atomic(), connection.cursor() as cursor:
            # Eventos de gatilho pendentes da própria transação do teste impedem o TRUNCATE antes do
            # gatilho; as restrições passam a ser imediatas, e o gatilho de TRUNCATE é o que decide.
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("TRUNCATE fiscal_regraclassificacaonfe CASCADE")
    assert RegraClassificacaoNFe.objects.count() == 1

    # Tabela vazia pode ser truncada: é o que o `flush` dos testes transacionais faz.
    OrigemNaturezaItemNFe.objects.all().delete()
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        cursor.execute("TRUNCATE fiscal_origemnaturezaitemnfe")


def test_a8_reversao_da_0020_recusa_com_origem_de_efetivada_e_nao_com_rascunho(
    escritorio_a, gestor, empresa
):
    """A9: a guarda da origem recusa origem de nota EFETIVADA. Origem de rascunho é provisória e não
    recusa (a natureza ainda pode mudar)."""
    documento = _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    M20._recusar_reversao_com_origens(registro_de_apps, None)

    _ler(empresa)
    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))
    with pytest.raises(RuntimeError, match="origem\\(ns\\) de natureza de NF-e de escrituração"):
        M20._recusar_reversao_com_origens(registro_de_apps, None)


def test_a9_volta_pelo_comando_migrate_recusa_com_regra_e_com_origem(escritorio_a, gestor, empresa):
    """O comando `migrate fiscal 0018` (volta) recusa, sem alterar nada, com regra e com origem."""
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.recorder import MigrationRecorder

    def aplicadas():
        return {
            nome
            for app, nome in MigrationRecorder(connection).applied_migrations()
            if app == "fiscal"
        }

    _regra(escritorio_a, gestor, None, cfop=CFOP_SEM_SINAL)
    with pytest.raises(RuntimeError, match="1 regra"):
        call_command("migrate", "fiscal", "0018", verbosity=0)
    assert "0020_dl087_origem_da_natureza_confirmada" in aplicadas()

    _nota(escritorio_a, gestor, 1, cfop=CFOP_REVENDA)
    _ler(empresa)
    confirmar_tudo(empresa, gestor, ANO, MES, previa_lida(empresa, ANO, MES))
    with pytest.raises(RuntimeError, match="origem\\(ns\\)"):
        call_command("migrate", "fiscal", "0018", verbosity=0)
    assert {
        "0019_dl087_regra_de_classificacao_nfe",
        "0020_dl087_origem_da_natureza_confirmada",
    } <= aplicadas()
    assert RegraClassificacaoNFe.objects.count() == 1
    assert OrigemNaturezaItemNFe.objects.count() == 1


def test_a8_lista_de_notas_da_regra_na_api_filtra_pela_empresa_e_pagina(
    client, gestor, empresa, outra_empresa, escritorio_a
):
    regra = _regra(escritorio_a, gestor, None, cfop=CFOP_SEM_SINAL)
    for numero in (1, 2):
        documento = _nota(escritorio_a, gestor, numero)
        _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    client.force_login(gestor)

    primeira = client.get(
        _url_api("nfe_classificacao_regra_notas", empresa.pk, regra.pk), {"tamanho": 1}
    ).json()
    segunda = client.get(
        _url_api("nfe_classificacao_regra_notas", empresa.pk, regra.pk),
        {"tamanho": 1, "pagina": 2},
    ).json()
    da_outra = client.get(
        _url_api("nfe_classificacao_regra_notas", outra_empresa.pk, regra.pk)
    ).json()

    assert primeira["total"] == 2 and len(primeira["notas"]) == 1
    assert segunda["total"] == 2 and len(segunda["notas"]) == 1
    assert primeira["notas"][0]["numero"] != segunda["notas"][0]["numero"]
    assert primeira["notas"][0]["origem"] == "regra"
    assert da_outra["total"] == 0


def test_a8_lista_de_notas_da_regra_com_paginacao_invalida_e_400(
    client, gestor, empresa, escritorio_a
):
    regra = _regra(escritorio_a, gestor, None, cfop=CFOP_SEM_SINAL)
    client.force_login(gestor)

    for params in ({"pagina": 0}, {"tamanho": 1000}, {"pagina": "x"}):
        resposta = client.get(
            _url_api("nfe_classificacao_regra_notas", empresa.pk, regra.pk), params
        )
        assert resposta.status_code == 400, params


def test_ver_notas_da_regra_lista_so_a_empresa_da_url(
    client, gestor, empresa, outra_empresa, escritorio_a
):
    regra = _regra(escritorio_a, gestor, None, cfop=CFOP_SEM_SINAL)
    documento = _nota(escritorio_a, gestor, 1)
    _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    client.force_login(gestor)

    da_empresa = client.get(
        reverse("fiscal_web:classificacao_regra_notas", args=[empresa.pk, regra.pk])
    ).content.decode("utf-8")
    da_outra = client.get(
        reverse("fiscal_web:classificacao_regra_notas", args=[outra_empresa.pk, regra.pk])
    ).content.decode("utf-8")

    assert "nº 1, série" in da_empresa
    assert "Nenhuma nota confirmada a partir desta regra" in da_outra


def test_ver_notas_de_regra_de_outra_empresa_responde_404(
    client, gestor, empresa, outra_empresa, escritorio_a
):
    regra_da_empresa = _regra(escritorio_a, gestor, empresa, cfop=CFOP_SEM_SINAL)
    client.force_login(gestor)

    resposta = client.get(
        reverse(
            "fiscal_web:classificacao_regra_notas", args=[outra_empresa.pk, regra_da_empresa.pk]
        )
    )

    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# A10 (baixa): sem regra que case, a resolução é IGUAL à embutida, em todo CFOP sem ponto.
# ---------------------------------------------------------------------------


def test_a10_sem_regra_que_case_a_resolucao_e_igual_a_embutida_em_todo_cfop():
    """Usa CFOP SEM ponto (como chega da nota) e regras no mesmo CFOP com NCM que não casa. O
    contexto tem regra: a resolução tem de cair na embutida, com a mesma natureza e o mesmo motivo.
    """
    cfops = sorted(codigo.replace(".", "") for codigo in tabela._tabela())
    assert "5102" in cfops and "5949" in cfops
    regras = tuple(
        SimpleNamespace(
            **{
                **_regra_fake(numero, natureza="revenda").__dict__,
                "cfop": codigo,
                "ncm": NCM_QUE_NAO_CASA,
                "ncm_modo": "exato",
            }
        )
        for numero, codigo in enumerate(cfops, start=1)
    )
    contexto = cl.ContextoDeClassificacao(
        escritorio_id=1, empresa_id=7, padrao_combustivel="posto", regras=regras
    )
    dia = datetime(2026, 3, 15, 10, tzinfo=FUSO)
    comparadas = 0
    for codigo in cfops:
        assert contexto.candidatas_do_item(codigo, NCM_CERVEJA) == []
        for fin, tipo in (("1", "saida_propria"), ("4", "devolucao")):
            for csosn in ("102", "500", "201"):
                for id_dest in ("1", "3"):
                    documento = SimpleNamespace(
                        modelo="55",
                        tp_nf="1" if fin == "1" else "0",
                        fin_nfe=fin,
                        id_dest=id_dest,
                        transferencia_entre_estabelecimentos=False,
                        dh_emissao=dia,
                    )
                    item = SimpleNamespace(cfop=codigo, ncm=NCM_CERVEJA, csosn=csosn, cst=None)
                    com_regra = cl.sugerir_natureza_com_regras(contexto, documento, item, tipo)
                    embutida = servico.sugerir_natureza_com_padrao(documento, item, "posto", tipo)
                    assert (com_regra.natureza, com_regra.motivo) == (
                        embutida.natureza,
                        embutida.motivo,
                    ), (codigo, fin, csosn, id_dest)
                    comparadas += 1
    assert comparadas == len(cfops) * 2 * 3 * 2


# ---------------------------------------------------------------------------
# A11 (baixa): origem na reclassificação em massa; natureza escolhida continua selecionada.
# ---------------------------------------------------------------------------


def test_a11_reclassificacao_em_massa_grava_origem_regra_e_depois_manual(
    escritorio_a, gestor, empresa
):
    regra = _regra(escritorio_a, gestor, empresa, cfop=CFOP_SEM_SINAL, natureza="revenda")
    documento = _nota(escritorio_a, gestor, 1)
    escrituracao = servico.criar_rascunho(vinculo(documento, empresa), usuario=gestor)
    filtros = servico.FiltrosReclassificacao(cfop=CFOP_SEM_SINAL)

    servico.reclassificar_em_massa(empresa, "revenda", filtros, gestor)
    origem = OrigemNaturezaItemNFe.objects.get(natureza_item__escrituracao=escrituracao)
    assert (origem.origem, origem.regra_classificacao_id) == ("regra", regra.pk)

    servico.reclassificar_em_massa(empresa, "producao_propria", filtros, gestor)
    origem.refresh_from_db()
    assert (origem.origem, origem.regra_classificacao_id) == ("manual", None)


def test_a11_natureza_escolhida_continua_selecionada_depois_de_regra_nova(
    client, gestor, empresa, escritorio_a
):
    documento = _nota(escritorio_a, gestor, 1)
    escrituracao = _rascunho_com_natureza(empresa, gestor, documento, "revenda")
    assert escrituracao.estado == "rascunho"
    _regra(escritorio_a, gestor, empresa, cfop=CFOP_SEM_SINAL, natureza="producao_propria")
    client.force_login(gestor)

    html = client.get(
        reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo(documento, empresa).pk])
    ).content.decode("utf-8")

    assert '<option value="revenda" selected>' in html
    assert '<option value="producao_propria" selected>' not in html


# ---------------------------------------------------------------------------
# A12 (baixa): as regras do produto descrevem os sufixos de CFOP que o código usa.
# ---------------------------------------------------------------------------


def test_a12_regras_do_produto_citam_os_sufixos_que_o_codigo_usa():
    sufixos = servico._CFOP_SEM_SUGESTAO
    linha = next(r for r in cl.REGRAS_DO_PRODUTO if "comercial exportadora" in r["sinal"])
    for sufixo in sufixos:
        assert f"x.{sufixo}" in linha["sinal"], sufixo
    assert "5501" not in linha["sinal"]


def test_a12_cada_regra_do_produto_tem_sinal_resultado_e_fonte():
    for linha in cl.REGRAS_DO_PRODUTO:
        assert linha["sinal"] and linha["resultado"] and linha["fonte"], linha
        assert "test_dl087_produto" not in linha["fonte"]


# ---------------------------------------------------------------------------
# A13 (baixa): Enter, botão de "criar regra" da fila, paginação da lista.
# ---------------------------------------------------------------------------


def _primeiro_botao_de_envio(html: str, url_do_formulario: str) -> str:
    """Primeiro botão do formulário da regra. A `action` o identifica, não o cabeçalho."""
    formulario_inicio = html.index(f'<form method="post" action="{url_do_formulario}"')
    botao = html.index("<button", formulario_inicio)
    return html[botao : html.index(">", botao) + 1]


def test_a13_enter_no_formulario_nao_dispara_atualizar(client, gestor, empresa):
    from apps.fiscal.tests.test_dl087_telas import url_nova

    client.force_login(gestor)
    html = client.get(url_nova(empresa)).content.decode("utf-8")

    primeiro = _primeiro_botao_de_envio(html, url_nova(empresa))
    assert 'name="acao" value="previa"' in primeiro
    assert "atualizar" not in primeiro


def test_a13_enter_de_quem_so_consulta_nao_envia_nada(client, paralegal, empresa):
    from apps.fiscal.tests.test_dl087_telas import url_nova

    client.force_login(paralegal)
    html = client.get(url_nova(empresa)).content.decode("utf-8")

    assert "disabled" in _primeiro_botao_de_envio(html, url_nova(empresa))


def test_a13_criar_regra_da_fila_e_botao_secundario_pequeno(client, gestor, empresa, escritorio_a):
    from apps.fiscal.tests.test_dl087_telas import url_fila

    notas_sem_sugestao(escritorio_a, gestor, empresa)
    client.force_login(gestor)

    html = client.get(url_fila(empresa)).content.decode("utf-8")

    assert 'class="botao botao--secundario botao--pequeno" href="' in html
    assert "botao--primario botao--pequeno" not in html


def test_a13_lista_de_regras_pagina_com_vinte_e_cinco_por_pagina(
    client, gestor, empresa, escritorio_a
):
    from apps.fiscal.tests.test_dl087_telas import url_regras

    cfops = [codigo.replace(".", "") for codigo in sorted(tabela._tabela())][:26]
    for codigo in cfops:
        _regra(escritorio_a, gestor, None, cfop=codigo)
    client.force_login(gestor)

    primeira = client.get(url_regras(empresa)).content.decode("utf-8")
    segunda = client.get(url_regras(empresa) + "?pagina=2").content.decode("utf-8")

    assert len(re.findall(r'<tr id="regra-\d+"', primeira)) == 25
    assert len(re.findall(r'<tr id="regra-\d+"', segunda)) == 1
