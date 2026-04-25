"""
config/settings.py
==================
Django settings for the Thematic Analysis web interface.

Reads all infrastructure config from pydantic_settings / .env — exactly
the same source as the Streamlit app.py did, so the same .env file works.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# ── Path helpers ───────────────────────────────────────────────────────────────
# BASE_DIR points at  thematic/web/
BASE_DIR = Path(__file__).resolve().parent.parent

# Project root (contains pyproject.toml, .env, thematic/)
PROJECT_ROOT = BASE_DIR.parent.parent


# ── Infrastructure settings (shared with Streamlit) ───────────────────────────

class InfraSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        extra="ignore",
    )

    db_url: str = f"sqlite:///{PROJECT_ROOT / 'thematic.db'}"
    chroma_path: str = str(PROJECT_ROOT / "chroma_store")
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    embedding_device: str | None = None
    ollama_model: str = "mistral:7b"
    ollama_host: str = "http://localhost:11434"
    anthropic_api_key: str = ""
    default_analyst: str = "analyst"
    use_claude: bool = False

    # Django-specific
    secret_key: str = "django-dev-secret-CHANGE-IN-PRODUCTION"
    debug: bool = True
    allowed_hosts: str = "localhost,127.0.0.1"


_infra = InfraSettings()

# ── Django core ────────────────────────────────────────────────────────────────

SECRET_KEY = _infra.secret_key
DEBUG = _infra.debug
ALLOWED_HOSTS = _infra.allowed_hosts.split(",")

# Expose parsed infra settings for use by apps/core/services.py
INFRA_SETTINGS = _infra

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Local apps
    "thematic.web.apps.core",
    "thematic.web.apps.corpus",
    "thematic.web.apps.coding",
    "thematic.web.apps.analysis",
    "thematic.web.apps.export",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",          # i18n URL handling
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "thematic.web.config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.messages.context_processors.messages",
                "thematic.web.apps.core.context_processors.active_project",
            ],
        },
    },
]

WSGI_APPLICATION = "thematic.web.config.wsgi.application"

# ── Sessions (file-based — no additional DB needed) ───────────────────────────
SESSION_ENGINE = "django.contrib.sessions.backends.file"
SESSION_FILE_PATH = PROJECT_ROOT / ".django_sessions"
SESSION_FILE_PATH.mkdir(exist_ok=True)

# ── Internationalisation ───────────────────────────────────────────────────────
LANGUAGE_CODE = "en"
LANGUAGES = [
    ("en", "English"),
    ("es", "Español"),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
USE_L10N = True
USE_TZ = True
TIME_ZONE = "America/Bogota"

# ── Static files ───────────────────────────────────────────────────────────────
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = PROJECT_ROOT / "staticfiles"
STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django doesn't manage our SQLAlchemy DB — but it needs *some* DATABASES entry
# for session middleware to work (even with file-based sessions).
DATABASES = {}

# ── Messages ───────────────────────────────────────────────────────────────────
from django.contrib.messages import constants as messages  # noqa: E402
MESSAGE_TAGS = {
    messages.DEBUG: "debug",
    messages.INFO: "info",
    messages.SUCCESS: "success",
    messages.WARNING: "warning",
    messages.ERROR: "error",
}
