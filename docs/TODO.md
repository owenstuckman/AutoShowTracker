# Project Status and TODO

## What Is Done

All five architectural layers are implemented with working code, tests, and documentation.

### Phase 0: Identification Pipeline (Complete)
- Parser with guessit integration and preprocessing for browser titles, filenames, SMTC metadata
- URL pattern matching for Netflix, YouTube, Crunchyroll, Plex, Disney+, Hulu, Amazon Prime, HBO Max, and generic pirate sites
- TMDb API client (httpx-based) with search, show detail, episode detail, find-by-external-id
- Episode resolver with alias lookup, cache, fuzzy matching (rapidfuzz, 0.80 threshold), confidence scoring
- 249 passing tests (52 unit + 197 integration across 100+ real-world inputs)
- CLI: `show-tracker identify "filename.mkv"`

### Phase 1: Windows Desktop MVP (Complete)
- **ActivityWatch integration**: REST client, event poller, bucket discovery, process manager with crash recovery, mock client for testing
- **SMTC listener**: Windows media session detection via winsdk WinRT bindings (event-driven)
- **MPRIS listener**: Linux D-Bus media session detection via dbus-next (event-driven)
- **Detection service**: Central orchestrator merging AW + SMTC/MPRIS + browser signals, deduplication, grace period, confidence routing
- **Browser extension**: Chrome Manifest V3 with content script (schema.org, Open Graph, video element monitoring, heartbeats), background service worker, popup UI
- **FastAPI API**: All endpoints for media events, watch history, show detail, episode grid, stats, unresolved queue, settings, aliases, export
- **Web UI**: Vanilla JS SPA with dashboard, shows grid, show detail with season tabs, unresolved resolution workflow, settings page
- **Storage**: Dual SQLite databases (watch_history.db + media_cache.db), SQLAlchemy ORM, repository pattern with heartbeat merging
- **CLI**: `show-tracker run`, `show-tracker init-db`, `show-tracker identify`, `show-tracker test-pipeline`

### Phase 2: Robust Detection (Complete)
- **VLC IPC**: HTTP interface client for VLC's web API (status, title, duration, position)
- **mpv IPC**: JSON IPC socket/pipe client (media-title, duration, position, path)
- **File handle inspection**: Cross-platform open file detection via psutil
- **Player service**: Orchestrator that tries native IPC then falls back to file handles
- **OCR subsystem**: Screenshot capture, per-app region cropping from JSON profiles, Tesseract + EasyOCR engines, preprocessing pipeline, orchestrator service
- **Browser event handler**: Priority chain (schema.org > Open Graph > URL pattern > page title)

### Configuration & Utilities (Complete)
- Pydantic-settings config with env vars, .env file, JSON defaults
- 50+ initial show alias seed data
- Default OCR region profiles for VLC, mpv, Plex, MPC-HC, Kodi
- Structured logging with file rotation

### Infrastructure & Distribution (Complete)
- **GitHub Actions CI**: Matrix builds on Ubuntu + Windows, Python 3.11 + 3.12 (lint, format, type check, test)
- **Linux systemd service**: User service file at `contrib/show-tracker.service`
- **Export API**: JSON and CSV export for watch history and shows (`/api/export/`)
- **Privacy policy**: `PRIVACY_POLICY.md` covering data collection, storage, browser extension permissions, third-party services
- **Third-party licenses**: `THIRD_PARTY_LICENSES.txt` listing all dependency licenses
- **Documentation**: README.md, docs/SETUP.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/API_REFERENCE.md, design docs in docs/design/

---

## What Is Left To Do

### Human-Required Tasks (see `docs/HUMAN_TODO.md` for step-by-step instructions)

#### Critical Path (COMPLETE)
- [x] **Set up Python environment** — venv created, dependencies installed, CLI verified
- [x] **Get a TMDb API key** — account created, key configured in `.env`
- [x] **Initialize databases and validate pipeline** — databases created, `show-tracker identify` tested end-to-end with TMDb resolution
- [x] **Start full service and verify web UI** — service starts, dashboard loads, API health check passes

#### Detection Source Testing (IN PROGRESS — test the ones you use)
- [ ] **Test SMTC listener on Windows** — start service, play media in VLC/browser, check logs for SMTC events, verify title/artist/playback status captured, test pause/resume
- [ ] **Test MPRIS listener on Linux** — verify D-Bus running, start service, play media, check logs for MPRIS events, test with VLC/mpv/browser
- [ ] **Test browser extension in Chrome** — load unpacked from `browser_extension/chrome/`, verify popup shows "Connected", test on Netflix/YouTube/Crunchyroll/Disney+/Hulu/Prime/HBO Max, verify heartbeats every 15s, verify pause/ended events
- [ ] **Test VLC web interface** — enable web interface in VLC preferences, set Lua HTTP password, restart VLC, verify http://localhost:8080 works, play a file, check detection
- [ ] **Test mpv IPC socket** — add `input-ipc-server` to mpv.conf, restart mpv, verify socket exists, play a file, check detection

