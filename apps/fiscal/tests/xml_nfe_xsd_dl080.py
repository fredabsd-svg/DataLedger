"""Corpus de XML SINTÉTICO de NF-e, NFC-e e evento de NF-e, validado pelo XSD (DL-080, rodada 1).

Correção do achado A6 da auditoria da DL-080 (rodada 1, 2026-10-09): o gerador `xml_nfe_dl080`
NÃO valida contra o XSD. Estes construtores foram montados do zero pelo auditor a partir dos XSD do
PL 010f (leiauteNFe_v4.00.xsd) e do PL 010d (leiauteEvento_v1.00.xsd), e cada XML foi validado com
`xmllint --schema`. Aqui entram copiados para o repositório, com a mesma estrutura.

Os XSD não entram no repositório (documento de terceiro). A validação com `xmllint` é feita pelos
testes de `test_dl080_corpus_xsd.py`, só quando o binário e a pasta dos XSD existem.

Todo CNPJ, CPF e chave daqui é SINTÉTICO. O DV é calculado por implementação PRÓPRIA deste
arquivo (`_dv_modulo_11`), independente do validador do leitor. A assinatura é um marcador de
forma: o leitor não confere assinatura (limite declarado no plano), e nada aqui é assinatura válida.
"""

from __future__ import annotations

import base64

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"

# Totais do ICMSTot na ordem do XSD. Valores sintéticos, todos em duas casas.
_TOTAIS = [
    ("vBC", "0.00"),
    ("vICMS", "0.00"),
    ("vICMSDeson", "0.00"),
    ("vFCP", "0.00"),
    ("vBCST", "0.00"),
    ("vST", "0.00"),
    ("vFCPST", "0.00"),
    ("vFCPSTRet", "0.00"),
    ("vProd", "100.00"),
    ("vFrete", "0.00"),
    ("vSeg", "0.00"),
    ("vDesc", "0.00"),
    ("vII", "0.00"),
    ("vIPI", "0.00"),
    ("vIPIDevol", "0.00"),
    ("vPIS", "0.00"),
    ("vCOFINS", "0.00"),
    ("vOutro", "0.00"),
    ("vNF", "100.00"),
]


def _dv_modulo_11(base: str, pesos: list[int]) -> str:
    """Módulo 11: caractere vale `ord(c) - 48` (cobre o CNPJ alfanumérico); resto 0 ou 1 dá DV 0."""
    soma = sum((ord(c) - 48) * peso for c, peso in zip(base, pesos, strict=True))
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def dv_da_chave(base43: str) -> str:
    """DV da chave: pesos 2 a 9 da direita para a esquerda (MOC 7.0, Tabela 2-1)."""
    n = len(base43)
    return _dv_modulo_11(base43, [2 + ((n - 1 - i) % 8) for i in range(n)])


