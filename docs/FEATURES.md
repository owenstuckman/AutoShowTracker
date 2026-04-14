# Completed Features

Everything listed here is implemented and working in the codebase.

---

## Phase 0 — Identification Pipeline

- guessit-based filename/title parsing with regex preprocessing
- TMDb v3 API client with fuzzy matching (rapidfuzz, 0.80 threshold)
- Confidence scoring system (base score per source + bonuses/penalties, clamped to 0.0–1.0)
- Show alias table (~50 pre-seeded abbreviations)
- TMDb response caching (SQLite, `media_cache.db`)
- `show-tracker identify` CLI command for single-string validation

## Phase 1 — Windows Desktop MVP

### 1A: Detection Layer (`src/show_tracker/detection/`)
- **ActivityWatch integration** — bundled as unmodified subprocess, REST API polling on localhost:5600, incremental timestamp tracking per bucket
- **SMTC listener** (`smtc_listener.py`) — Windows System Media Transport Controls via `winsdk`, event-driven playback status mapping
- **MPRIS listener** (`mpris_listener.py`) — Linux Media Player Remote Interfacing via `dbus-next`, PropertiesChanged signal handling
- **DetectionService** (`detection_service.py`) — central orchestrator merging ActivityWatch, SMTC/MPRIS, and browser events; deduplication with 120s grace period; confidence-tier routing (AUTO_LOG >= 0.9, LOG_AND_FLAG >= 0.7, UNRESOLVED < 0.7); callback registration for downstream persistence
- **Browser extension event handler** (`browser_handler.py`) — metadata extraction priority chain: schema.org > Open Graph > URL patterns > page title; supports Netflix, YouTube, Crunchyroll, Disney+, Hulu, Amazon Prime, HBO Max
- **Media session abstraction** (`media_session.py`) — `PlaybackStatus` enum, `MediaSessionEvent` dataclass, `MediaSessionListener` protocol, `get_media_listener()` factory with platform detection

### 1B: Browser Extension
- **Chrome extension** (`browser_extension/chrome/`) — Manifest V3, content script metadata extraction, service worker forwarding to `localhost:7600/api/media-event`, popup with status/toggle
- **Firefox extension** (`browser_extension/firefox/`) — Manifest V2 port, full feature parity with Chrome

### 1C: Web UI (`web_ui/`)
- Vanilla JS single-page application (no build step, no framework)
- Hash-based SPA routing (`#dashboard`, `#shows`, `#show/{id}`, `#youtube`, `#movies`, `#stats`, `#unresolved`, `#settings`)
- **Dashboard** — recently watched episodes, shows in progress, quick stats (episodes, shows, watch time, YouTube videos), recent YouTube card
- **Shows page** — all tracked shows with poster, progress, last watched
- **Show detail** — season/episode grid with watch status
- **YouTube page** — video list with channel info, stats (total watches, unique videos, watch time, top channels)
- **Movies page** — movie watch list with stats cards (total watches, unique movies, watch time) using dedicated `/api/movies/*` endpoints
- **Stats page** — daily/weekly/monthly charts, binge sessions, viewing patterns
- **Unresolved queue** — low-confidence detections with search/assign/dismiss flow
- **Settings page** — threshold editing, API key configuration, notification toggle, Trakt.tv connection management
- Responsive CSS with mobile breakpoints at 768px and 480px
- **Attribution footer** — sidebar footer credits TMDb and YouTube per their API attribution requirements

### 1C: API Layer (`src/show_tracker/api/`)

**System:**
- `GET /api/health` — status and version
- `GET /` — serves web UI
- `GET /docs` — Swagger UI
- `GET /redoc` — ReDoc

**Media Events:**
- `POST /api/media-event` — receives browser extension events (play/pause/ended/heartbeat/page_load)
- `GET /api/currently-watching` — current detection state

**Watch History:**
- `GET /api/history/recent` — recent episodes with `limit` parameter
- `GET /api/history/shows` — all tracked shows with progress summaries
- `GET /api/history/shows/{show_id}` — show detail with season/episode grid
- `GET /api/history/shows/{show_id}/progress` — episode-level progress tracking
- `GET /api/history/next-to-watch` — next unwatched episode per show
- `GET /api/history/stats` — total watch time, episodes, breakdown by show/week

**Unresolved Events:**
- `GET /api/unresolved` — list low-confidence detections
- `POST /api/unresolved/{event_id}/resolve` — manual assignment to show/episode
- `POST /api/unresolved/{event_id}/dismiss` — discard without resolution
- `POST /api/unresolved/{event_id}/search` — TMDb search for assignment candidates

