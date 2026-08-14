"""Base settings for wkfw-dashboard."""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve(strict=True).parent.parent.parent
APPS_DIR = BASE_DIR / "wkfw"
env = environ.Env()

READ_DOT_ENV_FILE = env.bool("DJANGO_READ_DOT_ENV_FILE", default=True)
if READ_DOT_ENV_FILE:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        env.read_env(str(env_file))

DEBUG = env.bool("DJANGO_DEBUG", False)
LOGGING_LEVEL = env.str("DJANGO_LOG_LEVEL", "INFO")
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
SITE_ID = 1
USE_I18N = True
USE_TZ = True
LOCALE_PATHS = [str(BASE_DIR / "locale")]

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default="postgres://postgres:postgres@localhost:5432/postgres",
    )
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DJANGO_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.admin",
    "django.forms",
]
THIRD_PARTY_APPS = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "drf_spectacular",
]
LOCAL_APPS = [
    "wkfw.users",
    "wkfw.workflow",
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
AUTH_USER_MODEL = "users.User"
LOGIN_REDIRECT_URL = "home"
LOGIN_URL = "account_login"

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

STATIC_ROOT = str(BASE_DIR / "staticfiles")
STATIC_URL = "/static/"
STATICFILES_DIRS = [str(APPS_DIR / "static")]
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]
MEDIA_ROOT = str(APPS_DIR / "media")
MEDIA_URL = "/media/"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [str(APPS_DIR / "templates")],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "wkfw.users.context_processors.allauth_settings",
                "django_settings_export.settings_export",
            ],
        },
    }
]

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"
CRISPY_TEMPLATE_PACK = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = "DENY"

EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_TIMEOUT = 5

ADMIN_URL = "admin/"
ADMINS = [("""LIneA""", "noreply@linea.org.br")]
MANAGERS = ADMINS

LOG_DIR = Path(env.str("DJANGO_LOG_DIR", default=str(BASE_DIR / "logs")))
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "%(levelname)s %(asctime)s %(module)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "djangosaml2": {
            "level": "DEBUG",
            "class": "logging.FileHandler",
            "filename": str(LOG_DIR / "djangosaml2.log"),
            "formatter": "verbose",
        },
    },
    "root": {"level": LOGGING_LEVEL, "handlers": ["console"]},
    "loggers": {
        "djangosaml2": {
            "level": "DEBUG",
            "handlers": ["djangosaml2", "console"],
            "propagate": False,
        },
    },
}

ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", False)
ACCOUNT_LOGIN_METHODS = {"username"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "username*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "optional"
ACCOUNT_ADAPTER = "wkfw.users.adapters.AccountAdapter"
ACCOUNT_FORMS = {"signup": "wkfw.users.forms.UserSignupForm"}
SOCIALACCOUNT_ADAPTER = "wkfw.users.adapters.SocialAccountAdapter"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}
CORS_URLS_REGEX = r"^/api/.*$"
SPECTACULAR_SETTINGS = {
    "TITLE": "WKFW Dashboard API",
    "DESCRIPTION": "Data release workflow operations API",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.IsAdminUser"],
}

AUTH_SAML2_ENABLED = env.bool("AUTH_SAML2_ENABLED", default=False)
LINEA_LOGIN_URL = env.str("LINEA_LOGIN_URL", default="/admin/login/?next=/")
RUBIN_LOGIN_URL = env.str("RUBIN_LOGIN_URL", default="/admin/login/?next=/")
LINEA_REGISTER_URL = env.str(
    "LINEA_REGISTER_URL",
    default="https://register-dev.linea.org.br/",
)
RUBIN_REGISTER_URL = env.str(
    "RUBIN_REGISTER_URL",
    default="https://register-dev.linea.org.br/",
)
INTERNAL_GROUPS = env.list("INTERNAL_GROUPS", default=[])
NAVBAR_IDAC_URL = env.str("NAVBAR_IDAC_URL", default="https://scienceplatform-dev.linea.org.br/idac")
NAVBAR_DATA_URL = env.str("NAVBAR_DATA_URL", default="https://data.linea.org.br/")
NAVBAR_DOCS_URL = env.str("NAVBAR_DOCS_URL", default="https://docs.linea.org.br/")

