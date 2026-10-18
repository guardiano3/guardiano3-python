"""Construction defaults: what a caller gets without configuring anything."""

import pytest

from guardiano3 import Guardiano3


def _host(client: Guardiano3) -> str:
    return client._api_client.configuration.host


def test_the_default_base_url_is_production(monkeypatch):
    """`Guardiano3(api_key=...)` must reach the real API, not localhost."""
    monkeypatch.delenv("GUARDIANO3_BASE_URL", raising=False)
    with Guardiano3(api_key="go3_test_x") as client:
        assert _host(client) == "https://api.guardiano3.com"


def test_the_environment_overrides_the_default(monkeypatch):
    monkeypatch.setenv("GUARDIANO3_BASE_URL", "https://staging.example.com/")
    with Guardiano3(api_key="go3_test_x") as client:
        assert _host(client) == "https://staging.example.com"


def test_an_explicit_base_url_beats_the_environment(monkeypatch):
    monkeypatch.setenv("GUARDIANO3_BASE_URL", "https://staging.example.com")
    with Guardiano3(api_key="go3_test_x", base_url="http://localhost:8000") as client:
        assert _host(client) == "http://localhost:8000"


def test_no_credential_fails_at_construction(monkeypatch):
    monkeypatch.delenv("GUARDIANO3_API_KEY", raising=False)
    with pytest.raises(ValueError):
        Guardiano3()
