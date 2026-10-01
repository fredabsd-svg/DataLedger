"""DL-057 (BL-553, nível 1 — trilha de auditoria): IP real atrás de proxy.

Critérios de aceite do plano:

1. Sem proxy confiável, `X-Forwarded-For` forjado é ignorado.
2. Com proxy confiável grava o IP do cliente; em cadeia de proxies, o primeiro
   endereço não confiável a partir da direita.
3. Cabeçalho malformado, IPv6 e espaços: sem erro, IP válido gravado.
4. Toda gravação da trilha usa a função única (varredura por teste).

Dados sintéticos: só endereços de documentação (RFC 5737 / RFC 3849).
"""

import ast
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


# --- Critério 4: guarda — ponto único de leitura do IP e de escrita da trilha ------
#
# UMA guarda, derivada de uma propriedade (AGENTS.md §3.1 e §8) e não de uma
# lista de arquivos ou de textos: em TODO `apps/` (menos `tests` e `migrations`),
# por AST,
#
#   1. só `apps/auditoria/ip.py` lê o endereço do cliente (`REMOTE_ADDR` ou os
#      cabeçalhos de encaminhamento) em `request.META`/`request.headers`;
#   2. só `apps/auditoria/services.py` cria `RegistroAuditoria`.
#
# Motivo (DL-057, achado F2): quem lê `REMOTE_ADDR` direto grava/limita pelo IP
# do proxy; quem lê `X-Forwarded-For` direto aceita IP forjado. A DL-056 passou a
# ler o IP fora de `apps/auditoria`, então a guarda precisa valer para todo app.

IP_PERMITIDO = "apps/auditoria/ip.py"
TRILHA_PERMITIDA = "apps/auditoria/services.py"

# Chaves de `request.META` que revelam o endereço do cliente. Os cabeçalhos de
# encaminhamento chegam em `META` com prefixo HTTP_ e traço virando sublinhado.
_CHAVES_DE_IP = {
    "REMOTE_ADDR",
    "HTTP_FORWARDED",
    "HTTP_X_REAL_IP",
    "HTTP_CLIENT_IP",
    "HTTP_TRUE_CLIENT_IP",
}
_PREFIXO_ENCAMINHADO = "HTTP_X_FORWARDED_"
_METODOS_DE_LEITURA = {"get", "pop", "setdefault"}
_METODOS_DE_ESCRITA = {"create", "bulk_create", "get_or_create", "update_or_create"}


def _constante_de_texto(no, nomes):
    """Valor de texto de uma expressão constante, ou `None` se não for constante.

    Dobra `"REMOTE_" + "ADDR"` e segue nomes atribuídos uma vez no módulo
    (`CHAVE = "REMOTE_ADDR"`): contornar a guarda por indireção trivial não pode
    funcionar. Expressão realmente dinâmica fica de fora (limite declarado).
    """
    if isinstance(no, ast.Constant) and isinstance(no.value, str):
        return no.value
    if isinstance(no, ast.Name):
        return nomes.get(no.id)
    if isinstance(no, ast.BinOp) and isinstance(no.op, ast.Add):
        esquerda = _constante_de_texto(no.left, nomes)
        direita = _constante_de_texto(no.right, nomes)
        if esquerda is not None and direita is not None:
            return esquerda + direita
    return None


def _e_chave_de_ip(chave):
    # `request.headers` usa o nome HTTP ("X-Forwarded-For"); `META`, "HTTP_X_FORWARDED_FOR".
    normalizada = chave.upper().replace("-", "_")
    candidatas = {normalizada, "HTTP_" + normalizada}
    return any(c in _CHAVES_DE_IP or c.startswith(_PREFIXO_ENCAMINHADO) for c in candidatas)


def _nomes_de_texto_do_modulo(arvore):
    nomes = {}
    for no in arvore.body:
        if (
            isinstance(no, ast.Assign)
            and len(no.targets) == 1
            and isinstance(no.targets[0], ast.Name)
            and isinstance(no.value, ast.Constant)
            and isinstance(no.value.value, str)
        ):
            nomes[no.targets[0].id] = no.value.value
    return nomes


def _termina_em(no, atributo):
    return isinstance(no, ast.Attribute) and no.attr == atributo


def _infracoes_de_ip(arvore):
    """(linha, chave) de cada leitura do endereço do cliente em META/headers."""
    nomes = _nomes_de_texto_do_modulo(arvore)
    achadas = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Subscript) and (
            _termina_em(no.value, "META") or _termina_em(no.value, "headers")
        ):
            chave = _constante_de_texto(no.slice, nomes)
        elif (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr in _METODOS_DE_LEITURA
            and (_termina_em(no.func.value, "META") or _termina_em(no.func.value, "headers"))
            and no.args
        ):
            chave = _constante_de_texto(no.args[0], nomes)
        else:
            continue
        if chave is not None and _e_chave_de_ip(chave):
            achadas.append((no.lineno, chave))
    return achadas


def _infracoes_de_trilha(arvore):
    """(linha, forma) de cada criação direta de `RegistroAuditoria`."""
    achadas = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        func = no.func
        nome = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if nome == "RegistroAuditoria":
            achadas.append((no.lineno, "RegistroAuditoria(...)"))
        elif (
            isinstance(func, ast.Attribute)
            and func.attr in _METODOS_DE_ESCRITA
            and _termina_em(func.value, "objects")
            and getattr(func.value.value, "id", getattr(func.value.value, "attr", None))
            == "RegistroAuditoria"
        ):
            achadas.append((no.lineno, f"RegistroAuditoria.objects.{func.attr}"))
    return achadas


