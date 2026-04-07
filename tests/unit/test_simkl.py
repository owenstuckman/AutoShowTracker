"""Unit tests for the Simkl import client."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest


class TestSimklClientInit:
    def test_loads_token_from_path(self, tmp_path: Path) -> None:
        token_path = tmp_path / "simkl_token.json"
        token_path.write_text(
            json.dumps({"access_token": "tok123", "expires_at": time.time() + 9999})
        )
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        assert client._access_token == "tok123"
        client.close()

    def test_missing_token_file_is_silent(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "none.json")
        assert client._access_token is None
        client.close()

    def test_is_authenticated_false_without_token(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "none.json")
        assert client.is_authenticated is False
        client.close()

    def test_is_authenticated_true_with_valid_token(self, tmp_path: Path) -> None:
        token_path = tmp_path / "simkl_token.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() + 9999}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        assert client.is_authenticated is True
        client.close()

    def test_is_authenticated_false_when_expired(self, tmp_path: Path) -> None:
        token_path = tmp_path / "simkl_token.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() - 1}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        assert client.is_authenticated is False
        client.close()


class TestSimklDeviceAuth:
    def _make_client(self, tmp_path: Path) -> object:
        from show_tracker.sync.simkl import SimklClient

        return SimklClient("cid", "csecret", token_path=tmp_path / "tok.json")

    def test_start_device_auth_returns_user_code(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "tok.json")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "user_code": "ABC123",
            "verification_url": "https://simkl.com/pin",
        }
        mock_resp.raise_for_status = MagicMock()
        client._client.get = MagicMock(return_value=mock_resp)

        result = client.start_device_auth()
        assert result["user_code"] == "ABC123"
        client.close()

    def test_poll_device_auth_returns_false_when_pending(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "tok.json")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        client._client.get = MagicMock(return_value=mock_resp)

        result = client.poll_device_auth("ABC123")
        assert result is False
        client.close()

    def test_poll_device_auth_saves_token_on_success(self, tmp_path: Path) -> None:
        token_path = tmp_path / "tok.json"
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "newtoken",
            "expires_in": 86400,
        }
        mock_resp.raise_for_status = MagicMock()
        client._client.get = MagicMock(return_value=mock_resp)

        result = client.poll_device_auth("ABC123")
        assert result is True
        assert client._access_token == "newtoken"
        assert token_path.exists()
        client.close()

    def test_poll_device_auth_raises_on_expired_pin(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklAuthError, SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "tok.json")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        client._client.get = MagicMock(return_value=mock_resp)

        with pytest.raises(SimklAuthError):
            client.poll_device_auth("EXPIRED")
        client.close()


class TestSimklGetAllItems:
    def test_get_all_items_returns_shows(self, tmp_path: Path) -> None:
        token_path = tmp_path / "tok.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() + 9999}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "shows": [
                {"show": {"title": "Breaking Bad"}, "seasons": []},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        client._client.get = MagicMock(return_value=mock_resp)

        items = client.get_all_items("shows")
        assert len(items) == 1
        assert items[0]["show"]["title"] == "Breaking Bad"
        client.close()

    def test_get_all_items_raises_when_unauthenticated(self, tmp_path: Path) -> None:
        from show_tracker.sync.simkl import SimklAuthError, SimklClient

        client = SimklClient("cid", "csecret", token_path=tmp_path / "none.json")
        with pytest.raises(SimklAuthError):
            client.get_all_items("shows")
        client.close()


class TestSimklImportHistory:
    def test_import_creates_watch_events(self, tmp_path: Path) -> None:
        token_path = tmp_path / "tok.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() + 9999}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)

        simkl_data = [
            {
                "show": {"title": "Breaking Bad"},
                "seasons": [
                    {
                        "number": 1,
                        "episodes": [
                            {"number": 1, "watched_at": "2024-01-01T00:00:00Z"},
                            {"number": 2, "watched_at": "2024-01-02T00:00:00Z"},
                        ],
                    }
                ],
            }
        ]

        mock_db = MagicMock()
        mock_session = MagicMock()
        mock_db.get_watch_session.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_db.get_watch_session.return_value.__exit__ = MagicMock(return_value=False)

        mock_repo = MagicMock()
        mock_show = MagicMock()
        mock_show.id = 1
        mock_ep = MagicMock()
        mock_ep.id = 10
        mock_repo.upsert_show.return_value = mock_show
        mock_repo.upsert_episode.return_value = mock_ep

        with (
            patch.object(client, "get_all_items", return_value=simkl_data),
            patch("show_tracker.storage.repository.WatchRepository", return_value=mock_repo),
        ):
            count = client.import_history(mock_db)

        assert count == 2
        client.close()

    def test_import_skips_episodes_without_title(self, tmp_path: Path) -> None:
        token_path = tmp_path / "tok.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() + 9999}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)

        simkl_data = [
            {
                "show": {"title": ""},  # empty title — should be skipped
                "seasons": [{"number": 1, "episodes": [{"number": 1}]}],
            }
        ]

        mock_db = MagicMock()
        with patch.object(client, "get_all_items", return_value=simkl_data):
            count = client.import_history(mock_db)

        assert count == 0
        client.close()

    def test_import_returns_zero_on_empty_history(self, tmp_path: Path) -> None:
        token_path = tmp_path / "tok.json"
        token_path.write_text(json.dumps({"access_token": "tok", "expires_at": time.time() + 9999}))
        from show_tracker.sync.simkl import SimklClient

        client = SimklClient("cid", "csecret", token_path=token_path)
        mock_db = MagicMock()
        with patch.object(client, "get_all_items", return_value=[]):
            count = client.import_history(mock_db)

        assert count == 0
        client.close()
