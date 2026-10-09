"""DL-080, correção da auditoria rodada 1 (A1 a A4, A7, A8): regressão e mutantes sobreviventes.

Cada bloco nomeia o achado. Os de LEITOR (`ler_arquivo`) não tocam o banco. Os de SERVIÇO e API
passam pelo pipeline real (`services.receber_envio`) com XML sintético. Os mutantes que o relatório
da rodada 1 deixou vivos (M03b, M03c, M06f, M07d, M07g, M07h, M07l, M11b, M12b, M28, M30, M40) têm
aqui o teste que os derruba. O resultado de cada mutação está no relatório da correção.
"""

import hashlib
import json
import re
from datetime import datetime, timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import leitor, services
from apps.fiscal.models import DocumentoNFe, EventoNFe, TipoResultadoArquivo, VinculoNFeEmpresa
from apps.fiscal.services import AVISO_EVENTO_NAO_VINCULADO_NFE
from apps.fiscal.tests import xml_nfe_xsd_dl080 as corpus
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_EMITENTE_A,
    CNPJ_SEM_CADASTRO,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
)
from apps.fiscal.tests.xml_sinteticos import zip_de
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
DATA_PADRAO = "2026-01-15T10:00:00-03:00"
MENSAGEM_NENHUM_PARTICIPANTE = services.MENSAGEM_NENHUM_PARTICIPANTE_DO_ESCRITORIO


# --- helpers ------------------------------------------------------------------------------


def _ler(conteudo: bytes):
    return leitor.ler_arquivo(conteudo, hashlib.sha256(conteudo).hexdigest())


def _recusa(conteudo: bytes) -> str:
    """Mensagem da recusa do leitor. Falha o teste se o XML não for recusado."""
    with pytest.raises(leitor.ArquivoRecusado) as exc:
        _ler(conteudo)
    return str(exc.value)


def _enviar(escritorio, usuario, conteudo, nome="nota.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    )


def _unico(lote):
    return lote.resultados.get()


def _json(resposta):
    return json.loads(resposta.content)


def _url_lista_api(empresa):
    return reverse("fiscal_api:nfe_notas", args=[empresa.pk])


def _url_detalhe_api(empresa, documento):
    return reverse("fiscal_api:nfe_detalhe", args=[empresa.pk, documento.pk])


def _url_lista_web(empresa, pagina=None):
    url = reverse("fiscal_web:nfe_recebidas") + f"?empresa={empresa.pk}"
    return url if pagina is None else f"{url}&pagina={pagina}"


def _url_detalhe_web(empresa, documento):
    return reverse("fiscal_web:nfe_detalhe", args=[empresa.pk, documento.pk])


def _html(resposta):
    return resposta.content.decode("utf-8")


# --- fixtures -----------------------------------------------------------------------------


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def gestor(usuario_gestor_a):
    return usuario_gestor_a


@pytest.fixture
def gestor_b(escritorio_b):
    usuario = get_user_model().objects.create_user(
        username="gestor-rodada1-b",
        email="gestor-rodada1-b@escritorio-fiscal-teste.com.br",
        password=SENHA,
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio_b, papel=Papel.GESTOR
    )
    return usuario


@pytest.fixture
def emitente_b(escritorio_b):
    """Mesmo CNPJ do emitente de A, em OUTRO escritório (DL-041: é permitido, e é isolado)."""
    return Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Emitente de B Ltda", cnpj=CNPJ_EMITENTE_A
    )


# =========================================================================================
# A1 — datas: ano fora de 20xx é recusado com o campo nomeado, e nada é gravado.
# =========================================================================================

VALORES_FORA_DO_XSD = [
    "0001-01-01T00:00:00+12:00",
    "9999-12-31T23:59:59-11:00",
    "1999-12-31T23:59:59-03:00",
    "2026-02-30T10:00:00-03:00",  # calendário: 30 de fevereiro
    "2026-01-15T24:00:00-03:00",  # hora fora de 00 a 23
    "2026-01-15T10:00:00+13:00",  # fuso fora de +00:00 a +12:00
    "2026-01-15T10:00:00-12:00",  # fuso fora de -00:00 a -11:00
]


