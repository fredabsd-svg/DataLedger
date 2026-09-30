"""DL-052 — decisão do Fred (30/09/2026): usuário se DESATIVA, não se apaga.

O admin do Django não oferece exclusão de usuário (nem individual nem em massa,
nem para superusuário); desativar (`is_active=False`) continua funcionando e
o usuário desativado não entra. A autoria de lançamento e de fechamento de
competência é `PROTECT` no ORM (testada também em
`apps/contabilidade/tests/test_dl052_invariantes_no_banco.py`). Dados sintéticos.
"""

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.urls import reverse

from apps.contabilidade.models import Competencia, Conta, NaturezaConta, TipoConta, TipoPartida
from apps.contabilidade.services import criar_lancamento, encerrar_competencia
from apps.empresas.models import Empresa
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"


@pytest.fixture
def superusuario(client):
    super_ = get_user_model().objects.create_superuser(
        username="super-dl052", email="super-dl052@escritorio.com.br", password=SENHA
    )
    assert client.login(username="super-dl052", password=SENHA)
    return super_


@pytest.fixture
def colaborador():
    return get_user_model().objects.create_user(
        username="colab-dl052", email="colab-dl052@escritorio.com.br", password=SENHA
    )


def test_admin_nao_abre_a_tela_de_exclusao_do_usuario(client, superusuario, colaborador):
    url = reverse("admin:accounts_usuario_delete", args=[colaborador.pk])

    assert client.get(url).status_code == 403
    assert client.post(url, {"post": "yes"}).status_code == 403
    assert get_user_model().objects.filter(pk=colaborador.pk).exists()


def test_admin_nao_oferece_a_acao_em_massa_excluir_selecionados(client, superusuario, colaborador):
    resposta = client.get(reverse("admin:accounts_usuario_changelist"))

    assert resposta.status_code == 200
    assert "delete_selected" not in resposta.content.decode()

    tentativa = client.post(
        reverse("admin:accounts_usuario_changelist"),
        {"action": "delete_selected", "_selected_action": [colaborador.pk], "post": "yes"},
    )
    assert tentativa.status_code in (200, 302)  # sem ação válida: só volta à lista
    assert get_user_model().objects.filter(pk=colaborador.pk).exists()


def test_admin_nao_mostra_o_botao_excluir_na_tela_do_usuario(client, superusuario, colaborador):
    resposta = client.get(reverse("admin:accounts_usuario_change", args=[colaborador.pk]))

    assert resposta.status_code == 200
    assert reverse("admin:accounts_usuario_delete", args=[colaborador.pk]) not in (
        resposta.content.decode()
    )


def test_desativar_usuario_continua_funcionando_e_ele_nao_entra(client, colaborador):
    superior = get_user_model().objects.create_superuser(
        username="super2-dl052", email="super2-dl052@escritorio.com.br", password=SENHA
    )
    assert client.login(username="super2-dl052", password=SENHA)
    # Campos obrigatórios do formulário do UserAdmin preservados; só `is_active` sai.
    url = reverse("admin:accounts_usuario_change", args=[colaborador.pk])
    dados = {
        "username": colaborador.username,
        "email": colaborador.email,
        "first_name": "",
        "last_name": "",
        "date_joined_0": colaborador.date_joined.strftime("%Y-%m-%d"),
        "date_joined_1": colaborador.date_joined.strftime("%H:%M:%S"),
        # `is_active` ausente = desmarcado.
    }
    resposta = client.post(url, dados)
    assert resposta.status_code == 302, getattr(resposta, "context", None)

    colaborador.refresh_from_db()
    assert colaborador.is_active is False
    assert get_user_model().objects.filter(pk=colaborador.pk).exists()
    client.logout()
    assert client.login(username="colab-dl052", password=SENHA) is False
    assert superior.is_active


def test_usuario_desativado_nao_faz_login_pela_tela(client, colaborador):
    colaborador.is_active = False
    colaborador.save(update_fields=["is_active"])

    resposta = client.post(
        reverse("login"), {"username": "colab-dl052", "password": SENHA}, follow=True
    )

    assert "_auth_user_id" not in client.session
    assert resposta.status_code == 200


