"""Telas da contabilidade (DL-017, fase B).

DE-026: estas views NUNCA chamam a própria API — chamam os serviços de
`apps.contabilidade.services` diretamente e renderizam HTML no servidor. A
autorização de LEITURA vem de uma função só, compartilhada com a API
(`apps.contabilidade.permissoes.papel_pode_ler_contabilidade` — ver o
docstring daquele módulo para o contrato completo); a autorização de
ESCRITA (criar conta, lançar) reaproveita a MESMA classe de permissão que a
API já usa para escrever (`apps.contabilidade.views.PodeEscriturar`), por
indicação explícita do docstring de `permissoes.py`: não existe uma segunda
lista de papéis "só para a tela" em lugar nenhum deste arquivo.

Cada view revalida a empresa pedida contra `request.escritorio` (o
escritório ATIVO da sessão, resolvido pelo `EscritorioAtivoMiddleware` —
nunca um `empresa_id` cru): uma empresa de outro escritório sempre dá 404,
nunca dado (critério 2 do plano DL-017).

Formatação é apresentação: todo valor monetário permanece `Decimal` até o
último instante, convertido para texto pt-BR só pelas funções `_valor_ptbr`/
`_indicador_natureza` deste módulo — nunca um `float` em ponto nenhum
(AGENTS.md, seção 10; riscos do plano DL-017).
"""

import hashlib
import re
import uuid
from datetime import timedelta
from decimal import Decimal
from functools import wraps

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# BL-217/A1 (auditoria DL-020 rodada 1): cada view de função deste módulo
# DECLARA os métodos HTTP que aceita. Não é decoração cosmética — é o fato do
# objeto que a varredura de contratos lê para saber se a view é superfície de
# escrita. A classificação anterior era TEXTUAL (`"request.method" in fonte`)
# e o auditor a contornou com uma view que grava lendo `json.loads(request.
# body)` sob `@require_POST`: suíte inteira verde, lint limpo, gravação sem
# contrato. Uma view de função alcançável pelo urlconf e SEM esta declaração
# reprova a varredura — não existe mais o caminho "não consegui classificar,
# então não é escrita".
from django.views.decorators.http import require_http_methods, require_safe

from apps.auditoria.services import registrar
from apps.contabilidade.models import (
    GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL,
    TIPO_DA_CLASSIFICACAO_PATRIMONIAL,
    # DL-034: os cinco nomes abaixo (ClassificacaoPatrimonial, GrupoDaLei,
    # GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL, TIPO_DA_CLASSIFICACAO_
    # PATRIMONIAL, TipoConta) servem só a tela do Balanço — ver
    # `_montar_grupos_do_balanco`/`balanco`, mais abaixo. Nenhum é
    # redeclarado: são os MESMOS enums e os MESMOS mapas que `apurar_saldos`
    # (services.py, DL-032/DL-033) já usa para montar `totais_por_grupo`/
    # `totais_por_classificacao` — a tela só precisa deles para saber COMO
    # REPARTIR essas duas chaves em seções impressas (quatro subgrupos do
    # Ativo Não Circulante, título de cada grupo), nunca para recalcular
    # nada que o servidor já apurou.
    ClassificacaoPatrimonial,
    Competencia,
    Conta,
    EstadoCompetencia,
    GrupoDaLei,
    LancamentoContabil,
    NaturezaConta,
    TipoConta,
    TipoPartida,
)
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade

# RC-77 (faixa de data) e RC-79 (teto de partidas) vêm de
# `apps.contabilidade.services` e NÃO são redeclarados aqui — nem a data
# mínima, nem os 30 dias, nem o 200. Declarar o mesmo número em dois
# arquivos é como o estado do projeto divergiu três vezes; e a recusa de
# verdade é do servidor (`criar_lancamento`), não desta tela. O que esta
# tela faz com eles é CONVENIÊNCIA: `min`/`max` no campo de data (DE-031 —
# o seletor nativo continua sendo o do navegador) e o teto de linhas do
# formulário. `data_maxima_lancamento` é FUNÇÃO porque "hoje + N dias" se
# move: congelá-la num import daria um formulário com teto de ontem.
from apps.contabilidade.services import (
    DATA_MINIMA_LANCAMENTO,
    LIMITE_PARTIDAS_POR_LANCAMENTO,
    ChaveIdempotenciaConflitante,
    CompetenciaEncerrada,
    CompetenciaJaEntregue,
    CompetenciaOperacaoInvalida,
    CompetenciaOperacaoRecusada,
    HierarquiaInconsistente,
    LancamentoInvalido,
    apurar_balancete,
    apurar_balanco_patrimonial,
    apurar_razao,
    avaliar_emissao_do_balancete,
    criar_lancamento,
    data_maxima_lancamento,
    encerrar_competencia,
    listar_diario,
    localizar_contas_que_aceitam_lancamento_e_tem_subordinadas,
    localizar_contas_sinteticas_com_movimento,
    localizar_inconsistencias_de_hierarquia,
    localizar_lancamentos_com_data_fora_da_faixa,
    localizar_lotes_desbalanceados,
    marcar_competencia_como_entregue,
    movimento_fora_do_periodo,
    reabrir_competencia,
    rotulo_e_inscricao_da_empresa,
)

# Reaproveitados de apps.contabilidade.views (API), de propósito, para não
# existir uma segunda cópia de nenhuma das regras a seguir:
# - PodeEscriturar: MESMA permissão de escrita que a API usa (indicação
#   explícita do docstring de permissoes.py — a tela de lançamento "usa a
#   regra de PodeEscriturar em views.py").
# - _saldo_absoluto_com_natureza: a conversão saldo-assinado -> (valor
#   absoluto, letra D/C) é uma regra sutil (RC-61: saldo zero não tem lado;
#   o sinal pode inverter a natureza APURADA em relação à CADASTRADA — ver o
#   docstring de origem) — exatamente o tipo de decisão que DE-026 não quer
#   duplicada em dois lugares.
# - TAMANHO_MAXIMO_HISTORICO e LIMITE_MAGNITUDE_VALOR: mesmos limites do
#   modelo (achado 1/4 da auditoria da DL-017, rodada 1) que a API já
#   verifica na fronteira ANTES de gravar — sem eles aqui, o mesmo texto
#   longo demais ou o mesmo valor grande demais que a API recusa com 400
#   chega ao INSERT do Postgres pela tela e vira 500 (`DataError`), porque
#   `criar_lancamento` (services.py) não os verifica: ele confia que quem
#   chama (API ou tela) já filtrou a entrada bruta do usuário.
# - _PADRAO_NIVEL_SIMPLES: MESMO padrão `^[0-9]+$` (não `\d`, que casaria
#   QUALQUER dígito Unicode) que a API usa para validar 'nivel' — achado
#   R2-2 da rodada 2: esta tela tinha uma cópia frouxa (`bruto.isdigit()`)
#   que aceitava dígito índico-arábico/fullwidth em silêncio. Usado só por
#   `_inteiro_de_cliente` abaixo, que preserva a MAGNITUDE de um texto
#   grande demais (ver o docstring dela para o porquê disso importar).
# - PodeFecharCompetencia (DL-016 fatia 1 / DL-031 fatia 2): MESMA permissão
#   (ADMINISTRADOR/GESTOR, RC-102) que a API já usa para fechar/reabrir/
#   entregar competência — reaproveitada aqui pelo mesmo motivo de
#   PodeEscriturar: não existe uma segunda lista de papéis "só para a tela".
from apps.contabilidade.views import (
    _PADRAO_NIVEL_SIMPLES,
    LIMITE_MAGNITUDE_VALOR,
    TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA,
    TAMANHO_MAXIMO_HISTORICO,
    PodeEscriturar,
    PodeFecharCompetencia,
    _saldo_absoluto_com_natureza,
)

# DataInvalida/para_data: o julgador único de "isto é uma DATA de cliente
# válida?" (BL-133, achado A9 da rodada 4). Esta tela tinha uma cópia
# PRÓPRIA (`_PADRAO_DATA_SIMPLES` + `date.fromisoformat` cru) cujo
# comentário original citava `apps.contabilidade.views._PADRAO_DATA_
# SIMPLES` como referência — símbolo que a própria BL-133 REMOVEU ao
# criar este módulo (R5-4/BL-143, rodada 5: a divergência já estava
# impressa no comentário, e três mutantes na gramática de data desta tela
# sobreviviam a 683 testes porque nada a defendia). `inicio`/`fim`
# (`_periodo_do_formulario`) e `data` do lançamento (`lancamento_novo`)
# usam `para_data` agora — a cópia privada não existe mais.
from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal

# IdentificadorInvalido/para_id: o julgador único de "isto é um
# IDENTIFICADOR de banco válido?" (BL-127, achado A2 da rodada 4— e o
# gêmeo achado no mesmo módulo, `EscritorioAtivoView.post`, ao aplicar a
# lição pelo EFEITO em vez de pela linha nomeada, DE-032). `conta_id`
# (`_itens_e_totais`, abaixo) É um identificador de banco — a mesma
# invariante que `para_id` já julga para `apps.tenancy` (BL-127) **e para
# a API de contabilidade** (`apps.contabilidade.views._extrair_itens`,
# R5-3/BL-142, corrigido pelo `desenvolvedor-pleno` na mesma rodada em
# que este comentário foi revisado). BL-146: uma versão ANTERIOR deste
# comentário já afirmava "a API já usa" quando ainda não usava — foi
# exatamente essa frase que impediu de checar. Não editar esta afirmação
# sem rodar `test_comentario_sobre_julgador_partilhado_so_afirma_o_que_e_
# verificavel` (test_dl017_rodada5_frontend.py), que confere o texto
# contra `inspect.getsource(apps.contabilidade.views)` — a mesma classe
# de proteção que esta nota descreve, aplicada a si própria. Esta tela
# usa `_identificador_de_cliente` (abaixo), que delega a `para_id`, em
# vez de reimplementar o padrão e o teto de magnitude aqui.
# Isto é DIFERENTE de `_inteiro_de_cliente`: nível de hierarquia e número
# de linhas não são identificadores, são QUANTIDADES onde a regra de
# negócio local precisa ver a magnitude real de um texto grande demais
# para poder recusá-lo com uma mensagem própria (ver R3-1/BL-115 no
# docstring de `_inteiro_de_cliente`) — por isso continuam com o julgador
# PRÓPRIO desta tela, não com o teto genérico de `para_id`.
from apps.core.identificadores import IdentificadorInvalido, para_id

# BL-196/R6-2: a política dos cinco dicionários de uma requisição mora em
# `apps.core.requisicao` — UM lugar, como `dinheiro`, `datas`, `escolhas`,
# `identificadores` e `restricoes`. Esta tela tinha a política escrita à mão
# em `lancamento_novo` (três `if` seguidos) e NADA em `conta_nova`, a 40
# linhas de distância no mesmo arquivo: enviar `conta_pai` como ARQUIVO
# gravava a conta na RAIZ do plano com 302 de sucesso. Aqui ficam só as
# DECLARAÇÕES do que cada tela aceita e a RESPOSTA de tela (re-renderizar o
# formulário com 400 e tudo o que o usuário digitou); o julgamento é do
# módulo.
from apps.core.requisicao import (
    DICIONARIO_ARQUIVO,
    DICIONARIO_CABECALHO,
    DICIONARIO_QUERYSTRING,
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaEmModoLivroCaixa, recusar_se_livro_caixa

# Mesmo teto de NÍVEL que a API aplica em `apps.contabilidade.views.NIVEL_
# MAXIMO` — valor repetido aqui (não importado) porque é só uma guarda de
# boa educação na fronteira HTTP desta tela (nenhum plano de contas real
# chega a esta profundidade), não uma regra de negócio contábil.
NIVEL_MAXIMO = 50

# Teto de indentação VISUAL do Plano de Contas e do Balancete (achado 6 da
# auditoria da DL-017, rodada 1): a coluna "Nível" sempre mostra o número
# REAL, então limitar a indentação a 10 níveis não esconde informação —
# nenhum plano de contas real chega lá (ver
# docs/projeto/mapa-funcional-contabil.md). Usada para escolher a classe
# CSS "nivel-N" (static/css/base.css), NUNCA um atributo `style` inline:
# o defeito original era exatamente `(nivel - 1) * 1.25`, um `float` que o
# `LANGUAGE_CODE = "pt-br"` localizava para `padding-left: 1,25rem` — CSS
# inválido, sem indentação nenhuma em nenhum nível, e sem nenhum teste ou
# erro acusando (AGENTS.md §10: nunca `float`, inclusive onde o número não
# é dinheiro).
NIVEL_INDENTACAO_MAXIMA = 10

LINHAS_INICIAIS_LANCAMENTO = 4

# RC-79/BL-207 — teto de partidas por lançamento, confirmado pelo Fred em
# 2026-09-15: **200**, com recusa explícita e NUNCA truncamento. O número
# não mora aqui: é `LIMITE_PARTIDAS_POR_LANCAMENTO`, de
# `apps.contabilidade.services`, que é quem recusa de verdade — para a tela
# e para a API ao mesmo tempo. Esta constante continua existindo com nome
# próprio porque o que ela significa NESTE arquivo é "quantas linhas o
# formulário oferece e re-exibe no máximo", e é assim que os comentários de
# R2-3/R3-2/R3-9 abaixo se referem a ela; o VALOR é um só.
LINHAS_MAXIMAS_LANCAMENTO = LIMITE_PARTIDAS_POR_LANCAMENTO


# ---------------------------------------------------------------------------
# Formatação de apresentação (critérios 4 e 5) — nunca usada para cálculo.
# ---------------------------------------------------------------------------


def _milhar_ptbr(parte_inteira):
    """Insere '.' a cada três dígitos na parte inteira (texto), preservando
    o sinal. Opera sobre STRING, não sobre número — evita qualquer resíduo
    de ponto flutuante ou dependência de locale do interpretador.
    """
    negativo = parte_inteira.startswith("-")
    digitos = parte_inteira[1:] if negativo else parte_inteira
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    resultado = ".".join(grupos)
    return f"-{resultado}" if negativo else resultado


def _valor_ptbr(valor):
    """Formata um Decimal monetário em pt-BR: '.' de milhar, ',' decimal,
    sempre duas casas (critério 4: `1234567.89` -> `1.234.567,89`).

    `Decimal(valor).quantize(Decimal("0.01"))` antes de qualquer formatação
    (mesmo motivo do `_como_moeda` de apps.contabilidade.views: SQLite, usado
    em desenvolvimento local, não preserva a escala de um DecimalField em
    agregações `Sum` como o PostgreSQL faz).

    Não usa o filtro `intcomma` do Django: `django.contrib.humanize` não
    está em INSTALLED_APPS, e esta etapa não tem permissão para alterar
    `config/settings.py` (arquivo do arquiteto-senior). Também não usa uma
    template tag própria, pelo mesmo motivo que impede isto em
    `apps.empresas.views._mascara_cnpj`: nenhuma permissão, nesta etapa,
    para criar `apps/contabilidade/templatetags/`. Formatação pura de
    apresentação — o valor segue `Decimal` até aqui.
    """
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    texto = str(quantizado)
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    parte_inteira, parte_decimal = texto.split(".")
    resultado = f"{_milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if negativo else resultado


def _indicador_natureza(letra):
    """Empacota a letra D/C (RC-61) com o texto por extenso, para o
    template anunciar "D (devedor)"/"C (credor)" — nunca só a letra, e
    nunca só cor (critério 14). `None` quando o saldo é zero: RC-61 diz que
    zero não tem lado, e não existe letra "certa" para inventar aqui.
    """
    if letra is None:
        return None
    return {"letra": letra, "extenso": "devedor" if letra == "D" else "credor"}


# ---------------------------------------------------------------------------
# Isolamento e permissão (critérios 1, 2 e 3)
# ---------------------------------------------------------------------------


def _empresa_do_escritorio_ativo(request, empresa_id):
    """Resolve a empresa da URL, sempre restrita ao escritório ATIVO da
    sessão (critério 2) — nunca por um `empresa_id` cru. Mesma regra de
    isolamento de `apps.empresas.mixins.EmpresaEscopadaMixin` (já usada
    pela API): uma empresa de outro escritório dá 404, não 403 — não
    confirma nem a existência do registro para quem não tem acesso.

    DL-038 (R5): memorizada por REQUISIÇÃO (não entre requisições — o cache
    vive só no objeto `request`, que é novo a cada chamada). Desde que o
    decorador `_sem_contabilidade_para_livro_caixa` passou a resolver a
    empresa ANTES da view (para recusar modo livro-caixa), cada view voltou
    a resolvê-la de novo no próprio corpo — sem memoizar, isso soma uma
    consulta a mais por requisição e estourava o teto de consultas da
    DL-015/DL-019 (`test_dl019_razao_reaproveita_ids_contas.py`). Só
    memoiza o resultado feliz: se `get_object_or_404` estourar Http404,
    nada fica em cache e a próxima chamada tenta de novo (mesmo
    comportamento de antes, sem mascarar erro).
    """
    cache = getattr(request, "_dl038_cache_empresa_do_escritorio_ativo", None)
    if cache is None:
        cache = {}
        request._dl038_cache_empresa_do_escritorio_ativo = cache
    if empresa_id not in cache:
        cache[empresa_id] = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)
    return cache[empresa_id]


def _resposta_sem_permissao(request, mensagem):
    # Critério 3: template próprio, com explicação e caminho de volta —
    # nunca texto cru, nunca 500. Reaproveita o MESMO template que
    # apps.empresas já usa (templates/erros/sem_permissao.html, da DL-009).
    return render(request, "erros/sem_permissao.html", {"mensagem": mensagem}, status=403)


def _resposta_sem_escritorio(request):
    # Reaproveita o mesmo template de apps.empresas (mesma situação: sem
    # escritório ativo não há como saber de qual contabilidade se fala).
    return render(request, "empresas/sem_escritorio.html")


def _sem_contabilidade_para_livro_caixa(view_func):
    """Decorador aplicado a TODA view de tela da contabilidade que recebe
    `empresa_id` (DL-038, R5/DE-075): recusa com a MESMA mensagem e a MESMA
    regra da API quando a empresa resolvida está em modo `livro_caixa` — a
    contabilidade por partidas dobradas não está disponível para ela.

    A regra em si mora só em `apps.empresas.services.recusar_se_livro_caixa`
    (fonte única, R5); este decorador apenas chama essa função depois de
    resolver a empresa pelo MESMO caminho que já garante o isolamento por
    escritório (`_empresa_do_escritorio_ativo`), e reaproveita o MESMO
    template de "sem permissão" (403) que as outras recusas desta tela usam
    — nunca 500, nunca uma segunda cópia da mensagem.

    O lado API equivalente é `apps.contabilidade.views.
    EmpresaEscopadaContabilMixin.get_empresa` — as duas pontas chamam a
    mesma função de serviço, então a mensagem nunca diverge entre tela e
    API. A prova de que TODA view desta tela com `empresa_id` está coberta
    (varredura DERIVADA das rotas registradas, não lista escrita à mão) é
    `apps/contabilidade/tests/test_dl038_recusa_livro_caixa.py` — nome
    corrigido nesta etapa (DL-038, etapa 2): a docstring citava
    `apps/core/tests/test_dl038_recusa_contabilidade_livro_caixa.py`, um
    arquivo que nunca existiu nesse caminho; o teste real sempre morou em
    `apps/contabilidade/tests/`, app a que a varredura pertence.
    """

    @wraps(view_func)
    def _view(request, empresa_id, *args, **kwargs):
        empresa = _empresa_do_escritorio_ativo(request, empresa_id)
        try:
            recusar_se_livro_caixa(empresa)
        except EmpresaEmModoLivroCaixa as exc:
            return _resposta_sem_permissao(request, exc.mensagem)
        return view_func(request, empresa_id, *args, **kwargs)

    return _view


def _pode_ler(request):
    return papel_pode_ler_contabilidade(getattr(request, "papel", None))


def _pode_escriturar(request):
    return PodeEscriturar().has_permission(request, None)


# ---------------------------------------------------------------------------
# Período e nível (critérios 7 e 9)
# ---------------------------------------------------------------------------


def _ultimo_dia_do_mes(referencia):
    proximo_mes = referencia.replace(day=28) + timedelta(days=4)
    return proximo_mes - timedelta(days=proximo_mes.day)


def _periodo_do_formulario(request):
    """Lê e valida 'inicio'/'fim' da querystring das três saídas com
    período (Diário, Razão, Balancete — critério 9).

    Ausência dos DOIS parâmetros (primeira visita à tela) usa o MÊS
    CORRENTE como valor inicial sugerido — diferente da API (DE-016), que
    RECUSA ausência: aqui é a TELA escolhendo um padrão por conveniência de
    quem vai usá-la todo dia, nunca o motor de cálculo. O padrão só é
    aplicado quando NADA foi enviado; um período enviado e malformado
    nunca "cai" no padrão silenciosamente — é reportado como erro.

    Devolve (inicio, fim, mensagem_de_erro). `mensagem_de_erro` é `None`
    quando o período é válido (default ou informado); do contrário, os dois
    primeiros valores vêm `None` e quem chama não deve apurar nada.
    """
    bruto_inicio = request.GET.get("inicio", "").strip()
    bruto_fim = request.GET.get("fim", "").strip()

    if not bruto_inicio and not bruto_fim:
        hoje = timezone.localdate()
        return hoje.replace(day=1), _ultimo_dia_do_mes(hoje), None

    if not bruto_inicio or not bruto_fim:
        return None, None, "Informe as duas datas do período (início e fim)."

    # R5-4/BL-143: `para_data` (`apps.core.datas`) é o ÚNICO julgador de
    # texto-de-cliente-para-data deste repositório (BL-133) — a cópia
    # PRÓPRIA que existia aqui (`_PADRAO_DATA_SIMPLES` + `date.
    # fromisoformat` cru) divergia da API sem que nenhum teste acusasse
    # (MX4/MX9/MX10, rodada 5): a mesma gramática, reimplementada, é
    # exatamente o que a DE-026 existe para impedir.
    try:
        inicio = para_data(bruto_inicio)
        fim = para_data(bruto_fim)
    except DataInvalida:
        return (
            None,
            None,
            "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD).",
        )

    if inicio > fim:
        return None, None, "A data de início não pode ser posterior à data de fim."

    return inicio, fim, None


