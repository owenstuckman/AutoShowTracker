# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

AutoShowTracker is an automatic TV show/episode tracker that detects what the user is watching across browsers, desktop media players, streaming services, and pirate sites. It identifies the specific episode using fuzzy matching against TMDb/TVDb and logs a unified watch history.

## Build and Development Commands

```bash
# Install in dev mode
pip install -e ".[dev,ocr,windows]"   # Windows
pip install -e ".[dev,ocr,linux]"     # Linux

# Run all tests
pytest

# Run unit tests only
pytest tests/unit/ -v

# Run a single test file
pytest tests/unit/test_parser.py -v

# Run a single test
pytest tests/unit/test_parser.py::TestParseFilenames::test_standard_sxxexx -v

# Lint
ruff check src/ tests/
ruff format --check src/ tests/

# Type check
mypy src/show_tracker/

# Initialize databases
show-tracker init-db

# Start all services
show-tracker run

# Identify a single media string (Phase 0 validation)
show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"
```

## Architecture (Five Layers)

1. **Collection Layer** (`src/show_tracker/detection/`): ActivityWatch polling, SMTC/MPRIS listeners (event-driven), browser extension events, OCR fallback — all fed into `DetectionService` which deduplicates and routes by confidence tier
2. **Parsing Layer** (`src/show_tracker/identification/parser.py`): `guessit` + regex preprocessing + URL pattern engine — extracts show name, season, episode from raw strings
3. **Identification Layer** (`src/show_tracker/identification/resolver.py`): TMDb API fuzzy matching via rapidfuzz (0.80 threshold), alias table lookup, aggressive caching, confidence scoring
4. **Storage Layer** (`src/show_tracker/storage/`): Two SQLite databases — `watch_history.db` (user data, non-rebuildable) and `media_cache.db` (TMDb cache, rebuildable). Synchronous SQLAlchemy ORM
5. **Presentation Layer** (`src/show_tracker/api/` + `web_ui/`): FastAPI HTTP API + vanilla JS SPA (no build step)

## Key Design Constraints

- **Python is the primary language** — guessit, TMDb client, OCR, SMTC/MPRIS listeners are all Python-native. Browser extension is JavaScript.
- **No audio fingerprinting** — detection is purely text-based (titles, URLs, metadata, OCR).
- **ActivityWatch is bundled as unmodified subprocess** (not forked, not a custom watcher). Keeps MPL 2.0 license boundary clean.
- **SMTC/MPRIS is primary desktop detection** — handles background playback and auto-advancing episodes that ActivityWatch's focus-based model misses.
- **OCR is last resort** — only triggered when SMTC/MPRIS + window title both fail. Uses per-app region cropping (`profiles/default_profiles.json`), not full-window.
- **Confidence routing**: >= 0.9 auto-logged, 0.7-0.9 logged+flagged, < 0.7 queued for manual resolution.
- **Dual databases**: `watch_history.db` is user data (preserve). `media_cache.db` is rebuildable (safe to delete).

## Configuration

Settings load from: env vars (prefix `ST_`) > `.env` file > `config/default_settings.json`. API keys use exact names: `TMDB_API_KEY`, `YOUTUBE_API_KEY`.

## Document Index

Design docs 00-09 in repo root. Key references:
- Detection priority chain (six levels): `03_MEDIA_DETECTION.md`
- Identification pipeline (guessit + TMDb fuzzy matching + confidence scoring): `04_CONTENT_IDENTIFICATION.md`
- Full SQLite schema: `07_DATA_MODEL.md`
- Implementation decisions: `docs/ARCHITECTURE_DECISIONS.md`
- Setup guide: `docs/SETUP_AND_USAGE.md`

## Key Dependencies

| Dependency | Purpose | License |
|------------|---------|---------|
| guessit | Parse messy media filenames/titles | LGPL 3.0 |
| rapidfuzz | Fuzzy string matching for TMDb resolution | MIT |
| FastAPI + uvicorn | HTTP API and web UI server | MIT/BSD |
| SQLAlchemy | ORM for dual SQLite databases | MIT |
| httpx | TMDb API HTTP client | BSD |
| pydantic-settings | Configuration management | MIT |
| click | CLI framework | BSD |
| Pillow | Image processing for OCR pipeline | MIT-like |
| winsdk | Windows SMTC access via WinRT | MIT |
| dbus-next | Linux MPRIS via D-Bus | MIT |
