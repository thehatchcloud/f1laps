"""Fetch F1 timing data with FastF1 and store it in the database.

The FastF1-specific parts (schedule + session download) are isolated in
``sync_schedule`` and ``fetch_session_frames`` so that ``store_session_data``
can be tested with plain pandas DataFrames.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Event, Lap, RefreshRun, SessionDriver, SessionRow

log = logging.getLogger(__name__)

# FastF1 session name -> short code used throughout the app
SESSION_CODES: dict[str, str] = {
    "Practice 1": "FP1",
    "Practice 2": "FP2",
    "Practice 3": "FP3",
    "Qualifying": "Q",
    "Sprint Qualifying": "SQ",
    "Sprint Shootout": "SQ",
    "Sprint": "S",
    "Race": "R",
}

# Fallback team colours (hex without '#') when FastF1 does not supply one.
TEAM_COLORS: dict[str, str] = {
    "Red Bull Racing": "3671C6",
    "Ferrari": "E8002D",
    "Mercedes": "27F4D2",
    "McLaren": "FF8000",
    "Aston Martin": "229971",
    "Alpine": "FF87BC",
    "Williams": "64C4FF",
    "RB": "6692FF",
    "Racing Bulls": "6692FF",
    "Kick Sauber": "52E252",
    "Audi": "52E252",
    "Haas F1 Team": "B6BABD",
    "Cadillac": "1F2A44",
}

_fastf1_ready = False


def _fastf1():
    """Import FastF1 lazily and configure its cache once."""
    global _fastf1_ready
    import fastf1

    if not _fastf1_ready:
        settings.fastf1_cache_dir.mkdir(parents=True, exist_ok=True)
        fastf1.Cache.enable_cache(str(settings.fastf1_cache_dir))
        fastf1.set_log_level("WARNING")
        _fastf1_ready = True
    return fastf1


# --------------------------------------------------------------------------- helpers


def _td_ms(value: Any) -> int | None:
    """pandas Timedelta / NaT -> integer milliseconds (or None)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timedelta):
        return int(round(value.total_seconds() * 1000))
    if isinstance(value, timedelta):
        return int(round(value.total_seconds() * 1000))
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return int(round(value * 1000))
    return None


def _int(value: Any) -> int | None:
    try:
        if value is None or pd.isna(value):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool(value: Any) -> bool:
    try:
        if value is None or pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _str(value: Any, default: str = "") -> str:
    try:
        if value is None or pd.isna(value):
            return default
    except (TypeError, ValueError):
        pass
    return str(value)


def _naive_utc(value: Any) -> datetime | None:
    """pandas Timestamp / datetime -> naive UTC datetime (SQLite friendly)."""
    try:
        if value is None or pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- schedule


def sync_schedule(db: Session, season: int) -> int:
    """Upsert the events and sessions of a season from the FastF1 schedule.

    Returns the number of sessions now known for the season.
    """
    fastf1 = _fastf1()
    schedule = fastf1.get_event_schedule(season, include_testing=False)
    count = 0
    for _, row in schedule.iterrows():
        rnd = _int(row.get("RoundNumber"))
        if not rnd:
            continue
        ev = db.scalar(select(Event).where(Event.season == season, Event.round == rnd))
        if ev is None:
            ev = Event(season=season, round=rnd, name=_str(row.get("EventName")))
            db.add(ev)
        ev.name = _str(row.get("EventName"), ev.name)
        ev.official_name = _str(row.get("OfficialEventName"))
        ev.location = _str(row.get("Location"))
        ev.country = _str(row.get("Country"))
        ev.event_format = _str(row.get("EventFormat"), "conventional")
        ev.event_date = _naive_utc(row.get("EventDate"))
        db.flush()

        for n in range(1, 6):
            name = _str(row.get(f"Session{n}"))
            if not name or name == "None":
                continue
            code = SESSION_CODES.get(name)
            if code is None:
                log.warning("Unknown session name %r in %s %s", name, season, ev.name)
                continue
            sess = db.scalar(
                select(SessionRow).where(SessionRow.event_id == ev.id, SessionRow.code == code)
            )
            if sess is None:
                sess = SessionRow(event_id=ev.id, number=n, code=code, name=name)
                db.add(sess)
            sess.number = n
            sess.name = name
            start = _naive_utc(row.get(f"Session{n}DateUtc"))
            if start is None:
                start = _naive_utc(row.get(f"Session{n}Date"))
            sess.start_utc = start
            count += 1
    db.commit()
    return count


# --------------------------------------------------------------------------- session data


@dataclass
class SessionFrames:
    laps: pd.DataFrame
    results: pd.DataFrame | None
    total_laps: int | None = None


