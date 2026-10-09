"""DL-080, rodada 1 (A6): o leitor real lê o corpus validado contra o XSD.

O corpus é `xml_nfe_xsd_dl080` (construtores do auditor, validados com `xmllint --schema` contra
os XSD do PL 010f e do PL 010d). Os casos cobrem: nfeProc, NFC-e, CNPJ alfanumérico,
idEstrangeiro, emitente e destinatário CPF, tpNFDebito, IBS/CBS, 990 itens, retirada e entrega,
e procEventoNFe. Todos sintéticos.

A parte que roda com `xmllint` só existe quando o binário E a pasta dos XSD existem
(`DL080_XSD_DIR`, com procNFe_v4.00.xsd e procEventoNFe_v1.00.xsd). Os XSD não entram no
repositório. Sem os dois, o teste NÃO é criado (não aparece como pulado): a limitação está no
relatório da rodada 1, e a leitura do corpus acima roda sempre.
"""

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from apps.fiscal import leitor, leitor_nfe
from apps.fiscal.tests import xml_nfe_xsd_dl080 as corpus

CNPJ_EMITENTE = corpus.cnpj_valido("100200300400")
CNPJ_DESTINATARIO = corpus.cnpj_valido("200300400500")
CNPJ_RETIRADA = corpus.cnpj_valido("300400500600")
CPF_ENTREGA = corpus.cpf_valido("111222333")


def _casos_nfe() -> dict[str, bytes]:
    """Cada caso do corpus de NF-e, por nome. Montados aqui, para o teste ser autocontido."""
    emitente = ("CNPJ", CNPJ_EMITENTE)
    destinatario = ("CNPJ", CNPJ_DESTINATARIO)
    return {
        "nfeproc": corpus.xml_nfe_valido(emitente=emitente, destinatario=destinatario),
        "nfce_65_sem_destinatario": corpus.xml_nfe_valido(
            emitente=emitente, destinatario=None, mod="65"
        ),
        "cnpj_alfanumerico": corpus.xml_nfe_valido(
            emitente=("CNPJ", corpus.cnpj_valido("12ABC34501DE")), destinatario=destinatario
        ),
        "destinatario_id_estrangeiro": corpus.xml_nfe_valido(
            emitente=emitente, destinatario=("idEstrangeiro", "EX123456789")
        ),
        "emitente_e_destinatario_cpf": corpus.xml_nfe_valido(
            emitente=("CPF", corpus.cpf_valido("123456789")),
            destinatario=("CPF", corpus.cpf_valido("987654321")),
        ),
        "tp_nf_debito": corpus.xml_nfe_valido(
            emitente=emitente, destinatario=destinatario, tp_nf_debito="01"
        ),
        "ibs_cbs_item_e_total": corpus.xml_nfe_valido(
            emitente=emitente, destinatario=destinatario, ibs_item=True, ibs_total=True
        ),
        "990_itens": corpus.xml_nfe_valido(emitente=emitente, destinatario=destinatario, itens=990),
        "retirada_e_entrega_de_terceiros": corpus.xml_nfe_valido(
            emitente=emitente,
            destinatario=destinatario,
            retirada=("CNPJ", CNPJ_RETIRADA),
            entrega=("CPF", CPF_ENTREGA),
        ),
    }


def _caso_evento() -> bytes:
    chave = corpus.chave_valida(doc14=CNPJ_EMITENTE, nnf="7")
    return corpus.xml_evento_valido(chave=chave, autor=("CNPJ", CNPJ_EMITENTE), c_stat="135")


def _ler(conteudo: bytes):
    return leitor.ler_arquivo(conteudo, hashlib.sha256(conteudo).hexdigest())


# --- Leitura pelo leitor real (sempre roda) -----------------------------------------------


def test_nfeproc_do_corpus_e_lida_com_os_campos_do_xsd():
    lido = _ler(_casos_nfe()["nfeproc"])
    assert isinstance(lido, leitor_nfe.DocumentoNFeLido)
    assert (lido.modelo, lido.versao, lido.c_stat) == ("55", "4.00", "100")
    assert lido.emitente == leitor_nfe.ParticipanteNFeLido(
        "CNPJ", CNPJ_EMITENTE, "Emitente Sintetico Ltda"
    )
    assert lido.destinatario.documento == CNPJ_DESTINATARIO
    assert lido.v_nf is not None and str(lido.v_nf) == "100.00"


