import httpx
import pytest

from app.collectors.github import GitHubIssueCollector


class FakeClient:
    def __init__(self, responses: list[httpx.Response]):
        self.responses = iter(responses)
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, *args, **kwargs) -> httpx.Response:
        self.calls += 1
        return next(self.responses)


def response(status_code: int, headers: dict[str, str] | None = None) -> httpx.Response:
    request = httpx.Request("GET", "https://api.github.com/search/issues")
    return httpx.Response(status_code, headers=headers, request=request, json={"items": []})


def test_search_retries_rate_limit_with_retry_after(monkeypatch: pytest.MonkeyPatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.collectors.github.time.sleep", sleeps.append)
    client = FakeClient(
        [
            response(403, {"retry-after": "3"}),
            response(200),
        ]
    )
    collector = GitHubIssueCollector(queries=["is:issue"], max_retries=2)

    with pytest.warns(RuntimeWarning, match="403"):
        result = collector._get_with_retry(client, "is:issue")

    assert result.status_code == 200
    assert client.calls == 2
    assert sleeps == [3.0]


def test_search_stops_after_retry_limit(monkeypatch: pytest.MonkeyPatch):
    sleeps: list[float] = []
    monkeypatch.setattr("app.collectors.github.time.sleep", sleeps.append)
    client = FakeClient([response(503), response(503), response(503)])
    collector = GitHubIssueCollector(queries=["is:issue"], max_retries=2)

    with pytest.warns(RuntimeWarning, match="503"):
        result = collector._get_with_retry(client, "is:issue")

    assert result.status_code == 503
    assert client.calls == 3
    assert sleeps == [2.0, 4.0]


def test_collect_skips_one_failed_query(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient([response(403), response(200)])
    monkeypatch.setattr("app.collectors.github.httpx.Client", lambda **kwargs: client)
    monkeypatch.setattr("app.collectors.github.time.sleep", lambda seconds: None)
    collector = GitHubIssueCollector(
        queries=["blocked is:issue", "working is:issue"],
        query_interval=0,
        max_retries=0,
    )

    with pytest.warns(RuntimeWarning, match="Skipping GitHub query"):
        items = collector.collect()

    assert items == []
    assert client.calls == 2


def test_collect_fails_when_every_query_fails(monkeypatch: pytest.MonkeyPatch):
    client = FakeClient([response(403), response(503)])
    monkeypatch.setattr("app.collectors.github.httpx.Client", lambda **kwargs: client)
    monkeypatch.setattr("app.collectors.github.time.sleep", lambda seconds: None)
    collector = GitHubIssueCollector(
        queries=["blocked is:issue", "also-blocked is:issue"],
        query_interval=0,
        max_retries=0,
    )

    with pytest.warns(RuntimeWarning), pytest.raises(httpx.HTTPStatusError):
        collector.collect()
