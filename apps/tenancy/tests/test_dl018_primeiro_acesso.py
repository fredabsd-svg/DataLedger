"""DL-018 — primeiro acesso via produto (DE-042).

Critérios de aceite que esta suíte cobre:

1. Instalação limpa → primeiro escritório → primeira empresa → primeiro
   lançamento, **sem tocar em `/admin/`** e sem comando além de subir
   o sistema. Aqui provamos o passo 1 (escritório + vínculo) — o passo
   2 (empresa) e o passo 3 (lançamento) já estão prontos pela DL-015.
3. **Autorização verificada no servidor**, nunca só na tela: quem já tem
   vínculo não ganha poder de criar escritório por acidente, e quem
   não tem vínculo não enxerga dado de escritório nenhum enquanto não
   criar o seu.
4. O isolamento entre escritórios continua provado por teste depois do
   fluxo novo — **nenhuma rota nova consulta por `pk` sem amarrar ao
   escopo**.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.auditoria.models import RegistroAuditoria
from apps.tenancy.models import (
    ConviteEscritorio,
    Escritorio,
    Papel,
    VinculoUsuarioEscritorio,
)
from apps.tenancy.services.primeiro_acesso import (
    aceitar_convite_e_criar_vinculo,
    criar_primeiro_escritorio_e_vinculo_admin,
    emitir_convite_para_escritorio,
)

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


# ---------------------------------------------------------------------------
# Critério 3 (autorização verificada no servidor): bootstrap é exclusivo
# de usuário sem vínculo.
# ---------------------------------------------------------------------------


def test_criar_primeiro_escritorio_e_vinculo_admin_funciona_quando_nao_ha_vinculo():
    """Critério 3, parte positiva: usuário sem vínculo consegue criar
    escritório + virar admin. É o fluxo principal da DL-018."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="primeiro", email="primeiro@dl018.local", password=SENHA
    )

    assert VinculoUsuarioEscritorio.objects.filter(usuario=usuario, ativo=True).count() == 0

    resultado = criar_primeiro_escritorio_e_vinculo_admin(
        usuario=usuario, nome="Escritório Teste", cnpj="11111111000111"
    )

    assert resultado.escritorio.nome == "Escritório Teste"
    assert resultado.escritorio.cnpj == "11111111000111"
    assert resultado.vinculo.usuario == usuario
    assert resultado.vinculo.escritorio == resultado.escritorio
    assert resultado.vinculo.papel == Papel.ADMINISTRADOR
    assert resultado.vinculo.ativo is True


