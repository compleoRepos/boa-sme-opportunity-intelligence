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
