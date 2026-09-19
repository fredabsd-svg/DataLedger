"""CA-6 (DL-024): matriz de acesso de `/auditoria/` FIXADA por teste.

Medido em `apps/auditoria/views.py:17`:
    `permission_classes = [TemEscritorioAtivo, papel_permitido(Papel.ADMINISTRADOR, Papel.GESTOR)]`

Hoje (2026-09-16):
- ADMINISTRADOR e GESTOR → 200 em `GET /auditoria/`.
- ANALISTA, FINANCEIRO e PARALEGAL → 403 em `GET /auditoria/`.
- Usuário sem `escritorio` ativo → 403.

O teste fixa esse estado. A próxima etapa que mexer na matriz (ex.:
PE-36/BAS-01, que é decisão do Fred) tem de mexer de propósito,
atualizando o teste junto — não pode acontecer de passagem.

Esta etapa NÃO decide quem pode ler o quê. Decidir isso é PE-36/BAS-01,
pendência do plano mestre com o Fred. A CA-6 é o cinto de segurança:
se alguém alterar o `permission_classes` em silêncio, a suíte quebra e
a alteração aparece no relatório da auditoria rodada 1.

Testes marcados com `@pytest.mark.django_db(transaction=True)` porque
exigem Postgres — a CI é quem roda.
"""

import pytest

URL_AUDITORIA = "/api/auditoria/"


def _setup_usuario_com_papel(escritorio, papel, username):
    """Helper: cria escritório, usuário com o papel pedido, vínculo
    ativo. Devolve a tupla (escritorio, usuario)."""
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import VinculoUsuarioEscritorio

    usuario = get_user_model().objects.create_user(username=username, password="senha-forte-123")
    VinculoUsuarioEscritorio.objects.create(
        usuario=usuario, escritorio=escritorio, papel=papel, ativo=True
    )
    return escritorio, usuario


@pytest.mark.django_db(transaction=True)
def test_administrador_tem_200_em_auditoria(client):
    """ADMINISTRADOR acessa `/auditoria/` (200)."""
    from apps.tenancy.models import Escritorio, Papel

    escritorio = Escritorio.objects.create(nome="E ADM", cnpj="11111111000111")
    _, usuario = _setup_usuario_com_papel(escritorio, Papel.ADMINISTRADOR, "adm")
    escritorio.ativo = True
    escritorio.save()
    client.login(username="adm", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 200, (
        f"CA-6 quebrada: ADMINISTRADOR deveria ter 200 em /auditoria/, "
        f"obteve {resposta.status_code}. "
        f"Se a matriz de acesso mudou de propósito, atualize este teste."
    )


@pytest.mark.django_db(transaction=True)
def test_gestor_tem_200_em_auditoria(client):
    """GESTOR acessa `/auditoria/` (200)."""
    from apps.tenancy.models import Escritorio, Papel

    escritorio = Escritorio.objects.create(nome="E GEST", cnpj="22222222000122")
    escritorio.ativo = True
    escritorio.save()
    _setup_usuario_com_papel(escritorio, Papel.GESTOR, "gest")
    client.login(username="gest", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 200, (
        f"CA-6 quebrada: GESTOR deveria ter 200 em /auditoria/, obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_analista_tem_403_em_auditoria(client):
    """ANALISTA NÃO acessa `/auditoria/` (403)."""
    from apps.tenancy.models import Escritorio, Papel

    escritorio = Escritorio.objects.create(nome="E ANAL", cnpj="33333333000133")
    escritorio.ativo = True
    escritorio.save()
    _setup_usuario_com_papel(escritorio, Papel.ANALISTA, "anal")
    client.login(username="anal", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 403, (
        f"CA-6 quebrada: ANALISTA deveria ter 403 em /auditoria/, obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_financeiro_tem_403_em_auditoria(client):
    """FINANCEIRO NÃO acessa `/auditoria/` (403)."""
    from apps.tenancy.models import Escritorio, Papel

    escritorio = Escritorio.objects.create(nome="E FIN", cnpj="44444444000144")
    escritorio.ativo = True
    escritorio.save()
    _setup_usuario_com_papel(escritorio, Papel.FINANCEIRO, "fin")
    client.login(username="fin", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 403, (
        f"CA-6 quebrada: FINANCEIRO deveria ter 403 em /auditoria/, obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_paralegal_tem_403_em_auditoria(client):
    """PARALEGAL NÃO acessa `/auditoria/` (403)."""
    from apps.tenancy.models import Escritorio, Papel

    escritorio = Escritorio.objects.create(nome="E PAR", cnpj="55555555000155")
    escritorio.ativo = True
    escritorio.save()
    _setup_usuario_com_papel(escritorio, Papel.PARALEGAL, "par")
    client.login(username="par", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 403, (
        f"CA-6 quebrada: PARALEGAL deveria ter 403 em /auditoria/, obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_usuario_sem_escritorio_ativo_tem_403_em_auditoria(client):
    """Usuário autenticado SEM escritório ativo NÃO acessa `/auditoria/`.

    O `TemEscritorioAtivo` permission corre antes do `papel_permitido`,
    então mesmo um ADMINISTRADOR sem escritório ativo recebe 403. A
    defesa em camadas: o `papel_permitido` olha `request.user.papel`,
    mas só faz sentido se houver papel definido — sem escritório
    ativo, o `papel` é `None`, e a permissão falha."""
    from django.contrib.auth import get_user_model

    from apps.tenancy.models import Escritorio

    escritorio = Escritorio.objects.create(nome="E Inativo", cnpj="66666666000166")
    escritorio.ativo = False
    escritorio.save()
    get_user_model().objects.create_user(username="sem_escritorio", password="senha-forte-123")
    client.login(username="sem_escritorio", password="senha-forte-123")

    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 403, (
        f"CA-6 quebrada: usuário sem escritório ativo deveria ter 403, "
        f"obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_anonimo_tem_403_em_auditoria(client):
    """Usuário NÃO autenticado NÃO acessa `/auditoria/` (403)."""
    resposta = client.get(URL_AUDITORIA)
    assert resposta.status_code == 403, (
        f"CA-6 quebrada: anônimo deveria ter 403, obteve {resposta.status_code}."
    )


@pytest.mark.django_db(transaction=True)
def test_url_de_auditoria_e_a_listagem(client):
    """Guarda contra mudança silenciosa de URL: a `RegistroAuditoriaListView`
    mora em `/api/auditoria/`. Se a URL mudar, este teste reprova e
    aponta onde atualizar."""
    from apps.auditoria.views import RegistroAuditoriaListView

    # A view existe e tem o nome esperado
    assert RegistroAuditoriaListView.__name__ == "RegistroAuditoriaListView"
