"""Testes de `apps.fiscal.services.receber_envio` — o coração da fatia 1.

Cobre os cenários da seção "Cenários de teste obrigatórios" do plano
(docs/planos/DL-010-F1-recepcao-nfse.md) e os critérios numerados: 1-8,
10-12, 15-18, 24, 25, 27, 28 (concorrência real fica em
`test_concorrencia.py`), 29 (preservação do XML — parte em
`test_consultas.py`), 31, 32.
"""

from __future__ import annotations

import zipfile
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EventoFiscal,
    PapelDocumento,
    ResultadoDoArquivo,
    TipoResultadoArquivo,
)
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_PRESTADOR_PADRAO,
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfe_minimo,
    xml_nfse,
    zip_de,
)

pytestmark = pytest.mark.django_db


# --- Sucesso -----------------------------------------------------------


@pytest.mark.parametrize("versao", ["1.00", "1.01"])
def test_recebe_nfse_solta_com_sucesso(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a, versao
):
    conteudo = xml_nfse(versao=versao)
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    assert lote.total_arquivos == 1
    assert lote.total_recebidos == 1
    assert lote.total_duplicados == 0
    assert lote.total_recusados == 0

    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    assert documento.versao == versao
    assert documento.v_serv == Decimal("100.00")
    assert documento.v_liq == Decimal("95.00")


def test_recebe_nfse_a_partir_de_arquivo_de_upload_do_django(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # `receber_envio` aceita bytes OU um objeto de upload real do Django
    # (contrato do plano: "arquivo = bytes ou arquivo enviado do Django").
    upload = SimpleUploadedFile(
        "nota.xml", xml_nfse(incluir_tomador=False), content_type="text/xml"
    )
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=upload, nome_arquivo="nota.xml"
    )
    assert lote.total_recebidos == 1


