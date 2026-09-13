"""Scheduled data checks (default: Fri/Sat/Sun at 23:30 in the configured time zone)."""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings, settings
from .refresh import RefreshRunner

log = logging.getLogger(__name__)

JOB_ID = "weekend-data-check"


def build_trigger(cfg: Settings = settings) -> CronTrigger:
    hour, minute = cfg.refresh_time.split(":")
    return CronTrigger(
        day_of_week=cfg.refresh_days,
        hour=int(hour),
        minute=int(minute),
        timezone=ZoneInfo(cfg.refresh_tz),
    )


class RefreshScheduler:
    def __init__(self, runner: RefreshRunner, cfg: Settings = settings):
        self.runner = runner
        self.cfg = cfg
        self.scheduler = BackgroundScheduler(timezone=ZoneInfo(cfg.refresh_tz))

    def start(self) -> None:
        self.scheduler.add_job(
            self._job,
            trigger=build_trigger(self.cfg),
            id=JOB_ID,
            name="Check for new F1 session data",
            coalesce=True,
            max_instances=1,
            misfire_grace_time=6 * 3600,
        )
        self.scheduler.start()
        log.info("Scheduled data check: %s at %s (%s); next run %s",
                 self.cfg.refresh_days, self.cfg.refresh_time, self.cfg.refresh_tz, self.next_run())

    def _job(self) -> None:
        self.runner.run_blocking(trigger="scheduled")

    def next_run(self) -> datetime | None:
        job = self.scheduler.get_job(JOB_ID) if self.scheduler.running else None
        return job.next_run_time if job else None

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
