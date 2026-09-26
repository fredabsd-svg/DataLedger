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
    identificador_evento,
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
        f'<?xml version="1.0" encoding="UTF-8"?><outraCoisa xmlns="{leitor.NS_NFSE}"/>'
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


def test_id_com_52_caracteres_e_recusado():
    # Achado A9/F36 (auditoria rodada 1): um dígito A MENOS que os 50
    # exigidos (NFS + 49 dígitos = 52 caracteres, não 53) precisa ser
    # recusado — o teste anterior só cobria formatos claramente errados
    # (letra, "NFS123"), nunca o limite exato do comprimento.
    identificador_curto = "NFS" + "0" * 49
    assert len(identificador_curto) == 52
    with pytest.raises(leitor.ArquivoRecusado, match="Id fora do formato"):
        _ler(xml_nfse(identificador=identificador_curto))


def test_prestador_sem_cnpj_nem_cpf_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="prestador"):
        _ler(xml_nfse(prestador_tipo=None))


# --- Achado A1 (auditoria rodada 1): tamanhos do XSD conferidos ANTES da
# gravação — sem isso, um arquivo passava a leitura inteira e só estourava
# `django.db.DataError` na hora de gravar, derrubando o ENVIO INTEIRO com
# 500 em vez de recusar só o arquivo (critério 7/8 quebrado). ------------


def test_nnfse_acima_do_limite_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="nNFSe"):
        _ler(xml_nfse(numero="1" * 14, incluir_tomador=False))


def test_nnfse_no_limite_e_aceito():
    lido = _ler(xml_nfse(numero="1" * 13, incluir_tomador=False))
    assert lido.numero == "1" * 13


def test_xnome_do_prestador_acima_do_limite_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="xNome"):
        _ler(xml_nfse(prestador_nome="A" * 301, incluir_tomador=False))


def test_xnome_do_prestador_no_limite_e_aceito():
    lido = _ler(xml_nfse(prestador_nome="A" * 300, incluir_tomador=False))
    assert lido.prestador.nome == "A" * 300


def test_nif_do_tomador_acima_do_limite_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="NIF"):
        _ler(xml_nfse(tomador_tipo="NIF", tomador_documento="1" * 41))


def test_nif_do_tomador_no_limite_e_aceito():
    lido = _ler(xml_nfse(tomador_tipo="NIF", tomador_documento="1" * 40))
    assert lido.tomador.documento == "1" * 40


def test_codificacao_declarada_desconhecida_e_recusada():
    # Achado A1: `encoding="x-inexistente"` faz o parser levantar
    # `LookupError` ao tentar resolver o codec — sem tratamento, isso
    # derrubava o ENVIO INTEIRO com 500.
    conteudo = (
        b'<?xml version="1.0" encoding="x-inexistente"?>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b'<infNFSe Id="' + ("NFS" + "0" * 50).encode() + b'"/></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado, match="codifica"):
        _ler(conteudo)


# --- Achado A9/F35: versão vizinha da suportada, não só "claramente errada" --


def test_versao_1_02_e_recusada():
    # "2.00" (test_versao_nao_suportada_e_recusada, acima) está longe do
    # domínio suportado — "1.02" é o vizinho IMEDIATO de "1.01" (a última
    # versão suportada), o caso que de fato prova que o conjunto é
    # FECHADO ({"1.00", "1.01"}), não "qualquer coisa que comece com 1.0".
    with pytest.raises(leitor.ArquivoRecusado, match="versão não suportada"):
        _ler(xml_nfse(versao="1.02", incluir_tomador=False))


# --- Achado A11 (auditoria rodada 1 / DE-076 item 3): ambiente de
# homologação e coerência do evento -----------------------------------------


def test_nfse_em_homologacao_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="homologação"):
        _ler(xml_nfse(tp_amb="2", incluir_tomador=False))


def test_nfse_em_producao_e_aceita():
    lido = _ler(xml_nfse(tp_amb="1", incluir_tomador=False))
    assert isinstance(lido, leitor.DocumentoLido)


def test_nfse_sem_tpamb_nao_e_recusada_por_omissao():
    # A recusa vale só quando o valor é EXPLICITAMENTE "2" — nunca por
    # ausência do campo (caso residual de XML que não segue o esquema à
    # risca; adivinhar "homologação" por omissão seria pior que aceitar).
    lido = _ler(xml_nfse(tp_amb=None, incluir_tomador=False))
    assert isinstance(lido, leitor.DocumentoLido)


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
        b'<infNFSe Id="' + ("NFS" + "0" * 50).encode() + b'"/></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado, match="DTD|proibid"):
        _ler(conteudo)


