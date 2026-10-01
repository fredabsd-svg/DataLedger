from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.accounts import limite_tentativas
from apps.accounts.forms import CadastroForm
from apps.auditoria.services import registrar
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.tenancy.services.primeiro_acesso import criar_primeiro_escritorio_e_vinculo_admin

CONTRATO_CADASTRO = ContratoDeRequisicao(
    campos=set(CadastroForm.base_fields) | {"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de uma nova empresa",
)

# Diferente do login, o cadastro pode dizer que está limitado: a recusa não
# revela existência de conta nenhuma (vem depois da validação do formulário,
# que já é o contrato atual) e quem digitou certo precisa saber que deve esperar.
MENSAGEM_CADASTRO_LIMITADO = (
    "Muitos cadastros foram feitos a partir deste endereço. Aguarde um pouco e tente novamente."
)


@sensitive_post_parameters("password1", "password2")
@require_http_methods(["GET", "POST"])
def cadastro(request):
    """Cria usuário e primeiro escritório juntos, sem associar cadastros existentes.

    O e-mail informado não comprova sua titularidade e nunca é usado para
    descobrir convites ou conceder vínculos preexistentes. Aceitar um convite
    continua exigindo seu token opaco, obtido por um canal externo de confiança.
    """
    if request.user.is_authenticated:
        return redirect("tenancy:painel")
    form = CadastroForm(request.POST if request.method == "POST" else None)
    status = 400 if form.is_bound else 200
    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_CADASTRO)
        except DadoNaoContratado as exc:
            form.add_error(None, exc.mensagem)
        if form.is_valid() and not limite_tentativas.reservar_cadastro(request):
            # Reservado ANTES de criar e sem efeito colateral na recusa: nada
            # de usuário, escritório, vínculo nem sessão (DL-056, critério 4).
            # Nenhum dado digitado vai para a trilha. `add_error` invalida o
            # formulário, então o `if` seguinte não cria nada.
            registrar(acao="cadastro.bloqueado", request=request)
            form.add_error(None, MENSAGEM_CADASTRO_LIMITADO)
            status = 429
        if form.is_valid():
            try:
                # A unicidade do banco também cobre concorrência: qualquer
                # falha no escritório, vínculo ou auditoria desfaz o usuário.
                with transaction.atomic():
                    usuario = get_user_model().objects.create_user(
                        username=form.cleaned_data["email"],
                        email=form.cleaned_data["email"],
                        first_name=form.cleaned_data["nome"],
                        password=form.cleaned_data["password1"],
                    )
                    resultado = criar_primeiro_escritorio_e_vinculo_admin(
                        usuario=usuario,
                        nome=form.cleaned_data["nome_escritorio"],
                        cnpj=form.cleaned_data["cnpj"],
                        # DL-059 (BL-579): sem `request` a trilha de
                        # `escritorio.criado_por_bootstrap` saía sem IP por
                        # este caminho (só o do primeiro acesso o gravava).
                        request=request,
                    )
            except IntegrityError:
                form.add_error(
                    None, "Não foi possível concluir o cadastro. E-mail ou CNPJ já em uso."
                )
            else:
                login(request, usuario)
                request.session["escritorio_id"] = resultado.escritorio.pk
                messages.success(request, "Conta criada! Seu ambiente está pronto para começar.")
                return redirect("tenancy:painel")
    resposta = render(request, "registration/signup.html", {"form": form}, status=status)
    if status == 429:
        resposta["Retry-After"] = str(settings.LIMITE_TENTATIVAS_CADASTRO_JANELA_SEGUNDOS)
    return resposta
