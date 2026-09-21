"""Fluxo de aprovação: done = aceito por qualquer pessoa autenticada.

in_progress → in_review (executor entrega) → done (qualquer um aprova) |
in_progress (rejeição com motivo). Assignees das atividades dependentes
são avisados no Slack; não há gate de papel (staff / próximo do step).
"""

import pytest
from django.contrib.auth import get_user_model

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import (
    WorkflowError,
    add_activity,
    add_step_to_release,
    create_draft,
    transition_activity,
)
from idac_drd.workflow.tests.helpers import make_release, prime_effort

User = get_user_model()


@pytest.fixture
def identity(db):
    return ExternalIdentity.objects.create(email="alice@linea.org.br", name="Alice")


@pytest.fixture
def approval_release(db, identity):
    release = DataRelease.objects.create(name="Approval", slug="approval", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=identity)
    return release


@pytest.fixture
def alice(db):
    return User.objects.create_user(username="alice", email="alice@linea.org.br", password="pass")


@pytest.fixture
def bob(db):
    return User.objects.create_user(username="bob", email="bob@linea.org.br", password="pass")


@pytest.fixture
def admin(db):
    return User.objects.create_user(username="admin", email="admin@linea.org.br", password="pass", is_staff=True)


def send_to_review(activity, actor):
    transition_activity(activity, to_status=Activity.Status.IN_PROGRESS, actor=actor)
    prime_effort(activity, actor)
    transition_activity(activity, to_status=Activity.Status.IN_REVIEW, actor=actor)


def test_done_requires_review(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=alice)
    with pytest.raises(WorkflowError, match="Approve only from In review"):
        transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)


def test_in_review_requires_progress(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    with pytest.raises(WorkflowError, match="Send to review only from In progress"):
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=alice)


def test_next_activity_assignee_approves(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, alice)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_anyone_can_approve(approval_release, alice, bob):
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, alice)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=bob)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_staff_approves_anywhere(approval_release, admin):
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, admin)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=admin)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_last_activity_anyone_approves(approval_release, alice):
    a2 = approval_release.activities.get(key="a2")  # última do step
    send_to_review(a2, alice)
    transition_activity(a2, to_status=Activity.Status.DONE, actor=alice)
    a2.refresh_from_db()
    assert a2.status == Activity.Status.DONE


def test_next_without_assignee_anyone_approves(approval_release, bob):
    approval_release.activities.filter(key="a2").update(assignee=None)
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, bob)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=bob)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_system_actor_approves(approval_release):
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, None)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=None)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_rejection_requires_reason(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    send_to_review(a1, alice)
    with pytest.raises(WorkflowError, match="Add a reason"):
        transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=alice)
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=alice, comment="Faltou validar o schema")
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert a1.transitions.last().comment == "Faltou validar o schema"


def test_add_activity_stores_objectives(db):
    release = DataRelease.objects.create(name="O", slug="o", status=DataRelease.Status.ACTIVE)
    step = add_step_to_release(release, label="Step A")
    act = add_activity(release, step=step, label="Step", objectives="Meta 1\nMeta 2")
    assert act.objectives == "Meta 1\nMeta 2"


def test_clone_copies_objectives(db):
    activities = [
        {"key": "s1", "label": "S1", "step": "a", "objectives": "Objetivo único"},
    ]
    source = make_release("Source", activities=activities)
    release = create_draft(name="R", copy_from_release=source)
    assert release.activities.get(key="s1").objectives == "Objetivo único"


# --- fluxo completo via API (PATCH), como o ActivityDrawer chama ---


def _client_for(user):
    # JSON: mesmo content-type que o frontend (api.js) usa no PATCH
    from rest_framework.test import APIClient

    client = APIClient()
    client.force_authenticate(user)
    client.default_format = "json"
    return client


def test_api_full_approval_cycle(approval_release, alice, bob):
    """in_progress → in_review → done via PATCH; gate de origem (não de ator)."""
    a1 = approval_release.activities.get(key="a1")
    alice_client = _client_for(alice)
    bob_client = _client_for(bob)

    # executor entrega (payload do drawer inclui campos operacionais)
    assert (
        alice_client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress", "notes": "trabalhando"}).status_code
        == 200
    )
    prime_effort(a1, alice)
    assert alice_client.patch(f"/api/activities/{a1.id}/", {"status": "in_review"}).status_code == 200

    # done direto de in_progress → 400 (gate de origem)
    a2 = approval_release.activities.get(key="a2")
    assert bob_client.patch(f"/api/activities/{a2.id}/", {"status": "done"}).status_code == 400

    # bob não executou a1, mas qualquer pessoa pode aprovar
    assert bob_client.patch(f"/api/activities/{a1.id}/", {"status": "done"}).status_code == 200
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_api_rejection_requires_comment(approval_release, alice):
    """Rejeição via PATCH: sem motivo → 400; com motivo → 200 e comment salvo."""
    a1 = approval_release.activities.get(key="a1")
    client = _client_for(alice)
    client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress"})
    prime_effort(a1, alice)
    client.patch(f"/api/activities/{a1.id}/", {"status": "in_review"})

    assert client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress"}).status_code == 400

    r = client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress", "comment": "Faltou validar o schema"})
    assert r.status_code == 200
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert a1.transitions.last().comment == "Faltou validar o schema"
