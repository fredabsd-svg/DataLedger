"""DL-057 (BL-553, nível 1 — trilha de auditoria): IP real atrás de proxy.

Critérios de aceite do plano:

1. Sem proxy confiável, `X-Forwarded-For` forjado é ignorado.
2. Com proxy confiável grava o IP do cliente; em cadeia de proxies, o primeiro
   endereço não confiável a partir da direita.
3. Cabeçalho malformado, IPv6 e espaços: sem erro, IP válido gravado.
4. Toda gravação da trilha usa a função única (varredura por teste).

Dados sintéticos: só endereços de documentação (RFC 5737 / RFC 3849).
"""

import importlib
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ImproperlyConfigured
from django.test import RequestFactory
from django.urls import reverse

from apps.auditoria import ip as modulo_ip
from apps.auditoria.ip import ip_do_cliente
from apps.auditoria.models import RegistroAuditoria
from apps.auditoria.services import registrar

PROXY = "192.0.2.10"
PROXY_2 = "192.0.2.11"
CLIENTE = "198.51.100.7"
FORJADO = "203.0.113.99"


def _request(remoto=PROXY, xff=None):
    extra = {"REMOTE_ADDR": remoto}
    if xff is not None:
        extra["HTTP_X_FORWARDED_FOR"] = xff
    request = RequestFactory().get("/", **extra)
    request.user = AnonymousUser()
    return request


# --- Critério 1: sem proxy confiável o cabeçalho é ignorado -----------------


def test_sem_proxy_confiavel_xff_forjado_e_ignorado(settings):
    settings.PROXIES_CONFIAVEIS = []

    assert ip_do_cliente(_request(remoto=CLIENTE, xff=FORJADO)) == CLIENTE


