from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from f1laps.db import Event, Lap, SessionDriver, SessionRow
from f1laps.ingest import candidate_sessions, store_session_data
from tests.conftest import fake_frames


def test_store_session_data_writes_drivers_and_laps(session_factory, seeded):
    with session_factory() as db:
        sess = db.get(SessionRow, seeded["race"])
        assert sess.status == "ingested"
        assert sess.lap_count == 16
        assert sess.driver_count == 2
        assert sess.total_laps == 8

        ver = db.scalar(select(SessionDriver).where(SessionDriver.driver_number == "1"))
        assert ver.abbreviation == "VER"
        assert ver.team_color == "3671C6"

        lap4 = db.scalar(select(Lap).where(Lap.driver_number == "1", Lap.lap_number == 4))
        assert lap4.pit_in is True and lap4.pit_out is False
        assert lap4.lap_time_ms == 95000
        assert lap4.compound == "MEDIUM"

        lap8 = db.scalar(select(Lap).where(Lap.driver_number == "4", Lap.lap_number == 8))
        assert lap8.lap_time_ms is None and lap8.s1_ms == 29500

        nor6 = db.scalar(select(Lap).where(Lap.driver_number == "4", Lap.lap_number == 6))
        assert nor6.deleted is True


def test_store_session_data_is_idempotent(session_factory, seeded):
    with session_factory() as db:
        sess = db.get(SessionRow, seeded["race"])
        store_session_data(db, sess, fake_frames())
        assert db.scalar(select(Lap).where(Lap.session_id == sess.id).limit(1)) is not None
        n = len(db.scalars(select(Lap).where(Lap.session_id == sess.id)).all())
        assert n == 16


def test_candidate_sessions_only_returns_finished_pending(session_factory, seeded):
    now = datetime(2025, 9, 7, 16, 0)
    with session_factory() as db:
        race = db.get(SessionRow, seeded["race"])
        fp1 = db.get(SessionRow, seeded["fp1"])
        race.start_utc = now - timedelta(hours=5)
        fp1.start_utc = now - timedelta(hours=1)  # still inside the grace window
        db.commit()

        due = candidate_sessions(db, [2025], force=False, now=now)
        assert due == []  # race is ingested, FP1 not finished

        fp1.start_utc = now - timedelta(hours=4)
        db.commit()
        due = candidate_sessions(db, [2025], force=False, now=now)
        assert [s.code for s in due] == ["FP1"]

        due = candidate_sessions(db, [2025], force=True, now=now)
        assert [s.code for s in due] == ["FP1", "R"]