def cnpj_valido(base12: str) -> str:
    """CNPJ de 14 posições, com os dois DV. A base aceita letras (NT Conjunta 2025.001)."""
    assert len(base12) == 12
    dv1 = _dv_modulo_11(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    dv2 = _dv_modulo_11(base12 + dv1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + dv1 + dv2


def cpf_valido(base9: str) -> str:
    """CPF de 11 dígitos, com os dois DV."""
    assert len(base9) == 9 and base9.isdigit()
    dv1 = _dv_modulo_11(base9, list(range(10, 1, -1)))
    dv2 = _dv_modulo_11(base9 + dv1, list(range(11, 1, -1)))
    return base9 + dv1 + dv2


def chave_valida(
    *,
    cuf: str = "35",
    aamm: str = "2601",
    doc14: str,
    mod: str = "55",
    serie: str = "1",
    nnf: str = "1",
    tp_emis: str = "1",
    cnf: str = "12345678",
) -> str:
    """Chave de 44 posições com o DV certo. `doc14` é o CNPJ (alfanumérico) ou o CPF zerado à
    esquerda, em 14 posições (MOC 7.0, Tabela 2-1)."""
    base43 = f"{cuf}{aamm}{doc14}{mod}{int(serie):03d}{int(nnf):09d}{tp_emis}{cnf}"
    assert len(base43) == 43, (len(base43), base43)
    return base43 + dv_da_chave(base43)


def _assinatura() -> str:
    """Marcador de forma de `ds:Signature`, com a estrutura do XMLDSig. Não assina nada."""
    return (
        f'<Signature xmlns="{NS_DSIG}"><SignedInfo>'
        '<CanonicalizationMethod Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        '<SignatureMethod Algorithm="http://www.w3.org/2000/09/xmldsig#rsa-sha1"/>'
        '<Reference URI="#X"><Transforms>'
        '<Transform Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"/>'
        '<Transform Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"/>'
        "</Transforms>"
        '<DigestMethod Algorithm="http://www.w3.org/2000/09/xmldsig#sha1"/>'
        f"<DigestValue>{base64.b64encode(b'x' * 20).decode()}</DigestValue></Reference>"
        "</SignedInfo>"
        f"<SignatureValue>{base64.b64encode(b's' * 128).decode()}</SignatureValue>"
        "<KeyInfo><X509Data>"
        f"<X509Certificate>{base64.b64encode(b'c' * 64).decode()}</X509Certificate>"
        "</X509Data></KeyInfo></Signature>"
    )


def _endereco(tag: str) -> str:
    return (
        f"<{tag}><xLgr>Rua Sintetica</xLgr><nro>10</nro><xBairro>Centro</xBairro>"
        "<cMun>3550308</cMun><xMun>Cidade Sintetica</xMun><UF>SP</UF>"
        f"<CEP>01001000</CEP><cPais>1058</cPais><xPais>Brasil</xPais></{tag}>"
    )


def _emitente(doc: str, tipo: str, nome: str, crt: str) -> str:
    return (
        f"<emit><{tipo}>{doc}</{tipo}><xNome>{nome}</xNome>{_endereco('enderEmit')}"
        f"<IE>111111111111</IE><CRT>{crt}</CRT></emit>"
    )


def _destinatario(tipo: str, doc: str, nome: str) -> str:
    if tipo == "idEstrangeiro":
        return (
            f"<dest><idEstrangeiro>{doc}</idEstrangeiro><xNome>{nome}</xNome>"
            "<indIEDest>9</indIEDest></dest>"
        )
    return (
        f"<dest><{tipo}>{doc}</{tipo}><xNome>{nome}</xNome>{_endereco('enderDest')}"
        "<indIEDest>9</indIEDest></dest>"
    )


def _local(tag: str, tipo: str, doc: str) -> str:
    """`retirada` ou `entrega` (TLocal): CNPJ ou CPF e endereço. Ficam entre `dest` e `det`."""
    return (
        f"<{tag}><{tipo}>{doc}</{tipo}><xLgr>Rua Sintetica</xLgr><nro>10</nro>"
        "<xBairro>Centro</xBairro><cMun>3550308</cMun><xMun>Cidade Sintetica</xMun>"
        f"<UF>SP</UF></{tag}>"
    )


def _det(n: int, *, ibs: bool) -> str:
    ibs_xml = "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>" if ibs else ""
    return (
        f'<det nItem="{n}"><prod><cProd>{n}</cProd><cEAN>SEM GTIN</cEAN>'
        f"<xProd>Produto sintetico {n}</xProd><NCM>22030000</NCM><CFOP>5102</CFOP>"
        "<uCom>UN</uCom><qCom>1.0000</qCom><vUnCom>100.0000000000</vUnCom>"
        "<vProd>100.00</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib>"
        "<qTrib>1.0000</qTrib><vUnTrib>100.0000000000</vUnTrib><indTot>1</indTot></prod>"
        "<imposto><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS>"
        "<PIS><PISNT><CST>07</CST></PISNT></PIS><COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS>"
        f"{ibs_xml}</imposto></det>"
    )


def xml_nfe_valido(
    *,
    emitente: tuple[str, str] = ("CNPJ", ""),
    destinatario: tuple[str, str] | None = ("CNPJ", ""),
    retirada: tuple[str, str] | None = None,
    entrega: tuple[str, str] | None = None,
    nome_emitente: str = "Emitente Sintetico Ltda",
    nome_destinatario: str = "Destinatario Sintetico Ltda",
    crt: str = "3",
    mod: str = "55",
    serie: str = "1",
    nnf: str = "1",
    tp_nf: str = "1",
    fin_nfe: str = "1",
    tp_nf_debito: str | None = None,
    dh_emi: str = "2026-01-15T10:00:00-03:00",
    itens: int = 1,
    ibs_item: bool = False,
    ibs_total: bool = False,
    totais: dict[str, str | None] | None = None,
    c_stat: str = "100",
    com_protocolo: bool = True,
    chave: str | None = None,
    declaracao: str = "UTF-8",
) -> bytes:
    """`nfeProc` (NF-e ou NFC-e) sintético, válido contra o `procNFe_v4.00.xsd`.

    `emitente` e `destinatario` são `(tipo, documento)`: `("CNPJ", ...)`, `("CPF", ...)` ou,
    só no destinatário, `("idEstrangeiro", ...)`. Sem destinatário (`None`), é o caso da NFC-e.
    A chave sai do CNPJ ou CPF do emitente, a menos que `chave` seja passada.
    `totais`: sobrescreve valores do ICMSTot; `None` como valor remove o elemento.
    """
    tipo_emit, doc_emit = emitente
    doc14 = doc_emit if tipo_emit == "CNPJ" else doc_emit.zfill(14)
    if chave is None:
        chave = chave_valida(doc14=doc14, mod=mod, serie=serie, nnf=nnf)

    valores = dict(_TOTAIS)
    for campo, valor in (totais or {}).items():
        if valor is None:
            valores.pop(campo, None)
        else:
            valores[campo] = valor
    icms_tot = "".join(f"<{campo}>{valor}</{campo}>" for campo, valor in valores.items())
    ibs_total_xml = "<IBSCBSTot><vBCIBSCBS>0.00</vBCIBSCBS></IBSCBSTot>" if ibs_total else ""
    total_xml = f"<total><ICMSTot>{icms_tot}</ICMSTot>{ibs_total_xml}</total>"

    debito_xml = f"<tpNFDebito>{tp_nf_debito}</tpNFDebito>" if tp_nf_debito else ""
    ide_xml = (
        f"<ide><cUF>{chave[:2]}</cUF><cNF>{chave[35:43]}</cNF><natOp>Venda sintetica</natOp>"
        f"<mod>{mod}</mod><serie>{serie}</serie><nNF>{nnf}</nNF>"
        f"<dhEmi>{dh_emi}</dhEmi><tpNF>{tp_nf}</tpNF><idDest>1</idDest>"
        "<cMunFG>3550308</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis>"
        f"<cDV>{chave[43]}</cDV><tpAmb>1</tpAmb><finNFe>{fin_nfe}</finNFe>{debito_xml}"
        "<indFinal>1</indFinal><indPres>1</indPres><procEmi>0</procEmi>"
        "<verProc>sintetico-rodada1</verProc></ide>"
    )
    emit_xml = _emitente(doc_emit, tipo_emit, nome_emitente, crt)
    dest_xml = ""
    if destinatario is not None:
        dest_xml = _destinatario(destinatario[0], destinatario[1], nome_destinatario)
    retirada_xml = _local("retirada", *retirada) if retirada else ""
    entrega_xml = _local("entrega", *entrega) if entrega else ""
    itens_xml = "".join(_det(n, ibs=ibs_item) for n in range(1, itens + 1))
    pag_xml = "<pag><detPag><tPag>01</tPag><vPag>100.00</vPag></detPag></pag>"

    inf_nfe = (
        f'<infNFe versao="4.00" Id="NFe{chave}">{ide_xml}{emit_xml}{dest_xml}'
        f"{retirada_xml}{entrega_xml}{itens_xml}{total_xml}"
        "<transp><modFrete>9</modFrete></transp>"
        f"{pag_xml}</infNFe>"
    )
    nfe_xml = f'<NFe xmlns="{NS_NFE}">{inf_nfe}{_assinatura()}</NFe>'
    protocolo = ""
    if com_protocolo:
        protocolo = (
            '<protNFe versao="4.00"><infProt><tpAmb>1</tpAmb><verAplic>SVRS</verAplic>'
            f"<chNFe>{chave}</chNFe><dhRecbto>2026-01-15T10:01:00-03:00</dhRecbto>"
            "<nProt>135260000000001</nProt>"
            f"<digVal>{base64.b64encode(b'd' * 20).decode()}</digVal>"
            f"<cStat>{c_stat}</cStat><xMotivo>Autorizado o uso da NF-e (sintetico)</xMotivo>"
            "</infProt></protNFe>"
        )
    texto = f'<nfeProc xmlns="{NS_NFE}" versao="4.00">{nfe_xml}{protocolo}</nfeProc>'
    return f'<?xml version="1.0" encoding="{declaracao}"?>\n{texto}'.encode()


def xml_evento_valido(
    *,
    tp_evento: str = "110111",
    chave: str,
    seq: int = 1,
    autor: tuple[str, str] = ("CNPJ", ""),
    dh_evento: str = "2026-01-20T09:00:00-03:00",
    c_stat: str | None = "135",
    declaracao: str = "UTF-8",
) -> bytes:
    """`procEventoNFe` sintético, válido contra o `procEventoNFe_v1.00.xsd` (PL 010d).

    `c_stat=None` omite o `retEvento` (evento sem retorno). O `autor` é `(tipo, documento)`.
    """
    tipo_autor, doc_autor = autor
    autor_xml = f"<{tipo_autor}>{doc_autor}</{tipo_autor}>"
    id_evento = f"ID{tp_evento}{chave}{seq:02d}"
    evento_xml = (
        f'<evento versao="1.00"><infEvento Id="{id_evento}">'
        f"<cOrgao>35</cOrgao><tpAmb>1</tpAmb>{autor_xml}"
        f"<chNFe>{chave}</chNFe><dhEvento>{dh_evento}</dhEvento>"
        f"<tpEvento>{tp_evento}</tpEvento><nSeqEvento>{seq}</nSeqEvento>"
        "<verEvento>1.00</verEvento>"
        '<detEvento versao="1.00"><descEvento>Cancelamento</descEvento>'
        "<nProt>135260000000001</nProt><xJust>Justificativa de teste valida</xJust>"
        "</detEvento></infEvento>"
        f"{_assinatura()}</evento>"
    )
    retorno = ""
    if c_stat is not None:
        retorno = (
            '<retEvento versao="1.00"><infEvento>'
            "<tpAmb>1</tpAmb><verAplic>SVRS</verAplic><cOrgao>35</cOrgao>"
            f"<cStat>{c_stat}</cStat><xMotivo>Evento registrado</xMotivo>"
            f"<chNFe>{chave}</chNFe><tpEvento>{tp_evento}</tpEvento>"
            "<xEvento>Evento registrado</xEvento>"
            f"<nSeqEvento>{seq}</nSeqEvento>"
            "<dhRegEvento>2026-01-20T09:00:05-03:00</dhRegEvento>"
            "<nProt>135260000000002</nProt></infEvento></retEvento>"
        )
    texto = f'<procEventoNFe xmlns="{NS_NFE}" versao="1.00">{evento_xml}{retorno}</procEventoNFe>'
    return f'<?xml version="1.0" encoding="{declaracao}"?>\n{texto}'.encode()
