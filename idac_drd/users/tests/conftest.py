import pytest

from idac_drd.users.models import ExternalIdentity


@pytest.fixture
def external_identity(db):
    return ExternalIdentity.objects.create(
        email="alice@linea.org.br",
        name="Alice Silva",
        github_handle="alicegh",
        slack_id="U1234ALICE",
    )
