"""DL-080, frente B: telas de conferência das NF-e e NFC-e recebidas (só leitura).

Cobre a lista (totais por situação, cancelada fora do total das autorizadas, filtros, paginação),
o detalhe (eventos em ordem, aviso de cancelamento, NFC-e sem destinatário), a lista de eventos sem
nota, a direção pelo papel combinado com `tpNF`, o isolamento entre escritórios e empresas (404 e
IDOR), as permissões, a acessibilidade e os textos em pt-BR escritos à mão.

Os XML são sintéticos (`xml_nfe_dl080`). Os valores esperados estão escritos à mão. A tela não
decide situação nem direção: esses casos passam pelo serviço e pela API da frente A, e aqui só se
confere o que aparece na tela.
"""

import re
from urllib.parse import urlencode

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.html import escape

from apps.contabilidade.tests.test_dl024_atalhos_e_acessibilidade import assert_moldura_acessivel
from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.models import DocumentoNFe
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_DESTINATARIO_A,
    CNPJ_EMITENTE_A,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
TITULO_TOTAIS = "Totais das NF-e recebidas pela empresa, por situação"
TITULO_LISTA = "NF-e e NFC-e recebidas pela empresa"
TITULO_ORFAOS = "Eventos de NF-e cuja nota ainda não chegou"
TITULO_EVENTOS_DA_NOTA = "Eventos de NF-e registrados para a chave desta nota"


# ---------------------------------------------------------------------------
# Auxiliares: usuários, envio, leitura do HTML (regex sobre o texto que a tela gera)
# ---------------------------------------------------------------------------


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio-fiscal-teste.com.br", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


def _enviar(escritorio, usuario, conteudo, nome="nota.xml"):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo=nome
    )


def _nota(escritorio, usuario, **parametros):
    """Recebe uma NF-e ou NFC-e sintética e devolve o `DocumentoNFe` gravado."""
    return _enviar(escritorio, usuario, xml_nfe(**parametros)).resultados.get().documento_nfe


def _evento(escritorio, usuario, **parametros):
    return _enviar(escritorio, usuario, proc_evento_xml(**parametros)).resultados.get().evento_nfe


def _grupos(chave):
    """Chave em grupos de 4, como a tela a mostra."""
    return " ".join(chave[i : i + 4] for i in range(0, len(chave), 4))


def _html(resposta):
    return resposta.content.decode("utf-8")


def _texto(trecho):
    return " ".join(re.sub(r"<[^>]+>", " ", trecho).split())


def _linhas_da_tabela(html, legenda):
    """Linhas (listas de textos de célula) da tabela cuja legenda começa por `legenda`.

    Devolve `[]` quando a página não tem essa tabela (estado vazio).
    """
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


def _linhas_de_nota(html):
    """Só as linhas de dados da lista de notas. A primeira coluna é o modelo (NF-e ou NFC-e)."""
    return [
        linha
        for linha in _linhas_da_tabela(html, TITULO_LISTA)
        if linha[:1] in (["NF-e"], ["NFC-e"])
    ]


def _numeros(html):
    return sorted(linha[2] for linha in _linhas_de_nota(html))


def _url_lista(empresa=None, **consulta):
    dados = {"empresa": empresa.pk} if empresa is not None else {}
    dados.update(consulta)
    url = reverse("fiscal_web:nfe_recebidas")
    return url + ("?" + urlencode(dados) if dados else "")


def _url_detalhe(empresa, documento):
    return reverse("fiscal_web:nfe_detalhe", args=[empresa.pk, documento.pk])


def _url_orfaos(**consulta):
    url = reverse("fiscal_web:nfe_eventos_orfaos")
    return url + ("?" + urlencode(consulta) if consulta else "")


# ---------------------------------------------------------------------------
# Cenário: escritório A com duas empresas; escritório B com uma empresa de MESMO CNPJ
# ---------------------------------------------------------------------------


