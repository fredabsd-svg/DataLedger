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

import re
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, localcontext
from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Sum
from django.http import Http404, HttpResponse
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
from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import folha_fator_r as servico_folha
from apps.fiscal import iss_municipal as servico_iss
from apps.fiscal import pre_das as servico_pre_das
from apps.fiscal import presumido as servico_presumido
from apps.fiscal import presumido_calculo as calc_presumido
from apps.fiscal import presumido_tabelas as tab_presumido
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as servico_receita
from apps.fiscal import retencoes as servico_retencoes
from apps.fiscal import simples_tabelas as tabelas
from apps.fiscal import tomadas as servico_tomadas
from apps.fiscal.api_escrituracao_nfe import MAIOR_ID
from apps.fiscal.api_nfe import DESCRICAO_EVENTO_NFE, direcao_para_o_cliente
from apps.fiscal.cfop import cfop as consultar_cfop
from apps.fiscal.formatacao_ptbr import milhar_ptbr as _milhar_ptbr
from apps.fiscal.formatacao_ptbr import valor_ptbr as _valor_ptbr
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    AtividadeEmpresa,
    AtividadePresuncaoEmpresa,
    DocumentoFiscal,
    DocumentoNFe,
    EnquadramentoAtividade,
    EscrituracaoFiscal,
    EscrituracaoNFe,
    EscrituracaoTomada,
    EstadoConfirmacaoMes,
    EstadoEscrituracao,
    EstadoFolhaFatorR,
    EstadoReceitaInformada,
    EventoFiscal,
    EventoNFe,
    FolhaFatorR,
    ItemNFe,
    LeituraItensNFe,
    LoteDeRecepcao,
    MedidaJudicialLC224,
    MercadoReceita,
    ModeloNFe,
    NaturezaItemNFe,
    NaturezaOperacao,
    NaturezaOperacaoNFe,
    NaturezaTomada,
    OpcaoRegimeCaixaSimples,
    OrigemReceitaInformada,
    PapelDocumento,
    PapelNFe,
    ReceitaInformada,
    ReceitaTrimestralPresumido,
    RegimeIss,
    RegimeIssEmpresa,
    RegraIssMunicipio,
    SituacaoIssReceitaInformada,
    VinculoDocumentoEmpresa,
    VinculoNFeEmpresa,
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
    aviso_do_evento_nfe,
    documentos_do_escritorio,
    efeito_do_evento_nfe,
    receber_envio,
    situacao_da_nfe,
    situacao_do_documento,
    vinculos_nfe_da_empresa,
)
from apps.fiscal.tomadas_campos import campos_tomada_do_documento
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


# Formatação pt-BR de apresentação: `_valor_ptbr` e `_milhar_ptbr` moram em
# `apps.fiscal.formatacao_ptbr` (importados no topo) desde a DL-078 (auditoria A6), para que o
# serviço de tomadas use o mesmo formatador nos avisos, sem importar a camada de tela.


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

    # DL-080: NF-e, NFC-e e eventos de NF-e também vêm no relatório (vínculos próprios).
    resultados = lote.resultados.select_related(
        "documento", "evento", "documento_nfe", "evento_nfe"
    ).order_by("id")
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
    # DL-074, HI-76: a proporcional vale nos 12 primeiros meses de atividade, mesmo
    # atravessando a virada do ano — não só no ano de início.
    "§ 3º": (
        "§ 3º (2º ao 12º mês de atividade, abertura no ano da opção): "
        "média dos meses de atividade anteriores × 12"
    ),
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
        "situacao_iss",
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


# Ponto seguido de exatamente três dígitos, sem dígito logo depois: padrão de milhar.
_PADRAO_DE_MILHAR_SEM_VIRGULA = re.compile(r"\.\d{3}(?!\d)")


# Milhar bem formado: grupos de três dígitos separados por ponto ('1.234', '12.345.678').
_PADRAO_DE_MILHAR_BEM_FORMADO = re.compile(r"\d{1,3}(?:\.\d{3})+")


class ValorInvalidoNoFormulario(ValueError):
    """Valor digitado que o formulário não aceita: a tela mostra a mensagem e não grava (A4)."""


class ValorAmbiguo(ValorInvalidoNoFormulario):
    """Valor digitado sem vírgula com ponto de milhar: a tela pede a vírgula (A4)."""


def _valor_do_formulario(bruto: str) -> str:
    """Valor digitado pelo contador, em pt-BR ('1.234,56') ou com ponto ('1234.56').

    Com vírgula, o ponto é separador de milhar e a vírgula é o decimal ('1.000,50' vira
    '1000.50'). O ponto de milhar só vale entre grupos de três dígitos: '1.23,4' é recusado
    (`ValorInvalidoNoFormulario`), e não lido como 123,40 (A4 da auditoria DL-075). Vírgula
    decimal só uma vez.

    Sem vírgula, o texto segue como está ('1500' e '1500.5'), exceto quando há ponto seguido
    de exatamente três dígitos: '10.000' pode ser dez mil ou dez centavos, e o sistema não
    adivinha. Nesse caso levanta `ValorAmbiguo` pedindo a vírgula.

    Não vira número aqui: o serviço recusa o que não for decimal positivo de até duas
    casas, e nunca aceita float.
    """
    texto = bruto.strip()
    if "," in texto:
        inteiro, _, decimal = texto.partition(",")
        if "," in decimal:
            raise ValorInvalidoNoFormulario(
                "Valor inválido: use uma só vírgula, para os centavos (ex.: 1.234,56)."
            )
        if "." in inteiro and not _PADRAO_DE_MILHAR_BEM_FORMADO.fullmatch(inteiro):
            raise ValorInvalidoNoFormulario(
                f"Valor inválido: {texto}. O ponto só separa grupos de três dígitos, como em "
                "1.234,56. Confira o valor."
            )
        return f"{inteiro.replace('.', '')}.{decimal}"
    if _PADRAO_DE_MILHAR_SEM_VIRGULA.search(texto):
        raise ValorAmbiguo(
            "Valor ambíguo: sem vírgula, o ponto é lido como separador de milhar. Se o valor é "
            f"{texto} reais, use vírgula para os centavos: {texto},00."
        )
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
        # Uma coluna por parcela, e as colunas somam o total: NFS-e + NF-e de saída + informado −
        # devolução deduzida no mês (que inclui o saldo de meses anteriores). Correção da rodada 1,
        # A7: a tela mostrava só NFS-e e informado, e o total não batia com as colunas.
        "linhas_mercado": [
            {
                "rotulo": _ROTULO_DO_MERCADO[m],
                "documento": _valor_ptbr(dados.composicao.de(m).documento),
                "nfe": _valor_ptbr(dados.composicao.de(m).mercadoria),
                "informado": _valor_ptbr(dados.composicao.de(m).informado),
                "devolucao": _valor_ptbr(dados.composicao.de(m).deduzido),
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
        # DL-075 (frente B): o pré-DAS do mesmo mês, para conferência (classe 1).
        "url_pre_das": _url_do_pre_das(empresa, ano, mes),
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
        # HI-80: sem valor padrão. O contador escolhe; "próprio município" não é presumido.
        "situacao_iss": "",
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
        "opcoes_situacao_iss": SituacaoIssReceitaInformada.choices,
        "inicio_de_uso_rotulo": _mes_por_extenso(inicio_ano, inicio_mes),
        "motivo_maximo": servico_receita.MOTIVO_MAXIMO,
        "suporte_maximo": servico_receita.DOCUMENTO_SUPORTE_MAXIMO,
        "url_voltar": reverse("fiscal_web:receita_do_mes")
        + "?"
        + urlencode({"empresa": empresa.pk}),
    }
    return render(request, "fiscal/receita_informada_nova.html", contexto, status=status)


def _lancar_receita_post(request, empresa):
    campos = (
        "ano",
        "mes",
        "mercado",
        "valor",
        "origem",
        "situacao_iss",
        "motivo",
        "documento_suporte",
        "acao",
    )
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

    try:
        valor = _valor_do_formulario(valores["valor"])
    except ValorInvalidoNoFormulario as exc:
        messages.error(request, str(exc))
        return _tela_de_lancar_receita(request, empresa, valores=valores, status=200)
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
                situacao_iss=valores["situacao_iss"],
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


# ---------------------------------------------------------------------------
# DL-075 (frente B): pré-DAS, atividades e folha para o fator r.
#
# CONFERÊNCIA (classe 1 de docs/projeto/personalizacao-de-relatorio.md): o pré-DAS calcula
# para o contador conferir contra o PGDAS-D. Nenhuma tela gera nem transmite DAS, e nenhuma
# calcula alíquota. A regra fica em `apps.fiscal.pre_das` e `apps.fiscal.folha_fator_r`;
# aqui há autorização, isolamento, leitura da entrada, formatação pt-BR e tradução de erro
# (mesmo critério da API, apps/fiscal/api.py).
#
# Uma tela de UMA empresa não lista as outras empresas do escritório (direção de arte §8.1):
# a lista de empresas só aparece quando nenhuma foi escolhida.
# ---------------------------------------------------------------------------

_AVISO_DO_PRE_DAS = (
    "Pré-apuração para conferência contra o PGDAS-D. Esta tela não gera nem transmite DAS, "
    "não substitui o aplicativo oficial e não é documento oficial."
)
_MENSAGEM_SEM_PERMISSAO_DO_SIMPLES = (
    "Seu papel consulta o Simples Nacional, mas não cadastra, altera, lança nem estorna: "
    "peça a um administrador ou gestor do escritório."
)
_PRECISAO_DE_EXIBICAO = 60
# Ponto decimal de um número dentro de um texto da memória. O dispositivo NÃO passa aqui:
# ele cita itens como "8.2.1", que não são números.
# Ponto decimal (percentuais e textos com ponto), ou dinheiro já em pt-BR ('500.000,00'), que
# a memória do pré-DAS produz com ponto de milhar. O dinheiro fica como está.
_PADRAO_PONTO_DECIMAL = re.compile(r"\d{1,3}(?:\.\d{3})+,\d{2}|(?<=\d)\.(?=\d)")
_TRIBUTOS_NA_ORDEM = (
    tabelas.IRPJ,
    tabelas.CSLL,
    tabelas.COFINS,
    tabelas.PIS,
    tabelas.CPP,
    tabelas.ISS,
    tabelas.ICMS,
    tabelas.IPI,
)
_ROTULO_DO_TRIBUTO = {
    tabelas.IRPJ: "IRPJ",
    tabelas.CSLL: "CSLL",
    tabelas.COFINS: "Cofins",
    tabelas.PIS: "PIS/Pasep",
    tabelas.CPP: "CPP",
    tabelas.ISS: "ISS",
    tabelas.ICMS: "ICMS",
    tabelas.IPI: "IPI",
}
_ROTULO_DO_SEGMENTO = {
    servico_pre_das.SEG_NORMAL: "Receita normal (ISS devido pelo prestador)",
    servico_pre_das.SEG_RETIDO: "Receita com ISS retido (o percentual do ISS é desconsiderado)",
    servico_pre_das.SEG_OUTRO_MUNICIPIO: (
        "Receita com ISS devido a outro município (sem divisão por município)"
    ),
    servico_pre_das.SEG_EXPORTACAO: "Exportação de serviço (sem PIS, Cofins e ISS)",
}
# Códigos de bloqueio que se resolvem cadastrando ou corrigindo a atividade da empresa.
_CODIGOS_DE_ATIVIDADE = frozenset(
    {
        "sem_atividade_padrao",
        "atividades_padrao_sobrepostas",
        "atividade_padrao_muda_no_mes",
        "atividade_informada_fora_da_vigencia",
    }
)
_ROTULO_DA_SITUACAO_DA_FOLHA = {
    servico_folha.SITUACAO_SEM_LANCAMENTO: "sem folha lançada",
    EstadoFolhaFatorR.RASCUNHO: "rascunho, não confirmada",
    EstadoFolhaFatorR.CONFIRMADA: "confirmada",
    EstadoFolhaFatorR.ESTORNADA: "estornada",
}
_ROTULO_DO_COMPONENTE = {
    "remuneracao_empregados_avulsos": "Remuneração base INSS: empregados e avulsos",
    "pro_labore_autonomos": "Pró-labore e autônomos",
    "decimo_terceiro": "13º salário (na competência da incidência)",
    "cpp_recolhida": "CPP recolhida (inclusive a do DAS)",
    "fgts_recolhido": "FGTS recolhido",
}
_ENQUADRAMENTOS_NA_TELA = [
    {
        "valor": valor,
        "rotulo": rotulo,
        "dispositivo": servico_pre_das.DISPOSITIVO_DO_ENQUADRAMENTO[valor],
    }
    for valor, rotulo in EnquadramentoAtividade.choices
]

# Contratos das superfícies de escrita (apps.core.requisicao, BL-196). Cada view de POST
# desta seção chama `recusar_dado_nao_contratado` com um destes.
_CONTRATO_DA_ATIVIDADE = ContratoDeRequisicao(
    campos={
        "csrfmiddlewaretoken",
        "descricao",
        "codigo_subitem",
        "enquadramento",
        "inicio",
        "fim",
        "padrao",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro da atividade",
)
_CONTRATO_ENCERRAR_ATIVIDADE = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "fim"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no encerramento da atividade",
)
_CONTRATO_DA_FOLHA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "ano", "mes", "documento_suporte", *FolhaFatorR.COMPONENTES},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento da folha",
)
_CONTRATO_SEM_CAMPOS_DA_FOLHA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na confirmação da folha",
)
_CONTRATO_MOTIVO_DA_FOLHA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da folha",
)


# ---------------------------------------------------------------------------
# Formatação de apresentação. Só exibição: nenhum cálculo passa por estas funções.
# ---------------------------------------------------------------------------


def _decimal_ptbr(valor, casas: int) -> str:
    """`Decimal` → texto pt-BR com `casas` decimais ('.' de milhar, ',' decimal).

    Arredonda SÓ para exibir (ROUND_HALF_UP). Nunca recebe `float` (AGENTS.md §10).
    """
    if valor is None:
        return "—"
    with localcontext() as contexto:
        contexto.prec = _PRECISAO_DE_EXIBICAO
        quantizado = Decimal(valor).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)
    inteiro, _, fracao = f"{quantizado:f}".partition(".")
    return f"{_milhar_ptbr(inteiro)},{fracao}" if fracao else _milhar_ptbr(inteiro)


def _dinheiro_ptbr(valor) -> str:
    return _decimal_ptbr(valor, 2)


def _percentual_ptbr(fracao) -> str:
    """Fração (0,0808) → percentual com 4 casas ('8,0800%'). A alíquota efetiva usa esta
    forma; o cálculo usa a precisão total, sem arredondar (LC 123, art. 18, § 1º-A)."""
    if fracao is None:
        return "—"
    with localcontext() as contexto:
        contexto.prec = _PRECISAO_DE_EXIBICAO
        percentual = Decimal(fracao) * 100
    return f"{_decimal_ptbr(percentual, 4)}%"


def _texto_da_memoria_em_ptbr(texto: str) -> str:
    """Números de um texto da memória, com vírgula decimal. Só o que é número.

    O dinheiro (já pt-BR, com milhar) passa sem mudança; o ponto decimal de percentuais vira
    vírgula.
    """
    return _PADRAO_PONTO_DECIMAL.sub(lambda m: m.group(0) if "," in m.group(0) else ",", texto)


def _data_do_formulario(texto: str):
    """Data digitada em dd/mm/aaaa → `date`, ou None se for inválida."""
    texto = texto.strip()
    if not texto.isascii() or len(texto) != 10 or texto[2] != "/" or texto[5] != "/":
        return None
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def _data_na_tela(data) -> str:
    return data.strftime("%d/%m/%Y") if data is not None else ""


def _vencimento_na_tela(data) -> str:
    """Data nominal do vencimento na tela (A7): a regra mora em `iss_municipal.data_nominal_br`."""
    return servico_iss.data_nominal_br(data)


# ---------------------------------------------------------------------------
# URLs e filtros das telas do Simples
# ---------------------------------------------------------------------------


def _url_do_pre_das(empresa, ano, mes):
    return _url_da_competencia(reverse("fiscal_web:pre_das"), empresa, ano, mes)


def _url_atividades(empresa):
    return reverse("fiscal_web:atividades") + "?" + urlencode({"empresa": empresa.pk})


def _url_folhas(empresa, ano):
    return (
        reverse("fiscal_web:folhas_fator_r") + "?" + urlencode({"empresa": empresa.pk, "ano": ano})
    )


def _contexto_do_filtro_de_empresa(request, empresa, competencia=None):
    """Valores do filtro das telas do Simples. A lista de empresas só existe SEM empresa
    escolhida; com uma escolhida, o filtro mostra só ela (direção de arte §8.1)."""
    ano = request.GET.get("ano", "").strip()
    mes = request.GET.get("mes", "").strip()
    if competencia is not None and not ano and not mes:
        ano, mes = str(competencia[0]), f"{competencia[1]:02d}"
    return {
        "empresa_selecionada": empresa,
        "empresas_do_escritorio": (
            None
            if empresa is not None
            else Empresa.objects.filter(escritorio=request.escritorio).order_by("razao_social")
        ),
        "ano_filtro": ano,
        "mes_filtro": mes,
        "url_trocar_empresa": reverse("empresas:lista"),
    }


# ---------------------------------------------------------------------------
# Pré-DAS do mês (tela 1)
# ---------------------------------------------------------------------------


def _acao_do_bloqueio(bloqueio, empresa, ano, mes):
    """`(rótulo, URL, texto)` para resolver o bloqueio. Sem caminho na tela, rótulo e URL
    vêm vazios e o texto diz o porquê: a tela não inventa um caminho que não existe."""
    codigo = bloqueio.codigo
    if codigo in ("mes_nao_confirmado", "rbt12_nao_apuravel"):
        return "Abrir a receita do mês", _url_do_mes(empresa, ano, mes), ""
    if codigo == "rbt12_recusado":
        if "data de abertura" in bloqueio.mensagem:
            return (
                None,
                None,
                "Não há tela para informar a data de abertura no CNPJ: ela fica no cadastro da "
                "empresa (API de empresas). Esta tela não altera cadastro.",
            )
        return "Abrir a receita do mês", _url_do_mes(empresa, ano, mes), ""
    if codigo == "regime_de_caixa":
        return (
            "Ver a opção pelo regime de caixa",
            reverse("fiscal_web:regime_caixa", args=[empresa.pk]),
            "",
        )
    if codigo in _CODIGOS_DE_ATIVIDADE:
        return "Cadastrar ou corrigir as atividades", _url_atividades(empresa), ""
    if codigo == "folha_nao_confirmada":
        return "Lançar e confirmar a folha", _url_folhas(empresa, ano), ""
    return (
        None,
        None,
        "Não há ação nesta tela: a regra vem do primeiro corte do pré-DAS (HI-68) ou da "
        "tabela de vigência.",
    )


def _bloqueio_na_tela(bloqueio, empresa, ano, mes) -> dict:
    rotulo, url, texto = _acao_do_bloqueio(bloqueio, empresa, ano, mes)
    return {
        "mensagem": bloqueio.mensagem,
        "dispositivo": bloqueio.dispositivo,
        "acao": rotulo,
        "url": url,
        "sem_acao": texto,
    }


def _diferenca_na_tela(diferenca, tributo) -> str:
    """Diferença centesimal (§ 1º-B, II). Quase sempre ~10^-60: mostra a ordem de grandeza."""
    if abs(diferenca) < Decimal("0.000000000001"):
        texto = "menor que 0,000000000001 em módulo (precisão total; a memória traz o valor)"
    else:
        texto = _decimal_ptbr(diferenca, 12)
    return f"{texto}, ao tributo {_ROTULO_DO_TRIBUTO.get(tributo, tributo)}"


def _segmento_na_tela(segmento) -> dict:
    return {
        "rotulo": _ROTULO_DO_SEGMENTO[segmento.segmento],
        "receita": _dinheiro_ptbr(segmento.receita),
        "total": _dinheiro_ptbr(segmento.total),
        "linhas": [
            {
                "tributo": _ROTULO_DO_TRIBUTO.get(linha.tributo, linha.tributo),
                "percentual": _percentual_ptbr(linha.percentual),
                "valor": _dinheiro_ptbr(linha.valor),
                "situacao": "Desconsiderado: valor zero" if linha.desconsiderado else "Incide",
            }
            for linha in segmento.linhas
        ],
    }


def _anexo_na_tela(anexo) -> dict:
    return {
        "rotulo": f"{_ROTULO_DO_MERCADO[anexo.mercado]}: Anexo {anexo.anexo}",
        "faixa": anexo.faixa,
        "rbt12": _dinheiro_ptbr(anexo.rbt12),
        "limite_superior": _dinheiro_ptbr(anexo.limite_superior),
        "aliquota_nominal": _percentual_ptbr(anexo.aliquota_nominal),
        "parcela_a_deduzir": _dinheiro_ptbr(anexo.parcela_a_deduzir),
        "aliquota_efetiva": _percentual_ptbr(anexo.aliquota_efetiva),
        "teto_iss": (
            "Sim: ISS fixado em 5% e os federais redistribuídos (§ 1º-B; nota do anexo)"
            if anexo.teto_iss_aplicado
            else "Não"
        ),
        "diferenca": _diferenca_na_tela(anexo.diferenca, anexo.tributo_da_diferenca),
        "total": _dinheiro_ptbr(anexo.total),
        "segmentos": [_segmento_na_tela(segmento) for segmento in anexo.segmentos],
    }


def _fator_r_na_tela(fator):
    if fator is None:
        return None
    return {
        "fs12": _dinheiro_ptbr(fator.fs12),
        "rbt12_conjunto": _dinheiro_ptbr(fator.rbt12_conjunto),
        "valor": _decimal_ptbr(fator.valor, 2),
        "regra_zero": fator.regra_zero,
    }


def _bloco_do_pre_das(resultado) -> dict:
    """Tudo que a tela mostra do pré-DAS apurado. Os números exatos ficam no resultado."""
    por_tributo = dict(resultado.total_por_tributo)
    tributos = [
        {
            "rotulo": _ROTULO_DO_TRIBUTO.get(tributo, tributo),
            "valor": _dinheiro_ptbr(por_tributo[tributo]),
        }
        for tributo in _TRIBUTOS_NA_ORDEM
        if tributo in por_tributo
    ]
    return {
        "total": _dinheiro_ptbr(resultado.total),
        "rbt12_por_mercado": [
            {"rotulo": _ROTULO_DO_MERCADO[mercado], "valor": _dinheiro_ptbr(valor)}
            for mercado, valor in resultado.rbt12.items()
        ],
        "fator_r": _fator_r_na_tela(resultado.fator_r),
        "anexos": [_anexo_na_tela(anexo) for anexo in resultado.anexos],
        "tributos": tributos,
        "segregacao": [
            {
                "mercado": _ROTULO_DO_MERCADO[anexo.mercado],
                "anexo": anexo.anexo,
                "segmento": _ROTULO_DO_SEGMENTO[segmento.segmento],
                "receita": _dinheiro_ptbr(segmento.receita),
                "tributos": _dinheiro_ptbr(segmento.total),
            }
            for anexo in resultado.anexos
            for segmento in anexo.segmentos
        ],
        "memoria": [
            {
                "ordem": passo.ordem,
                "descricao": _texto_da_memoria_em_ptbr(passo.descricao),
                "valor": _texto_da_memoria_em_ptbr(passo.valor),
                "dispositivo": passo.dispositivo,
            }
            for passo in resultado.memoria
        ],
    }


def _contexto_do_pre_das(empresa, ano, mes) -> dict:
    """Pré-DAS do mês: calcula pelo serviço e traduz a recusa em lista de bloqueios."""
    contexto = {
        "mes_rotulo": _mes_por_extenso(ano, mes),
        "url_receita": _url_do_mes(empresa, ano, mes),
        "url_atividades": _url_atividades(empresa),
        "url_folhas": _url_folhas(empresa, ano),
    }
    try:
        resultado = servico_pre_das.pre_das(empresa, ano, mes)
    except servico_pre_das.PreDasRecusado as exc:
        contexto.update(
            recusado=True,
            bloqueios=[_bloqueio_na_tela(b, empresa, ano, mes) for b in exc.bloqueios],
        )
        return contexto
    except servico_receita.ReceitaErro as exc:
        contexto.update(recusado=False, erro_competencia=exc.mensagem)
        return contexto
    contexto.update(recusado=False, erro_competencia="", **_bloco_do_pre_das(resultado))
    return contexto


@login_required
@require_safe
def pre_das(request):
    """Pré-DAS do mês por empresa (arquétipo D, conferência). Consulta: `papel_pode_consultar_
    documentos`. Recusa do cálculo é resposta 200 com a lista de bloqueios, nada gravado."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar o pré-DAS do Simples Nacional."
        )

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        "mostrar_ano": True,
        "mostrar_mes": True,
        "aviso_do_pre_das": _AVISO_DO_PRE_DAS,
        "pode_escriturar": _pode_escriturar(request),
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/pre_das.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/pre_das.html", contexto)

    ano, mes = competencia
    contexto.update(_contexto_do_pre_das(empresa, ano, mes))
    return render(request, "fiscal/pre_das.html", contexto)


# ---------------------------------------------------------------------------
# Atividades da empresa (tela 2)
# ---------------------------------------------------------------------------


def _dados_da_atividade_na_tela(atividade) -> dict:
    return {
        "descricao": atividade.descricao,
        "codigo_subitem": atividade.codigo_subitem or "—",
        "enquadramento": atividade.get_enquadramento_display(),
        "dispositivo": servico_pre_das.DISPOSITIVO_DO_ENQUADRAMENTO[atividade.enquadramento],
        "inicio": _data_na_tela(atividade.inicio),
        "fim": _data_na_tela(atividade.fim) if atividade.fim else "em aberto",
        "padrao": "Sim" if atividade.padrao else "Não",
    }


def _linha_da_atividade(atividade, empresa, pode_escriturar) -> dict:
    linha = {
        **_dados_da_atividade_na_tela(atividade),
        "pode_editar": pode_escriturar,
        "url_editar": reverse("fiscal_web:atividade_editar", args=[empresa.pk, atividade.pk]),
        "url_encerrar": None,
    }
    if atividade.fim is None:
        linha["url_encerrar"] = reverse(
            "fiscal_web:atividade_encerrar", args=[empresa.pk, atividade.pk]
        )
    return linha


@login_required
@require_safe
def atividades(request):
    """Atividades da empresa com vigência e enquadramento. Consulta: `papel_pode_consultar_
    documentos`. Cadastro e alteração são telas próprias, com a empresa no caminho."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar as atividades do Simples Nacional."
        )

    empresa, erro = _empresa_da_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa),
        "pode_escriturar": pode_escriturar,
        "mensagem_sem_permissao": _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES,
        "catalogo": _ENQUADRAMENTOS_NA_TELA,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/atividades.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/atividades.html", contexto)

    lista = AtividadeEmpresa.objects.filter(empresa=empresa).order_by("inicio", "id")
    contexto.update(
        atividades=[_linha_da_atividade(a, empresa, pode_escriturar) for a in lista],
        url_nova=reverse("fiscal_web:atividade_nova", args=[empresa.pk]),
    )
    return render(request, "fiscal/atividades.html", contexto)


def _valores_da_atividade(atividade=None) -> dict:
    """Valores do formulário. Com `atividade`, preenche com o que está gravado."""
    if atividade is None:
        return {
            "descricao": "",
            "codigo_subitem": "",
            "enquadramento": "",
            "inicio": "",
            "fim": "",
            "padrao": False,
        }
    return {
        "descricao": atividade.descricao,
        "codigo_subitem": atividade.codigo_subitem,
        "enquadramento": atividade.enquadramento,
        "inicio": _data_na_tela(atividade.inicio),
        "fim": _data_na_tela(atividade.fim),
        "padrao": atividade.padrao,
    }


def _tela_da_atividade(request, empresa, *, valores, atividade=None, status=200):
    if atividade is None:
        titulo = "Nova atividade"
        url_envio = reverse("fiscal_web:atividade_nova", args=[empresa.pk])
    else:
        titulo = "Alterar atividade"
        url_envio = reverse("fiscal_web:atividade_editar", args=[empresa.pk, atividade.pk])
    contexto = {
        "empresa": empresa,
        "titulo": titulo,
        "valores": valores,
        "url_envio": url_envio,
        "url_voltar": _url_atividades(empresa),
        "opcoes_enquadramento": EnquadramentoAtividade.choices,
        "catalogo": _ENQUADRAMENTOS_NA_TELA,
        "descricao_maxima": 200,
        "codigo_maximo": 20,
        "editando": atividade is not None,
    }
    return render(request, "fiscal/atividade_form.html", contexto, status=status)


