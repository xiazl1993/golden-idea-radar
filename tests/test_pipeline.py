from pathlib import Path

from sqlalchemy import func, select

from app.collectors.manual import CsvCollector
from app.models import Base, Observation, Score, SessionLocal, engine
from app.pipeline import run_pipeline
from app.storage import upsert_observations


def _reset() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_demo_pipeline(tmp_path: Path):
    _reset()
    sample = Path(__file__).parents[1] / "samples" / "evidence.csv"
    items = CsvCollector(sample).collect()
    with SessionLocal() as session:
        inserted = upsert_observations(session, items)
        assert inserted == 5
    report = tmp_path / "report.md"
    stats = run_pipeline(include_demo=True, report_path=str(report))
    assert stats["clusters"] >= 1
    assert stats["ideas"] >= 1
    assert report.exists()
    text = report.read_text(encoding="utf-8")
    assert "Golden Idea Radar" in text
    assert "Evidence samples" in text


def test_formal_run_excludes_existing_demo_signals(tmp_path: Path):
    _reset()
    sample = Path(__file__).parents[1] / "samples" / "evidence.csv"
    with SessionLocal() as session:
        upsert_observations(session, CsvCollector(sample).collect())
    run_pipeline(include_demo=True, report_path=str(tmp_path / "demo.md"))
    formal = run_pipeline(include_demo=False, report_path=str(tmp_path / "formal.md"))
    assert formal["ideas"] == 0
    assert "| 1 |" not in (tmp_path / "formal.md").read_text(encoding="utf-8")


def test_scores_keep_run_history(tmp_path: Path):
    _reset()
    sample = Path(__file__).parents[1] / "samples" / "evidence.csv"
    with SessionLocal() as session:
        upsert_observations(session, CsvCollector(sample).collect())
    first = run_pipeline(include_demo=True, report_path=str(tmp_path / "one.md"))
    second = run_pipeline(include_demo=True, report_path=str(tmp_path / "two.md"))
    with SessionLocal() as session:
        score_count = session.scalar(select(func.count()).select_from(Score)) or 0
        obs_count = session.scalar(select(func.count()).select_from(Observation)) or 0
    assert first["ideas"] == second["ideas"]
    assert score_count == first["ideas"] + second["ideas"]
    assert obs_count == 5
