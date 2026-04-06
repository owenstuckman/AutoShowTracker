"""Advanced watch time analytics API routes.

Provides daily, weekly, monthly time-series data, binge detection,
and viewing pattern analysis.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import Integer, func, text

from show_tracker.storage.models import Episode, Show, WatchEvent

router = APIRouter(prefix="/api/stats", tags=["stats"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DayStats(BaseModel):
    date: str
    total_seconds: int = 0
    episode_count: int = 0
    top_show: str | None = None


class WeekStats(BaseModel):
    week: str  # "2026-W12"
    total_seconds: int = 0
    episode_count: int = 0
    top_show: str | None = None


class MonthStats(BaseModel):
    month: str  # "2026-03"
    total_seconds: int = 0
    episode_count: int = 0
    top_show: str | None = None


class BingeSession(BaseModel):
    show_id: int
    show_title: str
    date: str
    episode_count: int
    total_seconds: int = 0
    first_episode: str = ""
    last_episode: str = ""


class ViewingPattern(BaseModel):
    hour_distribution: list[int] = Field(
        default_factory=lambda: [0] * 24,
        description="Episode count per hour of day (0-23)",
    )
    weekday_distribution: list[int] = Field(
        default_factory=lambda: [0] * 7,
        description="Episode count per weekday (0=Mon, 6=Sun)",
    )
    avg_session_minutes: float = 0.0
    most_active_hour: int = 0
    most_active_day: str = ""


# ---------------------------------------------------------------------------
# GET /api/stats/daily
# ---------------------------------------------------------------------------


@router.get("/daily", response_model=list[DayStats])
async def get_daily_stats(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
) -> list[DayStats]:
    """Return per-day watch statistics for the last N days."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                func.date(WatchEvent.started_at).label("day"),
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.count(WatchEvent.id).label("episode_count"),
            )
            .group_by(text("day"))
            .order_by(text("day DESC"))
            .limit(days)
            .all()
        )

        results = []
        for r in rows:
            # Find top show for this day
            top = (
                session.query(
                    Show.title,
                    func.count(WatchEvent.id).label("cnt"),
                )
                .join(Episode, Episode.show_id == Show.id)
                .join(WatchEvent, WatchEvent.episode_id == Episode.id)
                .filter(func.date(WatchEvent.started_at) == r.day)
                .group_by(Show.id)
                .order_by(text("cnt DESC"))
                .first()
            )

            results.append(
                DayStats(
                    date=r.day or "",
                    total_seconds=r.total_seconds,
                    episode_count=r.episode_count,
                    top_show=top.title if top else None,
                )
            )

        return results


# ---------------------------------------------------------------------------
# GET /api/stats/weekly
# ---------------------------------------------------------------------------


@router.get("/weekly", response_model=list[WeekStats])
async def get_weekly_stats(
    request: Request,
    weeks: int = Query(default=12, ge=1, le=104),
) -> list[WeekStats]:
    """Return per-week watch statistics."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                func.strftime("%Y-W%W", WatchEvent.started_at).label("week"),
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.count(WatchEvent.id).label("episode_count"),
            )
            .group_by(text("week"))
            .order_by(text("week DESC"))
            .limit(weeks)
            .all()
        )

        return [
            WeekStats(
                week=r.week or "",
                total_seconds=r.total_seconds,
                episode_count=r.episode_count,
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /api/stats/monthly
# ---------------------------------------------------------------------------


@router.get("/monthly", response_model=list[MonthStats])
async def get_monthly_stats(
    request: Request,
    months: int = Query(default=12, ge=1, le=60),
) -> list[MonthStats]:
    """Return per-month watch statistics."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                func.strftime("%Y-%m", WatchEvent.started_at).label("month"),
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.count(WatchEvent.id).label("episode_count"),
            )
            .group_by(text("month"))
            .order_by(text("month DESC"))
            .limit(months)
            .all()
        )

        return [
            MonthStats(
                month=r.month or "",
                total_seconds=r.total_seconds,
                episode_count=r.episode_count,
            )
            for r in rows
        ]


