"""Notificação de review (integrations/notify.py) — Slack DM ao aprovador.

Best-effort + gates: release em execução e SLACK_ENABLED. Cliente Slack real
substituído por fake — nada de HTTP.
"""

import pytest
from django.test import override_settings

from idac_drd.integrations import notify
from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import start_release, transition_activity


class FakeSlack:
    def __init__(self):
        self.dms = []

    def send_dm_to_user(self, user_id, text):
        self.dms.append((user_id, text))
        return {"ok": True}


@pytest.fixture
def slack(monkeypatch):
    fake = FakeSlack()
    monkeypatch.setattr("idac_drd.integrations.notify._slack_client", lambda: fake)
    return fake


@pytest.fixture
def release(db):
    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="Release 1", slug="r1", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    a1 = Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    a2 = Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=reviewer)
    return release, a1, a2


def make_activity(release, **overrides):
    values = {
        "release": release,
        "step": release.steps.get(),
        "key": "step-1",
        "label": "Step 1",
        "order": 0,
        "status": Activity.Status.TODO,
    }
    values.update(overrides)
    return Activity.objects.create(**values)


def test_dm_goes_to_next_activity_assignee(release, slack):
    _, a1, _ = release
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a1)

    assert len(slack.dms) == 1
    user_id, text = slack.dms[0]
    assert user_id == "U_BOB"
    assert "A1" in text
    assert "A2" in text  # destrava a próxima etapa
    assert "/releases/r1/" in text


def test_no_notification_without_slack_enabled(release, slack):
    _, a1, _ = release
    notify.notify_review(a1)  # SLACK_ENABLED default False
    assert not slack.dms


def test_no_notification_outside_active_release(release, slack):
    release, a1, _ = release
    release.status = DataRelease.Status.PLANNED
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a1)
    assert not slack.dms


def test_last_activity_of_step_no_reviewer(release, slack):
    release, _, a2 = release  # a2 é a última do step → staff aprova
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a2)
    assert not slack.dms


def test_assignee_without_slack_id_skipped(release, slack):
    release, a1, a2 = release
    a2.assignee.slack_id = ""
    a2.assignee.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a1)
    assert not slack.dms


def test_api_failure_logged_not_raised(release, slack, caplog):
    _, a1, _ = release

    def boom(*args, **kwargs):
        raise RuntimeError("slack down")

    slack.send_dm_to_user = boom
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a1)  # não levanta
    assert "Slack review notification failed" in caplog.text


# ── rejeição: aviso ao executor ──────────────────────────────────────────────


@pytest.fixture
def executor(db):
    return ExternalIdentity.objects.create(email="alice@linea.org.br", name="Alice", slack_id="U_ALICE")


def test_rejection_dm_goes_to_executor(release, executor, slack):
    release, a1, _ = release
    a1.assignee = executor
    a1.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_rejection(a1, "Faltou validar o schema", reviewer="bob")

    assert len(slack.dms) == 1
    user_id, text = slack.dms[0]
    assert user_id == "U_ALICE"
    assert "Rejected by bob" in text
    assert "Faltou validar o schema" in text
    assert "/releases/r1/" in text


def test_rejection_without_executor_skipped(release, slack):
    release, a1, _ = release  # a1 sem assignee
    with override_settings(SLACK_ENABLED=True):
        notify.notify_rejection(a1, "motivo", reviewer="bob")
    assert not slack.dms


def test_rejection_without_slack_id_skipped(release, executor, slack):
    release, a1, _ = release
    executor.slack_id = ""
    executor.save()
    a1.assignee = executor
    a1.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_rejection(a1, "motivo", reviewer="bob")
    assert not slack.dms


def test_rejection_gated_by_release_status(release, executor, slack):
    release, a1, _ = release
    a1.assignee = executor
    a1.save()
    release.status = DataRelease.Status.ARCHIVED
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_rejection(a1, "motivo", reviewer="bob")
    assert not slack.dms


def test_rejection_failure_logged_not_raised(release, executor, slack, caplog):
    release, a1, _ = release
    a1.assignee = executor
    a1.save()

    def boom(*args, **kwargs):
        raise RuntimeError("slack down")

    slack.send_dm_to_user = boom
    with override_settings(SLACK_ENABLED=True):
        notify.notify_rejection(a1, "motivo", reviewer="bob")  # não levanta
    assert "Slack rejection notification failed" in caplog.text


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_after_review_and_rejection(monkeypatch):
    """Caminho real: in_review e rejeição agendam on_commit; rodam no commit."""
    review_calls, rejection_calls = [], []

    def capture_rejection(activity, comment, reviewer):
        rejection_calls.append((activity, comment, reviewer))

    monkeypatch.setattr("idac_drd.integrations.notify.notify_review", review_calls.append)
    monkeypatch.setattr("idac_drd.integrations.notify.notify_rejection", capture_rejection)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-notify", status=DataRelease.Status.PLANNED)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    a1 = Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=reviewer)
    try:
        start_release(release)
        transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=None)
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=None)
        assert len(review_calls) == 1
        assert review_calls[0].key == "a1"
        # rejeição (com motivo) notifica o executor com o motivo
        transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=None, comment="fix")
        assert len(rejection_calls) == 1
        assert rejection_calls[0][0].key == "a1"
        assert rejection_calls[0][1] == "fix"
        # novo in_review notifica de novo
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=None)
        assert len(review_calls) == 2
    finally:
        release.delete()
