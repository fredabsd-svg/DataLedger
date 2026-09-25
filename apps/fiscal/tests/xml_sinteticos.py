"""Geradores de XML SINTÉTICO de NFS-e nacional e de evento, para os testes
da recepção (DL-010, fatia 1). Nenhum arquivo do acervo real do Fred entra
no repositório (regra do plano da etapa) — tudo aqui é montado a partir do
leiaute confirmado nos XSD oficiais (ver cabeçalho de
`apps/fiscal/leitor.py` para a fonte).

Os geradores incluem só os elementos que `apps.fiscal.leitor` efetivamente
lê (mais um mínimo de estrutura para o XML ficar bem formado) — não é um
gerador exaustivo de todo o leiaute, é o suficiente para exercitar nosso
leitor com XMLs estruturalmente corretos nos caminhos que importam.
"""

from __future__ import annotations

import io
import zipfile
from xml.sax.saxutils import escape

NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"
NS_NFE = "http://www.portalfiscal.inf.br/nfe"

CNPJ_PRESTADOR_PADRAO = "11222333000181"
CNPJ_TOMADOR_PADRAO = "44555666000100"
# CNPJ com zero à esquerda (RC-75 mediu 553 casos no acervo real) — um
# CNPJ alfanumérico-canônico válido, mas usado aqui só como TEXTO: o
# leitor nunca deve convertê-lo para número.
CNPJ_COM_ZERO_A_ESQUERDA = "01234567000121"


def identificador_nfse(
    sufixo: int = 1,
    *,
    municipio: str = "3550308",
    ambiente: str = "1",
    tipo_inscricao: str = "2",
    inscricao_federal: str = "11222333000181",
    competencia: str = "2401",
    dv: str = "0",
) -> str:
    """TSIdNFSe: "NFS" + 50 dígitos = município(7) + ambiente(1) +
    tipo de inscrição(1) + inscrição federal(14) + número(13) + ano-mês(4) +
    código numérico(9) + DV(1). `sufixo` varia o "número" e o "código
    numérico" para gerar identificadores distintos e determinísticos entre
    testes."""
    numero = f"{sufixo:013d}"
    codigo_numerico = f"{sufixo:09d}"
    base = (
        f"{municipio}{ambiente}{tipo_inscricao}{inscricao_federal}"
        f"{numero}{competencia}{codigo_numerico}{dv}"
    )
    assert len(base) == 50, f"base do Id da NFS-e com tamanho errado: {len(base)}"
    return "NFS" + base


def chave_nfse_de(identificador: str) -> str:
    """A chave de 50 dígitos SEM o prefixo "NFS" — o formato que
    `chNFSe` usa dentro do evento (TSChaveNFSe)."""
    assert identificador.startswith("NFS")
    return identificador[3:]


def identificador_evento(chave_nfse: str, codigo: str, numero_pedido: str = "001") -> str:
    """TSIdEvento: "EVT" + chave(50) + tipo do evento(6) + nPedRegEvento(3)."""
    tipo_evento = codigo[1:]  # remove o "e" inicial, sobram os 6 dígitos
    assert len(tipo_evento) == 6
    assert len(numero_pedido) == 3
    return "EVT" + chave_nfse + tipo_evento + numero_pedido


def _bloco_pessoa(tag: str, *, tipo: str | None, documento: str = "", nome: str = "") -> str:
    if tipo is None:
        return ""
    if tipo == "CNPJ":
        doc_el = f"<CNPJ>{documento}</CNPJ>"
    elif tipo == "CPF":
        doc_el = f"<CPF>{documento}</CPF>"
    elif tipo == "NIF":
        doc_el = f"<NIF>{documento}</NIF>"
    elif tipo == "nao_informado":
        doc_el = f"<cNaoNIF>{documento or '0'}</cNaoNIF>"
    else:
        raise ValueError(f"tipo de pessoa desconhecido: {tipo!r}")
    nome_el = f"<xNome>{escape(nome)}</xNome>" if nome else ""
    return f"<{tag}>{doc_el}{nome_el}</{tag}>"


def _finalizar(xml_texto: str, *, declaracao: str | None, minificado: bool, crlf: bool) -> bytes:
    if minificado:
        import re

        xml_texto = re.sub(r">\s+<", "><", xml_texto.strip())
    prolog = "" if declaracao is None else f'<?xml version="1.0" encoding="{declaracao}"?>\n'
    texto_final = prolog + xml_texto
    if crlf:
        texto_final = texto_final.replace("\n", "\r\n")
    return texto_final.encode("utf-8")


