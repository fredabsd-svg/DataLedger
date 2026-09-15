"""Política única dos cinco dicionários de uma requisição (BL-196, achado
R6-2 da auditoria DL-017 rodada 6).

Espelha `apps.core.dinheiro`, `apps.core.datas`, `apps.core.escolhas` e
`apps.core.identificadores`, e pelo mesmo motivo (DE-026): a regra mora num
lugar só, e **este módulo não responde HTTP**. Ele julga; quem responde é a
view — a tela re-renderiza o formulário com 400 e o que o usuário digitou, a
API devolve 400 em JSON. Por isso aqui não se importa nada de
`apps.contabilidade`, nem classe de resposta do Django, nem nada do DRF.

## O defeito que originou o módulo

O critério da BL-145 — *"nenhum dado enviado numa requisição deixa de ser
lido ou recusado, em nenhuma superfície e em nenhum dicionário"* — fechou em
**1 de 7** superfícies de escrita. O auditor mediu, autenticado e com payload
válido:

    POST conta_nova, `conta_pai` enviado como ARQUIVO (multipart)
    -> 302 "gravado", conta criada, conta_pai = None -> ficou RAIZ em silêncio

O contador escreveu "esta conta é filha de 1"; o sistema gravou uma conta
raiz, com redirecionamento de sucesso e sem uma palavra — o que muda a
indentação do plano, o nível e o Balancete por nível. A defesa já existia, a
40 linhas de distância, no MESMO arquivo (`lancamento_novo`). Querystring em
POST e campo desconhecido eram ignorados em silêncio em `conta_nova`,
`ativar_escritorio` e nas rotas de escrita da API.

## Os cinco dicionários, e o que este módulo faz com cada um

**1. Arquivos (`request.FILES`).** Recusado por completo, a não ser que o
contrato declare `aceita_arquivo=True`.

**2. Querystring (`request.GET` / `query_params`).** Recusada, a não ser que o
contrato declare `aceita_querystring=True`.

**3. Cabeçalhos (`request.headers` / `META`).** Só os NOMEADOS em
`cabecalhos_ignorados` são recusados. Uma requisição real tem dezenas de
cabeçalhos legítimos (`Cookie`, `Accept`, `User-Agent`), e recusar "todo
cabeçalho não contratado" quebraria qualquer navegador. O contrato nomeia os
cabeçalhos que **aquela superfície ignora de propósito** e que, por isso,
precisam falhar alto em vez de baixo — o caso real é `Idempotency-Key` na
tela, que não usa cabeçalho para idempotência e produzia DUPLICIDADE em
silêncio para quem o enviava.

**4. Corpo já decodificado** (`request.POST` na tela, `request.data` na API).
Toda chave fora de `campos` é recusada, nomeando a chave.

**5. Corpo bruto.** **Não** é lido aqui, e isso é decisão, não esquecimento: o
corpo bruto só chega a este sistema pelo decodificador da superfície
(formulário ou parser do DRF). Um corpo que o decodificador não entenda não
fica "ignorado em silêncio" — ou o parser já recusa com 400, ou o dicionário
decodificado sai vazio e a validação de campo obrigatório recusa. Não existe,
hoje, caminho em que um corpo bruto não lido produza gravação com aparência de
sucesso; se algum dia existir (ex.: uma rota que aceite
`application/octet-stream`), é aqui que a checagem entra.

## Ordem de avaliação — DECLARADA, porque a mensagem depende dela

`ORDEM_DE_AVALIACAO`, nesta ordem fixa: **arquivo, querystring, cabeçalho,
corpo**. É a mesma ordem que a tela de lançamento já usava quando o auditor
mediu as três recusas como corretas, e ela é estável de propósito: a
mensagem que o usuário vê depende de qual violação é encontrada primeiro, e
há teste de tela em cima desse texto. Mudar a ordem é mudar comportamento
observável.

## Uso

    from apps.core.requisicao import (
        ContratoDeRequisicao,
        DadoNaoContratado,
        recusar_dado_nao_contratado,
    )

    CONTRATO = ContratoDeRequisicao(
        campos={"codigo", "nome"},
        cabecalhos_ignorados=("Idempotency-Key",),
        contexto="no cadastro de conta",
    )

    try:
        recusar_dado_nao_contratado(request, CONTRATO)
    except DadoNaoContratado as exc:
        # A view monta a resposta da SUA superfície com `exc.dicionario`,
        # `exc.chaves`, `exc.razao` e/ou `exc.mensagem`.
        ...
"""

from collections.abc import Mapping

# Identificadores ESTÁVEIS do dicionário violado. São o que permite a cada
# superfície montar a sua própria mensagem (a tela tem três textos
# específicos por dicionário, que o auditor já mediu como corretos) sem
# precisar comparar texto de mensagem — comparar texto amarraria a tela à
# redação deste módulo.
DICIONARIO_ARQUIVO = "arquivo"
DICIONARIO_QUERYSTRING = "querystring"
DICIONARIO_CABECALHO = "cabecalho"
DICIONARIO_CORPO = "corpo"

