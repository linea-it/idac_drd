"""Notificação de fluxo (integrations/notify.py) — Slack DM ao responsável + canal.

Best-effort + gates: release em execução e SLACK_ENABLED. Copy PT-BR por
superfície: DM em 2ª pessoa sem menção, canal em 3ª pessoa com <@slack_id>.
Threads por step: eventos de atividade viram replies na âncora do step
(ReleaseStep.slack_thread_ts). CTA mrkdwn absoluto só quando SITE_URL está
configurado. Cliente Slack real substituído por fake — nada de HTTP.
"""

import pytest
from django.test import override_settings

from idac_drd.integrations import notify
from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import _block_until_prerequisites, add_activity, start_release, transition_activity

SITE = "https://example.test"


class FakeSlack:
    def __init__(self):
        self.dms = []
        self.channels = []
        self.posts = []  # (channel_id, text, thread_ts)

    def send_dm_to_user(self, user_id, text):
        self.dms.append((user_id, text))
        return {"ok": True, "ts": f"dm-{len(self.dms)}"}

    def post_to_channel(self, channel_id, text, thread_ts=None):
        self.channels.append((channel_id, text))
        self.posts.append((channel_id, text, thread_ts))
        return {"ok": True, "ts": f"ts-{len(self.posts)}"}


@pytest.fixture
def slack(monkeypatch):
    fake = FakeSlack()
    monkeypatch.setattr("idac_drd.integrations.notify._slack_client", lambda: fake)
    return fake


@pytest.fixture
def release(db):
    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="Release 1", slug="r1", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(
        release=release, key="a", label="Step A", order=0, color="#000099", slack_thread_ts="thread-a"
    )
    a1 = Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    a2 = Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=reviewer)
    a2.depends_on.add(a1)
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


# ── review: aviso ao aprovador natural ───────────────────────────────────────


def test_dm_goes_to_next_activity_assignee(release, slack):
    _, a1, _ = release
    with override_settings(SLACK_ENABLED=True, SITE_URL=SITE):
        notify.notify_review(a1)

    assert len(slack.dms) == 1
    user_id, text = slack.dms[0]
    assert user_id == "U_BOB"
    assert "Release 1 · *A1*" in text
    assert "Aprovar libera *A2*." in text
    assert f"<{SITE}/releases/r1/|Revisar entrega>" in text
    assert "<@" not in text  # DM é privada: sem menção


def test_no_notification_without_slack_enabled(release, slack):
    _, a1, _ = release
    notify.notify_review(a1)  # SLACK_ENABLED default False
    assert not slack.dms


def test_no_notification_outside_active_release(release, slack):
    release, a1, _ = release
    release.status = DataRelease.Status.DRAFT
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_review(a1)
    assert not slack.dms


def test_last_activity_of_step_no_reviewer(release, slack):
    release, _, a2 = release  # a2 sem dependentes → sem menção/DM
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


def test_review_goes_to_channel_when_configured(release, slack):
    release, _, a2 = release  # sem dependentes: sem aprovador para DM
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_review(a2)

    assert not slack.dms
    assert [c for c, _ in slack.channels] == ["C_TEAM"]
    text = slack.channels[0][1]
    assert "Release 1 · *A2*" in text
    assert "Qualquer pessoa pode aprovar esta entrega." in text
    assert f"<{SITE}/releases/r1/|Revisar entrega>" in text
    assert "<@" not in text  # sem aprovador nomeado


def test_review_with_channel_skips_dm(release, slack):
    _, a1, _ = release  # dependente (a2) tem assignee bob
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_review(a1)

    assert not slack.dms  # DM só como fallback sem canal
    assert len(slack.channels) == 1
    assert "<@U_BOB>" in slack.channels[0][1]  # canal menciona o dono
    assert f"<{SITE}/releases/r1/|Revisar entrega>" in slack.channels[0][1]


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
    with override_settings(SLACK_ENABLED=True, SITE_URL=SITE):
        notify.notify_rejection(a1, "Faltou validar o schema", reviewer="bob")

    assert len(slack.dms) == 1
    user_id, text = slack.dms[0]
    assert user_id == "U_ALICE"
    assert "Release 1 · *A1*" in text
    assert "a revisão devolveu sua atividade." in text
    assert "Revisada por bob." in text
    assert "*Motivo:* Faltou validar o schema" in text
    assert "Corrija e envie de novo." in text
    assert f"<{SITE}/releases/r1/|Corrigir e reenviar>" in text
    assert "<@" not in text


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


