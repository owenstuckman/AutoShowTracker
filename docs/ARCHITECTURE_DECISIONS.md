# Architecture Decisions and Implementation Notes

This document records the technical decisions made during implementation and explains the reasoning behind key architectural choices.

## Project Structure

```
AutoShowTracker/
├── src/show_tracker/           # Main Python package
│   ├── identification/         # Phase 0 core: parsing + TMDb resolution
│   │   ├── parser.py           # guessit integration + preprocessing
│   │   ├── url_patterns.py     # URL pattern matching for known platforms
│   │   ├── tmdb_client.py      # TMDb API client (httpx-based)
│   │   ├── resolver.py         # Main resolution engine
│   │   └── confidence.py       # Confidence scoring logic
│   ├── detection/              # Collection layer: AW + SMTC/MPRIS + browser
│   │   ├── activitywatch.py    # AW process manager, REST client, event poller
│   │   ├── media_session.py    # Cross-platform media session abstraction
│   │   ├── smtc_listener.py    # Windows SMTC via WinRT
│   │   ├── mpris_listener.py   # Linux MPRIS via D-Bus
│   │   ├── browser_handler.py  # Browser extension event processor
│   │   └── detection_service.py # Central orchestrator / detection loop
│   ├── storage/                # Data layer: SQLAlchemy models + repositories
│   │   ├── models.py           # ORM models for both databases
│   │   ├── database.py         # DatabaseManager (dual-DB lifecycle)
│   │   └── repository.py       # WatchRepository + CacheRepository
│   ├── api/                    # FastAPI HTTP API
│   │   ├── app.py              # ASGI app, lifespan, static files
│   │   ├── schemas.py          # Pydantic request/response models
│   │   ├── routes_media.py     # Browser extension event endpoint
│   │   ├── routes_history.py   # Watch history queries + stats
│   │   ├── routes_unresolved.py # Manual resolution workflow
│   │   └── routes_settings.py  # Settings + alias management
│   ├── ocr/                    # OCR fallback subsystem
│   │   ├── screenshot.py       # Background-safe window capture
│   │   ├── region_crop.py      # Per-app region cropping
│   │   ├── engine.py           # Tesseract/EasyOCR abstraction
│   │   └── ocr_service.py      # Orchestrator
│   ├── players/                # Direct player IPC
│   │   ├── vlc.py              # VLC HTTP interface client
│   │   ├── mpv.py              # mpv JSON IPC client
│   │   ├── file_inspector.py   # Open file handle inspection
│   │   └── player_service.py   # Orchestrator
│   ├── utils/                  # Shared utilities
│   │   ├── logging.py          # Logging configuration
│   │   └── aliases.py          # 50+ initial show alias seed data
│   ├── config.py               # Pydantic-settings configuration
│   └── main.py                 # Click CLI entry point
├── browser_extension/chrome/   # Chrome Manifest V3 extension
├── web_ui/                     # Frontend (vanilla JS SPA)
├── tests/                      # pytest test suite
├── config/                     # Default settings JSON
├── profiles/                   # OCR app region profiles
└── docs/                       # This documentation
```

## Decision: Synchronous SQLAlchemy (not async)

**Choice**: Used synchronous SQLAlchemy with context-managed sessions rather than async SQLAlchemy + aiosqlite.

**Why**: SQLite is local file I/O — it doesn't benefit from async the way network databases do. The synchronous API is simpler, more debuggable, and avoids the complexity of async session management. FastAPI handles the sync sessions fine since SQLite operations are fast. The `aiosqlite` dependency is kept in `pyproject.toml` as a future option.

## Decision: Dual SQLite Databases

**Choice**: Separate `watch_history.db` (user data) and `media_cache.db` (TMDb cache).

**Why**: The cache database is rebuildable — if it gets corrupted or stale, the user can delete it without losing their watch history. This separation also makes backups simpler: only `watch_history.db` needs to be preserved.

## Decision: Click CLI + FastAPI Server

**Choice**: Click for CLI commands, FastAPI for the HTTP API, uvicorn for serving.

