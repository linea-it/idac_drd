from config.middleware import prefix_location


def test_prefix_relative_root_and_admin():
    assert prefix_location("/", "/drd") == "/drd/"
    assert prefix_location("/admin/login/", "/drd") == "/drd/admin/login/"
    assert prefix_location("/drd/", "/drd") == "/drd/"
    assert prefix_location("/drd/admin/", "/drd") == "/drd/admin/"


def test_prefix_keeps_query_and_skips_idp():
    assert prefix_location("/admin/login/?next=/drd/", "/drd") == "/drd/admin/login/?next=/drd/"
    assert (
        prefix_location(
            "https://idp.example.org/sso",
            "/drd",
            allowed_hosts=["www.linea.org.br"],
        )
        == "https://idp.example.org/sso"
    )
    assert (
        prefix_location(
            "https://www.linea.org.br/admin/login/",
            "/drd",
            allowed_hosts=["www.linea.org.br"],
        )
        == "https://www.linea.org.br/drd/admin/login/"
    )
