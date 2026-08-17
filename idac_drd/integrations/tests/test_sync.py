"""Sync automática de atividades ↔ GitHub/GLPI (integrations/sync.py).

Best-effort + gates: release em execução e flags *_ENABLED. Clients reais
são substituídos por fakes — nada de HTTP.
"""

import pytest
from django.test import override_settings

from idac_drd.integrations import sync
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep

ENABLED = {
    "GH_ENABLED": True,
    "GLPI_ENABLED": True,
}


PROJECT_FIELD = (
    "PVT_proj",
    "f_status",
    {
        "🔖 To do": "o_todo",
        "🏗 In progress": "o_in_progress",
        "🚧 Blocked": "o_blocked",
        "👀 In review": "o_in_review",
        "✅ Done": "o_done",
    },
)


class FakeGithub:
    def __init__(self):
        self.created = []
        self.bodies = []
        self.updated = []
        self.project_field_calls = 0
        self.added_items = []
        self.set_statuses = []

    def create_issue(self, owner, repo, title, body, labels=None):
        self.created.append((owner, repo, title))
        self.bodies.append(body)
        return {"number": 42, "node_id": "I_kw_node42"}

    def update_issue(self, owner, repo, number, **fields):
        self.updated.append((owner, repo, number, fields))
        return {"number": number}

    def project_field(self, org, project_number):
        self.project_field_calls += 1
        return PROJECT_FIELD

    def add_project_item(self, project_id, content_id):
        self.added_items.append((project_id, content_id))
        return "PVTI_item42"

    def set_project_item_status(self, project_id, item_id, field_id, option_id):
        self.set_statuses.append((project_id, item_id, field_id, option_id))


class FakeGlpi:
    def __init__(self):
        self.created = []
        self.contents = []
        self.updated = []

    def create_ticket(self, name, content, ticket_type=1):
        self.created.append((name, ticket_type))
        self.contents.append(content)
        return {"id": 7}

    def update_ticket(self, ticket_id, **fields):
        self.updated.append((ticket_id, fields))
        return {"id": ticket_id}


@pytest.fixture
def clients(monkeypatch):
    gh, glpi = FakeGithub(), FakeGlpi()
    monkeypatch.setattr("idac_drd.integrations.sync._github_client", lambda: gh)
    monkeypatch.setattr("idac_drd.integrations.sync._glpi_client", lambda: glpi)
    return gh, glpi


@pytest.fixture(autouse=True)
def reset_project_cache():
    # o cache do field Status do projeto é global; zera entre testes
    sync._PROJECT_CACHE.update({"ts": 0.0, "data": None})


@pytest.fixture
def release(db):
    release = DataRelease.objects.create(name="Release 1", slug="r1", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    return release


def make_activity(release, **overrides):
    values = {
        "release": release,
        "step": release.steps.get(),
        "key": "step-1",
        "label": "Step 1",
        "order": 0,
        "status": Activity.Status.TODO,
        "github_repo": "linea-it/repo",
    }
    values.update(overrides)
    return Activity.objects.create(**values)


def test_gated_by_release_status(clients, release):
    """Release fora de execução (draft/arquivada): no-op silencioso."""
    gh, glpi = clients
    release.status = DataRelease.Status.PLANNED
    release.save()
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))
    assert not gh.created and not gh.updated
    assert not glpi.created and not glpi.updated


def test_disabled_flags_noop(clients, release):
    """Flags *_ENABLED off: nada é criado nem atualizado."""
    gh, glpi = clients
    with override_settings(GH_ENABLED=False, GLPI_ENABLED=False):
        sync.sync_activity(make_activity(release))
    assert not gh.created and not gh.updated
    assert not glpi.created and not glpi.updated


def test_creates_issue_and_ticket(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)

    assert gh.created == [("linea-it", "repo", "Step 1")]
    assert gh.added_items == [("PVT_proj", "I_kw_node42")]
    assert gh.set_statuses == [("PVT_proj", "PVTI_item42", "f_status", "o_todo")]
    assert glpi.created == [("Step 1", 1)]
    # referências persistidas na atividade
    activity.refresh_from_db()
    assert activity.github_issue_number == 42
    assert activity.github_issue_node_id == "I_kw_node42"
    assert activity.github_project_item_id == "PVTI_item42"
    assert activity.glpi_ticket_id == 7