def test_criar_primeiro_escritorio_recusa_quando_ja_ha_vinculo_ativo():
    """Critério 3, parte defensiva: o segundo POST ou a segunda aba do
    bootstrap não cria escritório duplicado. Defesa em service —
    qualquer caminho que invoque o serviço respeita."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="segundo", email="segundo@dl018.local", password=SENHA
    )

    # Primeira chamada — sucesso.
    criar_primeiro_escritorio_e_vinculo_admin(
        usuario=usuario, nome="Escritório 1", cnpj="11111111000111"
    )

    # Segunda chamada — defesa do service.
    with pytest.raises(Exception) as excinfo:
        criar_primeiro_escritorio_e_vinculo_admin(
            usuario=usuario, nome="Escritório 2", cnpj="22222222000122"
        )
    assert (
        "escritório ativo" in str(excinfo.value).lower() or "primeiro" in str(excinfo.value).lower()
    )

    # Apenas um escritório foi criado.
    assert Escritorio.objects.count() == 1


def test_criar_primeiro_escritorio_gera_registro_de_auditoria():
    """DE-042 / DL-018 critério 2: criar escritório é ato de sigilo,
    registrado na trilha."""
    User = get_user_model()
    usuario = User.objects.create_user(username="auditado", email="aud@dl018.local", password=SENHA)

    resultado = criar_primeiro_escritorio_e_vinculo_admin(
        usuario=usuario, nome="Escritório Auditado", cnpj="33333333000133"
    )

    registros = RegistroAuditoria.objects.filter(
        acao="escritorio.criado_por_bootstrap",
        escritorio=resultado.escritorio,
    )
    assert registros.count() == 1
    assert registros.first().usuario == usuario
    assert registros.first().detalhes["via"] == "primeiro_acesso"
    assert registros.first().detalhes["papel_atribuido"] == Papel.ADMINISTRADOR


# ---------------------------------------------------------------------------
# Convite — fluxo do segundo funcionário (DE-042 / DL-018 critério 3)
# ---------------------------------------------------------------------------


def test_emitir_convite_exige_convidador_ser_administrador_ativo():
    """Convite não pode ser emitido por ANALISTA ou GESTOR — só
    ADMINISTRADOR. Defesa contra escalada: ANALISTA pode visualizar,
    ADMINISTRADOR promove, mas só ADMINISTRADOR traz gente nova."""
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório A", cnpj="11111111000111")
    convidador = User.objects.create_user(
        username="analista", email="an@dl018.local", password=SENHA
    )
    # Vincula o convidador como ANALISTA, NÃO ADMINISTRADOR.
    VinculoUsuarioEscritorio.objects.create(
        usuario=convidador,
        escritorio=escritorio,
        papel=Papel.ANALISTA,
        ativo=True,
    )

    with pytest.raises(Exception) as excinfo:
        emitir_convite_para_escritorio(
            escritorio=escritorio,
            email_convidado="convidado@dl018.local",
            convidador=convidador,
        )
    assert "ADMINISTRADOR" in str(excinfo.value).upper()


def test_emitir_convite_sucesso_quando_convidador_e_admin():
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório B", cnpj="22222222000122")
    convidador = User.objects.create_user(username="admin", email="ad@dl018.local", password=SENHA)
    VinculoUsuarioEscritorio.objects.create(
        usuario=convidador,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )

    convite = emitir_convite_para_escritorio(
        escritorio=escritorio,
        email_convidado="convidado@dl018.local",
        convidador=convidador,
    )

    assert convite.escritorio == escritorio
    assert convite.email == "convidado@dl018.local"
    assert convite.papel_inicial == Papel.ANALISTA
    assert convite.emitido_por == convidador
    assert len(convite.token) == 32  # 32 chars base64-url
    assert not convite.consumido_em


def test_emitir_convite_gera_registro_de_auditoria():
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório C", cnpj="33333333000133")
    convidador = User.objects.create_user(
        username="admin2", email="ad2@dl018.local", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=convidador,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )

    convite = emitir_convite_para_escritorio(
        escritorio=escritorio,
        email_convidado="c@dl018.local",
        convidador=convidador,
    )

    assert (
        RegistroAuditoria.objects.filter(
            acao="convite.escritorio.emitido",
            detalhes__convite_id=convite.id,
        ).count()
        == 1
    )


# ---------------------------------------------------------------------------
# Aceitar convite — vínculo criado (DE-042 / DL-018 critério 3)
# ---------------------------------------------------------------------------


def test_aceitar_convite_cria_vinculo_para_convidado_autenticado():
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório D", cnpj="44444444000144")
    admin = User.objects.create_user(username="admin3", email="ad3@dl018.local", password=SENHA)
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )
    convite = emitir_convite_para_escritorio(
        escritorio=escritorio,
        email_convidado="convidado-d@dl018.local",
        convidador=admin,
    )

    # O "convidado" agora tem usuário e sessão autenticada.
    convidado = User.objects.create_user(
        username="convidado-d", email="convidado-d@dl018.local", password=SENHA
    )

    resultado = aceitar_convite_e_criar_vinculo(token=convite.token, usuario=convidado)

    assert resultado.vinculo.usuario == convidado
    assert resultado.vinculo.escritorio == escritorio
    assert resultado.vinculo.papel == Papel.ANALISTA
    assert resultado.vinculo.ativo is True

    # O convite foi consumido.
    convite.refresh_from_db()
    assert convite.consumido_por == convidado
    assert convite.consumido_em is not None


def test_aceitar_convite_recusa_token_inexistente():
    User = get_user_model()
    convidado = User.objects.create_user(
        username="convidado-x", email="x@dl018.local", password=SENHA
    )

    with pytest.raises(Exception) as excinfo:
        aceitar_convite_e_criar_vinculo(token="token-falso-que-nao-existe", usuario=convidado)
    assert "inexistente" in str(excinfo.value).lower() or "consumido" in str(excinfo.value).lower()


def test_aceitar_convite_recusa_token_ja_consumido():
    """Convite é de uso único: depois de consumido, não pode ser
    reapresentado. Defesa contra compartilhamento não-intencional
    de link."""
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório E", cnpj="55555555000155")
    admin = User.objects.create_user(username="admin4", email="ad4@dl018.local", password=SENHA)
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )
    convite = emitir_convite_para_escritorio(
        escritorio=escritorio,
        email_convidado="segundo-convidado@dl018.local",
        convidador=admin,
    )

    primeiro = User.objects.create_user(
        username="primeiro-convidado", email="primeiro-convidado@dl018.local", password=SENHA
    )
    aceitar_convite_e_criar_vinculo(token=convite.token, usuario=primeiro)

    # Um segundo usuário (ou o mesmo) tentando usar o mesmo token — recusa.
    segundo = User.objects.create_user(
        username="segundo-convidado", email="segundo-convidado@dl018.local", password=SENHA
    )
    with pytest.raises(Exception) as excinfo:
        aceitar_convite_e_criar_vinculo(token=convite.token, usuario=segundo)
    assert "inexistente" in str(excinfo.value).lower() or "consumido" in str(excinfo.value).lower()


# ---------------------------------------------------------------------------
# Views: usuário sem vínculo vê "Primeiro acesso" no painel e na bootstrap.
# ---------------------------------------------------------------------------


def test_painel_tem_link_bootstrap_quando_sem_vinculo(client):
    """Critério 1 (parte do painel): o caminho para o bootstrap aparece
    no painel quando o usuário não tem escritório. Defesa: o link só
    é renderizado no painel quando `escritorios` é vazio — não há
    como chegar no formulário por engano."""
    User = get_user_model()
    User.objects.create_user(username="painel", email="painel@dl018.local", password=SENHA)
    assert client.login(username="painel", password=SENHA)
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "bootstrap" in html.lower() or "primeiro escritório" in html.lower()


def test_painel_nao_tem_link_bootstrap_quando_ha_vinculo(client):
    """Controle positivo: usuário com vínculo NÃO vê o link de
    bootstrap — ele tem escritório, e o bootstrap não é para ele."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="com-vinculo", email="cv@dl018.local", password=SENHA
    )
    escritorio = Escritorio.objects.create(nome="Escritório F", cnpj="66666666000166")
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )
    assert client.login(username="com-vinculo", password=SENHA)
    resposta = client.get(reverse("tenancy:painel"))
    assert resposta.status_code == 200
    html = resposta.content.decode()
    assert "Criar o primeiro escritório" not in html