def fetch_session_frames(season: int, rnd: int, session_name: str) -> SessionFrames:
    """Download a session with FastF1 (laps + results only, no telemetry)."""
    fastf1 = _fastf1()
    session = fastf1.get_session(season, rnd, session_name)
    session.load(laps=True, telemetry=False, weather=False, messages=True)
    laps = session.laps
    if laps is None or len(laps) == 0:
        raise RuntimeError("no lap data available yet")
    results = None
    try:
        results = session.results
    except Exception:  # pragma: no cover - defensive
        results = None
    total_laps = None
    try:
        total_laps = _int(getattr(session, "total_laps", None))
    except Exception:  # pragma: no cover
        total_laps = None
    return SessionFrames(laps=pd.DataFrame(laps), results=results, total_laps=total_laps)


def store_session_data(db: Session, sess: SessionRow, frames: SessionFrames) -> tuple[int, int]:
    """Replace the drivers and laps of ``sess`` with the content of ``frames``.

    Returns (driver_count, lap_count).
    """
    laps = frames.laps
    results = frames.results

    # ---- drivers
    teams_by_number: dict[str, str] = {}
    abbr_by_number: dict[str, str] = {}
    if "DriverNumber" in laps.columns:
        for num, grp in laps.groupby("DriverNumber", sort=False):
            num = _str(num)
            if "Team" in grp.columns:
                teams_by_number[num] = _str(grp["Team"].dropna().iloc[0]) if grp["Team"].notna().any() else ""
            if "Driver" in grp.columns:
                abbr_by_number[num] = _str(grp["Driver"].dropna().iloc[0]) if grp["Driver"].notna().any() else num

    drivers: dict[str, SessionDriver] = {}
    if results is not None and len(results) > 0:
        for _, r in results.iterrows():
            num = _str(r.get("DriverNumber"))
            if not num:
                continue
            team = _str(r.get("TeamName")) or teams_by_number.get(num, "")
            color = _str(r.get("TeamColor")).lstrip("#") or TEAM_COLORS.get(team, "")
            drivers[num] = SessionDriver(
                driver_number=num,
                abbreviation=_str(r.get("Abbreviation")) or abbr_by_number.get(num, num),
                full_name=_str(r.get("FullName")) or _str(r.get("BroadcastName")),
                team=team,
                team_color=color,
                position=_int(r.get("Position")),
                headshot_url=_str(r.get("HeadshotUrl")),
            )
    # Drivers that appear in laps but not in results (happens in practice sessions)
    for num, abbr in abbr_by_number.items():
        if num not in drivers:
            team = teams_by_number.get(num, "")
            drivers[num] = SessionDriver(
                driver_number=num,
                abbreviation=abbr,
                full_name="",
                team=team,
                team_color=TEAM_COLORS.get(team, ""),
                position=None,
            )
    for d in drivers.values():
        if not d.team_color:
            d.team_color = TEAM_COLORS.get(d.team, "808080")

    # ---- laps
    lap_rows: list[Lap] = []
    for _, r in laps.iterrows():
        num = _str(r.get("DriverNumber"))
        lap_no = _int(r.get("LapNumber"))
        if not num or lap_no is None:
            continue
        lap_rows.append(
            Lap(
                driver_number=num,
                lap_number=lap_no,
                lap_time_ms=_td_ms(r.get("LapTime")),
                s1_ms=_td_ms(r.get("Sector1Time")),
                s2_ms=_td_ms(r.get("Sector2Time")),
                s3_ms=_td_ms(r.get("Sector3Time")),
                stint=_int(r.get("Stint")),
                compound=_str(r.get("Compound"), "UNKNOWN") or "UNKNOWN",
                tyre_life=_int(r.get("TyreLife")),
                fresh_tyre=_bool(r.get("FreshTyre")),
                pit_in=not pd.isna(r.get("PitInTime")) if "PitInTime" in laps.columns else False,
                pit_out=not pd.isna(r.get("PitOutTime")) if "PitOutTime" in laps.columns else False,
                track_status=_str(r.get("TrackStatus"), "1") or "1",
                position=_int(r.get("Position")),
                deleted=_bool(r.get("Deleted")),
                deleted_reason=_str(r.get("DeletedReason")),
                is_accurate=_bool(r.get("IsAccurate")) if "IsAccurate" in laps.columns else True,
                is_personal_best=_bool(r.get("IsPersonalBest")),
            )
        )

    # Replace existing content atomically
    sess.drivers.clear()
    sess.laps.clear()
    db.flush()
    for d in drivers.values():
        d.session_id = sess.id
        db.add(d)
    for lap in lap_rows:
        lap.session_id = sess.id
        db.add(lap)

    sess.status = "ingested"
    sess.ingested_at = utcnow()
    sess.last_error = ""
    sess.lap_count = len(lap_rows)
    sess.driver_count = len(drivers)
    if frames.total_laps:
        sess.total_laps = frames.total_laps
    db.commit()
    return len(drivers), len(lap_rows)


