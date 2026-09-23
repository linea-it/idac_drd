from .base import *  # noqa: F403

DEBUG = False
SECRET_KEY = "test-secret-key"
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
AUTH_SAML2_ENABLED = False

# Testes nunca tocam integrações reais: as flags do base vêm do env (que pode
# estar True no container) — sem isso, pytest cria tickets GLPI/issues GitHub
# de verdade. Os testes de sync ligam via override_settings(ENABLED) por teste.
GH_ENABLED = False
GLPI_ENABLED = False
SLACK_ENABLED = False
# Canal/DM dev também vêm do env e desviariam os testes para post_to_channel.
SLACK_CHANNEL_ID = ""
SLACK_DEV_USER_ID = ""
# on_commit executa a integração na hora (sem fila). A suíte não espera thread.
INTEGRATIONS_EAGER = True
