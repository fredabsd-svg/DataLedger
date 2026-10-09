"""DL-080 (frente A), leitor da NF-e: aceitos, recusas nomeadas e conferências. Sem banco.

Cada caso monta um XML sintético com `xml_nfe_dl080` (leiaute 4.00, caminhos da pesquisa do
leiaute, seção 1) e verifica o resultado pelo leitor de verdade (`apps.fiscal.leitor.ler_arquivo`).
A mensagem de recusa é conferida pelo trecho que o contador vê; a regra por trás está no comentário
do próprio leitor.
"""

import hashlib
from decimal import Decimal

import pytest

from apps.fiscal import leitor, leitor_nfe
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_ALFANUMERICO,
    CNPJ_DE_FORA,
    CPF_CLIENTE,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
    xml_raiz_generica,
)


def _ler(conteudo: bytes):
    return leitor.ler_arquivo(conteudo, hashlib.sha256(conteudo).hexdigest())


# --- Aceitos -------------------------------------------------------------------------


def test_nfe_55_autorizada_e_lida_pelos_campos_da_pesquisa():
    lido = _ler(xml_nfe(itens=3))
    assert isinstance(lido, leitor_nfe.DocumentoNFeLido)
    assert lido.modelo == "55"
    assert lido.versao == "4.00"
    assert len(lido.chave) == 44 and lido.chave.startswith("35260110")
    assert lido.serie == "1" and lido.numero == "1"
    assert lido.tp_nf == "1" and lido.fin_nfe == "1" and lido.id_dest == "1"
    assert lido.c_uf == "35"
    assert lido.emitente.tipo_documento == "CNPJ"
    assert lido.emitente.nome == "Emitente Sintetico Ltda"
    assert lido.destinatario is not None and lido.destinatario.tipo_documento == "CNPJ"
    assert lido.c_stat == "100"
    assert lido.n_prot == "135260000000001"
    assert lido.quantidade_itens == 3


def test_nfe_autorizada_com_cstat_150_tambem_entra():
    lido = _ler(xml_nfe(c_stat="150"))
    assert lido.c_stat == "150"


def test_nfce_65_sem_destinatario_e_aceita():
    # `dest` é opcional no XSD (leiauteNFe_v4.00.xsd:734) e a NFC-e normalmente não o traz.
    lido = _ler(xml_nfe(modelo="65", destinatario=None))
    assert lido.modelo == "65"
    assert lido.destinatario is None


def test_chave_com_cnpj_alfanumerico_valido_e_aceita():
    # NT Conjunta 2025.001: CNPJ alfanumérico, DV pelo ASCII - 48 (pesquisa, seção 3).
    chave = chave_nfe(emitente=CNPJ_ALFANUMERICO)
    lido = _ler(xml_nfe(chave=chave, emitente=("CNPJ", CNPJ_ALFANUMERICO)))
    assert lido.chave == chave
    assert lido.emitente.documento == CNPJ_ALFANUMERICO


def test_destinatario_estrangeiro_e_lido_como_id_estrangeiro():
    lido = _ler(xml_nfe(destinatario=("idEstrangeiro", "EX-0001")))
    assert lido.destinatario.tipo_documento == "idEstrangeiro"
    assert lido.destinatario.documento == "EX-0001"


def test_destinatario_pessoa_fisica_e_lido_como_cpf():
    lido = _ler(xml_nfe(destinatario=("CPF", CPF_CLIENTE)))
    assert lido.destinatario.tipo_documento == "CPF"
    assert lido.destinatario.documento == CPF_CLIENTE


def test_emitente_pessoa_fisica_e_lido_como_cpf():
    # Produtor rural com CPF: a chave leva o CPF com zeros à esquerda (14 posições).
    lido = _ler(xml_nfe(emitente=("CPF", CPF_CLIENTE), destinatario=None, modelo="55"))
    assert lido.emitente.tipo_documento == "CPF"
    assert lido.emitente.documento == CPF_CLIENTE


# --- Recusas nomeadas por raiz e versão (HI-110) ------------------------------------


def test_nfe_sem_protocolo_e_recusada_pelo_nome():
    with pytest.raises(leitor.ArquivoRecusado, match="NF-e sem protocolo de autorização"):
        _ler(xml_nfe(raiz="NFe"))


def test_nfe_proc_sem_protocolo_e_recusada_pelo_nome():
    with pytest.raises(leitor.ArquivoRecusado, match="NF-e sem protocolo de autorização"):
        _ler(xml_nfe(incluir_protocolo=False))


