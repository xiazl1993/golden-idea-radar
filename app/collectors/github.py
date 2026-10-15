from __future__ import annotations

from datetime import datetime
import time
import warnings

import httpx

from .base import CollectedObservation
from ..timeutil import as_utc_naive


DEFAULT_QUERIES = [
    '"feature request" "manual" automation is:issue',
    '"there is no way" is:issue',
    '"wish there was" is:issue',
    '"cannot" "from the CLI" is:issue',
    '"希望支持" is:issue',
    '"有没有办法" 自动 is:issue',
]

NOISE_TERMS = {
    "control center",
    "coordination channel",
    "coordination ledger",
    "canonical planning",
    "conductor log",
    "team huddle",
    "standing issue",
    "autopilot",
    "roadmap",
    "agent team",
    "execution authority",
}

RETRYABLE_STATUS_CODES = {403, 429, 500, 502, 503, 504}


class GitHubIssueCollector:
    def __init__(
        self,
        token: str | None = None,
        queries: list[str] | None = None,
        per_query: int = 30,
        query_interval: float = 2.1,
        max_retries: int = 3,
    ):
        self.token = token
        self.queries = queries or DEFAULT_QUERIES
        self.per_query = max(1, min(per_query, 100))
        self.query_interval = max(0.0, query_interval)
        self.max_retries = max(0, max_retries)

    @staticmethod
    def _is_noise(title: str, body: str) -> bool:
        haystack = f"{title}\n{body}".lower()
        return any(term in haystack for term in NOISE_TERMS)

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        retry_after = response.headers.get("retry-after")
        if retry_after:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass

        reset_at = response.headers.get("x-ratelimit-reset")
        if response.headers.get("x-ratelimit-remaining") == "0" and reset_at:
            try:
                return max(1.0, float(reset_at) - time.time() + 1.0)
            except ValueError:
                pass

        return min(60.0, 2.0 ** (attempt + 1))

    def _get_with_retry(self, client: httpx.Client, query: str) -> httpx.Response:
        response: httpx.Response | None = None
        for attempt in range(self.max_retries + 1):
            response = client.get(
                "https://api.github.com/search/issues",
                params={"q": query, "per_page": self.per_query, "sort": "updated", "order": "desc"},
            )
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == self.max_retries:
                return response

            delay = self._retry_delay(response, attempt)
            warnings.warn(
                f"GitHub search returned {response.status_code}; retrying in {delay:.1f}s "
                f"(attempt {attempt + 1}/{self.max_retries})",
                RuntimeWarning,
            )
            time.sleep(delay)

        assert response is not None
        return response

    @staticmethod
    def _error_detail(response: httpx.Response) -> str:
        try:
            message = response.json().get("message", "")
        except (ValueError, AttributeError):
            message = ""
        return f": {message}" if message else ""

    def collect(self) -> list[CollectedObservation]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        out: dict[str, CollectedObservation] = {}
        successful_queries = 0
        last_failure: httpx.Response | None = None
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            for index, query in enumerate(self.queries):
                response = self._get_with_retry(client, query)
                if response.is_error:
                    last_failure = response
                    warnings.warn(
                        f"Skipping GitHub query after retries ({response.status_code})"
                        f"{self._error_detail(response)}: {query}",
                        RuntimeWarning,
                    )
                else:
                    successful_queries += 1
                    for item in response.json().get("items", []):
                        if item.get("pull_request"):
                            continue
                        issue_id = str(item["id"])
                        body = item.get("body") or ""
                        title = item.get("title") or ""
                        if self._is_noise(title, body):
                            continue
                        text = (title + "\n" + body).strip()
                        if not text:
                            continue
                        published = item.get("created_at")
                        published_at = as_utc_naive(datetime.fromisoformat(published.replace("Z", "+00:00"))) if published else None
                        labels = [x.get("name") for x in item.get("labels", []) if isinstance(x, dict) and x.get("name")]
                        out[issue_id] = CollectedObservation(
                            source="github",
                            external_id=issue_id,
                            url=item.get("html_url"),
                            author=(item.get("user") or {}).get("login"),
                            title=title,
                            text=text,
                            published_at=published_at,
                            metadata={"query": query, "comments": item.get("comments", 0), "state": item.get("state"), "labels": labels},
                        )
                if index < len(self.queries) - 1 and self.query_interval:
                    time.sleep(self.query_interval)

        if successful_queries == 0 and last_failure is not None:
            last_failure.raise_for_status()
        return list(out.values())
