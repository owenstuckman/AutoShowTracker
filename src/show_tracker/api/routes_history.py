"""Watch history API routes.

Provides endpoints for querying the user's watch history, show progress,
next-to-watch recommendations, and viewing statistics.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, case, text

from show_tracker.api.schemas import (
    EpisodeGridItem,
    EpisodeInfo,
    EpisodeProgress,
    NextToWatch,
    SeasonInfo,
    ShowDetail,
    ShowSummary,
    ShowWatchTime,
    WatchStats,
    WeekWatchTime,
)
from show_tracker.storage.models import Episode, Show, WatchEvent, YouTubeWatch

router = APIRouter(prefix="/api/history", tags=["history"])


# ---------------------------------------------------------------------------
# GET /api/history/recent
# ---------------------------------------------------------------------------

@router.get("/recent", response_model=list[EpisodeInfo])
async def get_recent(
    request: Request,
    limit: int = Query(default=50, ge=1, le=500),
) -> list[EpisodeInfo]:
    """Return recently watched episodes with show info."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                WatchEvent.id,
                WatchEvent.episode_id,
                WatchEvent.started_at,
                WatchEvent.duration_seconds,
                WatchEvent.completed,
                WatchEvent.source,
                Episode.show_id,
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
                Show.title.label("show_title"),
            )
            .join(Episode, WatchEvent.episode_id == Episode.id)
            .join(Show, Episode.show_id == Show.id)
            .order_by(WatchEvent.started_at.desc())
            .limit(limit)
            .all()
        )

        return [
            EpisodeInfo(
                episode_id=r.episode_id,
                show_id=r.show_id,
                show_title=r.show_title,
                season_number=r.season_number,
                episode_number=r.episode_number,
                episode_title=r.episode_title,
                started_at=r.started_at,
                duration_seconds=r.duration_seconds,
                completed=r.completed,
                source=r.source,
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /api/history/shows
# ---------------------------------------------------------------------------

@router.get("/shows", response_model=list[ShowSummary])
async def get_shows(request: Request) -> list[ShowSummary]:
    """Return all tracked shows with watch progress summaries."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        # Subquery: count of watched episodes (at least one completed event)
        watched_sub = (
            session.query(
                Episode.show_id,
                func.count(func.distinct(Episode.id)).label("episodes_watched"),
            )
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .filter(WatchEvent.completed == True)  # noqa: E712
            .group_by(Episode.show_id)
            .subquery()
        )

        # Subquery: total episode count per show
        total_sub = (
            session.query(
                Episode.show_id,
                func.count(Episode.id).label("total_episodes"),
            )
            .group_by(Episode.show_id)
            .subquery()
        )

        # Subquery: last watched timestamp per show
        last_sub = (
            session.query(
                Episode.show_id,
                func.max(WatchEvent.started_at).label("last_watched"),
            )
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .group_by(Episode.show_id)
            .subquery()
        )

        rows = (
            session.query(
                Show.id,
                Show.title,
                Show.poster_path,
                Show.total_seasons,
                Show.status,
                func.coalesce(watched_sub.c.episodes_watched, 0).label("episodes_watched"),
                func.coalesce(total_sub.c.total_episodes, 0).label("total_episodes"),
                last_sub.c.last_watched,
            )
            .outerjoin(watched_sub, watched_sub.c.show_id == Show.id)
            .outerjoin(total_sub, total_sub.c.show_id == Show.id)
            .outerjoin(last_sub, last_sub.c.show_id == Show.id)
            .filter(total_sub.c.total_episodes > 0)
            .order_by(text("last_watched DESC NULLS LAST"))
            .all()
        )

        return [
            ShowSummary(
                show_id=r.id,
                title=r.title,
                poster_path=r.poster_path,
                total_seasons=r.total_seasons,
                status=r.status,
                episodes_watched=r.episodes_watched,
                total_episodes=r.total_episodes,
                last_watched=r.last_watched,
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /api/history/shows/{show_id}
# ---------------------------------------------------------------------------

@router.get("/shows/{show_id}", response_model=ShowDetail)
async def get_show_detail(show_id: int, request: Request) -> ShowDetail:
    """Return show detail with season/episode grid."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        show = session.query(Show).filter(Show.id == show_id).first()
        if show is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Show not found")

        episodes = (
            session.query(
                Episode.id,
                Episode.season_number,
                Episode.episode_number,
                Episode.title,
                Episode.air_date,
                Episode.runtime_minutes,
                func.max(case(
                    (WatchEvent.completed == True, 1),  # noqa: E712
                    else_=0,
                )).label("watched"),
                func.max(WatchEvent.started_at).label("last_watched"),
                func.count(WatchEvent.id).label("watch_count"),
            )
            .outerjoin(WatchEvent, WatchEvent.episode_id == Episode.id)
            .filter(Episode.show_id == show_id)
            .group_by(Episode.id)
            .order_by(Episode.season_number, Episode.episode_number)
            .all()
        )

        # Group into seasons
        seasons_map: dict[int, list[EpisodeGridItem]] = {}
        for ep in episodes:
            item = EpisodeGridItem(
                episode_id=ep.id,
                episode_number=ep.episode_number,
                title=ep.title,
                air_date=ep.air_date,
                runtime_minutes=ep.runtime_minutes,
                watched=bool(ep.watched),
                last_watched=ep.last_watched,
                watch_count=ep.watch_count,
            )
            seasons_map.setdefault(ep.season_number, []).append(item)

        seasons = [
            SeasonInfo(season_number=sn, episodes=eps)
            for sn, eps in sorted(seasons_map.items())
        ]

        return ShowDetail(
            show_id=show.id,
            title=show.title,
            original_title=show.original_title,
            poster_path=show.poster_path,
            first_air_date=show.first_air_date,
            status=show.status,
            total_seasons=show.total_seasons,
            tmdb_id=show.tmdb_id,
            seasons=seasons,
        )


# ---------------------------------------------------------------------------
# GET /api/history/shows/{show_id}/progress
# ---------------------------------------------------------------------------

@router.get("/shows/{show_id}/progress", response_model=list[EpisodeProgress])
async def get_show_progress(show_id: int, request: Request) -> list[EpisodeProgress]:
    """Return episode-level progress for a show."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                Episode.id,
                Episode.season_number,
                Episode.episode_number,
                Episode.title,
                func.max(case(
                    (WatchEvent.completed == True, 1),  # noqa: E712
                    else_=0,
                )).label("watched"),
                func.max(WatchEvent.duration_seconds).label("longest_watch"),
                func.max(WatchEvent.started_at).label("last_watched"),
            )
            .outerjoin(WatchEvent, WatchEvent.episode_id == Episode.id)
            .filter(Episode.show_id == show_id)
            .group_by(Episode.id)
            .order_by(Episode.season_number, Episode.episode_number)
            .all()
        )

        return [
            EpisodeProgress(
                episode_id=r.id,
                season_number=r.season_number,
                episode_number=r.episode_number,
                episode_title=r.title,
                watched=bool(r.watched),
                longest_watch=r.longest_watch,
                last_watched=r.last_watched,
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /api/history/next-to-watch
# ---------------------------------------------------------------------------

@router.get("/next-to-watch", response_model=list[NextToWatch])
async def get_next_to_watch(request: Request) -> list[NextToWatch]:
    """Return next unwatched episode per show.

    Only includes shows where the user has watched at least one episode.
    """
    db = request.app.state.db
    with db.get_watch_session() as session:
        # Shows with at least one watch event
        watched_shows = (
            session.query(Episode.show_id)
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .distinct()
            .subquery()
        )

        # Episodes marked as completed
        completed_episodes = (
            session.query(WatchEvent.episode_id)
            .filter(WatchEvent.completed == True)  # noqa: E712
            .distinct()
            .subquery()
        )

        # First unwatched episode per show
        rows = (
            session.query(
                Show.id.label("show_id"),
                Show.title.label("show_title"),
                Show.poster_path,
                Episode.season_number,
                Episode.episode_number,
                Episode.title.label("episode_title"),
            )
            .join(Episode, Episode.show_id == Show.id)
            .filter(Show.id.in_(session.query(watched_shows.c.show_id)))
            .filter(~Episode.id.in_(session.query(completed_episodes.c.episode_id)))
            .order_by(Show.id, Episode.season_number, Episode.episode_number)
            .all()
        )

        # Deduplicate: keep only the first unwatched per show
        seen: set[int] = set()
        results: list[NextToWatch] = []
        for r in rows:
            if r.show_id not in seen:
                seen.add(r.show_id)
                results.append(
                    NextToWatch(
                        show_id=r.show_id,
                        show_title=r.show_title,
                        poster_path=r.poster_path,
                        next_season=r.season_number,
                        next_episode=r.episode_number,
                        episode_title=r.episode_title,
                    )
                )

        return results


# ---------------------------------------------------------------------------
# GET /api/history/stats
# ---------------------------------------------------------------------------

@router.get("/stats", response_model=WatchStats)
async def get_stats(request: Request) -> WatchStats:
    """Return watch time statistics: totals, by show, and by week."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        # Total stats
        totals = (
            session.query(
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_time"),
                func.count(
                    func.distinct(
                        case(
                            (WatchEvent.completed == True, WatchEvent.episode_id),  # noqa: E712
                            else_=None,
                        )
                    )
                ).label("total_episodes"),
            )
            .first()
        )

        total_shows = (
            session.query(func.count(func.distinct(Episode.show_id)))
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .scalar()
        ) or 0

        # YouTube totals
        yt_count = session.query(func.count(YouTubeWatch.id)).scalar() or 0
        yt_time = (
            session.query(
                func.coalesce(func.sum(YouTubeWatch.watched_seconds), 0)
            ).scalar()
            or 0
        )

        # By show
        by_show_rows = (
            session.query(
                Show.id,
                Show.title,
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.count(WatchEvent.id).label("episode_count"),
            )
            .join(Episode, Episode.show_id == Show.id)
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .group_by(Show.id)
            .order_by(text("total_seconds DESC"))
            .all()
        )

        # By week (using SQLite strftime)
        by_week_rows = (
            session.query(
                func.strftime("%Y-W%W", WatchEvent.started_at).label("week"),
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.count(WatchEvent.id).label("episode_count"),
            )
            .group_by(text("week"))
            .order_by(text("week DESC"))
            .limit(52)
            .all()
        )

        episode_time = totals.total_time if totals else 0
        return WatchStats(
            total_watch_time_seconds=episode_time + yt_time,
            total_episodes_watched=totals.total_episodes if totals else 0,
            total_shows=total_shows,
            total_youtube_watches=yt_count,
            by_show=[
                ShowWatchTime(
                    show_id=r.id,
                    show_title=r.title,
                    total_seconds=r.total_seconds,
                    episode_count=r.episode_count,
                )
                for r in by_show_rows
            ],
            by_week=[
                WeekWatchTime(
                    week=r.week or "unknown",
                    total_seconds=r.total_seconds,
                    episode_count=r.episode_count,
                )
                for r in by_week_rows
            ],
        )
