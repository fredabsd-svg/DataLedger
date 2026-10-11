"""DL-084, item 2 (HI-137) e critério 8: tabela de feriados locais pelo banco, com a praça da
empresa.

- A carga da migração 0015 traz lei e data da leitura em TODA linha (critério 8).
- A praça é o município do estabelecimento MATRIZ. Sem matriz com município e UF, nenhum feriado.
- Exceção por ano: 05/10/2026 observado em 09/10/2026 em Palmas, com aviso bancário na data
observada.
- Dados sintéticos: empresas e estabelecimentos de teste. Os feriados são os da carga real (lei
lida).
"""

from datetime import date

import pytest
from django.db import IntegrityError, transaction

from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento
from apps.fiscal import presumido as servico
from apps.fiscal import presumido_calculo as calc
from apps.fiscal.models import ExcecaoFeriadoLocal, FeriadoLocal

pytestmark = pytest.mark.django_db

CNPJ_MATRIZ_TESTE = "11222333000181"
AVISO_BANCARIO_PALMAS = "feriado bancário em Palmas (Febraban)"
AVISO_ANTECIPAR = "antecipar: sem expediente bancário na praça"
AVISO_CONFIRMAR = "feriado local: confirmar expediente bancário na praça"


def _matriz(empresa, municipio, uf):
    Estabelecimento.objects.create(
        empresa=empresa,
        tipo=TipoEstabelecimento.MATRIZ,
        nome="Matriz sintética",
        cnpj=CNPJ_MATRIZ_TESTE,
        municipio=municipio,
        uf=uf,
    )


@pytest.fixture
def empresa_palmas(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente Palmas Ltda", cnpj="77888999000155"
    )
    _matriz(empresa, "Palmas", "TO")
    return empresa


def _avisos(dia, empresa):
    praca, feriados = servico._feriados_locais_da_praca(empresa)
    return calc.avisos_de_feriado_local(dia, feriados, praca) if praca else ()


# ---------------------------------------------------------------------------
# Critério 8: cada linha da carga cita a lei e a data da leitura
# ---------------------------------------------------------------------------


def test_toda_linha_de_feriado_local_cita_lei_e_data_da_leitura():
    feriados = FeriadoLocal.objects.all()
    assert feriados.count() >= 8
    for feriado in feriados:
        assert feriado.fundamento.strip(), feriado.descricao
        assert feriado.data_leitura == date(2026, 10, 9), feriado.descricao


def test_toda_excecao_por_ano_cita_o_ato_e_a_data_da_leitura():
    excecoes = ExcecaoFeriadoLocal.objects.all()
    assert excecoes.count() == 2
    for excecao in excecoes:
        assert excecao.fundamento.strip()
        assert excecao.data_leitura == date(2026, 10, 9)


def test_carga_de_palmas_traz_as_cinco_datas_da_hi_137_e_nao_o_18_de_marco():
    nomes = {(f.mes, f.dia, f.municipio) for f in FeriadoLocal.objects.filter(uf="TO")}
    assert {(8, 15, ""), (9, 8, ""), (10, 5, ""), (3, 19, "PALMAS"), (5, 20, "PALMAS")} <= nomes
    assert (3, 18, "") not in nomes and (3, 18, "PALMAS") not in nomes


def test_linha_de_feriado_sem_lei_e_recusada_pelo_banco(empresa_palmas):
    with pytest.raises(IntegrityError), transaction.atomic():
        FeriadoLocal.objects.create(
            uf="TO",
            municipio="SEMLEI",
            esfera="municipal",
            mes=1,
            dia=2,
            descricao="sem lei",
            fundamento="",
            data_leitura=date(2026, 10, 9),
            vigencia_inicio=date(2026, 1, 1),
        )


# ---------------------------------------------------------------------------
# Critério 2: praça, dois níveis de aviso, exceção por ano, e a data não muda
# ---------------------------------------------------------------------------


