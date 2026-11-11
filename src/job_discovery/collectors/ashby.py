import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote, urlencode

from bs4 import BeautifulSoup
from pydantic import ValidationError

from job_discovery.collectors.base import BaseCollector
from job_discovery.collectors.http import ATSHTTPClient
from job_discovery.collectors.models import (
    CollectionResult,
    CollectorJob,
)

logger = logging.getLogger(__name__)


class AshbyCollector(BaseCollector):
    """Collector for publicly accessible Ashby job boards."""

    platform = "ASHBY"

    DEFAULT_API_BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"

    def __init__(
        self,
        http_client: ATSHTTPClient | None = None,
        api_base_url: str = DEFAULT_API_BASE_URL,
        include_unlisted: bool = False,
        include_compensation: bool = True,
    ) -> None:
        self.http = http_client or ATSHTTPClient()
        self._owns_http_client = http_client is None

        self.api_base_url = api_base_url.rstrip("/")
        self.include_unlisted = include_unlisted
        self.include_compensation = include_compensation

    def close(self) -> None:
        if self._owns_http_client:
            self.http.close()

    @staticmethod
    def _clean_optional_string(value: Any) -> str | None:
        if isinstance(value, str):
            value = value.strip()
            return value or None

        if value is None:
            return None

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

        soup = BeautifulSoup(
            description_html,
            "lxml",
        )

        for element in soup(["script", "style"]):
            element.decompose()

        text = soup.get_text(
            separator="\n",
            strip=True,
        )

        return text or None

    @staticmethod
    def _extract_address_country(
        address: Any,
    ) -> str | None:
        if not isinstance(address, dict):
            return None

        country = address.get("addressCountry")

        return AshbyCollector._clean_optional_string(country)

    @staticmethod
    def _extract_primary_country(
        payload: dict[str, Any],
    ) -> str | None:
        address = payload.get("address")

        if not isinstance(address, dict):
            return None

        postal_address = address.get("postalAddress")

        return AshbyCollector._extract_address_country(postal_address)

    @staticmethod
    def _extract_secondary_locations(
        locations: Any,
    ) -> list[str]:
        if not isinstance(locations, list):
            return []

        result = []

        for item in locations:
            if not isinstance(item, dict):
                continue

            location = AshbyCollector._clean_optional_string(item.get("location"))

            if location:
                result.append(location)

        return result

    @staticmethod
    def _extract_salary(
        compensation: Any,
    ) -> dict[str, Any]:
        """Extract the first published salary component.

        Compensation can contain multiple tiers and components.
        We preserve the complete original structure in raw_payload.
        """

        result: dict[str, Any] = {
            "currency": None,
            "min": None,
            "max": None,
            "interval": None,
            "description": None,
        }

        if not isinstance(compensation, dict):
            return result

        result["description"] = AshbyCollector._clean_optional_string(
            compensation.get("compensationTierSummary")
        ) or AshbyCollector._clean_optional_string(
            compensation.get("scrapeableCompensationSalarySummary")
        )

        components = compensation.get("summaryComponents")

        if not isinstance(components, list):
            return result

        salary_components = [
            component
            for component in components
            if (isinstance(component, dict) and component.get("compensationType") == "Salary")
        ]

        if not salary_components:
            return result

        salary = salary_components[0]

        minimum = salary.get("minValue")
        maximum = salary.get("maxValue")

        if isinstance(minimum, (int, float)) and not isinstance(minimum, bool):
            result["min"] = minimum

        if isinstance(maximum, (int, float)) and not isinstance(maximum, bool):
            result["max"] = maximum

        result["currency"] = AshbyCollector._clean_optional_string(salary.get("currencyCode"))

        result["interval"] = AshbyCollector._clean_optional_string(salary.get("interval"))

        return result

    @staticmethod
    def _extract_department_names(
        payload: dict[str, Any],
    ) -> list[str]:
        result = []

        for field in ("department", "team"):
            value = AshbyCollector._clean_optional_string(payload.get(field))

            if value and value not in result:
                result.append(value)

        return result

    @staticmethod
    def _normalize_job(
        payload: dict[str, Any],
    ) -> CollectorJob:

        title = AshbyCollector._clean_optional_string(payload.get("title"))

        if not title:
            raise ValueError("Posting is missing its title.")

        # The documented public API does not expose a conventional
        # external posting ID. Use its canonical job URL instead.
        job_url = AshbyCollector._clean_optional_string(payload.get("jobUrl"))

        application_url = AshbyCollector._clean_optional_string(payload.get("applyUrl"))

        external_id = job_url or application_url

        if not external_id:
            raise ValueError("Posting is missing both jobUrl and applyUrl.")

        description_html = AshbyCollector._clean_optional_string(payload.get("descriptionHtml"))

        description_text = AshbyCollector._clean_optional_string(
            payload.get("descriptionPlain")
        ) or AshbyCollector._extract_description_text(description_html)

        workplace_type = AshbyCollector._clean_optional_string(payload.get("workplaceType"))

        is_remote = payload.get("isRemote")

        if not isinstance(is_remote, bool):
            is_remote = None

        compensation = AshbyCollector._extract_salary(payload.get("compensation"))

        primary_location = AshbyCollector._clean_optional_string(payload.get("location"))

        return CollectorJob(
            external_id=external_id,
            title=title,
            application_url=application_url or job_url,
            location=primary_location,
            country=AshbyCollector._extract_primary_country(payload),
            description_html=description_html,
            description_text=description_text,
            departments=(AshbyCollector._extract_department_names(payload)),
            offices=(
                AshbyCollector._extract_secondary_locations(payload.get("secondaryLocations"))
            ),
            employment_type=(AshbyCollector._clean_optional_string(payload.get("employmentType"))),
            workplace_type=workplace_type,
            is_remote=is_remote,
            publication_date=AshbyCollector._parse_datetime(payload.get("publishedAt")),
            updated_at=AshbyCollector._parse_datetime(payload.get("updatedAt")),
            salary_currency=compensation["currency"],
            salary_min=compensation["min"],
            salary_max=compensation["max"],
            salary_interval=compensation["interval"],
            salary_description=compensation["description"],
            raw_payload=payload,
        )

    def _build_url(self, board_identifier: str) -> str:
        encoded_identifier = quote(
            board_identifier,
            safe="",
        )

        params = urlencode({"includeCompensation": str(self.include_compensation).lower()})

        return f"{self.api_base_url}/{encoded_identifier}?{params}"

    def collect(self, board_identifier: str) -> CollectionResult:
        board = board_identifier.strip()

        if not board:
            raise ValueError("Ashby board identifier cannot be empty.")

        url = self._build_url(board)
        print('Ashby URL', url)

        payload = self.http.get_json(url)

        jobs_payload = payload.get("jobs")

        if not isinstance(jobs_payload, list):
            raise ValueError("Unexpected Ashby response: 'jobs' must be a list.")

        normalized_jobs: list[CollectorJob] = []
        warnings: list[str] = []

        skipped = 0
        seen_ids: set[str] = set()

        for index, raw_job in enumerate(jobs_payload):
            if not isinstance(raw_job, dict):
                skipped += 1

                warnings.append(f"Listing at index {index} is not a JSON object.")

                continue

            if not self.include_unlisted and raw_job.get("isListed") is False:
                skipped += 1
                continue

            try:
                job = self._normalize_job(raw_job)

                if job.external_id in seen_ids:
                    skipped += 1
                    warnings.append(f"Duplicate Ashby posting: {job.external_id}")
                    continue

                seen_ids.add(job.external_id)
                normalized_jobs.append(job)

            except (ValueError, ValidationError) as exc:
                skipped += 1

                warnings.append(f"Could not normalize listing at index {index}: {exc}")

                logger.warning(
                    "Skipping malformed Ashby listing on board %s, index %d: %s",
                    board,
                    index,
                    exc,
                )

        result = CollectionResult(
            platform=self.platform,
            board_identifier=board,
            jobs=normalized_jobs,
            collected_at=datetime.now(UTC),
            total_received=len(jobs_payload),
            total_valid=len(normalized_jobs),
            total_skipped=skipped,
            warnings=warnings,
        )

        logger.info(
            "Ashby collection completed: board=%s received=%d valid=%d skipped=%d",
            board,
            result.total_received,
            result.total_valid,
            result.total_skipped,
        )

        return result