def _dados_da_atividade_do_formulario(valores) -> dict:
    """Converte o formulário no dicionário do serviço. Recusa com mensagem, sem gravar."""
    if valores["enquadramento"] not in EnquadramentoAtividade.values:
        raise servico_pre_das.EntradaInvalidaAtividade(
            "Escolha o enquadramento da atividade no catálogo."
        )
    if not valores["inicio"].strip():
        raise servico_pre_das.EntradaInvalidaAtividade("Informe o início da vigência (dd/mm/aaaa).")
    inicio = _data_do_formulario(valores["inicio"])
    if inicio is None:
        raise servico_pre_das.EntradaInvalidaAtividade(
            "O início da vigência é uma data inválida: use dd/mm/aaaa."
        )
    fim = None
    if valores["fim"].strip():
        fim = _data_do_formulario(valores["fim"])
        if fim is None:
            raise servico_pre_das.EntradaInvalidaAtividade(
                "O fim da vigência é uma data inválida: use dd/mm/aaaa, ou deixe em branco "
                "para a atividade ficar em aberto."
            )
    return {
        "descricao": valores["descricao"],
        "codigo_subitem": valores["codigo_subitem"],
        "enquadramento": valores["enquadramento"],
        "inicio": inicio,
        "fim": fim,
        "padrao": valores["padrao"],
    }


def _salvar_atividade_post(request, empresa, atividade=None):
    """Cadastra (atividade None) ou altera. Recusa do serviço vira mensagem; nada gravado."""
    campos = ("descricao", "codigo_subitem", "enquadramento", "inicio", "fim")
    valores = {campo: request.POST.get(campo, "") for campo in campos}
    # O checkbox envia "1" quando marcado e não envia nada quando não; qualquer outro valor é "não".
    valores["padrao"] = request.POST.get("padrao", "") == "1"
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DA_ATIVIDADE)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_da_atividade(
            request, empresa, valores=valores, atividade=atividade, status=400
        )
    try:
        dados = _dados_da_atividade_do_formulario(valores)
        if atividade is None:
            servico_pre_das.cadastrar_atividade(
                empresa, dados, usuario=request.user, request=request
            )
        else:
            servico_pre_das.alterar_atividade(
                atividade, dados, usuario=request.user, request=request
            )
    except (servico_pre_das.EntradaInvalidaAtividade, servico_pre_das.AtividadeConflito) as exc:
        messages.error(request, exc.mensagem)
        return _tela_da_atividade(request, empresa, valores=valores, atividade=atividade)
    messages.success(
        request,
        "Atividade cadastrada." if atividade is None else "Atividade alterada.",
    )
    return redirect(_url_atividades(empresa))


def _atividade_da_empresa(empresa, atividade_id):
    # Atividade de outra empresa, mesmo do mesmo escritório, é 404 (isolamento).
    return get_object_or_404(AtividadeEmpresa, pk=atividade_id, empresa=empresa)


@login_required
@require_http_methods(["GET", "POST"])
def atividade_nova(request, empresa_id):
    """GET: formulário de cadastro. POST: cadastra (enquadramento e vigência, com trilha)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_da_atividade(request, empresa, valores=_valores_da_atividade())
    return _salvar_atividade_post(request, empresa)


@login_required
@require_http_methods(["GET", "POST"])
def atividade_editar(request, empresa_id, atividade_id):
    """GET: formulário com o que está gravado. POST: altera (vigência, padrão, enquadramento)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    atividade = _atividade_da_empresa(empresa, atividade_id)
    if request.method == "GET":
        return _tela_da_atividade(
            request, empresa, valores=_valores_da_atividade(atividade), atividade=atividade
        )
    return _salvar_atividade_post(request, empresa, atividade)


def _tela_de_encerrar_atividade(request, empresa, atividade, *, fim_digitado="", status=200):
    contexto = {
        "empresa": empresa,
        "atividade": _dados_da_atividade_na_tela(atividade),
        "ja_encerrada": atividade.fim is not None,
        "fim_digitado": fim_digitado,
        "url_envio": reverse("fiscal_web:atividade_encerrar", args=[empresa.pk, atividade.pk]),
        "url_voltar": _url_atividades(empresa),
    }
    return render(request, "fiscal/atividade_encerrar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def atividade_encerrar(request, empresa_id, atividade_id):
    """Encerra a vigência de uma atividade em aberto, com data de fim (dd/mm/aaaa)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    atividade = _atividade_da_empresa(empresa, atividade_id)
    if request.method == "GET":
        return _tela_de_encerrar_atividade(request, empresa, atividade)

    fim_bruto = request.POST.get("fim", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ENCERRAR_ATIVIDADE)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_encerrar_atividade(
            request, empresa, atividade, fim_digitado=fim_bruto, status=400
        )
    fim = _data_do_formulario(fim_bruto) if fim_bruto.strip() else None
    if fim is None:
        messages.error(request, "Informe o fim da vigência em dd/mm/aaaa.")
        return _tela_de_encerrar_atividade(request, empresa, atividade, fim_digitado=fim_bruto)
    if atividade.fim is not None:
        messages.error(
            request,
            f"Esta atividade já tem fim de vigência em {_data_na_tela(atividade.fim)}. "
            "Para outra data, altere a atividade.",
        )
        return _tela_de_encerrar_atividade(request, empresa, atividade, fim_digitado=fim_bruto)
    try:
        servico_pre_das.alterar_atividade(
            atividade, {"fim": fim}, usuario=request.user, request=request
        )
    except (servico_pre_das.EntradaInvalidaAtividade, servico_pre_das.AtividadeConflito) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_encerrar_atividade(request, empresa, atividade, fim_digitado=fim_bruto)
    messages.success(request, f"Atividade encerrada em {_data_na_tela(fim)}.")
    return redirect(_url_atividades(empresa))


# ---------------------------------------------------------------------------
# Folha para o fator r (tela 3)
# ---------------------------------------------------------------------------


def _linha_da_folha(folha, empresa, pode_escriturar) -> dict:
    """Uma folha: componentes, total e as ações que o estado permite (ou bloqueia, com motivo)."""
    rascunho = folha.estado == EstadoFolhaFatorR.RASCUNHO
    confirmada = folha.estado == EstadoFolhaFatorR.CONFIRMADA
    if not pode_escriturar:
        confirmar = "bloqueado" if rascunho else ""
        estornar = "bloqueado" if confirmada else ""
    else:
        confirmar = "ativo" if rascunho else ""
        estornar = "ativo" if confirmada else ""
    return {
        "competencia": f"{folha.mes:02d}/{folha.ano}",
        "estado": folha.get_estado_display(),
        "valores": [_dinheiro_ptbr(getattr(folha, nome)) for nome in FolhaFatorR.COMPONENTES],
        "total": _dinheiro_ptbr(folha.total),
        "documento": folha.documento_suporte,
        "motivo_estorno": folha.motivo_estorno,
        "confirmar": confirmar,
        "estornar": estornar,
        "url_confirmar": reverse("fiscal_web:folha_confirmar", args=[empresa.pk, folha.pk]),
        "url_estornar": reverse("fiscal_web:folha_estornar", args=[empresa.pk, folha.pk]),
    }


def _pendentes_da_folha_em_texto(pendentes) -> str:
    return "; ".join(
        f"{mes:02d}/{ano} ({_ROTULO_DA_SITUACAO_DA_FOLHA.get(situacao, situacao)})"
        for ano, mes, situacao in pendentes
    )


def _linha_do_fs12(ano, mes, lancada, resultado) -> dict:
    """FS12 do PA (art. 22 da Res. CGSN 140, pela janela do RBT12) e a folha confirmada do mês.

    `lancada` é a folha não estornada do mês (ou None) e `resultado` é o FS12 do mês, já
    calculado em lote por `servico_folha.fs12_do_ano` (A9 da auditoria DL-075: sem consulta
    por mês aqui). `resultado` pode ser a recusa `ApuracaoRecusada` do mês.
    """
    folha_do_mes = (
        _dinheiro_ptbr(lancada.total)
        if lancada is not None and lancada.estado == EstadoFolhaFatorR.CONFIRMADA
        else "—"
    )
    linha = {"competencia": _mes_por_extenso(ano, mes), "folha_do_mes": folha_do_mes}
    if isinstance(resultado, apuracao.ApuracaoRecusada):
        return {**linha, "fs12": "Não calculado", "regra": "—", "situacao": resultado.mensagem}
    fs = resultado
    if fs.valor is None:
        return {
            **linha,
            "fs12": "Não calculado",
            "regra": fs.regra,
            "situacao": "Faltam confirmar: " + _pendentes_da_folha_em_texto(fs.pendentes),
        }
    return {
        **linha,
        "fs12": _dinheiro_ptbr(fs.valor),
        "regra": fs.regra,
        "situacao": "Calculado com as folhas confirmadas da janela",
    }


@login_required
@require_safe
def folhas_fator_r(request):
    """Folhas da empresa no ano, e o FS12 de cada mês. Consulta: `papel_pode_consultar_
    documentos`. Lançar, confirmar e estornar são telas próprias."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite consultar a folha para o fator r."
        )

    empresa, erro = _empresa_da_escrituracao(request)
    ano_bruto = request.GET.get("ano", "").strip()
    hoje = timezone.localdate()
    ano = _inteiro_de_filtro(ano_bruto) if ano_bruto else hoje.year
    if ano is None or not (2000 <= ano <= 2100):
        erro = erro or "Ano inválido: informe o ano com quatro dígitos (AAAA)."
        ano = hoje.year
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa),
        "ano": ano,
        "ano_filtro": str(ano),
        "mostrar_ano": True,
        "pode_escriturar": pode_escriturar,
        "mensagem_sem_permissao": _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES,
        "componentes": [
            {"nome": nome, "rotulo": _ROTULO_DO_COMPONENTE[nome]}
            for nome in FolhaFatorR.COMPONENTES
        ],
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/folhas_fator_r.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/folhas_fator_r.html", contexto)

    folhas = list(FolhaFatorR.objects.filter(empresa=empresa, ano=ano).order_by("mes", "id"))
    # A9 (auditoria DL-075): o FS12 dos 12 meses sai de uma leitura só (folhas e períodos),
    # e não de uma consulta por mês, que fazia 176 consultas na página.
    ativa_por_mes = {
        folha.mes: folha for folha in folhas if folha.estado != EstadoFolhaFatorR.ESTORNADA
    }
    fs12_por_mes = servico_folha.fs12_do_ano(empresa, ano)
    contexto.update(
        folhas=[_linha_da_folha(folha, empresa, pode_escriturar) for folha in folhas],
        meses_fs12=[
            _linha_do_fs12(ano, mes, ativa_por_mes.get(mes), fs12_por_mes[mes])
            for mes in range(1, 13)
        ],
        url_nova=reverse("fiscal_web:folha_nova", args=[empresa.pk])
        + "?"
        + urlencode({"ano": ano}),
    )
    return render(request, "fiscal/folhas_fator_r.html", contexto)


def _valores_da_folha(request) -> dict:
    """Valores iniciais do lançamento: a competência pedida, ou a corrente."""
    hoje = timezone.localdate()
    ano = _inteiro_de_filtro(request.GET.get("ano", "").strip())
    mes = _inteiro_de_filtro(request.GET.get("mes", "").strip())
    valores = {
        "ano": str(ano) if ano is not None else str(hoje.year),
        "mes": f"{mes:02d}" if mes is not None and 1 <= mes <= 12 else f"{hoje.month:02d}",
        "documento_suporte": "",
    }
    valores.update({nome: "" for nome in FolhaFatorR.COMPONENTES})
    return valores


def _tela_de_lancar_folha(request, empresa, *, valores, status=200):
    contexto = {
        "empresa": empresa,
        "valores": valores,
        "opcoes_mes": _MESES_DO_ANO,
        "componentes": [
            {"nome": nome, "rotulo": _ROTULO_DO_COMPONENTE[nome], "valor": valores[nome]}
            for nome in FolhaFatorR.COMPONENTES
        ],
        "suporte_maximo": servico_folha.DOCUMENTO_SUPORTE_MAXIMO,
        "url_envio": reverse("fiscal_web:folha_nova", args=[empresa.pk]),
        "url_voltar": _url_folhas(empresa, valores["ano"]),
    }
    return render(request, "fiscal/folha_form.html", contexto, status=status)


def _lancar_folha_post(request, empresa):
    campos = ("ano", "mes", "documento_suporte", *FolhaFatorR.COMPONENTES)
    valores = {campo: request.POST.get(campo, "") for campo in campos}
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DA_FOLHA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_lancar_folha(request, empresa, valores=valores, status=400)

    ano = _inteiro_de_filtro(valores["ano"].strip())
    mes = _inteiro_de_filtro(valores["mes"].strip())
    if ano is None or mes is None or not 1 <= mes <= 12:
        messages.error(request, "Informe o ano e o mês da competência, com números.")
        return _tela_de_lancar_folha(request, empresa, valores=valores)

    componentes = {}
    for nome in FolhaFatorR.COMPONENTES:
        rotulo = _ROTULO_DO_COMPONENTE[nome]
        try:
            bruto = _valor_do_formulario(valores[nome])
        except ValorInvalidoNoFormulario as exc:
            # A4 (auditoria DL-075): "10.000" dava 500 nesta tela. Agora mostra a mensagem,
            # com status 200 como na receita, e não grava nada.
            messages.error(request, f"{rotulo}: {exc}")
            return _tela_de_lancar_folha(request, empresa, valores=valores)
        if not bruto:
            messages.error(
                request,
                f"Informe {rotulo.lower()}. Use 0,00 se não houve: não há folha zero por omissão.",
            )
            return _tela_de_lancar_folha(request, empresa, valores=valores)
        if not _so_digitos_com_ponto_decimal(bruto):
            # Notação científica e sinal não são valor digitado. O serviço aceitaria "1e3".
            messages.error(
                request,
                f"{rotulo}: valor inválido. Use só números, com vírgula ou ponto para os "
                "centavos (ex.: 1.234,56).",
            )
            return _tela_de_lancar_folha(request, empresa, valores=valores)
        componentes[nome] = bruto

    try:
        servico_folha.lancar_folha(
            empresa,
            ano,
            mes,
            componentes,
            valores["documento_suporte"],
            usuario=request.user,
            request=request,
        )
    except (servico_folha.FolhaErro, servico_receita.ReceitaErro) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_lancar_folha(request, empresa, valores=valores)
    messages.success(
        request,
        f"Folha de {mes:02d}/{ano} lançada em rascunho. Ela não entra no FS12 até ser confirmada.",
    )
    return redirect(_url_folhas(empresa, ano))


@login_required
@require_http_methods(["GET", "POST"])
def folha_nova(request, empresa_id):
    """GET: formulário com os cinco componentes. POST: lança a folha do mês em rascunho."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_de_lancar_folha(request, empresa, valores=_valores_da_folha(request))
    return _lancar_folha_post(request, empresa)


def _folha_da_empresa(empresa, folha_id):
    # Folha de outra empresa, mesmo do mesmo escritório, é 404 (isolamento).
    return get_object_or_404(FolhaFatorR, pk=folha_id, empresa=empresa)


@login_required
@require_http_methods(["POST"])
def folha_confirmar(request, empresa_id, folha_id):
    """POST — rascunho → confirmada. A partir daqui a folha entra no FS12 e não muda."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    folha = _folha_da_empresa(empresa, folha_id)
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_SEM_CAMPOS_DA_FOLHA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect(_url_folhas(empresa, folha.ano))
    try:
        servico_folha.confirmar_folha(folha, usuario=request.user, request=request)
    except servico_folha.FolhaErro as exc:
        messages.error(request, exc.mensagem)
    else:
        messages.success(
            request,
            f"Folha de {folha.mes:02d}/{folha.ano} confirmada. Ela entra no FS12 e não pode mais "
            "ser alterada: para corrigir, estorne com motivo.",
        )
    return redirect(_url_folhas(empresa, folha.ano))


def _tela_de_estornar_folha(request, empresa, folha, *, motivo, status=200):
    contexto = {
        "empresa": empresa,
        "competencia": f"{folha.mes:02d}/{folha.ano}",
        "estado": folha.get_estado_display(),
        "total": _dinheiro_ptbr(folha.total),
        "documento": folha.documento_suporte,
        "confirmada": folha.estado == EstadoFolhaFatorR.CONFIRMADA,
        "motivo": motivo,
        "motivo_maximo": servico_folha.MOTIVO_MAXIMO,
        "url_envio": reverse("fiscal_web:folha_estornar", args=[empresa.pk, folha.pk]),
        "url_voltar": _url_folhas(empresa, folha.ano),
    }
    return render(request, "fiscal/folha_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def folha_estornar(request, empresa_id, folha_id):
    """GET: confirmação com o motivo. POST: confirmada → estornada (motivo obrigatório)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_SIMPLES)
    empresa = _empresa_escopada(request, empresa_id)
    folha = _folha_da_empresa(empresa, folha_id)
    if request.method == "GET":
        return _tela_de_estornar_folha(request, empresa, folha, motivo="")

    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_MOTIVO_DA_FOLHA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_folha(request, empresa, folha, motivo=motivo, status=400)
    try:
        servico_folha.estornar_folha(folha, motivo, usuario=request.user, request=request)
    except servico_folha.FolhaErro as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_folha(request, empresa, folha, motivo=motivo)
    messages.success(
        request,
        f"Folha de {folha.mes:02d}/{folha.ano} estornada. Ela saiu do FS12; para o mês, "
        "lance outra folha se for o caso.",
    )
    return redirect(_url_folhas(empresa, folha.ano))


# ---------------------------------------------------------------------------
# DL-076 (frente B): ISS por município — apuração do ISS próprio, ISS retido sofrido, ISS
# devido a outros municípios, alíquotas do escritório, regime por empresa e regras (só leitura).
#
# CONFERÊNCIA, nunca guia (DL-076, item 5): a apuração mostra o que `apps.fiscal.iss_municipal`
# calcula e confere, com a memória e o dispositivo de cada passo. Nenhuma tela gera nem transmite
# guia. A regra fica no serviço; aqui há autorização, isolamento, leitura da entrada, formatação
# pt-BR e tradução de recusa (mesmo critério da API, `apps/fiscal/api.py`, seção DL-076).
#
# Leitura: `papel_pode_consultar_documentos`. Escrita (alíquota e regime): `papel_pode_escriturar_
# fiscal`, recusada no SERVIDOR também no POST. A alíquota é do ESCRITÓRIO ATIVO (id de outro
# escritório: 404). Regime e apurações são da EMPRESA (id de outra empresa, mesmo do escritório:
# 404). Sem empresa escolhida, a tela de uma empresa pede a escolha e não apura nada.
# ---------------------------------------------------------------------------

_MENSAGEM_SEM_CONSULTA_DO_ISS = "Seu papel não permite consultar o ISS municipal."
_MENSAGEM_SEM_PERMISSAO_DO_ISS = (
    "Seu papel consulta o ISS municipal, mas não cadastra nem altera alíquota ou regime: "
    "peça a um administrador ou gestor do escritório."
)
_TEXTO_DE_CONFERENCIA_DO_ISS = (
    "Conferência para emissão da guia no portal do município — o DataLedger não gera guia nem "
    "transmite."
)
# Faixa e exceção são lidas do serviço (constante pública), não redigidas aqui: se a lista de
# subitens da exceção mudar, a tela acompanha.
_TEXTO_DA_FAIXA_DA_ALIQUOTA = (
    "Faixa de 2% a 5% (LC 116/2003, art. 8º, II, e art. 8º-A). Os subitens "
    f"{', '.join(sorted(servico_iss.SUBITENS_EXCECAO_DO_MINIMO))} podem ficar abaixo de 2% pela "
    "exceção do § 1º do art. 8º-A da LC 116: entram com aviso, não são recusados."
)
_TEXTO_DO_REGIME_DO_ISS = (
    "Regime por exercício: por alíquota (apuração nota a nota), fixo de autônomo ou fixo de "
    "sociedade de profissionais. O fixo não tem apuração por alíquota: a apuração recusa e lista "
    "as notas para conferência. Empresa do Simples Nacional não tem apuração aqui: o ISS dela "
    "sai no pré-DAS."
)
_TEXTO_DAS_REGRAS_DO_MUNICIPIO = (
    "Somente leitura. A regra do município (vencimento, regra do dia não útil e fonte) é dado "
    "legal com vigência; não há tela para cadastrá-la nesta versão."
)
_PADRAO_IBGE = re.compile(r"[0-9]{7}")
# Valor monetário escrito pelo serviço na memória (`str(Decimal)`, com ponto e duas casas).
_PADRAO_DINHEIRO_NA_MEMORIA = re.compile(r"-?[0-9]+\.[0-9]{2}")
# Recusas do serviço que se resolvem em outra tela, com o município ou a competência já
# conhecidos pela própria apuração.
_CODIGOS_DO_REGIME_DO_ISS = frozenset({"regime_iss_ausente", "regime_fixo"})
_CODIGOS_DA_REGRA_DO_MUNICIPIO = frozenset(
    {"regra_municipio_ausente", "regra_municipio_fora_de_vigencia", "regra_municipio_sobreposta"}
)
_CAMPOS_DO_FORMULARIO_DA_ALIQUOTA = (
    "municipio_ibge",
    "subitem",
    "percentual",
    "fonte",
    "inicio",
    "fim",
)
_CAMPOS_DO_FORMULARIO_DO_REGIME = ("exercicio", "regime", "municipio_ibge")

_CONTRATO_ALIQUOTA_ISS = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", *_CAMPOS_DO_FORMULARIO_DA_ALIQUOTA},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro da alíquota do ISS",
)
_CONTRATO_ENCERRAR_ALIQUOTA_ISS = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "fim"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no encerramento da vigência da alíquota do ISS",
)
_CONTRATO_REGIME_ISS_TELA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", *_CAMPOS_DO_FORMULARIO_DO_REGIME},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no regime do ISS da empresa",
)

# Textos das duas telas de relatório. Um só template serve às duas; o que muda é o rótulo da
# coluna de valor e se há vencimento do retido (que só existe no retido sofrido).
_TEXTOS_DO_RELATORIO_MUNICIPAL = {
    "retido": {
        "titulo": "ISS retido sofrido",
        "descricao": (
            "Notas em que o tomador retém o ISS (tpRetISSQN 2 ou 3). O valor retido não entra "
            "no ISS a recolher do prestador: quem recolhe é o tomador, no município de incidência. "
            "O vencimento aqui é informativo."
        ),
        "coluna_valor": "ISS retido (R$)",
        "mostrar_vencimento": True,
        "sem_notas": "Nenhuma nota com ISS retido sofrido na competência.",
    },
    "outros": {
        "titulo": "ISS devido a outros municípios",
        "descricao": (
            "Notas de ISS devido em município de incidência diferente do estabelecimento. Os "
            "valores são os da própria nota: nada é calculado aqui."
        ),
        "coluna_valor": "ISS da nota (R$)",
        "mostrar_vencimento": False,
        "sem_notas": "Nenhuma nota de ISS devido a outro município na competência.",
    },
}


def _aliquota_ptbr(valor) -> str:
    """Alíquota em pontos (5 = 5%) com 4 casas, como a conferência a guarda: '5,0000%'.
    Só exibição: a comparação com o vISSQN é feita pelo serviço, com precisão total."""
    if valor is None:
        return "—"
    return f"{_decimal_ptbr(valor, 4)}%"


def _valor_da_memoria_na_tela(texto: str) -> str:
    """Só o valor monetário escrito pelo serviço (`1234.56`) vira pt-BR. Datas, códigos e textos
    seguem como estão: a regex não pega dispositivo como 'Decreto 1.667/2018' (não tem duas casas
    depois do ponto)."""
    if _PADRAO_DINHEIRO_NA_MEMORIA.fullmatch(texto):
        return _dinheiro_ptbr(Decimal(texto))
    return texto


def _vigencia_na_tela(inicio, fim) -> str:
    if fim is None:
        return f"desde {_data_na_tela(inicio)}, em aberto"
    return f"{_data_na_tela(inicio)} a {_data_na_tela(fim)}"


def _nome_de_usuario(usuario) -> str:
    return usuario.get_username() if usuario is not None else "—"


def _tomador_texto(nome: str, documento: str) -> str:
    if nome and documento:
        return f"{nome} ({documento})"
    return nome or documento or "—"


def _nomes_dos_municipios(codigos) -> dict[str, str]:
    """Nome de cada município pela regra cadastrada (só para exibir). Código sem regra fica sem
    nome, e a tela mostra o código cru: não inventa um nome."""
    codigos = {codigo for codigo in codigos if codigo}
    if not codigos:
        return {}
    nomes: dict[str, str] = {}
    for regra in RegraIssMunicipio.objects.filter(municipio_ibge__in=codigos).order_by(
        "inicio_vigencia", "id"
    ):
        nomes.setdefault(regra.municipio_ibge, regra.nome)
    return nomes


def _rotulo_do_municipio(codigo, nomes) -> str:
    if not codigo:
        return "Sem município de incidência"
    nome = nomes.get(codigo)
    return f"{nome} ({codigo})" if nome else f"Código {codigo} (sem regra cadastrada)"


def _url_com_filtro(nome_da_rota, empresa, **consulta) -> str:
    """Rota com a empresa (e o que mais houver) na querystring. As telas de UMA empresa levam a
    empresa assim, e não no caminho, porque o filtro é o mesmo da consulta."""
    return reverse(nome_da_rota) + "?" + urlencode({"empresa": empresa.pk, **consulta})


def _url_aliquotas(municipio=None) -> str:
    url = reverse("fiscal_web:iss_aliquotas")
    return f"{url}?{urlencode({'municipio': municipio})}" if municipio else url


def _url_nova_aliquota(municipio=None) -> str:
    url = reverse("fiscal_web:iss_aliquota_nova")
    return f"{url}?{urlencode({'municipio': municipio})}" if municipio else url


def _municipio_do_regime(empresa, ano):
    """Município do estabelecimento no exercício, ou None. Só para montar links de correção."""
    regime = RegimeIssEmpresa.objects.filter(empresa=empresa, exercicio=ano).first()
    return regime.municipio_ibge if regime is not None else None


# ---------------------------------------------------------------------------
# Apuração do ISS próprio (tela 1)
# ---------------------------------------------------------------------------


def _acao_do_bloqueio_iss(bloqueio, empresa, ano, mes, municipio):
    """(rótulo, URL, texto) para resolver o bloqueio. Sem caminho na tela, rótulo e URL vêm None
    e o texto diz o porquê: a tela não inventa um caminho que não existe."""
    codigo = bloqueio.codigo
    if codigo in _CODIGOS_DO_REGIME_DO_ISS:
        return (
            "Ver ou cadastrar o regime do ISS",
            _url_com_filtro("fiscal_web:iss_regimes", empresa),
            "",
        )
    if codigo == "subitem_sem_aliquota_vigente":
        # A mensagem do bloqueio nomeia o subitem; o link já leva o município do estabelecimento.
        return "Cadastrar a alíquota do subitem", _url_nova_aliquota(municipio), ""
    if codigo == "aliquota_sobreposta":
        return "Ver as alíquotas do município", _url_aliquotas(municipio), ""
    if codigo in _CODIGOS_DA_REGRA_DO_MUNICIPIO:
        return (
            "Ver as regras cadastradas",
            reverse("fiscal_web:iss_regras_municipio"),
            "A regra do município não tem tela de cadastro nesta versão: é dado legal, fora de "
            "rota de API.",
        )
    if codigo == "nota_sem_campo_de_iss":
        return (
            "Ver os documentos da competência",
            _url_com_filtro("fiscal_web:documentos_lista", empresa, ano=ano, mes=mes),
            "",
        )
    if codigo in ("nota_cancelada_escriturada", "nota_retida_com_natureza_devida"):
        return (
            "Corrigir a escrituração",
            _url_com_filtro("fiscal_web:notas_a_escriturar", empresa, ano=ano, mes=mes),
            "",
        )
    if codigo == "empresa_no_simples":
        return (
            "Ver o pré-DAS do Simples",
            _url_com_filtro("fiscal_web:pre_das", empresa, ano=ano, mes=mes),
            "",
        )
    return None, None, "Não há ação nesta tela para este bloqueio."


def _bloqueio_iss_na_tela(bloqueio, empresa, ano, mes, municipio) -> dict:
    rotulo, url, texto = _acao_do_bloqueio_iss(bloqueio, empresa, ano, mes, municipio)
    return {
        "mensagem": bloqueio.mensagem,
        "dispositivo": bloqueio.dispositivo,
        "acao": rotulo,
        "url": url,
        "sem_acao": texto,
    }


def _aviso_na_tela(aviso) -> dict:
    return {"mensagem": aviso.mensagem, "dispositivo": aviso.dispositivo}


def _nota_apurada_na_tela(nota) -> dict:
    # Tomador e alíquota aplicada vêm da apuração (A6): a tela não relê o XML da nota.
    tomador = _tomador_texto(nota.tomador_nome, nota.tomador_documento)
    # Esperado e diferença saem com 4 casas: com 2, uma diferença de centavos (a que a tolerância
    # de R$ 0,01 decide) ficaria escondida atrás do arredondamento de exibição.
    return {
        "numero": nota.numero,
        "tomador": tomador,
        "subitem": nota.subitem,
        "base": _dinheiro_ptbr(nota.v_bc),
        "aliquota_nota": _aliquota_ptbr(nota.p_aliq_aplic),
        "iss": _dinheiro_ptbr(nota.v_iss_qn),
        "aliquota_cadastrada": _aliquota_ptbr(nota.aliquota_cadastrada),
        "esperado": _decimal_ptbr(nota.esperado, 4),
        "diferenca": _decimal_ptbr(nota.diferenca, 4),
        "conferida": nota.conferida,
        "situacao": (
            "Conferida"
            if nota.conferida
            else "Pendência: o ISS da nota difere de base × alíquota cadastrada além de "
            f"R$ {_dinheiro_ptbr(servico_iss.TOLERANCIA)}"
        ),
        "avisos": list(nota.avisos),
    }


def _memoria_na_tela(memoria) -> list[dict]:
    return [
        {
            "ordem": passo.ordem,
            "descricao": passo.descricao,
            "valor": _valor_da_memoria_na_tela(passo.valor),
            "dispositivo": passo.dispositivo,
        }
        for passo in memoria
    ]


def _bloco_da_apuracao(empresa, resultado) -> dict:
    notas = [_nota_apurada_na_tela(n) for n in resultado.notas]
    # HI-89 (A2): o aviso de notas não escrituradas tem tela própria (destaque e link). Os demais
    # avisos seguem na lista comum, e este não aparece duas vezes.
    pendentes_de_escrituracao = [
        a for a in resultado.avisos if a.codigo == servico_iss.CODIGO_NOTAS_NAO_ESCRITURADAS
    ]
    return {
        "total": _dinheiro_ptbr(resultado.total),
        "municipio": f"{resultado.nome_municipio} ({resultado.municipio_ibge})",
        "regime": RegimeIss(resultado.regime).label,
        "vencimento_proprio": _vencimento_na_tela(resultado.vencimento_proprio),
        "vencimento_retido": _vencimento_na_tela(resultado.vencimento_retido),
        "regra_dia_nao_util": resultado.regra_dia_nao_util,
        # O dispositivo da regra de vencimento é a constante que o próprio serviço usa no passo 2
        # da memória: a tela cita a mesma fonte, sem reescrevê-la.
        "dispositivo_do_vencimento": servico_iss.DISP_REGRA,
        "aviso_multa": resultado.aviso_multa or "",
        "notas": notas,
        "pendencias": [n["numero"] for n in notas if not n["conferida"]],
        "avisos": [
            _aviso_na_tela(a)
            for a in resultado.avisos
            if a.codigo != servico_iss.CODIGO_NOTAS_NAO_ESCRITURADAS
        ],
        "escrituracao_pendente": (
            _aviso_na_tela(pendentes_de_escrituracao[0]) if pendentes_de_escrituracao else None
        ),
        "memoria": _memoria_na_tela(resultado.memoria),
    }


def _nota_de_relatorio_na_tela(nota, nomes) -> dict:
    ausentes = ", ".join(nota.ausentes)
    return {
        "numero": nota.numero,
        "data": _data_na_tela(nota.data_competencia),
        "situacao": "Cancelada depois de escriturada: fora do total" if nota.cancelada else "",
        "tomador": _tomador_texto(nota.tomador_nome, nota.tomador_documento),
        "municipio": _rotulo_do_municipio(nota.c_loc_incid, nomes),
        "subitem": nota.subitem or "—",
        "base": _dinheiro_ptbr(nota.v_bc),
        "aliquota": _aliquota_ptbr(nota.p_aliq_aplic),
        "valor": _dinheiro_ptbr(nota.v_iss_qn),
        "retencao": DESCRICAO_TP_RET_ISSQN.get(nota.tp_ret_issqn, nota.tp_ret_issqn or "—"),
        "ausentes": (
            f"Campos ausentes ou ilegíveis (não se presume zero): {ausentes}" if ausentes else ""
        ),
    }


def _contexto_da_apuracao(empresa, ano, mes) -> dict:
    contexto = {
        "mes_rotulo": _mes_por_extenso(ano, mes),
        "url_aliquotas": _url_aliquotas(),
        "url_regimes": _url_com_filtro("fiscal_web:iss_regimes", empresa),
        "url_retido": _url_com_filtro("fiscal_web:iss_retido_sofrido", empresa, ano=ano, mes=mes),
        "url_escriturar": _url_com_filtro(
            "fiscal_web:notas_a_escriturar", empresa, ano=ano, mes=mes
        ),
        "url_outros": _url_com_filtro(
            "fiscal_web:iss_outros_municipios", empresa, ano=ano, mes=mes
        ),
        "texto_de_conferencia": _TEXTO_DE_CONFERENCIA_DO_ISS,
    }
    try:
        resultado = servico_iss.apuracao_iss_proprio(empresa, ano, mes)
    except servico_iss.IssRecusado as exc:
        municipio = _municipio_do_regime(empresa, ano)
        nomes = _nomes_dos_municipios(nota.c_loc_incid for nota in exc.notas)
        contexto.update(
            recusado=True,
            bloqueios=[
                _bloqueio_iss_na_tela(b, empresa, ano, mes, municipio) for b in exc.bloqueios
            ],
            notas=[_nota_de_relatorio_na_tela(nota, nomes) for nota in exc.notas],
        )
        return contexto
    contexto.update(recusado=False, **_bloco_da_apuracao(empresa, resultado))
    return contexto


@login_required
@require_safe
def iss_apuracao(request):
    """Apuração do ISS próprio do mês (DL-076, item 5). Consulta: `papel_pode_consultar_documentos`.
    Recusa do serviço é resposta 200 com a lista COMPLETA de bloqueios, nada gravado."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_ISS)

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        "mostrar_ano": True,
        "mostrar_mes": True,
        "pode_escriturar": _pode_escriturar(request),
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/iss_apuracao.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/iss_apuracao.html", contexto)

    ano, mes = competencia
    contexto.update(_contexto_da_apuracao(empresa, ano, mes))
    return render(request, "fiscal/iss_apuracao.html", contexto)


# ---------------------------------------------------------------------------
# Relatórios: ISS retido sofrido (tela 2) e ISS devido a outros municípios (tela 3)
# ---------------------------------------------------------------------------


def _grupo_na_tela(grupo, nomes) -> dict:
    return {
        "municipio": _rotulo_do_municipio(grupo.municipio_ibge, nomes),
        "total": _dinheiro_ptbr(grupo.total),
        "incompletas": ", ".join(grupo.incompletas) or "—",
        "vencimento_retido": _vencimento_na_tela(grupo.vencimento_retido) or "—",
        "aviso": grupo.aviso or "",
    }


def _relatorio_municipal(request, tipo: str):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_ISS)

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        **_TEXTOS_DO_RELATORIO_MUNICIPAL[tipo],
        "mostrar_ano": True,
        "mostrar_mes": True,
        "pode_escriturar": _pode_escriturar(request),
        "texto_de_conferencia": _TEXTO_DE_CONFERENCIA_DO_ISS,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/iss_relatorio.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/iss_relatorio.html", contexto)

    ano, mes = competencia
    if tipo == "retido":
        relatorio = servico_iss.relatorio_iss_retido_sofrido(empresa, ano, mes)
    else:
        relatorio = servico_iss.relatorio_iss_outros_municipios(empresa, ano, mes)
    nomes = _nomes_dos_municipios(
        [n.c_loc_incid for n in relatorio.notas] + [g.municipio_ibge for g in relatorio.grupos]
    )
    contexto.update(
        mes_rotulo=_mes_por_extenso(ano, mes),
        notas=[_nota_de_relatorio_na_tela(n, nomes) for n in relatorio.notas],
        grupos=[_grupo_na_tela(g, nomes) for g in relatorio.grupos],
        avisos=[_aviso_na_tela(a) for a in relatorio.avisos],
        url_apuracao=_url_com_filtro("fiscal_web:iss_apuracao", empresa, ano=ano, mes=mes),
    )
    return render(request, "fiscal/iss_relatorio.html", contexto)