def test_bootstrap_post_cria_escritorio_e_redireciona_para_painel(client):
    """Critério 1 (parte final): usuário sem vínculo preenche o
    formulário, POSTA, e cai no painel já com escritório."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="bootstrap-post", email="bp@dl018.local", password=SENHA
    )
    assert client.login(username="bootstrap-post", password=SENHA)

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Escritório Bootstrap", "cnpj": "77777777000177"},
    )
    assert resposta.status_code == 302, (
        f"bootstrap POST deveria redirecionar; recebi {resposta.status_code}"
    )
    assert resposta["Location"] == reverse("tenancy:painel")

    usuario.refresh_from_db()
    vinculos = VinculoUsuarioEscritorio.objects.filter(usuario=usuario, ativo=True)
    assert vinculos.count() == 1
    assert vinculos.first().escritorio.nome == "Escritório Bootstrap"
    assert vinculos.first().papel == Papel.ADMINISTRADOR


def test_bootstrap_post_com_vinculo_ativo_redireciona_para_painel_sem_criar_nada(
    client,
):
    """Controle positivo: usuário com vínculo NÃO pode usar o bootstrap.
    Defesa contra "duas abas" — o segundo POST cai no painel com
    mensagem, sem criar segundo escritório."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="bootstrap-ja-vinculado", email="bjv@dl018.local", password=SENHA
    )
    escritorio = Escritorio.objects.create(nome="Escritório G", cnpj="88888888000188")
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )
    assert client.login(username="bootstrap-ja-vinculado", password=SENHA)

    total_antes = Escritorio.objects.count()
    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Escritório H", "cnpj": "99999999000199"},
    )
    assert resposta.status_code == 302
    assert resposta["Location"] == reverse("tenancy:painel")
    assert Escritorio.objects.count() == total_antes, "um segundo escritório foi criado!"


# ---------------------------------------------------------------------------
# Critério 4: isolamento entre escritórios continua provado.
# ---------------------------------------------------------------------------


