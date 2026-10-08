"""DL-076 (frente A), critérios 2, 3, 4 e 6: apuração do ISS próprio de Palmas.

Dados 100% sintéticos, pelo pipeline real de recepção e de efetivação. Os valores esperados
são escritos À MÃO (ver o quadro em `suporte_iss_dl076.cenario_outubro`):

competência 10/2026, ISS devido pelo prestador, Palmas:
  1001  17.01  base 1000,00  5%  devido 50,00   conforme
  1002  07.02  base  200,00  3%  devido  6,00   conforme
  1003  17.01  base  333,33  5%  devido 16,67   conforme (diferença 0,0035 ≤ 0,01)
  1004  17.01  base 1000,00  5%  devido 40,00   PENDÊNCIA (esperado 50,00)
  1005  17.01  base 1000,00  5%  devido 50,01   conforme (diferença 0,01, sem passar do limite)
  1006  17.01  base 1000,00  5%  devido 50,02   PENDÊNCIA (diferença 0,02)
  1007  17.01  base  500,00  5%  devido 25,00   conforme; dCompet 31/10, dhEmi 02/11
TOTAL = 50,00 + 6,00 + 16,67 + 40,00 + 50,01 + 50,02 + 25,00 = 237,70
Fora do total: 2001 retida (30,00); 3001 outro município (99,00); 4001 exportação (0,00);
5001 imune (0,00); 7001 devido com cLocIncid de outro município (11,00).
"""

from datetime import date
from decimal import Decimal

import pytest

from apps.empresas.models import HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import iss_municipal as iss
from apps.fiscal import services
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    PapelDocumento,
    RegimeIss,
    RegimeIssEmpresa,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.suporte_iss_dl076 import (
    DEVIDO,
    OUTRO_MUNICIPIO,
    PALMAS,
    aliquota,
    cenario_outubro,
    receber,
    regime_aliquota,
)
from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, xml_evento

pytestmark = pytest.mark.django_db

HOJE = date(2026, 10, 20)


@pytest.fixture
def cenario(escritorio_a, usuario_gestor_a, empresa_a):
    return cenario_outubro(escritorio_a, usuario_gestor_a, empresa_a)


def _numeros(notas):
    return {nota.numero for nota in notas}


def _apurar(empresa, ano=2026, mes=10, **kwargs):
    return iss.apuracao_iss_proprio(empresa, ano, mes, hoje=kwargs.pop("hoje", HOJE), **kwargs)


def _recusa(empresa, ano=2026, mes=10):
    with pytest.raises(iss.IssRecusado) as excinfo:
        _apurar(empresa, ano, mes)
    return excinfo.value


# ---------------------------------------------------------------------------
# Critério 2 — total = soma do vISSQN das notas de ISS próprio da competência
# ---------------------------------------------------------------------------


