"""DL-087 (frente A), critério 7: volume com CINQUENTA regras nos CFOP das notas.

Correção da rodada 1 (A6). A versão anterior chamava de "pior caso" as regras em CFOP que NÃO
aparecem nas notas, e esse era o MELHOR caso (o índice por CFOP as descarta de início). Aqui as
cinquenta regras ficam nos CFOP que as notas usam (5656 e 5102), com NCM exato que NÃO casa com
nenhuma nota: o índice por CFOP sozinho não bastava, e o índice por NCM é que evita a comparação.

Não é medido o caso em que TODA regra do CFOP casa o item (regra sem NCM, com vigências que não se
cruzam): nesse caso o índice não reduz nada, e é o pior caso real. Fica declarado no relatório.

Medidas na mesma execução e máquina, com a mesma função: prévia do lote, fila "a classificar",
prévia de impacto (uma regra), prévia da tela (`_previas_da_regra`, com as variantes) e cada parte
da confirmação. As prévias rodam três vezes (média e maior no `pytest -s`); a confirmação, uma vez
por parte.

Variáveis de ambiente (roda SÓ com `DL085_MEDIR_VOLUME=1`, são minutos):
  DL087_COM_REGRAS=0 | 1  sem regra (0) ou cinquenta regras nos CFOP das notas (1, padrão).
  DL085_NOTAS            notas do mês (padrão 10.000, como na DL-085).
"""

import os
import statistics
import time
from datetime import date

import pytest

from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import classificacao as cl
from apps.fiscal import escrituracao_nfe_lote as lote
from apps.fiscal import presumido as presumido_servico
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import views_web
from apps.fiscal.tests import test_dl085_volume as base
from apps.fiscal.tests.suporte_dl085 import usuario_gestor
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_EMITENTE_A

pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(
        os.environ.get("DL085_MEDIR_VOLUME") != "1",
        reason="medida de volume: defina DL085_MEDIR_VOLUME=1",
    ),
]

ANO, MES = 2026, 3
NOTAS = int(os.environ.get("DL085_NOTAS", "10000"))
TAMANHO_ENVIO = 2000
COM_REGRAS = os.environ.get("DL087_COM_REGRAS", "1") == "1"
CINQUENTA = 50
# CFOP das notas da medida (5656 combustível, 5102 revenda; ver test_dl085_volume).
CFOP_DAS_NOTAS = ("5656", "5102")
VEZES = 3


def _cinquenta_regras_que_nao_casam(escritorio, usuario) -> None:
    """Cinquenta regras de escritório: 25 em cada CFOP das notas, NCM exato que nenhuma nota tem."""
    for numero in range(CINQUENTA):
        cl.criar_regra(
            escritorio=escritorio,
            empresa=None,
            dados=cl.DadosDaRegra(
                tipo="saida_propria",
                cfop=CFOP_DAS_NOTAS[numero % 2],
                natureza="revenda",
                vigencia_inicio=date(2026, 1, 1),
                ncm=f"9999{numero:04d}",
                ncm_modo="exato",
            ),
            usuario=usuario,
        )


def _medir(rotulo: str, funcao):
    """Roda `funcao` três vezes; imprime média e maior. Devolve o resultado da última."""
    tempos = []
    resultado = None
    for _ in range(VEZES):
        inicio = time.perf_counter()
        resultado = funcao()
        tempos.append(time.perf_counter() - inicio)
    print(
        f"[DL-087 volume] {rotulo}: média {statistics.mean(tempos):.3f} s, "
        f"maior {max(tempos):.3f} s ({VEZES} vezes)"
    )
    return resultado


def test_volume_do_mes_com_e_sem_regra_nos_cfop_das_notas(escritorio_a):
    usuario = usuario_gestor(escritorio_a, "gestor-volume-dl087")
    empresa = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Posto Volume DL087 Ltda", cnpj=CNPJ_EMITENTE_A
    )
    HistoricoRegimeTributario.objects.create(
        empresa=empresa,
        regime=RegimeTributario.LUCRO_PRESUMIDO,
        vigencia_inicio=date(2026, 1, 1),
    )
    presumido_servico.definir_criterio(empresa, 2026, "competencia", usuario)
    presumido_servico.criar_atividade(
        empresa,
        {"atividade": tab.SERVICOS_GERAIS, "inicio": date(2026, 1, 1), "padrao": True},
        usuario,
    )
    # Recepção em envios de 2.000, como a DL-085 (fluxo real).
    for inicio in range(1, NOTAS + 1, TAMANHO_ENVIO):
        quantidade = min(TAMANHO_ENVIO, NOTAS - inicio + 1)
        base._envio(escritorio_a, usuario, inicio, quantidade)

    rotulo = "com 50 regras nos CFOP das notas" if COM_REGRAS else "sem regra"
    if COM_REGRAS:
        _cinquenta_regras_que_nao_casam(escritorio_a, usuario)
    # Leitura em partes, como a tela faz antes da prévia (fora das medidas).
    while True:
        leitura = lote.ler_notas_do_mes(empresa, ANO, MES, limite=lote.LIMITE_MAXIMO_DA_LEITURA)
        assert not leitura.falhas_nesta_chamada, leitura.falhas_nesta_chamada
        if leitura.terminou:
            break

    previa = _medir(f"{rotulo} | prévia do lote", lambda: lote.previa_do_lote(empresa, ANO, MES))
    _medir(f"{rotulo} | fila a classificar", lambda: cl.fila_a_classificar(empresa, ANO, MES))
    regra_da_tela = cl.DadosDaRegra(
        tipo="saida_propria",
        cfop="5656",
        natureza="revenda",
        vigencia_inicio=date(ANO, MES, 1),
        ncm="27101259",
        ncm_modo="exato",
    )
    _medir(
        f"{rotulo} | prévia de impacto (1 regra)",
        lambda: cl.previa_de_impacto(empresa, ANO, MES, regra_da_tela, "empresa"),
    )
    _medir(
        f"{rotulo} | prévia da tela (com variantes)",
        lambda: views_web._previas_da_regra(empresa, ANO, MES, regra_da_tela, "empresa"),
    )

    # Confirmação: a primeira parte (com a prévia) e as seguintes, uma a uma, com a mesma escolha
    # de limite da DL-085. Roda por último, porque efetiva o mês.
    tempos_partes = []
    inicio = time.perf_counter()
    progresso = lote.confirmar_lote(
        empresa, ANO, MES, previa.assinatura, {}, usuario, limite=lote.LIMITE_PADRAO_DA_PARTE
    )
    tempos_partes.append(time.perf_counter() - inicio)
    while not progresso.terminou:
        inicio = time.perf_counter()
        progresso = lote.confirmar_lote(
            empresa,
            None,
            None,
            None,
            None,
            usuario,
            limite=lote.LIMITE_PADRAO_DA_PARTE,
            lote_id=progresso.lote_id,
        )
        tempos_partes.append(time.perf_counter() - inicio)
    assert progresso.falhas_total == 0
    print(
        f"[DL-087 volume] {rotulo} | confirmação: {len(tempos_partes)} partes, média "
        f"{statistics.mean(tempos_partes):.3f} s, maior {max(tempos_partes):.3f} s; "
        f"notas {NOTAS}, efetivadas {progresso.efetivadas_total}"
    )
