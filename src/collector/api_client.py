"""HTTP client for the DB Timetables API (DB API Marketplace).

Responsibilities:
- authentication via the `DB-Client-Id` / `DB-Api-Key` headers (values never logged)
- client-side rate limiting: at most one call per `min_interval_s`
- retries with exponential backoff for 429 and 5xx, honouring `Retry-After`
- timeouts on every request
"""

from __future__ import annotations

import logging
import time
from urllib.parse import quote

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.config import API_MIN_INTERVAL_S, API_TIMEOUT_S, TIMETABLES_BASE_URL, ApiCredentials

logger = logging.getLogger(__name__)


class TimetablesClient:
    """Thin, rate-limited wrapper around the four Timetables endpoints.

    Methods return the raw XML text so the caller can archive it before parsing.
    `plan` returns None for a 404 (no timetable published for that hour).
    """

    def __init__(
        self,
        credentials: ApiCredentials,
        base_url: str = TIMETABLES_BASE_URL,
        min_interval_s: float = API_MIN_INTERVAL_S,
        timeout_s: float = API_TIMEOUT_S,
        max_retries: int = 4,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._last_call = 0.0
        self.n_calls = 0

        retry = Retry(
            total=max_retries,
            backoff_factor=2.0,  # 2 s, 4 s, 8 s, ...
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,  # we call raise_for_status ourselves for a clear error
        )
        self.session = requests.Session()
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {
                "DB-Client-Id": credentials.client_id,
                "DB-Api-Key": credentials.api_key,
                "Accept": "application/xml",
            }
        )

    def __repr__(self) -> str:  # never expose the session headers
        return f"TimetablesClient(base_url={self.base_url!r}, calls={self.n_calls})"

    # --- internals -----------------------------------------------------------------
    def _throttle(self) -> None:
        """Sleep so that consecutive calls are at least `min_interval_s` apart."""
        wait = self.min_interval_s - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, path: str, allow_404: bool = False) -> str | None:
        self._throttle()
        url = f"{self.base_url}/{path}"
        started = time.monotonic()
        response = self.session.get(url, timeout=self.timeout_s)
        self.n_calls += 1
        # Only the path is logged, never headers.
        logger.info("GET /%s -> %s (%.0f ms)", path, response.status_code, (time.monotonic() - started) * 1000)
        if allow_404 and response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise PermissionError(
                f"Timetables API returned {response.status_code}: check DB_CLIENT_ID / DB_API_KEY "
                "and that the application is subscribed to the Timetables API."
            )
        response.raise_for_status()
        response.encoding = "utf-8"
        return response.text

    # --- endpoints -------------------------------------------------------------------
    def station(self, pattern: str) -> str:
        """`/station/{pattern}`: stations matching a name, EVA number or DS100 code."""
        return self._get(f"station/{quote(pattern, safe='')}")  # type: ignore[return-value]

    def plan(self, eva: str, date_yymmdd: str, hour_hh: str) -> str | None:
        """`/plan/{eva}/{YYMMDD}/{HH}`: planned stops of one hour (no live data)."""
        return self._get(f"plan/{eva}/{date_yymmdd}/{hour_hh}", allow_404=True)

    def fchg(self, eva: str) -> str:
        """`/fchg/{eva}`: all currently known changes (delays, platforms, cancellations)."""
        return self._get(f"fchg/{eva}")  # type: ignore[return-value]

    def rchg(self, eva: str) -> str:
        """`/rchg/{eva}`: changes from the last 2 minutes only (not needed for snapshots)."""
        return self._get(f"rchg/{eva}")  # type: ignore[return-value]
