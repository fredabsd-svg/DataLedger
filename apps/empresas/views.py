from datetime import date

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from rest_framework import generics
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.empresas.forms import EmpresaForm
from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
from apps.empresas.serializers import (
    EmpresaSerializer,
    EstabelecimentoSerializer,
    HistoricoRegimeTributarioSerializer,
)
from apps.empresas.services import registrar_regime_tributario
from apps.tenancy.permissions import TemEscritorioAtivo


class EmpresaQuerySetMixin:
    permission_classes = [TemEscritorioAtivo]

    def get_queryset(self):
        # Isolamento: sempre filtrado pelo escritório ativo da requisição,
        # nunca por um identificador recebido do cliente.
        return Empresa.objects.filter(escritorio=self.request.escritorio)


class EmpresaListCreateView(EmpresaQuerySetMixin, generics.ListCreateAPIView):
    serializer_class = EmpresaSerializer


class EmpresaDetailView(EmpresaQuerySetMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EmpresaSerializer


class EmpresaEscopadaMixin:
    """Resolve a empresa da URL restrita ao escritório ativo da requisição.

    Uma empresa de outro escritório resulta em 404, não em 403: não
    confirma sequer a existência do registro para quem não tem acesso.
    """

    permission_classes = [TemEscritorioAtivo]

    def get_empresa(self):
        return get_object_or_404(
            Empresa, pk=self.kwargs["empresa_id"], escritorio=self.request.escritorio
        )


class EstabelecimentoListCreateView(EmpresaEscopadaMixin, generics.ListCreateAPIView):
    serializer_class = EstabelecimentoSerializer

    def get_queryset(self):
        return Estabelecimento.objects.filter(empresa=self.get_empresa())

    def perform_create(self, serializer):
        serializer.save(empresa=self.get_empresa())


class HistoricoRegimeTributarioListCreateView(EmpresaEscopadaMixin, generics.ListAPIView):
    serializer_class = HistoricoRegimeTributarioSerializer

    def get_queryset(self):
        return HistoricoRegimeTributario.objects.filter(empresa=self.get_empresa())

    def post(self, request, *args, **kwargs):
        empresa = self.get_empresa()
        regime = request.data.get("regime")
        vigencia_inicio = request.data.get("vigencia_inicio")
        if not regime or not vigencia_inicio:
            raise DRFValidationError("regime e vigencia_inicio são obrigatórios.")

        try:
            data_inicio = date.fromisoformat(vigencia_inicio)
        except ValueError as exc:
            raise DRFValidationError("vigencia_inicio deve estar no formato AAAA-MM-DD.") from exc

        try:
            registro = registrar_regime_tributario(empresa, regime, data_inicio)
        except ValueError as exc:
            raise DRFValidationError(str(exc)) from exc

        serializer = self.get_serializer(registro)
        return Response(serializer.data, status=201)


@login_required
def lista_empresas(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    empresas = Empresa.objects.filter(escritorio=request.escritorio)
    return render(request, "empresas/lista.html", {"empresas": empresas})


@login_required
def criar_empresa(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")

    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save(commit=False)
            empresa.escritorio = request.escritorio
            empresa.save()
            return redirect("empresas:lista")
    else:
        form = EmpresaForm()

    return render(request, "empresas/form.html", {"form": form})
