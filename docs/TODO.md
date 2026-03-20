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

#### Phase 2 Gaps — COMPLETE

- [x] **TVDb API client and fallback**
  - `src/show_tracker/identification/tvdb_client.py` — Full TVDb v4 client with JWT auth, search, series/episode lookup, absolute-to-season/episode mapping
  - `resolver.py` updated with `_try_tvdb_fallback()` — triggers when TMDb confidence < 0.6, no season number, episode > 50 (anime absolute numbering)
- [x] **YouTube Data API integration**
  - `src/show_tracker/identification/youtube_client.py` — YouTube Data API v3 client with video/playlist lookup, series detection from playlists/titles
  - `identification/__init__.py` updated with YouTube enrichment in `identify_media()` — tries YouTube API first for YouTube URLs, falls back to normal resolver

#### Phase 3 Remaining — COMPLETE

- [x] **Linux AppImage packaging**
  - `scripts/build_appimage.sh` — Full AppImage build script using appimagetool, bundles Python venv + all deps + data files

#### Web UI Enhancements — COMPLETE

- [x] **Stats page with charts**
  - Added Chart.js CDN to `index.html`, Stats nav link, `renderStats()` view in `app.js`
  - Daily/weekly bar charts, hourly viewing pattern chart, binge session list
- [x] **Movies tab**
  - Added Movies nav link, `renderMovies()` view with movie card grid in `app.js`

#### Testing Gaps — COMPLETE

- [x] **Browser extension automated testing**
  - `tests/e2e/test_browser_extension.py` — Playwright-based E2E tests with Chromium + extension loaded
  - Test pages served via built-in HTTP server (schema.org, OG tags, video elements, player detection)
  - Tests: metadata extraction, playback events to API, popup UI loading
  - Run: `pytest tests/e2e/test_browser_extension.py -v` (requires `pip install playwright && playwright install chromium`)
- [x] **OCR accuracy benchmarks**
  - `scripts/ocr_benchmark.py` — Benchmark script supporting Tesseract and EasyOCR engines
  - `tests/data/ocr_screenshots/manifest.json` — Ground-truth manifest (add screenshots to run)
  - Reports per-player, per-resolution accuracy with fuzzy title matching
  - Run: `python scripts/ocr_benchmark.py --engine tesseract --verbose`
- [x] **API load testing**
  - `scripts/load_test.py` — Async httpx-based load test (no extra dependencies)
  - Simulates N concurrent viewers with realistic play/heartbeat/pause/ended lifecycle
  - Also tests concurrent read endpoints (health, currently-watching)
  - Reports latency percentiles (p50/p95/p99), RPS, success rate, pass/fail assessment
  - Run: `python scripts/load_test.py --viewers 10 --duration 60 --interval 15`

#### Distribution — Automation COMPLETE, Submissions Human-Required

**Automated infrastructure (done):**
- [x] **GitHub Actions release pipeline** — `.github/workflows/release.yml` triggers on `v*` tags, builds all artifacts, creates GitHub Release
  - PyPI publish (requires `PYPI_API_TOKEN` secret)
  - Windows PyInstaller binary (ZIP)
  - Linux AppImage
  - Chrome + Firefox extension ZIPs
- [x] **Extension packaging script** — `scripts/package_extensions.sh` validates manifests and creates submission-ready ZIPs
- [x] **Version bump script** — `scripts/bump_version.sh` updates pyproject.toml, __init__.py, and both manifest.json files
- [x] **PyPI metadata** — `pyproject.toml` updated with authors, classifiers, project URLs
- [x] **Distribution guide** — `docs/DISTRIBUTION.md` with step-by-step instructions for all channels

**Human-required submissions (remaining):**
- [ ] **PyPI publication** — Run `git tag v0.1.0 && git push --tags` to trigger automated publish, or manually `python -m build && twine upload dist/*`
- [ ] **Chrome Web Store submission** — Create developer account ($5), upload `dist/show-tracker-chrome-*.zip`, see `docs/DISTRIBUTION.md`
- [ ] **Firefox Add-ons submission** — Upload `dist/show-tracker-firefox-*.zip` at https://addons.mozilla.org/developers/
