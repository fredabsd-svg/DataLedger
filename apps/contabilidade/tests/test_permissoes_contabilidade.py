"""DL-017, fase A, critério 1: a regra de quem lê contabilidade existe em um
só lugar (`apps.contabilidade.permissoes.papel_pode_ler_contabilidade`), e
API e tela (fase B, ainda não escrita) decidem igual porque as duas chamam a
MESMA função — não duas cópias da mesma lista de papéis.

Este arquivo cobre o lado da FUNÇÃO, direto, sem DRF nem HTTP. O lado da API
já tem teste equivalente, parametrizado com os MESMOS seis casos, em
`test_dl015_saidas_com_periodo.py::test_leitura_das_quatro_rotas_de_
contabilidade_depende_do_papel` — deliberadamente hoje em outro arquivo
(nasceu antes desta etapa, da rodada 2 da auditoria da DL-015). Os dois
testes são INDEPENDENTES (nenhum chama o outro, nenhum deriva o resultado
esperado a partir da implementação): cada um hardcoda a expectativa de
negócio (CLIENTE não lê; os cinco papéis operacionais leem). É esse
hardcode, dos DOIS lados, que faz uma mutação em `permissoes.py` — por
exemplo trocar `Papel.CLIENTE` para dentro da tupla, ou inverter a
comparação `in` da função — derrubar os dois testes ao mesmo tempo: o daqui
porque o resultado direto muda, e o da API porque a rota que antes recusava
o CLIENTE passa a devolver 200. Nenhum dos dois "sabe" da mutação de
antemão; os dois só descrevem o que a regra de negócio exige.

A fase B (`especialista-frontend`) usa exatamente esta mesma função — ver o
docstring de `apps/contabilidade/permissoes.py` para o contrato que a view
web precisa seguir.
"""

import pytest

from apps.contabilidade.permissoes import (
    PAPEIS_QUE_LEEM_CONTABILIDADE,
    papel_pode_ler_contabilidade,
)
from apps.tenancy.models import Papel

# Sem banco de dados: a função não consulta nada, só compara o papel contra
# a tupla. Nenhum destes testes precisa de `pytest.mark.django_db`.


@pytest.mark.parametrize(
    "papel,esperado",
    [
        (Papel.ADMINISTRADOR, True),
        (Papel.GESTOR, True),
        (Papel.ANALISTA, True),
        (Papel.FINANCEIRO, True),
        (Papel.PARALEGAL, True),
        (Papel.CLIENTE, False),  # sigilo de cliente contra cliente (DE-020 §4)
        (None, False),  # sem papel resolvido (ex.: sem escritório ativo)
    ],
)
def test_papel_pode_ler_contabilidade_decide_por_papel(papel, esperado):
    assert papel_pode_ler_contabilidade(papel) is esperado


def test_todo_papel_do_enum_esta_coberto_pela_tupla_ou_e_o_cliente():
    """Nenhum papel novo pode entrar no enum `Papel` sem que este módulo
    declare explicitamente se ele lê contabilidade ou não — evita que um
    papel futuro (ex.: um "estagiário") caia, por omissão, do lado errado
    sem ningum decidir isso de propósito. Hoje o único papel que NÃO lê é
    o CLIENTE; qualquer outro precisa estar na tupla.
    """
    papeis_cobertos = set(PAPEIS_QUE_LEEM_CONTABILIDADE) | {Papel.CLIENTE}
    assert set(Papel.values) == {papel.value for papel in papeis_cobertos}


def test_tupla_compartilhada_nao_duplica_papel():
    # Guarda simples de integridade dos dados desta etapa: cada papel
    # aparece no máximo uma vez na tupla que a função consulta.
    assert len(PAPEIS_QUE_LEEM_CONTABILIDADE) == len(set(PAPEIS_QUE_LEEM_CONTABILIDADE))
