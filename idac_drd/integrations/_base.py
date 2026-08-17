import requests


class IntegrationAPIError(requests.RequestException):
    """Base error for optional external integrations (GitHub, GLPI, Slack)."""

    def __init__(self, message, *, status_code=None, body=None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def error_snippet(resp, limit=300) -> str:
    """Short excerpt of the response body, safe to include in error messages."""
    try:
        data = resp.json()
    except ValueError:
        return (resp.text or "")[:limit]
    return (data if isinstance(data, str) else str(data))[:limit]


def raise_response_error(resp, exc_cls, *, message=None):
    """Re-raise a non-2xx HTTP response as exc_cls with status code and body snippet."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as exc:
        raise exc_cls(message or str(exc), status_code=resp.status_code, body=error_snippet(resp)) from exc
