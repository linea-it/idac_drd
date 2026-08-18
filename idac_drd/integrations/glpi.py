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

    def create_ticket(
        self,
        name: str,
        content: str,
        ticket_type: int = 1,
        users_id_requester: int | None = None,
        users_id_assign: int | None = None,
    ) -> dict:
        """Create a ticket (type 1=incident, 2=request). Returns the ticket dict (``id``).

        The GLPI API requires the payload wrapped in an ``input`` key
        (see https://helpdesk-dev.linea.org.br/apirest.php).
        """
        payload = {"name": name, "content": content, "type": ticket_type}
        # Actor fields are "virtual" fields in the GLPI API: they need the
        # leading underscore (users_id_* without it is silently ignored).
        if users_id_requester is not None:
            payload["_users_id_requester"] = users_id_requester
        if users_id_assign is not None:
            payload["_users_id_assign"] = users_id_assign
        session_token = self.init_session()
        resp = requests.post(
            f"{self.api_url}/Ticket",
            headers=self._headers(session_token),
            json={"input": payload},
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
            json={"input": fields},
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def get_ticket(self, ticket_id: int) -> dict:
        """Read a ticket (GET /Ticket/{id}) — status atual para idempotência."""
        session_token = self.init_session()
        resp = requests.get(
            f"{self.api_url}/Ticket/{ticket_id}",
            headers=self._headers(session_token),
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def get_ticket_users(self, ticket_id: int) -> list[dict]:
        """Lista os atores do ticket (Ticket_User: ``users_id`` + ``type`` 1=requester, 2=assign, 3=observer).

        A API não expõe os atores no GET /Ticket (sempre ``None``); quem atribuiu
        um ticket só se verifica aqui.
        """
        session_token = self.init_session()
        resp = requests.get(
            f"{self.api_url}/Ticket/{ticket_id}/Ticket_User",
            headers=self._headers(session_token),
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def assign_ticket(self, ticket_id: int, users_id: int) -> dict:
        """Atribui o executor via PUT com o campo virtual ``_users_id_assign`` (int).

        Validado ao vivo (ticket 153): ``_itil_assign`` em LISTA é ignorado
        silenciosamente; o escalar funciona — ``{"_users_id_assign": 38}`` e
        ``{"_itil_assign": {"_type": "user", "users_id": 38}}``. Usamos o mesmo
        campo virtual da criação. O GLPI promove o ticket para processing
        (assigned) sozinho quando o primeiro executor é atribuído — promoção
        automática é feature, não bug.
        """
        session_token = self.init_session()
        resp = requests.put(
            f"{self.api_url}/Ticket/{ticket_id}",
            headers=self._headers(session_token),
            json={"input": {"_users_id_assign": users_id}},
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def unassign_ticket(self, ticket_id: int, ticket_user_id: int) -> dict:
        """Remove um ator do ticket (DELETE /Ticket/{id}/Ticket_User/{ticket_user_id}).

        Usado para desatribuir o executor quando o dashboard perde o assignee.
        """
        session_token = self.init_session()
        resp = requests.delete(
            f"{self.api_url}/Ticket/{ticket_id}/Ticket_User/{ticket_user_id}",
            headers=self._headers(session_token),
            timeout=self.timeout,
        )
        raise_response_error(resp, GlpiAPIError)
        return resp.json()

    def add_followup(self, ticket_id: int, content: str) -> dict:
        """Registra uma nota na timeline do ticket (POST /Ticket/{id}/ITILFollowup).

        Validado ao vivo no perfil Webservices: o app tem o right de Followup.
        """
        session_token = self.init_session()
        resp = requests.post(
            f"{self.api_url}/Ticket/{ticket_id}/ITILFollowup",
            headers=self._headers(session_token),
            json={"input": {"items_id": ticket_id, "itemtype": "Ticket", "content": content}},
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


def create_glpi_ticket(
    name: str,
    content: str,
    ticket_type: int = 1,
    users_id_requester: int | None = None,
    users_id_assign: int | None = None,
) -> dict | None:
    """Create a GLPI ticket — only when GLPI_ENABLED=True.

    Returns None (no-op) when the integration is disabled.
    """
    if not settings.GLPI_ENABLED:
        return None
    return _glpi_client().create_ticket(name, content, ticket_type, users_id_requester, users_id_assign)


def check_glpi() -> bool:
    """Smoke-test the GLPI connection. Returns False when the integration is disabled."""
    if not settings.GLPI_ENABLED:
        return False
    return _glpi_client().check()
