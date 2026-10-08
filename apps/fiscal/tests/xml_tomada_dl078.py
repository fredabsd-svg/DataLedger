"""Gerador de NFS-e SINTÉTICA TOMADA, com os campos federais e de regime, para a DL-078.

Dados 100% sintéticos: CNPJs de `xml_sinteticos`, valores escritos à mão nos testes, nenhuma
nota real. A posição de cada elemento segue o XSD (a linha de cada caminho está em
`apps/fiscal/tomadas_campos.py`). Não há validação contra o XSD neste ambiente (sem lxml nem
xmlschema); a conferência dos caminhos foi feita lendo os dois XSD oficiais.

Parâmetro `omitir` tira um elemento do XML (ausência), e um valor `None` também não é escrito.
Nunca se escreve texto vazio para simular ausência: isso seria outra coisa.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_PRESTADOR_PADRAO,
    CNPJ_TOMADOR_PADRAO,
    NS_NFSE,
    identificador_nfse,
)

# CPF sintético de exemplo (o da documentação pública), usado só para o prestador pessoa física.
CPF_PRESTADOR_SINTETICO = "52998224725"


def _elemento(nome: str, valor: str | None, omitir: frozenset[str]) -> str:
    if valor is None or nome in omitir:
        return ""
    return f"<{nome}>{escape(valor)}</{nome}>"


def xml_tomada(
    *,
    versao: str = "1.01",
    sufixo: int = 1,
    identificador: str | None = None,
    numero: str | None = None,
    prestador_documento: str = CNPJ_PRESTADOR_PADRAO,
    prestador_tipo: str = "CNPJ",
    prestador_nome: str = "Prestadora Sintética Ltda",
    tomador_documento: str = CNPJ_TOMADOR_PADRAO,
    tomador_nome: str = "Tomadora Sintética Ltda",
    dh_emi: str = "2026-10-05T10:00:00-03:00",
    d_compet: str = "2026-10-05",
    tp_emit: str | None = "1",
    c_loc_incid: str | None = "1721000",
    c_loc_prestacao: str | None = "1721000",
    c_trib_nac: str | None = "170101",
    op_simp_nac: str | None = None,
    reg_ap_trib_sn: str | None = None,
    v_serv: str = "1000.00",
    v_desc_incond: str | None = None,
    v_desc_cond: str | None = None,
    v_liq: str = "1000.00",
    v_iss_qn: str | None = None,
    tp_ret_issqn: str | None = "2",
    trib_issqn: str | None = "1",
    federal: bool = True,
    cst_pis_cofins: str = "00",
    v_pis: str | None = None,
    v_cofins: str | None = None,
    tp_ret_pis_cofins: str | None = None,
    v_ret_cp: str | None = None,
    v_ret_irrf: str | None = None,
    v_ret_csll: str | None = None,
    omitir: frozenset[str] = frozenset(),
) -> bytes:
    """NFS-e sintética tomada. Os campos federais só entram com `federal=True`.

    `omitir` aceita nomes de elemento (ex.: "vRetCP", "tpEmit", "cLocIncid", "vISSQN").
    `federal=False` não escreve o grupo `tribFed` (ausência do grupo inteiro, caso CPF e MEI).
    """
    if identificador is None:
        identificador = identificador_nfse(sufixo)
    if numero is None:
        numero = str(sufixo)

    if prestador_tipo == "CPF":
        doc_prestador = f"<CPF>{escape(prestador_documento)}</CPF>"
    else:
        doc_prestador = f"<CNPJ>{escape(prestador_documento)}</CNPJ>"

    regime = ""
    if op_simp_nac is not None and "opSimpNac" not in omitir:
        regime_filhos = _elemento("opSimpNac", op_simp_nac, omitir)
        regime_filhos += _elemento("regApTribSN", reg_ap_trib_sn, omitir)
        regime = f"<regTrib>{regime_filhos}</regTrib>"

    desc_cond = ""
    if v_desc_incond is not None or v_desc_cond is not None:
        desc_cond = (
            "<vDescCondIncond>"
            + _elemento("vDescIncond", v_desc_incond, omitir)
            + _elemento("vDescCond", v_desc_cond, omitir)
            + "</vDescCondIncond>"
        )

    trib_mun = (
        "<tribMun>"
        + _elemento("tribISSQN", trib_issqn, omitir)
        + _elemento("tpRetISSQN", tp_ret_issqn, omitir)
        + "</tribMun>"
    )

    federal_xml = ""
    if federal:
        pis_cofins = ""
        if tp_ret_pis_cofins is not None or v_pis is not None or v_cofins is not None:
            pis_cofins = (
                "<piscofins>"
                + _elemento("CST", cst_pis_cofins, omitir)
                + _elemento("vPis", v_pis, omitir)
                + _elemento("vCofins", v_cofins, omitir)
                + _elemento("tpRetPisCofins", tp_ret_pis_cofins, omitir)
                + "</piscofins>"
            )
        federal_xml = (
            "<tribFed>"
            + pis_cofins
            + _elemento("vRetCP", v_ret_cp, omitir)
            + _elemento("vRetIRRF", v_ret_irrf, omitir)
            + _elemento("vRetCSLL", v_ret_csll, omitir)
            + "</tribFed>"
        )

    servico_loc = ""
    if c_loc_prestacao is not None and "cLocPrestacao" not in omitir:
        servico_loc = f"<locPrest><cLocPrestacao>{c_loc_prestacao}</cLocPrestacao></locPrest>"

    corpo = f"""<NFSe xmlns="{NS_NFSE}" versao="{versao}">
  <infNFSe Id="{identificador}">
    <xLocEmi>Palmas</xLocEmi>
    <xLocPrestacao>Palmas</xLocPrestacao>
    <nNFSe>{numero}</nNFSe>
    {_elemento("cLocIncid", c_loc_incid, omitir)}
    <xTribNac>Descrição sintética</xTribNac>
    <emit>{doc_prestador}<xNome>{escape(prestador_nome)}</xNome></emit>
    <valores>
      <vBC>{v_serv}</vBC>
      {_elemento("vISSQN", v_iss_qn, omitir)}
      <vLiq>{v_liq}</vLiq>
    </valores>
    <DPS versao="{versao}">
      <infDPS Id="DPS{"0" * 42}">
        <tpAmb>1</tpAmb>
        <dhEmi>{dh_emi}</dhEmi>
        <dCompet>{d_compet}</dCompet>
        {_elemento("tpEmit", tp_emit, omitir)}
        <prest>{doc_prestador}<xNome>{escape(prestador_nome)}</xNome>{regime}</prest>
        <toma><CNPJ>{tomador_documento}</CNPJ><xNome>{escape(tomador_nome)}</xNome></toma>
        <serv>
          {servico_loc}
          <cServ>{_elemento("cTribNac", c_trib_nac, omitir)}</cServ>
        </serv>
        <valores>
          <vServPrest>{_elemento("vServ", v_serv, omitir)}</vServPrest>
          {desc_cond}
          <trib>
            {trib_mun}
            {federal_xml}
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
</NFSe>"""
    return corpo.encode("utf-8")
