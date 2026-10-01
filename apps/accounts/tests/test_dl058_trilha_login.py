"""DL-058 (B3 e B4): trilha de falha de login e autenticação explícita da API.

Dados 100% sintéticos, criados nos próprios testes.
"""

import base64

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.auditoria.models import RegistroAuditoria
from apps.contabilidade.models import NaturezaConta, TipoConta
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio, Papel, VinculoUsuarioEscritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
# Uma "senha" digitada por engano no campo de usuário. Não pode aparecer na
# trilha em lugar nenhum.
SENHA_NO_CAMPO_ERRADO = "Minha-Senha-Secreta-9"


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password=SENHA
    )


def _falhas():
    return list(RegistroAuditoria.objects.filter(acao="login.falha").order_by("id"))


# --- B3 -----------------------------------------------------------------------


def test_b3_falha_com_usuario_inexistente_nao_grava_o_texto_digitado(client, usuario):
    client.post(reverse("login"), {"username": SENHA_NO_CAMPO_ERRADO, "password": "qualquer"})

    (registro,) = _falhas()
    assert registro.usuario is None
    assert "username" not in registro.detalhes
    assert SENHA_NO_CAMPO_ERRADO not in str(registro.detalhes)
    assert SENHA_NO_CAMPO_ERRADO.lower() not in str(registro.detalhes).lower()
    # Só o prefixo do HMAC: 16 caracteres hexadecimais.
    prefixo = registro.detalhes["username_hmac"]
    assert len(prefixo) == 16
    int(prefixo, 16)


def test_b3_mesma_tentativa_repetida_gera_o_mesmo_prefixo(client, usuario):
    """O prefixo ainda serve para agrupar a mesma tentativa (e por isso a
    normalização: caixa e espaços nas pontas não mudam o valor)."""
    client.post(reverse("login"), {"username": "Fulano-Inexistente", "password": "x"})
    client.post(reverse("login"), {"username": "  fulano-inexistente ", "password": "x"})
    client.post(reverse("login"), {"username": "outro-inexistente", "password": "x"})

    primeiro, segundo, terceiro = (r.detalhes["username_hmac"] for r in _falhas())
    assert primeiro == segundo
    assert primeiro != terceiro


def test_b3_prefixo_depende_do_segredo_da_aplicacao(client, usuario, settings):
    """HMAC e não hash puro: com outra SECRET_KEY o valor muda, então quem lê
    a trilha não confirma candidatos de senha por força bruta offline."""
    client.post(reverse("login"), {"username": "fulano-inexistente", "password": "x"})
    settings.SECRET_KEY = "outra-chave-sintetica-apenas-para-este-teste"
    client.post(reverse("login"), {"username": "fulano-inexistente", "password": "x"})

    antes, depois = (r.detalhes["username_hmac"] for r in _falhas())
    assert antes != depois


def test_b3_trilha_e_limitador_usam_o_mesmo_resumo_do_usuario(client, usuario):
    """Integração DL-058 + DL-056: o resumo gravado em `login.falha` é o mesmo
    da chave do limitador (mesma normalização, mesma SECRET_KEY)."""
    from apps.accounts.limite_tentativas import chave_do_usuario

    client.post(reverse("login"), {"username": "  Fulano-Inexistente ", "password": "x"})

    (registro,) = _falhas()
    assert registro.detalhes["username_hmac"] == chave_do_usuario("fulano-inexistente")[:16]


def test_b3_falha_com_usuario_existente_grava_o_nome_da_conta_sem_senha(client, usuario):
    client.post(reverse("login"), {"username": "ana", "password": SENHA_NO_CAMPO_ERRADO})

    (registro,) = _falhas()
    assert registro.detalhes == {"username": "ana"}
    assert SENHA_NO_CAMPO_ERRADO not in str(registro.detalhes)
    assert SENHA not in str(registro.detalhes)


# --- B4 -----------------------------------------------------------------------


def test_b4_autenticacao_da_api_e_so_por_sessao():
    assert settings.REST_FRAMEWORK["DEFAULT_AUTHENTICATION_CLASSES"] == [
        "rest_framework.authentication.SessionAuthentication"
    ]


@pytest.fixture
def api_cenario(usuario):
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa A Ltda", cnpj="11122233000183"
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=Papel.GESTOR
    )
    return {"empresa": empresa, "url": reverse("contabilidade:contas", args=[empresa.id])}


def _basic(usuario, senha):
    credencial = base64.b64encode(f"{usuario}:{senha}".encode()).decode()
    return f"Basic {credencial}"


class _SondaDeAutenticacao(APIView):
    """View de teste que NÃO declara `authentication_classes`: usa o padrão
    da configuração, que é justamente o que a DL-058/B4 muda. Permite tudo
    para só devolver quem o DRF considerou autenticado."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"autenticado": request.user.is_authenticated})


def test_b4_basic_valido_nao_autentica_no_padrao_do_drf(usuario):
    """O teste que reprova SEM a correção. As rotas do produto exigem também
    um escritório ativo (vindo da sessão), o que mascararia o Basic; a sonda
    mede só a camada de autenticação."""
    requisicao = APIRequestFactory().get("/sonda/", HTTP_AUTHORIZATION=_basic("ana", SENHA))

    resposta = _SondaDeAutenticacao.as_view()(requisicao)

    assert resposta.data == {"autenticado": False}


def test_b4_cabecalho_basic_valido_nao_autentica_na_api(client, api_cenario):
    # Teste de ponta a ponta na rota real. Honestidade: ele passa mesmo SEM a
    # correção, porque a rota também exige escritório ativo (da sessão); quem
    # reprova sem a correção é o teste da sonda acima.
    resposta = client.get(api_cenario["url"], HTTP_AUTHORIZATION=_basic("ana", SENHA))

    assert resposta.status_code in (401, 403)
    assert resposta.status_code != 200


def test_b4_cabecalho_basic_valido_nao_escreve_na_api(client, api_cenario):
    from apps.contabilidade.models import Conta

    resposta = client.post(
        api_cenario["url"],
        data={
            "codigo": "1.1",
            "nome": "Caixa",
            "tipo": TipoConta.ATIVO,
            "natureza": NaturezaConta.DEVEDORA,
        },
        content_type="application/json",
        HTTP_AUTHORIZATION=_basic("ana", SENHA),
    )

    assert resposta.status_code in (401, 403)
    assert not Conta.objects.filter(empresa=api_cenario["empresa"]).exists()


def test_b4_sessao_continua_autenticando_na_api(client, api_cenario):
    """Par do teste acima: sem ele, 'a API recusa tudo' passaria."""
    assert client.login(username="ana", password=SENHA)

    resposta = client.get(api_cenario["url"])

    assert resposta.status_code == 200
