"""Typed exceptions, mapped from the API's error codes.

The API publishes a stable `error.code` for every failure (see the error
reference in the API documentation). Mapping it to a class is what lets callers write
`except RateLimitError:` instead of inspecting status integers.

Two rules from the contract shape this module:

* **Unknown codes must not break the client.** New codes are added without a
  version bump, so an unrecognised one falls back to the class for its HTTP
  status. A client that crashed on a new error code would make adding one a
  breaking change.
* **`requestId` belongs in the string form.** It is the one value support needs,
  and if it only lives on an attribute nobody will paste it into the report.
"""

from __future__ import annotations

from typing import Any, Optional


class Guardiano3Error(Exception):
    """Base class for everything this SDK raises."""


class APIError(Guardiano3Error):
    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        details: Optional[list] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.details = details or []
        self.retry_after = retry_after

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.append(f"[{self.code}]")
        # Deliberately in the string form: this is the value support asks for.
        if self.request_id:
            parts.append(f"(request {self.request_id})")
        return " ".join(parts)


class AuthenticationError(APIError):
    """401. The credential is missing, invalid, expired or revoked."""


class PermissionError_(APIError):
    """403. Authenticated, but not allowed -- role, scope or environment."""


class NotFoundError(APIError):
    """404. It does not exist, or it is not yours. The API does not distinguish."""


class ConflictError(APIError):
    """409."""


class ValidationError(APIError):
    """400/422. `details` carries the offending fields."""


class RateLimitError(APIError):
    """429 RATE_LIMITED. Retrying after `retry_after` will work."""


class QuotaExceededError(RateLimitError):
    """429 QUOTA_EXCEEDED.

    A subclass of RateLimitError so `except RateLimitError` still catches it,
    but distinct because waiting a few seconds does *not* help -- the allowance
    resets on a schedule, and an SDK should not spin.
    """


class ServerError(APIError):
    """5xx."""


class ConnectionError_(Guardiano3Error):
    """The request never reached the API."""


_BY_CODE: dict[str, type[APIError]] = {
    "UNAUTHENTICATED": AuthenticationError,
    "INVALID_CREDENTIALS": AuthenticationError,
    "INVALID_TOKEN": AuthenticationError,
    "TOKEN_REVOKED": AuthenticationError,
    "INVALID_REFRESH_TOKEN": AuthenticationError,
    "REFRESH_TOKEN_REUSED": AuthenticationError,
    "INVALID_API_KEY": AuthenticationError,
    "REAUTHENTICATION_REQUIRED": AuthenticationError,
    "MFA_REQUIRED": AuthenticationError,
    "FORBIDDEN": PermissionError_,
    "INSUFFICIENT_SCOPE": PermissionError_,
    "EMAIL_NOT_VERIFIED": PermissionError_,
    "ACCOUNT_SUSPENDED": PermissionError_,
    "WRONG_ENVIRONMENT": PermissionError_,
    "NOT_FOUND": NotFoundError,
    "ALREADY_EXISTS": ConflictError,
    "CONFLICT": ConflictError,
    "IDEMPOTENCY_KEY_REUSED": ConflictError,
    "VALIDATION_ERROR": ValidationError,
    "INVALID_REQUEST": ValidationError,
    "PASSWORD_POLICY_VIOLATION": ValidationError,
    "BREACHED_PASSWORD": ValidationError,
    "UNSUPPORTED_MEDIA_TYPE": ValidationError,
    "PAYLOAD_TOO_LARGE": ValidationError,
    "RATE_LIMITED": RateLimitError,
    "QUOTA_EXCEEDED": QuotaExceededError,
    "CONCURRENCY_LIMIT": RateLimitError,
    "INTERNAL_ERROR": ServerError,
    "SERVICE_UNAVAILABLE": ServerError,
    "UPSTREAM_ERROR": ServerError,
    "UPSTREAM_TIMEOUT": ServerError,
    "NOT_CONFIGURED": ServerError,
}

_BY_STATUS: dict[int, type[APIError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionError_,
    404: NotFoundError,
    409: ConflictError,
    413: ValidationError,
    415: ValidationError,
    422: ValidationError,
    429: RateLimitError,
}


def error_class(status_code: int, code: Optional[str]) -> type[APIError]:
    """The exception class for a failure.

    Code first, status as the fallback -- so a code this SDK version has never
    heard of still lands somewhere sensible instead of raising a bare error.
    """
    if code and code in _BY_CODE:
        return _BY_CODE[code]
    if status_code in _BY_STATUS:
        return _BY_STATUS[status_code]
    return ServerError if status_code >= 500 else APIError


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def from_response(status_code: int, body: Any, headers: Optional[dict] = None) -> APIError:
    """Build a typed exception from an API error response."""
    headers = headers or {}
    envelope = (body or {}).get("error") if isinstance(body, dict) else None

    if isinstance(envelope, dict):
        code = envelope.get("code")
        message = envelope.get("message") or "Request failed."
        request_id = envelope.get("requestId")
        details = envelope.get("details")
    else:
        # Legacy routes, or a proxy that replied instead of the API. Salvage
        # what we can rather than pretending the response was well-formed.
        code = None
        message = (
            body.get("detail") if isinstance(body, dict) and isinstance(body.get("detail"), str)
            else f"Request failed with status {status_code}."
        )
        request_id = None
        details = None

    request_id = request_id or headers.get("x-request-id") or headers.get("X-Request-Id")

    return error_class(status_code, code)(
        message,
        status_code=status_code,
        code=code,
        request_id=request_id,
        details=details,
        retry_after=_as_int(headers.get("retry-after") or headers.get("Retry-After")),
    )
