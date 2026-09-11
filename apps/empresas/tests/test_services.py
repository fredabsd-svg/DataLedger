from datetime import date

import pytest

from apps.empresas.models import Empresa, RegimeTributario
from apps.empresas.services import registrar_regime_tributario
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa():
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    return Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )


def test_novo_regime_fecha_o_periodo_anterior(empresa):
    primeiro = registrar_regime_tributario(
        empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 1, 1)
    )

    segundo = registrar_regime_tributario(
        empresa, RegimeTributario.LUCRO_PRESUMIDO, date(2025, 1, 1)
    )

    primeiro.refresh_from_db()
    assert primeiro.vigencia_fim == date(2024, 12, 31)
    assert segundo.vigencia_fim is None
    assert segundo.regime == RegimeTributario.LUCRO_PRESUMIDO


def test_nao_permite_vigencia_anterior_ao_periodo_atual(empresa):
    registrar_regime_tributario(empresa, RegimeTributario.SIMPLES_NACIONAL, date(2024, 6, 1))

    with pytest.raises(ValueError):
        registrar_regime_tributario(empresa, RegimeTributario.LUCRO_REAL, date(2024, 1, 1))
