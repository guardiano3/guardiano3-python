# GuardianO3 Python SDK

> **Not published yet.** Version 0.1.0 is being prepared. `pip install guardiano3`
> works once it is on PyPI.

The official Python client for the [GuardianO3](https://guardiano3.com) API:
real-time fraud intelligence for phone calls. Send a transcript, an audio clip
or stream live audio, and get a risk decision back.

You need an API key from the developer console at
[guardiano3.com](https://guardiano3.com).

## Install

```bash
pip install guardiano3
pip install "guardiano3[live]"   # adds websockets, for LiveSession
```

Requires Python 3.10+.

## How this repository is laid out

| Directory | What it is |
|---|---|
| `src/guardiano3/` | **Hand-written**: the client, retries, idempotency, typed errors, pagination, live sessions |
| `src/guardiano3_generated/` | **Generated** from `openapi/v1.json` by `scripts/generate.sh`. Never edited by hand |
| `openapi/v1.json` | A copy of the GuardianO3 API contract, updated whenever the API changes |

Pull requests are welcome for the hand-written part; see
[CONTRIBUTING](https://github.com/guardiano3/.github/blob/main/CONTRIBUTING.md).
If generated code is wrong, open an issue: the fix belongs in the contract.

## A client

<!-- sample:python-client -->
```python
import os

from guardiano3 import Guardiano3

client = Guardiano3(api_key=os.environ["GO3_API_KEY"])
```

| Argument | Default | |
|---|---|---|
| `api_key` | `$GUARDIANO3_API_KEY` | A `go3_live_…` / `go3_test_…` key |
| `access_token` | — | A user access token, for personal-data endpoints |
| `base_url` | `$GUARDIANO3_BASE_URL`, else `https://api.guardiano3.com` | Set it only to reach a different environment |
| `timeout` | `30.0` | Seconds |
| `retry_policy` | `RetryPolicy()` | See below |

Pass one credential or the other. Both are sent as `Authorization: Bearer`, and
the API distinguishes them by the `go3_` prefix — there is nothing to configure
differently. If neither is given and `GUARDIANO3_API_KEY` is unset, the
constructor raises `ValueError` immediately rather than failing on the first
call.

Use it as a context manager, or call `close()`, so the connection pool is
released:

<!-- sample:python-context-manager -->
```python
import os

from guardiano3 import Guardiano3

with Guardiano3(api_key=os.environ["GO3_API_KEY"]) as client:
    who = client.api_keys.whoami_v1_whoami_get()
    print(who.actor_label, who.scopes)
```

## Calling operations

Operations are grouped by tag: `client.auth`, `client.sessions`,
`client.account`, `client.analysis`, `client.api_keys`, `client.policies`, `client.org`. Method names come from
the contract's `operationId`, which is why they are long
(`analyze_text_v1_analyze_text_post`) — they are generated, stable, and
unambiguous. The hand-written layer adds short forms only where they earn their
keep, such as `iter_history()`.

<!-- sample:python-analyze -->
```python
import os

from guardiano3 import Guardiano3

with Guardiano3(api_key=os.environ["GO3_API_KEY"]) as client:
    result = client.analysis.analyze_text_v1_analyze_text_post(
        text_analysis_request={"text": "Share the OTP to unblock your account."}
    )

print(result.risk_level.value, result.risk_score)  # high 78.5
```

An audio clip goes up as a file -- a path, raw bytes, or a `(filename, bytes)`
pair. WAV, MP3, FLAC, OGG, M4A and WebM are accepted, up to 120 seconds:

<!-- sample:python-analyze-audio -->
```python
import os

from guardiano3 import Guardiano3

with Guardiano3(api_key=os.environ["GO3_API_KEY"]) as client:
    with open("audio.m4a", "rb") as fh:
        result = client.analysis.analyze_audio_v1_analyze_audio_post(
            file=("audio.m4a", fh.read()), language="hi"
        )

print(result.risk_level.value, result.transcript)
```

`language` is optional; omit it and the language is detected from the
transcript. API keys are for the integration surface -- profile, stats and
key management (`client.account`, `client.api_keys` other than `whoami`)
need a signed-in user's `access_token` and refuse a key with `401`.

Models are Pydantic, so a bad value fails **locally**, before the request
leaves — an invalid value costs no round trip. Properties are snake_case
(`risk_score`); the wire format stays camelCase. That is the alias doing its
job, not drift.

**Enums are `str` subclasses**, so `result.risk_level == "high"` is true and
`json.dumps` produces `"high"`. Only `print()` and f-strings differ:
`str(RiskLevel.HIGH)` is `"RiskLevel.HIGH"`, so use `.value` when the string is
going somewhere a person or another system will read it. The TypeScript SDK has
no such wrinkle — its enums are plain string unions.

## Errors

<!-- sample:python-errors -->
```python
import os

from guardiano3 import (
    Guardiano3,
    NotFoundError,
    QuotaExceededError,
    RateLimitError,
    ValidationError,
)

with Guardiano3(api_key=os.environ["GO3_API_KEY"]) as client:
    try:
        client.sessions.get_session_v1_sessions_session_id_get(session_id="nope")
    except NotFoundError as exc:
        # Also raised when the row exists but belongs to someone else.
        print(exc.code, exc.status_code, exc.request_id)
    except QuotaExceededError:
        raise                       # do not retry: waiting will not help
    except RateLimitError as exc:
        print("retry after", exc.retry_after)
    except ValidationError as exc:
        for detail in exc.details:
            print(detail)
```

| Exception | Status |
|---|---|
| `AuthenticationError` | 401 |
| `PermissionError_` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` | 409 |
| `ValidationError` | 422 |
| `RateLimitError` | 429 |
| `QuotaExceededError` | 429 with `QUOTA_EXCEEDED` — a subclass, so `except RateLimitError` still catches it |
| `ServerError` | 5xx |
| `ConnectionError_` | the request never got an answer |

All inherit `APIError` (itself a `Guardiano3Error`) and carry `.code`,
`.status_code`, `.request_id`, `.details` and `.retry_after`.

**An unrecognised code falls back to the class for its HTTP status** rather than
raising something unhandleable. New error codes are added without a version
bump, so a client that crashed on one would make adding a code a breaking
change.

`request_id` is in `str(exc)`, not only on the attribute — if it lived only on
the attribute, nobody would paste it into a support ticket.

## Retries

Automatic, and narrow on purpose.

| | |
|---|---|
| Retried | 429, 502, 503, 504 |
| **Not** retried | 4xx other than 429, **500**, and any `QUOTA_EXCEEDED` |
| Attempts | 3 |
| Backoff | 0.5s, doubling, capped at 20s, ±25% jitter |
| `Retry-After` | Honoured when present — the server knows when its window resets |

500 is excluded deliberately: the API returns it for an unexpected fault, not a
transient one, and retrying turns one incident into a bigger one. Jitter is not
decoration — without it, every client that hit a limit at the same moment
retries at the same moment and re-creates the overload the limit existed to
prevent.

<!-- sample:python-retry-policy -->
```python
import os

from guardiano3 import Guardiano3, RetryPolicy

client = Guardiano3(
    api_key=os.environ["GO3_API_KEY"],
    retry_policy=RetryPolicy(max_attempts=5, initial_backoff=1.0, max_backoff=30.0),
)
```

`RetryPolicy(max_attempts=1)` disables retries.

## Idempotency

Every unsafe request carries an `Idempotency-Key`, generated **once per logical
call, outside the retry loop**. That ordering is the whole point: a key
generated per attempt would make each retry a fresh write, which is exactly
what idempotency keys exist to prevent.

To control the key yourself — to make a create idempotent across process
restarts, say — send your own header; the SDK does not overwrite one you set.

## Pagination

<!-- sample:python-pagination -->
```python
import os

from guardiano3 import Guardiano3

with Guardiano3(access_token=os.environ["GO3_ACCESS_TOKEN"]) as client:
    for session in client.iter_history(limit=50, max_items=500):
        print(session.id, session.risk_level)
```

Lazy: a page is fetched only once the previous one is consumed, so
`next(client.iter_history())` costs one request rather than walking your whole
history. `max_items` stops early. Cursors are never your problem.

For any other paginated endpoint, `iterate` takes the page function directly:

<!-- sample:python-iterate -->
```python
import os

from guardiano3 import Guardiano3, iterate

with Guardiano3(access_token=os.environ["GO3_ACCESS_TOKEN"]) as client:
    pages = client.sessions.list_history_v1_history_get
    for item in iterate(lambda cursor=None, limit=None: pages(cursor=cursor, limit=limit)):
        print(item.id)
```

## WebSocket / Live Sessions

`LiveSession` manages the two WebSocket channels for real-time session
analysis: binary audio uplink and typed JSON decision downlink. It is an
async context manager and an async iterator.

Requires the `live` extra: `pip install "guardiano3[live]"`.

<!-- sample:python-live -->
```python
import asyncio
import os

from guardiano3 import Guardiano3, LiveSession

async def main():
    with Guardiano3(api_key=os.environ["GO3_API_KEY"]) as client:
        # 1. Create a session via REST
        session = client.sessions.create_session_v1_sessions_post(
            session_create_request={
                "phoneNumber": "+91 98765 43210",
                "direction": "incoming",
            }
        )

        # 2. Open the live channels
        async with LiveSession(
            base_url="https://api.guardiano3.com",
            credential=os.environ["GO3_API_KEY"],
            session_id=session.id,
        ) as live:
            # 3. Send PCM audio (16-bit LE, 16kHz mono). In a real client this
            #    is a chunk off the microphone; here it comes from a file.
            with open("audio.raw", "rb") as fh:
                pcm_bytes = fh.read()
            await live.send_audio(pcm_bytes)

            # 4. Consume decisions as an async iterator
            async for frame in live:
                if frame.type == "ready":
                    print("Ready:", frame.session_id)
                elif frame.type == "decision":
                    print(frame.risk_level, frame.risk_score, frame.transcript)
                elif frame.type == "decisionUpdate":
                    print("Updated:", frame.risk_level, frame.verification_status)
                elif frame.type == "lagging":
                    print("Dropped chunks:", frame.dropped_chunks)
                elif frame.type == "error":
                    print("Error:", frame.error_code, frame.error_message)

asyncio.run(main())
```

| `frame.type` | Fields set | When |
|---|---|---|
| `ready` | `session_id` | Session authenticated, audio accepted |
| `decision` | `risk_level`, `risk_score`, `fraud_category`, `verification_status`, `transcript`, `explanation` | Scored chunk |
| `decisionUpdate` | same as `decision` | Final decision for a chunk first sent as `pending`; replace it in place |
| `lagging` | `dropped_chunks` | Audio arriving faster than transcription |
| `degraded` | `degraded_reason`, `unheard_seconds`, `total_unheard_seconds` | Part of the audio was not analysed; no decision covers it. Not fatal: do not read a quiet stream as a safe session |
| `error` | `error_code`, `error_message` | Fatal; server closes after sending |
| `ping` | — | Keep-alive |

Every frame also carries `raw` (the full parsed dict) and `session_id`.

Both channels authenticate by sending `{"token": "..."}` as the first text
frame. Audio is sent as raw bytes (PCM 16-bit LE, 16kHz mono). All
decision frames carry a `type` discriminator.

## Async

Not yet. The generated layer is urllib3-based and synchronous. Run calls in a
thread pool (`asyncio.to_thread`) if you need them off the event loop; a real
async client comes with the async generator, not before, because a fake one
that blocks the loop is worse than an honest synchronous one.

## Logging

The SDK logs nothing on its own. `X-Request-Id` is on every response and on
every `APIError`; log it next to your own request id and a failure becomes one
lookup rather than a correlation exercise.

Never log a key. `WhoAmIResponse.actor_label` and an `ApiKeyResponse.prefix`
identify a credential without revealing it.

## What it will never do

The SDK contains **no business logic and makes no authorization decisions**. It
is transport, serialisation, authentication, models, errors, pagination and
retries. Anything it decided, an attacker could decide differently with `curl`
— so the rules live on the server, and the SDK is a convenience rather than a
control.

## Licence

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).

The licence covers this SDK's source code. Using the GuardianO3 API requires an
API key and acceptance of the [Terms of Service](https://guardiano3.com/terms).

Security issues: see [SECURITY](https://github.com/guardiano3/.github/blob/main/SECURITY.md).
Never put API keys, session audio or transcripts in an issue.
