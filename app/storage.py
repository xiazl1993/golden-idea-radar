from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .collectors.base import CollectedObservation
from .models import Observation


def upsert_observations(session: Session, items: list[CollectedObservation]) -> int:
    inserted = 0
    for item in items:
        existing = session.scalar(select(Observation).where(Observation.source == item.source, Observation.external_id == item.external_id))
        if existing:
            existing.text = item.text
            existing.title = item.title
            existing.url = item.url
            existing.author = item.author
            existing.published_at = item.published_at
            existing.metadata_json = item.metadata
            existing.is_demo = item.is_demo
            continue
        session.add(Observation(source=item.source, external_id=item.external_id, url=item.url, author=item.author, title=item.title, text=item.text, published_at=item.published_at, metadata_json=item.metadata, is_demo=item.is_demo))
        inserted += 1
    session.commit()
    return inserted
