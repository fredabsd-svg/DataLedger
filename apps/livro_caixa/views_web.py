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
from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_safe

from apps.core.datas import DataInvalida, para_data
from apps.core.dinheiro import ValorMonetarioInvalido, para_decimal
from apps.core.identificadores import IdentificadorInvalido, para_id
from apps.core.requisicao import (
    ContratoDeRequisicao,
    DadoNaoContratado,
    recusar_dado_nao_contratado,
)
from apps.core.restricoes import RestricaoViolada
from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.services import EmpresaNaoEmModoLivroCaixa, recusar_se_nao_livro_caixa
from apps.livro_caixa.carne_leao import (
    DependentesCarneLeaoInvalido,
    TabelaCarneLeaoNaoConfigurada,
    apurar_carne_leao_anual,
    apurar_carne_leao_mensal,
    registrar_dependentes_carne_leao,
    retificar_dependentes_carne_leao,
)
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    DependentesCarneLeaoCliente,
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

    B6 (achado da rodada 1 da auditoria da DL-046): a chave do cache é a
    MESMA que `apps.core.context_processors._empresa_atual` já lê
    (`_dl038_cache_empresa_do_escritorio_ativo`) — antes desta correção
    este módulo usava uma chave própria (`_dl046_cache_...`), e o context
    processor (que roda DEPOIS da view, no MESMO `request`, na
    renderização do template) nunca a encontrava: cada tela do
    livro-caixa pagava uma consulta a mais, só para a trilha de
    navegação resolver de novo a MESMA empresa que a view já tinha
    resolvido. Reaproveitar a chave do cache do context processor
    elimina a consulta duplicada sem duas fontes de cache para o mesmo
    dado — o nome ("dl038") ficou do primeiro módulo a criar o cache, não
    é mais "propriedade" exclusiva da contabilidade.
    """
    cache = getattr(request, "_dl038_cache_empresa_do_escritorio_ativo", None)
    if cache is None:
        cache = {}
        request._dl038_cache_empresa_do_escritorio_ativo = cache
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


def _mascara_caepf(caepf):
    """14 dígitos, sem dígito verificador conhecido (HI-31): os 9
    primeiros são os do CPF do titular, agrupados como CPF
    (999.999.999); os 5 últimos são o "resumido" da inscrição
    (999-99) — mesma leitura de composição da fonte da HI-31, sem
    inventar o algoritmo do DV que a Receita não documenta."""
    if not caepf or len(caepf) != 14:
        return caepf or ""
    return f"{caepf[0:3]}.{caepf[3:6]}.{caepf[6:9]}/{caepf[9:12]}-{caepf[12:14]}"


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
            # N1 (reconferência da DL-046, DE-088 item 2): o servidor
            # (`criar_lancamento_caixa`, `LancamentoCaixa.clean()`) já
            # aceitava este indicador — a tela não o oferecia, e por isso
            # recusava (400) todo rendimento de trabalho não assalariado
            # recebido de PF sem CPF do beneficiário, mesmo quando o
            # leiaute oficial prevê exatamente esse caso (indicador "S").
            "cpf_beneficiario_nao_informado",
            "cnpj_pagador",
            "chave_idempotencia",
        }
    ),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no lançamento de caixa",
)


def _cpf_beneficiario_nao_informado_marcado(dados):
    """Checkbox HTML: presente no POST (qualquer valor) quando marcada,
    AUSENTE quando desmarcada — nunca `"false"` (mesma leitura que
    `ContaCaixaForm`/`ativa` já faz via `forms.BooleanField`, mas este
    campo não passa por `django.forms` porque o restante do formulário
    de lançamento é lido campo a campo do `request.POST`, não por um
    `Form`)."""
    return bool(dados.get("cpf_beneficiario_nao_informado"))


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
        "cpf_beneficiario_nao_informado": _cpf_beneficiario_nao_informado_marcado(dados),
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

        # M1 (rodada 1 da auditoria da DL-046): `conta` chega da tela como
        # TEXTO cru do formulário — "abc", "1.5" ou espaço em branco
        # faziam `ContaLivroCaixa.objects.filter(pk=conta_id, ...)`
        # levantar `ValueError` do ORM (o Django não recusa um `pk`
        # textual malformado antes de montar a consulta), virando 500. A
        # API já não tinha este defeito porque `_extrair_conta`
        # (apps/livro_caixa/views.py) já usa `para_id` — aqui é a MESMA
        # conversão, só que a mensagem de recusa continua a mesma de
        # antes (nenhuma tela de teste dependia do texto da mensagem
        # mudar entre "malformado" e "não encontrado" — os dois casos
        # significam a mesma coisa para quem preenche o formulário:
        # "essa não é uma conta válida desta empresa").
        try:
            conta_id = para_id(request.POST.get("conta") or "")
        except IdentificadorInvalido:
            return _recusa("Escolha uma conta do livro-caixa desta empresa.")
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
                cpf_beneficiario_nao_informado=_cpf_beneficiario_nao_informado_marcado(
                    request.POST
                ),
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

    # B6 (rodada 1 da auditoria da DL-046): `lancamento.estornos.exists()`
    # por LINHA fazia uma consulta a mais por lançamento (14 consultas
    # com 5 lançamentos, 59 com 50 — medido). `Exists(OuterRef("pk"))`
    # anotado na MESMA consulta principal resolve "este lançamento já foi
    # estornado?" para todas as linhas de uma vez, número de consultas
    # CONSTANTE em relação à quantidade de lançamentos — mesmo padrão que
    # `apurar_livro_caixa` (services.py) já segue para esta lista.
    lancamentos = list(
        LancamentoCaixa.objects.filter(empresa=empresa, data__gte=inicio, data__lte=fim)
        .select_related("conta")
        .annotate(_tem_estorno=Exists(LancamentoCaixa.objects.filter(estorno_de=OuterRef("pk"))))
        .order_by("-data", "-id")
    )
    linhas = [
        {
            "lancamento": lancamento,
            "valor_ptbr": _valor_ptbr(lancamento.valor),
            "e_estorno": lancamento.estorno_de_id is not None,
            "ja_estornado": lancamento._tem_estorno,
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
    # M6 (rodada 1 da auditoria da DL-046, DE-087 item 7): a identificação
    # impressa segue o TIPO DE INSCRIÇÃO da empresa, nunca "CPF" fixo —
    # antes desta correção o relatório de uma empresa CNPJ em livro-caixa
    # (o módulo aceita qualquer tipo; a restrição a CPF é só do carnê-leão,
    # fatia 2, decisão do Fred) saía com "— CPF " vazio. Mesmo padrão de
    # `apps.empresas.views.lista_empresas` (`rotulo_inscricao`/
    # `inscricao_formatada`) e de `apps.tenancy.views._empresas_da_
    # carteira` — três lugares que já calculam a MESMA coisa a partir do
    # MESMO enum, cada um com sua própria cópia local de `_mascara_cnpj`/
    # `_mascara_cpf` (docstring do módulo: livro-caixa não importa
    # helper "privado" de outro módulo).
    if empresa.tipo_inscricao == TipoInscricao.CPF:
        rotulo_inscricao = "CPF"
        inscricao_formatada = _mascara_cpf(empresa.cpf)
    else:
        rotulo_inscricao = "CNPJ"
        inscricao_formatada = _mascara_cnpj(empresa.cnpj)
    contexto = {
        "empresa": empresa,
        "inicio": inicio,
        "fim": fim,
        "rotulo_inscricao": rotulo_inscricao,
        "inscricao_formatada": inscricao_formatada,
        # CAEPF (RC-129/HI-31): opcional — o CADASTRO (apps/empresas/
        # forms.py) continua sem máscara, mas a IMPRESSÃO passou a levar
        # `_mascara_caepf` (R-B2 da reconferência) — o template só imprime
        # a linha quando `empresa.caepf` não é vazio.
        "caepf": _mascara_caepf(empresa.caepf),
        "carimbo_de_emissao_texto": carimbo_de_emissao.strftime("%d/%m/%Y às %H:%M:%S"),
        "timbre_linhas": empresa.escritorio.linhas_do_timbre,
    }
    if inicio is None or fim is None:
        messages.error(request, "O período informado não pôde ser usado.")
        return render(request, "livro_caixa/relatorio.html", contexto, status=400)

    apuracao = apurar_livro_caixa(empresa=empresa, inicio=inicio, fim=fim)
    todos_os_itens = [
        {
            "lancamento_id": item["lancamento_id"],
            "data": item["data"],
            "conta": item["conta"],
            "conta_nome": item["conta_nome"],
            "natureza": item["natureza"],
            "valor_ptbr": _valor_ptbr(item["valor"]),
            "historico": item["historico"],
            "documento_origem": item["documento_origem"],
            # M8 (rodada 1 da auditoria da DL-046): o Nº do lançamento
            # original — sem ele, a linha do estorno só dizia "Estorno",
            # sem dizer QUAL lançamento foi estornado (a promessa de
            # `lancamento_estornar.html`: "os dois ficam visíveis na
            # lista e no relatório Livro Caixa, com a referência entre
            # eles" — a lista (`lancamentos_lista.html`) já cumpria; o
            # relatório, não).
            "estorno_de_id": item["estorno_de_id"],
            "e_estorno": item["e_estorno"],
            # D3/N3-N5 (DE-087 item 13, DE-088 item 4): pagamentos P20
            # (imposto pago, previdência oficial, pensão) são DEDUÇÃO do
            # carnê-leão, não despesa de custeio do art. 68.
            # `apurar_livro_caixa` (services.py) já marca cada item com
            # `grupo` — pagamentos P20 vêm como `saida_deducao_carne_leao`
            # — este dicionário só separa o item para o template montar a
            # tabela própria, sem repetir a regra de classificação aqui.
            "eh_pagamento_p20_carne_leao": item.get("grupo") == "saida_deducao_carne_leao",
        }
        for item in apuracao["itens"]
    ]
    contexto.update(
        {
            "itens": [item for item in todos_os_itens if not item["eh_pagamento_p20_carne_leao"]],
            "pagamentos_p20_carne_leao": [
                item for item in todos_os_itens if item["eh_pagamento_p20_carne_leao"]
            ],
            "total_entradas_ptbr": _valor_ptbr(apuracao["total_entradas"]),
            "total_saidas_ptbr": _valor_ptbr(apuracao["total_saidas"]),
            "total_saidas_custeio_ptbr": _valor_ptbr(apuracao["total_saidas_custeio"]),
            "total_saidas_deducao_carne_leao_ptbr": _valor_ptbr(
                apuracao["total_saidas_deducao_carne_leao"]
            ),
            "saldo_ptbr": _valor_ptbr(apuracao["saldo"]),
        }
    )
    return render(request, "livro_caixa/relatorio.html", contexto)


# ---------------------------------------------------------------------------
# Carnê-leão (DL-046, fatia 2) — servidor + API prontos
# (`apps.livro_caixa.carne_leao`, `apps.livro_caixa.views`,
# `desenvolvedor-pleno`, 2026-09-27); este bloco é só a FRENTE DA TELA,
# mesma regra do docstring do módulo: NENHUM cálculo tributário mora aqui.
# Cada função abaixo só FORMATA (pt-BR, `_valor_ptbr`) e RÓTULA o que
# `apurar_carne_leao_mensal`/`apurar_carne_leao_anual` já devolveram —
# nunca reimplementa a fórmula, a tabela, a redução ou a escolha entre
# deduções reais e desconto simplificado (isso é do motor,
# apps/livro_caixa/carne_leao.py, fora do escopo de arquivos desta etapa).
# ---------------------------------------------------------------------------


def _identificacao_do_contribuinte(empresa):
    """`(rotulo_inscricao, inscricao_formatada)` — MESMA regra de
    `livro_caixa_relatorio` (M6, rodada 1 da auditoria da DL-046, DE-087
    item 7): segue o TIPO DE INSCRIÇÃO cadastrado da empresa, nunca "CPF"
    fixo. Extraído aqui como função PRÓPRIA (em vez de repetir o mesmo
    `if`/`else` mais duas vezes, uma por tela desta fatia) — ainda uma
    cópia local do MESMO cálculo de apresentação que `livro_caixa_
    relatorio` já faz inline, por decisão de não tocar naquela view
    funcionando para não arriscar uma regressão nela nesta etapa."""
    if empresa.tipo_inscricao == TipoInscricao.CPF:
        return "CPF", _mascara_cpf(empresa.cpf)
    return "CNPJ", _mascara_cnpj(empresa.cnpj)


# Mesma faixa de ano que `apps.contabilidade.views_web` usa para a
# competência da DRE (`_ANO_MINIMO_COMPETENCIA`/`_ANO_MAXIMO_COMPETENCIA`)
# — cópia LOCAL (docstring do módulo), não importada de lá.
_ANO_MINIMO_CARNE_LEAO, _ANO_MAXIMO_CARNE_LEAO = 1970, 2999
_MES_MINIMO_CARNE_LEAO, _MES_MAXIMO_CARNE_LEAO = 1, 12

# Mesma gramática de dígitos ASCII estritos que a API já usa
# (`_PADRAO_ANO_MES_SIMPLES`, apps/livro_caixa/views.py) — cópia local,
# nunca importada da API (o módulo NUNCA chama nem importa a própria API,
# docstring do topo deste arquivo).
_PADRAO_ANO_MES_CARNE_LEAO = re.compile(r"^[0-9]{1,4}$")


def _competencia_carne_leao_adjacente(ano, mes, delta_meses):
    """Competência (ano, mês) deslocada por `delta_meses` — mesma
    aritmética PURA de `_competencia_adjacente` (apps.contabilidade.
    views_web), cópia local pelo mesmo motivo do docstring do módulo.
    Também usada para achar o MÊS SEGUINTE de uma competência (o mês de
    vencimento do DARF, RIR/2018 art. 123) — é só deslocamento de
    calendário civil, nunca resolução de dia útil nem feriado (a tarefa
    desta etapa pede explicitamente para NÃO calcular isso)."""
    indice = (ano * 12) + (mes - 1) + delta_meses
    return indice // 12, indice % 12 + 1


def _ano_mes_carne_leao_valido(ano, mes):
    return (
        ano is not None
        and mes is not None
        and _ANO_MINIMO_CARNE_LEAO <= ano <= _ANO_MAXIMO_CARNE_LEAO
        and _MES_MINIMO_CARNE_LEAO <= mes <= _MES_MAXIMO_CARNE_LEAO
    )


def _competencia_carne_leao_do_formulario(request):
    """Lê 'ano'/'mes' da querystring do demonstrativo MENSAL — mesma
    gramática e o mesmo padrão de ausência-usa-mês-corrente de
    `_competencia_dre_do_formulario` (apps.contabilidade.views_web), cópia
    local. Devolve `(ano, mes, erro_ou_none)` — nunca lança exceção."""
    bruto_ano = request.GET.get("ano")
    bruto_mes = request.GET.get("mes")
    if not bruto_ano and not bruto_mes:
        hoje = timezone.localdate()
        return hoje.year, hoje.month, None
    if not bruto_ano or not _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(bruto_ano):
        return None, None, "Informe 'ano' (dígitos) na querystring."
    if not bruto_mes or not _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(bruto_mes):
        return None, None, "Informe 'mes' (dígitos, 1 a 12) na querystring."
    ano = int(bruto_ano)
    mes = int(bruto_mes)
    if not (_ANO_MINIMO_CARNE_LEAO <= ano <= _ANO_MAXIMO_CARNE_LEAO):
        return (
            None,
            None,
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO_CARNE_LEAO} e "
            f"{_ANO_MAXIMO_CARNE_LEAO}.",
        )
    if not (_MES_MINIMO_CARNE_LEAO <= mes <= _MES_MAXIMO_CARNE_LEAO):
        return None, None, f"'mes' inválido: {mes} — deve estar entre 1 e 12."
    return ano, mes, None


def _ano_carne_leao_do_formulario(request):
    """Mesma ideia de `_competencia_carne_leao_do_formulario`, só para
    'ano' — usada pelo demonstrativo ANUAL."""
    bruto_ano = request.GET.get("ano")
    if not bruto_ano:
        return timezone.localdate().year, None
    if not _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(bruto_ano):
        return None, "Informe 'ano' (dígitos) na querystring."
    ano = int(bruto_ano)
    if not (_ANO_MINIMO_CARNE_LEAO <= ano <= _ANO_MAXIMO_CARNE_LEAO):
        return (
            None,
            f"'ano' inválido: {ano} — deve estar entre {_ANO_MINIMO_CARNE_LEAO} e "
            f"{_ANO_MAXIMO_CARNE_LEAO}.",
        )
    return ano, None


# Código do modelo ALUGUEL/OUTROS (aluguel) — usado só para decidir se o
# aviso do art. 42 do RIR/2018 aparece na tela (item 3 da tarefa da
# integração, 2026-09-27). `apps.livro_caixa.validators` não exporta este
# código como constante pública (só os dois usados na regra do limite do
# livro-caixa, `CODIGO_RENDIMENTO_TRABALHO_NAO_ASSALARIADO`/`CODIGO_
# RENDIMENTO_NOTARIAL`) — cópia local do MESMO literal que `_CODIGO_PARA_
# MODELO_DE_RENDIMENTO` (validators.py) usa para o modelo aluguel/outros,
# nunca uma regra nova: só decide se um AVISO aparece, não altera cálculo
# nenhum.
_CODIGO_RENDIMENTO_ALUGUEL = "R01.003.001"


def _ha_rendimento_de_aluguel(rendimentos):
    return any(item["codigo"] == _CODIGO_RENDIMENTO_ALUGUEL for item in rendimentos)


def _faixa_aplicada_ptbr(faixa):
    """Formata a faixa da tabela progressiva que `_pipeline` (motor) já
    escolheu (`faixa_aplicada`, item 7 do contrato da API — acréscimo do
    arquiteto-senior) — `limite_inferior`/`limite_superior`/`parcela_a_
    deduzir` em reais, `aliquota` em PERCENTUAL.

    ⚠️ Multiplicar a alíquota por 100 aqui é conversão de UNIDADE para
    exibição (a fração 0,0750 armazenada no banco é a mesma "7,50%" que
    a tabela oficial imprime), não uma regra de cálculo tributário — a
    mesma classe de operação que `_valor_ptbr` já faz ao formatar
    Decimal para texto; nenhum valor NOVO nasce aqui, só a notação
    muda."""
    return {
        "limite_inferior_ptbr": _valor_ptbr(faixa["limite_inferior"]),
        # `tem_limite_superior` (SEM sufixo `_ptbr`, de propósito): o
        # template testa esta chave no `{% if %}` que decide entre "até
        # X" e "sem limite" — nunca a chave `_ptbr`, para a varredura de
        # interface (`test_todo_valor_em_celula_usa_a_classe_do_sistema`)
        # não confundir uma CONDIÇÃO com um VALOR monetário impresso sem
        # a classe do sistema.
        "tem_limite_superior": faixa["limite_superior"] is not None,
        "limite_superior_ptbr": (
            _valor_ptbr(faixa["limite_superior"]) if faixa["limite_superior"] is not None else None
        ),
        "aliquota_ptbr": _valor_ptbr(faixa["aliquota"] * 100) + "%",
        "parcela_a_deduzir_ptbr": _valor_ptbr(faixa["parcela_a_deduzir"]),
    }


def _pipeline_carne_leao_ptbr(pipeline):
    """Formata em pt-BR uma das duas memórias de cálculo que `_apurar_um_
    mes` (motor) já produz — `memoria_deducoes_reais`/`memoria_desconto_
    simplificado`, cada uma com `base`/`imposto_tabela`/`reducao_
    disponivel`/`reducao_aplicada`/`imposto_apos_reducao`/`faixa_aplicada`/
    `vigencia_tabela_inicio` (os dois últimos, acréscimo do
    arquiteto-senior, item 7 do contrato da API). Só formatação, nenhum
    valor novo."""
    return {
        "base_ptbr": _valor_ptbr(pipeline["base"]),
        "imposto_tabela_ptbr": _valor_ptbr(pipeline["imposto_tabela"]),
        "reducao_disponivel_ptbr": _valor_ptbr(pipeline["reducao_disponivel"]),
        "reducao_aplicada_ptbr": _valor_ptbr(pipeline["reducao_aplicada"]),
        "imposto_apos_reducao_ptbr": _valor_ptbr(pipeline["imposto_apos_reducao"]),
        "faixa_aplicada": _faixa_aplicada_ptbr(pipeline["faixa_aplicada"]),
        "vigencia_tabela_inicio": pipeline["vigencia_tabela_inicio"],
    }


def _rendimentos_para_contexto(rendimentos):
    """Formata a lista `rendimentos` (item 7/M-2 do contrato da API —
    `{codigo, origem, valor, entra_na_base, motivo_exclusao}`, já pronta
    pelo motor) para a tela — só `_valor_ptbr` e o rótulo por extenso da
    origem (`OrigemRecebimento`, já usado pelo cadastro de lançamento).
    Esta é a resposta ao achado próprio da entrega anterior desta etapa
    (o motor não detalhava rendimento por código): agora detalha, e a
    tela mostra o detalhamento REAL, não mais só as categorias
    agregadas."""
    return [
        {
            "codigo": item["codigo"],
            "origem_label": OrigemRecebimento(item["origem"]).label if item["origem"] else "—",
            "valor_ptbr": _valor_ptbr(item["valor"]),
            "entra_na_base": item["entra_na_base"],
            "motivo_exclusao": item["motivo_exclusao"],
        }
        for item in rendimentos
    ]


def _mes_sem_rendimento_sujeito(mes_resultado):
    """Achado (b) da verificação independente do fechamento de R-A1
    (2026-09-27, decisão do arquiteto-senior) — PRESENTATION, isolada
    neste ÚNICO ponto e reaproveitada pelas DUAS telas (mensal e
    anual), nunca reescrita em cada uma.

    Por quê: `desconto_simplificado` (`apps.livro_caixa.carne_leao.
    _apurar_um_mes`) é um TETO da tabela — um percentual do limite da
    faixa zero, calculado sobre a TABELA, nunca sobre o rendimento do
    mês — por isso é positivo mesmo num mês sem nenhum rendimento
    sujeito. Como ele é sempre >= deduções reais (0,00 sem movimento
    nenhum), `forma_escolhida` do motor "vence" para "simplificado"
    por definição, e `deducao_aplicada` sai um valor positivo (ex.:
    "607,20") — sem esta distinção, a tela mostraria essa dedução como
    se tivesse sido de fato aplicada a um rendimento que não existiu.

    Só isola a CONDIÇÃO de apresentação — nunca decide nada do motor:
    `forma_escolhida`/`deducao_aplicada`/`desconto_simplificado`
    continuam vindo do motor sem alteração nenhuma; só o que a tela
    ESCREVE nas células muda, e só quando esta função devolve
    verdadeiro."""
    return mes_resultado["rendimento_total_sujeito"] == 0


def _contexto_resultado_mensal_carne_leao(resultado):
    """Traduz o dicionário que `apurar_carne_leao_mensal` devolve (motor,
    apps/livro_caixa/carne_leao.py, já com a correção da rodada 1 da
    auditoria/DE-091) para o contexto pt-BR do template — cada chave
    `*_ptbr` é só `_valor_ptbr` sobre o valor que o motor já calculou;
    `criterio_escolha_forma`, `vencimento` e `alertas` são texto PRONTO do
    motor, impressos como estão — esta função nunca decide qual critério
    foi aplicado, nunca calcula o mês de vencimento e nunca decide se há
    alerta: só formata e agrupa o que já veio pronto."""
    return {
        "ano": resultado["ano"],
        "mes": resultado["mes"],
        "data_referencia": date(resultado["ano"], resultado["mes"], 1),
        "vencimento": resultado["vencimento"],
        "rendimento_total_sujeito_ptbr": _valor_ptbr(resultado["rendimento_total_sujeito"]),
        "rendimento_trabalho_base_ptbr": _valor_ptbr(resultado["rendimento_trabalho_base"]),
        "rendimento_notarial_base_ptbr": _valor_ptbr(resultado["rendimento_notarial_base"]),
        "rendimentos": _rendimentos_para_contexto(resultado["rendimentos"]),
        "ha_rendimento_de_aluguel": _ha_rendimento_de_aluguel(resultado["rendimentos"]),
        "previdencia_oficial_ptbr": _valor_ptbr(resultado["previdencia_oficial"]),
        "pensao_alimenticia_paga_ptbr": _valor_ptbr(resultado["pensao_alimenticia_paga"]),
        "dependentes_quantidade": resultado["dependentes_quantidade"],
        "dependentes_valor_ptbr": _valor_ptbr(resultado["dependentes_valor"]),
        # R-B4 (reconferência) — valor por dependente E a vigência que a
        # produz, para a memória mostrar de ONDE o valor total de
        # dependentes vem (antes só o total, sem o fator).
        "valor_por_dependente_ptbr": _valor_ptbr(resultado["valor_por_dependente"]),
        "receita_atividade_limite_livro_caixa_ptbr": _valor_ptbr(
            resultado["receita_atividade_limite_livro_caixa"]
        ),
        "despesa_livro_caixa_do_mes_ptbr": _valor_ptbr(resultado["despesa_livro_caixa_do_mes"]),
        "excesso_livro_caixa_anterior_ptbr": _valor_ptbr(resultado["excesso_livro_caixa_anterior"]),
        "deducao_livro_caixa_aplicada_ptbr": _valor_ptbr(resultado["deducao_livro_caixa_aplicada"]),
        "excesso_livro_caixa_novo_ptbr": _valor_ptbr(resultado["excesso_livro_caixa_novo"]),
        "excesso_livro_caixa_existe": resultado["excesso_livro_caixa_novo"] > 0,
        "deducoes_reais_total_ptbr": _valor_ptbr(resultado["deducoes_reais_total"]),
        "desconto_simplificado_ptbr": _valor_ptbr(resultado["desconto_simplificado"]),
        "forma_escolhida": resultado["forma_escolhida"],
        # Achado (b), reconferência (2026-09-27) — a linha "Forma aplicada
        # neste mês" (carne_leao_mensal.html) usa este rótulo em vez de
        # `forma_escolhida` cru: sem rendimento sujeito no mês, dizer
        # "Desconto simplificado" sugeriria que algum valor foi de fato
        # deduzido de um rendimento que não existiu (ver o docstring de
        # `_mes_sem_rendimento_sujeito`, acima — a mesma função que o
        # anual usa). O RESTANTE da memória (as duas linhas "Imposto após
        # redução — pela via de...", com o selo "Aplicada") continua
        # mostrando a comparação REAL que o motor fez, sem alteração — é
        # a memória de cálculo completa (classe 1, NBC TG 26 item 51), e
        # só a frase-resumo desta ÚLTIMA linha muda.
        "forma_aplicada_rotulo": (
            "Sem rendimento sujeito no mês"
            if _mes_sem_rendimento_sujeito(resultado)
            else (
                "Deduções reais"
                if resultado["forma_escolhida"] == "real"
                else "Desconto simplificado"
            )
        ),
        # Texto PRONTO do motor (item 7 do contrato da API, DE-091) — a
        # tela NUNCA descreve um critério que o motor não aplicou (ver a
        # seção "Achado material" do plano DL-046 sobre a versão anterior
        # deste campo, que isolava um texto fixo enquanto o motor corrigido
        # não chegava a este worktree).
        "criterio_escolha_forma": resultado["criterio_escolha_forma"],
        "memoria_deducoes_reais": _pipeline_carne_leao_ptbr(resultado["memoria_deducoes_reais"]),
        "memoria_desconto_simplificado": _pipeline_carne_leao_ptbr(
            resultado["memoria_desconto_simplificado"]
        ),
        "base_de_calculo_ptbr": _valor_ptbr(resultado["base_de_calculo"]),
        "imposto_pela_tabela_ptbr": _valor_ptbr(resultado["imposto_pela_tabela"]),
        "reducao_lei_15270_2025_ptbr": _valor_ptbr(resultado["reducao_lei_15270_2025"]),
        # R-B4 (reconferência) — sem vigência de redução (legítimo antes
        # de 2026-01-01, R-B3) a linha da redução precisa dizer isso, em
        # vez de deixar 0,00 parecer que a redução foi CALCULADA e deu
        # zero.
        "reducao_vigente": resultado["reducao_vigente"],
        "imposto_apos_reducao_ptbr": _valor_ptbr(resultado["imposto_apos_reducao"]),
        "imposto_com_exterior_ptbr": _valor_ptbr(resultado["imposto_com_exterior"]),
        "imposto_sem_exterior_ptbr": _valor_ptbr(resultado["imposto_sem_exterior"]),
        # "Há rendimento do exterior" (para mostrar a comparação com/sem
        # exterior só quando ela faz sentido) — leitura direta da lista
        # `rendimentos` que o motor já classificou, não uma conta nova.
        "ha_rendimento_exterior": any(
            item["origem"] == "EX" and item["entra_na_base"] for item in resultado["rendimentos"]
        ),
        "imposto_pago_exterior_do_mes_ptbr": _valor_ptbr(resultado["imposto_pago_exterior_do_mes"]),
        "limite_compensacao_exterior_ptbr": _valor_ptbr(resultado["limite_compensacao_exterior"]),
        "compensacao_exterior_aplicada_ptbr": _valor_ptbr(
            resultado["compensacao_exterior_aplicada"]
        ),
        # R-B4 (reconferência) — a parte do imposto pago no exterior que
        # NUNCA compensa neste mês (passa do limite) ficava sem rótulo
        # próprio na memória; agora rotulada, e só aparece quando > 0.
        "imposto_exterior_nao_compensavel_ptbr": _valor_ptbr(
            resultado["imposto_exterior_nao_compensavel"]
        ),
        "ha_imposto_exterior_nao_compensavel": resultado["imposto_exterior_nao_compensavel"] > 0,
        "saldo_credito_exterior_novo_ptbr": _valor_ptbr(resultado["saldo_credito_exterior_novo"]),
        "ha_credito_exterior": resultado["saldo_credito_exterior_novo"] > 0,
        "imposto_devido_no_mes_ptbr": _valor_ptbr(resultado["imposto_devido_no_mes"]),
        "saldo_pendente_abaixo_de_dez_anterior_ptbr": _valor_ptbr(
            resultado["saldo_pendente_abaixo_de_dez_anterior"]
        ),
        "valor_a_pagar_ptbr": _valor_ptbr(resultado["valor_a_pagar"]),
        "ha_valor_a_pagar": resultado["valor_a_pagar"] > 0,
        "saldo_pendente_abaixo_de_dez_novo_ptbr": _valor_ptbr(
            resultado["saldo_pendente_abaixo_de_dez_novo"]
        ),
        "ha_saldo_pendente_abaixo_de_dez": resultado["saldo_pendente_abaixo_de_dez_novo"] > 0,
        "codigo_darf": resultado["codigo_darf"],
        "tabela_vigencia_inicio": resultado["tabela_vigencia_inicio"],
        "reducao_vigencia_inicio": resultado["reducao_vigencia_inicio"],
        "dependente_vigencia_inicio": resultado["dependente_vigencia_inicio"],
        "alertas": resultado["alertas"],
        "sem_movimento_no_mes": (
            resultado["rendimento_total_sujeito"] == 0 and resultado["deducoes_reais_total"] == 0
        ),
    }


@login_required
@require_safe
def carne_leao_mensal(request, empresa_id):
    """Demonstrativo MENSAL do carnê-leão (DL-046, fatia 2) — arquétipos D
    (painel de período) e A (documento de conferência) combinados: a
    navegação de competência "‹ Mês anterior / Mês seguinte ›" é a MESMA
    ideia de `contabilidade_web:dre` (`_competencia_adjacente`, cópia
    local), e o quadro abaixo é a memória de cálculo COMPLETA que o motor
    (`apps.livro_caixa.carne_leao.apurar_carne_leao_mensal`) devolve —
    esta view NUNCA calcula (ver o docstring de `_contexto_resultado_
    mensal_carne_leao`, acima).
    """
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler o carnê-leão desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    rotulo_inscricao, inscricao_formatada = _identificacao_do_contribuinte(empresa)
    contexto = {
        "empresa": empresa,
        "rotulo_inscricao": rotulo_inscricao,
        "inscricao_formatada": inscricao_formatada,
        "caepf": _mascara_caepf(empresa.caepf),
        # Igual a `livro_caixa_relatorio`: carimbo e timbre são
        # preenchidos SEMPRE, mesmo em estado de erro — o documento
        # continua identificando o emitente/contribuinte mesmo quando a
        # competência pedida não pôde ser usada.
        "carimbo_de_emissao_texto": timezone.localtime().strftime("%d/%m/%Y às %H:%M:%S"),
        "timbre_linhas": empresa.escritorio.linhas_do_timbre,
    }

    ano, mes, erro = _competencia_carne_leao_do_formulario(request)
    if erro:
        messages.error(request, erro)
        return render(request, "livro_caixa/carne_leao_mensal.html", contexto, status=400)

    ano_anterior, mes_anterior = _competencia_carne_leao_adjacente(ano, mes, -1)
    ano_seguinte, mes_seguinte = _competencia_carne_leao_adjacente(ano, mes, 1)
    contexto.update(
        {
            "ano": ano,
            "mes": mes,
            "data_referencia": date(ano, mes, 1),
            "ano_anterior": ano_anterior
            if _ano_mes_carne_leao_valido(ano_anterior, mes_anterior)
            else None,
            "mes_anterior": mes_anterior,
            "ano_seguinte": ano_seguinte
            if _ano_mes_carne_leao_valido(ano_seguinte, mes_seguinte)
            else None,
            "mes_seguinte": mes_seguinte,
        }
    )

    try:
        resultado = apurar_carne_leao_mensal(empresa=empresa, ano=ano, mes=mes)
    except TabelaCarneLeaoNaoConfigurada as exc:
        # 409: não é erro de quem preencheu o formulário — é AUSÊNCIA de
        # dado normativo vigente para a competência pedida (tabela,
        # redução ou valor por dependente), sempre um problema de
        # configuração do servidor (critério 5 do plano: "nenhum número
        # normativo no código" — a migração de dados que semeia essas
        # tabelas pode simplesmente não cobrir a competência pedida).
        messages.error(request, str(exc))
        contexto["erro_configuracao"] = True
        contexto["mensagem_erro_carne_leao"] = str(exc)
        return render(request, "livro_caixa/carne_leao_mensal.html", contexto, status=409)

    contexto["erro_configuracao"] = False
    contexto.update(_contexto_resultado_mensal_carne_leao(resultado))
    return render(request, "livro_caixa/carne_leao_mensal.html", contexto)


def _linha_anual_carne_leao(mes_resultado):
    """Uma linha da tabela do demonstrativo ANUAL — só formatação/rótulo
    sobre o dicionário que o motor já devolve para aquele mês (mesmo
    formato de `_apurar_um_mes`, reaproveitado por `apurar_carne_leao_
    anual`). As colunas espelham, uma a uma, os 8 campos de
    `resultado["totais"]` (item 7/M-2 do contrato da API) — para a linha
    de TOTAL (`_totais_anuais_ptbr`, abaixo) bater exatamente com a soma
    visível de cada coluna.

    ⚠️ **N21 (reconferência) — `deducao_aplicada` vem do MOTOR, nunca
    escolhida aqui.** Até a correção da reconferência, esta função
    reimplementava a seleção "simplificado? desconto : deduções reais"
    (mesma regra que `_totais_anuais`, no motor, já fazia) — a
    DUPLICAÇÃO em duas camadas foi exatamente o que deixou a coluna sem
    cobertura de teste (o mutante "sempre usa deduções reais" sobrevivia
    à suíte do desenvolvedor). O motor agora devolve `deducao_aplicada`
    pronta em CADA mês (mesmo campo que `_totais_anuais` soma para o
    total do ano); esta função só formata.

    ⚠️ **Achado (b), reconferência (2026-09-27) — "Dedução aplicada" e
    "Forma" mostram "—" num mês sem rendimento sujeito.** Mesma razão
    do mensal (ver `_mes_sem_rendimento_sujeito`, acima, reaproveitada
    aqui, nunca reescrita): `deducao_aplicada` do motor é positiva
    mesmo sem rendimento (é o TETO do desconto simplificado, não uma
    fração do rendimento) — sem esta exceção a linha do mês pareceria
    ter aplicado uma dedução real a uma renda que não existiu. Só
    apresentação: `sem_rendimento_sujeito` não muda nenhum dos oito
    totais nem a soma do ano (`totais`/`_totais_anuais_ptbr`, que
    continuam somando o valor VERDADEIRO que o motor devolveu — só a
    CÉLULA deste mês, na tela, mostra "—" em vez do número)."""
    sem_rendimento_sujeito = _mes_sem_rendimento_sujeito(mes_resultado)
    return {
        "mes": mes_resultado["mes"],
        "data_referencia": date(mes_resultado["ano"], mes_resultado["mes"], 1),
        "rendimento_total_sujeito_ptbr": _valor_ptbr(mes_resultado["rendimento_total_sujeito"]),
        "sem_rendimento_sujeito": sem_rendimento_sujeito,
        "deducao_aplicada_ptbr": (
            "—" if sem_rendimento_sujeito else _valor_ptbr(mes_resultado["deducao_aplicada"])
        ),
        "forma_escolhida": mes_resultado["forma_escolhida"],
        "base_de_calculo_ptbr": _valor_ptbr(mes_resultado["base_de_calculo"]),
        "imposto_pela_tabela_ptbr": _valor_ptbr(mes_resultado["imposto_pela_tabela"]),
        "reducao_lei_15270_2025_ptbr": _valor_ptbr(mes_resultado["reducao_lei_15270_2025"]),
        "compensacao_exterior_aplicada_ptbr": _valor_ptbr(
            mes_resultado["compensacao_exterior_aplicada"]
        ),
        "imposto_devido_no_mes_ptbr": _valor_ptbr(mes_resultado["imposto_devido_no_mes"]),
        "valor_a_pagar_ptbr": _valor_ptbr(mes_resultado["valor_a_pagar"]),
    }


def _totais_anuais_ptbr(totais):
    """Só FORMATA os 8 campos que `apurar_carne_leao_anual` já soma
    (`resultado["totais"]`, item 7/M-2 do contrato da API,
    `apps.livro_caixa.carne_leao._totais_anuais`) — NENHUMA soma nasce
    nesta view; a soma exata dos 12 meses é inteiramente do motor."""
    return {campo: _valor_ptbr(valor) for campo, valor in totais.items()}


@login_required
@require_safe
def carne_leao_anual(request, empresa_id):
    """Demonstrativo ANUAL do carnê-leão — os 12 meses do ano-calendário
    (`apps.livro_caixa.carne_leao.apurar_carne_leao_anual`), com
    `resultado["totais"]` do próprio motor só FORMATADO para pt-BR
    (`_totais_anuais_ptbr`, acima) — nenhuma soma nasce aqui (R-B5 da
    reconferência: esta docstring citava `_totais_anuais_carne_leao`,
    função removida na integração com o servidor corrigido)."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler o carnê-leão desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    rotulo_inscricao, inscricao_formatada = _identificacao_do_contribuinte(empresa)
    contexto = {
        "empresa": empresa,
        "rotulo_inscricao": rotulo_inscricao,
        "inscricao_formatada": inscricao_formatada,
        "caepf": _mascara_caepf(empresa.caepf),
        "carimbo_de_emissao_texto": timezone.localtime().strftime("%d/%m/%Y às %H:%M:%S"),
        "timbre_linhas": empresa.escritorio.linhas_do_timbre,
    }

    ano, erro = _ano_carne_leao_do_formulario(request)
    if erro:
        messages.error(request, erro)
        return render(request, "livro_caixa/carne_leao_anual.html", contexto, status=400)

    ano_anterior = ano - 1
    ano_seguinte = ano + 1
    contexto.update(
        {
            "ano": ano,
            "ano_anterior": ano_anterior
            if _ANO_MINIMO_CARNE_LEAO <= ano_anterior <= _ANO_MAXIMO_CARNE_LEAO
            else None,
            "ano_seguinte": ano_seguinte
            if _ANO_MINIMO_CARNE_LEAO <= ano_seguinte <= _ANO_MAXIMO_CARNE_LEAO
            else None,
        }
    )

    try:
        resultado = apurar_carne_leao_anual(empresa=empresa, ano=ano)
    except TabelaCarneLeaoNaoConfigurada as exc:
        messages.error(request, str(exc))
        contexto["erro_configuracao"] = True
        contexto["mensagem_erro_carne_leao"] = str(exc)
        return render(request, "livro_caixa/carne_leao_anual.html", contexto, status=409)

    contexto["erro_configuracao"] = False
    contexto["linhas"] = [_linha_anual_carne_leao(mes) for mes in resultado["meses"]]
    contexto["totais"] = _totais_anuais_ptbr(resultado["totais"])
    return render(request, "livro_caixa/carne_leao_anual.html", contexto)


