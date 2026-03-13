"""Handler for browser extension media events.

Processes incoming ``MediaEvent`` payloads from the Show Tracker browser
extension, extracts the best available metadata using a priority chain
(schema.org > Open Graph > URL patterns > page title), and converts the
result into a standardized internal event format that the detection
service can feed into the parsing/identification layers.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal event format
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BrowserMediaEvent:
    """Standardized browser media event after metadata extraction.

    This is what the detection service receives from the browser handler,
    regardless of which metadata source provided the information.
    """

    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: str = "page_load"  # play | pause | ended | heartbeat | page_load
    url: str = ""
    domain: str = ""

    # Best extracted metadata (filled from the highest-priority source)
    title: str = ""
    show_name: str = ""
    season_number: int | None = None
    episode_number: int | None = None
    content_type: str = ""  # "TVEpisode", "Movie", "VideoObject", etc.

    # Playback state (from <video> element inspection)
    is_playing: bool = False
    position_seconds: float | None = None
    duration_seconds: float | None = None

    # Provenance — which source supplied the best metadata
    metadata_source: str = ""  # "schema_org" | "open_graph" | "url_pattern" | "page_title"

    # The raw payload for debugging
    raw_payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# URL pattern matching
# ---------------------------------------------------------------------------

_URL_PATTERNS: list[tuple[str, re.Pattern[str], list[str]]] = [
    # Netflix: /watch/<content_id>
    (
        "netflix",
        re.compile(r"netflix\.com/watch/(?P<content_id>\d+)"),
        ["content_id"],
    ),
    # YouTube: /watch?v=<video_id>
    (
        "youtube",
        re.compile(r"youtube\.com/watch\?.*v=(?P<video_id>[A-Za-z0-9_-]{11})"),
        ["video_id"],
    ),
    # Crunchyroll: /watch/<id>/<slug>
    (
        "crunchyroll",
        re.compile(r"crunchyroll\.com/watch/(?P<content_id>[A-Z0-9]+)/(?P<slug>[^?]+)"),
        ["content_id", "slug"],
    ),
    # Disney+: /video/<uuid>
    (
        "disneyplus",
        re.compile(r"disneyplus\.com/video/(?P<content_id>[a-f0-9-]+)"),
        ["content_id"],
    ),
    # Hulu: /watch/<content_id>
    (
        "hulu",
        re.compile(r"hulu\.com/watch/(?P<content_id>[a-f0-9-]+)"),
        ["content_id"],
    ),
    # Amazon Prime Video: /detail/<id> or /gp/video/detail/<id>
    (
        "primevideo",
        re.compile(r"(?:primevideo|amazon)\.com/(?:gp/video/)?detail/(?P<content_id>[A-Z0-9]+)"),
        ["content_id"],
    ),
    # Generic: slug with SxxExx pattern
    (
        "generic_sxxexx",
        re.compile(
            r"/(?P<slug>[^/]*[Ss]\d{1,2}[Ee]\d{1,2}[^/]*)"
        ),
        ["slug"],
    ),
]


def _match_url(url: str) -> dict[str, Any] | None:
    """Try to extract structured info from a URL using known patterns."""
    for platform, pattern, fields in _URL_PATTERNS:
        m = pattern.search(url)
        if m:
            result: dict[str, Any] = {"platform": platform}
            for f in fields:
                result[f] = m.group(f)
            return result
    return None


# ---------------------------------------------------------------------------
# Metadata extraction helpers
# ---------------------------------------------------------------------------

# Season/episode regex for page titles and slugs.
_SXXEXX_RE = re.compile(
    r"[Ss](?P<season>\d{1,2})\s*[Ee](?P<episode>\d{1,2})"
)

_SEASON_EPISODE_WORDS_RE = re.compile(
    r"[Ss]eason\s+(?P<season>\d{1,2}).*?[Ee]pisode\s+(?P<episode>\d{1,2})",
    re.IGNORECASE,
)


def _extract_season_episode(text: str) -> tuple[int | None, int | None]:
    """Try to extract season/episode numbers from free text."""
    m = _SXXEXX_RE.search(text)
    if m:
        return int(m.group("season")), int(m.group("episode"))

    m = _SEASON_EPISODE_WORDS_RE.search(text)
    if m:
        return int(m.group("season")), int(m.group("episode"))

    return None, None


def _extract_from_schema_org(schema_items: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extract structured metadata from schema.org JSON-LD items.

    Returns a dict with ``title``, ``show_name``, ``season_number``,
    ``episode_number``, and ``content_type`` — or *None* if nothing useful.
    """
    for item in schema_items:
        item_type = item.get("type", "")
        if item_type not in ("TVEpisode", "Episode", "VideoObject", "Movie", "TVSeries"):
            continue

        result: dict[str, Any] = {
            "title": item.get("name", ""),
            "content_type": item_type,
            "show_name": "",
            "season_number": None,
            "episode_number": None,
        }

        series_name = item.get("seriesName", "")
        if series_name:
            result["show_name"] = series_name

        season = item.get("seasonNumber")
        episode = item.get("episodeNumber")
        if season is not None:
            result["season_number"] = int(season)
        if episode is not None:
            result["episode_number"] = int(episode)

        # If we got at least a title, consider it useful.
        if result["title"]:
            return result

    return None


