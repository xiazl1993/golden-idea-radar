from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

from .base import CollectedObservation
from ..timeutil import as_utc_naive


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip().replace("Z", "+00:00")
    try:
        return as_utc_naive(datetime.fromisoformat(value))
    except ValueError:
        return None


class CsvCollector:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def collect(self) -> list[CollectedObservation]:
        rows: list[CollectedObservation] = []
        with self.path.open("r", encoding="utf-8-sig", newline="") as f:
            for idx, row in enumerate(csv.DictReader(f), start=1):
                text = (row.get("text") or "").strip()
                if not text:
                    continue
                metadata_raw = (row.get("metadata_json") or "").strip()
                try:
                    metadata = json.loads(metadata_raw) if metadata_raw else {}
                except json.JSONDecodeError:
                    metadata = {"raw_metadata": metadata_raw}
                rows.append(CollectedObservation(source=(row.get("source") or "manual").strip(), external_id=(row.get("external_id") or f"row-{idx}").strip(), url=(row.get("url") or "").strip() or None, author=(row.get("author") or "").strip() or None, title=(row.get("title") or "").strip() or None, text=text, published_at=_dt(row.get("published_at")), metadata=metadata, is_demo=(row.get("is_demo") or "false").strip().lower() in {"1", "true", "yes"}))
        return rows