#### Post-Setup Tuning
- [ ] **Tune confidence thresholds** — use system for 3-5 days, review unresolved queue, check for false positives in auto-logged items, adjust `ST_AUTO_LOG_THRESHOLD`/`ST_REVIEW_THRESHOLD` in `.env`
- [ ] **Seed show aliases** — add abbreviations for shows you watch via `POST /api/aliases`

---

### Code Tasks (can be done by a developer or AI assistant)

#### Phase 1D: Packaging

- [ ] **PyInstaller bundling**
  - Create a PyInstaller spec file for `src/show_tracker/main.py`
  - Bundle data files: `config/default_settings.json`, `profiles/default_profiles.json`, `web_ui/`, guessit data
  - Add hidden imports for guessit, rebulk, SQLAlchemy SQLite dialect
  - Test the built binary on a clean machine
- [ ] **System tray icon via pystray**
  - Add `pystray` and `Pillow` to dependencies
  - Create `src/show_tracker/tray.py` with icon states (running/stopped/error)
  - Menu items: "Open Dashboard" (webbrowser.open), "Start/Stop", "Quit"
  - Integrate with `show-tracker run` command — launch tray alongside uvicorn
  - Create a simple icon (16x16, 32x32, 64x64 PNGs or ICO)
- [ ] **First-run wizard**
  - On first startup (no databases exist), prompt user for TMDb API key
  - Validate the key by making a test TMDb API call
  - Write the key to `.env` or `user_settings` table
  - Could be a terminal wizard (click prompts) or a web UI page

#### Phase 2 Gaps

- [ ] **Full-window OCR spatial filtering**
  - When no app profile exists in `profiles/default_profiles.json`, fall back to full-window OCR
  - After OCR, filter results by position: keep only text in top 15% or bottom 15% of the window (where title overlays typically appear)
  - Filter by estimated font size: discard very small text (subtitles) and keep larger text (titles)
  - File to modify: `src/show_tracker/ocr/ocr_service.py`
- [ ] **TVDb API client and fallback**
  - Create `src/show_tracker/identification/tvdb_client.py` (similar pattern to `tmdb_client.py`)
  - Add TVDb search + episode lookup methods
  - In `resolver.py`, add fallback: if TMDb confidence < 0.6 AND parsed input has no season number AND episode number > 50, try TVDb (likely anime with absolute numbering)
  - Map TVDb absolute episodes to season/episode format
- [ ] **YouTube Data API integration**
  - Extend `src/show_tracker/identification/tmdb_client.py` or create a separate YouTube client
  - Use the video ID (already extracted by `url_patterns.py`) to fetch video snippet from YouTube API
  - Check if video belongs to a playlist — if the playlist is a "series", extract series/episode info
  - Requires `YOUTUBE_API_KEY` in `.env`
- [ ] **Movie support**
  - Currently the pipeline only identifies TV episodes. Extend to support movies:
  - In `parser.py`: detect when guessit returns `type: "movie"` instead of `type: "episode"`
  - In `resolver.py`: add `search_movie()` and `get_movie()` TMDb API calls
  - In `models.py`: add a `Movie` model and `MovieWatch` event (or reuse `Show` with a `media_type` column)
  - In the web UI: add a "Movies" tab alongside "Shows"

#### Phase 3: Cross-Platform

- [ ] **macOS MediaRemote listener**
  - Create `src/show_tracker/detection/macos_listener.py`
  - Use `pyobjc-framework-MediaPlayer` to access `MPNowPlayingInfoCenter`
  - Alternatively, create a small Swift helper binary that outputs JSON and communicate via subprocess
  - Implement the `MediaSessionListener` Protocol (same interface as SMTC/MPRIS)
- [ ] **macOS screenshot capture**
  - In `src/show_tracker/ocr/screenshot.py`, add macOS support
  - Use `Quartz.CGWindowListCreateImage` via `pyobjc-framework-Quartz`
  - Alternative: use `screencapture` CLI tool via subprocess
- [ ] **Linux AppImage packaging**
  - Create an AppImage build script using `appimagetool`
  - Bundle Python, all dependencies, and data files
  - Test on Ubuntu, Fedora, and Arch

#### Phase 4: Polish & Advanced Features

