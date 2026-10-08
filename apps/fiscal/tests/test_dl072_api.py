"""DL-072 (frente A) — API da escrituração das NFS-e prestadas.

Critérios do plano cobertos aqui: 9 (isolamento entre escritórios e entre
empresas: 404 nas duas direções), 10 (CLIENTE não acessa; papel sem permissão
de escriturar recebe 403), e os fluxos de efetivar, estornar e conferência pela
API, com a mesma regra do domínio.

Autorização é verificada no servidor. Os testes usam o cliente HTTP real, com
sessão e escritório ativo resolvidos pelo middleware, e não chamam as views
diretamente.
"""

import json
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from apps.auditoria.models import RegistroAuditoria
from apps.fiscal import escrituracao as servico
from apps.fiscal import services
from apps.fiscal.models import (
    DocumentoFiscal,
    EscrituracaoFiscal,
    NaturezaOperacao,
    PapelDocumento,
    VinculoDocumentoEmpresa,
)
from apps.fiscal.tests.xml_sinteticos import (
    chave_nfse_de,
    identificador_nfse,
    xml_evento,
    xml_nfse,
)
from apps.tenancy.models import Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

NATUREZA = NaturezaOperacao.PRESTADO_ISS_DEVIDO_PRESTADOR
OUTRA = NaturezaOperacao.PRESTADO_ISS_RETIDO


def _usuario(escritorio, papel, username):
    usuario = get_user_model().objects.create_user(
        username=username,
        email=f"{username}@escritorio-fiscal-teste.com.br",
        password="senha-forte-123",
    )
    VinculoUsuarioEscritorio.objects.create(usuario=usuario, escritorio=escritorio, papel=papel)
    return usuario


def _logar(client, usuario):
    client.force_login(usuario)
    return client


@pytest.fixture
def usuario_gestor_b(escritorio_b):
    # Gestor do OUTRO escritório: o isolamento precisa ser provado com um
    # usuário real, não com um id trocado na URL.
    return _usuario(escritorio_b, Papel.GESTOR, "gestor-b-escrituracao")


def _nota(escritorio, usuario, sufixo=1, **kwargs):
    identificador = identificador_nfse(sufixo)
    services.receber_envio(
        escritorio=escritorio,
        usuario=usuario,
        arquivo=xml_nfse(identificador=identificador, numero=str(sufixo), **kwargs),
        nome_arquivo="nota.xml",
    )
    return DocumentoFiscal.objects.get(escritorio=escritorio, identificador=identificador)


def _vinculo(documento, empresa, papel=PapelDocumento.PRESTADOR):
    return VinculoDocumentoEmpresa.objects.get(documento=documento, empresa=empresa, papel=papel)


def _url_notas(empresa, ano=2024, mes=1):
    return f"/fiscal/api/empresas/{empresa.pk}/notas-prestadas/?ano={ano}&mes={mes}"


def _url_efetivar(empresa, vinculo):
    return f"/fiscal/api/empresas/{empresa.pk}/notas-prestadas/{vinculo.pk}/efetivar/"


def _url_estornar(empresa, escrituracao):
    return f"/fiscal/api/empresas/{empresa.pk}/escrituracoes/{escrituracao.pk}/estornar/"


def _url_conferencia(empresa, ano=2024, mes=1):
    return f"/fiscal/api/empresas/{empresa.pk}/conferencia/?ano={ano}&mes={mes}"


def _post(client, url, corpo):
    return client.post(url, data=json.dumps(corpo), content_type="application/json")


# ---------------------------------------------------------------------------
# Critério 10 — quem pode e quem não pode
# ---------------------------------------------------------------------------


def test_cliente_nao_lista_nem_escritura_e_nada_e_gravado(
    client, escritorio_a, empresa_a, usuario_gestor_a, usuario_cliente_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_cliente_a)

    assert client.get(_url_notas(empresa_a)).status_code == 403
    assert client.get(_url_conferencia(empresa_a)).status_code == 403
    resposta = _post(
        client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
    )

    assert resposta.status_code == 403
    assert EscrituracaoFiscal.objects.count() == 0
    assert RegistroAuditoria.objects.filter(acao__startswith="escrituracao_fiscal.").count() == 0


