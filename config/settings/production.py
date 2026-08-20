from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .base import *  # noqa: F403
from .base import LINEA_LOGIN_URL, LOGIN_URL, RUBIN_LOGIN_URL, env

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


def _with_script_name(url, script_name):
    """Prefixa path absoluto (e ?next=) com o SCRIPT_NAME do reverse proxy."""
    if not isinstance(url, str) or not url.startswith("/"):
        return url
    parts = urlsplit(url)
    path = parts.path or "/"
    if path == "/":
        path = f"{script_name}/"
    elif path != script_name and not path.startswith(f"{script_name}/"):
        path = f"{script_name}{path}"
    query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        if key == "next" and val.startswith("/"):
            if val == "/":
                val = f"{script_name}/"
            elif val != script_name and not val.startswith(f"{script_name}/"):
                val = f"{script_name}{val}"
        query.append((key, val))
    return urlunsplit(("", "", path, urlencode(query), parts.fragment))


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
    LOGIN_URL = _with_script_name(LOGIN_URL, _script_name)
    LINEA_LOGIN_URL = _with_script_name(LINEA_LOGIN_URL, _script_name)
    RUBIN_LOGIN_URL = _with_script_name(RUBIN_LOGIN_URL, _script_name)
