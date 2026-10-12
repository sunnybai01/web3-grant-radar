import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Float,
    ForeignKey, UniqueConstraint, Index, JSON, Boolean,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from .database import Base


class RawSignal(Base):
    """Original fetch records before dedup — every scraped item lands here."""
    __tablename__ = "raw_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_type = Column(String(32), nullable=False, index=True)  # rss|github_api|twitter|discord|web_scraper|rsshub
    source_name = Column(String(128), nullable=False, index=True)
    raw_content = Column(Text, nullable=False)
    raw_url = Column(Text, nullable=True)
    canonical_url = Column(Text, nullable=True)
    content_hash = Column(String(64), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    # Processing state. A signal counts as "seen" by L1 only once processed:
    # pending -> done | failed. Failed (or abandoned pending) signals are retried
    # when fetched again, up to RAW_SIGNAL_MAX_ATTEMPTS.
    status = Column(String(16), nullable=False, default="pending", server_default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=1, server_default="1")
    last_error = Column(Text, nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Keyed on (url, content_hash), not url alone: many listing/index pages keep a
        # stable URL while their content rolls over, and a url-only key would block
        # every opportunity added after the first fetch.
        UniqueConstraint(
            "canonical_url", "content_hash", name="uq_raw_signals_canonical_url_content"
        ),
        Index("ix_raw_signals_fetched", "source_name", "fetched_at"),
        Index("ix_raw_signals_url_hash", "canonical_url", "content_hash"),
    )


class Event(Base):
    """Deduped, verified, structured event — the master entity (Event-Centric design)."""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(32), nullable=False, index=True)  # grant|hackathon|bounty|other
    title = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=True)
    deadline = Column(DateTime(timezone=True), nullable=True, index=True)
    amount = Column(String(256), nullable=True)
    track = Column(String(128), nullable=True)
    ecosystem = Column(String(64), nullable=True, index=True)
    application_url = Column(Text, nullable=True)
    source_url = Column(Text, nullable=True)
    source_platform = Column(String(128), nullable=True)

    # Zero-trust verification
    is_verified = Column(Boolean, default=False)
    verification_log = Column(JSON, nullable=True)

    # Scoring (4D matrix)
    score_roi = Column(Float, nullable=True)
    score_reputation = Column(Float, nullable=True)
    score_timeliness = Column(Float, nullable=True)
    score_strategy = Column(Float, nullable=True)
    final_score = Column(Float, nullable=True, index=True)

    # Heat tracking — each new source adds weight
    heat_count = Column(Integer, default=1)

    # Slack dispatch tracking
    status = Column(String(32), default="new")  # new|pushed|archived|expired|fraud
    slack_ts = Column(String(64), nullable=True)
    slack_channel_id = Column(String(32), nullable=True)

    # Dashboard triage decision: new | shortlisted | dismissed. This is the source
    # of truth for "dismissed"; is_dismissed is kept in sync for rollback only.
    triage_status = Column(String(16), nullable=False, default="new", server_default="new", index=True)
    triaged_at = Column(DateTime(timezone=True), nullable=True)

    # Legacy dismissal flag — written alongside triage_status, no longer read.
    is_dismissed = Column(Boolean, default=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    sources = relationship("EventSource", back_populates="event", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_events_type_score", "event_type", "final_score"),
        Index("ix_events_status", "status", "created_at"),
        Index("ix_events_window", "created_at", "ecosystem"),
        # Covers: WHERE status IN (?) AND event_type IN (?) AND final_score >= ?
        #         ORDER BY final_score DESC
        Index(
            "ix_events_dashboard",
            "status",
            "event_type",
            "final_score",
            postgresql_using="btree",
        ),
    )


class EventSource(Base):
    """Multi-source evidence chain — one event may have many source traces."""
    __tablename__ = "event_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type = Column(String(32), nullable=False)
    source_name = Column(String(128), nullable=False)
    source_url = Column(Text, nullable=True)
    raw_signal_id = Column(Integer, ForeignKey("raw_signals.id", ondelete="SET NULL"), nullable=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())

    event = relationship("Event", back_populates="sources")

    __table_args__ = (
        UniqueConstraint("event_id", "source_url", name="uq_event_source_url"),
    )


class SourceHealth(Base):
    """Per-source health monitoring."""
    __tablename__ = "source_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(128), unique=True, nullable=False, index=True)
    last_success_at = Column(DateTime(timezone=True), nullable=True)
    last_fetch_at = Column(DateTime(timezone=True), nullable=True)
    consecutive_failures = Column(Integer, default=0)
    status = Column(String(16), default="healthy")  # healthy|degraded|down
    last_error = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TwitterSourceState(Base):
    """Per-source Twitter cursor and cooldown state."""
    __tablename__ = "twitter_source_state"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(128), unique=True, nullable=False, index=True)
    last_tweet_id = Column(String(64), nullable=True)
    cursor = Column(Text, nullable=True)
    auth_profile = Column(String(64), nullable=True)
    cooldown_until = Column(DateTime(timezone=True), nullable=True)
    last_fetched_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ScheduleLog(Base):
    """Job execution audit log."""
    __tablename__ = "schedule_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_name = Column(String(128), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)
    items_fetched = Column(Integer, default=0)
    items_new = Column(Integer, default=0)
    items_deduped = Column(Integer, default=0)
    items_classified = Column(Integer, default=0)
    items_verified = Column(Integer, default=0)
    status = Column(String(16), default="running")  # running|success|failed
    error_message = Column(Text, nullable=True)


class PushLog(Base):
    """Slack push audit log."""
    __tablename__ = "push_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="SET NULL"), nullable=True, index=True)
    pushed_at = Column(DateTime(timezone=True), server_default=func.now())
    channel = Column(String(32), default="slack")  # slack|telegram
    action = Column(String(16), default="create")   # create|update|thread_append
    slack_ts = Column(String(64), nullable=True)
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)


class AgentMission(Base):
    """Run-level record for an agent-driven investigation mission."""
    __tablename__ = "agent_missions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    goal = Column(String(255), nullable=False, index=True)
    event_id = Column(Integer, nullable=False, index=True)
    status = Column(String(32), default="running", index=True)  # running|completed|failed
    mission_type = Column(String(64), default="single_event_investigation")
    max_steps = Column(Integer, default=3)
    conclusion = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    finished_at = Column(DateTime(timezone=True), nullable=True)

    trajectories = relationship(
        "AgentTrajectory",
        back_populates="mission",
        cascade="all, delete-orphan",
    )


class AgentTrajectory(Base):
    """Step-by-step trace of what the agent did during a mission."""
    __tablename__ = "agent_trajectories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mission_id = Column(Integer, ForeignKey("agent_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    action = Column(String(64), nullable=False)
    thought = Column(Text, nullable=True)
    action_input = Column(JSON, nullable=True)
    observation = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    mission = relationship("AgentMission", back_populates="trajectories")

    __table_args__ = (
        UniqueConstraint("mission_id", "step_index", name="uq_agent_mission_step"),
    )


class DailySummaryLog(Base):
    """One-row-per-day send audit for daily summary delivery."""
    __tablename__ = "daily_summary_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    summary_date = Column(Date, nullable=False, index=True)
    channel = Column(String(32), nullable=False, default="slack")
    status = Column(String(16), default="running")  # running|success|failed
    slack_ts = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("summary_date", "channel", name="uq_daily_summary_date_channel"),
    )
