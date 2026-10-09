"""Leitura segura de NF-e (modelo 55), NFC-e (modelo 65) e de evento de NF-e — DL-080, frente A.

Fonte dos caminhos, tipos e padrões citados nos comentários: pacote de esquemas
PL 010f (leiauteNFe_v4.00.xsd, tiposBasico_v4.00.xsd, DFeTiposBasicos_v1.00.xsd),
pacote PL 010d (Evento/leiauteEvento_v1.00.xsd) e pesquisa do leiaute de
09/10/2026 (docs/projeto/consultas/2026-10-09-leiaute-nfe.md). Os XSD baixados
são documento de terceiro e NÃO entram no repositório: os números de linha
citados aqui servem para reconferência, não para carregar esquema em runtime.

Este módulo não grava nada no banco e não importa `apps.fiscal.leitor`: o
leitor da NFS-e importa ESTE módulo para despachar o namespace da NF-e, e a
importação de volta criaria um ciclo. A recusa daqui é `RecusaNFe`, que
`apps.fiscal.leitor.ler_arquivo` converte em `ArquivoRecusado`.

Ordem das conferências, que é a ordem da recusa (a primeira que falha manda):
raiz e versão, protocolo de autorização, status do protocolo, `@Id` e DV da
chave, consistência entre a chave e `ide`, participantes, valores e itens.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.empresas.validators import _calcular_digito_verificador

# Namespace único da NF-e, que não varia por versão (pesquisa, seção 6).
NS_NFE = "http://www.portalfiscal.inf.br/nfe"
_NS = {"n": NS_NFE}

VERSAO_SUPORTADA = "4.00"  # TVerNFe, leiauteNFe_v4.00.xsd:7561-7569 (pesquisa, seção 1)
_VERSOES_LEGADAS = frozenset({"1.10", "2.00", "3.00", "3.10"})  # HI-110; nomeadas uma a uma
VERSAO_EVENTO_SUPORTADA = "1.00"  # procEventoNFe/@versao, PL 010d, EVT:350-367

# Status do protocolo que tornam a nota autorizada (HI-109, MOC 7.0).
_CSTAT_AUTORIZADA = frozenset({"100", "150"})
# Denegações: a nota existe na base da SEFAZ, mas o uso como documento fiscal é
# vedado (MOC 7.0, MOC:4095-4108). Recusadas, nunca gravadas (HI-109).
_CSTAT_DENEGADA = frozenset({"110", "301", "302", "303"})

# Chave de acesso, TChNFe (tiposBasico_v4.00.xsd:49-58): 6 dígitos, 12 caracteres
# A-Z/0-9 (CNPJ alfanumérico, NT Conjunta 2025.001) e 26 dígitos.
_FORMATO_CHAVE = re.compile(r"[0-9]{6}[0-9A-Z]{12}[0-9]{26}")
# infNFe/@Id: "NFe" + chave (leiauteNFe_v4.00.xsd:6625-6634).
_FORMATO_ID_NFE = re.compile(r"NFe([0-9]{6}[0-9A-Z]{12}[0-9]{26})")
# evento/infEvento/@Id: "ID" + tpEvento(6) + chave(44) + nSeqEvento(2) = 54 posições.
# A pesquisa escreveu 52; a conta do próprio padrão dá 54 (leiauteEvento_v1.00.xsd:136).
_FORMATO_ID_EVENTO = re.compile(r"ID[0-9]{12}[0-9A-Z]{12}[0-9]{28}")
# TCnpj (tiposBasico_v4.00.xsd:89-98) e TCpf (:119-127).
_FORMATO_CNPJ = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_FORMATO_CPF = re.compile(r"[0-9]{11}")
# TDec_1302 (tiposBasico_v4.00.xsd:301-307): sem sinal, até 13 inteiros, 2 casas.
# Sem espaço e sem vírgula: o XSD não admite nem um nem outro.
_FORMATO_DECIMAL = re.compile(r"0|0\.[0-9]{2}|[1-9][0-9]{0,12}(\.[0-9]{2})?")
# TStat (tiposBasico_v4.00.xsd:79-88, e o mesmo tipo no PL 010d): 3 ou 4 dígitos. Vale para o cStat
# do protocolo e para o cStat do retorno do evento. O campo do banco tem 4 posições por isso.
_FORMATO_CSTAT = re.compile(r"[0-9]{3,4}")
# TProt (tiposBasico_v4.00.xsd:59-67): 15 ou 17 dígitos.
_FORMATO_N_PROT = re.compile(r"[0-9]{15}|[0-9]{17}")
# nNF (tiposBasico_v4.00.xsd:369-377) e serie (:378-384).
_FORMATO_NNF = re.compile(r"[1-9][0-9]{0,8}")
_FORMATO_SERIE = re.compile(r"0|[1-9][0-9]{0,2}")
# nSeqEvento (pesquisa, seção 2: EVT:61-68).
_FORMATO_NSEQ_EVENTO = re.compile(r"[1-9][0-9]{0,1}")
# TDateTimeUTC (tiposBasico_v4.00.xsd:546-552): AAAA-MM-DDThh:mm:ssTZD com ANO 20xx
# (XSD:552, `20[0-9][0-9]`) e fuso em hora cheia, de -00:00 a -11:00 e de +00:00 a +12:00.
# Sem "Z". A expressão cobre forma, ano e fuso. O calendário (31 de abril, 29 de fevereiro de
# ano não bissexto) fica com `datetime.fromisoformat` em `_data_hora`. Ano fora de 20xx
# (0001, 1999, 9999) é recusado: a data gravada com ano absurdo derrubava a lista e o detalhe
# com erro de servidor (auditoria DL-080, rodada 1, A1).
# O XSD também aceita vírgula como sinal do fuso (`[\-,\+]`). Não se replica: vírgula não é
# fuso, e a recusa mais estreita que o XSD é deliberada.
_FORMATO_DATA_HORA = re.compile(
    r"20[0-9]{2}-[0-9]{2}-[0-9]{2}T(2[0-3]|[01][0-9]):[0-5][0-9]:[0-5][0-9]"
    r"(-(0[0-9]|10|11):00|\+(0[0-9]|1[0-2]):00)"
)
# TAmb (tiposBasico_v4.00.xsd:458): 1 produção, 2 homologação. Obrigatório em ide, em
# infEvento e no retorno do evento (XSD sem minOccurs). Ausente é recusa, nunca presunção.
_DOMINIO_TP_AMB = frozenset({"1", "2"})
# Séries 890 a 919: notas avulsas emitidas no site do Fisco (NFA-e). A chave leva o CNPJ ou o
# CPF da SEFAZ, e não o do emitente (pesquisa, seção 3, MOC:1047-1053; a faixa 900-919 é
# SEFAZ). Fora dessa faixa, o CNPJ/CPF da chave tem de ser o do emitente. A faixa 920-969 é
# de aplicativo do contribuinte com CPF: a chave leva o CPF da própria empresa, e a conferência
# vale. A pesquisa não cita a faixa 970-999, e por isso ela também é conferida (pendência).
_SERIES_NFA_E = range(890, 920)
_LIMITE_TEXTO_CAMPO_TSTRING = 60  # xNome de emitente e destinatário (maxLength 60)
_LIMITE_ID_ESTRANGEIRO = 20

_DOMINIO_MODELO = frozenset({"55", "65"})  # MOC 7.0 e TB:359-367
_DOMINIO_TP_NF = frozenset({"0", "1"})  # ide/tpNF, XSD:81-92
_DOMINIO_ID_DEST = frozenset({"1", "2", "3"})  # ide/idDest, XSD:93-105
_DOMINIO_FIN_NFE = frozenset({"1", "2", "3", "4", "5", "6"})  # ide/finNFe, XSD:185-195
# Finalidades de débito e de crédito (XSD:7485-7507 e XSD:7509-7527; pesquisa, seção 4).
_DOMINIO_TP_NF_DEBITO = frozenset({f"{n:02d}" for n in range(1, 9)})
_DOMINIO_TP_NF_CREDITO = frozenset({f"{n:02d}" for n in range(1, 7)})
_DOMINIO_CRT = frozenset({"1", "2", "3", "4"})  # emit/CRT, XSD:601

# Raízes do namespace da NF-e que NÃO são nota nem evento. Cada uma recebe uma
# recusa com o próprio nome (HI-110). Lista fechada: qualquer outra raiz cai na
# recusa genérica de `ler_nfe`, também com o nome.
_RAIZES_RECUSADAS = {
    "enviNFe": (
        "mensagem de transmissão (enviNFe), não é nota: "
        "só entra a NF-e com protocolo de autorização (nfeProc)."
    ),
    "retEnviNFe": (
        "retorno de transmissão (retEnviNFe), não é nota: "
        "só entra a NF-e com protocolo de autorização (nfeProc)."
    ),
    "envEvento": (
        "mensagem de transmissão de evento (envEvento), não é evento registrado: "
        "só entra o procEventoNFe."
    ),
    "procInutNFe": (
        "inutilização de numeração (procInutNFe), não é nota nem evento: fora desta recepção."
    ),
    "retInutNFe": (
        "retorno de inutilização de numeração (retInutNFe), não é nota nem evento: "
        "fora desta recepção."
    ),
    "resNFe": (
        "resumo da distribuição (resNFe), sem a nota completa: só entra a NF-e completa (nfeProc)."
    ),
    "resEvento": (
        "resumo de evento da distribuição (resEvento), sem o evento completo: "
        "só entra o procEventoNFe."
    ),
    "retConsSitNFe": ("consulta de situação (retConsSitNFe), não é nota: fora desta recepção."),
}


class RecusaNFe(Exception):
    """Um XML do namespace da NF-e não entra. A mensagem é o motivo, em português.

    `apps.fiscal.leitor.ler_arquivo` converte esta exceção em `ArquivoRecusado`;
    quem grava é `apps.fiscal.services`, que trata a recusa por arquivo.
    """


@dataclass(frozen=True)
class ParticipanteNFeLido:
    """Emitente, destinatário ou autor de evento de NF-e.

    `tipo_documento` é "CNPJ", "CPF" ou "idEstrangeiro" (só destinatário). O
    nome e o tipo batem com o que `services.localizar_empresa_do_escritorio`
    espera de qualquer participante (ele só lê tipo e documento).
    """

    tipo_documento: str
    documento: str
    nome: str


@dataclass(frozen=True)
class DocumentoNFeLido:
    """NF-e ou NFC-e já extraída e conferida, pronta para `DocumentoNFe`.

    Totais `None` quando o campo não vem no XML: ausente nunca vira zero.
    `quantidade_itens` é a contagem de `det`; o conteúdo dos itens não é lido.
    """

    modelo: str
    versao: str
    chave: str
    serie: str
    numero: str
    dh_emissao: datetime
    tp_nf: str
    fin_nfe: str
    tp_nf_debito: str
    tp_nf_credito: str
    id_dest: str
    c_uf: str
    emitente: ParticipanteNFeLido
    crt: str
    destinatario: ParticipanteNFeLido | None
    v_nf: Decimal | None
    v_prod: Decimal | None
    v_icms: Decimal | None
    v_st: Decimal | None
    v_ipi: Decimal | None
    v_pis: Decimal | None
    v_cofins: Decimal | None
    v_desc: Decimal | None
    v_frete: Decimal | None
    c_stat: str
    n_prot: str
    dh_recbto: datetime
    quantidade_itens: int
    tem_ibscbs_total: bool
    tem_ibscbs_item: bool
    xml_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class EventoNFeLido:
    """Evento de NF-e (procEventoNFe) já extraído, pronto para `EventoNFe`.

    `c_stat` é o status do retorno (`retEvento/infEvento/cStat`), ou `None`
    quando o retorno não vem. Sem retorno o evento não tem efeito.
    """

    identificador: str
    tp_evento: str
    chave: str
    n_seq_evento: int
    dh_evento: datetime
    autor: ParticipanteNFeLido
    c_stat: str | None
    xml_bytes: bytes
    sha256: str


# ---------------------------------------------------------------------------
# Auxiliares de leitura (mesma semântica da NFS-e, mas com o namespace da NF-e)
# ---------------------------------------------------------------------------


def _localname(tag: str) -> str:
    return tag.partition("}")[2] if tag.startswith("{") else tag


def _texto(pai, caminho):
    """Texto do elemento, sem `strip`: o XSD não admite espaço em volta do valor.
    `None` quando o elemento não existe ou está vazio."""
    if pai is None:
        return None
    achado = pai.find(caminho, _NS)
    if achado is None or achado.text is None:
        return None
    return achado.text


def _obrigatorio(pai, caminho, campo):
    valor = _texto(pai, caminho)
    if valor is None:
        raise RecusaNFe(f"Campo obrigatório ausente: '{campo}'.")
    return valor


def _valor_decimal(pai, caminho, campo):
    """Valor monetário em `Decimal` a partir de TEXTO, pelo padrão TDec_1302.

    Elemento ausente devolve `None`. Elemento presente fora do padrão é recusa
    citando o campo: nunca zero no lugar de valor ilegível (DE-010, nunca float).
    """
    if pai is None:
        return None
    achado = pai.find(caminho, _NS)
    if achado is None:
        return None
    texto = achado.text or ""
    if not _FORMATO_DECIMAL.fullmatch(texto):
        raise RecusaNFe(
            f"Valor de '{campo}' fora do padrão TDec_1302: {texto!r}. "
            "Esperado número com ponto, até 13 inteiros e até duas casas, sem sinal e sem vírgula."
        )
    return Decimal(texto)


def _data_hora(texto, campo):
    if texto is None:
        raise RecusaNFe(f"Campo obrigatório ausente: '{campo}'.")
    # O padrão do XSD vem primeiro (forma e fuso); `fromisoformat` só confere o
    # calendário (dia 31 de abril, por exemplo).
    if not _FORMATO_DATA_HORA.fullmatch(texto):
        raise RecusaNFe(f"Data/hora fora do padrão em '{campo}': {texto!r}.")
    try:
        return datetime.fromisoformat(texto)
    except ValueError as exc:
        raise RecusaNFe(f"Data/hora inválida em '{campo}': {texto!r}.") from exc


def _dominio(texto, dominio, campo):
    if texto not in dominio:
        raise RecusaNFe(f"'{campo}' fora do domínio: {texto!r}.")
    return texto


def _formato(texto, padrao, campo):
    if not padrao.fullmatch(texto):
        raise RecusaNFe(f"'{campo}' fora do formato: {texto!r}.")
    return texto


def _digito_verificador_da_chave(base43: str) -> str:
    """DV da chave de acesso: módulo 11 com pesos 2 a 9 da direita para a esquerda.

    Reaproveita `_calcular_digito_verificador` da DL-011 (apps/empresas/validators):
    ele já converte cada caractere por `ord(c) - 48`, o que cobre o CNPJ
    alfanumérico da NT Conjunta 2025.001 (letras valem 17 a 42). Regra do MOC 7.0,
    Tabela 2-1 (MOC:950-960): resto 0 ou 1 dá DV 0.
    """
    pesos = [2 + ((len(base43) - 1 - posicao) % 8) for posicao in range(len(base43))]
    return _calcular_digito_verificador(base43, pesos)


def _conferir_chave(chave: str) -> None:
    if not _FORMATO_CHAVE.fullmatch(chave):
        raise RecusaNFe(f"Chave de acesso fora do formato de 44 posições: {chave!r}.")
    if _digito_verificador_da_chave(chave[:43]) != chave[43]:
        raise RecusaNFe(f"Dígito verificador da chave de acesso inválido: {chave!r}.")


def _conferir_versao_nfe(versao) -> None:
    """Só o leiaute 4.00 entra. Legados são nomeados; qualquer outro, desconhecido."""
    if versao == VERSAO_SUPORTADA:
        return
    if versao in _VERSOES_LEGADAS:
        raise RecusaNFe(f"NF-e no leiaute {versao}; só o leiaute 4.00 é aceito.")
    raise RecusaNFe(f"versão desconhecida do leiaute da NF-e: {versao!r}.")


def _conferir_emitente_da_chave(chave: str, emitente: tuple[str, str]) -> None:
    """Posições 7 a 20 da chave são o CNPJ do emitente, ou o CPF com zeros à esquerda.

    Fora das séries de NFA-e (`_SERIES_NFA_E`), chave com outro CNPJ ou CPF não é da empresa
    identificada pelo `emit`. A recusa impede que a chave vire ligação com um cliente, mesmo
    quando o `emit` e o `dest` são estranhos (auditoria DL-080, rodada 1, A8).
    """
    tipo, documento = emitente
    if int(chave[22:25]) in _SERIES_NFA_E:
        return
    esperado = documento if tipo == "CNPJ" else documento.zfill(14)
    if chave[6:20] != esperado:
        raise RecusaNFe("CNPJ ou CPF da chave de acesso diferente do emitente (posições 7 a 20).")


def _conferir_ambiente(valor: str, campo: str, mensagem: str) -> None:
    """Ambiente de homologação (`2`) não tem valor fiscal, em nota, evento ou retorno (A3)."""
    _dominio(valor, _DOMINIO_TP_AMB, campo)
    if valor == "2":
        raise RecusaNFe(mensagem)


def _pessoa_cnpj_cpf(pai, rotulo):
    """Par (tipo, documento) do bloco CNPJ|CPF (xs:choice), ou `None` se nenhum.

    A chave de acesso não entra aqui: a empresa vem do emitente e do destinatário,
    nunca da chave (NFA-e, série 890 a 899, leva o CNPJ da SEFAZ na chave).
    """
    cnpj = _texto(pai, "n:CNPJ")
    if cnpj is not None:
        return "CNPJ", _formato(cnpj, _FORMATO_CNPJ, f"CNPJ de {rotulo}")
    cpf = _texto(pai, "n:CPF")
    if cpf is not None:
        return "CPF", _formato(cpf, _FORMATO_CPF, f"CPF de {rotulo}")
    return None


def _nome(pai, rotulo):
    nome = _texto(pai, "n:xNome") or ""
    if len(nome) > _LIMITE_TEXTO_CAMPO_TSTRING:
        raise RecusaNFe(
            f"xNome de {rotulo} com {len(nome)} caracteres, acima do limite de "
            f"{_LIMITE_TEXTO_CAMPO_TSTRING} (TString)."
        )
    return nome


# ---------------------------------------------------------------------------
# Entrada: despacho pela RAIZ e pela VERSÃO (HI-110)
# ---------------------------------------------------------------------------


def ler_nfe(raiz, conteudo: bytes, sha256: str) -> DocumentoNFeLido | EventoNFeLido:
    """Lê um elemento raiz do namespace da NF-e. Recusa com motivo, ou devolve o registro.

    `raiz` já vem parseada e segura (DTD proibido, `defusedxml`, em `leitor`).
    Aceita `nfeProc` no leiaute 4.00 e `procEventoNFe` na versão 1.00. Qualquer
    outra raiz é recusada com o próprio nome.
    """
    nome = _localname(raiz.tag)
    if nome == "nfeProc":
        return _ler_nfe_proc(raiz, conteudo, sha256)
    if nome == "NFe":
        return _recusar_nfe_sem_protocolo(raiz)
    if nome == "procEventoNFe":
        return _ler_proc_evento(raiz, conteudo, sha256)
    if nome in _RAIZES_RECUSADAS:
        raise RecusaNFe(_RAIZES_RECUSADAS[nome])
    raise RecusaNFe(f"tipo de documento NF-e não suportado: raiz {nome!r}.")


def _recusar_nfe_sem_protocolo(raiz):
    # `NFe` nua (sem nfeProc) não tem protocolo de autorização: a nota não está
    # autorizada e não entra (HI-110). A versão é conferida antes, porque um
    # leiaute antigo deve ser nomeado como tal, e não como "sem protocolo".
    inf = raiz.find("n:infNFe", _NS)
    if inf is not None:
        _conferir_versao_nfe(inf.get("versao"))
    raise RecusaNFe(
        "NF-e sem protocolo de autorização: a nota só entra autorizada (nfeProc com protNFe)."
    )


def _ler_nfe_proc(raiz, conteudo: bytes, sha256: str) -> DocumentoNFeLido:
    # TNfeProc (leiauteNFe_v4.00.xsd:6954-6962): @versao obrigatório, NFe e protNFe.
    _conferir_versao_nfe(raiz.get("versao"))
    # Uma NFe por nfeProc. Com duas, o protocolo não diz a qual delas se refere, e a leitura
    # não escolhe uma (auditoria DL-080, rodada 1, A8).
    if len(raiz.findall("n:NFe", _NS)) > 1:
        raise RecusaNFe("nfeProc com mais de uma NFe: só entra um XML por nota, com seu protocolo.")

    prot = raiz.find("n:protNFe", _NS)
    if prot is None:
        raise RecusaNFe(
            "NF-e sem protocolo de autorização: a nota só entra autorizada (nfeProc com protNFe)."
        )

    inf = raiz.find("n:NFe/n:infNFe", _NS)
    if inf is None:
        raise RecusaNFe("NF-e sem infNFe.")
    # infNFe/@versao: obrigatório, TVerNFe (leiauteNFe_v4.00.xsd:6620).
    _conferir_versao_nfe(inf.get("versao"))

    casamento = _FORMATO_ID_NFE.fullmatch(inf.get("Id") or "")
    if casamento is None:
        raise RecusaNFe(
            f"Id da NF-e fora do padrão 'NFe' + 44 posições (leiauteNFe_v4.00.xsd:6625-6634): "
            f"{inf.get('Id')!r}."
        )
    chave = casamento.group(1)
    _conferir_chave(chave)

    inf_prot = prot.find("n:infProt", _NS)
    if inf_prot is None:
        raise RecusaNFe("NF-e sem protocolo de autorização: protNFe sem infProt.")

    c_stat = _formato(_obrigatorio(inf_prot, "n:cStat", "cStat"), _FORMATO_CSTAT, "cStat")
    if c_stat in _CSTAT_DENEGADA:
        raise RecusaNFe(f"NF-e denegada — sem efeito fiscal (cStat {c_stat}).")
    if c_stat not in _CSTAT_AUTORIZADA:
        raise RecusaNFe(f"NF-e não autorizada: cStat {c_stat} no protocolo.")

    # protNFe/infProt/chNFe (leiauteNFe_v4.00.xsd:6709) tem de ser a mesma chave
    # do @Id: nota e protocolo que não batem não são a mesma operação.
    chave_do_protocolo = _obrigatorio(inf_prot, "n:chNFe", "chNFe")
    if chave_do_protocolo != chave:
        raise RecusaNFe("Chave do protocolo diferente da chave da NF-e (infNFe/@Id).")

    dh_recbto = _data_hora(_obrigatorio(inf_prot, "n:dhRecbto", "dhRecbto"), "dhRecbto")
    n_prot = _texto(inf_prot, "n:nProt") or ""
    if n_prot:
        _formato(n_prot, _FORMATO_N_PROT, "nProt")

    ide = inf.find("n:ide", _NS)
    if ide is None:
        raise RecusaNFe("NF-e sem ide.")
    # Nota emitida em homologação não tem valor fiscal (regra da NFS-e, DE-076 item 3). ide/tpAmb
    # é obrigatório no XSD (leiauteNFe_v4.00.xsd:178): ausente é recusa, e não "produção".
    _conferir_ambiente(
        _obrigatorio(ide, "n:tpAmb", "tpAmb"),
        "tpAmb",
        "NF-e emitida em ambiente de homologação (teste), sem valor fiscal.",
    )

    # cUF (leiauteNFe_v4.00.xsd:24), mod (:51), serie (:56), nNF (:61). A chave tem
    # as mesmas posições (MOC 7.0, Tabela 2-1, MOC:914-947): cUF 0-1, modelo 20-21,
    # série 22-24, número 25-33. Chave e campos que não batem são nota inconsistente.
    c_uf = _formato(_obrigatorio(ide, "n:cUF", "cUF"), re.compile(r"[0-9]{2}"), "cUF")
    if c_uf != chave[:2]:
        raise RecusaNFe("cUF da chave diferente de ide/cUF.")
    modelo = _dominio(_obrigatorio(ide, "n:mod", "mod"), _DOMINIO_MODELO, "mod")
    if modelo != chave[20:22]:
        raise RecusaNFe("Modelo da chave diferente de ide/mod.")
    serie = _formato(_obrigatorio(ide, "n:serie", "serie"), _FORMATO_SERIE, "serie")
    if serie.zfill(3) != chave[22:25]:
        raise RecusaNFe("Série da chave diferente de ide/serie.")
    numero = _formato(_obrigatorio(ide, "n:nNF", "nNF"), _FORMATO_NNF, "nNF")
    if numero.zfill(9) != chave[25:34]:
        raise RecusaNFe("Número da chave diferente de ide/nNF.")

    # dhEmi (leiauteNFe_v4.00.xsd:66): data e hora com fuso. Nunca só a data.
    dh_emissao = _data_hora(_obrigatorio(ide, "n:dhEmi", "dhEmi"), "dhEmi")
    tp_nf = _dominio(_obrigatorio(ide, "n:tpNF", "tpNF"), _DOMINIO_TP_NF, "tpNF")
    fin_nfe = _dominio(_obrigatorio(ide, "n:finNFe", "finNFe"), _DOMINIO_FIN_NFE, "finNFe")
    id_dest = _dominio(_obrigatorio(ide, "n:idDest", "idDest"), _DOMINIO_ID_DEST, "idDest")
    # Finalidades de débito e de crédito (pesquisa, seção 4): opcionais no XSD.
    # Ausente fica vazio, nunca um código inventado.
    tp_nf_debito = _texto(ide, "n:tpNFDebito") or ""
    if tp_nf_debito:
        _dominio(tp_nf_debito, _DOMINIO_TP_NF_DEBITO, "tpNFDebito")
    tp_nf_credito = _texto(ide, "n:tpNFCredito") or ""
    if tp_nf_credito:
        _dominio(tp_nf_credito, _DOMINIO_TP_NF_CREDITO, "tpNFCredito")

    # Emitente: CNPJ ou CPF (xs:choice, leiauteNFe_v4.00.xsd:519-531). Obrigatório.
    emit = inf.find("n:emit", _NS)
    par_emit = _pessoa_cnpj_cpf(emit, "emitente")
    if par_emit is None:
        raise RecusaNFe("NF-e sem emitente com CNPJ ou CPF.")
    _conferir_emitente_da_chave(chave, par_emit)
    crt_texto = _texto(emit, "n:CRT")
    crt = _dominio(crt_texto, _DOMINIO_CRT, "CRT") if crt_texto else ""
    emitente = ParticipanteNFeLido(par_emit[0], par_emit[1], _nome(emit, "emitente"))

    # Destinatário: OPCIONAL no XSD (leiauteNFe_v4.00.xsd:734). A NFC-e normalmente
    # não o traz. Quando vem, tem CNPJ, CPF ou idEstrangeiro (xs:choice).
    destinatario = None
    dest = inf.find("n:dest", _NS)
    if dest is not None:
        par_dest = _pessoa_cnpj_cpf(dest, "destinatário")
        if par_dest is not None:
            destinatario = ParticipanteNFeLido(
                par_dest[0], par_dest[1], _nome(dest, "destinatário")
            )
        else:
            estrangeiro = _texto(dest, "n:idEstrangeiro")
            if estrangeiro is None:
                raise RecusaNFe("Destinatário sem CNPJ, CPF ou idEstrangeiro.")
            if len(estrangeiro) > _LIMITE_ID_ESTRANGEIRO:
                raise RecusaNFe(
                    f"idEstrangeiro com {len(estrangeiro)} caracteres, acima do limite de "
                    f"{_LIMITE_ID_ESTRANGEIRO}."
                )
            destinatario = ParticipanteNFeLido(
                "idEstrangeiro", estrangeiro, _nome(dest, "destinatário")
            )

    # Totais (leiauteNFe_v4.00.xsd:5333-5480, grupo ICMSTot). Cada valor é
    # opcional; a ausência continua ausência (None). Só o ICMSTot é lido aqui.
    icms_tot = inf.find("n:total/n:ICMSTot", _NS)
    totais = {
        campo: _valor_decimal(icms_tot, f"n:{xml}", xml)
        for campo, xml in (
            ("v_nf", "vNF"),
            ("v_prod", "vProd"),
            ("v_icms", "vICMS"),
            ("v_st", "vST"),
            ("v_ipi", "vIPI"),
            ("v_pis", "vPIS"),
            ("v_cofins", "vCOFINS"),
            ("v_desc", "vDesc"),
            ("v_frete", "vFrete"),
        )
    }

    # Itens: só a contagem de `det` (leiauteNFe_v4.00.xsd:867, maxOccurs 990).
    quantidade_itens = len(inf.findall("n:det", _NS))
    # IBS/CBS: só a PRESENÇA do total e do grupo por item (política da fatia 1,
    # enquanto a PE-39 não for decidida). Nada é interpretado.
    tem_ibscbs_total = inf.find("n:total/n:IBSCBSTot", _NS) is not None
    tem_ibscbs_item = inf.find("n:det/n:imposto/n:IBSCBS", _NS) is not None

    return DocumentoNFeLido(
        modelo=modelo,
        versao=VERSAO_SUPORTADA,
        chave=chave,
        serie=serie,
        numero=numero,
        dh_emissao=dh_emissao,
        tp_nf=tp_nf,
        fin_nfe=fin_nfe,
        tp_nf_debito=tp_nf_debito,
        tp_nf_credito=tp_nf_credito,
        id_dest=id_dest,
        c_uf=c_uf,
        emitente=emitente,
        crt=crt,
        destinatario=destinatario,
        c_stat=c_stat,
        n_prot=n_prot,
        dh_recbto=dh_recbto,
        quantidade_itens=quantidade_itens,
        tem_ibscbs_total=tem_ibscbs_total,
        tem_ibscbs_item=tem_ibscbs_item,
        xml_bytes=conteudo,
        sha256=sha256,
        **totais,
    )


# ---------------------------------------------------------------------------
# Evento: procEventoNFe (PL 010d, Evento/leiauteEvento_v1.00.xsd)
# ---------------------------------------------------------------------------


def _ler_proc_evento(raiz, conteudo: bytes, sha256: str) -> EventoNFeLido:
    # procEventoNFe/@versao: 1.00 (EVT:350-367). Outra versão não é conferida à
    # ciegas: recusa com o número.
    versao = raiz.get("versao")
    if versao != VERSAO_EVENTO_SUPORTADA:
        raise RecusaNFe(
            f"versão de evento desconhecida: {versao!r} (esperado {VERSAO_EVENTO_SUPORTADA})."
        )

    inf = raiz.find("n:evento/n:infEvento", _NS)
    if inf is None:
        raise RecusaNFe("Evento sem infEvento.")
    # infEvento/tpAmb é obrigatório (leiauteEvento_v1.00.xsd, sem minOccurs). Evento de
    # homologação não cancela nota de produção: a mesma regra da nota (auditoria, A3).
    _conferir_ambiente(
        _obrigatorio(inf, "n:tpAmb", "tpAmb do evento"),
        "tpAmb do evento",
        "Evento emitido em ambiente de homologação (teste), sem valor fiscal.",
    )

    identificador = inf.get("Id") or ""
    if not _FORMATO_ID_EVENTO.fullmatch(identificador):
        raise RecusaNFe(
            f"Id do evento fora do padrão 'ID' + 52 posições (54 no total): {identificador!r}."
        )

    tp_evento = _formato(
        _obrigatorio(inf, "n:tpEvento", "tpEvento"), re.compile(r"[0-9]{6}"), "tpEvento"
    )
    chave = _obrigatorio(inf, "n:chNFe", "chNFe")
    _conferir_chave(chave)
    n_seq_texto = _formato(
        _obrigatorio(inf, "n:nSeqEvento", "nSeqEvento"), _FORMATO_NSEQ_EVENTO, "nSeqEvento"
    )
    dh_evento = _data_hora(_obrigatorio(inf, "n:dhEvento", "dhEvento"), "dhEvento")

    # O autor é CNPJ ou CPF (xs:choice em infEvento). Obrigatório: é ele que
    # liga o evento a uma empresa do escritório, quando houver.
    par_autor = _pessoa_cnpj_cpf(inf, "autor do evento")
    if par_autor is None:
        raise RecusaNFe("Evento sem CNPJ ou CPF do autor.")
    autor = ParticipanteNFeLido(par_autor[0], par_autor[1], "")

    # O @Id é "ID" + tpEvento + chNFe + nSeqEvento com dois dígitos (EVT:129-137,
    # e a regra escrita no próprio atributo). Id que não confere com o corpo é
    # evento montado de outro jeito: recusa, para não ligar o cancelamento errado.
    esperado = f"ID{tp_evento}{chave}{int(n_seq_texto):02d}"
    if identificador != esperado:
        raise RecusaNFe("Id do evento não confere com tpEvento, chNFe e nSeqEvento.")

    # retEvento/infEvento/cStat (EVT:171) é opcional no XML. Sem ele, o evento
    # não tem efeito (pesquisa, seção 2). Se o retorno traz outra chave, o status
    # é de outra nota: recusa.
    ret_inf = raiz.find("n:retEvento/n:infEvento", _NS)
    c_stat = None
    if ret_inf is not None:
        # tpAmb do retorno é obrigatório (TRetEvento/infEvento, leiauteEvento_v1.00.xsd).
        _conferir_ambiente(
            _obrigatorio(ret_inf, "n:tpAmb", "tpAmb do retorno do evento"),
            "tpAmb do retorno do evento",
            "Retorno de evento emitido em ambiente de homologação (teste), sem valor fiscal.",
        )
        c_stat = _texto(ret_inf, "n:cStat") or None
        if c_stat is not None:
            _formato(c_stat, _FORMATO_CSTAT, "cStat do retorno do evento")
        chave_do_retorno = _texto(ret_inf, "n:chNFe")
        if chave_do_retorno is not None and chave_do_retorno != chave:
            raise RecusaNFe("Retorno do evento referente a outra NF-e (chNFe diferente).")
        # tpEvento e nSeqEvento do retorno são opcionais (minOccurs 0). Quando vêm, têm de ser
        # os do evento: retorno de outro tipo ou de outra sequência não é a resposta deste
        # evento, e o status dele não pode cancelar a nota (auditoria, A8).
        tp_do_retorno = _texto(ret_inf, "n:tpEvento")
        if tp_do_retorno is not None and tp_do_retorno != tp_evento:
            raise RecusaNFe("Retorno do evento de outro tipo (tpEvento diferente do evento).")
        seq_do_retorno = _texto(ret_inf, "n:nSeqEvento")
        if seq_do_retorno is not None:
            seq_do_retorno = _formato(
                seq_do_retorno, _FORMATO_NSEQ_EVENTO, "nSeqEvento do retorno do evento"
            )
            if int(seq_do_retorno) != int(n_seq_texto):
                raise RecusaNFe("Retorno do evento de outra sequência (nSeqEvento diferente).")

    return EventoNFeLido(
        identificador=identificador,
        tp_evento=tp_evento,
        chave=chave,
        n_seq_evento=int(n_seq_texto),
        dh_evento=dh_evento,
        autor=autor,
        c_stat=c_stat,
        xml_bytes=conteudo,
        sha256=sha256,
    )