def _inteiro_de_cliente(texto):
    """Converte `texto` — entrada de CLIENTE — para `int`, ou devolve
    `None` se não for um inteiro ASCII simples. Nunca lança exceção, nunca
    reinterpreta em silêncio.

    Uso: QUANTIDADE de negócio (nível de hierarquia, número de linhas do
    lançamento) — nunca identificador de banco (para isso, ver
    `_identificador_de_cliente`, abaixo). A distinção importa porque uma
    quantidade absurdamente grande, mas ainda assim CONVERSÍVEL para
    `int` pelo próprio Python, precisa chegar como o `int` real na regra
    de negócio local, para que ELA decida — com a magnitude visível — se
    recusa e com que mensagem (R3-1/BL-115, abaixo). Um identificador não
    tem essa necessidade: qualquer coisa fora de um teto pequeno e fixo
    (19 dígitos, o maior `BigAutoField`) já é inválida por definição, não
    importa o valor exato.

    R2-2 (rodada 2): o guarda de formato não pode ser `isdigit()` sozinho
    — ele é `True` para QUALQUER dígito decimal Unicode, não só ASCII
    (`"٢".isdigit()` é `True`), e o `int()` do Python **aceita e converte**
    esses dígitos em silêncio: `int("７") == 7`, `int("٢") == 2`. Sem o
    guarda, um identificador em dígito Unicode passa por inteiro e é
    reinterpretado como se fosse outro — a mesma classe de reinterpretação
    silenciosa que a DE-029 proíbe para valor monetário, aqui para
    identificador.

    A1/A2 (rodada 4): nada protegia o `int()` seguinte de um texto
    absurdamente longo — `int("9" * 4301)` levanta `ValueError: Exceeds
    the limit (4300 digits) for integer string conversion`, um 500
    alcançável por qualquer POST/URL construído à mão. `nivel` do
    Balancete tinha exatamente esse defeito. `_inteiro_de_cliente` é o
    ÚNICO lugar deste arquivo que converte texto de QUANTIDADE de cliente
    para `int` — usado em TODO ponto onde isso acontece (ver
    `_nivel_do_formulario`, `_indices_de_linha_do_post` e o `num_linhas`
    de `lancamento_novo`), para que a lição não precise ser reaprendida
    campo por campo. Reaproveita `_PADRAO_NIVEL_SIMPLES` (`[0-9]+`,
    importado de `apps.contabilidade.views`) — mesmo padrão que a API já
    usa, não uma segunda cópia.

    R3-1 (rodada 3, BL-115): é exatamente esta preservação de magnitude
    que permite `lancamento_novo` recusar `num_linhas` absurdo com uma
    mensagem de NEGÓCIO ("aceita no máximo N partidas"), em vez de tratar
    um texto de 4000 dígitos como se fosse malformado e cair no padrão
    silenciosamente — só o que realmente estoura o limite de CONVERSÃO do
    interpretador (`sys.int_max_str_digits`) vira `None` aqui; o resto,
    por maior que seja, chega como `int` de verdade para a regra de
    negócio decidir.
    """
    if not texto or not _PADRAO_NIVEL_SIMPLES.fullmatch(texto):
        return None
    try:
        return int(texto)
    except ValueError:
        # Só alcançável por um texto com mais dígitos do que o limite de
        # conversão do próprio Python — o padrão acima já garante só
        # dígitos ASCII 0-9.
        return None


def _identificador_de_cliente(texto):
    """Converte `texto` — entrada de CLIENTE que deveria ser um
    IDENTIFICADOR DE BANCO (ex.: `conta_id`) — usando o julgador
    partilhado `para_id` (`apps.core.identificadores`), ou devolve `None`
    se não for um identificador válido. Nunca lança exceção.

    BL-127/A2 (rodada 4): esta tela tinha uma cópia PRÓPRIA da mesma
    invariante que `apps.core.identificadores.para_id` já julga para a
    API e para `apps.tenancy` — duas implementações da mesma regra
    divergem assim que uma for corrigida sem a outra (DE-026/DE-030).
    Delegar aqui, em vez de reimplementar o padrão e o teto de magnitude
    (19 dígitos, o maior `BigAutoField`), fecha essa divergência na raiz.

    Diferente de `_inteiro_de_cliente` (ver o docstring dela): um
    identificador de banco nunca precisa de mais de 19 dígitos, então não
    há necessidade de preservar a magnitude de um texto maior do que isso
    — é inválido de qualquer forma, e `conta_id` inválido sempre vira a
    MESMA mensagem ("conta inválida"), não importa se o texto era curto
    demais, tinha dígito Unicode, ou passava de 19 dígitos.
    """
    if not texto:
        return None
    try:
        return para_id(texto)
    except IdentificadorInvalido:
        return None


def _nivel_do_formulario(request):
    """Lê e valida o parâmetro opcional 'nivel' do Balancete.

    Ausente (ou vazio) devolve `None` — sem recorte de hierarquia, igual à
    API. Presente e malformado vira mensagem de erro, nunca um 500. A
    conversão em si é `_inteiro_de_cliente` (ver o docstring dela para o
    porquê); esta função só acrescenta o intervalo de negócio
    (1..`NIVEL_MAXIMO`) por cima.
    """
    bruto = request.GET.get("nivel", "").strip()
    if not bruto:
        return None, None
    nivel = _inteiro_de_cliente(bruto)
    if nivel is None or nivel < 1 or nivel > NIVEL_MAXIMO:
        return None, f"'Nível' deve ser um número inteiro entre 1 e {NIVEL_MAXIMO}."
    return nivel, None


_CRITERIOS_DE_APURACAO_VALIDOS = frozenset({"todas", "com_movimento"})
_TEXTO_DO_CRITERIO = {
    "todas": "todas as contas",
    "com_movimento": "movimento no período ou saldo anterior diferente de zero",
}


def _criterio_de_apuracao_do_formulario(request):
    """Lê e valida o parâmetro opcional 'criterio_de_apuracao' do Balancete
    (DL-027 Fatia B.2).

    Ausente (ou vazio) devolve `("todas", None)` — o default, que mantém o
    comportamento atual. Presente e fora do conjunto aceito vira mensagem
    de erro, nunca um 500 silencioso nem a aceitação de um valor
    desconhecido que passaria pelo service sem filtro.

    O par devolvido é `(valor_normalizado, mensagem_de_erro)` — mesmo
    contrato de `_nivel_do_formulario` e `_periodo_do_formulario`, para a
    view tratar uniformemente.
    """
    bruto = request.GET.get("criterio_de_apuracao", "").strip()
    if not bruto:
        return "todas", None
    if bruto not in _CRITERIOS_DE_APURACAO_VALIDOS:
        opcoes = ", ".join(sorted(_CRITERIOS_DE_APURACAO_VALIDOS))
        return (
            "todas",
            f"'Critério de apuração' deve ser um destes: {opcoes}.",
        )
    return bruto, None


# ---------------------------------------------------------------------------
# Plano de contas
# ---------------------------------------------------------------------------


