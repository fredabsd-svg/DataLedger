"""Gerador de XML SINTÉTICO de NF-e, NFC-e e evento de NF-e — DL-080, frente A.

Os caminhos e a ordem dos elementos seguem a pesquisa do leiaute (docs/projeto/consultas/
2026-10-09-leiaute-nfe.md, seções 1 e 2) e os esquemas PL 010f (leiauteNFe_v4.00.xsd) e PL 010d
(Evento/leiauteEvento_v1.00.xsd). Os XSD baixados não entram no repositório: este gerador
reproduz só o que o leitor lê, com a estrutura mínima para o XML ficar bem formado.

Todo CNPJ, CPF e chave daqui é SINTÉTICO. O dígito verificador é calculado por implementação
PRÓPRIA deste arquivo (`_dv_modulo_11` e `_dv_da_chave`), e NÃO pelo validador do leitor. Assim um
bug comum às duas implementações não passa despercebido: os testes que dependem do DV usam este
cálculo como referência independente.

A assinatura (`ds:Signature`) é um marcador de forma: o leitor não confere assinatura (limite
declarado na pesquisa e no plano). Nada aqui é assinatura válida.
"""

from __future__ import annotations

from xml.sax.saxutils import escape

NS_NFE = "http://www.portalfiscal.inf.br/nfe"
NS_DSIG = "http://www.w3.org/2000/09/xmldsig#"


def _dv_modulo_11(caracteres: str, pesos: list[int]) -> str:
    """Módulo 11 independente: caractere vale `ord(c) - 48`; resto 0 ou 1 dá DV 0."""
    soma = sum((ord(c) - 48) * peso for c, peso in zip(caracteres, pesos, strict=True))
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def _pesos_da_direita(tamanho: int) -> list[int]:
    """Pesos 2 a 9 cíclicos, da direita para a esquerda (MOC 7.0, Tabela 2-1)."""
    return [2 + ((tamanho - 1 - posicao) % 8) for posicao in range(tamanho)]


def dv_da_chave(base43: str) -> str:
    assert len(base43) == 43
    return _dv_modulo_11(base43, _pesos_da_direita(43))


def cnpj_com_dv(base12: str) -> str:
    """CNPJ de 14 posições (12 base + 2 DV). A base pode ter letras (NT Conjunta 2025.001)."""
    assert len(base12) == 12
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    dv1 = _dv_modulo_11(base12, pesos_1)
    dv2 = _dv_modulo_11(base12 + dv1, pesos_2)
    return base12 + dv1 + dv2


def cpf_com_dv(base9: str) -> str:
    assert len(base9) == 9 and base9.isdigit()
    pesos_1 = list(range(10, 1, -1))
    pesos_2 = list(range(11, 1, -1))
    dv1 = _dv_modulo_11(base9, pesos_1)
    dv2 = _dv_modulo_11(base9 + dv1, pesos_2)
    return base9 + dv1 + dv2


def chave_nfe(
    *,
    cuf: str = "35",
    aamm: str = "2601",
    emitente: str = "",
    modelo: str = "55",
    serie: str = "1",
    numero: str = "1",
    tp_emis: str = "1",
    cnf: str = "00000001",
) -> str:
    """Chave de 44 posições (MOC 7.0, Tabela 2-1). `emitente` tem 14 posições (CNPJ alfanumérico,
    ou CPF com zeros à esquerda). Devolve a chave com o DV certo.
    """
    assert len(emitente) == 14, emitente
    base43 = (
        f"{cuf}{aamm}{emitente}{modelo}{int(serie):03d}{int(numero):09d}{tp_emis}{cnf.zfill(8)}"
    )
    assert len(base43) == 43, len(base43)
    return base43 + dv_da_chave(base43)


# CNPJs e CPF sintéticos com DV correto. Os bases foram escolhidos para não coincidir com os
# CNPJ das fixtures de `xml_sinteticos` (11222333000181, 44555666000100) nem com `empresa_b`.
CNPJ_EMITENTE_A = cnpj_com_dv("100200300400")  # numérico
CNPJ_DESTINATARIO_A = cnpj_com_dv("200300400500")  # numérico, segunda empresa do mesmo escritório
CNPJ_ALFANUMERICO = cnpj_com_dv("12ABC34501DE")  # CNPJ alfanumérico (NT Conjunta 2025.001)
CNPJ_DE_FORA = cnpj_com_dv("777888999000")  # cliente de OUTRO escritório, nos testes de isolamento
CNPJ_SEM_CADASTRO = cnpj_com_dv("600700800900")  # não está cadastrado em lugar nenhum
CPF_CLIENTE = cpf_com_dv("123456789")  # pessoa física cliente
CPF_SEM_CADASTRO = cpf_com_dv("987654321")

