"""DL-046, RC-129/HI-31: CAEPF (Cadastro de Atividade Econômica da Pessoa
Física) — campo opcional no cadastro de cliente pessoa física.

Fonte (consultada em 2026-09-26): documentação oficial do Cadastro
Compartilhado da Receita Federal (SERPRO) — 14 posições (9 do CPF + 5 do
número resumido de inscrição), SEM algoritmo de dígito verificador
documentado. Por isso a validação aqui é só de FORMATO (14 dígitos) e de
COERÊNCIA estrutural com o CPF do titular (os 9 primeiros dígitos batem) —
nunca um DV inventado (HI-31, requisitos.md).
"""

import json

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.empresas.models import Empresa, TipoInscricao
from apps.empresas.validators import normalizar_caepf, validar_caepf
from apps.empresas.views import _campo_da_restricao_de_empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

CPF_VALIDO = "12345678909"
CAEPF_COERENTE = "12345678900001"  # 9 primeiros dígitos == CPF_VALIDO[:9]
CAEPF_INCOERENTE = "99999999900001"


@pytest.fixture
def escritorio():
    return Escritorio.objects.create(nome="Escritório CAEPF", cnpj="91100000000070")


# ---------------------------------------------------------------------------
# Validador puro
# ---------------------------------------------------------------------------


def test_validar_caepf_aceita_14_digitos():
    validar_caepf(CAEPF_COERENTE)  # não levanta


def test_validar_caepf_recusa_tamanho_errado():
    with pytest.raises(ValidationError):
        validar_caepf("123456789")


def test_validar_caepf_recusa_nao_numerico_apos_normalizar():
    with pytest.raises(ValidationError):
        validar_caepf("abcdefghijklmn")


def test_normalizar_caepf_remove_mascara():
    assert normalizar_caepf("123.456.789-00001") == CAEPF_COERENTE.replace("00001", "") + "00001"


def test_validar_caepf_recusa_incoerencia_com_cpf():
    with pytest.raises(ValidationError):
        validar_caepf(CAEPF_INCOERENTE, cpf=CPF_VALIDO)


def test_validar_caepf_aceita_coerencia_com_cpf():
    validar_caepf(CAEPF_COERENTE, cpf=CPF_VALIDO)  # não levanta


def test_achado_frontend_campo_da_restricao_de_caepf_e_caepf_nao_cnpj():
    """Achado do `especialista-frontend` na rodada 1 de auditoria: a
    constraint "empresa_caepf_so_para_cpf_com_formato_valido" já entrava
    no `with restricao_como_400(mensagens_de(...))` de `EmpresaListCreateView.
    perform_create`, mas faltava em `_CAMPO_DA_RESTRICAO_DE_EMPRESA` — sem
    a entrada, uma corrida que violasse ESSA constraint caía no
    `.get(..., "cnpj")` (o padrão da função) e reportava o erro no campo
    errado."""
    assert _campo_da_restricao_de_empresa("empresa_caepf_so_para_cpf_com_formato_valido") == "caepf"


def test_m19_caepf_que_difere_do_cpf_so_no_nono_digito_e_recusado():
    """M19 (rodada 1 de auditoria): isola a comparação dos NOVE dígitos —
    um CAEPF que bate com o CPF nos OITO primeiros mas erra só no nono
    (`CPF_VALIDO[:9] = "123456789"`, CAEPF aqui com "...780") precisa ser
    recusado; uma comparação enfraquecida para 8 dígitos deixaria passar."""
    caepf_com_nono_digito_errado = "12345678000001"
    assert caepf_com_nono_digito_errado[:8] == CPF_VALIDO[:8]
    assert caepf_com_nono_digito_errado[:9] != CPF_VALIDO[:9]
    with pytest.raises(ValidationError):
        validar_caepf(caepf_com_nono_digito_errado, cpf=CPF_VALIDO)


# ---------------------------------------------------------------------------
# Modelo — Empresa.clean() / CheckConstraint
# ---------------------------------------------------------------------------


def test_empresa_cpf_com_caepf_coerente_e_aceita(escritorio):
    # `exclude=["cnpj"]`: `Empresa.cnpj` não tem `blank=True` de propósito
    # (obrigatoriedade de FORMULÁRIO pré-existente à DL-046 — comentário em
    # `models.py` sobre EmpresaForm/admin ainda não conhecerem
    # `tipo_inscricao`); não é a regra sob teste aqui.
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano CAEPF",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
        caepf=CAEPF_COERENTE,
    )
    empresa.full_clean(exclude=["cnpj"])
    empresa.save()
    assert empresa.pk is not None