**Why**: Click provides a clean CLI experience with subcommands (`run`, `identify`, `init-db`, `test-pipeline`). FastAPI provides automatic OpenAPI docs, Pydantic validation, and async support for the HTTP API. The `run` command starts uvicorn which serves both the API and web UI.

## Decision: Vanilla JS Frontend (No Build Step)

**Choice**: Plain JavaScript SPA with hash-based routing instead of React/Svelte.

**Why**: The web UI is simple (5 views: dashboard, shows, show detail, unresolved, settings). A framework would add a build step, node dependency, and complexity that isn't justified. The vanilla JS approach means the frontend ships as static files with zero build tooling.

## Decision: Protocol-Based Dependency Injection in Resolver

**Choice**: `AliasStore` and `CacheStore` are Python `Protocol` classes, not abstract base classes.

**Why**: Structural subtyping means any object with the right methods works — no inheritance required. This makes testing trivial (just pass an object with the right methods) and avoids coupling the resolver to specific storage implementations.

## Decision: Browser Extension as Separate Component

**Choice**: The Chrome extension is a standalone Manifest V3 extension that posts to the local HTTP API, not integrated into ActivityWatch's extension.

**Why**: ActivityWatch's web extension only provides tab URL + title. Our extension needs deep metadata scraping (schema.org, Open Graph, video element state, heartbeats). Keeping it separate means we can evolve independently and support richer metadata extraction.

## Decision: Confidence-Tiered Processing

**Choice**: Three confidence tiers determine how detections are routed:
- `>= 0.9`: Auto-logged without confirmation
- `0.7 - 0.9`: Logged but flagged for review
- `< 0.7`: Queued as unresolved for manual resolution

**Why**: This balances automation with accuracy. High-confidence detections (clean filenames, URL pattern matches) are logged silently. Uncertain detections surface in the UI for user correction, which also trains the alias table for future accuracy.

## Decision: Event-Driven SMTC/MPRIS + Polling AW

**Choice**: SMTC/MPRIS listeners are event-driven (callbacks on media changes). ActivityWatch data is polled every 10 seconds.

**Why**: OS media session APIs naturally push events on track changes — polling them would waste resources. ActivityWatch's REST API doesn't support push notifications, so polling is the only option. The 10-second interval balances responsiveness with resource usage.

## Decision: OCR as Last Resort with Per-App Profiles

**Choice**: OCR is only triggered when SMTC/MPRIS and window title both fail. Uses JSON-defined bounding boxes per app, not full-window OCR.

**Why**: Full-window OCR produces too much noise (subtitles, UI chrome, ads). Region cropping to known title bar / transport control areas yields clean text. The JSON profiles are simple to maintain and scale with window resizing (percentages, not pixels).

## Decision: rapidfuzz Over difflib

**Choice**: Used `rapidfuzz` for fuzzy string matching instead of Python's built-in `difflib.SequenceMatcher`.

**Why**: rapidfuzz is 10-100x faster for Levenshtein-based fuzzy matching and provides the same ratio API. Since the resolver may compare against multiple TMDb search results per detection, speed matters.

## Decision: httpx for TMDb Client

**Choice**: Used `httpx` (sync mode) for TMDb API calls instead of `requests`.

**Why**: httpx provides the same API as requests but also supports async mode, connection pooling, and HTTP/2. The TMDb client uses sync calls wrapped in a class that can be easily extended to async later.

## Phase Coverage

| Phase | Status | Components |
|-------|--------|------------|
| Phase 0 | Complete | Identification pipeline, parser, TMDb client, confidence scoring, test dataset |
| Phase 1 | Complete | ActivityWatch integration, SMTC/MPRIS listeners, browser extension, web UI, CLI, FastAPI API |
| Phase 2 | Complete | VLC/mpv IPC, OCR subsystem (screenshot, region crop, engine), file handle inspection |
| Phase 3 | Partial | MPRIS listener implemented; macOS MediaRemote listener is stubbed (needs pyobjc) |
| Phase 4 | Partial | Statistics endpoint implemented; sync/export, notifications, Android not yet implemented |
