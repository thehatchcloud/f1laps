"""FastAPI application: JSON API under /api plus the built frontend at /."""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from . import __version__
from .analysis import session_summary
from .config import settings
from .db import Event, Lap, RefreshRun, SessionDriver, SessionRow, make_engine, make_session_factory
from .refresh import RefreshRunner
from .scheduler import RefreshScheduler

log = logging.getLogger(__name__)

SESSION_LABELS = {
    "FP1": "Practice 1",
    "FP2": "Practice 2",
    "FP3": "Practice 3",
    "Q": "Qualifying",
    "SQ": "Sprint Qualifying",
    "S": "Sprint",
    "R": "Race",
}


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() + "Z" if dt else None


class RefreshRequest(BaseModel):
    season: int | None = None
    session_id: int | None = None
    force: bool = False


def create_app(session_factory=None, *, enable_scheduler: bool | None = None) -> FastAPI:
    if session_factory is None:
        session_factory = make_session_factory(make_engine(settings.db_path))
    if enable_scheduler is None:
        enable_scheduler = settings.scheduler_enabled

    runner = RefreshRunner(session_factory)
    scheduler = RefreshScheduler(runner) if enable_scheduler else None

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if scheduler:
            scheduler.start()
        if settings.refresh_on_startup and enable_scheduler:
            # Delay a little so the server is responsive immediately after a deploy.
            threading.Timer(15.0, lambda: runner.start(trigger="startup")).start()
        yield
        if scheduler:
            scheduler.shutdown()

    app = FastAPI(title="f1laps", version=__version__, lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.runner = runner
    app.state.scheduler = scheduler

    # ------------------------------------------------------------------ meta

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__}

    # ------------------------------------------------------------------ calendar

    @app.get("/api/seasons")
    def seasons() -> list[dict[str, Any]]:
        with session_factory() as db:
            rows = db.execute(
                select(Event.season, func.count(Event.id)).group_by(Event.season).order_by(Event.season.desc())
            ).all()
            known = {s: n for s, n in rows}
        for s in settings.season_list:
            known.setdefault(s, 0)
        return [{"season": s, "events": n} for s, n in sorted(known.items(), reverse=True)]

    @app.get("/api/seasons/{season}/events")
    def events(season: int) -> list[dict[str, Any]]:
        with session_factory() as db:
            evs = db.scalars(
                select(Event).where(Event.season == season).options(selectinload(Event.sessions)).order_by(Event.round)
            ).all()
            return [_event_dict(ev) for ev in evs]

    # ------------------------------------------------------------------ session data

    @app.get("/api/sessions/{session_id}")
    def session_detail(session_id: int) -> dict[str, Any]:
        with session_factory() as db:
            sess = db.get(SessionRow, session_id, options=[selectinload(SessionRow.event)])
            if sess is None:
                raise HTTPException(404, "session not found")
            drivers = db.scalars(
                select(SessionDriver).where(SessionDriver.session_id == session_id)
            ).all()
            laps = db.scalars(
                select(Lap).where(Lap.session_id == session_id).order_by(Lap.driver_number, Lap.lap_number)
            ).all()

        laps_by_driver: dict[str, list[dict[str, Any]]] = {}
        for lap in laps:
            laps_by_driver.setdefault(lap.driver_number, []).append(_lap_dict(lap))
        summary = session_summary(laps_by_driver)

        driver_list = []
        for d in drivers:
            stats = summary["drivers"].get(d.driver_number, {})
            driver_list.append(
                {
                    "number": d.driver_number,
                    "abbreviation": d.abbreviation,
                    "full_name": d.full_name,
                    "team": d.team,
                    "team_color": f"#{d.team_color}" if d.team_color else "#808080",
                    "position": d.position,
                    "headshot_url": d.headshot_url,
                    "stats": stats,
                }
            )
        # Order: classification, then best lap
        driver_list.sort(
            key=lambda d: (
                d["position"] is None,
                d["position"] or 0,
                d["stats"].get("best_lap_ms") is None,
                d["stats"].get("best_lap_ms") or 0,
            )
        )

        return {
            "session": _session_dict(sess),
            "event": _event_dict(sess.event, with_sessions=False),
            "fastest_lap_ms": summary["fastest_lap_ms"],
            "fastest_driver": summary["fastest_driver"],
            "drivers": driver_list,
            "laps": {num: ls for num, ls in laps_by_driver.items()},
        }

    # ------------------------------------------------------------------ refresh

    @app.post("/api/refresh", status_code=202)
    def refresh(req: RefreshRequest | None = None) -> dict[str, Any]:
        req = req or RefreshRequest()
        started = runner.start(
            trigger="manual",
            seasons=[req.season] if req.season else None,
            force=req.force,
            session_ids=[req.session_id] if req.session_id else None,
        )
        return {"started": started, **runner.status()}

    @app.get("/api/refresh/status")
    def refresh_status() -> dict[str, Any]:
        with session_factory() as db:
            last = db.scalars(select(RefreshRun).order_by(RefreshRun.started_at.desc()).limit(1)).first()
        status = runner.status()
        status["next_scheduled"] = _iso_aware(scheduler.next_run()) if scheduler else None
        status["schedule"] = {
            "days": settings.refresh_days,
            "time": settings.refresh_time,
            "timezone": settings.refresh_tz,
            "enabled": bool(scheduler),
        }
        if status["last_run"] is None and last is not None:
            status["last_run"] = {
                "trigger": last.trigger,
                "started_at": _iso(last.started_at),
                "finished_at": _iso(last.finished_at),
                "ok": last.ok,
                "summary": last.summary,
                "ingested": [],
                "failed": [],
                "schedule_errors": [],
            }
        return status

    # ------------------------------------------------------------------ frontend

    static_dir = settings.static_dir
    if static_dir.is_dir():
        assets = static_dir / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = static_dir / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


