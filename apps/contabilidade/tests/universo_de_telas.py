"""Universo de telas do produto — módulo de APOIO (BL-352, rodada 10 da
auditoria DL-026, docs/auditorias/2026-09-19-dl-026-rodada-7.md, achado G2).

NÃO é coletado como teste: nenhuma função aqui começa com `test_`, e o nome
do arquivo não casa com `python_files = ["test_*.py"]` (pyproject.toml) —
`pytest` nunca importa este módulo por conta própria; ele só existe para ser
importado pelas guardas.

O DEFEITO que este módulo existe para fechar: `NOMES_DE_TELA_DE_
CONTABILIDADE` e `NOMES_DE_TELA_FORA_DA_CONTABILIDADE` viviam dentro de
`test_dl024_atalhos_e_acessibilidade.py`, e a guarda de título
(`test_bl332_titulo_sem_marca_do_fornecedor.py`) importava só o primeiro —
8 telas. A guarda irmã, escrita no MESMO commit
(`test_bl338_operador_fora_do_papel.py`), já sabia que a pergunta "esta tela
existe no produto?" precisa da UNIÃO dos dois — 14 telas, das quais 12 entram
no seu próprio recorte (`_NOMES_DE_ROTA_COM_ESCRITORIO`, que ainda subtrai
duas sem `request.escritorio`) — e reconstruía essa união por conta própria.
Duas fontes para o
mesmo fato divergiram no commit que as criou; o auditor mediu a divergência
em menos de uma hora (rodada 7, G2), transformando `templates/empresas/
lista.html` numa tela de documento coerente e mostrando que a guarda de
título nem chegava a olhar para ela.

A CORREÇÃO promove o UNIVERSO — o conjunto completo de rotas que renderizam
uma tela HTML do produto — a um lugar só. O que ela **não** faz é promover
também um RECORTE já filtrado para uma guarda específica: `_NOMES_DE_ROTA_
COM_ESCRITORIO` (em test_bl338) subtrai as telas sem `request.escritorio`
porque ISSO é específico da guarda do escritório ativo; a propriedade do
TÍTULO não depende de `request.escritorio` nenhum, e herdar aquela exclusão
por acidente seria o MESMO defeito de novo, só que um passo adiante (lista
compartilhada em vez de lista duplicada, mas ainda assim uma lista de
exceções que não pertence à guarda que a usa sem questionar). Por isso:
cada guarda que importar `UNIVERSO_DE_ROTAS_DE_TELA` declara, NELA MESMA, em
comentário, o seu próprio recorte e o motivo — nunca aqui.

Dados: nenhum diretamente. As funções abaixo só resolvem URLs (`django.urls.
reverse`) a partir de um dicionário de cenário (`empresa`/`caixa`/
`lancamento`, no formato que os testes deste pacote já usam) — não criam
registro nenhum.
"""

from django.urls import reverse
from django.utils import timezone

