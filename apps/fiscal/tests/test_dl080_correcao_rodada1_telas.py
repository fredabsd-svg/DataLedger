"""DL-080, correção da auditoria rodada 1: quadro de totais por direção (A5) e interface (A9).

Os valores esperados estão escritos à mão, como os de `test_dl080_telas.py`. Os XML são sintéticos.
A direção sai do serviço (`direcao_para_o_cliente`); a tela só mostra o que o serviço calcula.
"""

import re

import pytest
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_EMITENTE_A,
    CPF_CLIENTE,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
)

pytestmark = pytest.mark.django_db

TITULO_TOTAIS = "Totais das NF-e recebidas pela empresa, por situação"
TITULO_LISTA = "NF-e e NFC-e recebidas pela empresa"


def _enviar(escritorio, usuario, conteudo, nome="nota.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    ).resultados.get()


def _html(resposta):
    return resposta.content.decode("utf-8")


def _texto(trecho):
    return " ".join(re.sub(r"<[^>]+>", " ", trecho).split())


def _linhas_da_tabela(html, legenda):
    """Linhas (listas de textos) da tabela cuja legenda começa por `legenda`. `[]` sem a tabela."""
    bloco = re.search(
        r"<table[^>]*>\s*<caption[^>]*>" + re.escape(legenda) + r".*?</table>", html, re.S
    )
    if bloco is None:
        return []
    linhas = []
    for linha in re.findall(r"<tr>(.*?)</tr>", bloco.group(0), re.S):
        celulas = re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", linha, re.S)
        linhas.append([_texto(celula) for celula in celulas])
    return linhas


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def cliente_de_fora(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Cliente Sintetico Ltda", cnpj=CNPJ_DE_FORA
    )


# =========================================================================================
# A5 — totais: a soma das autorizadas sai por direção, e a cancelada fica fora de todas.
# =========================================================================================


def test_quadro_de_totais_separa_as_direcoes_com_valores_escritos_a_mao(
    client, escritorio_a, usuario_gestor_a, emitente
):
    """Uma nota de cada direção, com vNF conhecido:
    - saída: a empresa emite, tpNF 1 -> 1.234,56
    - entrada: a empresa é destinatária, tpNF 1 -> 500,00
    - entrada própria: a empresa emite, tpNF 0 -> 80,00
    - a conferir: a empresa é destinatária, tpNF 0 -> 10,00
    - cancelada (saída de 999,00): fica numa linha própria e fora das outras.
    """
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(numero="1", totais={"vNF": "1234.56"}))
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(
            numero="2",
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", CNPJ_EMITENTE_A),
            tp_nf="1",
            totais={"vNF": "500.00"},
        ),
    )
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(numero="3", tp_nf="0", totais={"vNF": "80.00"}),
    )
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(
            numero="4",
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", CNPJ_EMITENTE_A),
            tp_nf="0",
            totais={"vNF": "10.00"},
        ),
    )
    cancelada = _enviar(
        escritorio_a, usuario_gestor_a, xml_nfe(numero="5", totais={"vNF": "999.00"})
    ).documento_nfe
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(chave=cancelada.chave, c_stat="135"))

    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"))
    totais = _linhas_da_tabela(html, TITULO_TOTAIS)

    assert totais[1] == ["Autorizadas: saída", "1", "1.234,56"]
    assert totais[2] == ["Autorizadas: entrada", "1", "500,00"]
    assert totais[3] == ["Autorizadas: entrada própria", "1", "80,00"]
    assert totais[4] == ["Autorizadas: a conferir", "1", "10,00"]
    assert totais[5][0].startswith("Canceladas")
    assert totais[5][1:] == ["1", "999,00"]
    # Nenhuma soma única das autorizadas (1.824,56) e nenhuma soma da cancelada entre as direções.
    assert "1.824,56" not in html
    assert "1.233,56" not in html


def test_cancelada_nao_entra_na_direcao_de_saida(client, escritorio_a, usuario_gestor_a, emitente):
    cancelada = _enviar(
        escritorio_a, usuario_gestor_a, xml_nfe(numero="1", totais={"vNF": "80.00"})
    ).documento_nfe
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(chave=cancelada.chave, c_stat="135"))
    client.force_login(usuario_gestor_a)
    totais = _linhas_da_tabela(
        _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}")),
        TITULO_TOTAIS,
    )
    assert totais[1] == ["Autorizadas: saída", "0", "0,00"]
    assert totais[5][1:] == ["1", "80,00"]


