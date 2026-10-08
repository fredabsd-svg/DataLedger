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
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt, csrf_protect
from django.views.decorators.http import require_http_methods, require_safe

from apps.auditoria.models import RegistroAuditoria
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.empresas.models import Empresa
from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    EstadoConfirmacaoMes,
    EstadoEscrituracao,
    EstadoReceitaInformada,
    EventoFiscal,
    LoteDeRecepcao,
    MercadoReceita,
    NaturezaOperacao,
    OpcaoRegimeCaixaSimples,
    OrigemReceitaInformada,
    PapelDocumento,
    ReceitaInformada,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.permissoes import (
    papel_pode_consultar_documentos,
    papel_pode_escriturar_fiscal,
    papel_pode_receber_documentos,
)
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
                request=request,
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
    documentos_da_pagina = list(pagina.object_list)
    pode_escriturar = _pode_escriturar(request)
    links_de_escrituracao = (
        _links_de_escrituracao(request.escritorio, documentos_da_pagina) if pode_escriturar else {}
    )
    linhas = []
    for documento in documentos_da_pagina:
        situacao = _situacao_de_exibicao(documento)
        linhas.append(
            {
                "documento": documento,
                "situacao": situacao,
                # Convenção do projeto (varredura de interface, apps/core/tests/
                # test_dl024_varredura_de_interface.py): todo valor monetário
                # chega ao template já formatado, com o sufixo '_ptbr' —
                # `Decimal` até aqui, texto só a partir daqui (AGENTS.md §10).
                "v_serv_ptbr": _valor_ptbr(documento.v_serv),
                # DL-072 (frente B): nota cancelada não é escriturada (plano,
                # critério 5); quem só consulta não recebe link nenhum.
                "links_para_escriturar": (
                    [] if situacao == "cancelada" else links_de_escrituracao.get(documento.pk, [])
                ),
            }
        )
    contexto = {
        **contexto_comum,
        "pagina": pagina,
        "linhas": linhas,
        "querystring_sem_pagina": _querystring_sem_pagina(request),
        "empresa_selecionada": empresa,
        "algum_filtro_ativo": bool(empresa or competencia or situacao),
        "pode_escriturar": pode_escriturar,
    }
    return render(request, "fiscal/documentos_lista.html", contexto)


def _links_de_escrituracao(escritorio, documentos):
    """`{documento_id: [{"url", "razao_social"}]}` — só vínculos de PRESTADOR
    (nota tomada não se escritura nesta etapa, plano DL-072 "fica fora").
    Uma consulta para a página inteira, nunca uma por documento."""
    mapa = {documento.pk: [] for documento in documentos}
    if not mapa:
        return mapa
    vinculos = (
        VinculoDocumentoEmpresa.objects.filter(
            documento_id__in=list(mapa.keys()),
            papel=PapelDocumento.PRESTADOR,
            documento__escritorio=escritorio,
            empresa__escritorio=escritorio,
        )
        .select_related("empresa")
        .order_by("empresa__razao_social", "id")
    )
    for vinculo in vinculos:
        mapa[vinculo.documento_id].append(
            {
                "url": reverse("fiscal_web:escriturar_nota", args=[vinculo.empresa_id, vinculo.pk]),
                "razao_social": vinculo.empresa.razao_social,
            }
        )
    return mapa


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


# ---------------------------------------------------------------------------
# DL-072 (frente B): telas da escrituração das NFS-e prestadas.
#
# Toda regra de escrituração (quem é prestador, o que se efetiva, o que é
# estorno, a conferência) vem de `apps.fiscal.escrituracao`. Aqui só há
# isolamento (escritório e empresa, 404), permissão (`papel_pode_*` no
# servidor), formatação e montagem da resposta. Recusa do serviço vira
# MENSAGEM na própria tela, com status 200 e nada gravado (plano DL-072,
# critérios 2 e 4).
# ---------------------------------------------------------------------------

_ROTULO_DE_SITUACAO = {
    servico_escrituracao.SITUACAO_A_ESCRITURAR: "A escriturar",
    servico_escrituracao.SITUACAO_RASCUNHO: "Rascunho (ainda não efetivada)",
    servico_escrituracao.SITUACAO_EFETIVADA: "Efetivada",
    servico_escrituracao.SITUACAO_CANCELADA: "Cancelada",
    servico_escrituracao.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA: (
        "Cancelada depois de escriturada: estorne a escrituração"
    ),
}

_SITUACOES_QUE_ESCRITURAM = frozenset(
    {servico_escrituracao.SITUACAO_A_ESCRITURAR, servico_escrituracao.SITUACAO_RASCUNHO}
)

_SITUACOES_COM_ESCRITURACAO_PARA_VER = frozenset(
    {
        servico_escrituracao.SITUACAO_EFETIVADA,
        servico_escrituracao.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA,
    }
)

_ACOES_DO_FORMULARIO_DE_ESCRITURAR = frozenset({"rascunho", "efetivar"})

_CONTRATO_ESCRITURAR_NOTA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "natureza", "acao"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na escrituração da nota",
)

_CONTRATO_ESTORNAR_ESCRITURACAO = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração",
)


def _pode_escriturar(request):
    return papel_pode_escriturar_fiscal(getattr(request, "papel", None))


def _resposta_sem_permissao_de_escriturar(request):
    return _resposta_sem_permissao(
        request,
        "Seu papel consulta as notas, mas não escritura nem estorna. "
        "Peça a um administrador ou gestor do escritório.",
    )


def _empresa_escopada(request, empresa_id):
    # Empresa de OUTRO escritório é 404: não confirma que o ID existe.
    return get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)


def _vinculo_da_empresa(request, empresa, vinculo_id):
    # Vínculo de outra empresa (mesmo escritório) também é 404.
    return get_object_or_404(
        VinculoDocumentoEmpresa.objects.select_related("documento", "empresa"),
        pk=vinculo_id,
        empresa=empresa,
        documento__escritorio=request.escritorio,
    )


def _escrituracao_da_empresa(request, empresa, escrituracao_id):
    # Detalhe e estorno não leem o XML: o `defer` evita trazer o blob de cada nota
    # (auditoria A10). A tela de escriturar, que usa a sugestão, não passa por aqui.
    return get_object_or_404(
        EscrituracaoFiscal.objects.select_related(
            "vinculo__documento", "efetivada_por", "estornada_por"
        ).defer("vinculo__documento__xml_original"),
        pk=escrituracao_id,
        empresa=empresa,
        empresa__escritorio=request.escritorio,
    )


