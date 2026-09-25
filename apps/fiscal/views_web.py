"""Telas de recepção e conferência de documentos fiscais (DL-010, fatia 1,
etapa 2 — `especialista-frontend`).

Molde: `apps.contabilidade.views_web` (DE-026, DL-017 fase B) — mesmos
princípios:

- Nenhuma regra de negócio é reimplementada aqui. Toda decisão de quem pode
  fazer o quê vem de `apps.fiscal.permissoes` (fonte única, DE-026); toda
  gravação e toda consulta vêm de `apps.fiscal.services` (contrato do plano
  DL-010-F1). Esta tela só resolve `request.escritorio`/`request.papel`
  (`EscritorioAtivoMiddleware` — nunca um valor enviado pelo cliente),
  formata para pt-BR e monta HTML.
- Cada view revalida o registro pedido (lote, documento, evento) contra
  `request.escritorio` — nunca um `<int:...>` cru da URL. Um registro de
  OUTRO escritório sempre dá 404, nunca 403 (critério 27 do plano): 404 não
  confirma nem a existência do registro para quem não tem acesso a ele.
- Autorização é verificada NO SERVIDOR (AGENTS.md §11): `papel_pode_
  receber_documentos`/`papel_pode_consultar_documentos`, nunca uma cópia
  local de "quem pode o quê".
- Formatação pt-BR é APRESENTAÇÃO: todo valor monetário permanece `Decimal`
  até o último instante, convertido para texto só pelas funções `_valor_
  ptbr`/`_milhar_ptbr` deste módulo — nunca um `float` em ponto nenhum
  (AGENTS.md §10).

## Duas decisões de permissão desta etapa (registradas aqui por não terem
## lugar melhor — não há decisao.md a acrescentar por este agente)

1. **Envio (`recepcao`) e o relatório de um envio (`relatorio_envio`) exigem
   `papel_pode_receber_documentos`** — o mesmo papel que fez (ou poderia
   fazer) o envio consegue ver o que aconteceu com ele. `PARALEGAL`, que
   `papel_pode_consultar_documentos` inclui, NÃO entra aqui: ele lê o
   ACERVO já recebido, não a operação de recepção em si.
2. **Lista de documentos, detalhe e download de XML (documento e evento)
   exigem `papel_pode_consultar_documentos`** — a leitura mais ampla, no
   mesmo espírito de `apps.contabilidade.permissoes.papel_pode_ler_
   contabilidade` (DE-026): todos os papéis MENOS `CLIENTE` (HI-21).

## A conversão "identificador da nota" -> "chave referenciada pelo evento"

`apps.fiscal.services.situacao_do_documento` documenta que a conversão
entre `DocumentoFiscal.identificador` ("NFS" + 50 dígitos, TSIdNFSe) e
`EventoFiscal.chave_nfse` (os mesmos 50 dígitos, SEM o prefixo, TSChaveNFSe)
"vive só ali" — mas aquele contrato só devolve um booleano (cancelada ou
não), e o detalhe do documento (critério de tela do plano) precisa LISTAR
os eventos, não só saber se algum cancela. Não existe, no contrato do
plano, uma função de serviço para "eventos que referenciam este documento"
— e `apps/fiscal/services.py` está fora dos arquivos que esta etapa pode
tocar. A view usa a MESMA fatia (`identificador[3:]`) que já é pública no
docstring de `DocumentoFiscal`/`EventoFiscal` (models.py: TSIdNFSe é "NFS" +
50 dígitos; TSChaveNFSe são os mesmos 50 dígitos sem prefixo) — não é uma
regra NOVA, é a mesma regra de formato, já documentada no modelo,
reaplicada aqui para uma LISTAGEM em vez de um booleano. Sinalizado no
relatório de entrega desta etapa como candidato a virar uma função própria
de `services.py` (`eventos_do_documento`), para o `desenvolvedor-pleno`
avaliar — sem ela, é este comentário, e não um segundo lugar silencioso,
que guarda a duplicação.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.models import Empresa
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, LoteDeRecepcao
from apps.fiscal.permissoes import papel_pode_consultar_documentos, papel_pode_receber_documentos
from apps.fiscal.services import (
    CODIGOS_QUE_CANCELAM,
    LIMITE_TAMANHO_ENVIO_BYTES,
    EnvioInvalido,
    documentos_do_escritorio,
    receber_envio,
    situacao_do_documento,
)
from apps.fiscal.uploads import LimiteDeTamanhoUploadHandler

# Tamanho de página das duas listas desta etapa (envios e documentos). Não é
# regra de negócio — é só quantas linhas cabem numa página de HTML antes de
# a tabela ficar pesada demais para renderizar/rolar; qualquer valor razoável
# serve, e este projeto não tem, ainda, uma convenção compartilhada de
# tamanho de página (nenhuma outra tela usa `Paginator` hoje — grep
# confirmado nesta etapa).
ITENS_POR_PAGINA = 25

# RC-110 (docs/planos/DL-010-F1-recepcao-nfse.md): os TRÊS valores possíveis
# de `tpRetISSQN`, já confirmados no plano — a tela só EXIBE o texto que o
# plano já registrou como fato lido do XSD, nunca interpreta nem calcula
# (limite declarado do plano: "a retenção de ISS é lida e exibida, não
# interpretada nem calculada"). Código fora deste mapa (não deveria
# acontecer — o leitor já valida o formato — mas a tela nunca confia só
# nisso) cai no `default` do template, mostrando o código cru em vez de
# quebrar.
DESCRICAO_TP_RET_ISSQN = {
    "1": "Não retido",
    "2": "Retido pelo tomador",
    "3": "Retido pelo intermediário",
}

# Textos exibidos para cada `resultado` de `ResultadoDoArquivo`
# (TipoResultadoArquivo.choices já dá "Recebido"/"Duplicado"/"Recusado" via
# get_resultado_display — este mapa é só para a CLASSE CSS, que precisa de
# um token estável e sem acento, nunca do texto exibido, que pode mudar).
CLASSE_CSS_POR_RESULTADO = {
    "recebido": "resultado-arquivo--recebido",
    "duplicado": "resultado-arquivo--duplicado",
    "recusado": "resultado-arquivo--recusado",
}

_SITUACOES_VALIDAS = frozenset({"valida", "cancelada"})


# ---------------------------------------------------------------------------
# Formatação de apresentação (mesmo espírito de `apps.contabilidade.
# views_web._valor_ptbr`/`_milhar_ptbr` — NÃO importado de lá: é
# apresentação pura, sem regra de negócio, e os dois módulos não têm uma
# dependência um do outro nem um lugar comum para este utilitário hoje.
# Sinalizado no relatório de entrega como candidato a `apps.core` — mover
# exigiria tocar em `apps/contabilidade/views_web.py`, fora dos arquivos
# desta etapa).
# ---------------------------------------------------------------------------


def _milhar_ptbr(parte_inteira):
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
    """`Decimal` -> texto pt-BR, sempre duas casas, '.' de milhar, ','
    decimal. Nunca recebe `float` (AGENTS.md §10) — `v_serv`/`v_liq` chegam
    como `Decimal` desde `apps.fiscal.leitor` (DE-010) e permanecem assim
    até aqui."""
    if valor is None:
        return "—"
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    sinal, digitos, expoente = quantizado.as_tuple()
    texto_digitos = "".join(str(d) for d in digitos).rjust(3, "0")
    parte_inteira = texto_digitos[:-2] or "0"
    parte_decimal = texto_digitos[-2:]
    resultado = f"{_milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if sinal else resultado


# ---------------------------------------------------------------------------
# Isolamento e permissão (críticos 26/27 do plano)
# ---------------------------------------------------------------------------


def _resposta_sem_permissao(request, mensagem):
    # Mesmo template que apps.empresas/apps.contabilidade já usam
    # (templates/erros/sem_permissao.html, DL-009) — critério 3 do plano
    # DL-017, reaproveitado aqui em vez de um segundo template idêntico.
    return render(request, "erros/sem_permissao.html", {"mensagem": mensagem}, status=403)


def _resposta_sem_escritorio(request):
    # Mesmo template que apps.contabilidade/apps.empresas já usam para a
    # mesma situação (sem escritório ativo, não há de quem seria o acervo
    # fiscal).
    return render(request, "empresas/sem_escritorio.html")


def _pode_receber(request):
    return papel_pode_receber_documentos(getattr(request, "papel", None))


def _pode_consultar(request):
    return papel_pode_consultar_documentos(getattr(request, "papel", None))


def _lote_do_escritorio_ativo(request, lote_id):
    # Critério 27: lote de OUTRO escritório é 404, nunca 403 — não revela
    # nem que o ID existe.
    return get_object_or_404(
        LoteDeRecepcao.objects.select_related("usuario"), pk=lote_id, escritorio=request.escritorio
    )


def _documento_do_escritorio_ativo(request, documento_id):
    return get_object_or_404(DocumentoFiscal, pk=documento_id, escritorio=request.escritorio)


def _evento_do_escritorio_ativo(request, evento_id):
    return get_object_or_404(EventoFiscal, pk=evento_id, escritorio=request.escritorio)


# ---------------------------------------------------------------------------
# Filtros da lista de documentos
# ---------------------------------------------------------------------------


def _empresa_do_filtro(request):
    """Lê e valida o parâmetro opcional 'empresa' da querystring da lista.

    Ausente devolve `(None, None)` — sem filtro de empresa. Presente e
    malformado (não é um identificador de banco válido) ou de OUTRO
    escritório vira `(None, mensagem_de_erro)` — nunca um filtro que
    silenciosamente devolvesse os documentos de outra empresa nem um 500.
    O julgador de formato é o compartilhado `apps.core.identificadores.
    para_id` (mesmo módulo que `apps.contabilidade.views_web` já usa, via
    `_identificador_de_cliente` — aqui usado diretamente, sem uma segunda
    cópia do wrapper que só troca a exceção por `None`).
    """
    bruto = request.GET.get("empresa", "").strip()
    if not bruto:
        return None, None
    try:
        empresa_id = para_id(bruto)
    except IdentificadorInvalido:
        return None, "'Empresa' inválida."
    # Isolamento (mesma regra de `_empresa_do_escritorio_ativo` da
    # contabilidade): uma empresa de OUTRO escritório nunca filtra nada —
    # cai no mesmo "não encontrada", para não revelar se o ID pertence a
    # alguém.
    empresa = Empresa.objects.filter(pk=empresa_id, escritorio=request.escritorio).first()
    if empresa is None:
        return None, "'Empresa' inválida."
    return empresa, None


def _inteiro_de_filtro(texto):
    """Mesma lição de `apps.contabilidade.views_web._inteiro_de_cliente`
    (R2-2/A1-A2 daquela auditoria): só dígito ASCII, nunca dígito Unicode
    reinterpretado em silêncio, nunca um texto absurdamente longo caindo
    direto no `int()` do interpretador sem guarda de formato antes. Cópia
    local pequena e PRÓPRIA (não importada de `apps.contabilidade.
    views_web`, módulo privado de outro app) porque aqui o valor julgado é
    ano/mês — uma QUANTIDADE pequena, não um identificador de banco (para
    isso já existe `para_id`, usado em `_empresa_do_filtro` acima)."""
    if not texto or not texto.isascii() or not texto.isdigit():
        return None
    return int(texto)


def _competencia_do_filtro(request):
    """Lê e valida os parâmetros opcionais 'ano'/'mes' da querystring.

    Nenhum dos dois presente: `(None, None)` — sem filtro de competência.
    Só um presente, ou um dos dois fora da faixa razoável: `(None,
    mensagem)`. Nunca aplica um padrão de competência atual como a
    contabilidade faz para período (DE-016 da contabilidade é sobre
    PERÍODO de apuração, decisão daquele módulo; aqui não há razão de
    negócio confirmada para presumir "mês corrente" quando o usuário não
    pediu nada — RC-... nenhuma. Ausência simplesmente não filtra."""
    bruto_ano = request.GET.get("ano", "").strip()
    bruto_mes = request.GET.get("mes", "").strip()
    if not bruto_ano and not bruto_mes:
        return None, None
    if not bruto_ano or not bruto_mes:
        return None, "Informe ano e mês juntos (ou nenhum dos dois) para filtrar por competência."
    ano = _inteiro_de_filtro(bruto_ano)
    mes = _inteiro_de_filtro(bruto_mes)
    if ano is None or mes is None or mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        return None, "Competência inválida: informe um ano (AAAA) e um mês (1 a 12) válidos."
    return (ano, mes), None


def _situacao_do_filtro(request):
    bruto = request.GET.get("situacao", "").strip()
    if not bruto:
        return None, None
    if bruto not in _SITUACOES_VALIDAS:
        return None, "'Situação' deve ser 'valida' ou 'cancelada'."
    return bruto, None


def _situacao_de_exibicao(documento):
    """`"valida"`/`"cancelada"` para EXIBIÇÃO — lê `documento.cancelada`
    quando a anotação de `apps.fiscal.services.documentos_do_escritorio`
    já existir (ajuste em andamento pelo `desenvolvedor-pleno` no momento
    em que este plano foi escrito — ver o cabeçalho do plano DL-010-F1);
    cai para `apps.fiscal.services.situacao_do_documento` (a MESMA fonte,
    só que sem a anotação, uma consulta a mais por documento) enquanto a
    anotação não existir. Nenhuma das duas reimplementa a regra de
    cancelamento — as duas chamam a fonte única de `services.py`.
    """
    cancelada = getattr(documento, "cancelada", None)
    if cancelada is not None:
        return "cancelada" if cancelada else "valida"
    return situacao_do_documento(documento)


def _querystring_sem_pagina(request):
    """Querystring atual, sem 'pagina' — para os links de paginação
    preservarem os filtros ativos sem acumular 'pagina' repetida."""
    dados = request.GET.copy()
    dados.pop("pagina", None)
    return dados.urlencode()


# ---------------------------------------------------------------------------
# Tela 1: envio (recepção) — arquétipo C (caixa de entrada e conferência)
# ---------------------------------------------------------------------------


_CONTRATO_DO_FORMULARIO_DE_ENVIO = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    aceita_arquivo=True,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no envio de documentos fiscais",
)

_MENSAGEM_ARQUIVO_GRANDE_DEMAIS = (
    f"Arquivo acima do limite de {LIMITE_TAMANHO_ENVIO_BYTES} bytes (HI-22). "
    "Selecione um arquivo menor."
)


@login_required
# Achado A10 (auditoria rodada 1): `csrf_exempt` AQUI, e `csrf_protect` na
# view INTERNA (`_recepcao_verificada`, logo abaixo) — é o padrão que a
# própria documentação do Django recomenda para "Modifying upload handlers
# on the fly" (tópico "File Uploads"). O middleware de CSRF padrão lê
# `request.POST` para validar o token ANTES da view rodar — e isso já
# dispara o parser multipart com os handlers PADRÃO, antes que esta view
# tivesse a chance de inserir `LimiteDeTamanhoUploadHandler` na frente da
# lista. Isento aqui (nada é processado sem proteção: o corpo só é
# consumido dentro da função interna) e força a checagem de CSRF a
# acontecer DEPOIS do handler já estar na lista, chamando `_recepcao_
# verificada` explicitamente.
@csrf_exempt
@require_http_methods(["GET", "POST"])
def recepcao(request):
    if request.method == "POST":
        # Acha A10: o handler PRÓPRIO entra na FRENTE da lista — é o
        # PRIMEIRO a ver cada pedaço do corpo, antes dos handlers padrão do
        # Django (memória/arquivo temporário) gravarem qualquer coisa. Só
        # nesta view: nenhuma outra rota deste sistema aceita upload de
        # arquivo grande (RC-71/critério 25).
        handler = LimiteDeTamanhoUploadHandler(request, limite_bytes=LIMITE_TAMANHO_ENVIO_BYTES)
        request.upload_handlers.insert(0, handler)
    else:
        handler = None
    return _recepcao_verificada(request, handler)


@csrf_protect
def _recepcao_verificada(request, handler):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_receber(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite enviar documentos fiscais para recepção."
        )

    if request.method == "POST":
        # Achado A10: acessar `request.FILES` AQUI é o que de fato DISPARA
        # o parser multipart — Django é preguiçoso, só analisa o corpo da
        # requisição no primeiro acesso a `.POST`/`.FILES`. Só DEPOIS
        # deste acesso o `handler` sabe se abortou (`StopUpload` é
        # capturado DENTRO do parser, silenciosamente — não propaga como
        # exceção até aqui). Por isso a checagem de `handler.excedeu`
        # precisa vir DEPOIS, nunca antes, deste acesso.
        arquivo = request.FILES.get("arquivo")
        if handler is not None and handler.excedeu:
            # O upload foi abortado PELO HANDLER antes de terminar de ser
            # gravado em disco/memória — `request.FILES` não tem o
            # arquivo completo (pode nem ter a chave). Mensagem de
            # formulário legível, nunca 500, nunca um "selecione um
            # arquivo" genérico que esconderia o motivo real.
            messages.error(request, _MENSAGEM_ARQUIVO_GRANDE_DEMAIS)
            return _tela_de_recepcao(request, status=400)

        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_ENVIO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return _tela_de_recepcao(request, status=400)

        if arquivo is None:
            messages.error(request, "Selecione um arquivo (XML ou ZIP) para enviar.")
            return _tela_de_recepcao(request, status=400)

        try:
            lote = receber_envio(
                escritorio=request.escritorio,
                usuario=request.user,
                arquivo=arquivo,
                nome_arquivo=arquivo.name,
            )
        except EnvioInvalido as exc:
            # Critério do contrato de `services.receber_envio`: o ENVIO
            # INTEIRO é inválido (vazio, grande demais, ZIP corrompido/
            # aninhado/cifrado) — nada foi gravado. Mensagem do próprio
            # serviço, em pt-BR, re-renderizada no formulário (nunca 500).
            messages.error(request, str(exc))
            return _tela_de_recepcao(request, status=400)

        # PRG (Post/Redirect/Get): a confirmação de sucesso e as contagens
        # aparecem na tela seguinte (relatório do envio), nunca reenviando
        # o arquivo se a pessoa atualizar a página.
        messages.success(
            request,
            f"Envio processado: {lote.total_recebidos} recebido(s), "
            f"{lote.total_duplicados} duplicado(s), {lote.total_recusados} recusado(s).",
        )
        return redirect("fiscal_web:relatorio_envio", lote_id=lote.id)

    return _tela_de_recepcao(request)


def _tela_de_recepcao(request, *, status=200):
    lotes = LoteDeRecepcao.objects.filter(escritorio=request.escritorio).select_related("usuario")
    pagina = Paginator(lotes, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto = {
        "pagina": pagina,
        "querystring_sem_pagina": _querystring_sem_pagina(request),
    }
    return render(request, "fiscal/recepcao.html", contexto, status=status)


# ---------------------------------------------------------------------------
# Tela 2: relatório de um envio — arquétipo C
# ---------------------------------------------------------------------------


@login_required
@require_safe
def relatorio_envio(request, lote_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_receber(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ver relatórios de recepção fiscal."
        )
    lote = _lote_do_escritorio_ativo(request, lote_id)

    resultados = lote.resultados.select_related("documento", "evento").order_by("id")
    linhas = [
        {
            "resultado": resultado,
            "classe_css": CLASSE_CSS_POR_RESULTADO.get(resultado.resultado, ""),
        }
        for resultado in resultados
    ]
    contexto = {"lote": lote, "linhas": linhas}
    return render(request, "fiscal/relatorio_envio.html", contexto)


# ---------------------------------------------------------------------------
# Tela 3: lista de documentos — arquétipo A (tabela de consulta)
# ---------------------------------------------------------------------------


@login_required
@require_safe
def documentos_lista(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar documentos fiscais."
        )

    empresa, erro_empresa = _empresa_do_filtro(request)
    competencia, erro_competencia = _competencia_do_filtro(request)
    situacao, erro_situacao = _situacao_do_filtro(request)
    erro = erro_empresa or erro_competencia or erro_situacao

    # O formulário é sempre RE-EXIBIDO com o que a pessoa digitou — inclusive
    # quando algum filtro é inválido (arquétipo B/direção de arte: "o
    # formulário não some quando dá erro"). Por isso os três valores "brutos"
    # (string da querystring, não o valor JULGADO) entram no contexto nos
    # DOIS caminhos, erro ou sucesso — a comparação de 'selected'/'value' no
    # template é sempre contra o texto que a pessoa digitou, nunca contra o
    # objeto já resolvido (que pode nem existir, no caminho de erro).
    contexto_comum = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa_filtro_bruto": request.GET.get("empresa", ""),
        "ano_filtro": request.GET.get("ano", ""),
        "mes_filtro": request.GET.get("mes", ""),
        "situacao_filtro": request.GET.get("situacao", ""),
    }

    if erro:
        messages.error(request, erro)
        contexto = {**contexto_comum, "pagina": None, "algum_filtro_ativo": True}
        return render(request, "fiscal/documentos_lista.html", contexto, status=400)

    documentos = documentos_do_escritorio(
        request.escritorio, empresa=empresa, competencia=competencia, situacao=situacao
    )
    pagina = Paginator(documentos, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    linhas = [
        {
            "documento": documento,
            "situacao": _situacao_de_exibicao(documento),
            # Convenção do projeto (varredura de interface, apps/core/tests/
            # test_dl024_varredura_de_interface.py): todo valor monetário
            # chega ao template já formatado, com o sufixo '_ptbr' —
            # `Decimal` até aqui, texto só a partir daqui (AGENTS.md §10).
            "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        }
        for documento in pagina.object_list
    ]
    contexto = {
        **contexto_comum,
        "pagina": pagina,
        "linhas": linhas,
        "querystring_sem_pagina": _querystring_sem_pagina(request),
        "empresa_selecionada": empresa,
        "algum_filtro_ativo": bool(empresa or competencia or situacao),
    }
    return render(request, "fiscal/documentos_lista.html", contexto)


# ---------------------------------------------------------------------------
# Tela 4: detalhe do documento
# ---------------------------------------------------------------------------


@login_required
@require_safe
def documento_detalhe(request, documento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar documentos fiscais."
        )
    documento = _documento_do_escritorio_ativo(request, documento_id)

    vinculos = documento.vinculos.select_related("empresa").order_by("empresa__razao_social")

    # Ver o comentário de módulo, no topo do arquivo, sobre esta conversão:
    # é a MESMA fatia que apps.fiscal.services.situacao_do_documento já
    # documenta como pública (TSIdNFSe = "NFS" + 50 dígitos, TSChaveNFSe são
    # os mesmos 50 dígitos sem prefixo) — não uma regra nova.
    chave_referenciada = documento.identificador[3:]
    eventos = EventoFiscal.objects.filter(
        escritorio=documento.escritorio_id, chave_nfse=chave_referenciada
    ).order_by("-data_evento")

    contexto = {
        "documento": documento,
        "situacao": _situacao_de_exibicao(documento),
        "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        "v_liq_ptbr": _valor_ptbr(documento.v_liq),
        "vinculos": vinculos,
        "eventos": eventos,
        "codigos_que_cancelam": CODIGOS_QUE_CANCELAM,
        "descricao_retencao": DESCRICAO_TP_RET_ISSQN.get(documento.tp_ret_issqn),
    }
    return render(request, "fiscal/documento_detalhe.html", contexto)


# ---------------------------------------------------------------------------
# Tela 5: download do XML original (documento e evento) — critério 29
# ---------------------------------------------------------------------------


def _resposta_xml(nome_arquivo, conteudo_binario):
    """Devolve EXATAMENTE os bytes guardados, como anexo, tipo XML — nunca
    renderizado como HTML (critério 29 do plano).

    `Content-Type: application/xml`: o navegador nunca tenta interpretar o
    conteúdo como HTML.
    `Content-Disposition: attachment`: força download em vez de exibição
    inline — mesmo que algum navegador tentasse renderizar XML como árvore,
    o `attachment` evita que ISSO aconteça na mesma aba autenticada da
    tela.
    `X-Content-Type-Options: nosniff`: impede o navegador de "adivinhar" um
    tipo diferente do declarado a partir do conteúdo (o vetor clássico de
    um XML que começa parecendo HTML).
    `bytes(...)`: `BinaryField` pode chegar como `memoryview` dependendo do
    driver do banco — `HttpResponse` precisa de `bytes`/`str`, e o SHA-256
    calculado em cima do que efetivamente sai daqui é o que prova que os
    bytes não mudaram (ver o teste do critério 29).
    """
    resposta = HttpResponse(bytes(conteudo_binario), content_type="application/xml")
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    resposta["X-Content-Type-Options"] = "nosniff"
    return resposta


@login_required
@require_safe
def documento_xml(request, documento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar documentos fiscais."
        )
    documento = _documento_do_escritorio_ativo(request, documento_id)
    return _resposta_xml(f"{documento.identificador}.xml", documento.xml_original)


@login_required
@require_safe
def evento_xml(request, evento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar documentos fiscais."
        )
    evento = _evento_do_escritorio_ativo(request, evento_id)
    return _resposta_xml(f"{evento.identificador}.xml", evento.xml_original)
