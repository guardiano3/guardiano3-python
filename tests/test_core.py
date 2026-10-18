"""The Python SDK's hand-written core.

The generated layer is regenerated from the contract and is not tested here --
testing generated code tests the generator. What is tested is the half we wrote:
retries, idempotency, error mapping, pagination and request ids. That is where
the behaviour a caller depends on actually lives.
"""

import json

import pytest

from guardiano3 import errors
from guardiano3._transport import build_transport
from guardiano3.pagination import iterate
from guardiano3.retry import RetryPolicy

# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "code,expected",
    [
        ("INVALID_API_KEY", errors.AuthenticationError),
        ("TOKEN_REVOKED", errors.AuthenticationError),
        ("INSUFFICIENT_SCOPE", errors.PermissionError_),
        ("NOT_FOUND", errors.NotFoundError),
        ("IDEMPOTENCY_KEY_REUSED", errors.ConflictError),
        ("VALIDATION_ERROR", errors.ValidationError),
        ("RATE_LIMITED", errors.RateLimitError),
        ("QUOTA_EXCEEDED", errors.QuotaExceededError),
        ("INTERNAL_ERROR", errors.ServerError),
    ],
)
def test_published_codes_map_to_typed_exceptions(code, expected):
    raised = errors.from_response(400, {"error": {"code": code, "message": "x"}})
    assert isinstance(raised, expected)


def test_an_unknown_code_falls_back_to_the_status_class():
    """New codes are added without a version bump.

    A client that crashed on an unrecognised one would make adding an error code
    a breaking change.
    """
    raised = errors.from_response(
        403, {"error": {"code": "SOME_FUTURE_CODE", "message": "x"}}
    )
    assert isinstance(raised, errors.PermissionError_)
    assert raised.code == "SOME_FUTURE_CODE"


def test_a_quota_error_is_still_a_rate_limit_error():
    """`except RateLimitError` must keep catching it."""
    raised = errors.from_response(429, {"error": {"code": "QUOTA_EXCEEDED", "message": "x"}})
    assert isinstance(raised, errors.RateLimitError)
    assert isinstance(raised, errors.QuotaExceededError)


def test_the_request_id_is_in_the_string_form():
    """It is the value support asks for; on an attribute alone nobody pastes it."""
    raised = errors.from_response(
        404, {"error": {"code": "NOT_FOUND", "message": "No such session.", "requestId": "req_abc"}}
    )
    assert "req_abc" in str(raised)
    assert raised.request_id == "req_abc"


def test_the_request_id_falls_back_to_the_header():
    raised = errors.from_response(500, {}, {"x-request-id": "req_hdr"})
    assert raised.request_id == "req_hdr"


def test_a_legacy_detail_body_is_still_usable():
    """A legacy route or an intermediary proxy may answer instead of the API."""
    raised = errors.from_response(401, {"detail": "Not authenticated"})
    assert isinstance(raised, errors.AuthenticationError)
    assert raised.message == "Not authenticated"


def test_a_non_json_body_does_not_crash_the_client():
    raised = errors.from_response(502, None)
    assert isinstance(raised, errors.ServerError)
    assert "502" in raised.message


def test_retry_after_is_captured():
    raised = errors.from_response(
        429, {"error": {"code": "RATE_LIMITED", "message": "x"}}, {"Retry-After": "12"}
    )
    assert raised.retry_after == 12


def test_a_nonsense_retry_after_is_ignored_rather_than_crashing():
    raised = errors.from_response(429, {}, {"Retry-After": "soon"})
    assert raised.retry_after is None


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status", [429, 502, 503, 504])
def test_transient_failures_are_retried(status):
    assert RetryPolicy().should_retry(attempt=1, status_code=status) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 500])
def test_permanent_failures_are_not_retried(status):
    """Retrying a 404 wastes the caller's time; retrying a 500 makes an incident worse."""
    assert RetryPolicy().should_retry(attempt=1, status_code=status) is False


def test_a_quota_failure_is_not_retried():
    """Waiting seconds does not clear a daily allowance."""
    assert RetryPolicy().should_retry(attempt=1, status_code=429, code="QUOTA_EXCEEDED") is False


def test_attempts_are_bounded():
    policy = RetryPolicy(max_attempts=3)
    assert policy.should_retry(attempt=2, status_code=429) is True
    assert policy.should_retry(attempt=3, status_code=429) is False


def test_backoff_grows_and_is_capped():
    policy = RetryPolicy(initial_backoff=1.0, multiplier=2.0, max_backoff=5.0, jitter=0.0)
    assert [policy.backoff(a) for a in (1, 2, 3, 4, 5)] == [1.0, 2.0, 4.0, 5.0, 5.0]


