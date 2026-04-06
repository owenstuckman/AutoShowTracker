"""Movie watch history API routes.

Provides endpoints for listing and querying movie watch events
stored by the detection pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import func

from show_tracker.api.schemas import MovieStats, MovieWatchOut
from show_tracker.storage.models import MovieWatch

router = APIRouter(prefix="/api/movies", tags=["movies"])


@router.get("/recent", response_model=list[MovieWatchOut])
async def get_recent_movies(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[MovieWatchOut]:
    """Return recently watched movies."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = session.query(MovieWatch).order_by(MovieWatch.started_at.desc()).limit(limit).all()
        return [
            MovieWatchOut(
                id=r.id,
                tmdb_movie_id=r.tmdb_movie_id,
                title=r.title,
                year=r.year,
                started_at=r.started_at,
                ended_at=r.ended_at,
                duration_seconds=r.duration_seconds,
                watched_seconds=getattr(r, "watched_seconds", None),
                source=r.source,
                completed=r.completed,
            )
            for r in rows
        ]


@router.get("/stats", response_model=MovieStats)
async def get_movie_stats(request: Request) -> MovieStats:
    """Return movie watch statistics."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        total_watches = session.query(func.count(MovieWatch.id)).scalar() or 0
        unique_movies = (
            session.query(func.count(func.distinct(MovieWatch.tmdb_movie_id))).scalar() or 0
        )
        total_time = (
            session.query(func.coalesce(func.sum(MovieWatch.duration_seconds), 0)).scalar() or 0
        )

        return MovieStats(
            total_watches=total_watches,
            unique_movies=unique_movies,
            total_watch_seconds=total_time,
        )


@router.get("/{movie_id}", response_model=MovieWatchOut)
async def get_movie_watch(request: Request, movie_id: int) -> MovieWatchOut:
    """Return a single movie watch by ID."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        row = session.query(MovieWatch).filter(MovieWatch.id == movie_id).first()
        if row is None:
            raise HTTPException(status_code=404, detail="Movie watch not found")
        return MovieWatchOut(
            id=row.id,
            tmdb_movie_id=row.tmdb_movie_id,
            title=row.title,
            year=row.year,
            started_at=row.started_at,
            ended_at=row.ended_at,
            duration_seconds=row.duration_seconds,
            watched_seconds=getattr(row, "watched_seconds", None),
            source=row.source,
            completed=row.completed,
        )
