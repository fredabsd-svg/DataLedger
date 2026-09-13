"""
Configuração do Django para o DataLedger.

Todos os valores sensíveis ou dependentes de ambiente vêm de variáveis de
ambiente (arquivo .env em desenvolvimento, variáveis reais em produção).
Ver .env.example para a lista completa e valores de referência para
desenvolvimento local.
"""

import warnings
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DEBUG")

# DE-014: implantação em nuvem, acessada pela internet. ALLOWED_HOSTS e
# CSRF_TRUSTED_ORIGINS vêm do ambiente (nenhum host de produção hardcoded
# aqui) e o padrão é o mais restritivo possível: lista vazia recusa toda
# requisição em vez de aceitar um host não revisado.
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])


# Aplicação

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.tenancy",
    "apps.empresas",
    "apps.auditoria",
    "apps.contabilidade",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.tenancy.middleware.EscritorioAtivoMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# Banco de dados
# NUMERIC/DECIMAL do PostgreSQL é obrigatório para valores monetários e
# fiscais: ponto flutuante binário não é aceito nas regras do projeto.
#
# BL-50 (DE-014): a implantação alvo tem ~50 usuários simultâneos. SQLite
# serializa gravações e devolve "database is locked" sob essa concorrência —
# um defeito que NÃO aparece na instalação, só depois, com o escritório
# trabalhando. Por isso a escolha de banco é validada aqui, na subida do
# processo, em vez de vazar como incidente em produção:
#
# - DATABASE_URL ausente e DEBUG=False  -> recusa subir (ImproperlyConfigured).
# - DATABASE_URL ausente e DEBUG=True   -> SQLite local, mas com aviso
#   explícito no startup (nunca em silêncio).
# - DATABASE_URL aponta para SQLite e DEBUG=False -> recusa subir: configurar
#   explicitamente o banco errado é tão grave quanto não configurar nada.
_database_url = env("DATABASE_URL", default=None)

if _database_url:
    DATABASES = {"default": env.db_url_config(_database_url)}
    _banco_e_sqlite = DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    if _banco_e_sqlite and not DEBUG:
        raise ImproperlyConfigured(
            "DATABASE_URL aponta para SQLite, mas DEBUG=False exige um banco "
            "PostgreSQL (DE-014: implantação em nuvem com ~50 usuários "
            "simultâneos, que o SQLite não suporta em escrita concorrente). "
            "Configure DATABASE_URL com uma URL PostgreSQL, por exemplo "
            "postgres://usuario:senha@host:5432/nome_do_banco."
        )
elif DEBUG:
    # Aviso DECLARADO, não silencioso: quem rodar localmente sem configurar
    # DATABASE_URL precisa saber que está em SQLite e que isso nunca deve
    # acontecer fora de desenvolvimento nem com dado real de cliente.
    warnings.warn(
        "DATABASE_URL não configurada: usando SQLite local em "
        f"{BASE_DIR / 'db.sqlite3'}. Válido apenas em desenvolvimento "
        "(DEBUG=True) — nunca use SQLite em produção nem com dado real de "
        "cliente (BL-50, DE-014).",
        RuntimeWarning,
        stacklevel=1,
    )
    DATABASES = {
        "default": env.db_url_config("sqlite:///" + str(BASE_DIR / "db.sqlite3")),
    }
else:
    raise ImproperlyConfigured(
        "DATABASE_URL não configurada. Em produção (DEBUG=False) o "
        "DataLedger exige um banco PostgreSQL: defina a variável de "
        "ambiente DATABASE_URL, por exemplo "
        "postgres://usuario:senha@host:5432/nome_do_banco. SQLite não "
        "suporta a escrita concorrente exigida para ~50 usuários "
        "simultâneos (DE-014, BL-50)."
    )


# Validação de senha

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internacionalização

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True


