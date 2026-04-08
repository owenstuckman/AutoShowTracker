"""Unresolved events API routes.

Provides endpoints for listing, resolving, dismissing, and searching
unresolved media detection events that need manual review.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from show_tracker.api.schemas import (
    ResolveRequest,
    SearchRequest,
    SearchResult,
    UnresolvedEventOut,
)
from show_tracker.storage.models import Episode, Show, UnresolvedEvent, WatchEvent

router = APIRouter(prefix="/api/unresolved", tags=["unresolved"])

# ---------------------------------------------------------------------------
# Noise filter
# ---------------------------------------------------------------------------

# Domains whose URLs are never TV-show content
_NOISE_DOMAINS: frozenset[str] = frozenset(
    [
        "google.com",
        "google.co",
        "bing.com",
        "duckduckgo.com",
        "yahoo.com",
        "baidu.com",
        "reddit.com",
        "twitter.com",
        "x.com",
        "facebook.com",
        "instagram.com",
        "tiktok.com",
        "linkedin.com",
        "github.com",
        "stackoverflow.com",
        "wikipedia.org",
        "amazon.com",
        "ebay.com",
        "etsy.com",
        "news.ycombinator.com",
        "nytimes.com",
        "cnn.com",
        "bbc.com",
        "bbc.co.uk",
        "theguardian.com",
        "twitch.tv",
        "spotify.com",
        "soundcloud.com",
        "maps.google",
        "mail.google",
        "calendar.google",
        "docs.google",
        "drive.google",
        "youtube.com",
        "youtu.be",
    ]
)

# Exact strings (case-insensitive) that are browser chrome, not media titles
_NOISE_EXACT: frozenset[str] = frozenset(
    [
        "new tab",
        "blank page",
        "about:blank",
        "about:newtab",
        "homepage",
        "start page",
        "untitled",
        "loading…",
        "loading...",
    ]
)

# Raw inputs shorter than this are almost certainly noise
_MIN_RAW_LENGTH = 5


def _is_noise(raw_input: str, source: str, confidence: float | None) -> bool:
    """Return True if this unresolved event is almost certainly not a TV show.

    Filters applied (any one is sufficient to declare noise):
    - raw_input is very short (< 5 characters)
    - raw_input is a known browser-chrome string (e.g. "New Tab")
    - raw_input is a URL pointing at a known non-media domain
    - confidence is virtually zero AND no best-guess show (caught by caller)
    """
    text = raw_input.strip()
    if len(text) < _MIN_RAW_LENGTH:
        return True

    if text.lower() in _NOISE_EXACT:
        return True

    # Check for URL-like inputs against noise domains
    if text.startswith(("http://", "https://", "www.")):
        # Extract the hostname
        m = re.match(r"https?://([^/?\s]+)", text)
        if not m:
            m = re.match(r"www\.([^/?\s]+)", text)
        if m:
            host = re.sub(r"^www\.", "", m.group(1).lower())
            for domain in _NOISE_DOMAINS:
                if host == domain or host.endswith("." + domain):
                    return True

    return False


# ---------------------------------------------------------------------------
# GET /api/unresolved
# ---------------------------------------------------------------------------


@router.get("", response_model=list[UnresolvedEventOut])
async def list_unresolved(
    request: Request,
    show_all: bool = Query(
        default=False,
        description="Include likely-noise events (short strings, known non-media domains, etc.).",
    ),
) -> list[UnresolvedEventOut]:
    """List unresolved events pending manual review.

    By default, events that are almost certainly noise (browser chrome, social
    media URLs, near-zero-confidence entries with no show guess) are hidden.
    Pass ``?show_all=true`` to see everything.
    """
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(UnresolvedEvent)
            .filter(UnresolvedEvent.resolved == False)  # noqa: E712
            .order_by(UnresolvedEvent.detected_at.desc())
            .all()
        )

        results = []
        for r in rows:
            if not show_all:
                # Drop events where confidence was explicitly scored near-zero
                # with no show guess — these are ambiguous noise, not failed IDs.
                if r.confidence is not None and r.confidence < 0.05 and not r.best_guess_show:
                    continue
                if _is_noise(r.raw_input, r.source, r.confidence):
                    continue
            results.append(
                UnresolvedEventOut(
                    id=r.id,
                    raw_input=r.raw_input,
                    source=r.source,
                    source_detail=r.source_detail,
                    detected_at=r.detected_at,
                    best_guess_show=r.best_guess_show,
                    best_guess_season=r.best_guess_season,
                    best_guess_episode=r.best_guess_episode,
                    confidence=r.confidence,
                )
            )
        return results


# ---------------------------------------------------------------------------
# POST /api/unresolved/{id}/resolve
# ---------------------------------------------------------------------------


@router.post("/{event_id}/resolve")
async def resolve_event(
    event_id: int,
    body: ResolveRequest,
    request: Request,
) -> dict[str, Any]:
    """Manually assign an unresolved event to a specific show/episode.

    If the episode does not exist in the database, it will be created.
    A watch event is also recorded.
    """
    db = request.app.state.db
    with db.get_watch_session() as session:
        unresolved = session.query(UnresolvedEvent).filter(UnresolvedEvent.id == event_id).first()
        if unresolved is None:
            raise HTTPException(status_code=404, detail="Unresolved event not found")

        # Find or create the show — for manual resolution we need the show to exist
        show = session.query(Show).filter(Show.id == body.show_id).first()
        if show is None:
            raise HTTPException(status_code=404, detail="Show not found")

        # Find or create the episode
        episode = (
            session.query(Episode)
            .filter(
                Episode.show_id == body.show_id,
                Episode.season_number == body.season_number,
                Episode.episode_number == body.episode_number,
            )
            .first()
        )
        if episode is None:
            episode = Episode(
                show_id=body.show_id,
                season_number=body.season_number,
                episode_number=body.episode_number,
            )
            session.add(episode)
            session.flush()

        # Mark resolved
        unresolved.resolved = True
        unresolved.resolved_episode_id = episode.id

        # Create a watch event from the unresolved detection
        watch = WatchEvent(
            episode_id=episode.id,
            started_at=unresolved.detected_at,
            source=unresolved.source,
            source_detail=unresolved.source_detail,
            confidence=1.0,
            raw_input=unresolved.raw_input,
        )
        session.add(watch)

    return {"status": "ok", "message": "Event resolved", "episode_id": episode.id}


# ---------------------------------------------------------------------------
# POST /api/unresolved/{id}/dismiss
# ---------------------------------------------------------------------------


@router.post("/{event_id}/dismiss")
async def dismiss_event(event_id: int, request: Request) -> dict[str, Any]:
    """Dismiss an unresolved event without assigning it to an episode."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        unresolved = session.query(UnresolvedEvent).filter(UnresolvedEvent.id == event_id).first()
        if unresolved is None:
            raise HTTPException(status_code=404, detail="Unresolved event not found")

        unresolved.resolved = True

    return {"status": "ok", "message": "Event dismissed"}


# ---------------------------------------------------------------------------
# POST /api/unresolved/{id}/search
# ---------------------------------------------------------------------------


@router.post("/{event_id}/search", response_model=list[SearchResult])
async def search_tmdb(
    event_id: int,
    body: SearchRequest,
    request: Request,
) -> list[SearchResult]:
    """Search TMDb for candidate shows matching a query.

    This endpoint is used when the user wants to manually search for the
    correct show to assign an unresolved event to.  If no TMDb key is
    configured, returns an empty list.
    """
    settings = request.app.state.settings

    if not settings.has_tmdb_key():
        return []

    # Attempt a TMDb search
    import httpx

    results: list[SearchResult] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.themoviedb.org/3/search/tv",
                params={
                    "api_key": settings.tmdb_api_key,
                    "query": body.query,
                    "page": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("results", [])[:10]:
                results.append(
                    SearchResult(
                        tmdb_id=item["id"],
                        title=item.get("name", ""),
                        first_air_date=item.get("first_air_date"),
                        poster_path=item.get("poster_path"),
                        overview=item.get("overview"),
                    )
                )
    except Exception:
        # If the search fails, return empty rather than error
        pass

    return results
