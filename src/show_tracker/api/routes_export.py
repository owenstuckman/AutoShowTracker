"""Export API routes.

Provides JSON and CSV export of watch history and show data.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from show_tracker.storage.models import Episode, Show, WatchEvent

router = APIRouter(prefix="/api/export", tags=["export"])


def _fetch_history_rows(db: Any) -> list[dict[str, Any]]:
    """Fetch all watch history rows as dicts."""
    with db.get_watch_session() as session:
        rows = (
            session.query(
                Show.title.label("show_title"),
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
                WatchEvent.started_at,
                WatchEvent.duration_seconds,
                WatchEvent.completed,
                WatchEvent.source,
            )
            .join(Episode, WatchEvent.episode_id == Episode.id)
            .join(Show, Episode.show_id == Show.id)
            .order_by(WatchEvent.started_at.desc())
            .all()
        )
        return [
            {
                "show_title": r.show_title,
                "season_number": r.season_number,
                "episode_number": r.episode_number,
                "episode_title": r.episode_title,
                "started_at": r.started_at,
                "duration_seconds": r.duration_seconds,
                "completed": r.completed,
                "source": r.source,
            }
            for r in rows
        ]


def _fetch_shows_rows(db: Any) -> list[dict[str, Any]]:
    """Fetch all tracked shows as dicts."""
    with db.get_watch_session() as session:
        rows = (
            session.query(
                Show.id,
                Show.title,
                Show.tmdb_id,
                Show.status,
                Show.total_seasons,
                Show.first_air_date,
                Show.poster_path,
            )
            .order_by(Show.title)
            .all()
        )
        return [
            {
                "show_id": r.id,
                "title": r.title,
                "tmdb_id": r.tmdb_id,
                "status": r.status,
                "total_seasons": r.total_seasons,
                "first_air_date": r.first_air_date,
                "poster_path": r.poster_path,
            }
            for r in rows
        ]


def _rows_to_csv(rows: list[dict[str, Any]]) -> str:
    """Convert a list of dicts to a CSV string."""
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


# ---------------------------------------------------------------------------
# History export
# ---------------------------------------------------------------------------

@router.get("/history.json")
async def export_history_json(request: Request) -> JSONResponse:
    """Export all watch history as JSON."""
    rows = _fetch_history_rows(request.app.state.db)
    return JSONResponse(content=rows)


@router.get("/history.csv")
async def export_history_csv(request: Request) -> StreamingResponse:
    """Export all watch history as CSV."""
    rows = _fetch_history_rows(request.app.state.db)
    csv_content = _rows_to_csv(rows)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=watch_history.csv"},
    )


# ---------------------------------------------------------------------------
# Shows export
# ---------------------------------------------------------------------------

@router.get("/shows.json")
async def export_shows_json(request: Request) -> JSONResponse:
    """Export all tracked shows as JSON."""
    rows = _fetch_shows_rows(request.app.state.db)
    return JSONResponse(content=rows)


@router.get("/shows.csv")
async def export_shows_csv(request: Request) -> StreamingResponse:
    """Export all tracked shows as CSV."""
    rows = _fetch_shows_rows(request.app.state.db)
    csv_content = _rows_to_csv(rows)
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=shows.csv"},
    )
