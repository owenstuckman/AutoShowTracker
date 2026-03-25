"""Tests for URL pattern matching engine."""

from __future__ import annotations

from show_tracker.identification.url_patterns import match_url


class TestNetflix:
    def test_netflix_watch_url(self) -> None:
        result = match_url("https://www.netflix.com/watch/80001234")
        assert result is not None
        assert result.platform == "netflix"
        assert result.id_type == "netflix_content_id"
        assert result.platform_id == "80001234"

    def test_netflix_watch_with_query_params(self) -> None:
        result = match_url("https://www.netflix.com/watch/80001234?trackId=123")
        assert result is not None
        assert result.platform == "netflix"
        assert result.platform_id == "80001234"


class TestYouTube:
    def test_youtube_watch_url(self) -> None:
        result = match_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert result.platform == "youtube"
        assert result.id_type == "youtube_video_id"
        assert result.platform_id == "dQw4w9WgXcQ"

    def test_youtube_with_extra_params(self) -> None:
        result = match_url(
            "https://www.youtube.com/watch?v=abc123_-X&list=PLxyz&index=5"
        )
        assert result is not None
        assert result.platform == "youtube"
        assert result.platform_id == "abc123_-X"


class TestCrunchyroll:
    def test_crunchyroll_watch_url(self) -> None:
        result = match_url(
            "https://www.crunchyroll.com/en-us/watch/G4PH0WXVJ/the-episode-slug"
        )
        assert result is not None
        assert result.platform == "crunchyroll"
        assert result.id_type == "crunchyroll_slug"
        assert result.slug == "the-episode-slug"


class TestPlex:
    def test_plex_web_url(self) -> None:
        result = match_url(
            "https://app.plex.tv/web/index.html#!/server/abc123/"
            "details?key=%2Flibrary%2Fmetadata%2F98765"
        )
        assert result is not None
        assert result.platform == "plex"
        assert result.id_type == "plex_metadata_key"
        assert result.platform_id == "98765"


class TestDisneyPlus:
    def test_disney_plus_video_url(self) -> None:
        result = match_url("https://www.disneyplus.com/video/abc-123-def")
        assert result is not None
        assert result.platform == "disney_plus"
        assert result.id_type == "disney_content_id"
        assert result.platform_id == "abc-123-def"


class TestHulu:
    def test_hulu_watch_url(self) -> None:
        result = match_url("https://www.hulu.com/watch/abc-123-def-456")
        assert result is not None
        assert result.platform == "hulu"
        assert result.id_type == "hulu_content_id"
        assert result.platform_id == "abc-123-def-456"


class TestAmazonPrime:
    def test_prime_video_detail_url(self) -> None:
        result = match_url("https://www.primevideo.com/detail/B0ABC1234")
        assert result is not None
        assert result.platform == "amazon_prime"
        assert result.id_type == "amazon_content_id"
        assert result.platform_id == "B0ABC1234"

    def test_amazon_gp_video_detail_url(self) -> None:
        result = match_url(
            "https://www.amazon.com/gp/video/detail/B0ABC1234"
        )
        assert result is not None
        assert result.platform == "amazon_prime"
        assert result.platform_id == "B0ABC1234"


class TestHBOMax:
    def test_hbo_max_url(self) -> None:
        result = match_url(
            "https://play.hbomax.com/page/urn:hbo:page:abc123"
        )
        assert result is not None
        assert result.platform == "hbo_max"
        assert result.id_type == "hbo_content_id"

    def test_max_url(self) -> None:
        result = match_url(
            "https://play.max.com/show/urn:hbo:show:abc123"
        )
        assert result is not None
        assert result.platform == "hbo_max"


class TestGenericPirateSites:
    def test_slug_with_episode_info(self) -> None:
        result = match_url(
            "https://pirate-site.com/watch/law-and-order-svu-s03e07"
        )
        assert result is not None
        assert result.platform == "generic"
        assert result.id_type == "url_slug_with_episode"
        assert result.slug == "law-and-order-svu-s03e07"
        assert result.season == 3
        assert result.episode == 7

    def test_structured_show_url(self) -> None:
        result = match_url(
            "https://some-site.com/show/law-and-order-svu/season-3/episode-7"
        )
        assert result is not None
        assert result.platform == "generic"
        assert result.id_type == "url_structured"
        assert result.slug == "law-and-order-svu"
        assert result.season == 3
        assert result.episode == 7

    def test_structured_series_url(self) -> None:
        result = match_url(
            "https://streamsite.io/series/breaking-bad/season2/episode3"
        )
        assert result is not None
        assert result.platform == "generic"
        assert result.id_type == "url_structured"
        assert result.slug == "breaking-bad"
        assert result.season == 2
        assert result.episode == 3

    def test_stream_verb(self) -> None:
        result = match_url(
            "https://example.com/stream/some-show-s01e05"
        )
        assert result is not None
        assert result.platform == "generic"
        assert result.season == 1
        assert result.episode == 5


class TestNoMatch:
    def test_empty_string(self) -> None:
        assert match_url("") is None

    def test_unrecognized_url(self) -> None:
        assert match_url("https://www.google.com/search?q=tv+shows") is None

    def test_none_like_empty(self) -> None:
        assert match_url("") is None

    def test_random_path(self) -> None:
        assert match_url("https://example.com/about") is None


class TestUrlMatchResultDefaults:
    """Verify that optional fields default to None."""

    def test_netflix_has_no_season_episode(self) -> None:
        result = match_url("https://www.netflix.com/watch/80001234")
        assert result is not None
        assert result.season is None
        assert result.episode is None
        assert result.slug is None

    def test_generic_has_no_platform_id(self) -> None:
        result = match_url(
            "https://example.com/show/some-show/season-1/episode-1"
        )
        assert result is not None
        assert result.platform_id is None
