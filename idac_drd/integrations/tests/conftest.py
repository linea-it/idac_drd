import pytest
import requests


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, raises=None):
        self.status_code = status_code
        self._json = json_data or {}
        self._raises = raises

    def json(self):
        return self._json

    def raise_for_status(self):
        if self._raises:
            raise self._raises
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} Error")


@pytest.fixture
def fake_response():
    return FakeResponse
