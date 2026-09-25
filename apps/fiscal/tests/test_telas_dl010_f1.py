"""Testes das TELAS de recepção e conferência de documentos fiscais
(DL-010, fatia 1, etapa 2 — `especialista-frontend`).

Cada teste referencia o critério de aceite numerado do plano
(docs/planos/DL-010-F1-recepcao-nfse.md). Dados 100% sintéticos — nenhum
arquivo do acervo real do Fred entra no repositório (regra do plano),
reaproveitando os mesmos geradores que `apps.fiscal.tests.xml_sinteticos`
já usa para os testes de servidor.

Fixtures de escritório/empresa/usuário vêm de `apps/fiscal/tests/conftest.py`
(descoberta automática do pytest, mesmo diretório) — nenhuma redefinição
aqui.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.empresas.models import Empresa
from apps.fiscal.models import DocumentoFiscal, EventoFiscal, LoteDeRecepcao
from apps.fiscal.services import receber_envio
from apps.fiscal.tests.xml_sinteticos import (
    CNPJ_PRESTADOR_PADRAO,
    chave_nfse_de,
    xml_evento,
    xml_nfse,
    zip_de,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _upload(nome, conteudo):
    return SimpleUploadedFile(nome, conteudo, content_type="application/xml")


# ---------------------------------------------------------------------------
# Critério 26 — autorização no servidor
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nome_rota,kwargs",
    [
        ("fiscal_web:recepcao", {}),
        ("fiscal_web:documentos_lista", {}),
    ],
)
def test_sem_sessao_redireciona_ao_login(client, nome_rota, kwargs):
    resposta = client.get(reverse(nome_rota, kwargs=kwargs))
    assert resposta.status_code == 302
    assert "/login/" in resposta.url


def test_cliente_nao_envia_documentos(client, usuario_cliente_a):
    client.force_login(usuario_cliente_a)
    resposta = client.get(reverse("fiscal_web:recepcao"))
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


def test_cliente_nao_consulta_documentos(client, usuario_cliente_a):
    client.force_login(usuario_cliente_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"))
    assert resposta.status_code == 403
    assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


def test_post_de_envio_sem_permissao_nao_grava_lote_nem_trilha(client, usuario_cliente_a):
    """Critério 26: o POST sem permissão é recusado ANTES de tocar no
    banco — nem lote, nem trilha de auditoria."""
    client.force_login(usuario_cliente_a)
    # Contagem DEPOIS do login (deliberado): o próprio login já grava sua
    # própria entrada de trilha ("login.sucesso",
    # apps/accounts/signals.py) — contar antes do login incluiria essa
    # entrada, alheia ao que este teste verifica.
    total_lotes_antes = LoteDeRecepcao.objects.count()
    total_trilha_antes = RegistroAuditoria.objects.count()

    resposta = client.post(
        reverse("fiscal_web:recepcao"), {"arquivo": _upload("nota.xml", xml_nfse())}
    )

    assert resposta.status_code == 403
    assert LoteDeRecepcao.objects.count() == total_lotes_antes
    assert RegistroAuditoria.objects.count() == total_trilha_antes


def test_analista_recebe_e_consulta(client, usuario_analista_a):
    """ANALISTA está nos dois papéis (HI-21) — envio e consulta funcionam."""
    client.force_login(usuario_analista_a)
    assert client.get(reverse("fiscal_web:recepcao")).status_code == 200
    assert client.get(reverse("fiscal_web:documentos_lista")).status_code == 200


# ---------------------------------------------------------------------------
# Critério 27 — isolamento em todas as portas (404, nunca 403)
# ---------------------------------------------------------------------------


def test_lote_de_outro_escritorio_e_404(client, escritorio_a, escritorio_b, usuario_gestor_a):
    lote_b = receber_envio(
        escritorio=escritorio_b,
        usuario=_usuario_qualquer_de(escritorio_b),
        arquivo=xml_nfse(),
        nome_arquivo="nota-b.xml",
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:relatorio_envio", args=[lote_b.id]))
    assert resposta.status_code == 404


def _criar_empresa_prestadora(escritorio):
    """Empresa cujo CNPJ casa com o prestador PADRÃO de `xml_nfse()`
    (`CNPJ_PRESTADOR_PADRAO`) — só para que `receber_envio` RECEBA (e não
    recuse por falta de participante do escritório) uma nota sintética em
    um escritório que não é o `escritorio_a` da fixture padrão (que já tem
    `empresa_a`/`empresa_a2` com esses CNPJs)."""
    return Empresa.objects.create(
        escritorio=escritorio,
        razao_social=f"Prestadora de teste ({escritorio.id})",
        cnpj=CNPJ_PRESTADOR_PADRAO,
    )


def test_documento_de_outro_escritorio_e_404(client, escritorio_b, usuario_gestor_a):
    _criar_empresa_prestadora(escritorio_b)
    receber_envio(
        escritorio=escritorio_b,
        usuario=_usuario_qualquer_de(escritorio_b),
        arquivo=xml_nfse(),
        nome_arquivo="nota-b.xml",
    )
    documento_b = DocumentoFiscal.objects.get(escritorio=escritorio_b)
    client.force_login(usuario_gestor_a)

    assert (
        client.get(reverse("fiscal_web:documento_detalhe", args=[documento_b.id])).status_code
        == 404
    )
    assert client.get(reverse("fiscal_web:documento_xml", args=[documento_b.id])).status_code == 404


def test_evento_de_outro_escritorio_e_404(client, escritorio_b, usuario_gestor_a):
    _criar_empresa_prestadora(escritorio_b)
    usuario_b = _usuario_qualquer_de(escritorio_b)
    receber_envio(
        escritorio=escritorio_b, usuario=usuario_b, arquivo=xml_nfse(), nome_arquivo="nota-b.xml"
    )
    documento_b = DocumentoFiscal.objects.get(escritorio=escritorio_b)
    receber_envio(
        escritorio=escritorio_b,
        usuario=usuario_b,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento_b.identificador)),
        nome_arquivo="evento-b.xml",
    )
    evento_b = EventoFiscal.objects.get(escritorio=escritorio_b)

    client.force_login(usuario_gestor_a)
    assert client.get(reverse("fiscal_web:evento_xml", args=[evento_b.id])).status_code == 404


def test_filtro_por_empresa_de_outro_escritorio_nao_vaza(client, empresa_b, usuario_gestor_a):
    """Critério 27: filtrar a lista por uma empresa de OUTRO escritório
    nunca lista os documentos dela — o filtro simplesmente não casa (o
    mesmo comportamento de um ID inválido), nunca um 500 nem um vazamento."""
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"), {"empresa": empresa_b.id})
    assert resposta.status_code == 400
    # O apóstrofo da mensagem sai HTML-escapado (&#x27;) na renderização —
    # a asserção evita o caractere para não depender da forma de escape.
    assert "Empresa" in resposta.content.decode()
    assert "inválida" in resposta.content.decode()


def _usuario_qualquer_de(escritorio):
    usuario = get_user_model().objects.create_user(
        username=f"usuario-auxiliar-{escritorio.id}",
        email=f"aux-{escritorio.id}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


# ---------------------------------------------------------------------------
# Critério 29 — XML original preservado no download
# ---------------------------------------------------------------------------


def test_download_do_xml_do_documento_preserva_bytes_exatos(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo = xml_nfse()
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=conteudo, nome_arquivo="nota.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documento_xml", args=[documento.id]))

    assert resposta.status_code == 200
    assert resposta.content == conteudo
    assert resposta["Content-Type"] == "application/xml"
    assert resposta["Content-Disposition"].startswith("attachment;")
    assert resposta["X-Content-Type-Options"] == "nosniff"


def test_download_do_xml_do_evento_preserva_bytes_exatos(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_nfse(),
        nome_arquivo="nota.xml",
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    conteudo_evento = xml_evento(chave_nfse=chave_nfse_de(documento.identificador))
    receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_evento,
        nome_arquivo="evento.xml",
    )
    evento = EventoFiscal.objects.get(escritorio=escritorio_a)

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:evento_xml", args=[evento.id]))

    assert resposta.status_code == 200
    assert resposta.content == conteudo_evento
    assert resposta["Content-Type"] == "application/xml"
    assert resposta["X-Content-Type-Options"] == "nosniff"


# ---------------------------------------------------------------------------
# Tela 1: envio — estados vazio/erro/sucesso
# ---------------------------------------------------------------------------


def test_recepcao_estado_vazio(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:recepcao"))
    assert resposta.status_code == 200
    assert "Nenhum envio de documentos fiscais foi feito ainda" in resposta.content.decode()


def test_recepcao_sem_arquivo_e_erro_sem_500(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.post(reverse("fiscal_web:recepcao"), {})
    assert resposta.status_code == 400
    assert LoteDeRecepcao.objects.count() == 0


def test_recepcao_envio_vazio_e_erro_do_servico_sem_500(client, usuario_gestor_a):
    """`EnvioInvalido` (envio vazio) vira 400 com a mensagem do serviço, não
    um 500 — e nada é gravado (mesmo contrato de `services.receber_envio`)."""
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        reverse("fiscal_web:recepcao"),
        {"arquivo": SimpleUploadedFile("vazio.xml", b"", content_type="application/xml")},
    )
    assert resposta.status_code == 400
    assert LoteDeRecepcao.objects.count() == 0


def test_recepcao_sucesso_redireciona_ao_relatorio(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.post(
        reverse("fiscal_web:recepcao"), {"arquivo": _upload("nota.xml", xml_nfse())}
    )
    lote = LoteDeRecepcao.objects.get(escritorio=escritorio_a)
    assert resposta.status_code == 302
    assert resposta.url == reverse("fiscal_web:relatorio_envio", args=[lote.id])
    assert lote.total_recebidos == 1


def test_recepcao_lista_envios_recentes(client, escritorio_a, usuario_gestor_a):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:recepcao"))
    assert resposta.status_code == 200
    assert "a.xml" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Tela 2: relatório do envio — recebido/duplicado/recusado, tudo em texto
# ---------------------------------------------------------------------------


def test_relatorio_do_envio_mostra_recebido_duplicado_e_recusado(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    conteudo_zip = zip_de(
        {
            "nota_ok.xml": xml_nfse(numero="1"),
            "nota_ok_repetida.xml": xml_nfse(numero="1"),  # mesmo Id => duplicado
            "lixo.xml": b"isto nao e xml valido",
        }
    )
    lote = receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=conteudo_zip,
        nome_arquivo="lote.zip",
    )
    assert lote.total_recebidos == 1
    assert lote.total_duplicados == 1
    assert lote.total_recusados == 1

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:relatorio_envio", args=[lote.id]))
    texto = resposta.content.decode()

    assert resposta.status_code == 200
    assert "Recebido" in texto
    assert "Duplicado" in texto
    assert "Recusado" in texto
    # Critério de tela do plano: destaque visual acessível, NUNCA só cor —
    # as classes de reforço aparecem junto do texto, nunca no lugar dele.
    assert "resultado-arquivo--duplicado" in texto
    assert "resultado-arquivo--recusado" in texto


def test_relatorio_de_lote_inexistente_e_404(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:relatorio_envio", args=[999999]))
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Tela 3: lista de documentos — filtros, situação, estado vazio
# ---------------------------------------------------------------------------


def test_documentos_lista_estado_vazio(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"))
    assert resposta.status_code == 200
    assert "Nenhum documento fiscal recebido ainda" in resposta.content.decode()


def test_documentos_lista_mostra_documento_recebido(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"))
    texto = resposta.content.decode()
    assert resposta.status_code == 200
    assert "Prestador Teste Ltda" in texto
    assert "100,00" in texto  # v_serv formatado pt-BR


def test_documentos_lista_situacao_cancelada_nunca_parece_valida(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo="evento.xml",
    )

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"))
    texto = resposta.content.decode()
    assert "situacao-documento--cancelada" in texto
    assert ">Cancelada<" in texto


def test_documentos_lista_filtro_de_competencia_invalida_preserva_digitado(
    client, usuario_gestor_a
):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"), {"ano": "abc", "mes": "1"})
    assert resposta.status_code == 400
    texto = resposta.content.decode()
    assert 'value="abc"' in texto


def test_documentos_lista_filtro_por_empresa_do_escritorio(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documentos_lista"), {"empresa": empresa_a.id})
    assert resposta.status_code == 200
    assert "Prestador Teste Ltda" in resposta.content.decode()


# ---------------------------------------------------------------------------
# Tela 4: detalhe do documento
# ---------------------------------------------------------------------------


def test_documento_detalhe_mostra_vinculos_e_link_de_xml(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documento_detalhe", args=[documento.id]))
    texto = resposta.content.decode()

    assert resposta.status_code == 200
    assert documento.identificador in texto
    assert "Prestadora A Ltda" in texto  # empresa_a, vínculo prestador
    assert "Tomadora A2 Ltda" in texto  # empresa_a2, vínculo tomador
    assert reverse("fiscal_web:documento_xml", args=[documento.id]) in texto


def test_documento_detalhe_lista_evento_que_cancela(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    receber_envio(
        escritorio=escritorio_a, usuario=usuario_gestor_a, arquivo=xml_nfse(), nome_arquivo="a.xml"
    )
    documento = DocumentoFiscal.objects.get(escritorio=escritorio_a)
    receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(documento.identificador), codigo="e101101"),
        nome_arquivo="evento.xml",
    )

    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documento_detalhe", args=[documento.id]))
    texto = resposta.content.decode()
    assert "e101101" in texto
    assert "situacao-documento--cancelada" in texto


def test_documento_detalhe_inexistente_e_404(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("fiscal_web:documento_detalhe", args=[999999]))
    assert resposta.status_code == 404


# ---------------------------------------------------------------------------
# Sem escritório ativo (nenhum vínculo) — não é 500, é a tela dedicada
# ---------------------------------------------------------------------------


def test_sem_escritorio_ativo_nao_quebra(client, usuario_sem_vinculo):
    client.force_login(usuario_sem_vinculo)
    resposta = client.get(reverse("fiscal_web:recepcao"))
    assert resposta.status_code == 200
    assert "empresas/sem_escritorio.html" in [t.name for t in resposta.templates]


# ---------------------------------------------------------------------------
# Navegação principal (templates/base.html): o link para o Fiscal aparece
# quando a rota existe, e a moldura não quebra quando ela não existe — ver
# o comentário em templates/base.html sobre `{% url ... as %}`.
# ---------------------------------------------------------------------------


def test_link_fiscal_aparece_na_navegacao_principal(client, usuario_gestor_a):
    client.force_login(usuario_gestor_a)
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    assert reverse("fiscal_web:recepcao") in resposta.content.decode()