@pytest.fixture
def emitente(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Emitente Sintetica Ltda", cnpj=CNPJ_EMITENTE_A
    )


@pytest.fixture
def destinatario(escritorio_a):
    return Empresa.objects.create(
        escritorio=escritorio_a,
        razao_social="Destinataria Sintetica Ltda",
        cnpj=CNPJ_DESTINATARIO_A,
    )


@pytest.fixture
def gestor(escritorio_a):
    return _usuario(escritorio_a, Papel.GESTOR, "gestor-nfe-telas-a")


@pytest.fixture
def gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-nfe-telas-b")


@pytest.fixture
def tres_notas(escritorio_a, gestor, emitente, destinatario):
    """Uma NF-e emitida pela empresa (fevereiro), uma NFC-e emitida pela empresa (março, sem
    destinatário no XML) e uma nota que a empresa recebe como destinatária (abril)."""
    _nota(
        escritorio_a,
        gestor,
        numero="10",
        dh_emi="2026-02-10T10:00:00-03:00",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=("CNPJ", CNPJ_DE_FORA),
    )
    _nota(
        escritorio_a,
        gestor,
        numero="20",
        modelo="65",
        dh_emi="2026-03-20T10:00:00-03:00",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=None,
    )
    _nota(
        escritorio_a,
        gestor,
        numero="30",
        dh_emi="2026-04-30T10:00:00-03:00",
        emitente=("CNPJ", CNPJ_DE_FORA),
        destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
    )


# ---------------------------------------------------------------------------
# Lista: autorizada e cancelada, totais, cancelamento antes da nota
# ---------------------------------------------------------------------------


def test_lista_mostra_cancelada_marcada_e_fora_do_total_das_validas(
    client, escritorio_a, gestor, emitente
):
    _nota(escritorio_a, gestor, numero="1", totais={"vNF": "1234.56"})
    cancelada = _nota(escritorio_a, gestor, numero="2", totais={"vNF": "500.00"})
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=cancelada.chave,
        c_stat="135",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    resposta = client.get(_url_lista(emitente))

    assert resposta.status_code == 200
    html = _html(resposta)
    totais = _linhas_da_tabela(html, TITULO_TOTAIS)
    # Autorizadas: só a nota de 1.234,56. Canceladas: a de 500,00, separada e fora do total.
    # A5 (rodada 1): autorizadas saem por direção. A nota do teste é saída (emitente, tpNF 1).
    assert totais[1][:3] == ["Autorizadas: saída", "1", "1.234,56"]
    assert totais[5][0].startswith("Canceladas")
    assert totais[5][1:] == ["1", "500,00"]
    assert "1.734,56" not in html
    linhas = {linha[2]: linha for linha in _linhas_de_nota(html)}
    assert linhas["1"][7] == "Autorizada"
    assert linhas["2"][7] == "Cancelada"
    # Valor de cada nota (coluna Valor (vNF)), em pt-BR, escrito à mão.
    assert linhas["1"][8] == "1.234,56"
    assert linhas["2"][8] == "500,00"


def test_so_com_cancelada_o_total_das_autorizadas_fica_zerado(
    client, escritorio_a, gestor, emitente
):
    cancelada = _nota(escritorio_a, gestor, numero="3", totais={"vNF": "80.00"})
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=cancelada.chave,
        c_stat="135",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    totais = _linhas_da_tabela(_html(client.get(_url_lista(emitente))), TITULO_TOTAIS)

    assert totais[1][:3] == ["Autorizadas: saída", "0", "0,00"]
    assert totais[5][1:] == ["1", "80,00"]


