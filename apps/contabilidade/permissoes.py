"""Fonte única da regra "este papel pode ler a contabilidade?" (DE-026).

Contexto (DL-017, fase A, critério 1 do plano): antes desta etapa, a decisão
vivia só em `apps.contabilidade.views.PodeLerContabilidade`, uma classe de
permissão do DRF. A tela da contabilidade (fase B, `especialista-frontend`)
precisa da MESMA decisão, e reimplementá-la — mesmo que "só para a tela" — é
exatamente o defeito que a rodada 2 da auditoria da DL-015 encontrou: a
regra estava escrita em termos de uma LISTA DE ROTAS ("estas quatro rotas
exigem tal permissão"), então uma rota nova ou esquecida (`GET
.../lancamentos/`, `GET .../contas/`) continuava aberta ao papel CLIENTE sem
que ninguém tivesse "mudado a regra" em lugar nenhum — porque a regra nunca
existiu como uma função, só como uma lista espalhada.

Este módulo não depende de Django REST Framework nem de `HttpRequest`: só de
`Papel`. Isso é deliberado — é o que permite a API (uma permissão DRF) e uma
view Django comum (a tela, sem DRF) chegarem à MESMA decisão chamando a
MESMA função, em vez de cada lado ter sua própria cópia da lista de papéis.

Contrato para quem consome:

- API (`apps.contabilidade.views.PodeLerContabilidade`): já integrado nesta
  etapa — a classe de permissão do DRF chama `papel_pode_ler_contabilidade`
  em `has_permission`, sem repetir a lista de papéis.
- Tela (fase B, `apps.contabilidade.views_web`, escrita e integrada em
  `config/urls.py` sob o prefixo `contabilidade/painel/`): antes de
  renderizar qualquer tela de LEITURA de contabilidade (plano de contas,
  Diário, Razão, Balancete, conferência — a tela de LANÇAMENTO, que também
  escreve, usa a regra de `PodeEscriturar` em `views.py`, fora do escopo
  deste módulo), a view web passa `request.papel` a
  `papel_pode_ler_contabilidade`. Se `False`, responde com o template de
  falta de permissão
  (critério 3 do plano DL-017) — nunca texto cru, nunca 500, nunca a tela
  renderizada sem checar antes. `request.papel` vem do
  `EscritorioAtivoMiddleware`, resolvido a partir do vínculo do usuário com
  o escritório ATIVO — nunca de um campo enviado pelo cliente (mesma fonte
  que `apps.tenancy.permissions.papel_permitido` já usa na API; a tela usa a
  mesma fonte, nunca reconsulta o vínculo por fora do middleware).

Critério de aceite (plano DL-017, critério 1): mutar `papel_pode_ler_
contabilidade` (ou a tupla `PAPEIS_QUE_LEEM_CONTABILIDADE` da qual ela
depende) tem que derrubar teste tanto do lado da API quanto de um teste
direto desta função — prova de que não existe uma segunda cópia da decisão
em lugar nenhum. Ver `apps/contabilidade/tests/test_permissoes_contabilidade.py`.
"""

from apps.tenancy.models import Papel

# Papéis autorizados a LER contabilidade: Diário, Razão, Balancete,
# conferência, plano de contas (GET) e escrituração "crua" (GET
# .../lancamentos/, sem período). Decisão do arquiteto-senior (DE-020 §4,
# corrigida pela rodada 2 da auditoria da DL-015): o papel CLIENTE NÃO lê
# contabilidade nenhuma — antes da correção, qualquer usuário com vínculo
# CLIENTE no escritório lia o Diário, o Razão e o Balancete completos de
# TODOS os outros clientes do mesmo escritório, o que é sigilo de cliente
# contra cliente, não apenas permissão fina.
#
# Mudar QUEM lê contabilidade é mudar esta tupla, e SÓ esta tupla — nunca
# uma lista de rotas em `views.py`, nunca uma segunda tupla na tela da fase
# B. É a garantia que o teste do critério 1 do plano DL-017 verifica.
PAPEIS_QUE_LEEM_CONTABILIDADE = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
    Papel.ANALISTA,
    Papel.FINANCEIRO,
    Papel.PARALEGAL,
)


def papel_pode_ler_contabilidade(papel):
    """Responde: este papel pode ler a contabilidade deste escritório?

    `papel` é um valor de `apps.tenancy.models.Papel` (ou `None`, quando
    nenhum papel foi resolvido — por exemplo, sem escritório ativo). Não
    recebe `request` nem depende de DRF de propósito: é o que permite à API
    e à tela (fase B) chamarem exatamente a mesma função, sem que nenhuma
    das duas precise conhecer a outra.

    `None` sempre devolve `False` — ausência de papel nunca é interpretada
    como permissão.
    """
    return papel in PAPEIS_QUE_LEEM_CONTABILIDADE


# DL-089 / BL-73: estornar lançamento de ORIGEM AUTOMÁTICA (escrita fiscal, importação, e o
# zeramento do resultado, que tem chave `zeramento:` e origem `manual`) exige permissão própria,
# distinta da de lançar (`PodeEscriturar`: ADMINISTRADOR, GESTOR, ANALISTA e FINANCEIRO). Quem
# digita não deveria, por acidente, desfazer o que o sistema gerou; a regeração (BL-66) também
# conta com isso. Quais lançamentos são "automáticos" é decidido em
# `services.exige_permissao_de_estorno_automatico`; aqui só se decide quem pode.
#
# Papéis: ADMINISTRADOR e GESTOR, a mesma matriz de RC-102 (confirmada pelo Fred em
# 2026-09-20 para fechar, reabrir e entregar competência). Não é a MESMA permissão: é a
# matriz escolhida para esta operação, mantida nesta tupla. Mudar quem estorna automático
# é mudar esta tupla, e só ela. Lançamento manual continua estornável por quem lança.
PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA = (
    Papel.ADMINISTRADOR,
    Papel.GESTOR,
)


def papel_pode_estornar_origem_automatica(papel):
    """Responde: este papel pode estornar lançamento de origem automática?

    Mesma convenção de `papel_pode_ler_contabilidade`: `None` (sem papel resolvido) é
    `False`. Quem aplica a regra é `estornar_lancamento` no SERVIDOR, para todo caminho
    (API, tela, chamada direta de serviço), e não só a view.
    """
    return papel in PAPEIS_QUE_ESTORNAM_ORIGEM_AUTOMATICA
