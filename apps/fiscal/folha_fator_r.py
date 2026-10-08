"""Folha para o fator r do Simples Nacional — DL-075, frente A (domínio).

NÍVEL 1 (AGENTS.md §3.1): a folha entra no fator r, e o fator r escolhe entre o
Anexo III e o Anexo V. Contrato: docs/planos/DL-075-pre-das-do-simples.md (item 3);
base e hipóteses: HI-69 em docs/projeto/requisitos.md e a consulta do
contador-senior (item 6).

Regras que valem aqui, com a classificação de cada uma:

- Folha = remunerações pagas a pessoas físicas pelo trabalho, com pró-labore e
  autônomos, 13º na competência, mais CPP e FGTS efetivamente recolhidos. Aluguéis
  e lucros ficam FORA (LC 123 art. 18 §§ 24 a 26; Res. CGSN 140 art. 26 § 3º).
  NORMA.
- FS12 = soma da folha dos 12 meses anteriores ao PA. Antes do início de
  atividade, o mês conta como zero e não exige confirmação. No ano de início, a
  mesma janela do RBT12 (art. 22 da Res. CGSN 140, via `rbt12.janela_da_apuracao`)
  dá a média × 12. NORMA (art. 26 § 4º, por remissão ao art. 22).
- Cada mês de folha precisa estar CONFIRMADO. Mês sem folha confirmada bloqueia
  o fator r, e a lista de meses vai para a mensagem. Não se presume folha zero.
- Fator r = FS12 / RBT12 conjunto (interno + externo), TRUNCADO em 2 casas. Esta
  parte fica no `pre_das` (fator_r). Truncar é a regra do Manual do PGDAS-D, item 8.2.1.
- As regras de zero (FS12 = 0 → 0,01; FS12 > 0 e RBT12 = 0 → 0,28) são ROTINA do
  PGDAS-D (Manual, item 8.2.1), não norma. Não são fundamento normativo aqui.

Valores em `Decimal` com 2 casas, sem arredondamento de cálculo. A soma e a divisão
do FS12 usam precisão de 60 dígitos (como o RBT12). Trava: a EMPRESA é travada
primeiro, pela mesma ordem da receita (`receita.travar_empresa`), e o mês
confirmado tem trilha.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa
from apps.fiscal import rbt12 as apuracao
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import EstadoFolhaFatorR, FolhaFatorR

ZERO = Decimal("0.00")
DOCUMENTO_SUPORTE_MAXIMO = 300
MOTIVO_MAXIMO = 500
_PRECISAO_DO_FS12 = 60
_RESTRICAO_FOLHA_UNICA = "folha_mes_unica_ativa_por_empresa"
SITUACAO_SEM_LANCAMENTO = "sem_lancamento"


class FolhaErro(Exception):
    """Conflito de estado: a operação não cabe no estado atual. API: 409."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaFolha(FolhaErro):
    """Entrada fora da regra (valor, competência, texto). API: 400."""


def _mm_aaaa(ano: int, mes: int) -> str:
    return f"{mes:02d}/{ano}"


