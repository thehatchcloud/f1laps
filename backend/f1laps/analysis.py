"""Pure-Python pace statistics computed from stored laps."""

from __future__ import annotations

from statistics import mean, median
from typing import Any

# Laps slower than this fraction of the driver's best "clean" lap are treated as
# non-representative (cool-down laps, traffic, aborted laps) for the averages.
REPRESENTATIVE_THRESHOLD = 1.07


def is_green(track_status: str | None) -> bool:
    """True when the whole lap was run under green-flag conditions."""
    return (track_status or "1") == "1"


def is_clean(lap: dict[str, Any]) -> bool:
    return (
        lap.get("lap_time_ms") is not None
        and not lap.get("pit_in")
        and not lap.get("pit_out")
        and is_green(lap.get("track_status"))
        and lap.get("is_accurate", True)
    )


def _slope(points: list[tuple[float, float]]) -> float | None:
    """Least-squares slope (y per x) of a list of points; None with < 4 points."""
    if len(points) < 4:
        return None
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    sxx = sum((p[0] - mx) ** 2 for p in points)
    if sxx == 0:
        return None
    sxy = sum((p[0] - mx) * (p[1] - my) for p in points)
    return sxy / sxx


def driver_summary(laps: list[dict[str, Any]]) -> dict[str, Any]:
    """Summary statistics for one driver's laps (dicts as produced by the API)."""
    laps = sorted(laps, key=lambda l: l["lap_number"])
    clean = [l for l in laps if is_clean(l)]
    timed = [l for l in laps if l.get("lap_time_ms") is not None]
    valid_clean = [l for l in clean if not l.get("deleted")]

    best_lap = min(valid_clean, key=lambda l: l["lap_time_ms"]) if valid_clean else None
    best_ms = best_lap["lap_time_ms"] if best_lap else None

    rep = [l for l in valid_clean if best_ms and l["lap_time_ms"] <= best_ms * REPRESENTATIVE_THRESHOLD]
    rep_times = [l["lap_time_ms"] for l in rep]

    def best_sector(key: str) -> int | None:
        vals = [l[key] for l in laps if l.get(key) is not None and not l.get("deleted")]
        return min(vals) if vals else None

    s1, s2, s3 = best_sector("s1_ms"), best_sector("s2_ms"), best_sector("s3_ms")
    ideal = s1 + s2 + s3 if None not in (s1, s2, s3) else None

    # Stints
    stints: list[dict[str, Any]] = []
    by_stint: dict[int, list[dict[str, Any]]] = {}
    for l in laps:
        st = l.get("stint")
        if st is None:
            continue
        by_stint.setdefault(int(st), []).append(l)
    for st, st_laps in sorted(by_stint.items()):
        st_rep = [l for l in st_laps if l in rep]
        pts = [(float(l["lap_number"]), float(l["lap_time_ms"])) for l in st_rep]
        compounds = [l.get("compound") for l in st_laps if l.get("compound") and l.get("compound") != "UNKNOWN"]
        stints.append(
            {
                "stint": st,
                "compound": compounds[0] if compounds else "UNKNOWN",
                "start_lap": st_laps[0]["lap_number"],
                "end_lap": st_laps[-1]["lap_number"],
                "laps": len(st_laps),
                "avg_ms": int(round(mean([p[1] for p in pts]))) if pts else None,
                "deg_ms_per_lap": (round(s, 1) if (s := _slope(pts)) is not None else None),
            }
        )

    # Trend: second half of representative laps vs first half (negative = got faster)
    trend = None
    if len(rep_times) >= 6:
        half = len(rep_times) // 2
        trend = int(round(mean(rep_times[half:]) - mean(rep_times[:half])))

    return {
        "laps_total": len(laps),
        "laps_timed": len(timed),
        "laps_clean": len(clean),
        "best_lap_ms": best_ms,
        "best_lap_number": best_lap["lap_number"] if best_lap else None,
        "avg_ms": int(round(mean(rep_times))) if rep_times else None,
        "median_ms": int(round(median(rep_times))) if rep_times else None,
        "best_s1_ms": s1,
        "best_s2_ms": s2,
        "best_s3_ms": s3,
        "ideal_lap_ms": ideal,
        "trend_ms": trend,
        "stints": stints,
    }


def session_summary(laps_by_driver: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    per_driver = {num: driver_summary(laps) for num, laps in laps_by_driver.items()}
    bests = [(s["best_lap_ms"], num) for num, s in per_driver.items() if s["best_lap_ms"] is not None]
    fastest_ms, fastest_num = (min(bests) if bests else (None, None))
    for num, s in per_driver.items():
        s["gap_to_fastest_ms"] = (
            s["best_lap_ms"] - fastest_ms if fastest_ms is not None and s["best_lap_ms"] is not None else None
        )
    return {"fastest_lap_ms": fastest_ms, "fastest_driver": fastest_num, "drivers": per_driver}