def test_nfce_do_corpus_e_lida_sem_destinatario():
    lido = _ler(_casos_nfe()["nfce_65_sem_destinatario"])
    assert lido.modelo == "65"
    assert lido.destinatario is None


def test_cnpj_alfanumerico_do_corpus_e_aceito_com_a_chave_do_mesmo_cnpj():
    lido = _ler(_casos_nfe()["cnpj_alfanumerico"])
    cnpj = corpus.cnpj_valido("12ABC34501DE")
    assert lido.emitente.documento == cnpj
    assert lido.chave[6:20] == cnpj


def test_destinatario_id_estrangeiro_do_corpus_e_lido_como_id_estrangeiro():
    lido = _ler(_casos_nfe()["destinatario_id_estrangeiro"])
    assert lido.destinatario.tipo_documento == "idEstrangeiro"
    assert lido.destinatario.documento == "EX123456789"


def test_emitente_e_destinatario_cpf_do_corpus_sao_lidos_como_cpf():
    lido = _ler(_casos_nfe()["emitente_e_destinatario_cpf"])
    assert lido.emitente.tipo_documento == "CPF"
    assert lido.emitente.documento == corpus.cpf_valido("123456789")
    assert lido.destinatario.tipo_documento == "CPF"


def test_tp_nf_debito_do_corpus_e_lido():
    assert _ler(_casos_nfe()["tp_nf_debito"]).tp_nf_debito == "01"


def test_ibs_cbs_do_corpus_e_presente_no_total_e_no_item():
    lido = _ler(_casos_nfe()["ibs_cbs_item_e_total"])
    assert (lido.tem_ibscbs_total, lido.tem_ibscbs_item) == (True, True)


def test_990_itens_do_corpus_sao_contados():
    assert _ler(_casos_nfe()["990_itens"]).quantidade_itens == 990


def test_retirada_e_entrega_do_corpus_nao_mudam_quem_e_o_participante():
    # A3/A8: retirada e entrega de terceiros não são partes da operação. A leitura segue `emit`
    # e `dest`, e só eles.
    lido = _ler(_casos_nfe()["retirada_e_entrega_de_terceiros"])
    assert lido.emitente.documento == CNPJ_EMITENTE
    assert lido.destinatario.documento == CNPJ_DESTINATARIO


def test_evento_do_corpus_e_lido_com_o_status_do_retorno():
    lido = _ler(_caso_evento())
    assert isinstance(lido, leitor_nfe.EventoNFeLido)
    assert (lido.tp_evento, lido.n_seq_evento, lido.c_stat) == ("110111", 1, "135")


# --- Validação contra o XSD (só com xmllint e a pasta dos XSD) ----------------------------

_XMLLINT = shutil.which("xmllint")
_DIR_XSD = os.environ.get("DL080_XSD_DIR", "")

if _XMLLINT and _DIR_XSD and Path(_DIR_XSD, "procNFe_v4.00.xsd").is_file():

    @pytest.mark.parametrize("nome", sorted(_casos_nfe()))
    def test_corpus_nfe_valida_contra_o_procnfe_xsd(tmp_path, nome):
        arquivo = tmp_path / f"{nome}.xml"
        arquivo.write_bytes(_casos_nfe()[nome])
        resultado = subprocess.run(
            [
                _XMLLINT,
                "--noout",
                "--schema",
                str(Path(_DIR_XSD, "procNFe_v4.00.xsd")),
                str(arquivo),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultado.returncode == 0, resultado.stderr

    def test_corpus_evento_valida_contra_o_proc_evento_xsd(tmp_path):
        arquivo = tmp_path / "evento.xml"
        arquivo.write_bytes(_caso_evento())
        resultado = subprocess.run(
            [
                _XMLLINT,
                "--noout",
                "--schema",
                str(Path(_DIR_XSD, "procEventoNFe_v1.00.xsd")),
                str(arquivo),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert resultado.returncode == 0, resultado.stderr
