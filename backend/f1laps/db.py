"""Database models and session factory (SQLite via SQLAlchemy)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class Event(Base):
    """A Grand Prix weekend."""

    __tablename__ = "events"
    __table_args__ = (UniqueConstraint("season", "round", name="uq_event_season_round"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season: Mapped[int] = mapped_column(Integer, index=True)
    round: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String)  # e.g. "Italian Grand Prix"
    official_name: Mapped[str] = mapped_column(String, default="")
    location: Mapped[str] = mapped_column(String, default="")  # e.g. "Monza"
    country: Mapped[str] = mapped_column(String, default="")
    event_format: Mapped[str] = mapped_column(String, default="conventional")
    event_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    sessions: Mapped[list["SessionRow"]] = relationship(
        back_populates="event", cascade="all, delete-orphan", order_by="SessionRow.number"
    )


class SessionRow(Base):
    """One timed session (FP1, Qualifying, Race, ...) of an event."""

    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("event_id", "code", name="uq_session_event_code"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)  # 1..5 order within the weekend
    code: Mapped[str] = mapped_column(String)  # FP1, FP2, FP3, Q, SQ, SS, S, R
    name: Mapped[str] = mapped_column(String)  # FastF1 name, e.g. "Practice 1"
    start_utc: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # pending -> ingested | failed (retried) | unavailable (gave up)
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(String, default="")
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lap_count: Mapped[int] = mapped_column(Integer, default=0)
    driver_count: Mapped[int] = mapped_column(Integer, default=0)
    total_laps: Mapped[int | None] = mapped_column(Integer, nullable=True)  # scheduled race distance

    event: Mapped[Event] = relationship(back_populates="sessions")
    drivers: Mapped[list["SessionDriver"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="SessionDriver.position"
    )
    laps: Mapped[list["Lap"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class SessionDriver(Base):
    __tablename__ = "session_drivers"
    __table_args__ = (UniqueConstraint("session_id", "driver_number", name="uq_driver_session_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    driver_number: Mapped[str] = mapped_column(String)
    abbreviation: Mapped[str] = mapped_column(String)
    full_name: Mapped[str] = mapped_column(String, default="")
    team: Mapped[str] = mapped_column(String, default="")
    team_color: Mapped[str] = mapped_column(String, default="")  # hex without '#'
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)  # classification
    headshot_url: Mapped[str] = mapped_column(String, default="")

    session: Mapped[SessionRow] = relationship(back_populates="drivers")


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (UniqueConstraint("session_id", "driver_number", "lap_number", name="uq_lap"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"), index=True)
    driver_number: Mapped[str] = mapped_column(String)
    lap_number: Mapped[int] = mapped_column(Integer)
    lap_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s1_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s2_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    s3_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stint: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compound: Mapped[str] = mapped_column(String, default="UNKNOWN")
    tyre_life: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fresh_tyre: Mapped[bool] = mapped_column(Boolean, default=False)
    pit_in: Mapped[bool] = mapped_column(Boolean, default=False)
    pit_out: Mapped[bool] = mapped_column(Boolean, default=False)
    track_status: Mapped[str] = mapped_column(String, default="1")
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_reason: Mapped[str] = mapped_column(String, default="")
    is_accurate: Mapped[bool] = mapped_column(Boolean, default=True)
    is_personal_best: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped[SessionRow] = relationship(back_populates="laps")


class RefreshRun(Base):
    """History of scheduled / manual data checks."""

    __tablename__ = "refresh_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String)  # scheduled | manual | startup | cli
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    summary: Mapped[str] = mapped_column(String, default="")


def make_engine(db_path: Path | str):
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        url = f"sqlite:///{db_path}"
    else:
        url = db_path  # allow "sqlite:///:memory:" in tests
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    return engine


def make_session_factory(engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)