EMITENTE_PADRAO = ("CNPJ", CNPJ_EMITENTE_A)
DESTINATARIO_PADRAO = ("CNPJ", CNPJ_DESTINATARIO_A)

_TOTAIS_PADRAO = {
    "vBC": "0.00",
    "vICMS": "0.00",
    "vICMSDeson": "0.00",
    "vFCP": "0.00",
    "vBCST": "0.00",
    "vST": "0.00",
    "vFCPST": "0.00",
    "vFCPSTRet": "0.00",
    "vProd": "100.00",
    "vFrete": "0.00",
    "vSeg": "0.00",
    "vDesc": "0.00",
    "vII": "0.00",
    "vIPI": "0.00",
    "vIPIDevol": "0.00",
    "vPIS": "0.00",
    "vCOFINS": "0.00",
    "vOutro": "0.00",
    "vNF": "100.00",
}


def _comentario(tamanho: int) -> str:
    """Comentário XML de `tamanho` bytes de preenchimento. Não tem efeito no leitor, e serve para
    levar uma nota legítima de muitos itens acima de 1 MB, sem inventar conteúdo inválido."""
    return f"<!--{'c' * tamanho}-->" if tamanho else ""


def _pessoa(tag: str, tipo: str, documento: str, nome: str | None) -> str:
    """Bloco `emit`/`dest` com CNPJ, CPF ou idEstrangeiro (xs:choice)."""
    if tipo == "CNPJ":
        doc = f"<CNPJ>{documento}</CNPJ>"
    elif tipo == "CPF":
        doc = f"<CPF>{documento}</CPF>"
    elif tipo == "idEstrangeiro":
        doc = f"<idEstrangeiro>{escape(documento)}</idEstrangeiro>"
    else:
        raise ValueError(f"tipo de participante desconhecido: {tipo!r}")
    nome_xml = f"<xNome>{escape(nome)}</xNome>" if nome is not None else ""
    return f"<{tag}>{doc}{nome_xml}</{tag}>"


def _item(numero: int, *, ibscbs: bool, info_adicional: str, comentario: int = 0) -> str:
    """`det` mínimo: produto e um grupo de ICMS. Sem tributação real."""
    info = f"<infAdProd>{escape(info_adicional)}</infAdProd>" if info_adicional else ""
    ibs = "<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib></IBSCBS>" if ibscbs else ""
    return (
        f'<det nItem="{numero}">'
        f"<prod><cProd>{numero:06d}</cProd><cEAN>SEM GTIN</cEAN>"
        f"<xProd>Produto sintetico {numero}</xProd><NCM>22030000</NCM><CFOP>5102</CFOP>"
        "<uCom>UN</uCom><qCom>1.0000</qCom><vUnCom>100.0000000000</vUnCom>"
        "<vProd>100.00</vProd><cEANTrib>SEM GTIN</cEANTrib><uTrib>UN</uTrib>"
        "<qTrib>1.0000</qTrib><vUnTrib>100.0000000000</vUnTrib>"
        f"</prod>{info}"
        "<imposto><ICMS><ICMSSN102><orig>0</orig><CSOSN>102</CSOSN></ICMSSN102></ICMS>"
        f"{ibs}</imposto>{_comentario(comentario)}</det>"
    )


def _assinatura_marcador() -> str:
    return (
        f'<Signature xmlns="{NS_DSIG}"><SignedInfo/><SignatureValue>'
        "MARCADOR-SINTETICO-NAO-E-ASSINATURA</SignatureValue></Signature>"
    )


