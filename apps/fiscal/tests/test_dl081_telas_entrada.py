"""DL-081, frente B: entrada estranha nas telas da escrituração de NF-e responde 400 com mensagem.

Byte nulo, número gigante, data fora de faixa e campo fora do contrato NUNCA viram 500: o banco
(PostgreSQL) recusaria com erro de servidor. Cada caso acima do limite é recusado antes do banco.
"""

import html
from urllib.parse import urlencode

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal.models import EscrituracaoNFe
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel, vinculo
from apps.fiscal.tests.test_dl081_telas import _escriturar_com_o_exemplo, simples
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

GIGANTE = "9" * 5000


@pytest.fixture
def gestor(escritorio_a):
    return usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-entrada-dl081")


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Entrada DL081 Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def nota(client, gestor, emitente, escritorio_a):
    """Nota do exemplo do Simples, EFETIVADA: os testes de estorno e de entrada precisam dela."""
    client.force_login(gestor)
    vinculo_ = vinculo(receber(escritorio_a, gestor, simples(numero="1")), emitente)
    _escriturar_com_o_exemplo(client, emitente, vinculo_)
    client.post(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, vinculo_.pk]), {"acao": "efetivar"}
    )
    return vinculo_


def _lista(emp, **consulta):
    base = {"empresa": emp.pk, "ano": 2026, "mes": 3}
    base.update(consulta)
    return reverse("fiscal_web:nfe_a_escriturar") + "?" + urlencode(base)


def _texto(resposta):
    """HTML sem entidades: o template escapa a aspa simples (`&#x27;`), e o contador lê a aspa."""
    return html.unescape(resposta.content.decode("utf-8"))


def _recusado(resposta, trecho):
    assert resposta.status_code == 400, resposta.content[:300]
    assert trecho in _texto(resposta)


def test_byte_nulo_na_empresa_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.get(reverse("fiscal_web:nfe_a_escriturar") + "?empresa=%00&ano=2026&mes=3")

    _recusado(resposta, "tem caractere inválido")


def test_numero_gigante_na_empresa_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.get(
        reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={GIGANTE}&ano=2026&mes=3"
    )

    _recusado(resposta, "'Empresa' tem no máximo 20 caracteres.")


def test_identificador_de_empresa_acima_do_bigint_responde_400_antes_do_banco(client, gestor):
    client.force_login(gestor)

    resposta = client.get(
        reverse("fiscal_web:nfe_a_escriturar") + "?empresa=99999999999999999999&ano=2026&mes=3"
    )

    assert resposta.status_code == 400
    assert "Identificador fora da faixa aceita." in _texto(resposta) or (
        "'Empresa' inválida." in _texto(resposta)
    )


def test_empresa_no_caminho_acima_do_bigint_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.get(reverse("fiscal_web:nfe_escriturar", args=[99999999999999999999, 1]))

    _recusado(resposta, "Identificador fora da faixa aceita.")


def test_nota_no_caminho_acima_do_bigint_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.get(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, 99999999999999999999])
    )

    _recusado(resposta, "Identificador fora da faixa aceita.")


def test_escrituracao_no_caminho_acima_do_bigint_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_estornar", args=[emitente.pk, 99999999999999999999]),
        {"motivo": "teste"},
    )

    _recusado(resposta, "Identificador fora da faixa aceita.")


def test_ano_gigante_responde_400_antes_do_int(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.get(_lista(emitente, ano=GIGANTE))

    _recusado(resposta, "'Ano' tem no máximo 4 caracteres.")


@pytest.mark.parametrize("ano", ["1999", "2101", "abcd"])
def test_ano_fora_da_faixa_ou_nao_numerico_responde_400(client, gestor, emitente, ano):
    client.force_login(gestor)

    resposta = client.get(_lista(emitente, ano=ano))

    _recusado(resposta, "Competência inválida")


def test_mes_treze_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    _recusado(client.get(_lista(emitente, mes="13")), "Competência inválida")


@pytest.mark.parametrize(
    "inicio",
    ["01/01/0001", "31/12/9999", "2026-03-01", "29/02/2026"],
)
def test_data_fora_de_faixa_ou_formato_errado_na_reclassificacao_responde_400(
    client, gestor, emitente, inicio
):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {"empresa": emitente.pk, "natureza": "revenda", "acao": "previa", "inicio": inicio},
    )

    assert resposta.status_code == 400
    assert "'Período de'" in _texto(resposta)


def test_periodo_com_inicio_depois_do_fim_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {
            "empresa": emitente.pk,
            "natureza": "revenda",
            "acao": "previa",
            "inicio": "10/03/2026",
            "fim": "01/03/2026",
        },
    )

    _recusado(resposta, "'Período de' não pode ser posterior a 'Período até'.")


