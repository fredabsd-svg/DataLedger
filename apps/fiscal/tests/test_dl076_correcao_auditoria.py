"""Correção única da auditoria da DL-076 (rodada 1, 08/10/2026): achados A1 a A11 e os testes
T1 a T13 que o auditor propôs para matar os mutantes vivos.

Cada teste diz o que prova. O resultado esperado é escrito à mão, a partir da regra e dos
números do cenário; nada é copiado da saída do código. Dados 100% sintéticos (CNPJs e valores
inventados), nenhum dado real de cliente.

Os mutantes citados em cada bloco (M24, M51, ...) são os da seção 6 do relatório de auditoria.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as esc
from apps.fiscal import iss_municipal as iss
from apps.fiscal import services, views_web
from apps.fiscal.iss_nota import CamposIss, divergencia_de_base
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    EscrituracaoFiscal,
    RegimeIss,
    RegimeIssEmpresa,
)
from apps.fiscal.tests.suporte_iss_dl076 import (
    DEVIDO,
    OUTRO,
    OUTRO_MUNICIPIO,
    PALMAS,
    RETIDO,
    aliquota,
    receber,
    regime_aliquota,
)
from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, xml_evento
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

HOJE = date(2026, 10, 20)
ANO, MES = 2026, 10
CAMPO_VISSQN = "NFSe/infNFSe/valores/vISSQN"


def _url_da_empresa(nome, empresa):
    return reverse(nome) + f"?empresa={empresa.pk}&ano={ANO}&mes={MES}"


def _cancelar(escritorio, usuario, documento):
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo="c.xml",
    )


def _dados_da_aliquota(**sobrescritas):
    """POST válido do cadastro de alíquota (formulário da tela). Sobrescreva o que muda."""
    dados = {
        "municipio_ibge": PALMAS,
        "subitem": "17.01",
        "percentual": "5,00",
        "fonte": "Fonte sintética de teste (DL-076, correção da auditoria)",
        "inicio": "01/01/2026",
        "fim": "",
    }
    dados.update(sobrescritas)
    return dados


# ---------------------------------------------------------------------------
# A1 (média): percentual com vírgulas demais não pode dar 500. Cadastro e edição.
# ---------------------------------------------------------------------------

VALORES_DE_PERCENTUAL_INVALIDO = ["5,00,0", "1.23,4", "2,,5", "1,2,3", "5.00,00"]


@pytest.mark.parametrize("bruto", VALORES_DE_PERCENTUAL_INVALIDO)
def test_A1_percentual_invalido_no_cadastro_responde_200_e_nao_grava(
    client, escritorio_a, usuario_gestor_a, bruto
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        reverse("fiscal_web:iss_aliquota_nova"), _dados_da_aliquota(percentual=bruto)
    )
    assert resposta.status_code == 200
    assert "Alíquota inválida" in resposta.content.decode()
    assert not AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).exists()


@pytest.mark.parametrize("bruto", VALORES_DE_PERCENTUAL_INVALIDO)
def test_A1_percentual_invalido_na_edicao_responde_200_e_mantem_o_gravado(
    client, escritorio_a, usuario_gestor_a, bruto
):
    alvo = aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        reverse("fiscal_web:iss_aliquota_editar", args=[alvo.pk]),
        _dados_da_aliquota(percentual=bruto),
    )
    assert resposta.status_code == 200
    assert "Alíquota inválida" in resposta.content.decode()
    alvo.refresh_from_db()
    assert alvo.percentual == Decimal("5.0000")


# A8 (baixa): o erro do percentual fala do percentual, não de reais.
def test_A8_percentual_ambiguo_tem_mensagem_propria_sem_reais():
    with pytest.raises(iss.EntradaInvalidaIss) as excinfo:
        views_web._percentual_do_formulario("1.000")
    mensagem = excinfo.value.mensagem
    assert mensagem.startswith("Valor ambíguo na alíquota")
    assert "reais" not in mensagem


# ---------------------------------------------------------------------------
# A2 (média, HI-89): nota prestada recebida e não escriturada gera aviso forte na apuração.
# Três portas: serviço, API e tela.
# ---------------------------------------------------------------------------


def _cenario_com_nota_nao_escriturada(escritorio, usuario, empresa):
    """Uma nota efetivada (50,00) e uma recebida na competência e NÃO escriturada (nº 77)."""
    aliquota(escritorio, usuario, "17.01", "5.0000")
    regime_aliquota(empresa, usuario)
    receber(escritorio, usuario, 1, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00")
    receber(escritorio, usuario, 77, None, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="100.00")


def _cenario_sem_pendencia(escritorio, usuario, empresa):
    aliquota(escritorio, usuario, "17.01", "5.0000")
    regime_aliquota(empresa, usuario)
    receber(escritorio, usuario, 1, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00")


def test_A2_servico_avisa_a_nota_recebida_e_nao_escriturada(
    escritorio_a, usuario_gestor_a, empresa_a
):
    _cenario_com_nota_nao_escriturada(escritorio_a, usuario_gestor_a, empresa_a)
    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    # O total soma só a nota efetivada; a não escriturada fica fora (DL-072).
    assert resultado.total == Decimal("50.00")
    avisos = [a for a in resultado.avisos if a.codigo == iss.CODIGO_NOTAS_NAO_ESCRITURADAS]
    assert len(avisos) == 1
    assert "1 nota(s) prestada(s)" in avisos[0].mensagem
    assert "77" in avisos[0].mensagem


def test_A2_sem_pendencia_nao_gera_aviso(escritorio_a, usuario_gestor_a, empresa_a):
    _cenario_sem_pendencia(escritorio_a, usuario_gestor_a, empresa_a)
    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert not [a for a in resultado.avisos if a.codigo == iss.CODIGO_NOTAS_NAO_ESCRITURADAS]


def test_A2_api_devolve_o_aviso_em_avisos(client, escritorio_a, usuario_gestor_a, empresa_a):
    _cenario_com_nota_nao_escriturada(escritorio_a, usuario_gestor_a, empresa_a)
    client.force_login(usuario_gestor_a)
    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/iss/apuracao/?ano={ANO}&mes={MES}")
    assert resposta.status_code == 200
    codigos = [a["codigo"] for a in resposta.json()["avisos"]]
    assert iss.CODIGO_NOTAS_NAO_ESCRITURADAS in codigos


def test_A2_tela_destaca_o_aviso_e_leva_a_escriturar(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    _cenario_com_nota_nao_escriturada(escritorio_a, usuario_gestor_a, empresa_a)
    client.force_login(usuario_gestor_a)
    html = client.get(_url_da_empresa("fiscal_web:iss_apuracao", empresa_a)).content.decode()
    assert "Notas do mês ainda não escrituradas" in html
    assert "Escriturar as notas da competência" in html
    assert reverse("fiscal_web:notas_a_escriturar") + "?" in html
    # O aviso aparece uma vez: destaque e lista comum não repetem a mesma mensagem.
    assert html.count("1 nota(s) prestada(s)") == 1


def test_A2_tela_sem_pendencia_nao_destaca(client, escritorio_a, usuario_gestor_a, empresa_a):
    _cenario_sem_pendencia(escritorio_a, usuario_gestor_a, empresa_a)
    client.force_login(usuario_gestor_a)
    html = client.get(_url_da_empresa("fiscal_web:iss_apuracao", empresa_a)).content.decode()
    assert "Notas do mês ainda não escrituradas" not in html


# ---------------------------------------------------------------------------
# A3 (média): natureza "outro município" com cLocIncid igual ao do estabelecimento.
# ---------------------------------------------------------------------------


def test_A3_natureza_outro_com_local_do_proprio_municipio_avisa_na_apuracao_e_no_relatorio(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    receber(escritorio_a, usuario_gestor_a, 22, OUTRO, c_loc_incid=PALMAS, v_iss_qn="20.00")

    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    # A nota de outro município não soma no ISS próprio; o aviso só diz da contradição.
    assert resultado.total == Decimal("50.00")
    avisos = [a for a in resultado.avisos if a.codigo == "natureza_incompativel_com_incidencia"]
    assert len(avisos) == 1
    assert "22" in avisos[0].mensagem and PALMAS in avisos[0].mensagem

    relatorio = iss.relatorio_iss_outros_municipios(empresa_a, ANO, MES)
    assert [a.codigo for a in relatorio.avisos] == ["natureza_incompativel_com_incidencia"]
    assert relatorio.grupos[0].municipio_ibge == PALMAS
    assert relatorio.grupos[0].total == Decimal("20.00")


def test_A3_com_local_de_outro_municipio_nao_avisa(escritorio_a, usuario_gestor_a, empresa_a):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a, usuario_gestor_a, 22, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="20.00"
    )

    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert not [a for a in resultado.avisos if a.codigo == "natureza_incompativel_com_incidencia"]
    relatorio = iss.relatorio_iss_outros_municipios(empresa_a, ANO, MES)
    assert not [a for a in relatorio.avisos if a.codigo == "natureza_incompativel_com_incidencia"]


# ---------------------------------------------------------------------------
# A4 e A5: isolamento, permissão e lacunas de teste. T1 a T13 da proposta do auditor.
# ---------------------------------------------------------------------------


def test_T1_aliquota_de_outro_escritorio_nao_vale_na_apuracao(
    escritorio_a, escritorio_b, usuario_gestor_a, empresa_a
):
    # M24: a alíquota só existe no escritório B. A empresa é do A, então não há alíquota
    # cadastrada para o subitem e a apuração recusa com o subitem sem alíquota.
    aliquota(escritorio_b, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    with pytest.raises(iss.IssRecusado) as excinfo:
        iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert {b.codigo for b in excinfo.value.bloqueios} == {"subitem_sem_aliquota_vigente"}


def test_T2_escrituracao_estornada_nao_entra_na_apuracao(escritorio_a, usuario_gestor_a, empresa_a):
    # M42: a escrituração estornada não pode somar. Duas notas devidas de 50,00; estorna uma.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        2,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    primeira = EscrituracaoFiscal.objects.filter(estado="efetivada").order_by("id").first()
    esc.estornar_escrituracao(primeira, "teste de estorno (correção DL-076)", usuario_gestor_a)
    assert iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE).total == Decimal("50.00")


def test_T3_api_de_regime_nao_altera_regime_de_outra_empresa_pela_url_da_minha(
    client, escritorio_a, escritorio_b, usuario_gestor_a, empresa_a, empresa_b
):
    # M51: o PATCH usa a empresa da URL. Regime de B, pela URL de A, não pode ser alterado.
    gestor_b = get_user_model().objects.create_user(
        username="gestor-b-correcao", email="gestor-b@exemplo.invalid", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=gestor_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    regime_b = regime_aliquota(empresa_b, gestor_b)
    client.force_login(usuario_gestor_a)
    resposta = client.patch(
        f"/fiscal/api/empresas/{empresa_a.pk}/iss/regimes/{regime_b.pk}/",
        data=json.dumps({"regime": RegimeIss.FIXO_AUTONOMO}),
        content_type="application/json",
    )
    assert resposta.status_code == 404
    regime_b.refresh_from_db()
    assert regime_b.regime == RegimeIss.ALIQUOTA


def test_T4_lista_web_de_aliquotas_nao_mostra_aliquota_de_outro_escritorio(
    client, escritorio_a, escritorio_b, usuario_gestor_a
):
    # M55: a lista da tela filtra pelo escritório ativo; a alíquota 17.06 é só do B.
    aliquota(escritorio_b, usuario_gestor_a, "17.06", "4.0000")
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:iss_aliquotas"))
    assert resposta.status_code == 200
    assert "17.06" not in resposta.content.decode()


def test_T5_nota_cancelada_nao_entra_no_total_dos_relatorios(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # M63 e M64: a nota cancelada não soma em retido nem em outros municípios.
    regime_aliquota(empresa_a, usuario_gestor_a)
    d1 = receber(escritorio_a, usuario_gestor_a, 1, RETIDO, tp_ret_issqn="2", v_iss_qn="30.00")
    receber(escritorio_a, usuario_gestor_a, 2, RETIDO, tp_ret_issqn="2", v_iss_qn="10.00")
    d3 = receber(
        escritorio_a, usuario_gestor_a, 3, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="99.00"
    )
    receber(escritorio_a, usuario_gestor_a, 4, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="1.00")
    _cancelar(escritorio_a, usuario_gestor_a, d1)
    _cancelar(escritorio_a, usuario_gestor_a, d3)

    retido = iss.relatorio_iss_retido_sofrido(empresa_a, ANO, MES)
    assert {g.municipio_ibge: g.total for g in retido.grupos} == {PALMAS: Decimal("10.00")}
    outros = iss.relatorio_iss_outros_municipios(empresa_a, ANO, MES)
    assert {g.municipio_ibge: g.total for g in outros.grupos} == {OUTRO_MUNICIPIO: Decimal("1.00")}


def test_T6_limite_superior_do_aviso_de_aliquota_nas_outras_cidades(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # M40: 5,00 é o máximo legal e não avisa; 5,50 avisa. 2,00 não avisa; 1,99 avisa.
    regime_aliquota(empresa_a, usuario_gestor_a)
    for numero, percentual in enumerate(("5.00", "5.50", "2.00", "1.99"), start=1):
        receber(
            escritorio_a,
            usuario_gestor_a,
            numero,
            OUTRO,
            c_loc_incid=OUTRO_MUNICIPIO,
            c_trib_nac="070201",
            p_aliq_aplic=percentual,
            v_iss_qn="1.00",
        )
    relatorio = iss.relatorio_iss_outros_municipios(empresa_a, ANO, MES)
    avisados = sorted(
        a.mensagem.split("Nota ")[1].split(":")[0]
        for a in relatorio.avisos
        if a.codigo == "aliquota_fora_de_2_a_5"
    )
    assert avisados == ["2", "4"]


def test_T7_cadastro_de_regime_grava_a_trilha(empresa_a, usuario_gestor_a):
    # M62: o cadastro do regime deixa uma linha de auditoria com a ação exata.
    iss.cadastrar_regime(
        empresa_a,
        {"exercicio": ANO, "regime": RegimeIss.ALIQUOTA, "municipio_ibge": PALMAS},
        usuario=usuario_gestor_a,
    )
    assert RegistroAuditoria.objects.filter(acao="regime_iss.criado").count() == 1


def test_T8_apuracao_usa_o_regime_do_exercicio_da_competencia(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # M74: 2026 é alíquota; 2027 é fixo. A apuração de 10/2026 não pode ler o regime de 2027.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000", inicio=date(2026, 1, 1))
    regime_aliquota(empresa_a, usuario_gestor_a, exercicio=2026)
    RegimeIssEmpresa.objects.create(
        empresa=empresa_a,
        exercicio=2027,
        regime=RegimeIss.FIXO_AUTONOMO,
        municipio_ibge=PALMAS,
        criado_por=usuario_gestor_a,
    )
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    assert iss.apuracao_iss_proprio(empresa_a, 2026, 10, hoje=HOJE).total == Decimal("50.00")
    with pytest.raises(iss.IssRecusado) as excinfo:
        iss.apuracao_iss_proprio(empresa_a, 2027, 1, hoje=HOJE)
    assert {b.codigo for b in excinfo.value.bloqueios} == {"regime_fixo"}


def test_T9_cadastro_retroativo_de_vigencia_anterior_nao_conflita(escritorio_a, usuario_gestor_a):
    # M77: uma vigência que termina antes da existente é aceita; sobrepor um dia é recusado.
    base = {"municipio_ibge": PALMAS, "subitem": "17.01", "fonte": "fonte sintética"}
    iss.cadastrar_aliquota(
        escritorio_a,
        {
            **base,
            "percentual": Decimal("5"),
            "inicio_vigencia": date(2026, 1, 1),
            "fim_vigencia": None,
        },
        usuario=usuario_gestor_a,
    )
    iss.cadastrar_aliquota(
        escritorio_a,
        {
            **base,
            "percentual": Decimal("4"),
            "inicio_vigencia": date(2025, 1, 1),
            "fim_vigencia": date(2025, 12, 31),
        },
        usuario=usuario_gestor_a,
    )
    with pytest.raises(iss.IssConflito):
        iss.cadastrar_aliquota(
            escritorio_a,
            {
                **base,
                "percentual": Decimal("4"),
                "inicio_vigencia": date(2024, 1, 1),
                "fim_vigencia": date(2026, 1, 1),
            },
            usuario=usuario_gestor_a,
        )


@pytest.mark.parametrize("campo_omitido", ["cLocIncid", "cTribNac"])
def test_T10_campo_ausente_que_a_apuracao_exige_bloqueia_com_o_nome_do_campo(
    escritorio_a, usuario_gestor_a, empresa_a, campo_omitido
):
    # M80 e M82: sem cLocIncid ou cTribNac a nota não pode seguir para o cálculo.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
        omitir=frozenset({campo_omitido}),
    )
    with pytest.raises(iss.IssRecusado) as excinfo:
        iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert [b.codigo for b in excinfo.value.bloqueios] == ["nota_sem_campo_de_iss"]
    assert campo_omitido in excinfo.value.bloqueios[0].mensagem


@pytest.mark.parametrize("caminho", ["retido-sofrido", "outros-municipios"])
def test_T11_cliente_nao_le_relatorios_nem_regimes_pela_api(
    client, usuario_cliente_a, empresa_a, caminho
):
    # M87 e M88: o CLIENTE não lê o retido, os outros municípios, os regimes nem as regras.
    client.force_login(usuario_cliente_a)
    base = f"/fiscal/api/empresas/{empresa_a.pk}/iss/"
    assert client.get(f"{base}{caminho}/?ano={ANO}&mes={MES}").status_code == 403
    assert client.get(f"{base}regimes/").status_code == 403
    assert client.get("/fiscal/api/iss/regras-municipio/").status_code == 403


@pytest.mark.parametrize(
    "subitem,inciso",
    [
        ("03.04", "§ 1º"),
        ("03.05", "II"),
        ("07.02", "III"),
        ("07.04", "IV"),
        ("07.05", "V"),
        ("07.09", "VI"),
        ("07.10", "VII"),
        ("07.11", "VIII"),
        ("07.12", "IX"),
        ("07.16", "XII"),
        ("07.17", "XIII"),
        ("07.18", "XIV"),
        ("07.19", "III"),
        ("11.01", "XV"),
        ("11.02", "XVI"),
        ("11.04", "XVII"),
        ("12.01", "XVIII"),
        ("12.12", "XVIII"),
        ("14.14", "III"),
        ("16.01", "XIX"),
        ("16.02", "XIX"),
        ("17.05", "XX"),
        ("17.10", "XXI"),
        ("20.01", "XXII"),
        ("20.03", "XXII"),
        ("22.01", "§ 2º"),
        ("04.22", "XXIII"),
        ("04.23", "XXIII"),
        ("05.09", "XXIII"),
        ("15.01", "XXIV"),
        ("15.09", "XXV"),
    ],
)
def test_T12_tabela_completa_das_excecoes_do_art_3(subitem, inciso):
    # M66 a M69: cada linha da tabela do art. 3º da LC 116, conferida contra o texto do Planalto.
    assert iss.excecao_do_art_3(subitem) == inciso


@pytest.mark.parametrize(
    "subitem",
    [
        "10.04",
        "12.13",
        "07.01",
        "07.03",
        "07.06",
        "07.07",
        "07.08",
        "07.13",
        "07.14",
        "07.15",
        "11.03",
        "17.01",
        "17.06",
    ],
)
def test_T12b_subitens_fora_das_excecoes_do_art_3(subitem):
    assert iss.excecao_do_art_3(subitem) is None


@pytest.mark.parametrize("tp_ret", ["2", "3"])
def test_T13_retencao_2_ou_3_no_xml_de_nota_devida_bloqueia(
    escritorio_a, usuario_gestor_a, empresa_a, tp_ret
):
    # M29: qualquer retenção (2 ou 3) contradiz a natureza "devido pelo prestador".
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
        tp_ret_issqn=tp_ret,
    )
    with pytest.raises(iss.IssRecusado) as excinfo:
        iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert {b.codigo for b in excinfo.value.bloqueios} == {"nota_retida_com_natureza_devida"}


# ---------------------------------------------------------------------------
# A6 (baixa): consultas da apuração não crescem com o número de notas.
# ---------------------------------------------------------------------------


def test_A6_consultas_da_apuracao_sao_constantes_com_o_numero_de_notas(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    for numero in range(1, 11):
        receber(
            escritorio_a,
            usuario_gestor_a,
            numero,
            DEVIDO,
            c_trib_nac="170101",
            v_bc="1000.00",
            v_iss_qn="50.00",
        )
    with CaptureQueriesContext(connection) as com_dez:
        iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    for numero in range(11, 41):
        receber(
            escritorio_a,
            usuario_gestor_a,
            numero,
            DEVIDO,
            c_trib_nac="170101",
            v_bc="1000.00",
            v_iss_qn="50.00",
        )
    with CaptureQueriesContext(connection) as com_quarenta:
        resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert len(resultado.notas) == 40
    assert len(com_quarenta) == len(com_dez)
    assert len(com_quarenta) <= 20


def test_A6_tela_da_apuracao_nao_cresce_com_o_numero_de_notas(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    for numero in range(1, 11):
        receber(
            escritorio_a,
            usuario_gestor_a,
            numero,
            DEVIDO,
            c_trib_nac="170101",
            v_bc="1000.00",
            v_iss_qn="50.00",
        )
    client.force_login(usuario_gestor_a)
    url = _url_da_empresa("fiscal_web:iss_apuracao", empresa_a)
    # Primeira requisição paga o aquecimento único do processo (cache de tipos, por exemplo);
    # a comparação é entre duas requisições já aquecidas.
    assert client.get(url).status_code == 200
    with CaptureQueriesContext(connection) as com_dez:
        assert client.get(url).status_code == 200
    for numero in range(11, 41):
        receber(
            escritorio_a,
            usuario_gestor_a,
            numero,
            DEVIDO,
            c_trib_nac="170101",
            v_bc="1000.00",
            v_iss_qn="50.00",
        )
    with CaptureQueriesContext(connection) as com_quarenta:
        assert client.get(url).status_code == 200
    assert len(com_quarenta) == len(com_dez)


# ---------------------------------------------------------------------------
# A7 (baixa, HI-90 item 4): vencimento nominal com o dia da semana quando cai em fim de semana.
# ---------------------------------------------------------------------------


def test_A7_vencimento_de_fim_de_semana_sai_com_o_dia_sem_afirmar_outra_data(
    client, escritorio_a, usuario_gestor_a, empresa_a
):
    # 10/2026: retido 15/11/2026 é DOMINGO; próprio 10/11/2026 é terça (sem sufixo).
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_bc="1000.00",
        v_iss_qn="50.00",
    )
    client.force_login(usuario_gestor_a)
    html = client.get(_url_da_empresa("fiscal_web:iss_apuracao", empresa_a)).content.decode()
    assert "Vencimento nominal do ISS retido" in html
    assert "15/11/2026 (domingo)" in html
    assert "10/11/2026</dd>" in html
    assert "10/11/2026 (" not in html
    # A memória de cálculo mostra a mesma data nominal, com o mesmo dia da semana.
    assert "retido dia 15: 15/11/2026 (domingo)" in html


@pytest.mark.parametrize(
    "dia,esperado",
    [
        (date(2026, 11, 15), "15/11/2026 (domingo)"),
        (date(2027, 1, 9), "09/01/2027 (sábado)"),
        (date(2027, 1, 15), "15/01/2027"),
        (None, ""),
    ],
)
def test_A7_texto_do_vencimento_por_dia_da_semana(dia, esperado):
    assert views_web._vencimento_na_tela(dia) == esperado


# ---------------------------------------------------------------------------
# A8 (baixa): exemplo de subitem é 07.02 (não 7.02), na ajuda e na mensagem.
# ---------------------------------------------------------------------------


def test_A8_ajuda_do_formulario_mostra_o_subitem_com_zero(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    html = client.get(reverse("fiscal_web:iss_aliquota_nova")).content.decode()
    assert "17.01 ou 07.02" in html
    assert "17.01 ou 7.02" not in html


def test_A8_mensagem_do_subitem_mostra_o_exemplo_com_zero(escritorio_a, usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss) as excinfo:
        iss.cadastrar_aliquota(
            escritorio_a,
            {
                "municipio_ibge": PALMAS,
                "subitem": "7.02",
                "percentual": Decimal("3"),
                "fonte": "fonte sintética",
                "inicio_vigencia": date(2026, 1, 1),
                "fim_vigencia": None,
            },
            usuario=usuario_gestor_a,
        )
    assert "ex.: 17.01, 07.02" in excinfo.value.mensagem


# ---------------------------------------------------------------------------
# A9 (baixa): piso de 2% no banco (salvo a exceção) e vigência com limites sensatos.
# ---------------------------------------------------------------------------


def _aliquota_direta_no_orm(escritorio, usuario, subitem, percentual):
    return AliquotaIssMunicipal.objects.create(
        escritorio=escritorio,
        municipio_ibge=PALMAS,
        subitem=subitem,
        percentual=Decimal(percentual),
        fonte="fonte sintética",
        inicio_vigencia=date(2026, 1, 1),
        fim_vigencia=None,
        criada_por=usuario,
    )


def test_A9_banco_recusa_alíquota_abaixo_de_2_fora_da_excecao(escritorio_a, usuario_gestor_a):
    with pytest.raises(IntegrityError) as excinfo:
        with transaction.atomic():
            _aliquota_direta_no_orm(escritorio_a, usuario_gestor_a, "17.01", "1.5000")
    assert "aliquota_iss_piso_2_salvo_excecao" in str(excinfo.value)


@pytest.mark.parametrize("subitem", ["07.02", "07.05", "16.01"])
def test_A9_banco_aceita_a_excecao_do_paragrafo_1_do_art_8a(
    escritorio_a, usuario_gestor_a, subitem
):
    _aliquota_direta_no_orm(escritorio_a, usuario_gestor_a, subitem, "1.5000")
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a, subitem=subitem).exists()


def test_A9_banco_aceita_o_piso_exato_de_2(escritorio_a, usuario_gestor_a):
    _aliquota_direta_no_orm(escritorio_a, usuario_gestor_a, "17.01", "2.0000")
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a, subitem="17.01").exists()


@pytest.mark.parametrize(
    "inicio,fim",
    [
        (date(1, 1, 1), None),
        (date(9999, 12, 31), None),
        (date(1999, 12, 31), None),
        (date(2026, 1, 1), date(9999, 12, 31)),
        (date(2101, 1, 1), None),
    ],
)
def test_A9_servico_recusa_vigencia_fora_de_2000_a_2100(
    escritorio_a, usuario_gestor_a, inicio, fim
):
    with pytest.raises(iss.EntradaInvalidaIss) as excinfo:
        iss.cadastrar_aliquota(
            escritorio_a,
            {
                "municipio_ibge": PALMAS,
                "subitem": "17.01",
                "percentual": Decimal("5"),
                "fonte": "fonte sintética",
                "inicio_vigencia": inicio,
                "fim_vigencia": fim,
            },
            usuario=usuario_gestor_a,
        )
    assert "entre 2000 e 2100" in excinfo.value.mensagem
    assert not AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).exists()


def test_A9_servico_aceita_os_limites_2000_e_2100(escritorio_a, usuario_gestor_a):
    for subitem, inicio in (("17.01", date(2000, 1, 1)), ("17.02", date(2100, 12, 31))):
        iss.cadastrar_aliquota(
            escritorio_a,
            {
                "municipio_ibge": PALMAS,
                "subitem": subitem,
                "percentual": Decimal("5"),
                "fonte": "fonte sintética",
                "inicio_vigencia": inicio,
                "fim_vigencia": None,
            },
            usuario=usuario_gestor_a,
        )
    assert AliquotaIssMunicipal.objects.filter(escritorio=escritorio_a).count() == 2


# ---------------------------------------------------------------------------
# A10 (baixa): a fórmula do vBC do XSD v1.01 (tiposComplexos_v1.01.xsd:250) tem vCalcReeRepRes
# e o benefício municipal (vRedBCBM ou vCalcBM). Antes o aviso ignorava os dois.
# ---------------------------------------------------------------------------


def _campos(**valores):
    base = {"versao": "1.01", "v_serv": Decimal("1000.00"), "v_desc_incond": Decimal("0.00")}
    base.update(valores)
    return CamposIss(**base)


def test_A10_beneficio_municipal_coerente_com_vCalcBM_nao_avisa():
    # 1000 - 0 - 100 (vDR) - 200 (vCalcBM) = 700 = vBC.
    campos = _campos(v_dr=Decimal("100.00"), v_calc_bm=Decimal("200.00"), v_bc=Decimal("700.00"))
    assert divergencia_de_base(campos) is None


def test_A10_beneficio_municipal_coerente_com_vRedBCBM_nao_avisa():
    campos = _campos(v_dr=Decimal("100.00"), v_red_bc_bm=Decimal("200.00"), v_bc=Decimal("700.00"))
    assert divergencia_de_base(campos) is None


def test_A10_reembolso_coerente_com_vCalcReeRepRes_nao_avisa():
    # 1000 - 0 - 100 (vDR) - 50 (reembolso) = 850; sem benefício.
    campos = _campos(
        v_dr=Decimal("100.00"), v_calc_ree_rep_res=Decimal("50.00"), v_bc=Decimal("850.00")
    )
    assert divergencia_de_base(campos) is None


def test_A10_base_incoerente_com_o_beneficio_avisa_com_o_valor_da_formula():
    campos = _campos(v_dr=Decimal("100.00"), v_calc_bm=Decimal("200.00"), v_bc=Decimal("900.00"))
    aviso = divergencia_de_base(campos)
    assert aviso is not None and "(700.00)" in aviso


def test_A10_nota_com_beneficio_municipal_coerente_nao_gera_aviso_de_base(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # Pela pipeline: vServ 1000, vDescIncond 0, vDR 100, vCalcBM 200, vBC 700 (coerente).
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    documento = receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_serv="1000.00",
        v_desc_incond="0.00",
        v_dr="100.00",
        v_calc_bm="200.00",
        v_bc="700.00",
        v_iss_qn="35.00",
    )
    assert documento is not None
    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert resultado.total == Decimal("35.00")
    assert resultado.notas[0].avisos == ()


def test_A10_nota_com_beneficio_em_vRedBCBM_coerente_nao_gera_aviso(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_serv="1000.00",
        v_desc_incond="0.00",
        v_dr="100.00",
        v_red_bc_bm="200.00",
        v_bc="700.00",
        v_iss_qn="35.00",
    )
    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert resultado.notas[0].avisos == ()


# ---------------------------------------------------------------------------
# A11 (baixa): campo opcional do XSD ausente é normal e não alerta; o obrigatório, sim.
# ---------------------------------------------------------------------------


def test_A11_opcionais_ausentes_nao_entram_no_alerta_do_relatorio(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # Sem vDescIncond, vDR e vCalcDR (todos minOccurs=0 no XSD): nada a alertar.
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 1, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="20.00")
    relatorio = iss.relatorio_iss_outros_municipios(empresa_a, ANO, MES)
    assert relatorio.notas[0].ausentes == ()


def test_A11_obrigatorio_ausente_alerta_no_relatorio(escritorio_a, usuario_gestor_a, empresa_a):
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        RETIDO,
        tp_ret_issqn="2",
        v_iss_qn=None,
    )
    relatorio = iss.relatorio_iss_retido_sofrido(empresa_a, ANO, MES)
    assert CAMPO_VISSQN in relatorio.notas[0].ausentes


def test_A11_tela_alerta_so_o_obrigatorio(client, escritorio_a, usuario_gestor_a, empresa_a):
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 1, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="20.00")
    client.force_login(usuario_gestor_a)
    url = _url_da_empresa("fiscal_web:iss_outros_municipios", empresa_a)
    assert "Campos ausentes ou ilegíveis" not in client.get(url).content.decode()
    receber(escritorio_a, usuario_gestor_a, 2, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn=None)
    html = client.get(url).content.decode()
    assert "Campos ausentes ou ilegíveis" in html and "vISSQN" in html


# Dúvida 4 (decisão do arquiteto, DL-076 A10): vDescIncond ausente, que é minOccurs=0, conta como
# zero no aviso de base. Coerente não avisa; incoerente avisa com o número recomposto.


def test_A10_sem_vDescIncond_mas_com_deducao_coerente_nao_avisa():
    # 1000 - 0 (vDescIncond ausente) - 100 (vDR) = 900 = vBC.
    campos = _campos(v_desc_incond=None, v_dr=Decimal("100.00"), v_bc=Decimal("900.00"))
    assert divergencia_de_base(campos) is None


def test_A10_sem_vDescIncond_e_base_incoerente_avisa_com_o_valor_recomposto():
    campos = _campos(v_desc_incond=None, v_dr=Decimal("100.00"), v_bc=Decimal("800.00"))
    aviso = divergencia_de_base(campos)
    assert aviso is not None and "(900.00)" in aviso and "contam como zero" in aviso


def test_A10_nota_sem_vDescIncond_coerente_nao_gera_aviso(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        1,
        DEVIDO,
        c_trib_nac="170101",
        v_serv="1000.00",
        v_dr="100.00",
        v_bc="900.00",
        v_iss_qn="45.00",
    )
    resultado = iss.apuracao_iss_proprio(empresa_a, ANO, MES, hoje=HOJE)
    assert resultado.notas[0].avisos == ()
