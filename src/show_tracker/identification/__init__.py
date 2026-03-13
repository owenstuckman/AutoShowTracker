"""Content identification and parsing pipeline.

Transforms raw detection signals (window titles, URLs, OCR text, SMTC metadata)
into canonical episode entries via parsing, URL matching, and TMDb resolution.
"""

from show_tracker.identification.confidence import calculate_confidence
from show_tracker.identification.parser import ParseResult, parse_media_string, preprocess_for_guessit
from show_tracker.identification.resolver import EpisodeResolver, IdentificationResult
from show_tracker.identification.url_patterns import UrlMatchResult, match_url

__all__ = [
    "ParseResult",
    "parse_media_string",
    "preprocess_for_guessit",
    "UrlMatchResult",
    "match_url",
    "EpisodeResolver",
    "IdentificationResult",
    "calculate_confidence",
]