@pytest.mark.parametrize("valor", VALORES_FORA_DO_XSD)
def test_dh_emi_fora_do_xsd_e_recusado_com_o_campo_nomeado(valor):
    mensagem = _recusa(xml_nfe(dh_emi=valor))
    assert "dhEmi" in mensagem


@pytest.mark.parametrize("valor", VALORES_FORA_DO_XSD[:3])
def test_dh_recbto_fora_do_xsd_e_recusado_com_o_campo_nomeado(valor):
    assert "dhRecbto" in _recusa(xml_nfe(dh_recbto=valor))


@pytest.mark.parametrize("valor", VALORES_FORA_DO_XSD[:3])
def test_dh_evento_fora_do_xsd_e_recusado_com_o_campo_nomeado(valor):
    assert "dhEvento" in _recusa(proc_evento_xml(dh_evento=valor))


@pytest.mark.parametrize(
    "valor", ["2000-01-01T00:00:00-00:00", "2099-12-31T23:59:59+12:00", "2026-02-28T23:59:59-11:00"]
)
def test_dh_dentro_de_20xx_e_aceito_nos_limites(valor):
    assert _ler(xml_nfe(dh_emi=valor)).dh_emissao == datetime.fromisoformat(valor)


@pytest.mark.parametrize("campo", ["dhEmi", "dhRecbto", "dhEvento"])
@pytest.mark.parametrize("valor", VALORES_FORA_DO_XSD[:3])
def test_data_absurda_nao_grava_e_as_telas_continuam_respondendo_200(
    client, escritorio_a, gestor, emitente, campo, valor
):
    """Regressão do A1 (500 persistente). A nota boa é gravada antes, para as telas terem o que
    mostrar. A data ruim chega depois, recusada: nada é gravado, e lista, detalhe, órfãos, relatório
    do lote e API respondem 200."""
    boa = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    # Evento órfão (a nota 5 não chegou) com retorno 136: não cancela e não mexe na nota boa.
    orfao = chave_nfe(emitente=CNPJ_EMITENTE_A, numero="5")
    assert _unico(
        _enviar(escritorio_a, gestor, proc_evento_xml(chave=orfao, c_stat="136"))
    ).evento_nfe

    if campo == "dhEmi":
        ruim = xml_nfe(numero="9", dh_emi=valor)
    elif campo == "dhRecbto":
        ruim = xml_nfe(numero="9", dh_recbto=valor)
    else:
        ruim = proc_evento_xml(
            dh_evento=valor, chave=chave_nfe(emitente=CNPJ_EMITENTE_A, numero="9")
        )
    lote_ruim = _enviar(escritorio_a, gestor, ruim)
    resultado = _unico(lote_ruim)
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert campo in resultado.motivo
    assert DocumentoNFe.objects.count() == 1
    assert EventoNFe.objects.count() == 1

    client.force_login(gestor)
    assert client.get(_url_lista_web(emitente)).status_code == 200
    assert client.get(_url_detalhe_web(emitente, boa)).status_code == 200
    assert client.get(reverse("fiscal_web:nfe_eventos_orfaos")).status_code == 200
    assert client.get(reverse("fiscal_web:relatorio_envio", args=[lote_ruim.pk])).status_code == 200
    assert client.get(_url_lista_api(emitente)).status_code == 200
    assert client.get(_url_detalhe_api(emitente, boa)).status_code == 200


# =========================================================================================
# A2 — paginação: desempate determinístico. Sem ele, notas e eventos se repetem ou somem.
# =========================================================================================


def _numeros_da_lista_web(html):
    """Número (nNF) de cada linha de NOTA da tabela de notas. A coluna 2 é o número."""
    tabela = re.search(r"<caption[^>]*>NF-e e NFC-e recebidas pela empresa.*?</table>", html, re.S)
    if tabela is None:
        return []
    numeros = []
    for linha in re.findall(r"<tr>(.*?)</tr>", tabela.group(0), re.S):
        celulas = [
            " ".join(re.sub(r"<[^>]+>", " ", c).split())
            for c in re.findall(r"<td[^>]*>(.*?)</td>", linha, re.S)
        ]
        if celulas[:1] in (["NF-e"], ["NFC-e"]):
            numeros.append(celulas[2])
    return numeros


