"""DL-074 — R2 da reconferência: a checagem de receita igual é isolada por empresa.

Mutantes que sobreviveram à rodada 1 da reconferência:
- N8d: a checagem de duplicata sem `empresa=travada` faria a receita de uma empresa
  bloquear o lançamento de OUTRA empresa (ou de outro escritório), vazando número e data
  da receita alheia na mensagem.

O teste de concorrência (N8e, sem a trava da empresa antes da checagem) fica em
`test_dl074_r2_duplicata_concorrencia.py`, porque precisa de commits reais entre threads.

Dados sintéticos; a identidade da receita é a mesma nos três lançamentos.
"""

import pytest
from django.contrib.auth import get_user_model

from apps.fiscal import receita as servico
from apps.fiscal.models import MercadoReceita, ReceitaInformada
from apps.fiscal.tests.test_dl074_suporte import ORIGEM_OUTRAS
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

INTERNO = MercadoReceita.INTERNO


@pytest.fixture
def gestor_b(escritorio_b):
    usuario = get_user_model().objects.create_user(
        username="gestor-b-dl074-r2",
        email="gestor-b-dl074-r2@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    return usuario


def _lancar_igual(empresa, usuario):
    # Mesma identidade em todas as chamadas: mês, mercado, valor, origem e documento.
    return servico.lancar_receita_informada(
        empresa,
        2026,
        5,
        INTERNO,
        "1500.00",
        ORIGEM_OUTRAS,
        "Motivo sintético.",
        "NF 123 sintética",
        usuario,
        situacao_iss="proprio_municipio",
    )


def test_r2_receita_igual_em_outra_empresa_ou_outro_escritorio_nao_bloqueia(
    empresa_a, empresa_a2, empresa_b, usuario_gestor_a, gestor_b
):
    _lancar_igual(empresa_a, usuario_gestor_a)
    _lancar_igual(empresa_a2, usuario_gestor_a)
    _lancar_igual(empresa_b, gestor_b)

    assert ReceitaInformada.objects.count() == 3
    assert set(ReceitaInformada.objects.values_list("empresa_id", flat=True)) == {
        empresa_a.pk,
        empresa_a2.pk,
        empresa_b.pk,
    }


def test_r2_receita_igual_na_mesma_empresa_continua_bloqueada(empresa_a, usuario_gestor_a):
    # Controle: o isolamento não pode ter desligado a checagem dentro da própria empresa.
    _lancar_igual(empresa_a, usuario_gestor_a)

    with pytest.raises(servico.ReceitaErro, match="Já existe receita igual"):
        _lancar_igual(empresa_a, usuario_gestor_a)

    assert ReceitaInformada.objects.count() == 1
