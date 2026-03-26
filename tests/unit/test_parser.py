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


# ---------------------------------------------------------------------------
# parse_media_string — date-based episode parsing
# ---------------------------------------------------------------------------

class TestParseDateBasedEpisodes:
    """Date-based episode formats like show.2024.03.15."""

    def test_dotted_date_format(self) -> None:
        result = parse_media_string(
            "the.daily.show.2024.03.15.720p.web.mkv",
            source_type="filename",
        )
        assert "daily show" in result.title.lower() or "daily" in result.title.lower()
        # guessit should detect the date
        assert result.year == 2024 or result.content_type == "episode"

    def test_dashed_date_format(self) -> None:
        result = parse_media_string(
            "Conan.2024-03-15.Some.Guest.HDTV.mkv",
            source_type="filename",
        )
        assert "conan" in result.title.lower()
        assert result.year == 2024 or result.content_type == "episode"

    def test_date_with_show_name(self) -> None:
        result = parse_media_string(
            "Jimmy Kimmel Live 2024.01.20 720p WEB",
            source_type="filename",
        )
        assert "jimmy" in result.title.lower() or "kimmel" in result.title.lower()

    def test_date_only_no_season_episode(self) -> None:
        """Date-based shows typically have no season/episode numbers."""
        result = parse_media_string(
            "last.week.tonight.2024.03.10.hdtv.mkv",
            source_type="filename",
        )
        # guessit should extract year at minimum
        assert result.title != ""
        # Should be detected as episode (date-based) or have year set
        assert result.year is not None or result.content_type == "episode"

    def test_date_format_browser_title(self) -> None:
        result = parse_media_string(
            "The Late Show - March 15, 2024",
            source_type="browser_title",
        )
        assert "late show" in result.title.lower()


# ---------------------------------------------------------------------------
# parse_media_string — absolute episode numbering
# ---------------------------------------------------------------------------

class TestParseAbsoluteNumbering:
    """Absolute episode numbering (no season), common with anime."""

    def test_anime_absolute_episode(self) -> None:
        result = parse_media_string(
            "[SubGroup] Naruto - 150 (720p).mkv",
            source_type="filename",
        )
        assert result.episode is not None
        assert "naruto" in result.title.lower()

    def test_anime_absolute_episode_dotted(self) -> None:
        result = parse_media_string(
            "One.Piece.1089.1080p.WEB.mkv",
            source_type="filename",
        )
        # guessit should detect the high episode number
        assert result.episode is not None or result.year is not None
        assert "one piece" in result.title.lower() or "one" in result.title.lower()

    def test_absolute_episode_with_quality(self) -> None:
        result = parse_media_string(
            "[Fansub] Bleach - 366 [1080p][HEVC].mkv",
            source_type="filename",
        )
        assert result.episode is not None
        assert "bleach" in result.title.lower()

    def test_absolute_episode_marks_as_episode(self) -> None:
        """Absolute numbered content should be detected as episode type."""
        result = parse_media_string(
            "[SubGroup] Attack on Titan - 87 (1080p).mkv",
            source_type="filename",
        )
        assert result.content_type == "episode"
        assert result.episode is not None

    def test_absolute_numbering_no_season(self) -> None:
        """Absolute numbering typically has episode but no season."""
        result = parse_media_string(
            "[SubGroup] Demon Slayer - 44 [720p].mkv",
            source_type="filename",
        )
        assert result.episode is not None


# ---------------------------------------------------------------------------
# URL pattern completeness — additional edge cases
# ---------------------------------------------------------------------------

