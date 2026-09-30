"""Fonte ÚNICA de "quem fecha e reabre um período" (RC-102, RC-146).

RC-102 (Fred, 2026-09-20): a competência contábil é fechada, reaberta e
entregue por ADMINISTRADOR ou GESTOR; ANALISTA lança e não fecha. RC-146
(Fred, 2026-09-30): o mês do livro-caixa segue "a mesma regra da
contabilidade". Uma regra confirmada uma vez, portanto, e guardada num lugar
só: a contabilidade (`apps.contabilidade.views.PodeFecharCompetencia`) e o
livro-caixa (`apps.livro_caixa.permissoes.PAPEIS_QUE_FECHAM_MES_CAIXA`)
importam ESTA tupla, sem cada lado manter a sua lista literal — duas listas
iguais hoje divergem no dia em que alguém mudar só uma delas.

Mudar quem fecha período é mudar esta tupla, e só ela. Diferente da matriz de
ESCRITA e de LEITURA (copiada por valor em cada módulo, de propósito — ver
`apps.livro_caixa.permissoes`), aqui o compartilhamento é a própria regra
pedida pelo Fred: fechamento é uma política do escritório, não de um regime
de escrituração.

O módulo só depende de `Papel`: serve a permissões DRF, a telas e a serviços
sem importar nada de nenhum dos dois módulos de negócio.
"""

from apps.tenancy.models import Papel

PAPEIS_QUE_FECHAM_PERIODO = (Papel.ADMINISTRADOR, Papel.GESTOR)
