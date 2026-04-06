"""New episode desktop notifications.

Checks TMDb for upcoming air dates of shows the user is watching
and sends desktop notifications via plyer when episodes air today
or tomorrow.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from show_tracker.storage.models import Episode, Show, UserSetting, WatchEvent

if TYPE_CHECKING:
    from show_tracker.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


def check_new_episodes(
    db: DatabaseManager,
    tmdb_api_key: str,
) -> list[dict[str, Any]]:
    """Check TMDb for new episodes airing today or tomorrow.

    Only checks shows that the user has watched at least one episode of.

    Returns:
        List of dicts with keys: show_name, season, episode, episode_title, air_date
    """
    from show_tracker.identification.tmdb_client import TMDbClient, TMDbError

    today = date.today()
    tomorrow = today + timedelta(days=1)
    upcoming: list[dict[str, Any]] = []

    with db.get_watch_session() as session:
        # Get shows the user is actively watching (has watch events)
        show_rows = (
            session.query(Show.id, Show.title, Show.tmdb_id, Show.total_seasons)
            .join(Episode, Episode.show_id == Show.id)
            .join(WatchEvent, WatchEvent.episode_id == Episode.id)
            .filter(Show.tmdb_id.isnot(None))
            .filter(Show.status != "Ended")
            .distinct()
            .all()
        )

    if not show_rows:
        return upcoming

    client = TMDbClient(api_key=tmdb_api_key)
    try:
        for show in show_rows:
            if show.tmdb_id is None or show.total_seasons is None:
                continue

            try:
                # Check the latest season for upcoming episodes
                season_data = client.get_season(show.tmdb_id, show.total_seasons)
                episodes = season_data.get("episodes", [])

                for ep in episodes:
                    air_date_str = ep.get("air_date")
                    if not air_date_str:
                        continue

                    try:
                        air_date = date.fromisoformat(air_date_str)
                    except ValueError:
                        continue

                    if air_date in (today, tomorrow):
                        upcoming.append(
                            {
                                "show_name": show.title,
                                "season": ep.get("season_number"),
                                "episode": ep.get("episode_number"),
                                "episode_title": ep.get("name", ""),
                                "air_date": air_date_str,
                            }
                        )

            except TMDbError:
                logger.debug("Failed to check episodes for %s", show.title)
                continue
    finally:
        client.close()

    return upcoming


def send_notification(title: str, message: str) -> bool:
    """Send a desktop notification via plyer.

    Returns True if the notification was sent successfully.
    """
    try:
        from plyer import notification  # type: ignore[import-not-found]

        notification.notify(
            title=title,
            message=message,
            app_name="Show Tracker",
            timeout=10,
        )
        return True
    except ImportError:
        logger.debug("plyer not installed — cannot send desktop notification")
        return False
    except Exception:
        logger.debug("Failed to send notification", exc_info=True)
        return False


def notify_new_episodes(db: DatabaseManager, tmdb_api_key: str) -> int:
    """Check for and notify about new episodes.

    Tracks the last notification date in user_settings to avoid
    duplicate notifications.

    Returns:
        Number of notifications sent.
    """
    today_str = date.today().isoformat()

    # Check if we already notified today
    with db.get_watch_session() as session:
        setting = (
            session.query(UserSetting).filter(UserSetting.key == "last_notification_date").first()
        )

        if setting and setting.value == today_str:
            logger.debug("Already checked for notifications today")
            return 0

    # Check for new episodes
    upcoming = check_new_episodes(db, tmdb_api_key)

    if not upcoming:
        logger.debug("No new episodes found")
        _update_notification_date(db, today_str)
        return 0

    # Send notifications
    count = 0
    for ep in upcoming:
        title = f"New Episode: {ep['show_name']}"
        message = (
            f"S{ep['season']:02d}E{ep['episode']:02d}: {ep['episode_title']}\n"
            f"Airs: {ep['air_date']}"
        )
        if send_notification(title, message):
            count += 1

    _update_notification_date(db, today_str)
    logger.info("Sent %d new episode notifications", count)
    return count


def _update_notification_date(db: DatabaseManager, date_str: str) -> None:
    """Update the last notification check date in user settings."""
    with db.get_watch_session() as session:
        setting = (
            session.query(UserSetting).filter(UserSetting.key == "last_notification_date").first()
        )

        if setting:
            setting.value = date_str
        else:
            setting = UserSetting(key="last_notification_date", value=date_str)
            session.add(setting)

        session.commit()
