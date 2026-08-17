from unittest import mock

import pytest
import requests
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings

from idac_drd.integrations.glpi import GlpiAPIError, check_glpi, create_glpi_ticket

GLPI_CREDS = {
    "GLPI_API_URL": "https://glpi.example/apirest.php",
    "GLPI_USER": "svc-user",
    "GLPI_PASSWORD": "svc-pass",
    "GLPI_APP_TOKEN": "app-tok",
}


@mock.patch("requests.post")
def test_disabled_returns_none_without_calling_api(mock_post):
    with override_settings(GLPI_ENABLED=False, **GLPI_CREDS):
        assert create_glpi_ticket("name", "content") is None
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_enabled_without_credentials_raises(mock_post):
    with override_settings(GLPI_ENABLED=True, GLPI_API_URL="", GLPI_USER="", GLPI_PASSWORD="", GLPI_APP_TOKEN=""):
        with pytest.raises(ImproperlyConfigured) as exc_info:
            create_glpi_ticket("name", "content")
    assert "GLPI_API_URL" in str(exc_info.value)
    mock_post.assert_not_called()


@mock.patch("requests.post")
def test_create_ticket_success(mock_post, fake_response):
    mock_post.side_effect = [
        fake_response(200, {"session_token": "sesstok"}),
        fake_response(201, {"id": 42}),
    ]
    with override_settings(GLPI_ENABLED=True, **GLPI_CREDS):
        result = create_glpi_ticket("Ticket name", "Ticket content")

    assert result["id"] == 42
    assert len(mock_post.call_args_list) == 2

    init_call = mock_post.call_args_list[0]
    assert init_call.args[0] == "https://glpi.example/apirest.php/initSession"
    assert init_call.kwargs["headers"] == {"App-Token": "app-tok"}
    assert init_call.kwargs["data"] == {"login": "svc-user", "password": "svc-pass"}
    assert init_call.kwargs["timeout"] == 30

    ticket_call = mock_post.call_args_list[1]
    assert ticket_call.args[0] == "https://glpi.example/apirest.php/Ticket"
    assert ticket_call.kwargs["headers"] == {"App-Token": "app-tok", "Session-Token": "sesstok"}
    assert ticket_call.kwargs["json"] == {"name": "Ticket name", "content": "Ticket content", "type": 1}


@mock.patch("requests.post")
def test_create_ticket_http_error(mock_post, fake_response):
    mock_post.return_value = fake_response(
        400, {"0": "Session token missing"}, raises=requests.HTTPError("400 Client Error")
    )
    with override_settings(GLPI_ENABLED=True, **GLPI_CREDS):
        with pytest.raises(GlpiAPIError) as exc_info:
            create_glpi_ticket("name", "content")
    assert exc_info.value.status_code == 400


@mock.patch("requests.get")
@mock.patch("requests.post")
def test_check_glpi(mock_post, mock_get, fake_response):
    mock_post.return_value = fake_response(200, {"session_token": "sesstok"})
    mock_get.return_value = fake_response(200, {"myentities": [{"id": 1}]})
    with override_settings(GLPI_ENABLED=True, **GLPI_CREDS):
        assert check_glpi() is True
    mock_get.assert_called_once_with(
        "https://glpi.example/apirest.php/getMyEntities",
        headers={"App-Token": "app-tok", "Session-Token": "sesstok"},
        timeout=30,
    )


def test_check_glpi_disabled():
    with override_settings(GLPI_ENABLED=False):
        assert check_glpi() is False
