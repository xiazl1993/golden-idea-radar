from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class CollectedObservation:
    source: str
    external_id: str
    text: str
    title: str | None = None
    url: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_demo: bool = False


class Collector(Protocol):
    def collect(self) -> list[CollectedObservation]: ...
