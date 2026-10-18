"""The client a caller actually uses."""

from __future__ import annotations

import os
from typing import Any, Iterator, Optional

from guardiano3._transport import build_transport
from guardiano3.pagination import iterate
from guardiano3.retry import RetryPolicy

DEFAULT_BASE_URL = "https://api.guardiano3.com"
DEFAULT_TIMEOUT = 30.0


class Guardiano3:
    """A GuardianO3 API client.

        client = Guardiano3(api_key="go3_live_...")
        result = client.analysis.analyze_text_v1_analyze_text_post(
            text_analysis_request={"text": "share your otp"}
        )

    Authentication is one credential in one place: an API key or a user access
    token, both sent as `Authorization: Bearer`. The API tells them apart by the
    key prefix, so there is nothing for a caller to configure differently.

    **This client contains no business logic and makes no authorization
    decisions.** It is transport, serialisation, authentication, models, errors,
    pagination and retries. Anything it decided, an attacker could decide
    differently with curl -- so the rules live on the server.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        access_token: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        retry_policy: Optional[RetryPolicy] = None,
    ) -> None:
        # Imported here so `guardiano3.errors` and `guardiano3.retry` stay
        # importable without the generated package -- which is what lets the
        # policy layer be tested on its own.
        from guardiano3_generated import ApiClient, Configuration
        from guardiano3_generated.api.v1_account_api import V1AccountApi
        from guardiano3_generated.api.v1_analysis_api import V1AnalysisApi
        from guardiano3_generated.api.v1_api_keys_api import V1ApiKeysApi
        from guardiano3_generated.api.v1_auth_api import V1AuthApi
        from guardiano3_generated.api.v1_org_api import V1OrgApi
        from guardiano3_generated.api.v1_policies_api import V1PoliciesApi
        from guardiano3_generated.api.v1_sessions_api import V1SessionsApi

        credential = api_key or access_token or os.environ.get("GUARDIANO3_API_KEY")
        if not credential:
            raise ValueError(
                "No credential. Pass api_key=..., access_token=..., or set "
                "GUARDIANO3_API_KEY."
            )

        configuration = Configuration(
            host=(
                base_url or os.environ.get("GUARDIANO3_BASE_URL") or DEFAULT_BASE_URL
            ).rstrip("/"),
            access_token=credential,
        )
        configuration.retries = 0  # retries are ours; see guardiano3.retry

        transport_cls = build_transport(ApiClient)
        self._api_client = transport_cls(configuration, retry_policy=retry_policy)
        self._timeout = timeout

        self.auth = V1AuthApi(self._api_client)
        self.sessions = V1SessionsApi(self._api_client)
        self.account = V1AccountApi(self._api_client)
        self.analysis = V1AnalysisApi(self._api_client)
        self.api_keys = V1ApiKeysApi(self._api_client)
        self.policies = V1PoliciesApi(self._api_client)
        self.org = V1OrgApi(self._api_client)

    # -- convenience -------------------------------------------------------

    def iter_history(
        self, *, limit: Optional[int] = None, max_items: Optional[int] = None
    ) -> Iterator[Any]:
        """Every past session, newest first, across pages.

        Lazy: a page is fetched only when the previous one has been consumed.
        """

        def fetch(cursor=None, limit=None):
            return self.sessions.list_history_v1_history_get(cursor=cursor, limit=limit)

        return iterate(fetch, limit=limit, max_items=max_items)

    def close(self) -> None:
        close = getattr(self._api_client, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> "Guardiano3":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
