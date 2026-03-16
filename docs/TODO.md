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

All remaining tasks require human action (hardware access, API keys, manual testing, or external accounts). See `docs/HUMAN_TODO.md` for a detailed checklist.

### Immediate (Before First Real Use)

- [ ] **Get a TMDb API key and validate end-to-end** — requires creating a TMDb account
- [ ] **Test SMTC listener on Windows** — requires a Windows machine with media players
- [ ] **Test MPRIS listener on Linux** — requires a Linux desktop with D-Bus
- [ ] **Test browser extension in Chrome** — requires manual loading and streaming site access
- [ ] **Confidence threshold tuning** — requires running the system for several days

### Phase 1D: Packaging (Not Started)

- [ ] PyInstaller or cx_Freeze bundling into a single executable
- [ ] Windows installer (Inno Setup or NSIS) with Start Menu shortcuts
- [ ] System tray icon via `pystray` (start/stop, open UI, status indicator)
- [ ] Auto-start on Windows login (optional, registry or Startup folder)
- [ ] Bundle ActivityWatch binaries alongside the installer
- [ ] First-run wizard for TMDb API key setup

### Phase 2 Gaps

- [ ] **Full-window OCR spatial filtering**: When no app profile exists, run full-window OCR and filter by position (top/bottom 15%) and font size
- [ ] **OCR profile tuning**: Test crop regions against real screenshots at various resolutions
- [ ] **TVDb fallback**: Integrate TVDb API for anime with absolute episode numbering
- [ ] **YouTube Data API**: Use video ID to fetch playlist/series info and detect YouTube original series
- [ ] **Movie support**: Extend pipeline to identify movies (currently TV-episode only)

### Phase 3: Cross-Platform

- [ ] **macOS MediaRemote listener**: Implement via pyobjc or Swift helper binary
- [ ] **macOS screenshot capture**: CGWindowListCreateImage for OCR
- [ ] **macOS packaging**: DMG installer, code signing, notarization
- [ ] **Linux packaging**: AppImage, possibly Flatpak

### Phase 4: Polish & Advanced Features

- [ ] **Watch time analytics**: Daily/weekly/monthly charts, binge detection, viewing patterns
- [ ] **Import**: Trakt.tv and Simkl import
- [ ] **Sync**: Optional Trakt.tv two-way sync
- [ ] **New episode notifications**: Check TMDb air dates, desktop notifications via plyer
- [ ] **Plex/Jellyfin/Emby webhooks**: Direct webhook integration (highest accuracy, lowest effort)
- [ ] **Android**: ActivityWatch Android integration, REST API sync
- [ ] **Database migrations**: Alembic setup for schema evolution

### Testing Gaps

- [ ] End-to-end tests with a real or emulated ActivityWatch server
- [ ] Browser extension automated testing
- [ ] OCR accuracy benchmarks on real player screenshots
- [ ] API load testing

### Distribution

- [ ] Chrome Web Store submission (requires privacy policy URL + developer account)
- [ ] Firefox extension port and Add-ons submission
- [ ] PyPI publication (`pip install show-tracker`)
