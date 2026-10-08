"""DL-075 — correção única da auditoria: portas de TELA e de API.

Complementa `test_dl075_correcao_auditoria.py` (serviço). Aqui se prova o que a tela e a API
fazem com as mesmas entradas: A3 (folha de outra empresa pela API, mata M45), A4 (milhar mal
formado na tela da folha e da receita), A8 e A11 (API recusa float, notação científica e
confirmação de receita interna sem situação), A9 (lista de folhas com teto constante de
consultas) e a memória na tela (dinheiro em pt-BR, percentual com a precisão de antes).

Dados 100% sintéticos (test_dl075_suporte e test_dl074_suporte).
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.fiscal import folha_fator_r as servico_folha
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import EnquadramentoAtividade, FolhaFatorR, ReceitaInformada
from apps.fiscal.tests.test_dl075_suporte import (
    SUPORTE_SINTETICO,
    atividade_padrao,
    cenario_simples,
    folha_confirmada,
    folhas_dos_12_meses,
    janela_de_receitas,
    receber_e_confirmar_mes,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

ORIGEM_OUTRAS = "outras_receitas_atividade"


def _base(empresa):
    return f"/fiscal/api/empresas/{empresa.pk}"


def _post(client, url, corpo=None):
    if corpo is None:
        return client.post(url)
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


def _folha_payload(**mudancas):
    corpo = {
        "ano": 2026,
        "mes": 5,
        "remuneracao_empregados_avulsos": "1000.00",
        "pro_labore_autonomos": "0.00",
        "decimo_terceiro": "0.00",
        "cpp_recolhida": "0.00",
        "fgts_recolhido": "0.00",
        "documento_suporte": SUPORTE_SINTETICO,
    }
    corpo.update(mudancas)
    return corpo


def _receita_payload(**mudancas):
    corpo = {
        "ano": 2026,
        "mes": 6,
        "mercado": "interno",
        "valor": "1234.56",
        "origem": ORIGEM_OUTRAS,
        "motivo": "Lançamento sintético de teste.",
        "documento_suporte": "Extrato sintético de teste.",
        "situacao_iss": "proprio_municipio",
    }
    corpo.update(mudancas)
    return corpo


@pytest.fixture
def empresa(empresa_a, usuario_gestor_a):
    return cenario_simples(empresa_a)


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    usuario = get_user_model().objects.create_user(
        username="gestor-b-dl075-correcao",
        email="gestor-b-dl075-correcao@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    return usuario


# ---------------------------------------------------------------------------
# A3 — folha de OUTRA empresa do mesmo escritório, pelo caminho da empresa: 404 (mata M45)
# ---------------------------------------------------------------------------


def test_confirmar_folha_de_outra_empresa_responde_404_e_nao_muda_nada(
    client, empresa, empresa_a2, usuario_gestor_a
):
    folha = servico_folha.lancar_folha(
        empresa_a2,
        2026,
        5,
        {
            "remuneracao_empregados_avulsos": Decimal("1000"),
            "pro_labore_autonomos": Decimal("0"),
            "decimo_terceiro": Decimal("0"),
            "cpp_recolhida": Decimal("0"),
            "fgts_recolhido": Decimal("0"),
        },
        SUPORTE_SINTETICO,
        usuario_gestor_a,
    )
    client.force_login(usuario_gestor_a)

    resposta = _post(client, f"{_base(empresa)}/folhas-fator-r/{folha.pk}/confirmar/")

    assert resposta.status_code == 404
    folha.refresh_from_db()
    assert folha.estado == "rascunho"
    assert folha.confirmada_em is None


def test_estornar_folha_confirmada_de_outra_empresa_responde_404(
    client, empresa, empresa_a2, usuario_gestor_a
):
    folha = folha_confirmada(empresa_a2, usuario_gestor_a, 2026, 5, remuneracao="1000.00")
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/folhas-fator-r/{folha.pk}/estornar/", {"motivo": "X"}
    )

    assert resposta.status_code == 404
    folha.refresh_from_db()
    assert folha.estado == "confirmada"


# ---------------------------------------------------------------------------
# A11 — API: float e notação científica recusados; valor em texto ou inteiro aceito
# ---------------------------------------------------------------------------


def test_api_recusa_valor_de_receita_em_ponto_flutuante(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/receitas-informadas/", _receita_payload(valor=1234.56)
    )

    assert resposta.status_code == 400
    assert "ponto flutuante" in str(resposta.json())
    assert ReceitaInformada.objects.count() == 0


@pytest.mark.parametrize("valor", ["1E+3", "1e3"])
def test_api_recusa_notacao_cientifica_no_valor_da_receita(
    client, empresa, usuario_gestor_a, valor
):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client, f"{_base(empresa)}/receitas-informadas/", _receita_payload(valor=valor)
    )

    assert resposta.status_code == 400
    assert "Notação científica" in str(resposta.json())
    assert ReceitaInformada.objects.count() == 0


def test_api_aceita_valor_de_receita_em_texto_e_inteiro(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    texto = _post(
        client, f"{_base(empresa)}/receitas-informadas/", _receita_payload(valor="1234.56")
    )
    inteiro = _post(
        client,
        f"{_base(empresa)}/receitas-informadas/",
        _receita_payload(valor=1000, motivo="Outro lançamento sintético."),
    )

    assert texto.status_code == 201
    assert inteiro.status_code == 201


def test_api_recusa_float_em_componente_da_folha(client, empresa, usuario_gestor_a):
    client.force_login(usuario_gestor_a)

    resposta = _post(
        client,
        f"{_base(empresa)}/folhas-fator-r/nova/",
        _folha_payload(remuneracao_empregados_avulsos=1000.5),
    )

    assert resposta.status_code == 400
    assert "ponto flutuante" in str(resposta.json())
    assert FolhaFatorR.objects.filter(empresa=empresa).count() == 0


# ---------------------------------------------------------------------------
# A8 — API: confirmar receita interna sem situação do ISS responde 400 (nomeada)
# ---------------------------------------------------------------------------


def test_api_confirmar_receita_interna_sem_situacao_responde_400(client, empresa, usuario_gestor_a):
    receita = servico_receita.lancar_receita_informada(
        empresa,
        2026,
        6,
        "interno",
        "1000.00",
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        "Suporte sintético.",
        usuario_gestor_a,
        situacao_iss="proprio_municipio",
    )
    ReceitaInformada.objects.filter(pk=receita.pk).update(situacao_iss=None)
    client.force_login(usuario_gestor_a)

    resposta = _post(client, f"{_base(empresa)}/receitas-informadas/{receita.pk}/confirmar/")

    assert resposta.status_code == 400
    assert "situação do ISS" in str(resposta.json())
    receita.refresh_from_db()
    assert receita.estado == "rascunho"


# ---------------------------------------------------------------------------
# A4 — tela da folha e tela da receita: milhar mal formado
# ---------------------------------------------------------------------------


def _folha_valida(**sobrescritas):
    dados = {
        "ano": "2026",
        "mes": "05",
        "remuneracao_empregados_avulsos": "1.000,00",
        "pro_labore_autonomos": "0,00",
        "decimo_terceiro": "0,00",
        "cpp_recolhida": "0,00",
        "fgts_recolhido": "0,00",
        "documento_suporte": SUPORTE_SINTETICO,
    }
    dados.update(sobrescritas)
    return dados


# (valor digitado, o que a tela faz): None = grava; "ambiguo" e "malformado" = recusa com 200.
CASOS_DE_MILHAR = [
    ("10.000", "ambiguo"),
    ("1.234", "ambiguo"),
    ("1.23,4", "malformado"),
    ("1.234,56", Decimal("1234.56")),
    ("10000", Decimal("10000")),
    ("10,5", Decimal("10.5")),
]

MENSAGEM_DO_CASO = {
    "ambiguo": "Valor ambíguo",
    "malformado": "O ponto só separa grupos de três dígitos",
}


@pytest.mark.parametrize(("bruto", "esperado"), CASOS_DE_MILHAR)
def test_tela_da_folha_trata_milhar_sem_500_e_sem_gravar_valor_errado(
    client, empresa, usuario_gestor_a, bruto, esperado
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        reverse("fiscal_web:folha_nova", args=[empresa.pk]),
        _folha_valida(remuneracao_empregados_avulsos=bruto),
    )

    if isinstance(esperado, str):
        assert resposta.status_code == 200
        assert MENSAGEM_DO_CASO[esperado] in resposta.content.decode()
        assert FolhaFatorR.objects.count() == 0
    else:
        assert resposta.status_code == 302
        folha = FolhaFatorR.objects.get(empresa=empresa)
        assert folha.remuneracao_empregados_avulsos == esperado


@pytest.mark.parametrize(("bruto", "esperado"), CASOS_DE_MILHAR)
def test_tela_da_receita_informada_trata_milhar_do_mesmo_jeito(
    client, empresa, usuario_gestor_a, bruto, esperado
):
    client.force_login(usuario_gestor_a)

    resposta = client.post(
        reverse("fiscal_web:receita_informada_nova", args=[empresa.pk]),
        {
            "ano": "2026",
            "mes": "06",
            "mercado": "interno",
            "valor": bruto,
            "origem": ORIGEM_OUTRAS,
            "situacao_iss": "proprio_municipio",
            "motivo": "Lançamento sintético de teste.",
            "documento_suporte": "Extrato sintético de teste.",
            "acao": "rascunho",
        },
    )

    if isinstance(esperado, str):
        assert resposta.status_code == 200
        assert MENSAGEM_DO_CASO[esperado] in resposta.content.decode()
        assert ReceitaInformada.objects.count() == 0
    else:
        assert resposta.status_code == 302
        receita = ReceitaInformada.objects.get(empresa=empresa)
        assert receita.valor == esperado


# ---------------------------------------------------------------------------
# A9 — lista de folhas: FS12 dos 12 meses com teto constante de consultas
# ---------------------------------------------------------------------------


def test_lista_de_folhas_com_fs12_dos_12_meses_cabe_em_teto_de_consultas(
    client, empresa, usuario_gestor_a, django_assert_max_num_queries
):
    folhas_dos_12_meses(empresa, usuario_gestor_a, 2026, 6, [Decimal("1000")] * 12)
    client.force_login(usuario_gestor_a)

    with django_assert_max_num_queries(20):
        resposta = client.get(
            reverse("fiscal_web:folhas_fator_r"), {"empresa": empresa.pk, "ano": 2026}
        )

    assert resposta.status_code == 200
    assert len(resposta.context["meses_fs12"]) == 12


# ---------------------------------------------------------------------------
# Memória na tela: dinheiro em pt-BR com 2 casas; percentual com a precisão de antes
# ---------------------------------------------------------------------------


def test_tela_do_pre_das_mostra_dinheiro_pt_br_e_percentual_sem_perder_precisao(
    client, empresa, usuario_gestor_a
):
    atividade_padrao(empresa, usuario_gestor_a, EnquadramentoAtividade.ANEXO_III)
    janela_de_receitas(empresa, usuario_gestor_a, 2026, 6, [25000] * 12)
    receber_e_confirmar_mes(empresa, usuario_gestor_a, 2026, 6, "100000.00")
    client.force_login(usuario_gestor_a)

    resposta = client.get(
        reverse("fiscal_web:pre_das"), {"empresa": empresa.pk, "ano": 2026, "mes": 6}
    )

    html = resposta.content.decode()
    assert resposta.status_code == 200
    assert "300.000,00" in html  # RBT12 em pt-BR
    assert "0,080800000000" in html  # alíquota efetiva com a precisão que o cálculo usa
    assert "300000,000000000000" not in html  # o formato antigo, com 12 casas, não volta
