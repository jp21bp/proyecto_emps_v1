# Script for only Greenhouse, needs update for Lever
import logging
import random
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class ATSHTTPError(Exception):
    """Raised when an ATS request fails permanently."""


class ATSHTTPClient:
    """Shared synchronous HTTP client for public ATS interfaces."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        min_request_interval: float = 1.0,
        backoff_factor: float = 2.0,
        max_backoff: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be positive.")

        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        if min_request_interval < 0:
            raise ValueError("min_request_interval cannot be negative.")

        if backoff_factor <= 0 or max_backoff <= 0:
            raise ValueError("Backoff values must be positive.")

        self.max_retries = max_retries
        self.min_request_interval = min_request_interval
        self.backoff_factor = backoff_factor
        self.max_backoff = max_backoff

        self._last_request_at = 0.0
        self._owns_client = client is None

        self.client = client or httpx.Client(
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={
                "User-Agent": "LocalJobDiscovery/0.1",
                "Accept": "application/json",
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> "ATSHTTPClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _wait_for_request_slot(self) -> None:
        elapsed = time.monotonic() - self._last_request_at

        remaining = self.min_request_interval - elapsed

        if remaining > 0:
            time.sleep(remaining)

        self._last_request_at = time.monotonic()

    @staticmethod
    def _retry_after(response: httpx.Response) -> float | None:
        value = response.headers.get("Retry-After")

        if not value:
            return None

        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)

                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)

                return max(
                    0.0,
                    (retry_at - datetime.now(UTC)).total_seconds(),
                )
            except (TypeError, ValueError, OverflowError):
                return None

    def _backoff(self, attempt: int, retry_after: float | None) -> None:
        exponential = min(
            self.backoff_factor * (2**attempt),
            self.max_backoff,
        )

        delay = max(exponential, retry_after or 0.0)

        # Positive jitter avoids synchronized retry bursts.
        delay += random.uniform(0.0, min(1.0, delay * 0.1))

        logger.warning("Retrying ATS request in %.2f seconds.", delay)

        time.sleep(delay)

    def get_json(self, url: str) -> dict[str, Any]:
        """Perform a GET request and return a validated JSON object."""

        for attempt in range(self.max_retries + 1):
            self._wait_for_request_slot()

            try:
                response = self.client.get(url)

            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise ATSHTTPError(f"Network request failed: {exc}") from exc

                self._backoff(attempt, None)
                continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    raise ATSHTTPError(
                        f"ATS returned HTTP {response.status_code} after {attempt + 1} attempts."
                    )

                self._backoff(
                    attempt,
                    self._retry_after(response),
                )
                continue

            if response.is_error:
                raise ATSHTTPError(
                    f"ATS returned HTTP {response.status_code}: {response.text[:500]}"
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise ATSHTTPError("ATS returned invalid JSON.") from exc

            if not isinstance(payload, dict):
                raise ATSHTTPError("Expected a JSON object from ATS endpoint.")

            return payload

        raise ATSHTTPError("ATS request failed unexpectedly.")
