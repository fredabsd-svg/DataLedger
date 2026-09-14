"""Telas da contabilidade (DL-017, fase B).

DE-026: estas views NUNCA chamam a própria API — chamam os serviços de
`apps.contabilidade.services` diretamente e renderizam HTML no servidor. A
autorização de LEITURA vem de uma função só, compartilhada com a API
(`apps.contabilidade.permissoes.papel_pode_ler_contabilidade` — ver o
docstring daquele módulo para o contrato completo); a autorização de
ESCRITA (criar conta, lançar) reaproveita a MESMA classe de permissão que a
API já usa para escrever (`apps.contabilidade.views.PodeEscriturar`), por
indicação explícita do docstring de `permissoes.py`: não existe uma segunda
lista de papéis "só para a tela" em lugar nenhum deste arquivo.

Cada view revalida a empresa pedida contra `request.escritorio` (o
escritório ATIVO da sessão, resolvido pelo `EscritorioAtivoMiddleware` —
nunca um `empresa_id` cru): uma empresa de outro escritório sempre dá 404,
nunca dado (critério 2 do plano DL-017).

Formatação é apresentação: todo valor monetário permanece `Decimal` até o
último instante, convertido para texto pt-BR só pelas funções `_valor_ptbr`/
`_indicador_natureza` deste módulo — nunca um `float` em ponto nenhum
(AGENTS.md, seção 10; riscos do plano DL-017).
"""

import hashlib
import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.contabilidade.models import Conta, LancamentoContabil, TipoPartida
from apps.contabilidade.permissoes import papel_pode_ler_contabilidade
from apps.contabilidade.services import (
    ChaveIdempotenciaConflitante,
    HierarquiaInconsistente,
    LancamentoInvalido,
    apurar_balancete,
    apurar_razao,
    criar_lancamento,
    listar_diario,
    localizar_contas_que_aceitam_lancamento_e_tem_subordinadas,
    localizar_contas_sinteticas_com_movimento,
    localizar_inconsistencias_de_hierarquia,
    localizar_lotes_desbalanceados,
)

# Reaproveitados de apps.contabilidade.views (API), de propósito, para não
# existir uma segunda cópia de nenhuma das duas regras a seguir:
# - PodeEscriturar: MESMA permissão de escrita que a API usa (indicação
#   explícita do docstring de permissoes.py — a tela de lançamento "usa a
#   regra de PodeEscriturar em views.py").
# - _saldo_absoluto_com_natureza: a conversão saldo-assinado -> (valor
#   absoluto, letra D/C) é uma regra sutil (RC-61: saldo zero não tem lado;
#   o sinal pode inverter a natureza APURADA em relação à CADASTRADA — ver o
#   docstring de origem) — exatamente o tipo de decisão que DE-026 não quer
#   duplicada em dois lugares.
from apps.contabilidade.views import PodeEscriturar, _saldo_absoluto_com_natureza
from apps.empresas.models import Empresa

# Mesmo teto de NÍVEL que a API aplica em `apps.contabilidade.views.NIVEL_
# MAXIMO` — valor repetido aqui (não importado) porque é só uma guarda de
# boa educação na fronteira HTTP desta tela (nenhum plano de contas real
# chega a esta profundidade), não uma regra de negócio contábil.
NIVEL_MAXIMO = 50

# Formato ESTRITO aceito para 'inicio'/'fim' na querystring desta tela —
# mesma cautela da API (apps.contabilidade.views._PADRAO_DATA_SIMPLES):
# recusar ANTES de date.fromisoformat, que aceita formatos fora do
# contrato anunciado (ex.: data de semana ISO) e os reinterpreta em
# silêncio. Cópia deliberada e pequena (uma linha de regex), não a mesma
# regra de negócio contábil que DE-026 protege contra duplicação — é
# higiene de fronteira HTTP, própria de CADA fronteira.
_PADRAO_DATA_SIMPLES = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")

LINHAS_INICIAIS_LANCAMENTO = 4
LINHAS_MAXIMAS_LANCAMENTO = 20


# ---------------------------------------------------------------------------
# Formatação de apresentação (critérios 4 e 5) — nunca usada para cálculo.
# ---------------------------------------------------------------------------


