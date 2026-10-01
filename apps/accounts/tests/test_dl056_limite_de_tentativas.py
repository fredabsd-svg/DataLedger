"""DL-056 — limite de tentativas no login e no cadastro de escritório.

Critérios de aceite do plano (docs/planos/DL-056, nível 2):

1. N falhas -> a próxima tentativa, mesmo com a senha certa, é recusada até a
   janela passar; depois da janela, é aceita.
2. O limite por IP vale entre usuários diferentes.
3. A mensagem é idêntica para usuário existente e inexistente.
4. Cadastro acima do limite por IP é recusado sem criar nada.
5. Migração aplica e reverte (verificada por comando, registrada na entrega).

O relógio é controlado por `limite_tentativas._agora`; o banco é o PostgreSQL
real (a concorrência só significa algo com duas conexões de verdade). Todos os
dados são sintéticos.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.accounts import limite_tentativas
from apps.accounts.models import TentativaDeAcesso
from apps.auditoria.models import RegistroAuditoria
from apps.tenancy.models import Escritorio

pytestmark = pytest.mark.django_db

SENHA = "senha-forte-123"
IP_A = "203.0.113.10"
IP_B = "203.0.113.20"
T0 = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)


class Relogio:
    """Relógio manual: o tempo só anda quando o teste manda."""

    def __init__(self):
        self.agora = T0

    def __call__(self):
        return self.agora

    def avancar(self, **kwargs):
        self.agora += timedelta(**kwargs)


@pytest.fixture
def relogio(monkeypatch):
    r = Relogio()
    monkeypatch.setattr(limite_tentativas, "_agora", r)
    return r


@pytest.fixture
def usuario():
    return get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.example", password=SENHA
    )


def _tentar(usuario_digitado, senha, ip=IP_A, client=None):
    return (client or Client()).post(
        reverse("login"),
        {"username": usuario_digitado, "password": senha},
        REMOTE_ADDR=ip,
    )


def _logou(resposta):
    return resposta.status_code == 302


def _mensagem(resposta):
    return [str(e) for e in resposta.context["form"].non_field_errors()]


# --- Critério 1 -------------------------------------------------------------


def test_n_falhas_bloqueiam_ate_a_janela_passar_mesmo_com_senha_certa(relogio, usuario):
    for _ in range(5):
        assert not _logou(_tentar("ana", "senha-errada"))

    # Sexta tentativa, com a senha CERTA: recusada e sem sessão.
    client = Client()
    bloqueada = _tentar("ana", SENHA, client=client)
    assert not _logou(bloqueada)
    assert "_auth_user_id" not in client.session

    # Um segundo antes de fechar a janela, ainda bloqueado — e essa tentativa
    # bloqueada não pode ter renovado o bloqueio.
    relogio.avancar(minutes=14, seconds=59)
    assert not _logou(_tentar("ana", SENHA))

    relogio.avancar(seconds=2)
    client = Client()
    assert _logou(_tentar("ana", SENHA, client=client))
    assert "_auth_user_id" in client.session


def test_quarta_falha_ainda_nao_bloqueia_e_a_quinta_sim(relogio, usuario):
    for _ in range(4):
        _tentar("ana", "senha-errada")
    assert _logou(_tentar("ana", SENHA))  # 5ª tentativa: ainda permitida (limite é 5 falhas)

    # Sucesso zerou: 5 falhas novas são necessárias para bloquear de novo.
    for _ in range(5):
        _tentar("ana", "senha-errada")
    assert not _logou(_tentar("ana", SENHA))


def test_sucesso_zera_o_contador_do_usuario(relogio, usuario):
    for _ in range(4):
        _tentar("ana", "senha-errada")
    assert _logou(_tentar("ana", SENHA))
    assert not TentativaDeAcesso.objects.filter(escopo="login_usuario").exists()

    # Sem o zeramento, estas 4 falhas somariam 8 e a última entrada seria barrada.
    for _ in range(4):
        _tentar("ana", "senha-errada")
    assert _logou(_tentar("ana", SENHA))


def test_tentativa_bloqueada_nao_grava_nem_renova_o_bloqueio(relogio, usuario):
    for _ in range(5):
        _tentar("ana", "senha-errada")
    antes = TentativaDeAcesso.objects.count()
    for _ in range(10):
        _tentar("ana", "senha-errada")
    assert TentativaDeAcesso.objects.count() == antes


def test_variacao_de_caixa_e_espacos_cai_no_mesmo_balde(relogio, usuario):
    for digitado in ["ana", "ANA", " Ana ", "aNa", "ana"]:
        _tentar(digitado, "senha-errada")
    assert not _logou(_tentar("ana", SENHA))


def test_limite_por_usuario_e_por_usuario_digitado_nao_global(relogio, usuario):
    get_user_model().objects.create_user(username="bia", email="bia@x.example", password=SENHA)
    for _ in range(5):
        _tentar("ana", "senha-errada")
    assert _logou(_tentar("bia", SENHA))


def test_limites_vem_de_settings(relogio, usuario, settings):
    settings.LIMITE_TENTATIVAS_LOGIN_POR_USUARIO = 2
    settings.LIMITE_TENTATIVAS_LOGIN_JANELA_SEGUNDOS = 60
    _tentar("ana", "senha-errada")
    _tentar("ana", "senha-errada")
    assert not _logou(_tentar("ana", SENHA))
    relogio.avancar(seconds=61)
    assert _logou(_tentar("ana", SENHA))


def test_envio_sem_senha_nao_consome_tentativa(relogio, usuario):
    for _ in range(10):
        Client().post(reverse("login"), {"username": "ana", "password": ""}, REMOTE_ADDR=IP_A)
    assert not TentativaDeAcesso.objects.exists()
    assert _logou(_tentar("ana", SENHA))


# --- Critério 2 -------------------------------------------------------------


def test_limite_por_ip_vale_entre_usuarios_diferentes(relogio, usuario):
    # 20 falhas de IP_A, cada uma contra um usuário diferente (nenhum chega a 5).
    for i in range(20):
        assert not _logou(_tentar(f"alvo-{i}", "senha-errada", ip=IP_A))

    # A 21ª tentativa do mesmo IP, contra outro usuário e com senha certa: bloqueada.
    assert not _logou(_tentar("ana", SENHA, ip=IP_A))
    # Outro IP não é afetado.
    assert _logou(_tentar("ana", SENHA, ip=IP_B))

    # Passada a janela, o IP volta.
    relogio.avancar(minutes=15, seconds=1)
    assert _logou(_tentar("ana", SENHA, ip=IP_A))


def test_sucessos_nao_consomem_o_limite_do_ip(relogio):
    # Um escritório inteiro atrás do mesmo NAT entrando com sucesso não se bloqueia.
    for i in range(25):
        get_user_model().objects.create_user(
            username=f"u{i}", email=f"u{i}@x.example", password=SENHA
        )
        assert _logou(_tentar(f"u{i}", SENHA, ip=IP_A))


# --- Critério 3 -------------------------------------------------------------


def test_mensagem_identica_para_existente_inexistente_e_bloqueado(relogio, usuario):
    errada_existente = _tentar("ana", "senha-errada", ip=IP_B)
    errada_inexistente = _tentar("fantasma", "senha-errada", ip=IP_B)
    for _ in range(5):
        _tentar("ana", "senha-errada")
        _tentar("fantasma", "senha-errada")
    bloqueada_existente = _tentar("ana", SENHA)
    bloqueada_inexistente = _tentar("fantasma", SENHA)

    respostas = [errada_existente, errada_inexistente, bloqueada_existente, bloqueada_inexistente]
    assert {r.status_code for r in respostas} == {200}
    mensagens = [_mensagem(r) for r in respostas]
    assert mensagens[0], "a mensagem de login inválido precisa existir"
    assert all(m == mensagens[0] for m in mensagens), mensagens


def test_bloqueio_por_ip_tem_a_mesma_mensagem(relogio, usuario):
    normal = _tentar("ana", "senha-errada", ip=IP_B)
    for i in range(20):
        _tentar(f"alvo-{i}", "senha-errada", ip=IP_A)
    por_ip = _tentar("ana", SENHA, ip=IP_A)
    assert _mensagem(por_ip) == _mensagem(normal)


# --- Trilha e dado sensível -------------------------------------------------


def test_bloqueio_na_trilha_sem_senha_nem_texto_digitado(relogio):
    digitado = "texto-secreto-no-campo-de-usuario"
    senha = "senha-digitada-que-nao-pode-vazar"
    for _ in range(5):
        _tentar(digitado, senha)
    _tentar(digitado, senha)  # bloqueada

    registro = RegistroAuditoria.objects.get(acao="login.bloqueado")
    assert registro.endereco_ip == IP_A
    assert registro.detalhes["motivo"] == "usuario"
    assert registro.detalhes["usuario_hash"]
    assert digitado not in str(registro.detalhes)
    assert senha not in str(registro.detalhes)

    # Nem no contador: a chave é um hash, nunca o texto.
    for linha in TentativaDeAcesso.objects.all():
        assert digitado not in linha.chave
        assert senha not in linha.chave
    # E o bloqueio não gera o registro `login.falha` (que guarda o usuário
    # digitado — BL-555/B3): só as 5 falhas reais geraram.
    assert RegistroAuditoria.objects.filter(acao="login.falha").count() == 5


def test_bloqueio_por_ip_registra_motivo_ip(relogio):
    for i in range(20):
        _tentar(f"alvo-{i}", "x")
    _tentar("qualquer", "x")
    assert RegistroAuditoria.objects.get(acao="login.bloqueado").detalhes["motivo"] == "ip"


# --- Critério 4: cadastro ---------------------------------------------------


def _cnpj_valido(base12: str) -> str:
    def dv(digitos, pesos):
        resto = sum(int(d) * p for d, p in zip(digitos, pesos, strict=True)) % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = dv(base12, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    d2 = dv(base12 + d1, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return base12 + d1 + d2


def _dados_cadastro(n: int) -> dict:
    return {
        "nome": "Pessoa de Teste",
        "email": f"cadastro{n}@example.com",
        "nome_escritorio": f"Escritório Sintético {n}",
        "cnpj": _cnpj_valido(f"{10000000 + n:08d}0001"),
        "password1": "UmaSenha!Forte987",
        "password2": "UmaSenha!Forte987",
    }


def _cadastrar(n, ip=IP_A):
    return Client().post(reverse("cadastro"), _dados_cadastro(n), REMOTE_ADDR=ip)


def test_cadastro_acima_do_limite_por_ip_e_recusado_sem_criar_nada(relogio):
    for n in range(5):
        assert _cadastrar(n).status_code == 302
    usuarios, escritorios = get_user_model().objects.count(), Escritorio.objects.count()
    assert (usuarios, escritorios) == (5, 5)
    vinculos = RegistroAuditoria.objects.filter(acao="escritorio.criado_por_bootstrap").count()

    client = Client()
    resposta = client.post(reverse("cadastro"), _dados_cadastro(99), REMOTE_ADDR=IP_A)

    assert resposta.status_code == 429
    assert resposta["Retry-After"] == "3600"
    assert "Muitos cadastros" in resposta.content.decode()
    assert get_user_model().objects.count() == usuarios
    assert Escritorio.objects.count() == escritorios
    assert not get_user_model().objects.filter(email="cadastro99@example.com").exists()
    assert "_auth_user_id" not in client.session
    assert (
        RegistroAuditoria.objects.filter(acao="escritorio.criado_por_bootstrap").count() == vinculos
    )
    registro = RegistroAuditoria.objects.get(acao="cadastro.bloqueado")
    assert "cadastro99" not in str(registro.detalhes)

    # Outro IP não é afetado; e, passada a janela, o IP volta.
    assert _cadastrar(100, ip=IP_B).status_code == 302
    relogio.avancar(hours=1, seconds=1)
    assert _cadastrar(101, ip=IP_A).status_code == 302


def test_cadastro_invalido_nao_consome_o_limite(relogio):
    for n in range(10):
        dados = _dados_cadastro(n)
        dados["password2"] = "diferente"
        assert Client().post(reverse("cadastro"), dados, REMOTE_ADDR=IP_A).status_code == 400
    assert not TentativaDeAcesso.objects.exists()
    assert _cadastrar(50).status_code == 302


def test_cadastro_repetido_com_mesmo_email_nao_consome_o_limite(relogio):
    assert _cadastrar(1).status_code == 302
    for _ in range(10):
        assert _cadastrar(1).status_code == 400  # e-mail/CNPJ já em uso
    assert TentativaDeAcesso.objects.filter(escopo="cadastro_ip").count() == 1


def test_limite_de_cadastro_vem_de_settings(relogio, settings):
    settings.LIMITE_TENTATIVAS_CADASTRO_POR_IP = 1
    assert _cadastrar(1).status_code == 302
    assert _cadastrar(2).status_code == 429


# --- IP único da trilha (DL-057) e IP desconhecido (achado O2) ---------------------
#
# O limite lê o IP por `apps.auditoria.ip.ip_do_cliente`, a mesma função da trilha.
# Quando ela devolve `None` (sem `REMOTE_ADDR` válido), NÃO há limite por IP — só o
# por usuário. Agrupar os `None` numa chave só bloquearia o login de todos.

PROXY = "10.0.0.1"
SEM_IP = ["", "isto-nao-e-ip"]


@pytest.mark.parametrize("sem_ip", SEM_IP)
def test_sem_ip_o_limite_por_usuario_continua_valendo(relogio, usuario, sem_ip):
    for _ in range(5):
        assert not _logou(_tentar("ana", "senha-errada", ip=sem_ip))

    assert not _logou(_tentar("ana", SENHA, ip=sem_ip))  # 6ª, com a senha certa
    relogio.avancar(minutes=15, seconds=1)
    assert _logou(_tentar("ana", SENHA, ip=sem_ip))


@pytest.mark.parametrize("sem_ip", SEM_IP)
def test_sem_ip_nao_ha_balde_global_que_bloqueie_todo_mundo(relogio, usuario, sem_ip):
    # 25 falhas de usuários diferentes, todas sem IP: com a chave única para
    # `None` isso passaria dos 20 do limite por IP e travaria o acesso de todos.
    for i in range(25):
        assert not _logou(_tentar(f"alvo-{i}", "senha-errada", ip=sem_ip))

    assert _logou(_tentar("ana", SENHA, ip=sem_ip))
    assert not TentativaDeAcesso.objects.filter(escopo="login_ip").exists()
    # A chave de IP nunca vira texto fixo ("None", "desconhecido"...).
    assert not TentativaDeAcesso.objects.exclude(escopo="login_usuario").exists()


def test_reserva_sem_ip_so_tem_a_linha_do_usuario(relogio):
    request = RequestFactory().post("/entrar/", REMOTE_ADDR="")

    reserva, motivo = limite_tentativas.reservar_tentativa_de_login(request, "ana")

    assert motivo == ""
    assert reserva.ids_ip == ()
    assert TentativaDeAcesso.objects.count() == 1
    # Sucesso sem IP não tenta devolver reserva de IP que não existe.
    limite_tentativas.confirmar_sucesso_de_login(reserva)
    assert TentativaDeAcesso.objects.count() == 0


def test_bloqueio_por_usuario_sem_ip_vai_para_a_trilha_sem_ip(relogio, usuario):
    for _ in range(5):
        _tentar("ana", "senha-errada", ip="")

    _tentar("ana", SENHA, ip="")

    registro = RegistroAuditoria.objects.get(acao="login.bloqueado")
    assert registro.endereco_ip is None
    assert registro.detalhes["motivo"] == "usuario"


@pytest.mark.parametrize("sem_ip", SEM_IP)
def test_cadastro_sem_ip_nao_e_limitado_nem_agrupado(relogio, sem_ip):
    # Mais cadastros que o limite (5) sem IP conhecido: nenhum é recusado, e
    # nenhum balde de IP é criado para o `None`.
    for n in range(7):
        assert _cadastrar(n, ip=sem_ip).status_code == 302
    assert not TentativaDeAcesso.objects.exists()
    # Quem tem IP conhecido continua limitado.
    for n in range(10, 15):
        assert _cadastrar(n, ip=IP_A).status_code == 302
    assert _cadastrar(99, ip=IP_A).status_code == 429


def _pelo_proxy(usuario_digitado, senha, cliente):
    return Client().post(
        reverse("login"),
        {"username": usuario_digitado, "password": senha},
        REMOTE_ADDR=PROXY,
        HTTP_X_FORWARDED_FOR=cliente,
    )


def test_atras_de_proxy_confiavel_o_balde_e_o_ip_do_cliente_e_nao_o_do_proxy(relogio, settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]
    get_user_model().objects.create_user(username="bia", email="bia@x.example", password=SENHA)
    for i in range(20):
        _pelo_proxy(f"alvo-{i}", "senha-errada", IP_A)

    # O cliente A estourou o limite; o cliente B, atrás do MESMO proxy, não.
    assert not _logou(_pelo_proxy("bia", SENHA, IP_A))
    assert _logou(_pelo_proxy("bia", SENHA, IP_B))
    chaves = TentativaDeAcesso.objects.filter(escopo="login_ip").values_list("chave", flat=True)
    assert PROXY not in set(chaves)
    assert IP_A in set(chaves)


def test_sem_proxy_confiavel_cabecalho_forjado_nao_escolhe_o_balde(relogio, usuario, settings):
    settings.PROXIES_CONFIAVEIS = []
    for i in range(20):
        Client().post(
            reverse("login"),
            {"username": f"alvo-{i}", "password": "senha-errada"},
            REMOTE_ADDR=IP_A,
            HTTP_X_FORWARDED_FOR=f"198.51.100.{i + 1}",  # atacante troca o cabeçalho
        )

    # Continua o mesmo balde (o par TCP), então a 21ª é bloqueada.
    assert not _logou(_tentar("ana", SENHA, ip=IP_A))


# --- Limpeza oportunista ----------------------------------------------------


def test_limpeza_apaga_so_o_vencido_e_respeita_o_lote(relogio, monkeypatch):
    velho = T0 - timedelta(hours=2)
    TentativaDeAcesso.objects.bulk_create(
        [
            TentativaDeAcesso(escopo="login_ip", chave="198.51.100.1", registrado_em=velho)
            for _ in range(10)
        ]
    )
    recente = TentativaDeAcesso.objects.create(
        escopo="login_ip", chave="198.51.100.2", registrado_em=T0 - timedelta(minutes=5)
    )

    monkeypatch.setattr(limite_tentativas, "LOTE_DE_LIMPEZA", 4)
    assert limite_tentativas.limpar_vencidas() == 4
    assert TentativaDeAcesso.objects.filter(registrado_em=velho).count() == 6

    monkeypatch.setattr(limite_tentativas, "LOTE_DE_LIMPEZA", 500)
    assert limite_tentativas.limpar_vencidas() == 6
    assert list(TentativaDeAcesso.objects.all()) == [recente]


def test_reserva_limpa_vencidas_sem_tarefa_em_segundo_plano(relogio, usuario):
    TentativaDeAcesso.objects.create(
        escopo="login_ip", chave="198.51.100.9", registrado_em=T0 - timedelta(hours=3)
    )
    _tentar("ana", "senha-errada")
    assert not TentativaDeAcesso.objects.filter(chave="198.51.100.9").exists()


def test_limpeza_nao_apaga_o_que_a_janela_do_cadastro_ainda_enxerga(relogio):
    # 50 minutos: vencido para o login (15 min), mas dentro da janela de 1 h do cadastro.
    TentativaDeAcesso.objects.create(
        escopo="cadastro_ip", chave=IP_A, registrado_em=T0 - timedelta(minutes=50)
    )
    limite_tentativas.limpar_vencidas()
    assert TentativaDeAcesso.objects.filter(escopo="cadastro_ip").count() == 1


# --- Concorrência (duas ou mais conexões reais) ----------------------------


def _disparar_em_paralelo(alvo, quantidade):
    from django.db import connection

    barreira = threading.Barrier(quantidade, timeout=10)
    resultados, erros = [], []

    def executar():
        try:
            barreira.wait()
            resultados.append(alvo())
        except Exception as exc:  # o teste reprova pelas asserções abaixo
            erros.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=executar) for _ in range(quantidade)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "thread travada: possível deadlock"
    assert not erros, erros
    return resultados


@pytest.mark.django_db(transaction=True)
def test_duas_conexoes_nao_passam_do_limite_em_mais_de_uma(relogio):
    request = RequestFactory().post("/login/", REMOTE_ADDR=IP_A)
    # 4 tentativas já reservadas: sobra exatamente 1 vaga.
    for _ in range(4):
        limite_tentativas.reservar_tentativa_de_login(request, "ana")

    resultados = _disparar_em_paralelo(
        lambda: limite_tentativas.reservar_tentativa_de_login(request, "ana")[0] is not None, 2
    )

    assert sorted(resultados) == [False, True], resultados
    assert TentativaDeAcesso.objects.filter(escopo="login_usuario").count() == 5


@pytest.mark.django_db(transaction=True)
def test_varias_conexoes_nunca_reservam_alem_do_limite(relogio):
    request = RequestFactory().post("/login/", REMOTE_ADDR=IP_A)
    resultados = _disparar_em_paralelo(
        lambda: limite_tentativas.reservar_tentativa_de_login(request, "ana")[0] is not None, 8
    )
    assert sum(resultados) == 5, resultados
    assert TentativaDeAcesso.objects.filter(escopo="login_usuario").count() == 5


@pytest.mark.django_db(transaction=True)
def test_cadastros_concorrentes_nao_passam_do_limite(relogio):
    request = RequestFactory().post("/cadastro/", REMOTE_ADDR=IP_A)
    resultados = _disparar_em_paralelo(lambda: limite_tentativas.reservar_cadastro(request), 8)
    assert sum(resultados) == 5, resultados
