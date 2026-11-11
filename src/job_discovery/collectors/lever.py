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


class LeverCollector(BaseCollector):
    """Collector for publicly accessible Lever job boards."""

    platform = "LEVER"

    DEFAULT_API_BASE_URL = "https://api.lever.co/v0/postings"

    def __init__(
        self,
        http_client: ATSHTTPClient | None = None,
        api_base_url: str = DEFAULT_API_BASE_URL,
        page_size: int = 100,
        max_pages: int = 1000,
    ) -> None:
        if page_size <= 0:
            raise ValueError("page_size must be positive.")

        if max_pages <= 0:
            raise ValueError("max_pages must be positive.")

        self.http = http_client or ATSHTTPClient()
        self._owns_http_client = http_client is None

        self.api_base_url = api_base_url.rstrip("/")
        self.page_size = page_size
        self.max_pages = max_pages

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
    def _parse_timestamp(value: Any) -> datetime | None:
        """Convert Lever Unix timestamps in milliseconds to UTC."""

        if isinstance(value, bool) or value is None:
            return None

        try:
            timestamp = float(value) / 1000

            return datetime.fromtimestamp(
                timestamp,
                tz=UTC,
            )

        except (TypeError, ValueError, OverflowError, OSError):
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
    def _extract_categories(
        categories: Any,
    ) -> dict[str, Any]:
        if isinstance(categories, dict):
            return categories

        return {}

    @staticmethod
    def _extract_offices(
        categories: dict[str, Any],
    ) -> list[str]:
        locations = categories.get("allLocations")

        if isinstance(locations, list):
            return [
                value.strip() for value in locations if isinstance(value, str) and value.strip()
            ]

        location = categories.get("location")

        if isinstance(location, str) and location.strip():
            return [location.strip()]

        return []

    @staticmethod
    def _normalize_job(
        payload: dict[str, Any],
    ) -> CollectorJob:

        external_id = payload.get("id")
        title = payload.get("text")

        if not isinstance(external_id, str) or not external_id.strip():
            raise ValueError("Posting is missing its ID.")

        if not isinstance(title, str) or not title.strip():
            raise ValueError("Posting is missing its title.")

        categories = LeverCollector._extract_categories(payload.get("categories"))

        description_html = LeverCollector._clean_optional_string(payload.get("description"))

        description_text = LeverCollector._clean_optional_string(
            payload.get("descriptionPlain")
        ) or LeverCollector._extract_description_text(description_html)

        salary = payload.get("salaryRange")

        if not isinstance(salary, dict):
            salary = {}

        salary_min = salary.get("min")
        salary_max = salary.get("max")

        if isinstance(salary_min, bool) or not isinstance(salary_min, (int, float)):
            salary_min = None

        if isinstance(salary_max, bool) or not isinstance(salary_max, (int, float)):
            salary_max = None

        lists = payload.get("lists")

        if isinstance(lists, list):
            list_sections = []

            for section in lists:
                if isinstance(section, dict):
                    section_title = section.get("text")
                    section_content = section.get("content")

                    if isinstance(section_content, str):
                        list_sections.append(f"{section_title or ''}\n{section_content}")

            if list_sections:
                additional_text = "\n\n".join(list_sections)

                description_text = "\n\n".join(
                    value
                    for value in (
                        description_text,
                        additional_text,
                    )
                    if value
                )

        return CollectorJob(
            external_id=external_id.strip(),
            title=title.strip(),
            application_url=(
                LeverCollector._clean_optional_string(payload.get("applyUrl"))
                or LeverCollector._clean_optional_string(payload.get("hostedUrl"))
            ),
            location=LeverCollector._clean_optional_string(categories.get("location")),
            country_code=LeverCollector._clean_optional_string(payload.get("country")),
            description_html=description_html,
            description_text=description_text,
            departments=[
                value
                for value in (
                    LeverCollector._clean_optional_string(categories.get("team")),
                    LeverCollector._clean_optional_string(categories.get("department")),
                )
                if value is not None
            ],
            offices=LeverCollector._extract_offices(categories),
            employment_type=LeverCollector._clean_optional_string(categories.get("commitment")),
            workplace_type=LeverCollector._clean_optional_string(payload.get("workplaceType")),
            # Lever's createdAt is not necessarily the public
            # publication date.
            publication_date=None,
            source_created_at=LeverCollector._parse_timestamp(payload.get("createdAt")),
            updated_at=LeverCollector._parse_timestamp(payload.get("updatedAt")),
            salary_currency=LeverCollector._clean_optional_string(salary.get("currency")),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_interval=LeverCollector._clean_optional_string(salary.get("interval")),
            salary_description=(
                LeverCollector._clean_optional_string(payload.get("salaryDescriptionPlain"))
                or LeverCollector._clean_optional_string(payload.get("salaryDescription"))
            ),
            requisition_id=(LeverCollector._clean_optional_string(payload.get("reqCode"))),
            raw_payload=payload,
        )

    def _build_url(
        self,
        site: str,
        skip: int,
    ) -> str:
        encoded_site = quote(site, safe="")

        params = urlencode(
            {
                "mode": "json",
                "skip": skip,
                "limit": self.page_size,
            }
        )

        return f"{self.api_base_url}/{encoded_site}?{params}"

    def collect(self, board_identifier: str) -> CollectionResult:
        site = board_identifier.strip()

        if not site:
            raise ValueError("Lever site identifier cannot be empty.")

        normalized_jobs: list[CollectorJob] = []
        warnings: list[str] = []

        seen_ids: set[str] = set()

        total_received = 0
        skipped = 0

        for page_number in range(self.max_pages):
            skip = page_number * self.page_size

            url = self._build_url(site, skip)

            page = self.http.get_json_list(url)

            total_received += len(page)

            if not page:
                break

            for index, raw_job in enumerate(page):
                if not isinstance(raw_job, dict):
                    skipped += 1
                    warnings.append(
                        f"Page {page_number + 1}, index {index}: posting is not a JSON object."
                    )
                    continue

                external_id = raw_job.get("id")

                if isinstance(external_id, str):
                    if external_id in seen_ids:
                        skipped += 1
                        warnings.append(f"Duplicate Lever posting: {external_id}")
                        continue

                try:
                    job = self._normalize_job(raw_job)

                    if job.external_id in seen_ids:
                        skipped += 1
                        continue

                    seen_ids.add(job.external_id)
                    normalized_jobs.append(job)

                except (ValueError, ValidationError) as exc:
                    skipped += 1

                    warnings.append(f"Page {page_number + 1}, index {index}: {exc}")

                    logger.warning(
                        "Skipping malformed Lever posting on site %s: %s",
                        site,
                        exc,
                    )

            # A shorter page means there are no further pages.
            if len(page) < self.page_size:
                break

        else:
            warnings.append(f"Maximum pagination limit reached: {self.max_pages} pages.")

            logger.warning(
                "Lever pagination limit reached for site %s.",
                site,
            )

        result = CollectionResult(
            platform=self.platform,
            board_identifier=site,
            jobs=normalized_jobs,
            collected_at=datetime.now(UTC),
            total_received=total_received,
            total_valid=len(normalized_jobs),
            total_skipped=skipped,
            warnings=warnings,
        )

        logger.info(
            "Lever collection completed: site=%s received=%d valid=%d skipped=%d",
            site,
            result.total_received,
            result.total_valid,
            result.total_skipped,
        )

        return result
