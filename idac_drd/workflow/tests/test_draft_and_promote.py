"""Draft como objeto primário: rascunho → execução.

Cobre create_draft (em branco / copiar release), start e a edição da estrutura
durante a execução (o draft continua mutável; "em execução" é uma
indicação de operação, não um congelamento).
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import (
    WorkflowError,
    archive_release,
    create_draft,
    start_release,
    transition_activity,
    unarchive_release,
)
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def identity(db):
    return ExternalIdentity.objects.create(
        email="alice@linea.org.br", name="Alice", github_handle="alice", slack_id="U123"
    )


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="admin", password="pass", is_staff=True)


# ── create_draft ──────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_create_draft_blank_starts_empty():
    release = create_draft(name="Plano")
    assert release.status == DataRelease.Status.DRAFT
    assert release.started_at is None
    assert release.template_key == ""
    assert release.steps.count() == 0
    assert release.activities.count() == 0


@pytest.mark.django_db
def test_create_draft_from_release_copies_everything(identity):
    source = make_release("Source")
    act = source.activities.get(key="step-1")
    act.mode = Activity.Mode.NIFI
    act.github_repo = "linea-it/idac_drd"
    act.area = "Alertas"
    act.size = "L"
    act.assignee = identity
    act.save()
    act = source.activities.get(key="step-1")
    transition_activity(act, to_status=Activity.Status.IN_PROGRESS, actor=None)
    transition_activity(act, to_status=Activity.Status.IN_REVIEW, actor=None)
    transition_activity(act, to_status=Activity.Status.DONE, actor=None)

    plan = create_draft(name="Plano", copy_from_release=source)
    assert plan.status == DataRelease.Status.DRAFT
    assert plan.started_at is None

    copied = plan.activities.get(key="step-1")
    assert copied.mode == Activity.Mode.NIFI
    assert copied.github_repo == "linea-it/idac_drd"
    assert copied.area == "Alertas"
    assert copied.size == "L"
    assert copied.assignee == identity
    # estado de execução nunca é copiado
    assert copied.status == Activity.Status.TODO
    assert copied.notes == ""
    assert list(plan.activities.get(key="step-2").depends_on.values_list("key", flat=True)) == ["step-1"]
    # a release de origem não é afetada
    source.refresh_from_db()
    assert source.status == DataRelease.Status.ACTIVE
    assert source.activities.get(key="step-1").status == Activity.Status.DONE


@pytest.mark.django_db
def test_create_draft_from_release_copies_template_key():
    source = make_release("Source")
    source.template_key = "dp2"
    source.save(update_fields=["template_key"])
    plan = create_draft(name="Plano", copy_from_release=source)
    assert plan.template_key == "dp2"


@pytest.mark.django_db
def test_create_draft_from_release_without_template_key():
    source = make_release("Source")  # template_key vazia por padrão
    plan = create_draft(name="Plano", copy_from_release=source)
    assert plan.template_key == ""


# ── lifecycle: start ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_start_release_sets_active_and_started_at():
    release = make_release("Plano", status="draft")
    assert release.started_at is None
    start_release(release)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE
    assert release.started_at is not None


@pytest.mark.django_db
def test_start_release_requires_draft_and_activities():
    release = make_release("Active")  # já ativa
    with pytest.raises(WorkflowError):
        start_release(release)
    blank = create_draft(name="Blank")
    with pytest.raises(WorkflowError):
        start_release(blank)  # sem atividades


# ── edição durante a execução ────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_transition_blocked_in_draft(user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)
    act = release.activities.first()
    res = client.patch(f"/api/activities/{act.id}/", {"status": "in_progress"}, format="json")
    assert res.status_code == 400
    assert "start the release" in res.data[0].lower()


@pytest.mark.django_db
def test_api_start_flow(staff_user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=staff_user)
    res = client.post(f"/api/releases/{release.slug}/start/", format="json")
    assert res.status_code == 200
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE


@pytest.mark.django_db
def test_api_start_staff_only(user, staff_user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post(f"/api/releases/{release.slug}/start/", format="json")
    assert res.status_code == 403
    client.force_authenticate(user=staff_user)
    res = client.post(f"/api/releases/{release.slug}/start/", format="json")
    assert res.status_code == 200


@pytest.mark.django_db
def test_api_patch_status_rejected_outside_archive(user, staff_user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)
    # ciclo de vida (arquivar/desarquivar) é staff — não-staff leva 403
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "archived"}, format="json")
    assert res.status_code == 403
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "active"}, format="json")
    assert res.status_code == 403
    # staff: status só muda via start/archive — PATCH direto é 400
    client.force_authenticate(user=staff_user)
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "active"}, format="json")
    assert res.status_code == 400
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "completed"}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_structural_patch_allowed_in_execution(user, identity):
    # o draft continua editável durante a execução: sem congelamento estrutural
    release = make_release("Plano")
    act = release.activities.first()
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.patch(f"/api/activities/{act.id}/", {"label": "Renamed"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{act.id}/", {"github_repo": "x/y"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{act.id}/", {"step_id": release.steps.last().id}, format="json")
    assert res.status_code == 200
    # dependência válida no sentido da fixture (step-2 já depende de step-1);
    # auto-dependência/ciclos são rejeitados pelo cycle check, não pelo modo
    other = release.activities.exclude(id=act.id).first()
    res = client.patch(f"/api/activities/{other.id}/", {"depends_on_ids": [act.id]}, format="json")
    assert res.status_code == 200

    # assignee e notas seguem o mesmo caminho
    res = client.patch(
        f"/api/activities/{act.id}/",
        {"assignee_id": identity.id, "notes": "acompanhar de perto"},
        format="json",
    )
    assert res.status_code == 200
    act.refresh_from_db()
    assert act.assignee == identity
    assert act.notes == "acompanhar de perto"


@pytest.mark.django_db
def test_add_and_edit_steps_allowed_in_execution(user):
    release = make_release("Plano")
    step = release.steps.first()
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(f"/api/releases/{release.slug}/activities/", {"label": "New", "step_id": step.id}, format="json")
    assert res.status_code == 201
    res = client.post(f"/api/releases/{release.slug}/steps/", {"label": "Step X"}, format="json")
    assert res.status_code == 201
    new_step = release.steps.get(key="step-x")  # vazia
    res = client.patch(f"/api/releases/{release.slug}/steps/{new_step.id}/", {"label": "Step Y"}, format="json")
    assert res.status_code == 200
    res = client.delete(f"/api/releases/{release.slug}/steps/{new_step.id}/")
    assert res.status_code == 204
    # step com atividades continua indeletável em execução também
    res = client.delete(f"/api/releases/{release.slug}/steps/{step.id}/")
    assert res.status_code == 400

    # reordenar steps em execução: ordem é editável como o resto do draft
    step_b = release.steps.get(key="b")
    res = client.patch(
        f"/api/releases/{release.slug}/steps/{step.id}/",
        {"direction": 1},
        format="json",
    )
    assert res.status_code == 200
    step.refresh_from_db()
    step_b.refresh_from_db()
    assert list(release.steps.order_by("order", "id").values_list("key", flat=True)) == ["b", step.key]


@pytest.mark.django_db
def test_reorder_step_swaps_neighbors_with_duplicate_order(user):
    release = make_release("Plano", status="draft")
    step_a = release.steps.get(key="a")
    step_b = release.steps.get(key="b")
    step_b.order = step_a.order
    step_b.save(update_fields=["order"])
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.patch(
        f"/api/releases/{release.slug}/steps/{step_a.id}/",
        {"direction": 1},
        format="json",
    )
    assert res.status_code == 200
    assert list(release.steps.order_by("order", "id").values_list("key", flat=True)) == ["b", "a"]
    step_a.refresh_from_db()
    step_b.refresh_from_db()
    assert step_a.order != step_b.order


@pytest.mark.django_db
def test_step_crud_in_draft(user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(f"/api/releases/{release.slug}/steps/", {"label": "Step X", "color": "#00FF00"}, format="json")
    assert res.status_code == 201
    step = ReleaseStep.objects.get(release=release, key="step-x")
    assert step.color == "#00FF00"

    res = client.patch(f"/api/releases/{release.slug}/steps/{step.id}/", {"label": "Step Y"}, format="json")
    assert res.status_code == 200
    step.refresh_from_db()
    assert step.label == "Step Y"

    res = client.delete(f"/api/releases/{release.slug}/steps/{step.id}/")
    assert res.status_code == 204
    assert not release.steps.filter(key="step-x").exists()


@pytest.mark.django_db
def test_delete_step_only_empty(user):
    release = make_release("Plano", status="draft")
    client = APIClient()
    client.force_authenticate(user=user)
    step = release.steps.first()  # tem atividades
    res = client.delete(f"/api/releases/{release.slug}/steps/{step.id}/")
    assert res.status_code == 400


# ── sync / unarchive derivados ───────────────────────────────────────────────


@pytest.mark.django_db
def test_sync_does_not_touch_draft(user):
    release = make_release("Plano", status="draft")
    act = release.activities.first()
    act.status = Activity.Status.DONE
    act.save()
    assert release.status == DataRelease.Status.DRAFT  # sync nunca rodou em draft


@pytest.mark.django_db
def test_unarchive_returns_draft_or_active(user):
    draft = make_release("Draft", status="draft")
    archive_release(draft)
    unarchive_release(draft)
    assert draft.status == DataRelease.Status.DRAFT

    active = make_release("Active")
    transition_activity(active.activities.first(), to_status=Activity.Status.IN_PROGRESS, actor=user)
    archive_release(active)
    unarchive_release(active)
    assert active.status == DataRelease.Status.ACTIVE


# ── create via API ───────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_create_blank_and_from_sources(user):
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post("/api/releases/", {"name": "Blank"}, format="json")
    assert res.status_code == 201
    assert res.data["status"] == DataRelease.Status.DRAFT
    assert res.data["steps"] == []
    assert res.data["template_key"] == ""

    plan = make_release("Origem", status="draft")
    res = client.post("/api/releases/", {"name": "From release", "copy_from_release_slug": plan.slug}, format="json")
    assert res.status_code == 201
    assert len(res.data["steps"]) == 2