def _chaves_da_lista_de_orfaos(html):
    """Chave (sem espaços) de cada linha da tabela de eventos sem nota. Primeira célula da linha."""
    return [
        "".join(c.split()) for c in re.findall(r'<td class="valor-quebravel">([^<]*)</td>', html)
    ]


def test_sessenta_notas_com_mesma_emissao_aparecem_todas_nas_paginas(
    client, escritorio_a, gestor, emitente
):
    for numero in range(1, 61):
        _enviar(escritorio_a, gestor, xml_nfe(numero=str(numero)))
    client.force_login(gestor)

    vistas = []
    for pagina in (1, 2, 3):
        vistas += _numeros_da_lista_web(_html(client.get(_url_lista_web(emitente, pagina))))

    assert len(vistas) == 60
    assert len(set(vistas)) == 60
    assert set(vistas) == {str(n) for n in range(1, 61)}


def test_lote_de_600_notas_com_mesma_emissao_nao_repete_nem_omite_nas_paginas(
    client, escritorio_a, usuario_gestor_a, emitente
):
    """A2 no tamanho que expõe o problema: com 60 notas o PostgreSQL devolve o empate na mesma
    ordem em todas as páginas, e a falta de desempate não aparece. Com 600 (24 páginas), sem o
    desempate, notas se repetem e outras somem. Um ZIP só, como o lote real."""
    itens = [(f"n{n}.xml", xml_nfe(numero=str(n))) for n in range(1, 601)]
    _enviar(escritorio_a, usuario_gestor_a, zip_de(itens), nome="lote.zip")
    client.force_login(usuario_gestor_a)

    vistas = []
    for pagina in range(1, 25):
        vistas += _numeros_da_lista_web(_html(client.get(_url_lista_web(emitente, pagina))))

    assert len(vistas) == 600
    assert len(set(vistas)) == 600


def test_lote_de_600_eventos_orfaos_com_mesma_data_e_sequencia_nao_repete_nem_omite(
    client, escritorio_a, usuario_gestor_a
):
    itens = [
        (
            f"e{n}.xml",
            proc_evento_xml(chave=chave_nfe(emitente=CNPJ_EMITENTE_A, numero=str(n)), c_stat="135"),
        )
        for n in range(1, 601)
    ]
    _enviar(escritorio_a, usuario_gestor_a, zip_de(itens), nome="eventos.zip")
    client.force_login(usuario_gestor_a)

    vistas = []
    for pagina in range(1, 25):
        html = _html(client.get(reverse("fiscal_web:nfe_eventos_orfaos") + f"?pagina={pagina}"))
        vistas += _chaves_da_lista_de_orfaos(html)

    assert len(vistas) == 600
    assert len(set(vistas)) == 600


def test_sessenta_eventos_orfaos_com_mesma_data_e_sequencia_aparecem_todos(
    client, escritorio_a, gestor
):
    for numero in range(1, 61):
        chave = chave_nfe(emitente=CNPJ_EMITENTE_A, numero=str(numero))
        _enviar(escritorio_a, gestor, proc_evento_xml(chave=chave, c_stat="135"))
    client.force_login(gestor)

    vistas = []
    for pagina in (1, 2, 3):
        html = _html(client.get(reverse("fiscal_web:nfe_eventos_orfaos") + f"?pagina={pagina}"))
        vistas += _chaves_da_lista_de_orfaos(html)

    esperadas = {chave_nfe(emitente=CNPJ_EMITENTE_A, numero=str(n)) for n in range(1, 61)}
    assert len(vistas) == 60
    assert len(set(vistas)) == 60
    assert set(vistas) == esperadas


# =========================================================================================
# A3 — ambiente: homologação (2) não cancela nem entra, e tpAmb ausente é recusado (XSD).
# =========================================================================================


@pytest.mark.parametrize(
    "kwargs, trecho",
    [
        ({"tp_amb": "2"}, "homologação"),
        ({"tp_amb": None}, "tpAmb"),
        ({"tp_amb": "3"}, "'tpAmb' fora do domínio"),
    ],
)
def test_nota_com_tpamb_invalido_ou_ausente_e_recusada(kwargs, trecho):
    assert trecho in _recusa(xml_nfe(**kwargs))


