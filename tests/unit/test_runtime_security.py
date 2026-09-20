from __future__ import annotations

import pytest
from boa_oi.platform import auth_disabled, create_service_app


@pytest.mark.parametrize("environment", ["development", "local", "test"])
def test_auth_can_only_be_disabled_in_explicit_local_environments(monkeypatch, environment):
    monkeypatch.setenv("APP_ENV", environment)
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")

    assert auth_disabled() is True


def test_auth_disabled_is_rejected_outside_local_environments(monkeypatch):
    monkeypatch.setenv("APP_ENV", "pilot")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")

    with pytest.raises(RuntimeError, match="BOA_AUTH_DISABLED=true is forbidden"):
        auth_disabled()


def test_auth_disabled_is_rejected_when_environment_is_missing(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")

    with pytest.raises(RuntimeError, match="BOA_AUTH_DISABLED=true is forbidden"):
        auth_disabled()


def test_service_startup_rejects_unknown_environment_with_auth_disabled(monkeypatch):
    monkeypatch.setenv("APP_ENV", "unexpected")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")

    with pytest.raises(RuntimeError, match="BOA_AUTH_DISABLED=true is forbidden"):
        create_service_app("security-test", "Fail-closed proof", database=False)


def test_service_startup_fails_closed_when_auth_is_disabled_in_pilot(monkeypatch):
    monkeypatch.setenv("APP_ENV", "pilot")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "true")

    with pytest.raises(RuntimeError, match="BOA_AUTH_DISABLED=true is forbidden"):
        create_service_app("security-test", "Fail-closed proof", database=False)


def test_pilot_profile_keeps_oidc_authentication_enabled(monkeypatch):
    monkeypatch.setenv("APP_ENV", "pilot")
    monkeypatch.setenv("BOA_AUTH_DISABLED", "false")

    assert auth_disabled() is False
