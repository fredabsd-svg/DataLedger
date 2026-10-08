"""Receita mensal do Simples Nacional por mercado — DL-074, frente A (domínio).

Contrato: docs/planos/DL-074-receita-e-rbt12-do-simples.md (itens 2 a 4 e
critérios 1, 6 e 7). Decisões que o código não explica sozinho:

- A receita do mês é ESCRITURAÇÃO EFETIVADA (DL-072, pelo valor do serviço,
  `vServ`) + RECEITA INFORMADA CONFIRMADA, por mercado (HI-64). Rascunho e
  estornada não entram em nenhum total.
- O mercado de cada escrituração vem da natureza (`mercado_da_natureza`, a
  fonte única de HI-67). Exportação nunca soma no interno.
- "Início de uso do sistema" = o MÊS LOCAL (Brasília) de `Empresa.criado_em`
  (`inicio_de_uso`). Origem "histórico" só vale em competência ANTERIOR a esse
  mês. Escolha e justificativa: o cadastro é um fato gravado uma vez, antes de
  qualquer movimento; a primeira escrituração não pode abrir a janela do
  histórico por si mesma. Hipótese para o Fred validar (ver o relatório).
- A confirmação do mês guarda o TOTAL no instante do ato. Se a receita do mês
  mudar depois (por exemplo, uma escrituração efetivada que não passa pelo
  estorno), o mês deixa de estar confirmado de fato: a situação é
  `a_retificar` e o RBT12 não o usa. Assim a regra não depende de todo caminho
  de escrita passar pelo gancho.
- Estorno de escrituração ou de receita informada de mês CONFIRMADO reabre a
  confirmação e a marca `a_retificar` (Res. CGSN 140 art. 18: o cancelamento
  deduz no período de origem, nunca no mês corrente). O gancho genérico é
  `marcar_a_retificar`; `marcar_a_retificar_por_estorno` é a porta do estorno.
  Chamado por `apps.fiscal.escrituracao.estornar_escrituracao`, por
  `apps.fiscal.escrituracao.efetivar_escrituracao` (efetivar em mês confirmado
  também muda a receita do mês) e por `estornar_receita_informada`.
- Receita informada confirmada em mês já confirmado é recusada (409): mudaria o
  total de um mês declarado completo sem o ato de reabertura, com motivo.

Ordem de travas (concorrência): a EMPRESA é travada primeiro (`select_for_update`)
por qualquer serviço que mude receita, confirmação ou estorno. Assim a
confirmação e o estorno não se intercalam. A ordem é a mesma nos dois sentidos,
por isso não há impasse entre eles.

Valores: `Decimal`, duas casas (DE-010). Nenhum arredondamento de cálculo aqui.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal.models import (
    ConfirmacaoReceitaMensal,
    EscrituracaoFiscal,
    EstadoConfirmacaoMes,
    EstadoEscrituracao,
    EstadoReceitaInformada,
    MercadoReceita,
    OpcaoRegimeCaixaSimples,
    OrigemReceitaInformada,
    ReceitaInformada,
    mercado_da_natureza,
)

ZERO = Decimal("0.00")
ANO_MINIMO, ANO_MAXIMO = 1970, 2999
MOTIVO_MAXIMO = 500
DOCUMENTO_SUPORTE_MAXIMO = 300

# Último PA com opção pelo caixa (HI-66). A partir de 2027 a base é a competência.
ANO_ULTIMO_CAIXA = 2026

# Situação do mês, como o RBT12 e a tela a veem (DL-074, critério 5).
SITUACAO_CONFIRMADO = "confirmado"
SITUACAO_NAO_CONFIRMADO = "nao_confirmado"
SITUACAO_A_RETIFICAR = "a_retificar"

_RESTRICAO_CONFIRMACAO_UNICA = "confirmacao_mes_unica_por_empresa"
_RESTRICAO_OPCAO_CAIXA_UNICA = "opcao_caixa_unica_por_ano"


# ---------------------------------------------------------------------------
# Erros — mensagens em português, sem alíquota nem imposto.
# A API traduz `EntradaInvalidaReceita` para 400 e `ReceitaErro` para 409.
# ---------------------------------------------------------------------------


class ReceitaErro(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaReceita(ReceitaErro):
    pass


# ---------------------------------------------------------------------------
# Início de uso e histórico
# ---------------------------------------------------------------------------


def inicio_de_uso(empresa: Empresa) -> tuple[int, int]:
    """(ano, mês) em que a empresa começou a ser usada no sistema.

    É o mês local (Brasília) do cadastro, `Empresa.criado_em`, que é gravado uma
    única vez (`auto_now_add`) e não muda por ato do usuário. Competência
    anterior a este mês pode ser lançada como "histórico"; a partir dele não.
    """
    local = timezone.localtime(empresa.criado_em)
    return (local.year, local.month)


def _antes_do_inicio_de_uso(empresa: Empresa, ano: int, mes: int) -> bool:
    return (ano, mes) < inicio_de_uso(empresa)


# ---------------------------------------------------------------------------
# Leitura: composição do mês
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComposicaoMercado:
    """Receita de UM mercado em UM mês: o que veio de documento e o que foi informado."""

    mercado: str
    documento: Decimal
    informado: Decimal

    @property
    def total(self) -> Decimal:
        return self.documento + self.informado


@dataclass(frozen=True)
class Composicao:
    """Os dois mercados de um mês. Sempre os dois, mesmo que zerados."""

    interno: ComposicaoMercado
    externo: ComposicaoMercado

    def de(self, mercado: str) -> ComposicaoMercado:
        return self.interno if mercado == MercadoReceita.INTERNO else self.externo

    def total(self, mercado: str) -> Decimal:
        return self.de(mercado).total


def _proximo_mes(ano: int, mes: int) -> date:
    return date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)


def composicao_do_mes(empresa: Empresa, ano: int, mes: int) -> Composicao:
    """Receita do mês por mercado: escriturações efetivadas + informadas confirmadas.

    Consulta só a empresa dada (isolamento, AGENTS.md §11). O mercado de cada
    escrituração vem de `mercado_da_natureza` (HI-67), e não é repetido aqui.
    """
    documento = {MercadoReceita.INTERNO: ZERO, MercadoReceita.EXTERNO: ZERO}
    inicio = date(ano, mes, 1)
    linhas = (
        EscrituracaoFiscal.objects.filter(
            empresa=empresa,
            estado=EstadoEscrituracao.EFETIVADA,
            data_competencia__gte=inicio,
            data_competencia__lt=_proximo_mes(ano, mes),
        )
        .values("natureza")
        .annotate(total=Sum("valor_servico"))
        .order_by()
    )
    for linha in linhas:
        mercado = mercado_da_natureza(linha["natureza"])
        documento[mercado] += linha["total"] or ZERO

    informado = {MercadoReceita.INTERNO: ZERO, MercadoReceita.EXTERNO: ZERO}
    linhas_informadas = (
        ReceitaInformada.objects.filter(
            empresa=empresa, ano=ano, mes=mes, estado=EstadoReceitaInformada.CONFIRMADA
        )
        .values("mercado")
        .annotate(total=Sum("valor"))
        .order_by()
    )
    for linha in linhas_informadas:
        informado[linha["mercado"]] += linha["total"] or ZERO

    return Composicao(
        interno=ComposicaoMercado(
            MercadoReceita.INTERNO,
            documento[MercadoReceita.INTERNO],
            informado[MercadoReceita.INTERNO],
        ),
        externo=ComposicaoMercado(
            MercadoReceita.EXTERNO,
            documento[MercadoReceita.EXTERNO],
            informado[MercadoReceita.EXTERNO],
        ),
    )


def confirmacao_do_mes(empresa: Empresa, ano: int, mes: int, *, travar: bool = False):
    consulta = ConfirmacaoReceitaMensal.objects
    if travar:
        consulta = consulta.select_for_update(of=("self",))
    return consulta.filter(empresa=empresa, ano=ano, mes=mes).first()


def situacao_de(confirmacao, composicao: Composicao) -> str:
    """Situação do mês a partir da linha de confirmação e da composição atual.

    Confirmada e com total igual ao do ato → confirmado. Confirmada com total
    diferente → a retificar (a receita mudou depois). Reaberta → a retificar se
    veio de estorno; caso contrário, não confirmado. Sem linha → não confirmado.
    """
    if confirmacao is None:
        return SITUACAO_NAO_CONFIRMADO
    if confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA:
        confirmado_ate_agora = confirmacao.valor_confirmado_interno == composicao.total(
            MercadoReceita.INTERNO
        ) and confirmacao.valor_confirmado_externo == composicao.total(MercadoReceita.EXTERNO)
        return SITUACAO_CONFIRMADO if confirmado_ate_agora else SITUACAO_A_RETIFICAR
    return SITUACAO_A_RETIFICAR if confirmacao.a_retificar else SITUACAO_NAO_CONFIRMADO


def situacao_do_mes(empresa: Empresa, ano: int, mes: int) -> str:
    """Situação do mês para o RBT12: só `SITUACAO_CONFIRMADO` entra na apuração."""
    return situacao_de(confirmacao_do_mes(empresa, ano, mes), composicao_do_mes(empresa, ano, mes))


@dataclass(frozen=True)
class ReceitaDoMes:
    ano: int
    mes: int
    composicao: Composicao
    situacao: str
    confirmacao: ConfirmacaoReceitaMensal | None
    receitas_informadas: list


def receita_do_mes(empresa: Empresa, ano: int, mes: int) -> ReceitaDoMes:
    """Receita do mês, com a composição visível (documento × informado) e a situação."""
    validar_competencia(ano, mes)
    composicao = composicao_do_mes(empresa, ano, mes)
    confirmacao = confirmacao_do_mes(empresa, ano, mes)
    informadas = list(
        ReceitaInformada.objects.filter(empresa=empresa, ano=ano, mes=mes).order_by("id")
    )
    return ReceitaDoMes(
        ano=ano,
        mes=mes,
        composicao=composicao,
        situacao=situacao_de(confirmacao, composicao),
        confirmacao=confirmacao,
        receitas_informadas=informadas,
    )


# ---------------------------------------------------------------------------
# Validação de entrada
# ---------------------------------------------------------------------------


def validar_competencia(ano, mes) -> None:
    if isinstance(ano, bool) or not isinstance(ano, int) or not ANO_MINIMO <= ano <= ANO_MAXIMO:
        raise EntradaInvalidaReceita(f"Ano inválido: {ano!r}.")
    if isinstance(mes, bool) or not isinstance(mes, int) or not 1 <= mes <= 12:
        raise EntradaInvalidaReceita(f"Mês inválido: {mes!r}.")


def _mm_aaaa(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


def _texto_obrigatorio(valor, nome: str, maximo: int) -> str:
    limpo = valor.strip() if isinstance(valor, str) else ""
    if not limpo:
        raise EntradaInvalidaReceita(f"Informe {nome}.")
    if len(limpo) > maximo:
        raise EntradaInvalidaReceita(f"{nome.capitalize()} tem no máximo {maximo} caracteres.")
    return limpo


def _valor_positivo(valor) -> Decimal:
    """Valor da receita informada: decimal positivo, até 2 casas, sem float.

    `float` é recusado de propósito: 0.1 em binário não é 0.1, e a receita
    informada é declaração do contador. Texto ou `Decimal` são aceitos.
    """
    if isinstance(valor, float):
        raise EntradaInvalidaReceita(
            "Valor em ponto flutuante não é aceito; informe o valor em texto."
        )
    try:
        decimal = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EntradaInvalidaReceita("Valor inválido.") from exc
    if not decimal.is_finite() or decimal <= 0:
        raise EntradaInvalidaReceita("O valor da receita informada tem de ser maior que zero.")
    if decimal.normalize().as_tuple().exponent < -2:
        raise EntradaInvalidaReceita("O valor aceita no máximo duas casas decimais.")
    if decimal >= Decimal("1000000000000000"):
        raise EntradaInvalidaReceita("O valor excede o limite de 15 dígitos inteiros.")
    return decimal.quantize(Decimal("0.01"))


def _motivo(motivo) -> str:
    return _texto_obrigatorio(motivo, "o motivo", MOTIVO_MAXIMO)


# ---------------------------------------------------------------------------
# Trilha e gravação
# ---------------------------------------------------------------------------


def _iso(valor):
    return valor.isoformat() if valor is not None else None


def _snapshot_confirmacao(confirmacao) -> dict | None:
    if confirmacao is None:
        return None
    return {
        "estado": confirmacao.estado,
        "valor_confirmado_interno": str(confirmacao.valor_confirmado_interno),
        "valor_confirmado_externo": str(confirmacao.valor_confirmado_externo),
        "confirmada_em": _iso(confirmacao.confirmada_em),
        "confirmada_por": confirmacao.confirmada_por_id,
        "a_retificar": confirmacao.a_retificar,
        "reaberta_em": _iso(confirmacao.reaberta_em),
        "reaberta_por": confirmacao.reaberta_por_id,
        "motivo_reabertura": confirmacao.motivo_reabertura,
    }


def _snapshot_receita(receita: ReceitaInformada) -> dict:
    return {
        "estado": receita.estado,
        "ano": receita.ano,
        "mes": receita.mes,
        "mercado": receita.mercado,
        "valor": str(receita.valor),
        "origem": receita.origem,
        "confirmada_em": _iso(receita.confirmada_em),
        "estornada_em": _iso(receita.estornada_em),
        "motivo_estorno": receita.motivo_estorno,
    }


def travar_empresa(empresa: Empresa) -> Empresa:
    """Trava a linha da EMPRESA. Deve ser a primeira trava de cada serviço de
    receita, dentro de `transaction.atomic()` (ver a docstring do módulo)."""
    return (
        Empresa.objects.select_for_update(of=("self",))
        .select_related("escritorio")
        .get(pk=empresa.pk)
    )


def _inserir(objeto, restricao: str, mensagem: str) -> None:
    """INSERT traduzindo a violação de uma restrição única em erro de negócio.

    A trava de empresa já impede a corrida; a restrição do banco é a segunda
    defesa. O SAVEPOINT isola só este INSERT, para a transação de quem chamou
    continuar utilizável.
    """
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "__cause__", None), "diag", None)
        if getattr(diag, "constraint_name", None) == restricao:
            raise ReceitaErro(mensagem) from exc
        raise


# ---------------------------------------------------------------------------
# Confirmação e reabertura do mês
# ---------------------------------------------------------------------------


@transaction.atomic
def confirmar_mes(
    empresa: Empresa, ano: int, mes: int, usuario, request=None
) -> ConfirmacaoReceitaMensal:
    """Declara "receita de MM/AAAA completa", para os dois mercados.

    Grava o total de cada mercado no instante do ato. Mês já confirmado (e
    sem mudança) é recusado: para confirmar de novo, reabra com motivo antes.
    Mês reaberto (inclusive a retificar) é confirmado de novo, com novo ato.
    """
    validar_competencia(ano, mes)
    travada = travar_empresa(empresa)
    confirmacao = confirmacao_do_mes(travada, ano, mes, travar=True)
    if confirmacao is not None and confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA:
        raise ReceitaErro(
            f"A receita de {_mm_aaaa(ano, mes)} já está confirmada. "
            "Reabra o mês, com motivo, para alterá-la."
        )

    composicao = composicao_do_mes(travada, ano, mes)
    antes = _snapshot_confirmacao(confirmacao)
    agora = timezone.now()
    valores = {
        "valor_confirmado_interno": composicao.total(MercadoReceita.INTERNO),
        "valor_confirmado_externo": composicao.total(MercadoReceita.EXTERNO),
        "confirmada_em": agora,
        "confirmada_por": usuario,
    }
    if confirmacao is None:
        confirmacao = ConfirmacaoReceitaMensal(
            empresa=travada,
            ano=ano,
            mes=mes,
            estado=EstadoConfirmacaoMes.CONFIRMADA,
            **valores,
        )
        _inserir(
            confirmacao,
            _RESTRICAO_CONFIRMACAO_UNICA,
            "Este mês acabou de ser confirmado por outra ação. Atualize a tela.",
        )
    else:
        atualizadas = ConfirmacaoReceitaMensal.objects.filter(
            pk=confirmacao.pk, estado=EstadoConfirmacaoMes.REABERTA
        ).update(
            estado=EstadoConfirmacaoMes.CONFIRMADA,
            a_retificar=False,
            reaberta_em=None,
            reaberta_por=None,
            motivo_reabertura="",
            **valores,
        )
        if atualizadas != 1:
            raise ReceitaErro("A confirmação do mês mudou enquanto era gravada. Atualize a tela.")
        confirmacao = ConfirmacaoReceitaMensal.objects.get(pk=confirmacao.pk)

    registrar(
        acao="receita_mensal.confirmada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=confirmacao,
        request=request,
        detalhes={
            "empresa_id": travada.pk,
            "ano": ano,
            "mes": mes,
            "antes": antes,
            "depois": _snapshot_confirmacao(confirmacao),
        },
    )
    return confirmacao


@transaction.atomic
def reabrir_mes(
    empresa: Empresa, ano: int, mes: int, motivo: str, usuario, request=None
) -> ConfirmacaoReceitaMensal:
    """Reabre um mês confirmado. O motivo é obrigatório e fica na linha e na trilha."""
    validar_competencia(ano, mes)
    motivo_limpo = _motivo(motivo)
    travada = travar_empresa(empresa)
    confirmacao = confirmacao_do_mes(travada, ano, mes, travar=True)
    if confirmacao is None or confirmacao.estado != EstadoConfirmacaoMes.CONFIRMADA:
        raise ReceitaErro(
            f"Só mês confirmado pode ser reaberto; {_mm_aaaa(ano, mes)} não está confirmado."
        )

    antes = _snapshot_confirmacao(confirmacao)
    atualizadas = ConfirmacaoReceitaMensal.objects.filter(
        pk=confirmacao.pk, estado=EstadoConfirmacaoMes.CONFIRMADA
    ).update(
        estado=EstadoConfirmacaoMes.REABERTA,
        reaberta_em=timezone.now(),
        reaberta_por=usuario,
        motivo_reabertura=motivo_limpo,
    )
    if atualizadas != 1:
        raise ReceitaErro("A confirmação do mês mudou enquanto era reaberta. Atualize a tela.")
    confirmacao.refresh_from_db()

    registrar(
        acao="receita_mensal.reaberta",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=confirmacao,
        request=request,
        detalhes={
            "empresa_id": travada.pk,
            "ano": ano,
            "mes": mes,
            "antes": antes,
            "depois": _snapshot_confirmacao(confirmacao),
        },
    )
    return confirmacao


def marcar_a_retificar(
    empresa: Empresa,
    ano: int,
    mes: int,
    usuario,
    *,
    origem: str,
    motivo: str,
    acao: str,
    request=None,
):
    """GANCHO "a retificar" (DL-074, critério 6). Chamado DENTRO da transação do ato
    que muda a receita de um mês, com a empresa JÁ TRAVADA pelo chamador (ordem de
    travas: empresa primeiro, depois o que o ato trava).

    Quem chama: o estorno (de escrituração ou de receita informada) e a efetivação
    de escrituração em mês já confirmado. `motivo` (texto livre, até 500 caracteres)
    e `acao` (nome na trilha) são do chamador: o ato é que sabe por que o mês volta.

    Mês confirmado → reaberto e marcado `a_retificar`, com `motivo` na linha.
    Já reaberto → só marca `a_retificar`. Sem confirmação → nada muda (o mês não
    estava declarado completo). Não toca em nenhum outro mês: a correção é no mês
    de origem (Res. CGSN 140 art. 18, para o estorno).
    """
    confirmacao = confirmacao_do_mes(empresa, ano, mes, travar=True)
    if confirmacao is None:
        return None
    if confirmacao.estado == EstadoConfirmacaoMes.REABERTA and confirmacao.a_retificar:
        return confirmacao

    antes = _snapshot_confirmacao(confirmacao)
    agora = timezone.now()
    if confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA:
        atualizadas = ConfirmacaoReceitaMensal.objects.filter(
            pk=confirmacao.pk, estado=EstadoConfirmacaoMes.CONFIRMADA
        ).update(
            estado=EstadoConfirmacaoMes.REABERTA,
            a_retificar=True,
            reaberta_em=agora,
            reaberta_por=usuario,
            motivo_reabertura=motivo,
        )
    else:
        atualizadas = ConfirmacaoReceitaMensal.objects.filter(
            pk=confirmacao.pk, estado=EstadoConfirmacaoMes.REABERTA
        ).update(a_retificar=True)
    if atualizadas != 1:
        raise ReceitaErro("A confirmação do mês mudou enquanto era retificada. Atualize a tela.")
    confirmacao.refresh_from_db()

    registrar(
        acao=acao,
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=confirmacao,
        request=request,
        detalhes={
            "empresa_id": empresa.pk,
            "ano": ano,
            "mes": mes,
            "origem": origem,
            "antes": antes,
            "depois": _snapshot_confirmacao(confirmacao),
        },
    )
    return confirmacao


def marcar_a_retificar_por_estorno(
    empresa: Empresa, ano: int, mes: int, usuario, origem: str, request=None
):
    """Porta do ESTORNO sobre o gancho `marcar_a_retificar` (DL-074, critério 6).

    Mantém o texto e a ação de trilha que o estorno já gravava (testes e auditoria
    dependem deles). Res. CGSN 140 art. 18: o cancelamento deduz no período de origem.
    """
    return marcar_a_retificar(
        empresa,
        ano,
        mes,
        usuario,
        origem=origem,
        motivo=(
            f"Estorno de {origem}: receita de {_mm_aaaa(ano, mes)} a retificar "
            "(Res. CGSN 140, art. 18)."
        ),
        acao="receita_mensal.a_retificar_por_estorno",
        request=request,
    )


# ---------------------------------------------------------------------------
# Receita informada: lançar, confirmar, estornar
# ---------------------------------------------------------------------------


@transaction.atomic
def lancar_receita_informada(
    empresa: Empresa,
    ano: int,
    mes: int,
    mercado: str,
    valor,
    origem: str,
    motivo: str,
    documento_suporte: str,
    usuario,
    request=None,
) -> ReceitaInformada:
    """Cria a receita informada em RASCUNHO. Rascunho não entra em nenhum total.

    Origem "histórico" só é aceita em competência anterior ao início de uso do
    sistema (critério 7). A recusa é feita aqui, e não só na tela.
    """
    validar_competencia(ano, mes)
    if mercado not in MercadoReceita.values:
        raise EntradaInvalidaReceita(f"Mercado desconhecido: {mercado!r}.")
    if origem not in OrigemReceitaInformada.values:
        raise EntradaInvalidaReceita(f"Origem fora do catálogo: {origem!r}.")
    valor_decimal = _valor_positivo(valor)
    motivo_limpo = _motivo(motivo)
    suporte = _texto_obrigatorio(
        documento_suporte, "o documento de suporte", DOCUMENTO_SUPORTE_MAXIMO
    )
    if origem == OrigemReceitaInformada.HISTORICO_PRE_SISTEMA and not _antes_do_inicio_de_uso(
        empresa, ano, mes
    ):
        inicio_ano, inicio_mes = inicio_de_uso(empresa)
        raise EntradaInvalidaReceita(
            "A origem 'histórico' só vale para competência anterior ao início de uso "
            f"do sistema ({inicio_mes:02d}/{inicio_ano}). {_mm_aaaa(ano, mes)} é a partir daí: "
            "use outra origem."
        )

    receita = ReceitaInformada(
        empresa=empresa,
        ano=ano,
        mes=mes,
        mercado=mercado,
        valor=valor_decimal,
        origem=origem,
        motivo=motivo_limpo,
        documento_suporte=suporte,
        estado=EstadoReceitaInformada.RASCUNHO,
        criado_por=usuario,
    )
    receita.save()
    registrar(
        acao="receita_informada.lancada",
        usuario=usuario,
        escritorio=empresa.escritorio,
        objeto=receita,
        request=request,
        detalhes={"empresa_id": empresa.pk, "depois": _snapshot_receita(receita)},
    )
    return receita


@transaction.atomic
def confirmar_receita_informada(receita: ReceitaInformada, usuario, request=None):
    """Rascunho → confirmada. Recusado se o mês já está confirmado (reabra antes)."""
    travada = travar_empresa(receita.empresa)
    atual = ReceitaInformada.objects.select_for_update(of=("self",)).get(
        pk=receita.pk, empresa=travada
    )
    if atual.estado != EstadoReceitaInformada.RASCUNHO:
        raise ReceitaErro(
            f"Só receita em rascunho pode ser confirmada; esta está '{atual.get_estado_display()}'."
        )
    confirmacao = confirmacao_do_mes(travada, atual.ano, atual.mes, travar=True)
    if confirmacao is not None and confirmacao.estado == EstadoConfirmacaoMes.CONFIRMADA:
        raise ReceitaErro(
            f"A receita de {_mm_aaaa(atual.ano, atual.mes)} já está confirmada. "
            "Reabra o mês, com motivo, antes de incluir receita nova."
        )

    antes = _snapshot_receita(atual)
    atualizadas = ReceitaInformada.objects.filter(
        pk=atual.pk, estado=EstadoReceitaInformada.RASCUNHO
    ).update(
        estado=EstadoReceitaInformada.CONFIRMADA,
        confirmada_em=timezone.now(),
        confirmada_por=usuario,
    )
    if atualizadas != 1:
        raise ReceitaErro("A receita mudou enquanto era confirmada. Atualize a lista.")
    atual.refresh_from_db()

    registrar(
        acao="receita_informada.confirmada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={
            "empresa_id": travada.pk,
            "antes": antes,
            "depois": _snapshot_receita(atual),
        },
    )
    return atual


@transaction.atomic
def estornar_receita_informada(receita: ReceitaInformada, motivo: str, usuario, request=None):
    """Confirmada → estornada, com motivo. Se o mês estava confirmado, reabre-o a retificar."""
    motivo_limpo = _motivo(motivo)
    travada = travar_empresa(receita.empresa)
    atual = ReceitaInformada.objects.select_for_update(of=("self",)).get(
        pk=receita.pk, empresa=travada
    )
    if atual.estado != EstadoReceitaInformada.CONFIRMADA:
        raise ReceitaErro(
            f"Só receita confirmada pode ser estornada; esta está '{atual.get_estado_display()}'."
        )

    antes = _snapshot_receita(atual)
    atualizadas = ReceitaInformada.objects.filter(
        pk=atual.pk, estado=EstadoReceitaInformada.CONFIRMADA
    ).update(
        estado=EstadoReceitaInformada.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario,
        motivo_estorno=motivo_limpo,
    )
    if atualizadas != 1:
        raise ReceitaErro("A receita mudou enquanto era estornada. Atualize a lista.")
    atual.refresh_from_db()

    marcar_a_retificar_por_estorno(
        travada,
        atual.ano,
        atual.mes,
        usuario,
        origem=f"receita informada nº {atual.pk}",
        request=request,
    )
    registrar(
        acao="receita_informada.estornada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={
            "empresa_id": travada.pk,
            "antes": antes,
            "depois": _snapshot_receita(atual),
        },
    )
    return atual


# ---------------------------------------------------------------------------
# Opção pelo regime de caixa (HI-66)
# ---------------------------------------------------------------------------


def _simples_em_algum_dia_do_ano(empresa: Empresa, ano: int) -> bool:
    inicio, fim = date(ano, 1, 1), date(ano, 12, 31)
    return (
        HistoricoRegimeTributario.objects.filter(
            empresa=empresa,
            regime=RegimeTributario.SIMPLES_NACIONAL,
            vigencia_inicio__lte=fim,
        )
        .filter(vigencia_fim__isnull=True)
        .exists()
        or HistoricoRegimeTributario.objects.filter(
            empresa=empresa,
            regime=RegimeTributario.SIMPLES_NACIONAL,
            vigencia_inicio__lte=fim,
            vigencia_fim__gte=inicio,
        ).exists()
    )


@transaction.atomic
def registrar_opcao_regime_caixa(
    empresa: Empresa, ano: int, usuario, request=None
) -> OpcaoRegimeCaixaSimples:
    """Registra que a empresa optou pelo CAIXA no Simples em `ano`.

    Irretratável no ano (Res. CGSN 140, art. 16 § 1º, hipótese HI-66): a segunda
    tentativa é recusada pela restrição única. Anos a partir de 2027 são recusados
    antes de gravar (HI-66). Não há regra de caixa para 2027 sem o texto da Res.
    CGSN 190/2026.
    """
    if isinstance(ano, bool) or not isinstance(ano, int) or not 2000 <= ano <= ANO_ULTIMO_CAIXA:
        raise EntradaInvalidaReceita(
            f"A opção pelo regime de caixa só existe até o PA 12/{ANO_ULTIMO_CAIXA} "
            f"(HI-66): {ano!r} não é aceito. A partir de 2027 a base é a competência."
        )
    travada = travar_empresa(empresa)
    if not _simples_em_algum_dia_do_ano(travada, ano):
        raise ReceitaErro(f"A empresa não tem período do Simples Nacional em {ano}.")

    opcao = OpcaoRegimeCaixaSimples(empresa=travada, ano_calendario=ano, registrada_por=usuario)
    _inserir(
        opcao,
        _RESTRICAO_OPCAO_CAIXA_UNICA,
        f"A opção pelo caixa já foi registrada em {ano}; é irretratável no ano "
        "(Res. CGSN 140, art. 16, § 1º).",
    )
    registrar(
        acao="regime_caixa.optado",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=opcao,
        request=request,
        detalhes={"empresa_id": travada.pk, "ano_calendario": ano},
    )
    return opcao


def opcao_caixa_do_ano(empresa: Empresa, ano: int) -> bool:
    return OpcaoRegimeCaixaSimples.objects.filter(empresa=empresa, ano_calendario=ano).exists()
