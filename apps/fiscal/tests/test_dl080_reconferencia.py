"""DL-080 — ajustes da reconferência (R1, R2, R3), integrados pelo arquiteto.

Pela regra de parada do §3.1 não há nova rodada de correção. Os resíduos da reconferência
(docs/auditorias/2026-10-09-dl-080-reconferencia.md) fecham assim:

- R1: o invariante "a chave não liga empresa" volta a ser exercido pelo serviço na faixa em que
  a conferência chave × emitente não age (NFA-e, séries 890 a 899). Derruba o mutante que
  liga a empresa pelo CNPJ da chave.
- R2: a exceção da conferência é só 890 a 899 (MOC 7.0, Tabela 2-4): em 900 a 919 a chave leva
  o documento do próprio emitente.
- R3: `nfeProc` com mais de um `protNFe` e protocolo de homologação são recusados.

Dados sintéticos.
"""

import hashlib

import pytest

from apps.empresas.models import Empresa
from apps.fiscal import leitor, services
from apps.fiscal.models import DocumentoNFe, TipoResultadoArquivo, VinculoNFeEmpresa
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_EMITENTE_A,
    CNPJ_SEM_CADASTRO,
    chave_nfe,
    xml_nfe,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def emitente(escritorio_a):
    """Cliente do escritório cujo CNPJ aparece na chave da NFA-e."""
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )


def _ler(conteudo: bytes):
    return leitor.ler_arquivo(conteudo, hashlib.sha256(conteudo).hexdigest())


def _recusa(conteudo: bytes) -> str:
    with pytest.raises(leitor.ArquivoRecusado) as exc:
        _ler(conteudo)
    return str(exc.value)


# ---------- R1: na faixa da NFA-e, a chave com o CNPJ do cliente não liga a empresa ----------


@pytest.mark.parametrize("serie", ["890", "899"])
def test_nfa_e_com_chave_de_cliente_e_participantes_estranhos_nao_liga_a_empresa(
    escritorio_a, usuario_gestor_a, emitente, serie
):
    chave_com_cnpj_do_cliente = chave_nfe(emitente=CNPJ_EMITENTE_A, serie=serie)
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfe(
            serie=serie,
            chave=chave_com_cnpj_do_cliente,
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", CNPJ_SEM_CADASTRO),
        ),
        nome_arquivo="nota.xml",
    )
    resultado = lote.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO
    assert not VinculoNFeEmpresa.objects.exists()
    assert not DocumentoNFe.objects.exists()


# ---------- R2: em 900 a 919 a chave leva o documento do próprio emitente ----------


@pytest.mark.parametrize("serie", ["900", "909", "910", "919"])
def test_series_900_a_919_com_a_chave_do_proprio_emitente_sao_aceitas(serie):
    lido = _ler(xml_nfe(serie=serie))
    assert lido.chave[6:20] == CNPJ_EMITENTE_A


# ---------- R3: um protocolo só, e de produção ----------


def test_nfe_proc_com_dois_protocolos_e_recusado():
    original = xml_nfe().decode()
    inicio = original.index("<protNFe")
    fim = original.index("</protNFe>") + len("</protNFe>")
    protocolo = original[inicio:fim]
    duplicado = original[:fim] + protocolo.replace("<cStat>100</cStat>", "<cStat>110</cStat>")
    duplicado += original[fim:]
    assert duplicado.count("<protNFe") == 2
    assert "mais de um protNFe" in _recusa(duplicado.encode())


def test_protocolo_de_homologacao_e_recusado_mesmo_com_nota_de_producao():
    original = xml_nfe().decode()
    assert "<infProt><tpAmb>1</tpAmb>" in original
    adulterado = original.replace("<infProt><tpAmb>1</tpAmb>", "<infProt><tpAmb>2</tpAmb>")
    assert "homologação" in _recusa(adulterado.encode())