@pytest.mark.parametrize(
    "kwargs, trecho",
    [
        ({"tp_amb": "2"}, "Evento emitido em ambiente de homologação"),
        ({"tp_amb": None}, "tpAmb do evento"),
        ({"tp_amb_retorno": "2"}, "Retorno de evento emitido em ambiente de homologação"),
        ({"tp_amb_retorno": None}, "tpAmb do retorno do evento"),
    ],
)
def test_evento_com_tpamb_de_homologacao_ou_ausente_e_recusado(kwargs, trecho):
    assert trecho in _recusa(proc_evento_xml(**kwargs))


def test_evento_de_homologacao_nao_cancela_nota_de_producao(escritorio_a, gestor, emitente):
    """O caso que a auditoria mostrou: nota de produção, evento 135 com tpAmb 2. O evento é recusado
    e a nota continua válida."""
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    resultado = _unico(
        _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat="135", tp_amb="2"))
    )
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert services.situacao_da_nfe(nota) == "valida"
    assert not EventoNFe.objects.exists()


def test_retorno_de_homologacao_nao_cancela_nota_de_producao(escritorio_a, gestor, emitente):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    resultado = _unico(
        _enviar(
            escritorio_a,
            gestor,
            proc_evento_xml(chave=nota.chave, c_stat="135", tp_amb_retorno="2"),
        )
    )
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert services.situacao_da_nfe(nota) == "valida"


# =========================================================================================
# A7 e HI-116: só 135 e 155 têm efeito. O 136 é guardado e mostrado com aviso, sem cancelar.
# =========================================================================================


def test_136_e_guardado_sem_cancelar_a_nota(escritorio_a, gestor, emitente):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    resultado = _unico(
        _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat="136"))
    )
    assert resultado.resultado == TipoResultadoArquivo.RECEBIDO
    assert EventoNFe.objects.filter(c_stat="136").count() == 1
    assert services.situacao_da_nfe(nota) == "valida"


@pytest.mark.parametrize("c_stat", ["135", "155"])
def test_135_e_155_cancelam_a_nota(escritorio_a, gestor, emitente, c_stat):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat=c_stat))
    assert services.situacao_da_nfe(nota) == "cancelada"


def test_136_aparece_com_aviso_no_detalhe_da_api_e_nao_nos_outros(
    client, escritorio_a, gestor, emitente
):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(
        escritorio_a, gestor, proc_evento_xml(chave=nota.chave, tp_evento="110111", c_stat="136")
    )
    _enviar(
        escritorio_a,
        gestor,
        proc_evento_xml(chave=nota.chave, tp_evento="110111", n_seq=2, c_stat="135"),
    )
    client.force_login(gestor)
    eventos = {
        e["n_seq_evento"]: e for e in _json(client.get(_url_detalhe_api(emitente, nota)))["eventos"]
    }
    assert eventos[1]["aviso"] == AVISO_EVENTO_NAO_VINCULADO_NFE
    assert eventos[1]["efeito"] == "sem efeito"
    assert eventos[2]["aviso"] is None
    assert eventos[2]["efeito"] == "cancela"


def test_136_aparece_com_aviso_no_detalhe_da_tela(client, escritorio_a, gestor, emitente):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat="136"))
    client.force_login(gestor)
    html = _html(client.get(_url_detalhe_web(emitente, nota)))
    assert AVISO_EVENTO_NAO_VINCULADO_NFE in html
    assert "registrado, mas não vinculado a NF-e (cStat 136) — conferir" in html


# =========================================================================================
# A8 — leniências do leitor: nfeProc com duas NFe, retorno com tipo/sequência diferentes, e chave
# que não confere com o emitente (fora da faixa de NFA-e).
# =========================================================================================


def test_nfe_proc_com_duas_nfe_e_recusado():
    conteudo = xml_nfe().decode("utf-8")
    bloco = conteudo[conteudo.index("<NFe>") : conteudo.index("</NFe>") + len("</NFe>")]
    duas = conteudo.replace(bloco, bloco + bloco, 1)
    assert "mais de uma NFe" in _recusa(duas.encode("utf-8"))


