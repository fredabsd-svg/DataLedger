"""Conferência das entradas do mês — DL-091, frente A2 (classe "conferência", sem impressão).

Plano: docs/planos/DL-091-nfe-de-entrada.md, item 9 do escopo. Consulta de 13/10/2026, seção 1 e
"Proposta de corte 1", item 10. Decisões que o código não explica sozinho:

- NÃO é livro nem impressão oficial: é a tela e a API de conferência do mês da compra. O livro
  registro de entradas é outra etapa (DL-095, fora do corte 1).
- RECEBIDAS: as notas do mês em que a empresa é a DESTINATÁRIA (vínculo com papel destinatário). O
  mês é o de `servico.notas_do_mes`: a data de entrada, quando a compra está escriturada, e a
  emissão enquanto não está.
- ESCRITURADAS: compras efetivadas. A escriturar: compras em rascunho ou ainda sem escrituração.
  FORA: todas as outras, com o motivo nomeado (cancelada, cancelada depois de escriturada, devolução
  de venda recebida, e a recusa de `motivo_fora_da_escrituracao`).
- TOTAIS: a partir das escriturações EFETIVADAS da conferência (e só delas). Valor é o `vProd` do
  item, o valor da compra. Nenhum total aqui é receita: a compra não tem receita (DL-091).
- CRÉDITO e ST: lidos da MEMÓRIA gravada na efetivação (`MemoriaEntradaItemNFe`), imutável. O
  crédito elegível é o que a memória marcou como crédito destacado ou limitado (LC 123, art. 23). O
  ST retido é o `vICMSSTRet` informado, em qualquer natureza, porque é fato da nota.
- AVISOS de outro estado: as notas efetivadas cuja memória traz o aviso de antecipação ou DIFAL.
  Só aparecem os textos fixos de `entradas`; nenhuma alíquota do Tocantins.
- ISOLAMENTO: `notas_do_mes` e as consultas de totais filtram pela empresa. A permissão é conferida
  pela API, no servidor.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.fiscal import entradas
from apps.fiscal import escrituracao_nfe as servico
from apps.fiscal.models import (
    MarcaCreditoEntrada,
    MemoriaEntradaItemNFe,
    NaturezaItemNFe,
    NaturezaOperacaoNFe,
    PapelNFe,
    TipoEscrituracaoNFe,
)

ZERO = Decimal("0.00")

# Marcas cujo crédito é "elegível": o que a nota destaca e a regra admite (LC 87, art. 20; LC 123,
# art. 23). `credito_elegivel` só é preenchido nestas duas (`entradas.marca_do_credito`).
MARCAS_DE_CREDITO_ELEGIVEL = (
    MarcaCreditoEntrada.CREDITO_DESTACADO,
    MarcaCreditoEntrada.CREDITO_LIMITADO,
)
# Avisos que a conferência lista (outro estado). Os textos são os de `entradas`, fixos.
AVISOS_DE_OUTRO_ESTADO = (
    entradas.AVISO_SIMPLES_OUTRO_ESTADO,
    entradas.AVISO_NORMAL_OUTRO_ESTADO_USO,
)

CODIGO_CANCELADA = "cancelada"
CODIGO_CANCELADA_DEPOIS_DE_ESCRITURADA = "cancelada_depois_de_escriturada"
CODIGO_FORA_DA_ESCRITURACAO = "fora_da_escrituracao"
CODIGO_DEVOLUCAO_DE_VENDA = "devolucao_de_venda"

MOTIVO_DEVOLUCAO_DE_VENDA = (
    "devolução de venda recebida (finNFe 4): fica na escrituração de saída (DL-081), não na compra"
)
MOTIVO_CANCELADA_DEPOIS = (
    "cancelada depois de escriturada: estorne a escrituração para a conferência deixar de contá-la"
)


@dataclass(frozen=True)
class NotaFora:
    vinculo_id: int
    documento_id: int
    numero: str
    serie: str
    dh_emissao: datetime
    codigo: str
    motivo: str


@dataclass(frozen=True)
class LinhaDeTotal:
    """Um total: por natureza (E1 a E11) ou por CFOP de entrada. `valor` é o vProd dos itens."""

    chave: str
    rotulo: str
    itens: int
    valor: Decimal


@dataclass(frozen=True)
class NotaComAviso:
    vinculo_id: int
    documento_id: int
    numero: str
    serie: str
    avisos: tuple[str, ...]


@dataclass(frozen=True)
class TotalDeMarca:
    """Quantos itens a memória marcou com a marca, e o crédito que ela admite (zero se não há)."""

    marca: str
    itens: int
    credito: Decimal


@dataclass
class ConferenciaDeEntradas:
    ano: int
    mes: int
    recebidas: int = 0
    escrituradas: int = 0
    a_escriturar: int = 0
    fora: list[NotaFora] = field(default_factory=list)
    por_natureza: tuple[LinhaDeTotal, ...] = ()
    por_cfop_de_entrada: tuple[LinhaDeTotal, ...] = ()
    credito_destacado_elegivel: Decimal = ZERO
    por_marca: tuple[TotalDeMarca, ...] = ()
    st_retido: Decimal = ZERO
    itens_com_st_retido: int = 0
    notas_com_aviso_de_outro_estado: list[NotaComAviso] = field(default_factory=list)


def _motivo_de_fora(nota: servico.NotaDoMes) -> tuple[str, str]:
    """(código, motivo) de uma nota recebida que não é compra escriturada. Motivo nomeado."""
    if nota.situacao == servico.SITUACAO_CANCELADA_DEPOIS_DE_ESCRITURADA:
        return CODIGO_CANCELADA_DEPOIS_DE_ESCRITURADA, MOTIVO_CANCELADA_DEPOIS
    if nota.situacao == servico.SITUACAO_CANCELADA:
        return CODIGO_CANCELADA, "nota cancelada"
    if nota.tipo == TipoEscrituracaoNFe.DEVOLUCAO:
        return CODIGO_DEVOLUCAO_DE_VENDA, MOTIVO_DEVOLUCAO_DE_VENDA
    motivo = servico.motivo_fora_da_escrituracao(nota.documento, PapelNFe.DESTINATARIO)
    return CODIGO_FORA_DA_ESCRITURACAO, motivo


def conferencia_de_entradas(empresa, ano: int, mes: int) -> ConferenciaDeEntradas:
    """A conferência de entradas do mês da empresa. Só lê; não grava nada."""
    resultado = ConferenciaDeEntradas(ano=ano, mes=mes)
    recebidas = [
        nota
        for nota in servico.notas_do_mes(empresa, ano, mes)
        if nota.vinculo.papel == PapelNFe.DESTINATARIO
    ]
    resultado.recebidas = len(recebidas)
    efetivadas: list[servico.NotaDoMes] = []
    for nota in recebidas:
        if nota.tipo == TipoEscrituracaoNFe.ENTRADA:
            if nota.situacao == servico.SITUACAO_EFETIVADA:
                resultado.escrituradas += 1
                efetivadas.append(nota)
                continue
            if nota.situacao in (servico.SITUACAO_A_ESCRITURAR, servico.SITUACAO_RASCUNHO):
                resultado.a_escriturar += 1
                continue
        codigo, motivo = _motivo_de_fora(nota)
        resultado.fora.append(
            NotaFora(
                vinculo_id=nota.vinculo.pk,
                documento_id=nota.documento.pk,
                numero=nota.documento.numero,
                serie=nota.documento.serie,
                dh_emissao=nota.documento.dh_emissao,
                codigo=codigo,
                motivo=motivo,
            )
        )
    _preencher_totais(empresa, resultado, efetivadas)
    return resultado


def _preencher_totais(empresa, resultado: ConferenciaDeEntradas, efetivadas) -> None:
    """Totais das compras efetivadas: naturezas, CFOP de entrada, crédito, ST e avisos.

    Uma consulta para os itens e uma para as memórias, do conjunto de escriturações desta empresa.
    """
    if not efetivadas:
        return
    por_escrituracao = {nota.escrituracao.pk: nota for nota in efetivadas if nota.escrituracao}
    ids = list(por_escrituracao)
    registros = (
        NaturezaItemNFe.objects.select_related("item")
        .filter(escrituracao_id__in=ids, escrituracao__empresa=empresa)
        .exclude(natureza="")
    )
    por_natureza: dict[str, list] = defaultdict(lambda: [0, ZERO])
    por_cfop: dict[str, list] = defaultdict(lambda: [0, ZERO])
    for registro in registros:
        valor = registro.item.v_prod or ZERO
        for acumulado in (por_natureza[registro.natureza], por_cfop[registro.cfop_entrada]):
            acumulado[0] += 1
            acumulado[1] += valor
    resultado.por_natureza = tuple(
        LinhaDeTotal(
            chave=natureza,
            rotulo=NaturezaOperacaoNFe(natureza).label,
            itens=quantidade,
            valor=valor,
        )
        for natureza, (quantidade, valor) in sorted(por_natureza.items())
    )
    resultado.por_cfop_de_entrada = tuple(
        LinhaDeTotal(chave=cfop, rotulo=cfop, itens=quantidade, valor=valor)
        for cfop, (quantidade, valor) in sorted(por_cfop.items())
    )

    memorias = MemoriaEntradaItemNFe.objects.select_related("natureza_item").filter(
        natureza_item__escrituracao_id__in=ids,
        natureza_item__escrituracao__empresa=empresa,
    )
    credito_total = ZERO
    marcas: dict[str, list] = defaultdict(lambda: [0, ZERO])
    st_total = ZERO
    itens_st = 0
    avisos_por_nota: dict[int, set[str]] = defaultdict(set)
    for memoria in memorias:
        marcas[memoria.marca_credito][0] += 1
        # DL-091 (rodada 1, A1): só as marcas de crédito elegível entram no total. Um valor
        # preenchido em outra marca (p. ex., o comprador do Simples) não é crédito aproveitável.
        elegivel = (
            memoria.marca_credito in MARCAS_DE_CREDITO_ELEGIVEL
            and memoria.credito_elegivel is not None
        )
        if elegivel:
            credito_total += memoria.credito_elegivel
            marcas[memoria.marca_credito][1] += memoria.credito_elegivel
        if memoria.v_icms_st_ret is not None and memoria.v_icms_st_ret > 0:
            st_total += memoria.v_icms_st_ret
            itens_st += 1
        for aviso in memoria.avisos or []:
            if aviso in AVISOS_DE_OUTRO_ESTADO:
                avisos_por_nota[memoria.natureza_item.escrituracao_id].add(aviso)
    resultado.credito_destacado_elegivel = credito_total
    resultado.por_marca = tuple(
        TotalDeMarca(marca=marca, itens=quantidade, credito=credito)
        for marca, (quantidade, credito) in sorted(marcas.items())
    )
    resultado.st_retido = st_total
    resultado.itens_com_st_retido = itens_st

    for escrituracao_id, nota in por_escrituracao.items():
        if escrituracao_id in avisos_por_nota:
            resultado.notas_com_aviso_de_outro_estado.append(
                NotaComAviso(
                    vinculo_id=nota.vinculo.pk,
                    documento_id=nota.documento.pk,
                    numero=nota.documento.numero,
                    serie=nota.documento.serie,
                    avisos=tuple(sorted(avisos_por_nota[escrituracao_id])),
                )
            )
    resultado.notas_com_aviso_de_outro_estado.sort(key=lambda n: (n.numero, n.documento_id))
