"""TMDb (The Movie Database) API client.

Provides methods for searching shows, fetching show/season/episode details,
and cross-referencing external IDs. Uses httpx for HTTP requests with proper
error handling, timeouts, and rate-limit awareness.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
DEFAULT_TIMEOUT = 10.0  # seconds
RATE_LIMIT_STATUS = 429


class TMDbError(Exception):
    """Base exception for TMDb API errors."""


class TMDbRateLimitError(TMDbError):
    """Raised when the TMDb API rate limit is exceeded."""


class TMDbNotFoundError(TMDbError):
    """Raised when the requested resource is not found on TMDb."""


class TMDbClient:
    """Client for the TMDb REST API.

    Args:
        api_key: TMDb API key (v3 auth).
        timeout: Request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=TMDB_BASE_URL,
            timeout=timeout,
            params={"api_key": api_key},
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> TMDbClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # -- internal helpers --------------------------------------------------

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request and return the JSON response.

        Raises:
            TMDbRateLimitError: If HTTP 429 is returned.
            TMDbNotFoundError: If HTTP 404 is returned.
            TMDbError: For other non-2xx responses.
        """
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise TMDbError(f"Request timed out: {path}") from exc
        except httpx.HTTPError as exc:
            raise TMDbError(f"HTTP error during request to {path}: {exc}") from exc

        if response.status_code == RATE_LIMIT_STATUS:
            retry_after = response.headers.get("Retry-After", "unknown")
            raise TMDbRateLimitError(
                f"TMDb rate limit exceeded. Retry after {retry_after}s."
            )

        if response.status_code == 404:
            raise TMDbNotFoundError(f"Resource not found: {path}")

        if not response.is_success:
            raise TMDbError(
                f"TMDb API error {response.status_code} for {path}: {response.text}"
            )

        return response.json()  # type: ignore[no-any-return]

    # -- public API --------------------------------------------------------

    def search_show(self, query: str, year: int | None = None) -> list[dict[str, Any]]:
        """Search for TV shows by name.

        Args:
            query: Show name to search for.
            year: Optional first-air-date year to narrow results.

        Returns:
            List of show result dicts from TMDb.
        """
        params: dict[str, Any] = {"query": query}
        if year is not None:
            params["first_air_date_year"] = year

        data = self._get("/search/tv", params=params)
        results: list[dict[str, Any]] = data.get("results", [])
        return results

    def get_show(self, tmdb_id: int) -> dict[str, Any]:
        """Get full details for a TV show.

        Args:
            tmdb_id: TMDb show ID.

        Returns:
            Show details dict.
        """
        return self._get(f"/tv/{tmdb_id}")

    def get_episode(
        self, tmdb_id: int, season: int, episode: int
    ) -> dict[str, Any]:
        """Get details for a specific episode.

        Args:
            tmdb_id: TMDb show ID.
            season: Season number.
            episode: Episode number.

        Returns:
            Episode details dict.
        """
        return self._get(f"/tv/{tmdb_id}/season/{season}/episode/{episode}")

    def get_season(self, tmdb_id: int, season: int) -> dict[str, Any]:
        """Get season details including its episode list.

        Args:
            tmdb_id: TMDb show ID.
            season: Season number.

        Returns:
            Season details dict with an "episodes" list.
        """
        return self._get(f"/tv/{tmdb_id}/season/{season}")

    def find_by_external_id(
        self, external_id: str, source: str
    ) -> dict[str, Any]:
        """Find TMDb entries by an external ID (e.g. IMDB, TVDB).

        Args:
            external_id: The external identifier (e.g. "tt1234567" for IMDB).
            source: The source name. Must be one of: imdb_id, freebase_mid,
                    freebase_id, tvdb_id, tvrage_id, facebook_id, instagram_id,
                    twitter_id.

        Returns:
            Dict with keys like "tv_results", "movie_results", etc.
        """
        return self._get(f"/find/{external_id}", params={"external_source": source})
