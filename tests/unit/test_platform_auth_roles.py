from __future__ import annotations

from boa_oi.platform import _principal_from_claims


def test_client_roles_are_read_only_from_configured_audience(monkeypatch):
    monkeypatch.setenv("OAUTH_AUDIENCE", "boa-sme-api")
    principal = _principal_from_claims(
        {
            "sub": "user-001",
            "azp": "boa-sme-spa",
            "realm_access": {"roles": ["RELATIONSHIP_MANAGER"]},
            "resource_access": {
                "boa-sme-api": {"roles": ["BRANCH_MANAGER"]},
                "unrelated-application": {"roles": ["ADMIN"]},
            },
            "scope": "openid profile",
        }
    )

    assert principal.roles == {"RELATIONSHIP_MANAGER", "BRANCH_MANAGER"}
    assert "ADMIN" not in principal.roles


def test_admin_role_from_unrelated_resource_access_is_ignored(monkeypatch):
    monkeypatch.setenv("OAUTH_AUDIENCE", "boa-sme-api")
    principal = _principal_from_claims(
        {
            "sub": "user-002",
            "azp": "other-spa",
            "resource_access": {"other-api": {"roles": ["ADMIN"]}},
            "scope": "openid",
        }
    )

    assert principal.roles == set()


def test_oidc_email_is_exposed_only_when_verified(monkeypatch):
    monkeypatch.setenv("OAUTH_AUDIENCE", "boa-sme-api")
    base = {
        "sub": "user-email",
        "azp": "boa-sme-spa",
        "email": "rm@bank.example",
    }

    unverified = _principal_from_claims({**base, "email_verified": False})
    verified = _principal_from_claims({**base, "email_verified": True})

    assert unverified.email is None
    assert unverified.email_verified is False
    assert verified.email == "rm@bank.example"
    assert verified.email_verified is True