def test_retorno_de_evento_com_tipo_diferente_e_recusado():
    assert "tpEvento diferente" in _recusa(proc_evento_xml(tp_evento_retorno="110110"))


def test_retorno_de_evento_com_sequencia_diferente_e_recusado():
    assert "nSeqEvento diferente" in _recusa(proc_evento_xml(n_seq=1, n_seq_retorno=2))


def test_retorno_com_tipo_e_sequencia_iguais_e_aceito():
    lido = _ler(proc_evento_xml(tp_evento="110111", n_seq=1, c_stat="135"))
    assert (lido.tp_evento, lido.n_seq_evento, lido.c_stat) == ("110111", 1, "135")


@pytest.mark.parametrize("serie", ["890", "899", "900", "919"])
def test_nfa_e_com_cnpj_da_sefaz_na_chave_e_aceita(serie):
    """Séries 890 a 919 (pesquisa, seção 3): a chave leva o CNPJ da SEFAZ, e não o do emitente."""
    sefaz = chave_nfe(emitente="99888777000166", serie=serie)
    lido = _ler(xml_nfe(serie=serie, chave=sefaz))
    assert lido.emitente.documento == CNPJ_EMITENTE_A


@pytest.mark.parametrize("serie", ["889", "920", "970"])
def test_chave_com_cnpj_de_outro_fora_das_series_de_nfa_e_recusada(serie):
    """889 é de aplicativo do contribuinte. 920 é de CPF da empresa. 970 não aparece na pesquisa:
    por ora é conferida como as demais (pendência do relatório da rodada 1)."""
    chave_de_outro = chave_nfe(emitente="99888777000166", serie=serie)
    mensagem = _recusa(xml_nfe(serie=serie, chave=chave_de_outro))
    assert "diferente do emitente" in mensagem


def test_chave_do_proprio_cnpj_do_emitente_e_aceita_na_serie_comum():
    lido = _ler(xml_nfe(serie="5"))
    assert lido.chave[6:20] == CNPJ_EMITENTE_A


def test_emitente_cpf_da_serie_920_confere_com_o_cpf_zerado_na_chave():
    """Série 920 (aplicativo do contribuinte, CPF): as posições 7 a 20 são o CPF com zeros à
    esquerda (14 posições). A conferência vale, e o CPF da chave confere com o do emitente."""
    lido = _ler(xml_nfe(serie="920", emitente=("CPF", "12345678920")))
    assert lido.emitente.tipo_documento == "CPF"
    assert lido.chave[6:20] == "00012345678920"


# =========================================================================================
# A4 — mutantes sobreviventes. Cada teste nomeia o mutante que derruba.
# =========================================================================================


# M03b (lista da API e da tela) e M03c (efeito) — evento que NÃO é efetivo não cancela.
@pytest.mark.parametrize("c_stat", ["573", None])
def test_evento_rejeitado_ou_sem_retorno_nao_cancela_na_lista_da_api_nem_na_tela(
    client, escritorio_a, gestor, emitente, c_stat
):
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat=c_stat))
    client.force_login(gestor)
    item = _json(client.get(_url_lista_api(emitente)))["notas"][0]
    assert item["situacao"] == "valida"
    html = _html(client.get(_url_lista_web(emitente)))
    assert 'class="situacao-documento situacao-documento--valida"' in html
    assert "situacao-documento--cancelada" not in html


@pytest.mark.parametrize("c_stat", ["573", None])
def test_efeito_do_evento_rejeitado_ou_sem_retorno_e_sem_efeito(escritorio_a, gestor, c_stat):
    _enviar(escritorio_a, gestor, xml_nfe())
    evento = _unico(_enviar(escritorio_a, gestor, proc_evento_xml(c_stat=c_stat))).evento_nfe
    assert services.efeito_do_evento_nfe(evento) == "sem efeito"


def test_573_sem_efeito_no_detalhe_da_api(client, escritorio_a, gestor, emitente):
    """M30: 573 nunca entra em `CODIGOS_EFETIVOS_NFE`."""
    assert "573" not in services.CODIGOS_EFETIVOS_NFE
    nota = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_a, gestor, proc_evento_xml(chave=nota.chave, c_stat="573"))
    client.force_login(gestor)
    detalhe = _json(client.get(_url_detalhe_api(emitente, nota)))
    assert detalhe["situacao"] == "valida"
    assert detalhe["eventos"][0]["efeito"] == "sem efeito"