def test_total_e_a_soma_do_vissqn_das_notas_de_iss_proprio_da_competencia(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    assert resultado.total == Decimal("237.70")
    assert _numeros(resultado.notas) == {"1001", "1002", "1003", "1004", "1005", "1006", "1007"}


def test_retida_outro_municipio_exportacao_imune_e_fora_da_lista_nao_entram(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    fora = {"2001", "3001", "4001", "5001", "7001"}
    assert fora.isdisjoint(_numeros(resultado.notas))
    # A soma exclui 30,00 (retida), 99,00 (outro município), 11,00 (devido com incidência
    # de outro município) e os zeros. Incluir qualquer um deles muda o total.
    assert resultado.total != Decimal("237.70") + Decimal("30.00")
    assert resultado.total == Decimal("237.70")


def test_devido_com_incidencia_de_outro_municipio_vira_aviso_e_fica_fora(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    avisos = [a for a in resultado.avisos if a.codigo == "incidencia_em_outro_municipio"]
    assert len(avisos) == 1
    assert "7001" in avisos[0].mensagem
    assert OUTRO_MUNICIPIO in avisos[0].mensagem


def test_competencia_e_dcompet_e_nao_a_emissao(cenario, empresa_a):
    # 1007 foi emitida em 02/11/2026, com dCompet 31/10/2026: é nota de OUTUBRO. Um mutante
    # que usa a data de emissão a tiraria de 10/2026 e a colocaria em 11/2026.
    out = _apurar(empresa_a, 2026, 10)
    assert "1007" in _numeros(out.notas)
    nov = _apurar(empresa_a, 2026, 11)
    assert "1007" not in _numeros(nov.notas)
    assert nov.total == Decimal("0.00")


def test_rascunho_nao_entra_na_apuracao(escritorio_a, usuario_gestor_a, empresa_a):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    documento = receber(
        escritorio_a, usuario_gestor_a, 8001, None, c_trib_nac="170101", v_iss_qn="50.00"
    )
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, papel=PapelDocumento.PRESTADOR, empresa=empresa_a
    )
    servico_escrituracao.salvar_rascunho(vinculo, DEVIDO, usuario_gestor_a)
    resultado = _apurar(empresa_a)
    assert resultado.total == Decimal("0.00")
    assert resultado.notas == ()


def test_nota_de_outra_empresa_do_mesmo_escritorio_nao_entra(
    cenario, escritorio_a, usuario_gestor_a, empresa_a, empresa_a2
):
    # Prestadora A2 do mesmo escritório, com ISS devido em Palmas. Não é da empresa A.
    # Um mutante que tira o filtro `empresa=` soma os 77,00 aqui.
    receber(
        escritorio_a,
        usuario_gestor_a,
        9001,
        DEVIDO,
        prestador="44555666000100",
        tomador_documento="99888777000166",
        c_trib_nac="170101",
        v_iss_qn="77.00",
        v_bc="1000.00",
    )
    resultado = _apurar(empresa_a)
    assert resultado.total == Decimal("237.70")
    assert "9001" not in _numeros(resultado.notas)


def test_nota_cancelada_depois_de_escriturada_bloqueia_a_apuracao(
    cenario, escritorio_a, usuario_gestor_a, empresa_a
):
    documento = cenario["n1"]
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo="cancelamento.xml",
    )
    recusa = _recusa(empresa_a)
    codigos = {b.codigo for b in recusa.bloqueios}
    assert "nota_cancelada_escriturada" in codigos
    assert "1001" in " ".join(b.mensagem for b in recusa.bloqueios)


def test_retencao_no_xml_de_nota_escriturada_como_devida_bloqueia(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        9101,
        DEVIDO,
        c_trib_nac="170101",
        tp_ret_issqn="2",
        v_iss_qn="50.00",
    )
    recusa = _recusa(empresa_a)
    assert {b.codigo for b in recusa.bloqueios} == {"nota_retida_com_natureza_devida"}


# ---------------------------------------------------------------------------
# Critério 3 — conferência: diferença acima de R$ 0,01 é pendência; dentro, não
# ---------------------------------------------------------------------------


def test_conferencia_marca_pendencia_so_acima_da_tolerancia(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    pendentes = {n.numero for n in resultado.pendencias}
    # 1004: declarado 40,00, esperado 50,00. 1006: diferença 0,02. 1005: diferença 0,01 (não
    # passa do limite). 1003: diferença 0,0035.
    assert pendentes == {"1004", "1006"}


def test_pendencia_traz_os_dois_valores_declarado_e_esperado(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    nota = next(n for n in resultado.notas if n.numero == "1004")
    assert nota.v_iss_qn == Decimal("40.00")
    assert nota.esperado == Decimal("50")
    assert nota.diferenca == Decimal("-10")
    assert nota.aliquota_cadastrada == Decimal("5.0000")
    assert nota.conferida is False


def test_diferenca_de_exatamente_um_centavo_e_conforme(cenario, empresa_a):
    nota = next(n for n in _apurar(empresa_a).notas if n.numero == "1005")
    assert nota.diferenca == Decimal("0.01")
    assert nota.conferida is True


def test_diferenca_de_dois_centavos_e_pendencia(cenario, empresa_a):
    nota = next(n for n in _apurar(empresa_a).notas if n.numero == "1006")
    assert nota.diferenca == Decimal("0.02")
    assert nota.conferida is False


def test_conferencia_usa_a_base_vbc_nao_o_servico(escritorio_a, usuario_gestor_a, empresa_a):
    # vServ 1000,00, vDescIncond 100,00, vDR 50,00 → vBC 850,00. Esperado = 850 × 5% = 42,50.
    # Se a conferência usasse vServ, esperaria 50,00 e marcaria pendência à toa.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        9201,
        DEVIDO,
        c_trib_nac="170101",
        v_serv="1000.00",
        v_desc_incond="100.00",
        v_dr="50.00",
        v_bc="850.00",
        v_iss_qn="42.50",
    )
    resultado = _apurar(empresa_a)
    nota = resultado.notas[0]
    assert nota.esperado == Decimal("42.5")
    assert nota.conferida is True
    assert resultado.total == Decimal("42.50")


def test_base_que_nao_bate_com_os_termos_vira_aviso_na_nota(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        9301,
        DEVIDO,
        c_trib_nac="170101",
        v_serv="1000.00",
        v_desc_incond="100.00",
        v_dr="50.00",
        v_bc="900.00",
        v_iss_qn="45.00",
    )
    resultado = _apurar(empresa_a)
    nota = resultado.notas[0]
    assert nota.avisos, "a base divergente tem de sair como aviso na nota"
    assert "(900.00)" in nota.avisos[0] and "(850.00)" in nota.avisos[0]
    # A pendência é só da conferência do imposto; o aviso de base não bloqueia nem recalcula.
    assert resultado.total == Decimal("45.00")


# ---------------------------------------------------------------------------
# Critério 4 — recusa nomeada: subitem sem alíquota, regime, regra, campo ausente
# ---------------------------------------------------------------------------


def test_subitem_sem_aliquota_recusa_listando_o_subitem(
    cenario, escritorio_a, usuario_gestor_a, empresa_a
):
    receber(escritorio_a, usuario_gestor_a, 9401, DEVIDO, c_trib_nac="170601", v_iss_qn="10.00")
    recusa = _recusa(empresa_a)
    bloqueio = next(b for b in recusa.bloqueios if b.codigo == "subitem_sem_aliquota_vigente")
    assert "17.06" in bloqueio.mensagem


def test_aliquota_que_cobre_so_parte_do_mes_recusa_com_motivo_proprio(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(
        escritorio_a,
        usuario_gestor_a,
        "17.01",
        "4.0000",
        inicio=date(2019, 1, 1),
        fim=date(2026, 10, 15),
    )
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 9501, DEVIDO, c_trib_nac="170101", v_iss_qn="40.00")
    recusa = _recusa(empresa_a)
    bloqueio = next(b for b in recusa.bloqueios if b.codigo == "subitem_sem_aliquota_vigente")
    assert "cobre só parte do mês" in bloqueio.mensagem


def test_regime_ausente_recusa(empresa_b):
    recusa = _recusa(empresa_b)
    assert {b.codigo for b in recusa.bloqueios} == {"regime_iss_ausente"}


def test_regime_fixo_recusa_e_lista_as_notas_com_iss_destacado(
    escritorio_a, usuario_gestor_a, empresa_a
):
    RegimeIssEmpresa.objects.create(
        empresa=empresa_a,
        exercicio=2026,
        regime=RegimeIss.FIXO_AUTONOMO,
        municipio_ibge=PALMAS,
        criado_por=usuario_gestor_a,
    )
    receber(escritorio_a, usuario_gestor_a, 9601, DEVIDO, c_trib_nac="170101", v_iss_qn="10.00")
    receber(escritorio_a, usuario_gestor_a, 9602, DEVIDO, c_trib_nac="170101", v_iss_qn="0.00")
    recusa = _recusa(empresa_a)
    assert {b.codigo for b in recusa.bloqueios} == {"regime_fixo"}
    assert "fixo" in recusa.bloqueios[0].mensagem.lower()
    # Lista as duas notas, e marca a que traz ISS destacado.
    assert {n.numero for n in recusa.notas} == {"9601", "9602"}
    assert "9601" in recusa.bloqueios[0].mensagem
    assert "9602" not in recusa.bloqueios[0].mensagem.split("Com ISS destacado")[-1]


def test_regra_do_municipio_ausente_recusa(escritorio_a, usuario_gestor_a, empresa_a):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a, municipio=OUTRO_MUNICIPIO)
    recusa = _recusa(empresa_a)
    assert "regra_municipio_ausente" in {b.codigo for b in recusa.bloqueios}


def test_simples_no_mes_recusa_e_manda_para_o_pre_das(escritorio_a, usuario_gestor_a, empresa_a):
    HistoricoRegimeTributario.objects.create(
        empresa=empresa_a,
        regime=RegimeTributario.SIMPLES_NACIONAL,
        vigencia_inicio=date(2018, 1, 1),
    )
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    recusa = _recusa(empresa_a)
    bloqueio = next(b for b in recusa.bloqueios if b.codigo == "empresa_no_simples")
    assert "pré-DAS" in bloqueio.mensagem


def test_nota_sem_vbc_recusa_nomeando_o_campo_e_nao_presume_zero(
    escritorio_a, usuario_gestor_a, empresa_a
):
    # Um mutante que trata vBC ausente como zero viraria pendência com esperado 0 e total
    # calculado. Aqui tem de ser recusa, e o nome do campo tem de aparecer.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(
        escritorio_a,
        usuario_gestor_a,
        9701,
        DEVIDO,
        c_trib_nac="170101",
        v_bc=None,
        v_iss_qn="50.00",
        v_serv="1000.00",
    )
    recusa = _recusa(empresa_a)
    bloqueio = next(b for b in recusa.bloqueios if b.codigo == "nota_sem_campo_de_iss")
    assert "vBC" in bloqueio.mensagem
    assert "zero" in bloqueio.mensagem


