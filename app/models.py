from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings
from .timeutil import utcnow_naive


class Base(DeclarativeBase):
    pass


class Run(Base):
    __tablename__ = "gi_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(32), default="pipeline")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="running")
    stats: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class Observation(Base):
    __tablename__ = "gi_observations"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_gi_observation_source_external"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class PainSignal(Base):
    __tablename__ = "gi_pain_signals"
    __table_args__ = (UniqueConstraint("observation_id", name="uq_gi_pain_observation"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("gi_observations.id", ondelete="CASCADE"), index=True)
    normalized_text: Mapped[str] = mapped_column(Text)
    severity: Mapped[float] = mapped_column(Float, default=0.0)
    intent_score: Mapped[float] = mapped_column(Float, default=0.0)
    matched_phrases: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)

    observation: Mapped[Observation] = relationship()


class PainCluster(Base):
    __tablename__ = "gi_pain_clusters"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    title: Mapped[str] = mapped_column(Text)
    representative_text: Mapped[str] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list)
    signal_count: Mapped[int] = mapped_column(Integer, default=0)
    source_diversity: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class ClusterMember(Base):
    __tablename__ = "gi_cluster_members"
    __table_args__ = (UniqueConstraint("cluster_id", "pain_signal_id", name="uq_gi_cluster_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("gi_pain_clusters.id", ondelete="CASCADE"), index=True)
    pain_signal_id: Mapped[int] = mapped_column(ForeignKey("gi_pain_signals.id", ondelete="CASCADE"), index=True)
    similarity: Mapped[float] = mapped_column(Float, default=0.0)


class Idea(Base):
    __tablename__ = "gi_ideas"
    __table_args__ = (UniqueConstraint("cluster_id", name="uq_gi_idea_cluster"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("gi_pain_clusters.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text)
    target_user: Mapped[str] = mapped_column(Text, default="中国 ToC 用户")
    proposed_mvp: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="DISCOVERED", index=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


class Score(Base):
    __tablename__ = "gi_scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    idea_id: Mapped[int] = mapped_column(ForeignKey("gi_ideas.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("gi_runs.id", ondelete="SET NULL"), nullable=True)
    pain_score: Mapped[float] = mapped_column(Float)
    frequency_score: Mapped[float] = mapped_column(Float)
    growth_score: Mapped[float] = mapped_column(Float)
    payment_score: Mapped[float] = mapped_column(Float)
    gap_score: Mapped[float] = mapped_column(Float)
    mvp_score: Mapped[float] = mapped_column(Float)
    distribution_score: Mapped[float] = mapped_column(Float)
    builder_fit_score: Mapped[float] = mapped_column(Float)
    moat_score: Mapped[float] = mapped_column(Float)
    opportunity_score: Mapped[float] = mapped_column(Float)
    giant_risk: Mapped[float] = mapped_column(Float)
    model_risk: Mapped[float] = mapped_column(Float)
    regulatory_risk: Mapped[float] = mapped_column(Float)
    acquisition_risk: Mapped[float] = mapped_column(Float)
    operation_risk: Mapped[float] = mapped_column(Float)
    final_score: Mapped[float] = mapped_column(Float, index=True)
    rationale: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive)


engine_kwargs: dict[str, Any] = {"future": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
database_url = settings.database_url
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
elif database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql+psycopg://", 1)
engine = create_engine(database_url, **engine_kwargs)

if database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    # Local SQLite is self-bootstrapping. Postgres/Supabase must use the SQL
    # migration so RLS and the full research schema are not silently skipped.
    if database_url.startswith("sqlite"):
        Base.metadata.create_all(bind=engine)