def _valor_nao_negativo(valor, nome: str) -> Decimal:
    """Componente da folha: decimal >= 0, até 2 casas. Recusa `float` (DE-010)."""
    if isinstance(valor, float):
        raise EntradaInvalidaFolha(f"{nome}: valor em ponto flutuante não é aceito.")
    # A11 (auditoria DL-075): notação científica e não finitos são recusados, como na receita.
    if "e" in str(valor).lower():
        raise EntradaInvalidaFolha(
            f"{nome}: notação científica não é aceita; informe o valor por extenso."
        )
    try:
        decimal = Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise EntradaInvalidaFolha(f"{nome}: valor inválido.") from exc
    if not decimal.is_finite():
        raise EntradaInvalidaFolha(f"{nome}: valor inválido, não é um número finito.")
    if decimal < 0:
        raise EntradaInvalidaFolha(f"{nome}: o valor não pode ser negativo.")
    # Sem normalize(): ele apaga zeros à direita, e "10.000" passaria como 10,00 (mesmo erro
    # corrigido na receita informada, DL-074 R1).
    if decimal.as_tuple().exponent < -2:
        raise EntradaInvalidaFolha(f"{nome}: aceita no máximo duas casas decimais.")
    if decimal >= Decimal("1000000000000000"):
        raise EntradaInvalidaFolha(f"{nome}: excede o limite de 15 dígitos inteiros.")
    return decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _snapshot(folha: FolhaFatorR) -> dict:
    """Trilha da folha: componentes e estado, sem dado pessoal (é agregado da empresa)."""
    return {
        "estado": folha.estado,
        "ano": folha.ano,
        "mes": folha.mes,
        **{nome: str(getattr(folha, nome)) for nome in FolhaFatorR.COMPONENTES},
        "total": str(folha.total),
        "confirmada_em": folha.confirmada_em.isoformat() if folha.confirmada_em else None,
        "estornada_em": folha.estornada_em.isoformat() if folha.estornada_em else None,
        "motivo_estorno": folha.motivo_estorno,
    }


def _inserir(objeto: FolhaFatorR) -> None:
    """INSERT com savepoint. Violação do "um lançamento ativo por mês" vira 409."""
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "__cause__", None), "diag", None)
        if getattr(diag, "constraint_name", None) == _RESTRICAO_FOLHA_UNICA:
            raise FolhaErro(
                "Já existe folha deste mês em rascunho ou confirmada. Confirme ou estorne antes."
            ) from exc
        raise


def folha_ativa(empresa: Empresa, ano: int, mes: int):
    """Lançamento NÃO estornado do mês (rascunho ou confirmada), ou None."""
    return (
        FolhaFatorR.objects.filter(empresa=empresa, ano=ano, mes=mes)
        .exclude(estado=EstadoFolhaFatorR.ESTORNADA)
        .first()
    )


@transaction.atomic
def lancar_folha(
    empresa: Empresa,
    ano: int,
    mes: int,
    componentes: dict,
    documento_suporte: str,
    usuario,
    request=None,
) -> FolhaFatorR:
    """Cria a folha do mês em RASCUNHO. Rascunho não entra no FS12.

    `componentes`: chaves de `FolhaFatorR.COMPONENTES`, valores em texto ou `Decimal`.
    Faltando chave, a recusa nomeia qual. Não há folha "zero por omissão".
    """
    receita_servico.validar_competencia(ano, mes)
    faltando = [nome for nome in FolhaFatorR.COMPONENTES if nome not in componentes]
    if faltando:
        raise EntradaInvalidaFolha(f"Informe os componentes da folha: {', '.join(faltando)}.")
    valores = {
        nome: _valor_nao_negativo(componentes[nome], nome) for nome in FolhaFatorR.COMPONENTES
    }
    suporte = (documento_suporte or "").strip() if isinstance(documento_suporte, str) else ""
    if not suporte:
        raise EntradaInvalidaFolha("Informe o documento de suporte da folha (ex.: GFIP/eSocial).")
    if len(suporte) > DOCUMENTO_SUPORTE_MAXIMO:
        raise EntradaInvalidaFolha(
            f"O documento de suporte tem no máximo {DOCUMENTO_SUPORTE_MAXIMO} caracteres."
        )

    travada = receita_servico.travar_empresa(empresa)
    if folha_ativa(travada, ano, mes) is not None:
        raise FolhaErro(
            f"Já existe folha de {_mm_aaaa(ano, mes)} em rascunho ou confirmada. "
            "Confirme ou estorne antes de lançar outra."
        )
    folha = FolhaFatorR(
        empresa=travada,
        ano=ano,
        mes=mes,
        estado=EstadoFolhaFatorR.RASCUNHO,
        documento_suporte=suporte,
        criado_por=usuario,
        **valores,
    )
    _inserir(folha)
    registrar(
        acao="folha_fator_r.lancada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=folha,
        request=request,
        detalhes={"empresa_id": travada.pk, "depois": _snapshot(folha)},
    )
    return folha


