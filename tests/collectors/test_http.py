import httpx
import pytest

from job_discovery.collectors.http import (
    ATSHTTPClient,
    ATSHTTPError,
)


def test_successful_json_request() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jobs": []},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http = ATSHTTPClient(
        client=client,
        max_retries=0,
        min_request_interval=0,
    )

    assert http.get_json("https://example.com/jobs") == {"jobs": []}

    http.close()
    client.close()


def test_http_404_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http = ATSHTTPClient(
        client=client,
        max_retries=3,
        min_request_interval=0,
    )

    with pytest.raises(ATSHTTPError, match="404"):
        http.get_json("https://example.com/jobs")

    assert calls == 1

    http.close()
    client.close()


def test_invalid_json() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"not-json",
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http = ATSHTTPClient(
        client=client,
        max_retries=0,
        min_request_interval=0,
    )

    with pytest.raises(ATSHTTPError, match="invalid JSON"):
        http.get_json("https://example.com/jobs")

    http.close()
    client.close()


def test_non_object_json() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=["unexpected"],
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http = ATSHTTPClient(
        client=client,
        max_retries=0,
        min_request_interval=0,
    )

    with pytest.raises(ATSHTTPError, match="JSON object"):
        http.get_json("https://example.com/jobs")

    http.close()
    client.close()


def test_retry_after_429(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    delays = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "2"},
            )

        return httpx.Response(200, json={"jobs": []})

    monkeypatch.setattr(
        "job_discovery.collectors.http.time.sleep",
        delays.append,
    )

    monkeypatch.setattr(
        "job_discovery.collectors.http.random.uniform",
        lambda a, b: 0,
    )

    client = httpx.Client(transport=httpx.MockTransport(handler))

    http = ATSHTTPClient(
        client=client,
        max_retries=1,
        min_request_interval=0,
    )

    result = http.get_json("https://example.com/jobs")

    assert result == {"jobs": []}
    assert calls == 2
    assert delays == [2.0]

    http.close()
    client.close()