@login_required
@require_safe
def iss_retido_sofrido(request):
    """ISS retido sofrido do mês (HI-86), para empresa de qualquer regime. Consulta."""
    return _relatorio_municipal(request, "retido")


@login_required
@require_safe
def iss_outros_municipios(request):
    """ISS devido a outros municípios do mês (HI-85), sem cálculo. Consulta."""
    return _relatorio_municipal(request, "outros")


# ---------------------------------------------------------------------------
# Alíquotas do escritório (tela 4): listar, cadastrar, alterar e encerrar a vigência
# ---------------------------------------------------------------------------


def _municipio_do_filtro(request):
    """`(município, erro)` do filtro opcional da lista de alíquotas (código IBGE de 7 dígitos)."""
    bruto = request.GET.get("municipio", "").strip()
    if not bruto:
        return None, None
    if not _PADRAO_IBGE.fullmatch(bruto):
        return None, "Município: informe o código IBGE com 7 dígitos."
    return bruto, None


def _linha_da_aliquota(aliquota, pode_escriturar) -> dict:
    return {
        "municipio": aliquota.municipio_ibge,
        "subitem": aliquota.subitem,
        "percentual": _aliquota_ptbr(aliquota.percentual),
        "fonte": aliquota.fonte,
        "vigencia": _vigencia_na_tela(aliquota.inicio_vigencia, aliquota.fim_vigencia),
        "cadastrada_por": _nome_de_usuario(aliquota.criada_por),
        "alterada_por": _nome_de_usuario(aliquota.alterada_por),
        "pode_editar": pode_escriturar,
        "url_editar": reverse("fiscal_web:iss_aliquota_editar", args=[aliquota.pk]),
        "url_encerrar": (
            reverse("fiscal_web:iss_aliquota_encerrar", args=[aliquota.pk])
            if aliquota.fim_vigencia is None
            else None
        ),
    }


@login_required
@require_safe
def iss_aliquotas(request):
    """Alíquotas do ISS do escritório, por município e subitem, com vigência, fonte e autor.
    Consulta: `papel_pode_consultar_documentos`. Cadastro e alteração são telas próprias."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_ISS)

    municipio, erro = _municipio_do_filtro(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        "municipio_filtro": request.GET.get("municipio", "").strip(),
        "pode_escriturar": pode_escriturar,
        "mensagem_sem_permissao": _MENSAGEM_SEM_PERMISSAO_DO_ISS,
        "faixa": _TEXTO_DA_FAIXA_DA_ALIQUOTA,
        "url_nova": _url_nova_aliquota(municipio),
        "url_regras": reverse("fiscal_web:iss_regras_municipio"),
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/iss_aliquotas.html", contexto, status=400)

    consulta = AliquotaIssMunicipal.objects.filter(escritorio=request.escritorio).select_related(
        "criada_por", "alterada_por"
    )
    if municipio:
        consulta = consulta.filter(municipio_ibge=municipio)
    contexto["linhas"] = [
        _linha_da_aliquota(a, pode_escriturar)
        for a in consulta.order_by("municipio_ibge", "subitem", "inicio_vigencia", "id")
    ]
    return render(request, "fiscal/iss_aliquotas.html", contexto)


def _valores_da_aliquota(aliquota=None, *, municipio="") -> dict:
    if aliquota is None:
        return {
            "municipio_ibge": municipio,
            "subitem": "",
            "percentual": "",
            "fonte": "",
            "inicio": "",
            "fim": "",
        }
    return {
        "municipio_ibge": aliquota.municipio_ibge,
        "subitem": aliquota.subitem,
        # Pt-BR, como o contador digita: a mesma vírgula de volta, sem `str()` do Decimal.
        "percentual": _decimal_ptbr(aliquota.percentual, 4),
        "fonte": aliquota.fonte,
        "inicio": _data_na_tela(aliquota.inicio_vigencia),
        "fim": _data_na_tela(aliquota.fim_vigencia),
    }


def _tela_da_aliquota(request, *, valores, aliquota=None, status=200):
    if aliquota is None:
        titulo = "Nova alíquota do ISS"
        url_envio = reverse("fiscal_web:iss_aliquota_nova")
    else:
        titulo = "Alterar alíquota do ISS"
        url_envio = reverse("fiscal_web:iss_aliquota_editar", args=[aliquota.pk])
    contexto = {
        "titulo": titulo,
        "valores": valores,
        "url_envio": url_envio,
        "url_voltar": _url_aliquotas(),
        "editando": aliquota is not None,
        "faixa": _TEXTO_DA_FAIXA_DA_ALIQUOTA,
        "municipio_maximo": 7,
        "subitem_maximo": 5,
        "fonte_maxima": 1000,
    }
    return render(request, "fiscal/iss_aliquota_form.html", contexto, status=status)


def _percentual_do_formulario(bruto: str):
    """Alíquota digitada em pt-BR ('5,0000' ou '5.0000') → Decimal. Nunca float: o que não for
    número decimal sem sinal é recusado aqui, e o serviço cuida da faixa e das casas."""
    if not bruto.strip():
        raise servico_iss.EntradaInvalidaIss("Informe a alíquota em percentual (ex.: 5,00).")
    # ValorAmbiguo é subclasse de ValorInvalidoNoFormulario, por isso vem primeiro. A classe-base
    # cobre '5,00,0', '1.23,4' e similares, que antes subiam como 500 (A1 da auditoria DL-076).
    try:
        texto = _valor_do_formulario(bruto)
    except ValorAmbiguo as exc:
        # Mensagem do campo percentual, sem "reais" (A8): o texto do helper fala em reais.
        raise servico_iss.EntradaInvalidaIss(
            "Valor ambíguo na alíquota: sem vírgula, o ponto é lido como separador de milhar. "
            "Escreva a alíquota com vírgula para as casas decimais (ex.: 5,00 para 5%)."
        ) from exc
    except ValorInvalidoNoFormulario as exc:
        raise servico_iss.EntradaInvalidaIss(
            "Alíquota inválida: use um número com no máximo uma vírgula para as casas decimais "
            "(ex.: 5,00)."
        ) from exc
    if not _so_digitos_com_ponto_decimal(texto):
        raise servico_iss.EntradaInvalidaIss(
            "A alíquota aceita só números, com vírgula para as casas decimais (ex.: 5,00)."
        )
    return Decimal(texto)


def _dados_da_aliquota_do_formulario(valores) -> dict:
    """Converte o formulário no dicionário do serviço. Recusa com mensagem, sem gravar."""
    inicio = _data_do_formulario(valores["inicio"])
    if inicio is None:
        raise servico_iss.EntradaInvalidaIss(
            "O início da vigência é uma data inválida: use dd/mm/aaaa."
        )
    fim = None
    if valores["fim"].strip():
        fim = _data_do_formulario(valores["fim"])
        if fim is None:
            raise servico_iss.EntradaInvalidaIss(
                "O fim da vigência é uma data inválida: use dd/mm/aaaa, ou deixe em branco para a "
                "alíquota ficar em aberto."
            )
    return {
        "municipio_ibge": valores["municipio_ibge"].strip(),
        "subitem": valores["subitem"].strip(),
        "percentual": _percentual_do_formulario(valores["percentual"]),
        "fonte": valores["fonte"],
        "inicio_vigencia": inicio,
        "fim_vigencia": fim,
    }


def _salvar_aliquota_post(request, aliquota=None):
    """Cadastra (aliquota None) ou altera. Recusa do serviço vira mensagem; nada gravado."""
    valores = {campo: request.POST.get(campo, "") for campo in _CAMPOS_DO_FORMULARIO_DA_ALIQUOTA}
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ALIQUOTA_ISS)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_da_aliquota(request, valores=valores, aliquota=aliquota, status=400)
    try:
        dados = _dados_da_aliquota_do_formulario(valores)
        if aliquota is None:
            objeto, avisos = servico_iss.cadastrar_aliquota(
                request.escritorio, dados, usuario=request.user, request=request
            )
            sucesso = (
                f"Alíquota de {objeto.subitem} cadastrada para o município {objeto.municipio_ibge}."
            )
        else:
            objeto, avisos = servico_iss.alterar_aliquota(
                aliquota, dados, usuario=request.user, request=request
            )
            sucesso = "Alíquota alterada."
    except (servico_iss.EntradaInvalidaIss, servico_iss.IssConflito) as exc:
        messages.error(request, exc.mensagem)
        return _tela_da_aliquota(request, valores=valores, aliquota=aliquota)
    # Avisos (exceção do § 1º do art. 8º-A) não recusam: a alíquota entra, e o contador vê o aviso.
    for aviso in avisos:
        messages.warning(request, aviso.mensagem)
    messages.success(request, sucesso)
    return redirect(_url_aliquotas(objeto.municipio_ibge))


@login_required
@require_http_methods(["GET", "POST"])
def iss_aliquota_nova(request):
    """GET: formulário de cadastro (município pode vir na querystring). POST: cadastra."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_ISS)
    if request.method == "GET":
        municipio = request.GET.get("municipio", "").strip()
        return _tela_da_aliquota(request, valores=_valores_da_aliquota(municipio=municipio))
    return _salvar_aliquota_post(request)


@login_required
@require_http_methods(["GET", "POST"])
def iss_aliquota_editar(request, aliquota_id):
    """GET: formulário com o que está gravado. POST: altera (inclusive a vigência). Alíquota de
    OUTRO escritório é 404: a consulta já filtra pelo escritório ativo."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_ISS)
    aliquota = get_object_or_404(
        AliquotaIssMunicipal, pk=aliquota_id, escritorio=request.escritorio
    )
    if request.method == "GET":
        return _tela_da_aliquota(request, valores=_valores_da_aliquota(aliquota), aliquota=aliquota)
    return _salvar_aliquota_post(request, aliquota)


def _tela_de_encerrar_aliquota(request, aliquota, *, fim_digitado="", status=200):
    contexto = {
        "aliquota": _linha_da_aliquota(aliquota, True),
        "fim_digitado": fim_digitado,
        "url_envio": reverse("fiscal_web:iss_aliquota_encerrar", args=[aliquota.pk]),
        "url_voltar": _url_aliquotas(aliquota.municipio_ibge),
    }
    return render(request, "fiscal/iss_aliquota_encerrar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def iss_aliquota_encerrar(request, aliquota_id):
    """Encerra a vigência de uma alíquota em aberto: ela vale até a data informada, inclusive.
    Não há exclusão: o registro fica no histórico, com a trilha da alteração."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_ISS)
    aliquota = get_object_or_404(
        AliquotaIssMunicipal, pk=aliquota_id, escritorio=request.escritorio
    )
    if request.method == "GET":
        return _tela_de_encerrar_aliquota(request, aliquota)

    bruto = request.POST.get("fim", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ENCERRAR_ALIQUOTA_ISS)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_encerrar_aliquota(request, aliquota, fim_digitado=bruto, status=400)
    fim = _data_do_formulario(bruto)
    if fim is None:
        messages.error(
            request,
            "Informe o fim da vigência em dd/mm/aaaa: a alíquota vale até essa data, inclusive.",
        )
        return _tela_de_encerrar_aliquota(request, aliquota, fim_digitado=bruto)
    try:
        encerrada, _avisos = servico_iss.alterar_aliquota(
            aliquota, {"fim_vigencia": fim}, usuario=request.user, request=request
        )
    except (servico_iss.EntradaInvalidaIss, servico_iss.IssConflito) as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_encerrar_aliquota(request, aliquota, fim_digitado=bruto)
    messages.success(
        request, f"Vigência encerrada em {_data_na_tela(fim)}. A alíquota fica no histórico."
    )
    return redirect(_url_aliquotas(encerrada.municipio_ibge))


# ---------------------------------------------------------------------------
# Regime do ISS por empresa e exercício (tela 5) e regras do município (tela 6, só leitura)
# ---------------------------------------------------------------------------


def _linha_do_regime(regime, empresa, pode_escriturar, nomes) -> dict:
    return {
        "exercicio": regime.exercicio,
        "regime": regime.get_regime_display(),
        "municipio": _rotulo_do_municipio(regime.municipio_ibge, nomes),
        "pode_editar": pode_escriturar,
        "url_editar": reverse("fiscal_web:iss_regime_editar", args=[empresa.pk, regime.pk]),
    }


@login_required
@require_safe
def iss_regimes(request):
    """Regime do ISS da empresa, por exercício. Consulta: `papel_pode_consultar_documentos`."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_ISS)

    empresa, erro = _empresa_da_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa),
        "mostrar_ano": False,
        "mostrar_mes": False,
        "pode_escriturar": pode_escriturar,
        "mensagem_sem_permissao": _MENSAGEM_SEM_PERMISSAO_DO_ISS,
        "texto_do_regime": _TEXTO_DO_REGIME_DO_ISS,
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/iss_regimes.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/iss_regimes.html", contexto)

    regimes = list(RegimeIssEmpresa.objects.filter(empresa=empresa).order_by("exercicio", "id"))
    nomes = _nomes_dos_municipios(regime.municipio_ibge for regime in regimes)
    contexto.update(
        linhas=[_linha_do_regime(r, empresa, pode_escriturar, nomes) for r in regimes],
        url_novo=reverse("fiscal_web:iss_regime_novo", args=[empresa.pk]),
    )
    return render(request, "fiscal/iss_regimes.html", contexto)


def _valores_do_regime(regime=None) -> dict:
    if regime is None:
        return {
            "exercicio": str(timezone.localdate().year),
            "regime": "",
            "municipio_ibge": "",
        }
    return {
        "exercicio": str(regime.exercicio),
        "regime": regime.regime,
        "municipio_ibge": regime.municipio_ibge,
    }


def _tela_do_regime(request, empresa, *, valores, regime=None, status=200):
    if regime is None:
        titulo = "Novo regime do ISS"
        url_envio = reverse("fiscal_web:iss_regime_novo", args=[empresa.pk])
    else:
        titulo = "Alterar regime do ISS"
        url_envio = reverse("fiscal_web:iss_regime_editar", args=[empresa.pk, regime.pk])
    contexto = {
        "empresa": empresa,
        "titulo": titulo,
        "valores": valores,
        "url_envio": url_envio,
        "url_voltar": _url_com_filtro("fiscal_web:iss_regimes", empresa),
        "opcoes_regime": RegimeIss.choices,
        "editando": regime is not None,
        "texto_do_regime": _TEXTO_DO_REGIME_DO_ISS,
    }
    return render(request, "fiscal/iss_regime_form.html", contexto, status=status)


def _salvar_regime_post(request, empresa, regime=None):
    """Cadastra (regime None) ou altera o regime do exercício. Recusa vira mensagem, sem gravar."""
    valores = {campo: request.POST.get(campo, "") for campo in _CAMPOS_DO_FORMULARIO_DO_REGIME}
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_REGIME_ISS_TELA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_do_regime(request, empresa, valores=valores, regime=regime, status=400)
    exercicio = _inteiro_de_filtro(valores["exercicio"].strip())
    if exercicio is None:
        messages.error(request, "Informe o exercício com quatro dígitos (AAAA).")
        return _tela_do_regime(request, empresa, valores=valores, regime=regime)
    dados = {
        "exercicio": exercicio,
        "regime": valores["regime"].strip(),
        "municipio_ibge": valores["municipio_ibge"].strip(),
    }
    try:
        if regime is None:
            servico_iss.cadastrar_regime(empresa, dados, usuario=request.user, request=request)
            sucesso = f"Regime do ISS de {exercicio} cadastrado."
        else:
            servico_iss.alterar_regime(regime, dados, usuario=request.user, request=request)
            sucesso = f"Regime do ISS de {exercicio} alterado."
    except (servico_iss.EntradaInvalidaIss, servico_iss.IssConflito) as exc:
        messages.error(request, exc.mensagem)
        return _tela_do_regime(request, empresa, valores=valores, regime=regime)
    messages.success(request, sucesso)
    return redirect(_url_com_filtro("fiscal_web:iss_regimes", empresa))


@login_required
@require_http_methods(["GET", "POST"])
def iss_regime_novo(request, empresa_id):
    """GET: formulário do regime do exercício. POST: cadastra (um regime por exercício)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_ISS)
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _tela_do_regime(request, empresa, valores=_valores_do_regime())
    return _salvar_regime_post(request, empresa)


@login_required
@require_http_methods(["GET", "POST"])
def iss_regime_editar(request, empresa_id, regime_id):
    """GET: formulário com o que está gravado. POST: altera. Regime de OUTRA empresa é 404."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_PERMISSAO_DO_ISS)
    empresa = _empresa_escopada(request, empresa_id)
    regime = get_object_or_404(RegimeIssEmpresa, pk=regime_id, empresa=empresa)
    if request.method == "GET":
        return _tela_do_regime(request, empresa, valores=_valores_do_regime(regime), regime=regime)
    return _salvar_regime_post(request, empresa, regime)


@login_required
@require_safe
def iss_regras_municipio(request):
    """Regras do ISS por município (vencimento, dia não útil, fonte e vigência). Só leitura: a
    regra é dado legal, e o cadastro dela não tem rota nem tela."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_ISS)
    regras = RegraIssMunicipio.objects.order_by("municipio_ibge", "inicio_vigencia", "id")
    contexto = {
        "linhas": [
            {
                "municipio": f"{regra.nome} ({regra.municipio_ibge})",
                "dia_proprio": regra.dia_vencimento_proprio,
                "dia_retido": regra.dia_vencimento_retido,
                "regra_dia_nao_util": regra.regra_dia_nao_util,
                "fonte": regra.fonte,
                "vigencia": _vigencia_na_tela(regra.inicio_vigencia, regra.fim_vigencia),
            }
            for regra in regras
        ],
        "texto_das_regras": _TEXTO_DAS_REGRAS_DO_MUNICIPIO,
        "url_aliquotas": _url_aliquotas(),
    }
    return render(request, "fiscal/iss_regras_municipio.html", contexto)


# ---------------------------------------------------------------------------
# DL-078 (frente B): telas dos SERVIÇOS TOMADOS — escriturar, ISS retido a recolher, retenções
# federais e data de pagamento.
#
# Toda regra (natureza e recusas, avisos A1 a A8, totais, vencimento, competência) vem de
# `apps.fiscal.tomadas` e `apps.fiscal.retencoes`. Aqui há isolamento (404), permissão no servidor,
# formatação pt-BR e montagem da resposta. Recusa do serviço vira MENSAGEM na própria tela, com
# status 200 e nada gravado (mesmo critério da DL-072).
# ---------------------------------------------------------------------------

_MENSAGEM_SEM_CONSULTA_DAS_TOMADAS = "Seu papel não permite consultar as notas tomadas."
_TEXTO_DE_CONFERENCIA_DO_RETIDO = (
    "Conferência para a guia do ISS retido — o DataLedger não gera DAM nem transmite."
)
_TEXTO_DE_CONFERENCIA_DAS_RETENCOES = (
    "Conferência das retenções federais destacadas nas notas — o DataLedger não gera guia, não "
    "transmite EFD-Reinf nem DCTFWeb, e não decide se a retenção era devida."
)

# Texto de APRESENTAÇÃO do catálogo (HI-93): explica cada natureza com o que o próprio código faz
# com ela. Não cria regra: a regra mora em `apps.fiscal.tomadas` (sugestão e recusas).
_DESCRICAO_DA_NATUREZA_TOMADA = {
    NaturezaTomada.TOMADO_ISS_RETIDO_PELO_CLIENTE: (
        "O cliente tomador reteve o ISS. Exige tpRetISSQN 2 no XML. Entra no ISS retido a recolher."
    ),
    NaturezaTomada.TOMADO_SEM_RETENCAO: (
        "O ISS é do prestador, sem retenção. Exige tpRetISSQN 1 no XML. Não entra no ISS retido."
    ),
    NaturezaTomada.TOMADO_PRESTADOR_OUTRO_MUNICIPIO: (
        "Prestador de outro município, com ISS devido no local do tomador e sem retenção "
        "destacada. Exige tpRetISSQN 1 no XML. Em Palmas, pede conferência de CNES e RANFS."
    ),
    NaturezaTomada.TOMADO_DE_MEI: (
        "Prestador MEI. Se o XML trouxer tpRetISSQN 2, a nota entra no ISS retido com aviso para "
        "conferir."
    ),
    NaturezaTomada.TOMADO_DE_SIMPLES: (
        "Prestador ME/EPP do Simples Nacional. Com tpRetISSQN 2, a nota entra no ISS retido."
    ),
    NaturezaTomada.TOMADO_DE_PESSOA_FISICA: (
        "Prestador pessoa física. Com tpRetISSQN 2, a nota entra no ISS retido."
    ),
}

# O motivo da sugestão (o sinal do XML) vem do SERVIÇO, com a natureza: `NotaTomada.motivo_sugestao`
# (auditoria A7). A tela não repete a ordem das regras em texto.

_CONTRATO_ESCRITURAR_TOMADA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "natureza", "acao"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na escrituração da nota tomada",
)
_CONTRATO_ESTORNAR_TOMADA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração da nota tomada",
)
_CONTRATO_DATA_PAGAMENTO_TOMADA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "data_pagamento", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na data de pagamento da nota tomada",
)
# Ações da trilha da data de pagamento (informada e limpa): a tela mostra as duas.
_ACOES_DA_DATA_DE_PAGAMENTO = (
    "escrituracao_tomada.data_pagamento_informada",
    "escrituracao_tomada.data_pagamento_limpa",
)
_CONTRATO_LIMPAR_DATA_PAGAMENTO_TOMADA = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na limpeza da data de pagamento da nota tomada",
)


def _escrituracao_tomada_da_empresa(request, empresa, escrituracao_id):
    # Escrituração de OUTRA empresa, ou de outro escritório, é 404: não confirma que o ID existe.
    return get_object_or_404(
        EscrituracaoTomada.objects.select_related("vinculo__documento", "empresa"),
        pk=escrituracao_id,
        empresa=empresa,
        empresa__escritorio=request.escritorio,
    )