def _milhar_ptbr(parte_inteira):
    """Insere '.' a cada três dígitos na parte inteira (texto), preservando
    o sinal. Opera sobre STRING, não sobre número — evita qualquer resíduo
    de ponto flutuante ou dependência de locale do interpretador.
    """
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
    """Formata um Decimal monetário em pt-BR: '.' de milhar, ',' decimal,
    sempre duas casas (critério 4: `1234567.89` -> `1.234.567,89`).

    `Decimal(valor).quantize(Decimal("0.01"))` antes de qualquer formatação
    (mesmo motivo do `_como_moeda` de apps.contabilidade.views: SQLite, usado
    em desenvolvimento local, não preserva a escala de um DecimalField em
    agregações `Sum` como o PostgreSQL faz).

    Não usa o filtro `intcomma` do Django: `django.contrib.humanize` não
    está em INSTALLED_APPS, e esta etapa não tem permissão para alterar
    `config/settings.py` (arquivo do arquiteto-senior). Também não usa uma
    template tag própria, pelo mesmo motivo que impede isto em
    `apps.empresas.views._mascara_cnpj`: nenhuma permissão, nesta etapa,
    para criar `apps/contabilidade/templatetags/`. Formatação pura de
    apresentação — o valor segue `Decimal` até aqui.
    """
    quantizado = Decimal(valor).quantize(Decimal("0.01"))
    texto = str(quantizado)
    negativo = texto.startswith("-")
    if negativo:
        texto = texto[1:]
    parte_inteira, parte_decimal = texto.split(".")
    resultado = f"{_milhar_ptbr(parte_inteira)},{parte_decimal}"
    return f"-{resultado}" if negativo else resultado


def _indicador_natureza(letra):
    """Empacota a letra D/C (RC-61) com o texto por extenso, para o
    template anunciar "D (devedor)"/"C (credor)" — nunca só a letra, e
    nunca só cor (critério 14). `None` quando o saldo é zero: RC-61 diz que
    zero não tem lado, e não existe letra "certa" para inventar aqui.
    """
    if letra is None:
        return None
    return {"letra": letra, "extenso": "devedor" if letra == "D" else "credor"}


# ---------------------------------------------------------------------------
# Isolamento e permissão (critérios 1, 2 e 3)
# ---------------------------------------------------------------------------


def _empresa_do_escritorio_ativo(request, empresa_id):
    """Resolve a empresa da URL, sempre restrita ao escritório ATIVO da
    sessão (critério 2) — nunca por um `empresa_id` cru. Mesma regra de
    isolamento de `apps.empresas.mixins.EmpresaEscopadaMixin` (já usada
    pela API): uma empresa de outro escritório dá 404, não 403 — não
    confirma nem a existência do registro para quem não tem acesso.
    """
    return get_object_or_404(Empresa, pk=empresa_id, escritorio=request.escritorio)


def _resposta_sem_permissao(request, mensagem):
    # Critério 3: template próprio, com explicação e caminho de volta —
    # nunca texto cru, nunca 500. Reaproveita o MESMO template que
    # apps.empresas já usa (templates/erros/sem_permissao.html, da DL-009).
    return render(request, "erros/sem_permissao.html", {"mensagem": mensagem}, status=403)


def _resposta_sem_escritorio(request):
    # Reaproveita o mesmo template de apps.empresas (mesma situação: sem
    # escritório ativo não há como saber de qual contabilidade se fala).
    return render(request, "empresas/sem_escritorio.html")


def _pode_ler(request):
    return papel_pode_ler_contabilidade(getattr(request, "papel", None))


def _pode_escriturar(request):
    return PodeEscriturar().has_permission(request, None)


# ---------------------------------------------------------------------------
# Período e nível (critérios 7 e 9)
# ---------------------------------------------------------------------------


def _ultimo_dia_do_mes(referencia):
    proximo_mes = referencia.replace(day=28) + timedelta(days=4)
    return proximo_mes - timedelta(days=proximo_mes.day)


