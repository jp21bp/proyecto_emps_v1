import html
import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup
from pydantic import ValidationError

from job_discovery.collectors.base import BaseCollector
from job_discovery.collectors.http import ATSHTTPClient
from job_discovery.collectors.models import (
    CollectionResult,
    CollectorJob,
)

logger = logging.getLogger(__name__)


class GreenhouseCollector(BaseCollector):
    """Collector for publicly accessible Greenhouse job boards."""

    platform = "GREENHOUSE"

    BASE_URL = "https://boards-api.greenhouse.io/v1/boards"

    def __init__(
        self,
        http_client: ATSHTTPClient | None = None,
        include_prospect_posts: bool = False,
    ) -> None:
        self.http = http_client or ATSHTTPClient()
        self._owns_http_client = http_client is None
        self.include_prospect_posts = include_prospect_posts

    def close(self) -> None:
        if self._owns_http_client:
            self.http.close()

    @staticmethod
    def _clean_optional_string(value: Any) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            value = value.strip()
            return value or None

        return str(value)

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if not isinstance(value, str) or not value.strip():
            return None

        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)

            return parsed

        except ValueError:
            return None

    @staticmethod
    def _extract_description_text(
        description_html: str | None,
    ) -> str | None:
        if not description_html:
            return None

        # Greenhouse documents HTML-encoded job content.
        decoded = html.unescape(description_html)

        soup = BeautifulSoup(decoded, "lxml")

        for element in soup(["script", "style"]):
            element.decompose()

        text = soup.get_text(separator="\n", strip=True)

        return text or None

    @staticmethod
    def _extract_names(items: Any) -> list[str]:
        if not isinstance(items, list):
            return []

        names = []

        for item in items:
            if isinstance(item, dict):
                name = item.get("name")

                if isinstance(name, str) and name.strip():
                    names.append(name.strip())

        return names

    def _normalize_job(
        self,
        payload: dict[str, Any],
    ) -> CollectorJob:

        external_id = payload.get("id")
        title = payload.get("title")

        if external_id is None:
            raise ValueError("Job is missing its external ID.")

        if not isinstance(title, str) or not title.strip():
            raise ValueError("Job is missing its title.")

        location_data = payload.get("location")

        location = None

        if isinstance(location_data, dict):
            location = self._clean_optional_string(location_data.get("name"))

        description_html = self._clean_optional_string(payload.get("content"))

        return CollectorJob(
            external_id=str(external_id),
            title=title.strip(),
            application_url=self._clean_optional_string(payload.get("absolute_url")),
            location=location,
            description_html=description_html,
            description_text=self._extract_description_text(description_html),
            departments=self._extract_names(payload.get("departments")),
            offices=self._extract_names(payload.get("offices")),
            publication_date=self._parse_datetime(payload.get("first_published")),
            updated_at=self._parse_datetime(payload.get("updated_at")),
            language=self._clean_optional_string(payload.get("language")),
            requisition_id=self._clean_optional_string(payload.get("requisition_id")),
            raw_payload=payload,
        )

    def collect(self, board_identifier: str) -> CollectionResult:
        board_identifier = board_identifier.strip()

        if not board_identifier:
            raise ValueError("Greenhouse board identifier cannot be empty.")

        encoded_identifier = quote(board_identifier, safe="")

        url = f"{self.BASE_URL}/{encoded_identifier}/jobs"

        payload = self.http.get_json(f"{url}?content=true")

        jobs_payload = payload.get("jobs")

        if not isinstance(jobs_payload, list):
            raise ValueError("Unexpected Greenhouse response: 'jobs' must be a list.")

        normalized_jobs: list[CollectorJob] = []
        warnings: list[str] = []
        skipped = 0

        for index, raw_job in enumerate(jobs_payload):
            if not isinstance(raw_job, dict):
                skipped += 1
                warnings.append(f"Listing at index {index} is not a JSON object.")
                continue

            # Greenhouse identifies prospect posts through a null
            # internal_job_id. These are not ordinary vacancies.
            if not self.include_prospect_posts and raw_job.get("internal_job_id") is None:
                skipped += 1
                continue

            try:
                job = self._normalize_job(raw_job)
                normalized_jobs.append(job)

            except (ValueError, ValidationError) as exc:
                skipped += 1

                warnings.append(f"Could not normalize listing at index {index}: {exc}")

                logger.warning(
                    "Skipping malformed Greenhouse listing on board %s, index %d: %s",
                    board_identifier,
                    index,
                    exc,
                )

        result = CollectionResult(
            platform=self.platform,
            board_identifier=board_identifier,
            jobs=normalized_jobs,
            collected_at=datetime.now(UTC),
            total_received=len(jobs_payload),
            total_valid=len(normalized_jobs),
            total_skipped=skipped,
            warnings=warnings,
        )

        logger.info(
            "Greenhouse collection completed: board=%s received=%d valid=%d skipped=%d",
            board_identifier,
            result.total_received,
            result.total_valid,
            result.total_skipped,
        )

        return result
