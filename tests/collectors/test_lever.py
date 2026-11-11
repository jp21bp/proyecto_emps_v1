import json
from pathlib import Path

import httpx
import pytest

from job_discovery.collectors.http import ATSHTTPClient, ATSHTTPError
from job_discovery.collectors.lever import LeverCollector

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lever_postings.json"


@pytest.fixture
def lever_payload() -> list[dict]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def create_collector(
    handler,
    page_size: int = 100,
) -> LeverCollector:

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http_client = ATSHTTPClient(
        client=client,
        max_retries=0,
        min_request_interval=0,
    )

    return LeverCollector(
        http_client=http_client,
        page_size=page_size,
    )


def test_collect_jobs(lever_payload: list[dict]) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"

        assert request.url.path == ("/v0/postings/example")

        assert request.url.params["mode"] == "json"
        assert request.url.params["skip"] == "0"
        assert request.url.params["limit"] == "100"

        return httpx.Response(
            200,
            json=lever_payload,
        )

    collector = create_collector(handler)

    result = collector.collect("example")

    assert result.platform == "LEVER"
    assert result.board_identifier == "example"

    assert result.total_received == 3
    assert result.total_valid == 3
    assert result.total_skipped == 0

    assert len(result.jobs) == 3

    job = result.jobs[0]

    assert job.external_id == "lever-job-001"
    assert job.title == "Junior Data Analyst"

    assert job.location == "Remote - Americas"
    assert job.country_code is None

    assert job.application_url.endswith("/apply")

    assert job.departments == ["Data", "Analytics"]

    assert job.offices == [
        "Remote - Americas",
        "United States",
        "Latin America",
    ]

    assert job.employment_type == "Full-time"
    assert job.workplace_type == "remote"

    assert job.salary_currency == "USD"
    assert job.salary_min == 45000
    assert job.salary_max == 60000

    assert job.salary_interval == "per-year-salary"

    assert job.requisition_id == "DA-001"

    assert job.description_text is not None
    assert "Python" in job.description_text

    assert job.publication_date is None
    assert job.source_created_at is not None
    assert job.updated_at is not None

    assert job.raw_payload["id"] == "lever-job-001"

    collector.close()


def test_pagination(lever_payload: list[dict]) -> None:

    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = request.url.params

        skip = int(params["skip"])

        requests.append(skip)

        if skip == 0:
            return httpx.Response(
                200,
                json=lever_payload[:2],
            )

        if skip == 2:
            return httpx.Response(
                200,
                json=lever_payload[2:],
            )

        return httpx.Response(
            200,
            json=[],
        )

    collector = create_collector(
        handler,
        page_size=2,
    )

    result = collector.collect("example")

    assert requests == [0, 2]

    assert result.total_received == 3
    assert result.total_valid == 3

    assert len(result.jobs) == 3

    collector.close()


def test_duplicate_postings_are_skipped() -> None:

    duplicate = {
        "id": "duplicate-001",
        "text": "Data Analyst",
        "categories": {},
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[duplicate, duplicate],
        )

    collector = create_collector(handler)

    result = collector.collect("example")

    assert result.total_received == 2
    assert result.total_valid == 1
    assert result.total_skipped == 1

    collector.close()


def test_malformed_posting_is_skipped() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "id": "valid-001",
                    "text": "Data Analyst",
                    "categories": {},
                },
                {"id": "invalid-001"},
            ],
        )

    collector = create_collector(handler)

    result = collector.collect("example")

    assert result.total_received == 2
    assert result.total_valid == 1
    assert result.total_skipped == 1

    collector.close()


def test_empty_board() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    collector = create_collector(handler)

    result = collector.collect("empty")

    assert result.jobs == []
    assert result.total_received == 0

    collector.close()


def test_invalid_response_structure() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": []},
        )

    collector = create_collector(handler)

    with pytest.raises(ATSHTTPError, match="JSON array"):
        collector.collect("example")

    collector.close()


def test_empty_site_identifier() -> None:

    collector = create_collector(lambda request: httpx.Response(200, json=[]))

    with pytest.raises(ValueError, match="identifier"):
        collector.collect(" ")

    collector.close()


def test_site_identifier_is_url_encoded() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v0/postings/example%20company"

        return httpx.Response(200, json=[])

    collector = create_collector(handler)

    result = collector.collect("example%20company")

    assert result.total_valid == 0

    collector.close()
