"""Alembic environment configuration for AutoShowTracker.

Supports both watch_history.db and media_cache.db migrations.
The target database is selected via the ``--x db=watch`` or ``--x db=cache``
command-line argument. Defaults to watch_history.db.

Usage:
    alembic upgrade head                    # migrate watch_history.db
    alembic -x db=cache upgrade head        # migrate media_cache.db
    alembic revision --autogenerate -m "desc"
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from show_tracker.config import load_settings
from show_tracker.storage.models import WatchBase, CacheBase

# Alembic Config object
config = context.config

# Setup logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Determine which database to target
db_choice = context.get_x_argument(as_dictionary=True).get("db", "watch")

settings = load_settings()
settings.ensure_directories()

if db_choice == "cache":
    target_metadata = CacheBase.metadata
    db_url = f"sqlite:///{settings.media_cache_db}"
else:
    target_metadata = WatchBase.metadata
    db_url = f"sqlite:///{settings.watch_history_db}"

config.set_main_option("sqlalchemy.url", db_url)


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without connecting)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # Required for SQLite ALTER TABLE support
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (connects to the database)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # Required for SQLite ALTER TABLE support
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
