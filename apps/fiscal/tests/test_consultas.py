"""Testes de `apps.fiscal.services.documentos_do_escritorio` e
`situacao_do_documento` — isolamento (critério 27, RC-18) e conferência
(critério 29, preservação do XML original).
"""

from __future__ import annotations

import hashlib

import pytest

from apps.fiscal import services
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, LoteDeRecepcao
from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, identificador_nfse, xml_evento, xml_nfse

pytestmark = pytest.mark.django_db


def _receber(escritorio, usuario, conteudo, nome="arquivo.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    )


# --- Isolamento (RC-18/critério 27) --------------------------------------


def test_documentos_do_escritorio_isola_por_escritorio(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(1), incluir_tomador=False),
    )

    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

    usuario_b = get_user_model().objects.create_user(
        username="gestor-b-consulta", email="gestor-b-consulta@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    _receber(
        escritorio_b,
        usuario_b,
        xml_nfse(
            identificador=identificador_nfse(2),
            prestador_documento=empresa_b.cnpj,
            incluir_tomador=False,
        ),
    )

    documentos_a = list(services.documentos_do_escritorio(escritorio_a))
    documentos_b = list(services.documentos_do_escritorio(escritorio_b))

    assert len(documentos_a) == 1
    assert len(documentos_b) == 1
    assert documentos_a[0].escritorio_id == escritorio_a.id
    assert documentos_b[0].escritorio_id == escritorio_b.id
    assert documentos_a[0].id != documentos_b[0].id


def test_documentos_do_escritorio_com_empresa_de_outro_escritorio_nao_vaza(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(3), incluir_tomador=False),
    )
    # Passar uma empresa de OUTRO escritório não deve, por acidente,
    # devolver os documentos de `escritorio_a` inteiro — a interseção fica
    # vazia porque nenhum vínculo aponta para `empresa_b`.
    resultado = list(services.documentos_do_escritorio(escritorio_a, empresa=empresa_b))
    assert resultado == []


def test_lote_e_evento_tambem_ficam_isolados_por_escritorio(
    escritorio_a, escritorio_b, empresa_a, usuario_gestor_a
):
    _receber(escritorio_a, usuario_gestor_a, xml_evento(), nome="evento.xml")
    assert EventoFiscal.objects.filter(escritorio=escritorio_b).count() == 0
    assert LoteDeRecepcao.objects.filter(escritorio=escritorio_b).count() == 0
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


# --- Filtros --------------------------------------------------------------


def test_filtra_por_empresa(escritorio_a, empresa_a, empresa_a2, usuario_gestor_a):
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(4), incluir_tomador=False),
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(
            identificador=identificador_nfse(5),
            prestador_documento=empresa_a2.cnpj,
            incluir_tomador=False,
        ),
    )

    documentos_de_a = list(services.documentos_do_escritorio(escritorio_a, empresa=empresa_a))
    assert len(documentos_de_a) == 1
    assert documentos_de_a[0].vinculos.filter(empresa=empresa_a).exists()


def test_filtra_por_competencia(escritorio_a, empresa_a, usuario_gestor_a):
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(6), d_compet="2024-01-10", incluir_tomador=False),
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(7), d_compet="2024-02-10", incluir_tomador=False),
    )

    documentos_de_janeiro = list(
        services.documentos_do_escritorio(escritorio_a, competencia=(2024, 1))
    )
    assert len(documentos_de_janeiro) == 1
    assert documentos_de_janeiro[0].d_competencia.month == 1


def test_filtra_por_situacao_valida_e_cancelada(escritorio_a, empresa_a, usuario_gestor_a):
    identificador_cancelada = identificador_nfse(8)
    identificador_valida = identificador_nfse(9)
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_cancelada, incluir_tomador=False),
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_valida, incluir_tomador=False),
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_evento(chave_nfse=chave_nfse_de(identificador_cancelada), codigo="e101101"),
        nome="evento.xml",
    )

    canceladas = services.documentos_do_escritorio(escritorio_a, situacao="cancelada")
    validas = services.documentos_do_escritorio(escritorio_a, situacao="valida")

    assert [d.identificador for d in canceladas] == [identificador_cancelada]
    assert [d.identificador for d in validas] == [identificador_valida]


