"""DL-041 (RC-115/DE-077, critério 6 do plano): a recepção fiscal continua
vinculando a nota só à empresa do escritório que ENVIA, mesmo quando o
MESMO CNPJ existe em dois escritórios diferentes — cenário que só passou a
ser POSSÍVEL de construir depois desta etapa (antes, a unicidade GLOBAL de
CNPJ impedia duas empresas com o mesmo CNPJ em escritórios diferentes;
`_mapa_de_inscricoes_do_escritorio`/`_localizar_empresa_por_cnpj`
(apps/fiscal/services.py) já filtravam por escritório desde a DE-074 —
este teste prova que esse isolamento continua correto agora que o cenário
é alcançável de verdade, não só teórico).
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import PapelDocumento
from apps.fiscal.tests.xml_sinteticos import CNPJ_PRESTADOR_PADRAO, xml_nfse
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


@pytest.fixture
def empresa_b_mesmo_cnpj_de_a(escritorio_b):
    # MESMO CNPJ de `empresa_a` (CNPJ_PRESTADOR_PADRAO), mas no escritório
    # B — só possível desde a DL-041 (RC-115): a unicidade de CNPJ deixou
    # de ser global.
    return Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Prestadora B (mesmo CNPJ de A) Ltda",
        cnpj=CNPJ_PRESTADOR_PADRAO,
    )


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    usuario = get_user_model().objects.create_user(
        username="gestor-fiscal-b-dl041",
        email="gestor-fiscal-b-dl041@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    return usuario


def test_envio_no_escritorio_a_vincula_so_a_empresa_de_a(
    escritorio_a, empresa_a, usuario_gestor_a, empresa_b_mesmo_cnpj_de_a
):
    conteudo = xml_nfse(prestador_documento=CNPJ_PRESTADOR_PADRAO, incluir_tomador=False)

    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    assert lote.total_recebidos == 1
    documento = lote.resultados.get().documento
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa_id == empresa_a.pk
    assert vinculos[0].papel == PapelDocumento.PRESTADOR
    # NUNCA vincula à empresa do OUTRO escritório, mesmo com o CNPJ igual.
    assert vinculos[0].empresa_id != empresa_b_mesmo_cnpj_de_a.pk


def test_envio_no_escritorio_b_vincula_so_a_empresa_de_b(
    escritorio_b, empresa_b_mesmo_cnpj_de_a, usuario_gestor_b, empresa_a
):
    conteudo = xml_nfse(
        identificador=None,
        prestador_documento=CNPJ_PRESTADOR_PADRAO,
        incluir_tomador=False,
    )

    lote = services.receber_envio(
        escritorio=escritorio_b, usuario=usuario_gestor_b, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    assert lote.total_recebidos == 1
    documento = lote.resultados.get().documento
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa_id == empresa_b_mesmo_cnpj_de_a.pk
    assert vinculos[0].empresa_id != empresa_a.pk


def test_documentos_do_escritorio_a_nao_mostra_documento_do_escritorio_b_mesmo_cnpj(
    escritorio_a, empresa_a, usuario_gestor_a, escritorio_b, empresa_b_mesmo_cnpj_de_a
):
    usuario_gestor_b = get_user_model().objects.create_user(
        username="gestor-fiscal-b-dl041-isolamento",
        email="gestor-fiscal-b-dl041-isolamento@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_gestor_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )

    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(prestador_documento=CNPJ_PRESTADOR_PADRAO, incluir_tomador=False),
        nome_arquivo="nota-a.xml",
    )
    services.receber_envio(
        escritorio=escritorio_b,
        usuario=usuario_gestor_b,
        arquivo=xml_nfse(
            identificador=None, prestador_documento=CNPJ_PRESTADOR_PADRAO, incluir_tomador=False
        ),
        nome_arquivo="nota-b.xml",
    )

    documentos_de_a = services.documentos_do_escritorio(escritorio_a, empresa=empresa_a)
    documentos_de_b = services.documentos_do_escritorio(
        escritorio_b, empresa=empresa_b_mesmo_cnpj_de_a
    )

    assert documentos_de_a.count() == 1
    assert documentos_de_b.count() == 1
    assert set(documentos_de_a.values_list("pk", flat=True)).isdisjoint(
        set(documentos_de_b.values_list("pk", flat=True))
    )
