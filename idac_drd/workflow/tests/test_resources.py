"""Campo ``resources`` (links de documentação) em steps e activities.

Cobre validação no serializer (apenas URLs http(s), rótulo opcional) e a
persistência via API em steps (POST/PATCH) e activities (POST/PATCH).
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.workflow.models import DataRelease
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()

#: label ausente é normalizada para "" pelo validador
VALID_RESOURCES = [
    {"label": "Setup guide", "url": "https://docs.google.com/d/abc"},
    {"label": "", "url": "http://wiki.internal/instructions"},
]


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.mark.django_db
def test_step_resources_roundtrip(user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/releases/{release.slug}/steps/",
        {"label": "Step X", "resources": VALID_RESOURCES},
        format="json",
    )
    assert res.status_code == 201
    step = release.steps.get(key="step-x")
    assert step.resources == VALID_RESOURCES

    # PATCH substitui a lista
    res = client.patch(
        f"/api/releases/{release.slug}/steps/{step.id}/",
        {"resources": [{"label": "Only", "url": "https://docs.google.com/d/xyz"}]},
        format="json",
    )
    assert res.status_code == 200
    step.refresh_from_db()
    assert step.resources == [{"label": "Only", "url": "https://docs.google.com/d/xyz"}]

    # GET devolve os resources
    res = client.get(f"/api/releases/{release.slug}/")
    step_json = next(s for s in res.json()["steps"] if s["id"] == step.id)
    assert step_json["resources"] == [{"label": "Only", "url": "https://docs.google.com/d/xyz"}]


@pytest.mark.django_db
def test_step_resources_rejects_non_http_urls(user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/releases/{release.slug}/steps/",
        {"label": "Step X", "resources": [{"label": "Bad", "url": "javascript:alert(1)"}]},
        format="json",
    )
    assert res.status_code == 400

    step = release.steps.first()
    res = client.patch(
        f"/api/releases/{release.slug}/steps/{step.id}/",
        {"resources": [{"url": ""}]},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_activity_resources_roundtrip(user):
    release = make_release("Plano", status="draft")
    step = release.steps.first()
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "Activity X", "step_id": step.id, "resources": VALID_RESOURCES},
        format="json",
    )
    assert res.status_code == 201
    act = release.activities.get(key="activity-x")
    assert act.resources == VALID_RESOURCES

    # PATCH no serializer do modelo também valida
    res = client.patch(
        f"/api/activities/{act.id}/",
        {"resources": [{"label": "Runbook", "url": "https://runbook.example.org/x"}]},
        format="json",
    )
    assert res.status_code == 200
    act.refresh_from_db()
    assert act.resources == [{"label": "Runbook", "url": "https://runbook.example.org/x"}]

    res = client.patch(
        f"/api/activities/{act.id}/",
        {"resources": [{"url": "ftp://not-allowed"}]},
        format="json",
    )
    assert res.status_code == 400
    act.refresh_from_db()
    assert act.resources == [{"label": "Runbook", "url": "https://runbook.example.org/x"}]


@pytest.mark.django_db
def test_clone_release_copies_resources(user):
    release = make_release(
        "Origem",
        steps=[{"key": "a", "label": "Step A"}],
        activities=[{"key": "x", "label": "Activity X", "step": "a"}],
    )
    step = release.steps.get(key="a")
    act = release.activities.get(key="x")
    step.resources = VALID_RESOURCES
    step.save(update_fields=["resources"])
    act.resources = VALID_RESOURCES
    act.save(update_fields=["resources"])

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post(
        "/api/releases/",
        {"name": "Clone", "copy_from_release_slug": release.slug},
        format="json",
    )
    assert res.status_code == 201
    clone = DataRelease.objects.get(slug="clone")
    assert clone.steps.get(key="a").resources == VALID_RESOURCES
    assert clone.activities.get(key="x").resources == VALID_RESOURCES
