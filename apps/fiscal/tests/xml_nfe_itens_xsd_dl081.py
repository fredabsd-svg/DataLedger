"""Corpus de ITENS da NF-e, válido contra o XSD — DL-081, correção da rodada 1 (A1).

A rodada 1 aceitou fixtures que o XSD não aceita (ISSQN junto de ICMS, IPI sem `cEnq`), e por isso
o leitor errado passava. Aqui cada `det` é montado com a ordem e os grupos do
`leiauteNFe_v4.00.xsd` do PL 010f (linhas citadas em cada função), e a nota inteira sai com a
mesma estrutura do corpus da DL-080 (`xml_nfe_xsd_dl080`), que já foi validada por `xmllint`.

Casos que a rodada 1 recusava por erro do próprio leitor:
- IPI com `cEnq` (TIpi, linha 7579): `cEnq` vem antes do grupo IPITrib ou IPINT.
- item só com ISSQN, CFOP 5.933 (choice do `imposto`, linha 2117): sem grupo ICMS.
- `imposto` sem nenhum grupo da choice, ou só com PIS e Cofins: o choice inteiro é opcional.

Todo CNPJ e chave é SINTÉTICO (saem de `xml_nfe_xsd_dl080`). Os valores de um teste são escritos
no próprio teste: este módulo monta XML, não calcula total.
"""

from apps.fiscal.tests import xml_nfe_xsd_dl080 as corpus

NS_NFE = corpus.NS_NFE

CNPJ_EMITENTE = corpus.cnpj_valido("100200300400")
CNPJ_DESTINATARIO = corpus.cnpj_valido("200300400500")
CNPJ_PRODUTOR = corpus.cnpj_valido("300400500600")

# Grupos de tributo reutilizados. PIS e Cofins são opcionais no `imposto` (linhas 4573 e 4823);
# quando aparecem, o XSD exige o grupo CST (PISNT, COFINSNT).
ICMS_SN102 = "<ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS>"
PIS_NT = "<PIS><PISNT><CST>07</CST></PISNT></PIS>"
COFINS_NT = "<COFINS><COFINSNT><CST>07</CST></COFINSNT></COFINS>"

# IPITrib (linha 7623): CST, depois vBC e pIPI (ou qUnid e vUnid), e vIPI.
IPI_TRIB_50 = "<IPITrib><CST>50</CST><vBC>100.00</vBC><pIPI>5.00</pIPI><vIPI>5.00</vIPI></IPITrib>"

# IPI com `cEnq` (linha 7611), obrigatório antes do grupo. Este é o caso que a rodada 1 recusava.
IPI_COM_CENQ = f"<IPI><cEnq>999</cEnq>{IPI_TRIB_50}</IPI>"

# IPINT (linha 7678): só o CST. O IPI de NT não tem vIPI, e o leitor devolve None.
IPI_NT_COM_CENQ = "<IPI><cEnq>999</cEnq><IPINT><CST>53</CST></IPINT></IPI>"

# TIpi com CNPJProd, cSelo e qSelo antes do cEnq (linhas 7579 a 7611): são ignorados pelo leitor.
IPI_COM_OPCIONAIS = (
    f"<IPI><CNPJProd>{CNPJ_PRODUTOR}</CNPJProd><cSelo>SELO-SINTETICO</cSelo>"
    f"<qSelo>10</qSelo><cEnq>999</cEnq>{IPI_TRIB_50}</IPI>"
)

# ISSQN (linha 4443): vBC, vAliq, vISSQN, cMunFG, cListServ, indISS e indIncentivo são
# obrigatórios; os demais são opcionais. Código de município sintético.
ISSQN_SERVICO = (
    "<ISSQN><vBC>100.00</vBC><vAliq>5.00</vAliq><vISSQN>5.00</vISSQN>"
    "<cMunFG>3550308</cMunFG><cListServ>01.07</cListServ><indISS>1</indISS>"
    "<indIncentivo>2</indIncentivo></ISSQN>"
)


# ICMS-ST retido no Simples, CSOSN 500 (ICMSSN500, leiauteNFe_v4.00.xsd:4197 a 4212): vBCSTRet,
# pST e vICMSSTRet são obrigatórios nesse grupo. O caso é o de `test_grupo_icms_csosn500...`.
ICMS_SN500_ST = (
    "<ICMS><ICMSSN500><orig>0</orig><CSOSN>500</CSOSN>"
    "<vBCSTRet>800.00</vBCSTRet><pST>12.00</pST><vICMSSTRet>96.00</vICMSSTRet></ICMSSN500></ICMS>"
)

