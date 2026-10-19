"""Construction defaults, and responses decoded by the real generated client."""

import json

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


# ---------------------------------------------------------------------------
# Sessions without a phone number
# ---------------------------------------------------------------------------
# phoneNumber and direction are optional. A client built from an older
# contract raised ValidationError on the first history page that held such a
# session, so these go through the real generated deserializer.


class _Raw:
    """What urllib3 hands the generated RESTResponse."""

    def __init__(self, status, payload):
        self.status = status
        self.reason = "OK"
        self.data = json.dumps(payload).encode()
        self.headers = {"content-type": "application/json"}


def _serve(client, monkeypatch, *responses):
    """Answer each request with the next (status, payload)."""
    from guardiano3_generated.rest import RESTResponse

    queue = list(responses)
    monkeypatch.setattr(
        client._api_client.rest_client,
        "request",
        lambda *args, **kwargs: RESTResponse(_Raw(*queue.pop(0))),
    )


def test_history_holds_sessions_without_a_phone_number(monkeypatch):
    page = {
        "items": [
            {"id": "s1", "timestamp": "2026-10-19T10:00:00Z", "riskLevel": "low"},
            {
                "id": "s2",
                "timestamp": "2026-10-19T09:00:00Z",
                "riskLevel": "high",
                "phoneNumber": None,
                "direction": None,
            },
            {
                "id": "s3",
                "timestamp": "2026-10-19T08:00:00Z",
                "riskLevel": "medium",
                "phoneNumber": "+91 98765 43210",
                "direction": "incoming",
            },
        ],
        "hasMore": False,
    }
    with Guardiano3(api_key="go3_test_x", base_url="http://localhost:8000") as client:
        _serve(client, monkeypatch, (200, page))
        sessions = list(client.iter_history())

    assert [s.id for s in sessions] == ["s1", "s2", "s3"]
    assert [s.phone_number for s in sessions] == [None, None, "+91 98765 43210"]
    assert [s.direction for s in sessions] == [None, None, "incoming"]


def test_a_session_can_be_created_and_read_without_a_phone_number(monkeypatch):
    from guardiano3_generated.models import SessionCreateRequest

    request = SessionCreateRequest()
    assert request.to_dict() == {}

    stored = {
        "id": "s1",
        "timestamp": "2026-10-19T10:00:00Z",
        "duration": 0,
        "riskLevel": "low",
        "riskScore": 0.0,
        "phoneNumber": None,
    }
    with Guardiano3(api_key="go3_test_x", base_url="http://localhost:8000") as client:
        _serve(client, monkeypatch, (201, {"id": "s1"}), (200, stored))
        created = client.sessions.create_session(request)
        session = client.sessions.get_session(created.id)

    assert session.id == "s1"
    assert session.phone_number is None and session.direction is None
