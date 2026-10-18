"""The transport layer: retries, idempotency, request ids, typed errors.

This is the hand-written half of the SDK. The generated code knows the shape of
every endpoint; it does not know how to behave when the network misbehaves, and
that behaviour is what separates a usable client from a wrapper around
`requests`.

One property here is load-bearing and easy to get wrong:

    **The Idempotency-Key is generated once per logical request and reused for
    every retry of it.**

A key regenerated on retry defeats the entire mechanism -- the server sees two
unrelated requests and does the work twice, which is the exact failure
idempotency keys exist to prevent. It is worse than not retrying at all, because
it looks like it is working.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from guardiano3 import errors
from guardiano3.retry import RetryPolicy

logger = logging.getLogger("guardiano3")

#: Methods that change state and are therefore worth an idempotency key.
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH"})

#: The API does not accept the header here -- fingerprinting a large upload
#: would double its memory cost.
_NO_IDEMPOTENCY_PATHS = ("/v1/analyze/audio",)


def _decode(raw: Any) -> Any:
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except ValueError:
            return None
    return raw


def build_transport(base_api_client_cls):
    """Build an ApiClient subclass wrapping the generated transport.

    Takes the class rather than importing it, so this module stays importable
    without the generated package present -- which is what lets the policy above
    be unit-tested on its own.
    """

    class RetryingApiClient(base_api_client_cls):  # type: ignore[misc, valid-type]
        def __init__(self, *args, retry_policy: Optional[RetryPolicy] = None, **kwargs):
            super().__init__(*args, **kwargs)
            self.retry_policy = retry_policy or RetryPolicy()
            self._sleep = time.sleep

        def call_api(
            self,
            method,
            url,
            header_params=None,
            body=None,
            post_params=None,
            _request_timeout=None,
        ):
            headers = dict(header_params or {})

            # Correlates this call with the server's logs. Sent even on the
            # first attempt so a failure is traceable without a second run.
            headers.setdefault("X-Request-Id", f"cli_{uuid.uuid4().hex}")

            # Generated ONCE, outside the retry loop, and deliberately so.
            if (
                method.upper() in _UNSAFE_METHODS
                and "Idempotency-Key" not in headers
                and not any(url.endswith(p) or p in url for p in _NO_IDEMPOTENCY_PATHS)
            ):
                headers["Idempotency-Key"] = str(uuid.uuid4())

            attempt = 0
            while True:
                attempt += 1
                # A fresh copy per attempt: the generated rest.py deletes
                # Content-Type from the dict it is given for multipart uploads
                # (so urllib3 can set the boundary). Handing it our own dict
                # meant every retry of an audio upload went out with no
                # Content-Type and therefore no body -- a 422 for a request
                # that was fine. The copy keeps the same Idempotency-Key and
                # X-Request-Id; only the generated code's mutation is lost.
                response = super().call_api(
                    method, url, dict(headers), body, post_params, _request_timeout
                )

                status = getattr(response, "status", None)
                if status is None or status < 400:
                    return response

                # The generated RESTResponse leaves `.data` as None until
                # read() is called -- reading the attribute directly always
                # yields None, which silently turned every API error into a
                # generic "status N" with no code. Caught by the dogfood test,
                # not by the unit tests, because the stub was more forgiving
                # than the real class.
                reader = getattr(response, "read", None)
                raw = reader() if callable(reader) else getattr(response, "data", None)
                payload = _decode(raw)
                response_headers = dict(getattr(response, "getheaders", dict)() or {})
                code = None
                if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
                    code = payload["error"].get("code")

                if self.retry_policy.should_retry(attempt=attempt, status_code=status, code=code):
                    retry_after = response_headers.get("Retry-After") or response_headers.get(
                        "retry-after"
                    )
                    delay = self.retry_policy.backoff(
                        attempt,
                        retry_after=float(retry_after) if retry_after else None,
                    )
                    logger.debug(
                        "Retrying %s %s after %.2fs (attempt %d, status %s)",
                        method, url, delay, attempt, status,
                    )
                    self._sleep(delay)
                    continue

                # Raised here rather than letting the generated code produce its
                # own ApiException, so every failure out of this SDK is one of
                # our documented types.
                raise errors.from_response(status, payload, response_headers)

    return RetryingApiClient
