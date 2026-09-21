"""Play/pause: uma sessão aberta por assignee; effort = soma das sessões."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, ActivityWorkSession
from idac_drd.workflow.services import (
    WorkflowError,
    activity_effort_seconds,
    add_activity,
    pause_activity,
    play_activity,
    transition_activity,
)
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def release(db):
    return make_release("PlayTest", slug="play-test")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass", email="alice@linea.org.br")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="carol", password="pass", email="carol@linea.org.br")


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(username="admin", password="pass", email="admin@linea.org.br")


@pytest.fixture
def identity(db):
    return ExternalIdentity.objects.create(email="alice@linea.org.br", name="Alice")


@pytest.fixture
def identity_b(db):
    return ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob")


@pytest.mark.django_db
def test_play_requires_assignee(release, user):
    a1 = release.activities.get(key="step-1")
    with pytest.raises(WorkflowError, match="Assign someone"):
        play_activity(a1, actor=user)


@pytest.mark.django_db
def test_play_forbidden_for_other_user(release, other_user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    with pytest.raises(WorkflowError, match="assignee or a superuser"):
        play_activity(a1, actor=other_user)


@pytest.mark.django_db
def test_superuser_can_play_and_pause(release, superuser, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=superuser)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 1
    pause_activity(a1, actor=superuser)
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_play_opens_session_and_moves_to_in_progress(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert a1.started_at is not None
    open_sessions = ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True)
    assert open_sessions.count() == 1
    assert open_sessions.get().assignee_id == identity.id


@pytest.mark.django_db
def test_play_switch_pauses_previous(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)

    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    a2 = release.activities.get(key="step-2")
    a2.assignee = identity
    a2.save(update_fields=["assignee"])
    play_activity(a2, actor=user)

    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0
    assert ActivityWorkSession.objects.filter(activity=a2, ended_at__isnull=True).count() == 1
    closed = ActivityWorkSession.objects.filter(activity=a1).order_by("id")
    assert closed.exists()
    assert closed.last().end_reason in (
        ActivityWorkSession.EndReason.REVIEW,
        ActivityWorkSession.EndReason.DONE,
    )


@pytest.mark.django_db
def test_play_auto_pauses_other_in_progress(release, user, identity):
    """Duas activities do mesmo assignee: play na 2ª pausa a 1ª sem concluir."""
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)

    step = a1.step
    a3 = add_activity(release, label="Parallel", step=step, key="parallel", assignee=identity)
    play_activity(a3, actor=user)

    a1.refresh_from_db()
    a3.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert a3.status == Activity.Status.IN_PROGRESS
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0
    assert ActivityWorkSession.objects.filter(activity=a3, ended_at__isnull=True).count() == 1
    paused = ActivityWorkSession.objects.get(activity=a1)
    assert paused.end_reason == ActivityWorkSession.EndReason.PLAY_SWITCH


@pytest.mark.django_db
def test_pause_closes_session(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)
    pause_activity(a1, actor=user)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0
    session = ActivityWorkSession.objects.get(activity=a1)
    assert session.end_reason == ActivityWorkSession.EndReason.PAUSE
    assert session.ended_at is not None


@pytest.mark.django_db
def test_rejection_does_not_auto_open_session(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)
    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user, comment="faltou schema")
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0


@pytest.mark.django_db
def test_status_in_progress_opens_session(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user)
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_api_play_pause(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(f"/api/activities/{a1.id}/play/")
    assert res.status_code == 200
    assert res.data["status"] == "in_progress"
    assert res.data["is_playing"] is True
    assert res.data["playing_since"] is not None
    assert res.data["effort_seconds"] >= 0
    assert res.data.get("paused_activities") == []

    res = client.post(f"/api/activities/{a1.id}/pause/")
    assert res.status_code == 200
    assert res.data["is_playing"] is False
    assert res.data["status"] == "in_progress"


@pytest.mark.django_db
def test_api_play_reports_paused_switch(release, user, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    from idac_drd.workflow.services import add_activity

    a3 = add_activity(release, label="Parallel", step=a1.step, key="parallel", assignee=identity)
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.post(f"/api/activities/{a1.id}/play/").status_code == 200
    res = client.post(f"/api/activities/{a3.id}/play/")
    assert res.status_code == 200
    assert res.data["is_playing"] is True
    assert res.data["paused_activities"] == [{"id": a1.id, "label": a1.label}]


@pytest.mark.django_db
def test_reassign_closes_session(release, user, identity, identity_b):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    play_activity(a1, actor=user)
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch(f"/api/activities/{a1.id}/", {"assignee_id": identity_b.id}, format="json")
    assert res.status_code == 200
    assert ActivityWorkSession.objects.filter(activity=a1, ended_at__isnull=True).count() == 0
    assert ActivityWorkSession.objects.get(activity=a1).end_reason == ActivityWorkSession.EndReason.REASSIGN


@pytest.mark.django_db
def test_effort_sums_sessions(release, identity):
    a1 = release.activities.get(key="step-1")
    a1.assignee = identity
    a1.save(update_fields=["assignee"])
    now = timezone.now()
    ActivityWorkSession.objects.create(
        activity=a1,
        assignee=identity,
        started_at=now - timedelta(seconds=100),
        ended_at=now - timedelta(seconds=40),
        end_reason=ActivityWorkSession.EndReason.PAUSE,
    )
    ActivityWorkSession.objects.create(
        activity=a1,
        assignee=identity,
        started_at=now - timedelta(seconds=20),
        ended_at=None,
    )
    effort = activity_effort_seconds(a1, now=now)
    assert abs(effort - 80) < 1