def test_prestador_cliente_gera_vinculo_de_prestador(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo = xml_nfse(incluir_tomador=False)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    documento = DocumentoFiscal.objects.get()
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa == empresa_a
    assert vinculos[0].papel == PapelDocumento.PRESTADOR


def test_tomador_cliente_gera_vinculo_de_tomador(escritorio_a, empresa_a2, usuario_gestor_a):
    # Prestador é uma empresa QUALQUER fora do escritório; só o tomador é
    # cliente.
    conteudo = xml_nfse(prestador_documento="99988877000161")
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    documento = DocumentoFiscal.objects.get()
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa == empresa_a2
    assert vinculos[0].papel == PapelDocumento.TOMADOR


def test_os_dois_clientes_um_documento_dois_vinculos(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    conteudo = xml_nfse()  # prestador=empresa_a, tomador=empresa_a2 (fixture)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    documento = DocumentoFiscal.objects.get()
    papeis = {vinculo.empresa_id: vinculo.papel for vinculo in documento.vinculos.all()}
    assert papeis == {empresa_a.id: PapelDocumento.PRESTADOR, empresa_a2.id: PapelDocumento.TOMADOR}


def test_zip_com_varias_notas(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo_zip = zip_de(
        {
            "nota1.xml": xml_nfse(identificador=identificador_nfse(1), incluir_tomador=False),
            "nota2.xml": xml_nfse(identificador=identificador_nfse(2), incluir_tomador=False),
            "nota3.xml": xml_nfse(identificador=identificador_nfse(3), incluir_tomador=False),
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_arquivos == 3
    assert lote.total_recebidos == 3
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 3


# --- Duplicidade (critérios 3, 4, 15, 16, RC-69) -------------------------


def test_reenviar_mesmo_arquivo_nao_duplica(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo = xml_nfse(incluir_tomador=False)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote2.total_duplicados == 1
    assert lote2.total_recebidos == 0
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_mesmo_xml_em_outro_zip_nao_duplica(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo = xml_nfse(incluir_tomador=False)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    conteudo_zip = zip_de({"outra/pasta/mesma-nota.xml": conteudo})
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote2.total_duplicados == 1
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_mesma_nota_duas_pastas_do_mesmo_zip(escritorio_a, empresa_a, usuario_gestor_a):
    # RC-69: 105 casos medidos no acervo real — a mesma NFS-e catalogada
    # duas vezes na MESMA pasta/zip (ex.: "Entradas" e "Saídas" da
    # ferramenta de origem).
    conteudo = xml_nfse(incluir_tomador=False)
    conteudo_zip = zip_de({"Entradas/nota.xml": conteudo, "Saidas/nota.xml": conteudo})
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    assert lote.total_duplicados == 1
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_mesma_nota_nome_de_arquivo_diferente_ainda_duplica(
    escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo = xml_nfse(incluir_tomador=False)
    conteudo_zip = zip_de(
        {"nome-completamente-diferente.xml": conteudo, "outro-nome.xml": conteudo}
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    assert lote.total_duplicados == 1


def test_notas_de_emitentes_distintos_com_mesmo_numero_coexistem(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    # Critério 16 / RC-74: nNFSe NÃO é chave.
    conteudo_zip = zip_de(
        {
            "nota-emitente-1.xml": xml_nfse(
                identificador=identificador_nfse(1), numero="1", incluir_tomador=False
            ),
            "nota-emitente-2.xml": xml_nfse(
                identificador=identificador_nfse(2),
                numero="1",
                prestador_documento=empresa_a2.cnpj,
                incluir_tomador=False,
            ),
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 2
    numeros = list(
        DocumentoFiscal.objects.filter(escritorio=escritorio_a).values_list("numero", flat=True)
    )
    assert numeros == ["1", "1"]


# --- Eventos (critério 17, RC-70) ----------------------------------------


def test_evento_orfao_e_aceito_e_guardado(escritorio_a, usuario_gestor_a):
    conteudo_evento = xml_evento()
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_evento,
        nome_arquivo="evento.xml",
    )
    assert lote.total_recebidos == 1
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).exists()


def test_evento_antes_da_nota_depois_a_nota_chega_cancelada(
    escritorio_a, empresa_a, usuario_gestor_a
):
    identificador = identificador_nfse(10)
    chave = chave_nfse_de(identificador)

    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave, codigo="e101101"),
        nome_arquivo="evento.xml",
    )
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(identificador=identificador, incluir_tomador=False),
        nome_arquivo="nota.xml",
    )

    documento = DocumentoFiscal.objects.get(identificador=identificador)
    assert services.situacao_do_documento(documento) == "cancelada"


def test_nota_antes_do_evento_tambem_fica_cancelada(escritorio_a, empresa_a, usuario_gestor_a):
    identificador = identificador_nfse(11)
    chave = chave_nfse_de(identificador)

    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(identificador=identificador, incluir_tomador=False),
        nome_arquivo="nota.xml",
    )
    documento = DocumentoFiscal.objects.get(identificador=identificador)
    assert services.situacao_do_documento(documento) == "valida"

    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave, codigo="e101101"),
        nome_arquivo="evento.xml",
    )
    documento.refresh_from_db()
    assert services.situacao_do_documento(documento) == "cancelada"


def test_evento_duplicado_nao_duplica(escritorio_a, usuario_gestor_a):
    conteudo_evento = xml_evento()
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_evento,
        nome_arquivo="evento.xml",
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_evento,
        nome_arquivo="evento.xml",
    )
    assert lote2.total_duplicados == 1
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_evento_que_nao_cancela_nao_muda_situacao(escritorio_a, empresa_a, usuario_gestor_a):
    identificador = identificador_nfse(12)
    chave = chave_nfse_de(identificador)
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(identificador=identificador, incluir_tomador=False),
        nome_arquivo="nota.xml",
    )
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        # e202201 = confirmação do prestador — não cancela (HI-20).
        arquivo=xml_evento(chave_nfse=chave, codigo="e202201"),
        nome_arquivo="evento.xml",
    )
    documento = DocumentoFiscal.objects.get(identificador=identificador)
    assert services.situacao_do_documento(documento) == "valida"


# --- Recusas: isolamento (critérios 5, 6, 27, RC-112) ---------------------


def test_prestador_e_tomador_fora_do_escritorio_e_recusado(escritorio_a, usuario_gestor_a):
    conteudo = xml_nfse(
        prestador_documento="99988877000161",
        tomador_documento="88877766000155",
    )
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recusados == 1
    resultado = lote.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


def test_tomador_ausente_e_prestador_fora_e_recusado(escritorio_a, usuario_gestor_a):
    conteudo = xml_nfse(prestador_documento="99988877000161", incluir_tomador=False)
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recusados == 1
    assert lote.resultados.get().motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO


def test_prestador_pessoa_fisica_sem_cadastro_e_recusado_com_motivo_especifico(
    escritorio_a, usuario_gestor_a
):
    # RC-112: o Fred confirmou que o escritório atende cliente pessoa
    # física, mas o cadastro ainda não existe — a mensagem tem que dizer
    # ISSO, não o genérico "nenhum participante".
    conteudo = xml_nfse(
        prestador_tipo="CPF", prestador_documento="12345678909", incluir_tomador=False
    )
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recusados == 1
    resultado = lote.resultados.get()
    assert resultado.motivo == services.MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO
    assert "pessoa física" in resultado.motivo


def test_mensagem_de_recusa_e_identica_exista_ou_nao_empresa_em_outro_escritorio(
    escritorio_a, escritorio_b, empresa_b, usuario_gestor_a
):
    # Critério 27: a recusa não pode DAR PISTA de que o CNPJ pertence a
    # alguém em outro escritório.
    conteudo_cnpj_de_outro_escritorio = xml_nfse(
        prestador_documento=empresa_b.cnpj, incluir_tomador=False
    )
    conteudo_cnpj_inexistente = xml_nfse(
        identificador=identificador_nfse(20),
        prestador_documento="90888777000110",
        incluir_tomador=False,
    )

    lote_1 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_cnpj_de_outro_escritorio,
        nome_arquivo="nota1.xml",
    )
    lote_2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_cnpj_inexistente,
        nome_arquivo="nota2.xml",
    )

    assert lote_1.resultados.get().motivo == lote_2.resultados.get().motivo


