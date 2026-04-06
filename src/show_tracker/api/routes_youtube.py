"""YouTube watch history API routes.

Provides endpoints for listing and querying YouTube watch events
stored by the detection pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import func

from show_tracker.api.schemas import YouTubeStats, YouTubeWatchOut
from show_tracker.storage.models import YouTubeWatch

router = APIRouter(prefix="/api/youtube", tags=["youtube"])


@router.get("/recent", response_model=list[YouTubeWatchOut])
async def get_recent_youtube(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[YouTubeWatchOut]:
    """Return recently watched YouTube videos."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(YouTubeWatch).order_by(YouTubeWatch.started_at.desc()).limit(limit).all()
        )
        return [
            YouTubeWatchOut(
                id=r.id,
                video_id=r.video_id,
                title=r.title,
                channel_name=r.channel_name,
                duration_seconds=r.duration_seconds,
                watched_seconds=r.watched_seconds,
                started_at=r.started_at,
                ended_at=r.ended_at,
            )
            for r in rows
        ]


@router.get("/stats", response_model=YouTubeStats)
async def get_youtube_stats(request: Request) -> YouTubeStats:
    """Return YouTube watch statistics."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        total_videos = session.query(func.count(YouTubeWatch.id)).scalar() or 0
        unique_videos = (
            session.query(func.count(func.distinct(YouTubeWatch.video_id))).scalar() or 0
        )
        total_time = (
            session.query(func.coalesce(func.sum(YouTubeWatch.watched_seconds), 0)).scalar() or 0
        )

        # Top channels
        top_channels_rows = (
            session.query(
                YouTubeWatch.channel_name,
                func.count(YouTubeWatch.id).label("count"),
            )
            .filter(YouTubeWatch.channel_name.isnot(None))
            .group_by(YouTubeWatch.channel_name)
            .order_by(func.count(YouTubeWatch.id).desc())
            .limit(10)
            .all()
        )

        return YouTubeStats(
            total_watches=total_videos,
            unique_videos=unique_videos,
            total_watch_seconds=total_time,
            top_channels=[{"channel": r.channel_name, "count": r.count} for r in top_channels_rows],
        )
