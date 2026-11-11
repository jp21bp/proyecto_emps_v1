import json
from pathlib import Path

import httpx
import pytest

from job_discovery.collectors.ashby import AshbyCollector
from job_discovery.collectors.http import ATSHTTPClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "ashby_jobs.json"


@pytest.fixture
def ashby_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def create_collector(
    handler,
    include_unlisted: bool = False,
) -> AshbyCollector:

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http_client = ATSHTTPClient(
        client=client,
        max_retries=0,
        min_request_interval=0,
    )

    return AshbyCollector(
        http_client=http_client,
        include_unlisted=include_unlisted,
    )


def test_collect_jobs(ashby_payload: dict) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"

        assert request.url.path == ("/posting-api/job-board/example-company")

        assert request.url.params["includeCompensation"] == "true"

        return httpx.Response(
            200,
            json=ashby_payload,
        )

    collector = create_collector(handler)

    result = collector.collect("example-company")

    assert result.platform == "ASHBY"
    assert result.board_identifier == "example-company"

    assert result.total_received == 4
    assert result.total_valid == 3
    assert result.total_skipped == 1

    assert len(result.jobs) == 3

    job = result.jobs[0]

    assert job.external_id == ("https://jobs.ashbyhq.com/example-company/job-001")

    assert job.title == "Junior Data Analyst"

    assert job.location == "Remote - Americas"

    assert job.country == "Colombia"

    assert job.country_code is None

    assert job.application_url.endswith("/application")

    assert job.departments == ["Data", "Analytics"]

    assert job.offices == ["Latin America"]

    assert job.employment_type == "FullTime"

    assert job.workplace_type == "Remote"
    assert job.is_remote is True

    assert job.publication_date is not None

    assert job.publication_date.year == 2026

    assert job.salary_currency == "USD"
    assert job.salary_min == 45000
    assert job.salary_max == 60000

    assert job.salary_interval == "1 YEAR"

    assert job.salary_description == "$45K - $60K USD"

    assert job.description_text is not None
    assert "Python" in job.description_text

    assert job.raw_payload["title"] == "Junior Data Analyst"

    collector.close()


def test_unlisted_jobs_can_be_included(
    ashby_payload: dict,
) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=ashby_payload,
        )

    collector = create_collector(
        handler,
        include_unlisted=True,
    )

    result = collector.collect("example-company")

    assert result.total_received == 4
    assert result.total_valid == 4
    assert result.total_skipped == 0

    collector.close()


def test_empty_board() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "apiVersion": "1",
                "jobs": [],
            },
        )

    collector = create_collector(handler)

    result = collector.collect("empty-company")

    assert result.jobs == []
    assert result.total_received == 0
    assert result.total_valid == 0

    collector.close()


def test_invalid_response_structure() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"unexpected": []},
        )

    collector = create_collector(handler)

    with pytest.raises(ValueError, match="jobs"):
        collector.collect("example-company")

    collector.close()


def test_malformed_posting_is_skipped() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "title": "Valid Data Analyst",
                        "jobUrl": "https://example.com/jobs/1",
                        "isListed": True,
                    },
                    {
                        "title": "Missing URL",
                        "isListed": True,
                    },
                    "invalid-record",
                ]
            },
        )

    collector = create_collector(handler)

    result = collector.collect("example-company")

    assert result.total_received == 3
    assert result.total_valid == 1
    assert result.total_skipped == 2

    collector.close()


def test_salary_without_salary_component() -> None:

    compensation = {
        "summaryComponents": [
            {
                "compensationType": "EquityPercentage",
                "minValue": 0.5,
                "maxValue": 1.5,
            }
        ]
    }

    result = AshbyCollector._extract_salary(compensation)

    assert result["min"] is None
    assert result["max"] is None
    assert result["currency"] is None


def test_empty_board_identifier() -> None:

    collector = create_collector(
        lambda request: httpx.Response(
            200,
            json={"jobs": []},
        )
    )

    with pytest.raises(ValueError, match="identifier"):
        collector.collect(" ")

    collector.close()


def test_board_identifier_is_encoded() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == ("/posting-api/job-board/example%20company")

        return httpx.Response(
            200,
            json={"jobs": []},
        )

    collector = create_collector(handler)

    result = collector.collect("example%20company")

    assert result.total_valid == 0

    collector.close()
