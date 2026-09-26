"""Leitura segura de XML de NFS-e nacional e de evento — DL-010, fatia 1.

Fonte dos caminhos, tipos e regras de formato citados nos comentários:
esquemas XSD oficiais do Portal Nacional da NFS-e, pacote
NFSe-ESQUEMAS_XSD-v1.01-20260209 (SE/CGNFS-e), consultados em 2026-09-25
(RC-111, RC-110, docs/planos/DL-010-F1-recepcao-nfse.md). Os arquivos XSD em
si são documento de terceiro e não entram no repositório — os fatos
relevantes estão citados aqui e no plano da etapa, com o nome do elemento ou
tipo do esquema, para poderem ser reconferidos.

Este módulo não grava nada no banco — só interpreta bytes e devolve um
`DocumentoLido`/`EventoLido` imutável, ou levanta `ArquivoRecusado` com um
motivo em português. `apps.fiscal.services` é quem decide o que fazer com o
resultado (gravar, marcar como duplicado etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import ParseError, fromstring

# Namespace oficial da NFS-e nacional — RC-65 (medido no acervo real do
# escritório) e NFSe_v1.0x.xsd/evento_v1.0x.xsd (targetNamespace). Não muda
# entre as versões 1.00 e 1.01 do leiaute.
NS_NFSE = "http://www.sped.fazenda.gov.br/nfse"

# Namespace da NF-e — confirmado no levantamento de leiaute do plano-mãe
# (docs/planos/DL-010-recepcao-de-documentos-fiscais.md, seção "O que está
# confirmado": "Namespace único, que não varia por versão"). Serve só para
# dar ao usuário a mensagem específica "tipo ainda não suportado: NF-e" —
# qualquer OUTRO namespace (NFCom, CT-e, GTVe, ou raiz não reconhecida) cai
# no ramo genérico em `ler_arquivo`, porque esta fatia não teve acesso aos
# XSD desses formatos (RC-71/critério 18; "fora desta fatia" no plano).
NS_NFE = "http://www.portalfiscal.inf.br/nfe"

_NS = {"n": NS_NFSE}

# TSIdNFSe (tiposSimples_v1.0x.xsd): "NFS" + 50 dígitos = 53 posições
# (xs:pattern "NFS[0-9]{50}"). O esquema só prevê dígitos nessas 50
# posições — não há letra prevista mesmo com o CNPJ alfanumérico em vigor
# (RC-46). O dígito verificador (a última das 50 posições) NÃO é conferido
# aqui: o XSD não documenta o algoritmo, e o plano da etapa declara esse
# limite expressamente ("Limite declarado", DL-010-F1).
_FORMATO_ID_NFSE = re.compile(r"^NFS[0-9]{50}$")

# TSIdEvento: "EVT" + chave da NFS-e (50) + tipo do evento (6) + número do
# pedido de registro de evento (3) = 62 posições.
_FORMATO_ID_EVENTO = re.compile(r"^EVT[0-9]{59}$")

# TSChaveNFSe: 50 dígitos, SEM o prefixo "NFS" — é só a parte numérica da
# chave. `infEvento/pedRegEvento/infPedReg/chNFSe` referencia a nota por
# esses 50 dígitos, enquanto `infNFSe/@Id` tem o prefixo "NFS" na frente. Os
# dois formatos convivem no próprio XSD; a conversão entre eles vive em
# `apps.fiscal.services.situacao_do_documento` (o único lugar que precisa
# comparar os dois).
_FORMATO_CHAVE_NFSE = re.compile(r"^[0-9]{50}$")

# TVerNFSe: exatamente "1.00" ou "1.01" (xs:pattern "1\.00|1\.01") — RC-72.
_VERSOES_SUPORTADAS = frozenset({"1.00", "1.01"})

# TSDec15V2 (tiposSimples_v1.0x.xsd): decimal com PONTO, sem sinal, sem
# vírgula, até 15 dígitos inteiros (sem zero à esquerda, exceto o próprio
# "0") e exatamente 0 ou 2 casas decimais — xs:pattern
# "0|0\.[0-9]{2}|[1-9]{1}[0-9]{0,14}(\.[0-9]{2})?". É exatamente a regra do
# critério 32 do plano (recusar vírgula, negativo, mais de 2 casas ou texto
# não numérico) e da política de arredondamento explícito da DE-010 (nunca
# float): usamos uma expressão equivalente, mais simples de ler.
_FORMATO_DECIMAL = re.compile(r"^(0|[1-9][0-9]{0,14})(\.[0-9]{2})?$")

# TSTipoRetISSQN: enumeração fechada {1, 2, 3} (RC-110). O código é LIDO e
# validado quanto ao domínio, nunca interpretado (a retenção não é
# calculada nesta fatia).
_CODIGOS_RET_ISSQN = frozenset({"1", "2", "3"})

# O CÓDIGO do evento é o NOME do elemento escolhido dentro do xs:choice de
# TCInfPedReg (tiposEventos_v1.0x.xsd) — "e" + 6 dígitos (ex.: <e101101/>),
# não um valor de texto separado.
_FORMATO_CODIGO_EVENTO = re.compile(r"^e[0-9]{6}$")

# TSNNFSe (tiposSimples_v1.0x.xsd): 1 a 13 dígitos, sem padronização de
# zero à esquerda (RC-74/RC-75). Campo OPCIONAL — quando ausente, o texto
# vazio continua aceito (ver `_texto` devolvendo `None`, tratado como "").
_FORMATO_NUMERO_NFSE = re.compile(r"^[0-9]{1,13}$")

# Achado A1 da auditoria (rodada 1): os quatro tamanhos abaixo estão
# escritos nos próprios campos do modelo (`apps/fiscal/models.py`), mas o
# leitor não os conferia — um XML com `xNome` de 301 caracteres ou um `NIF`
# de 41 caracteres passava pela leitura inteira e só estourava
# `django.db.DataError` na hora de gravar, derrubando o ENVIO INTEIRO com
# 500 (critério 7/8 quebrado). Verificar aqui, ANTES da gravação, permite
# recusar SÓ o arquivo, com motivo — o comportamento que o plano promete.
# TSNomeRazaoSocial (tiposSimples_v1.0x.xsd): até 300 caracteres.
_TAMANHO_MAXIMO_NOME = 300
# TSNIF (tiposSimples_v1.0x.xsd): até 40 posições — o maior dos quatro
# formatos de documento de participante (CNPJ, CPF, NIF, cNaoNIF), por
# isso é o limite usado para os quatro (mesmo critério do model, que usa
# max_length=40 para os campos de documento do prestador/tomador).
_TAMANHO_MAXIMO_DOCUMENTO_PARTICIPANTE = 40


class ArquivoRecusado(Exception):
    """UM arquivo do envio é inválido; a mensagem da exceção é o motivo.

    Nunca levantada fora deste módulo por engano cruzando para o chamador
    sem tratamento: `apps.fiscal.services` captura sempre em volta de cada
    arquivo (critério 7/8 do plano — um arquivo ruim não impede os demais).
    """


@dataclass(frozen=True)
class ParticipanteLido:
    """Um bloco CNPJ|CPF|NIF|cNaoNIF do XML (TCEmitente/TCInfoPessoa/
    TCInfoPrestador). `tipo_documento` é um dos valores de
    `apps.fiscal.models.TipoDocumentoParticipante`; `documento` é sempre
    TEXTO (nunca convertido para número — RC-75, zero à esquerda)."""

    tipo_documento: str
    documento: str
    nome: str


@dataclass(frozen=True)
class DocumentoLido:
    """NFS-e nacional já extraída e validada, pronta para virar
    `apps.fiscal.models.DocumentoFiscal`."""

    versao: str
    identificador: str
    numero: str
    dh_emissao: datetime
    d_competencia: date
    prestador: ParticipanteLido
    tomador: ParticipanteLido | None
    v_serv: Decimal
    v_liq: Decimal
    tp_ret_issqn: str
    xml_bytes: bytes
    sha256: str


@dataclass(frozen=True)
class EventoLido:
    """Evento de NFS-e já extraído, pronto para virar
    `apps.fiscal.models.EventoFiscal`."""

    identificador: str
    codigo: str
    chave_nfse: str
    data_evento: datetime
    autor: ParticipanteLido | None
    xml_bytes: bytes
    sha256: str


def _texto(elemento, caminho):
    if elemento is None:
        return None
    achado = elemento.find(caminho, _NS)
    if achado is None or achado.text is None:
        return None
    return achado.text.strip()


def _elemento(elemento, caminho):
    if elemento is None:
        return None
    return elemento.find(caminho, _NS)


def _decimal_estrito(texto, campo):
    """`Decimal` a partir de TEXTO — nunca `float` (DE-010). Recusa vírgula,
    sinal, mais de duas casas decimais ou texto não numérico (critério 32
    do plano)."""
    if texto is None or not _FORMATO_DECIMAL.fullmatch(texto):
        raise ArquivoRecusado(
            f"Valor de '{campo}' inválido: {texto!r}. Esperado número decimal "
            "com ponto e até duas casas, sem vírgula e sem sinal."
        )
    return Decimal(texto)


def _data(texto, campo):
    if texto is None:
        raise ArquivoRecusado(f"Campo obrigatório ausente: '{campo}'.")
    try:
        return date.fromisoformat(texto)
    except ValueError as exc:
        raise ArquivoRecusado(f"Data inválida em '{campo}': {texto!r}.") from exc


def _data_hora(texto, campo):
    if texto is None:
        raise ArquivoRecusado(f"Campo obrigatório ausente: '{campo}'.")
    try:
        # TSDateTimeUTC sempre traz o deslocamento (+hh:mm/-hh:mm) — nunca
        # sufixo "Z". `datetime.fromisoformat` aceita esse formato desde a
        # 3.7 do Python. RC-75 registra fusos variados no acervo real,
        # inclusive +00:00/-00:00 suspeitos de valor padrão — isso é dado a
        # EXIBIR, não motivo de recusa aqui.
        valor = datetime.fromisoformat(texto)
    except ValueError as exc:
        raise ArquivoRecusado(f"Data/hora inválida em '{campo}': {texto!r}.") from exc
    if valor.tzinfo is None:
        raise ArquivoRecusado(f"Data/hora sem fuso horário em '{campo}': {texto!r}.")
    return valor


def _nome_valido(elemento):
    """`xNome` (TSNomeRazaoSocial), verificado contra o limite de tamanho
    ANTES de virar `ParticipanteLido.nome` — achado A1."""
    nome = _texto(elemento, "n:xNome") or ""
    if len(nome) > _TAMANHO_MAXIMO_NOME:
        raise ArquivoRecusado(
            f"xNome com {len(nome)} caracteres, acima do limite de "
            f"{_TAMANHO_MAXIMO_NOME} (TSNomeRazaoSocial)."
        )
    return nome


def _documento_valido(documento, tipo):
    """Documento (CNPJ/CPF/NIF) verificado contra o limite de tamanho —
    achado A1. O DV/formato específico de CNPJ e CPF é conferido depois,
    em `apps.fiscal.services` (ponto único de identificação); aqui só a
    condição que o XSD já fixa como TAMANHO MÁXIMO do campo."""
    if len(documento) > _TAMANHO_MAXIMO_DOCUMENTO_PARTICIPANTE:
        raise ArquivoRecusado(
            f"{tipo} com {len(documento)} caracteres, acima do limite de "
            f"{_TAMANHO_MAXIMO_DOCUMENTO_PARTICIPANTE} (TSNIF)."
        )
    return documento


def _participante(elemento, *, apenas_cnpj_ou_cpf=False):
    """Lê um bloco CNPJ|CPF|NIF|cNaoNIF e devolve `ParticipanteLido`, ou
    `None` se `elemento` for `None` (bloco ausente — ex.: tomador, que é
    opcional no esquema).

    `apenas_cnpj_ou_cpf=True` é para o EMITENTE (TCEmitente só admite
    CNPJ|CPF no esquema, nunca NIF/cNaoNIF) — usado para o prestador da
    NFS-e; recusa se nenhum dos dois estiver presente.
    """
    if elemento is None:
        return None
    cnpj = _texto(elemento, "n:CNPJ")
    if cnpj is not None:
        return ParticipanteLido("CNPJ", _documento_valido(cnpj, "CNPJ"), _nome_valido(elemento))
    cpf = _texto(elemento, "n:CPF")
    if cpf is not None:
        return ParticipanteLido("CPF", _documento_valido(cpf, "CPF"), _nome_valido(elemento))
    if apenas_cnpj_ou_cpf:
        raise ArquivoRecusado("Prestador sem CNPJ nem CPF.")
    nif = _texto(elemento, "n:NIF")
    if nif is not None:
        return ParticipanteLido("NIF", _documento_valido(nif, "NIF"), _nome_valido(elemento))
    nao_nif = _texto(elemento, "n:cNaoNIF")
    if nao_nif is not None:
        return ParticipanteLido("nao_informado", "", _nome_valido(elemento))
    raise ArquivoRecusado("Bloco de pessoa sem CNPJ, CPF, NIF nem cNaoNIF.")


def _raiz_segura(conteudo: bytes):
    """`fromstring` do `defusedxml`, com DTD proibido (critério 24, DE-074
    item 2 — "a única dependência nova").

    Recebe sempre BYTES, nunca `str`: assim o parser respeita a declaração
    de codificação do próprio XML (RC-75 mediu 714 arquivos SEM declaração
    no acervo real — nesse caso a especificação XML manda assumir UTF-8, e
    é o que o parser faz sozinho). Decodificar antes de chamar aqui
    esconderia esse comportamento atrás de uma escolha nossa de
    codificação — e um `str` já decodificado errado não seria mais
    recuperável (falha de decodificação vira recusa, nunca palpite, por
    isso `UnicodeDecodeError` também é convertida em `ArquivoRecusado`
    abaixo).
    """
    if not isinstance(conteudo, bytes):
        raise TypeError("_raiz_segura espera bytes, nunca str.")
    if not conteudo.strip():
        raise ArquivoRecusado("Arquivo XML vazio.")
    try:
        return fromstring(conteudo, forbid_dtd=True)
    except DefusedXmlException as exc:
        raise ArquivoRecusado(
            f"XML recusado por conter construção proibida (DTD ou entidade externa): {exc}"
        ) from exc
    except ParseError as exc:
        raise ArquivoRecusado(f"XML malformado: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ArquivoRecusado(
            f"Falha ao decodificar o XML (codificação declarada inválida): {exc}"
        ) from exc
    except LookupError as exc:
        # Achado A1: `encoding="x-inexistente"` (ou qualquer nome de
        # codificação que o Python não reconhece) faz o parser C do XML
        # levantar `LookupError` ao tentar resolver o codec — sem isto,
        # um único arquivo assim derrubava o ENVIO INTEIRO com 500.
        raise ArquivoRecusado(
            f"Falha ao decodificar o XML (codificação declarada desconhecida): {exc}"
        ) from exc
    except ValueError as exc:
        # Defesa em profundidade para qualquer outro `ValueError` que o
        # parser venha a levantar por conteúdo malformado não coberto
        # pelas exceções específicas acima (ex.: declaração de codificação
        # com sintaxe inválida) — ainda vira recusa do ARQUIVO, nunca 500.
        raise ArquivoRecusado(f"XML malformado: {exc}") from exc


def ler_arquivo(conteudo: bytes, sha256: str) -> DocumentoLido | EventoLido:
    """Lê um XML de NFS-e nacional (elemento raiz `NFSe`) ou de evento
    (elemento raiz `evento`).

    Classifica pela RAIZ e pelo NAMESPACE do documento (RC-71, critério 18
    — nunca pelo nome do arquivo ou da pasta: o acervo real tem uma GTVe
    com "_evento_" no nome, dentro de uma pasta "DESCONHECIDO"). Levanta
    `ArquivoRecusado` — com motivo — para qualquer arquivo que não seja um
    destes dois; quem chama (`apps.fiscal.services.receber_envio`) converte
    isso em um `ResultadoDoArquivo` "recusado" e segue para o próximo
    arquivo do envio.
    """
    raiz = _raiz_segura(conteudo)

    if "}" not in raiz.tag:
        raise ArquivoRecusado(f"XML sem espaço de nomes reconhecido: elemento raiz {raiz.tag!r}.")
    namespace, _, localname = raiz.tag[1:].partition("}")

    if namespace == NS_NFE:
        raise ArquivoRecusado("tipo ainda não suportado: NF-e")
    if namespace != NS_NFSE:
        raise ArquivoRecusado(f"tipo ainda não suportado: {namespace}")

    if localname == "NFSe":
        return _ler_nfse(raiz, conteudo, sha256)
    if localname == "evento":
        return _ler_evento(raiz, conteudo, sha256)
    raise ArquivoRecusado(f"tipo ainda não suportado: {localname}")


def _ler_nfse(raiz, conteudo: bytes, sha256: str) -> DocumentoLido:
    versao = raiz.get("versao")
    if versao not in _VERSOES_SUPORTADAS:
        raise ArquivoRecusado(f"versão não suportada: {versao!r}")

    inf_nfse = _elemento(raiz, "n:infNFSe")
    if inf_nfse is None:
        raise ArquivoRecusado("NFS-e sem infNFSe.")

    identificador = inf_nfse.get("Id")
    if not identificador or not _FORMATO_ID_NFSE.fullmatch(identificador):
        raise ArquivoRecusado(f"Id fora do formato NFS+50 dígitos: {identificador!r}")

    numero = _texto(inf_nfse, "n:nNFSe") or ""
    if numero and not _FORMATO_NUMERO_NFSE.fullmatch(numero):
        raise ArquivoRecusado(f"nNFSe fora do formato de até 13 dígitos (TSNNFSe): {numero!r}")

    emit = _elemento(inf_nfse, "n:emit")
    prestador = _participante(emit, apenas_cnpj_ou_cpf=True)
    if prestador is None:
        raise ArquivoRecusado("NFS-e sem prestador (emit).")

    dps = _elemento(inf_nfse, "n:DPS")
    inf_dps = _elemento(dps, "n:infDPS")
    if inf_dps is None:
        raise ArquivoRecusado("NFS-e sem DPS/infDPS.")

    # DE-076 item 3 (auditoria, achado A11): nota emitida em AMBIENTE DE
    # HOMOLOGAÇÃO (teste) não tem valor fiscal — `infDPS/tpAmb` = "2"
    # (TSTpAmb, tiposComplexos_v1.01.xsd: 1=Produção, 2=Homologação).
    # Ausência do campo NÃO recusa (é o caso raro de um XML que não segue
    # o esquema à risca; recusamos só quando o valor EXPLICITAMENTE diz
    # "2" — nunca adivinhamos homologação por omissão).
    tp_amb = _texto(inf_dps, "n:tpAmb")
    if tp_amb == "2":
        raise ArquivoRecusado("NFS-e emitida em ambiente de homologação (teste), sem valor fiscal.")

    dh_emissao = _data_hora(_texto(inf_dps, "n:dhEmi"), "dhEmi")
    d_competencia = _data(_texto(inf_dps, "n:dCompet"), "dCompet")

    # toma é OPCIONAL no esquema (DPS/infDPS/toma, minOccurs="0") — ausência
    # não é XML malformado (mesma armadilha do bloco "dest" opcional da
    # NF-e, registrada no plano-mãe, aplicada aqui ao tomador da NFS-e).
    toma = _elemento(inf_dps, "n:toma")
    tomador = _participante(toma)

    valores_nfse = _elemento(inf_nfse, "n:valores")
    v_liq = _decimal_estrito(_texto(valores_nfse, "n:vLiq"), "vLiq")

    valores_dps = _elemento(inf_dps, "n:valores")
    v_serv_prest = _elemento(valores_dps, "n:vServPrest")
    v_serv = _decimal_estrito(_texto(v_serv_prest, "n:vServ"), "vServ")

    trib = _elemento(valores_dps, "n:trib")
    trib_mun = _elemento(trib, "n:tribMun")
    tp_ret_issqn = _texto(trib_mun, "n:tpRetISSQN")
    if tp_ret_issqn not in _CODIGOS_RET_ISSQN:
        raise ArquivoRecusado(f"tpRetISSQN fora do domínio {{1,2,3}}: {tp_ret_issqn!r}")

    return DocumentoLido(
        versao=versao,
        identificador=identificador,
        numero=numero,
        dh_emissao=dh_emissao,
        d_competencia=d_competencia,
        prestador=prestador,
        tomador=tomador,
        v_serv=v_serv,
        v_liq=v_liq,
        tp_ret_issqn=tp_ret_issqn,
        xml_bytes=conteudo,
        sha256=sha256,
    )


def _ler_evento(raiz, conteudo: bytes, sha256: str) -> EventoLido:
    versao = raiz.get("versao")
    if versao not in _VERSOES_SUPORTADAS:
        raise ArquivoRecusado(f"versão não suportada: {versao!r}")

    inf_evento = _elemento(raiz, "n:infEvento")
    if inf_evento is None:
        raise ArquivoRecusado("evento sem infEvento.")

    identificador = inf_evento.get("Id")
    if not identificador or not _FORMATO_ID_EVENTO.fullmatch(identificador):
        raise ArquivoRecusado(f"Id do evento fora do formato EVT+59 dígitos: {identificador!r}")

    ped_reg_evento = _elemento(inf_evento, "n:pedRegEvento")
    inf_ped_reg = _elemento(ped_reg_evento, "n:infPedReg")
    if inf_ped_reg is None:
        raise ArquivoRecusado("evento sem pedRegEvento/infPedReg.")

    chave_nfse = _texto(inf_ped_reg, "n:chNFSe")
    if not chave_nfse or not _FORMATO_CHAVE_NFSE.fullmatch(chave_nfse):
        raise ArquivoRecusado(f"chNFSe fora do formato de 50 dígitos: {chave_nfse!r}")

    data_evento = _data_hora(_texto(inf_ped_reg, "n:dhEvento"), "dhEvento")

    cnpj_autor = _texto(inf_ped_reg, "n:CNPJAutor")
    cpf_autor = _texto(inf_ped_reg, "n:CPFAutor")
    autor = None
    if cnpj_autor is not None:
        autor = ParticipanteLido("CNPJ", _documento_valido(cnpj_autor, "CNPJAutor"), "")
    elif cpf_autor is not None:
        autor = ParticipanteLido("CPF", _documento_valido(cpf_autor, "CPFAutor"), "")

    # O código do evento é o NOME do elemento escolhido dentro do xs:choice
    # de TCInfPedReg (tiposEventos_v1.0x.xsd) — "e" + 6 dígitos (ex.:
    # e101101) — não um valor de texto à parte. Percorremos os filhos
    # DIRETOS de infPedReg e coletamos TODOS os que batem com o formato —
    # os demais filhos (tpAmb, verAplic, dhEvento, CNPJAutor/CPFAutor,
    # chNFSe) nunca casam com "e" + 6 dígitos, então não há ambiguidade em
    # percorrer todos. Achado A11 da auditoria (E15): a versão anterior
    # pegava só o PRIMEIRO e ignorava em silêncio um segundo elemento de
    # código — um evento com `<e202201/>` E `<e101101/>` (mal formado, mas
    # aceito por engano) tratava o evento como o primeiro dos dois, sem
    # avisar. Mais de um código agora é recusado explicitamente.
    codigos_encontrados = []
    for filho in inf_ped_reg:
        if "}" not in filho.tag:
            continue
        _, _, filho_local = filho.tag[1:].partition("}")
        if _FORMATO_CODIGO_EVENTO.fullmatch(filho_local):
            codigos_encontrados.append(filho_local)
    if not codigos_encontrados:
        raise ArquivoRecusado("evento sem código reconhecível (elemento eNNNNNN ausente).")
    if len(codigos_encontrados) > 1:
        raise ArquivoRecusado(
            f"evento com mais de um código reconhecível: {codigos_encontrados!r}."
        )
    codigo = codigos_encontrados[0]

    # Achado A11 (E13/E14): o `Id` do evento (TSIdEvento = "EVT" + chave(50)
    # + tipo do evento(6) + nº do pedido(3)) TRAZ a chave e o código dentro
    # de si mesmo, codificados — o formato já foi conferido acima
    # (`_FORMATO_ID_EVENTO`), mas nada garantia que os dígitos INTERNOS do
    # Id batessem com `chNFSe`/o código realmente usado. Um Id forjado com
    # a chave de OUTRA nota (ou o código de outro tipo de evento) passava
    # sem aviso. As posições abaixo são 1-indexed no XSD ("EVT" ocupa as 3
    # primeiras); em índice 0-based do Python: chave em [3:53], tipo do
    # evento (6 dígitos, sem o "e" do código) em [53:59].
    chave_no_id = identificador[3:53]
    tipo_no_id = identificador[53:59]
    if chave_no_id != chave_nfse:
        raise ArquivoRecusado(
            f"Id do evento não confere com chNFSe: Id traz {chave_no_id!r}, "
            f"chNFSe é {chave_nfse!r}."
        )
    if tipo_no_id != codigo[1:]:
        raise ArquivoRecusado(
            f"Id do evento não confere com o código: Id traz tipo {tipo_no_id!r}, "
            f"código é {codigo!r}."
        )

    return EventoLido(
        identificador=identificador,
        codigo=codigo,
        chave_nfse=chave_nfse,
        data_evento=data_evento,
        autor=autor,
        xml_bytes=conteudo,
        sha256=sha256,
    )
