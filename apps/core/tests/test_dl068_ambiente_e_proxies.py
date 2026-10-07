"""DL-068 (itens 4 e 5): `DJANGO_AMBIENTE` (BL-82) e proxies confiáveis (BL-577).

Critérios de aceite do plano cobertos aqui: 8, 9, 10, 12 e 13.

`config/settings.py` valida ambiente e proxies em código de MÓDULO, avaliado uma
única vez na importação das configurações. Por isso os critérios 8, 9, 10 e 12
sobem um processo Python NOVO (`manage.py check`) com o ambiente de uma
implantação real e observam código de saída e mensagem — o mesmo padrão de
`test_configuracao_producao.py`. O critério 13 (aviso do `check`) é uma função
pura sobre `settings.PROXIES_CONFIAVEIS` e roda em processo, com `settings`
trocado por teste.

Dados sintéticos: só endereços de documentação (RFC 5737 e RFC 3849).
"""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.checks import Tags, Warning, run_checks
from django.core.checks.registry import registry

from apps.auditoria.checks import verificar_proxies_confiaveis_largos

# apps/core/tests/test_x.py -> apps/core -> apps -> raiz do repositório.
BASE_DIR = Path(__file__).resolve().parents[3]

SECRET_KEY_DE_TESTE = "chave-apenas-para-verificar-subida-do-processo-de-teste"
BANCO_POSTGRES = "postgres://usuario:senha@host:5432/banco"
AMBIENTES_ACEITOS_NA_MENSAGEM = "desenvolvimento, homologacao, producao"


