import io

import pytest
from django.core.management import call_command

from idac_drd.users.models import ExternalIdentity


@pytest.mark.django_db
def test_loaddata_identities_populates_external_identities():
    # valida o mecanismo do loaddata sem valores reais: contagem esperada e
    # campos essenciais preenchidos em todas as identidades
    call_command("loaddata", "identities", stdout=io.StringIO(), verbosity=0)
    assert ExternalIdentity.objects.count() == 10
    for identity in ExternalIdentity.objects.all():
        assert identity.email
        assert identity.name
        assert identity.slack_id
