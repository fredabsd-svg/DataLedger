from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.tenancy.models import Escritorio


class MeusEscritoriosView(APIView):
    """Lista os escritórios aos quais o usuário autenticado tem vínculo ativo.

    Isolamento: o filtro é sempre por vínculo do usuário autenticado, nunca
    por um identificador recebido do cliente.

    `permission_classes` DECLARADO explicitamente (achado R3-10, auditoria
    DL-017 rodada 3): antes, esta view (e `EscritorioAtivoView`, abaixo) não
    declarava nada e dependia só de `REST_FRAMEWORK.DEFAULT_PERMISSION_
    CLASSES` (`config/settings.py`) para exigir autenticação — as ÚNICAS
    duas `APIView` do repositório nessa situação. Não havia vazamento (o
    padrão global já é `IsAuthenticated`), mas o risco é de MANUTENÇÃO:
    relaxar o padrão global para acrescentar uma rota pública no futuro
    tiraria a autenticação destas duas sem que nenhuma linha delas mudasse.
    `TemEscritorioAtivo` (usada no resto do projeto) NÃO serve aqui: as duas
    rotas existem justamente para o usuário CONSULTAR seus escritórios e
    definir/consultar o ativo — exigir um escritório já ativo seria
    impossível de satisfazer na primeira visita. `IsAuthenticated` é o
    mínimo correto, agora fixado na própria classe.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        escritorios = Escritorio.objects.filter(
            vinculos__usuario=request.user, vinculos__ativo=True
        ).distinct()
        return Response([{"id": e.id, "nome": e.nome, "cnpj": e.cnpj} for e in escritorios])


class EscritorioAtivoView(APIView):
    """Consulta ou define o escritório ativo na sessão do usuário.

    `permission_classes` declarado explicitamente pelo mesmo motivo de
    `MeusEscritoriosView` (achado R3-10) — ver o docstring dela.
    """

    permission_classes = [IsAuthenticated]

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
        # request.escritorio ainda reflete o valor de antes da troca (o
        # middleware já rodou nesta requisição): busca o novo explicitamente.
        registrar(
            acao="escritorio.ativado",
            usuario=request.user,
            escritorio=Escritorio.objects.get(pk=escritorio_id),
        )
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

        # BL-23: antes, um vínculo inexistente (ou um valor não numérico)
        # caía direto no redirecionamento sem avisar nada — o usuário achava
        # que a troca tinha funcionado. Agora todo caminho que não ativa
        # termina em mensagem de erro explícita. Validação por string (em
        # vez de try/except sobre int()) evita depender de exceção para um
        # caso de entrada tão comum quanto campo vazio ou valor não numérico.
        if not escritorio_id or not str(escritorio_id).isdigit():
            messages.error(request, "Escritório inválido.")
            return redirect("tenancy:painel")
        escritorio_id_valido = int(escritorio_id)

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado (mesma
        # regra de isolamento aplicada em EscritorioAtivoView.post).
        tem_vinculo = request.user.vinculos.filter(
            escritorio_id=escritorio_id_valido, ativo=True
        ).exists()
        if not tem_vinculo:
            messages.error(request, "Escritório inválido ou sem vínculo ativo com o seu usuário.")
            return redirect("tenancy:painel")

        request.session["escritorio_id"] = escritorio_id_valido
        escritorio = Escritorio.objects.get(pk=escritorio_id_valido)
        registrar(acao="escritorio.ativado", usuario=request.user, escritorio=escritorio)
        messages.success(request, f"Escritório ativo: {escritorio.nome}.")
    else:
        # BL-23/A9: GET nesta URL (link direto, favorito, back do navegador)
        # também voltava em silêncio — mesmo problema do POST inválido, só
        # que pelo método errado em vez do ID errado. O formulário do
        # painel só envia POST; chegar aqui por GET não troca nada e
        # precisa dizer isso.
        messages.error(request, "Use o formulário do painel para trocar de escritório.")
    return redirect("tenancy:painel")