def test_nota_sem_vnf_e_contada_e_nao_soma(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(numero="1", totais={"vNF": None}))
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(numero="2", totais={"vNF": "25.00"}))
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"))
    totais = _linhas_da_tabela(html, TITULO_TOTAIS)
    assert totais[1] == ["Autorizadas: saída", "2", "25,00"]
    assert "Notas sem vNF no XML não entram na soma: 1 autorizada(s) e 0 cancelada(s)." in _texto(
        html
    )


# =========================================================================================
# A9 — interface: CNPJ e CPF sem quebra, rolagem só na tabela, rótulo do módulo.
# =========================================================================================


def test_cnpj_da_contraparte_nao_quebra_no_meio(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"))
    # Destinatário (contraparte da emitente) com máscara de CNPJ, dentro de um trecho sem quebra.
    assert re.search(
        r'<span class="texto-apoio documento-sem-quebra">'
        r"CNPJ \d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}</span>",
        html,
    )


def test_cpf_da_contraparte_nao_quebra_no_meio(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(emitente=("CNPJ", CNPJ_EMITENTE_A), destinatario=("CPF", CPF_CLIENTE)),
    )
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"))
    assert re.search(
        r'<span class="texto-apoio documento-sem-quebra">'
        r"CPF \d{3}\.\d{3}\.\d{3}-\d{2}</span>",
        html,
    )


def test_detalhe_mostra_cnpj_sem_quebra(client, escritorio_a, usuario_gestor_a, emitente):
    documento = _enviar(escritorio_a, usuario_gestor_a, xml_nfe()).documento_nfe
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_detalhe", args=[emitente.pk, documento.pk])))
    assert re.search(
        r'<span class="documento-sem-quebra">CNPJ \d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}</span>', html
    )


def test_tabelas_da_conferencia_rolam_dentro_do_contentor_e_nao_a_pagina(
    client, escritorio_a, usuario_gestor_a, emitente
):
    """Rolagem horizontal só no contêiner da tabela (classe do projeto), em todas as telas novas."""
    documento = _enviar(escritorio_a, usuario_gestor_a, xml_nfe()).documento_nfe
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(chave=documento.chave, c_stat="135"))
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        proc_evento_xml(chave=chave_nfe(emitente=CNPJ_EMITENTE_A, numero="8"), c_stat="135"),
    )
    client.force_login(usuario_gestor_a)
    paginas = {
        "lista": client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"),
        "detalhe": client.get(reverse("fiscal_web:nfe_detalhe", args=[emitente.pk, documento.pk])),
        "orfaos": client.get(reverse("fiscal_web:nfe_eventos_orfaos")),
    }
    contentor = '<div class="tabela-com-rolagem-horizontal">'
    for nome, resposta in paginas.items():
        html = _html(resposta)
        tabelas = list(re.finditer(r"<table[^>]*>", html))
        assert tabelas, nome
        # Cada tabela da conferência abre logo depois do contêiner rolável: nenhuma solta na página.
        for tabela in tabelas:
            assert html[: tabela.start()].rstrip().endswith(contentor), nome


def test_rotulo_do_modulo_na_barra_lateral_diz_recepcao_de_documentos_fiscais(
    client, escritorio_a, usuario_gestor_a, emitente
):
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_recebidas") + f"?empresa={emitente.pk}"))
    assert "Recepção de NFS-e" not in html
    assert "Recepção de documentos fiscais" in html


def test_evento_110110_tem_o_nome_oficial_com_c_maiusculo(
    client, escritorio_a, usuario_gestor_a, emitente
):
    documento = _enviar(escritorio_a, usuario_gestor_a, xml_nfe()).documento_nfe
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        proc_evento_xml(chave=documento.chave, tp_evento="110110", c_stat="135"),
    )
    client.force_login(usuario_gestor_a)
    html = _html(client.get(reverse("fiscal_web:nfe_detalhe", args=[emitente.pk, documento.pk])))
    assert "Carta de Correção" in html
    assert "Carta de correção" not in html


@pytest.mark.parametrize(
    "rotulo, esperado",
    [
        ("NF-e", "NF-e já recebida anteriormente por este escritório."),
        ("Evento de NF-e", "Evento de NF-e já recebido anteriormente por este escritório."),
        ("Documento", "Documento já recebido anteriormente por este escritório."),
    ],
)
def test_mensagem_de_duplicado_concorda_com_o_rotulo(rotulo, esperado):
    """A concordância sai do participio, e a NFS-e ("Documento") não muda."""
    existente = type("Existente", (), {"sha256_arquivo": "a" * 64})()
    assert (
        services._motivo_de_duplicado(
            existente,
            "a" * 64,
            rotulo,
            participio="recebida" if rotulo == "NF-e" else "recebido",
        )
        == esperado
    )
