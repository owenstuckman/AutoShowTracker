# Project Status and TODO

## What Is Done

All five architectural layers are implemented with working code, tests, and documentation.

### Phase 0: Identification Pipeline (Complete)
- Parser with guessit integration and preprocessing for browser titles, filenames, SMTC metadata
- URL pattern matching for Netflix, YouTube, Crunchyroll, Plex, Disney+, Hulu, Amazon Prime, HBO Max, and generic pirate sites
- TMDb API client (httpx-based) with search, show detail, episode detail, find-by-external-id, search_movie, get_movie
- Episode resolver with alias lookup, cache, fuzzy matching (rapidfuzz, 0.80 threshold), confidence scoring
- Movie identification support with `MovieIdentificationResult` and `resolve_movie()` in resolver
- 249 passing tests (52 unit + 197 integration across 100+ real-world inputs)
- CLI: `show-tracker identify "filename.mkv"` (auto-detects movies vs episodes)

### Phase 1: Windows Desktop MVP (Complete)
- **ActivityWatch integration**: REST client, event poller, bucket discovery, process manager with crash recovery, mock client for testing
- **SMTC listener**: Windows media session detection via winsdk WinRT bindings (event-driven)
- **MPRIS listener**: Linux D-Bus media session detection via dbus-next (event-driven)
- **Detection service**: Central orchestrator merging AW + SMTC/MPRIS + browser signals, deduplication, grace period, confidence routing
- **Browser extension**: Chrome Manifest V3 + Firefox WebExtension port with content script (schema.org, Open Graph, video element monitoring, heartbeats), background service worker, popup UI
- **FastAPI API**: All endpoints for media events, watch history, show detail, episode grid, stats, unresolved queue, settings, aliases, export, webhooks, analytics
- **Web UI**: Vanilla JS SPA with dashboard, shows grid, show detail with season tabs, unresolved resolution workflow, settings page
- **Storage**: Dual SQLite databases (watch_history.db + media_cache.db), SQLAlchemy ORM, repository pattern with heartbeat merging
- **CLI**: `show-tracker run`, `show-tracker init-db`, `show-tracker identify`, `show-tracker test-pipeline`, `show-tracker setup`

### Phase 1D: Packaging (Complete)
- **PyInstaller spec**: `show_tracker.spec` with data files, hidden imports, platform-specific bundling
- **System tray icon**: `src/show_tracker/tray.py` via pystray — Open Dashboard, Quit menu items, integrated with `show-tracker run`
- **First-run wizard**: `src/show_tracker/first_run.py` — CLI wizard for TMDb API key, validation, database init; `show-tracker setup` command; auto-triggers on first `run`

### Phase 2: Robust Detection (Complete)
- **VLC IPC**: HTTP interface client for VLC's web API (status, title, duration, position)
- **mpv IPC**: JSON IPC socket/pipe client (media-title, duration, position, path)
- **File handle inspection**: Cross-platform open file detection via psutil
- **Player service**: Orchestrator that tries native IPC then falls back to file handles
- **OCR subsystem**: Screenshot capture (Windows, Linux, macOS), per-app region cropping from JSON profiles, Tesseract + EasyOCR engines, preprocessing pipeline, orchestrator service
- **Browser event handler**: Priority chain (schema.org > Open Graph > URL pattern > page title)
- **Movie support**: TMDb movie search/detail, MovieIdentificationResult, MovieWatch model, auto-detect content type

### Phase 3: Cross-Platform (Complete)
- **macOS MediaRemote listener**: Stub at `src/show_tracker/detection/macos_listener.py` with MediaSessionListener protocol (requires pyobjc on macOS to activate)
- **macOS screenshot capture**: Added to `src/show_tracker/ocr/screenshot.py` — Quartz CGWindowListCreateImage + screencapture CLI fallback

### Phase 4: Advanced Features (Complete)
- **Watch time analytics**: `GET /api/stats/daily`, `GET /api/stats/weekly`, `GET /api/stats/monthly`, `GET /api/stats/binge-sessions`, `GET /api/stats/patterns`
- **Plex/Jellyfin/Emby webhooks**: `POST /api/webhooks/plex`, `POST /api/webhooks/jellyfin`, `POST /api/webhooks/emby` — highest-accuracy detection source
- **New episode notifications**: `src/show_tracker/notifications.py` — TMDb air date checking, plyer desktop notifications, deduplication
- **Trakt.tv import**: `src/show_tracker/sync/trakt.py` — OAuth2 device flow, full watch history import, TMDb ID mapping, duplicate skip
- **Trakt.tv two-way sync**: Export local watch events to Trakt scrobble API, sync timestamp tracking
- **Database migrations**: Alembic setup with `alembic/env.py` supporting both WatchBase and CacheBase, batch mode for SQLite

