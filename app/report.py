from __future__ import annotations

from pathlib import Path

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .models import ClusterMember, Idea, Observation, PainSignal, Score


def _evidence(session: Session, idea: Idea, limit: int = 5) -> list[Observation]:
    return session.scalars(select(Observation).join(PainSignal, PainSignal.observation_id == Observation.id).join(ClusterMember, ClusterMember.pain_signal_id == PainSignal.id).where(ClusterMember.cluster_id == idea.cluster_id).order_by(Observation.published_at.desc().nullslast(), Observation.captured_at.desc()).limit(limit)).all()


def render_top(session: Session, run_id: int, limit: int = 20) -> str:
    rows = session.execute(select(Idea, Score).join(Score, Score.idea_id == Idea.id).where(Score.run_id == run_id).order_by(desc(Score.final_score)).limit(limit)).all()
    lines = ["# Golden Idea Radar — Top Candidates", "", f"Run: `{run_id}`", "", "| # | Idea | Final | Opportunity | Giant | Model | Regulatory | Evidence | Sources |", "|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for idx, (idea, score) in enumerate(rows, start=1):
        lines.append(f"| {idx} | {idea.title.replace('|', '/')} | {score.final_score:.1f} | {score.opportunity_score:.1f} | {score.giant_risk:.1f} | {score.model_risk:.1f} | {score.regulatory_risk:.1f} | {score.rationale.get('evidence_count', 0)} | {score.rationale.get('source_diversity', 0)} |")
    lines.append("")
    for idx, (idea, score) in enumerate(rows[:3], start=1):
        lines.extend([f"## Top {idx}: {idea.title}", f"- Final score: **{score.final_score:.1f}**", f"- Problem: {idea.problem[:500]}", f"- MVP: {idea.proposed_mvp}", f"- Evidence: {score.rationale.get('evidence_count', 0)} signals / {score.rationale.get('source_diversity', 0)} sources", f"- Kill checks: giant={score.giant_risk:.1f}, model={score.model_risk:.1f}, regulatory={score.regulatory_risk:.1f}, acquisition={score.acquisition_risk:.1f}, operation={score.operation_risk:.1f}", "- Evidence samples:"])
        evidence = _evidence(session, idea)
        if not evidence:
            lines.append("  - (none)")
        for obs in evidence:
            label = (obs.title or obs.text[:80]).replace("\n", " ")
            if obs.url:
                lines.append(f"  - [{obs.source}] [{label}]({obs.url})")
            else:
                lines.append(f"  - [{obs.source}] {label}")
        lines.append("")
    return "\n".join(lines)


def write_report(session: Session, path: str | Path, run_id: int, limit: int = 20) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_top(session, run_id=run_id, limit=limit), encoding="utf-8")
    return path
