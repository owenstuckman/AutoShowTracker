"""Simkl watch history import client.

Imports watch history from Simkl using their v1 REST API.
Authentication uses OAuth2 PIN flow (no redirect URI required).

API reference: https://simkl.docs.apiary.io/
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

SIMKL_BASE_URL = "https://api.simkl.com"


class SimklError(Exception):
    """Base exception for Simkl API errors."""


class SimklAuthError(SimklError):
    """Authentication failed or token expired."""


class SimklClient:
    """Client for the Simkl v1 API.

    Supports OAuth2 PIN-based device flow (same pattern as Trakt) and
    watch history import (episodes, movies, anime).

    Args:
        client_id: Simkl API client ID (from simkl.com/settings/developer).
        client_secret: Simkl API client secret.
        token_path: Path to store/load OAuth token.
    """

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_path = token_path or Path.home() / ".show-tracker" / "simkl_token.json"
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._client = httpx.Client(
            base_url=SIMKL_BASE_URL,
            timeout=15.0,
            headers={
                "Content-Type": "application/json",
                "simkl-api-key": client_id,
            },
        )
        self._load_token()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    # -- Auth ---------------------------------------------------------------

    def start_device_auth(self) -> dict[str, Any]:
        """Begin the OAuth2 PIN device flow.

        Returns a dict with ``user_code`` (display to user) and
        ``verification_url`` (where they enter the code).
        """
        resp = self._client.get(
            "/oauth/pin",
            params={"client_id": self.client_id, "redirect": "urn:ietf:wg:oauth:2.0:oob"},
        )
        resp.raise_for_status()
        return dict(resp.json())

    def poll_device_auth(self, user_code: str) -> bool:
        """Poll to see if the user has entered the PIN.

        Returns True if authentication succeeded, False if still pending.
        Raises SimklAuthError on error or expiry.
        """
        resp = self._client.get(
            f"/oauth/pin/{user_code}",
            params={"client_id": self.client_id},
        )
        if resp.status_code == 400:
            return False  # pending
        if resp.status_code == 401:
            raise SimklAuthError("PIN expired or invalid")
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + data.get("expires_in", 30 * 24 * 3600)
        self._save_token()
        return True

    @property
    def is_authenticated(self) -> bool:
        """True if we have a valid (non-expired) access token."""
        return bool(self._access_token) and time.time() < self._expires_at

    # -- History import -----------------------------------------------------

    def get_all_items(self, item_type: str = "shows") -> list[dict[str, Any]]:
        """Fetch all watched items of a given type.

        Args:
            item_type: One of ``"shows"``, ``"movies"``, or ``"anime"``.

        Returns:
            List of item dicts from the Simkl API.
        """
        self._ensure_auth()
        resp = self._authed_get(f"/sync/all-items/{item_type}")
        data = resp.get(item_type, [])
        logger.info("Simkl: fetched %d %s", len(data), item_type)
        return list(data)

    def import_history(self, db: DatabaseManager) -> int:
        """Import Simkl watch history into the local database.

        Currently imports TV episodes only. Movies and anime support
        can be added in a future iteration.

        Args:
            db: DatabaseManager for the local watch_history.db.

        Returns:
            Number of watch events imported.
        """
        items = self.get_all_items("shows")
        imported = 0

        for show in items:
            show_info = show.get("show", {})
            title = show_info.get("title", "")
            seasons = show.get("seasons", [])
            for season in seasons:
                season_num = season.get("number")
                for ep in season.get("episodes", []):
                    ep_num = ep.get("number")
                    watched_at = ep.get("watched_at")
                    if not (title and season_num is not None and ep_num is not None):
                        continue
                    try:
                        from show_tracker.storage.repository import WatchRepository

                        with db.get_watch_session() as session:
                            repo = WatchRepository(session)
                            show_row = repo.upsert_show(tmdb_id=None, title=title)
                            ep_row = repo.upsert_episode(
                                show_id=show_row.id,
                                season_number=season_num,
                                episode_number=ep_num,
                            )
                            repo.create_watch_event(
                                episode_id=ep_row.id,
                                source="simkl_import",
                                confidence=1.0,
                                raw_input=f"{title} S{season_num:02d}E{ep_num:02d}",
                                completed=True,
                                started_at=watched_at,
                            )
                        imported += 1
                    except Exception:
                        logger.debug(
                            "Failed to import Simkl episode %s S%sE%s",
                            title,
                            season_num,
                            ep_num,
                            exc_info=True,
                        )

        logger.info("Simkl import complete: %d episodes imported", imported)
        return imported

    # -- Internal -----------------------------------------------------------

    def _ensure_auth(self) -> None:
        if not self._access_token:
            raise SimklAuthError("Not authenticated. Run device auth flow first.")
        if time.time() > self._expires_at:
            raise SimklAuthError("Simkl access token expired. Re-authenticate.")

    def _authed_get(self, path: str, **kwargs: Any) -> dict[str, Any]:
        resp = self._client.get(
            path,
            headers={"Authorization": f"Bearer {self._access_token}"},
            **kwargs,
        )
        resp.raise_for_status()
        result: dict[str, Any] = resp.json()
        return result

    def _load_token(self) -> None:
        if not self.token_path.exists():
            return
        try:
            data = json.loads(self.token_path.read_text())
            self._access_token = data.get("access_token")
            self._expires_at = float(data.get("expires_at", 0))
        except Exception:
            logger.debug("Could not load Simkl token from %s", self.token_path)

    def _save_token(self) -> None:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(
            json.dumps(
                {
                    "access_token": self._access_token,
                    "expires_at": self._expires_at,
                }
            )
        )