# Arquivos estáticos

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# CSS próprio do projeto (DE-011: nenhuma biblioteca visual externa) vive em
# static/css/ na raiz do repositório, fora de qualquer app — por isso
# precisa ser declarado explicitamente aqui para o finder encontrá-lo.
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Usuário customizado desde a primeira migração: nunca trocar este valor
# depois que houver dados reais, pois isso não é suportado pelo Django.
AUTH_USER_MODEL = "accounts.Usuario"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "tenancy:painel"
LOGOUT_REDIRECT_URL = "login"


# Django REST Framework
# Escopo mínimo por enquanto: as ferramentas MCP e demais APIs definirão
# autenticação e permissões próprias nas etapas de fundação e de cada módulo.

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}


# Cabeçalhos de segurança que não dependem de HTTPS e por isso ficam
# sempre ativos (não quebram `runserver` em desenvolvimento):
#
# - X_FRAME_OPTIONS: impede que a tela do DataLedger seja carregada dentro
#   de um <iframe> de outro site (clickjacking). Não há motivo legítimo
#   para incorporar o sistema num frame alheio, então "DENY" é o mais
#   restritivo. Já é o padrão do Django, mas fica explícito aqui porque é
#   um requisito de implantação (BL-51), não um acidente de configuração.
# - SECURE_CONTENT_TYPE_NOSNIFF: impede que o navegador tente adivinhar
#   ("sniff") o tipo de um arquivo servido e o execute como script — vetor
#   comum quando o sistema aceita upload de documento fiscal/anexo.
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True


# Segurança adicional quando fora de desenvolvimento (BL-51, DE-014: acesso
# pela internet, com proxy reverso na frente).
# Ativa somente com DEBUG=False para não atrapalhar o ambiente local
# (que normalmente roda sem HTTPS) — forçar HTTPS no `runserver` quebraria
# o desenvolvimento e um ambiente local quebrado é o caminho mais curto
# para alguém desligar a proteção inteira, inclusive em produção.

if not DEBUG:
    # Redireciona toda requisição HTTP para HTTPS: senha e dado de cliente
    # não podem trafegar em claro pela internet.
    SECURE_SSL_REDIRECT = True

    # Sem proxy reverso na frente, request.is_secure() olharia diretamente
    # para a conexão TCP recebida pelo processo Django. Com proxy (DE-014),
    # a conexão do proxy até o Django é HTTP mesmo quando o cliente usou
    # HTTPS — por isso o Django precisa confiar no cabeçalho que o proxy
    # define com o protocolo original. Isto só é seguro porque o proxy é
    # quem TERMINA a conexão do cliente e SOBRESCREVE esse cabeçalho; ele
    # nunca pode repassar um X-Forwarded-Proto vindo do próprio cliente.
    # Sem isso, SECURE_SSL_REDIRECT entraria em loop de redirecionamento
    # atrás do proxy (procedimento de implantação: BL-53).
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # Cookies de sessão e de CSRF nunca devem trafegar sem cifra.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    # HSTS: instrui o navegador a nunca mais tentar HTTP puro neste domínio
    # pelo período abaixo, mesmo que o usuário digite a URL sem "https://".
    # 30 dias é suficiente para cobrir uma renovação de certificado sem
    # forçar todo mundo a esperar meses caso precisemos reverter.
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

    # include_subdomains: cobre qualquer subdomínio que venha a existir
    # (ex.: um futuro "api." ou "app."), porque não há hoje nenhum
    # subdomínio que precise continuar aceitando HTTP puro.
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    # preload: apenas ACRESCENTA a diretiva "preload" ao cabeçalho HSTS que
    # o navegador já recebe por causa de SECURE_HSTS_SECONDS acima — não
    # inscreve o domínio sozinho na lista de pré-carregamento dos
    # navegadores (isso exigiria um passo manual, deliberado, em
    # hstspreload.org). Como o domínio de produção só serve este sistema
    # (DE-014: servidor único), não há razão para aceitar HTTP puro em
    # nenhum caminho, e manter a diretiva fora do cabeçalho não traz
    # benefício — só deixa `check --deploy` acusando o aviso W021 à toa.
    SECURE_HSTS_PRELOAD = True