def test_empresa_cpf_com_caepf_incoerente_e_recusada(escritorio):
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano CAEPF Incoerente",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
        caepf=CAEPF_INCOERENTE,
    )
    with pytest.raises(ValidationError) as excinfo:
        empresa.full_clean(exclude=["cnpj"])
    assert "caepf" in excinfo.value.message_dict or "__all__" in excinfo.value.message_dict


def test_empresa_caepf_e_opcional(escritorio):
    empresa = Empresa(
        escritorio=escritorio,
        razao_social="Fulano Sem CAEPF",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
    )
    empresa.full_clean(exclude=["cnpj"])
    empresa.save()
    assert empresa.caepf == ""


def test_constraint_recusa_caepf_para_empresa_cnpj_no_banco(escritorio):
    # Bypassa `full_clean()` de propósito (mesmo padrão de
    # test_dl076_b8_modo_escrituracao_constraint.py): a CheckConstraint é a
    # camada que sobrevive a bulk_create/gravação direta pelo ORM, sem
    # passar por `clean()`.
    with pytest.raises(IntegrityError, match="empresa_caepf_so_para_cpf_com_formato_valido"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio,
                razao_social="Empresa CNPJ CAEPF Direto",
                tipo_inscricao=TipoInscricao.CNPJ,
                cnpj="11122233000183",
                caepf=CAEPF_COERENTE,
            )


def test_constraint_recusa_caepf_com_formato_invalido_no_banco(escritorio):
    with pytest.raises(IntegrityError, match="empresa_caepf_so_para_cpf_com_formato_valido"):
        with transaction.atomic():
            Empresa.objects.create(
                escritorio=escritorio,
                razao_social="Empresa CPF CAEPF Curto Demais",
                tipo_inscricao=TipoInscricao.CPF,
                cpf=CPF_VALIDO,
                caepf="123",
            )


def test_constraint_aceita_caepf_vazio_para_cpf(escritorio):
    empresa = Empresa.objects.create(
        escritorio=escritorio,
        razao_social="Empresa CPF Sem CAEPF Direto",
        tipo_inscricao=TipoInscricao.CPF,
        cpf=CPF_VALIDO,
    )
    assert empresa.caepf == ""


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


