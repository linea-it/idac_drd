from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", True)
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="local-dev-only-change-me-idac_drd-dashboard-secret-key",
)
ALLOWED_HOSTS = env.list(
    "ALLOWED_HOSTS",
    default=["localhost", "0.0.0.0", "127.0.0.1", "testserver"],
)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    }
}

INSTALLED_APPS += ["django_extensions"]  # noqa: F405
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
