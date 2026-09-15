"""Módulo de escolha fechada compartilhado (BL-141, achado R5-2 da
auditoria DL-017 rodada 5 — o quarto irmão de `dinheiro.py`/`datas.py`/
`identificadores.py`).

O defeito original: `apps/empresas/views.py` lia `regime = request.data.
get("regime")` e entregava o valor direto a `registrar_regime_tributario`
(`apps/empresas/services.py`), que faz `HistoricoRegimeTributario.objects.
create(regime=regime, ...)` sem checagem nenhuma de tipo ou de `choices`.
Medido pelo auditor: uma lista, um dicionário, um número, um booleano e um
texto fora das `choices` eram todos GRAVADOS — `str(valor)` do Python vira
literalmente o texto salvo (`"['simples_nacional']"`, `"{'a': 1}"`) — e um
texto de 500 caracteres derrubava a gravação com `DataError` (500 cru,
`max_length=20` do campo).

**Por que um módulo, e não só um `if` local:** o mesmo padrão seguro já
existia em `apps.contabilidade.views._extrair_itens` (`tipo not in
TipoPartida.values`) — correto por acidente de forma (uma checagem de
pertencimento a uma lista fechada nunca levanta exceção, seja qual for o
tipo do valor testado), mas escrito duas vezes de formas ligeiramente
diferentes é exatamente a duplicação que a DE-026 existe para impedir, e a
DE-034 manda varrer o repositório todo por esse padrão, não só o campo
apontado pelo relatório. Este módulo dá um NOME e um contrato explícito a
essa checagem, para toda `APIView` escrita à mão (fora de um
`ModelSerializer`, que já tem `ChoiceField` cuidando disso sozinho — ver a
nota no fim do docstring).

Decisão de desenho: `ChoiceField` do DRF na fronteira resolveria o mesmo
problema, mas só para views que já usam `Serializer`/`ModelSerializer` —
`HistoricoRegimeTributarioListCreateView.post` é uma view ESCRITA À MÃO
(como `LancamentoListCreateView.post`, em contabilidade), que lê
`request.data` diretamente. Um julgador de função simples, no mesmo molde
de `para_decimal`/`para_data`/`para_id`, serve às duas situações (view
escrita à mão E qualquer lugar que precise validar uma escolha fora de um
serializer) sem introduzir um serializer só para isto.
"""


class EscolhaInvalida(Exception):
    """Levantada quando um valor não é exatamente um dos valores aceitos.

    Cobre: qualquer tipo que não seja `str` (lista, dicionário, número,
    `bool`, `None` — nenhum deles é comparado por engano a uma opção
    válida, porque a comparação de pertencimento (`in`) nunca levanta,
    mas também nunca aceita algo que não seja uma string EXATAMENTE igual
    a uma das opções) e texto que não esteja entre as opções declaradas
    (incluindo variação de maiúsculas/minúsculas e espaço em volta — nunca
    normalizado em silêncio).
    """


def para_escolha(valor, opcoes_validas, *, nome_campo):
    """Recusa `valor` que não seja EXATAMENTE um dos `opcoes_validas`.

    `opcoes_validas` deve ser uma SEQUÊNCIA de `str` (lista ou tupla —
    `Enum.values` de um `django.db.models.TextChoices`, como
    `RegimeTributario.values`, já devolve uma lista). NUNCA um `set`:
    comparar um valor não-hasheável (lista, dicionário — exatamente os
    tipos que este módulo existe para recusar) contra um `set` levanta
    `TypeError` na própria checagem `in`, antes mesmo de chegar à recusa
    controlada — o oposto do que este módulo promete.

    Nunca normaliza (não tira espaço, não muda maiúscula/minúscula): um
    valor fora da grafia exata é RECUSADO, nunca corrigido em silêncio —
    mesma política do resto do módulo monetário/de data/de identificador
    (`apps.core.dinheiro`/`datas`/`identificadores`). `" simples_nacional "`
    com espaço é tão inválido quanto `"SIMPLES_NACIONAL"` com maiúsculas.

    `nome_campo` entra só na mensagem de erro, para o cliente da API saber
    qual campo recusou sem o chamador precisar montar a mensagem toda.
    """
    if valor not in opcoes_validas:
        raise EscolhaInvalida(
            f"'{nome_campo}' inválido: {valor!r}. Use um destes valores: "
            f"{', '.join(sorted(opcoes_validas))}."
        )
    return valor
