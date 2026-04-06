"""Comprehensive unit tests for AutoShowTracker API endpoints.

Strategy: Build a minimal FastAPI test app that includes all routers but
uses a simple synchronous lifespan that injects a temp-path DatabaseManager
instead of the production one (which would try to start ActivityWatch,
SMTC/MPRIS, etc.).

All tests use FastAPI's TestClient (Starlette's synchronous test client) so
no async test runner is needed.
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

from show_tracker import __version__
from show_tracker.api.schemas import HealthResponse
from show_tracker.storage.database import DatabaseManager
from show_tracker.storage.models import UnresolvedEvent, UserSetting, _utcnow
from show_tracker.storage.repository import WatchRepository

# ---------------------------------------------------------------------------
# Test app factory — same routers, no real lifespan side-effects
# ---------------------------------------------------------------------------


def make_test_app(db: DatabaseManager) -> FastAPI:
    """Create a minimal FastAPI app with all routers and a test DB injected."""

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        app.state.db = db
        # Provide a stub for app.state.detection so media-event routes don't crash
        app.state.detection = None
        yield
        db.close()

    application = FastAPI(
        title="AutoShowTracker (Test)",
        version=__version__,
        lifespan=test_lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Import and register all routers
    from show_tracker.api.routes_export import router as export_router
    from show_tracker.api.routes_history import router as history_router
    from show_tracker.api.routes_media import router as media_router
    from show_tracker.api.routes_movies import router as movies_router
    from show_tracker.api.routes_settings import router as settings_router
    from show_tracker.api.routes_stats import router as stats_router
    from show_tracker.api.routes_unresolved import router as unresolved_router
    from show_tracker.api.routes_youtube import router as youtube_router

    application.include_router(media_router)
    application.include_router(history_router)
    application.include_router(unresolved_router)
    application.include_router(settings_router)
    application.include_router(export_router)
    application.include_router(stats_router)
    application.include_router(youtube_router)
    application.include_router(movies_router)

    @application.get("/api/health", response_model=HealthResponse, tags=["system"])
    async def health_check() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__)

    return application


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="function")
def test_db(tmp_path: Path) -> DatabaseManager:
    manager = DatabaseManager(data_dir=tmp_path)
    manager.init_databases()
    return manager


@pytest.fixture(autouse=True)
def reset_media_state() -> None:
    """Reset the module-level _current_state in routes_media between tests."""
    import show_tracker.api.routes_media as routes_media
    routes_media._current_state = {}
    yield
    routes_media._current_state = {}


@pytest.fixture(scope="function")
def client(test_db: DatabaseManager) -> TestClient:
    app = make_test_app(test_db)
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Helper: populate some watch data
# ---------------------------------------------------------------------------


def _seed_watch_history(db: DatabaseManager) -> tuple[int, int]:
    """Create a show + episode + watch event. Return (show_id, episode_id)."""
    with db.get_watch_session() as session:
        repo = WatchRepository(session)
        show = repo.upsert_show(title="Breaking Bad", tmdb_id=1396)
        ep = repo.upsert_episode(
            show_id=show.id,
            season_number=1,
            episode_number=1,
            title="Pilot",
            runtime_minutes=58,
        )
        repo.create_watch_event(
            episode_id=ep.id,
            started_at=_utcnow(),
            source="test",
            duration_seconds=3100,
            completed=True,
        )
        return show.id, ep.id


# ===================================================================
# TestHealthEndpoint
# ===================================================================


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        data = resp.json()
        assert data["status"] == "ok"

    def test_health_returns_version(self, client: TestClient) -> None:
        resp = client.get("/api/health")
        data = resp.json()
        assert data["version"] == __version__
        assert data["version"] != ""


# ===================================================================
# TestMediaEvent
# ===================================================================


class TestMediaEvent:
    """POST /api/media-event"""

    def _valid_payload(self, event_type: str = "play") -> dict:
        return {
            "type": event_type,
            "timestamp": int(time.time() * 1000),  # current time in ms
            "tab_url": "https://www.netflix.com/watch/12345",
            "tab_id": 1,
            "metadata": {
                "url": "https://www.netflix.com/watch/12345",
                "title": "Breaking Bad - S01E01",
                "og": {},
                "video": [],
                "schema": [],
            },
            "position": 120.5,
            "duration": 3480.0,
            "source": "show-tracker-content",
        }

    def test_play_event_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("play"))
        assert resp.status_code == 200

    def test_play_event_returns_ok(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("play"))
        data = resp.json()
        assert data["status"] == "ok"

    def test_pause_event_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("pause"))
        assert resp.status_code == 200

    def test_ended_event_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("ended"))
        assert resp.status_code == 200

    def test_heartbeat_event_returns_200(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("heartbeat"))
        assert resp.status_code == 200

    def test_missing_type_returns_422(self, client: TestClient) -> None:
        payload = self._valid_payload()
        del payload["type"]
        resp = client.post("/api/media-event", json=payload)
        assert resp.status_code == 422

    def test_missing_timestamp_returns_422(self, client: TestClient) -> None:
        payload = self._valid_payload()
        del payload["timestamp"]
        resp = client.post("/api/media-event", json=payload)
        assert resp.status_code == 422

    def test_event_message_contains_event_type(self, client: TestClient) -> None:
        resp = client.post("/api/media-event", json=self._valid_payload("play"))
        data = resp.json()
        assert "play" in data["message"]

    def test_currently_watching_after_play(self, client: TestClient) -> None:
        """After a play event, currently-watching should reflect the state."""
        client.post("/api/media-event", json=self._valid_payload("play"))
        resp = client.get("/api/currently-watching")
        assert resp.status_code == 200
        data = resp.json()
        # With a fresh timestamp it should be watching
        assert data["is_watching"] is True


# ===================================================================
# TestCurrentlyWatching
# ===================================================================


class TestCurrentlyWatching:
    """GET /api/currently-watching"""

    def test_returns_200_when_empty(self, client: TestClient) -> None:
        resp = client.get("/api/currently-watching")
        assert resp.status_code == 200

    def test_not_watching_when_no_events(self, client: TestClient) -> None:
        resp = client.get("/api/currently-watching")
        data = resp.json()
        assert data["is_watching"] is False

    def test_not_watching_after_pause(self, client: TestClient) -> None:
        payload = {
            "type": "pause",
            "timestamp": int(time.time() * 1000),
            "tab_url": "https://netflix.com/watch/1",
            "tab_id": 1,
            "metadata": {"url": "", "title": "", "og": {}, "video": [], "schema": []},
        }
        client.post("/api/media-event", json=payload)
        resp = client.get("/api/currently-watching")
        data = resp.json()
        assert data["is_watching"] is False


# ===================================================================
# TestHistoryEndpoints
# ===================================================================


class TestHistoryEndpoints:
    """Tests for /api/history/* endpoints."""

    def test_recent_empty_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/history/recent")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_recent_returns_list(self, client: TestClient, test_db: DatabaseManager) -> None:
        _seed_watch_history(test_db)
        resp = client.get("/api/history/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_recent_item_schema(self, client: TestClient, test_db: DatabaseManager) -> None:
        _seed_watch_history(test_db)
        resp = client.get("/api/history/recent")
        item = resp.json()[0]
        assert "show_title" in item
        assert "season_number" in item
        assert "episode_number" in item
        assert "started_at" in item
        assert "completed" in item
        assert item["show_title"] == "Breaking Bad"

    def test_recent_limit_parameter(self, client: TestClient, test_db: DatabaseManager) -> None:
        # Create 5 watch events
        with test_db.get_watch_session() as session:
            repo = WatchRepository(session)
            show = repo.upsert_show(title="Show", tmdb_id=1)
            ep = repo.upsert_episode(show_id=show.id, season_number=1, episode_number=1)
            for _ in range(5):
                repo.create_watch_event(
                    episode_id=ep.id,
                    started_at=_utcnow(),
                    source="test",
                )
        resp = client.get("/api/history/recent?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3

    def test_shows_empty_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/history/shows")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_shows_returns_seeded_show(self, client: TestClient, test_db: DatabaseManager) -> None:
        _seed_watch_history(test_db)
        resp = client.get("/api/history/shows")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["title"] == "Breaking Bad"

    def test_shows_summary_schema(self, client: TestClient, test_db: DatabaseManager) -> None:
        _seed_watch_history(test_db)
        resp = client.get("/api/history/shows")
        item = resp.json()[0]
        assert "show_id" in item
        assert "title" in item
        assert "episodes_watched" in item
        assert "total_episodes" in item

    def test_show_detail_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/history/shows/99999")
        assert resp.status_code == 404

    def test_show_detail_returns_200(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.get(f"/api/history/shows/{show_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Breaking Bad"
        assert data["show_id"] == show_id
        assert "seasons" in data

    def test_show_detail_contains_seasons(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.get(f"/api/history/shows/{show_id}")
        data = resp.json()
        assert len(data["seasons"]) == 1
        season = data["seasons"][0]
        assert season["season_number"] == 1
        assert len(season["episodes"]) == 1

    def test_show_progress_returns_list(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.get(f"/api/history/shows/{show_id}/progress")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_show_progress_schema(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.get(f"/api/history/shows/{show_id}/progress")
        item = resp.json()[0]
        assert "episode_id" in item
        assert "season_number" in item
        assert "episode_number" in item
        assert "watched" in item

    def test_next_to_watch_empty_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/history/next-to-watch")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_next_to_watch_with_history(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        # ep1 completed, ep2 not watched
        with test_db.get_watch_session() as session:
            repo = WatchRepository(session)
            show = repo.upsert_show(title="Wire", tmdb_id=1438)
            ep1 = repo.upsert_episode(show_id=show.id, season_number=1, episode_number=1)
            repo.upsert_episode(show_id=show.id, season_number=1, episode_number=2)
            repo.create_watch_event(
                episode_id=ep1.id,
                started_at=_utcnow(),
                source="test",
                completed=True,
            )

        resp = client.get("/api/history/next-to-watch")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["show_title"] == "Wire"
        assert data[0]["next_episode"] == 2

    def test_stats_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/history/stats")
        assert resp.status_code == 200

    def test_stats_schema(self, client: TestClient) -> None:
        resp = client.get("/api/history/stats")
        data = resp.json()
        assert "total_watch_time_seconds" in data
        assert "total_episodes_watched" in data
        assert "total_shows" in data
        assert "by_show" in data
        assert "by_week" in data

    def test_stats_empty_has_zeros(self, client: TestClient) -> None:
        resp = client.get("/api/history/stats")
        data = resp.json()
        assert data["total_watch_time_seconds"] == 0
        assert data["total_episodes_watched"] == 0
        assert data["total_shows"] == 0
        assert data["by_show"] == []
        assert data["by_week"] == []

    def test_stats_with_data(self, client: TestClient, test_db: DatabaseManager) -> None:
        _seed_watch_history(test_db)
        resp = client.get("/api/history/stats")
        data = resp.json()
        assert data["total_episodes_watched"] >= 1
        assert data["total_shows"] >= 1
        assert len(data["by_show"]) >= 1


# ===================================================================
# TestSettingsEndpoints
# ===================================================================


class TestSettingsEndpoints:
    """Tests for /api/settings and /api/aliases endpoints."""

    def test_get_settings_empty_returns_200(self, client: TestClient) -> None:
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_settings_returns_list(self, client: TestClient, test_db: DatabaseManager) -> None:
        with test_db.get_watch_session() as session:
            session.add(UserSetting(key="theme", value="dark"))
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["key"] == "theme"
        assert data[0]["value"] == "dark"

    def test_get_settings_schema(self, client: TestClient, test_db: DatabaseManager) -> None:
        with test_db.get_watch_session() as session:
            session.add(UserSetting(key="notifications", value="true"))
        resp = client.get("/api/settings")
        item = resp.json()[0]
        assert "key" in item
        assert "value" in item

    def test_put_setting_creates_new(self, client: TestClient) -> None:
        resp = client.put("/api/settings/theme", json={"value": "dark"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["key"] == "theme"
        assert data["value"] == "dark"

    def test_put_setting_updates_existing(self, client: TestClient) -> None:
        client.put("/api/settings/theme", json={"value": "light"})
        resp = client.put("/api/settings/theme", json={"value": "dark"})
        assert resp.status_code == 200
        assert resp.json()["value"] == "dark"

    def test_put_setting_persisted_in_db(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        client.put("/api/settings/auto_log", json={"value": "true"})
        with test_db.get_watch_session() as session:
            repo = WatchRepository(session)
            val = repo.get_setting("auto_log")
        assert val == "true"

    def test_put_setting_missing_value_returns_422(self, client: TestClient) -> None:
        resp = client.put("/api/settings/theme", json={})
        assert resp.status_code == 422

    def test_settings_sorted_by_key(self, client: TestClient, test_db: DatabaseManager) -> None:
        with test_db.get_watch_session() as session:
            session.add(UserSetting(key="zzz", value="z"))
            session.add(UserSetting(key="aaa", value="a"))
        resp = client.get("/api/settings")
        keys = [item["key"] for item in resp.json()]
        assert keys == sorted(keys)


# ===================================================================
# TestAliasEndpoints
# ===================================================================


class TestAliasEndpoints:
    """Tests for /api/aliases endpoints."""

    def test_get_aliases_empty(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.get(f"/api/aliases/{show_id}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_post_alias_creates(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        resp = client.post("/api/aliases", json={"show_id": show_id, "alias": "BB"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["alias"] == "BB"
        assert data["show_id"] == show_id

    def test_post_alias_duplicate_returns_409(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        show_id, _ = _seed_watch_history(test_db)
        client.post("/api/aliases", json={"show_id": show_id, "alias": "BB"})
        resp = client.post("/api/aliases", json={"show_id": show_id, "alias": "BB"})
        assert resp.status_code == 409

    def test_get_aliases_after_creation(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        show_id, _ = _seed_watch_history(test_db)
        client.post("/api/aliases", json={"show_id": show_id, "alias": "BrBa"})
        resp = client.get(f"/api/aliases/{show_id}")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["alias"] == "BrBa"

    def test_delete_alias(self, client: TestClient, test_db: DatabaseManager) -> None:
        show_id, _ = _seed_watch_history(test_db)
        create_resp = client.post("/api/aliases", json={"show_id": show_id, "alias": "BB"})
        alias_id = create_resp.json()["id"]
        del_resp = client.delete(f"/api/aliases/{alias_id}")
        assert del_resp.status_code == 200
        assert del_resp.json()["status"] == "ok"

    def test_delete_alias_not_found_returns_404(self, client: TestClient) -> None:
        resp = client.delete("/api/aliases/99999")
        assert resp.status_code == 404


# ===================================================================
# TestUnresolvedEndpoints
# ===================================================================


class TestUnresolvedEndpoints:
    """Tests for /api/unresolved endpoints."""

    def test_list_unresolved_empty(self, client: TestClient) -> None:
        resp = client.get("/api/unresolved")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_unresolved_returns_events(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        with test_db.get_watch_session() as session:
            evt = UnresolvedEvent(
                raw_input="mystery.s01e01.mkv",
                source="filesystem",
                detected_at=_utcnow(),
                confidence=0.45,
            )
            session.add(evt)
        resp = client.get("/api/unresolved")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["raw_input"] == "mystery.s01e01.mkv"

    def test_list_unresolved_schema(
        self, client: TestClient, test_db: DatabaseManager
    ) -> None:
        with test_db.get_watch_session() as session:
            evt = UnresolvedEvent(
                raw_input="show.s02e05.mkv",
                source="browser",
                detected_at=_utcnow(),
            )
            session.add(evt)
        resp = client.get("/api/unresolved")
        item = resp.json()[0]
        assert "id" in item
        assert "raw_input" in item
        assert "source" in item
        assert "detected_at" in item
