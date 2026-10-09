"""DL-080 (frente A), API de leitura da NF-e: direção, filtros, situação, permissões e isolamento.

Critério 5 (direção pelo papel com `tpNF`), critério 9 (isolamento e permissões nas rotas novas) e
IDOR. Só `GET`: a API não grava nada. Os XML são sintéticos (`xml_nfe_dl080`).
"""

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.empresas.models import Empresa
from apps.fiscal import services
from apps.fiscal.api_nfe import DESCRICAO_EVENTO_NFE, direcao_para_o_cliente
from apps.fiscal.models import PapelNFe
from apps.fiscal.services import situacao_da_nfe
from apps.fiscal.tests.xml_nfe_dl080 import (
    CNPJ_DE_FORA,
    CNPJ_DESTINATARIO_A,
    CNPJ_EMITENTE_A,
    CNPJ_SEM_CADASTRO,
    chave_nfe,
    proc_evento_xml,
    xml_nfe,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db


def _enviar(escritorio, usuario, conteudo):
    return services.receber_envio(
        escritorio=escritorio, usuario=usuario, arquivo=conteudo, nome_arquivo="nota.xml"
    )


def _usuario(escritorio, papel, nome):
    usuario = get_user_model().objects.create_user(
        username=nome,
        email=f"{nome}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


@pytest.fixture
def usuario_paralegal_a(escritorio_a):
    return _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-nfe-a")


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-nfe-b")


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


def _url_lista(empresa, **consulta):
    url = reverse("fiscal_api:nfe_notas", args=[empresa.pk])
    if not consulta:
        return url
    partes = "&".join(f"{chave}={valor}" for chave, valor in consulta.items())
    return f"{url}?{partes}"


def _url_detalhe(empresa, documento_id):
    return reverse("fiscal_api:nfe_detalhe", args=[empresa.pk, documento_id])


def _json(resposta):
    return json.loads(resposta.content)


# --- direção para o cliente (critério 5, o uso do papel com tpNF) -------------------


@pytest.mark.parametrize(
    ("papel", "tp_nf", "esperado"),
    [
        (PapelNFe.EMITENTE, "1", "saida"),
        (PapelNFe.EMITENTE, "0", "entrada_propria"),
        (PapelNFe.DESTINATARIO, "1", "entrada"),
        (PapelNFe.DESTINATARIO, "0", "a_conferir"),
    ],
)
def test_direcao_combina_papel_com_tpnf(papel, tp_nf, esperado):
    assert direcao_para_o_cliente(papel, tp_nf) == esperado


def test_direcao_com_papel_desconhecido_e_recusada():
    with pytest.raises(ValueError):
        direcao_para_o_cliente("tomador", "1")


@pytest.mark.parametrize(
    ("papel_da_empresa", "tp_nf", "esperado"),
    [
        ("emitente", "1", "saida"),
        ("emitente", "0", "entrada_propria"),
        ("destinatario", "1", "entrada"),
        ("destinatario", "0", "a_conferir"),
    ],
)
def test_api_devolve_a_direcao_pelo_papel_da_empresa(
    client,
    escritorio_a,
    usuario_gestor_a,
    emitente,
    destinatario,
    papel_da_empresa,
    tp_nf,
    esperado,
):
    # A empresa é emitente ou destinatária, conforme o papel. Quem é a outra parte não importa.
    if papel_da_empresa == "emitente":
        conteudo = xml_nfe(
            tp_nf=tp_nf, emitente=("CNPJ", CNPJ_EMITENTE_A), destinatario=("CNPJ", CNPJ_DE_FORA)
        )
        empresa = emitente
    else:
        conteudo = xml_nfe(
            tp_nf=tp_nf, emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CNPJ", CNPJ_DESTINATARIO_A)
        )
        empresa = destinatario
    _enviar(escritorio_a, usuario_gestor_a, conteudo)
    client.force_login(usuario_gestor_a)
    notas = _json(client.get(_url_lista(empresa)))["notas"]
    assert len(notas) == 1
    assert notas[0]["direcao"] == esperado


def test_tpnf_nao_inverte_a_direcao_da_destinataria(
    client, escritorio_a, usuario_gestor_a, destinatario
):
    # Nota de SAÍDA (tpNF 1) emitida por outra empresa, para a empresa: é entrada, e não saída.
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(
            tp_nf="1", emitente=("CNPJ", CNPJ_DE_FORA), destinatario=("CNPJ", CNPJ_DESTINATARIO_A)
        ),
    )
    client.force_login(usuario_gestor_a)
    nota = _json(client.get(_url_lista(destinatario)))["notas"][0]
    assert nota["papel"] == "destinatario"
    assert nota["direcao"] == "entrada"


# --- lista: campos, filtros e situação -----------------------------------------------


def test_lista_traz_os_campos_do_critico_e_o_valor_como_texto(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(totais={"vNF": "1234.50"}))
    client.force_login(usuario_gestor_a)
    nota = _json(client.get(_url_lista(emitente)))["notas"][0]
    assert nota["papel"] == "emitente"
    assert nota["situacao"] == "valida"
    assert nota["modelo"] == "55"
    assert nota["modelo_nome"] == "NF-e"
    assert nota["numero"] == "1"
    assert nota["serie"] == "1"
    assert nota["v_nf"] == "1234.50"
    assert isinstance(nota["v_nf"], str)
    assert nota["tem_ibscbs"] is False
    assert nota["transferencia_entre_estabelecimentos"] is False


def test_nota_com_ibscbs_aparece_com_presenca_marcada(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(ibscbs_total=True))
    client.force_login(usuario_gestor_a)
    assert _json(client.get(_url_lista(emitente)))["notas"][0]["tem_ibscbs"] is True


def test_filtro_por_papel_separa_as_duas_pontas(
    client, escritorio_a, usuario_gestor_a, emitente, destinatario
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())  # emitente=A, destinatário=B
    client.force_login(usuario_gestor_a)
    so_emitente = _json(client.get(_url_lista(emitente, papel="emitente")))["notas"]
    so_destinatario = _json(client.get(_url_lista(destinatario, papel="destinatario")))["notas"]
    assert [n["papel"] for n in so_emitente] == ["emitente"]
    assert [n["papel"] for n in so_destinatario] == ["destinatario"]
    assert _json(client.get(_url_lista(emitente, papel="destinatario")))["notas"] == []


def test_filtro_por_modelo_separa_nfe_de_nfce(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(destinatario=None))
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(modelo="65", destinatario=None))
    client.force_login(usuario_gestor_a)
    nfce = _json(client.get(_url_lista(emitente, modelo="65")))["notas"]
    assert [n["modelo"] for n in nfce] == ["65"]
    assert nfce[0]["modelo_nome"] == "NFC-e"