def test_cancelamento_que_chega_antes_da_nota_aparece_cancelado_e_sai_dos_orfaos(
    client, escritorio_a, gestor, emitente
):
    # Ordem inversa: o cancelamento chega primeiro, como órfão, e a nota depois.
    chave = chave_nfe(emitente=CNPJ_EMITENTE_A)
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=chave,
        c_stat="135",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)
    assert _grupos(chave) in _html(client.get(_url_orfaos()))

    nota = _nota(escritorio_a, gestor, numero="1")

    assert nota.chave == chave
    assert _grupos(chave) not in _html(client.get(_url_orfaos()))
    assert _linhas_de_nota(_html(client.get(_url_lista(emitente))))[0][7] == "Cancelada"


# ---------------------------------------------------------------------------
# Lista: direção nos quatro casos de papel × tpNF
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("papel_da_empresa", "tp_nf", "direcao_esperada"),
    [
        ("emitente", "1", "Saída"),
        ("emitente", "0", "Entrada própria"),
        ("destinatario", "1", "Entrada"),
        ("destinatario", "0", "A conferir"),
    ],
)
def test_direcao_na_lista_combina_papel_com_tpnf(
    client, escritorio_a, gestor, emitente, destinatario, papel_da_empresa, tp_nf, direcao_esperada
):
    if papel_da_empresa == "emitente":
        empresa = emitente
        _nota(
            escritorio_a,
            gestor,
            tp_nf=tp_nf,
            emitente=("CNPJ", CNPJ_EMITENTE_A),
            destinatario=("CNPJ", CNPJ_DE_FORA),
        )
        papel_esperado = "Emitente"
    else:
        empresa = destinatario
        _nota(
            escritorio_a,
            gestor,
            tp_nf=tp_nf,
            emitente=("CNPJ", CNPJ_DE_FORA),
            destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
        )
        papel_esperado = "Destinatário"
    _logar(client, gestor)

    linha = _linhas_de_nota(_html(client.get(_url_lista(empresa))))[0]

    assert linha[5] == papel_esperado
    assert linha[6] == direcao_esperada


# ---------------------------------------------------------------------------
# Lista: filtros, paginação, NFC-e sem destinatário, transferência, IBS/CBS
# ---------------------------------------------------------------------------


def test_filtro_por_papel_separa_as_duas_pontas(client, gestor, emitente, destinatario, tres_notas):
    # Nota 30: a empresa DESTINATÁRIA recebe. Notas 10 e 20: a empresa EMITENTE emite.
    _logar(client, gestor)

    assert _numeros(_html(client.get(_url_lista(destinatario, papel="destinatario")))) == ["30"]
    assert _numeros(_html(client.get(_url_lista(emitente, papel="emitente")))) == ["10", "20"]
    assert _numeros(_html(client.get(_url_lista(emitente, papel="destinatario")))) == []


def test_filtro_por_modelo_separa_nfe_de_nfce(client, gestor, emitente, tres_notas):
    _logar(client, gestor)

    assert _numeros(_html(client.get(_url_lista(emitente, modelo="65")))) == ["20"]
    assert _numeros(_html(client.get(_url_lista(emitente, modelo="55")))) == ["10"]


def test_filtro_de_periodo_usa_a_data_de_emissao_em_dd_mm_aaaa(
    client, gestor, emitente, tres_notas
):
    _logar(client, gestor)

    html = _html(
        client.get(_url_lista(emitente, emissao_de="01/03/2026", emissao_ate="31/03/2026"))
    )

    assert _numeros(html) == ["20"]


def test_filtro_de_situacao_nao_mostra_cancelada_como_valida(
    client, escritorio_a, gestor, emitente, tres_notas
):
    cancelada = _nota(
        escritorio_a,
        gestor,
        numero="40",
        dh_emi="2026-05-01T10:00:00-03:00",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=("CNPJ", CNPJ_DE_FORA),
    )
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=cancelada.chave,
        c_stat="135",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    validas = _numeros(_html(client.get(_url_lista(emitente, situacao="valida"))))
    canceladas = _numeros(_html(client.get(_url_lista(emitente, situacao="cancelada"))))

    assert "40" not in validas
    assert canceladas == ["40"]


