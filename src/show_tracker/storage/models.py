"""SQLAlchemy ORM models for AutoShowTracker databases.

Two separate SQLite databases:
- watch_history.db: user's watch log, show metadata, and preferences
- media_cache.db: cached TMDb/TVDb data (rebuildable)
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> str:
    """Return current UTC time as ISO format string."""
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Base classes — one per database so metadata stays separate
# ---------------------------------------------------------------------------

class WatchBase(DeclarativeBase):
    """Base for all watch_history.db models."""
    pass


class CacheBase(DeclarativeBase):
    """Base for all media_cache.db models."""
    pass


# ===================================================================
# watch_history.db models
# ===================================================================

class Show(WatchBase):
    __tablename__ = "shows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tmdb_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    tvdb_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_air_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_seasons: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)
    updated_at: Mapped[str] = mapped_column(Text, default=_utcnow, onupdate=_utcnow)

    # Relationships
    episodes: Mapped[list[Episode]] = relationship(
        "Episode", back_populates="show", cascade="all, delete-orphan"
    )
    aliases: Mapped[list[ShowAlias]] = relationship(
        "ShowAlias", back_populates="show", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_shows_tmdb", "tmdb_id"),
        Index("idx_shows_title", "title"),
    )


class Episode(WatchBase):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(Integer, ForeignKey("shows.id"), nullable=False)
    tmdb_episode_id: Mapped[int | None] = mapped_column(Integer, unique=True, nullable=True)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    air_date: Mapped[str | None] = mapped_column(Text, nullable=True)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)

    # Relationships
    show: Mapped[Show] = relationship("Show", back_populates="episodes")
    watch_events: Mapped[list[WatchEvent]] = relationship(
        "WatchEvent", back_populates="episode", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("show_id", "season_number", "episode_number"),
        Index("idx_episodes_show", "show_id"),
        Index("idx_episodes_lookup", "show_id", "season_number", "episode_number"),
    )


class WatchEvent(WatchBase):
    __tablename__ = "watch_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("episodes.id"), nullable=False
    )
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)

    # Relationships
    episode: Mapped[Episode] = relationship("Episode", back_populates="watch_events")

    __table_args__ = (
        Index("idx_watch_events_episode", "episode_id"),
        Index("idx_watch_events_time", "started_at"),
        Index("idx_watch_events_confidence", "confidence"),
    )


class YouTubeWatch(WatchBase):
    __tablename__ = "youtube_watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    channel_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    watched_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    playlist_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    playlist_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)

    __table_args__ = (
        Index("idx_youtube_video", "video_id"),
        Index("idx_youtube_playlist", "playlist_id"),
    )


class MovieWatch(WatchBase):
    __tablename__ = "movie_watches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tmdb_movie_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    original_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    poster_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    ended_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)

    __table_args__ = (
        Index("idx_movie_watches_tmdb", "tmdb_movie_id"),
        Index("idx_movie_watches_time", "started_at"),
    )


class ShowAlias(WatchBase):
    __tablename__ = "show_aliases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    show_id: Mapped[int] = mapped_column(Integer, ForeignKey("shows.id"), nullable=False)
    alias: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    source: Mapped[str] = mapped_column(Text, default="system")

    # Relationships
    show: Mapped[Show] = relationship("Show", back_populates="aliases")

    __table_args__ = (
        Index("idx_aliases_lookup", "alias"),
    )


class UnresolvedEvent(WatchBase):
    __tablename__ = "unresolved_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[str] = mapped_column(Text, nullable=False)
    best_guess_show: Mapped[str | None] = mapped_column(Text, nullable=True)
    best_guess_season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    best_guess_episode: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_episode_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("episodes.id"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(Text, default=_utcnow)

    # Relationships
    resolved_episode: Mapped[Episode | None] = relationship("Episode")

    __table_args__ = (
        Index(
            "idx_unresolved_pending",
            "resolved",
            sqlite_where=(~resolved),
        ),
    )


class UserSetting(WatchBase):
    __tablename__ = "user_settings"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, default=_utcnow, onupdate=_utcnow)


# ===================================================================
# media_cache.db models
# ===================================================================

class TMDbShowCache(CacheBase):
    __tablename__ = "tmdb_show_cache"

    tmdb_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob
    fetched_at: Mapped[str] = mapped_column(Text, default=_utcnow)


class TMDbSearchCache(CacheBase):
    __tablename__ = "tmdb_search_cache"

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    result_tmdb_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array
    fetched_at: Mapped[str] = mapped_column(Text, default=_utcnow)


class TMDbEpisodeCache(CacheBase):
    __tablename__ = "tmdb_episode_cache"

    tmdb_episode_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    show_tmdb_id: Mapped[int] = mapped_column(Integer, nullable=False)
    season_number: Mapped[int] = mapped_column(Integer, nullable=False)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[str] = mapped_column(Text, nullable=False)  # JSON blob
    fetched_at: Mapped[str] = mapped_column(Text, default=_utcnow)


class FailedLookup(CacheBase):
    __tablename__ = "failed_lookups"

    query: Mapped[str] = mapped_column(Text, primary_key=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    first_failed_at: Mapped[str] = mapped_column(Text, default=_utcnow)
    last_failed_at: Mapped[str] = mapped_column(Text, default=_utcnow)
