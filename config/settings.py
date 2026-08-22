import os
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_PATH = BASE_DIR / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"

if not DEBUG and not SECRET_KEY:
    raise RuntimeError("Defina DJANGO_SECRET_KEY em producao.")

ALLOWED_HOSTS = [
    host for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if host
] or []


INSTALLED_APPS = [
    # O unfold precisa vir antes do admin: é assim que os templates dele
    # sobrescrevem os do django.contrib.admin.
    "unfold",
    "unfold.contrib.filters",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "fonts",
    "editor",
    "jobs",
    "legal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "config.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Depois do Authentication (precisa de request.user): nova versão dos
    # termos bloqueia o uso até ser aceita.
    "legal.middleware.AceiteObrigatorioMiddleware",
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
                "core.context.app_shell",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


DATABASES = {
    "default": {
        "ENGINE": os.environ.get("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": os.environ.get("DB_NAME", BASE_DIR / "db.sqlite3"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", ""),
        "PORT": os.environ.get("DB_PORT", ""),
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"

USE_I18N = True
USE_TZ = True


STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = Path(
    os.environ.get("DJANGO_STATIC_ROOT", "/var/www/sistema_vetorial/shared/staticfiles")
)

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(
    os.environ.get("DJANGO_MEDIA_ROOT", "/var/www/sistema_vetorial/shared/private_media")
)

if "test" in sys.argv:
    # A suíte grava fontes e PDFs de verdade. Apontando para a mídia de
    # produção, ela só roda como www-data — e ainda sujaria os arquivos reais.
    # Precisa vir antes de STORAGES, que congela o `location` na importação.
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="vetorial-test-media-"))

STORAGES = {
    "default": {
        "BACKEND": "core.storage.PrivateMediaStorage",
        "OPTIONS": {
            "location": str(MEDIA_ROOT),
            "base_url": None,
        },
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "editor:list"

UNFOLD = {
    "SITE_TITLE": "StölbenVetorial",
    "SITE_HEADER": "StölbenVetorial",
    "SITE_SUBHEADER": "Administração",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        # Verde-petróleo do tema do app.
        "primary": {
            "50": "236 246 245",
            "100": "205 232 229",
            "200": "160 210 205",
            "300": "110 184 177",
            "400": "63 152 144",
            "500": "31 122 114",
            "600": "24 101 94",
            "700": "20 82 77",
            "800": "18 66 62",
            "900": "16 55 52",
            "950": "8 32 30",
        },
    },
}

# Destino após o aceite nas telas do app `legal`.
LEGAL_REDIRECT_URL = "editor:list"

# Sem LEGAL_VISITOR_ACTION: o acesso visitante está desativado neste sistema, e
# a tela de aceite de visitante responde 404 enquanto assim for.
LOGOUT_REDIRECT_URL = "login"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

FILE_RETENTION_DAYS = int(os.environ.get("FILE_RETENTION_DAYS", "7"))

CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", CELERY_BROKER_URL)
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 30
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_CONTENT_TYPE_NOSNIFF = True

if "test" in sys.argv:
    # Sem isto, rodar a suíte com DEBUG=False faz o SecurityMiddleware devolver
    # 301 em todo request, e os testes falham por motivo de ambiente, não de
    # código.
    SECURE_SSL_REDIRECT = False

CSRF_TRUSTED_ORIGINS = [
    "https://vetorial.stolben.com",
    "https://www.vetorial.stolben.com",
]

ADMIN_PATH_PREFIX = "/admin/"

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "frame-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)

# Política exclusiva do admin. O 'unsafe-eval' é exigido pelo Alpine.js que o
# django-unfold usa: ele compila as expressões de `x-data`/`x-init` com
# `new Function()`, e o 'unsafe-inline' da política acima não cobre isso. Sem
# a concessão o painel carrega sem menu, abas nem tema. Ela fica presa ao
# /admin/, que só `is_staff` alcança.
CONTENT_SECURITY_POLICY_ADMIN = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "font-src 'self' data:; "
    "object-src 'none'; "
    "frame-src 'self' blob:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)
