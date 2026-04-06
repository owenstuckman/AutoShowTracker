"""Comprehensive unit tests for the AutoShowTracker storage layer.

Tests cover:
- DatabaseManager dual-database isolation
- WatchRepository CRUD operations
- CacheRepository CRUD operations
- WatchEvent completion logic
- All public repository methods
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from show_tracker.storage.database import DatabaseManager
from show_tracker.storage.models import (
    Episode,
    FailedLookup,
    Show,
    TMDbSearchCache,
    TMDbShowCache,
    UnresolvedEvent,
    WatchEvent,
    _utcnow,
)
from show_tracker.storage.repository import CacheRepository, WatchRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db(tmp_path: Path) -> DatabaseManager:
    """Create and initialize a DatabaseManager backed by tmp_path."""
    manager = DatabaseManager(data_dir=tmp_path)
    manager.init_databases()
    return manager


@pytest.fixture
def watch_repo(db: DatabaseManager):
    """Yield a WatchRepository with an open session; commits on exit."""
    with db.get_watch_session() as session:
        yield WatchRepository(session)


@pytest.fixture
def cache_repo(db: DatabaseManager):
    """Yield a CacheRepository with an open session; commits on exit."""
    with db.get_cache_session() as session:
        yield CacheRepository(session)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def make_show(repo: WatchRepository, title: str = "Breaking Bad", tmdb_id: int = 1396) -> Show:
    return repo.upsert_show(title=title, tmdb_id=tmdb_id)


def make_episode(
    repo: WatchRepository,
    show_id: int,
    season: int = 1,
    episode: int = 1,
    runtime_minutes: int | None = None,
) -> Episode:
    return repo.upsert_episode(
        show_id=show_id,
        season_number=season,
        episode_number=episode,
        runtime_minutes=runtime_minutes,
    )


def make_watch_event(
    repo: WatchRepository,
    episode_id: int,
    completed: bool = False,
    duration_seconds: int | None = None,
    source: str = "test",
) -> WatchEvent:
    return repo.create_watch_event(
        episode_id=episode_id,
        started_at=_utcnow(),
        source=source,
        completed=completed,
        duration_seconds=duration_seconds,
    )


# ===================================================================
# TestDualDatabaseIsolation
# ===================================================================


class TestDualDatabaseIsolation:
    """Verify that the two SQLite databases are independent."""

    def test_separate_file_paths(self, db: DatabaseManager) -> None:
        assert db.watch_db_path != db.cache_db_path
        assert db.watch_db_path.name == "watch_history.db"
        assert db.cache_db_path.name == "media_cache.db"

    def test_files_exist_after_init(self, db: DatabaseManager) -> None:
        assert db.watch_db_path.exists()
        assert db.cache_db_path.exists()

    def test_watch_write_does_not_affect_cache(self, db: DatabaseManager) -> None:
        """Writing a Show to watch_db doesn't create anything in cache_db."""
        with db.get_watch_session() as session:
            repo = WatchRepository(session)
            repo.upsert_show(title="Test Show", tmdb_id=9999)

        with db.get_cache_session() as session:
            cache_repo = CacheRepository(session)
            result = cache_repo.get_cached_show(9999)
        assert result is None

    def test_cache_write_does_not_affect_watch(self, db: DatabaseManager) -> None:
        """Writing to the cache db doesn't create a Show in watch_db."""
        with db.get_cache_session() as session:
            repo = CacheRepository(session)
            repo.cache_show(tmdb_id=42, data={"name": "Cached Show"})

        with db.get_watch_session() as session:
            from sqlalchemy import select

            show = session.execute(select(Show).where(Show.tmdb_id == 42)).scalar_one_or_none()
        assert show is None

    def test_cache_db_can_be_deleted_and_recreated(self, db: DatabaseManager) -> None:
        """Simulate deleting the cache db and reinitialising without touching watch db."""
        # Write to watch db
        with db.get_watch_session() as session:
            WatchRepository(session).upsert_show(title="Persistent Show", tmdb_id=111)

        # Write to cache db
        with db.get_cache_session() as session:
            CacheRepository(session).cache_show(tmdb_id=111, data={"name": "Cached"})

        # Close, delete cache, re-init
        db.close()
        db.cache_db_path.unlink()
        db.init_databases()

        # Watch data survives — access attributes inside session to avoid DetachedInstanceError
        with db.get_watch_session() as session:
            from sqlalchemy import select

            show = session.execute(select(Show).where(Show.tmdb_id == 111)).scalar_one_or_none()
            assert show is not None
            assert show.title == "Persistent Show"

        # Cache is empty again
        with db.get_cache_session() as session:
            result = CacheRepository(session).get_cached_show(111)
        assert result is None

    def test_sessions_are_independent_objects(self, db: DatabaseManager) -> None:
        """Each context manager call returns a distinct session."""
        with db.get_watch_session() as s1, db.get_watch_session() as s2:
            assert s1 is not s2

    def test_init_databases_is_idempotent(self, db: DatabaseManager) -> None:
        """Calling init_databases() a second time should not raise."""
        db.init_databases()  # second call
        assert db.watch_db_path.exists()
        assert db.cache_db_path.exists()

    def test_not_initialised_raises(self, tmp_path: Path) -> None:
        manager = DatabaseManager(data_dir=tmp_path)
        with pytest.raises(RuntimeError, match="init_databases"), manager.get_watch_session():
            pass