@pytest.mark.parametrize(
    "raiz",
    [
        "enviNFe",
        "retEnviNFe",
        "envEvento",
        "procInutNFe",
        "retInutNFe",
        "resNFe",
        "resEvento",
        "retConsSitNFe",
    ],
)
def test_raiz_que_nao_e_nota_e_recusada_com_o_proprio_nome(raiz):
    with pytest.raises(leitor.ArquivoRecusado, match=rf"\({raiz}\)"):
        _ler(xml_raiz_generica(raiz))


def test_raiz_desconhecida_no_namespace_da_nfe_e_recusada_com_o_nome():
    with pytest.raises(leitor.ArquivoRecusado, match="'raizEstranha'"):
        _ler(xml_raiz_generica("raizEstranha"))


@pytest.mark.parametrize("versao", ["1.10", "2.00", "3.00", "3.10"])
def test_leiaute_antigo_e_recusado_com_a_versao_nomeada(versao):
    with pytest.raises(
        leitor.ArquivoRecusado,
        match=rf"NF-e no leiaute {versao}; só o leiaute 4\.00 é aceito",
    ):
        _ler(xml_nfe(versao_raiz=versao, versao=versao))


def test_leiaute_antigo_em_nfe_sem_protocolo_e_nomeado_pela_versao():
    # A versão vem antes do protocolo: nota antiga é "leiaute antigo", não "sem protocolo".
    with pytest.raises(leitor.ArquivoRecusado, match="NF-e no leiaute 3.10"):
        _ler(xml_nfe(raiz="NFe", versao="3.10"))


def test_versao_desconhecida_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="versão desconhecida"):
        _ler(xml_nfe(versao_raiz="9.99", versao="9.99"))


# --- Chave, Id e protocolo (HI-109, critério 2) ------------------------------------


def test_dv_errado_da_chave_e_recusado():
    chave = chave_nfe(emitente="10020030040093")
    dv_errado = str((int(chave[43]) + 1) % 10)
    with pytest.raises(leitor.ArquivoRecusado, match="Dígito verificador"):
        _ler(xml_nfe(chave=chave[:43] + dv_errado))


def test_chave_do_protocolo_diferente_do_id_e_recusada():
    outra = chave_nfe(emitente="10020030040093", numero="2")
    with pytest.raises(leitor.ArquivoRecusado, match="Chave do protocolo diferente"):
        _ler(xml_nfe(chave_protocolo=outra))


def test_id_fora_do_padrao_e_recusado():
    # 43 posições: falta uma. (Com 44 dígitos o Id casa o padrão, e a recusa é do DV.)
    with pytest.raises(leitor.ArquivoRecusado, match="Id da NF-e fora do padrão"):
        _ler(xml_nfe(id_nfe="NFe" + "1" * 43))


def test_id_com_prefixo_errado_e_recusado():
    chave = chave_nfe(emitente="10020030040093")
    with pytest.raises(leitor.ArquivoRecusado, match="Id da NF-e fora do padrão"):
        _ler(xml_nfe(chave=chave, id_nfe=f"NFA{chave}"))


@pytest.mark.parametrize("c_stat", ["110", "301", "302", "303"])
def test_nfe_denegada_e_recusada_sem_efeito_fiscal(c_stat):
    # HI-109: denegada não entra, e o motivo é o nome do efeito (MOC 7.0:4095-4108).
    with pytest.raises(leitor.ArquivoRecusado, match="NF-e denegada — sem efeito fiscal"):
        _ler(xml_nfe(c_stat=c_stat))


def test_status_nao_autorizado_e_recusado_com_o_codigo():
    with pytest.raises(leitor.ArquivoRecusado, match="cStat 999"):
        _ler(xml_nfe(c_stat="999"))


# --- Valores pelo padrão TDec_1302 (critério 4) -------------------------------------


def test_totais_entram_como_decimal():
    lido = _ler(xml_nfe(totais={"vNF": "1234567890123.45", "vProd": "100"}))
    assert isinstance(lido.v_nf, Decimal)
    assert lido.v_nf == Decimal("1234567890123.45")
    assert lido.v_prod == Decimal("100")


@pytest.mark.parametrize(
    "valor_fora_do_padrao",
    ["1,00", "-1.00", "1.5", "01.00", "1e3", " 1.00", "12345678901234.00", "0.005"],
)
def test_valor_fora_do_padrao_tdec_1302_e_recusado_citando_o_campo(valor_fora_do_padrao):
    with pytest.raises(leitor.ArquivoRecusado, match="vNF"):
        _ler(xml_nfe(totais={"vNF": valor_fora_do_padrao}))


