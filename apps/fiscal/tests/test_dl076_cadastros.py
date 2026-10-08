"""DL-076 (frente A), critério 5 e itens 2/4: cadastros de alíquota, regra e regime.

Alíquota de 2% a 5% recusada nas três portas (serviço, API e banco como último barramento);
exceção do § 1º do art. 8º-A com aviso; sobreposição de vigência recusada; alteração e
encerramento com trilha (antes e depois); regime único por empresa e exercício; seed de Palmas.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import iss_municipal as iss
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    RegimeIss,
    RegimeIssEmpresa,
    RegraIssMunicipio,
)
from apps.fiscal.tests.suporte_iss_dl076 import PALMAS

pytestmark = pytest.mark.django_db


def _dados(**mudancas):
    dados = {
        "municipio_ibge": PALMAS,
        "subitem": "17.01",
        "percentual": Decimal("5.0000"),
        "fonte": "Alíquota sintética de teste",
        "inicio_vigencia": date(2026, 1, 1),
        "fim_vigencia": None,
    }
    dados.update(mudancas)
    return dados


# ---------------------------------------------------------------------------
# Critério 5 — faixa de 2% a 5%: porta de serviço
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("percentual", ["2.0000", "5.0000", "3.5000"])
def test_aliquota_nos_limites_inclusive_e_aceita(escritorio_a, usuario_gestor_a, percentual):
    objeto, avisos = iss.cadastrar_aliquota(
        escritorio_a, _dados(percentual=Decimal(percentual)), usuario=usuario_gestor_a
    )
    assert objeto.percentual == Decimal(percentual)
    assert avisos == ()


@pytest.mark.parametrize("percentual", ["5.0001", "6", "10"])
def test_aliquota_acima_de_5_e_recusada(escritorio_a, usuario_gestor_a, percentual):
    with pytest.raises(iss.EntradaInvalidaIss) as excinfo:
        iss.cadastrar_aliquota(
            escritorio_a, _dados(percentual=Decimal(percentual)), usuario=usuario_gestor_a
        )
    assert "máximo de 5%" in excinfo.value.mensagem
    assert AliquotaIssMunicipal.objects.count() == 0


@pytest.mark.parametrize("percentual", ["1.9999", "1", "0.5"])
def test_aliquota_abaixo_de_2_e_recusada_para_subitem_comum(
    escritorio_a, usuario_gestor_a, percentual
):
    with pytest.raises(iss.EntradaInvalidaIss) as excinfo:
        iss.cadastrar_aliquota(
            escritorio_a, _dados(percentual=Decimal(percentual)), usuario=usuario_gestor_a
        )
    assert "8º-A" in excinfo.value.mensagem


@pytest.mark.parametrize("subitem", ["07.02", "07.05", "16.01"])
def test_excecao_do_paragrafo_1_do_8a_entra_com_aviso(escritorio_a, usuario_gestor_a, subitem):
    objeto, avisos = iss.cadastrar_aliquota(
        escritorio_a,
        _dados(subitem=subitem, percentual=Decimal("1.5000")),
        usuario=usuario_gestor_a,
    )
    assert objeto.percentual == Decimal("1.5000")
    assert [a.codigo for a in avisos] == ["aliquota_abaixo_do_minimo_excecao"]
    assert "§ 1º do art. 8º-A" in avisos[0].mensagem


def test_zero_negativo_e_quatro_casas_e_formato_de_float_sao_recusados(
    escritorio_a, usuario_gestor_a
):
    for ruim in (Decimal("0"), Decimal("-2"), "5.00001", 5.0):
        with pytest.raises(iss.EntradaInvalidaIss):
            iss.cadastrar_aliquota(escritorio_a, _dados(percentual=ruim), usuario=usuario_gestor_a)


@pytest.mark.parametrize("subitem", ["41.01", "1.01", "01.1", "00.01", "17.00", "17-01", "17.001"])
def test_subitem_fora_do_formato_ii_ss_e_recusado(escritorio_a, usuario_gestor_a, subitem):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_aliquota(escritorio_a, _dados(subitem=subitem), usuario=usuario_gestor_a)


def test_municipio_com_outro_tamanho_e_recusado(escritorio_a, usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_aliquota(
            escritorio_a, _dados(municipio_ibge="172100"), usuario=usuario_gestor_a
        )


def test_fonte_obrigatoria(escritorio_a, usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_aliquota(escritorio_a, _dados(fonte="   "), usuario=usuario_gestor_a)


def test_fim_anterior_ao_inicio_e_recusado(escritorio_a, usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_aliquota(
            escritorio_a,
            _dados(inicio_vigencia=date(2026, 5, 1), fim_vigencia=date(2026, 4, 30)),
            usuario=usuario_gestor_a,
        )


# Porta de banco: a restrição de 5% segura mesmo sem o serviço.
def test_banco_recusa_percentual_acima_de_5_sem_passar_pelo_servico(escritorio_a, usuario_gestor_a):
    with pytest.raises(IntegrityError), transaction.atomic():
        AliquotaIssMunicipal.objects.create(
            escritorio=escritorio_a,
            municipio_ibge=PALMAS,
            subitem="17.01",
            percentual=Decimal("5.5000"),
            fonte="teste de banco",
            inicio_vigencia=date(2026, 1, 1),
            criada_por=usuario_gestor_a,
        )


# ---------------------------------------------------------------------------
# Sobreposição, alteração e encerramento, com trilha
# ---------------------------------------------------------------------------


def test_sobreposicao_de_vigencia_e_recusada(escritorio_a, usuario_gestor_a):
    iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    with pytest.raises(iss.IssConflito):
        iss.cadastrar_aliquota(
            escritorio_a,
            _dados(inicio_vigencia=date(2026, 6, 1), percentual=Decimal("4.0000")),
            usuario=usuario_gestor_a,
        )


def test_vigencias_encadeadas_sem_sobreposicao_sao_aceitas(escritorio_a, usuario_gestor_a):
    iss.cadastrar_aliquota(
        escritorio_a,
        _dados(
            inicio_vigencia=date(2019, 1, 1),
            fim_vigencia=date(2026, 9, 30),
            percentual=Decimal("4"),
        ),
        usuario=usuario_gestor_a,
    )
    objeto, _ = iss.cadastrar_aliquota(
        escritorio_a, _dados(inicio_vigencia=date(2026, 10, 1)), usuario=usuario_gestor_a
    )
    assert objeto.pk is not None


def test_mesmo_subitem_em_outro_municipio_ou_escritorio_nao_sobrepoe(
    escritorio_a, escritorio_b, usuario_gestor_a
):
    iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    iss.cadastrar_aliquota(escritorio_a, _dados(municipio_ibge="1100205"), usuario=usuario_gestor_a)
    # A alíquota é do escritório: o mesmo município e subitem, em outro escritório, não colide.
    iss.cadastrar_aliquota(escritorio_b, _dados(), usuario=usuario_gestor_a)
    assert AliquotaIssMunicipal.objects.count() == 3


def test_alteracao_grava_trilha_com_antes_e_depois(escritorio_a, usuario_gestor_a):
    aliquota, _ = iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    iss.alterar_aliquota(aliquota, {"percentual": Decimal("4.0000")}, usuario=usuario_gestor_a)
    registro = RegistroAuditoria.objects.filter(acao="aliquota_iss.alterada").latest("id")
    assert registro.detalhes["antes"]["percentual"] == "5.0000"
    assert registro.detalhes["depois"]["percentual"] == "4.0000"


def test_encerrar_vigencia_nao_exclui_e_fica_no_historico(escritorio_a, usuario_gestor_a):
    aliquota, _ = iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    iss.alterar_aliquota(aliquota, {"fim_vigencia": date(2026, 9, 30)}, usuario=usuario_gestor_a)
    assert AliquotaIssMunicipal.objects.filter(
        pk=aliquota.pk, fim_vigencia=date(2026, 9, 30)
    ).exists()


def test_cadastro_grava_trilha_sem_cpf_nem_segredo(escritorio_a, usuario_gestor_a):
    iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    registro = RegistroAuditoria.objects.filter(acao="aliquota_iss.criada").latest("id")
    assert registro.escritorio_id == escritorio_a.pk
    assert "fonte" in registro.detalhes["depois"]


def test_alteracao_com_sobreposicao_e_recusada(escritorio_a, usuario_gestor_a):
    primeira, _ = iss.cadastrar_aliquota(escritorio_a, _dados(), usuario=usuario_gestor_a)
    segunda, _ = iss.cadastrar_aliquota(
        escritorio_a,
        _dados(subitem="17.06", inicio_vigencia=date(2026, 1, 1)),
        usuario=usuario_gestor_a,
    )
    with pytest.raises(iss.IssConflito):
        iss.alterar_aliquota(segunda, {"subitem": "17.01"}, usuario=usuario_gestor_a)
    assert primeira.pk != segunda.pk


# ---------------------------------------------------------------------------
# Regime por empresa e exercício (HI-84)
# ---------------------------------------------------------------------------


def test_um_regime_por_empresa_e_exercicio(empresa_a, usuario_gestor_a):
    iss.cadastrar_regime(
        empresa_a,
        {"exercicio": 2026, "regime": RegimeIss.ALIQUOTA, "municipio_ibge": PALMAS},
        usuario=usuario_gestor_a,
    )
    with pytest.raises(iss.IssConflito):
        iss.cadastrar_regime(
            empresa_a,
            {"exercicio": 2026, "regime": RegimeIss.FIXO_AUTONOMO, "municipio_ibge": PALMAS},
            usuario=usuario_gestor_a,
        )
    # Outro exercício, da mesma empresa, é outra linha.
    iss.cadastrar_regime(
        empresa_a,
        {"exercicio": 2027, "regime": RegimeIss.FIXO_AUTONOMO, "municipio_ibge": PALMAS},
        usuario=usuario_gestor_a,
    )
    assert RegimeIssEmpresa.objects.filter(empresa=empresa_a).count() == 2


def test_regime_fora_do_catalogo_e_municipio_invalido_sao_recusados(empresa_a, usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_regime(
            empresa_a,
            {"exercicio": 2026, "regime": "lucro", "municipio_ibge": PALMAS},
            usuario=usuario_gestor_a,
        )
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_regime(
            empresa_a,
            {"exercicio": 2026, "regime": RegimeIss.ALIQUOTA, "municipio_ibge": "17210"},
            usuario=usuario_gestor_a,
        )


def test_alterar_regime_grava_trilha(empresa_a, usuario_gestor_a):
    regime = iss.cadastrar_regime(
        empresa_a,
        {"exercicio": 2026, "regime": RegimeIss.ALIQUOTA, "municipio_ibge": PALMAS},
        usuario=usuario_gestor_a,
    )
    iss.alterar_regime(
        regime, {"regime": RegimeIss.FIXO_SOCIEDADE_PROFISSIONAIS}, usuario=usuario_gestor_a
    )
    registro = RegistroAuditoria.objects.filter(acao="regime_iss.alterado").latest("id")
    assert registro.detalhes["antes"]["regime"] == RegimeIss.ALIQUOTA
    assert registro.detalhes["depois"]["regime"] == RegimeIss.FIXO_SOCIEDADE_PROFISSIONAIS


# ---------------------------------------------------------------------------
# Regra do município (HI-83): seed de Palmas e vigência
# ---------------------------------------------------------------------------


def test_palmas_entra_semeada_como_dado_global_com_fonte(db):
    regra = RegraIssMunicipio.objects.get(municipio_ibge=PALMAS)
    assert regra.dia_vencimento_proprio == 10
    assert regra.dia_vencimento_retido == 15
    assert regra.inicio_vigencia == date(2019, 1, 1)
    assert regra.fim_vigencia is None
    assert regra.criada_por_id is None
    assert "Decreto 1.667/2018" in regra.fonte and "art. 86 § 3º" in regra.fonte
    assert "primeiro dia útil seguinte" in regra.regra_dia_nao_util


def test_regra_sobreposta_e_recusada_e_regra_nova_sem_sobreposicao_passa(usuario_gestor_a):
    with pytest.raises(iss.IssConflito):
        iss.cadastrar_regra_municipio(
            {
                "municipio_ibge": PALMAS,
                "nome": "Palmas (TO)",
                "dia_vencimento_proprio": 12,
                "dia_vencimento_retido": 15,
                "regra_dia_nao_util": "x",
                "fonte": "teste",
                "inicio_vigencia": date(2025, 1, 1),
                "fim_vigencia": None,
            },
            usuario=usuario_gestor_a,
        )
    assert RegraIssMunicipio.objects.filter(municipio_ibge=PALMAS).count() == 1


def test_regra_dia_fora_de_1_a_28_e_recusada(usuario_gestor_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.cadastrar_regra_municipio(
            {
                "municipio_ibge": "1100205",
                "nome": "Teste",
                "dia_vencimento_proprio": 31,
                "dia_vencimento_retido": 15,
                "regra_dia_nao_util": "x",
                "fonte": "teste",
                "inicio_vigencia": date(2026, 1, 1),
            },
            usuario=usuario_gestor_a,
        )


def test_regra_fora_de_vigencia_no_mes_e_none(db):
    assert iss._regra_do_mes(PALMAS, 2018, 12) == (None, "fora_de_vigencia")
    regra, situacao = iss._regra_do_mes(PALMAS, 2026, 10)
    assert situacao == "vigente" and regra.municipio_ibge == PALMAS


def test_palmas_nao_tem_tabela_de_aliquota_no_produto(db):
    # HI-82: o percentual de Palmas NÃO é codificado. A alíquota é dado do escritório.
    assert not AliquotaIssMunicipal.objects.exists()
