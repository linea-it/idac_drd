from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IntegrationsConfig(AppConfig):
    name = "idac_drd.integrations"
    verbose_name = _("External integrations")
