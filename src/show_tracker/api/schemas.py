"""Pydantic request/response models for the AutoShowTracker API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Media Event (from browser extension)
# ---------------------------------------------------------------------------


class VideoElementInfo(BaseModel):
    playing: bool = False
    currentTime: float = 0.0  # noqa: N815
    duration: float = 0.0
    src: str | None = None
    playerType: str = "unknown"  # noqa: N815


class UrlMatchResult(BaseModel):
    platform: str | None = None
    content_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class MediaMetadata(BaseModel):
    url: str = ""
    url_match: UrlMatchResult | None = None
    schema_: list[dict[str, Any]] = Field(default_factory=list, alias="schema")
    og: dict[str, str] = Field(default_factory=dict)
    title: str = ""
    video: list[VideoElementInfo] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class MediaEventIn(BaseModel):
    """Incoming media event from the browser extension."""

    type: str  # "play" | "pause" | "ended" | "heartbeat" | "page_load"
    timestamp: int  # Unix ms
    tab_url: str = ""
    tab_id: int = 0
    metadata: MediaMetadata = Field(default_factory=MediaMetadata)
    position: float | None = None  # playback position seconds
    duration: float | None = None  # total duration seconds
    source: str | None = "show-tracker-content"


class MediaEventResponse(BaseModel):
    status: str = "ok"
    message: str = ""


class CurrentlyWatchingResponse(BaseModel):
    is_watching: bool = False
    event_type: str | None = None
    tab_url: str | None = None
    title: str | None = None
    position: float | None = None
    duration: float | None = None
    last_update: int | None = None  # Unix ms


# ---------------------------------------------------------------------------
# Watch History
# ---------------------------------------------------------------------------


class EpisodeInfo(BaseModel):
    episode_id: int
    show_id: int
    show_title: str
    season_number: int
    episode_number: int
    episode_title: str | None = None
    started_at: str
    duration_seconds: int | None = None
    completed: bool = False
    source: str = ""


class ShowSummary(BaseModel):
    show_id: int
    title: str
    poster_path: str | None = None
    total_seasons: int | None = None
    status: str | None = None
    episodes_watched: int = 0
    total_episodes: int = 0
    last_watched: str | None = None


class ShowDetail(BaseModel):
    show_id: int
    title: str
    original_title: str | None = None
    poster_path: str | None = None
    first_air_date: str | None = None
    status: str | None = None
    total_seasons: int | None = None
    tmdb_id: int | None = None
    seasons: list[SeasonInfo] = Field(default_factory=list)


class SeasonInfo(BaseModel):
    season_number: int
    episodes: list[EpisodeGridItem] = Field(default_factory=list)


class EpisodeGridItem(BaseModel):
    episode_id: int
    episode_number: int
    title: str | None = None
    air_date: str | None = None
    runtime_minutes: int | None = None
    watched: bool = False
    last_watched: str | None = None
    watch_count: int = 0


class EpisodeProgress(BaseModel):
    episode_id: int
    season_number: int
    episode_number: int
    episode_title: str | None = None
    watched: bool = False
    longest_watch: int | None = None
    last_watched: str | None = None


class NextToWatch(BaseModel):
    show_id: int
    show_title: str
    poster_path: str | None = None
    next_season: int
    next_episode: int
    episode_title: str | None = None


class WatchStats(BaseModel):
    total_watch_time_seconds: int = 0
    total_episodes_watched: int = 0
    total_shows: int = 0
    total_youtube_watches: int = 0
    by_show: list[ShowWatchTime] = Field(default_factory=list)
    by_week: list[WeekWatchTime] = Field(default_factory=list)


class ShowWatchTime(BaseModel):
    show_id: int
    show_title: str
    total_seconds: int = 0
    episode_count: int = 0


class WeekWatchTime(BaseModel):
    week: str  # ISO week "2026-W10"
    total_seconds: int = 0
    episode_count: int = 0


# ---------------------------------------------------------------------------
# Unresolved Events
# ---------------------------------------------------------------------------


class UnresolvedEventOut(BaseModel):
    id: int
    raw_input: str
    source: str
    source_detail: str | None = None
    detected_at: str
    best_guess_show: str | None = None
    best_guess_season: int | None = None
    best_guess_episode: int | None = None
    confidence: float | None = None


class ResolveRequest(BaseModel):
    show_id: int
    season_number: int
    episode_number: int


class SearchRequest(BaseModel):
    query: str


class SearchResult(BaseModel):
    tmdb_id: int
    title: str
    first_air_date: str | None = None
    poster_path: str | None = None
    overview: str | None = None


# ---------------------------------------------------------------------------
# Settings & Aliases
# ---------------------------------------------------------------------------


class SettingOut(BaseModel):
    key: str
    value: str


class SettingUpdate(BaseModel):
    value: str


class AliasCreate(BaseModel):
    show_id: int
    alias: str


class AliasOut(BaseModel):
    id: int
    show_id: int
    alias: str
    source: str = "user"


# ---------------------------------------------------------------------------
# Generic
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = ""


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------


class YouTubeWatchOut(BaseModel):
    id: int
    video_id: str
    title: str
    channel_name: str | None = None
    duration_seconds: int | None = None
    watched_seconds: int | None = None
    started_at: str
    ended_at: str | None = None


class YouTubeStats(BaseModel):
    total_watches: int = 0
    unique_videos: int = 0
    total_watch_seconds: int = 0
    top_channels: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Movies
# ---------------------------------------------------------------------------


class MovieWatchOut(BaseModel):
    id: int
    tmdb_movie_id: int | None = None
    title: str
    year: int | None = None
    started_at: str
    ended_at: str | None = None
    duration_seconds: int | None = None
    watched_seconds: int | None = None
    source: str | None = None
    completed: bool = False


class MovieStats(BaseModel):
    total_watches: int = 0
    unique_movies: int = 0
    total_watch_seconds: int = 0