def test_creates_once_then_updates_status(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release, status=Activity.Status.IN_PROGRESS)
        sync.sync_activity(activity)  # cria issue + ticket
        activity.refresh_from_db()
        sync.sync_activity(activity)  # segunda passada: refs já existem → só atualiza

    assert len(gh.created) == 1 and len(glpi.created) == 1
    assert len(gh.added_items) == 1  # item adicionado ao projeto uma única vez
    assert gh.project_field_calls == 1  # field do projeto cacheado (60s)
    assert gh.updated == [("linea-it", "repo", 42, {"state": "open"})]
    assert gh.set_statuses == [("PVT_proj", "PVTI_item42", "f_status", "o_in_progress")] * 2
    assert glpi.updated == [(7, {"status": 2})]


def test_done_closes_issue_and_solves_ticket(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)
        activity.refresh_from_db()

        activity.status = Activity.Status.DONE
        activity.save()
        sync.sync_activity(activity)

    assert gh.updated == [("linea-it", "repo", 42, {"state": "closed", "state_reason": "completed"})]
    # última atualização no projeto: ✅ Done
    assert gh.set_statuses[-1] == ("PVT_proj", "PVTI_item42", "f_status", "o_done")
    assert glpi.updated == [(7, {"status": 5})]


def test_blocked_maps_to_pending(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)
        activity.refresh_from_db()

        activity.status = Activity.Status.BLOCKED
        activity.save()
        sync.sync_activity(activity)

    assert gh.set_statuses[-1][3] == "o_blocked"
    assert glpi.updated == [(7, {"status": 4})]


def test_without_github_repo_skips_issue_but_creates_ticket(clients, release, caplog):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release, github_repo="")
        sync.sync_activity(activity)

    assert not gh.created
    assert not gh.added_items and not gh.set_statuses
    assert glpi.created == [("Step 1", 1)]
    assert "no GitHub repo" in caplog.text


def test_project_unavailable_keeps_issue_and_ticket(clients, release, caplog):
    """Sem acesso ao projeto (scope/erro), o item é pulado — o resto continua."""
    gh, glpi = clients

    def boom(*args, **kwargs):
        raise RuntimeError("Resource not accessible by integration")

    gh.project_field = boom
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))

    assert gh.created == [("linea-it", "repo", "Step 1")]
    assert not gh.added_items
    assert glpi.created == [("Step 1", 1)]
    assert "GitHub project sync failed" in caplog.text


def test_in_review_maps_to_project_review_and_glpi_pending(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        activity = make_activity(release)
        sync.sync_activity(activity)  # cria
        activity.refresh_from_db()

        activity.status = Activity.Status.IN_REVIEW
        activity.save()
        sync.sync_activity(activity)

    # issue segue aberta (fecha só na aprovação); projeto → In review; GLPI → Pending
    assert gh.updated == [("linea-it", "repo", 42, {"state": "open"})]
    assert gh.set_statuses[-1] == ("PVT_proj", "PVTI_item42", "f_status", "o_in_review")
    assert glpi.updated == [(7, {"status": 4})]


def test_objectives_go_to_issue_and_ticket_bodies(clients, release):
    gh, glpi = clients
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release, objectives="Validar schema\nGerar dataset final"))

    assert "**Objectives:**" in gh.bodies[0]
    assert "- [ ] Validar schema" in gh.bodies[0]
    assert "- [ ] Gerar dataset final" in gh.bodies[0]
    assert "**Objectives:**" in glpi.contents[0]
    assert "- [ ] Validar schema" in glpi.contents[0]


def test_api_failure_is_logged_not_raised(clients, release, monkeypatch, caplog):
    gh, glpi = clients

    def boom(*args, **kwargs):
        raise RuntimeError("network down")

    gh.create_issue = boom
    with override_settings(**ENABLED):
        sync.sync_activity(make_activity(release))

    assert "GitHub sync failed" in caplog.text
    # GLPI seguiu mesmo com o GitHub falhando
    assert glpi.created == [("Step 1", 1)]