def _municipio_da_tomada(documento):
    # O código de incidência vem do XML guardado (cLocIncid). Ausente fica None: "sem município".
    return campos_tomada_do_documento(documento).c_loc_incid


def _numero_da_nota(documento):
    return documento.numero or documento.identificador


def _data_iso_na_tela(texto_iso):
    if not texto_iso:
        return "—"
    return datetime.fromisoformat(texto_iso).strftime("%d/%m/%Y")


def _natureza_da_tomada_na_tela(nota):
    """`(rotulo, origem)` da coluna Natureza. Com escrituração, mostra a GRAVADA; sem ela, a
    SUGERIDA pelo XML, dizendo que nada foi escriturado (mesmo critério da DL-072, auditoria A6)."""
    if nota.escrituracao is not None:
        origem = (
            "Escriturada"
            if nota.escrituracao.estado == EstadoEscrituracao.EFETIVADA
            else "Rascunho, não efetivada"
        )
        return nota.escrituracao.get_natureza_display(), origem
    if nota.natureza_sugerida is None:
        return ROTULO_SEM_SUGESTAO, "Sem sugestão do XML"
    return NaturezaTomada(nota.natureza_sugerida).label, "Sugerida pelo XML, não escriturada"


def _acao_da_tomada(nota, empresa, pode_escriturar):
    """Ação da linha: `{"rotulo", "url"}` ou None. Quem só consulta não vê botão de escriturar."""
    if not pode_escriturar:
        return None
    if nota.situacao in _SITUACOES_QUE_ESCRITURAM:
        rotulo = "Continuar escrituração" if nota.escrituracao else "Escriturar"
    elif nota.escrituracao is not None and nota.situacao in _SITUACOES_COM_ESCRITURACAO_PARA_VER:
        rotulo = "Ver escrituração"
    else:
        return None
    return {
        "rotulo": rotulo,
        "url": reverse("fiscal_web:tomada_escriturar", args=[empresa.pk, nota.vinculo.pk]),
    }


def _linha_da_tomada(nota, empresa, pode_escriturar, municipio, nomes):
    documento = nota.documento
    natureza, origem = _natureza_da_tomada_na_tela(nota)
    return {
        "numero": _numero_da_nota(documento),
        "emissao": _data_na_tela(nota.data_emissao) or "—",
        "competencia": documento.d_competencia.strftime("%m/%Y")
        if documento.d_competencia
        else "—",
        "prestador": _tomador_texto(documento.prestador_nome, documento.prestador_documento),
        "municipio": _rotulo_do_municipio(municipio, nomes),
        "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        "natureza": natureza,
        "origem_natureza": origem,
        # Recusa nomeada (ex.: tpEmit 2 ou 3) aparece na lista, e não só na tela de escriturar.
        "bloqueio": nota.bloqueio,
        "situacao": _ROTULO_DE_SITUACAO.get(nota.situacao, nota.situacao),
        "acao": _acao_da_tomada(nota, empresa, pode_escriturar),
    }


# ---------------------------------------------------------------------------
# Tela: serviços tomados do mês — arquétipo A (tabela de consulta)
# ---------------------------------------------------------------------------


