"""Gerador de NFS-e SINTÉTICA com os campos de ISS, para os testes da DL-076.

Dados 100% sintéticos: CNPJs de `xml_sinteticos`, valores inventados para conferir a
aritmética, nenhuma nota real. Os elementos seguem a posição do XSD v1.01 (ver
`apps/fiscal/iss_nota.py` para cada caminho). Parâmetro `omitir` tira um campo do XML,
para testar a ausência: nunca se passa `None` como valor, porque isso escreveria o
elemento com texto vazio, que é outra coisa.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_PRESTADOR_PADRAO,
    CNPJ_TOMADOR_PADRAO,
    NS_NFSE,
    identificador_nfse,
)


def _pessoa(tag: str, documento: str, nome: str) -> str:
    return f"<{tag}><CNPJ>{documento}</CNPJ><xNome>{escape(nome)}</xNome></{tag}>"


def xml_nfse_iss(
    *,
    versao: str = "1.01",
    sufixo: int = 1,
    identificador: str | None = None,
    numero: str | None = None,
    prestador_documento: str = CNPJ_PRESTADOR_PADRAO,
    prestador_nome: str = "Prestadora Sintética Ltda",
    tomador_documento: str = CNPJ_TOMADOR_PADRAO,
    tomador_nome: str = "Tomadora Sintética Ltda",
    dh_emi: str = "2026-10-05T10:00:00-03:00",
    d_compet: str = "2026-10-05",
    c_trib_nac: str | None = "170101",
    c_loc_incid: str | None = "1721000",
    v_serv: str = "1000.00",
    v_desc_incond: str | None = None,
    v_dr: str | None = None,
    v_calc_dr: str | None = None,
    v_bc: str | None = "1000.00",
    p_aliq_aplic: str | None = "5.00",
    v_iss_qn: str | None = "50.00",
    tp_ret_issqn: str = "1",
    trib_issqn: str | None = "1",
    v_liq: str = "1000.00",
    omitir: frozenset[str] = frozenset(),
) -> bytes:
    """NFS-e sintética com os campos de ISS. Padrão: ISS devido, 5%, sobre R$ 1.000,00.

    `omitir` aceita nomes de elemento (ex.: "vBC", "cLocIncid", "cTribNac"). Um campo
    em `omitir` não é escrito. Um valor `None` também não é escrito.
    """
    if identificador is None:
        identificador = identificador_nfse(sufixo)
    if numero is None:
        numero = str(sufixo)

    def campo(nome: str, valor: str | None) -> str:
        if valor is None or nome in omitir:
            return ""
        return f"<{nome}>{escape(valor)}</{nome}>"

    loc_incid = campo("cLocIncid", c_loc_incid)
    trib_iss = campo("tribISSQN", trib_issqn)
    desc = (
        f"<vDescCondIncond>{campo('vDescIncond', v_desc_incond)}</vDescCondIncond>"
        if v_desc_incond is not None and "vDescIncond" not in omitir
        else ""
    )
    ded = (
        f"<vDedRed><pDR>0.00</pDR>{campo('vDR', v_dr)}</vDedRed>"
        if v_dr is not None and "vDR" not in omitir
        else ""
    )
    corpo = f"""<NFSe xmlns="{NS_NFSE}" versao="{versao}">
  <infNFSe Id="{identificador}">
    <xLocEmi>Palmas</xLocEmi>
    <xLocPrestacao>Palmas</xLocPrestacao>
    <nNFSe>{numero}</nNFSe>
    {loc_incid}
    <xTribNac>Descrição sintética</xTribNac>
    <emit><CNPJ>{prestador_documento}</CNPJ><xNome>{escape(prestador_nome)}</xNome></emit>
    <valores>
      {campo("vCalcDR", v_calc_dr)}
      {campo("vBC", v_bc)}
      {campo("pAliqAplic", p_aliq_aplic)}
      {campo("vISSQN", v_iss_qn)}
      <vLiq>{v_liq}</vLiq>
    </valores>
    <DPS versao="{versao}">
      <infDPS Id="DPS{"0" * 42}">
        <tpAmb>1</tpAmb>
        <dhEmi>{dh_emi}</dhEmi>
        <dCompet>{d_compet}</dCompet>
        {_pessoa("toma", tomador_documento, tomador_nome)}
        <serv>
          <locPrest><cLocPrestacao>1721000</cLocPrestacao></locPrest>
          <cServ>{campo("cTribNac", c_trib_nac)}</cServ>
        </serv>
        <valores>
          <vServPrest><vServ>{v_serv}</vServ></vServPrest>
          {desc}
          {ded}
          <trib>
            <tribMun>
              {trib_iss}
              <tpRetISSQN>{tp_ret_issqn}</tpRetISSQN>
            </tribMun>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
</NFSe>"""
    return corpo.encode("utf-8")