# nome CURTO (usado no `parametrize` e como chave de conveniência) → nome
# COMPLETO da rota (`namespace:nome`, o que `django.urls.reverse` aceita) —
# as oito telas de `templates/contabilidade/`, atrás do namespace
# `contabilidade_web`. ÚNICA fonte: antes vivia em
# `test_dl024_atalhos_e_acessibilidade.py` (BL-334); promovida aqui pelo
# BL-352 para ser a MESMA fonte que qualquer guarda de qualquer arquivo usa,
# em vez de cada uma reimportar de um arquivo de teste alheio.
NOMES_DE_TELA_DE_CONTABILIDADE = {
    "plano_de_contas": "contabilidade_web:plano_de_contas",
    "conta_nova": "contabilidade_web:conta_nova",
    "diario": "contabilidade_web:diario",
    "razao": "contabilidade_web:razao",
    "balancete": "contabilidade_web:balancete",
    # DL-034: sob o cenário PADRÃO deste módulo (plano de contas simples,
    # sem `classificacao_patrimonial`), a tela renderiza 200 no estado "não
    # pode emitir" (ver `views_web.py::balanco` e `avaliar_emissao_do_
    # balanco` em services.py) — é um 200 de verdade, não uma exceção
    # tolerada: a tela RESPONDE corretamente "não, e eis o porquê", nunca
    # 500.
    "balanco": "contabilidade_web:balanco",
    "conferencia": "contabilidade_web:conferencia",
    "lancamento_novo": "contabilidade_web:lancamento_novo",
    "lancamento_detalhe": "contabilidade_web:lancamento_detalhe",
    # DL-031 (fatia 2 da DL-016): só as DUAS telas do fechamento que
    # renderizam 200 sob o `cenario` PADRÃO deste módulo (competência ainda
    # 'aberta', sem lote desbalanceado) entram aqui. `competencia_reabrir` e
    # `competencia_entregar` exigem competência ENCERRADA como
    # pré-condição de estado — sem isso a view devolve 302 para o painel
    # (nunca 500, é o comportamento certo) — e por isso ficam de fora desta
    # lista genérica; ver `EXCLUSOES_NOMEADAS_DE_TELA`, em
    # test_dl024_atalhos_e_acessibilidade.py, e os testes próprios em
    # test_dl031_fechamento_de_competencia.py, que preparam o cenário certo
    # (competência fechada) antes de medir essas duas telas.
    "fechamento": "contabilidade_web:fechamento",
    "competencia_fechar": "contabilidade_web:competencia_fechar",
}

# rota COMPLETA (`namespace:nome`) → documentação (nome dos testes desta
# suíte que exercitam a renderização real dela — só para quem lê; a fonte de
# verdade da COBERTURA continua sendo
# `test_toda_rota_do_produto_esta_coberta_ou_excluida`, em
# test_dl024_atalhos_e_acessibilidade.py). Seis telas de FORA de
# `templates/contabilidade/`, todas estendendo a MESMA moldura
# (`base.html`). Movida aqui pelo BL-352 pela mesma razão da anterior.
NOMES_DE_TELA_FORA_DA_CONTABILIDADE = {
    "login": "test_tela_de_login_e_acessivel",
    "empresas:lista": (
        "test_tela_empresas_lista_e_acessivel, "
        "test_tela_empresas_sem_escritorio_e_acessivel, "
        "test_mutacao_accesskey_colidente_em_empresas_lista_e_detectada"
    ),
    "empresas:criar": (
        "test_tela_empresas_form_e_acessivel, test_tela_erro_sem_permissao_e_acessivel"
    ),
    "tenancy:painel": (
        "test_tela_painel_e_acessivel, "
        "test_mutacao_accesskey_colidente_em_tenancy_painel_e_detectada"
    ),
    "tenancy:aceitar-convite": "test_tela_aceitar_convite_e_acessivel",
    "tenancy:bootstrap-primeiro-acesso": "test_tela_bootstrap_primeiro_acesso_e_acessivel",
}

# A UNIÃO completa — o que este módulo existe para compartilhar. Qualquer
# guarda que precise saber "quais telas o produto tem" parte DAQUI, nunca de
# uma soma reconstruída à mão de `NOMES_DE_TELA_DE_CONTABILIDADE.values()`
# com `NOMES_DE_TELA_FORA_DA_CONTABILIDADE` (a MESMA soma, escrita duas
# vezes, foi exatamente o que divergiu no BL-352/G2).
UNIVERSO_DE_ROTAS_DE_TELA = frozenset(NOMES_DE_TELA_DE_CONTABILIDADE.values()) | frozenset(
    NOMES_DE_TELA_FORA_DA_CONTABILIDADE
)