# ===================================================================
# TestWatchRepositoryCRUD
# ===================================================================


class TestWatchRepositoryCRUD:
    """Tests for WatchRepository public methods."""

    # -- Shows -----------------------------------------------------------

    def test_upsert_show_creates_new(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        assert show.id is not None
        assert show.title == "Breaking Bad"
        assert show.tmdb_id == 1396

    def test_upsert_show_updates_existing(self, watch_repo: WatchRepository) -> None:
        show1 = make_show(watch_repo, title="Breaking Bad", tmdb_id=1396)
        show2 = watch_repo.upsert_show(title="Breaking Bad (Updated)", tmdb_id=1396)
        assert show1.id == show2.id
        assert show2.title == "Breaking Bad (Updated)"

    def test_upsert_show_without_tmdb_id(self, watch_repo: WatchRepository) -> None:
        show = watch_repo.upsert_show(title="Local Show")
        assert show.id is not None
        assert show.tmdb_id is None

    def test_upsert_show_updates_optional_fields(self, watch_repo: WatchRepository) -> None:
        show = watch_repo.upsert_show(title="Show", tmdb_id=500)
        updated = watch_repo.upsert_show(
            title="Show",
            tmdb_id=500,
            tvdb_id=12345,
            status="Ended",
            total_seasons=5,
        )
        assert updated.id == show.id
        assert updated.tvdb_id == 12345
        assert updated.status == "Ended"
        assert updated.total_seasons == 5

    # -- Episodes --------------------------------------------------------

    def test_upsert_episode_creates_new(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id, season=2, episode=3)
        assert ep.id is not None
        assert ep.season_number == 2
        assert ep.episode_number == 3

    def test_upsert_episode_updates_existing(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep1 = make_episode(watch_repo, show.id, season=1, episode=1)
        ep2 = watch_repo.upsert_episode(
            show_id=show.id,
            season_number=1,
            episode_number=1,
            title="Pilot",
            runtime_minutes=60,
        )
        assert ep1.id == ep2.id
        assert ep2.title == "Pilot"
        assert ep2.runtime_minutes == 60

    # -- WatchEvent creation ---------------------------------------------

    def test_create_watch_event(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        event = make_watch_event(watch_repo, ep.id)
        assert event.id is not None
        assert event.episode_id == ep.id
        assert event.completed is False

    def test_create_watch_event_with_source_detail(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        event = watch_repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="browser",
            source_detail="https://netflix.com/watch/12345",
            confidence=0.95,
            raw_input="Breaking Bad S01E01",
        )
        assert event.source == "browser"
        assert event.confidence == 0.95
        assert "netflix" in event.source_detail

    # -- get_recent_watches ----------------------------------------------

    def test_get_recent_watches_empty(self, watch_repo: WatchRepository) -> None:
        result = watch_repo.get_recent_watches()
        assert result == []

    def test_get_recent_watches_returns_data(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo, title="The Wire", tmdb_id=1438)
        ep = make_episode(watch_repo, show.id, season=1, episode=1)
        make_watch_event(watch_repo, ep.id, source="smtc")
        result = watch_repo.get_recent_watches()
        assert len(result) == 1
        assert result[0]["show_title"] == "The Wire"
        assert result[0]["season_number"] == 1
        assert result[0]["episode_number"] == 1
        assert result[0]["source"] == "smtc"

    def test_get_recent_watches_respects_limit(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        for _ in range(5):
            make_watch_event(watch_repo, ep.id)
        result = watch_repo.get_recent_watches(limit=3)
        assert len(result) == 3

    def test_get_recent_watches_ordered_by_started_at_desc(
        self, watch_repo: WatchRepository
    ) -> None:
        show = make_show(watch_repo)
        ep1 = make_episode(watch_repo, show.id, season=1, episode=1)
        ep2 = make_episode(watch_repo, show.id, season=1, episode=2)

        earlier = (datetime.now(UTC) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        watch_repo.create_watch_event(episode_id=ep1.id, started_at=earlier, source="test")
        watch_repo.create_watch_event(episode_id=ep2.id, started_at=_utcnow(), source="test")

        result = watch_repo.get_recent_watches()
        assert result[0]["episode_number"] == 2
        assert result[1]["episode_number"] == 1

    # -- get_show_progress -----------------------------------------------

    def test_get_show_progress_empty(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        result = watch_repo.get_show_progress(show.id)
        assert result == []

    def test_get_show_progress_with_data(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep1 = make_episode(watch_repo, show.id, season=1, episode=1)
        ep2 = make_episode(watch_repo, show.id, season=1, episode=2)
        make_watch_event(watch_repo, ep1.id, completed=True, duration_seconds=2700)
        make_watch_event(watch_repo, ep2.id, completed=False, duration_seconds=100)

        result = watch_repo.get_show_progress(show.id)
        assert len(result) == 2
        ep1_progress = next(r for r in result if r["episode_number"] == 1)
        assert ep1_progress["watched"] == 1  # SQLite max(True) = 1

    # -- get_next_to_watch -----------------------------------------------

    def test_get_next_to_watch_no_watches(self, watch_repo: WatchRepository) -> None:
        make_show(watch_repo)
        result = watch_repo.get_next_to_watch()
        assert result == []

    def test_get_next_to_watch_returns_first_unwatched(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep1 = make_episode(watch_repo, show.id, season=1, episode=1)
        make_episode(watch_repo, show.id, season=1, episode=2)
        # Watch ep1 as completed
        make_watch_event(watch_repo, ep1.id, completed=True)
        result = watch_repo.get_next_to_watch()
        assert len(result) == 1
        assert result[0]["show_id"] == show.id

    # -- Unresolved events -----------------------------------------------

    def test_create_and_retrieve_unresolved_event(self, watch_repo: WatchRepository) -> None:
        evt = UnresolvedEvent(
            raw_input="unknown.show.s02e05.mkv",
            source="filesystem",
            detected_at=_utcnow(),
            confidence=0.4,
        )
        watch_repo._session.add(evt)
        watch_repo._session.flush()

        results = watch_repo.get_unresolved_events()
        assert len(results) == 1
        assert results[0].raw_input == "unknown.show.s02e05.mkv"
        assert results[0].resolved is False

    def test_resolve_event_with_episode(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)

        evt = UnresolvedEvent(
            raw_input="mystery show",
            source="browser",
            detected_at=_utcnow(),
        )
        watch_repo._session.add(evt)
        watch_repo._session.flush()

        resolved = watch_repo.resolve_event(evt.id, episode_id=ep.id)
        assert resolved is not None
        assert resolved.resolved is True
        assert resolved.resolved_episode_id == ep.id

    def test_resolve_event_dismiss(self, watch_repo: WatchRepository) -> None:
        evt = UnresolvedEvent(
            raw_input="something",
            source="test",
            detected_at=_utcnow(),
        )
        watch_repo._session.add(evt)
        watch_repo._session.flush()

        resolved = watch_repo.resolve_event(evt.id, episode_id=None)
        assert resolved.resolved is True
        assert resolved.resolved_episode_id is None

    def test_resolve_event_not_found_returns_none(self, watch_repo: WatchRepository) -> None:
        result = watch_repo.resolve_event(99999, episode_id=None)
        assert result is None

    def test_get_unresolved_events_excludes_resolved(self, watch_repo: WatchRepository) -> None:
        for i in range(3):
            evt = UnresolvedEvent(
                raw_input=f"show_{i}",
                source="test",
                detected_at=_utcnow(),
            )
            watch_repo._session.add(evt)
        watch_repo._session.flush()

        # Resolve first one
        all_evts = watch_repo.get_unresolved_events()
        watch_repo.resolve_event(all_evts[0].id)

        remaining = watch_repo.get_unresolved_events()
        assert len(remaining) == 2

    # -- Settings --------------------------------------------------------

    def test_get_setting_not_found_returns_none(self, watch_repo: WatchRepository) -> None:
        assert watch_repo.get_setting("nonexistent") is None

    def test_set_and_get_setting(self, watch_repo: WatchRepository) -> None:
        watch_repo.set_setting("theme", "dark")
        assert watch_repo.get_setting("theme") == "dark"

    def test_update_setting(self, watch_repo: WatchRepository) -> None:
        watch_repo.set_setting("theme", "light")
        watch_repo.set_setting("theme", "dark")
        assert watch_repo.get_setting("theme") == "dark"

    def test_set_multiple_settings(self, watch_repo: WatchRepository) -> None:
        watch_repo.set_setting("key1", "val1")
        watch_repo.set_setting("key2", "val2")
        assert watch_repo.get_setting("key1") == "val1"
        assert watch_repo.get_setting("key2") == "val2"

    # -- Aliases ---------------------------------------------------------

    def test_add_and_get_alias(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        alias = watch_repo.add_alias(show.id, alias="BB", source="user")
        assert alias.id is not None

        aliases = watch_repo.get_aliases_for_show(show.id)
        assert len(aliases) == 1
        assert aliases[0].alias == "BB"

    def test_find_show_by_alias(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo, title="The Sopranos", tmdb_id=1398)
        watch_repo.add_alias(show.id, alias="Sopranos")

        found = watch_repo.find_show_by_alias("Sopranos")
        assert found is not None
        assert found.id == show.id
        assert found.title == "The Sopranos"

    def test_find_show_by_alias_not_found(self, watch_repo: WatchRepository) -> None:
        result = watch_repo.find_show_by_alias("NoSuchAlias")
        assert result is None

    def test_get_aliases_for_show_multiple(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        watch_repo.add_alias(show.id, alias="BB")
        watch_repo.add_alias(show.id, alias="BrBa")
        aliases = watch_repo.get_aliases_for_show(show.id)
        assert len(aliases) == 2

    # -- YouTube ---------------------------------------------------------

    def test_create_youtube_watch(self, watch_repo: WatchRepository) -> None:
        yw = watch_repo.create_youtube_watch(
            video_id="dQw4w9WgXcQ",
            title="Rick Astley - Never Gonna Give You Up",
            started_at=_utcnow(),
            channel_name="Official Rick Astley",
            duration_seconds=213,
        )
        assert yw.id is not None
        assert yw.video_id == "dQw4w9WgXcQ"
        assert yw.channel_name == "Official Rick Astley"

    # -- Heartbeat / process_heartbeat -----------------------------------

    def test_process_heartbeat_creates_new_event(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        event = watch_repo.process_heartbeat(
            episode_id=ep.id,
            source="smtc",
            confidence=0.9,
        )
        assert event.id is not None
        assert event.episode_id == ep.id

    def test_process_heartbeat_extends_existing(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)

        evt1 = watch_repo.process_heartbeat(episode_id=ep.id, source="smtc", confidence=0.9)
        initial_duration = evt1.duration_seconds

        evt2 = watch_repo.process_heartbeat(
            episode_id=ep.id, source="smtc", confidence=0.9, heartbeat_interval=30
        )
        assert evt1.id == evt2.id
        assert (evt2.duration_seconds or 0) > (initial_duration or 0)


# ===================================================================
# TestWatchEventCompletion
# ===================================================================


class TestWatchEventCompletion:
    """Tests for WatchEvent completion logic via finalize_watch_event."""

    def test_watch_event_completed_false_by_default(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        event = make_watch_event(watch_repo, ep.id)
        assert event.completed is False

    def test_finalize_marks_completed_at_90_percent(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        # 30-minute episode → 1800 seconds, 90% = 1620 seconds
        ep = make_episode(watch_repo, show.id, runtime_minutes=30)
        # Create open event (no ended_at) with enough duration
        watch_repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="test",
            duration_seconds=1620,  # exactly 90%
        )
        finalized = watch_repo.finalize_watch_event(ep.id)
        assert finalized is not None
        assert finalized.completed is True

    def test_finalize_not_completed_below_90_percent(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id, runtime_minutes=30)
        watch_repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="test",
            duration_seconds=500,  # way below 90%
        )
        finalized = watch_repo.finalize_watch_event(ep.id)
        assert finalized is not None
        assert finalized.completed is False

    def test_finalize_uses_default_runtime_when_none(self, watch_repo: WatchRepository) -> None:
        """When episode has no runtime, defaults to 45 min (2700s); 90% = 2430s."""
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id, runtime_minutes=None)
        watch_repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="test",
            duration_seconds=2430,
        )
        finalized = watch_repo.finalize_watch_event(ep.id)
        assert finalized is not None
        assert finalized.completed is True

    def test_finalize_no_open_event_returns_none(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id)
        result = watch_repo.finalize_watch_event(ep.id)
        assert result is None

    def test_finalize_sets_ended_at(self, watch_repo: WatchRepository) -> None:
        show = make_show(watch_repo)
        ep = make_episode(watch_repo, show.id, runtime_minutes=30)
        watch_repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="test",
            duration_seconds=1800,
        )
        finalized = watch_repo.finalize_watch_event(ep.id)
        assert finalized.ended_at is not None


# ===================================================================
# TestCacheRepositoryCRUD
# ===================================================================


class TestCacheRepositoryCRUD:
    """Tests for CacheRepository public methods."""

    # -- Show cache -------------------------------------------------------

    def test_cache_show_and_retrieve(self, cache_repo: CacheRepository) -> None:
        data = {"name": "Breaking Bad", "seasons": 5}
        cache_repo.cache_show(tmdb_id=1396, data=data)
        result = cache_repo.get_cached_show(1396)
        assert result is not None
        assert result["name"] == "Breaking Bad"
        assert result["seasons"] == 5

    def test_cache_show_miss_returns_none(self, cache_repo: CacheRepository) -> None:
        result = cache_repo.get_cached_show(99999)
        assert result is None

    def test_cache_show_updates_existing(self, cache_repo: CacheRepository) -> None:
        cache_repo.cache_show(tmdb_id=1396, data={"name": "Old"})
        cache_repo.cache_show(tmdb_id=1396, data={"name": "New"})
        result = cache_repo.get_cached_show(1396)
        assert result["name"] == "New"

    def test_cache_show_stale_returns_none(self, cache_repo: CacheRepository) -> None:
        """A cache entry > 6 months old should be stale (TMDb ToS max cache = 6 months)."""
        stale_time = (datetime.now(UTC) - timedelta(days=185)).strftime("%Y-%m-%d %H:%M:%S")
        entry = TMDbShowCache(
            tmdb_id=5555,
            data=json.dumps({"name": "Stale Show"}),
            fetched_at=stale_time,
        )
        cache_repo._session.add(entry)
        cache_repo._session.flush()
        result = cache_repo.get_cached_show(5555)
        assert result is None

    # -- Search cache -----------------------------------------------------

    def test_cache_search_and_retrieve(self, cache_repo: CacheRepository) -> None:
        cache_repo.cache_search(query="breaking bad", tmdb_ids=[1396, 999])
        result = cache_repo.get_cached_search("breaking bad")
        assert result == [1396, 999]

    def test_cache_search_miss_returns_none(self, cache_repo: CacheRepository) -> None:
        result = cache_repo.get_cached_search("nonexistent query xyz")
        assert result is None

    def test_cache_search_updates_existing(self, cache_repo: CacheRepository) -> None:
        cache_repo.cache_search("wire", [1438])
        cache_repo.cache_search("wire", [1438, 9999])
        result = cache_repo.get_cached_search("wire")
        assert result == [1438, 9999]

    def test_cache_search_stale_returns_none(self, cache_repo: CacheRepository) -> None:
        stale_time = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
        entry = TMDbSearchCache(
            query="stale query",
            result_tmdb_ids=json.dumps([1, 2, 3]),
            fetched_at=stale_time,
        )
        cache_repo._session.add(entry)
        cache_repo._session.flush()
        result = cache_repo.get_cached_search("stale query")
        assert result is None

    # -- Episode cache ----------------------------------------------------

    def test_cache_episode_and_retrieve(self, cache_repo: CacheRepository) -> None:
        data = {"name": "Pilot", "season_number": 1, "episode_number": 1}
        cache_repo.cache_episode(
            tmdb_episode_id=10001,
            show_tmdb_id=1396,
            season_number=1,
            episode_number=1,
            data=data,
        )
        result = cache_repo.get_cached_episode(10001)
        assert result is not None
        assert result["name"] == "Pilot"

    def test_cache_episode_miss_returns_none(self, cache_repo: CacheRepository) -> None:
        result = cache_repo.get_cached_episode(99999)
        assert result is None

    def test_cache_episode_updates_existing(self, cache_repo: CacheRepository) -> None:
        cache_repo.cache_episode(
            tmdb_episode_id=10002,
            show_tmdb_id=1396,
            season_number=1,
            episode_number=2,
            data={"name": "Old Title"},
        )
        cache_repo.cache_episode(
            tmdb_episode_id=10002,
            show_tmdb_id=1396,
            season_number=1,
            episode_number=2,
            data={"name": "New Title"},
        )
        result = cache_repo.get_cached_episode(10002)
        assert result["name"] == "New Title"

    # -- Failed lookups ---------------------------------------------------

    def test_record_failed_lookup(self, cache_repo: CacheRepository) -> None:
        entry = cache_repo.record_failed_lookup("bad show name", reason="no_results")
        assert entry.query == "bad show name"
        assert entry.reason == "no_results"
        assert entry.attempts == 1

    def test_record_failed_lookup_increments_attempts(self, cache_repo: CacheRepository) -> None:
        cache_repo.record_failed_lookup("bad show", reason="no_results")
        entry = cache_repo.record_failed_lookup("bad show", reason="no_results")
        assert entry.attempts == 2

    def test_get_failed_lookup_fresh(self, cache_repo: CacheRepository) -> None:
        cache_repo.record_failed_lookup("fresh fail", reason="no_results")
        result = cache_repo.get_failed_lookup("fresh fail")
        assert result is not None
        assert result.query == "fresh fail"

    def test_get_failed_lookup_not_found(self, cache_repo: CacheRepository) -> None:
        result = cache_repo.get_failed_lookup("nonexistent query")
        assert result is None

    def test_get_failed_lookup_expired_returns_none(self, cache_repo: CacheRepository) -> None:
        old_time = (datetime.now(UTC) - timedelta(hours=25)).strftime("%Y-%m-%d %H:%M:%S")
        entry = FailedLookup(
            query="old failure",
            reason="no_results",
            attempts=1,
            first_failed_at=old_time,
            last_failed_at=old_time,
        )
        cache_repo._session.add(entry)
        cache_repo._session.flush()
        result = cache_repo.get_failed_lookup("old failure", expiry_hours=24)
        assert result is None

    # -- is_cache_fresh ---------------------------------------------------

    def test_is_cache_fresh_with_recent_time(self) -> None:
        recent = _utcnow()
        assert CacheRepository.is_cache_fresh(recent) is True

    def test_is_cache_fresh_with_stale_time(self) -> None:
        stale = (datetime.now(UTC) - timedelta(days=8)).strftime("%Y-%m-%d %H:%M:%S")
        assert CacheRepository.is_cache_fresh(stale) is False

    def test_is_cache_fresh_none_returns_false(self) -> None:
        assert CacheRepository.is_cache_fresh(None) is False

    def test_is_cache_fresh_respects_expiry_override(self) -> None:
        one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        assert CacheRepository.is_cache_fresh(one_hour_ago, expiry_hours=2) is True
        assert CacheRepository.is_cache_fresh(one_hour_ago, expiry_hours=1) is False

    def test_is_cache_fresh_bad_format_returns_false(self) -> None:
        assert CacheRepository.is_cache_fresh("not-a-date") is False