def test_rejection_goes_to_channel_when_configured(release, slack):
    release, a1, _ = release  # a1 sem assignee: sem DM-alvo
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_rejection(a1, "Faltou validar o schema", reviewer="bob")

    assert not slack.dms
    assert [c for c, _ in slack.channels] == ["C_TEAM"]
    text = slack.channels[0][1]
    assert "a revisão devolveu a atividade." in text
    assert "*Motivo:* Faltou validar o schema" in text
    assert f"<{SITE}/releases/r1/|Corrigir e reenviar>" in text
    assert "<@" not in text  # sem executor nomeado


def test_rejection_with_channel_skips_dm(release, executor, slack):
    release, a1, _ = release
    a1.assignee = executor
    a1.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_rejection(a1, "motivo", reviewer="bob")

    assert not slack.dms  # DM só como fallback sem canal
    assert len(slack.channels) == 1
    assert "<@U_ALICE>" in slack.channels[0][1]  # canal menciona o dono


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


# ── tarefa pronta para iniciar: aviso ao assignee ───────────────────────────


def test_ready_dm_goes_to_assignee(release, slack):
    _, _, a2 = release  # a2 tem assignee bob (slack_id U_BOB)
    with override_settings(SLACK_ENABLED=True, SITE_URL=SITE):
        notify.notify_ready(a2)

    assert len(slack.dms) == 1
    user_id, text = slack.dms[0]
    assert user_id == "U_BOB"
    assert "Release 1 · *A2*" in text
    assert "sua atividade está pronta para você começar." in text
    assert f"<{SITE}/releases/r1/|Abrir a atividade>" in text
    assert "<@" not in text


def test_ready_with_channel_skips_dm(release, slack):
    _, _, a2 = release
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_ready(a2)

    assert not slack.dms  # DM só como fallback sem canal
    assert [c for c, _ in slack.channels] == ["C_TEAM"]
    assert "<@U_BOB>" in slack.channels[0][1]  # canal menciona o dono
    assert "esta atividade está pronta para você começar." in slack.channels[0][1]
    assert f"<{SITE}/releases/r1/|Abrir a atividade>" in slack.channels[0][1]


def test_ready_without_slack_id_only_channel(release, slack):
    _, _, a2 = release
    a2.assignee.slack_id = ""
    a2.assignee.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_ready(a2)

    assert not slack.dms
    assert len(slack.channels) == 1
    assert "<@" not in slack.channels[0][1]  # sem slack_id: canal sem menção
    assert f"<{SITE}/releases/r1/|Abrir a atividade>" in slack.channels[0][1]


def test_ready_without_assignee_and_channel_skipped(release, slack):
    _, a1, _ = release  # a1 sem assignee; sem canal configurado
    notify.notify_ready(a1)
    assert not slack.dms
    assert not slack.channels


def test_ready_gated_by_slack_enabled(release, slack):
    _, _, a2 = release
    notify.notify_ready(a2)  # SLACK_ENABLED default False
    assert not slack.dms


def test_ready_gated_by_release_status(release, slack):
    release, _, a2 = release
    release.status = DataRelease.Status.DRAFT
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_ready(a2)
    assert not slack.dms


def test_notify_without_site_url_omits_path(release, slack):
    _, _, a2 = release
    with override_settings(SLACK_ENABLED=True, SITE_URL=""):
        notify.notify_ready(a2)

    assert len(slack.dms) == 1
    assert "/releases/" not in slack.dms[0][1]  # sem URL: nunca path relativo


# ── release concluída: aviso de time no canal ────────────────────────────────


def test_complete_posts_to_channel(release, slack):
    release, _, _ = release
    release.status = DataRelease.Status.COMPLETED
    release.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_release_complete(release)

    assert not slack.dms  # aviso de time: sem DM individual
    assert len(slack.channels) == 1
    text = slack.channels[0][1]
    assert "*Release 1* concluído." in text
    assert "Todas as atividades foram aprovadas." in text
    assert f"<{SITE}/releases/r1/|Ver DPN>" in text


def test_complete_requires_channel(release, slack):
    release, _, _ = release
    release.status = DataRelease.Status.COMPLETED
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_release_complete(release)
    assert not slack.dms
    assert not slack.channels


def test_complete_gated_by_slack_enabled(release, slack):
    release, _, _ = release
    release.status = DataRelease.Status.COMPLETED
    release.save()
    notify.notify_release_complete(release)
    assert not slack.channels


# ── release iniciada: aviso de time no canal ──────────────────────────────────


def test_started_posts_to_channel(release, slack):
    """start posta a âncora do step com as atividades e grava o ts no banco."""
    release, _, _ = release
    release.status = DataRelease.Status.ACTIVE
    step = release.steps.get(key="a")
    step.slack_thread_ts = ""
    step.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_release_started(release)

    assert not slack.dms  # aviso de time: sem DM individual
    assert len(slack.channels) == 1
    text = slack.channels[0][1]
    assert "*Release 1* · Step A" in text
    assert "• A1" in text
    assert "• A2" in text
    assert f"<{SITE}/releases/r1/|Ver DPN>" in text
    assert release.steps.get(key="a").slack_thread_ts == "ts-1"