def test_empresa_de_palmas_recebe_os_dois_niveis_de_aviso(empresa_palmas):
    # 19/03/2027: São José em Palmas, com confirmação bancária. Dois avisos.
    assert _avisos(date(2027, 3, 19), empresa_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    # 05/10/2027: a lei estadual fixa, a lista da Febraban não traz para Palmas em 2027. Aviso
    # fraco.
    assert _avisos(date(2027, 10, 5), empresa_palmas) == (AVISO_CONFIRMAR,)


def test_excecao_de_2026_tira_o_aviso_de_05_10_e_poe_o_bancario_em_09_10(empresa_palmas):
    assert _avisos(date(2026, 10, 5), empresa_palmas) == ()
    assert _avisos(date(2026, 10, 9), empresa_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)


def test_excecao_so_vale_em_2026(empresa_palmas):
    # Em 2027, 05/10 volta a ser a data normativa, com o aviso fraco. 09/10/2027 não avisa.
    assert _avisos(date(2027, 10, 9), empresa_palmas) == ()


def test_empresa_sem_matriz_com_praca_nao_recebe_feriado_local(escritorio_a):
    sem_matriz = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Sem matriz Ltda", cnpj="77888999000156"
    )
    assert servico._feriados_locais_da_praca(sem_matriz) == (None, ())
    assert _avisos(date(2027, 3, 19), sem_matriz) == ()


def test_praca_de_outro_estado_so_recebe_os_feriados_do_proprio_estado(escritorio_a):
    sao_paulo = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente SP Ltda", cnpj="77888999000157"
    )
    _matriz(sao_paulo, "São Paulo", "SP")
    assert servico._feriados_locais_da_praca(sao_paulo) == ("São Paulo", ())


def test_estado_sem_municipio_especifico_recebe_so_a_lei_estadual(escritorio_a):
    # Araguaína/TO não tem linha bancária própria: aviso fraco para a lei estadual, sem Palmas.
    araguaina = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente Araguaína Ltda", cnpj="77888999000158"
    )
    _matriz(araguaina, "Araguaína", "TO")
    assert _avisos(date(2027, 8, 15), araguaina) == (AVISO_CONFIRMAR,)
    assert _avisos(date(2027, 3, 19), araguaina) == ()


def test_municipio_da_matriz_casa_sem_acento_e_sem_caixa(escritorio_a):
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente caixa Ltda", cnpj="77888999000159"
    )
    _matriz(empresa, "  palmas ", "TO")
    praca, _feriados = servico._feriados_locais_da_praca(empresa)
    assert praca == "palmas"
    # O casamento ignora caixa e acento: o aviso bancário de Palmas sai mesmo assim (o nome da
    # praça aparece como foi digitado na matriz).
    avisos = _avisos(date(2027, 3, 19), empresa)
    assert len(avisos) == 2 and avisos[1] == AVISO_ANTECIPAR
    assert avisos[0].startswith("feriado bancário em ") and avisos[0].endswith("(Febraban)")


def test_a_linha_da_praca_substitui_a_da_uf_no_mesmo_dia(empresa_palmas):
    # 15/08 existe na UF (sem fonte) e em Palmas (com fonte): vale a de Palmas, um aviso só.
    _praca, feriados = servico._feriados_locais_da_praca(empresa_palmas)
    dias_de_15_08 = [f for f in feriados if (f.mes, f.dia) == (8, 15)]
    assert len(dias_de_15_08) == 1
    assert dias_de_15_08[0].fonte_bancaria


# ---------------------------------------------------------------------------
# Escopo do escritório (DE-106, achado A1 da auditoria da DL-084)
# ---------------------------------------------------------------------------


def _empresa_de_palmas(escritorio, razao, cnpj):
    empresa = Empresa.objects.create(escritorio=escritorio, razao_social=razao, cnpj=cnpj)
    _matriz(empresa, "Palmas", "TO")
    return empresa