def test_vinculo_de_um_escritorio_nao_da_acesso_a_outro(client):
    """Bootstrap cria escritório E vínculo; o usuário NÃO pode, em
    sequência, manipular outro escritório que não seja o dele.
    O teste da DL-015/test_isolamento continua valendo; aqui
    garantimos que a criação de escritório NÃO mudou nada."""
    User = get_user_model()
    usuario = User.objects.create_user(
        username="bootstrap-isolado", email="bi@dl018.local", password=SENHA
    )
    criar_primeiro_escritorio_e_vinculo_admin(
        usuario=usuario, nome="Escritório I", cnpj="10101010000101"
    )

    # Outro escritório, sem o usuário ter vínculo.
    Escritorio.objects.create(nome="Outro Escritório", cnpj="20202020000102")

    assert client.login(username="bootstrap-isolado", password=SENHA)
    resposta = client.get(reverse("tenancy:api-escritorios"))
    # O usuário só vê o seu próprio escritório (um).
    import json

    dados = json.loads(resposta.content)
    assert len(dados) == 1
    assert dados[0]["nome"] == "Escritório I"


# ---------------------------------------------------------------------------
# Critério BL-218 — views exercitadas por POST real
# ---------------------------------------------------------------------------
#
# As três views da DL-018 são cobertas por testes de service (acima)
# E por testes de view via `client.post` (estes). Os testes de view
# são os que alimentam o elo de execução da BL-218 — uma chamada
# direta ao service não põe o quadro da view na pilha, e a BL-218
# reporta a superfície como não-exercitada.


def test_emitir_convite_por_view_chama_recusar_dado_nao_contratado(client):
    """BL-218: o handler POST do `emitir_convite` chega a
    `apps.core.requisicao.recusar_dado_nao_contratado`. O elo de
    execução da BL-218 confere essa trajetória na
    `pytest_sessionfinish`."""
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório BL218", cnpj="77777777000177")
    admin = User.objects.create_user(
        username="admin-bl218-emitir", email="abe@dl018.local", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )

    assert client.login(username="admin-bl218-emitir", password=SENHA)
    resposta = client.post(
        reverse("tenancy:emitir-convite"),
        {"escritorio_id": escritorio.pk, "email": "convidado-view@dl018.local"},
    )
    assert resposta.status_code == 302
    assert ConviteEscritorio.objects.filter(email="convidado-view@dl018.local").exists()


def test_aceitar_convite_por_view_chama_recusar_dado_nao_contratado(client):
    """BL-218: o handler POST do `aceitar_convite` chega a
    `apps.core.requisicao.recusar_dado_nao_contratado`."""
    User = get_user_model()
    escritorio = Escritorio.objects.create(nome="Escritório Convite", cnpj="88888888000188")
    admin = User.objects.create_user(
        username="admin-bl218-aceitar", email="aba@dl018.local", password=SENHA
    )
    VinculoUsuarioEscritorio.objects.create(
        usuario=admin,
        escritorio=escritorio,
        papel=Papel.ADMINISTRADOR,
        ativo=True,
    )

    convite = emitir_convite_para_escritorio(
        escritorio=escritorio,
        email_convidado="convidado-vista@dl018.local",
        convidador=admin,
    )

    User.objects.create_user(
        username="convidado-vista",
        email="convidado-vista@dl018.local",
        password=SENHA,
    )
    client.logout()
    assert client.login(username="convidado-vista", password=SENHA)

    resposta = client.post(reverse("tenancy:aceitar-convite", kwargs={"token": convite.token}))
    assert resposta.status_code == 302
    convite.refresh_from_db()
    assert convite.consumido_em is not None


def test_bootstrap_primeiro_acesso_por_view_chama_recusar_dado_nao_contratado(
    client,
):
    """BL-218: o handler POST do `bootstrap_primeiro_acesso` chega a
    `apps.core.requisicao.recusar_dado_nao_contratado`."""
    User = get_user_model()
    User.objects.create_user(username="bootstrap-bl218", email="bb@dl018.local", password=SENHA)
    assert client.login(username="bootstrap-bl218", password=SENHA)

    resposta = client.post(
        reverse("tenancy:bootstrap-primeiro-acesso"),
        {"nome": "Outro Escritório", "cnpj": "99999999000199"},
    )
    assert resposta.status_code == 302
