"""FastAPI application for AutoShowTracker.

Creates the ASGI app, registers CORS middleware, includes all routers,
and manages database lifecycle via startup/shutdown events.
"""

from __future__ import annotations

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
    """Initialise databases on startup, close connections on shutdown."""
    _settings.ensure_directories()
    _db.init_databases()
    app.state.db = _db
    app.state.settings = _settings
    yield
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

app.include_router(media_router)
app.include_router(history_router)
app.include_router(unresolved_router)
app.include_router(settings_router)


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