# Ver "Ordem de avaliação" no docstring do módulo: fixa e declarada, porque
# a mensagem que o usuário vê depende de qual violação vem primeiro.
ORDEM_DE_AVALIACAO = (
    DICIONARIO_ARQUIVO,
    DICIONARIO_QUERYSTRING,
    DICIONARIO_CABECALHO,
    DICIONARIO_CORPO,
)


class DadoNaoContratado(Exception):
    """Algum dado enviado na requisição não é lido por esta superfície.

    Exceção ÚNICA do módulo, de propósito: quem captura não precisa saber
    quantos dicionários existem. O que distingue os casos são os atributos,
    todos acessíveis separadamente — nenhuma superfície deve precisar
    interpretar a mensagem para saber o que aconteceu:

    - `dicionario`: uma das constantes `DICIONARIO_*` (texto estável,
      comparável).
    - `chaves`: tupla ordenada das chaves ofensoras. Sempre tupla, sempre
      ordenada (mensagem determinística entre execuções — `set` não tem
      ordem estável).
    - `razao`: frase curta em pt-BR explicando o que a superfície não
      aceita, SEM as chaves.
    - `mensagem`: a frase pronta, com as chaves, para quem só quer exibir.
      É também o `str()` da exceção.
    """

    def __init__(self, *, dicionario, chaves, razao, mensagem):
        self.dicionario = dicionario
        self.chaves = tuple(chaves)
        self.razao = razao
        self.mensagem = mensagem
        super().__init__(mensagem)


class ContratoDeRequisicao:
    """Declaração do que UMA superfície de escrita aceita receber.

    - `campos`: nomes aceitos no corpo já decodificado. `None` significa
      "este contrato não julga o corpo" (para uma view cujo corpo é julgado
      por outro ponto, item a item por exemplo); `frozenset()` significa
      "nenhum campo é aceito no corpo", que é diferente e é o contrato certo
      de uma rota de ação sem corpo (o estorno, por exemplo).
      Campos dinâmicos (`conta_1`, `tipo_1`, … da tela de lançamento) entram
      como lista já expandida por quem chama: expandir é trivial no
      chamador, que é quem sabe o teto da própria tela, e um contrato por
      expressão regular seria uma segunda gramática para manter.
    - `aceita_arquivo` / `aceita_querystring`: o padrão é `False` para os
      dois, porque nenhuma superfície de escrita deste sistema oferece
      upload ou tem contrato de querystring em POST. Quem passar a oferecer
      declara aqui.
    - `cabecalhos_ignorados`: cabeçalhos que esta superfície ignora DE
      PROPÓSITO e que, por isso, devem falhar alto. Ver a tabela no
      docstring do módulo para o motivo de a recusa de cabeçalho ser por
      lista nomeada, e não por exclusão.
    - `contexto`: trecho em pt-BR que entra na mensagem de campo
      desconhecido ("no lançamento", "em um item"), para o cliente saber
      ONDE estava a chave recusada num corpo com estrutura aninhada.
    """

    __slots__ = (
        "campos",
        "aceita_arquivo",
        "aceita_querystring",
        "cabecalhos_ignorados",
        "contexto",
    )

    def __init__(
        self,
        *,
        campos=None,
        aceita_arquivo=False,
        aceita_querystring=False,
        cabecalhos_ignorados=(),
        contexto="",
    ):
        self.campos = None if campos is None else frozenset(campos)
        self.aceita_arquivo = bool(aceita_arquivo)
        self.aceita_querystring = bool(aceita_querystring)
        self.cabecalhos_ignorados = tuple(cabecalhos_ignorados)
        self.contexto = contexto


def _com_contexto(contexto):
    """Devolve " no lançamento" a partir de "no lançamento" — ou "" se vazio."""
    return f" {contexto}" if contexto else ""


def _chaves_ordenadas(dicionario):
    """Chaves em ordem estável, como texto.

    `sorted()` sobre as chaves de um `QueryDict`/`dict` as devolve na mesma
    ordem em toda execução; sem isso, a mensagem mudaria de uma requisição
    para a outra e nenhum teste de texto poderia existir.
    """
    return tuple(sorted(str(chave) for chave in dicionario))


def _valor_de_cabecalho(requisicao, nome):
    """Valor do cabeçalho `nome`, sem depender de `request.headers` existir.

    `request.headers` (Django ≥ 2.2) é a forma canônica e é o que a
    `Request` do DRF também expõe. O acesso a `META` fica como segunda via
    porque `recusar_dado_nao_contratado` também é usada em teste unitário
    com objeto de requisição mínimo — e porque um cabeçalho presente e não
    lido é exatamente o defeito que este módulo existe para impedir: é
    melhor procurá-lo em dois lugares do que deixá-lo passar por causa da
    forma do objeto.
    """
    cabecalhos = getattr(requisicao, "headers", None)
    if cabecalhos is not None:
        valor = cabecalhos.get(nome)
        if valor:
            return valor
    meta = getattr(requisicao, "META", None) or {}
    return meta.get("HTTP_" + nome.upper().replace("-", "_"))


