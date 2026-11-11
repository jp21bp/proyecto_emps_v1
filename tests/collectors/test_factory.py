import httpx
import pytest

from job_discovery.collectors import (
    AshbyCollector,
    GreenhouseCollector,
    LeverCollector,
    create_collector,
    normalize_platform,
    supported_platforms,
)
from job_discovery.collectors.http import ATSHTTPClient


@pytest.mark.parametrize(
    ("platform", "expected_type"),
    [
        ("GREENHOUSE", GreenhouseCollector),
        ("greenhouse", GreenhouseCollector),
        ("Greenhouse", GreenhouseCollector),
        ("LEVER", LeverCollector),
        ("lever", LeverCollector),
        ("ASHBY", AshbyCollector),
        ("ashby", AshbyCollector),
    ],
)
def test_create_collector(
    platform: str,
    expected_type: type,
) -> None:

    collector = create_collector(platform)

    try:
        assert isinstance(collector, expected_type)
    finally:
        collector.close()


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("greenhouse", "GREENHOUSE"),
        (" GREENHOUSE ", "GREENHOUSE"),
        ("Lever", "LEVER"),
        ("ashby", "ASHBY"),
        ("smart recruiters", "SMART_RECRUITERS"),
        ("workday-ats", "WORKDAY_ATS"),
    ],
)
def test_normalize_platform(
    platform: str,
    expected: str,
) -> None:

    assert normalize_platform(platform) == expected


def test_supported_platforms() -> None:

    platforms = supported_platforms()

    assert platforms == (
        "ASHBY",
        "GREENHOUSE",
        "LEVER",
    )


@pytest.mark.parametrize(
    "platform",
    [
        "",
        " ",
        "WORKDAY",
        "SMARTRECRUITERS",
        "UNKNOWN",
    ],
)
def test_unsupported_platform(
    platform: str,
) -> None:

    with pytest.raises(
        ValueError,
        match="ATS platform",
    ):
        create_collector(platform)


def test_collector_options_are_forwarded() -> None:

    collector = create_collector(
        "LEVER",
        page_size=25,
        max_pages=10,
    )

    try:
        assert collector.page_size == 25
        assert collector.max_pages == 10
    finally:
        collector.close()


def test_ashby_options_are_forwarded() -> None:

    collector = create_collector(
        "ASHBY",
        include_compensation=False,
    )

    try:
        assert collector.include_compensation is False
    finally:
        collector.close()


def test_factory_rejects_invalid_platform_type() -> None:

    with pytest.raises(ValueError):
        create_collector(None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("platform", "board", "response"),
    [
        (
            "GREENHOUSE",
            "example",
            {"jobs": []},
        ),
        (
            "LEVER",
            "example",
            [],
        ),
        (
            "ASHBY",
            "example",
            {"jobs": []},
        ),
    ],
)
def test_factory_collectors_share_interface(
    platform: str,
    board: str,
    response: dict | list,
) -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=response,
        )

    httpx_client = httpx.Client(
        transport=httpx.MockTransport(handler)
    )

    http_client = ATSHTTPClient(
        client=httpx_client,
        max_retries=0,
        min_request_interval=0,
    )

    collector = create_collector(
        platform,
        http_client=http_client,
    )

    try:
        result = collector.collect(board)

        assert result.board_identifier == board
        assert result.total_received == 0
        assert result.total_valid == 0
        assert result.jobs == []

    finally:
        collector.close()
        http_client.close()