def _competencia_de_escrituracao(request):
    """`((ano, mes), erro)`. Sem competência pedida, mostra o mês corrente
    (fuso de Brasília). Competência pedida pela metade ou inválida é erro de
    formulário, mostrado na própria tela (mesma regra de `documentos_lista`)."""
    competencia, erro = _competencia_do_filtro(request)
    if erro or competencia is not None:
        return competencia, erro
    hoje = timezone.localdate()
    return (hoje.year, hoje.month), None


def _empresa_da_escrituracao(request):
    """`(empresa, erro)` do filtro `empresa` das telas de escrituração.

    Ausente: `(None, None)`, estado próprio da tela. Malformado (não numérico):
    erro de formulário, 400 com a mensagem na tela. Empresa inexistente ou de
    OUTRO escritório: 404, pelo mesmo caminho de `_empresa_escopada` que as telas
    de uma nota usam (plano DL-072, critério 9). A auditoria A9 pediu essa
    distinção: a lista respondia 400 para os dois casos.
    """
    bruto = request.GET.get("empresa", "").strip()
    if not bruto:
        return None, None
    try:
        empresa_id = para_id(bruto)
    except IdentificadorInvalido:
        return None, "'Empresa' inválida."
    return _empresa_escopada(request, empresa_id), None


def _filtros_de_escrituracao(request):
    """`(empresa, (ano, mes), erro)`. `empresa` é `None` quando não foi
    escolhida — estado próprio da tela, não erro. Empresa de outro escritório
    levanta 404 (ver `_empresa_da_escrituracao`)."""
    empresa, erro_empresa = _empresa_da_escrituracao(request)
    competencia, erro_competencia = _competencia_de_escrituracao(request)
    return empresa, competencia, erro_empresa or erro_competencia


def _contexto_do_filtro(request, competencia):
    """Valores do formulário de filtro. Sem competência digitada, o formulário
    mostra a competência que a tela usou (o mês corrente), para a pessoa ver
    o que está consultando."""
    ano = request.GET.get("ano", "").strip()
    mes = request.GET.get("mes", "").strip()
    if not ano and not mes and competencia is not None:
        ano, mes = str(competencia[0]), str(competencia[1])
    return {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa_filtro_bruto": request.GET.get("empresa", ""),
        "ano_filtro": ano,
        "mes_filtro": mes,
    }


def _acao_da_nota(nota, empresa, pode_escriturar):
    """Ação da linha: `{"rotulo", "url"}` ou `None`. Quem só consulta vê a
    escrituração, nunca o botão de escriturar (plano, critério 10)."""
    if nota.situacao in _SITUACOES_QUE_ESCRITURAM:
        if not pode_escriturar:
            return None
        rotulo = "Continuar escrituração" if nota.escrituracao else "Escriturar"
        return {
            "rotulo": rotulo,
            "url": reverse("fiscal_web:escriturar_nota", args=[empresa.pk, nota.vinculo.pk]),
        }
    if nota.escrituracao is not None and nota.situacao in _SITUACOES_COM_ESCRITURACAO_PARA_VER:
        return {
            "rotulo": "Ver escrituração",
            "url": reverse(
                "fiscal_web:escrituracao_detalhe", args=[empresa.pk, nota.escrituracao.pk]
            ),
        }
    return None


# Sem sugestão (XML com não incidência de ISS, HI-67): a tela não escolhe por
# o contador. O rótulo diz isso, em vez de mostrar uma natureza que não foi
# dita pelo XML.
ROTULO_SEM_SUGESTAO = "Sem sugestão — escolha a natureza"


def _rotulo_da_sugestao(natureza):
    if natureza is None:
        return ROTULO_SEM_SUGESTAO
    return NaturezaOperacao(natureza).label


def _natureza_de_exibicao(nota):
    """`(rotulo, origem)` da coluna "Natureza" (auditoria A6).

    Com escrituração (rascunho ou efetivada), mostra a natureza GRAVADA, e a origem
    diz se ela está efetivada ou só em rascunho. Sem escrituração, mostra a
    SUGERIDA pelo XML, com a origem dizendo que nada foi escriturado. Assim quem lê
    a lista não toma uma sugestão por uma escrituração feita.
    """
    if nota.escrituracao is not None:
        origem = (
            "Escriturada"
            if nota.escrituracao.estado == EstadoEscrituracao.EFETIVADA
            else "Rascunho, não efetivada"
        )
        return nota.escrituracao.get_natureza_display(), origem
    if nota.natureza_sugerida is None:
        return ROTULO_SEM_SUGESTAO, "Sem sugestão do XML"
    return NaturezaOperacao(nota.natureza_sugerida).label, "Sugerida pelo XML, não escriturada"


def _linha_da_nota(nota, empresa, pode_escriturar):
    documento = nota.documento
    natureza, origem_natureza = _natureza_de_exibicao(nota)
    return {
        "nota": nota,
        "situacao": _ROTULO_DE_SITUACAO.get(nota.situacao, nota.situacao),
        "natureza": natureza,
        "origem_natureza": origem_natureza,
        "retencao": DESCRICAO_TP_RET_ISSQN.get(documento.tp_ret_issqn, documento.tp_ret_issqn),
        "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        "acao": _acao_da_nota(nota, empresa, pode_escriturar),
    }


def _url_da_competencia(url_base, empresa, ano, mes):
    return f"{url_base}?{urlencode({'empresa': empresa.pk, 'ano': ano, 'mes': mes})}"


# ---------------------------------------------------------------------------
# Tela 6: notas a escriturar — arquétipo A (tabela de consulta) + filtro
# ---------------------------------------------------------------------------