def test_filtro_de_periodo_usa_a_data_de_emissao(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(dh_emi="2026-01-15T10:00:00-03:00", destinatario=None),
    )
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        xml_nfe(dh_emi="2026-03-20T10:00:00-03:00", numero="2", destinatario=None),
    )
    client.force_login(usuario_gestor_a)
    notas = _json(client.get(_url_lista(emitente, inicio="2026-03-01", fim="2026-03-31")))["notas"]
    assert [n["numero"] for n in notas] == ["2"]


def test_filtro_de_situacao_separa_cancelada_de_valida(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(destinatario=None))
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(numero="2", destinatario=None))
    _enviar(
        escritorio_a,
        usuario_gestor_a,
        proc_evento_xml(chave=chave_nfe(emitente=CNPJ_EMITENTE_A, numero="2"), c_stat="135"),
    )
    client.force_login(usuario_gestor_a)
    canceladas = _json(client.get(_url_lista(emitente, situacao="cancelada")))["notas"]
    validas = _json(client.get(_url_lista(emitente, situacao="valida")))["notas"]
    assert [n["numero"] for n in canceladas] == ["2"]
    assert [n["numero"] for n in validas] == ["1"]


@pytest.mark.parametrize(
    "consulta",
    [
        {"papel": "tomador"},
        {"modelo": "99"},
        {"situacao": "suspensa"},
        {"inicio": "15/01/2026"},
        {"inicio": "2026-03-31", "fim": "2026-03-01"},
    ],
)
def test_filtro_invalido_responde_400_com_mensagem(
    client, escritorio_a, usuario_gestor_a, emitente, consulta
):
    client.force_login(usuario_gestor_a)
    resposta = client.get(_url_lista(emitente, **consulta))
    assert resposta.status_code == 400
    assert "detail" in _json(resposta)


