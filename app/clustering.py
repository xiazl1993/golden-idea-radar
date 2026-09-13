from __future__ import annotations

import hashlib

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .models import ClusterMember, Observation, PainCluster, PainSignal
from .pain import keywords
from .timeutil import utcnow_naive


def _token_set(text: str) -> set[str]:
    return set(keywords(text, limit=24))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def rebuild_clusters(session: Session, threshold: float = 0.42, include_demo: bool = False) -> int:
    session.execute(delete(ClusterMember))
    session.commit()

    query = select(PainSignal).join(Observation, Observation.id == PainSignal.observation_id).order_by(PainSignal.id)
    if not include_demo:
        query = query.where(Observation.is_demo.is_(False))
    signals = session.scalars(query).all()

    raw_clusters: list[dict] = []
    for signal in signals:
        token_set = _token_set(signal.normalized_text)
        best_idx: int | None = None
        best_sim = 0.0
        for idx, cluster in enumerate(raw_clusters):
            sim = _jaccard(token_set, cluster["tokens"])
            if sim > best_sim:
                best_idx, best_sim = idx, sim
        if best_idx is not None and best_sim >= threshold:
            c = raw_clusters[best_idx]
            c["signals"].append(signal)
            c["tokens"] |= token_set
        else:
            raw_clusters.append({"signals": [signal], "tokens": token_set})

    keyed: dict[str, dict] = {}
    for c in raw_clusters:
        sigs: list[PainSignal] = c["signals"]
        kws = keywords(" ".join(s.normalized_text for s in sigs), limit=8)
        representative = max(sigs, key=lambda s: s.severity * 0.7 + s.intent_score * 0.3)
        key_seed = "|".join(sorted(kws[:6])) or representative.normalized_text[:120]
        cluster_key = hashlib.sha1(key_seed.encode("utf-8")).hexdigest()[:16]
        if cluster_key in keyed:
            keyed[cluster_key]["signals"].extend(sigs)
            keyed[cluster_key]["tokens"] |= c["tokens"]
        else:
            keyed[cluster_key] = {"signals": list(sigs), "tokens": set(c["tokens"]), "keywords": kws}

    count = 0
    for cluster_key, c in keyed.items():
        sigs = c["signals"]
        observations = [session.get(Observation, s.observation_id) for s in sigs]
        representative = max(sigs, key=lambda s: s.severity * 0.7 + s.intent_score * 0.3)
        kws = keywords(" ".join(s.normalized_text for s in sigs), limit=8)
        representative_obs = session.get(Observation, representative.observation_id)
        title = ((representative_obs.title if representative_obs else None) or representative.normalized_text[:56]).strip()
        seen = [(o.published_at or o.captured_at) for o in observations if o]

        cluster = session.scalar(select(PainCluster).where(PainCluster.key == cluster_key))
        values = dict(title=title, representative_text=representative.normalized_text[:1000], keywords=kws, signal_count=len(sigs), source_diversity=len({o.source for o in observations if o}), first_seen_at=min(seen) if seen else None, last_seen_at=max(seen) if seen else None, updated_at=utcnow_naive())
        if cluster:
            for k, v in values.items():
                setattr(cluster, k, v)
        else:
            cluster = PainCluster(key=cluster_key, **values)
            session.add(cluster)
            session.flush()

        rep_tokens = _token_set(representative.normalized_text)
        for s in sigs:
            session.add(ClusterMember(cluster_id=cluster.id, pain_signal_id=s.id, similarity=round(_jaccard(_token_set(s.normalized_text), rep_tokens), 4)))
        count += 1
    session.commit()
    return count