# Item com os grupos de tributo que o leitor lê, na ordem do XSD: ICMS00 com base e alíquota, II,
# IPI com cEnq e IPITrib, PIS e Cofins por alíquota. O ICMSUFDest fica de fora (não é preciso aqui).
ICMS_00 = (
    "<ICMS><ICMS00><orig>0</orig><CST>00</CST><modBC>3</modBC><vBC>100.00</vBC>"
    "<pICMS>18.00</pICMS><vICMS>18.00</vICMS></ICMS00></ICMS>"
)
PIS_ALIQ = (
    "<PIS><PISAliq><CST>01</CST><vBC>100.00</vBC><pPIS>1.65</pPIS><vPIS>1.65</vPIS></PISAliq></PIS>"
)
COFINS_ALIQ = (
    "<COFINS><COFINSAliq><CST>01</CST><vBC>100.00</vBC><pCOFINS>7.60</pCOFINS>"
    "<vCOFINS>7.60</vCOFINS></COFINSAliq></COFINS>"
)
II_XML = "<II><vBC>100.00</vBC><vDespAdu>0.00</vDespAdu><vII>3.00</vII><vIOF>0.00</vIOF></II>"


def prod(n: int, *, cfop: str = "5102", vprod: str = "100.00", ind_tot: str = "1") -> str:
    """`prod` (leiauteNFe_v4.00.xsd:867 em diante) com a ordem dos campos do XSD."""
    return (
        f"<prod><cProd>{n:06d}</cProd><cEAN>SEM GTIN</cEAN>"
        f"<xProd>Produto sintetico {n}</xProd><NCM>22030000</NCM>"
        f"<CFOP>{cfop}</CFOP><uCom>UN</uCom><qCom>1.0000</qCom>"
        f"<vUnCom>{vprod}</vUnCom><vProd>{vprod}</vProd><cEANTrib>SEM GTIN</cEANTrib>"
        f"<uTrib>UN</uTrib><qTrib>1.0000</qTrib><vUnTrib>{vprod}</vUnTrib>"
        f"<indTot>{ind_tot}</indTot></prod>"
    )


def det(n: int, imposto: str, *, cfop: str = "5102", vprod: str = "100.00", ind_tot: str = "1"):
    """Um `det` com o conteúdo de `imposto` dado (já na ordem do XSD, pelo chamador)."""
    return (
        f'<det nItem="{n}">{prod(n, cfop=cfop, vprod=vprod, ind_tot=ind_tot)}'
        f"<imposto>{imposto}</imposto></det>"
    )


def nfe_com_itens(dets: list[str], *, vnf: str = "100.00") -> bytes:
    """`nfeProc` sintética de NF-e (modelo 55) com os `det` dados, validada contra o XSD.

    `vNF` é o que o teste escreveu; não é calculado aqui. Os demais totais são os do corpus.
    """
    chave = corpus.chave_valida(doc14=CNPJ_EMITENTE, mod="55", serie="1", nnf="1")
    valores = dict(corpus._TOTAIS)
    valores["vNF"] = vnf
    icms_tot = "".join(f"<{campo}>{valor}</{campo}>" for campo, valor in valores.items())
    ide = (
        f"<ide><cUF>{chave[:2]}</cUF><cNF>{chave[35:43]}</cNF><natOp>Venda sintetica</natOp>"
        "<mod>55</mod><serie>1</serie><nNF>1</nNF>"
        "<dhEmi>2026-01-15T10:00:00-03:00</dhEmi><tpNF>1</tpNF><idDest>1</idDest>"
        "<cMunFG>3550308</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis>"
        f"<cDV>{chave[43]}</cDV><tpAmb>1</tpAmb><finNFe>1</finNFe>"
        "<indFinal>1</indFinal><indPres>1</indPres><procEmi>0</procEmi>"
        "<verProc>sintetico-dl081-xsd</verProc></ide>"
    )
    emit = corpus._emitente(CNPJ_EMITENTE, "CNPJ", "Emitente Sintetico Ltda", "3")
    dest = corpus._destinatario("CNPJ", CNPJ_DESTINATARIO, "Destinatario Sintetico Ltda")
    pag = "<pag><detPag><tPag>01</tPag><vPag>100.00</vPag></detPag></pag>"
    inf = (
        f'<infNFe versao="4.00" Id="NFe{chave}">{ide}{emit}{dest}{"".join(dets)}'
        f"<total><ICMSTot>{icms_tot}</ICMSTot></total>"
        f"<transp><modFrete>9</modFrete></transp>{pag}</infNFe>"
    )
    protocolo = (
        '<protNFe versao="4.00"><infProt><tpAmb>1</tpAmb><verAplic>SVRS</verAplic>'
        f"<chNFe>{chave}</chNFe><dhRecbto>2026-01-15T10:01:00-03:00</dhRecbto>"
        "<nProt>135260000000001</nProt>"
        "<digVal>ZGRkZGRkZGRkZGRkZGRkZGRkZGQ=</digVal>"
        "<cStat>100</cStat><xMotivo>Autorizado o uso da NF-e (sintetico)</xMotivo>"
        "</infProt></protNFe>"
    )
    texto = (
        f'<nfeProc xmlns="{NS_NFE}" versao="4.00"><NFe xmlns="{NS_NFE}">{inf}'
        f"{corpus._assinatura()}</NFe>{protocolo}</nfeProc>"
    )
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{texto}'.encode()