- [ ] **Watch time analytics**
  - Add new API endpoints: `GET /api/stats/daily`, `GET /api/stats/weekly`, `GET /api/stats/monthly`
  - Each returns time-series data: date/week/month, total watch time, episode count, top shows
  - Add binge detection: flag sessions where 3+ episodes of the same show are watched consecutively
  - In the web UI: add a "Stats" page with bar charts (can use Chart.js CDN, no build step needed)
  - Add viewing pattern analysis: most common watch times, weekday vs weekend breakdown
- [ ] **Trakt.tv import**
  - Create `src/show_tracker/sync/trakt.py`
  - Implement OAuth2 device flow (no redirect URI needed for local apps)
  - Fetch user's watch history from Trakt API
  - Map Trakt show/episode IDs to TMDb IDs (Trakt provides TMDb ID mappings)
  - Insert into local database, skipping duplicates
- [ ] **Trakt.tv two-way sync**
  - After import works, add export: push local watch events to Trakt's scrobble API
  - Add a sync timestamp to track what's been synced
  - Handle conflicts: if the same episode has different watch times locally vs Trakt, keep the earlier one
- [ ] **New episode notifications**
  - Add `plyer` to dependencies (cross-platform desktop notifications)
  - Create a background task that runs daily
  - For each show the user is watching: check TMDb for upcoming air dates
  - If an episode airs today or tomorrow, send a desktop notification
  - Store last-notified date in `user_settings` to avoid duplicate notifications
- [ ] **Plex/Jellyfin/Emby webhooks**
  - Add `POST /api/webhooks/plex`, `POST /api/webhooks/jellyfin`, `POST /api/webhooks/emby`
  - Parse each platform's webhook payload format (Plex sends JSON with library/metadata info)
  - Extract show name, season, episode from the webhook data
  - These are the highest-accuracy detection source — the media server knows exactly what's playing
  - Plex webhooks require Plex Pass; Jellyfin webhooks are free
- [ ] **Database migrations with Alembic**
  - Install Alembic: add to dev dependencies
  - Initialize: `alembic init alembic`
  - Configure `alembic/env.py` to use both `WatchBase` and `CacheBase` metadata
  - Generate initial migration: `alembic revision --autogenerate -m "initial"`
  - Test: `alembic upgrade head` on a fresh database
  - Document migration workflow in SETUP.md

#### Testing Gaps

- [ ] **End-to-end tests with ActivityWatch**
  - Create `tests/integration/test_activitywatch.py`
  - Use `MockActivityWatchClient` (already exists in `activitywatch.py`) to simulate AW events
  - Test the full flow: AW event → DetectionService → EpisodeResolver → WatchRepository
  - Verify deduplication, heartbeat merging, and grace period finalization
- [ ] **Browser extension automated testing**
  - Use Puppeteer or Playwright to automate Chrome with the extension loaded
  - Create test pages with `<video>` elements and structured metadata
  - Verify the content script extracts metadata and sends events to the API
  - Test the popup UI connection status
- [ ] **OCR accuracy benchmarks**
  - Collect screenshots from each supported player with known titles visible
  - Create a test dataset: `tests/data/ocr_screenshots/` with ground-truth labels
  - Write a benchmark script that runs OCR on each screenshot and compares to ground truth
  - Report per-player, per-resolution accuracy
- [ ] **API load testing**
  - Use `locust` or `httpx` to simulate concurrent browser extension events
  - Target: 10 concurrent "viewers" sending heartbeats every 15 seconds
  - Measure response latency and database write throughput
  - Verify no dropped events or database locks under load

#### Distribution

- [ ] **Chrome Web Store submission**
  - Host PRIVACY_POLICY.md at a public URL
  - Create developer account ($5 one-time fee)
  - Create 128x128 extension icon
  - Take store listing screenshots (1280x800)
  - ZIP the `browser_extension/chrome/` directory
  - Submit for review
- [ ] **Firefox extension port**
  - Copy Chrome extension to `browser_extension/firefox/`
  - Modify `manifest.json`: change `service_worker` to `scripts` array for background
  - Test in Firefox via `about:debugging` > "Load Temporary Add-on"
  - Submit to https://addons.mozilla.org/developers/
- [ ] **PyPI publication**
  - Verify all `[project]` metadata in `pyproject.toml` (authors, license, classifiers, urls)
  - Add `readme = "README.md"` to `[project]` if not already present
  - Build: `python -m build`
  - Upload to TestPyPI: `twine upload --repository testpypi dist/*`
  - Test install from TestPyPI in a clean venv
  - Upload to real PyPI: `twine upload dist/*`