def _linhas_hierarquicas(contas):
    """Nível ESTRUTURAL de cada conta (profundidade na árvore de
    `conta_pai`), só para indentar a listagem do Plano de Contas.

    Isto NÃO é a regra de saldo nem de consolidação — essas vivem inteiras
    em `apurar_balancete`/`apurar_razao` (services.py) e não são
    reimplementadas aqui. É só "quantos ancestrais esta conta tem", um
    fato estrutural sem julgamento contábil nenhum.

    Protegido contra ciclo (o mesmo problema que `HierarquiaInconsistente`
    nomeia em services.py): uma conta em ciclo não pode travar esta
    LISTAGEM — a conferência (tela própria, critério da DE-022/BL-64) é
    quem aponta isso; aqui o nível simplesmente degrada para `None`
    (exibido como "—"), sem exceção.
    """
    por_id = {conta.id: conta for conta in contas}
    niveis = {}

    def nivel_de(conta_id, caminho):
        if conta_id in niveis:
            return niveis[conta_id]
        if conta_id in caminho:
            return None
        conta = por_id[conta_id]
        if conta.conta_pai_id is None or conta.conta_pai_id not in por_id:
            resultado = 1
        else:
            pai_nivel = nivel_de(conta.conta_pai_id, caminho | {conta_id})
            resultado = None if pai_nivel is None else pai_nivel + 1
        niveis[conta_id] = resultado
        return resultado

    linhas = []
    for conta in contas:
        nivel = nivel_de(conta.id, frozenset())
        linhas.append(
            {
                "conta": conta,
                "nivel": nivel,
                # Inteiro, nunca `float` (achado 6) — vira a classe CSS
                # "nivel-N" no template, capada em NIVEL_INDENTACAO_MAXIMA.
                # A classe acompanha o NÍVEL: raiz é nível 1 e vira
                # "nivel-1"; só `None` (conta em ciclo, sem nível apurável)
                # cai em "nivel-0". As duas classes têm indentação zero na
                # folha de estilo, por motivos diferentes — a raiz porque é
                # raiz, o ciclo porque não há nível a representar. Nenhuma
                # classe negativa é gerada em nenhum caminho.
                "nivel_classe": min(nivel, NIVEL_INDENTACAO_MAXIMA) if nivel else 0,
            }
        )
    return linhas


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def plano_de_contas(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    contexto = {
        "empresa": empresa,
        "linhas": _linhas_hierarquicas(contas),
        "pode_escriturar": _pode_escriturar(request),
    }
    return render(request, "contabilidade/plano_de_contas.html", contexto)


class ContaCriarForm(forms.ModelForm):
    class Meta:
        model = Conta
        fields = ["codigo", "nome", "tipo", "natureza", "conta_pai", "aceita_lancamento"]

    def __init__(self, *args, empresa, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolamento (mesmo espírito do BL-40 / ContaSerializer.
        # validate_conta_pai na API): a lista de possíveis contas-pai nunca
        # pode incluir conta de OUTRA empresa — listar todas do banco
        # vazaria estrutura de plano de contas de outros clientes do
        # escritório.
        self.fields["conta_pai"].queryset = Conta.objects.filter(empresa=empresa).order_by("codigo")
        self.fields["conta_pai"].required = False


def _codigos_das_contas_mae(codigo):
    """Códigos das contas-mãe IMPLÍCITOS num código de conta, do mais alto
    para o mais próximo: `"4.1.1"` → `("4", "4.1")`.

    RC-80/BL-208. Só vale para plano com separador `"."`: um código sem
    ponto (`"41111"`, que alguns planos usam) não implica mãe nenhuma, e
    inventar hierarquia a partir de fatia de dígitos seria presumir regra
    contábil — o que o AGENTS.md proíbe. Parte vazia (`"4..1"`, `".1"`)
    também devolve vazio: não é hierarquia, é código malformado, e quem
    julga formato de código é o modelo.
    """
    partes = codigo.split(".")
    if len(partes) < 2 or any(not parte for parte in partes):
        return ()
    return tuple(".".join(partes[: i + 1]) for i in range(len(partes) - 1))


def _contas_mae_faltantes(empresa, codigo, conta_pai):
    """Quais contas-mãe implícitas no código NÃO existem no plano desta
    empresa — a consequência estrutural que o RC-80 manda avisar.

    Devolve vazio quando o contador escolheu uma conta-pai explicitamente:
    aí a conta não vai ficar como raiz, e o aviso ("ela ficará como raiz do
    plano") seria falso. Uma consulta só, com `codigo__in` — nunca uma por
    nível.
    """
    if conta_pai is not None:
        return ()
    codigos = _codigos_das_contas_mae(codigo or "")
    if not codigos:
        return ()
    existentes = set(
        Conta.objects.filter(empresa=empresa, codigo__in=codigos).values_list("codigo", flat=True)
    )
    return tuple(codigo_mae for codigo_mae in codigos if codigo_mae not in existentes)


@login_required
@require_http_methods(["GET", "POST"])
@_sem_contabilidade_para_livro_caixa
def conta_nova(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite criar contas nesta empresa.")

    if request.method == "POST":
        # BL-196/R6-2 (rodada 6) — a defesa que existia na tela vizinha
        # (`lancamento_novo`, 40 linhas abaixo) e NÃO existia aqui. Medido
        # pelo auditor: `conta_pai` enviado como ARQUIVO gravava a conta na
        # RAIZ do plano, com 302 de sucesso e sem uma palavra — muda a
        # indentação, o nível e o Balancete por nível. Querystring em POST,
        # campo desconhecido no corpo e `Idempotency-Key` por cabeçalho
        # eram igualmente aceitos e descartados em silêncio.
        #
        # A resposta é o formulário RE-RENDERIZADO com 400 e o que o
        # usuário digitou (mesma política de `_recusa_lancamento_com_erro`,
        # BL-199): recusar sem devolver o que foi digitado troca um defeito
        # por outro.
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CONTA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return render(
                request,
                "contabilidade/conta_form.html",
                {
                    "empresa": empresa,
                    "form": ContaCriarForm(
                        request.POST, instance=Conta(empresa=empresa), empresa=empresa
                    ),
                },
                status=400,
            )

        # A empresa é atribuída à instância ANTES de is_valid() — não é um
        # campo do formulário (o cliente nunca escolhe a empresa; ela vem
        # do escopo da URL, já revalidada acima). É o que permite a
        # Conta.clean() (chamada por full_clean() dentro de is_valid())
        # comparar `conta_pai.empresa_id` contra a empresa CERTA, e não
        # contra `None`.
        instancia = Conta(empresa=empresa)
        form = ContaCriarForm(request.POST, instance=instancia, empresa=empresa)
        if form.is_valid():
            # RC-80/BL-208 — regra confirmada pelo Fred em 2026-09-15:
            # conta sem as contas-mãe **avisa e deixa criar**. Cadastrar
            # `4.1.1` num plano sem `4` e sem `4.1` é legítimo (o contador
            # pode estar montando o plano de baixo para cima), mas tem
            # consequência ESTRUTURAL que ele não pediu: sem conta-pai, a
            # conta entra como RAIZ (nível 1), muda a indentação do Plano
            # de Contas e a linha em que ela aparece no Balancete por
            # nível. Nenhuma consequência estrutural de um cadastro
            # acontece sem o usuário ser avisado — então a primeira
            # tentativa NÃO grava: ela volta a tela com o aviso, os dados
            # preenchidos e um botão que diz o que vai acontecer.
            #
            # 200 e não 400 de propósito: não é erro do usuário, é uma
            # confirmação. E o caminho de correção fica visível ao lado
            # (cadastrar as mães primeiro), que é o que o RC-80 pede
            # quando diz "avisar".
            contas_mae_faltantes = _contas_mae_faltantes(
                empresa, form.cleaned_data.get("codigo"), form.cleaned_data.get("conta_pai")
            )
            if contas_mae_faltantes and request.POST.get("confirmar_conta_sem_conta_mae") != "1":
                messages.warning(
                    request,
                    f"O código “{form.cleaned_data.get('codigo')}” sugere "
                    f"{'a conta-mãe' if len(contas_mae_faltantes) == 1 else 'as contas-mãe'} "
                    f"{', '.join(contas_mae_faltantes)}, que não "
                    f"{'existe' if len(contas_mae_faltantes) == 1 else 'existem'} neste plano. "
                    "Nada foi gravado ainda: confirme abaixo, ou cadastre as contas-mãe "
                    "primeiro.",
                )
                return render(
                    request,
                    "contabilidade/conta_form.html",
                    {
                        "empresa": empresa,
                        "form": form,
                        "contas_mae_faltantes": contas_mae_faltantes,
                        "codigo_pedido": form.cleaned_data.get("codigo"),
                    },
                )
            try:
                # 'empresa' fica FORA da lista de campos do formulário, e
                # por isso o Django exclui a UniqueConstraint
                # "codigo_unico_por_empresa" da checagem de
                # `validate_unique()` dentro de full_clean() (regra do
                # próprio Django: uma constraint composta é pulada se
                # QUALQUER campo dela estiver fora do formulário). Este
                # try/except no INSERT é, por isso, o mecanismo real que
                # detecta duplicidade aqui — não apenas defesa de corrida,
                # como é em apps.empresas (onde o formulário já cobre
                # 'cnpj' inteiro).
                #
                # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do
                # mesmo `transaction.atomic()` que grava a Conta. Antes,
                # qualquer falha no INSERT do `RegistroAuditoria` deixava a
                # Conta gravada e a trilha silenciosamente vazia — o plano
                # de contas dizia uma coisa, a trilha dizia outra. Agora
                # ambos são uma só operação atômica; o `else:` (que só roda
                # em caso de sucesso no `try:`) garante que a auditoria
                # só é tentada se a gravação passou.
                with transaction.atomic():
                    conta = form.save()
                    registrar(acao="conta.criada", objeto=conta, request=request)
            except IntegrityError:
                form.add_error("codigo", "Já existe uma conta com este código nesta empresa.")
            else:
                messages.success(request, f"Conta “{conta}” criada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ContaCriarForm(empresa=empresa)

    return render(request, "contabilidade/conta_form.html", {"empresa": empresa, "form": form})


# ---------------------------------------------------------------------------
# Lançamento (critérios 10 e 11)
# ---------------------------------------------------------------------------


# DE-029 — substitui a cláusula de tradução da DE-027, que estava ERRADA.
# A DE-027 dizia "vírgula decimal vira ponto, separador de milhar sai", mas
# o código só tirava o ponto quando havia vírgula: "1.000" (mil reais em
# pt-BR) era gravado como 1,00 — bloqueador da rodada 2 da auditoria da
# DL-017, na `main` desde o PR #18. A causa raiz não é um `if` esquecido: é
# que "1.000" é AMBÍGUO (mil reais em pt-BR; um real no formato canônico da
# API) e não existe função de tradução bem definida sobre um texto ambíguo
# — corrigir o código para "sempre tirar o ponto" resolveria "1.000" e
# quebraria "10.00" no sentido oposto (dez reais viraria mil).
#
# A saída, como em todo lugar deste módulo monetário, é NUNCA adivinhar:
# uma gramática pt-BR EXPLÍCITA, e texto fora dela é recusado — nunca
# reinterpretado. Dígitos sem separador ALGUM, ou dígitos agrupados de três
# em três por ponto (grupo de milhar bem formado: exatamente três dígitos
# após cada ponto), com centavos opcionais depois da vírgula.
#
# "10.00"/"1.00" são RECUSADOS de propósito: não são grupo de milhar bem
# formado (".00" tem só dois dígitos) — são o formato CANÔNICO DA API
# (ponto como separador DECIMAL), não uma leitura pt-BR válida. Essa
# divergência entre tela e API para textos fora da gramática pt-BR é
# intencional (ver docs/projeto/decisoes.md, DE-029).
#
# `[0-9]`, não `\d`: mesma lição já aplicada em `_PADRAO_NIVEL_SIMPLES`
# (achado R2-2 desta rodada) e em `PADRAO_VALOR_DECIMAL_SIMPLES`
# (`apps.core.dinheiro`, achado R2-7) — `\d` do Python casa QUALQUER
# dígito decimal Unicode ("０１０" fullwidth, "١٢٣" índico-arábico, "๑๐"
# tailandês), não só ASCII 0-9. Sem esta troca, a gramática desta tela
# aceitaria esses textos em silêncio; `para_decimal` (segunda camada,
# chamada depois da tradução) já recusa todos eles hoje, então não havia
# furo ativo — mas manter `\d` aqui deixaria um julgador frouxo na
# PRIMEIRA camada, quando a segunda for a única linha de defesa não
# deveria ser por acidente.
_GRAMATICA_VALOR_PTBR = re.compile(r"^[+-]?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]{1,2})?$")


def _decimal_do_formulario(texto):
    """Converte o texto digitado no campo de valor (pt-BR) para `Decimal`.

    DUAS camadas, nesta ordem — DE-029 (rodada 2) sobre DE-027 (rodada 1):

    1. `_GRAMATICA_VALOR_PTBR` julga se o texto é uma representação pt-BR
       BEM FORMADA (a única coisa que só esta tela pode saber — a API não
       fala pt-BR). Texto fora da gramática é recusado AQUI, com mensagem
       que ensina o formato — nunca "corrigido" ou reinterpretado.
    2. Só o que casou a gramática é TRADUZIDO (pontos de milhar somem,
       vírgula decimal vira ponto — a única tradução de locale que esta
       tela faz, agora comprovadamente segura: a gramática já garantiu que
       cada ponto restante é um separador de milhar válido) e entregue a
       `apps.core.dinheiro.para_decimal`, que é quem julga se o resultado é
       uma representação aceitável de dinheiro em geral (mesmo módulo que a
       API usa em `_extrair_itens`, views.py) — sinal, não-finito, formato
       canônico. Continua sendo a ÚNICA função que decide isso (DE-027):
       esta view nunca constrói `Decimal` por conta própria.

    Antes da DE-027 (rodada 1), a função construía `Decimal(bruto)`
    diretamente — o construtor do Python é mais permissivo do que o
    contrato monetário do projeto (notação científica, "_" como separador
    de dígitos, não rejeita `NaN`/`Infinity`). Antes da DE-029 (rodada 2), a
    tradução só tirava o ponto quando havia vírgula, e "1.000" virava 1,00.

    Levanta `ValorMonetarioInvalido` para texto que não representa um valor
    monetário aceitável — quem chama trata isso como erro de FORMULÁRIO. A
    validação de DOMÍNIO (sinal, escala máxima — DE-010) continua sendo
    feita só por `criar_lancamento` (services.py); esta função só entende o
    formato de DIGITAÇÃO, nunca decide se o valor é aceitável contabilmente.
    """
    bruto = texto or ""
    if not _GRAMATICA_VALOR_PTBR.fullmatch(bruto):
        raise ValorMonetarioInvalido(
            f"Valor “{bruto}” não está no formato aceito. Use dígitos, ponto "
            "a cada três casas como separador de milhar (ex.: 1.000) e "
            "vírgula para os centavos (ex.: 1.000,00). Um texto ambíguo "
            "nunca é reinterpretado — é recusado."
        )
    # Seguro remover TODOS os pontos (não só quando há vírgula): a
    # gramática acima já garantiu que, se existem pontos, cada um deles é
    # um grupo de milhar de exatamente três dígitos — nunca um separador
    # decimal disfarçado (esse caso já foi recusado acima).
    traduzido = bruto.replace(".", "").replace(",", ".")
    return para_decimal(traduzido)


# R2-3 (rodada 2 da auditoria da DL-017): teto de SEGURANÇA para quantas
# linhas esta view tenta ler/exibir a partir de um único POST — bem acima
# do teto de NEGÓCIO (LINHAS_MAXIMAS_LANCAMENTO). Não é regra contábil: é
# higiene de fronteira HTTP, para que um ÚNICO campo com índice absurdo
# (ex.: "conta_999999999999") não force esta view a processar/exibir uma
# quantidade de linhas proporcional a esse índice.
#
# R3-9 (rodada 3, BL-120): os DOIS tetos precisam ficar nesta ordem para
# sempre — o de SEGURANÇA (este) estritamente maior que o de NEGÓCIO
# (LINHAS_MAXIMAS_LANCAMENTO, definido no topo do módulo) — porque hoje é
# a DESIGUALDADE entre os dois, e não o desenho de nenhuma função, que
# impede um índice fora do canônico (recusado por `_indices_de_linha_do_
# post`) de coincidir com um índice de negócio válido. Falhar cedo e
# ruidosamente (`AssertionError` na importação do módulo, não um 500 numa
# requisição) é deliberado: é uma invariante ESTRUTURAL do arquivo, não
# um dado de runtime — o mesmo motivo por que também há um teste dedicado
# (`test_teto_de_seguranca_e_estritamente_maior_que_o_teto_de_negocio`,
# em test_dl017_rodada2_frontend.py), que não depende do processo ter
# sido de fato importado com `assert` habilitado (`python -O` os
# descarta).
# RC-79/BL-207 (rodada 6): o teto de NEGÓCIO subiu de 20 para 200, e este
# teto de SEGURANÇA **subiu junto**, de 200 para 400 — que é exatamente o
# que a verificação abaixo existe para forçar. Ela REPROVOU a importação do
# módulo no instante em que o teto de negócio virou 200, com os dois em
# 200: o mecanismo da BL-120 funcionando como projetado, um ano-luz melhor
# do que a perda silenciosa que ele substituiu (com os dois iguais,
# `min(maior, 200)` voltaria a descartar em silêncio o índice 200 na
# fronteira). Mantido o dobro do teto de negócio, e não 201, para que a
# folga continue existindo sem depender de aritmética de fronteira.
LINHAS_LEITURA_TETO_DE_SEGURANCA = 400
assert LINHAS_MAXIMAS_LANCAMENTO < LINHAS_LEITURA_TETO_DE_SEGURANCA, (
    "LINHAS_MAXIMAS_LANCAMENTO (teto de NEGÓCIO) precisa ficar estritamente "
    "abaixo de LINHAS_LEITURA_TETO_DE_SEGURANCA (teto de SEGURANÇA) — R3-9/BL-120."
)

# R3-2/BL-116 (rodada 3): o padrão de BUSCA é deliberadamente amplo —
# qualquer sufixo NÃO VAZIO depois de "conta_"/"tipo_"/"valor_" — e não
# `[0-9]{1,4}` como na rodada 2. A versão antiga só CASAVA índices já bem
# formados; um índice mal formado ("conta_10000", "conta_0001",
# "conta_+3") simplesmente não casava NADA, ficava invisível para
# `_indices_de_linha_do_post` e para a leitura (`_linhas_lancamento_do_post`
# só lê pela chave CANÔNICA "conta_{i}", nunca "conta_0001") — a linha
# desaparecia em silêncio, com HTTP 302 "gravado com sucesso". Para poder
# RECUSAR uma chave malformada (em vez de ignorá-la), a busca precisa
# primeiro ENCONTRÁ-LA.
#
# A3 (rodada 4): `re.IGNORECASE` por um motivo específico — "CONTA_3" e
# "Conta_3" (prefixo em capitalização diferente da que o template emite)
# também precisam ser ENCONTRADOS para poderem ser recusados como não
# canônicos (ver o teste de capitalização em `_indices_de_linha_do_post`
# abaixo). Sem isto, ficavam invisíveis pelo mesmo motivo que o índice
# malformado ficava antes da correção da rodada 3.
_PADRAO_CHAVE_DE_LINHA = re.compile(r"^(conta|tipo|valor)_(.+)$", re.IGNORECASE)


def _indices_de_linha_do_post(post):
    """Varre o POST e devolve `(maior_indice, chaves_nao_canonicas)`.

    R2-3 (rodada 2): deriva quantas linhas o POST REALMENTE contém a
    partir do próprio conteúdo enviado — nunca do campo oculto
    `num_linhas`. O achado 5 da rodada 1 ("nunca truncar partidas em
    silêncio") só tinha sido fechado por cima: um `num_linhas` INFLADO
    já não truncava (BL-91), mas um `num_linhas` MALFORMADO, vazio ou
    menor do que o conteúdo real ainda abria a porta de baixo. A causa
    real nunca foi o teto: é a view confiar num CONTADOR ENVIADO PELO
    CLIENTE para decidir quantos campos ler. `num_linhas` continua
    existindo, mas só para a EXIBIÇÃO — nunca mais para decidir quantas
    linhas LER.

    R3-2/BL-116 (rodada 3): a correção da rodada 2 fechou o CASO medido
    (`num_linhas` malformado) e deixou aberta a CLASSE — um índice fora
    do formato canônico ainda desaparecia em silêncio, com 302 de
    sucesso. Um índice é CANÔNICO quando é um inteiro entre 1 e
    `LINHAS_LEITURA_TETO_DE_SEGURANCA`, escrito em dígitos ASCII, SEM
    zero à esquerda, sinal ou qualquer caractere que não seja dígito —
    ou seja, exatamente `str(i)` para algum `i` inteiro nesse intervalo.
    QUALQUER outra coisa ("0", "01", "0001", "10000", "+3", " 3", um
    sufixo não numérico) é NÃO CANÔNICA: esta função devolve a chave
    INTEIRA em `chaves_nao_canonicas`, e quem chama DEVE recusar o POST
    inteiro (400, nomeando as chaves) — nunca ignorar a linha e seguir
    em frente, que foi exatamente a política que produziu o achado 5.

    A conversão em si é `_inteiro_de_cliente` (ver o docstring dela): um
    sufixo com dígito Unicode fora do ASCII, ou absurdamente longo (mais
    dígitos do que o limite de conversão do próprio Python), nunca lança
    exceção — vira "chave não entendida" (não canônica), não um 500 nem
    uma reinterpretação silenciosa.
    """
    maior = 0
    chaves_nao_canonicas = []
    for chave in post:
        casamento = _PADRAO_CHAVE_DE_LINHA.match(chave)
        if not casamento:
            continue
        prefixo = casamento.group(1)
        if prefixo != prefixo.lower():
            # A3 (rodada 4): "CONTA_3"/"Conta_3" — o template NUNCA emite
            # prefixo fora de minúsculas; um POST construído à mão com
            # capitalização diferente não é uma linha "que não existe", é
            # uma linha que ninguém olhou. Recusa, não ignora.
            chaves_nao_canonicas.append(chave)
            continue
        sufixo = casamento.group(2)
        indice = _inteiro_de_cliente(sufixo)
        if (
            indice is None
            or str(indice) != sufixo
            or indice < 1
            or indice > LINHAS_LEITURA_TETO_DE_SEGURANCA
        ):
            chaves_nao_canonicas.append(chave)
            continue
        if indice > maior:
            maior = indice
    return maior, chaves_nao_canonicas


def _linhas_lancamento_do_post(post, num_linhas):
    """Extrai as linhas PREENCHIDAS do formulário de lançamento a partir do
    POST bruto. Uma linha totalmente vazia é ignorada — o contador não
    precisa preencher as N linhas oferecidas. Uma linha PARCIALMENTE
    preenchida é um erro de formulário, reportado como tal.

    `valor_texto` é devolvido SEM `.strip()` (achado 2, DE-027): espaço em
    volta do valor é uma DIGITAÇÃO que `_decimal_do_formulario`/
    `para_decimal` devem julgar, não algo que esta função pode descartar
    antes — descartar em silêncio é exatamente a reinterpretação que o
    projeto decidiu nunca fazer. `conta_id` e `tipo` continuam com
    `.strip()`: são identificadores/opções de `<select>`, não texto de
    dinheiro, e não têm um julgador de formato próprio para delegar a
    checagem. A DECISÃO de "linha em branco" usa o valor JÁ testado por
    vazio (`.strip()` só para esta comparação), não o texto guardado.

    R3-1 (rodada 3, BL-115): `num_linhas` é capado em `LINHAS_LEITURA_
    TETO_DE_SEGURANCA` DENTRO desta função, defesa em profundidade —
    além de todo chamador já ser responsável por nunca passar um número
    vindo do cliente sem antes recusá-lo (ver `lancamento_novo`), esta
    função por si só nunca deve poder ser levada a iterar um número de
    vezes proporcional a um valor arbitrário. Nenhum `range()` deste
    módulo confia sozinho no chamador para ficar seguro.
    """
    num_linhas = min(num_linhas, LINHAS_LEITURA_TETO_DE_SEGURANCA)
    linhas = []
    erros = []
    for i in range(1, num_linhas + 1):
        conta_id = (post.get(f"conta_{i}") or "").strip()
        tipo = (post.get(f"tipo_{i}") or "").strip()
        valor_bruto = post.get(f"valor_{i}") or ""
        valor_em_branco = not valor_bruto.strip()
        if not conta_id and not tipo and valor_em_branco:
            continue
        if not conta_id or not tipo or valor_em_branco:
            erros.append(f"Linha {i}: preencha conta, tipo e valor, ou deixe a linha em branco.")
            continue
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_bruto})
    return linhas, erros


def _veredito_fechamento(
    total_debito,
    total_credito,
    linhas_excluidas_do_total,
    num_partidas_validas,
    *,
    bloqueado_por_outro_erro=False,
):
    """Decide, em `Decimal`, um de três estados — `"fecha"`, `"nao_fecha"`
    ou `"nao_conferido"` — para o rodapé "Total conferido antes de gravar"
    do formulário de lançamento.

    BL-289 (A1 da auditoria DL-026 rodada 2): o TEMPLATE decidia sozinho,
    comparando os dois valores já formatados em pt-BR
    (`total_debito_ptbr == total_credito_ptbr`) — string, não `Decimal`.
    `_valor_ptbr(Decimal("0"))` devolve `"0,00"`, que é verdadeiro em
    template Django, e `"0,00" == "0,00"` também é verdadeiro: um
    formulário em BRANCO, duas linhas com valor inválido (descartadas do
    total) ou totais NEGATIVOS caíam todos no ramo "Fecha", incluindo o
    caso em que a própria tela já tinha avisado, duas linhas acima, que o
    que foi digitado não entrou na conta. Veredito é decisão de negócio;
    o template só EXIBE a chave que esta função devolve.

    As quatro condições de `"fecha"` cobrem `totais_batem` mais
    `len(itens) >= 2`, mais abaixo nesta view — mas NÃO bastam sozinhas
    para garantir a invariante exigida pela auditoria, "se a tela diz
    Fecha, gravar com o mesmo corpo tem de devolver 302, nunca 400" (ver
    `test_bl289_veredito_fechamento.py` e `test_bl307_*.py`). `criar_
    lancamento` só é chamado quando, ALÉM de débito == crédito > 0 e duas
    ou mais partidas, TAMBÉM não há nenhum outro erro (histórico maior que
    o teto, chave de idempotência maior que o teto, data inválida) — três
    condições que não têm relação nenhuma com débito, crédito ou linha
    excluída, e por isso não podiam ser expressas pelos quatro parâmetros
    originais desta função.
    `bloqueado_por_outro_erro` é exatamente essa quinta condição (BL-307,
    A1 da auditoria DL-026 rodada 3): quando `True`, "fecha" nunca é
    devolvido, mesmo que as partidas batam — dizer "Fecha" sobre um
    formulário que `criar_lancamento` vai recusar por um motivo alheio às
    partidas seria a MESMA mentira que a ausência de `linhas_excluidas_do_
    total` produzia, só que por outra causa. O padrão default (`False`)
    preserva o comportamento do caminho "adicionar_linha", que nunca
    valida histórico, chave ou data — ali "fecha" continua descrevendo
    somente a conferência das partidas, que é a única pergunta que aquele
    botão responde.

    `"nao_fecha"` exige duas ou mais partidas válidas e NENHUMA descartada
    — sem isso, "não fecha" seria dito sobre um total que ainda pode mudar
    assim que a linha pendente for corrigida, o que é ruído, não
    conferência. `"nao_fecha"` NÃO depende de `bloqueado_por_outro_erro`:
    débito e crédito genuinamente diferentes continuam sendo uma
    divergência real, ainda que exista também um erro de histórico ou data
    — não é uma afirmação falsa, é uma afirmação incompleta (o contador vê
    o outro erro na lista de mensagens, ao lado). Todo o resto (formulário
    em branco, linha descartada, total zerado, negativo, só uma partida
    válida, ou bloqueado por outro erro) é `"nao_conferido"` — nunca
    "Fecha" nem "Não fecha".
    """
    # `total_debito`/`total_credito` chegam `None` na primeira visita (GET
    # em branco) e nos ramos de erro que nunca calculam totais — tratados
    # como zero só para ESTA decisão (nunca exibidos como "0,00": ver
    # `total_debito_ptbr`/`total_credito_ptbr` abaixo, que continuam `None`
    # nesses casos).
    debito = total_debito if total_debito is not None else Decimal("0")
    credito = total_credito if total_credito is not None else Decimal("0")
    fecha = (
        debito == credito
        and debito > 0
        and linhas_excluidas_do_total == 0
        and num_partidas_validas >= 2
        and not bloqueado_por_outro_erro
    )
    if fecha:
        return "fecha"
    nao_fecha = num_partidas_validas >= 2 and linhas_excluidas_do_total == 0 and debito != credito
    if nao_fecha:
        return "nao_fecha"
    return "nao_conferido"


def _contexto_form_lancamento(
    empresa,
    contas_disponiveis,
    num_linhas,
    *,
    data_texto,
    historico,
    chave_idempotencia,
    linhas_preenchidas=None,
    total_debito=None,
    total_credito=None,
    linhas_excluidas_do_total=0,
    num_partidas_validas=0,
    bloqueado_por_outro_erro=False,
):
    # R3-1 (BL-115): defesa em profundidade — ver o comentário equivalente
    # em `_linhas_lancamento_do_post`. Esta função monta o CONTEXTO de
    # renderização; nunca deve poder ser levada a montar uma lista
    # proporcional a um `num_linhas` arbitrário.
    num_linhas = min(num_linhas, LINHAS_LEITURA_TETO_DE_SEGURANCA)
    linhas = []
    for i in range(1, num_linhas + 1):
        if linhas_preenchidas is not None:
            conta_id = linhas_preenchidas.get(f"conta_{i}", "")
            tipo = linhas_preenchidas.get(f"tipo_{i}", "")
            valor_texto = linhas_preenchidas.get(f"valor_{i}", "")
        else:
            conta_id, tipo, valor_texto = "", "", ""
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_texto})

    # BL-286 (rodada 3 da DL-026, corrige o M2 da rodada 1): o veredito
    # "Não fecha" precisa dizer DE QUANTO, e quem calcula é o SERVIDOR, não
    # o template — o `especialista-frontend` já tinha parado exatamente
    # aqui, porque só recebia os dois totais como TEXTO pt-BR já formatado
    # (`total_debito_ptbr`/`total_credito_ptbr`), e subtrair dois valores
    # monetários já formatados dentro do template violaria a regra do
    # AGENTS.md contra aritmética financeira fora do motor determinístico.
    #
    # A subtração abaixo acontece em `Decimal`, sobre os totais de ORIGEM
    # (`total_debito`/`total_credito`, ainda não formatados) — nunca sobre
    # `total_debito_ptbr`/`total_credito_ptbr`. Ela NÃO passa por
    # `apps.core.dinheiro.quantizar`: essa função existe para reduzir a
    # ESCALA de um valor segundo uma política de arredondamento (DE-010,
    # obrigatória quando a redução pode perder informação), e aqui não há
    # redução nenhuma — cada item já foi recusado por `criar_lancamento`/
    # `_decimal_do_formulario` se tivesse mais de
    # `ESCALA_MAXIMA_LANCAMENTO_MANUAL` (2) casas decimais, então
    # `total_debito` e `total_credito` já chegam aqui com, no máximo, 2
    # casas — a diferença de dois valores com a MESMA escala máxima é
    # EXATA, sem arredondamento a decidir (mesmo raciocínio já aplicado a
    # `_saldo_por_natureza`/`_saldo_por_natureza_item`, em services.py, que
    # também subtraem débito e crédito em `Decimal` puro, sem política).
    # `_valor_ptbr` continua sendo o ÚNICO formatador pt-BR desta tela —
    # reaproveitado aqui, não reimplementado.
    # BL-289 (A1 da auditoria DL-026 rodada 2): o veredito em si — ver o
    # docstring de `_veredito_fechamento` para a classe de defeito que isto
    # substitui. Calculado ANTES da diferença abaixo porque a diferença só
    # pode ser exibida no ramo "nao_fecha" (nunca em "nao_conferido" — um
    # formulário com linha descartada, por exemplo, também tem
    # `total_debito != total_credito` textualmente, mas mostrar "faltam X"
    # ali ensinaria um número que pode mudar assim que a linha pendente for
    # corrigida).
    # BL-307: `bloqueado_por_outro_erro` propaga a quinta condição (ver o
    # docstring de `_veredito_fechamento`) — sempre `False` no caminho
    # "adicionar_linha", que não valida histórico, chave nem data.
    veredito_fechamento = _veredito_fechamento(
        total_debito,
        total_credito,
        linhas_excluidas_do_total,
        num_partidas_validas,
        bloqueado_por_outro_erro=bloqueado_por_outro_erro,
    )

    diferenca_fechamento_ptbr = None
    lado_faltante_fechamento = None
    if veredito_fechamento == "nao_fecha":
        diferenca_fechamento = abs(total_debito - total_credito)
        diferenca_fechamento_ptbr = _valor_ptbr(diferenca_fechamento)
        # O lado que "falta" é o menor total — é ELE que precisa crescer
        # para fechar. Nunca um valor negativo exibido (critério 1 do
        # BL-286): a diferença já sai em módulo acima, e o lado vem à
        # parte, como palavra, não como sinal.
        lado_faltante_fechamento = "débito" if total_debito < total_credito else "crédito"

    return {
        "empresa": empresa,
        "contas": contas_disponiveis,
        "linhas": linhas,
        "num_linhas": num_linhas,
        "data_texto": data_texto,
        "historico": historico,
        "chave_idempotencia": chave_idempotencia,
        "pode_adicionar_linha": num_linhas < LINHAS_MAXIMAS_LANCAMENTO,
        "linhas_maximas": LINHAS_MAXIMAS_LANCAMENTO,
        # RC-77/BL-205 — faixa de data de lançamento (01/01/2000 a hoje +
        # N dias), confirmada pelo Fred em 2026-09-15. Os dois valores vêm
        # de `apps.contabilidade.services`, fonte única, e chegam ao
        # template em DUAS formas porque servem a dois propósitos
        # diferentes:
        #
        # - ISO (`*_iso`) para os atributos `min`/`max` do `<input
        #   type="date">`. É CONVENIÊNCIA, nunca defesa: o atributo é do
        #   navegador, e quem monta a requisição à mão passa por cima dele
        #   — a recusa de verdade é de `criar_lancamento` (servidor), com
        #   teste próprio. DE-031 continua valendo: o campo segue sendo o
        #   seletor nativo e o rótulo não volta a afirmar formato.
        # - pt-BR (`*_ptbr`) para o texto de apoio, porque toda data
        #   EXIBIDA por este sistema é dd/mm/aaaa (critério 7) — inclusive
        #   quando ela aparece dentro de uma frase.
        "data_minima_iso": DATA_MINIMA_LANCAMENTO.isoformat(),
        "data_maxima_iso": data_maxima_lancamento().isoformat(),
        "data_minima_ptbr": DATA_MINIMA_LANCAMENTO,
        "data_maxima_ptbr": data_maxima_lancamento(),
        "total_debito_ptbr": _valor_ptbr(total_debito) if total_debito is not None else None,
        "total_credito_ptbr": _valor_ptbr(total_credito) if total_credito is not None else None,
        # BL-289: chave ÚNICA de decisão — "fecha" / "nao_fecha" /
        # "nao_conferido" —, calculada em `Decimal` por `_veredito_
        # fechamento`. O template RAMIFICA por ela; não volta a comparar
        # `total_debito_ptbr`/`total_credito_ptbr` (texto) entre si.
        "veredito_fechamento": veredito_fechamento,
        # BL-286: `None` fora do ramo "nao_fecha" — nunca "0,00", que seria
        # ruído (critério 2). Só a variante "não fecha" do template usa
        # estas duas chaves.
        "diferenca_fechamento_ptbr": diferenca_fechamento_ptbr,
        "lado_faltante_fechamento": lado_faltante_fechamento,
        # R2-5: quantas linhas ficaram FORA da soma acima (conta/tipo/valor
        # incompletos, ou valor/conta inválidos) — a conferência precisa
        # ANUNCIAR a exclusão, nunca só mostrar um total plausível e
        # batendo que ignora, em silêncio, o que está preenchido ao lado.
        "linhas_excluidas_do_total": linhas_excluidas_do_total,
    }


def _itens_e_totais(linhas_brutas, contas_por_id):
    """Converte as linhas BRUTAS do POST (já filtradas por
    `_linhas_lancamento_do_post`) em itens prontos para `criar_lancamento`,
    somando débito e crédito no caminho.

    Compartilhada pelos dois ramos que precisam do MESMO cálculo (achado 3
    / BL-88): "adicionar_linha" (só para mostrar o total de CONFERÊNCIA,
    nunca para gravar) e "gravar" (para decidir se pode gravar). Antes
    desta correção, "adicionar_linha" reconstruía o formulário sem chamar
    nada disto, e o rodapé "Total conferido antes de gravar" mostrava
    `0,00 / 0,00` com as linhas já preenchidas ao lado — o único total que
    esta tela mostra num caminho sem erro (não há JavaScript, critério 15)
    estava sempre errado.

    Uma linha com conta/tipo/valor inválido não interrompe o cálculo: ela
    soma um erro à lista devolvida e é EXCLUÍDA da soma. Para
    "adicionar_linha" isso é a conferência PARCIAL esperada enquanto o
    contador ainda digita (uma linha isolada errada não deve zerar o total
    das demais); para "gravar", a presença de qualquer erro na lista já
    impede a gravação mais abaixo, então a soma aqui não precisa ser
    "tudo ou nada" — ela só alimenta a mensagem de conferência.

    Devolve `(itens, erros, total_debito, total_credito)`.
    """
    itens = []
    erros = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for linha in linhas_brutas:
        # A1 (rodada 4 da auditoria da DL-017): `linha["conta_id"].isdigit()`
        # sozinho aceitava dígito Unicode (`"７".isdigit()` é `True`, e o
        # `int()` seguinte reinterpretava em silêncio como a conta 7) e não
        # protegia o `int()` de um texto de mais de 4300 dígitos —
        # `ValueError` cru, 500. `conta_id` É um identificador de banco
        # (não uma quantidade de negócio), então usa `_identificador_de_
        # cliente` — o mesmo julgador (`para_id`) que a API e
        # `apps.tenancy` já usam para a idêntica invariante (ver o
        # comentário de importação de `para_id`, no topo do arquivo).
        conta_id = _identificador_de_cliente(linha["conta_id"])
        conta = contas_por_id.get(conta_id) if conta_id is not None else None
        if conta is None:
            # Também cobre o caso de um `conta_id` de OUTRA empresa (não
            # está em `contas_por_id`, que só tem contas DESTA empresa) —
            # nunca vaza para a mensagem de erro qual empresa seria, só que
            # a conta é inválida.
            erros.append(f"Linha {linha['indice']}: conta inválida.")
            continue
        try:
            valor = _decimal_do_formulario(linha["valor_texto"])
        except ValorMonetarioInvalido:
            # R2-1/DE-029: a mensagem ENSINA o formato em vez de só dizer
            # "inválido" — é a exigência da própria decisão ("recusa com
            # mensagem que ensina o formato"), no lugar onde o contador de
            # fato lê o erro (o rodapé de mensagens da tela).
            erros.append(
                f"Linha {linha['indice']}: valor “{linha['valor_texto']}” inválido. Use "
                "dígitos, ponto a cada três casas como separador de milhar "
                "(ex.: 1.000) e vírgula para os centavos (ex.: 1.000,00)."
            )
            continue
        # Mesmo teto de MAGNITUDE que a API já verifica em `_extrair_itens`
        # (views.py) antes de chamar `criar_lancamento` — achado da
        # varredura desta rodada (critério de aceite 1): `criar_lancamento`
        # (services.py) verifica sinal e ESCALA (casas decimais), mas nunca
        # magnitude; sem este limite AQUI, um valor cujo módulo não caiba
        # em `ItemLancamento.valor` (DecimalField max_digits=18,
        # decimal_places=2) passa por toda validação de domínio e só falha
        # no INSERT do Postgres com `DataError: numeric field overflow` —
        # 500, não 400, exatamente a MESMA classe de defeito dos achados 1
        # e 4, num caminho que o auditor não tinha percorrido ainda.
        if abs(valor) >= LIMITE_MAGNITUDE_VALOR:
            # A mensagem usa o TEXTO digitado, não `_valor_ptbr(valor)`: um
            # valor deste tamanho (por definição, aqui) pode ter centenas
            # de dígitos, e `_valor_ptbr` faz `.quantize(Decimal("0.01"))`
            # — que levanta `decimal.InvalidOperation` quando o resultado
            # excede a precisão do contexto decimal (28 dígitos, ver o
            # docstring de `quantizar` em apps/core/dinheiro.py). Formatar
            # o valor recusado por ser grande demais CRIARIA um 500 novo,
            # exatamente a classe de defeito que esta checagem existe para
            # fechar. `LIMITE_MAGNITUDE_VALOR` (10**16) é pequeno e seguro
            # de formatar.
            erros.append(
                f"Linha {linha['indice']}: valor “{linha['valor_texto']}” é grande demais "
                f"para um item de lançamento; o módulo deve ser menor que "
                f"{_valor_ptbr(LIMITE_MAGNITUDE_VALOR)}."
            )
            continue
        if linha["tipo"] not in (TipoPartida.DEBITO, TipoPartida.CREDITO):
            erros.append(f"Linha {linha['indice']}: tipo de partida inválido.")
            continue
        itens.append({"conta": conta, "tipo": linha["tipo"], "valor": valor})
        if linha["tipo"] == TipoPartida.DEBITO:
            total_debito += valor
        else:
            total_credito += valor
    return itens, erros, total_debito, total_credito


def _linhas_a_reexibir_do_post(post):
    """Quantas linhas um caminho de RECUSA precisa devolver à tela, derivado
    do CONTEÚDO REAL do POST — nunca um número fixo.

    R6-5/BL-199 (rodada 6): `_recusa_lancamento_com_erro` passava
    `LINHAS_INICIAIS_LANCAMENTO` (4) **fixo**, enquanto o caminho de
    gravação, 200 linhas abaixo, deriva `num_linhas_leitura` do conteúdo do
    POST justamente para não perder linha. Medido pelo auditor com 8 linhas
    preenchidas: voltavam 4, e as outras 4 o contador digitava de novo —
    numa função cujo docstring promete "o formulário RE-RENDERIZADO com o
    que já estava preenchido (nunca uma tela em branco)". Para
    `request.FILES` isso era anterior à rodada 6; para `request.GET` e para
    o cabeçalho era novo, e triplicou a exposição.

    A derivação tem a mesma FORMA do caminho de gravação, pela mesma razão
    (R2-3): o campo oculto `num_linhas` não decide quantas linhas existem —
    o CONTEÚDO decide. O teto de SEGURANÇA fecha por cima (o
    `_contexto_form_lancamento` também capa, defesa em profundidade): nem
    aqui um `num_linhas` arbitrário dimensiona a página.

    **O piso NÃO é o mesmo, e é deliberado** (resíduo do BL-199 apontado
    pelo `desenvolvedor-pleno` na varredura de afirmações; antes esta frase
    dizia "a MESMA", o que era falso): a gravação usa piso 2 porque lá
    `num_linhas_exibicao` também serve ao botão "+ linha", que precisa
    poder trabalhar com duas linhas; **um formulário RECUSADO volta com o
    piso da tela INICIAL** (`LINHAS_INICIAIS_LANCAMENTO`), para nunca
    oferecer menos linhas do que um formulário novo. A escolha não perde
    nada digitado em nenhum dos dois pisos — o piso só acrescenta linha em
    BRANCO —, e está travada por
    `test_piso_de_reexibicao_e_o_da_tela_INICIAL_e_nao_o_da_gravacao`
    (test_dl019_frontend_recusa_do_formulario_de_lancamento.py).

    `num_linhas` não entra no `max`: um campo oculto inflado (ou absurdo,
    acima do teto de segurança) faria esta função devolver uma página
    proporcional ao que o cliente mandou, exatamente o que o parágrafo
    acima diz que não acontece. Para um POST de formulário REAL isso não
    muda nada — o `<form>` emite as chaves de todas as linhas que
    renderizou, então o maior índice presente JÁ é o número de linhas
    exibidas.
    """
    maior_indice, _ = _indices_de_linha_do_post(post)
    return min(
        max(LINHAS_INICIAIS_LANCAMENTO, maior_indice),
        LINHAS_LEITURA_TETO_DE_SEGURANCA,
    )


def _recusa_lancamento_com_erro(request, empresa, contas_disponiveis, mensagem):
    """Recusa a tentativa de POST em `lancamento_novo` com `mensagem`,
    devolvendo o formulário RE-RENDERIZADO com **tudo** o que já estava
    preenchido (nunca uma tela em branco, nunca só as primeiras linhas) e
    `status=400`. Ponto único para os "dicionários da requisição" que esta
    view recusa por completo, nunca ignora em silêncio — hoje julgados por
    `apps.core.requisicao` (BL-196), antes três `if` escritos à mão aqui
    (`request.FILES`, A3/BL-128; `request.GET` e o cabeçalho
    `Idempotency-Key`, R5-6/BL-145).

    R6-5/BL-199: o número de linhas re-exibidas vem de
    `_linhas_a_reexibir_do_post` (ver o docstring dela) — era aqui que as
    linhas além da quarta se perdiam.
    """
    messages.error(request, mensagem)
    contexto = _contexto_form_lancamento(
        empresa,
        contas_disponiveis,
        _linhas_a_reexibir_do_post(request.POST),
        data_texto=request.POST.get("data", ""),
        historico=request.POST.get("historico", "").strip(),
        chave_idempotencia=request.POST.get("chave_idempotencia") or uuid.uuid4().hex,
        linhas_preenchidas=request.POST,
    )
    return render(request, "contabilidade/lancamento_form.html", contexto, status=400)


# ---------------------------------------------------------------------------
# BL-196/R6-2 — a política dos cinco dicionários aplicada às DUAS telas de
# POST deste arquivo. O julgamento é de `apps.core.requisicao`; aqui ficam
# a DECLARAÇÃO de cada contrato e a RESPOSTA de tela.
# ---------------------------------------------------------------------------


# Campos que o `<form>` de lançamento REALMENTE emite, fora as linhas
# (dinâmicas, tratadas abaixo). `csrfmiddlewaretoken` está aqui porque é
# enviado pelo `{% csrf_token %}` do próprio template: sem declará-lo, o
# contrato recusaria o formulário legítimo — o que seria a forma mais
# rápida possível de alguém "consertar" isto declarando `campos=None` e
# reabrindo o buraco.
_CAMPOS_FIXOS_DO_FORMULARIO_DE_LANCAMENTO = frozenset(
    {"csrfmiddlewaretoken", "acao", "num_linhas", "data", "historico", "chave_idempotencia"}
)


def _contrato_do_formulario_de_lancamento(post):
    """Contrato desta tela para ESTE POST.

    `campos` é declarado **explicitamente** (nunca `None`): os fixos acima,
    mais as chaves de linha presentes no POST que TÊM a forma de chave de
    linha (`conta_*`/`tipo_*`/`valor_*`, por `_PADRAO_CHAVE_DE_LINHA`).

    A divisão de trabalho com `_indices_de_linha_do_post` é deliberada e
    não é frouxidão: o contrato julga se o NOME do campo pertence ao
    vocabulário desta tela; `_indices_de_linha_do_post` julga se o ÍNDICE é
    canônico, e recusa `conta_0001`, `CONTA_3`, `conta_+3` com a mensagem
    específica que o auditor mediu como correta (R3-2/BL-116, A3/rodada 4).
    Se o contrato recusasse essas chaves primeiro, o contador passaria a
    ler "campo não reconhecido" no lugar de "índice de linha fora do
    formato esperado" — mensagem pior para o mesmo defeito, e três testes
    de texto quebrados. Nenhuma chave fica sem julgamento: o que o contrato
    deixa passar aqui, a canonicidade recusa na linha seguinte da view.
    """
    chaves_de_linha = {chave for chave in post if _PADRAO_CHAVE_DE_LINHA.match(chave)}
    return ContratoDeRequisicao(
        campos=_CAMPOS_FIXOS_DO_FORMULARIO_DE_LANCAMENTO | chaves_de_linha,
        # Esta tela nunca ofereceu upload, e não tem contrato de
        # querystring — ver `_mensagem_de_tela_para_dado_nao_contratado`
        # para a razão CERTA de recusar querystring (a razão que estava
        # escrita aqui era factualmente falsa sobre HTML).
        aceita_arquivo=False,
        aceita_querystring=False,
        # A chave de idempotência desta tela É o campo oculto do próprio
        # formulário. Quem manda `Idempotency-Key` por cabeçalho (o
        # contrato da API, não desta tela) e omite o campo do corpo recebia
        # uma chave nova a cada POST e GRAVAVA DUAS VEZES — a duplicidade
        # que a chave existe para impedir, na superfície errada
        # (R5-6/BL-145).
        cabecalhos_ignorados=("Idempotency-Key",),
        contexto="no formulário de lançamento",
    )


# Campos que o `<form>` de conta REALMENTE emite. `aceita_lancamento` é
# caixa de marcação (só vem quando marcada) e `confirmar_conta_sem_conta_
# mae` é o botão de confirmação do RC-80/BL-208 — os dois são legítimos e
# precisam estar declarados.
_CONTRATO_DO_FORMULARIO_DE_CONTA = ContratoDeRequisicao(
    campos=frozenset(
        {
            "csrfmiddlewaretoken",
            "codigo",
            "nome",
            "tipo",
            "natureza",
            "conta_pai",
            "aceita_lancamento",
            "confirmar_conta_sem_conta_mae",
        }
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta",
)


def _mensagem_de_tela_para_dado_nao_contratado(excecao, *, explicacao_extra=""):
    """Traduz `DadoNaoContratado` para a frase que ESTA superfície mostra.

    Decide por `excecao.dicionario` (constante estável), nunca pelo texto da
    mensagem do módulo: comparar texto amarraria a tela à redação de
    `apps.core.requisicao`, e a primeira reformulação lá quebraria o
    português daqui sem nenhum aviso.

    Por que recusar QUERYSTRING num POST, agora com a razão certa
    (R6-5/BL-199): a justificativa anterior dizia que "nenhum formulário
    renderizado por esta tela produz querystring num POST (o `<form>` não
    tem `action=`)" — e era **falsa sobre HTML**, como o auditor mediu: um
    `<form>` SEM `action` envia para a URL do próprio documento,
    querystring incluída. Quem chegasse à tela por um link com
    `?utm_source=...` não conseguia gravar. Duas mudanças fecham isso: os
    dois formulários passaram a declarar `action` explícito e sem
    querystring (ver os templates, e o teste que lê o atributo), e a razão
    escrita passou a ser a verdadeira — **esta tela não tem contrato de
    querystring**: nenhum parâmetro de URL altera o que ela grava, então um
    parâmetro presente é dado que ninguém vai ler, e dado que ninguém lê se
    recusa nomeando.
    """
    chaves = "; ".join(excecao.chaves)
    if excecao.dicionario == DICIONARIO_ARQUIVO:
        return (
            "Este formulário não aceita arquivo nenhum. Campo(s) enviados como "
            f"arquivo, recusados por completo: {chaves}. Nada foi gravado."
        )
    if excecao.dicionario == DICIONARIO_QUERYSTRING:
        return (
            "Este formulário não aceita parâmetros na URL — nenhum deles altera o "
            f"que ele grava. Parâmetro(s) recusados por completo: {chaves}. Nada "
            "foi gravado. Abra a tela pelo menu do sistema, sem parâmetros na "
            "URL, e envie de novo."
        )
    if excecao.dicionario == DICIONARIO_CABECALHO:
        return (
            f"Este formulário não usa o cabeçalho '{chaves}'. Reenvie sem esse "
            f"cabeçalho — ele não tem efeito nenhum aqui. {explicacao_extra}".strip()
        )
    return (
        f"Não reconheço o(s) campo(s) enviado(s): {chaves}. Nada foi gravado — um "
        "campo que esta tela não lê nunca é ignorado em silêncio."
    )


@login_required
@require_http_methods(["GET", "POST"])
@_sem_contabilidade_para_livro_caixa
def lancamento_novo(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite lançar nesta empresa.")

    # Só contas que aceitam lançamento direto e estão ativas entram na
    # lista de escolha — restringe o que a tela OFERECE para digitar, não
    # o que o Plano de Contas MOSTRA (essa tela continua listando tudo,
    # inclusive inativas: "não esconder informação contábil" é sobre
    # RELATÓRIO, não sobre a lista de opções de um formulário de entrada).
    contas_disponiveis = list(
        Conta.objects.filter(empresa=empresa, aceita_lancamento=True, ativo=True).order_by("codigo")
    )

    if request.method == "POST":
        # BL-196/R6-2 (rodada 6): UMA chamada, no lugar dos três `if`
        # escritos à mão que existiam aqui (e de nenhum em `conta_nova`).
        # A política é a de `apps.core.requisicao`, a ordem de avaliação é
        # a declarada lá (`ORDEM_DE_AVALIACAO`: arquivo, querystring,
        # cabeçalho, corpo) — a MESMA ordem em que esta view já recusava,
        # de propósito: a mensagem que o contador vê quando manda dois
        # erros de uma vez é comportamento observável, com teste em cima.
        #
        # Por que cada dicionário é recusado está no contrato
        # (`_contrato_do_formulario_de_lancamento`) e na tradução da
        # mensagem (`_mensagem_de_tela_para_dado_nao_contratado`), não
        # repetido aqui. O histórico dos achados que produziram cada um:
        # `request.FILES` = A3/BL-128 (um par de partidas completo e
        # balanceado enviado como campo de ARQUIVO sumia da tela, do total
        # e do aviso, e o resto gravava com 302 "sucesso"); `request.GET` e
        # o cabeçalho `Idempotency-Key` = R5-6/BL-145; campo desconhecido
        # no corpo = R6-2, que fechou na API e não na tela.
        try:
            recusar_dado_nao_contratado(
                request, _contrato_do_formulario_de_lancamento(request.POST)
            )
        except DadoNaoContratado as exc:
            return _recusa_lancamento_com_erro(
                request,
                empresa,
                contas_disponiveis,
                _mensagem_de_tela_para_dado_nao_contratado(
                    exc,
                    explicacao_extra=(
                        "O campo oculto do próprio formulário já garante que "
                        "reenviar a mesma tentativa não duplica o lançamento."
                    ),
                ),
            )

        acao = request.POST.get("acao")
        # A1/rodada 4 — mesma varredura: `num_linhas` é texto de
        # cliente virando `int()`, então passa por `_inteiro_de_cliente`
        # como qualquer outro campo deste arquivo (ver o docstring dela) —
        # nunca reinterpreta dígito Unicode, nunca lança exceção. Ausente
        # ou malformado cai no padrão de linhas iniciais, do mesmo jeito
        # que o `try/except` anterior já fazia — só que agora sem precisar
        # de uma cláusula `except` com mais de um tipo (a sintaxe que deu
        # origem ao R3-4/BL-118 nem chega a existir aqui).
        num_linhas_campo = _inteiro_de_cliente(request.POST.get("num_linhas", ""))
        if num_linhas_campo is None:
            num_linhas_campo = LINHAS_INICIAIS_LANCAMENTO

        data_texto = request.POST.get("data", "")
        historico = request.POST.get("historico", "").strip()
        # Idempotência (BL-43 / critério 11): o MESMO token acompanha toda
        # esta tentativa — inclusive um duplo clique, que envia duas
        # requisições com o MESMO corpo (o mesmo campo oculto), sem
        # depender de JavaScript nenhum. `criar_lancamento` (services.py)
        # já sabe devolver o MESMO lançamento em vez de duplicar quando o
        # conteúdo bate (ver o docstring de `criar_lancamento`).
        chave_idempotencia = request.POST.get("chave_idempotencia") or uuid.uuid4().hex

        # R3-1 (rodada 3, BL-115, BLOQUEADOR — "um POST prende a
        # requisição indefinidamente"): `num_linhas_campo` vem de um campo
        # OCULTO do formulário — o cliente controla o valor por completo
        # (um clique no inspetor do navegador). ANTES desta correção, um
        # `num_linhas` grande o bastante (`10**12`, `"9" * 4000`)
        # sobrevivia ao `int()` (o único limite era o de CONVERSÃO do
        # próprio Python, 4300 dígitos) e se propagava, via `max()`, para
        # `num_linhas_exibicao` e depois para `num_linhas_leitura` — SEM
        # NUNCA passar pelo teto de segurança, porque aquele teto só
        # capava o valor DERIVADO do conteúdo do POST, nunca o campo
        # oculto em si. O resultado era um `range()` dimensionado por um
        # inteiro arbitrário do cliente, nos DOIS ramos (`gravar` e
        # `adicionar_linha`) — 26 s de bloqueio medidos para 10 milhões, e
        # NENHUM retorno em 45 s para `10**12`. Com `gunicorn` sem
        # `--workers` (um único *worker* síncrono, o mesmo comando do
        # `docker-compose.yml` — o caminho pelo qual o Fred sobe o
        # sistema), um único POST autenticado deixa o sistema inteiro sem
        # resposta: não corrompe dado, **nega o serviço**.
        #
        # A classe (não só o caso): nenhum número vindo do cliente
        # dimensiona laço, alocação ou repetição nesta view — em NENHUM
        # ramo. A correção é recusar ANTES DE QUALQUER LEITURA, nos dois
        # ramos ao mesmo tempo (este `if` roda antes do `if acao ==
        # "adicionar_linha"` abaixo): nenhum valor vindo do cliente chega
        # perto de um `max()`, um `min()` ou um `range()` sem primeiro
        # passar por este teto.
        if num_linhas_campo > LINHAS_LEITURA_TETO_DE_SEGURANCA:
            messages.error(
                request,
                "'num_linhas' inválido: o formulário aceita no máximo "
                f"{LINHAS_MAXIMAS_LANCAMENTO} partidas por lançamento.",
            )
            # R6-5/BL-199, segunda rodada da DL-020: o número de linhas
            # re-exibidas vem do PONTO ÚNICO de derivação, como em toda
            # recusa desta tela. Era `LINHAS_INICIAIS_LANCAMENTO` fixo, e
            # perdia o que estivesse digitado além da quarta linha —
            # mesmo defeito do achado R6-5, no caminho vizinho. Derivar do
            # conteúdo é seguro aqui justamente porque
            # `_linhas_a_reexibir_do_post` NÃO olha o campo oculto: é o
            # `num_linhas` absurdo que acabou de ser recusado, e ele não
            # pode dimensionar a página (R3-1/BL-115).
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                _linhas_a_reexibir_do_post(request.POST),
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        # `num_linhas_campo` (o campo OCULTO do formulário) decide só
        # quantas linhas a tela EXIBE de volta a partir de agora — NUNCA
        # mais quantas linhas são LIDAS do POST (ver abaixo). Piso de 2 é
        # só para exibição, não afeta leitura. Já garantidamente dentro do
        # teto de segurança pela recusa acima.
        num_linhas_exibicao = max(2, num_linhas_campo)

        # R2-3 (rodada 2) + R3-2/BL-116 (rodada 3): a quantidade REAL de
        # linhas a LER vem do próprio CONTEÚDO do POST
        # (`_indices_de_linha_do_post`), nunca só do campo oculto — um
        # `num_linhas` malformado, vazio ou menor do que o conteúdo real
        # não pode fazer esta view ler MENOS campos do que os que o
        # cliente de fato enviou (R2-3). E QUALQUER chave
        # `conta_*`/`tipo_*`/`valor_*` fora do índice CANÔNICO (ver o
        # docstring daquela função) é RECUSADA, nunca ignorada (R3-2): era
        # assim que um par de linhas completo (débito e crédito batendo
        # entre si) desaparecia em silêncio, com HTTP 302 "gravado com
        # sucesso", quando o índice tinha zero à esquerda, sinal, espaço
        # ou 5+ dígitos.
        maior_indice, chaves_nao_canonicas = _indices_de_linha_do_post(request.POST)
        if chaves_nao_canonicas:
            messages.error(
                request,
                "Não entendi os seguintes campos do formulário — índice de "
                "linha fora do formato esperado, nunca reinterpretado nem "
                "ignorado: " + "; ".join(sorted(chaves_nao_canonicas)) + ".",
            )
            # R6-5/BL-199, segunda rodada da DL-020: era
            # `num_linhas_exibicao` — derivado do campo OCULTO, sem o maior
            # índice realmente presente —, e MEDIDO perdendo as linhas 5 a
            # 8 de um POST com oito linhas e `num_linhas=4`. É o defeito do
            # achado R6-5 no caminho vizinho de dentro da mesma view
            # (DE-034, item 1). Agora o mesmo ponto único de derivação de
            # toda recusa desta tela.
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                _linhas_a_reexibir_do_post(request.POST),
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        num_linhas_leitura = max(num_linhas_exibicao, maior_indice)

        contas_por_id = {conta.id: conta for conta in contas_disponiveis}

        if acao == "adicionar_linha":
            # Só acrescenta uma linha em branco e re-renderiza — NUNCA
            # grava nada. É a forma de a tela funcionar sem JavaScript
            # (critério 15): cada "+ linha" é um novo GET/POST normal.
            num_linhas_exibicao = min(num_linhas_exibicao + 1, LINHAS_MAXIMAS_LANCAMENTO)
            num_linhas_leitura = max(num_linhas_leitura, num_linhas_exibicao)
            # Achado 3 / BL-88 (rodada 1) + R2-3/R2-5 (rodada 2): as linhas
            # JÁ enviadas neste POST alimentam o MESMO cálculo de totais
            # que "gravar" usa (`_itens_e_totais`) — "Adicionar linha" é o
            # único botão de conferência que esta tela tem sem JavaScript.
            # Lê TODAS as linhas realmente presentes no POST
            # (`num_linhas_leitura`, não só as que serão re-exibidas): uma
            # linha preenchida além do que a página mostra de volta não
            # pode desaparecer do total sem aviso. R2-5: os erros desta
            # extração (linha incompleta, conta/valor inválidos) não são
            # mais descartados em silêncio — a CONTAGEM de quantas linhas
            # ficaram fora do total é anunciada na tela
            # (`linhas_excluidas_do_total`, no contexto e no template):
            # antes, o rodapé podia mostrar dois valores "batendo" que
            # ignoravam, sem uma palavra, uma linha preenchida ao lado —
            # e "batendo" é exatamente o sinal que convida a gravar.
            linhas_brutas, erros_incompletas = _linhas_lancamento_do_post(
                request.POST, num_linhas_leitura
            )
            itens_conf, erros_itens_conf, total_debito, total_credito = _itens_e_totais(
                linhas_brutas, contas_por_id
            )
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                num_linhas_exibicao,
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
                total_debito=total_debito,
                total_credito=total_credito,
                linhas_excluidas_do_total=len(erros_incompletas) + len(erros_itens_conf),
                # BL-289: quantas partidas VÁLIDAS entraram na soma acima —
                # o veredito "fecha"/"nao_fecha" exige pelo menos duas,
                # mesma exigência de `criar_lancamento` mais abaixo.
                num_partidas_validas=len(itens_conf),
            )
            return render(request, "contabilidade/lancamento_form.html", contexto)

        # Qualquer outro valor de 'acao' (normalmente "gravar") é tratado
        # como tentativa de gravação — nunca perde silenciosamente o que
        # foi digitado.
        if num_linhas_leitura > LINHAS_MAXIMAS_LANCAMENTO:
            # Achado 5 / BL-91 (rodada 1) + R2-3 (rodada 2): recusa o POST
            # inteiro — nunca processa só as primeiras
            # LINHAS_MAXIMAS_LANCAMENTO e descarta o resto em silêncio. A
            # comparação usa `num_linhas_leitura` (derivado do CONTEÚDO
            # real do POST) — não o campo oculto: um `num_linhas`
            # malformado ou reduzido não pode abrir, por baixo, a mesma
            # porta que um `num_linhas` inflado já não abre mais por cima.
            # Era exatamente por cima que um lote de 22 partidas (as 20
            # primeiras batendo, e as 2 últimas TAMBÉM batendo entre si)
            # fechava com "sucesso" perdendo 77,00 de débito e 77,00 de
            # crédito — perda silenciosa de fato contábil que nenhuma
            # conferência posterior aponta porque o que sobrou também
            # fecha balanceado. Em escrituração: recusa, nunca ajusta.
            #
            # R2-10 (rodada 2): a recusa não pode SOMAR uma segunda perda
            # à primeira — a tela volta a exibir só as primeiras
            # LINHAS_MAXIMAS_LANCAMENTO linhas (exibir todas as enviadas
            # deixaria esta view renderizar uma página proporcional a
            # quantas linhas um POST arbitrário mandasse), mas os valores
            # das linhas que excederam o teto são repetidos na própria
            # MENSAGEM de recusa, para que copiá-los para um segundo
            # lançamento não dependa de o contador tê-los memorizado.
            linhas_excedentes, _ = _linhas_lancamento_do_post(request.POST, num_linhas_leitura)
            linhas_excedentes = [
                linha for linha in linhas_excedentes if linha["indice"] > LINHAS_MAXIMAS_LANCAMENTO
            ]
            mensagem = (
                f"Este formulário aceita no máximo {LINHAS_MAXIMAS_LANCAMENTO} partidas "
                f"por lançamento; foram enviadas {num_linhas_leitura}. Nada foi gravado. "
                "Copie os dados abaixo para um segundo lançamento, ou peça ao "
                "administrador do escritório para avaliar um teto maior."
            )
            if linhas_excedentes:
                resumo = "; ".join(
                    f"linha {linha['indice']} ({linha['tipo'] or '?'}, "
                    f"{linha['valor_texto'] or '?'})"
                    for linha in linhas_excedentes
                )
                mensagem += f" Linhas que não couberam: {resumo}."
            messages.error(request, mensagem)
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                LINHAS_MAXIMAS_LANCAMENTO,
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

        linhas_brutas, erros = _linhas_lancamento_do_post(request.POST, num_linhas_leitura)
        # BL-307 (A1 da auditoria DL-026 rodada 3): contagem separada, ANTES
        # de `erros` receber qualquer mensagem que não seja sobre uma LINHA
        # descartada (histórico grande demais, chave de idempotência grande
        # demais) — essas duas não excluem partida nenhuma do total, e
        # somá-las aqui inflaria `linhas_excluidas_do_total` com motivo que
        # não é "linha fora da soma". O aviso R2-5 ("N linha(s) … ainda NÃO
        # entram no total abaixo") e o veredito "Fecha" (`_veredito_
        # fechamento`) dependem deste número estar certo NESTA MESMA
        # resposta — não só no ramo "adicionar_linha" (ver o comentário
        # abaixo, onde o valor é finalmente passado a `_contexto_form_
        # lancamento`).
        linhas_incompletas = len(erros)

        # Achado 4 / BL-90: mesmo teto do modelo (`historico =
        # CharField(max_length=300)`) verificado AQUI, antes de qualquer
        # tentativa de gravação — sem isto, o único guarda era o
        # `maxlength="300"` do HTML (proteção de NAVEGADOR, nunca de
        # servidor — AGENTS.md §1), e um POST direto com histórico maior
        # chegava ao INSERT do Postgres como `DataError: value too long
        # for type character varying(300)`, um 500 cru. O formulário de
        # conta é `ModelForm` e o Django já cuida disto sozinho; este é o
        # único formulário escrito à mão da entrega, e por isso o único
        # que precisa desta checagem explícita.
        if len(historico) > TAMANHO_MAXIMO_HISTORICO:
            erros.append(f"O histórico não pode ter mais de {TAMANHO_MAXIMO_HISTORICO} caracteres.")

        # Mesma classe de defeito dos achados 1 e 4, encontrada na
        # varredura desta rodada (critério de aceite 1): `chave_
        # idempotencia` é um campo OCULTO do formulário (o navegador nunca
        # o alonga sozinho), mas nada nesta view impedia um POST direto com
        # um valor maior que `LancamentoContabil.chave_idempotencia`
        # (CharField max_length=255) — reproduzido e confirmado
        # (`DataError: value too long for type character varying(255)`, um
        # 500 cru) antes desta correção. A API já tem o mesmo limite
        # (`TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA`, views.py); aqui é o mesmo
        # valor, reaproveitado, não duplicado.
        if len(chave_idempotencia) > TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA:
            erros.append(
                "A chave de idempotência não pode ter mais de "
                f"{TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA} caracteres."
            )

        itens, erros_itens, total_debito, total_credito = _itens_e_totais(
            linhas_brutas, contas_por_id
        )
        erros = erros + erros_itens
        # BL-307: as duas fontes de linha EXCLUÍDA da soma — incompleta
        # (`linhas_incompletas`, capturada acima) e inválida (`erros_itens`,
        # que acabou de sair de `_itens_e_totais`) — exatamente a mesma
        # conta que "adicionar_linha" já passa (`len(erros_incompletas) +
        # len(erros_itens_conf)`, mais acima nesta view). Antes desta
        # correção este ramo não calculava nada e `_contexto_form_
        # lancamento` recebia o padrão `linhas_excluidas_do_total=0` —
        # fazendo o veredito "Fecha" aparecer numa resposta 400 sempre que
        # débito e crédito das linhas VÁLIDAS batiam, mesmo com uma linha
        # descartada ao lado (A1 da auditoria DL-026 rodada 3).
        linhas_excluidas_do_total = linhas_incompletas + len(erros_itens)

        # R5-4/BL-143: mesmo julgador partilhado do período (ver o
        # comentário de `_periodo_do_formulario`) — `para_data`, nunca a
        # cópia privada nem `date.fromisoformat` cru.
        data_lancamento = None
        try:
            data_lancamento = para_data(data_texto or "")
        except DataInvalida:
            erros.append("Informe uma data válida.")

        totais_batem = total_debito == total_credito and total_debito > 0

        # Critério 10: a tela mostra os dois totais e IMPEDE o envio
        # enquanto forem diferentes. Quem garante isto DE VERDADE é
        # `criar_lancamento` abaixo (a validação do servidor) — esta
        # checagem aqui é só conveniência, e o teste do critério 10 POSTa
        # direto para esta view com débito != crédito para provar que,
        # mesmo que ESTA checagem não existisse, nenhum lançamento seria
        # gravado.
        if not erros and len(itens) >= 2 and totais_batem and data_lancamento is not None:
            try:
                # BL-14 (DL-024): o `with transaction.atomic()` envolve
                # tanto a chamada a `criar_lancamento` quanto o `registrar()`
                # da trilha. Antes, qualquer falha no INSERT do
                # `RegistroAuditoria` deixava o lançamento gravado e a
                # trilha silenciosamente vazia — o Diário dizia uma coisa,
                # a trilha dizia outra. O `transaction.atomic()` é
                # REENTRANTE: o serviço `criar_lancamento` é
                # `@transaction.atomic` por si, e o aninhamento resulta em
                # savepoint, e a falha do `registrar()` reverte o savepoint
                # E o commit do `criar_lancamento` que ainda não subiu.
                with transaction.atomic():
                    try:
                        lancamento = criar_lancamento(
                            empresa=empresa,
                            data=data_lancamento,
                            historico=historico,
                            itens=itens,
                            criado_por=request.user,
                            chave_idempotencia=chave_idempotencia,
                        )
                    except ChaveIdempotenciaConflitante as exc:
                        erros.append(str(exc))
                    except CompetenciaEncerrada as exc:
                        # BL-457/A2 (rodada 2 de auditoria): `CompetenciaEncerrada`
                        # é subclasse direta de `Exception`, DELIBERADAMENTE não
                        # de `LancamentoInvalido` (ver o docstring dela em
                        # services.py) — e por isso o `except LancamentoInvalido`
                        # logo abaixo nunca a capturava. Pela DE-026 não há API
                        # separada atrás desta tela: ela chama `criar_lancamento`
                        # direto, então sem este `except` a exceção escapava até
                        # o middleware de erro do Django e virava HTTP 500 — uma
                        # página de erro genérica no lugar da mensagem de negócio
                        # que o serviço já produz pronta (nomeando a competência
                        # e orientando a reabrir ou lançar em mês aberto). Nada
                        # era gravado (a trava funcionava); só a APRESENTAÇÃO da
                        # recusa quebrava. Medido com controle positivo: o MESMO
                        # POST com o mês aberto grava (302); só a competência
                        # fechada produzia o 500.
                        erros.append(str(exc))
                    except LancamentoInvalido as exc:
                        erros.append(str(exc))
                    else:
                        # O serviço informa se de fato criou ou reaproveitou um
                        # lançamento existente (mesma Idempotency-Key) — a trilha
                        # de auditoria e a mensagem precisam refletir o resultado
                        # real (mesmo cuidado da API, ver views.py).
                        if lancamento.criado_agora:
                            registrar(acao="lancamento.criado", objeto=lancamento, request=request)
                            messages.success(request, "Lançamento gravado com sucesso.")
                        else:
                            registrar(
                                acao="lancamento.criacao_repetida",
                                objeto=lancamento,
                                request=request,
                                detalhes={
                                    "chave_idempotencia_hash": hashlib.sha256(
                                        chave_idempotencia.encode("utf-8")
                                    ).hexdigest()[:12]
                                },
                            )
                            messages.info(
                                request,
                                "Este lançamento já havia sido gravado (nova tentativa com o "
                                "mesmo envio, sem duplicar).",
                            )
                        return redirect(
                            "contabilidade_web:lancamento_detalhe",
                            empresa_id=empresa.id,
                            lancamento_id=lancamento.id,
                        )
            except IntegrityError:
                # Defesa residual: se uma constraint que não foi prevista
                # levantar aqui (mudança de modelo, regressão), a operação
                # inteira — `criar_lancamento` + trilha — reverte junta, e
                # o usuário vê o erro em vez de acreditar num sucesso falso.
                erros.append("Não foi possível concluir a gravação do lançamento.")
        elif not erros:
            if len(itens) < 2:
                erros.append("Informe ao menos duas partidas.")
            elif total_debito != total_credito:
                # BL-298 (M7 da auditoria DL-026 rodada 2): esta frase só
                # cabe quando os totais REALMENTE divergem — mantida como
                # estava.
                erros.append(
                    f"Débitos ({_valor_ptbr(total_debito)}) e créditos "
                    f"({_valor_ptbr(total_credito)}) precisam ser iguais antes de gravar."
                )
            else:
                # `total_debito == total_credito` mas `not totais_batem`:
                # só resta a outra metade da condição, `total_debito <= 0`
                # (zero ou negativo). A frase de divergência MENTIRIA aqui
                # — os dois lados SÃO iguais — e foi exatamente o que o
                # auditor mediu: "gravar" com 0,00/0,00 respondia "Débitos
                # (0,00) e créditos (0,00) precisam ser iguais", quando o
                # problema real é não terem valor positivo nenhum. Frase
                # própria, que diz o que fazer.
                erros.append(
                    "O total do lançamento precisa ser maior que zero antes de gravar — "
                    "informe um valor positivo nas partidas."
                )

        for erro in erros:
            messages.error(request, erro)

        # BL-307: as TRÊS condições que bloqueiam `criar_lancamento` mas não
        # têm relação com débito, crédito, partida válida nem linha
        # excluída (ver o docstring de `_veredito_fechamento`, quinta
        # condição). Sem isto, um histórico grande demais, uma chave de
        # idempotência grande demais ou uma data inválida — com as duas
        # partidas restantes batendo perfeitamente — ainda fazia o veredito
        # dizer "Fecha" nesta MESMA resposta 400 (os dois últimos casos da
        # reprodução do achado A1: "histórico de 400 caracteres" e "data
        # 'abacaxi'", nenhum dos dois descarta uma linha, então a correção
        # de `linhas_excluidas_do_total` sozinha não bastava).
        # BL-318 (A1 da rodada 4): a enumeração acima estava ERRADA DE LUGAR,
        # não de conteúdo. As três condições eram as três que ESTA VIEW checa
        # antes de chamar o serviço; `criar_lancamento` tem DEZESSETE `raise`
        # próprios — faixa de data do RC-77, escala, byte nulo, conta que não
        # aceita lançamento, teto de partidas, conflito de idempotência — e
        # nenhum deles passava por aqui. Medido pelo auditor: quatro POSTs com
        # as duas partidas batendo devolviam 400 com "Fecha" EM VERDE, e o
        # primeiro deles é a data fora da faixa: quem digita 1999 em vez de
        # 2019 lia "Fecha" por cima da mensagem que recusou a data.
        #
        # Uma sexta condição enumerada não resolve — a lista de motivos de
        # recusa cresce. A afirmação verdadeira é estrutural e não envelhece:
        #
        #     esta resposta é 400, logo NÃO GRAVOU, logo nada está conferido.
        #
        # `"nao_fecha"` não depende desta bandeira, então divergência real
        # continua sendo anunciada com o valor da diferença.
        bloqueado_por_outro_erro = True

        contexto = _contexto_form_lancamento(
            empresa,
            contas_disponiveis,
            num_linhas_leitura,
            data_texto=data_texto,
            historico=historico,
            chave_idempotencia=chave_idempotencia,
            linhas_preenchidas=request.POST,
            total_debito=total_debito,
            total_credito=total_credito,
            # BL-289: mesma contagem de partidas válidas que decidiu se
            # `criar_lancamento` seria chamado acima — o rodapé desta
            # mesma resposta (400) precisa refletir a MESMA decisão, nunca
            # uma cópia que possa divergir.
            num_partidas_validas=len(itens),
            # BL-307: idem, para a contagem de linhas EXCLUÍDAS — sem isto
            # o padrão da assinatura (`linhas_excluidas_do_total=0`) fazia
            # `_veredito_fechamento` achar que nenhuma linha tinha sido
            # descartada nesta resposta, mesmo quando `linhas_excluidas_do_
            # total` (calculada acima) fosse maior que zero.
            linhas_excluidas_do_total=linhas_excluidas_do_total,
            bloqueado_por_outro_erro=bloqueado_por_outro_erro,
        )
        return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

    # GET: formulário em branco, com uma chave de idempotência NOVA para
    # esta tentativa (critério 11 — cada visita "limpa" ao formulário é uma
    # tentativa distinta).
    contexto = _contexto_form_lancamento(
        empresa,
        contas_disponiveis,
        LINHAS_INICIAIS_LANCAMENTO,
        data_texto=timezone.localdate().isoformat(),
        historico="",
        chave_idempotencia=uuid.uuid4().hex,
    )
    return render(request, "contabilidade/lancamento_form.html", contexto)


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def lancamento_detalhe(request, empresa_id, lancamento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    lancamento = get_object_or_404(
        LancamentoContabil.objects.prefetch_related("itens__conta"),
        pk=lancamento_id,
        empresa=empresa,
    )

    itens = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for item in lancamento.itens.all():
        if item.tipo == TipoPartida.DEBITO:
            total_debito += item.valor
        else:
            total_credito += item.valor
        itens.append(
            {"conta": item.conta, "tipo": item.tipo, "valor_ptbr": _valor_ptbr(item.valor)}
        )

    contexto = {
        "empresa": empresa,
        "lancamento": lancamento,
        "itens": itens,
        "total_debito_ptbr": _valor_ptbr(total_debito),
        "total_credito_ptbr": _valor_ptbr(total_credito),
    }
    return render(request, "contabilidade/lancamento_detalhe.html", contexto)


# ---------------------------------------------------------------------------
# BL-198 (b) / R6-4 — "há movimento fora do período consultado"
#
# É o item que fez a DL-020 existir, e o único achado aberto com esta
# característica: **o usuário não consegue conferir o que não aparece.** O
# auditor mediu um lançamento de 5.000,00 datado `9999-12-31` (um `9`
# digitado no lugar de `2`) ao lado de um de 100,00 de hoje:
#
#     Diário      (período padrão): mostra 5.000,00? False | avisa? False
#     Balancete   (período padrão): mostra 5.000,00? False | avisa? False
#     Razão       (período padrão): mostra 5.000,00? False | avisa? False
#     Conferência (sem período)   : mostra 5.000,00? False
#     total real de débito na base: 10.200,00
#
# O balancete do período **concilia** — é por isso que nenhuma conferência
# aponta. Para encontrar, o contador precisava suspeitar e alargar o
# período até o ano 9999.
#
# A faixa do RC-77 (BL-205) fecha a PORTA de entrada. Este aviso é a REDE
# embaixo dela, e continua necessário depois de a porta fechar, por três
# motivos: dado já gravado antes da regra não se conserta validando a
# entrada (está fora do escopo desta etapa); a faixa permite datas
# legítimas fora do período consultado (é o caso comum — o contador olha
# setembro e existe movimento de outubro); e há portas de escrita que não
# passam pela tela (o admin do Django, por exemplo).
#
# A consulta é de `services.py` (`movimento_fora_do_periodo`), UMA fonte;
# esta função só monta a apresentação e o caminho de correção — o link que
# ALARGA o período até incluir o que está fora, preservando os outros
# parâmetros da tela (o `nivel` do Balancete, por exemplo).
# ---------------------------------------------------------------------------


def _aviso_de_movimento_fora_do_periodo(
    request, empresa, inicio, fim, *, conta=None, ids_contas=None
):
    """Contexto do aviso, ou `None` quando não há nada fora do período.

    Os dois parâmetros do Razão têm papéis DIFERENTES, e é por isso que ele
    passa os dois (BL-212):

    - `ids_contas` é o que CONSULTA: o conjunto de contas já apurado por
      `apurar_razao` (chave `ids_contas` do resultado), reaproveitado para o
      aviso recortar pelo MESMO conjunto que a tela está somando sem
      percorrer a subárvore uma segunda vez — `_descendentes_de` faz uma
      consulta por nível de profundidade, e recomputá-lo aqui dobrava esse
      custo e estourava o teto de consultas do Razão.
    - `conta` é o que APRESENTA: a chave `"conta"` do contexto é a única
      coisa que faz o parcial dizer "esta conta (incluindo as subordinadas)"
      em vez de "esta empresa". Nenhuma consulta depende dela quando
      `ids_contas` vem, e o link que alarga o período também não — ele sai de
      `request.path` mais os parâmetros da tela.

    Sem nenhum dos dois, o recorte é a empresa inteira (Diário, Balancete).
    Com `conta` sem `ids_contas`, `movimento_fora_do_periodo` ainda recorta
    pela subárvore — pagando a travessia; nenhuma tela faz isso hoje.
    """
    fora = movimento_fora_do_periodo(
        empresa=empresa, inicio=inicio, fim=fim, conta=conta, ids_contas=ids_contas
    )
    if not fora:
        return None
    anteriores = fora.get("anteriores")
    posteriores = fora.get("posteriores")
    datas_extremas = [
        lado["data_extrema"] for lado in (anteriores, posteriores) if lado is not None
    ]
    # O link precisa ALARGAR, nunca substituir: quem está vendo setembro e
    # tem movimento em outubro deve continuar vendo setembro no resultado.
    inicio_ampliado = min([inicio, *datas_extremas])
    fim_ampliado = max([fim, *datas_extremas])
    parametros = request.GET.copy()
    parametros["inicio"] = inicio_ampliado.isoformat()
    parametros["fim"] = fim_ampliado.isoformat()
    return {
        "anteriores": anteriores,
        "posteriores": posteriores,
        "conta": conta,
        "inicio_ampliado": inicio_ampliado,
        "fim_ampliado": fim_ampliado,
        "url_ampliada": f"{request.path}?{parametros.urlencode()}",
    }


# ---------------------------------------------------------------------------
# Diário
# ---------------------------------------------------------------------------


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def diario(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    contexto = {"empresa": empresa, "inicio": inicio, "fim": fim}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/diario.html", contexto, status=400)

    lotes = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for lancamento in listar_diario(empresa=empresa, inicio=inicio, fim=fim):
        debito_lote = Decimal("0")
        credito_lote = Decimal("0")
        for item in lancamento.itens.all():
            if item.tipo == TipoPartida.DEBITO:
                debito_lote += item.valor
            else:
                credito_lote += item.valor
        total_debito += debito_lote
        total_credito += credito_lote
        lotes.append(
            {
                "lancamento": lancamento,
                "debito_ptbr": _valor_ptbr(debito_lote),
                "credito_ptbr": _valor_ptbr(credito_lote),
            }
        )

    contexto.update(
        {
            "lotes": lotes,
            "total_debito_ptbr": _valor_ptbr(total_debito),
            "total_credito_ptbr": _valor_ptbr(total_credito),
            # BL-198 (b): ver o comentário da função.
            "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                request, empresa, inicio, fim
            ),
            # BL-282: linhas do timbre do ESCRITÓRIO da empresa consultada
            # (nunca de outro — `empresa` já veio filtrada por
            # `escritorio=request.escritorio` em `_empresa_do_escritorio_
            # ativo`, então `empresa.escritorio` É o escritório ativo da
            # sessão). Sai "de graça" nesta tela pelo mesmo contrato do
            # Balancete (`Escritorio.linhas_do_timbre`), sem lógica de
            # fallback duplicada aqui — ver o docstring da property.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/diario.html", contexto)


# ---------------------------------------------------------------------------
# Razão
# ---------------------------------------------------------------------------


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def razao(request, empresa_id, conta_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )
    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    contexto = {"empresa": empresa, "conta": conta, "inicio": inicio, "fim": fim}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/razao.html", contexto, status=400)

    try:
        apuracao = apurar_razao(conta=conta, empresa=empresa, inicio=inicio, fim=fim)
    except HierarquiaInconsistente as exc:
        # Ciclo ou conta_pai de outra empresa: resposta controlada,
        # nomeando a conta, nunca um 500 mudo (mesmo tratamento da API).
        messages.error(request, str(exc))
        return render(request, "contabilidade/razao.html", contexto, status=409)

    # BL-198 (b) + BL-212: DEPOIS da apuração e FORA do `try`, de propósito.
    # Esta chamada já não percorre a hierarquia — ela reaproveita o conjunto
    # de contas que a apuração acabou de percorrer (`apuracao["ids_contas"]`),
    # então não há mais `HierarquiaInconsistente` a tratar aqui; o que a
    # protege é depender de `apuracao`, que só existe quando o plano está
    # consistente. Antes da BL-212 ela recomputava `_descendentes_de` (uma
    # consulta por NÍVEL de profundidade), dobrando o custo do Razão de um
    # plano profundo e estourando o teto de consultas. `conta` continua
    # sendo passada, mas só para a APRESENTAÇÃO: é a chave "conta" do
    # contexto, e é só ela que faz o aviso dizer "esta conta (incluindo as
    # subordinadas)" em vez de "esta empresa". O link que alarga o período
    # não depende dela — ele nasce de `request.path`, que no Razão já traz o
    # `conta_id`.
    aviso_fora_do_periodo = _aviso_de_movimento_fora_do_periodo(
        request, empresa, inicio, fim, conta=conta, ids_contas=apuracao["ids_contas"]
    )

    itens = []
    for linha in apuracao["itens"]:
        saldo_abs, saldo_nat = _saldo_absoluto_com_natureza(linha["saldo"], conta.natureza)
        itens.append(
            {
                "lancamento_id": linha["lancamento_id"],
                "data": linha["data"],
                "historico": linha["historico"],
                "conta_codigo": linha["conta"],
                "conta_nome": linha["conta_nome"],
                "tipo": linha["tipo"],
                "valor_ptbr": _valor_ptbr(linha["valor"]),
                "saldo_ptbr": _valor_ptbr(saldo_abs),
                "saldo_natureza": _indicador_natureza(saldo_nat),
            }
        )

    saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_anterior"], conta.natureza
    )
    saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_final"], conta.natureza
    )

    contexto.update(
        {
            "consolidado": apuracao["consolidado"],
            "itens": itens,
            "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
            "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
            "total_debito_ptbr": _valor_ptbr(apuracao["total_debito"]),
            "total_credito_ptbr": _valor_ptbr(apuracao["total_credito"]),
            "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
            "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
            "movimento_fora_do_periodo": aviso_fora_do_periodo,
            # BL-282: mesmo contrato do Balancete e do Diário — ver o
            # comentário em `diario`.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/razao.html", contexto)


# ---------------------------------------------------------------------------
# Balancete (critério 6)
# ---------------------------------------------------------------------------


def _veredito_balancete(total_debitos, total_creditos):
    """Decide, em `Decimal`, um de três estados — `"fecha"`, `"nao_fecha"`
    ou `"nada_a_conferir"` — para a faixa de fechamento no topo do
    balancete (`total_debitos`/`total_creditos`: as colunas "próprios" do
    PERÍODO, DE-024 §2 — as mesmas que já alimentam `total_debitos_ptbr`/
    `total_creditos_ptbr`).

    BL-290 (A2 da auditoria DL-026 rodada 2): o TEMPLATE decidia sozinho,
    comparando `total_debitos_ptbr == total_creditos_ptbr` — texto pt-BR,
    não `Decimal` (a mesma classe de defeito do BL-289/A1, só que na tela
    do balancete). Além de comparar texto, o ramo "Fecha" cobria também o
    caso `0,00 == 0,00` sem NENHUM movimento no período — o estado em que a
    tela abre no dia 1º de todo mês (BL-302/B4) —, mostrando um "Fecha"
    verde sobre nada. Um sinal que aparece sempre deixa de ser sinal.

    `"nada_a_conferir"`: os dois totais são zero — não há o que fechar
    neste período (sem movimento próprio nenhum). `"fecha"`: os totais
    batem E há movimento (pelo menos um dos dois maior que zero — na
    prática os dois, porque toda partida tem os dois lados). `"nao_fecha"`:
    os totais DIVERGEM.

    Por construção de partidas dobradas — todo lançamento EFETIVADO tem
    débito igual a crédito (`apps.contabilidade.services.criar_lancamento`)
    —, a soma de todos os débitos próprios do período sempre bate com a
    soma de todos os créditos próprios, salvo CORRUPÇÃO de dado. O ramo
    `"nao_fecha"` é, por isso, rede de segurança: hoje inalcançável em uso
    normal do produto (nenhum caminho de escrita deixa os totais
    divergirem), mas é exatamente no dia em que algo corromper o dado que
    esta tela precisa gritar — e uma rede que ninguém nunca viu funcionar
    não é rede (ver o teste que força a divergência via
    `monkeypatch.setattr(views_web, "apurar_balancete", ...)`, já que não
    existe caminho de escrita real para produzi-la).
    """
    if total_debitos == 0 and total_creditos == 0:
        return "nada_a_conferir"
    if total_debitos == total_creditos:
        return "fecha"
    return "nao_fecha"


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def balancete(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    nivel, erro_nivel = _nivel_do_formulario(request)
    criterio, erro_criterio = _criterio_de_apuracao_do_formulario(request)
    # DL-027 Fatia B.3: carimbo de data e hora da emissão — capturado
    # AQUI (não no template) para garantir que toda renderização da
    # mesma request use o mesmo timestamp, e que a string pt-BR seja
    # produzida uma única vez pela camada Python. `timezone.localtime()`
    # devolve o instante atual no fuso de `settings.TIME_ZONE`
    # ("America/Sao_Paulo"), não em UTC — é o que o usuário vê no
    # relógio dele.
    carimbo_de_emissao = timezone.localtime()
    contexto = {
        "empresa": empresa,
        "inicio": inicio,
        "fim": fim,
        "nivel": nivel,
        "criterio_de_apuracao": criterio,
        "criterio_de_apuracao_texto": _TEXTO_DO_CRITERIO[criterio],
        "criterio_de_apuracao_opcoes": sorted(_CRITERIOS_DE_APURACAO_VALIDOS),
        "carimbo_de_emissao": carimbo_de_emissao,
        "carimbo_de_emissao_texto": carimbo_de_emissao.strftime("%d/%m/%Y às %H:%M:%S"),
    }
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/balancete.html", contexto, status=400)
    if erro_nivel:
        messages.error(request, erro_nivel)
        return render(request, "contabilidade/balancete.html", contexto, status=400)
    if erro_criterio:
        messages.error(request, erro_criterio)
        return render(request, "contabilidade/balancete.html", contexto, status=400)

    try:
        apuracao = apurar_balancete(
            empresa=empresa,
            inicio=inicio,
            fim=fim,
            nivel=nivel,
            criterio_de_apuracao=criterio,
        )
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(
            request,
            "contabilidade/balancete_emissao_recusada.html",
            {"empresa": empresa},
            status=409,
        )

    # Necessário só para montar o link "ver Razão desta conta" (critério
    # 12): `apurar_balancete` devolve o CÓDIGO da conta (é o que o
    # contador lê), não o id interno que a URL do Razão precisa. Uma única
    # consulta, fora do laço — não é N+1.
    ids_por_codigo = dict(Conta.objects.filter(empresa=empresa).values_list("codigo", "id"))

    linhas = []
    for linha in apuracao["contas"]:
        saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
            linha["saldo_anterior"], linha["natureza"]
        )
        saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
            linha["saldo_final"], linha["natureza"]
        )
        # BL-281: `linha["natureza"]` É a natureza CADASTRADA da conta desta
        # linha (`Conta.natureza`, não o sinal computado do saldo) — provado
        # pelo comentário de origem em
        # apps/contabilidade/services.py:1088-1099 (`apurar_balancete`):
        # "Natureza CADASTRADA da conta (`Conta.natureza`) — exposta aqui só
        # para permitir à VIEW converter saldo_anterior/saldo_final [...] em
        # valor absoluto + natureza APURADA". A view já usava esse valor
        # para calcular `saldo_final_nat` acima; faltava só REPASSÁ-LO ao
        # contexto, no formato que `templates/contabilidade/_saldo.html` já
        # sabe ler (`conta.natureza`) — o parcial é reaproveitado tal como
        # está, sem mudança nele (fora do escopo desta etapa).
        #
        # Exposto como `dict`, não como o objeto `Conta`: a Django Template
        # Language resolve `conta.natureza` tentando PRIMEIRO
        # `conta["natureza"]` (lookup de dicionário) antes de tentar
        # `getattr` — `Variable._resolve_lookup`, biblioteca padrão do
        # Django — então `{"natureza": "devedora"}` resolve `conta.natureza`
        # exatamente como um objeto seria. Preferido ao objeto `Conta`
        # inteiro por dois motivos: (1) a view não tem o objeto aqui —
        # `apurar_balancete` devolve campos agregados, não instâncias de
        # `Conta`, e buscar uma consulta extra por linha para um único
        # campo já lido seria N+1 sem necessidade; (2) um dict deliberadamente
        # estreito não sugere ao template que outros atributos de `Conta`
        # (ex.: `codigo`, `nome`) estão disponíveis nesta chave — só
        # `natureza` está.
        #
        # `None` quando `linha["natureza"]` não é um dos dois valores de
        # `NaturezaConta` (defesa contra dado corrompido fora do caminho
        # validado — ex.: escrita direta no banco — já que o campo do
        # modelo é obrigatório e usa `choices`, então em dado íntegro isto
        # nunca acontece). Com `conta=None`, `_saldo.html` não marca
        # parênteses: `None.natureza` não resolve a "devedora" nem
        # "credora" em nenhum dos dois ramos do `{% if %}`, então cai no
        # `{% else %}` (mostra o valor sem parênteses) — never inventa um
        # lado para dado que o sistema não pode confirmar. Saldo ZERO já é
        # tratado sem depender disto: `_saldo.html` primeiro confere
        # `{% if natureza %}` (a natureza APURADA, `saldo_final_natureza`
        # abaixo) e `_indicador_natureza` devolve `None` para saldo zero
        # (RC-61) — o ramo de `conta.natureza` nunca é alcançado nesse caso.
        conta_natureza_cadastrada = (
            linha["natureza"] if linha["natureza"] in NaturezaConta.values else None
        )
        linhas.append(
            {
                "conta_id": ids_por_codigo.get(linha["conta"]),
                "conta": {"natureza": conta_natureza_cadastrada},
                "codigo": linha["conta"],
                "nome": linha["nome"],
                "nivel": linha["nivel"],
                # Inteiro, nunca `float` (achado 6 — mesma regra de
                # `_linhas_hierarquicas`, ver o comentário lá).
                "nivel_classe": min(linha["nivel"], NIVEL_INDENTACAO_MAXIMA)
                if linha["nivel"]
                else 0,
                "analitica": linha["analitica"],
                "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
                "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
                "debitos_ptbr": _valor_ptbr(linha["debitos"]),
                "creditos_ptbr": _valor_ptbr(linha["creditos"]),
                # DE-024 §2: é sobre ESTAS duas colunas (o movimento
                # PRÓPRIO de cada linha), não sobre "debitos"/"creditos"
                # (consolidados), que a soma das linhas exibidas reconcilia
                # com o rodapé (critério 6) — em qualquer arranjo de plano
                # de contas, porque todo lançamento é próprio de
                # exatamente uma conta.
                "debitos_proprios_ptbr": _valor_ptbr(linha["debitos_proprios"]),
                "creditos_proprios_ptbr": _valor_ptbr(linha["creditos_proprios"]),
                "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
                "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
            }
        )

    # DL-027 Fatia B (item 3 do plano): a trava de "Fecha / Não fecha"
    # que o produto já calculava (BL-290 / A2 da DL-026 rodada 2) vira
    # VETO aqui. A decisão mora no `services` —
    # `avaliar_emissao_do_balancete` decide em `Decimal`, nunca em texto
    # pt-BR já formatado (a mesma lição do BL-290: `_valor_ptbr`
    # arredonda, e 300,004 vs 300,00 viram o mesmo "300,00"). A view
    # pergunta e obedece (mesmo contrato de `avaliar_emissao_do_balanco`,
    # DL-034). Quando `pode_emitir` é `False`, devolvemos 409 com a
    # diferença em pt-BR e a orientação textual — o critério 9 do plano
    # proíbe veto seco. A resposta recusada não recebe contexto de
    # apuração, carimbo, timbre ou template imprimível do Balancete: um
    # HTTP 409 não pode entregar o documento que acabou de vetar.
    avaliacao = avaliar_emissao_do_balancete(apuracao)
    if not avaliacao["pode_emitir"]:
        messages.error(
            request,
            "O Balancete NÃO pode ser emitido: débitos e créditos do período "
            f"divergem em R$ {avaliacao['diferenca_ptbr']}. Verifique os "
            "lançamentos do período antes de reimprimir.",
        )
        return render(
            request,
            "contabilidade/balancete_emissao_recusada.html",
            {"empresa": empresa},
            status=409,
        )

    # Veredito calculado em `Decimal` sobre os totais de ORIGEM
    # (`apuracao["total_debitos"]`/`["total_creditos"]`) — nunca sobre
    # o texto pt-BR logo abaixo. Ver o docstring de
    # `_veredito_balancete` (mantido aqui só para o display; a
    # decisão de EMISSÃO vem de `avaliar_emissao_do_balancete`).
    veredito_balancete = avaliacao["veredito"]
    diferenca_balancete_ptbr = avaliacao["diferenca_ptbr"]

    contexto.update(
        {
            "linhas": linhas,
            "total_debitos_ptbr": _valor_ptbr(apuracao["total_debitos"]),
            "total_creditos_ptbr": _valor_ptbr(apuracao["total_creditos"]),
            # BL-290: chave ÚNICA de decisão para a faixa — "fecha" /
            # "nao_fecha" / "nada_a_conferir". O template ramifica por ela;
            # não volta a comparar `total_debitos_ptbr`/`total_creditos_
            # ptbr` (texto) entre si.
            "veredito_balancete": veredito_balancete,
            # `None` fora do ramo "nao_fecha" — nunca "0,00", que seria
            # ruído (mesma política do BL-286/BL-289 no lançamento).
            "diferenca_balancete_ptbr": diferenca_balancete_ptbr,
            # R6-9/BL-203 (rodada 6) — critério 13, texto literal: "empresa
            # sem lançamento no período mostra MENSAGEM, não tabela vazia
            # sem explicação". Diário, Razão e Conferência cumpriam; o
            # Balancete mostrava 3 linhas e 8 zeros, sem uma palavra. O
            # achado foi levantado na rodada 5 como observação, não entrou
            # no backlog, e por isso chegou intacto à rodada 6.
            #
            # A condição é "nenhum movimento NO PERÍODO" (os dois totais do
            # período em zero), não "nenhuma linha": um balancete com saldo
            # ANTERIOR e sem movimento no mês é informação legítima e
            # continua sendo exibido inteiro — a mensagem explica o que se
            # está vendo, **nunca esconde a tabela**. Esconder seria trocar
            # um defeito de explicação por um de omissão contábil.
            "sem_movimento_no_periodo": (
                bool(linhas) and apuracao["total_debitos"] == 0 and apuracao["total_creditos"] == 0
            ),
            # BL-198 (b): e é justamente no balancete zerado que o aviso
            # mais importa — ele concilia, então nada mais denuncia que
            # existe movimento fora do período.
            "movimento_fora_do_periodo": _aviso_de_movimento_fora_do_periodo(
                request, empresa, inicio, fim
            ),
            # BL-282: o Balancete é a tela nomeada pelo critério 9 da DL-026
            # para sair com a identidade do ESCRITÓRIO, não a do fornecedor
            # — ver o comentário em `diario` para o contrato completo.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
        }
    )
    return render(request, "contabilidade/balancete.html", contexto)


# ---------------------------------------------------------------------------
# Balanço Patrimonial (DL-034) — nível 1: a primeira DEMONSTRAÇÃO CONTÁBIL
# que o produto emite (classe 2 de personalizacao-de-relatorio.md), não
# conferência. "O que eu vou entregar fecha, e eu sei o que ele NÃO diz":
# quem decide SE PODE emitir é o SERVIDOR
# (apps.contabilidade.services.avaliar_emissao_do_balanco) — esta view
# pergunta, obedece e explica; nunca recompõe a decisão.
# ---------------------------------------------------------------------------

# Rótulo humano de cada lista de pendência que `avaliar_emissao_do_balanco`
# pode devolver em `emissao["listas_pendentes"]` — SÓ apresentação (a
# REGRA de quando cada lista fica não vazia mora inteira em services.py,
# nunca duplicada aqui). `.get(nome, nome)` no ponto de uso cobre uma
# lista futura que `_LISTAS_DE_PENDENCIA_DO_BALANCO` (services.py) venha a
# ganhar sem que este dicionário tenha sido atualizado ainda — a tela
# nomeia a CHAVE crua em vez de quebrar ou silenciar a pendência.
NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO = {
    "contas_com_tipo_desconhecido": ("Conta com tipo gravado fora do cadastro (dado corrompido)"),
    "contas_com_tipo_divergente_da_raiz": (
        "Conta cujo tipo diverge do tipo da raiz da sua hierarquia"
    ),
    "contas_com_classificacao_aninhada": (
        "Duas contas da mesma hierarquia classificando o mesmo grupo (circulante/não circulante)"
    ),
    "contas_com_classificacao_desconhecida": (
        "Conta com classificação patrimonial gravada fora do cadastro (dado corrompido)"
    ),
    "contas_sem_classificacao_patrimonial": (
        "Conta com saldo, do Ativo ou do Passivo, sem classificação circulante/não circulante"
    ),
    # BL-516: o agrupamento desta lista abrange contas-irmãs e contas-raiz
    # do mesmo tipo (para raízes, `conta_pai` é `None`). O rótulo descreve
    # a divergência de natureza sem afirmar que existe ancestral comum ou
    # não classificado.
    # DE-070: esta lista é AVISO, não veto — o rótulo evita "corrija",
    # que era instrução IMPOSSÍVEL sempre que a classificação já estava
    # certa (ver ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA, abaixo).
    "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
        "Contas de topo do mesmo tipo (irmãs ou raízes) com natureza cadastrada "
        "diferente entre si — aviso, não impede a emissão"
    ),
    "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
        "Conta que agrupa outras contas (não é folha), sem classificação "
        "própria nem de um ancestral, com movimento lançado diretamente nela"
    ),
}


def _data_base_do_formulario(request):
    """Lê e valida 'data_base' da querystring do Balanço — DIFERENTE de
    `_periodo_do_formulario` (Diário/Razão/Balancete, um INTERVALO): o
    Balanço é uma FOTOGRAFIA de uma única data (NBC TG 26 item 51(c), "a
    data de encerramento do período de reporte ou o período coberto").

    Ausência do parâmetro (primeira visita) usa HOJE como valor inicial
    sugerido — mesma convenção de conveniência de `_periodo_do_formulario`
    (é a TELA quem escolhe um padrão por conveniência de quem a usa todo
    dia; `apurar_saldos`/`apurar_balanco_patrimonial` não têm padrão
    próprio nenhum). Uma data enviada e malformada nunca "cai" no padrão em
    silêncio — mesma regra de `_periodo_do_formulario`.

    Devolve `(data_base, mensagem_de_erro)`.
    """
    bruto = request.GET.get("data_base", "").strip()
    if not bruto:
        return timezone.localdate(), None
    try:
        return para_data(bruto), None
    except DataInvalida:
        return None, "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD)."


# `_cnpj_mascarado` (DL-034) foi REMOVIDA nesta etapa (DL-038, etapa 2):
# ela sempre lia `empresa.cnpj` direto, e uma empresa CPF em modo
# contabilidade (permitida — nada no R4 proíbe isso) tem `empresa.cnpj`
# vazio por invariante de banco, o que imprimiria o Balanço com a
# inscrição EM BRANCO. O ponto único agora é `apps.contabilidade.services.
# rotulo_e_inscricao_da_empresa` — mesma app, sem o problema de
# acoplamento que motivava a duplicação original (import de símbolo
# PRIVADO de outro app): a nova função mora no MESMO app que a consome,
# só reescreve a máscara em vez de importar de `apps.empresas` (mesma
# decisão consciente, mesmo motivo, ver a docstring dela).


# BL-508 (auditoria DL-034, achado A10): rótulo HUMANO de cada campo extra
# que uma linha de pendência do Balanço pode carregar além de "conta"/
# "nome" — nunca o NOME CRU do campo do banco (`classificacao_
# patrimonial`, `natureza`, `tipo`, `tipo_da_raiz`, `...ancestral`), que a
# tela mostrava ao contador antes desta correção. Cobre HOJE todos os
# campos extras que as SETE listas de `_LISTAS_DE_PENDENCIA_DO_BALANCO`
# (services.py) anexam — ver o comentário de `_linhas_de_pendencia` sobre
# o que acontece quando um campo NOVO aparecer sem entrar aqui.
_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA = {
    "tipo": "Tipo cadastrado",
    "tipo_da_raiz": "Tipo da raiz da hierarquia",
    "classificacao_patrimonial": "Classificação cadastrada",
    "classificacao_patrimonial_ancestral": "Classificação do ancestral",
    "natureza": "Natureza cadastrada",
}

# Os TRÊS `TextChoices`/enum do modelo que guardam o VALOR desses campos —
# `EnumClasse(valor).label` é o mesmo rótulo que o CADASTRO já mostra
# (formulário de conta, DL-018/DL-020); nunca uma segunda tradução escrita
# à mão aqui (duas cópias do mesmo rótulo divergem — AGENTS.md §8).
_ENUM_DO_CAMPO_DE_PENDENCIA = {
    "tipo": TipoConta,
    "tipo_da_raiz": TipoConta,
    "classificacao_patrimonial": ClassificacaoPatrimonial,
    "classificacao_patrimonial_ancestral": ClassificacaoPatrimonial,
    "natureza": NaturezaConta,
}


def _humanizar_valor_de_campo_de_pendencia(chave, valor):
    """Traduz o VALOR cru de um campo extra de pendência (ex.:
    `"ativo_circulante"`, `"devedora"`) para o RÓTULO que o cadastro usa
    (ex.: "Ativo circulante", "Devedora") — via `EnumClasse(valor).label`,
    nunca uma tradução escrita à mão. As DUAS listas que existem
    exatamente para nomear DADO CORROMPIDO
    (`contas_com_tipo_desconhecido`/`contas_com_classificacao_
    desconhecida` — ver `services.py`) carregam, de propósito, um valor
    que NÃO está no enum (é o próprio defeito que a lista denuncia); para
    essas, `EnumClasse(valor)` lança `ValueError` e a função devolve o
    valor cru mesmo — não há rótulo humano possível para um valor que o
    cadastro nunca aceitaria, e mostrar o valor bruto AQUI é diferente de
    mostrar o NOME DO CAMPO cru (o defeito que o BL-508 fecha): o rótulo
    da CHAVE (`_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA`, acima) já apareceu
    antes deste valor, então a frase inteira continua legível."""
    enum_do_campo = _ENUM_DO_CAMPO_DE_PENDENCIA.get(chave)
    if enum_do_campo is None:
        return str(valor)
    try:
        return enum_do_campo(valor).label
    except ValueError:
        return str(valor)


# BL-508: a AÇÃO que resolve cada pendência — critério da correção 4 do
# auditor ("toda pendência declarada nomeia uma ação que RESOLVE", não um
# adjetivo do enunciado). Uma frase por lista, ao lado de
# `NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO` (mesmas SETE chaves —
# `test_dl034_tela_do_balanco.py` cruza as duas e reprova se uma lista
# ficar sem ação). A ÚNICA que não é imperativa
# (`contas_topo_classificadas_com_natureza_divergente_entre_irmas`) é a
# que a DE-070 tornou AVISO: ela nunca IMPEDE a emissão, então a "ação"
# certa é CONFERIR, não necessariamente CORRIGIR — ver o comentário grande
# em `avaliar_emissao_do_balanco` (services.py) sobre o motivo.
ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA = {
    "contas_com_tipo_desconhecido": (
        "Corrigir o tipo cadastrado da conta no plano de contas, escolhendo um dos tipos "
        "válidos (Ativo, Passivo, Patrimônio Líquido, Receita ou Despesa)."
    ),
    "contas_com_tipo_divergente_da_raiz": (
        "Corrigir o tipo da conta ou o da raiz da sua hierarquia no plano de contas, para "
        "que os dois coincidam."
    ),
    "contas_com_classificacao_aninhada": (
        "Remover a classificação circulante/não circulante de uma das duas contas no plano "
        "de contas — deixar só o grupo OU só as contas-folha classificadas, nunca os dois "
        "ao mesmo tempo na mesma hierarquia."
    ),
    "contas_com_classificacao_desconhecida": (
        "Corrigir a classificação patrimonial da conta no plano de contas, escolhendo uma "
        "das opções válidas de circulante/não circulante."
    ),
    "contas_sem_classificacao_patrimonial": (
        "Classificar a conta (ou um ancestral dela) como circulante ou não circulante no "
        "plano de contas."
    ),
    # BL-508 (correção 4 do auditor) + relato do arquiteto sobre o
    # contrato novo de services.py: esta é a ÚNICA ação que CONFERE, não
    # CORRIGE — a pendência não impede a emissão (DE-070), e pode ser o
    # desenho CORRETO do plano de contas (ex.: retificadora). O texto NÃO
    # afirma "o Balanço já foi emitido" — isso depende de OUTRA pendência
    # não estar bloqueando ao mesmo tempo (critério de aceite 6: o aviso
    # aparece nos DOIS desfechos, emitido ou recusado por outro motivo) —
    # quem decide "emitiu ou não" é a faixa de fechamento, não este texto.
    "contas_topo_classificadas_com_natureza_divergente_entre_irmas": (
        "Aviso, não bloqueio: esta pendência sozinha NUNCA impede a emissão do Balanço. "
        "Confira se a natureza cadastrada de cada conta abaixo está correta — é o desenho "
        "esperado quando uma delas é RETIFICADORA de propósito (ex.: “(-) Provisão para "
        "devedores duvidosos” sob o mesmo grupo de “Clientes”); se não for o caso, corrija "
        "a natureza cadastrada da conta errada no plano de contas."
    ),
    "contas_nao_folha_sem_classificacao_com_movimento_proprio": (
        "Classificar esta conta (ou um ancestral dela) como circulante/não circulante no "
        "plano de contas, ou lançar os valores numa conta-folha já classificada, em vez de "
        "lançar diretamente nesta conta-síntese."
    ),
}


# DE-070 (services.py): `avaliar_emissao_do_balanco` devolve a separação
# PRONTA — `listas_pendentes` (só o que IMPEDE) e `listas_informativas`
# (só o que AVISA, nunca impede), as duas DISJUNTAS por construção do lado
# do servidor (`_LISTAS_QUE_IMPEDEM_A_EMISSAO`/`_LISTAS_QUE_SO_AVISAM`,
# ver o comentário grande de `avaliar_emissao_do_balanco`). Esta tela NÃO
# recalcula veto nenhum nem duplica o nome de nenhuma lista específica —
# só CONSOME as duas chaves e decide em qual bloco visual cada uma
# aparece (Erro bloqueante vs. Aviso, nunca bloqueante).


def _lista_de_pendencia_para_contexto(nome, itens):
    """Uma entrada de `listas_pendentes`/`listas_apenas_aviso` do
    contexto do template — título humano (`NOMES_HUMANOS_...`), linhas
    humanizadas (`_linhas_de_pendencia`) e a AÇÃO que resolve
    (`ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA`). Extraída para as DUAS
    visões da view `balanco` (bloqueada e emitida-com-aviso) montarem a
    MESMA estrutura sem repetir os três `.get`/chamada."""
    return {
        "titulo": NOMES_HUMANOS_DAS_LISTAS_DE_PENDENCIA_DO_BALANCO.get(nome, nome),
        "linhas": _linhas_de_pendencia(itens),
        # BL-508 (correção 4 do auditor): "explica" tem de ser
        # VERIFICÁVEL — toda pendência declarada nomeia uma ação que
        # RESOLVE. `.get(nome, ...)` nomeia a CHAVE crua só se uma lista
        # nova aparecer sem ação cadastrada ainda — nunca quebra a tela,
        # mas fica claramente incompleto para quem lê (não finge ser uma
        # instrução de verdade).
        "acao": ACAO_QUE_RESOLVE_A_PENDENCIA_POR_LISTA.get(
            nome, f"Ação não cadastrada para a pendência '{nome}' — avise o suporte."
        ),
    }


def _linhas_de_pendencia(itens):
    """Uma linha por conta pendente, a partir de UMA das listas de
    `emissao["listas_pendentes"]` — genérica na FORMA (cada lista de
    `apurar_saldos` nomeia campos diferentes além de "conta"/"nome": ex.
    "tipo"/"tipo_da_raiz", "classificacao_patrimonial"/"...ancestral"),
    mas HUMANIZADA no CONTEÚDO desde o BL-508 (achado A10 da auditoria da
    DL-034): antes desta correção, o "rótulo/valor de apoio" de cada campo
    extra era o PAR CRU (`f"{chave}: {valor}"`, ex.: "classificacao_
    patrimonial: ativo_circulante"), mostrando ao contador o nome do campo
    do banco e a constante interna gravada nele. Agora cada par vira
    `_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA` (a CHAVE) +
    `_humanizar_valor_de_campo_de_pendencia` (o VALOR, via `.label` do
    enum) — uma chave NOVA que `apurar_saldos` ganhar no futuro sem entrar
    nos dois dicionários acima ainda aparece aqui (nunca quebra: cai no
    `.get(chave, chave)`/`str(valor)` cru — PIOR do que humanizado, mas
    NUNCA pior do que o comportamento anterior a esta correção), e um
    teste (`test_dl034_tela_do_balanco.py`) varre o CORPO da resposta
    procurando os nomes crus dos campos conhecidos hoje.
    """
    linhas = []
    for item in itens:
        detalhes = [
            f"{_ROTULOS_HUMANOS_DE_CAMPO_DE_PENDENCIA.get(chave, chave)}: "
            f"{_humanizar_valor_de_campo_de_pendencia(chave, valor)}"
            for chave, valor in item.items()
            if chave not in ("conta", "nome")
        ]
        linhas.append(
            {
                "conta": item.get("conta"),
                "nome": item.get("nome"),
                "detalhe": "; ".join(detalhes) if detalhes else None,
            }
        )
    return linhas


def _linha_de_conta_do_balanco(linha):
    """Uma linha IMPRESSA do Balanço, a partir de uma linha de
    `saldos["contas"]` (apurar_saldos) — MESMA conversão saldo-assinado ->
    (valor absoluto, D/C) que o Balancete já usa
    (`_saldo_absoluto_com_natureza`), pela natureza CADASTRADA desta
    própria conta (`linha["natureza"]`) — nunca a natureza do grupo: é a
    mesma prova que RC-61/BL-77 já sustentam para o Razão e o Balancete.
    """
    saldo_abs, saldo_natureza = _saldo_absoluto_com_natureza(linha["saldo"], linha["natureza"])
    natureza_cadastrada = linha["natureza"] if linha["natureza"] in NaturezaConta.values else None
    return {
        "codigo": linha["conta"],
        "nome": linha["nome"],
        "conta": {"natureza": natureza_cadastrada},
        "saldo_ptbr": _valor_ptbr(saldo_abs),
        "saldo_natureza": _indicador_natureza(saldo_natureza),
    }


def _subtotal_do_balanco(valor, tipo_do_grupo):
    """Um subtotal/total IMPRESSO do Balanço (subgrupo, grupo ou grande
    total) — mesma conversão de `_linha_de_conta_do_balanco`, mas pela
    natureza NATURAL DO TIPO (devedora no Ativo, credora no Passivo e no
    Patrimônio Líquido — o mesmo referencial da normalização do critério 1
    do plano DL-034/`avaliar_emissao_do_balanco`), porque um subtotal soma
    VÁRIAS contas e não tem uma única "natureza cadastrada" própria para
    servir de referência. Reaproveita `_saldo_absoluto_com_natureza`
    (RC-61) passando essa natureza esperada no lugar da natureza cadastrada
    de uma conta — mesma função, argumento diferente, nenhuma regra nova.
    """
    natureza_esperada = (
        NaturezaConta.DEVEDORA if tipo_do_grupo == TipoConta.ATIVO else NaturezaConta.CREDORA
    )
    valor_abs, natureza_apurada = _saldo_absoluto_com_natureza(valor, natureza_esperada)
    return {
        "valor_ptbr": _valor_ptbr(valor_abs),
        "natureza": _indicador_natureza(natureza_apurada),
        # Consumido por templates/contabilidade/_saldo_grupo.html — igual
        # em espírito a `conta.natureza` de `_saldo.html` (RC-61), mas em
        # texto puro: um SUBTOTAL não tem uma única conta cadastrada para
        # servir de referência de inversão.
        "natureza_esperada": (
            "devedora" if natureza_esperada == NaturezaConta.DEVEDORA else "credora"
        ),
    }


def _montar_grupos_do_balanco(saldos):
    """Monta as CINCO seções impressas do Balanço a partir de `saldos`
    (`apurar_saldos`, dentro de `apurar_balanco_patrimonial`) — Ativo
    Circulante, Ativo Não Circulante (com os QUATRO subgrupos do art. 178
    §1º II e o subtotal), Passivo Circulante, Passivo Não Circulante e
    Patrimônio Líquido (RC-106; escopo do plano DL-034, critério 1) — mais
    os DOIS grandes totais (Ativo; Passivo + Patrimônio Líquido) que a
    folha imprime lado a lado para o contador CONFERIR a equação a olho,
    sem precisar somar na mão.

    ⚠️ Só é chamada quando `emissao["pode_emitir"]` é `True` — quem chama
    (a view `balanco`) nunca monta esta estrutura para uma apuração
    pendente (critério "a tela não emite... mostra o que falta").

    As LINHAS de cada (sub)grupo vêm de `saldos["contas"]`, filtradas pelas
    que DEFINEM uma classificação própria (`classificacao_patrimonial` não
    `None`) — exatamente o mesmo conjunto que `totais_por_classificacao`
    soma (ver o docstring de `apurar_saldos`), nunca por prefixo de código
    nem por nível da árvore. Com `pode_emitir` verdadeiro, nenhuma conta
    está classificada em mais de um lugar (a lista de aninhamento já
    garantiu isso) — filtrar por "tem classificação própria" não duplica
    nenhuma linha.
    """
    linhas_por_classificacao = {}
    for linha in saldos["contas"]:
        classificacao = linha["classificacao_patrimonial"]
        if classificacao:
            linhas_por_classificacao.setdefault(classificacao, []).append(
                _linha_de_conta_do_balanco(linha)
            )

    def _secao(classificacao):
        tipo_do_grupo = TIPO_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        return {
            "titulo": ClassificacaoPatrimonial(classificacao).label,
            "linhas": linhas_por_classificacao.get(classificacao, []),
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_classificacao"][classificacao], tipo_do_grupo
            ),
        }

    # Os QUATRO subgrupos do Ativo Não Circulante, na ORDEM DE DECLARAÇÃO
    # do enum (art. 178 §1º II: realizável a longo prazo, investimentos,
    # imobilizado, intangível) — derivados do MAPA da lei (BL-490), nunca
    # uma lista de strings escrita à mão: toda `ClassificacaoPatrimonial`
    # cujo grupo da lei é `ATIVO_NAO_CIRCULANTE`.
    subgrupos_ativo_nao_circulante = [
        _secao(classificacao)
        for classificacao in ClassificacaoPatrimonial.values
        if GRUPO_DA_LEI_DA_CLASSIFICACAO_PATRIMONIAL[classificacao]
        == GrupoDaLei.ATIVO_NAO_CIRCULANTE
    ]

    # Patrimônio Líquido é o TERCEIRO grupo do passivo (art. 178 §2º III) —
    # não é circulante nem não circulante (RC-106) — e por isso não tem
    # `classificacao_patrimonial` nenhuma. As linhas vêm das RAÍZES de tipo
    # PATRIMONIO_LIQUIDO (mesmo conjunto que `totais_por_tipo` já soma,
    # DE-056), no molde do Balancete: cada raiz já vem CONSOLIDADA com a
    # subárvore inteira (DE-020).
    linhas_pl = [
        _linha_de_conta_do_balanco(linha)
        for linha in saldos["contas"]
        if linha["raiz"] and linha["tipo"] == TipoConta.PATRIMONIO_LIQUIDO
    ]

    return {
        "ativo_circulante": _secao(ClassificacaoPatrimonial.ATIVO_CIRCULANTE),
        "ativo_nao_circulante": {
            "titulo": GrupoDaLei.ATIVO_NAO_CIRCULANTE.label,
            "subgrupos": subgrupos_ativo_nao_circulante,
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_grupo"][GrupoDaLei.ATIVO_NAO_CIRCULANTE], TipoConta.ATIVO
            ),
        },
        "passivo_circulante": _secao(ClassificacaoPatrimonial.PASSIVO_CIRCULANTE),
        "passivo_nao_circulante": _secao(ClassificacaoPatrimonial.PASSIVO_NAO_CIRCULANTE),
        "patrimonio_liquido": {
            "titulo": TipoConta.PATRIMONIO_LIQUIDO.label,
            "linhas": linhas_pl,
            "subtotal": _subtotal_do_balanco(
                saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO],
                TipoConta.PATRIMONIO_LIQUIDO,
            ),
        },
        "total_ativo": _subtotal_do_balanco(
            saldos["totais_por_tipo"][TipoConta.ATIVO], TipoConta.ATIVO
        ),
        "total_passivo_e_pl": _subtotal_do_balanco(
            saldos["totais_por_tipo"][TipoConta.PASSIVO]
            + saldos["totais_por_tipo"][TipoConta.PATRIMONIO_LIQUIDO],
            TipoConta.PASSIVO,
        ),
        # Informativo, NUNCA usado para gatear emissão (essa decisão é
        # inteira de `avaliar_emissao_do_balanco` — ver o cabeçalho desta
        # seção): quando não-zero, é o resultado do período que AINDA não
        # foi transferido ao Patrimônio Líquido por lançamento de
        # encerramento (RC-104) — é a diferença honesta entre "Total do
        # Ativo" e "Total do Passivo + PL" que o contador vê no papel, e
        # que a equação de `apurar_saldos` já calcula. Mostrar isto é
        # cumprir "eu sei o que ele NÃO diz" em vez de deixar duas somas
        # divergentes sem explicação no documento. Formatado em VALOR
        # ABSOLUTO com o sinal preservado só em PALAVRA ("lucro"/
        # "prejuízo") — nunca "-" na frente do número (RC-90: sinal nunca é
        # o único canal, e este projeto nem usa sinal para valor negativo
        # em lugar nenhum do documento).
        #
        # BL-501 (achado da auditoria DL-034 rodada 1): a CHAVE deste
        # dicionário NÃO termina em "_ptbr" de propósito — só o campo
        # FOLHA (`valor_ptbr`, abaixo) termina. A varredura de interface
        # (`apps/core/tests/test_dl024_varredura_de_interface.py::
        # test_todo_valor_em_celula_usa_a_classe_do_sistema`) reprova
        # QUALQUER token que termine em "_ptbr" dentro de uma célula de
        # tabela sem a classe `valor-monetario` ao redor — inclusive
        # dentro de um `{% if %}` de template, que nunca é exibido. Com a
        # chave se chamando "resultado_nao_transferido_ptbr", o PRÓPRIO
        # `{% if grupos.resultado_nao_transferido_ptbr %}` (condição, não
        # saída) contava como um valor monetário desprotegido — dois
        # falsos positivos (a condição e o acesso a `.e_prejuizo`), medido
        # rodando a suíte. Renomear a chave para "resultado_nao_
        # transferido" (sem sufixo) resolve na raiz: a condição deixa de
        # casar com o padrão, e o único token que ainda termina em
        # "_ptbr" (`.valor_ptbr`, dentro do `<span class="valor-
        # monetario">` no template) continua coberto.
        "resultado_nao_transferido": (
            {
                "valor_ptbr": _valor_ptbr(abs(saldos["equacao"]["resultado_nao_transferido"])),
                "e_prejuizo": saldos["equacao"]["resultado_nao_transferido"] < 0,
            }
            if saldos["equacao"]["resultado_nao_transferido"] != 0
            else None
        ),
    }


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def balanco(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    data_base, erro_data_base = _data_base_do_formulario(request)
    contexto = {"empresa": empresa, "data_base": data_base}
    if erro_data_base:
        messages.error(request, erro_data_base)
        return render(request, "contabilidade/balanco.html", contexto, status=400)

    try:
        # DE-067: a ÚNICA porta de entrada que gera o documento impresso do
        # Balanço chama `apurar_balanco_patrimonial` — nunca `apurar_saldos`
        # direto —, porque só ela paga o snapshot (REPEATABLE READ) que
        # impede o documento sair com números de dois instantes diferentes.
        resultado = apurar_balanco_patrimonial(empresa=empresa, data_base=data_base)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/balanco.html", contexto, status=409)

    saldos = resultado["saldos"]
    emissao = resultado["emissao"]

    # DL-038 (etapa 2, critério 7): rótulo e inscrição corretos —
    # "CNPJ 12.345.678/0001-95" para pessoa jurídica, "CPF 123.456.789-09"
    # para pessoa física — nunca CNPJ fixo, que sairia em branco para
    # empresa CPF (`empresa.cnpj` é vazio por invariante de banco nesse
    # caso). Ver `rotulo_e_inscricao_da_empresa` para o porquê deste ser o
    # ponto único da formatação.
    rotulo_inscricao, inscricao_formatada = rotulo_e_inscricao_da_empresa(empresa)

    contexto.update(
        {
            # NBC TG 26 item 51/52 (RC-95) — o bloco de identificação é
            # consumido pelo template DENTRO do `<thead>` da tabela, para
            # se repetir em TODA página impressa (critério 4 do plano
            # DL-034; mesmo mecanismo já provado pelo cabeçalho de coluna
            # do Balancete, BL-282: `display: table-header-group`).
            "identificacao": resultado["identificacao"],
            "rotulo_inscricao": rotulo_inscricao,
            "inscricao_formatada": inscricao_formatada,
            # BL-282/RC-97: mesmo timbre do escritório que Balancete/
            # Diário/Razão já usam — ver o comentário em `diario` para o
            # contrato completo. Continua só na folha 1 (não é exigência do
            # item 51, que fala da ENTIDADE cliente, não do escritório
            # emitente); o bloco que PRECISA repetir em toda folha é o de
            # `identificacao`, acima, tratado à parte no template.
            "timbre_linhas": empresa.escritorio.linhas_do_timbre,
            # Estado VAZIO (critério do Balancete, B4/BL-283) — calculado
            # UMA vez, aqui, para o template nunca precisar adivinhar
            # "ausência de chave" como "vazio": a chave está SEMPRE
            # presente a partir deste ponto.
            "empresa_tem_plano_de_contas": bool(saldos["contas"]),
        }
    )

    if not saldos["contas"]:
        # Estado VAZIO: empresa sem NENHUMA conta cadastrada — mesmo
        # critério do Balancete (B4/BL-283): nada para classificar, nada
        # para recusar ainda, e mostrar uma recusa aqui confundiria "falta
        # cadastrar o plano" com "há pendência de classificação".
        return render(request, "contabilidade/balanco.html", contexto)

    # DE-070: `emissao["listas_informativas"]` já vem SEPARADA, pronta do
    # servidor — a que só AVISA, nunca impede (ver o comentário grande de
    # `avaliar_emissao_do_balanco`, services.py). A tela só monta a
    # ESTRUTURA de apresentação (título/linhas/ação); aparece tanto
    # emitindo quanto recusando, se estiver presente nos dois casos —
    # fora do `{% if/elif/else %}` do template, que decide só "monta a
    # tabela ou não".
    contexto["listas_apenas_aviso"] = [
        _lista_de_pendencia_para_contexto(nome, itens)
        for nome, itens in emissao["listas_informativas"].items()
    ]

    if not emissao["pode_emitir"]:
        # "O que eu vou entregar fecha, e eu sei o que ele NÃO diz": havendo
        # QUALQUER pendência que VETE, a tela NÃO monta a tabela do Balanço
        # — só o que falta, nomeado (critério 1 e "o momento da verdade" do
        # plano DL-034). 200, não um código de erro: a tela RESPONDEU
        # corretamente à pergunta "pode emitir?" — a resposta é "não, e eis
        # o porquê", que é sucesso da TELA, não falha de protocolo.
        contexto.update(
            {
                "pode_emitir": False,
                "residuo_pendente": [
                    {
                        "tipo_label": TipoConta(tipo).label,
                        "diferenca_ptbr": _valor_ptbr(abs(valor)),
                    }
                    for tipo, valor in emissao["residuo_pendente"].items()
                ],
                # `emissao["listas_pendentes"]` já vem só com o que
                # BLOQUEIA (DE-070/services.py) — a que só avisa está em
                # `listas_informativas`, tratada acima, nunca aqui.
                "listas_pendentes": [
                    _lista_de_pendencia_para_contexto(nome, itens)
                    for nome, itens in emissao["listas_pendentes"].items()
                ],
            }
        )
        return render(request, "contabilidade/balanco.html", contexto)

    contexto.update({"pode_emitir": True, "grupos": _montar_grupos_do_balanco(saldos)})
    return render(request, "contabilidade/balanco.html", contexto)


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def conferencia(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    lotes = []
    for lancamento in localizar_lotes_desbalanceados(empresa=empresa):
        # Linguagem de contador (a tela pede isto explicitamente), em vez
        # do rótulo técnico de três vias que a API devolve
        # ("sem_partidas"/"partida_unica"/"desbalanceado" — achado novo 12).
        if lancamento.quantidade_itens == 0:
            motivo = "Lançamento sem nenhuma partida."
        elif lancamento.quantidade_itens == 1:
            motivo = "Lançamento com uma única partida (sem contrapartida)."
        else:
            motivo = "Débitos e créditos não coincidem."
        lotes.append(
            {
                "lancamento": lancamento,
                "motivo": motivo,
                "total_debito_ptbr": _valor_ptbr(lancamento.total_debito),
                "total_credito_ptbr": _valor_ptbr(lancamento.total_credito),
                "diferenca_ptbr": _valor_ptbr(lancamento.total_debito - lancamento.total_credito),
            }
        )

    contas_sinteticas = [
        {
            "conta": conta,
            "debitos_ptbr": _valor_ptbr(conta.debitos),
            "creditos_ptbr": _valor_ptbr(conta.creditos),
        }
        for conta in localizar_contas_sinteticas_com_movimento(empresa=empresa)
    ]
    contas_com_subordinadas = localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(
        empresa=empresa
    )
    hierarquia_inconsistente = localizar_inconsistencias_de_hierarquia(empresa=empresa)

    # BL-198 (b) na Conferência: aqui não existe período, então o aviso
    # equivalente é outro — lançamento com data FORA DA FAIXA do RC-77
    # (antes de 01/01/2000 ou depois de hoje + N dias). É a única tela de
    # uso normal em que um lançamento datado `9999-12-31` aparece SEM o
    # contador precisar suspeitar primeiro e alargar o período à mão.
    #
    # Vale para dado JÁ GRAVADO: a faixa do RC-77 fecha a porta de entrada,
    # e esta linha acende a luz sobre o que entrou antes dela (ou por uma
    # porta que não passa pela tela, como o admin do Django). Validar a
    # entrada não conserta o passado — e o reparo de dado gravado está
    # declarado fora do escopo desta etapa, o que torna a Conferência o
    # único lugar onde esse passado é visível.
    lancamentos_com_data_fora_da_faixa = list(
        localizar_lancamentos_com_data_fora_da_faixa(empresa=empresa)
    )

    contexto = {
        "empresa": empresa,
        "lotes": lotes,
        "contas_sinteticas": contas_sinteticas,
        "contas_com_subordinadas": contas_com_subordinadas,
        "hierarquia_inconsistente": hierarquia_inconsistente,
        "lancamentos_com_data_fora_da_faixa": lancamentos_com_data_fora_da_faixa,
        "data_minima_lancamento": DATA_MINIMA_LANCAMENTO,
        "data_maxima_lancamento": data_maxima_lancamento(),
        "tudo_certo": not (
            lotes
            or contas_sinteticas
            or contas_com_subordinadas
            or hierarquia_inconsistente
            or lancamentos_com_data_fora_da_faixa
        ),
    }
    return render(request, "contabilidade/conferencia.html", contexto)


# ---------------------------------------------------------------------------
# Fechamento de competência (DL-016 fatia 1 no servidor; DL-031 é a PORTA)
#
# NENHUMA regra contábil desta seção mora aqui — encerrar_competencia,
# reabrir_competencia e marcar_competencia_como_entregue (services.py) já
# decidem, já travam a linha sob concorrência e já gravam a trilha de
# auditoria, auditados em duas rodadas na fatia 1. Esta tela só CHAMA os
# três serviços, traduz cada exceção de negócio em mensagem de português
# (nunca 500 — a lição do BL-457, medida na tela de lançamento) e trata o
# "sem permissão" como ESTADO explicado, não como sumiço silencioso de botão
# (critério 1 do plano DL-031).
#
# Arquétipos, pela direção de arte (§2): D (painel de período) para
# `fechamento`, E (assistente com etapas) para as três telas de ação —
# cada uma mostra o que vai acontecer e o que deixa de ser possível ANTES
# do botão, e a de entrega (a única ação sem volta pelo produto, RC-101)
# exige confirmação explícita em vez de um clique só.
# ---------------------------------------------------------------------------

# Mesma faixa das duas CheckConstraint de Competencia.Meta
# ("competencia_mes_entre_1_e_12", "competencia_ano_entre_1970_e_2999") — a
# MESMA faixa que apps.contabilidade.views._validar_ano_mes já aplica na
# API, antes de chamar o serviço. Não importada de lá: aquele validador fala
# o protocolo do DRF (levanta DRFValidationError), que esta tela não usa —
# só o NÚMERO é compartilhado, por comentário, no mesmo padrão que
# NIVEL_MAXIMO (acima) já copia o teto da API em vez de importar o nome.
_MES_MINIMO_COMPETENCIA, _MES_MAXIMO_COMPETENCIA = 1, 12
_ANO_MINIMO_COMPETENCIA, _ANO_MAXIMO_COMPETENCIA = 1970, 2999


def _ano_mes_de_competencia_valido(ano, mes):
    return (
        _MES_MINIMO_COMPETENCIA <= mes <= _MES_MAXIMO_COMPETENCIA
        and _ANO_MINIMO_COMPETENCIA <= ano <= _ANO_MAXIMO_COMPETENCIA
    )


def _pode_fechar_competencia(request):
    return PodeFecharCompetencia().has_permission(request, None)


def _competencia_pedida(fonte):
    """Lê e valida 'ano'/'mes' de `fonte` (request.GET no GET das três telas
    de ação — a competência viaja por querystring, como o período do
    Diário/Razão/Balancete — e request.POST no POST, onde os dois campos
    voltam como `<input type="hidden">` do próprio formulário, no mesmo
    contrato que a tela já julga).

    Nunca lança exceção: devolve `(ano, mes, None)` quando válido, ou
    `(None, None, mensagem)` quando não — mesmo padrão de
    `_periodo_do_formulario` (erro de entrada nunca é 500, sempre mensagem
    em português). `_inteiro_de_cliente` é o mesmo julgador de QUANTIDADE de
    cliente que o resto deste arquivo já usa (nunca reinterpreta dígito
    Unicode, nunca lança exceção) — 'ano'/'mes' são quantidade de negócio,
    não identificador de banco.
    """
    ano = _inteiro_de_cliente((fonte.get("ano") or "").strip())
    mes = _inteiro_de_cliente((fonte.get("mes") or "").strip())
    if ano is None or mes is None:
        return None, None, "Informe ano e mês da competência."
    if not _ano_mes_de_competencia_valido(ano, mes):
        return (
            None,
            None,
            f"Competência inválida: o mês deve estar entre {_MES_MINIMO_COMPETENCIA} e "
            f"{_MES_MAXIMO_COMPETENCIA}, e o ano entre {_ANO_MINIMO_COMPETENCIA} e "
            f"{_ANO_MAXIMO_COMPETENCIA}.",
        )
    return ano, mes, None


# BL-196: contrato de cada ação — mesma política dos cinco dicionários que
# `lancamento_novo`/`conta_nova` já aplicam, e pelo mesmo motivo (um campo
# que a superfície não lê nunca deve ser ignorado em silêncio). As três são
# rotas de AÇÃO: sem arquivo, sem querystring no POST (o GET usa
# querystring só para MONTAR o formulário; o POST manda 'ano'/'mes' como
# campo oculto do próprio `<form>`, como qualquer outro dado do corpo) e sem
# `Idempotency-Key` (nenhuma das três usa cabeçalho para idempotência; as
# três já são seguras para reenvio — fechar e entregar são idempotentes no
# SERVIÇO, e reabrir é uma ação explícita com motivo, não um POST que se
# repete sem querer).
CONTRATO_FECHAR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no fechamento de competência",
)
CONTRATO_REABRIR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura de competência",
)
CONTRATO_ENTREGAR_COMPETENCIA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "confirmar_entrega"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na entrega de competência",
)