def test_backoff_is_jittered():
    """Without jitter every client that hit the limit retries in the same instant."""
    policy = RetryPolicy(initial_backoff=1.0, jitter=0.25)
    delays = {round(policy.backoff(1), 6) for _ in range(50)}
    assert len(delays) > 1, "identical delays would re-create the overload"
    assert all(0.75 <= d <= 1.25 for d in delays)


def test_the_servers_retry_after_beats_our_guess():
    policy = RetryPolicy(initial_backoff=1.0, jitter=0.0)
    assert policy.backoff(1, retry_after=9) == 9.0


def test_retry_after_is_still_capped():
    """A hostile or broken Retry-After must not park the client for an hour."""
    policy = RetryPolicy(max_backoff=20.0)
    assert policy.backoff(1, retry_after=3600) == 20.0


# ---------------------------------------------------------------------------
# Transport: the properties that are easy to get wrong
# ---------------------------------------------------------------------------

class _Response:
    """Mirrors the generated RESTResponse, including its awkward part.

    `.data` stays None until `read()` is called. The first version of this stub
    populated `.data` eagerly, which made the unit tests pass while the real
    client turned every API error into a generic "status N" with no code. A test
    double that is kinder than the thing it stands for proves nothing.
    """

    def __init__(self, status, payload=None, headers=None):
        self.status = status
        self._payload = json.dumps(payload).encode() if payload is not None else b""
        self.data = None
        self._headers = headers or {}

    def read(self):
        if self.data is None:
            self.data = self._payload
        return self.data

    def getheaders(self):
        return self._headers


class _RecordingBase:
    """Stands in for the generated ApiClient."""

    def __init__(self, *args, **kwargs):
        self.calls = []
        self.responses = []

    def call_api(self, method, url, header_params=None, body=None, post_params=None,
                 _request_timeout=None):
        self.calls.append({"method": method, "url": url, "headers": dict(header_params or {})})
        return self.responses.pop(0)


def _client(responses, **kwargs):
    cls = build_transport(_RecordingBase)
    client = cls(**kwargs)
    client.responses = responses
    client._sleep = lambda _seconds: None  # no real waiting in tests
    return client


def test_the_idempotency_key_is_reused_across_retries():
    """The property this whole layer exists for.

    A key regenerated on retry defeats the mechanism entirely: the server sees
    two unrelated requests and does the work twice -- the exact failure
    idempotency keys prevent. Worse than not retrying, because it looks fine.
    """
    client = _client([
        _Response(429, {"error": {"code": "RATE_LIMITED", "message": "slow down"}}),
        _Response(429, {"error": {"code": "RATE_LIMITED", "message": "slow down"}}),
        _Response(201, {"id": "sess-1"}),
    ])
    client.call_api("POST", "/v1/sessions", {}, b"{}")

    keys = [c["headers"]["Idempotency-Key"] for c in client.calls]
    assert len(keys) == 3
    assert len(set(keys)) == 1, f"the key changed between retries: {keys}"


def test_the_request_id_is_also_stable_across_retries():
    client = _client([
        _Response(503, {"error": {"code": "SERVICE_UNAVAILABLE", "message": "x"}}),
        _Response(200, {"ok": True}),
    ])
    client.call_api("GET", "/v1/history", {})
    ids = [c["headers"]["X-Request-Id"] for c in client.calls]
    assert len(set(ids)) == 1


def test_a_caller_supplied_idempotency_key_is_respected():
    client = _client([_Response(201, {"id": "x"})])
    client.call_api("POST", "/v1/sessions", {"Idempotency-Key": "mine"}, b"{}")
    assert client.calls[0]["headers"]["Idempotency-Key"] == "mine"


def test_safe_methods_get_no_idempotency_key():
    client = _client([_Response(200, {})])
    client.call_api("GET", "/v1/history", {})
    assert "Idempotency-Key" not in client.calls[0]["headers"]


def test_audio_upload_gets_no_idempotency_key():
    """The API does not accept it there; sending it would be a 400."""
    client = _client([_Response(200, {})])
    client.call_api("POST", "http://host/v1/analyze/audio", {}, b"...")
    assert "Idempotency-Key" not in client.calls[0]["headers"]


def test_a_success_is_returned_untouched():
    client = _client([_Response(200, {"ok": True})])
    assert client.call_api("GET", "/v1/history", {}).status == 200
    assert len(client.calls) == 1


def test_a_permanent_failure_raises_immediately_without_retrying():
    client = _client([_Response(404, {"error": {"code": "NOT_FOUND", "message": "gone"}})])
    with pytest.raises(errors.NotFoundError) as exc:
        client.call_api("GET", "/v1/sessions/x", {})
    assert len(client.calls) == 1
    # Regression: the body must actually be parsed, not lost behind an unread
    # stream, or every error degrades to "status 404" with no code.
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.message == "gone"