def test_paralegal_consulta_mas_nao_escritura_nem_estorna(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    paralegal = _usuario(escritorio_a, Papel.PARALEGAL, "paralegal-escrituracao")
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a
    )
    _logar(client, paralegal)

    assert client.get(_url_notas(empresa_a)).status_code == 200

    resposta = _post(
        client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": OUTRA}
    )
    assert resposta.status_code == 403
    resposta = _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": "x"})
    assert resposta.status_code == 403
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == "efetivada"


@pytest.mark.parametrize(
    "papel", [Papel.ADMINISTRADOR, Papel.GESTOR, Papel.ANALISTA, Papel.FINANCEIRO]
)
def test_papeis_que_escrituram_efetivam_e_estornam(
    client, escritorio_a, empresa_a, usuario_gestor_a, papel
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    quem = _usuario(escritorio_a, papel, f"escriturador-{papel}")
    _logar(client, quem)

    resposta = _post(
        client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
    )
    assert resposta.status_code == 201, resposta.content

    escrituracao = EscrituracaoFiscal.objects.get()
    resposta = _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": "conferência"})
    assert resposta.status_code == 200, resposta.content
    assert resposta.json()["estado"] == "estornada"


def test_usuario_sem_vinculo_no_escritorio_nao_acessa(
    client, escritorio_a, empresa_a, usuario_sem_vinculo
):
    _logar(client, usuario_sem_vinculo)

    assert client.get(_url_notas(empresa_a)).status_code == 403


# ---------------------------------------------------------------------------
# Critério 9 — isolamento entre escritórios e entre empresas (404 nas duas vias)
# ---------------------------------------------------------------------------


def test_empresa_de_outro_escritorio_responde_404_em_todas_as_rotas(
    client, escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    assert client.get(_url_notas(empresa_b)).status_code == 404
    assert client.get(_url_conferencia(empresa_b)).status_code == 404
    assert (
        _post(
            client, _url_efetivar(empresa_b, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
        ).status_code
        == 404
    )
    assert EscrituracaoFiscal.objects.count() == 0


def test_escritorio_b_nao_enxerga_nem_estorna_escrituracao_de_a(
    client, escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a, usuario_gestor_b
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_b)

    # Pelo caminho da empresa dele, a escrituração de A não existe (404).
    assert _post(client, _url_estornar(empresa_b, escrituracao), {"motivo": "x"}).status_code == 404
    assert _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": "x"}).status_code == 404
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == "efetivada"


def test_vinculo_de_outra_empresa_do_mesmo_escritorio_responde_404(
    client, escritorio_a, empresa_a, empresa_a2, usuario_gestor_a
):
    # Nota em que empresa_a é prestadora e empresa_a2 é tomadora. Pedir o
    # vínculo de empresa_a pelo caminho de empresa_a2 não pode funcionar.
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client, _url_efetivar(empresa_a2, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
    )

    assert resposta.status_code == 404
    assert EscrituracaoFiscal.objects.count() == 0


def test_lista_nao_mostra_notas_de_outro_escritorio(
    client, escritorio_a, escritorio_b, empresa_a, empresa_b, usuario_gestor_a, usuario_gestor_b
):
    _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_b)

    resposta = client.get(_url_notas(empresa_b))

    assert resposta.status_code == 200
    assert resposta.json()["notas"] == []


# ---------------------------------------------------------------------------
# Fluxo pela API
# ---------------------------------------------------------------------------


def test_lista_mostra_a_escriturar_com_natureza_sugerida_e_valores_exatos(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    _nota(escritorio_a, usuario_gestor_a, tp_ret_issqn="2", v_serv="1234.56", v_liq="1000.10")
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_notas(empresa_a))

    assert resposta.status_code == 200
    (nota,) = resposta.json()["notas"]
    assert nota["situacao"] == "a_escriturar"
    assert nota["natureza_sugerida"] == NaturezaOperacao.PRESTADO_ISS_RETIDO
    assert nota["valor_servico"] == "1234.56"
    assert nota["valor_liquido"] == "1000.10"
    assert nota["competencia_difere_da_emissao"] is False
    assert nota["escrituracao_id"] is None


def test_efetivar_pela_api_grava_valores_do_documento(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a, v_serv="500.00", v_liq="450.00")
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
    )

    assert resposta.status_code == 201, resposta.content
    corpo = resposta.json()
    assert corpo["estado"] == "efetivada"
    assert corpo["valor_servico"] == "500.00"
    assert corpo["valor_liquido"] == "450.00"
    gravada = EscrituracaoFiscal.objects.get()
    assert gravada.valor_servico == Decimal("500.00")
    # A trilha guarda quem fez, pelo request.
    (registro,) = RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.efetivada")
    assert registro.usuario_id == usuario_gestor_a.pk


def test_valor_enviado_no_corpo_e_recusado_com_400_e_nada_e_gravado(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # Política de dados não contratados (BL-196): o valor vem do documento. Aceitar
    # e ignorar faria o cliente crer que escolheu o valor.
    nota = _nota(escritorio_a, usuario_gestor_a, v_serv="500.00", v_liq="450.00")
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client,
        _url_efetivar(empresa_a, _vinculo(nota, empresa_a)),
        {"natureza": NATUREZA, "valor_servico": "1.00", "valor_liquido": "0.01"},
    )

    assert resposta.status_code == 400
    assert "valor_servico" in str(resposta.json())
    assert EscrituracaoFiscal.objects.count() == 0
    assert RegistroAuditoria.objects.filter(acao__startswith="escrituracao_fiscal.").count() == 0


def test_querystring_no_post_de_efetivar_e_recusada(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_efetivar(empresa_a, _vinculo(nota, empresa_a)) + "?natureza=" + OUTRA,
        data=json.dumps({"natureza": NATUREZA}),
        content_type="application/json",
    )

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.count() == 0


def test_idempotency_key_nao_e_aceita_como_se_protegesse_a_api(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    # Esta API não usa Idempotency-Key. Enviá-la deve falhar alto, e não parecer
    # que a repetição está protegida.
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.post(
        _url_efetivar(empresa_a, _vinculo(nota, empresa_a)),
        data=json.dumps({"natureza": NATUREZA}),
        content_type="application/json",
        HTTP_IDEMPOTENCY_KEY="chave-qualquer",
    )

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.count() == 0


def test_estornar_com_campo_extra_e_recusado_e_nao_estorna(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client,
        _url_estornar(empresa_a, escrituracao),
        {"motivo": "erro", "data_estorno": "2001-01-01"},
    )

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == "efetivada"


def test_efetivar_repetido_com_a_mesma_natureza_e_200_e_nao_duplica(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)
    url = _url_efetivar(empresa_a, _vinculo(nota, empresa_a))

    primeira = _post(client, url, {"natureza": NATUREZA})
    segunda = _post(client, url, {"natureza": NATUREZA})

    assert primeira.status_code == 201
    assert segunda.status_code == 200
    assert segunda.json()["id"] == primeira.json()["id"]
    assert EscrituracaoFiscal.objects.count() == 1


def test_efetivar_com_outra_natureza_com_nota_efetivada_responde_409(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)
    url = _url_efetivar(empresa_a, _vinculo(nota, empresa_a))
    _post(client, url, {"natureza": NATUREZA})

    resposta = _post(client, url, {"natureza": OUTRA})

    assert resposta.status_code == 409
    assert "Estorne" in resposta.json()["detail"]
    assert EscrituracaoFiscal.objects.count() == 1


def test_efetivar_nota_cancelada_responde_409(client, escritorio_a, empresa_a, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    services.receber_envio(
        escritorio=escritorio_a,
        usuario=usuario_gestor_a,
        arquivo=xml_evento(chave_nfse=chave_nfse_de(nota.identificador), codigo="e101101"),
        nome_arquivo="evento.xml",
    )
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": NATUREZA}
    )

    assert resposta.status_code == 409
    assert "cancelada" in resposta.json()["detail"]
    assert EscrituracaoFiscal.objects.count() == 0


def test_efetivar_nota_tomada_responde_400(client, escritorio_a, empresa_a2, usuario_gestor_a):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = _post(
        client,
        _url_efetivar(empresa_a2, _vinculo(nota, empresa_a2, papel=PapelDocumento.TOMADOR)),
        {"natureza": NATUREZA},
    )

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.count() == 0


@pytest.mark.parametrize(
    "corpo",
    [{"natureza": "aliquota_5"}, {}, {"natureza": None}],
)
def test_efetivar_com_natureza_invalida_ou_ausente_responde_400(
    client, escritorio_a, empresa_a, usuario_gestor_a, corpo
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = _post(client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), corpo)

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.count() == 0


@pytest.mark.parametrize("motivo", ["", "   "])
def test_estornar_sem_motivo_responde_400_e_nao_estorna(
    client, escritorio_a, empresa_a, usuario_gestor_a, motivo
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": motivo})

    assert resposta.status_code == 400
    assert EscrituracaoFiscal.objects.get(pk=escrituracao.pk).estado == "efetivada"


def test_estornar_com_motivo_devolve_a_nota_para_a_escriturar(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    escrituracao = servico.efetivar_escrituracao(
        _vinculo(nota, empresa_a), NATUREZA, usuario_gestor_a
    )
    _logar(client, usuario_gestor_a)

    resposta = _post(client, _url_estornar(empresa_a, escrituracao), {"motivo": "natureza errada"})

    assert resposta.status_code == 200
    assert resposta.json()["motivo_estorno"] == "natureza errada"
    (linha,) = client.get(_url_notas(empresa_a)).json()["notas"]
    assert linha["situacao"] == "a_escriturar"
    assert RegistroAuditoria.objects.filter(acao="escrituracao_fiscal.estornada").count() == 1


@pytest.mark.parametrize(
    "consulta", ["", "ano=2024", "ano=2024&mes=13", "ano=abc&mes=1", "ano=1800&mes=1"]
)
def test_consulta_com_periodo_invalido_responde_400(
    client, escritorio_a, empresa_a, usuario_gestor_a, consulta
):
    _logar(client, usuario_gestor_a)

    resposta = client.get(f"/fiscal/api/empresas/{empresa_a.pk}/notas-prestadas/?{consulta}")

    assert resposta.status_code == 400


def test_conferencia_pela_api_fecha_recebidas_e_lista_bloqueios_e_avisos(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    efetivada = _nota(escritorio_a, usuario_gestor_a, sufixo=1)
    _nota(
        escritorio_a,
        usuario_gestor_a,
        sufixo=2,
        dh_emi="2024-01-15T10:00:00-03:00",
        d_compet="2024-02-01",
    )
    servico.efetivar_escrituracao(_vinculo(efetivada, empresa_a), NATUREZA, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = client.get(_url_conferencia(empresa_a, 2024, 2))

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["recebidas"] == corpo["escrituradas"] + corpo["pendentes"] == 1
    assert corpo["escrituradas"] == 0
    assert len(corpo["bloqueios"]) == 1
    assert corpo["bloqueios"][0]["competencia_difere_da_emissao"] is True
    assert len(corpo["avisos"]) == 1


def test_erro_de_negocio_responde_json_sem_detalhe_interno(
    client, escritorio_a, empresa_a, usuario_gestor_a
):
    nota = _nota(escritorio_a, usuario_gestor_a)
    _logar(client, usuario_gestor_a)

    resposta = _post(client, _url_efetivar(empresa_a, _vinculo(nota, empresa_a)), {"natureza": "x"})

    assert resposta.status_code == 400
    assert resposta.headers["Content-Type"].startswith("application/json")
    assert b"Traceback" not in resposta.content