def ingest_session(db: Session, sess: SessionRow) -> tuple[int, int]:
    """Download and store one session. Raises on failure (status is updated either way)."""
    ev = sess.event
    sess.attempts = (sess.attempts or 0) + 1
    sess.last_attempt_at = utcnow()
    db.commit()
    try:
        frames = fetch_session_frames(ev.season, ev.round, sess.name)
        return store_session_data(db, sess, frames)
    except Exception as exc:
        db.rollback()
        sess = db.get(SessionRow, sess.id)  # re-attach after rollback
        sess.last_error = f"{type(exc).__name__}: {exc}"[:500]
        sess.status = "unavailable" if sess.attempts >= settings.max_fetch_attempts else "failed"
        db.commit()
        raise


# --------------------------------------------------------------------------- refresh


@dataclass
class RefreshResult:
    trigger: str
    started_at: datetime
    finished_at: datetime | None = None
    schedule_errors: list[str] = field(default_factory=list)
    ingested: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: int = 0

    @property
    def ok(self) -> bool:
        return not self.schedule_errors and not self.failed

    def summary(self) -> str:
        parts = [f"{len(self.ingested)} session(s) ingested"]
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        if self.schedule_errors:
            parts.append(f"{len(self.schedule_errors)} schedule error(s)")
        return ", ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trigger": self.trigger,
            "started_at": self.started_at.isoformat() + "Z",
            "finished_at": self.finished_at.isoformat() + "Z" if self.finished_at else None,
            "ok": self.ok,
            "summary": self.summary(),
            "ingested": self.ingested,
            "failed": self.failed,
            "schedule_errors": self.schedule_errors,
            "skipped": self.skipped,
        }


def candidate_sessions(db: Session, seasons: list[int], *, force: bool, now: datetime | None = None) -> list[SessionRow]:
    """Sessions that have finished but are not stored yet (or all, when forced)."""
    now = now or utcnow()
    grace = timedelta(minutes=settings.session_grace_minutes)
    stmt = (
        select(SessionRow)
        .join(Event)
        .where(Event.season.in_(seasons))
        .order_by(Event.season, Event.round, SessionRow.number)
    )
    out: list[SessionRow] = []
    for sess in db.scalars(stmt):
        if sess.start_utc is None or sess.start_utc + grace > now:
            continue  # not finished yet (or unknown start)
        if force:
            out.append(sess)
        elif sess.status in ("pending", "failed"):
            out.append(sess)
    return out


def run_refresh(
    session_factory,
    *,
    trigger: str,
    seasons: list[int] | None = None,
    force: bool = False,
    session_ids: list[int] | None = None,
    progress: Callable[[str], None] | None = None,
) -> RefreshResult:
    """Sync schedules and ingest every session that is due. Safe to call repeatedly."""
    seasons = seasons or settings.season_list
    result = RefreshResult(trigger=trigger, started_at=utcnow())
    report = progress or (lambda msg: None)

    with session_factory() as db:
        run = RefreshRun(trigger=trigger, started_at=result.started_at)
        db.add(run)
        db.commit()
        run_id = run.id

    with session_factory() as db:
        if session_ids is None:
            for season in seasons:
                report(f"Syncing {season} schedule")
                try:
                    sync_schedule(db, season)
                except Exception as exc:
                    log.warning("Schedule sync failed for %s: %s", season, exc)
                    result.schedule_errors.append(f"{season}: {type(exc).__name__}: {exc}"[:300])
            targets = candidate_sessions(db, seasons, force=force)
        else:
            targets = [s for sid in session_ids if (s := db.get(SessionRow, sid)) is not None]

        for sess in targets:
            label = f"{sess.event.season} {sess.event.name} {sess.code}"
            report(f"Fetching {label}")
            try:
                ingest_session(db, sess)
                result.ingested.append(label)
                log.info("Ingested %s (%d laps)", label, sess.lap_count)
            except Exception as exc:
                result.failed.append(f"{label}: {type(exc).__name__}: {exc}"[:300])
                log.warning("Failed to ingest %s: %s", label, exc)

        result.finished_at = utcnow()
        run = db.get(RefreshRun, run_id)
        run.finished_at = result.finished_at
        run.ok = result.ok
        run.summary = result.summary()
        db.commit()
    return result
