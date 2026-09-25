"""Testes de `apps.fiscal.leitor` — leitura pura de XML, sem banco de dados.

Cobre os critérios do plano DL-010-F1 que são responsabilidade do LEITOR:
18 (classificação pelo conteúdo), 19 (1.00 e 1.01), 20 (CPF em qualquer
papel), 21 (variações de arquivo), 22 (zero à esquerda), 24 (DTD/entidade),
32 (Decimal estrito) — e os cenários "Recusa"/"Variação de arquivo" da
seção "Cenários de teste obrigatórios" do plano.
"""

from __future__ import annotations

import hashlib

import pytest

from apps.fiscal import leitor
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_COM_ZERO_A_ESQUERDA,
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfe_minimo,
    xml_nfse,
)


def _ler(conteudo: bytes):
    return leitor.ler_arquivo(conteudo, hashlib.sha256(conteudo).hexdigest())


# --- Sucesso -----------------------------------------------------------


@pytest.mark.parametrize("versao", ["1.00", "1.01"])
def test_le_nfse_nas_duas_versoes_suportadas(versao):
    # Critério 19 / RC-72.
    lido = _ler(xml_nfse(versao=versao))
    assert isinstance(lido, leitor.DocumentoLido)
    assert lido.versao == versao


def test_le_nfse_com_prestador_cpf():
    # Critério 20 / RC-73 — CPF no PRESTADOR.
    lido = _ler(xml_nfse(prestador_tipo="CPF", prestador_documento="12345678909"))
    assert lido.prestador.tipo_documento == "CPF"
    assert lido.prestador.documento == "12345678909"


def test_le_nfse_com_tomador_cpf():
    # Critério 20 / RC-73 — CPF no TOMADOR.
    lido = _ler(xml_nfse(tomador_tipo="CPF", tomador_documento="98765432100"))
    assert lido.tomador.tipo_documento == "CPF"
    assert lido.tomador.documento == "98765432100"


def test_tomador_ausente_e_aceito_como_none():
    # O tomador é OPCIONAL no esquema (armadilha 1 do plano-mãe, aplicada à
    # NFS-e): ausência não é malformação.
    lido = _ler(xml_nfse(incluir_tomador=False))
    assert lido.tomador is None


def test_tomador_com_nif():
    lido = _ler(xml_nfse(tomador_tipo="NIF", tomador_documento="US123456789"))
    assert lido.tomador.tipo_documento == "NIF"


def test_tomador_com_c_nao_nif():
    lido = _ler(xml_nfse(tomador_tipo="nao_informado", tomador_documento="1"))
    assert lido.tomador.tipo_documento == "nao_informado"
    assert lido.tomador.documento == ""


def test_numero_com_zero_a_esquerda_permanece_texto():
    # RC-75/critério 22: identificador NUNCA passa por conversão numérica.
    lido = _ler(xml_nfse(numero="0000000000007"))
    assert lido.numero == "0000000000007"
    assert isinstance(lido.numero, str)


def test_cnpj_com_zero_a_esquerda_permanece_texto():
    lido = _ler(xml_nfse(prestador_documento=CNPJ_COM_ZERO_A_ESQUERDA))
    assert lido.prestador.documento == CNPJ_COM_ZERO_A_ESQUERDA


def test_acentuacao_em_razao_social_nao_corrompe():
    lido = _ler(xml_nfse(prestador_nome="Confeitaria Ápice & Cia. Açúcar Ltda"))
    assert lido.prestador.nome == "Confeitaria Ápice & Cia. Açúcar Ltda"


# --- RC-75: variações de arquivo ----------------------------------------


def test_sem_declaracao_de_codificacao():
    lido = _ler(xml_nfse(declaracao=None))
    assert isinstance(lido, leitor.DocumentoLido)


def test_declaracao_utf8_maiuscula():
    lido = _ler(xml_nfse(declaracao="UTF-8"))
    assert isinstance(lido, leitor.DocumentoLido)


def test_declaracao_utf8_minuscula():
    lido = _ler(xml_nfse(declaracao="utf-8"))
    assert isinstance(lido, leitor.DocumentoLido)


