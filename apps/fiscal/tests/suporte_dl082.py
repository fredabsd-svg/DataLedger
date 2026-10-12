"""Suporte da DL-082 (frente A): NF-e de saída e de devolução e meses confirmados.

Monta o cenário pelos serviços reais (escrituração, receita, confirmação do mês). NÃO calcula nenhum
valor esperado: os números dos testes são escritos à mão nos próprios testes (AGENTS.md §7).
"""

from decimal import Decimal

from apps.fiscal import escrituracao_nfe as servico_nfe
from apps.fiscal import receita as servico_receita
from apps.fiscal.models import ItemNFe
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, vinculo
from apps.fiscal.tests.test_dl074_suporte import informar_e_confirmar
from apps.fiscal.tests.test_dl075_suporte import sequencia_anterior

DATA_PA = "2026-06-15T10:00:00-03:00"


def nota(
    escritorio,
    usuario,
    empresa,
    *,
    numero,
    itens,
    devolucao=False,
    id_dest="1",
    dh_emi=DATA_PA,
    emitente_cnpj=None,
):
    """NF-e de saída própria (ou de devolução recebida), com os itens dados.

    Cada item é um dict: `cfop`, `vprod`, e opcionalmente `csosn` (padrão 102), `vst` (ICMS-ST do
    item, fora da receita), `ncm`. `vNF` é a soma de `vProd` e `vST`, como a nota real.
    """
    dets = []
    soma = Decimal("0")
    soma_st = Decimal("0")
    for n, item in enumerate(itens, start=1):
        filhos = f"<vICMSST>{item['vst']}</vICMSST>" if item.get("vst") else ""
        icms = xml.icms(csosn=item.get("csosn", "102"), filhos=filhos)
        dets.append(
            xml.det(
                n,
                cfop=item["cfop"],
                vprod=item["vprod"],
                ncm=item.get("ncm", "22030000"),
                icms_xml=icms,
            )
        )
        soma += Decimal(item["vprod"])
        soma_st += Decimal(item.get("vst", "0"))
    totais = {"vProd": f"{soma:.2f}"}
    if soma_st:
        totais["vST"] = f"{soma_st:.2f}"
    vnf = f"{soma + soma_st:.2f}"
    emitente = ("CNPJ", emitente_cnpj) if emitente_cnpj else None
    kwargs = {"emitente": emitente} if emitente else {}
    return receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=dets,
            vnf=vnf,
            totais=totais,
            numero=str(numero),
            dh_emi=dh_emi,
            tp_nf="0" if devolucao else "1",
            fin_nfe="4" if devolucao else "1",
            id_dest=id_dest,
            **kwargs,
        ),
    )


def escriturar(
    empresa,
    usuario,
    documento,
    naturezas: dict[int, str],
    *,
    marcas=(),
    segmentos: dict[int, str] | None = None,
):
    """Rascunho, naturezas por número de item, marcas e segmentos de devolução, e efetivação.

    Usa os serviços de produção. `naturezas`, `marcas` e `segmentos` referem-se a `n_item`.
    """
    esc = servico_nfe.criar_rascunho(vinculo(documento, empresa), usuario=usuario)
    ids = {i.n_item: i.pk for i in ItemNFe.objects.filter(documento=documento)}
    for n_item, natureza in naturezas.items():
        servico_nfe.definir_natureza(esc, natureza, [ids[n_item]], usuario=usuario)
    if marcas:
        servico_nfe.definir_marca_monofasico(esc, [ids[n] for n in marcas], True, usuario)
    for n_item, segmento in (segmentos or {}).items():
        servico_nfe.definir_segmento_devolucao(esc, [ids[n_item]], segmento, usuario)
    return servico_nfe.efetivar(esc, usuario=usuario)


def janela(empresa, usuario, ate_ano, ate_mes, interno, externo=None):
    """Confirma os 12 meses ANTERIORES ao PA, com a receita informada de cada mercado.

    `interno` e `externo` têm 12 valores, do mais antigo. Valor zero não lança receita; o mês é
    confirmado do mesmo jeito, porque a janela do art. 22 exige os 12 meses confirmados.
    """
    externo = externo or [0] * 12
    assert len(interno) == 12 and len(externo) == 12
    for (ano, mes), valor_interno, valor_externo in zip(
        sequencia_anterior(ate_ano, ate_mes), interno, externo, strict=True
    ):
        if valor_interno:
            informar_e_confirmar(empresa, usuario, ano, mes, str(valor_interno), "interno")
        if valor_externo:
            informar_e_confirmar(empresa, usuario, ano, mes, str(valor_externo), "externo")
        servico_receita.confirmar_mes(empresa, ano, mes, usuario)


def informar(empresa, usuario, ano, mes, valor, mercado="interno"):
    """Receita informada confirmada no mês (sem confirmar o mês: o PA é confirmado depois das
    NF-e)."""
    return informar_e_confirmar(empresa, usuario, ano, mes, str(valor), mercado)


def confirmar_pa(empresa, usuario, ano=2026, mes=6):
    return servico_receita.confirmar_mes(empresa, ano, mes, usuario)