def _periodo_do_formulario(request):
    """Lê e valida 'inicio'/'fim' da querystring das três saídas com
    período (Diário, Razão, Balancete — critério 9).

    Ausência dos DOIS parâmetros (primeira visita à tela) usa o MÊS
    CORRENTE como valor inicial sugerido — diferente da API (DE-016), que
    RECUSA ausência: aqui é a TELA escolhendo um padrão por conveniência de
    quem vai usá-la todo dia, nunca o motor de cálculo. O padrão só é
    aplicado quando NADA foi enviado; um período enviado e malformado
    nunca "cai" no padrão silenciosamente — é reportado como erro.

    Devolve (inicio, fim, mensagem_de_erro). `mensagem_de_erro` é `None`
    quando o período é válido (default ou informado); do contrário, os dois
    primeiros valores vêm `None` e quem chama não deve apurar nada.
    """
    bruto_inicio = request.GET.get("inicio", "").strip()
    bruto_fim = request.GET.get("fim", "").strip()

    if not bruto_inicio and not bruto_fim:
        hoje = timezone.localdate()
        return hoje.replace(day=1), _ultimo_dia_do_mes(hoje), None

    if not bruto_inicio or not bruto_fim:
        return None, None, "Informe as duas datas do período (início e fim)."

    if not _PADRAO_DATA_SIMPLES.fullmatch(bruto_inicio) or not _PADRAO_DATA_SIMPLES.fullmatch(
        bruto_fim
    ):
        return (
            None,
            None,
            "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD).",
        )

    try:
        inicio = date.fromisoformat(bruto_inicio)
        fim = date.fromisoformat(bruto_fim)
    except ValueError:
        return (
            None,
            None,
            "Data inválida: use o seletor de data (ou o formato AAAA-MM-DD).",
        )

    if inicio > fim:
        return None, None, "A data de início não pode ser posterior à data de fim."

    return inicio, fim, None


def _nivel_do_formulario(request):
    """Lê e valida o parâmetro opcional 'nivel' do Balancete.

    Ausente (ou vazio) devolve `None` — sem recorte de hierarquia, igual à
    API. Presente e malformado vira mensagem de erro, nunca um 500.
    """
    bruto = request.GET.get("nivel", "").strip()
    if not bruto:
        return None, None
    if not bruto.isdigit():
        return None, "'Nível' deve ser um número inteiro."
    nivel = int(bruto)
    if nivel < 1 or nivel > NIVEL_MAXIMO:
        return None, f"'Nível' deve ser um número inteiro entre 1 e {NIVEL_MAXIMO}."
    return nivel, None


# ---------------------------------------------------------------------------
# Plano de contas
# ---------------------------------------------------------------------------


def _linhas_hierarquicas(contas):
    """Nível ESTRUTURAL de cada conta (profundidade na árvore de
    `conta_pai`), só para indentar a listagem do Plano de Contas.

    Isto NÃO é a regra de saldo nem de consolidação — essas vivem inteiras
    em `apurar_balancete`/`apurar_razao` (services.py) e não são
    reimplementadas aqui. É só "quantos ancestrais esta conta tem", um
    fato estrutural sem julgamento contábil nenhum.

    Protegido contra ciclo (o mesmo problema que `HierarquiaInconsistente`
    nomeia em services.py): uma conta em ciclo não pode travar esta
    LISTAGEM — a conferência (tela própria, critério da DE-022/BL-64) é
    quem aponta isso; aqui o nível simplesmente degrada para `None`
    (exibido como "—"), sem exceção.
    """
    por_id = {conta.id: conta for conta in contas}
    niveis = {}

    def nivel_de(conta_id, caminho):
        if conta_id in niveis:
            return niveis[conta_id]
        if conta_id in caminho:
            return None
        conta = por_id[conta_id]
        if conta.conta_pai_id is None or conta.conta_pai_id not in por_id:
            resultado = 1
        else:
            pai_nivel = nivel_de(conta.conta_pai_id, caminho | {conta_id})
            resultado = None if pai_nivel is None else pai_nivel + 1
        niveis[conta_id] = resultado
        return resultado

    linhas = []
    for conta in contas:
        nivel = nivel_de(conta.id, frozenset())
        linhas.append(
            {
                "conta": conta,
                "nivel": nivel,
                "indentacao_rem": (nivel - 1) * 1.25 if nivel else 0,
            }
        )
    return linhas


