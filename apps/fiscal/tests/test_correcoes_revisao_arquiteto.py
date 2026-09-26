"""Testes das quatro correções pedidas pelo arquiteto na revisão da entrega
original de `apps.fiscal.services` (DL-010 F1):

1. Memória antes do limite — `_ler_bytes_do_arquivo_enviado` não pode
   carregar um upload inteiro na memória antes de conferir o tamanho.
2. Leitura por entrada do ZIP capada em `LIMITE_TAMANHO_XML_BYTES + 1`,
   nunca no resto da cota total descompactada.
3. (situação anotada no banco — testes em `test_consultas.py`, mais perto
   dos demais testes de `documentos_do_escritorio`.)
4. Mensagem de "duplicado" distingue conteúdo IGUAL de conteúdo DIFERENTE
   sob o mesmo identificador.
"""

from __future__ import annotations

import pytest

from apps.fiscal import services
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, TipoResultadoArquivo
from apps.fiscal.tests.xml_sinteticos import identificador_nfse, xml_evento, xml_nfse, zip_de

pytestmark = pytest.mark.django_db


# --- Correção 1: memória antes do limite ------------------------------------


class _UploadComSizeGrande:
    """Simula um `UploadedFile` cujo `.size` já denuncia um envio grande
    demais. `.chunks()` NUNCA deve ser chamado — se for, o teste falha."""

    def __init__(self, size):
        self.size = size

    def chunks(self):
        raise AssertionError("chunks() não deveria ser chamado: .size já excede o limite")


def test_upload_com_size_acima_do_limite_nunca_chama_chunks(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_TAMANHO_ENVIO_BYTES", 100)
    upload = _UploadComSizeGrande(size=200)
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=upload,
            nome_arquivo="grande.xml",
        )


class _UploadSemSizeComChunks:
    """Sem atributo `.size` — só `.chunks()`. Conta quantos pedaços foram
    ENTREGUES pelo gerador, para provar que a leitura para assim que a
    soma acumulada excede o limite, sem consumir o resto do fluxo."""

    def __init__(self, pedaco: bytes, quantidade: int):
        self._pedaco = pedaco
        self._quantidade = quantidade
        self.pedacos_entregues = 0

    def chunks(self):
        for _ in range(self._quantidade):
            self.pedacos_entregues += 1
            yield self._pedaco


def test_upload_sem_size_aborta_assim_que_os_chunks_somados_excedem_o_limite(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    monkeypatch.setattr(services, "LIMITE_TAMANHO_ENVIO_BYTES", 100)
    # 1000 pedaços de 50 bytes somariam 50.000 bytes se lidos por inteiro —
    # a leitura tem de abortar bem antes disso.
    upload = _UploadSemSizeComChunks(pedaco=b"x" * 50, quantidade=1000)
    with pytest.raises(services.EnvioInvalido):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=upload,
            nome_arquivo="grande.xml",
        )
    # 3 pedaços de 50 bytes já somam 150 > 100 — bem menos que os 1000
    # declarados.
    assert upload.pedacos_entregues <= 3


# --- Correção 2: leitura por entrada do ZIP capada em 1 MB + 1 -------------


def test_entrada_do_zip_nunca_le_mais_que_o_limite_individual_mais_um(monkeypatch):
    monkeypatch.setattr(services, "LIMITE_TAMANHO_XML_BYTES", 50)
    conteudo_real_bem_maior = b"x" * 5000
    conteudo_zip = zip_de({"grande.xml": conteudo_real_bem_maior})

    itens = services._itens_do_zip(conteudo_zip)

    assert len(itens) == 1
    _, dados = itens[0]
    # LIMITE_TAMANHO_XML_BYTES + 1 — nunca os 5000 bytes reais da entrada.
    assert len(dados) == 51


def test_entrada_grande_no_zip_e_recusada_individualmente_sem_derrubar_o_envio(
    escritorio_a, empresa_a, usuario_gestor_a, monkeypatch
):
    boa = xml_nfse(identificador=identificador_nfse(950), incluir_tomador=False)
    monkeypatch.setattr(services, "LIMITE_TAMANHO_XML_BYTES", len(boa) + 10)
    conteudo_zip = zip_de({"boa.xml": boa, "grande.xml": b"y" * 100_000})

    lote = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )

    assert lote.total_recebidos == 1
    assert lote.total_recusados == 1
    recusado = lote.resultados.get(resultado=TipoResultadoArquivo.RECUSADO)
    assert "HI-22" in recusado.motivo