@transaction.atomic
def confirmar_folha(folha: FolhaFatorR, usuario, request=None) -> FolhaFatorR:
    """Rascunho → confirmada. A partir daqui a folha entra no FS12 e não muda mais."""
    travada = receita_servico.travar_empresa(folha.empresa)
    atual = FolhaFatorR.objects.select_for_update(of=("self",)).get(pk=folha.pk, empresa=travada)
    if atual.estado != EstadoFolhaFatorR.RASCUNHO:
        raise FolhaErro(
            f"Só folha em rascunho pode ser confirmada; esta está '{atual.get_estado_display()}'."
        )
    antes = _snapshot(atual)
    atualizadas = FolhaFatorR.objects.filter(pk=atual.pk, estado=EstadoFolhaFatorR.RASCUNHO).update(
        estado=EstadoFolhaFatorR.CONFIRMADA,
        confirmada_em=timezone.now(),
        confirmada_por=usuario,
    )
    if atualizadas != 1:
        raise FolhaErro("A folha mudou enquanto era confirmada. Atualize a lista.")
    atual.refresh_from_db()
    registrar(
        acao="folha_fator_r.confirmada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={"empresa_id": travada.pk, "antes": antes, "depois": _snapshot(atual)},
    )
    return atual


@transaction.atomic
def estornar_folha(folha: FolhaFatorR, motivo: str, usuario, request=None) -> FolhaFatorR:
    """Confirmada → estornada, com motivo. Quem quiser o mês de volta lança outro.

    Não há DAS gravado para retificar: o pré-DAS é recalculado a cada consulta, a
    partir dos lançamentos. O estorno apenas tira o mês do FS12.
    """
    motivo_limpo = (motivo or "").strip() if isinstance(motivo, str) else ""
    if not motivo_limpo:
        raise EntradaInvalidaFolha("Informe o motivo do estorno.")
    if len(motivo_limpo) > MOTIVO_MAXIMO:
        raise EntradaInvalidaFolha(f"O motivo tem no máximo {MOTIVO_MAXIMO} caracteres.")
    travada = receita_servico.travar_empresa(folha.empresa)
    atual = FolhaFatorR.objects.select_for_update(of=("self",)).get(pk=folha.pk, empresa=travada)
    if atual.estado != EstadoFolhaFatorR.CONFIRMADA:
        raise FolhaErro(
            f"Só folha confirmada pode ser estornada; esta está '{atual.get_estado_display()}'."
        )
    antes = _snapshot(atual)
    atualizadas = FolhaFatorR.objects.filter(
        pk=atual.pk, estado=EstadoFolhaFatorR.CONFIRMADA
    ).update(
        estado=EstadoFolhaFatorR.ESTORNADA,
        estornada_em=timezone.now(),
        estornada_por=usuario,
        motivo_estorno=motivo_limpo,
    )
    if atualizadas != 1:
        raise FolhaErro("A folha mudou enquanto era estornada. Atualize a lista.")
    atual.refresh_from_db()
    registrar(
        acao="folha_fator_r.estornada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atual,
        request=request,
        detalhes={"empresa_id": travada.pk, "antes": antes, "depois": _snapshot(atual)},
    )
    return atual


# ---------------------------------------------------------------------------
# FS12 (leitura)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fs12:
    """FS12 do PA. `valor` é None quando algum mês da janela não tem folha confirmada.

    `regra` é a do art. 22 usada (§ 1º a § 4º). `divisor` é o número de meses da média
    (§ 2º a § 4º) ou 12 (§ 1º). `pendentes` lista (ano, mês, situação) de cada mês que
    falta confirmar, para a mensagem do pré-DAS.
    """

    regra: str
    valor: Decimal | None
    divisor: int | None
    pendentes: tuple[tuple[int, int, str], ...]