# --- situacao_do_documento (HI-20) -----------------------------------------


@pytest.mark.parametrize("codigo_que_cancela", ["e101101", "e105102", "e105104", "e305101"])
def test_codigos_que_cancelam(escritorio_a, empresa_a, usuario_gestor_a, codigo_que_cancela):
    identificador = identificador_nfse(10 + hash(codigo_que_cancela) % 1000)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_evento(chave_nfse=chave_nfse_de(identificador), codigo=codigo_que_cancela),
        nome="evento.xml",
    )
    documento = DocumentoFiscal.objects.get(identificador=identificador)
    assert services.situacao_do_documento(documento) == "cancelada"


@pytest.mark.parametrize(
    "codigo_que_nao_cancela", ["e101103", "e105105", "e202201", "e203202", "e305102"]
)
def test_codigos_que_nao_cancelam(
    escritorio_a, empresa_a, usuario_gestor_a, codigo_que_nao_cancela
):
    identificador = identificador_nfse(200 + hash(codigo_que_nao_cancela) % 1000)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_evento(chave_nfse=chave_nfse_de(identificador), codigo=codigo_que_nao_cancela),
        nome="evento.xml",
    )
    documento = DocumentoFiscal.objects.get(identificador=identificador)
    assert services.situacao_do_documento(documento) == "valida"


def test_evento_de_outro_escritorio_nao_cancela_documento_deste(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

    identificador = identificador_nfse(300)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )

    usuario_b = get_user_model().objects.create_user(
        username="gestor-b-cancela", email="gestor-b-cancela@x.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    # Mesmo evento de cancelamento, mas enviado por OUTRO escritório — não
    # pode cancelar o documento do escritório A (isolamento).
    _receber(
        escritorio_b,
        usuario_b,
        xml_evento(chave_nfse=chave_nfse_de(identificador), codigo="e101101"),
        nome="evento.xml",
    )

    documento = DocumentoFiscal.objects.get(identificador=identificador, escritorio=escritorio_a)
    assert services.situacao_do_documento(documento) == "valida"


def test_evento_de_outro_escritorio_nao_cancela_documento_deste_via_lista_anotada(
    escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    # Achado A6/F04 (auditoria rodada 1): o teste acima
    # (`test_evento_de_outro_escritorio_nao_cancela_documento_deste`) busca
    # o documento por `DocumentoFiscal.objects.get(...)`, SEM a anotação
    # `.cancelada` — então `situacao_do_documento` cai no FALLBACK manual
    # (que já filtra por `escritorio_id` corretamente), nunca exercitando
    # o `OuterRef("escritorio_id")` de dentro de `documentos_do_escritorio`
    # (a subconsulta correlacionada que a tela de fato usa para listar).
    # Uma mutação que removesse esse filtro sobrevivia à suíte inteira.
    # Este teste passa pela LISTA anotada — o caminho real da tela.
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

    identificador = identificador_nfse(301)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )

    usuario_b = get_user_model().objects.create_user(
        username="gestor-b-cancela-lista",
        email="gestor-b-cancela-lista@x.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario_b, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    _receber(
        escritorio_b,
        usuario_b,
        xml_evento(chave_nfse=chave_nfse_de(identificador), codigo="e101101"),
        nome="evento.xml",
    )

    documento = services.documentos_do_escritorio(escritorio_a).get(identificador=identificador)
    assert documento.cancelada is False
    assert services.situacao_do_documento(documento) == "valida"


# --- Preservação do XML original (critério 29) -----------------------------


def test_xml_original_do_documento_preserva_bytes_exatos(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo = xml_nfse(incluir_tomador=False)
    _receber(escritorio_a, usuario_gestor_a, conteudo)
    documento = DocumentoFiscal.objects.get()
    assert bytes(documento.xml_original) == conteudo
    assert documento.sha256_arquivo == hashlib.sha256(conteudo).hexdigest()


def test_xml_original_do_evento_preserva_bytes_exatos(escritorio_a, usuario_gestor_a):
    conteudo = xml_evento()
    _receber(escritorio_a, usuario_gestor_a, conteudo, nome="evento.xml")
    evento = EventoFiscal.objects.get()
    assert bytes(evento.xml_original) == conteudo
    assert evento.sha256_arquivo == hashlib.sha256(conteudo).hexdigest()


# --- Correção do arquiteto: situação calculada no BANCO, não em Python -----
# (revisão da entrega original — 5.000 notas não podem virar 5.000 consultas)


def test_documentos_do_escritorio_sempre_devolve_queryset_anotada(
    escritorio_a, empresa_a, usuario_gestor_a
):
    from django.db.models import QuerySet

    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_nfse(identificador=identificador_nfse(400), incluir_tomador=False),
    )
    resultado = services.documentos_do_escritorio(escritorio_a)
    assert isinstance(resultado, QuerySet)
    documento = resultado.get()
    # A anotação `cancelada` é o contrato repassado à tela (etapa 2): cada
    # linha já vem com o booleano pronto, sem consulta adicional.
    assert documento.cancelada is False


def test_documentos_do_escritorio_anota_cancelada_corretamente(
    escritorio_a, empresa_a, usuario_gestor_a
):
    identificador = identificador_nfse(401)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )
    _receber(
        escritorio_a,
        usuario_gestor_a,
        xml_evento(chave_nfse=chave_nfse_de(identificador), codigo="e101101"),
        nome="evento.xml",
    )
    documento = services.documentos_do_escritorio(escritorio_a).get(identificador=identificador)
    assert documento.cancelada is True
    assert services.situacao_do_documento(documento) == "cancelada"


