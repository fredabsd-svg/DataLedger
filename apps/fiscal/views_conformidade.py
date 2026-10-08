"""Tela de conferência IBS/CBS das NFS-e recebidas — DL-073, modo AVISO.

Relatório de CONFERÊNCIA (classe 1 da personalização de relatório): aponta
indícios para revisão, não decide conformidade. Arquétipo A/C da direção de
arte (tabela de consulta com a situação e os avisos escritos em texto).

Regras que esta view cumpre, na mesma ordem de `apps.fiscal.views_web`:

- Permissão no SERVIDOR: `papel_pode_consultar_documentos` (fonte única em
  `apps.fiscal.permissoes`); papel CLIENTE recebe 403.
- Isolamento: a empresa é buscada com `get_object_or_404` filtrado pelo
  escritório ativo. Empresa de outro escritório dá 404, sem confirmar que o
  ID existe.
- Entrada inválida (empresa malformada, competência fora de faixa) dá 400
  com a mensagem em português, nunca 500.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_safe

from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.empresas.models import Empresa
from apps.fiscal.ibscbs import DATA_OBRIGATORIEDADE, SITUACAO_LEIAUTE_SEM_GRUPO, conformidade_do_mes
from apps.fiscal.permissoes import papel_pode_consultar_documentos

# Tamanho de página da tabela de notas. Não é regra de negócio; mesma
# convenção de `apps.fiscal.views_web.ITENS_POR_PAGINA`.
ITENS_POR_PAGINA = 25


def _inteiro_de_filtro(texto):
    """Só dígito ASCII, como em `apps.fiscal.views_web._inteiro_de_filtro`.
    Cópia pequena própria: não se importa função privada de outra view."""
    if not texto or not texto.isascii() or not texto.isdigit():
        return None
    return int(texto)


def _competencia_do_pedido(ano_bruto, mes_bruto):
    """(ano, mes) válidos, ou `(None, mensagem)`. A competência é obrigatória
    para a conferência: diferente de `documentos_lista`, aqui não há mês
    padrão implícito."""
    ano = _inteiro_de_filtro(ano_bruto)
    mes = _inteiro_de_filtro(mes_bruto)
    if ano is None or mes is None or mes < 1 or mes > 12 or ano < 2000 or ano > 2100:
        return None, "Competência inválida: informe um ano (AAAA) e um mês (1 a 12) válidos."
    return (ano, mes), None


def _querystring_sem_pagina(request):
    dados = request.GET.copy()
    dados.pop("pagina", None)
    return dados.urlencode()


@login_required
@require_safe
def conformidade_ibscbs(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    if not papel_pode_consultar_documentos(getattr(request, "papel", None)):
        return render(
            request,
            "erros/sem_permissao.html",
            {"mensagem": "Seu papel não permite consultar documentos fiscais."},
            status=403,
        )

    bruto_empresa = request.GET.get("empresa", "").strip()
    bruto_ano = request.GET.get("ano", "").strip()
    bruto_mes = request.GET.get("mes", "").strip()
    contexto = {
        "empresas_do_escritorio": Empresa.objects.filter(escritorio=request.escritorio).order_by(
            "razao_social"
        ),
        "empresa_filtro_bruto": bruto_empresa,
        "ano_filtro": bruto_ano,
        "mes_filtro": bruto_mes,
        "data_obrigatoriedade": DATA_OBRIGATORIEDADE,
        "situacao_leiaute_sem_grupo": SITUACAO_LEIAUTE_SEM_GRUPO,
    }

    if not bruto_empresa and not bruto_ano and not bruto_mes:
        # Entrada padrão: só o formulário e os avisos de leitura da tela.
        return render(request, "fiscal/conformidade_ibscbs.html", {**contexto, "consultado": False})

    erro = None
    empresa_id = None
    if not bruto_empresa:
        erro = "Escolha a empresa para conferir."
    else:
        try:
            empresa_id = para_id(bruto_empresa)
        except IdentificadorInvalido:
            erro = "'Empresa' inválida."
    competencia, erro_competencia = _competencia_do_pedido(bruto_ano, bruto_mes)
    erro = erro or erro_competencia
    if erro:
        messages.error(request, erro)
        return render(
            request,
            "fiscal/conformidade_ibscbs.html",
            {**contexto, "consultado": False},
            status=400,
        )

    # Isolamento: empresa de OUTRO escritório cai aqui em 404 (critério 10).
    empresa = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)
    ano, mes = competencia
    notas = conformidade_do_mes(empresa, ano, mes)
    pagina = Paginator(notas, ITENS_POR_PAGINA).get_page(request.GET.get("pagina"))
    contexto = {
        **contexto,
        "consultado": True,
        "empresa_selecionada": empresa,
        "competencia_texto": f"{mes:02d}/{ano}",
        "total_notas": len(notas),
        "total_com_aviso": sum(1 for nota in notas if nota.avisos),
        "total_leiaute_sem_grupo": sum(
            1 for nota in notas if nota.situacao == SITUACAO_LEIAUTE_SEM_GRUPO
        ),
        "pagina": pagina,
        "querystring_sem_pagina": _querystring_sem_pagina(request),
    }
    return render(request, "fiscal/conformidade_ibscbs.html", contexto)
