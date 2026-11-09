"""Settings for Glow & Grace.

Local development works without a .env file. Production must set
DJANGO_ENV=production plus the variables documented in .env.example.
"""

import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - import error is explained at startup
    load_dotenv = None


BASE_DIR = Path(__file__).resolve().parent.parent

if load_dotenv is not None:
    load_dotenv(BASE_DIR / ".env")


def env_bool(name, default="false"):
    return os.environ.get(name, default).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name):
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


IS_PRODUCTION = os.environ.get("DJANGO_ENV", "development").strip().lower() == "production"

if IS_PRODUCTION:
    DEBUG = False
else:
    DEBUG = env_bool("DJANGO_DEBUG", "true")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()
if IS_PRODUCTION and len(SECRET_KEY) < 32:
    raise ImproperlyConfigured(
        "Set DJANGO_SECRET_KEY to a long random value when DJANGO_ENV=production."
    )
if not SECRET_KEY:
    SECRET_KEY = "django-insecure-dev-only-glow-grace-change-this"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Set DJANGO_ALLOWED_HOSTS when DJANGO_ENV=production."
    )
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")


def database_from_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ImproperlyConfigured(
            "DATABASE_URL must start with postgres:// or postgresql://. "
            "Leave it unset to use SQLite locally."
        )
    name = parsed.path.lstrip("/")
    if not name:
        raise ImproperlyConfigured("DATABASE_URL is missing the database name.")
    options = {}
    query = parse_qs(parsed.query)
    if query.get("sslmode"):
        options["sslmode"] = query["sslmode"][-1]
    config = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": name,
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or ""),
        "CONN_MAX_AGE": 60,
    }
    if options:
        config["OPTIONS"] = options
    return config


DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
if DATABASE_URL:
    DATABASES = {"default": database_from_url(DATABASE_URL)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
            # Takes the write lock at the start of each transaction so two
            # customers cannot both pass the free-slot check for one time.
            "OPTIONS": {"transaction_mode": "IMMEDIATE", "timeout": 20},
        }
    }

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "salon",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "salon.context_processors.site_context",
            ],
        },
    }
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False

if IS_PRODUCTION:
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", "true")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend"
    if IS_PRODUCTION
    else "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", "true")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "bookings@localhost")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
EMAIL_TIMEOUT = 5

try:
    EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
except ValueError:
    EMAIL_PORT = 587

OWNER_EMAIL = os.environ.get("OWNER_EMAIL", "").strip()
PUBLIC_CONTACT_EMAIL = os.environ.get("PUBLIC_CONTACT_EMAIL", "").strip()
OWNER_WHATSAPP_NUMBER = os.environ.get("OWNER_WHATSAPP_NUMBER", "254700000000").strip()
SOCIAL_INSTAGRAM_URL = os.environ.get("SOCIAL_INSTAGRAM_URL", "").strip()
BOOKING_DUPLICATE_WINDOW_MINUTES = 3

SALON = {
    "name": "Glow & Grace Salon, Spa & Nail Studio",
    "short_name": "Glow & Grace",
    "address_lines": [
        "Rose Court, 2nd Floor",
        "12 Argwings Kodhek Road",
        "Kilimani, Nairobi",
    ],
    "hours": [
        ("Monday to Friday", "8:00 AM – 7:00 PM"),
        ("Saturday", "8:00 AM – 6:00 PM"),
        ("Sunday", "10:00 AM – 4:00 PM"),
    ],
    "about": (
        "Glow & Grace is a salon, spa and nail studio in Kilimani, Nairobi. "
        "Book online and you will know straight away whether your time is free."
    ),
}

CSRF_FAILURE_VIEW = "salon.views.csrf_failure"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "salon": {
            "handlers": ["console"],
            "level": "INFO",
        },
    },
}