@login_required
@require_safe
def tomadas_lista(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DAS_TOMADAS)

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        "mostrar_ano": True,
        "mostrar_mes": True,
        "pode_escriturar": pode_escriturar,
        "pagina": None,
        "querystring_sem_pagina": _querystring_sem_pagina(request),
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/tomadas_lista.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/tomadas_lista.html", contexto)

    ano, mes = competencia
    notas = servico_tomadas.notas_tomadas(empresa, ano, mes)
    pagina = Paginator(notas, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    municipios = {n.vinculo.pk: _municipio_da_tomada(n.documento) for n in pagina.object_list}
    nomes = _nomes_dos_municipios(municipios.values())
    a_escriturar = sum(1 for n in notas if n.situacao in _SITUACOES_QUE_ESCRITURAM)
    contexto.update(
        {
            "mes_rotulo": _mes_por_extenso(ano, mes),
            "ano": ano,
            "mes": mes,
            "pagina": pagina,
            "linhas": [
                _linha_da_tomada(n, empresa, pode_escriturar, municipios[n.vinculo.pk], nomes)
                for n in pagina.object_list
            ],
            "total_notas": len(notas),
            "total_a_escriturar": a_escriturar,
            "url_iss_retido": _url_com_filtro(
                "fiscal_web:iss_retido_a_recolher", empresa, ano=ano, mes=mes
            ),
        }
    )
    return render(request, "fiscal/tomadas_lista.html", contexto)


# ---------------------------------------------------------------------------
# Tela: escriturar uma nota tomada — arquétipo B (formulário de documento)
# ---------------------------------------------------------------------------


def _recusa_da_natureza_escolhida(documento, natureza):
    """Motivo, em texto, pelo qual a natureza ESCOLHIDA não pode ser efetivada nesta nota, ou None.

    A regra (T1 exige tpRetISSQN 2; T2 e T3 exigem tpRetISSQN 1) mora em
    `apps.fiscal.tomadas.recusa_de_natureza`. A tela a consulta só para decidir se o botão
    Efetivar aparece habilitado; o servidor recusa de novo na efetivação, de qualquer forma.
    """
    if natureza not in NaturezaTomada.values:
        return servico_tomadas.MENSAGEM_NATUREZA_FORA_DO_CATALOGO
    return servico_tomadas.recusa_de_natureza(natureza, campos_tomada_do_documento(documento))


def _estado_dos_botoes(nota, documento, natureza):
    """`(pode_rascunho, motivo_rascunho, pode_efetivar, motivo_efetivar)`. O motivo é texto e vai
    na tela ao lado do botão desabilitado (direção de arte §2.B: nunca o botão sumindo).

    A ORDEM importa (auditoria A2): o bloqueio da nota (tpEmit 2 ou 3) é testado ANTES da natureza.
    Se a natureza vazia viesse primeiro, o motivo real da recusa nunca apareceria na tela.
    """
    if nota.bloqueio:
        return False, nota.bloqueio, False, nota.bloqueio
    if not natureza:
        # Sem natureza escolhida, os botões ficam HABILITADOS: a tela não tem JavaScript para
        # destravar um botão desabilitado, e o servidor já recusa a natureza vazia com mensagem.
        return True, "", True, ""
    recusa = _recusa_da_natureza_escolhida(documento, natureza)
    return True, "", recusa is None, recusa or ""


def _tela_de_escriturar_tomada(request, empresa, vinculo, *, natureza=None, status=200):
    documento = vinculo.documento
    # ISS, IRRF e CSRF destacados NÃO são campos do DocumentoFiscal: vêm do XML guardado.
    campos = campos_tomada_do_documento(documento)
    nota = servico_tomadas.nota_tomada_do_vinculo(empresa, vinculo)
    escrituracao = nota.escrituracao if nota is not None else None
    sugerida = nota.natureza_sugerida if nota is not None else None
    if natureza is None:
        # Primeira vez: a natureza já gravada, ou a SUGERIDA pelo XML, pré-selecionada e nunca
        # gravada. Sem sugestão, nada vem pré-selecionado.
        natureza = escrituracao.natureza if escrituracao is not None else (sugerida or "")
    contexto = {
        "empresa": empresa,
        "vinculo": vinculo,
        "documento": documento,
        "nota": nota,
        "escrituracao": escrituracao,
        "natureza_selecionada": natureza,
        "catalogo": [
            (valor, rotulo, _DESCRICAO_DA_NATUREZA_TOMADA.get(valor, ""))
            for valor, rotulo in NaturezaTomada.choices
        ],
        "tem_sugestao": sugerida is not None,
        "natureza_sugerida_rotulo": (
            NaturezaTomada(sugerida).label if sugerida is not None else ROTULO_SEM_SUGESTAO
        ),
        # O sinal do XML que o serviço usou para sugerir (auditoria A7).
        "porque_sugestao": nota.motivo_sugestao if nota is not None else "",
        "situacao_rotulo": (
            _ROTULO_DE_SITUACAO.get(nota.situacao, nota.situacao) if nota is not None else None
        ),
        "pode_formulario": nota is not None and nota.situacao in _SITUACOES_QUE_ESCRITURAM,
        "efetivada": nota is not None and nota.situacao == servico_escrituracao.SITUACAO_EFETIVADA,
        "v_serv_ptbr": _valor_ptbr(documento.v_serv),
        "v_liq_ptbr": _valor_ptbr(documento.v_liq),
        "iss_ptbr": _valor_ptbr(campos.v_iss_qn),
        "municipio_rotulo": _rotulo_do_municipio(
            _municipio_da_tomada(documento),
            _nomes_dos_municipios([_municipio_da_tomada(documento)]),
        ),
        "irrf_ptbr": _valor_ptbr(campos.v_ret_irrf),
        "csrf_ptbr": _valor_ptbr(campos.v_ret_csll),
        "retencao": DESCRICAO_TP_RET_ISSQN.get(documento.tp_ret_issqn, documento.tp_ret_issqn),
        "avisos": nota.avisos if nota is not None else (),
        "url_lista": _url_com_filtro(
            "fiscal_web:tomadas_lista",
            empresa,
            ano=documento.d_competencia.year,
            mes=documento.d_competencia.month,
        ),
        "pode_pagamento": nota is not None and escrituracao is not None,
        "url_pagamento": (
            reverse(
                "fiscal_web:tomada_data_pagamento",
                args=[empresa.pk, escrituracao.pk],
            )
            if escrituracao is not None
            else ""
        ),
        "url_estornar": (
            reverse("fiscal_web:tomada_estornar", args=[empresa.pk, escrituracao.pk])
            if escrituracao is not None
            else ""
        ),
    }
    if nota is not None and nota.situacao in _SITUACOES_QUE_ESCRITURAM:
        (
            contexto["pode_rascunho"],
            contexto["motivo_rascunho"],
            contexto["pode_efetivar"],
            contexto["motivo_efetivar"],
        ) = _estado_dos_botoes(nota, documento, natureza)
    return render(request, "fiscal/tomada_escriturar.html", contexto, status=status)


def _escriturar_tomada_post(request, empresa, vinculo):
    natureza = request.POST.get("natureza", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESCRITURAR_TOMADA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar_tomada(request, empresa, vinculo, natureza=natureza, status=400)

    acao = request.POST.get("acao", "")
    if acao not in _ACOES_DO_FORMULARIO_DE_ESCRITURAR:
        messages.error(
            request, "Ação desconhecida. Escolha 'Salvar rascunho' ou 'Efetivar escrituração'."
        )
        return _tela_de_escriturar_tomada(request, empresa, vinculo, natureza=natureza, status=400)

    try:
        if acao == "rascunho":
            servico_tomadas.salvar_rascunho(
                vinculo, natureza, usuario=request.user, request=request
            )
            messages.success(
                request, "Rascunho salvo. A nota continua a escriturar até você efetivar."
            )
            return redirect(
                "fiscal_web:tomada_escriturar", empresa_id=empresa.pk, vinculo_id=vinculo.pk
            )
        escrituracao = servico_tomadas.efetivar_escrituracao_tomada(
            vinculo, natureza, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        # Recusa do serviço (natureza incompatível com o XML, nota cancelada, papel errado...):
        # mensagem na tela, status 200, nada gravado, e a natureza digitada continua lá.
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar_tomada(request, empresa, vinculo, natureza=natureza, status=200)

    if escrituracao.criada_agora:
        messages.success(request, "Nota tomada escriturada com a natureza confirmada.")
    else:
        messages.info(
            request, "Esta nota já estava escriturada com esta natureza. Nada foi alterado."
        )
    return redirect("fiscal_web:tomada_escriturar", empresa_id=empresa.pk, vinculo_id=vinculo.pk)


@login_required
@require_http_methods(["GET", "POST"])
def tomada_escriturar(request, empresa_id, vinculo_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    vinculo = _vinculo_da_empresa(request, empresa, vinculo_id)
    if request.method == "POST":
        return _escriturar_tomada_post(request, empresa, vinculo)
    return _tela_de_escriturar_tomada(request, empresa, vinculo)


# ---------------------------------------------------------------------------
# Telas: estornar e informar a data de pagamento de uma escrituração de tomada
# ---------------------------------------------------------------------------


def _tela_de_estornar_tomada(request, empresa, escrituracao, *, motivo, status=200):
    documento = escrituracao.vinculo.documento
    contexto = {
        "empresa": empresa,
        "escrituracao": escrituracao,
        "documento": documento,
        "efetivada": escrituracao.estado == EstadoEscrituracao.EFETIVADA,
        "natureza_rotulo": escrituracao.get_natureza_display(),
        "estado_rotulo": escrituracao.get_estado_display(),
        "motivo": motivo,
        "motivo_maximo": servico_tomadas.MOTIVO_MAXIMO,
        "url_detalhe": reverse(
            "fiscal_web:tomada_escriturar", args=[empresa.pk, escrituracao.vinculo_id]
        ),
    }
    return render(request, "fiscal/tomada_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def tomada_estornar(request, empresa_id, escrituracao_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    escrituracao = _escrituracao_tomada_da_empresa(request, empresa, escrituracao_id)
    if request.method == "GET":
        return _tela_de_estornar_tomada(request, empresa, escrituracao, motivo="")

    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESTORNAR_TOMADA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_tomada(request, empresa, escrituracao, motivo=motivo, status=400)

    try:
        servico_tomadas.estornar_escrituracao_tomada(
            escrituracao, motivo, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_tomada(request, empresa, escrituracao, motivo=motivo, status=200)

    messages.success(
        request, "Escrituração estornada. A nota voltou para a lista de serviços tomados."
    )
    return redirect(
        "fiscal_web:tomada_escriturar",
        empresa_id=empresa.pk,
        vinculo_id=escrituracao.vinculo_id,
    )


def _trilha_do_pagamento(request, escrituracao):
    """Trilha da data de pagamento: quem informou, quando, a data anterior e a nova, e o motivo.
    Filtrada pelo escritório ativo, como a trilha da DL-072: `objeto_id` sozinho não basta."""
    registros = (
        RegistroAuditoria.objects.filter(
            escritorio=request.escritorio,
            objeto_tipo="EscrituracaoTomada",
            objeto_id=str(escrituracao.pk),
            acao__in=_ACOES_DA_DATA_DE_PAGAMENTO,
        )
        .select_related("usuario")
        .order_by("criado_em", "id")
    )
    trilha = []
    for registro in registros:
        detalhes = registro.detalhes or {}
        antes = detalhes.get("antes") or {}
        depois = detalhes.get("depois") or {}
        trilha.append(
            {
                "quando": timezone.localtime(registro.criado_em).strftime("%d/%m/%Y %H:%M"),
                "operacao": (
                    "Data limpa"
                    if registro.acao == "escrituracao_tomada.data_pagamento_limpa"
                    else "Data informada"
                ),
                "usuario": registro.usuario.get_username() if registro.usuario else "—",
                "antes": _data_iso_na_tela(antes.get("data_pagamento")),
                "depois": _data_iso_na_tela(depois.get("data_pagamento")),
                # A limpeza grava o motivo em `detalhes`; a informação, na coluna da nota.
                "motivo": detalhes.get("motivo", depois.get("motivo_pagamento", "")),
            }
        )
    return trilha


def _janela_da_data_de_pagamento_na_tela(escrituracao):
    """`janela_inicio` e `janela_fim` para o texto de ajuda, ou None. Vem do serviço (HI-98)."""
    if escrituracao.data_emissao is None:
        return {"janela_inicio": None, "janela_fim": None}
    inicio, fim = servico_tomadas.janela_da_data_de_pagamento(
        escrituracao.data_emissao, servico_tomadas.hoje()
    )
    return {"janela_inicio": inicio, "janela_fim": fim}


def _tela_de_data_pagamento(
    request, empresa, escrituracao, *, data_digitada="", motivo="", status=200
):
    documento = escrituracao.vinculo.documento
    contexto = {
        "empresa": empresa,
        "escrituracao": escrituracao,
        "documento": documento,
        "efetivada": escrituracao.estado == EstadoEscrituracao.EFETIVADA,
        "natureza_rotulo": escrituracao.get_natureza_display(),
        "estado_rotulo": escrituracao.get_estado_display(),
        "irrf_ptbr": _valor_ptbr(escrituracao.v_ret_irrf),
        "csrf_ptbr": _valor_ptbr(escrituracao.v_ret_csll),
        "data_pagamento_atual": _data_na_tela(escrituracao.data_pagamento) or "Não informada",
        "tem_data_pagamento": escrituracao.data_pagamento is not None,
        # Janela que o serviço aceita (HI-98). Só existe com emissão (nota efetivada).
        **_janela_da_data_de_pagamento_na_tela(escrituracao),
        "url_limpar_pagamento": reverse(
            "fiscal_web:tomada_data_pagamento_limpar",
            args=[empresa.pk, escrituracao.pk],
        ),
        "data_digitada": data_digitada or _data_na_tela(escrituracao.data_pagamento),
        "motivo": motivo,
        "motivo_maximo": servico_tomadas.MOTIVO_MAXIMO,
        "trilha": _trilha_do_pagamento(request, escrituracao),
        "url_detalhe": reverse(
            "fiscal_web:tomada_escriturar", args=[empresa.pk, escrituracao.vinculo_id]
        ),
    }
    return render(request, "fiscal/tomada_data_pagamento.html", contexto, status=status)


def _data_pagamento_post(request, empresa, escrituracao):
    data_bruta = request.POST.get("data_pagamento", "").strip()
    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_DATA_PAGAMENTO_TOMADA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_data_pagamento(
            request, empresa, escrituracao, data_digitada=data_bruta, motivo=motivo, status=400
        )

    data = _data_do_formulario(data_bruta)
    if data is None:
        messages.error(request, "Data de pagamento inválida: informe dd/mm/aaaa. Nada foi gravado.")
        return _tela_de_data_pagamento(
            request, empresa, escrituracao, data_digitada=data_bruta, motivo=motivo, status=400
        )

    try:
        atualizada = servico_tomadas.informar_data_pagamento(
            escrituracao, data, motivo, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        # Motivo vazio ou longo, ou nota não efetivada: mensagem na tela, nada gravado.
        messages.error(request, exc.mensagem)
        return _tela_de_data_pagamento(
            request, empresa, escrituracao, data_digitada=data_bruta, motivo=motivo, status=200
        )

    if atualizada.criada_agora:
        messages.success(
            request,
            "Data de pagamento informada. O IRRF e a CSRF desta nota passam para o grupo "
            "dessa data.",
        )
    else:
        messages.info(request, "A data de pagamento já era esta. Nada foi alterado.")
    return redirect(
        "fiscal_web:tomada_data_pagamento",
        empresa_id=empresa.pk,
        escrituracao_id=escrituracao.pk,
    )


@login_required
@require_http_methods(["GET", "POST"])
def tomada_data_pagamento(request, empresa_id, escrituracao_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    escrituracao = _escrituracao_tomada_da_empresa(request, empresa, escrituracao_id)
    if request.method == "POST":
        return _data_pagamento_post(request, empresa, escrituracao)
    return _tela_de_data_pagamento(request, empresa, escrituracao)


def _limpar_data_pagamento_post(request, empresa, escrituracao):
    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_LIMPAR_DATA_PAGAMENTO_TOMADA)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_data_pagamento(request, empresa, escrituracao, motivo=motivo, status=400)

    try:
        limpa = servico_tomadas.limpar_data_pagamento(
            escrituracao, motivo, usuario=request.user, request=request
        )
    except servico_escrituracao.EscrituracaoErro as exc:
        # Motivo vazio ou nota não efetivada: mensagem na tela, nada gravado.
        messages.error(request, exc.mensagem)
        return _tela_de_data_pagamento(request, empresa, escrituracao, motivo=motivo, status=200)

    if limpa.criada_agora:
        messages.success(
            request,
            "Data de pagamento limpa. O IRRF e a CSRF desta nota voltaram para 'pendente de data "
            "de pagamento'.",
        )
    else:
        messages.info(request, "Esta nota já não tinha data de pagamento. Nada foi alterado.")
    return redirect(
        "fiscal_web:tomada_data_pagamento",
        empresa_id=empresa.pk,
        escrituracao_id=escrituracao.pk,
    )


@login_required
@require_http_methods(["POST"])
def tomada_data_pagamento_limpar(request, empresa_id, escrituracao_id):
    """POST — limpa a data de pagamento (HI-96). Só na tela de data de pagamento; sem GET."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao_de_escriturar(request)
    empresa = _empresa_escopada(request, empresa_id)
    escrituracao = _escrituracao_tomada_da_empresa(request, empresa, escrituracao_id)
    return _limpar_data_pagamento_post(request, empresa, escrituracao)


# ---------------------------------------------------------------------------
# Telas de totais: ISS retido a recolher (HI-94) e retenções federais (HI-95, HI-96)
# ---------------------------------------------------------------------------


def _nota_tomada_na_tela(escrituracao):
    documento = escrituracao.vinculo.documento
    return {
        "numero": _numero_da_nota(documento),
        "competencia": (
            escrituracao.data_competencia.strftime("%m/%Y")
            if escrituracao.data_competencia
            else "—"
        ),
        "emissao": _data_na_tela(escrituracao.data_emissao) or "—",
        "prestador": _tomador_texto(documento.prestador_nome, documento.prestador_documento),
        "natureza": escrituracao.get_natureza_display(),
        "valor_servico": _valor_ptbr(escrituracao.valor_servico),
        "iss": _valor_ptbr(escrituracao.v_iss_qn),
        "inss": _valor_ptbr(escrituracao.v_ret_cp),
        "irrf": _valor_ptbr(escrituracao.v_ret_irrf),
        "csrf": _valor_ptbr(escrituracao.v_ret_csll),
        "pagamento": _data_na_tela(escrituracao.data_pagamento) or "—",
    }


def _aviso_tomada_na_tela(escrituracao, aviso):
    return {
        "nota": _numero_da_nota(escrituracao.vinculo.documento),
        "codigo": aviso.codigo,
        "texto": aviso.texto,
        "fundamento": aviso.fundamento,
    }


def _grupo_do_retido_na_tela(grupo, nomes):
    return {
        "municipio": _rotulo_do_municipio(grupo.municipio, nomes),
        "total": _dinheiro_ptbr(grupo.total),
        "notas": [_nota_tomada_na_tela(e) for e in grupo.notas],
        "sem_valor": [_nota_tomada_na_tela(e) for e in grupo.sem_valor],
        "vencimento": grupo.vencimento_texto,
        "regra_dia_nao_util": grupo.regra_dia_nao_util,
    }


def _recusa_de_consulta_das_tomadas(request):
    """Resposta de recusa das telas de consulta de tomadas (sem escritório ou sem permissão)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DAS_TOMADAS)
    return None


@login_required
@require_safe
def iss_retido_a_recolher(request):
    """ISS retido a recolher pelo tomador, por município, no mês de dCompet (HI-94). Consulta."""
    resposta = _recusa_de_consulta_das_tomadas(request)
    if resposta is not None:
        return resposta

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        "mostrar_ano": True,
        "mostrar_mes": True,
        "pode_escriturar": _pode_escriturar(request),
        "texto_de_conferencia": _TEXTO_DE_CONFERENCIA_DO_RETIDO,
        "titulo": "ISS retido a recolher",
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/iss_retido_a_recolher.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/iss_retido_a_recolher.html", contexto)

    ano, mes = competencia
    resultado = servico_retencoes.iss_retido_a_recolher(empresa, ano, mes)
    nomes = _nomes_dos_municipios([g.municipio for g in resultado.grupos])
    contexto.update(
        mes_rotulo=_mes_por_extenso(ano, mes),
        grupos=[_grupo_do_retido_na_tela(g, nomes) for g in resultado.grupos],
        fora_do_total=[_nota_tomada_na_tela(e) for e in resultado.fora_do_total],
        canceladas=[_nota_tomada_na_tela(e) for e in resultado.canceladas],
        avisos=[_aviso_tomada_na_tela(e, a) for e, a in resultado.avisos],
        url_escriturar=_url_com_filtro("fiscal_web:tomadas_lista", empresa, ano=ano, mes=mes),
        url_retencoes=_url_com_filtro("fiscal_web:retencoes_federais", empresa, ano=ano, mes=mes),
    )
    return render(request, "fiscal/iss_retido_a_recolher.html", contexto)


def _pendente_na_tela(escrituracao, empresa, pode_escriturar):
    linha = _nota_tomada_na_tela(escrituracao)
    linha["url_pagamento"] = (
        reverse("fiscal_web:tomada_data_pagamento", args=[empresa.pk, escrituracao.pk])
        if pode_escriturar
        else ""
    )
    return linha


def _pagamentos_na_tela(grupos):
    return [
        {
            "data": _data_na_tela(grupo.data_pagamento),
            "total": _dinheiro_ptbr(grupo.total),
            "quantidade": len(grupo.notas),
            "notas": ", ".join(_numero_da_nota(e.vinculo.documento) for e in grupo.notas),
        }
        for grupo in grupos
    ]


@login_required
@require_safe
def retencoes_federais(request):
    """Retenções federais destacadas: CSRF, IRRF e INSS, cada uma com a sua competência (HI-95,
    HI-96). Só lê o que a nota destaca; não recalcula nem decide se a retenção era devida."""
    resposta = _recusa_de_consulta_das_tomadas(request)
    if resposta is not None:
        return resposta

    empresa, competencia, erro = _filtros_de_escrituracao(request)
    pode_escriturar = _pode_escriturar(request)
    contexto = {
        **_contexto_do_filtro_de_empresa(request, empresa, competencia),
        "mostrar_ano": True,
        "mostrar_mes": True,
        "pode_escriturar": pode_escriturar,
        "texto_de_conferencia": _TEXTO_DE_CONFERENCIA_DAS_RETENCOES,
        "titulo": "Retenções federais",
    }
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/retencoes_federais.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/retencoes_federais.html", contexto)

    ano, mes = competencia
    resultado = servico_retencoes.retencoes_federais(empresa, ano, mes)
    contexto.update(
        mes_rotulo=_mes_por_extenso(ano, mes),
        csrf_total=_dinheiro_ptbr(resultado.csrf_total),
        irrf_total=_dinheiro_ptbr(resultado.irrf_total),
        inss_total=_dinheiro_ptbr(resultado.inss_total),
        inss_vencimento_texto=resultado.inss_vencimento_texto,
        csrf_pagamentos=_pagamentos_na_tela(resultado.csrf_por_pagamento),
        irrf_pagamentos=_pagamentos_na_tela(resultado.irrf_por_pagamento),
        inss_notas=[_nota_tomada_na_tela(e) for e in resultado.inss_notas],
        pendentes=[
            _pendente_na_tela(e, empresa, pode_escriturar) for e in resultado.pendentes_de_pagamento
        ],
        canceladas=[_nota_tomada_na_tela(e) for e in resultado.canceladas],
        avisos=[_aviso_tomada_na_tela(e, a) for e, a in resultado.avisos],
        url_retido=_url_com_filtro("fiscal_web:iss_retido_a_recolher", empresa, ano=ano, mes=mes),
    )
    return render(request, "fiscal/retencoes_federais.html", contexto)


# ---------------------------------------------------------------------------
# Lucro Presumido, IRPJ e CSLL (DL-079, frente B: telas)
#
# Telas sobre `apps.fiscal.presumido` (frente A). A tela NÃO calcula: lê o que o serviço devolve e
# formata em pt-BR. Autorização no servidor: consulta (GET) exige `papel_pode_consultar_documentos`;
# cadastro, confirmação, estorno e revogação exigem `papel_pode_escriturar_fiscal`. Empresa de OUTRO
# escritório é 404; ato de OUTRA empresa do mesmo escritório também é 404, porque a busca é feita
# dentro da empresa. Entrada inválida volta com a mensagem e não grava nada.
# ---------------------------------------------------------------------------

_MENSAGEM_SEM_CONSULTA_DO_PRESUMIDO = "Seu papel não permite consultar o Lucro Presumido."
_MENSAGEM_SEM_ESCRITA_DO_PRESUMIDO = (
    "Seu papel consulta o Lucro Presumido, mas não cadastra, confirma, estorna nem revoga. "
    "Peça a um administrador ou gestor do escritório."
)
# Texto fixo de conferência (personalizacao-de-relatorio.md, classe 1): NÃO é guia nem DARF.
_TEXTO_CONFERENCIA_PRESUMIDO = "Conferência — não é guia nem DARF."
_TEXTO_CASO_QUARTO = {
    calc_presumido.CASO_I: (
        "Caso I: excedente anual zero. Recalcula sem acréscimo e deduz a diferença no 4º trimestre."
    ),
    calc_presumido.CASO_II: (
        "Caso II: excedente anual menor que a soma dos excedentes dos trimestres anteriores. "
        "Recalcula com o excedente rateado e deduz a diferença no 4º trimestre."
    ),
    calc_presumido.CASO_III: (
        "Caso III: excedente anual igual ou maior que a soma dos anteriores. Mantém a sobra; "
        "não há dedução."
    ),
}
_TRIBUTO_PRESUMIDO_ROTULO = {
    tab_presumido.IRPJ: "IRPJ",
    tab_presumido.CSLL: "CSLL",
    tab_presumido.AMBOS: "IRPJ e CSLL",
}
_ROTULO_TIPO_RECEITA = {
    "presuncao": "Receita de presunção",
    "integral": "Receita integral (art. 25, II)",
}
_ROTULO_CRITERIO_PRESUMIDO = {
    "competencia": "Competência",
    "caixa": "Caixa",
}
_RECUSA_CAIXA_PRESUMIDO = (
    "Critério de caixa: o Lucro Presumido não é apurado neste produto "
    "(IN RFB 1.700/2017, art. 223, §§ 1º a 4º). A apuração do ano sai recusada, com este "
    "motivo, e nenhum número de imposto é mostrado."
)
_PARCELA_SUSPENSA_TEXTO = "parcela suspensa por medida judicial — fora da dedução"
ZERO_PRESUMIDO = Decimal("0.00")


def _contrato_presumido(campos, contexto):
    """Campos aceitos num POST do presumido. O token do CSRF é sempre aceito; qualquer outro campo
    fora da lista é recusado com a mensagem nomeada (apps.core.requisicao)."""
    return ContratoDeRequisicao(
        campos={"csrfmiddlewaretoken", *campos},
        cabecalhos_ignorados=(),
        contexto=contexto,
    )


_CONTRATO_PRESUMIDO_ATIVIDADE = _contrato_presumido(
    {"atividade", "inicio", "padrao", "requisitos_hospitalares_confirmados", "fim"},
    "no cadastro da atividade de presunção",
)
_CONTRATO_PRESUMIDO_ENCERRAR = _contrato_presumido({"fim"}, "no encerramento da atividade")
_CONTRATO_PRESUMIDO_CRITERIO = _contrato_presumido({"ano", "criterio"}, "na definição do critério")
_CONTRATO_PRESUMIDO_RECEITA = _contrato_presumido(
    {"ano", "trimestre", "tipo", "atividade_id", "valor", "descricao", "suporte"},
    "no lançamento da receita do trimestre",
)
_CONTRATO_PRESUMIDO_MOTIVO = _contrato_presumido({"motivo"}, "no motivo da ação")
_CONTRATO_PRESUMIDO_INTEGRAIS = _contrato_presumido(
    {"ano", "trimestre", "observacao", "modo"}, "na declaração de receitas integrais"
)
_CONTRATO_PRESUMIDO_RETENCAO = _contrato_presumido(
    {"ano", "trimestre", "irrf_confirmado", "csll_confirmada", "motivo"},
    "na confirmação da retenção",
)
_CONTRATO_PRESUMIDO_MEDIDA = _contrato_presumido(
    {
        "tributo",
        "ano_inicial",
        "trimestre_inicial",
        "ano_final",
        "trimestre_final",
        "numero_processo",
        "orgao",
        "data_decisao",
        "deposito_judicial",
        "suporte",
    },
    "no cadastro da medida judicial",
)


def _pres_recusa_de_consulta(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_DO_PRESUMIDO)
    return None


def _pres_recusa_de_escrita(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_ESCRITA_DO_PRESUMIDO)
    return None


def _pres_percentual(fracao) -> str:
    """Fração do catálogo em percentual pt-BR, sem zeros à direita: 0,088 vira '8,8%'.

    Só apresentação: a fração chega e sai como `Decimal`, e nenhuma conta passa por aqui.
    """
    if fracao is None:
        return "—"
    return format((Decimal(fracao) * 100).normalize(), "f").replace(".", ",") + "%"


def _pres_trimestre(ano: int, trimestre: int) -> str:
    return f"{trimestre}º trimestre de {ano}"


def _pres_periodo_padrao(request):
    """(ano, trimestre, erro) da consulta. Ausente: o trimestre corrente (Brasília). Malformado ou
    fora do presumido: erro de formulário na tela, nunca 500 e nunca um número de outro período."""
    ano_bruto = request.GET.get("ano", "").strip()
    tri_bruto = request.GET.get("trimestre", "").strip()
    if not ano_bruto and not tri_bruto:
        hoje = timezone.localdate()
        return hoje.year, (hoje.month - 1) // 3 + 1, None
    ano = _inteiro_de_filtro(ano_bruto)
    trimestre = _inteiro_de_filtro(tri_bruto)
    if ano is None or trimestre is None:
        return None, None, "Informe o ano (AAAA) e o trimestre (1 a 4)."
    try:
        servico_presumido.validar_ano_e_trimestre(ano, trimestre)
    except servico_presumido.EntradaInvalidaPresumido as exc:
        return None, None, exc.mensagem
    return ano, trimestre, None


def _pres_ano_padrao(request):
    """(ano, erro) das telas que só pedem o ano (critério do ano, limite do ano)."""
    bruto = request.GET.get("ano", "").strip()
    if not bruto:
        return timezone.localdate().year, None
    ano = _inteiro_de_filtro(bruto)
    if ano is None:
        return None, "Informe o ano (AAAA)."
    try:
        servico_presumido.validar_ano_e_trimestre(ano, 1)
    except servico_presumido.EntradaInvalidaPresumido as exc:
        return None, exc.mensagem
    return ano, None


def _pres_contexto(request, empresa, *, pode_escriturar, titulo, **extra):
    """Contexto comum: a empresa escolhida (ou a escolha, sem empresa), o aviso das ADIs e o
    texto de conferência. Nenhum dado de outra empresa entra aqui (a escolha só aparece sem
    empresa)."""
    return {
        "titulo": titulo,
        "empresa_selecionada": empresa,
        "empresas_do_escritorio": (
            None
            if empresa is not None
            else Empresa.objects.filter(escritorio=request.escritorio).order_by("razao_social")
        ),
        "url_trocar_empresa": reverse("empresas:lista"),
        "pode_escriturar": pode_escriturar,
        "texto_conferencia": _TEXTO_CONFERENCIA_PRESUMIDO,
        "aviso_adi": tab_presumido.AVISO_ADI,
        "data_conferencia_adi": _data_na_tela(tab_presumido.DATA_CONFERENCIA_ADI),
        **extra,
    }


def _pres_url_consulta(nome, empresa, **consulta):
    """URL de uma tela de consulta, com a empresa e os filtros na querystring."""
    return reverse(nome) + "?" + urlencode({"empresa": empresa.pk, **consulta})


# ---------------------------------------------------------------------------
# Atividades de presunção (tela 1)
# ---------------------------------------------------------------------------


def _pres_linha_da_atividade(atividade, empresa, pode_escriturar) -> dict:
    definicao = tab_presumido.ATIVIDADES_POR_CODIGO[atividade.atividade]
    encerrar = None
    if pode_escriturar and atividade.fim is None:
        encerrar = reverse(
            "fiscal_web:presumido_atividade_encerrar", args=[empresa.pk, atividade.pk]
        )
    return {
        "rotulo": definicao.rotulo,
        "irpj": _pres_percentual(definicao.irpj),
        "csll": _pres_percentual(definicao.csll),
        "inicio": _data_na_tela(atividade.inicio),
        "fim": _data_na_tela(atividade.fim) or "em aberto",
        "padrao": "Sim" if atividade.padrao else "Não",
        "requisitos": (
            "Requisitos hospitalares confirmados"
            if atividade.requisitos_hospitalares_confirmados
            else ""
        ),
        "url_encerrar": encerrar,
    }


def _pres_catalogo_na_tela() -> list[dict]:
    return [
        {
            "rotulo": item.rotulo,
            "irpj": _pres_percentual(item.irpj),
            "csll": _pres_percentual(item.csll),
            "observacao": item.observacao,
        }
        for item in tab_presumido.CATALOGO_ATIVIDADES
    ]


@login_required
@require_safe
def presumido_atividades(request):
    """Atividades de presunção da empresa, com percentuais de IRPJ e CSLL e vigência. Consulta."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    pode = _pode_escriturar(request)
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=pode,
        titulo="Atividades de presunção",
        catalogo=_pres_catalogo_na_tela(),
        # A10: a ESC (38,4%) fica fora do catálogo; é nomeada aqui para não ser lida como serviços.
        fora_do_corte=tab_presumido.ESC_FORA_DO_PRIMEIRO_CORTE,
    )
    if erro:
        messages.error(request, erro)
        return render(request, "fiscal/presumido_atividades.html", contexto, status=400)
    if empresa is None:
        return render(request, "fiscal/presumido_atividades.html", contexto)
    contexto.update(
        atividades=[
            _pres_linha_da_atividade(a, empresa, pode)
            for a in servico_presumido.listar_atividades(empresa)
        ],
        url_nova=reverse("fiscal_web:presumido_atividade_nova", args=[empresa.pk]),
    )
    return render(request, "fiscal/presumido_atividades.html", contexto)


def _pres_valores_atividade(valores=None) -> dict:
    if valores is not None:
        return valores
    return {"atividade": "", "inicio": "", "fim": "", "padrao": False, "requisitos": False}


def _pres_tela_atividade(request, empresa, *, valores, erro=None, status=200):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Nova atividade de presunção",
        valores=valores,
        erro=erro,
        catalogo=_pres_catalogo_na_tela(),
        opcoes_atividade=[(c.codigo, c.rotulo) for c in tab_presumido.CATALOGO_ATIVIDADES],
        url_envio=reverse("fiscal_web:presumido_atividade_nova", args=[empresa.pk]),
        url_voltar=_pres_url_consulta("fiscal_web:presumido_atividades", empresa),
    )
    return render(request, "fiscal/presumido_atividade_form.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def presumido_atividade_nova(request, empresa_id):
    """Cadastra uma atividade de presunção com vigência. Serviço hospitalar exige os requisitos."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _pres_tela_atividade(request, empresa, valores=_pres_valores_atividade())
    valores = {
        "atividade": request.POST.get("atividade", ""),
        "inicio": request.POST.get("inicio", ""),
        "fim": request.POST.get("fim", ""),
        "padrao": request.POST.get("padrao", "") == "1",
        "requisitos": request.POST.get("requisitos_hospitalares_confirmados", "") == "1",
    }
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_ATIVIDADE)
    except DadoNaoContratado as exc:
        return _pres_tela_atividade(
            request, empresa, valores=valores, erro=exc.mensagem, status=400
        )
    inicio = _data_do_formulario(valores["inicio"])
    if inicio is None:
        return _pres_tela_atividade(
            request,
            empresa,
            valores=valores,
            erro="Informe o início da vigência em dd/mm/aaaa.",
            status=400,
        )
    fim = None
    if valores["fim"].strip():
        fim = _data_do_formulario(valores["fim"])
        if fim is None:
            return _pres_tela_atividade(
                request,
                empresa,
                valores=valores,
                erro="O fim da vigência é uma data inválida: use dd/mm/aaaa, ou deixe em branco.",
                status=400,
            )
    dados = {
        "atividade": valores["atividade"],
        "inicio": inicio,
        "fim": fim,
        "padrao": valores["padrao"],
        "requisitos_hospitalares_confirmados": valores["requisitos"],
    }
    try:
        servico_presumido.criar_atividade(empresa, dados, request.user, request)
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_atividade(
            request, empresa, valores=valores, erro=exc.mensagem, status=status
        )
    messages.success(request, "Atividade de presunção cadastrada.")
    return redirect(_pres_url_consulta("fiscal_web:presumido_atividades", empresa))


def _pres_tela_encerrar(request, empresa, atividade, *, fim_digitado="", erro=None, status=200):
    definicao = tab_presumido.ATIVIDADES_POR_CODIGO[atividade.atividade]
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Encerrar atividade de presunção",
        atividade={
            "rotulo": definicao.rotulo,
            "inicio": _data_na_tela(atividade.inicio),
            "fim": _data_na_tela(atividade.fim),
        },
        ja_encerrada=atividade.fim is not None,
        fim_digitado=fim_digitado,
        erro=erro,
        url_envio=reverse(
            "fiscal_web:presumido_atividade_encerrar", args=[empresa.pk, atividade.pk]
        ),
        url_voltar=_pres_url_consulta("fiscal_web:presumido_atividades", empresa),
    )
    return render(request, "fiscal/presumido_atividade_encerrar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def presumido_atividade_encerrar(request, empresa_id, atividade_id):
    """Encerra a vigência de uma atividade em aberto. A linha continua na trilha; nada é apagado."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    atividade = get_object_or_404(AtividadePresuncaoEmpresa, pk=atividade_id, empresa=empresa)
    if request.method == "GET":
        return _pres_tela_encerrar(request, empresa, atividade)
    fim_bruto = request.POST.get("fim", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_ENCERRAR)
    except DadoNaoContratado as exc:
        return _pres_tela_encerrar(
            request, empresa, atividade, fim_digitado=fim_bruto, erro=exc.mensagem, status=400
        )
    fim = _data_do_formulario(fim_bruto)
    if fim is None:
        return _pres_tela_encerrar(
            request,
            empresa,
            atividade,
            fim_digitado=fim_bruto,
            erro="Informe o fim da vigência em dd/mm/aaaa.",
            status=400,
        )
    try:
        servico_presumido.encerrar_atividade(empresa, atividade.pk, fim, request.user, request)
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_encerrar(
            request, empresa, atividade, fim_digitado=fim_bruto, erro=exc.mensagem, status=status
        )
    messages.success(request, f"Atividade encerrada em {_data_na_tela(fim)}.")
    return redirect(_pres_url_consulta("fiscal_web:presumido_atividades", empresa))


# ---------------------------------------------------------------------------
# Critério do ano (tela 2)
# ---------------------------------------------------------------------------


def _pres_tela_criterio(request, empresa, *, ano, erro=None, status=200):
    criterio = servico_presumido.criterio_do_ano(empresa, ano)
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=_pode_escriturar(request),
        titulo="Critério de receita do ano",
        ano_filtro=ano,
        erro=erro,
        criterio=criterio,
        criterio_rotulo=_ROTULO_CRITERIO_PRESUMIDO.get(criterio, "não informado"),
        recusa_caixa=_RECUSA_CAIXA_PRESUMIDO if criterio == "caixa" else "",
        opcoes_criterio=[("competencia", "Competência"), ("caixa", "Caixa")],
        url_gravar=reverse("fiscal_web:presumido_criterio_gravar", args=[empresa.pk]),
        url_consulta=_pres_url_consulta("fiscal_web:presumido_criterio", empresa, ano=ano),
    )
    return render(request, "fiscal/presumido_criterio.html", contexto, status=status)


@login_required
@require_safe
def presumido_criterio(request):
    """Critério do ano (competência ou caixa). Caixa mostra a recusa nomeada. Consulta."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    ano, erro_ano = _pres_ano_padrao(request)
    erro = erro or erro_ano
    if erro:
        contexto = _pres_contexto(
            request,
            empresa,
            pode_escriturar=_pode_escriturar(request),
            titulo="Critério de receita",
            erro=erro,
        )
        return render(request, "fiscal/presumido_criterio.html", contexto, status=400)
    if empresa is None:
        contexto = _pres_contexto(
            request,
            empresa,
            pode_escriturar=_pode_escriturar(request),
            titulo="Critério de receita",
        )
        return render(request, "fiscal/presumido_criterio.html", contexto)
    return _pres_tela_criterio(request, empresa, ano=ano)


@login_required
@require_http_methods(["POST"])
def presumido_criterio_gravar(request, empresa_id):
    """Define o critério do ano. Trocar um critério já definido é conflito, e nada muda."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_CRITERIO)
    except DadoNaoContratado as exc:
        return _pres_tela_criterio(
            request, empresa, ano=timezone.localdate().year, erro=exc.mensagem, status=400
        )
    ano = _inteiro_de_filtro(request.POST.get("ano", "").strip())
    if ano is None:
        return _pres_tela_criterio(
            request,
            empresa,
            ano=timezone.localdate().year,
            erro="Informe o ano (AAAA) do critério.",
            status=400,
        )
    try:
        servico_presumido.definir_criterio(
            empresa, ano, request.POST.get("criterio", ""), request.user, request
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_criterio(request, empresa, ano=ano, erro=exc.mensagem, status=status)
    messages.success(request, f"Critério de {ano} gravado.")
    return redirect(_pres_url_consulta("fiscal_web:presumido_criterio", empresa, ano=ano))


# ---------------------------------------------------------------------------
# Receitas do trimestre e declaração de receitas integrais (tela 3)
# ---------------------------------------------------------------------------


def _pres_linha_da_receita(receita, empresa, pode_escriturar) -> dict:
    ativa = receita.estado == "ativa"
    presuncao = receita.tipo == "presuncao"
    return {
        "tipo": _ROTULO_TIPO_RECEITA.get(receita.tipo, receita.tipo),
        "atividade": (
            tab_presumido.ATIVIDADES_POR_CODIGO[receita.atividade.atividade].rotulo
            if presuncao and receita.atividade_id
            else "—"
        ),
        "descricao": receita.descricao,
        "valor": _valor_ptbr(receita.valor),
        "suporte": receita.suporte,
        "estado": "Ativa" if ativa else "Estornada",
        "motivo_estorno": receita.motivo_estorno,
        "url_estornar": (
            reverse("fiscal_web:presumido_receita_estornar", args=[empresa.pk, receita.pk])
            if ativa and pode_escriturar
            else None
        ),
    }


def _pres_declaracao_na_tela(apuracao) -> dict:
    """Se a declaração de integrais do trimestre vale, ou caiu porque o total mudou (HI-104)."""
    if apuracao.declaracao_total is None:
        return {
            "situacao": "nenhuma",
            "texto": (
                "Nenhuma declaração de receitas integrais neste trimestre. A apuração sai parcial."
            ),
        }
    if apuracao.declaracao_valida:
        return {
            "situacao": "vale",
            "texto": (
                f"A declaração vale: o total declarado ({_valor_ptbr(apuracao.declaracao_total)}) "
                "é o total atual das receitas integrais."
            ),
        }
    return {
        "situacao": "caiu",
        "texto": (
            "A declaração caiu porque o total mudou: declarado "
            f"{_valor_ptbr(apuracao.declaracao_total)}, "
            f"atual {_valor_ptbr(apuracao.integrais_atuais)}. "
            "Declare de novo para a apuração sair completa."
        ),
    }


def _pres_valores_receita(valores=None) -> dict:
    if valores is not None:
        return valores
    return {"tipo": "presuncao", "atividade_id": "", "valor": "", "descricao": "", "suporte": ""}


def _pres_tela_receitas(request, empresa, ano, trimestre, *, status=200, erro=None, valores=None):
    apuracao = servico_presumido.apurar_trimestre(empresa, ano, trimestre)
    pode = _pode_escriturar(request)
    atividades = [
        {
            "id": a.pk,
            "rotulo": f"{tab_presumido.ATIVIDADES_POR_CODIGO[a.atividade].rotulo} "
            f"(desde {_data_na_tela(a.inicio)})",
        }
        for a in servico_presumido.listar_atividades(empresa)
    ]
    integrais_nenhuma = apuracao.integrais_atuais == ZERO_PRESUMIDO
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=pode,
        titulo="Receitas do trimestre",
        ano_filtro=ano,
        trimestre_filtro=trimestre,
        trimestre_rotulo=_pres_trimestre(ano, trimestre),
        erro=erro,
        valores=_pres_valores_receita(valores),
        receitas=[
            _pres_linha_da_receita(r, empresa, pode)
            for r in servico_presumido.listar_receitas(empresa, ano, trimestre)
        ],
        atividades=atividades,
        declaracao=_pres_declaracao_na_tela(apuracao),
        integrais_atuais=_valor_ptbr(apuracao.integrais_atuais),
        integrais_nenhuma=integrais_nenhuma,
        motivo_sem_integrais=(
            ""
            if integrais_nenhuma
            else "Há receitas integrais lançadas neste trimestre: declare o total, não 'não houve'."
        ),
        opcoes_tipo=[
            ("presuncao", "Receita de presunção"),
            ("integral", "Receita integral (art. 25, II)"),
        ],
        url_receita=reverse("fiscal_web:presumido_receita_nova", args=[empresa.pk]),
        url_integrais=reverse("fiscal_web:presumido_integrais_declarar", args=[empresa.pk]),
        url_consulta=_pres_url_consulta(
            "fiscal_web:presumido_receitas", empresa, ano=ano, trimestre=trimestre
        ),
    )
    return render(request, "fiscal/presumido_receitas.html", contexto, status=status)


@login_required
@require_safe
def presumido_receitas(request):
    """Receitas do trimestre (presunção e integrais), com a declaração de integrais. Consulta."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    ano, trimestre, erro_periodo = _pres_periodo_padrao(request)
    erro = erro or erro_periodo
    if erro or empresa is None:
        contexto = _pres_contexto(
            request,
            empresa,
            pode_escriturar=_pode_escriturar(request),
            titulo="Receitas do trimestre",
            erro=erro,
        )
        return render(
            request, "fiscal/presumido_receitas.html", contexto, status=400 if erro else 200
        )
    return _pres_tela_receitas(request, empresa, ano, trimestre)


def _pres_valor_do_formulario(bruto: str) -> str:
    """Valor em pt-BR digitado ('1.234,56'). Formato ruim vira mensagem; nunca float."""
    try:
        return _valor_do_formulario(bruto)
    except ValorInvalidoNoFormulario as exc:
        raise servico_presumido.EntradaInvalidaPresumido(str(exc)) from exc


@login_required
@require_http_methods(["POST"])
def presumido_receita_nova(request, empresa_id):
    """Lança receita de presunção (com atividade) ou integral (sem atividade), com suporte."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    ano = _inteiro_de_filtro(request.POST.get("ano", "").strip())
    trimestre = _inteiro_de_filtro(request.POST.get("trimestre", "").strip())
    valores = {
        "tipo": request.POST.get("tipo", ""),
        "atividade_id": request.POST.get("atividade_id", ""),
        "valor": request.POST.get("valor", ""),
        "descricao": request.POST.get("descricao", ""),
        "suporte": request.POST.get("suporte", ""),
    }
    if ano is None or trimestre is None:
        return _pres_tela_receitas_sem_periodo(request, empresa, "Informe o ano e o trimestre.")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_RECEITA)
        dados = {
            "tipo": valores["tipo"],
            "valor": _pres_valor_do_formulario(valores["valor"]),
            "descricao": valores["descricao"],
            "suporte": valores["suporte"],
        }
        if valores["tipo"] == servico_presumido.TIPO_PRESUNCAO:
            dados["atividade_id"] = _inteiro_de_filtro(valores["atividade_id"].strip())
        servico_presumido.criar_receita(empresa, ano, trimestre, dados, request.user, request)
    except DadoNaoContratado as exc:
        return _pres_tela_receitas(
            request, empresa, ano, trimestre, status=400, erro=exc.mensagem, valores=valores
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_receitas(
            request, empresa, ano, trimestre, status=status, erro=exc.mensagem, valores=valores
        )
    messages.success(request, "Receita lançada no trimestre.")
    return redirect(
        _pres_url_consulta("fiscal_web:presumido_receitas", empresa, ano=ano, trimestre=trimestre)
    )


def _pres_tela_receitas_sem_periodo(request, empresa, erro):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=_pode_escriturar(request),
        titulo="Receitas do trimestre",
        erro=erro,
    )
    return render(request, "fiscal/presumido_receitas.html", contexto, status=400)


@login_required
@require_http_methods(["POST"])
def presumido_integrais_declarar(request, empresa_id):
    """Declara as receitas integrais pelo total atual, ou "não houve" com total zero."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    ano = _inteiro_de_filtro(request.POST.get("ano", "").strip())
    trimestre = _inteiro_de_filtro(request.POST.get("trimestre", "").strip())
    if ano is None or trimestre is None:
        return _pres_tela_receitas_sem_periodo(request, empresa, "Informe o ano e o trimestre.")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_INTEGRAIS)
        if request.POST.get("modo") == "sem_integrais":
            servico_presumido.declarar_sem_receitas_integrais(
                empresa, ano, trimestre, request.user, request
            )
        else:
            servico_presumido.declarar_receitas_integrais(
                empresa, ano, trimestre, request.POST.get("observacao", ""), request.user, request
            )
    except DadoNaoContratado as exc:
        return _pres_tela_receitas(request, empresa, ano, trimestre, status=400, erro=exc.mensagem)
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_receitas(
            request, empresa, ano, trimestre, status=status, erro=exc.mensagem
        )
    messages.success(request, "Receitas integrais do trimestre declaradas.")
    return redirect(
        _pres_url_consulta("fiscal_web:presumido_receitas", empresa, ano=ano, trimestre=trimestre)
    )


def _pres_tela_estornar_receita(request, empresa, receita, *, motivo="", erro=None, status=200):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Estornar receita do trimestre",
        receita=_pres_linha_da_receita(receita, empresa, False),
        motivo=motivo,
        erro=erro,
        url_envio=reverse("fiscal_web:presumido_receita_estornar", args=[empresa.pk, receita.pk]),
        url_voltar=_pres_url_consulta(
            "fiscal_web:presumido_receitas", empresa, ano=receita.ano, trimestre=receita.trimestre
        ),
    )
    return render(request, "fiscal/presumido_receita_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def presumido_receita_estornar(request, empresa_id, receita_id):
    """Estorna uma receita com motivo obrigatório. Fica na trilha, marcada como estornada."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    receita = get_object_or_404(ReceitaTrimestralPresumido, pk=receita_id, empresa=empresa)
    if request.method == "GET":
        return _pres_tela_estornar_receita(request, empresa, receita)
    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_MOTIVO)
        servico_presumido.estornar_receita(empresa, receita.pk, motivo, request.user, request)
    except DadoNaoContratado as exc:
        return _pres_tela_estornar_receita(
            request, empresa, receita, motivo=motivo, erro=exc.mensagem, status=400
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_estornar_receita(
            request, empresa, receita, motivo=motivo, erro=exc.mensagem, status=status
        )
    messages.success(request, "Receita estornada.")
    return redirect(
        _pres_url_consulta(
            "fiscal_web:presumido_receitas", empresa, ano=receita.ano, trimestre=receita.trimestre
        )
    )


# ---------------------------------------------------------------------------
# Retenções do trimestre (tela 4)
# ---------------------------------------------------------------------------


def _pres_csll_na_tela(linha) -> str:
    """CSLL proposta com a marca da regra: exata, estimada ou a classificar (HI-102, HI-103)."""
    if linha.csll_situacao == "exata":
        return f"{_valor_ptbr(linha.csll_proposta)} (exata, tpRetPisCofins 8)"
    if linha.csll_situacao == "estimada":
        return f"{_valor_ptbr(linha.csll_proposta)} — estimada — conferir no comprovante"
    return f"a classificar: {linha.csll_motivo}"


def _pres_linha_da_retencao(linha, empresa, ano, trimestre, pode_escriturar) -> dict:
    return {
        "numero": linha.numero,
        "competencia": _data_na_tela(linha.data_competencia),
        "valor": _valor_ptbr(linha.valor_servico),
        "irrf_proposto": _valor_ptbr(linha.irrf_proposto),
        "csll_proposta": _pres_csll_na_tela(linha),
        "irrf_confirmado": (
            _valor_ptbr(linha.irrf_confirmado)
            if linha.irrf_confirmado is not None
            else "não confirmado"
        ),
        "csll_confirmada": (
            _valor_ptbr(linha.csll_confirmada)
            if linha.csll_confirmada is not None
            else "não confirmada"
        ),
        "url_confirmar": (
            reverse(
                "fiscal_web:presumido_retencao_confirmar",
                args=[empresa.pk, linha.escrituracao_id],
            )
            + "?"
            + urlencode({"ano": ano, "trimestre": trimestre})
            if pode_escriturar
            else None
        ),
    }


@login_required
@require_safe
def presumido_retencoes(request):
    """Retenções sofridas por nota do trimestre: proposta, marca e confirmação ativa. Consulta."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    ano, trimestre, erro_periodo = _pres_periodo_padrao(request)
    erro = erro or erro_periodo
    pode = _pode_escriturar(request)
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=pode,
        titulo="Retenções do trimestre",
        ano_filtro=ano,
        trimestre_filtro=trimestre,
        erro=erro,
    )
    if erro or empresa is None:
        return render(
            request, "fiscal/presumido_retencoes.html", contexto, status=400 if erro else 200
        )
    linhas = servico_presumido.retencoes_do_trimestre(empresa, ano, trimestre)
    contexto.update(
        trimestre_rotulo=_pres_trimestre(ano, trimestre),
        retencoes=[
            _pres_linha_da_retencao(linha, empresa, ano, trimestre, pode) for linha in linhas
        ],
        url_consulta=_pres_url_consulta(
            "fiscal_web:presumido_retencoes", empresa, ano=ano, trimestre=trimestre
        ),
    )
    return render(request, "fiscal/presumido_retencoes.html", contexto)


def _pres_tela_confirmar_retencao(
    request, empresa, ano, trimestre, linha, *, valores, motivo, erro=None, status=200
):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Confirmar retenção",
        ano_filtro=ano,
        trimestre_filtro=trimestre,
        trimestre_rotulo=_pres_trimestre(ano, trimestre),
        retencao=_pres_linha_da_retencao(linha, empresa, ano, trimestre, False),
        proposta_irrf=linha.irrf_proposto,
        proposta_csll=linha.csll_proposta,
        valores=valores,
        motivo=motivo,
        erro=erro,
        url_envio=reverse(
            "fiscal_web:presumido_retencao_confirmar", args=[empresa.pk, linha.escrituracao_id]
        ),
        url_voltar=_pres_url_consulta(
            "fiscal_web:presumido_retencoes", empresa, ano=ano, trimestre=trimestre
        ),
    )
    return render(request, "fiscal/presumido_retencao_confirmar.html", contexto, status=status)


def _pres_linha_da_nota_no_trimestre(empresa, escrituracao_id, ano, trimestre):
    """A linha de retenção da nota, dentro do trimestre pedido, ou None se a nota não está ali.

    Nota que não entra na apuração não tem linha: no POST quem recusa é o serviço, com a mesma
    mensagem da API (A12). No GET, sem linha não há o que confirmar, e a resposta é 404.
    """
    for linha in servico_presumido.retencoes_do_trimestre(empresa, ano, trimestre):
        if linha.escrituracao_id == escrituracao_id:
            return linha
    return None


def _pres_tela_retencoes_com_erro(request, empresa, ano, trimestre, erro, status):
    """Lista de retenções com a recusa da confirmação, para nota que não tem linha no trimestre."""
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Retenções do trimestre",
        ano_filtro=ano,
        trimestre_filtro=trimestre,
        trimestre_rotulo=_pres_trimestre(ano, trimestre),
        erro=erro,
        retencoes=[],
        url_consulta=_pres_url_consulta(
            "fiscal_web:presumido_retencoes", empresa, ano=ano, trimestre=trimestre
        ),
    )
    return render(request, "fiscal/presumido_retencoes.html", contexto, status=status)


def _pres_erro_da_retencao(request, empresa, ano, trimestre, linha, valores, motivo, erro, status):
    """Recusa da confirmação: volta ao formulário da nota, ou à lista se a nota não tem linha."""
    if linha is None:
        return _pres_tela_retencoes_com_erro(request, empresa, ano, trimestre, erro, status)
    return _pres_tela_confirmar_retencao(
        request,
        empresa,
        ano,
        trimestre,
        linha,
        valores=valores,
        motivo=motivo,
        erro=erro,
        status=status,
    )


@login_required
@require_http_methods(["GET", "POST"])
def presumido_retencao_confirmar(request, empresa_id, escrituracao_id):
    """Confirma o IRRF e a CSLL de UMA nota, com trilha. Valor diferente exige motivo."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    # GET lê o período da consulta; POST lê os campos ocultos do formulário. A URL de envio não leva
    # querystring: o contrato de requisição recusa parâmetro de URL em POST.
    if request.method == "GET":
        ano, trimestre, erro_periodo = _pres_periodo_padrao(request)
    else:
        ano = _inteiro_de_filtro(request.POST.get("ano", "").strip())
        trimestre = _inteiro_de_filtro(request.POST.get("trimestre", "").strip())
        erro_periodo = (
            None if ano is not None and trimestre is not None else "Informe o ano e o trimestre."
        )
        if erro_periodo is None:
            try:
                servico_presumido.validar_ano_e_trimestre(ano, trimestre)
            except servico_presumido.EntradaInvalidaPresumido as exc:
                erro_periodo = exc.mensagem
    if erro_periodo or ano is None:
        contexto = _pres_contexto(
            request,
            empresa,
            pode_escriturar=True,
            titulo="Retenções do trimestre",
            erro=erro_periodo or "Informe o ano e o trimestre.",
        )
        return render(request, "fiscal/presumido_retencoes.html", contexto, status=400)
    # A nota tem de ser DA empresa (404 para as outras, como nas demais rotas de ato). Se ela está
    # na lista do trimestre é outra questão: quem decide a recusa é o serviço (A12).
    get_object_or_404(EscrituracaoFiscal, pk=escrituracao_id, empresa=empresa)
    linha = _pres_linha_da_nota_no_trimestre(empresa, escrituracao_id, ano, trimestre)
    if request.method == "GET":
        if linha is None:
            raise Http404("Nota não encontrada nesta empresa e neste trimestre.")
        valores = {
            "irrf": "" if linha.irrf_proposto is None else _valor_ptbr(linha.irrf_proposto),
            "csll": "" if linha.csll_proposta is None else _valor_ptbr(linha.csll_proposta),
        }
        return _pres_tela_confirmar_retencao(
            request, empresa, ano, trimestre, linha, valores=valores, motivo=""
        )
    valores = {
        "irrf": request.POST.get("irrf_confirmado", ""),
        "csll": request.POST.get("csll_confirmada", ""),
    }
    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_RETENCAO)
        irrf = _pres_valor_do_formulario(valores["irrf"]) if valores["irrf"].strip() else None
        csll = _pres_valor_do_formulario(valores["csll"]) if valores["csll"].strip() else None
        servico_presumido.confirmar_retencao(
            empresa, escrituracao_id, irrf, csll, motivo, request.user, request
        )
    except DadoNaoContratado as exc:
        return _pres_erro_da_retencao(
            request, empresa, ano, trimestre, linha, valores, motivo, exc.mensagem, 400
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_erro_da_retencao(
            request, empresa, ano, trimestre, linha, valores, motivo, exc.mensagem, status
        )
    messages.success(request, "Retenção confirmada.")
    return redirect(
        _pres_url_consulta("fiscal_web:presumido_retencoes", empresa, ano=ano, trimestre=trimestre)
    )


# ---------------------------------------------------------------------------
# Medidas judiciais contra o acréscimo (tela 5)
# ---------------------------------------------------------------------------

_ROTULO_TRIBUTO_MEDIDA = {"irpj": "IRPJ", "csll": "CSLL", "ambos": "IRPJ e CSLL"}


def _pres_periodo_da_medida(medida) -> str:
    inicio = _pres_trimestre(medida.ano_inicial, medida.trimestre_inicial)
    if medida.ano_final is None:
        return f"A partir do {inicio}, sem prazo final"
    return f"Do {inicio} ao {_pres_trimestre(medida.ano_final, medida.trimestre_final)}"


def _pres_linha_da_medida(medida, empresa, pode_escriturar) -> dict:
    return {
        "tributo": _ROTULO_TRIBUTO_MEDIDA.get(medida.tributo, medida.tributo),
        "periodo": _pres_periodo_da_medida(medida),
        "processo": medida.numero_processo,
        "orgao": medida.orgao,
        "data_decisao": _data_na_tela(medida.data_decisao),
        "deposito": "Sim — depositar" if medida.deposito_judicial else "Não — suspensa",
        "suporte": medida.suporte,
        "situacao": "Ativa" if medida.ativa else f"Revogada: {medida.motivo_revogacao}",
        "url_revogar": (
            reverse("fiscal_web:presumido_medida_revogar", args=[empresa.pk, medida.pk])
            if medida.ativa and pode_escriturar
            else None
        ),
    }


def _pres_tela_medidas(request, empresa, *, status=200, erro=None):
    pode = _pode_escriturar(request)
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=pode,
        titulo="Medidas judiciais contra a LC 224",
        erro=erro,
        medidas=[
            _pres_linha_da_medida(m, empresa, pode)
            for m in servico_presumido.listar_medidas(empresa)
        ],
        url_nova=reverse("fiscal_web:presumido_medida_nova", args=[empresa.pk]),
        url_consulta=_pres_url_consulta("fiscal_web:presumido_medidas", empresa),
    )
    return render(request, "fiscal/presumido_medidas.html", contexto, status=status)


@login_required
@require_safe
def presumido_medidas(request):
    """Medidas judiciais da empresa, com o aviso fixo das ADIs. Consulta; o resto é à parte."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    if erro:
        return render(
            request,
            "fiscal/presumido_medidas.html",
            _pres_contexto(
                request,
                empresa,
                pode_escriturar=_pode_escriturar(request),
                titulo="Medidas judiciais contra a LC 224",
                erro=erro,
            ),
            status=400,
        )
    if empresa is None:
        return render(
            request,
            "fiscal/presumido_medidas.html",
            _pres_contexto(
                request,
                empresa,
                pode_escriturar=_pode_escriturar(request),
                titulo="Medidas judiciais contra a LC 224",
            ),
        )
    return _pres_tela_medidas(request, empresa)


def _pres_valores_medida(valores=None) -> dict:
    if valores is not None:
        return valores
    return {
        "tributo": "irpj",
        "ano_inicial": "",
        "trimestre_inicial": "",
        "ano_final": "",
        "trimestre_final": "",
        "numero_processo": "",
        "orgao": "",
        "data_decisao": "",
        "deposito_judicial": False,
        "suporte": "",
    }


def _pres_tela_medida_nova(request, empresa, *, valores, erro=None, status=200):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Nova medida judicial",
        valores=valores,
        erro=erro,
        opcoes_tributo=[("irpj", "IRPJ"), ("csll", "CSLL"), ("ambos", "IRPJ e CSLL")],
        url_envio=reverse("fiscal_web:presumido_medida_nova", args=[empresa.pk]),
        url_voltar=_pres_url_consulta("fiscal_web:presumido_medidas", empresa),
    )
    return render(request, "fiscal/presumido_medida_form.html", contexto, status=status)


