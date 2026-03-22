# AutoShowTracker

Automatic TV show and episode tracker that detects what you're watching across browsers, desktop media players, streaming services, and pirate sites. Identifies the specific episode using fuzzy matching against TMDb and logs a unified watch history — all running locally.

## How It Works

1. **Detects** what you're watching via browser extension, OS media session APIs (SMTC/MPRIS), player IPC (VLC/mpv), ActivityWatch window titles, or OCR fallback
2. **Identifies** the show and episode by parsing filenames/titles with guessit, matching URLs to streaming platforms, and fuzzy-searching TMDb
3. **Logs** watch events to a local SQLite database with confidence-based routing (auto-log, flag for review, or queue for manual resolution)
4. **Displays** your watch history, show progress, and statistics through a local web dashboard

## Quick Start

```bash
# Clone and install
git clone https://github.com/owenstuckman/AutoShowTracker.git
cd AutoShowTracker
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install with platform-specific extras
pip install -e ".[dev,ocr,windows]"  # Windows
pip install -e ".[dev,ocr,linux]"    # Linux
pip install -e ".[dev]"              # WSL (or use: python scripts/auto_setup.py)

# Configure
cp .env.example .env
# Edit .env and add your TMDB_API_KEY (free at https://www.themoviedb.org/settings/api)

# Initialize databases and start
show-tracker init-db
show-tracker run
# Open http://127.0.0.1:7600 in your browser
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `show-tracker run` | Start all services (API, detection, web UI) |
| `show-tracker setup` | Interactive first-run wizard (TMDb key, DB init) |
| `show-tracker identify <string>` | Identify a single media string |
| `show-tracker test-pipeline` | Run accuracy tests on the identification pipeline |
| `show-tracker init-db` | Initialize/create database files |

## Architecture

Five-layer system: Collection → Parsing → Identification → Storage → Presentation

- **Collection**: ActivityWatch polling, SMTC/MPRIS listeners, browser extension events, VLC/mpv IPC, OCR fallback
- **Parsing**: guessit + regex preprocessing + URL pattern matching for 9 streaming platforms
- **Identification**: TMDb API search with rapidfuzz fuzzy matching (0.80 threshold), alias table, caching
- **Storage**: Dual SQLite databases — `watch_history.db` (user data) + `media_cache.db` (rebuildable cache)
- **Presentation**: FastAPI HTTP API + vanilla JS single-page web dashboard

## Browser Extension

Load the Chrome extension from `browser_extension/chrome/` as an unpacked extension. It extracts structured metadata (JSON-LD, Open Graph, URL patterns, video element state) from streaming sites and sends events to the local API.

## Configuration

Settings load from: environment variables (`ST_` prefix) > `.env` file > `config/default_settings.json`

Key settings: `TMDB_API_KEY` (required), `ST_DATA_DIR` (default: `~/.show-tracker`), `ST_MEDIA_SERVICE_PORT` (default: 7600), `ST_AUTO_LOG_THRESHOLD` (default: 0.9), `ST_REVIEW_THRESHOLD` (default: 0.7)

## Documentation

| Document | Description |
|----------|-------------|
| [Docs Index](docs/INDEX.md) | Full documentation index |
| [Setup Guide](docs/SETUP.md) | Installation, configuration, VLC/mpv setup, browser extension |
| [Architecture](docs/ARCHITECTURE.md) | System architecture, data flow, design tradeoffs |
| [API Reference](docs/API_REFERENCE.md) | Full HTTP API documentation |
| [Distribution](docs/DISTRIBUTION.md) | Building, packaging, and publishing releases |
| [ActivityWatch](docs/ACTIVITYWATCH.md) | ActivityWatch integration details |
| [Decisions](docs/DECISIONS.md) | Numbered implementation decision log (D001-D013) |
| [TODO](docs/TODO.md) | Project status and remaining work |
| [Human TODO](docs/HUMAN_TODO.md) | Manual tasks requiring human action |
| [Design Docs](docs/design/) | Original design specifications (00-09) |
| [Privacy Policy](PRIVACY_POLICY.md) | Data collection and privacy details |

## Tests

```bash
pytest                          # All 249 tests
pytest tests/unit/ -v           # Unit tests (parser, URL patterns)
pytest tests/integration/ -v   # Integration tests (100+ real-world inputs)
```

## Tech Stack

Python 3.11+ | FastAPI | SQLAlchemy | guessit | rapidfuzz | httpx | Click | Chrome Manifest V3

## License

See [docs/design/09_LICENSING_AND_DISTRIBUTION.md](docs/design/09_LICENSING_AND_DISTRIBUTION.md) for licensing details.
