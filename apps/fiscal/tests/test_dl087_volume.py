"""DL-087 (frente A), critério 7: o volume do lote com 50 regras cadastradas não piora mais de 10%.

Roda SÓ com `DL085_MEDIR_VOLUME=1` (são minutos, como o da DL-085). Reusa a medida da DL-085
(`test_dl085_volume.test_medida_de_volume_do_mes_de_nfce`, sem alterar o arquivo dela) e a executa
depois de cadastrar CINQUENTA regras do escritório. As regras usam CFOP que NÃO aparecem nas notas
da medida: é o pior caso de varredura (cada item é comparado com as 50), e nenhuma nota muda de
sugestão. Os tempos saem no `pytest -s`, junto com os da medida sem regras.
"""

import os
from datetime import date

import pytest

from apps.fiscal import cfop as tabela
from apps.fiscal import classificacao as cl
from apps.fiscal.models import RegraClassificacaoNFe
from apps.fiscal.tests import test_dl085_volume as base
from apps.fiscal.tests.suporte_dl085 import usuario_gestor

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        os.environ.get("DL085_MEDIR_VOLUME") != "1",
        reason="medida de volume: defina DL085_MEDIR_VOLUME=1",
    ),
]

CINQUENTA = 50
# A medida só usa estes dois CFOP. Os cinquenta primeiros, em ordem, da tabela oficial que começam
# com 5 ou 6, sem eles, não aparecem nas notas da medida.
_CFOP_DA_MEDIDA = ("5656", "5102")


def _cinquenta_cfop_que_nao_casam() -> list[str]:
    # A tabela guarda o CFOP com ponto ("5.656"): normaliza antes de comparar.
    sem_ponto = [codigo.replace(".", "") for codigo in sorted(tabela._tabela())]
    candidatos = [
        codigo for codigo in sem_ponto if codigo[0] in "56" and codigo not in _CFOP_DA_MEDIDA
    ]
    return candidatos[:CINQUENTA]


def test_volume_com_cinquenta_regras_do_escritorio(escritorio_a):
    gestor = usuario_gestor(escritorio_a, "gestor-regras-volume-dl087")
    codigos = _cinquenta_cfop_que_nao_casam()
    assert len(codigos) == CINQUENTA, "a tabela oficial precisa ter cinquenta CFOP candidatos"
    for codigo in codigos:
        cl.criar_regra(
            escritorio=escritorio_a,
            empresa=None,
            dados=cl.DadosDaRegra(
                tipo="saida_propria",
                cfop=codigo,
                natureza="revenda",
                vigencia_inicio=date(2026, 1, 1),
            ),
            usuario=gestor,
        )
    assert RegraClassificacaoNFe.objects.count() == CINQUENTA
    print(f"\nDL-087 volume: {CINQUENTA} regras do escritório cadastradas antes da medida")
    base.test_medida_de_volume_do_mes_de_nfce(escritorio_a)