@login_required
def plano_de_contas(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    contas = list(Conta.objects.filter(empresa=empresa).order_by("codigo"))
    contexto = {
        "empresa": empresa,
        "linhas": _linhas_hierarquicas(contas),
        "pode_escriturar": _pode_escriturar(request),
    }
    return render(request, "contabilidade/plano_de_contas.html", contexto)


class ContaCriarForm(forms.ModelForm):
    class Meta:
        model = Conta
        fields = ["codigo", "nome", "tipo", "natureza", "conta_pai", "aceita_lancamento"]

    def __init__(self, *args, empresa, **kwargs):
        super().__init__(*args, **kwargs)
        # Isolamento (mesmo espírito do BL-40 / ContaSerializer.
        # validate_conta_pai na API): a lista de possíveis contas-pai nunca
        # pode incluir conta de OUTRA empresa — listar todas do banco
        # vazaria estrutura de plano de contas de outros clientes do
        # escritório.
        self.fields["conta_pai"].queryset = Conta.objects.filter(empresa=empresa).order_by("codigo")
        self.fields["conta_pai"].required = False


@login_required
def conta_nova(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite criar contas nesta empresa.")

    if request.method == "POST":
        # A empresa é atribuída à instância ANTES de is_valid() — não é um
        # campo do formulário (o cliente nunca escolhe a empresa; ela vem
        # do escopo da URL, já revalidada acima). É o que permite a
        # Conta.clean() (chamada por full_clean() dentro de is_valid())
        # comparar `conta_pai.empresa_id` contra a empresa CERTA, e não
        # contra `None`.
        instancia = Conta(empresa=empresa)
        form = ContaCriarForm(request.POST, instance=instancia, empresa=empresa)
        if form.is_valid():
            try:
                # 'empresa' fica FORA da lista de campos do formulário, e
                # por isso o Django exclui a UniqueConstraint
                # "codigo_unico_por_empresa" da checagem de
                # `validate_unique()` dentro de full_clean() (regra do
                # próprio Django: uma constraint composta é pulada se
                # QUALQUER campo dela estiver fora do formulário). Este
                # try/except no INSERT é, por isso, o mecanismo real que
                # detecta duplicidade aqui — não apenas defesa de corrida,
                # como é em apps.empresas (onde o formulário já cobre
                # 'cnpj' inteiro).
                with transaction.atomic():
                    conta = form.save()
            except IntegrityError:
                form.add_error("codigo", "Já existe uma conta com este código nesta empresa.")
            else:
                registrar(acao="conta.criada", objeto=conta, request=request)
                messages.success(request, f"Conta “{conta}” criada com sucesso.")
                return redirect("contabilidade_web:plano_de_contas", empresa_id=empresa.id)
    else:
        form = ContaCriarForm(empresa=empresa)

    return render(request, "contabilidade/conta_form.html", {"empresa": empresa, "form": form})


# ---------------------------------------------------------------------------
# Lançamento (critérios 10 e 11)
# ---------------------------------------------------------------------------


def _decimal_do_formulario(texto):
    """Converte o texto digitado no campo de valor (pt-BR: vírgula decimal,
    ponto como separador de milhar opcional) para `Decimal`.

    Levanta `InvalidOperation`/`ValueError` para texto que não representa
    um número — quem chama trata isso como erro de FORMULÁRIO. A validação
    de DOMÍNIO (sinal, escala máxima — DE-010) continua sendo feita só por
    `criar_lancamento` (services.py); esta função só entende o formato de
    DIGITAÇÃO, nunca decide se o valor é aceitável contabilmente.
    """
    bruto = (texto or "").strip()
    if not bruto:
        raise ValueError("valor vazio")
    if "," in bruto:
        bruto = bruto.replace(".", "").replace(",", ".")
    return Decimal(bruto)


def _linhas_lancamento_do_post(post, num_linhas):
    """Extrai as linhas PREENCHIDAS do formulário de lançamento a partir do
    POST bruto. Uma linha totalmente vazia é ignorada — o contador não
    precisa preencher as N linhas oferecidas. Uma linha PARCIALMENTE
    preenchida é um erro de formulário, reportado como tal.
    """
    linhas = []
    erros = []
    for i in range(1, num_linhas + 1):
        conta_id = (post.get(f"conta_{i}") or "").strip()
        tipo = (post.get(f"tipo_{i}") or "").strip()
        valor_texto = (post.get(f"valor_{i}") or "").strip()
        if not conta_id and not tipo and not valor_texto:
            continue
        if not conta_id or not tipo or not valor_texto:
            erros.append(f"Linha {i}: preencha conta, tipo e valor, ou deixe a linha em branco.")
            continue
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_texto})
    return linhas, erros


def _contexto_form_lancamento(
    empresa,
    contas_disponiveis,
    num_linhas,
    *,
    data_texto,
    historico,
    chave_idempotencia,
    linhas_preenchidas=None,
    total_debito=None,
    total_credito=None,
):
    linhas = []
    for i in range(1, num_linhas + 1):
        if linhas_preenchidas is not None:
            conta_id = linhas_preenchidas.get(f"conta_{i}", "")
            tipo = linhas_preenchidas.get(f"tipo_{i}", "")
            valor_texto = linhas_preenchidas.get(f"valor_{i}", "")
        else:
            conta_id, tipo, valor_texto = "", "", ""
        linhas.append({"indice": i, "conta_id": conta_id, "tipo": tipo, "valor_texto": valor_texto})

    return {
        "empresa": empresa,
        "contas": contas_disponiveis,
        "linhas": linhas,
        "num_linhas": num_linhas,
        "data_texto": data_texto,
        "historico": historico,
        "chave_idempotencia": chave_idempotencia,
        "pode_adicionar_linha": num_linhas < LINHAS_MAXIMAS_LANCAMENTO,
        "total_debito_ptbr": _valor_ptbr(total_debito) if total_debito is not None else None,
        "total_credito_ptbr": _valor_ptbr(total_credito) if total_credito is not None else None,
    }


