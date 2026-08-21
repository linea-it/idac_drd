from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from idac_drd.integrations.github import GitHubAPIError
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture(autouse=True)
def clear_github_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def release(db):
    # Campos estruturais (repo/area/size) só podem ser alterados em draft
    return make_release("DP-Test", slug="dp-test", status="draft")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.fixture
def client(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.mark.django_db
def test_options_empty_without_token(client):
    with override_settings(GH_TOKEN=""):
        res = client.get("/api/github/options/")
    assert res.status_code == 200
    assert res.data == {
        "repos": [],
        "areas": [],
        "sizes": [],
        "statuses": [],
        "error": "GH_TOKEN not set",
    }


@pytest.mark.django_db
@mock.patch(
    "idac_drd.integrations.github.GitHubClient.project_single_select_options",
    return_value=([], [], []),
)
@mock.patch(
    "idac_drd.integrations.github.GitHubClient.list_org_repos",
    side_effect=GitHubAPIError("boom"),
)
def test_options_includes_error_on_api_failure(mock_repos, mock_project, client):
    with override_settings(GH_TOKEN="token"):
        res = client.get("/api/github/options/")
    assert res.status_code == 200
    assert res.data["repos"] == []
    assert res.data["error"] == "boom"


@pytest.mark.django_db
@mock.patch(
    "idac_drd.workflow.api.views.fetch_github_options",
    return_value={"repos": ["r1"], "areas": ["Área X"], "sizes": ["M"]},
)
def test_options_returns_fetched_and_caches(mock_fetch, client):
    res1 = client.get("/api/github/options/")
    res2 = client.get("/api/github/options/")
    assert res1.status_code == 200
    assert res1.data == {"repos": ["r1"], "areas": ["Área X"], "sizes": ["M"]}
    assert res2.data == res1.data
    assert mock_fetch.call_count == 1  # segunda chamada vem do cache


@pytest.mark.django_db
def test_create_activity_with_repo_area_size(client, release):
    step_id = release.steps.first().id
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {
            "label": "Activity nova",
            "step_id": step_id,
            "github_repo": "linea-it/idac_drd",
            "area": "Ingestão",
            "size": "M",
        },
        format="json",
    )
    assert res.status_code == 201
    assert res.data["github_repo"] == "linea-it/idac_drd"
    assert res.data["area"] == "Ingestão"
    assert res.data["size"] == "M"
    activity = release.activities.get(key=res.data["key"])
    assert activity.github_repo == "linea-it/idac_drd"
    assert activity.area == "Ingestão"
    assert activity.size == "M"


@pytest.mark.django_db
def test_create_activity_defaults_blank(client, release):
    step_id = release.steps.first().id
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "Activity simples", "step_id": step_id},
        format="json",
    )
    assert res.status_code == 201
    assert res.data["github_repo"] == ""
    assert res.data["area"] == ""
    assert res.data["size"] == ""


@pytest.mark.django_db
def test_patch_updates_repo_area_size(client, release):
    activity = release.activities.first()
    res = client.patch(
        f"/api/activities/{activity.id}/",
        {"github_repo": "linea-it/other", "area": "Alertas", "size": "L"},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["github_repo"] == "linea-it/other"
    assert res.data["area"] == "Alertas"
    assert res.data["size"] == "L"
    activity.refresh_from_db()
    assert activity.github_repo == "linea-it/other"
    assert activity.area == "Alertas"
    assert activity.size == "L"