def _urls_de_contabilidade(cenario):
    """URL completa de cada tela de `NOMES_DE_TELA_DE_CONTABILIDADE`, para
    um `cenario` de teste com `empresa`/`caixa`/`lancamento` (o formato que
    as fixtures `cenario`/`cenario_bl338`/`cenario_bl344` já produzem).
    Movida de `test_dl024_atalhos_e_acessibilidade.py` (BL-334) para
    `universo_de_telas.py` (BL-352) — mesma função, mesmo comportamento,
    fonte única."""
    empresa_id = cenario["empresa"].id
    inicio = timezone.localdate().replace(day=1).isoformat()
    fim = timezone.localdate().isoformat()
    periodo = f"?inicio={inicio}&fim={fim}"
    # Nomes de rota vêm de NOMES_DE_TELA_DE_CONTABILIDADE — nunca retypados
    # aqui —, só os `args`/query string (que dependem do cenário) continuam
    # próprios de cada rota.
    args_por_tela = {
        "plano_de_contas": ([empresa_id], ""),
        "conta_nova": ([empresa_id], ""),
        "diario": ([empresa_id], periodo),
        "razao": ([empresa_id, cenario["caixa"].id], periodo),
        "balancete": ([empresa_id], periodo),
        # DL-034: sem querystring — a tela usa HOJE como data-base padrão
        # (mesma convenção de conveniência do período do Balancete/Diário/
        # Razão), nunca um padrão do motor de cálculo.
        "balanco": ([empresa_id], ""),
        "conferencia": ([empresa_id], ""),
        "lancamento_novo": ([empresa_id], ""),
        "lancamento_detalhe": ([empresa_id, cenario["lancamento"].id], ""),
        "fechamento": ([empresa_id], ""),
        # ?ano=&mes= do mês CORRENTE: sob o `cenario` padrão a competência
        # do mês corrente ainda está 'aberta' (só existe porque a fixture
        # cria um lançamento nela) e a base está balanceada — exatamente o
        # estado em que `competencia_fechar` (GET) renderiza o formulário
        # de confirmação, 200.
        "competencia_fechar": (
            [empresa_id],
            f"?ano={timezone.localdate().year}&mes={timezone.localdate().month}",
        ),
    }
    return {
        nome_curto: reverse(NOMES_DE_TELA_DE_CONTABILIDADE[nome_curto], args=args) + query
        for nome_curto, (args, query) in args_por_tela.items()
    }


# Args posicionais de `reverse` para cada rota de FORA da contabilidade —
# mecânica de construção de URL, comum a QUALQUER guarda que precise
# renderizar essas seis telas (não é um recorte: as SEIS entram aqui, mesmo
# que uma guarda específica não consiga, ou não precise, exercitar todas —
# a decisão de QUAIS usar é da guarda, feita sobre `UNIVERSO_DE_ROTAS_DE_
# TELA`, nunca deste dicionário).
ARGS_DE_ROTA_FORA_DA_CONTABILIDADE = {
    "login": [],
    "empresas:lista": [],
    "empresas:criar": [],
    "tenancy:painel": [],
    "tenancy:aceitar-convite": ["token-inexistente-bl352"],
    "tenancy:bootstrap-primeiro-acesso": [],
}


def url_por_nome_de_rota(nome_de_rota, cenario):
    """URL completa para `nome_de_rota` (`namespace:nome`), cobrindo TODA a
    `UNIVERSO_DE_ROTAS_DE_TELA` — tanto as de `NOMES_DE_TELA_DE_
    CONTABILIDADE` (via `_urls_de_contabilidade`, que resolve `args`/query
    string a partir do `cenario`) quanto as de `NOMES_DE_TELA_FORA_DA_
    CONTABILIDADE` (via `ARGS_DE_ROTA_FORA_DA_CONTABILIDADE`). Generalizada,
    pelo BL-352, de `_url_por_nome_de_rota` (antes só em
    `test_bl338_operador_fora_do_papel.py`) para ser a MESMA função que
    qualquer guarda usa — em vez de cada arquivo reimplementar o mesmo
    despacho entre os dois dicionários."""
    nomes_curtos_por_rota_completa = {
        rota: curto for curto, rota in NOMES_DE_TELA_DE_CONTABILIDADE.items()
    }
    if nome_de_rota in nomes_curtos_por_rota_completa:
        nome_curto = nomes_curtos_por_rota_completa[nome_de_rota]
        return _urls_de_contabilidade(cenario)[nome_curto]
    return reverse(nome_de_rota, args=ARGS_DE_ROTA_FORA_DA_CONTABILIDADE[nome_de_rota])
