from f1laps.demo import seed_demo


def test_demo_seed_and_api(session_factory):
    from fastapi.testclient import TestClient
    from f1laps.main import create_app

    seed_demo(session_factory)
    with TestClient(create_app(session_factory, enable_scheduler=False)) as c:
        events = c.get("/api/seasons/2025/events").json()
        demo = next(e for e in events if e["round"] == 99)
        race = next(s for s in demo["sessions"] if s["code"] == "R")
        assert race["status"] == "ingested" and race["lap_count"] == 20 * 57
        detail = c.get(f"/api/sessions/{race['id']}").json()
        assert len(detail["drivers"]) == 20
        assert all(len(s["stats"]["stints"]) == 2 for s in detail["drivers"])
