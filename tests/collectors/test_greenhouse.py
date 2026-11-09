import json
from pathlib import Path

import httpx
import pytest

from job_discovery.collectors.greenhouse import GreenhouseCollector
from job_discovery.collectors.http import ATSHTTPClient

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "greenhouse_jobs.json"


@pytest.fixture
def greenhouse_payload() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def create_collector(
    handler,
    include_prospect_posts: bool = False,
) -> GreenhouseCollector:

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http_client = ATSHTTPClient(
        min_request_interval=0,
        max_retries=0,
        client=client,
    )

    return GreenhouseCollector(
        http_client=http_client,
        include_prospect_posts=include_prospect_posts,
    )


def test_collect_jobs(greenhouse_payload: dict) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"

        assert str(request.url) == (
            "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
        )

        return httpx.Response(
            200,
            json=greenhouse_payload,
        )

    collector = create_collector(handler)

    result = collector.collect("example")

    assert result.platform == "GREENHOUSE"
    assert result.board_identifier == "example"

    assert result.total_received == 3
    assert result.total_valid == 2
    assert result.total_skipped == 1

    assert len(result.jobs) == 2

    job = result.jobs[0]

    assert job.external_id == "12345"
    assert job.title == "Junior Data Analyst"
    assert job.location == "Remote - Americas"

    assert job.departments == ["Data"]
    assert job.offices == ["Remote"]

    assert "Python" in job.description_text
    assert "SQL" in job.description_text

    assert job.application_url.endswith("/12345")

    assert job.updated_at is not None
    assert job.publication_date is None

    assert job.raw_payload["id"] == 12345

    collector.close()


def test_prospect_posts_can_be_included(
    greenhouse_payload: dict,
) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=greenhouse_payload,
        )

    collector = create_collector(
        handler,
        include_prospect_posts=True,
    )

    result = collector.collect("example")

    assert result.total_received == 3
    assert result.total_valid == 3
    assert result.total_skipped == 0

    collector.close()


def test_empty_board() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": [], "meta": {"total": 0}},
        )

    collector = create_collector(handler)

    result = collector.collect("empty")

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
        collector.collect("example")

    collector.close()


def test_malformed_job_is_skipped() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 123,
                        "internal_job_id": 456,
                        "title": "Valid Job",
                    },
                    {
                        "id": 124,
                        "internal_job_id": 457,
                    },
                ]
            },
        )

    collector = create_collector(handler)

    result = collector.collect("example")

    assert result.total_received == 2
    assert result.total_valid == 1
    assert result.total_skipped == 1

    assert result.jobs[0].title == "Valid Job"

    collector.close()


def test_empty_board_identifier() -> None:

    collector = create_collector(lambda request: httpx.Response(200, json={"jobs": []}))

    with pytest.raises(ValueError, match="identifier"):
        collector.collect(" ")

    collector.close()