def test_nota_sem_visqn_recusa_nomeando_o_campo_e_nao_soma_zero(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 9801, DEVIDO, c_trib_nac="170101", v_iss_qn=None)
    recusa = _recusa(empresa_a)
    bloqueio = next(b for b in recusa.bloqueios if b.codigo == "nota_sem_campo_de_iss")
    assert "vISSQN" in bloqueio.mensagem


def test_todos_os_bloqueios_sao_coletados_de_uma_vez(escritorio_a, usuario_gestor_a, empresa_a):
    # Subitem sem alíquota E nota sem vBC: a recusa lista os dois, como o pré-DAS.
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000")
    regime_aliquota(empresa_a, usuario_gestor_a)
    receber(escritorio_a, usuario_gestor_a, 9901, DEVIDO, c_trib_nac="170601", v_iss_qn="10.00")
    receber(
        escritorio_a,
        usuario_gestor_a,
        9902,
        DEVIDO,
        c_trib_nac="170101",
        v_bc=None,
        v_iss_qn="10.00",
    )
    recusa = _recusa(empresa_a)
    assert {b.codigo for b in recusa.bloqueios} >= {
        "subitem_sem_aliquota_vigente",
        "nota_sem_campo_de_iss",
    }


# ---------------------------------------------------------------------------
# Vigência da alíquota (mutação c)
# ---------------------------------------------------------------------------