def test_retries_are_exhausted_then_the_error_is_raised():
    client = _client(
        [_Response(503, {"error": {"code": "SERVICE_UNAVAILABLE", "message": "x"}})] * 3,
        retry_policy=RetryPolicy(max_attempts=3),
    )
    with pytest.raises(errors.ServerError):
        client.call_api("GET", "/v1/history", {})
    assert len(client.calls) == 3


def test_the_servers_retry_after_is_honoured_between_attempts():
    slept = []
    client = _client([
        _Response(429, {"error": {"code": "RATE_LIMITED", "message": "x"}}, {"Retry-After": "4"}),
        _Response(200, {}),
    ])
    client._sleep = slept.append
    client.call_api("GET", "/v1/history", {})
    assert slept == [4.0]


def test_a_quota_error_is_surfaced_rather_than_retried():
    client = _client([
        _Response(429, {"error": {"code": "QUOTA_EXCEEDED", "message": "exhausted"}},
                  {"Retry-After": "40000"}),
    ])
    with pytest.raises(errors.QuotaExceededError):
        client.call_api("POST", "/v1/analyze/text", {}, b"{}")
    assert len(client.calls) == 1, "an SDK must not sit in a loop until midnight"


def test_a_retried_audio_upload_still_carries_its_file():
    """Regression for R1 (2026-10-15 dev re-test).

    The generated rest.py deletes Content-Type from the headers dict it is
    handed for multipart uploads, and the transport used to hand it the same
    dict on every attempt. The first attempt was fine; every retry went out
    with no Content-Type and a 0-byte body, and the server answered 422.

    The recording stubs above copy the headers they receive, so they cannot see
    this -- the bug lives in the interaction with the real generated client.
    This test therefore drives the real client against a local HTTP server that
    answers 502 and then 200, and inspects what actually went over the wire.
    """
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from guardiano3.client import Guardiano3

    received = []
    statuses = [502, 200]

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - the stdlib's name
            length = int(self.headers.get("Content-Length") or 0)
            received.append({
                "content_type": self.headers.get("Content-Type") or "",
                "body": self.rfile.read(length),
                "request_id": self.headers.get("X-Request-Id"),
            })
            status = statuses.pop(0)
            payload = (
                {"error": {"code": "TRANSCRIPTION_FAILED", "message": "asr down"}}
                if status >= 400 else {}
            )
            raw = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args):  # keep pytest output clean
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        audio = b"RIFF\x24\x00\x00\x00WAVEfmt fake-audio-bytes"
        client = Guardiano3(
            api_key="go3_test_key",
            base_url=f"http://127.0.0.1:{server.server_port}",
            retry_policy=RetryPolicy(max_attempts=3),
        )
        client._api_client._sleep = lambda _seconds: None
        # The raw-response variant, so the test is about the request and not
        # about deserialising a full AnalysisResponse.
        response = client.analysis.analyze_audio_v1_analyze_audio_post_without_preload_content(
            file=("clip.wav", audio)
        )
        assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()

    assert len(received) == 2, "one 502, then one retry"
    first, retry = received
    for req in (first, retry):
        assert req["content_type"].startswith("multipart/form-data; boundary="), req
        assert audio in req["body"], "the file bytes must be in every attempt"
    assert retry["request_id"] == first["request_id"]


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class _Page:
    def __init__(self, items, next_cursor):
        self.items = items
        self.next_cursor = next_cursor
        self.has_more = bool(next_cursor)


def test_pages_are_flattened_in_order():
    pages = {None: _Page([1, 2], "c1"), "c1": _Page([3], None)}
    assert list(iterate(lambda cursor=None, limit=None: pages[cursor])) == [1, 2, 3]


def test_iteration_is_lazy():
    calls = []

    def fetch(cursor=None, limit=None):
        calls.append(cursor)
        return _Page([1, 2], "next")

    next(iterate(fetch))
    assert len(calls) == 1, "one page, not the whole history"


def test_max_items_stops_early():
    pages = {None: _Page([1, 2], "c1"), "c1": _Page([3, 4], "c2")}
    assert list(iterate(lambda cursor=None, limit=None: pages[cursor], max_items=3)) == [1, 2, 3]


def test_a_page_claiming_more_but_giving_no_cursor_terminates():
    """Otherwise a server bug becomes an infinite loop in every client."""

    class _Liar:
        items = [1]
        next_cursor = None
        has_more = True

    assert list(iterate(lambda cursor=None, limit=None: _Liar())) == [1]


def test_an_empty_first_page_yields_nothing():
    assert list(iterate(lambda cursor=None, limit=None: _Page([], None))) == []
