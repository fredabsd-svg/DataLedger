"""Suporte dos testes da DL-076: cenário de Palmas com notas SINTÉTICAS.

As notas passam pelo pipeline real (`services.receber_envio`) e são efetivadas pelo serviço
real (`escrituracao.efetivar_escrituracao`), para que a apuração seja testada sobre os
mesmos dados que o produto grava. Nada aqui é dado de cliente.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from apps.fiscal import escrituracao as servico_escrituracao
from apps.fiscal import services
from apps.fiscal.models import (
    AliquotaIssMunicipal,
    DocumentoFiscal,
    NaturezaOperacao,
    PapelDocumento,
    RegimeIss,
    RegimeIssEmpresa,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_iss_dl076 import xml_nfse_iss
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO, identificador_nfse

PALMAS = "1721000"
OUTRO_MUNICIPIO = "1100205"

DEVIDO = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
RETIDO = NaturezaOperacao.PRESTADO_ISS_RETIDO
OUTRO = NaturezaOperacao.PRESTADO_ISS_OUTRO_MUNICIPIO
EXPORTACAO = NaturezaOperacao.PRESTADO_EXPORTACAO_SERVICO
IMUNE = NaturezaOperacao.PRESTADO_ISS_IMUNE_ISENTO_REDUZIDO


def receber(escritorio, usuario, sufixo, natureza=None, *, prestador=CNPJ_PRESTADOR_PADRAO, **xml):
    """Recebe a NFS-e sintética pelo pipeline real e, se `natureza`, efetiva a escrituração."""
    identificador = identificador_nfse(sufixo)
    # Sem desconto nem dedução, o serviço é a própria base: vServ acompanha vBC. Assim o
    # aviso de base só sai quando o teste o quer.
    xml.setdefault("v_serv", xml.get("v_bc") or "1000.00")
    conteudo = xml_nfse_iss(
        sufixo=sufixo, identificador=identificador, prestador_documento=prestador, **xml
    )
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=conteudo,
        nome_arquivo=f"nota-{sufixo}.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)
    if natureza is not None:
        vinculo = VinculoDocumentoEmpresa.objects.get(
            documento=documento, papel=PapelDocumento.PRESTADOR, empresa__cnpj=prestador
        )
        servico_escrituracao.efetivar_escrituracao(vinculo, natureza, usuario)
    return documento


def aliquota(
    escritorio, usuario, subitem, percentual, *, inicio=date(2026, 1, 1), fim=None, municipio=PALMAS
):
    return AliquotaIssMunicipal.objects.create(
        escritorio=escritorio,
        municipio_ibge=municipio,
        subitem=subitem,
        percentual=Decimal(percentual),
        fonte="Alíquota sintética de teste (DL-076)",
        inicio_vigencia=inicio,
        fim_vigencia=fim,
        criada_por=usuario,
    )


def regime_aliquota(empresa, usuario, *, exercicio=2026, municipio=PALMAS):
    return RegimeIssEmpresa.objects.create(
        empresa=empresa,
        exercicio=exercicio,
        regime=RegimeIss.ALIQUOTA,
        municipio_ibge=municipio,
        criado_por=usuario,
    )


def cenario_outubro(escritorio, usuario, empresa):
    """Empresa de Palmas com regime por alíquota, alíquotas 17.01 (5%) e 07.02 (3%), e as
    notas de 10/2026 descritas em `test_dl076_apuracao.py`. Devolve os documentos por nome."""
    aliquota(escritorio, usuario, "17.01", "5.0000")
    aliquota(escritorio, usuario, "07.02", "3.0000")
    regime_aliquota(empresa, usuario)
    return {
        "n1": receber(
            escritorio, usuario, 1001, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.00"
        ),
        "n2": receber(
            escritorio,
            usuario,
            1002,
            DEVIDO,
            c_trib_nac="070201",
            v_bc="200.00",
            p_aliq_aplic="3.00",
            v_iss_qn="6.00",
        ),
        "n3": receber(
            escritorio, usuario, 1003, DEVIDO, c_trib_nac="170101", v_bc="333.33", v_iss_qn="16.67"
        ),
        "n4": receber(
            escritorio, usuario, 1004, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="40.00"
        ),
        "n5": receber(
            escritorio, usuario, 1005, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.01"
        ),
        "n6": receber(
            escritorio, usuario, 1006, DEVIDO, c_trib_nac="170101", v_bc="1000.00", v_iss_qn="50.02"
        ),
        "x1": receber(
            escritorio,
            usuario,
            1007,
            DEVIDO,
            c_trib_nac="170101",
            v_bc="500.00",
            v_iss_qn="25.00",
            dh_emi="2026-11-02T10:00:00-03:00",
            d_compet="2026-10-31",
        ),
        "r1": receber(escritorio, usuario, 2001, RETIDO, tp_ret_issqn="2", v_iss_qn="30.00"),
        "o1": receber(
            escritorio, usuario, 3001, OUTRO, c_loc_incid=OUTRO_MUNICIPIO, v_iss_qn="99.00"
        ),
        "e1": receber(escritorio, usuario, 4001, EXPORTACAO, trib_issqn="3", v_iss_qn="0.00"),
        "i1": receber(escritorio, usuario, 5001, IMUNE, trib_issqn="2", v_iss_qn="0.00"),
        "d1": receber(
            escritorio,
            usuario,
            7001,
            DEVIDO,
            c_loc_incid=OUTRO_MUNICIPIO,
            v_iss_qn="11.00",
        ),
    }