def test_situacao_invalida_levanta_valueerror(escritorio_a):
    with pytest.raises(ValueError, match="valida|cancelada"):
        services.documentos_do_escritorio(escritorio_a, situacao="feita-a-mao")


def test_listar_documentos_com_situacao_custa_uma_consulta_constante(
    django_assert_num_queries, escritorio_a, empresa_a, usuario_gestor_a
):
    # A versão anterior calculava a situação em PYTHON — uma consulta de
    # eventos POR DOCUMENTO (5.000 notas viravam 5.000 consultas). A
    # correção anota `cancelada` no próprio SELECT (Exists/OuterRef), então
    # listar N documentos com `situacao` continua custando UMA consulta,
    # não N — este teste prova isso por MEDIÇÃO, não por leitura do código.
    for i in range(5):
        _receber(
            escritorio_a,
            usuario_gestor_a,
            xml_nfse(identificador=identificador_nfse(410 + i), incluir_tomador=False),
        )

    with django_assert_num_queries(1):
        documentos = list(services.documentos_do_escritorio(escritorio_a, situacao="valida"))
        for documento in documentos:
            # situacao_do_documento usa a anotação já carregada — nenhuma
            # consulta extra por documento (o N+1 que este teste existe
            # para provar que NÃO acontece).
            assert services.situacao_do_documento(documento) == "valida"

    assert len(documentos) == 5


def test_situacao_do_documento_sem_anotacao_ainda_consulta(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Caminho de fallback: documento obtido por FORA de
    # `documentos_do_escritorio` (sem a anotação `cancelada`) — continua
    # funcionando, só que com uma consulta.
    identificador = identificador_nfse(420)
    _receber(
        escritorio_a, usuario_gestor_a, xml_nfse(identificador=identificador, incluir_tomador=False)
    )
    documento_sem_anotacao = DocumentoFiscal.objects.get(identificador=identificador)
    assert not hasattr(documento_sem_anotacao, "cancelada")
    assert services.situacao_do_documento(documento_sem_anotacao) == "valida"