# M11b — a lista da API devolve a situação real, nunca um valor fixo.
def test_lista_da_api_mostra_cancelada_quando_a_nota_e_cancelada(
    client, escritorio_a, gestor, emitente
):
    cancelada = _unico(_enviar(escritorio_a, gestor, xml_nfe(numero="1"))).documento_nfe
    _enviar(escritorio_a, gestor, xml_nfe(numero="2"))
    _enviar(escritorio_a, gestor, proc_evento_xml(chave=cancelada.chave, c_stat="135"))
    client.force_login(gestor)
    situacoes = {
        item["numero"]: item["situacao"]
        for item in _json(client.get(_url_lista_api(emitente)))["notas"]
    }
    assert situacoes == {"1": "cancelada", "2": "valida"}


# M28 — `mod` 57 e 58 não são NF-e nem NFC-e.
@pytest.mark.parametrize("modelo", ["57", "58"])
def test_modelo_57_e_58_sao_recusados(modelo):
    assert "'mod' fora do domínio" in _recusa(xml_nfe(modelo=modelo))


# M06f — retirada e entrega de terceiros não ligam empresa, mesmo com emit e dest estranhos.
@pytest.mark.parametrize("campo", ["retirada", "entrega"])
def test_retirada_ou_entrega_de_cliente_nao_liga_a_empresa(escritorio_a, gestor, emitente, campo):
    emit = ("CNPJ", CNPJ_DE_FORA)
    dest = ("CNPJ", CNPJ_SEM_CADASTRO)
    cliente = ("CNPJ", CNPJ_EMITENTE_A)  # cliente cadastrado no escritório
    extra = {campo: cliente}
    conteudo = corpus.xml_nfe_valido(emitente=emit, destinatario=dest, **extra)
    resultado = _unico(_enviar(escritorio_a, gestor, conteudo))
    assert resultado.resultado == TipoResultadoArquivo.RECUSADO
    assert resultado.motivo == MENSAGEM_NENHUM_PARTICIPANTE
    assert not VinculoNFeEmpresa.objects.exists()


# M07d / M07g / M07h / M07l / M40 / M12b — isolamento entre escritórios com a MESMA chave.


def test_anotacao_cancelada_da_lista_nao_olha_evento_de_outro_escritorio(
    client, escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """M07d: evento 135 em B para a chave X não cancela a nota X de A."""
    nota_a = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_b, gestor_b, xml_nfe())
    _enviar(escritorio_b, gestor_b, proc_evento_xml(chave=nota_a.chave, c_stat="135"))
    client.force_login(gestor)
    item = _json(client.get(_url_lista_api(emitente)))["notas"][0]
    assert item["situacao"] == "valida"
    assert "situacao-documento--cancelada" not in _html(client.get(_url_lista_web(emitente)))


def test_detalhe_web_nao_mostra_evento_de_outro_escritorio(
    client, escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """M07g: o detalhe de A não lista o evento que B recebeu para a mesma chave."""
    nota_a = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_b, gestor_b, proc_evento_xml(chave=nota_a.chave, c_stat="135"))
    client.force_login(gestor)
    html = _html(client.get(_url_detalhe_web(emitente, nota_a)))
    assert "Nenhum evento registrado para esta nota" in html
    assert services.situacao_da_nfe(nota_a) == "valida"


