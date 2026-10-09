"""DL-081 (frente A), avisos de IBS/CBS (item 6; HI-123). Só avisam: nada entra na receita.

Os três avisos e os limites da regra: CRT 1, 2 e 4 com grupo em 2026; CRT 3 sem grupo a partir de
03/08/2026 (no dia de São Paulo, não no UTC); `vNFTot` diferente de `vNF + vIBS + vCBS + vIS`.
Funções puras: a nota e a leitura são objetos simples, com valores escritos à mão.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from apps.fiscal import escrituracao_nfe as servico

SP = ZoneInfo("America/Sao_Paulo")


def nota(*, crt="1", presente=True, emissao=datetime(2026, 3, 15, 10, 0, tzinfo=SP), v_nf="100.00"):
    return SimpleNamespace(
        emitente_crt=crt,
        tem_ibscbs_total=presente,
        tem_ibscbs_item=False,
        dh_emissao=emissao,
        v_nf=None if v_nf is None else Decimal(v_nf),
    )


def leitura(*, v_nf_tot=None, v_ibs=None, v_cbs=None, v_is=None):
    def d(valor):
        return None if valor is None else Decimal(valor)

    return SimpleNamespace(v_nf_tot=d(v_nf_tot), v_ibs=d(v_ibs), v_cbs=d(v_cbs), v_is=d(v_is))


def codigos(avisos):
    return [a.codigo for a in avisos]


# --- grupo presente em CRT 1, 2 ou 4 em 2026 ----------------------------------------------------


def test_grupo_presente_em_crt_1_2_4_em_2026_avisa():
    for crt in ("1", "2", "4"):
        assert codigos(servico.avisos_ibscbs(nota(crt=crt), None)) == [
            "ibscbs_presente_em_crt_1_2_4"
        ], crt


def test_grupo_presente_em_crt_3_nao_avisa_por_esse_motivo():
    assert codigos(servico.avisos_ibscbs(nota(crt="3"), None)) == []


def test_grupo_presente_em_2025_nao_avisa():
    nota_2025 = nota(crt="1", emissao=datetime(2025, 12, 31, 12, 0, tzinfo=SP))
    assert codigos(servico.avisos_ibscbs(nota_2025, None)) == []


def test_grupo_ausente_em_crt_1_nao_avisa():
    assert codigos(servico.avisos_ibscbs(nota(crt="1", presente=False), None)) == []


# --- grupo ausente em CRT 3 a partir de 03/08/2026 ---------------------------------------------


def test_grupo_ausente_em_crt_3_a_partir_de_3_de_agosto_avisa():
    dia = nota(crt="3", presente=False, emissao=datetime(2026, 8, 3, 9, 0, tzinfo=SP))
    assert codigos(servico.avisos_ibscbs(dia, None)) == ["ibscbs_ausente_em_crt_3"]


def test_grupo_ausente_em_crt_3_antes_de_3_de_agosto_nao_avisa():
    antes = nota(crt="3", presente=False, emissao=datetime(2026, 8, 2, 23, 30, tzinfo=SP))
    assert codigos(servico.avisos_ibscbs(antes, None)) == []


def test_limite_de_data_usa_o_dia_de_sao_paulo_e_nao_o_utc():
    """02/08 às 23:30 em Brasília é 03/08 em UTC (02:30). O aviso segue o dia de São Paulo: não
    dispara."""
    emissao = datetime(2026, 8, 2, 23, 30, tzinfo=SP)
    assert emissao.astimezone(ZoneInfo("UTC")).day == 3
    assert (
        codigos(servico.avisos_ibscbs(nota(crt="3", presente=False, emissao=emissao), None)) == []
    )


def test_grupo_ausente_em_crt_2_nao_avisa_por_esse_motivo():
    assert codigos(servico.avisos_ibscbs(nota(crt="2", presente=False), None)) == []


# --- vNFTot diferente de vNF + vIBS + vCBS + vIS ------------------------------------------------


def test_vnftot_igual_a_soma_nao_avisa():
    dados = nota(crt="3", presente=True, v_nf="100.00")
    assert (
        codigos(
            servico.avisos_ibscbs(
                dados, leitura(v_nf_tot="101.00", v_ibs="0.10", v_cbs="0.90", v_is="0.00")
            )
        )
        == []
    )


def test_vnftot_diferente_da_soma_avisa_por_um_centavo():
    dados = nota(crt="3", presente=True, v_nf="100.00")
    avisos = servico.avisos_ibscbs(dados, leitura(v_nf_tot="101.01", v_ibs="0.10", v_cbs="0.90"))
    assert codigos(avisos) == ["vnftot_incoerente"]
    assert "101.01" in avisos[0].mensagem and "101.00" in avisos[0].mensagem


def test_is_ausente_vale_zero_na_formula_do_vnftot():
    """IS pode não existir na nota: ausente conta como zero nesta conferência (decisão da
    DL-081)."""
    dados = nota(crt="3", presente=True, v_nf="100.00")
    assert codigos(servico.avisos_ibscbs(dados, leitura(v_nf_tot="100.10", v_ibs="0.10"))) == []


def test_vnftot_ausente_nao_avisa():
    dados = nota(crt="3", presente=True, v_nf="100.00")
    assert codigos(servico.avisos_ibscbs(dados, leitura(v_ibs="0.10", v_cbs="0.90"))) == []


def test_sem_vnf_nao_ha_como_conferir_e_nao_avisa():
    dados = nota(crt="3", presente=True, v_nf=None)
    assert codigos(servico.avisos_ibscbs(dados, leitura(v_nf_tot="5.00"))) == []


def test_aviso_traz_o_dispositivo_citado():
    avisos = servico.avisos_ibscbs(nota(crt="1"), None)
    assert avisos[0].dispositivo.startswith("LC 214/2025, art. 348")
