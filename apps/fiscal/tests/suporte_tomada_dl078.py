"""Suporte dos testes da DL-078: NFS-e TOMADAS sintéticas pelo pipeline real.

As notas passam por `services.receber_envio` (recepção real) e são escrituradas pelo serviço
real (`apps.fiscal.tomadas`). Nada aqui grava valor de cliente: os dados são sintéticos.
"""

from __future__ import annotations

from datetime import date

from apps.fiscal import services, tomadas
from apps.fiscal.models import (
    DocumentoFiscal,
    NaturezaTomada,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, identificador_nfse, xml_evento
from apps.fiscal.tests.xml_tomada_dl078 import xml_tomada

PALMAS = "1721000"
OUTRO_MUNICIPIO = "1100205"  # sem regra de ISS cadastrada: caso "não parametrizado"

# "Hoje" fixo dos testes (AGENTS.md §7). Os cenários pagam em outubro e novembro de 2026, e a janela
# da data de pagamento (HI-98) não aceita data futura. O relógio do teste fica em 15/12/2026, depois
# de todos os pagamentos dos cenários, para que o resultado não dependa do dia em que o teste roda.
# O fixture que fixa o relógio mora em `apps/fiscal/tests/conftest.py` (`relogio_do_teste`).
DIA_DE_HOJE_NO_TESTE = date(2026, 12, 15)

T1 = NaturezaTomada.TOMADO_ISS_RETIDO_PELO_CLIENTE
T2 = NaturezaTomada.TOMADO_SEM_RETENCAO
T3 = NaturezaTomada.TOMADO_PRESTADOR_OUTRO_MUNICIPIO
T5 = NaturezaTomada.TOMADO_DE_MEI
T6 = NaturezaTomada.TOMADO_DE_SIMPLES
T7 = NaturezaTomada.TOMADO_DE_PESSOA_FISICA


def receber_tomada(escritorio, usuario, sufixo: int, **xml) -> DocumentoFiscal:
    """Recebe NFS-e tomada sintética. Por padrão a tomadora é a empresa de CNPJ padrão."""
    identificador = identificador_nfse(sufixo)
    conteudo = xml_tomada(sufixo=sufixo, identificador=identificador, **xml)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=conteudo,
        nome_arquivo=f"tomada-{sufixo}.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def vinculo_tomador(documento: DocumentoFiscal, empresa) -> VinculoDocumentoEmpresa:
    return VinculoDocumentoEmpresa.objects.get(
        documento=documento, empresa=empresa, papel=PapelDocumento.TOMADOR
    )


def cancelar(escritorio, usuario, documento: DocumentoFiscal, sufixo_evento: int = 1) -> None:
    """Recebe o evento de cancelamento da nota (e101101), pelo pipeline real."""
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo=f"evento-{sufixo_evento}.xml",
    )


def efetivar(documento: DocumentoFiscal, empresa, natureza: str, usuario):
    return tomadas.efetivar_escrituracao_tomada(
        vinculo_tomador(documento, empresa), natureza, usuario
    )


def tomada_efetivada(escritorio, empresa, usuario, sufixo: int, natureza: str = T1, **xml):
    """Nota tomada recebida e efetivada pelo serviço. Devolve a escrituração.

    A tomadora é `empresa`, salvo se `xml` informar `tomador_documento` (o chamador decide).
    """
    xml.setdefault("tomador_documento", empresa.cnpj)
    documento = receber_tomada(escritorio, usuario, sufixo, **xml)
    return efetivar(documento, empresa, natureza, usuario)
