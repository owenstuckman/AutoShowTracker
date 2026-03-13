"""Central configuration for Show Tracker.

Uses pydantic-settings to load configuration from environment variables,
a JSON settings file, and programmatic defaults. Environment variables
take precedence over file-based settings.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEFAULT_DATA_DIR = Path.home() / ".show-tracker"
_DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "default_settings.json"


class Settings(BaseSettings):
    """Application-wide settings.

    Values are resolved in this order (highest priority first):
      1. Environment variables (prefixed with ``ST_`` or exact name for API keys).
      2. Values passed programmatically.
      3. Defaults defined here.
    """

    model_config = SettingsConfigDict(
        env_prefix="ST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Networking / Ports ──────────────────────────────────────────────
    activitywatch_port: int = Field(
        default=5600,
        description="Port where ActivityWatch aw-server-rust listens.",
    )
    media_service_port: int = Field(
        default=7600,
        description="Port for the Show Tracker media identification HTTP API.",
    )

    # ── Identification Thresholds ───────────────────────────────────────
    auto_log_threshold: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score at or above which a detection is automatically "
            "logged without user confirmation."
        ),
    )
    review_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score below which a detection is sent to the unresolved "
            "queue for manual review."
        ),
    )

    # ── Feature Flags ───────────────────────────────────────────────────
    ocr_enabled: bool = Field(
        default=True,
        description="Enable OCR fallback when SMTC/MPRIS and window title fail.",
    )

    # ── External API Keys ───────────────────────────────────────────────
    tmdb_api_key: str = Field(
        default="",
        description="TMDb v3 API key. Set via TMDB_API_KEY env var.",
        validation_alias="TMDB_API_KEY",
    )
    youtube_api_key: str = Field(
        default="",
        description="YouTube Data API v3 key. Optional. Set via YOUTUBE_API_KEY env var.",
        validation_alias="YOUTUBE_API_KEY",
    )

    # ── Paths ───────────────────────────────────────────────────────────
    data_dir: Path = Field(
        default=_DEFAULT_DATA_DIR,
        description="Root directory for all application data (databases, logs, cache).",
    )

    # ── Timing ──────────────────────────────────────────────────────────
    heartbeat_interval: int = Field(
        default=30,
        gt=0,
        description="Seconds between heartbeat pulses while media is playing.",
    )
    grace_period: int = Field(
        default=120,
        gt=0,
        description=(
            "Seconds to wait after the last heartbeat before finalising a watch "
            "event (handles brief pauses and buffering)."
        ),
    )
    polling_interval: int = Field(
        default=10,
        gt=0,
        description="Seconds between ActivityWatch REST API polling cycles.",
    )

    # ── Derived Paths (computed, not set by user) ───────────────────────
    @property
    def watch_history_db(self) -> Path:
        """Path to the watch-history SQLite database."""
        return self.data_dir / "watch_history.db"

    @property
    def media_cache_db(self) -> Path:
        """Path to the TMDb/media-cache SQLite database."""
        return self.data_dir / "media_cache.db"

    @property
    def log_dir(self) -> Path:
        """Directory for log files."""
        return self.data_dir / "logs"

    # ── Validators ──────────────────────────────────────────────────────
    @field_validator("data_dir", mode="before")
    @classmethod
    def _expand_data_dir(cls, v: Any) -> Path:
        """Expand ``~`` and resolve to an absolute path."""
        return Path(v).expanduser().resolve()

    @model_validator(mode="after")
    def _check_thresholds(self) -> "Settings":
        if self.review_threshold > self.auto_log_threshold:
            msg = (
                f"review_threshold ({self.review_threshold}) must be <= "
                f"auto_log_threshold ({self.auto_log_threshold})"
            )
            raise ValueError(msg)
        return self

    # ── Helpers ──────────────────────────────────────────────────────────
    def ensure_directories(self) -> None:
        """Create the data directory tree if it does not already exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def has_tmdb_key(self) -> bool:
        """Return True if a TMDb API key is configured."""
        return bool(self.tmdb_api_key)

    def has_youtube_key(self) -> bool:
        """Return True if a YouTube API key is configured."""
        return bool(self.youtube_api_key)


def load_settings(**overrides: Any) -> Settings:
    """Build a ``Settings`` instance, optionally merging file-based defaults.

    Parameters
    ----------
    **overrides:
        Keyword arguments forwarded to the ``Settings`` constructor.  These
        take precedence over environment variables and file defaults.

    Returns
    -------
    Settings
        Fully-resolved application settings.
    """
    # Merge defaults from the shipped JSON file (lowest priority).
    file_defaults: dict[str, Any] = {}
    if _DEFAULT_SETTINGS_PATH.exists():
        with open(_DEFAULT_SETTINGS_PATH, encoding="utf-8") as fh:
            file_defaults = json.load(fh)

    # Overrides beat file defaults; env vars are handled internally by pydantic.
    merged = {**file_defaults, **overrides}
    return Settings(**merged)