@login_required
@require_safe
def notas_a_escriturar(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar notas fiscais a escriturar."
        )

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro(request, competencia),
        "pode_escriturar": pode_escriturar,
        "pagina": None,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/notas_a_escriturar.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/notas_a_escriturar.html", contexto)

    ano, mes = competencia
    notas = servico_escrituracao.notas_a_escriturar(empresa, ano, mes)
    pagina = Paginator(notas, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto.update(
        {
            "empresa_selecionada": empresa,
            "ano": ano,
            "mes": mes,
            "pagina": pagina,
            "linhas": [_linha_da_nota(n, empresa, pode_escriturar) for n in pagina.object_list],
            "total_notas": len(notas),
            # Aviso HI-57: competência (dCompet) diferente do mês de emissão.
            "notas_com_aviso": sum(1 for n in notas if n.competencia_difere_da_emissao),
            "querystring_sem_pagina": _querystring_sem_pagina(request),
        }
    )
    return render(request, "fiscal/notas_a_escriturar.html", contexto)


# ---------------------------------------------------------------------------
# Tela 7: escriturar uma nota — arquétipo B (formulário de documento)
# ---------------------------------------------------------------------------


def _nota_do_vinculo(empresa, vinculo):
    """A linha da nota, pela mesma regra da lista, SEM reprocessar o mês inteiro
    (auditoria A10). `None` para nota tomada, que não entra nesta escrituração."""
    return servico_escrituracao.nota_do_vinculo(empresa, vinculo)


def _tela_de_escriturar(request, empresa, vinculo, *, natureza=None, status=200):
    documento = vinculo.documento
    nota = _nota_do_vinculo(empresa, vinculo)
    escrituracao = nota.escrituracao if nota is not None else None
    sugerida = (
        nota.natureza_sugerida
        if nota is not None
        else servico_escrituracao.sugerir_natureza(documento)
    )
    if natureza is None:
        # Sem escolha digitada: a natureza já confirmada (rascunho ou efetivada)
        # ou, na primeira vez, a SUGERIDA — pré-selecionada, nunca gravada.
        # Sem sugestão (None): nada pré-selecionado; o contador precisa escolher.
        natureza = escrituracao.natureza if escrituracao else sugerida
    contexto = {
        "empresa": empresa,
        "vinculo": vinculo,
        "documento": documento,
        "nota": nota,
        "escrituracao": escrituracao,
        "natureza_selecionada": natureza,
        "opcoes_de_natureza": NaturezaOperacao.choices,
        "tem_sugestao": sugerida is not None,
        "natureza_sugerida_rotulo": _rotulo_da_sugestao(sugerida),
        "situacao_rotulo": (
            _ROTULO_DE_SITUACAO.get(nota.situacao, nota.situacao) if nota is not None else None
        ),
        "pode_formulario": nota is not None and nota.situacao in _SITUACOES_QUE_ESCRITURAM,
        "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        "v_liq_ptbr": _valor_ptbr(documento.v_liq),
        "retencao": DESCRICAO_TP_RET_ISSQN.get(documento.tp_ret_issqn, documento.tp_ret_issqn),
        "url_lista": (
            _url_da_competencia(
                reverse("fiscal_web:notas_a_escriturar"),
                empresa,
                documento.d_competencia.year,
                documento.d_competencia.month,
            )
        ),
    }
    return render(request, "fiscal/escriturar_nota.html", contexto, status=status)


def _escriturar_nota_post(request, empresa, vinculo):
    natureza = request.POST.get("natureza", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESCRITURAR_NOTA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar(request, empresa, vinculo, natureza=natureza, status=400)

    acao = request.POST.get("acao", "")
    if acao not in _ACOES_DO_FORMULARIO_DE_ESCRITURAR:
        messages.error(
            request, "Ação desconhecida. Escolha 'Salvar rascunho' ou 'Efetivar escrituração'."
        )
        return _tela_de_escriturar(request, empresa, vinculo, natureza=natureza, status=400)

    try:
        if acao == "rascunho":
            servico_escrituracao.salvar_rascunho(
                vinculo, natureza, usuario=request.user, request=request
            )
            messages.success(
                request, "Rascunho salvo. A nota continua a escriturar até você efetivar."
            )
            return redirect(
                "fiscal_web:escriturar_nota", empresa_id=empresa.pk, vinculo_id=vinculo.pk
            )
        escrituracao = servico_escrituracao.efetivar_escrituracao(
            vinculo, natureza, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        # Recusa do serviço (cancelada, já efetivada com outra natureza, papel
        # tomador, natureza inválida): mensagem na tela, status 200, nada gravado.
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar(request, empresa, vinculo, natureza=natureza, status=200)

    if escrituracao.criada_agora:
        messages.success(request, "Nota escriturada com a natureza confirmada.")
    else:
        # Idempotente (plano, decisão da frente A): repetir o clique não grava nada.
        messages.info(
            request, "Esta nota já estava escriturada com esta natureza. Nada foi alterado."
        )
    return redirect(
        "fiscal_web:escrituracao_detalhe",
        empresa_id=empresa.pk,
        escrituracao_id=escrituracao.pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def escriturar_nota(request, empresa_id, vinculo_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    vinculo = _vinculo_da_empresa(request, empresa, vinculo_id)
    if request.method == "POST":
        return _escriturar_nota_post(request, empresa, vinculo)
    return _tela_de_escriturar(request, empresa, vinculo)


# ---------------------------------------------------------------------------
# Tela 8: detalhe da escrituração — arquétipo A (detalhe) com trilha
# ---------------------------------------------------------------------------


@login_required
@require_safe
def escrituracao_detalhe(request, empresa_id, escrituracao_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar notas fiscais a escriturar."
        )
    empresa = _empresa_escopada(request, empresa_id)
    escrituracao = _escrituracao_da_empresa(request, empresa, escrituracao_id)
    documento = escrituracao.vinculo.documento
    efetivada = escrituracao.estado == EstadoEscrituracao.EFETIVADA
    contexto = {
        "empresa": empresa,
        "escrituracao": escrituracao,
        "documento": documento,
        "natureza_rotulo": escrituracao.get_natureza_display(),
        "estado_rotulo": escrituracao.get_estado_display(),
        "valor_servico_ptbr": _valor_ptbr(escrituracao.valor_servico),
        "valor_liquido_ptbr": _valor_ptbr(escrituracao.valor_liquido),
        "iss_retido_rotulo": (
            "Sim" if escrituracao.iss_retido else "Não" if escrituracao.iss_retido is False else "—"
        ),
        "efetivada": efetivada,
        "pode_estornar": efetivada and _pode_escriturar(request),
        # Pendência do plano (critério 5): cancelamento depois da efetivação.
        "cancelada_depois": efetivada and situacao_do_documento(documento) == "cancelada",
        "url_lista": _url_da_competencia(
            reverse("fiscal_web:notas_a_escriturar"),
            empresa,
            documento.d_competencia.year,
            documento.d_competencia.month,
        ),
    }
    contexto.update(_historico_da_escrituracao(request, empresa, escrituracao))
    return render(request, "fiscal/escrituracao_detalhe.html", contexto)


_ROTULO_DA_ACAO_DE_ESCRITURACAO = {
    "escrituracao_fiscal.rascunho_salvo": "Rascunho salvo",
    "escrituracao_fiscal.efetivada": "Efetivada",
    "escrituracao_fiscal.estornada": "Estornada",
}


def _historico_da_escrituracao(request, empresa, escrituracao):
    """Histórico do detalhe (auditoria A11, plano DL-072 item 7).

    `outras`: as outras escriturações da MESMA nota (estornadas antes, ou a que
    veio depois), cada uma com link para o próprio detalhe. `trilha`: as entradas
    de `RegistroAuditoria` desta escrituração, filtradas pelo escritório ativo. O
    `objeto_id` sozinho não basta: a filtragem por escritório impede que uma linha
    de outro escritório, com o mesmo id, apareça aqui.
    """
    outras = [
        {
            "escrituracao": outra,
            "url": reverse("fiscal_web:escrituracao_detalhe", args=[empresa.pk, outra.pk]),
        }
        for outra in EscrituracaoFiscal.objects.filter(
            vinculo_id=escrituracao.vinculo_id, empresa=empresa
        )
        .exclude(pk=escrituracao.pk)
        .order_by("id")
    ]
    registros = (
        RegistroAuditoria.objects.filter(
            escritorio=request.escritorio,
            objeto_tipo="EscrituracaoFiscal",
            objeto_id=str(escrituracao.pk),
        )
        .select_related("usuario")
        .order_by("criado_em", "id")
    )
    trilha = [
        {
            "quando": registro.criado_em,
            "acao": _ROTULO_DA_ACAO_DE_ESCRITURACAO.get(registro.acao, registro.acao),
            "usuario": registro.usuario.get_username() if registro.usuario else "—",
        }
        for registro in registros
    ]
    return {"outras_escrituracoes": outras, "trilha": trilha}


# ---------------------------------------------------------------------------
# Tela 9: estornar — arquétipo E (confirmação com motivo obrigatório)
# ---------------------------------------------------------------------------


def _tela_de_estornar(request, empresa, escrituracao, *, motivo, status=200):
    documento = escrituracao.vinculo.documento
    contexto = {
        "empresa": empresa,
        "escrituracao": escrituracao,
        "documento": documento,
        "efetivada": escrituracao.estado == EstadoEscrituracao.EFETIVADA,
        "natureza_rotulo": escrituracao.get_natureza_display(),
        "estado_rotulo": escrituracao.get_estado_display(),
        "motivo": motivo,
        "motivo_maximo": servico_escrituracao.MOTIVO_MAXIMO,
        "url_detalhe": reverse(
            "fiscal_web:escrituracao_detalhe", args=[empresa.pk, escrituracao.pk]
        ),
    }
    return render(request, "fiscal/escrituracao_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def escrituracao_estornar(request, empresa_id, escrituracao_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    escrituracao = _escrituracao_da_empresa(request, empresa, escrituracao_id)

    if request.method == "GET":
        return _tela_de_estornar(request, empresa, escrituracao, motivo="")

    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESTORNAR_ESCRITURACAO)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar(request, empresa, escrituracao, motivo=motivo, status=400)

    try:
        servico_escrituracao.estornar_escrituracao(
            escrituracao, motivo, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        # Motivo vazio, longo demais, ou escrituração que não está efetivada:
        # mensagem na tela, o motivo digitado continua lá, nada gravado.
        messages.error(request, exc.mensagem)
        return _tela_de_estornar(request, empresa, escrituracao, motivo=motivo, status=200)

    messages.success(
        request,
        "Escrituração estornada. A nota voltou para a lista de notas a escriturar.",
    )
    return redirect(
        "fiscal_web:escrituracao_detalhe",
        empresa_id=empresa.pk,
        escrituracao_id=escrituracao.pk,
    )


# ---------------------------------------------------------------------------
# Tela 10: conferência da escrituração — arquétipo C (conferência)
#
# Relatório de CONFERÊNCIA (classe 1 de docs/projeto/personalizacao-de-
# relatorio.md): não é demonstração contábil nem livro. Só leitura.
# ---------------------------------------------------------------------------


@login_required
@require_safe
def conferencia_escrituracao(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar a conferência da escrituração."
        )

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro(request, competencia),
        "pode_escriturar": pode_escriturar,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/conferencia_escrituracao.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/conferencia_escrituracao.html", contexto)

    ano, mes = competencia
    resultado = servico_escrituracao.conferencia(empresa, ano, mes)
    # Identidade da conferência, conferida aqui também (não só confiada ao
    # serviço): recebidas = escrituradas + pendentes.
    fecha = resultado.recebidas == resultado.escrituradas + resultado.pendentes
    contexto.update(
        {
            "empresa_selecionada": empresa,
            "ano": ano,
            "mes": mes,
            "recebidas": resultado.recebidas,
            "escrituradas": resultado.escrituradas,
            "pendentes": resultado.pendentes,
            # Pendentes = bloqueios + pendentes sem bloqueio (canceladas que nunca
            # foram escrituradas, sem o que escriturar).
            "pendentes_com_bloqueio": len(resultado.bloqueios),
            "pendentes_sem_bloqueio": resultado.pendentes - len(resultado.bloqueios),
            "fecha": fecha,
            "bloqueios": [_linha_da_nota(n, empresa, pode_escriturar) for n in resultado.bloqueios],
            "avisos": [_linha_da_nota(n, empresa, pode_escriturar) for n in resultado.avisos],
            "divergencias": [
                _linha_da_nota(n, empresa, pode_escriturar) for n in resultado.divergencias
            ],
            # Valores em R$ (auditoria A8), sempre pelo `_valor_ptbr` de Decimal.
            "total_recebidas_ptbr": _valor_ptbr(resultado.total_recebidas),
            "total_escrituradas_ptbr": _valor_ptbr(resultado.total_escrituradas),
            "total_pendentes_ptbr": _valor_ptbr(resultado.total_pendentes),
            "fecha_em_valor": resultado.total_recebidas
            == resultado.total_escrituradas + resultado.total_pendentes,
            "soma_gravada_ptbr": _valor_ptbr(resultado.soma_gravada_escrituradas),
            "soma_documentos_ptbr": _valor_ptbr(resultado.soma_documentos_escrituradas),
            "diferenca_ptbr": _valor_ptbr(resultado.diferenca_escrituradas),
            "diferenca_nula": resultado.diferenca_escrituradas == 0,
        }
    )
    return render(request, "fiscal/conferencia_escrituracao.html", contexto)


# ---------------------------------------------------------------------------
# DL-074 (frente B): receita mensal do Simples Nacional — painel do mês,
# confirmação e reabertura, receita informada, RBT12 e regime de caixa.
#
# NÍVEL 1 (AGENTS.md §3.1): o RBT12 decide a faixa do DAS. A tela é PRÉ-APURAÇÃO
# para o contador conferir contra o PGDAS-D, relatório de CONFERÊNCIA (classe 1 de
# docs/projeto/personalizacao-de-relatorio.md). Nenhuma tela transmite, gera DAS,
# calcula alíquota ou é documento oficial. A regra fica em `apps.fiscal.receita` e
# `apps.fiscal.rbt12`; aqui há só autorização, isolamento, leitura da entrada e
# tradução de erro (mesmo critério da API da DL-074, apps/fiscal/api.py).
# ---------------------------------------------------------------------------

_ROTULO_DA_SITUACAO = {
    servico_receita.SITUACAO_CONFIRMADO: "Confirmado",
    servico_receita.SITUACAO_NAO_CONFIRMADO: "Não confirmado",
    servico_receita.SITUACAO_A_RETIFICAR: "A retificar",
    # Mês da janela anterior à abertura no CNPJ: zero, sem confirmação a exigir.
    "fora_da_atividade": "Antes da abertura (zero)",
}

_EXPLICACAO_DA_SITUACAO = {
    servico_receita.SITUACAO_CONFIRMADO: (
        "A receita declarada confere com o total atual. O mês entra no RBT12."
    ),
    servico_receita.SITUACAO_NAO_CONFIRMADO: (
        "O mês ainda não foi declarado completo. Sem confirmação ele não entra no RBT12, "
        "e o RBT12 dos meses seguintes fica não apurável."
    ),
    servico_receita.SITUACAO_A_RETIFICAR: (
        "A receita mudou depois da confirmação, ou o mês foi reaberto para retificação. "
        "Ele não entra no RBT12 até ser confirmado de novo."
    ),
}

_ROTULO_DO_MERCADO = {
    MercadoReceita.INTERNO: "Mercado interno",
    MercadoReceita.EXTERNO: "Mercado externo (exportação de serviço)",
}

# Regra do art. 22 da Res. CGSN 140, por extenso, para o contador ler. A chave é o
# rótulo que `apps.fiscal.rbt12` devolve. Nenhum texto aqui traz alíquota.
_REGRA_POR_EXTENSO = {
    "§ 1º": "§ 1º (regra geral): soma dos 12 meses anteriores ao período de apuração",
    "§ 2º": "§ 2º (primeiro mês de atividade): receita do próprio mês × 12",
    "§ 3º": "§ 3º (meses seguintes do ano de início): média dos meses de atividade anteriores × 12",
    "§ 4º": (
        "§ 4º (abertura no ano anterior ao da opção): § 3º até o 12º mês de atividade, "
        "§ 1º a partir do 13º"
    ),
}

_ROTULO_DO_ESTADO_DA_RECEITA = {
    EstadoReceitaInformada.RASCUNHO: "Rascunho (não entra em nenhum total)",
    EstadoReceitaInformada.CONFIRMADA: "Confirmada",
    EstadoReceitaInformada.ESTORNADA: "Estornada",
}

_MESES_DO_ANO = [
    (f"{numero:02d}", f"{numero:02d} — {nome}")
    for numero, nome in enumerate(
        (
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ),
        start=1,
    )
]

_MENSAGEM_SEM_PERMISSAO_DE_RECEITA = (
    "Seu papel consulta a receita, mas não confirma, reabre, lança nem estorna: "
    "peça a um administrador ou gestor do escritório."
)

# Contratos das superfícies de escrita (apps.core.requisicao, BL-196). Toda view de
# POST desta seção chama `recusar_dado_nao_contratado` com um destes.
_CONTRATO_SEM_CAMPOS = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na ação sobre a receita",
)
_CONTRATO_MOTIVO_DO_MES = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura do mês",
)
_CONTRATO_RECEITA_INFORMADA = ContratoDeRequisicao(
    campos={
        "csrfmiddlewaretoken",
        "ano",
        "mes",
        "mercado",
        "valor",
        "origem",
        "motivo",
        "documento_suporte",
        "acao",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento da receita informada",
)
_CONTRATO_MOTIVO_DA_RECEITA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da receita informada",
)
_CONTRATO_REGIME_CAIXA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na opção pelo regime de caixa",
)


def _mes_por_extenso(ano, mes):
    return f"{mes:02d}/{ano}"


def _url_do_mes(empresa, ano, mes):
    return _url_da_competencia(reverse("fiscal_web:receita_do_mes"), empresa, ano, mes)


def _valor_do_formulario(bruto: str) -> str:
    """Valor digitado pelo contador, em pt-BR ('1.234,56') ou com ponto ('1234.56').

    Com vírgula, o ponto é separador de milhar e a vírgula é o decimal. Sem vírgula,
    o texto segue como está. Não vira número aqui: o serviço recusa o que não for
    decimal positivo de até duas casas, e nunca aceita float.
    """
    texto = bruto.strip()
    if "," in texto:
        return texto.replace(".", "").replace(",", ".")
    return texto


def _so_digitos_com_ponto_decimal(texto: str) -> bool:
    """Só dígitos ASCII, com no máximo um ponto decimal. Recusa sinal, letras e notação
    científica. Não valida a quantidade de casas: isso é do serviço (até duas)."""
    semponto = texto.replace(".", "", 1)
    return bool(semponto) and semponto.isascii() and semponto.isdigit()


def _celula_de_valor(valor, texto_se_nulo):
    """Célula de RBT12: número em R$ (tabulado) ou texto explicando a ausência."""
    if valor is None:
        return {"texto": texto_se_nulo, "monetario": False}
    return {"texto": _valor_ptbr(valor), "monetario": True}


def _linhas_do_mercado_no_rbt12(resultado, mercado):
    """Linhas de UM mercado do RBT12. O valor é exato no cálculo; aqui é só exibição."""
    r = resultado.de(mercado)
    return [
        {"rotulo": "Soma da janela", "celula": _celula_de_valor(r.soma, "—")},
        {
            "rotulo": "Meses no divisor",
            "celula": {
                "texto": str(r.divisor) if r.divisor is not None else "—",
                "monetario": False,
            },
        },
        {
            "rotulo": "RBT12 apurado",
            "celula": _celula_de_valor(
                r.apurado, "Não apurável: há meses da janela sem confirmação (lista acima)"
            ),
        },
        {
            "rotulo": "Acumulado no ano (até o período)",
            "celula": _celula_de_valor(
                r.acumulado_no_ano, "Não calculado: há meses do ano sem confirmação"
            ),
        },
        {"rotulo": "Teto do limite", "celula": _celula_de_valor(r.teto_limite, "Não cadastrado")},
        {
            "rotulo": "Teto do sublimite",
            "celula": _celula_de_valor(r.teto_sublimite, "Não cadastrado"),
        },
    ]


def _linha_da_janela(mes_da_janela):
    m = mes_da_janela
    return {
        "rotulo": f"{m.mes:02d}/{m.ano}",
        "situacao": _ROTULO_DA_SITUACAO.get(m.situacao, m.situacao),
        "pendente": m.na_atividade and m.situacao != servico_receita.SITUACAO_CONFIRMADO,
        "interno": _valor_ptbr(m.interno),
        "externo": _valor_ptbr(m.externo),
    }


def _pendentes_em_texto(pendentes):
    return [
        f"{mes:02d}/{ano} ({_ROTULO_DA_SITUACAO.get(situacao, situacao)})"
        for ano, mes, situacao in pendentes
    ]


def _bloco_do_rbt12(resultado):
    """Tudo que a tela mostra do RBT12: regra, janela, pendentes, valores e avisos.

    Os avisos vêm de `apps.fiscal.rbt12` já com o dispositivo que os motiva: a tela
    não reescreve nem interpreta o limite.
    """
    apurados = [resultado.de(m).apurado for m in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO)]
    # Sem `quantize` no cálculo, o RBT12 pode ter dízima. A exibição usa duas casas;
    # a tela avisa quando isso esconde casas, em vez de fingir que o valor é exato.
    valores_exatos = all(
        valor == valor.quantize(Decimal("0.01")) for valor in apurados if valor is not None
    )
    return {
        "regra": _REGRA_POR_EXTENSO.get(resultado.regra, resultado.regra),
        "apuravel": resultado.apuravel,
        "data_abertura_ptbr": resultado.data_abertura.strftime("%d/%m/%Y"),
        "ano_opcao": resultado.ano_opcao,
        "modo_limite": resultado.modo_limite,
        "janela": [_linha_da_janela(m) for m in resultado.janela],
        "pendentes": _pendentes_em_texto(resultado.pendentes_da_janela),
        "pendentes_do_ano": _pendentes_em_texto(resultado.pendentes_do_ano),
        "por_mercado": [
            {"rotulo": _ROTULO_DO_MERCADO[m], "linhas": _linhas_do_mercado_no_rbt12(resultado, m)}
            for m in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO)
        ],
        "avisos": [
            {
                "mensagem": aviso.mensagem,
                "dispositivo": aviso.dispositivo,
                "mercado": (
                    _ROTULO_DO_MERCADO[aviso.mercado]
                    if aviso.mercado is not None
                    else "Empresa, no ano"
                ),
            }
            for aviso in resultado.avisos
        ],
        "valores_exatos": valores_exatos,
    }


def _linha_da_receita_informada(receita, empresa, pode_escriturar):
    return {
        "id": receita.pk,
        "mercado": receita.get_mercado_display(),
        "valor_ptbr": _valor_ptbr(receita.valor),
        "origem": receita.get_origem_display(),
        "suporte": receita.documento_suporte,
        "estado": _ROTULO_DO_ESTADO_DA_RECEITA.get(receita.estado, receita.estado),
        "motivo_estorno": receita.motivo_estorno,
        "pode_confirmar": pode_escriturar and receita.estado == EstadoReceitaInformada.RASCUNHO,
        "pode_estornar": pode_escriturar and receita.estado == EstadoReceitaInformada.CONFIRMADA,
        "url_confirmar": reverse(
            "fiscal_web:receita_informada_confirmar", args=[empresa.pk, receita.pk]
        ),
        "url_estornar": reverse(
            "fiscal_web:receita_informada_estornar", args=[empresa.pk, receita.pk]
        ),
    }


def _contexto_do_mes(empresa, ano, mes, pode_escriturar):
    """Tudo que o painel do mês mostra. Regra só nos serviços; aqui, apresentação."""
    dados = servico_receita.receita_do_mes(empresa, ano, mes)
    confirmacao = dados.confirmacao
    # Quem pode mudar a confirmação: só quem escritura, e só no estado que o serviço
    # aceita (sem linha ou reaberta confirma; confirmada reabre).
    pode_confirmar = pode_escriturar and (
        confirmacao is None or confirmacao.estado == EstadoConfirmacaoMes.REABERTA
    )
    pode_reabrir = (
        pode_escriturar
        and confirmacao is not None
        and confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
    )
    # O RBT12 é lido só quando há como apurar. Recusa nomeada (sem data de abertura,
    # sem período do Simples, 2027 em diante) vira mensagem, e a tela segue.
    try:
        resultado = apuracao.rbt12(empresa, ano, mes)
        recusa_do_rbt12 = None
        rbt12 = _bloco_do_rbt12(resultado)
    except apuracao.ApuracaoRecusada as exc:
        recusa_do_rbt12 = exc.mensagem
        rbt12 = None

    return {
        "empresa_selecionada": empresa,
        "ano": ano,
        "mes": mes,
        "mes_rotulo": _mes_por_extenso(ano, mes),
        "pode_escriturar": pode_escriturar,
        "mensagem_sem_permissao": _MENSAGEM_SEM_PERMISSAO_DE_RECEITA,
        "linhas_mercado": [
            {
                "rotulo": _ROTULO_DO_MERCADO[m],
                "documento": _valor_ptbr(dados.composicao.de(m).documento),
                "informado": _valor_ptbr(dados.composicao.de(m).informado),
                "total": _valor_ptbr(dados.composicao.de(m).total),
            }
            for m in (MercadoReceita.INTERNO, MercadoReceita.EXTERNO)
        ],
        "situacao": dados.situacao,
        "situacao_rotulo": _ROTULO_DA_SITUACAO[dados.situacao],
        "explicacao_situacao": _EXPLICACAO_DA_SITUACAO[dados.situacao],
        "confirmada_em": confirmacao.confirmada_em if confirmacao is not None else None,
        "motivo_reabertura": confirmacao.motivo_reabertura if confirmacao is not None else "",
        "pode_confirmar": pode_confirmar,
        "pode_reabrir": pode_reabrir,
        "receitas": [
            _linha_da_receita_informada(r, empresa, pode_escriturar)
            for r in dados.receitas_informadas
        ],
        "url_nova_receita": (
            reverse("fiscal_web:receita_informada_nova", args=[empresa.pk])
            + "?"
            + urlencode({"ano": ano, "mes": f"{mes:02d}"})
        ),
        "url_confirmar": reverse("fiscal_web:receita_mes_confirmar", args=[empresa.pk, ano, mes]),
        "url_reabrir": reverse("fiscal_web:receita_mes_reabrir", args=[empresa.pk, ano, mes]),
        "url_regime_caixa": reverse("fiscal_web:regime_caixa", args=[empresa.pk]),
        "recusa_do_rbt12": recusa_do_rbt12,
        "rbt12": rbt12,
    }


@login_required
@require_safe
def receita_do_mes(request):
    """Painel do mês por empresa (arquétipo D). Consulta: `papel_pode_consultar_documentos`."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar a receita do Simples Nacional."
        )

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro(request, competencia),
        "pode_escriturar": pode_escriturar,
        "empresa_selecionada": None,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/receita_do_mes.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/receita_do_mes.html", contexto)

    ano, mes = competencia
    contexto.update(_contexto_do_mes(empresa, ano, mes, pode_escriturar))
    return render(request, "fiscal/receita_do_mes.html", contexto)


@login_required
@require_http_methods(["POST"])
def receita_mes_confirmar(request, empresa_id, ano, mes):
    """POST — "receita de MM/AAAA completa". Recusa do serviço vira mensagem, nada gravado."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DE_RECEITA)
    empresa = _empresa_escopada(request, empresa_id)
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_SEM_CAMPOS)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect(_url_do_mes(empresa, ano, mes))
    try:
        servico_receita.confirmar_mes(empresa, ano, mes, usuario=request.user, request=request)
    except (servico_receita.EntradaInvalidaReceita, servico_receita.ReceitaErro) as exc:
        messages.error(request, exc.mensagem)
    else:
        messages.success(
            request,
            f"Receita de {_mes_por_extenso(ano, mes)} confirmada. O mês passa a entrar no RBT12.",
        )
    return redirect(_url_do_mes(empresa, ano, mes))


