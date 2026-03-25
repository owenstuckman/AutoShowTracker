"""URL pattern matching engine for streaming platforms.

Matches URLs against known patterns for Netflix, YouTube, Crunchyroll, Plex,
Disney+, Hulu, Amazon Prime Video, HBO Max, and generic pirate site structures.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UrlMatchResult:
    """Result from matching a URL against known platform patterns."""

    platform: str
    id_type: str
    platform_id: str | None = None
    slug: str | None = None
    season: int | None = None
    episode: int | None = None


# Each entry: (compiled regex, platform, id_type, extractor function)
# The extractor receives the regex match object and returns a dict of UrlMatchResult fields.
_URL_PATTERNS: list[tuple[re.Pattern[str], str, str, Callable[[re.Match[str]], dict[str, Any]]]] = [
    # Netflix: /watch/<content_id>
    (
        re.compile(r"netflix\.com/watch/(\d+)", re.IGNORECASE),
        "netflix",
        "netflix_content_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # YouTube: /watch?v=<video_id>
    (
        re.compile(r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)", re.IGNORECASE),
        "youtube",
        "youtube_video_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # Crunchyroll: /watch/<id>/<slug>
    (
        re.compile(r"crunchyroll\.com/(?:.*/)?watch/[^/]*/(.+?)(?:\?|$)", re.IGNORECASE),
        "crunchyroll",
        "crunchyroll_slug",
        lambda m: {"slug": m.group(1)},
    ),
    # Plex: web interface with metadata key
    (
        re.compile(
            r"plex\.tv/web/.*key=%2Flibrary%2Fmetadata%2F(\d+)", re.IGNORECASE
        ),
        "plex",
        "plex_metadata_key",
        lambda m: {"platform_id": m.group(1)},
    ),
    # Disney+: /video/<content_id>
    (
        re.compile(r"disneyplus\.com/video/([a-zA-Z0-9-]+)", re.IGNORECASE),
        "disney_plus",
        "disney_content_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # Hulu: /watch/<content_id>
    (
        re.compile(r"hulu\.com/watch/([a-zA-Z0-9-]+)", re.IGNORECASE),
        "hulu",
        "hulu_content_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # Amazon Prime Video: /detail/<content_id> or /gp/video/detail/<content_id>
    (
        re.compile(
            r"(?:primevideo|amazon)\.com/(?:gp/video/)?detail/([a-zA-Z0-9]+)", re.IGNORECASE
        ),
        "amazon_prime",
        "amazon_content_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # HBO Max / Max: /play/<content_id> or specific episode URN pattern
    (
        re.compile(r"(?:play\.hbomax|play\.max)\.com/.*/([a-zA-Z0-9:-]+)", re.IGNORECASE),
        "hbo_max",
        "hbo_content_id",
        lambda m: {"platform_id": m.group(1)},
    ),
    # Generic pirate: URL slug containing SxxExx pattern
    # e.g., /watch/law-and-order-svu-s03e07
    (
        re.compile(
            r"/(?:watch|stream|play|view)/([a-z0-9-]+-s(\d{1,2})e(\d{1,2}))", re.IGNORECASE
        ),
        "generic",
        "url_slug_with_episode",
        lambda m: {
            "slug": m.group(1),
            "season": int(m.group(2)),
            "episode": int(m.group(3)),
        },
    ),
    # Generic pirate: structured /show/<slug>/season-<n>/episode-<n>
    (
        re.compile(
            r"/(?:show|series|tv)/([a-z0-9-]+)/season-?(\d+)/episode-?(\d+)", re.IGNORECASE
        ),
        "generic",
        "url_structured",
        lambda m: {
            "slug": m.group(1),
            "season": int(m.group(2)),
            "episode": int(m.group(3)),
        },
    ),
]


def match_url(url: str) -> UrlMatchResult | None:
    """Match a URL against known platform patterns.

    Tries each pattern in order and returns the first match.

    Args:
        url: The URL to match.

    Returns:
        A UrlMatchResult if a pattern matches, or None.
    """
    if not url:
        return None

    for pattern, platform, id_type, extractor in _URL_PATTERNS:
        m = pattern.search(url)
        if m:
            try:
                fields = extractor(m)
            except Exception:
                logger.exception("URL pattern extractor failed for %r", url)
                continue

            return UrlMatchResult(
                platform=platform,
                id_type=id_type,
                platform_id=fields.get("platform_id"),
                slug=fields.get("slug"),
                season=fields.get("season"),
                episode=fields.get("episode"),
            )

    return None
