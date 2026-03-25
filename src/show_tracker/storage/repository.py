"""Data access layer for AutoShowTracker.

Provides WatchRepository (watch_history.db operations) and
CacheRepository (media_cache.db operations) that accept SQLAlchemy
sessions and encapsulate all query logic.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from show_tracker.storage.models import (
    Episode,
    FailedLookup,
    Show,
    ShowAlias,
    TMDbEpisodeCache,
    TMDbSearchCache,
    TMDbShowCache,
    UnresolvedEvent,
    UserSetting,
    WatchEvent,
    YouTubeWatch,
    _utcnow,
)

# ===================================================================
# WatchRepository — operates on watch_history.db
# ===================================================================

class WatchRepository:
    """Data access methods for the watch_history database."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----- Shows -----------------------------------------------------

    def upsert_show(
        self,
        *,
        tmdb_id: int | None = None,
        title: str,
        tvdb_id: int | None = None,
        original_title: str | None = None,
        poster_path: str | None = None,
        first_air_date: str | None = None,
        status: str | None = None,
        total_seasons: int | None = None,
    ) -> Show:
        """Insert a show or update it if the tmdb_id already exists.

        Returns the existing or newly created ``Show`` instance.
        """
        show: Show | None = None
        if tmdb_id is not None:
            show = self._session.execute(
                select(Show).where(Show.tmdb_id == tmdb_id)
            ).scalar_one_or_none()

        if show is not None:
            # Update mutable fields
            show.title = title
            if tvdb_id is not None:
                show.tvdb_id = tvdb_id
            if original_title is not None:
                show.original_title = original_title
            if poster_path is not None:
                show.poster_path = poster_path
            if first_air_date is not None:
                show.first_air_date = first_air_date
            if status is not None:
                show.status = status
            if total_seasons is not None:
                show.total_seasons = total_seasons
            show.updated_at = _utcnow()
        else:
            show = Show(
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                title=title,
                original_title=original_title,
                poster_path=poster_path,
                first_air_date=first_air_date,
                status=status,
                total_seasons=total_seasons,
            )
            self._session.add(show)

        self._session.flush()
        return show

    # ----- Episodes --------------------------------------------------

    def upsert_episode(
        self,
        *,
        show_id: int,
        season_number: int,
        episode_number: int,
        tmdb_episode_id: int | None = None,
        title: str | None = None,
        air_date: str | None = None,
        runtime_minutes: int | None = None,
    ) -> Episode:
        """Insert an episode or update it if (show_id, season, episode) exists."""
        episode = self._session.execute(
            select(Episode).where(
                Episode.show_id == show_id,
                Episode.season_number == season_number,
                Episode.episode_number == episode_number,
            )
        ).scalar_one_or_none()

        if episode is not None:
            if tmdb_episode_id is not None:
                episode.tmdb_episode_id = tmdb_episode_id
            if title is not None:
                episode.title = title
            if air_date is not None:
                episode.air_date = air_date
            if runtime_minutes is not None:
                episode.runtime_minutes = runtime_minutes
        else:
            episode = Episode(
                show_id=show_id,
                tmdb_episode_id=tmdb_episode_id,
                season_number=season_number,
                episode_number=episode_number,
                title=title,
                air_date=air_date,
                runtime_minutes=runtime_minutes,
            )
            self._session.add(episode)

        self._session.flush()
        return episode

    # ----- Watch events ----------------------------------------------

    def create_watch_event(
        self,
        *,
        episode_id: int,
        started_at: str,
        source: str,
        source_detail: str | None = None,
        confidence: float | None = None,
        raw_input: str | None = None,
        duration_seconds: int | None = None,
        ended_at: str | None = None,
        completed: bool = False,
    ) -> WatchEvent:
        """Create a new watch event."""
        event = WatchEvent(
            episode_id=episode_id,
            started_at=started_at,
            ended_at=ended_at,
            duration_seconds=duration_seconds,
            completed=completed,
            source=source,
            source_detail=source_detail,
            confidence=confidence,
            raw_input=raw_input,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def process_heartbeat(
        self,
        *,
        episode_id: int,
        source: str,
        confidence: float,
        raw_input: str | None = None,
        source_detail: str | None = None,
        heartbeat_interval: int = 30,
        gap_threshold_minutes: int = 5,
    ) -> WatchEvent:
        """Process a heartbeat signal for an episode currently playing.

        If an open watch event exists for this episode within
        ``gap_threshold_minutes``, extends it. Otherwise starts a new one.

        Args:
            heartbeat_interval: Seconds to add per heartbeat (default 30).
            gap_threshold_minutes: Max gap before starting a new event.

        Returns:
            The extended or newly created ``WatchEvent``.
        """
        now = _utcnow()
        cutoff = (
            datetime.now(UTC) - timedelta(minutes=gap_threshold_minutes)
        ).strftime("%Y-%m-%d %H:%M:%S")

        # Find the most recent open event for this episode within the gap
        recent = self._session.execute(
            select(WatchEvent)
            .where(
                WatchEvent.episode_id == episode_id,
                WatchEvent.ended_at.is_(None),
                WatchEvent.started_at > cutoff,
            )
            .order_by(WatchEvent.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if recent is not None:
            # Extend the existing event
            new_duration = (recent.duration_seconds or 0) + heartbeat_interval
            recent.duration_seconds = new_duration
            recent.ended_at = now
            self._session.flush()
            return recent

        # Start a new watch event
        event = WatchEvent(
            episode_id=episode_id,
            started_at=now,
            duration_seconds=0,
            source=source,
            source_detail=source_detail,
            confidence=confidence,
            raw_input=raw_input,
        )
        self._session.add(event)
        self._session.flush()
        return event

    def finalize_watch_event(self, episode_id: int) -> WatchEvent | None:
        """Finalize the most recent open watch event for an episode.

        Sets ``ended_at`` to now and marks ``completed`` based on whether
        the user watched >= 90% of the episode's expected runtime.

        Returns:
            The finalized ``WatchEvent``, or ``None`` if no open event found.
        """
        event = self._session.execute(
            select(WatchEvent)
            .where(
                WatchEvent.episode_id == episode_id,
                WatchEvent.ended_at.is_(None),
            )
            .order_by(WatchEvent.started_at.desc())
            .limit(1)
        ).scalar_one_or_none()

        if event is None:
            return None

        now = _utcnow()
        event.ended_at = now

        # Determine completion
        episode = self._session.execute(
            select(Episode).where(Episode.id == episode_id)
        ).scalar_one_or_none()

        expected_seconds = ((episode.runtime_minutes or 45) * 60) if episode else 2700
        event.completed = (event.duration_seconds or 0) >= (expected_seconds * 0.9)

        self._session.flush()
        return event

    # ----- Queries ---------------------------------------------------

    def get_recent_watches(self, limit: int = 50) -> Sequence[dict[str, Any]]:
        """Return recently watched episodes with show info.

        Returns a list of dicts matching the design doc query pattern.
        """
        stmt = (
            select(
                Show.title.label("show_title"),
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
                WatchEvent.started_at,
                WatchEvent.duration_seconds,
                WatchEvent.completed,
                WatchEvent.source,
            )
            .join(Episode, Episode.id == WatchEvent.episode_id)
            .join(Show, Show.id == Episode.show_id)
            .order_by(WatchEvent.started_at.desc())
            .limit(limit)
        )
        rows = self._session.execute(stmt).all()
        return [row._asdict() for row in rows]

    def get_show_progress(self, show_id: int) -> Sequence[dict[str, Any]]:
        """Return per-episode watch progress for a show.

        Follows the query pattern from the design doc — groups by episode,
        returns the best watch attempt per episode.
        """
        from sqlalchemy import func

        stmt = (
            select(
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
                func.max(WatchEvent.completed).label("watched"),
                func.max(WatchEvent.duration_seconds).label("longest_watch"),
                func.max(WatchEvent.started_at).label("last_watched"),
            )
            .outerjoin(WatchEvent, WatchEvent.episode_id == Episode.id)
            .where(Episode.show_id == show_id)
            .group_by(Episode.id)
            .order_by(Episode.season_number, Episode.episode_number)
        )
        rows = self._session.execute(stmt).all()
        return [row._asdict() for row in rows]

    def get_next_to_watch(self) -> Sequence[dict[str, Any]]:
        """Return the next unwatched episode per show (for shows with history).

        Only includes shows the user has watched at least one episode of.
        """
        from sqlalchemy import func

        # Subquery: shows with at least one completed watch
        watched_shows = (
            select(Episode.show_id)
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .where(WatchEvent.completed.is_(True))
            .distinct()
            .subquery()
        )

        # Episodes without a completed watch event
        stmt = (
            select(
                Show.id.label("show_id"),
                Show.title.label("show_title"),
                func.min(Episode.season_number).label("next_season"),
                func.min(Episode.episode_number).label("next_episode"),
            )
            .join(Episode, Episode.show_id == Show.id)
            .outerjoin(
                WatchEvent,
                (WatchEvent.episode_id == Episode.id)
                & (WatchEvent.completed.is_(True)),
            )
            .where(WatchEvent.id.is_(None), Show.id.in_(select(watched_shows)))
            .group_by(Show.id)
        )
        rows = self._session.execute(stmt).all()
        return [row._asdict() for row in rows]

    # ----- Unresolved events -----------------------------------------

    def get_unresolved_events(self, limit: int = 50) -> Sequence[UnresolvedEvent]:
        """Return pending (unresolved) events ordered by detection time."""
        stmt = (
            select(UnresolvedEvent)
            .where(UnresolvedEvent.resolved.is_(False))
            .order_by(UnresolvedEvent.detected_at.desc())
            .limit(limit)
        )
        return list(self._session.execute(stmt).scalars().all())

    def resolve_event(
        self, event_id: int, episode_id: int | None = None
    ) -> UnresolvedEvent | None:
        """Mark an unresolved event as resolved, optionally linking to an episode.

        Args:
            event_id: The unresolved event id.
            episode_id: The resolved episode id, or None to dismiss.

        Returns:
            The updated event, or None if not found.
        """
        evt = self._session.get(UnresolvedEvent, event_id)
        if evt is None:
            return None
        evt.resolved = True
        evt.resolved_episode_id = episode_id
        self._session.flush()
        return evt

    # ----- YouTube ---------------------------------------------------

    def create_youtube_watch(
        self,
        *,
        video_id: str,
        title: str,
        started_at: str,
        channel_name: str | None = None,
        channel_id: str | None = None,
        duration_seconds: int | None = None,
        watched_seconds: int | None = None,
        playlist_id: str | None = None,
        playlist_index: int | None = None,
        ended_at: str | None = None,
    ) -> YouTubeWatch:
        """Record a YouTube watch event."""
        watch = YouTubeWatch(
            video_id=video_id,
            title=title,
            channel_name=channel_name,
            channel_id=channel_id,
            duration_seconds=duration_seconds,
            watched_seconds=watched_seconds,
            playlist_id=playlist_id,
            playlist_index=playlist_index,
            started_at=started_at,
            ended_at=ended_at,
        )
        self._session.add(watch)
        self._session.flush()
        return watch

    # ----- Settings --------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        """Return a user setting value, or None if not set."""
        setting = self._session.get(UserSetting, key)
        return setting.value if setting else None

    def set_setting(self, key: str, value: str) -> UserSetting:
        """Create or update a user setting."""
        setting = self._session.get(UserSetting, key)
        if setting is not None:
            setting.value = value
            setting.updated_at = _utcnow()
        else:
            setting = UserSetting(key=key, value=value)
            self._session.add(setting)
        self._session.flush()
        return setting

    # ----- Aliases ---------------------------------------------------

    def add_alias(
        self, show_id: int, alias: str, source: str = "system"
    ) -> ShowAlias:
        """Add an alias for a show. Raises on duplicate alias."""
        sa = ShowAlias(show_id=show_id, alias=alias, source=source)
        self._session.add(sa)
        self._session.flush()
        return sa

    def get_aliases_for_show(self, show_id: int) -> Sequence[ShowAlias]:
        """Return all aliases for a given show."""
        stmt = select(ShowAlias).where(ShowAlias.show_id == show_id)
        return list(self._session.execute(stmt).scalars().all())

    def find_show_by_alias(self, alias: str) -> Show | None:
        """Look up a show by one of its aliases (exact match)."""
        stmt = (
            select(Show)
            .join(ShowAlias, ShowAlias.show_id == Show.id)
            .where(ShowAlias.alias == alias)
        )
        return self._session.execute(stmt).scalar_one_or_none()


# ===================================================================
# CacheRepository — operates on media_cache.db
# ===================================================================

class CacheRepository:
    """Data access methods for the media_cache database."""

    DEFAULT_EXPIRY_HOURS: int = 24 * 7  # 1 week

    def __init__(self, session: Session) -> None:
        self._session = session

    # ----- Freshness helper ------------------------------------------

    @staticmethod
    def is_cache_fresh(
        fetched_at: str | None,
        expiry_hours: int | None = None,
    ) -> bool:
        """Check whether a cached entry is still fresh.

        Args:
            fetched_at: ISO datetime string of when the entry was cached.
            expiry_hours: Hours before the cache expires.
                          Defaults to ``DEFAULT_EXPIRY_HOURS`` (7 days).

        Returns:
            True if the entry is still valid.
        """
        if fetched_at is None:
            return False
        if expiry_hours is None:
            expiry_hours = CacheRepository.DEFAULT_EXPIRY_HOURS
        try:
            fetched = datetime.strptime(fetched_at, "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=UTC
            )
        except ValueError:
            return False
        return datetime.now(UTC) - fetched < timedelta(hours=expiry_hours)

    # ----- Search cache ----------------------------------------------

    def get_cached_search(
        self, query: str, expiry_hours: int | None = None
    ) -> list[int] | None:
        """Return cached TMDb IDs for a search query, or None if stale/missing.

        Args:
            query: The normalised search string (lowercase, trimmed).
            expiry_hours: Override default expiry.

        Returns:
            List of TMDb show IDs, or None.
        """
        entry = self._session.get(TMDbSearchCache, query)
        if entry is None or not self.is_cache_fresh(entry.fetched_at, expiry_hours):
            return None
        result: list[int] = json.loads(entry.result_tmdb_ids)
        return result

    def cache_search(self, query: str, tmdb_ids: list[int]) -> TMDbSearchCache:
        """Store or update a search-result cache entry."""
        entry = self._session.get(TMDbSearchCache, query)
        now = _utcnow()
        if entry is not None:
            entry.result_tmdb_ids = json.dumps(tmdb_ids)
            entry.fetched_at = now
        else:
            entry = TMDbSearchCache(
                query=query,
                result_tmdb_ids=json.dumps(tmdb_ids),
                fetched_at=now,
            )
            self._session.add(entry)
        self._session.flush()
        return entry

    # ----- Show cache ------------------------------------------------

    def get_cached_show(
        self, tmdb_id: int, expiry_hours: int | None = None
    ) -> dict[str, Any] | None:
        """Return cached TMDb show data as a dict, or None if stale/missing."""
        entry = self._session.get(TMDbShowCache, tmdb_id)
        if entry is None or not self.is_cache_fresh(entry.fetched_at, expiry_hours):
            return None
        result: dict[str, Any] = json.loads(entry.data)
        return result

    def cache_show(self, tmdb_id: int, data: dict[str, Any]) -> TMDbShowCache:
        """Store or update a show cache entry."""
        entry = self._session.get(TMDbShowCache, tmdb_id)
        now = _utcnow()
        if entry is not None:
            entry.data = json.dumps(data)
            entry.fetched_at = now
        else:
            entry = TMDbShowCache(
                tmdb_id=tmdb_id,
                data=json.dumps(data),
                fetched_at=now,
            )
            self._session.add(entry)
        self._session.flush()
        return entry

    # ----- Episode cache ---------------------------------------------

    def get_cached_episode(
        self, tmdb_episode_id: int, expiry_hours: int | None = None
    ) -> dict[str, Any] | None:
        """Return cached TMDb episode data as a dict, or None if stale/missing."""
        entry = self._session.get(TMDbEpisodeCache, tmdb_episode_id)
        if entry is None or not self.is_cache_fresh(entry.fetched_at, expiry_hours):
            return None
        result: dict[str, Any] = json.loads(entry.data)
        return result

    def cache_episode(
        self,
        *,
        tmdb_episode_id: int,
        show_tmdb_id: int,
        season_number: int,
        episode_number: int,
        data: dict[str, Any],
    ) -> TMDbEpisodeCache:
        """Store or update an episode cache entry."""
        entry = self._session.get(TMDbEpisodeCache, tmdb_episode_id)
        now = _utcnow()
        if entry is not None:
            entry.data = json.dumps(data)
            entry.show_tmdb_id = show_tmdb_id
            entry.season_number = season_number
            entry.episode_number = episode_number
            entry.fetched_at = now
        else:
            entry = TMDbEpisodeCache(
                tmdb_episode_id=tmdb_episode_id,
                show_tmdb_id=show_tmdb_id,
                season_number=season_number,
                episode_number=episode_number,
                data=json.dumps(data),
                fetched_at=now,
            )
            self._session.add(entry)
        self._session.flush()
        return entry

    # ----- Failed lookups --------------------------------------------

    def get_failed_lookup(
        self, query: str, expiry_hours: int = 24
    ) -> FailedLookup | None:
        """Return a failed lookup if it exists and hasn't expired.

        Default expiry is 24 hours — prevents hammering the API for
        queries that recently failed, but allows retries eventually.
        """
        entry = self._session.get(FailedLookup, query)
        if entry is None:
            return None
        if not self.is_cache_fresh(entry.last_failed_at, expiry_hours):
            return None
        return entry

    def record_failed_lookup(
        self, query: str, reason: str = "no_results"
    ) -> FailedLookup:
        """Record or update a failed lookup entry."""
        entry = self._session.get(FailedLookup, query)
        now = _utcnow()
        if entry is not None:
            entry.attempts = (entry.attempts or 0) + 1
            entry.last_failed_at = now
            entry.reason = reason
        else:
            entry = FailedLookup(
                query=query,
                reason=reason,
                attempts=1,
                first_failed_at=now,
                last_failed_at=now,
            )
            self._session.add(entry)
        self._session.flush()
        return entry
