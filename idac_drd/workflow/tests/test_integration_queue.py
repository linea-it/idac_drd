"""Fila FIFO das integrações: a view responde antes do HTTP externo."""

import time

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from idac_drd.workflow.models import Activity, DataRelease, ReleaseStep
from idac_drd.workflow.services import drain_integrations, hold_integrations

User = get_user_model()


@pytest.mark.django_db(transaction=True)
def test_start_responds_before_http_then_fifo(monkeypatch):
    calls = []

    def slow_notify(release):
        calls.append("notify_release_started")
        time.sleep(0.05)

    def slow_sync(activity, actor=None):
        calls.append(f"sync:{activity.key}")
        time.sleep(0.05)

    monkeypatch.setattr("idac_drd.integrations.notify.notify_release_started", slow_notify)
    monkeypatch.setattr("idac_drd.integrations.sync.sync_activity", slow_sync)

    staff = User.objects.create_user(username="staff-queue", password="pass", is_staff=True)
    release = DataRelease.objects.create(name="Queue", slug="queue-start", status=DataRelease.Status.DRAFT)
    step = ReleaseStep.objects.create(release=release, key="a", label="Step A", order=0, color="#000099")
    Activity.objects.create(release=release, step=step, key="s1", label="S1", order=0)
    Activity.objects.create(release=release, step=step, key="s2", label="S2", order=1)

    client = APIClient()
    client.force_authenticate(user=staff)
    hold_integrations()
    try:
        with override_settings(INTEGRATIONS_EAGER=False):
            started = time.monotonic()
            res = client.post(f"/api/releases/{release.slug}/start/", format="json")
            elapsed = time.monotonic() - started
        assert res.status_code == 200
        assert res.data["status"] == "active"
        assert elapsed < 1.0
        assert calls == []
        drain_integrations()
        assert calls == ["notify_release_started", "sync:s1", "sync:s2"]
    finally:
        drain_integrations()
        release.delete()