def test_conexao_de_origem_nao_confiavel_ignora_xff_mesmo_com_lista_preenchida(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    # REMOTE_ADDR não é o proxy: quem pediu pode ter escrito o cabeçalho.
    assert ip_do_cliente(_request(remoto=CLIENTE, xff=FORJADO)) == CLIENTE


# --- Critério 2: com proxy confiável -----------------------------------------


def test_com_proxy_confiavel_grava_o_ip_do_cliente(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    assert ip_do_cliente(_request(xff=CLIENTE)) == CLIENTE


def test_cabecalho_ausente_com_proxy_confiavel_usa_remote_addr(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    assert ip_do_cliente(_request()) == PROXY


def test_cadeia_com_dois_proxies_confiaveis_pega_o_primeiro_nao_confiavel(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY, PROXY_2]

    request = _request(xff=f"{CLIENTE}, {PROXY_2}")

    assert ip_do_cliente(request) == CLIENTE


def test_valor_forjado_a_esquerda_do_cliente_e_descartado(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY, PROXY_2]

    # O cliente mandou um XFF com 203.0.113.99; o primeiro proxy acrescentou o
    # IP do cliente, o segundo acrescentou o do primeiro.
    request = _request(xff=f"{FORJADO}, {CLIENTE}, {PROXY_2}")

    assert ip_do_cliente(request) == CLIENTE


def test_cliente_que_forja_um_proxy_confiavel_na_ponta_esquerda_nao_vence(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    request = _request(xff=f"{PROXY}, {CLIENTE}")

    assert ip_do_cliente(request) == CLIENTE


def test_todos_os_enderecos_confiaveis_vale_o_mais_a_esquerda(settings):
    settings.PROXIES_CONFIAVEIS = ["192.0.2.0/24"]

    assert ip_do_cliente(_request(xff=f"{PROXY_2}, {PROXY}")) == PROXY_2


def test_rede_cidr_ipv4(settings):
    settings.PROXIES_CONFIAVEIS = ["192.0.2.0/24"]

    assert ip_do_cliente(_request(remoto="192.0.2.200", xff=CLIENTE)) == CLIENTE
    # Fora da rede: cabeçalho ignorado.
    assert ip_do_cliente(_request(remoto="192.0.3.1", xff=FORJADO)) == "192.0.3.1"


def test_rede_cidr_ipv6(settings):
    settings.PROXIES_CONFIAVEIS = ["2001:db8:1::/48"]

    assert ip_do_cliente(_request(remoto="2001:db8:1::5", xff=CLIENTE)) == CLIENTE
    assert ip_do_cliente(_request(remoto="2001:db8:2::5", xff=FORJADO)) == "2001:db8:2::5"


def test_versoes_diferentes_nao_se_confundem(settings):
    settings.PROXIES_CONFIAVEIS = ["::/0"]

    # Rede IPv6 não cobre IPv4.
    assert ip_do_cliente(_request(remoto=PROXY, xff=FORJADO)) == PROXY


# --- Critério 3: IPv6, espaços, malformado, vazio -----------------------------


def test_cliente_ipv6_e_gravado_normalizado(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    assert ip_do_cliente(_request(xff="2001:0DB8:0:0:0:0:0:1")) == "2001:db8::1"


def test_remote_addr_ipv4_mapeado_em_ipv6_casa_com_proxy_ipv4(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    assert ip_do_cliente(_request(remoto=f"::ffff:{PROXY}", xff=CLIENTE)) == CLIENTE


def test_espacos_em_volta_dos_enderecos_sao_tolerados(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY, PROXY_2]

    request = _request(xff=f"  {CLIENTE}  ,\t{PROXY_2} ")

    assert ip_do_cliente(request) == CLIENTE


@pytest.mark.parametrize(
    "xff",
    [
        "",
        "   ",
        ",",
        f"{CLIENTE},",  # entrada vazia à direita
        "nao-e-ip",
        f"{CLIENTE}, lixo",  # malformado no caminho da direita para a esquerda
        "198.51.100.7:8080",  # porta não faz parte de X-Forwarded-For
        "999.1.1.1",
        "unknown",
        "[2001:db8::1]",
        "2001:db8::1%eth0",
    ],
)
def test_cabecalho_malformado_cai_para_remote_addr_sem_excecao(settings, xff):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    assert ip_do_cliente(_request(xff=xff)) == PROXY


def test_lixo_a_esquerda_do_cliente_nao_atrapalha(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    # O percurso para no primeiro não confiável; o que está além dele é ignorado.
    assert ip_do_cliente(_request(xff=f"lixo, {CLIENTE}")) == CLIENTE


@pytest.mark.parametrize("remoto", [None, "", "nao-e-ip", "/run/gunicorn.sock"])
def test_remote_addr_ausente_ou_invalido_devolve_none(settings, remoto):
    settings.PROXIES_CONFIAVEIS = [PROXY]
    request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR=FORJADO)
    request.META.pop("REMOTE_ADDR", None)
    if remoto is not None:
        request.META["REMOTE_ADDR"] = remoto

    assert ip_do_cliente(request) is None


def test_entrada_invalida_na_lista_de_proxies_nao_estoura_e_nao_da_confianca(settings):
    modulo_ip._redes_confiaveis.cache_clear()
    settings.PROXIES_CONFIAVEIS = ["isto-nao-e-rede", PROXY]

    assert ip_do_cliente(_request(xff=CLIENTE)) == CLIENTE
    assert ip_do_cliente(_request(remoto="192.0.2.50", xff=FORJADO)) == "192.0.2.50"


# --- Configuração (config/settings.py) ------------------------------------------


@pytest.fixture
def recarregar_settings(monkeypatch):
    """Recarrega `config.settings` com a variável de ambiente dada e restaura depois."""
    from config import settings as config_settings

    def aplicar(valor):
        if valor is None:
            monkeypatch.delenv("DJANGO_PROXIES_CONFIAVEIS", raising=False)
        else:
            monkeypatch.setenv("DJANGO_PROXIES_CONFIAVEIS", valor)
        return importlib.reload(config_settings)

    yield aplicar
    monkeypatch.delenv("DJANGO_PROXIES_CONFIAVEIS", raising=False)
    importlib.reload(config_settings)


def test_padrao_do_projeto_e_lista_vazia(recarregar_settings):
    # Sem proxy declarado o sistema não pode confiar em cabeçalho do cliente.
    assert recarregar_settings(None).PROXIES_CONFIAVEIS == []


def test_configuracao_le_ips_e_redes_do_ambiente(recarregar_settings):
    lido = recarregar_settings("192.0.2.10, 2001:db8::/32").PROXIES_CONFIAVEIS

    assert lido == ["192.0.2.10", "2001:db8::/32"]


def test_configuracao_invalida_impede_a_subida(recarregar_settings):
    # Erro de digitação na lista não pode ser silencioso: relaxaria a trilha.
    with pytest.raises(ImproperlyConfigured, match="lixo"):
        recarregar_settings("192.0.2.10,lixo")


# --- Gravação real na trilha ----------------------------------------------------


@pytest.mark.django_db
def test_registrar_grava_na_trilha_o_ip_do_cliente_atras_do_proxy(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    registro = registrar(acao="teste.dl057", request=_request(xff=f"{FORJADO}, {CLIENTE}"))

    registro.refresh_from_db()
    assert registro.endereco_ip == CLIENTE


@pytest.mark.django_db
def test_registrar_sem_proxy_confiavel_nao_grava_ip_forjado(settings):
    settings.PROXIES_CONFIAVEIS = []

    registro = registrar(acao="teste.dl057", request=_request(remoto=CLIENTE, xff=FORJADO))

    registro.refresh_from_db()
    assert registro.endereco_ip == CLIENTE


@pytest.mark.django_db
def test_registrar_com_cabecalho_malformado_grava_remote_addr(settings):
    settings.PROXIES_CONFIAVEIS = [PROXY]

    registro = registrar(acao="teste.dl057", request=_request(xff="%%%, ???"))

    registro.refresh_from_db()
    assert registro.endereco_ip == PROXY


@pytest.mark.django_db
def test_login_real_grava_o_ip_do_cliente_na_trilha(client, settings):
    """Requisição de ponta a ponta (middleware, view, sinal, banco)."""
    settings.PROXIES_CONFIAVEIS = [PROXY]
    get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )

    client.post(
        reverse("login"),
        {"username": "ana", "password": "senha-forte-123"},
        REMOTE_ADDR=PROXY,
        HTTP_X_FORWARDED_FOR=f"{FORJADO}, {CLIENTE}",
    )

    assert RegistroAuditoria.objects.get(acao="login.sucesso").endereco_ip == CLIENTE


@pytest.mark.django_db
def test_login_real_sem_proxy_confiavel_ignora_cabecalho_forjado(client, settings):
    settings.PROXIES_CONFIAVEIS = []
    get_user_model().objects.create_user(
        username="ana", email="ana@escritorio.com.br", password="senha-forte-123"
    )

    client.post(
        reverse("login"),
        {"username": "ana", "password": "senha-errada"},
        REMOTE_ADDR=CLIENTE,
        HTTP_X_FORWARDED_FOR=FORJADO,
    )

    assert RegistroAuditoria.objects.get(acao="login.falha").endereco_ip == CLIENTE


# --- Critério 4: varredura — ponto único ------------------------------------------


def _fontes_de_producao_da_auditoria():
    raiz = Path(__file__).resolve().parents[1]
    for caminho in raiz.rglob("*.py"):
        relativo = caminho.relative_to(raiz)
        if relativo.parts[0] in {"tests", "migrations"}:
            continue
        if relativo.as_posix() == "ip.py":
            continue
        yield relativo, caminho.read_text(encoding="utf-8")


def test_nenhum_ponto_de_apps_auditoria_le_o_endereco_direto():
    """Só `ip.py` lê `REMOTE_ADDR`/`X-Forwarded-For`.

    Propriedade, não lista de arquivos: módulo novo em apps/auditoria que leia
    o endereço por conta própria reprova aqui, em vez de voltar a gravar o IP
    do proxy na trilha.
    """
    proibidos = ("REMOTE_ADDR", "X_FORWARDED_FOR", "X-Forwarded-For")
    infratores = [
        f"{relativo}: {marca}"
        for relativo, texto in _fontes_de_producao_da_auditoria()
        for marca in proibidos
        if marca in texto
    ]

    assert infratores == []


def test_a_varredura_enxerga_o_registrar_e_ele_usa_a_funcao_unica():
    # Guarda contra a varredura passar "no vazio": `services.py` precisa estar
    # no conjunto varrido e precisa de fato chamar `ip_do_cliente`.
    arquivos = {rel.as_posix(): texto for rel, texto in _fontes_de_producao_da_auditoria()}

    assert "services.py" in arquivos
    assert "ip_do_cliente(request)" in arquivos["services.py"]