SETTINGS_EXPORT = [
    "AUTH_SAML2_ENABLED",
    "LINEA_LOGIN_URL",
    "LINEA_REGISTER_URL",
    "RUBIN_LOGIN_URL",
    "RUBIN_REGISTER_URL",
    "NAVBAR_IDAC_URL",
    "NAVBAR_DATA_URL",
    "NAVBAR_DOCS_URL",
]

if AUTH_SAML2_ENABLED:
    import saml2

    SITE_URL = env.str("SITE_URL")
    FQDN = SITE_URL
    SAML_SP_NAME = env.str("SAML_SP_NAME", default="SP WKFW Dashboard")
    CERT_DIR = BASE_DIR / "config" / "certificates"
    ATTR_DIR = BASE_DIR / "config" / "attribute-maps"

    INSTALLED_APPS += ["djangosaml2"]
    AUTHENTICATION_BACKENDS += ["wkfw.users.saml2.LineaSaml2Backend"]
    MIDDLEWARE += ["djangosaml2.middleware.SamlSessionMiddleware"]
    SAML_ACS_FAILURE_RESPONSE_FUNCTION = "wkfw.users.views.saml2_template_failure"
    SAML_SESSION_COOKIE_NAME = "saml_session"
    SESSION_COOKIE_SECURE = True
    LOGIN_URL = "/login/"
    SESSION_EXPIRE_AT_BROWSER_CLOSE = False
    SAML_DEFAULT_BINDING = saml2.BINDING_HTTP_POST
    SAML_IGNORE_LOGOUT_ERRORS = True
    SAML_CREATE_UNKNOWN_USER = True
    SAML_CSP_HANDLER = ""
    SAML_ATTRIBUTE_MAPPING = {
        "eduPersonUniqueId": ("username",),
        "cn": ("first_name",),
        "sn": ("last_name",),
        "email": ("email",),
    }
    SAML_CONFIG = {
        "xmlsec_binary": "/usr/bin/xmlsec1",
        "entityid": FQDN + "/saml2/metadata/",
        "attribute_map_dir": str(ATTR_DIR),
        "description": SAML_SP_NAME,
        "service": {
            "sp": {
                "name": SAML_SP_NAME,
                "ui_info": {
                    "display_name": {"text": SAML_SP_NAME, "lang": "en"},
                    "description": {"text": SAML_SP_NAME, "lang": "en"},
                    "information_url": {"text": FQDN, "lang": "en"},
                    "privacy_statement_url": {"text": FQDN, "lang": "en"},
                },
                "name_id_format": [
                    "urn:oasis:names:tc:SAML:2.0:nameid-format:persistent",
                    "urn:oasis:names:tc:SAML:2.0:nameid-format:transient",
                ],
                "endpoints": {
                    "assertion_consumer_service": [
                        (FQDN + "/saml2/acs/", saml2.BINDING_HTTP_POST),
                    ],
                    "single_logout_service": [
                        (FQDN + "/saml2/ls/", saml2.BINDING_HTTP_REDIRECT),
                        (FQDN + "/saml2/ls/post", saml2.BINDING_HTTP_POST),
                    ],
                },
                "force_authn": False,
                "name_id_format_allow_create": False,
                "want_response_signed": True,
                "authn_requests_signed": True,
                "want_assertions_signed": False,
                "only_use_keys_in_metadata": True,
                "allow_unsolicited": False,
            },
        },
        "metadata": {
            "remote": [
                {"url": env.str("SAML_IDP_METADATA_URL")},
            ],
        },
        "debug": True,
        "key_file": str(CERT_DIR / "private.key"),
        "cert_file": str(CERT_DIR / "public.cert"),
        "encryption_keypairs": [
            {
                "key_file": str(CERT_DIR / "private.key"),
                "cert_file": str(CERT_DIR / "public.cert"),
            }
        ],
        "contact_person": [
            {
                "given_name": "LIneA",
                "email_address": "noreply@linea.org.br",
                "contact_type": "technical",
            }
        ],
        "organization": {
            "name": [{"text": "LIneA", "lang": "en"}],
            "display_name": [{"text": "LIneA", "lang": "en"}],
            "url": [{"text": "https://www.linea.org.br/", "lang": "en"}],
        },
    }
