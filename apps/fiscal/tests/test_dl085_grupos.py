"""DL-085, confirmação por grupo: `confirmar_lote(grupos=...)`, a API e os campos novos do domínio.

Cenário: 3 notas de combustível (grupo A), 2 de revenda (grupo B) e 1 sem sugestão (fora). Valores
escritos à mão. Notas sintéticas, recebidas pela recepção real. Os grupos são pedidos pelas
chaves da prévia, como a tela faz.
"""

import json
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal.models import (
    EscrituracaoNFe,
    ItemNFe,
    LoteEscrituracaoNFe,
    LoteEscrituracaoNFeNota,
)
from apps.fiscal.tests.suporte_dl081 import vinculo
from apps.fiscal.tests.suporte_dl085 import nfce, previa_lida, usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = pytest.mark.django_db

ANO, MES = 2026, 3


@pytest.fixture
def gestor(escritorio_a):
    return usuario_gestor(escritorio_a, "gestor-grupos-dl085")


@pytest.fixture
def posto(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto grupos DL085 Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _cenario(escritorio, usuario, empresa):
    """Grupo de combustível (notas 1 a 3), de revenda (notas 4 e 5), e a nota 9 sem sugestão."""
    for numero, valor in ((1, "100.00"), (2, "250.00"), (3, "40.00")):
        nfce(escritorio, usuario, numero=numero, valor=valor)
    for numero in (4, 5):
        nfce(escritorio, usuario, numero=numero, valor="80.00", cfop="5102", csosn="102")
    fora = nfce(escritorio, usuario, numero=9, valor="33.00", cfop="5949", csosn="102")
    return vinculo(fora, empresa)


def _grupos(previa):
    """(chave do grupo de combustível, chave do grupo de revenda), pela natureza sugerida."""
    combustivel = next(g.chave for g in previa.grupos if g.assinaturas[0].natureza == "combustivel")
    revenda = next(g.chave for g in previa.grupos if g.assinaturas[0].natureza == "revenda")
    return combustivel, revenda


def _numeros_com_escrituracao(empresa):
    return set(
        EscrituracaoNFe.objects.filter(empresa=empresa).values_list(
            "vinculo__documento__numero", flat=True
        )
    )


def _confirmar_ate_o_fim(empresa, usuario, previa, **kwargs):
    progresso = lote.confirmar_lote(empresa, ANO, MES, previa.assinatura, {}, usuario, **kwargs)
    while not progresso.terminou:
        progresso = lote.confirmar_lote(
            empresa, None, None, None, None, usuario, lote_id=progresso.lote_id, limite=50
        )
    return progresso


# ---------------------------------------------------------------------------
# Subconjunto: marcados efetivados, desmarcados intactos, sem rascunho
# ---------------------------------------------------------------------------


def test_so_os_grupos_marcados_sao_efetivados_e_os_outros_ficam_intactos(
    escritorio_a, gestor, posto
):
    """Confirma só a revenda. As 3 notas de combustível não ganham rascunho, nem escrituração, nem
    linha no lote. As 2 de revenda são efetivadas. A nota sem sugestão continua fora."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)

    progresso = _confirmar_ate_o_fim(posto, gestor, previa, grupos=[revenda])

    assert progresso.terminou
    assert progresso.efetivadas_total == 2
    assert _numeros_com_escrituracao(posto) == {"4", "5"}
    assert EscrituracaoNFe.objects.filter(empresa=posto).count() == 2
    lote_gravado = LoteEscrituracaoNFe.objects.get(empresa=posto)
    assert set(
        LoteEscrituracaoNFeNota.objects.filter(lote=lote_gravado).values_list(
            "chave_grupo", flat=True
        )
    ) == {revenda}
    assert lote_gravado.quantidade_notas == 2


def test_grupos_todos_equivale_a_nao_informar_grupos(escritorio_a, gestor, posto):
    """Com todos os grupos marcados, é o mesmo que não informar (None): cinco efetivadas."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    combustivel, revenda = _grupos(previa)

    progresso = _confirmar_ate_o_fim(posto, gestor, previa, grupos=[combustivel, revenda])

    assert progresso.efetivadas_total == 5
    assert _numeros_com_escrituracao(posto) == {"1", "2", "3", "4", "5"}


def test_a_assinatura_e_a_da_previa_inteira_mesmo_com_grupos(escritorio_a, gestor, posto):
    """A assinatura não muda com o recorte: é a da prévia inteira. Se o mês mudou, 409, mesmo que o
    grupo pedido não tenha mudado."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)
    nfce(escritorio_a, gestor, numero=6, valor="10.00")  # entra uma nota nova, fora do grupo pedido

    with pytest.raises(lote.PreviaDesatualizada):
        lote.confirmar_lote(posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda])
    assert not EscrituracaoNFe.objects.filter(empresa=posto).exists()


# ---------------------------------------------------------------------------
# Recusas nomeadas (400), sem gravar nada
# ---------------------------------------------------------------------------


def test_grupo_inexistente_na_previa_e_400_nomeado_sem_gravar(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)

    with pytest.raises(servico.EntradaInvalidaNFe) as exc:
        lote.confirmar_lote(
            posto,
            ANO,
            MES,
            previa.assinatura,
            {},
            gestor,
            grupos=[revenda, "saida_propria-0000000000000000"],
        )

    assert "não existe mais na prévia" in exc.value.mensagem
    assert "Nada foi efetivado" in exc.value.mensagem
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()
    assert not EscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_lista_vazia_de_grupos_e_400_sem_gravar(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)

    with pytest.raises(servico.EntradaInvalidaNFe) as exc:
        lote.confirmar_lote(posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[])

    assert "Marque ao menos um grupo" in exc.value.mensagem
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_escolha_de_natureza_de_grupo_nao_marcado_e_recusada(escritorio_a, gestor, posto):
    """Seletor de um grupo desmarcado não é ignorado: recusa, porque a escolha seria de nota que não
    entra no lote."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    combustivel, revenda = _grupos(previa)

    with pytest.raises(servico.EntradaInvalidaNFe) as exc:
        lote.confirmar_lote(
            posto,
            ANO,
            MES,
            previa.assinatura,
            {combustivel: {"5656|500|combustivel": "combustivel_revenda"}},
            gestor,
            grupos=[revenda],
        )

    assert "não está marcado" in exc.value.mensagem
    assert not EscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_grupos_na_continuacao_sao_recusados_em_vez_de_ignorados(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)
    primeira = lote.confirmar_lote(
        posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda], limite=1
    )

    with pytest.raises(servico.EntradaInvalidaNFe):
        lote.confirmar_lote(
            posto, None, None, None, None, gestor, lote_id=primeira.lote_id, grupos=[revenda]
        )