def test_valor_ausente_fica_none_e_nao_vira_zero():
    lido = _ler(xml_nfe(totais={"vICMS": None, "vIPI": None}))
    assert lido.v_icms is None
    assert lido.v_ipi is None
    assert lido.v_nf == Decimal("100.00")


def test_valor_vazio_e_recusado_e_nao_vira_zero():
    with pytest.raises(leitor.ArquivoRecusado, match="vICMS"):
        _ler(xml_nfe(totais={"vICMS": ""}))


# --- Identificação e conferências da chave (ide) -------------------------------------


def test_modelo_da_chave_diferente_do_ide_e_recusado():
    chave_de_55 = chave_nfe(emitente="10020030040093", modelo="55")
    with pytest.raises(leitor.ArquivoRecusado, match="Modelo da chave diferente"):
        _ler(xml_nfe(modelo="65", chave=chave_de_55))


def test_serie_da_chave_diferente_do_ide_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="Série da chave diferente"):
        _ler(xml_nfe(chave=chave_nfe(emitente="10020030040093", serie="2")))


def test_numero_da_chave_diferente_do_ide_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="Número da chave diferente"):
        _ler(xml_nfe(chave=chave_nfe(emitente="10020030040093", numero="2")))


def test_cuf_da_chave_diferente_do_ide_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="cUF da chave diferente"):
        _ler(xml_nfe(c_uf_ide="41"))


def test_modelo_fora_do_dominio_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="'mod' fora do domínio"):
        _ler(xml_nfe(modelo="99", chave=chave_nfe(emitente="10020030040093", modelo="99")))


def test_ambiente_de_homologacao_e_recusado_como_sem_valor_fiscal():
    with pytest.raises(leitor.ArquivoRecusado, match="homologação"):
        _ler(xml_nfe(tp_amb="2"))


def test_tp_nf_fora_do_dominio_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="'tpNF' fora do domínio"):
        _ler(xml_nfe(tp_nf="2"))


def test_data_de_emissao_sem_fuso_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="dhEmi"):
        _ler(xml_nfe(dh_emi="2026-01-15T10:00:00"))


def test_data_de_emissao_com_z_e_recusada_pois_o_xsd_nao_admite():
    with pytest.raises(leitor.ArquivoRecusado, match="dhEmi"):
        _ler(xml_nfe(dh_emi="2026-01-15T10:00:00Z"))


def test_data_de_emissao_com_fuso_de_hora_cheia_e_aceita_com_o_fuso_lido():
    lido = _ler(xml_nfe(dh_emi="2026-01-15T10:00:00-03:00"))
    assert lido.dh_emissao.utcoffset().total_seconds() == -3 * 3600


def test_data_fora_do_calendario_e_recusada():
    with pytest.raises(leitor.ArquivoRecusado, match="inválida|fora do padrão"):
        _ler(xml_nfe(dh_emi="2026-04-31T10:00:00-03:00"))


def test_nome_do_destinatario_acima_de_60_caracteres_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="xNome de destinatário"):
        _ler(xml_nfe(destinatario_nome="X" * 61))


# --- Itens e IBS/CBS: só presença e contagem ----------------------------------------


def test_itens_so_sao_contados():
    assert _ler(xml_nfe(itens=990)).quantidade_itens == 990


def test_ibscbs_so_informa_presenca_do_total_e_do_item():
    sem = _ler(xml_nfe())
    assert sem.tem_ibscbs_total is False and sem.tem_ibscbs_item is False
    com = _ler(xml_nfe(ibscbs_total=True, ibscbs_item=True))
    assert com.tem_ibscbs_total is True and com.tem_ibscbs_item is True


# --- Eventos (procEventoNFe) ----------------------------------------------------------


def test_evento_de_cancelamento_com_retorno_135_e_lido():
    lido = _ler(proc_evento_xml(tp_evento="110111", c_stat="135"))
    assert isinstance(lido, leitor_nfe.EventoNFeLido)
    assert lido.tp_evento == "110111"
    assert lido.c_stat == "135"
    assert lido.n_seq_evento == 1
    assert lido.identificador == "ID110111" + lido.chave + "01"
    assert len(lido.identificador) == 54
    assert lido.autor.tipo_documento == "CNPJ"


def test_evento_sem_retorno_tem_c_stat_none():
    assert _ler(proc_evento_xml(c_stat=None)).c_stat is None