def test_aliquota_e_a_vigente_na_competencia_e_nao_a_de_outro_periodo(
    escritorio_a, usuario_gestor_a, empresa_a
):
    aliquota(
        escritorio_a,
        usuario_gestor_a,
        "17.01",
        "4.0000",
        inicio=date(2019, 1, 1),
        fim=date(2026, 9, 30),
    )
    aliquota(escritorio_a, usuario_gestor_a, "17.01", "5.0000", inicio=date(2026, 10, 1))
    regime_aliquota(empresa_a, usuario_gestor_a)
    # Em 10/2026 a alíquota é 5%: 1000 × 5% = 50,00 confere. Se a vigência fosse ignorada,
    # a alíquota de 4% (de 09/2026) seria escolhida e 50,00 apareceria como pendência.
    receber(escritorio_a, usuario_gestor_a, 10001, DEVIDO, c_trib_nac="170101", v_iss_qn="50.00")
    # Em 09/2026 a alíquota é 4%: 1000 × 4% = 40,00.
    receber(
        escritorio_a,
        usuario_gestor_a,
        10002,
        DEVIDO,
        c_trib_nac="170101",
        v_iss_qn="40.00",
        d_compet="2026-09-05",
        dh_emi="2026-09-05T10:00:00-03:00",
    )
    out = _apurar(empresa_a, 2026, 10)
    assert out.notas[0].aliquota_cadastrada == Decimal("5.0000")
    assert out.pendencias == ()
    set_ = _apurar(empresa_a, 2026, 9)
    assert set_.notas[0].aliquota_cadastrada == Decimal("4.0000")
    assert set_.pendencias == ()


