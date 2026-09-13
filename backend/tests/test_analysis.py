from f1laps.analysis import driver_summary, is_clean, session_summary


def _lap(n, t, **kw):
    base = {
        "lap_number": n, "lap_time_ms": t, "s1_ms": None, "s2_ms": None, "s3_ms": None,
        "stint": 1, "compound": "MEDIUM", "pit_in": False, "pit_out": False,
        "track_status": "1", "deleted": False, "is_accurate": True,
    }
    base.update(kw)
    return base


def test_is_clean_excludes_pit_and_flag_laps():
    assert is_clean(_lap(1, 90000))
    assert not is_clean(_lap(1, 90000, pit_in=True))
    assert not is_clean(_lap(1, 90000, pit_out=True))
    assert not is_clean(_lap(1, 90000, track_status="4"))
    assert not is_clean(_lap(1, None))


def test_driver_summary_basic_stats():
    laps = [
        _lap(1, 95000, pit_out=True),
        _lap(2, 90500, s1_ms=29500, s2_ms=30500, s3_ms=30500),
        _lap(3, 90300, s1_ms=29400, s2_ms=30400, s3_ms=30500),
        _lap(4, 90100, s1_ms=29300, s2_ms=30300, s3_ms=30500),
        _lap(5, 89900, s1_ms=29200, s2_ms=30300, s3_ms=30400),
        _lap(6, 89700, s1_ms=29100, s2_ms=30200, s3_ms=30400),
        _lap(7, 89500, s1_ms=29000, s2_ms=30100, s3_ms=30400),
        _lap(8, 88000, deleted=True),  # deleted laps never count as best
        _lap(9, 120000),  # cool-down lap, outside the 107% window
    ]
    s = driver_summary(laps)
    assert s["best_lap_ms"] == 89500 and s["best_lap_number"] == 7
    assert s["ideal_lap_ms"] == 29000 + 30100 + 30400
    assert s["avg_ms"] == 90000
    assert s["trend_ms"] < 0  # got faster over the run
    assert s["laps_clean"] == 8
    assert len(s["stints"]) == 1
    st = s["stints"][0]
    assert st["compound"] == "MEDIUM" and st["laps"] == 9
    assert st["deg_ms_per_lap"] < 0


def test_session_summary_gap_to_fastest():
    summary = session_summary({"1": [_lap(1, 90000)], "4": [_lap(1, 90750)]})
    assert summary["fastest_driver"] == "1"
    assert summary["drivers"]["4"]["gap_to_fastest_ms"] == 750
    assert summary["drivers"]["1"]["gap_to_fastest_ms"] == 0