def _pres_inteiro_opcional(bruto: str, nome: str):
    """Ano ou trimestre opcional: vazio é None (prazo indeterminado no final); texto ruim é erro."""
    texto = bruto.strip()
    if not texto:
        return None
    valor = _inteiro_de_filtro(texto)
    if valor is None:
        raise servico_presumido.EntradaInvalidaPresumido(f"{nome} deve ser um número inteiro.")
    return valor


@login_required
@require_http_methods(["GET", "POST"])
def presumido_medida_nova(request, empresa_id):
    """Cadastra uma medida judicial contra o acréscimo, com processo, órgão, data e suporte."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    if request.method == "GET":
        return _pres_tela_medida_nova(request, empresa, valores=_pres_valores_medida())
    campos = (
        "tributo",
        "ano_inicial",
        "trimestre_inicial",
        "ano_final",
        "trimestre_final",
        "numero_processo",
        "orgao",
        "data_decisao",
        "suporte",
    )
    valores = {campo: request.POST.get(campo, "") for campo in campos}
    valores["deposito_judicial"] = request.POST.get("deposito_judicial", "") == "1"
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_MEDIDA)
        data = _data_do_formulario(valores["data_decisao"])
        if data is None:
            raise servico_presumido.EntradaInvalidaPresumido(
                "A data da decisão é inválida: use dd/mm/aaaa."
            )
        dados = {
            "tributo": valores["tributo"],
            "ano_inicial": _inteiro_de_filtro(valores["ano_inicial"].strip()),
            "trimestre_inicial": _inteiro_de_filtro(valores["trimestre_inicial"].strip()),
            "ano_final": _pres_inteiro_opcional(valores["ano_final"], "O ano final"),
            "trimestre_final": _pres_inteiro_opcional(
                valores["trimestre_final"], "O trimestre final"
            ),
            "numero_processo": valores["numero_processo"],
            "orgao": valores["orgao"],
            "data_decisao": data,
            "deposito_judicial": valores["deposito_judicial"],
            "suporte": valores["suporte"],
        }
        servico_presumido.cadastrar_medida(empresa, dados, request.user, request)
    except DadoNaoContratado as exc:
        return _pres_tela_medida_nova(
            request, empresa, valores=valores, erro=exc.mensagem, status=400
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_medida_nova(
            request, empresa, valores=valores, erro=exc.mensagem, status=status
        )
    messages.success(request, "Medida judicial cadastrada.")
    return redirect(_pres_url_consulta("fiscal_web:presumido_medidas", empresa))


def _pres_tela_revogar(request, empresa, medida, *, motivo="", erro=None, status=200):
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=True,
        titulo="Revogar medida judicial",
        medida=_pres_linha_da_medida(medida, empresa, False),
        motivo=motivo,
        erro=erro,
        url_envio=reverse("fiscal_web:presumido_medida_revogar", args=[empresa.pk, medida.pk]),
        url_voltar=_pres_url_consulta("fiscal_web:presumido_medidas", empresa),
    )
    return render(request, "fiscal/presumido_medida_revogar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
def presumido_medida_revogar(request, empresa_id, medida_id):
    """Revoga uma medida ativa, com motivo. A medida não é apagada: a revogação fica na trilha."""
    recusa = _pres_recusa_de_escrita(request)
    if recusa is not None:
        return recusa
    empresa = _empresa_escopada(request, empresa_id)
    medida = get_object_or_404(MedidaJudicialLC224, pk=medida_id, empresa=empresa)
    if request.method == "GET":
        return _pres_tela_revogar(request, empresa, medida)
    motivo = request.POST.get("motivo", "")
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_PRESUMIDO_MOTIVO)
        servico_presumido.revogar_medida(empresa, medida.pk, motivo, request.user, request)
    except DadoNaoContratado as exc:
        return _pres_tela_revogar(
            request, empresa, medida, motivo=motivo, erro=exc.mensagem, status=400
        )
    except servico_presumido.PresumidoErro as exc:
        status = 400 if isinstance(exc, servico_presumido.EntradaInvalidaPresumido) else 409
        return _pres_tela_revogar(
            request, empresa, medida, motivo=motivo, erro=exc.mensagem, status=status
        )
    messages.success(request, "Medida judicial revogada.")
    return redirect(_pres_url_consulta("fiscal_web:presumido_medidas", empresa))


# ---------------------------------------------------------------------------
# Apuração do trimestre: a memória de conferência (tela 6)
# ---------------------------------------------------------------------------


def _pres_valor_ou_traco(valor) -> str:
    return _valor_ptbr(valor) if valor is not None else "—"


def _pres_memoria_por_atividade(linhas, com_acrescimo: bool) -> list[dict]:
    """Uma linha por atividade: receita, excedente, alíquotas (normal e acrescida) e parcelas.

    Os números vêm prontos do serviço; a tela só formata. Sem acréscimo no trimestre, a coluna
    acrescida sai como traço, e não como zero (ausência não é zero).
    """
    return [
        {
            "atividade": tab_presumido.ATIVIDADES_POR_CODIGO[linha.atividade].rotulo,
            "receita": _valor_ptbr(linha.receita),
            "excedente": _valor_ptbr(linha.excedente),
            "aliquota": _pres_percentual(linha.aliquota),
            "aliquota_acrescida": _pres_percentual(linha.aliquota_acrescida)
            if com_acrescimo
            else "—",
            "parcela_normal": _valor_ptbr(linha.base_normal),
            "parcela_acrescida": _valor_ptbr(linha.base_acrescida) if com_acrescimo else "—",
        }
        for linha in linhas
    ]


def _pres_medida_na_tela(colunas) -> dict:
    if colunas.medida == "suspensa":
        texto = (
            "Parcela suspensa por medida judicial: "
            f"{_valor_ptbr(colunas.valor_suspenso)} fica fora "
            "do a recolher. A coluna recolhida é a sem LC 224."
        )
    elif colunas.medida == "depositar":
        texto = (
            "Parcela a depositar em juízo: "
            f"{_valor_ptbr(colunas.valor_suspenso)}. A coluna recolhida "
            "é a sem LC 224."
        )
    else:
        texto = "Sem medida judicial ativa neste trimestre para este tributo."
    return {"situacao": colunas.medida, "texto": texto}


def _pres_quotas_na_tela(quotas) -> dict:
    def parcela(p):
        return {
            "numero": p.numero,
            "valor": _valor_ptbr(p.valor),
            "vencimento": _data_na_tela(p.vencimento),
            "aviso": "calendário a conferir" if p.aviso_calendario else "",
            "juros": p.juros,
        }

    return {
        "devido": _valor_ptbr(quotas.devido),
        "unica": [parcela(p) for p in quotas.quota_unica],
        "duas": [parcela(p) for p in quotas.duas_quotas] if quotas.duas_quotas else None,
        "motivo_sem_duas": quotas.motivo_sem_duas_quotas or "",
        "tres": [parcela(p) for p in quotas.tres_quotas] if quotas.tres_quotas else None,
        "motivo_sem_tres": quotas.motivo_sem_tres_quotas or "",
    }


def _pres_tributo_na_tela(colunas, trimestre: int, fechamento, codigo_tributo: str) -> dict:
    """Um tributo no trimestre: as três colunas, a memória por atividade, a medida, a dedução e a
    recolher. Os valores são os do serviço; esta função só escolhe o que mostrar e formata."""
    linha = colunas.linhas_do_ano[trimestre - 1]
    sem = linha.sem_lc224
    com = linha.com_lc224
    com_acrescimo = com is not None
    colunas_tres = [
        {
            "rotulo": "Base de cálculo",
            "sem": _valor_ptbr(sem.base),
            "com": _pres_valor_ou_traco(com.base if com_acrescimo else None),
            "parcela": "—",
        },
        {
            "rotulo": "Imposto principal",
            "sem": _valor_ptbr(sem.principal),
            "com": _pres_valor_ou_traco(com.principal if com_acrescimo else None),
            "parcela": "—",
        },
        {
            "rotulo": "Adicional",
            "sem": _valor_ptbr(sem.adicional)
            if codigo_tributo == tab_presumido.IRPJ
            else "não se aplica",
            "com": (
                _pres_valor_ou_traco(com.adicional if com_acrescimo else None)
                if codigo_tributo == tab_presumido.IRPJ
                else "não se aplica"
            ),
            "parcela": "—",
        },
        {
            "rotulo": "Imposto total",
            "sem": _valor_ptbr(sem.total),
            "com": _pres_valor_ou_traco(com.total if com_acrescimo else None),
            "parcela": _pres_valor_ou_traco(linha.parcela_lc224),
        },
    ]
    return {
        "tributo": _TRIBUTO_PRESUMIDO_ROTULO[codigo_tributo],
        "codigo_darf": tab_presumido.CODIGO_DARF[codigo_tributo],
        "rotulo_darf": tab_presumido.ROTULO_DARF[codigo_tributo],
        "fonte_darf": tab_presumido.FONTE_CODIGOS_DARF,
        "acrescimo_aplicavel": colunas.acrescimo_aplicavel,
        "memoria": _pres_memoria_por_atividade(
            colunas.memoria_com_lc224 if com_acrescimo else colunas.memoria_sem_lc224, com_acrescimo
        ),
        "receitas_integrais": _valor_ptbr(colunas.receitas_integrais),
        "colunas": colunas_tres,
        "coluna_escolhida": "com LC 224"
        if colunas.coluna_escolhida == "com_lc224"
        else "sem LC 224",
        "medida": _pres_medida_na_tela(colunas),
        "retencao_confirmada": _valor_ptbr(colunas.retencao_confirmada),
        "deducao_quarto": _valor_ptbr(colunas.deducao_quarto_trimestre)
        if trimestre == 4
        else "não se aplica fora do 4º trimestre",
        "saldo_per_dcomp": _valor_ptbr(colunas.saldo_per_dcomp),
        "saldo_negativo": _valor_ptbr(colunas.saldo_negativo),
        "tributo_escolhido": _valor_ptbr(colunas.tributo_escolhido),
        "a_recolher": _valor_ptbr(colunas.a_recolher),
        "quotas": _pres_quotas_na_tela(colunas.quotas),
        "caso_quarto": _TEXTO_CASO_QUARTO.get(colunas.caso_quarto) if colunas.caso_quarto else None,
        "fechamento": (
            _pres_fechamento_na_tela(fechamento, linha_do_ano=colunas.linhas_do_ano)
            if fechamento is not None
            else None
        ),
    }


def _pres_fechamento_na_tela(fechamento, *, linha_do_ano) -> dict:
    """Memória do fechamento do ano: N, limite anual, excedente, S e o que cada trimestre contribui.

    Trimestre coberto por medida aparece como parcela suspensa, fora da dedução (item 0).
    """
    return {
        "n": fechamento.n,
        "receita_no_acrescimo": _valor_ptbr(fechamento.receita_no_acrescimo),
        "limite_anual": _valor_ptbr(fechamento.limite_anual),
        "excedente_anual": _valor_ptbr(fechamento.excedente_anual),
        "s": _valor_ptbr(fechamento.s),
        "caso": fechamento.caso,
        "caso_texto": _TEXTO_CASO_QUARTO[fechamento.caso],
        "trimestres": [
            {
                "trimestre": linha.trimestre,
                "diferenca": (
                    _PARCELA_SUSPENSA_TEXTO
                    if linha.suspensa_por_medida
                    else _pres_valor_ou_traco(linha.diferenca_recalculo)
                ),
                "suspensa": linha.suspensa_por_medida,
            }
            for linha in linha_do_ano
            if linha.em_acrescimo
        ],
    }


def _pres_apuracao_na_tela(apuracao, ano, trimestre) -> dict:
    """Situação, recusas nomeadas, notas e receitas que compõem a base, e os dois tributos."""
    if apuracao.recusas:
        motivo = "há recusas, listadas abaixo; nenhum tributo sai."
    elif apuracao.declaracao_total is None:
        motivo = (
            "receitas integrais do trimestre não declaradas "
            "(sem a declaração, a apuração é parcial)."
        )
    elif not apuracao.declaracao_valida:
        motivo = "a declaração de receitas integrais caiu porque o total mudou depois dela."
    else:
        motivo = ""
    tributos = {}
    if apuracao.irpj is not None:
        tributos["irpj"] = _pres_tributo_na_tela(
            apuracao.irpj, trimestre, apuracao.fechamento_irpj, tab_presumido.IRPJ
        )
        tributos["csll"] = _pres_tributo_na_tela(
            apuracao.csll, trimestre, apuracao.fechamento_csll, tab_presumido.CSLL
        )
    return {
        "ano": ano,
        "trimestre_rotulo": _pres_trimestre(ano, trimestre),
        "situacao": apuracao.situacao,
        "situacao_texto": (
            "Completa: não há recusa e a declaração de receitas integrais vale."
            if apuracao.situacao == "completa"
            else f"Parcial: {motivo}"
        ),
        "criterio": _ROTULO_CRITERIO_PRESUMIDO.get(apuracao.criterio, "não informado"),
        "recusas": [
            {"codigo": r.codigo, "mensagem": r.mensagem, "itens": ", ".join(r.itens)}
            for r in apuracao.recusas
        ],
        "notas": [
            {
                "numero": n.numero or n.identificador,
                "competencia": _data_na_tela(n.data_competencia),
                "valor": _valor_ptbr(n.valor_servico),
                "desconto": _valor_ptbr(n.desconto_incondicionado),
                "base": _valor_ptbr(n.base),
                "atividade": tab_presumido.ATIVIDADES_POR_CODIGO[n.atividade].rotulo,
            }
            for n in apuracao.notas
        ],
        "receitas": [
            {
                "atividade": tab_presumido.ATIVIDADES_POR_CODIGO[r.atividade].rotulo,
                "valor": _valor_ptbr(r.valor),
            }
            for r in apuracao.receitas
        ],
        "integrais_atuais": _valor_ptbr(apuracao.integrais_atuais),
        "declaracao": _pres_declaracao_na_tela(apuracao),
        "tributos": tributos,
        "avisos": list(apuracao.avisos),
        "fontes": [
            tab_presumido.FONTE_ALIQUOTAS,
            tab_presumido.FONTE_LIMITE_LC224,
            tab_presumido.FONTE_PERCENTUAIS,
        ],
    }


@login_required
@require_safe
def presumido_apuracao(request):
    """Memória de conferência do trimestre: os dois tributos, as três colunas, as recusas.

    Esta tela não grava nada e não calcula: lê a apuração do serviço e mostra. Não é guia nem DARF.
    """
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    ano, trimestre, erro_periodo = _pres_periodo_padrao(request)
    erro = erro or erro_periodo
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=_pode_escriturar(request),
        titulo="Apuração do trimestre",
        ano_filtro=ano,
        trimestre_filtro=trimestre,
        erro=erro,
    )
    if erro or empresa is None:
        return render(
            request, "fiscal/presumido_apuracao.html", contexto, status=400 if erro else 200
        )
    apuracao = servico_presumido.apurar_trimestre(empresa, ano, trimestre)
    contexto.update(
        apuracao=_pres_apuracao_na_tela(apuracao, ano, trimestre),
        url_consulta=_pres_url_consulta(
            "fiscal_web:presumido_apuracao", empresa, ano=ano, trimestre=trimestre
        ),
    )
    return render(request, "fiscal/presumido_apuracao.html", contexto)


# ---------------------------------------------------------------------------
# Controle do limite do ano (tela 7)
# ---------------------------------------------------------------------------


@login_required
@require_safe
def presumido_limite(request):
    """Controle do limite de R$ 1.250.000,00 por trimestre, por tributo, com o fechamento."""
    recusa = _pres_recusa_de_consulta(request)
    if recusa is not None:
        return recusa
    empresa, erro = _empresa_da_escrituracao(request)
    ano, erro_ano = _pres_ano_padrao(request)
    tributo = request.GET.get("tributo", "irpj").strip() or "irpj"
    erro = erro or erro_ano
    contexto = _pres_contexto(
        request,
        empresa,
        pode_escriturar=_pode_escriturar(request),
        titulo="Controle do limite do ano",
        ano_filtro=ano,
        tributo_filtro=tributo,
        opcoes_tributo=[("irpj", "IRPJ"), ("csll", "CSLL")],
        erro=erro,
    )
    if erro or empresa is None:
        return render(
            request, "fiscal/presumido_limite.html", contexto, status=400 if erro else 200
        )
    try:
        controle = servico_presumido.controle_limite_ano(empresa, ano, tributo)
    except servico_presumido.EntradaInvalidaPresumido as exc:
        contexto["erro"] = exc.mensagem
        return render(request, "fiscal/presumido_limite.html", contexto, status=400)
    contexto.update(
        controle=_pres_controle_na_tela(controle),
        url_consulta=_pres_url_consulta(
            "fiscal_web:presumido_limite", empresa, ano=ano, tributo=tributo
        ),
    )
    return render(request, "fiscal/presumido_limite.html", contexto)


def _pres_controle_na_tela(controle) -> dict:
    linhas = [
        {
            "trimestre": linha.trimestre,
            "acrescimo": "com acréscimo"
            if linha.em_acrescimo
            else "sem acréscimo (fora do período)",
            "receita": _valor_ptbr(linha.receita_presumida),
            "limite": _pres_valor_ou_traco(linha.limite),
            "excedente": _pres_valor_ou_traco(linha.excedente) if linha.em_acrescimo else "—",
            "sobra": _pres_valor_ou_traco(linha.sobra),
            "diferenca": (
                _PARCELA_SUSPENSA_TEXTO
                if linha.suspensa_por_medida
                else _pres_valor_ou_traco(linha.diferenca_recalculo)
            ),
        }
        for linha in controle.linhas
    ]
    fechamento = None
    if controle.fechamento is not None:
        fechamento = {
            "n": controle.fechamento.n,
            "limite_anual": _valor_ptbr(controle.fechamento.limite_anual),
            "receita_no_acrescimo": _valor_ptbr(controle.fechamento.receita_no_acrescimo),
            "excedente_anual": _valor_ptbr(controle.fechamento.excedente_anual),
            "s": _valor_ptbr(controle.fechamento.s),
            "caso": controle.fechamento.caso,
            "caso_texto": _TEXTO_CASO_QUARTO[controle.fechamento.caso],
            "deducao": _valor_ptbr(controle.deducao_quarto_trimestre),
        }
    return {
        "tributo": _TRIBUTO_PRESUMIDO_ROTULO[controle.tributo],
        "primeiro_trimestre": controle.primeiro_trimestre,
        "linhas": linhas,
        "fechamento": fechamento,
        "recusas": [
            {"codigo": r.codigo, "mensagem": r.mensagem, "itens": ", ".join(r.itens)}
            for r in controle.recusas
        ],
    }


# ---------------------------------------------------------------------------
# DL-080 (frente B): NF-e e NFC-e recebidas — telas de conferência, só leitura.
#
# Esta seção não decide situação nem direção. A situação vem de
# `services.vinculos_nfe_da_empresa` (anotação `cancelada`, na lista) e de
# `services.situacao_da_nfe` (no detalhe). A direção vem de
# `apps.fiscal.api_nfe.direcao_para_o_cliente`, a MESMA função que a API usa. Aqui só se traduz
# código para texto, se escolhe o outro lado da nota e se formata valor em pt-BR.
#
# Isolamento: a lista pede UMA empresa do escritório ativo (empresa de outro escritório, ou
# inexistente, responde 404). O detalhe busca a nota DENTRO do vínculo com a empresa da URL, então
# nota de outra empresa do mesmo escritório, ou de outro escritório, responde 404 (IDOR).
# ---------------------------------------------------------------------------

_MENSAGEM_SEM_CONSULTA_NFE = "Seu papel não permite consultar NF-e recebidas."

# Texto literal do aviso de cancelamento (plano DL-080, item 9). A tela não o reescreve.
_AVISO_NFE_CANCELADA = "NF-e cancelada — não tem efeito fiscal."

_ROTULO_PAPEL_NFE = {PapelNFe.EMITENTE: "Emitente", PapelNFe.DESTINATARIO: "Destinatário"}
_ROTULO_DIRECAO_NFE = {
    "saida": "Saída",
    "entrada": "Entrada",
    "entrada_propria": "Entrada própria",
    "a_conferir": "A conferir",
}
_ROTULO_SITUACAO_NFE = {"valida": "Autorizada", "cancelada": "Cancelada"}

# finNFe (plano DL-080, item 9). Código fora deste mapa aparece cru, nunca com um texto inventado.
_ROTULO_FIN_NFE = {
    "1": "Normal",
    "2": "Complementar",
    "3": "De ajuste",
    "4": "Devolução",
    "5": "Nota de crédito",
    "6": "Nota de débito",
}
_ROTULO_TP_NF = {"0": "0 (entrada)", "1": "1 (saída)"}
_ROTULO_EFEITO_EVENTO_NFE = {
    "cancela": "Cancela a nota",
    "sem efeito": "Sem efeito sobre a situação",
}
_TEXTO_EVENTO_SEM_NOME = "Evento não catalogado nesta recepção"

# Campos de ICMSTot na ordem da tela. Campo ausente (None) vira "—" em `valor_ptbr`, nunca zero.
_CAMPOS_TOTAIS_NFE = (
    ("v_nf", "Valor total da nota (vNF)"),
    ("v_prod", "Valor dos produtos (vProd)"),
    ("v_icms", "ICMS (vICMS)"),
    ("v_st", "ICMS-ST (vST)"),
    ("v_ipi", "IPI (vIPI)"),
    ("v_pis", "PIS (vPIS)"),
    ("v_cofins", "COFINS (vCOFINS)"),
    ("v_desc", "Desconto (vDesc)"),
    ("v_frete", "Frete (vFrete)"),
)

_FILTROS_NFE_SEM_EMPRESA = ("emissao_de", "emissao_ate", "papel", "modelo", "situacao")

# Só dígito ASCII entra na data: `datetime.strptime` aceitaria dígito Unicode sem avisar.
_PADRAO_DATA_BR = re.compile(r"[0-9]{2}/[0-9]{2}/[0-9]{4}")


def _empresa_nfe_da_consulta(request, bruto):
    """Empresa do escritório ativo pelo parâmetro `empresa`. Malformada, inexistente ou de outro
    escritório: 404. Não se diferencia uma da outra, para não confirmar que o ID existe."""
    try:
        empresa_id = para_id(bruto)
    except IdentificadorInvalido as exc:
        raise Http404("Empresa não encontrada.") from exc
    return get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)


def _data_br_do_filtro(bruto, rotulo):
    """`dd/mm/aaaa` -> `date`. Vazio -> None. Valor fora do formato: ValueError com mensagem."""
    if not bruto:
        return None
    if not _PADRAO_DATA_BR.fullmatch(bruto):
        raise ValueError(f"'{rotulo}' deve ser uma data no formato dd/mm/aaaa.")
    try:
        return datetime.strptime(bruto, "%d/%m/%Y").date()
    except ValueError as exc:
        raise ValueError(f"'{rotulo}' não é uma data válida.") from exc


def _filtros_de_nfe(parametros):
    """Filtros da lista, já no formato que `vinculos_nfe_da_empresa` recebe.

    O filtro de período é pela data de EMISSÃO (`dhEmi`), como no serviço. Valor inválido vira
    ValueError com a mensagem que a tela mostra.
    """
    filtros = {}
    inicio = _data_br_do_filtro(parametros.get("emissao_de", "").strip(), "Emissão de")
    fim = _data_br_do_filtro(parametros.get("emissao_ate", "").strip(), "Emissão até")
    if inicio and fim and inicio > fim:
        raise ValueError("'Emissão de' não pode ser posterior a 'Emissão até'.")
    if inicio:
        filtros["inicio"] = inicio
    if fim:
        filtros["fim"] = fim

    papel = parametros.get("papel", "").strip()
    if papel:
        if papel not in PapelNFe.values:
            raise ValueError("'Papel' deve ser emitente ou destinatário.")
        filtros["papel"] = papel

    modelo = parametros.get("modelo", "").strip()
    if modelo:
        if modelo not in ModeloNFe.values:
            raise ValueError("'Modelo' deve ser 55 (NF-e) ou 65 (NFC-e).")
        filtros["modelo"] = modelo

    situacao = parametros.get("situacao", "").strip()
    if situacao:
        if situacao not in _ROTULO_SITUACAO_NFE:
            raise ValueError("'Situação' deve ser autorizada ou cancelada.")
        filtros["situacao"] = situacao
    return filtros


def _chave_em_grupos(chave):
    """Chave de acesso em grupos de 4 posições, só para leitura."""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def _documento_na_tela(tipo, numero):
    """CNPJ e CPF com máscara, só para leitura. Outro tipo (idEstrangeiro) sai como veio."""
    if not tipo:
        return ""
    if tipo == "CNPJ" and len(numero) == 14:
        return f"CNPJ {numero[:2]}.{numero[2:5]}.{numero[5:8]}/{numero[8:12]}-{numero[12:]}"
    if tipo == "CPF" and len(numero) == 11:
        return f"CPF {numero[:3]}.{numero[3:6]}.{numero[6:9]}-{numero[9:]}"
    return f"{tipo} {numero}"


def _contraparte_da_nota(documento, papel):
    """`(nome, documento)` do OUTRO lado da nota, o que não é a empresa consultada.

    Empresa emitente: a contraparte é o destinatário, que pode faltar (NFC-e). Empresa destinatária:
    a contraparte é o emitente, que sempre existe.
    """
    if papel == PapelNFe.EMITENTE:
        return (
            documento.destinatario_nome,
            _documento_na_tela(
                documento.destinatario_tipo_documento, documento.destinatario_documento
            ),
        )
    return (
        documento.emitente_nome,
        _documento_na_tela(documento.emitente_tipo_documento, documento.emitente_documento),
    )


# Ordem das direções no quadro de totais (A5). A soma é por direção, nunca única: uma soma de
# saídas e entradas juntas não tem sentido contábil e pareceria faturamento.
_DIRECOES_NO_TOTAL = ("saida", "entrada", "entrada_propria", "a_conferir")


def _totais_por_direcao(vinculos):
    """Quantidade e soma de vNF por DIREÇÃO das autorizadas, e o total das canceladas.

    Conta sobre o conjunto FILTRADO inteiro, não só a página. A direção sai do MESMO ponto da API
    (`direcao_para_o_cliente`, papel combinado com `tpNF`), uma vez por grupo de (papel, tpNF,
    situação), e não é recalculada aqui. Cancelada fica fora de TODAS as direções: ela tem a
    própria linha. `sem_valor` conta notas sem vNF, que não entram na soma.
    """
    zerado = {"quantidade": 0, "soma": Decimal("0"), "sem_valor": 0}
    totais = {direcao: dict(zerado) for direcao in _DIRECOES_NO_TOTAL}
    totais["cancelada"] = dict(zerado)
    grupos = (
        vinculos.order_by()
        .values("papel", "documento__tp_nf", "cancelada")
        .annotate(
            quantidade=Count("id"),
            soma=Sum("documento__v_nf"),
            sem_valor=Count("id", filter=Q(documento__v_nf__isnull=True)),
        )
    )
    for grupo in grupos:
        if grupo["cancelada"]:
            destino = totais["cancelada"]
        else:
            destino = totais[direcao_para_o_cliente(grupo["papel"], grupo["documento__tp_nf"])]
        destino["quantidade"] += grupo["quantidade"]
        destino["soma"] += grupo["soma"] or Decimal("0")
        destino["sem_valor"] += grupo["sem_valor"]
    quadro = {
        chave: {
            "quantidade": dados["quantidade"],
            "soma_ptbr": _valor_ptbr(dados["soma"]),
            "sem_valor": dados["sem_valor"],
        }
        for chave, dados in totais.items()
    }
    # Só para a frase da tela: autorizadas sem vNF, somadas entre as direções (nunca um valor).
    quadro["autorizadas_sem_valor"] = sum(
        totais[direcao]["sem_valor"] for direcao in _DIRECOES_NO_TOTAL
    )
    return quadro


def _linha_da_nfe(vinculo, empresa):
    documento = vinculo.documento
    nome_contraparte, documento_contraparte = _contraparte_da_nota(documento, vinculo.papel)
    cancelada = bool(vinculo.cancelada)  # anotação do serviço, sem consulta nova por linha
    return {
        "modelo": documento.get_modelo_display(),
        "serie": documento.serie,
        "numero": documento.numero,
        "emissao": documento.dh_emissao,
        "contraparte_nome": nome_contraparte,
        "contraparte_documento": documento_contraparte,
        "papel": _ROTULO_PAPEL_NFE[vinculo.papel],
        "direcao": _ROTULO_DIRECAO_NFE[direcao_para_o_cliente(vinculo.papel, documento.tp_nf)],
        "cancelada": cancelada,
        "situacao": _ROTULO_SITUACAO_NFE["cancelada" if cancelada else "valida"],
        "v_nf_ptbr": _valor_ptbr(documento.v_nf),
        "tem_ibscbs": documento.tem_ibscbs_total or documento.tem_ibscbs_item,
        "transferencia": documento.transferencia_entre_estabelecimentos,
        "url": reverse("fiscal_web:nfe_detalhe", args=[empresa.pk, documento.pk]),
    }


@login_required
@require_safe
def nfe_recebidas(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_NFE)

    # Valores BRUTOS (como vieram na querystring) voltam ao formulário também no erro.
    filtros_brutos = {nome: request.GET.get(nome, "").strip() for nome in _FILTROS_NFE_SEM_EMPRESA}
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa": None,
        "filtros_brutos": filtros_brutos,
        "algum_filtro_ativo": any(filtros_brutos.values()),
        "pagina": None,
        "linhas": [],
        "totais": [],
        "url_trocar_empresa": reverse("fiscal_web:nfe_recebidas"),
        "url_eventos_sem_nota": reverse("fiscal_web:nfe_eventos_orfaos"),
    }
    bruto_empresa = request.GET.get("empresa", "").strip()
    if not bruto_empresa:
        return render(request, "fiscal/nfe_lista.html", contexto)

    empresa = _empresa_nfe_da_consulta(request, bruto_empresa)
    contexto["empresa"] = empresa
    try:
        filtros = _filtros_de_nfe(request.GET)
    except ValueError as exc:
        messages.error(request, str(exc))
        return render(request, "fiscal/nfe_lista.html", contexto, status=400)

    vinculos = vinculos_nfe_da_empresa(request.escritorio, empresa, **filtros)
    pagina = Paginator(vinculos, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto.update(
        {
            "pagina": pagina,
            "linhas": [_linha_da_nfe(vinculo, empresa) for vinculo in pagina.object_list],
            "totais": _totais_por_direcao(vinculos),
            "querystring_sem_pagina": _querystring_sem_pagina(request),
        }
    )
    return render(request, "fiscal/nfe_lista.html", contexto)


def _evento_na_tela(evento):
    return {
        "tipo": evento.tp_evento,
        "nome": DESCRICAO_EVENTO_NFE.get(evento.tp_evento, _TEXTO_EVENTO_SEM_NOME),
        "sequencia": evento.n_seq_evento,
        "data": evento.dh_evento,
        # `c_stat` do retorno. Vazio quando o retorno não veio: sem retorno, sem efeito.
        "c_stat": evento.c_stat or "",
        "efeito": _ROTULO_EFEITO_EVENTO_NFE[efeito_do_evento_nfe(evento)],
        # Aviso para conferir (cStat 136). `None` quando não há, e a tela não mostra nada.
        "aviso": aviso_do_evento_nfe(evento),
    }


@login_required
@require_safe
def nfe_detalhe(request, empresa_id, documento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_NFE)

    empresa = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)
    # Busca pelo VÍNCULO com a empresa da URL. Nota de outra empresa do mesmo escritório, ou de
    # outro escritório, responde 404 (IDOR).
    vinculo = get_object_or_404(
        VinculoNFeEmpresa.objects.select_related("documento"),
        empresa=empresa,
        documento_id=documento_id,
        documento__escritorio=request.escritorio,
    )
    documento = vinculo.documento
    situacao = situacao_da_nfe(documento)
    eventos = EventoNFe.objects.filter(
        escritorio=request.escritorio, chave=documento.chave
    ).order_by("dh_evento", "n_seq_evento")
    contexto = {
        "empresa": empresa,
        "documento": documento,
        "situacao": situacao,
        "situacao_rotulo": _ROTULO_SITUACAO_NFE[situacao],
        "aviso_cancelada": _AVISO_NFE_CANCELADA if situacao == "cancelada" else "",
        "papel_rotulo": _ROTULO_PAPEL_NFE[vinculo.papel],
        "direcao_rotulo": _ROTULO_DIRECAO_NFE[
            direcao_para_o_cliente(vinculo.papel, documento.tp_nf)
        ],
        "modelo_rotulo": documento.get_modelo_display(),
        "chave_em_grupos": _chave_em_grupos(documento.chave),
        "tp_nf_rotulo": _ROTULO_TP_NF.get(documento.tp_nf, documento.tp_nf),
        "fin_nfe_rotulo": _ROTULO_FIN_NFE.get(documento.fin_nfe, documento.fin_nfe),
        "emitente_documento": _documento_na_tela(
            documento.emitente_tipo_documento, documento.emitente_documento
        ),
        "destinatario_definido": bool(documento.destinatario_tipo_documento),
        "destinatario_documento": _documento_na_tela(
            documento.destinatario_tipo_documento, documento.destinatario_documento
        ),
        "totais": [
            (rotulo, _valor_ptbr(getattr(documento, campo))) for campo, rotulo in _CAMPOS_TOTAIS_NFE
        ],
        "eventos": [_evento_na_tela(evento) for evento in eventos],
        "url_lista": reverse("fiscal_web:nfe_recebidas") + f"?empresa={empresa.pk}",
    }
    return render(request, "fiscal/nfe_detalhe.html", contexto)


def _evento_orfao_na_tela(evento):
    return {
        **_evento_na_tela(evento),
        "chave_em_grupos": _chave_em_grupos(evento.chave),
        # Autor identificado só quando o CNPJ/CPF é de empresa do escritório. Cancelamento de
        # fornecedor, por exemplo, fica sem autor identificado.
        "autor_empresa": evento.empresa.razao_social if evento.empresa_id else "",
    }


@login_required
@require_safe
def nfe_eventos_orfaos(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_NFE)

    bruto_empresa = request.GET.get("empresa", "").strip()
    empresa = _empresa_nfe_da_consulta(request, bruto_empresa) if bruto_empresa else None
    # Órfão é o evento cuja nota ainda não está no acervo DESTE escritório. Quando a nota chega, o
    # evento sai daqui sem nenhuma gravação: a situação da nota já consulta o evento por chave.
    nota_no_acervo = DocumentoNFe.objects.filter(
        escritorio_id=OuterRef("escritorio_id"), chave=OuterRef("chave")
    )
    eventos = (
        EventoNFe.objects.filter(escritorio=request.escritorio)
        .annotate(tem_nota=Exists(nota_no_acervo))
        .filter(tem_nota=False)
    )
    # O filtro por empresa é pelo AUTOR do evento (`EventoNFe.empresa`). Cancelamento de fornecedor
    # não tem autor no escritório, então só aparece sem filtro.
    if empresa is not None:
        eventos = eventos.filter(empresa=empresa)
    # Desempate pela chave primária: eventos com o mesmo dhEvento e nSeqEvento (lote de notas
    # ainda não chegadas) saem numa ordem fixa, sem repetir nem omitir linhas entre páginas (A2).
    eventos = eventos.select_related("empresa").order_by("-dh_evento", "-n_seq_evento", "-pk")
    pagina = Paginator(eventos, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa": empresa,
        "empresa_filtro_bruto": bruto_empresa,
        "pagina": pagina,
        "linhas": [_evento_orfao_na_tela(evento) for evento in pagina.object_list],
        "querystring_sem_pagina": _querystring_sem_pagina(request),
        "algum_filtro_ativo": bool(bruto_empresa),
        "url_lista_nfe": reverse("fiscal_web:nfe_recebidas"),
    }
    return render(request, "fiscal/nfe_eventos_orfaos.html", contexto)


# ---------------------------------------------------------------------------
# DL-081 (frente B): telas da escrituração das NF-e de saída e da devolução de venda.
#
# A tela chama o serviço da frente A (`apps.fiscal.escrituracao_nfe`) e NÃO recalcula nada:
# elegibilidade, sugestão, conferência com o vNF, efetivação, estorno e reclassificação são do
# serviço. Aqui só se lê a entrada (formato estranho responde 400, nunca 500), decide-se a
# permissão no servidor e o resultado vira texto em pt-BR. Arquétipos (direção de arte §2): a
# lista e a conferência são de consulta (A e C); escriturar é formulário de documento (B);
# estornar e reclassificar são confirmações de ação sensível (E).
# ---------------------------------------------------------------------------

_ANO_MINIMO_NFE, _ANO_MAXIMO_NFE = 1970, 2999
_TAMANHO_NATUREZA_NFE = 24
_ACOES_ESCRITURAR_NFE = frozenset({"criar", "item", "bloco", "efetivar"})
_ACOES_RECLASSIFICAR_NFE = frozenset({"previa", "confirmar"})
_MENSAGEM_SEM_CONSULTA_ESCRITURACAO_NFE = "Seu papel não permite consultar a escrituração de NF-e."
_MENSAGEM_SEM_ESCRITA_NFE = (
    "Seu papel consulta as NF-e, mas não escritura, estorna nem reclassifica. "
    "Peça a um administrador, gestor, analista ou financeiro do escritório."
)
_ROTULO_SITUACAO_NFE_ESCRITURACAO = {
    servico_nfe.SITUACAO_A_ESCRITURAR: "Sem escrituração",
    servico_nfe.SITUACAO_RASCUNHO: "Rascunho, não efetivada",
    servico_nfe.SITUACAO_EFETIVADA: "Efetivada",
    servico_nfe.SITUACAO_CANCELADA: "Cancelada, não escriturada",
    servico_nfe.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA: "Cancelada depois de escriturada",
    servico_nfe.SITUACAO_NAO_ELEGIVEL: "Fora da escrituração",
}
# O serviço devolve "a escriturar" também para a nota estornada. A tela só distingue, para
# quem lê, que ela já teve uma escrituração estornada: é um dado da própria linha, não regra.
_ROTULO_ESTORNADA_NFE = "Estornada, a escriturar de novo"
_ROTULO_LEITURA_NFE = {
    LeituraItensNFe.ESTADO_LIDA: "Lida",
    LeituraItensNFe.ESTADO_ILEGIVEL: "Ilegível",
}
_ROTULO_PAPEL_NATUREZA_NFE = {"receita": "Receita", "deducao": "Dedução (devolução)"}
_ROTULO_MERCADO_NFE = {"interno": "Mercado interno", "externo": "Mercado externo"}
_ROTULO_SEGREGACAO_NFE = {
    "normal": "Normal (revenda, produção e substituto)",
    "sujeita_st": "Sujeita a ST (natureza 3)",
    "monofasico": "Monofásico de PIS e Cofins (natureza 5)",
    "exportacao": "Exportação (mercado externo)",
}


class _EntradaNfeRecusada(Exception):
    """Entrada fora do formato aceito: a tela responde 400 com a mensagem, nunca 500."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _entrada_nfe_verificada(view):
    """Converte `_EntradaNfeRecusada` em 400 com a mensagem. Fica por DENTRO de `login_required`."""

    @wraps(view)
    def envoltorio(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except _EntradaNfeRecusada as exc:
            return render(
                request, "fiscal/nfe_entrada_recusada.html", {"mensagem": exc.mensagem}, status=400
            )

    return envoltorio


def _texto_seguro_nfe(valor, rotulo):
    """Recusa byte nulo e substituto isolado: o banco responde 500 se algum deles passa."""
    texto = "" if valor is None else valor
    if "\x00" in texto or any(0xD800 <= ord(caractere) <= 0xDFFF for caractere in texto):
        raise _EntradaNfeRecusada(f"'{rotulo}' tem caractere inválido.")
    return texto


def _texto_nfe(valor, rotulo, maximo):
    texto = _texto_seguro_nfe(valor, rotulo).strip()
    if len(texto) > maximo:
        raise _EntradaNfeRecusada(f"'{rotulo}' tem no máximo {maximo} caracteres.")
    return texto


def _id_da_rota_nfe(valor):
    # Identificador acima do bigint responde 400 aqui, antes do banco (que daria 500).
    if not 1 <= valor <= MAIOR_ID:
        raise _EntradaNfeRecusada("Identificador fora da faixa aceita.")
    return valor


def _id_do_formulario_nfe(bruto, rotulo):
    texto = _texto_nfe(bruto, rotulo, 19)
    if not re.fullmatch(r"[0-9]{1,19}", texto):
        raise _EntradaNfeRecusada(f"'{rotulo}' inválido.")
    return _id_da_rota_nfe(int(texto))


def _empresa_nfe_da_rota(request, empresa_id):
    # Empresa de OUTRO escritório é 404: não confirma que o ID existe.
    _id_da_rota_nfe(empresa_id)
    return get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)


