"""Optional Slack integration — send DMs and channel messages via the Web API.

Inert (returns None) unless settings.SLACK_ENABLED is True.
"""

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from idac_drd.integrations._base import IntegrationAPIError


class SlackAPIError(IntegrationAPIError):
    """Raised when the Slack API returns an error (HTTP non-200 or ``ok: false``)."""


class SlackClient:
    BASE_URL = "https://slack.com/api"

    def __init__(self, bot_token: str, timeout: int = 30):
        self.bot_token = bot_token
        self.timeout = timeout

    def _post(self, method: str, payload: dict) -> dict:
        # form-urlencoded é o formato canônico do Slack; JSON body é ignorado
        # por alguns workspaces (erro "missing required field" com campo presente).
        resp = requests.post(
            f"{self.BASE_URL}/{method}",
            headers={"Authorization": f"Bearer {self.bot_token}"},
            data=payload,
            timeout=self.timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            raise SlackAPIError(f"Slack API returned invalid JSON (HTTP {resp.status_code}).") from None
        if resp.status_code != 200:
            raise SlackAPIError(
                f"Slack API error: {data.get('error', f'HTTP {resp.status_code}')}",
                status_code=resp.status_code,
            )
        if not data.get("ok"):
            # Slack reports most API errors as HTTP 200 with ok:false.
            # response_metadata.messages aponta o campo/escopo exato do erro.
            detail = data.get("error")
            meta = data.get("response_metadata", {}).get("messages")
            if meta:
                detail = f"{detail}: {'; '.join(meta)}"
            raise SlackAPIError(f"Slack API error: {detail}")
        return data

    def lookup_user_by_email(self, email: str) -> str:
        """Resolve an email to a Slack user id."""
        data = self._post("users.lookupByEmail", {"email": email})
        return data["user"]["id"]

    def send_dm(self, email: str, text: str) -> dict:
        """Send a DM to the user with the given email (opens the DM if needed).

        Mentioning the user in ``text`` requires the raw id: ``<@USER_ID>``.
        """
        return self.send_dm_to_user(self.lookup_user_by_email(email), text)

    def send_dm_to_user(self, user_id: str, text: str) -> dict:
        """Send a DM to a Slack user id (opens the DM if needed)."""
        channel = self._post("conversations.open", {"users": user_id})
        # as_user foi removido da API (deprecated_argument) — bot posta como bot.
        return self._post("chat.postMessage", {"channel": channel["channel"]["id"], "text": text})

    def post_to_channel(self, channel_id: str, text: str, thread_ts: str | None = None) -> dict:
        """Post a message to a channel the bot has joined.

        ``thread_ts`` (timestamp de uma mensagem do mesmo canal) posta a
        mensagem como reply naquela thread.
        """
        payload = {"channel": channel_id, "text": text}
        if thread_ts:
            payload["thread_ts"] = thread_ts
        return self._post("chat.postMessage", payload)

    def check(self) -> bool:
        """Validate the bot token via auth.test."""
        self._post("auth.test", {})
        return True


def _slack_client() -> SlackClient:
    if not settings.SLACK_BOT_TOKEN:
        raise ImproperlyConfigured("Slack integration enabled (SLACK_ENABLED=True) but SLACK_BOT_TOKEN is not set.")
    return SlackClient(settings.SLACK_BOT_TOKEN)


def send_slack_dm(email: str, text: str) -> dict | None:
    """Send a DM to ``email`` — only when SLACK_ENABLED=True.

    Returns None (no-op) when the integration is disabled.
    """
    if not settings.SLACK_ENABLED:
        return None
    return _slack_client().send_dm(email, text)


def post_slack_message(text: str, thread_ts: str | None = None) -> dict | None:
    """Post a message — to SLACK_CHANNEL_ID when set, else DM to SLACK_DEV_USER_ID (dev fallback).

    Only when SLACK_ENABLED=True. Returns None (no-op) when the integration is disabled.
    """
    if not settings.SLACK_ENABLED:
        return None
    client = _slack_client()
    if settings.SLACK_CHANNEL_ID:
        return client.post_to_channel(settings.SLACK_CHANNEL_ID, text, thread_ts=thread_ts)
    if settings.SLACK_DEV_USER_ID:
        return client.send_dm_to_user(settings.SLACK_DEV_USER_ID, text)
    raise ImproperlyConfigured(
        "Slack integration enabled (SLACK_ENABLED=True) but SLACK_CHANNEL_ID and SLACK_DEV_USER_ID are both unset."
    )


def check_slack() -> bool:
    """Smoke-test the Slack connection. Returns False when the integration is disabled."""
    if not settings.SLACK_ENABLED:
        return False
    _slack_client().check()
    return True
