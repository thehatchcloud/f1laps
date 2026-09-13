"""Command line helpers: `f1laps refresh`, `f1laps sync-schedule`, `f1laps serve`."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import settings
from .db import make_engine, make_session_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="f1laps")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ref = sub.add_parser("refresh", help="fetch every finished session that is not stored yet")
    p_ref.add_argument("--season", type=int, action="append", help="season(s) to check (default: configured)")
    p_ref.add_argument("--force", action="store_true", help="re-download sessions that are already stored")

    p_sync = sub.add_parser("sync-schedule", help="only update the event/session calendar")
    p_sync.add_argument("--season", type=int, action="append")

    sub.add_parser("demo-seed", help="insert a synthetic 'Demo Grand Prix' race for trying the UI offline")

    p_serve = sub.add_parser("serve", help="run the web server")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)

    args = parser.parse_args(argv)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("f1laps.main:app", host=args.host, port=args.port, log_level=settings.log_level.lower())
        return 0

    factory = make_session_factory(make_engine(settings.db_path))
    seasons = getattr(args, "season", None) or settings.season_list

    if args.cmd == "sync-schedule":
        from .ingest import sync_schedule

        with factory() as db:
            for season in seasons:
                n = sync_schedule(db, season)
                print(f"{season}: {n} sessions in calendar")
        return 0

    if args.cmd == "demo-seed":
        from .demo import seed_demo

        seed_demo(factory)
        print("Demo Grand Prix seeded (season 2025, round 99)")
        return 0

    if args.cmd == "refresh":
        from .ingest import run_refresh

        result = run_refresh(factory, trigger="cli", seasons=seasons, force=args.force, progress=print)
        print(result.summary())
        for f in result.failed + result.schedule_errors:
            print("  !", f)
        return 0 if result.ok else 1

    return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
