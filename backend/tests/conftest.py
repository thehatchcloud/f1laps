from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlalchemy import create_engine

from f1laps import db as dbmod
from f1laps.db import Event, SessionRow, make_session_factory
from f1laps.ingest import SessionFrames, store_session_data


def _td(seconds: float | None):
    return pd.NaT if seconds is None else pd.Timedelta(seconds=seconds)


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    dbmod.Base.metadata.create_all(engine)
    return make_session_factory(engine)


def fake_frames() -> SessionFrames:
    """A tiny two-driver race: VER (Red Bull) and NOR (McLaren), 8 laps, one stop each."""
    rows = []

    def lap(num, drv, team, n, t, s1, s2, s3, stint, compound, life, pit_in=None, pit_out=None, ts="1", deleted=False):
        rows.append(
            {
                "DriverNumber": num,
                "Driver": drv,
                "Team": team,
                "LapNumber": float(n),
                "LapTime": _td(t),
                "Sector1Time": _td(s1),
                "Sector2Time": _td(s2),
                "Sector3Time": _td(s3),
                "Stint": float(stint),
                "Compound": compound,
                "TyreLife": float(life),
                "FreshTyre": life == 1,
                "PitInTime": _td(pit_in),
                "PitOutTime": _td(pit_out),
                "TrackStatus": ts,
                "Position": float(1 if drv == "VER" else 2),
                "Deleted": deleted,
                "DeletedReason": "track limits" if deleted else "",
                "IsAccurate": True,
                "IsPersonalBest": False,
            }
        )

    # VER: 4 laps on MEDIUM, box lap 4, 4 laps on HARD
    lap("1", "VER", "Red Bull Racing", 1, 92.0, 30.0, 31.0, 31.0, 1, "MEDIUM", 1, pit_out=1.0)
    lap("1", "VER", "Red Bull Racing", 2, 90.5, 29.5, 30.5, 30.5, 1, "MEDIUM", 2)
    lap("1", "VER", "Red Bull Racing", 3, 90.7, 29.6, 30.6, 30.5, 1, "MEDIUM", 3)
    lap("1", "VER", "Red Bull Racing", 4, 95.0, 29.7, 30.7, 34.6, 1, "MEDIUM", 4, pit_in=400.0)
    lap("1", "VER", "Red Bull Racing", 5, 96.0, 35.0, 30.5, 30.5, 2, "HARD", 1, pit_out=410.0)
    lap("1", "VER", "Red Bull Racing", 6, 90.2, 29.4, 30.4, 30.4, 2, "HARD", 2)
    lap("1", "VER", "Red Bull Racing", 7, 90.1, 29.3, 30.4, 30.4, 2, "HARD", 3)
    lap("1", "VER", "Red Bull Racing", 8, 90.0, 29.3, 30.3, 30.4, 2, "HARD", 4)
    # NOR: safety-car lap 3, deleted lap 6
    lap("4", "NOR", "McLaren", 1, 92.5, 30.2, 31.1, 31.2, 1, "MEDIUM", 1, pit_out=2.0)
    lap("4", "NOR", "McLaren", 2, 90.8, 29.6, 30.6, 30.6, 1, "MEDIUM", 2)
    lap("4", "NOR", "McLaren", 3, 110.0, 35.0, 37.0, 38.0, 1, "MEDIUM", 3, ts="4")
    lap("4", "NOR", "McLaren", 4, 90.9, 29.7, 30.6, 30.6, 1, "MEDIUM", 4)
    lap("4", "NOR", "McLaren", 5, 95.5, 29.8, 30.7, 35.0, 1, "MEDIUM", 5, pit_in=450.0)
    lap("4", "NOR", "McLaren", 6, 89.0, 29.0, 30.0, 30.0, 2, "HARD", 1, pit_out=460.0, deleted=True)
    lap("4", "NOR", "McLaren", 7, 90.4, 29.4, 30.5, 30.5, 2, "HARD", 2)
    lap("4", "NOR", "McLaren", 8, None, 29.5, None, None, 2, "HARD", 3)

    laps = pd.DataFrame(rows)
    results = pd.DataFrame(
        [
            {"DriverNumber": "1", "Abbreviation": "VER", "FullName": "Max Verstappen", "TeamName": "Red Bull Racing", "TeamColor": "3671C6", "Position": 1.0, "HeadshotUrl": ""},
            {"DriverNumber": "4", "Abbreviation": "NOR", "FullName": "Lando Norris", "TeamName": "McLaren", "TeamColor": "FF8000", "Position": 2.0, "HeadshotUrl": ""},
        ]
    )
    return SessionFrames(laps=laps, results=results, total_laps=8)


@pytest.fixture()
def seeded(session_factory):
    """Database with one 2025 event and an ingested race session."""
    with session_factory() as db:
        ev = Event(season=2025, round=14, name="Italian Grand Prix", location="Monza", country="Italy")
        db.add(ev)
        db.flush()
        race = SessionRow(event_id=ev.id, number=5, code="R", name="Race")
        fp1 = SessionRow(event_id=ev.id, number=1, code="FP1", name="Practice 1")
        db.add_all([race, fp1])
        db.commit()
        store_session_data(db, race, fake_frames())
        ids = {"event": ev.id, "race": race.id, "fp1": fp1.id}
    return ids


@pytest.fixture()
def client(session_factory, seeded, monkeypatch):
    from f1laps.main import create_app

    app = create_app(session_factory, enable_scheduler=False)
    with TestClient(app) as c:
        c.ids = seeded  # type: ignore[attr-defined]
        yield c
