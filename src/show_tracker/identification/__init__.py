"""Content identification and parsing pipeline.

Transforms raw detection signals (window titles, URLs, OCR text, SMTC metadata)
into canonical episode entries via parsing, URL matching, and TMDb resolution.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, TYPE_CHECKING

from show_tracker.identification.confidence import calculate_confidence
from show_tracker.identification.parser import ParseResult, parse_media_string, preprocess_for_guessit
from show_tracker.identification.resolver import EpisodeResolver, IdentificationResult, MovieIdentificationResult
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
    "MovieIdentificationResult",
    "identify_media",
]


async def identify_media(
    raw_string: str,
    *,
    source: str = "manual",
    url: str | None = None,
    media_type: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any] | None:
    """Convenience function: resolve a raw string to a canonical episode or movie.

    This is the Phase 0 entry point — takes a raw string and returns a dict
    with identification results, or None if resolution failed.

    Args:
        raw_string: The raw media string to identify.
        source: Source type hint (e.g. "browser_title", "filename").
        url: Optional URL associated with the detection.
        media_type: Force "movie" or "episode" identification. If None,
            auto-detects from the parsed result.
        settings: Application settings (loaded from env if not provided).
    """
    if settings is None:
        from show_tracker.config import load_settings
        settings = load_settings()

    if not settings.has_tmdb_key():
        return None

    client = TMDbClient(api_key=settings.tmdb_api_key)
    resolver = EpisodeResolver(tmdb_client=client)

    try:
        # Auto-detect content type if not specified
        if media_type is None:
            parsed = parse_media_string(raw_string, source)
            media_type = parsed.content_type or "episode"

        if media_type == "movie":
            result = resolver.resolve_movie(raw_string, source_type=source)
            if result.tmdb_movie_id is None and result.confidence < 0.3:
                return None
            out = asdict(result)
            out["media_type"] = "movie"
            return out
        else:
            # If this is a YouTube URL, try to enrich with YouTube API first
            url_info = match_url(url) if url else None
            if (
                url_info
                and url_info.platform == "youtube"
                and url_info.platform_id
                and settings.has_youtube_key()
            ):
                yt_enriched = _try_youtube_enrichment(
                    url_info.platform_id, settings.youtube_api_key
                )
                if yt_enriched:
                    # Use enriched data if it looks like a series
                    enriched_string = yt_enriched.get("enriched_string", raw_string)
                    result = resolver.resolve(enriched_string, source_type="youtube", url=url)
                    if result.tmdb_show_id is not None or result.confidence >= 0.3:
                        out = asdict(result)
                        out["media_type"] = "episode"
                        out["youtube_info"] = yt_enriched
                        return out

            result = resolver.resolve(raw_string, source_type=source, url=url)
            if result.tmdb_show_id is None and result.confidence < 0.3:
                return None
            out = asdict(result)
            out["media_type"] = "episode"
            return out
    finally:
        client.close()


def _try_youtube_enrichment(
    video_id: str, api_key: str
) -> dict[str, Any] | None:
    """Try to get series info from YouTube Data API.

    Returns enrichment data if the video looks like part of a series,
    or None otherwise.
    """
    try:
        from show_tracker.identification.youtube_client import YouTubeClient, YouTubeError

        yt = YouTubeClient(api_key=api_key)
        try:
            info = yt.detect_series_info(video_id)
            if info and info.get("is_series") and info.get("series_name"):
                # Build an enriched string for the resolver
                series = info["series_name"]
                ep = info.get("episode_number")
                season = info.get("season_number")
                if season and ep:
                    enriched = f"{series} S{season:02d}E{ep:02d}"
                elif ep:
                    enriched = f"{series} E{ep:02d}"
                else:
                    enriched = series

                return {
                    "enriched_string": enriched,
                    "series_name": series,
                    "episode_number": ep,
                    "season_number": season,
                    "channel_name": info.get("channel_name"),
                    "playlist_id": info.get("playlist_id"),
                    "playlist_index": info.get("playlist_index"),
                }
        finally:
            yt.close()
    except Exception:
        pass

    return None