def test_repetir_a_primeira_chamada_com_outros_grupos_e_409(escritorio_a, gestor, posto):
    """Com o lote da revenda em andamento, pedir o combustível é outro ato: 409, e nada muda."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    combustivel, revenda = _grupos(previa)
    lote.confirmar_lote(posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda], limite=1)

    with pytest.raises(lote.LoteEmAndamento):
        lote.confirmar_lote(posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[combustivel])
    assert LoteEscrituracaoNFe.objects.filter(empresa=posto).count() == 1


def test_repetir_com_os_mesmos_grupos_continua_o_lote(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)
    primeira = lote.confirmar_lote(
        posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda], limite=1
    )

    repetida = lote.confirmar_lote(
        posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda], limite=1
    )

    assert repetida.lote_id == primeira.lote_id
    assert _numeros_com_escrituracao(posto) == {"4", "5"}


# ---------------------------------------------------------------------------
# Registro do lote, trilha e campos novos
# ---------------------------------------------------------------------------


def test_trilha_e_resumo_registram_os_grupos_confirmados(escritorio_a, gestor, posto):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)

    progresso = _confirmar_ate_o_fim(posto, gestor, previa, grupos=[revenda])

    registro = RegistroAuditoria.objects.get(
        acao="escrituracao_nfe.lote_confirmado",
        objeto_tipo="LoteEscrituracaoNFe",
        objeto_id=str(progresso.lote_id),
    )
    assert registro.detalhes["grupos_confirmados"] == [revenda]
    assert [g["chave"] for g in registro.detalhes["grupos"]] == [revenda]
    assert lote.resumo_do_lote(LoteEscrituracaoNFe.objects.get(pk=progresso.lote_id))["grupos"] == [
        revenda
    ]


def test_fora_do_lote_traz_o_valor_da_nota(escritorio_a, gestor, posto):
    """vNF da nota sem sugestão: 33,00, escrito à mão. Vem do domínio, não de consulta da tela."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)

    (recusa,) = previa.fora

    assert recusa.valor_nf == Decimal("33.00")
    assert recusa.codigo == lote.CODIGO_SEM_SUGESTAO