def xml_nfse(
    *,
    versao: str = "1.01",
    identificador: str | None = None,
    numero: str = "1",
    dh_emi: str = "2024-01-15T10:00:00-03:00",
    d_compet: str = "2024-01-15",
    prestador_tipo: str | None = "CNPJ",
    prestador_documento: str = CNPJ_PRESTADOR_PADRAO,
    prestador_nome: str = "Prestador Teste Ltda",
    incluir_tomador: bool = True,
    tomador_tipo: str | None = "CNPJ",
    tomador_documento: str = CNPJ_TOMADOR_PADRAO,
    tomador_nome: str = "Tomador Teste Ltda",
    v_serv: str = "100.00",
    v_liq: str = "95.00",
    tp_ret_issqn: str = "1",
    declaracao: str | None = "UTF-8",
    minificado: bool = False,
    crlf: bool = False,
) -> bytes:
    """NFS-e nacional sintética. Todos os parâmetros têm um valor padrão
    válido; sobrescreva só o que o cenário do teste precisa variar."""
    if identificador is None:
        identificador = identificador_nfse()

    toma_xml = ""
    if incluir_tomador:
        toma_xml = _bloco_pessoa(
            "toma", tipo=tomador_tipo, documento=tomador_documento, nome=tomador_nome
        )
    emit_xml = _bloco_pessoa(
        "emit", tipo=prestador_tipo, documento=prestador_documento, nome=prestador_nome
    )

    corpo = f"""<NFSe xmlns="{NS_NFSE}" versao="{versao}">
  <infNFSe Id="{identificador}">
    <nNFSe>{numero}</nNFSe>
    {emit_xml}
    <valores>
      <vLiq>{v_liq}</vLiq>
    </valores>
    <DPS versao="{versao}">
      <infDPS Id="DPS{"0" * 42}">
        <dhEmi>{dh_emi}</dhEmi>
        <dCompet>{d_compet}</dCompet>
        {toma_xml}
        <valores>
          <vServPrest>
            <vServ>{v_serv}</vServ>
          </vServPrest>
          <trib>
            <tribMun>
              <tpRetISSQN>{tp_ret_issqn}</tpRetISSQN>
            </tribMun>
          </trib>
        </valores>
      </infDPS>
    </DPS>
  </infNFSe>
</NFSe>"""
    return _finalizar(corpo, declaracao=declaracao, minificado=minificado, crlf=crlf)


def xml_evento(
    *,
    versao: str = "1.01",
    chave_nfse: str | None = None,
    codigo: str = "e101101",
    numero_pedido: str = "001",
    dh_evento: str = "2024-01-20T10:00:00-03:00",
    autor_tipo: str | None = "CNPJ",
    autor_documento: str = CNPJ_PRESTADOR_PADRAO,
    identificador: str | None = None,
    declaracao: str | None = "UTF-8",
    minificado: bool = False,
    crlf: bool = False,
) -> bytes:
    """Evento de NFS-e sintético (cancelamento por padrão)."""
    if chave_nfse is None:
        chave_nfse = chave_nfse_de(identificador_nfse())
    if identificador is None:
        identificador = identificador_evento(chave_nfse, codigo, numero_pedido)

    autor_xml = ""
    if autor_tipo == "CNPJ":
        autor_xml = f"<CNPJAutor>{autor_documento}</CNPJAutor>"
    elif autor_tipo == "CPF":
        autor_xml = f"<CPFAutor>{autor_documento}</CPFAutor>"

    corpo = f"""<evento xmlns="{NS_NFSE}" versao="{versao}">
  <infEvento Id="{identificador}">
    <pedRegEvento versao="{versao}">
      <infPedReg Id="PRE{"0" * 56}">
        <dhEvento>{dh_evento}</dhEvento>
        {autor_xml}
        <chNFSe>{chave_nfse}</chNFSe>
        <{codigo}>
          <xDesc>Evento de teste</xDesc>
        </{codigo}>
      </infPedReg>
    </pedRegEvento>
  </infEvento>
</evento>"""
    return _finalizar(corpo, declaracao=declaracao, minificado=minificado, crlf=crlf)


def xml_nfe_minimo() -> bytes:
    """NF-e sintética mínima — só para provar que o namespace da NF-e é
    reconhecido e recusado (RC-71/critério 18), nunca processado."""
    corpo = f"""<nfeProc xmlns="{NS_NFE}" versao="4.00">
  <NFe>
    <infNFe Id="NFe00000000000000000000000000000000000000">
      <emit><CNPJ>{CNPJ_PRESTADOR_PADRAO}</CNPJ></emit>
    </infNFe>
  </NFe>
</nfeProc>"""
    return _finalizar(corpo, declaracao="UTF-8", minificado=False, crlf=False)


def zip_de(itens) -> bytes:
    """Monta um ZIP em memória a partir de `{nome: bytes}` ou
    `[(nome, bytes), ...]`."""
    buffer = io.BytesIO()
    pares = itens.items() if isinstance(itens, dict) else itens
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        for nome, conteudo in pares:
            arquivo_zip.writestr(nome, conteudo)
    return buffer.getvalue()