def _tela_de_reabrir_mes(request, empresa, ano, mes, *, motivo, status=200):
    confirmacao = servico_receita.confirmacao_do_mes(empresa, ano, mes)
    contexto = {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "mes_rotulo": _mes_por_extenso(ano, mes),
        "confirmada": (
            confirmacao is not None and confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA
        ),
        "motivo": motivo,
        "motivo_maximo": servico_receita.MOTIVO_MAXIMO,
        "url_mes": _url_do_mes(empresa, ano, mes),
    }
    return render(request, "fiscal/receita_mes_reabrir.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def receita_mes_reabrir(request, empresa_id, ano, mes):
    """GET: tela de confirmação com o motivo. POST: reabre o mês (motivo obrigatório)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DE_RECEITA)
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_de_reabrir_mes(request, empresa, ano, mes, motivo="")

    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_MOTIVO_DO_MES)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_reabrir_mes(request, empresa, ano, mes, motivo=motivo, status=400)
    try:
        servico_receita.reabrir_mes(
            empresa, ano, mes, motivo, usuario=request.user, request=request
        )
    except (servico_receita.EntradaInvalidaReceita, servico_receita.ReceitaErro) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_reabrir_mes(request, empresa, ano, mes, motivo=motivo, status=200)
    messages.success(
        request,
        f"Receita de {_mes_por_extenso(ano, mes)} reaberta. "
        "O mês sai do RBT12 até ser confirmado de novo.",
    )
    return redirect(_url_do_mes(empresa, ano, mes))


def _valores_do_lancamento(request):
    """Valores iniciais do formulário de lançamento: a competência pedida ou a corrente."""
    hoje = timezone.localdate()
    ano = _inteiro_de_filtro(request.GET.get("ano", "").strip())
    mes = _inteiro_de_filtro(request.GET.get("mes", "").strip())
    return {
        "ano": str(ano) if ano is not None else str(hoje.year),
        "mes": f"{mes:02d}" if mes is not None and 1 <= mes <= 12 else f"{hoje.month:02d}",
        "mercado": MercadoReceita.INTERNO,
        "valor": "",
        "origem": "",
        "motivo": "",
        "documento_suporte": "",
    }


def _tela_de_lancar_receita(request, empresa, *, valores, status=200):
    inicio_ano, inicio_mes = servico_receita.inicio_de_uso(empresa)
    contexto = {
        "empresa": empresa,
        "valores": valores,
        "opcoes_mes": _MESES_DO_ANO,
        "opcoes_mercado": MercadoReceita.choices,
        "opcoes_origem": OrigemReceitaInformada.choices,
        "inicio_de_uso_rotulo": _mes_por_extenso(inicio_ano, inicio_mes),
        "motivo_maximo": servico_receita.MOTIVO_MAXIMO,
        "suporte_maximo": servico_receita.DOCUMENTO_SUPORTE_MAXIMO,
        "url_voltar": reverse("fiscal_web:receita_do_mes")
        + "?"
        + urlencode({"empresa": empresa.pk}),
    }
    return render(request, "fiscal/receita_informada_nova.html", contexto, status=status)


def _lancar_receita_post(request, empresa):
    campos = ("ano", "mes", "mercado", "valor", "origem", "motivo", "documento_suporte", "acao")
    valores = {campo: request.POST.get(campo, "") for campo in campos}
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_RECEITA_INFORMADA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=400)
    if valores["acao"] not in ("rascunho", "confirmar"):
        messages.error(
            request, "Ação desconhecida. Escolha 'Salvar rascunho' ou 'Salvar e confirmar'."
        )
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=400)

    ano = _inteiro_de_filtro(valores["ano"].strip())
    mes = _inteiro_de_filtro(valores["mes"].strip())
    if ano is None or mes is None:
        messages.error(request, "Informe o ano e o mês da competência, com números.")
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=200)

    valor = _valor_do_formulario(valores["valor"])
    if not _so_digitos_com_ponto_decimal(valor):
        # Notação científica, sinal e letras não são valor digitado pelo contador. O serviço
        # aceitaria "1e3" como decimal, então a forma é conferida aqui, na entrada.
        messages.error(
            request,
            "Valor inválido: use só números, com vírgula ou ponto para os centavos "
            "(ex.: 1.234,56).",
        )
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=200)

    try:
        # Lançar e confirmar são UM ato: se a confirmação for recusada (mês já confirmado,
        # por exemplo), o lançamento também não é gravado. A mensagem diz isso.
        with transaction.atomic():
            receita = servico_receita.lancar_receita_informada(
                empresa,
                ano,
                mes,
                valores["mercado"],
                valor,
                valores["origem"],
                valores["motivo"],
                valores["documento_suporte"],
                usuario=request.user,
                request=request,
            )
            if valores["acao"] == "confirmar":
                servico_receita.confirmar_receita_informada(
                    receita, usuario=request.user, request=request
                )
    except (servico_receita.EntradaInvalidaReceita, servico_receita.ReceitaErro) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=200)

    if valores["acao"] == "confirmar":
        messages.success(request, "Receita informada confirmada. Ela entra na receita do mês.")
    else:
        messages.success(
            request, "Rascunho salvo. Ele não entra em nenhum total até ser confirmado."
        )
    return redirect(_url_do_mes(empresa, ano, mes))


@login_required
@require_http_methods(["GET", "POST"])
def receita_informada_nova(request, empresa_id):
    """GET: formulário de lançamento. POST: rascunho ou rascunho já confirmado."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DE_RECEITA)
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_de_lancar_receita(request, empresa, valores=_valores_do_lancamento(request))
    return _lancar_receita_post(request, empresa)


def _receita_da_empresa(empresa, receita_id):
    # Receita de outra empresa, mesmo do mesmo escritório, é 404 (isolamento).
    return get_object_or_404(ReceitaInformada, pk=receita_id, empresa=empresa)


@login_required
@require_http_methods(["POST"])
def receita_informada_confirmar(request, empresa_id, receita_id):
    """POST — rascunho → confirmada. Recusa do serviço vira mensagem; nada gravado."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DE_RECEITA)
    empresa = _empresa_escopada(request, empresa_id)
    receita = _receita_da_empresa(empresa, receita_id)
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_SEM_CAMPOS)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect(_url_do_mes(empresa, receita.ano, receita.mes))
    try:
        servico_receita.confirmar_receita_informada(receita, usuario=request.user, request=request)
    except servico_receita.ReceitaErro as exc:
        messages.error(request, exc.mensagem)
    else:
        messages.success(request, "Receita informada confirmada. Ela entra na receita do mês.")
    return redirect(_url_do_mes(empresa, receita.ano, receita.mes))


def _tela_de_estornar_receita(request, empresa, receita, *, motivo, status=200):
    contexto = {
        "empresa": empresa,
        "receita": receita,
        "mes_rotulo": _mes_por_extenso(receita.ano, receita.mes),
        "confirmada": receita.estado == EstadoReceitaInformada.CONFIRMADA,
        "estado_rotulo": _ROTULO_DO_ESTADO_DA_RECEITA.get(receita.estado, receita.estado),
        "valor_ptbr": _valor_ptbr(receita.valor),
        "origem_rotulo": receita.get_origem_display(),
        "motivo": motivo,
        "motivo_maximo": servico_receita.MOTIVO_MAXIMO,
        "url_mes": _url_do_mes(empresa, receita.ano, receita.mes),
    }
    return render(request, "fiscal/receita_informada_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def receita_informada_estornar(request, empresa_id, receita_id):
    """GET: tela de confirmação com o motivo. POST: estorna (motivo obrigatório)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DE_RECEITA)
    empresa = _empresa_escopada(request, empresa_id)
    receita = _receita_da_empresa(empresa, receita_id)
    if request.method == "GET":
        return _tela_de_estornar_receita(request, empresa, receita, motivo="")

    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_MOTIVO_DA_RECEITA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_receita(request, empresa, receita, motivo=motivo, status=400)
    try:
        servico_receita.estornar_receita_informada(
            receita, motivo, usuario=request.user, request=request
        )
    except (servico_receita.EntradaInvalidaReceita, servico_receita.ReceitaErro) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_receita(request, empresa, receita, motivo=motivo, status=200)
    messages.success(
        request,
        "Receita informada estornada. Se o mês estava confirmado, ele voltou a 'a retificar'.",
    )
    return redirect(_url_do_mes(empresa, receita.ano, receita.mes))