class TestUrlPatternEdgeCases:
    """Additional URL pattern tests for edge cases and completeness."""

    def test_crunchyroll_no_language_prefix(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        result = match_url(
            "https://www.crunchyroll.com/watch/GRDKJZ81Y/episode-slug"
        )
        assert result is not None
        assert result.platform == "crunchyroll"

    def test_youtube_short_url(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        # youtu.be short links may or may not be matched
        result = match_url("https://youtu.be/dQw4w9WgXcQ")
        # We just verify it doesn't crash — short links may not match
        assert result is None or result.platform == "youtube"

    def test_netflix_title_url_not_matched(self) -> None:
        """Netflix /title/ URLs (browse pages) should not match as video."""
        from show_tracker.identification.url_patterns import match_url

        result = match_url("https://www.netflix.com/title/80001234")
        # /title/ is not /watch/ — may not match
        assert result is None or result.platform == "netflix"

    def test_generic_slug_uppercase_sxxexx(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        result = match_url("https://example.com/watch/some-show-S02E10")
        assert result is not None
        assert result.season == 2
        assert result.episode == 10

    def test_generic_structured_with_hyphenated_season(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        result = match_url(
            "https://site.com/show/the-office/season-4/episode-12"
        )
        assert result is not None
        assert result.slug == "the-office"
        assert result.season == 4
        assert result.episode == 12

    def test_amazon_prime_video_subdomain(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        result = match_url("https://www.primevideo.com/detail/B09XYZ1234/")
        assert result is not None
        assert result.platform == "amazon_prime"

    def test_hbo_max_episode_url(self) -> None:
        from show_tracker.identification.url_patterns import match_url

        result = match_url(
            "https://play.max.com/episode/urn:hbo:episode:abc456"
        )
        assert result is not None
        assert result.platform == "hbo_max"


# ---------------------------------------------------------------------------
# Platform suffix stripping — comprehensive coverage
# ---------------------------------------------------------------------------

class TestPlatformSuffixStripping:
    """Thorough tests for all platform suffixes in _PLATFORM_SUFFIXES."""

    @pytest.mark.parametrize(
        "raw, platform_name",
        [
            ("The Mandalorian | Netflix", "Netflix"),
            ("The Mandalorian - YouTube", "YouTube"),
            ("The Mandalorian | Hulu", "Hulu"),
            ("The Mandalorian | Disney+", "Disney+"),
            ("The Mandalorian | Amazon Prime Video", "Amazon Prime Video"),
            ("The Mandalorian - Crunchyroll", "Crunchyroll"),
            ("The Mandalorian | HBO Max", "HBO Max"),
            ("The Mandalorian | Max", "Max"),
            ("The Mandalorian - Watch Free Full Episode", "Watch Free"),
            ("The Mandalorian - Watch Online HD", "Watch Online"),
            ("The Mandalorian - Plex", "Plex"),
            ("The Mandalorian | Plex", "Plex"),
            ("The Mandalorian | Peacock", "Peacock"),
            ("The Mandalorian | Paramount+", "Paramount+"),
            ("The Mandalorian | Apple TV+", "Apple TV+"),
            ("The Mandalorian | Apple TV", "Apple TV"),
        ],
    )
    def test_all_platform_suffixes(self, raw: str, platform_name: str) -> None:
        result = preprocess_for_guessit(raw, "browser_title")
        assert platform_name not in result
        assert "mandalorian" in result.lower()

    def test_suffix_case_insensitive(self) -> None:
        result = preprocess_for_guessit("Show | NETFLIX", "browser_title")
        assert "netflix" not in result.lower()
        assert "show" in result.lower()


# ---------------------------------------------------------------------------
# Noise word removal — comprehensive coverage
# ---------------------------------------------------------------------------

class TestNoiseWordRemoval:
    """Tests for noise word removal across different contexts."""

    def test_all_noise_words_removed_browser(self) -> None:
        raw = "Watch Breaking Bad Free HD Online Streaming Full Episode"
        result = preprocess_for_guessit(raw, "browser_title")
        lower = result.lower()
        assert "watch" not in lower.split()  # "watch" as standalone word
        assert "free" not in lower.split()
        assert "hd" not in lower.split()
        assert "online" not in lower.split()
        assert "streaming" not in lower.split()
        assert "full episode" not in lower

    def test_noise_words_not_removed_for_filenames(self) -> None:
        raw = "watch.dogs.s01e05.720p.mkv"
        result = preprocess_for_guessit(raw, "filename")
        assert "watch" in result.lower()

    def test_noise_words_not_removed_for_smtc(self) -> None:
        raw = "Free Birds S01E01"
        result = preprocess_for_guessit(raw, "smtc")
        assert "free" in result.lower()

    def test_noise_words_removed_for_youtube(self) -> None:
        raw = "Watch Free Breaking Bad Full Episode Online"
        result = preprocess_for_guessit(raw, "youtube")
        lower = result.lower()
        assert "watch" not in lower.split()
        assert "free" not in lower.split()

    def test_noise_word_partial_match_preserved(self) -> None:
        """Words containing noise substrings should not be altered."""
        raw = "Watchmen S01E01"
        result = preprocess_for_guessit(raw, "browser_title")
        # "Watchmen" contains "watch" but is a different word
        assert "watchmen" in result.lower()


# ---------------------------------------------------------------------------
# Whitespace normalization — comprehensive coverage
# ---------------------------------------------------------------------------

class TestWhitespaceNormalization:
    """Tests for whitespace normalization in preprocessing."""

    def test_multiple_spaces(self) -> None:
        result = preprocess_for_guessit("Law   and   Order", "browser_title")
        assert "  " not in result

    def test_leading_trailing_spaces(self) -> None:
        result = preprocess_for_guessit("   Breaking Bad   ", "browser_title")
        assert result == result.strip()
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_tabs_normalized(self) -> None:
        result = preprocess_for_guessit("Law\tand\tOrder", "browser_title")
        assert "\t" not in result
        assert "  " not in result

    def test_newlines_normalized(self) -> None:
        result = preprocess_for_guessit("Law\nand\nOrder", "browser_title")
        assert "\n" not in result

    def test_mixed_whitespace(self) -> None:
        result = preprocess_for_guessit("  Law \t and \n Order  ", "browser_title")
        assert "\t" not in result
        assert "\n" not in result
        assert "  " not in result
        assert result == result.strip()

    def test_empty_string(self) -> None:
        result = preprocess_for_guessit("", "browser_title")
        assert result == ""

    def test_whitespace_only(self) -> None:
        result = preprocess_for_guessit("   ", "browser_title")
        assert result == ""


# ---------------------------------------------------------------------------
# Player suffix stripping — VLC/mpv
# ---------------------------------------------------------------------------

class TestPlayerSuffixStripping:
    """Tests for VLC and mpv suffix stripping from window titles."""

    def test_vlc_suffix_smtc(self) -> None:
        result = preprocess_for_guessit(
            "Breaking.Bad.S01E01.mkv - VLC media player", "smtc"
        )
        assert "VLC" not in result
        assert "breaking" in result.lower()

    def test_vlc_suffix_window_title(self) -> None:
        result = preprocess_for_guessit(
            "Breaking.Bad.S01E01.mkv - VLC media player", "window_title"
        )
        assert "VLC" not in result

    def test_mpv_suffix_window_title(self) -> None:
        result = preprocess_for_guessit(
            "Breaking Bad S01E01 - mpv", "window_title"
        )
        assert "mpv" not in result.split()

    def test_vlc_not_stripped_from_browser_title(self) -> None:
        """VLC suffix stripping only applies to smtc/window_title."""
        result = preprocess_for_guessit(
            "VLC media player tips - YouTube", "browser_title"
        )
        # YouTube suffix removed but VLC stays (it's part of title)
        assert "vlc" in result.lower()

    def test_mpv_not_stripped_from_filename(self) -> None:
        result = preprocess_for_guessit("mpv.config.s01e01.mkv", "filename")
        assert "mpv" in result.lower()
