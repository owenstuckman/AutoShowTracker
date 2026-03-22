"""FastAPI application for AutoShowTracker.

Creates the ASGI app, registers CORS middleware, includes all routers,
and manages database lifecycle via startup/shutdown events.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from show_tracker import __version__
from show_tracker.config import load_settings
from show_tracker.storage.database import DatabaseManager
from show_tracker.api.schemas import HealthResponse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state — accessible via app.state from route handlers
# ---------------------------------------------------------------------------

_settings = load_settings()
_db = DatabaseManager(data_dir=_settings.data_dir)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Initialise databases on startup, start detection, close on shutdown."""
    _settings.ensure_directories()
    _db.init_databases()
    app.state.db = _db
    app.state.settings = _settings

    # -- Start the detection service ----------------------------------------
    from show_tracker.detection.activitywatch import ActivityWatchClient
    from show_tracker.detection.detection_service import DetectionService
    from show_tracker.detection.media_session import get_media_listener

    # Create ActivityWatch client (connects to existing AW server if running).
    aw_client: ActivityWatchClient | None = None
    try:
        client = ActivityWatchClient(port=_settings.activitywatch_port)
        client.get_buckets()  # quick connectivity check
        aw_client = client
        logger.info("Connected to ActivityWatch on port %d", _settings.activitywatch_port)
    except Exception:
        logger.info(
            "ActivityWatch not reachable on port %d — AW polling disabled",
            _settings.activitywatch_port,
        )

    # Create platform media listener (SMTC on Windows, MPRIS on Linux, None on WSL).
    media_listener = None
    try:
        media_listener = get_media_listener()
        if media_listener is not None:
            logger.info("Media listener: %s", type(media_listener).__name__)
        else:
            logger.info("No media listener available on this platform")
    except Exception:
        logger.warning("Failed to create media listener", exc_info=True)

    detection = DetectionService(
        aw_client=aw_client,
        media_listener=media_listener,
        polling_interval=_settings.polling_interval,
        heartbeat_interval=_settings.heartbeat_interval,
        grace_period=_settings.grace_period,
        auto_log_threshold=_settings.auto_log_threshold,
        review_threshold=_settings.review_threshold,
    )

    # Log all detection events to the console/file for visibility.
    def _on_detection(event, tier):  # type: ignore[no-untyped-def]
        logger.info(
            "Detection [%s]: source=%s title=%r app=%s url=%s",
            tier.value,
            event.source,
            event.media_title or event.window_title or event.page_title,
            event.app_name,
            event.url[:80] if event.url else "",
        )

    detection.register_result_callback(_on_detection)

    # -- Persistence callback: identify and store watch events ---------------

    from show_tracker.detection.detection_service import ConfidenceTier
    from show_tracker.identification.resolver import EpisodeResolver
    from show_tracker.identification.tmdb_client import TMDbClient
    from show_tracker.storage.repository import WatchRepository
    from show_tracker.storage.models import UnresolvedEvent, _utcnow

    import re as _re

    def _is_youtube_url(url: str | None) -> bool:
        if not url:
            return False
        return bool(_re.search(r"(youtube\.com/watch|youtu\.be/|youtube\.com/embed/)", url))

    def _extract_youtube_video_id(url: str) -> str | None:
        m = _re.search(r"[?&]v=([a-zA-Z0-9_-]{11})", url)
        if m:
            return m.group(1)
        m = _re.search(r"youtu\.be/([a-zA-Z0-9_-]{11})", url)
        if m:
            return m.group(1)
        m = _re.search(r"embed/([a-zA-Z0-9_-]{11})", url)
        if m:
            return m.group(1)
        return None

    def _persist_detection(event, tier):  # type: ignore[no-untyped-def]
        """Identify the detected media and persist it to the database."""
        # Build the best raw string from available metadata.
        raw_string = (
            event.media_title
            or event.window_title
            or event.page_title
            or event.url
        )
        if not raw_string:
            return

        logger.debug(
            "Persist callback: raw=%r source=%s tier=%s url=%s",
            raw_string[:80], event.source, tier.value if tier else "?",
            (event.url or "")[:80],
        )

        # -- YouTube: store as YouTubeWatch instead of episode ----------------
        if _is_youtube_url(event.url):
            video_id = _extract_youtube_video_id(event.url)
            if not video_id:
                logger.debug("YouTube URL but no video ID: %s", event.url)
                return
            title = (
                event.media_title
                or event.page_title
                or event.window_title
                or "Unknown"
            )
            # Strip common YouTube suffixes from window titles
            title = _re.sub(r"\s*[-–]\s*YouTube\s*$", "", title).strip() or title
            try:
                with _db.get_watch_session() as session:
                    repo = WatchRepository(session)
                    repo.create_youtube_watch(
                        video_id=video_id,
                        title=title,
                        started_at=_utcnow(),
                    )
                logger.info("Persisted YouTube watch: %s (%s)", title[:60], video_id)
            except Exception:
                logger.warning("Failed to persist YouTube watch %s", video_id, exc_info=True)
            return

        # -- TV episode identification ----------------------------------------
        # Skip if no TMDb key configured — can't identify without it.
        if not _settings.has_tmdb_key():
            logger.debug("No TMDb key — skipping identification for %r", raw_string[:60])
            return

        try:
            client = TMDbClient(api_key=_settings.tmdb_api_key)
            try:
                resolver = EpisodeResolver(tmdb_client=client)
                result = resolver.resolve(
                    raw_string,
                    source_type=event.source,
                    url=event.url or None,
                )
            finally:
                client.close()
        except Exception:
            logger.warning("Identification failed for %r", raw_string, exc_info=True)
            return

        # Route by confidence.
        try:
            with _db.get_watch_session() as session:
                repo = WatchRepository(session)

                if result.tmdb_show_id is not None and result.season is not None and result.episode is not None:
                    # We have a resolved episode — persist it.
                    show = repo.upsert_show(
                        tmdb_id=result.tmdb_show_id,
                        title=result.show_name,
                    )
                    episode = repo.upsert_episode(
                        show_id=show.id,
                        season_number=result.season,
                        episode_number=result.episode,
                        tmdb_episode_id=result.tmdb_episode_id,
                        title=result.episode_title,
                    )

                    repo.process_heartbeat(
                        episode_id=episode.id,
                        source=event.source,
                        confidence=result.confidence,
                        raw_input=raw_string,
                        source_detail=event.url[:200] if event.url else None,
                    )

                    logger.info(
                        "Persisted watch: %s S%02dE%02d (confidence=%.2f)",
                        result.show_name,
                        result.season,
                        result.episode,
                        result.confidence,
                    )
                elif tier == ConfidenceTier.UNRESOLVED:
                    # Low confidence / unresolved — queue for manual resolution.
                    unresolved = UnresolvedEvent(
                        raw_input=raw_string,
                        source=event.source,
                        source_detail=event.url[:200] if event.url else None,
                        detected_at=_utcnow(),
                        best_guess_show=result.show_name or None,
                        best_guess_season=result.season,
                        best_guess_episode=result.episode,
                        confidence=result.confidence,
                    )
                    session.add(unresolved)
                    logger.info(
                        "Queued unresolved: %r (confidence=%.2f)",
                        raw_string,
                        result.confidence,
                    )
                else:
                    logger.debug(
                        "Skipped: %r (tier=%s, tmdb_show=%s, season=%s, ep=%s, conf=%.2f)",
                        raw_string[:60], tier.value if tier else "?",
                        result.tmdb_show_id, result.season, result.episode,
                        result.confidence,
                    )
        except Exception:
            logger.warning("Failed to persist detection for %r", raw_string[:60], exc_info=True)

    detection.register_result_callback(_persist_detection)

    try:
        await detection.start()
        logger.info("DetectionService started")
    except Exception:
        logger.warning("DetectionService failed to start", exc_info=True)

    app.state.detection = detection

    yield

    # -- Shutdown -----------------------------------------------------------
    try:
        await detection.stop()
        logger.info("DetectionService stopped")
    except Exception:
        logger.warning("Error stopping DetectionService", exc_info=True)

    _db.close()


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

