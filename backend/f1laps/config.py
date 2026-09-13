"""Runtime configuration, read from environment variables (prefix F1LAPS_)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="F1LAPS_", env_file=".env", extra="ignore")

    # Where the SQLite database and the FastF1 HTTP cache live. Mount this as a volume.
    data_dir: Path = Path("./data")
    # Directory with the built frontend (index.html + assets). Served at "/" when present.
    static_dir: Path = Path("./static")

    # Seasons to keep in sync. The current season is always included.
    seasons: str = "2025,2026"

    # Scheduled data check: days (APScheduler day_of_week syntax), local time and zone.
    refresh_days: str = "fri,sat,sun"
    refresh_time: str = "23:30"
    refresh_tz: str = "UTC"
    scheduler_enabled: bool = True

    # Run a data check shortly after the service starts (useful right after a deploy).
    refresh_on_startup: bool = True

    # A session is considered "over" (and worth fetching) this many minutes after it started.
    session_grace_minutes: int = 180

    # Give up on a session after this many failed fetch attempts.
    max_fetch_attempts: int = 12

    log_level: str = "INFO"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "f1laps.db"

    @property
    def fastf1_cache_dir(self) -> Path:
        return self.data_dir / "fastf1-cache"

    @property
    def season_list(self) -> list[int]:
        out: set[int] = set()
        for part in self.seasons.split(","):
            part = part.strip()
            if part:
                out.add(int(part))
        return sorted(out)


settings = Settings()
