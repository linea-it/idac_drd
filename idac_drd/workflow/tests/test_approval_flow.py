"""Conclusão: quem executa marca os objetivos e vai de in_progress para done.

in_review deixa de ser entrada do fluxo. Linha que já está nesse status
ainda pode ser concluída ou devolvida (compatibilidade).
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


def _ready(activity, actor):
    transition_activity(activity, to_status=Activity.Status.IN_PROGRESS, actor=actor)
    prime_effort(activity, actor)


def test_done_from_todo_is_rejected(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    with pytest.raises(WorkflowError, match="Complete only from In progress"):
        transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)


def test_entering_in_review_is_rejected(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    _ready(a1, alice)
    with pytest.raises(WorkflowError, match="Complete the activity from In progress"):
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=alice)


def test_done_requires_every_objective(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    a1.objectives = "[x] Validar schema\n[ ] Gerar dataset"
    a1.save(update_fields=["objectives"])
    _ready(a1, alice)
    with pytest.raises(WorkflowError, match="Check every objective"):
        transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)
    a1.objectives = "[x] Validar schema\n[x] Gerar dataset"
    a1.save(update_fields=["objectives"])
    transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_done_without_objectives(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    _ready(a1, alice)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_legacy_in_review_can_still_complete(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    a1.status = Activity.Status.IN_REVIEW
    a1.objectives = "[ ] Ainda aberto"
    a1.save(update_fields=["status", "objectives"])
    transition_activity(a1, to_status=Activity.Status.DONE, actor=alice)
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_legacy_rejection_requires_reason(approval_release, alice):
    a1 = approval_release.activities.get(key="a1")
    a1.status = Activity.Status.IN_REVIEW
    a1.save(update_fields=["status"])
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


def test_api_complete_from_in_progress(approval_release, alice, bob):
    """in_progress → done via PATCH. Objetivos marcados no mesmo request."""
    a1 = approval_release.activities.get(key="a1")
    a1.objectives = "Validar schema"
    a1.save(update_fields=["objectives"])
    alice_client = _client_for(alice)
    bob_client = _client_for(bob)

    assert (
        alice_client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress", "notes": "trabalhando"}).status_code
        == 200
    )
    prime_effort(a1, alice)
    assert (
        alice_client.patch(
            f"/api/activities/{a1.id}/",
            {"status": "done", "objectives": "[ ] Validar schema"},
        ).status_code
        == 400
    )
    assert (
        alice_client.patch(
            f"/api/activities/{a1.id}/",
            {"status": "done", "objectives": "[x] Validar schema"},
        ).status_code
        == 200
    )

    a2 = approval_release.activities.get(key="a2")
    assert bob_client.patch(f"/api/activities/{a2.id}/", {"status": "done"}).status_code == 400
    a1.refresh_from_db()
    assert a1.status == Activity.Status.DONE


def test_api_legacy_rejection_requires_comment(approval_release, alice):
    """Linha ainda em in_review: voltar sem motivo → 400; com motivo → 200."""
    a1 = approval_release.activities.get(key="a1")
    a1.status = Activity.Status.IN_REVIEW
    a1.save(update_fields=["status"])
    client = _client_for(alice)

    assert client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress"}).status_code == 400

    r = client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress", "comment": "Faltou validar o schema"})
    assert r.status_code == 200
    a1.refresh_from_db()
    assert a1.status == Activity.Status.IN_PROGRESS
    assert a1.transitions.last().comment == "Faltou validar o schema"
