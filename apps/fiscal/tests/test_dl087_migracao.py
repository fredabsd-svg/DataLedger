"""DL-087 (frente A), migração aditiva e reversível. A reversão recusa, sem alterar nada, enquanto
houver regra de classificação ou origem gravada. Os passos da migração estão no próprio arquivo.

A ida, a volta e a ida foram executadas com `manage.py migrate` (saída no relatório da entrega);
aqui ficam as guardas, com o registro real de migrações.
"""

import importlib
from datetime import date

import pytest
from django.apps import apps as registro_de_apps

from apps.fiscal import classificacao as cl
from apps.fiscal.models import OrigemNaturezaItemNFe, RegraClassificacaoNFe
from apps.fiscal.tests.suporte_dl081 import usuario_com_papel
from apps.tenancy.models import Papel

pytestmark = pytest.mark.django_db

M19 = importlib.import_module("apps.fiscal.migrations.0019_dl087_regra_de_classificacao_nfe")
M20 = importlib.import_module("apps.fiscal.migrations.0020_dl087_origem_da_natureza_confirmada")


def test_guarda_da_0019_passa_sem_regra_e_recusa_com_regra(escritorio_a):
    M19._recusar_reversao_com_regras(registro_de_apps, None)  # sem regra: passa
    gestor = usuario_com_papel(escritorio_a, Papel.GESTOR, "gestor-migracao-dl087")
    cl.criar_regra(
        escritorio=escritorio_a,
        empresa=None,
        dados=cl.DadosDaRegra(
            tipo="saida_propria",
            cfop="5102",
            natureza="revenda",
            vigencia_inicio=date(2026, 1, 1),
        ),
        usuario=gestor,
    )
    with pytest.raises(
        RuntimeError, match="Reversão da DL-087 recusada, sem alterar nada: 1 regra"
    ):
        M19._recusar_reversao_com_regras(registro_de_apps, None)
    assert RegraClassificacaoNFe.objects.count() == 1


def test_guarda_da_0020_passa_sem_origem_gravada(escritorio_a):
    """Sem origem gravada, a guarda da reversão passa (A9). Com origem, recusa: ver o teste de
    `test_dl087_correcao_rodada1.py`, que grava a origem por uma confirmação real."""
    M20._recusar_reversao_com_origens(registro_de_apps, None)
    assert OrigemNaturezaItemNFe.objects.count() == 0


def test_a_guarda_e_a_ultima_operacao_de_cada_migracao():
    """Reversão roda as operações de trás para frente: as guardas, por serem as últimas, rodam
    PRIMEIRO. Na 0020 a da origem (A9) é a última, e a da regra (0019) vem logo antes."""
    assert M19.Migration.operations[-1].reverse_code is M19._recusar_reversao_com_regras
    assert M20.Migration.operations[-1].reverse_code is M20._recusar_reversao_com_origens
    assert M20.Migration.operations[-2].reverse_code is M19._recusar_reversao_com_regras