def _feriado_do_escritorio(escritorio, **extra):
    dados = {
        "escritorio": escritorio,
        "uf": "TO",
        "municipio": "PALMAS",
        "esfera": "municipal",
        "fundamento": "Lei municipal sintética nº B/2026",
        "data_leitura": date(2026, 10, 9),
        "fonte_bancaria": "",
        "vigencia_inicio": date(2026, 1, 1),
    }
    dados.update(extra)
    return FeriadoLocal.objects.create(**dados)


def test_a_linha_do_escritorio_nao_afeta_as_empresas_de_outro_escritorio(
    escritorio_b, empresa_palmas
):
    empresa_b_palmas = _empresa_de_palmas(escritorio_b, "Cliente B Palmas Ltda", "77888999000161")
    linha_b = _feriado_do_escritorio(
        escritorio_b,
        mes=1,
        dia=2,
        descricao="Feriado sintético do escritório B",
        fonte_bancaria="Febraban (teste sintético)",
    )
    # A linha do escritório B vale para as empresas dele…
    assert _avisos(date(2027, 1, 2), empresa_b_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    # …e para as empresas do escritório A ela não existe: o aviso nem nasce.
    assert _avisos(date(2027, 1, 2), empresa_palmas) == ()
    _praca, feriados = servico._feriados_locais_da_praca(empresa_palmas)
    assert all(f.descricao != linha_b.descricao for f in feriados)


def test_a_linha_do_escritorio_substitui_a_da_base_no_mesmo_dia(escritorio_a, empresa_palmas):
    # 15/08 da base (Palmas, com a lista bancária) avisa que a praça fecha…
    assert _avisos(date(2027, 8, 15), empresa_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    # …a linha do escritório A do mesmo dia, sem fonte, substitui a da base para as empresas dele,
    # e o dia fica com UM aviso só (o mais fraco), nunca dois.
    _feriado_do_escritorio(
        escritorio_a,
        mes=8,
        dia=15,
        descricao="15/08 do escritório A",
        fundamento="Lei sintética nº A/2026",
    )
    assert _avisos(date(2027, 8, 15), empresa_palmas) == (AVISO_CONFIRMAR,)


def test_excecao_do_escritorio_substitui_a_da_base_so_para_as_empresas_dele(
    escritorio_b, empresa_palmas
):
    empresa_b_palmas = _empresa_de_palmas(escritorio_b, "Cliente B Palmas Ltda", "77888999000161")
    # Base: o 05/10 de 2026 foi observado em 09/10 (decreto carregado) — o aviso sai em 09/10.
    assert _avisos(date(2026, 10, 9), empresa_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    assert _avisos(date(2026, 10, 5), empresa_palmas) == ()

    # O escritório B registra o PRÓPRIO 05/10 e a PRÓPRIA exceção de 2026 (observada em 08/10).
    linha_b = _feriado_do_escritorio(
        escritorio_b,
        mes=10,
        dia=5,
        descricao="05/10 do escritório B",
        fonte_bancaria="Febraban (teste sintético)",
    )
    ExcecaoFeriadoLocal.objects.create(
        escritorio=escritorio_b,
        feriado=linha_b,
        ano=2026,
        data_observada=date(2026, 10, 8),
        fundamento="Decreto sintético nº B/2026",
        data_leitura=date(2026, 10, 9),
        fonte_bancaria="Febraban (teste sintético)",
    )

    # Para as empresas dele, a exceção do escritório substitui a da base no mesmo ano: o aviso vai
    # para 08/10 e a data observada da base (09/10) deixa de avisar.
    assert _avisos(date(2026, 10, 8), empresa_b_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    assert _avisos(date(2026, 10, 9), empresa_b_palmas) == ()
    assert _avisos(date(2026, 10, 5), empresa_b_palmas) == ()

    # E para as empresas do escritório A, NADA mudou.
    assert _avisos(date(2026, 10, 9), empresa_palmas) == (AVISO_BANCARIO_PALMAS, AVISO_ANTECIPAR)
    assert _avisos(date(2026, 10, 8), empresa_palmas) == ()
    assert _avisos(date(2026, 10, 5), empresa_palmas) == ()
