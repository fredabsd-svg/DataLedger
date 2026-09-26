"""Contexto de navegação global do menu (DL-040).

Injeta, em TODA renderização de template (via `TEMPLATES[...]["OPTIONS"]
["context_processors"]`, `config/settings.py`), o que o menu principal
(`templates/base.html`) precisa decidir SEM reimplementar regra de negócio:
se o papel ativo pode ver os itens de Contabilidade/Fiscal do menu —
reaproveitando as MESMAS funções de permissão do domínio
(`apps.contabilidade.permissoes.papel_pode_ler_contabilidade`,
`apps.fiscal.permissoes.papel_pode_consultar_documentos`), nunca uma lista
nova de papéis (AGENTS.md §8/§11: "evitar duplicação de regras entre
tela... permissões").

O menu só decide o que CONVIDA a ver; a recusa de verdade continua sendo a
do servidor em cada view (esta função nunca autoriza nada, só informa a
apresentação).

**Decisão deliberada: nenhuma consulta ao banco aqui.** Uma primeira versão
desta função também expunha a lista de EMPRESAS do escritório ativo, para
um seletor de troca de empresa dentro do cabeçalho de cada tela de
contabilidade — e isso violava, na própria tela de UMA empresa, a garantia
de isolamento entre empresas que o AGENTS.md declara ("Dados de empresas
diferentes ficam isolados") e que
`apps.contabilidade.tests.test_dl031_fechamento_de_competencia.
test_isolamento_painel_de_uma_empresa_nao_mostra_competencia_de_outra` já
mede: a página do fechamento da empresa A passava a conter, no HTML, a
razão social da empresa B (mesmo escritório, MAS ainda assim uma empresa
diferente). A troca de empresa continua existindo — `empresas:trocar-
secao` (`apps.empresas.views.trocar_empresa_na_secao`) — mas o CAMINHO até
ela é `templates/empresas/lista.html` (a tela cujo propósito já É listar
todas as empresas do escritório; não há isolamento a proteger ali), nunca
um seletor embutido em toda tela de uma empresa específica.
"""

from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.fiscal.permissoes import papel_pode_consultar_documentos


def navegacao_do_menu(request):
    papel = getattr(request, "papel", None)
    return {
        "pode_ler_contabilidade_no_menu": papel_pode_ler_contabilidade(papel),
        "pode_consultar_fiscal_no_menu": papel_pode_consultar_documentos(papel),
    }
