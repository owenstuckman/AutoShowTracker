"""Tests for the media string parser.

Covers all input format categories from the design doc:
- Pirate filenames / VLC window titles
- Browser tab titles (Netflix, Hulu, generic streaming)
- SMTC / MPRIS metadata
- YouTube titles
- Plex clean metadata
"""

from __future__ import annotations

import pytest

from show_tracker.identification.parser import (
    ParseResult,
    parse_media_string,
    preprocess_for_guessit,
)

# ---------------------------------------------------------------------------
# preprocess_for_guessit
# ---------------------------------------------------------------------------

class TestPreprocessForGuessit:
    """Tests for the preprocessing step that cleans raw strings."""

    @pytest.mark.parametrize(
        "raw, source_type, expected_substring_removed",
        [
            ("Law & Order: SVU | Netflix", "browser_title", "Netflix"),
            ("Some Show - YouTube", "browser_title", "YouTube"),
            ("Breaking Bad | Hulu", "browser_title", "Hulu"),
            ("Loki | Disney+", "browser_title", "Disney+"),
            ("The Boys | Amazon Prime Video", "browser_title", "Amazon Prime Video"),
            ("My Hero Academia - Crunchyroll", "browser_title", "Crunchyroll"),
            ("Succession | HBO Max", "browser_title", "HBO Max"),
        ],
    )
    def test_strips_platform_suffixes(
        self, raw: str, source_type: str, expected_substring_removed: str
    ) -> None:
        result = preprocess_for_guessit(raw, source_type)
        assert expected_substring_removed not in result
        # The show title should survive
        assert len(result.strip()) > 0

    @pytest.mark.parametrize(
        "raw, expected_absent_words",
        [
            (
                "Watch Law & Order SVU Season 3 Episode 7 Free HD",
                ["Watch", "Free", "HD"],
            ),
            (
                "Law and Order SVU Online Streaming Full Episode",
                ["Online", "Streaming", "Full Episode"],
            ),
        ],
    )
    def test_removes_noise_words_for_browser_titles(
        self, raw: str, expected_absent_words: list[str]
    ) -> None:
        result = preprocess_for_guessit(raw, "browser_title")
        lower = result.lower()
        for word in expected_absent_words:
            assert word.lower() not in lower

    def test_does_not_remove_noise_words_for_filenames(self) -> None:
        raw = "watch.the.throne.s01e03.720p.mkv"
        result = preprocess_for_guessit(raw, "filename")
        # "watch" is part of the title here — should NOT be removed for filenames
        assert "watch" in result.lower()

    def test_normalizes_whitespace(self) -> None:
        raw = "  Law  &   Order   SVU  "
        result = preprocess_for_guessit(raw, "browser_title")
        assert "  " not in result
        assert result == result.strip()

    def test_strips_vlc_suffix_for_smtc(self) -> None:
        raw = "law.and.order.svu.s03e07.720p.mkv - VLC media player"
        result = preprocess_for_guessit(raw, "smtc")
        assert "VLC media player" not in result

    def test_strips_mpv_suffix(self) -> None:
        raw = "Breaking Bad S01E01 - mpv"
        result = preprocess_for_guessit(raw, "window_title")
        assert "mpv" not in result


# ---------------------------------------------------------------------------
# parse_media_string — pirate filenames
# ---------------------------------------------------------------------------

