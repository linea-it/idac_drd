import pytest
from django.db import IntegrityError

from idac_drd.users.models import ExternalIdentity


@pytest.mark.django_db
def test_external_identity_fields(external_identity):
    assert external_identity.email == "alice@linea.org.br"
    assert external_identity.github_handle == "alicegh"
    assert external_identity.slack_id == "U1234ALICE"
    assert str(external_identity) == "alice@linea.org.br"


@pytest.mark.django_db
def test_external_identity_name_optional(db):
    identity = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob Silva")
    assert identity.name == "Bob Silva"


@pytest.mark.django_db
def test_external_identity_blanks_are_optional(db):
    identity = ExternalIdentity.objects.create(email="bob@linea.org.br")
    assert identity.github_handle == ""
    assert identity.slack_id == ""


@pytest.mark.django_db
def test_external_identity_email_unique(external_identity):
    with pytest.raises(IntegrityError):
        ExternalIdentity.objects.create(email="alice@linea.org.br")
