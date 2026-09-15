from django.contrib import messages
from django.contrib.auth.decorators import login_required
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
from apps.tenancy.models import Escritorio

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

        request.session["escritorio_id"] = escritorio_id
        # request.escritorio ainda reflete o valor de antes da troca (o
        # middleware já rodou nesta requisição): busca o novo explicitamente.
        registrar(
            acao="escritorio.ativado",
            usuario=request.user,
            escritorio=Escritorio.objects.get(pk=escritorio_id),
        )
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
