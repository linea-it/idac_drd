from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, EmailField, Model
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    name = CharField(_("Name of User"), blank=True, max_length=255)

    def get_absolute_url(self) -> str:
        return reverse("users:detail", kwargs={"username": self.username})


class ExternalIdentity(Model):
    """Mapa email -> identidades externas (GitHub, Slack) de um assignee.

    Separada do User/login: o SAML continua sendo a única fonte de autenticação;
    esta tabela só resolve "quem é quem" pelo email após autenticado.
    """

    email = EmailField(_("Email"), unique=True, blank=True, null=True)
    name = CharField(_("Name"), blank=True, max_length=255)
    github_handle = CharField(_("GitHub handle"), blank=True, max_length=39)
    slack_id = CharField(
        _("Slack ID"),
        blank=True,
        max_length=20,
        help_text=_("Slack member ID, e.g. U0123ABCDEF."),
    )

    def __str__(self) -> str:
        return self.email or self.name or self.slack_id or "?"
