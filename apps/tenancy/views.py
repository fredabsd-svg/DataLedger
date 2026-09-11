from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.models import Escritorio


class MeusEscritoriosView(APIView):
    """Lista os escritórios aos quais o usuário autenticado tem vínculo ativo.

    Isolamento: o filtro é sempre por vínculo do usuário autenticado, nunca
    por um identificador recebido do cliente.
    """

    def get(self, request):
        escritorios = Escritorio.objects.filter(
            vinculos__usuario=request.user, vinculos__ativo=True
        ).distinct()
        return Response([{"id": e.id, "nome": e.nome, "cnpj": e.cnpj} for e in escritorios])


class EscritorioAtivoView(APIView):
    """Consulta ou define o escritório ativo na sessão do usuário."""

    def get(self, request):
        if request.escritorio is None:
            return Response({"escritorio_ativo": None})
        return Response(
            {
                "escritorio_ativo": {
                    "id": request.escritorio.id,
                    "nome": request.escritorio.nome,
                    "papel": request.papel,
                }
            }
        )

    def post(self, request):
        escritorio_id = request.data.get("escritorio_id")

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado.
        tem_vinculo = request.user.vinculos.filter(escritorio_id=escritorio_id, ativo=True).exists()
        if not tem_vinculo:
            return Response({"detail": "Escritório inválido ou sem vínculo ativo."}, status=403)

        request.session["escritorio_id"] = int(escritorio_id)
        return Response({"status": "ok"})


@login_required
def painel(request):
    """Página inicial pós-login: mostra o escritório ativo e permite trocar.

    Fluxo simples com formulário HTML padrão nesta etapa; HTMX/Alpine
    entram quando houver necessidade real de atualização parcial de
    página, evitando complexidade sem uso imediato.
    """
    escritorios = Escritorio.objects.filter(
        vinculos__usuario=request.user, vinculos__ativo=True
    ).distinct()
    return render(
        request,
        "tenancy/painel.html",
        {"escritorios": escritorios, "escritorio_ativo": request.escritorio},
    )


@login_required
def ativar_escritorio(request):
    if request.method == "POST":
        escritorio_id = request.POST.get("escritorio_id")
        tem_vinculo = request.user.vinculos.filter(escritorio_id=escritorio_id, ativo=True).exists()
        if tem_vinculo:
            request.session["escritorio_id"] = int(escritorio_id)
    return redirect("tenancy:painel")