def test_quebra_de_linha_crlf():
    lido = _ler(xml_nfse(crlf=True))
    assert isinstance(lido, leitor.DocumentoLido)


def test_xml_minificado():
    lido = _ler(xml_nfse(minificado=True))
    assert isinstance(lido, leitor.DocumentoLido)


def test_xml_indentado():
    lido = _ler(xml_nfse(minificado=False))
    assert isinstance(lido, leitor.DocumentoLido)


# --- Classificação pelo conteúdo (RC-71/critério 18) ---------------------


def test_classifica_evento_mesmo_com_nome_de_arquivo_enganoso():
    # O conteúdo decide, nunca o nome do arquivo — aqui simulado por não
    # existir "nome de arquivo" nenhum na entrada do leitor: ele só recebe
    # bytes. O teste prova que um EVENTO é reconhecido como evento pelo
    # elemento raiz, independentemente de qualquer rótulo externo.
    conteudo = xml_evento()
    lido = _ler(conteudo)
    assert isinstance(lido, leitor.EventoLido)


def test_nfe_e_recusada_com_motivo_especifico():
    with pytest.raises(leitor.ArquivoRecusado, match="NF-e"):
        _ler(xml_nfe_minimo())


def test_namespace_desconhecido_e_recusado_com_motivo_generico():
    conteudo = b'<?xml version="1.0" encoding="UTF-8"?><raiz xmlns="urn:outro:formato"/>'
    with pytest.raises(leitor.ArquivoRecusado, match="tipo ainda não suportado"):
        _ler(conteudo)


def test_elemento_raiz_sem_namespace_e_recusado():
    conteudo = b'<?xml version="1.0" encoding="UTF-8"?><raiz/>'
    with pytest.raises(leitor.ArquivoRecusado, match="sem espaço de nomes"):
        _ler(conteudo)


def test_elemento_raiz_desconhecido_no_namespace_da_nfse_e_recusado():
    conteudo = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<outraCoisa xmlns="{leitor.NS_NFSE}"/>'
    ).encode()
    with pytest.raises(leitor.ArquivoRecusado, match="tipo ainda não suportado"):
        _ler(conteudo)


# --- Recusas de formato/limite -------------------------------------------


def test_xml_vazio_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="vazio"):
        _ler(b"")


def test_xml_malformado_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="malformado"):
        _ler(b"<NFSe><infNFSe>")


def test_xml_truncado_e_recusado():
    conteudo = xml_nfse()
    truncado = conteudo[: len(conteudo) // 2]
    with pytest.raises(leitor.ArquivoRecusado):
        _ler(truncado)


def test_versao_nao_suportada_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="versão não suportada"):
        _ler(xml_nfse(versao="2.00"))


def test_id_fora_do_formato_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="Id fora do formato"):
        _ler(xml_nfse(identificador="NFS123"))


def test_id_com_letra_e_recusado():
    # O XSD só admite dígitos nas 50 posições do Id — RC-46/limite
    # declarado no plano da etapa.
    identificador_invalido = "NFS" + "A" * 50
    with pytest.raises(leitor.ArquivoRecusado, match="Id fora do formato"):
        _ler(xml_nfse(identificador=identificador_invalido))


def test_prestador_sem_cnpj_nem_cpf_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="prestador"):
        _ler(xml_nfse(prestador_tipo=None))


# --- Decimal estrito (critério 32 / DE-010) -------------------------------


@pytest.mark.parametrize(
    "v_serv_invalido",
    [
        "100,00",  # vírgula
        "-100.00",  # negativo
        "100.005",  # mais de 2 casas
        "cem reais",  # não numérico
        "",  # vazio
    ],
)
def test_vserv_invalido_e_recusado(v_serv_invalido):
    with pytest.raises(leitor.ArquivoRecusado, match="vServ"):
        _ler(xml_nfse(v_serv=v_serv_invalido))


