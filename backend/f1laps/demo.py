"""Synthetic session generator so the UI can be tried without network access.

    f1laps demo-seed

creates a fake 2025 "Demo Grand Prix" race with 20 drivers, realistic-ish
lap-time evolution, pit stops, a safety car period and sector times.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pandas as pd
from sqlalchemy import select

from .db import Event, SessionRow
from .ingest import SessionFrames, TEAM_COLORS, store_session_data

GRID = [
    ("1", "VER", "Max Verstappen", "Red Bull Racing"),
    ("22", "TSU", "Yuki Tsunoda", "Red Bull Racing"),
    ("4", "NOR", "Lando Norris", "McLaren"),
    ("81", "PIA", "Oscar Piastri", "McLaren"),
    ("16", "LEC", "Charles Leclerc", "Ferrari"),
    ("44", "HAM", "Lewis Hamilton", "Ferrari"),
    ("63", "RUS", "George Russell", "Mercedes"),
    ("12", "ANT", "Andrea Kimi Antonelli", "Mercedes"),
    ("14", "ALO", "Fernando Alonso", "Aston Martin"),
    ("18", "STR", "Lance Stroll", "Aston Martin"),
    ("10", "GAS", "Pierre Gasly", "Alpine"),
    ("43", "COL", "Franco Colapinto", "Alpine"),
    ("23", "ALB", "Alexander Albon", "Williams"),
    ("55", "SAI", "Carlos Sainz", "Williams"),
    ("6", "HAD", "Isack Hadjar", "Racing Bulls"),
    ("30", "LAW", "Liam Lawson", "Racing Bulls"),
    ("27", "HUL", "Nico Hulkenberg", "Kick Sauber"),
    ("5", "BOR", "Gabriel Bortoleto", "Kick Sauber"),
    ("31", "OCO", "Esteban Ocon", "Haas F1 Team"),
    ("87", "BEA", "Oliver Bearman", "Haas F1 Team"),
]

COMPOUND_PACE = {"SOFT": -0.4, "MEDIUM": 0.0, "HARD": 0.45}
COMPOUND_DEG = {"SOFT": 0.09, "MEDIUM": 0.05, "HARD": 0.03}


def demo_frames(total_laps: int = 57, seed: int = 7) -> SessionFrames:
    rng = random.Random(seed)
    rows = []
    results = []
    sc_laps = set(range(23, 27))  # safety car on laps 23-26
    base_lap = 83.0  # seconds, quickest car
    for pos, (num, abbr, name, team) in enumerate(GRID, start=1):
        car_pace = base_lap + 0.10 * pos + rng.uniform(-0.15, 0.15)
        strategy = rng.choice([("MEDIUM", 22, "HARD"), ("HARD", 30, "MEDIUM"), ("SOFT", 15, "HARD")])
        stint_no, compound, next_change, life = 1, strategy[0], strategy[1], 1
        fuel_effect = 0.055  # seconds gained per lap as fuel burns
        for lap in range(1, total_laps + 1):
            pit_in = pit_out = None
            if lap == next_change:
                pit_in = float(lap * 90)
            if lap == next_change + 1:
                pit_out = float(lap * 90 + 25)
                stint_no += 1
                compound = strategy[2]
                life = 1
                next_change = 10_000
            t = car_pace + COMPOUND_PACE[compound] + COMPOUND_DEG[compound] * life - fuel_effect * lap
            t += rng.gauss(0, 0.18)
            if lap == 1:
                t += 4.0 + 0.25 * pos  # standing start / traffic
            if pit_in:
                t += 6.0
            if pit_out:
                t += 12.0
            ts = "1"
            if lap in sc_laps:
                t += 25.0
                ts = "4"
            s1 = t * 0.30 + rng.gauss(0, 0.05)
            s2 = t * 0.38 + rng.gauss(0, 0.05)
            s3 = t - s1 - s2
            rows.append(
                {
                    "DriverNumber": num,
                    "Driver": abbr,
                    "Team": team,
                    "LapNumber": float(lap),
                    "LapTime": pd.Timedelta(seconds=round(t, 3)),
                    "Sector1Time": pd.Timedelta(seconds=round(s1, 3)),
                    "Sector2Time": pd.Timedelta(seconds=round(s2, 3)),
                    "Sector3Time": pd.Timedelta(seconds=round(s3, 3)),
                    "Stint": float(stint_no),
                    "Compound": compound,
                    "TyreLife": float(life),
                    "FreshTyre": life == 1,
                    "PitInTime": pd.Timedelta(seconds=pit_in) if pit_in else pd.NaT,
                    "PitOutTime": pd.Timedelta(seconds=pit_out) if pit_out else pd.NaT,
                    "TrackStatus": ts,
                    "Position": float(pos),
                    "Deleted": False,
                    "DeletedReason": "",
                    "IsAccurate": True,
                    "IsPersonalBest": False,
                }
            )
            life += 1
        results.append(
            {
                "DriverNumber": num,
                "Abbreviation": abbr,
                "FullName": name,
                "TeamName": team,
                "TeamColor": TEAM_COLORS.get(team, "808080"),
                "Position": float(pos),
                "HeadshotUrl": "",
            }
        )
    return SessionFrames(laps=pd.DataFrame(rows), results=pd.DataFrame(results), total_laps=total_laps)


def seed_demo(session_factory, season: int = 2025) -> int:
    with session_factory() as db:
        ev = db.scalar(select(Event).where(Event.season == season, Event.round == 99))
        if ev is None:
            ev = Event(season=season, round=99, name="Demo Grand Prix", location="Demo Park", country="Nowhere",
                       event_format="conventional", event_date=datetime(season, 6, 1))
            db.add(ev)
            db.flush()
        start = datetime(season, 6, 1, 13, 0)
        for n, (code, name) in enumerate([("FP1", "Practice 1"), ("Q", "Qualifying"), ("R", "Race")], start=1):
            sess = db.scalar(select(SessionRow).where(SessionRow.event_id == ev.id, SessionRow.code == code))
            if sess is None:
                sess = SessionRow(event_id=ev.id, number=n, code=code, name=name)
                db.add(sess)
            sess.start_utc = start - timedelta(days=3 - n)
            db.flush()
            if code == "R":
                store_session_data(db, sess, demo_frames())
        db.commit()
        return ev.id