def test_started_requires_channel(release, slack):
    release, _, _ = release
    release.status = DataRelease.Status.ACTIVE
    release.save()
    with override_settings(SLACK_ENABLED=True):
        notify.notify_release_started(release)
    assert not slack.dms
    assert not slack.channels


def test_started_gated_by_slack_enabled(release, slack):
    release, _, _ = release
    release.status = DataRelease.Status.ACTIVE
    release.save()
    notify.notify_release_started(release)
    assert not slack.channels


# ── threads por step: replies na âncora e âncora lazy ────────────────────────


def test_reply_uses_step_thread(release, slack):
    """Evento de atividade no canal posta reply na thread gravada do step."""
    _, a1, _ = release  # step com slack_thread_ts="thread-a" (fixture)
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM"):
        notify.notify_ready(a1)

    assert len(slack.posts) == 1
    _, text, thread_ts = slack.posts[0]
    assert thread_ts == "thread-a"
    assert "esta atividade está pronta para você começar." in text


def test_anchor_created_lazily_on_first_event(release, slack):
    """Sem ts gravado, o 1º evento posta a âncora e o reply na thread dela."""
    release, a1, _ = release
    step = release.steps.get(key="a")
    step.slack_thread_ts = ""
    step.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM", SITE_URL=SITE):
        notify.notify_ready(a1)

    assert len(slack.posts) == 2
    anchor_text = slack.posts[0][1]
    assert "*Release 1* · Step A" in anchor_text
    assert "• A1" in anchor_text
    assert slack.posts[0][2] is None  # âncora é top-level
    assert slack.posts[1][2] == "ts-1"  # reply na thread recém-criada
    assert release.steps.get(key="a").slack_thread_ts == "ts-1"


def test_anchor_race_keeps_existing_thread(release, slack):
    """Âncora postada mas o banco já tem ts: reusa o ts existente."""
    release, _, _ = release
    step = release.steps.get(key="a")
    step.slack_thread_ts = "already"
    step.save()

    ts = notify._post_step_anchor(slack, step)

    assert ts == "already"
    assert len(slack.posts) == 1  # a âncora foi postada, mas não gravada
    assert release.steps.get(key="a").slack_thread_ts == "already"


def test_started_posts_one_anchor_per_step(release, slack):
    """start posta 1 âncora por step com atividades; step vazio é pulado."""
    release, _, _ = release
    ReleaseStep.objects.create(release=release, key="empty", label="Vazio", order=1, color="#000099")
    ReleaseStep.objects.filter(release=release).update(slack_thread_ts="")
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM"):
        notify.notify_release_started(release)

    assert len(slack.posts) == 1  # só o step "a" (o "empty" não tem atividades)
    assert "*Release 1* · Step A" in slack.posts[0][1]
    assert release.steps.get(key="a").slack_thread_ts == "ts-1"
    assert release.steps.get(key="empty").slack_thread_ts == ""


def test_complete_posts_without_thread(release, slack):
    """Conclusão é marco final: mensagem de topo, sem thread."""
    release, _, _ = release
    release.status = DataRelease.Status.COMPLETED
    release.save()
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM"):
        notify.notify_release_complete(release)

    assert len(slack.posts) == 1
    assert slack.posts[0][2] is None


def test_anchor_failure_reply_falls_back_to_top_level(release, monkeypatch, caplog):
    """Âncora falha (exceção): o evento ainda sai como mensagem de topo."""
    release, a1, _ = release
    step = release.steps.get(key="a")
    step.slack_thread_ts = ""
    step.save()

    class FlakySlack(FakeSlack):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def post_to_channel(self, channel_id, text, thread_ts=None):
            self.calls += 1
            if self.calls == 1:  # 1ª chamada = âncora
                raise RuntimeError("slack down")
            return super().post_to_channel(channel_id, text, thread_ts)

    flaky = FlakySlack()
    monkeypatch.setattr("idac_drd.integrations.notify._slack_client", lambda: flaky)
    with override_settings(SLACK_ENABLED=True, SLACK_CHANNEL_ID="C_TEAM"):
        notify.notify_ready(a1)

    assert "Slack anchor failed for step" in caplog.text
    assert len(flaky.posts) == 1
    _, text, thread_ts = flaky.posts[0]
    assert thread_ts is None  # degradou para top-level
    assert "pronta para você começar" in text


