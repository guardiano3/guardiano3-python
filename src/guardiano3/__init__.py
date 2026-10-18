"""GuardianO3 Python SDK.

Generated models and operations from the published OpenAPI contract
(`openapi/v1.json`), over a hand-written transport that adds retries with
jitter, idempotency keys, request-id propagation, cursor pagination and typed
errors.

    from guardiano3 import Guardiano3, RateLimitError

    with Guardiano3(api_key="go3_live_...") as client:
        try:
            for session in client.iter_history(limit=50):
                print(session.id, session.risk_level)
        except RateLimitError as exc:
            print("slow down", exc.retry_after, exc.request_id)

Never edit `guardiano3_generated/` -- it is regenerated from the contract by
`scripts/generate.sh`.
"""

from guardiano3.client import Guardiano3
from guardiano3.errors import (
    APIError,
    AuthenticationError,
    ConflictError,
    ConnectionError_,
    Guardiano3Error,
    NotFoundError,
    PermissionError_,
    QuotaExceededError,
    RateLimitError,
    ServerError,
    ValidationError,
)
from guardiano3.live import LiveFrame, LiveSession
from guardiano3.pagination import iterate
from guardiano3.retry import RetryPolicy

__version__ = "0.1.0"

__all__ = [
    "Guardiano3",
    "LiveSession",
    "LiveFrame",
    "RetryPolicy",
    "iterate",
    "Guardiano3Error",
    "APIError",
    "AuthenticationError",
    "PermissionError_",
    "NotFoundError",
    "ConflictError",
    "ValidationError",
    "RateLimitError",
    "QuotaExceededError",
    "ServerError",
    "ConnectionError_",
    "__version__",
]