def _tela_de_regime_caixa(request, empresa, *, ano_digitado="", status=200):
    contexto = {
        "empresa": empresa,
        "ano_digitado": ano_digitado,
        "ano_maximo": servico_receita.ANO_ULTIMO_CAIXA,
        "opcoes": OpcaoRegimeCaixaSimples.objects.filter(empresa=empresa).order_by(
            "ano_calendario"
        ),
        "pode_registrar": _pode_escriturar(request),
        "url_voltar": reverse("fiscal_web:receita_do_mes")
        + "?"
        + urlencode({"empresa": empresa.pk}),
    }
    return render(request, "fiscal/regime_caixa.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def regime_caixa(request, empresa_id):
    """Opção pelo regime de caixa no Simples, por ano (só até 2026, HI-66).

    GET: consulta (`papel_pode_consultar_documentos`). POST: registro, que exige
    `papel_pode_escriturar_fiscal` e é recusado no servidor para quem só consulta.
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if request.method == "POST" and not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite registrar a opção pelo regime de caixa."
        )
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar o regime de caixa."
        )
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_de_regime_caixa(request, empresa)

    bruto = request.POST.get("ano", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_REGIME_CAIXA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_regime_caixa(request, empresa, ano_digitado=bruto, status=400)
    ano = _inteiro_de_filtro(bruto.strip())
    if ano is None:
        messages.error(request, "Informe o ano-calendário com quatro dígitos (AAAA).")
        return _tela_de_regime_caixa(request, empresa, ano_digitado=bruto, status=200)
    try:
        servico_receita.registrar_opcao_regime_caixa(
            empresa, ano, usuario=request.user, request=request
        )
    except (servico_receita.EntradaInvalidaReceita, servico_receita.ReceitaErro) as exc:
        # Recusa de 2027 em diante e ano duplicado: mensagem com a fonte, nada gravado.
        messages.error(request, exc.mensagem)
        return _tela_de_regime_caixa(request, empresa, ano_digitado=bruto, status=200)
    messages.success(
        request,
        f"Opção pelo regime de caixa registrada para {ano}. Ela é irretratável no ano.",
    )
    return redirect("fiscal_web:regime_caixa", empresa_id=empresa.pk)
