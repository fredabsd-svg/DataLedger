"""DL-070 (frente A) — entradas do acesso: bootstrap e convite.

Defeitos cobertos, todos reproduzidos em PostgreSQL antes da correção:

- BL-645: `POST /bootstrap/` gravava `cnpj='abc'`, respondia 500 (DataError)
  para máscara que não cabe na coluna e 500 (IntegrityError) para CNPJ já
  cadastrado. A validação passa a ser a mesma do cadastro público.
- BL-646: `nome` com mais de 200 caracteres dava 500 (DataError).
- BL-647: `POST /convites/emitir/` aceitava e-mail malformado e dava 500
  (DataError) acima de 254 caracteres.
- BL-651: escritório sem vínculo do usuário respondia "Apenas ADMINISTRADOR..."
  e escritório inexistente respondia "Escritório inválido.", o que revelava a
  existência de id alheio. Os dois precisam responder igual.

Regra transversal: entrada recusada não grava `Escritorio`, `ConviteEscritorio`
nem `VinculoUsuarioEscritorio`, e não pode virar 500.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db.models import Max
from django.test import Client
from django.urls import reverse

from apps.empresas.validators import normalizar_cnpj, validar_cnpj
from apps.tenancy.forms import PrimeiroEscritorioForm
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    Papel,
    VinculoUsuarioEscritorio,
)

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-dl070"

# CNPJs sintéticos com dígito verificador válido, gerados pela própria função
# `validar_cnpj` do projeto. Nenhum é de empresa real.
CNPJ_VALIDO = "11222333000181"
CNPJ_VALIDO_MASCARADO = "11.222.333/0001-81"
CNPJ_VALIDO_2 = "12345678000195"


def _usuario(username):
    return get_user_model().objects.create_user(
        username=username, email=f"{username}@dl070.local", password=SENHA
    )


def _escritorio_com_admin(username, cnpj):
    admin = _usuario(username)
    escritorio = Escritorio.objects.create(nome=f"Escritório {username}", cnpj=cnpj)
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin, escritorio=escritorio, papel=Papel.ADMINISTRADOR, ativo=True
    )
    return admin, escritorio


def _contagens():
    return (
        Escritorio.objects.count(),
        ConviteEscritorio.objects.count(),
        VinculoUsuarioEscritorio.objects.count(),
    )


def _mensagens(resposta):
    return [str(m) for m in get_messages(resposta.wsgi_request)]


# ---------------------------------------------------------------------------
# BL-645 / BL-646 — POST /bootstrap/
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nome", "cnpj", "trecho_da_mensagem"),
    [
        pytest.param("Escritório Teste", "abc", "CNPJ deve ter 14 caracteres", id="cnpj_abc"),
        pytest.param(
            "Escritório Teste",
            "11.222.333/0001-810",
            "no máximo 18 caracteres",
            id="cnpj_mascarado_longo",
        ),
        pytest.param(
            "Escritório Teste",
            "11.222.333/0001-82",
            "dígitos verificadores não conferem",
            id="cnpj_mascarado_dv_invalido",
        ),
        pytest.param(
            "Escritório Teste",
            "11222333000182",
            "dígitos verificadores não conferem",
            id="cnpj_so_digitos_dv_invalido",
        ),
        pytest.param(
            "N" * 201,
            CNPJ_VALIDO,
            "no máximo 200 caracteres",
            id="nome_com_201_caracteres",
        ),
    ],
)
def test_bootstrap_recusa_entrada_invalida_sem_500_e_sem_gravar(
    client, nome, cnpj, trecho_da_mensagem
):
    usuario = _usuario("bootstrap-invalido")
    client.force_login(usuario)
    antes = _contagens()

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"), {"nome": nome, "cnpj": cnpj}
    )

    assert resposta.status_code == 200, "entrada inválida deve voltar à tela, não 500"
    assert any(trecho_da_mensagem in m for m in _mensagens(resposta)), _mensagens(resposta)
    assert _contagens() == antes, "entrada recusada não pode gravar nada"


@pytest.mark.parametrize(
    "cnpj_enviado",
    [
        pytest.param(CNPJ_VALIDO, id="so_digitos"),
        pytest.param(CNPJ_VALIDO_MASCARADO, id="mascarado"),
    ],
)
def test_bootstrap_recusa_cnpj_ja_cadastrado_com_mensagem(client, cnpj_enviado):
    # Com dígitos, o defeito original era IntegrityError (500); com máscara,
    # DataError. As duas formas são o mesmo CNPJ e devem ser recusadas igual.
    Escritorio.objects.create(nome="Já existente", cnpj=CNPJ_VALIDO)
    usuario = _usuario("bootstrap-duplicado")
    client.force_login(usuario)
    antes = _contagens()

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Novo Escritório", "cnpj": cnpj_enviado},
    )

    assert resposta.status_code == 200
    assert any("já está cadastrado" in m for m in _mensagens(resposta))
    assert _contagens() == antes


def test_bootstrap_aceita_cnpj_com_mascara_e_grava_so_digitos(client):
    usuario = _usuario("bootstrap-mascarado")
    client.force_login(usuario)

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Escritório Mascarado", "cnpj": CNPJ_VALIDO_MASCARADO},
    )

    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("tenancy:painel")
    escritorio = Escritorio.objects.get(nome="Escritório Mascarado")
    assert escritorio.cnpj == CNPJ_VALIDO
    assert VinculoUsuarioEscritorio.objects.filter(
        usuario=usuario, escritorio=escritorio, papel=Papel.ADMINISTRADOR
    ).exists()


def test_bootstrap_aceita_nome_com_exatamente_200_caracteres(client):
    usuario = _usuario("bootstrap-limite")
    client.force_login(usuario)
    nome_limite = "N" * 200

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": nome_limite, "cnpj": CNPJ_VALIDO},
    )

    assert resposta.status_code == 302
    assert Escritorio.objects.filter(nome=nome_limite, cnpj=CNPJ_VALIDO).exists()


# ---------------------------------------------------------------------------
# BL-647 — POST /convites/emitir/ (e-mail)
# ---------------------------------------------------------------------------

# 300 caracteres exatos, malformado (local part com 288 caracteres).
EMAIL_300_CARACTERES = "a" * 288 + "@dl070.local"
# 260 caracteres, mas bem formado segundo `validate_email`: só o tamanho recusa.
EMAIL_260_BEM_FORMADO = "a" * 64 + "@" + ("d" * 63 + ".") * 3 + "com"
# 254 caracteres exatos, bem formado: o limite do próprio campo, aceito.
EMAIL_254_BEM_FORMADO = "a" * 64 + "@" + ("d" * 63 + ".") * 2 + "d" * 57 + ".com"


def test_fixtures_de_email_tem_o_tamanho_declarado():
    # Guarda contra erro de contagem: o teste de limite só prova algo se o
    # e-mail tem mesmo o tamanho que o nome diz.
    assert len(EMAIL_300_CARACTERES) == 300
    assert len(EMAIL_260_BEM_FORMADO) == 260
    assert len(EMAIL_254_BEM_FORMADO) == 254


@pytest.mark.parametrize(
    ("email", "trecho_da_mensagem"),
    [
        pytest.param("nao-e-email", "E-mail do convidado inválido", id="malformado"),
        pytest.param("", "E-mail do convidado é obrigatório", id="vazio"),
        pytest.param("a@", "E-mail do convidado inválido", id="incompleto"),
        pytest.param("E-mail do convidado", "E-mail do convidado inválido", id="texto_sem_arroba"),
        pytest.param(EMAIL_300_CARACTERES, "E-mail do convidado", id="300_caracteres"),
        pytest.param(
            EMAIL_260_BEM_FORMADO,
            "no máximo 254 caracteres",
            id="260_caracteres_bem_formado",
        ),
    ],
)
def test_convite_recusa_email_invalido_sem_500_e_sem_criar_convite(
    client, email, trecho_da_mensagem
):
    admin, escritorio = _escritorio_com_admin("admin-email-invalido", CNPJ_VALIDO)
    client.force_login(admin)
    antes = _contagens()

    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": escritorio.pk, "email": email},
    )

    assert resposta.status_code == 302, "e-mail inválido deve voltar ao painel, não 500"
    assert resposta["Location"] == reverse("tenancy:painel")
    assert any(trecho_da_mensagem in m for m in _mensagens(resposta)), _mensagens(resposta)
    assert _contagens() == antes, "e-mail recusado não pode criar convite"


def test_convite_aceita_email_de_254_caracteres_no_limite(client):
    admin, escritorio = _escritorio_com_admin("admin-email-limite", CNPJ_VALIDO)
    client.force_login(admin)

    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": escritorio.pk, "email": EMAIL_254_BEM_FORMADO},
    )

    assert resposta.status_code == 302
    assert ConviteEscritorio.objects.filter(email=EMAIL_254_BEM_FORMADO).exists()


def test_administrador_emite_convite_com_email_valido(client):
    # Controle positivo: a validação nova não pode barrar o caminho feliz.
    admin, escritorio = _escritorio_com_admin("admin-controle", CNPJ_VALIDO)
    client.force_login(admin)

    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": escritorio.pk, "email": "convidado-dl070@dl070.local"},
    )

    assert resposta.status_code == 302
    convite = ConviteEscritorio.objects.get(email="convidado-dl070@dl070.local")
    assert convite.escritorio == escritorio
    assert convite.emitido_por == admin


# ---------------------------------------------------------------------------
# BL-651 — escritorio_id de escritório alheio não revela existência
# ---------------------------------------------------------------------------


def test_escritorio_sem_vinculo_responde_igual_a_id_inexistente(client):
    # O usuário não tem vínculo nenhum com `alheio`. Antes da correção, o id
    # existente caía em "Apenas ADMINISTRADOR..." e o inexistente em
    # "Escritório inválido.", e a diferença revelava que `alheio` existe.
    _admin_alheio, alheio = _escritorio_com_admin("admin-alheio", CNPJ_VALIDO)
    intruso = _usuario("intruso-sem-vinculo")
    inexistente = Escritorio.objects.aggregate(maior=Max("pk"))["maior"] + 1000
    url = reverse("tenancy:emitir-convite")
    email = "convidado-bl651@dl070.local"
    # Dois clientes separados: a mensagem da primeira resposta fica no cookie
    # até ser exibida, e a segunda requisição a leria junto. Cada resposta
    # precisa ser comparada sozinha.
    cliente_existente = Client()
    cliente_existente.force_login(intruso)
    cliente_inexistente = Client()
    cliente_inexistente.force_login(intruso)

    resposta_existente = cliente_existente.post(url, {"escritorio_id": alheio.pk, "email": email})
    resposta_inexistente = cliente_inexistente.post(
        url, {"escritorio_id": inexistente, "email": email}
    )

    assert resposta_existente.status_code == resposta_inexistente.status_code == 302
    assert resposta_existente["Location"] == resposta_inexistente["Location"]
    assert _mensagens(resposta_existente) == _mensagens(resposta_inexistente)
    assert _mensagens(resposta_existente) == ["Escritório inválido."]
    assert ConviteEscritorio.objects.count() == 0


def test_membro_nao_administrador_continua_recusado_pela_autorizacao_do_servico(client):
    # A correção de BL-651 só muda a resposta para quem não tem vínculo. Quem
    # tem vínculo sem ser ADMINISTRADOR continua recusado pelo serviço, que
    # segue sendo a autorização real.
    _admin, escritorio = _escritorio_com_admin("admin-do-analista", CNPJ_VALIDO)
    analista = _usuario("analista-com-vinculo")
    VinculoUsuarioEscritorio.objects.create(
        usuario=analista, escritorio=escritorio, papel=Papel.ANALISTA, ativo=True
    )
    client.force_login(analista)

    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": escritorio.pk, "email": "convidado-analista@dl070.local"},
    )

    assert resposta.status_code == 302
    assert any("Apenas ADMINISTRADOR" in m for m in _mensagens(resposta))
    assert not ConviteEscritorio.objects.exists()


# ---------------------------------------------------------------------------
# Corrida de CNPJ duplicado: a checagem prévia não enxerga o CNPJ, e o banco
# é quem recusa no INSERT (IntegrityError). Antes da correção, isso era 500.
# ---------------------------------------------------------------------------


def _clean_cnpj_sem_checagem_de_duplicidade(self):
    # Mesma normalização e validação do formulário real, sem a consulta de
    # duplicidade. Simula a janela entre a checagem e o INSERT, em que outra
    # requisição já gravou o mesmo CNPJ.
    cnpj = normalizar_cnpj(self.cleaned_data["cnpj"])
    validar_cnpj(cnpj)
    return cnpj


def test_corrida_de_cnpj_duplicado_responde_com_mensagem_sem_500_e_sem_gravar(client, monkeypatch):
    Escritorio.objects.create(nome="Já existente", cnpj=CNPJ_VALIDO)
    monkeypatch.setattr(
        PrimeiroEscritorioForm, "clean_cnpj", _clean_cnpj_sem_checagem_de_duplicidade
    )
    usuario = _usuario("bootstrap-corrida")
    client.force_login(usuario)
    antes = _contagens()

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Novo Escritório", "cnpj": CNPJ_VALIDO_MASCARADO},
    )

    assert resposta.status_code == 200, "corrida de duplicado deve voltar à tela, não 500"
    assert any("já está cadastrado" in m for m in _mensagens(resposta)), _mensagens(resposta)
    assert _contagens() == antes, "a tentativa perdida na corrida não pode gravar nada"
    assert not VinculoUsuarioEscritorio.objects.filter(usuario=usuario).exists()

    # A conexão continua utilizável depois do erro de integridade: a mesma
    # requisição com outro CNPJ, ainda sem a checagem prévia, tem de dar certo.
    resposta_seguinte = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Escritório Depois da Corrida", "cnpj": "22.233.344/0001-83"},
    )
    assert resposta_seguinte.status_code == 302
    assert Escritorio.objects.filter(nome="Escritório Depois da Corrida").exists()
