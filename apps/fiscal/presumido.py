"""Lucro Presumido, IRPJ e CSLL trimestrais, com o acréscimo da LC 224 — DL-079, frente A (serviço).

NÍVEL 1 (AGENTS.md §3.1): é o imposto que o cliente paga. Este módulo lê o banco, decide as
recusas e grava os atos com trilha. A aritmética fica em `apps.fiscal.presumido_calculo`, sem banco.
Plano: docs/planos/DL-079-lucro-presumido-irpj-csll.md. Fonte normativa:
docs/projeto/consultas/2026-10-08-contador-senior-presumido.md (itens 1 a 12).

Decisões que o código não explica sozinho:

- Receita sujeita à presunção do trimestre (R_t) = NFS-e prestadas EFETIVADAS e não
  canceladas, com `dCompet` no trimestre, pelo valor do serviço menos o desconto incondicional
  lido do XML guardado (`vDescCondIncond/vDescIncond`: XSD 1.01, linha 1679; 1.00, linha 1285);
  mais as receitas
  `presuncao` ativas. Quais escriturações contam vem de `receita._escrituracoes_efetivadas_do_mes`,
  a fonte única do filtro. Rascunho, estornada e cancelada não entram.
- Nota sem desconto no XML é desconto ZERO. Desconto presente mas fora do formato é recusa
  (`nota_xml_invalido`): não se presume nem zero nem o valor da nota.
- Atividade da nota: a padrão vigente na `dCompet`. Receita informada nomeia a atividade, que
  precisa estar vigente em algum dia do trimestre.
- Retenção PROPOSTA por nota (IRRF = `vRetIRRF`; CSLL conforme `tpRetPisCofins`). Só entra na
  apuração a CONFIRMAÇÃO ativa do contador, com trilha (HI-102, HI-103).
- Trimestre sem regime de Lucro Presumido em qualquer dia, ou com mudança de regime dentro
  dele, é recusado com código nomeado.
- Anos anteriores a 2026 não são apurados aqui: a LC 224 não existe neles.
- Encerramento de atividade da empresa não tem data no cadastro: o 4º trimestre é sempre o
  fechamento do ano. Início de atividade é a `data_abertura_cnpj` (HI-107; consulta, item 4).
- Meses do adicional no trimestre de abertura: conta-se o MÊS CALENDÁRIO tocado pela atividade
  (o mês da abertura inteiro). É HIPÓTESE: o texto lido não diz como tratar fração de mês.
- A situação só é `completa` sem recusas e com a declaração de receitas integrais válida (HI-104).
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditoria.services import registrar
from apps.empresas.models import Empresa, HistoricoRegimeTributario, RegimeTributario
from apps.fiscal import presumido_calculo as calc
from apps.fiscal import presumido_tabelas as tab
from apps.fiscal import receita as receita_servico
from apps.fiscal.models import (
    AtividadePresuncaoEmpresa,
    ConfirmacaoRetencaoPresumido,
    CriterioReceitaPresumido,
    DeclaracaoReceitasIntegrais,
    EscrituracaoFiscal,
    EstadoEscrituracao,
    MedidaJudicialLC224,
    ReceitaTrimestralPresumido,
)
from apps.fiscal.services import situacao_do_documento
from apps.fiscal.tomadas import TP_RET_PIS_COFINS_COM_RETENCAO
from apps.fiscal.tomadas_campos import campos_tomada_do_documento

ZERO = Decimal("0.00")
ANO_MAXIMO = 2999
TRIMESTRES = (1, 2, 3, 4)
CRITERIO_COMPETENCIA = "competencia"
CRITERIO_CAIXA = "caixa"
TIPO_PRESUNCAO = "presuncao"
TIPO_INTEGRAL = "integral"
ESTADO_ATIVA = "ativa"
ESTADO_ESTORNADA = "estornada"
ESTADO_RETENCAO_ATIVA = "ativa"
ESTADO_RETENCAO_SUBSTITUIDA = "substituida"
TP_CSLL_EXATA = "8"
TP_CSLL_ESTIMADA = "3"
MOTIVO_MAXIMO = 500
TEXTO_CURTO_MAXIMO = 300
# Valor com dígitos ASCII, sinal opcional e até duas casas. Mesmo cuidado de DL-075 (R5): o texto
# é validado ANTES do Decimal, que aceitaria "1_000" e dígitos Unicode.
FORMATO_VALOR = re.compile(r"-?[0-9]+(?:\.[0-9]{1,2})?")


# ---------------------------------------------------------------------------
# Erros nomeados. A API traduz EntradaInvalidaPresumido em 400, NaoEncontradoPresumido em 404 e
# PresumidoConflito em 409. Nenhum deles deixa exceção genérica escapar.
# ---------------------------------------------------------------------------


class PresumidoErro(Exception):
    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


class EntradaInvalidaPresumido(PresumidoErro):
    pass


class NaoEncontradoPresumido(PresumidoErro):
    pass


class PresumidoConflito(PresumidoErro):
    pass


# ---------------------------------------------------------------------------
# Recusas e leitura de datas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Recusa:
    """Motivo nomeado pelo qual a apuração não sai. `itens` lista notas ou receitas."""

    codigo: str
    mensagem: str
    itens: tuple[str, ...] = ()


def inicio_e_fim_do_trimestre(ano: int, trimestre: int) -> tuple[date, date]:
    mes_inicial = (trimestre - 1) * 3 + 1
    mes_final = mes_inicial + 2
    ultimo_dia = calendar.monthrange(ano, mes_final)[1]
    return date(ano, mes_inicial, 1), date(ano, mes_final, ultimo_dia)


def _meses_do_trimestre(trimestre: int) -> list[int]:
    mes_inicial = (trimestre - 1) * 3 + 1
    return [mes_inicial, mes_inicial + 1, mes_inicial + 2]


def validar_ano_e_trimestre(ano, trimestre) -> None:
    """Ano e trimestre válidos para o presumido: 2026 a 2999 e trimestre de 1 a 4."""
    if not isinstance(ano, int) or isinstance(ano, bool):
        raise EntradaInvalidaPresumido("Informe o ano como número inteiro.")
    if not (tab.ANO_INICIAL_LC224 <= ano <= ANO_MAXIMO):
        raise EntradaInvalidaPresumido(
            f"Ano fora da regra: o acréscimo da LC 224 vale de {tab.ANO_INICIAL_LC224} "
            f"a {ANO_MAXIMO}."
        )
    if not isinstance(trimestre, int) or isinstance(trimestre, bool) or trimestre not in TRIMESTRES:
        raise EntradaInvalidaPresumido("Trimestre inválido: use 1, 2, 3 ou 4.")


def _valor_decimal(valor, nome: str) -> Decimal:
    """Valor monetário vindo de texto ou de Decimal. Float é recusado (HI-100, nunca binário)."""
    if isinstance(valor, bool) or valor is None:
        raise EntradaInvalidaPresumido(f"Informe {nome}.")
    if isinstance(valor, float):
        raise EntradaInvalidaPresumido(f"{nome}: valor em ponto flutuante não é aceito.")
    if isinstance(valor, Decimal):
        decimal = valor
    else:
        texto = str(valor).strip()
        if not FORMATO_VALOR.fullmatch(texto):
            raise EntradaInvalidaPresumido(f"{nome}: use número com até duas casas decimais.")
        try:
            decimal = Decimal(texto)
        except InvalidOperation as exc:
            raise EntradaInvalidaPresumido(f"{nome}: valor inválido.") from exc
    if not decimal.is_finite():
        raise EntradaInvalidaPresumido(f"{nome}: valor inválido.")
    if decimal != decimal.quantize(calc.CENTAVO):
        raise EntradaInvalidaPresumido(f"{nome}: use no máximo duas casas decimais.")
    return decimal


def _texto(valor, nome: str, maximo: int, obrigatorio: bool = True) -> str:
    texto = "" if valor is None else str(valor).strip()
    if obrigatorio and not texto:
        raise EntradaInvalidaPresumido(f"Informe {nome}.")
    if len(texto) > maximo:
        raise EntradaInvalidaPresumido(f"{nome}: máximo de {maximo} caracteres.")
    return texto


def _data(valor, nome: str) -> date:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except (TypeError, ValueError) as exc:
        raise EntradaInvalidaPresumido(f"{nome}: use a data no formato AAAA-MM-DD.") from exc


# ---------------------------------------------------------------------------
# Regime tributário e abertura (HistoricoRegimeTributario; data_abertura_cnpj)
# ---------------------------------------------------------------------------


def _regimes_do_trimestre(empresa: Empresa, inicio: date, fim: date) -> set[str | None]:
    """Regime de cada dia do trimestre, pelo histórico. None = dia sem período cobrindo."""
    periodos = list(
        HistoricoRegimeTributario.objects.filter(empresa=empresa, vigencia_inicio__lte=fim).filter(
            Q(vigencia_fim__isnull=True) | Q(vigencia_fim__gte=inicio)
        )
    )
    regimes: set[str | None] = set()
    dia = inicio
    while dia <= fim:
        cobrindo = [
            p
            for p in periodos
            if p.vigencia_inicio <= dia and (p.vigencia_fim is None or p.vigencia_fim >= dia)
        ]
        cobrindo.sort(key=lambda p: (p.vigencia_inicio, p.id), reverse=True)
        regimes.add(cobrindo[0].regime if cobrindo else None)
        dia += timedelta(days=1)
    return regimes


def _recusa_de_regime(empresa: Empresa, ano: int, trimestre: int) -> Recusa | None:
    inicio, fim = inicio_e_fim_do_trimestre(ano, trimestre)
    regimes = _regimes_do_trimestre(empresa, inicio, fim)
    rotulo = f"{trimestre}º trimestre de {ano}"
    if regimes == {RegimeTributario.LUCRO_PRESUMIDO}:
        return None
    if None in regimes:
        return Recusa(
            "regime_nao_informado",
            f"Sem regime tributário cadastrado em algum dia do {rotulo}.",
        )
    if len(regimes) > 1:
        return Recusa(
            "regime_muda_no_trimestre",
            f"Houve mudança de regime tributário dentro do {rotulo}: a apuração não cobre "
            "o trimestre.",
        )
    return Recusa(
        "regime_diferente",
        f"O regime do {rotulo} não é Lucro Presumido.",
    )


def _meses_em_atividade(empresa: Empresa, ano: int, trimestre: int) -> tuple[bool, int]:
    """(em atividade no trimestre, meses em atividade). Abertura no meio do trimestre conta o mês
    calendário tocado (HIPÓTESE, ver o módulo)."""
    inicio, fim = inicio_e_fim_do_trimestre(ano, trimestre)
    abertura = empresa.data_abertura_cnpj
    if abertura is None or abertura <= inicio:
        return True, 3
    if abertura > fim:
        return False, 0
    ultimo_mes = fim.month
    return True, ultimo_mes - abertura.month + 1


# ---------------------------------------------------------------------------
# Atividade de presunção: vigência e padrão
# ---------------------------------------------------------------------------


def _vigente_no_dia(atividade: AtividadePresuncaoEmpresa, dia: date) -> bool:
    return atividade.inicio <= dia and (atividade.fim is None or atividade.fim >= dia)


def _vigente_no_trimestre(atividade: AtividadePresuncaoEmpresa, ano: int, trimestre: int) -> bool:
    inicio, fim = inicio_e_fim_do_trimestre(ano, trimestre)
    return atividade.inicio <= fim and (atividade.fim is None or atividade.fim >= inicio)


def _padrao_do_dia(padroes: list[AtividadePresuncaoEmpresa], dia: date):
    """A padrão vigente num dia (no máximo uma, o serviço recusa sobreposição)."""
    vigentes = [p for p in padroes if _vigente_no_dia(p, dia)]
    if not vigentes:
        return None
    vigentes.sort(key=lambda p: (p.inicio, p.id), reverse=True)
    return vigentes[0]


def _sobrepoe(a_inicio: date, a_fim: date | None, b: AtividadePresuncaoEmpresa) -> bool:
    b_fim = b.fim
    return a_inicio <= (b_fim or date.max) and (a_fim is None or b.inicio <= a_fim)


def _padroes_sobrepostos(empresa, inicio: date, fim: date | None, excluir_pk=None):
    padroes = AtividadePresuncaoEmpresa.objects.filter(empresa=empresa, padrao=True)
    if excluir_pk is not None:
        padroes = padroes.exclude(pk=excluir_pk)
    return [p for p in padroes if _sobrepoe(inicio, fim, p)]


def _validar_atividade(dados: dict) -> dict:
    codigo = _texto(dados.get("atividade"), "a atividade de presunção", 40)
    if codigo not in tab.ATIVIDADES_POR_CODIGO:
        raise EntradaInvalidaPresumido(f"Atividade de presunção fora do catálogo: {codigo!r}.")
    inicio = _data(dados.get("inicio"), "o início da vigência")
    fim_bruto = dados.get("fim")
    fim = None if fim_bruto in (None, "") else _data(fim_bruto, "o fim da vigência")
    if fim is not None and fim < inicio:
        raise EntradaInvalidaPresumido("O fim da vigência não pode ser anterior ao início.")
    padrao = dados.get("padrao", False)
    requisitos = dados.get("requisitos_hospitalares_confirmados", False)
    if not isinstance(padrao, bool) or not isinstance(requisitos, bool):
        raise EntradaInvalidaPresumido(
            "'padrao' e 'requisitos_hospitalares_confirmados' são true ou false."
        )
    if codigo == tab.SERVICOS_HOSPITALARES and not requisitos:
        raise EntradaInvalidaPresumido(
            "Serviço hospitalar só vale com os dois requisitos legais confirmados pelo contador "
            "(Lei 9.249, art. 15, § 1º, III, 'a')."
        )
    return {
        "atividade": codigo,
        "inicio": inicio,
        "fim": fim,
        "padrao": padrao,
        "requisitos_hospitalares_confirmados": requisitos,
    }


def _inserir(objeto, restricao: str, mensagem: str) -> None:
    """INSERT com savepoint: violação de restrição única vira conflito (409), nunca 500 (mesmo molde
    de `receita._inserir`)."""
    try:
        with transaction.atomic():
            objeto.save()
    except IntegrityError as exc:
        diag = getattr(getattr(exc, "__cause__", None), "diag", None)
        if getattr(diag, "constraint_name", None) == restricao:
            raise PresumidoConflito(mensagem) from exc
        raise


@transaction.atomic
def criar_atividade(
    empresa: Empresa, dados: dict, usuario, request=None
) -> AtividadePresuncaoEmpresa:
    """Cadastra uma atividade de presunção. Padrão não pode sobrepor outra padrão (HI-101)."""
    valores = _validar_atividade(dados)
    travada = receita_servico.travar_empresa(empresa)
    if valores["padrao"] and _padroes_sobrepostos(travada, valores["inicio"], valores["fim"]):
        raise PresumidoConflito(
            "Já há atividade padrão com vigência sobreposta. A padrão é uma por vez."
        )
    atividade = AtividadePresuncaoEmpresa(empresa=travada, criada_por=usuario, **valores)
    _inserir(
        atividade,
        "presumido_padrao_unica_em_aberto",
        "Já há uma atividade padrão em aberto. Encerre a vigência dela antes.",
    )
    registrar(
        acao="presumido.atividade_criada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atividade,
        request=request,
        detalhes={"atividade": valores["atividade"], "padrao": valores["padrao"]},
    )
    return atividade


@transaction.atomic
def encerrar_atividade(empresa: Empresa, atividade_id: int, fim, usuario, request=None):
    """Encerra a vigência de uma atividade. Só o fim muda; a linha continua na trilha."""
    travada = receita_servico.travar_empresa(empresa)
    atividade = (
        AtividadePresuncaoEmpresa.objects.select_for_update(of=("self",))
        .filter(pk=atividade_id, empresa=travada)
        .first()
    )
    if atividade is None:
        raise NaoEncontradoPresumido("Atividade de presunção não encontrada nesta empresa.")
    if atividade.fim is not None:
        raise PresumidoConflito("Esta atividade já tem fim de vigência.")
    fim_data = _data(fim, "o fim da vigência")
    if fim_data < atividade.inicio:
        raise EntradaInvalidaPresumido("O fim da vigência não pode ser anterior ao início.")
    antes = {"fim": None}
    atividade.fim = fim_data
    atividade.save(update_fields=["fim"])
    registrar(
        acao="presumido.atividade_encerrada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=atividade,
        request=request,
        detalhes={"antes": antes, "depois": {"fim": fim_data.isoformat()}},
    )
    return atividade


def listar_atividades(empresa: Empresa):
    return AtividadePresuncaoEmpresa.objects.filter(empresa=empresa).order_by("inicio", "id")


# ---------------------------------------------------------------------------
# Critério de receita do ano (IN 1.700, art. 223: caixa é recusado)
# ---------------------------------------------------------------------------


@transaction.atomic
def definir_criterio(empresa: Empresa, ano: int, criterio: str, usuario, request=None):
    """Define o critério do ano uma vez. Repetir o mesmo valor é idempotente; trocar é conflito."""
    validar_ano_e_trimestre(ano, 1)
    if criterio not in (CRITERIO_COMPETENCIA, CRITERIO_CAIXA):
        raise EntradaInvalidaPresumido("Critério fora do catálogo: use 'competencia' ou 'caixa'.")
    travada = receita_servico.travar_empresa(empresa)
    existente = CriterioReceitaPresumido.objects.filter(empresa=travada, ano=ano).first()
    if existente is not None:
        if existente.criterio == criterio:
            return existente, False
        raise PresumidoConflito(
            f"O critério de {ano} já foi definido como '{existente.criterio}'. "
            "Não se troca depois de definido."
        )
    criterio_obj = CriterioReceitaPresumido(
        empresa=travada, ano=ano, criterio=criterio, criado_por=usuario
    )
    _inserir(
        criterio_obj,
        "presumido_criterio_unico_por_ano",
        "O critério deste ano já foi definido.",
    )
    registrar(
        acao="presumido.criterio_definido",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=criterio_obj,
        request=request,
        detalhes={"ano": ano, "criterio": criterio},
    )
    return criterio_obj, True


def criterio_do_ano(empresa: Empresa, ano: int) -> str | None:
    registro = CriterioReceitaPresumido.objects.filter(empresa=empresa, ano=ano).first()
    return registro.criterio if registro is not None else None


# ---------------------------------------------------------------------------
# Receita informada do trimestre (presunção com atividade, ou integral)
# ---------------------------------------------------------------------------


@transaction.atomic
def criar_receita(empresa: Empresa, ano: int, trimestre: int, dados: dict, usuario, request=None):
    validar_ano_e_trimestre(ano, trimestre)
    tipo = dados.get("tipo")
    if tipo not in (TIPO_PRESUNCAO, TIPO_INTEGRAL):
        raise EntradaInvalidaPresumido("Tipo de receita: use 'presuncao' ou 'integral'.")
    valor = _valor_decimal(dados.get("valor"), "o valor")
    if valor <= 0:
        raise EntradaInvalidaPresumido("O valor da receita precisa ser positivo.")
    descricao = _texto(dados.get("descricao"), "a descrição", TEXTO_CURTO_MAXIMO)
    suporte = _texto(dados.get("suporte"), "o documento de suporte", TEXTO_CURTO_MAXIMO)
    atividade = None
    if tipo == TIPO_PRESUNCAO:
        atividade_id = dados.get("atividade_id")
        if atividade_id is None:
            raise EntradaInvalidaPresumido("Receita de presunção exige a atividade de presunção.")
        atividade = AtividadePresuncaoEmpresa.objects.filter(
            pk=atividade_id, empresa=empresa
        ).first()
        if atividade is None:
            raise EntradaInvalidaPresumido("Atividade de presunção não encontrada nesta empresa.")
        if not _vigente_no_trimestre(atividade, ano, trimestre):
            raise EntradaInvalidaPresumido(
                "A atividade de presunção não está vigente em nenhum dia do trimestre."
            )
    elif dados.get("atividade_id") is not None:
        raise EntradaInvalidaPresumido("Receita integral não leva atividade de presunção.")

    travada = receita_servico.travar_empresa(empresa)
    receita = ReceitaTrimestralPresumido(
        empresa=travada,
        ano=ano,
        trimestre=trimestre,
        tipo=tipo,
        atividade=atividade,
        descricao=descricao,
        valor=valor,
        suporte=suporte,
        estado=ESTADO_ATIVA,
        criada_por=usuario,
    )
    receita.save()
    registrar(
        acao="presumido.receita_criada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=receita,
        request=request,
        detalhes={"ano": ano, "trimestre": trimestre, "tipo": tipo, "valor": str(valor)},
    )
    return receita


@transaction.atomic
def estornar_receita(empresa: Empresa, receita_id: int, motivo, usuario, request=None):
    """Estorno: a única mudança depois de criada (gatilho do banco). Com motivo obrigatório."""
    motivo_limpo = _texto(motivo, "o motivo do estorno", MOTIVO_MAXIMO)
    travada = receita_servico.travar_empresa(empresa)
    receita = (
        ReceitaTrimestralPresumido.objects.select_for_update(of=("self",))
        .filter(pk=receita_id, empresa=travada)
        .first()
    )
    if receita is None:
        raise NaoEncontradoPresumido("Receita não encontrada nesta empresa.")
    if receita.estado != ESTADO_ATIVA:
        raise PresumidoConflito("Esta receita já está estornada.")
    agora = timezone.now()
    ReceitaTrimestralPresumido.objects.filter(pk=receita.pk, estado=ESTADO_ATIVA).update(
        estado=ESTADO_ESTORNADA,
        motivo_estorno=motivo_limpo,
        estornada_em=agora,
        estornada_por=usuario,
    )
    receita.refresh_from_db()
    registrar(
        acao="presumido.receita_estornada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=receita,
        request=request,
        detalhes={"antes": {"estado": ESTADO_ATIVA}, "depois": {"estado": ESTADO_ESTORNADA}},
    )
    return receita


def listar_receitas(empresa: Empresa, ano: int, trimestre: int):
    return ReceitaTrimestralPresumido.objects.filter(
        empresa=empresa, ano=ano, trimestre=trimestre
    ).order_by("id")


def _integrais_ativas(empresa: Empresa, ano: int, trimestre: int) -> Decimal:
    total = ReceitaTrimestralPresumido.objects.filter(
        empresa=empresa,
        ano=ano,
        trimestre=trimestre,
        tipo=TIPO_INTEGRAL,
        estado=ESTADO_ATIVA,
    ).values_list("valor", flat=True)
    return sum((v for v in total), ZERO)


@transaction.atomic
def declarar_receitas_integrais(
    empresa: Empresa, ano: int, trimestre: int, observacao, usuario, request=None
):
    """Declara as integrais do trimestre com o TOTAL atual como snapshot (HI-104)."""
    validar_ano_e_trimestre(ano, trimestre)
    observacao_limpa = _texto(observacao, "a observação", MOTIVO_MAXIMO, obrigatorio=False)
    travada = receita_servico.travar_empresa(empresa)
    total = _integrais_ativas(travada, ano, trimestre)
    declaracao = DeclaracaoReceitasIntegrais(
        empresa=travada,
        ano=ano,
        trimestre=trimestre,
        total=total,
        observacao=observacao_limpa,
        declarada_por=usuario,
    )
    declaracao.save()
    registrar(
        acao="presumido.integrais_declaradas",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=declaracao,
        request=request,
        detalhes={"ano": ano, "trimestre": trimestre, "total": str(total)},
    )
    return declaracao


def _declaracao_valida(empresa: Empresa, ano: int, trimestre: int):
    """(declaração mais recente ou None, válida?). Válida = o total atual ainda é o snapshot."""
    declaracao = (
        DeclaracaoReceitasIntegrais.objects.filter(empresa=empresa, ano=ano, trimestre=trimestre)
        .order_by("-declarada_em", "-id")
        .first()
    )
    if declaracao is None:
        return None, False
    return declaracao, declaracao.total == _integrais_ativas(empresa, ano, trimestre)


# ---------------------------------------------------------------------------
# Notas: leitura, atividade, desconto e retenção proposta
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RetencaoProposta:
    irrf: Decimal | None
    csll: Decimal | None
    csll_situacao: str
    csll_motivo: str


def proposta_de_retencao(campos) -> RetencaoProposta:
    """Retenção proposta de UMA nota (HI-102, HI-103). Ausente é ausente: nunca vira zero.

    CSLL: `tpRetPisCofins` 8 é exata (`vRetCSLL`); 3 é estimada por `vRetCSLL / 4,65`. Código
    ambíguo, outros códigos, `vPis`/`vCofins` junto com código de retenção, ou `vRetCSLL` ausente:
    "a classificar", sem valor.
    """
    irrf = campos.v_ret_irrf
    tp = campos.tp_ret_pis_cofins
    ambiguo = (campos.v_pis is not None or campos.v_cofins is not None) and (
        tp in TP_RET_PIS_COFINS_COM_RETENCAO
    )
    if campos.v_ret_csll is None:
        return RetencaoProposta(irrf, None, "a_classificar", "vRetCSLL ausente na nota")
    if ambiguo:
        return RetencaoProposta(
            irrf,
            None,
            "a_classificar",
            "vPis/vCofins preenchidos junto com código de retenção: ambíguo",
        )
    if tp == TP_CSLL_EXATA:
        return RetencaoProposta(irrf, campos.v_ret_csll, "exata", "")
    if tp == TP_CSLL_ESTIMADA:
        estimada = calc.centavos(campos.v_ret_csll / tab.FATOR_ESTIMATIVA_CSLL_TP3)
        return RetencaoProposta(
            irrf,
            estimada,
            "estimada",
            "estimada — conferir no comprovante de retenção",
        )
    motivo = (
        "tpRetPisCofins ausente na nota"
        if tp is None
        else f"tpRetPisCofins {tp}: sem regra confirmada"
    )
    return RetencaoProposta(irrf, None, "a_classificar", motivo)


@dataclass(frozen=True)
class NotaApurada:
    escrituracao_id: int
    numero: str
    identificador: str
    data_competencia: date
    valor_servico: Decimal
    desconto_incondicionado: Decimal
    base: Decimal
    atividade: str
    retencao: RetencaoProposta


@dataclass(frozen=True)
class ReceitaApurada:
    receita_id: int
    atividade: str
    valor: Decimal


@dataclass(frozen=True)
class DadosDoTrimestre:
    """O que o banco diz de UM trimestre, já com as recusas que ele gera."""

    trimestre: int
    inicio: date
    fim: date
    em_atividade: bool
    meses: int
    notas: tuple[NotaApurada, ...]
    receitas: tuple[ReceitaApurada, ...]
    integrais: Decimal
    recusas: tuple[Recusa, ...]


def _ler_nota(
    escrituracao: EscrituracaoFiscal, padroes
) -> tuple[NotaApurada | None, Recusa | None]:
    documento = escrituracao.vinculo.documento
    campos = campos_tomada_do_documento(documento)
    rotulo = documento.numero or documento.identificador
    if campos.erro_leitura is not None or any("vDescIncond" in c for c in campos.invalidos):
        return None, Recusa(
            "nota_xml_invalido",
            "O XML guardado desta nota tem o desconto incondicional fora do formato. "
            "A nota não entra até a leitura ser corrigida.",
            (rotulo,),
        )
    desconto = campos.v_desc_incond if campos.v_desc_incond is not None else ZERO
    valor = escrituracao.valor_servico
    if desconto > valor:
        return None, Recusa(
            "desconto_maior_que_servico",
            "O desconto incondicional da nota é maior que o valor do serviço.",
            (rotulo,),
        )
    padrao = _padrao_do_dia(padroes, escrituracao.data_competencia)
    if padrao is None:
        return None, Recusa(
            "nota_sem_atividade",
            "Nota sem atividade de presunção vigente na competência.",
            (rotulo,),
        )
    nota = NotaApurada(
        escrituracao_id=escrituracao.pk,
        numero=documento.numero,
        identificador=documento.identificador,
        data_competencia=escrituracao.data_competencia,
        valor_servico=valor,
        desconto_incondicionado=desconto,
        base=valor - desconto,
        atividade=padrao.atividade,
        retencao=proposta_de_retencao(campos),
    )
    return nota, None


def _escrituracoes_que_contam(
    empresa: Empresa, ano: int, trimestre: int
) -> list[EscrituracaoFiscal]:
    """NFS-e prestadas EFETIVADAS e não canceladas, com dCompet no trimestre.

    O filtro de documento é o de `receita._escrituracoes_efetivadas_do_mes` (fonte única).
    """
    contam = []
    for mes in _meses_do_trimestre(trimestre):
        for escrituracao in receita_servico._escrituracoes_efetivadas_do_mes(
            empresa, ano, mes
        ).select_related("vinculo__documento"):
            if situacao_do_documento(escrituracao.vinculo.documento) == "cancelada":
                continue
            contam.append(escrituracao)
    return contam


def _carregar_trimestre(empresa: Empresa, ano: int, trimestre: int, padroes) -> DadosDoTrimestre:
    inicio, fim = inicio_e_fim_do_trimestre(ano, trimestre)
    em_atividade, meses = _meses_em_atividade(empresa, ano, trimestre)
    if not em_atividade:
        # Trimestre anterior à abertura: não há regime a conferir nem nota. A recusa
        # "antes da abertura" é do trimestre PEDIDO, em `apurar_trimestre`; um trimestre anterior
        # só entra no cálculo como zero, e não pode bloquear os seguintes.
        return DadosDoTrimestre(
            trimestre=trimestre,
            inicio=inicio,
            fim=fim,
            em_atividade=False,
            meses=0,
            notas=(),
            receitas=(),
            integrais=ZERO,
            recusas=(),
        )
    recusas: list[Recusa] = []
    regime = _recusa_de_regime(empresa, ano, trimestre)
    if regime is not None:
        recusas.append(regime)
    notas: list[NotaApurada] = []
    for escrituracao in _escrituracoes_que_contam(empresa, ano, trimestre):
        nota, recusa = _ler_nota(escrituracao, padroes)
        if recusa is not None:
            recusas.append(recusa)
        else:
            notas.append(nota)
    receitas: list[ReceitaApurada] = []
    sem_vigencia: list[str] = []
    integrais = ZERO
    for receita in (
        ReceitaTrimestralPresumido.objects.filter(
            empresa=empresa, ano=ano, trimestre=trimestre, estado=ESTADO_ATIVA
        )
        .select_related("atividade")
        .order_by("id")
    ):
        if receita.tipo == TIPO_INTEGRAL:
            integrais += receita.valor
        elif _vigente_no_trimestre(receita.atividade, ano, trimestre):
            receitas.append(ReceitaApurada(receita.pk, receita.atividade.atividade, receita.valor))
        else:
            sem_vigencia.append(f"receita {receita.pk}")
    if sem_vigencia:
        recusas.append(
            Recusa(
                "receita_sem_atividade_vigente",
                "Receita informada cuja atividade de presunção não está vigente no trimestre.",
                tuple(sem_vigencia),
            )
        )
    return DadosDoTrimestre(
        trimestre=trimestre,
        inicio=inicio,
        fim=fim,
        em_atividade=em_atividade,
        meses=meses,
        notas=tuple(notas),
        receitas=tuple(receitas),
        integrais=integrais,
        recusas=tuple(recusas),
    )


def _receitas_por_atividade(dados: DadosDoTrimestre) -> tuple[tuple[str, Decimal], ...]:
    """R_t,i por atividade, na ordem do catálogo (a última recebe o resíduo do rateio)."""
    somas: dict[str, Decimal] = {}
    for nota in dados.notas:
        somas[nota.atividade] = somas.get(nota.atividade, ZERO) + nota.base
    for receita in dados.receitas:
        somas[receita.atividade] = somas.get(receita.atividade, ZERO) + receita.valor
    return tuple((codigo, somas[codigo]) for codigo in tab.CODIGOS_DE_ATIVIDADE if codigo in somas)


def _periodo(dados: DadosDoTrimestre) -> calc.PeriodoTrimestre:
    return calc.PeriodoTrimestre(
        trimestre=dados.trimestre,
        receitas=_receitas_por_atividade(dados),
        integrais=dados.integrais,
        meses=dados.meses,
        em_atividade=dados.em_atividade,
    )


def _periodos_do_ano(
    empresa: Empresa, ano: int, ate: int
) -> tuple[list[calc.PeriodoTrimestre], list[Recusa], dict[int, DadosDoTrimestre]]:
    """Os quatro períodos do ano para o cálculo. Trimestres depois de `ate` entram zerados: o
    limite é recursivo para a frente, então os anteriores não dependem deles. Só o 4º
    (fechamento) precisa de todos os dados reais."""
    padroes = list(AtividadePresuncaoEmpresa.objects.filter(empresa=empresa, padrao=True))
    carregados: dict[int, DadosDoTrimestre] = {}
    periodos = []
    recusas: list[Recusa] = []
    for trimestre in TRIMESTRES:
        if trimestre <= ate:
            dados = _carregar_trimestre(empresa, ano, trimestre, padroes)
            carregados[trimestre] = dados
            recusas.extend(dados.recusas)
            periodos.append(_periodo(dados))
        else:
            em_atividade, meses = _meses_em_atividade(empresa, ano, trimestre)
            periodos.append(calc.PeriodoTrimestre(trimestre, (), ZERO, meses, em_atividade))
    return periodos, recusas, carregados


# ---------------------------------------------------------------------------
# Confirmação de retenção: única fonte de dedução
# ---------------------------------------------------------------------------


def _confirmacoes_ativas(
    empresa: Empresa, escrituracao_ids
) -> dict[int, ConfirmacaoRetencaoPresumido]:
    confirmacoes = ConfirmacaoRetencaoPresumido.objects.filter(
        escrituracao__empresa=empresa,
        escrituracao_id__in=list(escrituracao_ids),
        estado=ESTADO_RETENCAO_ATIVA,
    )
    return {c.escrituracao_id: c for c in confirmacoes}


def _retencoes_confirmadas(empresa: Empresa, dados: DadosDoTrimestre) -> tuple[Decimal, Decimal]:
    """(IRRF confirmado, CSLL confirmada) das notas que ENTRAM na base do trimestre."""
    ids = [n.escrituracao_id for n in dados.notas]
    confirmacoes = _confirmacoes_ativas(empresa, ids)
    irrf = ZERO
    csll = ZERO
    for escrituracao_id in ids:
        confirmacao = confirmacoes.get(escrituracao_id)
        if confirmacao is None:
            continue
        if confirmacao.irrf_confirmado is not None:
            irrf += confirmacao.irrf_confirmado
        if confirmacao.csll_confirmada is not None:
            csll += confirmacao.csll_confirmada
    return irrf, csll


@transaction.atomic
def confirmar_retencao(
    empresa: Empresa,
    escrituracao_id: int,
    irrf_confirmado,
    csll_confirmada,
    motivo,
    usuario,
    request=None,
) -> ConfirmacaoRetencaoPresumido:
    """Confirma a retenção de UMA nota prestada da empresa (trilha; substitui a ativa anterior)."""
    irrf = (
        None
        if irrf_confirmado in (None, "")
        else _valor_decimal(irrf_confirmado, "o IRRF confirmado")
    )
    csll = (
        None
        if csll_confirmada in (None, "")
        else _valor_decimal(csll_confirmada, "a CSLL confirmada")
    )
    if irrf is None and csll is None:
        raise EntradaInvalidaPresumido("Informe o IRRF ou a CSLL confirmada.")
    if (irrf is not None and irrf < 0) or (csll is not None and csll < 0):
        raise EntradaInvalidaPresumido("A retenção confirmada não pode ser negativa.")
    travada = receita_servico.travar_empresa(empresa)
    escrituracao = (
        EscrituracaoFiscal.objects.select_for_update(of=("self",))
        .filter(pk=escrituracao_id, empresa=travada)
        .first()
    )
    if escrituracao is None:
        raise NaoEncontradoPresumido("Escrituração não encontrada nesta empresa.")
    if escrituracao.estado != EstadoEscrituracao.EFETIVADA:
        raise PresumidoConflito("A retenção só se confirma em nota efetivada.")
    if situacao_do_documento(escrituracao.vinculo.documento) == "cancelada":
        raise PresumidoConflito(
            "Nota cancelada não entra na apuração: não há retenção a confirmar."
        )

    campos = campos_tomada_do_documento(escrituracao.vinculo.documento)
    proposta = proposta_de_retencao(campos)
    difere = (irrf is not None and irrf != campos.v_ret_irrf) or (
        csll is not None and csll != proposta.csll
    )
    motivo_limpo = _texto(motivo, "o motivo", MOTIVO_MAXIMO, obrigatorio=False)
    if difere and not motivo_limpo:
        raise EntradaInvalidaPresumido("O valor confirmado difere do proposto: informe o motivo.")

    anterior = (
        ConfirmacaoRetencaoPresumido.objects.select_for_update(of=("self",))
        .filter(escrituracao=escrituracao, estado=ESTADO_RETENCAO_ATIVA)
        .first()
    )
    antes = None
    if anterior is not None:
        antes = {
            "irrf_confirmado": _texto_valor(anterior.irrf_confirmado),
            "csll_confirmada": _texto_valor(anterior.csll_confirmada),
        }
        ConfirmacaoRetencaoPresumido.objects.filter(
            pk=anterior.pk, estado=ESTADO_RETENCAO_ATIVA
        ).update(estado=ESTADO_RETENCAO_SUBSTITUIDA)
    confirmacao = ConfirmacaoRetencaoPresumido(
        escrituracao=escrituracao,
        irrf_confirmado=irrf,
        csll_confirmada=csll,
        motivo=motivo_limpo,
        estado=ESTADO_RETENCAO_ATIVA,
        confirmada_por=usuario,
    )
    _inserir(
        confirmacao,
        "presumido_confirmacao_ativa_unica_por_escrituracao",
        "Esta retenção acabou de ser confirmada por outra ação. Atualize a tela.",
    )
    registrar(
        acao="presumido.retencao_confirmada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=confirmacao,
        request=request,
        detalhes={
            "escrituracao_id": escrituracao.pk,
            "antes": antes,
            "depois": {
                "irrf_confirmado": _texto_valor(irrf),
                "csll_confirmada": _texto_valor(csll),
            },
            "substituiu": anterior is not None,
        },
    )
    return confirmacao


def _texto_valor(valor) -> str | None:
    return None if valor is None else str(valor)


@dataclass(frozen=True)
class LinhaRetencao:
    escrituracao_id: int
    numero: str
    data_competencia: date
    valor_servico: Decimal
    irrf_proposto: Decimal | None
    csll_proposta: Decimal | None
    csll_situacao: str
    csll_motivo: str
    irrf_confirmado: Decimal | None
    csll_confirmada: Decimal | None


def retencoes_do_trimestre(empresa: Empresa, ano: int, trimestre: int) -> tuple[LinhaRetencao, ...]:
    """Propostas de cada nota do trimestre e o que o contador já confirmou (HI-102, HI-103)."""
    validar_ano_e_trimestre(ano, trimestre)
    padroes = list(AtividadePresuncaoEmpresa.objects.filter(empresa=empresa, padrao=True))
    notas = []
    for escrituracao in _escrituracoes_que_contam(empresa, ano, trimestre):
        nota, _recusa = _ler_nota(escrituracao, padroes)
        if nota is not None:
            notas.append(nota)
    confirmacoes = _confirmacoes_ativas(empresa, [n.escrituracao_id for n in notas])
    linhas = []
    for nota in notas:
        confirmacao = confirmacoes.get(nota.escrituracao_id)
        linhas.append(
            LinhaRetencao(
                escrituracao_id=nota.escrituracao_id,
                numero=nota.numero,
                data_competencia=nota.data_competencia,
                valor_servico=nota.valor_servico,
                irrf_proposto=nota.retencao.irrf,
                csll_proposta=nota.retencao.csll,
                csll_situacao=nota.retencao.csll_situacao,
                csll_motivo=nota.retencao.csll_motivo,
                irrf_confirmado=confirmacao.irrf_confirmado if confirmacao else None,
                csll_confirmada=confirmacao.csll_confirmada if confirmacao else None,
            )
        )
    return tuple(
        sorted(linhas, key=lambda linha_: (linha_.data_competencia, linha_.escrituracao_id))
    )


# ---------------------------------------------------------------------------
# Medida judicial contra o acréscimo
# ---------------------------------------------------------------------------


def _validar_medida(dados: dict) -> dict:
    tributo = dados.get("tributo")
    if tributo not in ("irpj", "csll", "ambos"):
        raise EntradaInvalidaPresumido("Tributo da medida: use 'irpj', 'csll' ou 'ambos'.")
    ano_i, tri_i = dados.get("ano_inicial"), dados.get("trimestre_inicial")
    validar_ano_e_trimestre(ano_i, tri_i)
    ano_f, tri_f = dados.get("ano_final"), dados.get("trimestre_final")
    if (ano_f is None) != (tri_f is None):
        raise EntradaInvalidaPresumido(
            "Informe o ano e o trimestre final juntos, ou nenhum (prazo indeterminado)."
        )
    if ano_f is not None:
        validar_ano_e_trimestre(ano_f, tri_f)
        if (ano_f, tri_f) < (ano_i, tri_i):
            raise EntradaInvalidaPresumido("O período final é anterior ao inicial.")
    deposito = dados.get("deposito_judicial", False)
    if not isinstance(deposito, bool):
        raise EntradaInvalidaPresumido("'deposito_judicial' é true ou false.")
    return {
        "tributo": tributo,
        "ano_inicial": ano_i,
        "trimestre_inicial": tri_i,
        "ano_final": ano_f,
        "trimestre_final": tri_f,
        "numero_processo": _texto(dados.get("numero_processo"), "o número do processo", 60),
        "orgao": _texto(dados.get("orgao"), "o órgão judicial", 200),
        "data_decisao": _data(dados.get("data_decisao"), "a data da decisão"),
        "deposito_judicial": deposito,
        "suporte": _texto(dados.get("suporte"), "o documento de suporte", TEXTO_CURTO_MAXIMO),
    }


@transaction.atomic
def cadastrar_medida(empresa: Empresa, dados: dict, usuario, request=None) -> MedidaJudicialLC224:
    valores = _validar_medida(dados)
    travada = receita_servico.travar_empresa(empresa)
    medida = MedidaJudicialLC224(empresa=travada, criada_por=usuario, **valores)
    medida.save()
    registrar(
        acao="presumido.medida_cadastrada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=medida,
        request=request,
        detalhes={"tributo": valores["tributo"], "depositos": valores["deposito_judicial"]},
    )
    return medida


@transaction.atomic
def revogar_medida(
    empresa: Empresa, medida_id: int, motivo, usuario, request=None
) -> MedidaJudicialLC224:
    motivo_limpo = _texto(motivo, "o motivo da revogação", MOTIVO_MAXIMO)
    travada = receita_servico.travar_empresa(empresa)
    medida = (
        MedidaJudicialLC224.objects.select_for_update(of=("self",))
        .filter(pk=medida_id, empresa=travada)
        .first()
    )
    if medida is None:
        raise NaoEncontradoPresumido("Medida judicial não encontrada nesta empresa.")
    if not medida.ativa:
        raise PresumidoConflito("Esta medida já foi revogada.")
    MedidaJudicialLC224.objects.filter(pk=medida.pk, ativa=True).update(
        ativa=False, revogada_em=timezone.now(), motivo_revogacao=motivo_limpo
    )
    medida.refresh_from_db()
    registrar(
        acao="presumido.medida_revogada",
        usuario=usuario,
        escritorio=travada.escritorio,
        objeto=medida,
        request=request,
        detalhes={"antes": {"ativa": True}, "depois": {"ativa": False}},
    )
    return medida


def listar_medidas(empresa: Empresa):
    return MedidaJudicialLC224.objects.filter(empresa=empresa).order_by(
        "ano_inicial", "trimestre_inicial", "id"
    )


def _medida_que_cobre(medidas, tributo: str, ano: int, trimestre: int):
    for medida in medidas:
        if medida.tributo not in (tributo, tab.AMBOS):
            continue
        fim = None if medida.ano_final is None else (medida.ano_final, medida.trimestre_final)
        if calc.cobre_o_trimestre(
            (medida.ano_inicial, medida.trimestre_inicial), fim, ano, trimestre
        ):
            return medida
    return None


# ---------------------------------------------------------------------------
# Apuração do trimestre
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ColunasTributo:
    """Um tributo no trimestre pedido: as três colunas e o que sai a recolher (HI-100, item 10)."""

    tributo: str
    acrescimo_aplicavel: bool
    receita_presumida: Decimal
    receitas_integrais: Decimal
    base_sem_lc224: Decimal
    base_com_lc224: Decimal | None
    imposto_sem_lc224: Decimal
    imposto_com_lc224: Decimal | None
    parcela_lc224: Decimal | None
    adicional_com_lc224: Decimal
    memoria_com_lc224: tuple[calc.LinhaAtividade, ...]
    memoria_sem_lc224: tuple[calc.LinhaAtividade, ...]
    deducao_quarto_trimestre: Decimal
    saldo_per_dcomp: Decimal
    retencao_confirmada: Decimal
    coluna_escolhida: str
    medida: str
    valor_suspenso: Decimal | None
    tributo_escolhido: Decimal
    a_recolher: Decimal
    saldo_negativo: Decimal
    quotas: calc.OpcoesDeQuota
    caso_quarto: str | None


@dataclass(frozen=True)
class Apuracao:
    ano: int
    trimestre: int
    situacao: str
    recusas: tuple[Recusa, ...]
    criterio: str | None
    declaracao_valida: bool
    declaracao_total: Decimal | None
    integrais_atuais: Decimal
    notas: tuple[NotaApurada, ...]
    receitas: tuple[ReceitaApurada, ...]
    irpj: ColunasTributo | None
    csll: ColunasTributo | None
    fechamento_irpj: calc.Fechamento | None
    fechamento_csll: calc.Fechamento | None
    avisos: tuple[str, ...]


def _avisos(empresa: Empresa, acrescimo: bool) -> tuple[str, ...]:
    avisos = []
    if acrescimo:
        avisos.append(tab.AVISO_ADI)
    if empresa.data_abertura_cnpj is None:
        avisos.append(
            "Data de abertura no CNPJ não informada: a apuração supõe atividade no ano inteiro."
        )
    return tuple(avisos)


def _colunas(
    tributo: str,
    ano: int,
    trimestre: int,
    apuracao_anual: calc.ApuracaoAnual,
    integrais: Decimal,
    retencao: Decimal,
    medida,
) -> ColunasTributo:
    linha = apuracao_anual.linhas[trimestre - 1]
    sem = linha.sem_lc224
    com = linha.com_lc224
    aplicavel = linha.em_acrescimo
    deducao = apuracao_anual.deducao_quarto_trimestre if trimestre == 4 else ZERO
    escolhido_base = com if aplicavel and medida is None else sem
    tributo_devido = escolhido_base.total
    deducao_aplicada = min(deducao, tributo_devido)
    saldo_dcomp = deducao - deducao_aplicada
    apos_deducao = tributo_devido - deducao_aplicada
    a_recolher = max(ZERO, apos_deducao - retencao)
    saldo_negativo = max(ZERO, retencao - apos_deducao)
    quotas = calc.opcoes_de_quota(a_recolher, ano, trimestre)
    caso = (
        apuracao_anual.fechamento.caso if (trimestre == 4 and apuracao_anual.fechamento) else None
    )
    return ColunasTributo(
        tributo=tributo,
        acrescimo_aplicavel=aplicavel,
        receita_presumida=linha.receita_presumida,
        receitas_integrais=integrais,
        base_sem_lc224=sem.base,
        base_com_lc224=com.base if com else None,
        imposto_sem_lc224=sem.total,
        imposto_com_lc224=com.total if com else None,
        parcela_lc224=linha.parcela_lc224,
        adicional_com_lc224=(com if com is not None else sem).adicional,
        memoria_com_lc224=(com if com is not None else sem).linhas,
        memoria_sem_lc224=sem.linhas,
        deducao_quarto_trimestre=deducao_aplicada,
        saldo_per_dcomp=saldo_dcomp,
        retencao_confirmada=retencao,
        coluna_escolhida="com_lc224" if escolhido_base is com else "sem_lc224",
        medida=(
            "nenhuma"
            if medida is None or not aplicavel
            else ("depositar" if medida.deposito_judicial else "suspensa")
        ),
        valor_suspenso=linha.parcela_lc224 if (medida is not None and aplicavel) else None,
        tributo_escolhido=tributo_devido,
        a_recolher=a_recolher,
        saldo_negativo=saldo_negativo,
        quotas=quotas,
        caso_quarto=caso,
    )


def apurar_trimestre(empresa: Empresa, ano, trimestre) -> Apuracao:
    """Apuração do trimestre de IRPJ e CSLL, com memória e recusas nomeadas (DL-079, item 4).

    Entrada inválida levanta `EntradaInvalidaPresumido` (400). Regra de negócio que impede a
    apuração NÃO levanta: sai em `recusas`, e os tributos ficam None (sem número errado).
    """
    try:
        validar_ano_e_trimestre(ano, trimestre)
    except EntradaInvalidaPresumido as exc:
        # Ano ou trimestre inválido é recusa nomeada (sai em `recusas`), sem tributo calculado.
        return Apuracao(
            ano=ano,
            trimestre=trimestre,
            situacao="parcial",
            recusas=(Recusa("ano_ou_trimestre_invalido", exc.mensagem),),
            criterio=None,
            declaracao_valida=False,
            declaracao_total=None,
            integrais_atuais=ZERO,
            notas=(),
            receitas=(),
            irpj=None,
            csll=None,
            fechamento_irpj=None,
            fechamento_csll=None,
            avisos=(),
        )
    periodos, recusas_do_ano, carregados = _periodos_do_ano(empresa, ano, trimestre)
    dados = carregados[trimestre]
    recusas = list(recusas_do_ano)
    if not dados.em_atividade:
        recusas.append(
            Recusa(
                "trimestre_antes_da_abertura",
                f"O {trimestre}º trimestre de {ano} é anterior à abertura da empresa.",
            )
        )

    criterio = criterio_do_ano(empresa, ano)
    if criterio is None:
        recusas.append(
            Recusa(
                "criterio_nao_informado",
                f"O critério de receita de {ano} não foi informado (competência ou caixa).",
            )
        )
    elif criterio == CRITERIO_CAIXA:
        recusas.append(
            Recusa(
                "criterio_caixa",
                "Regime de caixa no presumido não é apurado aqui (IN RFB 1.700/2017, art. 223).",
            )
        )

    declaracao, valida = _declaracao_valida(empresa, ano, trimestre)
    integrais_atuais = dados.integrais
    notas = dados.notas
    receitas = dados.receitas
    if recusas:
        return Apuracao(
            ano=ano,
            trimestre=trimestre,
            situacao="parcial",
            recusas=tuple(recusas),
            criterio=criterio,
            declaracao_valida=valida,
            declaracao_total=declaracao.total if declaracao else None,
            integrais_atuais=integrais_atuais,
            notas=notas,
            receitas=receitas,
            irpj=None,
            csll=None,
            fechamento_irpj=None,
            fechamento_csll=None,
            avisos=_avisos(empresa, False),
        )

    retencao_irrf, retencao_csll = _retencoes_confirmadas(empresa, dados)
    medidas = list(MedidaJudicialLC224.objects.filter(empresa=empresa, ativa=True))
    anual = {t: calc.apurar_ano(t, ano, periodos) for t in tab.TRIBUTOS}
    colunas = {
        tab.IRPJ: _colunas(
            tab.IRPJ,
            ano,
            trimestre,
            anual[tab.IRPJ],
            dados.integrais,
            retencao_irrf,
            _medida_que_cobre(medidas, tab.IRPJ, ano, trimestre),
        ),
        tab.CSLL: _colunas(
            tab.CSLL,
            ano,
            trimestre,
            anual[tab.CSLL],
            dados.integrais,
            retencao_csll,
            _medida_que_cobre(medidas, tab.CSLL, ano, trimestre),
        ),
    }
    acrescimo = any(c.acrescimo_aplicavel for c in colunas.values())
    situacao = "completa" if valida else "parcial"
    return Apuracao(
        ano=ano,
        trimestre=trimestre,
        situacao=situacao,
        recusas=(),
        criterio=criterio,
        declaracao_valida=valida,
        declaracao_total=declaracao.total if declaracao else None,
        integrais_atuais=integrais_atuais,
        notas=notas,
        receitas=receitas,
        irpj=colunas[tab.IRPJ],
        csll=colunas[tab.CSLL],
        fechamento_irpj=anual[tab.IRPJ].fechamento,
        fechamento_csll=anual[tab.CSLL].fechamento,
        avisos=_avisos(empresa, acrescimo),
    )


# ---------------------------------------------------------------------------
# Controle do limite da LC 224 no ano
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaControle:
    trimestre: int
    em_acrescimo: bool
    receita_presumida: Decimal
    limite: Decimal | None
    excedente: Decimal
    sobra: Decimal | None


@dataclass(frozen=True)
class ControleLimite:
    ano: int
    tributo: str
    primeiro_trimestre: int | None
    linhas: tuple[LinhaControle, ...]
    fechamento: calc.Fechamento | None
    recusas: tuple[Recusa, ...]


def controle_limite_ano(empresa: Empresa, ano, tributo: str) -> ControleLimite:
    """Limite do ano por trimestre (R_t, L_t, E_t, sobra) e o fechamento com o caso (item 4)."""
    if not isinstance(ano, int) or isinstance(ano, bool):
        raise EntradaInvalidaPresumido("Informe o ano como número inteiro.")
    if tributo not in tab.TRIBUTOS:
        raise EntradaInvalidaPresumido("Tributo: use 'irpj' ou 'csll'.")
    validar_ano_e_trimestre(ano, 1)
    periodos, recusas, _carregados = _periodos_do_ano(empresa, ano, 4)
    anual = calc.apurar_ano(tributo, ano, periodos)
    linhas = tuple(
        LinhaControle(
            trimestre=linha.trimestre,
            em_acrescimo=linha.em_acrescimo,
            receita_presumida=linha.receita_presumida,
            limite=linha.limite,
            excedente=linha.excedente,
            sobra=linha.sobra,
        )
        for linha in anual.linhas
    )
    return ControleLimite(
        ano=ano,
        tributo=tributo,
        primeiro_trimestre=anual.primeiro_trimestre,
        linhas=linhas,
        fechamento=anual.fechamento,
        recusas=tuple(recusas),
    )
