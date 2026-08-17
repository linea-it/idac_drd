import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def release(db):
    return make_release("DP-Test", slug="dp-test")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.fixture
def identity(db):
    return ExternalIdentity.objects.create(email="alice@linea.org.br", name="Alice Silva")


@pytest.mark.django_db
def test_assignee_is_external_identity(release, user, identity):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.first()
    res = client.patch(f"/api/activities/{activity.id}/", {"assignee_id": identity.id}, format="json")
    assert res.status_code == 200
    assert res.data["assignee"]["email"] == "alice@linea.org.br"
    assert res.data["assignee"]["name"] == "Alice Silva"
    assert "username" not in res.data["assignee"]
    activity.refresh_from_db()
    assert activity.assignee_id == identity.id


@pytest.mark.django_db
def test_assignee_rejects_user_id(release, user, identity):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.first()
    ghost = User.objects.create_user(username="ghost", password="pass")
    # user e identity têm sequences independentes (ambos começam em 1): se o id
    # do ghost coincidir com uma identidade, o PATCH passaria — usa pk alto então.
    bad_id = ghost.id if not ExternalIdentity.objects.filter(pk=ghost.id).exists() else 999999
    res = client.patch(f"/api/activities/{activity.id}/", {"assignee_id": bad_id}, format="json")
    assert res.status_code == 400
    activity.refresh_from_db()
    assert activity.assignee is None


@pytest.mark.django_db
def test_assignee_can_be_unset(release, user, identity):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.first()
    activity.assignee = identity
    activity.save()
    res = client.patch(f"/api/activities/{activity.id}/", {"assignee_id": None}, format="json")
    assert res.status_code == 200
    assert res.data["assignee"] is None
    activity.refresh_from_db()
    assert activity.assignee_id is None


@pytest.mark.django_db
def test_export_uses_identity_email(release, user, identity):
    activity = release.activities.first()
    activity.assignee = identity
    activity.save()
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/analytics/bottlenecks/?release=dp-test")
    assert res.status_code == 200
    rows = res.data["primary"]["activities"]
    with_assignee = next(r for r in rows if r["key"] == activity.key)
    assert with_assignee["assignee"] == "alice@linea.org.br"
    no_assignee = next(r for r in rows if r["key"] != activity.key)
    assert no_assignee["assignee"] is None
