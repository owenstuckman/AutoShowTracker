"""YouTube Data API v3 client.

Fetches video metadata (title, channel, playlist info) from the YouTube API
to enhance identification of YouTube-sourced media. Used when the URL pattern
matcher extracts a YouTube video ID.

Requires ``YOUTUBE_API_KEY`` in ``.env``.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT = 10.0


class YouTubeError(Exception):
    """Base exception for YouTube API errors."""


class YouTubeClient:
    """Client for the YouTube Data API v3.

    Args:
        api_key: YouTube Data API v3 key.
        timeout: Request timeout in seconds.
    """

    def __init__(self, api_key: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.api_key = api_key
        self._client = httpx.Client(
            base_url=YOUTUBE_API_BASE,
            timeout=timeout,
            params={"key": api_key},
            headers={"Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> YouTubeClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a GET request and return the JSON response."""
        try:
            resp = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise YouTubeError(f"Request timed out: {path}") from exc
        except httpx.HTTPError as exc:
            raise YouTubeError(f"HTTP error for {path}: {exc}") from exc

        if resp.status_code == 403:
            raise YouTubeError("YouTube API quota exceeded or key invalid")
        if not resp.is_success:
            raise YouTubeError(f"YouTube API error {resp.status_code}: {resp.text}")

        return resp.json()  # type: ignore[no-any-return]

    # -- Video info --------------------------------------------------------

    def get_video(self, video_id: str) -> dict[str, Any] | None:
        """Fetch video snippet and content details.

        Args:
            video_id: YouTube video ID (11 characters).

        Returns:
            Video resource dict or None if not found.
        """
        data = self._get("/videos", params={
            "part": "snippet,contentDetails",
            "id": video_id,
        })
        items = data.get("items", [])
        return items[0] if items else None

    def get_video_snippet(self, video_id: str) -> dict[str, Any] | None:
        """Fetch just the snippet (title, channel, description) for a video.

        Returns:
            Snippet dict or None if not found.
        """
        video = self.get_video(video_id)
        if video is None:
            return None
        return video.get("snippet", {})

    # -- Playlist info -----------------------------------------------------

    def get_playlist(self, playlist_id: str) -> dict[str, Any] | None:
        """Fetch playlist metadata.

        Args:
            playlist_id: YouTube playlist ID.

        Returns:
            Playlist resource dict or None.
        """
        data = self._get("/playlists", params={
            "part": "snippet,contentDetails",
            "id": playlist_id,
        })
        items = data.get("items", [])
        return items[0] if items else None

    def get_playlist_items(
        self,
        playlist_id: str,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        """Fetch items in a playlist.

        Args:
            playlist_id: YouTube playlist ID.
            max_results: Maximum items to return (1-50).

        Returns:
            List of playlist item dicts.
        """
        data = self._get("/playlistItems", params={
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(max_results, 50),
        })
        return data.get("items", [])

    # -- Series detection --------------------------------------------------

    def detect_series_info(self, video_id: str) -> dict[str, Any] | None:
        """Attempt to extract series/episode information from a YouTube video.

        Checks:
        1. If the video belongs to a playlist that looks like a "series"
        2. If the video title contains episode numbering patterns
        3. If the channel has a series-style naming convention

        Args:
            video_id: YouTube video ID.

        Returns:
            Dict with series info if detected:
            {
                "series_name": str,
                "episode_number": int | None,
                "season_number": int | None,
                "episode_title": str,
                "playlist_id": str | None,
                "playlist_index": int | None,
                "channel_name": str,
                "is_series": bool,
            }
            or None if this doesn't look like a series.
        """
        video = self.get_video(video_id)
        if video is None:
            return None

        snippet = video.get("snippet", {})
        title = snippet.get("title", "")
        channel = snippet.get("channelTitle", "")
        description = snippet.get("description", "")

        result: dict[str, Any] = {
            "series_name": None,
            "episode_number": None,
            "season_number": None,
            "episode_title": title,
            "playlist_id": None,
            "playlist_index": None,
            "channel_name": channel,
            "is_series": False,
        }

        # Check 1: Extract episode patterns from the title
        ep_info = _extract_episode_from_title(title)
        if ep_info:
            result.update(ep_info)
            result["is_series"] = True

        # Check 2: See if the video is in a playlist
        # YouTube doesn't directly tell us which playlists a video is in
        # via the videos endpoint, but we can check the description for
        # playlist links or use the video's channel uploads
        playlist_match = re.search(r"list=([a-zA-Z0-9_-]+)", description)
        if playlist_match:
            playlist_id = playlist_match.group(1)
            result["playlist_id"] = playlist_id

            try:
                playlist = self.get_playlist(playlist_id)
                if playlist:
                    playlist_title = playlist.get("snippet", {}).get("title", "")
                    item_count = playlist.get("contentDetails", {}).get("itemCount", 0)

                    # If playlist has 3+ items, likely a series
                    if item_count >= 3:
                        result["series_name"] = playlist_title
                        result["is_series"] = True

                        # Find this video's position in the playlist
                        items = self.get_playlist_items(playlist_id)
                        for i, item in enumerate(items, start=1):
                            item_video_id = (
                                item.get("contentDetails", {}).get("videoId")
                                or item.get("snippet", {}).get("resourceId", {}).get("videoId")
                            )
                            if item_video_id == video_id:
                                result["playlist_index"] = i
                                if result["episode_number"] is None:
                                    result["episode_number"] = i
                                break
            except YouTubeError:
                logger.debug("Failed to fetch playlist %s", playlist_id)

        return result if result["is_series"] else None


def _extract_episode_from_title(title: str) -> dict[str, Any] | None:
    """Extract episode/season info from a YouTube video title.

    Common patterns:
    - "Series Name - Episode 5"
    - "Series Name S01E05"
    - "Series Name | Ep. 5"
    - "Series Name - Part 5"
    - "Series Name #5"
    - "Series Name E5 - Episode Title"
    """
    patterns = [
        # S01E05 format
        re.compile(
            r"^(?P<series>.+?)\s*[-|]\s*S(?P<season>\d{1,2})E(?P<episode>\d{1,3})",
            re.IGNORECASE,
        ),
        # "Episode 5" or "Ep. 5" or "Ep 5"
        re.compile(
            r"^(?P<series>.+?)\s*[-|]\s*(?:Episode|Ep\.?)\s*(?P<episode>\d{1,4})",
            re.IGNORECASE,
        ),
        # "Part 5"
        re.compile(
            r"^(?P<series>.+?)\s*[-|]\s*Part\s*(?P<episode>\d{1,4})",
            re.IGNORECASE,
        ),
        # "Series Name #5"
        re.compile(
            r"^(?P<series>.+?)\s*#(?P<episode>\d{1,4})",
        ),
        # "E5" at the end
        re.compile(
            r"^(?P<series>.+?)\s+E(?P<episode>\d{1,3})(?:\s|$|-)",
            re.IGNORECASE,
        ),
    ]

    for pattern in patterns:
        m = pattern.match(title)
        if m:
            groups = m.groupdict()
            return {
                "series_name": groups.get("series", "").strip(),
                "episode_number": int(groups["episode"]),
                "season_number": int(groups["season"]) if "season" in groups else None,
            }

    return None