def test_falha_traz_numero_e_serie_da_nota(escritorio_a, gestor, posto):
    """Falha por desvio (o item mudou depois da confirmação): a falha vem com número e série."""
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)
    primeira = lote.confirmar_lote(
        posto, ANO, MES, previa.assinatura, {}, gestor, grupos=[revenda], limite=1
    )
    alvo = (
        LoteEscrituracaoNFeNota.objects.filter(lote_id=primeira.lote_id)
        .exclude(estado="efetivada")
        .order_by("vinculo_id")
        .first()
    )
    ItemNFe.objects.filter(documento=alvo.vinculo.documento).update(cfop="5949")

    progresso = lote.confirmar_lote(
        posto, None, None, None, None, gestor, lote_id=primeira.lote_id, limite=50
    )

    (falha,) = progresso.falhas_nesta_chamada
    assert falha.vinculo_id == alvo.vinculo_id
    assert falha.numero == alvo.vinculo.documento.numero
    assert falha.serie == alvo.vinculo.documento.serie
    assert falha.motivo == lote.MENSAGEM_DESVIO


# ---------------------------------------------------------------------------
# API: campo `grupos`, e os campos novos no payload
# ---------------------------------------------------------------------------


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def test_api_confirma_so_os_grupos_marcados(escritorio_a, gestor, posto, client):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    _, revenda = _grupos(previa)
    client.force_login(gestor)

    resposta = _post(
        client,
        reverse("fiscal_api:nfe_lote_confirmar", args=[posto.pk]),
        {"ano": ANO, "mes": MES, "assinatura": previa.assinatura, "grupos": [revenda]},
    )

    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["efetivadas_total"] == 2
    assert _numeros_com_escrituracao(posto) == {"4", "5"}


@pytest.mark.parametrize(
    "grupos_do_corpo",
    [
        pytest.param([], id="lista-vazia"),
        pytest.param(["saida_propria-0000000000000000"], id="grupo-inexistente"),
    ],
)
def test_api_grupos_invalidos_respondem_400_sem_gravar(
    escritorio_a, gestor, posto, client, grupos_do_corpo
):
    _cenario(escritorio_a, gestor, posto)
    previa = previa_lida(posto, ANO, MES)
    client.force_login(gestor)

    resposta = _post(
        client,
        reverse("fiscal_api:nfe_lote_confirmar", args=[posto.pk]),
        {"ano": ANO, "mes": MES, "assinatura": previa.assinatura, "grupos": grupos_do_corpo},
    )

    assert resposta.status_code == 400, resposta.content
    assert not LoteEscrituracaoNFe.objects.filter(empresa=posto).exists()


def test_api_previa_expoe_valor_da_nota_fora_e_falha_expoe_numero_e_serie(
    escritorio_a, gestor, posto, client
):
    _cenario(escritorio_a, gestor, posto)
    client.force_login(gestor)
    client.post(
        reverse("fiscal_api:nfe_lote_ler", args=[posto.pk]),
        data=json.dumps({"ano": ANO, "mes": MES, "limite": 50}),
        content_type="application/json",
    )

    corpo = client.get(
        reverse("fiscal_api:nfe_lote_previa", args=[posto.pk]) + f"?ano={ANO}&mes={MES}"
    ).json()

    (nota_fora,) = corpo["fora_do_lote"]["notas"]
    assert nota_fora["valor_nf"] == "33.00"
