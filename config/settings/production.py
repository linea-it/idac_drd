from .base import *  # noqa: F403
from .base import LOGIN_URL, env

DEBUG = False
SECRET_KEY = env("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
# preload exige >= 1 ano; 60s tornava o PRELOAD inócuo
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["https://www.linea.org.br", "https://linea.org.br"],
)

# Nginx em /drd/ faz rewrite e o uvicorn vê PATH_INFO sem o prefixo.
_script_name = env.str("DJANGO_FORCE_SCRIPT_NAME", default="").rstrip("/")
if _script_name:
    FORCE_SCRIPT_NAME = _script_name
    STATIC_URL = f"{_script_name}/static/"
    MEDIA_URL = f"{_script_name}/media/"
    CSRF_COOKIE_PATH = _script_name
    SESSION_COOKIE_PATH = _script_name
    # Pedido chega como /static/...; STATIC_URL público é /drd/static/.
    WHITENOISE_STATIC_PREFIX = "/static/"
    if isinstance(LOGIN_URL, str) and LOGIN_URL.startswith("/"):
        LOGIN_URL = f"{_script_name}{LOGIN_URL}"