# --- detalhe e eventos ----------------------------------------------------------------


def test_detalhe_traz_totais_protocolo_e_eventos_com_efeito(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(totais={"vNF": "100.00", "vICMS": None}))
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(c_stat="135"))
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(tp_evento="110110", c_stat="135"))
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    detalhe = _json(client.get(_url_detalhe(emitente, documento_id)))
    assert detalhe["situacao"] == "cancelada"
    assert detalhe["totais"]["v_nf"] == "100.00"
    assert detalhe["totais"]["v_icms"] is None, "campo ausente aparece como nulo, nunca zero"
    assert detalhe["protocolo"]["c_stat"] == "100"
    assert detalhe["protocolo"]["n_prot"] == "135260000000001"
    eventos = {e["tp_evento"]: e for e in detalhe["eventos"]}
    assert eventos["110111"]["efeito"] == "cancela"
    assert eventos["110111"]["descricao"] == "Cancelamento"
    assert eventos["110110"]["efeito"] == "sem efeito"
    # A5/A9 (rodada 1): nome oficial com C e C maiúsculos, vindo de DESCRICAO_EVENTO_NFE.
    assert eventos["110110"]["descricao"] == "Carta de Correção"


def test_evento_sem_retorno_aparece_no_detalhe_sem_efeito(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(c_stat=None))
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    detalhe = _json(client.get(_url_detalhe(emitente, documento_id)))
    assert detalhe["situacao"] == "valida"
    evento = detalhe["eventos"][0]
    assert evento["c_stat"] is None
    assert evento["registrado"] is False
    assert evento["efeito"] == "sem efeito"


def test_evento_de_tipo_nao_catalogado_aparece_sem_nome_inventado(
    client, escritorio_a, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(tp_evento="999999", c_stat="135"))
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    evento = _json(client.get(_url_detalhe(emitente, documento_id)))["eventos"][0]
    assert evento["descricao"] == "evento não catalogado nesta recepção"
    assert "999999" not in DESCRICAO_EVENTO_NFE


def test_detalhe_de_nfce_sem_destinatario(client, escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(modelo="65", destinatario=None))
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    detalhe = _json(client.get(_url_detalhe(emitente, documento_id)))
    assert detalhe["modelo"] == "65"
    assert detalhe["destinatario"] is None


def test_situacao_da_nfe_vale_nas_duas_ordens(escritorio_a, usuario_gestor_a, emitente):
    _enviar(escritorio_a, usuario_gestor_a, proc_evento_xml(c_stat="135"))
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    from apps.fiscal.models import DocumentoNFe

    assert situacao_da_nfe(DocumentoNFe.objects.get()) == "cancelada"


# --- permissões (critério 9) ----------------------------------------------------------


def test_gestor_e_paralegal_leem_cliente_nao_le(
    client, escritorio_a, usuario_gestor_a, usuario_paralegal_a, usuario_cliente_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]

    client.force_login(usuario_paralegal_a)
    assert client.get(_url_lista(emitente)).status_code == 200
    assert client.get(_url_detalhe(emitente, documento_id)).status_code == 200

    client.force_login(usuario_cliente_a)
    assert client.get(_url_lista(emitente)).status_code == 403
    assert client.get(_url_detalhe(emitente, documento_id)).status_code == 403


def test_usuario_sem_vinculo_no_escritorio_nao_le(client, usuario_sem_vinculo, emitente):
    client.force_login(usuario_sem_vinculo)
    assert client.get(_url_lista(emitente)).status_code == 403


