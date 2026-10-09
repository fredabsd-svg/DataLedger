"""Suporte dos testes da DL-079 (frente A): NFS-e PRESTADAS sintéticas pelo pipeline real.

As notas passam por `services.receber_envio` (recepção real) e são efetivadas pelo serviço real
(`apps.fiscal.escrituracao`). O XML base é o de `xml_sinteticos.xml_nfse`; este módulo só acrescenta
os campos que o presumido lê: `vDescCondIncond/vDescIncond` e `tribFed` (IRRF, CSLL e PIS/Cofins).
Os CNPJs são os de `conftest` (empresa_a é a prestadora). Tudo é sintético.
"""

from __future__ import annotations

from apps.fiscal import escrituracao as escrituracao_servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_nfse

NATUREZA_INTERNA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR


def xml_prestada(
    *,
    sufixo: int,
    v_serv: str,
    d_compet: str,
    desc_incond: str | None = None,
    ret_irrf: str | None = None,
    ret_csll: str | None = None,
    tp_ret: str | None = None,
    v_pis: str | None = None,
    v_cofins: str | None = None,
    prestador: str | None = None,
) -> bytes:
    """NFS-e prestada sintética. Campo omitido (None) fica AUSENTE no XML, como no acervo real."""
    base = xml_nfse(
        identificador=identificador_nfse(sufixo),
        numero=str(sufixo),
        dh_emi=f"{d_compet}T10:00:00-03:00",
        d_compet=d_compet,
        v_serv=v_serv,
        v_liq=v_serv,
        **({"prestador_documento": prestador} if prestador is not None else {}),
    ).decode("utf-8")
    if desc_incond is not None:
        bloco = f"<vDescCondIncond><vDescIncond>{desc_incond}</vDescIncond></vDescCondIncond>"
        base = base.replace("</vServPrest>", "</vServPrest>" + bloco, 1)
    fed = []
    if tp_ret is not None or v_pis is not None or v_cofins is not None:
        pis = "<piscofins><CST>00</CST>"
        if v_pis is not None:
            pis += f"<vPis>{v_pis}</vPis>"
        if v_cofins is not None:
            pis += f"<vCofins>{v_cofins}</vCofins>"
        if tp_ret is not None:
            pis += f"<tpRetPisCofins>{tp_ret}</tpRetPisCofins>"
        pis += "</piscofins>"
        fed.append(pis)
    if ret_irrf is not None:
        fed.append(f"<vRetIRRF>{ret_irrf}</vRetIRRF>")
    if ret_csll is not None:
        fed.append(f"<vRetCSLL>{ret_csll}</vRetCSLL>")
    if fed:
        base = base.replace("</tribMun>", "</tribMun><tribFed>" + "".join(fed) + "</tribFed>", 1)
    return base.encode("utf-8")


def receber_prestada(escritorio, usuario, sufixo: int, **xml) -> DocumentoFiscal:
    """Recebe a NFS-e prestada pelo pipeline real e devolve o documento gravado."""
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_prestada(sufixo=sufixo, **xml),
        nome_arquivo=f"prestada-{sufixo}.xml",
    )
    return DocumentoFiscal.objects.get(
        escritorio=escritorio, identificador=identificador_nfse(sufixo)
    )


def efetivar_prestada(documento: DocumentoFiscal, empresa, usuario):
    """Efetiva a nota pelo serviço de escrituração (natureza interna: mercado interno)."""
    vinculo = VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.PRESTADOR
    )
    return escrituracao_servico.efetivar_escrituracao(vinculo, NATUREZA_INTERNA, usuario)


def nota_efetivada(escritorio, empresa, usuario, sufixo: int, **xml):
    """Nota prestada recebida e efetivada. Devolve a `EscrituracaoFiscal`."""
    documento = receber_prestada(escritorio, usuario, sufixo, **xml)
    return efetivar_prestada(documento, empresa, usuario)
