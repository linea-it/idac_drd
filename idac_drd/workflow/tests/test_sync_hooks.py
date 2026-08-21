"""Hooks de integração nos services do workflow.

add_activity, _clone_structure, transition_activity e start_release agendam a
sync (GitHub/GLPI) via transaction.on_commit — a decisão de aplicar (gate de
execução + flags) fica dentro de integrations/sync.sync_activity.
"""

import pytest

from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import (
    add_activity,
    add_step_to_release,
    create_draft,
    delete_activity,
    move_activity,
    start_release,
    transition_activity,
    update_release_step,
)
from idac_drd.workflow.tests.helpers import make_release


@pytest.fixture
def active_release(db):
    release = DataRelease.objects.create(name="Release 1", slug="r1", status=DataRelease.Status.ACTIVE)
    ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    return release


@pytest.fixture
def queued(monkeypatch):
    """Captura as atividades agendadas para a sync."""
    calls = []
    monkeypatch.setattr("idac_drd.workflow.services._sync_later", calls.append)
    return calls


def test_add_activity_queues_sync(active_release, queued):
    act = add_activity(active_release, label="Step 1", step=active_release.steps.get())
    assert queued == [act]


def test_add_activity_in_draft_also_queues(queued, db):
    # o gate está na sync (release ACTIVE + flags); o hook é incondicional
    release = DataRelease.objects.create(name="D", slug="d", status=DataRelease.Status.DRAFT)
    step = ReleaseStep.objects.create(release=release, key="a", label="A", color="#000099")
    act = add_activity(release, label="Step 1", step=step)
    assert queued == [act]


def test_rename_release_allowed_only_in_draft(db, monkeypatch):
    """PATCH name: permitido em draft; bloqueado após iniciar a execução.

    O nome compõe o título das issues/tickets — renomear no meio da execução
    dessincronizaria as ferramentas (tickets GLPI fechados são terminais).
    """
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIClient

    user = get_user_model().objects.create_user(username="alice", password="pass")
    client = APIClient()
    client.force_authenticate(user)

    draft = DataRelease.objects.create(name="Draft", slug="draft", status=DataRelease.Status.DRAFT)
    res = client.patch("/api/releases/draft/", {"name": "Draft v2"}, format="json")
    assert res.status_code == 200
    assert res.json()["name"] == "Draft v2"

    active = DataRelease.objects.create(name="Active", slug="active", status=DataRelease.Status.ACTIVE)
    res = client.patch("/api/releases/active/", {"name": "Active v2"}, format="json")
    assert res.status_code == 400
    active.refresh_from_db()
    assert active.name == "Active"


def test_add_activity_resumes_completed_release(queued, db):
    release = DataRelease.objects.create(name="C", slug="c", status=DataRelease.Status.COMPLETED)
    step = ReleaseStep.objects.create(release=release, key="a", label="A", color="#000099")
    add_activity(release, label="Step 1", step=step)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE


def test_add_step_resumes_completed_release(db):
    release = DataRelease.objects.create(name="C", slug="c2", status=DataRelease.Status.COMPLETED)
    add_step_to_release(release, label="Step A")
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE


def test_transition_queues_sync(active_release, queued):
    act = add_activity(active_release, label="Step 1", step=active_release.steps.get())
    queued.clear()
    transition_activity(act, to_status=Activity.Status.IN_PROGRESS)
    assert queued == [act]


def test_start_release_queues_every_activity(queued, db):
    release = DataRelease.objects.create(name="P", slug="p", status=DataRelease.Status.DRAFT)
    step = add_step_to_release(release, label="Step A")
    add_activity(release, label="Step 1", step=step)
    add_activity(release, label="Step 2", step=step)

    queued.clear()
    start_release(release)

    assert [a.label for a in queued] == ["Step 1", "Step 2"]


def test_clone_into_active_release_queues_each_activity(queued, db):
    source = make_release("Source", status="active")
    queued.clear()
    create_draft(name="R", copy_from_release=source)
    assert sorted(a.key for a in queued) == ["step-1", "step-2"]


def test_clone_strips_objective_marks(db):
    # marcação [x]/[ ] é de execução: a release clonada nasce com objetivos limpos
    source = make_release("Source", status="active")
    act = source.activities.get(key="step-1")
    act.objectives = "[x] Criar schemas\n[ ] Processar ingestao"
    act.save(update_fields=["objectives"])
    clone = create_draft(name="R", copy_from_release=source)
    assert clone.activities.get(key="step-1").objectives == "Criar schemas\nProcessar ingestao"


def test_move_activity_queues_sync(active_release, queued):
    # o título do ticket contém o label do step — mover re-sincroniza
    act = add_activity(active_release, label="Step 1", step=active_release.steps.get())
    step_b = add_step_to_release(active_release, label="Step B")
    queued.clear()
    move_activity(act, step=step_b)
    assert queued == [act]


def test_rename_step_queues_sync_of_its_activities(active_release, queued):
    act = add_activity(active_release, label="Step 1", step=active_release.steps.get())
    queued.clear()
    update_release_step(active_release.steps.get(), label="Step A v2")
    assert queued == [act]


def test_delete_activity_queues_cleanup(active_release, monkeypatch):
    cleanup_calls = []
    monkeypatch.setattr(
        "idac_drd.workflow.services._cleanup_after_delete_later",
        lambda **kwargs: cleanup_calls.append(kwargs),
    )
    act = add_activity(active_release, label="Step 1", step=active_release.steps.get())
    delete_activity(act)
    assert cleanup_calls == [
        {
            "release_status": DataRelease.Status.ACTIVE,
            "github_repo": "",
            "github_issue_number": None,
            "glpi_ticket_id": None,
            "label": "Step 1",
        }
    ]


@pytest.mark.django_db(transaction=True)
def test_on_commit_runs_sync_after_commit(monkeypatch):
    """O caminho real: start_release agenda on_commit; o callback roda no commit."""
    calls = []
    # sync_activity agora recebe (activity, actor=None)
    monkeypatch.setattr("idac_drd.integrations.sync.sync_activity", lambda a, actor=None: calls.append(a))

    release = DataRelease.objects.create(name="P", slug="p-oncommit", status=DataRelease.Status.DRAFT)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    Activity.objects.create(release=release, step=step, key="s1", label="S1", order=0)
    Activity.objects.create(release=release, step=step, key="s2", label="S2", order=1)
    try:
        # sem wrapper externo, o atomic do start_release commita na saída e o
        # callback roda ali mesmo (HTTP fora de transação, como em produção)
        start_release(release)
        assert sorted(a.key for a in calls) == ["s1", "s2"]
    finally:
        release.delete()