**Settings & Aliases:**
- `GET /api/settings` / `PUT /api/settings/{key}` — settings CRUD
- `POST /api/aliases` / `GET /api/aliases/{show_id}` / `DELETE /api/aliases/{alias_id}` — alias CRUD

**Export:**
- `GET /api/export/history.json` — JSON export of all watch events
- `GET /api/export/history.csv` — CSV export with headers
- `GET /api/export/shows.json` / `GET /api/export/shows.csv` — show export

**YouTube:**
- `GET /api/youtube/recent` — recent YouTube watches with `limit`
- `GET /api/youtube/stats` — total watches, unique videos, watch seconds, top channels

**Webhooks:**
- `POST /api/webhooks/plex` — Plex media server events (multipart form)
- `POST /api/webhooks/jellyfin` — Jellyfin events (JSON)
- `POST /api/webhooks/emby` — Emby events (JSON)

**Analytics:**
- `GET /api/stats/daily` — per-day stats with `days` parameter
- `GET /api/stats/weekly` — per-week stats with `weeks` parameter
- `GET /api/stats/monthly` — per-month stats with `months` parameter
- `GET /api/stats/binge-sessions` — binge detection (3+ episodes same show, same day)
- `GET /api/stats/patterns` — viewing patterns (hour/weekday distribution, avg session, most active time)

**Movies:**
- `GET /api/movies/recent` — recent movie watches with `limit` parameter
- `GET /api/movies/stats` — total watches, unique movies, total watch seconds
- `GET /api/movies/{movie_id}` — single movie detail by ID

**Trakt Sync:**
- `POST /api/sync/trakt/auth` — start Trakt OAuth2 device flow
- `GET /api/sync/trakt/status` — check connection status
- `POST /api/sync/trakt/sync` — trigger manual import from Trakt
- `DELETE /api/sync/trakt/disconnect` — remove stored token

### 1C: Storage Layer (`src/show_tracker/storage/`)
- **Dual SQLite databases** — `watch_history.db` (user data, non-rebuildable) and `media_cache.db` (TMDb/TVDb cache, rebuildable)
- **SQLAlchemy ORM models** — `Show`, `Episode`, `WatchEvent`, `YouTubeWatch`, `MovieWatch`, `ShowAlias`, `UnresolvedEvent`, `UserSetting`, `TMDbShowCache`, `TMDbSearchCache`
- **WatchRepository** — CRUD operations, `upsert_show()`, `upsert_episode()`, `process_heartbeat()`, `create_youtube_watch()`
- **DatabaseManager** — session management with auto-commit context manager
- **TMDb cache TTL** — `TMDB_MAX_CACHE_HOURS = 24*30*6` (6 months) enforced per TMDb ToS; `get_cached_show()` and `get_cached_episode()` default to this maximum

### 1C: CLI (`src/show_tracker/main.py`)
- Click-based CLI with commands: `run`, `identify`, `test-pipeline`, `init-db`, `setup`
- `show-tracker identify` — single string identification with `--source` flag
- `show-tracker run` — starts FastAPI server with all detection services
- `show-tracker init-db` — database initialization with `--force` flag
- `show-tracker setup` — interactive first-run wizard

### 1C: Configuration (`src/show_tracker/config.py`)
- pydantic-settings with env var priority: `ST_*` prefix env vars > `.env` file > `config/default_settings.json` > Pydantic defaults
- Exact names for API keys: `TMDB_API_KEY`, `YOUTUBE_API_KEY`, `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET`
- All configurable: `ST_DATA_DIR`, `ST_MEDIA_SERVICE_PORT`, `ST_ACTIVITYWATCH_PORT`, `ST_AUTO_LOG_THRESHOLD`, `ST_REVIEW_THRESHOLD`, `ST_OCR_ENABLED`, `ST_HEARTBEAT_INTERVAL`, `ST_GRACE_PERIOD`, `ST_POLLING_INTERVAL`

### 1D: Packaging
- **PyInstaller** (`show_tracker.spec`) — Windows binary with bundled web_ui, config, profiles, guessit, hidden imports
- **System tray** (`tray.py`) — pystray-based icon with "Open Dashboard" and "Quit" menu
- **First-run wizard** (`first_run.py`) — interactive CLI for TMDb key validation, `.env` writing, database init

## Phase 2 — Robust Detection

