import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.workflow.models import Activity, DataRelease
from idac_drd.workflow.services import WorkflowError, add_activity, archive_release, create_plan, transition_activity
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def release(db):
    return make_release("DP-Test", slug="dp-test")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(username="admin", password="pass", is_staff=True)


@pytest.mark.django_db
def test_gate_blocks_until_prerequisite_done(release, user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    with pytest.raises(WorkflowError):
        transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=user)
    # step-1 conclui via revisão; step-2 (sem assignee) aprova o anterior
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user)
    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=user)
    a2.refresh_from_db()
    assert a2.status == Activity.Status.IN_PROGRESS
    assert a2.transitions.count() == 1


@pytest.mark.django_db
def test_activity_with_pending_prerequisite_is_born_blocked(release):
    # sem deps pendentes nasce todo (pronta para executar); com deps pendentes
    # nasce blocked — assim não gera ticket no GLPI antes da hora
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    assert a1.status == Activity.Status.TODO
    assert a2.status == Activity.Status.BLOCKED
    assert a2.blocked_reason == "Aguardando pré-requisitos: Step 1"


@pytest.mark.django_db
def test_done_unblocks_prerequisite_blocked_dependent(release, user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    assert a2.status == Activity.Status.BLOCKED
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user)
    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    # pré-requisito concluído: a dependente desbloqueia sozinha (todo, sem reason)
    a2.refresh_from_db()
    assert a2.status == Activity.Status.TODO
    assert a2.blocked_reason == ""


@pytest.mark.django_db
def test_manually_blocked_stays_blocked_after_prerequisite_done(release, user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user)
    # bloqueio manual com motivo próprio (como a view faz: reason setado antes)
    a2.blocked_reason = "Esperando fornecedor"
    a2.save(update_fields=["blocked_reason"])
    transition_activity(a2, to_status=Activity.Status.BLOCKED, actor=user)
    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    # bloqueio humano não é desfeito pela conclusão do pré-requisito
    a2.refresh_from_db()
    assert a2.status == Activity.Status.BLOCKED


