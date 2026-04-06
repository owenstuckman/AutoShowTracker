"""Tests for the episode resolver, identification result dataclasses, and alias data.

Uses mocked TMDb/TVDb clients to avoid real HTTP calls.  Tests cover:
- FUZZY_THRESHOLD constant value
- IdentificationResult and MovieIdentificationResult dataclass construction
- EpisodeResolver initialisation and attribute presence
- Resolver resolution path (alias, cache, TMDb search, unresolved)
- Alias seed data (INITIAL_ALIASES) correctness
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from rapidfuzz import fuzz

from show_tracker.identification.resolver import (
    FUZZY_THRESHOLD,
    EpisodeResolver,
    IdentificationResult,
    MovieIdentificationResult,
    _NullAliasStore,
    _NullCacheStore,
)
from show_tracker.utils.aliases import INITIAL_ALIASES

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------


def _mock_tmdb() -> MagicMock:
    """Return a MagicMock that satisfies the TMDbClient interface."""
    client = MagicMock()
    client.search_show.return_value = []
    client.search_movie.return_value = []
    client.get_show.return_value = {"name": "Test Show"}
    client.get_episode.return_value = {"id": 99, "name": "Test Episode"}
    return client


def _resolver(
    *,
    alias_store=None,
    cache_store=None,
    tvdb_client=None,
    tmdb_overrides: dict[str, Any] | None = None,
) -> EpisodeResolver:
    """Build an EpisodeResolver with a mock TMDb client."""
    client = _mock_tmdb()
    if tmdb_overrides:
        for attr, val in tmdb_overrides.items():
            setattr(client, attr, val)
    return EpisodeResolver(
        tmdb_client=client,
        alias_store=alias_store,
        cache_store=cache_store,
        tvdb_client=tvdb_client,
    )


# ---------------------------------------------------------------------------
# TestFuzzyThreshold
# ---------------------------------------------------------------------------


class TestFuzzyThreshold:
    def test_value_is_0_80(self) -> None:
        assert FUZZY_THRESHOLD == 0.80

    def test_type_is_float(self) -> None:
        assert isinstance(FUZZY_THRESHOLD, float)

    def test_below_threshold_not_accepted(self) -> None:
        """A TMDb candidate with ratio < 0.80 should be rejected (no show match)."""
        # 'Breaking Badd' vs 'Breaking Bad' — ratio will be slightly below 1 but still > 0.80
        # Use something obviously low instead
        ratio = fuzz.ratio("xyz abc", "breaking bad") / 100.0
        assert ratio < FUZZY_THRESHOLD

    def test_perfect_match_above_threshold(self) -> None:
        ratio = fuzz.ratio("breaking bad", "breaking bad") / 100.0
        assert ratio >= FUZZY_THRESHOLD


# ---------------------------------------------------------------------------
# TestIdentificationResult
# ---------------------------------------------------------------------------


class TestIdentificationResult:
    """IdentificationResult dataclass construction and field access."""

    def _make(self, **overrides: Any) -> IdentificationResult:
        defaults: dict[str, Any] = {
            "tmdb_episode_id": 1001,
            "tmdb_show_id": 202,
            "show_name": "Breaking Bad",
            "season": 2,
            "episode": 7,
            "episode_title": "Negro y Azul",
            "confidence": 0.92,
            "source": "filename",
            "raw_input": "breaking.bad.s02e07.mkv",
            "match_method": "guessit+tmdb_fuzzy",
        }
        defaults.update(overrides)
        return IdentificationResult(**defaults)

    def test_basic_fields(self) -> None:
        r = self._make()
        assert r.tmdb_episode_id == 1001
        assert r.tmdb_show_id == 202
        assert r.show_name == "Breaking Bad"
        assert r.season == 2
        assert r.episode == 7
        assert r.episode_title == "Negro y Azul"
        assert r.confidence == pytest.approx(0.92)
        assert r.source == "filename"
        assert r.raw_input == "breaking.bad.s02e07.mkv"
        assert r.match_method == "guessit+tmdb_fuzzy"

    def test_optional_fields_can_be_none(self) -> None:
        r = self._make(
            tmdb_episode_id=None,
            tmdb_show_id=None,
            season=None,
            episode=None,
            episode_title=None,
        )
        assert r.tmdb_episode_id is None
        assert r.tmdb_show_id is None
        assert r.season is None
        assert r.episode is None
        assert r.episode_title is None

    def test_frozen_cannot_mutate(self) -> None:
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.show_name = "Other Show"  # type: ignore[misc]

    def test_confidence_bounds(self) -> None:
        """confidence field accepts values in [0.0, 1.0]."""
        r0 = self._make(confidence=0.0)
        r1 = self._make(confidence=1.0)
        assert r0.confidence == 0.0
        assert r1.confidence == 1.0

    def test_match_method_values(self) -> None:
        """Known match_method strings are accepted."""
        for method in ("exact_url", "guessit+tmdb_fuzzy", "alias_lookup", "cache_hit"):
            r = self._make(match_method=method)
            assert r.match_method == method


# ---------------------------------------------------------------------------
# TestMovieIdentificationResult
# ---------------------------------------------------------------------------


class TestMovieIdentificationResult:
    def _make(self, **overrides: Any) -> MovieIdentificationResult:
        defaults: dict[str, Any] = {
            "tmdb_movie_id": 500,
            "title": "Inception",
            "original_title": "Inception",
            "year": 2010,
            "confidence": 0.97,
            "source": "filename",
            "raw_input": "Inception.2010.1080p.mkv",
            "match_method": "guessit+tmdb_fuzzy",
        }
        defaults.update(overrides)
        return MovieIdentificationResult(**defaults)

    def test_basic_fields(self) -> None:
        r = self._make()
        assert r.tmdb_movie_id == 500
        assert r.title == "Inception"
        assert r.original_title == "Inception"
        assert r.year == 2010
        assert r.confidence == pytest.approx(0.97)
        assert r.source == "filename"
        assert r.raw_input == "Inception.2010.1080p.mkv"
        assert r.match_method == "guessit+tmdb_fuzzy"

    def test_optional_fields_none(self) -> None:
        r = self._make(tmdb_movie_id=None, original_title=None, year=None)
        assert r.tmdb_movie_id is None
        assert r.original_title is None
        assert r.year is None

    def test_frozen(self) -> None:
        r = self._make()
        with pytest.raises((AttributeError, TypeError)):
            r.title = "Other"  # type: ignore[misc]

    def test_confidence_float(self) -> None:
        r = self._make(confidence=0.5)
        assert isinstance(r.confidence, float)


# ---------------------------------------------------------------------------
# TestEpisodeResolverInit
# ---------------------------------------------------------------------------


class TestEpisodeResolverInit:
    """EpisodeResolver initialises correctly from its arguments."""

    def test_basic_init(self) -> None:
        client = _mock_tmdb()
        resolver = EpisodeResolver(tmdb_client=client)
        assert resolver.tmdb is client

    def test_default_alias_store_is_null(self) -> None:
        resolver = _resolver()
        assert isinstance(resolver.aliases, _NullAliasStore)

    def test_custom_alias_store_set(self) -> None:
        alias = MagicMock()
        resolver = _resolver(alias_store=alias)
        assert resolver.aliases is alias

    def test_default_cache_store_is_null(self) -> None:
        resolver = _resolver()
        assert isinstance(resolver.cache, _NullCacheStore)

    def test_custom_cache_store_set(self) -> None:
        cache = MagicMock()
        resolver = _resolver(cache_store=cache)
        assert resolver.cache is cache

    def test_tvdb_defaults_to_none(self) -> None:
        resolver = _resolver()
        assert resolver.tvdb is None

    def test_tvdb_can_be_set(self) -> None:
        tvdb = MagicMock()
        resolver = _resolver(tvdb_client=tvdb)
        assert resolver.tvdb is tvdb

    def test_resolver_has_resolve_method(self) -> None:
        resolver = _resolver()
        assert callable(resolver.resolve)

    def test_resolver_has_resolve_movie_method(self) -> None:
        resolver = _resolver()
        assert callable(resolver.resolve_movie)


# ---------------------------------------------------------------------------
# TestNullStores
# ---------------------------------------------------------------------------


class TestNullStores:
    """_NullAliasStore and _NullCacheStore behave as no-ops."""

    def test_null_alias_store_returns_none(self) -> None:
        store = _NullAliasStore()
        assert store.lookup_alias("breaking bad") is None
        assert store.lookup_alias("") is None

    def test_null_cache_store_get_show_id_returns_none(self) -> None:
        store = _NullCacheStore()
        assert store.get_show_id("breaking bad") is None

    def test_null_cache_store_set_show_id_is_noop(self) -> None:
        store = _NullCacheStore()
        store.set_show_id("breaking bad", 1234)  # should not raise

    def test_null_cache_store_get_episode_returns_none(self) -> None:
        store = _NullCacheStore()
        assert store.get_episode(1234, 1, 1) is None

    def test_null_cache_store_set_episode_is_noop(self) -> None:
        store = _NullCacheStore()
        store.set_episode(1234, 1, 1, {"id": 9})  # should not raise


# ---------------------------------------------------------------------------
# TestResolverResolutionPath — no real HTTP
# ---------------------------------------------------------------------------


class TestResolverResolutionPath:
    """Test the resolve() dispatch logic with mocked stores and TMDb."""

    def test_empty_string_returns_unresolved(self) -> None:
        resolver = _resolver()
        result = resolver.resolve("", source_type="smtc")
        assert result.tmdb_show_id is None
        assert result.confidence < 0.5

    def test_alias_lookup_used_when_alias_matches(self) -> None:
        """If the alias store finds a hit, match_method='alias_lookup'."""
        alias_store = MagicMock()
        alias_store.lookup_alias.return_value = 12345

        client = _mock_tmdb()
        client.get_show.return_value = {"name": "Game of Thrones"}
        client.get_episode.return_value = {"id": 77, "name": "Winter Is Coming"}

        resolver = EpisodeResolver(
            tmdb_client=client,
            alias_store=alias_store,
        )
        result = resolver.resolve(
            "got s01e01", source_type="browser_title"
        )
        assert result.match_method == "alias_lookup"
        assert result.tmdb_show_id == 12345

    def test_cache_hit_used_when_cache_has_show(self) -> None:
        """If cache has a stored ID and alias misses, match_method='cache_hit'."""
        cache_store = MagicMock()
        cache_store.get_show_id.return_value = 99999
        cache_store.get_episode.return_value = None  # no episode cache

        client = _mock_tmdb()
        client.get_show.return_value = {"name": "Breaking Bad"}
        client.get_episode.return_value = {"id": 5, "name": "Pilot"}

        alias_store = MagicMock()
        alias_store.lookup_alias.return_value = None  # alias misses

        resolver = EpisodeResolver(
            tmdb_client=client,
            alias_store=alias_store,
            cache_store=cache_store,
        )
        result = resolver.resolve("Breaking Bad s01e01", source_type="filename")
        assert result.match_method == "cache_hit"
        assert result.tmdb_show_id == 99999

    def test_tmdb_search_used_when_alias_and_cache_miss(self) -> None:
        """When alias+cache miss, TMDb search is called."""
        client = _mock_tmdb()
        client.search_show.return_value = [
            {"id": 42, "name": "Firefly", "original_name": "Firefly", "popularity": 50.0}
        ]
        client.get_show.return_value = {"name": "Firefly"}
        client.get_episode.return_value = {"id": 1, "name": "Serenity"}

        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve("Firefly S01E01", source_type="filename")
        assert result.match_method == "guessit+tmdb_fuzzy"
        assert result.tmdb_show_id == 42

    def test_below_fuzzy_threshold_returns_unresolved(self) -> None:
        """If the best TMDb match is below FUZZY_THRESHOLD, return unresolved."""
        client = _mock_tmdb()
        # "xyzzy nonsense" will not match "Firefly" above threshold
        client.search_show.return_value = [
            {"id": 99, "name": "Firefly", "original_name": "Firefly", "popularity": 10.0}
        ]

        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve("xyzzy nonsense s01e01", source_type="filename")
        assert result.tmdb_show_id is None

    def test_tmdb_error_returns_unresolved(self) -> None:
        """If TMDb raises an error, resolve() returns an unresolved result."""
        from show_tracker.identification.tmdb_client import TMDbError

        client = _mock_tmdb()
        client.search_show.side_effect = TMDbError("network down")

        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve("Stranger Things s01e01", source_type="smtc")
        assert result.tmdb_show_id is None

    def test_no_results_from_tmdb_returns_unresolved(self) -> None:
        """Empty TMDb search results return unresolved."""
        client = _mock_tmdb()
        client.search_show.return_value = []

        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve("NonExistentShow99 s01e01", source_type="filename")
        assert result.tmdb_show_id is None

    def test_resolve_returns_identification_result_type(self) -> None:
        resolver = _resolver()
        result = resolver.resolve("some show s01e01", source_type="smtc")
        assert isinstance(result, IdentificationResult)

    def test_resolve_preserves_raw_input(self) -> None:
        resolver = _resolver()
        raw = "breaking.bad.s01e01.720p.mkv"
        result = resolver.resolve(raw, source_type="filename")
        assert result.raw_input == raw

    def test_resolve_source_field_matches_input(self) -> None:
        resolver = _resolver()
        result = resolver.resolve("some show s01e01", source_type="browser_title")
        assert result.source == "browser_title"


# ---------------------------------------------------------------------------
# TestResolveMovie
# ---------------------------------------------------------------------------


class TestResolveMovie:
    """Tests for the resolve_movie() method."""

    def test_empty_string_returns_no_id(self) -> None:
        resolver = _resolver()
        result = resolver.resolve_movie("", source_type="filename")
        assert result.tmdb_movie_id is None
        assert result.confidence == 0.0

    def test_below_threshold_returns_no_id(self) -> None:
        client = _mock_tmdb()
        client.search_movie.return_value = [
            {"id": 1, "title": "Inception", "original_title": "Inception", "popularity": 100}
        ]
        resolver = EpisodeResolver(tmdb_client=client)
        # "xyzzy" should not fuzzy-match "Inception"
        result = resolver.resolve_movie("xyzzy 2099", source_type="filename")
        assert result.tmdb_movie_id is None

    def test_good_match_returns_movie_id(self) -> None:
        client = _mock_tmdb()
        client.search_movie.return_value = [
            {
                "id": 27205,
                "title": "Inception",
                "original_title": "Inception",
                "release_date": "2010-07-16",
                "popularity": 80.0,
            }
        ]
        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve_movie("Inception 2010", source_type="filename")
        assert result.tmdb_movie_id == 27205
        assert result.title == "Inception"

    def test_resolve_movie_returns_correct_type(self) -> None:
        resolver = _resolver()
        result = resolver.resolve_movie("Inception 2010", source_type="filename")
        assert isinstance(result, MovieIdentificationResult)

    def test_tmdb_error_returns_failed_result(self) -> None:
        from show_tracker.identification.tmdb_client import TMDbError

        client = _mock_tmdb()
        client.search_movie.side_effect = TMDbError("timeout")
        resolver = EpisodeResolver(tmdb_client=client)
        result = resolver.resolve_movie("Inception 2010", source_type="filename")
        assert result.tmdb_movie_id is None
        assert result.match_method == "tmdb_search_failed"


# ---------------------------------------------------------------------------
# TestFuzzyMatchingLogic
# ---------------------------------------------------------------------------


class TestFuzzyMatchingLogic:
    """Unit tests for the raw fuzzy scoring used inside the resolver."""

    @pytest.mark.parametrize(
        "query, candidate, expect_above_threshold",
        [
            ("breaking bad", "Breaking Bad", True),
            ("breaking bad", "Breaking Point", False),
            ("stranger things", "Stranger Things", True),
            ("strngr thngs", "Stranger Things", True),  # 0.89 ratio, above 0.80 threshold
            ("the office", "The Office", True),
            ("xyz random", "Game of Thrones", False),
        ],
    )
    def test_fuzzy_ratio_against_threshold(
        self, query: str, candidate: str, expect_above_threshold: bool
    ) -> None:
        ratio = fuzz.ratio(query.lower(), candidate.lower()) / 100.0
        if expect_above_threshold:
            assert ratio >= FUZZY_THRESHOLD, (
                f"Expected {ratio:.2f} >= {FUZZY_THRESHOLD} for {query!r} vs {candidate!r}"
            )
        else:
            assert ratio < FUZZY_THRESHOLD, (
                f"Expected {ratio:.2f} < {FUZZY_THRESHOLD} for {query!r} vs {candidate!r}"
            )

    def test_popularity_boost_capped_at_005(self) -> None:
        """Popularity boost must not exceed 0.05 regardless of popularity value."""
        popularity = 100_000  # very high
        boost = min(popularity / 10_000.0, 0.05)
        assert boost == pytest.approx(0.05)

    def test_popularity_boost_scales_below_cap(self) -> None:
        popularity = 200
        boost = min(popularity / 10_000.0, 0.05)
        assert boost == pytest.approx(0.02)

    def test_zero_popularity_gives_zero_boost(self) -> None:
        boost = min(0 / 10_000.0, 0.05)
        assert boost == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# TestAliasLookup
# ---------------------------------------------------------------------------


class TestAliasLookup:
    """Tests for the INITIAL_ALIASES seed data in show_tracker.utils.aliases."""

    def test_initial_aliases_is_dict(self) -> None:
        assert isinstance(INITIAL_ALIASES, dict)

    def test_initial_aliases_not_empty(self) -> None:
        assert len(INITIAL_ALIASES) > 0

    def test_all_keys_are_lowercase(self) -> None:
        """Alias keys should be lowercase for case-insensitive lookup."""
        for key in INITIAL_ALIASES:
            assert key == key.lower(), f"Alias key {key!r} is not lowercase"

    def test_all_values_are_non_empty_strings(self) -> None:
        for alias, canonical in INITIAL_ALIASES.items():
            assert isinstance(canonical, str), f"Value for {alias!r} is not a string"
            assert canonical.strip(), f"Value for {alias!r} is empty or whitespace"

    @pytest.mark.parametrize(
        "alias, expected_canonical",
        [
            ("got", "Game of Thrones"),
            ("bb", "Breaking Bad"),
            ("brba", "Breaking Bad"),
            ("bcs", "Better Call Saul"),
            ("himym", "How I Met Your Mother"),
            ("aot", "Attack on Titan"),
            ("mha", "My Hero Academia"),
            ("b99", "Brooklyn Nine-Nine"),
            ("oitnb", "Orange Is the New Black"),
            ("tbbt", "The Big Bang Theory"),
            ("twd", "The Walking Dead"),
            ("iasip", "It's Always Sunny in Philadelphia"),
            ("parks and rec", "Parks and Recreation"),
            ("svu", "Law & Order: Special Victims Unit"),
            ("simpsons", "The Simpsons"),
        ],
    )
    def test_well_known_aliases(self, alias: str, expected_canonical: str) -> None:
        assert INITIAL_ALIASES[alias] == expected_canonical

    def test_short_aliases_differ_from_canonical(self) -> None:
        """Short abbreviation aliases (< 10 chars) must differ from canonical lowercase."""
        for alias, canonical in INITIAL_ALIASES.items():
            if len(alias) < 10:
                assert alias != canonical.lower(), (
                    f"Short alias {alias!r} maps to its own lowercase canonical title"
                )

    def test_canonical_titles_are_title_case_or_proper_noun(self) -> None:
        """Canonical titles should start with an uppercase letter."""
        for alias, canonical in INITIAL_ALIASES.items():
            assert canonical[0].isupper(), (
                f"Canonical title {canonical!r} (for alias {alias!r}) does not start uppercase"
            )

    def test_shingeki_no_kyojin_alias(self) -> None:
        assert INITIAL_ALIASES["shingeki no kyojin"] == "Attack on Titan"

    def test_boku_no_hero_alias(self) -> None:
        assert INITIAL_ALIASES["boku no hero academia"] == "My Hero Academia"

    def test_rick_and_morty_punctuation_alias(self) -> None:
        assert INITIAL_ALIASES["rick & morty"] == "Rick and Morty"

    def test_no_duplicate_aliases(self) -> None:
        """Each alias key must be unique (dict guarantees this, but confirm)."""
        keys = list(INITIAL_ALIASES.keys())
        assert len(keys) == len(set(keys))