def _rodar_manage_check(overrides, deploy=False, timeout=60):
    """Sobe `manage.py check` num processo separado com o ambiente indicado.

    Parte de uma cópia do ambiente do processo de teste (PATH, HOME etc.) e
    REMOVE as três variáveis que esta etapa controla, para o resultado não
    depender de quem roda: a integração contínua define `DEBUG=True`, e a
    máquina do desenvolvedor pode ter variáveis soltas. Também força
    `DATABASE_URL=""` antes de aplicar `overrides`: string vazia sobrepõe o que
    `django-environ` leria do `.env` da raiz e cai no ramo "ausente" da guarda
    de banco. `DJANGO_PROXIES_CONFIAVEIS` vai vazio pelo mesmo motivo (o `.env`
    local não pode contaminar o cenário).
    """
    ambiente = dict(os.environ)
    for variavel in ("DEBUG", "DJANGO_AMBIENTE", "DJANGO_PROXIES_CONFIAVEIS"):
        ambiente.pop(variavel, None)
    ambiente["DJANGO_SECRET_KEY"] = SECRET_KEY_DE_TESTE
    ambiente["DJANGO_ALLOWED_HOSTS"] = "localhost"
    ambiente["DATABASE_URL"] = ""
    ambiente["DJANGO_PROXIES_CONFIAVEIS"] = ""
    ambiente.update(overrides)

    comando = [sys.executable, "manage.py", "check"]
    if deploy:
        comando.append("--deploy")

    return subprocess.run(
        comando,
        cwd=BASE_DIR,
        env=ambiente,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


# --- Critério 8: produção e homologação recusam DEBUG=True -------------------


@pytest.mark.parametrize("ambiente", ["producao", "homologacao"])
def test_ambiente_fora_de_desenvolvimento_com_debug_true_recusa_subir(ambiente):
    """BL-82: DEBUG=True mostra variáveis e configurações nas páginas de erro e
    desliga as proteções de HTTPS. Fora de desenvolvimento a aplicação não pode
    subir assim, e a mensagem precisa nomear as DUAS variáveis para quem
    estiver olhando o log de implantação saber o que corrigir."""
    resultado = _rodar_manage_check(
        {"DJANGO_AMBIENTE": ambiente, "DEBUG": "True", "DATABASE_URL": BANCO_POSTGRES}
    )

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DJANGO_AMBIENTE" in resultado.stderr
    assert "DEBUG" in resultado.stderr
    assert "DEBUG=False" in resultado.stderr


def test_debug_true_em_producao_e_recusado_antes_de_qualquer_outra_checagem():
    """Sem banco configurado, o erro que o operador vê deve ser o do ambiente:
    `DEBUG=True` em produção é o defeito mais grave e não pode ficar escondido
    atrás da mensagem sobre `DATABASE_URL`."""
    resultado = _rodar_manage_check({"DJANGO_AMBIENTE": "producao", "DEBUG": "True"})

    assert resultado.returncode != 0
    assert "DJANGO_AMBIENTE" in resultado.stderr
    assert "DATABASE_URL" not in resultado.stderr


@pytest.mark.parametrize("valor", ["  producao  ", "PRODUCAO", " Producao\t", "HomologaCAO "])
def test_espacos_e_caixa_no_ambiente_nao_desligam_a_guarda(valor):
    """Limite: um `.env` editado à mão costuma trazer espaço sobrando ou
    maiúscula. O valor é normalizado (`strip` e minúsculas); se não fosse,
    ` PRODUCAO` cairia como inválido ou, pior, como desenvolvimento."""
    resultado = _rodar_manage_check(
        {"DJANGO_AMBIENTE": valor, "DEBUG": "True", "DATABASE_URL": BANCO_POSTGRES}
    )

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    # É a guarda de DEBUG que reprova, não a de valor inválido.
    assert "não aceita DEBUG=True" in resultado.stderr


# --- Critério 9: produção bem configurada sobe; desenvolvimento como hoje ----


def test_producao_com_debug_false_e_postgres_sobe_sem_avisos_de_deploy():
    """Regressão: a guarda não pode recusar a produção legítima. `check
    --deploy` sai sem nenhum aviso (BL-51 continua valendo)."""
    resultado = _rodar_manage_check(
        {
            "DJANGO_AMBIENTE": "producao",
            "DEBUG": "False",
            "DATABASE_URL": BANCO_POSTGRES,
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
            "DJANGO_ALLOWED_HOSTS": "app.exemplo.com.br",
        },
        deploy=True,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "System check identified no issues" in resultado.stdout
    # Avisos do `check` saem em stderr: conferir só stdout não os enxergaria.
    assert "WARNINGS" not in resultado.stdout + resultado.stderr


def test_homologacao_com_debug_false_e_postgres_sobe():
    resultado = _rodar_manage_check(
        {"DJANGO_AMBIENTE": "homologacao", "DEBUG": "False", "DATABASE_URL": BANCO_POSTGRES}
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def test_sem_a_variavel_e_com_debug_true_sobe_como_antes():
    """Compatibilidade: suíte, integração contínua e a máquina do
    desenvolvedor não declaram `DJANGO_AMBIENTE`. O padrão é `desenvolvimento`,
    que continua aceitando DEBUG=True (e o aviso de SQLite do BL-50)."""
    resultado = _rodar_manage_check({"DEBUG": "True"})

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "RuntimeWarning" in resultado.stderr


@pytest.mark.parametrize("valor", ["desenvolvimento", "  Desenvolvimento  "])
def test_desenvolvimento_declarado_aceita_debug_true(valor):
    """O `.env.example` declara `desenvolvimento` justamente para o compose
    local continuar subindo com DEBUG=True sobre a imagem, que é `producao`."""
    resultado = _rodar_manage_check({"DJANGO_AMBIENTE": valor, "DEBUG": "True"})

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


# --- Critério 10: valor fora da lista recusa subir ---------------------------


@pytest.mark.parametrize("valor", ["staging", "prod", "producão", "dev", "1", ""])
def test_ambiente_com_valor_fora_da_lista_recusa_subir_e_lista_os_aceitos(valor):
    """Valor desconhecido não pode cair em silêncio num padrão. O caso `""` é
    deliberado: na imagem de produção, um `DJANGO_AMBIENTE=` vazio esquecido no
    `.env` voltaria ao padrão `desenvolvimento` e desligaria a guarda."""
    resultado = _rodar_manage_check(
        {"DJANGO_AMBIENTE": valor, "DEBUG": "False", "DATABASE_URL": BANCO_POSTGRES}
    )

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DJANGO_AMBIENTE" in resultado.stderr
    assert AMBIENTES_ACEITOS_NA_MENSAGEM in resultado.stderr


# --- Critério 12: proxies confiáveis recusam rede /0 -------------------------


@pytest.mark.parametrize(
    "valor",
    [
        "0.0.0.0/0",
        "::/0",
        # Limites: espaços, /0 em meio a outros valores válidos, endereço com
        # bits de host (o prefixo é que manda: `1.2.3.4/0` é a internet toda).
        "  0.0.0.0/0  ",
        "192.0.2.10, 0.0.0.0/0, 198.51.100.0/24",
        "192.0.2.10,2001:db8::/32,::/0",
        "1.2.3.4/0",
        "2001:db8::1/0",
    ],
)
def test_rede_com_prefixo_zero_nos_proxies_confiaveis_recusa_subir(valor):
    """BL-577: com `/0` todo cliente da internet seria 'proxy confiável' e
    escolheria, pelo `X-Forwarded-For`, o IP que a trilha de auditoria grava."""
    resultado = _rodar_manage_check(
        {
            "DEBUG": "False",
            "DATABASE_URL": BANCO_POSTGRES,
            "DJANGO_PROXIES_CONFIAVEIS": valor,
        }
    )

    assert resultado.returncode != 0, resultado.stdout + resultado.stderr
    assert "ImproperlyConfigured" in resultado.stderr
    assert "DJANGO_PROXIES_CONFIAVEIS" in resultado.stderr
    assert "/0" in resultado.stderr
    assert "trilha" in resultado.stderr


@pytest.mark.parametrize("valor", ["", "192.0.2.10", "192.0.2.10,2001:db8::/64,10.0.0.0/8"])
def test_proxies_legitimos_continuam_subindo(valor):
    """Regressão: a recusa de `/0` não pode pegar lista vazia, IP único nem
    rede privada larga."""
    resultado = _rodar_manage_check(
        {
            "DEBUG": "False",
            "DATABASE_URL": BANCO_POSTGRES,
            "DJANGO_PROXIES_CONFIAVEIS": valor,
        }
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "auditoria.W001" not in resultado.stdout + resultado.stderr


def test_rede_larga_publica_sem_ser_zero_sobe_mas_avisa_no_check():
    """O limite entre recusar e avisar: `0.0.0.0/1` não é `/0`, então a
    aplicação sobe (há implantação legítima atrás de CDN com faixas largas), e
    o aviso aparece na saída do `manage.py check` do processo real — o que
    prova que a verificação está registrada, não só que a função funciona."""
    resultado = _rodar_manage_check(
        {
            "DEBUG": "False",
            "DATABASE_URL": BANCO_POSTGRES,
            "DJANGO_PROXIES_CONFIAVEIS": "0.0.0.0/1",
        }
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    # O Django escreve os avisos de `check` em stderr; olha-se os dois fluxos.
    saida = resultado.stdout + resultado.stderr
    assert "auditoria.W001" in saida
    assert "0.0.0.0/1" in saida


# --- Critério 13: aviso do system check --------------------------------------


def _avisos(settings, proxies):
    settings.PROXIES_CONFIAVEIS = proxies
    return verificar_proxies_confiaveis_largos()


@pytest.mark.parametrize(
    "rede",
    [
        "198.51.100.0/23",  # IPv4 público, um bit abaixo do limite /24
        "198.51.100.5/23",  # bits de host: o prefixo é o que conta
        "198.51.0.0/16",
        # Faixas de documentação: `ipaddress.is_private` as chama de privadas,
        # mas não são a rede interna de um proxy. Aqui contam como públicas, e
        # estes dois casos matam a troca por `is_private`.
        "2001:db8::/63",  # IPv6 um bit abaixo do limite /64
        "2001:db8::/32",
        "172.0.0.0/8",  # parece RFC 1918, mas só 172.16.0.0/12 é privado
        "192.168.0.0/15",  # começa no privado e invade 192.169.x.x, público
        "0.0.0.0/1",  # cobre metade da internet
        "0.0.0.0/0",  # a internet toda (o settings já recusa; o check não depende disso)
        "::/0",
    ],
)
def test_rede_publica_larga_gera_aviso(settings, rede):
    avisos = _avisos(settings, [rede])

    assert len(avisos) == 1, avisos
    aviso = avisos[0]
    assert isinstance(aviso, Warning)
    assert aviso.id == "auditoria.W001"
    assert "DJANGO_PROXIES_CONFIAVEIS" in aviso.msg
    assert aviso.hint


@pytest.mark.parametrize(
    "rede",
    [
        "198.51.100.0/24",  # exatamente o limite IPv4
        "198.51.100.0/25",
        "2001:db8::/64",  # exatamente o limite IPv6
        "2001:db8::/65",
        "203.0.113.10",  # IP único
        "2001:db8::1",
        "10.0.0.0/8",  # privada larga
        "172.16.0.0/12",
        "192.168.0.0/16",
        "127.0.0.0/8",  # loopback
        "169.254.0.0/16",  # link-local
        "fc00::/7",  # IPv6 privado (ULA), largo
        "fe80::/10",  # IPv6 link-local, largo
        "::1",
    ],
)
def test_rede_estreita_ou_privada_nao_gera_aviso(settings, rede):
    assert _avisos(settings, [rede]) == []


def test_lista_vazia_nao_gera_aviso(settings):
    assert _avisos(settings, []) == []


def test_cada_rede_larga_gera_o_seu_aviso_e_as_demais_sao_ignoradas(settings):
    avisos = _avisos(
        settings,
        ["203.0.113.10", "198.51.100.0/23", "10.0.0.0/8", "2001:db8::/63", "198.51.100.0/24"],
    )

    assert [aviso.id for aviso in avisos] == ["auditoria.W001", "auditoria.W001"]
    assert "198.51.100.0/23" in avisos[0].msg
    assert "2001:db8::/63" in avisos[1].msg


def test_entrada_invalida_e_ignorada_pelo_aviso_sem_levantar_excecao(settings):
    """O erro de entrada inválida é do `settings.py`, que recusa subir. O check
    não pode ele mesmo quebrar o `manage.py check` por causa disso."""
    assert _avisos(settings, ["nao-e-ip", "", "198.51.100.0/23"])[0].id == "auditoria.W001"


def test_verificacao_esta_registrada_e_aparece_no_check_do_django(settings):
    """O aviso só vale se o Django o executar de verdade: a função precisa
    estar registrada (por `AuditoriaConfig.ready`) e sair em `run_checks`."""
    assert verificar_proxies_confiaveis_largos in registry.registered_checks

    settings.PROXIES_CONFIAVEIS = ["198.51.100.0/23"]
    ids = [mensagem.id for mensagem in run_checks(tags=[Tags.security])]

    assert "auditoria.W001" in ids
