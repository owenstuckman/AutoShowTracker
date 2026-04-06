"""Database manager for AutoShowTracker.

Manages two SQLite databases:
- watch_history.db: user's watch log and preferences
- media_cache.db: cached TMDb/TVDb data (rebuildable)
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

if TYPE_CHECKING:
    from collections.abc import Generator

    from sqlalchemy.engine import Engine

from show_tracker.storage.models import CacheBase, WatchBase


def _enable_sqlite_fk(dbapi_conn: Any, connection_record: Any) -> None:
    """Enable foreign key enforcement for every new SQLite connection."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def _enable_wal(dbapi_conn: Any, connection_record: Any) -> None:
    """Enable WAL journal mode for better concurrent read performance."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode = WAL")
    cursor.close()


class DatabaseManager:
    """Creates and manages both SQLite databases and provides session factories.

    Usage::

        db = DatabaseManager(data_dir="~/.show_tracker")
        db.init_databases()

        with db.get_watch_session() as session:
            session.add(Show(title="Breaking Bad", tmdb_id=1396))

        with db.get_cache_session() as session:
            session.add(TMDbShowCache(tmdb_id=1396, data="{}"))
    """

    def __init__(self, data_dir: str | Path | None = None) -> None:
        """Initialise the database manager.

        Args:
            data_dir: Directory where database files are stored.
                      Defaults to ``~/.show_tracker``.
        """
        if data_dir is None:
            data_dir = Path.home() / ".show_tracker"
        self._data_dir = Path(data_dir)

        self._watch_engine: Engine | None = None
        self._cache_engine: Engine | None = None
        self._WatchSession: sessionmaker[Session] | None = None
        self._CacheSession: sessionmaker[Session] | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def data_dir(self) -> Path:
        return self._data_dir

    @property
    def watch_db_path(self) -> Path:
        return self._data_dir / "watch_history.db"

    @property
    def cache_db_path(self) -> Path:
        return self._data_dir / "media_cache.db"

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_databases(self) -> None:
        """Create database files and all tables.

        Safe to call multiple times; existing tables are not recreated.
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Watch history database
        self._watch_engine = create_engine(
            f"sqlite:///{self.watch_db_path}",
            echo=False,
        )
        event.listen(self._watch_engine, "connect", _enable_sqlite_fk)
        event.listen(self._watch_engine, "connect", _enable_wal)
        WatchBase.metadata.create_all(self._watch_engine)
        self._WatchSession = sessionmaker(bind=self._watch_engine)

        # Media cache database
        self._cache_engine = create_engine(
            f"sqlite:///{self.cache_db_path}",
            echo=False,
        )
        event.listen(self._cache_engine, "connect", _enable_wal)
        CacheBase.metadata.create_all(self._cache_engine)
        self._CacheSession = sessionmaker(bind=self._cache_engine)

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    @contextmanager
    def get_watch_session(self) -> Generator[Session, None, None]:
        """Provide a transactional session scope for watch_history.db.

        Commits on success, rolls back on exception, always closes.
        """
        if self._WatchSession is None:
            raise RuntimeError("Databases not initialised. Call init_databases() first.")
        session = self._WatchSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @contextmanager
    def get_cache_session(self) -> Generator[Session, None, None]:
        """Provide a transactional session scope for media_cache.db.

        Commits on success, rolls back on exception, always closes.
        """
        if self._CacheSession is None:
            raise RuntimeError("Databases not initialised. Call init_databases() first.")
        session = self._CacheSession()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Teardown
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Dispose of engine connections."""
        if self._watch_engine is not None:
            self._watch_engine.dispose()
        if self._cache_engine is not None:
            self._cache_engine.dispose()