def xml_nfe(
    *,
    modelo: str = "55",
    versao: str = "4.00",
    versao_raiz: str | None = None,
    chave: str | None = None,
    emitente: tuple[str, str] = EMITENTE_PADRAO,
    emitente_nome: str | None = "Emitente Sintetico Ltda",
    crt: str | None = "3",
    destinatario: tuple[str, str] | None = DESTINATARIO_PADRAO,
    destinatario_nome: str | None = "Destinatario Sintetico Ltda",
    tp_nf: str = "1",
    fin_nfe: str = "1",
    tp_nf_debito: str | None = None,
    tp_nf_credito: str | None = None,
    id_dest: str = "1",
    serie: str = "1",
    numero: str = "1",
    dh_emi: str = "2026-01-15T10:00:00-03:00",
    totais: dict[str, str | None] | None = None,
    itens: int = 1,
    ibscbs_item: bool = False,
    ibscbs_total: bool = False,
    info_adicional_item: str = "",
    raiz: str = "nfeProc",
    incluir_protocolo: bool = True,
    c_stat: str = "100",
    chave_protocolo: str | None = None,
    dh_recbto: str = "2026-01-15T10:01:00-03:00",
    n_prot: str | None = "135260000000001",
    id_nfe: str | None = None,
    padding_comentario: int = 0,
    declaracao: str | None = "UTF-8",
    tp_amb: str | None = "1",
    autxml_cnpj: str | None = None,
    transporta_cnpj: str | None = None,
    inf_adicional: str | None = None,
    c_uf_ide: str | None = None,
    comentario_por_item: int = 0,
) -> bytes:
    """NF-e (`nfeProc`) ou NFC-e sintética. Os padrões formam uma nota autorizada e válida.

    `chave`: se omitida, é montada com o emitente, série, número e modelo deste XML. Passar outra
    chave cria a inconsistência de propósito (ver os testes de `ide`).
    `totais`: sobrescreve valores do ICMSTot; `None` como valor REMOVE o elemento.
    `padding_comentario`: bytes de comentário XML, só para testar o limite de tamanho (o comentário
    não muda o conteúdo lido).
    `tp_amb=None` omite ide/tpAmb (o XSD o exige: a recusa é testada com ele ausente).

    ATENÇÃO: este gerador NÃO valida contra o XSD (faltam indTot, pag, indIEDest, endereços, e a
    assinatura é um marcador). O corpus validado pelo XSD é `xml_nfe_xsd_dl080`.
    """
    tipo_emit, documento_emit = emitente
    if chave is None:
        chave = chave_nfe(
            emitente=documento_emit.zfill(14) if tipo_emit == "CPF" else documento_emit,
            modelo=modelo,
            serie=serie,
            numero=numero,
        )
    if chave_protocolo is None:
        chave_protocolo = chave
    if id_nfe is None:
        id_nfe = f"NFe{chave}"

    tp_debito_xml = f"<tpNFDebito>{tp_nf_debito}</tpNFDebito>" if tp_nf_debito else ""
    tp_credito_xml = f"<tpNFCredito>{tp_nf_credito}</tpNFCredito>" if tp_nf_credito else ""
    dest_xml = ""
    if destinatario is not None:
        tipo_dest, documento_dest = destinatario
        dest_xml = _pessoa("dest", tipo_dest, documento_dest, destinatario_nome)

    emit_xml = _pessoa("emit", tipo_emit, documento_emit, emitente_nome)
    crt_xml = f"<CRT>{crt}</CRT>" if crt is not None else ""
    # `emit` recebe o CRT dentro do próprio bloco (leiauteNFe_v4.00.xsd:601).
    emit_xml = emit_xml.replace("</emit>", f"{crt_xml}</emit>")

    valores = dict(_TOTAIS_PADRAO)
    if totais:
        for campo, valor in totais.items():
            if valor is None:
                valores.pop(campo, None)
            else:
                valores[campo] = valor
    icms_tot = "".join(f"<{campo}>{valor}</{campo}>" for campo, valor in valores.items())
    ibs_total_xml = "<IBSCBSTot><vBCIBSCBS>0.00</vBCIBSCBS></IBSCBSTot>" if ibscbs_total else ""

    itens_xml = "".join(
        _item(
            n,
            ibscbs=ibscbs_item,
            info_adicional=info_adicional_item,
            comentario=comentario_por_item,
        )
        for n in range(1, itens + 1)
    )
    padding = f"<!-- {'p' * padding_comentario} -->" if padding_comentario else ""

    tp_amb_xml = f"<tpAmb>{tp_amb}</tpAmb>" if tp_amb is not None else ""
    ide_xml = (
        "<ide>"
        f"<cUF>{c_uf_ide or chave[:2]}</cUF><cNF>{chave[35:43]}</cNF><natOp>Venda sintetica</natOp>"
        f"<mod>{modelo}</mod><serie>{serie}</serie><nNF>{numero}</nNF>"
        f"<dhEmi>{dh_emi}</dhEmi><tpNF>{tp_nf}</tpNF><idDest>{id_dest}</idDest>"
        "<cMunFG>3550308</cMunFG><tpImp>1</tpImp><tpEmis>1</tpEmis>"
        f"<cDV>{chave[43]}</cDV>{tp_amb_xml}<finNFe>{fin_nfe}</finNFe>"
        f"{tp_debito_xml}{tp_credito_xml}"
        "<indFinal>1</indFinal><indPres>1</indPres><procEmi>0</procEmi>"
        "<verProc>sintetico-dl080</verProc></ide>"
    )
    total_xml = f"<total><ICMSTot>{icms_tot}</ICMSTot>{ibs_total_xml}</total>"
    # Participantes que NÃO são partes da operação (autXML, transportador, informação adicional).
    # A recepção não pode ligar empresa por nenhum deles (pesquisa, seção 5).
    autxml_xml = f"<autXML><CNPJ>{autxml_cnpj}</CNPJ></autXML>" if autxml_cnpj else ""
    transporta_xml = (
        f"<transporta><CNPJ>{transporta_cnpj}</CNPJ></transporta>" if transporta_cnpj else ""
    )
    info_xml = (
        f"<infAdic><infCpl>{escape(inf_adicional)}</infCpl></infAdic>" if inf_adicional else ""
    )
    inf_nfe = (
        f'<infNFe Id="{id_nfe}" versao="{versao}">'
        f"{ide_xml}{emit_xml}{dest_xml}{autxml_xml}{itens_xml}{total_xml}"
        f"<transp><modFrete>9</modFrete>{transporta_xml}</transp>{info_xml}"
        "</infNFe>"
    )

    assinatura = _assinatura_marcador()
    if raiz == "NFe":
        # `NFe` pura: sem `versao` no elemento raiz (o atributo fica em infNFe) e sem protNFe.
        texto = f'<NFe xmlns="{NS_NFE}">{padding}{inf_nfe}{assinatura}</NFe>'
    else:
        protocolo = (
            _protocolo(chave_protocolo, c_stat, dh_recbto, n_prot) if incluir_protocolo else ""
        )
        versao_xml = f' versao="{versao_raiz or versao}"'
        texto = (
            f'<{raiz} xmlns="{NS_NFE}"{versao_xml}>{padding}'
            f"<NFe>{inf_nfe}{assinatura}</NFe>{protocolo}</{raiz}>"
        )
    if declaracao is not None:
        texto = f'<?xml version="1.0" encoding="{declaracao}"?>\n' + texto
    return texto.encode("utf-8")