@pytest.mark.parametrize(
    ("consulta", "mensagem", "valor_mantido"),
    [
        ({"emissao_de": "31/02/2026"}, "'Emissão de' não é uma data válida.", "31/02/2026"),
        (
            {"emissao_de": "2026-02-01"},
            "'Emissão de' deve ser uma data no formato dd/mm/aaaa.",
            "2026-02-01",
        ),
        (
            {"emissao_de": "01/04/2026", "emissao_ate": "01/03/2026"},
            "'Emissão de' não pode ser posterior a 'Emissão até'.",
            "01/03/2026",
        ),
        ({"papel": "tomador"}, "'Papel' deve ser emitente ou destinatário.", None),
        ({"modelo": "57"}, "'Modelo' deve ser 55 (NF-e) ou 65 (NFC-e).", None),
        ({"situacao": "rascunho"}, "'Situação' deve ser autorizada ou cancelada.", None),
    ],
)
def test_filtro_invalido_responde_400_com_a_mensagem_e_nao_mostra_a_lista(
    client, gestor, emitente, tres_notas, consulta, mensagem, valor_mantido
):
    _logar(client, gestor)

    resposta = client.get(_url_lista(emitente, **consulta))

    assert resposta.status_code == 400
    html = _html(resposta)
    # `escape` porque a mensagem sai com aspas escapadas (&#x27;) pelo template.
    assert escape(mensagem) in html
    assert 'name="emissao_de"' in html  # o formulário continua na tela
    if valor_mantido is not None:
        assert f'value="{valor_mantido}"' in html  # o que foi digitado volta ao campo
    assert TITULO_LISTA not in html


def test_lista_pagina_de_25_e_o_link_da_proxima_mantem_os_filtros(
    client, escritorio_a, gestor, emitente
):
    for numero in range(1, 27):
        _nota(escritorio_a, gestor, numero=str(numero))
    _logar(client, gestor)

    primeira = _html(client.get(_url_lista(emitente, modelo="55")))
    segunda = _html(client.get(_url_lista(emitente, modelo="55", pagina="2")))

    assert len(_linhas_de_nota(primeira)) == 25
    assert len(_linhas_de_nota(segunda)) == 1
    # A querystring sem `pagina` sai escapada (`&amp;`) e a `pagina` vem depois, literal.
    assert f'href="?empresa={emitente.pk}&amp;modelo=55&pagina=2"' in primeira


def test_nfce_sem_destinatario_mostra_contraparte_nao_identificada(
    client, escritorio_a, gestor, emitente, tres_notas
):
    _logar(client, gestor)

    linha = [
        linha
        for linha in _linhas_de_nota(_html(client.get(_url_lista(emitente))))
        if linha[2] == "20"
    ][0]

    assert linha[0] == "NFC-e"
    assert "Não identificada no XML" in linha[4]
    # No detalhe, o bloco do destinatário não aparece: nem nome, nem documento inventados.
    nota = DocumentoNFe.objects.get(escritorio=escritorio_a, numero="20")
    detalhe = _html(client.get(_url_detalhe(emitente, nota)))
    assert "Esta nota não traz destinatário no XML" in detalhe
    assert "Não informado no XML" not in _texto(
        detalhe[detalhe.index("<h2>Destinatário</h2>") : detalhe.index("<h2>Totais</h2>")]
    )