def test_anonimo_nao_le_a_api(client, emitente):
    resposta = client.get(_url_lista(emitente))
    assert resposta.status_code in (401, 403)
    assert b"notas" not in resposta.content


def test_api_nao_aceita_escrita(client, escritorio_a, usuario_gestor_a, emitente):
    client.force_login(usuario_gestor_a)
    assert (
        client.post(_url_lista(emitente), data="{}", content_type="application/json").status_code
        == 405
    )
    assert client.delete(_url_lista(emitente)).status_code == 405


# --- isolamento (critério 9, IDOR) ----------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404_na_lista_e_no_detalhe(
    client, escritorio_a, escritorio_b, usuario_gestor_a, emitente
):
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe())
    empresa_b = Empresa.objects.create(
        escritorio=escritorio_b, razao_social="De B", cnpj=CNPJ_DE_FORA
    )
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    assert client.get(_url_lista(empresa_b)).status_code == 404
    assert client.get(_url_detalhe(empresa_b, documento_id)).status_code == 404


def test_nota_de_outra_empresa_do_mesmo_escritorio_responde_404_idor(
    client, escritorio_a, usuario_gestor_a, emitente
):
    # `destinatario` não tem vínculo com esta nota: não pode ver o detalhe pela URL dela.
    empresa_sem_vinculo = Empresa.objects.create(
        escritorio=escritorio_a, razao_social="Sem Relacao", cnpj=CNPJ_SEM_CADASTRO
    )
    _enviar(escritorio_a, usuario_gestor_a, xml_nfe(destinatario=None))
    client.force_login(usuario_gestor_a)
    documento_id = _json(client.get(_url_lista(emitente)))["notas"][0]["documento_id"]
    assert client.get(_url_detalhe(empresa_sem_vinculo, documento_id)).status_code == 404
    assert client.get(_url_detalhe(emitente, documento_id)).status_code == 200


def test_id_de_nota_de_outro_escritorio_responde_404(
    client, escritorio_a, escritorio_b, usuario_gestor_a, usuario_gestor_b, emitente
):
    # A mesma chave existe no escritório B. O id da nota do B, pedido com a empresa de A, é 404.
    Empresa.objects.create(escritorio=escritorio_b, razao_social="Emitente B", cnpj=CNPJ_EMITENTE_A)
    _enviar(escritorio_b, usuario_gestor_b, xml_nfe(destinatario=None))
    from apps.fiscal.models import DocumentoNFe

    id_do_b = DocumentoNFe.objects.get(escritorio=escritorio_b).pk
    client.force_login(usuario_gestor_a)
    assert client.get(_url_detalhe(emitente, id_do_b)).status_code == 404


def test_vinculo_cruzado_entre_escritorios_nao_aparece_na_lista_nem_no_detalhe(
    client, escritorio_a, escritorio_b, usuario_gestor_a, usuario_gestor_b, emitente
):
    # Defesa em profundidade. A aplicação nunca cria esse vínculo, e o banco não o impede.
    # A nota é do escritório B, e o vínculo aponta para uma empresa do A. A API filtra nos DOIS
    # lados (empresa e nota), então a nota não aparece para o A, nem na lista nem no detalhe.
    Empresa.objects.create(escritorio=escritorio_b, razao_social="Dono no B", cnpj=CNPJ_EMITENTE_A)
    _enviar(escritorio_b, usuario_gestor_b, xml_nfe(destinatario=None))
    from apps.fiscal.models import DocumentoNFe, VinculoNFeEmpresa

    documento_b = DocumentoNFe.objects.get(escritorio=escritorio_b)
    VinculoNFeEmpresa.objects.create(
        documento=documento_b, empresa=emitente, papel=PapelNFe.EMITENTE
    )
    client.force_login(usuario_gestor_a)
    assert _json(client.get(_url_lista(emitente)))["notas"] == []
    assert client.get(_url_detalhe(emitente, documento_b.pk)).status_code == 404