# ---------------------------------------------------------------------------
# Critério 6 — vencimento: 10/2026 → 10/11/2026 (próprio) e 15/11/2026 (retido)
# ---------------------------------------------------------------------------


def test_vencimento_de_10_2026_e_10_11_e_15_11(cenario, empresa_a):
    resultado = _apurar(empresa_a)
    assert resultado.vencimento_proprio == date(2026, 11, 10)
    assert resultado.vencimento_retido == date(2026, 11, 15)
    assert "primeiro dia útil seguinte" in resultado.regra_dia_nao_util
    assert resultado.municipio_ibge == PALMAS
    assert resultado.nome_municipio == "Palmas (TO)"


def test_vencimento_de_dezembro_cai_em_janeiro_do_ano_seguinte(
    escritorio_a, usuario_gestor_a, empresa_a
):
    regime_aliquota(empresa_a, usuario_gestor_a, exercicio=2026)
    resultado = _apurar(empresa_a, 2026, 12)
    assert resultado.vencimento_proprio == date(2027, 1, 10)
    assert resultado.vencimento_retido == date(2027, 1, 15)


def test_aviso_de_multa_so_quando_a_data_de_hoje_passou_do_vencimento(cenario, empresa_a):
    assert _apurar(empresa_a, hoje=date(2026, 11, 10)).aviso_multa is None
    aviso = _apurar(empresa_a, hoje=date(2026, 11, 11)).aviso_multa
    assert aviso is not None
    assert "0,33%" in aviso and "LC 285/2013, art. 142" in aviso


def test_memoria_de_calculo_traz_dispositivo_por_passo(cenario, empresa_a):
    memoria = _apurar(empresa_a).memoria
    assert [p.ordem for p in memoria] == [1, 2, 3, 4, 5]
    assert all(p.dispositivo for p in memoria)
    passo_total = next(p for p in memoria if p.ordem == 4)
    assert passo_total.valor == "237.70"
    passo_venc = next(p for p in memoria if p.ordem == 2)
    assert "10/11/2026" in passo_venc.valor and "15/11/2026" in passo_venc.valor


def test_apuracao_nao_grava_nada(cenario, empresa_a):
    antes = AliquotaIssMunicipal.objects.count(), RegimeIssEmpresa.objects.count()
    _apurar(empresa_a)
    assert (AliquotaIssMunicipal.objects.count(), RegimeIssEmpresa.objects.count()) == antes


def test_competencia_invalida_e_recusada_antes_de_qualquer_calculo(empresa_a):
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.apuracao_iss_proprio(empresa_a, 2026, 13)
    with pytest.raises(iss.EntradaInvalidaIss):
        iss.apuracao_iss_proprio(empresa_a, True, 10)