def _empresa_nfe_do_campo(request, bruto):
    """Empresa de um campo (querystring ou formulário). Vazio é `None`; de outro escritório, 404."""
    texto = _texto_nfe(bruto, "Empresa", 20)
    if not texto:
        return None
    try:
        empresa_id = para_id(texto)
    except IdentificadorInvalido as exc:
        raise _EntradaNfeRecusada("'Empresa' inválida.") from exc
    return _empresa_nfe_da_rota(request, empresa_id)


def _vinculo_nfe_da_empresa(request, empresa, vinculo_id):
    # Vínculo de outra empresa (mesmo escritório) também é 404 (IDOR).
    _id_da_rota_nfe(vinculo_id)
    return get_object_or_404(
        VinculoNFeEmpresa.objects.select_related("documento"),
        pk=vinculo_id,
        empresa=empresa,
        documento__escritorio=request.escritorio,
    )


def _escrituracao_nfe_da_empresa(request, empresa, escrituracao_id):
    _id_da_rota_nfe(escrituracao_id)
    return get_object_or_404(
        EscrituracaoNFe.objects.select_related("vinculo__documento", "empresa"),
        pk=escrituracao_id,
        empresa=empresa,
        empresa__escritorio=request.escritorio,
    )


def _competencia_nfe(request):
    """(ano, mês) da consulta. Ausente: mês corrente (fuso de Brasília). Fora do formato ou da
    faixa: 400. O tamanho é conferido ANTES do `int`, para número gigante não estourar o limite."""
    _texto_nfe(request.GET.get("ano"), "Ano", 4)
    _texto_nfe(request.GET.get("mes"), "Mês", 2)
    competencia, erro = _competencia_do_filtro(request)
    if erro:
        raise _EntradaNfeRecusada(erro)
    if competencia is None:
        hoje = timezone.localdate()
        return hoje.year, hoje.month
    return competencia


def _data_nfe(bruto, rotulo):
    try:
        data = _data_br_do_filtro(_texto_nfe(bruto, rotulo, 10), rotulo)
    except ValueError as exc:
        raise _EntradaNfeRecusada(str(exc)) from exc
    if data is not None and not _ANO_MINIMO_NFE <= data.year <= _ANO_MAXIMO_NFE:
        raise _EntradaNfeRecusada(
            f"'{rotulo}' fora do intervalo aceito ({_ANO_MINIMO_NFE} a {_ANO_MAXIMO_NFE})."
        )
    return data


def _codigo_fiscal_nfe(bruto, rotulo, padrao, descricao):
    """CFOP, CST/CSOSN ou NCM: só dígitos, na quantidade certa. Vazio é filtro ausente."""
    texto = _texto_nfe(bruto, rotulo, 8)
    if not texto:
        return None
    if not re.fullmatch(padrao, texto):
        raise _EntradaNfeRecusada(f"'{rotulo}' deve ter {descricao}, só dígitos.")
    return texto


def _contagem_do_formulario_nfe(bruto, rotulo):
    texto = _texto_nfe(bruto, rotulo, 9)
    if not re.fullmatch(r"[0-9]{1,9}", texto):
        raise _EntradaNfeRecusada(f"'{rotulo}' inválido.")
    return int(texto)


def _vinculos_com_estorno(vinculo_ids):
    """Vínculos com escrituração ESTORNADA. Só para a linha dizer que a nota já foi escriturada."""
    if not vinculo_ids:
        return set()
    return set(
        EscrituracaoNFe.objects.filter(
            vinculo_id__in=vinculo_ids, estado=EstadoEscrituracao.ESTORNADA
        ).values_list("vinculo_id", flat=True)
    )


def _escrituracao_ativa_nfe(vinculo):
    """Rascunho ou efetivada da nota. A regra de unicidade é do serviço; aqui só se lê."""
    return EscrituracaoNFe.objects.filter(
        vinculo=vinculo,
        estado__in=[EstadoEscrituracao.RASCUNHO, EstadoEscrituracao.EFETIVADA],
    ).first()


def _linha_nfe_a_escriturar(nota, empresa, pode_escriturar, estornadas):
    """Linha da lista e da conferência. A situação vem do serviço; a tela só a traduz."""
    documento = nota.documento
    situacao = nota.situacao
    rotulo = _ROTULO_SITUACAO_NFE_ESCRITURACAO.get(situacao, situacao)
    if situacao == servico_nfe.SITUACAO_A_ESCRITURAR and nota.vinculo.pk in estornadas:
        rotulo = _ROTULO_ESTORNADA_NFE
    ilegivel = nota.leitura_estado == LeituraItensNFe.ESTADO_ILEGIVEL
    url = reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, nota.vinculo.pk])
    if situacao == servico_nfe.SITUACAO_A_ESCRITURAR and pode_escriturar and not ilegivel:
        # Botão de criar o rascunho: POST para a própria tela de escriturar (que confere a conta).
        acao = {"tipo": "criar", "rotulo": "Criar rascunho", "url": url}
    else:
        if situacao == servico_nfe.SITUACAO_RASCUNHO and pode_escriturar:
            rotulo_acao = "Continuar escrituração"
        elif situacao in (servico_nfe.SITUACAO_EFETIVADA, servico_nfe.SITUACAO_RASCUNHO):
            rotulo_acao = "Ver escrituração"
        else:
            rotulo_acao = "Ver nota"
        acao = {"tipo": "ver", "rotulo": rotulo_acao, "url": url}
    return {
        "nota": nota,
        "numero": documento.numero,
        "serie": documento.serie,
        "modelo": documento.get_modelo_display(),
        "emissao": documento.dh_emissao,
        "valor_nf_ptbr": _valor_ptbr(documento.v_nf),
        "situacao": rotulo,
        "destaque": situacao == servico_nfe.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA,
        "leitura": _ROTULO_LEITURA_NFE.get(nota.leitura_estado, "Ainda não lida"),
        "leitura_motivo": nota.leitura_motivo or "",
        "ilegivel": ilegivel,
        "acao": acao,
    }


# Tela 1 — arquétipo A (tabela de consulta): notas do mês a escriturar.


@login_required
@require_safe
@_entrada_nfe_verificada
def nfe_a_escriturar(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_ESCRITURACAO_NFE)

    empresa = _empresa_nfe_do_campo(request, request.GET.get("empresa"))
    ano, mes = _competencia_nfe(request)
    pode = _pode_escriturar(request)
    url_reclassificar = reverse("fiscal_web:nfe_reclassificar")
    if empresa is not None:
        url_reclassificar += f"?{urlencode({'empresa': empresa.pk})}"
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "pode_escriturar": pode,
        "pagina": None,
        "linhas": [],
        "url_reclassificar": url_reclassificar,
        "url_conferencia": reverse("fiscal_web:nfe_conferencia"),
    }
    if empresa is None:
        return render(request, "fiscal/nfe_a_escriturar.html", contexto)

    notas = servico_nfe.notas_do_mes(empresa, ano, mes)
    # Desempate determinístico: o serviço já ordena por dhEmi e documento_id; a paginação
    # só corta essa ordem.
    elegiveis = [nota for nota in notas if nota.tipo is not None]
    pagina = Paginator(elegiveis, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    estornadas = _vinculos_com_estorno([nota.vinculo.pk for nota in pagina.object_list])
    contexto.update(
        {
            "pagina": pagina,
            "linhas": [
                _linha_nfe_a_escriturar(nota, empresa, pode, estornadas)
                for nota in pagina.object_list
            ],
            "total_elegiveis": len(elegiveis),
            "fora_da_escrituracao": len(notas) - len(elegiveis),
            "querystring_sem_pagina": _querystring_sem_pagina(request),
        }
    )
    return render(request, "fiscal/nfe_a_escriturar.html", contexto)


# Tela 2 — arquétipo B (formulário de documento): escriturar uma nota.

_CONTRATO_ESCRITURAR_NFE = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "acao", "item_id", "natureza", "sinal"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na escrituração de NF-e",
)


def _opcoes_de_natureza(tipo):
    return [
        (valor, NaturezaOperacaoNFe(valor).label)
        for valor in sorted(
            servico_nfe.naturezas_permitidas(tipo), key=lambda v: NaturezaOperacaoNFe(v).label
        )
    ]


