import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.users.models import ExternalIdentity

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.fixture
def identity(db):
    return ExternalIdentity.objects.create(
        email="alice@linea.org.br",
        name="Alice Silva",
        github_handle="alicegh",
        slack_id="U1234ALICE",
    )


@pytest.mark.django_db
def test_api_lists_external_identities(user, identity):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/external-identities/")
    assert res.status_code == 200
    assert res.data[0]["email"] == "alice@linea.org.br"
    assert res.data[0]["name"] == "Alice Silva"
    assert res.data[0]["github_handle"] == "alicegh"
    assert res.data[0]["slack_id"] == "U1234ALICE"


@pytest.mark.django_db
def test_api_external_identities_readonly(user, identity):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post(
        "/api/external-identities/",
        {"email": "bob@linea.org.br", "github_handle": "bobgh", "slack_id": "U5678BOB"},
        format="json",
    )
    assert res.status_code == 405
    assert not ExternalIdentity.objects.filter(email="bob@linea.org.br").exists()


@pytest.mark.django_db
def test_api_external_identities_requires_auth(identity):
    res = APIClient().get("/api/external-identities/")
    # IsAuthenticated + SessionAuthentication: request anônimo é 403 (padrão do projeto)
    assert res.status_code == 403