### Configuration & Utilities (Complete)
- Pydantic-settings config with env vars, .env file, JSON defaults
- 50+ initial show alias seed data
- Default OCR region profiles for VLC, mpv, Plex, MPC-HC, Kodi
- Structured logging with file rotation

### Infrastructure & Distribution (Complete)
- **GitHub Actions CI**: Matrix builds on Ubuntu + Windows, Python 3.11 + 3.12 (lint, format, type check, test)
- **Linux systemd service**: User service file at `contrib/show-tracker.service`
- **Export API**: JSON and CSV export for watch history and shows (`/api/export/`)
- **Firefox extension**: Full port at `browser_extension/firefox/` (Manifest V2, browser.* APIs, gecko settings)
- **Privacy policy**: `PRIVACY_POLICY.md` covering data collection, storage, browser extension permissions, third-party services
- **Third-party licenses**: `THIRD_PARTY_LICENSES.txt` listing all dependency licenses
- **Documentation**: README.md, docs/SETUP.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, docs/API_REFERENCE.md, design docs in docs/design/

### Testing (Partial)
- **End-to-end ActivityWatch tests**: `tests/integration/test_activitywatch.py` — event parsing, URL matching, deduplication, heartbeat merging

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
- [ ] **Test browser extension in Firefox** — load from `browser_extension/firefox/` via about:debugging, verify same functionality as Chrome
- [ ] **Test VLC web interface** — enable web interface in VLC preferences, set Lua HTTP password, restart VLC, verify http://localhost:8080 works, play a file, check detection
- [ ] **Test mpv IPC socket** — add `input-ipc-server` to mpv.conf, restart mpv, verify socket exists, play a file, check detection
- [ ] **Test Plex/Jellyfin/Emby webhooks** — configure webhook URL `http://localhost:7600/api/webhooks/{platform}`, play media, verify events received

#### Post-Setup Tuning
- [ ] **Tune confidence thresholds** — use system for 3-5 days, review unresolved queue, check for false positives in auto-logged items, adjust `ST_AUTO_LOG_THRESHOLD`/`ST_REVIEW_THRESHOLD` in `.env`
- [ ] **Seed show aliases** — add abbreviations for shows you watch via `POST /api/aliases`
- [ ] **Set up Trakt.tv sync** — get Trakt API credentials, run device auth flow, import history

---

### Remaining Code Tasks

#### Phase 2 Gaps (requires external API keys or domain expertise)

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

#### Phase 3 Remaining

- [ ] **Linux AppImage packaging**
  - Create an AppImage build script using `appimagetool`
  - Bundle Python, all dependencies, and data files
  - Test on Ubuntu, Fedora, and Arch

#### Testing Gaps

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

#### Distribution (Human + Code)

- [ ] **Chrome Web Store submission**
  - Host PRIVACY_POLICY.md at a public URL
  - Create developer account ($5 one-time fee)
  - Create 128x128 extension icon
  - Take store listing screenshots (1280x800)
  - ZIP the `browser_extension/chrome/` directory
  - Submit for review
- [ ] **Firefox Add-ons submission**
  - Test in Firefox via `about:debugging` > "Load Temporary Add-on"
  - Submit to https://addons.mozilla.org/developers/
- [ ] **PyPI publication**
  - Verify all `[project]` metadata in `pyproject.toml` (authors, license, classifiers, urls)
  - Build: `python -m build`
  - Upload to TestPyPI: `twine upload --repository testpypi dist/*`
  - Test install from TestPyPI in a clean venv
  - Upload to real PyPI: `twine upload dist/*`

#### Web UI Enhancements

- [ ] **Stats page with charts**
  - Add a "Stats" page to the web UI using Chart.js CDN
  - Bar charts for daily/weekly/monthly watch time
  - Binge session highlights
  - Viewing pattern heatmap (hour x day-of-week)
- [ ] **Movies tab**
  - Add a "Movies" tab to the web UI alongside "Shows"
  - Display MovieWatch entries from the database
  - Movie detail view with poster, title, year
