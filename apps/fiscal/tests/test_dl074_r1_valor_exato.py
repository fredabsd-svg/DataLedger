"""DL-074 — R1 da reconferência (docs/auditorias/2026-10-08-dl-074-reconferencia.md).

Valor com mais de duas casas decimais era normalizado antes da conferência: "10.000"
virava 10,00 e a tela confirmava R$ 10,00 (ou "1,000" virava R$ 1,00). Agora o serviço
recusa qualquer valor com mais de duas casas sem normalizar, e a tela e a API recusam a
mesma forma com mensagem útil. Dados sintéticos; os valores esperados estão escritos à mão.

Três portas: serviço (`apps.fiscal.receita`), tela (POST com acao=confirmar) e API (400).
"""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.fiscal import receita as servico
from apps.fiscal.models import EstadoReceitaInformada, MercadoReceita, ReceitaInformada
from apps.fiscal.tests.test_dl074_suporte import ORIGEM_OUTRAS

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO

# Formas que o contador digita e que NÃO podem gravar valor com centavos inventados.
FORMAS_AMBIGUAS = ["10.000", "1.500", "1.234.567", "1,000", "10,000", "1.000,000"]


def _lancar(empresa, usuario, valor):
    return servico.lancar_receita_informada(
        empresa,
        2026,
        5,
        INTERNO,
        valor,
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        "Suporte sintético.",
        usuario,
        situacao_iss="proprio_municipio",
    )


def _lancamento_valido(**sobrescritas):
    dados = {
        "ano": "2026",
        "mes": "05",
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": "100,00",
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "acao": "rascunho",
    }
    dados.update(sobrescritas)
    return dados


def _url_lancar(empresa):
    return reverse("fiscal_web:receita_informada_nova", args=[empresa.pk])


def _base_api(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


# ---------------------------------------------------------------------------
# Porta 1 — serviço
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["10.000", "1.500", "1000.000", "10.0000", "0.001"])
def test_r1_servico_recusa_mais_de_duas_casas_mesmo_com_zero_a_direita(
    empresa_a, usuario_gestor_a, valor
):
    # "10.000" era normalizado para 10,00. Três casas são recusadas, mesmo com o último zero.
    with pytest.raises(servico.EntradaInvalidaReceita, match="use vírgula para os centavos"):
        _lancar(empresa_a, usuario_gestor_a, valor)

    assert ReceitaInformada.objects.count() == 0


def test_r1_servico_recusa_decimal_com_tres_casas_passado_direto(empresa_a, usuario_gestor_a):
    # Quem chama o serviço com Decimal (API, futura importação) passa pela mesma regra.
    with pytest.raises(servico.EntradaInvalidaReceita, match="no máximo duas casas decimais"):
        _lancar(empresa_a, usuario_gestor_a, Decimal("10.000"))

    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        ("10000", "10000.00"),
        ("10.50", "10.50"),
        ("10.00", "10.00"),
        ("1000.50", "1000.50"),
        ("0.10", "0.10"),
        (Decimal("10.5"), "10.50"),
    ],
)
def test_r1_servico_aceita_o_que_tem_no_maximo_duas_casas(
    empresa_a, usuario_gestor_a, valor, esperado
):
    receita = _lancar(empresa_a, usuario_gestor_a, valor)

    assert receita.valor == Decimal(esperado)
    assert ReceitaInformada.objects.count() == 1


@pytest.mark.parametrize("valor", ["1,000", "10,000", "1.000,000"])
def test_r1_servico_recusa_texto_com_virgula_que_nao_e_decimal_valido(
    empresa_a, usuario_gestor_a, valor
):
    # O serviço só recebe o texto já convertido pela tela (a vírgula vira ponto lá). Texto
    # com vírgula que chega direto é recusado como valor inválido, sem gravar nada.
    with pytest.raises(servico.EntradaInvalidaReceita):
        _lancar(empresa_a, usuario_gestor_a, valor)

    assert ReceitaInformada.objects.count() == 0


# ---------------------------------------------------------------------------
# Porta 2 — tela (POST com acao=confirmar não grava nada nas formas ambíguas)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("digitado", FORMAS_AMBIGUAS)
def test_r1_tela_recusa_forma_ambigua_com_confirmar_e_nao_grava(
    client, empresa_a, usuario_gestor_a, digitado
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_lancar(empresa_a), _lancamento_valido(valor=digitado, acao="confirmar")
    )

    assert resposta.status_code == 200
    assert "use vírgula para os centavos" in resposta.content.decode()
    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize(
    ("digitado", "gravado"),
    [("1.000,50", "1000.50"), ("10,5", "10.50"), ("10000", "10000.00")],
)
def test_r1_tela_converte_as_formas_corretas_e_confirma_o_valor_certo(
    client, empresa_a, usuario_gestor_a, digitado, gravado
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        _url_lancar(empresa_a), _lancamento_valido(valor=digitado, acao="confirmar")
    )

    assert resposta.status_code == 302
    receita = ReceitaInformada.objects.get()
    assert receita.valor == Decimal(gravado)
    assert receita.estado == EstadoReceitaInformada.CONFIRMADA


# ---------------------------------------------------------------------------
# Porta 3 — API (o DecimalField(decimal_places=2) do DRF recusa com 400)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("valor", ["10.000", "1.500", "10,000", "1.234.567"])
def test_r1_api_recusa_forma_ambigua_com_400_e_nao_grava(
    client, empresa_a, usuario_gestor_a, valor
):
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2026,
        "mes": 5,
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": valor,
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "NF 999 sintética",
    }

    resposta = client.post(
        f"{_base_api(empresa_a)}/receitas-informadas/",
        data=corpo,
        content_type="application/json",
    )

    assert resposta.status_code == 400, resposta.content
    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize("valor", ["10.50", "10000", "1000.50"])
def test_r1_api_aceita_decimal_com_no_maximo_duas_casas(client, empresa_a, usuario_gestor_a, valor):
    client.force_login(usuario_gestor_a)
    corpo = {
        "ano": 2026,
        "mes": 5,
        "mercado": "interno",
        "situacao_iss": "proprio_municipio",
        "valor": valor,
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": f"NF {valor} sintética",
    }

    resposta = client.post(
        f"{_base_api(empresa_a)}/receitas-informadas/",
        data=corpo,
        content_type="application/json",
    )

    assert resposta.status_code == 201, resposta.content
    assert ReceitaInformada.objects.count() == 1
