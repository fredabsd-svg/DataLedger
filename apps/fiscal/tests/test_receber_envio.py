"""Testes de `apps.fiscal.services.receber_envio` — o coração da fatia 1.

Cobre os cenários da seção "Cenários de teste obrigatórios" do plano
(docs/planos/DL-010-F1-recepcao-nfse.md) e os critérios numerados: 1-8,
10-12, 15-18, 24, 25, 27, 28 (concorrência real fica em
`test_concorrencia.py`), 29 (preservação do XML — parte em
`test_consultas.py`), 31, 32.
"""

from __future__ import annotations

import zipfile
import zlib
from decimal import Decimal
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa, TipoInscricao
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


# --- Achado A5 (auditoria rodada 1): reenvio acrescenta vínculo que faltava


def test_reenvio_apos_cadastro_do_segundo_participante_acrescenta_vinculo(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Cenário exato do achado A5: nota com prestador cliente (empresa_a) e
    # tomador AINDA NÃO cadastrado — recebida com 1 vínculo. A tomadora é
    # cadastrada DEPOIS. O reenviar da MESMA nota tem que acrescentar o
    # vínculo que faltava, sem duplicar o documento nem o vínculo já
    # existente.
    conteudo = xml_nfse()  # prestador=empresa_a, tomador=CNPJ_TOMADOR_PADRAO (ainda não cliente)
    lote1 = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote1.total_recebidos == 1
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    assert documento.vinculos.count() == 1

    from apps.fiscal.tests.xml_sinteticos import CNPJ_TOMADOR_PADRAO

    tomadora = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Tomadora Cadastrada Depois Ltda",
        cnpj=CNPJ_TOMADOR_PADRAO,
    )

    lote2 = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote2.total_duplicados == 1
    assert lote2.total_recebidos == 0
    documento.refresh_from_db()
    assert documento.vinculos.count() == 2
    assert set(documento.vinculos.values_list("empresa_id", "papel")) == {
        (empresa_a.pk, PapelDocumento.PRESTADOR),
        (tomadora.pk, PapelDocumento.TOMADOR),
    }
    # A mensagem registra QUE algo mudou — não é o mesmo "já recebido"
    # genérico do reenvio comum.
    assert "Vínculo novo" in lote2.resultados.get().motivo
    assert tomadora.razao_social in lote2.resultados.get().motivo


def test_reenvio_sem_novo_cadastro_nao_cria_vinculo_a_mais(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    # Reenvio comum (os dois participantes já eram clientes desde o
    # início) NÃO deve ganhar vínculo novo — idempotência: reenviar duas,
    # três vezes dá sempre o mesmo resultado.
    conteudo = xml_nfse()  # prestador=empresa_a, tomador=empresa_a2 (fixture)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    assert documento.vinculos.count() == 2

    lote2 = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote2.total_duplicados == 1
    documento.refresh_from_db()
    assert documento.vinculos.count() == 2
    assert "Vínculo novo" not in lote2.resultados.get().motivo


# --- Achado A9/F30: nota de uma empresa para ela mesma ---------------------


def test_nota_com_prestador_igual_ao_tomador_gera_um_unico_vinculo(
    escritorio_a, empresa_a, usuario_gestor_a
):
    # Sem a guarda `empresa_tomador != empresa_prestador`, o segundo
    # vínculo (mesma empresa, papel diferente) violaria a unicidade
    # `(documento, empresa)` DENTRO do savepoint do arquivo — a nota
    # viraria "duplicado" sem nunca ter sido gravada de verdade.
    conteudo = xml_nfse(tomador_documento=empresa_a.cnpj)
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 0
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa == empresa_a
    assert vinculos[0].papel == PapelDocumento.PRESTADOR


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


def test_estabelecimento_de_outro_escritorio_nao_vincula_nota_deste(
    escritorio_a, escritorio_b, usuario_gestor_a
):
    # Achado A6/F02 (auditoria rodada 1): `_localizar_empresa_por_cnpj`
    # busca em `Empresa.cnpj` E em `Estabelecimento.cnpj` — o teste
    # `test_mensagem_de_recusa_e_identica_exista_ou_nao_empresa_em_outro_
    # escritorio` (abaixo) só exercita o lado `Empresa`. Este exercita o
    # lado `Estabelecimento`: uma FILIAL de outro escritório com o mesmo
    # CNPJ do prestador não pode vincular a nota — sem o filtro
    # `empresa__escritorio=escritorio`, ela vincularia por engano.
    from apps.empresas.models import Empresa, Estabelecimento, TipoEstabelecimento

    empresa_matriz_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Matriz Outro Escritório Ltda", cnpj="55566677000100"
    )
    cnpj_da_filial_b = "55566677000280"
    Estabelecimento.objects.create(
        empresa=empresa_matriz_b,
        tipo=TipoEstabelecimento.FILIAL,
        nome="Filial de B",
        cnpj=cnpj_da_filial_b,
    )

    conteudo = xml_nfse(prestador_documento=cnpj_da_filial_b, incluir_tomador=False)
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    assert lote.total_recusados == 1
    assert lote.resultados.get().motivo == services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


