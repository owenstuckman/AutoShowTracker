"""Trakt.tv API client for import and two-way sync.

Implements OAuth2 device flow authentication (no redirect URI needed),
watch history import, and scrobble export.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from show_tracker.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

TRAKT_BASE_URL = "https://api.trakt.tv"
TRAKT_API_VERSION = "2"


class TraktError(Exception):
    """Base exception for Trakt API errors."""


class TraktAuthError(TraktError):
    """Authentication failed or token expired."""


class TraktClient:
    """Client for the Trakt.tv API.

    Args:
        client_id: Trakt API client ID (from trakt.tv/oauth/applications).
        client_secret: Trakt API client secret.
        token_path: Path to store/load OAuth tokens.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = token_path or Path.home() / ".show-tracker" / "trakt_token.json"
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0.0
        self._client = httpx.Client(
            base_url=TRAKT_BASE_URL,
            timeout=15.0,
            headers={
                "Content-Type": "application/json",
                "trakt-api-version": TRAKT_API_VERSION,
                "trakt-api-key": client_id,
            },
        )
        self._load_token()

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TraktClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- Authentication (OAuth2 Device Flow) --------------------------------

    def start_device_auth(self) -> dict[str, Any]:
        """Start the OAuth2 device flow.

        Returns:
            Dict with user_code, verification_url, device_code, expires_in,
            interval (seconds between polls).
        """
        resp = self._client.post("/oauth/device/code", json={
            "client_id": self.client_id,
        })
        if not resp.is_success:
            raise TraktError(f"Device auth failed: {resp.status_code}")
        result: dict[str, Any] = resp.json()
        return result

    def poll_device_auth(self, device_code: str, interval: int = 5, timeout: int = 600) -> bool:
        """Poll for device authorization completion.

        Args:
            device_code: From start_device_auth response.
            interval: Seconds between poll attempts.
            timeout: Max seconds to wait.

        Returns:
            True if authenticated, False if timed out.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            resp = self._client.post("/oauth/device/token", json={
                "code": device_code,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            })

            if resp.status_code == 200:
                data = resp.json()
                self._access_token = data["access_token"]
                self._refresh_token = data.get("refresh_token")
                self._expires_at = data.get("created_at", time.time()) + data.get("expires_in", 7776000)
                self._save_token()
                logger.info("Trakt authentication successful")
                return True
            elif resp.status_code == 400:
                # Pending — user hasn't authorized yet
                time.sleep(interval)
                continue
            elif resp.status_code == 404:
                raise TraktError("Invalid device code")
            elif resp.status_code == 409:
                raise TraktError("Device code already approved")
            elif resp.status_code == 410:
                raise TraktError("Device code expired")
            elif resp.status_code == 418:
                raise TraktError("User denied authorization")
            elif resp.status_code == 429:
                time.sleep(interval * 2)
                continue
            else:
                raise TraktError(f"Unexpected status {resp.status_code}")

        return False

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    # -- Watch History Import -----------------------------------------------

    def get_watched_shows(self) -> list[dict[str, Any]]:
        """Fetch the user's watched shows from Trakt.

        Returns:
            List of show dicts with seasons/episodes and TMDb IDs.
        """
        self._ensure_auth()
        resp = self._authed_get("/users/me/watched/shows?extended=noseasons")
        if isinstance(resp, dict):
            return [resp]
        return resp

    def get_watch_history(
        self,
        media_type: str = "shows",
        page: int = 1,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch paginated watch history.

        Args:
            media_type: "shows", "movies", or "episodes"
            page: Page number (1-based).
            limit: Items per page.

        Returns:
            List of history entry dicts.
        """
        self._ensure_auth()
        resp = self._authed_get(
            f"/users/me/history/{media_type}",
            params={"page": str(page), "limit": str(limit)},
        )
        if isinstance(resp, dict):
            return [resp]
        return resp

    def get_all_episode_history(self) -> list[dict[str, Any]]:
        """Fetch complete episode watch history (all pages)."""
        all_history: list[dict[str, Any]] = []
        page = 1

        while True:
            batch = self.get_watch_history("episodes", page=page, limit=100)
            if not batch:
                break
            all_history.extend(batch)
            page += 1

        return all_history

    # -- Scrobble Export ----------------------------------------------------

    def scrobble_start(self, episode_ids: dict[str, Any], progress: float = 0.0) -> dict[str, Any]:
        """Send a scrobble start event to Trakt.

        Args:
            episode_ids: Dict with "trakt", "tmdb", or "tvdb" ID.
            progress: Playback progress percentage (0-100).
        """
        self._ensure_auth()
        return self._authed_post("/scrobble/start", json={
            "episode": {"ids": episode_ids},
            "progress": progress,
        })

    def scrobble_stop(self, episode_ids: dict[str, Any], progress: float = 100.0) -> dict[str, Any]:
        """Send a scrobble stop event to Trakt."""
        self._ensure_auth()
        return self._authed_post("/scrobble/stop", json={
            "episode": {"ids": episode_ids},
            "progress": progress,
        })

    def add_to_history(self, episodes: list[dict[str, Any]]) -> dict[str, Any]:
        """Batch-add episodes to Trakt watch history.

        Args:
            episodes: List of episode dicts, each with "ids" and "watched_at".
        """
        self._ensure_auth()
        return self._authed_post("/sync/history", json={
            "episodes": episodes,
        })

    # -- Internal -----------------------------------------------------------

    def _ensure_auth(self) -> None:
        if not self._access_token:
            raise TraktAuthError("Not authenticated. Run device auth flow first.")
        if time.time() > self._expires_at:
            self._refresh_access_token()

    def _refresh_access_token(self) -> None:
        if not self._refresh_token:
            raise TraktAuthError("No refresh token available. Re-authenticate.")

        resp = self._client.post("/oauth/token", json={
            "refresh_token": self._refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
            "grant_type": "refresh_token",
        })

        if not resp.is_success:
            raise TraktAuthError(f"Token refresh failed: {resp.status_code}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._refresh_token = data.get("refresh_token", self._refresh_token)
        self._expires_at = data.get("created_at", time.time()) + data.get("expires_in", 7776000)
        self._save_token()

    def _authed_get(
        self,
        path: str,
        params: dict[str, str] | None = None,
    ) -> list[dict[str, Any]] | dict[str, Any]:
        resp = self._client.get(
            path,
            params=params,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if resp.status_code == 401:
            raise TraktAuthError("Access token expired or invalid")
        if not resp.is_success:
            raise TraktError(f"Trakt API error {resp.status_code}: {resp.text}")
        data: list[dict[str, Any]] | dict[str, Any] = resp.json()
        return data

    def _authed_post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        resp = self._client.post(
            path,
            json=json,
            headers={"Authorization": f"Bearer {self._access_token}"},
        )
        if resp.status_code == 401:
            raise TraktAuthError("Access token expired or invalid")
        if not resp.is_success:
            raise TraktError(f"Trakt API error {resp.status_code}: {resp.text}")
        result: dict[str, Any] = resp.json()
        return result

    def _save_token(self) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": self._access_token,
            "refresh_token": self._refresh_token,
            "expires_at": self._expires_at,
        }
        self.token_path.write_text(json.dumps(data), encoding="utf-8")

    def _load_token(self) -> None:
        if self.token_path.exists():
            try:
                data = json.loads(self.token_path.read_text(encoding="utf-8"))
                self._access_token = data.get("access_token")
                self._refresh_token = data.get("refresh_token")
                self._expires_at = data.get("expires_at", 0.0)
            except (json.JSONDecodeError, KeyError):
                logger.debug("Failed to load Trakt token from %s", self.token_path)


# ---------------------------------------------------------------------------
# High-level import/sync helpers
# ---------------------------------------------------------------------------

def import_from_trakt(
    trakt_client: TraktClient,
    db: DatabaseManager,
) -> dict[str, int]:
    """Import watch history from Trakt into the local database.

    Maps Trakt episodes to local show/episode records using TMDb IDs.
    Skips duplicates (episodes already watched at the same timestamp).

    Returns:
        Dict with counts: {"imported": N, "skipped": N, "failed": N}
    """
    from show_tracker.storage.models import (
        Episode,
        Show,
        WatchEvent,
    )

    history = trakt_client.get_all_episode_history()
    stats = {"imported": 0, "skipped": 0, "failed": 0}

    with db.get_watch_session() as session:
        for entry in history:
            try:
                ep_data = entry.get("episode", {})
                show_data = entry.get("show", {})
                watched_at = entry.get("watched_at", "")

                tmdb_show_id = show_data.get("ids", {}).get("tmdb")
                season_num = ep_data.get("season")
                episode_num = ep_data.get("number")

                if not tmdb_show_id or season_num is None or episode_num is None:
                    stats["failed"] += 1
                    continue

                # Find or create the show
                show = session.query(Show).filter(Show.tmdb_id == tmdb_show_id).first()
                if not show:
                    show = Show(
                        tmdb_id=tmdb_show_id,
                        title=show_data.get("title", "Unknown"),
                    )
                    session.add(show)
                    session.flush()

                # Find or create the episode
                episode = (
                    session.query(Episode)
                    .filter(
                        Episode.show_id == show.id,
                        Episode.season_number == season_num,
                        Episode.episode_number == episode_num,
                    )
                    .first()
                )
                if not episode:
                    episode = Episode(
                        show_id=show.id,
                        season_number=season_num,
                        episode_number=episode_num,
                        title=ep_data.get("title"),
                    )
                    session.add(episode)
                    session.flush()

                # Check for duplicate watch event
                existing = (
                    session.query(WatchEvent)
                    .filter(
                        WatchEvent.episode_id == episode.id,
                        WatchEvent.started_at == watched_at,
                    )
                    .first()
                )
                if existing:
                    stats["skipped"] += 1
                    continue

                # Create watch event
                watch = WatchEvent(
                    episode_id=episode.id,
                    started_at=watched_at,
                    completed=True,
                    source="trakt_import",
                    confidence=1.0,
                )
                session.add(watch)
                stats["imported"] += 1

            except Exception:
                logger.debug("Failed to import Trakt entry", exc_info=True)
                stats["failed"] += 1
                continue

        session.commit()

    logger.info(
        "Trakt import: %d imported, %d skipped, %d failed",
        stats["imported"],
        stats["skipped"],
        stats["failed"],
    )
    return stats


def export_to_trakt(
    trakt_client: TraktClient,
    db: DatabaseManager,
) -> dict[str, int]:
    """Export local watch history to Trakt.

    Pushes completed watch events that haven't been synced yet.
    Uses a sync timestamp in user_settings to track progress.

    Returns:
        Dict with counts: {"exported": N, "failed": N}
    """
    from show_tracker.storage.models import (
        Episode,
        Show,
        UserSetting,
        WatchEvent,
    )

    stats = {"exported": 0, "failed": 0}

    with db.get_watch_session() as session:
        # Get last sync timestamp
        setting = session.query(UserSetting).filter(
            UserSetting.key == "trakt_last_sync"
        ).first()
        last_sync = setting.value if setting else "1970-01-01T00:00:00Z"

        # Find unsyncced completed watch events
        events = (
            session.query(WatchEvent, Episode, Show)
            .join(Episode, WatchEvent.episode_id == Episode.id)
            .join(Show, Episode.show_id == Show.id)
            .filter(
                WatchEvent.completed == True,  # noqa: E712
                WatchEvent.started_at > last_sync,
                Show.tmdb_id.isnot(None),
            )
            .order_by(WatchEvent.started_at)
            .all()
        )

        if not events:
            return stats

        # Build batch for Trakt API
        episodes_batch = []
        for watch, episode, show in events:
            episodes_batch.append({
                "ids": {"tmdb": show.tmdb_id},
                "watched_at": watch.started_at,
                "seasons": [{
                    "number": episode.season_number,
                    "episodes": [{
                        "number": episode.episode_number,
                        "watched_at": watch.started_at,
                    }],
                }],
            })

        # Send to Trakt in batches of 100
        for i in range(0, len(episodes_batch), 100):
            batch = episodes_batch[i:i + 100]
            try:
                trakt_client.add_to_history(batch)
                stats["exported"] += len(batch)
            except TraktError:
                logger.exception("Failed to export batch to Trakt")
                stats["failed"] += len(batch)

        # Update sync timestamp
        if events:
            latest_ts = max(w.started_at for w, _, _ in events)
            if setting:
                setting.value = latest_ts
            else:
                session.add(UserSetting(key="trakt_last_sync", value=latest_ts))
            session.commit()

    return stats
