"""Unresolved events API routes.

Provides endpoints for listing, resolving, dismissing, and searching
unresolved media detection events that need manual review.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from show_tracker.api.schemas import (
    ResolveRequest,
    SearchRequest,
    SearchResult,
    UnresolvedEventOut,
)
from show_tracker.storage.models import Episode, Show, UnresolvedEvent, WatchEvent

router = APIRouter(prefix="/api/unresolved", tags=["unresolved"])


# ---------------------------------------------------------------------------
# GET /api/unresolved
# ---------------------------------------------------------------------------

@router.get("", response_model=list[UnresolvedEventOut])
async def list_unresolved(request: Request) -> list[UnresolvedEventOut]:
    """List all unresolved events pending manual review."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(UnresolvedEvent)
            .filter(UnresolvedEvent.resolved == False)  # noqa: E712
            .order_by(UnresolvedEvent.detected_at.desc())
            .all()
        )

        return [
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
            for r in rows
        ]


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
