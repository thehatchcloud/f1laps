"""Runs data refreshes in a background thread and exposes their status."""

from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Any

from .ingest import RefreshResult, run_refresh, utcnow

log = logging.getLogger(__name__)


class RefreshRunner:
    def __init__(self, session_factory):
        self._session_factory = session_factory
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.running: bool = False
        self.current_trigger: str | None = None
        self.current_step: str | None = None
        self.started_at: datetime | None = None
        self.last_result: RefreshResult | None = None

    def start(self, *, trigger: str, seasons=None, force: bool = False, session_ids=None) -> bool:
        """Start a refresh; returns False if one is already running."""
        with self._lock:
            if self.running:
                return False
            self.running = True
            self.current_trigger = trigger
            self.current_step = "starting"
            self.started_at = utcnow()

        def work():
            try:
                self.last_result = run_refresh(
                    self._session_factory,
                    trigger=trigger,
                    seasons=seasons,
                    force=force,
                    session_ids=session_ids,
                    progress=self._progress,
                )
            except Exception as exc:  # pragma: no cover - defensive
                log.exception("Refresh crashed")
                res = RefreshResult(trigger=trigger, started_at=self.started_at or utcnow())
                res.finished_at = utcnow()
                res.schedule_errors.append(f"{type(exc).__name__}: {exc}")
                self.last_result = res
            finally:
                with self._lock:
                    self.running = False
                    self.current_step = None
                    self.current_trigger = None

        self._thread = threading.Thread(target=work, name=f"refresh-{trigger}", daemon=True)
        self._thread.start()
        return True

    def _progress(self, msg: str) -> None:
        self.current_step = msg

    def run_blocking(self, **kwargs) -> RefreshResult | None:
        """Used by the scheduler: start and wait, skip if already running."""
        if not self.start(**kwargs):
            log.info("Refresh already running; scheduled run skipped")
            return None
        assert self._thread is not None
        self._thread.join()
        return self.last_result

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "trigger": self.current_trigger,
            "step": self.current_step,
            "started_at": self.started_at.isoformat() + "Z" if self.started_at and self.running else None,
            "last_run": self.last_result.to_dict() if self.last_result else None,
        }
