"""TVDb (TheTVDB) API client.

Provides search and episode lookup methods for TheTVDB v4 API,
used as a fallback when TMDb fails — especially for anime with
absolute episode numbering.

Requires a TVDb API key configured via ``TVDB_API_KEY`` in ``.env``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TVDB_BASE_URL = "https://api4.thetvdb.com/v4"
DEFAULT_TIMEOUT = 10.0


class TVDbError(Exception):
    """Base exception for TVDb API errors."""


class TVDbAuthError(TVDbError):
    """Authentication failed or token invalid."""


class TVDbNotFoundError(TVDbError):
    """Requested resource not found on TVDb."""


class TVDbClient:
    """Client for the TVDb v4 REST API.

    The TVDb v4 API uses a JWT token obtained by posting the API key
    to ``/login``. The token is cached for the lifetime of this client.

    Args:
        api_key: TVDb subscriber API key.
        timeout: Request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key
        self._token: str | None = None
        self._client = httpx.Client(
            base_url=TVDB_BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TVDbClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- Authentication -----------------------------------------------------

    def _ensure_token(self) -> None:
        """Authenticate with TVDb and cache the JWT token."""
        if self._token is not None:
            return

        try:
            resp = self._client.post("/login", json={"apikey": self.api_key})
        except httpx.HTTPError as exc:
            raise TVDbError(f"TVDb login request failed: {exc}") from exc

        if resp.status_code == 401:
            raise TVDbAuthError("TVDb API key is invalid")

        if not resp.is_success:
            raise TVDbError(f"TVDb login failed with status {resp.status_code}")

        data = resp.json()
        self._token = data.get("data", {}).get("token")
        if not self._token:
            raise TVDbError("TVDb login response did not include a token")

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute an authenticated GET request."""
        self._ensure_token()

        try:
            resp = self._client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except httpx.TimeoutException as exc:
            raise TVDbError(f"Request timed out: {path}") from exc
        except httpx.HTTPError as exc:
            raise TVDbError(f"HTTP error for {path}: {exc}") from exc

        if resp.status_code == 401:
            # Token may have expired — clear and retry once
            self._token = None
            self._ensure_token()
            resp = self._client.get(
                path,
                params=params,
                headers={"Authorization": f"Bearer {self._token}"},
            )

        if resp.status_code == 404:
            raise TVDbNotFoundError(f"Resource not found: {path}")

        if not resp.is_success:
            raise TVDbError(f"TVDb API error {resp.status_code} for {path}: {resp.text}")

        return resp.json()  # type: ignore[no-any-return]

    # -- Public API ---------------------------------------------------------

    def search(self, query: str, search_type: str = "series") -> list[dict[str, Any]]:
        """Search TVDb for series or movies.

        Args:
            query: Search query string.
            search_type: "series" or "movie".

        Returns:
            List of result dicts with id, name, year, etc.
        """
        data = self._get("/search", params={"query": query, "type": search_type})
        return data.get("data", [])

    def get_series(self, tvdb_id: int) -> dict[str, Any]:
        """Get full series details.

        Args:
            tvdb_id: TVDb series ID.

        Returns:
            Series details dict.
        """
        data = self._get(f"/series/{tvdb_id}")
        return data.get("data", {})

    def get_series_extended(self, tvdb_id: int) -> dict[str, Any]:
        """Get extended series details including episodes.

        Args:
            tvdb_id: TVDb series ID.

        Returns:
            Extended series details with seasons and episodes.
        """
        data = self._get(f"/series/{tvdb_id}/extended")
        return data.get("data", {})

    def get_series_episodes(
        self,
        tvdb_id: int,
        season_type: str = "default",
        season: int | None = None,
        page: int = 0,
    ) -> dict[str, Any]:
        """Get episodes for a series.

        Args:
            tvdb_id: TVDb series ID.
            season_type: "default" (standard numbering) or "absolute" (anime).
            season: Optional season number to filter.
            page: Pagination page (0-based).

        Returns:
            Dict with "episodes" list and pagination info.
        """
        params: dict[str, Any] = {"page": page}
        if season is not None:
            params["season"] = season

        data = self._get(f"/series/{tvdb_id}/episodes/{season_type}", params=params)
        return data.get("data", {})

    def get_episode(self, episode_id: int) -> dict[str, Any]:
        """Get details for a specific episode.

        Args:
            episode_id: TVDb episode ID.

        Returns:
            Episode details dict.
        """
        data = self._get(f"/episodes/{episode_id}")
        return data.get("data", {})

    def map_absolute_to_season_episode(
        self,
        tvdb_id: int,
        absolute_number: int,
    ) -> tuple[int, int] | None:
        """Map an absolute episode number to season/episode format.

        This is the key function for anime support — anime trackers
        typically use absolute numbering (e.g., episode 150) but TMDb
        and most databases use season/episode format.

        Args:
            tvdb_id: TVDb series ID.
            absolute_number: The absolute episode number.

        Returns:
            Tuple of (season_number, episode_number) or None if not found.
        """
        try:
            # Fetch episodes with absolute numbering
            result = self.get_series_episodes(tvdb_id, season_type="absolute")
            episodes = result.get("episodes", [])

            for ep in episodes:
                if ep.get("absoluteNumber") == absolute_number:
                    season = ep.get("seasonNumber")
                    episode = ep.get("number")
                    if season is not None and episode is not None:
                        return (season, episode)

            # If not found in first page, try paginating
            page = 1
            while True:
                result = self.get_series_episodes(
                    tvdb_id, season_type="absolute", page=page
                )
                episodes = result.get("episodes", [])
                if not episodes:
                    break

                for ep in episodes:
                    if ep.get("absoluteNumber") == absolute_number:
                        season = ep.get("seasonNumber")
                        episode = ep.get("number")
                        if season is not None and episode is not None:
                            return (season, episode)
                page += 1

        except TVDbError:
            logger.debug(
                "Failed to map absolute ep %d for TVDb series %d",
                absolute_number, tvdb_id,
                exc_info=True,
            )

        return None