# ---------------------------------------------------------------------------
# Dependentes do carnê-leão (HI-35) — quantidade por vigência mensal.
# ---------------------------------------------------------------------------


class DependentesCarneLeaoForm(forms.ModelForm):
    class Meta:
        model = DependentesCarneLeaoCliente
        fields = ["quantidade", "competencia_inicio"]
        widgets = {"competencia_inicio": forms.DateInput(attrs={"type": "date"})}
        labels = {
            "quantidade": "Quantidade de dependentes",
            "competencia_inicio": "Vigente a partir de (mês)",
        }
        help_texts = {
            "competencia_inicio": (
                "Escolha o dia 1 do mês em que a quantidade passa a valer — "
                "ex.: 01/10/2026 para vigorar a partir de outubro de 2026."
            ),
        }


_CONTRATO_DO_FORMULARIO_DE_DEPENDENTES_CARNE_LEAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "quantidade", "competencia_inicio"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no registro de dependentes do carnê-leão",
)


@login_required
@require_http_methods(["GET", "POST"])
def dependentes_carne_leao(request, empresa_id):
    """Arquétipos A (tabela de vigências) + B (formulário) combinados na
    mesma tela — mesmo molde de `contabilidade_web:parametros_contabeis`
    (poucas vigências por empresa, ao longo dos anos, nunca justifica uma
    segunda navegação). A gravação passa inteira por `apps.livro_caixa.
    carne_leao.registrar_dependentes_carne_leao` — autorização real no
    SERVIDOR (dentro do serviço, `recusar_se_nao_livro_caixa` sob
    `select_for_update()`); `pode_escriturar`, aqui, só decide o que a
    TELA oferece."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler os dependentes do carnê-leão desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    pode_escriturar = _pode_escriturar(request)
    form = None

    if request.method == "POST":
        if not pode_escriturar:
            return _resposta_sem_permissao(
                request,
                "Seu papel não permite registrar dependentes do carnê-leão desta empresa.",
            )
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_DO_FORMULARIO_DE_DEPENDENTES_CARNE_LEAO)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)

        form = DependentesCarneLeaoForm(request.POST)
        if form.is_valid():
            try:
                registrar_dependentes_carne_leao(
                    empresa=empresa,
                    quantidade=form.cleaned_data["quantidade"],
                    competencia_inicio=form.cleaned_data["competencia_inicio"],
                    criado_por=request.user,
                    request=request,
                )
            except DependentesCarneLeaoInvalido as exc:
                # `full_clean()` (dentro do serviço) devolve, entre outros,
                # o erro de "sempre o dia 1 do mês" (Model.clean()) — texto
                # único no formulário inteiro (`add_error(None, ...)`),
                # mesmo padrão de `ParametroContabilInvalido` em
                # `contabilidade_web.parametros_contabeis`: o serviço não
                # separa por campo neste erro.
                form.add_error(None, str(exc))
            except RestricaoViolada as exc:
                # Corrida na `UniqueConstraint` "dependentes_carne_leao_
                # competencia_unica_por_empresa" — mesmo padrão de
                # `parametro_contabil`/`registrar_regime_tributario`.
                form.add_error("competencia_inicio", str(exc))
            else:
                messages.success(
                    request, "Quantidade de dependentes do carnê-leão registrada com sucesso."
                )
                return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)
    elif pode_escriturar:
        form = DependentesCarneLeaoForm()

    vigencias = list(
        DependentesCarneLeaoCliente.objects.filter(empresa=empresa).order_by("-competencia_inicio")
    )
    contexto = {
        "empresa": empresa,
        "vigencias": vigencias,
        "pode_escriturar": pode_escriturar,
        "form": form,
    }
    status = 400 if form is not None and form.is_bound and form.errors else 200
    return render(request, "livro_caixa/dependentes_carne_leao.html", contexto, status=status)


_CONTRATO_RETIFICAR_DEPENDENTES_CARNE_LEAO = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "quantidade"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na retificação de dependentes do carnê-leão",
)


@login_required
@require_http_methods(["POST"])
def dependentes_carne_leao_retificar(request, empresa_id, dependente_id):
    """DE-091 item 6 (M-6) — corrige a QUANTIDADE de um registro já
    existente (nunca cria um novo; a competência de vigência não muda).
    Rota de AÇÃO (só POST, sem tela própria — o formulário fica inline na
    tabela de `dependentes_carne_leao`, mesmo padrão de "Encerrar
    vigência" em `contabilidade_web:parametro_contabil_encerrar`): sucesso
    e erro voltam para a MESMA tela, por mensagem (`django.contrib.
    messages`), nunca uma segunda página."""
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(
            request,
            "Seu papel não permite retificar dependentes do carnê-leão desta empresa.",
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return recusa

    # Isolamento: `registro` só é alcançado se pertencer a ESTA empresa —
    # mesmo padrão de `EstornarLancamentoCaixaView`/`lancamento_caixa_
    # estornar` (a view busca com `empresa=empresa` ANTES de chamar o
    # serviço; um `dependente_id` de outra empresa/escritório já vira 404
    # aqui, antes de qualquer autorização adicional do serviço).
    registro = get_object_or_404(DependentesCarneLeaoCliente, pk=dependente_id, empresa=empresa)

    try:
        recusar_dado_nao_contratado(request, _CONTRATO_RETIFICAR_DEPENDENTES_CARNE_LEAO)
    except DadoNaoContratado as exc:
        messages.error(request, exc.mensagem)
        return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)

    try:
        quantidade = para_id(request.POST.get("quantidade") or "")
    except IdentificadorInvalido:
        messages.error(
            request,
            "Informe uma quantidade de dependentes válida (número inteiro, não negativo).",
        )
        return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)

    try:
        retificar_dependentes_carne_leao(
            registro, quantidade=quantidade, retificado_por=request.user, request=request
        )
    except DependentesCarneLeaoInvalido as exc:
        messages.error(request, str(exc))
        return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)

    messages.success(
        request,
        f"Quantidade de dependentes vigente desde {registro.competencia_inicio.strftime('%m/%Y')} "
        "retificada com sucesso.",
    )
    return redirect("livro_caixa_web:dependentes_carne_leao", empresa_id=empresa.id)
