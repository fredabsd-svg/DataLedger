from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
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
from apps.empresas.services import erro_de_cnpj_duplicado_como_400, registrar_regime_tributario
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
        # R4 (reauditoria, rodada 2): duas requisições simultâneas com o
        # mesmo CNPJ podem passar as duas pelo UniqueValidator do
        # serializer (ele faz SELECT; entre o SELECT e este INSERT o
        # concorrente comita) e uma delas estoura IntegrityError na
        # constraint do banco. O savepoint de transaction.atomic() isola
        # esse erro: se ele ocorrer, só o INSERT é desfeito, e a conexão
        # continua utilizável para o registrar() de auditoria abaixo.
        # erro_de_cnpj_duplicado_como_400 (apps/empresas/services.py)
        # concentra a detecção de qual IntegrityError é a violação da
        # constraint de cnpj — ver o comentário lá sobre por que isso mora
        # num lugar só (A1, reauditoria, rodada 3).
        try:
            with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
                empresa = serializer.save()
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict) from exc
        registrar(acao="empresa.criada", objeto=empresa, request=self.request)


class EmpresaDetailView(EmpresaQuerySetMixin, generics.RetrieveUpdateAPIView):
    serializer_class = EmpresaSerializer

    def get_permissions(self):
        permissions = super().get_permissions()
        if self.request.method in ("PUT", "PATCH"):
            permissions.append(PodeGerenciarEmpresa())
        return permissions

    def perform_update(self, serializer):
        # A1 (reauditoria da etapa DL-011, rodada 3): o R4 tinha sido
        # corrigido só na criação. PUT/PATCH para o CNPJ de outra empresa
        # tem exatamente a mesma corrida (SELECT do UniqueValidator, depois
        # UPDATE) — reproduzida pelo auditor em 6 de 6 execuções com duas
        # threads. Mesmo tratamento de perform_create, mesmo gerenciador de
        # contexto compartilhado.
        try:
            with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
                serializer.save()
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict) from exc


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
        # Mesmo tratamento de corrida do achado R4 em EmpresaListCreateView
        # (ver comentário lá): cnpj de Estabelecimento também é unique=True.
        try:
            with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
                estabelecimento = serializer.save(empresa=self.get_empresa())
        except DjangoValidationError as exc:
            raise DRFValidationError(exc.message_dict) from exc
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


def _mascara_cnpj(cnpj):
    """Formata um CNPJ de 14 caracteres como XX.XXX.XXX/XXXX-XX.

    Puramente de apresentação: não repete a validação de
    apps.empresas.validators, que já garantiu o formato na gravação. Se o
    valor armazenado não tiver exatamente 14 caracteres (dado herdado ou
    corrompido), devolve o valor original em vez de mascarar errado.

    O CNPJ alfanumérico (NT 2025.001/IN RFB 2.229, ver
    apps/empresas/validators.py) continua com 14 posições, então o mesmo
    agrupamento de sempre é aplicado a letras e dígitos — não só a dígitos.
    Importante: esse agrupamento XX.XXX.XXX/XXXX-XX é convenção nossa de
    exibição, não uma regra normativa. A NT 2025.001 define validação, chave
    de acesso e código de barras; ela não define máscara de tela. Se a
    Receita publicar um formato de apresentação próprio, esta função deve
    ser revista.
    """
    if len(cnpj) != 14:
        return cnpj
    return f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


@login_required
def lista_empresas(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    empresas = list(Empresa.objects.filter(escritorio=request.escritorio))
    # Formatação de apresentação (CNPJ mascarado) feita aqui, na view, e não
    # em template tag própria: esta etapa não tem permissão para criar
    # arquivos em apps/empresas/templatetags/ (ver docs/planos/DL-009).
    for empresa in empresas:
        empresa.cnpj_formatado = _mascara_cnpj(empresa.cnpj)
    contexto = {
        "empresas": empresas,
        # Booleano calculado com o enum e passado pronto ao template: a
        # regra de quem pode cadastrar mora só aqui, não repetida como
        # string literal na marcação (achado A8 da auditoria de DL-009).
        # A autorização real de qualquer forma é sempre re-checada no
        # servidor em criar_empresa; isto só decide o que a tela mostra.
        "pode_cadastrar": request.papel in (Papel.ADMINISTRADOR, Papel.GESTOR),
    }
    return render(request, "empresas/lista.html", contexto)


@login_required
def criar_empresa(request):
    if request.escritorio is None:
        return render(request, "empresas/sem_escritorio.html")
    if request.papel not in (Papel.ADMINISTRADOR, Papel.GESTOR):
        # Falta de permissão ganha template próprio, com explicação e
        # caminho de volta — nunca mais texto cru sem contexto (BL-22).
        # A autorização real continua sendo aplicada aqui, no servidor;
        # o template só explica a negativa que já ocorreu.
        contexto = {"mensagem": "Seu papel não permite cadastrar empresas."}
        return render(request, "erros/sem_permissao.html", contexto, status=403)

    if request.method == "POST":
        form = EmpresaForm(request.POST)
        if form.is_valid():
            empresa = form.save(commit=False)
            empresa.escritorio = request.escritorio
            # R4 (reauditoria da etapa DL-011): o form.is_valid() já checou
            # unicidade via validate_unique() (um SELECT), mas entre esse
            # SELECT e o INSERT abaixo um concorrente pode ter comitado o
            # mesmo CNPJ — a corrida que gera 500 se não tratada. O
            # savepoint isola o erro para a conexão continuar utilizável.
            try:
                with transaction.atomic(), erro_de_cnpj_duplicado_como_400():
                    empresa.save()
            except DjangoValidationError as exc:
                for mensagem in exc.message_dict.get("cnpj", []):
                    form.add_error("cnpj", mensagem)
            else:
                registrar(acao="empresa.criada", objeto=empresa, request=request)
                messages.success(request, f"Empresa “{empresa}” cadastrada com sucesso.")
                return redirect("empresas:lista")
    else:
        form = EmpresaForm()

    return render(request, "empresas/form.html", {"form": form})
