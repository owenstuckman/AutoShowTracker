"""Storage layer for AutoShowTracker.

Public API::

    from show_tracker.storage import DatabaseManager, WatchRepository, CacheRepository

    db = DatabaseManager(data_dir="~/.show_tracker")
    db.init_databases()

    with db.get_watch_session() as session:
        repo = WatchRepository(session)
        show = repo.upsert_show(tmdb_id=1396, title="Breaking Bad")
"""

from show_tracker.storage.database import DatabaseManager
from show_tracker.storage.models import (
    CacheBase,
    Episode,
    FailedLookup,
    Show,
    ShowAlias,
    TMDbEpisodeCache,
    TMDbSearchCache,
    TMDbShowCache,
    UnresolvedEvent,
    UserSetting,
    WatchBase,
    WatchEvent,
    YouTubeWatch,
)
from show_tracker.storage.repository import CacheRepository, WatchRepository

__all__ = [
    "CacheBase",
    "CacheRepository",
    "DatabaseManager",
    "Episode",
    "FailedLookup",
    "Show",
    "ShowAlias",
    "TMDbEpisodeCache",
    "TMDbSearchCache",
    "TMDbShowCache",
    "UnresolvedEvent",
    "UserSetting",
    "WatchBase",
    "WatchEvent",
    "WatchRepository",
    "YouTubeWatch",
]
