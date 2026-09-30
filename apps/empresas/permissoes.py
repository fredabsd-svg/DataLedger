"""Fonte única da regra "este papel lê o cadastro de empresas?" (DL-055).

Por que existe: até a DL-055 os GETs de empresa e de estabelecimento exigiam
só `TemEscritorioAtivo`, então um usuário com papel CLIENTE recebia razão
social e CNPJ/CPF de TODAS as empresas do escritório — sigilo de cliente
contra cliente (DE-020 §4), que já valia para a contabilidade e não valia
para a carteira que a contabilidade pendura.

Não há, hoje, vínculo entre um usuário CLIENTE e uma empresa específica
(PE-36). Enquanto não existir, o critério é conservador: o CLIENTE não lê o
cadastro de NENHUMA empresa. Quando o portal do cliente existir, o acesso
restrito à própria empresa entra em etapa própria, e é esta a tupla a mudar.

A tupla é a MESMA de `PAPEIS_QUE_LEEM_CONTABILIDADE`, por REFERÊNCIA e não
por cópia (mesmo padrão de `PAPEIS_QUE_FECHAM_MES_CAIXA` em
`apps.livro_caixa.permissoes`): hoje "quem vê a carteira" e "quem lê a
escrituração" é a mesma decisão da DE-020 §4, e uma segunda lista de papéis
divergiria na primeira alteração. O nome próprio existe para que separá-las,
se um dia a decisão se separar, seja mudar UMA linha aqui.

Lista de PERMITIDOS, não de negados: um papel novo nasce sem ver a carteira
até alguém decidir que deve.
"""

from apps.contabilidade.permissoes import PAPEIS_QUE_LEEM_CONTABILIDADE
from apps.tenancy.permissions import papel_permitido

PAPEIS_QUE_LEEM_CARTEIRA = PAPEIS_QUE_LEEM_CONTABILIDADE


def papel_pode_ler_carteira(papel):
    """`None` (sem papel resolvido) sempre devolve `False`."""
    return papel in PAPEIS_QUE_LEEM_CARTEIRA


# Permissão DRF do mesmo critério, para as rotas da API. Usada em TODA rota
# de empresa/estabelecimento/regime (não só nos GET): para o CLIENTE as
# escritas já eram recusadas por `PodeGerenciarEmpresa`, e aplicar esta
# também a OPTIONS/HEAD fecha o último método seguro. A checagem acontece em
# `initial()`, antes de qualquer `get_object`/`get_empresa`, então o corpo e
# o status do CLIENTE são idênticos para id existente e inexistente.
PodeLerCarteira = papel_permitido(*PAPEIS_QUE_LEEM_CARTEIRA)
PodeLerCarteira.message = "Seu papel não permite consultar o cadastro de empresas."
