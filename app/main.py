from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from sqlalchemy import desc, select

from .models import ClusterMember, Idea, Observation, PainSignal, Run, Score, SessionLocal, init_db
from .pipeline import run_pipeline

app = FastAPI(title="Golden Idea Radar", version="0.1.0")


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": "0.1.0"}


@app.post("/pipeline/run")
def pipeline_run(include_demo: bool = False) -> dict:
    return run_pipeline(include_demo=include_demo)


def _latest_run_id(session) -> int | None:
    return session.scalar(select(Run.id).where(Run.status == "succeeded").order_by(desc(Run.id)).limit(1))


@app.get("/ideas")
def ideas(limit: int = Query(20, ge=1, le=100), run_id: int | None = None) -> list[dict]:
    with SessionLocal() as session:
        effective_run = run_id or _latest_run_id(session)
        if effective_run is None:
            return []
        rows = session.execute(
            select(Idea, Score)
            .join(Score, Score.idea_id == Idea.id)
            .where(Score.run_id == effective_run)
            .order_by(desc(Score.final_score))
            .limit(limit)
        ).all()
        return [
            {
                "id": idea.id,
                "title": idea.title,
                "problem": idea.problem,
                "mvp": idea.proposed_mvp,
                "status": idea.status,
                "final_score": score.final_score,
                "opportunity_score": score.opportunity_score,
                "risks": {
                    "giant": score.giant_risk,
                    "model": score.model_risk,
                    "regulatory": score.regulatory_risk,
                    "acquisition": score.acquisition_risk,
                    "operation": score.operation_risk,
                },
                "evidence": score.rationale,
            }
            for idea, score in rows
        ]


@app.get("/ideas/{idea_id}/evidence")
def idea_evidence(idea_id: int, limit: int = Query(50, ge=1, le=200)) -> list[dict]:
    with SessionLocal() as session:
        idea = session.get(Idea, idea_id)
        if not idea:
            raise HTTPException(status_code=404, detail="idea not found")
        rows = session.scalars(
            select(Observation)
            .join(PainSignal, PainSignal.observation_id == Observation.id)
            .join(ClusterMember, ClusterMember.pain_signal_id == PainSignal.id)
            .where(ClusterMember.cluster_id == idea.cluster_id)
            .order_by(Observation.published_at.desc().nullslast(), Observation.captured_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "source": row.source,
                "external_id": row.external_id,
                "url": row.url,
                "title": row.title,
                "text": row.text,
                "published_at": row.published_at,
                "is_demo": row.is_demo,
            }
            for row in rows
        ]