def test_localizar_empresa_do_escritorio_sem_mapa_externo_continua_isolado(
    escritorio_a, escritorio_b, usuario_gestor_a
):
    # Achado N3 da reconferência (BL-528, DL-039): antes desta correção
    # havia DOIS caminhos de identificação — um com o dicionário (usado
    # por `receber_envio`, coberto pelo teste acima) e outro que consultava
    # o banco direto quando `mapa` não era fornecido, sem NENHUM teste
    # próprio, e que a mutação F01 (CNPJ) conseguia atravessar sem
    # reprovar nada. Agora existe um ÚNICO caminho: sem `mapa`, a função
    # MONTA um internamente (`_mapa_de_inscricoes_do_escritorio`), sempre
    # filtrado pelo escritório — o mesmo mecanismo que protege o caminho
    # de produção. Este teste chama `localizar_empresa_do_escritorio`
    # DIRETO, sem passar `mapa`, provando que o caminho "avulso" (fora do
    # laço de um envio) é tão isolado quanto o de produção.
    from apps.fiscal.leitor import ParticipanteLido

    empresa_a = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Empresa A N3 Ltda", cnpj="11222333000181"
    )
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B N3 Ltda", cnpj="99988877000161"
    )

    participante_de_a = ParticipanteLido(
        tipo_documento="CNPJ", documento="11222333000181", nome="Empresa A"
    )
    participante_de_b = ParticipanteLido(
        tipo_documento="CNPJ", documento="99988877000161", nome="Empresa B"
    )

    # Achada corretamente dentro do PRÓPRIO escritório.
    assert services.localizar_empresa_do_escritorio(escritorio_a, participante_de_a) == empresa_a
    # NUNCA encontrada fora dele — o CNPJ de B não "vaza" para uma busca
    # feita com o escritório A, mesmo sem `mapa` fornecido pelo chamador.
    assert services.localizar_empresa_do_escritorio(escritorio_a, participante_de_b) is None


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


# --- DL-038 (R8): prestador/tomador pessoa física COM cadastro -------------


def test_prestador_cpf_cadastrado_no_escritorio_entra_vinculado(escritorio_a, usuario_gestor_a):
    # R8: CPF casa com `Empresa` de `tipo_inscricao=CPF` do MESMO
    # escritório — mesmo comportamento de sucesso que já existe para CNPJ
    # (test_prestador_cliente_gera_vinculo_de_prestador), agora para pessoa
    # física cadastrada.
    empresa_cpf = Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Fulano de Tal",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="12345678909",
        cnpj="",
    )
    conteudo = xml_nfse(
        prestador_tipo="CPF", prestador_documento="12345678909", incluir_tomador=False
    )
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )

    assert lote.total_recebidos == 1
    assert lote.total_recusados == 0
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    vinculos = list(documento.vinculos.all())
    assert len(vinculos) == 1
    assert vinculos[0].empresa == empresa_cpf
    assert vinculos[0].papel == PapelDocumento.PRESTADOR


def test_cpf_de_outro_escritorio_continua_recusado_com_mensagem_identica(
    escritorio_a, escritorio_b, usuario_gestor_a
):
    # Critério 27 (agora para CPF): o CPF cadastrado em OUTRO escritório
    # não pode dar pista de que existe — a recusa "sem cadastro" tem que
    # ser a MESMA, cadastrado alhures ou nunca cadastrado.
    Empresa.objects.create(
        escritorio=escritorio_b,
        razao_social="Fulano de Outro Escritório",
        tipo_inscricao=TipoInscricao.CPF,
        cpf="98765432100",
        cnpj="",
    )
    conteudo_cpf_de_outro_escritorio = xml_nfse(
        prestador_tipo="CPF", prestador_documento="98765432100", incluir_tomador=False
    )
    conteudo_cpf_nunca_cadastrado = xml_nfse(
        identificador=identificador_nfse(21),
        prestador_tipo="CPF",
        prestador_documento="12345678909",
        incluir_tomador=False,
    )

    lote_1 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_cpf_de_outro_escritorio,
        nome_arquivo="nota1.xml",
    )
    lote_2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_cpf_nunca_cadastrado,
        nome_arquivo="nota2.xml",
    )

    esperado = services.MENSAGEM_PARTICIPANTE_PESSOA_FISICA_SEM_CADASTRO
    assert lote_1.resultados.get().motivo == lote_2.resultados.get().motivo
    assert lote_1.resultados.get().motivo == esperado


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


