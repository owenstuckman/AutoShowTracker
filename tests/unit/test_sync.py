"""Unit tests for the Trakt sync routes and notification logic."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from show_tracker.api.routes_sync import router
from show_tracker.notifications import check_new_episodes, send_notification

# ---------------------------------------------------------------------------
# TestTraktSync — structural router tests
# ---------------------------------------------------------------------------


class TestTraktSync:
    """Structural tests for the Trakt sync APIRouter."""

    def test_router_has_routes(self) -> None:
        """The sync router has at least one registered route."""
        assert len(router.routes) > 0

    def test_router_prefix(self) -> None:
        """Router prefix is /api/sync/trakt."""
        assert router.prefix == "/api/sync/trakt"

    def _route_paths(self) -> list[str]:
        """Return all path strings registered on the router."""
        return [r.path for r in router.routes]  # type: ignore[attr-defined]

    def test_auth_route_registered(self) -> None:
        """POST /auth endpoint is registered."""
        paths = self._route_paths()
        # Paths may be relative (without the prefix) or absolute
        assert any("auth" in p for p in paths)

    def test_status_route_registered(self) -> None:
        """GET /status endpoint is registered."""
        paths = self._route_paths()
        assert any("status" in p for p in paths)

    def test_sync_route_registered(self) -> None:
        """POST /sync endpoint is registered."""
        paths = self._route_paths()
        assert any("sync" in p for p in paths)

    def test_disconnect_route_registered(self) -> None:
        """DELETE /disconnect endpoint is registered."""
        paths = self._route_paths()
        assert any("disconnect" in p for p in paths)

    def test_router_tags(self) -> None:
        """Router is tagged with 'sync'."""
        assert "sync" in router.tags

    def _route_methods(self) -> dict[str, list[str]]:
        """Return {path: [methods]} for all routes."""
        result: dict[str, list[str]] = {}
        for r in router.routes:
            path = getattr(r, "path", "")
            methods = list(getattr(r, "methods", []) or [])
            result[path] = methods
        return result

    def test_auth_is_post(self) -> None:
        """The auth endpoint uses POST."""
        methods_by_path = self._route_methods()
        auth_methods = [
            methods for path, methods in methods_by_path.items() if "auth" in path
        ]
        assert any("POST" in m for m in auth_methods)

    def test_status_is_get(self) -> None:
        """The status endpoint uses GET."""
        methods_by_path = self._route_methods()
        status_methods = [
            methods for path, methods in methods_by_path.items() if "status" in path
        ]
        assert any("GET" in m for m in status_methods)

    def test_disconnect_is_delete(self) -> None:
        """The disconnect endpoint uses DELETE."""
        methods_by_path = self._route_methods()
        disconnect_methods = [
            methods for path, methods in methods_by_path.items() if "disconnect" in path
        ]
        assert any("DELETE" in m for m in disconnect_methods)


# ---------------------------------------------------------------------------
# TestSendNotification
# ---------------------------------------------------------------------------


class TestSendNotification:
    """Tests for send_notification()."""

    def test_send_notification_returns_true_when_plyer_works(self) -> None:
        """send_notification() returns True when plyer.notification.notify succeeds."""
        mock_plyer = MagicMock()
        mock_plyer.notification.notify = MagicMock()

        with patch.dict("sys.modules", {"plyer": mock_plyer}):
            result = send_notification("Test Title", "Test message")

        assert result is True
        mock_plyer.notification.notify.assert_called_once()

    def test_send_notification_returns_false_when_plyer_missing(self) -> None:
        """send_notification() returns False when plyer is not installed."""
        with (
            patch.dict("sys.modules", {"plyer": None}),
            patch("builtins.__import__", side_effect=ImportError("no module")),
        ):
            result = send_notification("Title", "Message")
        # Should gracefully return False, not raise
        assert result is False

    def test_send_notification_returns_false_on_exception(self) -> None:
        """send_notification() returns False when plyer.notify raises."""
        mock_plyer = MagicMock()
        mock_plyer.notification.notify.side_effect = OSError("notification failed")

        with patch.dict("sys.modules", {"plyer": mock_plyer}):
            result = send_notification("Title", "Message")

        assert result is False

    def test_send_notification_passes_correct_args(self) -> None:
        """send_notification() passes title and message to plyer."""
        mock_plyer = MagicMock()
        mock_plyer.notification.notify = MagicMock()

        with patch.dict("sys.modules", {"plyer": mock_plyer}):
            send_notification("Episode Alert", "New episode of Breaking Bad")

        call_kwargs = mock_plyer.notification.notify.call_args
        assert call_kwargs is not None
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        args = call_kwargs.args if call_kwargs.args else ()
        # title might be positional or keyword
        all_args = list(args) + list(kwargs.values())
        assert "Episode Alert" in all_args or kwargs.get("title") == "Episode Alert"


# ---------------------------------------------------------------------------
# TestNotificationDispatch
# ---------------------------------------------------------------------------


class TestNotificationDispatch:
    """Tests for check_new_episodes() with mocked DB and TMDb."""

    def _make_mock_db(self, show_rows: list | None = None) -> MagicMock:
        """Build a mock DatabaseManager that returns the given show rows."""
        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_watch_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_watch_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_query = MagicMock()
        mock_session.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.distinct.return_value = mock_query
        mock_query.all.return_value = show_rows or []

        return mock_db

    def test_no_episodes_when_no_shows_watched(self) -> None:
        """check_new_episodes() returns [] when user has no watch history."""
        mock_db = self._make_mock_db(show_rows=[])
        result = check_new_episodes(mock_db, tmdb_api_key="fake_key")
        assert result == []

    def test_no_episodes_when_tmdb_returns_none(self) -> None:
        """check_new_episodes() returns [] when TMDb has no upcoming episodes."""
        today = date.today()

        mock_show = MagicMock()
        mock_show.title = "Breaking Bad"
        mock_show.tmdb_id = 1396
        mock_show.total_seasons = 5

        mock_db = self._make_mock_db(show_rows=[mock_show])

        with patch("show_tracker.identification.tmdb_client.TMDbClient") as mock_client_cls:
            instance = mock_client_cls.return_value
            # Return episodes that do NOT air today or tomorrow
            far_future = (today + timedelta(days=30)).isoformat()
            instance.get_season.return_value = {
                "episodes": [
                    {
                        "episode_number": 10,
                        "season_number": 5,
                        "name": "Future Episode",
                        "air_date": far_future,
                    }
                ]
            }
            instance.close = MagicMock()

            result = check_new_episodes(mock_db, tmdb_api_key="fake_key")

        assert result == []

    def test_returns_episode_airing_today(self) -> None:
        """check_new_episodes() returns an entry for an episode airing today."""
        today = date.today()

        mock_show = MagicMock()
        mock_show.title = "Succession"
        mock_show.tmdb_id = 12345
        mock_show.total_seasons = 4

        mock_db = self._make_mock_db(show_rows=[mock_show])

        with patch("show_tracker.identification.tmdb_client.TMDbClient") as mock_client_cls:
            instance = mock_client_cls.return_value
            instance.get_season.return_value = {
                "episodes": [
                    {
                        "episode_number": 1,
                        "season_number": 4,
                        "name": "The Munsters",
                        "air_date": today.isoformat(),
                    }
                ]
            }
            instance.close = MagicMock()

            result = check_new_episodes(mock_db, tmdb_api_key="fake_key")

        assert len(result) == 1
        ep = result[0]
        assert ep["show_name"] == "Succession"
        assert ep["season"] == 4
        assert ep["episode"] == 1
        assert ep["episode_title"] == "The Munsters"

    def test_returns_episode_airing_tomorrow(self) -> None:
        """check_new_episodes() returns an entry for an episode airing tomorrow."""
        tomorrow = date.today() + timedelta(days=1)

        mock_show = MagicMock()
        mock_show.title = "House of the Dragon"
        mock_show.tmdb_id = 94997
        mock_show.total_seasons = 2

        mock_db = self._make_mock_db(show_rows=[mock_show])

        with patch("show_tracker.identification.tmdb_client.TMDbClient") as mock_client_cls:
            instance = mock_client_cls.return_value
            instance.get_season.return_value = {
                "episodes": [
                    {
                        "episode_number": 8,
                        "season_number": 2,
                        "name": "The Red Dragon",
                        "air_date": tomorrow.isoformat(),
                    }
                ]
            }
            instance.close = MagicMock()

            result = check_new_episodes(mock_db, tmdb_api_key="fake_key")

        assert len(result) == 1
        assert result[0]["show_name"] == "House of the Dragon"
        assert result[0]["air_date"] == tomorrow.isoformat()

    def test_skips_episode_with_no_air_date(self) -> None:
        """check_new_episodes() skips episodes that have no air_date field."""
        mock_show = MagicMock()
        mock_show.title = "Some Show"
        mock_show.tmdb_id = 99999
        mock_show.total_seasons = 1

        mock_db = self._make_mock_db(show_rows=[mock_show])

        with patch("show_tracker.identification.tmdb_client.TMDbClient") as mock_client_cls:
            instance = mock_client_cls.return_value
            instance.get_season.return_value = {
                "episodes": [
                    {
                        "episode_number": 1,
                        "season_number": 1,
                        "name": "No Date",
                        "air_date": None,
                    }
                ]
            }
            instance.close = MagicMock()

            result = check_new_episodes(mock_db, tmdb_api_key="fake_key")

        assert result == []

    def test_skips_show_without_tmdb_id(self) -> None:
        """check_new_episodes() skips shows that have no tmdb_id."""
        mock_show = MagicMock()
        mock_show.title = "Unknown Show"
        mock_show.tmdb_id = None
        mock_show.total_seasons = 3

        mock_db = self._make_mock_db(show_rows=[mock_show])

        with patch("show_tracker.identification.tmdb_client.TMDbClient") as mock_client_cls:
            instance = mock_client_cls.return_value
            instance.close = MagicMock()

            result = check_new_episodes(mock_db, tmdb_api_key="fake_key")

        # TMDb should not even be queried
        instance.get_season.assert_not_called()
        assert result == []