def _protocolo(chave: str, c_stat: str, dh_recbto: str, n_prot: str | None) -> str:
    nprot_xml = f"<nProt>{n_prot}</nProt>" if n_prot else ""
    return (
        '<protNFe versao="4.00"><infProt><tpAmb>1</tpAmb><verAplic>SVRS_SINTETICO</verAplic>'
        f"<chNFe>{chave}</chNFe><dhRecbto>{dh_recbto}</dhRecbto>{nprot_xml}"
        "<digVal>MARCADOR-SINTETICO</digVal>"
        f"<cStat>{c_stat}</cStat><xMotivo>Autorizado o uso da NF-e (sintetico)</xMotivo>"
        "</infProt></protNFe>"
    )


def xml_raiz_generica(raiz: str, *, versao: str | None = None) -> bytes:
    """Raiz do namespace da NF-e que NÃO é nota nem evento (enviNFe, procInutNFe, resNFe...)."""
    atributo = f' versao="{versao}"' if versao is not None else ""
    corpo = f'<{raiz} xmlns="{NS_NFE}"{atributo}><infSem>conteudo sintetico</infSem></{raiz}>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n' + corpo).encode("utf-8")


def proc_evento_xml(
    *,
    tp_evento: str = "110111",
    n_seq: int = 1,
    chave: str | None = None,
    autor: tuple[str, str] = EMITENTE_PADRAO,
    dh_evento: str = "2026-01-20T09:00:00-03:00",
    c_stat: str | None = "135",
    c_stat_retorno_sem_codigo: bool = False,
    chave_retorno: str | None = None,
    id_evento: str | None = None,
    versao: str = "1.00",
    declaracao: str | None = "UTF-8",
    tp_amb: str | None = "1",
    tp_amb_retorno: str | None = "1",
    tp_evento_retorno: str | None = None,
    n_seq_retorno: int | None = None,
) -> bytes:
    """`procEventoNFe` sintético (PL 010d, leiauteEvento_v1.00.xsd).

    `c_stat=None` omite o `retEvento` inteiro (evento sem retorno).
    `c_stat_retorno_sem_codigo=True` deixa o retorno sem `cStat`.
    `chave_retorno` troca a chave do retorno, para o caso de outra nota.
    `tp_amb` e `tp_amb_retorno`: ambiente do evento e do retorno; `None` omite o elemento.
    `tp_evento_retorno` e `n_seq_retorno`: tipo e sequência do retorno, quando diferentes do evento.
    """
    if chave is None:
        chave = chave_nfe(emitente=CNPJ_EMITENTE_A)
    if id_evento is None:
        id_evento = f"ID{tp_evento}{chave}{n_seq:02d}"
    tipo_autor, documento_autor = autor
    if tipo_autor == "CNPJ":
        autor_xml = f"<CNPJ>{documento_autor}</CNPJ>"
    else:
        autor_xml = f"<CPF>{documento_autor}</CPF>"

    tp_amb_evento_xml = f"<tpAmb>{tp_amb}</tpAmb>" if tp_amb is not None else ""
    evento_xml = (
        f'<evento versao="{versao}"><infEvento Id="{id_evento}">'
        f"<cOrgao>35</cOrgao>{tp_amb_evento_xml}{autor_xml}"
        f"<chNFe>{chave}</chNFe><dhEvento>{dh_evento}</dhEvento>"
        f"<tpEvento>{tp_evento}</tpEvento><nSeqEvento>{n_seq}</nSeqEvento>"
        "<verEvento>1.00</verEvento>"
        '<detEvento versao="1.00"><descEvento>Cancelamento sintetico</descEvento>'
        "<nProt>135260000000001</nProt><xJust>Justificativa sintetica</xJust></detEvento>"
        f"</infEvento>{_assinatura_marcador()}</evento>"
    )

    ret_xml = ""
    if c_stat is not None:
        codigo_xml = "" if c_stat_retorno_sem_codigo else f"<cStat>{c_stat}</cStat>"
        chave_ret = chave if chave_retorno is None else chave_retorno
        tp_ret = tp_evento if tp_evento_retorno is None else tp_evento_retorno
        seq_ret = n_seq if n_seq_retorno is None else n_seq_retorno
        tp_amb_ret_xml = f"<tpAmb>{tp_amb_retorno}</tpAmb>" if tp_amb_retorno is not None else ""
        ret_xml = (
            f'<retEvento versao="{versao}"><infEvento Id="ID{c_stat}SINTETICO">'
            f"{tp_amb_ret_xml}<verAplic>SVRS_SINTETICO</verAplic><cOrgao>35</cOrgao>"
            f"{codigo_xml}<xMotivo>Evento registrado (sintetico)</xMotivo>"
            f"<chNFe>{chave_ret}</chNFe><tpEvento>{tp_ret}</tpEvento>"
            f"<xEvento>Cancelamento sintetico</xEvento><nSeqEvento>{seq_ret}</nSeqEvento>"
            "<dhRegEvento>2026-01-20T09:00:05-03:00</dhRegEvento>"
            "<nProt>135260000000002</nProt></infEvento></retEvento>"
        )

    texto = (
        f'<procEventoNFe xmlns="{NS_NFE}" versao="{versao}">{evento_xml}{ret_xml}</procEventoNFe>'
    )
    if declaracao is not None:
        texto = f'<?xml version="1.0" encoding="{declaracao}"?>\n' + texto
    return texto.encode("utf-8")