app = FastAPI(
    title="AutoShowTracker",
    version=__version__,
    description="Automatic cross-platform TV show tracking",
    lifespan=lifespan,
)

# CORS — allow local development origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:7600",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:7600",
        "chrome-extension://*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------

from show_tracker.api.routes_media import router as media_router  # noqa: E402
from show_tracker.api.routes_history import router as history_router  # noqa: E402
from show_tracker.api.routes_unresolved import router as unresolved_router  # noqa: E402
from show_tracker.api.routes_settings import router as settings_router  # noqa: E402
from show_tracker.api.routes_export import router as export_router  # noqa: E402
from show_tracker.api.routes_webhooks import router as webhooks_router  # noqa: E402
from show_tracker.api.routes_stats import router as stats_router  # noqa: E402
from show_tracker.api.routes_youtube import router as youtube_router  # noqa: E402

app.include_router(media_router)
app.include_router(history_router)
app.include_router(unresolved_router)
app.include_router(settings_router)
app.include_router(export_router)
app.include_router(webhooks_router)
app.include_router(stats_router)
app.include_router(youtube_router)


# ---------------------------------------------------------------------------
# Serve the web UI as static files
# ---------------------------------------------------------------------------

_WEB_UI_DIR = Path(__file__).resolve().parent.parent.parent.parent / "web_ui"
_TEMPLATES_DIR = _WEB_UI_DIR / "templates"
_STATIC_DIR = _WEB_UI_DIR / "static"

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ---------------------------------------------------------------------------
# Top-level routes
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


@app.get("/", include_in_schema=False)
async def serve_ui() -> FileResponse:
    """Serve the single-page application shell."""
    index = _TEMPLATES_DIR / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return FileResponse(str(_TEMPLATES_DIR / "index.html"))