@pytest.mark.django_db
def test_blocked_cannot_go_to_review(release, user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    with pytest.raises(WorkflowError):
        transition_activity(a2, to_status=Activity.Status.IN_REVIEW, actor=user)
    assert a1.status == Activity.Status.TODO  # nada mudou


@pytest.mark.django_db
def test_clone_copies_deps():
    source = make_release("R1")
    plan = create_plan(name="R1 copy", copy_from_release=source)
    assert plan.activities.count() == 2
    a2 = plan.activities.get(key="step-2")
    assert list(a2.depends_on.values_list("key", flat=True)) == ["step-1"]


@pytest.mark.django_db
def test_add_activity_and_archive_readonly(user):
    release = make_release("DP-Test", status="planned")
    step = release.steps.get(key="a")
    after = release.activities.get(key="step-1")
    new = add_activity(release, label="Inserted", step=step, after=after)
    assert new.depends_on.filter(id=after.id).exists()
    archive_release(release)
    with pytest.raises(WorkflowError):
        transition_activity(release.activities.get(key="step-1"), to_status=Activity.Status.DONE, actor=user)


@pytest.mark.django_db
def test_api_transition_gate(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    a2 = release.activities.get(key="step-2")
    res = client.patch(f"/api/activities/{a2.id}/", {"status": "in_progress"}, format="json")
    assert res.status_code == 400
    a1 = release.activities.get(key="step-1")
    res = client.patch(f"/api/activities/{a1.id}/", {"status": "in_progress"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{a1.id}/", {"status": "in_review"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{a1.id}/", {"status": "done"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{a2.id}/", {"status": "in_progress"}, format="json")
    assert res.status_code == 200


@pytest.mark.django_db
def test_api_activity_mode(user):
    release = make_release("DP-Test", status="planned")
    client = APIClient()
    client.force_authenticate(user=user)
    step = release.steps.get(key="a")
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "NiFi step", "step_id": step.id, "mode": "nifi"},
        format="json",
    )
    assert res.status_code == 201
    assert release.activities.get(label="NiFi step").mode == Activity.Mode.NIFI
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "Manual step", "step_id": step.id},
        format="json",
    )
    assert res.status_code == 201
    assert release.activities.get(label="Manual step").mode == Activity.Mode.MANUAL


@pytest.mark.django_db
def test_api_create_user_staff_only(user, staff_user):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post("/api/users/", {"username": "bob", "password": "SecretPass123"}, format="json")
    assert res.status_code == 403
    client.force_authenticate(user=staff_user)
    res = client.post(
        "/api/users/",
        {"username": "bob", "name": "Bob", "email": "bob@example.com", "password": "SecretPass123"},
        format="json",
    )
    assert res.status_code == 201
    bob = User.objects.get(username="bob")
    assert bob.check_password("SecretPass123")
    res = client.post("/api/users/", {"username": "bob", "password": "other"}, format="json")
    assert res.status_code == 400
    # senha fraca é rejeitada pelos AUTH_PASSWORD_VALIDATORS
    res = client.post("/api/users/", {"username": "carol", "password": "12345"}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_activity_edit_step_and_deps(user):
    release = make_release("DP-Test", status="planned")
    step_b = release.steps.get(key="b")  # step vazio (activities estão no step a)
    other = make_release("Other", status="planned")
    other_step = other.steps.first()
    a1 = release.activities.get(key="step-1")
    a3 = add_activity(release, label="Step 3", step=release.steps.get(key="a"))

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch(
        f"/api/activities/{a1.id}/",
        {"label": "Renamed", "step_id": step_b.id, "depends_on_ids": [a3.id]},
        format="json",
    )
    assert res.status_code == 200
    a1.refresh_from_db()
    assert a1.label == "Renamed"
    assert a1.step_id == step_b.id
    assert list(a1.depends_on.values_list("id", flat=True)) == [a3.id]

    res = client.patch(f"/api/activities/{a1.id}/", {"step_id": other_step.id}, format="json")
    assert res.status_code == 400
    res = client.patch(
        f"/api/activities/{a1.id}/",
        {"depends_on_ids": [other.activities.first().id]},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_activity_rejects_dep_cycle(user):
    release = make_release("DP-Test", status="planned")
    client = APIClient()
    client.force_authenticate(user=user)
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    res = client.patch(f"/api/activities/{a1.id}/", {"depends_on_ids": [a2.id]}, format="json")
    assert res.status_code == 400
    res = client.patch(f"/api/activities/{a1.id}/", {"depends_on_ids": [a1.id]}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_move_activity(user):
    release = make_release("DP-Test", status="planned")
    step = release.steps.get(key="a")
    add_activity(release, label="Third", step=step, after=release.activities.get(key="step-2"))
    a1, a2, a3 = sorted(release.activities.all(), key=lambda a: a.order)
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(f"/api/activities/{a3.id}/move/", {"step_id": step.id, "after_id": a1.id}, format="json")
    assert res.status_code == 200
    a3.refresh_from_db()
    assert a3.order == 1
    a2.refresh_from_db()
    assert a2.order == 2

    step_b = release.steps.get(key="b")  # step vazio (activities estão no step a)
    res = client.post(f"/api/activities/{a3.id}/move/", {"step_id": step_b.id, "after_id": None}, format="json")
    assert res.status_code == 200
    a3.refresh_from_db()
    assert a3.step_id == step_b.id
    assert a3.order == 0

    res = client.post(f"/api/activities/{a1.id}/move/", {"step_id": step.id, "after_id": a1.id}, format="json")
    assert res.status_code == 400

    archive_release(release)
    res = client.patch(f"/api/activities/{a1.id}/", {"label": "x"}, format="json")
    assert res.status_code == 400
    res = client.post(f"/api/activities/{a1.id}/move/", {"step_id": step.id}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_release_auto_completed(release, user, staff_user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    # step-1: aprovado pelo próximo (step-2 não tem assignee → qualquer um)
    transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=user)
    transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE
    # step-2 é a última do step → staff aprova
    transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=user)
    transition_activity(a2, to_status=Activity.Status.IN_REVIEW, actor=user)
    transition_activity(a2, to_status=Activity.Status.DONE, actor=staff_user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.COMPLETED
    # uma atividade deixando de ser done devolve a release para active
    transition_activity(a2, to_status=Activity.Status.TODO, actor=user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE


@pytest.mark.django_db
def test_api_unarchive_release(release, staff_user):
    client = APIClient()
    client.force_authenticate(user=staff_user)
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "archived"}, format="json")
    assert res.status_code == 200
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ARCHIVED
    assert release.archived_at is not None

    res = client.patch(f"/api/releases/{release.slug}/", {"status": "active"}, format="json")
    assert res.status_code == 200
    release.refresh_from_db()
    # sem nenhuma atividade iniciada, desarquivar volta para draft
    assert release.status == DataRelease.Status.PLANNED
    assert release.archived_at is None