# --- Recusas: formato (critérios 7, 8, 18, 24) -----------------------------


def test_versao_nao_suportada_e_recusada_sem_derrubar_o_lote(
    escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo_zip = zip_de(
        {
            "boa.xml": xml_nfse(identificador=identificador_nfse(30), incluir_tomador=False),
            "versao-ruim.xml": xml_nfse(
                identificador=identificador_nfse(31), versao="9.99", incluir_tomador=False
            ),
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 1
    recusado = lote.resultados.get(resultado=TipoResultadoArquivo.RECUSADO)
    assert "versão não suportada" in recusado.motivo


def test_id_fora_do_formato_e_recusado(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo = xml_nfse(identificador="NFS123")
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recusados == 1
    assert "Id fora do formato" in lote.resultados.get().motivo


def test_xml_malformado_truncado_e_vazio_nao_derrubam_o_lote(
    escritorio_a, empresa_a, usuario_gestor_a
):
    boa = xml_nfse(identificador=identificador_nfse(40), incluir_tomador=False)
    conteudo_zip = zip_de(
        {
            "boa.xml": boa,
            "malformado.xml": b"<NFSe><infNFSe>",
            "truncado.xml": boa[: len(boa) // 2],
            "vazio.xml": b"",
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_arquivos == 4
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 3


def test_nfe_e_recusada_sem_derrubar_o_lote(escritorio_a, empresa_a, usuario_gestor_a):
    conteudo_zip = zip_de(
        {
            "boa.xml": xml_nfse(identificador=identificador_nfse(50), incluir_tomador=False),
            "nfe.xml": xml_nfe_minimo(),
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    recusado = lote.resultados.get(resultado=TipoResultadoArquivo.RECUSADO)
    assert "NF-e" in recusado.motivo


def test_nome_de_arquivo_enganoso_e_classificado_pelo_conteudo(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # RC-71: um arquivo cujo NOME diz "evento" mas o CONTEÚDO é uma NFS-e
    # (e vice-versa) tem que ser classificado pelo conteúdo.
    conteudo_zip = zip_de(
        {
            "definitivamente_um_evento.xml": xml_nfse(incluir_tomador=False),
            "definitivamente_uma_nota.xml": xml_evento(),
        }
    )
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_xml_com_dtd_e_recusado_sem_derrubar_o_lote(escritorio_a, empresa_a, usuario_gestor_a):
    hostil = (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<!DOCTYPE NFSe [<!ENTITY x "1">]>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b'<infNFSe Id="' + ("NFS" + "0" * 50).encode() + b'"/></NFSe>'
    )
    conteudo_zip = zip_de(
        {
            "boa.xml": xml_nfse(identificador=identificador_nfse(60), incluir_tomador=False),
            "hostil.xml": hostil,
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 1


# --- Limites (HI-22) -------------------------------------------------------


def test_envio_vazio_levanta_envio_invalido(escritorio_a, usuario_gestor_a):
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=b"", nome_arquivo="vazio.xml"
        )
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


def test_envio_acima_do_tamanho_maximo_levanta_envio_invalido(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_TAMANHO_ENVIO_BYTES", 100)
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=b"x" * 101,
            nome_arquivo="grande.xml",
        )


def test_envio_no_limite_de_tamanho_e_aceito(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    conteudo = xml_nfse(incluir_tomador=False)
    monkeypatch.setattr(services, "LIMITE_TAMANHO_ENVIO_BYTES", len(conteudo))
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recebidos == 1


def test_arquivo_acima_do_limite_individual_e_recusado(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    conteudo = xml_nfse(incluir_tomador=False)
    monkeypatch.setattr(services, "LIMITE_TAMANHO_XML_BYTES", len(conteudo) - 1)
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recusados == 1
    assert "1 MB" in lote.resultados.get().motivo or "bytes" in lote.resultados.get().motivo


def test_quantidade_de_arquivos_no_limite_e_aceita(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_ARQUIVOS_NO_ENVIO", 2)
    conteudo_zip = zip_de(
        {
            "a.xml": xml_nfse(identificador=identificador_nfse(70), incluir_tomador=False),
            "b.xml": xml_nfse(identificador=identificador_nfse(71), incluir_tomador=False),
        }
    )
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_arquivos == 2


def test_quantidade_de_arquivos_acima_do_limite_levanta_envio_invalido(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_ARQUIVOS_NO_ENVIO", 2)
    conteudo_zip = zip_de(
        {
            "a.xml": xml_nfse(identificador=identificador_nfse(80), incluir_tomador=False),
            "b.xml": xml_nfse(identificador=identificador_nfse(81), incluir_tomador=False),
            "c.xml": xml_nfse(identificador=identificador_nfse(82), incluir_tomador=False),
        }
    )
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=conteudo_zip,
            nome_arquivo="lote.zip",
        )
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


def test_descompactado_acima_do_limite_declarado_levanta_envio_invalido(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_DESCOMPACTADO_BYTES", 50)
    conteudo_zip = zip_de({"grande.xml": b"x" * 100})
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=conteudo_zip,
            nome_arquivo="lote.zip",
        )


# --- ZIP hostil (critério 25) -----------------------------------------------


def test_zip_corrompido_levanta_envio_invalido(escritorio_a, usuario_gestor_a):
    with pytest.raises(services.EnvioInvalido, match="corrompido"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=b"PK\x03\x04" + b"nao e um zip de verdade",
            nome_arquivo="lote.zip",
        )


def test_zip_aninhado_levanta_envio_invalido(escritorio_a, usuario_gestor_a):
    zip_interno = zip_de({"nota.xml": xml_nfse()})
    zip_externo = zip_de({"interno.zip": zip_interno})
    with pytest.raises(services.EnvioInvalido, match="ZIP dentro de ZIP"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=zip_externo,
            nome_arquivo="lote.zip",
        )


def _com_bit_de_criptografia_marcado(conteudo_zip: bytes) -> bytes:
    """`zipfile.ZipFile._open_to_write` ZERA `flag_bits` antes de escrever
    (linha `zinfo.flag_bits = 0x00`), então não dá para produzir uma
    entrada com o bit de senha marcado só setando `ZipInfo.flag_bits` antes
    de `writestr` — a própria biblioteca padrão apaga. Marcamos o bit
    diretamente nos BYTES já escritos: offset 6-7 do cabeçalho local
    (assinatura `PK\\x03\\x04`) e offset 8-9 do cabeçalho do diretório
    central (assinatura `PK\\x01\\x02`) são o campo "general purpose bit
    flag"; o bit 0 (byte baixo, little-endian) é o de criptografia clássica
    do formato ZIP.
    """
    dados = bytearray(conteudo_zip)
    pos_local = dados.find(b"PK\x03\x04")
    assert pos_local != -1
    dados[pos_local + 6] |= 0x01
    pos_central = dados.find(b"PK\x01\x02")
    assert pos_central != -1
    dados[pos_central + 8] |= 0x01
    return bytes(dados)


def test_zip_com_entrada_cifrada_levanta_envio_invalido(escritorio_a, usuario_gestor_a):
    conteudo_zip = _com_bit_de_criptografia_marcado(zip_de({"nota.xml": xml_nfse()}))
    with pytest.raises(services.EnvioInvalido, match="cifrada"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=conteudo_zip,
            nome_arquivo="lote.zip",
        )


def test_zip_com_diretorio_e_ignorado(escritorio_a, empresa_a, usuario_gestor_a):
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        arquivo_zip.writestr("pasta/", b"")
        arquivo_zip.writestr("pasta/nota.xml", xml_nfse(incluir_tomador=False))
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=buffer.getvalue(),
        nome_arquivo="lote.zip",
    )
    assert lote.total_arquivos == 1
    assert lote.total_recebidos == 1


# --- Trilha de auditoria (critério 31) --------------------------------------


def test_trilha_grava_contagens_e_sha256_sem_conteudo_sensivel(
    escritorio_a, empresa_a, usuario_gestor_a
):
    nome_prestador_sensivel = "Razão Social Confidencial Ltda"
    conteudo = xml_nfse(prestador_nome=nome_prestador_sensivel, incluir_tomador=False)

    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    registro = RegistroAuditoria.objects.get(acao="fiscal.envio_recebido")
    assert registro.usuario_id == usuario_gestor_a.id
    assert registro.escritorio_id == escritorio_a.id
    assert registro.detalhes["sha256_arquivo"] == lote.sha256_arquivo
    assert registro.detalhes["total_recebidos"] == 1

    detalhes_como_texto = str(registro.detalhes)
    assert nome_prestador_sensivel not in detalhes_como_texto
    assert CNPJ_PRESTADOR_PADRAO not in detalhes_como_texto
    assert "<NFSe" not in detalhes_como_texto


def test_envio_invalido_nao_grava_lote_nem_trilha(escritorio_a, usuario_gestor_a):
    contagem_antes = RegistroAuditoria.objects.count()
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=b"", nome_arquivo="vazio.xml"
        )
    assert RegistroAuditoria.objects.count() == contagem_antes
    from apps.fiscal.models import LoteDeRecepcao

    assert not LoteDeRecepcao.objects.filter(escritorio=escritorio_a).exists()


# --- Nunca levanta exceção por arquivo ruim (contrato do plano) ------------


def test_receber_envio_nunca_levanta_por_arquivo_individual_ruim(
    escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo_zip = zip_de(
        {
            "boa.xml": xml_nfse(identificador=identificador_nfse(90), incluir_tomador=False),
            "recusa-isolamento.xml": xml_nfse(
                identificador=identificador_nfse(91),
                prestador_documento="90888777000110",
                incluir_tomador=False,
            ),
            "recusa-formato.xml": b"nao e xml nenhum",
            "recusa-versao.xml": xml_nfse(
                identificador=identificador_nfse(92), versao="0.01", incluir_tomador=False
            ),
        }
    )
    # Não deve levantar NENHUMA exceção.
    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_arquivos == 4
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 3
    assert ResultadoDoArquivo.objects.filter(lote=lote).count() == 4
