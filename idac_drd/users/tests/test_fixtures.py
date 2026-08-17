import io

import pytest
from django.core.management import call_command

from idac_drd.users.models import ExternalIdentity


@pytest.mark.django_db
def test_loaddata_identities_populates_external_identities():
    call_command("loaddata", "identities", stdout=io.StringIO(), verbosity=0)
    rodrigo = ExternalIdentity.objects.get(email="rodrigo.boufleur@linea.org.br")
    assert rodrigo.github_handle == "rcboufleur"
    assert rodrigo.slack_id == "UARSZNZC7"
    assert rodrigo.name == "Rodrigo Boufleur"
    carlos = ExternalIdentity.objects.get(email="carlosadean@linea.org.br")
    assert carlos.github_handle == "carlosadean"
    assert carlos.slack_id == "U0E8BJ9EX"
    julia = ExternalIdentity.objects.get(email="julia@linea.org.br")
    assert julia.github_handle == "gschwend"
    luigi = ExternalIdentity.objects.get(slack_id="U06N6GZP4TT")
    assert luigi.email is None
    assert luigi.github_handle == "luigilcsilva"
    assert ExternalIdentity.objects.count() == 10
