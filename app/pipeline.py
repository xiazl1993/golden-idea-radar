from __future__ import annotations

from .clustering import rebuild_clusters
from .config import settings
from .models import Run, SessionLocal, init_db
from .pain import extract_pain_signals
from .report import write_report
from .scoring import build_and_score
from .timeutil import utcnow_naive


def run_pipeline(include_demo: bool = False, report_path: str = "reports/latest.md") -> dict:
    init_db()
    with SessionLocal() as session:
        run = Run(run_type="pipeline", status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        try:
            pains = extract_pain_signals(session, include_demo=include_demo)
            clusters = rebuild_clusters(session, threshold=settings.cluster_threshold, include_demo=include_demo)
            ideas = build_and_score(session, run)
            report = write_report(session, report_path, run_id=run.id)
            run.finished_at = utcnow_naive()
            run.status = "succeeded"
            run.stats = {"pain_signals_touched": pains, "clusters": clusters, "ideas": ideas, "report": str(report)}
            session.commit()
            return {"run_id": run.id, **run.stats}
        except Exception as exc:
            session.rollback()
            failed = session.get(Run, run.id)
            if failed:
                failed.finished_at = utcnow_naive()
                failed.status = "failed"
                failed.stats = {"error": type(exc).__name__}
                session.commit()
            raise