def _empresa_com_contas():
    escritorio = Escritorio.objects.create(nome="Escritório usuário 052", cnpj="53535353000153")
    empresa = Empresa.objects.create(
        escritorio=escritorio, razao_social="Empresa usuário 052 Ltda", cnpj="53535353000154"
    )
    caixa = Conta.objects.create(
        empresa=empresa,
        codigo="1",
        nome="Caixa",
        tipo=TipoConta.ATIVO,
        natureza=NaturezaConta.DEVEDORA,
    )
    capital = Conta.objects.create(
        empresa=empresa,
        codigo="2",
        nome="Capital",
        tipo=TipoConta.PATRIMONIO_LIQUIDO,
        natureza=NaturezaConta.CREDORA,
    )
    return empresa, caixa, capital


def test_apagar_usuario_que_escriturou_pelo_orm_e_recusado_e_nada_muda(colaborador):
    empresa, caixa, capital = _empresa_com_contas()
    lancamento = criar_lancamento(
        empresa=empresa,
        data=date(2026, 2, 10),
        historico="Escriturado pelo colaborador",
        itens=[
            {"conta": caixa, "tipo": TipoPartida.DEBITO, "valor": Decimal("1.00")},
            {"conta": capital, "tipo": TipoPartida.CREDITO, "valor": Decimal("1.00")},
        ],
        criado_por=colaborador,
    )

    with pytest.raises(ProtectedError):
        colaborador.delete()

    assert get_user_model().objects.filter(pk=colaborador.pk).exists()
    lancamento.refresh_from_db()
    assert lancamento.criado_por_id == colaborador.pk


def test_apagar_usuario_que_fechou_competencia_e_recusado(colaborador):
    empresa, caixa, capital = _empresa_com_contas()
    encerrar_competencia(empresa=empresa, ano=2026, mes=2, usuario=colaborador)

    with pytest.raises(ProtectedError):
        colaborador.delete()

    competencia = Competencia.objects.get(empresa=empresa, ano=2026, mes=2)
    assert competencia.fechada_por_id == colaborador.pk


def test_apagar_usuario_que_nunca_escriturou_continua_possivel_pelo_orm(colaborador):
    """A proteção é da AUTORIA, não do usuário: quem nunca escriturou, não
    fechou competência nem tem registro protegido não é impedido pelo ORM
    (a exclusão deixa de ser oferecida no admin, que é a porta do produto)."""
    colaborador.delete()

    assert not get_user_model().objects.filter(username="colab-dl052").exists()


# --- rodada 1, D6: PROTECT isolado em cada campo de autoria da RC-144 --------

CAMPOS_DE_AUTORIA = [
    ("contabilidade", "LancamentoContabil", "criado_por"),
    ("contabilidade", "Competencia", "fechada_por"),
    ("contabilidade", "Competencia", "entregue_por"),
    ("auditoria", "RegistroAuditoria", "usuario"),
    ("livro_caixa", "LancamentoCaixa", "criado_por"),
    ("livro_caixa", "DependentesCarneLeaoCliente", "criado_por"),
]


@pytest.mark.parametrize(("app", "modelo", "campo"), CAMPOS_DE_AUTORIA)
def test_d6_os_seis_campos_de_autoria_sao_protect(app, modelo, campo):
    """Metadado do modelo: reverter qualquer um dos seis para SET_NULL reprova."""
    from django.apps import apps
    from django.db.models import PROTECT

    assert apps.get_model(app, modelo)._meta.get_field(campo).remote_field.on_delete is PROTECT


@pytest.mark.parametrize("campo", ["fechada_por", "entregue_por"])
def test_d6_apagar_usuario_autor_da_competencia_e_recusado_sem_depender_da_trilha(
    colaborador, campo
):
    """A `Competencia` é montada por ORM, SEM `encerrar_competencia` e portanto
    sem registro de auditoria: só o `on_delete` do próprio campo segura o usuário."""
    empresa, _caixa, _capital = _empresa_com_contas()
    competencia = Competencia.objects.create(
        empresa=empresa, ano=2026, mes=5, **{campo: colaborador}
    )

    with pytest.raises(ProtectedError):
        colaborador.delete()

    competencia.refresh_from_db()
    assert getattr(competencia, f"{campo}_id") == colaborador.pk