# --- Achado A1 (auditoria rodada 1), reprodução do critério 7/8: um ARQUIVO
# ruim, dentro de um envio com uma nota BOA, não pode derrubar o envio
# inteiro. Cada caso abaixo era 500 na revisão auditada.


def _nfse_com_xnome_grande():
    return xml_nfse(
        identificador=identificador_nfse(600), prestador_nome="A" * 301, incluir_tomador=False
    )


def _nfse_com_nnfse_grande():
    return xml_nfse(identificador=identificador_nfse(601), numero="1" * 14, incluir_tomador=False)


def _nfse_com_nif_grande():
    return xml_nfse(
        identificador=identificador_nfse(602),
        tomador_tipo="NIF",
        tomador_documento="1" * 41,
    )


def _nfse_com_namespace_grande():
    return (
        b'<?xml version="1.0" encoding="UTF-8"?>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse' + b"x" * 600 + b'" versao="1.01">'
        b'<infNFSe Id="' + identificador_nfse(603).encode() + b'"/></NFSe>'
    )


def _nfse_com_versao_grande():
    return xml_nfse(
        identificador=identificador_nfse(604), versao="1" + "0" * 600, incluir_tomador=False
    )


def _nfse_com_encoding_desconhecido():
    return (
        b'<?xml version="1.0" encoding="x-inexistente"?>'
        b'<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.01">'
        b'<infNFSe Id="' + identificador_nfse(605).encode() + b'"/></NFSe>'
    )


@pytest.mark.parametrize(
    "nome_arquivo_ruim,conteudo_ruim_fn",
    [
        ("xnome-grande.xml", _nfse_com_xnome_grande),
        ("nnfse-grande.xml", _nfse_com_nnfse_grande),
        ("nif-grande.xml", _nfse_com_nif_grande),
        ("namespace-grande.xml", _nfse_com_namespace_grande),
        ("versao-grande.xml", _nfse_com_versao_grande),
        ("encoding-desconhecido.xml", _nfse_com_encoding_desconhecido),
    ],
)
def test_arquivo_ruim_com_campo_gigante_nao_derruba_o_lote_com_nota_boa(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a, nome_arquivo_ruim, conteudo_ruim_fn
):
    boa = xml_nfse(identificador=identificador_nfse(599), incluir_tomador=False)
    conteudo_zip = zip_de({"boa.xml": boa, nome_arquivo_ruim: conteudo_ruim_fn()})

    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )

    assert lote.total_arquivos == 2
    assert lote.total_recebidos == 1
    assert lote.total_recusados == 1
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1
    resultado_ruim = lote.resultados.exclude(resultado=TipoResultadoArquivo.RECEBIDO).get()
    assert resultado_ruim.motivo  # tem motivo, não fica em branco
    assert len(resultado_ruim.motivo) <= 500  # nunca estoura a coluna (truncamento, A1)


def test_nome_de_entrada_do_zip_com_600_caracteres_e_truncado_sem_derrubar_o_lote(
    escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    # Achado A1: `caminho_no_zip` (`ResultadoDoArquivo`) tem `max_length=500`
    # — um nome de entrada de 600 caracteres estourava `DataError` na
    # gravação do RESULTADO, não do documento (o XML em si é válido). Isto
    # derrubava o envio INTEIRO, mesmo a nota boa junto tendo sido lida com
    # sucesso.
    boa = xml_nfse(identificador=identificador_nfse(606), incluir_tomador=False)
    nome_gigante = "n" * 600 + ".xml"
    conteudo_zip = zip_de(
        {"boa.xml": boa, nome_gigante: boa}
    )  # mesmo conteúdo -> duplicado, não recusado

    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )

    assert lote.total_arquivos == 2
    assert lote.total_recebidos == 1
    assert lote.total_duplicados == 1
    caminhos = list(lote.resultados.values_list("caminho_no_zip", flat=True))
    assert any(len(c) <= 500 for c in caminhos)
    assert all(len(c) <= 500 for c in caminhos)  # nunca estoura a coluna (truncamento, A1)


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