def test_transferencia_entre_estabelecimentos_aparece_marcada_na_lista(
    client, escritorio_a, gestor, emitente
):
    # Matriz e filial com o MESMO CNPJ de empresa do escritório: um vínculo, marcado.
    _nota(
        escritorio_a,
        gestor,
        numero="50",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    linha = _linhas_de_nota(_html(client.get(_url_lista(emitente))))[0]

    assert linha[10] == "Sim"


def test_ibscbs_aparece_como_sim_e_nao_na_lista(client, escritorio_a, gestor, emitente):
    _nota(
        escritorio_a,
        gestor,
        numero="60",
        ibscbs_total=True,
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=("CNPJ", CNPJ_DE_FORA),
    )
    _nota(
        escritorio_a,
        gestor,
        numero="61",
        emitente=("CNPJ", CNPJ_EMITENTE_A),
        destinatario=("CNPJ", CNPJ_DE_FORA),
    )
    _logar(client, gestor)

    linhas = {linha[2]: linha for linha in _linhas_de_nota(_html(client.get(_url_lista(emitente))))}

    assert linhas["60"][9] == "Sim"
    assert linhas["61"][9] == "Não"


# ---------------------------------------------------------------------------
# Detalhe: identificação, totais, protocolo, eventos em ordem e aviso de cancelamento
# ---------------------------------------------------------------------------


def test_detalhe_de_nota_valida_mostra_eventos_em_ordem_com_nome_oficial_e_efeito(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(escritorio_a, gestor, numero="70")
    _evento(
        escritorio_a,
        gestor,
        tp_evento="210200",
        chave=nota.chave,
        c_stat="135",
        dh_evento="2026-01-16T09:00:00-03:00",
        autor=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110110",
        chave=nota.chave,
        c_stat="135",
        dh_evento="2026-01-17T09:00:00-03:00",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _evento(
        escritorio_a,
        gestor,
        tp_evento="210220",
        chave=nota.chave,
        c_stat=None,
        dh_evento="2026-01-18T09:00:00-03:00",
        autor=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    assert "NF-e cancelada — não tem efeito fiscal." not in html
    cabecalho, *corpo = _linhas_da_tabela(html, TITULO_EVENTOS_DA_NOTA)
    assert cabecalho[:3] == ["Código do evento", "Nome do evento", "Sequência"]
    assert corpo == [
        [
            "210200",
            "Confirmação da operação",
            "1",
            "16/01/2026 09:00",
            "135",
            "Sem efeito sobre a situação",
        ],
        [
            "110110",
            "Carta de Correção",
            "1",
            "17/01/2026 09:00",
            "135",
            "Sem efeito sobre a situação",
        ],
        [
            "210220",
            "Desconhecimento da operação",
            "1",
            "18/01/2026 09:00",
            "Sem retorno",
            "Sem efeito sobre a situação",
        ],
    ]


def test_detalhe_de_nota_cancelada_tem_o_aviso_no_topo_antes_da_identificacao(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(escritorio_a, gestor, numero="71")
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=nota.chave,
        c_stat="135",
        dh_evento="2026-01-20T09:00:00-03:00",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    aviso = html.index("NF-e cancelada — não tem efeito fiscal.")
    identificacao = html.index("<h2>Identificação</h2>")
    assert aviso < identificacao
    assert "Cancela a nota" in html
    assert "Cancelada" in _texto(html[html.index("<h1>") : html.index("</h1>")])


def test_detalhe_mostra_identificacao_com_texto_oficial_e_chave_em_grupos_de_4(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(escritorio_a, gestor, numero="72", fin_nfe="2", tp_nf="0", id_dest="2")
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    assert _grupos(nota.chave) in html
    assert "0 (entrada)" in html  # tpNF com o sentido do ponto de vista do emitente
    assert "<dd>Complementar</dd>" in html  # finNFe 2
    assert "<dd>Entrada própria</dd>" in html  # emitente com tpNF 0
    assert "<dt>Local de destino (idDest)</dt>" in html


def test_detalhe_mostra_totais_pt_br_e_campo_ausente_com_travessao(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(
        escritorio_a,
        gestor,
        numero="73",
        totais={"vNF": "1234.56", "vProd": "0.50", "vFrete": None},
    )
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    assert '<dd class="valor-monetario">1.234,56</dd>' in html
    assert '<dd class="valor-monetario">0,50</dd>' in html
    assert '<dd class="valor-monetario">—</dd>' in html  # vFrete ausente: travessão, nunca zero
    assert "Frete (vFrete)" in html


def test_detalhe_mostra_protocolo_itens_e_aviso_do_ibscbs(client, escritorio_a, gestor, emitente):
    nota = _nota(escritorio_a, gestor, numero="74", itens=3, ibscbs_item=True)
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    assert "Quantidade de itens: 3." in html
    assert "IBS/CBS: grupo presente, não interpretado nesta etapa (PE-39)." in html
    assert "135260000000001" in html  # nProt do protocolo sintético
    assert "15/01/2026 10:01" in html  # dhRecbto em -03:00 mostrado em horário de Brasília


# ---------------------------------------------------------------------------
# Eventos sem nota (órfãos): por escritório, com filtro opcional de empresa (autor)
# ---------------------------------------------------------------------------


def test_orfaos_mostra_chave_tipo_e_data_e_o_filtro_usa_o_autor(
    client, escritorio_a, gestor, emitente, destinatario
):
    chave_a = chave_nfe(emitente=CNPJ_DE_FORA, numero="99")
    chave_b = chave_nfe(emitente=CNPJ_DE_FORA, numero="98")
    _evento(
        escritorio_a,
        gestor,
        tp_evento="210210",
        chave=chave_a,
        c_stat="135",
        dh_evento="2026-02-03T09:00:00-03:00",
        autor=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=chave_b,
        c_stat="135",
        dh_evento="2026-02-04T09:00:00-03:00",
        autor=("CNPJ", CNPJ_DE_FORA),
    )
    _logar(client, gestor)

    sem_filtro = _html(client.get(_url_orfaos()))
    so_destinatario = _html(client.get(_url_orfaos(empresa=destinatario.pk)))

    linhas = _linhas_da_tabela(sem_filtro, TITULO_ORFAOS)[1:]
    assert [linha[1] for linha in linhas] == ["110111", "210210"]  # o mais recente primeiro
    assert linhas[0][0] == _grupos(chave_b)
    assert linhas[0][7] == "Não identificada como empresa do escritório"
    assert linhas[1][7] == "Destinataria Sintetica Ltda"
    # O filtro pelo autor deixa de fora o evento de quem não é empresa do escritório.
    assert [linha[1] for linha in _linhas_da_tabela(so_destinatario, TITULO_ORFAOS)[1:]] == [
        "210210"
    ]


def test_orfaos_nao_mostra_evento_de_outro_escritorio(
    client, escritorio_a, gestor, escritorio_b, gestor_b
):
    _evento(
        escritorio_b,
        gestor_b,
        tp_evento="110111",
        chave=chave_nfe(emitente=CNPJ_DE_FORA, numero="77"),
        c_stat="135",
        autor=("CNPJ", CNPJ_DE_FORA),
    )
    _logar(client, gestor)

    html = _html(client.get(_url_orfaos()))

    assert "Nenhum evento de NF-e aguardando a nota." in html
    assert _linhas_da_tabela(html, TITULO_ORFAOS) == []


# ---------------------------------------------------------------------------
# Isolamento, IDOR, escrita e permissões
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_ou_malformada_responde_404_em_todas_as_telas(
    client, escritorio_a, gestor, escritorio_b, gestor_b
):
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj=CNPJ_EMITENTE_A
    )
    nota_b = _nota(escritorio_b, gestor_b, numero="80", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, gestor)

    assert client.get(_url_lista(empresa_b)).status_code == 404
    assert client.get(_url_orfaos(empresa=empresa_b.pk)).status_code == 404
    assert client.get(_url_detalhe(empresa_b, nota_b)).status_code == 404
    assert client.get(_url_lista() + "?empresa=abc").status_code == 404
    assert client.get(_url_orfaos(empresa="abc")).status_code == 404


def test_nota_de_outra_empresa_do_mesmo_escritorio_nao_aparece_e_responde_404(
    client, escritorio_a, gestor, emitente, destinatario
):
    nota_da_destinataria = _nota(
        escritorio_a,
        gestor,
        numero="81",
        emitente=("CNPJ", CNPJ_DE_FORA),
        destinatario=("CNPJ", CNPJ_DESTINATARIO_A),
    )
    _logar(client, gestor)

    assert "81" not in _numeros(_html(client.get(_url_lista(emitente))))
    assert client.get(_url_detalhe(emitente, nota_da_destinataria)).status_code == 404
    assert client.get(_url_detalhe(destinatario, nota_da_destinataria)).status_code == 200


def test_id_de_nota_de_outro_escritorio_responde_404_idor(
    client, escritorio_a, gestor, emitente, escritorio_b, gestor_b
):
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj=CNPJ_EMITENTE_A
    )
    nota_b = _nota(escritorio_b, gestor_b, numero="82", emitente=("CNPJ", CNPJ_EMITENTE_A))
    assert nota_b is not None
    _logar(client, gestor)

    assert client.get(_url_detalhe(emitente, nota_b)).status_code == 404
    assert "82" not in _numeros(_html(client.get(_url_lista(emitente))))


def test_mesmo_cnpj_em_dois_escritorios_fica_isolado_na_lista(
    client, escritorio_a, gestor, emitente, escritorio_b, gestor_b
):
    Empresa.objects.create(
        escritorio=escritorio_b, razao_social="Empresa B Ltda", cnpj=CNPJ_EMITENTE_A
    )
    _nota(escritorio_a, gestor, numero="83", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _nota(escritorio_b, gestor_b, numero="84", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, gestor)

    assert _numeros(_html(client.get(_url_lista(emitente)))) == ["83"]


@pytest.mark.parametrize("papel", [Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO, Papel.PARALEGAL])
def test_papeis_que_consultam_documentos_leem_as_telas_novas(client, escritorio_a, emitente, papel):
    usuario = _usuario(escritorio_a, papel, f"leitor-nfe-{papel}")
    nota = _nota(escritorio_a, usuario, numero="90", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, usuario)

    assert client.get(_url_lista(emitente)).status_code == 200
    assert client.get(_url_detalhe(emitente, nota)).status_code == 200
    assert client.get(_url_orfaos()).status_code == 200


def test_cliente_recebe_403_nas_telas_novas(
    client, escritorio_a, gestor, emitente, usuario_cliente_a
):
    nota = _nota(escritorio_a, gestor, numero="91", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, usuario_cliente_a)

    for resposta in (
        client.get(_url_lista(emitente)),
        client.get(_url_detalhe(emitente, nota)),
        client.get(_url_orfaos()),
    ):
        assert resposta.status_code == 403
        assert "erros/sem_permissao.html" in [t.name for t in resposta.templates]


def test_anonimo_e_redirecionado_para_o_login_nas_telas_novas(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(escritorio_a, gestor, numero="92", emitente=("CNPJ", CNPJ_EMITENTE_A))

    for url in (_url_lista(emitente), _url_detalhe(emitente, nota), _url_orfaos()):
        resposta = client.get(url)
        assert resposta.status_code == 302, url
        assert "login" in resposta["Location"], url


def test_usuario_sem_vinculo_nao_ve_a_lista(client, emitente, usuario_sem_vinculo):
    _logar(client, usuario_sem_vinculo)

    resposta = client.get(_url_lista(emitente))

    assert "empresas/sem_escritorio.html" in [t.name for t in resposta.templates]
    assert TITULO_LISTA not in _html(resposta)


def test_as_telas_novas_nao_aceitam_escrita(client, escritorio_a, gestor, emitente):
    nota = _nota(escritorio_a, gestor, numero="93", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, gestor)

    assert client.post(_url_lista(emitente)).status_code == 405
    assert client.post(_url_detalhe(emitente, nota)).status_code == 405
    assert client.post(_url_orfaos()).status_code == 405


# ---------------------------------------------------------------------------
# Acessibilidade, menu, trilha e home
# ---------------------------------------------------------------------------


def _ids_referenciados_que_nao_existem(html):
    existentes = set(re.findall(r'\bid="([^"]+)"', html))
    referencias = set()
    for bloco in re.findall(r'aria-describedby="([^"]+)"', html):
        referencias.update(bloco.split())
    referencias.update(re.findall(r'\bfor="([^"]+)"', html))
    return referencias - existentes


def test_telas_novas_sao_acessiveis_com_legenda_e_escopo_nos_cabecalhos(
    client, escritorio_a, gestor, emitente
):
    nota = _nota(escritorio_a, gestor, numero="94", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _nota(escritorio_a, gestor, numero="95", emitente=("CNPJ", CNPJ_EMITENTE_A), destinatario=None)
    _evento(
        escritorio_a,
        gestor,
        tp_evento="110111",
        chave=nota.chave,
        c_stat="135",
        autor=("CNPJ", CNPJ_EMITENTE_A),
    )
    _logar(client, gestor)

    paginas = [
        _url_lista(),
        _url_lista(emitente),
        _url_lista(emitente, emissao_de="31/02/2026"),
        _url_detalhe(emitente, nota),
        _url_orfaos(),
        _url_orfaos(empresa=emitente.pk),
    ]
    for url in paginas:
        resposta = client.get(url)
        assert resposta.status_code in (200, 400), url
        html = _html(resposta)
        assert_moldura_acessivel(html)
        assert not _ids_referenciados_que_nao_existem(html), url
        assert html.count("<table") == html.count("<caption"), url
        assert not re.findall(r"<th\b(?![^>]*\bscope=)[^>]*>", html), url


def test_menu_do_fiscal_leva_as_telas_novas_e_marca_a_pagina_atual(client, gestor, emitente):
    _logar(client, gestor)

    lista = _html(client.get(_url_lista(emitente)))
    orfaos = _html(client.get(_url_orfaos()))

    # A página atual é texto, nunca link para si mesma (direção de arte §8.1).
    assert f'<a href="{reverse("fiscal_web:nfe_recebidas")}">NF-e recebidas</a>' not in lista
    assert '<span class="item-atual" aria-current="page">NF-e recebidas</span>' in lista
    assert f'href="{reverse("fiscal_web:nfe_eventos_orfaos")}"' in lista
    assert '<span class="item-atual" aria-current="page">Eventos de NF-e sem nota</span>' in orfaos


def test_home_do_fiscal_tem_o_atalho_para_a_lista_de_nfe_da_empresa_unica(client, gestor, emitente):
    _logar(client, gestor)

    html = _html(client.get(reverse("module_home:home", args=["fiscal"])))

    assert f'href="{reverse("fiscal_web:nfe_recebidas")}?empresa={emitente.pk}"' in html


def test_detalhe_tem_trilha_com_a_lista_e_botao_de_volta(client, escritorio_a, gestor, emitente):
    nota = _nota(escritorio_a, gestor, numero="96", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, gestor)

    html = _html(client.get(_url_detalhe(emitente, nota)))

    assert "Voltar para NF-e recebidas" in html
    assert f'href="{reverse("fiscal_web:nfe_recebidas")}?empresa={emitente.pk}"' in html


def test_lista_sem_empresa_pede_a_escolha_e_nao_lista_nada(client, escritorio_a, gestor, emitente):
    _nota(escritorio_a, gestor, numero="97", emitente=("CNPJ", CNPJ_EMITENTE_A))
    _logar(client, gestor)

    html = _html(client.get(_url_lista()))

    assert "Escolha uma empresa para ver as NF-e recebidas." in html
    assert _numeros(html) == []
