import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from wkfw.workflow.models import Activity, DataRelease, ReleaseLane, WorkflowTemplate
from wkfw.workflow.services import (
    WorkflowError,
    add_activity,
    archive_release,
    create_release_from_template,
    load_template_from_dict,
    transition_activity,
)

User = get_user_model()


@pytest.fixture
def template(db):
    data = {
        "key": "test",
        "name": "Test",
        "version": 1,
        "lanes": [
            {"key": "a", "label": "Lane A", "order": 0, "color": "#000099"},
        ],
        "stages": [
            {"key": "step-1", "label": "Step 1", "lane": "a", "order": 0, "depends_on": []},
            {"key": "step-2", "label": "Step 2", "lane": "a", "order": 1, "depends_on": ["step-1"]},
        ],
    }
    return load_template_from_dict(data)


@pytest.fixture
def release(template):
    return create_release_from_template(name="DP-Test", template=template, slug="dp-test")


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
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=user)
    a2.refresh_from_db()
    assert a2.status == Activity.Status.IN_PROGRESS
    assert a2.transitions.count() == 1


@pytest.mark.django_db
def test_clone_copies_deps(template):
    release = create_release_from_template(name="R1", template=template)
    assert release.activities.count() == 2
    a2 = release.activities.get(key="step-2")
    assert list(a2.depends_on.values_list("key", flat=True)) == ["step-1"]


@pytest.mark.django_db
def test_add_stage_and_archive_readonly(release, user):
    lane = release.lanes.get(key="a")
    after = release.activities.get(key="step-1")
    new = add_activity(release, label="Inserted", lane=lane, after=after)
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
    res = client.patch(f"/api/activities/{a1.id}/", {"status": "done"}, format="json")
    assert res.status_code == 200
    res = client.patch(f"/api/activities/{a2.id}/", {"status": "in_progress"}, format="json")
    assert res.status_code == 200


@pytest.mark.django_db
def test_api_activity_mode(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    lane = release.lanes.get(key="a")
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "NiFi step", "lane_id": lane.id, "mode": "nifi"},
        format="json",
    )
    assert res.status_code == 201
    assert release.activities.get(label="NiFi step").mode == Activity.Mode.NIFI
    res = client.post(
        f"/api/releases/{release.slug}/activities/",
        {"label": "Manual step", "lane_id": lane.id},
        format="json",
    )
    assert res.status_code == 201
    assert release.activities.get(label="Manual step").mode == Activity.Mode.MANUAL


