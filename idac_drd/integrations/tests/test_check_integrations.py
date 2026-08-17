import io
from unittest import mock

import pytest
from django.core.management import call_command
from django.test import override_settings


def test_all_disabled_prints_skip_and_returns_zero():
    out = io.StringIO()
    with override_settings(GH_ENABLED=False, GLPI_ENABLED=False, SLACK_ENABLED=False):
        ret = call_command("check_integrations", stdout=out)

    assert ret is None  # exit code 0 (default)
    text = out.getvalue()
    assert text.count("SKIP") == 3
    assert "github" in text and "glpi" in text and "slack" in text


def test_failed_check_exits_one():
    out = io.StringIO()
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        with mock.patch("idac_drd.integrations.slack.check_slack", side_effect=RuntimeError("boom")):
            with pytest.raises(SystemExit) as exc_info:
                call_command("check_integrations", stdout=out)

    assert exc_info.value.code == 1
    assert "slack: FAIL" in out.getvalue()


def test_all_ok_returns_zero():
    out = io.StringIO()
    with override_settings(
        GH_ENABLED=True,
        GH_TOKEN="tok",
        GLPI_ENABLED=True,
        GLPI_API_URL="https://glpi.example",
        GLPI_USER="u",
        GLPI_PASSWORD="p",
        GLPI_APP_TOKEN="a",
        SLACK_ENABLED=True,
        SLACK_BOT_TOKEN="bot-tok",
    ):
        with (
            mock.patch("idac_drd.integrations.github.check_github", return_value=True),
            mock.patch("idac_drd.integrations.glpi.check_glpi", return_value=True),
            mock.patch("idac_drd.integrations.slack.check_slack", return_value=True),
        ):
            ret = call_command("check_integrations", stdout=out)

    assert ret is None  # exit code 0 (default)
    assert out.getvalue().count(": OK") == 3
