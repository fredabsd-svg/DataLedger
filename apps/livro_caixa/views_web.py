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

import calendar
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
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
from apps.livro_caixa.carne_leao_arquivos import (
    GeracaoArquivoCarneLeaoBloqueada,
    PeriodoInvalidoParaArquivoCarneLeaoWeb,
    conferencia_sem_movimento,
    gerar_arquivos_carne_leao,
)
from apps.livro_caixa.models import (
    ContaLivroCaixa,
    DependentesCarneLeaoCliente,
    EstadoMesCaixa,
    FechamentoMesCaixa,
    LancamentoCaixa,
    NaturezaCaixa,
    OrigemRecebimento,
)
from apps.livro_caixa.permissoes import (
    papel_pode_escriturar_livro_caixa,
    papel_pode_fechar_mes_caixa,
    papel_pode_ler_livro_caixa,
)
from apps.livro_caixa.services import (
    TAMANHO_MAXIMO_MOTIVO_REABERTURA,
    ChaveIdempotenciaConflitanteCaixa,
    FechamentoMesCaixaInvalido,
    FechamentoMesCaixaRecusado,
    LancamentoCaixaInvalido,
    MesCaixaEncerrado,
    MesCaixaOcupado,
    apurar_livro_caixa,
    criar_conta_livro_caixa,
    criar_lancamento_caixa,
    encerrar_mes_caixa,
    estado_dos_meses_caixa,
    estornar_lancamento_caixa,
    mes_caixa_esta_encerrado,
    reabrir_mes_caixa,
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


def _pode_fechar_mes(request):
    return papel_pode_fechar_mes_caixa(getattr(request, "papel", None))


def _meses_encerrados(empresa, ano_inicial, ano_final):
    """Conjunto `{(ano, mes)}` dos meses ENCERRADOS de `empresa` entre os
    dois anos (inclusive) — UMA consulta, sem lock. Só informa a TELA (aviso
    de mês encerrado e ausência do botão de estornar); a recusa de verdade é
    da trava de `criar_lancamento_caixa`, que lê o estado sob lock (DL-053).
    Estado desconhecido NÃO conta como encerrado aqui: a tela só deixa de
    oferecer a ação quando tem certeza, e o servidor recusa de qualquer
    forma quando o estado não for "aberto"."""
    return set(
        FechamentoMesCaixa.objects.filter(
            empresa=empresa,
            estado=EstadoMesCaixa.ENCERRADO,
            ano__gte=ano_inicial,
            ano__lte=ano_final,
        ).values_list("ano", "mes")
    )


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
        fields = ["codigo", "nome", "natureza", "codigo_carne_leao", "codigo_ocupacao", "ativa"]
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
            # DL-046 fatia 3 (HI-34): sobreposição OPCIONAL da ocupação do
            # cliente — quando preenchida, é esta que entra no arquivo do
            # Carnê-Leão Web, no lugar da de `Empresa`. Obrigatória na
            # prática para a conta notarial (que é sempre 117) e para o
            # trabalho não assalariado quando a linha do arquivo precisa da
            # ocupação; `ContaLivroCaixa.clean()` é quem recusa ocupação
            # fora desses dois modelos de rendimento.
            "codigo_ocupacao": (
                "3 dígitos da tabela oficial de ocupações do Carnê-Leão Web, "
                "sobrepõe a ocupação do cliente nesta conta. Só para conta de "
                "RECEITA de trabalho não assalariado (R01.001.001) ou "
                "notarial (R01.001.002) — nesta última é sempre 117."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Direção de arte §4.6/DL-038 (mesmo padrão de EmpresaForm): opção
        # sempre visível, sem JavaScript escondendo uma atrás da outra.
        self.fields["natureza"].widget = forms.RadioSelect(choices=NaturezaCaixa.choices)


_CONTRATO_DO_FORMULARIO_DE_CONTA_CAIXA = ContratoDeRequisicao(
    campos=frozenset(
        {
            "csrfmiddlewaretoken",
            "codigo",
            "nome",
            "natureza",
            "codigo_carne_leao",
            # DL-046 fatia 3: campo novo da tela — sem esta entrada o
            # contrato recusaria (400) o preenchimento dele.
            "codigo_ocupacao",
            "ativa",
        }
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
                    codigo_ocupacao=form.cleaned_data["codigo_ocupacao"],
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
            # DL-046 fatia 3 (RC-127/RC-135): os quatro campos novos do
            # lançamento. Sem eles a tela não conseguia lançar o pagamento
            # de previdência oficial (P20.01.00001), que EXIGE a competência
            # — nem informar o IRRF de PJ, que é o que faz o indicador S/N
            # do arquivo do Carnê-Leão Web sair correto.
            "valor_irrf",
            "competencia_previdencia",
            "multa_previdencia",
            "juros_previdencia",
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


def _valor_monetario_opcional_do_formulario(bruto):
    """Campo monetário OPCIONAL de formulário HTML: `""` (o que o navegador
    envia para um input em branco) vira `None` — "não informado" —, e o
    resto é lido com a MESMA gramática pt-BR do campo `valor`
    (`_decimal_do_formulario`, DE-029), virando `Decimal`.

    A conversão acontece AQUI, e não só no serviço, porque os dois
    contratos são diferentes de propósito: o contrato do SERVIÇO é o da
    API (`para_decimal`, DE-030 — texto decimal simples, "12.34"), e o da
    TELA é pt-BR ("12,34", "1.500,00" — direção de arte §4.9). Passar o
    texto da tela adiante faria o serviço recusar um "12,34" com uma
    mensagem de gramática que não é a deste campo. O que segue para
    `criar_lancamento_caixa` é `Decimal`/`None` — a validação de escala e
    de sinal continua sendo do serviço (`_valor_monetario_opcional`), nunca
    duplicada aqui. `ValorMonetarioInvalido` propaga para a view recusar
    com o texto digitado preservado."""
    texto = (bruto or "").strip()
    if not texto:
        return None
    return _decimal_do_formulario(texto)


def _competencia_previdencia_do_formulario(bruto):
    """Competência da previdência oficial vinda do formulário: AAAA-MM-DD,
    sempre o primeiro dia do mês (é o modelo que checa o dia). Vazio é
    "não informado"; data malformada propaga `DataInvalida`, que a view
    traduz para recusa com o dígito digitado preservado."""
    texto = (bruto or "").strip()
    if not texto:
        return None
    return para_data(texto)


def _meses_encerrados_para_o_formulario(empresa):
    """Meses encerrados do ano anterior em diante, em texto `MM/AAAA` e em
    ordem cronológica, para o aviso do formulário de lançamento (DL-053,
    critério 7). Um `<input type="date">` não consegue excluir meses sem
    JavaScript (regra 6 da direção de arte), então a tela AVISA quais datas
    serão recusadas, em texto; quem recusa de verdade é o servidor. O ano
    anterior entra porque é onde o contador corrige o fechamento recém-feito."""
    ano_corrente = timezone.localdate().year
    encerrados = sorted(_meses_encerrados(empresa, ano_corrente - 1, 9999))
    return [f"{mes:02d}/{ano}" for ano, mes in encerrados]


def _contexto_form_lancamento_caixa(empresa, contas, dados, *, chave_idempotencia):
    return {
        "empresa": empresa,
        "contas": contas,
        "meses_encerrados": _meses_encerrados_para_o_formulario(empresa),
        "ano_do_fechamento": timezone.localdate().year,
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
        # DL-046 fatia 3: os quatro campos novos voltam para o formulário
        # como TEXTO digitado (mesmo tratamento de `valor`), para a recusa
        # não apagar o que o contador preencheu.
        "valor_irrf": dados.get("valor_irrf", ""),
        "competencia_previdencia": dados.get("competencia_previdencia", ""),
        "multa_previdencia": dados.get("multa_previdencia", ""),
        "juros_previdencia": dados.get("juros_previdencia", ""),
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

        def _recusa(mensagem, status=400):
            messages.error(request, mensagem)
            contexto = _contexto_form_lancamento_caixa(
                empresa, contas, request.POST, chave_idempotencia=chave_idempotencia
            )
            return render(request, "livro_caixa/lancamento_form.html", contexto, status=status)

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

        # DL-046, fatia 3 (RC-127/RC-135): os três campos monetários
        # opcionais novos são lidos com a MESMA gramática pt-BR de `valor`
        # (ver `_valor_monetario_opcional_do_formulario`), aqui e não dentro
        # da chamada do serviço — a recusa precisa nomear o CAMPO digitado
        # errado, e um `ValorMonetarioInvalido` levantado na avaliação dos
        # argumentos não estaria coberto pelos `except` abaixo.
        valores_monetarios_opcionais = {}
        for nome_do_campo in ("valor_irrf", "multa_previdencia", "juros_previdencia"):
            try:
                valores_monetarios_opcionais[nome_do_campo] = (
                    _valor_monetario_opcional_do_formulario(request.POST.get(nome_do_campo, ""))
                )
            except ValorMonetarioInvalido as exc:
                return _recusa(f"'{nome_do_campo}' inválido: {exc}")

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
                # DL-046, fatia 3 (RC-127/RC-135): os quatro campos novos —
                # os três monetários já convertidos acima (`Decimal`/`None`;
                # o campo vazio do HTML é `""`, e o helper faz a troca por
                # "não informado").
                valor_irrf=valores_monetarios_opcionais["valor_irrf"],
                multa_previdencia=valores_monetarios_opcionais["multa_previdencia"],
                juros_previdencia=valores_monetarios_opcionais["juros_previdencia"],
                competencia_previdencia=_competencia_previdencia_do_formulario(
                    request.POST.get("competencia_previdencia", "")
                ),
                criado_por=request.user,
                chave_idempotencia=chave_idempotencia,
                request=request,
            )
        except ChaveIdempotenciaConflitanteCaixa as exc:
            return _recusa(str(exc))
        except MesCaixaEncerrado as exc:
            # DL-053: mês encerrado — 409 (conflito de ESTADO, como na API),
            # com a mensagem do serviço, que nomeia o mês e orienta reabrir.
            # Nada foi gravado; o formulário volta preenchido.
            return _recusa(str(exc), status=409)
        except DataInvalida as exc:
            # Só a `competencia_previdencia` é lida dentro deste `try` por
            # `para_data` (a `data` do lançamento já é convertida antes) —
            # mesma mensagem do campo vizinho, para os dois não contarem
            # histórias diferentes do mesmo tipo de erro.
            return _recusa(f"'competencia_previdencia' inválida: {exc}")
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
    # DL-053, critério 7: o mês encerrado aparece como encerrado e a ação de
    # estornar NÃO é oferecida nele (o estorno usa a data do original, então
    # exigiria reabrir o mês). Uma consulta para o intervalo inteiro; a
    # recusa continua sendo do servidor de qualquer forma.
    encerrados = _meses_encerrados(empresa, inicio.year, fim.year)
    linhas = [
        {
            "lancamento": lancamento,
            "valor_ptbr": _valor_ptbr(lancamento.valor),
            "e_estorno": lancamento.estorno_de_id is not None,
            "ja_estornado": lancamento._tem_estorno,
            "mes_encerrado": (lancamento.data.year, lancamento.data.month) in encerrados,
        }
        for lancamento in lancamentos
    ]
    contexto["linhas"] = linhas
    contexto["meses_encerrados_no_periodo"] = [
        f"{mes:02d}/{ano}"
        for ano, mes in sorted(encerrados)
        if (inicio.year, inicio.month) <= (ano, mes) <= (fim.year, fim.month)
    ]
    return render(request, "livro_caixa/lancamentos_lista.html", contexto)


def _contexto_lancamento_estornar(empresa, lancamento):
    return {
        "empresa": empresa,
        "lancamento": lancamento,
        "valor_ptbr": _valor_ptbr(lancamento.valor),
        # DL-053: o estorno usa a data do ORIGINAL; se o mês dela está
        # encerrado a tela explica e não oferece o botão (informativo — o
        # servidor recusa o POST de qualquer forma, com 409).
        "mes_encerrado": mes_caixa_esta_encerrado(
            empresa=empresa, ano=lancamento.data.year, mes=lancamento.data.month
        ),
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
        except MesCaixaEncerrado as exc:
            # DL-053, critério 2: estorno de lançamento de mês encerrado —
            # 409, nada gravado; reabrir o mês é o caminho (RC-130).
            # O texto do serviço para o estorno cita o código interno da
            # regra ("RC-130"), que não pode aparecer para o contador; a
            # tela diz a mesma coisa em linguagem de escritório. A recusa por
            # espera de lock (`MesCaixaOcupado`) mantém a mensagem do
            # serviço, que não cita código nenhum.
            if isinstance(exc, MesCaixaOcupado):
                messages.error(request, str(exc))
            else:
                messages.error(
                    request,
                    f"O mês {lancamento.data.month:02d}/{lancamento.data.year} do livro-caixa "
                    f"de {empresa} está encerrado; o lançamento não foi estornado. Reabra o "
                    "mês, informando o motivo, e estorne de novo.",
                )
            return render(
                request,
                "livro_caixa/lancamento_estornar.html",
                _contexto_lancamento_estornar(empresa, lancamento),
                status=409,
            )
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


# ---------------------------------------------------------------------------
# Arquivos de importação do Carnê-Leão Web (DL-046, fatia 3 — RC-127):
# tela de pendências/conferência e os dois downloads de CSV.
#
# A tela NÃO calcula nada: chama `gerar_arquivos_carne_leao`
# (`apps.livro_caixa.carne_leao_arquivos`, serviço do `desenvolvedor-pleno`)
# e só FORMATA (pt-BR, `_valor_ptbr`) o que ele devolveu — mesma regra do
# bloco do carnê-leão, acima. As três views repetem a MESMA ordem de
# checagem das outras telas deste arquivo (escritório ativo → empresa do
# escritório → papel de leitura → modo livro-caixa), e nenhuma delas
# calcula valor monetário nenhum.
#
# A trilha distingue o que aconteceu de fato: a chamada de mera CONFERÊNCIA
# (esta tela, sem download) grava `carne_leao_arquivo.conferido`, e só quem
# baixa os bytes deixa `carne_leao_arquivo.gerado` — ver o parâmetro
# `para_download` de `gerar_arquivos_carne_leao`. (A versão anterior desta
# seção chamava isto de "limitação declarada"; deixou de ser quando a ação
# passou a dizer a verdade.)
# ---------------------------------------------------------------------------


# DE-092: nenhum identificador interno do projeto em texto VISÍVEL.
#
# A correção é na FONTE — as mensagens de `Pendencia.motivo` perderam as
# referências entre parênteses em `apps/livro_caixa/carne_leao_arquivos.py`.
# A normalização de apresentação que existia aqui foi removida na
# reconferência da rodada 1: com a fonte limpa ela não tinha mais o que
# remover, e mantê-la esconderia uma reintrodução futura justamente do
# lugar onde ela precisa aparecer. O que protege hoje é a varredura de
# texto visível nos testes (`test_sem_identificador_interno_nem_patch`).


# Rótulo de exibição do CAMPO de cada pendência (o valor de `Pendencia.
# campo` é o nome do campo no modelo/serviço, jargão demais para a tela).
# Campo sem entrada aqui aparece com o próprio nome — nunca some em silêncio.
_ROTULOS_DE_CAMPO_DE_PENDENCIA = {
    "historico": "Histórico",
    "codigo_ocupacao": "Código de ocupação",
    "competencia_previdencia": "Competência da previdência oficial",
    "conta.codigo_carne_leao": "Código do Carnê-Leão Web da conta",
}


def _pendencias_para_tela(pendencias):
    """Lista COMPLETA das pendências (critério 4 do plano: nada truncado),
    só com o rótulo do campo traduzido e o motivo normalizado (DE-092)."""
    return [
        {
            "lancamento_id": pendencia.lancamento_id,
            "campo": _ROTULOS_DE_CAMPO_DE_PENDENCIA.get(pendencia.campo, pendencia.campo),
            "motivo": pendencia.motivo,
        }
        for pendencia in pendencias
    ]


def _conferencia_de_arquivo_para_tela(conferencia):
    """Formata a `conferencia` do serviço para a tela — SEMPRE expõe as
    duas diferenças (o serviço só permite diferença não-zero por lançamento
    de conta SEM código do Carnê-Leão Web: fora do arquivo, dentro do
    Livro Caixa), e diz em TEXTO se cada uma é zero ou não (direção de arte
    §4.3: cor nunca é o único canal). Os booleanos abaixo são comparação
    com ZERO para escolher o texto — nenhum valor monetário é calculado
    aqui.

    `sem_lancamentos_no_periodo` marca o estado VAZIO da tela: nenhum
    lançamento entrou no arquivo E nada foi excluído — não há o que
    exportar, e os dois botões de download ficam de fora (arquivo vazio não
    é o que a importação do Carnê-Leão Web consome)."""
    zerado = Decimal("0.00")
    return {
        "linhas_rendimentos": conferencia["linhas_rendimentos"],
        "linhas_pagamentos": conferencia["linhas_pagamentos"],
        "totais_rendimentos": [
            {"codigo": codigo, "valor_ptbr": _valor_ptbr(valor)}
            for codigo, valor in sorted(conferencia["totais_rendimentos_por_codigo"].items())
        ],
        "totais_pagamentos": [
            {"codigo": codigo, "valor_ptbr": _valor_ptbr(valor)}
            for codigo, valor in sorted(conferencia["totais_pagamentos_por_codigo"].items())
        ],
        "total_rendimentos_ptbr": _valor_ptbr(conferencia["total_rendimentos"]),
        "total_pagamentos_ptbr": _valor_ptbr(conferencia["total_pagamentos"]),
        "total_entradas_livro_caixa_ptbr": _valor_ptbr(conferencia["total_entradas_livro_caixa"]),
        "total_saidas_livro_caixa_ptbr": _valor_ptbr(conferencia["total_saidas_livro_caixa"]),
        "diferenca_rendimentos_ptbr": _valor_ptbr(conferencia["diferenca_rendimentos"]),
        "diferenca_pagamentos_ptbr": _valor_ptbr(conferencia["diferenca_pagamentos"]),
        "diferenca_rendimentos_zerada": conferencia["diferenca_rendimentos"] == zerado,
        "diferenca_pagamentos_zerada": conferencia["diferenca_pagamentos"] == zerado,
        "lancamentos_excluidos_estorno": conferencia["lancamentos_excluidos_estorno"],
        "lancamentos_excluidos_sem_codigo": conferencia["lancamentos_excluidos_sem_codigo"],
        "sem_lancamentos_no_periodo": conferencia_sem_movimento(conferencia),
    }


def _url_da_tela_de_arquivos(empresa, request):
    """Destino dos redirects dos downloads — preserva `inicio`/`fim` da
    querystring, porque o estado desta família de telas mora na URL (sem
    sessão): sem isso, o redirect cairia no mês corrente e esconderia o
    período que a pessoa estava conferindo."""
    parametros = {
        chave: request.GET[chave] for chave in ("inicio", "fim") if request.GET.get(chave)
    }
    url = reverse("livro_caixa_web:arquivos_carne_leao", args=[empresa.id])
    return f"{url}?{urlencode(parametros)}" if parametros else url


@login_required
@require_safe
def arquivos_carne_leao(request, empresa_id):
    """`GET .../carne-leao/arquivos/?inicio=...&fim=...` — painel de
    período (arquétipo D) combinado com o documento de conferência: lista
    TODAS as pendências quando o leiaute oficial recusaria alguma linha
    (sem nenhum download — nunca arquivo parcial), ou mostra a conferência
    e os dois downloads quando a geração passa. Período inválido (querystring
    malformada ou fora de um ano-calendário) é 400 com mensagem, nunca 500."""
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
        "inicio": inicio,
        "fim": fim,
        "pode_baixar": False,
        "pendencias": [],
        "conferencia": None,
        "estado_vazio": False,
    }
    if inicio is None or fim is None:
        messages.error(request, "O período informado não pôde ser usado.")
        return render(request, "livro_caixa/arquivos_carne_leao.html", contexto, status=400)

    try:
        _rendimentos, _pagamentos, conferencia = gerar_arquivos_carne_leao(
            empresa=empresa, inicio=inicio, fim=fim, usuario=request.user, request=request
        )
    except PeriodoInvalidoParaArquivoCarneLeaoWeb as exc:
        messages.error(request, str(exc))
        return render(request, "livro_caixa/arquivos_carne_leao.html", contexto, status=400)
    except GeracaoArquivoCarneLeaoBloqueada as exc:
        contexto["pendencias"] = _pendencias_para_tela(exc.pendencias)
        return render(request, "livro_caixa/arquivos_carne_leao.html", contexto)

    contexto["conferencia"] = _conferencia_de_arquivo_para_tela(conferencia)
    contexto["estado_vazio"] = contexto["conferencia"]["sem_lancamentos_no_periodo"]
    contexto["pode_baixar"] = not contexto["estado_vazio"]
    return render(request, "livro_caixa/arquivos_carne_leao.html", contexto)


def _servir_arquivo_carne_leao(request, empresa_id, *, prefixo, escolher_conteudo):
    """Corpo comum dos dois downloads, abaixo — só o PREFIXO do nome do
    arquivo e qual dos dois `bytes` servir mudam entre eles (mesmo desenho
    de `_ArquivoCarneLeaoDownloadViewBase`, na API). Mesmas checagens, na
    mesma ordem, da tela de arquivos.

    ⚠️ Nunca arquivo parcial: com pendência (ou período inválido) a
    resposta é `messages.error` + redirect de volta para a tela de
    arquivos, que lista o que falta — o download só existe quando a
    geração passou inteira. O nome do arquivo é NEUTRO (período e tipo),
    nunca CPF/CNPJ (LGPD: o anexo pode parar em pasta de download
    compartilhada)."""
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
    if inicio is None or fim is None:
        messages.error(request, "O período informado não pôde ser usado.")
        return redirect(_url_da_tela_de_arquivos(empresa, request))

    try:
        rendimentos_bytes, pagamentos_bytes, conferencia = gerar_arquivos_carne_leao(
            empresa=empresa,
            inicio=inicio,
            fim=fim,
            usuario=request.user,
            request=request,
            # Achado 5 da rodada 1 da auditoria: aqui os bytes VÃO para o
            # cliente, então a trilha registra "gerado" — a tela de
            # conferência, que chama a mesma função só para olhar os
            # números, registra "conferido".
            para_download=True,
        )
    except PeriodoInvalidoParaArquivoCarneLeaoWeb as exc:
        messages.error(request, str(exc))
        return redirect(_url_da_tela_de_arquivos(empresa, request))
    except GeracaoArquivoCarneLeaoBloqueada:
        messages.error(
            request,
            "O arquivo não foi gerado: existem lançamentos que o leiaute do Carnê-Leão Web "
            "recusaria. A lista completa está na tela de arquivos, para corrigir antes de "
            "importar — nada é truncado nem corrigido em silêncio.",
        )
        return redirect(_url_da_tela_de_arquivos(empresa, request))

    # Achado 4 da rodada 1 da auditoria: a TELA esconde os botões quando não
    # há o que exportar, mas o endereço de download continuava devolvendo um
    # CSV vazio com 200 — sucesso aparente num canto onde a tela dizia outra
    # coisa. A MESMA regra de estado vazio vale aqui: sem lançamento no
    # período (incluído ou excluído), não há arquivo a importar e a resposta
    # volta para a tela com o motivo.
    if conferencia_sem_movimento(conferencia):
        messages.error(
            request,
            "Não há lançamentos neste período para exportar — o arquivo do Carnê-Leão Web "
            "só é gerado quando existe movimento a importar.",
        )
        return redirect(_url_da_tela_de_arquivos(empresa, request))

    # Mesmo formato dos arquivos-modelo oficiais (HI-41, registrado no
    # serviço): ISO-8859-1 com CRLF — o `Content-Type` declara a
    # codificação para o navegador não reencodificar os acentos.
    nome_arquivo = f"carne-leao-{prefixo}-{inicio:%Y-%m}-a-{fim:%Y-%m}.csv"
    resposta = HttpResponse(
        escolher_conteudo(rendimentos_bytes, pagamentos_bytes),
        content_type="text/csv; charset=ISO-8859-1",
    )
    resposta["Content-Disposition"] = f'attachment; filename="{nome_arquivo}"'
    return resposta


@login_required
@require_safe
def arquivo_rendimentos_carne_leao(request, empresa_id):
    """Download do CSV de rendimentos do período — pronto para importar no
    Carnê-Leão Web (mesmo contrato de nome/codificação das telas de
    download do Fiscal)."""
    return _servir_arquivo_carne_leao(
        request,
        empresa_id,
        prefixo="rendimentos",
        escolher_conteudo=lambda rendimentos, pagamentos: rendimentos,
    )


@login_required
@require_safe
def arquivo_pagamentos_carne_leao(request, empresa_id):
    """Download do CSV de pagamentos do período — mesmo contrato do de
    rendimentos, ao lado."""
    return _servir_arquivo_carne_leao(
        request,
        empresa_id,
        prefixo="pagamentos",
        escolher_conteudo=lambda rendimentos, pagamentos: pagamentos,
    )


# ---------------------------------------------------------------------------
# Fechamento de mês do livro-caixa (DL-053, critério 7 — a TELA)
#
# NENHUMA regra de fechamento mora aqui: `encerrar_mes_caixa`,
# `reabrir_mes_caixa` e `estado_dos_meses_caixa` (services.py) decidem, travam
# o mês sob concorrência e gravam a trilha na mesma transação. Esta seção só
# CHAMA os serviços e traduz cada recusa em mensagem de escritório (nunca 500).
#
# Molde: o fechamento de competência da contabilidade (DL-031) — painel de
# período (arquétipo D) para a consulta e uma tela de confirmação por ação
# (arquétipo E) que diz o que vai acontecer antes do botão.
#
# PERMISSÃO (RC-146 = RC-102): a consulta exige o papel que LÊ o livro-caixa;
# encerrar e reabrir exigem o papel de `papel_pode_fechar_mes_caixa`
# (administrador ou gestor) — conferido AQUI, no servidor, em GET e em POST.
# O painel esconde os botões de quem não pode e explica por quê, mas isso é
# só ajuda: o 403 abaixo é que vale (testado pela requisição, banco inalterado).
# ---------------------------------------------------------------------------

# Mesma faixa que o serviço valida (`_ANO_MINIMO_FECHAMENTO`/`_ANO_MAXIMO_
# FECHAMENTO`, privados de services.py) — copiada por valor, como o resto
# deste módulo faz com o que é "privado" de outro arquivo.
_ANO_MINIMO_FECHAMENTO_MES, _ANO_MAXIMO_FECHAMENTO_MES = 1970, 2999

_CONTRATO_ENCERRAR_MES_CAIXA = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "ano", "mes"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="no encerramento de mês do livro-caixa",
)
_CONTRATO_REABRIR_MES_CAIXA = ContratoDeRequisicao(
    campos=frozenset({"csrfmiddlewaretoken", "ano", "mes", "motivo"}),
    aceita_arquivo=False,
    aceita_querystring=False,
    cabecalhos_ignorados=("Idempotency-Key",),
    contexto="na reabertura de mês do livro-caixa",
)


def _url_do_painel_de_fechamento(empresa, ano):
    return (
        f"{reverse('livro_caixa_web:fechamento_mes', args=[empresa.id])}?{urlencode({'ano': ano})}"
    )


def _ano_do_painel_de_fechamento(request):
    """Ano pedido por `?ano=` (padrão: o corrente). Devolve `(ano, erro)`;
    nunca lança exceção. Só dígitos ASCII (`[0-9]`), nunca dígito Unicode."""
    bruto = (request.GET.get("ano") or "").strip()
    if not bruto:
        return timezone.localdate().year, None
    if _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(bruto):
        ano = int(bruto)
        if _ANO_MINIMO_FECHAMENTO_MES <= ano <= _ANO_MAXIMO_FECHAMENTO_MES:
            return ano, None
    return None, (
        f"O ano informado não é válido: use um ano entre {_ANO_MINIMO_FECHAMENTO_MES} e "
        f"{_ANO_MAXIMO_FECHAMENTO_MES}."
    )


def _ano_e_mes_do_fechamento(fonte):
    """Lê `ano`/`mes` de `fonte` (GET na tela de confirmação, POST no envio,
    onde voltam como campos ocultos do formulário). Devolve `(ano, mes,
    erro)`; nunca lança exceção — erro de entrada vira mensagem, não 500."""
    bruto_ano = (fonte.get("ano") or "").strip()
    bruto_mes = (fonte.get("mes") or "").strip()
    if not _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(
        bruto_ano
    ) or not _PADRAO_ANO_MES_CARNE_LEAO.fullmatch(bruto_mes):
        return None, None, "Informe o ano e o mês do fechamento."
    ano, mes = int(bruto_ano), int(bruto_mes)
    if not (1 <= mes <= 12) or not (
        _ANO_MINIMO_FECHAMENTO_MES <= ano <= _ANO_MAXIMO_FECHAMENTO_MES
    ):
        return (
            None,
            None,
            f"Mês ou ano inválido: o mês deve estar entre 1 e 12 e o ano entre "
            f"{_ANO_MINIMO_FECHAMENTO_MES} e {_ANO_MAXIMO_FECHAMENTO_MES}.",
        )
    return ano, mes, None


def _porta_do_fechamento(request, empresa_id, *, para_agir):
    """Portão comum das três telas: devolve `(empresa, resposta_de_recusa)`.

    Ordem (a mesma das demais telas do módulo): escritório ativo → empresa do
    escritório (404 para outro escritório, sem confirmar que existe) → papel
    (403) → modo de escrituração. O papel vem ANTES do modo para quem não tem
    acesso nunca ficar sabendo o modo de escrituração da empresa."""
    if request.escritorio is None:
        return None, _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if para_agir:
        if not _pode_fechar_mes(request):
            return empresa, _resposta_sem_permissao(
                request,
                "Seu papel não permite encerrar nem reabrir meses do livro-caixa desta "
                "empresa — essa ação exige administrador ou gestor. Fale com um deles.",
            )
    elif not _pode_ler(request):
        return empresa, _resposta_sem_permissao(
            request, "Seu papel não permite ler o livro-caixa desta empresa."
        )
    recusa = _sem_livro_caixa_para_contabilidade(request, empresa)
    if recusa is not None:
        return empresa, recusa
    return empresa, None


@login_required
@require_safe
def fechamento_mes_caixa(request, empresa_id):
    """Painel de fechamento (arquétipo D): os 12 meses do ano, o estado de
    cada um, quem encerrou e quando, e a última reabertura com o motivo.

    Quem lê o livro-caixa mas não pode fechar (analista, financeiro,
    paralegal) vê o painel INTEIRO; só a coluna de ações muda, com a
    explicação no topo em vez de sumir em silêncio."""
    empresa, recusa = _porta_do_fechamento(request, empresa_id, para_agir=False)
    if recusa is not None:
        return recusa

    ano, erro = _ano_do_painel_de_fechamento(request)
    contexto = {"empresa": empresa, "pode_fechar": _pode_fechar_mes(request)}
    if erro is not None:
        messages.error(request, erro)
        contexto["ano"] = None
        contexto["ano_corrente"] = timezone.localdate().year
        return render(request, "livro_caixa/fechamento_mes.html", contexto, status=400)

    hoje = timezone.localdate()
    meses = estado_dos_meses_caixa(empresa=empresa, ano=ano)
    for mes in meses:
        mes["encerrado"] = mes["estado"] == EstadoMesCaixa.ENCERRADO
        mes["e_mes_atual"] = (mes["ano"], mes["mes"]) == (hoje.year, hoje.month)
        mes["primeiro_dia"] = date(ano, mes["mes"], 1)  # o template escreve o nome do mês
        mes["inicio_iso"] = mes["primeiro_dia"].isoformat()
        mes["fim_iso"] = date(ano, mes["mes"], calendar.monthrange(ano, mes["mes"])[1]).isoformat()
    contexto.update(
        {
            "ano": ano,
            "ano_corrente": hoje.year,
            "ano_anterior": ano - 1 if ano > _ANO_MINIMO_FECHAMENTO_MES else None,
            "ano_seguinte": ano + 1 if ano < _ANO_MAXIMO_FECHAMENTO_MES else None,
            "meses": meses,
            "quantidade_encerrados": sum(1 for mes in meses if mes["encerrado"]),
            "quantidade_com_reabertura": sum(1 for mes in meses if mes["reaberto_em"] is not None),
        }
    )
    return render(request, "livro_caixa/fechamento_mes.html", contexto)


def _contexto_da_acao_de_fechamento(empresa, ano, mes):
    return {
        "empresa": empresa,
        "ano": ano,
        "mes": mes,
        "motivo_tamanho_maximo": TAMANHO_MAXIMO_MOTIVO_REABERTURA,
        "inicio_iso": date(ano, mes, 1).isoformat(),
        "fim_iso": date(ano, mes, calendar.monthrange(ano, mes)[1]).isoformat(),
    }


@login_required
@require_http_methods(["GET", "POST"])
def mes_caixa_encerrar(request, empresa_id):
    """Encerra um mês (arquétipo E, etapa única). GET mostra o que o mês
    contém e o que passa a ser recusado ANTES do botão; POST chama
    `encerrar_mes_caixa`, que decide e trava de verdade."""
    empresa, recusa = _porta_do_fechamento(request, empresa_id, para_agir=True)
    if recusa is not None:
        return recusa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro = _ano_e_mes_do_fechamento(fonte)
    if erro is not None:
        messages.error(request, erro)
        return redirect("livro_caixa_web:fechamento_mes", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_ENCERRAR_MES_CAIXA)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect(_url_do_painel_de_fechamento(empresa, ano))
        try:
            encerrar_mes_caixa(
                empresa=empresa, ano=ano, mes=mes, usuario=request.user, request=request
            )
        except (FechamentoMesCaixaInvalido, FechamentoMesCaixaRecusado) as exc:
            # Mês já encerrado, espera de lock estourada ou entrada inválida:
            # nada foi gravado. O painel mostra o estado ATUAL do mês, que é o
            # que a pessoa precisa ver para decidir o que fazer a seguir.
            messages.error(request, str(exc))
            return redirect(_url_do_painel_de_fechamento(empresa, ano))
        messages.success(
            request,
            f"Mês {mes:02d}/{ano} do livro-caixa de {empresa.razao_social} encerrado com "
            "sucesso. Lançamentos e estornos nele ficam bloqueados até a reabertura.",
        )
        return redirect(_url_do_painel_de_fechamento(empresa, ano))

    if mes_caixa_esta_encerrado(empresa=empresa, ano=ano, mes=mes):
        messages.info(
            request, f"O mês {mes:02d}/{ano} de {empresa.razao_social} já está encerrado."
        )
        return redirect(_url_do_painel_de_fechamento(empresa, ano))

    contexto = _contexto_da_acao_de_fechamento(empresa, ano, mes)
    # O que o mês contém, ANTES de encerrar: é a conferência do contador.
    # `apurar_livro_caixa` é o mesmo cálculo do relatório Livro Caixa, então
    # os totais daqui batem com ele (estorno entra com o sinal invertido).
    apuracao = apurar_livro_caixa(
        empresa=empresa,
        inicio=date.fromisoformat(contexto["inicio_iso"]),
        fim=date.fromisoformat(contexto["fim_iso"]),
    )
    contexto.update(
        {
            "quantidade_lancamentos": len(apuracao["itens"]),
            "total_entradas_ptbr": _valor_ptbr(apuracao["total_entradas"]),
            "total_saidas_ptbr": _valor_ptbr(apuracao["total_saidas"]),
            "saldo_ptbr": _valor_ptbr(apuracao["saldo"]),
            # Aviso, não bloqueio: encerrar mês ainda em curso é possível,
            # mas quase sempre é engano do contador.
            "mes_em_curso": date.fromisoformat(contexto["fim_iso"]) >= timezone.localdate(),
        }
    )
    return render(request, "livro_caixa/fechamento_mes_encerrar.html", contexto)


@login_required
@require_http_methods(["GET", "POST"])
def mes_caixa_reabrir(request, empresa_id):
    """Reabre um mês encerrado (arquétipo E, etapa única). O motivo é
    obrigatório e fica na trilha de auditoria; a recusa de verdade é do
    serviço (`reabrir_mes_caixa`), que a tela traduz sem nunca dar 500."""
    empresa, recusa = _porta_do_fechamento(request, empresa_id, para_agir=True)
    if recusa is not None:
        return recusa

    fonte = request.POST if request.method == "POST" else request.GET
    ano, mes, erro = _ano_e_mes_do_fechamento(fonte)
    if erro is not None:
        messages.error(request, erro)
        return redirect("livro_caixa_web:fechamento_mes", empresa_id=empresa.id)

    if request.method == "POST":
        try:
            recusar_dado_nao_contratado(request, _CONTRATO_REABRIR_MES_CAIXA)
        except DadoNaoContratado as exc:
            messages.error(request, exc.mensagem)
            return redirect(_url_do_painel_de_fechamento(empresa, ano))
        motivo = request.POST.get("motivo", "")
        try:
            reabrir_mes_caixa(
                empresa=empresa,
                ano=ano,
                mes=mes,
                usuario=request.user,
                motivo=motivo,
                request=request,
            )
        except FechamentoMesCaixaInvalido as exc:
            # Motivo em branco (ou longo demais) é erro de FORMULÁRIO: a tela
            # volta com o que foi digitado, status 400, e nada muda no mês.
            messages.error(request, str(exc))
            contexto = _contexto_da_acao_de_fechamento(empresa, ano, mes)
            contexto["motivo"] = motivo
            contexto.update(_contexto_do_encerramento_atual(empresa, ano, mes))
            return render(request, "livro_caixa/fechamento_mes_reabrir.html", contexto, status=400)
        except FechamentoMesCaixaRecusado as exc:
            # Mês que já estava aberto (duas pessoas reabrindo) ou espera de
            # lock estourada: nada foi gravado; o painel mostra o estado atual.
            messages.error(request, str(exc))
            return redirect(_url_do_painel_de_fechamento(empresa, ano))
        messages.success(
            request,
            f"Mês {mes:02d}/{ano} do livro-caixa de {empresa.razao_social} reaberto com "
            "sucesso. O motivo ficou registrado na trilha de auditoria.",
        )
        return redirect(_url_do_painel_de_fechamento(empresa, ano))

    if not mes_caixa_esta_encerrado(empresa=empresa, ano=ano, mes=mes):
        messages.info(
            request,
            f"O mês {mes:02d}/{ano} de {empresa.razao_social} não está encerrado; não há o "
            "que reabrir.",
        )
        return redirect(_url_do_painel_de_fechamento(empresa, ano))

    contexto = _contexto_da_acao_de_fechamento(empresa, ano, mes)
    contexto["motivo"] = ""
    contexto.update(_contexto_do_encerramento_atual(empresa, ano, mes))
    return render(request, "livro_caixa/fechamento_mes_reabrir.html", contexto)


def _contexto_do_encerramento_atual(empresa, ano, mes):
    """Quem encerrou o mês e quando — mostrado na tela de reabertura para a
    pessoa saber o que está desfazendo. Lê os 12 meses do ano (uma consulta)
    pelo serviço e fica com o pedido."""
    estado = estado_dos_meses_caixa(empresa=empresa, ano=ano)[mes - 1]
    return {
        "fechado_por_nome": estado["fechado_por_nome"],
        "fechado_em": estado["fechado_em"],
    }
