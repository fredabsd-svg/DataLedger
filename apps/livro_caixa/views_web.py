"""Telas do livro-caixa (DL-046, fatia 1) — servidor + API prontos
(`apps.livro_caixa.{models,services,views,serializers}`, `desenvolvedor-pleno`,
2026-09-26); este módulo é só a FRENTE DA TELA, no molde de
`apps.contabilidade.views_web` (DE-026): a autorização de LEITURA e de
ESCRITA reaproveita as MESMAS funções que a API já usa
(`apps.livro_caixa.permissoes.papel_pode_ler_livro_caixa`/
`papel_pode_escriturar_livro_caixa`) — nenhuma segunda lista de papéis "só
para a tela"; a GRAVAÇÃO passa inteira pelos SERVIÇOS
(`apps.livro_caixa.services`), nunca reimplementada aqui.

Este arquivo NUNCA chama a própria API (DE-026) — chama os serviços
diretamente e renderiza HTML no servidor.

Vários helpers pequenos deste módulo (`_empresa_do_escritorio_ativo`,
`_resposta_sem_permissao`, `_resposta_sem_escritorio`, formatação
monetária pt-BR) são CÓPIAS locais, de propósito — mesmo raciocínio do
comentário de `apps.livro_caixa.permissoes` sobre a matriz de papéis:
livro-caixa e contabilidade são regimes de escrituração DIFERENTES
(RC-113/RC-114), e importar uma função "privada" (prefixo `_`) de
`apps.contabilidade.views_web` amarraria os dois módulos por acidente de
implementação, nunca por contrato.
"""

import re
import uuid
from datetime import timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import RestricaoViolada
from apps.empresas.models import Empresa
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
    OrigemRecebimento,
)
from apps.livro_caixa.permissoes import (
    papel_pode_escriturar_livro_caixa,
    papel_pode_ler_livro_caixa,
)
from apps.livro_caixa.services import (
    ChaveIdempotenciaConflitanteCaixa,
    LancamentoCaixaInvalido,
    apurar_livro_caixa,
    criar_conta_livro_caixa,
    criar_lancamento_caixa,
    estornar_lancamento_caixa,
)
from apps.livro_caixa.validators import (
    DATA_MINIMA_LANCAMENTO_CAIXA,
    data_maxima_lancamento_caixa,
)

TAMANHO_MAXIMO_CHAVE_IDEMPOTENCIA_CAIXA = 255


# ---------------------------------------------------------------------------
# Isolamento e permissão — mesmo desenho de apps.contabilidade.views_web.
# ---------------------------------------------------------------------------


def _empresa_do_escritorio_ativo(request, empresa_id):
    """Resolve a empresa da URL, restrita ao escritório ATIVO da sessão —
    nunca por um `empresa_id` cru. Empresa de outro escritório dá 404,
    nunca confirma a existência do registro para quem não tem acesso.
    Memoizado por REQUISIÇÃO (mesmo motivo de `apps.contabilidade.
    views_web._empresa_do_escritorio_ativo`, R5 da DL-038): a recusa de
    modo (`_sem_livro_caixa_para_contabilidade`) resolve a empresa ANTES
    do corpo da view, e sem cache isso somaria uma consulta a mais por
    requisição.
    """
    cache = getattr(request, "_dl046_cache_empresa_do_escritorio_ativo", None)
    if cache is None:
        cache = {}
        request._dl046_cache_empresa_do_escritorio_ativo = cache
    if empresa_id not in cache:
        cache[empresa_id] = get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)
    return cache[empresa_id]


def _resposta_sem_permissao(request, mensagem):
    return render(request, "erros/sem_permissao.html", {"mensagem": mensagem}, status=403)


def _resposta_sem_escritorio(request):
    return render(request, "empresas/sem_escritorio.html")


