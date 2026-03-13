"""Content identification and parsing pipeline.

Transforms raw detection signals (window titles, URLs, OCR text, SMTC metadata)
into canonical episode entries via parsing, URL matching, and TMDb resolution.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, TYPE_CHECKING

from show_tracker.identification.confidence import calculate_confidence
from show_tracker.identification.parser import ParseResult, parse_media_string, preprocess_for_guessit
from show_tracker.identification.resolver import EpisodeResolver, IdentificationResult
from show_tracker.identification.tmdb_client import TMDbClient
from show_tracker.identification.url_patterns import UrlMatchResult, match_url

if TYPE_CHECKING:
    from show_tracker.config import Settings

__all__ = [
    "ParseResult",
    "parse_media_string",
    "preprocess_for_guessit",
    "UrlMatchResult",
    "match_url",
    "EpisodeResolver",
    "IdentificationResult",
    "calculate_confidence",
    "identify_media",
]


async def identify_media(
    raw_string: str,
    *,
    source: str = "manual",
    url: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Convenience function: resolve a raw string to a canonical episode.

    This is the Phase 0 entry point — takes a raw string and returns a dict
    with identification results, or None if resolution failed.
    """
    if settings is None:
        from show_tracker.config import load_settings
        settings = load_settings()

    if not settings.has_tmdb_key():
        return None

    client = TMDbClient(api_key=settings.tmdb_api_key)
    resolver = EpisodeResolver(tmdb_client=client)

    try:
        result = resolver.resolve(raw_string, source_type=source, url=url)
    finally:
        client.close()

    if result.tmdb_show_id is None and result.confidence < 0.3:
        return None

    return asdict(result)