### 2A: Player IPC (`src/show_tracker/players/`)
- **VLC client** (`vlc.py`) — HTTP web interface XML parsing, `PlayerStatus` dataclass
- **mpv client** (`mpv.py`) — JSON IPC protocol, Unix socket + Windows named pipe support
- **Player service** (`player_service.py`) — unified interface, player identification by app name
- **File inspector** (`file_inspector.py`) — `/proc/<pid>/fd/` inspection for open media files

### 2B–2C: OCR Pipeline (`src/show_tracker/ocr/`)
- **OCR service** (`ocr_service.py`) — orchestrator combining screenshot + region cropping + engine
- **Engine** (`engine.py`) — Tesseract primary + EasyOCR fallback, lazy loading, graceful degradation
- **Screenshot** (`screenshot.py`) — platform-specific capture (Windows PrintWindow, Linux X11, macOS stub)
- **Region cropping** (`region_crop.py`) — per-app bounding box profiles from `profiles/default_profiles.json`, percentage-based coordinates
- Full-window fallback with spatial filtering (top/bottom 15%), font size filtering, candidate scoring

### 2D: Improved Identification (`src/show_tracker/identification/`)
- **TVDb client** (`tvdb_client.py`) — TVDb v4 API with OAuth2 device flow, search, episode lookup, anime/absolute numbering fallback
- **YouTube client** (`youtube_client.py`) — YouTube Data API v3, video metadata, playlist info, series detection; class-level `_quota_used` counter with warnings at 80% and errors at 100% of 10,000 unit/day free tier
- **Movie identification** — `MovieIdentificationResult` dataclass, `resolve_movie()` in resolver, `MovieWatch` ORM model
- **URL patterns** (`url_patterns.py`) — platform-specific extractors for Netflix, Disney+, Prime, HBO Max, Crunchyroll, Hulu, YouTube

## Phase 3 — Cross-Platform

- **Linux MPRIS listener** — `dbus-next` D-Bus interface, fully implemented
- **Linux AppImage** — build script (`scripts/build_appimage.sh`)
- **Linux OCR** — X11 window capture only; Wayland not yet supported (see TODO.md)
- **macOS MediaRemote** (`macos_listener.py`) — polls `MPNowPlayingInfoCenter.defaultCenter()` every 2 s; emits `MediaSessionEvent` on title/playback state change; wired into `get_media_listener()` factory; `pyobjc-framework-MediaPlayer>=9.0` in `[macos]` optional dep group. **Untested on real hardware** — see HUMAN_TODO.md 2h.
- **macOS screenshot** — `_capture_macos()` in `ocr/screenshot.py`: Quartz `CGWindowListCreateImage` primary, `screencapture` CLI fallback
- **macOS packaging** — DMG/pkg installer not yet implemented (no build script)

## Phase 4 — Advanced Features

### 4A: Analytics
- Stats endpoints (daily, weekly, monthly, binge-sessions, patterns) — all implemented in `routes_stats.py`
- Web UI stats page with chart rendering

### 4B: Sync and Export
- **Export** — JSON and CSV export for history and shows (`routes_export.py`)
- **Simkl import** (`sync/simkl.py`) — OAuth2 PIN device flow, `get_all_items()`, `import_history()` mapping Simkl episodes/movies to local WatchRepository records
- **Trakt sync module** (`sync/trakt.py`) — OAuth2 device flow, watch history import, scrobble export
- **Trakt API routes** (`routes_sync.py`) — auth, status, sync, disconnect endpoints
- **Trakt web UI** — Settings page Trakt section with connect/import/disconnect flow
- **Trakt auto-scrobble** — `trakt_scrobble_enabled` setting (default false); when enabled, calls `scrobble_stop()` on every finalized watch via `DetectionService.register_finalize_callback()`

### 4C: Notifications
- `notifications.py` — `check_new_episodes()` and `notify_new_episodes()` via plyer
- Hourly background task in FastAPI lifespan calls `notify_new_episodes()` when TMDb key is configured
- Clean cancellation on server shutdown
- `notifications_enabled` user setting — checked by background task, configurable via Settings page
- **"Continue watching" prompt** — dashboard "Next Up" card populated from `/api/history/next-to-watch` on every app open

### 4E: Webhooks
- Plex (multipart form), Jellyfin (JSON), Emby (JSON) — all implemented in `routes_webhooks.py`
- Movie metadata extraction from webhooks

## Infrastructure