def _violacoes(relativo, texto):
    """Violações de um arquivo; `relativo` é o caminho POSIX a partir da raiz do repositório."""
    arvore = ast.parse(texto)
    achadas = []
    if relativo != IP_PERMITIDO:
        achadas += [(relativo, linha, f"lê {chave}") for linha, chave in _infracoes_de_ip(arvore)]
    if relativo != TRILHA_PERMITIDA:
        achadas += [(relativo, linha, forma) for linha, forma in _infracoes_de_trilha(arvore)]
    return achadas


def _fontes_de_producao():
    """Todo `.py` de `apps/` que não seja teste nem migração: (caminho POSIX, texto)."""
    raiz = Path(__file__).resolve().parents[3]
    for caminho in sorted((raiz / "apps").rglob("*.py")):
        relativo = caminho.relative_to(raiz)
        if {"tests", "migrations"} & set(relativo.parts):
            continue
        yield relativo.as_posix(), caminho.read_text(encoding="utf-8")


def test_so_ip_py_le_o_endereco_e_so_services_py_cria_a_trilha():
    """A propriedade, sobre todo `apps/`. Módulo novo que viole reprova aqui."""
    fontes = dict(_fontes_de_producao())

    # A guarda não pode passar no vazio: os arquivos-chave estão no conjunto e o
    # detector, sem a isenção, ENXERGA a leitura de ip.py e a criação de services.py.
    assert IP_PERMITIDO in fontes
    assert TRILHA_PERMITIDA in fontes
    assert "apps/accounts/limite_tentativas.py" in fontes
    assert _infracoes_de_ip(ast.parse(fontes[IP_PERMITIDO]))
    assert _infracoes_de_trilha(ast.parse(fontes[TRILHA_PERMITIDA]))

    infratores = [v for relativo, texto in fontes.items() for v in _violacoes(relativo, texto)]

    assert infratores == []


@pytest.mark.parametrize(
    ("relativo", "codigo"),
    [
        # M8: outro app lendo o par TCP direto.
        ("apps/accounts/x.py", 'def f(request):\n    return request.META.get("REMOTE_ADDR")\n'),
        ("apps/accounts/x.py", 'def f(request):\n    return request.META["REMOTE_ADDR"]\n'),
        # M9: contornar por concatenação ou por constante nomeada.
        ("apps/auditoria/x.py", 'def f(r):\n    return r.META.get("REMOTE_" + "ADDR")\n'),
        ("apps/tenancy/x.py", 'K = "REMOTE_ADDR"\n\ndef f(r):\n    return r.META[K]\n'),
        # M10: outros cabeçalhos de IP, no próprio apps/auditoria.
        ("apps/auditoria/x.py", 'def f(r):\n    return r.META.get("HTTP_X_REAL_IP")\n'),
        ("apps/fiscal/x.py", 'def f(r):\n    return r.META.get("HTTP_X_FORWARDED_FOR", "")\n'),
        ("apps/fiscal/x.py", 'def f(r):\n    return r.META.get("HTTP_X_FORWARDED_HOST")\n'),
        ("apps/fiscal/x.py", 'def f(r):\n    return r.META.get("HTTP_FORWARDED")\n'),
        ("apps/fiscal/x.py", 'def f(r):\n    return r.META.get("HTTP_CLIENT_IP")\n'),
        ("apps/fiscal/x.py", 'def f(r):\n    return r.META.get("HTTP_TRUE_CLIENT_IP")\n'),
        # O acesso pela API de cabeçalhos do Django é a mesma leitura.
        ("apps/fiscal/x.py", 'def f(r):\n    return r.headers.get("X-Forwarded-For")\n'),
        # ip.py só é isento pelo caminho exato: o mesmo código em outro arquivo reprova.
        ("apps/auditoria/ip2.py", 'def f(r):\n    return r.META.get("REMOTE_ADDR")\n'),
        # Trilha: criação fora de services.py.
        ("apps/core/x.py", "def f():\n    return RegistroAuditoria(acao='x')\n"),
        ("apps/core/x.py", "def f():\n    return RegistroAuditoria.objects.create(acao='x')\n"),
        ("apps/core/x.py", "def f(lote):\n    RegistroAuditoria.objects.bulk_create(lote)\n"),
        ("apps/core/x.py", "def f(m):\n    return m.RegistroAuditoria(acao='x')\n"),
    ],
)
def test_a_guarda_reprova_as_mutacoes(relativo, codigo):
    assert _violacoes(relativo, codigo) != []


@pytest.mark.parametrize(
    ("relativo", "codigo"),
    [
        # Leituras sem relação com o endereço não são tocadas.
        ("apps/core/x.py", 'def f(r):\n    return r.META.get("CONTENT_TYPE")\n'),
        ("apps/core/x.py", 'def f(r):\n    return r.headers.get("User-Agent")\n'),
        # Consultar a trilha não é escrever nela.
        ("apps/core/x.py", "def f():\n    return RegistroAuditoria.objects.filter(acao='x')\n"),
        # As duas isenções, pelo caminho exato.
        ("apps/auditoria/ip.py", 'def f(r):\n    return r.META.get("REMOTE_ADDR")\n'),
        ("apps/auditoria/services.py", "def f():\n    return RegistroAuditoria.objects.create()\n"),
    ],
)
def test_a_guarda_nao_reprova_o_que_nao_viola(relativo, codigo):
    assert _violacoes(relativo, codigo) == []
