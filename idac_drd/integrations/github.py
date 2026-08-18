"""Optional GitHub integration — create issues via the REST API.

Inert (returns None) unless settings.GH_ENABLED is True.
"""

import logging
import unicodedata

import requests
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from idac_drd.integrations._base import IntegrationAPIError, raise_response_error

logger = logging.getLogger(__name__)

# GitHub Project V2 "Software" (#39) da org linea-it: os SingleSelects "Área" e
# "Size" alimentam os selects de area/size das activities. Requer escopo read:project
# no token; sem ele (Resource not accessible) as listas voltam vazias.
ORG = "linea-it"
SOFTWARE_PROJECT_NUMBER = 39
DEFAULT_REPO = f"{ORG}/idac_drd"  # usado quando a activity não define github_repo


class GitHubAPIError(IntegrationAPIError):
    """Raised when the GitHub API returns a non-2xx response."""


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, timeout: int = 30):
        self.token = token
        self.timeout = timeout

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: list[str] | None = None,
        assignees: list[str] | None = None,
    ) -> dict:
        """Create an issue on {owner}/{repo}.

        Returns the created issue dict; useful fields: ``number`` and ``html_url``
        (callers should derive the URL from owner/repo + number, not store it).
        """
        payload = {"title": title, "body": body, "labels": labels or []}
        if assignees:
            payload["assignees"] = assignees
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        resp = requests.post(
            url,
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        raise_response_error(resp, GitHubAPIError)
        return resp.json()

    def update_issue(self, owner: str, repo: str, number: int, **fields) -> dict:
        """Update an issue ({owner}/{repo}#{number}) via PATCH.

        ``fields`` are merged into the JSON body — e.g. ``state="closed"``,
        ``state_reason="completed"``. Idempotent: PATCHing a state it already
        has is a no-op (returns 200 with the current issue).
        """
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues/{number}"
        resp = requests.patch(
            url,
            headers=self._headers(),
            json=fields,
            timeout=self.timeout,
        )
        raise_response_error(resp, GitHubAPIError)
        return resp.json()

    def check(self) -> bool:
        """Validate the token against GET /user."""
        resp = requests.get(f"{self.BASE_URL}/user", headers=self._headers(), timeout=self.timeout)
        raise_response_error(resp, GitHubAPIError)
        return True

    def list_org_repos(self, org: str = ORG) -> list[str]:
        """Names (sorted) of the org's repositories, paginated (100 per page)."""
        repos: list[str] = []
        page = 1
        while True:
            resp = requests.get(
                f"{self.BASE_URL}/orgs/{org}/repos",
                headers=self._headers(),
                params={"per_page": 100, "page": page},
                timeout=self.timeout,
            )
            raise_response_error(resp, GitHubAPIError)
            data = resp.json()
            repos.extend(r["name"] for r in data)
            if len(data) < 100:
                break
            page += 1
        return sorted(repos)

    def project_single_select_options(
        self, org: str = ORG, project_number: int = SOFTWARE_PROJECT_NUMBER
    ) -> tuple[list[str], list[str], list[str]]:
        """Options of the Área/Size/Status SingleSelect fields of a Project V2.

        Returns (areas, sizes, statuses). Without read:project scope (or any
        API error) all lists are empty — the caller must treat them as
        best-effort.
        """
        query = (
            f'query {{ organization(login: "{org}") {{'
            f"projectV2(number: {project_number}) {{"
            "fields(first: 100) { nodes { ... on ProjectV2SingleSelectField { name options { name } } } }"
            "} } }"
        )
        try:
            resp = requests.post(
                f"{self.BASE_URL}/graphql",
                headers=self._headers(),
                json={"query": query},
                timeout=self.timeout,
            )
            raise_response_error(resp, GitHubAPIError)
            body = resp.json()
            # GraphQL responde 200 mesmo com erro de negócio (ex.: sem read:project)
            if "errors" in body:
                raise GitHubAPIError(str(body["errors"][0].get("message", body["errors"])))
            nodes = body["data"]["organization"]["projectV2"]["fields"]["nodes"]
        except (GitHubAPIError, KeyError, TypeError, requests.RequestException) as exc:
            logger.warning("GitHub project %s/%s options unavailable: %s", org, project_number, exc)
            return [], [], []
        areas, sizes, statuses = [], [], []
        for node in nodes or []:
            # normalize() remove acentos: "Área" → "Area"
            name = unicodedata.normalize("NFD", node.get("name", "").lower()).encode("ascii", "ignore").decode()
            options = [o["name"] for o in node.get("options") or []]
            if "area" in name:
                areas = options
            elif "size" in name:
                sizes = options
            elif "status" in name:
                statuses = options
        return areas, sizes, statuses

    def project_field(self, org: str = ORG, project_number: int = SOFTWARE_PROJECT_NUMBER) -> tuple[str, str, dict]:
        """Resolve o campo single-select ``Status`` de um Project V2.

        Returns (project_id, field_id, {option_name: option_id}). Raises
        GitHubAPIError when the project or field is not found.
        """
        query = (
            f'query {{ organization(login: "{org}") {{'
            f"projectV2(number: {project_number}) {{ id "
            "fields(first: 100) { nodes { ... on ProjectV2SingleSelectField { id name options { id name } } } }"
            "} } }"
        )
        resp = requests.post(
            f"{self.BASE_URL}/graphql",
            headers=self._headers(),
            json={"query": query},
            timeout=self.timeout,
        )
        raise_response_error(resp, GitHubAPIError)
        body = resp.json()
        if "errors" in body:
            raise GitHubAPIError(str(body["errors"][0].get("message", body["errors"])))
        project = body["data"]["organization"]["projectV2"]
        for node in project["fields"]["nodes"] or []:
            if node.get("name", "").lower() == "status":
                options = {o["name"]: o["id"] for o in node.get("options") or []}
                return project["id"], node["id"], options
        raise GitHubAPIError(f"Project {org}/{project_number} has no Status single-select field")

    def project_single_select_fields(
        self, org: str = ORG, project_number: int = SOFTWARE_PROJECT_NUMBER
    ) -> tuple[str, dict[str, tuple[str, dict]]]:
        """Todos os campos SingleSelect de um Project V2.

        Returns (project_id, {nome_normalizado: (field_id, {option: option_id})}).
        Nomes normalizados sem acento e minúsculo ("Area", "Size", "Status") —
        o mesmo padrão de ``project_single_select_options``. Best-effort: em
        erro (ex.: sem read:project) retorna ("", {}) — o chamador pula o item
        do projeto sem quebrar a sync.
        """
        query = (
            f'query {{ organization(login: "{org}") {{'
            f"projectV2(number: {project_number}) {{ id "
            "fields(first: 100) { nodes { ... on ProjectV2SingleSelectField { id name options { id name } } } }"
            "} } }"
        )
        try:
            resp = requests.post(
                f"{self.BASE_URL}/graphql",
                headers=self._headers(),
                json={"query": query},
                timeout=self.timeout,
            )
            raise_response_error(resp, GitHubAPIError)
            body = resp.json()
            # GraphQL responde 200 mesmo com erro de negócio (ex.: sem read:project)
            if "errors" in body:
                raise GitHubAPIError(str(body["errors"][0].get("message", body["errors"])))
            project = body["data"]["organization"]["projectV2"]
        except (GitHubAPIError, KeyError, TypeError, requests.RequestException) as exc:
            logger.warning("GitHub project %s/%s fields unavailable: %s", org, project_number, exc)
            return "", {}
        fields: dict[str, tuple[str, dict]] = {}
        for node in project["fields"]["nodes"] or []:
            # normalize() remove acentos: "Área" → "area"
            name = unicodedata.normalize("NFD", node.get("name", "").lower()).encode("ascii", "ignore").decode()
            if not name:
                continue
            fields[name] = (node["id"], {o["name"]: o["id"] for o in node.get("options") or []})
        return project["id"], fields

    def add_project_item(self, project_id: str, content_id: str) -> str:
        """Add an issue/PR to a Project V2; returns the new item's node id."""
        query = (
            "mutation { addProjectV2ItemById(input: {"
            f'projectId: "{project_id}", contentId: "{content_id}"'
            "}) { item { id } } }"
        )
        resp = requests.post(
            f"{self.BASE_URL}/graphql",
            headers=self._headers(),
            json={"query": query},
            timeout=self.timeout,
        )
        raise_response_error(resp, GitHubAPIError)
        body = resp.json()
        if "errors" in body:
            raise GitHubAPIError(str(body["errors"][0].get("message", body["errors"])))
        return body["data"]["addProjectV2ItemById"]["item"]["id"]

    def set_project_item_status(self, project_id: str, item_id: str, field_id: str, option_id: str) -> dict:
        """Set the single-select field of a project item (status, área ou size)."""
        query = (
            "mutation { updateProjectV2ItemFieldValue(input: {"
            f'projectId: "{project_id}", itemId: "{item_id}", fieldId: "{field_id}", '
            f'value: {{ singleSelectOptionId: "{option_id}" }}'
            "}) { projectV2Item { id } } }"
        )
        resp = requests.post(
            f"{self.BASE_URL}/graphql",
            headers=self._headers(),
            json={"query": query},
            timeout=self.timeout,
        )
        raise_response_error(resp, GitHubAPIError)
        body = resp.json()
        if "errors" in body:
            raise GitHubAPIError(str(body["errors"][0].get("message", body["errors"])))
        return body["data"]["updateProjectV2ItemFieldValue"]


def _github_client() -> GitHubClient:
    if not settings.GH_TOKEN:
        raise ImproperlyConfigured("GitHub integration enabled (GH_ENABLED=True) but GH_TOKEN is not set.")
    return GitHubClient(settings.GH_TOKEN)


def create_github_issue(owner: str, repo: str, title: str, body: str, labels: list[str] | None = None) -> dict | None:
    """Create an issue on {owner}/{repo} — only when GH_ENABLED=True.

    Returns None (no-op) when the integration is disabled.
    """
    if not settings.GH_ENABLED:
        return None
    return _github_client().create_issue(owner, repo, title, body, labels)


def check_github() -> bool:
    """Smoke-test the GitHub connection. Returns False when the integration is disabled."""
    if not settings.GH_ENABLED:
        return False
    return _github_client().check()


def fetch_github_options() -> dict:
    """Repos da org + áreas/sizes do project Software, para os selects das activities.

    Best-effort: sem GH_TOKEN (ou em qualquer erro da API) retorna listas vazias
    — nunca levanta. GH_ENABLED não gateia leitura; é flag de escrita. Em falha,
    inclui ``error`` (motivo) no payload para a UI avisar o usuário.
    """
    if not settings.GH_TOKEN:
        logger.warning("GH_TOKEN not set — devolvendo options vazios")
        return {
            "repos": [],
            "areas": [],
            "sizes": [],
            "statuses": [],
            "error": "GH_TOKEN not set",
        }
    client = GitHubClient(settings.GH_TOKEN)
    error = None
    try:
        repos = client.list_org_repos()
    except GitHubAPIError as exc:
        logger.warning("GitHub org repos unavailable: %s", exc)
        repos = []
        error = str(exc)
    areas, sizes, statuses = client.project_single_select_options()
    payload = {"repos": repos, "areas": areas, "sizes": sizes, "statuses": statuses}
    if error:
        payload["error"] = error
    return payload
