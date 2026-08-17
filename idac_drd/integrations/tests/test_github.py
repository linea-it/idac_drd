from unittest import mock

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from idac_drd.integrations.github import (
    GitHubAPIError,
    GitHubClient,
    check_github,
    create_github_issue,
    fetch_github_options,
)

GITHUB_HEADERS = {
    "Authorization": "Bearer tok",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


@mock.patch("requests.post")
def test_disabled_returns_none_without_calling_api(mock_post):
    with override_settings(GH_ENABLED=False, GH_TOKEN="tok"):
        assert create_github_issue("owner", "repo", "title", "body") is None
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_enabled_without_token_raises(mock_post):
    with override_settings(GH_ENABLED=True, GH_TOKEN=""):
        with pytest.raises(ImproperlyConfigured):
            create_github_issue("owner", "repo", "title", "body")
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_create_issue_success(mock_post, fake_response):
    mock_post.return_value = fake_response(201, {"number": 42, "html_url": "https://github.com/o/r/issues/42"})
    with override_settings(GH_ENABLED=True, GH_TOKEN="tok"):
        result = create_github_issue("o", "r", "My title", "My body", labels=["bug"])

    mock_post.assert_called_once_with(
        "https://api.github.com/repos/o/r/issues",
        headers=GITHUB_HEADERS,
        json={"title": "My title", "body": "My body", "labels": ["bug"]},
        timeout=30,
    )
    assert result["number"] == 42
    assert result["html_url"] == "https://github.com/o/r/issues/42"


@mock.patch("requests.post")
def test_create_issue_http_error(mock_post, fake_response):
    mock_post.return_value = fake_response(
        422, {"message": "Validation Failed"}, raises=requests.HTTPError("422 Client Error")
    )
    with override_settings(GH_ENABLED=True, GH_TOKEN="tok"):
        with pytest.raises(GitHubAPIError) as exc_info:
            create_github_issue("o", "r", "t", "b")
    assert exc_info.value.status_code == 422
    assert "Validation Failed" in exc_info.value.body


@mock.patch("requests.get")
def test_check_github(mock_get, fake_response):
    mock_get.return_value = fake_response(200, {"login": "carlosadean"})
    with override_settings(GH_ENABLED=True, GH_TOKEN="tok"):
        assert check_github() is True
    mock_get.assert_called_once_with("https://api.github.com/user", headers=GITHUB_HEADERS, timeout=30)


def test_check_github_disabled():
    with override_settings(GH_ENABLED=False, GH_TOKEN=""):
        assert check_github() is False


@mock.patch("requests.get")
def test_list_org_repos_paginates(mock_get, fake_response):
    page1 = [{"name": f"repo-{i:03d}"} for i in range(100)]
    page2 = [{"name": f"repo-{i:03d}"} for i in range(100, 154)]
    mock_get.side_effect = [fake_response(200, page1), fake_response(200, page2)]

    repos = GitHubClient("tok").list_org_repos()

    assert len(repos) == 154
    assert repos == sorted(f"repo-{i:03d}" for i in range(154))
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].kwargs["params"] == {"per_page": 100, "page": 1}
    assert mock_get.call_args_list[1].kwargs["params"] == {"per_page": 100, "page": 2}


@mock.patch("requests.get")
def test_list_org_repos_single_page(mock_get, fake_response):
    mock_get.return_value = fake_response(200, [{"name": "only"}])
    assert GitHubClient("tok").list_org_repos() == ["only"]
    mock_get.assert_called_once()


def _graphql_nodes():
    return [
        {"name": "Área", "options": [{"name": "Alertas"}, {"name": "Ingestão"}]},
        {"name": "Size", "options": [{"name": "S"}, {"name": "M"}]},
        {
            "name": "Status",
            "options": [{"name": "No status"}, {"name": "Todo"}, {"name": "In Progress"}, {"name": "Done"}],
        },
    ]


@mock.patch("requests.post")
def test_project_single_select_options(mock_post, fake_response):
    mock_post.return_value = fake_response(
        200, {"data": {"organization": {"projectV2": {"fields": {"nodes": _graphql_nodes()}}}}}
    )
    areas, sizes, statuses = GitHubClient("tok").project_single_select_options()
    assert areas == ["Alertas", "Ingestão"]
    assert sizes == ["S", "M"]
    assert statuses == ["No status", "Todo", "In Progress", "Done"]
    called_args, called_kwargs = mock_post.call_args
    assert called_args[0] == "https://api.github.com/graphql"
    assert "projectV2(number: 39)" in called_kwargs["json"]["query"]
    assert called_kwargs["headers"] == GITHUB_HEADERS


