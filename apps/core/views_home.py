"""Portas autenticadas e somente de leitura da home de módulos (DL-049)."""

import re

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe

from apps.core.module_homes import (
    FiltroHomeInvalido,
    menu_modulos,
    modulo_conhecido,
    montar_home,
    pode_ler_modulo,
    resolver_escopo,
)


def _responder(request, modulo, *, lista=False):
    definicao = modulo_conhecido(modulo)
    template = "core/module_queue.html" if lista else "core/module_home.html"
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    if not pode_ler_modulo(request.papel, modulo):
        # A recusa vem ANTES do seletor plural e da apuração. Não passa
        # nomes, totais nem valores para a renderização de um 403.
        return render(
            request,
            template,
            {
                "home": {
                    "modulo": definicao,
                    "estado": "sem_permissao",
                    "modulos_navigation": menu_modulos(request),
                    "vazio": {
                        "titulo": "Seu perfil não permite consultar este módulo.",
                        "texto": (
                            "Os dados das empresas não foram consultados. Escolha uma área "
                            "permitida no menu."
                        ),
                    },
                }
            },
            status=403,
        )
    try:
        escopo = resolver_escopo(request, modulo)
        bruto_pagina = request.GET.get("pagina", "1")
        if not re.fullmatch(r"[1-9][0-9]{0,6}", bruto_pagina):
            raise FiltroHomeInvalido("Informe uma página válida da lista.")
        estado = request.GET.get("estado", "") if lista else ""
        home = montar_home(
            request,
            escopo,
            estado=estado,
            pagina=int(bruto_pagina) if lista else 1,
            tamanho=25 if lista else 8,
        )
    except FiltroHomeInvalido as exc:
        return render(
            request,
            template,
            {
                "home": {
                    "modulo": definicao,
                    "estado": "filtro_invalido",
                    "modulos_navigation": menu_modulos(request),
                    "vazio": {"titulo": "Não foi possível aplicar os filtros.", "texto": str(exc)},
                }
            },
            status=400,
        )
    request._module_home_context = home
    return render(request, template, {"home": home})


@login_required
@require_safe
def home_modulo(request, modulo):
    """Primeira tela do módulo, preservando empresa e competência autorizadas."""
    return _responder(request, modulo)


@login_required
@require_safe
def pendencias_modulo(request, modulo):
    """Lista paginada do mesmo indicador; cada estado é validado no servidor."""
    return _responder(request, modulo, lista=True)