@pytest.mark.parametrize(
    "v_liq_invalido",
    ["100,00", "-1.00", "1.005", "abc"],
)
def test_vliq_invalido_e_recusado(v_liq_invalido):
    with pytest.raises(leitor.ArquivoRecusado, match="vLiq"):
        _ler(xml_nfse(v_liq=v_liq_invalido))


def test_valores_decimais_sao_decimal_nunca_float():
    from decimal import Decimal

    lido = _ler(xml_nfse(v_serv="12345678901234.56", v_liq="0.01"))
    assert isinstance(lido.v_serv, Decimal)
    assert lido.v_serv == Decimal("12345678901234.56")
    assert lido.v_liq == Decimal("0.01")


def test_tp_ret_issqn_fora_do_dominio_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="tpRetISSQN"):
        _ler(xml_nfse(tp_ret_issqn="9"))


@pytest.mark.parametrize("codigo", ["1", "2", "3"])
def test_tp_ret_issqn_valido_e_preservado_sem_interpretacao(codigo):
    # RC-110: o código é lido e exibido, nunca interpretado nesta fatia.
    lido = _ler(xml_nfse(tp_ret_issqn=codigo))
    assert lido.tp_ret_issqn == codigo


# --- Segurança: DTD e entidade externa (critério 24) ----------------------


def test_xml_com_dtd_e_recusado():
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE NFSe [<!ENTITY x "1">]>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b"<infNFSe Id=\"" + ("NFS" + "0" * 50).encode() + b'"/></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado, match="DTD|proibid"):
        _ler(conteudo)


def test_xml_com_entidade_externa_e_recusado():
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE NFSe [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b"<infNFSe Id=\"" + ("NFS" + "0" * 50).encode() + b'">&xxe;</infNFSe></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado):
        _ler(conteudo)


def test_xml_com_expansao_de_entidade_e_recusado():
    # "Billion laughs" reduzido — a defesa é o DTD proibido, então nem
    # chega a expandir a primeira entidade.
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<!DOCTYPE lolz [ <!ENTITY lol \"lol\">"
        b'<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>'
        b"<NFSe><infNFSe>&lol2;</infNFSe></NFSe>"
    )
    with pytest.raises(leitor.ArquivoRecusado):
        _ler(conteudo)


# --- Evento ----------------------------------------------------------------


def test_le_evento_com_codigo_e_chave_corretos():
    identificador_nota = identificador_nfse(sufixo=42)
    chave = chave_nfse_de(identificador_nota)
    lido = _ler(xml_evento(chave_nfse=chave, codigo="e101101"))
    assert isinstance(lido, leitor.EventoLido)
    assert lido.codigo == "e101101"
    assert lido.chave_nfse == chave


def test_evento_com_autor_cpf():
    lido = _ler(xml_evento(autor_tipo="CPF", autor_documento="12345678909"))
    assert lido.autor.tipo_documento == "CPF"


def test_evento_sem_autor_e_aceito():
    lido = _ler(xml_evento(autor_tipo=None))
    assert lido.autor is None


def test_evento_chave_fora_do_formato_e_recusado():
    # Desacopla o Id (que precisa ter formato válido para o teste isolar a
    # checagem de chNFSe) do valor de chNFSe propriamente dito, que é o
    # campo malformado sob teste.
    identificador_valido = identificador_evento(chave_nfse_de(identificador_nfse()), "e101101")
    with pytest.raises(leitor.ArquivoRecusado, match="chNFSe"):
        _ler(xml_evento(identificador=identificador_valido, chave_nfse="123"))


@pytest.mark.parametrize(
    "codigo", ["e202201", "e203202", "e202205", "e305102", "e305103"]
)
def test_le_eventos_que_nao_cancelam_tambem(codigo):
    # O leitor lê QUALQUER evento reconhecível — a decisão de "cancela ou
    # não" é do serviço (HI-20), não do leitor.
    lido = _ler(xml_evento(codigo=codigo))
    assert lido.codigo == codigo


# --- Tipagem defensiva -------------------------------------------------


def test_ler_arquivo_recusa_str_em_vez_de_bytes():
    with pytest.raises(TypeError):
        leitor.ler_arquivo("<NFSe/>", "sha")