def _sem_livro_caixa_para_contabilidade(request, empresa):
    """Recusa (403, mesma mensagem e mesma regra da API) quando `empresa`
    NÃO está em modo `livro_caixa` — o livro-caixa só existe para cliente
    em livro-caixa; a contabilidade por partidas dobradas é a outra porta
    (`apps.contabilidade.views_web`). Espelho exato de `_sem_contabilidade_
    para_livro_caixa` (contabilidade), mesma ORDEM de chamada: sempre
    DEPOIS de `request.escritorio`/`_empresa_do_escritorio_ativo` e de
    `_pode_ler`/`_pode_escriturar` — nunca antes, para um papel sem
    permissão de LEITURA nunca ver a mensagem de modo (que revelaria o
    modo de escrituração da empresa a quem não tem acesso nem para ler).
    """
    try:
        recusar_se_nao_livro_caixa(empresa)
    except EmpresaNaoEmModoLivroCaixa as exc:
        return _resposta_sem_permissao(request, exc.mensagem)
    return None


def _pode_ler(request):
    return papel_pode_ler_livro_caixa(getattr(request, "papel", None))


def _pode_escriturar(request):
    return papel_pode_escriturar_livro_caixa(getattr(request, "papel", None))


# ---------------------------------------------------------------------------
# Formatação de apresentação — cópia local de apps.contabilidade.views_web
# (mesmo motivo do docstring do módulo): nunca usada para cálculo, o valor
# segue Decimal até aqui.
# ---------------------------------------------------------------------------


def _milhar_ptbr(parte_inteira):
    negativo = parte_inteira.startswith("-")
    digitos = parte_inteira[1:] if negativo else parte_inteira
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    resultado = ".".join(grupos)
    return f"-{resultado}" if negativo else resultado


def _valor_ptbr(valor):
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    texto = str(quantizado)
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    parte_inteira, parte_decimal = texto.split(".")
    resultado = f"{_milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if negativo else resultado


def _mascara_cpf(cpf):
    if not cpf or len(cpf) != 11:
        return cpf or ""
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


def _mascara_cnpj(cnpj):
    if not cnpj or len(cnpj) != 14:
        return cnpj or ""
    return f"{cnpj[0:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:14]}"


# DE-029 (mesma gramática de apps.contabilidade.views_web): dígitos sem
# separador, ou grupo de milhar bem formado (exatamente três dígitos após
# cada ponto), com centavos opcionais depois da vírgula — texto fora da
# gramática é RECUSADO, nunca reinterpretado.
_GRAMATICA_VALOR_PTBR = re.compile(r"^[+-]?([0-9]+|[0-9]{1,3}(\.[0-9]{3})+)(,[0-9]{1,2})?$")


def _decimal_do_formulario(texto):
    bruto = texto or ""
    if not _GRAMATICA_VALOR_PTBR.fullmatch(bruto):
        raise ValorMonetarioInvalido(
            f"Valor “{bruto}” não está no formato aceito. Use dígitos, ponto a cada "
            "três casas como separador de milhar (ex.: 1.000) e vírgula para os "
            "centavos (ex.: 1.000,00)."
        )
    traduzido = bruto.replace(".", "").replace(",", ".")
    return para_decimal(traduzido)


# ---------------------------------------------------------------------------
# Plano de contas do livro-caixa (critério 1 do plano; item 2 do FAZER)
# ---------------------------------------------------------------------------


