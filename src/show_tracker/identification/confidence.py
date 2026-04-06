"""Confidence scoring logic for content identification.

Computes a 0.0-1.0 confidence score based on the quality of the parse,
the TMDb fuzzy match score, the detection source reliability, and the
match method used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from show_tracker.identification.parser import ParseResult

# Base confidence by source reliability (higher = more trustworthy)
_SOURCE_BASE: dict[str, float] = {
    "plex": 0.90,
    "smtc": 0.70,
    "mpris": 0.70,
    "browser_title": 0.60,
    "browser_url": 0.85,
    "filename": 0.65,
    "youtube": 0.55,
    "window_title": 0.55,
    "ocr": 0.40,
    "unknown": 0.50,
}

# Bonus/penalty adjustments
_BONUS_EXACT_SEASON_EPISODE = 0.10
_BONUS_HIGH_FUZZY = 0.08  # applied when tmdb_match_score >= 0.95
_BONUS_URL_PLATFORM_MATCH = 0.15
_PENALTY_NO_SEASON = -0.10
_PENALTY_OCR_SOURCE = -0.10
_PENALTY_ABBREVIATED_TITLE = -0.05


def calculate_confidence(
    parse_result: ParseResult,
    tmdb_match_score: float,
    source_type: str,
    match_method: str,
) -> float:
    """Calculate a confidence score for an identification result.

    Args:
        parse_result: The structured parse output.
        tmdb_match_score: Fuzzy match ratio (0.0-1.0) between parsed title and
                          the TMDb show name. Pass 1.0 for exact/URL-based matches.
        source_type: Detection source (e.g. "smtc", "browser_title", "ocr").
        match_method: How the match was made (e.g. "exact_url", "guessit+tmdb_fuzzy",
                      "alias_lookup", "cache_hit").

    Returns:
        Confidence score clamped to [0.0, 1.0].
    """
    # Start with a base from source reliability
    base = _SOURCE_BASE.get(source_type, _SOURCE_BASE["unknown"])

    # Weight the TMDb fuzzy score into the base (average with base)
    score = (base + tmdb_match_score) / 2.0

    # --- Bonuses ---

    # URL pattern match on a known streaming platform is very reliable
    if match_method == "exact_url":
        score += _BONUS_URL_PLATFORM_MATCH

    # Both season and episode were present in the raw parse
    if parse_result.season is not None and parse_result.episode is not None:
        score += _BONUS_EXACT_SEASON_EPISODE

    # Very high TMDb fuzzy score
    if tmdb_match_score >= 0.95:
        score += _BONUS_HIGH_FUZZY

    # --- Penalties ---

    # OCR source is inherently noisy
    if source_type == "ocr":
        score += _PENALTY_OCR_SOURCE

    # No season number means more ambiguity
    if parse_result.season is None and parse_result.episode is not None:
        score += _PENALTY_NO_SEASON

    # Short titles (likely abbreviated) are less reliable
    if len(parse_result.title) <= 5:
        score += _PENALTY_ABBREVIATED_TITLE

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, score))