@login_required
@require_safe
@_sem_contabilidade_para_livro_caixa
def fechamento(request, empresa_id):
    """Painel de competências da empresa (arquétipo D) — critérios 1 e 2.

    Lista os meses com estado, quem fechou, quando e se foi entregue; a
    conferência do RC-58 é checada AQUI, uma vez, para a base inteira da
    empresa — havendo lote desbalanceado, nenhum link de "Fechar" aparece
    nas linhas 'aberta' (critério 2: nunca deixar o contador clicar para
    descobrir). Quem não pode fechar/reabrir/entregar (RC-102) continua
    vendo o painel inteiro — só a coluna de ações muda, com uma explicação
    no topo em vez de sumir em silêncio (critério 1).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    # RC-58 / critério 2: mesma checagem que `encerrar_competencia`
    # (services.py) aplica antes de fechar — repetida aqui só para EXIBIR o
    # bloqueio antes do clique. A recusa de verdade continua sendo a do
    # serviço; esta lista não é usada para decidir nada além do que a tela
    # mostra.
    lotes_desbalanceados = list(localizar_lotes_desbalanceados(empresa=empresa))

    competencias = list(
        Competencia.objects.filter(empresa=empresa)
        .select_related("fechada_por", "entregue_por")
        .order_by("-ano", "-mes")
    )

    hoje = timezone.localdate()
    contexto = {
        "empresa": empresa,
        "competencias": competencias,
        "pode_fechar": _pode_fechar_competencia(request),
        "quantidade_lotes_desbalanceados": len(lotes_desbalanceados),
        "ano_sugestao": hoje.year,
        "mes_sugestao": hoje.month,
        "opcoes_mes": range(1, 13),
    }
    return render(request, "contabilidade/fechamento.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
@_sem_contabilidade_para_livro_caixa
def competencia_fechar(request, empresa_id):
    """Fecha uma competência (arquétipo E, etapa única) — critérios 2, 3, 5, 8.

    GET mostra o que vai ser fechado e o que deixa de ser possível ANTES do
    botão (o "momento da verdade" do plano DL-031); se houver lote
    desbalanceado (RC-58), nenhum botão aparece — só o caminho para a
    Conferência. POST chama `encerrar_competencia` (services.py), que é
    quem decide e trava de verdade: toda recusa do serviço vira mensagem em
    português nesta mesma tela, nunca 500 (BL-457).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite fechar competências desta empresa — essa ação "
            "exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_FECHAR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        try:
            competencia = encerrar_competencia(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # Critério 2/5 — RC-58 (lote desbalanceado) ou qualquer outro
            # estado que impeça o fechamento: a mensagem do próprio serviço
            # já nomeia a competência e o motivo. Nunca 500 (BL-457) — o
            # teste desta tela leva controle positivo no mesmo caso.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        # Critério 4/idempotência do serviço: reflete o resultado REAL —
        # `encerrada_agora=False` quando a competência já estava fechada
        # (duas requisições, ou o usuário voltou nesta mesma tela) nunca vira
        # "fechada agora" na mensagem.
        if competencia.encerrada_agora:
            messages.success(
                request, f"Competência {mes:02d}/{ano} de {empresa} fechada com sucesso."
            )
        else:
            messages.info(request, f"Competência {mes:02d}/{ano} de {empresa} já estava fechada.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: se já está encerrada, não há o que confirmar — volta ao painel
    # com o estado explicado em vez de mostrar um formulário sem sentido.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is not None and competencia.estado == EstadoCompetencia.ENCERRADA:
        messages.info(request, f"A competência {mes:02d}/{ano} de {empresa} já está encerrada.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    lotes_desbalanceados = list(localizar_lotes_desbalanceados(empresa=empresa))
    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "quantidade_lotes_desbalanceados": len(lotes_desbalanceados),
    }
    return render(request, "contabilidade/competencia_fechar.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
@_sem_contabilidade_para_livro_caixa
def competencia_reabrir(request, empresa_id):
    """Reabre uma competência (arquétipo E, etapa única) — critérios 3, 5, 6, 8.

    Motivo é obrigatório na tela (rótulo próprio, avisando que fica na
    trilha); a recusa de verdade é do serviço (`reabrir_competencia`,
    `CompetenciaOperacaoInvalida` para motivo vazio). Mês já entregue
    (RC-101/BL-468) NUNCA oferece este formulário — nem no GET (precheck de
    conveniência) nem, se a corrida acontecer, no POST (a exceção
    `CompetenciaJaEntregue` do serviço vira mensagem, nunca 500).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite reabrir competências desta empresa — essa ação "
            "exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_REABRIR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        motivo = request.POST.get("motivo", "")
        try:
            reabrir_competencia(
                empresa=empresa,
                ano=ano,
                mes=mes,
                usuario=request.user,
                motivo=motivo,
                request=request,
            )
        except CompetenciaOperacaoInvalida as exc:
            # Critério 3: motivo vazio é erro de FORMULÁRIO — a tela NUNCA
            # some (o que já estava preenchido continua lá), status 400.
            messages.error(request, str(exc))
            return render(
                request,
                "contabilidade/competencia_reabrir.html",
                {"empresa": empresa, "ano": ano, "mes": mes, "motivo": motivo},
                status=400,
            )
        except CompetenciaJaEntregue as exc:
            # Critério 6/BL-468: a mensagem do serviço já nomeia a data da
            # entrega e orienta o ajuste no mês aberto (RC-101). Nunca 500
            # (BL-457) — controle positivo no mesmo caso, no teste desta tela.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)
        except CompetenciaOperacaoRecusada as exc:
            # Ex.: tentar reabrir uma competência que nunca foi encerrada.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        messages.success(request, f"Competência {mes:02d}/{ano} de {empresa} reaberta com sucesso.")
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: só oferece o formulário quando há, de fato, o que reabrir.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is None or competencia.estado != EstadoCompetencia.ENCERRADA:
        messages.info(
            request,
            f"A competência {mes:02d}/{ano} de {empresa} não está encerrada; não há o que reabrir.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)
    if competencia.entregue_em is not None:
        # Critério 6/BL-468 — precheck de conveniência: o servidor recusa do
        # mesmo jeito se a corrida acontecer (ver o `except
        # CompetenciaJaEntregue` acima), mas o contador nunca deveria
        # precisar clicar num formulário para descobrir isto.
        messages.error(
            request,
            f"A competência {mes:02d}/{ano} de {empresa} já foi entregue ao cliente em "
            f"{timezone.localtime(competencia.entregue_em):%d/%m/%Y %H:%M}. Depois da "
            "entrega, a competência não reabre — o ajuste vai no mês aberto.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    contexto = {"empresa": empresa, "ano": ano, "mes": mes, "motivo": ""}
    return render(request, "contabilidade/competencia_reabrir.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
@_sem_contabilidade_para_livro_caixa
def competencia_entregar(request, empresa_id):
    """Marca uma competência como entregue ao cliente (arquétipo E, etapa
    única) — critérios 4, 5, 8.

    Esta é a ÚNICA ação da fatia sem volta pelo produto (RC-101: depois de
    entregue, a competência nunca mais reabre) — por isso exige uma
    confirmação EXPLÍCITA (caixa de marcação), não um único clique.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_fechar_competencia(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite marcar competências desta empresa como entregues "
            "— essa ação exige administrador ou gestor (RC-102). Fale com um deles.",
        )

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro_competencia = _competencia_pedida(fonte)
    if erro_competencia:
        messages.error(request, erro_competencia)
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ENTREGAR_COMPETENCIA)
        except DadoNaoContratado as exc:
            messages.error(request, _mensagem_de_tela_para_dado_nao_contratado(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        # Critério 4: a caixa de confirmação NÃO é regra de negócio — o
        # serviço não sabe dela e não precisa saber. É só o que impede um
        # clique não intencional de chegar ao serviço, proporcional ao
        # risco desta ação (AGENTS.md §0, item 6: ação sem volta pede
        # confirmação que identifique a operação).
        if request.POST.get("confirmar_entrega") != "1":
            messages.error(
                request,
                "Confirme a caixa de seleção para marcar esta competência como "
                "entregue — nada foi gravado.",
            )
            return render(
                request,
                "contabilidade/competencia_entregar.html",
                {"empresa": empresa, "ano": ano, "mes": mes},
                status=400,
            )

        try:
            marcar_competencia_como_entregue(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except CompetenciaOperacaoRecusada as exc:
            # Ex.: tentar entregar uma competência que ainda está aberta.
            messages.error(request, str(exc))
            return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

        messages.success(
            request,
            f"Competência {mes:02d}/{ano} de {empresa} marcada como entregue. Depois da "
            "entrega, ela não reabre pelo produto — qualquer ajuste vai no mês aberto "
            "(RC-101).",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    # GET: só oferece a confirmação quando a competência está encerrada —
    # entregar mês aberto não faz sentido e o serviço recusaria mesmo assim.
    competencia = Competencia.objects.filter(empresa=empresa, ano=ano, mes=mes).first()
    if competencia is None or competencia.estado != EstadoCompetencia.ENCERRADA:
        messages.info(
            request,
            f"Só é possível marcar como entregue uma competência encerrada; feche a "
            f"competência {mes:02d}/{ano} de {empresa} primeiro.",
        )
        return redirect("contabilidade_web:fechamento", empresa_id=empresa.id)

    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        # Docstring de marcar_competencia_como_entregue (services.py): a
        # entrega "pode repetir-se" — confirmar de novo apenas atualiza a
        # data/quem entregou. A tela avisa a diferença em vez de tratar como
        # se fosse a primeira vez.
        "ja_entregue_em": competencia.entregue_em,
    }
    return render(request, "contabilidade/competencia_entregar.html", contexto)