class TestParseFilenames:
    """Pirate filenames and VLC window titles."""

    def test_standard_sxxexx(self) -> None:
        result = parse_media_string(
            "law.and.order.svu.s03e07.720p.bluray.x264-demand.mkv",
            source_type="filename",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"
        assert "law" in result.title.lower()

    def test_sxxexx_with_episode_title(self) -> None:
        result = parse_media_string(
            "Law.&.Order.SVU.S03E07.Sacrifice.720p.WEB-DL.mkv",
            source_type="filename",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_bracket_subgroup_format(self) -> None:
        result = parse_media_string(
            "[SubGroup] Law and Order SVU - 03x07 (720p).mkv",
            source_type="filename",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_preserves_raw_input(self) -> None:
        raw = "some.show.s01e01.mkv"
        result = parse_media_string(raw, source_type="filename")
        assert result.raw_input == raw


# ---------------------------------------------------------------------------
# parse_media_string — browser titles
# ---------------------------------------------------------------------------

class TestParseBrowserTitles:
    """Browser tab titles from streaming sites."""

    def test_season_episode_with_noise(self) -> None:
        result = parse_media_string(
            "Law & Order SVU Season 3 Episode 7 - Watch Free HD",
            source_type="browser_title",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_sxxexx_with_online_suffix(self) -> None:
        result = parse_media_string(
            "Watch Law and Order: Special Victims Unit S3E7 Online",
            source_type="browser_title",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_netflix_suffix_stripped(self) -> None:
        result = parse_media_string(
            "Law & Order: Special Victims Unit | Netflix",
            source_type="browser_title",
        )
        assert "netflix" not in result.title.lower()


# ---------------------------------------------------------------------------
# parse_media_string — SMTC / MPRIS metadata
# ---------------------------------------------------------------------------

class TestParseSMTC:
    """SMTC and MPRIS metadata strings."""

    def test_smtc_filename(self) -> None:
        result = parse_media_string(
            "law.and.order.svu.s03e07.720p.bluray.mkv",
            source_type="smtc",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_smtc_dash_format(self) -> None:
        result = parse_media_string(
            "Law & Order: SVU - Sacrifice",
            source_type="smtc",
        )
        # Without season/episode in the string, guessit may not find them
        assert "law" in result.title.lower()

    def test_plex_smtc_format(self) -> None:
        result = parse_media_string(
            "Law & Order: Special Victims Unit - S03E07 - Sacrifice",
            source_type="smtc",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"


# ---------------------------------------------------------------------------
# parse_media_string — YouTube titles
# ---------------------------------------------------------------------------

class TestParseYouTube:
    """YouTube video titles."""

    def test_youtube_full_episode(self) -> None:
        result = parse_media_string(
            "Law & Order SVU Season 3 Episode 7 Full Episode",
            source_type="youtube",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"

    def test_youtube_compact_format(self) -> None:
        result = parse_media_string(
            "L&O SVU 3x07 Sacrifice",
            source_type="youtube",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"


# ---------------------------------------------------------------------------
# parse_media_string — Plex clean metadata
# ---------------------------------------------------------------------------

class TestParsePlex:
    """Plex clean metadata strings."""

    def test_plex_standard_format(self) -> None:
        result = parse_media_string(
            "Law & Order: Special Victims Unit - S03E07 - Sacrifice",
            source_type="plex",
        )
        assert result.season == 3
        assert result.episode == 7
        assert result.content_type == "episode"


# ---------------------------------------------------------------------------
# parse_media_string — edge cases
# ---------------------------------------------------------------------------

class TestParseEdgeCases:
    """Edge cases and fallback behaviour."""

    def test_empty_string(self) -> None:
        result = parse_media_string("", source_type="unknown")
        assert isinstance(result, ParseResult)

    def test_movie_detection(self) -> None:
        result = parse_media_string(
            "The.Matrix.1999.1080p.BluRay.x264.mkv",
            source_type="filename",
        )
        assert result.content_type == "movie"
        assert result.year == 1999

    def test_source_type_preserved(self) -> None:
        result = parse_media_string("anything", source_type="ocr")
        assert result.source_type == "ocr"

    def test_url_match_fills_missing_season_episode(self) -> None:
        from show_tracker.identification.url_patterns import UrlMatchResult

        url_match = UrlMatchResult(
            platform="generic",
            id_type="url_structured",
            slug="some-show",
            season=2,
            episode=5,
        )
        result = parse_media_string(
            "Some Show",
            source_type="browser_title",
            url_match=url_match,
        )
        assert result.season == 2
        assert result.episode == 5
        assert result.content_type == "episode"
        assert result.url_match is url_match