# ---------------------------------------------------------------------------
# GET /api/stats/binge-sessions
# ---------------------------------------------------------------------------


@router.get("/binge-sessions", response_model=list[BingeSession])
async def get_binge_sessions(
    request: Request,
    min_episodes: int = Query(default=3, ge=2, le=20),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[BingeSession]:
    """Detect binge sessions: 3+ episodes of the same show on the same day."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        rows = (
            session.query(
                Show.id.label("show_id"),
                Show.title.label("show_title"),
                func.date(WatchEvent.started_at).label("day"),
                func.count(WatchEvent.id).label("ep_count"),
                func.coalesce(func.sum(WatchEvent.duration_seconds), 0).label("total_seconds"),
                func.min(Episode.season_number * 1000 + Episode.episode_number).label("first_ep"),
                func.max(Episode.season_number * 1000 + Episode.episode_number).label("last_ep"),
            )
            .join(Episode, Episode.show_id == Show.id)
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .group_by(Show.id, text("day"))
            .having(func.count(WatchEvent.id) >= min_episodes)
            .order_by(text("day DESC"))
            .limit(limit)
            .all()
        )

        results = []
        for r in rows:
            first_s, first_e = divmod(r.first_ep, 1000)
            last_s, last_e = divmod(r.last_ep, 1000)
            results.append(
                BingeSession(
                    show_id=r.show_id,
                    show_title=r.show_title,
                    date=r.day or "",
                    episode_count=r.ep_count,
                    total_seconds=r.total_seconds,
                    first_episode=f"S{first_s:02d}E{first_e:02d}",
                    last_episode=f"S{last_s:02d}E{last_e:02d}",
                )
            )

        return results


# ---------------------------------------------------------------------------
# GET /api/stats/patterns
# ---------------------------------------------------------------------------


@router.get("/patterns", response_model=ViewingPattern)
async def get_viewing_patterns(request: Request) -> ViewingPattern:
    """Analyze viewing patterns: time-of-day, day-of-week, session length."""
    db = request.app.state.db
    with db.get_watch_session() as session:
        # Hour distribution (SQLite strftime %H = hour 00-23)
        hour_rows = (
            session.query(
                func.cast(func.strftime("%H", WatchEvent.started_at), type_=Integer).label("hour"),
                func.count(WatchEvent.id).label("cnt"),
            )
            .group_by(text("hour"))
            .all()
        )

        hours = [0] * 24
        for r in hour_rows:
            if r.hour is not None and 0 <= r.hour < 24:
                hours[r.hour] = r.cnt

        # Weekday distribution (SQLite strftime %w: 0=Sunday, 1=Monday, ...)
        day_rows = (
            session.query(
                func.cast(func.strftime("%w", WatchEvent.started_at), type_=Integer).label("dow"),
                func.count(WatchEvent.id).label("cnt"),
            )
            .group_by(text("dow"))
            .all()
        )

        # Convert SQLite %w (0=Sun) to ISO (0=Mon)
        weekdays = [0] * 7
        for r in day_rows:
            if r.dow is not None:
                iso_day = (r.dow - 1) % 7  # 0=Mon ... 6=Sun
                weekdays[iso_day] = r.cnt

        # Average session duration
        avg_dur = (
            session.query(
                func.avg(WatchEvent.duration_seconds).label("avg"),
            )
            .filter(WatchEvent.duration_seconds.isnot(None))
            .scalar()
        ) or 0.0

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        most_active_day_idx = weekdays.index(max(weekdays)) if any(weekdays) else 0

        return ViewingPattern(
            hour_distribution=hours,
            weekday_distribution=weekdays,
            avg_session_minutes=round(avg_dur / 60.0, 1),
            most_active_hour=hours.index(max(hours)) if any(hours) else 0,
            most_active_day=day_names[most_active_day_idx],
        )