def _usuario_gestor(escritorio, username):
    from django.contrib.auth import get_user_model

    usuario = get_user_model().objects.create_user(
        username=username, email=f"{username}@escritorio.com.br", password="senha-forte-123"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return usuario


def test_api_cria_empresa_cpf_com_caepf_coerente(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-ok")
    client.login(username="gestor-caepf-ok", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Fulano CAEPF API",
                "tipo_inscricao": "CPF",
                "cpf": CPF_VALIDO,
                "caepf": CAEPF_COERENTE,
                "modo_escrituracao": "livro_caixa",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 201, resposta.content
    assert Empresa.objects.get(cpf=CPF_VALIDO).caepf == CAEPF_COERENTE


def test_api_recusa_caepf_incoerente_com_cpf(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-incoerente")
    client.login(username="gestor-caepf-incoerente", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Fulano CAEPF Incoerente API",
                "tipo_inscricao": "CPF",
                "cpf": CPF_VALIDO,
                "caepf": CAEPF_INCOERENTE,
                "modo_escrituracao": "livro_caixa",
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert "caepf" in resposta.json()


def test_api_recusa_caepf_para_empresa_cnpj(client, escritorio):
    _usuario_gestor(escritorio, "gestor-caepf-cnpj")
    client.login(username="gestor-caepf-cnpj", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:api-lista"),
        data=json.dumps(
            {
                "razao_social": "Empresa CNPJ CAEPF API",
                "tipo_inscricao": "CNPJ",
                "cnpj": "11122233000183",
                "caepf": CAEPF_COERENTE,
            }
        ),
        content_type="application/json",
    )
    assert resposta.status_code == 400
    assert "caepf" in resposta.json()


# ---------------------------------------------------------------------------
# Tela — `criar_empresa` (`especialista-frontend`, autorização do
# arquiteto-senior de 2026-09-26, no mesmo worktree ba9f109/DL-046 fatia 1).
# MESMA regra e MESMA mensagem da API (`EmpresaForm.clean()`, DE-026) —
# estes testes provam que a TELA obedece, nunca reconferem a regra em si
# (isso já está provado nas seções "Modelo"/"API" acima). Edição de
# empresa EXISTENTE não existe hoje como tela (só `criar_empresa`) — fora
# do escopo desta etapa, registrado no backlog pelo arquiteto-senior.
# ---------------------------------------------------------------------------


def test_tela_cadastro_pf_com_caepf_valido_grava(client, escritorio):
    _usuario_gestor(escritorio, "gestor-tela-caepf-ok")
    client.login(username="gestor-tela-caepf-ok", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano CAEPF Tela",
            "nome_fantasia": "",
            "tipo_inscricao": "CPF",
            "cnpj": "",
            "cpf": CPF_VALIDO,
            "caepf": CAEPF_COERENTE,
            "modo_escrituracao": "livro_caixa",
        },
    )
    assert resposta.status_code == 302  # redireciona — sucesso
    empresa = Empresa.objects.get(razao_social="Fulano CAEPF Tela")
    assert empresa.caepf == CAEPF_COERENTE


def test_tela_cadastro_pf_com_caepf_incoerente_mostra_mensagem_e_preserva_formulario(
    client, escritorio
):
    _usuario_gestor(escritorio, "gestor-tela-caepf-incoerente")
    client.login(username="gestor-tela-caepf-incoerente", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano CAEPF Incoerente Tela",
            "nome_fantasia": "",
            "tipo_inscricao": "CPF",
            "cnpj": "",
            "cpf": CPF_VALIDO,
            "caepf": CAEPF_INCOERENTE,
            "modo_escrituracao": "livro_caixa",
        },
    )
    assert resposta.status_code == 200  # re-renderiza, não redireciona
    conteudo = resposta.content.decode()
    assert "não corresponde ao CPF" in conteudo
    # O que a pessoa digitou continua lá (arquétipo B, direção de arte §2):
    # nada foi gravado, e o formulário não volta em branco.
    assert 'value="Fulano CAEPF Incoerente Tela"' in conteudo
    assert f'value="{CAEPF_INCOERENTE}"' in conteudo
    assert not Empresa.objects.filter(razao_social="Fulano CAEPF Incoerente Tela").exists()


def test_tela_cadastro_pf_com_caepf_formato_invalido_mostra_mensagem_do_servidor(
    client, escritorio
):
    _usuario_gestor(escritorio, "gestor-tela-caepf-formato")
    client.login(username="gestor-tela-caepf-formato", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano CAEPF Formato Tela",
            "nome_fantasia": "",
            "tipo_inscricao": "CPF",
            "cnpj": "",
            "cpf": CPF_VALIDO,
            "caepf": "123",
            "modo_escrituracao": "livro_caixa",
        },
    )
    assert resposta.status_code == 200
    assert "14 dígitos" in resposta.content.decode()
    assert not Empresa.objects.filter(razao_social="Fulano CAEPF Formato Tela").exists()


def test_tela_cadastro_cnpj_com_caepf_e_recusado_conforme_o_servidor(client, escritorio):
    _usuario_gestor(escritorio, "gestor-tela-caepf-cnpj")
    client.login(username="gestor-tela-caepf-cnpj", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Empresa CNPJ CAEPF Tela Ltda",
            "nome_fantasia": "",
            "tipo_inscricao": "CNPJ",
            "cnpj": "11.222.333/0001-81",
            "cpf": "",
            "caepf": CAEPF_COERENTE,
            "modo_escrituracao": "contabilidade",
        },
    )
    assert resposta.status_code == 200
    # MESMA mensagem que a API usa (EmpresaSerializer.validate) — DE-026:
    # tela e API nunca contam duas histórias diferentes.
    assert "CAEPF só é aceito para empresa com tipo de inscrição CPF." in resposta.content.decode()
    assert not Empresa.objects.filter(razao_social="Empresa CNPJ CAEPF Tela Ltda").exists()


def test_tela_cadastro_pf_sem_caepf_continua_gravando_normalmente(client, escritorio):
    """Controle: CAEPF é OPCIONAL — não preenchê-lo não impede o
    cadastro nem gera erro nenhum (mesma garantia do modelo/API, agora do
    lado da tela)."""
    _usuario_gestor(escritorio, "gestor-tela-caepf-vazio")
    client.login(username="gestor-tela-caepf-vazio", password="senha-forte-123")

    resposta = client.post(
        reverse("empresas:criar"),
        {
            "razao_social": "Fulano Sem CAEPF Tela",
            "nome_fantasia": "",
            "tipo_inscricao": "CPF",
            "cnpj": "",
            "cpf": CPF_VALIDO,
            "caepf": "",
            "modo_escrituracao": "livro_caixa",
        },
    )
    assert resposta.status_code == 302
    empresa = Empresa.objects.get(razao_social="Fulano Sem CAEPF Tela")
    assert empresa.caepf == ""


def test_tela_formulario_de_nova_empresa_mostra_o_campo_caepf(client, escritorio):
    _usuario_gestor(escritorio, "gestor-tela-caepf-campo")
    client.login(username="gestor-tela-caepf-campo", password="senha-forte-123")

    conteudo = client.get(reverse("empresas:criar")).content.decode()
    assert "CAEPF" in conteudo
    assert "14 dígitos" in conteudo
