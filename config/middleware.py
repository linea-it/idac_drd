"""Garante /drd nos Location quando o nginx remove o prefixo no proxy."""

from urllib.parse import urlsplit, urlunsplit

from django.conf import settings


def prefix_location(location, script_name, allowed_hosts=None):
    if not location or not script_name:
        return location
    script_name = script_name.rstrip("/")
    parts = urlsplit(location)
    path = parts.path or "/"

    def prefix_path(current):
        if current == "/":
            return f"{script_name}/"
        if current == script_name or current.startswith(f"{script_name}/"):
            return current
        if not current.startswith("/"):
            return current
        return f"{script_name}{current}"

    if parts.scheme or parts.netloc:
        host = (parts.hostname or "").lower()
        allowed = {h.lower() for h in (allowed_hosts or []) if h != "*"}
        if host and allowed and host not in allowed:
            return location
        return urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                prefix_path(path),
                parts.query,
                parts.fragment,
            )
        )
    if location.startswith("/"):
        return urlunsplit(("", "", prefix_path(path), parts.query, parts.fragment))
    return location


class PrefixRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        location = response.get("Location")
        script = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
        if location and script:
            response["Location"] = prefix_location(location, script, settings.ALLOWED_HOSTS)
        return response
