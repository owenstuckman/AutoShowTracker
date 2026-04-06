"""Tests for confidence scoring logic.

Covers calculate_confidence() across source types, bonuses, penalties,
clamping behaviour, and URL-match interactions.
"""

from __future__ import annotations

import pytest

from show_tracker.identification.confidence import (
    _BONUS_EXACT_SEASON_EPISODE,
    _BONUS_HIGH_FUZZY,
    _BONUS_URL_PLATFORM_MATCH,
    _PENALTY_ABBREVIATED_TITLE,
    _PENALTY_NO_SEASON,
    _PENALTY_OCR_SOURCE,
    _SOURCE_BASE,
    calculate_confidence,
)
from show_tracker.identification.parser import ParseResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_parse_result(
    title: str = "Breaking Bad",
    season: int | None = 1,
    episode: int | None = 5,
    content_type: str = "episode",
) -> ParseResult:
    """Return a minimal ParseResult for testing."""
    return ParseResult(
        title=title,
        season=season,
        episode=episode,
        content_type=content_type,
        source_type="unknown",
        raw_input=title,
    )


# ---------------------------------------------------------------------------
# TestSourceBaseConfidence
# ---------------------------------------------------------------------------


class TestSourceBaseConfidence:
    """Base confidence comes from the source-reliability table."""

    def _score_for_source(self, source: str) -> float:
        """Return the score with a neutral tmdb_match_score of 0.5."""
        pr = _make_parse_result()
        return calculate_confidence(pr, 0.5, source, "guessit+tmdb_fuzzy")

    def test_plex_base(self) -> None:
        # plex base = 0.90; avg with 0.5 tmdb = 0.70
        expected = (0.90 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("plex") == pytest.approx(expected)

    def test_smtc_base(self) -> None:
        expected = (0.70 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("smtc") == pytest.approx(expected)

    def test_mpris_base(self) -> None:
        expected = (0.70 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("mpris") == pytest.approx(expected)

    def test_browser_title_base(self) -> None:
        expected = (0.60 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("browser_title") == pytest.approx(expected)

    def test_browser_url_base(self) -> None:
        expected = (0.85 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("browser_url") == pytest.approx(expected)

    def test_filename_base(self) -> None:
        expected = (0.65 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("filename") == pytest.approx(expected)

    def test_youtube_base(self) -> None:
        expected = (0.55 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("youtube") == pytest.approx(expected)

    def test_window_title_base(self) -> None:
        # actual value for window_title is 0.55
        expected = (0.55 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("window_title") == pytest.approx(expected)

    def test_ocr_base(self) -> None:
        # ocr base = 0.40; plus the OCR penalty
        expected = (0.40 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE + _PENALTY_OCR_SOURCE
        assert self._score_for_source("ocr") == pytest.approx(expected)

    def test_unknown_base(self) -> None:
        expected = (0.50 + 0.5) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert self._score_for_source("unknown") == pytest.approx(expected)

    def test_unrecognised_source_falls_back_to_unknown(self) -> None:
        """A source not in the table must use the 'unknown' default."""
        pr = _make_parse_result()
        score_unknown = calculate_confidence(pr, 0.5, "unknown", "guessit+tmdb_fuzzy")
        score_novel = calculate_confidence(pr, 0.5, "totally_new_source", "guessit+tmdb_fuzzy")
        assert score_novel == pytest.approx(score_unknown)

    def test_source_base_table_completeness(self) -> None:
        """All expected keys are present in the private table."""
        expected_keys = {
            "plex",
            "smtc",
            "mpris",
            "browser_title",
            "browser_url",
            "filename",
            "youtube",
            "window_title",
            "ocr",
            "unknown",
        }
        assert expected_keys.issubset(set(_SOURCE_BASE.keys()))


# ---------------------------------------------------------------------------
# TestBonusScoring
# ---------------------------------------------------------------------------


class TestBonusScoring:
    """Bonus adjustments raise the score above the base average."""

    def test_exact_url_match_method_gives_bonus(self) -> None:
        """match_method='exact_url' triggers _BONUS_URL_PLATFORM_MATCH.

        Use 'ocr' with a low tmdb score so both values stay well below 1.0.
        """
        pr = _make_parse_result()
        score_url = calculate_confidence(pr, 0.3, "ocr", "exact_url")
        score_fuzzy = calculate_confidence(pr, 0.3, "ocr", "guessit+tmdb_fuzzy")
        assert score_url - score_fuzzy == pytest.approx(_BONUS_URL_PLATFORM_MATCH)

    def test_season_and_episode_present_gives_bonus(self) -> None:
        """Both season+episode present triggers _BONUS_EXACT_SEASON_EPISODE."""
        with_both = _make_parse_result(season=2, episode=3)
        without_both = _make_parse_result(season=None, episode=None)
        score_with = calculate_confidence(with_both, 0.8, "smtc", "guessit+tmdb_fuzzy")
        score_without = calculate_confidence(without_both, 0.8, "smtc", "guessit+tmdb_fuzzy")
        assert score_with - score_without == pytest.approx(_BONUS_EXACT_SEASON_EPISODE)

    def test_high_fuzzy_score_gives_bonus(self) -> None:
        """tmdb_match_score >= 0.95 triggers _BONUS_HIGH_FUZZY.

        Use 'ocr' as the source so bonuses/penalties keep the score well below
        1.0 and clamping does not interfere with the arithmetic check.
        """
        pr = _make_parse_result()
        # ocr: base=0.40, penalty=-0.10, s+e bonus=+0.10
        # high: (0.40+0.95)/2 + 0.10 + 0.08 - 0.10 = 0.755
        # low:  (0.40+0.80)/2 + 0.10       - 0.10 = 0.60
        score_high = calculate_confidence(pr, 0.95, "ocr", "guessit+tmdb_fuzzy")
        score_low = calculate_confidence(pr, 0.80, "ocr", "guessit+tmdb_fuzzy")
        diff_from_avg = (0.95 - 0.80) / 2.0
        assert score_high - score_low == pytest.approx(_BONUS_HIGH_FUZZY + diff_from_avg)

    def test_fuzzy_score_below_095_no_high_fuzzy_bonus(self) -> None:
        """tmdb_match_score of 0.94 should NOT trigger the high-fuzzy bonus."""
        pr = _make_parse_result()
        score_094 = calculate_confidence(pr, 0.94, "smtc", "guessit+tmdb_fuzzy")
        # If the bonus were applied the score would be higher; manually compute expected
        base = _SOURCE_BASE["smtc"]
        expected = (base + 0.94) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert score_094 == pytest.approx(expected)

    def test_exactly_095_triggers_bonus(self) -> None:
        """Boundary: tmdb_match_score == 0.95 must apply the high-fuzzy bonus.

        Use 'ocr' to keep the raw sum below 1.0 so clamping doesn't mask the bonus.
        ocr base=0.40, penalty=-0.10:
          (0.40+0.95)/2 + 0.10 + 0.08 - 0.10 = 0.755
        """
        pr = _make_parse_result()
        base = _SOURCE_BASE["ocr"]
        expected = (
            (base + 0.95) / 2.0
            + _BONUS_EXACT_SEASON_EPISODE
            + _BONUS_HIGH_FUZZY
            + _PENALTY_OCR_SOURCE
        )
        assert calculate_confidence(pr, 0.95, "ocr", "guessit+tmdb_fuzzy") == pytest.approx(
            expected
        )

    def test_all_bonuses_stack(self) -> None:
        """URL match + season/ep + high fuzzy score all add up."""
        pr = _make_parse_result(season=1, episode=1)
        base = _SOURCE_BASE["browser_url"]
        expected = (
            (base + 1.0) / 2.0
            + _BONUS_URL_PLATFORM_MATCH
            + _BONUS_EXACT_SEASON_EPISODE
            + _BONUS_HIGH_FUZZY
        )
        # May be capped at 1.0
        expected_clamped = min(1.0, expected)
        result = calculate_confidence(pr, 1.0, "browser_url", "exact_url")
        assert result == pytest.approx(expected_clamped)


# ---------------------------------------------------------------------------
# TestPenaltyScoring
# ---------------------------------------------------------------------------


class TestPenaltyScoring:
    """Penalties reduce the score below the base average."""

    def test_missing_season_penalty(self) -> None:
        """Episode present but season missing triggers _PENALTY_NO_SEASON."""
        with_season = _make_parse_result(season=1, episode=3)
        without_season = _make_parse_result(season=None, episode=3)
        score_with = calculate_confidence(with_season, 0.8, "smtc", "guessit+tmdb_fuzzy")
        score_without = calculate_confidence(without_season, 0.8, "smtc", "guessit+tmdb_fuzzy")
        # with_season has season+ep bonus, without_season has no_season penalty
        expected_diff = _BONUS_EXACT_SEASON_EPISODE - _PENALTY_NO_SEASON
        assert score_with - score_without == pytest.approx(expected_diff)

    def test_no_penalty_when_both_missing(self) -> None:
        """No season AND no episode — the no-season penalty should NOT apply."""
        pr = _make_parse_result(season=None, episode=None)
        base = _SOURCE_BASE["smtc"]
        expected = (base + 0.8) / 2.0
        assert calculate_confidence(pr, 0.8, "smtc", "guessit+tmdb_fuzzy") == pytest.approx(
            expected
        )

    def test_ocr_source_penalty(self) -> None:
        """OCR source triggers _PENALTY_OCR_SOURCE."""
        pr = _make_parse_result()
        base = _SOURCE_BASE["ocr"]
        expected = (base + 0.8) / 2.0 + _BONUS_EXACT_SEASON_EPISODE + _PENALTY_OCR_SOURCE
        assert calculate_confidence(pr, 0.8, "ocr", "guessit+tmdb_fuzzy") == pytest.approx(expected)

    def test_short_title_penalty(self) -> None:
        """Title with 5 or fewer characters triggers _PENALTY_ABBREVIATED_TITLE."""
        short_pr = _make_parse_result(title="ABC")
        normal_pr = _make_parse_result(title="Breaking Bad")
        score_short = calculate_confidence(short_pr, 0.8, "smtc", "guessit+tmdb_fuzzy")
        score_normal = calculate_confidence(normal_pr, 0.8, "smtc", "guessit+tmdb_fuzzy")
        assert score_normal - score_short == pytest.approx(-_PENALTY_ABBREVIATED_TITLE)

    def test_exactly_5_chars_triggers_penalty(self) -> None:
        """Boundary: title of exactly 5 characters should trigger the penalty."""
        pr = _make_parse_result(title="ABCde")
        base = _SOURCE_BASE["smtc"]
        expected = (base + 0.8) / 2.0 + _BONUS_EXACT_SEASON_EPISODE + _PENALTY_ABBREVIATED_TITLE
        assert calculate_confidence(pr, 0.8, "smtc", "guessit+tmdb_fuzzy") == pytest.approx(
            expected
        )

    def test_6_chars_no_abbreviated_penalty(self) -> None:
        """Title of 6 characters should NOT trigger the abbreviated-title penalty."""
        pr = _make_parse_result(title="ABCDEF")
        base = _SOURCE_BASE["smtc"]
        expected = (base + 0.8) / 2.0 + _BONUS_EXACT_SEASON_EPISODE
        assert calculate_confidence(pr, 0.8, "smtc", "guessit+tmdb_fuzzy") == pytest.approx(
            expected
        )


# ---------------------------------------------------------------------------
# TestCapAt1
# ---------------------------------------------------------------------------


class TestCapAt1:
    """Confidence must never exceed 1.0 regardless of bonus stacking."""

    def test_perfect_plex_match_capped(self) -> None:
        pr = _make_parse_result()
        result = calculate_confidence(pr, 1.0, "plex", "exact_url")
        assert result <= 1.0

    def test_high_score_is_exactly_one(self) -> None:
        """All bonuses active on the most reliable source should cap at 1.0."""
        pr = _make_parse_result(season=1, episode=1)
        result = calculate_confidence(pr, 1.0, "plex", "exact_url")
        assert result == pytest.approx(1.0)

    def test_floor_is_zero(self) -> None:
        """Score must not go below 0.0 even with max penalties."""
        pr = _make_parse_result(title="AB", season=None, episode=1)
        result = calculate_confidence(pr, 0.0, "ocr", "guessit+tmdb_fuzzy")
        assert result >= 0.0

    @pytest.mark.parametrize("source", list(_SOURCE_BASE.keys()))
    def test_all_sources_within_bounds(self, source: str) -> None:
        """For every known source, score is always in [0, 1]."""
        pr = _make_parse_result()
        for score in (0.0, 0.5, 1.0):
            result = calculate_confidence(pr, score, source, "guessit+tmdb_fuzzy")
            assert 0.0 <= result <= 1.0, (
                f"score={result} out of range for source={source}, tmdb={score}"
            )


# ---------------------------------------------------------------------------
# TestConfidenceWithUrlMatch
# ---------------------------------------------------------------------------


class TestConfidenceWithUrlMatch:
    """Passing match_method='exact_url' should raise confidence."""

    def test_exact_url_raises_over_fuzzy(self) -> None:
        pr = _make_parse_result()
        score_url = calculate_confidence(pr, 0.85, "browser_url", "exact_url")
        score_fuzzy = calculate_confidence(pr, 0.85, "browser_url", "guessit+tmdb_fuzzy")
        assert score_url > score_fuzzy

    def test_exact_url_bonus_magnitude(self) -> None:
        """Use ocr/low-score to avoid clamping."""
        pr = _make_parse_result()
        score_url = calculate_confidence(pr, 0.3, "ocr", "exact_url")
        score_fuzzy = calculate_confidence(pr, 0.3, "ocr", "guessit+tmdb_fuzzy")
        assert score_url - score_fuzzy == pytest.approx(_BONUS_URL_PLATFORM_MATCH)

    def test_alias_lookup_method_no_url_bonus(self) -> None:
        """alias_lookup method does not trigger URL bonus. Use ocr to avoid clamping."""
        pr = _make_parse_result()
        score_alias = calculate_confidence(pr, 0.3, "ocr", "alias_lookup")
        score_url = calculate_confidence(pr, 0.3, "ocr", "exact_url")
        assert score_url - score_alias == pytest.approx(_BONUS_URL_PLATFORM_MATCH)

    def test_cache_hit_method_no_url_bonus(self) -> None:
        """cache_hit method does not trigger URL bonus. Use ocr to avoid clamping."""
        pr = _make_parse_result()
        score_cache = calculate_confidence(pr, 0.3, "ocr", "cache_hit")
        score_url = calculate_confidence(pr, 0.3, "ocr", "exact_url")
        assert score_url - score_cache == pytest.approx(_BONUS_URL_PLATFORM_MATCH)

    def test_zero_tmdb_score_with_url_match(self) -> None:
        """Even with tmdb_score=0.0 an exact_url match still adds the bonus."""
        pr = _make_parse_result()
        base = _SOURCE_BASE["browser_url"]
        expected = (base + 0.0) / 2.0 + _BONUS_URL_PLATFORM_MATCH + _BONUS_EXACT_SEASON_EPISODE
        result = calculate_confidence(pr, 0.0, "browser_url", "exact_url")
        assert result == pytest.approx(max(0.0, min(1.0, expected)))
