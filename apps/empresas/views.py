from datetime import date

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from rest_framework import generics
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.auditoria.services import registrar
from apps.empresas.forms import EmpresaForm
from apps.empresas.mixins import EmpresaEscopadaMixin
from apps.empresas.models import Empresa, Estabelecimento, HistoricoRegimeTributario
from apps.empresas.serializers import (
    EmpresaSerializer,
    EstabelecimentoSerializer,
    HistoricoRegimeTributarioSerializer,
)
from apps.empresas.services import registrar_regime_tributario
from apps.tenancy.models import Papel
from apps.tenancy.permissions import TemEscritorioAtivo, papel_permitido

# Criação/alteração de cadastro é restrita a quem administra o escritório;
# consulta continua liberada a qualquer papel vinculado (ver get_permissions
# e as views de leitura, que só exigem TemEscritorioAtivo).
PodeGerenciarEmpresa = papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)


class EmpresaQuerySetMixin:
    permission_classes = [TemEscritorioAtivo]

    def get_queryset(self):
        # Isolamento: sempre filtrado pelo escritório ativo da requisição,
        # nunca por um identificador recebido do cliente.
        return Empresa.objects.filter(escritorio=self.request.escritorio)


class EmpresaListCreateView(EmpresaQuerySetMixin, generics.ListCreateAPIView):
    serializer_class = EmpresaSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def perform_create(self, serializer):
        empresa = serializer.save()
        registrar(acao="empresa.criada", objeto=empresa, request=self.request)


class EmpresaDetailView(EmpresaQuerySetMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EmpresaSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method in ("PUT", "PATCH"):
            permissions.append(PodeGerenciarEmpresa())
        return permissions


class EstabelecimentoListCreateView(EmpresaEscopadaMixin, generics.ListCreateAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = EstabelecimentoSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def get_queryset(self):
        return Estabelecimento.objects.filter(empresa=self.get_empresa())

    def perform_create(self, serializer):
        estabelecimento = serializer.save(empresa=self.get_empresa())
        registrar(acao="estabelecimento.criado", objeto=estabelecimento, request=self.request)


class HistoricoRegimeTributarioListCreateView(EmpresaEscopadaMixin, generics.ListAPIView):
    permission_classes = [TemEscritorioAtivo]
    serializer_class = HistoricoRegimeTributarioSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method == "POST":
            permissions.append(PodeGerenciarEmpresa())
        return permissions

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

        registrar(
            acao="regime_tributario.registrado",
            objeto=registro,
            request=request,
            detalhes={"regime": regime, "vigencia_inicio": vigencia_inicio},
        )
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
    if request.papel not in (Papel.ADMINISTRADOR, Papel.GESTOR):
        return HttpResponseForbidden("Seu papel não permite cadastrar empresas.")

    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save(commit=False)
            empresa.escritorio = request.escritorio
            empresa.save()
            registrar(acao="empresa.criada", objeto=empresa, request=request)
            return redirect("empresas:lista")
    else:
        form = EmpresaForm()

    return render(request, "empresas/form.html", {"form": form})