def _folhas_ativas_do_ano(empresa: Empresa, ano: int) -> dict[tuple[int, int], FolhaFatorR]:
    """Folha NÃO estornada de cada mês de `ano - 1` e `ano`, em uma consulta.

    Cobre toda janela de PA de `ano` (a janela do art. 22 vai até 12 meses antes do PA, e
    o PA mais antigo de `ano` é janeiro). A unicidade do lançamento ativo por mês
    (`folha_mes_unica_ativa_por_empresa`) garante no máximo uma folha por mês.
    """
    folhas = FolhaFatorR.objects.filter(empresa=empresa, ano__in=(ano - 1, ano)).exclude(
        estado=EstadoFolhaFatorR.ESTORNADA
    )
    return {(folha.ano, folha.mes): folha for folha in folhas}


def fs12(empresa: Empresa, ano: int, mes: int) -> Fs12:
    """FS12 do PA pela mesma janela do RBT12 (DL-075, item 3). Recusa como o RBT12."""
    janela = apuracao.janela_da_apuracao(empresa, ano, mes)
    return _fs12_da_janela(janela, _folhas_ativas_do_ano(empresa, ano))


def fs12_do_ano(empresa: Empresa, ano: int) -> dict[int, Fs12 | apuracao.ApuracaoRecusada]:
    """FS12 dos 12 meses de `ano`, em duas consultas fixas (A9 da auditoria DL-075).

    Mesmo resultado de `fs12` mês a mês, mas sem consultar folha nem período por mês. Um
    mês que o RBT12 recusa aparece como `ApuracaoRecusada` (a tela mostra a mensagem).
    """
    periodos = apuracao.periodos_do_simples(empresa)
    folhas = _folhas_ativas_do_ano(empresa, ano)
    resultado: dict[int, Fs12 | apuracao.ApuracaoRecusada] = {}
    for mes in range(1, 13):
        try:
            janela = apuracao.janela_da_apuracao(empresa, ano, mes, periodos=periodos)
        except apuracao.ApuracaoRecusada as exc:
            resultado[mes] = exc
            continue
        resultado[mes] = _fs12_da_janela(janela, folhas)
    return resultado


def _fs12_da_janela(janela, folhas: dict[tuple[int, int], FolhaFatorR]) -> Fs12:
    """FS12 da janela, com as folhas do ano já lidas. Regra única de `fs12` e `fs12_do_ano`."""
    abertura = (janela.abertura.year, janela.abertura.month)
    soma = ZERO
    contados = 0
    pendentes: list[tuple[int, int, str]] = []
    for ano_m, mes_m in janela.meses:
        if (ano_m, mes_m) < abertura:
            # Antes da abertura: zero, sem exigir folha (mesmo critério do RBT12).
            continue
        contados += 1
        lancamento = folhas.get((ano_m, mes_m))
        if lancamento is None or lancamento.estado != EstadoFolhaFatorR.CONFIRMADA:
            situacao = lancamento.estado if lancamento is not None else SITUACAO_SEM_LANCAMENTO
            pendentes.append((ano_m, mes_m, situacao))
            continue
        soma += lancamento.total

    if pendentes:
        return Fs12(regra=janela.regra, valor=None, divisor=None, pendentes=tuple(pendentes))
    if janela.regra == "§ 1º":
        return Fs12(regra=janela.regra, valor=soma, divisor=12, pendentes=())
    # § 2º a § 4º: média dos meses de atividade da janela × 12 (art. 22 §§ 2º a 4º).
    with localcontext() as contexto:
        contexto.prec = _PRECISAO_DO_FS12
        valor = soma * 12 / Decimal(contados)
    return Fs12(regra=janela.regra, valor=valor, divisor=contados, pendentes=())
