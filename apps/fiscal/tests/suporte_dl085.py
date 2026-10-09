"""Suporte dos testes da DL-085 (frente A): NFC-e sintéticas e o caminho do lote até o fim.

Sem fixtures aqui: cada módulo de teste declara as suas. Tudo é sintético: os CNPJ vêm de
`xml_nfe_dl080` (com dígito verificador certo) e os valores são escritos à mão nos testes.
"""

from apps.fiscal import escrituracao_nfe_lote as lote_servico
from apps.fiscal.tests import xml_nfe_dl081 as xml
from apps.fiscal.tests.suporte_dl081 import receber, usuario_com_papel
from apps.fiscal.tests.xml_nfe_dl080 import CNPJ_DESTINATARIO_A, CNPJ_EMITENTE_A
from apps.tenancy.models import Papel

# Posto: venda de combustível a consumidor (CFOP 5656, descrição oficial), CSOSN 500 (ICMS já
# recolhido) e NCM de gasolina. A sugestão é `combustivel` (1,6%), sem conflito (DL-083).
CFOP_COMBUSTIVEL = "5656"
NCM_COMBUSTIVEL = "27101259"
# Revenda comum: CFOP 5102 e CSOSN 102, sem ST. Sugestão `revenda`.
CFOP_REVENDA = "5102"
DH_PADRAO = "2026-03-15T10:00:00-03:00"
CNPJ_SEGUNDA_EMPRESA = CNPJ_DESTINATARIO_A


def usuario_gestor(escritorio, nome="gestor-dl085"):
    return usuario_com_papel(escritorio, Papel.GESTOR, nome)


def nfce(
    escritorio,
    usuario,
    *,
    numero,
    valor="100.00",
    emitente=CNPJ_EMITENTE_A,
    cfop=CFOP_COMBUSTIVEL,
    csosn="500",
    ncm=NCM_COMBUSTIVEL,
    dh_emi=DH_PADRAO,
    dets=None,
    vnf=None,
    totais=None,
):
    """NFC-e (modelo 65) sintética, recebida pela recepção real (DL-080). Um item, salvo `dets`."""
    if dets is None:
        dets = [xml.det(1, cfop=cfop, vprod=valor, ncm=ncm, icms_xml=xml.icms(csosn=csosn))]
    return receber(
        escritorio,
        usuario,
        xml.nfe(
            dets=dets,
            vnf=vnf if vnf is not None else valor,
            totais=totais if totais is not None else {"vProd": valor},
            modelo="65",
            numero=str(numero),
            dh_emi=dh_emi,
            emitente=("CNPJ", emitente),
            destinatario=None,
        ),
    )


def confirmar_tudo(
    empresa,
    usuario,
    ano,
    mes,
    previa,
    *,
    escolhas=None,
    limite=lote_servico.LIMITE_PADRAO_DA_PARTE,
    max_partes=10_000,
):
    """Confirma a prévia dada e roda as partes até o fim. Devolve o último progresso.

    `max_partes` é só um freio contra laço infinito: um teste que precisa de mais partes que isso
    está errado.
    """
    progresso = lote_servico.confirmar_lote(
        empresa, ano, mes, previa.assinatura, escolhas or {}, usuario, limite=limite
    )
    partes = 1
    while not progresso.terminou:
        progresso = lote_servico.confirmar_lote(
            empresa, None, None, None, None, usuario, limite=limite, lote_id=progresso.lote_id
        )
        partes += 1
        if partes > max_partes:
            raise AssertionError("o lote não terminou: laço de partes")
    return progresso


def naturezas_por_item(previa_nota) -> dict[int, str]:
    """Natureza SUGERIDA de cada item de uma nota da prévia, por `ItemNFe.pk`."""
    return {item.item_id: item.natureza_sugerida for item in previa_nota.itens}


def achar_nota(previa, vinculo_id):
    """A nota de um vínculo dentro dos grupos da prévia (ou None)."""
    for grupo in previa.grupos:
        for nota in grupo.notas:
            if nota.vinculo_id == vinculo_id:
                return nota
    return None


def previa_lida(empresa, ano, mes):
    """Lê o mês inteiro em partes (como a tela faz antes de confirmar) e devolve a prévia.

    O mês de teste é menor que o teto de uma parte de leitura, então uma chamada basta. Se não
    terminar, o teste falha aqui, com o motivo, e não depois, numa asserção confusa.
    """
    leitura = lote_servico.ler_notas_do_mes(
        empresa, ano, mes, limite=lote_servico.LIMITE_MAXIMO_DA_LEITURA
    )
    assert leitura.terminou and not leitura.falhas_nesta_chamada, leitura
    return lote_servico.previa_do_lote(empresa, ano, mes)