def test_retorno_sem_codigo_de_status_tem_c_stat_none():
    assert _ler(proc_evento_xml(c_stat_retorno_sem_codigo=True)).c_stat is None


def test_retorno_com_status_fora_dos_efetivos_e_lido_e_fica_para_o_servico():
    # O leitor só lê. Quem decide o efeito é o serviço (CODIGOS_EFETIVOS_NFE).
    assert _ler(proc_evento_xml(c_stat="128")).c_stat == "128"


def test_retorno_de_outra_nfe_e_recusado():
    outra = chave_nfe(emitente="10020030040093", numero="9")
    with pytest.raises(leitor.ArquivoRecusado, match="outra NF-e"):
        _ler(proc_evento_xml(chave_retorno=outra))


def test_id_do_evento_que_nao_confere_com_o_corpo_e_recusado():
    chave = chave_nfe(emitente="10020030040093")
    with pytest.raises(leitor.ArquivoRecusado, match="não confere"):
        _ler(proc_evento_xml(chave=chave, id_evento=f"ID110110{chave}01"))


def test_id_do_evento_fora_do_padrao_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="Id do evento fora do padrão"):
        _ler(proc_evento_xml(id_evento="EVT" + "0" * 51))


def test_numero_de_sequencia_que_nao_confere_com_o_id_e_recusado():
    chave = chave_nfe(emitente="10020030040093")
    with pytest.raises(leitor.ArquivoRecusado, match="não confere"):
        _ler(proc_evento_xml(chave=chave, n_seq=2, id_evento=f"ID110111{chave}01"))


def test_evento_com_chave_de_dv_errado_e_recusado():
    chave = chave_nfe(emitente="10020030040093")
    with pytest.raises(leitor.ArquivoRecusado, match="Dígito verificador"):
        _ler(proc_evento_xml(chave=chave[:43] + str((int(chave[43]) + 1) % 10)))


def test_evento_de_versao_desconhecida_e_recusado():
    with pytest.raises(leitor.ArquivoRecusado, match="versão de evento desconhecida"):
        _ler(proc_evento_xml(versao="2.00"))


def test_evento_com_autor_pessoa_fisica_e_lido_como_cpf():
    lido = _ler(proc_evento_xml(autor=("CPF", CPF_CLIENTE)))
    assert lido.autor.tipo_documento == "CPF"


def test_evento_de_outro_cnpj_autor_e_lido_com_o_documento_do_autor():
    lido = _ler(proc_evento_xml(autor=("CNPJ", CNPJ_DE_FORA)))
    assert lido.autor.documento == CNPJ_DE_FORA


# --- Detecção de namespace (limite por tipo, HI-112) ---------------------------------


def test_namespace_da_raiz_da_nfe_e_lido_sem_parse_completo():
    assert leitor.namespace_da_raiz(xml_nfe()) == leitor.NS_NFE


def test_namespace_da_raiz_da_nfse_e_o_da_nfse():
    from apps.fiscal.tests.xml_sinteticos import xml_nfse

    assert leitor.namespace_da_raiz(xml_nfse()) == leitor.NS_NFSE


def test_namespace_da_raiz_com_dtd_ou_lixo_nao_e_nfe():
    assert leitor.namespace_da_raiz(b"<!DOCTYPE x [<!ENTITY e SYSTEM 'f'>]><x/>") is None
    assert leitor.namespace_da_raiz(b"isto nao e xml") is None
    assert leitor.namespace_da_raiz(b"") is None


# --- cStat (TStat: 3 ou 4 dígitos, tiposBasico_v4.00.xsd:79-90) -----------------------


def test_retorno_de_evento_com_cstat_de_quatro_digitos_e_lido():
    # Quatro dígitos são válidos no TStat. Não podem cair no campo de 3 posições do banco.
    assert _ler(proc_evento_xml(c_stat="1000")).c_stat == "1000"


@pytest.mark.parametrize("c_stat", ["1", "12345", "1a3"])
def test_cstat_do_retorno_fora_do_tstat_e_recusado(c_stat):
    with pytest.raises(leitor.ArquivoRecusado, match="cStat do retorno"):
        _ler(proc_evento_xml(c_stat=c_stat))


@pytest.mark.parametrize("c_stat", ["1", "12345"])
def test_cstat_do_protocolo_fora_do_tstat_e_recusado(c_stat):
    with pytest.raises(leitor.ArquivoRecusado, match="'cStat' fora do formato"):
        _ler(xml_nfe(c_stat=c_stat))
