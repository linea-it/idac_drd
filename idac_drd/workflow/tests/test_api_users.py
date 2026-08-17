import pytest
from django.contrib.auth import get_user_model

from idac_drd.users.models import ExternalIdentity
from idac_drd.workflow.api.serializers import UserSerializer

User = get_user_model()


@pytest.mark.django_db
def test_user_serializer_name_falls_back_to_external_identity():
    ExternalIdentity.objects.create(email="alice@linea.org.br", name="Alice Silva")
    user = User.objects.create_user(username="alice", email="alice@linea.org.br", password="pass")
    assert UserSerializer(user).data["name"] == "Alice Silva"


@pytest.mark.django_db
def test_user_serializer_prefers_user_name():
    ExternalIdentity.objects.create(email="bob@linea.org.br", name="Bob do Slack")
    user = User.objects.create_user(username="bob", email="bob@linea.org.br", password="pass", name="Bob do Django")
    assert UserSerializer(user).data["name"] == "Bob do Django"


@pytest.mark.django_db
def test_user_serializer_empty_name_without_identity():
    user = User.objects.create_user(username="carol", email="carol@linea.org.br", password="pass")
    assert UserSerializer(user).data["name"] == ""
