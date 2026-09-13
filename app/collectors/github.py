from __future__ import annotations

from datetime import datetime

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


class GitHubIssueCollector:
    def __init__(self, token: str | None = None, queries: list[str] | None = None, per_query: int = 30):
        self.token = token
        self.queries = queries or DEFAULT_QUERIES
        self.per_query = max(1, min(per_query, 100))

    @staticmethod
    def _is_noise(title: str, body: str) -> bool:
        haystack = f"{title}\n{body}".lower()
        return any(term in haystack for term in NOISE_TERMS)

    def collect(self) -> list[CollectedObservation]:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        out: dict[str, CollectedObservation] = {}
        with httpx.Client(timeout=20, headers=headers, follow_redirects=True) as client:
            for query in self.queries:
                response = client.get(
                    "https://api.github.com/search/issues",
                    params={"q": query, "per_page": self.per_query, "sort": "updated", "order": "desc"},
                )
                response.raise_for_status()
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
        return list(out.values())