def test_detalhe_da_api_nao_mostra_evento_de_outro_escritorio(
    client, escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """M07h: o detalhe da API de A não traz eventos de B."""
    nota_a = _unico(_enviar(escritorio_a, gestor, xml_nfe())).documento_nfe
    _enviar(escritorio_b, gestor_b, proc_evento_xml(chave=nota_a.chave, c_stat="135"))
    client.force_login(gestor)
    assert _json(client.get(_url_detalhe_api(emitente, nota_a)))["eventos"] == []


def test_mesma_nota_nos_dois_escritorios_nao_e_duplicado(
    escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """A mesma chave em dois escritórios é duas notas, cada uma no seu acervo. Não é duplicado."""
    _enviar(escritorio_a, gestor, xml_nfe())
    resultado_b = _unico(_enviar(escritorio_b, gestor_b, xml_nfe()))
    assert resultado_b.resultado == TipoResultadoArquivo.RECEBIDO
    assert DocumentoNFe.objects.count() == 2


def test_reenvio_em_a_devolve_a_nota_de_a_e_nao_a_de_b(
    escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """M07l: o duplicado busca a nota do PRÓPRIO escritório. B tem a mesma chave, com outro conteúdo
    e data de emissão mais nova (é a que um `first()` sem escritório devolveria)."""
    original_a = xml_nfe()
    documento_a = _unico(_enviar(escritorio_a, gestor, original_a)).documento_nfe
    _enviar(escritorio_b, gestor_b, xml_nfe(dh_emi="2026-02-01T10:00:00-03:00"))

    resultado = _unico(_enviar(escritorio_a, gestor, original_a))

    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert resultado.documento_nfe.pk == documento_a.pk
    assert "DIFERENTE" not in resultado.motivo
    assert "NF-e já recebida anteriormente por este escritório." == resultado.motivo


def test_mesmo_evento_nos_dois_escritorios_gera_dois_registros_e_nao_e_duplicado(
    escritorio_a, escritorio_b, gestor, gestor_b, emitente, emitente_b
):
    """M12b: unicidade do evento inclui o escritório. Mesmo Id e mesmo conteúdo em A e em B."""
    conteudo = proc_evento_xml(c_stat="135")
    primeiro_b = _unico(_enviar(escritorio_b, gestor_b, conteudo))
    primeiro_a = _unico(_enviar(escritorio_a, gestor, conteudo))
    assert primeiro_a.resultado == primeiro_b.resultado == TipoResultadoArquivo.RECEBIDO
    assert primeiro_a.motivo == primeiro_b.motivo == ""
    assert EventoNFe.objects.count() == 2


def test_mesmo_id_com_conteudo_diferente_em_outro_escritorio_nao_e_sinalizado(
    escritorio_a, escritorio_b, gestor, gestor_b
):
    """M12b, lado do aviso: o aviso 'conteúdo diferente' só vale dentro do MESMO escritório. Em B, o
    mesmo Id com outro retorno é o primeiro registro de B: não há o que conferir."""
    _enviar(escritorio_a, gestor, proc_evento_xml(c_stat="135"))
    resultado_b = _unico(_enviar(escritorio_b, gestor_b, proc_evento_xml(c_stat="573")))
    assert resultado_b.resultado == TipoResultadoArquivo.RECEBIDO
    assert resultado_b.motivo == ""


def test_reenvio_de_evento_em_a_devolve_o_evento_de_a(escritorio_a, escritorio_b, gestor, gestor_b):
    """M40: o duplicado de evento busca no PRÓPRIO escritório.

    Mesmo Id e mesmo conteúdo em A e em B têm o mesmo sha, e pelo pipeline também a mesma data:
    um `first()` sem escritório empataria, e o banco escolheria pela ordem física. Para o teste não
    depender disso, o registro de B é marcado como MAIS RECENTE com um `update` direto. Esse estado
    não sai do pipeline; ele isola a consulta, que tem de ignorar o registro de outro escritório
    mesmo quando ele é o primeiro na ordenação. O resultado esperado não depende da data.
    """
    conteudo = proc_evento_xml(c_stat="135")
    evento_a = _unico(_enviar(escritorio_a, gestor, conteudo)).evento_nfe
    evento_b = _unico(_enviar(escritorio_b, gestor_b, conteudo)).evento_nfe
    EventoNFe.objects.filter(pk=evento_b.pk).update(
        dh_evento=evento_b.dh_evento + timedelta(days=1)
    )
    resultado = _unico(_enviar(escritorio_a, gestor, conteudo))
    assert resultado.resultado == TipoResultadoArquivo.DUPLICADO
    assert resultado.evento_nfe.pk == evento_a.pk
    assert resultado.evento_nfe.pk != evento_b.pk
