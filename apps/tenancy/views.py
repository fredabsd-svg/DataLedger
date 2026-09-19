from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render

# BL-217/A1 (auditoria DL-020 rodada 1): as views de FUNÇÃO deste módulo
# declaram os métodos HTTP que aceitam. É esta declaração — fato do objeto,
# não substring do fonte — que a varredura de contratos
# (`apps/core/tests/test_dl019_varredura_de_contratos.py`) lê para saber se a
# view é superfície de escrita. A classificação textual anterior
# (`"request.method" in fonte`) foi contornada pelo auditor com uma view que
# grava lendo `json.loads(request.body)`, com a suíte inteira verde.
from django.views.decorators.http import require_http_methods, require_safe
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditoria.services import registrar
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    VinculoUsuarioEscritorio,
)
from apps.tenancy.services.primeiro_acesso import (
    ConvidanteNaoEhAdministrador,
    ConviteInvalido,
    ConviteTokenColidiu,
    PrimeiroEscritorioJaExiste,
    aceitar_convite_e_criar_vinculo,
    criar_primeiro_escritorio_e_vinculo_admin,
    emitir_convite_para_escritorio,
)

# BL-196 / achado R6-2 (rodada 6): a política dos cinco dicionários também
# nas duas superfícies de troca de escritório ativo. Medido pelo auditor:
# `ativar_escritorio` aceitava querystring, campo desconhecido e
# `request.FILES` — **302 nos três**, ignorando em silêncio —, e
# `POST /api/escritorio-ativo/` com `xpto` respondia **200**.
#
# As duas aceitam UM campo só (`escritorio_id`) e nenhum cabeçalho de
# idempotência: trocar de escritório é operação idempotente por natureza (o
# resultado de fazer duas vezes é o mesmo), então quem envia
# `Idempotency-Key` aqui está usando um contrato que não existe e precisa
# ouvir isso — é o mesmo erro do R5-6 na tela de lançamento, onde a chave
# ignorada produzia duplicidade.
CONTRATO_ESCRITORIO_ATIVO = ContratoDeRequisicao(
    campos={"escritorio_id"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na troca de escritório ativo",
)


# DL-018 — contratos do fluxo de bootstrap e convite (DL-018).
# Os campos `csrfmiddlewaretoken` aparecem no `request.POST` das views
# de função porque o Django injeta o token CSRF como campo do form
# automaticamente — não é dado de cliente, é mecanismo de defesa contra
# CSRF. Por isso ele entra em `campos` aqui: o `recusar_dado_nao_contratado`
# confere a forma do payload como um todo, e este campo é parte esperada
# do form.
CONTRATO_BOOTSTRAP_PRIMEIRO_ESCRITORIO = ContratoDeRequisicao(
    campos={"nome", "cnpj", "csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no bootstrap do primeiro escritório (DL-018)",
)


CONTRATO_EMITIR_CONVITE = ContratoDeRequisicao(
    campos={"escritorio_id", "email", "csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na emissão de convite por ADMINISTRADOR (DL-018)",
)


CONTRATO_ACEITAR_CONVITE = ContratoDeRequisicao(
    campos={"csrfmiddlewaretoken"},
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no aceite de convite por usuário autenticado (DL-018)",
)


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
        # BL-196: a política vem de `apps.core.requisicao`; aqui só a
        # tradução para o protocolo desta superfície. 400 (entrada que o
        # contrato não aceita), não 403 — o 403 abaixo é para vínculo
        # inexistente, que é outra coisa e não deve ser confundida.
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ESCRITORIO_ATIVO)
        except DadoNaoContratado as exc:
            return Response({"detail": exc.mensagem}, status=400)

        escritorio_id_bruto = request.data.get("escritorio_id")

        # `para_id` (achado A2 da auditoria DL-017 rodada 4, BL-127, e o
        # gêmeo encontrado nesta mesma correção): antes, `escritorio_id`
        # ia direto para o `filter()` sem checagem nenhuma — um
        # identificador em texto com milhares de dígitos (`"9" * 6000`)
        # levantava `ValueError` DENTRO do ORM ao montar o filtro
        # (`Field 'id' expected a number but got ...`), 500 cru; e um
        # `int` JSON igualmente grande estourava o mesmo limite ao ser
        # comparado. `para_id` aceita as duas formas (texto da querystring/
        # formulário, número JSON) com o MESMO julgador, e nunca deixa um
        # identificador fora do formato chegar ao ORM.
        try:
            escritorio_id = para_id(escritorio_id_bruto)
        except IdentificadorInvalido:
            return Response({"detail": "Escritório inválido ou sem vínculo ativo."}, status=403)

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado.
        tem_vinculo = request.user.vinculos.filter(escritorio_id=escritorio_id, ativo=True).exists()
        if not tem_vinculo:
            return Response({"detail": "Escritório inválido ou sem vínculo ativo."}, status=403)

        # BL-14 (DL-024): o `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava o `RegistroAuditoria`. Antes, se
        # o INSERT da trilha falhasse, a troca de escritório ativo
        # continuava válida e a auditoria ficava silenciosamente vazia.
        # **Limitação:** a `request.session` não reverte por
        # `transaction.atomic()` (ver comentário equivalente em
        # `ativar_escritorio`). A defesa cobre o RegistroAuditoria.
        with transaction.atomic():
            # request.escritorio ainda reflete o valor de antes da troca (o
            # middleware já rodou nesta requisição): busca o novo explicitamente.
            escritorio = Escritorio.objects.get(pk=escritorio_id)
            registrar(
                acao="escritorio.ativado",
                usuario=request.user,
                escritorio=escritorio,
            )
        request.session["escritorio_id"] = escritorio_id
        return Response({"status": "ok"})


@login_required
@require_safe
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
@require_http_methods(["GET", "POST"])
def ativar_escritorio(request):
    if request.method == "POST":
        # BL-196: mesma política da view irmã acima, mesma fonte única, e
        # aqui na forma que esta superfície usa para dizer "não" — mensagem
        # de erro e volta ao painel, o padrão que o BL-23 instituiu para
        # todo caminho que NÃO ativa. O auditor mediu 302 silencioso para
        # querystring, campo desconhecido e arquivo: a troca não acontecia
        # (ou acontecia com dado ignorado) e o usuário não era avisado de
        # nada.
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ESCRITORIO_ATIVO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect("tenancy:painel")

        escritorio_id = request.POST.get("escritorio_id")

        # BL-23: antes, um vínculo inexistente (ou um valor não numérico)
        # caía direto no redirecionamento sem avisar nada — o usuário achava
        # que a troca tinha funcionado. Agora todo caminho que não ativa
        # termina em mensagem de erro explícita.
        #
        # `para_id` (achado A2 da auditoria DL-017 rodada 4, BL-127):
        # SUBSTITUI a validação por `str(escritorio_id).isdigit()` +
        # `int(escritorio_id)` que havia aqui. O comentário que justificava
        # essa escolha ("evita depender de exceção para um caso de entrada
        # tão comum") é exatamente o que causava o defeito: `.isdigit()`
        # aceita QUALQUER dígito Unicode (`"２"`.isdigit()` é `True`,
        # reinterpretado em silêncio para `2`) e não impõe limite de
        # comprimento (`"9" * 6000` passa em `.isdigit()`, e só o `int()`
        # seguinte estourava com `ValueError` cru — 500). `para_id` aplica
        # as duas defesas de uma vez, com o mesmo julgador usado em
        # `EscritorioAtivoView.post` (view irmã, mesmo arquivo) — nunca
        # reimplementado aqui.
        try:
            escritorio_id_valido = para_id(escritorio_id)
        except IdentificadorInvalido:
            messages.error(request, "Escritório inválido.")
            return redirect("tenancy:painel")

        # Nunca confiar apenas no ID recebido: exige vínculo ativo do
        # próprio usuário autenticado com o escritório solicitado (mesma
        # regra de isolamento aplicada em EscritorioAtivoView.post).
        tem_vinculo = request.user.vinculos.filter(
            escritorio_id=escritorio_id_valido, ativo=True
        ).exists()
        if not tem_vinculo:
            messages.error(request, "Escritório inválido ou sem vínculo ativo com o seu usuário.")
            return redirect("tenancy:painel")

        # BL-14 (DL-024): `registrar()` foi MOVIDO para dentro do mesmo
        # `transaction.atomic()` que grava o `RegistroAuditoria`. Antes, se
        # o INSERT da trilha falhasse, a troca de escritório ativo
        # continuava válida e a auditoria ficava silenciosamente vazia —
        # a sessão dizia uma coisa, a trilha dizia outra. Agora ambos
        # são uma só operação atômica; qualquer exceção do `registrar()`
        # propaga e a transação reverte. **Limitação:** a `request.session`
        # não é revertida por `transaction.atomic()` — a troca fica
        # registrada no cookie mesmo se a trilha falhar. Quem precisa de
        # reversão completa da sessão precisa de abordagem diferente
        # (fora do escopo do BL-14, registro como pendência para DL futura).
        with transaction.atomic():
            escritorio = Escritorio.objects.get(pk=escritorio_id_valido)
            registrar(acao="escritorio.ativado", usuario=request.user, escritorio=escritorio)
        request.session["escritorio_id"] = escritorio_id_valido
        messages.success(request, f"Escritório ativo: {escritorio.nome}.")
    else:
        # BL-23/A9: GET nesta URL (link direto, favorito, back do navegador)
        # também voltava em silêncio — mesmo problema do POST inválido, só
        # que pelo método errado em vez do ID errado. O formulário do
        # painel só envia POST; chegar aqui por GET não troca nada e
        # precisa dizer isso.
        messages.error(request, "Use o formulário do painel para trocar de escritório.")
    return redirect("tenancy:painel")


# ---------------------------------------------------------------------------
# DL-018 — primeiro acesso via produto (DE-042)
# ---------------------------------------------------------------------------
#
# Três superfícies novas:
#
# - `bootstrap_primeiro_acesso` (GET/POST): tela para o usuário sem
#   vínculo criar o primeiro escritório. Renderiza um formulário
#   simples (nome + CNPJ). POST cria escritório e vincula o usuário
#   como ADMINISTRADOR — redireciona para o painel.
# - `emitir_convite` (POST): API para o ADMINISTRADOR do escritório
#   cadastrar o e-mail do segundo funcionário.
# - `aceitar_convite` (GET/POST): tela para o convidado apresentar o
#   token recebido (em geral via link), autenticado, e virar
#   ANALISTA do escritório.
#
# A defesa é no serviço (`primeiro_acesso.py`), não nas views — aqui só
# tradução HTTP. As exceções de domínio viram 400/403/409/410 conforme o
# contrato.


@login_required
@require_http_methods(["GET", "POST"])
def bootstrap_primeiro_acesso(request):
    """DL-018 critério 1: primeira superfície para o usuário sem
    vínculo. Renderiza formulário no GET e cria escritório + vínculo
    ADMINISTRADOR no POST.

    O ponto-chave é a `PrimeiroEscritorioJaExiste` no serviço: se o
    usuário JÁ tem escritório, o caminho `bootstrap` não é o dele —
    redirecionar para o painel. Defesa contra o caso "duas abas
    abertas de bootstrap no mesmo usuário": o segundo POST cai no
    painel com mensagem de erro, e não em 500."""
    if VinculoUsuarioEscritorio.objects.filter(usuario=request.user, ativo=True).exists():
        messages.info(
            request,
            "Você já tem escritório. Use o painel para gerenciar.",
        )
        return redirect("tenancy:painel")

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_BOOTSTRAP_PRIMEIRO_ESCRITORIO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return render(request, "tenancy/primeiro_acesso.html", {})

        nome = (request.POST.get("nome") or "").strip()
        cnpj = (request.POST.get("cnpj") or "").strip()
        if not nome or not cnpj:
            messages.error(request, "Nome e CNPJ são obrigatórios.")
            return render(
                request,
                "tenancy/primeiro_acesso.html",
                {"nome": nome, "cnpj": cnpj},
            )

        try:
            resultado = criar_primeiro_escritorio_e_vinculo_admin(
                usuario=request.user,
                nome=nome,
                cnpj=cnpj,
            )
        except PrimeiroEscritorioJaExiste:
            messages.error(request, "Você já tem escritório ativo.")
            return redirect("tenancy:painel")

        messages.success(
            request,
            f"Escritório criado: {resultado.escritorio.nome}. "
            "Você é o ADMINISTRADOR. Convide o segundo funcionário pela tela de escritório.",
        )
        return redirect("tenancy:painel")

    return render(request, "tenancy/primeiro_acesso.html", {})


@login_required
@require_http_methods(["POST"])
def emitir_convite(request):
    """DL-018 critério 3: ADMINISTRADOR do escritório convida o
    segundo funcionário por e-mail. Token opaco devolvido na resposta
    — a próxima etapa que envia por e-mail de verdade (SMTP) entra
    aqui.
    """
    try:
        recusar_dado_nao_contratado(request, CONTRATO_EMITIR_CONVITE)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect("tenancy:painel")

    escritorio_id_raw = request.POST.get("escritorio_id")
    email = (request.POST.get("email") or "").strip()

    try:
        escritorio_id = para_id(escritorio_id_raw)
    except IdentificadorInvalido:
        messages.error(request, "Escritório inválido.")
        return redirect("tenancy:painel")

    try:
        escritorio = Escritorio.objects.get(pk=escritorio_id)
    except Escritorio.DoesNotExist:
        messages.error(request, "Escritório inválido.")
        return redirect("tenancy:painel")

    if not email:
        messages.error(request, "E-mail do convidado é obrigatório.")
        return redirect("tenancy:painel")

    try:
        convite = emitir_convite_para_escritorio(
            escritorio=escritorio,
            email_convidado=email,
            convidador=request.user,
        )
    except ConvidanteNaoEhAdministrador:
        messages.error(
            request,
            "Apenas ADMINISTRADOR ativo pode convidar. "
            "Se você é o segundo funcionário, aguarde o convite.",
        )
        return redirect("tenancy:painel")
    except ConviteTokenColidiu:
        # Provavelmente impossível (~1 em 2^190). Tentar de novo — o
        # `save()` do modelo vai gerar outro token. Não é 5xx: o cliente
        # PODE retentar com o mesmo payload.
        messages.warning(
            request,
            "Colisão rara de token. Tente novamente — o sistema gerou outro token automaticamente.",
        )
        return redirect("tenancy:painel")

    messages.success(
        request,
        f"Convite emitido para {convite.email}. A próxima etapa envia por e-mail de verdade.",
    )
    return redirect("tenancy:painel")


@login_required
@require_http_methods(["GET", "POST"])
def aceitar_convite(request, token: str):
    """DL-018 critério 3: usuário autenticado apresenta o token de
    convite e vira ANALISTA (ou o `papel_inicial` do convite) do
    escritório. Token está no path da URL para simplicidade da etapa
    — quando SMTP entrar, o token vem por link no e-mail, e esta
    rota permanece a mesma.
    """
    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, CONTRATO_ACEITAR_CONVITE)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect("tenancy:painel")

        try:
            aceitar_convite_e_criar_vinculo(token=token, usuario=request.user)
        except ConviteInvalido:
            messages.error(
                request,
                "Convite inexistente, expirado ou já consumido.",
            )
            return redirect("tenancy:painel")

        messages.success(
            request,
            "Vínculo criado. Use o painel para começar.",
        )
        return redirect("tenancy:painel")

    convite = ConviteEscritorio.objects.filter(token=token).first()
    return render(
        request,
        "tenancy/aceitar_convite.html",
        {"token": token, "convite": convite},
    )