def test_limite_total_descompactado_ainda_vale_com_leitura_capada_por_entrada(
    escritorio_a, usuario_gestor_a, monkeypatch
):
    # A proteção do limite TOTAL descompactado continua valendo mesmo com
    # cada leitura individual capada em LIMITE_TAMANHO_XML_BYTES + 1: a
    # soma entre entradas ainda estoura o teto.
    monkeypatch.setattr(services, "LIMITE_TAMANHO_XML_BYTES", 100)
    monkeypatch.setattr(services, "LIMITE_DESCOMPACTADO_BYTES", 250)
    conteudo_zip = zip_de({f"n{i}.xml": b"y" * 200 for i in range(3)})

    with pytest.raises(services.EnvioInvalido, match="excede"):
        services.receber_envio(
            escritorio=escritorio_a,
            usuario=usuario_gestor_a,
            arquivo=conteudo_zip,
            nome_arquivo="lote.zip",
        )
    assert not DocumentoFiscal.objects.filter(escritorio=escritorio_a).exists()


# --- Correção 4: duplicado com conteúdo diferente merece conferência ------


def test_duplicado_com_mesmo_conteudo_mantem_motivo_generico(
    escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo = xml_nfse(identificador=identificador_nfse(960), incluir_tomador=False)
    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo,
        nome_arquivo="nota-de-novo.xml",
    )
    resultado = lote2.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert resultado.motivo == "Documento já recebido anteriormente por este escritório."
    assert "DIFERENTE" not in resultado.motivo


def test_duplicado_com_conteudo_diferente_avisa_para_conferir(
    escritorio_a, empresa_a, usuario_gestor_a
):
    identificador = identificador_nfse(961)
    original = xml_nfse(
        identificador=identificador, prestador_nome="Nome Original", incluir_tomador=False
    )
    divergente = xml_nfse(
        identificador=identificador, prestador_nome="Nome Bem Diferente", incluir_tomador=False
    )
    assert original != divergente  # sanidade: são conteúdos realmente distintos

    services.receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=original, nome_arquivo="nota.xml"
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=divergente,
        nome_arquivo="nota-divergente.xml",
    )

    resultado = lote2.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert "DIFERENTE" in resultado.motivo
    assert "conferir" in resultado.motivo.lower()

    # O original NUNCA é sobrescrito: continua com o nome do prestador de
    # antes, não o do arquivo divergente.
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a, identificador=identificador)
    assert documento.prestador_nome == "Nome Original"
    assert DocumentoFiscal.objects.filter(escritorio=escritorio_a).count() == 1


def test_evento_duplicado_com_mesmo_conteudo_mantem_motivo_generico(escritorio_a, usuario_gestor_a):
    conteudo = xml_evento(numero_pedido="001")
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo,
        nome_arquivo="evento.xml",
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo,
        nome_arquivo="evento-de-novo.xml",
    )
    resultado = lote2.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert resultado.motivo == "Evento já recebido anteriormente por este escritório."


def test_evento_duplicado_com_conteudo_diferente_avisa_para_conferir(
    escritorio_a, usuario_gestor_a
):
    identificador = identificador_nfse(962)
    from apps.fiscal.tests.xml_sinteticos import chave_nfse_de, identificador_evento

    chave = chave_nfse_de(identificador)
    id_evento = identificador_evento(chave, "e101101")

    original = xml_evento(
        chave_nfse=chave, identificador=id_evento, dh_evento="2024-01-20T10:00:00-03:00"
    )
    divergente = xml_evento(
        chave_nfse=chave, identificador=id_evento, dh_evento="2024-01-21T11:00:00-03:00"
    )
    assert original != divergente

    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=original,
        nome_arquivo="evento.xml",
    )
    lote2 = services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=divergente,
        nome_arquivo="evento-divergente.xml",
    )

    resultado = lote2.resultados.get()
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert "DIFERENTE" in resultado.motivo

    evento = EventoFiscal.objects.get(escritorio=escritorio_a, identificador=id_evento)
    assert bytes(evento.xml_original) == original
    assert EventoFiscal.objects.filter(escritorio=escritorio_a).count() == 1