@login_required
def lancamento_novo(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_escriturar(request):
        return _resposta_sem_permissao(request, "Seu papel não permite lançar nesta empresa.")

    # Só contas que aceitam lançamento direto e estão ativas entram na
    # lista de escolha — restringe o que a tela OFERECE para digitar, não
    # o que o Plano de Contas MOSTRA (essa tela continua listando tudo,
    # inclusive inativas: "não esconder informação contábil" é sobre
    # RELATÓRIO, não sobre a lista de opções de um formulário de entrada).
    contas_disponiveis = list(
        Conta.objects.filter(empresa=empresa, aceita_lancamento=True, ativo=True).order_by("codigo")
    )

    if request.method == "POST":
        acao = request.POST.get("acao")
        try:
            num_linhas = int(request.POST.get("num_linhas", LINHAS_INICIAIS_LANCAMENTO))
        except TypeError, ValueError:
            num_linhas = LINHAS_INICIAIS_LANCAMENTO
        num_linhas = max(2, min(num_linhas, LINHAS_MAXIMAS_LANCAMENTO))

        data_texto = request.POST.get("data", "")
        historico = request.POST.get("historico", "").strip()
        # Idempotência (BL-43 / critério 11): o MESMO token acompanha toda
        # esta tentativa — inclusive um duplo clique, que envia duas
        # requisições com o MESMO corpo (o mesmo campo oculto), sem
        # depender de JavaScript nenhum. `criar_lancamento` (services.py)
        # já sabe devolver o MESMO lançamento em vez de duplicar quando o
        # conteúdo bate (ver o docstring de `criar_lancamento`).
        chave_idempotencia = request.POST.get("chave_idempotencia") or uuid.uuid4().hex

        if acao == "adicionar_linha":
            # Só acrescenta uma linha em branco e re-renderiza — NUNCA
            # grava nada. É a forma de a tela funcionar sem JavaScript
            # (critério 15): cada "+ linha" é um novo GET/POST normal.
            num_linhas = min(num_linhas + 1, LINHAS_MAXIMAS_LANCAMENTO)
            contexto = _contexto_form_lancamento(
                empresa,
                contas_disponiveis,
                num_linhas,
                data_texto=data_texto,
                historico=historico,
                chave_idempotencia=chave_idempotencia,
                linhas_preenchidas=request.POST,
            )
            return render(request, "contabilidade/lancamento_form.html", contexto)

        # Qualquer outro valor de 'acao' (normalmente "gravar") é tratado
        # como tentativa de gravação — nunca perde silenciosamente o que
        # foi digitado.
        linhas_brutas, erros = _linhas_lancamento_do_post(request.POST, num_linhas)

        itens = []
        total_debito = Decimal("0")
        total_credito = Decimal("0")
        contas_por_id = {conta.id: conta for conta in contas_disponiveis}
        for linha in linhas_brutas:
            conta = (
                contas_por_id.get(int(linha["conta_id"])) if linha["conta_id"].isdigit() else None
            )
            if conta is None:
                # Também cobre o caso de um `conta_id` de OUTRA empresa
                # (não está em `contas_por_id`, que só tem contas DESTA
                # empresa) — nunca vaza para a mensagem de erro qual
                # empresa seria, só que a conta é inválida.
                erros.append(f"Linha {linha['indice']}: conta inválida.")
                continue
            try:
                valor = _decimal_do_formulario(linha["valor_texto"])
            except InvalidOperation, ValueError:
                erros.append(f"Linha {linha['indice']}: valor “{linha['valor_texto']}” inválido.")
                continue
            if linha["tipo"] not in (TipoPartida.DEBITO, TipoPartida.CREDITO):
                erros.append(f"Linha {linha['indice']}: tipo de partida inválido.")
                continue
            itens.append({"conta": conta, "tipo": linha["tipo"], "valor": valor})
            if linha["tipo"] == TipoPartida.DEBITO:
                total_debito += valor
            else:
                total_credito += valor

        data_lancamento = None
        if not _PADRAO_DATA_SIMPLES.fullmatch(data_texto or ""):
            erros.append("Informe uma data válida.")
        else:
            try:
                data_lancamento = date.fromisoformat(data_texto)
            except ValueError:
                erros.append("Informe uma data válida.")

        totais_batem = total_debito == total_credito and total_debito > 0

        # Critério 10: a tela mostra os dois totais e IMPEDE o envio
        # enquanto forem diferentes. Quem garante isto DE VERDADE é
        # `criar_lancamento` abaixo (a validação do servidor) — esta
        # checagem aqui é só conveniência, e o teste do critério 10 POSTa
        # direto para esta view com débito != crédito para provar que,
        # mesmo que ESTA checagem não existisse, nenhum lançamento seria
        # gravado.
        if not erros and len(itens) >= 2 and totais_batem and data_lancamento is not None:
            try:
                lancamento = criar_lancamento(
                    empresa=empresa,
                    data=data_lancamento,
                    historico=historico,
                    itens=itens,
                    criado_por=request.user,
                    chave_idempotencia=chave_idempotencia,
                )
            except ChaveIdempotenciaConflitante as exc:
                erros.append(str(exc))
            except LancamentoInvalido as exc:
                erros.append(str(exc))
            else:
                # O serviço informa se de fato criou ou reaproveitou um
                # lançamento existente (mesma Idempotency-Key) — a trilha
                # de auditoria e a mensagem precisam refletir o resultado
                # real (mesmo cuidado da API, ver views.py).
                if lancamento.criado_agora:
                    registrar(acao="lancamento.criado", objeto=lancamento, request=request)
                    messages.success(request, "Lançamento gravado com sucesso.")
                else:
                    registrar(
                        acao="lancamento.criacao_repetida",
                        objeto=lancamento,
                        request=request,
                        detalhes={
                            "chave_idempotencia_hash": hashlib.sha256(
                                chave_idempotencia.encode("utf-8")
                            ).hexdigest()[:12]
                        },
                    )
                    messages.info(
                        request,
                        "Este lançamento já havia sido gravado (nova tentativa com o "
                        "mesmo envio, sem duplicar).",
                    )
                return redirect(
                    "contabilidade_web:lancamento_detalhe",
                    empresa_id=empresa.id,
                    lancamento_id=lancamento.id,
                )
        elif not erros:
            if len(itens) < 2:
                erros.append("Informe ao menos duas partidas.")
            elif not totais_batem:
                erros.append(
                    f"Débitos ({_valor_ptbr(total_debito)}) e créditos "
                    f"({_valor_ptbr(total_credito)}) precisam ser iguais antes de gravar."
                )

        for erro in erros:
            messages.error(request, erro)

        contexto = _contexto_form_lancamento(
            empresa,
            contas_disponiveis,
            num_linhas,
            data_texto=data_texto,
            historico=historico,
            chave_idempotencia=chave_idempotencia,
            linhas_preenchidas=request.POST,
            total_debito=total_debito,
            total_credito=total_credito,
        )
        return render(request, "contabilidade/lancamento_form.html", contexto, status=400)

    # GET: formulário em branco, com uma chave de idempotência NOVA para
    # esta tentativa (critério 11 — cada visita "limpa" ao formulário é uma
    # tentativa distinta).
    contexto = _contexto_form_lancamento(
        empresa,
        contas_disponiveis,
        LINHAS_INICIAIS_LANCAMENTO,
        data_texto=timezone.localdate().isoformat(),
        historico="",
        chave_idempotencia=uuid.uuid4().hex,
    )
    return render(request, "contabilidade/lancamento_form.html", contexto)


@login_required
def lancamento_detalhe(request, empresa_id, lancamento_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    lancamento = get_object_or_404(
        LancamentoContabil.objects.prefetch_related("itens__conta"),
        pk=lancamento_id,
        empresa=empresa,
    )

    itens = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for item in lancamento.itens.all():
        if item.tipo == TipoPartida.DEBITO:
            total_debito += item.valor
        else:
            total_credito += item.valor
        itens.append(
            {"conta": item.conta, "tipo": item.tipo, "valor_ptbr": _valor_ptbr(item.valor)}
        )

    contexto = {
        "empresa": empresa,
        "lancamento": lancamento,
        "itens": itens,
        "total_debito_ptbr": _valor_ptbr(total_debito),
        "total_credito_ptbr": _valor_ptbr(total_credito),
    }
    return render(request, "contabilidade/lancamento_detalhe.html", contexto)


# ---------------------------------------------------------------------------
# Diário
# ---------------------------------------------------------------------------


@login_required
def diario(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    contexto = {"empresa": empresa, "inicio": inicio, "fim": fim}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/diario.html", contexto, status=400)

    lotes = []
    total_debito = Decimal("0")
    total_credito = Decimal("0")
    for lancamento in listar_diario(empresa=empresa, inicio=inicio, fim=fim):
        debito_lote = Decimal("0")
        credito_lote = Decimal("0")
        for item in lancamento.itens.all():
            if item.tipo == TipoPartida.DEBITO:
                debito_lote += item.valor
            else:
                credito_lote += item.valor
        total_debito += debito_lote
        total_credito += credito_lote
        lotes.append(
            {
                "lancamento": lancamento,
                "debito_ptbr": _valor_ptbr(debito_lote),
                "credito_ptbr": _valor_ptbr(credito_lote),
            }
        )

    contexto.update(
        {
            "lotes": lotes,
            "total_debito_ptbr": _valor_ptbr(total_debito),
            "total_credito_ptbr": _valor_ptbr(total_credito),
        }
    )
    return render(request, "contabilidade/diario.html", contexto)


# ---------------------------------------------------------------------------
# Razão
# ---------------------------------------------------------------------------


@login_required
def razao(request, empresa_id, conta_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )
    conta = get_object_or_404(Conta, pk=conta_id, empresa=empresa)

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    contexto = {"empresa": empresa, "conta": conta, "inicio": inicio, "fim": fim}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/razao.html", contexto, status=400)

    try:
        apuracao = apurar_razao(conta=conta, empresa=empresa, inicio=inicio, fim=fim)
    except HierarquiaInconsistente as exc:
        # Ciclo ou conta_pai de outra empresa: resposta controlada,
        # nomeando a conta, nunca um 500 mudo (mesmo tratamento da API).
        messages.error(request, str(exc))
        return render(request, "contabilidade/razao.html", contexto, status=409)

    itens = []
    for linha in apuracao["itens"]:
        saldo_abs, saldo_nat = _saldo_absoluto_com_natureza(linha["saldo"], conta.natureza)
        itens.append(
            {
                "lancamento_id": linha["lancamento_id"],
                "data": linha["data"],
                "historico": linha["historico"],
                "conta_codigo": linha["conta"],
                "conta_nome": linha["conta_nome"],
                "tipo": linha["tipo"],
                "valor_ptbr": _valor_ptbr(linha["valor"]),
                "saldo_ptbr": _valor_ptbr(saldo_abs),
                "saldo_natureza": _indicador_natureza(saldo_nat),
            }
        )

    saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_anterior"], conta.natureza
    )
    saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
        apuracao["saldo_final"], conta.natureza
    )

    contexto.update(
        {
            "consolidado": apuracao["consolidado"],
            "itens": itens,
            "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
            "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
            "total_debito_ptbr": _valor_ptbr(apuracao["total_debito"]),
            "total_credito_ptbr": _valor_ptbr(apuracao["total_credito"]),
            "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
            "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
        }
    )
    return render(request, "contabilidade/razao.html", contexto)


# ---------------------------------------------------------------------------
# Balancete (critério 6)
# ---------------------------------------------------------------------------


@login_required
def balancete(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    inicio, fim, erro_periodo = _periodo_do_formulario(request)
    nivel, erro_nivel = _nivel_do_formulario(request)
    contexto = {"empresa": empresa, "inicio": inicio, "fim": fim, "nivel": nivel}
    if erro_periodo:
        messages.error(request, erro_periodo)
        return render(request, "contabilidade/balancete.html", contexto, status=400)
    if erro_nivel:
        messages.error(request, erro_nivel)
        return render(request, "contabilidade/balancete.html", contexto, status=400)

    try:
        apuracao = apurar_balancete(empresa=empresa, inicio=inicio, fim=fim, nivel=nivel)
    except HierarquiaInconsistente as exc:
        messages.error(request, str(exc))
        return render(request, "contabilidade/balancete.html", contexto, status=409)

    # Necessário só para montar o link "ver Razão desta conta" (critério
    # 12): `apurar_balancete` devolve o CÓDIGO da conta (é o que o
    # contador lê), não o id interno que a URL do Razão precisa. Uma única
    # consulta, fora do laço — não é N+1.
    ids_por_codigo = dict(Conta.objects.filter(empresa=empresa).values_list("codigo", "id"))

    linhas = []
    for linha in apuracao["contas"]:
        saldo_anterior_abs, saldo_anterior_nat = _saldo_absoluto_com_natureza(
            linha["saldo_anterior"], linha["natureza"]
        )
        saldo_final_abs, saldo_final_nat = _saldo_absoluto_com_natureza(
            linha["saldo_final"], linha["natureza"]
        )
        linhas.append(
            {
                "conta_id": ids_por_codigo.get(linha["conta"]),
                "codigo": linha["conta"],
                "nome": linha["nome"],
                "nivel": linha["nivel"],
                "indentacao_rem": (linha["nivel"] - 1) * 1.25,
                "analitica": linha["analitica"],
                "saldo_anterior_ptbr": _valor_ptbr(saldo_anterior_abs),
                "saldo_anterior_natureza": _indicador_natureza(saldo_anterior_nat),
                "debitos_ptbr": _valor_ptbr(linha["debitos"]),
                "creditos_ptbr": _valor_ptbr(linha["creditos"]),
                # DE-024 §2: é sobre ESTAS duas colunas (o movimento
                # PRÓPRIO de cada linha), não sobre "debitos"/"creditos"
                # (consolidados), que a soma das linhas exibidas reconcilia
                # com o rodapé (critério 6) — em qualquer arranjo de plano
                # de contas, porque todo lançamento é próprio de
                # exatamente uma conta.
                "debitos_proprios_ptbr": _valor_ptbr(linha["debitos_proprios"]),
                "creditos_proprios_ptbr": _valor_ptbr(linha["creditos_proprios"]),
                "saldo_final_ptbr": _valor_ptbr(saldo_final_abs),
                "saldo_final_natureza": _indicador_natureza(saldo_final_nat),
            }
        )

    contexto.update(
        {
            "linhas": linhas,
            "total_debitos_ptbr": _valor_ptbr(apuracao["total_debitos"]),
            "total_creditos_ptbr": _valor_ptbr(apuracao["total_creditos"]),
        }
    )
    return render(request, "contabilidade/balancete.html", contexto)


# ---------------------------------------------------------------------------
# Conferência
# ---------------------------------------------------------------------------


@login_required
def conferencia(request, empresa_id):
    if request.escritorio is None:
        return _resposta_sem_escritorio(request)
    empresa = _empresa_do_escritorio_ativo(request, empresa_id)
    if not _pode_ler(request):
        return _resposta_sem_permissao(
            request, "Seu papel não permite ler a contabilidade desta empresa."
        )

    lotes = []
    for lancamento in localizar_lotes_desbalanceados(empresa=empresa):
        # Linguagem de contador (a tela pede isto explicitamente), em vez
        # do rótulo técnico de três vias que a API devolve
        # ("sem_partidas"/"partida_unica"/"desbalanceado" — achado novo 12).
        if lancamento.quantidade_itens == 0:
            motivo = "Lançamento sem nenhuma partida."
        elif lancamento.quantidade_itens == 1:
            motivo = "Lançamento com uma única partida (sem contrapartida)."
        else:
            motivo = "Débitos e créditos não coincidem."
        lotes.append(
            {
                "lancamento": lancamento,
                "motivo": motivo,
                "total_debito_ptbr": _valor_ptbr(lancamento.total_debito),
                "total_credito_ptbr": _valor_ptbr(lancamento.total_credito),
                "diferenca_ptbr": _valor_ptbr(lancamento.total_debito - lancamento.total_credito),
            }
        )

    contas_sinteticas = [
        {
            "conta": conta,
            "debitos_ptbr": _valor_ptbr(conta.debitos),
            "creditos_ptbr": _valor_ptbr(conta.creditos),
        }
        for conta in localizar_contas_sinteticas_com_movimento(empresa=empresa)
    ]
    contas_com_subordinadas = localizar_contas_que_aceitam_lancamento_e_tem_subordinadas(
        empresa=empresa
    )
    hierarquia_inconsistente = localizar_inconsistencias_de_hierarquia(empresa=empresa)

    contexto = {
        "empresa": empresa,
        "lotes": lotes,
        "contas_sinteticas": contas_sinteticas,
        "contas_com_subordinadas": contas_com_subordinadas,
        "hierarquia_inconsistente": hierarquia_inconsistente,
        "tudo_certo": not (
            lotes or contas_sinteticas or contas_com_subordinadas or hierarquia_inconsistente
        ),
    }
    return render(request, "contabilidade/conferencia.html", contexto)
