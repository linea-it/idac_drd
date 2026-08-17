"""Export/import de PLAN em JSON: round-trip fiel + validações.

O formato de arquivo (v1) é a fonte canônica do shape: o que o export
produz é exatamente o que o import consome. Referências por key/email —
nenhum id sobrevive ao arquivo.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, DataRelease
from idac_drd.workflow.services import export_plan_payload, import_plan_payload
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


def base_payload(**overrides):
    payload = {
        "format": "idac_drd-plan",
        "version": 1,
        "name": "DR1",
        "steps": [
            {"key": "rucio-server", "label": "Rucio Server", "order": 0, "color": "#000099", "resources": []},
            {"key": "pipeline", "label": "Pipeline", "order": 1},
        ],
        "activities": [
            {
                "key": "receive-files-dr",
                "label": "Receive Files (DR)",
                "step_key": "rucio-server",
                "order": 0,
                "depends_on": [],
            },
            {
                "key": "send-files-dr",
                "label": "Send Files (DR)",
                "step_key": "pipeline",
                "order": 0,
                "assignee_email": "alice@linea.org.br",
                "depends_on": ["receive-files-dr"],
            },
        ],
    }
    payload.update(overrides)
    return payload


# ── export: shape do payload ─────────────────────────────────────────────────


@pytest.mark.django_db
def test_export_shape_uses_keys_and_email_not_ids(identity):
    source = make_release("Source")
    act = source.activities.get(key="step-1")
    act.assignee = identity
    act.save()

    payload = export_plan_payload(source)

    assert payload["format"] == "idac_drd-plan"
    assert payload["version"] == 1
    assert payload["name"] == "Source"
    assert [s["key"] for s in payload["steps"]] == ["a", "b"]
    # activities referenciam step e dependências por key — nunca por id
    by_key = {a["key"]: a for a in payload["activities"]}
    assert by_key["step-1"]["step_key"] == "a"
    assert by_key["step-2"]["step_key"] == "a"
    assert by_key["step-2"]["depends_on"] == ["step-1"]
    assert by_key["step-1"]["assignee_email"] == "alice@linea.org.br"
    # estado de execução não sobrevive ao arquivo
    assert "id" not in by_key["step-1"]
    assert "status" not in by_key["step-1"]
    assert "step_id" not in by_key["step-1"]


# ── round-trip ───────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_round_trip_reproduces_structure_and_resets_status(identity):
    source = make_release("Source", status="active")
    act = source.activities.get(key="step-1")
    act.mode = Activity.Mode.NIFI
    act.github_repo = "linea-it/idac_drd"
    act.area = "Alertas"
    act.size = "L"
    act.description = "descrição"
    act.objectives = "objetivo 1\nobjetivo 2"
    act.resources = [{"label": "Docs", "url": "https://docs.linea.org.br"}]
    act.assignee = identity
    act.save()

    payload = export_plan_payload(source)
    # nome novo no import: slug é único, a release de origem continua existindo
    payload["name"] = "Imported"
    plan = import_plan_payload(payload)

    # release importada nasce planned (draft), como qualquer plano
    assert plan.status == DataRelease.Status.PLANNED
    assert plan.started_at is None
    assert plan.template_key == ""
    assert list(plan.steps.values_list("key", flat=True)) == ["a", "b"]

    copied = plan.activities.get(key="step-1")
    assert copied.step.key == "a"
    assert copied.mode == Activity.Mode.NIFI
    assert copied.github_repo == "linea-it/idac_drd"
    assert copied.area == "Alertas"
    assert copied.size == "L"
    assert copied.description == "descrição"
    assert copied.objectives == "objetivo 1\nobjetivo 2"
    assert copied.resources == [{"label": "Docs", "url": "https://docs.linea.org.br"}]
    assert copied.assignee == identity  # resolvido por email
    # estado de execução nunca é importado
    assert copied.status == Activity.Status.TODO
    assert copied.started_at is None
    assert copied.completed_at is None
    assert list(plan.activities.get(key="step-2").depends_on.values_list("key", flat=True)) == ["step-1"]


@pytest.mark.django_db
def test_import_unknown_assignee_email_is_ignored(user):
    payload = base_payload()
    payload["activities"][1]["assignee_email"] = "nobody@linea.org.br"

    client = APIClient()
    client.force_authenticate(user=user)
    res = client.post("/api/releases/import/", payload, format="json")

    assert res.status_code == 201
    plan = DataRelease.objects.get(slug="dr1")
    assert plan.activities.get(key="send-files-dr").assignee is None


# ── import: validações do arquivo ────────────────────────────────────────────


def post_import(payload, user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client.post("/api/releases/import/", payload, format="json")


@pytest.mark.django_db
def test_api_import_creates_planned_release(user):
    res = post_import(base_payload(), user)

    assert res.status_code == 201
    assert res.data["status"] == DataRelease.Status.PLANNED
    plan = DataRelease.objects.get(slug="dr1")
    assert plan.steps.count() == 2
    assert plan.activities.count() == 2


@pytest.mark.django_db
def test_api_import_duplicate_slug_returns_400(user):
    assert post_import(base_payload(), user).status_code == 201
    # mesmo nome → mesmo slug (slugify) → IntegrityError vira 400, como no create
    res = post_import(base_payload(), user)
    assert res.status_code == 400


@pytest.mark.django_db
def test_import_unknown_step_key(user):
    payload = base_payload()
    payload["activities"][0]["step_key"] = "does-not-exist"
    assert post_import(payload, user).status_code == 400


@pytest.mark.django_db
def test_import_unknown_depends_on_key(user):
    payload = base_payload()
    payload["activities"][1]["depends_on"] = ["ghost-activity"]
    assert post_import(payload, user).status_code == 400


@pytest.mark.django_db
def test_import_duplicate_keys(user):
    payload = base_payload()
    payload["steps"] = [*payload["steps"], payload["steps"][0]]
    assert post_import(payload, user).status_code == 400

    payload = base_payload()
    payload["activities"] = [*payload["activities"], payload["activities"][0]]
    assert post_import(payload, user).status_code == 400


@pytest.mark.django_db
def test_import_invalid_resources(user):
    payload = base_payload()
    payload["steps"][0]["resources"] = [{"url": "javascript:alert(1)"}]
    assert post_import(payload, user).status_code == 400

    payload = base_payload()
    payload["activities"][0]["resources"] = [{"label": "Sem url"}]
    assert post_import(payload, user).status_code == 400


@pytest.mark.django_db
def test_import_rejects_unknown_format_and_version(user):
    assert post_import(base_payload(format="outro-formato"), user).status_code == 400
    assert post_import(base_payload(version=2), user).status_code == 400


# ── endpoints ────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_export_endpoint(user):
    release = make_release("Source")
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.get(f"/api/releases/{release.slug}/export/")

    assert res.status_code == 200
    assert res.data["name"] == "Source"
    assert len(res.data["steps"]) == 2
    assert len(res.data["activities"]) == 2


@pytest.mark.django_db
def test_api_export_works_for_any_status(user):
    # exportar uma release executada permite planejar a próxima a partir dela
    client = APIClient()
    client.force_authenticate(user=user)
    for status in ("planned", "active", "completed", "archived"):
        release = make_release(f"Source {status}", status=status)
        res = client.get(f"/api/releases/{release.slug}/export/")
        assert res.status_code == 200