def test_xml_com_dtd_simples_sem_entidade_e_recusado():
    # Achado A9/F18 (auditoria rodada 1): o teste acima (`test_xml_com_dtd_
    # e_recusado`) usa uma DTD com `<!ENTITY x "1">` — mesmo se `forbid_dtd`
    # virasse `False` por mutação, o `forbid_entities` (independente, TRUE
    # por padrão do defusedxml) ainda pegaria a ENTIDADE e a mensagem
    # continuaria batendo em `match="DTD|proibid"`, mascarando a mutação.
    # Este teste usa uma DTD SEM entidade nenhuma — só `forbid_dtd=True`
    # pode recusá-la; se a mutação zerar essa flag, este XML passa como
    # válido (e falha adiante por outro motivo, "sem prestador"), matando
    # o mutante de verdade.
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b"<!DOCTYPE NFSe>"
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b'<infNFSe Id="' + ("NFS" + "0" * 50).encode() + b'"/></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado, match="DTD|proibid"):
        _ler(conteudo)


def test_xml_com_entidade_externa_e_recusado():
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE NFSe [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b'<infNFSe Id="' + ("NFS" + "0" * 50).encode() + b'">&xxe;</infNFSe></NFSe>'
    )
    with pytest.raises(leitor.ArquivoRecusado):
        _ler(conteudo)


def test_xml_com_expansao_de_entidade_e_recusado():
    # "Billion laughs" reduzido — a defesa é o DTD proibido, então nem
    # chega a expandir a primeira entidade.
    conteudo = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE lolz [ <!ENTITY lol "lol">'
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


@pytest.mark.parametrize("codigo", ["e202201", "e203202", "e202205", "e305102", "e305103"])
def test_le_eventos_que_nao_cancelam_tambem(codigo):
    # O leitor lê QUALQUER evento reconhecível — a decisão de "cancela ou
    # não" é do serviço (HI-20), não do leitor.
    lido = _ler(xml_evento(codigo=codigo))
    assert lido.codigo == codigo


# --- Achado A11 (auditoria rodada 1): coerência entre Id, chNFSe e código --
#
# `TSIdEvento` ("EVT" + chave(50) + tipo do evento(6) + nº do pedido(3))
# TRAZ a chave e o código dentro de si mesmo, codificados. Antes desta
# correção, só o FORMATO do Id era conferido (regex EVT+59 dígitos) — um Id
# com a chave de OUTRA nota, ou com o tipo de OUTRO evento, passava sem
# aviso (experimentos E13/E14/E15 da auditoria).


def test_evento_com_id_que_traz_chave_diferente_de_chnfse_e_recusado():
    chave_real = chave_nfse_de(identificador_nfse(sufixo=201))
    chave_de_outra_nota = chave_nfse_de(identificador_nfse(sufixo=202))
    identificador_forjado = identificador_evento(chave_de_outra_nota, "e101101")
    with pytest.raises(leitor.ArquivoRecusado, match="não confere com chNFSe"):
        _ler(
            xml_evento(chave_nfse=chave_real, codigo="e101101", identificador=identificador_forjado)
        )


def test_evento_com_id_que_traz_tipo_diferente_do_codigo_e_recusado():
    chave = chave_nfse_de(identificador_nfse(sufixo=203))
    # O Id é construído para o código e105102, mas o elemento de código no
    # corpo do XML é e101101 — os dois têm que bater, e não batem aqui.
    identificador_com_outro_tipo = identificador_evento(chave, "e105102")
    with pytest.raises(leitor.ArquivoRecusado, match="não confere com o código"):
        _ler(
            xml_evento(
                chave_nfse=chave, codigo="e101101", identificador=identificador_com_outro_tipo
            )
        )


def test_evento_com_mais_de_um_elemento_de_codigo_e_recusado():
    # Achado A11/E15: a versão anterior pegava o PRIMEIRO elemento
    # reconhecível e ignorava um segundo em silêncio (e202201 "vencia"
    # e101101 só por vir depois no percurso). Construído manualmente
    # porque `xml_evento()` só admite um código por vez.
    chave = chave_nfse_de(identificador_nfse(sufixo=204))
    identificador = identificador_evento(chave, "e101101")
    conteudo = f"""<evento xmlns="{leitor.NS_NFSE}" versao="1.01">
  <infEvento Id="{identificador}">
    <pedRegEvento versao="1.01">
      <infPedReg Id="PRE{"0" * 56}">
        <dhEvento>2024-01-20T10:00:00-03:00</dhEvento>
        <chNFSe>{chave}</chNFSe>
        <e101101><xDesc>Primeiro</xDesc></e101101>
        <e202201><xDesc>Segundo</xDesc></e202201>
      </infPedReg>
    </pedRegEvento>
  </infEvento>
</evento>""".encode()
    with pytest.raises(leitor.ArquivoRecusado, match="mais de um código"):
        _ler(conteudo)


# --- Tipagem defensiva -------------------------------------------------


def test_ler_arquivo_recusa_str_em_vez_de_bytes():
    with pytest.raises(TypeError):
        leitor.ler_arquivo("<NFSe/>", "sha")