def _corpo_decodificado(requisicao):
    """O dicionário do corpo JÁ DECODIFICADO pela superfície.

    `request.data` quando existir (a `Request` do DRF: cobre JSON,
    formulário e multipart), `request.POST` caso contrário (view de tela,
    `HttpRequest` do Django). A escolha é por presença de atributo, não por
    `isinstance`, justamente para não importar DRF aqui.

    Pode devolver algo que não é `Mapping` (uma lista JSON no topo, por
    exemplo) — quem chama trata isso como "não há campos para julgar", e é
    o certo: outra checagem, mais adiante, recusa estrutura errada com uma
    mensagem melhor do que esta poderia dar.
    """
    dados = getattr(requisicao, "data", None)
    if dados is not None:
        return dados
    return getattr(requisicao, "POST", None)


def recusar_campos_nao_contratados(dados, campos_aceitos, *, contexto=""):
    """Levanta `DadoNaoContratado` se `dados` tiver chave fora de `campos_aceitos`.

    Pública porque o corpo da API tem estrutura ANINHADA: o topo do
    lançamento e cada item da lista de partidas são dois dicionários
    diferentes, com listas de campos diferentes, e o segundo não é
    alcançável pelo contrato do primeiro. Sem esta função, `views.py`
    reimplementaria a mesma subtração de conjuntos — que é o que a BL-196
    existe para impedir.

    Não faz nada se `dados` não for um `Mapping`: ver
    `_corpo_decodificado`.
    """
    if not isinstance(dados, Mapping):
        return
    campos_aceitos = frozenset(campos_aceitos)
    desconhecidos = tuple(sorted(str(chave) for chave in set(dados) - campos_aceitos))
    if not desconhecidos:
        return
    razao = "Esta requisição não reconhece o(s) campo(s) enviado(s) no corpo."
    aceitos = ", ".join(sorted(campos_aceitos)) or "nenhum"
    raise DadoNaoContratado(
        dicionario=DICIONARIO_CORPO,
        chaves=desconhecidos,
        razao=razao,
        mensagem=(
            f"Campo(s) não reconhecido(s){_com_contexto(contexto)}: "
            f"{', '.join(desconhecidos)}. Campos aceitos: {aceitos}."
        ),
    )


def recusar_dado_nao_contratado(requisicao, contrato):
    """Julga os cinco dicionários de `requisicao` contra `contrato`.

    Devolve `None` quando nada sobra. Levanta `DadoNaoContratado` na
    PRIMEIRA violação encontrada, seguindo `ORDEM_DE_AVALIACAO` — nunca
    monta resposta HTTP, nunca grava nada, nunca registra auditoria.

    Chamar isto ANTES de qualquer gravação é responsabilidade de quem usa:
    um dado ignorado recusado depois do `save()` não repara nada.
    """
    arquivos = getattr(requisicao, "FILES", None) or {}
    if arquivos and not contrato.aceita_arquivo:
        chaves = _chaves_ordenadas(arquivos)
        raise DadoNaoContratado(
            dicionario=DICIONARIO_ARQUIVO,
            chaves=chaves,
            razao="Esta requisição não aceita arquivo nenhum.",
            mensagem=(
                "Esta requisição não aceita arquivo nenhum. Campo(s) enviados "
                f"como arquivo, recusados por completo: {'; '.join(chaves)}."
            ),
        )

    querystring = getattr(requisicao, "query_params", None)
    if querystring is None:
        querystring = getattr(requisicao, "GET", None) or {}
    if querystring and not contrato.aceita_querystring:
        chaves = _chaves_ordenadas(querystring)
        raise DadoNaoContratado(
            dicionario=DICIONARIO_QUERYSTRING,
            chaves=chaves,
            razao="Esta requisição não aceita parâmetros na URL.",
            mensagem=(
                "Esta requisição não aceita parâmetros na URL. Parâmetro(s) "
                f"recusados por completo: {'; '.join(chaves)}."
            ),
        )

    presentes = tuple(
        nome for nome in contrato.cabecalhos_ignorados if _valor_de_cabecalho(requisicao, nome)
    )
    if presentes:
        raise DadoNaoContratado(
            dicionario=DICIONARIO_CABECALHO,
            chaves=presentes,
            razao=(
                "Esta requisição não usa o(s) cabeçalho(s) enviado(s) — nesta "
                "superfície eles não têm efeito nenhum."
            ),
            mensagem=(
                "Cabeçalho(s) sem efeito nesta requisição, recusados para não "
                f"passarem por lidos: {'; '.join(presentes)}."
            ),
        )

    if contrato.campos is not None:
        recusar_campos_nao_contratados(
            _corpo_decodificado(requisicao), contrato.campos, contexto=contrato.contexto
        )
