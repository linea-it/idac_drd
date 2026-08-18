"""Rastro de edição dos campos de texto (ActivityTextRevision).

Captura só no único ponto de update em runtime (ActivityViewSet.partial_update):
salvar o mesmo valor não gera revisão; apagar vira text_after=""; criação
(clone/import/atividade nova) e ``.save()`` direto não geram revisão.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.workflow.models import Activity, ActivityTextRevision
from idac_drd.workflow.services import archive_release, create_plan, export_plan_payload, import_plan_payload
from idac_drd.workflow.tests.helpers import make_release

User = get_user_model()


@pytest.fixture
def release(db):
    return make_release("DP-Test", slug="dp-test")


@pytest.fixture
def user(db):
    return User.objects.create_user(username="alice", password="pass")


def patch_notes(client, activity, notes, **extra):
    payload = {"notes": notes}
    payload.update(extra)
    return client.patch(f"/api/activities/{activity.id}/", payload, format="json")


@pytest.mark.django_db
def test_patch_notes_creates_revision(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.get(key="step-1")
    activity.notes = "nota antiga"
    activity.save(update_fields=["notes"])

    res = patch_notes(client, activity, "nota nova")
    assert res.status_code == 200

    rev = activity.text_revisions.get()
    assert rev.field == ActivityTextRevision.Field.NOTES
    assert rev.text_before == "nota antiga"
    assert rev.text_after == "nota nova"
    assert rev.actor == user


@pytest.mark.django_db
def test_patch_unchanged_creates_no_revision(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.get(key="step-1")
    activity.notes = "mesma nota"
    activity.save(update_fields=["notes"])

    res = patch_notes(client, activity, "mesma nota")
    assert res.status_code == 200
    assert activity.text_revisions.count() == 0


@pytest.mark.django_db
def test_patch_deleting_notes_revision_after_empty(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.get(key="step-1")
    activity.notes = "vai sumir"
    activity.save(update_fields=["notes"])

    res = patch_notes(client, activity, "")
    assert res.status_code == 200

    rev = activity.text_revisions.get()
    assert rev.text_before == "vai sumir"
    assert rev.text_after == ""


@pytest.mark.django_db
def test_patch_two_fields_creates_two_revisions(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.get(key="step-1")
    activity.description = "desc antiga"
    activity.objectives = "obj antigo"
    activity.save(update_fields=["description", "objectives"])

    res = client.patch(
        f"/api/activities/{activity.id}/",
        {"description": "desc nova", "objectives": "obj novo"},
        format="json",
    )
    assert res.status_code == 200

    revisions = {r.field: r for r in activity.text_revisions.all()}
    assert set(revisions) == {"description", "objectives"}
    assert revisions["description"].text_before == "desc antiga"
    assert revisions["description"].text_after == "desc nova"
    assert revisions["objectives"].text_before == "obj antigo"
    assert revisions["objectives"].text_after == "obj novo"


@pytest.mark.django_db
def test_status_change_with_notes_creates_revision_and_transition(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    activity = release.activities.get(key="step-1")
    activity.notes = "registro da execução"
    activity.save(update_fields=["notes"])

    res = client.patch(
        f"/api/activities/{activity.id}/",
        {"status": "in_progress", "notes": "registro atualizado"},
        format="json",
    )
    assert res.status_code == 200

    assert activity.text_revisions.count() == 1
    assert activity.text_revisions.get().text_after == "registro atualizado"
    assert activity.transitions.count() == 1
    assert activity.transitions.get().to_status == Activity.Status.IN_PROGRESS


@pytest.mark.django_db
def test_text_revisions_endpoint_scoped_by_release(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    a1 = release.activities.get(key="step-1")
    a2 = release.activities.get(key="step-2")
    for act, text in ((a1, "um"), (a2, "dois")):
        act.notes = "antes"
        act.save(update_fields=["notes"])
        patch_notes(client, act, text)
    other = make_release("DP-Outro", slug="dp-outro")
    other_a = other.activities.get(key="step-1")
    other_a.notes = "fora"
    other_a.save(update_fields=["notes"])
    patch_notes(client, other_a, "desta")

    res = client.get(f"/api/releases/{release.slug}/text-revisions/")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 2
    assert {row["activity"] for row in data} == {a1.id, a2.id}
    assert all(row["actor"]["username"] == "alice" for row in data)
    assert "text_before" in data[0] and "text_after" in data[0]


@pytest.mark.django_db
def test_patch_archived_release_creates_no_revision(release, user):
    client = APIClient()
    client.force_authenticate(user=user)
    archive_release(release)
    activity = release.activities.get(key="step-1")
    activity.notes = "vai falhar"
    activity.save(update_fields=["notes"])

    res = patch_notes(client, activity, "não grava")
    assert res.status_code == 400
    assert activity.text_revisions.count() == 0


@pytest.mark.django_db
def test_creation_paths_do_not_create_revisions(release, user):
    # atividade nova via serviço
    step = release.steps.get(key="a")
    from idac_drd.workflow.services import add_activity

    created = add_activity(release, label="Nova", step=step, description="nasce com desc")
    assert created.text_revisions.count() == 0

    # clone de release
    clone = create_plan(name="Clone", copy_from_release=release)
    assert ActivityTextRevision.objects.filter(activity__release=clone).count() == 0

    # import de plano (slug é único: nome novo no import)
    payload = export_plan_payload(release)
    payload["name"] = "Imported"
    imported = import_plan_payload(payload)
    assert ActivityTextRevision.objects.filter(activity__release=imported).count() == 0


@pytest.mark.django_db
def test_direct_save_does_not_create_revision(release):
    activity = release.activities.get(key="step-1")
    activity.notes = "via ORM direto"
    activity.save(update_fields=["notes"])
    assert activity.text_revisions.count() == 0
