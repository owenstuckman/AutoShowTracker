"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-03-25

Creates all tables for watch_history.db:
- shows, episodes, watch_events, youtube_watches, movie_watches,
  show_aliases, unresolved_events, user_settings
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- shows ---------------------------------------------------------------
    op.create_table(
        "shows",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tmdb_id", sa.Integer, unique=True, nullable=True),
        sa.Column("tvdb_id", sa.Integer, nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("original_title", sa.Text, nullable=True),
        sa.Column("poster_path", sa.Text, nullable=True),
        sa.Column("first_air_date", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=True),
        sa.Column("total_seasons", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Text),
        sa.Column("updated_at", sa.Text),
    )
    op.create_index("idx_shows_tmdb", "shows", ["tmdb_id"])
    op.create_index("idx_shows_title", "shows", ["title"])

    # -- episodes ------------------------------------------------------------
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer, sa.ForeignKey("shows.id"), nullable=False),
        sa.Column("tmdb_episode_id", sa.Integer, unique=True, nullable=True),
        sa.Column("season_number", sa.Integer, nullable=False),
        sa.Column("episode_number", sa.Integer, nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("air_date", sa.Text, nullable=True),
        sa.Column("runtime_minutes", sa.Integer, nullable=True),
        sa.Column("created_at", sa.Text),
        sa.UniqueConstraint("show_id", "season_number", "episode_number"),
    )
    op.create_index("idx_episodes_show", "episodes", ["show_id"])
    op.create_index("idx_episodes_lookup", "episodes", ["show_id", "season_number", "episode_number"])

    # -- watch_events --------------------------------------------------------
    op.create_table(
        "watch_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("episode_id", sa.Integer, sa.ForeignKey("episodes.id"), nullable=False),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("ended_at", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("completed", sa.Boolean, default=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_detail", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("raw_input", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text),
    )
    op.create_index("idx_watch_events_episode", "watch_events", ["episode_id"])
    op.create_index("idx_watch_events_time", "watch_events", ["started_at"])
    op.create_index("idx_watch_events_confidence", "watch_events", ["confidence"])

    # -- youtube_watches -----------------------------------------------------
    op.create_table(
        "youtube_watches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("video_id", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("channel_name", sa.Text, nullable=True),
        sa.Column("channel_id", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("watched_seconds", sa.Integer, nullable=True),
        sa.Column("playlist_id", sa.Text, nullable=True),
        sa.Column("playlist_index", sa.Integer, nullable=True),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("ended_at", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text),
    )
    op.create_index("idx_youtube_video", "youtube_watches", ["video_id"])
    op.create_index("idx_youtube_playlist", "youtube_watches", ["playlist_id"])

    # -- movie_watches -------------------------------------------------------
    op.create_table(
        "movie_watches",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tmdb_movie_id", sa.Integer, nullable=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("original_title", sa.Text, nullable=True),
        sa.Column("year", sa.Integer, nullable=True),
        sa.Column("poster_path", sa.Text, nullable=True),
        sa.Column("started_at", sa.Text, nullable=False),
        sa.Column("ended_at", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("completed", sa.Boolean, default=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_detail", sa.Text, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("raw_input", sa.Text, nullable=True),
        sa.Column("created_at", sa.Text),
    )
    op.create_index("idx_movie_watches_tmdb", "movie_watches", ["tmdb_movie_id"])
    op.create_index("idx_movie_watches_time", "movie_watches", ["started_at"])

    # -- show_aliases --------------------------------------------------------
    op.create_table(
        "show_aliases",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.Integer, sa.ForeignKey("shows.id"), nullable=False),
        sa.Column("alias", sa.Text, nullable=False, unique=True),
        sa.Column("source", sa.Text, default="system"),
    )
    op.create_index("idx_aliases_lookup", "show_aliases", ["alias"])

    # -- unresolved_events ---------------------------------------------------
    op.create_table(
        "unresolved_events",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("raw_input", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("source_detail", sa.Text, nullable=True),
        sa.Column("detected_at", sa.Text, nullable=False),
        sa.Column("best_guess_show", sa.Text, nullable=True),
        sa.Column("best_guess_season", sa.Integer, nullable=True),
        sa.Column("best_guess_episode", sa.Integer, nullable=True),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("resolved", sa.Boolean, default=False),
        sa.Column("resolved_episode_id", sa.Integer, sa.ForeignKey("episodes.id"), nullable=True),
        sa.Column("created_at", sa.Text),
    )
    op.create_index(
        "idx_unresolved_pending",
        "unresolved_events",
        ["resolved"],
        sqlite_where=sa.text("resolved = 0"),
    )

    # -- user_settings -------------------------------------------------------
    op.create_table(
        "user_settings",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("updated_at", sa.Text),
    )


def downgrade() -> None:
    op.drop_table("user_settings")
    op.drop_table("unresolved_events")
    op.drop_table("show_aliases")
    op.drop_table("movie_watches")
    op.drop_table("youtube_watches")
    op.drop_table("watch_events")
    op.drop_table("episodes")
    op.drop_table("shows")