def _iso_aware(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _session_dict(s: SessionRow) -> dict[str, Any]:
    return {
        "id": s.id,
        "code": s.code,
        "name": SESSION_LABELS.get(s.code, s.name),
        "number": s.number,
        "start_utc": _iso(s.start_utc),
        "status": s.status,
        "ingested_at": _iso(s.ingested_at),
        "lap_count": s.lap_count,
        "driver_count": s.driver_count,
        "total_laps": s.total_laps,
        "last_error": s.last_error if s.status in ("failed", "unavailable") else "",
    }


def _event_dict(ev: Event, with_sessions: bool = True) -> dict[str, Any]:
    d = {
        "id": ev.id,
        "season": ev.season,
        "round": ev.round,
        "name": ev.name,
        "official_name": ev.official_name,
        "location": ev.location,
        "country": ev.country,
        "format": ev.event_format,
        "date": _iso(ev.event_date),
    }
    if with_sessions:
        d["sessions"] = [_session_dict(s) for s in sorted(ev.sessions, key=lambda s: s.number)]
    return d


def _lap_dict(lap: Lap) -> dict[str, Any]:
    return {
        "lap_number": lap.lap_number,
        "lap_time_ms": lap.lap_time_ms,
        "s1_ms": lap.s1_ms,
        "s2_ms": lap.s2_ms,
        "s3_ms": lap.s3_ms,
        "stint": lap.stint,
        "compound": lap.compound,
        "tyre_life": lap.tyre_life,
        "fresh_tyre": lap.fresh_tyre,
        "pit_in": lap.pit_in,
        "pit_out": lap.pit_out,
        "track_status": lap.track_status,
        "position": lap.position,
        "deleted": lap.deleted,
        "deleted_reason": lap.deleted_reason,
        "is_accurate": lap.is_accurate,
        "is_personal_best": lap.is_personal_best,
    }


app = create_app()