@pytest.mark.parametrize(
    ("campo", "valor", "mensagem"),
    [
        ("cfop", "51", "'CFOP' deve ter exatamente 4 dígitos"),
        ("cfop", "51a2", "'CFOP' deve ter exatamente 4 dígitos"),
        ("cst_csosn", "1", "'CST/CSOSN' deve ter 2 ou 3 dígitos"),
        ("ncm", "2203", "'NCM' deve ter exatamente 8 dígitos"),
        ("ncm", "2203000\x00", "'NCM' tem caractere inválido."),
    ],
)
def test_codigo_fiscal_com_formato_errado_responde_400(
    client, gestor, emitente, campo, valor, mensagem
):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {"empresa": emitente.pk, "natureza": "revenda", "acao": "previa", campo: valor},
    )

    _recusado(resposta, mensagem)


def test_natureza_com_byte_nulo_ou_gigante_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    nula = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {"empresa": emitente.pk, "natureza": "revenda\x00", "acao": "previa"},
    )
    gigante = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {"empresa": emitente.pk, "natureza": GIGANTE, "acao": "previa"},
    )

    _recusado(nula, "'Natureza' tem caractere inválido.")
    _recusado(gigante, "'Natureza' tem no máximo 24 caracteres.")


def test_natureza_desconhecida_responde_400_sem_ecoar_o_valor(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {"empresa": emitente.pk, "natureza": "xyz-injetado", "acao": "previa"},
    )

    assert resposta.status_code == 400
    assert "xyz-injetado" not in _texto(resposta)


def test_motivo_de_estorno_com_byte_nulo_responde_400_e_nada_muda(client, gestor, nota, emitente):
    escrituracao = EscrituracaoNFe.objects.get(vinculo=nota, estado="efetivada")

    resposta = client.post(
        reverse("fiscal_web:nfe_estornar", args=[emitente.pk, escrituracao.pk]),
        {"motivo": "motivo\x00"},
    )

    _recusado(resposta, "'Motivo do estorno' tem caractere inválido.")
    escrituracao.refresh_from_db()
    assert escrituracao.estado == "efetivada"


def test_motivo_de_estorno_gigante_responde_400(client, gestor, nota, emitente):
    escrituracao = EscrituracaoNFe.objects.get(vinculo=nota, estado="efetivada")

    resposta = client.post(
        reverse("fiscal_web:nfe_estornar", args=[emitente.pk, escrituracao.pk]),
        {"motivo": GIGANTE},
    )

    _recusado(resposta, "O motivo do estorno tem no máximo 500 caracteres.")


def test_item_id_gigante_responde_400(client, gestor, nota, emitente):
    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, nota.pk]),
        {"acao": "item", "item_id": "9" * 30, "natureza": "revenda"},
    )

    _recusado(resposta, "'Item' tem no máximo 19 caracteres.")


def test_acao_desconhecida_responde_400(client, gestor, nota, emitente):
    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, nota.pk]), {"acao": "apagar"}
    )

    _recusado(resposta, "Ação desconhecida na escrituração de NF-e.")


def test_previstas_nao_numericas_na_confirmacao_responde_400(client, gestor, emitente):
    client.force_login(gestor)

    resposta = client.post(
        reverse("fiscal_web:nfe_reclassificar"),
        {
            "empresa": emitente.pk,
            "natureza": "revenda",
            "acao": "confirmar",
            "previstas_notas": "um",
            "previstos_itens": "2",
        },
    )

    _recusado(resposta, "'Notas' inválido.")


def test_campo_fora_do_contrato_responde_400(client, gestor, nota, emitente):
    resposta = client.post(
        reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, nota.pk]),
        {"acao": "criar", "campo_inventado": "x"},
    )

    assert resposta.status_code == 400


def test_entrada_estranha_nunca_responde_500(client, gestor, nota, emitente):
    """Varredura de entradas ruins nas quatro telas que recebem dados: nenhuma vira 500."""
    client.force_login(gestor)
    escrituracao = EscrituracaoNFe.objects.get(vinculo=nota, estado="efetivada")
    casos = [
        (reverse("fiscal_web:nfe_a_escriturar") + f"?empresa={GIGANTE}", "get"),
        (reverse("fiscal_web:nfe_conferencia") + "?empresa=\x00&ano=2026&mes=3", "get"),
        (reverse("fiscal_web:nfe_reclassificar") + "?empresa=%00", "get"),
        (reverse("fiscal_web:nfe_escriturar", args=[emitente.pk, 10**19]), "get"),
        (reverse("fiscal_web:nfe_estornar", args=[emitente.pk, escrituracao.pk]), "post"),
    ]
    for url, metodo in casos:
        resposta = client.get(url) if metodo == "get" else client.post(url, {"motivo": "\x00\x00"})
        assert resposta.status_code < 500, url
