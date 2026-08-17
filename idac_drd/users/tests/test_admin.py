import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model

from idac_drd.users.models import ExternalIdentity

User = get_user_model()


def test_external_identity_registered_in_admin():
    assert admin.site.is_registered(ExternalIdentity)


@pytest.mark.django_db
def test_external_identity_changelist_renders(admin_client):
    # Admin renderiza a changelist; cobre regressões como __str__ retornando None
    # (caso real: Luigi sem email no identities.yaml)
    ExternalIdentity.objects.create(name="Sem Email", slack_id="U0000")
    ExternalIdentity.objects.create(email="alice@linea.org.br")
    res = admin_client.get("/admin/users/externalidentity/")
    assert res.status_code == 200
    assert "alice@linea.org.br" in res.content.decode()