@pytest.mark.django_db
def test_api_create_user_staff_only(user, staff_user):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post("/api/users/", {"username": "bob", "password": "secret"}, format="json")
    assert res.status_code == 403
    client.force_authenticate(user=staff_user)
    res = client.post(
        "/api/users/",
        {"username": "bob", "name": "Bob", "email": "bob@example.com", "password": "secret"},
        format="json",
    )
    assert res.status_code == 201
    bob = User.objects.get(username="bob")
    assert bob.check_password("secret")
    res = client.post("/api/users/", {"username": "bob", "password": "other"}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_activity_edit_lane_and_deps(release, user):
    lane_b = ReleaseLane.objects.create(release=release, key="b", label="Lane B", order=1)
    other = create_release_from_template(name="Other", template=release.template, slug="other")
    other_lane = other.lanes.first()
    a1 = release.activities.get(key="step-1")
    a3 = add_activity(release, label="Step 3", lane=release.lanes.get(key="a"))

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch(
        f"/api/activities/{a1.id}/",
        {"label": "Renamed", "lane_id": lane_b.id, "depends_on_ids": [a3.id]},
        format="json",
    )
    assert res.status_code == 200
    a1.refresh_from_db()
    assert a1.label == "Renamed"
    assert a1.lane_id == lane_b.id
    assert list(a1.depends_on.values_list("id", flat=True)) == [a3.id]

    res = client.patch(f"/api/activities/{a1.id}/", {"lane_id": other_lane.id}, format="json")
    assert res.status_code == 400
    res = client.patch(
        f"/api/activities/{a1.id}/",
        {"depends_on_ids": [other.activities.first().id]},
        format="json",
    )
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_activity_rejects_dep_cycle(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    res = client.patch(f"/api/activities/{a1.id}/", {"depends_on_ids": [a2.id]}, format="json")
    assert res.status_code == 400
    res = client.patch(f"/api/activities/{a1.id}/", {"depends_on_ids": [a1.id]}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_api_move_activity(release, user):
    lane = release.lanes.get(key="a")
    add_activity(release, label="Third", lane=lane, after=release.activities.get(key="step-2"))
    a1, a2, a3 = sorted(release.activities.all(), key=lambda a: a.order)
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(f"/api/activities/{a3.id}/move/", {"lane_id": lane.id, "after_id": a1.id}, format="json")
    assert res.status_code == 200
    a3.refresh_from_db()
    assert a3.order == 1
    a2.refresh_from_db()
    assert a2.order == 2

    lane_b = ReleaseLane.objects.create(release=release, key="b", label="Lane B", order=1)
    res = client.post(f"/api/activities/{a3.id}/move/", {"lane_id": lane_b.id, "after_id": None}, format="json")
    assert res.status_code == 200
    a3.refresh_from_db()
    assert a3.lane_id == lane_b.id
    assert a3.order == 0

    res = client.post(f"/api/activities/{a1.id}/move/", {"lane_id": lane.id, "after_id": a1.id}, format="json")
    assert res.status_code == 400

    archive_release(release)
    res = client.patch(f"/api/activities/{a1.id}/", {"label": "x"}, format="json")
    assert res.status_code == 400
    res = client.post(f"/api/activities/{a1.id}/move/", {"lane_id": lane.id}, format="json")
    assert res.status_code == 400


@pytest.mark.django_db
def test_release_auto_completed(release, user):
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    transition_activity(a1, to_status=Activity.Status.DONE, actor=user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE
    transition_activity(a2, to_status=Activity.Status.DONE, actor=user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.COMPLETED
    # uma atividade deixando de ser done devolve a release para active
    transition_activity(a2, to_status=Activity.Status.TODO, actor=user)
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE


@pytest.mark.django_db
def test_api_unarchive_release(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch(f"/api/releases/{release.slug}/", {"status": "archived"}, format="json")
    assert res.status_code == 200
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ARCHIVED
    assert release.archived_at is not None

    res = client.patch(f"/api/releases/{release.slug}/", {"status": "active"}, format="json")
    assert res.status_code == 200
    release.refresh_from_db()
    assert release.status == DataRelease.Status.ACTIVE
    assert release.archived_at is None


@pytest.mark.django_db
def test_api_template_stage_patch_delete(template, user, staff_user):
    step_1 = template.stages.get(key="step-1")
    step_2 = template.stages.get(key="step-2")

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.patch(f"/api/templates/test/stages/{step_1.id}/", {"label": "x"}, format="json")
    assert res.status_code == 403
    res = client.delete(f"/api/templates/test/stages/{step_1.id}/")
    assert res.status_code == 403

    client.force_authenticate(user=staff_user)
    # step-2 depends on step-1, so making step-1 depend on step-2 is a cycle
    res = client.patch(
        f"/api/templates/test/stages/{step_1.id}/",
        {"depends_on": ["step-2"]},
        format="json",
    )
    assert res.status_code == 400
    res = client.patch(f"/api/templates/test/stages/{step_1.id}/", {"depends_on": ["step-1"]}, format="json")
    assert res.status_code == 400

    res = client.patch(
        f"/api/templates/test/stages/{step_1.id}/",
        {"label": "Step 1 renamed", "description": "d", "order": 5},
        format="json",
    )
    assert res.status_code == 200
    step_1.refresh_from_db()
    assert step_1.label == "Step 1 renamed"
    assert step_1.order == 5

    res = client.patch(
        f"/api/templates/test/stages/{step_1.id}/",
        {"depends_on": ["step-2"]},
        format="json",
    )
    assert res.status_code == 400

    res = client.delete(f"/api/templates/test/stages/{step_2.id}/")
    assert res.status_code == 204
    assert not template.stages.filter(key="step-2").exists()


@pytest.mark.django_db
def test_api_template_create_patch_delete(user, staff_user, release):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post("/api/templates/", {"name": "Custom"}, format="json")
    assert res.status_code == 403

    client.force_authenticate(user=staff_user)
    res = client.post("/api/templates/", {"name": "Custom Workflow"}, format="json")
    assert res.status_code == 201
    tpl = res.json()
    assert tpl["key"] == "custom-workflow"
    assert tpl["lanes"] == []
    assert tpl["stages"] == []

    res = client.post("/api/templates/", {"name": "Dup", "key": "custom-workflow"}, format="json")
    assert res.status_code == 400

    res = client.patch(
        f"/api/templates/{tpl['key']}/",
        {"name": "Custom Renamed", "version": 2, "is_active": False},
        format="json",
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Custom Renamed"
    assert res.json()["version"] == 2
    assert res.json()["is_active"] is False

    res = client.delete(f"/api/templates/{tpl['key']}/")
    assert res.status_code == 204
    assert not WorkflowTemplate.objects.filter(key="custom-workflow").exists()
    release.refresh_from_db()
    assert release.template is not None  # template de origem do release não foi deletado


@pytest.mark.django_db
def test_api_template_lanes_crud(template, user, staff_user):
    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post("/api/templates/test/lanes/", {"label": "Lane X"}, format="json")
    assert res.status_code == 403

    client.force_authenticate(user=staff_user)
    res = client.post(
        "/api/templates/test/lanes/",
        {"label": "Lane X", "order": 5, "color": "#00FF00"},
        format="json",
    )
    assert res.status_code == 201
    lane = res.json()
    assert lane["key"] == "lane-x"
    assert lane["order"] == 5
    assert lane["color"] == "#00FF00"

    res = client.post("/api/templates/test/lanes/", {"label": "Lane X"}, format="json")
    assert res.status_code == 400  # key duplicada

    res = client.patch(f"/api/templates/test/lanes/{lane['id']}/", {"label": "Lane Y"}, format="json")
    assert res.status_code == 200
    assert res.json()["label"] == "Lane Y"

    # stage na lane é deletado em cascata
    stage = template.stages.get(key="step-1")
    res = client.delete(f"/api/templates/test/lanes/{template.lanes.get(key='a').id}/")
    assert res.status_code == 204
    assert not template.stages.filter(key="step-1").exists()
    assert not template.lanes.filter(key="a").exists()