class ContaCaixaForm(forms.ModelForm):
    class Meta:
        model = ContaLivroCaixa
        fields = ["codigo", "nome", "natureza", "codigo_carne_leao", "ativa"]
        help_texts = {
            "codigo_carne_leao": (
                "Código do Carnê-Leão Web (Receita Federal) — a dedutibilidade "
                "decorre dele. Conta de RECEITA: rendimento no formato "
                "R01.xxx.xxx (ex.: R01.001.001 trabalho não assalariado; "
                "R01.003.001 aluguel). Conta de DESPESA: pagamento P10 "
                "(dedutível) ou P11 (não dedutível), seguido do código desta "
                "própria conta; ou P20 (imposto pago, pensão, previdência — "
                "código fixo da Receita). A tabela completa de códigos ainda "
                "não foi confirmada (PE-71) — aqui só o FORMATO, nunca a "
                "lista inteira."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Direção de arte §4.6/DL-038 (mesmo padrão de EmpresaForm): opção
        # sempre visível, sem JavaScript escondendo uma atrás da outra.
        self.fields["natureza"].widget = forms.RadioSelect(choices=NaturezaCaixa.choices)


_CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA = ContratoDeRequisicao(
    campos=frozenset(
        {"csrfmiddlewaretoken", "codigo", "nome", "natureza", "codigo_carne_leao", "ativa"}
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no cadastro de conta do livro-caixa",
)


@login_required
@require_safe
def plano_de_contas_caixa(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler o livro-caixa desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    contas = list(ContaLivroCaixa.objects.filter(empresa=empresa).order_by("codigo"))
    contexto = {
        "empresa": empresa,
        "contas": contas,
        "pode_escriturar": _pode_escriturar(request),
    }
    return render(request, "livro_caixa/plano_de_contas.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def conta_caixa_nova(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite criar contas do livro-caixa nesta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return render(
                request,
                "livro_caixa/conta_form.html",
                {"empresa": empresa, "form": ContaCaixaForm(request.POST)},
                status=400,
            )

        form = ContaCaixaForm(request.POST)
        if form.is_valid():
            try:
                conta = criar_conta_livro_caixa(
                    empresa=empresa,
                    codigo=form.cleaned_data["codigo"],
                    nome=form.cleaned_data["nome"],
                    natureza=form.cleaned_data["natureza"],
                    codigo_carne_leao=form.cleaned_data["codigo_carne_leao"],
                    ativa=form.cleaned_data["ativa"],
                    criado_por=request.user,
                    request=request,
                )
            except DjangoValidationError as exc:
                # `criar_conta_livro_caixa` propaga `full_clean()` sem
                # tradução (docstring dela) — `message_dict` preserva o
                # CAMPO de cada erro quando `Conta.clean()`/campo próprio já
                # os separou (ex.: "codigo_carne_leao"); erro geral
                # (`ValidationError` solta) vira erro do formulário inteiro.
                if hasattr(exc, "message_dict"):
                    for campo, mensagens_do_campo in exc.message_dict.items():
                        alvo = campo if campo in form.fields else None
                        for mensagem in mensagens_do_campo:
                            form.add_error(alvo, mensagem)
                else:
                    for mensagem in exc.messages:
                        form.add_error(None, mensagem)
            except RestricaoViolada as exc:
                form.add_error("codigo", str(exc))
            else:
                messages.success(request, f"Conta “{conta}” criada com sucesso.")
                return redirect("livro_caixa_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ContaCaixaForm()

    return render(request, "livro_caixa/conta_form.html", {"empresa": empresa, "form": form})


# ---------------------------------------------------------------------------
# Lançamento de caixa (critério 2 do plano; item 3 do FAZER)
# ---------------------------------------------------------------------------


_CONTRATO_DO_FORMULARIO_DE_LANCAMENTO_CAIXA = ContratoDeRequisicao(
    campos=frozenset(
        {
            "csrfmiddlewaretoken",
            "data",
            "conta",
            "valor",
            "historico",
            "documento_origem",
            "recebido_de",
            "cpf_titular_pagamento",
            "cpf_beneficiario_servico",
            "cnpj_pagador",
            "chave_idempotencia",
        }
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento de caixa",
)


def _contexto_form_lancamento_caixa(empresa, contas, dados, *, chave_idempotencia):
    return {
        "empresa": empresa,
        "contas": contas,
        "origens": OrigemRecebimento.choices,
        "data_texto": dados.get("data", ""),
        "conta_selecionada_id": dados.get("conta", ""),
        "valor_texto": dados.get("valor", ""),
        "historico": dados.get("historico", ""),
        "documento_origem": dados.get("documento_origem", ""),
        "recebido_de_selecionado": dados.get("recebido_de", ""),
        "cpf_titular_pagamento": dados.get("cpf_titular_pagamento", ""),
        "cpf_beneficiario_servico": dados.get("cpf_beneficiario_servico", ""),
        "cnpj_pagador": dados.get("cnpj_pagador", ""),
        "chave_idempotencia": chave_idempotencia,
        "data_minima_iso": DATA_MINIMA_LANCAMENTO_CAIXA.isoformat(),
        "data_maxima_iso": data_maxima_lancamento_caixa().isoformat(),
        "data_minima_ptbr": DATA_MINIMA_LANCAMENTO_CAIXA,
        "data_maxima_ptbr": data_maxima_lancamento_caixa(),
    }


@login_required
@require_http_methods(["GET", "POST"])
def lancamento_caixa_novo(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite lançar no livro-caixa desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    contas = list(ContaLivroCaixa.objects.filter(empresa=empresa, ativa=True).order_by("codigo"))

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_LANCAMENTO_CAIXA)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            contexto = _contexto_form_lancamento_caixa(
                empresa,
                contas,
                request.POST,
                chave_idempotencia=request.POST.get("chave_idempotencia") or uuid.uuid4().hex,
            )
            return render(request, "livro_caixa/lancamento_form.html", contexto, status=400)

        chave_idempotencia = request.POST.get("chave_idempotencia") or uuid.uuid4().hex

        def _recusa(mensagem):
            messages.error(request, mensagem)
            contexto = _contexto_form_lancamento_caixa(
                empresa, contas, request.POST, chave_idempotencia=chave_idempotencia
            )
            return render(request, "livro_caixa/lancamento_form.html", contexto, status=400)

        conta_id = request.POST.get("conta") or ""
        conta = ContaLivroCaixa.objects.filter(pk=conta_id, empresa=empresa).first()
        if conta is None:
            return _recusa("Escolha uma conta do livro-caixa desta empresa.")

        try:
            valor = _decimal_do_formulario(request.POST.get("valor", ""))
        except ValorMonetarioInvalido as exc:
            return _recusa(str(exc))

        data_texto = request.POST.get("data", "")
        try:
            data_lancamento = para_data(data_texto)
        except DataInvalida as exc:
            return _recusa(f"'data' inválida: {exc}")

        try:
            lancamento = criar_lancamento_caixa(
                empresa=empresa,
                conta=conta,
                data=data_lancamento,
                valor=valor,
                historico=request.POST.get("historico", "").strip(),
                documento_origem=request.POST.get("documento_origem", "").strip(),
                recebido_de=request.POST.get("recebido_de") or None,
                cpf_titular_pagamento=request.POST.get("cpf_titular_pagamento", "").strip(),
                cpf_beneficiario_servico=request.POST.get("cpf_beneficiario_servico", "").strip(),
                cnpj_pagador=request.POST.get("cnpj_pagador", "").strip(),
                criado_por=request.user,
                chave_idempotencia=chave_idempotencia,
                request=request,
            )
        except ChaveIdempotenciaConflitanteCaixa as exc:
            return _recusa(str(exc))
        except LancamentoCaixaInvalido as exc:
            return _recusa(str(exc))

        if lancamento.criado_agora:
            messages.success(
                request, f"Lançamento de {_valor_ptbr(lancamento.valor)} gravado com sucesso."
            )
        else:
            messages.info(
                request, "Este lançamento já tinha sido gravado (repetição identificada)."
            )
        return redirect("livro_caixa_web:lancamentos", empresa_id=empresa.id)

    contexto = _contexto_form_lancamento_caixa(
        empresa, contas, {}, chave_idempotencia=uuid.uuid4().hex
    )
    return render(request, "livro_caixa/lancamento_form.html", contexto)


# ---------------------------------------------------------------------------
# Lista de lançamentos do período, com ação "Estornar" (item 3 do FAZER)
# ---------------------------------------------------------------------------


def _periodo_do_formulario_caixa(request):
    """Mês corrente por padrão (primeira visita, sem querystring); senão lê
    `inicio`/`fim` — mesmo contrato de `_periodo_do_formulario`
    (contabilidade): devolve `(None, None)` quando a entrada não pôde ser
    usada, nunca lança exceção."""
    bruto_inicio = request.GET.get("inicio")
    bruto_fim = request.GET.get("fim")
    if not bruto_inicio and not bruto_fim:
        hoje = timezone.localdate()
        inicio = hoje.replace(day=1)
        if hoje.month == 12:
            fim = hoje.replace(day=31)
        else:
            proximo_mes = hoje.replace(day=1, month=hoje.month + 1)
            fim = proximo_mes - timedelta(days=1)
        return inicio, fim
    try:
        inicio = para_data(bruto_inicio)
        fim = para_data(bruto_fim)
    except DataInvalida:
        return None, None
    if inicio > fim:
        return None, None
    return inicio, fim


@login_required
@require_safe
def lancamentos_caixa_lista(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler o livro-caixa desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    inicio, fim = _periodo_do_formulario_caixa(request)
    contexto = {
        "empresa": empresa,
        "pode_escriturar": _pode_escriturar(request),
        "inicio": inicio,
        "fim": fim,
    }
    if inicio is None or fim is None:
        messages.error(request, "O período informado não pôde ser usado.")
        return render(request, "livro_caixa/lancamentos_lista.html", contexto, status=400)

    lancamentos = list(
        LancamentoCaixa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .select_related("conta")
        .order_by("-data", "-id")
    )
    linhas = [
        {
            "lancamento": lancamento,
            "valor_ptbr": _valor_ptbr(lancamento.valor),
            "e_estorno": lancamento.estorno_de_id is not None,
            "ja_estornado": lancamento.estornos.exists(),
        }
        for lancamento in lancamentos
    ]
    contexto["linhas"] = linhas
    return render(request, "livro_caixa/lancamentos_lista.html", contexto)


def _contexto_lancamento_estornar(empresa, lancamento):
    return {
        "empresa": empresa,
        "lancamento": lancamento,
        "valor_ptbr": _valor_ptbr(lancamento.valor),
    }


@login_required
@require_http_methods(["GET", "POST"])
def lancamento_caixa_estornar(request, empresa_id, lancamento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite estornar lançamentos do livro-caixa nesta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    lancamento = get_object_or_404(LancamentoCaixa, pk=lancamento_id, empresa=empresa)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(
                request,
                ContratoDeRequisicao(
                    campos=frozenset({"csrfmiddlewaretoken"}),
                    aceita_arquivo=False,
                    aceita_querystring=False,
                    cabecalhos_ignorados=("Idempotency-Key",),
                    contexto="no estorno de lançamento de caixa",
                ),
            )
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return render(
                request,
                "livro_caixa/lancamento_estornar.html",
                _contexto_lancamento_estornar(empresa, lancamento),
                status=400,
            )
        try:
            estornar_lancamento_caixa(lancamento, criado_por=request.user, request=request)
        except LancamentoCaixaInvalido as exc:
            messages.error(request, str(exc))
            return render(
                request,
                "livro_caixa/lancamento_estornar.html",
                _contexto_lancamento_estornar(empresa, lancamento),
                status=400,
            )
        messages.success(request, f"Lançamento nº {lancamento.id} estornado com sucesso.")
        return redirect("livro_caixa_web:lancamentos", empresa_id=empresa.id)

    return render(
        request,
        "livro_caixa/lancamento_estornar.html",
        _contexto_lancamento_estornar(empresa, lancamento),
    )


# ---------------------------------------------------------------------------
# Relatório "Livro Caixa" do período (critério 3 do plano; item 4 do FAZER)
# ---------------------------------------------------------------------------


@login_required
@require_safe
def livro_caixa_relatorio(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler o livro-caixa desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    inicio, fim = _periodo_do_formulario_caixa(request)
    carimbo_de_emissao = timezone.localtime()
    contexto = {
        "empresa": empresa,
        "inicio": inicio,
        "fim": fim,
        "cpf_formatado": _mascara_cpf(empresa.cpf),
        "cnpj_formatado": _mascara_cnpj(empresa.cnpj),
        "carimbo_de_emissao_texto": carimbo_de_emissao.strftime("%d/%m/%Y às %H:%M:%S"),
        "timbre_linhas": empresa.escritorio.linhas_do_timbre,
    }
    if inicio is None or fim is None:
        messages.error(request, "O período informado não pôde ser usado.")
        return render(request, "livro_caixa/relatorio.html", contexto, status=400)

    apuracao = apurar_livro_caixa(empresa=empresa, inicio=inicio, fim=fim)
    contexto.update(
        {
            "itens": [
                {
                    "lancamento_id": item["lancamento_id"],
                    "data": item["data"],
                    "conta": item["conta"],
                    "conta_nome": item["conta_nome"],
                    "natureza": item["natureza"],
                    "valor_ptbr": _valor_ptbr(item["valor"]),
                    "historico": item["historico"],
                    "documento_origem": item["documento_origem"],
                    "e_estorno": item["e_estorno"],
                }
                for item in apuracao["itens"]
            ],
            "total_entradas_ptbr": _valor_ptbr(apuracao["total_entradas"]),
            "total_saidas_ptbr": _valor_ptbr(apuracao["total_saidas"]),
            "saldo_ptbr": _valor_ptbr(apuracao["saldo"]),
        }
    )
    return render(request, "livro_caixa/relatorio.html", contexto)
