"""Episode resolution engine.

Ties together parsing, URL matching, alias lookup, caching, and TMDb search
to resolve raw detection signals into canonical episode identifications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol

from rapidfuzz import fuzz

from show_tracker.identification.confidence import calculate_confidence
from show_tracker.identification.parser import ParseResult, parse_media_string
from show_tracker.identification.tmdb_client import (
    TMDbClient,
    TMDbError,
    TMDbNotFoundError,
)
from show_tracker.identification.url_patterns import match_url

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.80  # minimum fuzzy ratio to accept a TMDb match


@dataclass(frozen=True)
class IdentificationResult:
    """Canonical identification of a detected episode."""

    tmdb_episode_id: int | None
    tmdb_show_id: int | None
    show_name: str
    season: int | None
    episode: int | None
    episode_title: str | None
    confidence: float  # 0.0 - 1.0
    source: str
    raw_input: str
    match_method: str  # "exact_url", "guessit+tmdb_fuzzy", "alias_lookup", "cache_hit"


@dataclass(frozen=True)
class MovieIdentificationResult:
    """Canonical identification of a detected movie."""

    tmdb_movie_id: int | None
    title: str
    original_title: str | None
    year: int | None
    confidence: float
    source: str
    raw_input: str
    match_method: str


class AliasStore(Protocol):
    """Protocol for looking up show aliases."""

    def lookup_alias(self, alias: str) -> int | None:
        """Return the TMDb show ID for *alias*, or None if unknown."""
        ...


class CacheStore(Protocol):
    """Protocol for caching TMDb search/episode results."""

    def get_show_id(self, query: str) -> int | None:
        """Return cached TMDb show ID for a search query, or None."""
        ...

    def set_show_id(self, query: str, tmdb_id: int) -> None:
        """Cache a search query -> TMDb show ID mapping."""
        ...

    def get_episode(self, tmdb_show_id: int, season: int, episode: int) -> dict[str, Any] | None:
        """Return cached episode data, or None."""
        ...

    def set_episode(self, tmdb_show_id: int, season: int, episode: int, data: dict[str, Any]) -> None:
        """Cache episode data."""
        ...


class _NullAliasStore:
    """Default no-op alias store."""

    def lookup_alias(self, alias: str) -> int | None:
        return None


class _NullCacheStore:
    """Default no-op cache store."""

    def get_show_id(self, query: str) -> int | None:
        return None

    def set_show_id(self, query: str, tmdb_id: int) -> None:
        pass

    def get_episode(self, tmdb_show_id: int, season: int, episode: int) -> dict[str, Any] | None:
        return None

    def set_episode(self, tmdb_show_id: int, season: int, episode: int, data: dict[str, Any]) -> None:
        pass


class EpisodeResolver:
    """Resolves raw detection strings to canonical episode identifications.

    Args:
        tmdb_client: A configured TMDb API client.
        alias_store: Optional store for show alias lookups.
        cache_store: Optional store for caching TMDb results.
        tvdb_client: Optional TVDb client for anime absolute-number fallback.
    """

    def __init__(
        self,
        tmdb_client: TMDbClient,
        alias_store: AliasStore | None = None,
        cache_store: CacheStore | None = None,
        tvdb_client: Any | None = None,
    ) -> None:
        self.tmdb = tmdb_client
        self.aliases: AliasStore = alias_store or _NullAliasStore()
        self.cache: CacheStore = cache_store or _NullCacheStore()
        self.tvdb = tvdb_client

    def resolve(
        self,
        raw_string: str,
        source_type: str,
        url: str | None = None,
    ) -> IdentificationResult:
        """Resolve a raw string (and optional URL) to a canonical episode.

        Resolution order:
        1. URL pattern matching (if URL provided).
        2. Parse the raw string with guessit.
        3. Check show_aliases for known mappings.
        4. Check cache for prior TMDb lookups.
        5. Search TMDb with fuzzy matching.
        6. Fetch episode details.

        Args:
            raw_string: The raw detection string.
            source_type: Detection source (e.g. "browser_title", "smtc").
            url: Optional URL associated with the detection.

        Returns:
            An IdentificationResult (may have None IDs if resolution failed).
        """
        # Step 1: URL pattern matching
        url_match = match_url(url) if url else None

        # Step 2: Parse the raw string
        parsed = parse_media_string(raw_string, source_type, url_match=url_match)

        # If URL match gave us a known platform ID, that is the strongest signal
        if url_match is not None and url_match.platform_id is not None:
            # For known platforms like Netflix, the platform_id can be used
            # directly via find_by_external_id or as a high-confidence signal
            match_method = "exact_url"
        else:
            match_method = "guessit+tmdb_fuzzy"

        title_query = parsed.title.strip()
        if not title_query:
            return self._unresolved(parsed, source_type, match_method)

        # Step 3: Check alias table
        tmdb_show_id = self.aliases.lookup_alias(title_query)
        if tmdb_show_id is None:
            # Also try lowercase
            tmdb_show_id = self.aliases.lookup_alias(title_query.lower())
        if tmdb_show_id is not None:
            match_method = "alias_lookup"
            return self._resolve_with_show_id(
                tmdb_show_id, parsed, source_type, match_method, tmdb_match_score=0.95
            )

        # Step 4: Check cache
        cached_id = self.cache.get_show_id(title_query.lower())
        if cached_id is not None:
            match_method = "cache_hit"
            return self._resolve_with_show_id(
                cached_id, parsed, source_type, match_method, tmdb_match_score=0.90
            )

        # Step 5: Search TMDb
        try:
            results = self.tmdb.search_show(title_query, year=parsed.year)
        except TMDbError:
            logger.exception("TMDb search failed for %r", title_query)
            return self._unresolved(parsed, source_type, match_method)

        if not results:
            return self._unresolved(parsed, source_type, match_method)

        # Fuzzy match against results, prefer higher popularity for ties
        best_show: dict[str, Any] | None = None
        best_score = 0.0

        for show in results:
            for name_field in (show.get("name", ""), show.get("original_name", "")):
                if not name_field:
                    continue
                ratio = fuzz.ratio(title_query.lower(), name_field.lower()) / 100.0
                # Slight boost for more popular shows when scores are close
                popularity_boost = min(show.get("popularity", 0) / 10000.0, 0.05)
                adjusted = ratio + popularity_boost
                if adjusted > best_score:
                    best_score = adjusted
                    best_show = show

        # The actual fuzzy score (without popularity boost) for confidence calc
        if best_show is not None:
            raw_score = max(
                fuzz.ratio(title_query.lower(), best_show.get("name", "").lower()) / 100.0,
                fuzz.ratio(
                    title_query.lower(),
                    best_show.get("original_name", "").lower(),
                )
                / 100.0,
            )
        else:
            raw_score = 0.0

        if best_show is None or raw_score < FUZZY_THRESHOLD:
            # TVDb fallback: if TMDb failed and this looks like anime
            # (no season, high episode number), try TVDb
            tvdb_result = self._try_tvdb_fallback(parsed, source_type)
            if tvdb_result is not None:
                return tvdb_result
            return self._unresolved(parsed, source_type, match_method)

        tmdb_show_id = best_show["id"]

        # Cache the mapping
        self.cache.set_show_id(title_query.lower(), tmdb_show_id)

        return self._resolve_with_show_id(
            tmdb_show_id, parsed, source_type, match_method, tmdb_match_score=raw_score
        )

    def resolve_movie(
        self,
        raw_string: str,
        source_type: str,
    ) -> MovieIdentificationResult:
        """Resolve a raw string to a canonical movie identification.

        Args:
            raw_string: The raw detection string.
            source_type: Detection source.

        Returns:
            A MovieIdentificationResult.
        """
        parsed = parse_media_string(raw_string, source_type)
        title_query = parsed.title.strip()

        if not title_query:
            return MovieIdentificationResult(
                tmdb_movie_id=None,
                title=title_query,
                original_title=None,
                year=parsed.year,
                confidence=0.0,
                source=source_type,
                raw_input=raw_string,
                match_method="none",
            )

        # Search TMDb for movies
        try:
            results = self.tmdb.search_movie(title_query, year=parsed.year)
        except TMDbError:
            logger.exception("TMDb movie search failed for %r", title_query)
            return MovieIdentificationResult(
                tmdb_movie_id=None,
                title=title_query,
                original_title=None,
                year=parsed.year,
                confidence=0.0,
                source=source_type,
                raw_input=raw_string,
                match_method="tmdb_search_failed",
            )

        if not results:
            return MovieIdentificationResult(
                tmdb_movie_id=None,
                title=title_query,
                original_title=None,
                year=parsed.year,
                confidence=0.0,
                source=source_type,
                raw_input=raw_string,
                match_method="no_results",
            )

        # Fuzzy match
        best_movie: dict[str, Any] | None = None
        best_score = 0.0

        for movie in results:
            for name_field in (movie.get("title", ""), movie.get("original_title", "")):
                if not name_field:
                    continue
                ratio = fuzz.ratio(title_query.lower(), name_field.lower()) / 100.0
                popularity_boost = min(movie.get("popularity", 0) / 10000.0, 0.05)
                adjusted = ratio + popularity_boost
                if adjusted > best_score:
                    best_score = adjusted
                    best_movie = movie

        if best_movie is None:
            raw_score = 0.0
        else:
            raw_score = max(
                fuzz.ratio(title_query.lower(), best_movie.get("title", "").lower()) / 100.0,
                fuzz.ratio(title_query.lower(), best_movie.get("original_title", "").lower()) / 100.0,
            )

        if best_movie is None or raw_score < FUZZY_THRESHOLD:
            return MovieIdentificationResult(
                tmdb_movie_id=None,
                title=title_query,
                original_title=None,
                year=parsed.year,
                confidence=raw_score,
                source=source_type,
                raw_input=raw_string,
                match_method="below_threshold",
            )

        # Extract year from release_date
        release_date = best_movie.get("release_date", "")
        year = None
        if release_date and len(release_date) >= 4:
            try:
                year = int(release_date[:4])
            except ValueError:
                pass

        return MovieIdentificationResult(
            tmdb_movie_id=best_movie["id"],
            title=best_movie.get("title", title_query),
            original_title=best_movie.get("original_title"),
            year=year,
            confidence=raw_score,
            source=source_type,
            raw_input=raw_string,
            match_method="guessit+tmdb_fuzzy",
        )

    # -- TVDb fallback for anime -------------------------------------------

    def _try_tvdb_fallback(
        self,
        parsed: ParseResult,
        source_type: str,
    ) -> IdentificationResult | None:
        """Try TVDb as a fallback for anime with absolute episode numbering.

        Only triggers when:
        - A TVDb client is configured
        - TMDb confidence < 0.6 (low match)
        - No season number in the parsed result
        - Episode number > 50 (likely absolute numbering)

        Returns an IdentificationResult if TVDb resolves it, else None.
        """
        if self.tvdb is None:
            return None

        # Only trigger for likely-anime patterns
        if parsed.season is not None:
            return None
        if parsed.episode is None or parsed.episode <= 50:
            return None

        title_query = parsed.title.strip()
        if not title_query:
            return None

        logger.debug(
            "Attempting TVDb fallback for %r (absolute ep %d)",
            title_query, parsed.episode,
        )

        try:
            from show_tracker.identification.tvdb_client import TVDbError

            # Search TVDb
            results = self.tvdb.search(title_query, search_type="series")
            if not results:
                return None

            # Take the first result (TVDb search is usually accurate for anime)
            best = results[0]
            tvdb_id = best.get("tvdb_id") or best.get("id")
            if tvdb_id is None:
                return None

            tvdb_id = int(tvdb_id)
            show_name = best.get("name", title_query)

            # Map absolute episode to season/episode
            mapping = self.tvdb.map_absolute_to_season_episode(tvdb_id, parsed.episode)
            if mapping is None:
                return None

            season, episode = mapping

            # Try to find this show on TMDb via TVDb external ID
            try:
                find_result = self.tmdb.find_by_external_id(str(tvdb_id), "tvdb_id")
                tv_results = find_result.get("tv_results", [])
                if tv_results:
                    tmdb_show_id = tv_results[0]["id"]
                    show_name = tv_results[0].get("name", show_name)

                    # Now resolve with the TMDb show ID and mapped season/episode
                    # Create a modified ParseResult with the mapped values
                    mapped_parsed = ParseResult(
                        title=show_name,
                        season=season,
                        episode=episode,
                        year=parsed.year,
                        episode_title=parsed.episode_title,
                        content_type="episode",
                        source_type=parsed.source_type,
                        raw_input=parsed.raw_input,
                        url_match=parsed.url_match,
                    )

                    return self._resolve_with_show_id(
                        tmdb_show_id, mapped_parsed, source_type,
                        match_method="tvdb_absolute_fallback",
                        tmdb_match_score=0.75,
                    )
            except TMDbError:
                logger.debug("TMDb find_by_external_id failed for TVDb ID %d", tvdb_id)

            # If TMDb cross-ref failed, return a result with TVDb info only
            confidence = calculate_confidence(parsed, 0.70, source_type, "tvdb_absolute_fallback")
            return IdentificationResult(
                tmdb_episode_id=None,
                tmdb_show_id=None,
                show_name=show_name,
                season=season,
                episode=episode,
                episode_title=None,
                confidence=confidence,
                source=source_type,
                raw_input=parsed.raw_input,
                match_method="tvdb_absolute_fallback",
            )

        except Exception:
            logger.debug("TVDb fallback failed for %r", title_query, exc_info=True)
            return None

    # -- internal helpers --------------------------------------------------

    def _resolve_with_show_id(
        self,
        tmdb_show_id: int,
        parsed: ParseResult,
        source_type: str,
        match_method: str,
        tmdb_match_score: float,
    ) -> IdentificationResult:
        """Fetch episode details given a resolved TMDb show ID."""
        season = parsed.season
        episode = parsed.episode
        show_name = parsed.title
        episode_title = parsed.episode_title
        tmdb_episode_id: int | None = None

        # Try to get the show name from TMDb for canonical naming
        try:
            show_data = self.tmdb.get_show(tmdb_show_id)
            show_name = show_data.get("name", show_name)
        except TMDbError:
            logger.debug("Could not fetch show details for TMDb ID %d", tmdb_show_id)

        # If both season and episode are known, fetch episode details
        if season is not None and episode is not None:
            cached_ep = self.cache.get_episode(tmdb_show_id, season, episode)
            if cached_ep is not None:
                tmdb_episode_id = cached_ep.get("id")
                episode_title = episode_title or cached_ep.get("name")
            else:
                try:
                    ep_data = self.tmdb.get_episode(tmdb_show_id, season, episode)
                    tmdb_episode_id = ep_data.get("id")
                    episode_title = episode_title or ep_data.get("name")
                    self.cache.set_episode(tmdb_show_id, season, episode, ep_data)
                except TMDbNotFoundError:
                    logger.debug(
                        "Episode S%02dE%02d not found for TMDb show %d",
                        season, episode, tmdb_show_id,
                    )
                except TMDbError:
                    logger.exception(
                        "Failed to fetch episode S%02dE%02d for TMDb show %d",
                        season, episode, tmdb_show_id,
                    )

        confidence = calculate_confidence(parsed, tmdb_match_score, source_type, match_method)

        return IdentificationResult(
            tmdb_episode_id=tmdb_episode_id,
            tmdb_show_id=tmdb_show_id,
            show_name=show_name,
            season=season,
            episode=episode,
            episode_title=episode_title,
            confidence=confidence,
            source=source_type,
            raw_input=parsed.raw_input,
            match_method=match_method,
        )

    def _unresolved(
        self,
        parsed: ParseResult,
        source_type: str,
        match_method: str,
    ) -> IdentificationResult:
        """Build a low-confidence result when resolution fails."""
        confidence = calculate_confidence(parsed, 0.0, source_type, match_method)

        return IdentificationResult(
            tmdb_episode_id=None,
            tmdb_show_id=None,
            show_name=parsed.title,
            season=parsed.season,
            episode=parsed.episode,
            episode_title=parsed.episode_title,
            confidence=confidence,
            source=source_type,
            raw_input=parsed.raw_input,
            match_method=match_method,
        )
