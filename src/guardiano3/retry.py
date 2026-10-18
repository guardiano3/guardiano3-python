"""Retry policy.

Deliberately narrow about what is safe to repeat.

* **Only 429 and 502/503/504 are retried.** A 400 or a 404 will fail again;
  retrying it wastes the caller's time and the API's capacity. A 500 is not
  retried either -- the API returns 500 for an unexpected fault, not a transient
  one, and hammering it makes an incident worse.
* **`Retry-After` is honoured** when the API sends one. It knows when the window
  resets; guessing produces either a wasted wait or a second refusal.
* **Backoff is jittered.** Without jitter, every client that hit a limit at the
  same moment retries at the same moment, and the thundering herd re-creates the
  overload the limit existed to prevent.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

RETRYABLE_STATUSES = frozenset({429, 502, 503, 504})

#: A quota does not clear by waiting a few seconds, so an SDK must not sit in a
#: retry loop until midnight. Surfaced to the caller instead.
NON_RETRYABLE_CODES = frozenset({"QUOTA_EXCEEDED"})


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    initial_backoff: float = 0.5
    max_backoff: float = 20.0
    multiplier: float = 2.0
    #: Fraction of the computed delay to randomise, in each direction.
    jitter: float = 0.25

    def should_retry(
        self, *, attempt: int, status_code: Optional[int], code: Optional[str] = None
    ) -> bool:
        if attempt >= self.max_attempts:
            return False
        if code in NON_RETRYABLE_CODES:
            return False
        return status_code in RETRYABLE_STATUSES

    def backoff(
        self, attempt: int, *, retry_after: Optional[float] = None, rand=random.random
    ) -> float:
        """Seconds to wait before attempt number ``attempt`` (1-based)."""
        if retry_after is not None and retry_after >= 0:
            # The server's answer beats our guess.
            return min(float(retry_after), self.max_backoff)

        base = min(
            self.initial_backoff * (self.multiplier ** max(0, attempt - 1)),
            self.max_backoff,
        )
        spread = base * self.jitter
        return max(0.0, base + (rand() * 2 - 1) * spread)
