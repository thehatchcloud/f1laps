from datetime import timedelta

from f1laps.scheduler import build_trigger
from f1laps.config import Settings


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_seasons_and_events(client):
    seasons = client.get("/api/seasons").json()
    assert {"season": 2025, "events": 1} in seasons

    events = client.get("/api/seasons/2025/events").json()
    assert len(events) == 1
    ev = events[0]
    assert ev["name"] == "Italian Grand Prix" and ev["location"] == "Monza"
    codes = {s["code"]: s for s in ev["sessions"]}
    assert codes["R"]["status"] == "ingested" and codes["R"]["lap_count"] == 16
    assert codes["FP1"]["status"] == "pending"


def test_session_detail(client):
    data = client.get(f"/api/sessions/{client.ids['race']}").json()
    assert data["session"]["code"] == "R"
    assert data["event"]["location"] == "Monza"
    assert data["fastest_driver"] == "1"
    assert data["fastest_lap_ms"] == 90000

    drivers = {d["abbreviation"]: d for d in data["drivers"]}
    assert drivers["VER"]["team_color"] == "#3671C6"
    assert drivers["VER"]["team"] == "Red Bull Racing"
    assert drivers["NOR"]["stats"]["gap_to_fastest_ms"] == 400
    assert [d["abbreviation"] for d in data["drivers"]] == ["VER", "NOR"]

    ver_laps = data["laps"]["1"]
    assert len(ver_laps) == 8
    assert ver_laps[3]["pit_in"] is True
    assert ver_laps[4]["compound"] == "HARD"
    stints = drivers["VER"]["stats"]["stints"]
    assert [s["compound"] for s in stints] == ["MEDIUM", "HARD"]
    assert stints[1]["start_lap"] == 5


def test_session_not_found(client):
    assert client.get("/api/sessions/9999").status_code == 404


def test_refresh_status_and_trigger(client, monkeypatch):
    status = client.get("/api/refresh/status").json()
    assert status["running"] is False
    assert status["schedule"]["days"] == "fri,sat,sun"

    calls = {}

    def fake_run_refresh(factory, **kwargs):
        calls.update(kwargs)
        from f1laps.ingest import RefreshResult, utcnow
        r = RefreshResult(trigger=kwargs["trigger"], started_at=utcnow())
        r.finished_at = utcnow()
        return r

    monkeypatch.setattr("f1laps.refresh.run_refresh", fake_run_refresh)
    resp = client.post("/api/refresh", json={"season": 2025})
    assert resp.status_code == 202
    assert resp.json()["started"] is True
    client.app.state.runner._thread.join(timeout=5)
    assert calls["trigger"] == "manual" and calls["seasons"] == [2025]
    status = client.get("/api/refresh/status").json()
    assert status["running"] is False and status["last_run"]["ok"] is True


def test_cron_trigger_from_settings():
    cfg = Settings(refresh_days="fri,sat,sun", refresh_time="23:30", refresh_tz="America/New_York")
    trig = build_trigger(cfg)
    text = str(trig)
    assert "day_of_week='fri,sat,sun'" in text and "hour='23'" in text and "minute='30'" in text
