import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
PRODUCTION = os.environ.get("RADAR_ENV") == "production" or os.environ.get("ALTARE") == "1"
DEBUG = not PRODUCTION and os.environ.get("RADAR_DEBUG") == "1"
PUBLIC_URL = os.environ.get("RADAR_PUBLIC_URL") or os.environ.get("ALTARE_URL", "")
PUBLIC_URL = PUBLIC_URL.rstrip("/")
SECRET_KEY = os.environ.get("RADAR_SECRET_KEY", "")
ADMIN_PASSWORD_HASH = os.environ.get("RADAR_ADMIN_PASSWORD_HASH", "")
LEGACY_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

if PRODUCTION:
    if len(SECRET_KEY) < 50 or not (ADMIN_PASSWORD_HASH or len(LEGACY_PASSWORD) >= 12):
        raise ImproperlyConfigured("Configure RADAR_SECRET_KEY and administrator authentication.")
    if not PUBLIC_URL.startswith("https://") or not urlsplit(PUBLIC_URL).hostname:
        raise ImproperlyConfigured("Configure the public HTTPS origin.")
else:
    SECRET_KEY = SECRET_KEY or "local-ai-radar-development-only-unsafe-for-internet"

ALLOWED_HOSTS = [urlsplit(PUBLIC_URL).hostname] if PRODUCTION else ["127.0.0.1", "localhost", "testserver"]
CSRF_TRUSTED_ORIGINS = [PUBLIC_URL] if PRODUCTION else []
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if PRODUCTION else None
SECURE_SSL_REDIRECT = PRODUCTION
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SECURE_HSTS_SECONDS = 31536000 if PRODUCTION else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = PRODUCTION
# Altare owns the managed public domain. Browser preload enrollment is separate.
SILENCED_SYSTEM_CHECKS = ["security.W021"] if PRODUCTION else []
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "no-referrer"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_SECURE = PRODUCTION
SESSION_COOKIE_NAME = "__Host-radar" if PRODUCTION else "radar_dev"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Strict"
SESSION_COOKIE_AGE = 7 * 24 * 60 * 60
CSRF_USE_SESSIONS = True
CSRF_COOKIE_SECURE = PRODUCTION
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 100

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "radar.security.private_headers",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
INSTALLED_APPS = ["django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages",
                  "django.contrib.staticfiles", "radar"]
ROOT_URLCONF = "radar.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "radar.wsgi.application"
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage" if PRODUCTION else
                    "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Asia/Shanghai"
LANGUAGE_CODE = "zh-hans"

database_url = os.environ.get("RADAR_DATABASE_URL") or os.environ.get("DATABASE_URL")
if database_url:
    url = urlsplit(database_url)
    if url.scheme not in {"postgres", "postgresql"} or not url.hostname or not url.path.strip("/"):
        raise ImproperlyConfigured("Expected a PostgreSQL connection URL.")
    params = dict(parse_qsl(url.query))
    sslmode = os.environ.get("RADAR_DB_SSLMODE", params.get("sslmode", "require" if PRODUCTION else "prefer"))
    if PRODUCTION and sslmode not in {"require", "verify-ca", "verify-full"}:
        raise ImproperlyConfigured("Production PostgreSQL requires TLS.")
    options = {
        "sslmode": sslmode, "connect_timeout": 5,
        "options": "-c statement_timeout=8000 -c lock_timeout=4000 -c idle_in_transaction_session_timeout=15000",
    }
    if PRODUCTION:
        options["options"] += " -c search_path=radar"
    root_cert = os.environ.get("RADAR_DB_SSLROOTCERT") or params.get("sslrootcert")
    if root_cert:
        options["sslrootcert"] = root_cert
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": unquote(url.path[1:]), "USER": unquote(url.username or ""),
        "PASSWORD": unquote(url.password or ""), "HOST": url.hostname, "PORT": url.port or 5432,
        "CONN_MAX_AGE": 60, "CONN_HEALTH_CHECKS": True, "OPTIONS": options,
    }}
elif PRODUCTION:
    raise ImproperlyConfigured("Configure the managed PostgreSQL connection before starting production.")
else:
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("RADAR_SQLITE_PATH", BASE_DIR / "radar.sqlite3"),
        "OPTIONS": {"timeout": 10, "transaction_mode": "IMMEDIATE"},
    }}

LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "loggers": {
        "radar": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["console"], "level": "CRITICAL", "propagate": False},
    },
}
