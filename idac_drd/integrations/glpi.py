"""Optional GLPI integration — create tickets via the GLPI REST API.

Inert (returns None) unless settings.GLPI_ENABLED is True.

Auth flow: ``initSession`` (login/password as form-urlencoded data) returns a
Session-Token; the ``App-Token`` header is required on every call, including
``initSession``. A fresh session is opened per call — no caching (tokens expire
server-side in ~30min; per-call sessions keep the client stateless).
"""

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from idac_drd.integrations._base import IntegrationAPIError, raise_response_error

_REQUIRED_CREDENTIALS = ("GLPI_API_URL", "GLPI_USER", "GLPI_PASSWORD", "GLPI_APP_TOKEN")


class GlpiAPIError(IntegrationAPIError):
    """Raised when the GLPI API returns a non-2xx response."""


class GlpiClient:
    def __init__(self, api_url: str, user: str, password: str, app_token: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        self.user = user
        self.password = password
        self.app_token = app_token
        self.timeout = timeout

    def _headers(self, session_token: str | None = None) -> dict:
        headers = {"App-Token": self.app_token}
        if session_token:
            headers["Session-Token"] = session_token
        return headers

    def init_session(self) -> str:
        """Open a GLPI session; returns the Session-Token."""
        resp = requests.post(
            f"{self.api_url}/initSession",
            headers=self._headers(),
            data={"login": self.user, "password": self.password},
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()["session_token"]

    def create_ticket(self, name: str, content: str, ticket_type: int = 1) -> dict:
        """Create a ticket (type 1=incident, 2=request). Returns the ticket dict (``id``)."""
        session_token = self.init_session()
        resp = requests.post(
            f"{self.api_url}/Ticket",
            headers=self._headers(session_token),
            json={"name": name, "content": content, "type": ticket_type},
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def update_ticket(self, ticket_id: int, **fields) -> dict:
        """Update a ticket via PUT /Ticket/{id}; ``fields`` are the ticket fields."""
        session_token = self.init_session()
        resp = requests.put(
            f"{self.api_url}/Ticket/{ticket_id}",
            headers=self._headers(session_token),
            json=fields,
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def check(self) -> bool:
        """Open a session and list entities to validate the Session-Token."""
        session_token = self.init_session()
        resp = requests.get(
            f"{self.api_url}/getMyEntities",
            headers=self._headers(session_token),
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return True


def _glpi_client() -> GlpiClient:
    missing = [name for name in _REQUIRED_CREDENTIALS if not getattr(settings, name)]
    if missing:
        raise ImproperlyConfigured(f"GLPI integration enabled (GLPI_ENABLED=True) but missing: {', '.join(missing)}.")
    if not settings.GLPI_API_URL.lower().startswith("https://"):
        raise ImproperlyConfigured("GLPI_API_URL must use https — credentials travel in plain text otherwise.")
    return GlpiClient(
        settings.GLPI_API_URL,
        settings.GLPI_USER,
        settings.GLPI_PASSWORD,
        settings.GLPI_APP_TOKEN,
    )


def create_glpi_ticket(name: str, content: str, ticket_type: int = 1) -> dict | None:
    """Create a GLPI ticket — only when GLPI_ENABLED=True.

    Returns None (no-op) when the integration is disabled.
    """
    if not settings.GLPI_ENABLED:
        return None
    return _glpi_client().create_ticket(name, content, ticket_type)


def check_glpi() -> bool:
    """Smoke-test the GLPI connection. Returns False when the integration is disabled."""
    if not settings.GLPI_ENABLED:
        return False
    return _glpi_client().check()