@mock.patch("requests.post")
def test_project_single_select_options_unavailable(mock_post, fake_response):
    mock_post.return_value = fake_response(403, {"message": "Resource not accessible by integration"})
    assert GitHubClient("tok").project_single_select_options() == ([], [], [])


@mock.patch("requests.post")
def test_project_single_select_options_graphql_error(mock_post, fake_response):
    # GraphQL responde 200 mesmo com erro de negócio (sem read:project)
    mock_post.return_value = fake_response(
        200, {"errors": [{"message": "Resource not accessible by integration", "type": "FORBIDDEN"}]}
    )
    assert GitHubClient("tok").project_single_select_options() == ([], [], [])


def test_fetch_github_options_without_token():
    with override_settings(GH_TOKEN=""):
        assert fetch_github_options() == {"repos": [], "areas": [], "sizes": [], "statuses": []}


@mock.patch("requests.post")
def test_project_field_resolves_ids(mock_post, fake_response):
    mock_post.return_value = fake_response(
        200,
        {
            "data": {
                "organization": {
                    "projectV2": {
                        "id": "PVT_proj",
                        "fields": {
                            "nodes": [
                                {"id": "f_area", "name": "Área", "options": [{"id": "o1", "name": "Alertas"}]},
                                {
                                    "id": "f_status",
                                    "name": "Status",
                                    "options": [
                                        {"id": "o_todo", "name": "🔖 To do"},
                                        {"id": "o_done", "name": "✅ Done"},
                                    ],
                                },
                            ]
                        },
                    }
                }
            }
        },
    )
    project_id, field_id, options = GitHubClient("tok").project_field()
    assert (project_id, field_id) == ("PVT_proj", "f_status")
    assert options == {"🔖 To do": "o_todo", "✅ Done": "o_done"}
    assert "fields(first: 100)" in mock_post.call_args.kwargs["json"]["query"]


@mock.patch("requests.post")
def test_project_field_missing_raises(mock_post, fake_response):
    mock_post.return_value = fake_response(
        200, {"data": {"organization": {"projectV2": {"id": "PVT_p", "fields": {"nodes": []}}}}}
    )
    with pytest.raises(GitHubAPIError):
        GitHubClient("tok").project_field()


@mock.patch("requests.post")
def test_add_project_item(mock_post, fake_response):
    mock_post.return_value = fake_response(200, {"data": {"addProjectV2ItemById": {"item": {"id": "PVTI_item"}}}})
    item_id = GitHubClient("tok").add_project_item("PVT_proj", "I_kw_issue")
    assert item_id == "PVTI_item"
    query = mock_post.call_args.kwargs["json"]["query"]
    assert "addProjectV2ItemById" in query
    assert 'projectId: "PVT_proj"' in query and 'contentId: "I_kw_issue"' in query


@mock.patch("requests.post")
def test_set_project_item_status(mock_post, fake_response):
    mock_post.return_value = fake_response(
        200, {"data": {"updateProjectV2ItemFieldValue": {"project": {"id": "PVT_proj"}}}}
    )
    GitHubClient("tok").set_project_item_status("PVT_proj", "PVTI_item", "f_status", "o_done")
    query = mock_post.call_args.kwargs["json"]["query"]
    assert "updateProjectV2ItemFieldValue" in query
    assert 'singleSelectOptionId: "o_done"' in query


@mock.patch.object(GitHubClient, "list_org_repos", return_value=["a-repo", "b-repo"])
@mock.patch.object(
    GitHubClient,
    "project_single_select_options",
    return_value=(["Área X"], ["M"], ["No status", "Todo", "In Progress", "Done"]),
)
def test_fetch_github_options_with_token(mock_repos, mock_ss):
    with override_settings(GH_TOKEN="tok"):
        assert fetch_github_options() == {
            "repos": ["a-repo", "b-repo"],
            "areas": ["Área X"],
            "sizes": ["M"],
            "statuses": ["No status", "Todo", "In Progress", "Done"],
        }
