# AutoShowTracker — Setup and Usage Guide

## Prerequisites

- **Python 3.11+** (required by `pyproject.toml`)
- **TMDb API Key** — free at https://www.themoviedb.org/settings/api (required for content identification)
- **ActivityWatch** (optional for Phase 1+) — downloaded from https://activitywatch.net/

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/owenstuckman/AutoShowTracker.git
cd AutoShowTracker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install in development mode with all optional dependencies
pip install -e ".[dev,ocr,windows]"  # Windows
pip install -e ".[dev,ocr,linux]"    # Linux
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your TMDB_API_KEY
```

### 3. Initialize databases

```bash
show-tracker init-db
```

This creates `~/.show-tracker/watch_history.db` and `~/.show-tracker/media_cache.db`.

### 4. Test the identification pipeline (Phase 0)

```bash
# Identify a single title
show-tracker identify "law.and.order.svu.s03e07.720p.bluray.mkv"

# Identify from a browser title
show-tracker identify "Breaking Bad Season 2 Episode 3 - Watch Free" --source browser_title

# Run the full test dataset
show-tracker test-pipeline --verbose
```

### 5. Start all services

```bash
show-tracker run
```

This launches:
- FastAPI HTTP API on `http://127.0.0.1:7600`
- Web UI at `http://127.0.0.1:7600/`
- Media event endpoint at `POST http://127.0.0.1:7600/api/media-event`
- ActivityWatch polling (if AW is running on port 5600)
- SMTC/MPRIS media session listener (platform-dependent)

### 6. Install the browser extension (Chrome)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable "Developer mode" (top right toggle)
3. Click "Load unpacked"
4. Select the `browser_extension/chrome/` directory from this repo
5. The extension will begin sending playback events to the local service

## CLI Commands

| Command | Description |
|---------|-------------|
| `show-tracker run` | Start all services (API, detection, web UI) |
| `show-tracker identify <string>` | Identify a single media string |
| `show-tracker test-pipeline` | Run accuracy tests on identification pipeline |
| `show-tracker init-db` | Initialize/create database files |
| `show-tracker --version` | Show version |
| `show-tracker --help` | Show help |

### Options for `run`

```
--host TEXT     Bind address (default: 127.0.0.1)
--port INT      API port override (default: from config, 7600)
--data-dir PATH Override data directory
```

## API Endpoints

### Media Events (Browser Extension)
- `POST /api/media-event` — Receive playback events
- `GET /api/currently-watching` — Current detection state

### Watch History
- `GET /api/history/recent?limit=50` — Recently watched episodes
- `GET /api/history/shows` — All tracked shows with progress
- `GET /api/history/shows/{id}` — Show detail with season/episode grid
- `GET /api/history/shows/{id}/progress` — Episode-level progress
- `GET /api/history/next-to-watch` — Next unwatched episode per show
- `GET /api/history/stats` — Watch time statistics

### Unresolved Events
- `GET /api/unresolved` — Pending unresolved events
- `POST /api/unresolved/{id}/resolve` — Manually assign to episode
- `POST /api/unresolved/{id}/dismiss` — Dismiss without tracking
- `POST /api/unresolved/{id}/search` — Search TMDb for candidates

### Settings & Aliases
- `GET /api/settings` — All user settings
- `PUT /api/settings/{key}` — Update a setting
- `POST /api/aliases` — Add a show alias
- `GET /api/aliases/{show_id}` — Get aliases for a show
- `DELETE /api/aliases/{id}` — Remove an alias

### System
- `GET /api/health` — Health check
- `GET /` — Web UI

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/ -v

# Integration tests (parser accuracy across 100+ inputs)
pytest tests/integration/ -v

# With coverage
pytest --cov=show_tracker --cov-report=term-missing

# Single test file
pytest tests/unit/test_parser.py -v

# Single test
pytest tests/unit/test_parser.py::TestParseFilenames::test_standard_sxxexx -v
```

## Configuration

Settings are resolved in priority order:
1. Environment variables (prefixed with `ST_` or exact name for API keys)
2. `.env` file in project root
3. `config/default_settings.json`

### Key Settings

| Setting | Env Var | Default | Description |
|---------|---------|---------|-------------|
| TMDb API Key | `TMDB_API_KEY` | (none) | Required for identification |
| YouTube API Key | `YOUTUBE_API_KEY` | (none) | Optional, for YouTube series |
| Data Directory | `ST_DATA_DIR` | `~/.show-tracker` | Where databases and logs live |
| AW Port | `ST_ACTIVITYWATCH_PORT` | `5600` | ActivityWatch server port |
| API Port | `ST_MEDIA_SERVICE_PORT` | `7600` | Show Tracker HTTP API port |
| Auto-log Threshold | `ST_AUTO_LOG_THRESHOLD` | `0.9` | Auto-log confidence cutoff |
| Review Threshold | `ST_REVIEW_THRESHOLD` | `0.7` | Unresolved queue cutoff |
| OCR Enabled | `ST_OCR_ENABLED` | `true` | Enable OCR fallback |
| Heartbeat Interval | `ST_HEARTBEAT_INTERVAL` | `30` | Seconds between heartbeats |
| Grace Period | `ST_GRACE_PERIOD` | `120` | Seconds before finalizing watch |
| Polling Interval | `ST_POLLING_INTERVAL` | `10` | AW polling interval |

## Data Storage

All data is stored locally in `~/.show-tracker/`:

```
~/.show-tracker/
├── watch_history.db    # User's watch log, shows, episodes, settings
├── media_cache.db      # Cached TMDb data (safe to delete, will rebuild)
└── logs/
    └── show_tracker.log
```

### Database Schema

**watch_history.db** contains:
- `shows` — tracked TV shows with TMDb metadata
- `episodes` — individual episodes linked to shows
- `watch_events` — timestamped watch records with duration/completion
- `youtube_watches` — YouTube-specific watch records
- `show_aliases` — name mappings for abbreviations and alternate titles
- `unresolved_events` — low-confidence detections awaiting manual review
- `user_settings` — key-value settings store

**media_cache.db** contains:
- `tmdb_show_cache` — cached TMDb show data
- `tmdb_search_cache` — cached search query results
- `tmdb_episode_cache` — cached episode details
- `failed_lookups` — tracks failed queries to avoid API hammering
