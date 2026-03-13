"""Parsing layer for raw media strings.

Extracts structured data (show name, season, episode, etc.) from raw strings
originating from browser titles, SMTC metadata, filenames, and other sources.
Uses guessit internally with preprocessing tailored to each source type.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from show_tracker.identification.url_patterns import UrlMatchResult

logger = logging.getLogger(__name__)

# Browser title suffixes to strip (platform branding)
_PLATFORM_SUFFIXES: list[str] = [
    r"\s*\|\s*Netflix$",
    r"\s*-\s*YouTube$",
    r"\s*\|\s*Hulu$",
    r"\s*\|\s*Disney\+$",
    r"\s*\|\s*Amazon Prime Video$",
    r"\s*-\s*Crunchyroll$",
    r"\s*\|\s*HBO Max$",
    r"\s*\|\s*Max$",
    r"\s*-\s*Watch Free.*$",
    r"\s*-\s*Watch Online.*$",
    r"\s*-\s*Plex$",
    r"\s*\|\s*Plex$",
    r"\s*\|\s*Peacock$",
    r"\s*\|\s*Paramount\+$",
    r"\s*\|\s*Apple TV\+?$",
]

# Noise words commonly found in streaming/pirate browser titles
_NOISE_WORDS: list[str] = [
    "watch",
    "free",
    "hd",
    "online",
    "streaming",
    "full episode",
]


@dataclass(frozen=True)
class ParseResult:
    """Structured result from parsing a raw media string."""

    title: str
    season: int | None = None
    episode: int | None = None
    year: int | None = None
    episode_title: str | None = None
    content_type: str = "unknown"  # "episode", "movie", "unknown"
    source_type: str = "unknown"
    raw_input: str = ""
    url_match: UrlMatchResult | None = field(default=None, compare=False)


def preprocess_for_guessit(raw_string: str, source_type: str) -> str:
    """Clean a raw string before passing it to guessit.

    Strips platform branding suffixes, removes noise words for browser sources,
    and normalizes whitespace.

    Args:
        raw_string: The raw title/filename string.
        source_type: Origin of the string (e.g. "browser_title", "smtc", "filename",
                     "youtube", "plex").

    Returns:
        Cleaned string suitable for guessit parsing.
    """
    cleaned = raw_string

    # Strip platform suffixes (applies to all source types)
    for pattern in _PLATFORM_SUFFIXES:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    # Remove noise words only for browser titles
    if source_type in ("browser_title", "youtube"):
        for word in _NOISE_WORDS:
            cleaned = re.sub(rf"\b{re.escape(word)}\b", "", cleaned, flags=re.IGNORECASE)

    # Strip trailing " - VLC media player" style suffixes from window titles
    if source_type in ("smtc", "window_title"):
        cleaned = re.sub(r"\s*-\s*VLC media player$", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*-\s*mpv$", "", cleaned, flags=re.IGNORECASE)

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    return cleaned


def parse_media_string(
    raw_string: str,
    source_type: str = "unknown",
    url_match: UrlMatchResult | None = None,
) -> ParseResult:
    """Parse a raw media string into structured data.

    Uses guessit internally after preprocessing. Handles all common input formats:
    pirate filenames, browser titles, SMTC metadata, YouTube titles, and Plex metadata.

    Args:
        raw_string: The raw string to parse.
        source_type: Origin type (e.g. "browser_title", "smtc", "filename", "youtube", "plex").
        url_match: Optional pre-matched URL result to incorporate.

    Returns:
        A ParseResult with extracted structured data.
    """
    try:
        from guessit import guessit
    except ImportError:
        logger.error("guessit is not installed; cannot parse media string")
        return ParseResult(
            title=raw_string,
            content_type="unknown",
            source_type=source_type,
            raw_input=raw_string,
            url_match=url_match,
        )

    cleaned = preprocess_for_guessit(raw_string, source_type)

    try:
        result = guessit(cleaned)
    except Exception:
        logger.exception("guessit failed to parse: %r", cleaned)
        return ParseResult(
            title=cleaned,
            content_type="unknown",
            source_type=source_type,
            raw_input=raw_string,
            url_match=url_match,
        )

    # Extract fields from guessit result
    title = str(result.get("title", cleaned))
    season = result.get("season")
    episode = result.get("episode")
    year = result.get("year")
    episode_title = result.get("episode_title")

    # guessit returns type as "episode" or "movie"
    guessit_type = str(result.get("type", "unknown"))
    if guessit_type == "episode":
        content_type = "episode"
    elif guessit_type == "movie":
        content_type = "movie"
    else:
        content_type = "unknown"

    # If guessit found an episode number but no season, still mark as episode
    if episode is not None and content_type == "unknown":
        content_type = "episode"

    # Handle multi-episode: guessit may return a list for episode
    if isinstance(episode, list):
        episode = episode[0]  # Take the first episode number

    # If URL match provides season/episode that guessit missed, incorporate them
    if url_match is not None:
        if season is None and url_match.season is not None:
            season = url_match.season
        if episode is None and url_match.episode is not None:
            episode = url_match.episode
        if season is not None and episode is not None:
            content_type = "episode"

    # Ensure integer types
    season = int(season) if season is not None else None
    episode = int(episode) if episode is not None else None
    year = int(year) if year is not None else None

    return ParseResult(
        title=title,
        season=season,
        episode=episode,
        year=year,
        episode_title=episode_title,
        content_type=content_type,
        source_type=source_type,
        raw_input=raw_string,
        url_match=url_match,
    )
