"""Fonte única das regras de autorização do módulo Fiscal (DL-010 F1, HI-21).

Molde: `apps.contabilidade.permissoes` (DE-026) — mesma razão de existir:
uma função por decisão, sem depender de `request` nem de Django REST
Framework, para que a API (fora do escopo desta fatia), a tela (etapa 2,
`especialista-frontend`) e qualquer ferramenta de IA futura cheguem à MESMA
decisão chamando a MESMA função — nunca reimplementando uma lista de papéis
em cada porta (é a duplicação que a rodada 2 da auditoria da DL-015
encontrou, aplicada aqui antes de existir).

HI-21 é HIPÓTESE, não regra confirmada pelo Fred: nasce de REUSO da matriz
já confirmada para a contabilidade — não existe matriz fiscal definida
(PE-08 em docs/projeto/requisitos.md). Fica registrada como tal; se o Fred
confirmar outra composição, só as duas tuplas abaixo mudam, em um lugar só.

Autorização é verificada NO SERVIDOR (AGENTS.md §11, RC-17) — nunca só na
interface. `papel` deve vir de `request.papel`, resolvido pelo
`EscritorioAtivoMiddleware` a partir do vínculo do usuário com o escritório
ATIVO — nunca de um campo enviado pelo cliente.
"""

from apps.tenancy.models import Papel

# Recebem (enviam) documentos fiscais os MESMOS papéis que escrituram
# (HI-21) — mesma composição de `apps.contabilidade.permissoes.
# PAPEIS_QUE_ESCREVEM_CONTABILIDADE`, se existir; aqui é uma tupla própria
# porque o módulo Fiscal é independente do Contábil e não deve importar dele
# só para reusar uma lista de papéis.
PAPEIS_QUE_RECEBEM_DOCUMENTOS = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
)

# Consultam documentos fiscais os mesmos papéis que leem a contabilidade:
# todos MENOS o CLIENTE (HI-21) — mesmo critério de
# `apps.contabilidade.permissoes.papel_pode_ler_contabilidade` (DE-026):
# sigilo de cliente contra cliente do mesmo escritório.
PAPEIS_QUE_CONSULTAM_DOCUMENTOS = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
)


def papel_pode_receber_documentos(papel):
    """Este papel pode ENVIAR documentos fiscais para recepção?

    `None` (sem papel — por exemplo, sem escritório ativo resolvido) nunca
    é interpretado como permissão.
    """
    return papel in PAPEIS_QUE_RECEBEM_DOCUMENTOS


def papel_pode_consultar_documentos(papel):
    """Este papel pode CONSULTAR (ler) documentos fiscais já recebidos?"""
    return papel in PAPEIS_QUE_CONSULTAM_DOCUMENTOS


# DL-072 (frente A): quem ESCRITURA e ESTORNA NFS-e prestadas. A composição é
# a MESMA de `apps.contabilidade.views.PodeEscriturar` (medida em 2026-10-08):
# ADMINISTRADOR, GESTOR, ANALISTA e FINANCEIRO. O plano da DL-072 listava só
# os três primeiros entre parênteses; a medição mostrou que a contabilidade
# inclui FINANCEIRO, e a regra "mesmos papéis que escrituram na contabilidade"
# foi mantida. Divergência registrada no relatório da frente A, para o Fred
# confirmar. PARALEGAL e CLIENTE nunca escrituram.
#
# `tests/test_dl072_permissoes.py` compara esta tupla, papel por papel, com a
# permissão DRF da contabilidade — se uma mudar sem a outra, a suíte reprova.
PAPEIS_QUE_ESCRITURAM_FISCAL = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
)


def papel_pode_escriturar_fiscal(papel):
    """Este papel pode efetivar ou estornar escrituração de NFS-e prestada?

    `None` (sem escritório ativo) nunca é permissão. A checagem é feita no
    servidor, pela API (`apps.fiscal.api`), e vale também para qualquer outra
    porta que venha a escriturar.
    """
    return papel in PAPEIS_QUE_ESCRITURAM_FISCAL