- **GitHub Actions CI** (`.github/workflows/ci.yml`) — Ubuntu + Windows matrix, Python 3.11/3.12, ruff + mypy + pytest
- **Release workflow** (`.github/workflows/release.yml`) — triggered on version tags, builds PyPI package + PyInstaller + AppImage + browser extensions
- **Alembic initial migration** (`alembic/versions/001_initial_schema.py`) — all 8 watch_history.db tables, tested on fresh and existing DBs, documented in SETUP.md
- **systemd service** (`contrib/show-tracker.service`)
- **Privacy policy** (`PRIVACY_POLICY.md`)
- **Third-party licenses** (`THIRD_PARTY_LICENSES.txt`)
- **Extension packager** (`scripts/package_extensions.sh`)
- **Version bump script** (`scripts/bump_version.sh`)
- **OCR benchmark** (`scripts/ocr_benchmark.py`)
- **API load test** (`scripts/load_test.py`)
- **Auto-setup script** (`scripts/auto_setup.py`)
- **Windows installer** (`scripts/inno_setup.iss`) — Inno Setup script with Start Menu shortcuts, optional desktop/startup entries, database init, user data preservation on uninstall

## Design Decisions (D001–D013)

All documented in `docs/DECISIONS.md`:
- D001: SQLAlchemy 2.0 over raw sqlite3
- D002: FastAPI over Flask
- D003: httpx over requests
- D004: rapidfuzz over python-Levenshtein
- D005: Vanilla JavaScript (no React/Svelte)
- D006: Hash-based SPA routing
- D007: pydantic-settings for configuration
- D008: click for CLI
- D009: Protocol classes for cross-platform abstraction
- D010: Conditional imports for platform packages
- D011: OCR engines use lazy loading
- D012: Detection service uses asyncio
- D013: Browser extension sends HTTP events (not WebSocket)

## Code Quality

### Mypy Type Checking — Clean (0 errors across 52 source files)
- Full type annotations across all modules
- Platform-conditional imports properly annotated with `type: ignore[import-not-found]`
- Untyped third-party libraries suppressed with `type: ignore[import-untyped]`
- Generic type parameters (`dict[str, Any]`, `list[int]`, etc.) on all public API signatures

### Pytest — 648 tests passing (unit)
- **Parser** (`test_parser.py`) — filename parsing, date-based episodes, absolute numbering, URL patterns, platform suffix stripping, noise word removal
- **URL patterns** (`test_url_patterns.py`) — Netflix, YouTube, Crunchyroll, Plex, Disney+, Hulu, Amazon Prime, HBO Max
- **Resolver** (`test_resolver.py`) — TMDb fuzzy matching (0.80 threshold), alias table lookup, cache TTL, IdentificationResult/MovieIdentificationResult dataclasses
- **Confidence scoring** (`test_confidence.py`) — base scores per source, URL/season+ep/fuzzy bonuses, OCR/no-season/abbreviated-title penalties, 1.0 cap
- **Detection service** (`test_detection_service.py`) — deduplication, confidence routing, callbacks, heartbeat emission, AW event conversion, lifecycle
- **Detection sources** (`test_detection_sources.py`) — SMTC/MPRIS callbacks, EventPoller, bucket discovery, browser events, ActiveWatch
- **Platform listeners** (`test_platform_listeners.py`) — SMTCListener async (session attachment, event emission, start/stop, winsdk mocked), MPRISListener async (D-Bus connection, player discovery, signal dispatch, dbus-next mocked), ActivityWatchManager subprocess (launch, shutdown, health check, crash retry with backoff), MacOSMediaListener (poll loop, state change detection, stopped-on-clear, pyobjc mocked)
- **Simkl client** (`test_simkl.py`) — token load/save, device auth PIN flow, `get_all_items`, `import_history` episode mapping
- **Storage** (`test_storage.py`) — dual DB isolation, WatchRepository CRUD, unresolved lifecycle, completion at ≥90%, cache TTL (6-month max per TMDb ToS), FailedLookup TTL (24h)
- **API endpoints** (`test_api.py`) — all routes: health, media-event, currently-watching, history, unresolved, settings, aliases, export, stats, webhooks, movies
- **OCR pipeline** (`test_ocr.py`) — region cropping, profile loading, engine selection, preprocessing (grayscale, threshold, upscale, invert)
- **Player IPC** (`test_players.py`) — VLC HTTP XML parsing, mpv JSON IPC socket/pipe
- **CLI** (`test_cli.py`) — identify, test-pipeline, init-db, setup wizard
- **Configuration** (`test_config.py`) — defaults, env var overrides, priority order, path derivation, ensure_directories()
- **Sync & notifications** (`test_sync.py`) — Trakt router structure, send_notification(), check_new_episodes() with mocked DB and TMDb