def test_arquivo_exatamente_no_limite_individual_e_aceito(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    # Achado A9/F21: o teste acima prende só o lado "1 byte A MAIS que o
    # limite é recusado" — uma mutação que trocasse `>` por `>=` ainda
    # passaria nele. Este prende o outro lado: exatamente NO limite (nem
    # um byte a mais) tem que ser ACEITO.
    conteudo = xml_nfse(incluir_tomador=False)
    monkeypatch.setattr(services, "LIMITE_TAMANHO_XML_BYTES", len(conteudo))
    lote = services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    assert lote.total_recebidos == 1


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


# --- Achado A2 (auditoria rodada 1): falha ao LER uma entrada do ZIP -------
#
# Só o CONSTRUTOR de `zipfile.ZipFile` estava protegido — abrir/ler uma
# entrada com deflate corrompido, CRC-32 incompatível, ou método de
# compressão não suportado (deflate64) derrubava o ENVIO INTEIRO com 500.
# Simulado por monkeypatch em `zipfile.ZipFile.open`: reproduzir os três
# tipos exatos de corrupção byte a byte é frágil e não acrescenta cobertura
# além do ponto de código exercitado — o que importa é que QUALQUER falha
# na abertura/leitura de uma entrada vira `EnvioInvalido`, nunca 500.


@pytest.mark.parametrize(
    "excecao",
    [
        zlib.error("Error -3 while decompressing data"),
        zipfile.BadZipFile("Bad CRC-32 for file 'a.xml'"),
        NotImplementedError("compression type 9 (deflate64)"),
        EOFError("Unexpected end of file"),
        OSError("I/O operation failed"),
    ],
)
def test_falha_ao_ler_entrada_do_zip_levanta_envio_invalido(
    escritorio_a, usuario_gestor_a, monkeypatch, excecao
):
    zip_valido = zip_de({"nota.xml": xml_nfse()})

    def _open_com_erro(self, *args, **kwargs):
        raise excecao

    monkeypatch.setattr(zipfile.ZipFile, "open", _open_com_erro)
    with pytest.raises(services.EnvioInvalido, match="corrompid"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=zip_valido,
            nome_arquivo="lote.zip",
        )
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


# --- Achado A8 (auditoria rodada 1): contagem de entradas pelo EOCD --------


def test_contagem_de_entradas_pelo_eocd_recusa_zip_com_muitas_entradas_vazias(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    # Reproduz o ataque medido pela auditoria (ZIP de 601.184 entradas
    # VAZIAS) numa escala menor: o ponto sob teste é que a recusa acontece
    # pela LEITURA DO EOCD, sem `infolist()` — provado indiretamente por
    # `test_contagem_de_entradas_do_zip_bate_com_zipfile` (services) e
    # `test_infolist_nao_e_chamado_quando_o_eocd_ja_recusa` (monkeypatch)
    # abaixo; aqui, o comportamento OBSERVÁVEL: recusado com a mensagem
    # certa, mesmo limite de sempre.
    monkeypatch.setattr(services, "LIMITE_ARQUIVOS_NO_ENVIO", 100)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        for i in range(150):
            arquivo_zip.writestr(f"{i}.xml", b"")
    with pytest.raises(services.EnvioInvalido, match="150 arquivos"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=buffer.getvalue(),
            nome_arquivo="lote.zip",
        )


def test_infolist_nao_e_chamado_quando_o_eocd_ja_recusa(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    # Achado A8: a checagem cedo (EOCD) evita PAGAR o custo de
    # `infolist()` quando já dá para recusar sem ele. Mata o mutante que
    # apagaria a chamada cedo (`_contagem_de_entradas_do_zip`) sem
    # reintroduzir o comportamento errado (`infolist()` sempre chamado):
    # se a checagem cedo não existisse, `ZipFile.infolist` SERIA chamado
    # antes da recusa — este teste falharia.
    monkeypatch.setattr(services, "LIMITE_ARQUIVOS_NO_ENVIO", 2)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as arquivo_zip:
        for i in range(5):
            arquivo_zip.writestr(f"{i}.xml", b"")
    conteudo = buffer.getvalue()

    chamado = {"vezes": 0}
    infolist_original = zipfile.ZipFile.infolist

    def _infolist_contado(self, *args, **kwargs):
        chamado["vezes"] += 1
        return infolist_original(self, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "infolist", _infolist_contado)
    with pytest.raises(services.EnvioInvalido, match="5 arquivos"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=conteudo,
            nome_arquivo="lote.zip",
        )
    assert chamado["vezes"] == 0, "infolist() foi chamado mesmo com o EOCD já recusando cedo."


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