def _linha_do_item_nfe(item, natureza, documento, tipo):
    """Uma linha de item. CFOP (texto da tabela oficial), CST/CSOSN, NCM, valor, receita, natureza
    gravada e sugestão com o motivo que o serviço deu. Sem sugestão, a tela diz "escolha"."""
    sugestao = servico_nfe.sugerir_natureza_item(documento, item, tipo)
    info = consultar_cfop(item.cfop)
    if item.csosn:
        cst_csosn = f"CSOSN {item.csosn}"
    elif item.cst:
        cst_csosn = f"CST {item.cst}"
    else:
        cst_csosn = "—"
    return {
        "item_id": item.pk,
        "n_item": item.n_item,
        "x_prod": item.x_prod,
        "ncm": item.ncm,
        "cfop": item.cfop,
        "cfop_descricao": (
            info.descricao if info else "CFOP fora da tabela oficial: a classificar"
        ),
        "cst_csosn": cst_csosn,
        "v_prod_ptbr": _valor_ptbr(item.v_prod),
        "receita_ptbr": (
            _valor_ptbr(item.receita_bruta_item) if item.ind_tot == "1" else "fora do total"
        ),
        "natureza_gravada": natureza,
        "natureza_gravada_rotulo": NaturezaOperacaoNFe(natureza).label if natureza else "",
        "sugestao": sugestao.natureza or "",
        "sugestao_rotulo": (
            NaturezaOperacaoNFe(sugestao.natureza).label
            if sugestao.natureza
            else "sem sugestão — escolha"
        ),
        "sugestao_motivo": sugestao.motivo,
        "opcoes": _opcoes_de_natureza(tipo),
        "selecionada": natureza or sugestao.natureza or "",
    }


def _grupos_de_sinal(linhas):
    """Itens SEM natureza confirmada, agrupados pela sugestão: o bloco confirma um grupo inteiro."""
    contagem: dict[str, int] = {}
    for linha in linhas:
        if linha["natureza_gravada"] or not linha["sugestao"]:
            continue
        contagem[linha["sugestao"]] = contagem.get(linha["sugestao"], 0) + 1
    return [
        {"sinal": sinal, "rotulo": NaturezaOperacaoNFe(sinal).label, "quantidade": quantidade}
        for sinal, quantidade in sorted(contagem.items())
    ]


# Mensagem de divergência com o vNF, em pt-BR. A do serviço traz os valores com ponto decimal
# ("2880.00"), que não é a forma que o contador lê: a tela diz a mesma coisa e mostra os valores
# na tabela da conferência.
_MOTIVO_NAO_CONFERE_NFE = (
    "A receita dos itens não confere com o valor da nota (vNF). "
    "A nota não é efetivada: veja a conferência com o vNF."
)


def _pares_da_escrituracao(documento, escrituracao):
    """(item, natureza) de cada item da nota. Sem escrituração, todos sem natureza ainda."""
    if escrituracao is None:
        return [
            (item, "") for item in ItemNFe.objects.filter(documento=documento).order_by("n_item")
        ]
    registros = (
        NaturezaItemNFe.objects.select_related("item")
        .filter(escrituracao=escrituracao)
        .order_by("item__n_item")
    )
    return [(registro.item, registro.natureza or "") for registro in registros]


def _estado_da_efetivacao(documento, leitura, escrituracao, pares, cancelada):
    """(pode, motivo, conferência, divergiu). Efetivar só se habilita quando o serviço aceitaria: a
    checagem é a do próprio serviço (`conferir_valores`, função pura, sem gravar). O servidor
    recusa de novo no POST, por mais que o botão esteja habilitado."""
    if escrituracao is None or escrituracao.estado != EstadoEscrituracao.RASCUNHO:
        return False, "", None, False
    if cancelada:
        return False, "Nota cancelada não pode ser efetivada.", None, False
    if leitura is None or leitura.estado != LeituraItensNFe.ESTADO_LIDA:
        motivo = "itens ainda não lidos" if leitura is None else leitura.motivo
        return False, f"Itens ilegíveis, nota bloqueada: {motivo}", None, False
    faltam = sum(1 for _, natureza in pares if not natureza)
    if faltam:
        return (
            False,
            f"Falta a natureza de {faltam} item(ns). Confirme a natureza de cada item.",
            None,
            False,
        )
    try:
        conferencia = servico_nfe.conferir_valores(documento, leitura, pares)
    except servico_nfe.DivergenciaComVnf:
        return False, _MOTIVO_NAO_CONFERE_NFE, None, True
    except servico_nfe.EscrituracaoNFeErro as exc:
        # Bloqueios que nomeiam a regra (PE-85, vNF ausente, versão do leitor): a mensagem do
        # serviço
        # é a que o contador precisa ver, e não a de divergência.
        return False, exc.mensagem, None, False
    return True, "", conferencia, False


def _recusa_previa_da_efetivacao(vinculo, escrituracao):
    """Motivo da recusa ANTES de chamar o serviço, em pt-BR, ou `None` se a checagem passa. O
    serviço continua sendo a autoridade: ele confere tudo de novo, dentro da transação."""
    documento = vinculo.documento
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    pode, motivo, _, _ = _estado_da_efetivacao(
        documento,
        leitura,
        escrituracao,
        _pares_da_escrituracao(documento, escrituracao),
        situacao_da_nfe(documento) == "cancelada",
    )
    return None if pode else motivo


def _conferencia_na_tela(documento, leitura, pares, escrituracao, efetivada, conferencia):
    """Componentes do vNF em pt-BR. Efetivada: soma e vNF são os GRAVADOS. Rascunho conferido: os
    que o serviço devolveu. Rascunho recusado: a soma dos itens sai da mesma regra de receita, só
    para exibir. Tributos fora da receita são os da nota; ausente fica traço, nunca zero."""
    if efetivada and escrituracao is not None:
        soma, valor_nf = escrituracao.soma_itens, escrituracao.valor_nf
    elif conferencia is not None:
        soma, valor_nf = conferencia.soma_itens, conferencia.valor_nf
    else:
        soma = sum(
            (item.receita_bruta_item for item, _ in pares if item.ind_tot == "1"),
            Decimal("0.00"),
        )
        valor_nf = documento.v_nf
    return {
        "receita_ptbr": _valor_ptbr(soma),
        "vnf_ptbr": _valor_ptbr(valor_nf),
        "vst_ptbr": _valor_ptbr(documento.v_st),
        "vipi_ptbr": _valor_ptbr(documento.v_ipi),
        "vii_ptbr": _valor_ptbr(leitura.v_ii if leitura else None),
        "vipi_devol_ptbr": _valor_ptbr(leitura.v_ipi_devol if leitura else None),
    }


def _tela_de_escriturar_nfe(request, empresa, vinculo, *, status=200):
    documento = vinculo.documento
    _, competencia = servico_nfe.dia_e_competencia(documento)
    tipo = servico_nfe.tipo_da_nota(documento, vinculo.papel)
    leitura = LeituraItensNFe.objects.filter(documento=documento).first()
    escrituracao = _escrituracao_ativa_nfe(vinculo)
    # A nota é buscada direto pelo vínculo, sem listar o mês inteiro (DL-081, A6).
    nota = servico_nfe.nota_do_vinculo(empresa, vinculo)
    lida = leitura is not None and leitura.estado == LeituraItensNFe.ESTADO_LIDA
    cancelada = situacao_da_nfe(documento) == "cancelada"
    pode = _pode_escriturar(request)

    linhas: list[dict] = []
    pares: list[tuple] = []
    if lida and tipo is not None:
        pares = _pares_da_escrituracao(documento, escrituracao)
        tipo_da_tela = escrituracao.tipo if escrituracao is not None else tipo
        linhas = [
            _linha_do_item_nfe(item, natureza, documento, tipo_da_tela) for item, natureza in pares
        ]

    pode_efetivar, motivo_efetivar, conferencia, divergiu = (
        _estado_da_efetivacao(documento, leitura, escrituracao, pares, cancelada)
        if pares
        else (False, "", None, False)
    )
    rascunho = escrituracao is not None and escrituracao.estado == EstadoEscrituracao.RASCUNHO
    efetivada = escrituracao is not None and escrituracao.estado == EstadoEscrituracao.EFETIVADA
    contexto = {
        "empresa": empresa,
        "vinculo": vinculo,
        "documento": documento,
        "papel_rotulo": _ROTULO_PAPEL_NFE[vinculo.papel],
        "modelo_rotulo": documento.get_modelo_display(),
        "chave_em_grupos": _chave_em_grupos(documento.chave),
        "tp_nf_rotulo": _ROTULO_TP_NF.get(documento.tp_nf, documento.tp_nf),
        "fin_nfe_rotulo": _ROTULO_FIN_NFE.get(documento.fin_nfe, documento.fin_nfe),
        "emissao": documento.dh_emissao,
        "competencia_rotulo": f"{competencia.month:02d}/{competencia.year}",
        "emitente_documento": _documento_na_tela(
            documento.emitente_tipo_documento, documento.emitente_documento
        ),
        "destinatario_documento": _documento_na_tela(
            documento.destinatario_tipo_documento, documento.destinatario_documento
        ),
        "valor_nf_ptbr": _valor_ptbr(documento.v_nf),
        "nota": nota,
        "situacao_rotulo": (
            _ROTULO_SITUACAO_NFE_ESCRITURACAO.get(nota.situacao, nota.situacao)
            if nota is not None
            else ""
        ),
        "fora_motivo": (
            None
            if tipo is not None
            else servico_nfe.motivo_fora_da_escrituracao(documento, vinculo.papel)
        ),
        "escrituracao": escrituracao,
        "rascunho": rascunho,
        "efetivada": efetivada,
        "lida": lida,
        "leitura_rotulo": _ROTULO_LEITURA_NFE.get(
            leitura.estado if leitura else None, "Ainda não lida"
        ),
        "leitura_motivo": leitura.motivo if leitura else "",
        "avisos": servico_nfe.avisos_ibscbs(documento, leitura),
        "pode_escriturar": pode,
        "linhas": linhas,
        "grupos_de_sinal": _grupos_de_sinal(linhas) if rascunho and pode else [],
        "pendentes": sum(1 for _, natureza in pares if not natureza),
        "pode_efetivar": pode_efetivar,
        "motivo_efetivar": motivo_efetivar,
        "conferencia": (
            _conferencia_na_tela(documento, leitura, pares, escrituracao, efetivada, conferencia)
            if pares and (rascunho or efetivada)
            else None
        ),
        "conferencia_divergiu": divergiu,
        "segregacao": (
            [
                {
                    "rotulo": _ROTULO_SEGREGACAO_NFE[chave],
                    "valor_ptbr": _valor_ptbr(valor),
                }
                for chave, valor in servico_nfe.segregacao_da_escrituracao(escrituracao).items()
            ]
            if efetivada or rascunho
            else []
        ),
        "url_lista": (
            reverse("fiscal_web:nfe_a_escriturar")
            + "?"
            + urlencode({"empresa": empresa.pk, "ano": competencia.year, "mes": competencia.month})
        ),
        "url_estornar": (
            reverse("fiscal_web:nfe_estornar", args=[empresa.pk, escrituracao.pk])
            if efetivada and escrituracao is not None
            else ""
        ),
        "url_escriturar": reverse("fiscal_web:nfe_escriturar", args=[empresa.pk, vinculo.pk]),
    }
    return render(request, "fiscal/nfe_escriturar.html", contexto, status=status)


def _redirecionar_escriturar_nfe(empresa, vinculo):
    return redirect("fiscal_web:nfe_escriturar", empresa_id=empresa.pk, vinculo_id=vinculo.pk)


def _itens_com_sugestao_pendente(documento, escrituracao, sinal):
    """Itens SEM natureza confirmada cuja sugestão é `sinal`: o alvo do bloco é escolhido aqui,
    no servidor, pelo mesmo serviço de sugestão. O cliente não envia lista de itens."""
    registros = NaturezaItemNFe.objects.select_related("item").filter(
        escrituracao=escrituracao, natureza=""
    )
    return [
        registro.item_id
        for registro in registros
        if servico_nfe.sugerir_natureza_item(documento, registro.item, escrituracao.tipo).natureza
        == sinal
    ]


def _escriturar_nfe_post(request, empresa, vinculo):
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESCRITURAR_NFE)
    except DadoNaoContratado as exc:
        raise _EntradaNfeRecusada(exc.mensagem) from exc
    acao = request.POST.get("acao", "")
    if acao not in _ACOES_ESCRITURAR_NFE:
        raise _EntradaNfeRecusada("Ação desconhecida na escrituração de NF-e.")

    try:
        if acao == "criar":
            escrituracao = servico_nfe.criar_rascunho(
                vinculo, usuario=request.user, request=request
            )
            if escrituracao.criada_agora:
                messages.success(
                    request, "Rascunho criado. Confirme a natureza de cada item e efetive."
                )
            else:
                messages.info(request, "Esta nota já tinha rascunho. Nada foi alterado.")
            return _redirecionar_escriturar_nfe(empresa, vinculo)

        escrituracao = _escrituracao_ativa_nfe(vinculo)
        if escrituracao is None:
            raise servico_nfe.EscrituracaoNFeErro(
                "Esta nota não tem rascunho. Crie o rascunho antes de confirmar naturezas."
            )
        if acao == "efetivar":
            # Recusa em pt-BR antes do serviço, que continua a autoridade (ver `_recusa_previa`).
            recusa = _recusa_previa_da_efetivacao(vinculo, escrituracao)
            if recusa:
                messages.error(request, recusa)
                return _tela_de_escriturar_nfe(request, empresa, vinculo, status=409)
            efetivada = servico_nfe.efetivar(escrituracao, usuario=request.user, request=request)
            if efetivada.criada_agora:
                messages.success(
                    request, "Escrituração efetivada. A receita do mês foi atualizada."
                )
            else:
                messages.info(request, "Esta escrituração já estava efetivada. Nada foi alterado.")
        elif acao == "item":
            item_id = _id_do_formulario_nfe(request.POST.get("item_id"), "Item")
            natureza = _texto_nfe(request.POST.get("natureza"), "Natureza", _TAMANHO_NATUREZA_NFE)
            servico_nfe.definir_natureza(
                escrituracao, natureza, [item_id], usuario=request.user, request=request
            )
            messages.success(request, "Natureza do item confirmada.")
        else:  # bloco
            sinal = _texto_nfe(request.POST.get("sinal"), "Sinal", _TAMANHO_NATUREZA_NFE)
            ids = _itens_com_sugestao_pendente(vinculo.documento, escrituracao, sinal)
            if not ids:
                raise servico_nfe.EntradaInvalidaNFe(
                    "Nenhum item sem natureza confirmada tem esta sugestão."
                )
            servico_nfe.definir_natureza(
                escrituracao, sinal, ids, usuario=request.user, request=request
            )
            messages.success(
                request, f"Natureza confirmada em {len(ids)} item(ns) com a mesma sugestão."
            )
    except servico_nfe.EntradaInvalidaNFe as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar_nfe(request, empresa, vinculo, status=400)
    except servico_nfe.EscrituracaoNFeErro as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_escriturar_nfe(request, empresa, vinculo, status=409)
    return _redirecionar_escriturar_nfe(empresa, vinculo)


@login_required
@require_http_methods(["GET", "POST"])
@_entrada_nfe_verificada
def nfe_escriturar(request, empresa_id, vinculo_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    # POST é escrita: quem só consulta (PARALEGAL, CLIENTE) recebe 403, mesmo sem botão na tela.
    if request.method == "POST":
        if not _pode_escriturar(request):
            return _resposta_sem_permissao(request, _MENSAGEM_SEM_ESCRITA_NFE)
    elif not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_ESCRITURACAO_NFE)
    empresa = _empresa_nfe_da_rota(request, empresa_id)
    vinculo = _vinculo_nfe_da_empresa(request, empresa, vinculo_id)
    if request.method == "POST":
        return _escriturar_nfe_post(request, empresa, vinculo)
    return _tela_de_escriturar_nfe(request, empresa, vinculo)


# Tela 3 — arquétipo E (confirmação de ação sensível): estornar, com motivo.

_CONTRATO_ESTORNAR_NFE = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken", "motivo"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no estorno da escrituração de NF-e",
)


def _tela_de_estornar_nfe(request, empresa, escrituracao, *, motivo, status=200):
    contexto = {
        "empresa": empresa,
        "escrituracao": escrituracao,
        "documento": escrituracao.vinculo.documento,
        "efetivada": escrituracao.estado == EstadoEscrituracao.EFETIVADA,
        "estado_rotulo": escrituracao.get_estado_display(),
        "competencia_rotulo": (
            f"{escrituracao.competencia.month:02d}/{escrituracao.competencia.year}"
            if escrituracao.competencia
            else "—"
        ),
        "receita_ptbr": _valor_ptbr(escrituracao.receita_bruta),
        "devolucao_ptbr": _valor_ptbr(escrituracao.devolucao),
        "motivo": motivo,
        "motivo_maximo": servico_nfe.MOTIVO_MAXIMO,
        "url_detalhe": reverse(
            "fiscal_web:nfe_escriturar",
            args=[empresa.pk, escrituracao.vinculo_id],
        ),
    }
    return render(request, "fiscal/nfe_estornar.html", contexto, status=status)


@login_required
@require_http_methods(["GET", "POST"])
@_entrada_nfe_verificada
def nfe_estornar(request, empresa_id, escrituracao_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_ESCRITA_NFE)
    empresa = _empresa_nfe_da_rota(request, empresa_id)
    escrituracao = _escrituracao_nfe_da_empresa(request, empresa, escrituracao_id)
    if request.method == "GET":
        return _tela_de_estornar_nfe(request, empresa, escrituracao, motivo="")

    try:
        recusar_dado_nao_contratado(request, _CONTRATO_ESTORNAR_NFE)
    except DadoNaoContratado as exc:
        raise _EntradaNfeRecusada(exc.mensagem) from exc
    # O tamanho e o motivo vazio são do serviço (EntradaInvalidaNFe, 400). Aqui só o byte nulo.
    motivo = _texto_seguro_nfe(request.POST.get("motivo"), "Motivo do estorno")
    try:
        servico_nfe.estornar(escrituracao, motivo, usuario=request.user, request=request)
    except servico_nfe.EntradaInvalidaNFe as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_nfe(request, empresa, escrituracao, motivo=motivo, status=400)
    except servico_nfe.EscrituracaoNFeErro as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_estornar_nfe(request, empresa, escrituracao, motivo=motivo, status=409)
    messages.success(
        request, "Escrituração estornada. A nota voltou para a lista, a escriturar de novo."
    )
    return redirect(
        "fiscal_web:nfe_escriturar",
        empresa_id=empresa.pk,
        vinculo_id=escrituracao.vinculo_id,
    )


# Tela 4 — arquétipo E: reclassificação em massa, com prévia e confirmação.

_CONTRATO_RECLASSIFICAR_NFE = ContratoDeRequisicao(
    campos={
        "csrfmiddlewaretoken",
        "acao",
        "empresa",
        "natureza",
        "inicio",
        "fim",
        "cfop",
        "cst_csosn",
        "ncm",
        "previstas_notas",
        "previstos_itens",
        "previstas_assinatura",
    },
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reclassificação em massa de NF-e",
)


def _filtros_da_reclassificacao(post):
    inicio = _data_nfe(post.get("inicio"), "Período de")
    fim = _data_nfe(post.get("fim"), "Período até")
    if inicio and fim and inicio > fim:
        raise _EntradaNfeRecusada("'Período de' não pode ser posterior a 'Período até'.")
    return servico_nfe.FiltrosReclassificacao(
        inicio=inicio,
        fim=fim,
        cfop=_codigo_fiscal_nfe(post.get("cfop"), "CFOP", r"[0-9]{4}", "exatamente 4 dígitos"),
        cst_csosn=_codigo_fiscal_nfe(
            post.get("cst_csosn"), "CST/CSOSN", r"[0-9]{2,3}", "2 ou 3 dígitos"
        ),
        ncm=_codigo_fiscal_nfe(post.get("ncm"), "NCM", r"[0-9]{8}", "exatamente 8 dígitos"),
    )


def _valores_da_reclassificacao(post):
    """Valores digitados, de volta ao formulário (só após a validação de formato)."""
    return {
        "natureza": _texto_nfe(post.get("natureza"), "Natureza", _TAMANHO_NATUREZA_NFE),
        "inicio": _texto_nfe(post.get("inicio"), "Período de", 10),
        "fim": _texto_nfe(post.get("fim"), "Período até", 10),
        "cfop": _texto_nfe(post.get("cfop"), "CFOP", 8),
        "cst_csosn": _texto_nfe(post.get("cst_csosn"), "CST/CSOSN", 8),
        "ncm": _texto_nfe(post.get("ncm"), "NCM", 8),
    }


def _tela_de_reclassificar_nfe(request, empresa, *, valores, previa=None, status=200):
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa": empresa,
        "valores": valores,
        "opcoes_de_natureza": sorted(NaturezaOperacaoNFe.choices, key=lambda opcao: opcao[1]),
        "previa": previa,
        "url_lista": reverse("fiscal_web:nfe_a_escriturar"),
    }
    return render(request, "fiscal/nfe_reclassificar.html", contexto, status=status)


def _previa_da_reclassificacao(empresa, natureza, filtros, request):
    """Prévia: roda o SERVIÇO de verdade e desfaz tudo no fim. Assim a contagem é a que a
    confirmação gravaria, sem uma segunda regra de filtro na tela. Nada persiste."""
    with transaction.atomic():
        resultado = servico_nfe.reclassificar_em_massa(
            empresa, natureza, filtros, usuario=request.user, request=request
        )
        transaction.set_rollback(True)
    return resultado


def _reclassificar_nfe_post(request):
    try:
        recusar_dado_nao_contratado(request, _CONTRATO_RECLASSIFICAR_NFE)
    except DadoNaoContratado as exc:
        raise _EntradaNfeRecusada(exc.mensagem) from exc
    acao = request.POST.get("acao", "")
    if acao not in _ACOES_RECLASSIFICAR_NFE:
        raise _EntradaNfeRecusada("Ação desconhecida na reclassificação.")
    empresa = _empresa_nfe_do_campo(request, request.POST.get("empresa"))
    if empresa is None:
        raise _EntradaNfeRecusada("Escolha uma empresa para reclassificar.")
    filtros = _filtros_da_reclassificacao(request.POST)
    valores = _valores_da_reclassificacao(request.POST)
    natureza = valores["natureza"]

    if acao == "previa":
        try:
            resultado = _previa_da_reclassificacao(empresa, natureza, filtros, request)
        except servico_nfe.EntradaInvalidaNFe as exc:
            messages.error(request, exc.mensagem)
            return _tela_de_reclassificar_nfe(request, empresa, valores=valores, status=400)
        previa = {
            "notas": resultado.escrituracoes_afetadas,
            "itens": resultado.itens_alterados,
            # Assinatura dos pares alterados: a confirmação recusa se o conjunto mudou (A10).
            "assinatura": resultado.assinatura,
            "natureza_rotulo": NaturezaOperacaoNFe(natureza).label
            if natureza in NaturezaOperacaoNFe.values
            else natureza,
        }
        return _tela_de_reclassificar_nfe(request, empresa, valores=valores, previa=previa)

    previstas_notas = _contagem_do_formulario_nfe(request.POST.get("previstas_notas"), "Notas")
    previstos_itens = _contagem_do_formulario_nfe(request.POST.get("previstos_itens"), "Itens")
    previstas_assinatura = request.POST.get("previstas_assinatura", "")
    divergiu = False
    try:
        with transaction.atomic():
            resultado = servico_nfe.reclassificar_em_massa(
                empresa, natureza, filtros, usuario=request.user, request=request
            )
            # A confirmação só grava o que a prévia mostrou. Se os dados mudaram, desfaz tudo. A
            # comparação é pela assinatura do conjunto (A10): contagens iguais não bastam, porque
            # uma nota pode sair e outra entrar, com o mesmo total.
            if (
                resultado.escrituracoes_afetadas,
                resultado.itens_alterados,
                resultado.assinatura,
            ) != (previstas_notas, previstos_itens, previstas_assinatura):
                transaction.set_rollback(True)
                divergiu = True
    except servico_nfe.EntradaInvalidaNFe as exc:
        messages.error(request, exc.mensagem)
        return _tela_de_reclassificar_nfe(request, empresa, valores=valores, status=400)
    if divergiu:
        messages.error(
            request,
            "Os dados mudaram desde a prévia: nada foi alterado. "
            "Refaça a prévia antes de confirmar.",
        )
        return _tela_de_reclassificar_nfe(request, empresa, valores=valores, status=409)
    messages.success(
        request,
        f"Reclassificados {resultado.itens_alterados} item(ns) em "
        f"{resultado.escrituracoes_afetadas} nota(s) em rascunho.",
    )
    return redirect(
        f"{reverse('fiscal_web:nfe_reclassificar')}?{urlencode({'empresa': empresa.pk})}"
    )


@login_required
@require_http_methods(["GET", "POST"])
@_entrada_nfe_verificada
def nfe_reclassificar(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_ESCRITA_NFE)
    if request.method == "POST":
        return _reclassificar_nfe_post(request)
    empresa = _empresa_nfe_do_campo(request, request.GET.get("empresa"))
    valores = {"natureza": "", "inicio": "", "fim": "", "cfop": "", "cst_csosn": "", "ncm": ""}
    return _tela_de_reclassificar_nfe(request, empresa, valores=valores)


# Tela 5 — arquétipo C (conferência do mês). Relatório de CONFERÊNCIA (classe 1 da
# personalização de relatório): só leitura, nenhum valor é recalculado aqui.


@login_required
@require_safe
@_entrada_nfe_verificada
def nfe_conferencia(request):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    if not _pode_consultar(request):
        return _resposta_sem_permissao(request, _MENSAGEM_SEM_CONSULTA_ESCRITURACAO_NFE)
    empresa = _empresa_nfe_do_campo(request, request.GET.get("empresa"))
    ano, mes = _competencia_nfe(request)
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "url_lista": reverse("fiscal_web:nfe_a_escriturar"),
    }
    if empresa is None:
        return render(request, "fiscal/nfe_conferencia.html", contexto)

    conferencia = servico_nfe.conferencia_do_mes(empresa, ano, mes)
    composicao = servico_receita.composicao_do_mes(empresa, ano, mes)
    notas = conferencia.notas
    naturezas = sorted(
        conferencia.receita_por_natureza.items(),
        key=lambda par: NaturezaOperacaoNFe(par[0]).label,
    )
    total_nfe = sum((linha["soma_na_receita"] for _, linha in naturezas), Decimal("0.00"))
    contexto.update(
        {
            "situacao": [
                {"rotulo": "Recebidas no mês (elegíveis)", "quantidade": conferencia.recebidas},
                {"rotulo": "Escrituradas e efetivadas", "quantidade": conferencia.escrituradas},
                {
                    "rotulo": "Pendentes (sem escrituração ou em rascunho)",
                    "quantidade": conferencia.pendentes,
                },
                {"rotulo": "Canceladas (total)", "quantidade": conferencia.canceladas},
                {
                    "rotulo": "Canceladas depois de escriturada",
                    "quantidade": conferencia.escrituradas_canceladas,
                    "destaque": True,
                },
                {
                    "rotulo": "Itens sem sugestão de natureza (em nota a escriturar)",
                    "quantidade": conferencia.itens_sem_sugestao,
                },
                {
                    "rotulo": "Fora da escrituração (compra, ajuste e outras)",
                    "quantidade": conferencia.nao_elegiveis,
                },
            ],
            "receita_de_natureza": [
                {
                    "rotulo": NaturezaOperacaoNFe(natureza).label,
                    "papel": _ROTULO_PAPEL_NATUREZA_NFE[linha["papel"]],
                    "mercado": _ROTULO_MERCADO_NFE[linha["mercado"]],
                    "bruto_ptbr": _valor_ptbr(linha["bruto"]),
                    "soma_ptbr": _valor_ptbr(linha["soma_na_receita"]),
                }
                for natureza, linha in naturezas
                if linha["papel"] != "nao_receita"
            ],
            "sem_receita": [
                {
                    "rotulo": NaturezaOperacaoNFe(natureza).label,
                    "bruto_ptbr": _valor_ptbr(linha["bruto"]),
                }
                for natureza, linha in naturezas
                if linha["papel"] == "nao_receita"
            ],
            "total_nfe_ptbr": _valor_ptbr(total_nfe),
            "valor_por_cfop": [
                {"cfop": cfop, "valor_ptbr": _valor_ptbr(valor)}
                for cfop, valor in sorted(conferencia.valor_bruto_por_cfop.items())
            ],
            "composicao": [
                {
                    "mercado": _ROTULO_MERCADO_NFE[mercado.mercado],
                    "mercadoria_ptbr": _valor_ptbr(mercado.mercadoria),
                    "devolucao_ptbr": _valor_ptbr(mercado.devolucao),
                    "saldo_entrada_ptbr": _valor_ptbr(mercado.saldo_entrada),
                    "deduzido_ptbr": _valor_ptbr(mercado.deduzido),
                    "saldo_transportado_ptbr": _valor_ptbr(mercado.saldo_transportado),
                }
                for mercado in (composicao.interno, composicao.externo)
            ],
            "canceladas_depois": [
                _linha_nfe_a_escriturar(nota, empresa, False, set())
                for nota in notas
                if nota.situacao == servico_nfe.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA
            ],
        }
    )
    return render(request, "fiscal/nfe_conferencia.html", contexto)
