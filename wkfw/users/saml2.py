import logging
from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group
from djangosaml2.backends import Saml2Backend

logger = logging.getLogger("djangosaml2")


class LineaSaml2Backend(Saml2Backend):
    def authenticate(
        self,
        request,
        session_info=None,
        attribute_mapping=None,
        create_unknown_user=True,
        assertion_info=None,
        **kwargs,
    ):
        logger.info("=====================================================")
        logger.info("authenticate()")
        logger.info(f"session_info: {session_info}")
        logger.info(f"attribute_mapping: {attribute_mapping}")
        logger.info(f"create_unknown_user: {create_unknown_user}")

        if session_info is None or attribute_mapping is None:
            logger.info("Session info or attribute mapping are None")
            return None

        if "ava" not in session_info:
            logger.error('"ava" key not found in session_info')
            return None

        idp_entityid = session_info["issuer"]
        attributes = self.clean_attributes(session_info["ava"], idp_entityid)

        list_idp_name = attributes.get("schacProjectMembership", None)
        idp_name = None
        if list_idp_name:
            idp_name = list_idp_name[0]

        logger.info(f"idp_name: {idp_name}")
        request.session["idp_name"] = idp_name

        if self.get_user_identifier(attributes) is None:
            logger.error("No user identifier found in attributes. Redirect to registration page.")
            # Define flag para redirecionamento para página de registro
            request.session["needs_registration"] = True

            return None

        user = super().authenticate(
            request,
            session_info,
            attribute_mapping,
            create_unknown_user,
            assertion_info,
            **kwargs,
        )

        if user is not None:
            # Tratamento dos grupos que o usuario pertence
            self.setup_groups(user, attributes)

            # Status do usuário (atributo SAML)
            user_status = attributes.get("schacUserStatus", None)
            request.session["user_status"] = user_status
            logger.info(f"User Status: {user_status}")
            if user_status is None:
                logger.error("User status not found in attributes.")
                return None

            if user_status in ["PendingApproval", "Pending"]:
                logger.info(f"User status is {user_status}. Redirecting to login error page.")
                return None

            return user
        else:
            logger.error("Authentication failed. User not found or not created.")
            return None

    def is_authorized(
        self,
        attributes: dict,
        attribute_mapping: dict,
        idp_entityid: str,
        assertion_info: dict,
        **kwargs,
    ) -> bool:
        """Permite política de autorização customizada com base nos atributos SAML."""
        logger.info("is_authorized()")

        # Estamos considerando que todos os usuarios terão cadastro no LIneA mesmo os de outras instituições.
        # O SATOSA do linea sempre vai retornar o uid do usuario, um status e o member que são os grupos
        # que o usuario pertence.
        # Se o usuario não tiver uid será redirecionado para a tela de cadastro.
        # O status será utilizado para dar o feedback correto, cadastro necessário ou em andamento.
        user_lookup_value = self.get_user_identifier(attributes)

        logger.info(f"User Lookup Value: {user_lookup_value}")
        if user_lookup_value in [None, "None", ""]:
            logger.error("No user uid identifier.")
            return False

        # Usuario com uid pode prosseguir com a autenticação
        return True

    def _extract_user_identifier_params(
        self, session_info: dict, attributes: dict, attribute_mapping: dict
    ) -> tuple[str, Any | None]:
        """Retorna o atributo usado na busca do usuário e o valor correspondente.

        O valor pode ser o name_id ou outro atributo SAML da requisição.
        """
        logger.info("_extract_user_identifier_params()")

        # Chave de busca
        user_lookup_key = "username"

        # Valor de busca
        try:
            user_lookup_value = self.get_user_identifier(attributes)

            logger.info(f"User Lookup Key: {user_lookup_key} Value: {user_lookup_value}")
            if user_lookup_value in [None, "None", ""]:
                logger.error("No identifier to search user.")
                return user_lookup_key, None

            return user_lookup_key, user_lookup_value

        except Exception as e:
            logger.error("Failed to extract user identifier.")
            logger.error(e)
            return user_lookup_key, None

    def get_user_identifier(self, attributes: dict) -> Any:
        """Retorna o identificador de usuário usado na autenticação."""
        # Chave de busca
        user_lookup_key = "uid"

        try:
            # Valor de busca
            user_lookup_value = attributes.get(user_lookup_key, None)

            if user_lookup_value and isinstance(user_lookup_value, list):
                user_lookup_value = user_lookup_value[0]
            else:
                user_lookup_value = None

        except Exception as e:
            logger.error("Failed to extract user identifier uid.")
            logger.error(e)
            return None

        if user_lookup_value in [None, "None", ""]:
            logger.error("No identifier uid to search user.")
            return None

        return self.clean_user_main_attribute(user_lookup_value)

    def clean_user_main_attribute(self, main_attribute: Any) -> Any:
        """Normaliza o valor que identifica o usuário. Por padrão só substitui '.' por '_'."""
        main_attribute = main_attribute.replace(".", "_")
        return main_attribute

    def user_can_authenticate(self, user) -> bool:
        """Rejeita usuários com is_active=False. Modelos de usuário sem esse atributo são aceitos."""
        is_active = getattr(user, "is_active", None)
        return is_active or is_active is None

    def save_user(self, user, *args, **kwargs):
        logger.info(f"save_user() user: {user}")
        user = super().save_user(user, *args, **kwargs)
        return user

    def setup_groups(self, user, attributes: dict):
        logger.info("Setup User Groups")

        # Grupo saml2 para marcar login via djangosaml2
        groups = ["saml2"]

        # Grupos internos que não serão removidos do usuário
        internal_groups = getattr(settings, "INTERNAL_GROUPS", [])

        # Recupera os grupos do usuário (atributo member)
        try:
            for group in attributes.get("member", []):
                groups.append(group)
        except Exception as e:
            logger.error(f"Failed on retrieve groups. Error: {e}")

        # Remove o usuário dos grupos que não estão na lista SAML (exceto internos)
        for group in user.groups.all():
            if group.name not in groups and group.name not in internal_groups:
                user.groups.remove(group)
                logger.info(f"User has been removed from the group {group.name}")

        # Adiciona o usuário a todos os grupos indicados no SAML
        for name in groups:
            group, _created = Group.objects.get_or_create(name=name)
            user.groups.add(group)

        logger.info(f"User has been added to the following groups: {groups}")

        return user