# ── caminho real: on_commit dispara os avisos ────────────────────────────────


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_ready_on_start(monkeypatch):
    """start_release avisa todos os assignees de atividades prontas (todo)."""
    ready_calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_ready", ready_calls.append)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-ready", status=DataRelease.Status.DRAFT)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0, assignee=reviewer)
    Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=reviewer)
    try:
        start_release(release)
        assert {c.key for c in ready_calls} == {"a1", "a2"}
    finally:
        release.delete()


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_started(monkeypatch):
    """start_release avisa no canal que a release iniciou (1x, aviso de time)."""
    started_calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_release_started", started_calls.append)

    release = DataRelease.objects.create(name="P", slug="p-started", status=DataRelease.Status.DRAFT)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    try:
        start_release(release)
        assert len(started_calls) == 1
        assert started_calls[0] is release
    finally:
        release.delete()


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_ready_on_auto_unblock(monkeypatch):
    """Conclusão do pré-requisito desbloqueia o dependente → aviso ao assignee."""
    ready_calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_ready", ready_calls.append)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-unblock", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    a1 = Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    a2 = Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1, assignee=reviewer)
    a2.depends_on.set([a1])
    _block_until_prerequisites(a2)
    assert a2.status == Activity.Status.BLOCKED
    try:
        transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=None)
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=None)
        transition_activity(a1, to_status=Activity.Status.DONE, actor=None)
        assert len(ready_calls) == 1
        assert ready_calls[0].key == "a2"
    finally:
        release.delete()


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_ready_on_manual_unblock(monkeypatch):
    """Desbloqueio manual (blocked → todo) devolve a bola ao assignee."""
    ready_calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_ready", ready_calls.append)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-manual", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    a1 = Activity.objects.create(
        release=release,
        step=step,
        key="a1",
        label="A1",
        order=0,
        status=Activity.Status.BLOCKED,
        blocked_reason="Waiting on prerequisites: X",
        assignee=reviewer,
    )
    try:
        transition_activity(a1, to_status=Activity.Status.TODO, actor=None)
        assert len(ready_calls) == 1
        assert ready_calls[0].key == "a1"
    finally:
        release.delete()


@pytest.mark.django_db(transaction=True)
def test_add_activity_in_active_release_notifies_assignee(monkeypatch):
    """Atividade nova numa release em execução nasce pronta — o assignee é avisado."""
    ready_calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_ready", ready_calls.append)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-add", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    try:
        activity = add_activity(release, label="Nova", step=step, assignee=reviewer)
        assert len(ready_calls) == 1
        assert ready_calls[0].key == activity.key
    finally:
        release.delete()


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_after_review_and_rejection(monkeypatch):
    """Caminho real: in_review e rejeição agendam on_commit; rodam no commit."""
    review_calls, rejection_calls = [], []

    def capture_rejection(activity, comment, reviewer):
        rejection_calls.append((activity, comment, reviewer))

    monkeypatch.setattr("idac_drd.integrations.notify.notify_review", review_calls.append)
    monkeypatch.setattr("idac_drd.integrations.notify.notify_rejection", capture_rejection)

    reviewer = ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob", slack_id="U_BOB")
    release = DataRelease.objects.create(name="P", slug="p-notify", status=DataRelease.Status.DRAFT)
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


@pytest.mark.django_db(transaction=True)
def test_on_commit_notifies_complete_when_last_approved(monkeypatch):
    """Aprovar a última atividade dispara o aviso de conclusão — o caminho
    inverso (release completa → ativa) não notifica."""
    calls = []

    monkeypatch.setattr("idac_drd.integrations.notify.notify_release_complete", calls.append)

    release = DataRelease.objects.create(name="P", slug="p-complete", status=DataRelease.Status.ACTIVE)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    a1 = Activity.objects.create(release=release, step=step, key="a1", label="A1", order=0)
    a2 = Activity.objects.create(release=release, step=step, key="a2", label="A2", order=1)
    try:
        transition_activity(a1, to_status=Activity.Status.IN_PROGRESS, actor=None)
        transition_activity(a1, to_status=Activity.Status.IN_REVIEW, actor=None)
        transition_activity(a1, to_status=Activity.Status.DONE, actor=None)
        assert calls == []  # a2 ainda pendente: release continua ativa
        transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=None)
        transition_activity(a2, to_status=Activity.Status.IN_REVIEW, actor=None)
        transition_activity(a2, to_status=Activity.Status.DONE, actor=None)
        assert len(calls) == 1
        assert calls[0].slug == "p-complete"
        assert calls[0].status == DataRelease.Status.COMPLETED
        # reverter para active não notifica de novo
        transition_activity(a2, to_status=Activity.Status.IN_PROGRESS, actor=None)
        assert len(calls) == 1
    finally:
        release.delete()