def _extract_from_open_graph(og: dict[str, str]) -> dict[str, Any] | None:
    """Extract metadata from Open Graph tags."""
    og_title = og.get("title", "")
    if not og_title:
        return None

    og_type = og.get("type", "")
    content_type = ""
    if og_type in ("video.episode", "video.tv_show"):
        content_type = "TVEpisode"
    elif og_type == "video.movie":
        content_type = "Movie"
    elif og_type.startswith("video"):
        content_type = "VideoObject"

    season, episode = _extract_season_episode(og_title)

    show_name = og.get("video:series", "")

    return {
        "title": og_title,
        "show_name": show_name,
        "season_number": season,
        "episode_number": episode,
        "content_type": content_type,
    }


def _extract_from_page_title(page_title: str) -> dict[str, Any]:
    """Extract whatever we can from the raw page title (lowest priority)."""
    # Strip common suffixes like " | Netflix", " - YouTube"
    cleaned = re.sub(r"\s*[\|\-\u2013\u2014]\s*(Netflix|YouTube|Hulu|Crunchyroll|Disney\+|Amazon|Prime Video)\s*$", "", page_title, flags=re.IGNORECASE)
    season, episode = _extract_season_episode(cleaned)

    return {
        "title": cleaned.strip(),
        "show_name": "",
        "season_number": season,
        "episode_number": episode,
        "content_type": "",
    }


# ---------------------------------------------------------------------------
# Browser event handler
# ---------------------------------------------------------------------------


class BrowserEventHandler:
    """Processes incoming browser extension ``MediaEvent`` payloads.

    Each call to :meth:`handle_event` applies the metadata extraction
    priority chain and returns a :class:`BrowserMediaEvent`.
    """

    def handle_event(self, payload: dict[str, Any]) -> BrowserMediaEvent:
        """Process a raw browser extension event payload.

        Parameters
        ----------
        payload:
            The JSON body sent by the browser extension's background
            service worker (matches the ``MediaEvent`` TypeScript interface
            defined in ``06_BROWSER_EXTENSION.md``).

        Returns
        -------
        BrowserMediaEvent
            Standardized event with the best available metadata.
        """
        event_type = str(payload.get("type", "page_load"))
        tab_url = str(payload.get("tab_url", payload.get("metadata", {}).get("url", "")))
        timestamp_ms = payload.get("timestamp")
        metadata = payload.get("metadata", {})

        parsed_url = urlparse(tab_url)
        domain = parsed_url.netloc.removeprefix("www.")

        timestamp = datetime.now(timezone.utc)
        if timestamp_ms is not None:
            try:
                timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
            except (ValueError, TypeError, OSError):
                pass

        # Playback state from video element inspection.
        video_info = metadata.get("video", [])
        is_playing = False
        position: float | None = None
        duration: float | None = None
        if video_info and isinstance(video_info, list) and video_info[0]:
            first_video = video_info[0]
            is_playing = bool(first_video.get("playing", False))
            position = first_video.get("currentTime")
            duration = first_video.get("duration")

        # Also honour top-level position/duration (heartbeat events).
        if position is None:
            position = payload.get("position")
        if duration is None:
            duration = payload.get("duration")

        # --- Priority chain ---------------------------------------------------

        best: dict[str, Any] | None = None
        source = ""

        # 1. Schema.org structured data
        schema_items: list[dict[str, Any]] = metadata.get("schema", [])
        if schema_items:
            best = _extract_from_schema_org(schema_items)
            if best:
                source = "schema_org"

        # 2. Open Graph tags
        if best is None:
            og: dict[str, str] = metadata.get("og", {})
            if og:
                best = _extract_from_open_graph(og)
                if best:
                    source = "open_graph"

        # 3. URL pattern matching
        if best is None:
            url_match = _match_url(tab_url)
            if url_match:
                slug = url_match.get("slug", "")
                season, episode = _extract_season_episode(slug) if slug else (None, None)
                best = {
                    "title": slug.replace("-", " ").strip() if slug else "",
                    "show_name": "",
                    "season_number": season,
                    "episode_number": episode,
                    "content_type": "",
                }
                source = "url_pattern"

        # 4. Page title (fallback)
        if best is None:
            page_title = str(metadata.get("title", ""))
            if page_title:
                best = _extract_from_page_title(page_title)
                source = "page_title"

        if best is None:
            best = {
                "title": "",
                "show_name": "",
                "season_number": None,
                "episode_number": None,
                "content_type": "",
            }
            source = ""

        return BrowserMediaEvent(
            timestamp=timestamp,
            event_type=event_type,
            url=tab_url,
            domain=domain,
            title=best["title"],
            show_name=best["show_name"],
            season_number=best["season_number"],
            episode_number=best["episode_number"],
            content_type=best["content_type"],
            is_playing=is_playing,
            position_seconds=position,
            duration_seconds=duration,
            metadata_source=source,
            raw_payload=payload,
        )
