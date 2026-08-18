"""Guards da API: destrutivos, rate limiting e analytics. (P0/P1 da revisão)

DELETE de release é permitido só para drafts (204); releases iniciadas ou
arquivadas seguem 405. Throttle do DRF protege a API inteira, e o analytics
expõe mediana (robusta a outliers) além da média.
"""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


# ── destrutivos ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_delete_draft_release(user):
    release = make_release("Plano", status="planned")
    step_id = release.steps.first().id
    activity_id = release.activities.first().id
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.delete(f"/api/releases/{release.slug}/")
    assert res.status_code == 204
    from idac_drd.workflow.models import Activity, ActivityTransition, ReleaseStep

    assert not ReleaseStep.objects.filter(id=step_id).exists()
    assert not Activity.objects.filter(id=activity_id).exists()
    assert not ActivityTransition.objects.filter(activity_id=activity_id).exists()


@pytest.mark.django_db
def test_api_delete_release_denied_for_official_history(user):
    # releases em execução/arquivadas são histórico oficial: DELETE → 405
    active = make_release("Active")
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.delete(f"/api/releases/{active.slug}/")
    assert res.status_code == 405

    archived = make_release("Archived", status="archived")
    res = client.delete(f"/api/releases/{archived.slug}/")
    assert res.status_code == 405

    completed = make_release("Completed", status="completed")
    res = client.delete(f"/api/releases/{completed.slug}/")
    assert res.status_code == 405


@pytest.mark.django_db
def test_activity_delete_only_todo(user):
    # em draft qualquer status é removível (blocked nasce de deps pendentes e
    # nada começou); em execução o limite é o estado da atividade (não apagar
    # histórico de uma atividade que já começou).
    client = APIClient()
    client.force_authenticate(user=user)

    draft = make_release("Plano", status="planned")
    blocked_in_draft = draft.activities.get(key="step-2")  # nasce blocked (dep pendente)
    assert blocked_in_draft.status == "blocked"
    res = client.delete(f"/api/activities/{blocked_in_draft.id}/")
    assert res.status_code == 204  # blocked em draft: permitido

    no_deps = [
        {"key": "s1", "label": "S1", "step": "a"},
        {"key": "s2", "label": "S2", "step": "a"},
    ]
    active = make_release("Active", activities=no_deps)
    act = active.activities.first()
    res = client.delete(f"/api/activities/{act.id}/")
    assert res.status_code == 204  # todo em execução: permitido também

    act.status = "in_progress"
    act.save()
    res = client.delete(f"/api/activities/{act.id}/")
    assert res.status_code == 400  # iniciada: não se apaga histórico

    blocked = make_release("Active2", slug="active2")
    blocked_act = blocked.activities.get(key="step-2")  # nasce blocked
    res = client.delete(f"/api/activities/{blocked_act.id}/")
    assert res.status_code == 400  # blocked em execução: não se apaga histórico


# ── rate limiting ────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_user_throttle_applied(user, monkeypatch):
    # THROTTLE_RATES é um class attr congelado no primeiro import do módulo;
    # override_settings não o afeta depois disso — monkeypatch no attr é a via certa.
    monkeypatch.setattr(SimpleRateThrottle, "THROTTLE_RATES", {"user": "2/min"})
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.get("/api/releases/").status_code == 200
    assert client.get("/api/releases/").status_code == 200
    assert client.get("/api/releases/").status_code == 429


# ── analytics ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_analytics_median_and_avg(user):
    activities = [
        {"key": "s1", "label": "S1", "step": "a", "depends_on": []},
        {"key": "s2", "label": "S2", "step": "a", "depends_on": ["s1"]},
        {"key": "s3", "label": "S3", "step": "a", "depends_on": ["s2"]},
    ]
    release = make_release("Analytics", slug="analytics-test", activities=activities)
    now = timezone.now()
    for key, seconds in (("s1", 100), ("s2", 200), ("s3", 900)):
        act = release.activities.get(key=key)
        act.started_at = now - timedelta(seconds=seconds)
        act.completed_at = now
        act.save()

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.get("/api/analytics/bottlenecks/?release=analytics-test")
    assert res.status_code == 200
    stats = res.data["primary"]
    assert stats["avg_duration_seconds"] == 400
    assert stats["median_duration_seconds"] == 200  # robusta ao outlier de 900
    assert stats["bottleneck"]["key"] == "s3"
