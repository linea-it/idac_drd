from unittest import mock

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from idac_drd.integrations.slack import SlackAPIError, check_slack, post_slack_message, send_slack_dm

SLACK_HEADERS = {"Authorization": "Bearer bot-tok"}


@mock.patch("requests.post")
def test_disabled_returns_none_without_calling_api(mock_post):
    with override_settings(SLACK_ENABLED=False, SLACK_BOT_TOKEN="bot-tok"):
        assert send_slack_dm("user@example.com", "hi") is None
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_enabled_without_token_raises(mock_post):
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN=""):
        with pytest.raises(ImproperlyConfigured):
            send_slack_dm("user@example.com", "hi")
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_send_dm_success(mock_post, fake_response):
    mock_post.side_effect = [
        fake_response(200, {"ok": True, "user": {"id": "U123"}}),
        fake_response(200, {"ok": True, "channel": {"id": "C456"}}),
        fake_response(200, {"ok": True, "channel": "C456", "ts": "1700000000.000001"}),
    ]
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        result = send_slack_dm("user@example.com", "Hello <@U123>")

    calls = mock_post.call_args_list
    assert len(calls) == 3
    assert calls[0].args[0] == "https://slack.com/api/users.lookupByEmail"
    assert calls[0].kwargs["data"] == {"email": "user@example.com"}
    assert calls[1].args[0] == "https://slack.com/api/conversations.open"
    assert calls[1].kwargs["data"] == {"users": "U123"}
    assert calls[2].args[0] == "https://slack.com/api/chat.postMessage"
    assert calls[2].kwargs["data"] == {
        "channel": "C456",
        "text": "Hello <@U123>",
        "unfurl_links": "false",
        "unfurl_media": "false",
    }
    assert all(call.kwargs["headers"] == SLACK_HEADERS for call in calls)
    assert result["ts"] == "1700000000.000001"


@mock.patch("requests.post")
def test_slack_ok_false_raises(mock_post, fake_response):
    mock_post.return_value = fake_response(200, {"ok": False, "error": "users_not_found"})
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        with pytest.raises(SlackAPIError) as exc_info:
            send_slack_dm("missing@example.com", "hi")
    assert "users_not_found" in str(exc_info.value)


@mock.patch("requests.post")
def test_slack_ok_false_includes_response_metadata(mock_post, fake_response):
    mock_post.return_value = fake_response(
        200,
        {
            "ok": False,
            "error": "invalid_arguments",
            "response_metadata": {"messages": ["[ERROR] missing required field: channel"]},
        },
    )
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        with pytest.raises(SlackAPIError) as exc_info:
            send_slack_dm("missing@example.com", "hi")
    assert "invalid_arguments" in str(exc_info.value)
    assert "missing required field: channel" in str(exc_info.value)


@mock.patch("requests.post")
def test_slack_http_error_raises(mock_post, fake_response):
    mock_post.return_value = fake_response(500, {"error": "internal_error"})
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        with pytest.raises(SlackAPIError) as exc_info:
            check_slack()
    assert exc_info.value.status_code == 500


@mock.patch("requests.post")
def test_post_message_requires_channel_or_dev_user(mock_post):
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok", SLACK_CHANNEL_ID="", SLACK_DEV_USER_ID=""):
        with pytest.raises(ImproperlyConfigured):
            post_slack_message("hi")
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_post_message_to_channel(mock_post, fake_response):
    mock_post.return_value = fake_response(200, {"ok": True, "channel": "C1", "ts": "1.2"})
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok", SLACK_CHANNEL_ID="C1", SLACK_DEV_USER_ID=""):
        post_slack_message("hi")
    mock_post.assert_called_once_with(
        "https://slack.com/api/chat.postMessage",
        headers=SLACK_HEADERS,
        data={"channel": "C1", "text": "hi", "unfurl_links": "false", "unfurl_media": "false"},
        timeout=30,
    )


@mock.patch("requests.post")
def test_post_message_to_thread(mock_post, fake_response):
    mock_post.return_value = fake_response(200, {"ok": True, "channel": "C1", "ts": "1.2"})
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok", SLACK_CHANNEL_ID="C1", SLACK_DEV_USER_ID=""):
        post_slack_message("hi", thread_ts="1700000000.000001")
    mock_post.assert_called_once_with(
        "https://slack.com/api/chat.postMessage",
        headers=SLACK_HEADERS,
        data={
            "channel": "C1",
            "text": "hi",
            "unfurl_links": "false",
            "unfurl_media": "false",
            "thread_ts": "1700000000.000001",
        },
        timeout=30,
    )


@mock.patch("requests.post")
def test_post_message_falls_back_to_dev_user_dm(mock_post, fake_response):
    mock_post.side_effect = [
        fake_response(200, {"ok": True, "channel": {"id": "D1"}}),
        fake_response(200, {"ok": True, "channel": "D1", "ts": "1.2"}),
    ]
    with override_settings(
        SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok", SLACK_CHANNEL_ID="", SLACK_DEV_USER_ID="UARSZNZC7"
    ):
        post_slack_message("hi")

    calls = mock_post.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == "https://slack.com/api/conversations.open"
    assert calls[0].kwargs["data"] == {"users": "UARSZNZC7"}
    assert calls[1].args[0] == "https://slack.com/api/chat.postMessage"
    assert calls[1].kwargs["data"] == {
        "channel": "D1",
        "text": "hi",
        "unfurl_links": "false",
        "unfurl_media": "false",
    }


@mock.patch("requests.post")
def test_check_slack(mock_post, fake_response):
    mock_post.return_value = fake_response(200, {"ok": True, "team_id": "T1", "user_id": "B1"})
    with override_settings(SLACK_ENABLED=True, SLACK_BOT_TOKEN="bot-tok"):
        assert check_slack() is True
    assert mock_post.call_args.args[0] == "https://slack.com/api/auth.test"


def test_check_slack_disabled():
    with override_settings(SLACK_ENABLED=False):
        assert check_slack() is False
